# Combining Repeatable Annotations with @Inherited in Java

When an annotation is marked with `@Repeatable`, you can apply multiple annotations of the same type to the same declaration. When that annotation also uses `@Inherited`, Java Reflection can look up those annotations **through class inheritance**. However, the result is not simply “take the parent's annotations and append the child's annotations”.

**Most important rule:** with `getAnnotationsByType(AnnotationType.class)` on a class, **if the current class directly or indirectly declares annotations of the requested type, those annotations are used; otherwise, if that type has `@Inherited`, the lookup can walk up to the superclass**. This usually results in **replacing the parent's list**, rather than automatically merging lists.

To do this correctly, you must also declare `@Inherited` properly **on both the repeatable annotation and the container**, choose `RUNTIME` retention if you want to read them via Reflection, and clearly distinguish `getAnnotationsByType` from APIs that only read a single annotation or only read direct declarations.

## 1. Recap of the Two Independent Mechanisms

### 1.1. @Repeatable Enables Multiple Occurrences

A repeatable annotation has a corresponding container:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}
```

`@Role` is the repeatable annotation type. `@Roles` is the **container**, which has an element named exactly `value()` with the return type `Role[]`. When used:

```java
@Role("read")
@Role("write")
class Service {
}
```

the compiler can represent the two `@Role` annotations via the `@Roles` container. Declaring `@Repeatable` does not automatically generate the container: you must define `@interface Roles` yourself with a valid signature.

### 1.2. @Inherited Controls Lookup Across Superclasses

`@Inherited` is a **meta-annotation** for annotation types. It specifies that in appropriate Reflection lookups, an annotation on a **parent class** can be found on a **child class** that has not declared the corresponding annotation.

```java
import java.lang.annotation.Inherited;

@Inherited
@interface Marker {
}
```

`@Inherited` does not mean the JVM copies the annotation into the subclass's source or `.class` file; it affects **Reflection lookup semantics**. It applies only along the **class's superclass** hierarchy, does not automatically retrieve annotations from interfaces implemented via `implements`, and does not automatically inherit annotations on methods, fields, or parameters.

An annotation with only `@Inherited` and without `@Repeatable` does not automatically allow repeated use. Similarly, an annotation with only `@Repeatable` is not automatically inherited in Reflection APIs.

## 2. Valid Annotation Pair When Combining @Repeatable and @Inherited

Declarations used in most examples:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
```

Role of each component:

1. `@Repeatable(Roles.class)` is **applied to `Role`** to allow repeating the `Role` type.
2. `Roles.value()` must return **`Role[]`**, i.e., a one-dimensional array of the repeatable annotation itself; not `String[]`, a single `Role`, or `List<Role>`.
3. `@Inherited` **on `Role`** allows `Role` to be looked up according to inheritance rules.
4. **The container `Roles` must also have `@Inherited`** because `Role` is marked with `@Inherited`; this is also a validity constraint for a repeatable annotation type.
5. `@Retention(RUNTIME)` on **both** so that Reflection can see the annotation/container at runtime.
6. `@Target(TYPE)` on both annotations is compatible so they can be applied to the required type declarations.

**Important:** if `Role` has `@Inherited` but `Roles` does not have `@Inherited`, the compiler will reject the repeatable annotation pair definition. You cannot “patch” this by adding an `@Inherited` at the usage site on a class; `@Inherited` must be declared on the **annotation type**.

Retention must also be compatible: if `Role` has `RUNTIME`, `Roles` must not use `CLASS` or `SOURCE`. If `@Retention` is omitted, it defaults to `CLASS`; the Reflection APIs in this article will not return those annotations.

### Why Does the Container Also Need @Inherited?

When two `@Role` annotations are applied together on a class, the compiler represents them via **`@Roles`**. In the class file, what Java Reflection sees as the direct annotation when querying the container type is `@Roles`, containing `Role[]`.

Therefore, both parts must participate in a consistent configuration. `@Inherited` on `Role` states that lookups by the `Role` type can use the superclass; `@Inherited` on the container ensures that the type holding the repeated instances is also marked properly according to the language constraints.

Do not assume that `@Repeatable` automatically turns every annotation in the array into individual directly declared annotations on the subclass.

## 3. Complete Java 17+ Program: Testing Each Inheritance Case

Create a single file named **`InheritedRepeatableDemo.java`**:

```java
import java.lang.annotation.*;
import java.util.Arrays;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}

@Role("base-read")
@Role("base-write")
class BaseService {
}

class ChildService extends BaseService {
}

@Role("local")
class LocalService extends BaseService {
}

@Role("local-a")
@Role("local-b")
class LocalPairService extends BaseService {
}

@Roles({@Role("manual-a"), @Role("manual-b")})
class ExplicitService extends BaseService {
}

@Roles({})
class EmptyContainerService extends BaseService {
}

@Role("iface")
interface Contract {
}

class Implementation implements Contract {
}

public class InheritedRepeatableDemo {
    static void inspect(Class<?> type) {
        Role[] associated = type.getAnnotationsByType(Role.class);
        Role[] declared = type.getDeclaredAnnotationsByType(Role.class);

        String a = Arrays.toString(
                Arrays.stream(associated)
                      .map(Role::value)
                      .toArray(String[]::new));
        String d = Arrays.toString(
                Arrays.stream(declared)
                      .map(Role::value)
                      .toArray(String[]::new));

        System.out.println(type.getSimpleName()
                + " | byType=" + a
                + " | declared=" + d
                + " | container=" + (type.getAnnotation(Roles.class) != null));
    }

    public static void main(String[] args) {
        inspect(BaseService.class);
        inspect(ChildService.class);
        inspect(LocalService.class);
        inspect(LocalPairService.class);
        inspect(ExplicitService.class);
        inspect(EmptyContainerService.class);
        inspect(Implementation.class);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 InheritedRepeatableDemo.java
java InheritedRepeatableDemo
```

Exact stdout:

```text
BaseService | byType=[base-read, base-write] | declared=[base-read, base-write] | container=true
ChildService | byType=[base-read, base-write] | declared=[] | container=true
LocalService | byType=[local] | declared=[local] | container=true
LocalPairService | byType=[local-a, local-b] | declared=[local-a, local-b] | container=true
ExplicitService | byType=[manual-a, manual-b] | declared=[manual-a, manual-b] | container=true
EmptyContainerService | byType=[base-read, base-write] | declared=[] | container=true
Implementation | byType=[] | declared=[] | container=false
```

**Verification:** this example was compiled with `javac --release 17` and actually run; the stdout lines were cross-checked.

## 4. Analyzing the Results from Parent Class to Child Class

### 4.1. Parent Class Has Two Repeated Annotations

```java
@Role("base-read")
@Role("base-write")
class BaseService {}
```

`BaseService.class.getAnnotationsByType(Role.class)` returns two `Role` elements, containing `"base-read"` and `"base-write"`, respectively. Meanwhile, `getDeclaredAnnotationsByType(Role.class)` also returns two elements because they **originate from that class declaration itself**, even though they may be represented via the container.

If you use `BaseService.class.getAnnotation(Roles.class)`, the API retrieves the single container annotation, and you can access the `Role[]` array via `value()`.

### 4.2. Child Class Has No Role of Its Own: Received from Superclass

```java
class ChildService extends BaseService {}
```

Because `ChildService` has no `Role` declared directly or indirectly on the child class and `Role` is an inherited annotation, `ChildService.class.getAnnotationsByType(Role.class)` returns **the parent's two Role annotations**.

However:

```java
ChildService.class.getDeclaredAnnotationsByType(Role.class)
```

returns an **empty array**, because no `Role` is declared by `ChildService` itself. The word “declared” in the API is very important: it ignores values coming from the superclass.

### 4.3. Child Class Has One Role of Its Own: Does Not Append the Parent's

```java
@Role("local")
class LocalService extends BaseService {}
```

`LocalService.class.getAnnotationsByType(Role.class)` returns **only a single element `"local"`**, rather than three elements `["base-read", "base-write", "local"]`.

Reason: the `Role` type already has **a direct occurrence** on the child class. When the requested type is already present according to the associated annotations rules on the current class, Reflection **does not continue fetching `Role` annotations from the superclass to append them**.

This differs from many “configuration merging” styles that frameworks might implement on their own.

### 4.4. Child Class Has Two Roles of Its Own: Replaces the Entire Parent List

```java
@Role("local-a")
@Role("local-b")
class LocalPairService extends BaseService {}
```

`getAnnotationsByType(Role.class)` returns `["local-a", "local-b"]`. The two usages on the child class are held by the child class's `Roles` container; they **replace** the list found via the superclass in the `Role` result of this API.

**Practical rule:** if a child class declares one or more `Role` annotations to customize the list, treat that list as the `Role` configuration set specific to the child class when using `getAnnotationsByType`, not as a “delta” automatically added to the parent.

### 4.5. Child Class Uses an Explicit Container

```java
@Roles({@Role("manual-a"), @Role("manual-b")})
class ExplicitService extends BaseService {}
```

The result of `getAnnotationsByType(Role.class)` is `["manual-a", "manual-b"]`, the same as writing two separate `@Role` annotations. The API is able to **unpack the valid container** to retrieve the list of `Role` annotations.

Writing the container explicitly does not change the underlying data type: `Roles.value()` is still `Role[]`.

### 4.6. Empty Container: A Notable Edge Case

```java
@Roles({})
class EmptyContainerService extends BaseService {}
```

This is a case that is easy to mispredict.

In the Java example in section 3:

- `getDeclaredAnnotationsByType(Role.class)` returns an **empty array** because the container on the child class contains no `Role` annotations.
- `getAnnotationsByType(Role.class)` instead returns **`["base-read", "base-write"]`** because there is no directly or indirectly present `Role` from the child class, so the inheritance rule of `@Inherited` allows looking up the superclass.
- `getAnnotation(Roles.class)` can still return the `Roles` container present on the child class, even though `Roles.value()` is an empty array.

Therefore, **placing `@Roles({})` is not a reliable way to “clear” all `Role` annotations from the parent class when using `getAnnotationsByType(Role.class)`**. If your business logic needs an inheritance-disabling state, model an explicit “disable/override” marker or value with clear semantics and handle it in the metadata consumption layer.

This is a consequence of the Reflection rules regarding *directly present*, *indirectly present*, and *associated* annotations, not a bug in Java.

### 4.7. Implementing an Interface Does Not Carry Over Role

```java
@Role("iface")
interface Contract {}

class Implementation implements Contract {}
```

`Implementation.class.getAnnotationsByType(Role.class)` returns an **empty array**. Even though `Role` has `@Inherited`, the `implements` relationship is not the **extends class** relationship that `@Inherited` applies to. Having an annotation on an interface does not make the implementing class automatically see that annotation through this standard inheritance mechanism.

If you need to look up metadata from implemented interfaces, your tooling must actively traverse `getInterfaces()` and establish clear rules for multiple interfaces, duplicates, ordering, and precedence.

## 5. Understanding the Three Types of “Presence” in Reflection Accurately

Java distinguishes multiple forms of annotation presence. For repeatable annotations, you should interpret them in terms of the **queried** annotation type, rather than merely checking whether a physical container exists.

- **Directly present:** an annotation of that exact type exists on the element that Reflection treats as direct, for example a `@Role("local")` on `LocalService`.
- **Indirectly present:** the container annotation is directly present and its `value()` array contains one or more annotations of the repeatable type, for example the two `@Role` annotations on `BaseService`.
- **Associated:** used for type-based queries; it includes directly/indirectly present annotations on the current element and, if none exist there and the annotation type carries `@Inherited` on a class, can walk up to the superclass to look it up.

Because `getAnnotationsByType(Role.class)` relies on associated annotations of type `Role`, it supports single occurrences, multiple occurrences, and appropriately inherited annotations.

You can read the rule in order:

```text
getAnnotationsByType(Role.class) on a Class
    |
    +-- One or more direct / indirect Role annotations on this class?
    |       |
    |       +-- Yes --> return those Role annotations (do not append parent's Role)
    |       |
    |       +-- No
    |              |
    |              +-- Does Role have @Inherited and a superclass?
    |                       |
    |                       +-- Yes --> continue lookup up to superclass
    |                       |
    |                       +-- No  --> return empty array
```

The diagram illustrates only the `Class<?>` lookup scenario in this article. Do not use it to claim that `@Inherited` works on every kind of `AnnotatedElement`.

## 6. Comparing the Reflection APIs

Using the `Role` and `Roles` types from the main example:

| API | Unpacks repeatable container? | Considers superclass when applicable? | When to use |
| --- | --- | --- | --- |
| `type.getDeclaredAnnotationsByType(Role.class)` | Yes | **No** | Retrieve only directly/indirectly present Role annotations on the current class |
| `type.getAnnotationsByType(Role.class)` | Yes | **Yes**, if Role has `@Inherited` | Retrieve Role annotations associated with the class according to standard rules |
| `type.getDeclaredAnnotation(Role.class)` | Does not unpack container | No | Query a single directly declared Role |
| `type.getAnnotation(Role.class)` | Does not unpack container | Yes, according to the “present” rule for a single Role | Query a single Role; not suitable for reading all repeatable annotations |
| `type.getDeclaredAnnotation(Roles.class)` | Reads container as a single annotation | No | Retrieve the container declared by the class itself |
| `type.getAnnotation(Roles.class)` | Reads container as a single annotation | Can inherit container if `@Inherited` | Retrieve a single container; **not equivalent** to querying the set of Role annotations |

### 6.1. A Subtle Pitfall: Querying the Container vs. Querying Role Can Yield Different Configurations

In section 3, `LocalService` has a direct `@Role("local")`, while `BaseService` has a container holding `"base-read"` and `"base-write"`.

When calling:

```java
LocalService.class.getAnnotationsByType(Role.class)
```

the result is a single `Role` `"local"`. However:

```java
LocalService.class.getAnnotation(Roles.class)
```

can return the **`Roles` container inherited from `BaseService`**, because `LocalService` does not directly declare the `Roles` container and the container is marked with `@Inherited`. These are **two different Reflection queries**.

Therefore, **you must not conclude** that retrieving `Roles.class` and calling `value()` is always equivalent to `getAnnotationsByType(Role.class)` on an arbitrary class in an inheritance hierarchy.

If your goal is to return `Role` annotations according to the standard repeatability/inheritance rules, **call `getAnnotationsByType(Role.class)` directly**. Read the container only when you genuinely want to work with the `Roles` annotation type as a separate metadata type.

### 6.2. getAnnotation(Role.class) Is Not a “First Role” API

`getAnnotation(Role.class)` does **not** mean “get the first element of `getAnnotationsByType(Role.class)`”. If a class has multiple `Role` annotations wrapped in `Roles`, `getAnnotation(Role.class)` can return `null` even though `getAnnotationsByType(Role.class)` returns multiple elements.

Do not use “get a single annotation” to infer the first element of the list; if you want to select a specific element from the array, you must define clear rules for ordering and handle the empty array case yourself.

## 7. @Inherited Does Not Apply to Method, Field, or Parameter Annotations

`@Inherited` only extends the lookup rules for annotations on a **class** along the appropriate class inheritance relationship. It does not automatically propagate annotations from an overridden method to the overriding method in a subclass.

Standalone example in the file **`MethodBoundaryDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Flags {
    Flag[] value();
}

class Parent {
    @Flag("first")
    @Flag("second")
    public void act() {
    }
}

class OverrideChild extends Parent {
    @Override
    public void act() {
    }
}

class InheritChild extends Parent {
}

public class MethodBoundaryDemo {
    public static void main(String[] args) throws Exception {
        Method overridden = OverrideChild.class.getMethod("act");
        Method inherited = InheritChild.class.getMethod("act");

        System.out.println(overridden.getDeclaringClass().getSimpleName());
        System.out.println(overridden.getAnnotationsByType(Flag.class).length);
        System.out.println(inherited.getDeclaringClass().getSimpleName());
        System.out.println(inherited.getAnnotationsByType(Flag.class).length);
    }
}
```

Run:

```bash
javac --release 17 MethodBoundaryDemo.java
java MethodBoundaryDemo
```

Stdout:

```text
OverrideChild
0
Parent
2
```

Two points worth noting:

- `OverrideChild` actually **declares a new `act()` method**, without `@Flag`; when reading this `Method`, the annotations from the parent's method are not automatically propagated down, so the result is `0`.
- `InheritChild` **does not override** `act()`. Calling `getMethod("act")` on it can return the `Method` object itself declared by `Parent`; `getDeclaringClass()` is `Parent`, and directly reading annotations on the **Parent.act method** finds the two `@Flag` annotations. This is **not** `@Inherited` being applied to methods.

The difference lies in **which Method object is returned**, not in an annotation inheritance rule on methods.

## 8. Choosing the Right @Retention for Both Annotation Types

`@Inherited` does not turn an annotation with only `CLASS` retention into metadata readable via Reflection. If you expect:

```java
ChildService.class.getAnnotationsByType(Role.class)
```

then `Role` and `Roles` in the example must be retained until runtime.

| Primary annotation Role | Container Roles | Accepted by compiler for retention? | Runtime Reflection query |
| --- | --- | --- | --- |
| `RUNTIME` | `RUNTIME` | Yes | Works if the annotation exists |
| `RUNTIME` | `CLASS` | **No** | Rejected by compiler because container retention is shorter |
| `CLASS` | `CLASS` | Yes | No Role information via standard Reflection |
| `SOURCE` | `SOURCE` | Yes | Present only at the source stage; not readable via Reflection |

If `@Retention` is not specified for an annotation type, the default value is `CLASS`. This often explains the situation where “I already wrote `@Inherited`, yet `getAnnotationsByType` still returns an empty array”.

A compiler can read/inspect annotations during pre-runtime stages using its own mechanisms. However, the standard Reflection APIs in this article require `RUNTIME`.

## 9. Checking for a Valid Container Pair

Given:

```java
@Repeatable(Audits.class)
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audit {
    String event();
}
```

a matching container:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audits {
    Audit[] value();
}
```

Common compiler errors:

### 9.1. Forgetting @Inherited on the Container

```java
// Incorrect if Audit is annotated with @Inherited:
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audits {
    Audit[] value();
}
```

The compiler enforces the container rule: if the repeatable type has `@Inherited`, the container must also have `@Inherited`.

### 9.2. Using the Wrong value() in the Container

```java
// Incorrect if used as the container for Audit:
@interface Audits {
    String[] value();
}
```

`Audit.event()` has type `String`, but the container must hold **`Audit[]`**, not an array of `event` values. Do not replace it with `Audit value()`, `List<Audit>`, or rename the element to `items()`.

### 9.3. Declaring Additional Container Elements Without a Default

```java
// Incorrect when used as a repeatable container:
@interface Audits {
    Audit[] value();
    String owner();
}
```

If the compiler generates the container for repeated `@Audit` annotations, it will not know the required `owner` value. If an additional element is needed, write `String owner() default "system";`. Do not add extra data to the container unless there is an actual need to process it.

### 9.4. Incompatible Targets on the Two Annotations

If `Audit` is used on class declarations and method declarations, the container must allow the necessary locations to represent those multiple usages. A practical configuration is to declare compatible `@Target` values on both the repeatable annotation and the container, then verify with `javac`.

`@Inherited` itself still does not make method annotations inherited across overrides, even if both types declare the `METHOD` target.

## 10. @Inherited Does Not Automatically “Merge Configurations” Across Class Hierarchy Levels

In an application, you might want a child class to **inherit most permissions** from its parent class and then add a new permission. However, the standard `getAnnotationsByType` rule does not do that when the child class has its own `Role`.

Example:

```java
@Role("READ")
@Role("EXPORT")
class DocumentBase {
}

@Role("EDIT")
class DocumentEditor extends DocumentBase {
}
```

In the case where both `Role` and `Roles` are configured as in section 2:

```java
Role[] roles = DocumentEditor.class.getAnnotationsByType(Role.class);
```

the `roles` array consists of `Role("EDIT")` according to the associated annotations lookup rule, **and does not automatically contain `READ` and `EXPORT`**.

If your business logic requires **merging along the superclass chain**, you need to explicitly define an algorithm such as:

1. Traverse the current class and then walk up each superclass using `getSuperclass()`.
2. At **each class**, read only the annotations declared by that class with `getDeclaredAnnotationsByType(Role.class)` to avoid duplicates via the inheritance mechanism.
3. Define precedence: child-first or parent-first, whether to deduplicate, and whether “deny/disable” is allowed.
4. Merge the values according to your application's policy rather than assuming `@Inherited` provides this.

The following Java pseudo-code illustrates **explicit collection**, not how Reflection works by default:

```java
static java.util.List<Role> collectDeclaredRoles(Class<?> type) {
    java.util.List<Role> result = new java.util.ArrayList<>();
    for (Class<?> current = type;
         current != null;
         current = current.getSuperclass()) {
        Role[] here = current.getDeclaredAnnotationsByType(Role.class);
        java.util.Collections.addAll(result, here);
    }
    return result;
}
```

This snippet requires the `Role` types from section 2 and must be placed inside a class; it intentionally **merges information across multiple levels**. For `DocumentEditor`, this traversal sees `EDIT` on the child and `READ`, `EXPORT` on the parent, unlike standard `getAnnotationsByType`.

**Especially for access control/authorization:** do not assume merging annotations is safe by default. “Override”, “additive”, and “deny” semantics have security implications; they must have formal rules and tests.

## 11. Grandchild, Direct Child, and Undeclared Cases

Suppose:

```java
@Role("root")
class Root {
}

class Middle extends Root {
}

@Role("leaf")
class Leaf extends Middle {
}
```

`Middle.class.getAnnotationsByType(Role.class)` looks up `Root` and returns `"root"` if there is no annotation on `Middle`. However, `Leaf.class.getAnnotationsByType(Role.class)` returns `"leaf"` due to the direct annotation on `Leaf`; it does not append `"root"`.

If `Leaf` did not declare `Role`, the query could continue past `Middle` to find `Root`. This rule applies along the **extends class chain**; it does not traverse into any interface implemented by `Middle` or `Leaf`.

## 12. Common Misconceptions

**“Only `@Inherited` on the primary annotation is needed; the container does not matter.”** False. When an annotation is repeatable and carries `@Inherited` itself, the container must also be marked with `@Inherited` as required for validity in Java.

**“`@Repeatable` includes `@Inherited` by default.”** False. The two meta-annotations serve two independent mechanisms and must be chosen explicitly.

**“If a child class has its own `@Role`, Reflection will add the parent's `@Role` annotations.”** False. `getAnnotationsByType(Role.class)` uses the directly/indirectly present `Role` annotations on the child class if any exist, and does not automatically merge lists.

**“`getDeclaredAnnotationsByType` always equals `getAnnotationsByType`.”** False. The `ChildService` case in section 3 returns an empty array for the declared API, whereas the associated API returns two annotations from `BaseService`.

**“A child class implementing an interface with `@Role` inherits `@Role`.”** False. `@Inherited` does not follow `implements` relationships.

**“`@Inherited` makes a parent method's annotation appear on the overriding method.”** False. It only has inheritance semantics for annotations on classes in applicable APIs.

**“Simply calling `getAnnotation(Roles.class)` and reading `value()` is always the same as `getAnnotationsByType(Role.class)`.”** False when inheritance and direct/container annotations exist at different levels. The two queries ask two different questions.

**“`@Roles({})` definitely blocks inherited `Role` annotations.”** False. The verified example in section 3 shows that querying `getAnnotationsByType(Role.class)` still finds `Role` annotations on the parent class if the empty container on the child class produces no `Role` elements.

**“`@Inherited` allows Reflection to read `CLASS` annotations.”** False. `@Retention(RUNTIME)` remains a necessary condition for standard Java Reflection APIs to read annotations at runtime.

**“If you want to combine parent and child annotations, Java provides a built-in merge operation.”** False. Merging is a custom business policy and must be programmed explicitly.

## 13. Self-Check Exercises

### Exercise 1 — Predict the Inherited List

Given:

```java
@Role("A")
@Role("B")
class ParentA {}

class ChildA extends ParentA {}

@Role("C")
class ChildB extends ParentA {}
```

Assume the `Role`/`Roles` pair has been defined as in section 2. Predict:

- `ParentA.class.getAnnotationsByType(Role.class)`
- `ChildA.class.getAnnotationsByType(Role.class)`
- `ChildB.class.getAnnotationsByType(Role.class)`
- `ChildB.class.getDeclaredAnnotationsByType(Role.class)`

**Hint:** `[A, B]`, `[A, B]`, `[C]`, `[C]`, respectively.

### Exercise 2 — Why Must the Container Have @Inherited?

Remove `@Inherited` from the `Roles` definition while keeping `@Inherited` on `Role`. Should you wait until Reflection runs to discover the error?

**Answer:** no. This is an **invalid** repeatable annotation configuration and must be rejected by the compiler at the type declaration step.

### Exercise 3 — Annotations on Interfaces

If `interface Feature` has `@Role("feature")`, and `class Consumer implements Feature` does not declare its own `Role`, does `Consumer.class.getAnnotationsByType(Role.class)` contain `feature`?

**Answer:** no. `@Inherited` only considers the appropriate superclass relationship and does not automatically inherit annotations from implemented interfaces.

### Exercise 4 — Declared vs. Associated

Why is `ChildService.class.getDeclaredAnnotationsByType(Role.class)` empty while `ChildService.class.getAnnotationsByType(Role.class)` has two elements?

**Answer:** `declared` reads only on the current class itself, whereas `getAnnotationsByType` considers the `@Inherited` rule when there are no directly/indirectly present elements of the requested type.

### Exercise 5 — Empty Container

For `@Roles({}) class EmptyContainerService extends BaseService` in section 3, predict the number of elements returned by:

```java
EmptyContainerService.class.getDeclaredAnnotationsByType(Role.class).length
EmptyContainerService.class.getAnnotationsByType(Role.class).length
```

**Answer:** `0` and `2`. An empty container array does not necessarily block looking up `Role` from the parent class.

### Exercise 6 — Overridden Methods

`Parent.act()` has two `@Flag` annotations, while `OverrideChild.act()` overrides it without any `@Flag`. Does querying `getAnnotationsByType(Flag.class)` on the overriding method see the two annotations from `Parent.act()`?

**Answer:** no. `@Inherited` does not inherit method annotations.

### Exercise 7 — Combining Configurations

You want to always retrieve every `Role` from `DocumentEditor`, `DocumentBase`, and other superclasses, even when the child has its own `Role`. Should you use a single call to `DocumentEditor.class.getAnnotationsByType(Role.class)`?

**Answer:** no. Traverse superclasses explicitly, calling `getDeclaredAnnotationsByType(Role.class)` at each level, and then merge them according to your application's precedence and deduplication policy.

## 14. Checklist Before Using Inherited Repeatable Annotations

1. **Is the repeated/container pair correct?** Are `@Repeatable(Container.class)` and `Repeated[] value()` exact?
2. **Do both have `@Inherited` when the repeatable annotation uses it?** Avoid compiler errors and misconceptions about the container.
3. **Do both have sufficient retention to be read via Reflection?** For runtime, usually both are `RUNTIME`.
4. **Are the targets compatible?** If the annotation is for classes, configure matching `TYPE` targets for the pair.
5. **Reading a list or reading a single annotation?** For repeatable annotations, prefer `getAnnotationsByType` if you want all annotations according to standard rules.
6. **Want only declarations on the current class?** Use `getDeclaredAnnotationsByType`.
7. **Expecting child and parent to merge automatically?** Not by default; if needed, you must program your own algorithm.
8. **Are interfaces or overridden methods involved?** `@Inherited` does not automatically inherit annotations in those places.
9. **Are there empty containers or explicit containers?** Check the actual results of the APIs being used; do not infer from source syntax.
10. **Have you tested all cases: no declaration on child, child declaring one annotation, child declaring multiple annotations, and an empty container?** These cases clearly distinguish the semantics.

**Conclusion:** `@Repeatable` solves using multiple annotations of the same type and requires a container with `Repeated[] value()`; `@Inherited` governs looking up annotations along a class's superclass hierarchy. When combined, the container must be declared appropriately, and `getAnnotationsByType` generally **prioritizes the current class's annotations rather than appending to the parent class's**. Thoroughly understanding the direct, indirect, and associated variants helps avoid subtle bugs in Reflection as well as in framework metadata design.
