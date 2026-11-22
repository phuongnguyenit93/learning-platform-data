# Inspecting Java Bytecode

After compiling Java source code, the `javac` compiler produces `.class` files containing **bytecode**. Bytecode is the intermediate instruction set that the Java Virtual Machine (JVM) reads, verifies, and executes. Inspecting bytecode helps you understand what the compiler translated your source code into, determine the class file version, view method calls and constants, and diagnose compatibility errors between Java versions.

The primary command-line tool for reading class file structures and disassembling bytecode is **`javap`**, provided in the JDK.

## 1. What is Bytecode?

Java bytecode is an intermediate instruction set stored in a class file. It is designed so that the JVM can execute it across different operating systems and hardware architectures.

General workflow:

1. A developer writes source code in a `.java` file.
2. `javac` checks the source code and compiles it into bytecode.
3. The bytecode is stored in a `.class` file.
4. The JVM loads the class, verifies its validity, and executes the bytecode.
5. The JVM can interpret instructions or compile frequently executed code into machine code using the JIT (Just-In-Time Compiler).

Example:

```text
BytecodeDemo.java
       |
       | javac
       v
BytecodeDemo.class
       |
       | JVM: load, verify, execute
       v
Program output
```

Bytecode is not CPU-specific machine code. A `.class` file can generally run on different platforms if a compatible JVM is installed and the required dependencies are present.

## 2. Creating a Class File to Inspect

Create the file **`BytecodeDemo.java`**:

```java
public class BytecodeDemo {
    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        int result = add(7, 5);
        System.out.println("result=" + result);
    }
}
```

Compile into the `out` directory:

```bash
javac -g -d out BytecodeDemo.java
```

Explanation:

- `-g` instructs the compiler to generate debug information such as line numbers and local variable information.
- `-d out` sets the root directory for the output class files.
- `BytecodeDemo.java` is the source code being compiled.

After compilation, the directory structure is:

```text
project/
  BytecodeDemo.java
  out/
    BytecodeDemo.class
```

Because the class does not declare a package, `BytecodeDemo.class` is located directly inside `out`.

## 3. What is javap?

`javap` is a disassembler tool included with the JDK. It reads class files and displays information about classes, methods, fields, signatures, and bytecode.

Verify the tool:

```bash
javap -help
```

If the terminal does not recognize `javap`, check that the JDK is installed and that the JDK's `bin` directory is in `PATH`. `javap` is typically not included in a runtime-only package.

To view the public declarations of a class:

```bash
javap -classpath out BytecodeDemo
```

Abbreviated output:

```text
Compiled from "BytecodeDemo.java"
public class BytecodeDemo {
  public BytecodeDemo();
  public static int add(int, int);
  public static void main(java.lang.String[]);
}
```

This view displays the class and method signatures. It does not yet display the bytecode instructions inside each method.

## 4. Viewing Bytecode with the -c Option

The `-c` option instructs `javap` to disassemble the bytecode of the methods.

Run:

```bash
javap -classpath out -c BytecodeDemo
```

In the output, find the method:

```text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
```

This is a typical instruction sequence that `javac` generates for the `add` method in the example:

| Instruction | Meaning |
| --- | --- |
| `iload_0` | Pushes the integer variable at local variable slot 0 onto the operand stack |
| `iload_1` | Pushes the integer variable at local variable slot 1 onto the operand stack |
| `iadd` | Pops two int values from the stack, adds them, and pushes the result back onto the stack |
| `ireturn` | Returns the int value at the top of the stack |

The numbers before the colons such as `0`, `1`, `2`, `3` are bytecode offsets within the method's code section, not line numbers in the source code.

In many cases, instruction names begin with a letter indicating the data type:

- `i`: operates on `int`.
- `l`: operates on `long`.
- `f`: operates on `float`.
- `d`: operates on `double`.
- `a`: object reference.

Some common instructions:

| Instruction | Meaning |
| --- | --- |
| `bipush` | Pushes a signed byte constant onto the stack |
| `iconst_0`, `iconst_1` | Pushes small int constants onto the stack |
| `iload`, `istore` | Reads/writes an int variable in the local variable array |
| `aload`, `astore` | Reads/writes a reference variable |
| `iadd`, `isub`, `imul`, `idiv` | Integer addition, subtraction, multiplication, division |
| `getstatic`, `putstatic` | Reads/writes a static field |
| `getfield`, `putfield` | Reads/writes an instance field |
| `invokevirtual` | Invokes an instance method using virtual dispatch |
| `invokestatic` | Invokes a static method |
| `invokespecial` | Invokes a constructor or certain special methods |
| `invokeinterface` | Invokes a method through an interface |
| `ireturn`, `areturn`, `return` | Returns an int, a reference, or finishes a void method |

Bytecode is a stack-based instruction format. When reading a disassembly, track values pushed onto the stack, popped off the stack, and stored in local variables to understand the execution flow.

The instructions for the `main` method can vary across JDK and compiler versions. For example, string concatenation may compile to `invokedynamic` on modern JDKs. Therefore, inspect the actual output of the JDK you are using rather than expecting the entire disassembly to match a template identically.

## 5. Viewing Class File Structure with -verbose

The `-verbose` option (abbreviated `-v`) displays detailed information about the class file.

Run:

```bash
javap -classpath out -verbose BytecodeDemo
```

The output typically includes:

- Class file version (minor version and major version).
- Class access flags.
- Current class name and superclass name.
- Constant pool.
- Interfaces, fields, and methods.
- Class and method attributes.
- Code attribute, bytecode, and exception table.
- Debug information if the class was compiled with those attributes.

### Constant pool

The constant pool is a table containing constants and references used by the class file. Common entries include:

- UTF-8 strings used for class names, method names, descriptors, and literals.
- Class and interface information.
- Field and method references.
- Integer, floating-point, and string literals.
- Name-and-type entries and references used for linking.

For example, the call `System.out.println(...)` requires references to the `java/lang/System` class, the `out` field, and the `println` method. Related information can be observed in the constant pool and bytecode.

The constant pool is not a list of all objects currently existing on the heap. It is a class file data structure used to describe constants and references.

## 6. Checking the Class File Version

In the `javap -verbose` output, look for lines similar to:

```text
minor version: 0
major version: 61
```

`major version` identifies the class file format version. Some common values:

| Java Version | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

For example, major version 61 corresponds to Java 17. The runtime must support that class file version to load the class normally.

If you compile with a newer JDK and run on a runtime that is too old, you may encounter the error:

```text
UnsupportedClassVersionError
```

With JDK 9 and later, you can use `--release` to compile for a supported target platform version:

```bash
javac --release 17 -d out17 BytecodeDemo.java
```

In this case, the generated class file targets the Java 17 platform and the corresponding standard Java APIs. `--release` helps control compatibility at the language, bytecode, and standard API levels; it does not automatically guarantee that all external libraries or native code are compatible.

## 7. Viewing Access Flags, Descriptors, and Private Members

Other useful options:

| Option | Purpose |
| --- | --- |
| `-p` or `-private` | Also displays private members |
| `-s` | Displays internal type signatures/descriptors |
| `-l` | Displays the line number table and local variable table if present |
| `-constants` | Displays eligible static final constant values |
| `-v` | Displays detailed class file information |

Example:

```bash
javap -classpath out -p -s BytecodeDemo
```

The `-p` option is useful when you need to inspect non-public methods or fields. The `-s` option displays member descriptors; for example, the descriptor of a method that takes two `int`s and returns an `int` is:

```text
(II)I
```

In a descriptor:

- `I` represents the `int` type.
- `V` represents the `void` type.
- `L...;` represents a reference type.
- `[` represents an array.

For example, the descriptor `([Ljava/lang/String;)V` corresponds to a method that takes a `String` array and returns no value.

## 8. Viewing Debug Information and Mapping Back to Source Code

When compiling with the `-g` option, the compiler can store additional debug attributes such as:

- `LineNumberTable`: maps bytecode offsets back to source code line numbers.
- `LocalVariableTable`: local variable names, types, and their scope in bytecode.
- `SourceFile`: the name of the associated source file.

Inspect with:

```bash
javap -classpath out -l BytecodeDemo
```

Or combine multiple options:

```bash
javap -classpath out -c -l -p BytecodeDemo
```

If the corresponding debug information is absent, `javap -l` may not display these tables. You can recompile with `javac -g` to request debug information generation.

Local variable names are not always stored in the class file. Therefore, when inspecting a class built in size-optimized mode or without debug info, you may only see slots and data types instead of the original variable names.

## 9. Checking JVM Bytecode Verification

When the JVM loads a class, it checks the class file and bytecode to ensure structural validity and type-safety rules are satisfied before execution.

The bytecode verifier performs checks such as:

- Valid class file structure and instruction format.
- Data types on the operand stack at points in the control flow.
- Local variable usage.
- Type consistency at branches and control-flow merge points.
- Access rules and JVM constraints.

You can instruct the JVM to verify classes in full verification mode at runtime:

```bash
java -Xverify:all -cp out BytecodeDemo
```

Program output:

```text
result=12
```

`-Xverify:all` instructs the JVM to verify all involved classes in full verification mode. This is a useful diagnostic option when investigating bytecode or class loading issues; it does not replace functional testing.

Bytecode verification only checks JVM rules and structural consistency. It does not prove that the program's algorithm is correct in terms of business logic, does not detect all logic bugs, and does not guarantee that the application is free of security vulnerabilities.

## 10. Distinguishing Bytecode from JIT-Generated Machine Code

Bytecode resides in `.class` files and serves as input to the JVM. At runtime, the JVM can:

- Interpret bytecode.
- Collect profiling information about execution behavior.
- Use the JIT compiler to convert frequently executed code into machine code suited for the CPU.
- Optimize based on runtime information and perform deoptimization when optimization assumptions no longer hold.

Therefore, the output of `javap -c` shows the bytecode stored in the class file, not the final machine code that the CPU executes after JIT optimization.

You should not infer actual performance solely from the number of bytecode instructions. Performance also depends on the JIT, input data, GC, operating system, CPU, libraries, and how benchmarks are conducted.

## 11. Common javap Commands

Assuming the class file is in the `out` directory:

| Purpose | Command |
| --- | --- |
| View class signature | `javap -classpath out BytecodeDemo` |
| View bytecode | `javap -classpath out -c BytecodeDemo` |
| View class file details | `javap -classpath out -v BytecodeDemo` |
| View including private members | `javap -classpath out -p BytecodeDemo` |
| View descriptors | `javap -classpath out -s BytecodeDemo` |
| View debug information | `javap -classpath out -l BytecodeDemo` |
| Combine bytecode and debug info | `javap -classpath out -c -l -p BytecodeDemo` |

If the class belongs to a package, use its fully qualified name, such as `com.example.BytecodeDemo`, and set the classpath to the root directory containing the `com` directory.

You can inspect a class inside a JAR by adding the JAR to the classpath:

```bash
javap -classpath lib/example.jar -c com.example.Tool
```

If there are multiple dependency locations, pass the classpath list with the appropriate separator:

- Windows: semicolon `;`.
- macOS/Linux: colon `:`.

## 12. Common Errors When Inspecting Bytecode

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `javap` is not recognized | JDK is not installed or `bin` directory is not in `PATH` | Install the JDK and check `PATH` |
| `Class not found` when running javap | Incorrect classpath or non-fully-qualified class name | Set the classpath to the root directory and use the full package name |
| No bytecode shown | Missing the `-c` option | Run `javap -c` |
| Local variable names not shown | Class lacks `LocalVariableTable` | Compile with `javac -g` and inspect again |
| Runtime reports `UnsupportedClassVersionError` | Runtime does not support the class file's major version | Upgrade the runtime or compile with the appropriate `--release` |
| Bytecode differs from example | Different JDK/compiler, compiler options, or optimizations | Rely on actual output; only compare instruction meanings and execution flow |
| Dependent class not found | Missing JAR or dependency directory in classpath | Add the dependency when running and check the classpath |

## 13. Recommended Bytecode Inspection Workflow

When investigating a class file:

1. Compile the source code with the exact JDK and keep the `.class` file.
2. Use `javap -classpath ... -c` to view the bytecode instructions.
3. Use `javap -verbose` to check the major version, constant pool, access flags, and attributes.
4. Use `javap -p -s` to inspect private members and descriptors.
5. Use `javap -l` if you need to map bytecode back to line numbers or variable names.
6. Use `java -Xverify:all` when you need to check JVM verification.
7. Cross-check the classpath, runtime version, and dependencies if the class fails to load.

Keeping the source code, compilation command, and JDK version makes inspection results reproducible. For automated build projects, store compiler version information and build configuration alongside artifacts to facilitate investigation.

## 14. Key Takeaways

- `.java` is source code; `.class` contains bytecode and class metadata.
- `javap -c` is used to read method bytecode.
- `javap -v` displays the class file structure, constant pool, and major version.
- `javap -p`, `-s`, and `-l` help view private members, descriptors, and debug information, respectively.
- The JVM verifier checks bytecode validity before execution; `-Xverify:all` requests full verification mode.
- Bytecode differs from the machine code that the JIT may generate while the application is running.
- The class file's major version must be supported by the runtime.

Knowing how to use `javap` helps developers look deeper into compilation results, understand how Java represents instructions and data, and diagnose compatibility issues between the compiler, class file, and JVM.
