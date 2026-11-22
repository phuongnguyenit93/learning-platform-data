# RuntimeVisibleAnnotations and RuntimeInvisibleAnnotations in Java class files

## 1. What are these two attributes?

When `javac` compiles a program containing annotations, annotation information can become **metadata in the `.class` file**. According to the Java Virtual Machine (JVM) class file format, two important attributes for declaration annotations are:

- **`RuntimeVisibleAnnotations`**: stores annotations that the Java runtime must support retrieving via the Reflection API, typically annotation types with `@Retention(RetentionPolicy.RUNTIME)`.
- **`RuntimeInvisibleAnnotations`**: stores annotations retained in the class file but **not exposed by standard Java reflection at runtime**, typically annotation types with `@Retention(RetentionPolicy.CLASS)`.

Here, the terms **visible/invisible** refer to **the level of support by runtime reflection**, not `public`/`private`, not whether the class is loaded by the JVM, and not whether a bytecode-reading tool can see the data.

A class file inspection tool such as `javap -v` or a bytecode analysis library can see **both types of attributes**. However, when using `Class.getAnnotation(...)`, `Field.getAnnotation(...)`, or `Method.getAnnotation(...)`, annotations with `CLASS` retention are not exposed by these APIs.

For example, if a class has:

```java
@ClassStamp("saved-in-bytecode")
@RuntimeStamp("read-by-reflection")
class Report {}
```

and the two corresponding annotation types are defined with `CLASS` and `RUNTIME` retention, then in the class metadata you can see:

```text
RuntimeInvisibleAnnotations:
  ClassStamp(value="saved-in-bytecode")

RuntimeVisibleAnnotations:
  RuntimeStamp(value="read-by-reflection")
```

The block above is a **simplified diagram**, not a verbatim copy of `javap` output: the `javap -v` command also displays constant pool indices and other structures. The runnable example in section 4 will show the actual contents of these attributes.

## 2. Mapping to the three @Retention levels

`@Retention` is a meta-annotation that determines up to which stage the compiler retains an annotation. It is declared on the **annotation type**, not on individual annotation usages.

| `RetentionPolicy` | Annotation on class/field/method in source | Present in class file after compilation? | Class file attribute for declaration annotations | Reflection at runtime |
| --- | --- | --- | --- | --- |
| `SOURCE` | Yes | No | No corresponding entry created for that annotation usage | No |
| `CLASS` | Yes | Yes | `RuntimeInvisibleAnnotations` | No |
| `RUNTIME` | Yes | Yes | `RuntimeVisibleAnnotations` | Yes, according to the exact location and lookup rules |

An example of defining annotations:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceStamp {}

@Retention(RetentionPolicy.CLASS)
@interface ClassStamp {}

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeStamp {}
```

These are **supporting declarations**; not yet a standalone program. Java defaults the retention to **`CLASS`** when an annotation type does not declare `@Retention`.

Especially important points:

1. `SOURCE` is not recorded as an annotation on the **annotated element** in the class file. However, the compiler still generates the `SourceStamp.class` file for the **annotation type definition** `SourceStamp` if that type is compiled, and `SourceStamp.class` can still contain meta-annotations describing that type itself. Do not confuse these two inspection targets.
2. `CLASS` still leaves a trace in bytecode. Saying that “`CLASS` annotations disappear after compilation” is incorrect; more accurately, they are not exposed by standard runtime reflection APIs.
3. `RUNTIME` is retained in the class file and makes metadata available to reflection. This does **not** automatically execute business logic.
4. `@Retention` is independent of `@Target`. `@Target` determines whether an annotation can be applied to a class, field, method, constructor, or type-use; `@Retention` determines how long the annotation is retained.
5. `@Documented` affects display in applicable Javadoc documentation; `@Inherited` affects certain lookup rules on classes. They do **not turn** `CLASS` into `RUNTIME`.

## 3. Where is RuntimeVisibleAnnotations located in a class file?

A `.class` file has multiple structures, including class information, fields (*field_info*), methods (*method_info*), and attributes. Attributes for declaration annotations can be attached to the corresponding elements in the class file.

An example class:

```java
@RuntimeStamp("type")
class Sample {
    @RuntimeStamp("field")
    int count;

    @RuntimeStamp("method")
    void run() {}
}
```

If `RuntimeStamp` is an annotation type with `RUNTIME` retention and appropriate targets, the compiler can emit:

- One `RuntimeVisibleAnnotations` at the **class level** containing `@RuntimeStamp("type")` metadata.
- One `RuntimeVisibleAnnotations` in the metadata of **field `count`** containing `@RuntimeStamp("field")`.
- One `RuntimeVisibleAnnotations` in the metadata of **method `run`** containing `@RuntimeStamp("method")`.

These are **different** locations. Reflection on `Sample.class` does not automatically return annotations attached specifically to a field or method; you must obtain the `Field`/`Method` and call the API on that specific object.

`RuntimeInvisibleAnnotations` is distributed similarly for annotations with `CLASS` retention. `RuntimeVisibleAnnotations` and `RuntimeInvisibleAnnotations` can also appear together on **the same element**, because the same class can carry multiple annotations with different retention policies.

The attribute name in `javap` may appear multiple times: once in the field section, once in the method section, and once at the class level. To interpret it correctly, you must look at **which declaration context** the attribute is in, rather than merely spotting the string `RuntimeVisibleAnnotations` in the output.

## 4. Complete Java 17+ example: from source to javap and reflection

We write a program with three annotations corresponding to `SOURCE`, `CLASS`, and `RUNTIME`, applied to **a class, a field, and a method**. After compiling, we use `javap -v` to inspect the metadata and use reflection to verify what can actually be read at runtime.

Save the entire code block below as **`RetentionAttributesDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.SOURCE)
@interface SourceStamp {
    String value();
}

@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.CLASS)
@interface ClassStamp {
    String value();
}

@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeStamp {
    String value();
}

@SourceStamp("source-type")
@ClassStamp("class-type")
@RuntimeStamp("runtime-type")
class Report {
    @SourceStamp("source-field")
    @ClassStamp("class-field")
    @RuntimeStamp("runtime-field")
    private int total;

    @SourceStamp("source-method")
    @ClassStamp("class-method")
    @RuntimeStamp("runtime-method")
    public int count() {
        return total;
    }
}

public class RetentionAttributesDemo {
    public static void main(String[] args)
            throws NoSuchFieldException, NoSuchMethodException {
        Class<Report> type = Report.class;
        Field field = type.getDeclaredField("total");
        Method method = type.getDeclaredMethod("count");

        System.out.println("SOURCE on class: "
                + type.isAnnotationPresent(SourceStamp.class));
        System.out.println("CLASS on class: "
                + type.isAnnotationPresent(ClassStamp.class));
        System.out.println("RUNTIME on class: "
                + type.getAnnotation(RuntimeStamp.class).value());
        System.out.println("RUNTIME on field: "
                + field.getAnnotation(RuntimeStamp.class).value());
        System.out.println("RUNTIME on method: "
                + method.getAnnotation(RuntimeStamp.class).value());
    }
}
```

### 4.1. Compiling and running

From the directory containing `RetentionAttributesDemo.java`, using JDK 17 or later:

```bash
javac --release 17 -d out RetentionAttributesDemo.java
java -cp out RetentionAttributesDemo
```

**Exact stdout:**

```text
SOURCE on class: false
CLASS on class: false
RUNTIME on class: runtime-type
RUNTIME on field: runtime-field
RUNTIME on method: runtime-method
```

Explanation of each result:

- `SOURCE on class: false`: the compiler does not retain `@SourceStamp("source-type")` as a runtime annotation on `Report`.
- `CLASS on class: false`: `@ClassStamp("class-type")` may **still be present in the class file**, but `isAnnotationPresent` does not see `CLASS` retention.
- `RUNTIME on class: runtime-type`: the `RuntimeStamp` annotation type allows observation via runtime reflection, so `getAnnotation(RuntimeStamp.class)` retrieves the value on the class.
- The remaining two lines: use the corresponding `Field` and `Method` objects to read runtime annotations on the marked members.

These results were verified by compiling with `javac --release 17` and running on a JDK supporting Java 17.

### 4.2. Inspecting with javap -v

After compiling, run:

```bash
javap -v -p -classpath out Report
```

- `-v` (verbose) shows the class file structure, constant pool, and attributes.
- `-p` also displays non-public members, because the `total` field is `private`.
- `-classpath out` tells `javap` where to find `Report.class`.

In the output, you will encounter sections structured similarly to the following (**constant pool indices and unrelated lines omitted**):

```text
private int total;
  ...
  RuntimeVisibleAnnotations:
    RuntimeStamp(value="runtime-field")
  RuntimeInvisibleAnnotations:
    ClassStamp(value="class-field")

public int count();
  ...
  RuntimeVisibleAnnotations:
    RuntimeStamp(value="runtime-method")
  RuntimeInvisibleAnnotations:
    ClassStamp(value="class-method")

...
RuntimeVisibleAnnotations:
  RuntimeStamp(value="runtime-type")
RuntimeInvisibleAnnotations:
  ClassStamp(value="class-type")
```

This is an **illustrative pattern**, not the verbatim `javap` stdout; the actual output includes reference numbers such as `#14`, multiline formatting, flags, descriptors, and other sections. The actual contents were cross-checked against `javap -v -p` after compiling the example.

Points worth noting:

1. `RuntimeStamp` appears in `RuntimeVisibleAnnotations` on the class, field, and method, corresponding to `RUNTIME` retention.
2. `ClassStamp` appears in `RuntimeInvisibleAnnotations` in all three locations, corresponding to `CLASS` retention.
3. Usages of `@SourceStamp(...)` on `Report` **do not appear** in these annotation attributes because of `SOURCE` retention.
4. The name `Report` in the `javap` command is very important. If you replace it with `RuntimeStamp`, you are analyzing the **class file of the annotation type** rather than the annotated class, so you may see meta-annotations such as `@Retention` and `@Target` — which is different data.

### 4.3. When using Java reflection to read CLASS retention

Do not write:

```java
ClassStamp stamp = Report.class.getAnnotation(ClassStamp.class);
System.out.println(stamp.value());
```

This is a **non-standalone illustration** and can throw `NullPointerException`, because `getAnnotation(ClassStamp.class)` returns `null` for annotations that only have `CLASS` retention.

To read `ClassStamp` at runtime using class file data, you need a **bytecode-reading tool**, not standard `AnnotatedElement.getAnnotation`. A bytecode analysis library can read `RuntimeInvisibleAnnotations` without needing an instance of `Report`. On the other hand, if you control the annotation definition and the true goal is runtime reflection, consider changing the retention to `RUNTIME` and then **recompiling** the classes where the annotation is applied.

## 5. RuntimeInvisible does not mean private, removed, or unreadable by any tool

Misconceptions that easily lead to poor design:

**Misconception 1: “Invisible means the annotation is declared private.”** Retention differs from access modifiers. A `public` annotation type can still be stored in `RuntimeInvisibleAnnotations` when it has `CLASS` retention.

**Misconception 2: “Invisible means the metadata was removed from the .class file.”** No. This very attribute is the metadata **trace** in the class file. Bytecode-reading tools can parse it without relying on the reflection API.

**Misconception 3: “Visible is because the class was instantiated with new.”** No. `RuntimeVisibleAnnotations` is metadata on the class file. You can use `Report.class.getAnnotation(RuntimeStamp.class)` without creating any `Report` instance. The number of objects created/GC'd does not determine retention.

**Misconception 4: “If `getAnnotation` returns null, the class file does not contain the annotation.”** Insufficient. The annotation might have `CLASS` retention; you might be reading the wrong class/member; or it might be a repeatable annotation represented via a container. To diagnose, identify the annotation definition, target, and retention, and use `javap -v` when needed.

**Misconception 5: “Changing @Retention automatically updates all old bytecode.”** No. Compiled `.class` files retain metadata as of compile time. After modifying an annotation type definition, you must recompile the sources applying that annotation if you want the appropriate new attributes. Do not assume that merely replacing the JAR containing the annotation type will rewrite already existing class files.

## 6. Do not confuse with RuntimeVisibleTypeAnnotations / RuntimeInvisibleTypeAnnotations

The two attributes in the lesson title primarily apply to **declaration annotations**. For annotations placed on **type uses** (*type-use annotations*, Java 8+), the class file uses different names:

- `RuntimeVisibleTypeAnnotations` for type-use annotations with `RUNTIME` retention.
- `RuntimeInvisibleTypeAnnotations` for type-use annotations with `CLASS` retention.

Illustrative example (not a standalone program):

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonEmptyText {}

class Repository {
    List<@NonEmptyText String> labels;
}
```

`@NonEmptyText` annotates the **type argument `String`** of `List<String>`, not the entire `labels` field declaration. The corresponding metadata belongs to the *type annotations* category, not just standard `RuntimeVisibleAnnotations`.

Reading this information requires going through the type annotation API, for example `Field.getAnnotatedType()`, and then `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` to retrieve the annotation on the type argument. You should not expect `field.getAnnotation(NonEmptyText.class)` to automatically find every annotation within the field's type structure.

An annotation type can have multiple targets, so in some cases the compiler may generate metadata in different locations depending on whether the annotation is applied to a declaration or a type use. To draw a conclusion, identify the **target and exact position in Java syntax** and then read the corresponding attribute.

## 7. Parameter annotations and default values: yet other attribute names

### 7.1. Method/constructor parameter annotations

Annotations on **parameter declarations** (`ElementType.PARAMETER`) can be stored in:

- `RuntimeVisibleParameterAnnotations` if retention is `RUNTIME`;
- `RuntimeInvisibleParameterAnnotations` if retention is `CLASS`.

Example:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface RequestId {}

class Api {
    void receive(@RequestId String id) {}
}
```

The snippet above is **illustrative**; to compile it standalone, you need to import `Retention`, `RetentionPolicy`, `Target`, and `ElementType` appropriately. To query it at runtime, you can obtain the `Method` and call `getParameterAnnotations()` or use `Parameter` objects.

Note that **annotations on a parameter declaration** and annotations on a **type use inside the parameter type** are two different kinds of locations. They can be stored using separate attribute families.

### 7.2. AnnotationDefault

If an annotation type declares an element with a default value:

```java
@interface Priority {
    int value() default 5;
}
```

The `default 5` value is stored using the **`AnnotationDefault`** attribute on the corresponding method of the **annotation type** `Priority`. That is neither a usage of `@Priority` on a class nor `RuntimeVisibleAnnotations`. The `Method.getDefaultValue()` API on the reflected method element indicates the default if present.

Do not confuse `AnnotationDefault` with the retention of an annotation type. An annotation with a default value and `CLASS` retention is still an annotation type with a default element, yet applying that annotation to a class does not thereby make it visible through runtime reflection.

## 8. Repeatable annotations (@Repeatable) and containers

When the same repeatable annotation is applied multiple times to a class or member, the compiler represents the component annotations via the **container annotation type** specified by `@Repeatable`.

Example:

```java
@Role("READ")
@Role("WRITE")
class AccessService {}
```

This is an **illustration**; assume `Role` is repeatable and has a suitable container, both with `RUNTIME` retention. In the class file, the data can appear as the container annotation inside `RuntimeVisibleAnnotations`. The `getAnnotation(Role.class)` API does not unwrap the container automatically, but `getAnnotationsByType(Role.class)` can return the component `Role` annotations.

Thus, when you see `RuntimeVisibleAnnotations` in `javap -v` while `getAnnotation(Role.class)` returns `null`, in addition to retention you also need to check **the repeatable/container representation**.

If a container with `CLASS` retention is used, the corresponding metadata is not read by Java runtime reflection via these APIs. Compatibility constraints between the repeatable annotation and container must be checked by the Java compiler at definition time.

## 9. Relationship with reflection, annotation processors, and bytecode tools

There are three paths for reading annotations, and they should not be conflated.

| Mechanism | Timing | SOURCE | CLASS | RUNTIME |
| --- | --- | --- | --- | --- |
| **Compiler / annotation processor** when compiling source | Compile time | Can be read in the source element model | Can be read when processing source | Can be read when processing source |
| **`.class` analysis**, e.g., `javap -v` or bytecode libraries | Post-compilation | No `SOURCE` annotation usages in target bytecode | Can read invisible attributes | Can read visible attributes |
| **Java Reflection API** on declaration metadata | Runtime | No | No | Yes, if the annotation exists on the right target and the lookup relationship matches |

The compiler can use `@Override` (`SOURCE` retention) to report errors right at compile time without keeping it in the class file. Bytecode inspection tools can analyze `CLASS` and `RUNTIME` after compilation. Reflection-based frameworks typically require annotation types with `RUNTIME` retention.

If a build process uses **bytecode rewriting/obfuscation/shrinking**, those tools can transform metadata. When encountering unexpected results, in addition to the source and retention, you must inspect the **final class file actually loaded/distributed**, not just the original class file immediately after `javac`. Annotation-preservation rules of third-party tools are separate configuration, not the meaning of the two attributes according to the JVM Specification.

## 10. Diagnostic workflow for an annotation “present in source but unreadable”

When `getAnnotation(MyAnnotation.class)` returns `null`, follow these steps in order:

1. **Check the annotation type declaration:** does it have `@Retention(RetentionPolicy.RUNTIME)`? If `@Retention` is absent, it defaults to `CLASS`.
2. **Check the right target:** is the annotation applied to a class, field, method, constructor, parameter, or type-use position? Which reflection API reads that exact location?
3. **Check the right element:** `getDeclaredField("x")` differs from `getDeclaredMethod("x")`; an annotation on a method is not an annotation on the class.
4. **Inspect the class file:** `javap -v -p -classpath out FullyQualifiedClassName`. Look for `RuntimeVisibleAnnotations`, `RuntimeInvisibleAnnotations`, or the appropriate `TypeAnnotations`/`ParameterAnnotations` variants.
5. **Look at the attribute's context:** does it belong to the class, a field, a method, or another component? Do not draw conclusions merely from finding the keyword.
6. **Check repeatable annotations:** if the type has `@Repeatable` and multiple usages, try `getAnnotationsByType(T.class)`.
7. **Check inheritance:** `@Inherited` only affects certain annotation lookups on **classes** along superclasses; it does not apply similarly to fields or methods.
8. **Verify which class file is running:** the classpath, module path, JAR version, and bytecode transformation tools can cause the runtime to use a different class than the one you are analyzing.
9. **Do not modify Java member visibility arbitrarily:** reading metadata on a private field via `Field.getAnnotation(...)` does not mean you have to call `setAccessible(true)`. Permission to read a private field's value or invoke a private method is a separate matter.

## 11. Short practice exercises

With the `RetentionAttributesDemo.java` program in section 4, you can verify three changes yourself:

**Exercise A — change retention:** change `ClassStamp` from `RetentionPolicy.CLASS` to `RetentionPolicy.RUNTIME`; recompile the program; predict that `RuntimeInvisibleAnnotations` for the `ClassStamp` usages will move to the `RuntimeVisibleAnnotations` group, while `isAnnotationPresent(ClassStamp.class)` on `Report.class` changes from `false` to `true`.

**Exercise B — change location:** remove `@RuntimeStamp("runtime-field")` from the `total` field while keeping `@RuntimeStamp("runtime-type")` on the class. After recompiling, `Report.class.getAnnotation(RuntimeStamp.class)` will still read the annotation on the class, whereas `Field.getAnnotation(RuntimeStamp.class)` on `total` will no longer have that annotation. When trying this, remember to update the field printing code to check for `null` safely instead of calling `value()` immediately.

**Exercise C — read the right element:** keep the program unchanged, run `javap -v -p -classpath out Report`, and identify the three `RuntimeVisibleAnnotations` locations corresponding to the class, field, and method. Match each location with the three values `runtime-type`, `runtime-field`, and `runtime-method`.

These exercises require no libraries beyond the JDK. They help connect three levels: **retention definition in source → attribute in the class file → reflection lookup result**.

**Remember:** `RuntimeVisibleAnnotations` contains declaration annotation metadata supported for runtime reading via reflection, typically originating from `@Retention(RUNTIME)`. `RuntimeInvisibleAnnotations` contains metadata still present in bytecode but not exposed through standard reflection, typically originating from `@Retention(CLASS)`. `SOURCE` leaves no annotation entry at the target after compilation. Type-use annotations, parameter annotations, and element defaults have **separate attribute families**, so you must choose the right attribute and lookup API before concluding whether data exists or has disappeared.
