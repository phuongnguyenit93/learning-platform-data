# Using javap to Inspect Declarations, Descriptors, and Bytecode in Java

After `javac` compiles a `.java` file into `.class`, **source code has been transformed into class-file structures**: class name, superclass/interfaces, fields, methods, binary types, modifiers, constant pool, attributes, and bytecode instructions. The **`javap`** tool in the JDK lets you read this information without manually decoding every byte of the class file.

This lesson belongs to the **Compilation Output Validation** group of Java Advance – compilation. The goal is not “decompiling bytecode back into the exact original Java code”, but **verifying what the compiler actually generated**: whether the class has the expected members and access levels, how return/parameter types appear in **descriptors**, whether generics are preserved in **Signature** or erased, which instructions bytecode uses, and when bridge methods or `invokedynamic` appear.

The examples are based on Java 17, using `javac --release 17` and the JDK's `javap`. Illustrative outputs were verified with JDK 24.0.2 compiling for target 17. Constant pool indices, instruction offsets, or certain bytecode details can change when switching compilers/JDKs/options; distinguish **stable structure and meaning** from **specific compiler implementation choices**.

## 1. What Is javap and When Is It Used?

`javap` is the **class-file disassembler/inspector** bundled with the JDK; it reads `.class` files and does not directly compile source. It can:

- List class/interface, field, constructor, and method declarations.
- Show private members with `-p`.
- Show JVM **descriptors** with `-s`.
- Disassemble **instructions** of methods having a `Code` attribute with `-c`.
- Show class-file metadata, constant pool, access flags, attributes, and bootstrap information with `-v`.
- Show line number/local variable tables when matching debug info exists, using `-l` combined with `-c` or `-v`.
- Show compile-time constant values with `-constants`.
- Show class-file checksum/path with `-sysinfo`.

A few practical scenarios:

| Question | How to Use javap |
|---|---|
| Does the artifact have the method I thought was compiled? | `javap -p` |
| What signature does the binary API have? | `javap -p -s` |
| How did the compiler generate operators, calls, and returns? | `javap -c` |
| Is there a bridge method due to generics/overrides? | `javap -p -v` |
| Which Java target does the class belong to? | `javap -v` to read major/minor version |
| Is there a generic Signature even though descriptor is erased? | `javap -v`, compare `descriptor` and `Signature` |
| Does bytecode contain `invokedynamic`? | `javap -c` then `-v` to inspect `BootstrapMethods` |
| Which source line/local variable maps to which opcode? | Compile with `-g` then `javap -c -l` |

**Limitation:** `javap` does not prove a program has no runtime errors, does not replace unit tests, and does not recover exact comments, formatting, syntactic style, or business intent of the original source.

## 2. Basic Syntax and Locating the Right Class to Inspect

Typical commands:

~~~sh
javap -classpath out lesson.bytecode.BytecodeSample
javap -classpath out -p -s lesson.bytecode.BytecodeSample
javap -classpath out -c lesson.bytecode.BytecodeSample
javap -classpath out -v lesson.bytecode.BytecodeSample
~~~

With binary name `lesson.bytecode.BytecodeSample`, the classpath must contain **the root of the package tree**: if bytecode resides at `out/lesson/bytecode/BytecodeSample.class`, set classpath to **`out`**, not `out/lesson/bytecode`.

You can pass the class file path directly:

~~~sh
javap -p -s out/lesson/bytecode/BytecodeSample.class
~~~

You can also read a class from a JAR on the classpath:

~~~sh
javap -classpath artifacts/example.jar -p -s lesson.bytecode.BytecodeSample
~~~

The JAR command above is a syntax example: replace `artifacts/example.jar` with an actual JAR containing that class. `javap` **does not automatically find every JAR in a project**, nor automatically fetch dependencies from Maven Central or the Gradle cache just from knowing a class name.

### 2.1. Checking the JDK and Avoiding Reading Stale Classes

Before inspecting, run:

~~~sh
javac -version
java -version
javap -version
~~~

Then verify where bytecode is emitted: `javac -d out` creates an output tree by package. If a project has multiple `target/classes`, `build/classes`, JARs, or modules, specify paths explicitly rather than relying on the current directory or environment variables.

`javap` can successfully read **a version of a class other than the artifact you meant to verify**. When seeing output different from source, first locate which binary/path/JAR was actually picked up before suspecting the compiler.

### 2.2. How Does It Differ from javac and java?

- **javac**: validates/compiles source into class files.
- **javap**: inspects the structure of existing class files.
- **java**: launches and executes programs on the JVM.

You cannot use `javap -c SomeSource.java` as a primary way to disassemble uncompiled source code. Compile the class first or point to an existing class file.

## 3. Java 17 Sample Project with Fields, Methods, Generics, and Calls

Create the structure:

~~~text
project/
├── src/
│   └── lesson/bytecode/
│       ├── BytecodeSample.java
│       ├── Provider.java
│       └── StringProvider.java
└── out/             # created when compiling
~~~

Open a terminal in the `project` directory and save the three files with exact names. Files containing public types must match the public class/interface name.

### 3.1. BytecodeSample.java

~~~java
package lesson.bytecode;

import java.util.List;

public final class BytecodeSample {
    public static final int LIMIT = 10;
    private final String name;

    public BytecodeSample(String name) {
        this.name = name;
    }

    public int sum(int left, int right) {
        return left + right;
    }

    public String greeting(String guest) {
        return name + ":" + guest;
    }

    public List<String> names() {
        return List.of(name);
    }

    public static void main(String[] args) {
        BytecodeSample sample = new BytecodeSample("Lan");
        System.out.println(sample.sum(2, 3));
        System.out.println(sample.greeting("Mai"));
    }
}
~~~

This class has:

- `public static final` constant `LIMIT`.
- `private final String name` to observe `-p`.
- Constructor accepting String.
- Method `sum(int,int)` matching descriptor `(II)I`.
- Method `greeting(String)` performing string concatenation to observe one way the compiler can use `invokedynamic`.
- Method `names()` returning `List<String>` to compare generic `Signature` against erased descriptor.
- Main to verify runtime stdout.

### 3.2. Provider.java and StringProvider.java

Create **src/lesson/bytecode/Provider.java**:

~~~java
package lesson.bytecode;

public interface Provider<T> {
    T get();
}
~~~

Create **src/lesson/bytecode/StringProvider.java**:

~~~java
package lesson.bytecode;

public final class StringProvider implements Provider<String> {
    @Override
    public String get() {
        return "ok";
    }
}
~~~

These two types help observe **type erasure** and **bridge methods**: the generic interface declares `T get()`, the implementation returns String; the compiler needs to preserve compatibility with calls through the erased type.

### 3.3. Compiling and Running

Linux/macOS:

~~~sh
mkdir -p out
javac --release 17 -encoding UTF-8 -g -d out src/lesson/bytecode/BytecodeSample.java src/lesson/bytecode/Provider.java src/lesson/bytecode/StringProvider.java
java -cp out lesson.bytecode.BytecodeSample
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac --release 17 -encoding UTF-8 -g -d out src/lesson/bytecode/BytecodeSample.java src/lesson/bytecode/Provider.java src/lesson/bytecode/StringProvider.java
java -cp out lesson.bytecode.BytecodeSample
~~~

**Verified exact stdout:**

~~~text
5
Lan:Mai
~~~

`-g` requests generating extra debug info (especially local variable and source line tables) for use in the `-l` section. `--release 17` selects Java 17 language/APIs and class-file target, even though the JDK running javac may be newer.

## 4. First Step: Default javap Lists Declarations

Run:

~~~sh
javap -classpath out lesson.bytecode.BytecodeSample
~~~

Verified output snippet:

~~~text
Compiled from "BytecodeSample.java"
public final class lesson.bytecode.BytecodeSample {
  public static final int LIMIT;
  public lesson.bytecode.BytecodeSample(java.lang.String);
  public int sum(int, int);
  public java.lang.String greeting(java.lang.String);
  public java.util.List<java.lang.String> names();
  public static void main(java.lang.String[]);
}
~~~

Notable details:

1. The class's qualified name is `lesson.bytecode.BytecodeSample`.
2. `public final` of the class and `public` of the members appear in declarations.
3. The constructor bears the class name and takes a String.
4. `sum` has two int parameters and returns int.
5. `names` in declaration form can display `List<String>`, because javap reads additional generic metadata when present.
6. Field `private final String name` **does not appear yet** in the default listing; `-p` is needed.

This text is a **presentation rendered from the class file**, not the original source code. It does not include method bodies, comments, declaration order in all cases, or original syntactic choices.

## 5. Viewing Full Members with -p

Run:

~~~sh
javap -classpath out -p lesson.bytecode.BytecodeSample
~~~

The listing additionally includes:

~~~text
private final java.lang.String name;
~~~

`-p` (also written `-private`) shows all members, including private ones. Distinguish it from other visibility display options:

| Option | Purpose |
|---|---|
| No modifier passed | Displays regular members per javap defaults, omitting private |
| `-public` | Displays only public members |
| `-protected` | Displays protected and public members |
| `-package` | Displays members with package access or higher |
| `-p` or `-private` | Displays all members, including private |

When inspecting a **published binary API**, you can inspect `-public -s`. When inspecting the actual structure of a class, use `-p -s` to avoid missing private fields/methods and compiler-generated members.

### 5.1. Viewing Constant Values with -constants

~~~sh
javap -classpath out -constants lesson.bytecode.BytecodeSample
~~~

A notable line:

~~~text
public static final int LIMIT = 10;
~~~

Do not confuse `-constants` with evaluating every `final` field at runtime. This option displays **constant values present in class-file metadata** when applicable, such as constant variables per Java rules. For field `private final String name` assigned only in the constructor, there is no compile-time constant value to print similarly.

## 6. What Is a Descriptor? Why Does It Differ from Java Declarations?

A **JVM descriptor** is a string encoding **types at the class-file/binary linkage level**, used in field descriptions and method signatures. It is not written in normal Java source syntax. The `javap -s` tool displays these descriptors.

Run:

~~~sh
javap -classpath out -p -s lesson.bytecode.BytecodeSample
~~~

Verified excerpt:

~~~text
public static final int LIMIT;
  descriptor: I

private final java.lang.String name;
  descriptor: Ljava/lang/String;

public lesson.bytecode.BytecodeSample(java.lang.String);
  descriptor: (Ljava/lang/String;)V

public int sum(int, int);
  descriptor: (II)I

public java.lang.String greeting(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

public java.util.List<java.lang.String> names();
  descriptor: ()Ljava/util/List;

public static void main(java.lang.String[]);
  descriptor: ([Ljava/lang/String;)V
~~~

Descriptors reflect the types the JVM uses to resolve methods/fields, not what the method computes.

### 6.1. Primitive Type Code Table

| Java Type | Field Descriptor |
|---|---|
| `byte` | `B` |
| `char` | `C` |
| `double` | `D` |
| `float` | `F` |
| `int` | `I` |
| `long` | `J` |
| `short` | `S` |
| `boolean` | `Z` |
| `void` | `V`, used only in the return position of a method descriptor |

`I` is int, not Integer. `J` is long, not a class name. `V` means the method returns void, and cannot be set as a field type.

### 6.2. Descriptors for References and Arrays

- `Ljava/lang/String;`: reference to class `java.lang.String`.
- `Ljava/util/List;`: reference to interface `java.util.List`.
- `[I`: one-dimensional array of int (`int[]`).
- `[[I`: two-dimensional array of int (`int[][]`).
- `[Ljava/lang/String;`: String array (`String[]`).
- `[[Ljava/lang/String;`: two-dimensional String array.

Type names in object descriptors use **slashes** instead of dots and end with a **semicolon**. Each `[` indicates an additional array dimension. For nested classes, binary names can contain `$` such as `Outer$Inner`.

### 6.3. Descriptors for Methods

Template:

~~~text
(<parameter descriptors in order>)<return type descriptor>
~~~

Examples:

| Java method | Descriptor |
|---|---|
| `void run()` | `()V` |
| `int sum(int a, int b)` | `(II)I` |
| `String greeting(String s)` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `void main(String[] args)` | `([Ljava/lang/String;)V` |
| `long compute(int[] a, boolean b)` | `([IZ)J` |
| `String[][] matrix()` | `()[[Ljava/lang/String;` |

Decoding `(II)I`: open `(`, two int parameters `I I`, close `)`, return int `I`. Decoding `([Ljava/lang/String;)V`: one parameter which is a String array, method returns void.

Constructors in bytecode have the special name `<init>` with return descriptor `V`. For example, `(Ljava/lang/String;)V` represents a constructor taking String. `<clinit>` is the class initialization method when needed; it differs from constructors and usually does not appear as a regular Java source method.

### 6.4. Descriptors Do Not Retain Generic Type Arguments

`names()` is presented in Java form with return `List<String>` yet its descriptor is:

~~~text
()Ljava/util/List;
~~~

Reason: **type erasure**. JVM descriptors use the raw type of `List`, without the `<String>` part. An auxiliary attribute named **`Signature`** can retain generic info for compilers/reflection tools. Do not conclude generics have “completely vanished from the class file” just because the descriptor lacks type arguments.

## 7. Distinguishing descriptor from the Signature Attribute

Run:

~~~sh
javap -classpath out -v lesson.bytecode.BytecodeSample
~~~

In the `names` method section, verified output contains:

~~~text
descriptor: ()Ljava/util/List;
Signature: #67
~~~

In the comment of the corresponding entry, `javap` shows the generic content:

~~~text
()Ljava/util/List<Ljava/lang/String;>;
~~~

Meaning:

- **descriptor**: JVM form used for method linkage after erasure, `()Ljava/util/List;`.
- **Signature**: auxiliary generic metadata, representing `List<String>`.
- **Binary compatibility**: you cannot assume two methods differing only in generic type arguments form two valid overloads; erasure can make their signatures collide.

For example, you cannot simultaneously declare `void f(List<String> x)` and `void f(List<Integer> x)` in the same class just to distinguish them by generic type arguments: after erasure, both have parameter type `List`.

### 7.1. Return Types and Differences When Overriding

A method's descriptor includes its **return type**, even though Java source overloading rules do not trivially permit two methods differing only in return type. The compiler can generate a **bridge method** to maintain polymorphism when generics/covariant returns change binary descriptions. Section 10 will illustrate this with a dedicated class.

## 8. Viewing Bytecode with -c: Reading the JVM Operand Stack

Run:

~~~sh
javap -classpath out -c lesson.bytecode.BytecodeSample
~~~

In the `sum` method, verified output:

~~~text
public int sum(int, int);
  Code:
     0: iload_1
     1: iload_2
     2: iadd
     3: ireturn
~~~

The JVM uses an **operand stack** virtual machine for many instructions. We can trace:

| Offset | Opcode | Stack before → after |
|---|---|---|
| 0 | `iload_1` | `[] → [left]` |
| 1 | `iload_2` | `[left] → [left, right]` |
| 2 | `iadd` | `[left, right] → [left + right]` |
| 3 | `ireturn` | Pop int from stack, return to caller |

In an instance method, local slot **0** usually holds `this`, while int parameters `left` and `right` sit in slots 1 and 2. Opcode `iload_1` does not mean “read source line 1” but **read local variable slot 1**.

`iadd` adds two int values on the operand stack and pushes the int result. `ireturn` is used for methods returning int (and certain smaller types represented as int in bytecode). Methods returning references normally use `areturn`; methods returning void use `return`.

### 8.1. Offsets Are Not Java Line Numbers

Numbers `0, 1, 2, 3` before the colon are **bytecode offsets** inside the Code attribute, not source line numbers. Instructions vary in length, so offsets do not necessarily increment by one each time. When using `-g` and `-c -l`, instructions can be matched against LineNumberTable.

### 8.2. Constructors Have invokespecial and putfield

The constructor section of BytecodeSample has:

~~~text
0: aload_0
1: invokespecial #1     // Method java/lang/Object."<init>":()V
4: aload_0
5: aload_1
6: putfield      #7     // Field name:Ljava/lang/String;
9: return
~~~

Interpretation:

1. `aload_0` pushes `this` onto the stack.
2. `invokespecial` calls the superclass constructor `Object.<init>`.
3. `aload_0` and `aload_1` push the object and String parameter.
4. `putfield` writes the parameter into instance field `name`.
5. `return` finishes the constructor.

Indices `#1`, `#7` are **constant-pool references** inside the class being read, not stable “method IDs” across two compilations. You can inspect the meaning of corresponding entries with `javap -v`.

### 8.3. Commonly Encountered Opcodes

| Opcode | Meaning |
|---|---|
| `aload_n`, `iload_n` | Push reference/int from local slot onto operand stack |
| `astore_n`, `istore_n` | Store reference/int from stack into local slot |
| `iconst_0`, `iconst_1`, ... | Push small int constant |
| `ldc` | Load constant-pool constant usable with this instruction |
| `getfield`, `putfield` | Read/write instance field |
| `getstatic`, `putstatic` | Read/write static field |
| `new`, `dup` | Create object and duplicate top stack value |
| `invokestatic` | Call static method |
| `invokevirtual` | Call virtual instance method |
| `invokespecial` | Call special instance methods, including constructors |
| `invokeinterface` | Call interface method |
| `invokedynamic` | Dynamic call site linked via a bootstrap method |
| `iadd` | Add two ints on the stack |
| `ireturn`, `areturn`, `return` | Return int, reference, or void |
| `ifeq`, `if_icmpge`, `goto` | Control flow / branching |

Do not infer that every interface call in source always makes the compiler emit the exact same opcode in all situations. Instruction selection also depends on method kind, static type, language rules, and compilation output.

## 9. String Concatenation and invokedynamic

Sample method:

~~~java
public String greeting(String guest) {
    return name + ":" + guest;
}
~~~

With javac targeting Java 17 in the verification run, the disassembly is:

~~~text
0: aload_0
1: getfield      #7    // Field name:Ljava/lang/String;
4: aload_1
5: invokedynamic #13, 0 // InvokeDynamic #0:makeConcatWithConstants:(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
10: areturn
~~~

The compiler uses an **invokedynamic call site** allowing runtime to establish an appropriate string concatenation strategy. When inspecting `javap -v`, the constant pool and `BootstrapMethods` hold information about the bootstrap method, in this implementation case involving `java.lang.invoke.StringConcatFactory`.

Do not confuse the `invokedynamic` instruction with source “calling a function named invokedynamic”. It is an instruction in the class file. Similarly, seeing `invokedynamic` does not by itself prove lambdas are present; modern Java uses it for multiple purposes, including string concatenation.

Different javac/JDK/targets may emit string concatenation bytecode differently (e.g., using StringBuilder or another mechanism). **The required observable outcome** remains `Lan:Mai` when running the example; bytecode shape is an implementation choice that can change.

## 10. Compiler-Generated Bridge Methods and Synthetic Methods

Inspect the StringProvider class from section 3:

~~~sh
javap -classpath out -p -s lesson.bytecode.StringProvider
~~~

Verified meaningful excerpt:

~~~text
public java.lang.String get();
  descriptor: ()Ljava/lang/String;

public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
~~~

Why does source declare only one `get()` method while output has **two**? Because interface `Provider<T>` after erasure has the corresponding method `Object get()`, whereas the implementation declares `String get()`. The compiler generates a **bridge method** so calls through the interface's binary form still reach the right implementation.

Use:

~~~sh
javap -classpath out -p -v lesson.bytecode.StringProvider
~~~

For method `Object get()`, verified output contains:

~~~text
descriptor: ()Ljava/lang/Object;
flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
~~~

`ACC_BRIDGE` identifies the method as a bridge; `ACC_SYNTHETIC` indicates it was compiler-generated and does not directly correspond to a normal source method declaration.

A conceptual mental model of the bridge can be viewed as:

~~~java
// Conceptual illustration code, NOT Java source that you can declare yourself
// with two get() methods simultaneously differing only in return type.
public Object get() {
    return get(); // delegates to the String get() version by binary descriptor
}
~~~

Do not copy the illustrative snippet above into a real class: Java source **does not allow** overloading two methods differing only in return type; bridges exist at the class-file level, emitted by the compiler under binary linkage rules. To see the bridge's actual opcodes, use `javap -p -c` on the compiled class.

### 10.1. Why Are Bridges Important When Checking APIs?

When upgrading library versions, changing generic superclasses/interfaces, or changing covariant returns, bridge methods can affect **binary compatibility**. Reading only source without checking class files may miss the synthetic method enabling old binary consumers to keep invoking the right behavior.

Also note bytecode can contain other synthetic methods/fields, such as from certain Java constructs or compiler transformations. Do not call every compiler-generated method “malicious” or “redundant”; inspect its flags and role.

## 11. Using -v to View Class-File Metadata

~~~sh
javap -classpath out -v lesson.bytecode.BytecodeSample
~~~

`-v` (verbose) provides more information than `-c`:

- Classfile path, size, and readable metadata.
- Major/minor version, class access flags.
- Constant pool entries.
- Field/method declarations along with descriptors, flags, and attributes.
- Code, StackMapTable, or verification info when present.
- LineNumberTable/LocalVariableTable if the class contains debug info.
- Signature, SourceFile, InnerClasses, BootstrapMethods... when present.

**Verified** header excerpt for Java 17 target:

~~~text
minor version: 0
major version: 61
flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER
~~~

**Major 61 is Java 17.** Even though the current compiler tool might be JDK 24, `javac --release 17` selects the class-file format matching Java 17. This is a way to verify output was not confused with the running javac version.

For class files using preview language/VM features of a release, minor version may be specially marked (65535) per specification. Do not assume every class compiled with preview flags has that marker if the class does not actually use preview features. To analyze preview, cross-check the exact JDK and feature.

### 11.1. Constant Pool References

In disassembly, the line:

~~~text
invokevirtual #34    // Method sum:(II)I
~~~

points to an entry in the constant pool. `#34` is **the index in the constant pool inside that specific class file**, not a stable method number. When the compiler generates different bytecode or orders the constant pool differently, the index can change even though the target method semantically remains `sum(int,int)`.

When using `-v`, you can trace from an instruction to a constant-pool entry, then to the class name and corresponding NameAndType/descriptor. This is how to investigate a `NoSuchMethodError` or suspect code calling the wrong binary API.

### 11.2. Access Flags

Javap displays flags such as:

- `ACC_PUBLIC`, `ACC_PRIVATE`, `ACC_PROTECTED`.
- `ACC_STATIC`, `ACC_FINAL`.
- `ACC_ABSTRACT`, `ACC_INTERFACE`.
- `ACC_BRIDGE`, `ACC_SYNTHETIC` in appropriate cases.

Note that **class and method flag codes have different contexts**; do not deduce mechanically just from hex numbers. `javap` already decodes flag names, usually more readable than raw access_flags.

### 11.3. Attributes Depending on Class Kind

When compiling records, sealed classes, lambdas, nestmates, generic signatures, or module artifacts, `-v` may show attributes such as `Record`, `PermittedSubclasses`, `NestHost`/`NestMembers`, `BootstrapMethods`, or `Module` depending on structure. These attributes are not required to exist in every class. Do not expect them on BytecodeSample if source does not use the corresponding feature.

## 12. Reading Line Numbers and Local Variables with -c -l

To learn which source line bytecode maps to and what names local slots carry, compile with debug information:

~~~sh
javac --release 17 -g -d out src/lesson/bytecode/BytecodeSample.java src/lesson/bytecode/Provider.java src/lesson/bytecode/StringProvider.java
~~~

Then run:

~~~sh
javap -classpath out -c -l lesson.bytecode.BytecodeSample
~~~

`-l` requests displaying line/local-variable tables **when present**, and in verified javap it must be combined with `-c` or `-v` to print the tables properly. Running `javap -l` alone on the tested JDK emitted a warning like:

~~~text
Warning: bad combination of options: -l without -c, line number and local variable tables will not be printed
~~~

Therefore, practice guides use **`-c -l`**. If local variable tables are missing, verify you actually compiled with **`-g`** and are reading the right output file. Debug info may be stripped by optimization/obfuscation tools in release artifacts.

### 12.1. LocalVariableTable Does Not Define Method Logic

`LocalVariableTable` can hold names `left`, `right`, slots, start/length ranges, and descriptors for local variables. It primarily supports debugging/tooling; the JVM does not strictly need those source variable names to execute the method.

Example with method:

~~~java
public int sum(int left, int right) {
    int result = left + right;
    return result;
}
~~~

If compiled with `-g`, bytecode may show:

~~~text
0: iload_1
1: iload_2
2: iadd
3: istore_3
4: iload_3
5: ireturn
~~~

And LocalVariableTable has `left` slot 1, `right` slot 2, `result` slot 3. **This snippet is a different variant** from the sum method in the original BytecodeSample, because it has an intermediate variable `result`. It was verified with a separate Example class. Do not mix up results from two source versions and assume javap contradicts itself.

### 12.2. SourceFile, LineNumberTable, and LocalVariableTable Differ

| Attribute | Role |
|---|---|
| `SourceFile` | Source file name recorded inside the class |
| `LineNumberTable` | Maps bytecode offsets to source lines |
| `LocalVariableTable` | Names, slots, ranges, and descriptors of local variables |
| `LocalVariableTypeTable` | Can hold generic signatures of local variables when applicable |
| `Signature` | Generic metadata for classes/members |

Source compiled without `-g` can still retain default line info, yet **never guarantee all debug tables always exist**. Compiler flags and class-file processing tools decide which metadata is actually kept.

## 13. Distinguishing -s, -c, -v, and -p

Four options answer different questions:

| Command | Primary Information |
|---|---|
| `javap MyClass` | Human-readable Java-style declarations |
| `javap -p MyClass` | Includes private members |
| `javap -s MyClass` | JVM descriptors |
| `javap -c MyClass` | Method bytecode disassembly |
| `javap -v MyClass` | Full detailed metadata |
| `javap -p -s MyClass` | All member declarations and descriptors |
| `javap -p -c MyClass` | Bytecode including private methods (if Code exists) |
| `javap -c -l MyClass` | Instructions plus line/local-variable tables when present |
| `javap -constants MyClass` | Compiler-recorded constant values |
| `javap -sysinfo MyClass` | Artifact info, size/checksum when supported |

When comparing binary APIs, usually start with **`-p -s`**. When checking compiled behavior, add **`-c`**. Only enable **`-v`** when needing to read the constant pool, flags, generic Signature, bootstrap, or deep metadata, because the output is quite long and easy to lose the main point in.

## 14. Using javap to Inspect JARs, Modules, and Dependencies

### 14.1. Classes from a JAR

Suppose classes have been packaged into a JAR:

~~~sh
jar --create --file artifacts/sample.jar -C out .
javap -classpath artifacts/sample.jar -p -s lesson.bytecode.BytecodeSample
~~~

Create the `artifacts` directory before running the command. Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path artifacts | Out-Null
~~~

Linux/macOS: `mkdir -p artifacts`.

Use `jar --list --file artifacts/sample.jar` to verify the JAR contains entry `lesson/bytecode/BytecodeSample.class`. If javap reports class not found, it is usually due to pointing to the wrong classpath root, wrong binary name, or the JAR actually lacking the class; do not rush to conclude the compiler failed to produce the class.

### 14.2. Classes Belonging to a Named Module

With JPMS, javap supports module-related options such as **`--module-path`**, **`--module`**, or **`-m`**, depending on tool syntax:

~~~sh
javap --module-path mods --module demo.library -p demo.library.api.Greeting
~~~

This is an illustrative command for a project **that actually has module demo.library** at `mods`, not a command to run directly on BytecodeSample (because the sample project has no module-info.java). Specify the exact module and class belonging to that module.

Do not substitute classpath and module path mechanically. If a class resides in a named module, verify the module path and that the module is located/resolved via javap's mechanism.

### 14.3. Checking Exact Library Versions Before Running

An application compiled against method `greeting(String)` yet run with a JAR lacking the matching descriptor can hit `NoSuchMethodError`. In that case you can compare:

~~~sh
javap -classpath compile-libs/api.jar -p -s some.package.Library
javap -classpath runtime-libs/api.jar -p -s some.package.Library
~~~

Both JAR paths and class names in the example above are **placeholders** to replace with actual artifacts; the goal is comparing **binary names, static/instance, params, and return descriptors** of API versions, not just method names seen in source.

`javap` only tells you about the class file you are reading. It **does not prove** the production JVM is loading that exact class file; check runtime classpath/module path or class loading logs when verifying the version actually loaded.

## 15. Reading Bytecode Without Over-Inferring

There are several traps when inspecting javap:

1. **Bytecode is not source.** Compilers can transform structures and generate bridge/synthetic members.
2. **One Java expression does not necessarily equal one opcode.** String concatenation can use invokedynamic; a call may need multiple load/cast instructions.
3. **Do not equate offsets with line numbers.** Offsets are bytecode positions inside the Code attribute.
4. **Do not treat constant pool indices as stable.** `#13`, `#34` can change.
5. **Do not infer runtime duration from instruction count.** The JVM has an interpreter/JIT, optimizations, inlining, GC, and other runtime properties.
6. **Do not guess generic types from descriptors alone.** Read Signature when needed.
7. **Do not think synthetic/bridge is a bug.** They are often needed to maintain compatibility.
8. **Do not assume private members do not exist just because default javap omits them.** Use -p.
9. **Do not conclude the JVM will execute all branches cleanly just because javap can read the class.** Bytecode can still throw exceptions/runtime linkage errors.
10. **Do not treat javap output as an absolute formatting contract across JDKs.** Use assertions about semantics rather than matching verbatim version-dependent text.

### 15.1. Unexpected Case: Source Has Annotations or Generics Yet Bytecode Differs from Source

Annotations with `RetentionPolicy.SOURCE` may not be written into class files; javap -v will not see them in runtime-visible annotations. With generic return `List<String>`, the descriptor is `Ljava/util/List;` while the Signature attribute can retain type arguments. Both examples illustrate why you must understand **how the compiler stores metadata**, rather than only looking at source syntax.

### 15.2. When Should You Inspect -v Instead of Just -c?

Use `-v` if wanting to know:

- Whether the class target is Java 17 (major 61).
- What access flags a bridge method has.
- Where runtime annotations or generic signatures are stored.
- Which constant pool entries method references point to.
- What the bootstrap method for invokedynamic is.
- Whether the class has Record/PermittedSubclasses/NestMembers/Module attributes.

Use `-c` if only needing to understand a method's opcodes and stack operation order. Use `-s` if only checking binary descriptors, as it has less noise.

## 16. Reproducible Output Validation Process

Suppose you just modified a Java method. Instead of immediately opening huge bytecode listings, proceed in order:

**Step 1 — Pin JDK and source.** Record `javac -version`; compile verified source targeting the right `--release`.

**Step 2 — Use dedicated output.** `javac -d out ...`, without mixing with `.class` files from earlier builds. Avoid accidentally reading stale JARs.

**Step 3 — Verify class existence.** Check path `out/package/Class.class` or the entry inside the JAR.

**Step 4 — List API.** `javap -classpath out -p -s FullyQualifiedClass`; compare declarations/descriptors against expectations.

**Step 5 — Check essential bytecode.** `javap -classpath out -c FullyQualifiedClass`; look for key methods/opcodes and calls.

**Step 6 — Inspect deep metadata if needed.** `javap -v` for class version, constant pool, Signature, bridge/synthetic flags, BootstrapMethods.

**Step 7 — Correlate with source.** Compile -g if needed, use `javap -c -l`; compare lines/slots. Remember local names are debug info and may be absent.

**Step 8 — Run for real.** `java -cp out FullyQualifiedClass` or run via the project's actual launcher/module, comparing stdout/test cases. Javap does not replace runtime validation.

**Step 9 — Verify distribution artifact.** If packaging a JAR, re-inspect the released JAR itself; a class in the out folder does not guarantee that class is inside the final artifact.

**Step 10 — Record results.** Save compiler target, artifact hash, key signatures, and test output; do not rely on mutable constant pool indices.

## 17. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Check |
|---|---|---|
| `Error: class not found` | Wrong classpath/binary name, class not compiled yet | Verify `-d out` and package tree |
| Javap prints old API | Reading stale JAR/class file | Specify exact classpath and artifact, cleanly rebuild project output |
| Private field not visible | Using default javap | Add -p |
| Descriptor not visible | Forgot -s | Use -p -s |
| Method body not visible | Forgot -c or method has no Code | Use -c, understand abstract/native methods have no Code |
| Local variable names missing | Missing debug info or wrong flags | Compile -g; use -c -l |
| `-l` alone warns bad combination | Needs disassembly/verbose combined | Use -c -l or -v |
| Generic signature differs from descriptor | JVM uses erasure | Compare Signature attribute too with -v |
| Strange Object get() method present | Compiler generated bridge | Check ACC_BRIDGE, ACC_SYNTHETIC in -v |
| Unexpected major version | Wrong compile target | Check --release, javac -version, actual JAR |
| `NoSuchMethodError` at runtime despite javap showing method | May be inspecting a different binary/runtime artifact or mismatched signature | Compare runtime class loading and descriptors |
| Bytecode differs when changing JDK | Compiler strategy/options changed | Compare same target yet verify semantics instead of absolute indices |

## 18. Self-Practice Exercises

**Exercise 1 — Predict descriptors.** Write descriptors for `int[] values()`, `void log(String, long)`, and `String[][] find(boolean)`. Answers: `()[I`, `(Ljava/lang/String;J)V`, `(Z)[[Ljava/lang/String;`.

**Exercise 2 — Compare visibility.** Run default javap and javap -p on BytecodeSample. Why does the `name` field appear only on the second run?

**Exercise 3 — Trace stack.** Use `javap -c` on sum; describe the stack after iload_1, iload_2, iadd, and ireturn. Try changing to `left - right`, recompile, and find the corresponding opcode.

**Exercise 4 — Generic erasure.** With names(), why does the descriptor return List while the javap declaration displays List<String>? Find Signature in -v.

**Exercise 5 — Bridge.** With StringProvider, find both String get() and Object get(). From ACC_BRIDGE/ACC_SYNTHETIC flags, explain why source lacks two declarations yet the class file has them.

**Exercise 6 — invokedynamic.** Inspect greeting() bytecode and BootstrapMethods in -v. Locate StringConcatFactory info. Explain why you cannot assume all string concatenation uses the exact same opcodes across all compilers.

**Exercise 7 — Major version.** Compile for Java 17 target, check major 61. Then compile for another target your JDK supports, observe the version, and discuss whether an older JVM can read newer classes.

**Exercise 8 — Debug info.** Compile a method having variable result with -g, view -c -l. Recompile with debug metadata disabled and compare LocalVariableTable; why can runtime still run properly?

**Exercise 9 — Actual artifact.** Package sample into a JAR, run javap from the JAR instead of the out directory. If results differ, check whether the JAR packaged the latest classes.

**Exercise 10 — NoSuchMethodError symptom.** Create two versions of a library with a same-named method having different descriptors. Use javap -p -s to compare binary signatures, then explain why the class appears to exist yet the JVM cannot find the old method.

## 19. Quick Checklist When Using javap

- [ ] Reading the right class, package, JAR, or module?
- [ ] Know the exact javac target and major/minor inside the class?
- [ ] Used -p if private members are needed?
- [ ] Used -s to verify descriptors instead of guessing from source?
- [ ] Distinguished generic Signature from erased descriptor?
- [ ] Used -c and understood operand stack, local slots, and offsets?
- [ ] Used -v when needing constant pool, flags, bootstrap, or synthetic members?
- [ ] Compiled -g and used -c -l if debug tables are needed?
- [ ] Remembered output can vary by compiler/options while sharing the same semantics?
- [ ] Ran application/tests and inspected the actual distributed artifact?

**Conclusion:** `javap` is a tool to verify **compilation results at the class-file level**. Read **declarations** to check APIs, **descriptors** to check binary forms linked by the JVM, **bytecode** to understand instructions and stack flows, and **verbose attributes** to analyze generics, bridge/synthetic methods, invokedynamic, or versions. Understanding all these layers helps you investigate differences between Java source, released JARs, and runtime behavior instead of guessing from method names.

## 20. References

- Oracle Java SE 17, `The javap Command`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Oracle Java SE 17, `The javac Command`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- The Java Virtual Machine Specification, `Field Descriptors` and `Method Descriptors`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3
- The Java Virtual Machine Specification, `Class File Format` and `Attributes`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- The Java Virtual Machine Specification, `Instructions`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- The Java Language Specification, `Erasure`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6

To verify yourself, start with the Java 17 source code and commands in section 3; then compare `javap` output across each option instead of only reading the explanations.
