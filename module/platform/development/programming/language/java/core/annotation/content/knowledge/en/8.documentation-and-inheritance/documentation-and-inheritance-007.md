# Custom Meta-Annotations and Limitations of Transitive Processing in Java Core

A **meta-annotation** is an annotation applied to the **declaration of another annotation**. It allows describing that annotation: specifying where it can be used with `@Target`, when metadata is retained with `@Retention`, or adding a custom convention for the application. From there, developers can create a *composed annotation* such as `@GetReports` pre-annotated with `@Route(method = "GET", path = "/reports")`.

The most important point: **Java Core has no general rule that automatically converts a meta-annotation into an annotation on the class, method, or field using the composed annotation**. Standard reflection only returns annotations according to the exact semantics of `AnnotatedElement`; if you want to infer indirectly from `@GetReports` to `@Route`, the tool or framework author must implement that lookup logic.

General example:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Route {
    String method();
    String path();
}

@Route(method = "GET", path = "/reports")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface GetReports {}

@GetReports
class ReportController {}
```

- `ReportController` is **directly** annotated with `@GetReports`.
- The **annotation type** `GetReports` is **directly** annotated with `@Route`.
- `ReportController.class.getAnnotation(Route.class)` returns `null`. `@Route` does not automatically "flow" down to `ReportController`.
- `GetReports.class.getAnnotation(Route.class)` returns a `Route` because that is where `@Route` is actually applied.

The distinction between **annotations on an element**, **meta-annotations on an annotation type**, **`@Inherited` inheritance**, and **framework-implemented discovery/composition mechanisms** is the focus of this lesson.

## 1. What Is a Custom Meta-Annotation?

Java has standard meta-annotations:

| Meta-annotation | Primary Purpose |
|---|---|
| `@Target` | Restricts where the annotation can be applied |
| `@Retention` | Specifies whether the annotation is retained until SOURCE, CLASS, or RUNTIME |
| `@Documented` | Instructs the Javadoc tool to record the annotation in the documentation of the annotated element |
| `@Inherited` | Allows annotation inheritance along the superclass in situations defined by Java |
| `@Repeatable` | Declares that an annotation can appear multiple times on the same element, using a container annotation |

We can also define our own annotation to use as a meta-annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface FeatureGroup {
    String value();
}

@FeatureGroup("operations")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface BatchJob {}

@BatchJob
class NightlyJob {}
```

`FeatureGroup` describes the **annotation type** `BatchJob`, while `BatchJob` describes the **class** `NightlyJob`.

This can be visualized as:

```text
NightlyJob.class
    |
    | directly has
    v
@BatchJob
    |
    | BatchJob.class directly has
    v
@FeatureGroup("operations")
```

This is a two-level relationship in metadata. In Java Core, there is no rule that turns that diagram into a direct `@FeatureGroup` relationship on `NightlyJob`. When designing a framework, treating `@BatchJob` as synonymous with a type of feature group is a **custom convention**, which the framework needs to implement in code.

## 2. Distinguishing Three Easily Confused Concepts

**Direct annotation:** the annotation actually applied to the element under consideration.

```java
@BatchJob
class NightlyJob {}
```

`NightlyJob.class.getDeclaredAnnotation(BatchJob.class)` finds `BatchJob`, whereas `NightlyJob.class.getDeclaredAnnotation(FeatureGroup.class)` returns `null`.

**Meta-annotation:** an annotation applied to the declaration of an annotation type:

```java
@FeatureGroup("operations")
@interface BatchJob {}
```

`BatchJob.class.getDeclaredAnnotation(FeatureGroup.class)` can read `FeatureGroup` if this annotation has RUNTIME retention.

**Transitive/composed lookup:** a custom-written algorithm or a framework actively traversing from the annotation on an element to its annotation type, and then continuing to look up meta-annotations. This is **not** the default behavior of `Class.getAnnotation(...)`.

When using the terms "has an annotation", "inherits", or "transitive", it is necessary to state clearly **which target is being queried and which API/algorithm is performing the query**. For example: "`NightlyJob` directly has `BatchJob`" is different from "`BatchJob` is meta-annotated with `FeatureGroup`".

## 3. Defining a Custom Meta-Annotation Properly

Common pattern:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Category {
    String value();
}
```

Here:

- `@Target(ElementType.ANNOTATION_TYPE)` restricts where `@Category` can be placed to annotation type declarations, such as `@interface QueryHandler`.
- `@Retention(RetentionPolicy.RUNTIME)` allows a tool using reflection to read `@Category` on `QueryHandler.class` at runtime.
- `String value()` holds the data of the meta-annotation, such as `"read-only"`.

Usage example:

```java
@Category("read-only")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface QueryHandler {}

class QueryService {
    @QueryHandler
    String getStatus() {
        return "ready";
    }
}
```

If reading metadata via Java reflection:

```java
// Illustration inside a method that can throw NoSuchMethodException:
var method = QueryService.class.getDeclaredMethod("getStatus");

QueryHandler direct = method.getAnnotation(QueryHandler.class);
Category meta = QueryHandler.class.getAnnotation(Category.class);

System.out.println(direct != null); // true
System.out.println(meta.value());    // read-only
System.out.println(method.getAnnotation(Category.class) == null); // true
```

This short snippet illustrates this in a context where the types have already been defined. It is not a standalone runnable Java program; a complete example is in a later section.

### What `@Retention` and `@Target` Do Not Automatically Propagate Through a Wrapper

**The retention of a meta-annotation does not automatically determine the retention of the composed annotation.** Consider:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface MetaFlag {}

@MetaFlag
@Target(ElementType.TYPE)
@interface Flagged {}
```

`MetaFlag` has RUNTIME, while `Flagged` **does not automatically have RUNTIME**: if `@Retention` is not declared, `Flagged` defaults to **CLASS**. Therefore, `Flagged.class.getAnnotation(MetaFlag.class)` can see `MetaFlag`, whereas a class annotated with `@Flagged` cannot necessarily be queried for `Flagged` via runtime reflection. To scan at runtime, RUNTIME retention must be declared on `Flagged`.

**The target of a meta-annotation does not automatically become the target of the composed annotation.** `@Target(ANNOTATION_TYPE)` on `MetaFlag` only restricts `MetaFlag`; if you want `Flagged` to be used only on classes, you need to place `@Target(TYPE)` directly on the `Flagged` definition.

Similarly, `@Documented` on a meta-annotation does not automatically cause a composed annotation to be included in Javadoc at its usage sites; an annotation that should be recorded by Javadoc must follow the rules of `@Documented` itself.

## 4. Complete Java 17+ Example: Composed Annotations and @Inherited

Create a single file named **`MetaAnnotationDemo.java`**:

```java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Route {
    String method();
    String path();
}

@Route(method = "GET", path = "/reports")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface GetReports {}

@GetReports
class ReportController {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {}

@Audited
class BaseService {}

class ChildService extends BaseService {}

@Audited
interface AuditedContract {}

class ContractService implements AuditedContract {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Traced {}

class BaseAction {
    @Traced
    public void act() {}
}

class ChildAction extends BaseAction {
    @Override
    public void act() {}
}

public class MetaAnnotationDemo {
    static Route findOneLevelRoute(Class<?> type) {
        for (Annotation direct : type.getDeclaredAnnotations()) {
            Route route = direct.annotationType().getAnnotation(Route.class);
            if (route != null) {
                return route;
            }
        }
        return null;
    }

    public static void main(String[] args) throws NoSuchMethodException {
        System.out.println("direct Route: "
                + ReportController.class.isAnnotationPresent(Route.class));
        System.out.println("direct GetReports: "
                + ReportController.class.isAnnotationPresent(GetReports.class));

        Route onAnnotationType = GetReports.class.getAnnotation(Route.class);
        System.out.println("meta Route: " + onAnnotationType.method()
                + " " + onAnnotationType.path());

        Route resolved = findOneLevelRoute(ReportController.class);
        System.out.println("resolved Route: " + resolved.method()
                + " " + resolved.path());

        System.out.println("child inherits Audited: "
                + ChildService.class.isAnnotationPresent(Audited.class));
        System.out.println("child declares Audited: "
                + (ChildService.class.getDeclaredAnnotation(Audited.class)
                        != null));
        System.out.println("interface propagates Audited: "
                + ContractService.class.isAnnotationPresent(Audited.class));
        System.out.println("override inherits Traced: "
                + ChildAction.class.getDeclaredMethod("act")
                        .isAnnotationPresent(Traced.class));
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 -Xlint:all MetaAnnotationDemo.java
java MetaAnnotationDemo
```

Expected output:

```text
direct Route: false
direct GetReports: true
meta Route: GET /reports
resolved Route: GET /reports
child inherits Audited: true
child declares Audited: false
interface propagates Audited: false
override inherits Traced: false
```

Explanation:

1. `@Route` is not directly applied to `ReportController`, so the direct query returns `false`; `@GetReports` is directly applied, so it returns `true`.
2. `GetReports.class.getAnnotation(Route.class)` queries **the annotation type declaration itself** and reads `GET /reports`.
3. `findOneLevelRoute(...)` is a method we wrote: it reads the direct annotations of the class, gets `annotationType()`, and actively looks up `@Route` **at exactly one meta level**. Therefore, it can infer the route.
4. `@Audited` has `@Inherited`, so `ChildService` sees it via its superclass `BaseService`, even though `ChildService` does not declare it directly.
5. `ContractService` implements an interface annotated with `@Audited`, but `@Inherited` does not propagate across the `implements` relationship.
6. `@Traced` is applied to a method of `BaseAction`. The overriding method in `ChildAction` does not receive `@Traced` merely because the annotation type has `@Inherited`.

**Scope of the helper:** `findOneLevelRoute(...)` only serves a simple scenario; it **does not automatically traverse multiple levels**, does not automatically inherit conventions from superclasses, and does not check for conflicts if multiple annotations are meta-annotated with `@Route`. These rules must be clearly designed if used in a real application.

## 5. How Does Standard Java Reflection Actually Find Annotations?

Java reflection has the `AnnotatedElement` API implemented on classes, methods, fields, and applicable elements. The common methods have their own semantics:

| API | Kind of Annotation It Finds | Notes |
|---|---|---|
| `getDeclaredAnnotation(A.class)` | Annotation `A` directly applied to the element | Does not look up through superclasses |
| `getAnnotation(A.class)` | Annotation `A` that is "present" as defined by Java | May take inheritance into account for a **class** when `A` has `@Inherited` |
| `getDeclaredAnnotations()` | All directly declared annotations | Does not automatically expand meta-annotations |
| `getAnnotations()` | Annotations that are "present" | On a class, may include inherited annotations |
| `getDeclaredAnnotationsByType(A.class)` | `A` directly or indirectly via a **repeatable container** on the element | Does not automatically scan custom meta-annotations |
| `getAnnotationsByType(A.class)` | `A` annotations "associated" with the element | Understands repeatable containers and defined inheritance cases |

The term "indirectly present" in the `AnnotatedElement` documentation has a technical meaning related to **`@Repeatable` and container annotations**, not an arbitrary algorithm that reads `@A` and traces every meta-annotation located on `A.class`.

Example:

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

@Tag("api")
@Tag("core")
class TaggedService {}
```

If you call `TaggedService.class.getAnnotationsByType(Tag.class)`, the API returns two `@Tag` instances thanks to the **repeatable container** mechanism. This does not prove that it knows how to find `@Category` from `@BatchJob`: the two features have completely different contracts.

Do not rely on the array order of `getDeclaredAnnotations()` to resolve configuration precedence among independent annotations; if a framework allows multiple equivalent annotations, it should define an explicit ordering/conflict mechanism.

## 6. @Inherited Is a Limited Exception, Not a General Transitive Mechanism

`@Inherited` is declared on an **annotation type**, for example:

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policy {
    String value();
}

@Policy("strict")
class Parent {}

class Child extends Parent {}
```

Query:

```java
boolean inherited = Child.class.isAnnotationPresent(Policy.class);
Policy declared = Child.class.getDeclaredAnnotation(Policy.class);
```

Here `inherited == true` and `declared == null`. Java looks up the superclass when the subclass lacks the corresponding annotation and the annotation type has `@Inherited`. It **does not** modify the source code, does not physically copy an annotation onto the subclass, and does not automatically create another annotation.

Important limitations:

- **Only follows class superclasses:** a class implementing an interface annotated with `@Policy` does not automatically receive `@Policy` from the interface via `@Inherited`.
- **Not automatically inherited on methods:** if a method is overridden, annotations on the parent method are not automatically transferred to the child method, even if the annotation type is marked with `@Inherited`.
- **Does not make composed annotations transitive:** if an annotation A has a meta-annotation B, `@Inherited` does not automatically cause `getAnnotation(B.class)` on a class using A to infer B.
- **Know which annotation is inherited:** `@Inherited` is placed on the specific annotation type required for Java's mechanism to pick it up from the superclass; placing it on a related annotation at the meta level does not automatically confer inheritance to another composed annotation.

When a subclass directly declares the `Policy` annotation type itself, a normal query uses the subclass's annotation instead of continuing to retrieve that instance from the superclass. This is a lookup mechanism for a **specific annotation type**, not a merge of the values of all annotations of the same type across every level.

## 7. How Do One Meta Level and Multiple Meta Levels Differ?

Consider the following illustrative declarations (each annotation has RUNTIME retention for reflection):

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface SecurityBoundary {}

@SecurityBoundary
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface InternalFeature {}

@InternalFeature
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface InternalController {}

@InternalController
class BillingController {}
```

The path is:

```text
BillingController
    -> @InternalController          (direct annotation)
        -> @InternalFeature         (level-1 meta-annotation)
            -> @SecurityBoundary   (level-2 meta-annotation)
```

With standard reflection:

- `BillingController.class.getAnnotation(SecurityBoundary.class)` is `null`.
- `InternalController.class.getAnnotation(InternalFeature.class)` reads the level-1 annotation.
- `InternalFeature.class.getAnnotation(SecurityBoundary.class)` reads the next-level annotation.
- `InternalController.class.getAnnotation(SecurityBoundary.class)` **is still `null`**: reflection does not automatically traverse through `InternalFeature`.

A helper that scans only **one level** like `findOneLevelRoute` will not find `@SecurityBoundary` when starting from `BillingController`; reaching it requires a multi-level traversal algorithm.

This is the meaning of "limitations of transitive processing in Java Core": **metadata forms a traversable relationship**, but **there is no guarantee that the standard API will interpret or merge that chain for the application**.

## 8. If Writing Your Own Transitive Scanner, What Do You Need to Decide?

For the requirement of merely checking *whether a meta-annotation type exists somewhere along the path*, you can write an annotation graph traversal algorithm. The illustrative example below uses the reflection API and prevents revisiting an already-examined type:

```java
import java.lang.annotation.Annotation;
import java.lang.reflect.AnnotatedElement;
import java.util.HashSet;
import java.util.Set;

final class MetaScanner {
    static boolean hasMetaAnnotation(
            AnnotatedElement element,
            Class<? extends Annotation> sought) {
        Set<Class<? extends Annotation>> visited = new HashSet<>();
        for (Annotation direct : element.getDeclaredAnnotations()) {
            if (contains(direct.annotationType(), sought, visited)) {
                return true;
            }
        }
        return false;
    }

    private static boolean contains(
            Class<? extends Annotation> current,
            Class<? extends Annotation> sought,
            Set<Class<? extends Annotation>> visited) {
        if (!visited.add(current)) {
            return false;
        }
        if (current == sought) {
            return true;
        }
        for (Annotation meta : current.getDeclaredAnnotations()) {
            if (contains(meta.annotationType(), sought, visited)) {
                return true;
            }
        }
        return false;
    }
}
```

This is **a compilable utility** if saved in a file with the same class name or used within an appropriate source file. It only returns a boolean and only starts from the **directly declared annotations** of the input element. It contains no rules to:

- inherit annotations on superclasses/interfaces;
- read annotations with SOURCE or CLASS retention via runtime reflection;
- choose a specific value when multiple branches reach annotations of the same type;
- override/merge attributes between outer-level and inner-level annotations;
- determine precedence between direct declarations and transitive declarations;
- infer which annotations represent valid business configuration.

The `visited` set helps avoid repeated traversal in the meta-annotation graph; specifically, **defining the resolution policy** is more important than a piece of DFS code. If only one-level traversal is needed, the simple helper in the complete example is usually easier to control.

When a product needs composed annotations with many customizable attributes, aliases, or override rules, create a clear abstraction instead of assuming that every system should traverse the entire annotation graph without distinguishing meaning.

## 9. Attributes (Elements) Are Not Automatically Merged or "Aliased"

Suppose:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Endpoint {
    String path();
}

@Endpoint(path = "/default")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface WebEndpoint {
    String value() default "/custom";
}

@WebEndpoint("/orders")
class OrderEndpoint {}
```

From Java Core we can read:

- `OrderEndpoint.class.getAnnotation(WebEndpoint.class).value()` → `"/orders"`.
- `WebEndpoint.class.getAnnotation(Endpoint.class).path()` → `"/default"`.

**There is no rule in Java Core** that automatically treats `WebEndpoint.value()` as an alias for `Endpoint.path()` and turns `"/default"` into `"/orders"`. If a framework wants to let users override the path via `@WebEndpoint("/orders")`, it must declare and enforce this value-mapping rule.

Similarly, if two composed annotations both define an endpoint with different methods/paths, Java does not automatically decide which one takes precedence. You can report an error, forbid combining them, or establish a clear ordering. Do not rely on the arbitrary order of annotations returned from a scan.

## 10. How Do SOURCE, CLASS, and RUNTIME Affect Transitive Processing?

A scanner using Java reflection at runtime only sees annotations that are retained in a way accessible to reflection. If one level of the chain has SOURCE retention, the annotation usage at that level is stripped from the binary; with CLASS retention, standard runtime reflection cannot read that usage either.

| Position in the Chain | If SOURCE/CLASS | Consequence When Using Runtime Reflection |
|---|---|---|
| Composed annotation applied to a class, e.g., `@GetReports` | SOURCE is not stored in the class; CLASS is not exposed by reflection | A runtime scanner generally cannot start from `@GetReports` |
| Meta-annotation applied to an annotation type, e.g., `@Route` on `GetReports` | If not RUNTIME, reflection does not return the meta-annotation at that level | `@Route` cannot be found via `GetReports.class.getAnnotation(...)` |
| Annotation needed as a result to read attributes | Attributes of a non-visible type cannot be automatically retrieved via standard reflection | Must choose runtime metadata or an artifact processed at compile time |

Therefore, when designing a **runtime meta-annotation scanner**, the annotations that need to be visible along the search path generally must have `@Retention(RUNTIME)` appropriately. With **annotation processing at source compile time**, the processor can query the compiler model instead of runtime reflection, so the retention requirements differ: it can still see SOURCE annotations during the compilation pass being processed.

Do not change the retention of all annotations to RUNTIME out of habit. Choose when the metadata will be consumed first, and then choose the retention that fits the actual consumer.

## 11. Java Core and Framework Extensibility

A framework may intentionally define "combined" annotations to condense configuration:

```text
@BusinessEndpoint
     |
     +-- meta: @Route
     |
     +-- meta: @AccessPolicy
     |
     +-- meta: @LoggingCategory
```

However, for `@BusinessEndpoint` to carry business meaning, the framework must specifically implement:

1. **Discovery:** finding which annotations exist on a class/method; deciding whether to inspect superclasses/interfaces.
2. **Meta traversal:** limiting to one level or recursing, and whether to exclude standard meta-annotations from certain types of scans.
3. **Attribute resolution:** choosing which level's value applies when path, role, or timeout is defined multiple times.
4. **Conflict handling:** whether to report an error or choose an explicit precedence when multiple declarations are incompatible.
5. **Lifecycle:** whether to read at compile time via an annotation processor, via runtime reflection, or from generated artifacts.

For example, Spring Framework has its own utilities for composed annotations and merged annotations. That is **Spring's contract**, not an API or automatic feature of Java Core. In plain Java code, achieving similar rules requires building them yourself or using a library with equivalent definitions.

Seeing an annotation meta-annotated with another annotation does not mean every library in the application knows how to utilize that structure. Tools must be written to recognize it.

## 12. Common Mistakes and How to Test

**Mistake 1 — Assuming `getAnnotation` automatically finds meta-annotations on a class.**

```java
@Route(method = "GET", path = "/reports")
@interface GetReports {}

@GetReports
class ReportController {}
```

Querying `ReportController.class.getAnnotation(Route.class)` does not find it. Query `GetReports.class` instead, or write a custom scanner if you genuinely want to retrieve `Route` through `GetReports`.

**Mistake 2 — Applying `@Inherited` to a meta-annotation and expecting the composed annotation to be inherited automatically.**

Just because `@Route` has `@Inherited` does not mean `@GetReports` will automatically be inherited by every subclass. If you truly want the `GetReports` annotation to be reflected from the superclass, `@Inherited` must be placed on the **`GetReports` definition** and applied on the class. Even then, `@Route` still does not become a direct annotation of the subclass.

**Mistake 3 — Thinking `@Inherited` applies to interfaces and method overrides.**

It only supports superclass relationships for class-level annotations as specified by the JDK. If you need to scan interfaces or method overrides, the framework's algorithm must handle that separately; special care is needed when a class has multiple interfaces and methods with the same name.

**Mistake 4 — The meta-annotation has RUNTIME, but the outer annotation lacks RUNTIME.**

If the composed annotation has the default CLASS retention, a runtime scanner cannot see it on a class the way it can with RUNTIME. Each annotation type along the path needs its own retention designed separately; there is no automatic retention propagation mechanism.

**Mistake 5 — Confusing repeatable `getAnnotationsByType` with meta traversal.**

This API handles `@Repeatable` containers; it does not automatically traverse `@A -> @B -> @C`. The term "indirectly present" in the Javadoc does not mean arbitrary meta-level transitivity.

**Mistake 6 — Writing a custom DFS without semantic constraints.**

A scanner that traverses all annotations may encounter standard meta-annotations such as `@Retention` and `@Target`, or multiple custom configuration branches. Being able to traverse does not mean knowing how to combine attributes properly. Define the supported set of annotations and conflict rules clearly.

**Mistake 7 — Testing only the happy path.**

For a composed annotation used in a real project, you should test at least: direct annotations, one meta level, multiple meta levels, missing RUNTIME, class inheritance, interfaces, method overrides, multiple annotations with the same meta-annotation, and conflicting-value cases. These scenarios test the design of **the processor**, not just the annotation syntax.

## 13. Practical Design Rules

For Java Core, if you only want a **simple metadata label**, a direct annotation applied to a class/method is usually sufficient. If you need to group configurations under a short name, a custom meta-annotation can handle the **structure description** part; the **structure interpretation** part requires an explicit consumer.

When designing a composed annotation, ask yourself:

- Will the annotation be read by a **compile-time processor** or by **runtime reflection**?
- Which level is direct and which level needs to be queried through meta-annotations?
- Is superclass inheritance needed? Is scanning interfaces or method overrides with custom rules needed?
- Is there a need to change/override attributes of the meta-annotation, or is merely detecting its presence enough?
- If there are multiple paths to the same meta-annotation, how should they be selected, merged, or reported as errors?

Document that contract and provide verification examples. It helps avoid false expectations about core APIs and clarifies differences when porting code between plain Java and frameworks that support composed annotations.

## 14. Self-Check Exercises

### Exercise 1: Predict getAnnotation

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Checked {}

@Checked
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ValidatedType {}

@ValidatedType
class Customer {}
```

Predict the two expressions:

```java
Customer.class.isAnnotationPresent(Checked.class)
ValidatedType.class.isAnnotationPresent(Checked.class)
```

**Answer:** `false` and `true`. `Customer` directly has `@ValidatedType`; `ValidatedType` is the one that directly has `@Checked`.

### Exercise 2: Does @Inherited Propagate Through Interfaces?

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Registered {}

@Registered
interface Plugin {}

class FilePlugin implements Plugin {}
```

**Answer:** `FilePlugin.class.isAnnotationPresent(Registered.class)` is `false`. Java's `@Inherited` does not look up annotations from implemented interfaces.

### Exercise 3: Annotation with @Retention(RUNTIME) at the Inner Level

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface FeatureFlag {}

@FeatureFlag
@Target(ElementType.TYPE)
@interface Enabled {}

@Enabled
class Example {}
```

Can `Enabled` be read on `Example.class` using ordinary runtime reflection?

**Answer:** no. `Enabled` lacks `@Retention(RUNTIME)` and defaults to CLASS. `FeatureFlag` having its own RUNTIME retention does not automatically change the retention of `Enabled`.

### Exercise 4: Does @Repeatable Help Find @FeatureFlag from @Enabled?

**Answer:** no. `@Repeatable` together with `getAnnotationsByType(...)` only provides a mechanism for containing/unpacking multiple annotations of the same type according to Java's rules. This is not a general query API following meta-annotation paths.

### Exercise 5: Does an Overriding Method Receive the Parent Method's Annotations?

**Answer:** not automatically via `@Inherited`. A framework may choose to traverse methods across superclasses/interfaces, but Java reflection does not automatically copy or merge parent class method annotations onto overriding methods.

### Exercise 6: When to Write a One-Level Scanner, When to Consider a Framework?

**Answer:** a one-level scanner is reasonable when you need to look up a clear meta-annotation and do not have to handle hierarchies, aliases, or conflicts. When you need multi-level transitivity, complex inheritance, substitute attributes, and combining multiple annotations, design a complete algorithm or use a framework with well-defined and tested rules.

## References

- [Java SE 17 — `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): defines the forms of annotation presence and the differences among `getAnnotation`, `getDeclaredAnnotation`, and `getAnnotationsByType`.
- [Java SE 17 — `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): superclass scope, interface limitations, and elements outside classes.
- [JLS Java SE 17 — `9.6 Annotation Interfaces`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): standard meta-annotations, `@Inherited`, `@Repeatable`, `@Target`, and `@Retention`.
- [Java SE 17 — `java.lang.annotation.Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): retention of each annotation type.
- [Java SE 17 — `java.lang.annotation.Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html): conditions for applying annotations to annotation types, classes, methods, and other declarations.
