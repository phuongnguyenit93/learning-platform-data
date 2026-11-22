# Viewing the Constant Pool with javap

The **constant pool** is a table of constants and references stored inside a Java class file. This table holds information that the JVM needs to describe a class and link its components, such as class names, field names, method names, descriptors, string literals, numeric values, method handles, and dynamic invocation references.

The `javap` tool included with the JDK can decode a class file into human-readable text. To view the constant pool, the most important option is `-verbose` (abbreviated `-v`). This is a practical way to inspect constant pool entries and trace relationships between indices without having to read raw binary data.

## 1. Where Is the Constant Pool Located in a Class File?

A class file has the following overall structure:

```text
ClassFile
├── magic
├── minor_version / major_version
├── constant_pool
├── access_flags
├── this_class / super_class
├── interfaces
├── fields
├── methods
└── attributes
```

The constant pool comes after the class file version section and before the class description metadata. Other sections of the class file typically reference the constant pool by index instead of repeating names and descriptors.

For example, the `this_class` field does not directly store the string `com/example/Message`; instead, it stores an index pointing to a `CONSTANT_Class_info` entry. That Class entry in turn points to a UTF-8 entry containing the internal name of the class.

Therefore, when reading the constant pool, keep two things in mind:

- An entry may hold data directly, such as an integer or a UTF-8 string.
- Another entry may hold indices pointing to other entries within the same constant pool.

The constant pool is not just a simple list of literals appearing in source code. It also contains reference structures required for linking and execution.

## 2. javap Commands to View the Constant Pool

Suppose the class file is located in the `out` directory and its fully qualified class name is `com.example.Message`. Run:

```sh
javap -verbose -classpath out com.example.Message
```

You can use the shorter form:

```sh
javap -v -cp out com.example.Message
```

Explanation:

- `javap`: the class file disassembler/analyzer tool.
- `-verbose` or `-v`: displays detailed information, including the constant pool and attributes.
- `-classpath out` or `-cp out`: specifies the root directory where classes are located.
- `com.example.Message`: the fully qualified class name, using dots between packages.

To also view private members and class file details:

```sh
javap -v -p -classpath out com.example.Message
```

If the class file is inside a JAR:

```sh
javap -v -classpath app.jar com.example.Message
```

To save the output to a text file:

```sh
javap -v -p -classpath out com.example.Message > constant-pool.txt
```

The output file is a decoded representation produced by `javap`, not a byte-for-byte copy of the class file. Indices and formatting may change when the source code, compiler, or JDK version changes.

## 3. Example: Creating a Class File to Inspect

Create the following directory structure:

```text
project/
└── src/
    └── com/
        └── example/
            └── ConstantPoolDemo.java
```

Contents of `ConstantPoolDemo.java`:

```java
package com.example;

public class ConstantPoolDemo {
    private static final int MAX_RETRIES = 3;
    private static final String LABEL = "jdk-tooling";

    private final String name;

    public ConstantPoolDemo(String name) {
        this.name = name;
    }

    public String message(int count) {
        return LABEL + ":" + name + ":" + count;
    }

    public static void main(String[] args) {
        ConstantPoolDemo demo = new ConstantPoolDemo("Java");
        System.out.println(demo.message(MAX_RETRIES));
    }
}
```

Compile into the `out` directory:

```sh
mkdir -p out
javac -d out src/com/example/ConstantPoolDemo.java
```

On Windows PowerShell, you can create the directory with:

```powershell
New-Item -ItemType Directory -Force out
javac -d out src/com/example/ConstantPoolDemo.java
```

Run the program:

```sh
java -cp out com.example.ConstantPoolDemo
```

Output:

```text
jdk-tooling:Java:3
```

View the constant pool:

```sh
javap -v -p -classpath out com.example.ConstantPoolDemo
```

In the output, locate the section starting with:

```text
Constant pool:
```

Entries are numbered like `#1`, `#2`, `#3`... The actual indices may differ between compilations or compiler versions. Use them to understand how entries reference each other, rather than memorizing fixed index numbers.

## 4. How to Read a Constant Pool Entry

A line in the constant pool section has the general form:

```text
#<index> = <tag> <data>
```

Illustrative example:

```text
#1 = Methodref          #2.#3
#2 = Class              #4
#3 = NameAndType        #5:#6
#4 = Utf8               java/lang/Object
#5 = Utf8               <init>
#6 = Utf8               ()V
```

How to trace it:

1. `#1` is a Methodref entry, representing a reference to a method.
2. Methodref references `#2` to identify the owning class and `#3` to identify the name and descriptor.
3. `#2` is a Class entry, referencing `#4`.
4. `#4` is a UTF-8 entry containing the internal name `java/lang/Object`.
5. `#3` is a NameAndType entry, combining `#5` and `#6`.
6. `#5` is the method name `<init>`; `#6` is the descriptor `()V`.

Thus, entry `#1` describes a call to the constructor `java.lang.Object()`. This is an illustrative example of how references work; the exact order and indices in a real class file depend on the source code and compiler.

In `javap -v` output, the comments after `//` help humans quickly read those relationships. However, when analyzing the structure, you should understand the indices before the comment, as those are the actual references stored in the class file.

## 5. Common Entry Types

Each constant pool entry begins with a tag identifying its data type. Common types include:

| Tag | Entry Name | Meaning |
|---:|---|---|
| 1 | `Utf8` | Modified UTF-8 string, used for names and descriptors |
| 3 | `Integer` | 32-bit integer constant |
| 4 | `Float` | 32-bit floating-point constant |
| 5 | `Long` | 64-bit integer constant |
| 6 | `Double` | 64-bit floating-point constant |
| 7 | `Class` | Reference to a class or interface name |
| 8 | `String` | Reference to a string literal |
| 9 | `Fieldref` | Reference to a class field |
| 10 | `Methodref` | Reference to a class method |
| 11 | `InterfaceMethodref` | Reference to an interface method |
| 12 | `NameAndType` | Pair of name and descriptor |
| 15 | `MethodHandle` | Reference to a field or method with a handle kind |
| 16 | `MethodType` | Descriptor of a method type |
| 17 | `Dynamic` | Constant computed via a bootstrap method |
| 18 | `InvokeDynamic` | Call site linked via a bootstrap method |
| 19 | `Module` | Module name |
| 20 | `Package` | Package name |

New tags are added across class file versions. An older JDK may not recognize a tag used by a newer class file.

### 5.1. Utf8

`Utf8` entries store strings used by other parts of the class file, for example:

- Class name: `com/example/ConstantPoolDemo`.
- Method name: `message`.
- Field name: `name`.
- Descriptor: `(I)Ljava/lang/String;`.
- Attribute names: `Code`, `LineNumberTable`, `SourceFile`.
- String literal: `jdk-tooling`.

The string format in the constant pool is **Modified UTF-8**, which is not identical to standard UTF-8. When writing a tool to parse class files, do not decode these bytes assuming standard UTF-8.

### 5.2. Integer, Float, Long, and Double

These entries represent numeric constants. For example, the literal `3` may be stored as an Integer; floating-point literals may appear as Float or Double depending on their type.

`Long` and `Double` occupy two slots in the constant pool. The second slot is reserved and cannot be referenced as an independent entry. Therefore, when tracing indices, you may see a gap after a Long or Double entry.

### 5.3. Class

A Class entry references a Utf8 entry containing the internal name of a class or interface. For example:

```text
java/lang/String
com/example/ConstantPoolDemo
[I
[Ljava/lang/String;
```

Regular class names use slashes `/` to separate packages. Array types use a special descriptor form, such as `[I` for an `int` array and `[Ljava/lang/String;` for a `String` array.

### 5.4. String

A String entry references a Utf8 entry containing the literal content. For example, the literal:

```java
String label = "jdk-tooling";
```

may produce a `String` entry referencing the string `jdk-tooling`.

Do not confuse the `CONSTANT_String` entry in the class file with the JVM's entire String Pool mechanism. The constant pool is a structure in the class file; when the JVM loads and processes literals, it applies runtime rules for String objects and interning. `String.intern()` is a runtime API related to canonical strings, not a command to inspect the constant pool.

## 6. Fieldref, Methodref, and InterfaceMethodref

These three reference types are essential when you want to understand which members a class calls or accesses.

### 6.1. Fieldref

`Fieldref` represents a reference to a field. It links:

- The class or interface that owns the field.
- The field name.
- The field descriptor.

Source code example:

```java
class Counter {
    int value;

    int read() {
        return value;
    }
}
```

In the class file, accessing the field may use a Fieldref entry identifying `Counter.value` with an `int` descriptor (`I`). The corresponding bytecode typically includes instructions such as `getfield` or `putfield`, depending on the operation.

### 6.2. Methodref

`Methodref` represents a reference to a method declared in a class. This entry references a Class and a NameAndType.

For example, the call:

```java
System.out.println("Hello");
```

needs to reference the `java/io/PrintStream` class, the `println` method, and the descriptor matching the argument type. In the constant pool, these components may be represented via Methodref, Class, NameAndType, and Utf8.

### 6.3. InterfaceMethodref

`InterfaceMethodref` is used to reference a method declared in an interface. For example, invoking a method through a variable of an interface type can use this reference entry.

When reading `javap -v`, trace Class and NameAndType to answer three questions:

1. Which class or interface owns the member?
2. What is the member's name?
3. What are the parameter types and return type?

This is a useful way to analyze dependencies at the bytecode level.

## 7. NameAndType and Descriptors

A `NameAndType` entry combines a member name with a descriptor. A descriptor describes a field type or method signature in JVM format.

Descriptor examples:

| Java declaration | Descriptor |
|---|---|
| `int count` | `I` |
| `String name` | `Ljava/lang/String;` |
| `int[] values` | `[I` |
| `void reset()` | `()V` |
| `int add(int a, int b)` | `(II)I` |
| `String format(int code)` | `(I)Ljava/lang/String;` |
| `void save(String path, boolean force)` | `(Ljava/lang/String;Z)V` |

Primitive types have dedicated symbols:

| Java Type | Descriptor |
|---|---|
| boolean | `Z` |
| byte | `B` |
| char | `C` |
| short | `S` |
| int | `I` |
| long | `J` |
| float | `F` |
| double | `D` |
| void | `V` |

For methods, parameter types appear inside parentheses; the return type follows the closing parenthesis. For example, `(II)I` takes two `int` parameters and returns an `int`.

Descriptors do not preserve full generic types after type erasure. For example, both `List<String>` and `List<Integer>` use the raw descriptor `Ljava/util/List;`. Generic type information may be stored separately in the `Signature` attribute.

## 8. MethodHandle, MethodType, and InvokeDynamic

These entries commonly appear when source code uses lambdas, method references, or dynamic invocation mechanisms.

### 8.1. MethodHandle

`MethodHandle` describes a handle to a field or method. It has a reference kind that specifies how it is accessed, such as getting a field, setting a field, or invoking a method according to the corresponding rules.

Method handles are the foundation for many APIs in `java.lang.invoke`, including `MethodHandles` and `MethodHandle`.

### 8.2. MethodType

`MethodType` describes the parameter types and return type of a method. It is commonly used alongside method handles and dynamic linking mechanisms.

### 8.3. InvokeDynamic

`InvokeDynamic` represents a call site linked through a bootstrap method. This mechanism allows the JVM or runtime to link an invocation flexibly.

Common cases that generate related entries include:

- Lambda expressions.
- Method references.
- String concatenation in modern Java versions.
- Frameworks or libraries that use the `invokedynamic` mechanism.

In `javap -v`, you can see `InvokeDynamic` entries in the constant pool and the `BootstrapMethods` attribute in the class's attributes section. An InvokeDynamic entry points to a NameAndType and a bootstrap method entry; the BootstrapMethods attribute provides information about the bootstrap method and its associated arguments.

Example:

```java
import java.util.function.IntUnaryOperator;

public class DynamicDemo {
    public static void main(String[] args) {
        IntUnaryOperator twice = value -> value * 2;
        System.out.println(twice.applyAsInt(4));
    }
}
```

Compile and inspect:

```sh
javac -d out DynamicDemo.java
javap -v -p -classpath out DynamicDemo
```

Program output:

```text
8
```

With modern compilers, lambdas are typically represented via `invokedynamic` and a bootstrap method related to the lambda metafactory mechanism. Exact indices and bytecode details may vary across JDK versions; the key is recognizing the relationship between InvokeDynamic, NameAndType, and BootstrapMethods.

## 9. Dynamic Constants, Module, and Package

### 9.1. Dynamic Constant

`CONSTANT_Dynamic` (tag 17) represents a constant computed via a bootstrap method when the runtime resolves that constant. It differs from numeric or string literals stored directly.

Dynamic constants allow the runtime to compute and cache values according to class file rules. They can be used by compilers or bytecode generation tools; not all ordinary Java source code produces this entry.

### 9.2. Module and Package

`CONSTANT_Module` and `CONSTANT_Package` appear in class files containing module metadata, especially `module-info.class`. They reference module or package names within the module structure.

You can inspect a module descriptor with:

```sh
javap -v module-info.class
```

Or use the appropriate module syntax when analyzing an installed module. These entries serve the Java Platform Module System (JPMS), rather than ordinary package/class references in typical application classes.

## 10. Tracing the Constant Pool from Bytecode

The constant pool is tightly coupled with bytecode instructions. Several instructions use a constant pool index to locate the target element to operate on:

| Bytecode instruction | Typical reference |
|---|---|
| `ldc`, `ldc_w`, `ldc2_w` | Literal or dynamic constant |
| `getfield`, `putfield` | Fieldref |
| `getstatic`, `putstatic` | Fieldref |
| `invokevirtual` | Methodref |
| `invokespecial` | Methodref or reference type specified for the instruction |
| `invokestatic` | Methodref or InterfaceMethodref depending on version/definition |
| `invokeinterface` | InterfaceMethodref |
| `invokedynamic` | InvokeDynamic |

Use both `-v` and `-c` to view the constant pool alongside bytecode:

```sh
javap -v -c -p -classpath out com.example.ConstantPoolDemo
```

When you see an instruction like `getfield #...`, look up the corresponding index in the Constant pool section to see the class, field name, and descriptor. When you see `invokevirtual #...`, trace the Methodref to identify the method being called.

This is an essential technique when investigating:

- Which API version a library is referencing.
- Why `NoSuchMethodError` or `NoSuchFieldError` occurs.
- Whether bytecode invokes a class method or an interface method.
- Which JVM instructions the compiler generated for a source code operation.

## 11. Distinguishing the Constant Pool from Similar Concepts

| Concept | Scope | Role |
|---|---|---|
| Class-file constant pool | Per class file | Stores constants, names, and symbolic references of the class |
| Runtime constant pool | Per class/interface when represented by the JVM at runtime | JVM's runtime representation of the constant pool |
| String Pool | Runtime canonical String management mechanism | Manages interned strings |
| Java constant variable | `final` variable of primitive/String type initialized with a constant expression | May be inlined by the compiler at call sites |
| `ConstantValue` attribute | Field attribute in a class file | Records the initial value for certain static constant fields |

A `static final` variable does not automatically become a Fieldref entry in the constant pool. For constant variables of primitive or String types, the compiler may replace usage sites with the literal value directly. The field may still have a `ConstantValue` attribute in the class file.

Similarly, seeing a `String` entry in the constant pool does not mean the entire runtime String Pool is stored in the class file. The class file holds literals and references; creating and resolving String objects happens according to JVM rules.

## 12. Useful javap Options for Analysis

| Option | Effect |
|---|---|
| `-v`, `-verbose` | Prints detailed information, including the constant pool and attributes |
| `-p`, `-private` | Shows private members as well |
| `-c` | Disassembles method bytecode |
| `-s` | Prints internal type signatures |
| `-constants` | Shows `static final` constant values when available |
| `-classpath`, `-cp`, `--class-path` | Specifies where to find classes |
| `-sysinfo` | Displays system information of the class file, such as path, size, and checksum |

Note: `-constants` only displays eligible constant field values; it does not replace `-verbose` when you need to inspect the full constant pool. To inspect symbolic references, descriptors, InvokeDynamic, and BootstrapMethods, use `-v`.

## 13. A Systematic Workflow for Reading the Constant Pool

When analyzing an unfamiliar class file, you can follow these steps:

1. Identify the exact class file and classpath/module path.
2. Run `javap -v -p` to inspect all information.
3. Read the major/minor version first to determine the compiler target.
4. Locate the class name, superclass, and interfaces.
5. In the Constant pool, categorize entries into Utf8, Class, String, numeric, Fieldref, Methodref, and NameAndType.
6. Trace indices to find the owner, member name, and descriptor.
7. Cross-reference entries with bytecode using `javap -c`.
8. Check BootstrapMethods if InvokeDynamic or Dynamic entries are present.
9. Inspect attributes such as Signature, ConstantValue, RuntimeVisibleAnnotations, and Code when needed.
10. Note the compiler/JDK version and release configuration when comparing results across builds.

Do not try to understand the entire constant pool from top to bottom all at once. Start from a specific bytecode instruction or member, then trace the indices it uses. This helps you find the relevant information much faster.

## 14. Common Errors When Viewing the Constant Pool

| Symptom | Common Cause | How to Fix |
|---|---|---|
| `Error: class not found` | Incorrect fully qualified class name or classpath does not point to the output root | Use `javap -v -cp out com.example.ClassName` and verify the package location |
| `javap` reports an invalid class file | The file is not a class file, is corrupted, or is truncated | Rebuild the artifact; confirm the path does not point to the wrong file |
| Constant pool section is missing | `-v`/`-verbose` was not used, or viewing condensed output | Run `javap -verbose` |
| Only public members are shown | Private member display is not enabled | Add `-p` |
| A local variable name is missing | Variable names were not stored because debug metadata was not generated | Compile with `-g`; note that local names do not necessarily live in the constant pool |
| Expected generic type names are missing | Descriptors use post-type-erasure types | Check the `Signature` attribute instead of reading only the descriptor |
| Constant pool indices differ from examples | Source code or compiler produced a different entry order | Trace indices within the actual class file you are inspecting, rather than relying on sample numbers |
| No Fieldref found for a `static final` variable | Compiler may have inlined the constant variable | Check `ConstantValue` and the bytecode at usage sites |
| Unclear InvokeDynamic entry | Haven't checked BootstrapMethods or the corresponding NameAndType | Use `javap -v -c` and trace the references |
| Older JDK's `javap` cannot read a newer class file | Tool does not support the newer major version or tags | Use `javap` from a JDK compatible with the class file |

## 15. Checklist

- [ ] Identified the correct class file and output root.
- [ ] Used `javap -v` or `javap -verbose` to display the constant pool.
- [ ] Used `-p` if private members also need to be inspected.
- [ ] Understood that constant pool indices start at 1; index 0 is unused.
- [ ] Knew that Long and Double occupy two slots.
- [ ] Distinguished Utf8, Class, String, NameAndType, Fieldref, and Methodref.
- [ ] Read descriptors to determine field types, parameters, and return values.
- [ ] Distinguished the class-file constant pool from the runtime String Pool.
- [ ] Used `-c` to correlate constant pool entries with bytecode instructions.
- [ ] Checked BootstrapMethods when InvokeDynamic or Dynamic entries are present.
- [ ] Avoided relying on fixed indices from an example or a single compilation.

The constant pool is the map of names, types, and symbolic references that the JVM uses to understand the contents of a class. Once you know how to inspect it with `javap -v` and trace its indices, you can accurately determine which classes, fields, methods, and APIs a class file references, as well as how source code, bytecode, and JVM linking relate to one another.