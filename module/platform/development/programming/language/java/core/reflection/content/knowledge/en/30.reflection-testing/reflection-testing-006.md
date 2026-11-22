# Testing Runtime Annotations, Repeatable Annotations, and Type-Use Annotations in Java Reflection

Annotations in Java are metadata attached to declarations or type-use locations. When writing tools based on Reflection, merely seeing `@Something` syntax in source code **is not enough** to conclude the application will be able to read that annotation at runtime. The outcome also depends on `@Retention`, `@Target`, whether the annotation is repeated, the **location** where the annotation is placed, and the Reflection API used to read it.

This lesson guides you through designing automated tests for three easily confused cases:

1. **Runtime annotations:** does the annotation actually exist at runtime, and on the expected element?
2. **Repeatable annotations:** are multiple declarations retrieved completely via `getAnnotationsByType`?
3. **Type-use annotations:** is metadata attached to a *type-use site* (return type, parameter type, generic type argument, array, etc.) retrieved using the `AnnotatedType` API family instead of only reading annotations on the declaration element?

Examples run on **Java 17+**, without needing external libraries. In addition, the lesson clearly distinguishes cases requiring JUnit or running tests against the actual packaged artifact when building real tools.

## 1. Three Factors Determining Whether an Annotation Is Readable

An annotation can have three related configurations:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Action {
    String value();
}
```

- **`@Retention`** determines how long the annotation is retained.
- **`@Target`** specifies the valid locations where the annotation can be placed.
- **`@Repeatable`** allows declaring multiple instances of the same annotation type on a valid element/location, backed by a compatible container annotation.

### Retention policy

| Policy | How far does the compiler retain it? | Readable by Core Reflection at runtime? |
|---|---|---|
| `RetentionPolicy.SOURCE` | Source code only; no obligation to appear in the class file | No |
| `RetentionPolicy.CLASS` | Stored in the class file (default when `@Retention` is omitted), but the JVM is not required to retain it for Reflection | **No** via standard runtime annotation APIs |
| `RetentionPolicy.RUNTIME` | Retained for the JVM to expose via Reflection | **Yes**, when metadata still exists and is read at the right location |

A class file containing a `CLASS` annotation **does not mean** `Class.getAnnotation(...)` has to return the annotation object. Runtime tests must use `@Retention(RUNTIME)` if the framework needs to read the annotation at runtime.

### Target

Examples of common targets:

- `ElementType.TYPE`: class, interface, enum, record, or certain type declarations.
- `ElementType.METHOD`, `FIELD`, `CONSTRUCTOR`: the corresponding declaration elements.
- `ElementType.PARAMETER`: **parameter declaration** of a method/constructor.
- `ElementType.TYPE_USE`: **type-use site**, such as `List<@Mark String>`, return type, parameter type, array component, used superclass.
- `ElementType.TYPE_PARAMETER`: type parameter declaration such as `class Box<@Mark T>`.

**Crucial distinction:** an annotation with `@Target(PARAMETER)` is read via the parameter declaration annotation APIs, whereas an annotation with `@Target(TYPE_USE)` placed on the *type of a parameter* must be read via `getAnnotatedParameterTypes()`. If an annotation has multiple targets, inspect the exact location where it appears and where the compiler records the metadata.

## 2. Testing Runtime Annotations: Declaring and Reading at the Exact Location

Given:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeInfo {
    String value();
}

@RuntimeInfo("active")
class Plugin {}
```

A test must verify both **presence** and **value**:

```java
RuntimeInfo info = Plugin.class.getAnnotation(RuntimeInfo.class);
if (info == null || !info.value().equals("active")) {
    throw new AssertionError("Missing or incorrect runtime annotation");
}
```

These are two illustrative snippets that can be placed together in an appropriate Java program. Checks that only test `info != null` fail to detect when the annotation exists but critical attributes are wrong. If the annotation defines a contract for a plugin, check the target method/class, required attributes, and how the framework maps them to behavior.

Commonly used APIs:

| API | Returns | Notes |
|---|---|---|
| `Class.getAnnotation(A.class)` | An annotation of type `A` or `null` | Considers inherited annotations on a class when `A` has `@Inherited` per API rules |
| `Class.getDeclaredAnnotation(A.class)` | Directly declared annotation or `null` | Does not retrieve annotations solely from inheritance |
| `isAnnotationPresent(A.class)` | Boolean | Reflects the API's presence semantics; does not return annotation values |
| `getAnnotations()` | Annotations present under inheritance rules | Does not automatically "unpack" every repeatable container |
| `getDeclaredAnnotations()` | Direct annotations | May include the repeatable container annotation |
| `Method.getAnnotation(A.class)` | Method annotation | Different from annotations attached to the **return type** |

`@Inherited` applies to annotation inheritance on **class declarations**; it does not automatically apply to methods, interfaces, or type-use annotations. Even with `@Inherited`, an overriding method does not automatically "inherit" method annotations under that rule; a framework wanting to search superclasses/interfaces must define its own algorithm.

## 3. Repeatable Annotations: "Seeing the Container" Is Not Reading Everything

A repeatable annotation must have a compatible container:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}

@Label("fast")
@Label("safe")
class Handler {}
```

The compiler represents repeated `@Label` annotations through the `@Labels` container (when multiple annotations of the same type appear at one site). Therefore:

- `Handler.class.getAnnotationsByType(Label.class)` retrieves both **two** `Label` instances, in observable declaration order.
- `Handler.class.getAnnotation(Label.class)` when only two `Label`s are indirectly present via a container typically returns `null`, because this API **does not automatically unwrap the container**.
- `Handler.class.getAnnotation(Labels.class)` shows the container is stored at runtime.
- `getDeclaredAnnotationsByType(Label.class)` is a good choice when you want to read **only** annotations directly associated with the class under inspection.

Important constraints on the container:

1. The container has a `value()` element returning an array of the repeatable annotation type (e.g., `Label[]`).
2. `@Retention` and `@Target` of the container must be compatible with the repeatable annotation per Java rules; you cannot arbitrarily choose a shorter retention for the container.
3. To retrieve repeatable annotations at runtime, both the repeatable type and the container must be designed/packaged properly so Reflection can see them.
4. If repeatable class annotations need to be inherited, test both the repeatable type and the container with respect to `@Inherited`. Do not use a test on a single class to infer subclass behavior.
5. Do not use `getAnnotation(Label.class)` as the sole check for repeatables; use `getAnnotationsByType(Label.class)` or `getDeclaredAnnotationsByType(Label.class)`.

**Note:** `getAnnotationsByType` supports both the single-annotation case and the indirect-container case. It is more appropriate whenever an annotation type is defined as repeatable. Do not hard-code the container name in application code if the by-type API already solves the requirement cleanly.

## 4. Type-Use Annotations: Reading via `AnnotatedType`

Consider:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeHint {
    String value();
}
```

With method:

```java
public @TypeHint("return") List<@TypeHint("element") String> names(
        @TypeHint("parameter-type") String input) {
    return List.of(input);
}
```

This is an **illustrative snippet**: the method must be placed in a class along with `import java.util.List;` and the `TypeHint` definition above.

There are at least three distinct metadata locations:

- `@TypeHint("return")` is attached to the **return type** `List<String>`.
- `@TypeHint("element")` is attached to the **generic type argument** `String` inside `List<...>`.
- `@TypeHint("parameter-type")` is attached to the **parameter's type** `String`.

To read them properly:

```java
Method m = SomeClass.class.getDeclaredMethod("names", String.class);

AnnotatedType result = m.getAnnotatedReturnType();
TypeHint onReturn = result.getAnnotation(TypeHint.class);

AnnotatedParameterizedType generic =
        (AnnotatedParameterizedType) result;
TypeHint onElement = generic.getAnnotatedActualTypeArguments()[0]
        .getAnnotation(TypeHint.class);

TypeHint onParameter = m.getAnnotatedParameterTypes()[0]
        .getAnnotation(TypeHint.class);
```

This snippet assumes `SomeClass` declares the matching method. Calling `getAnnotatedActualTypeArguments()` descends into the generic structure. If the runtime type is not `AnnotatedParameterizedType`, check with `instanceof` rather than casting blindly.

**Common confusions:**

- `m.getAnnotation(TypeHint.class)` looks for annotations attached to the **method declaration**, not annotations attached to the **return type**.
- `m.getParameterAnnotations()[0]` reads parameter declaration annotations. With `TypeHint` targeting only `TYPE_USE`, in the example above the parameter's declaration annotation list may be empty—this is correct behavior.
- `m.getReturnType()` only returns the `Class<?>` of the return type (e.g., `List.class`); it does not provide annotation sites for `List<@TypeHint String>`.
- `m.getGenericReturnType()` returns the generic type representation, but to retrieve **type-use annotations**, you need the corresponding `AnnotatedType` structure.

Additional APIs when building in-depth metadata readers:

| Location to inspect | Suitable API |
|---|---|
| Field's type | `Field.getAnnotatedType()` |
| Method's return type | `Method.getAnnotatedReturnType()` |
| Method's parameter types | `Method.getAnnotatedParameterTypes()` |
| Declared exception types | `Method.getAnnotatedExceptionTypes()` |
| Used superclass/interface types | `Class.getAnnotatedSuperclass()` / `getAnnotatedInterfaces()` |
| Generic type arguments | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` |
| Array component | `AnnotatedArrayType.getAnnotatedGenericComponentType()` |
| Wildcard or type variable bounds | `AnnotatedWildcardType` / `AnnotatedTypeVariable` with corresponding bound APIs |

With `String @TypeHint []` and `@TypeHint String[]`, annotations can be placed at **different type levels**. Do not flatten all type-use annotations into a single list and lose positional information. Tests must descend into the exact `AnnotatedType` branch.

## 5. Java 17+ Program Testing All Three Cases

The example below runs standalone and **does not use Java `assert`**, because `assert` is usually disabled when running without `-ea`. The `check` helper always throws `AssertionError` if Reflection returns the wrong result.

Save as **`AnnotationInspectionDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.List;

public class AnnotationInspectionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface RuntimeInfo { String value(); }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.TYPE)
    @interface BuildOnly {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Repeatable(Labels.class)
    @interface Label { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface Labels { Label[] value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface TypeHint { String value(); }

    @RuntimeInfo("present")
    @BuildOnly
    @Label("a")
    @Label("b")
    static class Example {
        public @TypeHint("return") List<@TypeHint("element") String> names(
                @TypeHint("parameter") String value) {
            return List.of(value);
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> type = Example.class;
        RuntimeInfo info = type.getAnnotation(RuntimeInfo.class);
        check(info != null && info.value().equals("present"), "runtime info");
        check(type.getAnnotation(BuildOnly.class) == null, "CLASS retention");
        Label[] labels = type.getAnnotationsByType(Label.class);
        check(labels.length == 2, "repeatable labels");
        check(type.getAnnotation(Label.class) == null, "indirectly present label");
        check(type.getAnnotation(Labels.class) != null, "container");
        Method method = type.getDeclaredMethod("names", String.class);
        AnnotatedType resultType = method.getAnnotatedReturnType();
        TypeHint resultHint = resultType.getAnnotation(TypeHint.class);
        AnnotatedType elementType =
                ((AnnotatedParameterizedType) resultType)
                        .getAnnotatedActualTypeArguments()[0];
        TypeHint elementHint = elementType.getAnnotation(TypeHint.class);
        TypeHint parameterHint = method.getAnnotatedParameterTypes()[0]
                .getAnnotation(TypeHint.class);
        check(resultHint != null && resultHint.value().equals("return"), "return type");
        check(elementHint != null && elementHint.value().equals("element"), "generic element");
        check(parameterHint != null && parameterHint.value().equals("parameter"), "parameter type");
        check(method.getParameterAnnotations()[0].length == 0,
                "TYPE_USE is not declaration PARAMETER");

        System.out.println("runtime class annotation = " + info.value());
        System.out.println("CLASS retention visible = "
                + (type.getAnnotation(BuildOnly.class) != null));
        System.out.println("repeatable values = "
                + labels[0].value() + ", " + labels[1].value());
        System.out.println("container present = "
                + (type.getAnnotation(Labels.class) != null));
        System.out.println("return type = " + resultHint.value());
        System.out.println("type argument = " + elementHint.value());
        System.out.println("parameter type = " + parameterHint.value());
        System.out.println("parameter declaration annotations = "
                + method.getParameterAnnotations()[0].length);
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 AnnotationInspectionDemo.java
java AnnotationInspectionDemo
```

**Actual stdout of the example:**

```text
runtime class annotation = present
CLASS retention visible = false
repeatable values = a, b
container present = true
return type = return
type argument = element
parameter type = parameter
parameter declaration annotations = 0
ALL CHECKS PASSED
```

The code was verified with `javac --release 17` on a newer JDK and ran successfully with the stdout order above.

### Interpreting the Results Case by Case

1. `RuntimeInfo` has `RetentionPolicy.RUNTIME`, so `getAnnotation(RuntimeInfo.class)` returns an instance with value `present`.
2. `BuildOnly` only has `RetentionPolicy.CLASS`, so `getAnnotation(BuildOnly.class)` returns `null` even though the annotation appears in source code.
3. The two `@Label`s attached to the class are grouped into container `@Labels`. Therefore `getAnnotationsByType(Label.class)` returns two instances, while `getAnnotation(Label.class)` returns `null` in this repeated case.
4. `getAnnotatedReturnType()` finds `return` on the return type; `AnnotatedParameterizedType` finds `element` on the generic type argument `String`.
5. `getAnnotatedParameterTypes()[0]` reads `parameter` on the parameter's **type**. `getParameterAnnotations()[0]` is empty because the annotation is declared only for `TYPE_USE`.
6. The `ALL CHECKS PASSED` line only appears after all required conditions pass. Changing retention/target, removing the container, or using the wrong API will cause the test to fail or the compiler to reject an invalid definition.

## 6. Turning Verification Checks into an Automated Test Suite

In a CI-enabled system, do not only inspect stdout. Convert `check(...)` conditions into JUnit 5 (JUnit Jupiter) assertions, running with the exact artifact and dependencies that the application actually uses.

Illustrative example of a test method in a test class:

```java
@Test
void repeatableAnnotationsAreVisible() {
    Label[] labels = Example.class.getAnnotationsByType(Label.class);
    assertEquals(2, labels.length);
    assertEquals("a", labels[0].value());
    assertEquals("b", labels[1].value());
}
```

The snippet above **is not a standalone program**: it assumes `import org.junit.jupiter.api.Test`, static import `org.junit.jupiter.api.Assertions.assertEquals`, and accessible definitions of `Example`/`Label`. With JUnit, the test fails if an annotation is missing or its value differs. Write similar tests for `getAnnotatedReturnType()`, `getAnnotatedParameterTypes()`, and verifying that `CLASS` annotations **are not** retrieved by Reflection.

### High-Value Checks

- **Retention:** `RUNTIME` is present; `CLASS` and `SOURCE` are absent in runtime APIs.
- **Target and site:** class/method/field/parameter declaration/type-use are read by their respective APIs.
- **Repeatable:** count, values, container, distinguishing `getAnnotation` and `getAnnotationsByType`.
- **Declared vs. inherited:** test on subclasses with `@Inherited`; do not extrapolate behavior to interfaces or methods.
- **Nested types:** `List<@A String>`, `Map<@A String, @B Integer>`, arrays, wildcards, bounds — inspect the right `AnnotatedType` branch.
- **Ordering and determinism:** if the system depends on repeated annotation order, write tests with distinct values rather than only counting them.
- **Packaged artifact:** repeat tests against the JAR/module/artifact after shading, shrinking, or obfuscation if applicable; build tools can alter or strip annotations and required elements.

### Negative Tests Are Critical

Do not only assert "found." Assert what **must not be considered valid**:

```java
if (Example.class.getAnnotation(BuildOnly.class) != null) {
    throw new AssertionError("CLASS annotation unexpectedly visible");
}
if (Example.class.getAnnotation(Label.class) != null) {
    throw new AssertionError("Expected repeatable container lookup semantics");
}
```

This is an illustrative check within the same scope as the previous example. It protects against false assumptions about retention and repeatable lookup. Do not rely on specific IDE behavior or seeing an annotation in a decompiler to conclude `Class.getAnnotation` will return a value.

## 7. Annotation Inheritance and Complex Type-Use Structures

### `@Inherited` Does Not Replace Dedicated Discovery Tests

For a class annotation marked `@Inherited`, `Sub.class.getAnnotationsByType(...)` can see annotations from the superclass according to the API's presence/inheritance rules, whereas `getDeclaredAnnotationsByType(...)` only retrieves annotations on `Sub` itself. If `Sub` declares annotations of the same repeatable type, results also follow shadowing and container association rules; do not assume all superclass and subclass annotations are concatenated into a single list.

Do not apply `@Inherited` to annotations on interfaces or methods and expect Reflection to merge metadata up the hierarchy automatically. For frameworks with custom annotation-merging mechanisms, test both **Core Reflection behavior** and **framework discovery behavior**, because they can differ.

### `AnnotatedType` Is a Tree, Not a List of Names

If a validator tool reads:

```java
List<@TypeHint("item") String>
```

the metadata sits on the **generic type argument**; reading only `List.class.getAnnotations()` will not see the annotation on `String`. For nested generics:

```java
Map<String, List<@TypeHint("leaf") Integer>>
```

you must traverse `AnnotatedParameterizedType` level by level, navigating to the second type argument of `Map` and then the first type argument of `List`. The snippets above are **illustrative types**, not complete Java declarations. If the structure involves a wildcard, array, or type variable, use the matching `AnnotatedType` subtype. Test suites should create dedicated fixtures for every shape the tool supports and assert annotations at each exact site.

## 8. Common Mistakes and How to Fix Them

| Symptom | Common cause | How to verify |
|---|---|---|
| `getAnnotation(A.class) == null` | Retention is not RUNTIME, wrong target/site, annotation stripped from artifact | Check `@Retention` definition; choose exact element and API |
| Two annotations present, yet `getAnnotation(A.class)` returns null | Repeatable stored indirectly in container | Call `getAnnotationsByType(A.class)` |
| `getParameterAnnotations()` empty while source has `@A String` | Annotation only targets `TYPE_USE` | Call `getAnnotatedParameterTypes()` |
| Cannot find annotation in `List<@A String>` | Reading type declaration or raw return type without descending into generics | Use `AnnotatedParameterizedType` |
| Test sees annotation on superclass but not subclass | Using declared API or wrong assumption about `@Inherited` | Separate present/declared/inherited tests |
| Annotation exists in source but missing in runtime build | Shrinker/obfuscator removed metadata or annotation definition | Test on release artifact; configure proper keep rules |
| `ClassCastException` casting `AnnotatedType` | Actual type is not a parameterized type | Check `instanceof` before traversing by shape |
| Annotation value differs from expected | Wrong default/member values or wrong type/site | Assert values too, not only `isAnnotationPresent` |
| Results change when using a framework | Framework uses a different merge/search algorithm than Core Reflection | Write independent tests for both Reflection and the framework |

Distinguish *annotation absent* from *unable to load class/method* due to class-loading or access/module issues. `getDeclaredMethods()` can throw linkage errors if a required dependency is missing; that is not proof an annotation is absent.

## 9. Quality Checklist for Annotation-Reading Tools

Before releasing an annotation scanner/validator, verify:

1. Annotation types have `RUNTIME` retention when runtime discovery is required.
2. `@Target` permits the right elements and type-use sites.
3. Repeatable annotations have valid containers, and the scanner uses the by-type API.
4. The scanner distinguishes direct, declared, and inherited metadata.
5. The scanner traverses `AnnotatedType` structures properly for generics, arrays, bounds, and wildcards.
6. Do not infer method declaration annotations from return type annotations or vice versa.
7. Test presence, absence, wrong values, wrong structures, and missing class/container metadata.
8. CI runs on the JDK and artifact matching the deployment environment; if a transformer/shrinker is used, test the transformed artifact as well.
9. Do not treat the order of `getDeclaredMethods()` or `getDeclaredAnnotations()` as an API contract when that order is not guaranteed.
10. Error reports include class, method, type site, and annotation name, so developers know exactly which fixture is invalid.

## 10. Self-Check Questions

**Question 1.** An annotation declared `@Retention(CLASS)` can appear in the class file. Why can `getAnnotation` not retrieve it?

Because `CLASS` retention does not require annotations to be retained for Core Reflection at runtime; to make runtime APIs see it, use `RUNTIME`.

**Question 2.** Two `@Label` annotations on the same class can cause `getAnnotation(Label.class)` to return `null`. Does that mean they are lost?

No. They may be represented indirectly via a container. Use `getAnnotationsByType(Label.class)` to retrieve all of them.

**Question 3.** Are `getParameterAnnotations()` and `getAnnotatedParameterTypes()` the same?

No. The first API reads annotations on parameter declarations; the second reads annotations on **parameter types**.

**Question 4.** To read `@A` in `List<@A String>`, can you call `List.class.getAnnotation(A.class)`?

No. `@A` is on the **type argument `String`** at the type-use site, not on the `java.util.List` declaration. You must traverse `AnnotatedParameterizedType`.

**Question 5.** Why is it necessary to test repeatable and type-use annotations on the packaged artifact?

Because shrinkers/obfuscators, classpath, modules, or bytecode transformations can affect members and runtime metadata; source/debug tests do not always reflect the release environment.

## References

- Java SE 17 API: [`Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html), [`Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html), [`Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html).
- Java SE 17 API: [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html), [`AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html), [`AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
- Java Language Specification §9.6–§9.7: annotation types, repeatable annotations, applicability; §9.6.4.2–§9.6.4.3: retention and target; §9.6.4.3 and rules related to repeatable/container per JLS edition.

**Takeaway:** To test annotations with Reflection, always ask **"Does the annotation have RUNTIME retention, what kind of location is it placed on, and is it repeatable or type-use?"**. The answer determines the right API: `getAnnotation` for ordinary direct metadata, `getAnnotationsByType` for repeatables, and the `AnnotatedType` tree for annotations on type-use sites.