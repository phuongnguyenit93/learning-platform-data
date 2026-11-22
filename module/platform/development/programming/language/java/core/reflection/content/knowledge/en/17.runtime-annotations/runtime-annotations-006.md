# Annotations on Interfaces or Methods Do Not Propagate Automatically Like Class Annotations

In Java Reflection, annotations placed on **classes**, **interfaces**, and **methods** do not follow the same inheritance rules. The meta-annotation `@Inherited` only enables annotations on a **superclass** to be found when querying a **subclass** along the superclass chain. It does **not** automatically propagate annotations from an interface to an implementing class, from a superinterface to a subinterface, or from a parent/interface method to an overriding/implementing method.

Therefore, when handling **runtime annotations**, you must distinguish three things: where the annotation is **directly declared**, which **method** the Reflection method object represents, and whether the application requires additional lookup rules beyond standard Java Reflection. This distinction determines the results of `getAnnotation`, `getDeclaredAnnotation`, and related APIs.

## 1. Retention, Target, and Inherited are three distinct concepts

Define an annotation that can be placed on types/methods and read at runtime:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface Label {
    String value();
}
```

The snippet above is an **illustrative definition**, saved in `Label.java` if declaring a top-level `public` annotation. The complete example in section 4 declares `Label` inside a class so that only a single file is needed.

| Meta-annotation | Effect | Does not mean |
| --- | --- | --- |
| `@Retention(RUNTIME)` | Retains the annotation so Reflection APIs can read it at runtime | The annotation will be inherited |
| `@Target(TYPE)` / `@Target(METHOD)` | Allows applying the annotation at type or method sites | Annotations on interfaces/methods will propagate automatically |
| `@Inherited` | When querying an annotation on a **class**, if the class does not declare it, Reflection can search **superclasses** | Interfaces, methods, fields, and parameters automatically inherit annotations |

`@Inherited` is only a meta-annotation attached to the **annotation type definition**. Even though `Label` is allowed on methods (`@Target(METHOD)`), the `@Inherited` effect **still does not apply to methods**.

An annotation that needs to be observed via `Class.getAnnotation` or `Method.getAnnotation` must have runtime retention. The default retention if `@Retention` is omitted is `CLASS`, which is unsuitable for examples reading annotations at runtime.

## 2. Baseline for comparison: annotations on a superclass

Suppose `Label` has `@Inherited`, `@Retention(RUNTIME)`, and `@Target(TYPE)`, `Base` carries `@Label("base-class")`, while `Child extends Base` declares no label. When querying `Child.class.getAnnotation(Label.class)`, Reflection receives the label from `Base`; `Child.class.getDeclaredAnnotation(Label.class)` returns `null`. If `Child` itself carries `@Label("child-class")`, its own label wins.

This is a **lookup rule on class declarations**; it does not copy the annotation into `Child`'s bytecode. The next section contrasts this rule with interfaces and methods, which Java Reflection treats differently.

## 3. Interfaces and methods do not automatically inherit annotations

### 3.1. Interface annotated directly, implementing class does not get it automatically

```java
@Label("contract")
interface Contract {}

class Implementation implements Contract {}
```

`Contract.class.getAnnotation(Label.class)` returns the direct annotation on `Contract`. `Implementation.class.getAnnotation(Label.class)` returns `null` if `Implementation` has no matching annotation from a superclass. Likewise, `interface Sub extends Contract` does not automatically receive `Contract`'s annotation via `@Inherited`.

If a framework wants interface annotations to take effect on implementing classes, the framework must **actively search interfaces**, then apply its own policy on ordering and conflicts.

### 3.2. Overriding method does not automatically receive the parent method's annotation

```java
class Parent {
    @Label("parent-operation")
    public void execute() {}
}
class Child extends Parent {
    @Override
    public void execute() {}
}
```

`Child.class.getDeclaredMethod("execute").getAnnotation(Label.class)` returns `null` because method `Child.execute` is a new declaration and does not automatically receive `@Label` from `Parent.execute`. Even when `Label` carries `@Inherited`, Reflection does not automatically walk overridden methods.

Interface methods behave similarly: an annotation on `Contract.execute()` does not automatically appear on `Implementation.execute()`.

### 3.3. Inheriting a method **without overriding** is a different case

```java
class Parent {
    @Label("parent-method")
    public void work() {}
}
class Child extends Parent {}
```

`Child.class.getMethod("work")` can return the `Method` declared on `Parent`; `getDeclaringClass()` shows `Parent.class`. If we read `getAnnotation(Label.class)` on that `Method` itself, we still see `@Label("parent-method")` because **we are reading `Parent`'s method metadata**, not an annotation copied onto a different method on `Child`.

The examples in section 3 are separate illustrative scenarios; do not place multiple `Parent` classes with the same name in the same file. The next section contains a complete runnable program distinguishing these cases with distinct names.

## 4. Compilable/runnable Java 17+ example

Create the file `AnnotationInheritanceDemo.java` with the contents:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class AnnotationInheritanceDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    public @interface Label {
        String value();
    }

    @Label("base-class")
    static class Base {
        @Label("base-inherited-method")
        public void inheritedMethod() {}

        @Label("base-override-method")
        public void overriddenMethod() {}
    }

    static class Child extends Base {
        @Override
        public void overriddenMethod() {}
    }

    @Label("interface-type")
    interface Contract {
        @Label("interface-method")
        void execute();
    }

    static class Implementation implements Contract {
        @Override
        public void execute() {}
    }

    public static void main(String[] args) throws Exception {
        System.out.println("child.class=" +
                Child.class.getAnnotation(Label.class).value());
        System.out.println("child.declaredAbsent=" +
                (Child.class.getDeclaredAnnotation(Label.class) == null));

        System.out.println("interface.direct=" +
                Contract.class.getAnnotation(Label.class).value());
        System.out.println("implementation.interfaceAbsent=" +
                (Implementation.class.getAnnotation(Label.class) == null));

        Method inherited =
                Child.class.getMethod("inheritedMethod");
        System.out.println("inheritedMethod.owner=" +
                inherited.getDeclaringClass().getSimpleName());
        System.out.println("inheritedMethod.label=" +
                inherited.getAnnotation(Label.class).value());

        Method overridden =
                Child.class.getMethod("overriddenMethod");
        System.out.println("overriddenMethod.owner=" +
                overridden.getDeclaringClass().getSimpleName());
        System.out.println("overriddenMethod.labelAbsent=" +
                (overridden.getAnnotation(Label.class) == null));
        System.out.println("parentMethod.label=" +
                Base.class.getMethod("overriddenMethod")
                        .getAnnotation(Label.class).value());

        Method implemented =
                Implementation.class.getMethod("execute");
        System.out.println("implementedMethod.labelAbsent=" +
                (implemented.getAnnotation(Label.class) == null));
        System.out.println("interfaceMethod.label=" +
                Contract.class.getMethod("execute")
                        .getAnnotation(Label.class).value());
    }
}
```

Run in the directory containing the file, with Java 17 or later:

```bash
javac AnnotationInheritanceDemo.java
java AnnotationInheritanceDemo
```

Stdout result:

```text
child.class=base-class
child.declaredAbsent=true
interface.direct=interface-type
implementation.interfaceAbsent=true
inheritedMethod.owner=Base
inheritedMethod.label=base-inherited-method
overriddenMethod.owner=Child
overriddenMethod.labelAbsent=true
parentMethod.label=base-override-method
implementedMethod.labelAbsent=true
interfaceMethod.label=interface-method
```

**Explanation of each group of results:**

1. `Child` inherits the **class-level annotation lookup result** from `Base` because `Label` carries `@Inherited`. `getDeclaredAnnotation` still returns `null` because `Child` does not declare it itself.
2. `Contract` is annotated directly with `@Label`, so `interface-type` is read; `Implementation` implements `Contract` but does not automatically receive that annotation.
3. `inheritedMethod` is not overridden by `Child`; `Child.class.getMethod(...)` returns `Base`'s `Method` object, so `getDeclaringClass()` is `Base` and `Label` is still present on that method.
4. `overriddenMethod` is a method declared on `Child`; the `Label` annotation is not propagated from `Base`'s method. Querying `Base.overriddenMethod` directly still has `base-override-method`.
5. `Implementation.execute` does not automatically have `Contract.execute`'s annotation. To read `interface-method`, you must query the method declared on the interface.

The example only **reads metadata**; there is no need to call `setAccessible(true)` or invoke the target methods. The result does not depend on the return order of Reflection arrays.

## 5. Choosing the API by the element being queried

| API | When to use? |
| --- | --- |
| `getAnnotation(A.class)` / `isAnnotationPresent(A.class)` | Query a *present* annotation on an element; only when the element is a class can `@Inherited` be considered. |
| `getDeclaredAnnotation(A.class)` | Query only annotations declared directly, without searching superclasses. |
| `getAnnotations()` / `getDeclaredAnnotations()` | List annotations within the corresponding scope, without auto-unpacking repeatable containers. |
| `getAnnotationsByType(A.class)` / `getDeclaredAnnotationsByType(A.class)` | Also read indirect `@Repeatable` annotations inside containers, with or without applicable inheritance. |

On a `Method` representing an overriding declaration, both single-annotation getters read the **current method**; if you need annotations on a parent/interface method, you must actively traverse the method relationship. Do not infer that a method has received an inherited annotation just because `getMethod()` returned a declaration from a superclass.

## 6. When you want a parent method's annotation, you must traverse manually

A library sometimes wants an overriding method to use annotations declared on the parent method. That is a **custom-designed rule**; Java Reflection does not do this by default.

Example of a helper searching for a direct annotation on methods with the same name/signature along the superclass chain:

```java
import java.lang.annotation.Annotation;
import java.lang.reflect.Method;

static <A extends Annotation> A findFromClassHierarchy(
        Class<?> start,
        String methodName,
        Class<?>[] parameterTypes,
        Class<A> annotationType) {
    for (Class<?> current = start;
         current != null;
         current = current.getSuperclass()) {
        try {
            Method method = current.getDeclaredMethod(
                    methodName, parameterTypes);
            A annotation = method.getDeclaredAnnotation(annotationType);
            if (annotation != null) {
                return annotation;
            }
        } catch (NoSuchMethodException ignored) {
            // This class does not declare a method with the searched signature.
        }
    }
    return null;
}
```

This is an **illustrative helper** that must be placed inside a class and has no `main`. It can find `@Label("base-override-method")` on `Base.overriddenMethod` when starting from `Child` and not finding `Label` on `Child`'s method.

**Important limitation:** this snippet searches by **matching name and parameter types**, which does not prove the two methods have a valid Java override relationship. It does not exclude `private`, `static`, or synthetic/bridge methods, does not check visibility, and does not traverse interfaces. If a framework needs strict annotation inheritance semantics, it must handle these conditions explicitly, especially with generics, covariant returns, and multiple superclasses/interfaces.

## 7. To find annotations on interfaces, you also need a custom policy

In the program in section 4:

```java
Label interfaceLabel =
        Contract.class.getAnnotation(Label.class);
Method interfaceMethod =
        Contract.class.getMethod("execute");
Label methodLabel =
        interfaceMethod.getAnnotation(Label.class);
```

This snippet is **illustrative code**, requiring `Contract`/`Label` declarations, importing `Method`, and handling `NoSuchMethodException`. It directly reads annotations on the interface and the method declared by the interface; it does not make `Implementation` carry that annotation.

If a class dynamically implements multiple interfaces, you can access `Class.getInterfaces()` to traverse them yourself; consider superinterfaces and interfaces implemented by superclasses when the problem requires it, as well as avoiding duplicate visits. If two interfaces have the same annotation with different values, the application must define a precedence/conflict rule. **There is no default Java Reflection policy** dictating which interface annotation gets “propagated” to the implementation.

Frameworks can implement merged-annotation mechanisms, searching annotations across interfaces or method hierarchies according to their own policies. That is framework behavior and does not alter the contract of `@Inherited` or `Class.getAnnotation` in standard Java. When relying on a framework, verify the exact version and specific API.

## 8. Common misconceptions

| Misconception | Correct fact |
| --- | --- |
| `@Inherited` makes interface annotations propagate to implementing classes | Only inspects superclasses when querying a class; interfaces do not propagate automatically |
| `@Inherited` makes overriding methods receive annotations from the parent method | Does not apply to methods |
| `@Target(TYPE, METHOD)` gives annotations an inheritance mechanism in both places | Target only restricts where the annotation can be placed |
| `@Retention(RUNTIME)` means the annotation is inherited | Runtime retention only makes it visible to Reflection |
| `Child.getMethod("work").getAnnotation(...)` sees an annotation so the child method was annotated | If not overridden, the `Method` object can be the superclass's method |
| `getAnnotation` and `getDeclaredAnnotation` are equivalent | `getDeclaredAnnotation` reads only direct declarations; `getAnnotation` on a class can consider `@Inherited` |
| Annotations on `Contract.execute` automatically appear on `Implementation.execute` | Must query the interface method or use a custom search mechanism |
| A method with `@Override` copies annotations from the parent | `@Override` is a compile-time check and does not copy runtime annotations |
| A framework API finding interface annotations means standard Reflection does the same | The framework may traverse the hierarchy under additional rules |

## 9. Checklist for handling runtime annotations

1. **Identify the element containing the annotation:** class, interface, method, or another element? The `@Inherited` mechanism applies only to classes via superclasses.
2. **Check retention:** `RetentionPolicy.RUNTIME` is needed to read annotations via Reflection at runtime.
3. **Check target:** `ElementType.TYPE` for classes/interfaces, `METHOD` for methods; target does not specify inheritance.
4. **Choose the right API:** `getDeclaredAnnotation` for direct reads; `getAnnotation` when needing the element's “present” semantics.
5. **When reading an inherited method, check `getDeclaringClass()`:** you may be reading the parent method's metadata rather than a propagated annotation.
6. **When reading an overriding/implementing method, do not rely on @Inherited:** inspect the parent method/interface method explicitly when application policy requires it.
7. **When multiple annotation sources exist, define clear precedence:** superclasses, interfaces, overridden methods, repeatable containers, and conflicts must have a contract.
8. **Verify framework behavior with tests:** results from extended lookup mechanisms cannot be inferred from standard Reflection APIs alone.

## 10. Primary references

- [`@Inherited` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): inheritance scope limited to annotations on classes and superclasses.
- [`AnnotatedElement` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): meanings of present, declared, associated annotations, and query APIs.

**Key takeaway:** `@Inherited` takes effect only when **querying annotations on a class along the superclass chain**. Interfaces and methods have their own annotations; implementing classes or overriding methods do not automatically receive those annotations. When propagation from interfaces/methods is needed, build an explicit lookup rule and clearly check declaring class, override relationships, precedence, and runtime retention.