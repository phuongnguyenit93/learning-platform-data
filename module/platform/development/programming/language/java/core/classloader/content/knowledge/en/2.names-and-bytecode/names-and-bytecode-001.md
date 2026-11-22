# Binary Name, Canonical Name, and Internal Name of a Class in Java

> **Scope:** Java Core → ClassLoader → Names and Bytecode. This article explains the three representations of class/interface names across source code, Java Reflection, and the `.class` format, and how to use them properly when loading classes or reading bytecode. Examples run on Java 17+.

## 1. Why does the same class have multiple names?

Consider a member class inside `package demo`:

```java
package demo;

public class Outer {
    public static class Inner {}
}
```

The same type `Inner` can be referred to in several ways depending on the context:

| Context | String | Meaning |
| --- | --- | --- |
| Java source code / canonical name | `demo.Outer.Inner` | Dotted type notation, matching how it is referenced in Java source. |
| Binary name | `demo.Outer$Inner` | Class identifier after compilation; `$` joins the enclosing class and the member class. |
| JVM internal name | `demo/Outer$Inner` | Class name form used inside the class file structure and many parts of bytecode. |
| Field descriptor (reference type) | `Ldemo/Outer$Inner;` | Describes an object **type** in a descriptor; wraps the internal name with `L` and `;`. |
| Class file resource name | `demo/Outer$Inner.class` | Corresponding resource path, typically resolved via the classpath or module path. |

**No single character-replacement rule works in every case.** Specifically, the `.` between `Outer` and `Inner` in the canonical name becomes `$` in the binary name, while the `.` separating *package* segments becomes `/` in the internal name. `ClassLoader` takes binary names; bytecode analyzers typically require internal names or descriptors.

## 2. Canonical name

A canonical name is a type's name according to the Java language naming rules (JLS §6.7):

- Top-level class/interface: `java.util.Map`, `demo.Outer`.
- Member class/interface: `java.util.Map.Entry`, `demo.Outer.Inner`.
- Array type whose element type has a canonical name: `java.lang.String[]`, `demo.Outer.Inner[][]`.
- Primitive types: `int`, `boolean`; `void` also has its own representation via a `Class` object.

In Reflection, `Class.getCanonicalName()` returns the canonical name **or `null`** if the type has no canonical name. Local classes (declared inside a method or block) and anonymous classes normally **do not have a canonical name**; therefore, you must not assume the return value is always a string.

Canonical names are useful for human-readable explanations or Java code generation. They are not general-purpose arguments for `Class.forName`: for a member class, `demo.Outer.Inner` is the canonical name, not the binary name that this API requires.

## 3. Binary name

According to JLS §13.1, the binary name of ordinary class/interface declarations follows these rules:

| Declaration kind | Binary name example | Key takeaway |
| --- | --- | --- |
| Top-level | `demo.Outer` | Identical to the canonical name. |
| Member class/interface | `demo.Outer$Inner` | Combines the enclosing class's binary name, `$`, and the member's simple name. |
| Local class | Form `demo.Outer$1Local` | Includes compiler-generated digits; **do not rely on specific numbers**. |
| Anonymous class | Form `demo.Outer$1` | Has no simple/canonical name; numbering order is not a stable contract for code to depend on. |

`Class.getName()` returns the binary name for ordinary classes/interfaces that are neither arrays nor hidden classes. `Class.forName("demo.Outer$Inner")` or `ClassLoader.loadClass("demo.Outer$Inner")` uses the binary name to locate the class (different overloads have different initialization/loader behavior).

Additional notes:

- **Both static nested classes and non-static inner classes** use `$` in their binary name; the `static` keyword does not change the naming format.
- The `$` character can appear in valid Java identifiers. Therefore, **you cannot reliably determine nesting relationships simply by splitting the string at `$`**. When you need the declaration structure, use metadata/Reflection such as `getDeclaringClass()`, `getEnclosingClass()`, `isMemberClass()`, `isLocalClass()`, and `isAnonymousClass()`.
- Binary names of local/anonymous classes are compiler implementation details; editing source code can renumber `$1`, `$2` files. Avoid hardcoding them as APIs or persistent identifiers.
- A class also has a **runtime identity** tied to the class loader that defined it: two different loaders can define two distinct classes with the same binary name. A name alone does not guarantee that two `Class<?>` objects represent the same type.

## 4. JVM internal name

JVMS §4.2.1 specifies the *internal form* of a class/interface binary name: replace the dots **separating package components** with forward slashes `/`. The `$Inner` suffix of a member name stays intact:

```text
Binary name:   java.util.Map$Entry
Internal name: java/util/Map$Entry
```

In a `.class` file, `CONSTANT_Class_info` entries in the constant pool reference internal name strings such as `demo/Outer$Inner`. Type-operating instructions like `new`, `checkcast`, or `instanceof` also reference type representations through the constant pool. Seeing `/` when inspecting `javap -v` or using bytecode manipulation libraries is completely normal.

**Do not confuse an internal name with a descriptor:**

- Class internal name: `java/lang/String`.
- Field descriptor for a reference to that class: `Ljava/lang/String;`.
- Descriptor for `int`: `I` (there is no internal name for a primitive *class*).
- Descriptor for `String[]`: `[Ljava/lang/String;`.
- Method descriptor for a method taking `String` and `int` and returning `void`: `(Ljava/lang/String;I)V`.

In descriptors: `B` byte, `C` char, `D` double, `F` float, `I` int, `J` long, `S` short, `Z` boolean, `V` void (valid only as the return type of a method descriptor), `L<internal-name>;` for reference types, and each `[` adds one array dimension. Java generics are erased in ordinary descriptors: `List<String>` has field descriptor `Ljava/util/List;`; if generic type information is retained, it lives in separate `Signature` metadata.

You can visualize the progression of a member class as follows:

```text
Java source:          demo.Outer.Inner
                           |
                           | javac
                           v
Binary name:          demo.Outer$Inner
                           |
                           | JVM class-file encoding
                           v
Internal name:        demo/Outer$Inner
                           |
                           | field/method descriptor
                           v
Reference descriptor: Ldemo/Outer$Inner;
```

These are **context-specific representations**, not different kinds of classes.

## 5. Observing with a Java 17+ program

Create the file `demo/NamesDemo.java`:

```java
package demo;

public class NamesDemo {
    static class Member {}

    public static void main(String[] args) throws Exception {
        show("top", NamesDemo.class);
        show("member", Member.class);
        show("String[]", String[].class);
        show("int[][]", int[][].class);
        show("primitive", int.class);

        class Local {}
        Object anonymous = new Object() {};
        System.out.println("local canonical null: "
                + (Local.class.getCanonicalName() == null));
        System.out.println("anonymous simple empty: "
                + anonymous.getClass().getSimpleName().isEmpty());
        System.out.println("loaded member: "
                + Class.forName("demo.NamesDemo$Member").getName());
    }

    static void show(String label, Class<?> type) {
        System.out.println(label + ": name=" + type.getName()
                + ", canonical=" + type.getCanonicalName()
                + ", simple=" + type.getSimpleName()
                + ", type=" + type.getTypeName());
    }
}
```

Compile and run from the directory containing `demo/`:

```bash
javac -d out demo/NamesDemo.java
java -cp out demo.NamesDemo
```

Deterministic output on Java 17+:

```text
top: name=demo.NamesDemo, canonical=demo.NamesDemo, simple=NamesDemo, type=demo.NamesDemo
member: name=demo.NamesDemo$Member, canonical=demo.NamesDemo.Member, simple=Member, type=demo.NamesDemo$Member
String[]: name=[Ljava.lang.String;, canonical=java.lang.String[], simple=String[], type=java.lang.String[]
int[][]: name=[[I, canonical=int[][], simple=int[][], type=int[][]
primitive: name=int, canonical=int, simple=int, type=int
local canonical null: true
anonymous simple empty: true
loaded member: demo.NamesDemo$Member
```

Interpreting the `Class` methods:

| Method | Purpose | Notes |
| --- | --- | --- |
| `getName()` | Binary name for ordinary classes/interfaces; `[`-prefixed encoding for arrays; keyword name for primitives/void | **Not** always the binary name of an ordinary class. |
| `getCanonicalName()` | Canonical name representing the type in source code | May be `null` for local, anonymous, or other types without a canonical name. |
| `getSimpleName()` | Short name; empty string for anonymous classes | For arrays, appends `[]` to the element's simple name. |
| `getTypeName()` | More readable type name display for arrays | For `String[]`, returns `java.lang.String[]` rather than `[Ljava.lang.String;`. |
| `getPackageName()` | Package name of the type | Must not be used to infer member/local relationships via string splitting. |

Printing `getName()` for local/anonymous classes is omitted from the fixed output because the numeric suffix is compiler-generated; the program only checks the specified properties.

## 6. Arrays, primitives, and hidden classes

For **arrays**, `Class.getName()` uses a form close to a descriptor, except **the element class name uses dots**:

| Java type | `Class.getName()` | JVM field descriptor |
| --- | --- | --- |
| `int` | `int` | `I` |
| `int[]` | `[I` | `[I` |
| `int[][]` | `[[I` | `[[I` |
| `java.lang.String` | `java.lang.String` | `Ljava/lang/String;` |
| `java.lang.String[]` | `[Ljava.lang.String;` | `[Ljava/lang/String;` |
| `demo.Outer.Inner[][]` | `[[Ldemo.Outer$Inner;` | `[[Ldemo/Outer$Inner;` |

Thus, `name.replace('.', '/')` only converts **ordinary classes/interfaces** from binary form to internal form; for arrays, you are dealing with a different type representation. When building frameworks or bytecode tooling, use a proper descriptor parser rather than ad-hoc string concatenation or splitting.

For **primitives/void**, `int.class.getName()` returns `"int"` and `void.class.getName()` returns `"void"`; they cannot be loaded with `Class.forName("int")` or `Class.forName("void")`. There is no ordinary `int.class` or `void.class` file for a `ClassLoader` to locate.

Modern Java versions also introduce **hidden classes** (for example, created via `MethodHandles.Lookup.defineHiddenClass`). According to the Java 17 `Class.getName()` API, a hidden class name has the form `N/suffix`; this is not an ordinary binary name that `Class.forName` can look up. Do not assume that every string returned by `getName()` can be loaded by that name.

## 7. ClassLoader and resource paths: choosing the right name

Three common operations use three different forms:

```java
// Binary name, with $ for member classes:
Class<?> type = Class.forName("demo.NamesDemo$Member");

// ClassLoader accepts the binary name of an ordinary class:
Class<?> same = NamesDemo.class.getClassLoader()
        .loadClass("demo.NamesDemo$Member");

// .class resource name uses /, not the canonical name:
var url = NamesDemo.class.getClassLoader()
        .getResource("demo/NamesDemo$Member.class");
```

The snippet above **illustrates the API calls when `NamesDemo` is on the classpath**, not a standalone program. `type == same` is `true` if both calls return the same class from the same defining loader; if loader selection differs, you cannot infer equality from the name alone. `getResource` may return `null` if the resource is not found or is inaccessible under a given configuration or module setup.

Several rules to keep distinct:

1. `Class.forName(String)` takes a binary name for ordinary classes; a member's canonical name such as `"demo.NamesDemo.Member"` will not load `Member` in the example. For arrays, the API also accepts the array name format returned by `Class.getName()`, such as `"[I"` or `"[Ljava.lang.String;"`; it does not accept Java syntax `"java.lang.String[]"`.
2. `ClassLoader.loadClass(String)` takes the binary name of a class/interface to load, not the path `demo/NamesDemo$Member.class` or the internal name `demo/NamesDemo$Member`. Do not assume it handles array descriptors the way `Class.forName` does.
3. `ClassLoader.getResource("demo/NamesDemo$Member.class")` uses a `/`-separated path **without a leading `/`**; by contrast, `NamesDemo.class.getResource("/demo/NamesDemo$Member.class")` accepts an absolute path per the `Class` API.
4. Having `loadClass` find a class while `getResource` returns no file can happen with custom loaders, dynamically generated classes, or module configurations. Class loading and resource lookup are two separate tasks.

## 8. Inspecting names directly in bytecode

Using the files compiled in section 5, run:

```bash
javap -v -classpath out 'demo.NamesDemo$Member'
```

The command above uses Unix shell quoting to prevent `$` from being expanded. On Windows PowerShell, single quotes work the same way. Look for entries such as:

```text
this_class: ... // demo/NamesDemo$Member
```

The line above is an **abbreviated illustrative sample**, because constant pool indices depend on bytecode contents and compiler version. Try running `javap -v -classpath out demo.NamesDemo` next to inspect `InnerClasses`, `EnclosingMethod` (if present), and descriptor strings in the constant pool. The `javap` command line accepts class names using the tool's syntax, while annotations/comments in its output may display internal names.

The relationship between file names and class names also aids debugging:

- Source: `demo/NamesDemo.java`.
- Top-level class output: `out/demo/NamesDemo.class`.
- Member class output: `out/demo/NamesDemo$Member.class`.
- Resource path: `demo/NamesDemo$Member.class`.
- String for `Class.forName`: `demo.NamesDemo$Member`.

Physical paths or JAR/module layouts depend on the build setup and class loader, so do not equate file names with runtime type identity.

## 9. Common errors and how to resolve them

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `ClassNotFoundException` when using `"demo.Outer.Inner"` | Passing a member's canonical name instead of its binary name | Use `"demo.Outer$Inner"` and verify the class is on the classpath/module path. |
| Resource `demo.Outer$Inner.class` not found | Resource names must use `/` | Pass `demo/Outer$Inner.class` to `ClassLoader.getResource`. |
| Descriptor `Ljava/lang/String;` rejected by `loadClass` | A descriptor is not a binary name | Pass `java.lang.String` to ordinary class-loading APIs. |
| `getCanonicalName()` causes `NullPointerException` on string operations | Local/anonymous/hidden classes may have no canonical name | Check for `null`, or use a naming API suited to the purpose. |
| Replacing `$` with `.` breaks class loading | Splitting a binary name into source-style syntax that loaders do not understand | Keep binary names for class loading; use canonical names only for display. |
| Two classes print the same `getName()` but casting fails | Different defining class loaders | Inspect `clazz.getClassLoader()` and the runtime identity of each `Class<?>`. |
| `NoClassDefFoundError` during linking/loading | Possibly a missing transitive dependency or class verification/initialization failure; a `/` alone is not sufficient evidence | Inspect the root cause (`Caused by`), classpath/module path, loader, and the name reported by the JVM. |

**Practical debugging workflow:** determine whether the API expects a *binary name*, *internal name*, *descriptor*, or *resource path* → check `getName()`/`getCanonicalName()` and the class's loader → run `javap -v` to confirm the internal name/descriptor → then inspect the classpath, module path, access permissions, and class loader.

## 10. Self-check

1. What are the binary name, internal name, and descriptor of a member interface `com.acme.Api.Response`?  
   **Answer:** `com.acme.Api$Response`; `com/acme/Api$Response`; `Lcom/acme/Api$Response;`.
2. How do `String[][].class.getName()` and the field descriptor of this type differ?  
   **Answer:** `[[Ljava.lang.String;` versus `[[Ljava/lang/String;`.
3. What must `Local.class.getCanonicalName()` return when `Local` is declared inside a method?  
   **Answer:** `null`. `Local.class.getName()` still has a compiler-generated name, though you should not rely on its numbering.
4. Why does `Class.forName("java.util.Map.Entry")` fail to load the `Entry` member interface?  
   **Answer:** That string is the canonical name; the API requires the binary name `java.util.Map$Entry`.
5. If two class loaders load the same binary name, must they produce a single class?  
   **Answer:** No; runtime class identity also depends on the defining loader.

## 11. Authoritative references

- [JLS §6.7 — Fully Qualified Names and Canonical Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.7): canonical naming rules.
- [JLS §13.1 — The Form of a Binary](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1): definition of binary names and class file structure.
- [JVMS §4.2.1 — Binary Class and Interface Names](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.2.1): internal name representation.
- [JVMS §4.3 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): field and method descriptors.
- [Java SE 17 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName`, `getCanonicalName`, `getSimpleName`, and `getTypeName`.
