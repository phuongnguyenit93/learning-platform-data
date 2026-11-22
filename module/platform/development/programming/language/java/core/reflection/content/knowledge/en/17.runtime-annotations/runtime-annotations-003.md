# getAnnotation, getDeclaredAnnotation, and isAnnotationPresent in Java Reflection

## 1. Goal: looking up annotations at runtime with the right scope

Annotations in Java are metadata attached to classes, interfaces, methods, fields, constructors, parameters, packages, or type-use sites, depending on the `@Target` declaration. Frameworks commonly use annotations to mark components, routers, converters, validation, transactions, mappings, and business rules. The three core APIs on `java.lang.reflect.AnnotatedElement` are:

- `<T extends Annotation> T getAnnotation(Class<T> annotationClass)`: retrieves the requested annotation type if it is **present** on the element according to Reflection rules; if absent, returns `null`.
- `<T extends Annotation> T getDeclaredAnnotation(Class<T> annotationClass)`: retrieves the requested annotation type **attached directly on the element** (directly present), without searching inherited annotations; if absent, returns `null`.
- `boolean isAnnotationPresent(Class<? extends Annotation> annotationClass)`: asks whether that annotation type is **present** on the element. By contract, the result is equivalent to `getAnnotation(annotationClass) != null`.

The biggest difference between `getAnnotation` and `getDeclaredAnnotation` appears with **annotations on classes that have `@Inherited`**. For many other elements, such as methods and fields, the two APIs usually produce the same result because Java **does not automatically inherit annotations of overridden methods or hidden fields**.

**Starting point:** for Reflection to read an annotation, that annotation must normally declare `@Retention(RetentionPolicy.RUNTIME)`. If the annotation only has `SOURCE` or `CLASS` retention, the three runtime APIs above do not return that annotation, even when `@MyMarker` appears in the source.

## 2. Conditions for the three APIs to read an annotation

The annotation must be retained with `@Retention(RetentionPolicy.RUNTIME)` and queried on the **exact element**. The default when `@Retention` is omitted is `CLASS`; runtime Reflection does not return usages of annotations that only have `SOURCE` or `CLASS` retention.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Feature { String name(); }
```

This is a fragment requiring `import java.lang.annotation.*`. `@Target(TYPE)` allows attaching `Feature` to a type declaration; querying `Method.getAnnotation(Feature.class)` will not find an annotation placed on a class. The dedicated retention lesson explains class-file visibility and `TYPE_USE` cases.

## 3. Which types use `AnnotatedElement` as a common interface?

`Class<?>`, `Method`, `Field`, `Constructor<?>`, `Parameter`, `Package`, `Module`, and several other Reflection objects implement or are viewed through `AnnotatedElement` (check the specific Java version for specialized types). This makes it possible to write utilities:

~~~java
import java.lang.annotation.Annotation;
import java.lang.reflect.AnnotatedElement;

// Illustrative fragment; place inside an appropriate class or method.
static <A extends Annotation> A findAnnotation(
        AnnotatedElement element, Class<A> type) {
    return element.getAnnotation(type);
}
~~~

The generic method preserves the exact annotation type in the return value: calling `findAnnotation(User.class, Feature.class)` yields return type `Feature`, with no raw cast needed. `getAnnotation` does **not** invoke business logic on the class/method; it only reads metadata. Reading annotations on a private method also **does not require `setAccessible(true)`**: permission to invoke a private method is separate from reading annotation metadata on a `Method` object already obtained via `getDeclaredMethod`.

Some examples of objects that must be chosen accurately:

- `SomeClass.class`: looks up annotations on the class.
- `SomeClass.class.getDeclaredMethod("run")`: looks up annotations on the directly declared method.
- `SomeClass.class.getDeclaredField("id")`: looks up annotations on the directly declared field.
- `SomeClass.class.getDeclaredConstructor()`: looks up annotations on the constructor matching the signature.
- `method.getParameters()[i]`: looks up annotations on the corresponding formal parameter.

Do not retrieve a parameter's annotation by calling `method.getAnnotation(ParamMarker.class)`: that call queries the **method**, not the method's parameter.

## 4. Distinguishing “directly present” and “present”

The terminology in `AnnotatedElement` matters more than the casual word “has”:

1. An annotation of type `A` is **directly present** on an element if the element's direct metadata contains annotation `A` (following the appropriate rules for repeatable annotations).
2. An annotation of type `A` is **present** if it is directly present; additionally, for a **class**, an annotation of type `A` marked `@Inherited` can be present by traversing the **superclass** chain when the class does not have annotation `A` directly.
3. `getDeclaredAnnotation(A.class)` checks only **directly present**; it does not search superclasses.
4. `getAnnotation(A.class)` checks **present**, so it can receive annotation `A` from a superclass if the `@Inherited` conditions are met.
5. `isAnnotationPresent(A.class)` is equivalent to `getAnnotation(A.class) != null`. It does **not** check only the declared level.

A common misconception: “`getDeclaredAnnotation` = look only in directly written methods, while `getAnnotation` = also search superclass methods.” **Incorrect.** Core Reflection's `@Inherited` mechanism only automatically searches annotations at the class level and the superclass chain of **that class**; it does not cause an overriding method to inherit annotations from its parent method.

### Quick table by element

| Situation | `getAnnotation(A.class)` | `getDeclaredAnnotation(A.class)` | `isAnnotationPresent(A.class)` |
| --- | --- | --- | --- |
| Class has `@A` directly, `A` has runtime retention | Returns `A` | Returns `A` | `true` |
| Subclass does not declare `@A`; superclass has `@A` and `A` has `@Inherited` | Can return inherited annotation | `null` | `true` |
| Subclass does not declare `@A`; superclass has `@A` but `A` lacks `@Inherited` | `null` | `null` | `false` |
| Overriding method does not have `@A`; parent method has `@A` | `null` on overriding method | `null` | `false` |
| Subclass field hides parent field without `@A` | `null` on subclass field | `null` | `false` |
| Annotation in source has `RetentionPolicy.CLASS` | `null` | `null` | `false` |
| Repeatable `@A` appears twice and is stored via container `@As` | Use `getAnnotationsByType(A.class)` to retrieve both annotations; `getAnnotation(A.class)` does not auto-unpack the container | Does not auto-unpack the container | Not a query for “is any A inside the container” |

## 5. How does `@Inherited` change results on a class?

Given an annotation type `Policy` with `@Inherited`, `@Retention(RUNTIME)`, and `@Target(TYPE)`, if `Base` carries `@Policy("base")` while `Child extends Base` does not declare `Policy`, `Child.class.getAnnotation(Policy.class)` sees `"base"` whereas `getDeclaredAnnotation(Policy.class)` returns `null`. If `Child` writes `@Policy("child")`, the local value takes precedence.

This rule searches only the **class's superclass chain**. Annotations on interfaces or overridden methods are not automatically copied; a non-overridden method can still be found via `getMethod` and carry the original superclass annotation. The lessons on `@Inherited` and on interfaces/methods cover those cases specifically. The complete example immediately below verifies both outcomes.

## 6. Complete Java 17+ program: comparing the three APIs

Save the file **`AnnotationLookupDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AnnotationLookupDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface LocalOnly {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Checked {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    @interface Column {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.CONSTRUCTOR)
    @interface Create {}

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

    @Role("base")
    @LocalOnly
    static class Base {
        @Column
        private int id;

        @Create
        Base() {}

        @Checked
        public void execute() {}

        @Checked
        public void unchanged() {}
    }

    static class Child extends Base {
        @Override
        public void execute() {}
    }

    @Role("child")
    static class ExplicitChild extends Base {}

    @Role("interface")
    interface MarkedInterface {}

    static class ImplementsInterface implements MarkedInterface {}

    @Label("one")
    @Label("two")
    static class MultipleLabels {}

    public static void main(String[] args) throws Exception {
        Role inherited = Child.class.getAnnotation(Role.class);
        System.out.println("child role=" + inherited.value());
        System.out.println("child declared role="
                + (Child.class.getDeclaredAnnotation(Role.class) != null));
        System.out.println("child has role="
                + Child.class.isAnnotationPresent(Role.class));
        System.out.println("child has local="
                + Child.class.isAnnotationPresent(LocalOnly.class));
        System.out.println("explicit child role="
                + ExplicitChild.class.getAnnotation(Role.class).value());
        System.out.println("interface role inherited="
                + ImplementsInterface.class.isAnnotationPresent(Role.class));

        Method overridden = Child.class.getDeclaredMethod("execute");
        Method inheritedMethod = Child.class.getMethod("unchanged");
        System.out.println("overridden method checked="
                + overridden.isAnnotationPresent(Checked.class));
        System.out.println("inherited method owner="
                + inheritedMethod.getDeclaringClass().getSimpleName());
        System.out.println("inherited method checked="
                + inheritedMethod.isAnnotationPresent(Checked.class));

        Field field = Base.class.getDeclaredField("id");
        Constructor<Base> constructor = Base.class.getDeclaredConstructor();
        System.out.println("field column="
                + (field.getDeclaredAnnotation(Column.class) != null));
        System.out.println("constructor create="
                + constructor.isAnnotationPresent(Create.class));

        System.out.println("repeatable getAnnotation="
                + (MultipleLabels.class.getAnnotation(Label.class) != null));
        System.out.println("repeatable container="
                + MultipleLabels.class.isAnnotationPresent(Labels.class));
        System.out.println("repeatable byType="
                + MultipleLabels.class.getAnnotationsByType(Label.class).length);
        System.out.println("repeatable declaredByType="
                + MultipleLabels.class
                    .getDeclaredAnnotationsByType(Label.class).length);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 AnnotationLookupDemo.java
java AnnotationLookupDemo
~~~

Expected output on Java 17+:

~~~text
child role=base
child declared role=false
child has role=true
child has local=false
explicit child role=child
interface role inherited=false
overridden method checked=false
inherited method owner=Base
inherited method checked=true
field column=true
constructor create=true
repeatable getAnnotation=false
repeatable container=true
repeatable byType=2
repeatable declaredByType=2
~~~

### Reading each group of results

- `Child` does **not** have `@Role` directly, but `@Role` is marked `@Inherited` on the annotation type and superclass `Base` has `@Role("base")`. Thus `getAnnotation` returns the parent's copy, `getDeclaredAnnotation` returns `null`, and `isAnnotationPresent` returns `true`.
- `@LocalOnly` does not have `@Inherited`, so `Child.class.isAnnotationPresent(LocalOnly.class)` returns `false` even though `Base` has this annotation.
- `ExplicitChild` writes `@Role("child")` directly, so the nearest value is `child`, not `base`.
- `ImplementsInterface` implements an interface that has `@Role("interface")`. `@Inherited` **does not apply across interface relationships**; the result is `false`.
- `Child.execute()` overrides the parent method without `@Checked`, so it does **not** automatically inherit the method annotation. For `unchanged()`, `getMethod` returns the very method object declared on `Base` (because Child does not override it), so `@Checked` is found. This is Reflection selecting a **different method**, not an annotation inheritance rule for overridden methods.
- `Base.id` is a private field with `@Column`; retrieving it via `Base.class.getDeclaredField("id")` lets you read the annotation without opening access via `setAccessible(true)`.
- `Base()` has `@Create` and Reflection finds it on the `Constructor` object.
- The two `@Label` annotations are stored via the `@Labels` container annotation, so `getAnnotation(Label.class)` does not return a single element; `getAnnotationsByType(Label.class)` / `getDeclaredAnnotationsByType(Label.class)` unpack both.

## 7. When an annotation is repeated

With a `@Repeatable(Labels.class)`, two `@Label` annotations are normally stored by the compiler inside the `@Labels` container. Therefore `getAnnotation(Label.class)` and `isAnnotationPresent(Label.class)` can return `null` and `false` respectively, even though the class has two label values. To read all labels, use `getAnnotationsByType(Label.class)`; to read only on the current element, use `getDeclaredAnnotationsByType(Label.class)`.

Containers and inheritance rules for repeatable annotations are explained in two dedicated lessons. `getAnnotation` also does not automatically scan meta-annotations placed on an annotation type: frameworks wanting to discover stereotype/composed annotations need a separate algorithm.

## 8. Getting annotations on classes and methods: watch out for overrides

Scenario:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Validate {}

class Parent {
    @Validate
    public void save() {}
}

class Child extends Parent {
    @Override
    public void save() {}
}
~~~

This is an illustrative fragment requiring the corresponding imports; it is not a standalone program. When selecting `Child.class.getDeclaredMethod("save")`, that is **`Child`'s method**, which does not carry `@Validate`, so both `getAnnotation(Validate.class)` and `getDeclaredAnnotation(Validate.class)` return `null`.

If a framework wants to support “inherited method annotations”, it must **define its own algorithm**: walk the appropriate superclasses/interfaces, match overriding methods by name and parameter types, and account for bridge methods, modifiers, visibility, generic erasure, and conflicting annotations. Do not write a naive loop scanning solely by method name, because overloads, overrides, and default interface methods can cause the wrong choice.

Additionally:

- `getMethod(...)` finds public methods that may be inherited; it can return a `Method` whose `getDeclaringClass()` is a superclass. Reading annotations on that object reads the annotations of the **actual declaration**.
- `getDeclaredMethod(...)` finds methods declared in the specified class without walking superclasses. If the class does not declare the requested method, it throws `NoSuchMethodException`.
- For methods with the same name but different parameter types, look up with the full signature, e.g. `getDeclaredMethod("save", String.class)`.
- `@Inherited` has no effect on `@Target(METHOD)` under Reflection rules; it is a mechanism that applies to class annotations.

## 9. Things to check before using results in business logic

### 9.1. Annotation type, retention, and target

When an annotation is not found:

1. Check that the annotation is imported from the right package and is actually the intended annotation class.
2. Check `@Retention(RUNTIME)`. Without an explicit retention, the default is `CLASS`.
3. Check `@Target` and the annotation's position in source: class, method, field, constructor, parameter, or `TYPE_USE`.
4. Check the exact Reflection element being read: which class, which method signature, which declaring class's field.
5. If expecting an inherited annotation, verify that `@Inherited` is on the annotation type and that you are querying on a **class** with a superclass relationship.
6. If the annotation is repeatable, prefer `getAnnotationsByType` over `getAnnotation`.
7. If you want metadata on interfaces or meta-annotations, implement a dedicated strategy. Core Reflection does not automatically traverse the entire interface/meta-annotation tree.

### 9.2. Avoiding `NullPointerException` when reading values

`getAnnotation(...)` and `getDeclaredAnnotation(...)` can return `null`, so do not write:

~~~java
// Illustrative code that can fail when the annotation is absent.
String name = element.getAnnotation(Feature.class).name();
~~~

Replace with a check branch:

~~~java
// Illustrative fragment; element is an AnnotatedElement.
Feature feature = element.getAnnotation(Feature.class);
if (feature != null) {
    String name = feature.name();
    // Use name according to business rules.
}
~~~

If you only need to know whether the annotation is present, calling `isAnnotationPresent(Feature.class)` makes the intent clear. If you need member contents such as `value()`, call `getAnnotation` once and check for null to avoid unnecessary repeated lookups.

### 9.3. Reading an annotation does not guarantee every member value is valid

An annotation result is an object representing runtime metadata with element methods. In cases where the class file or annotation declaration is no longer compatible, reading an element can raise errors such as `TypeNotPresentException`, `EnumConstantNotPresentException`, `AnnotationTypeMismatchException`, or `IncompleteAnnotationException`. This does not turn `getAnnotation` into a business-operation API: when extracting configuration from annotations, a framework should report metadata errors with the annotation name, element, and failing member rather than silently ignoring them.

`getAnnotation(null)`, `getDeclaredAnnotation(null)`, and `isAnnotationPresent(null)` are not ways to check for “any annotation”; the API requires a non-null annotation class and can throw `NullPointerException`.

### 9.4. Do not use `getDeclaredAnnotation` to guess Java access levels

The word “declared” means “annotation directly on this element”, not “for private/protected members only”. An annotation on a public class can still be retrieved via `getDeclaredAnnotation`. Likewise, an annotation on a private method can be read from a `Method` obtained via `getDeclaredMethod` without opening access to invoke the method.

### 9.5. Annotation inheritance differs from member inheritance

- Field hiding: a field with the same name in a subclass and a field in a parent are **two distinct declarations** and do not automatically share annotations.
- Method overriding: a new method in a subclass does not automatically inherit annotations from the parent method.
- Constructors: are not inherited, so annotations on a parent constructor do not transfer to a child constructor.
- Parameter annotations: are not automatically inherited by parameter position across overriding methods.
- Class inheritance: only annotation types with `@Inherited` are considered by Core Reflection along superclasses, subject to the corresponding conditions.

## 10. Recommendations for designing an annotation lookup utility

For frameworks, explicitly write out the **lookup policy** rather than using an ambiguous `findAnnotation` function.

**Declared-only policy:** when checking a declaration at an exact site, use `getDeclaredAnnotation` or `getDeclaredAnnotationsByType`. Suitable for configuration that must be attached directly to a specific class to avoid accidentally picking up rules from a superclass.

**Java-present policy:** when you want Java's built-in semantics, use `getAnnotation` or `isAnnotationPresent`; for classes + `@Inherited`, annotations from superclasses are valid. For repeatable annotations, use the appropriate `ByType` APIs.

**Framework-custom policy:** when you want to scan interfaces, overridden methods, or meta-annotations as well, define an explicit lookup algorithm and precedence order, and test with diamond inheritance, conflicting annotations, method overloads, bridge methods, and classloaders. Do not assume `isAnnotationPresent` already performs that work.

Policy decision examples:

| Goal | Recommended policy |
| --- | --- |
| Does the current class declare `@Configuration` itself? | `getDeclaredAnnotation(Configuration.class) != null` |
| Does the class have a Java-recognized `@Inherited` annotation from a superclass? | `getAnnotation(...)` or `isAnnotationPresent(...)` |
| All repeatable route markers on this class? | `getDeclaredAnnotationsByType(Route.class)` |
| Finding annotations on interface methods and implementation overrides? | Custom framework algorithm; do not rely on `getAnnotation` on overriding methods. |
| Finding marker annotations nested inside meta-annotations? | Controlled traversal of annotation types/meta-annotations. |
| Need to read an annotation with configuration values? | `getAnnotation`, check for null, then read element methods. |

## 11. Verification exercises

1. In the demo, remove `@Inherited` from the `Role` definition: predict the output for `child role` and `child has role`; update the code to handle `null` before running.
2. Attach `@Role("child-own")` directly on `Child`, then compare `getAnnotation` and `getDeclaredAnnotation` on `Child` itself.
3. Attach `@Checked` directly on `Child.execute()` to see that overriding method annotations no longer depend on the superclass.
4. Use `Child.class.getMethod("unchanged").getDeclaringClass()` to explain why the annotation on `Base.unchanged()` can still be read.
5. Try an annotation with `RetentionPolicy.CLASS` or omit `@Retention` and observe `getAnnotation(...) == null`.
6. Try two `@Label`s versus one `@Label`; check `getAnnotation(Label.class)`, `isAnnotationPresent(Label.class)`, and `getAnnotationsByType(Label.class)`.
7. Create an interface with `@Role` and a class implementing the interface; prove that `@Inherited` does not apply through interfaces.
8. Create an annotation placed on a formal parameter using `@Target(PARAMETER)`, and read it via `method.getParameters()[0].getAnnotation(...)` rather than reading on `Method`.
9. Write one helper using declared-only and one using Java-present, then run both against `Base/Child` to compare the API contracts.

## 12. References

- [Java SE 17 — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): `getAnnotation`, `getDeclaredAnnotation`, `isAnnotationPresent`, repeatable annotations, and definitions of present/directly present.
- [Java SE 17 — Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): annotation inheritance along class superclasses, not from interfaces or methods.
- [Java SE 17 — Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): retention policies and the `CLASS` default.
- [Java SE 17 — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): container annotation mechanism and the `ByType` APIs.
- [Java Language Specification 17 — `9.6 Annotation Types and `9.7 Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): definitions, applicability, and annotation semantics.

**Key takeaway:** `getDeclaredAnnotation` reads only annotations attached directly; `getAnnotation` reads *present* annotations (potentially via superclasses for classes and annotation types marked `@Inherited`); `isAnnotationPresent` checks that same present condition. For repeatable annotations, interface lookups, or overridden methods, choose the appropriate API/policy rather than expecting these three getters to handle everything automatically.