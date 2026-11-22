# Distinguishing Java Core Meta-Annotations from Framework Composed Annotations

A **meta-annotation** is an annotation placed **on the declaration of another annotation type**. Java Core already includes several standard meta-annotations such as `@Target`, `@Retention`, `@Documented`, `@Inherited`, and `@Repeatable` to govern certain **language, compiler, and Reflection rules**. Meanwhile, a **composed annotation** from a framework, such as Spring, uses that same meta-annotation syntax to **combine business and configuration semantics**, while relying on **metadata discovery/merging algorithms provided by the framework**.

**Key point:** Java syntax allows an annotation to be placed on another annotation, but **standard Java Reflection does not automatically infer that every meta-annotation becomes a direct annotation on a class carrying a composed annotation**. A framework that wants to support such behavior must provide its own lookup logic, attribute merging, and rule handling.

This lesson belongs to the topic of **annotation design in Java Core**. We will start with Java's contract, test it with a Java 17 program without external libraries, and then compare it with the Spring case to see a clear **boundary of responsibility**.

## 1. “Meta-annotation” is a syntactic position, not a single feature

Java uses the `@` symbol for both regular annotations and meta-annotations. The difference depends on **what the annotation is attached to**:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {
}

@Audited
class InvoiceService {
}
```

In this snippet:

- `@Retention` and `@Target` are placed on `@interface Audited`: they are **meta-annotations**, describing the rules for using `Audited`.
- `@Audited` is placed on `class InvoiceService`: this is an **application of an annotation to a class**.
- Both forms conform to the annotation syntax of the Java language.

Not every annotation placed on another annotation belongs to Java's standard set of meta-annotations. A business annotation declared with `@Target(ANNOTATION_TYPE)` can also be used as a **custom meta-annotation**; that **does not automatically give it meaning for Reflection on a class at a lower level**.

For example, `@RequiredRole("ADMIN")` can be placed on `@AdminOnly`. Java knows the structure:

```text
Declaration of @interface AdminOnly
    └─ annotated with @RequiredRole("ADMIN")

Declaration of class ReportPage
    └─ annotated with @AdminOnly
```

However, direct Reflection on `ReportPage` **is not required** to automatically “traverse through” `@AdminOnly` and return `@RequiredRole`. To use that relationship, application or framework code must **access the `AdminOnly` annotation type and analyze it further**.

## 2. Five representative meta-annotations defined by Java Core

The standard annotations below belong to `java.lang.annotation` and have meanings defined by Java.

| Meta-annotation | Core meaning in Java | What it does **not** do |
| --- | --- | --- |
| `@Target` | Specifies the **syntactic locations** where the annotation type is allowed to be used. | Does not enable a framework to automatically process annotations placed at those locations. |
| `@Retention` | Specifies whether the annotation is retained to the **SOURCE**, **CLASS**, or **RUNTIME** level. | Does not automatically merge annotations from multiple layers. |
| `@Documented` | Marks the annotation as part of the public API so that standard documentation tools such as Javadoc display it when appropriate. | Does not cause every other nested/meta-annotation to automatically appear as a direct annotation. |
| `@Inherited` | Allows an annotation type to be found via Reflection along a class's **superclass chain**, in specified cases. | Does not search implemented interfaces; does not create a general-purpose composed-annotation mechanism. |
| `@Repeatable` | Allows multiple uses of **the same annotation type** at the same location through a valid **container**. | Does not mean that annotations of **different types** will be composed or have their attributes merged. |

Example syntax:

```java
import java.lang.annotation.*;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface FeatureFlag {
    String value() default "on";
}
```

With the `FeatureFlag` type:

- The compiler checks usage on **types** because of `@Target(TYPE)`.
- Runtime Reflection can read it because of `@Retention(RUNTIME)`.
- Javadoc can display the annotation according to the `@Documented` rule.
- `@Inherited` only affects certain queries on a **subclass** when the annotation is placed on a **superclass**.
- Nothing here causes `@FeatureFlag` to become an automatic feature-enabling rule in the application. **Business logic must read and interpret** `FeatureFlag`.

**`@Target(ANNOTATION_TYPE)`** is how you declare an annotation dedicated specifically to **marking annotation type declarations**. When you want an annotation to be used both directly on a class and to mark another annotation, you can use `@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})` to allow both purposes.

### Three levels of `@Retention`

```java
@Retention(RetentionPolicy.SOURCE)   // Used in source, not retained in the class file
@Retention(RetentionPolicy.CLASS)    // Retained in the class file, not visible to normal Reflection
@Retention(RetentionPolicy.RUNTIME)  // Retained so runtime Reflection can read it
```

The three lines **illustrate the available syntax options**; do not place all three on the same annotation type.

If **`@Retention` is not declared**, the default is `RetentionPolicy.CLASS`. When a framework uses Reflection to look for runtime annotations, an annotation with `CLASS` retention will usually **not be found**, even though the meta-annotation syntax and logical configuration look correct.

## 3. Java Core meta-annotations have special semantics because the language defines them

Why does Java know how to process `@Retention` or `@Target`, yet not automatically understand `@RequiredRole`? Because the Java Language Specification and the Java SE APIs have **predefined the meanings** of the standard annotations. The compiler and Reflection simply have to adhere to those contracts.

For example:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@interface OnlyOnMethod {
}

// @OnlyOnMethod class WrongPlace {} // Compile error: target is METHOD, not TYPE
```

This target-location check is the responsibility **of the Java compiler**, without needing a framework to scan the code.

Similarly:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Marker {
}

@Marker
class Parent {
}

class Child extends Parent {
}
```

With `Child.class.getAnnotation(Marker.class)`, Java Reflection can find `Marker` according to the **annotation inheritance rules on classes**. This is completely different from “finding an arbitrary annotation placed on another annotation type”.

**Limitations of `@Inherited` to remember:**

1. It queries a **class** and walks through **superclasses**; it does not automatically look up metadata on implemented interfaces.
2. It does not make methods/fields/parameters automatically inherit annotations in a general sense.
3. `Class.getDeclaredAnnotation(Marker.class)` only searches for **directly declared** annotations, so a subclass that does not declare `@Marker` can return `null` with this API.
4. Having `@Inherited` attached to `Marker` does not cause every **meta-annotation placed on `Marker`** to automatically propagate down to subclasses.

Frameworks may have richer lookup rules across class hierarchies and interfaces; they should not be confused with Java's `@Inherited` contract.

## 4. How do framework composed annotations differ?

A **composed annotation** is a way of using **a custom annotation** to represent **a set of metadata or multiple other annotations**, relying on **a specific framework's processor**.

In the Spring ecosystem, a familiar example is:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.lang.annotation.*;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Service
@Transactional
public @interface TransactionalService {
}
```

This is a **Spring-dependent example snippet**, not JDK-only code; it requires the corresponding Spring dependencies and a properly named annotation file to compile.

A class using it:

```java
@TransactionalService
class PaymentService {
}
```

Spring has an annotation-processing mechanism **across multiple meta-annotation layers** to recognize the `@Service` stereotype and `@Transactional` transaction metadata when the corresponding mechanisms are configured. Thanks to this, code authors reduce repeating multiple annotations across classes.

However, **plain Java Core** does not automatically guarantee the following behaviors:

- `Class.getAnnotation(Service.class)` on `PaymentService` will not automatically find `@Service` indirectly through `@TransactionalService`.
- `Class.getAnnotation(Transactional.class)` on `PaymentService` will also not automatically retrieve `@Transactional` through standard Java Reflection alone.
- Simply writing `@TransactionalService` **does not automatically enable transaction management** if the application does not yet have the necessary Spring components/configuration.
- Spring processes stereotypes, transactions, and attribute aliases based on **its own rules**, not because Java has a composed-annotation operator understood by the compiler.

At the language level, `@TransactionalService` is an annotation type with **ordinary meta-annotations**; “composition” is **the semantics of the processing layer**.

## 5. Complete Java 17 example: What does Java Reflection see and not see?

This example uses **only Java SE 17**. It checks three things:

1. A class directly annotated with an annotation will be read by Reflection as a direct annotation.
2. An annotation **placed on another annotation type** does not automatically appear as an annotation of a class using that intermediate type.
3. `@Inherited` has a different effect: it searches superclasses in the cases specified by Java, but does not search interfaces.

Create the file **`CoreMetaVsComposedDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@interface RequiredRole {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@RequiredRole("ADMIN")
@interface AdminOnly {
}

@AdminOnly
class AdminPage {
}

@RequiredRole("ADMIN")
class DirectPage {
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tracked {
}

@Tracked
class BaseReport {
}

class MonthlyReport extends BaseReport {
}

@Tracked
interface TaggedInterface {
}

class InterfaceImplementation implements TaggedInterface {
}

public class CoreMetaVsComposedDemo {
    public static void main(String[] args) {
        System.out.println("direct=" +
                DirectPage.class.isAnnotationPresent(RequiredRole.class));

        System.out.println("metaIsNotDirect=" +
                (AdminPage.class.getAnnotation(RequiredRole.class) == null));

        System.out.println("composedPresent=" +
                AdminPage.class.isAnnotationPresent(AdminOnly.class));

        RequiredRole meta = AdminOnly.class.getAnnotation(RequiredRole.class);
        System.out.println("metaOnAnnotationType=" + meta.value());

        AdminOnly present = AdminPage.class.getAnnotation(AdminOnly.class);
        RequiredRole manual = present.annotationType()
                .getAnnotation(RequiredRole.class);
        System.out.println("manualTraverse=" + manual.value());

        System.out.println("inheritedFromSuperclass=" +
                MonthlyReport.class.isAnnotationPresent(Tracked.class));

        System.out.println("notDeclaredOnSubclass=" +
                (MonthlyReport.class.getDeclaredAnnotation(Tracked.class) == null));

        System.out.println("notInheritedFromInterface=" +
                !InterfaceImplementation.class.isAnnotationPresent(Tracked.class));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CoreMetaVsComposedDemo.java
java CoreMetaVsComposedDemo
```

**Stdout:**

```text
direct=true
metaIsNotDirect=true
composedPresent=true
metaOnAnnotationType=ADMIN
manualTraverse=ADMIN
inheritedFromSuperclass=true
notDeclaredOnSubclass=true
notInheritedFromInterface=true
```

### Result analysis

- **`direct=true`**: `DirectPage` has `@RequiredRole("ADMIN")` itself on the class declaration.
- **`metaIsNotDirect=true`**: `AdminPage` only has `@AdminOnly`. Java Reflection querying `RequiredRole` **on `AdminPage`** does not automatically traverse through `AdminOnly` to retrieve `RequiredRole`.
- **`composedPresent=true`**: `AdminOnly` is indeed attached directly to `AdminPage`.
- **`metaOnAnnotationType=ADMIN`**: `RequiredRole` **is present on the `@interface AdminOnly` declaration**, so accessing `AdminOnly.class.getAnnotation(RequiredRole.class)` reads it.
- **`manualTraverse=ADMIN`**: the code retrieves `@AdminOnly` from `AdminPage`, queries `annotationType()`, and then reads the meta-annotation on that **annotation type**. This is a **manual traversal** step, not Java having merged annotations onto `AdminPage`.
- **`inheritedFromSuperclass=true`**: with `@Tracked` annotated with `@Inherited`, querying on `MonthlyReport` can retrieve the annotation from `BaseReport`.
- **`notDeclaredOnSubclass=true`**: the subclass does not directly declare `@Tracked`; `getDeclaredAnnotation` still returns `null`.
- **`notInheritedFromInterface=true`**: Java does not retrieve `@Tracked` on the `TaggedInterface` interface for the `InterfaceImplementation` class via `@Inherited`.

**Note:** the manual traversal approach in the example handles only **one level** of meta-annotations. If annotations are composed across multiple levels, contain reference cycles, have multiple annotations of the same type, have attributes needing overrides, or involve complex class hierarchies, a dedicated algorithm must be designed. That is precisely why frameworks provide annotation-processing libraries instead of requiring every application to perform deep traversal on its own.

## 6. Java Reflection does not mean “meta-annotations cannot be read”

A statement such as “Java does not support custom meta-annotations” is **false**. Java allows placing annotations on an annotation type if the target is valid, retaining them according to retention, and reading the metadata of the annotation type itself at runtime.

The distinction to make is **which location the API looks from and whether it traverses multiple levels automatically**:

```java
AdminPage.class.getAnnotation(RequiredRole.class);  // null
AdminPage.class.getAnnotation(AdminOnly.class);      // has the AdminOnly annotation
AdminOnly.class.getAnnotation(RequiredRole.class);   // has the RequiredRole annotation
```

All three calls above are standard Java Reflection and all work strictly according to contract. What Java **does not do by default** is turn the first line into a result based on the path `AdminPage → AdminOnly → RequiredRole`.

A library can build its own algorithm: retrieve direct annotations, read `annotationType()`, traverse meta-annotations level by level, and return the discovered metadata. However, it must decide at least:

- **How many levels** should be traversed, and how should **cycles** be handled?
- If two branches contain the same annotation type with different values, **which branch takes precedence**?
- Should annotations on superclasses, interfaces, or overridden methods be allowed to participate in the search?
- Should `@Repeatable` and containers be supported?
- Should default values, same-named attributes, and **aliases** be merged?
- Which retention does the source/target metadata use, and is it available at runtime?

**Java SE does not define a general answer** to these composition questions. Spring and other frameworks have their own strategies.

## 7. `@Target` and `@Retention` must be designed for each level

Suppose you want to declare `@AdminOnly` to place on a class, with an inner marker carrying the meaning `@RequiredRole`.

The minimal valid configuration for reading with runtime Reflection:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@interface RequiredRole {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@RequiredRole("ADMIN")
@interface AdminOnly {
}
```

**The two annotations have their own metadata**; they do not copy it automatically:

- `RequiredRole` needs `@Target(ANNOTATION_TYPE)` (optionally combined with other targets) to be applicable on the `@interface AdminOnly` declaration.
- `AdminOnly` needs `@Target(TYPE)` so users can place it on a class.
- If Reflection is needed at runtime, `RequiredRole` needs `RUNTIME` retention to be read from `AdminOnly.class`.
- `AdminOnly` also needs `RUNTIME` retention to be read from `AdminPage.class`.
- Attaching `@Retention(RUNTIME)` to `RequiredRole` **does not automatically** give `AdminOnly` runtime retention; each annotation type follows its own `@Retention`.

A common mistake is putting `@Retention(RUNTIME)` only on the **inner** annotation, while leaving the outer composed annotation undeclared so it defaults to `CLASS`. In that case, reading `@AdminOnly` from the class via Reflection cannot work as in the example.

Similarly, putting `@Target(ANNOTATION_TYPE)` only on the inner marker does not automatically make `@AdminOnly` usable on methods/fields; the target of `AdminOnly` must match where it is actually used.

## 8. Do not confuse `@Inherited` with a framework's composition mechanism

`@Inherited` is **a standard Java meta-annotation**, but its semantics are very **narrow**. Placing `@Inherited` on `@RequiredRole` does not mean Java will automatically turn every class using `@AdminOnly` into a class directly bearing `@RequiredRole`.

Example illustrating the distinction:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}

@Region("east")
class BaseController {
}

class ChildController extends BaseController {
}
```

This is a standalone **illustrative snippet**. `ChildController.class.getAnnotation(Region.class)` can find the annotation from `BaseController`, whereas `getDeclaredAnnotation(Region.class)` on `ChildController` returns `null`. However, if `@Region` is only a meta-annotation on `@SpecialController` and the subclass is annotated with `@SpecialController`, Java does not automatically “unpack” `Region` from the intermediate annotation via `@Inherited`.

Another common point of confusion: interfaces are not part of the standard `@Inherited` lookup path. Some frameworks allow looking up annotations on **interfaces** or on methods via interfaces/overrides; that is a **framework rule**, and must not be inferred from `@Inherited`.

## 9. `@Repeatable` is not a framework-style composed annotation either

`@Repeatable` is a language mechanism for **applying the same annotation type multiple times** at the same location. Java requires a container annotation with a `value()` element whose type is an array of that annotation:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@interface Tags {
    Tag[] value();
}

@Tag("audit")
@Tag("monitor")
class LogService {
}
```

This is a standalone illustrative example without `main`. `@Repeatable` allows two `@Tag` annotations on one class. The compiler applies **container rules** according to Java; Reflection provides APIs such as `getAnnotationsByType(Tag.class)` to read repeatable annotations.

It differs from a composed annotation in that:

- `@Repeatable(Tags.class)` associates **one annotation type with a container of that same element type**.
- `@AdminOnly` composing `@RequiredRole`, `@Service`, or `@Transactional` involves combining **different annotation types**, along with application semantics interpreted by a library/framework.
- Java's `getAnnotationsByType(...)` has a rule to look through a **repeatable container**, but **that does not turn it into a lookup engine for arbitrary custom meta-annotations**.

If using repeatable annotations at runtime, remember to design `@Retention(RUNTIME)` for both the repeatable annotation and the container if Reflection is needed; the declaration pair must satisfy the retention/target compatibility rules in the Java Language Specification.

## 10. How does Spring handle composed annotations?

In Spring, certain annotations carry **stereotype** or **configuration** semantics:

- `@Component` identifies a type as a candidate for Spring component scanning; `@Service` and `@Repository` are meta-annotated with `@Component`.
- `@RestController` combines the semantics of `@Controller` and `@ResponseBody` in Spring Web.
- `@GetMapping` by design is a specialization of `@RequestMapping` for the HTTP GET method and has an alias mechanism for multiple attributes such as `path`/`value`.
- A custom annotation such as `@TransactionalService` can place `@Service` and `@Transactional` as meta-annotations for the framework to interpret.

Spring has dedicated metadata-processing APIs, such as `org.springframework.core.annotation.AnnotatedElementUtils` and `org.springframework.core.annotation.MergedAnnotations`.

A **Spring-dependent** example, separate from the standalone Java 17 program in Section 5:

```java
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.stereotype.Service;

Service service = AnnotatedElementUtils.findMergedAnnotation(
        PaymentService.class,
        Service.class
);
```

This is a **snippet**: to compile it, you need Spring dependencies, a properly annotated `PaymentService`, and the code placed inside a class/method. Spring can find `@Service` from a matching meta-annotation structure **according to Spring's algorithm**, whereas `PaymentService.class.getAnnotation(Service.class)` is standard Reflection and does not automatically search through composed annotations.

Do not assume that **every** framework searches and merges like Spring, or that every API within Spring uses the same strategy. Options such as direct, inherited, meta-present, type hierarchy, method hierarchy, repeatable, and attribute resolution also depend on the API and framework version.

### Merged attributes and aliases

In Java Core, two element methods on two annotations **are not automatically related** just because they share the same name. For example, `@A(name="x")` and `@B(name="x")` are two separate values.

Spring additionally defines the `@AliasFor` annotation and **alias/override** rules when processing merged annotations. A **Spring-specific** example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface NamedComponent {
    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}
```

The snippet above must reside in the file **`NamedComponent.java`** and requires Spring on the compile classpath; it is not plain Java syntax usable without adding the library. When an appropriate Spring component processes `@NamedComponent("billing")`, the alias rule can map the value to the `Component.value` attribute in Spring's merged annotation model.

**`@AliasFor` is not a standard Java meta-annotation.** `javac` simply sees a validly declared annotation; Spring itself defines how alias relationships and their corresponding constraints are interpreted. You cannot create an `@AliasFor` and expect Java Core's `Class.getAnnotation(Component.class)` to automatically return the merged metadata.

## 11. Comprehensive comparison table

| Aspect | Java Core meta-annotation | Framework composed annotation |
| --- | --- | --- |
| Who defines the semantics? | The Java Language Specification and Java SE APIs for standard meta-annotations. | The framework or annotation-processing library. |
| Syntax? | `@Retention`, `@Target`, etc., on `@interface`. | Also Java annotation syntax placed on `@interface`. |
| Common goals | Valid locations, retention, documentation, class-level inheritance, container-based repetition. | Grouping stereotypes, configuration, policies, routes, or behaviors of multiple annotations. |
| Requires dependencies outside the JDK? | No, for `java.lang.annotation`. | Yes, if using Spring/Jakarta/a specific library. |
| Does the compiler understand the semantics natively? | For standard rules like `@Target`, `@Repeatable`: yes. | The compiler typically checks only syntax/types; composition behavior belongs to the framework. |
| Can standard Reflection find meta-annotations on an annotation type? | Yes, if retention allows. | Can read structural information, but does not merge onto the annotated class by default. |
| Automatically searches across multiple levels of custom annotations? | No general mechanism in `Class.getAnnotation(...)`. | May do so, depending on the framework's API/algorithm. |
| Attribute merging/overriding and aliases? | No aliasing principle across annotations of different types. | May exist, such as Spring's `@AliasFor`/`MergedAnnotations`. |
| Inheritance impact? | `@Inherited` has narrow rules only along a class's superclass chain. | May add lookup across hierarchies/interfaces/methods depending on the API. |
| Processing time? | Compiler, Javadoc, annotation processing, and Reflection per annotation type. | Frameworks usually read metadata at bootstrap/runtime; some libraries also process at build time. |

The two columns **are not mutually exclusive opposites**. Frameworks still rely on valid Java Core annotations, and a pure Java Core project can still **write its own resolver** to traverse meta-annotations. What distinguishes them is **the origin of the automatic semantics**: standard Java or logic added by a framework/library.

## 12. Designing annotations to avoid implicit framework dependencies

When designing an annotation, identify **who the metadata consumer is** first:

### Case A: the annotation is processed by the Java compiler or an annotation processor

For example, a build-time-only marker read by a generator:

```java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateMapper {
}
```

The processor can traverse `RoundEnvironment`, `Element`, and `AnnotationMirror` to read `@GenerateMapper`; `RUNTIME` retention is not strictly required.

If you design meta-annotations on custom annotations for a processor to recognize, the processor **must traverse on its own** from the annotation in use to the meta-annotated annotation type. `@SupportedAnnotationTypes(...)` does not mean every meta-present annotation will be automatically decomposed by the compiler into direct applications on classes. The processor's scanning mechanism needs to be designed accordingly.

### Case B: a Java Core library reads annotations at runtime on its own

Requirements:

1. The annotation on the class is declared with `@Retention(RUNTIME)`.
2. The meta-annotation to be read also has `RUNTIME` retention.
3. Code queries the right annotation type, traverses the levels itself, and guards against cycles if needed.
4. Define precedence rules if there are multiple markers or conflicting attributes.
5. Do not confuse **accessing a meta-annotation on an annotation type** with **a direct annotation on a class**.

If only a simple piece of information is needed, using `@RequiredRole` directly on the class is sometimes clearer than creating a composed annotation and writing an entire new resolver.

### Case C: a framework supports composed annotations

Requirements:

1. Choose a mechanism **documented by the framework**; do not assume `Class.getAnnotation` has merging capabilities.
2. Check `@Target`, `@Retention`, element types, and default values of every annotation in the chain.
3. Check how the framework detects stereotypes, searches meta-annotations, handles inheritance, and applies attribute alias rules.
4. If the framework has multiple versions, write integration tests across the versions that need to be supported.
5. Do not claim that merely adding an annotation will activate behavior before enabling component scanning, transaction processing, web mapping, or the corresponding configuration.

**Good design keeps the boundary clear:** Java defines valid metadata; the processor/framework decides how to interpret that metadata.

## 13. Common mistakes to avoid

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking that if `@MyAnnotation` has the `@Policy` meta-annotation, `MyClass.class.getAnnotation(Policy.class)` automatically returns `Policy`. | Standard Java Reflection does not automatically flatten custom meta-annotations. | Read `MyAnnotation.class` or use a framework resolver. |
| Assuming every annotation used on another annotation is a standard Java annotation. | Business annotations can also be meta-annotations in the syntactic sense. | Distinguish between **standard** and **custom** meta-annotations. |
| Using `@Retention(RUNTIME)` only on the inner-layer marker. | The outer-layer annotation has its own retention, which may default to `CLASS`. | Configure retention for every type that requires Reflection. |
| Using only `@Target(ANNOTATION_TYPE)` on the outer annotation while trying to attach it to a class. | The outer annotation's target does not allow classes. | Set targets matching where it is actually used. |
| Treating `@Inherited` as a mechanism for finding annotations from interfaces and all meta-levels. | Java only has narrow inheritance rules through superclasses. | Use an appropriate lookup API if the framework requires interfaces/hierarchies. |
| Confusing `@Repeatable` with composing multiple different annotation types. | `@Repeatable` is a container for **the same annotation type**. | Use composition/a processor when you want to combine multiple kinds of metadata. |
| Expecting the `@Service` meta-annotation to be automatically turned into `@Component` on a class by `javac`. | The Java compiler does not perform Spring's composition. | Let the Spring component scanner/metadata resolver handle it. |
| Using `@AliasFor` while only calling Java Core's `Class.getAnnotation`. | Aliasing is Spring semantics. | Use the merged annotation API provided by the framework. |
| Guessing that two attributes with the same name automatically override each other in every framework. | Attribute mapping has specific rules and version behavior. | Explicitly declare aliases if needed, and check the framework's documentation/tests. |
| Using a `@Transactional` meta-annotation without configuring transaction management. | Metadata does not automatically turn into runtime transactions. | Check configuration, proxy/interception mechanisms, and framework conditions. |
| Seeing Reflection return `null` and concluding that the meta-annotation is absent from bytecode. | You might be querying the wrong `AnnotatedElement` or using the wrong retention. | Check the annotation on the annotation type itself and verify runtime retention. |
| Writing a recursive resolver without cycle prevention or precedence decisions. | Meta-annotation chains can nest deeply or overlap across multiple branches. | Track visited elements, define precedence, and write tests for conflicts. |

## 14. Knowledge self-check

Based on the `CoreMetaVsComposedDemo.java` program in Section 5:

1. **Why is `AdminPage.class.getAnnotation(RequiredRole.class)` `null`?** Because `RequiredRole` is placed on the `AdminOnly` declaration, not directly on `AdminPage`, and standard Java Reflection does not automatically merge custom meta-annotations.
2. **How can you read the value `"ADMIN"` using only the JDK?** Call `AdminOnly.class.getAnnotation(RequiredRole.class).value()` or retrieve `AdminOnly` from the class and query `annotationType()`.
3. **If you remove `@Retention(RUNTIME)` from `AdminOnly`, what happens?** It defaults to `CLASS`; the program can no longer retrieve `AdminOnly` on `AdminPage` using normal runtime Reflection.
4. **What if you remove `@Retention(RUNTIME)` from `RequiredRole`?** Reading `RequiredRole` from `AdminOnly.class` will no longer see that annotation via runtime Reflection.
5. **Does `@Inherited` cause a class implementing an interface annotated with `@Tracked` to have `@Tracked`?** No; this is not a Java Core rule.
6. **Is `@Documented` a Spring composed annotation?** No; it is a standard Java meta-annotation for documentation.
7. **Does `@Repeatable` allow aliasing from `@AdminOnly.value()` to `@RequiredRole.value()`?** No; it addresses using the same annotation type multiple times.
8. **What does Spring do that Java's `Class.getAnnotation` does not do automatically?** It can search across multiple meta-annotation levels and merge attributes/aliases according to Spring's annotation model.
9. **Why does `@TransactionalService` not guarantee that transactions work when you only have Java source?** Because Spring and the transaction-processing mechanisms must be properly configured/applied.
10. **When should you use a direct annotation instead of a composed annotation?** When only a single simple meaning is needed, there is no need to group configuration, or no resolver/framework supports it.
11. **How do you verify that a composed annotation actually works?** Write an integration test with the framework's proper API and configuration, not just verifying that the Java source compiles.
12. **Conclusion:** Java Core defines **the syntax and certain standard meta-annotation semantics**; frameworks can build **higher-level composition semantics** on top of that same metadata, but those behaviors do not automatically become rules of `javac` or Java Reflection.

## 15. Authoritative reference documentation

- [Java SE 17 – `java.lang.annotation.Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html): where an annotation can be used, especially `ANNOTATION_TYPE`.
- [Java SE 17 – `java.lang.annotation.Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): the SOURCE/CLASS/RUNTIME lifecycle.
- [Java SE 17 – `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): superclass-based inheritance limits.
- [Java SE 17 – `java.lang.annotation.Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): repeatable annotations via a container.
- [Java SE 17 – `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): distinguishing directly present, indirectly present, and present, along with annotation retrieval methods.
- [Spring Framework – Annotation Programming Model](https://github.com/spring-projects/spring-framework/wiki/Spring-Annotation-Programming-Model): meta-annotations, composed annotations, stereotypes, attribute aliases, and overrides.
- [Spring Framework – `MergedAnnotations` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/MergedAnnotations.html): the framework's annotation lookup and merging capabilities.

Remember: **“meta-annotation” describes where an annotation is placed; “composed annotation” describes how a combination of annotations is used and processed.** Java provides the foundation, while automatic behaviors beyond Java's contract must come from a specific processor or framework.
