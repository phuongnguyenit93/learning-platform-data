# Reading the Constant Pool and Class Attributes for Output Validation

When checking Java compilation outputs, reading only `.java` source code or running a quick test program is not enough to know **what the compiler actually wrote into `.class`**. A class file contains the **constant pool** (a table of constants and symbolic references), version information, class/field/method descriptors, access flags, bytecode, and many **attributes** carrying metadata for the verifier, runtime, reflection, and analysis tools. Understanding them well enough helps detect wrong Java targets, missing annotations, incorrect generic signatures, bytecode referencing unexpected dependencies, or required attributes of `record`, `sealed`, and `invokedynamic`.

The lesson's goal is **output validation**, not rewriting a complete reader for the entire Java Class File Format. We use the `javap` tool of JDK 17+, how to cross-check against the Java Virtual Machine Specification (JVMS), self-compiled examples, and verifiable PASS/FAIL criteria. **Do not draw conclusions based on index `#n` or the presence of one specific bytecode instruction if that is merely an implementation choice of `javac`.**

## 1. Path from Source to Data Needing Validation

~~~text
Java Source + --release / -g / -parameters / processors
                         │
                         ▼
                 javac compilation
                         │
                         ▼
                   class file (.class)
           ┌─────────────┼─────────────┐
           │             │             │
           ▼             ▼             ▼
     Header/version  Constant pool  Class/field/method
                                   + attributes
           │             │             │
           └─────────────┼─────────────┘
                         ▼
         javap -v / -c / -s / -p / -l
                         │
                         ▼
      Compare policy: target, API, metadata,
       dependency, access, code, module, ...
                         │
                    PASS or FAIL
~~~

The `javap` command **analyzes class files statically** and prints information; it does not execute `main`, does not prove all runtime dependencies are present, and does not show how the JIT optimized native machine code. When the goal is running business logic correctly, **additional** unit/integration/runtime tests are needed rather than replacing them with constant-pool inspection.

Five pragmatic questions:

1. Does the file have the right **major/minor version** for the target Java version?
2. Does the class have the right **binary name, superclass, interfaces, access flags, and method/field descriptors**?
3. Are the expected **symbolic references** to classes/methods/fields and bootstrap handles present?
4. Are the **attributes** needed for reflection, generic tooling, records, sealed types, debug, or annotation processing in the right places?
5. Do the results comply with the application's **release policy**, rather than merely differing in `javap` text from another build?

## 2. ClassFile: Overall Structure of a .class File

Overview structure per JVMS §4.1:

~~~text
ClassFile {
    u4 magic;
    u2 minor_version;
    u2 major_version;
    u2 constant_pool_count;
    cp_info constant_pool[constant_pool_count - 1];
    u2 access_flags;
    u2 this_class;
    u2 super_class;
    u2 interfaces_count;
    u2 interfaces[interfaces_count];
    u2 fields_count;
    field_info fields[fields_count];
    u2 methods_count;
    method_info methods[methods_count];
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

This is a **structural model from the specification**, not a runnable `.java` file. `u1`, `u2`, `u4` are unsigned quantities of 1, 2, and 4 bytes respectively; multi-byte values in a class file are **big-endian**. Magic is `0xCAFEBABE`. `constant_pool_count` includes a reserved slot at index 0; valid constant pool indices normally start at 1.

**Distinguishing data layers:**

| Component | Interpretation During Validation |
| --- | --- |
| `magic` and version | Valid class file at recognition level, minimum JVM target regarding format |
| `constant_pool` | Symbolic references, literals, and linkage info for bytecode/metadata |
| `access_flags` | Properties such as `public`, `final`, `interface`, `abstract`; interpreted by structure kind |
| `this_class`, `super_class`, `interfaces` | Identity and type hierarchy at the binary level |
| `fields` and `methods` | Members with names, descriptors, flags, and individual attributes |
| `attributes` | Metadata/bytecode extensions per location, format, and attribute-specific requirements |

Do not confuse the **constant pool in the file** with the **runtime constant pool** belonging to the JVM's class-loading mechanism; they are related yet live at different stages. Reading `javap -v` shows class-file information before runtime performs resolution.

## 3. Complete Java 17+ Example to Inspect Constant Pool and Attributes

Create file **`VerifySample.java`**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Objects;

@Retention(RetentionPolicy.RUNTIME)
@interface Reviewed {
    String value();
}

@Reviewed("class-level")
public final class VerifySample<T extends Number> {
    public static final int LIMIT = 42;
    private final T value;

    public VerifySample(T value) {
        this.value = Objects.requireNonNull(value);
    }

    public String label(String prefix) {
        return prefix + ":" + value;
    }

    public static void main(String[] args) {
        VerifySample<Integer> sample = new VerifySample<>(7);
        System.out.println(sample.label("n"));
    }
}
~~~

Class `VerifySample` deliberately uses: compile-time constant `LIMIT`, generic field `T extends Number`, generic-aware method and dynamic string concatenation, an annotation with `RUNTIME` retention, a constructor, and class/method/field access flags. Source consists of one file with two top-level types; the `Reviewed` annotation type is not `public`, so this file organization is valid.

Compile from the directory containing source with JDK 17+:

~~~bash
mkdir -p out
javac --release 17 -g -parameters -d out VerifySample.java
java -cp out VerifySample
~~~

Stdout of the `java` command:

~~~text
n:7
~~~

Normal compilation output has `out/VerifySample.class` and `out/Reviewed.class`. Even with both classes in one source file, **each top-level type is a separate class file**. Because source declares no `package`, the classes sit directly under `out`. If placing `package demo;`, class names and paths change accordingly.

Inspect the compiled class:

~~~bash
javap -classpath out -v -p -c -s VerifySample
~~~

The options have specific purposes:

- `-classpath out`: ensures `javap` finds the exact class file just compiled.
- `-v` / `-verbose`: prints extensive class-file info, including constant pool, version, access flags, and attributes.
- `-p` / `-private`: displays private members too; if omitted, `value` may not appear.
- `-c`: disassembles instructions in the `Code` attribute of methods with code.
- `-s`: prints internal **descriptors** of fields/methods, helping spot erased types.
- `-l`: another option to print line/local variable tables; with `-v`, much debug info is already shown.

**Do not match the entire printed text verbatim across JDKs.** Format names, comments, entry counts, constant pool order, and how the compiler lowers string concatenation can differ. Verify **meaningful attributes according to requirements**.

## 4. How to Read the Constant Pool in javap -v

A short excerpt for **format illustration**:

~~~text
Constant pool:
   #1 = Methodref          #2.#3     // java/lang/Object."<init>":()V
   #2 = Class              #4        // java/lang/Object
   #3 = NameAndType        #5:#6     // "<init>":()V
   #4 = Utf8               java/lang/Object
   #5 = Utf8               <init>
   #6 = Utf8               ()V
~~~

Indices `#1` to `#6` here are **not a guaranteed output** of `VerifySample.class`. A real `javap` command yields a richer set of entries and the order may differ. The goal is learning how to trace **references from one entry to other entries**.

Interpretation:

1. `Methodref` describes a reference to a method or constructor.
2. It points to a `Class` containing the class name in JVM internal form `java/lang/Object`.
3. It also points to `NameAndType`, representing the **name** and **descriptor** pair of the method.
4. `Utf8` holds the name or descriptor string encoded in class-file format.
5. Comments after `//` are human-readable annotations generated by `javap`; they are not verbatim data stored in a comment field of the constant pool.

For example, `()V` means a method with **no parameters**, returning **void**. `<init>` is the special name of an instance initialization method. This link helps verify **which symbol** a constructor/method call in bytecode references, not just a short Java name.

### Key Entry Table

| Form in `javap` | JVMS Constant | When to Inspect? |
| --- | --- | --- |
| `Utf8` | `CONSTANT_Utf8` | Names, descriptors, attribute names, and many text literals |
| `Integer`, `Float` | `CONSTANT_Integer`, `CONSTANT_Float` | 32-bit integer / 32-bit float literal values |
| `Long`, `Double` | `CONSTANT_Long`, `CONSTANT_Double` | 64-bit numeric literals; occupy two pool indices |
| `Class` | `CONSTANT_Class` | Symbolic reference to class/interface/array type |
| `String` | `CONSTANT_String` | String literal used via constant pool |
| `Fieldref` | `CONSTANT_Fieldref` | Field reference |
| `Methodref` | `CONSTANT_Methodref` | Class method reference |
| `InterfaceMethodref` | `CONSTANT_InterfaceMethodref` | Interface method reference |
| `NameAndType` | `CONSTANT_NameAndType` | Member name and paired descriptor |
| `MethodHandle` | `CONSTANT_MethodHandle` | Handle with reference kind/target |
| `MethodType` | `CONSTANT_MethodType` | Method type description |
| `InvokeDynamic` | `CONSTANT_InvokeDynamic` | Dynamic call site, linked via bootstrap method |
| `Dynamic` | `CONSTANT_Dynamic` | Dynamically computed constant |
| `Module`, `Package` | `CONSTANT_Module`, `CONSTANT_Package` | Module descriptors and package names when applicable |

**Do not interpret `String` in the pool as an already-allocated String instance in memory before running.** The constant pool holds class-file info; resolution, interning, initialization, or related bootstrapping are handled by the JVM at runtime per appropriate rules.

**Long/Double occupy two slots:** after a `CONSTANT_Long` or `CONSTANT_Double` entry, the very next index is not an independent valid entry. Therefore, when writing a custom parser, do not assume exactly one valid entry exists at every `#n` from 1 to `constant_pool_count - 1`.

**Utf8 uses modified UTF-8** per the Class File Format; do not assume identical byte encoding as `StandardCharsets.UTF_8` in every case. When building a binary parser, follow the specification; reading text with `javap` is usually simpler, safer, and sufficient for validation goals.

## 5. Symbolic References, Descriptors, and Type Names

A `Fieldref` or `Methodref` **does not contain a running Java object**. It represents a **symbolic reference**: owning class, member name, and descriptor. The JVM can perform resolution at load/link time or when the instruction actually needs it, according to the corresponding rules.

Slash `/` and dot `.` have different meanings:

- Java source: `java.lang.String`.
- Common JVM internal name: `java/lang/String`.
- Descriptor of a reference type: `Ljava/lang/String;`.
- Descriptor of array of String: `[Ljava/lang/String;`.

Basic descriptor table:

| Java Type | Field Descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

`V` represents `void` **only when used as a method return descriptor**, never as a field type.

A method descriptor consists of **parameter types inside parentheses** followed by the return type:

~~~text
()V
(I)J
(Ljava/lang/String;I)Z
([Ljava/lang/String;)V
~~~

The examples mean respectively: no parameters, returns void; takes int, returns long; takes String and int, returns boolean; takes String array, returns void.

### Generic Types Do Not Reside Intact in Descriptors

In `VerifySample<T extends Number>`:

~~~java
private final T value;
public String label(String prefix) { ... }
~~~

Field `value` will have a descriptor matching the type erasure of `T`, here `Ljava/lang/Number;`, **not `TT;` as a separate runtime descriptor**. Generic information for `T` can reside in the **`Signature` attribute**.

Therefore:

- **Descriptor** serves JVM linkage and binary shape of fields/methods.
- **Signature** supplements generic information specified for tools such as reflection/generic-aware tooling.
- Generic metadata does not make the JVM automatically verify every element of `List<String>` is a String at runtime; erasure must still be understood properly.

Do not compare generic signatures by looking solely at `descriptor:`, because it may only show post-erasure types.

## 6. Reading Access Flags and Class Structure

In `javap -v`, the header section usually has:

~~~text
major version: 61
flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER
this_class: #...                         // VerifySample
super_class: #...                        // java/lang/Object
~~~

This is a **conceptual illustration**; `#...` are not real indices and the flags line may vary in display by compiler/target. Normal Java 17 class files have major 61, minor 0. Class flags differ from method/field flags.

Information to verify:

- `ACC_PUBLIC`/`ACC_PRIVATE`/`ACC_PROTECTED`: access levels on applicable structures.
- `ACC_FINAL`, `ACC_ABSTRACT`, `ACC_INTERFACE`, `ACC_ANNOTATION`, `ACC_ENUM`, `ACC_MODULE`: class/interface/annotation/module properties.
- `ACC_STATIC`, `ACC_SYNCHRONIZED`, `ACC_NATIVE`, `ACC_BRIDGE`, `ACC_VARARGS`: different meanings on members/methods.
- `ACC_SYNTHETIC` or `Synthetic` attribute: compiler-generated elements not written directly in source, depending on version/mechanism.
- `this_class`, `super_class`, `interfaces`: binary identity/type hierarchy.

**Do not interpret every flag identically everywhere.** For example, `ACC_SUPER` applies to class files per JVMS; it does not mean the class is the Java `super` keyword. An interface does not have the same class hierarchy relations as a concrete class. Module descriptors in `module-info.class` have their own rules.

If you suspect a public API changed, compare **lists of fields/methods, names, descriptors, and access flags** before examining generic signatures or annotation metadata. Many `NoSuchMethodError` bugs stem from binary signatures/descriptors no longer matching compiled calls.

## 7. What Are Attributes and Where Do They Reside?

`attribute_info` has a common header:

~~~text
attribute_info {
    u2 attribute_name_index;
    u4 attribute_length;
    u1 info[attribute_length];
}
~~~

`attribute_name_index` is an index pointing to a `CONSTANT_Utf8` carrying the **attribute name**. `attribute_length` counts the **number of bytes of the info payload**, excluding the six header bytes. The `info` contents of each attribute must be parsed per its individual specification; no single generic parser can understand every attribute merely by knowing its name.

Attributes can appear on:

- **ClassFile** — class-level metadata such as `SourceFile`, `Signature`, `BootstrapMethods`, `Record`, `PermittedSubclasses`.
- **field_info** — such as `ConstantValue`, `Signature`, runtime annotations on fields.
- **method_info** — such as `Code`, `Exceptions`, `Signature`, `MethodParameters`, and annotation metadata.
- **Code_attribute** — attributes nested inside code such as `LineNumberTable`, `LocalVariableTable`, `StackMapTable`.
- **record_component_info** — component metadata defined for records.

An attribute with a valid name yet placed in the wrong location, violating length/constraints, or containing invalid pool indices does not become valid just because `javap` recognizes the name string. To validate formally, follow the target JVMS version.

## 8. The Most Important Attributes for Output Validation

| Attribute | Where to Read It and What Does It Serve? |
| --- | --- |
| `Code` | Bytecode and method execution info; does not apply as a code body for abstract/native methods |
| `ConstantValue` | Special initialization value for `static` constant fields under JVMS conditions |
| `Signature` | Generic signature of class/field/method when metadata beyond descriptor is needed |
| `Exceptions` | Checked/declared exceptions listed in the method declaration |
| `SourceFile` | Source file name attached to the class; not a reliable full workspace path |
| `LineNumberTable` | Maps bytecode offsets to source lines, supporting stack traces/debugging |
| `LocalVariableTable` | Metadata about local variables when generated by the compiler |
| `LocalVariableTypeTable` | Generic local-variable metadata in applicable cases |
| `MethodParameters` | Names/flags of formal parameters at the class-file level |
| `RuntimeVisibleAnnotations` | Annotations eligible to be seen by runtime reflection |
| `RuntimeInvisibleAnnotations` | Annotations stored in the class yet not runtime-visible |
| `AnnotationDefault` | Default value of an element in an annotation type declaration |
| `BootstrapMethods` | Bootstrap parameters for `invokedynamic` and `CONSTANT_Dynamic` |
| `StackMapTable` | Verification type frames, supporting class verification |
| `InnerClasses` | Nested/member class relationship metadata per spec |
| `EnclosingMethod` | Enclosing method/class of local/anonymous classes when needed |
| `NestHost`, `NestMembers` | Nest-based access control (Java 11+) |
| `Record` | Record components metadata (Java 16+) |
| `PermittedSubclasses` | List of permitted subtypes of a sealed class/interface (Java 17+) |
| `Module`, `ModulePackages`, `ModuleMainClass` | Metadata in `module-info.class` per individual locations/constraints |

The **absence** of an attribute **is not always an error**:

- A method with no useful local variables or compiled without requesting debug vars may lack `LocalVariableTable`.
- Without dynamic call sites/constants, `BootstrapMethods` is unnecessary.
- Without `RUNTIME` annotations, `RuntimeVisibleAnnotations` is unnecessary.
- An ordinary class that is not a record will not have `Record`.
- A class not participating in an appropriate sealed hierarchy will not have `PermittedSubclasses`.
- A method not needing additionally encoded stack map frames may not have `StackMapTable` printed as learners might expect.

**Validate conditionally** based on class kind and source/target/options; do not require every `.class` file to contain the exact same set of attributes.

## 9. Verifying ConstantValue and Compile-Time Constants

In the sample source:

~~~java
public static final int LIMIT = 42;
~~~

`javac` can emit the `ConstantValue` attribute for field `LIMIT` to represent a constant variable determined at compile time. When inspecting:

~~~bash
javap -classpath out -p -v VerifySample
~~~

look for the `LIMIT` field section with an excerpt equivalent to:

~~~text
descriptor: I
flags: (0x0019) ACC_PUBLIC, ACC_STATIC, ACC_FINAL
ConstantValue: int 42
~~~

These are **properties to check**; surrounding lines/ordering depend on `javap`. `ConstantValue` differs from the `Code` of a class initializer. Not **every `static final` field** has `ConstantValue`: for example, a field initialized with `new Object()` requires runtime logic and cannot be represented as a primitive/String constant under the corresponding rules.

Consequence for binary compatibility: primitive/String compile-time constant values can be inlined into consumer classes at compile time, so changing a constant in a library without rebuilding consumers can produce “old value” behavior. When validating a release, besides inspecting `ConstantValue`, consider rebuilding consumers depending on constants.

## 10. Verifying the Code Attribute and Method Bytecode

A `method_info` can contain a `Code` attribute with:

~~~text
Code {
    max_stack
    max_locals
    code_length
    code[code_length]
    exception_table
    attributes
}
~~~

The template above describes **main fields** of `Code_attribute`, not a complete source definition for compilation. `Code` stores JVM bytecode (not CPU assembly), operand stack limits, local variable slots, exception handlers, and nested attributes.

With source:

~~~java
public String label(String prefix) {
    return prefix + ":" + value;
}
~~~

Java 17 `javac` normally uses `invokedynamic` for dynamic string concatenation under the JEP 280 mechanism. `javap -c -v` may print the `invokedynamic` instruction in `label` and an `InvokeDynamic` entry in the constant pool. However, this is a **code generation choice of a specific compiler**; the mandatory business outcome is that the method concatenates values properly, not that every compiler emits the exact same instruction sequence.

When analyzing:

1. Identify the right method by **name + descriptor**.
2. Read `Code` and instruction offsets.
3. Track operand stack, local slots, and symbolic references to fields/methods.
4. Check exception table and handlers if source has try/catch/finally.
5. When `invokedynamic` is present, inspect `BootstrapMethods`/method handles.
6. Do not infer JIT inlining or executed machine code from `javap` printouts.

`max_stack`/`max_locals` reflect limits for JVM bytecode in the method; they are **not** the number of Java objects on the heap, and do not directly prove good/bad performance.

### Exceptions Is Not the Same as the Exception Table

- The `Exceptions` attribute on `method_info` records exception classes that the method **declares in `throws`** per format.
- The **exception table** sits inside `Code`, describing protected bytecode regions and handler offsets.
- A method can throw unchecked exceptions even without an `Exceptions` attribute; do not search for `NullPointerException` in `Exceptions` and conclude “the method never throws NPE”.

## 11. Verifying Parameter Names, Source Lines, and Local Variables

Which exact debug attributes appear depends on compiler flags:

~~~bash
javac --release 17 -g -parameters -d out VerifySample.java
javap -classpath out -l -p VerifySample
javap -classpath out -v -p VerifySample
~~~

`-g` requests generating debug information including source lines and local variables per compiler-supported levels. `-parameters` requests formal parameter name metadata to reflect via core reflection in valid cases; results normally relate to the `MethodParameters` attribute.

Distinguish three pieces of information:

| Information | Attribute | Used For |
| --- | --- | --- |
| Source line mapping | `LineNumberTable` | Stack traces, breakpoints, mapping bytecode ↔ lines |
| Local variable names/ranges | `LocalVariableTable` | Debuggers displaying local slots/live ranges |
| Formal parameter names/flags | `MethodParameters` | Reflection on parameter names, analyzing parameter metadata |

**`MethodParameters` is not synonymous with `LocalVariableTable`**. When parameter names are needed via reflection (e.g., frameworks binding by parameter names), enabling only `-g` does not guarantee equivalence with `-parameters`. Conversely, `-parameters` does not require full local debug information for the method.

A class file that has been shrunk/obfuscated or built with different options may lose/alter metadata even though code still runs; therefore validation must apply to the **final released artifact**, not only temporary `.class` files before packaging.

## 12. Verifying Generics via Signature

Generics in Java largely use **erasure**, so descriptors usually do not retain full type parameters. In `VerifySample<T extends Number>`, signals to inspect:

- Class has `Signature` describing type parameter `T` and bound `Number`.
- Field `value` has a descriptor matching erasure (`Ljava/lang/Number;`).
- Field `value` may have `Signature` expressing a reference to type variable `T`.
- Method code operates on JVM reference types matching erasure.

Command:

~~~bash
javap -classpath out -p -s -v VerifySample
~~~

Be careful **not to confuse**:

~~~text
descriptor: Ljava/lang/Number;
Signature: ... TT; ...
~~~

The two lines are **illustrative in meaning**, not an exact transcript of full comments or pool indices. `TT;` in signature grammar represents **type variable T**, not an ordinary JVM field descriptor.

If checking a public generic API, verify **both descriptor and Signature**. Descriptor is required for binary linkage; Signature helps generic-aware tools understand type parameters. A class file with a malformed or inconsistent Signature can cause reflection/generic tooling to fail even when some bytecode still appears loadable.

**Do not infer** that the class file contains a separate runtime specialization for `VerifySample<Integer>` just because source has a generic type argument. That is not how normal erasure works in Java.

## 13. Verifying Annotation Retention

In the sample source, annotation type:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@interface Reviewed {
    String value();
}
~~~

and using class:

~~~java
@Reviewed("class-level")
public final class VerifySample<T extends Number> { ... }
~~~

Because retention is `RUNTIME`, `VerifySample.class` must contain appropriate runtime-visible annotation metadata, observable via `javap -v` in `RuntimeVisibleAnnotations`. Do not merely search for the literal `"class-level"` in the constant pool and conclude the annotation definitely exists; the string could appear for other reasons.

Try cross-checking with reflection code — file **`AnnotationCheck.java`**:

~~~java
public class AnnotationCheck {
    public static void main(String[] args) {
        Reviewed a = VerifySample.class.getAnnotation(Reviewed.class);
        System.out.println(a == null ? "missing" : a.value());
    }
}
~~~

After building `VerifySample.java`:

~~~bash
javac --release 17 -cp out -d out AnnotationCheck.java
java -cp out AnnotationCheck
~~~

Exact stdout:

~~~text
class-level
~~~

This is a **scoped runtime test**, complementing static verification of `RuntimeVisibleAnnotations`.

Three retentions to distinguish:

- `SOURCE`: processed by the compiler, yet the annotation does not need to be stored in the class file.
- `CLASS`: the annotation can be retained in the class file under **runtime-invisible** and is not visible to core reflection in the normal way.
- `RUNTIME`: the annotation can be queried by runtime reflection via the corresponding API.

**Not every annotation in source appears in `RuntimeVisibleAnnotations`**. Type annotations also have separate attributes (`RuntimeVisibleTypeAnnotations`, `RuntimeInvisibleTypeAnnotations`). To audit, know the annotation target and retention rather than checking only a single attribute name.

## 14. invokedynamic, MethodHandle, and BootstrapMethods

`InvokeDynamic` in the constant pool represents a call site linked via a bootstrap method. It differs from traditional `Methodref`/`InterfaceMethodref`. `BootstrapMethods` supplies bootstrap method handles along with bootstrap arguments referenced by dynamic call sites or dynamic constants.

Relationship skeleton:

~~~text
Instruction invokedynamic #n
             │
             ▼
CONSTANT_InvokeDynamic_info
      │            │
      ▼            ▼
bootstrap index  NameAndType
      │
      ▼
BootstrapMethods attribute
      ├── CONSTANT_MethodHandle
      └── bootstrap arguments (0..n)
~~~

On OpenJDK `javac` Java 17, dynamic string concatenation can use `java/lang/invoke/StringConcatFactory`. Lambda expressions usually use `invokedynamic` with an appropriate bootstrap (such as `LambdaMetafactory`). **Specific bootstrap names and sequences do not replace Java semantic rules**; newer compilers may alter representations within class format/behavior limits.

Key verification point from JVMS: a class file having `CONSTANT_InvokeDynamic` or `CONSTANT_Dynamic` requires a corresponding valid `BootstrapMethods` attribute per specification. Seeing `BootstrapMethods` does not prove a specific lambda ran or was JIT-optimized; it is **linkage metadata**.

**Distinguishing `CONSTANT_Dynamic` and `CONSTANT_InvokeDynamic`:**

- `Dynamic` describes a *constant* computed via bootstrap upon appropriate resolution.
- `InvokeDynamic` describes a *dynamic call site* for invocation.

Do not conclude `Dynamic` is present just because source contains a non-compile-time constant expression; many ordinary runtime expressions need no constant-dynamic entry.

## 15. Record Attribute: Verifying Java 17 Records

Create **`Point.java`**:

~~~java
public record Point(int x, int y) {
    public static void main(String[] args) {
        System.out.println(new Point(2, 3));
    }
}
~~~

Run:

~~~bash
javac --release 17 -d out Point.java
java -cp out Point
javap -classpath out -v -p Point
~~~

Business stdout:

~~~text
Point[x=2, y=3]
~~~

With Java 17 target, `Point`'s class file needs to represent a record per JVMS, including the **`Record` attribute** describing record components. When reading `javap -v`, inspect each component name/descriptor, and check generated members such as canonical constructor, accessors, and corresponding `equals`/`hashCode`/`toString` methods.

**Do not conclude a class is a record solely because its superclass is `java.lang.Record`**: class-file/metadata conditions must be evaluated per JVMS and semantics. Another reflection test is `Point.class.isRecord()` and `getRecordComponents()` at an appropriate runtime. The `Record` attribute exists since class-file major 60 (Java 16) and fits the Java 17 example.

A compiler may emit `BootstrapMethods` due to generated record methods (e.g., `ObjectMethods` mechanism), yet exact pool counts/indices are not stable QA requirements.

## 16. PermittedSubclasses: Verifying Sealed Hierarchies

Create two Java 17 files:

**`Shape.java`**

~~~java
public sealed interface Shape permits Circle {
}
~~~

**`Circle.java`**

~~~java
public record Circle(int radius) implements Shape {
}
~~~

Compile:

~~~bash
javac --release 17 -d out Shape.java Circle.java
javap -classpath out -v Shape
javap -classpath out -v Circle
~~~

In `Shape.class`, look for **`PermittedSubclasses`** listing `Circle` by symbolic class names. In `Circle.class`, look for record markers and implementing `Shape`. This is how to confirm a sealed hierarchy in the **actual class file**, not just source having the `sealed` keyword.

`PermittedSubclasses` appears in class files major 61+ per Java 17 JVMS. It does **not necessarily** appear in every `final` or `record` implementation sitting under a sealed parent; the key attribute resides on the sealed class/interface **declaring the permitted direct subclasses set**.

If a class implementing `Shape` does not belong to the permitted list, the JVM may reject the type relationship upon loading/linking under sealed class constraints, in addition to the compiler already checking from source. Do not try manually patching bytecode/attributes to bypass this rule.

## 17. Module Attribute: module-info.class Differs from Regular Classes

With Java modules (JPMS), the `module-info.class` file contains a module descriptor rather than an ordinary application class. Create an example:

~~~text
module-demo/
└── src/
    ├── module-info.java
    └── demo/api/Greeter.java
~~~

**`src/module-info.java`**

~~~java
module demo.greeter {
    exports demo.api;
}
~~~

**`src/demo/api/Greeter.java`**

~~~java
package demo.api;

public final class Greeter {
    private Greeter() {}

    public static String greet() {
        return "ok";
    }
}
~~~

From the `module-demo` directory:

~~~bash
mkdir -p mods/demo.greeter
javac --release 17 -d mods/demo.greeter \
  src/module-info.java src/demo/api/Greeter.java
javap -v mods/demo.greeter/module-info.class
~~~

`module-info.class` has distinct structure/flags such as `ACC_MODULE` and the **`Module` attribute**. Information can include module name, version, requires, exports, opens, uses, provides per descriptor and packaging choices. `ModulePackages`/`ModuleMainClass` have their own emission conditions (e.g., packaging tools/module tooling); not every module descriptor is required to contain both.

Use `javap -v `module-info.class`` to inspect the actually emitted binary descriptor, or module/JAR management tools such as `jar --describe-module` when appropriate. Do not confuse `exports` with `opens`: a package exported for ordinary public type access does not automatically grant all deep-reflection access.

If app classes use the classpath, the runtime module graph still depends on `--module-path` and roots. A valid `Module` attribute does not guarantee the `java` command resolved the module and all required dependencies.

## 18. NestHost, NestMembers, and InnerClasses

A source file containing nested classes can generate multiple class files, for example:

~~~java
public class Outer {
    private int secret = 21;

    public class Inner {
        public int doubleSecret() {
            return secret * 2;
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer();
        System.out.println(outer.new Inner().doubleSecret());
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d out Outer.java
java -cp out Outer
javap -classpath out -v -p Outer
javap -classpath out -v -p 'Outer$Inner'
~~~

Stdout:

~~~text
42
~~~

In Bash shells, single quotes around `Outer$Inner` prevent `$Inner` from being expanded by the shell as an environment variable. In PowerShell, single quotes can also be used. Files `Outer$Inner.class` and `Outer.class` carry metadata for nested/nest relationships per compiler/JVMS.

**`InnerClasses`** describes nesting relationships for metadata/language purposes. **`NestHost`/`NestMembers`** supports nest-based access control since Java 11; therefore Java 17 compilers usually do not need to generate synthetic accessors just so a nestmate can access private members in eligible cases.

Do not understand the name `InnerClasses` as a guaranteed list of every anonymous/local/method type under all circumstances. Inspect the actual class file and distinguish **Java lexical nesting**, **class-file nest membership**, and **binary names containing `$`**.

## 19. Class-File Version Is the First Check

Class files have `major`/`minor`:

| Java Release | Common Major |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

For ordinary Java 17 code without preview, expect **major 61, minor 0** after:

~~~bash
javac --release 17 -d out VerifySample.java
javap -classpath out -v VerifySample
~~~

Note `--release 17` **does not force all external libraries** on the classpath to also be major 61 or lower. Dependency artifacts must be verified if the product claims to run on Java 17.

Class files using preview features have special rules regarding `minor_version = 65535` and corresponding runtime; **do not include preview artifacts in general compatibility matrices** without explicitly specifying version/`--enable-preview`.

### Java 17 Program Reading the First Three Header Fields

File **`HeaderCheck.java`**:

~~~java
import java.io.DataInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class HeaderCheck {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass one .class path");
        }

        try (DataInputStream in = new DataInputStream(
                Files.newInputStream(Path.of(args[0])))) {
            int magic = in.readInt();
            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();

            System.out.printf(
                    "magic=%08X minor=%d major=%d%n",
                    magic, minor, major);
        }
    }
}
~~~

Compile `VerifySample.java` first, then run:

~~~bash
javac --release 17 HeaderCheck.java
java HeaderCheck out/VerifySample.class
~~~

Stdout:

~~~text
magic=CAFEBABE minor=0 major=61
~~~

This snippet **only checks the first 8 bytes**; it does not parse the constant pool, does not validate the whole class, or confirm runtime loadability. If the file is too short, the stream will throw an exception; if it has valid magic/version yet the rest is corrupted, `HeaderCheck` can still print numbers normally. This is a very narrow format smoke check, not a substitute for the verifier or `javap`.

## 20. When Comparing Class Files from Two Builds

A real task: two builds of the same source with changed JDK, flags, or dependencies produce different outputs. Classify before concluding a bug:

| Observed Difference | Possible Meaning |
| --- | --- |
| Major version changed | Target `--release`/`-target` or JDK compiler config changed |
| Public API descriptor changed | Risk of binary incompatibility |
| `Signature` changed while descriptor kept | Generic metadata/API semantics/tooling may have changed |
| `MethodParameters` lost | Frameworks relying on parameter reflection may be affected |
| `RuntimeVisibleAnnotations` lost | Reflection or dependency injection/serialization may change |
| `LineNumberTable`/`LocalVariableTable` changed | Debug metadata/obfuscation/compiler flags changed |
| Constant pool index changed | Usually layout/detail; `#n` changing alone does not prove behavior changed |
| `BootstrapMethods` changed | Compiler strategy/dynamic linkage metadata changed; inspect deeply before concluding |
| `Code` instruction sequence differs | Compiler implementation/lowering may differ; verify behavior with tests |
| `PermittedSubclasses` or `Record` changed | Verify language-level binary contract |
| `Module` exports/requires changed | Module graph and accessibility may be affected |

**Check on the actual released artifact.** If Gradle/Maven creates JARs, shades, obfuscates, adds multi-release entries, or instruments coverage after `javac` runs, class files in the release JAR can differ from those in the intermediate output directory.

To inspect a class inside a JAR:

~~~bash
jar tf app.jar
javap -classpath app.jar -v -p demo.App
~~~

Both commands are **templates**: replace `app.jar` and `demo.App` with the actual artifact/class. `jar tf` lists entries; `javap` reads the specified class without scanning the entire JAR. For multi-release JARs, inspect the `META-INF/versions/N` versions selected by the corresponding runtime; a base class does not represent all versions.

## 21. PASS/FAIL Matrix: What Should Be Verified?

| Criterion | Tool | PASS When |
| --- | --- | --- |
| Header, Java target | `javap -v` or reading header | Major/minor matches policy; no unintended preview |
| Public binary API | `javap -p -s`, API diff | Descriptors and access flags match release |
| Compile-time constants | `javap -v` | `ConstantValue` accurate when required |
| Generic contract | `javap -v -s` | `Signature` valid and consistent with descriptor |
| Runtime annotations | `javap -v` + reflection test | Annotations present and readable when retention/target require |
| Bytecode/verifier metadata | `javap -v -c` + JVM test | Output valid; JVM loads/tests cleanly per supported environment |
| Lambda/concat linkage | `javap -v` + JVM test | Bootstrap metadata valid, runtime behavior accurate |
| Record/sealed | `javap -v` + runtime reflection | `Record`/`PermittedSubclasses` and semantics accurate |
| Module descriptor | `javap module-info.class` / `jar --describe-module` | Requires/exports/opens match module API |
| Dependencies | `jdeps` and runtime test | Needed modules/JARs/APIs present, no wrong runtime target |

For a library, inspecting class files of the **public API surface** is critical. Yet system validation still needs test runs to catch reflection, serialization, classpath, native library, service loading, or business data errors.

## 22. What Not to Infer from the Constant Pool

**“The constant pool contains class name `com/foo/Bar`, so the program will definitely load Bar.”** False. The entry may be referenced by a branch that never runs, metadata, reflection, or other bytecode. The JVM does not eagerly resolve every symbolic reference the way learners imagine.

**“A String name appearing means the annotation definitely remains.”** False. You must inspect the exact attributes containing annotation entries and retention/visibility.

**“Seeing `InvokeDynamic` means the code has been JIT-optimized.”** False. `invokedynamic` is an instruction/call-site linkage in the class file; JIT is a separate runtime optimization layer.

**“`Signature` describes generics, so the JVM runtime checks `List<String>`.”** False. Java generics are mainly erasure; type metadata does not by itself enforce that every element has type String.

**“Classfile major 61 means the application is Java 17 compatible.”** Not enough. Dependency classes, platform APIs, runtime module graph, preview features, native code, container images, and JVM flags all need verification.

**“Same source, different constant pool indices means logic changed.”** False. Constant pool indices, ordering, and codegen details can differ while semantic behavior remains equivalent.

**“Every method must have Code, every class must have StackMapTable.”** False. Abstract/native methods have no regular code body; `StackMapTable` applies according to specific code/version constraints.

## 23. Validation Workflow for an Artifact in a Real Project

1. Record **JDK compiler version, `--release`, build tool flags**, and commit/dependency lock of source.
2. Compile to a clean output directory; check exit code, never treat stale files as new results.
3. Run `javap -v -p -c -s` on classes needing audit, starting with public classes and new types.
4. Read header/major/minor, `this_class`, access flags, superclass/interfaces.
5. Read the constant pool by **symbolic references**, without relying on fixed `#n` numbers.
6. Read field/method descriptors, generic Signature, and annotations required for the API contract.
7. Verify specialized attributes: `ConstantValue`, `Code`, `StackMapTable`, `BootstrapMethods`, `Record`, `PermittedSubclasses`, `Module`.
8. If output must remain compatible with an older runtime, test **with the lowest Java runtime**, together with the release artifact and full dependencies.
9. Run unit/integration tests and reflection tests when metadata attributes affect behavior.
10. When comparing two builds, prioritize **semantic diffs** of public descriptors/attributes, rather than strictly comparing full `javap` text or raw class bytes unless policy mandates reproducible builds.

### Minimal Verification Command Set for the Example

~~~bash
javac --release 17 -g -parameters -d out VerifySample.java
javap -classpath out -v -p -c -s VerifySample
javap -classpath out -v Reviewed
java -cp out VerifySample
~~~

On this example, you can verify: major version 61, `LIMIT` with `ConstantValue: int 42`, generic metadata, runtime-visible annotation, method bytecode, and stdout `n:7`. For `Reviewed.class`, you can inspect `AnnotationDefault` if the annotation type declares a default value; the current demo declares no default so **that attribute is not needed**.

## 24. Self-Check Knowledge Questions

**Question 1.** Why are `#15 = Methodref ...` in build A and `#29 = Methodref ...` in build B not enough to report a bug?  
**Answer:** Index numbers are merely positions in the constant pool. You must compare symbolic targets (class, name, descriptor) and usage semantics.

**Question 2.** Do `descriptor: Ljava/lang/Number;` and generic `T extends Number` contradict each other?  
**Answer:** No. The descriptor reflects erasure; `Signature` can store type variable `T` metadata.

**Question 3.** Why is `MethodParameters` needed if a framework must read parameter names via reflection?  
**Answer:** That is formal parameter metadata corresponding to compiler option `-parameters`; `LocalVariableTable` from debug info does not fully substitute for it.

**Question 4.** If an annotation has `SOURCE` retention, is not seeing it in `RuntimeVisibleAnnotations` an error?  
**Answer:** No. SOURCE annotations serve the compiler and are usually not stored in class files.

**Question 5.** Does `BootstrapMethods` mean the JIT has already run?  
**Answer:** No. It is metadata supporting dynamic linkage in the class file.

**Question 6.** What should you look for when auditing a Java 17 sealed class/interface?  
**Answer:** `PermittedSubclasses` on the sealed parent along with the permitted direct subclasses list; verify relationships and matching runtime behavior.

**Question 7.** Should the `Record` attribute appear in the regular class `VerifySample`?  
**Answer:** Not expected; it is for class files representing records. Verify `Point.class` from the record example instead.

**Question 8.** Does major 61 guarantee a library runs on Java 17 with all dependencies?  
**Answer:** No. You must check dependency class-file versions and run tests on a real Java 17 runtime.

**Question 9.** Why are the `Exceptions` attribute and `exception_table` not the same?  
**Answer:** One describes declared exceptions of a method, whereas the exception table inside `Code` describes handlers for bytecode ranges.

**Question 10.** Why cannot a program reading the 8-byte header replace `javap` or the bytecode verifier?  
**Answer:** It only verifies magic/major/minor; it does not check the constant pool, attributes, instruction constraints, or dependency resolution.

## 25. Key Takeaways and Official References

- **Constant pool** is the table of symbolic references/literals used by a class file; `#n` is an index, not a stable API identifier.
- **Descriptors** describe field/method types at the JVM level; **Signature** stores additional generic metadata when needed.
- **Attributes** have distinct locations and contracts; check presence/values based on source, compiler flags, and class-file version, rather than applying a rigid checklist to every class.
- **`javap -v -p -c -s`** is a quick inspection tool; code tests and runtime checks must supplement it when confirming an application works.
- For non-preview Java 17, **major 61, minor 0** is the target indicator; it is not enough to guarantee full application portability.
- When auditing releases, prioritize public APIs, annotations, module/record/sealed metadata, and dependency graphs over pool ordering changes.

Primary specifications to cross-check by version:

- [Java SE 17 JVMS §4.1 — ClassFile structure](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1).
- [Java SE 17 JVMS §4.4 — The Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4).
- [Java SE 17 JVMS §4.7 — Attributes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7).
- [Oracle Java 17 — javap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [Java SE 17 JVMS §4.3 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3).
