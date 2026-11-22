# Parameter and Type-Use Annotation Attributes in Java .class Files

After Java compiles source code, annotations are not simply stored as lines starting with the `@` character. Retained annotations become **metadata in the attributes of the `.class` file**. For **declared parameters** and **type-use locations**, the Java Virtual Machine Specification (JVMS) defines distinct groups of attributes.

This topic explains how to read the compilation trace of:

- Annotations attached to a **parameter declaration** of a method or constructor, such as `@RequestId String id` with an annotation having `@Target(PARAMETER)`.
- Annotations attached to a **parameter's type** or an inner subtype, such as `@NonNull String id` or `List<@NonNull String>` with an annotation having `@Target(TYPE_USE)`.
- The differences among `RUNTIME`, `CLASS`, and `SOURCE` retention when viewed with `javap -v` and with Java reflection.

This knowledge helps answer two easily confused questions: *"Why does `javap` see an annotation while reflection cannot read it?"* and *"Why does calling `Parameter.getAnnotation()` not see an annotation placed on the parameter's type?"*

## 1. Two Location Kinds: Parameter Declarations and Type Uses

Consider an illustrative example:

```java
void register(
        @InputName("user-id")
        @TypeLabel("value-type") String userId,
        java.util.List<@TypeLabel("element-type") String> groups) {
    // Process data in the application.
}
```

This is **not yet a standalone program**: you need to define the two annotations and place the method inside a class.

The locations here differ:

| Syntax | Annotated target | Required `ElementType` |
| --- | --- | --- |
| `@InputName("user-id")` on parameter `userId` | **Formal parameter** declaration | `PARAMETER` |
| `@TypeLabel("value-type") String` | The parameter's **use of type `String`** | `TYPE_USE` |
| `List<@TypeLabel("element-type") String>` | Generic type argument `String` nested inside `List` | `TYPE_USE` |

A **declared parameter** is a variable appearing in the parameter list of a method or constructor. A **type use** is a location where a Java type is used, which can be at the parameter type itself, inside a generic argument, on an array component, on a return type, on a wildcard, and so on.

Because an annotation with only `@Target(PARAMETER)` is not permitted in all `TYPE_USE` positions, you cannot simply use it to mark `List<@InputName String>`. Conversely, an annotation with only `TYPE_USE` is not a parameter declaration annotation, even though its syntax looks quite close to the parameter name.

### Declaring the two illustrative annotations

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface InputName {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeLabel {
    String value();
}
```

These are valid definitions that can be placed in the same package. They only describe metadata; they do not automatically validate string values or execute validation.

**One thing to remember:** when an annotation is declared for **both** `PARAMETER` and `TYPE_USE`, a syntactic position on a parameter can carry meaning for both the declaration and the type use according to Java's *applicability* rules. To make the compilation trace easier to observe, the main example in this article intentionally uses **separate annotation types** for the two target kinds.

## 2. The Four Most Important .class Attributes

In `.class`, the JVM dedicates one group of attributes to annotations on formal parameter declarations and another group to annotations on type uses:

| Class file attribute | Contents | Retention | Typical location |
| --- | --- | --- | --- |
| `RuntimeVisibleParameterAnnotations` | Declaration annotations on **method/constructor parameters** | `RUNTIME` | In `method_info` |
| `RuntimeInvisibleParameterAnnotations` | Parameter declaration annotations not visible to standard reflection | `CLASS` | In `method_info` |
| `RuntimeVisibleTypeAnnotations` | Annotations on **type uses** and certain type-parameter declarations | `RUNTIME` | In appropriate structures: `ClassFile`, `field_info`, `method_info`, or `Code` |
| `RuntimeInvisibleTypeAnnotations` | Type-use annotations stored in bytecode but not exposed to standard reflection | `CLASS` | The corresponding locations above |

JVMS 17 describes them in **§4.7.18, §4.7.19, §4.7.20, and §4.7.21**, respectively.

The names **Visible** and **Invisible** here relate to **standard runtime reflection**; they do not mean the attribute is hidden from `javap`. Both groups can be inspected via class-file analysis tools.

Annotations with `RetentionPolicy.SOURCE` are normally processed only by the compiler or tools on source code and are **not written into the runtime annotation attributes** mentioned above.

### Do not confuse with other attributes

- `RuntimeVisibleAnnotations` / `RuntimeInvisibleAnnotations` (§4.7.16–17) store annotations **on declarations** of classes, fields, methods, or corresponding members — not the dedicated way to locate formal parameter annotations.
- `AnnotationDefault` (§4.7.22) stores the **default value of an element of an annotation type**, such as `int retries() default 2;`; it is not about default values of regular method parameters.
- `MethodParameters` (§4.7.24) stores information about the **names and flags of formal parameters** when compiled appropriately, for example with `javac -parameters`. It is **different from** `RuntimeVisibleParameterAnnotations`.
- `Signature` (§4.7.9) contains generic signatures such as `List<String>` where needed. It describes the generic type structure, whereas `RuntimeVisibleTypeAnnotations` / `RuntimeInvisibleTypeAnnotations` attach metadata to **positions within that structure**.

A method can have multiple attributes on the same `method_info`; each attribute has its own purpose. Therefore, inspecting a single attribute is not always enough to understand all of the metadata.

## 3. How Do ParameterAnnotations Store Information?

For a method with formal parameter annotations, the `RuntimeVisibleParameterAnnotations` or `RuntimeInvisibleParameterAnnotations` attributes contain information **per parameter**.

At a simple conceptual level, the contents include:

```text
method_info
  RuntimeVisibleParameterAnnotations
    num_parameters
    parameter_annotations[0]
      annotation(s) of the first formal parameter
    parameter_annotations[1]
      annotation(s) of the second formal parameter
    ...
```

The indices and mapping order to the descriptor are defined by the JVMS. You do not need to parse bytecode manually to use regular annotations; APIs such as `Executable.getParameterAnnotations()` and `Parameter.getAnnotation(...)` read the appropriate runtime metadata.

An example with two parameters:

```java
void transfer(
        @InputName("source") String from,
        @InputName("destination") String to) {
    // Transfer data.
}
```

In bytecode, `InputName` is an annotation **of each formal parameter**, not an annotation attached to the `transfer` method itself. Calling `method.getAnnotation(InputName.class)` does not retrieve those annotations; you need to select the parameter first.

### Warning about compiler-generated parameters

Certain constructors, inner classes, enums, or other compiled code may contain synthetic/mandated parameters or mapping details that are not obvious from source syntax. When writing bytecode-processing tools, **do not assume that a source parameter index always corresponds mechanically to every slot in the descriptor of every kind of executable**. Follow the JVMS, the Java reflection API, and the appropriate metadata flags for the actual case.

The main example below uses **a regular instance method with one formal parameter**, so that the comparison is easy to observe.

## 4. TypeAnnotations Store Location Information Using Target and Type Path

Unlike declaration annotations, type-use annotations need to specify **which position in the type tree the annotation belongs to**.

The type annotation structure in the JVMS has two core pieces of information:

1. **`target_type` / `target_info`:** the kind of location being annotated, such as method parameter type, method return type, field type component, cast, local-variable type, etc.
2. **`type_path`:** the path descending into the type structure: array components, nested types, wildcard bounds, or generic type arguments.

Example with one parameter:

```java
void accept(
        @TypeLabel("list") java.util.List<@TypeLabel("item") String> values) {
}
```

This is an **illustrative** method, requiring the type annotation `TypeLabel` with `TYPE_USE`.

In the parameter type `List<String>`:

- The `"list"` annotation sits **on the outer type** of the formal parameter.
- The `"item"` annotation sits on **type argument 0**, which is `String`.

When viewed with `javap -v`, the relevant type annotation entries may be described like this:

```text
METHOD_FORMAL_PARAMETER, param_index=0
METHOD_FORMAL_PARAMETER, param_index=0, location=[TYPE_ARGUMENT(0)]
```

These are **typical semantic labels**, not a verbatim copy of the entire bytecode of a class. The index `param_index=0` identifies the first formal parameter. `location=[TYPE_ARGUMENT(0)]` indicates the path to the first type argument.

For other positions, the JVMS also uses path kinds such as `ARRAY`, `INNER_TYPE`, `WILDCARD_BOUND`, or `TYPE_ARGUMENT`, depending on the structure. This path is necessary to distinguish `List<@Label String>` from `@Label List<String>`.

### Why can a type annotation reside in Code?

Type annotations do not appear only in method/field signatures. For example, inside a method body there are **type uses** in expressions, type casts, or local variables according to language rules. The JVMS allows `RuntimeVisibleTypeAnnotations` / `RuntimeInvisibleTypeAnnotations` to be present in the `Code` attribute for locations belonging to the method body.

**Reflection scope note:** not every type annotation stored in `Code` has a standard reflection API to read it from a runtime object per local variable, expression, or bytecode offset. `javap -v` and appropriate class-file analysis tools are more useful for some such cases.

## 5. Retention: How Do SOURCE, CLASS, and RUNTIME Differ?

`@Retention` specifies how long an annotation is retained:

| Retention | Post-compilation trace | Standard Java reflection |
| --- | --- | --- |
| `SOURCE` | Not stored in the class file as a runtime annotation attribute | Not readable |
| `CLASS` | Stored as **RuntimeInvisible...** in the appropriate attribute | Not readable via standard mechanisms |
| `RUNTIME` | Stored as **RuntimeVisible...** in the appropriate attribute | Readable with the appropriate reflection API |

If **`@Retention` is not specified**, Java defaults to `RetentionPolicy.CLASS`. Thus, the annotation can show up when running `javap -v`, yet `getAnnotation()` returns `null`.

This distinction is **intentional in the JVM model**, not an accidental reflection bug.

Both target and retention must match:

- Parameter declaration annotation: `@Target(PARAMETER)`; if `RUNTIME`, it is stored under the visible parameter annotations group.
- Annotation on parameter type or generic argument: `@Target(TYPE_USE)`; if `RUNTIME`, it uses the visible type annotations group.
- The same annotation type may allow multiple targets; in that case, identify the exact **position where it was actually applied** when reading metadata.

An annotation with RUNTIME retention **does not guarantee that every `getAnnotation()` sees it**. You also have to call the API on the **right `AnnotatedElement` or `AnnotatedType`**.

## 6. Standalone Java 17+ Example: Four Class-File Attributes at Once

Create a single file **`ParameterTraceDemo.java`** with all the code below. The example was compiled and run with `javac` and `java`, and inspected with `javap -v`.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.List;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface ParamRuntime {
    String value();
}

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.CLASS)
@interface ParamClass {
    String value();
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface TypeRuntime {
    String value();
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.CLASS)
@interface TypeClass {
    String value();
}

class Service {
    public void accept(
            @ParamRuntime("declaration")
            @ParamClass("stored-in-class")
            @TypeRuntime("list-type")
            @TypeClass("hidden-type")
            List<@TypeRuntime("element-type") String> values) {
        System.out.println(values.size());
    }
}

public class ParameterTraceDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Method method = Service.class.getDeclaredMethod("accept", List.class);
        Parameter parameter = method.getParameters()[0];

        System.out.println("parameter=" +
                parameter.getAnnotation(ParamRuntime.class).value());

        System.out.println("class-parameter-visible=" +
                (parameter.getAnnotation(ParamClass.class) != null));

        AnnotatedParameterizedType type = (AnnotatedParameterizedType)
                parameter.getAnnotatedType();

        System.out.println("type=" +
                type.getAnnotation(TypeRuntime.class).value());

        System.out.println("element=" +
                type.getAnnotatedActualTypeArguments()[0]
                        .getAnnotation(TypeRuntime.class).value());

        System.out.println("class-type-visible=" +
                (type.getAnnotation(TypeClass.class) != null));

        System.out.println("parameter-name=" + parameter.getName());
    }
}
```

Run from the directory containing the file, with JDK 17 or later:

```bash
javac -parameters -encoding UTF-8 ParameterTraceDemo.java
java ParameterTraceDemo
```

**Exact stdout** (when compiled with the `-parameters` flag as above):

```text
parameter=declaration
class-parameter-visible=false
type=list-type
element=element-type
class-type-visible=false
parameter-name=values
```

Line-by-line analysis:

1. `parameter=declaration`: `@ParamRuntime` belongs to `PARAMETER` with `RUNTIME` retention, so it can be read via `Parameter.getAnnotation()`.
2. `class-parameter-visible=false`: `@ParamClass` is still compiled into bytecode (CLASS retention), but is not exposed by standard Java reflection.
3. `type=list-type`: `@TypeRuntime("list-type")` belongs to the **type use `List<...>`** position of the formal parameter. You must read `Parameter.getAnnotatedType()` instead of only reading annotations directly on `Parameter`.
4. `element=element-type`: `@TypeRuntime("element-type")` is on the `String` type argument. You must go deeper using `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`.
5. `class-type-visible=false`: `@TypeClass` is in the type annotations group with CLASS retention, so it is not retrieved by standard runtime reflection.
6. `parameter-name=values`: the name `values` is retained when using `-parameters`. It belongs to parameter-name metadata, **not** the contents of parameter/type annotations.

All annotation types in this example are simply markers with one `String value()` element. The JVM does not turn them into parameter-processing rules. `Service.accept()` is declared but not called in `main`; the `System.out.println(values.size())` line in the method body **does not appear** in the stdout above.

### Opening the .class trace with javap -v

After `javac` succeeds, run:

```bash
javap -v -p Service
```

This command is a **class-file inspection** step, not running `main`. In the `accept(java.util.List<java.lang.String>)` method section or its corresponding signature/descriptor, look for four attributes:

```text
RuntimeVisibleTypeAnnotations
RuntimeInvisibleTypeAnnotations
RuntimeVisibleParameterAnnotations
RuntimeInvisibleParameterAnnotations
```

The four names above are **the entries to look for**, not the complete verbatim output of `javap`: ordering, constant-pool indices, line numbers, and detailed formatting may vary between JDK versions.

When tested on the example code, the corresponding type-use positions are displayed semantically as:

```text
METHOD_FORMAL_PARAMETER, param_index=0
METHOD_FORMAL_PARAMETER, param_index=0, location=[TYPE_ARGUMENT(0)]
```

- The visible parameter annotation contains `ParamRuntime("declaration")`.
- The invisible parameter annotation contains `ParamClass("stored-in-class")`.
- The visible type annotations contain `TypeRuntime("list-type")` and `TypeRuntime("element-type")`, with the matching type-argument path.
- The invisible type annotation contains `TypeClass("hidden-type")`.
- `MethodParameters` can show the name `values` due to using `-parameters`.

Although the two invisible attributes contain data, reflection in the previous section returned `false` as designed. **Do not assume reflection is wrong just because `javap` sees an attribute.**

### Try removing the -parameters flag

Re-run `javac -encoding UTF-8 ParameterTraceDemo.java` **without** `-parameters` and then run `java ParameterTraceDemo` in a standard compilation environment:

- The name from `parameter.getName()` usually becomes `arg0` (if the compiler does not store parameter names via an equivalent mechanism).
- Annotations by target and retention are still stored and read according to the same rules.

For a clean test, delete the `.class` files created by the example itself before recompiling if your compiler or environment does not overwrite them as expected. **`-parameters` is not a requirement for `@Target(PARAMETER)` annotations to be stored.**

## 7. Choosing the Right Reflection API

Different API groups read different data:

| Question | Primary API | Metadata object |
| --- | --- | --- |
| Direct annotation on the first formal parameter | `method.getParameters()[0].getAnnotation(A.class)` | `Parameter` |
| All declaration annotations for parameters | `method.getParameterAnnotations()` | `Annotation[][]` |
| Annotation on a parameter's type | `method.getParameters()[0].getAnnotatedType()` | `AnnotatedType` |
| Annotated types of all parameters | `method.getAnnotatedParameterTypes()` | `AnnotatedType[]` |
| Annotation on `String` in `List<String>` | Cast appropriately to `AnnotatedParameterizedType`, then `getAnnotatedActualTypeArguments()[0]` | Annotated type argument |
| Annotation on the method's return type | `method.getAnnotatedReturnType()` | Annotated return type |
| Declared name of the parameter when metadata is available | `Parameter.getName()` and `isNamePresent()` | `MethodParameters`/parameter name |

Two different questions:

```java
// Assume the method and annotation types are from the main example.
Parameter p = method.getParameters()[0];

p.getAnnotation(ParamRuntime.class);  // Annotation on the declaration.
p.getAnnotatedType()
 .getAnnotation(TypeRuntime.class);     // Annotation on the List type position.
```

This is an **API illustration snippet**; `method` must exist as in the full program. An annotation on `String` inside `List<String>` is one level deeper, so `AnnotatedParameterizedType` is needed.

Reflection generally sees only RUNTIME-retention annotations and also depends on the kind of annotated element; it is not a general tool for listing every attribute in a class file. When auditing bytecode, use `javap -v` or an appropriate bytecode analysis library.

## 8. Compilation Cases to Distinguish

### A. A declaration annotation on a method is not on a formal parameter

```java
// Assume @MethodLabel has target METHOD,
// @ParamLabel has target PARAMETER.
@MethodLabel
void process(@ParamLabel String input) {}
```

The two annotations are in two different locations:

- `@MethodLabel` is a declaration annotation on the method: it can be stored via `RuntimeVisibleAnnotations` / `RuntimeInvisibleAnnotations` depending on retention.
- `@ParamLabel` is a declaration annotation on the formal parameter: it can be stored via `RuntimeVisibleParameterAnnotations` / `RuntimeInvisibleParameterAnnotations`.

If you use `method.getAnnotation(ParamLabel.class)`, you are querying the wrong element. Read the corresponding `Parameter`.

### B. A type-use annotation on a generic argument differs from one on the outer type

```java
// Assume @TypeLabel has @Target(TYPE_USE).
void execute(java.util.List<@TypeLabel("item") String> values) {}
```

The annotation sits on the generic type argument `String`. Reflection must select the parameter type `List<...>` first and then enter the type argument. Bytecode needs `type_path` to record the exact position of `String` in the type tree.

### C. Constructor parameters are also formal parameters

```java
class Customer {
    Customer(@InputName("customer-id") String id) {
        // Illustration: annotation placed on a constructor parameter.
    }
}
```

This snippet assumes `InputName` has already been declared. A constructor in a class file is also described by a `method_info` (with the special bytecode name `<init>`). Therefore, the corresponding **ParameterAnnotations** group still applies. In reflection, obtain `Constructor<?>` and then call `getParameters()` or `getParameterAnnotations()`.

### D. SOURCE retention does not appear in those attributes

If you replace `@Retention(RUNTIME)` with `@Retention(SOURCE)` for a test annotation, `javac` can process it during compilation, but the class file does not store a runtime annotation attribute for that annotation itself. Do not conclude that an annotation "was never in the source" simply from not seeing its name in `javap -v`.

### E. Do not infer business behavior from class-file structure

An annotation named `@Validated` or `@NonNull` does not automatically cause bytecode to have an extra data-checking `if` branch, unless an annotation processor, compiler plugin, or runtime framework actually processes the annotation and generates/executes that logic.

**Attributes store metadata; consumers interpret metadata.** These are two completely different processes.

## 9. Practical Workflow to Diagnose a "Missing" Annotation

When reflection returns `null`, check in order:

1. **Check @Target.** Is the annotation for `PARAMETER` or `TYPE_USE`? If multiple targets are declared, check the actual applied location.
2. **Check @Retention.** `RUNTIME` is the choice for standard reflection. `CLASS` may be visible through the class file, though not through standard reflection.
3. **Read the right API.** Use `Parameter.getAnnotation()` for declarations; use `getAnnotatedType()` and traverse the type tree for type uses.
4. **Ensure you are inspecting the right compiled class.** Check classpath, module path, JDK version, class name, and the actual `.class` file. An old class may shadow the new one.
5. **Run javap -v.** Identify the attribute name, target, parameter index, and type path. Do not rely solely on a short snippet from the source.
6. **Verify the element in the descriptor.** Be especially careful with synthetic constructor parameters, nested classes, enums/records, or cases where the compiler adds metadata.
7. **Only then check the framework.** The framework might only read declaration annotations, ignore type-use annotations, or apply its own inheritance/meta-annotation rules beyond basic Java reflection.

For annotations on complex generics, such as `List<@TypeLabel String>`, exact location information is usually more important than seeing an annotation of the same name appear somewhere in `javap` output.

## 10. Common Pitfalls

| Misconception | Accurate understanding |
| --- | --- |
| "An annotation before a parameter name is a PARAMETER annotation" | You must consider `@Target` and position: the annotation may apply to the **parameter type** |
| "RuntimeInvisible means javap cannot read it" | `javap -v` can still display the attribute; it is just unavailable via standard reflection |
| "CLASS retention is the same as SOURCE retention" | `CLASS` is stored in the class file; `SOURCE` is not stored in runtime annotation attributes |
| "-parameters is required for Parameter.getAnnotation" | `-parameters` mainly preserves formal parameter names and info in `MethodParameters` metadata |
| "getParameterAnnotations sees List<@A String>" | You need to descend through `AnnotatedParameterizedType` |
| "RuntimeVisibleAnnotations is the parameter attribute" | Formal parameter declarations have their own `...ParameterAnnotations` group |
| "TypeAnnotations only live in method_info" | They can also reside in `ClassFile`, `field_info`, or `Code` when appropriate |
| "A type annotation on List means the inner String is annotated" | List and the String type argument have two separate positions, requiring a type path `type_path` |
| "A custom annotation automatically creates data checks" | Only a consumer that understands the annotation enforces checks or behavior |

## 11. Self-Check Exercises

**Question 1.** An annotation has `@Target(PARAMETER)` and `@Retention(RUNTIME)` attached to a method parameter. Which attribute group does the attribute name belong to?

**Answer:** `RuntimeVisibleParameterAnnotations` in `method_info`.

**Question 2.** If the retention on that annotation is changed to `CLASS`, which group will the attribute belong to, and can reflection read it?

**Answer:** `RuntimeInvisibleParameterAnnotations`; standard reflection does not return this annotation.

**Question 3.** Given `List<@Mark String> values`, what kind of attribute holds the annotation if `Mark` only allows `TYPE_USE` and has `RUNTIME` retention?

**Answer:** `RuntimeVisibleTypeAnnotations`, with the target corresponding to the formal parameter type and the path to the type argument.

**Question 4.** Given `List<@Mark String>`, is `Parameter.getAnnotation(Mark.class)` a sufficient API to view the annotation on `String`?

**Answer:** No. You need `getAnnotatedType()`, cast appropriately to `AnnotatedParameterizedType`, and then obtain the type argument.

**Question 5.** Why does `javap -v` show `RuntimeInvisibleTypeAnnotations` while `getAnnotatedType().getAnnotation()` returns `null`?

**Answer:** Because `CLASS` retention is stored for class-file processing tools, but is not visible through standard runtime reflection.

**Question 6.** Does `-parameters` "enable annotations on parameters"?

**Answer:** No. It preserves formal parameter names/metadata like `values` so reflection can read the name; the mechanism for storing annotations uses separate attributes.

**Question 7.** In `List<@Mark String>`, how is `type_path` useful?

**Answer:** It identifies that the annotation is on the **inner type argument**, rather than on the outermost `List` type.

## References

- [JVMS 17, §4.7.18 — RuntimeVisibleParameterAnnotations](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.18).
- [JVMS 17, §4.7.19 — RuntimeInvisibleParameterAnnotations](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.19).
- [JVMS 17, §4.7.20 — RuntimeVisibleTypeAnnotations and type_path](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.20).
- [JVMS 17, §4.7.21 — RuntimeInvisibleTypeAnnotations](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.21).
- [Java SE 17 API — Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html).
- [Java SE 17 API — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).

**Remember:** When tracing annotations in bytecode, determine **the annotated target (parameter declaration or type-use)**, **retention (SOURCE/CLASS/RUNTIME)**, and **position in the type tree**. Those three factors determine which class-file attribute contains the metadata and how tools or reflection can access the metadata.
