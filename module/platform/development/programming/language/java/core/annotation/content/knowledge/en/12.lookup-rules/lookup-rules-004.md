# `getAnnotationsByType` vs. `getDeclaredAnnotationsByType` in Java

## 1. The Problem: "Having an Annotation" and "Declaring an Annotation Itself" Are Different

Both methods on the `java.lang.reflect.AnnotatedElement` interface accept **an annotation type** and return **an array of annotations of that type**:

```java
<A extends Annotation> A[] getAnnotationsByType(Class<A> annotationClass);
<A extends Annotation> A[] getDeclaredAnnotationsByType(Class<A> annotationClass);
```

These are **simplified signatures for explanation**, not two method declarations you need to write yourself. In real Java code, you invoke them on reflective objects such as `Class<?>`, `Method`, `Field`, `Constructor<?>`, or `Parameter`.

They are similar in that they:

- Return an `A[]` array and **do not return `null`** when no matching annotation is found.
- Support **repeatable annotations**: retrieve both direct annotations and annotations indirectly contained in a *container annotation* according to Java rules.
- Require metadata with a retention policy suitable for reflection, typically `@Retention(RetentionPolicy.RUNTIME)` on the annotation type and the container when it is a repeatable annotation.

They differ in query scope:

- `getDeclaredAnnotationsByType(A.class)` only retrieves annotations of type `A` **directly or indirectly contained on the element itself**.
- `getAnnotationsByType(A.class)` retrieves annotations of type `A` **associated** with the element. For a **class** and an annotation with `@Inherited`, it can also search up the superclass hierarchy when the current class has no `A` annotation directly or indirectly contained.

An easy mnemonic is **`Declared` = on the current declaration**. The notable extension of the method without `Declared` relates to **inheritance via a class's superclass**, rather than every kind of relationship between Java elements.

## 2. Where the Two APIs Sit in `AnnotatedElement`

`AnnotatedElement` is the common interface for inspecting annotations on a reflective element. Methods that are easily confused with one another:

| Method | Result | Repeatable Container Handling | Can Consider `@Inherited` on Class |
|---|---|---|---|
| `getAnnotation(A.class)` | A single `A` or `null` | **Does not unwrap** the `A[]` container | Yes, following the *present* rule |
| `getDeclaredAnnotation(A.class)` | A single `A` or `null` | **Does not unwrap** the container | No |
| `getAnnotationsByType(A.class)` | An `A[]` array | **Yes**, retrieves indirectly contained `A`s | Yes, following the *associated* rule |
| `getDeclaredAnnotationsByType(A.class)` | An `A[]` array | **Yes**, but on the element itself | No |
| `getAnnotations()` | An `Annotation[]` array | Does not automatically replace the container with a list of `A` | Yes, under the *present* rule |
| `getDeclaredAnnotations()` | An `Annotation[]` array | Does not automatically replace the container with a list of `A` | No |

`getAnnotationsByType` is **not merely a plural version** of `getAnnotation`. It understands the relationship between a repeatable annotation and the container declared with `@Repeatable`. Meanwhile, `getAnnotation(A.class)` only queries for a single annotation of type `A` under the *present* rule and can return `null` even when multiple `@A` annotations are inside a container.

Example:

```java
A[] all = element.getAnnotationsByType(A.class);
A[] local = element.getDeclaredAnnotationsByType(A.class);
```

Here, `element` is an `AnnotatedElement`, and `A` is a validly defined annotation type. If you need to retrieve **all repeated annotations of a given type**, the two `ByType` methods are a better choice than iterating over `getAnnotations()` and manually casting.

## 3. Why Do Both Methods Read Annotations Inside a Container?

Suppose we define:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

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
```

And attach two annotations on the same class:

```java
@Label("stable")
@Label("reviewed")
class ReleaseService {}
```

The compiler uses an implicit container to represent multiple `@Label` annotations at this location, equivalent in value to:

```java
@Labels({@Label("stable"), @Label("reviewed")})
class ReleaseService {}
```

The two class declaration snippets above are **two alternative ways of writing it**; do not combine both into the same file.

On `ReleaseService.class`:

```java
Label[] a = ReleaseService.class.getAnnotationsByType(Label.class);
Label[] b = ReleaseService.class.getDeclaredAnnotationsByType(Label.class);
```

Both `a` and `b` contain two elements with `value` in the order `"stable"`, `"reviewed"`, because the two `Label` annotations are **indirectly contained directly on that class itself**. `@Inherited` is not needed for this case.

In contrast:

```java
Label one = ReleaseService.class.getAnnotation(Label.class);
Labels container = ReleaseService.class.getAnnotation(Labels.class);
```

When **two** `@Label` annotations are contained via `@Labels`, `one` is `null` while `container` is non-`null`. That does not mean the `Label` annotations were lost; you queried using an API that only looks for a single *present* `Label` instead of an API that understands the repeatable mechanism.

## 4. Key Difference: `@Inherited` Inheritance from a Superclass

`@Inherited` belongs to `java.lang.annotation`. If an annotation type has the `@Inherited` meta-annotation and `RUNTIME` retention, then when looking up annotations on a **class**, the Java Reflection API can search up the superclass hierarchy.

A valid definition for an inherited repeatable annotation:

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
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}
```

**Important:** When the repeatable annotation `Tag` carries `@Inherited`, the container `Tags` must also carry `@Inherited` per Java's constraints. The container must also have a retention policy at least as long as the repeatable annotation's; in this example, both are `RUNTIME` so that reflection can observe them.

The classes:

```java
@Tag("parent-a")
@Tag("parent-b")
class Parent {}

class Child extends Parent {}
```

Querying on `Child.class`:

```java
Tag[] associated = Child.class.getAnnotationsByType(Tag.class);
Tag[] declared = Child.class.getDeclaredAnnotationsByType(Tag.class);
```

Result:

- `associated`: the two tags `"parent-a"`, `"parent-b"` found via the superclass `Parent`.
- `declared`: **empty array**. `Child` declares neither `@Tag` nor the container `@Tags` on itself.

This is the most important scenario where the two APIs produce different results.

### What if the Subclass Declares Its Own Annotation?

```java
@Tag("local")
class ChildWithOwnTag extends Parent {}
```

When `ChildWithOwnTag.class` already has a direct `@Tag`, `getAnnotationsByType(Tag.class)` returns **`"local"`** and does not automatically add `"parent-a"` and `"parent-b"`. `getDeclaredAnnotationsByType(Tag.class)` also returns `"local"`.

**Practical takeaway:** `getAnnotationsByType` is not a function that "collects every tag across the entire class hierarchy." It follows the *associated* rule: when the current class has directly present or indirectly contained `Tag` annotations, the result on that class takes precedence; only when there is no `Tag` on the current class and the annotation type permits inheritance does searching the superclass take effect.

If business logic requires *merging* tags from all superclasses, the program must implement its own inheritance-tree traversal algorithm and a dedicated merge rule.

## 5. Three Scenarios to Distinguish When Inspecting a Class

| Scenario | `getAnnotationsByType(Tag.class)` | `getDeclaredAnnotationsByType(Tag.class)` |
|---|---|---|
| Class declares a single `@Tag` on itself | One tag on the class | One tag on the class |
| Class declares two `@Tag` annotations on itself (implicit container) | Two tags on the class | Two tags on the class |
| Class declares no tags, but superclass has tags with `@Inherited` | Eligible tags from the superclass | Empty array |
| Class declares tags on itself and superclass also has tags | Tags on the class itself, not merged with the superclass by default | Tags on the class itself |
| Class declares no tags, superclass has tags **without** `@Inherited` | Empty array | Empty array |
| Class declares no tags and none are found on the superclass | Empty array | Empty array |

The table assumes the annotation and container have `RUNTIME` retention, valid declarations, and queries performed on **`Class<?>`**.

A subclass can inherit metadata from **the nearest superclass that has eligible associated annotations**, rather than concatenating results from every parent class by default. This is a distinction worth noting when implementing authorization policies, class classification, or annotation-driven configuration.

## 6. Complete Java 17+ Example: Running and Comparing the Two APIs

Create a file named **`ByTypeLookupDemo.java`** with the following content:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Method;
import java.util.Arrays;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}

@Label("base-A")
@Label("base-B")
class BaseService {}

class ChildService extends BaseService {}

@Label("local")
class OverrideService extends BaseService {}

@Labels({@Label("explicit-A"), @Label("explicit-B")})
class ExplicitService {}

@Label("single")
class SingleService {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Repeatable(Tasks.class)
@interface Task {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Tasks {
    Task[] value();
}

class ParentMethods {
    @Task("parent-1")
    @Task("parent-2")
    public void run() {}
}

class ChildMethods extends ParentMethods {
    @Override
    public void run() {}
}

public class ByTypeLookupDemo {
    private static String labels(Label[] labels) {
        String[] values = Arrays.stream(labels)
                .map(Label::value)
                .toArray(String[]::new);
        return Arrays.toString(values);
    }

    private static void inspect(String name, AnnotatedElement element) {
        Label[] associated = element.getAnnotationsByType(Label.class);
        Label[] declared =
                element.getDeclaredAnnotationsByType(Label.class);
        System.out.println(name + " associated=" + labels(associated)
                + " declared=" + labels(declared));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        inspect("Base", BaseService.class);
        inspect("Child", ChildService.class);
        inspect("Override", OverrideService.class);
        inspect("Explicit", ExplicitService.class);
        inspect("Single", SingleService.class);

        Method parentMethod = ParentMethods.class.getDeclaredMethod("run");
        Method childMethod = ChildMethods.class.getDeclaredMethod("run");

        System.out.println("ParentMethods.run tasks="
                + parentMethod.getAnnotationsByType(Task.class).length);
        System.out.println("ChildMethods.run tasks="
                + childMethod.getAnnotationsByType(Task.class).length);
    }
}
```

In the directory containing the file, using JDK 17 or newer:

```bash
javac ByTypeLookupDemo.java
java ByTypeLookupDemo
```

**Exact stdout:**

```text
Base associated=[base-A, base-B] declared=[base-A, base-B]
Child associated=[base-A, base-B] declared=[]
Override associated=[local] declared=[local]
Explicit associated=[explicit-A, explicit-B] declared=[explicit-A, explicit-B]
Single associated=[single] declared=[single]
ParentMethods.run tasks=2
ChildMethods.run tasks=0
```

Line-by-line explanation:

1. **Base:** two `@Label` annotations are declared directly on `BaseService`; both APIs return two values.
2. **Child:** declares no `@Label`; `getAnnotationsByType` looks up to `BaseService` because `Label` has `@Inherited`. `getDeclaredAnnotationsByType` only inspects `ChildService`, so it returns an empty array.
3. **Override:** the class has a direct `@Label("local")`. Both APIs see `"local"`; metadata on `BaseService` is not automatically appended.
4. **Explicit:** the `@Labels` container is written explicitly. Both `ByType` APIs unwrap the container's list of `Label` annotations.
5. **Single:** there is only a single direct `@Label` annotation; both APIs return one element.
6. **Method:** the `run()` method on `ParentMethods` contains two `Task` annotations. The overridden method in `ChildMethods` does not automatically inherit the parent method's annotations; `@Inherited` does not support method annotation inheritance either.

The example has no external framework dependencies, keeps the file name matching the public class `ByTypeLookupDemo`, and uses `RUNTIME`-retention annotations so reflection can read them.

## 7. Not Every Element Has Inheritance Rules

The two `ByType` methods belong to `AnnotatedElement`, so they can also be called on non-class element types:

```java
Method method = SomeClass.class.getDeclaredMethod("work");
Field field = SomeClass.class.getDeclaredField("id");
Constructor<?> ctor = SomeClass.class.getDeclaredConstructor();
```

These are illustrative snippets requiring a `SomeClass` and the corresponding declared members; if written as a full program, you must import `java.lang.reflect.Method`, `Field`, and `Constructor`, and handle the checked exceptions.

For **`Method`**, **`Field`**, **`Constructor`**, **`Parameter`**, or **`Package`**, there is no dedicated superclass-style `@Inherited` mechanism like there is for `Class<?>` objects. Therefore, the two `ByType` methods normally return the same directly present and indirectly contained annotations on **that element itself**.

Some common misconceptions:

- Subclass **overrides a method**: the new method does not automatically inherit annotations from the parent method.
- Subclass **does not override a method**: `Child.class.getMethod("work")` may return the `Method` object of the public method inherited from the superclass. Any annotations read are on **the reflected method**, not because `@Inherited` works on methods.
- Class **implements an interface**: an `@Inherited` annotation on an interface does not automatically become an annotation on the implementing class.
- **Package/subpackage**: a subpackage does not inherit annotations from a parent package.
- Annotations in **type-use positions** (*type use*): you need to query the appropriate `AnnotatedType` or corresponding reflective object; the two methods do not automatically search every annotation position in a type signature.

Consequently, the difference between the two `ByType` methods is not always visible. It only manifests clearly when choosing the right reflective object and an inheritance scenario.

## 8. `@Inherited` with Repeatable Containers: Check Both Annotation Types

When an annotation is repeatable, Java requires a *container annotation*:

```java
@Repeatable(Container.class)
@interface Item {
    String value();
}

@interface Container {
    Item[] value();
}
```

If you want to use `@Inherited` on `Item`, you must also place `@Inherited` on **the `Container` container**. Similarly, the container's retention must be at least equal to the repeatable annotation's retention. For reading via reflection, the simplest approach is to declare `RUNTIME` on both.

Incorrect configuration example:

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(BrokenItems.class)
@interface BrokenItem {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface BrokenItems {
    BrokenItem[] value();
}
```

This snippet **intentionally fails to compile** because `BrokenItem` has `@Inherited` while `BrokenItems` is missing `@Inherited`.

Fix it to:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface BrokenItems {
    BrokenItem[] value();
}
```

This is **a standalone replacement for the `BrokenItems` definition in the broken snippet**; do not place both duplicate-named declarations in the same file at the same time.

Additionally, if the repeatable annotation has `@Documented`, the container must also have `@Documented`. The return type of `Container.value()` must be strictly a one-dimensional array of the repeatable annotation, and any additional elements of the container must have a `default`.

These rules matter because `getAnnotationsByType` relies on a valid container mechanism to locate repeated annotations, while `@Inherited` determines when it continues searching on superclasses.

## 9. Distinguishing "Directly Present", "Indirectly Present", "Present", and "Associated"

The Java Reflection API uses terms with specific meanings:

- **Directly present:** an annotation of type `T` appears directly on the element.
- **Indirectly present:** `T` annotations residing inside a container annotation that Java recognizes as the container for the repeatable type `T`.
- **Present:** the relationship used by APIs such as `getAnnotation(T.class)`; includes directly present annotations and those that can be inherited on a class via `@Inherited`.
- **Associated:** the broader relationship used by `getAnnotationsByType(T.class)`; includes directly present, indirectly present, and class inheritance cases according to Java rules.

Therefore, the snippet:

```java
@Label("x")
@Label("y")
class C {}
```

can cause `C.class.getAnnotation(Label.class)` to return `null`, whereas `C.class.getAnnotationsByType(Label.class)` returns a two-element array. This is the expected result: the container holds the two `Label` annotations indirectly, and `getAnnotation` does not unwrap the container.

It is also necessary to distinguish "`Declared`" in its two forms:

- `getDeclaredAnnotation(Label.class)`: returns at most **one directly present `Label`**, without unwrapping the container.
- `getDeclaredAnnotationsByType(Label.class)`: returns **all directly present or indirectly contained `Label` annotations** on the element itself.

Therefore, the word `Declared` does **not** mean "only annotations written directly, excluding elements inside a container." When used with the `ByType` suffix, the container is still unwrapped to collect matching annotations.

## 10. When to Choose Which Method?

| Requirement | Recommended Method | Reason |
|---|---|---|
| Read all occurrences of a repeatable annotation, allowing class inheritance | `getAnnotationsByType(T.class)` | Understands containers and `@Inherited` |
| Read only annotations attached to the class itself, including repeated ones | `getDeclaredAnnotationsByType(T.class)` | Does not search superclasses |
| Read a non-repeatable annotation, allowing class inheritance | `getAnnotation(T.class)` | Returns a single annotation or `null` |
| Read a non-repeatable annotation, only on the class itself | `getDeclaredAnnotation(T.class)` | Queries direct declarations |
| Check whether an annotation exists without needing its value | `isAnnotationPresent(T.class)` for a single *present* annotation; or `getAnnotationsByType(T.class).length > 0` for repeatable annotations | `isAnnotationPresent` does not unwrap repeatable containers |
| Retrieve all different annotation types in raw form | `getAnnotations()` / `getDeclaredAnnotations()` | Suitable for general inspection; does not automatically unwrap repeatables |

A method used in tools/frameworks:

```java
static <A extends java.lang.annotation.Annotation>
A[] readLocal(java.lang.reflect.AnnotatedElement element,
              Class<A> annotationType) {
    return element.getDeclaredAnnotationsByType(annotationType);
}
```

This is a syntactically complete helper **when placed inside an appropriate class**. It lets consumers choose to retrieve all repeated annotations while inspecting only the current element.

The version that accepts inheritance:

```java
static <A extends java.lang.annotation.Annotation>
A[] readAssociated(java.lang.reflect.AnnotatedElement element,
                   Class<A> annotationType) {
    return element.getAnnotationsByType(annotationType);
}
```

Both helpers have the same return type; the difference lies in the semantics of the underlying API called. Neither should be named `findAll` without describing its scope.

## 11. Common Mistakes

### Mistake 1 — Using `getAnnotation` to Read Repeated Annotations

```java
Label label = BaseService.class.getAnnotation(Label.class);
```

If `BaseService` has two `@Label` annotations, `label` is `null` because they reside inside a container. You must use `getAnnotationsByType(Label.class)` to receive a two-element array.

### Mistake 2 — Using `getDeclaredAnnotationsByType` and Concluding the Superclass Has No Metadata

With `ChildService extends BaseService` declaring no tags, `getDeclaredAnnotationsByType(Label.class)` returns `[]` even though `BaseService` has two tags. If you want to allow inheritance, use `getAnnotationsByType(Label.class)` and ensure the annotation type has `@Inherited`.

### Mistake 3 — Assuming `getAnnotationsByType` Always Merges All Parent Classes

If the subclass has already declared a tag, the result is the matching tag on the subclass; it does not combine all parent tags by default. To accumulate metadata across the entire superclass hierarchy, you must explicitly traverse it and apply precedence/merging rules.

### Mistake 4 — Missing `@Inherited` or Placing It Only on the Repeatable Annotation

Without `@Inherited`, `getAnnotationsByType` on a subclass will not automatically look up annotations from the superclass. For a repeatable annotation to support `@Inherited`, both the repeatable annotation and its container must meet the coordination requirements, including having `@Inherited` on the container.

### Mistake 5 — Missing `@Retention(RUNTIME)`

If an annotation only has `CLASS` or `SOURCE` retention, reflection cannot read it even though `@T` appears in the source code. Proper `RUNTIME` retention is required, along with recompiling the classes that use the annotation.

### Mistake 6 — Reading the Wrong Element

If an annotation is placed on a method, retrieve the annotation from the `Method` object rather than calling `SomeClass.class.getAnnotationsByType(...)` and expecting to see method annotations. If the annotation is placed on a package, query `Package`; if on a type-use position, use the appropriate `AnnotatedType`.

### Mistake 7 — Treating an Empty Array as `null`

`getAnnotationsByType` and `getDeclaredAnnotationsByType` return an empty array when there are no matching annotations. The standard check is:

```java
Label[] labels = type.getAnnotationsByType(Label.class);
if (labels.length == 0) {
    System.out.println("No labels");
}
```

`type` is a valid `Class<?>`. Do not use `if (labels == null)` to check for "no labels".

### Mistake 8 — Ignoring Explicit Containers

If a class uses an explicit container:

```java
@Labels({@Label("a"), @Label("b")})
class ContainerOnly {}
```

`getDeclaredAnnotationsByType(Label.class)` must still retrieve both `Label` annotations via the repeatable mechanism. There is no need to manually call `getAnnotation(Labels.class)` and extract `value()` when you only want to read the `Label` annotations.

## 12. Self-Check Questions

Consider the following configuration (illustrative snippet only; the annotations have `RUNTIME` retention):

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Modes.class)
@interface Mode {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Modes {
    Mode[] value();
}

@Mode("A")
@Mode("B")
class Root {}

class Mid extends Root {}

@Mode("C")
class Leaf extends Mid {}
```

Determine:

1. How many elements does `Root.class.getAnnotationsByType(Mode.class)` have?
2. How many elements does `Root.class.getDeclaredAnnotationsByType(Mode.class)` have?
3. What values does `Mid.class.getAnnotationsByType(Mode.class)` return?
4. What values does `Mid.class.getDeclaredAnnotationsByType(Mode.class)` return?
5. What values does `Leaf.class.getAnnotationsByType(Mode.class)` return?
6. What values does `Leaf.class.getDeclaredAnnotationsByType(Mode.class)` return?
7. Does `Root.class.getAnnotation(Mode.class)` return one of the two `Mode` annotations?
8. If `@Inherited` is removed from both `Mode` and `Modes` and the code is recompiled, what does `Mid.class.getAnnotationsByType(Mode.class)` receive?
9. If `Mode` has `RUNTIME` retention while `Modes` is left at the default `CLASS`, is the repeatable configuration valid?
10. Is the annotation lookup result on an overridden method determined by `Mode`'s `@Inherited`?

Answers and explanations:

1. **Two:** `A` and `B`, which are directly/indirectly present annotations on `Root`.
2. **Two:** the declarations are directly on `Root`.
3. **Two:** `A`, `B`, inherited via the superclass since `Mid` has no `Mode` of its own.
4. **Empty array:** `Mid` declares neither `Mode` nor the container on itself.
5. **One:** `C`; direct metadata on `Leaf` takes precedence over `A`, `B` from `Root`.
6. **One:** `C` is declared on `Leaf`.
7. **No:** the two `Mode` annotations are contained in the container, so `getAnnotation(Mode.class)` does not unwrap the list.
8. **Empty array:** there is no `@Inherited` mechanism for `Mode`, and `Mid` has no direct annotation.
9. **No:** the container cannot have a shorter retention than the repeatable annotation.
10. **No:** `@Inherited` only applies to annotations on class declarations via superclasses; it does not copy annotations of overridden methods.

## 13. Project Application Checklist

- Choose `getAnnotationsByType` when you need both repeatable containers **and** inherited annotations allowed on classes.
- Choose `getDeclaredAnnotationsByType` when you only need metadata on the element itself but still want to unwrap repeatable containers.
- Remember that `getAnnotation`/`getDeclaredAnnotation` returns a single annotation or `null` and does not unwrap containers.
- Verify that both the annotation and the container have an appropriate retention policy, typically `RUNTIME` for reflection.
- If class inheritance is expected, define both the repeatable annotation and its container with `@Inherited`.
- Do not confuse class annotation inheritance with annotations on overridden methods, fields, interfaces, or packages.
- Do not expect `getAnnotationsByType` to automatically merge all annotations from every superclass when the subclass already has values on itself.
- Handle the result as an **array**, even when empty; do not check for `null`.
- Query the exact `AnnotatedElement` object corresponding to where the annotation is actually attached.
- Test all cases: a single `@T`, multiple `@T`s, an explicit container, an empty subclass, and a subclass with its own `@T`.
- When changing the retention or metadata of a repeatable/container pair, recompile the sources that use the annotation and verify the reflection result on the actual artifact.

Reference documentation: [`AnnotatedElement` in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html) and [`@Inherited` in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html).

Understanding the boundary between **associated** and **declared** helps you choose the right API: both collect repeated annotations via the container mechanism, while the difference in inheritance mainly appears when querying `@Inherited` annotations on a **class**.
