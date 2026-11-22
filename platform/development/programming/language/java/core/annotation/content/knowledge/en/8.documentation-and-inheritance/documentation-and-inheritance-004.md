# Annotation Inheritance Boundaries: Not Propagated from Interfaces, Methods, or Fields

## 1. Understanding `@Inherited` Correctly in Java

In Java, **class inheritance**, **member inheritance**, and **inherited annotation lookup** are different mechanisms. A method can be inherited by a subclass in terms of method invocation, but that does not mean the metadata of that method is copied to a new method. This is the cause of much confusion when using the `@Inherited` meta-annotation.

`@Inherited` resides in the `java.lang.annotation` package. It is placed on an **annotation type declaration** to mark that annotations of that type can be **looked up along the superclass chain** under certain conditions:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

@Category("parent")
class Parent {}

class Child extends Parent {}
```

With this code snippet, `Child.class.getAnnotation(Category.class)` can find `@Category("parent")` from `Parent` when `Child` does not directly have `@Category`. However, `Child.class.getDeclaredAnnotation(Category.class)` still returns `null` because `Child` **does not directly declare** that annotation.

**Core boundary of this article:** `@Inherited` only has inheritance semantics on **class declarations** along the superclass chain. It does **not** cause annotations to propagate from implemented interfaces, does not cause annotations to propagate from overridden methods, and does not cause annotations to propagate to fields redeclared in a subclass.

## 2. Under What Exact Conditions Is an Annotation Looked Up from a Superclass?

Suppose there is an annotation type `A` with `@Inherited`:

1. An annotation of type `A` is placed directly on a **class declaration** on the superclass side.
2. A subclass is queried for `A`, while that class itself **does not directly declare** `A`.
3. When looking up using Reflection methods that consider inheritance, such as `Class.getAnnotation(A.class)` or `Class.getAnnotations()`, Java can continue up the **superclass chain** to find `A`.
4. If the subclass directly declares an annotation of the same type, the subclass's direct value takes precedence; elements are not automatically merged with the annotation on the superclass.

To observe it via Reflection at runtime, the annotation type needs `@Retention(RetentionPolicy.RUNTIME)`. If retention is not specified, the default is `CLASS`, and ordinary Reflection cannot read metadata attached to the superclass.

You can visualize it as follows:

```text
@Category("base")
class Base {}
      |
      | extends
      v
class Intermediate extends Base {}
      |
      | extends
      v
class FinalChild extends Intermediate {}

FinalChild.class.getAnnotation(Category.class)
    -> can find @Category("base") from Base

FinalChild.class.getDeclaredAnnotation(Category.class)
    -> null: FinalChild does not directly declare Category
```

`@Inherited` **does not actually copy the source annotation into the subclass declaration**. It affects the **metadata lookup** rules. When running `javap -v` on a subclass that has no direct annotation, do not expect to see a copy of the annotation from the superclass inside the subclass's own `.class` file.

### Two Easily Confused Reflection APIs

| API on `Class` object | Considers superclass when annotation type has `@Inherited`? | Meaning |
| --- | --- | --- |
| `getAnnotation(A.class)` | Yes, under valid conditions | Returns the direct annotation or an inherited one from a superclass |
| `getAnnotations()` | Yes, for inherited annotations | Lists direct annotations and valid inherited annotations |
| `getDeclaredAnnotation(A.class)` | No | Only annotations directly on the class being inspected |
| `getDeclaredAnnotations()` | No | Only directly declared annotations |
| `isAnnotationPresent(A.class)` | Yes, following `getAnnotation` rules | Checks presence using the corresponding lookup mechanism |

These are `Class` APIs. Do not mechanically apply this rule to `Method`, `Field`, or every framework API.

## 3. No Annotation Inheritance from Interfaces

Consider an interface annotated with an `@Inherited` annotation type:

```java
// The snippets below share the @Category declaration from section 2.
@Category("contract")
interface PaymentContract {}

class PaymentService implements PaymentContract {}
```

Even though `PaymentService` implements `PaymentContract`, ordinary calls:

```java
PaymentContract.class.getAnnotation(Category.class); // has Category
PaymentService.class.getAnnotation(Category.class);  // null
```

Explanation: **inheritance via `@Inherited` only follows a class's superclass chain**, not `implements` or `extends` between interfaces. The fact that an interface is a Java type does not cause metadata placed on an interface declaration to become an inherited annotation on the implementing class.

This also applies if `PaymentService` implements multiple interfaces that are each annotated with `@Category`; standard Reflection does not pick an interface from which to "inherit" that annotation.

In particular, when **one interface extends another interface**, `@Inherited` does not cause the annotation to automatically appear on the subinterface via `Class.getAnnotation` under class superclass rules. If a framework wants to find annotations along the **interface hierarchy**, the framework must provide its own scanning/lookup mechanism.

**Spring and framework scenarios:** some frameworks have systems that search for annotations along interfaces, meta-annotations, or composed structures. Lookup results defined by a framework can be broader than direct Java Reflection; this must not be taken as evidence that the language's `@Inherited` supports interfaces.

## 4. No Propagation of Annotations from Superclass Methods to Overriding Methods

Consider the following case:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Trace {
    String value();
}

class BaseHandler {
    @Trace("base")
    public void handle() {}
}

class DerivedHandler extends BaseHandler {
    @Override
    public void handle() {}
}
```

Here, `@Trace` is permitted on both classes and methods by `@Target`. However, `@Inherited` **only affects annotations on class declarations**. It **does not cause `DerivedHandler.handle()` to inherit `@Trace("base")`** from `BaseHandler.handle()`.

If you retrieve the overriding method itself:

```java
DerivedHandler.class
    .getDeclaredMethod("handle")
    .getAnnotation(Trace.class); // null
```

`@Override` only asserts that the method has a valid overriding relationship; it has **nothing to do with copying annotations** from the superclass method. If processing logic needs an annotation on an overriding method, it must be placed directly on that method, or a consumer must be written to actively traverse to the corresponding method in the superclass/interface.

### Why Does Looking Up an "Inherited" Method Sometimes Still Show the Annotation?

There is one situation that must be distinguished very clearly. Suppose `BaseHandler` has `public void process()` annotated with `@Trace`, while `DerivedHandler` **does not override `process()`**. When calling:

```java
DerivedHandler.class.getMethod("process")
```

Reflection can return the `Method` object **declared in `BaseHandler`**, because `getMethod` also looks up inherited `public` methods. When subsequently calling `getAnnotation(Trace.class)` on that `Method`, you are reading the **direct annotation of the superclass method**, not an annotation that Java has propagated through a method override.

Use `method.getDeclaringClass()` to distinguish. If it returns `BaseHandler.class`, then the `Method` represents the original declaration. If the subclass overrides it, the subclass has its own `Method` declaration, and the superclass method's annotation does not follow automatically.

## 5. No Propagation of Annotations to Subclass Fields

A `field` is a separate declaration site. Consider:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface ColumnLabel {
    String value();
}

class BaseRecord {
    @ColumnLabel("ID")
    public String id;

    @ColumnLabel("CODE")
    public String code;
}

class ChildRecord extends BaseRecord {
    // Redeclaring the name 'code': this is field hiding, not overriding.
    public String code;
}
```

On `ChildRecord`, the following two cases are different:

- `ChildRecord.class.getField("id")` can return the `Field` **declared in `BaseRecord`**, because `id` is an inherited `public` field and is not hidden. The annotation seen is the **direct annotation on the superclass field**.
- `ChildRecord.class.getDeclaredField("code")` returns the `code` field declared by `ChildRecord` itself, **without `@ColumnLabel`**. The annotation on `BaseRecord.code` does not transfer to the redeclared field.

Java **does not override fields** the way it overrides methods; a field with the same name in a subclass performs **field hiding**. Both fields are two separate declarations, and metadata is not automatically copied.

Similarly, an annotation placed on a **parameter, constructor, or method** does not automatically propagate to a member with the same name/type in a subclass solely because of the inheritance relationship between the classes.

## 6. Complete Java 17+ Example: Classes, Interfaces, Overrides, and Fields

Create the file **`InheritedBoundariesDemo.java`**. The following program runs standalone on Java 17+, without requiring Spring/JUnit. The same annotation type `@Trace` is permitted on type, method, and field declarations to demonstrate that **even though all placement sites are valid, only annotations placed on classes participate in the `@Inherited` mechanism**.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.FIELD})
@interface Trace {
    String value();
}

@Trace("interface-type")
interface JobContract {
    @Trace("interface-method")
    void perform();
}

@Trace("parent-type")
class ParentJob {
    @Trace("parent-method")
    public void unchanged() {}

    @Trace("parent-overridden")
    public void overridden() {}

    @Trace("parent-field")
    public String visible;

    @Trace("parent-hidden")
    public String hidden;
}

class ChildJob extends ParentJob {
    @Override
    public void overridden() {}

    public String hidden;
}

class ContractJob implements JobContract {
    @Override
    public void perform() {}
}

public class InheritedBoundariesDemo {
    public static void main(String[] args)
            throws NoSuchMethodException, NoSuchFieldException {

        Trace inheritedType = ChildJob.class.getAnnotation(Trace.class);
        System.out.println("Child class: " + inheritedType.value());
        System.out.println("Child declared: "
                + (ChildJob.class.getDeclaredAnnotation(Trace.class) != null));

        System.out.println("Interface itself: "
                + JobContract.class.getAnnotation(Trace.class).value());
        System.out.println("Interface to class: "
                + (ContractJob.class.getAnnotation(Trace.class) != null));

        Method overridden = ChildJob.class.getDeclaredMethod("overridden");
        System.out.println("Overridden method: "
                + (overridden.getAnnotation(Trace.class) != null));

        Method unchanged = ChildJob.class.getMethod("unchanged");
        System.out.println("Inherited method owner: "
                + unchanged.getDeclaringClass().getSimpleName());
        System.out.println("Inherited method marker: "
                + unchanged.getAnnotation(Trace.class).value());

        Field hidden = ChildJob.class.getDeclaredField("hidden");
        System.out.println("Hidden field: "
                + (hidden.getAnnotation(Trace.class) != null));

        Field visible = ChildJob.class.getField("visible");
        System.out.println("Inherited field owner: "
                + visible.getDeclaringClass().getSimpleName());
        System.out.println("Inherited field marker: "
                + visible.getAnnotation(Trace.class).value());

        Method implemented = ContractJob.class.getDeclaredMethod("perform");
        System.out.println("Interface method to implementation: "
                + (implemented.getAnnotation(Trace.class) != null));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 InheritedBoundariesDemo.java
java InheritedBoundariesDemo
```

Stdout output:

```text
Child class: parent-type
Child declared: false
Interface itself: interface-type
Interface to class: false
Overridden method: false
Inherited method owner: ParentJob
Inherited method marker: parent-method
Hidden field: false
Inherited field owner: ParentJob
Inherited field marker: parent-field
Interface method to implementation: false
```

### Interpreting the Output Accurately

**Subclass:**
- `ChildJob.class.getAnnotation(Trace.class)` finds `@Trace("parent-type")` from `ParentJob` because `Trace` has `@Inherited`, is placed on the **superclass**, and has `RUNTIME` retention.
- `ChildJob.class.getDeclaredAnnotation(Trace.class)` returns `null`, because `ChildJob` is not directly annotated with `@Trace`.

**Interface:**
- `JobContract.class.getAnnotation(Trace.class)` reads the annotation **directly** on the interface declaration.
- `ContractJob.class.getAnnotation(Trace.class)` returns `null`; `implements JobContract` does not trigger `@Inherited`.

**Method:**
- `ChildJob.overridden()` is a new method declaration in the subclass, without the annotation even though the superclass method was annotated with `@Trace`.
- `ChildJob.class.getMethod("unchanged")` finds the public method **actually declared in `ParentJob`**; the `getDeclaringClass()` line confirms the source. The annotation read belongs to that method.

**Field:**
- `ChildJob.hidden` is a new field hiding the field of the same name in the superclass, so the annotation on the superclass field does not automatically propagate.
- `ChildJob.class.getField("visible")` returns the public field **declared in `ParentJob`**; the annotation is the direct metadata of the superclass field.

**Method from interface:**
- `ContractJob.perform()` implements the method in the interface, but the annotation on `JobContract.perform()` is not copied to the implementing class's method.

The takeaway is not that "Reflection always returns null for inherited methods/fields." **If Reflection returns the actual `Method` or `Field` object of the superclass, the direct annotation on the original target can still be read.** What does not happen is **metadata propagation to a new declaration in the subclass**.

## 7. Decision Table: Inspecting the Right Target Element

| Scenario | Receives annotation via `@Inherited`? | Explanation |
| --- | --- | --- |
| Subclass has no annotation, superclass has an `@Inherited` annotation type | **Yes**, with an appropriate class Reflection lookup | Follows only the superclass path |
| Class implements an annotated interface | **No** | Interfaces are not part of the superclass chain for annotation inheritance |
| Subinterface extends an annotated superinterface | **No** under `@Inherited` rules | Not class inheritance |
| Subclass method overrides an annotated superclass method | **No** | Subclass method is a separate declaration |
| Subclass only inherits a public method without overriding it | **No propagation**; can still read the superclass method's annotation | `getMethod` can return the original superclass method |
| Subclass field redeclares the same name as an annotated superclass field | **No** | Two different fields; field hiding |
| Subclass queries a public field in the superclass that has not been hidden | **No propagation**; can still read the superclass field's annotation | `getField` can return the original field |
| Subclass directly declares an annotation of the same type | Direct value takes precedence | No inheritance from superclass needed |

These are standard Reflection rules. A library with its own annotation lookup API may search more broadly, but you need to check its specific documentation and mechanism before applying it.

## 8. Common Misconceptions

### "`@Inherited` propagates every annotation on every element."

False. `@Inherited` only governs the inheritance of **annotations on class declarations**. It does not cause every `Method`, `Field`, parameter, and interface to automatically possess the annotation of its parent-level counterpart.

### "`@Target(METHOD)` plus `@Inherited` means overriding methods inherit annotations."

False. `@Target` only specifies where an annotation may be placed; `@Inherited` still only has meaning on class declarations. Allowing a marker to be placed on a method does not expand inheritance semantics.

### "If `getMethod` sees an annotation, the subclass method must have inherited the metadata."

False. `getMethod` can return the public method in the superclass. Check `method.getDeclaringClass()`; if it is the superclass, you are looking at the superclass method's annotation, not metadata on an override in the subclass.

### "Fields and methods are inherited in the same way."

Incorrect. Methods can be overridden; fields can be *hidden* by a declaration with the same name. Regardless of the mechanism, a **new declaration** does not automatically receive annotations from the old declaration.

### "Annotations on interfaces have no effect."

This claim is also false. Annotations on an interface can still be read **directly on the interface itself**, and frameworks/processors can actively search along the interface hierarchy. They simply are not **automatically propagated by Java's `@Inherited`** to implementing classes.

### "Once `@Inherited` is present, any retention policy can be looked up via Reflection."

False. If it needs to be observed at runtime via Reflection, the annotation must have `@Retention(RetentionPolicy.RUNTIME)`. `@Inherited` does not replace `@Retention`.

### "Using a framework with interfaces changes standard Reflection behavior as well."

No. A framework may design its own annotation lookup system. When explaining a result, you must know whether you are using Java's `Class.getAnnotation`, a framework utility API, or a compile-time processor.

## 9. What If an Application Needs to "Inherit" Method or Interface Annotations?

For a requirement such as *"methods implementing an interface contract must carry the same audit policy"*, there are two approaches:

- **Place the annotation on the exact declaration that the consumer processes**, for example placing it on the implementing or overriding method. This approach is explicit, suitable when there are few usage sites, and avoids relying on a custom lookup algorithm.
- **Design the consumer to actively look up other sources**, for example finding methods with the same signature in superclasses and interfaces, or finding annotations on interfaces that the class implements. When doing so, you must define precedence order, overriding relationships, overloading, bridge methods, generic methods, multiple interfaces carrying conflicting metadata, and the rules of any relevant framework.

In code using plain Reflection, `Method.getAnnotation(...)` does not automatically run an algorithm to search both the interface hierarchy and superclass methods. If a library reports that it *found* an annotation on an interface or superclass method, check the library's logic: that proves **the consumer is doing extra work**, not that the meaning of `@Inherited` in Java has changed.

Conversely, if you only want to share an annotation **at the class level** between a superclass and a subclass, `@Inherited` plus `RUNTIME` is usually the appropriate standard mechanism, provided the relationship is `extends` between classes.

## 10. Self-Check Exercises

**Exercise 1.** `@Inherited @Retention(RUNTIME) @interface Label {}` is placed on `interface Marker {}`. Does `A.class.getAnnotation(Label.class)` return it for `class A implements Marker {}`?

**Answer:** No, because `@Inherited` does not propagate annotations from an interface to an implementing class.

**Exercise 2.** `Base.run()` has `@Trace`, while `Child.run()` overrides it without `@Trace`. Does `Child.class.getDeclaredMethod("run").getAnnotation(Trace.class)` see the metadata from Base?

**Answer:** No. `Child.run()` is a separate method declaration.

**Exercise 3.** `Child` does not override `Base.execute()`. Why can `Child.class.getMethod("execute")` read the annotation carried by `Base.execute()`?

**Answer:** `getMethod` can return the `Method` object declared in `Base`. The annotation is **direct metadata of the Base method**; verify via `getDeclaringClass()`.

**Exercise 4.** `Child` has a new `code` field with the same name as the annotated field in `Base`. Does the annotation automatically appear on `Child.code`?

**Answer:** No. Field hiding creates another declaration; `@Inherited` does not copy annotations from the superclass field.

**Exercise 5.** `Child.class.getAnnotation(Label.class)` sees the annotation from `Base`, while `Child.class.getDeclaredAnnotation(Label.class)` returns `null`. Is this a contradiction?

**Answer:** No. The first API considers the inherited annotation lookup mechanism on classes; the second API only reads direct annotations of the current class.

**Exercise 6.** A framework finds an annotation on an interface when a class implements that interface. Does that prove that Java's `@Inherited` supports interfaces?

**Answer:** No. The framework may have its own interface lookup algorithm, going beyond the default lookup scope of Java Reflection.

**Key takeaway:** `@Inherited` supports annotation lookup along a **class's superclass chain**; it does not copy metadata to interface implementations, overriding methods, or hidden fields. If you see an annotation on an "inherited" method or field, verify whether it is actually the declaration in the superclass returned by Reflection.
