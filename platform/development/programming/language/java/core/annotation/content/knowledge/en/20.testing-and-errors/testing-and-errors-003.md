# Testing Inheritance, Shadowing, and Annotation Lookup APIs in Java

## 1. Why Test Annotation Lookup?

When a Java system uses annotations to select configuration, validation, access permissions, or processing strategies, **simply checking “whether an annotation is present” is not enough**. The result can vary depending on:

- Whether the annotation has **`@Retention(RUNTIME)`**.
- Whether the annotation type has **`@Inherited`**.
- Whether the annotation is placed on a **class, interface, or method**.
- Whether the annotation is **directly on the element**, looked up from a **superclass**, or **repeated via a container** with `@Repeatable`.
- Whether the code uses **`getAnnotation`**, **`getDeclaredAnnotation`**, **`getAnnotationsByType`**, **`getDeclaredAnnotationsByType`**, or general array-returning APIs.

A typical mistake is assuming a subclass always receives the parent's configuration and then *accumulates* it with its own configuration. In reality, `@Inherited` has specific **precedence/shadowing** rules. With repeatable annotations, `getAnnotation` can even return the value from the parent, while `getAnnotationsByType` returns the child's values on the very same class.

This lesson guides you through designing a **test case matrix**, running a Java 17+ example without external libraries, and accurately interpreting each reflection result.

## 2. Four Annotation Relationships to Distinguish

According to Java SE's `java.lang.reflect.AnnotatedElement`, four terms have distinct meanings:

| Term | Condition |
| --- | --- |
| **Directly present** | The runtime metadata of the element itself contains an annotation of that type |
| **Indirectly present** | The element directly contains the **container annotation** of a `@Repeatable`, and the target annotation is inside the container's `value()` |
| **Present** | A directly present annotation, or one looked up from a **superclass** according to `@Inherited` rules on a class when there is no directly present annotation of the same type |
| **Associated** | A directly or indirectly present annotation, or one looked up from a superclass according to `@Inherited` when there is neither a directly **nor indirectly** present annotation of the same type on the current class |

“Indirectly present” **does not mean** “inherited from a parent”; it refers specifically to the container mechanism of repeatable annotations. Meanwhile, “inherited” is accounted for under *present* or *associated* under specific conditions.

### API Mapping Table

| API | Relationship Type Read | Unpacks Container? | Has `@Inherited` Inheritance Mechanism? |
| --- | --- | --- | --- |
| `getDeclaredAnnotation(T.class)` | **Directly present** | No | No |
| `getAnnotation(T.class)` | **Present** | No | Yes, only for applicable class queries |
| `getDeclaredAnnotationsByType(T.class)` | **Directly + indirectly present** | Yes | No |
| `getAnnotationsByType(T.class)` | **Associated** | Yes | Yes, only for applicable class queries |
| `getDeclaredAnnotations()` | All **directly present** annotations | Does not automatically unpack containers | No |
| `getAnnotations()` | All **present** annotations | Does not automatically unpack containers | Yes, per applicable rules |
| `isAnnotationPresent(T.class)` | Checks **present** | Does not unpack containers | Same as `getAnnotation(T.class) != null` |

**API selection rule:** when an annotation is repeatable, prefer the **`ByType`** methods to retrieve all values; when you need to distinguish declarations **of the class itself** from inherited configuration, use the **`Declared`** family.

An easily overlooked detail: `getAnnotation(T.class)` returns only **one** annotation of type `T`, so it cannot return all repeatable values contained indirectly.

## 3. What Does @Inherited Actually Inherit?

Declaring an inherited annotation:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Policy {
    String value();
}
```

Applying it to a parent class:

```java
@Policy("base")
class Base {}

class Child extends Base {}
```

On `Child.class`, `getAnnotation(Policy.class)` can find `Policy("base")` from `Base` because `Policy` has `@Inherited`. However, `Child.class.getDeclaredAnnotation(Policy.class)` returns `null`: the subclass **does not directly declare** that annotation.

Important limitations:

1. `@Inherited` only affects annotation lookup on a **class declaration**, and only along the **superclass** chain.
2. Annotations declared on an **interface** are not automatically propagated to a class that `implements` the interface.
3. `@Inherited` does **not** cause an annotation placed on a parent method to be automatically applied to an **overriding method** in a subclass.
4. It does not extend to fields, constructors, or parameters.
5. `@Inherited` is unrelated to whether a class is loaded, instantiated, or invoked: it is a **rule during metadata lookup**, not an automatic runtime action.

`@Retention(RUNTIME)` is a necessary condition if you want to read it via reflection. An annotation with `@Inherited` but the default `CLASS` retention is still not returned by reflection APIs in the way used by the runtime examples below.

### What Does “Shadowing” Mean in This Problem?

In this lesson, *shadowing/precedence* refers to **the lookup rules for annotations of the same type within a class hierarchy**, and is not identical to **field hiding**, **method overriding**, **variable shadowing**, or **classloader visibility** in the Java language.

Example:

```java
@Policy("base")
class Base {}

@Policy("child")
class Child extends Base {}
```

When querying `Child.class.getAnnotation(Policy.class)`, the result is `"child"` because the subclass's annotation is directly present. `@Inherited` does not turn the result into a list `["base", "child"]`.

If you want to **manually merge configurations** across multiple class levels, the library must traverse `getSuperclass()` itself and apply its own designed merge rules. The default APIs do not automatically solve business-level merging.

## 4. Repeatable Annotations: The Difference Most Worth Testing

Suppose an annotation is repeatable:

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

`Role` has `@Repeatable(Roles.class)`, and `Roles` is the container with the element `Role[] value()`. To define a valid repeatable annotation, the retention and target of the container must be compatible. When the repeatable type has `@Inherited`, the container must also carry `@Inherited`. Setting **the same `RUNTIME` retention, `TYPE` target, and `@Inherited`** is the clear choice in this example.

### 4.1. Subclass Does Not Declare Role

```java
@Role("base-role")
class Base {}

class Inherits extends Base {}
```

For `Inherits`:

- `getDeclaredAnnotation(Role.class)`: `null`, because there is no directly present `Role`.
- `getDeclaredAnnotationsByType(Role.class)`: empty array, because there is no directly or indirectly present `Role`.
- `getAnnotation(Role.class)`: finds `"base-role"` from the parent class via `@Inherited`.
- `getAnnotationsByType(Role.class)`: array containing `"base-role"`, thanks to associated inheritance.

### 4.2. Subclass Declares One Role

```java
@Role("child-role")
class Overrides extends Base {}
```

Both `getAnnotation(Role.class)` and `getAnnotationsByType(Role.class)` on `Overrides.class` prioritize the subclass's own annotation. `"base-role"` is **not automatically added** to the array.

### 4.3. Subclass Declares TWO Roles — The Surprising Case

```java
@Role("alpha")
@Role("beta")
class RepeatedChild extends Base {}
```

The compiler represents the two `@Role` annotations on `RepeatedChild` through the **container `@Roles`**. Therefore:

- `RepeatedChild.class.getDeclaredAnnotation(Role.class)` returns `null`: there is no single `Role` directly present; the **container** is directly present.
- `RepeatedChild.class.getDeclaredAnnotation(Roles.class)` is **not null**.
- `RepeatedChild.class.getDeclaredAnnotationsByType(Role.class)` returns `["alpha", "beta"]`.
- `RepeatedChild.class.getAnnotationsByType(Role.class)` also returns `["alpha", "beta"]`, **without adding** `"base-role"`, because the two `Role` annotations are already indirectly present on the subclass.
- However, **`RepeatedChild.class.getAnnotation(Role.class)` can return `Role("base-role")` inherited from Base**: in terms of *present*, the subclass has no directly present `Role`, even though it has a container holding two indirectly present `Role` annotations.

Essential takeaway: **`getAnnotation(Role.class)` and `getAnnotationsByType(Role.class)` can observe values from two different levels on the same class**. This is not a compiler bug; it is the exact consequence of the difference between *present* and *associated*.

This scenario should definitely be included in **regression tests** if your library allows repeating inheritable annotations.

## 5. Distinguishing Annotations on Classes, Interfaces, and Overridden Methods

### Subclass Implements an Interface

```java
@Policy("interface")
interface TaskContract {}

class ImplementsTask implements TaskContract {}
```

`ImplementsTask.class.getAnnotation(Policy.class)` returns `null` if the class does not have `@Policy` from an eligible superclass. **`@Inherited` does not look up annotations on an interface that a class `implements`**.

### Overridden Methods

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

class Base {
    @MethodMark
    public void run() {}
}

class Overrides extends Base {
    @Override
    public void run() {}
}
```

Reflection with:

```java
Overrides.class.getDeclaredMethod("run")
        .isAnnotationPresent(MethodMark.class)
```

returns `false`, because an overriding method is a new method declaration and `@Inherited` does not automatically copy annotations from the parent method to the child method.

**A distinction when using reflection:** if the subclass **does not override** `run`, `Inherits.class.getMethod("run")` can return the exact `Method` declared on `Base`. The annotation observed then is the annotation on **the Base method**, **not because @Inherited applies to methods**. Check `method.getDeclaringClass()` to understand the exact source of the metadata.

The snippets in sections 3–5 are standalone illustrative examples; section 6 combines all components into **one truly runnable file**, avoiding collisions between classes with the same names across the snippets.

## 6. Complete Java 17+ Program: Verified Lookup Matrix

Create the file **AnnotationLookupTest.java** with the following content. The program uses only Java SE APIs and requires no external libraries; it tests **single-annotation inheritance**, **subclass annotation precedence**, **repeatable annotations + containers**, **method overriding**, and **interfaces not participating in inheritance**.

```java
import java.lang.annotation.*;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policy {
    String value();
}

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

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

@Policy("base")
@Role("base-role")
class Base {
    @MethodMark
    public void run() {}
}

class Inherits extends Base {}

@Policy("child")
@Role("child-role")
class Overrides extends Base {
    @Override
    public void run() {}
}

@Role("alpha")
@Role("beta")
class RepeatedChild extends Base {}

@Policy("interface")
interface TaskContract {}

class ImplementsTask implements TaskContract {}

public class AnnotationLookupTest {
    static String roles(Class<?> type) {
        return Arrays.stream(type.getAnnotationsByType(Role.class))
                .map(Role::value)
                .collect(Collectors.joining(",", "[", "]"));
    }

    static String policy(Policy p) {
        return p == null ? "null" : p.value();
    }

    static String role(Role r) {
        return r == null ? "null" : r.value();
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        System.out.println("inherit policy="
                + policy(Inherits.class.getAnnotation(Policy.class)));
        System.out.println("inherit declared="
                + policy(Inherits.class.getDeclaredAnnotation(Policy.class)));
        System.out.println("inherit roles=" + roles(Inherits.class));

        System.out.println("override policy="
                + policy(Overrides.class.getAnnotation(Policy.class)));
        System.out.println("override roles=" + roles(Overrides.class));

        Method method = Overrides.class.getDeclaredMethod("run");
        System.out.println("override method mark="
                + method.isAnnotationPresent(MethodMark.class));

        System.out.println("repeated declared role="
                + role(RepeatedChild.class.getDeclaredAnnotation(Role.class)));
        System.out.println("repeated container="
                + (RepeatedChild.class.getDeclaredAnnotation(Roles.class) != null));
        System.out.println("repeated present role="
                + role(RepeatedChild.class.getAnnotation(Role.class)));
        System.out.println("repeated associated=" + roles(RepeatedChild.class));
        System.out.println("repeated declared by type="
                + RepeatedChild.class.getDeclaredAnnotationsByType(Role.class).length);

        System.out.println("interface inherited="
                + policy(ImplementsTask.class.getAnnotation(Policy.class)));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 AnnotationLookupTest.java
java AnnotationLookupTest
```

Exact stdout:

```text
inherit policy=base
inherit declared=null
inherit roles=[base-role]
override policy=child
override roles=[child-role]
override method mark=false
repeated declared role=null
repeated container=true
repeated present role=base-role
repeated associated=[alpha,beta]
repeated declared by type=2
interface inherited=null
```

This is actual output **verified by running with `javac --release 17`**, not fabricated data based on API names. The `null` string is printed intentionally via helpers to avoid a `NullPointerException` when an annotation is not found.

### Interpreting Each Result Group

1. **`Inherits`** does not declare `Policy` or `Role`, yet `@Inherited` allows non-`Declared` APIs to look them up on `Base`. `getDeclaredAnnotation(Policy.class)` is `null`.
2. **`Overrides`** directly declares `@Policy("child")` and `@Role("child-role")`, so its own values shadow the parent's values of the same types in the corresponding lookup results.
3. `Overrides.run()` overrides `Base`'s method without automatically inheriting `@MethodMark`. Simply marking the annotation type with `@Inherited` **does not change that rule**.
4. **`RepeatedChild`** declares two Roles; the `Roles` container is present, while `Role` is not directly present. Therefore, `getDeclaredAnnotation(Role.class) == null`, whereas `getDeclaredAnnotation(Roles.class) != null`.
5. **Notable divergence case:** `getAnnotation(Role.class)` returns `base-role`, whereas `getAnnotationsByType(Role.class)` returns `alpha,beta` by unpacking the container on the subclass without merging roles from the parent.
6. **`ImplementsTask`** does not automatically receive `@Policy("interface")`, because `@Inherited` does not look up annotations on implemented interfaces.

Together, these cases protect code against two mistakes: **calling an API unsuitable for the intended purpose** and **misunderstanding shadowing rules when an annotation becomes repeatable**.

## 7. Converting the Example into Automated Tests Without Libraries

Printing to stdout helps with quick inspection, but continuous testing requires **pass/fail conditions**. For a project not using JUnit, Java SE can report failures directly via `AssertionError` when the result differs from expectations:

```java
// You can add this method to AnnotationLookupTest:
static void check(boolean ok, String description) {
    if (!ok) {
        throw new AssertionError(description);
    }
}
```

Then place the checks inside `main`:

```java
check(Inherits.class.getDeclaredAnnotation(Policy.class) == null,
        "Inherited annotation không phải declared annotation");

check("base".equals(
        Inherits.class.getAnnotation(Policy.class).value()),
        "Class con phải đọc được inherited Policy");

check(RepeatedChild.class.getDeclaredAnnotation(Role.class) == null,
        "Role lặp không trực tiếp có mặt");

check(RepeatedChild.class.getDeclaredAnnotationsByType(Role.class).length == 2,
        "Phải đọc được hai Role qua container");

check("base-role".equals(
        RepeatedChild.class.getAnnotation(Role.class).value()),
        "getAnnotation dùng present/inherited semantics");

check("[alpha,beta]".equals(roles(RepeatedChild.class)),
        "getAnnotationsByType dùng associated semantics");

check(!Overrides.class.getDeclaredMethod("run")
        .isAnnotationPresent(MethodMark.class),
        "@Inherited không tự áp dụng cho method override");
```

This is an **add-on snippet** that should be placed into the same `AnnotationLookupTest` class from section 6, not a standalone Java file. If a condition fails, the program throws an `AssertionError` and the process terminates with a non-zero exit code, making it suitable for CI.

Do not confuse this with Java's `assert` keyword: when using an `assert condition;` statement, **`-ea`** must be enabled when running the JVM for the assertion to be executed. The `check` helper explicitly calls `throw new AssertionError`, so it does not depend on the `-ea` flag.

### Both Negative Cases and Data Sources Should Be Tested

Merely seeing `getAnnotation(...) != null` does not prove whether the annotation came from the class itself or a superclass. A good test suite needs at least one `getDeclaredAnnotation(...) == null` check and one check that a non-`Declared` API returns the expected value. For repeatable annotations, you must test `getDeclaredAnnotationsByType`, `getAnnotationsByType`, and the container as well.

For methods, you should check `getDeclaringClass()` when using `getMethod` to distinguish a parent method inherited for accessibility from an actual overriding method.

## 8. Recommended Test Case Matrix for a Project

| Test Case | Setup | API to Observe | Expected Condition |
| --- | --- | --- | --- |
| Direct annotation | `@Policy("base")` on class | `getAnnotation`, `getDeclaredAnnotation` | Both read `base` |
| Single-annotation inheritance | Child has no Policy, parent has one | `getAnnotation`, `getDeclaredAnnotation` | `base` and `null` |
| Shadowing on subclass | Child has `@Policy("child")` | `getAnnotation` | `child`, not automatically merged with `base` |
| Annotation not marked with `@Inherited` | Only parent has it, child does not | `getAnnotation` on child | `null` |
| Annotation placed on interface | Class `implements` interface with Policy | `getAnnotation` on class | `null`, unless another source has Policy |
| Annotation on overridden method | Parent has `@MethodMark`, child overrides without annotating | `getDeclaredMethod(...).getAnnotation` | `null` |
| Inherited method without override | Child does not declare `run` | `getMethod(...).getDeclaringClass` | Returns the class declaring the method, which may be Base |
| Single occurrence of repeatable annotation | One direct `@Role` | `getDeclaredAnnotation(Role.class)` | Finds the Role |
| Two occurrences of repeatable annotation | Two `@Role` on the same class | `getDeclaredAnnotation(Role.class)` | `null` because it is via container |
| Two annotations via container | Two `@Role` | `getDeclaredAnnotationsByType` | Two-element array in the correct order |
| Child has two Roles, parent has one Role | `RepeatedChild` | `getAnnotation(Role.class)` | Can observe **the parent's** value |
| Same case, associated lookup | `RepeatedChild` | `getAnnotationsByType(Role.class)` | Two Roles **from the child**, without accumulating the parent's |
| `CLASS` retention | Annotation does not declare Retention | Runtime reflection | Does not appear via runtime APIs |
| Subclass with no Roles | `Inherits` | `getAnnotationsByType(Role.class)` | Inherits Role from Base if the type is inheritable |

**Test design note:** Test at least **0 / 1 / multiple values** for repeatable annotations, **with and without `@Inherited`**, class/interface/method targets, and **the Declared family versus non-Declared APIs**. These are independent testing dimensions; checking only one method on one class easily misses defects.

## 9. What Does “Shadowing” Mean When Merging Annotations from Parent and Child?

Distinguish between two policies a library might choose:

### A. Default Java Reflection Policy

If you need **the nearest effective configuration**, `getAnnotationsByType(Role.class)` under associated semantics prioritizes the `Role` annotations directly or indirectly present on the current class. Only when the current class has no `Role` of that type is the superclass consulted, provided `Role` has `@Inherited`.

For example, if the child has `alpha` and `beta`, the default result **does not contain** `base-role`.

### B. Custom Policy: Merging Across Multiple Classes

A framework might want: “collect all roles from `Base` to `RepeatedChild`, deduplicate them, let the child override roles with the same key, and preserve precedence order”. This is an **application rule**; it cannot be derived from the default `getAnnotationsByType`.

The implementation must clearly decide:

1. Whether to traverse `getSuperclass()` from child to parent or from parent to child.
2. On **each class**, call `getDeclaredAnnotationsByType(Role.class)` to read **only** the metadata attached to that class, avoiding accidentally double-counting inherited annotations.
3. Define the distinguishing key and override policy when duplicate values exist.
4. Determine whether interfaces are considered; Java `@Inherited` by default does **not** consider interfaces.
5. Test repeatable containers and the ordering of values.

Conceptual algorithm example (not a standalone runnable file):

```java
for (Class<?> current = target;
     current != null;
     current = current.getSuperclass()) {

    Role[] local = current.getDeclaredAnnotationsByType(Role.class);
    for (Role role : local) {
        // Insert the role into a custom data structure and apply merge rules.
    }
}
```

Do not use `getAnnotationsByType` to iterate through each level and blindly sum everything up, because that API may have **already inherited** data from a superclass and cause duplicate counting. If higher privileges on a subclass or a deny/allow policy are required, test the security impact of the merge rules rather than treating every annotation as an inherently trustworthy directive.

## 10. Testing in a Way That Avoids Implementation Coupling

### 10.1. Read Actual Values, Do Not Parse toString

Use `policy.value()` and `role.value()`; do not parse `annotation.toString()`. The `toString()` string is a human-readable representation, not a standard format for asserting ordering, type names, or serialization.

### 10.2. Test with the Right Retention

If you omit `@Retention(RUNTIME)` from `Policy`, the annotation defaults to `CLASS`. Runtime checks like `getAnnotation(Policy.class)` will no longer reflect what is attached in source; do not mistake that for an inheritance bug.

When using runtime repeatable annotations, the **container** must also have a compatible retention, typically `RUNTIME`, so that `ByType` APIs can access it.

### 10.3. Distinguish Class Declaration Annotations from Type-Use Annotations

This lesson tests annotations **on class declarations** using `Class.getAnnotationsByType`. Annotations with `@Target(TYPE_USE)` can be placed on **a type being used**, such as a variable, generic parameter, or supertype use. They are typically read through `AnnotatedType` and its corresponding reflection APIs, rather than simply substituting `Class.getAnnotation`.

If an inheritance test does not see a type-use annotation placed on `extends @SomeAnnotation Base`, first verify that you are calling the right API (`getAnnotatedSuperclass()`) and using the right retention/target, rather than treating `@Inherited` for declaration annotations as the solution.

### 10.4. Be Careful with Multiple Classloaders

Two annotation types with the same string name loaded by two different classloaders can be two different `Class` objects. `getAnnotation(SomeAnnotation.class)` requires **the exact annotation type** attached in the runtime metadata. In plugin/modular applications, test classloader boundaries separately if applicable.

### 10.5. Do Not Rely on the Ordering of Heterogeneous getAnnotations()

`getAnnotationsByType(Role.class)` follows rules that preserve the order of Role annotations inside the container. However, **the ordering of all annotations of different types in `getAnnotations()`** should not be treated as a stable source format for driving business logic. Use set comparisons or type names if you only need presence.

## 11. Common Pitfalls and How to Spot Them

**1. Using `getDeclaredAnnotation` and concluding `@Inherited` does not work.** Declared methods intentionally return only directly present annotations; compare with `getAnnotation` when verifying inherited behavior.

**2. Thinking `@Inherited` applies to interfaces.** Java does not automatically look up annotations on implemented interfaces.

**3. Thinking `@Inherited` applies to method overrides.** A parent method's annotation is not automatically attached to an overriding declaration in a subclass.

**4. Thinking `getMethod()` retrieving an inherited method means the method annotation was inherited.** `getMethod()` can return the `Method` object declared in Base; check `getDeclaringClass()`.

**5. Using `getAnnotation(Role.class)` to find all Roles.** With a repeatable container, this API does not unpack the list of Roles; use `getAnnotationsByType`.

**6. Assuming `getAnnotation(Role.class)` and `getAnnotationsByType(Role.class)` always agree on the source of an annotation.** When the child has two Roles in a container and the parent has a direct Role, the two APIs can return different content according to *present* and *associated* semantics.

**7. Assuming `getAnnotationsByType` always merges parent and child.** When the child has a Role directly or indirectly, the child's associated result prioritizes the local values.

**8. Omitting `@Inherited` on the container.** If a repeatable annotation is marked `@Inherited`, the container must satisfy compatibility rules; matching target and retention is the configuration to use in this lesson.

**9. Forgetting `RUNTIME` retention.** An annotation may exist in source or class files yet be unreadable via runtime APIs.

**10. Comparing `toString()` strings to verify configuration.** Check typed accessors, counts, and `Declared` positions rather than string formatting.

**11. Testing everything with a single boolean result.** A boolean does not tell you whether the annotation came from the current class, a superclass, or a container; you need to check multiple APIs and actual values.

**12. Accidentally using an annotation type with the same name from another package.** `getAnnotation` takes the `Class<T>` object of the exact annotation interface, not just the type's simple name.

**13. Forgetting the “no annotation” case.** Always check for `null` on single-object APIs and zero-length arrays on `ByType` APIs; do not assume every query returns data.

## 12. Hands-On Exercises and Expanding the Test Suite

1. **Add a grandchild level:** Declare `class GrandChild extends Inherits {}`. Try `getAnnotation(Policy.class)`, `getDeclaredAnnotation(Policy.class)`, and `getAnnotationsByType(Role.class)`; explain how the lookup traces back to Base along the superclass chain.
2. **Create per-type shadowing:** Place `@Policy("child-only")` on a subclass without placing `Role`. Verify that each annotation type applies inheritance rules independently.
3. **Make Role non-inheritable:** Remove `@Inherited` from both `Role` and `Roles`; rerun the tests and record what changes. Distinguish direct/indirect from inherited.
4. **Explicit container:** Replace the two `@Role` annotations on `RepeatedChild` with `@Roles({@Role("alpha"), @Role("beta")})`. Compare `getDeclaredAnnotation(Roles.class)` and `getDeclaredAnnotationsByType(Role.class)`.
5. **Single Role on subclass:** Change `RepeatedChild` to have only `@Role("alpha")`. Predict `getDeclaredAnnotation(Role.class)` and `getAnnotation(Role.class)`; explain the difference compared to having two Roles.
6. **Intentional role merging:** Write a function that traverses `getSuperclass()` and calls `getDeclaredAnnotationsByType(Role.class)`; define parent-first or child-first ordering; test that there is no duplicate counting.
7. **Inherited method:** Use `Inherits.class.getMethod("run")`, print `getDeclaringClass().getSimpleName()`, and compare the found annotation with `Overrides.class.getDeclaredMethod("run")`.
8. **Interface lookup:** Define a framework policy that allows retrieving annotations from interfaces; write code to traverse `getInterfaces()` and compare it with Java's default behavior.
9. **CLASS retention:** Try removing RUNTIME retention from Policy, predict the difference between source code and reflection, then restore it.
10. **JUnit 5:** If the project already has JUnit, convert the `check(...)` calls into `assertNull`, `assertEquals`, and `assertArrayEquals` with test names that accurately describe the metadata source; no production API changes are needed.
11. **Order verification:** Swap `@Role("alpha") @Role("beta")` to the reverse order and confirm that the `ByType` array reflects the order stored in the container.
12. **Java-version regression:** Run the same test across the JDKs supported by your project; avoid depending on `getAnnotations()` ordering across different annotation types or `toString()` strings to prevent false positives.

## 13. Official Documentation

- [AnnotatedElement — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): defines directly present, indirectly present, present, associated, and how the APIs map to each relationship type.
- [Inherited — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): scope of class annotation inheritance, not applicable to implemented interfaces or method annotations.
- [Repeatable — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): declaring repeatable annotations and containers.
- [Class — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): the `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType`, and `getDeclaredAnnotationsByType` methods.
- [Method — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): looking up metadata on methods and distinguishing inherited methods from overridden ones.

**In summary:** To test annotation lookup accurately, you must distinguish **annotations on the declaration itself**, **inheritance via a superclass**, and **repeatable annotations inside a container**. `getAnnotation` and `getAnnotationsByType` are not interchangeable when `@Repeatable` is involved. Use the Declared APIs to identify values belonging to the class itself, add tests for shadowing, method overrides, and interfaces, and write custom merge logic when business requirements go beyond Java's `@Inherited` rules.
