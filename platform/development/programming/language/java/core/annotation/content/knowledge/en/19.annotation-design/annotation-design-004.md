# Intentional Annotation Design: @Target, @Retention, @Documented, @Inherited, and @Repeatable

Java allows defining annotations with `@interface`, but a well-designed annotation is more than just a name and a few data elements. An API author must decide **where it can be applied**, **how long metadata persists**, **whether it appears in public documentation**, **whether it is looked up via a superclass**, and **whether it can be declared multiple times on the same element**.

The five standard meta-annotations in this topic have distinct responsibilities:

| Meta-annotation | Design question | Example |
| --- | --- | --- |
| `@Target` | **Where** is the annotation written? | `@Target(ElementType.METHOD)` |
| `@Retention` | **Until which stage** does the metadata persist? | `@Retention(RetentionPolicy.RUNTIME)` |
| `@Documented` | Is the annotation part of the **API documentation contract**? | `@Documented` |
| `@Inherited` | When looked up on a subclass, is it **searched on the superclass**? | `@Inherited` |
| `@Repeatable` | Can **multiple annotations of the same type** be used on one element? | `@Repeatable(Tags.class)` |

These annotations describe the **rules of an annotation type**; they do not by themselves perform data validation, logging, authorization, retries, or application code generation. Business behavior only arises when a compiler, annotation processor, analysis tool, or framework actually reads and interprets the metadata.

## 1. Selection process from requirements, not enabling all five flags

A practical principle is to enable only those mechanisms that have a clear meaning for the annotation's users:

1. Identify the **consumer**: a compile-time annotation processor, bytecode analysis tool, runtime reflection, or framework.
2. Identify the **element kinds** the consumer can handle: class, method, field, constructor, parameter, type use, or another annotation.
3. Choose the **shortest sufficient** retention to avoid retaining unnecessary runtime metadata.
4. Decide whether appearing in the **Javadoc of the annotated API** is useful.
5. If the annotation marks a class, decide whether a subclass **should inherit the configuration or must redeclare it**.
6. If an element needs multiple values of the same kind, consider repeatable annotations and **design a container** that is compatible.
7. Document elements, defaults, and conflict rules; test with both the compiler and reflection.

There is no “turning everything on is best” configuration. For example, `@Documented` may make sense for `@PublicApi`, yet be unnecessary for an annotation intended only for an internal annotation processor; `@Inherited` may be right for class configuration, yet inappropriate if the configuration must be specified individually on each subtype.

## 2. @Target — restricting where an annotation can be used

`java.lang.annotation.Target` accepts `ElementType` constants. For an annotation dedicated to checking methods:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface Timed {
    String category() default "default";
}
```

`@Timed` can only be attached to a **method declaration**. It cannot be attached to a field or constructor, cannot be placed at a **method call**, and does not automatically allow annotating the `String` type in `List<String>`.

To allow multiple locations, use a set of values:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Audited {}
```

This snippet assumes `ElementType` and `Target` have been imported. It allows using `@Audited` on class/interface and method declarations in their respective contexts.

Some common targets:

| ElementType | Example usage locations |
| --- | --- |
| `TYPE` | Class, interface, enum, or annotation type declaration |
| `FIELD` | Field of a class, including enum constants |
| `METHOD` | Method declaration |
| `CONSTRUCTOR` | Constructor declaration |
| `PARAMETER` | Formal parameter declaration |
| `ANNOTATION_TYPE` | Declaration of an annotation type |
| `TYPE_PARAMETER` | Type parameter declaration `T` |
| `TYPE_USE` | Use of a type, for example `List<@Check String>` |
| `RECORD_COMPONENT` | Record component of a record |

**Do not mix declaration targets and type-use targets.** For `List<@Check String>`, the annotation needs to allow `TYPE_USE`. For `@Check private String code;`, the location may relate to a field declaration and/or a type use depending on `@Target` and applicability rules; you must design the target according to the consumer's intent.

### If @Target is omitted

An annotation type that does not declare `@Target` can be used in the appropriate **declaration contexts** according to the JLS. It **does not automatically become** an annotation usable at every `TYPE_USE`. This is not a practice to use to “reserve flexibility”: if the consumer only supports methods, declare `@Target(METHOD)` so the compiler rejects misplaced annotations early.

A common mistake is using `@Target({FIELD, METHOD, PARAMETER, TYPE_USE})` for every annotation without having a consumer that handles each location. That creates a loose contract and hard-to-explain behavior. Prefer a small, clear, and tested set of targets.

## 3. @Retention — deciding metadata lifetime

`java.lang.annotation.Retention` takes one of three `RetentionPolicy` values:

| Value | Compiler and class file | Runtime reflection |
| --- | --- | --- |
| `SOURCE` | Present in source code; not stored under the class file's annotation attributes | Cannot be read |
| `CLASS` | Retained in the class file, typically in the appropriate `RuntimeInvisible...Annotations` attributes | Cannot be read via standard reflection |
| `RUNTIME` | Retained in the class file in the appropriate `RuntimeVisible...Annotations` attributes | Can be read via the appropriate reflection API |

If **no `@Retention` is declared**, the default retention is `CLASS`. This is a common source of bugs when code calls `getAnnotation(...)` and receives `null`.

Example of an annotation serving only an annotation processor:

```java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateAdapter {}
```

This is an illustrative snippet that requires importing `Retention`, `RetentionPolicy`, `Target`, and `ElementType`. If the build only needs a processor to read the annotation from the source model, `SOURCE` is usually appropriate. There is no need to retain that configuration until runtime.

Example of an annotation serving reflection:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Endpoint {
    String path();
}
```

A consumer can obtain the `Method` and read `getAnnotation(Endpoint.class)`. However, **`RUNTIME` does not make the annotation automatically trigger a router**. A framework still has to scan methods, read `path()`, and register the route.

### Retention is not target

Two independent decisions:

- `@Target(METHOD)`: the annotation is **attached to a method declaration**.
- `@Retention(RUNTIME)`: that annotation can be **read at runtime**.

An annotation with the right target but `CLASS` retention will not appear through ordinary runtime reflection. An annotation with `RUNTIME` retention placed at a disallowed target location causes a **compile-time error**; retention never legitimizes an invalid usage location.

## 4. @Documented — publishing annotations in the Javadoc contract

`java.lang.annotation.Documented` marks that **the presence of the annotation on an API element** is content that tools such as `javadoc` should include in the appropriate documentation.

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Publicly introduced API with a stable contract. */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface PublicApi {
    /** @return the API version where support begins */
    String since();
}

/** Library service. */
@PublicApi(since = "1.0")
class LibraryService {}
```

This is a valid declaration without `main`. With `@Documented`, the Javadoc of `LibraryService` can display the `@PublicApi(since = "1.0")` annotation as part of the public contract.

**Distinguish three concepts:**

- `/** ... */` comments write the **Javadoc explaining the annotation type and its elements**.
- `@Documented` decides whether **the presence/values of the annotation at the use site** are treated as part of the documentation contract.
- `@Retention` decides **metadata storage**, not the usefulness of the Javadoc content.

`@Documented` **does not perform logging on its own**, does not force frameworks to honor the annotation, and has no superclass inheritance effect. An annotation used only for internal builds might not need `@Documented`. Conversely, annotations that affect library users, compatibility, or contracts are usually worth showing in Javadoc.

## 5. @Inherited — looking up annotations through a class's superclass

`java.lang.annotation.Inherited` causes an annotation type, when queried on a **class declaration**, to be searched on its superclass if the current class does not directly declare that annotation type.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policy {
    String value();
}

@Policy("base")
class Base {}

class Child extends Base {}
```

In runtime reflection:

```java
// With the declarations from the example above:
Child.class.getAnnotation(Policy.class).value(); // "base"
Child.class.getDeclaredAnnotation(Policy.class); // null
```

The two expressions above illustrate the results when placed inside a method. `getAnnotation()` can see an annotation that is **present** under `@Inherited` rules. `getDeclaredAnnotation()` only retrieves annotations **directly declared** on `Child`.

**Limitations you must not overlook:**

- `@Inherited` only has standard inheritance semantics when looking up an annotation on a **class**, along the **superclass** chain.
- It does not automatically look up annotations on an **interface** that a class `implements`.
- It does not make annotations placed on an **overridden method**, a hidden field, a constructor, or a parameter automatically appear on the corresponding element of a subclass.
- When a subclass declares an annotation of the same type, the value directly on the subclass is used according to lookup rules instead of being automatically merged with the superclass.
- If the annotation needs to be read by reflection at runtime, it must have `@Retention(RUNTIME)`. Having `@Inherited` with `CLASS` retention does not suddenly make reflection able to read it.

**Design question:** Do you want subclasses to **use the parent class's configuration by default**, or must each class confirm its own configuration? For security or transaction policies, implicit inheritance may not be appropriate if not clearly controlled. If you want to require redeclaration, do not use `@Inherited`.

## 6. @Repeatable — allowing multiple annotations of the same type

Before Java 8, an annotation could typically appear only once per element. `@Repeatable` makes it possible to express multiple values of the same type:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Repeatable(Tags.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("api")
@Tag("stable")
class Component {}
```

This is valid code. `Tags` is the **container annotation type** of `Tag`, with the element `Tag[] value()`. The compiler can represent multiple `@Tag` annotations through the container.

Use `getAnnotationsByType(Tag.class)` to retrieve **the values of the same type**, even when they reside inside a container:

```java
Tag[] all = Component.class.getAnnotationsByType(Tag.class);
System.out.println(all.length); // 2
```

This snippet illustrates the API and must be placed inside a valid method. In the example, there are two values corresponding to `"api"` and `"stable"`.

### Mandatory requirements for the container

JLS §9.6.3 specifies that the container `TC` of a repeatable annotation `T` must satisfy several strict requirements:

1. Have a `value()` element returning **`T[]`**, not `Object[]`, `String[]`, or any arbitrary array type.
2. Every element other than `value()` (if any) **has a default**.
3. The container's retention is **at least as long as** the repeatable annotation's retention: `SOURCE ≤ CLASS ≤ RUNTIME`.
4. The `@Target` declarations must be **compatible** according to JLS rules; the container must not narrow a valid repeatable location. Certain cases of `TYPE`, `TYPE_USE`, and `TYPE_PARAMETER` have special compatibility rules.
5. If the repeatable annotation has `@Documented`, the container **must also have** `@Documented`.
6. If the repeatable annotation has `@Inherited`, the container **must also have** `@Inherited`.

Metadata does not necessarily have to be identical on both sides in the reverse direction. For example, the JLS allows the container to have `@Documented` while the repeatable annotation does not; however, in the direction where the repeatable annotation has `@Documented` and the container lacks it, that is an **error**.

### Two misconfigured examples

```java
// INTENTIONALLY WRONG: container.value() returns the wrong array type.
@Repeatable(BadContainer.class)
@interface BadTag {}

@interface BadContainer {
    String[] value();
}
```

```java
// INTENTIONALLY WRONG: The @Repeatable annotation is retained until RUNTIME,
// whereas the container is only retained until CLASS.
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(ShortLivedTags.class)
@interface LongLivedTag {}

@Retention(RetentionPolicy.CLASS)
@interface ShortLivedTags {
    LongLivedTag[] value();
}
```

The two snippets above are **examples intentionally designed not to compile**, showing errors caused by container requirements rather than `@Repeatable` being unsupported.

### Using reflection properly with repeatable annotations

The differences among the APIs are very important:

- `getAnnotation(Tag.class)` looks up a **present** `Tag`; it **does not automatically unpack every annotation inside the container**.
- `getDeclaredAnnotation(Tag.class)` considers only a `Tag` declared directly under the **directly present** concept.
- `getAnnotationsByType(Tag.class)` returns all **associated** `Tag` annotations, including values indirectly present inside the container and inheritance rules where applicable.
- `getDeclaredAnnotationsByType(Tag.class)` reads directly or indirectly through the container **on the current element**, without searching superclasses.

For a repeatable annotation, if an API needs the list, prefer `getAnnotationsByType()` or `getDeclaredAnnotationsByType()` rather than expecting `getAnnotation()` to return multiple elements.

## 7. Combining @Documented + @Inherited + @Repeatable correctly

When an annotation is repeatable, and must also **appear in Javadoc** and **be looked up through a superclass**, declare the appropriate metadata on both the repeatable annotation and the container.

This is a very easy situation to get wrong: writing `@Inherited` and `@Documented` on the repeatable annotation while forgetting the two corresponding meta-annotations on the container will cause a compile-time error.

### Complete Java 17 example verified by execution

Create exactly one file `PolicyDemo.java`:

```java
import java.lang.annotation.*;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

/**
 * A label describing the scope of application of a service.
 *
 * @since 1.0
 */
@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    /** @return the label name provided by the application */
    String value();
}

/** Container for multiple labels on the same class. */
@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    /** @return the labels currently attached to the class */
    Label[] value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Trace {}

@Label("audit")
@Label("metrics")
class BaseService {
    @Trace
    public void run() {}
}

class ChildService extends BaseService {
    @Override
    public void run() {}
}

@Label("local")
class LocalService extends BaseService {}

public class PolicyDemo {
    private static String labels(Class<?> type) {
        return Arrays.stream(type.getAnnotationsByType(Label.class))
                .map(Label::value)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("base=" + labels(BaseService.class));
        System.out.println("child=" + labels(ChildService.class));
        System.out.println("child-declared="
                + ChildService.class.getDeclaredAnnotationsByType(Label.class).length);
        System.out.println("local=" + labels(LocalService.class));

        Method overriding = ChildService.class.getDeclaredMethod("run");
        System.out.println("override-trace="
                + overriding.isAnnotationPresent(Trace.class));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 -encoding UTF-8 PolicyDemo.java
java PolicyDemo
```

The **exact** stdout, verified with `javac` and `java`:

```text
base=audit,metrics
child=audit,metrics
child-declared=0
local=local
override-trace=false
```

**Line-by-line explanation:**

1. `base=audit,metrics`: `BaseService` directly declares two `@Label` annotations. The `getAnnotationsByType(Label.class)` API unpacks the values in the container.
2. `child=audit,metrics`: `ChildService` does not declare its own `@Label`. Because both the repeated type and the container follow `@Inherited` rules, a lookup by type via `getAnnotationsByType` can retrieve them from the superclass.
3. `child-declared=0`: `ChildService` does **not directly** declare any labels; `getDeclaredAnnotationsByType` does not look up the parent.
4. `local=local`: `LocalService` declares its own `@Label("local")`; the lookup result by type is the child's label, **without automatically accumulating** the parent's two labels `audit` and `metrics`.
5. `override-trace=false`: the `ChildService.run()` method overrides the method in `BaseService`, yet does not automatically carry the `@Trace` annotation from the parent method. `@Inherited` is not a mechanism for copying method annotations.

This code uses `@Documented` to support API documentation. The program does not invoke `javadoc`, so no separate output line is produced by `@Documented`.

### Generating sample Javadoc documentation

If you want to view Javadoc for the annotation types and labeled classes:

```bash
javadoc -private -encoding UTF-8 -docencoding UTF-8 -d docs PolicyDemo.java
```

The `-private` flag helps display package-private types in the demo as well. The actual rendering depends on the Javadoc tool and options, but `@Documented` expresses the intent to publish the annotation at its usage sites.

The `javadoc` command may emit warnings about incomplete documentation on the illustrative classes; those are tool messages and are **not** part of the stdout listed for `java PolicyDemo`.

## 8. Typical selection sets by purpose

These are **decision templates**, not formulas forcing every project to use the exact same configuration.

| Scenario | Target | Retention | Documented | Inherited | Repeatable |
| --- | --- | --- | --- | --- | --- |
| Marker for an annotation processor to generate an adapter for a class | `TYPE` | `SOURCE` | Usually no | Usually no | Only if there are genuinely multiple configurations |
| Route annotation for a method scanned by a framework at runtime | `METHOD` | `RUNTIME` | Possibly yes for public APIs | Not useful for methods | Usually no, unless the framework supports multiple routes |
| Runtime class configuration shared with subclasses | `TYPE` | `RUNTIME` | Depends on public meaning | Yes if implicit inheritance is needed | Only if multiple configurations are needed |
| Classification label on a class for documentation and tooling | `TYPE` | `RUNTIME` or `CLASS` depending on consumer | Usually yes | Depends on policy | Possibly yes |
| Nullability/type checker for type uses | `TYPE_USE` | `CLASS` or `SOURCE` depending on checker | According to public API | Not class metadata inheritance | According to checker semantics |
| Metadata with multiple independent conditions on a class | `TYPE` | Depends on reading time | If public | If configuration is inherited | Yes, and a container must be designed |

**Decision rule:** Target derives from **location**, retention from the **consumer phase**, documented from **API documentation needs**, inherited from **subclass rules**, and repeatable from the **number of values to attach**. Do not select everything merely because an existing framework supports these meta-annotations.

## 9. Design conflicts to resolve with a clear contract

### A. Inherit metadata or require subtypes to redefine it?

If `@ServicePolicy` affects security or transaction scope, should a new subclass automatically receive the parent class's policy? `@Inherited` can cause tools querying `Class.getAnnotation()` to find the old configuration.

If a subtype must have its policy reviewed separately, do not enable `@Inherited` automatically. You can require direct declaration and use `getDeclaredAnnotation()` in the validator.

### B. Multiple annotations or a single annotation with an array?

Two approaches:

```java
// Approach 1: repeatable annotation.
@Tag("audit")
@Tag("metrics")
class ExampleA {}

// Approach 2: annotation with an array.
// Assume @TagList has String[] value().
@TagList({"audit", "metrics"})
class ExampleB {}
```

This is an **illustrative snippet** using separately declared `Tag` or `TagList`. With a repeatable annotation, each label is an independent annotation that can have multiple elements; with a single annotation containing an array, the consumer gets one centralized list.

Consider the following:

- Do you need **multiple configurations with complex structures**, each carrying its own fields? Repeatable is usually natural.
- Is there only a simple, straightforward list of names? An annotation with `String[]` may be easier to use.
- Do you need to synchronize retention, target, documented, and inherited across both the repeated type and the container? Repeatable introduces extra compatibility responsibilities.
- Does the system use `getAnnotationsByType()` properly? Using only `getAnnotation()` may miss elements inside the container.
- What rules are needed for ordering, duplicates, inheritance, and overriding? Document them clearly in Javadoc and tests.

### C. Public API annotation or internal metadata?

If library users need to know about `@StableApi`, `@Documented` is a reasonable choice. If the annotation only triggers an internal code generator, exposing the annotation on every Javadoc page may clutter the API contract.

### D. Is RUNTIME retention truly necessary?

Not necessarily. A compile-time processor that only needs `SOURCE` can still read the annotation. A bytecode analyzer can read `CLASS` metadata using class-file tooling. Only use `RUNTIME` if the consumer needs reflection/runtime access.

### E. Is the system interpreting meta-annotations on its own?

Standard Java reflection **does not automatically turn** an annotation placed on an annotation type into an annotation directly present on every class that uses it.

```java
// With an appropriate @Target and RUNTIME retention:
@PolicyTag
@interface AuditService {}

@AuditService
class Server {}
```

This is an **illustrative declaration** requiring suitable `PolicyTag` and `AuditService` types. If only `AuditService` is placed on `Server`, Java reflection does not automatically make `Server.class.getAnnotation(PolicyTag.class)` non-`null`. A framework may traverse meta-annotations deeply, but that is an **additional rule of the framework**, not a default effect of `@Documented`, `@Inherited`, or `@Repeatable`.

## 10. Compile-time and runtime testing for a new annotation type

Before publishing an annotation, you should have the following kinds of tests:

**Compile-time tests:**

- Apply the annotation at the locations allowed by `@Target`; compilation must succeed.
- Apply it to an invalid location such as a field when only `METHOD` is allowed; the compiler must reject it.
- If using `@Repeatable`, test at least two annotations of the same type; verify the container requirements and mandatory meta-annotations.
- Test an **invalid container** case (different from `value() T[]`, retention too short, or missing `@Inherited`/`@Documented` when the repeated type requires them) and verify the compiler reports an error.

**Runtime tests:**

- Reflection finds the `RUNTIME` annotation at the expected locations.
- `SOURCE` or `CLASS` annotations are not mistaken for runtime reflection annotations.
- With `@Inherited`, test a subclass without a declaration, a subclass with a direct declaration, and the interface case.
- With repeatable annotations, test `getAnnotationsByType()` and `getDeclaredAnnotationsByType()`, not only `getAnnotation()`.
- With method overriding, confirm that method metadata is not automatically inherited in ways not specified by the standard.

**Documentation tests:**

- Generate Javadoc and check whether public annotations are displayed appropriately.
- Describe each annotation element and its default, especially inheritance, override, and multi-value rules.
- Ensure the documentation does not promise business behavior that the consumer has not implemented.

## 11. Common mistakes

**1. Enabling RUNTIME for every annotation.** Retention should follow consumer needs, not habit.

**2. Omitting Target for “flexible usage”.** This can allow the annotation to be placed outside declarations the consumer actually understands. A narrow target helps the compiler catch mistakes early.

**3. Using @Inherited on a method annotation and expecting overrides to inherit it.** The standard mechanism concerns looking up annotations on a **class through its superclass**.

**4. Using @Inherited and expecting implementing an interface to propagate the annotation.** Interfaces are not part of `@Inherited`'s automatic lookup path.

**5. Thinking @Documented equals full Javadoc.** It does not write the explanation of the annotation type or its elements for the author.

**6. Thinking @Documented makes an annotation readable at runtime.** That is the job of `@Retention(RUNTIME)`.

**7. Using @Repeatable when container.value() is not T[].** This is a compile-time error due to container constraints.

**8. Forgetting retention/target/@Inherited/@Documented on the container.** The JLS requires the container to satisfy the corresponding compatibility conditions.

**9. Using only getAnnotation with repeatable annotations.** You should use `getAnnotationsByType()` to retrieve values indirectly held inside the container as well.

**10. Expecting repeatable annotations on a subclass to automatically accumulate all values from the superclass.** Java has specific *associated* and inheritance rules; when a subclass directly declares an annotation of the same type, the result does not automatically merge all values from the parent.

**11. Treating annotations as runtime logic.** An `@Audit` marker does not emit logs on its own; a consumer must implement the behavior.

**12. Forgetting to check the contract when modifying a library's meta-annotations.** Changing `@Target` can break compilation for previously valid clients; changing retention can cause reflection to lose data; adding `@Inherited` can alter subclass behavior; changing repeated/container types can break annotation-reading code.

## 12. Pre-merge design checklist

| Question | Expected verification |
| --- | --- |
| Which consumer is the annotation for? | Javadoc clearly states the processor, runtime framework, or tool |
| Is Target accurate? | Only locations understood by the consumer are allowed |
| Is Retention sufficient without being excessive? | SOURCE/CLASS/RUNTIME matching the lifecycle |
| Is @Documented needed? | The API contract genuinely needs the annotation displayed |
| Is configuration inherited? | Class hierarchy and direct declaration cases have been tested |
| Are there multiple values of the same kind? | Repeatable or array according to appropriate semantics |
| Is the repeatable container valid? | value() T[], defaults, retention, target, documented, inherited |
| Is the repeatable annotation read with the right API? | getAnnotationsByType/getDeclaredAnnotationsByType |
| Are there subclass conflicts? | Override/non-merging policy is clearly stated |
| Does each element have appropriate documentation/default? | Values and constraints match the consumer |
| Are there tests with javac, java, and javadoc? | Clear results depending on the phases used |
| Does changing meta-annotations affect clients? | Compatibility reviewed at both compile-time and runtime |

## 13. Self-check questions

**Question 1.** Does an annotation used only in an annotation processor on a class need `RUNTIME` by default?

**Answer:** No. `@Retention(SOURCE)` is usually sufficient; `@Target(TYPE)` clarifies the usage scope.

**Question 2.** Do `@Documented` and `@Retention(RUNTIME)` do the same thing?

**Answer:** No. One affects whether the annotation is displayed in API documentation, while the other determines whether metadata is available for reflection at runtime.

**Question 3.** The class `Child extends Base` does not declare the `@Policy` annotation, whereas `Base` does and the `Policy` type has `@Inherited`. Which two methods can return different results?

**Answer:** `Child.class.getAnnotation(Policy.class)` can retrieve it from the superclass, whereas `getDeclaredAnnotation(Policy.class)` is `null`, assuming the retention is `RUNTIME`.

**Question 4.** Is `@Repeatable(Tags.class)` with `Tags.value()` of type `String[]` valid for the repeated type `Tag`?

**Answer:** No. The container must have `Tag[] value()`.

**Question 5.** A repeated annotation is marked with `@Inherited` and `@Documented`; the container only has retention and target. Is that enough?

**Answer:** No. The container must be marked with `@Inherited` and `@Documented` accordingly under the JLS.

**Question 6.** Does an overriding method automatically receive an `@Inherited` annotation from the parent method?

**Answer:** No. This is not how `@Inherited` works.

**Question 7.** Does `getAnnotationsByType(Label.class)` on a subclass that directly writes `@Label("local")` return the parent's labels as well by default?

**Answer:** No. Under the standard repeatable and inheritance model, associated annotations on the child do not automatically accumulate the list from the superclass.

**Question 8.** When designing a `@Tracked` annotation with multiple labels, when should you use repeatable instead of an array?

**Answer:** When each application is an independent configuration or has multiple separate elements and tooling wants to process each attachment individually. If it is simply a plain list of strings, `String[]` may be more convenient.

## Official documentation

- [Java Language Specification 17, §9.6.3 — Repeatable Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3).
- [JLS 17, §9.6.4.1 — @Target](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1).
- [JLS 17, §9.6.4.2 — @Retention](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2).
- [JLS 17, §9.6.4.3 — @Inherited](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3).
- [Java SE 17 API — Documented](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Documented.html).
- [Java SE 17 API — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html).
- [Java SE 17 API — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

**Conclusion:** Intentional annotation design means **allowing the right locations, retaining metadata for the right lifecycle, publishing the right contract, inheriting within the right scope, and repeating only when genuinely needed**. With `@Repeatable`, do not forget the container and compatibility rules. With `@Inherited`, rely on the standard superclass behavior only when that is truly the intended API contract.
