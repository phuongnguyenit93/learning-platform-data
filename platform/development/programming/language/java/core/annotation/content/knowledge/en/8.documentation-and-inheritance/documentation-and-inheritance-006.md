# Distinguishing Annotation Inheritance from Java Member Inheritance

## 1. Two Mechanisms Named “Inheritance” That Work Differently

When writing:

~~~java
class Parent {
    public void execute() {}
}

class Child extends Parent {}
~~~

`Child` can call `execute()` even without declaring that method itself. This is **Java member inheritance**: governed by `extends`, `implements`, access control, overriding/hiding, and the rules of the language.

Now consider:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Role {
    String value();
}

@Role("service")
class Parent {}

class Child extends Parent {}
~~~

`Child.class.getAnnotation(Role.class)` can return `@Role("service")` even though `Child` does not directly declare that annotation. This is **annotation inheritance via `@Inherited` during class lookup**. It differs from `Child` inheriting methods or fields from `Parent`.

The key point: **`@Inherited` only controls how an annotation type is looked up on a class declaration through the superclass hierarchy; it does not copy annotations onto every field, method, constructor, or overridden method.** Conversely, Java member inheritance rules still apply regardless of whether `@Inherited` is present.

## 2. Java Member Inheritance: What Can a Subclass Actually Use?

A class can inherit eligible members from its superclass or superinterfaces, depending on the member kind and access rules. The categories to distinguish:

| Member | Key Rule |
|---|---|
| Instance method | Eligible methods can be inherited; a subclass can **override** methods that allow overriding. |
| `public`/`protected` field | Eligible fields can be inherited; a field with the same name in a subclass **hides** the original field, rather than overriding it. |
| `static` method | Inherited under eligible conditions; a `static` method with the same signature can **hide** it, without participating in dynamic dispatch like instance overriding. |
| `private` member | Not inherited according to language rules; private methods/fields still belong to the declaring class. |
| Package-private member | Whether it is inherited and its accessibility depend on the package and JLS conditions. |
| Constructor | **Not inherited**; subclass constructors are declared separately and call a superclass constructor according to initialization rules. |
| Interface method | A class can implement abstract methods or inherit default methods, depending on conflicts and overriding rules. |

For instance methods, a call on an object can execute the subclass implementation thanks to **dynamic dispatch**. Meanwhile, annotation metadata is attached to each specific method declaration; Java does not automatically copy annotations from a parent method to an overriding method.

Example:

~~~java
class Parent {
    public String label() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String label() {
        return "child";
    }
}
~~~

`new Child().label()` returns `"child"` because Java selects the overriding method. Annotations on `Parent.label()`, if any, do not automatically become direct annotations of `Child.label()`.

## 3. What Does `@Inherited` Actually Do?

`java.lang.annotation.Inherited` is a **meta-annotation**: you place it on an **annotation type declaration**, not directly on a subclass or a method to request inheritance.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Environment {
    String value();
}
~~~

For an annotation type annotated with `@Inherited`, when looking up that annotation on a **class declaration**, if the class has no corresponding annotation directly declared on it, the lookup mechanism continues up the **superclass chain** until it finds the annotation or reaches `Object`.

~~~java
@Environment("production")
class Parent {}

class Middle extends Parent {}

class Child extends Middle {}
~~~

If you query `Child.class.getAnnotation(Environment.class)`, reflection can locate `Parent`'s annotation and return `@Environment("production")`.

Points to remember:

1. `@Inherited` is **not required** for a class to inherit regular methods/fields.
2. `@Inherited` applies to annotation lookup on a **class**; it does not automatically apply to methods, fields, or constructors.
3. It only follows the **superclass**. An annotation placed on an **interface** is not automatically propagated to an implementing class, nor from an interface to a subinterface via `@Inherited`.
4. If a subclass directly declares an annotation of the same type, the value declared on the subclass is used; elements of the two annotations are not automatically merged.
5. To look up annotations via reflection at runtime, the annotation type needs `@Retention(RetentionPolicy.RUNTIME)`. `@Inherited` by itself **does not change retention**.

### 3.1. `@Target` and `@Retention` Have Separate Roles

`@Target(ElementType.TYPE)` allows placing the annotation on class and interface declarations; `@Inherited` takes effect when looking up annotations **on a class** through superclasses. `@Retention(RUNTIME)` is what makes the annotation accessible via Java reflection while the application is running.

If an annotation uses `@Retention(CLASS)` or `@Retention(SOURCE)`, adding `@Inherited` will not make `Class.getAnnotation(...)` suddenly return data at runtime. By default, if `@Retention` is omitted, an annotation has `CLASS` retention.

`@Inherited` is also not the mechanism of `@Documented`: `@Documented` relates to including the annotation in Javadoc, not controlling the rule for recognizing annotations in superclasses.

## 4. Looking at the Reflection API: Directly Declared or Found via Superclass?

Two common ways to query:

~~~java
// Illustrative example, assuming Environment/Parent/Child from section 3 have been declared:
Environment inherited = Child.class.getAnnotation(Environment.class);
Environment declared = Child.class.getDeclaredAnnotation(Environment.class);
~~~

- `getAnnotation(Environment.class)`: on `Class`, returns the annotation if directly present or present according to the applicable inheritance rules. With `@Inherited`, it can look on superclasses.
- `getDeclaredAnnotation(Environment.class)`: considers only annotations declared **directly** on the queried class; does not search through superclasses.
- `getAnnotations()`: collects annotations that are directly present as well as inherited annotations considered present according to the corresponding API.
- `getDeclaredAnnotations()`: collects only annotations directly declared on the class.
- `getAnnotationsByType()` and `getDeclaredAnnotationsByType()`: have additional rules for `@Repeatable` annotations; when working with repeated annotations, you must read the exact contract of these two APIs.

Example illustrating the expected results if `@Environment("production")` is only on `Parent`:

| Query | Result |
|---|---|
| `Parent.class.getDeclaredAnnotation(Environment.class)` | Returns `@Environment("production")` |
| `Child.class.getAnnotation(Environment.class)` | Returns `@Environment("production")` via `@Inherited` |
| `Child.class.getDeclaredAnnotation(Environment.class)` | `null` |
| `Child.class.getDeclaredAnnotations()` | Does not contain `Environment` if Child does not declare it |
| `Child.class.getSuperclass()` | `Middle.class` in the three-level example |

**The fact that an annotation is found on a class via an API does not mean the subclass's class file contains a direct copy of the annotation.** The simple proof is that `getAnnotation(...)` returns data while `getDeclaredAnnotation(...)` returns `null`.

If the subclass itself specifies:

~~~java
@Environment("development")
class Child extends Parent {}
~~~

then `Child.class.getAnnotation(Environment.class).value()` is `"development"`. The system takes the annotation on Child; values are not “merged” with the annotation of the same type on Parent. Any element omitted at the declaration site uses the annotation type's `default`, if any.

## 5. `@Inherited` Does **Not** Inherit Annotations from Interfaces

This is a common misconception: Java can inherit or implement methods from an interface, but annotations on an **interface declaration** do not participate in the superclass lookup for `@Inherited`.

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

@Category("api")
interface Api {}

class ApiImpl implements Api {}
~~~

Even though `Category` carries `@Inherited`, the following query returns `null`:

~~~java
System.out.println(ApiImpl.class.getAnnotation(Category.class)); // null
~~~

Similarly, an interface `ExtendedApi extends Api` does not automatically receive `@Category("api")` via `@Inherited`.

If a framework wants to find annotations on interfaces, it must **explicitly traverse the interfaces** and define a lookup policy. Default Java reflection via `Class.getAnnotation` does not automatically add interface-scanning rules. This is a common difference between plain Java reflection and utilities designed by frameworks.

## 6. Does `@Inherited` Have Any Effect on Method/Field Annotations?

An annotation type can declare `@Inherited` even when its `@Target` only includes `METHOD` or `FIELD`; that syntax does not turn the annotation into metadata that automatically propagates to subclass members.

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Reviewed {}

class Base {
    @Reviewed
    public void execute() {}
}

class Derived extends Base {
    @Override
    public void execute() {}
}
~~~

The two reflection method objects are distinct:

~~~java
Base.class.getDeclaredMethod("execute").isAnnotationPresent(Reviewed.class);    // true
Derived.class.getDeclaredMethod("execute").isAnnotationPresent(Reviewed.class); // false
~~~

`Derived.execute()` overrides a regular Java method. Having `@Reviewed` on the original method does not automatically attach `@Reviewed` to the overriding method. If a policy of “whether an overriding method carries the annotation effect of the parent method” is required, it must be defined and looked up manually by the library consuming the annotation.

The same applies to fields: an annotation on a field in `Base` is not automatically copied onto a new field with the same name in `Derived`.

## 7. Easy-to-Confuse Point: Obtaining an Inherited Method's Annotation via `getMethod()`

Reconsider the case:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Reviewed {}

class Base {
    @Reviewed
    public void execute() {}
}

class Derived extends Base {
    // Does not override execute().
}
~~~

In this case:

~~~java
var method = Derived.class.getMethod("execute");
System.out.println(method.getDeclaringClass().getSimpleName()); // Base
System.out.println(method.isAnnotationPresent(Reviewed.class)); // true
~~~

Why do we see `true` when `@Inherited` does not apply to methods?

**Because `getMethod("execute")` finds the exact method declared in `Base`** (a method being inherited by `Derived`). The `Method` object has `getDeclaringClass() == Base.class`, so the `@Reviewed` annotation is a **direct** annotation of the method on Base. Java does not create a new method and copy the annotation over.

If `Derived` overrides `execute()`, `Derived.class.getMethod("execute")` normally points to the new declaration in Derived, which no longer has the original annotation unless the author annotates it again. This is the difference between:

- **Member lookup scope**: `Class.getMethod` can look up inherited `public` methods, whereas `getDeclaredMethod` only considers methods declared directly in that exact class.
- **Member annotation lookup scope**: `Method.getAnnotation` reads the annotations of the method declaration that the `Method` object represents; it does not automatically inspect overridden methods in other superclasses.

Therefore, seeing an annotation on a `Method` returned by `Derived.class.getMethod(...)` is **not sufficient evidence** to claim that `@Inherited` propagated the annotation to the method.

## 8. Similarly for Fields: Inherited Fields Differ from Hidden Fields

Suppose:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Column {}

class Parent {
    @Column
    public int id = 1;
}

class Child extends Parent {}           // Inherits field id

class ShadowChild extends Parent {
    public int id = 2;                  // Hides Parent's field
}
~~~

When calling:

~~~java
var fromChild = Child.class.getField("id");
var fromShadow = ShadowChild.class.getField("id");
~~~

- `fromChild.getDeclaringClass()` is `Parent.class`; `fromChild` carries `@Column` because it is the **original field** in Parent.
- `fromShadow.getDeclaringClass()` is `ShadowChild.class`; the new field does not automatically carry `@Column` even though it has the same name.
- If you directly query `Parent.class.getDeclaredField("id")`, you still see the original field and its annotation.
- There is no dynamic dispatch for fields as there is for instance methods; field hiding is determined by the reference type and access rules.

A constructor is also not inherited: `Child` can call `Parent`'s constructor via `super(...)`, but it does not “own” a copy of the constructor or the annotations on the parent constructor. Parameter annotations are likewise not automatically copied to the subclass constructor.

## 9. Runnable Java 17+ Example: Comparing the Scenarios

Create a **Main.java** file in a separate directory with the following full content:

~~~java
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

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalOnly {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Mark {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldMark {}

@Role("base")
@LocalOnly
class Base {
    @Mark
    public String report() {
        return "base";
    }

    @FieldMark
    public int id = 7;
}

class PlainChild extends Base {}

class Child extends Base {
    @Override
    public String report() {
        return "child";
    }
}

@Role("child")
class OwnRoleChild extends Base {}

class ShadowChild extends Base {
    public int id = 9;
}

@Role("interface")
interface Api {
    @Mark
    default String ping() {
        return "api";
    }
}

class ApiImpl implements Api {}

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("plainRole="
                + PlainChild.class.getAnnotation(Role.class).value());
        System.out.println("plainRoleDeclared="
                + (PlainChild.class.getDeclaredAnnotation(Role.class) != null));
        System.out.println("plainLocalOnly="
                + (PlainChild.class.getAnnotation(LocalOnly.class) != null));
        System.out.println("ownRole="
                + OwnRoleChild.class.getAnnotation(Role.class).value());
        System.out.println("apiImplRole="
                + (ApiImpl.class.getAnnotation(Role.class) != null));

        System.out.println("plainMethodDeclaring="
                + PlainChild.class.getMethod("report")
                        .getDeclaringClass().getSimpleName());
        System.out.println("plainMethodMark="
                + PlainChild.class.getMethod("report")
                        .isAnnotationPresent(Mark.class));
        System.out.println("overriddenMethodDeclaring="
                + Child.class.getMethod("report")
                        .getDeclaringClass().getSimpleName());
        System.out.println("overriddenMethodMark="
                + Child.class.getMethod("report")
                        .isAnnotationPresent(Mark.class));
        System.out.println("childMethodResult=" + new Child().report());

        System.out.println("plainFieldDeclaring="
                + PlainChild.class.getField("id")
                        .getDeclaringClass().getSimpleName());
        System.out.println("plainFieldMark="
                + PlainChild.class.getField("id")
                        .isAnnotationPresent(FieldMark.class));
        System.out.println("shadowFieldDeclaring="
                + ShadowChild.class.getField("id")
                        .getDeclaringClass().getSimpleName());
        System.out.println("shadowFieldMark="
                + ShadowChild.class.getField("id")
                        .isAnnotationPresent(FieldMark.class));

        System.out.println("apiImplPingMark="
                + ApiImpl.class.getMethod("ping")
                        .isAnnotationPresent(Mark.class));
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Output:

~~~text
plainRole=base
plainRoleDeclared=false
plainLocalOnly=false
ownRole=child
apiImplRole=false
plainMethodDeclaring=Base
plainMethodMark=true
overriddenMethodDeclaring=Child
overriddenMethodMark=false
childMethodResult=child
plainFieldDeclaring=Base
plainFieldMark=true
shadowFieldDeclaring=ShadowChild
shadowFieldMark=false
apiImplPingMark=true
~~~

Let's read each group of results according to its true nature:

1. `plainRole=base` yet `plainRoleDeclared=false`: `@Inherited` helps reflection find class metadata on the superclass; PlainChild does not directly declare `@Role`.
2. `plainLocalOnly=false`: annotation type `LocalOnly` does not have `@Inherited`, so it is not automatically present on PlainChild even though Base carries it.
3. `ownRole=child`: an annotation of the same type declared directly by Child (here `OwnRoleChild`) gives priority to the data at the subclass.
4. `apiImplRole=false`: annotations from interface `Api` are not automatically inherited via `@Inherited`.
5. `plainMethodDeclaring=Base` and `plainMethodMark=true`: `getMethod` returns the method in Base; it is not propagating the annotation onto a new method.
6. `overriddenMethodDeclaring=Child` and `overriddenMethodMark=false`: annotations are not automatically copied to the overriding method.
7. `childMethodResult=child`: Java still uses dynamic dispatch and invokes the implementation in Child regardless of annotations.
8. `plainFieldDeclaring=Base`, `plainFieldMark=true`: the inherited field is reflected as the original field in Base.
9. `shadowFieldDeclaring=ShadowChild`, `shadowFieldMark=false`: the new field hides the old field and does not automatically receive the old field's metadata.
10. `apiImplPingMark=true`: `ApiImpl.class.getMethod("ping")` sees the original `default` method in `Api`; this method's annotation is the annotation on that interface method, **not the result of `@Inherited` on the method**.

The two annotation types `Mark` and `FieldMark` in the example **intentionally carry `@Inherited`** to prove that this meta-annotation does not cause annotations to “move” from a parent method/field to a new declaration in a subclass.

## 10. `@Override` and `@Inherited` Are Not Directly Related

`@Override` is placed on a **method declaration** and is used to instruct the compiler to check whether the method validly overrides/implements a method according to Java rules. It has no responsibility for copying annotations between methods.

~~~java
class Base {
    public void save() {}
}

class Child extends Base {
    @Override
    public void save() {}
}
~~~

`@Override` in Child only verifies a valid override relationship. If Base.save() also has `@Mark`, that does **not** cause Child.save() to receive `@Mark`. If a library requires the annotation on the method implementation itself, it must be placed on the appropriate declaration or metadata lookup logic along the hierarchy must be built.

Even without `@Override`, the overriding relationship is still determined by Java based on signature, visibility, inheritance, and related rules. Thus, `@Override` is a compile-time error-checking tool, not a prerequisite for creating method inheritance.

## 11. When Using Frameworks or Writing Custom Annotation-Reading Utilities

For example, a library wants to know which class carries a “role” or which method carries a “policy”. There are different lookup policies:

| Requirement | Appropriate API/Approach | Considerations |
|---|---|---|
| Look up class-level annotation supporting superclass inheritance | `clazz.getAnnotation(Role.class)` | Requires `@Inherited` and `RUNTIME`; does not traverse into interfaces. |
| Look up only class-level annotation declared on the current class | `clazz.getDeclaredAnnotation(Role.class)` | Ignores superclasses. |
| Read annotation on a method found via the public API | `clazz.getMethod(...).getAnnotation(Mark.class)` | May receive a `Method` declared in a superclass/interface; check `getDeclaringClass()`. |
| Read only methods declared in the current class | `clazz.getDeclaredMethod(...)` | Does not automatically trace back to overridden methods; may throw `NoSuchMethodException`. |
| Read field annotations | `getField(...)` or `getDeclaredField(...)` | Distinguish inherited fields from hidden fields. |
| Find annotations from an overridden superclass method | Manually traverse superclasses and locate the corresponding method | Must handle signatures, overriding, visibility, and bridge/generic methods according to contract. |
| Find class annotations on interfaces | Manually traverse the interface hierarchy if the policy requires it | `@Inherited` does not automatically search interfaces. |

When implementing deep lookup yourself, you need to decide clearly **whether to prioritize metadata in the subclass**, whether to merge/override values, which interfaces to handle, and how to handle `@Repeatable`. This is a **library convention**, not something automatically derived from `@Inherited`.

Frameworks may provide their own utilities to search for annotations across multiple layers of classes, interfaces, or methods. Do not take the results of a framework utility to infer the default rules of `Class.getAnnotation()`; read the specific API contract.

An example that commonly happens in applications: a parent class's `@Role` can be found by `Child.class.getAnnotation(Role.class)`, whereas an annotation marking `Base.save()` does not exist on `Child.save()` after overriding. If your security/validation logic only scans annotations on the method implementation, you need to place the annotation in the right location or use a consistent lookup mechanism.

## 12. Common Misconceptions and How to Check

### Misconception 1: “If Child inherits a method, it also inherits the method's annotation”

Incorrect when Child **overrides** the method: an overriding method is a new declaration. If Child does not override it, `getMethod` can return the parent method itself with its existing annotation. You should check `Method.getDeclaringClass()` before drawing a conclusion.

### Misconception 2: “Adding `@Inherited` makes annotations from interfaces propagate down as well”

Incorrect: `@Inherited` traverses the class's superclasses, does not search interfaces, and does not traverse the entire type tree.

### Misconception 3: “I see the annotation from `getAnnotation()`, so the annotation is directly on the subclass”

Check `getDeclaredAnnotation()`. If `getAnnotation()` is non-`null` while `getDeclaredAnnotation()` is `null`, it may be a class-level annotation found via `@Inherited`.

### Misconception 4: “A field with the same name in a subclass reuses the parent field's annotation”

The field in the subclass may **hide** the old field, yet the two fields are two separate declarations. Check `Field.getDeclaringClass()`.

### Misconception 5: “`@Override` automatically inherits annotations from the overridden method”

`@Override` only requests an override check at compile time; it does not automatically copy annotation metadata.

### Misconception 6: “`@Inherited` turns an annotation into an automatically executing runtime rule”

Annotations are metadata. To change application behavior, a compiler, tool, or runtime framework must **read and interpret** the metadata. `@Inherited` only affects how an annotation can be found in eligible cases.

### Misconception 7: “`@Inherited` alone is enough; `@Retention(RUNTIME)` is not needed”

Incorrect if the code intends to read the annotation via reflection at runtime. An annotation with the default `CLASS` retention is not automatically available in the results of `Class.getAnnotation` at runtime.

### Misconception 8: “Parent constructors are inherited, so constructor annotations are also inherited”

Constructors are not inherited. Annotations on a superclass constructor do not automatically become annotations on a subclass constructor, even when the subclass calls `super(...)`.

## 13. Short Procedure to Diagnose a “Missing” Annotation

When an annotation is not found as expected, check the following in order:

1. **Declaration location**: is the annotation on a `class`, `interface`, `method`, `field`, `constructor`, or `parameter`?
2. **Applicable target**: check whether `@Target` includes `TYPE`, `METHOD`, `FIELD`, etc., matching that location.
3. **Retention**: runtime reflection requires `@Retention(RUNTIME)`.
4. **Java relationships**: does the class `extends` a superclass, `implements` an interface, or have a method `override`/field `hide`?
5. **API being called**: `getAnnotation` or `getDeclaredAnnotation`, `getMethod` or `getDeclaredMethod`, `getField` or `getDeclaredField`?
6. **Declaring class**: for `Method`/`Field`, call `getDeclaringClass()` to know which member is actually being read.
7. **Business intent**: if you want to trace annotations along a method hierarchy or interface hierarchy, define and implement that policy explicitly.

Do not fix the issue by adding `@Inherited` to every annotation type: that solution will not help with method overriding, field hiding, or classes implementing interfaces.

## 14. Official References

- [Java SE 17 JLS §9.6.4.3 — `@Inherited`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3): annotation inheritance applies only within a class's superclasses.
- [Java SE 17 API — `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): official description of its scope and limitations regarding interfaces and methods.
- [Java SE 17 API — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): differences among `getAnnotation`, `getDeclaredAnnotation`, and repeatable annotations.
- [Java SE 17 JLS §8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): inheritance and overriding/hiding rules within classes.
- [Java SE 17 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredField`, and other reflection APIs.

**Remember:** Java member inheritance answers **which methods/fields a subclass can use**. `@Inherited` answers **whether a class-level annotation can be found through superclasses during metadata lookup**. Method overriding and field hiding create separate declarations that do not automatically inherit the parent member's annotations; an inherited method/field can carry annotations because the reflection object itself points to the original declaration.
