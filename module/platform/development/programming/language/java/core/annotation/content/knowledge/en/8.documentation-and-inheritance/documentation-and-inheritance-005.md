# An Annotation Declared on a Subclass Shadows an Annotation of the Same Type on the Superclass

In Java Core, if an annotation type is marked with `@Inherited`, Reflection on a **class** can look up an annotation of that type on a superclass when the class under consideration does not declare a corresponding annotation. However, when **a subclass directly declares an annotation of the same type**, the declaration on the subclass takes precedence and the superclass's annotation is **shadowed in the lookup result**. The values of the two annotations are not automatically combined or merged.

This is a rule about how Java determines which annotation is **present** when querying a class, rather than the subclass deleting or modifying metadata in the superclass's `.class` file.

## 1. Objectives

After this lesson, you will be able to:

- Explain the conditions under which a class annotation can be inherited in Java: the annotation type must have `@Inherited` and an appropriate retention policy if read via Reflection at runtime.
- Predict the annotation returned when a subclass does not declare one, when a subclass declares one of the same type, and when there are multiple levels of inheritance.
- Understand why an annotation declared on a subclass **replaces all values of the inherited annotation of the same type**, while elements omitted in the subclass annotation use the `default` of the annotation type.
- Compare `getAnnotation(...)` with `getDeclaredAnnotation(...)`, `getAnnotations()`, and `getDeclaredAnnotations()`.
- Distinguish class-inherited annotations from annotations on interfaces, methods, fields, and repeatable annotations.
- Verify with a Java 17+ example that you compile and run yourself.

## 2. Prerequisites: How Does `@Inherited` Work?

Consider declaring an annotation used to describe a processing mode:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Mode {
    String value();
    int level() default 1;
}
~~~

This is an **illustrative declaration**; the complete program appears below.

The three meta-annotations each have a distinct role:

- `@Inherited`: allows the class annotation lookup mechanism to search up the **superclass** chain when needed.
- `@Retention(RetentionPolicy.RUNTIME)`: retains the annotation so Reflection can read it at runtime. If retention is not declared, it defaults to `CLASS`, and standard Reflection cannot read it.
- `@Target(ElementType.TYPE)`: allows the annotation to be applied to type declarations (in this example, on a class); the target does not create inheritance behavior on its own.

`@Inherited` is only meaningful for annotations placed on **class** declarations when Java looks up that annotation type on a subclass. It does not cause annotations placed on interfaces, methods, fields, or parameters to be automatically inherited under this rule.

For an annotation type that is not annotated with `@Inherited`, Reflection on a subclass does not automatically search the superclass for that annotation simply because the subclass uses `extends`.

## 3. Case 1: The Subclass Does Not Declare the Annotation

Suppose:

~~~java
@Mode(value = "base", level = 7)
class Base {}

class NoTag extends Base {}
~~~

`Base` directly declares `@Mode(value = "base", level = 7)`. `NoTag` does not have its own `@Mode`. Because `Mode` is marked with `@Inherited`, when querying:

~~~java
Mode inherited = NoTag.class.getAnnotation(Mode.class);
System.out.println(inherited.value()); // base
System.out.println(inherited.level()); // 7
~~~

Reflection retrieves the values from the annotation on `Base`.

However:

~~~java
Mode declared = NoTag.class.getDeclaredAnnotation(Mode.class);
System.out.println(declared); // null
~~~

The `null` result is expected because `NoTag` **does not directly declare** `@Mode`.

The distinction to remember:

- `getAnnotation(Mode.class)` returns an annotation considered **present** according to the API rules, which may come from a superclass if `@Inherited` applies.
- `getDeclaredAnnotation(Mode.class)` examines only the current element and does not look up the superclass.

Do not interpret this as the compiler copying `@Mode` from `Base` into `NoTag.class`. The superclass's annotation remains on the superclass; the Reflection API defines the lookup behavior to return the inherited result.

## 4. Case 2: The Subclass Declares the Same Type and Shadows the Superclass Annotation

Still using `Base`, declare the subclass:

~~~java
@Mode("child")
class Child extends Base {}
~~~

Now `Child` has its own `@Mode`. Querying:

~~~java
Mode mode = Child.class.getAnnotation(Mode.class);
System.out.println(mode.value()); // child
System.out.println(mode.level()); // 1
~~~

Result:

- `value()` is `"child"`, declared directly on `Child`.
- `level()` is `1`, taken from **`Mode.level() default 1`**.
- `level = 7` from the annotation on `Base` is **not merged** into the annotation on `Child`.

This is precisely what it means for an annotation on a subclass to **shadow an annotation of the same type on the superclass**. The lookup mechanism finds a matching annotation directly on the subclass, so it does not continue to retrieve the annotation of the same type from the superclass to merge elements.

Visual comparison:

| Class | Direct Annotation | `getAnnotation(Mode.class)` | `getDeclaredAnnotation(Mode.class)` |
| --- | --- | --- | --- |
| `Base` | `@Mode(value="base", level=7)` | `base:7` | `base:7` |
| `NoTag extends Base` | None | `base:7` (inherited during lookup) | `null` |
| `Child extends Base` | `@Mode("child")` | `child:1` | `child:1` |
| `Grandchild extends Child` | None | `child:1` (from `Child`) | `null` |

If you want `Child` to retain `level = 7`, you must **explicitly write** `@Mode(value = "child", level = 7)` or build custom processing logic to merge configurations. Standard Java Reflection does not perform such merging automatically.

### When There Are Multiple Consecutive Superclasses

~~~java
class Grandchild extends Child {}
~~~

`Grandchild` does not declare `@Mode`, so Reflection walks up the superclass chain and encounters `@Mode("child")` on `Child` first. The result is `child:1`, **not** `base:7`.

This yields an easy-to-remember rule: for an inheritable annotation type, **the nearest declaration along the path from the queried class up through its superclasses takes effect in the lookup result for an annotation of that type**. When the queried class declares it directly, the class itself is the nearest location.

The superclass still retains its own annotation: `Base.class.getAnnotation(Mode.class)` continues to return `base:7`, regardless of how many subclasses declare a different `@Mode`.

## 5. Standalone Java 17+ Example

Create a single file named **`InheritedShadowDemo.java`** and save the entire program below. Omit any `package` declaration so it can be run directly in the directory containing the file.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Mode {
    String value();
    int level() default 1;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Owner {
    String value();
}

@Mode(value = "base", level = 7)
@Owner("base-owner")
class Base {}

class NoTag extends Base {}

@Mode("child")
class Child extends Base {}

class Grandchild extends Child {}

@Mode("interface")
interface Contract {}

class ImplementsContract implements Contract {}

public class InheritedShadowDemo {
    public static void main(String[] args) {
        Mode base = Base.class.getAnnotation(Mode.class);
        Mode noTag = NoTag.class.getAnnotation(Mode.class);
        Mode child = Child.class.getAnnotation(Mode.class);
        Mode grandchild = Grandchild.class.getAnnotation(Mode.class);

        System.out.println("base=" + base.value()
                + ":" + base.level());
        System.out.println("noTag=" + noTag.value()
                + ":" + noTag.level());
        System.out.println("noTagDeclared="
                + NoTag.class.getDeclaredAnnotation(Mode.class));
        System.out.println("child=" + child.value()
                + ":" + child.level());
        System.out.println("childDeclared="
                + Child.class.getDeclaredAnnotation(Mode.class).value());
        System.out.println("grandchild=" + grandchild.value()
                + ":" + grandchild.level());
        System.out.println("ownerInherited="
                + NoTag.class.isAnnotationPresent(Owner.class));
        System.out.println("interfaceInherited="
                + ImplementsContract.class.isAnnotationPresent(Mode.class));
    }
}
~~~

Compile and run using JDK 17 or later:

~~~bash
javac -encoding UTF-8 InheritedShadowDemo.java
java InheritedShadowDemo
~~~

**Exact stdout:**

~~~text
base=base:7
noTag=base:7
noTagDeclared=null
child=child:1
childDeclared=child
grandchild=child:1
ownerInherited=false
interfaceInherited=false
~~~

Meaning of each group of lines:

1. `base=base:7`: `Base` declares `@Mode` completely, and Reflection reads that direct annotation itself.
2. `noTag=base:7`: `NoTag` does not declare it; `getAnnotation` is allowed to look up `Base` because `Mode` has `@Inherited`.
3. `noTagDeclared=null`: `getDeclaredAnnotation` does not examine superclasses.
4. `child=child:1`: `Child` declares `@Mode("child")` itself, so the result shadows the superclass annotation; `level` takes the default `1`, not `7` from the superclass.
5. `childDeclared=child`: `getDeclaredAnnotation` finds the annotation declared directly on `Child`.
6. `grandchild=child:1`: `Grandchild` continues to inherit the nearest annotation on `Child` during lookup.
7. `ownerInherited=false`: `Owner` has `RUNTIME` retention but **does not have `@Inherited`**, so `@Owner("base-owner")` on `Base` is not automatically visible on `NoTag`.
8. `interfaceInherited=false`: `Contract` is annotated with `@Mode`, but `ImplementsContract` only `implements Contract`. `@Inherited` **does not retrieve annotations from implemented interfaces**.

The example does not create any framework or automatic annotation-attaching logic; this is purely the behavior of reading metadata via Reflection.

## 6. APIs That Return Different Results

For a `Class<?>` object, the commonly used Reflection APIs:

| API | Handles class annotation inheritance? | Result for `NoTag` in the example |
| --- | --- | --- |
| `getAnnotation(Mode.class)` | Yes, if `@Inherited` applies and no closer declaration exists | `@Mode(value="base", level=7)` |
| `getDeclaredAnnotation(Mode.class)` | No; direct only | `null` |
| `isAnnotationPresent(Mode.class)` | Follows `getAnnotation` semantics | `true` |
| `getAnnotations()` | Includes annotations considered present; may include inherited annotations | Contains `Mode` from `Base` |
| `getDeclaredAnnotations()` | Does not look up superclasses | Does not contain `Mode` |
| `getAnnotationsByType(Mode.class)` | Supports repeatable types and inherits according to associated annotation rules | One `Mode` element in the example |
| `getDeclaredAnnotationsByType(Mode.class)` | Only directly/indirectly present on the element; does not search superclasses | Zero-length array |

On `Child`, both `getAnnotation(Mode.class)` and `getDeclaredAnnotation(Mode.class)` find `Child`'s annotation, so there is no reason to retrieve the annotation of the same type from `Base`.

Methods that return a single annotation, such as `getAnnotation(...)`, can return `null`. When working with general APIs, you need to check the value before invoking its elements:

~~~java
Mode mode = SomeClass.class.getAnnotation(Mode.class);
if (mode != null) {
    System.out.println(mode.value());
}
~~~

The snippet above illustrates the idea, assuming `Mode` and `SomeClass` are already declared; it is not a standalone runnable file.

### "Inherited" Differs from "Directly Declared"

In terms of metadata, both `Base` and `Child` have their own annotation declarations. `NoTag` and `Grandchild` do not necessarily have an annotation of the same type stored directly in their class files, even though `getAnnotation` returns an annotation at runtime.

If a program needs to know whether the author of the subclass **explicitly specified their own value**, use `getDeclaredAnnotation` or `getDeclaredAnnotationsByType` rather than relying solely on `getAnnotation`.

If a program only needs the effective class-level configuration under Java's inheritance rules, `getAnnotation` is generally more appropriate. When multi-level merging or per-element fallback is required, the application must design its own algorithm to retrieve and combine annotations from each superclass.

## 7. No Element Merging: Default Values Still Come from the Annotation Type

Consider again:

~~~java
@interface IllustrationOnly {
    String name();
    int priority() default 10;
    String[] tags() default {};
}
~~~

If you add `@Inherited` and `@Retention(RUNTIME)` to `IllustrationOnly`, and then the superclass uses `@IllustrationOnly(name = "base", priority = 99, tags = {"shared"})` while the subclass declares `@IllustrationOnly(name = "child")`, the effective metadata of the subclass will be:

~~~text
name = child
priority = 10
tags = []
~~~

`priority` and `tags` take the **default values declared by the annotation type**, not `99` or `{"shared"}` from the superclass. This remains true even if the subclass provides only a single element in its annotation.

If the subclass does not have `@IllustrationOnly` at all, the inherited lookup result can contain the values from the annotation on the superclass: `base`, `99`, `{"shared"}`.

Note that the `IllustrationOnly` snippet illustrates the defaults mechanism; it does not yet declare `@Inherited` and `@Retention` in the code fence. When practicing independently, you must add those exact meta-annotations.

## 8. When a Subclass Declares Multiple Annotations of Different Types

Suppose the superclass has `@Mode("base")` and `@Owner("base-owner")`, and the subclass only adds a custom-defined annotation of a **different type**, `@Component`. Declaring `@Component` does not mean all annotations from the superclass disappear.

The shadowing rule here operates **per annotation type**:

- If the subtype directly declares `Mode`, the `Mode` value inherited from the superclass is shadowed in the lookup result for `Mode`.
- If the subtype declares another type `Other`, the lookup for `Mode` can still walk up to the superclass, provided the inheritance conditions are met.
- An annotation type without `@Inherited` does not automatically gain an inheritance path just because the subclass omits annotations.

Therefore, you should not say "if a subclass has an annotation, it blocks all annotations on the superclass." More accurately, **declaring an annotation of the same type affects the lookup result for that same type**.

## 9. Boundaries of `@Inherited`

### 9.1. Interfaces Do Not Participate in the Superclass Lookup Chain

~~~java
@Mode("contract")
interface ServiceContract {}

class ServiceImpl implements ServiceContract {}
~~~

Even if `Mode` has `@Inherited`, `ServiceImpl.class.getAnnotation(Mode.class)` does **not** automatically search through `ServiceContract`. Annotations on interfaces and annotations on superclasses do not share the same Reflection inheritance rules.

If a framework wants to retrieve annotations from interfaces or from interfaces implemented by superclasses, the framework must traverse the type hierarchy itself and establish its own precedence rules.

### 9.2. Overridden Methods Do Not Automatically "Inherit Annotations" via `@Inherited`

~~~java
class ParentOperation {
    @Deprecated
    public void execute() {}
}

class ChildOperation extends ParentOperation {
    @Override
    public void execute() {}
}
~~~

This snippet is illustrative, not a complete program. `@Deprecated` on the superclass's method does not automatically become a declared annotation on the subclass's overriding method. `@Inherited` specifies inheritance semantics only for **class annotations**; the same rule does not apply to methods, fields, or parameters.

You must distinguish **method overriding** (how the language selects the method implementation to execute) from **class annotation inheritance** (how Reflection looks up a type of metadata). They are two different mechanisms.

### 9.3. `@Documented` Does Not Determine Annotation Precedence

`@Documented` causes an annotation to be included in the Javadoc of the annotated element. It does not create an inheritance path and does not define how a subclass shadows annotations. Under the topic of "documentation and inheritance," you must distinguish:

- `@Documented`: affects how the annotation appears in API documentation.
- `@Inherited`: affects the class annotation lookup rules when the current class does not yet have a matching annotation.
- `@Retention(RUNTIME)`: affects whether Reflection can read the annotation at runtime.

To accurately read retained annotations, you must consider the metadata, the annotated target location, and the specific query API.

## 10. Advanced Case: Repeatable Annotations

When an annotation type is declared with `@Repeatable`, Java code can place multiple annotations of the same type on a single element. The compiler can represent them via a **container annotation**; in that case, `getAnnotation(Tag.class)` does not share the same "read all" behavior as `getAnnotationsByType(Tag.class)`.

A valid repeatable configuration requires attention to `@Inherited` on both the repeatable annotation itself **and** its corresponding container; if the repeatable annotation has `@Inherited`, the container must also meet the inheritance requirement. Conceptual example:

~~~java
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

@Role("reader")
@Role("writer")
class BaseRoles {}

@Role("admin")
class ChildRoles extends BaseRoles {}
~~~

This example is a valid declaration snippet that can be used to observe the Reflection APIs.

With `ChildRoles.class.getAnnotationsByType(Role.class)`, the result is the subclass annotation `admin`, **without automatically adding** `reader` and `writer` from `BaseRoles`. The associated-annotation rules prioritize annotations of the same type directly or indirectly present on the subclass itself before searching superclasses.

If `ChildRoles` declares no `Role` annotations, `getAnnotationsByType(Role.class)` can return the `Role` annotations placed on the superclass according to the `@Inherited` rules. You should use `getAnnotationsByType` when the goal is to read all instances of a repeatable annotation type; `getAnnotation(Role.class)` may not return the expected element when annotations are wrapped in a container.

You do not need to master every detail of `@Repeatable` to grasp the main lesson. Keep the basic rule in mind: declaring the same **annotation type** on a subclass affects the inheritance result; with repeatable annotations, how the API determines presence also involves the container and the lookup method used.

## 11. Common Mistakes

**Mistake 1 — Forgetting `@Inherited`.** Placing `@Mode` on the superclass, calling `Child.class.getAnnotation(Mode.class)`, and receiving `null`. Check whether the annotation type has `@Inherited`; `RUNTIME` alone is not enough.

**Mistake 2 — Adding `@Inherited` but forgetting `RUNTIME`.** `@Inherited` describes the inheritance mechanism, but runtime Reflection cannot see annotation types with `CLASS`/`SOURCE` retention. When runtime reflection is needed, explicitly declare `@Retention(RUNTIME)`.

**Mistake 3 — Assuming elements are merged.** The superclass has `level = 7` and the subclass writes `@Mode("child")`, yet the program expects `level = 7`. Java produces the default value `1`; if merging is desired, you must implement your own rules.

**Mistake 4 — Confusing `getDeclaredAnnotation` with `getAnnotation`.** `getDeclaredAnnotation` only looks for declarations directly on the class itself, so `NoTag` returns `null` even though `getAnnotation` finds the inherited annotation.

**Mistake 5 — Assuming the superclass's metadata is modified.** A subclass annotation shadowing during lookup does not modify `Base.class`, does not overwrite `Base`'s class file, and does not change the result when querying the superclass itself.

**Mistake 6 — Assuming implementing an interface also inherits annotations.** `@Inherited` only searches a class's superclasses; interface annotations must be inspected manually by your code or framework if needed.

**Mistake 7 — Applying this mechanism to overridden methods.** A subclass method does not automatically inherit annotations from the identically named superclass method via `@Inherited`. Inspecting the `Method` on each class will show metadata according to the actual declarations and the API used.

**Mistake 8 — Interpreting "same type" as "same name."** Two annotation types in different packages are still two distinct types even if they share the same simple name. The rule compares the corresponding `Class<? extends Annotation>` objects, not merely the display name string.

**Mistake 9 — Overlooking repeatable annotations.** When a type has `@Repeatable`, the `getAnnotationsByType` lookup has container-traversal and inheritance semantics that differ from querying a single annotation. Choose the API according to the type of annotation being read.

## 12. Practice Exercises

1. **No declaration on the subclass:** Run `InheritedShadowDemo`. Before running it, predict `NoTag.class.getAnnotation(Mode.class)` and `getDeclaredAnnotation(Mode.class)`; explain why the two results differ.
2. **Shadowing the superclass annotation:** Change `@Mode("child")` to `@Mode(value = "child", level = 9)` on `Child`. Predict and verify which values `Child` and `Grandchild` receive.
3. **Removing the subclass annotation:** Remove `@Mode("child")` from `Child` (keeping `extends Base`). Re-run and explain why `Child`/`Grandchild` revert to receiving `base:7`.
4. **Removing `@Inherited`:** Remove that meta-annotation from `Mode`. Add safe `null` checks before reading values; predict how `NoTag` and `Grandchild` change.
5. **Removing runtime retention:** Switch `Mode` to `CLASS`. Predict `getAnnotation(...)` and explain why metadata may still exist in `.class` yet remain invisible to Reflection.
6. **Adding another type:** Create an additional `@Team("backend")` annotated with `@Inherited`, place it on `Base`, and override only `Mode` on `Child`. Compare the two separate queries on `Child`: `getAnnotation(Mode.class)` and `getAnnotation(Team.class)`.
7. **Interfaces and members:** Apply `@Mode` to an interface and test a class with `implements`. Create a `@Target(METHOD)` annotation on a superclass method, override that method in the subclass, and compare the two `Method.getDeclaredAnnotations()` results.
8. **Repeatable:** Run the `Role`/`Roles` snippet, print `Arrays.toString(...)` or iterate over `getAnnotationsByType(Role.class)` on `ChildRoles`. Then remove `@Role("admin")` from the subclass and verify inheritance.

## 13. Learning Summary

An annotation declared directly on a subclass **takes precedence** over an annotation of the same type that could be inherited from a superclass. If the subclass does not declare it, `@Inherited` allows Reflection to search sequentially for the nearest superclass. If the subclass does declare it, the subclass's values are the effective values of the found annotation; omitted elements take the annotation type's defaults and are not merged from the superclass. `getDeclaredAnnotation` answers **who declared it directly**, whereas `getAnnotation` answers **which annotation is considered present** under Java's rules.

To apply this reliably, check whether the annotation type has `@Inherited`, whether its retention allows runtime Reflection, which element kind the annotation is placed on, and which specific query API is being used.

### References

- [Java Language Specification 17 — `9.6.4.3: `@Inherited`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3).
- [Java SE 17 API — `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html).
- [Java SE 17 API — `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).
- [Java SE 17 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
