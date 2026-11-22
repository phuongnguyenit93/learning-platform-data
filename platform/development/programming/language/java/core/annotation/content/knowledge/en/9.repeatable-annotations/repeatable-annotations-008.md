# Compatibility Impact When Converting a Regular Annotation to a Repeatable Annotation in Java

## 1. The Problem: A Small Change in Definition, a Major Impact on Metadata Readers

A **non-repeatable annotation** can appear only once in the same declaration or type-use context. Since Java 8, `@Repeatable` allows writing multiple annotations of the same type on an element, but Java needs a **containing annotation type** (commonly called a *container*) to hold those occurrences.

For example, initially, the API only allows each class to carry one role:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Role {
    String value();
}
~~~

Classes using the old version of the API:

~~~java
@Role("reader")
class ReaderService {
}
~~~

After some time, the requirements change: the same service can carry both `"reader"` and `"writer"`. The library author wants to turn `Role` into a repeatable annotation.

Typical change:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
public @interface Role {
    String value();
}
~~~

Adding the container annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Roles {
    Role[] value();
}
~~~

Both snippets are **definitions in separate files `Role.java` and `Roles.java` in the same package**, not a single-file program. From there, you can use:

~~~java
@Role("reader")
@Role("writer")
class ReaderWriterService {
}
~~~

The important question when releasing the library is: **can old client code still compile and link; can old annotation processors still read the data correctly?**

Three layers of compatibility must be separated:

1. **Source compatibility**: can source code that previously used the annotation still compile when using the new API version?
2. **Binary compatibility**: can previously compiled client `.class` files still link with the new annotation definition?
3. **Behavioral compatibility**: do processors, frameworks, or reflection code still return/conclude the same as before?

According to the contract of `java.lang.reflect.AnnotatedElement` in Java SE 17, converting an annotation type `T` to be repeatable is **source and binary compatible with old uses of `T` and container `TC`** when the conversion is performed according to the rules. **However, it cannot be inferred that all reflection results and application behavior remain the same**.

## 2. How Does the Compiler Represent One Annotation and Multiple Annotations?

There are two cases to examine separately.

**One occurrence**:

~~~java
@Role("reader")
class SingleRole {
}
~~~

In Java 17, having just a single `@Role` ordinarily continues to be stored as **one direct `Role` annotation**. Just because `@Repeatable` is added to `Role` does not mean the compiler must wrap a single use into `Roles`.

**Multiple occurrences at the same location**:

~~~java
@Role("reader")
@Role("writer")
class MultipleRoles {
}
~~~

For two annotations of the same type as above, the compiler treats them as equivalent to an implicit container:

~~~java
@Roles({@Role("reader"), @Role("writer")})
class MultipleRoles {
}
~~~

The two `MultipleRoles` declarations above are **two alternatives**, not placed simultaneously in the same file. The container has a `value()` element returning `Role[]`; the order of the roles in the array corresponds to the left-to-right order of the annotations in the source.

Consequence: when code reads only **direct annotations**, `MultipleRoles` can appear as an annotation of type `Roles`, with the `Role` annotations inside it. When using an API dedicated to repeatable annotations, Java **unwraps the container** to return each `Role`.

This is the main reason why converting from non-repeatable to repeatable can affect **metadata readers** without causing compilation errors.

## 3. Runnable Java 17 Example: Comparing Old and New Reflection APIs

Create a single file **`RepeatableCompatibilityDemo.java`**:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}

@Role("reader")
class OneRole {
}

@Role("reader")
@Role("writer")
class TwoRoles {
}

@Roles({@Role("admin"), @Role("auditor")})
class ExplicitContainer {
}

public class RepeatableCompatibilityDemo {
    public static void main(String[] args) {
        inspect("one", OneRole.class);
        inspect("two", TwoRoles.class);
        inspect("explicit", ExplicitContainer.class);
    }

    private static void inspect(String label, Class<?> type) {
        Role direct = type.getAnnotation(Role.class);

        String[] values = Arrays.stream(type.getAnnotationsByType(Role.class))
                .map(Role::value)
                .toArray(String[]::new);

        Annotation[] raw = type.getDeclaredAnnotations();
        String[] rawTypes = Arrays.stream(raw)
                .map(a -> a.annotationType().getSimpleName())
                .toArray(String[]::new);

        System.out.println(label
                + ": direct=" + (direct == null ? "null" : direct.value())
                + ", byType=" + Arrays.toString(values)
                + ", container=" + (type.getDeclaredAnnotation(Roles.class) != null)
                + ", declaredTypes=" + Arrays.toString(rawTypes));
    }
}
~~~

Run with JDK 17+ in the directory containing the file:

~~~bash
javac RepeatableCompatibilityDemo.java
java RepeatableCompatibilityDemo
~~~

**Exact stdout**:

~~~text
one: direct=reader, byType=[reader], container=false, declaredTypes=[Role]
two: direct=null, byType=[reader, writer], container=true, declaredTypes=[Roles]
explicit: direct=null, byType=[admin, auditor], container=true, declaredTypes=[Roles]
~~~

Explanation:

- **`OneRole`**: has only one `@Role`, so `getAnnotation(Role.class)` returns the corresponding object. `getAnnotationsByType(Role.class)` also returns an array containing one element.
- **`TwoRoles`**: two annotations of the same type are represented by the `Roles` container. `getAnnotation(Role.class)` returns `null` because there is no direct `Role`; `getAnnotationsByType(Role.class)` unwraps the container and returns both.
- **`ExplicitContainer`**: using `@Roles(...)` directly is also unwrapped into two elements by the `getAnnotationsByType(Role.class)` API. Meanwhile, `getAnnotation(Role.class)` still returns `null`.
- **`getDeclaredAnnotations()`** returns the annotations that appear directly at the class file/reflection level. In the two cases containing multiple `Role` annotations, the direct element is the `Roles` container, so code that only searches for `Role` in this array will miss the metadata that needs to be processed.

The sample code has `@Retention(RUNTIME)` on both `Role` and `Roles`. Without retaining metadata at runtime, we cannot use a reflection example like the one above to demonstrate the difference.

### Note on the Nature of the Example

This is a program **already using the post-conversion API**, intended to illustrate the difference between a site with one annotation and a site with multiple annotations. It **does not by itself prove** that an old `.class` file can link with a new library version: to verify binary compatibility empirically, you need to compile the client against the old version, keep the client bytecode unchanged, and then run it with the new library.

## 4. Source Compatibility: Old Source Code Usually Needs No Modification

Suppose a client has written:

~~~java
@Role("reader")
class ExistingClient {
}
~~~

After `Role` is declared repeatable, this code remains valid and compiles. Programs using the `Role` type as before do not need to modify their syntax merely because `@Repeatable(Roles.class)` was added.

One benefit of the conversion process is that **there is no need to force all clients currently using a single annotation to switch to the container syntax**. Clients can continue using `@Role("reader")`, while clients that need multiple roles can use:

~~~java
@Role("reader")
@Role("writer")
class MultiRoleClient {
}
~~~

Source code containing multiple annotations of the same type **before `Role` was repeatable** would be invalid if two `@Role` annotations were written directly on the same element. Adding `@Repeatable` **extends** that syntax at locations where both `Role` and the container are permitted to be applied.

However, the source compatibility claim here applies only to **converting to repeatable status according to the rules**. If you simultaneously **rename `Role`**, remove the `value()` element, change an element's return type, make incompatible target/retention changes, or alter other APIs, those are separate changes that must be evaluated independently.

## 5. Binary Compatibility: Recompiling All Clients Is Not Required

A previous `.class` file carrying a `@Role("reader")` has metadata describing the direct use of `Role`. When the library adds `@Repeatable(Roles.class)`, **the old client bytecode does not rewrite itself into a container**. It still describes a direct `Role` and can link with the new `Role` definition according to the compatibility rules published by the Java API.

Similarly, if `Roles` previously existed as a regular annotation with a `Role[] value()` element, class files using `Roles` can continue to link after `Roles` is designated as the official container for `Role`.

Adding the container annotation as **a new type** is another common case. In that situation, old clients that do not yet know about `Roles` can still continue using `Role` as before, whereas new clients compiled from source containing two `@Role` annotations additionally depend on `Roles` at runtime if the container's retention is `RUNTIME`.

The phrase "binary compatible" must be understood precisely:

- It states that binaries compiled from old valid usages **can link** with the new annotation type according to the guarantee stated in Java SE 17.
- It **does not guarantee** that every scanning/reflection library, bytecode transformer, or external framework will interpret the set of annotations the same way as before.
- It also **does not allow omitting the container at runtime** when newly compiled classes actually contain `Roles` metadata. Missing the container type or changing the container definition incompatibly can cause metadata reading to fail or go unrecognized.

Therefore, binary testing should retain old client artifacts in the test suite, rather than simply recompiling the entire project and declaring everything compatible.

## 6. Behavioral Compatibility: Changes in Reflection Are the Greatest Risk

`AnnotatedElement` distinguishes between annotations that are **directly present** and **indirectly present** (inside a container). It also has the concepts of **present** and **associated** to handle annotation inheritance rules on classes.

| Reflection API | With one direct `@Role` | With two `@Role` annotations contained in `@Roles` |
| --- | --- | --- |
| `getAnnotation(Role.class)` | Returns `Role` | Usually `null` if no `Role` is directly present or inherited according to the rules |
| `getDeclaredAnnotation(Role.class)` | Returns `Role` | `null` |
| `isAnnotationPresent(Role.class)` | `true` | `false` in the example without inheritance |
| `getAnnotations()` / `getDeclaredAnnotations()` | Contains `Role` | Contains `Roles` |
| `getAnnotationsByType(Role.class)` | One element | Two elements |
| `getDeclaredAnnotationsByType(Role.class)` | One element | Two elements |

The table examines **classes without `@Inherited` issues**, such as the `OneRole` and `TwoRoles` examples that were run. With `@Inherited` annotations and superclass/subclass relationships, the API's inheritance rules must additionally be applied; the rows in the table should not be used as conclusions for all cases.

The consumer's metadata processing policy can change significantly:

~~~java
Role role = type.getAnnotation(Role.class);
if (role != null) {
    register(role.value());
}
~~~

The snippet above is **a hypothetical fragment inside a method that has a `Class<?> type` variable and a `register(String)` method**. It makes sense when the annotation is non-repeatable and applied once. When a class has two `@Role` annotations, `getAnnotation(Role.class)` can return `null`, leading to **all roles being skipped**.

To support multiple `Role` annotations, the consumer needs to change its logic:

~~~java
for (Role role : type.getAnnotationsByType(Role.class)) {
    register(role.value());
}
~~~

This is also a fragment that requires the `register` method in a real application. For a class with only one `@Role`, the loop runs once; for a class with two `@Role` annotations, the loop runs twice. This is a change in **the consumer's logic**, not something obtained automatically when the library merely adds `@Repeatable`.

A subsequent business issue: if multiple `Role` annotations can be declared, the processing code must clearly state whether to **merge**, **prioritize**, **deduplicate**, **reject conflicts**, or **preserve order**. Java preserves the order of annotations in the container according to source order, but Java does not know how the application wants to handle duplicates/conflicts.

## 7. Pre-Existing Container: Results Can Change Even Without Recompiling the Client

Before `Role` became repeatable, a project may already have had a `Roles` annotation accepting an array:

~~~java
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}

@Roles({@Role("reader"), @Role("writer")})
class OldStyleMultiple {
}
~~~

This is **an illustrative fragment of the old version**, without imports and retention added yet for runtime reflection to work. If both `Role` and `Roles` have `RUNTIME` retention, suppose `OldStyleMultiple.class` was compiled **before** `@Repeatable` existed, then:

- `getAnnotation(Roles.class)` sees the `Roles` container.
- `getAnnotation(Role.class)` does not see a direct `Role`.
- `getAnnotationsByType(Role.class)` does not yet treat `Roles` as the official container of a repeatable `Role`, because `Role` does not yet have `@Repeatable(Roles.class)`; the result may be an empty array.

After updating only **the definition of `Role`** to become a valid `@Repeatable(Roles.class)`, runtime reflection now knows that `Roles` is the container of `Role`. When reading **the exact same unchanged `OldStyleMultiple` class file** again, `getAnnotationsByType(Role.class)` can return the two roles inside the container.

This is a very noteworthy case: **the client's source and binary remain unchanged**, yet the result of **a reflection method** changes because the repeatability metadata of the annotation type has changed.

Methods that do not automatically unwrap containers, such as `getAnnotation(Role.class)` and `getAnnotation(Roles.class)`, do not change their results merely because `Roles` is designated as the container. It is the `get[Declared]AnnotationsByType` API family that changes its view once it knows the repeatable mapping.

If the old framework already unwrapped `Roles.value()` on its own, after adding `@Repeatable` you must avoid **unwrapping the container twice** or combining results from both reading paths in an uncontrolled manner.

## 8. Why Must the Container Be Designed to Specification?

Not every annotation containing `Role[]` is automatically accepted by the compiler as a container. `@Repeatable(Roles.class)` must reference a valid **containing annotation type** according to JLS §9.6.3.

Mandatory conditions to check:

1. `Roles` declares `Role[] value();` with **the exact element and array type**. `Object[]`, `String[]`, or `Role value()` are all unsuitable.
2. If `Roles` has elements other than `value()`, all of those elements must have a `default`, so that the compiler can create an implicit container.
3. The retention of `Roles` must be **at least as long as the retention of `Role`**. For example, if `Role` has `RUNTIME`, then `Roles` must also have `RUNTIME`; if `Role` has `SOURCE`, the container may be retained longer.
4. The `@Target` scope of the container must not be wider than the applicability scope of the original annotation according to the specific rules of the JLS. The container can be narrower, making repetition valid only on certain targets.
5. If `Role` is marked with `@Documented`, then `Roles` must also have `@Documented`.
6. If `Role` is marked with `@Inherited`, then `Roles` must also have `@Inherited`.

The last two directions are **not completely symmetrical**: the container is permitted to have `@Documented` or `@Inherited` even when the original annotation does not. However, to avoid surprises in documentation presentation or metadata inheritance, these policies should be designed intentionally.

### Example of an Invalid Container

~~~java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@interface Roles {
    Role[] value();
}
~~~

The snippet above is **an intentional compilation error example**: `Role` is retained until `RUNTIME`, whereas `Roles` only goes up to `CLASS`. Java does not accept a container configuration with a shorter retention than the original annotation.

Another error:

~~~java
// Invalid if Roles.value() returns Object[]:
// @interface Roles {
//     Object[] value();
// }
~~~

You cannot use an arbitrary container with an `Object[]` array and expect `getAnnotationsByType(Role.class)` to treat it as `Role[]`.

### The Container Target Can Affect Extensibility

For example, `Role` was originally allowed on `TYPE` and `METHOD`, while `Roles` only has `@Target(TYPE)`. **Applying one `@Role` on a method** may still be valid; however, **applying two `@Role` annotations on a method** is invalid because the compiler cannot place the implicit container on that target. Thus, adding repeatable does not necessarily mean the annotation can be repeated everywhere it can appear singly.

When converting, check both **existing usage sites** and **new sites expected to allow repetition**, especially with `TYPE_USE`, `TYPE_PARAMETER`, record components, or targets with intersecting rules.

## 9. `@Inherited`: A Source of Differences When Repeatable Annotations Appear on a Superclass

`@Inherited` only governs certain forms of annotation lookup **on classes**, and does not cause metadata to automatically propagate to every method or interface.

If an annotation `Role` is marked with `@Inherited`, then the container `Roles` must also be `@Inherited`. When reading a subclass via `getAnnotationsByType(Role.class)`, Java can return the `Role` annotations inherited from the superclass if the subclass has no `Role` directly or indirectly attached to itself.

If the subclass **has its own `@Role`**, the result is usually the role on the subclass, not automatically merged with all roles inherited from the superclass. Therefore, migrating to repeatable requires clearly defining the meaning of the inheritance policy: **replace the parent's set of roles or merge both?** The standard reflection API provides specific semantics; merging results according to a different policy requires custom logic.

Important: `getAnnotation(Role.class)` and `getAnnotationsByType(Role.class)` use different presence/association concepts. Do not conclude simply with "`Role` has `@Inherited`, so every scanner works automatically," especially when the roles on the superclass have already been wrapped into `Roles`.

## 10. `@Documented` and Annotation Processors: Scope of Impact Extends Beyond Runtime

**Javadoc:** If the original annotation `Role` is marked `@Documented`, the container must also be `@Documented`. This ensures the JLS does not allow a container configuration to drop the commitment to publish the original annotation. However, how annotations are rendered in HTML is still handled by the Javadoc tool; you should inspect the generated documentation after migrating.

**Compile-time annotation processors:** Processors that read annotation structures at compile time may see a container annotation when annotations of the same type are repeated. If a processor only looks for a `Role` type or accesses the list of annotation mirrors directly assuming there is no container, code generation or validation may miss the repeatable group. Code using `javax.lang.model.element.AnnotationMirror` and `RoundEnvironment` should be tested with a single annotation, multiple annotations, and an explicit container. Do not assume the compile-time API automatically behaves **identically** to `AnnotatedElement.getAnnotationsByType` at runtime; they are two different models.

**Frameworks:** Frameworks have their own annotation-reading APIs and may already handle containers or meta-annotations in their own way. When upgrading the annotation library, verify the contract of the framework version in use rather than assuming that adding `@Repeatable` automatically fixes all metadata-reading paths.

## 11. Compatibility Scenarios to Test Before Release

| Scenario | Key Expectation | What to Check |
| --- | --- | --- |
| Old client with one `@Role` | Still usable; if retention is `RUNTIME`, direct reading still retrieves it | Compile old source with new library; run old class with new library |
| New client with one `@Role` | Metadata usually remains a direct `Role` | `getAnnotation` and `getAnnotationsByType` |
| New client with multiple `@Role` annotations | Container represents the values | `getDeclaredAnnotations`, `getAnnotationsByType` |
| Old client with explicit `@Roles(...)` | Can still link, but the by-type API may unwrap the container after migration | Reflection before/after changing `@Repeatable` |
| Consumer using `getAnnotation(Role.class)` | Risk of ignoring elements when the annotation is repeated | Switch to `getAnnotationsByType` when business logic allows multiple |
| Consumer using `getDeclaredAnnotations()` | May see `Roles` instead of `Role` | Identify the container and processing order |
| With `@Inherited` | Subclass may return different results depending on presence/association | Test superclass and subclass |
| With `@Documented` | Container must be consistent, Javadoc must be correct | Compile + inspect HTML |
| Custom annotation processor / framework | May not yet understand repeatable/container | Integration tests for the exact metadata-reading paths |

Tests should include **old compiled artifacts**, **new compiled artifacts**, and **old consumer code**. Testing only sources freshly recompiled with a new JDK is not sufficient to prove backward compatibility of a release.

### Practical Conversion Workflow

1. **Inventory consumers**: find code calling `getAnnotation`, `isAnnotationPresent`, `getDeclaredAnnotations`, `getAnnotationsByType`, compile-time processors, or framework-specific scanning APIs.
2. **Keep the annotation type stable**: preserve the fully qualified name of `Role`, the `value()` element, element types, target/retention, and legacy contracts whenever possible.
3. **Choose the container**: create a new `Roles` or use an existing type if it truly meets the specification; verify `value()`, defaults, retention, target, `@Inherited`, and `@Documented`.
4. **Upgrade consumers before expanding data**: update reading paths to repeatable-aware APIs, define duplicate, ordering, and conflict handling; test with both single and multiple annotations.
5. **Deploy/ensure container availability at runtime**: especially when new clients have compiled two direct annotations into a container metadata entry.
6. **Test across an old/new matrix**: compile old source against the new API, run old binaries with the new API, and include new classes with two annotations. Verify the behavior of frameworks/processors/Javadoc if they are part of the contract.
7. **Document behavioral changes clearly**: communicate to API integrators that methods retrieving a single direct annotation may no longer see repeated cases.

Ordering consumer upgrades before allowing multiple annotations to appear widely helps reduce the risk of old scanners silently ignoring metadata.

## 12. Common Misconceptions

**"Going from `@Role` to `@Repeatable` is a binary breaking change."** Not necessarily; a valid change to repeatable alone is described by Java as source/binary compatible. The risk usually lies in **metadata-reading behavior** and accompanying API changes.

**"`getAnnotation(Role.class)` will return the first role if there are two roles."** False. With two `@Role` annotations wrapped via `Roles`, there is no direct `Role`, so the result can be `null`; the right API for the full set of values is `getAnnotationsByType(Role.class)`.

**"Even a single `Role` annotation definitely turns into `Roles`."** False. A single usage continues to be direct in the normal case; the compiler does not need a container for one usage.

**"Binary compatibility means all reflection results are invariant."** False. If the container existed before `Role` was repeatable, `getAnnotationsByType(Role.class)` may begin unwrapping the container even though the old class file remains unchanged.

**"Having `Role[] value()` is enough to serve as a container."** False. There are also requirements on retention, target, defaults for additional elements, `@Documented`, and `@Inherited`.

**"You can read all repeatable annotations with `getDeclaredAnnotations()` and just filter by the name `Role`."** False. With multiple usages, the raw annotation can be `Roles`; use the by-type API or handle the container intentionally.

**"If a repeatable annotation has `@Inherited`, subclasses always automatically merge all values from the superclass."** False. The API applies inheritance/association rules and does not perform a union of roles across all levels by default.

**"Adding `@Repeatable` makes frameworks and processors automatically understand business semantics."** False. `@Repeatable` only defines syntax and container mapping; the consumer must decide how to process the metadata.

## 13. Self-Check

**Question 1.** An old compiled class has `@Role("reader")`. If only a valid `@Repeatable(Roles.class)` is added to `Role`, does the class file automatically turn into `@Roles({@Role("reader")})`?

**Answer:** No. The metadata of the old class file does not change on its own; repeatability is a property of the annotation type used when the compiler processes multiple usages and when the reflection API recognizes the container.

**Question 2.** Why can old code `clazz.getAnnotation(Role.class)` return `null` after a class is annotated with two `@Role` annotations?

**Answer:** The two annotations are represented by a direct `Roles` container, while `Role` is located indirectly inside. `getAnnotation` does not unwrap the container to return an arbitrary element.

**Question 3.** Through which API should a list of repeatable `Role` annotations be read?

**Answer:** `getAnnotationsByType(Role.class)` when you also want inherited cases according to the relevant semantics; `getDeclaredAnnotationsByType(Role.class)` when you only want values declared directly or indirectly on the element itself.

**Question 4.** `Role` has `RUNTIME` retention, and the container `Roles` has `CLASS` retention. Can it be used as a valid repeatable annotation?

**Answer:** No. The container must have a retention at least equal to that of the original annotation.

**Question 5.** Before `Role` became repeatable, a class already used `@Roles({@Role("reader"), @Role("writer")})` and both had `RUNTIME` retention. After the conversion, what can change even without recompiling the class?

**Answer:** `getAnnotationsByType(Role.class)` can begin unwrapping `Roles` and returning both `Role` annotations, because `Role` now explicitly specifies the container via `@Repeatable`.

**Hands-on exercise:** Run `RepeatableCompatibilityDemo.java` and record the three results. Then try replacing the `getAnnotationsByType(Role.class)` consumer with `getAnnotation(Role.class)` in the role-iteration logic. Compare the cases with one annotation, two annotations, and an explicit container. Explain the difference using three concepts: **directly present**, **indirectly present**, and **containing annotation**.

## 14. Java SE 17 References

- [Java SE 17 — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): clearly describes source/binary compatibility and changes in reflection results when an annotation type becomes repeatable.
- [JLS §9.6.3 — Repeatable Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3): conditions for a valid container annotation.
- [JLS §9.7.5 — Multiple Annotations of the Same Interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.5): compiler rules for multiple annotations of the same type.
- [Java SE 17 — `Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): the API and role of the containing annotation type.

When converting a regular annotation to a repeatable annotation, preserving **the old type** helps maintain source and binary compatibility. Preserving **observable behavior** also depends on all consumers: they need to account for the container, the by-type APIs, inheritance rules, and the policy for handling multiple values.
