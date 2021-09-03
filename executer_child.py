import os
import resource
import sys
import json
import random

import cppyy
import ctypes

try:
    temp_path = os.environ["TMPDIR"]
except:
    temp_path = "executer_temp_files"
    

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

class ExecuterWrapperChild():
    def __init__(self):
        cppyy.cppdef("#include \"./bits.h\"")
        cppyy.cppdef("#include<ctime>")
        cppyy.cppdef("using namespace std;")

    # Transforms arrays into vectors. int** -> vector<vector<int>>
    @staticmethod
    def vectorize_type(rtype):
        nlay = rtype.count("*")
        inner_type = rtype.rstrip("* ")

        for i in range(nlay):
            inner_type = "vector<" + inner_type + ">"

        return inner_type
        
    # Output arrays are transformed into vectors before return
    # Cling does not support array outputs as value (only as pointer)
    # so we need to transform all array outputs into vector outputs
    def vectorize(self, rtype, code, name):
        nlay = rtype.count("*")
        it_nlay = nlay

        inner_type = rtype.rstrip("* ")
        if inner_type.__contains__("*"):
            return "error at vectorization, inner type contains pointers"

        rtypes = [inner_type]
        while it_nlay > 0:
            it_nlay -= 1
            inner_type = "vector<" + inner_type + ">"
            rtypes.append(inner_type)

        code = inner_type + " " + name + code.split(name)[1]
        
        ncode = []
        bcode = code.split("\n")
        for line in bcode:
            if line.__contains__("return"):
                val = line.split("return ")[1].rstrip(";");
                ind = self.get_indentation(line)
                if nlay == 1:                                   
                    ncode.append("\n"+" "*2*ind + "// vectorization of array[1] for output \n" +
                                     " "*2*ind + "if (sizeof(" + val + ") == 0) { \n" +
                                     " "*2*ind + "    return " + rtypes[1] + "(); \n" +
                                     " "*2*ind + "} else { \n" +
                                     " "*2*ind + "    int hvs = sizeof(" + val + ")/sizeof(" + val + "[0]); \n" +
                                     " "*2*ind + "    " + rtypes[1] + " hvans(hvs); \n" +
                                     " "*2*ind + "    for (int hvi=0; hvi<hvs; hvi++) hvans[hvi] = " + val + "[hvi]; \n" +
                                     " "*2*ind + "    return hvans; \n" +
                                     " "*2*ind + "}"
                                     )
                elif nlay == 2:
                    ncode.append("\n"+" "*2*ind + "// vectorization of array[2] for output \n" +
                                     " "*2*ind + "if (sizeof(" + val + ") == 0) { \n" +
                                     " "*2*ind + "    return " + rtypes[2] + "(); \n" +
                                     " "*2*ind + "} else { \n" +
                                     " "*2*ind + "    int hvw = sizeof(" + val + ")/sizeof(" + val + "[0]); \n" +
                                     " "*2*ind + "    int hvh = sizeof(" + val + "[0])/sizeof(" + val + "[0][0]); \n" +
                                     " "*2*ind + "    " + rtypes[2] + " hvans(hvw, " + rtypes[1] + "(hvh)); \n" +
                                     " "*2*ind + "    for (int hvi=0; hvi<hvw; hvi++) \n" +
                                     " "*2*ind + "        for (int hvj=0; hvj<hvh; hvj++) hvans[hvi][hvj] = " + val + "[hvi][hvj]; \n" +
                                     " "*2*ind + "    return hvans; \n" +
                                     " "*2*ind + "}"
                                     )
                elif nlay == 3:
                    ncode.append("\n"+" "*2*ind + "// vectorization of array[3] for output \n" +
                                     " "*2*ind + "if (sizeof(" + val + ") == 0) { \n" +
                                     " "*2*ind + "    return " + rtypes[3] + "(); \n" +
                                     " "*2*ind + "} else { \n" +
                                     " "*2*ind + "    int hvw = sizeof(" + val + ")/sizeof(" + val + "[0]); \n" +
                                     " "*2*ind + "    int hvh = sizeof(" + val + "[0])/sizeof(" + val + "[0][0]); \n" +
                                     " "*2*ind + "    int hvz = sizeof(" + val + "[0][0])/sizeof(" + val + "[0][0][0]); \n" +
                                     " "*2*ind + "    " + rtypes[3] + " hvans(hvw, " + rtypes[2] + "(hvh, " + rtypes[1] + "(hvz))); \n" +
                                     " "*2*ind + "    for (int hvi=0; hvi<hvw; hvi++) \n" +
                                     " "*2*ind + "        for (int hvj=0; hvj<hvh; hvj++) \n" +
                                     " "*2*ind + "            for (int hvk=0; hvk<hvz; hvk++) hvans[hvi][hvj][hvk] = " + val + "[hvi][hvj][hvk]; \n" +
                                     " "*2*ind + "    return hvans; \n" +
                                     " "*2*ind + "}"
                                     )
                else:
                    return "error at vectorization"
            else:
                ncode.append(line)
        ncode = "\n".join(ncode)
        return ncode

    # Given the argument header of the code, extract the names and types of the inputs
    # "int a, int b, map<int, int> c" -> ["a", "b", "c"] and ["int","int","map<int, int>"]
    def find_names_types(self, arguments):
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
    def arrayization(self, name, code):
        bcode = code.split("\n")
        arguments = bcode[0].split(name+"(")[1].split(")")[0]
        new_header = bcode[0].split(name)[0] + name + "("
        new_code = ["  // arrayization for input"]
        names, types = self.find_names_types(arguments)
        assert len(names) == len(types), "Assertion error, size of types and names differ"

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

                new_header = new_header + ntype + " f" + val + ", "
                
                new_code.append("  " + basic_type + " " + val + f" = f{val}.data();")
                    
                '''
                if nlay == 1:
                    new_code.append("  " + basic_type + " " + val + f"[f{val}.size()];")
                    new_code.append(f"  for (int hfi=0; hfi<(int)f{val}.size(); hfi++) {val}[hfi] = f{val}[hfi];")
                elif nlay == 2:
                    new_code.append("  " + basic_type + " " + val + f"[f{val}.size()][f{val}[0].size()];")
                    new_code.append(f"  for (int hfi=0; hfi<(int)f{val}.size(); hfi++)")
                    new_code.append(f"    for (int hfj=0; hfj<(int)f{val}[0].size(); hfj++) {val}[hfi][hfj] = f{val}[hfi][hfj];")
                elif nlay == 3:
                    new_code.append("  " + basic_type + " " + val + f"[f{val}.size()][f{val}[0].size()][f{val}[0][0].size()];")
                    new_code.append(f"  for (int hfi=0; hfi<(int)f{val}.size(); hfi++)")
                    new_code.append(f"    for (int hfj=0; hfj<(int)f{val}[0].size(); hfj++)")
                    new_code.append(f"      for (int hfk=0; hfk<(int)f{val}[0].size(); hfk++) {val}[hfi][hfj][hfk] = f{val}[hfi][hfj][hfk];")
                '''
        new_code.append("  // end arrayization for input")
        new_code.append("")
        if len(new_code) == 3:
            new_code = []
        new_header = new_header[:-2] + ") {"

        code = new_header
        if new_code != []: code = code + "\n" + "\n".join(new_code)
        code = code + "\n" + "\n".join(bcode[1:])
        
        return code

    # Given a line, returns its indentation level, which, because of the beautifier,
    # coincides with the depth level of the line in the AST.
    def get_indentation(self, line):
        ind = 0
        while ind < len(line) and line[ind] == ' ':
            ind = ind + 1
        return ind//2

    # Add lines to code to set a timeout in the C++ execution
    def put_timers(self, code):
        ncode = code.split("\n")
        new_code = []
        clock_line = "clock_t initialTimeCling = clock();"
        for i_c, c in enumerate(ncode):
            new_code.append(c)
            if i_c == 0:
                new_code.append(clock_line);
            if c.__contains__("for (") or c.__contains__("while ("):
                if c[-1] == ";": 
                    new_code[-1] = new_code[-1][:-1]
                new_code.append("if (double(clock() - initialTimeCling) / CLOCKS_PER_SEC > 1) throw \"timeout\";")
        return "\n".join(new_code)

    # Transform Cling value Literals into C++ value Literals
    def to_correct_type(self, val, inp_type):
        if "list" in inp_type or "*" in inp_type or "vector" in inp_type:
            if "set" in inp_type:
                assert False, "Both vector and set in type"
            val = val.replace('{','[')
            val = val.replace('}',']')
        val = val.replace('false', 'False').replace('true', 'True')
        return eval(val)
    
    # Transform C++ value Literals into Cling value Literals
    def to_cling_type(self, val, inp_type):
        val = val.replace('False', 'false').replace('True', 'true')
        if inp_type == "string": val = '"' + val + '"'
        if inp_type == "char": val = "'" + val + "'"
        if "." in val and val.endswith("f"): val = val[:-1]
        return val
    
    # Execute a code in a series of inputs. 
    # If check = True, the executions will stop when a false output is recieved
    #       this is an optimization for the "checking a code passes its testcases" usecase
    def execute(self, code, inputs = [], check = False, outputs = None):
        if "return" not in code:
            return [], "Function does not contain a return"
        
        old_d_limit = resource.getrlimit(resource.RLIMIT_DATA)
        resource.setrlimit(resource.RLIMIT_DATA, (2**27, old_d_limit[1]))
        
        bcode = code.split("\n")
        while bcode[0][:2] == "//": 
            bcode = bcode[1:]
        bcode[0] = bcode[0].replace('-','')
        name = bcode[0].split("(")[0].split(" ")[-1]

        code = "\n".join(bcode)
        code = self.put_timers(code)


        rtype = code.split(name)[0][:-1] 
        if rtype.__contains__("*"):
            code = self.vectorize(rtype, code, name)
            if code.__contains__("error"):
                return [], "Failed at the pre-compiler vectorization" + code
        

        code = self.arrayization(name, code)
        if code.__contains__("error"):
            return [], "Failed at the pre-compiler arrayization"

        bcode = code.split("\n")
        arguments = bcode[0].split("(")[1].split(")")[0]
        input_types = [" ".join(x.split(" ")[:-1])[:-1] for x in arguments.split(", ")]
        
        cppyy.cppdef(code)

        outs = []
        for i_inp, inp in enumerate(inputs):
            inp_tuple = tuple([self.to_correct_type(x, input_types[i]) for i, x in enumerate(inp)])
            
            val = getattr(cppyy.gbl, name)(*inp_tuple)
            val = self.to_cling_type(str(val), self.vectorize_type(rtype))
            
            if check:
                if val != outputs[i_inp]: 
                    outs.append(False)
                    break
                else:
                    outs.append(True)
            else: outs.append(val)
            
        resource.setrlimit(resource.RLIMIT_DATA, (old_d_limit[0], old_d_limit[1]))
        return outs, None
    
    def execute_check(self, code, inputs = [], outputs = []):
        return self.execute(code, inputs, True, outputs)

def main():
    code_id = int(sys.argv[1])
    
    data = None
    with open(f"{temp_path}/CODE_INPUTS_{str(code_id)}.json", "r") as r:
        data = json.load(r)
    
    executer = ExecuterWrapperChild()
    if "outputs" in data:
        out, warn = executer.execute_check(data["code"], data["inputs"], data["outputs"])
    else:
        out, warn = executer.execute(data["code"], data["inputs"])
    
    with open(f"{temp_path}/OUTPUTS_WARNING_{str(code_id)}.json", "w+") as w:
        json.dump({"outputs": out, "warning": warn}, w, indent=2)
        w.close()
    

if __name__ == "__main__":
    main()
