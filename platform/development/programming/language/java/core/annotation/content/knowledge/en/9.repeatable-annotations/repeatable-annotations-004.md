# Target, Retention, Documented, and Inherited Constraints of a Repeatable Annotation's Containing Type

An annotation in Java can appear multiple times on the same declaration when that annotation type is marked with `@Repeatable`. However, merely declaring `@Repeatable(Container.class)` is not enough. The **containing annotation type (often called the container)** must be compatible with the repeated annotation (the base/repeatable annotation) according to the rules for `@Target`, `@Retention`, `@Documented`, and `@Inherited`.

If these rules are violated, an error may occur **immediately when declaring the annotation** or **when using it repeatedly at a specific location**. Even when the code compiles successfully, choosing inconsistent metadata can lead to unexpected results when reflection reads the annotations or when generating Javadoc.

This lesson focuses on **the contract between a repeatable annotation and its containing type**, along with how to verify it in practice with Java 17 or later.

## 1. Two Types Participating in a Repeatable Annotation

Example of a `@Role` annotation that can be repeated on the same class:

~~~java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}

@Role("reader")
@Role("writer")
class AccountService {}
~~~

Here:

- `Role` is the **base annotation type**: the annotation the source author wants to repeat.
- `Roles` is the **containing annotation type**: it holds an array of `Role` via the `Role[] value()` element.
- When multiple `@Role` annotations appear at the same location, Java treats them as an **implicit container annotation** whose `value` holds the base annotations in source order.
- `@Repeatable(Roles.class)` must point to the exact containing type. The name `Roles` is merely a readable convention; Java does not automatically infer the container by appending the letter “s”.

The two declarations above use the default `CLASS` retention; the example only illustrates syntax and is not yet designed for runtime reflection.

### Foundational Conditions for the Container

According to the Java Language Specification (JLS) §9.6.3, for `Roles` to be a valid containing type of `Role`:

1. It must have a **`Role[] value()`** element with the exact return type.
2. Any element other than `value()`, if present, **must declare a default value**.
3. The retention of the container must be **at least as long as** the retention of the base annotation.
4. The container may only be applicable at locations where the base annotation is also applicable, with special equivalence rules for `TYPE`, `ANNOTATION_TYPE`, and `TYPE_PARAMETER`.
5. If the base has `@Documented`, the container must also have `@Documented`.
6. If the base has `@Inherited`, the container must also have `@Inherited`.

These conditions are checked when the compiler determines whether the container is valid for `@Repeatable`. They are distinct from the requirement that **at the actual repetition site**, both the base and the container must be applicable to that location.

## 2. @Target: The Containing Type Can Be Narrower, but Cannot Be Arbitrarily Broader

`@Target` determines which locations (`ElementType`) an annotation can be attached to, such as `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, or `TYPE_USE`.

The core rule is:

> The container must only support contexts that the base annotation also supports. The container can be **narrower than** the base; that restricts **where the base annotation is allowed to repeat**.

Valid example:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@Target(ElementType.TYPE)
@interface Flags {
    Flag[] value();
}
~~~

`Flag` can be used on a class or a method. `Flags` can only be used on a class. Therefore:

~~~java
@Flag("a")
@Flag("b")
class OrderService {
    @Flag("single")
    void process() {}

    // Two @Flag annotations on the same method will fail because
    // the Flags container does not apply to METHOD.
}
~~~

In this example, **using a single `@Flag` on a method is valid**. However, if you place **two `@Flag` annotations on a method**, the compiler must synthesize an implicit `@Flags` container there; since `Flags` does not have the `METHOD` target, repeating it on a method is rejected.

This is an important distinction between:

- **Can the base be applied at that location?**
- **Can the base be repeated at that location?** To repeat, **both the base and the container** must be applicable at that location.

### When the Target Declaration Makes the Container Invalid from the Start

Intentionally invalid example (not included in a runnable program):

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Repeatable(Wrappers.class)
@interface Mark {}

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Wrappers {
    Mark[] value();
}
~~~

`Mark` applies only to `TYPE`, yet `Wrappers` applies to `METHOD` as well. This is an **invalid container**, because the container is broader than the base on `METHOD`. The error does not wait until two `@Mark` annotations are written on a method; the `@Repeatable(Wrappers.class)` definition itself already violates the contract.

### Note on the TYPE, ANNOTATION_TYPE, TYPE_USE, and TYPE_PARAMETER Cases

The specification does not compare `ElementType` sets via simple string matching or naive set inclusion. `TYPE` and `TYPE_USE` can both cover **type declarations**, `TYPE` also covers annotation interface declarations; similarly, `TYPE_USE` can cover type parameter declarations.

Specifically, when the container has:

- `ANNOTATION_TYPE`: the base can have `ANNOTATION_TYPE`, `TYPE`, or `TYPE_USE`.
- `TYPE`: the base can have `TYPE` or `TYPE_USE`.
- `TYPE_PARAMETER`: the base can have `TYPE_PARAMETER` or `TYPE_USE`.

Those are the three exceptions to the requirement of having the exact same enum constant. For example, **a base with `@Target(TYPE)` and a container with `@Target(ANNOTATION_TYPE)` is valid**: repeating the base can take place on an annotation interface declaration, though not on a regular Java class.

If the base has `@Target(TYPE_USE)` and the container has `@Target(TYPE)`, compatibility can be evaluated under the rule that `TYPE_USE` covers type declarations, but **do not infer in reverse that `TYPE` allows using the annotation in every type-use context** such as a generic type argument. To use repetition in `List<@Mark String>`, the container must be compatible with that type context itself.

### What If @Target Is Not Declared?

If neither declares `@Target`, they can appear/repeat in the **declaration contexts** permitted by the language, though they do not automatically become type-use annotations.

If the base does not declare `@Target` while the container has `@Target`, repetition can only take place in the **intersection of valid locations**, which is typically narrowed by the container. If the base has a specific `@Target`, the container must be designed within the location limits of the base according to JLS rules.

In libraries, it is advisable to explicitly declare `@Target` for **both types** so that the usage scope is easy to understand and leaves fewer opportunities for misapplication.

## 3. @Retention: The Container Must Live at Least as Long as the Base

`@Retention` determines up to which stage metadata is retained:

| RetentionPolicy | Meaning |
| --- | --- |
| `SOURCE` | Only in source; this annotation is not stored in the class file |
| `CLASS` | Stored in the class file; access via runtime reflection is not guaranteed |
| `RUNTIME` | Stored in the class file and accessible via runtime reflection |

When `@Retention` is omitted, the default is **`CLASS`**.

The retention lifetime order is evaluated as `SOURCE < CLASS < RUNTIME`. The JLS requires:

**Retention(container) ≥ Retention(base).**

| Base | Container | Is the container valid with respect to retention? |
| --- | --- | --- |
| SOURCE | SOURCE | Yes |
| SOURCE | CLASS | Yes |
| SOURCE | RUNTIME | Yes |
| CLASS | SOURCE | No |
| CLASS | CLASS | Yes |
| CLASS | RUNTIME | Yes |
| RUNTIME | SOURCE | No |
| RUNTIME | CLASS | No |
| RUNTIME | RUNTIME | Yes |

Keep in mind that a “Yes” row only satisfies the **retention condition**; the other container conditions such as `value()`, `@Target`, `@Documented`, and `@Inherited` must also be satisfied.

### Invalid Example: RUNTIME Base, CLASS Container

~~~java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@interface Tag {}

@Retention(RetentionPolicy.CLASS)
@interface Tags {
    Tag[] value();
}
~~~

This is an **intentionally non-compiling** example: `Tag` wants to be retained until runtime, while `Tags` only has `CLASS` retention. When `@Tag` is repeated, the compiler needs the implicit container to represent the values; if the container were stripped from runtime metadata, the information could not be reflected consistently. Java prevents that design right at the annotation definition.

### Why Is the Same Retention Usually Chosen?

Although a `SOURCE` base and a `RUNTIME` container can satisfy the JLS rule, an asymmetric design can easily cause confusion when tools read direct versus container representations of annotations. For a new annotation API, choosing **the same `@Retention` for both the base and the container** is usually clearest.

If a framework needs to call `getAnnotationsByType(...)` at runtime, both the base and the container should have `@Retention(RUNTIME)`. Placing an annotation at a valid location does not guarantee Java reflection will see it when retention is only SOURCE or CLASS.

## 4. @Documented: If the Base Has It, the Container Must Also Have It

`@Documented` is a meta-annotation that affects the inclusion of annotations in API documentation generated by Javadoc.

The **one-way** rule of the JLS:

- **The base has `@Documented` ⇒ the container is required to have `@Documented`.**
- The container has `@Documented`, while the base does not: **still valid under the container rule**.

Properly designed example:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.Repeatable;

@Documented
@Repeatable(Policies.class)
@interface Policy {
    String value();
}

@Documented
@interface Policies {
    Policy[] value();
}
~~~

When `@Policy` is repeated, the compiler represents it using the container. Keeping `@Documented` on the container gives the documentation system the information that the container represents annotations that should be documented. If `@Documented` is missing on the container while the base has it, `@Repeatable` declares a container that is **invalid at compile time**.

Intentionally invalid example:

~~~java
@java.lang.annotation.Documented
@java.lang.annotation.Repeatable(Labels.class)
@interface Label {}

@interface Labels {
    Label[] value();
}
// ERROR: the base is @Documented, but the container is missing @Documented.
~~~

Having `@Documented` on the container **does not automatically make all annotation details appear as a separate table in every documentation generator**. Javadoc only reads/organizes metadata according to the tool's rules; final display also depends on the annotation's location and how the tool renders it.

In practice, the easiest approach to maintain is to attach `@Documented` to both or to neither, unless there is a clear API reason for them to differ.

## 5. @Inherited: If the Base Is Inherited, the Container Must Also Be Inherited

`@Inherited` applies to querying annotations of a **class** in a superclass/subclass relationship. It **does not automatically make annotations on methods, fields, or interfaces inherited in the reflection sense of `@Inherited`**.

A similar **one-way** rule applies:

- **The base has `@Inherited` ⇒ the container is required to have `@Inherited`.**
- The container has `@Inherited` while the base does not: **not prohibited by this container rule**, though the intended meaning must be carefully evaluated.

Valid example:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;

@Inherited
@Repeatable(Features.class)
@interface Feature {
    String value();
}

@Inherited
@interface Features {
    Feature[] value();
}
~~~

If the base has `@Inherited` while the container lacks `@Inherited`, the compiler reports an error right at the definition of the repeatable annotation. The reason is: when two base annotations are merged into a container, the inheritance metadata also needs a compatible path.

However, `@Inherited` does not mean that the JVM duplicates annotations from a superclass into the subclass's class file. It is a reflection lookup rule when an annotation type is marked inheritable, for example `Class.getAnnotationsByType(...)`. `getDeclaredAnnotationsByType(...)` inspects only directly declared annotations and does not walk up to the superclass.

### Important Limitations

- **Class-to-subclass** only; it does not apply that way for interface-to-implementing-class.
- Does not automatically propagate annotations from a superclass method to an overriding method in a subclass.
- A subclass that directly declares annotations of the same type can **shadow** inherited annotations when querying `getAnnotationsByType`; the result is not always an unconditional concatenation of parent and child annotations.
- `@Inherited` does not alter `@Target` and does not turn invalid locations into valid ones.
- To read annotations at runtime, an appropriate retention is still needed; `@Inherited` alone does not make a SOURCE/CLASS annotation visible in runtime reflection.

## 6. Complete Java 17 Example: All Four Meta-Annotations Consistent

Suppose an API allows attaching multiple `@Tag` labels to a class or method; we want the labels to be documented, retained until runtime, and allow subclasses to inherit class labels.

Save the file **RepeatableContainerDemo.java**:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
    String category() default "general";
}

@Tag("core")
@Tag("report")
class BaseHandler {
    @Tag("audit")
    @Tag("latency")
    void handle() {}
}

class DerivedHandler extends BaseHandler {
    @Override
    void handle() {}
}

@Tag("child")
class TaggedChild extends BaseHandler {}

public class RepeatableContainerDemo {
    static String labels(Tag[] tags) {
        return Arrays.stream(tags).map(Tag::value)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("base=" + labels(
                BaseHandler.class.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("container=" +
                (BaseHandler.class.getDeclaredAnnotation(Tags.class) != null));
        System.out.println("directSingle=" +
                (BaseHandler.class.getDeclaredAnnotation(Tag.class) != null));
        System.out.println("derivedDeclared=" +
                DerivedHandler.class.getDeclaredAnnotationsByType(Tag.class).length);
        System.out.println("derivedInherited=" + labels(
                DerivedHandler.class.getAnnotationsByType(Tag.class)));
        System.out.println("childOwn=" + labels(
                TaggedChild.class.getAnnotationsByType(Tag.class)));
        System.out.println("overriddenMethod=" +
                DerivedHandler.class.getDeclaredMethod("handle")
                        .getAnnotationsByType(Tag.class).length);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 RepeatableContainerDemo.java
java RepeatableContainerDemo
~~~

**Exact stdout (compiled and run with JDK 21 using `--release 17`):**

~~~text
base=core,report
container=true
directSingle=false
derivedDeclared=0
derivedInherited=core,report
childOwn=child
overriddenMethod=0
~~~

**Reading the output by mechanism:**

1. `@Target({TYPE, METHOD})` on **both** types allows repeating `Tag` on the `BaseHandler` class and the `handle` method. Neither type is broader than the other.
2. `@Retention(RUNTIME)` on both the base and the container makes the metadata readable via reflection. Two `@Tag` annotations placed directly at the same location are represented as a single `@Tags` container: therefore `container=true`, while `directSingle=false`.
3. `getDeclaredAnnotationsByType(Tag.class)` understands the container structure and returns the two values `core` and `report` in declaration order: `base=core,report`.
4. `DerivedHandler` does not declare `Tag` directly, so `derivedDeclared=0`; however, both types have `@Inherited`, so querying `getAnnotationsByType(Tag.class)` searches through the superclass and obtains `derivedInherited=core,report`.
5. `TaggedChild` has one direct `@Tag("child")`, so the result is `childOwn=child`, without automatically appending `core,report` from the parent.
6. The overriding method `DerivedHandler.handle()` **does not inherit `@Tag` from the parent method**. The result is `overriddenMethod=0` even though both the base and the container have `@Inherited`.
7. `@Documented` has no stdout line, because its effect relates to API documentation generation rather than a runtime function that alters labels.

Here `Tags.category()` has `default "general"`. If you remove the default while still keeping an element other than `value()`, the container becomes invalid according to JLS §9.6.3.

**Note:** `getAnnotation(Tag.class)` (without “sByType”) does not automatically unwrap all repeatable annotations inside a container. When you need to retrieve the whole group, prefer `getAnnotationsByType(Tag.class)` or `getDeclaredAnnotationsByType(Tag.class)` depending on your inheritance requirements.

## 7. Common Declaration Errors: Distinguishing Container Errors from Usage-Site Errors

The following snippets are **intentionally invalid illustrations and should not be merged into the runnable file**. Each snippet assumes distinct annotation names are defined separately to avoid name collisions.

### Error 1: Wrong Type for Container value()

~~~java
@java.lang.annotation.Repeatable(Boxes.class)
@interface Box {}

@interface Boxes {
    Object[] value(); // Error: must be Box[].
}
~~~

The very first condition is already violated. The container must return **an array of the exact base annotation type**.

### Error 2: Additional Element Without a Default

~~~java
@java.lang.annotation.Repeatable(Headers.class)
@interface Header {}

@interface Headers {
    Header[] value();
    String owner(); // Error: additional element must have a default.
}
~~~

The compiler cannot synthesize an implicit container compliant with the contract when a required value for an additional element is missing. Fix this by changing it to `String owner() default "unknown";` or removing the element.

### Error 3: Container Has a Broader Target Than the Base

~~~java
@java.lang.annotation.Target(java.lang.annotation.ElementType.METHOD)
@java.lang.annotation.Repeatable(Methods.class)
@interface MethodTag {}

@java.lang.annotation.Target({
    java.lang.annotation.ElementType.METHOD,
    java.lang.annotation.ElementType.FIELD
})
@interface Methods {
    MethodTag[] value();
}
~~~

The base applies only to METHOD, while the container adds FIELD. This is a container declaration error. Fix it by removing FIELD from the container, or widening the base if the API contract truly requires FIELD.

### Error 4: Container Is Missing Runtime Retention

~~~java
@java.lang.annotation.Retention(
    java.lang.annotation.RetentionPolicy.RUNTIME)
@java.lang.annotation.Repeatable(Options.class)
@interface Option {}

@java.lang.annotation.Retention(
    java.lang.annotation.RetentionPolicy.CLASS)
@interface Options {
    Option[] value();
}
~~~

The base is RUNTIME while the container is CLASS: **invalid**, not merely causing missing data at runtime.

### Error 5: Missing Documented or Inherited on the Container

~~~java
@java.lang.annotation.Documented
@java.lang.annotation.Inherited
@java.lang.annotation.Repeatable(Markers.class)
@interface Marker {}

@interface Markers {
    Marker[] value();
    // Error: the container does not yet have both @Documented and @Inherited.
}
~~~

Each one-way constraint applies independently: adding only one of the two is still insufficient if the base has both.

### Error 6: Valid Definitions but Repeated at an Invalid Location

~~~java
@java.lang.annotation.Target({
    java.lang.annotation.ElementType.TYPE,
    java.lang.annotation.ElementType.METHOD
})
@java.lang.annotation.Repeatable(Checks.class)
@interface Check {}

@java.lang.annotation.Target(java.lang.annotation.ElementType.TYPE)
@interface Checks {
    Check[] value();
}

class Processor {
    @Check
    void workOnce() {} // Valid: a single annotation on a method.

    // @Check @Check
    // void workTwice() {} // Error: requires the container at METHOD.
}
~~~

Here **both definitions are valid**, yet the repetition location is **invalid**. How to resolve this depends on intent: add `METHOD` to `Checks` if repetition on methods is desired, or allow only a single `@Check` at that location.

### Error 7: Mixing an Explicit Container with Repeated Base Annotations

~~~java
// INTENTIONALLY INVALID: placing multiple base annotations alongside an explicit container.
//
// @Tag("a")
// @Tag("b")
// @Tags({@Tag("c")})
// class Mixed {}
~~~

Once multiple `@Tag` annotations appear at the same location, the compiler will need an implicit container. You cannot simultaneously place an explicit `@Tags` there. This rule belongs to **JLS §9.7.5**, which is distinct from container definition validity in §9.6.3.

## 8. Verifying Implementation Goals via Reflection and Javadoc

When developing a library or framework that uses repeatable annotations, break QA down into distinct questions:

| Question | How to Verify |
| --- | --- |
| Is it defined as a valid container? | Compile the base/container definitions; check `value()`, defaults, and the four meta-annotations |
| Can it be repeated on the target class, method, or field of interest? | Compile an example with **two annotations at the exact usage site** |
| Are all repeated values retrieved at runtime? | Use `getAnnotationsByType` and `getDeclaredAnnotationsByType` |
| Does inheritance on subclasses work as expected? | Compare queries on parent/child classes, along with a case where the child has a direct annotation |
| Does Javadoc display metadata appropriately? | Generate documentation with `javadoc` for the actual API if `@Documented` is a requirement |
| Is cross-version compatibility acceptable? | Test the compiler/JDK and metadata when changing `@Target`, retention, or container type |

You should not look solely at `@Repeatable(Container.class)` and conclude that the annotation can be repeated at every location or will be inherited automatically.

### Notes When Changing a Released Annotation API

- **Narrowing the container's `@Target`** can cause previously valid repeating source code to no longer compile.
- **Changing `@Retention`** affects metadata discoverability via class files/runtime reflection; any change needs to be coordinated with consumers.
- **Removing `@Documented` or `@Inherited` from the container** while the base still keeps it can render **the annotation definition itself invalid**.
- **Renaming or changing the container type** requires checking code and tools that read previously compiled annotations; metadata in existing class files is not automatically rewritten by editing the library source.
- **Changing an additional element to lack a default** can cause the container to lose validity even if `value()` is declared properly.

For a new annotation, choosing **matching** Target, Retention, Documented, and Inherited settings for the base and container is usually the easiest configuration to understand and maintain. However, **it is not mandatory for every characteristic to be identical**: the specification intentionally allows a container to have a narrower Target and a longer retention, as well as certain one-way differences for `@Documented` and `@Inherited`. When relying on such differences, you should write actual tests at the intended usage sites.

## 9. Decision Process and Self-Check

Ask yourself in order:

1. **Does the base have `@Repeatable` pointing to the right container?** Does the container have the exact `Base[] value()` element, and do any additional elements have defaults?
2. **Does the container exceed the usage scope of the base?** Check Target according to JLS §9.6.3, including the TYPE/TYPE_USE/ANNOTATION_TYPE/TYPE_PARAMETER exceptions.
3. **Does the container retain metadata at least as long as the base?** If the base is RUNTIME, the container must also be RUNTIME.
4. **Does the base have `@Documented` or `@Inherited`?** If so, the container must have the corresponding annotation.
5. **Is the repetition site valid for both types?** A valid container definition does not yet guarantee repetition is allowed at every Target of the base.
6. **What does the consumer need to see?** Choose the right reflection API, retention, and inheritance mechanism; test both classes and methods when relevant.

Some review questions:

**(1) Base targets TYPE and METHOD; container targets only TYPE. Can this be declared? Can it be repeated twice on a method?** The declaration is **valid**; repeating it on a method is **invalid** because the container does not apply to METHOD. A single annotation on a method remains valid.

**(2) Base is RUNTIME; container has no @Retention. Is this allowed?** **No**. The container defaults to CLASS, which is shorter than the RUNTIME base.

**(3) Base does not have @Documented, container has @Documented. Is this prohibited?** No; the constraint only requires the direction where **if the base has it, the container must also have it**. The same applies to `@Inherited`.

**(4) Why can a derived class read two @Tag annotations from its parent while an overriding method does not see the two @Tag annotations on the parent method?** Because `@Inherited` only supports **class annotations** through the superclass and does not inherit annotations of overridden methods.

**(5) If a container has an additional element besides value(), what must be done?** Provide a **default value** for each additional element so that the compiler can synthesize the implicit container from the list of base annotations.

**(6) Container @Target(ANNOTATION_TYPE), base @Target(TYPE). Is the declaration valid?** **Valid**, because the base TYPE covers annotation interface declarations. However, repeating the base on a regular class will be rejected if the container only has ANNOTATION_TYPE.

## 10. Official References

- Java Language Specification, Java SE 21, **§9.6.3 Repeatable Annotation Interfaces**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.3
- **§9.6.4.1 @Target**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.1
- **§9.6.4.2 @Retention**, **§9.6.4.3 @Inherited**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html
- **§9.7.5 Multiple Annotations of the Same Interface**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.5
- JDK 21 API, **Repeatable**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Repeatable.html

When designing a repeatable annotation, check **two levels of validity**: the container **is validly declared** according to the six conditions of JLS §9.6.3; and **repetition at the exact usage site** is valid under §9.7.5. The constraints on `@Target`, `@Retention`, `@Documented`, and `@Inherited` ensure that the containing type can represent the base annotations consistently across compilation, documentation, and reflection.
