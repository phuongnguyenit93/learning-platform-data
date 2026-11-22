# getAnnotation vs. getDeclaredAnnotation in Java

When reading annotations via reflection, the two methods have very similar names but **differ in lookup scope**:

- `getAnnotation(AnnotationType.class)`: looks up an annotation of the specified type if that annotation is **present** (*present according to Java rules*). For `Class`, the result can come from a superclass when the annotation type is marked with `@Inherited`.
- `getDeclaredAnnotation(AnnotationType.class)`: looks up only an annotation that is **directly present** (*declared directly on the element under inspection*). This method **does not retrieve inherited annotations**.

Both belong to the `java.lang.reflect.AnnotatedElement` API, implemented by reflection classes such as `Class`, `Method`, `Field`, and `Constructor`. They return the corresponding annotation, or `null` if none is found within the lookup scope.

The difference is most clearly observed with **an annotation with `@Inherited` applied to a parent class and queried on a child class**. However, `getAnnotation()` should not be understood as “searching everywhere relevant”: it has strict rules, especially for interfaces, method overrides, and repeatable annotations.

## 1. Core Model: directly present and present

Imagine an `@Role("ADMIN")` annotation appearing on the `BaseController` declaration, while `AdminController extends BaseController` does not declare that annotation.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Role("ADMIN")
class BaseController {}

class AdminController extends BaseController {}
```

These are **valid declarations**, without a `main` method yet. `@Inherited` allows Java reflection, when querying a **child class**, to receive an annotation of type `Role` from its superclass if the child class does not directly declare that annotation type.

The following reads produce these results:

```java
Role a = AdminController.class.getAnnotation(Role.class);
// a != null, a.value().equals("ADMIN")

Role b = AdminController.class.getDeclaredAnnotation(Role.class);
// b == null

Role c = BaseController.class.getDeclaredAnnotation(Role.class);
// c != null, c.value().equals("ADMIN")
```

This is an **illustrative expression snippet**, which can be placed inside a method once the classes above exist.

### Direct Comparison Table

| Property | `getAnnotation(A.class)` | `getDeclaredAnnotation(A.class)` |
| --- | --- | --- |
| Return type | `A` or `null` | `A` or `null` |
| Reads annotations directly on the element? | Yes | Yes |
| For `Class`: can it see annotations from a superclass? | Yes, if the annotation type is `@Inherited` and satisfies inheritance rules | No |
| Automatically reads annotations on implemented (`implements`) interfaces? | No | No |
| Automatically retrieves annotations from overridden methods? | No | No |
| Automatically unwraps multiple `@Repeatable` annotations from a container? | No; use `getAnnotationsByType` | No; use `getDeclaredAnnotationsByType` |
| What does it return if no valid annotation exists in scope? | `null` | `null` |
| Requires runtime retention when using reflection? | Yes | Yes |

In terms of `AnnotatedElement` concepts:

- **Directly present:** an annotation declared directly on the element, with appropriate runtime metadata.
- **Present:** directly present **or**, when the element is a class and the annotation type is inheritable, found through a superclass according to `@Inherited` rules.
- **Indirectly present:** a repeatable annotation contained inside a container annotation.
- **Associated:** the scope used for `getAnnotationsByType`, encompassing directly/indirectly present annotations and certain inheritance cases.

These terms are not interchangeable. For repeatable annotations, the distinction between **present** and **associated** is particularly important.

## 2. @Inherited Determines Whether Lookup Searches Up the Superclass

`@Inherited` is a standard meta-annotation in `java.lang.annotation`. It is placed on an **annotation type definition**:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {}
```

The relevant types must be imported as in the example in section 1. With an annotation type like `Audited`, child classes can look up the annotation from a superclass even without declaring it directly.

Key points:

1. `@Inherited` **does not cause the annotation to be automatically copied as a declaration onto the child class**; it controls **how the annotation is looked up**.
2. The standard mechanism traverses only **superclasses of a class**, not interfaces implemented by the class.
3. If the child class directly declares **the same annotation type**, the child's declaration takes precedence when calling `getAnnotation()`.
4. Without `@Inherited`, `getAnnotation()` on a child class will **not** automatically retrieve an annotation placed only on the parent.
5. To access an annotation via reflection at runtime, the annotation type must have `@Retention(RetentionPolicy.RUNTIME)`. If `@Retention` is omitted, the default is `CLASS`.

### With @Inherited and Without @Inherited

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ConfigSource {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DirectOnly {}

@ConfigSource
@DirectOnly
class Parent {}

class Child extends Parent {}
```

These are **illustrative declarations**, requiring the corresponding imports.

For `Child.class`:

| Call | Result |
| --- | --- |
| `getAnnotation(ConfigSource.class)` | Non-`null`, obtained from `Parent` |
| `getDeclaredAnnotation(ConfigSource.class)` | `null` |
| `getAnnotation(DirectOnly.class)` | `null` |
| `getDeclaredAnnotation(DirectOnly.class)` | `null` |

If called on `Parent.class`, both methods see each annotation because they are declared directly on `Parent`.

### What If the Child Class Declares the Same Annotation?

```java
@Role("PARENT")
class Account {}

@Role("CHILD")
class PremiumAccount extends Account {}
```

This is an **illustrative snippet** using the `Role` type from section 1.

- `PremiumAccount.class.getAnnotation(Role.class).value()` returns `"CHILD"`.
- `PremiumAccount.class.getDeclaredAnnotation(Role.class).value()` also returns `"CHILD"`.
- If you want to know what value the parent declared, query `Account.class` directly.

Java does not merge `"PARENT"` and `"CHILD"` into one value; for a single annotation type, the declaration on the child class shadows the one of the same type from the parent during lookup.

## 3. Annotations Are Not Automatically Inherited from Interfaces

A common misconception: if a class implements an interface marked with an `@Inherited` annotation, calling `getAnnotation()` on that class will return the annotation from the interface.

This is incorrect. Java considers only **superclasses** under this rule:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Marker {}

@Marker
interface ServiceApi {}

class ServiceImpl implements ServiceApi {}
```

This is an **illustrative snippet**, requiring standard annotation imports.

```java
ServiceApi.class.getAnnotation(Marker.class) != null;   // true
ServiceImpl.class.getAnnotation(Marker.class) == null;  // true
ServiceImpl.class.getDeclaredAnnotation(Marker.class) == null; // true
```

The last two are `true` because `implements ServiceApi` is not an `extends` relationship between two classes. Even though an interface can extend another interface, `@Inherited` still does not automatically create a propagation path across the interface hierarchy.

If a framework wants to “look up annotations across interfaces”, it must actively traverse the interfaces and define how to handle conflicts. That is not the default behavior of `Class.getAnnotation()`.

## 4. For Methods, Fields, and Constructors: No Class-Style Inheritance Lookup

Because `getAnnotation()` is in `AnnotatedElement`, you can also call it on `Method`, `Field`, and `Constructor`. However, **do not apply the class `@Inherited` rule to these elements**.

Example:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Operation {
    String value();
}

class ParentService {
    @Operation("base")
    public void execute() {}
}

class ChildService extends ParentService {
    @Override
    public void execute() {}
}
```

This is an **illustrative snippet**, requiring the `Retention`, `RetentionPolicy`, `Target`, and `ElementType` imports.

If you look up the `execute()` method declared in `ChildService`:

```java
java.lang.reflect.Method childMethod =
    ChildService.class.getDeclaredMethod("execute");

childMethod.getAnnotation(Operation.class);          // null
childMethod.getDeclaredAnnotation(Operation.class);  // null
```

Even though the parent's method has `@Operation("base")`, the child's **overriding** method is a separate declaration. Java does not copy annotations from the overridden declaration to the overriding declaration.

### Distinguishing Finding a Method Object from Finding a Method's Annotations

There are two different operations:

- `Class.getMethod("execute")[ [T]]: finds a **public Method object**, and can find a method inherited from a superclass if the child class does not override it.
- `Method.getAnnotation(Operation.class)`: reads annotations of the **obtained Method object**, according to `AnnotatedElement` rules.

If `ChildService` **does not override** `execute()`, `ChildService.class.getMethod("execute")` can return the `Method` reflecting the method **declared on `ParentService`**. In that case, `getAnnotation(Operation.class)` can see `@Operation("base")` because that is the annotation on the parent method that was found, **not** because `Method.getAnnotation()` inherits annotations across overrides.

Similarly:

- A field that is **shadowed/hidden** in a child class does not automatically receive annotations from a same-named field in the parent.
- A child class's constructor does not inherit from a parent class's constructor; annotations placed on the parent constructor do not automatically appear on the child constructor.
- `@Inherited` has a useful scope when the annotation type is used on a **class declaration**; it does not cause annotations on methods/fields/constructors to propagate automatically through member relationships.

## 5. Standalone Java 17+ Example: Comparison in One Program

Create an **`AnnotationLookupDemo.java`** file and copy the entire code below. The example includes:

- `InheritedFlag` marked with `@Inherited`.
- `LocalFlag` not marked with `@Inherited`.
- A child class that declares no additional annotations.
- A child class that declares an annotation of the same type to override the visible metadata.
- A class implementing an annotated interface.
- An overriding method that does not receive the annotation from the parent method.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface InheritedFlag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface LocalFlag {
    String value();
}

@InheritedFlag("base")
@LocalFlag("base-only")
class Base {
    @LocalFlag("base-method")
    public void execute() {}
}

class Child extends Base {
    @Override
    public void execute() {}
}

@InheritedFlag("child")
class ExplicitChild extends Base {}

@InheritedFlag("interface")
interface MarkedInterface {}

class Implementation implements MarkedInterface {}

public class AnnotationLookupDemo {
    private static String value(InheritedFlag flag) {
        return flag == null ? "null" : flag.value();
    }

    public static void main(String[] args) throws NoSuchMethodException {
        System.out.println("child.getAnnotation="
                + value(Child.class.getAnnotation(InheritedFlag.class)));

        System.out.println("child.getDeclaredAnnotation="
                + value(Child.class.getDeclaredAnnotation(InheritedFlag.class)));

        System.out.println("child.localFlagAbsent="
                + (Child.class.getAnnotation(LocalFlag.class) == null));

        System.out.println("explicit.getAnnotation="
                + value(ExplicitChild.class.getAnnotation(InheritedFlag.class)));

        System.out.println("explicit.getDeclaredAnnotation="
                + value(ExplicitChild.class.getDeclaredAnnotation(InheritedFlag.class)));

        System.out.println("interface.impl="
                + value(Implementation.class.getAnnotation(InheritedFlag.class)));

        Method parent = Base.class.getDeclaredMethod("execute");
        Method child = Child.class.getDeclaredMethod("execute");

        System.out.println("parent.method="
                + parent.getAnnotation(LocalFlag.class).value());

        System.out.println("child.method.getAnnotationAbsent="
                + (child.getAnnotation(LocalFlag.class) == null));

        System.out.println("child.method.getDeclaredAnnotationAbsent="
                + (child.getDeclaredAnnotation(LocalFlag.class) == null));
    }
}
```

Compile and run using **JDK 17 or later**:

```bash
javac -encoding UTF-8 AnnotationLookupDemo.java
java AnnotationLookupDemo
```

**Exact** stdout:

```text
child.getAnnotation=base
child.getDeclaredAnnotation=null
child.localFlagAbsent=true
explicit.getAnnotation=child
explicit.getDeclaredAnnotation=child
interface.impl=null
parent.method=base-method
child.method.getAnnotationAbsent=true
child.method.getDeclaredAnnotationAbsent=true
```

Explanation:

1. `child.getAnnotation=base`: `Child` does not declare `InheritedFlag`, but the annotation type has `@Inherited`, so it receives it from `Base`.
2. `child.getDeclaredAnnotation=null`: `Child` has no direct `InheritedFlag` declaration.
3. `child.localFlagAbsent=true`: `LocalFlag` is declared only on `Base` and is not an `@Inherited` annotation type.
4. The two `explicit...=child` lines: `ExplicitChild` places `@InheritedFlag("child")` directly, so both methods retrieve the child's value.
5. `interface.impl=null`: `Implementation` only `implements MarkedInterface`; it is not a subclass of this interface in the superclass hierarchy.
6. `parent.method=base-method`: The Method object from `Base` has the `@LocalFlag("base-method")` annotation.
7. The two `child.method...Absent=true` lines: `Child.execute()` overrides the method, but does not declare the annotation directly. There is no mechanism to automatically inherit annotations from an overridden method.

The program only reads annotations and prints the results; **annotations do not automatically trigger business logic**. There are no libraries outside the JDK and no command-line arguments are required.

### What If @Retention(RUNTIME) Is Removed?

Annotations have a default retention of `RetentionPolicy.CLASS`, meaning the compiler can store them in the class file, but standard runtime reflection cannot retrieve them as in the program above. If you remove `@Retention(RetentionPolicy.RUNTIME)` from `InheritedFlag`, the `getAnnotation(InheritedFlag.class)` call will not return the annotation at runtime as in the example, and the corresponding lines will change.

Do not confuse `@Inherited` with `@Retention`: one describes **the lookup scope across parent classes**, while the other determines whether the annotation **exists to be read at runtime**.

## 6. getAnnotations and getDeclaredAnnotations: The Same Rules in Array Form

In addition to methods that read a single annotation type, Java provides:

```java
java.lang.annotation.Annotation[] all =
    Child.class.getAnnotations();

java.lang.annotation.Annotation[] direct =
    Child.class.getDeclaredAnnotations();
```

These are **illustrative expressions** using `Child` from the complete example.

- `getAnnotations()` returns the annotations that are **present** on the element. When the element is a class, the list may include `@Inherited` annotation types from superclasses.
- `getDeclaredAnnotations()` returns only the annotations that are **directly present**; it does not retrieve them from parent classes.
- Returns an **empty array** when none exist, not `null`.
- The order of annotations of different types in the array generally **should not be relied upon as a business contract**; inspect them by annotation type.

Two contrasting API pairs:

| What you want to read | Single annotation type | All annotations present within scope |
| --- | --- | --- |
| Present / possibly inherited on a class | `getAnnotation(A.class)` | `getAnnotations()` |
| Directly declared | `getDeclaredAnnotation(A.class)` | `getDeclaredAnnotations()` |

Choose the API based on the business question: do you need the **effective configuration** inherited through parent classes, or do you need to know **what the current class actually declares**?

## 7. Repeatable Annotations: Why Is getAnnotationsByType Needed?

`@Repeatable` allows applying multiple annotations of the same type to a single element. The compiler can represent multiple occurrences through a **container annotation**. Consequently, calling `getAnnotation(A.class)` or `getDeclaredAnnotation(A.class)` will not necessarily retrieve `A` annotations that are contained indirectly.

Example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RoleName {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    RoleName[] value();
}

@RoleName("READ")
@RoleName("WRITE")
class PermissionBase {}

class PermissionChild extends PermissionBase {}
```

These are **valid illustrative declarations**; there is no `main` method. The container type `Roles` is marked with `@Inherited` compatibly with the `RoleName` annotation type. For `PermissionChild`:

```java
// Illustrative expressions:
PermissionChild.class.getAnnotation(RoleName.class);         // null
PermissionChild.class.getDeclaredAnnotation(RoleName.class); // null

PermissionChild.class.getAnnotationsByType(RoleName.class).length; // 2
PermissionChild.class.getDeclaredAnnotationsByType(RoleName.class).length; // 0
```

Why are the results different?

1. The two `@RoleName` annotations on `PermissionBase` are represented by the compiler through a `@Roles` container.
2. `getAnnotation(RoleName.class)` looks for **a single present RoleName annotation**; it **does not automatically unwrap the container**.
3. `getAnnotationsByType(RoleName.class)` is the API that supports repeatable annotations: it inspects **associated** annotations, including cases contained within a container.
4. `PermissionChild` does not directly declare `RoleName` or `Roles`, so `getDeclaredAnnotationsByType(RoleName.class)` returns an empty array. The version without `Declared` can look up to the superclass thanks to the corresponding rules for repeatable `@Inherited` annotations.

### When the Child Itself Declares Repeatable Annotations

If `PermissionChild` declares one `@RoleName("ADMIN")` directly, `getAnnotationsByType(RoleName.class)` on the child returns the annotation directly associated with the child; it **does not accumulate by default** `READ`/`WRITE` from the parent. Once Java determines that the annotation type already has directly or indirectly present information on the child, looking up to the superclass for that type is no longer needed.

Therefore, when writing code that supports repeatable annotations, use:

- `getAnnotationsByType(A.class)` if you want to read all *associated* annotations of the same type, taking standard inheritance cases into account.
- `getDeclaredAnnotationsByType(A.class)` if you want to read all annotations of the same type present directly or indirectly via a container **directly on the current element**.

You cannot simply replace `getAnnotation` with `getDeclaredAnnotation` and expect to properly handle a list of repeatable annotations.

## 8. Distinguishing Annotation Declarations, Meta-Annotations, and Type-Use

### Meta-Annotations Do Not Automatically “Propagate” Through getAnnotation

Suppose:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tracked {}

@Tracked
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface AuditEnabled {}

@AuditEnabled
class BillingService {}
```

These are **illustrative declarations**, requiring imports of the standard annotations. `AuditEnabled` is **meta-annotated** with `Tracked`, whereas `BillingService` only directly declares `AuditEnabled`.

```java
BillingService.class.getAnnotation(Tracked.class);       // null
AuditEnabled.class.getAnnotation(Tracked.class);         // non-null
```

Plain Java reflection does not automatically inspect the definition of every present annotation and aggregate them into annotations of the class. A framework may support meta-annotation traversal, but that is additional framework logic.

### Type-Use Annotations Require a Different Reflection API

`Class.getAnnotation()` and `Method.getAnnotation()` primarily read **declaration annotations**. If an annotation is placed on a **type use**, such as:

```java
// Assume @Mark allows TYPE_USE.
java.util.List<@Mark String> values;
```

the annotation here belongs to the type argument `String`, and is not placed on the `values` field itself. You need to go through `Field.getAnnotatedType()`, `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`, and the `AnnotatedType.getAnnotation()` API to read the right location.

Do not equate `getDeclaredAnnotation()` with “reading every annotation located inside the current declaration”. It only changes the scope to **directly present** on the specific `AnnotatedElement` you are calling it on.

## 9. Process for Choosing the Right Method When Building a Framework

**Step 1 — Identify the element to read.** Is it a `Class`, `Method`, `Field`, `Constructor`, `Parameter`, or `AnnotatedType`? An overriding method and the parent method are two different elements.

**Step 2 — Determine the lookup policy.** If configuration is allowed to be inherited through the class hierarchy via `@Inherited`, consider `Class.getAnnotation`. If you need to inspect **local** declarations for validation, diffing, or override detection, use `getDeclaredAnnotation`.

**Step 3 — Check retention.** Reflection cannot see annotations with `SOURCE` or `CLASS` retention via these runtime calls; for runtime access, `RUNTIME` is required.

**Step 4 — Consider repeatability.** If the annotation type has `@Repeatable` and can appear multiple times, prefer the `getAnnotationsByType` / `getDeclaredAnnotationsByType` APIs; do not try to retrieve them with a single `getAnnotation` call.

**Step 5 — Check interface/override limitations.** Java does not automatically traverse interfaces to “inherit annotations”; nor does it automatically inherit metadata from overridden methods. If that business rule is needed, the tool must traverse them explicitly.

**Step 6 — Handle null, empty arrays, and configuration errors.** With `getAnnotation`, always check for `null` before calling elements such as `value()`. With array-returning APIs, check `length` or iterate over the array; do not assume a result is present.

**Step 7 — Write tests with parent/child classes.** Create a class without annotations, a child class that overrides an annotation, an annotated interface, an overriding method, and a repeatable container. A clear test is better than guessing from API names.

## 10. Common Misconceptions

| Misconception | What Is True |
| --- | --- |
| “`getAnnotation()` always looks up through all parents/interfaces” | Standard inheritance rules apply only through **superclasses** for `@Inherited` annotation types on classes |
| “`getDeclaredAnnotation()` also retrieves from superclasses” | Only retrieves annotations **directly** on the queried element |
| “Adding `@Inherited` makes all method annotations inherited as well” | No. `@Inherited` does not apply to method overrides in that way |
| “When a child declares an annotation of the same type, the system automatically merges it with the parent's” | Typically uses the child's direct declaration; does not automatically merge |
| “`getAnnotation()` always retrieves repeatable annotations” | For indirect annotations inside a container, use `getAnnotationsByType` |
| “`getDeclaredAnnotation()` sees all type-use annotations nested inside generics” | You must read the corresponding `AnnotatedType` |
| “An `@Retention(CLASS)` annotation can still be retrieved by `getAnnotation()`” | Runtime reflection requires `RUNTIME` |
| “`getAnnotation()` not finding an annotation means the class has no metadata at all” | The annotation might be on a type-use, in a repeatable container, on an interface/framework convention, or lacking runtime retention |
| “Reading `@Tracked` on an annotation type will cause a class to have that annotation indirectly” | Java does not automatically infer a meta-annotation as an annotation on the class using it |

## 11. Self-Check Questions

**Question 1.** `Base` has `@Inherited @interface Flag` with `@Flag` on the class declaration, while `Child extends Base` does not declare `@Flag`. Which method sees the annotation on `Child.class`?

**Answer:** `getAnnotation(Flag.class)` if the annotation has `RUNTIME` retention and follows `@Inherited` rules. `getDeclaredAnnotation(Flag.class)` returns `null`.

**Question 2.** Why can `Child.class.getDeclaredAnnotation(Flag.class)` return `null` while `Child.class.getAnnotation(Flag.class)` is non-`null`?

**Answer:** The former requires the annotation to be **directly declared**; the latter allows **present** annotations via `@Inherited` on a superclass.

**Question 3.** An interface is marked with an `@Inherited` annotation; does a class implementing the interface automatically see the annotation when calling `getAnnotation()`?

**Answer:** No. Java does not retrieve annotations from interfaces via the `@Inherited` mechanism.

**Question 4.** A method in a subclass overrides a parent method annotated with `@Action`. Does `getAnnotation(Action.class)` on the **overriding** method automatically return the parent method's annotation?

**Answer:** No. You must explicitly define a policy to look up metadata on the parent method if the application requires it.

**Question 5.** If the `@Tag` annotation is repeated twice and contained in `@Tags`, which method reads both values?

**Answer:** `getAnnotationsByType(Tag.class)` or `getDeclaredAnnotationsByType(Tag.class)`, depending on whether you need to consider inheritance cases or only declarations directly on the element.

**Question 6.** When there are no annotations, does `getDeclaredAnnotations()` return `null` or an empty array?

**Answer:** An empty array.

**Question 7.** When should you choose `getDeclaredAnnotation()` for a configuration system?

**Answer:** When you need to confirm that the current element **declares the annotation itself**, for example deciding whether a class overrides parent configuration metadata; use `getAnnotation()` when the policy genuinely allows standard inheritance.

## References

- [Java SE 17 API — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): definitions of directly present, present, associated, and lookup methods.
- [Java SE 17 API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): behavior of `getAnnotation`, `getDeclaredAnnotation`, and related APIs.
- [Java SE 17 API — Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): limits of annotation inheritance on classes.
- [Java SE 17 API — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): container annotations and multiple annotations of the same type.
- [Java Language Specification 17, §9.6.4.3 — @Inherited](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3).

**Key takeaway:** `getDeclaredAnnotation()` answers “what annotations does **this element itself declare**?”; `getAnnotation()` answers “what annotations are **present according to Java rules**?”. For a class hierarchy, `@Inherited` can make the two answers differ. For repeatable annotations, interfaces, or method overrides, you must choose the exact API and lookup policy rather than inferring from method names.
