# @Inherited Applies Only Under Class Annotation Inheritance Rules in Java Reflection

In Java, **@Inherited** is a *meta-annotation* in the **java.lang.annotation** package, placed on an **annotation type declaration** to allow Reflection to see that annotation on a **subclass** when the annotation is declared on a **superclass**. However, the inheritance scope of @Inherited is narrower than intuition suggests: it applies to **annotations on class declarations** when looked up along the **superclass chain**, does not automatically propagate annotations from interfaces, does not propagate annotations of methods/fields to same-named methods/fields in a subclass, and does not create an actual annotation copy in the subclass's class file.

For example, if the annotation type **@Category** is marked @Inherited, class Base has @Category("service"), and class Child extends Base does not declare @Category, then **Child.class.getAnnotation(Category.class)** finds the annotation from Base. However, **Child.class.getDeclaredAnnotation(Category.class)** returns null, because Child does not directly declare @Category.

To understand Reflection behavior accurately, distinguish three things: **where the annotation is declared**, **whether the annotation type has @Inherited and @Retention(RUNTIME)**, and **whether the lookup API considers inherited annotations**.

## 1. Declaring an inheritable annotation properly

Example declaration of an annotation intended for classes:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}
~~~

Meaning of each meta-annotation:

- **@Inherited**: allows annotation queries on a subclass to walk up the superclass chain if the current class does not directly have an annotation of the same type.
- **@Retention(RetentionPolicy.RUNTIME)**: retains the annotation for Reflection to read at runtime. If @Retention is omitted, the default value is CLASS; the annotation may reside in the class file but is not exposed by Reflection through standard runtime APIs.
- **@Target(ElementType.TYPE)**: allows the annotation to appear on type declarations, including classes and interfaces. This does not mean annotations on an interface will be inherited by implementing classes.
- **@interface Category**: declares an *annotation interface*, while the @Inherited marker annotates that annotation interface itself, not class Base.

Usage:

~~~java
@Category("service")
class Base {}

class Child extends Base {}
~~~

The following queries have different meanings:

~~~java
Category inherited = Child.class.getAnnotation(Category.class);         // from Base
Category direct = Child.class.getDeclaredAnnotation(Category.class);   // null
~~~

These two snippets are illustrative fragments and must be placed together in a program or in the same package where Category, Base, and Child are declared.

**No annotation is copied into Child.** @Inherited affects the *lookup* rule in Reflection; it does not alter the class structure, methods, fields, or compiled bytecode of the subclass.

## 2. The inheritance rule walks only the class's superclasses

For an annotation type A that has @Inherited and is retained at runtime, when calling **SomeClass.class.getAnnotation(A.class)**, the general rule is:

1. If the class under inspection has annotation A directly, return that class's own A.
2. If there is no direct A, check the nearest **superclass**.
3. Continue walking up the superclasses until a matching A is found or the superclass chain ends (at Object).
4. If none is found, return **null**.

This rule is **only for annotations on class declarations**. It does not traverse implemented interfaces or superinterfaces.

Example:

~~~text
@Category("root") Base
                  │
                Middle
                  │
                Leaf

Leaf.class.getAnnotation(Category.class) -> Category("root")
~~~

If Middle declares **@Category("middle")**, then Leaf will see **"middle"** because it is closer to Leaf. If Leaf declares **@Category("leaf")** itself, Leaf's result is **"leaf"**. A direct annotation of the same type on a subclass **shadows** the inherited annotation of the same type; Java does not combine both.

### Interfaces and implements do not create @Inherited inheritance

~~~java
@Category("contract")
interface Contract {}

class ContractImpl implements Contract {}
~~~

Even though Category has @Inherited, **ContractImpl.class.getAnnotation(Category.class)** returns null. Even when a subinterface extends a parent interface, @Inherited **does not** turn an annotation on a superinterface into an inherited annotation on the subinterface.

The reason is that @Inherited is defined for queries on **class declarations** along the **superclass chain**. The implements/extends relationship between interfaces does not create this lookup path.

A framework may actively scan interfaces or meta-annotations according to its own rules, but that is a **framework** feature, not the default behavior of Class.getAnnotation in core Java.

### Nested classes do not automatically inherit annotations from their enclosing class

~~~java
@Category("outer")
class Outer {
    static class Nested {}
}
~~~

Nested resides inside Outer lexically, but does not **extend Outer**. Therefore Nested.class.getAnnotation(Category.class) does not receive "outer" merely from the nesting relationship. **Class inheritance** and **class nesting** are two different relationships.

## 3. Reflection APIs: getAnnotation and getDeclaredAnnotation

The **AnnotatedElement** interface provides a common API for reading annotations on Class, Method, Field, Constructor, Parameter, and other reflective elements. However, inheritance behavior depends on **which kind of element is being queried**.

| API | Finds direct annotations? | Can see annotations inherited from superclass? | Notes |
| --- | --- | --- | --- |
| **Class.getAnnotation(A.class)** | Yes | Yes, if A has @Inherited | Returns A or null |
| **Class.isAnnotationPresent(A.class)** | Yes | Yes, if A has @Inherited | Equivalent to getAnnotation(A.class) != null |
| **Class.getAnnotations()** | Yes | Yes, for inheritable types under present rules | Returns Annotation[] |
| **Class.getDeclaredAnnotation(A.class)** | Yes | **No** | Direct annotations only |
| **Class.getDeclaredAnnotations()** | Yes | **No** | Does not walk superclasses |
| **Class.getAnnotationsByType(A.class)** | Yes | Yes under **associated** rules, including @Repeatable | Returns A[] |
| **Class.getDeclaredAnnotationsByType(A.class)** | Yes | **No** | Unpacks @Repeatable container without inheritance |
| **Method/Field/Constructor.getAnnotation(A.class)** | Yes | **Not via @Inherited** | Annotations on a member do not transfer to another member |

Some terminology from the AnnotatedElement Javadoc:

- **Directly present**: annotation type A is directly represented on the element in the corresponding runtime annotation attribute.
- **Indirectly present**: annotation A is an element inside the **container annotation** of @Repeatable on the element.
- **Present**: directly present, or found along superclasses when A is inheritable and the element is a class.
- **Associated**: directly/indirectly present, or found along superclasses if A is inheritable and the current class has no direct/indirect A.

Distinguishing *present* and *associated* is especially important with **repeatable annotations**: getAnnotation/getAnnotations use the *present* relationship, while getAnnotationsByType uses the *associated* relationship.

### Short example distinguishing declared and inherited

~~~java
@Category("base")
class Base {}

class Child extends Base {}

boolean visible = Child.class.isAnnotationPresent(Category.class);       // true
boolean own = Child.class.getDeclaredAnnotation(Category.class) != null; // false
~~~

Child can “see” Category when queried via getAnnotation without **declaring** Category. This is not a bug, but two different lookup modes.

## 4. Do not confuse member inheritance with annotation inheritance

`@Inherited` governs only annotations on **class declarations**, even when the annotation type has `@Target(METHOD)`. `Child.class.getDeclaredMethod("run").getAnnotation(Audited.class)` is `null` if `Child.run()` overrides `Base.run()` while `Child.run()` itself is not marked `@Audited`.

Conversely, if `Child` **does not override**, `Child.class.getMethod("run")` may return the very `Method` declared by `Base`. In that case `method.getDeclaringClass() == Base.class`, and `Base.run()`'s annotation is still present **on the original method**. Inherited public fields behave similarly when Reflection returns the superclass `Field`; a hiding field is a new declaration. Constructors are not inherited, and parameter and type-use annotations do not automatically propagate either. The interface/method lesson goes deeper into traversing overrides and interfaces when a framework wants to search on its own.

## 5. Complete runnable Java 17+ example

This single example simultaneously demonstrates: an inherited class annotation via superclass; an annotation without @Inherited; an annotation on an interface; an annotation on an overriding method; and @Repeatable with @Inherited.

Save everything to **`InheritedLessonDemo.java`**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.Method;

public class InheritedLessonDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Inherited
    @interface Feature { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Local { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @Inherited
    @interface Audited {}

    @Feature("base")
    @Local("base-only")
    static class Base {
        @Audited public void execute() {}
    }
    static class Child extends Base {}
    @Feature("child")
    static class TaggedChild extends Base {}

    @Feature("interface")
    interface Service {}
    static class ServiceImpl implements Service {}

    static class OverrideChild extends Base {
        @Override public void execute() {}
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Inherited
    @Repeatable(Roles.class)
    @interface Role { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Inherited
    @interface Roles { Role[] value(); }

    @Role("reader") @Role("writer")
    static class RoleBase {}
    static class RoleChild extends RoleBase {}
    @Role("admin")
    static class RoleOwn extends RoleBase {}

    public static void main(String[] args) throws Exception {
        System.out.println("inherited feature=" + Child.class.getAnnotation(Feature.class).value());
        System.out.println("declared feature=" + (Child.class.getDeclaredAnnotation(Feature.class) != null));
        System.out.println("noninherited local=" + (Child.class.getAnnotation(Local.class) != null));
        System.out.println("override annotation=" + TaggedChild.class.getAnnotation(Feature.class).value());
        System.out.println("interface annotation inherited=" + (ServiceImpl.class.getAnnotation(Feature.class) != null));

        Method overridden = OverrideChild.class.getDeclaredMethod("execute");
        Method unchanged = Child.class.getMethod("execute");
        System.out.println("overridden method annotated=" + overridden.isAnnotationPresent(Audited.class));
        System.out.println("inherited method annotated=" + unchanged.isAnnotationPresent(Audited.class));
        System.out.println("method declaring=" + unchanged.getDeclaringClass().getSimpleName());

        System.out.println("repeatable inherited=" + RoleChild.class.getAnnotationsByType(Role.class).length);
        System.out.println("repeatable declared=" + RoleChild.class.getDeclaredAnnotationsByType(Role.class).length);
        System.out.println("repeatable getAnnotation null=" + (RoleChild.class.getAnnotation(Role.class) == null));
        System.out.println("repeatable local overrides=" + RoleOwn.class.getAnnotationsByType(Role.class)[0].value());
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 InheritedLessonDemo.java
java InheritedLessonDemo
~~~

Stdout verified when compiled with **javac --release 17** and run on JDK 24:

~~~text
inherited feature=base
declared feature=false
noninherited local=false
override annotation=child
interface annotation inherited=false
overridden method annotated=false
inherited method annotated=true
method declaring=Base
repeatable inherited=2
repeatable declared=0
repeatable getAnnotation null=true
repeatable local overrides=admin
~~~

Reading the results:

1. **inherited feature=base**: Child has no direct @Feature, so Class.getAnnotation walks up to Base to find @Feature("base").
2. **declared feature=false**: Class.getDeclaredAnnotation queries only direct annotations on Child.
3. **noninherited local=false**: @Local has runtime retention but lacks @Inherited, so it is not found via superclass by Child's Class.getAnnotation.
4. **override annotation=child**: TaggedChild declares @Feature("child") itself; the nearest direct annotation wins over Base's @Feature("base").
5. **interface annotation inherited=false**: ServiceImpl implements Service but does not receive @Feature on Service.
6. **overridden method annotated=false**: method execute overridden by OverrideChild does not receive @Audited, even though the @Audited type has @Inherited.
7. **inherited method annotated=true** and **method declaring=Base**: Child does not override, getMethod returns the original Method declared by Base, so the original annotation remains present.
8. **repeatable inherited=2**: RoleChild does not declare Role, so getAnnotationsByType finds the two Role annotations on the superclass and unpacks the Roles container.
9. **repeatable declared=0**: No direct/indirect Role in RoleChild's declaration.
10. **repeatable getAnnotation null=true**: on RoleBase, the two @Roles are represented by the compiler under **container @Roles**, so getAnnotation(Role.class) does not unpack the container to find Role elements. Use getAnnotationsByType(Role.class).
11. **repeatable local overrides=admin**: RoleOwn declares an own Role, so getAnnotationsByType(Role.class) gets the local Role("admin") and does not append the two Roles on the superclass.

### Trying changes to the annotation type

In the program above, remove **@Inherited** from @Feature and recompile. Then Child.class.getAnnotation(Feature.class) will return null, because @Feature is no longer inheritable; the line calling .value() directly will cause **NullPointerException**. To test safely, update the print line to check for null before reading value.

Similarly, changing RetentionPolicy.RUNTIME on Feature to RetentionPolicy.CLASS will prevent standard runtime queries from finding @Feature even while keeping @Inherited: both **retention** and **inheritance lookup** must align.

## 6. @Inherited combined with @Repeatable: look at the container

Since Java 8, an annotation type can be marked **@Repeatable(Container.class)** to appear multiple times on the same element. When also using @Inherited, you must understand the **base annotation** and the **container annotation**.

Proper sample declaration:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface Roles {
    Role[] value();
}
~~~

If **Role** has @Inherited, **the container Roles must also have @Inherited** according to the JLS rule on containing annotation types; if the container lacks it, the compiler rejects the invalid @Repeatable definition.

With:

~~~java
@Role("reader")
@Role("writer")
class Parent {}

class Child extends Parent {}
~~~

The compiler represents the two @Roles on Parent under a **container @Roles**. When reading annotations, pay attention to:

| Method on Child.class | Typical result |
| --- | --- |
| **getAnnotationsByType(Role.class)** | Array of two Roles ("reader", "writer") inherited under associated rules |
| **getDeclaredAnnotationsByType(Role.class)** | Empty array because Child does not directly declare Role |
| **getAnnotation(Role.class)** | null when Parent has two Roles contained by Roles |
| **getAnnotation(Roles.class)** | Can find the inherited container Roles |
| **getDeclaredAnnotation(Roles.class)** | null if Child does not declare container Roles |

**Do not equate getAnnotation(Role.class) with getAnnotationsByType(Role.class)**. The first only looks up a single *present* annotation under the AnnotatedElement model, while the second can **unpack the container** and handle multiple associated annotations.

With a direct @Role("admin") on Child, getAnnotationsByType(Role.class) returns Child's single direct Role; it does not append Parent's inherited Roles. Annotation inheritance does not automatically merge all values along the class tree.

A framework using annotations can design its own merge mechanism, but if you only want standard Java behavior, let getAnnotationsByType handle repeatable and inherited annotations instead of writing a loop that automatically accumulates superclasses.

## 7. Boundaries of `@Inherited`

| Situation | Does `@Inherited` apply automatically? |
| --- | --- |
| `class Child extends Parent` with annotation on `Parent` | Yes, if the annotation is runtime-retained and Child has no annotation of the same type. |
| `class Impl implements Interface` or `SubInterface extends Interface` | No, because it is not a class's superclass chain. |
| Method override, field hiding, constructor, formal parameter | No; each declaration has its own metadata. |
| Nested class in enclosing class, package/module annotation, type-use | No; nesting/type-location relationships differ from class inheritance. |
| Annotation attached to another annotation type | No; `Class.getAnnotation` does not automatically traverse the meta-annotation graph. |

When a framework wants to extend these lookup paths, it must define precedence and conflict resolution rather than attributing that capability to Java's `@Inherited`.

## 8. Practical applications when scanning runtime annotations

Suppose a framework scans classes to find inherited configuration:

- **If the annotation has @Inherited and the design requires inheriting configuration from a superclass**: use Class.getAnnotation(A.class) or Class.getAnnotationsByType(A.class) for repeatable annotations.
- **If you only want to know configuration written directly on the class**: use Class.getDeclaredAnnotation(A.class) or Class.getDeclaredAnnotationsByType(A.class).
- **If the framework needs to read annotations on interfaces**: actively use getInterfaces()/getGenericInterfaces() or an interface hierarchy utility; @Inherited does not help automatically.
- **If you need to read annotations on overriding methods**: identify the target method and, where appropriate, trace overridden declarations/superinterfaces with an explicit merge policy.
- **If using composed/meta-annotations**: you must traverse annotation types; Java's Class.getAnnotation does not do this out of the box.
- **If processing repeatable annotations**: use getAnnotationsByType to unpack containers rather than calling only getAnnotation.
- **If the annotation lacks runtime retention**: Reflection cannot rely on Class.getAnnotation to find it; review the @Retention configuration or use bytecode analysis if the problem genuinely needs CLASS metadata.

Example of writing a simple helper for class inheritance:

~~~java
static <A extends java.lang.annotation.Annotation> A inheritedOnClass(
        Class<?> type, Class<A> annotationType) {
    return type.getAnnotation(annotationType);
}
~~~

This is a method fragment. This function uses Reflection's standard mechanism itself and does **not** automatically traverse interfaces or methods. If annotationType is not marked @Inherited, the result is only the class's direct annotation (not searching superclasses via @Inherited).

### Notes when a framework allows annotations from multiple sources

If you want to combine superclass, interface, and method annotations, you must define a separate contract: whether the current class or superclass takes priority, whether multiple configurations are merged, which side wins when two interfaces declare different values, and whether meta-annotations are read. Do not label all of these merging strategies as standard @Inherited behavior.

Deep scanning also carries performance and ordering risks: cache results per class/annotation type when used repeatedly, handle cycles in the meta-annotation graph, and define clear precedence rules. For simple superclass rules, the Class.getAnnotation API already handles them.

## 9. Common mistakes

1. **Marking @Inherited on an annotation type and expecting method annotations to be inherited automatically:** incorrect. It applies only to class declarations.
2. **Assuming an annotated interface causes implementing classes to receive the annotation:** incorrect; Class.getAnnotation does not search through interfaces.
3. **Forgetting @Retention(RUNTIME):** the annotation will not appear through standard runtime Reflection.
4. **Confusing getDeclaredAnnotation with getAnnotation:** declared skips inherited annotations, even if the annotation type has @Inherited.
5. **Mistaking getMethod("run") finding an annotation for overriding method annotation inheritance:** check Method.getDeclaringClass(); it may actually be the superclass's method.
6. **Assuming @Inherited automatically merges annotations of the same type across levels:** a subclass's direct annotation shadows the inherited annotation of the same type; for repeatable annotations, getAnnotationsByType returns the nearest associated group per associated rules.
7. **Using getAnnotation to read a repeatable annotation with multiple values:** can yield null because the compiler stores a container. Use getAnnotationsByType.
8. **Forgetting @Inherited on the container of an inheritable repeatable annotation:** such a @Repeatable configuration is invalid per JLS.
9. **Assuming @Inherited scans meta-annotations:** incorrect. That is logic the framework or scanner must implement itself.
10. **Treating all annotations as identical at runtime:** @Target, @Retention, and the queried element kind all affect the result.

## 10. Self-check exercises

**Question 1.** @Feature is declared @Inherited and @Retention(RUNTIME). Base has @Feature("A"), Child extends Base declares no annotation. What is Child.class.getAnnotation(Feature.class)?

**Answer:** Feature("A"). Class.getDeclaredAnnotation(Feature.class) on Child returns null.

**Question 2.** If Child has @Feature("B"), does getAnnotation on Child return A or B?

**Answer:** B. Direct annotation on Child takes precedence over the same type on the superclass.

**Question 3.** Interface Contract has @Feature("I"), class Impl implements Contract. Does Impl.class.getAnnotation(Feature.class) return I?

**Answer:** No. @Inherited does not traverse implemented interfaces.

**Question 4.** Base.run is marked with annotation @Audited which has @Inherited. Child overrides run without writing @Audited. What does Child.class.getDeclaredMethod("run").isAnnotationPresent(Audited.class) return?

**Answer:** false. @Inherited does not propagate annotations on overriding methods.

**Question 5.** If Child **does not override** run and Child.class.getMethod("run") finds the public method on Base, can the @Audited annotation be read?

**Answer:** Yes, because the returned Method actually belongs to Base. Check Method.getDeclaringClass() to confirm; this is not annotation inheritance between two Methods.

**Question 6.** A superclass has @Role("read") and @Role("write") where Role is @Repeatable and @Inherited. The subclass does not declare Role. Which API should be used to get both values?

**Answer:** Class.getAnnotationsByType(Role.class). It unpacks the Roles container and applies associated rules.

**Question 7.** Annotation @Meta marks annotation type @Label. Class Sample has @Label but not @Meta. Does @Inherited on Meta cause Sample.class.getAnnotation(Meta.class) to find it automatically?

**Answer:** No. @Inherited does not automatically scan meta-annotations; a separate annotation-type scanning algorithm is required.

**Key takeaway:** **@Inherited adds only a lookup rule for runtime annotations on class declarations along the superclass chain.** Always check **@Retention(RUNTIME)**, distinguish **getAnnotation** from **getDeclaredAnnotation**, do not extrapolate to interfaces/methods/fields/constructors, and use **getAnnotationsByType** for repeatable annotations.

### References

- Java SE 17 — java.lang.annotation.Inherited: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html
- JLS 17 — §9.6.4.3 @Inherited and §9.6.3 Repeatable Annotation Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html
- Java SE 17 — java.lang.reflect.AnnotatedElement, definitions of directly present/present/associated: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- Java SE 17 — java.lang.Class, getAnnotation/getAnnotationsByType/getDeclaredAnnotation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 — java.lang.annotation.Repeatable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html