# annotationType() and the Actual Type of an Annotation in Java

When reading an annotation via reflection, we receive **an object representing the annotation value**. This object can be used to invoke elements such as **name()**, **value()**, or **version()**. However, it is necessary to distinguish:

1. **The annotation type declared with @interface**, for example **Route**.
2. **Annotation instance** returned when reading metadata, for example from **getAnnotation(Route.class)**.
3. **The runtime implementation class of that object** returned by **getClass()**. On common JDK releases, it is an internal proxy class; its name and how it is created are not a stable programming contract.

The **annotationType()** method belongs to **java.lang.annotation.Annotation** and returns **the Class representing the declared annotation type**, not the runtime implementation proxy class.

Example of the core idea:

~~~java
Route route = Service.class.getAnnotation(Route.class);

Class<? extends java.lang.annotation.Annotation> declaredType =
        route.annotationType();

Class<?> runtimeImplementation = route.getClass();
~~~

Here, **declaredType** represents the **Route** type, whereas **runtimeImplementation** is the actual class of the **route** object. These two Class objects do not have the same meaning. **route != null** must be checked before calling **annotationType()**.

## 1. Annotation type: the type defined by @interface

An annotation type is declared as follows:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Route {
    String path();
    int version() default 1;
}
~~~

**Route** is an **annotation interface** as termed in the Java Language Specification; its definition syntax is **@interface**. Java treats an annotation interface as a specialized kind of interface that implicitly extends **java.lang.annotation.Annotation**.

Important properties:

- **Route.class** is a **Class** object representing the Route type definition.
- **Route.class.isAnnotation()** returns **true**.
- **Route.class.isInterface()** also returns **true**, because an annotation type is a special kind of interface.
- **Route.class.getDeclaredMethods()** describes the declared elements such as **path()** and **version()**.
- **Route.class.getDeclaredMethod("version").getDefaultValue()** returns the default value **1** (boxed as Integer); if an element has no default, **getDefaultValue()** returns **null**.
- **@Retention(RUNTIME)** is an important condition when you want to retrieve an annotation from a class via reflection at runtime. Without it, the default is **RetentionPolicy.CLASS**.

An annotation type **is not an ordinary business class**. Do not use **new Route(...)** to create an annotation object. Java code applies annotations using the syntax **@Route(path = "...")**, while reflection APIs provide an object from which annotation elements can be read.

## 2. Annotation instance: the value obtained from reflection

Using Route:

~~~java
@Route(path = "/users", version = 2)
class UserService {
}
~~~

Reading:

~~~java
Route route =
        UserService.class.getAnnotation(Route.class);

if (route != null) {
    System.out.println(route.path());
    System.out.println(route.version());
}
~~~

**route** is an **annotation value** with static type **Route**. The calls **path()** and **version()** retrieve the element-values represented by the annotation.

If the class is not annotated with Route and has no matching inherited Route annotation, **getAnnotation(Route.class)** returns **null**. Therefore, you cannot call **annotationType()** or **path()** directly on the result without checking.

If the annotation is present but does not specify **version**, **route.version()** returns the **default 1** value, rather than null. These are two different situations:

- **Entire annotation is missing**: **getAnnotation(...) == null**.
- **Annotation is present, an explicit element-value is missing**: the element method receives the **default** if the annotation type declares a default.

Java does not automatically trigger routing when a class has **@Route**; the annotation only provides metadata. Frameworks or application code must read and process the metadata to produce behavior.

## 3. What does annotationType() return?

The contract of the **java.lang.annotation.Annotation** interface includes:

~~~java
Class<? extends java.lang.annotation.Annotation> annotationType();
~~~

This method returns the Class object representing **the annotation interface to which the annotation value belongs**.

With:

~~~java
Route route =
        UserService.class.getAnnotation(Route.class);

if (route != null) {
    System.out.println(route.annotationType() == Route.class);
}
~~~

The result is **true**. You do not need to know what internal mechanism the JDK used to create the Route instance.

The return value has the generic type **Class<? extends Annotation>** because the method on the Annotation interface must work for every annotation type. The actual Class object in the example is the Class representing **Route**.

### How does annotationType() differ from Route.class?

- **Route.class** is a **class literal** written directly in source code to represent the Route type.
- **route.annotationType()** is the result of querying **the annotation type of the route object** you have.

Both expressions can refer to **the same Class object** when the route object is indeed a Route value. The difference lies in **how the type information is obtained**, not in having two definitions of the Route type.

When the Route type is already known at compile time and you call **getAnnotation(Route.class)**, it returns a Route that already has the static type **Route**, so **annotationType()** is usually unnecessary to determine the type again. It is more useful when processing an **Annotation[]** collection consisting of multiple types unknown at the time of writing the code.

## 4. annotationType() is NOT the same as getClass()

**getClass()** is a method present on every Java object from **Object**. For an annotation instance, it indicates the actual implementation class of that instance at runtime.

~~~java
Route route = UserService.class.getAnnotation(Route.class);

if (route != null) {
    Class<? extends java.lang.annotation.Annotation> annotationClass =
            route.annotationType();

    Class<?> runtimeClass = route.getClass();

    System.out.println(annotationClass == Route.class); // true
    System.out.println(runtimeClass == Route.class);    // false
}
~~~

**Why is the last line false?** **Route** is an annotation interface; the **route** object must have a concrete implementation to exist at runtime. The implementation class is not the Route interface itself.

On many JVMs/JDKs, reflection implements annotation objects using a **dynamic proxy**, which may have an internal name formatted like **jdk.proxy...$Proxy...**. However:

- The runtime class name **is not stable** across JDK versions, module/class loader environments, or JVM implementations.
- Do not hardcode a proxy name, and do not compare proxy name strings to infer the annotation type.
- Do not treat the proxy class as the annotation type to pass into **getAnnotation(...)**.
- Do not infer whether an annotation is present or not by inspecting the implementation class name.

**The right way to know the annotation type** is **annotation.annotationType()**. If you want to know whether the object is actually a Route value, you can use **route instanceof Route**, **Route.class.isInstance(route)**, or check **annotationType() == Route.class** in a specific situation.

### Quick Comparison

| Expression | Meaning | Example Result |
| --- | --- | --- |
| **Route.class** | The declared annotation type | **demo.Route** |
| **route.annotationType()** | The annotation type that the route value represents | **demo.Route** |
| **route.getClass()** | The implementation class of the route object itself | Proxy/implementation class chosen by the JVM/JDK |
| **route.annotationType().isAnnotation()** | Is the declared type an annotation interface? | **true** |
| **route instanceof Route** | Is the object compatible with the Route type? | **true** |
| **Route.class.isInstance(route)** | Checks the object against the Class representing Route | **true** |

**Do not use getClass() == Route.class** to check an annotation object because this compares against the **interface**, not the implementation class.

## 5. Complete Java 17+ example, compiles and runs standalone

Create the file **src/demo/AnnotationTypeDemo.java**:

~~~java
package demo;

import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Route {
    String path();
    int version() default 1;
    String[] tags() default {};
}

@Route(path = "/users", tags = {"api", "public"})
class UserService {
}

@Route(path = "/users", tags = {"api", "public"})
class AnotherUserService {
}

class PlainService {
}

public class AnnotationTypeDemo {
    public static void main(String[] args)
            throws NoSuchMethodException {

        Route first = UserService.class.getAnnotation(Route.class);
        Route second =
                AnotherUserService.class.getAnnotation(Route.class);

        System.out.println("annotation type="
                + first.annotationType().getName());
        System.out.println("type is annotation="
                + first.annotationType().isAnnotation());
        System.out.println("same declared type="
                + (first.annotationType() == Route.class));

        Class<?> runtimeClass = first.getClass();
        System.out.println("runtime equals annotation type="
                + (runtimeClass == Route.class));
        System.out.println("instance of Route="
                + (first instanceof Route));

        System.out.println("path=" + first.path());
        System.out.println("version=" + first.version());
        System.out.println("tags=" + Arrays.toString(first.tags()));

        System.out.println("same values=" + first.equals(second));
        System.out.println("same hash code="
                + (first.hashCode() == second.hashCode()));

        Method versionMethod =
                Route.class.getDeclaredMethod("version");
        System.out.println("declared default="
                + versionMethod.getDefaultValue());

        Route missing = PlainService.class.getAnnotation(Route.class);
        System.out.println("plain has route=" + (missing != null));

        Annotation[] annotations =
                UserService.class.getAnnotations();
        for (Annotation annotation : annotations) {
            System.out.println("from Annotation[]="
                    + annotation.annotationType().getSimpleName());
        }
    }
}
~~~

Compile and run from the directory containing **src**:

~~~bash
javac -encoding UTF-8 -d out src/demo/AnnotationTypeDemo.java
java -cp out demo.AnnotationTypeDemo
~~~

**Exact expected stdout, independent of internal proxy names:**

~~~text
annotation type=demo.Route
type is annotation=true
same declared type=true
runtime equals annotation type=false
instance of Route=true
path=/users
version=1
tags=[api, public]
same values=true
same hash code=true
declared default=1
plain has route=false
from Annotation[]=Route
~~~

### Program Analysis

1. **UserService** has **@Route** directly and Route is retained until runtime; **getAnnotation(Route.class)** returns a non-null Route object.
2. **first.annotationType().getName()** is **demo.Route**, the full name of the annotation type; not the runtime proxy name.
3. **isAnnotation()** yields true because Route is declared with **@interface**.
4. **getClass() == Route.class** yields false because Route.class is the annotation interface whereas **getClass()** indicates the actual implementation class.
5. **path()** returns "/users"; **version()** returns 1 because the **version()** element is not explicitly passed and has **default 1**.
6. **tags()** returns **String[]**; **Arrays.toString(...)** prints in the format **[api, public]**.
7. The two classes UserService and AnotherUserService use the Route annotation with equal element values, so **equals()** returns true, and equal annotation objects must have the same **hashCode()**.
8. **Method.getDefaultValue()** inspects the **version()** element in the Route type definition and returns **1**, without needing to know which class the annotation is applied to.
9. **PlainService** is not annotated with Route, so **getAnnotation(Route.class)** returns null; the program checks for null instead of calling methods on the result.
10. **getAnnotations()** returns the annotations present on UserService; the loop uses the general **Annotation** type, so **annotationType()** identifies each annotation type when iterating over a collection that may contain multiple types.

The example intentionally **does not print runtimeClass.getName()** to avoid tying the lesson's output to a proxy class name that Java does not guarantee to be stable.

## 6. When working with Annotation[]: type identification and safe casting

When you do not know in advance what type each element of an annotation array has, **annotationType()** is especially useful:

~~~java
import java.lang.annotation.Annotation;

for (Annotation a : UserService.class.getAnnotations()) {
    Class<? extends Annotation> type = a.annotationType();

    System.out.println("found: " + type.getName());

    if (type == Route.class) {
        Route route = Route.class.cast(a);
        System.out.println("path: " + route.path());
    }
}
~~~

The snippet above belongs to package demo and assumes Route/UserService already exist as in the complete example.

The check **type == Route.class** clearly expresses that the queried Annotation value belongs to **the Route annotation type**, rather than depending on the internal implementation class.

**Route.class.cast(a)** is a runtime-checked cast. Once the exact type is determined, specific elements such as **path()** and **version()** can be called.

Writing with **instanceof** is also valid and usually shorter when only one known type is of interest:

~~~java
for (Annotation a : UserService.class.getAnnotations()) {
    if (a instanceof Route route) {
        System.out.println(route.path());
    }
}
~~~

This snippet uses **pattern matching for instanceof**, supported in Java 17. When you need to work with many different annotation types, **annotationType()** provides access to the Class to use type-based reflection APIs.

**You should not cast based on getClass().getSimpleName()** or based on a proxy-name string. Those implementation details are not part of the public interface of the annotation type.

## 7. annotationType() and the annotation equals/hashCode contract

**java.lang.annotation.Annotation** specifies that annotation values are compared by **annotation type and element values**, not by reference address or runtime proxy name.

Example:

~~~java
@Route(path = "/health", version = 1)
class HealthA {
}

@Route(path = "/health")
class HealthB {
}
~~~

When read using the same Route definition with **version() default 1**, the two annotations represent the same type and the same effective element-values, so **equals()** returns true:

~~~java
Route a = HealthA.class.getAnnotation(Route.class);
Route b = HealthB.class.getAnnotation(Route.class);

System.out.println(a.equals(b)); // true
~~~

This demonstrates that **the default value of an annotation element** is also used to determine the effective value when read. Two annotations do not necessarily need to have identical source syntax to be equal.

Principles:

- Two annotations cannot be equal if they belong to **two different annotation types**.
- Two annotations of the same type are equal when each corresponding element has an equal value according to annotation rules, including **arrays** being compared by array content.
- If **a.equals(b)** is true, then **a.hashCode() == b.hashCode()** according to the hashCode contract.
- **a == b** only compares object identity; it is not the needed annotation value check.
- **a.getClass() == b.getClass()** is not a condition that guarantees annotation values are equal or have the same annotation type according to the API.

**Do not implement your own equals based on getClass() of an annotation object.** When you need to compare annotation values, use **equals()**; when you need to classify by annotation type, use **annotationType()**.

## 8. annotationType() is not the Class of the annotated element

Note two semantically different Class objects:

~~~java
Route route = UserService.class.getAnnotation(Route.class);

Class<?> annotatedClass = UserService.class;
Class<? extends java.lang.annotation.Annotation> type =
        route.annotationType();
~~~

**annotatedClass** is the class **annotated with the annotation**; **type** is the type **of the annotation**. They are not the same.

For example:

- UserService.class can be annotated with multiple annotations, each having its own type.
- One Route annotation type can be used on many classes; **annotationType()** on each Route value always yields **Route.class**.
- **Class.getAnnotation(Route.class)** asks whether the UserService class has the Route annotation.
- **Route.class.getAnnotation(...)** queries another annotation applied **on the Route type declaration itself**, such as **@Retention** or **@Target**. This is not a query about UserService.

To check whether a Class is an annotation type:

~~~java
System.out.println(Route.class.isAnnotation());       // true
System.out.println(UserService.class.isAnnotation()); // false
~~~

If you have a **Class<?>** of unknown type, check **isAnnotation()** before treating it as an annotation type. The Java type **Annotation.class** represents the base interface, not an annotation interface defined with **@interface** to be applied directly in source code.

## 9. Accessing metadata of the annotation type itself from annotationType()

Once you have an Annotation instance, you can query the meta-annotations on its type:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

Annotation a = UserService.class.getAnnotation(Route.class);
if (a != null) {
    Class<? extends Annotation> type = a.annotationType();

    Retention retention = type.getAnnotation(Retention.class);
    Target target = type.getAnnotation(Target.class);

    if (retention != null) {
        RetentionPolicy policy = retention.value();
        System.out.println(policy); // RUNTIME, for the Route in the example
    }

    if (target != null) {
        System.out.println(
                java.util.Arrays.toString(target.value()));
        // [TYPE], for the Route in the example
    }
}
~~~

Here, **Retention** and **Target** are meta-annotations placed on **the Route type**. Querying **type.getAnnotation(Retention.class)** inspects Route's configuration, rather than retrieving Retention directly from UserService.

To list the elements defined by Route:

~~~java
Class<? extends Annotation> type = a.annotationType();

for (java.lang.reflect.Method element : type.getDeclaredMethods()) {
    System.out.println(element.getName()
            + " -> " + element.getReturnType().getTypeName());
}
~~~

When order does not matter, this loop is valid; **the order of Methods returned by reflection is not guaranteed by Java**. You should not write tests that rely on a fixed order of getDeclaredMethods().

You can read **Method.getDefaultValue()** on each element. The return value may be null if the element does not declare a default. Do not confuse **element default == null** with **the annotation not existing**.

## 10. Do TYPE_USE, @Inherited, and @Repeatable change annotationType()?

**No.** These mechanisms affect **where an annotation can appear or how it is retrieved**, rather than changing the type returned by **annotationType()** on an obtained annotation value.

### Annotation on a type use (TYPE_USE)

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {
}

class Example {
    @NonNull String name;
}
~~~

To read the annotation on **the String type** of the field:

~~~java
java.lang.reflect.Field field =
        Example.class.getDeclaredField("name");

NonNull nonNull =
        field.getAnnotatedType().getAnnotation(NonNull.class);

if (nonNull != null) {
    System.out.println(nonNull.annotationType() == NonNull.class);
    // true
}
~~~

The reflection snippet above must be placed inside a method with **throws NoSuchFieldException** or corresponding exception handling. **Field.getAnnotation(NonNull.class)** does not replace **Field.getAnnotatedType().getAnnotation(...)** because the example only declares the TYPE_USE target; the two APIs query two different metadata locations.

### Annotation looked up through a superclass (@Inherited)

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

@Category("backend")
class Parent {
}

class Child extends Parent {
}
~~~

If an import for **java.lang.annotation.Inherited** is declared, the method **Child.class.getAnnotation(Category.class)** can find Category from Parent thanks to @Inherited. When a value is obtained, **annotation.annotationType()** is still **Category.class**. It does not become **Child.class** or another “inherited annotation type”.

**getDeclaredAnnotation(Category.class)** on Child returns null because Child does not directly declare Category.

### Repeatable annotations (@Repeatable)

~~~java
import java.lang.annotation.Repeatable;

@Repeatable(Tags.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("fast")
@Tag("safe")
class Job {
}
~~~

To retrieve the individual repeated Tag annotations, use:

~~~java
Tag[] tags = Job.class.getAnnotationsByType(Tag.class);

for (Tag tag : tags) {
    System.out.println(tag.annotationType() == Tag.class); // true
}
~~~

The container annotation, if read separately, has the type **Tags**, not Tag:

~~~java
Tags container = Job.class.getAnnotation(Tags.class);
if (container != null) {
    System.out.println(container.annotationType() == Tags.class);
    // true
}
~~~

Do not confuse the number of annotations returned with **the annotation type of each instance**. The repeatable rule can store one container for multiple Tag values, yet **tag.annotationType()** still identifies the Tag type for each tag value.

## 11. Common limitations and mistakes

| Mistake or assumption | Problem | How to understand/fix |
| --- | --- | --- |
| **annotation.getClass() == Route.class** is expected to be true | getClass() is the implementation class, Route.class is the annotation interface | Use **annotation.annotationType() == Route.class** |
| Using **annotation.getClass().getName()** as a configuration identifier | The proxy/runtime class name is an implementation detail | Use **annotation.annotationType().getName()** |
| Calling **getAnnotation(...).annotationType()** immediately | getAnnotation can return null | Check the object before calling |
| Using **new Route(...)** | An annotation type is not created directly with a constructor like an ordinary object | Apply **@Route(...)** and read via the appropriate API |
| Comparing annotations with the **==** operator | Compares identity instead of element-values | Use **equals()** when the goal is comparing values |
| Using **getClass()** to implement a custom equals for an annotation value | The implementation class is not part of the annotation type contract | Rely on the **Annotation.equals/hashCode** contract |
| Confusing **Route.class** with **UserService.class** | One is the annotation type, the other is the annotated class | Name variables clearly: annotationType and annotatedClass |
| Expecting **getAnnotation** to see an annotation without runtime retention | Default retention is CLASS | Add **@Retention(RUNTIME)** if runtime reading is needed |
| Using **Class.getAnnotation** to read TYPE_USE on a field | Queries the wrong metadata location | Use **Field.getAnnotatedType()** or the appropriate AnnotatedType |
| Assuming **annotationType()** indicates where the annotation is applied | It returns the type, not the usage location | Keep the reflection element/location information separately |
| Assuming an element default makes the annotation present automatically | Defaults only apply when the annotation exists | Check **getAnnotation(...) != null** first |
| Traversing repeatable annotations only with **getAnnotation(Tag.class)** | A container may exist instead of a direct Tag | Use **getAnnotationsByType(Tag.class)** |

### Distinguishing getClass, instanceof, and annotationType

If you already have an **Annotation a** of unknown type:

~~~java
if (a instanceof Route route) {
    System.out.println(route.path());
}
~~~

This is a clear Java 17 expression when you need to handle **a specific type**. If the program needs to obtain **the Class of the annotation type** for generic analysis via reflection, use:

~~~java
Class<? extends java.lang.annotation.Annotation> type =
        a.annotationType();
~~~

If you need to find **the runtime implementation class for debugging**, you can use **a.getClass()**, but do not rely on that detail to make business logic decisions.

## 12. Self-check exercises

**Exercise 1.** Given:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@interface Flag {
}

@Flag
class FeatureA {
}
~~~

Assume **Retention** and **RetentionPolicy** have been imported. Obtain **Flag f = FeatureA.class.getAnnotation(Flag.class)**. Compare:

- **f.annotationType() == Flag.class**: **true**.
- **f.getClass() == Flag.class**: **false** because Flag.class is the annotation interface, not the object's implementation class.
- **f instanceof Flag**: **true**.
- **f.annotationType().isAnnotation()**: **true**.

**Exercise 2.** A class is not annotated with Flag. What does **SomeClass.class.getAnnotation(Flag.class)** return if there is no matching annotation inheritance relationship? **null**. You need to check it before calling **annotationType()**.

**Exercise 3.** Two classes have **@Route(path = "/health")** and **@Route(path = "/health", version = 1)**. If Route.version() has **default 1** and the remaining elements are equal, are the two annotation values equal? **Yes**, because the effective element-values are equal.

**Exercise 4.** In the loop **for (Annotation a : clazz.getAnnotations())**, you need to record the annotation type name. Should you choose **a.annotationType().getName()** or **a.getClass().getName()**? **Choose annotationType().getName()**. getClass() provides the implementation class name, which can change.

**Exercise 5.** Given **Tag[] tags = Job.class.getAnnotationsByType(Tag.class)**, is **tags[0].annotationType()** equal to Tags.class? **No**, each element in the array is a Tag, so it returns **Tag.class**; the container annotation **Tags** (if queried separately) has **annotationType() == Tags.class**.

**Exercise 6.** To read the default value declared on the version() element of Route, which method should you use? **Route.class.getDeclaredMethod("version").getDefaultValue()**. This method reads the default from the type definition; it does not require a specific Route instance.

## 13. Official Java documentation

- **Java SE 17 — Annotation:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html — the **annotationType()**, **equals()**, **hashCode()**, and **toString()** contract of annotation values.
- **Java SE 17 — AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — **getAnnotation(...)**, **getDeclaredAnnotation(...)**, **getAnnotationsByType(...)**, and annotation retrieval rules.
- **Java SE 17 — Class:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — **isAnnotation()**, **isInstance(...)**, **getName()**, **getDeclaredMethods()**.
- **Java SE 17 — Method.getDefaultValue():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue() — retrieves the default value declared for an annotation element.
- **Java Language Specification §9.6 — Annotation Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6 — defines annotation interfaces, their elements, and related language behavior.

In summary: **annotationType() returns the annotation interface that the annotation value represents**. **getClass() returns the implementation class of the runtime object**, which is typically a proxy and is not stable for use as the annotation type name. When writing reflection code, use **annotationType()** to classify or inspect annotation types, **equals()** to compare annotation values, and always **check for null before reading** the result of getAnnotation(...).
