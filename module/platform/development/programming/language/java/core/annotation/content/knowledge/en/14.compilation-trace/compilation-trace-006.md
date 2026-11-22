# Cross-Referencing Source Code, Class Files, and Reflection Results for Java Annotations

An annotation written in source code **does not necessarily exist in the class file**, and an annotation present in the class file **is not necessarily returned by Java reflection**. This is the key point when debugging frameworks that look up annotations, when reading `javap -v` output, or when seeing the IDE display metadata while the program's `getAnnotation(...)` call returns `null`.

You can view the process across three layers of evidence:

~~~text
Java source code (.java)
    |
    | javac: checks @Target, element values, annotation processors...
    v
Class file (.class) + attributes retained by compilation
    |
    | JVM loads class and reflection evaluates annotation type, retention, location
    v
Result from Class / Field / Method / AnnotatedType / ... at runtime
~~~

This article demonstrates how to cross-reference **source code → bytecode/class file → reflection** with a runnable Java 17 example. The focus is on distinguishing `@Retention(SOURCE)`, `CLASS`, and `RUNTIME`; reading the right metadata sections from `javap -v`; and explaining cases where data exists in the class file but standard reflection APIs cannot find it.

## 1. Three Questions Before Investigating an Annotation

When seeing an annotation such as:

~~~java
@Audited("checkout")
class CheckoutService {}
~~~

you need to ask **three distinct questions**:

1. **Is the annotation valid in the source code?** The compiler checks that the annotation type exists, `@Target` allows the applied location, the `value` element has the right type, and the value expression is valid. An annotation processor can consume the metadata right during compilation.
2. **Does the compiler write the annotation to the class file of `CheckoutService`?** This depends on `@Retention` and the kind of location. A `SOURCE` annotation normally does not appear on the target class file; `CLASS` or `RUNTIME` can be stored in the corresponding attribute.
3. **Can reflection find it?** Normally the annotation must have `RetentionPolicy.RUNTIME`, and you must also query **the right element** such as `Class`, `Method`, `Field`, or `AnnotatedType`. An annotation on a method does not automatically become an annotation on the class containing that method.

Do not infer that the three answers will be the same. In particular, `javap -v` may display metadata that `SomeClass.class.getAnnotation(...)` **does not return**.

## 2. @Retention: The Decisive Link Between Source, Class File, and Runtime

`@Retention` is placed on **the annotation type declaration**, rather than automatically changing depending on each place where the annotation is used.

| Retention | In source | On target class file | Via standard runtime reflection |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Yes | That annotation is not retained in the binary representation | No |
| `RetentionPolicy.CLASS` | Yes | Yes, except for special cases excluded by the JLS | Not exposed as a runtime annotation |
| `RetentionPolicy.RUNTIME` | Yes | Yes, except for special cases excluded by the JLS | Readable if querying the right annotated element/type |

**The default** when an annotation type does not declare `@Retention` is **`RetentionPolicy.CLASS`**, not `SOURCE` or `RUNTIME`.

A short illustration (declarations only, not yet a complete file):

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@interface CheckedAtCompileTime {}

@Retention(RetentionPolicy.CLASS)
@interface StoredInBytecode {}

// No @Retention => defaults to CLASS.
@interface AlsoStoredInBytecode {}

@Retention(RetentionPolicy.RUNTIME)
@interface VisibleAtRuntime {}
~~~

From this, it follows that:

- `SOURCE` is suitable for analysis/checking tools or annotation processors that only need information during compilation.
- `CLASS` is suitable when metadata is needed at the binary level, for tools that read/transform class files, or for post-compilation processing steps; Java runtime reflection does not automatically expose it.
- `RUNTIME` is suitable when libraries/frameworks use reflection to look up metadata at program runtime.

**Exception note:** The JLS specifies that annotations **on local variable declarations** and **on lambda formal parameter declarations** are not retained in the binary representation, even if the annotation type has CLASS/RUNTIME retention. Annotations on the **type** of a local variable/lambda parameter with `TYPE_USE` are a different case and may be stored according to type annotation rules. Therefore, you should not write an overly broad rule like “every `@Retention(RUNTIME)` can be read via reflection”.

## 3. Where Does a Class File Store Annotations?

A `.class` file does not store the entire source code verbatim. The compiler generates a JVM class file structure containing the constant pool, class/field/method descriptors, and **attributes**.

For standard *declaration annotations*, the important attribute names include:

- **`RuntimeVisibleAnnotations`**: annotations on a class/field/method belonging to the runtime-visible group.
- **`RuntimeInvisibleAnnotations`**: annotations remaining in the class file that are not exposed by standard Java reflection as runtime annotations; for example, an annotation with CLASS retention.
- **`RuntimeVisibleParameterAnnotations`** and **`RuntimeInvisibleParameterAnnotations`**: annotation metadata on formal parameters of a method/constructor.
- **`RuntimeVisibleTypeAnnotations`** and **`RuntimeInvisibleTypeAnnotations`**: annotations on **type-use contexts** (`TYPE_USE`), such as generic type arguments or complex type components.
- **`AnnotationDefault`**: the default value declared by an **annotation element method**, located in the class file of the **annotation type**.

The name “RuntimeInvisible” means the annotation **is not provided by JVM reflection as an ordinary runtime annotation**; it does **not** mean the bytecode has removed the annotation or that tools like `javap` cannot view it.

A class file can contain multiple attribute groups in **different locations**. For example, an annotation on a **field** is recorded in the field's info; an annotation on a **method** is recorded in the method section; a type annotation on a generic argument may reside in `RuntimeVisibleTypeAnnotations` within the field/method metadata section, rather than in `RuntimeVisibleAnnotations` on the class.

Besides the groups above, there is also annotation-specific metadata in specialized structures such as record components; you need to inspect the actual location in `javap -v`. Seeing an annotation's name in the **constant pool** is not enough to conclude that it is attached to the class being inspected: the constant pool also contains type references, method names, strings, and other information.

## 4. Runnable Java 17 Example: One Class, Three Retentions, and One Type Annotation

Create a single file **`AnnotationTraceDemo.java`**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.AnnotatedParameterizedType;
import java.util.List;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceOnly { String value(); }

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface BinaryOnly { String value(); }

@Target(ElementType.TYPE)
@interface DefaultBinary { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeReadable { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD})
@interface MemberLabel { String value() default "auto"; }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMark {}

@SourceOnly("compiler")
@BinaryOnly("classfile")
@DefaultBinary("implicit")
@RuntimeReadable("reflection")
final class Sample {
    @MemberLabel("identifier")
    private int id = 42;

    @MemberLabel
    public int id() { return id; }

    private List<@TypeMark String> names;
}

public class AnnotationTraceDemo {
    public static void main(String[] args) throws Exception {
        Class<Sample> type = Sample.class;
        System.out.println("SOURCE=" + type.isAnnotationPresent(SourceOnly.class));
        System.out.println("CLASS=" + type.isAnnotationPresent(BinaryOnly.class));
        System.out.println("DEFAULT=" + type.isAnnotationPresent(DefaultBinary.class));
        System.out.println("RUNTIME=" + type.getAnnotation(RuntimeReadable.class).value());
        System.out.println("FIELD=" +
                type.getDeclaredField("id").getAnnotation(MemberLabel.class).value());
        System.out.println("METHOD=" +
                type.getDeclaredMethod("id").getAnnotation(MemberLabel.class).value());
        var annotated = type.getDeclaredField("names").getAnnotatedType();
        var parameterized = (AnnotatedParameterizedType) annotated;
        var arg = parameterized.getAnnotatedActualTypeArguments()[0];
        System.out.println("TYPE_USE=" + arg.isAnnotationPresent(TypeMark.class));
    }
}
~~~

This file uses the annotation types and the `Sample` class as package-private, with only `AnnotationTraceDemo` being public. Therefore, save it under the exact filename `AnnotationTraceDemo.java` so that `javac` compiles it properly.

Open a terminal in the directory containing the file and run it with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 -d out AnnotationTraceDemo.java
java -cp out AnnotationTraceDemo
~~~

**Exact stdout** (compiled with `javac --release 17` and tested):

~~~text
SOURCE=false
CLASS=false
DEFAULT=false
RUNTIME=reflection
FIELD=identifier
METHOD=auto
TYPE_USE=true
~~~

### Reading Each Line of stdout

1. **`SOURCE=false`**: `@SourceOnly("compiler")` is present in `Sample`'s source code but omitted from the class file; reflection cannot see it.
2. **`CLASS=false`**: `@BinaryOnly("classfile")` is retained in the class file with CLASS retention, yet cannot be read via `Class.isAnnotationPresent`.
3. **`DEFAULT=false`**: `@DefaultBinary` does not declare `@Retention`, so it defaults to CLASS and is likewise not returned by reflection.
4. **`RUNTIME=reflection`**: `@RuntimeReadable` has RUNTIME retention and is attached directly to `Sample`, so `Class.getAnnotation(RuntimeReadable.class)` reads the value `reflection`.
5. **`FIELD=identifier`**: `MemberLabel` is declared on the `id` field; retrieve it using `getDeclaredField("id")` and then read the annotation of that `Field`.
6. **`METHOD=auto`**: the `id()` method has `@MemberLabel` without specifying `value`. Reflection returns the default value `auto` defined in the annotation type.
7. **`TYPE_USE=true`**: `@TypeMark` is on **`String` inside `List<String>`**, so you must go through `Field.getAnnotatedType()`, cast to `AnnotatedParameterizedType`, and select the actual type argument. It is not a declaration annotation on the `names` field.

The values printed by the program itself do not prove the bytecode locations, so we need **`javap -v`** in the next step.

## 5. Inspecting the Class File with javap -v

After compiling the example above, run:

~~~bash
javap -v -p -classpath out Sample
~~~

Here:

- **`-classpath out`** points to the directory containing the `.class` files generated by `javac -d out`.
- **`-v`** (verbose) displays detailed class file information, including the constant pool and attributes.
- **`-p`** additionally displays private members, allowing us to inspect the `id` field and `names` field.

The full output of `javap -v` is quite long and contains constant-pool indices such as `#12`, `#35` that depend on the compilation build. We only need to look for the **attribute names** and where they appear, without memorizing those indices.

### 5.1. Metadata on the Sample Class Itself

When looking at the end of the dump for `Sample`, you will find the annotation information for the corresponding **class**:

~~~text
RuntimeVisibleAnnotations:
    RuntimeReadable(
      value="reflection"
    )
RuntimeInvisibleAnnotations:
    BinaryOnly(
      value="classfile"
    )
    DefaultBinary(
      value="implicit"
    )
~~~

This is an **abbreviated version omitting constant pool indices and some secondary lines** for readability; it is not a requirement that the entire `javap` output match the exact indentation in this block.

- `RuntimeReadable` appears in `RuntimeVisibleAnnotations` because its retention is RUNTIME.
- `BinaryOnly` and `DefaultBinary` appear in `RuntimeInvisibleAnnotations` because their retention is CLASS.
- **`SourceOnly` does not appear as an annotation stored on `Sample`** because its retention is SOURCE. If you grep the name across **other class files**, you may still see the name `SourceOnly` because of the class defining the annotation or code referencing that type; this does not contradict the conclusion about the metadata on `Sample`.

### 5.2. Metadata on Fields/Methods

In the separate sections for the `id` field and the `id()` method, look for `RuntimeVisibleAnnotations` containing `MemberLabel`. Do not confuse that group with class-level annotations.

On the `names` field, the compiler writes the type-use annotation for the generic argument into the corresponding metadata section, which in this example includes **`RuntimeVisibleTypeAnnotations`** with `TypeMark`. This attribute explains why the code must read `getAnnotatedType()` and the actual type argument instead of calling `getAnnotation(TypeMark.class)` directly on `Field`.

### 5.3. Default Values Reside on the Annotation Type, Not Always at the Usage Site

Inspect the definition of `MemberLabel`:

~~~bash
javap -v -p -classpath out MemberLabel
~~~

Look for the `value()` method section and the **`AnnotationDefault`** attribute with the string `auto`. When `@MemberLabel` is used without arguments on the `Sample.id()` method, the metadata at the usage site does not need to redundantly store the default value. When read via reflection, the runtime resolves the default from the annotation type definition and returns `auto`.

This also explains a library upgrade scenario: if the default value in an annotation type changes in a new version, a class using the annotation **without explicitly specifying a value** may receive the new default when running against the new version of the annotation type. Therefore, an annotation type's default is part of the API contract and requires compatibility testing.

## 6. Why Does javap See It When Reflection Does Not?

There are at least **four categories of causes** to distinguish.

### 6.1. Retention Is Not RUNTIME

This is the direct reason for `CLASS=false` and `DEFAULT=false`: bytecode still contains the metadata, but Java reflection only exposes matching runtime annotations. Use `javap -v` or a bytecode analysis library when you need to inspect CLASS-retained annotations.

If a framework needs to look up the annotation at runtime, **design the annotation type with `@Retention(RUNTIME)`**. Changing retention in source code does not automatically fix previously compiled classes; you must recompile/repackage the classes using the annotation so the metadata is generated under the new policy.

### 6.2. Querying the Wrong Annotated Element

If an annotation is placed on a `method`, `field`, `parameter`, `record component`, `package`, or `module`, calling `SomeClass.class.getAnnotation(A.class)` cannot substitute for the API of the exact element.

| Declaration site | How to obtain the object to inspect |
| --- | --- |
| Class | `SomeClass.class` |
| Method | `SomeClass.class.getDeclaredMethod("name", parameterTypes...)` |
| Field | `SomeClass.class.getDeclaredField("fieldName")` |
| Formal parameter | `Method.getParameters()[index]` and `Parameter.getAnnotation(...)` |
| Record component | `SomeRecord.class.getRecordComponents()[index]` |
| Package | `SomeClass.class.getPackage()` |
| Module | `SomeClass.class.getModule()` |
| Type-use, e.g. generic argument | `Field.getAnnotatedType()`, or `Method.getAnnotatedReturnType()` and the corresponding `AnnotatedType` objects |

For packages/modules, you must properly compile/package `package-info.class` or `module-info.class` and run within the corresponding context. An annotation on a record component may have propagation rules to generated members when `@Target` is compatible; do not automatically assume every field/method receives the annotation.

### 6.3. Confusing Declaration Annotations with TYPE_USE Annotations

`RuntimeVisibleAnnotations` and `RuntimeVisibleTypeAnnotations` describe **two different structures**. For example:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface MarkType {}

class Container {
    java.util.List<@MarkType String> values;
}
~~~

This is an **illustrative declaration snippet**, not a standalone runnable file. To read `@MarkType` on the `String` type argument, obtain `Field.getAnnotatedType()` and then traverse `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`. Simply calling `Field.getAnnotation(MarkType.class)` will not return information about that type annotation.

An annotation with multiple targets, such as `FIELD` and `TYPE_USE`, may be represented in different places depending on the syntax/location where it is applied. Therefore, you must identify the location from the source code before inferring which attribute the class file contains.

### 6.4. Bytecode or Runtime Class Differs from the Source You Are Looking At

Common issues include:

- **Stale classes in output/cache**: the source changed, but the loaded `.class` is still the previous build. You need to recompile and verify the correct output folder/JAR.
- **Multiple versions with the same name on the classpath**: the class loader loads a different class from the one you just edited. Check the actual class location, for example `SomeClass.class.getProtectionDomain().getCodeSource()` if available and appropriate.
- **Different class loaders**: two classes with the same fully qualified name defined by two class loaders are two distinct types. `getAnnotation(A.class)` matches by the annotation type object, not merely by the name string.
- **Changed annotation type or element**: an incompatible runtime version can make annotation values unreadable or throw errors such as `AnnotationTypeMismatchException`, `IncompleteAnnotationException`, `TypeNotPresentException`, or `EnumConstantNotPresentException` when accessing the affected elements.

Therefore, before concluding “the compiler stripped the annotation”, inspect **the exact binary** that the application is running, not merely another class file with the same name.

## 7. Compilation Trace: Annotation Processors Differ from Reflection in When They Read

An annotation processor using `javax.annotation.processing` and the `javax.lang.model` model reads the source/element model **during compilation**. It can process an annotation with SOURCE retention because the annotation has not yet been removed from the compile-time data source.

For example, having a processor read `@SourceOnly("compiler")` is **an implementable capability**, not automatic behavior in the `AnnotationTraceDemo` program: the example program does not register any processor.

Timeline flow:

~~~text
Source code, @SourceOnly("compiler")
        |
        +--> javac + annotation processor (if configured)
        |        reads the source model
        |
        +--> javac generates Sample.class
                 does not retain SourceOnly on the class
                 retains BinaryOnly/DefaultBinary in invisible annotations
                 retains RuntimeReadable in visible annotations
                        |
                        +--> runtime reflection sees RuntimeReadable
                             but does not see SourceOnly/BinaryOnly
~~~

Point to remember: **annotation processing is not Java runtime reflection**. An annotation processor can use compiler APIs, whereas reflection reads metadata provided by the runtime class model. Comparing these two points in time helps explain why a build tool successfully processed an annotation while the running application still cannot find it.

### @Target Does Not Replace @Retention Either

`@Target` checks the validity of the **location**: `TYPE`, `METHOD`, `FIELD`, `TYPE_USE`, etc. `@Retention` determines metadata lifetime. An annotation with `@Target(METHOD)` + `@Retention(RUNTIME)` still will not show up when querying `Class.getAnnotation(...)`, because it is on a method rather than on the class.

Conversely, `@Target(TYPE)` + `@Retention(CLASS)` can appear in the class file but not through runtime reflection. You must resolve **both dimensions** correctly.

## 8. Boundaries to Keep in Mind Regarding Class Files and Reflection

### 8.1. Not All Source Information Has a Direct Reflection API

A local-variable **declaration annotation** is not retained in the class file under JLS rules. For a type-use annotation on a local variable type, metadata may be retained in bytecode (for example, in the `Code` attribute) depending on retention and target, but standard Java reflection **has no general API to list annotations on all local variables in a method's bytecode**.

To inspect this data, deep class file analysis (or bytecode tooling) is required. `Method.getAnnotations()` is not a way to find annotations placed on local variables inside a method body.

### 8.2. @Inherited Is a Separate Lookup Rule, Not Bytecode Copying

If an annotation has `@Inherited`, `@Target(TYPE)`, and `@Retention(RUNTIME)`, `Child.class.getAnnotation(A.class)` can look up the superclass when `Child` has no direct annotation. That **does not mean** the `Child` class file automatically receives an additional corresponding annotation attribute.

Furthermore, `@Inherited` does not automatically cause annotations on overridden methods to be inherited, nor does it automatically transfer annotations from an interface to an implementing class. When cross-referencing reflection against `javap -v Child`, you must recognize that class-level reflection can apply a lookup rule at runtime without requiring the child's bytecode to store a new annotation.

### 8.3. Repeatable Annotations May Be Stored as a Container

With `@Repeatable`, multiple base annotations at the same location are usually represented by a **container annotation**. `javap -v` may show the container holding an array of values, while `getAnnotationsByType(Base.class)` returns multiple base annotations after unwrapping the container.

Therefore, seeing one container in the class file while reflection returns multiple base annotations **is not a contradiction**. To compare them properly, understand both the `getDeclaredAnnotationsByType` and `getAnnotationsByType` APIs, as well as the container's retention/target. The container must satisfy the JLS constraints for repeatable annotations.

### 8.4. Annotation Values Must Be Compile-Time-Compatible

An annotation declaration does not allow every kind of runtime value like normal method calls. Primitive/`String` elements require a valid constant expression; `Class` elements use class literals; enum elements use enum constants; nested annotations/arrays have restricted syntax. If the source uses them incorrectly, **there is no successfully compiled class file to cross-reference**; resolve the `javac` error first.

This must be distinguished from **metadata loss due to retention**. Compile-time errors do not belong to the same category as “source compiles successfully but reflection cannot read the annotation”.

## 9. A Repeatable Debugging Workflow

When tasked with investigating why an annotation does not appear at runtime, follow this order:

1. **Identify the annotated element** in source code: class, method, field, parameter, record component, package, module, or type use. Record the exact name and signature.
2. **Read the annotation type declaration**: verify `@Target`, `@Retention` (or the CLASS default), `@Repeatable`/container capability, and elements with defaults.
3. **Recompile in a controlled manner** with the appropriate JDK/`--release`, making the output location explicit. Verify the command succeeds, rather than relying solely on IDE indicators.
4. **Run `javap -v -p` on the exact class file** and look for the corresponding attribute: visible/invisible declaration, parameter, type annotations, or default. Distinguish an actual attribute from merely seeing the name in the constant pool.
5. **Run reflection on the actual application/binary**: obtain the right `Class`/`Method`/`Field`/`AnnotatedType`, and call `getAnnotation` or `getAnnotationsByType` as needed.
6. **Compare against retention expectations**: SOURCE is not retained; CLASS may appear in the binary but not via reflection; RUNTIME can be read if querying the right element and not blocked by special rules.
7. **If the results still diverge**, check the class loader, classpath/module path, annotation type version, stale package/class files, and `@Inherited` or repeatable/container rules.

Diagnostic table:

| Symptom | Common explanation | How to verify |
| --- | --- | --- |
| Annotation present in source, absent from target class file | SOURCE retention or special location not stored | Read `@Retention`, run `javap -v` on the right binary |
| Present in `RuntimeInvisibleAnnotations` but `getAnnotation` returns `null` | CLASS retention | RUNTIME is needed if reflection is desired |
| `RuntimeVisibleAnnotations` present on method, but `Class.getAnnotation` returns `null` | Querying the wrong object | `getDeclaredMethod(...)` then read `Method` |
| `RuntimeVisibleTypeAnnotations` present on generic argument | Reading declaration instead of type use | Traverse `AnnotatedType`/`AnnotatedParameterizedType` |
| Reflection sees annotation on subclass, but `javap` on subclass does not | `@Inherited` class-level lookup | Compare superclass binary and `getDeclaredAnnotation` |
| Reflection returns multiple base annotations, `javap` sees one container | Repeatable annotation representation | `getAnnotationsByType` and container declaration |
| Reflection has metadata differing from the recently edited source | Stale binary/classloader or different version | Check binary origin and build/redeploy |

## 10. Common Mistakes When Interpreting Traces

**Mistake 1 — Seeing an annotation name in the constant pool and concluding it is attached to the class.** The constant pool also contains type names used elsewhere. Only treat an annotation as attached to an element when an attribute actually describes it at that exact location.

**Mistake 2 — Thinking “RuntimeInvisible” means deleted.** It is still in the class file; what is restricted is its ability to be reflected as a runtime annotation.

**Mistake 3 — Seeing `@Retention(RUNTIME)` and forgetting `@Target` and the annotated element.** Retention does not automatically propagate metadata to another class, package, or method. You must inspect the actual attachment site.

**Mistake 4 — Treating `getDeclaredAnnotations()` and `getAnnotations()` as completely identical APIs.** With class annotations and `@Inherited`, the results can differ. Repeatable annotations also have their own container-reading behavior.

**Mistake 5 — Changing a default and assuming every class file stores the old value.** If the usage site does not explicitly specify the element, the default value may come from the annotation type version loaded at runtime. Verify both the target class file and the class file defining the annotation.

**Mistake 6 — Treating the workspace `.java` file as proof that the JVM is running that exact version.** Another copy on the classpath, a JAR dependency, or a different class loader can explain most discrepancies.

**Mistake 7 — Treating the full `javap` output of one JDK version as a contract on the ordering of every line.** Constant-pool numbers, indices, and formatting layout can change across compilers/JDKs. Focus on the actual attributes and values.

## 11. Self-Check Exercises

Based on the `AnnotationTraceDemo` program:

**1. Why does `Sample.class.isAnnotationPresent(SourceOnly.class)` return `false`?** Because `@SourceOnly` is omitted from `Sample`'s class file according to SOURCE retention. The annotation type `SourceOnly` still exists as a compiled type because code references it, but **the annotation usage on Sample** is not stored.

**2. Why is `@BinaryOnly` visible via `javap -v Sample` yet still invisible to reflection?** Its metadata is retained in `RuntimeInvisibleAnnotations` due to CLASS retention.

**3. Why can `DefaultBinary` not be read at runtime even though it does not declare `@Retention`?** Because the default retention of an annotation type is CLASS.

**4. `MemberLabel.value()` defaults to `auto`. Where is this value stored?** The default is encoded in the metadata of **the `MemberLabel` annotation type** (`AnnotationDefault`). When `Sample.id()` only writes `@MemberLabel`, reflection resolves the default from the annotation type.

**5. Why is it necessary to cast to `AnnotatedParameterizedType` when reading `@TypeMark`?** Because the annotation is attached to the **generic type argument** `String` in `List<String>`, not a declaration annotation on the `names` field.

**6. What happens if `Sample` has `@RuntimeReadable`, but you query `Sample.class.getDeclaredMethod("id").getAnnotation(RuntimeReadable.class)`?** It returns `null` because that annotation belongs to the class, not the method.

**7. If a RUNTIME annotation is placed on a local-variable declaration, can it be listed via `Method.getAnnotations()`?** No. That declaration annotation is not retained as an annotation on the method; studying type annotations inside code requires appropriate tooling.

**8. If `@Inherited` allows `Child.class.getAnnotation(X.class)` to find the parent's annotation, will `javap -v Child` necessarily show X on the child class?** No. Reflection can look up the superclass without requiring the compiler to copy X into the child's binary.

## 12. Official Documentation

- **Java Language Specification `9.6.4.2 — @Retention**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.2
- **JLS `9.7.4 — Where Annotations May Appear**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.4
- **JVM Specification `4.7 — Attributes**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7
- **Java SE 21 API — RetentionPolicy**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/RetentionPolicy.html
- **Java SE 21 API — AnnotatedElement**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- **javap command reference (JDK 21)**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html

Properly cross-referencing annotations means determining **what the source code declares**, **what the compiler encoded and where in the class file**, and **which element runtime reflection inspects and which lookup rules it applies**. Only when these three links align can you explain with certainty why an annotation is found, hidden from reflection, or completely omitted after compilation.
