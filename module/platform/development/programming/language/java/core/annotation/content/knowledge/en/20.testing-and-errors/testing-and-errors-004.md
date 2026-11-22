# Testing Repeatable Annotations, Container Types, and Result Order in Java

In Java, a **repeatable annotation** is an annotation type that can appear multiple times at the same location, for example:

```java
@Tag("first")
@Tag("second")
class Pair {}
```

This syntax works when `Tag` is marked with `@Repeatable(Tags.class)` and has a **containing annotation type** `Tags` with the required element `Tag[] value()`. At compilation, the two `@Tag` occurrences are represented **via a `@Tags` container**. Therefore, standard Reflection APIs and APIs that specifically support repeatable annotations can return **different results even when querying the same class**.

This lesson focuses on **testing and error detection**, not just syntax declaration. We will verify precisely:

- Whether a single annotation is read directly.
- Whether two repeated annotations are contained in `Tags` and returned in the right **order**.
- What results an explicit container and an empty container produce.
- The difference between `getAnnotation`, `getDeclaredAnnotation`, `getDeclaredAnnotations`, `getAnnotationsByType`, and `getDeclaredAnnotationsByType`.
- How `@Inherited` affects results on subclasses, and what the limitations are when testing methods/parameters.
- Which container definition or retention errors must be rejected by the compiler or cause tests to read an empty array.
- How to combine **runnable tests, checks with clear error messages, and `javap -v`** to verify bytecode traces.

The full example runs on **JDK 17+**, requiring only the JDK without external testing libraries. The checks proactively throw `AssertionError` if a condition is false, so they do not depend on whether `-ea` is enabled on the JVM.

## 1. Concepts to Distinguish When Writing Tests

### Repeated Annotations and Container Annotations

Example of a valid definition:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}
```

- `Tag` is the **repeated annotation type**. `Tag.value()` returns a `String`.
- `Tags` is the **container annotation type**. `Tags.value()` returns **`Tag[]`**, not `String[]`.
- `@Repeatable(Tags.class)` on `Tag` tells the compiler to use `Tags` when multiple `@Tag` annotations appear at the same location.
- `@Retention(RUNTIME)` is placed on **both types** so that the program can read metadata using standard Java Reflection.
- `@Target(TYPE)` restricts the applicable locations for the class-level example. If you want to test methods and parameters, you must expand the target accordingly.

**A single `@Tag` does not mean `@Tags` is always present.** When only one `@Tag` appears at a location, it can be represented directly, without the compiler generating a container usage.

### Four Basic Test States

| Scenario | Syntax | What to Test |
| --- | --- | --- |
| Single annotation | `@Tag("solo")` | `Tag` is visible directly; do not infer a container |
| Multiple repeated annotations | `@Tag("first") @Tag("second")` | Container represents `Tag[2]`; by-type APIs return the exact order |
| Explicit container | `@Tags({@Tag("a"), @Tag("b")})` | By-type APIs unwrap the container just like the repeated case |
| Empty container | `@Tags({})` | Container exists, but the set of `Tag`s has length 0 |

Each state tests a different contract. **Only testing the multiple-annotation case while skipping single/empty is insufficient** for general metadata-reading code.

## 2. Choosing the Right Reflection API for Testing

The following methods belong to the `AnnotatedElement` group and have their own rules:

| API | Test Question | Notes When `@Tag` Is Repeated |
| --- | --- | --- |
| `getDeclaredAnnotation(Tag.class)` | Is a `Tag` directly declared on this element? | **Does not automatically unwrap the container** |
| `getAnnotation(Tag.class)` | Is a `Tag` "present" according to the API rules? | Not an operation to get the first `Tag` of a repeated list |
| `getDeclaredAnnotation(Tags.class)` | Is the `Tags` container directly declared? | Read `Tags.value()` to inspect the inner array |
| `getDeclaredAnnotations()` | Which runtime-visible annotations are considered directly declared? | Two `@Tag` annotations may appear as a single `Tags` |
| `getDeclaredAnnotationsByType(Tag.class)` | Which `Tag` annotations are **directly/indirectly present** on this element itself? | **Unwraps the container**, preserves `Tag` order |
| `getAnnotationsByType(Tag.class)` | Which `Tag` annotations are **associated** with this element? | Unwraps the container; for classes with `@Inherited`, may search superclasses |

For example, if a class has two `@Tag` annotations compiled into `Tags`, calling:

```java
Pair.class.getDeclaredAnnotation(Tag.class)
```

returns `null` in the standard example, whereas:

```java
Pair.class.getDeclaredAnnotationsByType(Tag.class)
```

returns an array of two `Tag` instances. These two results **do not conflict**: one API looks for a direct annotation, while the other searches by type and **unwraps the container**.

**API selection rule:** if the goal is to retrieve all annotations of the same type—including single, repeated, or explicit container cases—prefer `getDeclaredAnnotationsByType(T.class)` (without inheritance) or `getAnnotationsByType(T.class)` (which takes associated rules and applicable inheritance into account).

Do not write tests assuming `getAnnotation(Tag.class)` is equivalent to `getAnnotationsByType(Tag.class)[0]`. The two calls have different contracts, and the first query can return `null`.

## 3. Where Is Order Guaranteed?

Given two annotations of the same type written as:

```java
@Tag("first")
@Tag("second")
class Pair {}
```

the compiler represents them with a `Tags` containing a `Tag[]` array in **the order in which the repeated annotations appear**. Accordingly, `getDeclaredAnnotationsByType(Tag.class)` returns the `Tag` elements in the order **`first` before `second`** in the example.

You can check using concrete values:

```java
Tag[] values = Pair.class.getDeclaredAnnotationsByType(Tag.class);
String[] names = {
    values[0].value(),
    values[1].value()
};
```

This snippet belongs inside a method; before indexing, you must ensure the array has length 2. In the full test suite, we compare **the entire array** rather than only looking at the first value.

### Limitations of Order Guarantees

Two kinds of ordering must be distinguished:

1. **The order of repeated annotations of the same type**, such as `@Tag("first") @Tag("second")`, which is represented as an array inside the container and returned in order by by-type APIs.
2. **The order among annotations of different types** when iterating over the result of `getDeclaredAnnotations()` or a metadata `Map` collection. Do not design tests that depend on an arbitrary order between unrelated annotation types, unless a specific API guarantees it.

For example:

```java
@Tag("first")
@Tag("second")
@OtherAnnotation
class Pair {}
```

If `OtherAnnotation` is validly declared, fetching all declared annotations and asserting that `Tags` necessarily appears at index 0 in every situation is a brittle test. **Filter by type** or use a by-type API, and only check the order **within the `Tag` list**.

Also, do not treat array order as a default business priority system. If annotations express rules that may conflict, explicitly define whether the first rule wins or the last rule wins and test that policy separately.

## 4. Complete Java 17+ Test Suite Without JUnit

Create a file named **`RepeatableAnnotationTests.java`** with the following content:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.Arrays;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.PARAMETER})
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.PARAMETER})
@interface Tags {
    Tag[] value();
}

@Tag("first")
@Tag("second")
class Pair {
}

@Tag("single")
class Single {
}

@Tags({@Tag("manual-1"), @Tag("manual-2")})
class Explicit {
}

@Tags({})
class Empty {
}

class Child extends Pair {
}

@Tag("child")
class ChildOverride extends Pair {
}

class Handler {
    @Tag("check")
    @Tag("audit")
    public void run(
            @Tag("required") @Tag("logged") String value) {
    }
}

public class RepeatableAnnotationTests {
    static int passed = 0;

    static void eq(String label, Object expected, Object actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
        passed++;
    }

    static String values(Tag[] annotations) {
        return Arrays.toString(
                Arrays.stream(annotations)
                        .map(Tag::value)
                        .toArray(String[]::new));
    }

    static String nullToText(Object object) {
        return object == null ? "null" : object.toString();
    }

    public static void main(String[] args) throws Exception {
        eq("pair by type", "[first, second]",
                values(Pair.class.getDeclaredAnnotationsByType(Tag.class)));

        eq("pair declared container", Tags.class,
                Pair.class.getDeclaredAnnotations()[0].annotationType());

        eq("pair container order", "[first, second]",
                values(Pair.class.getDeclaredAnnotation(Tags.class).value()));

        eq("pair direct Tag absent", "null",
                nullToText(Pair.class.getDeclaredAnnotation(Tag.class)));

        eq("single Tag", "[single]",
                values(Single.class.getDeclaredAnnotationsByType(Tag.class)));

        eq("single direct type", Tag.class,
                Single.class.getDeclaredAnnotations()[0].annotationType());

        eq("single container absent", "null",
                nullToText(Single.class.getDeclaredAnnotation(Tags.class)));

        eq("explicit container", "[manual-1, manual-2]",
                values(Explicit.class.getDeclaredAnnotationsByType(Tag.class)));

        eq("empty container", "[]",
                values(Empty.class.getDeclaredAnnotationsByType(Tag.class)));

        eq("empty direct container", 0,
                Empty.class.getDeclaredAnnotation(Tags.class).value().length);

        eq("child declared no tags", 0,
                Child.class.getDeclaredAnnotationsByType(Tag.class).length);

        eq("child inherited order", "[first, second]",
                values(Child.class.getAnnotationsByType(Tag.class)));

        eq("child local overrides", "[child]",
                values(ChildOverride.class.getAnnotationsByType(Tag.class)));

        Method run = Handler.class.getDeclaredMethod("run", String.class);

        eq("method pair", "[check, audit]",
                values(run.getDeclaredAnnotationsByType(Tag.class)));

        Parameter param = run.getParameters()[0];

        eq("parameter pair", "[required, logged]",
                values(param.getAnnotationsByType(Tag.class)));

        eq("parameter container", 2,
                param.getAnnotation(Tags.class).value().length);

        System.out.println("PASS " + passed + " checks");
        System.out.println("Pair: "
                + values(Pair.class.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("Single: "
                + values(Single.class.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("Explicit: "
                + values(Explicit.class.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("Child: "
                + values(Child.class.getAnnotationsByType(Tag.class)));
        System.out.println("Override: "
                + values(ChildOverride.class.getAnnotationsByType(Tag.class)));
        System.out.println("Method: "
                + values(run.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("Parameter: "
                + values(param.getAnnotationsByType(Tag.class)));
    }
}
```

**Note on `@Inherited`:** the example applies `@Inherited` to both `Tag` and `Tags` so we can test that `Child` inherits `Pair`'s `Tag` annotations according to **class**-level lookup rules. This meta-annotation does **not** make annotations on methods or parameters automatically inherited. `@Target` includes `TYPE`, `METHOD`, and `PARAMETER` to test all three locations in the same example.

The types `Tag`, `Tags`, `Pair`, `Single`, etc. are in the default package and there is only one `public class` so the file runs standalone. In real applications, place them in an explicit package; the testing principles do not change.

### 4.1. Running the Tests

In the directory containing the file:

```bash
javac --release 17 RepeatableAnnotationTests.java
java RepeatableAnnotationTests
```

Exact stdout:

```text
PASS 16 checks
Pair: [first, second]
Single: [single]
Explicit: [manual-1, manual-2]
Child: [first, second]
Override: [child]
Method: [check, audit]
Parameter: [required, logged]
```

**Verified:** the Java file compiled successfully with `javac --release 17` and ran on the JDK; all 16 checks passed and the stdout matched the output above.

### 4.2. Why Use an eq() Method That Throws AssertionError Directly?

The `eq(label, expected, actual)` method checks that the result **exactly equals the expected data**. When there is a discrepancy, the test stops with:

```text
java.lang.AssertionError: <label>: expected=<...>, actual=<...>
```

This is an **error message format template**, not an error that occurs during a successful run. The actual message will include the specific label and values.

Java has `assert` syntax, but tests written using `assert` must be run with `java -ea` to enable assertions. The test suite here calls `throw new AssertionError(...)` directly, so it does not depend on the `-ea` flag. That makes the command `java RepeatableAnnotationTests` sufficient for verification.

The `values(...)` method converts the annotation array into a string in **the exact order** returned by Reflection. If `first` and `second` are swapped, the comparison check against `[first, second]` will fail instead of merely seeing a count of 2 and assuming the test was sufficient.

## 5. Explanation of the 16 Checks

### 5.1. Pair — The Compiler Uses One Container for Two Tag Annotations

```java
@Tag("first")
@Tag("second")
class Pair {}
```

The checks:

- `getDeclaredAnnotationsByType(Tag.class)` must return the order `[first, second]`.
- `Pair.class.getDeclaredAnnotations()[0].annotationType()` is `Tags.class` **in the Pair example where only one container annotation type is declared on the class**, so index 0 is valid. Do not generalize this index to classes with other annotation types.
- `getDeclaredAnnotation(Tags.class).value()` contains an array of two `Tag` annotations in the same order.
- `getDeclaredAnnotation(Tag.class)` returns `null` because the repeated `Tag` annotations are represented indirectly inside the container.

The three APIs provide three different views: **direct declaration form**, **physical container**, and **Tag list by type**. Good tests should verify more than just array length.

### 5.2. Single — Only One Tag, Tags Is Not Required

```java
@Tag("single")
class Single {}
```

In the example:

- `getDeclaredAnnotationsByType(Tag.class)` returns `[single]`.
- `getDeclaredAnnotations()[0].annotationType()` is `Tag.class`.
- `getDeclaredAnnotation(Tags.class)` returns `null`.

If production code only looks for the container without handling a single `Tag`, it will **miss a valid case**.

### 5.3. Explicit — Explicitly Written Container

```java
@Tags({@Tag("manual-1"), @Tag("manual-2")})
class Explicit {}
```

`getDeclaredAnnotationsByType(Tag.class)` returns `[manual-1, manual-2]`. That means users can write the container directly in source code and the by-type API result still unpacks both `Tag` annotations accurately.

In terms of data, an explicit container and a compiler-generated container for multiple repeated annotations can carry the same metadata structure; **it is not necessarily possible to recover the exact source syntax from the class file**.

### 5.4. Empty — Container with an Empty Array

```java
@Tags({})
class Empty {}
```

A `Tags` annotation is directly present, yet `getDeclaredAnnotationsByType(Tag.class)` returns `[]` and `getDeclaredAnnotation(Tags.class).value().length` equals 0. This is why tests need to check **the contents and element count**, not just whether `Tags` is present.

### 5.5. Child — Inherited from the Parent Class

```java
class Child extends Pair {}
```

`Child` does not declare `Tag` on the current class. Because `Tag` and `Tags` have `@Inherited`, `Child.class.getAnnotationsByType(Tag.class)` receives `[first, second]` from the superclass, whereas `Child.class.getDeclaredAnnotationsByType(Tag.class)` returns an empty array.

Testing both APIs prevents confusing annotations that are **associated through inheritance** with annotations that are **declared on the subclass**.

### 5.6. ChildOverride — Tag on the Subclass Replaces, Rather Than Appends

```java
@Tag("child")
class ChildOverride extends Pair {}
```

`getAnnotationsByType(Tag.class)` returns **`[child]`**, not `[first, second, child]`.

A system that wants to combine annotations across multiple class hierarchy levels must **write its own merge policy**, such as traversing `getSuperclass()` manually and calling `getDeclaredAnnotationsByType` at each level. `@Inherited` does not automatically accumulate the parent and child lists when the child already has an annotation of the same type.

### 5.7. Method and Parameter — Order at the Exact Declaration Location

```java
class Handler {
    @Tag("check") @Tag("audit")
    public void run(@Tag("required") @Tag("logged") String value) {}
}
```

The test retrieves the exact method by name and parameter type list:

```java
Method run = Handler.class.getDeclaredMethod("run", String.class);
```

Then:

- `run.getDeclaredAnnotationsByType(Tag.class)` returns `[check, audit]`.
- `run.getParameters()[0].getAnnotationsByType(Tag.class)` returns `[required, logged]`.
- `parameter.getAnnotation(Tags.class).value().length` equals 2.

Annotations on a **method declaration** and annotations on a **parameter declaration** are at two different locations. A test that accidentally reads the method instead of the parameter might get the right `Tag` type but the wrong values.

`@Inherited` does not cause these annotations to propagate from a parent method to an overriding method. Testing class inheritance and testing method declarations are two independent cases.

## 6. Bytecode Verification with javap -v

Reflection tests only answer "what does the runtime API see?". To check **how the compiler encoded the repeated annotations**, use the JDK `javap` tool:

```bash
javap -v -p Pair
javap -v -p Single
javap -v -p Explicit
javap -v -p Empty
```

If you compiled into a different directory using `javac -d out`, add `-classpath out`:

```bash
javap -v -p -classpath out Pair
```

In the metadata section of **Pair.class**, look for the attribute:

```text
RuntimeVisibleAnnotations:
    ... Tags(
        value = [ ... Tag(value="first"), ... Tag(value="second") ]
    )
```

This is an **abbreviated content layout**, not a verbatim copy from `javap`. Constant-pool indices and descriptor formatting vary by JDK. Three things to verify:

1. `Pair.class` has declaration metadata in `RuntimeVisibleAnnotations` because the retention is `RUNTIME`.
2. The direct-level annotation is **`Tags`**, meaning the **container**.
3. The `value` element inside the container holds **two `Tag` annotations in the order first, second**.

For `Single.class`, the metadata on the class is a direct `Tag`, **without automatically generating a container just because Tag is repeatable**. For `Explicit.class` and `Empty.class`, the explicit `Tags` container appears; the arrays have two and zero elements, respectively.

**Verified with JDK tools:** running `javap -v` on `Pair.class` confirmed the presence of the `Tags` container inside `RuntimeVisibleAnnotations`. No external bytecode-reading library outside the JDK is required to verify this step.

### How Does CLASS Retention Differ?

If the annotation pair has `@Retention(CLASS)`, the compiler still retains metadata in `.class` under an attribute such as `RuntimeInvisibleAnnotations`, but standard Java Reflection **does not return** those annotations. Therefore:

```java
type.getDeclaredAnnotationsByType(Tag.class)
```

can return an empty array even though the bytecode contains the annotations if `Tag` does not have `RUNTIME` retention. In that case, do not conclude that the compiler lost data; use `javap -v` to inspect the class file, or change retention to `RUNTIME` if your true goal is reading via Reflection.

**Do not mix bytecode tests with Reflection tests:** `javap` reads the `.class` file, whereas `getDeclaredAnnotationsByType` reads metadata through the runtime API. The two access paths serve distinct purposes.

## 7. Testing Order: Checking Size, Content, and Position

A good test has three layers of checks:

**Layer 1 — size:**

```java
Tag[] tags = Pair.class.getDeclaredAnnotationsByType(Tag.class);
if (tags.length != 2) {
    throw new AssertionError("Expected two tags");
}
```

**Layer 2 — content:**

```java
if (!"first".equals(tags[0].value())) {
    throw new AssertionError("Wrong first tag");
}
```

**Layer 3 — full sequence order:**

```java
String actual = values(tags);
eq("pair ordered values", "[first, second]", actual);
```

The snippets above belong inside the `RepeatableAnnotationTests` class once the `values` and `eq` helpers are present, rather than being standalone compilable files.

Checking only `tags.length == 2` can miss the `[second, first]` case. Checking only the first value also misses a mismatch in the second element. For ordered metadata, compare **the entire retrieved sequence** against the expected string or array.

In production tests, you can use `List<String>` or `String[]` with `Arrays.equals(...)` for explicit comparison instead of a string produced by `Arrays.toString(...)`. This lesson's example uses strings because they are easy to display and compare against stdout.

## 8. Edge Cases to Test to Avoid Gaps

| Case | Required Test | Why |
| --- | --- | --- |
| No annotation applied | By-type returns an empty array | Consumers must handle the absence of metadata |
| Applied once | By-type returns one element; container may be absent | Must not handle only the container case |
| Applied twice | By-type returns two, in exact order | Verifies compiler and Reflection coordination |
| Applied more than twice | By-type returns all in exact order | Do not hardcode a limit of 2 |
| Explicit container | Returns elements from `value()` | Source code may write the container directly |
| Empty container | Container exists, but by-type is empty | Do not confuse container presence with Tag presence |
| Annotation on method/parameter | Exact element/parameter is queried | Metadata scope differs from class |
| Missing retention RUNTIME | Reflection cannot read it | Distinguish retention errors from repeatable errors |
| Subclass does not declare Tag | Associated API can search superclass | Verifies `@Inherited` |
| Subclass has its own Tag | Child list does not automatically append to parent list | Avoids misunderstanding merge behavior |

Be careful about ordering when annotations span **classes in an inheritance hierarchy**. `getAnnotationsByType` is not an API that concatenates all annotations from every superclass into a single sequence; it follows the associated annotations rules. The order of elements returned within a `Tag` set from a single declaration or container is still preserved.

### Testing More Than Two Elements

You can add a class:

```java
@Tag("first")
@Tag("middle")
@Tag("last")
class Triple {
}
```

And then check:

```java
eq("triple order", "[first, middle, last]",
        values(Triple.class.getDeclaredAnnotationsByType(Tag.class)));
```

This is an **illustrative** extension to the main file; you need to add `Triple` to the same file before running it. It verifies that the logic does not assume the element count is 2.

## 9. Compilation Errors from Invalid Repeatable/Container Declarations

The examples below are **intentionally invalid**; do not combine them with the runnable program in Section 4.

### 9.1. Repeating an Annotation Type Without @Repeatable

```java
@interface Flag {
    String value();
}

@Flag("one")
@Flag("two")
class Wrong {
}
```

The compiler rejects this because `Flag` is not a repeatable annotation type. Simply placing two lines of the same annotation in source code **does not make it repeatable**.

**Fix:** define a valid container:

```java
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@interface Flags {
    Flag[] value();
}
```

The fix requires importing `java.lang.annotation.Repeatable`. If you intend to read it via Reflection, you must also add appropriate retention on both.

### 9.2. Container Returns the Wrong Type

```java
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@interface Flags {
    String[] value(); // Wrong: must return Flag[].
}
```

The container signature always requires `Flag[] value()`, not an array of the data type inside `Flag.value()`. `String[]` cannot substitute for the `Flag[]` annotation array.

### 9.3. Container Missing an Element Named value

```java
@Repeatable(Flags.class)
@interface Flag {}

@interface Flags {
    Flag[] items(); // Wrong element name.
}
```

The compiler requires **`Flag[] value()`**, not `items()`, `getItems()`, or `annotations()`.

### 9.4. Container Has an Additional Element Without a Default

```java
@Repeatable(Flags.class)
@interface Flag {}

@interface Flags {
    Flag[] value();
    String owner(); // No default.
}
```

When the compiler packs multiple `@Flag` annotations into the container, it has no value for `owner`. If an extra element is needed, declare an appropriate `default`:

```java
String owner() default "system";
```

The fix line is an **element declaration** placed inside `@interface Flags`, not a standalone Java statement.

### 9.5. Container Retention Is Shorter Than the Primary Annotation

```java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Flags.class)
@interface Flag {}

@Retention(RetentionPolicy.CLASS)
@interface Flags {
    Flag[] value();
}
```

Invalid configuration: the repeated annotation has `RUNTIME` retention, while the container only has `CLASS`. The compiler requires the container retention to be compatible and no shorter than that of the repeated annotation. A pair meant to be readable via Reflection should use `RUNTIME` on both.

### 9.6. Incompatible @Target

If `Flag` is placed on a parameter, while `Flags` is only allowed on `TYPE`, the compiler cannot validly contain repeated `@Flag` occurrences on a parameter. You must declare a container target compatible with the allowed locations of the repeated annotation.

In the complete test file, both `Tag` and `Tags` have `@Target({TYPE, METHOD, PARAMETER})`, so all three test groups—class, method, and parameter—share one valid pair of types.

### 9.7. @Inherited Present on the Repeated Type but Missing on the Container

```java
@Inherited
@Repeatable(Flags.class)
@interface Flag {}

@interface Flags {
    Flag[] value();
}
```

If the repeated annotation `Flag` has `@Inherited`, the container must also have `@Inherited` according to compiler rules. Aside from fixing the declaration pair, remember that `@Inherited` does **not** apply to propagating method/parameter annotations on overrides.

## 10. Runtime Errors Easily Mistaken for Compiler Errors

### 10.1. getAnnotation(Tag.class) Returns null While By-Type Returns Values

Scenario:

```java
@Tag("first")
@Tag("second")
class Pair {}
```

Because a container is present, `Pair.class.getDeclaredAnnotation(Tag.class)` returns `null`. This is valid behavior; the compiler did not drop `Tag`. Use `getDeclaredAnnotationsByType(Tag.class)` or read `Tags.value()` directly.

### 10.2. An Empty Container Carries No Tag Elements

`@Tags({})` can certainly exist. `getDeclaredAnnotation(Tags.class)` is non-`null`, but `getDeclaredAnnotationsByType(Tag.class).length == 0`. Consumer tests must inspect **the actual list**, not merely the presence of the container.

### 10.3. A Single Direct Tag May Have No Container

`@Tag("single")` can cause `getDeclaredAnnotation(Tags.class)` to return `null`. If the consumer only reads `Tags`, it will not see the direct `Tag`. Use the by-type API for uniform handling.

### 10.4. SOURCE/CLASS Retention Prevents Reflection from Seeing Annotations

If `@Retention` is omitted, the default is `CLASS`; standard Reflection APIs only see annotations with `RUNTIME` retention. Adding `@Repeatable` **does not automatically enable runtime retention**.

Check both annotation types: `Tag` and `Tags`. Changing the Reflection method without changing retention will not make a `CLASS`-retained annotation visible.

### 10.5. Confusing Declared and Associated APIs

`Child.class.getDeclaredAnnotationsByType(Tag.class)` is empty because `Child` itself does not declare `Tag`. However, `Child.class.getAnnotationsByType(Tag.class)` can retrieve it from `Pair` via `@Inherited`.

If you only want direct metadata to decide overrides, use the declared API. If you want metadata according to inheritance rules, use the associated API.

### 10.6. Assuming @Inherited Combines Parent and Child Lists

`ChildOverride` has `@Tag("child")` directly. `getAnnotationsByType(Tag.class)` returns `[child]` rather than adding `first` and `second` from the parent. If merging is needed, that is business logic you must write and test separately.

### 10.7. Ordering Between Different Annotation Types

Do not write tests requiring all annotations returned by `getDeclaredAnnotations()` to follow source order across **different types**. Instead, check the correct type and then compare the array order of repeated annotations of **the same type**.

### 10.8. Selecting the Wrong Method or Parameter

Overloaded methods use different signatures: `getDeclaredMethod("run", String.class)` differs from `getDeclaredMethod("run", int.class)`. Reading method metadata differs from reading parameter metadata. If a test finds `Tag` present but with the wrong content, verify that the Reflection element being queried is **the right declaration**.

## 11. When Using JUnit Instead of Custom Tests

In a project with JUnit 5, you can use `assertArrayEquals` to compare the entire result instead of a string. Example **snippet requiring a project already configured with JUnit Jupiter**:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import org.junit.jupiter.api.Test;

class RepeatableJUnitTest {
    @Test
    void tagsKeepSourceOrder() {
        Tag[] tags = Pair.class.getDeclaredAnnotationsByType(Tag.class);
        String[] actual = java.util.Arrays.stream(tags)
                .map(Tag::value)
                .toArray(String[]::new);

        assertArrayEquals(
                new String[] {"first", "second"},
                actual);
    }
}
```

This snippet **is not standalone with only the JDK** because it requires JUnit Jupiter and its build/test runner; it reuses `Tag` and `Pair` from this lesson. The main test suite in Section 4 does not need JUnit, so it runs immediately with `javac/java`.

If using JUnit, you should also have clearly named tests such as `singleTagDoesNotRequireContainer`, `explicitContainerIsExpanded`, `emptyContainerReturnsNoTag`, and `inheritedTagDoesNotMergeWithLocalTag`. Testing one idea per test helps identify errors faster.

## 12. Testing with javap and Java Reflection Complement Each Other

The two testing layers answer different questions:

| Tool | What Does It Check? | Example |
| --- | --- | --- |
| `javac` | Are the source code and container definition valid? | Compiler reports an error if `Tags.value()` has the wrong type |
| `javap -v` | How are annotations encoded in the class file? | `Pair.class` has `Tags` containing a `Tag[]` array |
| Java Reflection | What metadata does the runtime API return? | `getDeclaredAnnotationsByType(Tag.class)` returns `[first, second]` |
| Assertion suite / JUnit | Does the result match the contract expected by the application? | Order, count, empty/override cases |
| Business consumer tests | Is the metadata interpreted correctly in your logic? | Which rule runs first; how duplicate data is handled |

A real-world project does not necessarily use all five test layers for every annotation. However, when debugging **container/order/retention** issues, combining `javac`, `javap`, and Reflection helps isolate the cause quickly:

- `javac` fails: the annotation definition or usage is invalid.
- `javac` succeeds and `javap` shows the container, but Reflection returns empty: suspect retention or querying the wrong API.
- Reflection returns all elements, but the consumer processes them in the wrong order: bug in the consumer or business rules.
- Container only, missing single: missing direct branch in bytecode/metadata-reading code.

**An important caveat:** if the build has a post-`javac` bytecode optimization or transformation step, inspect **the final class file actually being loaded**, not just intermediate class files. Bytecode tools can alter metadata depending on their configuration.

## 13. Self-Check Exercises

### Exercise 1 — Result of Each API

Given `Pair` from this lesson, predict:

```java
Pair.class.getDeclaredAnnotation(Tag.class)
Pair.class.getDeclaredAnnotation(Tags.class).value().length
Pair.class.getDeclaredAnnotationsByType(Tag.class).length
```

**Answer:** `null`, `2`, `2`, respectively. The repeated `Tag` annotations live inside the container, and the by-type API unwraps the container.

### Exercise 2 — Checking Order

Suppose a consumer accidentally reverses the order to `[second, first]` while keeping the element count at 2. Which tests will catch this?

**Answer:** a test that compares **the entire ordered sequence** or checks each index will catch it; a test that only checks `length == 2` will not catch it.

### Exercise 3 — The Single Case

Why can `Single.class.getDeclaredAnnotation(Tags.class)` return `null` even though `Single.class.getDeclaredAnnotationsByType(Tag.class)` has one element?

**Answer:** a single `@Tag` can be represented directly without needing `Tags`.

### Exercise 4 — Empty Explicit Container

Given `@Tags({}) class Empty {}`, is it true that `Empty.class.getDeclaredAnnotation(Tags.class) != null` while `Empty.class.getDeclaredAnnotationsByType(Tag.class).length == 0`?

**Answer:** yes. The container is present, but it contains no `Tag` annotations.

### Exercise 5 — @Inherited

If `Child extends Pair` does not declare `Tag`, while `ChildOverride extends Pair` has `@Tag("child")`, what does `getAnnotationsByType(Tag.class)` return on each class?

**Answer:** `Child` returns `[first, second]`, and `ChildOverride` returns `[child]`. There is no automatic concatenation.

### Exercise 6 — Method and Parameter

For `Handler.run` in this lesson, to read `[required, logged]`, do you use `Method` or `Parameter` as the final object on which to call `getAnnotationsByType(Tag.class)`?

**Answer:** retrieve the `Parameter` at index 0 from `run.getParameters()` and call the API on that parameter. Calling it on `Method` reads `[check, audit]`.

### Exercise 7 — Wrong Container Type

If `Tags` declares `String[] value()` instead of `Tag[] value()`, does the error occur at compile time or when calling Reflection?

**Answer:** at compile time when defining the invalid `@Repeatable` relationship, before the program runs.

### Exercise 8 — Retention Error

If you keep the same code but remove `@Retention(RUNTIME)` from both `Tag` and `Tags`, will Reflection still return `[first, second]`?

**Answer:** no. The default retention is `CLASS`, so standard Java Reflection does not see that metadata. Tools like `javap` can still read the `RuntimeInvisibleAnnotations` trace in the class file.

## 14. Checklist Before Completing Testing

1. **Standard definition:** does the repeated annotation have `@Repeatable(Container.class)` and does the container have the exact `Repeated[] value()`?
2. **Consistent metadata:** are retention, target, `@Inherited`, and any additional container elements valid?
3. **Runtime visibility:** if tests use Reflection, are both types retained until runtime?
4. **Single test:** is a single direct annotation tested without requiring a container?
5. **Repeated test:** are at least two annotations tested with specific **content and order**?
6. **Explicit container test:** can the consumer read a container written directly by the user?
7. **Empty container test:** does it avoid confusing the container's existence with inner elements?
8. **Right API test:** are `getAnnotation`/`getDeclaredAnnotation` distinguished from the `...AnnotationsByType` APIs?
9. **Right location test:** are class, method, and parameter queried on the right `AnnotatedElement`?
10. **Inheritance test:** tested only on classes, remembering that `getDeclaredAnnotationsByType` differs from `getAnnotationsByType`?
11. **No automatic merging:** when a subclass has its own annotation, is the result verified not to append the parent's?
12. **No reliance on unguaranteed ordering:** does it only rely on the array order of repeated annotations of the same type, without assuming all annotation types are ordered by source?
13. **No dependency on -ea:** do tests actually execute assertions when invoked with plain `java`?
14. **Class file verification:** is `javap -v` used to distinguish container representation issues from runtime API issues?
15. **Deterministic output:** on failure, does the test clearly report which case failed, what was expected, and what was actual?

**Conclusion:** testing repeatable annotations requires looking simultaneously at **the container type, the query API, and the order of elements in the array**. A test that only counts annotations cannot detect reversed ordering; a test that only reads the container misses single annotations; and a test that only uses `getAnnotation` misses the repeated annotation list. A standalone test suite running on JDK 17+, combining `getDeclaredAnnotationsByType` with `javap -v`, verifies core Java behavior accurately and pinpoints whether an error lies at compile time, in runtime visibility, or in metadata consumption logic.
