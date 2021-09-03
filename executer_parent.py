import os
import json
import subprocess as sp
import time

try:
    tmp_path = os.environ["TMPDIR"] 
except:
    tmp_path = "executer_temp_files"

class ExecuterWrapper():
    def __init__(self, core_id):
        self.core_id = core_id

    # Executes code with given inputs. Executes all inputs.
    def execute(self, code, inputs, outputs = None): 
        if not os.path.exists(tmp_path):
            os.mkdir(tmp_path)

        with open(f"{tmp_path}/CODE_INPUTS_{str(self.core_id)}.json", "w+") as o:
            if outputs == None:
                json.dump({"code": code, "inputs": inputs}, o, indent=2)
            else:
                json.dump({"code": code, "inputs": inputs, "outputs": outputs}, o, indent=2)
            o.close()

        deadp = sp.run(["python3", f"executer_child.py", str(self.core_id)], capture_output=True)

        if deadp.returncode == 0:
            data = None
            try:
                with open(f"{tmp_path}/OUTPUTS_WARNING_{str(self.core_id)}.json", "r") as r:
                    data = json.load(r)
                    o.close()
            except Exception as E:
                print(E)
                return None, "cppyy core dump error"
            return data["outputs"], data["warning"]
        else:
            print(deadp)
            return None, "cppyy core dump error"
    
    # Executes code with given inputs and checks the real output is the expected outputs. 
    # Returns results if a single unmatched output is found, so it might execute less inputs than given
    def execute_check(self, code, inputs, outputs):
        return self.execute(code, inputs, outputs)

def main():
    executer = ExecuterWrapper(1000)

    outs, warn = executer.execute("int fun_name(int var0iable, int* var1iable){\n  return var0iable+var1iable[0];\n}", \
            [["1", "{1}"], ["2", "{1}"]])
    print(outs, warn)

    checks, warn = executer.execute_check("int fun_name(int var0iable, int * var1iable){\n  while (var0iable < 100000) {\n    var0iable++;\n  }\n  return var0iable+var1iable[0];\n}", \
            [["1", "{1}"], ["2", "{1}"]], ["2", "3"])
    print(checks, warn)
    
    checks, warn = executer.execute_check("int fun_name(int var0iable, map<int, int> var1iable){\n  return var0iable+var1iable[0];\n}", \
            [["1", "{0: 1}"], ["2", "{0: 1}"]], ["2", "3"])
    print(checks, warn)

if __name__ == "__main__":
    main()
