# Reading Class Values via the Type Model and Handling MirroredTypeException in Java Annotation Processing

In Java, an annotation element can return `Class<?>` or `Class<?>[]`:

~~~java
@interface LinkedTo {
    Class<?> value();
    Class<?>[] extras() default {};
}
~~~

When using annotations at **application runtime**, we typically expect to obtain a `Class<?>` object from `annotation.value()`. However, when writing an **annotation processor** that runs at compile time via `javac`, the kind of information to work with is the **Java Language Model** — specifically `TypeMirror` and `TypeElement`. If the processor invokes a `Class`-typed element on the annotation proxy provided by the compiler, the API may throw `MirroredTypeException` to pass the **described type** to the processor without loading that class into the compiler's JVM. For `Class[]`, the corresponding API is `MirroredTypesException`.

This lesson explains why the exception here is an **intentional API mechanism**, how to handle it properly with `TypeMirror`, how to read `AnnotationMirror` directly (often more suitable when building tooling), along with a Java 17+ example that actually compiles and runs an annotation processor.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish `java.lang.Class<?>` in runtime Reflection from `javax.lang.model.type.TypeMirror` in the compile-time language model.
- Explain why the compiler cannot necessarily load a class written as `SomeType.class` in the source code being compiled.
- Catch `MirroredTypeException` when reading a `Class<?>` element and retrieve the `TypeMirror` using `getTypeMirror()`.
- Catch `MirroredTypesException` for `Class<?>[]` and retrieve the list of `TypeMirror` instances via `getTypeMirrors()`.
- Read annotations via `Element.getAnnotationMirrors()` / `AnnotationMirror` / `AnnotationValue` without invoking a proxy element returning `Class<?>`.
- Distinguish `AnnotationMirror.getElementValues()` (explicitly specified values) from `Elements.getElementValuesWithDefaults()` (including defaults).
- Use `Types.isSameType(...)`, `Types.isSubtype(...)`, and `Types.asElement(...)` in the appropriate contexts instead of `Class<?>` comparisons.
- Choose the right strategy for handling missing/unresolved types, type mirrors with `TypeKind.ERROR`, and annotation processing rounds.
- Verify a `SOURCE`-retention processor using two `javac --release 17` commands.

## 2. Two Worlds: Runtime Reflection and the Compile-Time Language Model

### 2.1. At Runtime: `Class<?>` Represents a Class Known to the Runtime Environment

A runtime program can declare:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Handler {
    Class<?> value();
}

@Handler(String.class)
class RuntimeExample {}
~~~

If the annotation is kept with `RUNTIME` retention and the referenced class can be loaded, it can be queried:

~~~java
Class<?> clazz = RuntimeExample.class
        .getAnnotation(Handler.class)
        .value();

System.out.println(clazz.getName()); // java.lang.String
~~~

The two blocks above are snippets in the same illustrative context; place them in a valid file or IDE when practicing. Runtime Reflection works with class objects already understood by the JVM through its loading/linking mechanism. On a `Class<?>` object, you can obtain its name, superclass, methods, and fields using the Reflection API.

### 2.2. At Compile Time: The Compiler Models Types Before the Program Runs

An annotation processor implements `javax.annotation.processing.Processor`, typically extending `AbstractProcessor`. It receives objects belonging to the Java Language Model:

| Role | Primary API |
| --- | --- |
| A declaration such as class/interface/method/field | `javax.lang.model.element.Element` |
| Declaration of a class/interface type | `TypeElement` |
| A **type** in the program being compiled | `TypeMirror` |
| An annotation appearing on a declaration | `AnnotationMirror` |
| An element value of an annotation | `AnnotationValue` |
| Utilities for working with types | `processingEnv.getTypeUtils()`, `Types` interface |
| Utilities for working with declarations and annotations | `processingEnv.getElementUtils()`, `Elements` interface |

For example, the source contains:

~~~java
@LinkedTo(java.util.List.class)
public class Example {}
~~~

The compiler needs to know that this is a reference to **the type `java.util.List`**, yet creating a `Class<java.util.List>` object is not the central interface of the source model. More importantly, the referenced type might be a class **currently being compiled**, generated in a later round, or not yet ready to be loaded by the processor's class loader.

Therefore, in a processor, the appropriate question is usually **"which type is referenced, and what type relationships does it have?"**, not **"how do I call `Class.forName` to load it?"**.

## 3. `MirroredTypeException`: A Signal Shifting from `Class` to `TypeMirror`

The `javax.lang.model.element.Element.getAnnotation(Class<A>)` API can provide a proxy implementing the annotation type's interface. If that annotation has an element returning `Class`, invoking the element in a compile-time context may throw:

~~~java
javax.lang.model.type.MirroredTypeException
~~~

This is an unchecked exception with the method:

~~~java
TypeMirror mirror = exception.getTypeMirror();
~~~

The returned `TypeMirror` models the type declared in the annotation, for example `java.util.List`. Instead of treating the exception as "breaking the processor", in this case **the processor should use the type delivered with the exception**.

Standard pattern:

~~~java
LinkedTo annotation = element.getAnnotation(LinkedTo.class);

TypeMirror referencedType;
try {
    annotation.value(); // Class<?>: in a processor, this will throw MirroredTypeException.
    throw new AssertionError("Expected MirroredTypeException in this processor");
} catch (MirroredTypeException exception) {
    referencedType = exception.getTypeMirror();
}
~~~

The pattern above assumes it is running inside a processor, `element` is valid, and `LinkedTo` and `MirroredTypeException` have been imported. Because this is a way to verify the annotation proxy behavior of the compiler in use, the snippet with `AssertionError` is suited for **learning examples**; production libraries should choose the appropriate language model API and should not necessarily treat every implementation that manages to return a `Class` as an error.

Note:

- `MirroredTypeException` contains a **`TypeMirror`**, not a `Class<?>`.
- `getTypeMirror()` can return `null` if the exception has been serialized/deserialized according to the API contract; normally, a processor that catches the exception directly will receive the mirror.
- There is no need to call `Class.forName(...)` to recover the type; that is a step in the wrong direction if you only want to inspect type metadata.
- `TypeMirror.toString()` can provide a useful display name such as `java.util.List`, but do not treat that string as the sole basis for all type-relationship checks.

### Why Shouldn't You Try Calling `annotation.value().getName()`?

The snippet:

~~~java
String name = annotation.value().getName();
~~~

looks natural, but during source processing it can throw `MirroredTypeException` **right at the `annotation.value()` call**; the `getName()` part is never executed. Broadening the catch block around the entire statement can still read the type mirror, but a cleaner solution is to read the `TypeMirror` intentionally.

In a processor, the class of the annotation type (`LinkedTo.class`) must be available to the processor in order to call `getAnnotation(LinkedTo.class)`; that does **not** mean the class **referenced in the `value()` element** is already available to load.

## 4. `MirroredTypesException` for `Class<?>[]`

If an annotation declares an array of class literals:

~~~java
@interface Dependencies {
    Class<?>[] value();
}
~~~

And the user writes:

~~~java
@Dependencies({String.class, Runnable.class})
class ExampleDependencies {}
~~~

Then when the processor reads `annotation.value()`, it may throw **`MirroredTypesException`**, with:

~~~java
List<? extends TypeMirror> types =
        exception.getTypeMirrors();
~~~

Comparison:

| Element Value | Compile-Time Exception | Language Model Retrieval API |
| --- | --- | --- |
| `Class<?> clazz()` | `MirroredTypeException` | `getTypeMirror()` |
| `Class<?>[] classes()` | `MirroredTypesException` | `getTypeMirrors()` |

`MirroredTypeException` **extends** `MirroredTypesException`, so when multiple catch branches appear together, the subclass branch must come before the superclass branch. For two separate elements as in the main example, we catch them in **two separate `try` blocks** so there is no conflict.

Pattern:

~~~java
List<? extends TypeMirror> types;
try {
    annotation.extras();
    throw new AssertionError("Expected MirroredTypesException");
} catch (MirroredTypesException exception) {
    types = exception.getTypeMirrors();
}
~~~

This is an example targeting compile time. In normal application runtime Reflection, reading `Class<?>[]` typically returns an array of class objects when the classes can be loaded.

An annotation array can be written in single-element shorthand at the use site, yet **its return type is still `Class<?>[]`** and in annotation processing it corresponds to a list of type mirrors; do not treat it like a single `Class<?>` because of the shorthand syntax.

## 5. Complete Java 17+ Example Verifying Both Proxy and AnnotationMirror

We will build a processor consisting of three files in the `demo` package. The target annotation has `SOURCE` retention to demonstrate that **annotation processing does not require `RUNTIME` retention**. The compiler analyzes annotations right as it compiles the source.

Directory structure:

~~~text
src/
  demo/
    LinkedTo.java
    LinkProcessor.java
    Example.java
build/           (output directory for .class files)
~~~

### 5.1. `src/demo/LinkedTo.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface LinkedTo {
    Class<?> value();

    Class<?>[] extras() default {
        String.class, Runnable.class
    };
}
~~~

`value()` is required, while `extras()` defaults to two class literals. Note that a `Class<?>` annotation element is used **to reference a type**; no code will instantiate `String` or `Runnable` from these literals.

### 5.2. `src/demo/LinkProcessor.java`

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.AnnotationValue;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.MirroredTypeException;
import javax.lang.model.type.MirroredTypesException;
import javax.lang.model.type.TypeMirror;

@SupportedAnnotationTypes("demo.LinkedTo")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class LinkProcessor extends AbstractProcessor {

    @Override
    public boolean process(Set<? extends TypeElement> types,
                           RoundEnvironment round) {

        for (Element element :
                round.getElementsAnnotatedWith(LinkedTo.class)) {

            // Approach 1: annotation proxy + exception containing TypeMirror.
            LinkedTo annotation =
                    element.getAnnotation(LinkedTo.class);

            TypeMirror single;
            List<? extends TypeMirror> multiple;

            try {
                annotation.value();
                throw new AssertionError(
                        "Class loaded unexpectedly in this demo");
            } catch (MirroredTypeException exception) {
                single = exception.getTypeMirror();
            }

            try {
                annotation.extras();
                throw new AssertionError(
                        "Class array loaded unexpectedly in this demo");
            } catch (MirroredTypesException exception) {
                multiple = exception.getTypeMirrors();
            }

            System.out.println("proxySingle=" + single);
            System.out.println("proxyArray=" +
                    multiple.stream()
                            .map(Object::toString)
                            .collect(Collectors.joining(",")));

            // Approach 2: read the annotation model directly without invoking Class.
            for (AnnotationMirror mirror :
                    element.getAnnotationMirrors()) {

                if (!mirror.getAnnotationType()
                        .toString().equals("demo.LinkedTo")) {
                    continue;
                }

                Map<? extends ExecutableElement,
                        ? extends AnnotationValue> explicit =
                        mirror.getElementValues();

                Map<? extends ExecutableElement,
                        ? extends AnnotationValue> withDefaults =
                        processingEnv.getElementUtils()
                                .getElementValuesWithDefaults(mirror);

                System.out.println("explicit=" + explicit.size()
                        + ",withDefaults=" + withDefaults.size());

                for (var entry : withDefaults.entrySet()) {
                    String key = entry.getKey().getSimpleName().toString();

                    if (key.equals("value")) {
                        TypeMirror fromMirror =
                                (TypeMirror) entry.getValue().getValue();

                        System.out.println("mirrorSingle=" + fromMirror);
                        System.out.println("sameType=" +
                                processingEnv.getTypeUtils()
                                        .isSameType(single, fromMirror));
                    } else if (key.equals("extras")) {
                        @SuppressWarnings("unchecked")
                        List<? extends AnnotationValue> array =
                                (List<? extends AnnotationValue>)
                                        entry.getValue().getValue();

                        System.out.println("mirrorArray=" +
                                array.stream()
                                        .map(item ->
                                                item.getValue().toString())
                                        .collect(Collectors.joining(",")));
                    }
                }
            }
        }
        return true;
    }
}
~~~

The code uses `var` for the local loop variable (valid since Java 10) and `Collectors.joining(...)` to concatenate the names in the exact order they appear in the array. The processor is automatically instantiated by the `javac` environment; learners do not need to write a `main` method for the processor.

**Note on `AssertionError`:** this is an intentional check in the **javac test fixture** to confirm that execution takes the exception path. In a processor that must support multiple implementations, prefer the `AnnotationMirror` path or design an appropriate fallback rather than expecting every implementation to throw a single exception in the exact same way as the example.

### 5.3. `src/demo/Example.java`

~~~java
package demo;

@LinkedTo(java.util.List.class)
public class Example {}
~~~

`Example` explicitly specifies only `value()`. The `extras()` element does not appear in the `@LinkedTo` line, so it receives the default `{String.class, Runnable.class}`.

### 5.4. Compiling and Running Processing

Create the `build` directory and run the following in the directory containing `src`:

~~~bash
mkdir -p build

javac --release 17 -proc:none -d build \
  src/demo/LinkedTo.java src/demo/LinkProcessor.java

javac --release 17 -cp build -processorpath build \
  -processor demo.LinkProcessor -d build \
  src/demo/Example.java
~~~

The line-continuation backslash `\` is Bash/POSIX shell syntax. On Windows PowerShell, create the directory with `New-Item -ItemType Directory -Force build` or `mkdir build`, and write each `javac` command on a single line:

~~~powershell
javac --release 17 -proc:none -d build src/demo/LinkedTo.java src/demo/LinkProcessor.java
javac --release 17 -cp build -processorpath build -processor demo.LinkProcessor -d build src/demo/Example.java
~~~

- The first command compiles the annotation type and the processor class, using `-proc:none` to avoid running processors while building the processor itself.
- `-cp build` lets the compiler find `demo.LinkedTo` when compiling the target source.
- `-processorpath build` lets the compiler locate `demo.LinkProcessor`; `-processor` selects it explicitly.
- `--release 17` ensures the code is compatible with the Java 17 language level and APIs. The processor runs inside the compiler's JVM rather than via a `java Example` command.
- `-d build` writes class files into the build directory; no additional source files are generated in this demo.

**Output printed when the second `javac` command runs:**

~~~text
proxySingle=java.util.List
proxyArray=java.lang.String,java.lang.Runnable
explicit=1,withDefaults=2
mirrorSingle=java.util.List
sameType=true
mirrorArray=java.lang.String,java.lang.Runnable
~~~

These lines were compiled and verified with `javac --release 17` on a modern JDK.

### 5.5. Output Analysis

1. `proxySingle=java.util.List`: when the processor calls `annotation.value()`, `MirroredTypeException` provides the `TypeMirror` for `java.util.List`.
2. `proxyArray=java.lang.String,java.lang.Runnable`: `MirroredTypesException` provides the list of mirrors in the order of the default values of `extras()`.
3. `explicit=1,withDefaults=2`: the author of `@LinkedTo` supplied only `value`; `AnnotationMirror.getElementValues()` has one entry. `Elements.getElementValuesWithDefaults(...)` adds `extras`, resulting in two entries.
4. `mirrorSingle=java.util.List`: the value of a `Class`-typed element in the annotation model is a `TypeMirror`, not a `Class<?>`.
5. `sameType=true`: `Types.isSameType(single, fromMirror)` compares the two type mirrors and confirms they represent the same type.
6. `mirrorArray=java.lang.String,java.lang.Runnable`: `AnnotationValue.getValue()` for the array is a list of `AnnotationValue` instances; each element has a `TypeMirror` as its value.

There is no need to load `java.util.List` via `Class.forName`; the processor works strictly with the type model. The example also shows that `SOURCE` retention can still be used in annotation processing.

## 6. How to Read `AnnotationMirror` Without Using Exceptions

Although catching `MirroredTypeException` is a valid and useful technique when you already have an annotation proxy, **direct access to the language model** is often more appropriate in a general-purpose processor or when handling annotations whose interfaces are not on the processor's compile classpath.

### 6.1. Step 1 — Find the Desired Annotation Mirror

~~~java
for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
    if (mirror.getAnnotationType().toString()
            .equals("demo.LinkedTo")) {
        // Found the target annotation.
    }
}
~~~

This code runs **inside the processor**. `AnnotationMirror.getAnnotationType()` returns the annotation's `DeclaredType`, letting us know which annotation is being represented.

Comparing the fully qualified name with `toString()` is a simple approach for a demo. In a larger processor, you can use a `TypeElement` obtained from `Elements.getTypeElement("demo.LinkedTo")` and compare types with `Types.isSameType(...)`, or compare `TypeElement.getQualifiedName()` to avoid relying on string formatting.

### 6.2. Step 2 — Decide Whether Default Values Are Needed

~~~java
Map<? extends ExecutableElement, ? extends AnnotationValue> explicit =
        mirror.getElementValues();

Map<? extends ExecutableElement, ? extends AnnotationValue> complete =
        processingEnv.getElementUtils()
                .getElementValuesWithDefaults(mirror);
~~~

The difference:

| API | Includes default elements if omitted at the use site? |
| --- | --- |
| `AnnotationMirror.getElementValues()` | **No**; contains only explicitly specified element values |
| `Elements.getElementValuesWithDefaults(mirror)` | **Yes**; returns values along with defaults for the needed elements |

If you want to know what the source author explicitly wrote, choose `getElementValues()`. If you want to read the **full effective** configuration to validate or generate code, typically choose `getElementValuesWithDefaults()`.

The map keys are `ExecutableElement` instances describing the annotation elements such as `value()` and `extras()`, **not raw string keys**. The example code converts a key to its name via `entry.getKey().getSimpleName().toString()`.

### 6.3. Step 3 — Understand the Data Types Returned by `AnnotationValue.getValue()`

The `AnnotationValue.getValue()` API returns `Object`, but the actual value falls within a specified set of types:

| Annotation Element Type | Value Received via the Model |
| --- | --- |
| `int`, `boolean`, `long`... | Wrapper such as `Integer`, `Boolean`, `Long` |
| `String` | `String` |
| `Class<?>` or `Class<? extends X>` | `TypeMirror` |
| Enum element | `VariableElement` representing the enum constant |
| Nested annotation | `AnnotationMirror` |
| Array, including `Class<?>[]` | `List<? extends AnnotationValue>`, where each element is a model value |

For a single `Class<?>`:

~~~java
TypeMirror type =
        (TypeMirror) entry.getValue().getValue();
~~~

For `Class<?>[]`:

~~~java
@SuppressWarnings("unchecked")
List<? extends AnnotationValue> values =
        (List<? extends AnnotationValue>)
                entry.getValue().getValue();

for (AnnotationValue value : values) {
    TypeMirror type = (TypeMirror) value.getValue();
    System.out.println(type);
}
~~~

The two snippets above are **illustrative processor fragments**, assuming the `entry` variable comes from the map above. Arrays are modeled as a list of `AnnotationValue` instances, **not** a `List<TypeMirror>` at the outer level and not a `Class<?>[]`.

If you want code that handles all annotation value types rigorously, look at `AnnotationValueVisitor` / `SimpleAnnotationValueVisitor*` instead of casting based on element names; for a known annotation type, targeted casting as shown in the demo remains easy to learn and direct.

## 7. Using `TypeMirror` Properly in the Compiler

### 7.1. `TypeMirror` Is Not `Class<?>`

The two object types serve two different purposes:

| Property | `Class<?>` | `TypeMirror` |
| --- | --- | --- |
| Primary world | JVM/runtime Reflection | Compile-time language model |
| Represents | A class known to the runtime system | A Java type modeled by the compiler |
| Class loading dependency | May require class loading | Not a class loading operation |
| Type relationship analysis | `isAssignableFrom(...)` on class | `Types.isAssignable(...)`, `isSubtype(...)`, `isSameType(...)` |
| Retrieving declaration | Reflection class/method/field | `Types.asElement(...)`, `TypeElement`, and language-model elements |
| Usage in annotation processors | Avoid for source types being compiled | Fits the compiler-managed model |

Although `TypeMirror.toString()` usually produces a sufficiently clear name representation, applications that need **semantic type checking** should use `Types` rather than string comparison.

For example:

~~~java
Types typeUtils = processingEnv.getTypeUtils();
boolean same = typeUtils.isSameType(left, right);
boolean compatible = typeUtils.isAssignable(left, right);
boolean subclassOrSame =
        typeUtils.isSubtype(left, right);
~~~

`left` and `right` must be valid `TypeMirror` instances provided by the processing environment. `isSameType` checks type equivalence; `isAssignable` checks assignability; `isSubtype` checks the subtype relationship. These three questions are **not the same test**.

### 7.2. Obtaining `TypeElement` When the Value Points to a Class/Interface

If you want to obtain the **declaration** of a type:

~~~java
Element typeElement =
        processingEnv.getTypeUtils().asElement(typeMirror);

if (typeElement instanceof TypeElement declaration) {
    System.out.println(declaration.getQualifiedName());
}
~~~

For a mirror representing a **declared class/interface type** such as `java.util.List`, `asElement(...)` can return a `TypeElement` so you can inspect its name, modifiers, declared methods, and so on.

However, not every `TypeMirror` represents a declared type:

- `int.class` describes a primitive type and has no corresponding class declaration `TypeElement`.
- `String[].class` describes an array type, for which you may need to inspect `ArrayType.getComponentType()`.
- `void.class` (where Java allows it) relates to a pseudo-type.
- An unresolved type can appear as an `ErrorType` / `TypeKind.ERROR`.

Therefore, check `mirror.getKind()` and the result of `asElement(...)` before casting. Do not assume that a `Class<?>` annotation element means the mirror always has `TypeKind.DECLARED`.

### 7.3. Comparing Against Another Type in the Compilation Environment

For example, suppose you need to check whether the marked type is compatible with `java.lang.Runnable`:

~~~java
TypeElement runnableElement =
        processingEnv.getElementUtils()
                .getTypeElement("java.lang.Runnable");

if (runnableElement != null) {
    TypeMirror runnableType = runnableElement.asType();
    boolean compatible = processingEnv.getTypeUtils()
            .isAssignable(typeMirror, runnableType);
}
~~~

If `typeMirror` is a type assignable to `Runnable`, `compatible` is `true`. Do not replace this check with `typeMirror.toString().contains("Runnable")`, because string checks do not understand subtypes, interface implementations, or generic type relations.

When you need to compare for the **exact same type** regardless of how it is referenced, `isSameType` is more appropriate. For generics, consider erasure and parameterization depending on your goal, rather than stripping `<...>` manually via text processing.

### 7.4. Unresolved Types and Generated Sources

Annotation processors often run across **multiple rounds**; they may encounter incomplete types or classes that will be generated by another processor. Depending on the compiler and source state, a `TypeMirror` may be an `ErrorType`. In that case:

- Do not call `Class.forName(...)` to "rescue" a type that does not yet exist.
- Check `getKind() == TypeKind.ERROR` when necessary and emit a clear diagnostic.
- If the workflow allows, reprocess the information in a subsequent round once the files have been generated or resolved.
- Avoid caching `TypeMirror`/`Element` beyond the processing environment in which they were provided, especially across different rounds or compilations, without a clear understanding of the API contract.

Users of the processor need helpful diagnostics such as "the referenced type could not be resolved", not the stacktrace of an unnecessary class loading operation.

## 8. Default `Class` Values and the Difference Between the Two APIs

Given the declaration:

~~~java
@interface Strategy {
    Class<?> primary();
    Class<?>[] fallback() default {String.class};
}
~~~

And the usage:

~~~java
@Strategy(primary = java.util.Map.class)
class Configuration {}
~~~

**When reading through an annotation proxy** in a processor, calling `primary()` can lead to `MirroredTypeException`; calling `fallback()` can lead to `MirroredTypesException` even when the value is not written at the usage site, because the proxy provides effective values including defaults.

**When reading through `AnnotationMirror`**, `getElementValues()` usually contains only `primary` because `fallback` is omitted at the use site. Use `Elements.getElementValuesWithDefaults()` to obtain both.

Thus there are two distinct kinds of requirements:

- **Track what the user actually wrote in source**: use the map from `getElementValues()`.
- **Obtain the effective configuration**: use `getElementValuesWithDefaults()`, then read the appropriate model value of type `TypeMirror` or list of `AnnotationValue` instances.

You should not change an annotation type's retention to `RUNTIME` just to retrieve `Class<?>` inside a processor. Retention describes how long the annotation is retained; it does not alter the **compile-time language model** nature of a processor.

## 9. When to Catch Exceptions vs. When to Use AnnotationMirror?

**Approach A — invoke the annotation proxy and catch `MirroredTypeException`:**

Suitable when the processor **already knows the annotation type at compile time** and existing code uses `element.getAnnotation(MyAnnotation.class)` to read other elements (strings, numbers, enums). This approach is concise for some cases, but requires special exception handling for `Class` and `Class[]`.

**Approach B — read `AnnotationMirror`:**

Suitable when writing a **general-purpose processor** or tooling validator, when you need to preserve source structure or distinguish **explicit/default** values, when the annotation type is not directly on the compile classpath of the processor code, or when you want to avoid proxy methods returning `Class`. This approach aligns with the language model mindset and scales cleanly to enum, nested annotation, and array elements.

There is no requirement that every tool use a single approach. What matters is **never trying to load the target class just to know its type at compile time**.

Some common mistakes when implementing this yourself:

- Catching `ClassNotFoundException` instead of `MirroredTypeException`. In this proxy path, the central exception is `MirroredTypeException` or `MirroredTypesException`, not an ordinary `Class.forName` failure.
- Confusing `MirroredTypeException` with `TypeNotPresentException` from other runtime contexts. Check carefully which API you are calling and what the compiler/proxy provides.
- Calling `annotation.value().getCanonicalName()` inside `try` without realizing the exception is thrown **before** the `getCanonicalName()` call.
- Casting `AnnotationValue.getValue()` directly to `Class<?>`: in the language model, for a class literal it is a `TypeMirror`.
- Casting an array value directly to `List<TypeMirror>`: the outer layer is `List<? extends AnnotationValue>`.
- Filtering annotations by the simple name `"LinkedTo"` in a multi-package project; two different annotation types can share the same simple name.
- Forgetting default values and assuming `getElementValues().size() == 1` means the annotation only has one element.
- Using `TypeMirror.toString()` as the final answer for subtype/generic checks; use `Types` to perform semantic type checks.
- Trying to retain a `TypeMirror` across compiler invocations and compare it as a globally immutable runtime type; the model belongs to the compilation environment.

## 10. Cases Requiring Careful Consideration

### 10.1. Primitives, Arrays, and `void.class`

A `Class<?>` annotation element can hold `int.class`, `String[].class`, or `void.class` where Java permits. When retrieving the `TypeMirror`, do not assume it is a `DeclaredType` with a `TypeElement`. Inspect `TypeKind` or handle it with an appropriate `TypeVisitor`.

If you only need the kind of type for reporting diagnostics, `getKind()` and `toString()` may already suffice; if you need type relationships or declarations, use the corresponding APIs.

### 10.2. `Class<? extends Interface>` Still Produces a Model Type

For example:

~~~java
@interface HandlerType {
    Class<? extends Runnable> value();
}
~~~

The compiler checks whether the type literal conforms to the `Runnable` bound according to Java's rules. In the processor, the element type is still a `Class`-valued annotation member, and its corresponding model should still be processed via `TypeMirror`. `Types.isAssignable(...)` allows checking compatibility when additional tool rules need to be verified.

### 10.3. Nested Annotations Containing `Class`

An annotation element can return a nested annotation:

~~~java
@interface Inner {
    Class<?> type();
}

@interface Outer {
    Inner nested();
}
~~~

If using a proxy, `outer.nested().type()` may throw `MirroredTypeException` at the `type()` member. If using the model, the `nested` `AnnotationValue` holds an **`AnnotationMirror`**, and `type` inside it holds a **`TypeMirror`**. Modeling nested annotations structurally reduces runtime assumptions.

### 10.4. Arrays and Ordering

For `Class<?>[]`, declaration order can be important information. `MirroredTypesException.getTypeMirrors()` and the `AnnotationValue` list represent the array elements in order. Do not convert them into a `Set<String>` if the logic requires preserving order or allowing duplicate values.

### 10.5. Portability and Build Environments

The example executes with standard `javac`. Tools based on the Java Compiler API, IDEs, or incremental compilers may differ in how they discover processors, display stdout/diagnostics, and order processing rounds. Do not design code that requires a specific class loader or relies on display strings when the `TypeMirror`/`Types` APIs provide direct functionality.

## 11. Leveled Practice Exercises

1. **Single Class:** Run the three-file program. Replace `@LinkedTo(java.util.List.class)` with `@LinkedTo(java.util.Map.class)` and predict the `proxySingle`, `mirrorSingle`, and `sameType` lines.
2. **Class array:** Override `extras = {Thread.class, Exception.class}` in `Example`. Predict why `explicit=2,withDefaults=2`, yet both array-reading paths yield the two new types.
3. **Default value:** Remove the `extras` argument completely at the usage site, and verify that `AnnotationMirror.getElementValues()` omits `extras` while `Elements.getElementValuesWithDefaults()` does not.
4. **Exception question:** Remove the `try/catch` around `annotation.value()`, let the compiler run, and observe the stacktrace. Restore the code and explain why this is not a `ClassNotFoundException`.
5. **Types API:** Obtain the `TypeElement` for `java.util.Collection`, then call `Types.isAssignable(single, collection.asType())` when `single` points to `java.util.List`. Predict the result and explain the interface relationship.
6. **Primitive:** Try `@LinkedTo(int.class)`. Observe `TypeMirror.getKind()` and explain why you should not unconditionally cast `Types.asElement(...)` to `TypeElement`.
7. **Array type:** Try `@LinkedTo(String[].class)`. Use `TypeKind.ARRAY` and `ArrayType.getComponentType()` to determine the element type.
8. **Nested model:** Create `@interface Inner { Class<?> clazz(); }` and `@interface Outer { Inner child(); }`, and apply it to a class. Traverse from `AnnotationMirror` to the `AnnotationValue` of `child`, then into the nested annotation model, and read the class literal as a `TypeMirror`.
9. **Visitor:** Replace the `instanceof`/casts with an `AnnotationValueVisitor` implementing `visitType` and `visitArray` branches. Write tests for `Class<?>`, `Class<?>[]`, and `String`.
10. **Diagnostic:** Replace `System.out.println` with `processingEnv.getMessager().printMessage(Diagnostic.Kind.NOTE, ...)` and show how the compiler/IDE displays the message on the source element being processed.
11. **Source-level behavior:** Change the retention of `LinkedTo` from `SOURCE` to `CLASS` or `RUNTIME`. Verify that the compile-time processor can still see the annotation and discuss runtime Reflection separately.
12. **Multi-round:** Create another processor that generates a class in the first round and an annotation referencing an appropriate class. Observe the type resolution states and rounds, and apply `TypeKind.ERROR` along with a diagnostics strategy instead of class loading.

## 12. Quick Reference Table

| Question | Takeaway |
| --- | --- |
| Should a `Class<?>` value in an annotation processor be read like runtime Reflection? | Not by default; prefer the `TypeMirror` model |
| What can happen when calling `Class<?> value()` on an annotation proxy? | `MirroredTypeException` |
| How do you retrieve the type from the exception? | `getTypeMirror()` |
| What can happen when calling `Class<?>[] extras()`? | `MirroredTypesException` |
| How do you retrieve the list of types from the exception? | `getTypeMirrors()` |
| Want to avoid proxy exceptions? | Traverse `AnnotationMirror` / `AnnotationValue` |
| What is `AnnotationValue.getValue()` for a class literal? | `TypeMirror` |
| What is `AnnotationValue.getValue()` for a Class array? | `List<? extends AnnotationValue>`, where each item holds a `TypeMirror` |
| Does `getElementValues()` automatically include defaults? | No |
| Which API includes defaults? | `Elements.getElementValuesWithDefaults(...)` |
| How do you compare two types in the compiler? | `Types.isSameType(...)` or other type-relationship APIs |
| Is `RUNTIME` retention required to process annotations at compile time? | No; `SOURCE` is still readable by an annotation processor |
| Should `Class.forName` be a required step? | No; loading classes is not the goal of the language model |

**Conclusion:** `Class`-typed annotation elements express **type information**, yet **runtime `Class<?>`** and **compile-time `TypeMirror`** belong to two different models. `MirroredTypeException` / `MirroredTypesException` serves as the bridge when you choose to read through the annotation proxy. When you need control over defaults, nested structures, or direct work with the Java language constructs being compiled, `AnnotationMirror` together with `AnnotationValue` and `Elements/Types` is the clearer, safer, and more extensible choice.

### References

- [Java SE 17 — MirroredTypeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/MirroredTypeException.html).
- [Java SE 17 — MirroredTypesException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/MirroredTypesException.html).
- [Java SE 17 — Element.getAnnotation](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/Element.html).
- [Java SE 17 — TypeMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html).
- [Java SE 17 — AnnotationMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html).
- [Java SE 17 — AnnotationValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationValue.html).
- [Java SE 17 — Elements.getElementValuesWithDefaults](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html#getElementValuesWithDefaults(javax.lang.model.element.AnnotationMirror)).
- [Java SE 17 — Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html).
- [Java SE 17 — Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html).
