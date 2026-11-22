# Constant pool in class files: constants, type names, and symbolic references

## Objectives

When compiling Java source code, `javac` generates a `.class` file containing bytecode along with several tables and attributes describing the class. A central component is the **constant pool**: an indexed table used to describe constant values, character strings, class names, field/method names, data types, and symbolic references. Although called a “constant pool”, it **does not only contain immutable values such as numbers and strings**.

After this lesson, you can:

- Point out the location and structure of `constant_pool` in `ClassFile`, distinguishing the **class-file constant pool** from the **run-time constant pool**.
- Read the important entry groups: `Utf8`, `Integer`, `Long`, `Class`, `String`, `NameAndType`, `Fieldref`, `Methodref`, `InterfaceMethodref`, and the group serving dynamic linking.
- Explain the reference chain `Methodref → Class + NameAndType → Utf8`, and how *internal names* and *descriptors* are used.
- Understand how the bytecodes `ldc`, `getstatic`, `invokestatic`, and `invokevirtual` access the constant pool, and when the JVM needs **resolution**.
- Compile Java 17+ yourself, observe the table with `javap -v`, and analyze common linking errors without confusing them with syntax errors.

## 1. What is the constant pool used for?

JVM bytecode mainly works with the operand stack, local variables, and operands with a compact format. It **does not encode the final memory address of every class, field, and method** inside each instruction. Instead, instructions can reference **an index** in the current class's constant pool.

Example of the idea:

~~~text
getstatic    #18   // symbolic reference to System.out
ldc          #24   // load String constant
invokevirtual #30  // symbolic reference to PrintStream.println
~~~

This is an **illustration**; the numbers `#18`, `#24`, `#30` are only examples, **not stable indices** of a specific class. `javac` and other tools may order constant pool entries differently.

The constant pool helps **share information within the same class file** and represent dependencies in symbolic form (name, kind, descriptor). When the JVM loads/links and executes the class, it can resolve those symbols into the corresponding runtime entities.

Distinguish three terms right away:

| Term | Where it lives / role | Common misconception |
| --- | --- | --- |
| **Class-file constant pool** | The `constant_pool` table encoded directly inside each `.class` file | Does not consist only of literals; also has type names and references to fields/methods. |
| **Run-time constant pool** | The runtime structure created from the constant pool when the JVM creates a class/interface; by specification, it is a component of the **method area** | May contain resolved state/information; not synonymous with a single JVM-wide String table. |
| **String intern pool** | The canonicalization mechanism for `String` objects, used by `String.intern()` and string literals according to Java rules | Not synonymous with each class file's `CONSTANT_String` table. |

Each class file owns **its own** constant pool. Two classes that both mention `java/lang/String` can have **two separate `CONSTANT_Class` entries** in two class files. Having the same name does not by default mean they reference a shared physical location in the file or in JVM memory.

## 2. Location of the table in the ClassFile structure

According to the Java Virtual Machine Specification (JVMS), a `ClassFile` has the general layout:

~~~text
ClassFile {
    u4 magic;                  // 0xCAFEBABE
    u2 minor_version;
    u2 major_version;
    u2 constant_pool_count;
    cp_info constant_pool[constant_pool_count - 1];
    u2 access_flags;
    u2 this_class;
    u2 super_class;
    u2 interfaces_count;
    ...
    fields[];
    methods[];
    attributes[];
}
~~~

This is a **simplified diagram**; the full structure also has counts and sub-arrays corresponding to interfaces, fields, methods, and attributes. The notation `u1`, `u2`, `u4` represents unsigned integers with widths of 1, 2, and 4 bytes respectively; the byte order of the class file format is **big-endian**.

- `magic` is `0xCAFEBABE`, identifying a class file.
- `major_version`/`minor_version` indicate the **class file format version**, not the installed JDK version itself. Java 17 typically produces major **61**; Java 21 typically produces major **65** with the corresponding default target.
- `constant_pool_count` is a `u2`; valid indices of constant pool slots run from **1** to **`constant_pool_count - 1`**. **Index 0 is not an entry**.
- Each physical entry begins with a 1-byte `tag`, followed by data fields that vary by entry type.
- Slots following a `CONSTANT_Long` or `CONSTANT_Double` entry have a special rule: **each value of these types occupies two consecutive index slots**, though there is only one actual data entry. The next slot is unusable. Therefore, you must not infer the number of actually stored entries as `constant_pool_count - 1` in all cases.

### Example of index slots with a gap

~~~text
constant_pool_count = 8
#1 Utf8     "Sample"
#2 Class    name_index = 1
#3 Long     3000000000
#4 <unusable: slot after Long>
#5 Utf8     "java/lang/Object"
#6 Class    name_index = 5
#7 Utf8     "<init>"
~~~

This example illustrates the index structure, **not a complete valid class file**. With `Long` at `#3`, bytecode must not reference entry `#4`. The same rule applies to `Double`; other entries occupy only one index.

Several fields in the `ClassFile` structure also reference the pool. For example, `this_class` and `super_class` contain indices to `CONSTANT_Class` entries; the class name is followed through a `CONSTANT_Utf8` entry.

## 3. Entry types in the constant pool

The JVMS defines **17 tag types** in the modern class file format. Not every class file contains all of them; which types appear depends on the source, compiler, purpose of the class, target, and bytecode features used.

| Tag (decimal) | Entry name | Main meaning |
| --- | --- | --- |
| 1 | `CONSTANT_Utf8` | Text in **modified UTF-8** form: names, descriptors, attribute names, literal text, etc. |
| 3 | `CONSTANT_Integer` | 32-bit integer constant (can also be used for `boolean`, `byte`, `short`, `char` values under the appropriate encoding). |
| 4 | `CONSTANT_Float` | 32-bit floating-point constant. |
| 5 | `CONSTANT_Long` | 64-bit integer constant; occupies two index slots. |
| 6 | `CONSTANT_Double` | 64-bit floating-point constant; occupies two index slots. |
| 7 | `CONSTANT_Class` | Symbolic reference to a class/interface type or an array type descriptor as specified. |
| 8 | `CONSTANT_String` | Constant reference to a `String` object; points to content in `CONSTANT_Utf8`. |
| 9 | `CONSTANT_Fieldref` | Symbolic reference to a field of a class/interface. |
| 10 | `CONSTANT_Methodref` | Symbolic reference to a method (or constructor) of a class as specified. |
| 11 | `CONSTANT_InterfaceMethodref` | Symbolic reference to a method of an interface. |
| 12 | `CONSTANT_NameAndType` | Pairs a member/call site name with a field or method type **descriptor**. |
| 15 | `CONSTANT_MethodHandle` | Describes a method handle with reference kind and reference index. |
| 16 | `CONSTANT_MethodType` | Describes a method type via a descriptor. |
| 17 | `CONSTANT_Dynamic` | Dynamic constant (*dynamic constant*) computed and linked by a bootstrap method. |
| 18 | `CONSTANT_InvokeDynamic` | Dynamic call site used by the `invokedynamic` instruction and a bootstrap method. |
| 19 | `CONSTANT_Module` | Describes a module name, typically used with `module-info.class`. |
| 20 | `CONSTANT_Package` | Describes a package name, typically used with `module-info.class`. |

**Non-contiguous tags**: this does not mean every number from 1 to 20 is valid; for example, 2, 13, and 14 are **unused** in the type table above.

The group supporting dynamic linking (`MethodHandle`, `MethodType`, `Dynamic`, `InvokeDynamic`) will be explained thoroughly in a later section. You should not interpret the word “constant” in `CONSTANT_InvokeDynamic` as a literal that can be loaded with `ldc`: it is a description of a *dynamic call site*.

### `CONSTANT_Utf8` and modified UTF-8

`CONSTANT_Utf8_info` has a `length` of type `u2` and a byte sequence encoded in the JVM's **modified UTF-8**. This is **not completely identical to standard UTF-8**; the representation of the null character and certain UTF-16 code units differ. The field limit is **65,535 encoded bytes**, not 65,535 Java characters or Unicode characters. When reading binary files directly, you must follow the exact modified UTF-8 rules, byte length, and indices; do not arbitrarily use a regular UTF-8 decoder.

A `Utf8` entry only contains text; it **is not automatically a Java `String` object**. It can represent a class name, field name, descriptor, attribute name, or the text referenced by `CONSTANT_String`.

## 4. Type names: `Class` and internal name

Example of a Java class:

~~~java
package org.example;

public class Invoice {
}
~~~

This is standalone illustrative source code. In Java code, the fully qualified name of the class is `org.example.Invoice`. In the JVM's **internal name**, the dot separating packages is represented by a forward slash:

~~~text
Java name:       org.example.Invoice
JVM internal:    org/example/Invoice

A form of constant pool entries:
#10 = Class             #11
#11 = Utf8              org/example/Invoice
~~~

Indices `#10`/`#11` are **illustrative**. `CONSTANT_Class` contains `name_index` pointing to `CONSTANT_Utf8` storing the name; it **does not contain an entire `java.lang.Class` object in serialized form**.

For array types, the name in `CONSTANT_Class` can use an **array descriptor**, such as `[Ljava/lang/String;` (array `String[]`), as specifically required by the JVMS. A class file can also contain dependent type names such as `java/lang/Object`, `java/lang/System`, `java/io/PrintStream` if needed.

### Class identity also depends on the class loader

**The same name alone is not enough to guarantee the same runtime class.** When the JVM loads a class, the identity of a class/interface is tied to its **binary name and defining class loader**. Two different class loaders can define two classes with the same binary name that are two distinct types. Therefore, resolving a `CONSTANT_Class` also depends on the context of the referencing class and loading/linking rules, not just the text content of the class name.

## 5. Field/method names and descriptors: `NameAndType`

To link to a member, the JVM needs more than just a name. A name like `print` or `value` does not convey enough information about parameter types, return type, or field type.

A **field descriptor** denotes the type of a field; a **method descriptor** encodes the parameter type list and return type. Some basic notations:

| Descriptor | Corresponding Java type |
| --- | --- |
| `B` | `byte` |
| `C` | `char` |
| `D` | `double` |
| `F` | `float` |
| `I` | `int` |
| `J` | `long` |
| `S` | `short` |
| `Z` | `boolean` |
| `V` | `void` (only valid in the method return type position, not for field/parameter types) |
| `Ljava/lang/String;` | Reference to `java.lang.String` |
| `[I` | `int[]` |
| `[[Ljava/lang/String;` | `String[][]` |

Example:

~~~java
int count;
long sum(int a, long b) { return a + b; }
String join(String s, int n) { return s + n; }
~~~

This code snippet only illustrates members inside a class, not a standalone program. The corresponding descriptors:

~~~text
count : I
sum   : (IJ)J
join  : (Ljava/lang/String;I)Ljava/lang/String;
main  : ([Ljava/lang/String;)V
~~~

Analyzing `(IJ)J`:
- Parentheses `(...)` enclose the parameter types, in order `int` (`I`) and `long` (`J`).
- The part after `)` is the return type `long` (`J`).
- A descriptor **does not contain Java parameter names**, annotations, source-level generics, or `public`/`static` keywords.

Generics are **erased** at the regular JVM descriptor level: for example, `List<String>` is normally represented by the raw type `Ljava/util/List;` in a field/method descriptor. Declared generic information may appear in a separate `Signature` attribute, not as a new descriptor form like `List<String>`.

### `NameAndType` references two `Utf8` entries

A `CONSTANT_NameAndType` entry has two indices:
- `name_index` → `CONSTANT_Utf8` containing the name, e.g., `println`.
- `descriptor_index` → `CONSTANT_Utf8` containing the descriptor, e.g., `(Ljava/lang/String;)V`.

From there, `CONSTANT_Methodref`/`Fieldref` combines **Class** with **NameAndType** to identify the full symbol.

## 6. Symbolic reference structure: `Fieldref`, `Methodref`, `InterfaceMethodref`

Suppose there is a Java call:

~~~java
System.out.println("Hello");
~~~

This is an illustrative statement inside a Java method. It needs to access the static field `java.lang.System.out`, then invoke the method `java.io.PrintStream.println(String)`.

An illustrative graph:

~~~text
Fieldref: java/lang/System.out:Ljava/io/PrintStream;
  |
  +--> Class #A ---------> Utf8 "java/lang/System"
  |
  +--> NameAndType #B ---> Utf8 "out"
                         +-> Utf8 "Ljava/io/PrintStream;"

Methodref: java/io/PrintStream.println:(Ljava/lang/String;)V
  |
  +--> Class #C ---------> Utf8 "java/io/PrintStream"
  |
  +--> NameAndType #D ---> Utf8 "println"
                         +-> Utf8 "(Ljava/lang/String;)V"
~~~

The labels `#A`, `#B`, `#C`, `#D` are placeholders explaining **relationships**, not actual class file indices.

In binary form:
- `CONSTANT_Fieldref_info`, `CONSTANT_Methodref_info`, and `CONSTANT_InterfaceMethodref_info` all contain `class_index` and `name_and_type_index`.
- `class_index` points to `CONSTANT_Class`; `name_and_type_index` points to `CONSTANT_NameAndType`.
- The difference among the three types reflects **resolution rules / member kind** for a field, class method, or interface method.
- **Overloaded methods** can have the same name but different descriptors, so the name `println` alone is not enough to specify the exact overload.
- Constructors use the special JVM name `<init>` with a descriptor returning `V`; the class initializer `<clinit>` has its own role in the method structure, not as a regular constructor.

A **symbolic reference** is the bundle of information “which class, what name, what descriptor”, **not the actual address** of the method/field in the process. The name and descriptor are taken from the constant pool for the JVM to resolve in the appropriate loading/linking context.

## 7. Complete example: compile and inspect the constant pool with `javap`

Create the exact file **`ConstantPoolDemo.java`**:

~~~java
public final class ConstantPoolDemo {
    private static final String CATEGORY = "JVM";
    private static final long BASE = 3_000_000_000L;

    public static long add(long delta) {
        return BASE + delta;
    }

    public static void main(String[] args) {
        String source = "class-file";
        long result = add(7L);

        System.out.println(CATEGORY);
        System.out.println(source);
        System.out.println(result);
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac --release 17 ConstantPoolDemo.java
java ConstantPoolDemo
~~~

**Exact stdout:**

~~~text
JVM
class-file
3000000007
~~~

Why this output? `BASE` is a `long` constant with value 3,000,000,000; the method `add(7L)` returns 3,000,000,007. The two strings `"JVM"` and `"class-file"` are printed before the numeric result.

Inspect the compiled file:

~~~bash
javap -v -p ConstantPoolDemo
javap -c -p ConstantPoolDemo
javap -s -p ConstantPoolDemo
~~~

Meaning:
- `javap -v`: displays class file metadata, version, and the **Constant pool** table, along with code/attribute details.
- `-p`: also shows private members.
- `-c`: disassembles method bytecode.
- `-s`: prints JVM **descriptors** of fields/methods.

You should recognize the **kinds** of entries, rather than memorizing specific index numbers. With a typical Java compiler, observed results may include:

| Entry/bytecode kind | Origin in the example | What to observe |
| --- | --- | --- |
| `CONSTANT_Class`, `CONSTANT_Utf8` | `ConstantPoolDemo`, `java/lang/Object`, `java/lang/System`, `java/io/PrintStream` | Classes are referenced via internal names. |
| `CONSTANT_String` → `CONSTANT_Utf8` | `"JVM"` and `"class-file"` | `String` references a text entry; the `ldc` instruction can load a string literal. |
| `CONSTANT_Long` | `3_000_000_000L` and `7L` | 64-bit constants loaded with `ldc2_w` if the compiler emits a direct load instruction. |
| `CONSTANT_Fieldref` | `java/lang/System.out` | Bytecode `getstatic` references a static field. |
| `CONSTANT_Methodref` | `ConstantPoolDemo.add`, `PrintStream.println` | `invokestatic` and `invokevirtual` index into method references. |
| `CONSTANT_NameAndType` | `out:Ljava/io/PrintStream;`, `add:(J)J`, `println:(J)V` | Distinguishes member name from descriptor. |
| `ConstantValue` attribute | `CATEGORY` and `BASE` are compile-time constants | The constant value of a field is stored via a separate attribute referencing the pool; optimizations may inline it at call sites. |

**Do not copy exact `#N` numbers from one machine as a reference standard.** Different compilers/JDKs/targets or bytecode generation strategies can produce different indices, ordering, entry counts, and instructions while the program remains valid.

### Tracing from bytecode to the constant pool

In `main` of the program above, bytecodes of the form:

~~~text
ldc          #N   // string "class-file" or "JVM"
ldc2_w       #N   // large long value
invokestatic #N   // ConstantPoolDemo.add:(J)J
getstatic    #N   // java/lang/System.out
invokevirtual #N  // corresponding PrintStream.println overload
~~~

are **paths observable depending on how the compiler chooses instructions**, not an exact `javap` dump. To determine the actual values, find the `#N` number on the disassembled instruction and look up the same number in the `Constant pool` table. In `javap` output, the right-hand comment usually already resolves the indices at the display level into readable form such as `Method ConstantPoolDemo.add:(J)J`.

In particular, `CATEGORY` and `BASE` are **compile-time constant variables** (`static final` with an eligible constant initializer). The compiler may **inline** the used values, causing `main` or `add` not to use `getstatic` for these fields themselves; the presence of a field in the class file does not mean every read of it must have a corresponding `CONSTANT_Fieldref`.

## 8. Which values actually need an entry and which bytecodes reference the pool?

Not every Java source literal generates a constant pool entry to be loaded by `ldc`.

Example:

~~~java
int zero = 0;
int small = 5;
int medium = 100;
long large = 3_000_000_000L;
String name = "JVM";
~~~

This snippet illustrates code inside a method. A compiler can often emit:
- `iconst_0`, `iconst_5` for small integers.
- `bipush` or `sipush` to carry a short integer value **directly inside the instruction**.
- `ldc` or `ldc_w` for constants loaded from the pool (integers/floats, Strings, class literals, method types/handles, or suitable dynamic constants).
- `ldc2_w` for `long`/`double` (or dynamic constants of a suitable 64-bit type).
- Certain small `long`/`double` values like 0 or 1 have **dedicated instructions** (`lconst_0`, `dconst_1`), so they do not need a pool entry to load that literal.

Do not conclude “not seeing the number 5 in the constant pool means the compiler lost data”; the value may be embedded in the opcode. Conversely, `CONSTANT_Integer` does not necessarily serve only `int` variables in Java code: the class file specification uses this constant type for smaller integer types where appropriate.

**`ldc` vs `ldc_w`:** two instructions that load constants with index operands of different widths (1 byte and 2 bytes). `ldc2_w` uses a two-byte index to load a category 2 value such as `long`/`double`. The `w` here refers to **index width**, not that a string or number automatically converts to “higher precision”.

## 9. The constant pool in the file and the resolution process in the JVM

When loading a class, the JVM creates the corresponding run-time constant pool structure. **Symbolic references** need to be linked to actual classes, fields, methods, or call site entities. Resolution is part of **linking**; the major steps in a class's lifecycle are:

~~~text
.class on disk
    |
    v
Loading: create runtime structure of the class/interface
    |
    v
Linking:
    +-- Verification: check validity/constraints
    +-- Preparation: prepare static variables with default values
    +-- Resolution: map symbolic references to concrete entities
    |
    v
Initialization: run class initialization when triggered
    |
    v
Execution: bytecode uses constant pool and linking results
~~~

This diagram is conceptual: the JVM may **resolve on demand** or **resolve eagerly**, as long as it obeys the error-reporting timing and behavior required by the specification. Therefore, **you must not assert that all `Methodref` and `Fieldref` entries are resolved immediately when the class is loaded**, nor assert that resolution only occurs after execution of a specific instruction begins.

### Example of method reference resolution

To execute a call to a method such as `PrintStream.println(String)`, the VM must:
1. Read a `CONSTANT_Methodref` from the run-time constant pool of the currently executing class.
2. Find the owner type name via `Class` and the name/descriptor via `NameAndType`.
3. Following class loading, access control, and method resolution rules, determine the appropriate type and member or report a linking error.
4. When the instruction is executed, apply the semantics of the invoke kind, where `invokevirtual` also has a mechanism to **select the method implementation** based on the runtime receiver type.

**Resolution and virtual dispatch are not the same concept.** Resolution establishes the meaning of a symbolic reference; runtime method selection (such as virtual method dispatch) decides which implementation will run on a specific receiver.

Similarly, `CONSTANT_Fieldref` does not contain a reliable “fixed offset” of a field in every object. JVM implementations may cache/quicken differently, but that is an execution detail, not the original file format.

### Related linking errors

| Error | Common situation |
| --- | --- |
| `NoClassDefFoundError` | A class that needs to be defined/initialized is unavailable at runtime or cannot be loaded/initialized as required; check the root cause. |
| `NoSuchFieldError` | Bytecode references a field with a name/descriptor, but the runtime class version no longer has a matching field. |
| `NoSuchMethodError` | Bytecode references a method with a name/descriptor, but runtime cannot find a matching method, often due to binary-incompatible dependencies. |
| `IllegalAccessError` | Links to a class/member that is not permitted to be accessed under runtime rules, even though the source code may have compiled under a different configuration. |
| `IncompatibleClassChangeError` | The class/member kind changed incompatibly, such as static/instance or class/interface mismatch. |
| `ClassFormatError` | Class file data does not satisfy format/constraints when the JVM attempts to load it. |
| `VerifyError` | Violates bytecode validity checks during verification. |
| `BootstrapMethodError` | Bootstrapping of a dynamic constant/call site failed under specification conditions. |

The errors above are not simply “a wrong string in the constant pool”. You should verify **the actual JARs on the classpath/module path, bytecode versions, dependency versions, and class loaders**. A program that compiles successfully can still fail linking if runtime provides a different API than the one used at compile time.

## 10. Dynamic linking: MethodHandle, MethodType, InvokeDynamic, and Dynamic

Modern JVM languages and features need to represent links more flexible than regular `Methodref` references:

- **`CONSTANT_MethodHandle` (tag 15):** describes a method handle, consisting of `reference_kind` and `reference_index` pointing to the appropriate reference type. This is a link description following method handle semantics, not necessarily a direct call.
- **`CONSTANT_MethodType` (tag 16):** points to a `Utf8` containing a **method descriptor**, e.g., `(I)Ljava/lang/String;`.
- **`CONSTANT_InvokeDynamic` (tag 18):** describes a **dynamic call site**: a bootstrap method index and `NameAndType`. The `invokedynamic` bytecode uses this entry; the JVM performs bootstrapping/linking to produce the corresponding `CallSite`.
- **`CONSTANT_Dynamic` (tag 17):** describes a **constant value computed at resolution time**, also using a bootstrap and `NameAndType`, but the name-and-type descriptor here is a **field descriptor** of the value, unlike the method descriptor of `InvokeDynamic`.

`CONSTANT_InvokeDynamic` has existed since Java 7 / JVM class file major 51; `CONSTANT_Dynamic` since Java 11 / class file major 55. **They are not the same**: one is a *call site* to invoke, while the other is a *constant value* that can be loaded.

### Role of the `BootstrapMethods` attribute

If a class file has `CONSTANT_Dynamic` or `CONSTANT_InvokeDynamic`, it must have exactly **one** `BootstrapMethods` attribute at the class level. This attribute contains a table of bootstrap entries:

~~~text
BootstrapMethods:
  bootstrap_method_ref  -> CONSTANT_MethodHandle
  bootstrap_arguments[] -> constant entries of permitted types
~~~

The `bootstrap_method_attr_index` field in `CONSTANT_InvokeDynamic`/`CONSTANT_Dynamic` points to a **0-based index in the attribute's `bootstrap_methods` table**, **not** a constant pool index. Meanwhile, `bootstrap_method_ref` inside the attribute is an index to `CONSTANT_MethodHandle` in the constant pool. These two kinds of indices must be clearly distinguished when reading the file.

The **bootstrap method** performs the actual linking according to the contract of the dynamic entry type; a constant pool entry is descriptive information, not full Java logic embedded directly inside the entry.

### Java 17 example with lambda and string concatenation

Create the file **`DynamicPoolDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class DynamicPoolDemo {
    public static void main(String[] args) {
        IntUnaryOperator increment = value -> value + 1;
        int result = increment.applyAsInt(4);
        System.out.println("result=" + result);
    }
}
~~~

Commands:

~~~bash
javac --release 17 DynamicPoolDemo.java
java DynamicPoolDemo
javap -v -p DynamicPoolDemo
~~~

**Application stdout:**

~~~text
result=5
~~~

When using **standard `javac` for Java 17**, lambdas are typically emitted via `invokedynamic` with a bootstrap involving `LambdaMetafactory`; string concatenation typically uses `invokedynamic` with a bootstrap involving `StringConcatFactory`. In `javap -v` output, look for `InvokeDynamic`, `MethodHandle`, `MethodType`, and the `BootstrapMethods` attribute to see the related references.

**Java source does not need to contain the keyword `invokedynamic`.** It is a JVM instruction; the compiler chooses how to use it. Not every `invokedynamic` bytecode is a lambda; entries in the constant pool reflect the reality **of the compiled file**, and are not sufficient to uniquely conclude a single source Java syntax.

## 11. `CONSTANT_Module` and `CONSTANT_Package`

Since Java 9 (class file major 53), the constant pool also has two types to support the module system:

- `CONSTANT_Module`: points to a `Utf8` containing the module name.
- `CONSTANT_Package`: points to a `Utf8` containing the package name in the internal form as specified.

These entries typically appear in **`module-info.class`**, along with the `Module` attribute and related structures. Example module declaration:

~~~java
module org.example.payments {
    exports org.example.payments.api;
    requires java.logging;
}
~~~

This is illustrative content of **`module-info.java`**; compiling it requires an appropriate module/source structure and the exported package must exist. When viewing `javap -v module-info.class`, you can see `Module`/`Package` entries. You should not expect non-modular Java classes to have these tags.

## 12. The constant pool and other attributes in a class file

Many names/metadata are **referenced through the constant pool, yet the data does not reside entirely in the constant pool**:

- **`ConstantValue`:** an attribute of a field, having `constantvalue_index` pointing to a value in the pool. It describes the initial constant value of an eligible field; constant variables can also be inlined by the compiler when used elsewhere.
- **`Code`:** a method attribute containing bytecode, max stack/locals, exception table, and nested attributes. Instructions in `Code` use constant pool indices as operands.
- **`Signature`:** can store source-level generic information that descriptors erased; the text value resides in the referenced `Utf8`, without changing the semantics of standard field/method descriptors.
- **`SourceFile`, `LineNumberTable`, `LocalVariableTable`:** serve source/debug information if present; attribute names and many strings reside in `Utf8`, while detailed information is in separate attributes.
- **`StackMapTable`:** supports verifier type checking via frames; it can reference types via the constant pool without “turning into” a single constant entry.
- **Annotation attributes** and other attributes can use indices to `Utf8` and class/const entries according to their specific format.

Thus, **the constant pool is a structured reference table for the entire class file**, not a place storing bytecode, debug info, object graphs, or all metadata in a single block.

### Does the compiler always generate one entry for every occurrence of a literal?

No. The compiler can:
- Reuse the same constant pool entry for identical uses when valid.
- Inline compile-time constant values or precompute constant expressions.
- Use instructions with immediate operands, bypassing the pool.
- Generate auxiliary information, synthetic methods, and bootstrap arguments when compiling lambdas, string concatenation, records, or other features.
- Use separate `Utf8` entries for the same text or order them differently; you should not write tools that rely on an invariant ordering.

The specification describes **valid format and semantics**, and does not promise a fixed `#1, #2, #3,...` layout for the same source code across all compilers.

## 13. String literals and the String intern pool: an example to avoid confusion

A `CONSTANT_String` in a class file holds an index to a `CONSTANT_Utf8` for the literal content. When the JVM resolves an eligible String constant, the program receives a **reference to a `String` object** according to string literal/interning semantics; the entry in the file **is not a byte array packaging a runtime String object**.

Complete example **`StringPoolContrast.java`**:

~~~java
public class StringPoolContrast {
    public static void main(String[] args) {
        String a = "hello";
        String b = "hello";
        String c = new String("hello");

        System.out.println(a == b);
        System.out.println(a == c);
        System.out.println(a.equals(c));
        System.out.println(a == c.intern());
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 StringPoolContrast.java
java StringPoolContrast
~~~

**Stdout:**

~~~text
true
false
true
true
~~~

Explanation:
- The two `"hello"` literals are canonicalized according to string literal rules, so `a == b` is true.
- `new String("hello")` creates a different object, so `a == c` is false.
- `a.equals(c)` compares content and is true.
- `c.intern()` returns the canonicalized reference of that string, so `a == c.intern()` is true.

**Do not conclude “every `Utf8` entry is interned into a Java String”.** Most `Utf8` entries in a class file may simply be class names, descriptors, fields, or attributes; the intern mechanism for runtime strings is a separate concept.

## 14. Common issues when reading `javap` or processing class files directly

| Symptom | Cause / accurate explanation | How to check |
| --- | --- | --- |
| Seeing `Methodref #A.#B` without immediately seeing the method name | `Methodref` points indirectly through `Class` + `NameAndType`, then to `Utf8` | Follow each index or read `javap -v` comments. |
| Indices start at `#1` and there is a gap after `Long` | Index 0 is invalid; `Long`/`Double` occupy two slots | Check `constant_pool_count` and specification `4.4.5`. |
| A string literal exists, but no String object data is seen | Class file stores `CONSTANT_String` → `Utf8`, not heap objects | Separate the file constant pool concept from heap/String intern. |
| Compiled `5` but the constant pool has no `Integer 5` | `iconst_5` can place the literal directly in the opcode | Use `javap -c` to inspect instructions. |
| A `static final` field appears, yet no `getstatic` is seen at call sites | Compile-time constants can be inlined | Check `ConstantValue` and actual instructions at the call site. |
| `#N` indices differ across machines even with identical stdout | Compilers, targets, and class file generators can change layout | Do not hardcode pool indices in tests. |
| `InvokeDynamic` has bootstrap index 0, mistaken for `#0` | BootstrapMethods index is 0-based, distinct from constant pool indices | Read both tables accurately. |
| Seeing `Ljava/util/List;` without seeing `String` in generic descriptor | Type erasure; generics may reside in `Signature` | Use `javap -v -s -p`. |
| `NoSuchMethodError` appears even though compilation succeeded | Runtime class version has different members than the compile-time version | Compare JARs/dependencies, descriptors, class loaders, and module path. |
| Custom class file parser fails on Vietnamese text or null characters | `Utf8` uses modified UTF-8 with byte `length` | Read the `u2 length` structure and decode MUTF-8 properly. |
| Parser tool encounters unrecognized tags 17/18/19/20 | Older parser does not yet support modern class files | Upgrade the library/parser and respect the corresponding version/tags. |
| Using `java.lang.String` directly as an internal name | JVM uses `java/lang/String` in Class/descriptors | Convert binary/internal names according to the format. |

### How to investigate linking errors

When an error like `NoSuchMethodError` occurs, do not arbitrarily edit source code just because the error mentions *method*. Determine:

1. Which **owner class**, **method name**, and **descriptor** the error mentions.
2. Which class originates the call? In that class's bytecode, which `Methodref` or `InterfaceMethodref` does `javap -c -v` point to?
3. Which **class/JAR version** does runtime actually load, and by which class loader; check the classpath/module path and duplicate dependency versions.
4. Does the target class version have the exact method with matching descriptor/access/staticness?
5. Rebuild and run with the same set of runtime artifacts. Binary errors caused by replacing a library without recompiling the caller may not appear when compiling the source of an independent module.

A method with the same name but a **different descriptor** is not considered the same member for linking. This is one reason the constant pool stores **name and type** as two explicit components.

## 15. Self-check

**Question 1.** Does the constant pool in `.class` only contain integers and String literals?

**Answer:** No. It also contains `Utf8` names, `Class`, `NameAndType`, field/method/interface method references, and entries serving dynamic linking and modules.

**Question 2.** How does a `CONSTANT_Methodref` suffice to know the class, method name, parameter types, and return type?

**Answer:** From `class_index` to `CONSTANT_Class`/`Utf8` to get the owner; from `name_and_type_index` to `CONSTANT_NameAndType`/two `Utf8` entries to get the name and method descriptor.

**Question 3.** Why does `Long` in the constant pool make the next index unusable?

**Answer:** The class file format specifies that `CONSTANT_Long` and `CONSTANT_Double` occupy **two index slots**, even though they are a single data entry; the next slot must not be referenced.

**Question 4.** Do `java/lang/String` and `Ljava/lang/String;` have the same role?

**Answer:** `java/lang/String` is the internal name of the class; `Ljava/lang/String;` is the **field descriptor** for a reference type to that class. The descriptor adds `L` and `;`.

**Question 5.** What method does `(IJ)J` represent?

**Answer:** Two parameters `int` and `long`, with return type `long`. The method name and parameter names are not included in this descriptor string.

**Question 6.** Why should you not hardcode `#12` from `javap` as “the println call” in a tool?

**Answer:** Pool order/indices are specific to a given class file; compilers can generate different layouts. You must read the actual entry/index from the file itself.

**Question 7.** Does a `static final long BASE = 3_000_000_000L;` field always cause `getstatic` at every usage site?

**Answer:** No. A compile-time constant value can be inlined; usage sites may use `ldc2_w` instead of `getstatic` on the field.

**Question 8.** How does `CONSTANT_InvokeDynamic` differ from `CONSTANT_Dynamic`?

**Answer:** `InvokeDynamic` describes a **dynamic call site** for the `invokedynamic` instruction to link to a `CallSite`; `Dynamic` describes a **dynamic constant value** with a field descriptor type, computed at resolution via a bootstrap.

**Question 9.** Does bootstrap index 0 access `constant_pool[0]`?

**Answer:** No. `bootstrap_method_attr_index` is a **0-based** index into the attribute's list of bootstrap methods; the constant pool starts at **1**.

**Question 10.** Does the same name `com/example/Plugin` guarantee the same runtime class?

**Answer:** No. Class identity also depends on the defining class loader. Two loaders can define classes with the same name but different runtime identities.

## 16. Key takeaways

~~~text
ClassFile
  |
  +-- constant_pool (#1 .. #count-1)
  |      |
  |      +-- Literal       : Integer / Float / Long / Double / String
  |      +-- Text          : Utf8 (MUTF-8)
  |      +-- Type          : Class, Module, Package
  |      +-- Member symbols: Class + NameAndType -> Fieldref/Methodref/InterfaceMethodref
  |      +-- Dynamic links : MethodHandle/MethodType/Dynamic/InvokeDynamic
  |
  +-- fields / methods / Code / attributes
               |
               +-- reference pool indices

JVM: Loading -> Linking (including Resolution) -> Initialization -> Execution
        |
        +-- run-time constant pool and linking of symbolic references
~~~

**Main idea:** the constant pool is a **structured table of symbols and constants** that helps a class file represent dependencies independently of runtime memory layout. Understanding the path `Fieldref/Methodref → Class + NameAndType → Utf8`, how descriptors encode types, and how the JVM resolves them is the foundation for reading `javap`, investigating linking errors, and exploring advanced bytecode.

## Official references

- [JVMS Java SE 21 — `4.1` The ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.1).
- [JVMS Java SE 21 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3).
- [JVMS Java SE 21 — `4.4` The Constant Pool](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4).
- [JVMS Java SE 21 — `4.7.23` BootstrapMethods](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.23).
- [JVMS Java SE 21 — `5.1` The Run-Time Constant Pool](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.1).
- [JVMS Java SE 21 — `5.4` Linking, especially `5.4.3` Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3).
- [JDK 21 — javap tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).
