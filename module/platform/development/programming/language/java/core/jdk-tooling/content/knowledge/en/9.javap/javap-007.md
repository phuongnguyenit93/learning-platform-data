# Viewing verbose output with javap

## 1. Purpose of javap -verbose

**javap** is a tool included with the JDK for reading and displaying information from Java class files. The **-v** or **-verbose** option instructs javap to display extensive details of the class file, allowing you to inspect the structure that the JVM uses when loading and executing the class.

Basic command:

~~~bash
javap -v demo.Sample
~~~

This command tells javap to locate the demo.Sample class on the default classpath and print detailed information. In a project, you should explicitly specify the directory containing the class files:

~~~bash
javap -classpath out -v demo.Sample
~~~

Verbose output is useful when you need to:

- Check which Java version a class file was compiled for.
- View the class name, superclass, interfaces, and access flags.
- Read the constant pool and references to classes, fields, and methods.
- Inspect field and method descriptors.
- Observe the bytecode inside the Code attribute.
- View the exception table, StackMapTable, and debug attributes.
- Verify annotations, generic signatures, records, sealed classes, or module metadata.
- Investigate discrepancies between the source code and the actual packaged class file.

It is important to distinguish **javap -verbose** from **javac -verbose**. javac -verbose prints operational information during compilation, such as the compiler reading source/class files or writing class files. javap -verbose reads an existing class file and displays its internal structure. The two commands serve two different stages.

javap does not execute static initializers, constructors, or methods of the class being inspected. It reads bytecode structure and metadata from the class file; to test runtime behavior, you still need to run the program or write tests.

## 2. Creating a class file to inspect

Create a source file at src/demo/VerboseSample.java:

~~~java
package demo;

public class VerboseSample {
    public static final int MAX_RETRIES = 3;

    private final String name;

    public VerboseSample(String name) {
        this.name = name;
    }

    public int add(int left, int right) {
        int result = left + right;
        return result;
    }

    public String greeting() {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        VerboseSample sample = new VerboseSample("Java");
        System.out.println(sample.greeting());
        System.out.println("sum=" + sample.add(2, 3));
    }
}
~~~

From the project root directory, compile using JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 -g -parameters -d out src/demo/VerboseSample.java
~~~

Meaning of the options:

- **--release 17:** compiles against the API and bytecode format of Java 17.
- **-encoding UTF-8:** reads the source using UTF-8.
- **-g:** generates full debug information, including source/line and local variable information.
- **-parameters:** stores method/constructor parameter names so reflection can access them.
- **-d out:** writes class files into the out directory, following the package structure.

After compiling, the output structure includes:

~~~text
project/
├── src/
│   └── demo/
│       └── VerboseSample.java
└── out/
    └── demo/
        └── VerboseSample.class
~~~

Run the program to have a reference result:

~~~bash
java -cp out demo.VerboseSample
~~~

Stdout:

~~~text
Hello, Java
sum=5
~~~

Now inspect the class file with javap:

~~~bash
javap -classpath out -v -p demo.VerboseSample
~~~

The **-p** or **-private** option requests displaying private members as well. If -p is omitted, javap typically displays only public/protected members according to the tool's default mode. The exact verbose output may vary slightly across JDK versions, but the main information groups retain corresponding meanings.

## 3. Reading the header: class identity and version

At the top of the verbose output, javap presents the class name, minor/major version, access flags, current class name, superclass, and interfaces.

An illustrative snippet:

~~~text
Classfile .../out/demo/VerboseSample.class
  Last modified ...; size ...
  SHA-256 checksum ...
  Compiled from "VerboseSample.java"
public class demo.VerboseSample
  minor version: 0
  major version: 61
  flags: (0x0021) ACC_PUBLIC, ACC_SUPER
  this_class: ...
  super_class: ...
  interfaces: 0, fields: ..., methods: ...
~~~

This is an example illustrating the output shape; exact paths, checksums, indices, and counts depend on the actual file.

### Class file version

Two important version fields:

- **minor version:** minor version of the class file.
- **major version:** major version of the class file.

Some common major versions:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

If a class file is compiled with a JDK newer than the running runtime, an older JVM may reject loading the class with an UnsupportedClassVersionError. Therefore, the major version helps determine what runtime level the bytecode requires.

Do not look only at the JDK version installed on the build machine. What matters is the actual release/target used when creating the class file. The javac --release option locks both the API and bytecode to the target release.

### Access flags

Flags describe access properties or characteristics of a class/member. Some common flags:

- **ACC_PUBLIC:** the class or member has public access.
- **ACC_FINAL:** the class cannot be inherited from, or the member cannot be overridden/reassigned depending on the corresponding context.
- **ACC_ABSTRACT:** abstract class or method.
- **ACC_INTERFACE:** this is an interface.
- **ACC_ENUM:** this is an enum.
- **ACC_ANNOTATION:** this is an annotation type.
- **ACC_SUPER:** flag related to superclass method invocation rules in the JVM.
- **ACC_SYNTHETIC:** compiler-generated element, not appearing directly as a normal source declaration.
- **ACC_BRIDGE:** bridge method generated by the compiler to ensure correct dispatch in certain generic/covariant return situations.

Not every flag is valid for every kind of construct. You should read flags in the context of a class, field, or method.

## 4. Constant pool: the central reference table

A large portion of the verbose output is the **Constant pool**. This is the table of constants and symbolic references used by the bytecode. Bytecode instructions usually reference entries by index instead of repeating full class names, method names, or strings.

Illustrative example:

~~~text
Constant pool:
  #1 = Methodref          #2.#3
  #2 = Class              #4
  #3 = NameAndType        #5:#6
  #4 = Utf8               java/lang/Object
  #5 = Utf8               <init>
  #6 = Utf8               ()V
  ...
~~~

The indices are for illustration only. When reading real output, follow the indices to understand which class, method name, and descriptor a reference points to.

Common constant pool entry types:

| Tag | Meaning |
|---|---|
| Utf8 | String stored in the class file, used for names, descriptors, and metadata. |
| Integer, Float | 32-bit integer and floating-point constants. |
| Long, Double | 64-bit constants; occupy two index slots in the constant pool according to the class file format. |
| Class | Reference to the name of a class or interface. |
| String | Reference to a string constant. |
| Fieldref | Symbolic reference to a field of a class/interface. |
| Methodref | Symbolic reference to a method of a class. |
| InterfaceMethodref | Symbolic reference to a method of an interface. |
| NameAndType | Combines a name with a descriptor. |
| MethodHandle, MethodType | Metadata supporting method handles and method types. |
| Dynamic, InvokeDynamic | Dynamic constant and dynamic invocation, typically associated with a bootstrap method. |
| Module, Package | Module and package references in modular class files. |

For example, when you see a Methodref, you can follow its entries to find the owner class, method name, and descriptor. When you see InvokeDynamic, check BootstrapMethods as well to understand the bootstrap method linked to that dynamic call.

The constant pool is neither a list of runtime variables nor a list of all objects that will be created when the program runs. It is a symbolic/constant structure supporting bytecode linking and execution.

## 5. Descriptors: data types at the JVM level

Verbose output displays field and method descriptors. A descriptor is a type representation in the class file format, unlike Java source syntax.

Some basic type notations:

| Descriptor | Java Type |
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
| Ljava/lang/String; | java.lang.String |
| [I | int[] |
| [Ljava/lang/String; | String[] |

Example method descriptor:

~~~text
(Ljava/lang/String;II)I
~~~

It can be read as follows:

- The part inside the parentheses is the parameter list.
- Ljava/lang/String; is a String parameter.
- The next two I characters are two int parameters.
- The character after the closing parenthesis is the return type; I means int.

A Java method of the form:

~~~java
public int add(int left, int right)
~~~

will have the corresponding descriptor:

~~~text
(II)I
~~~

A constructor taking a String has the descriptor:

~~~text
(Ljava/lang/String;)V
~~~

A constructor does not return an object according to its descriptor; it has return type V (void) in the JVM's method representation.

### Descriptors and generic Signature

Generic types undergo type erasure in the descriptor used for JVM linking. For example:

~~~java
List<String> names;
~~~

The field's descriptor is:

~~~text
Ljava/util/List;
~~~

Generic information may be stored separately in the **Signature** attribute, if present. Thus, when verbose output shows a Signature containing java/util/List<java/lang/String;>, that is additional generic metadata, not a replacement runtime descriptor.

This distinction is very important when inspecting reflection, bridge methods, generic APIs, or binary compatibility.

## 6. Fields and field attributes

After the class header and constant pool, javap lists the fields. Each field may have access flags, a descriptor, and its own attributes.

Example fields:

~~~java
public static final int MAX_RETRIES = 3;
private final String name;
~~~

In verbose output you may see a structure similar to:

~~~text
public static final int MAX_RETRIES;
  descriptor: I
  flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: int 3

private final java.lang.String name;
  descriptor: Ljava/lang/String;
  flags: ACC_PRIVATE, ACC_FINAL
~~~

**ConstantValue** stores the constant value for an eligible field, typically a static final primitive or String with a compile-time constant value. It is not an attribute used for every final field.

Other field attributes you may encounter:

- **Signature:** generic signature.
- **RuntimeVisibleAnnotations:** annotations retained to be read by runtime reflection.
- **RuntimeInvisibleAnnotations:** annotations not required to be retained for runtime reflection, though still usable by compilers/tools.
- **Synthetic:** marks a field generated by the compiler or having synthetic nature.

If the source has a compile-time constant, the compiler may inline that value into the class files of call sites. When checking constant changes across modules/JARs, keep in mind that replacing only the class declaring the constant may not cause already-compiled clients to pick up the new value; clients may need to be recompiled.

## 7. Methods and the Code attribute

Each method has a name, descriptor, access flags, and related attributes. A method with a body typically contains a **Code** attribute.

Example source:

~~~java
public int add(int left, int right) {
    int result = left + right;
    return result;
}
~~~

Verbose output may contain something similar to:

~~~text
public int add(int, int);
  descriptor: (II)I
  flags: ACC_PUBLIC
  Code:
    stack=2, locals=4, args_size=3
       0: iload_1
       1: iload_2
       2: iadd
       3: istore_3
       4: iload_3
       5: ireturn
~~~

The offsets and instructions illustrate a simple method. Local variable names and exact layout can vary depending on compiler/debug options.

Fields inside Code:

- **stack:** maximum number of slots needed on the method's operand stack.
- **locals:** number of local variable slots needed in the frame.
- **args_size:** number of parameter slots as displayed by javap; for an instance method, slot 0 is this.
- **code_length:** number of bytecode bytes in the method.
- **Exception table:** bytecode ranges that have exception handlers.
- **Nested attributes:** additional metadata such as LineNumberTable, LocalVariableTable, and StackMapTable.

Bytecode operates on the operand stack. For example, iload_1 loads a local variable onto the stack, iadd pops two int values and pushes the result, istore_3 stores the result into a local slot, and ireturn returns an int value.

This is JVM-level bytecode, not CPU assembly code. The JVM may interpret the bytecode or compile it into machine code using JIT depending on the runtime.

## 8. Exception table and StackMapTable

Inside the Code attribute, verbose output may present an exception table:

~~~text
Exception table:
  from    to  target type
     0     8    12   Class java/lang/Exception
~~~

The columns describe the protected bytecode range, the handler location, and the type of exception caught. The bytecode range and offsets in the table have meaning in the JVM format; do not interpret them as source line numbers.

**StackMapTable** contains stack map frames for bytecode verification. The JVM uses this information during verification to check the types of the operand stack and local variables at key control-flow points.

When reading StackMapTable:

- A frame represents the type state of the stack/locals at a bytecode offset.
- Verification types can be integer, float, long, double, null, uninitializedThis, object, or uninitialized object.
- An object type references the corresponding class in the constant pool.
- Frames help the verifier check whether control-flow branches and stack states are consistent.

StackMapTable is not a runtime log and does not indicate that a branch actually executed. It is static metadata for bytecode verification.

If bytecode is hand-crafted or transformed by a bytecode tool, an invalid StackMapTable can cause the JVM to reject loading the class with a VerifyError. In that case, you need to inspect the bytecode and frame metadata, not just the source code.

## 9. Debug attributes: line numbers and local variables

Debug information helps link bytecode back to source code. Depending on how it was compiled, verbose output may contain:

- **SourceFile:** name of the associated source file.
- **LineNumberTable:** maps bytecode offsets to source line numbers.
- **LocalVariableTable:** local variable names, descriptors, slot indices, and scope ranges.
- **LocalVariableTypeTable:** generic signatures of local variables when present.
- **MethodParameters:** parameter names and related flags if saved by the compiler via -parameters.

You can compile with different options:

~~~bash
javac --release 17 -g -parameters -d out src/demo/VerboseSample.java
~~~

To omit all debug information:

~~~bash
javac --release 17 -g:none -d out src/demo/VerboseSample.java
~~~

To select specific debug information groups:

~~~bash
javac --release 17 -g:source,lines -d out src/demo/VerboseSample.java
~~~

By default, javac usually retains source file and line number information, but does not necessarily store local variable names. The -g option enables full debug information; -parameters saves formal parameter names for reflection.

The absence of LocalVariableTable does not mean local variables do not exist in bytecode. The compiler still allocates the necessary slots in the frame; only the debug names and scopes may not be stored.

## 10. Annotations, generics, and extended attributes

Verbose output also reveals many attribute types describing advanced Java constructs.

| Attribute | Role |
|---|---|
| Signature | Generic signature of a class, field, or method. |
| Exceptions | List of checked exceptions declared in throws. |
| RuntimeVisibleAnnotations | Annotations retained to be read at runtime. |
| RuntimeInvisibleAnnotations | Annotations without runtime retention that are still stored in the class file. |
| RuntimeVisibleParameterAnnotations | Parameter annotations readable at runtime. |
| AnnotationDefault | Default value of an element in an annotation type. |
| MethodParameters | Names and modifier metadata of method/constructor parameters. |
| InnerClasses | Information about nested/inner classes. |
| EnclosingMethod | The method or constructor enclosing a local/anonymous class. |
| NestHost / NestMembers | Metadata about nestmate access among related classes. |
| Record | Metadata of a record class. |
| PermittedSubclasses | List of permitted subclasses of a sealed class/interface. |
| Module | Module descriptor metadata in modular class files. |
| BootstrapMethods | Bootstrap methods used by invokedynamic or dynamic constants. |

Attributes do not appear in every class. For example, Record only exists on record classes; PermittedSubclasses only applies to sealed types; Module appears in module descriptors.

With lambdas or string concatenation, you may see **InvokeDynamic** in the constant pool and **BootstrapMethods** in the class attributes. javac can use invokedynamic to link behavior at runtime via a bootstrap method. Do not expect every lambda expression or string concatenation to be represented as a direct method call identical to the source.

## 11. javap options commonly used with verbose

Verbose output is very detailed. You can combine other options to focus on the specific information you need to inspect.

| Option | Purpose |
|---|---|
| -v or -verbose | Displays detailed class file information. |
| -p or -private | Displays all class members, including private ones. |
| -c | Disassembles method bytecode. |
| -l | Prints line number and local variable tables. |
| -s | Prints internal type signatures/descriptors. |
| -constants | Displays values of eligible static final constants. |
| -sysinfo | Displays system information of the class file such as path, size, timestamp, and checksum. |
| -classpath or --class-path | Specifies where to look for classes. |
| -module-path | Specifies the module path when looking up classes in modules. |
| -version | Displays the javap version. |

Examples:

~~~bash
javap -classpath out -p -c demo.VerboseSample
~~~

Focuses only on member declarations and bytecode.

~~~bash
javap -classpath out -p -l demo.VerboseSample
~~~

Inspects line number and local variable tables.

~~~bash
javap -classpath out -p -s demo.VerboseSample
~~~

Inspects field and method descriptors.

~~~bash
javap -classpath out -p -constants demo.VerboseSample
~~~

Checks constant field values.

~~~bash
javap -classpath out -v -p demo.VerboseSample > verbose-output.txt
~~~

Saves the entire verbose output for searching or comparison.

On PowerShell you can also redirect:

~~~powershell
javap -classpath out -v -p demo.VerboseSample *> verbose-output.txt
~~~

Choose options according to the question you need to answer. When investigating a class file, you typically start with -v -p, then use -c, -l, or -s to read the relevant parts in depth.

## 12. Reading classes from JARs and the module path

javap can read classes not only from an output directory but also from JARs or modules.

If a JAR is in the lib directory:

~~~bash
javap -classpath lib/example.jar -v -p com.example.Service
~~~

If you need to inspect a class belonging to a module on the module path:

~~~bash
javap --module-path mods --module com.example.app/com.example.app.Main -v
~~~

The module syntax has the form module-name/class-name. For JDK modules, you can inspect a class in a specific module:

~~~bash
javap --module java.base -p -s java.lang.String
~~~

Specify the classpath or module path explicitly to avoid javap accidentally reading a class with the same name from another location. When multiple versions of the same library exist, inspect the exact JAR actually used by the application.

For classes in a multi-release JAR, entry selection can depend on the JDK version and how javap is invoked. When you need to inspect an exact version-specific entry, check the JAR structure and the options supported by javap on the JDK in use; do not assume every tool always selects the same entry.

## 13. Investigation workflow using verbose output

A practical workflow:

1. **Identify the artifact:** locate the exact class file/JAR that the application is running, not just a file from the latest build directory.
2. **Verify the toolchain:** note the JDK/javap version and how the artifact was built.
3. **Print the overall structure:** use javap -v -p to view class version, flags, fields, methods, and attributes.
4. **Read the constant pool and descriptors:** identify symbolic references, owners, method names, and parameter/return types.
5. **Read Code:** use -c or the Code section in verbose output to trace bytecode and control flow.
6. **Read debug/verification metadata:** check LineNumberTable, LocalVariableTable, and StackMapTable when investigating related errors.
7. **Compare artifacts:** if you have two versions of a class, save their outputs separately and diff them to find changes.
8. **Cross-check with runtime:** verify the classpath/module path and the actual loaded class if the output does not match application behavior.

To compare two artifacts:

~~~bash
javap -classpath old.jar -v -p com.example.Service > old.txt
javap -classpath new.jar -v -p com.example.Service > new.txt
~~~

Then use an OS or IDE diff tool. Keep in mind that the output may contain paths, timestamps, checksums, and constant pool indices that change across builds; not every differing line means the API or behavior has changed.

When comparing binary compatibility, focus on class/member access, descriptors, superclass/interfaces, generic signatures, checked exceptions, annotations, and attributes that affect linking. A simple text diff is only a clue; you need to evaluate against the contract and runtime.

## 14. Common issues when reading verbose output

| Symptom | Possible cause | Resolution |
|---|---|---|
| javap cannot find the class | Wrong classpath or class name missing package. | Explicitly specify -classpath and the full binary name. |
| Inspecting the wrong/old class | Multiple JARs/directories contain the same class name. | Verify the artifact source and use a minimal, explicit classpath. |
| Private fields/methods not shown | -p was not used. | Add -p or -private. |
| Local variable names not shown | Compiled without local-variable debug info. | Recompile with -g or -g:vars. |
| Reflection parameter names not shown | Not compiled with -parameters. | Enable -parameters and recompile. |
| Only hard-to-read descriptors shown | Descriptors use JVM notation instead of Java syntax. | Refer to the descriptor table or use javap -s. |
| Cannot understand InvokeDynamic | Haven't read BootstrapMethods or related constant pool entries. | Trace the bootstrap method and dynamic entry. |
| JVM rejects class version | Artifact is newer than the runtime. | Check major version and target release. |
| javap reports a class file error | File is not a valid class, is corrupted, or is too new for the javap in use. | Verify the artifact and use a sufficiently new JDK to read it. |
| Output is too long | Verbose prints all metadata and the constant pool. | Redirect to a file, search by method/attribute name, or use -c/-l/-s as appropriate. |

Do not edit bytecode directly just because a line in verbose output looks unusual. Identify the compiler, source, processor, toolchain, and input artifact before making changes.

## 15. Checklist when viewing javap verbose output

- [ ] Identified the exact class file or JAR to inspect.
- [ ] Explicitly specified the classpath/module path to avoid reading the wrong class.
- [ ] Recorded the javap/JDK version.
- [ ] Checked the major/minor version and access flags.
- [ ] Understood how to follow indices in the constant pool.
- [ ] Read field/method descriptors and distinguished them from generic Signatures.
- [ ] Checked Code, bytecode, exception table, and StackMapTable when needed.
- [ ] Checked debug attributes and understood the effect of -g/-parameters.
- [ ] Inspected annotation, record, sealed, or module attributes if used by the class.
- [ ] Distinguished javap -verbose from javac -verbose.
- [ ] Cross-checked the class file with runtime/build configuration before drawing conclusions.
- [ ] Controlled verbose logs to avoid exposing sensitive information in the constant pool or internal paths.

javap -verbose provides a deep look into the class file structure used by the JVM. By reading in order—class version, flags, constant pool, descriptors, fields, methods, and attributes—you can explain the generated bytecode, identify missing metadata, and investigate differences between source code and the actual artifact.