# AnnotationMirror and AnnotationValue in the Java Language Model

In JSR 269 **annotation processing**, the compiler allows programs to inspect Java structures **at compile time**: classes, methods, fields, parameters, types, and the annotations attached to them. Two foundational APIs for working with annotation metadata are:

- **`javax.lang.model.element.AnnotationMirror`**: represents **a single annotation usage** in the compiler's language model, including the annotation type and the mapping from the annotation's elements to their values.
- **`javax.lang.model.element.AnnotationValue`**: represents **a value of an annotation element**, such as `3`, `"checkout"`, `String.class`, an enum constant, a nested annotation, or an array of annotation values.

They are not types used to read metadata via Java Reflection while the business application is running. `AnnotationMirror` and `AnnotationValue` serve the **compile-time language model**, typically processed inside `AbstractProcessor.process(...)` using `Element`, `TypeMirror`, `Elements`, and `RoundEnvironment` objects.

A key distinction: for annotations with default values, `AnnotationMirror.getElementValues()` only returns the elements **explicitly specified at the annotation site**; to receive defaults as well, use **`Elements.getElementValuesWithDefaults(mirror)`**.

## 1. Why Does the Compiler Need a Model Instead of Reflection?

Suppose we are compiling:

```java
@Review(value = "checkout", retries = 3)
class CheckoutService {}
```

An annotation processor may need to know:

- Which `Review` annotation does `CheckoutService` have?
- What **annotation type** is `Review` in the code being compiled?
- At this usage site, what is the `value` element set to?
- What is the value of `retries`? Is it written explicitly or does it use the default?
- If an element returns `Class<?>` but the Java type being compiled cannot yet be loaded by a `ClassLoader`, how can it be analyzed?
- If an annotation contains an enum, a nested annotation, or an array, how does the compiler represent those values?

Reflection primarily operates on classes that have already been compiled and loaded into the JVM, with annotations having `RUNTIME` retention. An annotation processor, by contrast, also needs to inspect **source code currently being processed by the compiler**, including annotations with `SOURCE` retention.

That is why the `javax.lang.model` API uses a **language model** system instead of trying to obtain `Class<?>`, `Method`, or runtime annotation proxies from business classes whose compilation has not yet finished.

| Requirement | Appropriate API |
| --- | --- |
| Inspect annotations while javac is compiling | `Element.getAnnotationMirrors()`, `AnnotationMirror`, `AnnotationValue` |
| Read default values in the compiler model | `Elements.getElementValuesWithDefaults(...)` |
| Inspect types in the current source | `TypeMirror`, `Types`, `TypeElement` |
| Read annotations of a loaded class at runtime | Java Reflection such as `Class.getAnnotation(...)` |
| Read annotations with `CLASS` retention from `.class` files after compilation | Class file/bytecode reader, not standard Java Reflection |

An annotation processor does not "execute annotation code"; it reads metadata and performs its own logic such as validating conventions, reporting compiler errors, or generating files.

## 2. What Does AnnotationMirror Represent?

Example declaration and usage:

```java
@interface Review {
    String value();
    int retries() default 2;
}

@Review("checkout")
class CheckoutService {}
```

In the compiler, the `TypeElement` object for `CheckoutService` can provide:

```java
List<? extends AnnotationMirror> mirrors =
        checkoutElement.getAnnotationMirrors();
```

This is a snippet inside an annotation processor, assuming the variable `checkoutElement` is an appropriate `Element` and both `java.util.List` and `javax.lang.model.element.AnnotationMirror` have been imported.

Each `AnnotationMirror` describes **one annotation on an element according to the compiler model**. Key APIs:

```java
DeclaredType annotationType = mirror.getAnnotationType();

Map<? extends ExecutableElement, ? extends AnnotationValue> explicit =
        mirror.getElementValues();
```

- `getAnnotationType()` returns a `DeclaredType` representing the **annotation type** used. You can use `annotationType.asElement()` to retrieve the `TypeElement` of the annotation type.
- `getElementValues()` returns a `Map` whose **keys** are `ExecutableElement`s representing element methods such as `value()` or `retries()`, and whose **values** are the corresponding `AnnotationValue`s.
- For `@Review("checkout")`, this map only has a key for `value`; the `retries` element **does not appear** because the annotation usage site did not specify it.

Why isn't the key a `String`? Because the compiler stores a direct reference to the **method element declaration** in the annotation type. To display the name you can call `entry.getKey().getSimpleName()`, and to precisely inspect the method element you can work with the `ExecutableElement` API.

`AnnotationMirror` is not equivalent to a runtime proxy object of `@Review`. Calling `getAnnotationType()` does not return a Java `Class<Review>`, and `getElementValues()` is not a `Map<String,Object>`.

## 3. What Data Types Does AnnotationValue Represent?

`AnnotationValue` describes each valid value of an annotation element, without forcing every value into a simple runtime Java type. It provides:

```java
Object raw = annotationValue.getValue();
```

`getValue()` returns `Object` because values take multiple forms. You need to inspect **the actual type of the object according to the `javax.lang.model` contract**:

| Annotation element kind | Form of `AnnotationValue.getValue()` in the language model | Interpretation |
| --- | --- | --- |
| Primitives `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `char` | Corresponding wrapper such as `Boolean`, `Integer`, `Character` | Represented constant value |
| `String` | `String` | String value |
| `Class` or `Class<?>` | **`TypeMirror`** | Java type model, **not `Class<?>`** |
| Enum | **`VariableElement`** | Enum constant element, not a runtime enum instance |
| Nested annotation | **`AnnotationMirror`** | An annotation value containing another annotation's metadata |
| One-dimensional array | **`List<? extends AnnotationValue>`** | List of annotation value elements, not a regular Java array |

**The two most common mistakes:**

1. Casting a `Class<?> handler()` element to `Class<?>` via `((Class<?>) annotationValue.getValue())` is wrong: the object returned by the model is a **`TypeMirror`**.
2. For `String[] labels()`, `getValue()` does **not** return `String[]`, but rather a `List` of `AnnotationValue`s; you must access each element value individually.

Values of `enum` types are also not loaded enum objects. The compiler uses `VariableElement` to reference **an enum constant in the source/type model**.

### 3.1. Nested Data

Example:

```java
@interface Tag {
    String value();
}

@interface Review {
    Tag tag();
    String[] labels();
}
```

When used as:

```java
@Review(tag = @Tag("public"), labels = {"api", "payment"})
class Endpoint {}
```

then:

- `Review` is represented by an `AnnotationMirror`.
- The value of `tag` is an `AnnotationValue` whose `getValue()` is the **`AnnotationMirror`** of `@Tag("public")`.
- The value of `labels` is an `AnnotationValue` whose `getValue()` is a **list of two `AnnotationValue`s**, each wrapping a `String`.

To read values deeper inside a nested annotation, you must continue reading **the mirror of the nested annotation**, rather than casting it to a `Tag` instance to call `tag.value()`.

## 4. Retrieving Explicitly Written Values and Default Values

Consider:

```java
@interface Review {
    String value();
    int retries() default 2;
    String[] labels() default {"core"};
}

@Review("checkout")
class CheckoutService {}
```

Here:

```java
Map<? extends ExecutableElement, ? extends AnnotationValue> explicit =
        mirror.getElementValues();
```

contains only the `value` element with `"checkout"`. The `retries` and `labels` elements have defaults, but at the annotation usage site they are **not explicitly written**.

When you need **the final values according to the annotation declaration**, call:

```java
Map<? extends ExecutableElement, ? extends AnnotationValue> all =
        processingEnv.getElementUtils()
                     .getElementValuesWithDefaults(mirror);
```

Now the map has the following elements:

| Element | `getElementValues()` | `getElementValuesWithDefaults()` |
| --- | --- | --- |
| `value` | `"checkout"` | `"checkout"` |
| `retries` | No entry | `2` |
| `labels` | No entry | `{"core"}` represented in the model |

Distinguish between **an absent entry** and **a null value**. Annotation elements do not accept `null` as a valid value; an absent entry in `getElementValues()` normally means that at the annotation usage site no explicit value was written for that element. It should not be treated as "written as `null`".

If you want to know the default value on the **definition itself** of an element, `ExecutableElement` also provides:

```java
AnnotationValue defaultValue = methodElement.getDefaultValue();
```

This value can be `null` if the annotation element declaration **has no default**. This is a `null` from **the API indicating the absence of a default**, not a user-written `null` annotation value.

**Two different needs:**

- `getElementValuesWithDefaults(mirror)`: reads a **specific annotation usage**, including the defaults it inherits.
- `ExecutableElement.getDefaultValue()`: reads an **annotation element definition**, whether or not it has a default.

All ways of reading must inspect the right annotation mirror, especially when the processor handles multiple annotation types.

## 5. Traversing Values with AnnotationValueVisitor

You can use `instanceof` after `getValue()`, but when you need extensible code or support for all value types, Java provides:

```java
<R, P> R AnnotationValue.accept(AnnotationValueVisitor<R, P> visitor, P p)
```

The visitor has specialized operations:

- `visitBoolean`, `visitByte`, `visitShort`, `visitInt`, `visitLong`, `visitChar`, `visitFloat`, `visitDouble`;
- `visitString`;
- `visitType(TypeMirror, ...)` for class literals;
- `visitEnumConstant(VariableElement, ...)` for enums;
- `visitAnnotation(AnnotationMirror, ...)` for nested annotations;
- `visitArray(List<? extends AnnotationValue>, ...)` for arrays.

A visitor avoids scattering error-prone casts throughout your code. The helper class `SimpleAnnotationValueVisitor9<R,P>` (Java 9+) lets you override the branches you need and inherit default handling for the rest. Java 17 can use this class.

**Note the method name `visitType`:** it provides the data as a **`TypeMirror`**, without requiring the corresponding `Class<?>` to be loadable in the JVM running the processor. This is an essential difference when analyzing source code.

The snippet below is an illustrative branch, used inside a visitor class:

```java
@Override
public String visitType(TypeMirror type, Void unused) {
    return "type:" + type;
}
```

To resolve more complex types (generics, arrays, error types...), you can additionally use `Types`, `TypeKind`, and subtypes of `TypeMirror` as needed, rather than relying on `toString()` always being a stable identifier for comparison.

## 6. Java 17+ Example: An Annotation Processor That Actually Reads Mirror and Value

This section creates **four files** in the same directory, without using any framework outside the JDK:

```text
Review.java
ReviewProcessor.java
CheckoutService.java
DefaultService.java
```

The example runs in two steps: compiling the annotation type and processor, then using that processor to compile the annotated classes.

### 6.1. Review.java — Defining Metadata with Multiple Value Types

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface Review {
    String value();
    int retries() default 2;
    Class<?> handler() default Runnable.class;
    Priority priority() default Priority.NORMAL;
    Tag tag() default @Tag("stable");
    String[] labels() default {"core"};
}

enum Priority {
    NORMAL, HIGH
}

@interface Tag {
    String value();
}
```

In `Review`, the compiler may encounter:

- `String` (`value`);
- `int` (`retries`);
- `Class<?>` (`handler`);
- `enum` (`priority`);
- nested annotation `Tag` (`tag`);
- `String[]` array (`labels`).

`@Retention(SOURCE)` intentionally demonstrates that the annotation processor still sees the annotation in the source during compilation, even though runtime Java Reflection cannot read this usage. Retention does not have to be `RUNTIME` for annotation processing to work.

`Tag` has default `CLASS` retention because none is explicitly declared; in this example it is used as a nested annotation value. What makes it possible for the processor to work is that the annotation value is available in the **compile-time model** of `Review`.

### 6.2. ReviewProcessor.java — Retrieving AnnotationMirror and Reading AnnotationValue

```java
import java.util.*;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.SimpleAnnotationValueVisitor9;

@SupportedAnnotationTypes("Review")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ReviewProcessor extends AbstractProcessor {
    static class ValueText
            extends SimpleAnnotationValueVisitor9<String, Void> {

        @Override
        public String visitString(String s, Void ignored) {
            return "string:" + s;
        }

        @Override
        public String visitInt(int n, Void ignored) {
            return "int:" + n;
        }

        @Override
        public String visitType(TypeMirror type, Void ignored) {
            return "type:" + type;
        }

        @Override
        public String visitEnumConstant(VariableElement constant, Void ignored) {
            return "enum:" + constant.getSimpleName();
        }

        @Override
        public String visitAnnotation(AnnotationMirror a, Void ignored) {
            return "annotation:" + a.getAnnotationType();
        }

        @Override
        public String visitArray(
                List<? extends AnnotationValue> values, Void ignored) {
            List<String> rendered = new ArrayList<>();
            for (AnnotationValue value : values) {
                rendered.add(value.accept(this, null));
            }
            return "array:" + rendered;
        }
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return false;
        }

        TypeElement review =
                processingEnv.getElementUtils().getTypeElement("Review");
        if (review == null) {
            return false;
        }

        for (Element element : roundEnv.getElementsAnnotatedWith(review)) {
            for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
                if (!mirror.getAnnotationType().asElement().equals(review)) {
                    continue;
                }

                System.out.println("element=" + element.getSimpleName());
                System.out.println("annotationType="
                        + mirror.getAnnotationType());
                System.out.println("explicit=" + names(mirror.getElementValues()));

                Map<? extends ExecutableElement,
                    ? extends AnnotationValue> all =
                    processingEnv.getElementUtils()
                                 .getElementValuesWithDefaults(mirror);

                ValueText visitor = new ValueText();
                all.entrySet().stream()
                    .sorted(Comparator.comparing(
                        e -> e.getKey().getSimpleName().toString()))
                    .forEach(e -> System.out.println(
                        e.getKey().getSimpleName() + "="
                        + e.getValue().accept(visitor, null)));
            }
        }
        return false;
    }

    private static String names(
            Map<? extends ExecutableElement,
                ? extends AnnotationValue> values) {

        return values.keySet().stream()
                .map(e -> e.getSimpleName().toString())
                .sorted()
                .toList()
                .toString();
    }
}
```

Key points in the processor:

1. `@SupportedAnnotationTypes("Review")` requests processing of the annotation type named `Review`. The example uses the **default package** to make it easy to compile with the commands below; in a real project, you should place the annotation in a named package and use the corresponding fully qualified name.
2. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` declares the source version supported by the processor in the example. The compilation commands use `--release 17` for compatibility.
3. `roundEnv.getElementsAnnotatedWith(review)` finds the `Element`s annotated with `@Review` in the current processing round.
4. `element.getAnnotationMirrors()` returns the element's annotation metadata. The code filters using `mirror.getAnnotationType().asElement()` to select **the exact `Review` type**, avoiding mixing in other annotations.
5. `mirror.getElementValues()` is used to display **the names of the explicitly written elements**.
6. `getElementValuesWithDefaults(mirror)` is used to obtain all values including elements that do not appear in the source at the usage site.
7. `ValueText` decodes the types `String`, `int`, `Class` (`TypeMirror`), enum (`VariableElement`), nested annotation (`AnnotationMirror`), and array (`List<AnnotationValue>`).
8. The code sorts by element name before printing so that the output has a deterministic order. **The order of the returned `Map` should not be relied upon as a display contract**.

The `ValueText` class is just a presentation visitor for the purposes of this lesson. When writing a production processor, you usually want to **return strongly typed data** and use `Messager.printMessage(Diagnostic.Kind.ERROR, ..., element)` to report compiler errors instead of `System.out.println`. `System.out` is used here to make the example easy to reproduce and compare stdout.

The nested `Tag` value is rendered by the visitor as `annotation:Tag`; this example **does not yet print `Tag.value()`**, though you can traverse into the nested `AnnotationMirror` to do so using the same `getElementValuesWithDefaults` mechanism.

### 6.3. CheckoutService.java — Specifying All Values

```java
@Review(
    value = "checkout",
    retries = 3,
    handler = String.class,
    priority = Priority.HIGH,
    tag = @Tag("public"),
    labels = {"api", "payment"}
)
class CheckoutService {}
```

In this usage, all **six elements** have explicit values: `value`, `retries`, `handler`, `priority`, `tag`, and `labels`.

### 6.4. DefaultService.java — Specifying Only the Required Value

```java
@Review("default")
class DefaultService {}
```

Here only `value` is written explicitly. The other elements take their defaults from the annotation type definition.

### 6.5. Commands to Compile and Run the Processor

From the directory containing the four files, create the output directory:

```bash
mkdir out
```

**Step 1.** Compile the annotation type and processor:

```bash
javac --release 17 -d out Review.java ReviewProcessor.java
```

**Step 2.** Compile the two classes annotated with `@Review` and **explicitly specify the processor**:

```bash
javac --release 17 -cp out -processorpath out -processor ReviewProcessor -d out CheckoutService.java DefaultService.java
```

In Step 2:

- `-cp out` helps the compiler find the compiled `Review`, `Priority`, and `Tag`.
- `-processorpath out` makes `ReviewProcessor` discoverable on the processor path.
- `-processor ReviewProcessor` specifies the processor to run. The example does **not** rely on automatic processor discovery via `META-INF/services`.
- `-d out` specifies where to store the generated `.class` files.
- There is no need to run `java CheckoutService`: they are classes inspected while **javac** runs, not an application with a `main` method.

**Output of Step 2:**

```text
element=CheckoutService
annotationType=Review
explicit=[handler, labels, priority, retries, tag, value]
handler=type:java.lang.String
labels=array:[string:api, string:payment]
priority=enum:HIGH
retries=int:3
tag=annotation:Tag
value=string:checkout
element=DefaultService
annotationType=Review
explicit=[value]
handler=type:java.lang.Runnable
labels=array:[string:core]
priority=enum:NORMAL
retries=int:2
tag=annotation:Tag
value=string:default
```

The example was tested with `javac --release 17` on a newer JDK, through the corresponding **two compilation steps**, and the printed result matched the output block above.

**Do not confuse this:** this is console output emitted by `System.out.println` inside `ReviewProcessor.process` **while javac is compiling**. It is not the runtime stdout of `CheckoutService`, nor does it prove that the annotation is retained at runtime. `@Retention(SOURCE)` fits the example.

## 7. Analyzing Each AnnotationValue from the Output

### 7.1. String and Primitives

```text
value=string:checkout
retries=int:3
```

`value` is a `String` value. `retries` is an `int` wrapped by `AnnotationValue`; `visitInt` receives an `int`. For other primitives, the visitor has corresponding dedicated methods, such as `visitBoolean`, `visitChar`, and `visitLong`.

An annotation element of type `int` can accept a constant expression such as `1 + 2`; the value model exposes **the computed value** rather than necessarily preserving the original source syntax. Do not use `AnnotationValue.toString()` to recover the exact code written by the user.

### 7.2. A Class Literal Becomes a TypeMirror

```text
handler=type:java.lang.String
```

The source contains `handler = String.class`. The compiler supplies a `TypeMirror` when the visitor processes `handler`, rather than returning `String.class` as a `java.lang.Class`.

Similarly, the default `Runnable.class` produces the output `type:java.lang.Runnable`. `TypeMirror` lets you inspect **the type being compiled**, including project types and complex types, without having to load the actual Java class.

In production tooling, when you need to compare types, you should use `Types.isSameType(...)`, `Types.isSubtype(...)`, or access the appropriate `TypeElement`, rather than just comparing `type.toString()` strings.

### 7.3. An Enum Constant Becomes a VariableElement

```text
priority=enum:HIGH
```

The source contains `Priority.HIGH`. The visitor receives a `VariableElement` representing the enum constant and calls `getSimpleName()` to display `HIGH`.

If the processor needs to know the enum type, you can inspect the enclosing element or the type model of the constant; do not assume `AnnotationValue.getValue()` is a `Priority.HIGH` object in the processor runtime.

### 7.4. A Nested Annotation Becomes an AnnotationMirror

```text
tag=annotation:Tag
```

In the source, there is `tag = @Tag("public")`. The visitor sees an **`AnnotationMirror`** for `Tag`.

If you need `"public"`, traverse the values of the nested mirror:

```java
@Override
public String visitAnnotation(AnnotationMirror nested, Void ignored) {
    Map<? extends ExecutableElement, ? extends AnnotationValue> entries =
            processingEnv.getElementUtils()
                         .getElementValuesWithDefaults(nested);

    for (var entry : entries.entrySet()) {
        if (entry.getKey().getSimpleName().contentEquals("value")) {
            return "tag:" + entry.getValue().getValue();
        }
    }
    return "tag:(missing)";
}
```

This is a snippet **to replace the `visitAnnotation` branch in the processor**, not a standalone complete program. The code only illustrates a specific `Tag` annotation; general-purpose code should handle all elements of a nested annotation, data types, and diagnostics if the structure is unexpected.

### 7.5. An Array Becomes a List of AnnotationValue

```text
labels=array:[string:api, string:payment]
```

`labels` is declared as `String[]`. The `visitArray` visitor receives `List<? extends AnnotationValue>` and uses `value.accept(this, null)` to process **each component value**, preserving order.

For `Class<?>[]`, each child element will be handled by `visitType`; for an array of nested annotations, each child element goes through `visitAnnotation`. Do not cast the whole `getValue()` to `String[]`, `Class<?>[]`, or `Tag[]`.

## 8. Should You Use getValue(), toString(), or a Visitor?

Three common approaches:

**Approach 1 — `getValue()` followed by type branching:** suitable for small logic where you know the element being read in advance, and where you thoroughly check `TypeMirror`/`VariableElement`/`AnnotationMirror`/`List` cases.

**Approach 2 — `AnnotationValue.toString()`:** convenient for quick display during debugging, but **it is not a contract for source code recovery or stable data serialization**. Its text representation may include quotes, type name formats, and case-dependent details. Do not rely on the `toString()` string as a standard way to check types.

**Approach 3 — `AnnotationValue.accept(visitor, p)`:** generally easier to extend if you need to handle multiple element kinds; the visitor has dedicated methods for each value form and supports array/nested annotation branches.

Example of correct `Class` handling code:

```java
Object raw = value.getValue();
if (raw instanceof TypeMirror typeMirror) {
    // typeMirror belongs to the type model system, not Class<?>.
    System.out.println(typeMirror);
}
```

This is a snippet inside a processor with a variable `value` of type `AnnotationValue`, requiring `TypeMirror` to be imported.

Do not write:

```java
// Wrong for an annotation value containing a Class literal:
Class<?> clazz = (Class<?>) value.getValue();
```

Reason: in the language model, a class literal uses `TypeMirror`. This is a fundamental difference from a runtime annotation proxy having a method of type `Class<?>`.

## 9. How Do AnnotationMirror and TypeMirror Differ?

Their names look similar, yet they describe different things.

| Type | Represents | Example |
| --- | --- | --- |
| `Element` | A declared Java program element: class, method, field, parameter... | `TypeElement` for `CheckoutService` |
| `TypeMirror` | **A Java type** in the compiler model | types `java.lang.String`, `List<String>` |
| `AnnotationMirror` | **A single annotation usage** | `@Review(value = "checkout", ...)` |
| `AnnotationValue` | **The value of an annotation element** | `"checkout"`, `3`, `String.class` in model form |
| `ExecutableElement` | An executable element/method declaration in the model | `Review.retries()` |

`AnnotationMirror.getAnnotationType()` returns a **`DeclaredType`**, a kind of `TypeMirror` representing **the annotation type**. However, `AnnotationMirror` itself is not a `TypeMirror`: one is **a metadata usage**, while the other is **a type**.

For a class literal in an annotation, **`AnnotationValue.getValue()` returns a `TypeMirror`**. For a nested annotation, **`AnnotationValue.getValue()` returns an `AnnotationMirror`**. These two cases must be distinguished when writing a general-purpose visitor.

## 10. Round-Based Annotation Processing and Which Sources Are Read?

An `AbstractProcessor` participates in javac's processing rounds. In each round, the compiler provides a `RoundEnvironment` and the set of annotation types that the processor can handle.

Example:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    if (roundEnv.processingOver()) {
        return false;
    }

    // Read the annotated elements in the current round.
    return false;
}
```

`roundEnv.getElementsAnnotatedWith(type)` finds the annotated elements according to the rules of annotation processing in that round. When a processor generates additional sources, the compiler can process those new sources in the next round.

Therefore:

- Do not assume `process` is called only **once**.
- Do not generate the same file multiple times without managing state and processing rounds.
- In a production processor, use `processingEnv.getMessager().printMessage(...)` to emit diagnostics anchored to an `Element` or `AnnotationMirror` when needed.
- Specify `@SupportedAnnotationTypes` and `@SupportedSourceVersion` accurately for the supported annotation/module/source level.
- Returning `true` from `process` means **claiming** the processed annotation types; it does not mean the annotation value is a boolean or whether the processor succeeded or failed. The example returns `false` so as not to claim them.

**A note on Retention:** an annotation with `SOURCE` retention can still be read while the processor works on the source. However, the compiler does not retain it in the `.class` file for runtime Reflection to find. Do not choose `RUNTIME` retention just because you think an annotation processor must use Reflection.

## 11. Repeatable Annotations and AnnotationMirror

Given:

```java
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@interface Tags {
    Tag[] value();
}

@Tag("a")
@Tag("b")
class Sample {}
```

The compiler has rules for representing repeated annotations through a **container annotation**. When using the compile-time model:

- `Element.getAnnotationMirrors()` returns a list of annotation mirrors according to the language model contract. For repeated annotations, how the annotations appear in the mirror list relates to the **container** rules; do not assume there are always two separate top-level `AnnotationMirror`s for two `@Tag` annotations.
- An `AnnotationMirror` for the `Tags` container has a `value()` element whose `AnnotationValue` holds a **list of `AnnotationValue`s**, where each item can hold an `AnnotationMirror` for an individual `@Tag`.
- A general-purpose tool that wants to read every `Tag` must inspect both direct annotations and the appropriate container annotation, or use the appropriate type-based API when supported and when its semantics meet the requirements.

Do not simply cast the result of `getAnnotationMirrors()` to an array of runtime annotation proxies, and do not assume `getValue()` for the container array is a runtime Java `Tag[]`.

If order matters, preserve the order from the `AnnotationValue` items in the container array. If `@Inherited` support is needed, distinguish the lookup semantics of the compile-time model from runtime Reflection APIs and verify against the specific contract.

## 12. Distinguishing the Model API getAnnotation(...) from Java Reflection

`Element` also has the convenience methods `getAnnotation(Class<A>)` and `getAnnotationsByType(Class<A>)`. They belong to `AnnotatedConstruct` in the language-model API and **do not mean** an annotation processor should depend on runtime Reflection of the class being compiled.

When an annotation type has an element of type `Class<?>`, using an annotation proxy from these convenience APIs can result in a **`MirroredTypeException`** (or related exceptions involving type mirrors). The reason is that the `Class` object of the type referenced in source may not be loaded yet or may not be suitable to represent as a runtime class inside the processor.

In the main example:

```java
@Review(handler = String.class, value = "checkout")
class CheckoutService {}
```

If a processor attempts to call accessors on an annotation proxy in a runtime-like manner, it may have to deal with the issue of the class literal being represented as a type mirror. A robust approach is to read:

```java
AnnotationMirror mirror = ...;       // Mirror of @Review
AnnotationValue handlerValue = ...;  // Value of the handler() element
TypeMirror handlerType =
        (TypeMirror) handlerValue.getValue();
```

This is a snippet, not a standalone file; in practice you must select `handlerValue` from the mirror's element values map and check the type properly before casting.

**Design rule:** when processing source code or comparing Java types being compiled, prefer `javax.lang.model` data (`Element`/`TypeMirror`/`AnnotationMirror`) rather than forcing the business class to already exist as a runtime `Class<?>`.

## 13. Common Mistakes

**"`AnnotationMirror` is `java.lang.annotation.Annotation`."** False. It is the compile-time model of **a single annotation usage**, not a runtime annotation proxy instance.

**"`AnnotationValue.getValue()` always returns the element's exact Java value type."** False for `Class`, enums, nested annotations, and arrays; these cases respectively use `TypeMirror`, `VariableElement`, `AnnotationMirror`, and `List<? extends AnnotationValue>`.

**"`mirror.getElementValues()` always includes elements with defaults."** False. It only contains explicitly written elements. Use `getElementValuesWithDefaults` if you need the complete result.

**"A missing element in the map means the default is `null`."** False. In the Java language, an annotation element has no valid `null` value. Being absent means **not explicitly written**; read defaults through the appropriate API.

**"`Class<?>` in an annotation can be cast directly from getValue()."** False. The language model uses `TypeMirror`.

**"An enum constant is a runtime enum object."** False. The language model returns a `VariableElement`.

**"An array returns `String[]` or `AnnotationMirror[]`."** False. An array's `AnnotationValue` returns a list of **`AnnotationValue`**s.

**"A processor only runs if the annotation is retained until `RUNTIME`."** False. A processor can process annotations in source code that have `SOURCE` retention.

**"`getAnnotationMirrors()` is a way to read .class files via Reflection."** False. It is a compiler model API; bytecode readers and Reflection are different mechanisms.

**"AnnotationValue.toString() restores the exact string typed by the user."** False. The value model may lose the distinction between `1 + 2` and `3`, or source syntax/formatting details.

**"Returning false from process means the processor failed."** False. This boolean relates to claiming annotation types in the processing pipeline.

## 14. Self-Check Exercises

### Exercise 1 — Two Different Maps

Given `@Review("default")` and the `Review` declaration in Section 6, predict:

- Which keys are present in `mirror.getElementValues()`?
- Which keys appear after `getElementValuesWithDefaults(mirror)`?

**Answer:** the first map has only `value`. The second map contains `value`, `retries`, `handler`, `priority`, `tag`, `labels`.

### Exercise 2 — Class Literal

For `@Review(handler = String.class, value = "checkout")`, can `AnnotationValue.getValue()` of `handler` be cast to `Class<?>`?

**Answer:** no. It returns a `TypeMirror` representing `java.lang.String` in the compiler model.

### Exercise 3 — Enum and Nested Annotation

Why does the visitor use `visitEnumConstant(VariableElement, ...)` for `Priority.HIGH` and `visitAnnotation(AnnotationMirror, ...)` for `@Tag("public")`?

**Answer:** an enum constant is a declared element of the enum type; a nested annotation is a separate annotation usage with its own type and element values. Neither is a business object instance instantiated by the source code.

### Exercise 4 — Array

For `labels = {"api", "payment"}`, what form does `AnnotationValue.getValue()` of `labels` return?

**Answer:** a `List<? extends AnnotationValue>` with two elements; each child element returns the corresponding string via `getValue()` or `visitString`.

### Exercise 5 — SOURCE Retention

Why can `ReviewProcessor` read `@Review` even though `Review` is declared with `@Retention(SOURCE)`?

**Answer:** the processor runs **while the compiler analyzes source code**. `SOURCE` retention only specifies that this data does not need to be kept in the output class file; it does not remove it from the source model during compilation.

### Exercise 6 — Nested Annotation Value

To retrieve the string `"public"` inside `tag = @Tag("public")`, how do you interact with the `AnnotationMirror` of `Tag`?

**Answer:** use the APIs for reading the element values of the nested `AnnotationMirror`, locate the `value()` element, then retrieve the corresponding `AnnotationValue` and decode the string.

### Exercise 7 — Error When Reading Class via Proxy

Why shouldn't a processor base its logic on calling `Review review = element.getAnnotation(Review.class); Class<?> c = review.handler();` like a normal runtime Reflection API?

**Answer:** the types referenced in the source might not be loaded yet; the language-model proxy accessor for `Class` may throw `MirroredTypeException`. Use `AnnotationMirror` and `TypeMirror` to handle them independently of class loading.

### Exercise 8 — Real Build

Compile the four files from Section 6. Why are `-processorpath out` and `-processor ReviewProcessor` needed in the second command?

**Answer:** so javac can locate and invoke the processor compiled in Step 1. Packaging `META-INF/services` is not necessary when the processor is explicitly specified.

## 15. Checklist for Applying This to an Annotation Processor

1. **Read from the compiler model:** do you have the right annotated `Element`?
2. **Select the right annotation type:** have you checked `mirror.getAnnotationType()`?
3. **Distinguish explicit from default:** do you want only what is written in the source, or the result including defaults?
4. **Choose how to traverse values:** do you need full support for primitives, `String`, class literals, enums, nested annotations, and arrays?
5. **Avoid invalid runtime casts:** use `TypeMirror`, `VariableElement`, `AnnotationMirror`, and `List<AnnotationValue>` in the appropriate places.
6. **Nested annotations and arrays:** if deep data is needed, are you traversing recursively and preserving order?
7. **Do not depend on loading business classes:** avoid using `Class<?>` to represent types being analyzed by the compiler.
8. **Handle rounds:** do you check `processingOver()` and avoid generating duplicate files?
9. **Verify the source version:** is the processor declared and compiled with an appropriate source level?
10. **Use appropriate diagnostics:** when an invalid configuration is detected, do you report errors anchored to an `Element` instead of only printing to the console?
11. **Test all cases:** fully specified annotations, annotations using defaults, empty arrays, class literals, enums, and nested annotations?
12. **Review javac output:** have you verified the exact explicit information and default values without inferring from `toString()`?

**Conclusion:** `AnnotationMirror` describes **a single annotation usage in the compile-time model**, while `AnnotationValue` describes **each value assigned to annotation elements**. `getElementValues()` provides explicitly written data; `getElementValuesWithDefaults()` supplements it with default values. Thanks to `TypeMirror`, `VariableElement`, nested `AnnotationMirror`, and the visitor for `AnnotationValue`, a processor can analyze Java metadata with the proper types **right while javac is working**, without needing to turn unfinished source code into runtime classes to use Reflection.
