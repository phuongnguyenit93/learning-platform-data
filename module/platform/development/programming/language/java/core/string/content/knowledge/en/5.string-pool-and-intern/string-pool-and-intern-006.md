# Distinguishing the String Pool from the Class File Constant Pool in Java

The **String Pool** and the **constant pool in a `.class` file** both contain the word "pool", yet they serve **two completely different roles**:

- **The class file constant pool** is a **data-structure table inside `.class` bytecode** describing the constants and symbolic links used by compiled Java code. Among them may be descriptions of a string literal, class names, method names, data types, numeric constants, and many other entries. It is not a store holding live `java.lang.String` objects at runtime.
- **The String Pool** is the mechanism for **sharing `String` objects by content while a program runs** (*string interning*). When two references point to the same interned `String`, they share the same identity. This pool relates to the Java runtime and `String.intern()`, not the `constant_pool` table written on disk.

A literal like `"java"` may be **described** by a `CONSTANT_String_info` entry in a class file; when the JVM uses that literal, the JVM obtains a **reference to an interned `String`**. That is the connection between the two concepts, not evidence that they are the same memory region or the same table.

## 1. Comparing the Two Concepts

| Criterion | Class file constant pool | String Pool (intern pool) |
|---|---|---|
| **Purpose** | Represents constants and symbolic references in the `.class` format | Shares `String` instances with equal content |
| **Primary phase** | Generated during compilation/bytecode transformation; read when the JVM loads and links classes | Used during program execution |
| **Contents** | Entries with types/tags such as `CONSTANT_Utf8`, `CONSTANT_String`, `CONSTANT_Class`, `CONSTANT_Methodref`, `CONSTANT_Integer`, `CONSTANT_InvokeDynamic`, etc. | Interned `String` objects (and the mapping mechanism to look them up) |
| **Scope of representation** | **Each class file** has its own table | The interning mechanism ensures literals/interned strings with equivalent content use a canonical reference under Java's contract |
| **Inspection/observation** | `javap -v ClassName`; shows `#n = …` entries and bytecode instructions referencing them | Observe literal behavior, `intern()`, and the `==` operator; `javap` does not print the entire runtime String Pool |
| **Relation to object identity** | An entry in `.class` is **not itself** a `String` object | Two references to the same `String` instance give `==` as `true` |
| **Contains all `String` objects?** | No; only metadata/constants of that class file | No; strings newly created with `new String(...)` or runtime operations are not automatically interned |
| **Contains all kinds of constants?** | Contains many kinds of information, not just strings | Only concerns interned `String` values |

**Do not confuse:** Some documentation also mentions the **run-time constant pool** in the JVM specification. This is a **per-class/interface** representation derived from the `.class` file's `constant_pool` when the class is created by the JVM, used for linking and execution (`JVMS `2.5.5`). It is also **not synonymous** with the String Pool used to intern `String` objects.

## 2. How Is a String Literal Stored in `.class`?

Suppose the source code uses:

```java
public class ClassPoolView {
    static final String MESSAGE = "Con" + "stant";

    public static String getMessage() {
        return "Constant";
    }
}
```

The Java compiler can recognize `"Con" + "stant"` as a **compile-time constant expression**. With standard `javac`, the value of `MESSAGE` is `"Constant"`, and the getter returns a literal with the same content.

In the class file format, the relevant structures are typically:

```text
CONSTANT_String_info
    tag          = 8   (CONSTANT_String)
    string_index = n   (points to CONSTANT_Utf8_info)

CONSTANT_Utf8_info
    tag    = 1   (CONSTANT_Utf8)
    length = ...
    bytes  = ... (content uses modified UTF-8)
```

- `CONSTANT_String_info` is an **indexed entry** in the table; it points to a `CONSTANT_Utf8_info` entry describing the string content. It does **not contain a pointer to a Java `String` object already sitting inside the class file**.
- `CONSTANT_Utf8_info` is a length-prefixed byte-array structure in the `.class` format. It stores **modified UTF-8 (MUTF-8)**, which differs from standard UTF-8 in certain cases (such as NUL and supplementary characters outside the BMP). Do not equate "the UTF-8 bytes in `.class`" with "how a `String` is stored in the heap."
- `CONSTANT_Utf8_info` also represents class names, method names, descriptors, and many items that are **not literals**. Seeing `Utf8 java` in `javap` output is **not enough** to conclude that a `String` object named `"java"` has been interned.
- `CONSTANT_String_info` is only a **description of a string that can be loaded by the JVM**. Upon resolution, the JVM can use a reference to an actual `String` according to interning rules.
- A class file contains many other entry types: class, field, method, method-type, integer, floating-point descriptions, and more. They do not belong to the String Pool.

### Inspecting with `javap`

Compile and inspect bytecode:

```bash
javac -encoding UTF-8 ClassPoolView.java
javap -v -c ClassPoolView
```

The output will include a **`Constant pool:`** section containing indexed `#n` entries. A **structural illustration** (the `#n` indices vary by compiler/JDK and class details; this is **not** fixed verbatim output):

```text
Constant pool:
   #a = String             #b             // Constant
   #b = Utf8               Constant
   ...
   #c = Utf8               MESSAGE
   ...
   #d = Utf8               ConstantValue
   ...

public static java.lang.String getMessage();
  Code:
     ...
     ldc      #a             // String Constant
     areturn
```

Here, `ldc` pushes a reference to the `String` corresponding to the string literal after the JVM processes the `CONSTANT_String` entry. The compiler may also attach a **`ConstantValue`** attribute for the `static final String MESSAGE` field because it is a constant variable. Exact entry ordering and additional entries depend on the generated bytecode.

Looking at `javap -v` is a good way to inspect the **class file constant pool**. However, that output alone cannot tell you every `String` currently interned at runtime, object addresses, how many objects are in the pool, or the JVM's storage algorithm.

## 3. Why Do Literals Share One `String` at Runtime?

The Java Language Specification requires **string literals** and strings that are values of **constant expressions** to be interned. When literals with the same content are used, they reference **the same `String` instance**; this rule applies even when literals reside in different classes.

Example:

```java
String a = "java";
String b = "java";
System.out.println(a == b); // true
```

Two literals with the same content share a reference. Even though each class file may have its own `CONSTANT_String` entry for `"java"`, those entries are **distinct metadata entries**; the runtime ensures the corresponding interned literal string is a single canonical object.

### The bridge from `CONSTANT_String` to `String`

A typical flow can be pictured as follows:

```text
Java source code: "java"
         |
         v
Compiled into class file
         |
         v
Class file constant_pool
  CONSTANT_String -> CONSTANT_Utf8 ("java")
         |
         v
JVM loads/links and uses the string constant
  (e.g., when executing the ldc instruction)
         |
         v
Resolves/obtains String reference
according to interning rules
         |
         v
Canonical java.lang.String object
         |
         v
Java instruction uses that reference
```

This is a **conceptual model**, not a statement of the exact instant the JVM creates the object. The JVM may optimize and resolve constants at times permitted by the specification; whether the JVM resolves eagerly or lazily does not change the observable rules for literals and `intern()`.

Similarly, the **run-time constant pool** may hold resolved values/references for a running class; that does not turn the entire run-time constant pool into the String Pool.

## 4. Three Concepts Often Loosely Called "Constant Pool"

| Exact name | When it exists/is used | How to understand it |
|---|---|---|
| **Class-file constant pool** (`constant_pool`) | Structure inside the `.class` format | Symbolic entries and constants written by the compiler or bytecode processor |
| **Run-time constant pool** | Per class/interface, created by the JVM when loading a class; used in linking/execution | Runtime representation derived from the class-file constant pool, which may include resolved values/targets |
| **String Pool / intern pool** | While the application runs and uses literals/`intern()` | Mechanism for sharing `java.lang.String` instances by content |

**The question "Where does the String Pool live?"** can be answered at two levels:

- **By Java's contract:** interned strings provide canonical references. The JLS does not require programmers to infer a specific physical memory address from the word "pool."
- **By implementation:** JVMs such as HotSpot manage interned data with dedicated runtime structures; organization, sizing, and management policies are JVM/GC topics and can vary across versions. Do not memorize rules like "the String Pool is definitely in PermGen" for modern Java, because PermGen was removed from HotSpot starting in Java 8.

More important than physical location is **the principle governing when two references point to the same object**: literals and constant expressions are interned; `intern()` obtains the canonical reference; strings created at runtime are not automatically interned.

## 5. Common Mistakes and How to Verify

| Claim | Problem | How to verify/understand properly |
|---|---|---|
| "The String Pool is the `Constant pool:` table in `javap`." | `javap` reads `.class` metadata, not canonical heap objects | Distinguish the file format from runtime `String` identity behavior |
| "`CONSTANT_Utf8_info` is a `String` object." | This entry is byte data inside a class file | Distinguish binary format descriptions from Java objects |
| "If a `String` is in the class-file constant pool, it must already be instantiated at compile time." | The compiler does not create runtime Java objects for `.class` files | The corresponding `String` object is obtained by the JVM when the constant is used at runtime |
| "Two classes have separate `CONSTANT_String` entries, so equal literals are two objects." | Separate metadata does not mean separate instances | Literals are interned by content |
| "`new String("x")` gets the exact interned object because `"x"` is interned." | `new` creates a separate object | Use `==` to observe identity, `equals` to compare content |
| "`static final` always produces a compile-time constant entry." | You must check whether the initializer is a constant expression | Compare `static final String A="x"` with `static final String B=new String("x")` |
| "If two strings are `equals`, then `==` must also be true." | Content and object identity are two different comparisons | Use `equals` for business logic |
| "`intern()` is always a performance optimization." | Interning also incurs lookup and pool-management cost; effectiveness depends on the dataset | Use only when benefits are established and verified by measurement |

## 6. Specification References

- [Java Language Specification, 3.10.5 — String Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.5): rules for string literals and interning.
- [Java Language Specification, 15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29): compile-time constant expressions.
- [Java Virtual Machine Specification, 4.4 — The Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4): structure of `CONSTANT_String_info` and `CONSTANT_Utf8_info`.
- [Java Virtual Machine Specification, 2.5.5 — Run-Time Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.5): the run-time constant pool concept.

**Remember:** `constant_pool` in `.class` is **a table describing constants and symbols**; the String Pool is **a runtime mechanism for sharing `String` objects**. A `CONSTANT_String_info` entry can be the starting point for the JVM to obtain an interned `String` reference, but the class file entry and the interned object are **two different things**. When inspecting, use `javap -v` for `.class` structure, and use `==`/`equals`/`intern()` in code to distinguish identity from content.