# Class File Attributes for Modules, Nestmates, Records, and Sealed Classes

A Java `.class` file contains more than a list of methods and bytecode instructions. **Class-file attributes** store additional metadata so the JVM can control access permissions, describe a module, identify record components, or check which classes are permitted to inherit. Four important groups in modern Java are **`Module` / `ModulePackages` / `ModuleMainClass`**, **`NestHost` / `NestMembers`**, **`Record`**, and **`PermittedSubclasses`**.

These attributes are easy to confuse with modifiers in source code. For example, Java uses the `sealed` keyword, but there is no corresponding `ACC_SEALED` bit in `access_flags`: the class file uses `PermittedSubclasses`. Similarly, `record` is reflected through the `Record` attribute; `module-info.class` is a special form of class file with the `ACC_MODULE` bit, not an ordinary Java class with `main`.

This lesson places each attribute in the class file structure, explains runtime constraints, its relationship to Java code, and how to inspect it with `javap`. Examples use **Java 17+** (all four groups are standard features in Java 17).

## 1. Viewing Attributes in Their Right Place in `ClassFile`

According to the Java Virtual Machine Specification (JVMS), a class file has the simplified form:

```text
ClassFile
├── magic, minor_version, major_version
├── constant_pool[]           // names, types, descriptors, symbol references...
├── access_flags              // ACC_PUBLIC, ACC_FINAL, ACC_MODULE, ...
├── this_class, super_class, interfaces[]
├── fields[]                  // field_info, with its own attributes
├── methods[]                 // method_info, Code and its own attributes
└── attributes[]              // CLASS-level attributes
    ├── Module | ModulePackages | ModuleMainClass
    ├── NestHost | NestMembers
    ├── Record
    ├── PermittedSubclasses
    └── other class-level attributes if any
```

This is a model illustrating **possibilities**, not that an actual class file necessarily contains all of the above attributes. `module-info.class` has its own constraints, and `NestHost` does not appear simultaneously with `NestMembers` on the same class file.

Each attribute generally has a header:

```text
u2 attribute_name_index    // index in constant pool, pointing to UTF-8 name
u4 attribute_length        // number of content bytes, excluding 6-byte header
... payload ...            // structure varies by attribute
```

`u2` and `u4` are unsigned integers of 2-byte or 4-byte width in the JVM format, not Java field declaration types. `javap -v` reads the binary data and interprets it into human-readable names/values; the source file does not store every modifier verbatim as a Java string.

### 1.1. Table of the Four Groups to Remember

| Group | Attribute in class file | Used since official class-file version | Main meaning |
| --- | --- | --- | --- |
| Module | `Module`, `ModulePackages`, `ModuleMainClass` | **53.0 / Java 9** | Module descriptor and metadata about packages/main class |
| Nestmate | `NestHost`, `NestMembers` | **55.0 / Java 11** | Declares nest relationships for `private` access checks |
| Record | `Record` | **60.0 / Java 16** | Declares a record class and list of record components |
| Sealed class/interface | `PermittedSubclasses` | **61.0 / Java 17** | Lists the types permitted to directly `extends` / `implements` |

The milestones above are the **class-file format versions in which the attributes were officially defined**, which does not mean there were no preview sources prior to that: records and sealed classes went through preview stages in earlier JDKs before becoming standard. Preview class files have their own version/`--enable-preview` rules; do not assume preview bytecode from an earlier release is automatically compatible with a later release.

### 1.2. Attributes and Access Flags Are Different

- An **access flag** is a bit in `access_flags`. For example, `ACC_MODULE` identifies a module descriptor, while `ACC_FINAL` indicates a class cannot be inherited.
- An **attribute** is a structure with its own name, length, and payload. `Record` and `PermittedSubclasses` belong to this group.
- **`InnerClasses`** describes information about nested/member classes so tools understand the source structure; it **does not replace** `NestHost`/`NestMembers` in deciding `private` access permissions in Java 11+ JVMs.
- The `Record` attribute does not replace `fields[]` and `methods[]`; those still exist to describe the actual fields, constructor, and accessors.

Each attribute has **allowed locations**, a maximum occurrence count, and compatibility limits. You cannot arbitrarily insert a `Module` attribute into a method and expect the JVM to understand it as a module.

## 2. Module Attributes: Describing Module Boundaries at the Class-File Level

The Java Platform Module System (JPMS, Java 9) introduced `module-info.java`. Compiling this file produces **`module-info.class`**, a class file with a structure dedicated to the module descriptor.

Source example:

```java
module com.example.catalog {
    requires java.logging;
    exports com.example.catalog.api;
    opens com.example.catalog.internal to com.example.consumer;
    uses com.example.catalog.spi.Provider;
    provides com.example.catalog.spi.Provider
        with com.example.catalog.internal.DefaultProvider;
}
```

This is a **snippet illustrating module descriptor syntax**, and it cannot compile on its own without the referenced packages, types, and modules. A complete runnable example appears in section 7.

Correspondingly, the `Module` attribute records these groups of data:

| Component in `Module` | Role |
| --- | --- |
| `module_name_index`, `module_flags`, `module_version_index` | Name and metadata of the module |
| `requires[]` | Required modules, flags such as `transitive`/`static` when applicable, optional version info |
| `exports[]` | Packages exported to other modules, optionally qualified exports |
| `opens[]` | Packages opened for deep reflection according to declared conditions |
| `uses[]` | Service interfaces declared as used |
| `provides[]` | Services and lists of provider implementations |

Module names in `Module` are referenced through `CONSTANT_Module_info` entries in the constant pool; packages through `CONSTANT_Package_info`, unlike `CONSTANT_Class_info` commonly seen for class names. `requires java.logging` is module relationship metadata, **not a bytecode instruction calling logging**.

### 2.1. `ACC_MODULE` and Constraints of `module-info.class`

When `ACC_MODULE` is set:

- `this_class` denotes the special name **`module-info`**.
- No other access flags may be set simultaneously in `access_flags`.
- `super_class`, the number of interfaces, fields, and methods are **0**. `module-info.class` has no ordinary Java constructor, no `main()` method, and no instances.
- There is **exactly one `Module` attribute** per the module class file constraint; some other attributes are allowed, including `ModulePackages` and `ModuleMainClass`.
- Requires a minimum class-file format of **53.0** (Java 9).

Therefore, `module-info.class` is **not** `com.example.ModuleInfo` that can be instantiated with `new` or called like a regular class. The JVM/toolchain uses that descriptor to understand the **module**, along with the JPMS resolution/layer configuration process.

### 2.2. How Is `ModulePackages` Different from `exports`?

`ModulePackages` records **the list of packages belonging to the module** according to the class-file attribute mechanism. The list can include packages that are **not exported or opened**, whereas `Module.exports[]` only specifies packages **accessible according to module relationships**.

- `exports p.api`: allows access to public types in the exported package from modules that read this module.
- `opens p.internal`: opens deep reflection capabilities according to module policy, without turning all types into compile-time public API.
- `ModulePackages`: reflects membership/package inventory; **does not grant read, exports, or opens permissions**.

`ModulePackages` **may not appear** in a simple `module-info.class` produced by `javac`. Other packaging/tooling steps (such as JAR tools or runtime image tools) may add the necessary metadata. **Do not conclude a module has no packages** just because you do not see this attribute.

### 2.3. Is `ModuleMainClass` the JAR's `Main-Class`?

`ModuleMainClass` is a class-file attribute specifying **the module's main class** if this information is stored in the module descriptor. It is **stored in a different place** from `Main-Class` in `META-INF/MANIFEST.MF` of a traditional JAR.

`module-info.java` **does not declare a main class using a `main` syntax in the module descriptor**. This information can be added by packaging tools, such as when creating a modular JAR with the appropriate main class option. When `ModuleMainClass` is absent, a module can still be run by **explicitly specifying the module and main class**:

```bash
java --module-path out -m com.example.catalog/com.example.catalog.Main
```

This is illustrative syntax; a complete runnable program with a different module name is guided in section 7. Not every `module-info.class` has `ModuleMainClass`, and class-file metadata should not be confused with application filenames or classpaths.

## 3. Nestmate Attributes: `private` Access Among Classes in the Same Nest

Before Java 11, when a nested class compiled by `javac` needed to access a `private` member of its enclosing class, the compiler often had to generate **synthetic access methods** (e.g., bridge methods named like `access$000`) so that bytecode could access it legally. Starting in Java 11, the JVM understands **nestmates**: classes belonging to **the same valid nest** are permitted to access each other's private members.

### 3.1. Two Complementary Attributes

- **`NestMembers`** resides in the class file of the **nest host**, containing the list of classes/interfaces **permitted to claim** membership in the nest.
- **`NestHost`** resides in the class file of a **member**, specifying the class acting as the host.
- The host **is itself a member** of the nest it manages and does not need to declare itself in the `NestMembers` list.
- A class file must not contain both **`NestHost` and `NestMembers`** simultaneously.

Java example:

```java
public class Vault {
    private int secret = 42;

    static class Reader {
        int read(Vault value) {
            return value.secret;
        }
    }
}
```

With Java 17 `javac`:

```text
Vault.class
  NestMembers:
    Vault$Reader

Vault$Reader.class
  NestHost:
    class Vault
```

This is a **diagram of the relevant lines**, not the full fixed output from `javap -v`. `Reader` can access `private int secret` of `Vault` thanks to the nest relationship verified by the JVM, rather than forcing the compiler to generate public/package-visible accessors.

### 3.2. Not Just Naming the Host on One Side

The JVM does not unconditionally trust any class that self-declares `NestHost: SomeHost`. When checking nest membership, classes must satisfy specification conditions such as **same runtime package**, and the host–member information is validated according to `NestHost`/`NestMembers` rules.

A **runtime package** is tied to the package name **and defining class loader**; two classes with the same `package com.example;` line but defined by different loaders do not necessarily belong to the same runtime package. Nestmates do not arbitrarily open `private` access across loaders/packages.

This mutual condition prevents an unintended class file from spoofing itself as a nestmate to read private fields of another class. If violated, access checks or class loading/linking may fail with errors such as `IllegalAccessError` or `IncompatibleClassChangeError`, depending on the exact case.

### 3.3. Difference from `InnerClasses` and `EnclosingMethod`

| Metadata | Question it answers |
| --- | --- |
| `InnerClasses` | How is this type declared/stored in a nested/member relationship? |
| `EnclosingMethod` | Which method or constructor encloses this local/anonymous type? |
| `NestHost` / `NestMembers` | Which classes are recognized by the JVM as being in the same nest for `private` access checks? |

Therefore, "a class named `Outer$Inner`" **does not automatically** have all private permissions; `$` is just a naming convention commonly used by compilers. In Java 11+, **valid nest metadata** is the foundation for private access between class files.

Reflection provides `Class.getNestHost()`, `getNestMembers()`, and `isNestmateOf(...)` to observe the result from the JVM's perspective, rather than merely reading name strings in source code.

## 4. `Record` Attribute: Metadata of Record Components

`record` is a language construct standardized in **Java 16**. Example:

```java
public record Point(int x, int y) {}
```

Compiling this to `Point.class` still produces an **ordinary class file** with a constructor, private final instance fields `x`, `y`, accessor methods `x()`, `y()`, and `equals`, `hashCode`, `toString` methods per the record contract.

The special part is having a **`Record` attribute** at the `ClassFile` level, representing the list of record components. `Record` does not contain "all methods" or the entire record source; it primarily describes the names/types and attributes accompanying each component.

### 4.1. Data of a `Record` Attribute

```text
Record_attribute
├── attribute_name_index
├── attribute_length
├── components_count
└── components[]
    ├── name_index
    ├── descriptor_index
    ├── attributes_count
    └── attributes[]   // e.g., Signature, annotations...
```

For `Point(int x, int y)`:

| Component | Name | JVM field descriptor |
| --- | --- | --- |
| 1 | `x` | `I` (int) |
| 2 | `y` | `I` (int) |

For `record User(String name, long id) {}`, the corresponding descriptors are `Ljava/lang/String;` and `J`. If a component has a generic type, a `Signature` attribute can supplement generic information alongside the erased descriptor.

A **record component** is a concept in the record's header. It corresponds to a field, accessor, and constructor parameter in the Java model, but it is **not** a `field_info` or `method_info`. That is why Java Reflection has a separate `getRecordComponents()` instead of forcing inference of components from all declared fields.

### 4.2. No `ACC_RECORD` in JVMS Java 17

In `access_flags` of a class file in JVMS 17, **there is no official `ACC_RECORD` bit**. A Java record class typically has `ACC_FINAL` per language rules and extends `java.lang.Record`; the **`Record` attribute** marks the record structure and components.

Distinctions to keep in mind:

- `ACC_FINAL` is not enough to conclude a class is a record; many ordinary final classes are not records.
- A class extending `java.lang.Record` and having a `Record` attribute in its class file matches how records are compiled; **do not infer a record solely from the filename or from `final`**.
- The methods `Class.isRecord()` and `getRecordComponents()` are the appropriate APIs to observe record metadata at runtime.
- Record component names/types reside in the attribute per the class-file contract, independent of whether `javac -g` is enabled to retain debug local variables.

### 4.3. What `Record` Does NOT Replace

`Record` does not "self-contain the bytecode" of the canonical constructor, accessors, `equals`, `hashCode`, or `toString`. The compiler still generates method/field structures; the JVM runtime/library coordinates execution using normal classes and bytecode.

On common JDKs, code generated by `javac` for record methods may use `invokedynamic` and `java.lang.runtime.ObjectMethods` to implement `equals`/`hashCode`/`toString`. This is an **observable codegen detail**, not a rule that "the `Record` attribute already contains the hash algorithm".

Not all annotations on a component are stored in the same location: depending on `@Target`, an annotation may apply to the record component, field, accessor, or constructor parameter per language rules. When inspecting, you must check the right metadata location.

## 5. `PermittedSubclasses`: Who Is Allowed to Inherit a Sealed Class/Interface?

`sealed` became a standard feature in **Java 17**. Example:

```java
public sealed interface Shape permits Circle, Rectangle {}

final class Circle implements Shape {}

final class Rectangle implements Shape {}
```

At the source level, `permits Circle, Rectangle` states that these two types may **directly** `implements Shape`. In the class file of `Shape`, the `PermittedSubclasses` metadata contains the corresponding `CONSTANT_Class_info` references.

```text
Shape.class
  PermittedSubclasses:
    Circle
    Rectangle
```

### 5.1. No `ACC_SEALED` Bit

The JVMS uses **the presence of `PermittedSubclasses`** on a class/interface to express the sealed boundary. There is no `ACC_SEALED` defined as a direct counterpart to the `sealed` modifier.

- `final class`: does not allow other classes to inherit, uses `ACC_FINAL`; must not simultaneously have `PermittedSubclasses`.
- `sealed class/interface`: permits a specific list of **direct subclasses/direct subinterfaces**, uses `PermittedSubclasses`.
- `non-sealed`: expresses reopening a branch so it is no longer restricted by the sealed parent; **there is no `ACC_NON_SEALED` bit**. The runtime represents the existing restrictions and modifiers using ordinary class structures.

A class permitted to directly inherit a sealed parent in **Java source code** must typically declare one of `final`, `sealed`, or `non-sealed` (records are implicitly final); those source rules and the final class bytecode may differ in how they are expressed.

### 5.2. Direct, Not All Descendants

Suppose:

```java
sealed interface Command permits ReadCommand, WriteCommand {}

non-sealed class ReadCommand implements Command {}

final class WriteCommand implements Command {}

final class SpecialRead extends ReadCommand {}
```

`PermittedSubclasses` of `Command` contains **ReadCommand** and **WriteCommand**, and **does not need** to contain `SpecialRead` because `SpecialRead` is only a grandchild inheriting through a `non-sealed` branch.

If a class not listed in `PermittedSubclasses` attempts to **directly** extend/implement the sealed parent, the JVM must reject it via class derivation/linking mechanisms. This is not merely a `javac` syntax check: the metadata helps enforce constraints even when the JVM loads class files compiled or modified outside the standard compiler.

### 5.3. Module and Package Constraints

For Java source:

- If the sealed parent belongs to a **named module**, direct permitted subclasses must be in the **same module**.
- If the sealed parent belongs to an **unnamed module**, direct permitted subclasses must be in the **same package**.
- Java source conditions also require valid direct subtypes, accessibility, and corresponding modifier characteristics.

At runtime, the JVM further checks direct relationships and the validity of class-loader/runtime-module/package per the JVMS. You cannot simply copy a name into `PermittedSubclasses` to bypass module/package boundaries or private access.

### 5.4. Reflection

For a sealed class/interface, `Class.isSealed()` indicates sealed status; `Class.getPermittedSubclasses()` returns a `Class<?>[]` array for the permitted classes at runtime. This is not a list of all objects or all indirect subclasses on the heap.

The **iteration order of the array** may reflect metadata/runtime, but the lesson should not rely on order as a business sorting rule. If name-stable results are needed, the application must sort them itself.

## 6. A Java 17 Source Illustrating Nestmate + Record + Sealed

Create the file **`ClassAttributeDemo.java`**:

```java
public class ClassAttributeDemo {

    private final String secret = "OK";

    static class Reader {
        static String read(ClassAttributeDemo owner) {
            return owner.secret;
        }
    }

    sealed interface Shape permits Point, Circle {}

    record Point(int x, int y) implements Shape {}

    record Circle(int radius) implements Shape {}

    public static void main(String[] args) {
        ClassAttributeDemo owner = new ClassAttributeDemo();
        Point point = new Point(2, 3);

        System.out.println("nestmate=" + Reader.read(owner));
        System.out.println("record=" + point);
        System.out.println("record-components=" +
                Point.class.getRecordComponents().length);
        System.out.println("sealed=" + Shape.class.isSealed());
        System.out.println("permitted=" +
                Shape.class.getPermittedSubclasses().length);
    }
}
```

Compile/run with **JDK 17+**:

```bash
javac ClassAttributeDemo.java
java ClassAttributeDemo
```

Exact stdout:

```text
nestmate=OK
record=Point[x=2, y=3]
record-components=2
sealed=true
permitted=2
```

**Why is this right?**

1. `Reader` is a nested class and can read `private String secret` of the enclosing class thanks to the nestmate relationship.
2. `Point` is a record with two components `x` and `y`; by default `toString()` represents them as `Point[x=2, y=3]`.
3. `Shape` is a sealed interface; the list of two direct permitted implementations is `Point` and `Circle`.
4. Both record implementations are implicitly final per record source rules, matching the direct subclass rule of a sealed parent.
5. The example does not use a module descriptor; the three metadata groups nest/record/sealed can appear in class files on the **classpath**, independent of whether the program has a named module.

### 6.1. Generated Class Files

A typical `javac` compiler will generate:

```text
ClassAttributeDemo.class
ClassAttributeDemo$Reader.class
ClassAttributeDemo$Shape.class
ClassAttributeDemo$Point.class
ClassAttributeDemo$Circle.class
```

The `$` sign is ordinary binary name notation for compiler-generated nested types, not an attribute. Exact files depend on the compiler, and the important attribute information lies **inside** the files.

Reading the metadata:

```bash
javap -v -p ClassAttributeDemo
javap -v -p 'ClassAttributeDemo$Reader'
javap -v -p 'ClassAttributeDemo$Point'
javap -v -p 'ClassAttributeDemo$Shape'
```

On PowerShell or POSIX shells, single quotes protect `$` from shell variables. In some environments, `javap` accepts both binary names and `.class` file paths. Here, binary names including `$` are used.

Expected findings:

| Inspect | Important metadata |
| --- | --- |
| `ClassAttributeDemo` | `NestMembers` listing the nested types placed in the nest by the compiler |
| `ClassAttributeDemo$Reader` | `NestHost: ClassAttributeDemo` |
| `ClassAttributeDemo$Point` | `Record` containing components `x:I` and `y:I`; `NestHost` for the nested type |
| `ClassAttributeDemo$Shape` | `PermittedSubclasses` listing `...$Point` and `...$Circle`; also has `NestHost` |
| `ClassAttributeDemo$Circle` | `Record` having component `radius:I` |

`javap` may additionally print the constant pool, `InnerClasses`, method code, bootstrap metadata, `SourceFile`, and much more. **Do not expect the output to contain only the lines listed in the table**; these are the key items to look for.

### 6.2. How Metadata Flow and Runtime Relate

```text
Java 17 source code
  │
  ├─ class Outer + nested Reader
  │     └─ ClassFile: NestMembers / NestHost
  │               └─ Used by JVM to check private access
  │
  ├─ record Point
  │     └─ ClassFile: Record (component names + descriptors)
  │               └─ Reflection reads getRecordComponents()
  │
  └─ sealed interface Shape
        └─ ClassFile: PermittedSubclasses
                  └─ JVM checks allowed direct subtypes
```

A class file can have **multiple attributes at once**. `Point` is both a **record** and a **nest member**, and is a direct subtype listed in `Shape`. `PermittedSubclasses` resides on the **parent `Shape`**, not on each record implementer just because it is permitted.

## 7. Standalone Java 17 Example: Creating `module-info.class`

To see the `Module*` group clearly, use a small separate project with two files:

```text
src/
├── module-info.java
└── demo/
    └── api/
        └── Hello.java
```

**`src/module-info.java`**:

```java
module demo.catalog {
    exports demo.api;
}
```

**`src/demo/api/Hello.java`**:

```java
package demo.api;

public class Hello {
    public static void main(String[] args) {
        System.out.println("module=" + Hello.class.getModule().getName());
    }
}
```

In the directory containing `src`, using JDK 17+:

```bash
javac -d out src/module-info.java src/demo/api/Hello.java
java --module-path out -m demo.catalog/demo.api.Hello
javap -v out/module-info.class
```

Stdout from **the `java` command**:

```text
module=demo.catalog
```

The `javap` command produces class-file analysis output, in which you look for `ACC_MODULE`, `Module`, `module-info`, the `demo.api` export, and the `java.base` dependency reflected by the compiler/module descriptor. The two commands `java` and `javap` do not have a fixed "combined stdout", so only the application run output is shown above.

**Detailed explanation:**

- `javac` generates `out/module-info.class` and `out/demo/api/Hello.class`.
- `module-info.class` carries information for module `demo.catalog` with the exported package `demo.api`.
- `Hello.class` is an ordinary class containing the `main` method; `module-info.class` does not contain the runnable program.
- `Hello.class.getModule().getName()` reflects the class's runtime module, returning `demo.catalog` in this run.
- `ModuleMainClass` is not required: the command `java -m demo.catalog/demo.api.Hello` already explicitly specifies the main class name.
- If `javap -v out/module-info.class` does not display `ModulePackages`, that does not mean the module has no packages; this attribute may be added by packaging tools.

This example does not require Maven/Gradle; the module path simply points to the **output directory** of a compiled module. For multi-module applications, directory/module-path layouts and `requires` clauses will be more complex.

## 8. Reading Class Files and Identifying Each Group with `javap`

`javap` is a tool bundled with the JDK that displays attributes in text form. A practical workflow:

1. Identify **the exact `.class` file** that the JVM/toolchain will use. A JAR may contain multiple versions of a class under `META-INF/versions/`.
2. Run `javap -v -p` on the specific class. `-v` prints attributes in addition, `-p` includes private members.
3. Check `major version` and `minor version` to know the class-file release. Classes with `Record` are officially defined from 60.0, `PermittedSubclasses` from 61.0.
4. Distinguish between the **attribute name** and **referenced data in the constant pool**: many `#123` values are indices, not stable IDs across two compilations.
5. If runtime verification is needed, use Reflection or try loading/running the program on a supported JDK; the class file is only one part of actual behavior.

Example of reading abbreviated output:

```text
ClassAttributeDemo$Shape
  major version: 61
  ...
  NestHost: class ClassAttributeDemo
  PermittedSubclasses:
    ClassAttributeDemo$Point
    ClassAttributeDemo$Circle
```

This is an **illustrative excerpt** to show how to locate attributes, and does not guarantee exact ordering/indentation/whitespace across every `javap` version.

### 8.1. Be Careful When Searching by String

If `javap` only prints the word "Record" in the **constant pool**, that is not necessarily proof of a **`Record` attribute** at the class level; the constant pool contains many strings and names used by code. Confirm it appears in the corresponding **attributes section** and has a components structure.

Similarly:

- The word `sealed` in source does not equate to an access flag named `ACC_SEALED`.
- A `ClassFile` having `InnerClasses` does not automatically guarantee nest access.
- The name `Module` appearing as a Java package/identifier name in bytecode does not mean the file is `module-info.class`.
- `Record` is not a "record object stored in the constant pool"; it is class-level metadata.

## 9. JDK Compatibility and Common Errors

| Situation | Reason | How to diagnose |
| --- | --- | --- |
| Running a Java 17 class (`major 61`) on a Java 11 JVM (up to 55) | Class-file version too new | `java -version`, `javap -v`, `UnsupportedClassVersionError` |
| Running a record class compiled on Java 16+ on an older JDK | Lacks format/language/runtime support for records | Check major version, toolchain, and `java.lang.Record` |
| Class file uses `PermittedSubclasses` incorrectly/invalidly | JVMS requires valid attribute structure and direct subtypes | `javap -v`, class generation, verification/linkage errors |
| Nested class accesses `private` but nest metadata does not match | Nest membership not verified by the JVM | Check `NestHost`, `NestMembers`, runtime package/loader |
| A class file has both `NestHost` and `NestMembers` | Violates format constraints | Fix class generator/instrumentation |
| `module-info.class` contains ordinary methods/fields | Violates `ACC_MODULE` constraints | Fix compiler/generator; inspect `module-info.class` |
| `ModulePackages` not seen after `javac` | May be an optional attribute added by packaging | Check final metadata in JAR/image |
| Reflection sees record components but code cannot find field by expected name | Component, field, and method are different structures | Use `getRecordComponents()`; inspect class fields/methods |
| `Class.isSealed()` is true but subtype list does not match expectations | Metadata stores **direct permitted subclasses**, not all descendants | Inspect `PermittedSubclasses` on parent |

**Important boundary:** these attributes help the JVM understand classes, but they do not make an older JDK suddenly understand new syntax or class formats. A program that needs to support Java 11 cannot keep Java 17 record/sealed bytecode as-is and just change a runtime flag. To support older runtimes, you must change the implementation and compile appropriately.

### 9.1. Attributes Unknown to Older Runtimes

The JVMS has rules for newly defined attributes: a JVM recognizes predefined attributes according to the version it supports. However, **do not infer** that an older JVM will safely ignore a new class just because of an unfamiliar attribute: it also checks the **major version**, class structure, and other constraints. With newer class formats, version errors typically occur **before** the program can proceed to process metadata.

Therefore, there is no valid workflow like "delete the `Record` line from a Java 17 file and change major to 55 to run on Java 11". Manually editing binary bytecode can corrupt the constant pool, constructor contract, references, and other elements.

## 10. Common Misconceptions

1. **"`record` is represented by the `ACC_RECORD` flag."** There is no such standard flag in JVMS 17; `Record` is a class-level attribute.
2. **"`sealed` is represented by the `ACC_SEALED` flag."** No; `PermittedSubclasses` on the sealed parent defines the set of direct permitted subtypes.
3. **"Every nested class is a nestmate just because its name contains `$`."** No; the runtime applies nest checks based on metadata and package/loader conditions.
4. **"`NestMembers` allows classes to inherit from each other."** No; it serves nest/private access relationships, not inheritance.
5. **"`PermittedSubclasses` lists all descendants."** No; the list is of permitted direct subtypes; a `non-sealed` branch can have further descendants.
6. **"`Record` contains the bytecode of `equals`, `hashCode`, and `toString`."** No; methods and code reside in the method/implementation structures.
7. **"`ModulePackages` is the list of all exported packages."** No; it can include internal non-exported packages as well.
8. **"`ModuleMainClass` must be present to run a module."** No; the Java launcher can accept an explicit main class.
9. **"`module-info.class` is an ordinary class that can instantiate objects."** No; `ACC_MODULE` comes with special structural constraints.
10. **"If the JVM sees a new attribute name, it will definitely load the new bytecode."** No; major/minor versions and the entire structure/specification must still be compatible.
11. **"`InnerClasses` is the only mechanism for private access of nested classes in Java 17."** No; `NestHost`/`NestMembers` is the foundation for nestmate checks.
12. **"Every class file of a Java program has all four groups of attributes."** No; only metadata applicable to the compiled structure is present.

## 11. Practice Exercises and Answers

**Question 1.** `module-info.class` reports the `ACC_MODULE` flag and has a `Module` attribute. Can it contain `public static void main`?

**Answer:** No. A module descriptor class file has a special structure with `methods_count = 0`. The application's main class, if any, is another class; the `ModuleMainClass` metadata does not create a `main` method either.

**Question 2.** `Outer$Inner.class` has `NestHost: Outer`, but class `Outer` does not accept that member. Does it automatically gain `private` access to `Outer`?

**Answer:** No. The JVM needs to validate a legitimate nest relationship (along with package/loader conditions). A one-sided declaration does not arbitrarily grant private access.

**Question 3.** In `record Book(String name, int pages) {}`, how many components does the `Record` attribute have and what are their descriptors?

**Answer:** Two components: `name` has descriptor `Ljava/lang/String;`, `pages` has descriptor `I`. The corresponding fields/accessors are described in other class-file structures.

**Question 4.** Sealed interface `Shape permits Circle, Rectangle` has a class `SpecialCircle extends Circle` on the `non-sealed Circle` branch. Must `PermittedSubclasses` of `Shape` list `SpecialCircle`?

**Answer:** No. Only the two direct permitted implementations `Circle` and `Rectangle`; `SpecialCircle` is not a direct subtype of `Shape`.

**Question 5.** If you need to read the list of record components via Reflection, should you choose `getDeclaredFields()` or `getRecordComponents()`?

**Answer:** Use `getRecordComponents()` to get **record components**. `getDeclaredFields()` returns field declarations, which is a different concept.

**Question 6.** Why can a file with `major version: 55` not rely on standard Java 17 `PermittedSubclasses` to guarantee sealed enforcement?

**Answer:** `PermittedSubclasses` is officially defined starting at class-file version **61.0** (Java 17). A JVM understanding major 55 (Java 11) does not have the corresponding sealed runtime contract.

**Question 7.** A `module-info.class` does not have `ModulePackages` but has `Module.exports[]`. Is this a compilation error?

**Answer:** Not necessarily. `ModulePackages` is supplementary metadata that may appear due to packaging; `Module` can contain exports information even without `ModulePackages` in the freshly compiled file.

## 12. Key Takeaways

- **`Module`** describes module relationships (requires/exports/opens/uses/provides), while **`ModulePackages`** and **`ModuleMainClass`** are supplementary module metadata. They reside in the `module-info.class` class-file descriptor with **`ACC_MODULE`**.
- **`NestHost` / `NestMembers`** help the JVM verify nestmates and allow controlled private access; they do not replace inheritance logic and do not arise automatically from `$` names.
- **`Record`** stores record components and related information; records still have actual fields/methods/constructors. **There is no standard `ACC_RECORD` in JVMS 17**.
- **`PermittedSubclasses`** allows the JVM to verify **direct subtypes** of a sealed class/interface; **there is no `ACC_SEALED`**.
- Read all of **class-file version, constant pool, access flags, and class-level attributes** accurately, then confirm behavior with `javap`/Reflection. That is how modern Java modifiers connect to the constraints the JVM actually understands.

### References

- [JVMS Java SE 17 — ClassFile structure (`4.1`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1).
- [JVMS Java SE 17 — Predefined attributes (`4.7`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7).
- [JVMS Java SE 17 — Module (`4.7.25`), ModulePackages (`4.7.26), ModuleMainClass (`4.7.27)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.25).
- [JVMS Java SE 17 — NestHost (`4.7.28), NestMembers (`4.7.29)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.28).
- [JVMS Java SE 17 — Record (`4.7.30`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.30).
- [JVMS Java SE 17 — PermittedSubclasses (`4.7.31`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.31).
- [JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
