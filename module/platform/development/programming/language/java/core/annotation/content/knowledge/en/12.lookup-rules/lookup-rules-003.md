# `getAnnotations()` vs. `getDeclaredAnnotations()` in Java Reflection

## 1. The Problem: “Having an Annotation” Differs from “Declaring an Annotation Directly”

In Java, an annotation is metadata attached to a declaration or a type-use site. To look up annotations at **runtime**, Java provides the `java.lang.reflect.AnnotatedElement` interface. Objects reflecting a class, method, field, constructor, parameter, and many other elements can use the methods of this interface.

Two important APIs:

- **`getAnnotations()`**: returns the annotations **present** on the queried element. For **`Class`**, the set of present annotations may include annotations from superclasses via `@Inherited`.
- **`getDeclaredAnnotations()`**: returns the annotations **directly present** on **that element itself**. This API ignores annotations that are only present through inheritance.

These are two **no-argument** methods that both return `java.lang.annotation.Annotation[]`:

~~~java
Annotation[] all = SomeClass.class.getAnnotations();
Annotation[] declared = SomeClass.class.getDeclaredAnnotations();
~~~

The core difference is **not** “reading public annotations” versus “reading private annotations”, nor is it “reading everything in the Java tree” versus “reading only each individual class under every kind of inheritance”. It is the difference between **present** and **directly present** according to the `AnnotatedElement` contract.

Both methods return an **empty array** when there are no matching annotations, rather than returning `null`. To look up a specific annotation type, use the singular or `...ByType` APIs presented below.

## 2. Quick Comparison Table

| Aspect | `getAnnotations()` | `getDeclaredAnnotations()` |
|---|---|---|
| Return value | `Annotation[]` | `Annotation[]` |
| Meaning | Annotations *present* on the element | Annotations *directly present* on the element |
| On a class with `@Inherited` on the annotation type | May include annotations from superclasses | Does not receive annotations present only on superclasses |
| Superclass annotations **without** `@Inherited` | Not automatically retrieved | Not automatically retrieved |
| Annotations on `implements` interfaces | Not automatically retrieved via `@Inherited` | Not automatically retrieved |
| Annotations on an overriding method | Not automatically retrieved from the overridden method | Not automatically retrieved |
| **Inherited** method/field that has not been overridden/hidden | Reflects only the annotations of the `Method`/`Field` object actually being queried | Same; the object itself may be a method/field from a parent class |
| `@Repeatable` annotation applied multiple times | Raw array may contain the *container annotation* | Raw array may contain the *container annotation* |
| No results | Zero-length array | Zero-length array |
| Requirement for runtime reflection | Annotation requires `@Retention(RUNTIME)` to appear | Same |

**The scope of `@Inherited` is very narrow:** it only applies to querying annotations **on a class** along the **superclass chain**; it does not turn annotations on methods, fields, or interfaces into automatically inherited annotations.

Another point: `getAnnotations()` and `getDeclaredAnnotations()` do not guarantee annotation order matching the order written in source code. If stable output is needed for tests or display, you should **sort** by name/type instead of assuming a specific array order.

## 3. Basic Example: Annotation on a Superclass

Consider the following condensed program:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalOnly {}

@Region("base")
@LocalOnly
class Base {}

class Child extends Base {}
~~~

`Child` does not directly declare any annotations. However, for `@Region`, the annotation type is marked with `@Inherited`:

~~~java
Region inherited = Child.class.getAnnotation(Region.class);
Region local = Child.class.getDeclaredAnnotation(Region.class);

System.out.println(inherited.value()); // base
System.out.println(local == null);       // true
~~~

When called on `Child.class`:

- `getAnnotations()` contains **`@Region("base")`** because `Region` allows lookup along the superclass.
- `getDeclaredAnnotations()` is an **empty array** because the header of `Child` does not declare any annotations.
- `@LocalOnly` is not returned by `getAnnotations()` on `Child` because its annotation type does **not** have `@Inherited`.
- `Base.class.getAnnotations()` and `Base.class.getDeclaredAnnotations()` both see the two annotations `Region` and `LocalOnly` declared directly on `Base`.

If `Child` declares its own:

~~~java
@Region("child")
class ChildWithOwnRegion extends Base {}
~~~

then `ChildWithOwnRegion.class.getAnnotation(Region.class).value()` returns `"child"`. A directly declared annotation of the same type is selected instead of the annotation found from the superclass. Java **does not merge element values** of the child annotation with the parent annotation.

### 3.1. The `@Retention(RUNTIME)` Requirement

An annotation type needs `RUNTIME` retention for its results to be visible via reflection at runtime. If `@Retention` is omitted, the default is `RetentionPolicy.CLASS`; metadata may be stored in the `.class` file, but that does not mean runtime reflection APIs will see that annotation.

`@Inherited` does **not** automatically change retention. An annotation with `@Inherited` whose retention is not `RUNTIME` will not automatically appear when calling `Class.getAnnotations()` at runtime.

## 4. With Multiple Levels of Inheritance

Given the chain:

~~~java
@Region("root")
class Root {}

class Middle extends Root {}

class Leaf extends Middle {}
~~~

`Leaf.class.getAnnotation(Region.class)` can find `@Region("root")` along the chain `Leaf -> Middle -> Root`. If `Middle` declares `@Region("middle")`, queries from `Middle` and `Leaf` receive `"middle"` unless `Leaf` declares that annotation itself.

However, calling `getDeclaredAnnotation(Region.class)` or `getDeclaredAnnotations()` on `Leaf.class` does **not automatically look** into `Middle` or `Root`: only the direct metadata of `Leaf` is examined.

When using `getAnnotations()`, the result is the **set of annotations present per type**, not a list of every occurrence of the same annotation type across all parent classes. If you need to track annotations at **each level** for migration, policy inheritance, or auditing, manually traverse each `getSuperclass()` and call `getDeclaredAnnotations()` accordingly; do not use `getAnnotations()` and then infer the history of all classes.

Example illustrating a level-by-level inspection algorithm (independent of the `Main.java` program below):

~~~java
for (Class<?> c = Leaf.class; c != null; c = c.getSuperclass()) {
    System.out.println(c.getName());
    for (var annotation : c.getDeclaredAnnotations()) {
        System.out.println("  " + annotation.annotationType().getName());
    }
}
~~~

The algorithm above lists annotations on **each class**, including annotations without `@Inherited`. This is **intentional in the manual superclass-traversal code**, not a default capability of `getAnnotations()`.

## 5. `@Inherited` Does Not Work Through Interfaces

Suppose:

~~~java
@Region("api")
interface Api {}

class Implementation implements Api {}
~~~

Even though `Region` has `@Inherited`, neither of the following two queries on the `Implementation` class sees `@Region("api")`:

~~~java
Implementation.class.getAnnotations();         // does not contain Region from Api
Implementation.class.getDeclaredAnnotations(); // does not contain Region from Api
~~~

`@Inherited` only supports **a class inheriting from a superclass**. It **does not search interfaces**, even when an interface is annotated with an annotation that has `@Target(TYPE)` and `@Inherited`. A **subinterface** also does not automatically receive annotations from its parent interface through the `@Inherited` mechanism.

If a framework wants to consider annotations on interfaces, it must define and execute its own **interface hierarchy traversal rule**; that is not the default contract of `Class.getAnnotations()`.

## 6. Why Does an Overriding Method Not “Inherit Annotations”?

An **overriding** method in a subclass is a new declaration. `@Inherited` does not copy annotations from the parent method to the overriding method, even if you place `@Inherited` on an annotation type intended for methods.

~~~java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Checked {}

class Base {
    @Checked
    public void work() {}
}

class Child extends Base {
    @Override
    public void work() {}
}
~~~

For `Child.work()`:

~~~java
var method = Child.class.getDeclaredMethod("work");

System.out.println(method.getAnnotations().length);         // 0
System.out.println(method.getDeclaredAnnotations().length); // 0
~~~

For the **method in Base**:

~~~java
var method = Base.class.getDeclaredMethod("work");

System.out.println(method.isAnnotationPresent(Checked.class)); // true
~~~

Both APIs on the `Method` object query the annotations of **the very method declaration that the object reflects**. `getAnnotations()` **does not search for** annotations on the overridden method in the superclass. To apply `@Checked` to the overriding method, place it explicitly on that method or build a reflection policy that manually traverses the hierarchy by matching signatures.

### 6.1. Common Pitfall: `getMethod()` Can Return the Inherited Method Itself

In the case where `Child` **does not override**:

~~~java
class ChildWithoutOverride extends Base {}
~~~

When calling:

~~~java
var method = ChildWithoutOverride.class.getMethod("work");
System.out.println(method.getDeclaringClass().getSimpleName()); // Base
System.out.println(method.isAnnotationPresent(Checked.class)); // true
~~~

`Class.getMethod("work")` searches for an eligible public method and can return the `Method` object declared in `Base`. In that case, both `method.getAnnotations()` and `method.getDeclaredAnnotations()` see the annotation declared **directly on `Base.work()` itself**.

Thus, **annotations do not propagate from the parent method to the child method**; the `method` variable simply points to the **parent method**. Check `Method.getDeclaringClass()` to avoid drawing the wrong conclusion.

The same rule applies to inherited fields: `Child.class.getField("name")` can return the `Field` object declared in the superclass. If a subclass creates a new field with the same name to **hide** the old field, the two fields are two declarations, and annotations are not automatically copied to the new field.

## 7. `getAnnotations()` Is Not `getMethods()` or `getDeclaredMethods()`

Two axes must be distinguished:

**Axis 1 — selecting the member to query:**

- `Class.getMethod("work")` finds the appropriate public method, which may include an inherited method.
- `Class.getDeclaredMethod("work")` only finds a method actually declared on the current class.
- `Class.getField("id")` and `Class.getDeclaredField("id")` also differ in whether they look up inherited fields.

**Axis 2 — looking up metadata on the selected member:**

- `method.getAnnotations()` inspects annotations *present* on the `Method` object.
- `method.getDeclaredAnnotations()` inspects annotations *directly present* on the represented method itself.

The name `getDeclaredAnnotations` does not mean it automatically looks up members via `getDeclaredMethod`. Each API performs a **different step**. When debugging, log `getDeclaringClass()` to see which declaration the reflection object actually belongs to.

## 8. Repeatable Annotations: Why Is the Array Result Sometimes a Container Annotation?

An annotation type can be allowed to repeat multiple times on a single declaration using `@Repeatable`:

~~~java
import java.lang.annotation.*;

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

@Tag("alpha")
@Tag("beta")
class ParentTags {}

class ChildTags extends ParentTags {}
~~~

The two `@Tag` annotations placed on `ParentTags` can be represented as a single **container annotation `@Tags`** in metadata. When calling:

~~~java
Annotation[] raw = ParentTags.class.getDeclaredAnnotations();
~~~

In this example, the `raw` array contains **`Tags`** (the container) instead of two separate `Tag` objects. For `ChildTags`:

- `ChildTags.class.getAnnotations()` can contain `Tags` **inherited from ParentTags**; here both `Tag` and the container `Tags` have `@Inherited`.
- `ChildTags.class.getDeclaredAnnotations()` remains empty because `ChildTags` does not directly declare any annotations.
- `ChildTags.class.getAnnotationsByType(Tag.class)` returns **two `Tag`s** after accounting for repeatable/container handling and inheritance.
- `ChildTags.class.getDeclaredAnnotationsByType(Tag.class)` returns an empty array because there is no `Tag` directly or indirectly present (via a directly declared container) on Child.

This is an important point: **`getAnnotations()` does not automatically unpack all repeatable annotations into individual elements of the original annotation type**. Choose a `...ByType` API when you need the annotations of a repeatable type.

According to Java rules, if a repeatable annotation type uses `@Inherited`, the annotation type used as its container must also satisfy the corresponding constraints. Therefore, the sample intentionally marks **both `Tag` and `Tags` with `@Inherited`**.

### 8.1. The Four Singular and `ByType` APIs

| API | Returns | Characteristics |
|---|---|---|
| `getAnnotation(Tag.class)` | `Tag` or `null` | A single annotation type directly present/present per the API; does not automatically unpack multiple `Tag`s in a container |
| `getDeclaredAnnotation(Tag.class)` | `Tag` or `null` | Only the **directly present** annotation type |
| `getAnnotationsByType(Tag.class)` | `Tag[]` | Automatically recognizes repeatable annotations and unpacks containers, applying the appropriate association/inheritance rules |
| `getDeclaredAnnotationsByType(Tag.class)` | `Tag[]` | Automatically recognizes repeatable/container annotations **declared on the element**, without taking annotations from superclasses |

If a class has two `@Tag` annotations, `getAnnotation(Tag.class)` in the example can return `null` because the direct metadata is the **`@Tags` container**; however, `getAnnotationsByType(Tag.class)` returns both values. `getAnnotation(Tags.class)` can read the container directly.

**Do not confuse `getDeclaredAnnotationsByType` with `getDeclaredAnnotations`:** the first supports unpacking repeatable containers, while the second returns the raw array of annotations on the declaration.

When a subclass declares its own `Tag` of the same type as an inherited annotation, the selection of `@Repeatable` annotations based on `associated`/`indirectly present` follows specific rules; do not assume `getAnnotationsByType` always concatenates all annotations across every parent-child level.

## 9. Complete Runnable Java 17+ Example

Save the entire content below to **Main.java**. The example sorts annotation names alphabetically so that the output does not depend on the array order returned by reflection.

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface Region {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Inherited
@interface Checked {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface Tags {
    Tag[] value();
}

@Region("base")
@LocalOnly
class Base {
    @Checked
    public void work() {}
}

class Child extends Base {}

@Region("own")
class OwnChild extends Base {}

class OverrideChild extends Base {
    @Override
    public void work() {}
}

@Tag("alpha")
@Tag("beta")
class ParentTags {}

class ChildTags extends ParentTags {}

public class Main {
    static String names(Annotation[] values) {
        String result = Arrays.stream(values)
                .map(a -> a.annotationType().getSimpleName())
                .sorted()
                .collect(Collectors.joining(","));
        return result.isEmpty() ? "-" : result;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("base.all="
                + names(Base.class.getAnnotations()));
        System.out.println("child.all="
                + names(Child.class.getAnnotations()));
        System.out.println("child.declared="
                + names(Child.class.getDeclaredAnnotations()));
        System.out.println("child.region="
                + Child.class.getAnnotation(Region.class).value());
        System.out.println("child.region.declared="
                + (Child.class.getDeclaredAnnotation(Region.class) != null));
        System.out.println("own.region="
                + OwnChild.class.getAnnotation(Region.class).value());

        System.out.println("inherited.method.owner="
                + Child.class.getMethod("work")
                        .getDeclaringClass().getSimpleName());
        System.out.println("inherited.method.checked="
                + Child.class.getMethod("work")
                        .isAnnotationPresent(Checked.class));
        System.out.println("override.method.checked="
                + OverrideChild.class.getMethod("work")
                        .isAnnotationPresent(Checked.class));

        System.out.println("tags.parent.raw="
                + names(ParentTags.class.getAnnotations()));
        System.out.println("tags.child.raw="
                + names(ChildTags.class.getAnnotations()));
        System.out.println("tags.child.declared="
                + names(ChildTags.class.getDeclaredAnnotations()));
        System.out.println("tags.child.byType="
                + ChildTags.class.getAnnotationsByType(Tag.class).length);
        System.out.println("tags.child.declaredByType="
                + ChildTags.class.getDeclaredAnnotationsByType(Tag.class).length);
        System.out.println("tags.parent.getAnnotation.Tag="
                + (ParentTags.class.getAnnotation(Tag.class) != null));
    }
}
~~~

From the directory containing `Main.java`, compile and run:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Expected output:

~~~text
base.all=LocalOnly,Region
child.all=Region
child.declared=-
child.region=base
child.region.declared=false
own.region=own
inherited.method.owner=Base
inherited.method.checked=true
override.method.checked=false
tags.parent.raw=Tags
tags.child.raw=Tags
tags.child.declared=-
tags.child.byType=2
tags.child.declaredByType=0
tags.parent.getAnnotation.Tag=false
~~~

Explanation:

1. `base.all=LocalOnly,Region`: both direct annotations have runtime retention.
2. `child.all=Region`: `@Region` is looked up via the superclass because of `@Inherited`; `@LocalOnly` is not looked up via the superclass.
3. `child.declared=-` and `child.region.declared=false`: `Child` does not directly declare any annotations.
4. `own.region=own`: the direct annotation on `OwnChild` is used instead of `@Region("base")` on the superclass.
5. `inherited.method.owner=Base` and `inherited.method.checked=true`: `Child.class.getMethod("work")` returns the method in Base, so it reads the annotations of that method itself.
6. `override.method.checked=false`: `OverrideChild.work()` is a new declaration and does not automatically receive `@Checked` from Base even though `Checked` is marked with `@Inherited`.
7. `tags.parent.raw=Tags`: the two repeated `Tag` annotations are stored/represented via the `Tags` container.
8. `tags.child.raw=Tags`, `tags.child.declared=-`: the inherited container can be reflected through `getAnnotations()`, but it is not an annotation declared on ChildTags.
9. `tags.child.byType=2`, `tags.child.declaredByType=0`: the `ByType` API unpacks the container and handles inheritance, whereas `DeclaredByType` only considers annotations directly/indirectly present on ChildTags.
10. `tags.parent.getAnnotation.Tag=false`: the singular form does not automatically unpack the container into multiple `Tag`s.

## 10. Other Misconceptions to Avoid

### 10.1. “Declared” Does Not Mean “Public Only”

`getDeclaredAnnotations()` **does not filter by `public`, `private`, or `protected` modifiers**. It distinguishes the origin of metadata on an element, not access privileges. A private method can still carry annotations, and `getDeclaredMethod` can still return the `Method` object for a private method.

### 10.2. “getAnnotations()” Does Not Scan All Superclass Members

The fact that a class's `getAnnotations()` sees an inherited `@Region` **does not mean** every `Field` or `Method` of the class automatically receives annotations from the superclass. For members, inspect `getDeclaringClass()` and distinguish inherited methods from overriding methods.

### 10.3. Superclass Annotations Do Not Appear When `@Inherited` Is Missing

With the standard runtime APIs, the annotation type must be marked with `@Inherited` for class-level annotations from a superclass to be discovered via `getAnnotations()`. Add `@Retention(RUNTIME)` so reflection can see the metadata at runtime. If you need to access annotations from all parent classes **regardless of `@Inherited`**, you must traverse them manually and use `getDeclaredAnnotations()` on each class.

### 10.4. Annotations on Interfaces Do Not Automatically Appear on Implementing Classes

`@Inherited` does not govern interface hierarchies. Frameworks may define deeper annotation lookup strategies, but that is **framework** logic, not the default behavior of `Class.getAnnotations()`.

### 10.5. The Count in `getAnnotations().length` Differs from the Number of Tags Written in Source

With `@Repeatable`, the array from `getAnnotations()` may contain a single **container** representing multiple annotations of the same type. When you need all repeated annotations, use `getAnnotationsByType()`.

### 10.6. Annotations Visible in Source Code Cannot Be Read at Runtime

If an annotation type uses `SOURCE` or `CLASS` retention, runtime reflection will not necessarily see it. `@Target` determines where an annotation can be applied, whereas `@Retention` determines the metadata retention lifecycle.

### 10.7. Confusing Declaration Annotations with Type-Use Annotations

`getAnnotations()` called directly on a `Field`/`Method` primarily works with **declaration annotations**. If an annotation has `@Target(TYPE_USE)` and is placed **on the field's type** or **the method's return type**, use `getAnnotatedType()` or `getAnnotatedReturnType()` and read metadata from the corresponding `AnnotatedType`.

Example:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface CheckedType {}

class Example {
    @CheckedType String name;
}
~~~

To check the annotation on the **field's type**, use:

~~~java
var field = Example.class.getDeclaredField("name");
boolean exists = field.getAnnotatedType()
        .isAnnotationPresent(CheckedType.class);
~~~

Do not rely solely on `field.getAnnotations()` and conclude that the type-use annotation is absent.

### 10.8. Modifying the Returned Array Does Not Modify Metadata

The APIs that return annotation arrays do not grant the ability to modify annotations on a class or method. For example, setting `result[0] = null` only changes the caller's local array; subsequent reflection calls still follow the metadata of the running class.

## 11. Checklist for Choosing the Right API

- **Want to read all declaration annotations *present* on a class, considering `@Inherited`?** Choose `clazz.getAnnotations()`.
- **Only want annotations declared by this exact class?** Choose `clazz.getDeclaredAnnotations()`.
- **Only interested in a single annotation type?** Choose `getAnnotation(Foo.class)` or `getDeclaredAnnotation(Foo.class)`; the singular form returns `null` if not found.
- **Can the annotation be repeated?** Choose `getAnnotationsByType(Foo.class)` or `getDeclaredAnnotationsByType(Foo.class)` to unpack containers.
- **Reading an inherited method or field?** Print `getDeclaringClass()`; distinguish `getMethod` from `getDeclaredMethod`.
- **Want to read metadata from interfaces or all superclasses even without `@Inherited`?** Define your own hierarchy traversal algorithm and override/precedence policy.
- **Is the annotation on a type argument, return type, or field type?** Query `AnnotatedType`, and do not confuse it with a declaration.
- **Cannot see the annotation at runtime?** Check `@Retention(RUNTIME)`, `@Target`, the API being used, and the reflection object being queried.

## 12. Official References

- [Java SE 17 — `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): defines **present**, **directly present**, **associated**, **indirectly present**, and the `ByType` APIs.
- [Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getAnnotations`, `getDeclaredAnnotations`, `getMethod`, and `getDeclaredMethod` on a class.
- [Java SE 17 — `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): limits annotation inheritance to classes and superclasses.
- [Java SE 17 — `java.lang.annotation.Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): repeatable annotation and container mechanism.
- [JLS Java SE 17 `9.6.4.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3): formal semantics of `@Inherited`.

**Remember:** `getAnnotations()` returns **present** annotation metadata, which for classes may include annotations found from superclasses when the annotation type has `@Inherited`. `getDeclaredAnnotations()` returns only metadata **directly** on the element. Neither API searches interfaces by default, propagates annotations across method overrides, or automatically unpacks every repeatable annotation inside a container; if different behavior is needed, choose the appropriate `ByType` API or implement specific lookup rules.
