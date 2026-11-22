# Reading Java Bytecode with javap

**javap** is a command-line tool bundled with the JDK for reading class file information and displaying bytecode in a more readable mnemonic form. It helps you understand how the compiler has transformed Java source code into JVM instructions, inspect class file versions, method descriptors, the constant pool, debug information, and class structure.

javap is often called a *disassembler* for Java bytecode. It does not fully reconstruct the original source code like a decompiler. The tool displays the structure stored in the .class file; local variable names, comments, source formatting, and certain other information may be lost after compilation.

## 1. What Is Bytecode and How Does javap Help?

When compiling a Java file, javac translates source code into one or more class files. Each class file contains a structure understood by the JVM, including the constant pool, class information, fields, methods, attributes, and the bytecode sequences of methods.

Bytecode is the intermediate instruction set of the JVM, not machine code specific to a single CPU. The JVM can interpret bytecode or compile frequently executed code into machine code using the JIT compiler.

For example, the Java expression:

~~~java
int sum = a + b;
~~~

can be represented by JVM instructions such as:

~~~text
iload_0
iload_1
iadd
istore_2
~~~

These instructions sequentially load two int variables onto the operand stack, add them, and store the result in a local variable slot. javap helps you inspect similar instructions inside actual class files.

Common use cases for javap:

- Understanding what bytecode the compiler generates for a piece of Java code.
- Checking the class file major/minor version.
- Reading method descriptors, access flags, and the constant pool.
- Finding method calls, field accesses, control branches, and exception handlers.
- Investigating differences between compiler options or JDK versions.
- Verifying classes inside JARs, dependencies, or modules.
- Inspecting debug information such as line number and local variable tables.

## 2. Preparation and Basic Syntax

javap is located in the **bin** directory of the JDK, alongside tools like javac, java, and jar. You can check it with:

~~~bash
javap -version
javap -help
~~~

General syntax:

~~~bash
javap [options] class...
~~~

The input is usually a fully qualified class name, a path to a .class file, or a class found via the classpath/module path.

For example, if the class is in package demo and the output directory is out:

~~~bash
javap -classpath out demo.Calculator
~~~

If passing the class file path directly:

~~~bash
javap out/demo/Calculator.class
~~~

A class name with a package must use dots, such as demo.Calculator; a file path uses slashes matching the directory structure. When inspecting multiple classes, you can pass multiple class names in the same command.

## 3. Important javap Options

| Option | Purpose |
|---|---|
| -c | Display bytecode instructions in methods |
| -p or -private | Show all class members, including private ones |
| -v or -verbose | Show detailed information: constant pool, flags, attributes, stack map frames, and more metadata |
| -l | Show line number table and local variable table if stored in the class file |
| -s | Show internal type signatures / descriptors of fields and methods |
| -constants | Show static final constant values that can be represented in the constant pool |
| -sysinfo | Show system information about the class file being inspected |
| -classpath or --class-path | Specify where to find classes |
| --module | Specify the module containing the class to inspect |
| --module-path | Specify where to find modules |
| --multi-release | Select the entry version in a multi-release JAR to analyze |

Options can be combined. For example:

~~~bash
javap -c -p -classpath out demo.Calculator
javap -v -p -classpath out demo.Calculator
javap -c -l -p -classpath out demo.Calculator
javap -s -p -classpath out demo.Calculator
~~~

An effective way to read output is to start with -c -p, then add -v when you need the constant pool, descriptors, flags, or deeper metadata.

## 4. Practical Example: Viewing the Bytecode of a Class

Create **Calculator.java**:

~~~java
package demo;

public class Calculator {
    public static int add(int left, int right) {
        return left + right;
    }

    public static int absolute(int value) {
        if (value < 0) {
            return -value;
        }
        return value;
    }

    public static void main(String[] args) {
        int result = add(2, 3);
        System.out.println(result);
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -g -d out Calculator.java
~~~

The -g option instructs javac to store debug information such as line numbers and local variable tables. The -d out option places the class file into the output directory.

View the class structure and bytecode:

~~~bash
javap -classpath out -c -p demo.Calculator
~~~

In the output, the add method section may look like:

~~~text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
~~~

Explanation:

- iload_0: pushes the int value in local variable slot 0 onto the operand stack.
- iload_1: pushes the int in slot 1 onto the stack.
- iadd: pops two ints from the stack, adds them, and pushes the result back onto the stack.
- ireturn: returns the int value at the top of the stack from the method.

Because add is static, the two parameters reside in slot 0 and slot 1. For an instance method, slot 0 usually holds this, so the first parameter starts at slot 1. The long and double types occupy two local variable slots according to the JVM model.

The absolute section may contain the instructions:

~~~text
iload_0
ifge
iload_0
ineg
ireturn
iload_0
ireturn
~~~

The compiler may use a branch with a specific offset to jump to the part that returns the non-negative value. ifge checks the int value on the stack: if it is greater than or equal to 0, it jumps to the corresponding branch; ineg negates the integer. Offsets and instruction ordering depend on the actual bytecode generated by the compiler.

Run the program:

~~~bash
java -cp out demo.Calculator
~~~

Stdout:

~~~text
5
~~~

This is a small program that can be compiled and run standalone. The illustrative bytecode should be compared against the output from the JDK you are using, as compilers may change instruction ordering between versions or build options.

## 5. How to Read a Line of Bytecode

A disassembly line typically looks like:

~~~text
12: invokevirtual #18 // Method java/io/PrintStream.println:(I)V
~~~

Components:

- 12 is the bytecode offset within the method, measured in bytes from the start of the code array.
- invokevirtual is the opcode that invokes an instance method using virtual dispatch.
- #18 is the index referencing an entry in the constant pool.
- The comment helps humans understand which method and descriptor the entry references.

The offset is not a line number. An opcode may be longer than one byte because it has accompanying operands; therefore, the next offset can increase by more than 1.

Common opcode groups:

| Group | Examples | Meaning |
|---|---|---|
| Load and store local variables | iload, aload, istore, astore | Transfer values between local variables and the operand stack |
| Constants | iconst_0, bipush, ldc | Push a constant onto the operand stack |
| Arithmetic | iadd, isub, imul, idiv, ineg | Perform arithmetic operations |
| Comparison and branching | if_icmpge, ifeq, ifnull, goto | Control execution flow |
| Field | getfield, putfield, getstatic, putstatic | Read or write a field |
| Method invocation | invokestatic, invokevirtual, invokeinterface, invokespecial, invokedynamic | Invoke a method or call site |
| Object and array | new, anewarray, newarray, aaload, aastore | Create objects/arrays and access elements |
| Return | ireturn, areturn, return | End a method and return a result |
| Exception | athrow | Throw a throwable |

The opcode prefix often indicates the data type:

- i: int.
- l: long.
- f: float.
- d: double.
- a: reference to an object or array.

This is a useful convention for reading bytecode. Some instructions have dedicated forms for small constants or fixed local slots, such as iconst_0, iload_1, aload_0.

## 6. Operand Stack and Local Variables

Each time the JVM executes a method, the method's frame has its own local variables area and operand stack.

**Local variables** hold method parameters and local variables. Instructions such as iload, aload, istore, and astore read/write these slots.

**Operand stack** is where bytecode takes operands and places intermediate results. For example, int addition:

~~~text
iload_0
iload_1
iadd
istore_2
~~~

Sequence:

1. iload_0 pushes a onto the stack.
2. iload_1 pushes b onto the stack.
3. iadd pops two int values, adds them, and pushes the result.
4. istore_2 pops the result from the stack and stores it in slot 2.

The stack is the foundation of JVM bytecode. When reading a sequence of opcodes, track the values pushed onto and popped from the stack to understand what each instruction does.

In javap -v output, the Code attribute may contain stack=... and locals=.... stack is the maximum depth of the operand stack in the method; locals is the number of allocated local variable slots. These values are written into the class file by the compiler and used by the JVM when executing/verifying bytecode.

## 7. Reading Method and Field Descriptors

In a class file, methods and fields use descriptors to describe data types. A descriptor is the internal JVM representation, different from how types are written in Java source.

Basic symbols:

| Symbol | Java Type |
|---|---|
| B | byte |
| C | char |
| D | double |
| F | float |
| I | int |
| J | long |
| S | short |
| Z | boolean |
| V | void, used only as a return type |
| L...; | reference to a class/interface |
| [...] | array of the following type |

A method descriptor has the form:

~~~text
(parameter-types)return-type
~~~

Examples:

| Descriptor | Interpretation |
|---|---|
| (II)I | Takes two ints, returns int |
| (Ljava/lang/String;)V | Takes one String, returns void |
| ([Ljava/lang/String;)V | Takes a String array, returns void |
| ()Z | Takes no parameters, returns boolean |
| (J[D)Ljava/lang/String; | Takes a long and a double array, returns String |

For the demo.Calculator class, the descriptor of the add(int, int) method is (II)I. You can view it quickly with:

~~~bash
javap -s -p -classpath out demo.Calculator
~~~

Note: descriptors describe types after the compiler applies language rules and type erasure. Generic type arguments usually do not appear in method descriptors; generic information may be stored separately in the Signature attribute.

## 8. Reading the Constant Pool and Verbose Output

The constant pool is a table of constants and references used by the class file. It may contain:

- Class names and package names.
- Field and method names.
- Method descriptors and field descriptors.
- String literals and numeric constants.
- Method handles, method types, and dynamic call sites.
- References used by bytecode instructions.

View detailed information:

~~~bash
javap -v -p -classpath out demo.Calculator
~~~

In the output, the top section usually contains entries like:

~~~text
Constant pool:
   #1 = Methodref          #2.#3
   #2 = Class              #4
   #3 = NameAndType        #5:#6
   #4 = Utf8               java/lang/Object
~~~

Indices #1, #2... are constant pool indices. An instruction can reference an entry through this index. When reading javap -c, the comment after the opcode usually already explains the entry; if you need more details, look up the corresponding index in the Constant pool section of the -v output.

Constant pool indices are not stable identifiers across builds. Adding a method, changing source code, or using a different compiler can change the order of entries. When comparing bytecode, compare the referenced contents rather than just the # numbers.

## 9. Viewing Debug Information with -l

When compiled with debug information, javac can store:

- **LineNumberTable**: maps bytecode offsets to source lines.
- **LocalVariableTable**: local variable names, descriptors, and variable scope.
- **LocalVariableTypeTable**: generic type information for variables, if present.

Example:

~~~bash
javac -g -d out Calculator.java
javap -c -l -p -classpath out demo.Calculator
~~~

The line number section may look like:

~~~text
LineNumberTable:
  line 5: 0
  line 6: 4
~~~

The numbers illustrate mapping offsets in the method to source lines. The actual table depends on the source and compiler.

If the class file was compiled with -g:none, debug tables may not exist. In that case, javap -l cannot infer local variable names or source lines that were stripped. The absence of LocalVariableTable does not mean the bytecode has no local variable slots; it only means debug names and scopes were not stored.

## 10. Inspecting Common Java Constructs

### Loops and Conditionals

if, for, while, and switch are typically represented using comparison and jump instructions. Look for opcodes such as:

~~~text
ifeq
ifne
if_icmplt
if_icmpge
goto
tableswitch
lookupswitch
~~~

The compiler may reorder branches or optimize expressions. Therefore, do not assume each Java statement maps one-to-one to a single opcode.

### Method Calls

Common invocation instructions:

- invokestatic: calls a static method.
- invokevirtual: calls an instance method using virtual dispatch.
- invokeinterface: calls a method through an interface.
- invokespecial: used for constructors, private methods, or certain special calls according to JVM rules.
- invokedynamic: calls through a dynamic call site, commonly used for lambdas and certain language/runtime mechanisms.

### Lambdas and String Concatenation

Lambdas are typically represented via invokedynamic along with bootstrap method information. In modern JDKs, string concatenation with the + operator may also use invokedynamic and StringConcatFactory, instead of always creating a StringBuilder chain like some older compilers.

To view details, use:

~~~bash
javap -v -c -p -classpath out demo.Calculator
~~~

Look for InvokeDynamic, BootstrapMethods, and related method handles.

### Exception Handling

try, catch, and finally constructs are represented via bytecode and the exception table in the Code attribute. When viewing javap -v, look for:

~~~text
Exception table:
  from    to  target type
~~~

The columns indicate the protected bytecode range, handler location, and caught exception type. finally may be implemented by the compiler using multiple code blocks or exception handler mechanisms; do not expect a single separate bytecode block named finally.

### Constructors and Static Initializers

- Java constructors are stored under the special name <init>.
- Static initializers are stored in the special method <clinit>.
- A compiler-generated default constructor is still a method in the class file.
- Superclass constructor calls typically appear as invokespecial.

Find these methods with:

~~~bash
javap -c -p -classpath out demo.Calculator
~~~

## 11. Reading Classes in JARs, Dependencies, and Modules

### Classes Inside a JAR

Use -classpath to specify the JAR:

~~~bash
javap -classpath library.jar -c -p com.example.Library
~~~

If a class depends on multiple JARs, join them using the operating system's path separator. The separator is typically : on Linux/macOS and ; on Windows.

PowerShell example:

~~~powershell
javap -classpath "app.jar;lib/dependency.jar" -c -p com.example.Main
~~~

Linux/macOS:

~~~bash
javap -classpath "app.jar:lib/dependency.jar" -c -p com.example.Main
~~~

### Classes in JDK Modules

You can inspect a class belonging to a module using --module:

~~~bash
javap --module java.base java.lang.String
~~~

Or combine with -c and -p to inspect methods and bytecode accessible via the class file:

~~~bash
javap --module java.base -c -p java.util.ArrayList
~~~

### Multi-release JARs

A multi-release JAR can contain different implementations per Java release. Use --multi-release N to select the entry version to analyze:

~~~bash
javap --multi-release 17 -classpath library.jar -c -p com.example.Feature
~~~

The value N specifies the release version to select when looking up in a multi-release JAR. When results differ across releases, check both the Multi-Release: true manifest entry and the entries under META-INF/versions/.

## 12. Checking Class File Version with javap

javap can display the major/minor version in verbose mode:

~~~bash
javap -verbose -classpath out demo.Calculator
~~~

Look for the lines:

~~~text
minor version: 0
major version: 61
~~~

Major version 61 corresponds to Java 17. If you encounter UnsupportedClassVersionError, use javap to inspect the offending class, even if it resides inside a dependency JAR.

A verification workflow:

1. Run java -version to see which runtime is executing.
2. Identify the exact class file reported by the JVM error.
3. Use javap -verbose to read the major/minor version.
4. Compare it against the maximum version supported by the runtime.
5. Check dependencies and the build's --release configuration.

javap only reads class files. It does not prove that all other classes in the application are compatible; check dependencies and dynamically loaded classes when necessary.

## 13. Comparing Bytecode Between Two Builds

javap is useful when you want to understand why a source change or compiler option altered the bytecode.

Example:

~~~bash
javap -c -p -classpath build-old com.example.Service > old.txt
javap -c -p -classpath build-new com.example.Service > new.txt
~~~

Then compare the two files with a diff tool:

~~~bash
diff -u old.txt new.txt
~~~

On PowerShell, you can use:

~~~powershell
Compare-Object (Get-Content old.txt) (Get-Content new.txt)
~~~

When comparing, keep in mind:

- Constant pool indices can change even if the bytecode logic has not changed.
- File names, line numbers, local variables, and debug attributes may differ.
- Different JDKs may choose different opcodes or optimizations.
- Small source changes can shift offsets and branches within a method.
- Two different bytecode sequences can still have the same semantics.

To compare behavior, combine bytecode inspection with tests and logic analysis. Do not treat a text diff of javap -v as the sole proof of a regression.

## 14. Common Errors When Using javap

| Issue | Possible Cause | Resolution |
|---|---|---|
| Error: class not found | Wrong class name or classpath | Check package, output directory, and -classpath |
| javap reads the wrong class | Multiple versions of the same class on the classpath | Specify a concrete classpath or pass the .class file path |
| Private methods not shown | Default mode only displays members with default visibility | Add -p |
| Bytecode not shown | Disassemble option not used | Add -c |
| Variable names/source lines missing | Class does not store debug metadata | Recompile with -g if source is available |
| Output too long | Using -v on a large class | Start with -c -p, add -v when needed |
| Unclear what #12 means | It is a constant pool index | Use -v to look up the corresponding entry |
| Cannot read newer class | javap JDK is too old for the class file | Use javap from a JDK that supports that class version |
| Output differs across JDKs | Compiler changed bytecode generation | Compare source, flags, and JDK version together |

## 15. A Systematic Bytecode Reading Workflow

When analyzing an unfamiliar class, you can follow this order:

1. **Locate the class**: find the right .class file, JAR, or module; verify package and classpath.
2. **Inspect structure**: run javap -p to see fields, constructors, and methods.
3. **Inspect instructions**: run javap -c -p and select the method to analyze.
4. **Track the stack**: for each opcode, identify values pushed/popped and local slots accessed.
5. **Decode descriptors**: use -s or -v to understand parameters, return types, and field types.
6. **Look up the constant pool**: use -v when you need to understand method references, field references, strings, or bootstrap methods.
7. **Check debug metadata**: add -l if you need to correlate offsets with source lines.
8. **Check runtime compatibility**: inspect major/minor versions and compare with the target JVM.
9. **Compare and verify**: use diff, tests, and runtime behavior to confirm conclusions.

You do not need to start with verbose output for every class. Narrow down to one method and one specific question, such as “does this method use virtual or static dispatch?”, “which slot stores this value?”, or “which Java release was this class compiled for?”.

## 16. Key Takeaways

- javap is a disassembler for reading class files; it does not fully reconstruct the original source code.
- -c shows bytecode; -p shows private members as well; -v shows the constant pool and metadata; -l shows debug tables; -s shows descriptors.
- JVM bytecode is an intermediate instruction set using an operand stack and local variables in each method frame.
- Offsets in the output are byte positions in the code array, not source line numbers.
- A descriptor like (II)I describes two int parameters and an int return value.
- Constant pool indices are only references within one class file; they are not stable identifiers across builds.
- invokedynamic, BootstrapMethods, the exception table, and stack map frames help you understand lambdas, string concatenation, and control flow more deeply.
- javap can be used to inspect classes in directories, JARs, and JDK modules.
- When comparing bytecode, consider JDK version, compiler flags, and debug metadata; textual differences do not necessarily mean behavioral differences.

## Official References

- [javap Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html)
- [Java Virtual Machine Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html)
- [Java Virtual Machine Specification — Instruction Set](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-6.html)
- [Java Language Specification — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se26/html/jls-13.html)
