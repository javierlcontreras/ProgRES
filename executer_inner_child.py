from hashlib import md5
import os
import sys
import random
import json
import math
import pexpect
import traceback
import cppyy
import inspect
import re


id_num = 0

try:
    tmp_path = os.environ["TMPDIR"] 
except:
    tmp_path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + "/executer_temp_files"

sys.path.insert(0, tmp_path)
from clang.cindex import Config, Index, TokenKind

path_to_clang = f"{tmp_path}/clang/lib"
path_to_cling = f"{tmp_path}/cling/bin/cling"

Config.set_library_path(path_to_clang)
pcling = None

line_per_line_DB = []


def send_statement(line):
    pcling.expect("\[cling\]\$")
    pcling.sendline(line)
    pcling.expect("\[cling\]\$")
    pcling.sendline("")

    if len(sys.argv) == 4 and int(sys.argv[3]) >= 2: #For debugging
        print("send_statement(): sending ", line, " recieved", pcling.before, ".")
    
    return pcling.before    

# Separates type (which comes in parenthesis) from value and return both
def separate_cling_return_expression(out):
    rel = "\n".join(out.split("\n")[1:])
    f = -1
    s = -1
    for i, c in enumerate(rel):
        if f == -1 and c == "(":
            f = i
        if s == -1 and c == ")":
            s = i
    return rel[f+1:s], rel[s+2:-2]


# Finds all tokens for that line, looks for identifiers and checks their values
def compute_line_state(line):
    state = {}
    index = Index.create()
    tu = index.parse(f'tmp_{id_num}.cpp', args=['-std=c++11'], unsaved_files=[(f'tmp_{id_num}.cpp', line)])
    tokens = tu.get_tokens(extent=tu.cursor.extent)
    for token in tokens:
        if token.kind == TokenKind.IDENTIFIER:
            out = send_statement(token.spelling)
            # Some of the IDENTIFIERS are not valid variables (like functions, streams...)
            if not str(out).__contains__("error") and not str(out).__contains__("warning") and \
                    not str(out).__contains__("ostream") and not str(out).__contains__("istream") \
                    and not str(out).__contains__("unction"):
                ctype, cvalue = separate_cling_return_expression(out)
                state[token.spelling] = [ctype, cvalue]

    if len(sys.argv) == 4 and int(sys.argv[3]) >= 2: # For debugging
        print("compute_line_state(): ", line.replace("\n", ""), " the state is: ", state)

    return state

# checks the state of the line variables before and after and runs the line
# if is_exp = True it will return the content of the expression (when inside if/while)
def execute_line(line_number, line, is_exp=False):

    state_before = compute_line_state(line)
    
    out = None
    return_bool = is_exp

    out = send_statement(line)
    if str(out).__contains__("false") and not "rror" in str(out):
        ct, cv = separate_cling_return_expression(out)
        if "false" in cv:
            return_bool = False
    if str(out).__contains__("variable length array declaration"):
        nline = ""
        for arg in line.split("["):
            if not "]" in arg:
                nline += arg + "["
                continue
            assert arg.count("]") == 1, "Array declared with result of array"
            argv = arg.split("]")[0]
            args = arg.split("]")[1]
            outi = send_statement(argv)
            print("EEOEOEOOEOEO", argv, outi, "EOEOEOEOEOOE")
            assert not "rror" in outi and not "?" in outi, "Error in useful array size"
            ctt, cvv = separate_cling_return_expression(outi)
            nline += cvv + "]" + args
        line = nline 
        out = send_statement(line)

    if str(out).__contains__("redefinition"):
                    # Remove complain and re-run
        checkline = line
        if " = " in checkline: checkline = checkline.split("=")[0]
        assert not "*" in checkline and not "[" in checkline, "redeclaration of array"
        if ("vector" in line or "string" in line):    
            assert "(" not in line, "redeclaration of collection using constructor"
        if len(state_before) == 1:
            var = [aux_key for aux_key in state_before.keys()][0]
            default = "{}"
            if state_before[var][0] == "std::string &":
                default = '""'
            elif state_before[var][0] == "char":
                default = "''"
            elif state_before[var][0] == "int" or state_before[var][0] == "long long" or state_before[var][0] == "double" or state_before[var][0] == "float":
                default = "0"
            send_statement(var + " = " + default + ";")

        redefined_line = line
        redefined_line = redefined_line.lstrip(" ")
        start_rl = 1
        if (redefined_line.startswith('long') or redefined_line.startswith('const') or 
                redefined_line.startswith('unsigned')): start_rl=2
        redefined_line = " ".join(redefined_line.split(" ")[start_rl:])
        for i in state_before:
            state_before[i][1] = "null"
        out = send_statement(redefined_line)
        assert "rror" not in out, "Error in useful redefinition line"
    elif str(out).__contains__("variable length array declaration not allowed at file scope"):
                    # Handles things like: int v[2+3][4]
        line_copy = line.split("]")
        for i in range(len(line_copy)):
            inside = line_copy[i].split("[")
            if len(inside) == 2:
                _, inside[1] = separate_cling_return_expression(send_statement(inside[1]))
            line_copy[i] = "[".join(inside)
        line_copy = "]".join(line_copy)
        send_statement(line_copy)
    elif str(out).__contains__("error"):
                    # Parent will see it as dead
        assert False, "Error in useful line (" + str(line_number) + ") " + line + ": " + out

    state_after = compute_line_state(line)

    state = {} # Differences between before and after
    for var in state_after:
        bef = "null" # For declarations
        if state_before.__contains__(var):
            bef = state_before[var][1]
        state[var] = [state_after[var][0], bef, state_after[var][1]]
    if is_exp: # Also saves expressions
        ctype, cvalue = separate_cling_return_expression(out)
        state[line + " ... (CONDITIONAL_EXPRESSION)"] = [ctype, "null", cvalue]
        if cvalue == "0" or cvalue == "False":
            return_bool = False

    global line_per_line_DB
    line_per_line_DB.append([line_number, state])


    if len(sys.argv) == 4 and int(sys.argv[3]) >= 1:
        print("(", line_number, ") ", line, ": ", state, "\n")

    return return_bool

# ---------------------- STACK EMULATOR --------------------------------------

# Gets expressions inside if(), while(), etc
def get_bool_check(line):
    l, r = 0, len(line)
    for i, c in enumerate(line):
        if c == '(':
            l = i
            break
    for i, c in enumerate(line):
        if c == ')':
            r = i
    return line[l+1:r]


# Assumes two spaces, coming from the beautifier
def get_indentation(line):
    ind = 0
    while ind < len(line) and line[ind] == ' ':
        ind = ind + 1
    return ind//2


# Ensure parenthesis get closed
def advance_parentheses(line, accept_spaces = True, accept_parenthesis = False, closure_corners = True):
    it = 0
    ccorn = 0
    cparen = 0
    cclau = 0
    while it < len(line):
        if ((accept_spaces and line[it] == " ") or line[it] == "," or line[it] == ";" or (accept_parenthesis and line[it] == ")")) and (not closure_corners or ccorn == 0) and cparen == 0 and cclau == 0:
            return it
        elif line[it] == "<":
            ccorn += 1
        elif line[it] == ">":
            ccorn -= 1
        elif line[it] == "{":
            cparen += 1
        elif line[it] == "}":
            cparen -= 1
        elif line[it] == "[":
            cclau += 1
        elif line[it] == "]":
            cclau -= 1
        
        it += 1

    return len(line)


def treat_test(code):
    code = code.split("\n")
    global line_per_line_DB
    line_per_line_DB = []

    # generate cling instance
    global pcling
    if pcling != None and pcling.isalive():
        pcling.terminate(force=True)
        # Open Cling; timeout is 10 minutes
    pcling = pexpect.spawnu(f'{path_to_cling} --nologo', timeout=600)
    
    # create stack of while if and elses
    # stack item -> name of field, bool, depth, line_number, iteration
    stack = []
    line_number = 0
    while line_number < len(code):
        # CHECK SIZE OF LOGGER
        if len(sys.argv) == 4 and int(sys.argv[3]) >= 1:
            print("Size of log for now: ", sys.getsizeof(str(line_per_line_DB)))
        #assert sys.getsizeof(str(line_per_line_DB)) < 1e6, f"output log too big{sys.getsizeof(str(line_per_line_DB))}" # 1e6 = 1MB
        if sys.getsizeof(str(line_per_line_DB)) >= 1e6:
            if sys.getsizeof(str(line_per_line_DB[-1])) >= 1e4:
                assert False, "HUGELINE: A single line has size more than 1e3"
            line_per_line_DB = line_per_line_DB[:-1]
            return None, "Line per line too big"

        #print(code[line_number])
        depth = get_indentation(code[line_number])
        if len(stack) != 0 and depth == stack[-1][2]:
        
            top = stack[-1]

            field            = top[0] # Whether deepest nest is an if or a while
            bool_exp        = top[1] # To handle expression of the while loop
            original_depth  = top[2] # The depth of the nest I'm in
            original_line   = top[3] # Which line the nest started
            iteration        = top[4] # Iteration of the while

            if field == "if" or field == "else if" or field == "else":
                while True:
                    if code[line_number].__contains__("} else if ") or code[line_number].__contains__("} else {"):
                        line_number += 1
                        while depth < get_indentation(code[line_number]):
                            line_number += 1
                    else:
                        assert code[line_number].__contains__("}"), "Ifs finalizes not in }, but in " + code[line_number] + " at " + str(line_number)
                        break
                line_number += 1
                stack = stack[:-1]
            elif field == "while":
                check_result = execute_line(original_line, bool_exp, True)
                
                check_state = line_per_line_DB[-1]
                line_per_line_DB = line_per_line_DB[:-1]

                if check_result: # while condition still true
                    line_number = original_line + 1 # original line is the while(expression) {
                    '''
                    rand = random.randint(0, max(0, iteration-100)) ## TODO(jlcontreras): minimum number of iterations
                    if rand != 0:
                        lit = len(line_per_line_DB) - 1
                        
                        while lit >= 0 and line_per_line_DB[lit][0] != original_line:
                            #print ("I will be deleting ", line_per_line_DB[lit])
                            lit -= 1
                        
                        assert lit > 0, "Can not find the previous iteration of a while"
                        line_per_line_DB = line_per_line_DB[:lit]
                    '''
                    line_per_line_DB.append(check_state)

                    stack[-1][4] += 1
                else:
                    line_number += 1
                    stack = stack[:-1]
            else:
                break
        elif code[line_number].__contains__("main("):
            stack.append(["main", None, depth, line_number, None])
            line_number += 1
        elif code[line_number].__contains__("if ("):
            check = get_bool_check(code[line_number])
            check_result = execute_line(line_number, check, True)
            if check_result:
                stack.append(["if", None, depth, line_number, None])
                line_number += 1
            else:
                line_number += 1
                while depth < get_indentation(code[line_number]):
                    line_number += 1
                while True:
                    if code[line_number].__contains__("} else if ("):
                        check2 = get_bool_check(code[line_number])
                        check_result2 = execute_line(line_number, check2, True)
                        if check_result2:
                            stack.append(["else if", None, depth, line_number, None])
                            line_number += 1
                            break
                        else:
                            line_number += 1
                            while depth < get_indentation(code[line_number]):
                                line_number += 1
                    elif code[line_number].__contains__("} else {"):
                        stack.append(["else", None, depth, line_number, None])
                        line_number += 1
                        break
                    else:
                        line_number += 1
                        break
        elif code[line_number].__contains__("while ("):
            check = get_bool_check(code[line_number])
            check_result = execute_line(line_number, check, True)
            if check_result:
                stack.append(["while", check, depth, line_number, 0])
                line_number += 1
            else:
                line_number += 1
                while depth < get_indentation(code[line_number]):
                    line_number += 1
                assert code[line_number].__contains__("}"), "While finalizes not in }, but in " + code[line_number] + " at " + str(line_number)
                line_number += 1
        elif "return" in code[line_number]:
            expression = ";".join(code[line_number].split("return ")[-1].split(";")[:-1])
            cliout = send_statement(expression)
            assert not "rror" in cliout and not "arning" in cliout, "Error in useful return line"
            typ, value = separate_cling_return_expression(cliout)
            return value, None 

        else:
            out = execute_line(line_number, code[line_number])
            line_number += 1

    return None, "No return found in function execution"


# Given the argument header of the code, extract the names and types of the inputs
# "int a, int b, map<int, int> c" -> ["a", "b", "c"] and ["int","int","map<int, int>"]
def find_names_types(arguments):
    argl = arguments.split(", ")
    argL = []
    for arg in argl:
        if len(argL) == 0 or (not "map" in argL[-1] and not "pair" in argL[-1]) or ", " in argL[-1]:
            argL.append(arg)
        else:
            argL[-1] += ", " + arg
    types, names = [], []
    for arg in argL:
        types.append(" ".join(arg.split(" ")[:-1]))
        names.append(arg.split(" ")[-1])
    return names, types


# Input arrays are transformed from vectors
# Cling does not support array inputs as value (only as pointer)
# so we need to transform all array inputs into vector inputs
def arrayization(code, name):
    bcode = code.split("\n")
    arguments = bcode[0].split(name+"(")[1].split(")")[0].replace("*", "* ")
    new_header = bcode[0].split(name)[0] + name + "("
    names, types = find_names_types(arguments)
 
    for it in range(len(names)): 
        val = names[it]
        itype = types[it]

        nlay = itype.count("*") + itype.count("[")
        if nlay == 0:
            new_header = new_header + itype + " " + val + ", "
        else:
            ntype = itype.rstrip("*[] ")
            basic_type = itype.rstrip("*[] ")
            for i in range(nlay):
                ntype = "vector<" + ntype + ">"

            new_header = new_header + ntype + f" " + val + ", "

    bcode[0] = new_header[:-2] + ") {"
    print("\n".join(bcode))
    return "\n".join(bcode)

# Transforms a function into a main code without arguments
def front_transformation(code, fun_name, inputs):
    bcode = code.split("\n")
    ncode = ["#include \"./bits.h\"", "using namespace std;"]
    extralines = []

    for i_line, line in enumerate(bcode):
        if fun_name in line:
            arguments = ")".join(line.split(fun_name+"(")[-1].split(")")[:-1])
            names, types = find_names_types(arguments)
            
            ncode.append("int main() {")

            for j_name, name in enumerate(names):
                ncode.append(f"  {types[j_name]} {name} = {inputs[j_name]};")

        else: ncode.append(line)      

    return "\n".join(ncode)


def whilify_fors(code, num):
    line = code[num]
    l, r = 0, len(line)
    for i, c in enumerate(line):
        if c == '(':
            l = i
            break
    for i, c in enumerate(line):
        if c == ')':
            r = i

    line = line[l+1:r]
    line = line.split(';')

    ind = get_indentation(code[num])
    code[num] = "  "*ind + "while (" + line[1] + ") {"
    code.insert(num, "  "*ind + line[0] + "; // whilified")
    num = num + 2
    while num < len(code) and ind < get_indentation(code[num]):
        num = num + 1
    code.insert(num, "  "*(ind+1) + line[2] + ";")

def take_empty_lines_out(code):
    L = code.split("\n")
    NL = []
    for l in L:
        if (l != ""): NL.append(l)
    return "\n".join(NL)

def beautify(code):
    code = take_empty_lines_out(code)

    filer = open(f"{tmp_path}/{id_num}.txt", "w+")
    filer.write(code)
    filer.close()
    beautified_file = os.popen(f"{tmp_path}/cling/bin/clang-format"+" -style=\"{ ColumnLimit: 0 }\" "+f"{tmp_path}/{id_num}.txt")
    return beautified_file.read()
    
def beautify_split(code):
    return beautify("\n".join(code)).split("\n")

def main():
    global id_num
    id_num = int(sys.argv[1])

    data = None
    with open(f"{tmp_path}/INNER_CODE_INPUT_{str(id_num)}.json", "r") as r:
        data = json.load(r)
    
    code = beautify(data["code"])
    inp = data["input"]
    
    bcode = code.split("\n")
    while bcode[0][:2] == "//": 
        bcode = bcode[1:]
    bcode[0] = bcode[0].replace('-','')
    name = bcode[0].split("(")[0].split(" ")[-1]
    
    # whilify the main
    bcode = code.split("\n")
    for num, line in enumerate(bcode):
        if re.search("for \(", line):
            whilify_fors(bcode, num)
    code = beautify("\n".join(bcode))
 
    code = arrayization(code, name)
    if code.__contains__("error"):
        assert False, "Failed at the pre-compiler vectorization" + code
    
    code = front_transformation(code, name, inp)
    code = beautify(code)

    # whilify the main
    bcode = code.split("\n")
    for num, line in enumerate(bcode):
        if re.search("for \(", line):
            whilify_fors(bcode, num)
    code = beautify("\n".join(bcode))
 
    bcode = code.split("\n")
    ncode = []
    for line in bcode:
        nline = line.split("//")[0].rstrip(" ")
        if nline.strip(" ") != "":
            ncode.append(nline)
    code = "\n".join(ncode)
    
    out, warn = treat_test(code)

    with open(f"{tmp_path}/INNER_LINES_OUTPUT_{str(id_num)}.json", "w") as w:
        json.dump({"lines": line_per_line_DB, "output": out, "warning": warn, "executed_code": code}, w)
    
if __name__ == "__main__":
    main()
