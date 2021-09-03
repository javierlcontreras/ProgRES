import os
import json
import subprocess as sp
import time

try:
    tmp_path = os.environ["TMPDIR"] 
except:
    tmp_path = "executer_temp_files"

class ExecuterInnerWrapper():
    def __init__(self, core_id):
        self.core_id = core_id

    # Executes code with given inputs. Executes all inputs.
    def execute_inner(self, code, inpu): 
        if not os.path.exists(tmp_path):
            os.mkdir(tmp_path)

        with open(f"{tmp_path}/INNER_CODE_INPUT_{str(self.core_id)}.json", "w+") as o:
            json.dump({"code": code, "input": inpu}, o, indent=2)

        deadp = sp.run(["python3", f"executer_inner_child.py", str(self.core_id)], capture_output=True)
        print(deadp)

        if deadp.returncode == 0:
            data = None
            try:
                with open(f"{tmp_path}/INNER_LINES_OUTPUT_{str(self.core_id)}.json", "r") as r:
                    data = json.load(r)
                    o.close()
            except Exception as E:
                print(E)
                return None, None, "cppyy core dump error", None
            return data["lines"], data["output"], data["warning"], data["executed_code"]
        else:
            print(deadp)
            return None, None, "cppyy core dump error", None


def main():
    executer_inner = ExecuterInnerWrapper(100)

    # return de line executions, the output, any warnings on the execution
    # and the actual code executed, which migh be slightly diferent (but equivalent)
    # to the one queried. The line numbers in the line per line log refer to this 
    # modified code
    lines, out, warn, code = executer_inner.execute_inner(  "int* fun_name(int var0iable, int* var1iable){\n"+
                                                            "  while (var0iable < 10) {\n"+
                                                            "    var0iable++;\n"+
                                                            "  }\n"+
                                                            "  var1iable[0] = var0iable;\n"+
                                                            "  return var1iable;\n"+
                                                            "}", \
            ["1", "{1}"])
    print(lines, out, warn)
    print(code)


if __name__ == "__main__":
    main()
