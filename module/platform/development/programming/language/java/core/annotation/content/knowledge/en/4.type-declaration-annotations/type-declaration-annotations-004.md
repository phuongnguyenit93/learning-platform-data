# Designing Marker, Single-Element, and Multi-Element Annotation Types in Java

Java allows defining an **annotation type** using the **@interface** keyword. Depending on the amount of data to be represented, an annotation type is typically designed in three forms: **marker annotation** (no elements), **single-element annotation** (one element), and **multi-element annotation** (multiple elements).

These three forms differ primarily in the **data contract** that the person writing the annotation must provide. They do not inherently determine whether the annotation operates at compile time or runtime: where it can be applied, how long it is retained, and who interprets the metadata are separate decisions.

## 1. Declaring an Annotation Type with @interface

Basic pattern:

~~~java
@interface TenAnnotation {
    // Annotation elements (if any)
}
~~~

Unlike a regular **interface**, an **@interface** declaration is used to define an annotation type. Its elements are written like parameterless methods, typically declaring a return type and a name, for example **String name();**. A semicolon ends the declaration; no method body is provided.

Some rules to keep in mind:

- The annotation type name follows Java type naming rules. It can be declared in a package and referenced by its short name after an import or by its fully qualified name, for example **@com.example.audit.Review**.
- A top-level annotation type declared **public** must reside in a source file with the same name, such as **public @interface Review** in **Review.java**. The multi-type examples in a single file below use non-public top-level annotations so they can run standalone.
- An annotation element may only return types permitted by Java: primitive types, **String**, **Class** (with valid type parameters), enums, an annotation type, or **one-dimensional arrays** of those types.
- Do not declare elements that accept parameters, a **void** return type, two-dimensional arrays, or arbitrary types such as **Object**, **List<String>**, or **Map<String, String>**.
- Each element may have **default** to specify a default value. If there is no default, the user must provide a value when applying the annotation.
- The value passed to an element must be a valid **annotation element value** at compile time: numbers and strings from appropriate constant expressions, enum constants, class literals, nested annotations, or arrays of permitted values. Do not use **null**, **new** to instantiate arbitrary objects, or data known only at runtime.

The type and element declarations determine the data structure. **@Target** and **@Retention** are meta-annotations commonly used to specify valid locations and the lifetime of metadata; they will appear in the complete example.

## 2. Marker Annotation: Marker Type Without Elements

A **marker annotation** has a body that declares no annotation elements. It expresses binary information at the declaration level: **marked** or **unmarked**.

~~~java
@interface Experimental {
}
~~~

Usage:

~~~java
@Experimental
class NewFeatureService {
}
~~~

If you only need to mark a class so that a tool or program can inspect it later, a marker annotation is the simplest design. For example, a program can look for classes annotated with **@Experimental** to issue a warning or apply a separate workflow. The **@Experimental** marker itself does not automatically enable any feature.

A marker has no elements, so you **must not** write:

~~~java
@Experimental(value = true)
class WrongFeatureService {
}
~~~

The snippet above **does not compile**: Experimental has no element named **value**. If you need to store a boolean, a status, or another piece of information, switch to an annotation with an appropriate element.

In addition to **@Experimental**, Java also allows the form **@Experimental()** because the name–value pair list is empty. The form without parentheses is more common for markers.

A common point of confusion: an annotation that declares multiple elements where **all have default** values can be applied without specifying values, yet structurally it is **not a marker annotation**. A true marker has **0 elements**.

**When to use a marker:** when the representation need is strictly yes/no, with no accompanying configuration data; for example, marking an internal API or indicating that a class participates in a processing step defined by a framework.

## 3. Single-Element Annotation: Type with Exactly One Element

If you need to pass exactly one piece of information, define one element:

~~~java
@interface Category {
    String value();
}
~~~

Usage has two valid forms:

~~~java
@Category(value = "payment")
class PaymentService {
}

@Category("report")
class ReportService {
}
~~~

**@Category("report")** is shorthand syntax for **@Category(value = "report")** because the element has the special name **value**. This is merely syntactic shorthand; the value and annotation type do not change.

If the single element has a name other than **value**, the name must be written explicitly:

~~~java
@interface Owner {
    String team();
}

@Owner(team = "backend")
class OwnedService {
}
~~~

With the declaration above, writing **@Owner("backend")** is invalid. The shorthand rule is tied to the **element name value()**; having only one element in an annotation does not by itself allow omitting the name.

### Providing Default Values

~~~java
@interface Category {
    String value() default "general";
}
~~~

With this declaration, **@Category** is valid and corresponds to **value = "general"**. However, consider whether a default value undermines the purpose of supplying an important piece of information: if each class is required to have its own category code, the **value()** element should not have a default.

An annotation that has a **value()** element and other elements with defaults also allows the shorthand form for **value** when the other elements are not specified:

~~~java
@interface Route {
    String value();
    boolean enabled() default true;
}

@Route("/users")
class UserRoute {
}

@Route(value = "/admin", enabled = false)
class AdminRoute {
}
~~~

In this example, **Route** is a **multi-element** annotation, even though the usage **@Route("/users")** looks like a single-element annotation. To determine the design form, you must look at the **type declaration**, rather than inferring it from the number of arguments at a single usage site.

## 4. Multi-Element Annotation: Type with Multiple Elements

When metadata needs to describe multiple attributes with independent meanings, declare each attribute as an element:

~~~java
enum Level {
    LOW,
    HIGH
}

@interface Review {
    String owner();
    int version();
    Level level() default Level.LOW;
    String[] tags() default {};
}
~~~

Here **Review** has four elements. The two elements **owner** and **version** are required; **level** and **tags** are optional because they have defaults.

Full usage:

~~~java
@Review(
    owner = "team-a",
    version = 2,
    level = Level.HIGH,
    tags = {"security", "critical"}
)
class PaymentComponent {
}
~~~

Usage providing only the required elements:

~~~java
@Review(owner = "team-b", version = 1)
class ReportingComponent {
}
~~~

When unspecified, **level()** has the value **Level.LOW** and **tags()** has an empty array. All elements are read by **name**, so the order of the pairs **owner = ...**, **version = ...**, **level = ...** is not a convention carrying business meaning.

With a multi-element annotation, element names help prevent confusion when passing values of the same type. For example, **owner** and **description** both have type String but represent two different concepts; clear naming helps readers understand the data right where the annotation is applied.

### Arrays as Element Values

The **String[] tags()** element accepts:

~~~java
@Review(owner = "team-a", version = 2, tags = {})
class NoTags {}

@Review(owner = "team-a", version = 2, tags = {"api", "public"})
class MultipleTags {}

@Review(owner = "team-a", version = 2, tags = "internal")
class SingleTag {}
~~~

When an element has an array type, Java allows omitting the curly braces when passing **a single** value of the corresponding component type. **tags = "internal"** is equivalent to **tags = {"internal"}**. For multiple elements, use curly braces as shown in the **MultipleTags** example.

### Defaults and API Design

Default values reside in the **annotation type declaration**, not attached to the class using it:

~~~java
@interface Retry {
    int attempts() default 3;
    boolean enabled() default true;
}
~~~

Correct: **int attempts() default 3;**. Incorrect: **int attempts() = 3;**.

If you add a new required element to an annotation that is already used in many places, existing annotation usages may no longer compile when recompiled. Adding a new element with **default** generally keeps existing calling code syntactically valid, though you must still consider the behavioral implications of the default value. Renaming or removing an element also affects source code referencing it.

## 5. Complete Java 17+ Example: Three Design Forms Side by Side

The following example demonstrates marker, single-element, and multi-element annotations together on classes, and then uses reflection to read the metadata.

Create the file **src/demo/AnnotationDesignDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Experimental {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

enum Level {
    LOW,
    HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Review {
    String owner();
    int version();
    Level level() default Level.LOW;
    String[] tags() default {};
}

@Experimental
@Category("payment")
@Review(
    owner = "team-a",
    version = 2,
    level = Level.HIGH,
    tags = {"api", "billing"}
)
class PaymentService {
}

@Category(value = "report")
@Review(owner = "team-b", version = 1)
class ReportService {
}

public class AnnotationDesignDemo {
    public static void main(String[] args) {
        printInfo(PaymentService.class);
        printInfo(ReportService.class);
    }

    private static void printInfo(Class<?> type) {
        System.out.println("class=" + type.getSimpleName());
        System.out.println(
            "experimental=" + type.isAnnotationPresent(Experimental.class)
        );

        Category category = type.getAnnotation(Category.class);
        System.out.println("category=" + category.value());

        Review review = type.getAnnotation(Review.class);
        System.out.println(
            "review=" + review.owner() + "/v" + review.version()
        );
        System.out.println("level=" + review.level());
        System.out.println("tags=" + Arrays.toString(review.tags()));
    }
}
~~~

From the directory containing **src**, run:

~~~bash
javac -encoding UTF-8 -d out src/demo/AnnotationDesignDemo.java
java -cp out demo.AnnotationDesignDemo
~~~

Exact stdout:

~~~text
class=PaymentService
experimental=true
category=payment
review=team-a/v2
level=HIGH
tags=[api, billing]
class=ReportService
experimental=false
category=report
review=team-b/v1
level=LOW
tags=[]
~~~

**Explanation of each form:**

1. **Experimental** has 0 elements. The code **isAnnotationPresent(Experimental.class)** checks whether that annotation is present on the specified class. PaymentService has the annotation so it yields true; ReportService does not so it yields false.
2. **Category** has exactly 1 element **value()**. PaymentService uses the shorthand form **@Category("payment")**; ReportService uses the full form **@Category(value = "report")**. **category.value()** returns the corresponding string.
3. **Review** has 4 elements. PaymentService specifies all values explicitly. ReportService specifies the required values **owner** and **version**; **level** and **tags** receive their defaults, printing **LOW** and **[]**.
4. The annotations are declared with **@Retention(RetentionPolicy.RUNTIME)** so that reflection can read them at runtime. **@Target(ElementType.TYPE)** is set to allow them to be applied to class declarations.
5. The example does not create an automatic service governance, auditing, or authorization mechanism. It only stores and then reads metadata; business behavior (if needed) must be determined by a framework, annotation processor, or application code.

In the **printInfo** method, both classes have Category and Review, so invoking the elements is safe in this example. In real programs, **getAnnotation(...)** can return **null**; you should check before calling methods on the result.

**Note on source files:** All annotations and helper enums in the example are non-public top-level types in the same **demo** package, while the only public class is **AnnotationDesignDemo**, so they can be placed together in a single source file as instructed.

## 6. Comparing the Three Forms in Design

| Criterion | Marker | Single-element | Multi-element |
| --- | --- | --- | --- |
| Number of declared elements | 0 | 1 | 2 or more |
| Declaration example | **@interface Experimental {}** | **@interface Category { String value(); }** | **@interface Review { String owner(); int version(); }** |
| Usage example | **@Experimental** | **@Category("payment")** | **@Review(owner = "team", version = 2)** |
| Information represented | Presence or absence of a mark | One configuration value | Multiple metadata fields |
| Value must be specified | No | Yes, unless the element has a default | Only elements without defaults |
| Design considerations | Name must clearly reflect the mark's meaning | Choose **value()** if there is one central value | Use specific element names and sensible defaults |

Choose the form based on the **meaning to be represented**:

- If you only need to mark a class for a tool to recognize, a marker avoids unnecessary data.
- If you need a single central code or label, a single-element annotation is sufficient; name it **value** when an intuitive shorthand syntax is desired.
- If you need multiple independent parameters such as owner, version, level, or tags, a multi-element annotation makes the declaration explicit. Only add elements when the metadata genuinely needs that information.

Annotations are suited for **metadata declared in source code** and processed according to specific rules. If a value changes frequently in the runtime environment, depends on the user, or needs immediate updates without rebuilding the application, the design may need a runtime configuration source instead of hardcoding every value into annotations.

## 7. Element Type Constraints and Default Annotations

The following examples illustrate valid values at the declaration site:

~~~java
@interface Settings {
    int limit() default 10;
    String label() default "default";
    Class<?> target() default String.class;
    Level priority() default Level.LOW;
    String[] names() default {};
}
~~~

Here **Level** is an enum declared in the same package or validly imported. **String.class** is a class literal, **Level.LOW** is an enum constant, and **{}** is an empty array. In an annotation, declaring **default** differs from assigning a field or a constructor parameter.

An annotation element can also have another annotation as its type:

~~~java
@interface TimeLimit {
    int millis() default 100;
}

@interface Action {
    TimeLimit timeout() default @TimeLimit;
}
~~~

In this example, **timeout()** is a single element of type TimeLimit, and **default @TimeLimit** is valid because TimeLimit's elements have defaults. **@TimeLimit** is a nested annotation value, not a constructor call. When focusing on how to design marker/single/multi-element annotations, look at the number of elements declared in each **@interface**; an element's value type can be another annotation without changing the classification principle.

The following declarations are invalid as annotation elements:

~~~java
// INVALID example - for error recognition only:
// @interface Invalid {
//     Object data();
//     java.util.List<String> tags();
//     int[][] matrix();
//     void run();
//     String find(String key);
// }
~~~

The reasons, respectively, are that the Object type is not allowed, collections do not belong to the set of valid types, two-dimensional arrays are not allowed, void is not a valid element type, and annotation methods do not accept parameters. These are language rules and do not depend on any framework.

## 8. Meta-Annotations Do Not Determine the Number of Elements

When designing a type, the following annotations commonly appear directly above the **@interface** declaration:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Trace {
    String value() default "";
}
~~~

- **@Target(ElementType.METHOD)** allows Trace to be applied to method declarations. If you try to place **@Trace** on a class, the compiler will report an error because the location is inappropriate.
- **@Retention(RetentionPolicy.RUNTIME)** allows retaining the annotation at runtime and accessing it via reflection. If retention is not specified, the default is **RetentionPolicy.CLASS**, meaning it is retained in the class file but generally not visible via reflection at runtime.
- **Trace** has one element **value()**, regardless of @Target and @Retention appearing above its declaration. Meta-annotations are annotations applied to the Trace type and are not counted as elements of Trace.

Marker, single-element, and multi-element annotations can all use @Target, @Retention, or other appropriate meta-annotations. Classification by the number of elements and the retention/applicability policy are two separate decisions.

## 9. Common Errors and How to Fix Them

| Error | Cause | Fix |
| --- | --- | --- |
| Writing **interface Flag {}** and then using **@Flag** | Flag is a regular interface, not yet an annotation type | Declare **@interface Flag {}** |
| Writing **@Experimental(true)** for a marker with no elements | No **value()** exists to receive true | Use **@Experimental**, or design an element if data is needed |
| Writing **@Owner("backend")** when the element is **team()** | Only the **value()** element supports omitting the name | Use **@Owner(team = "backend")** |
| Writing **@Review(owner = "team")** when **version()** is required | An element without a default is missing | Provide **version = ...** or define a default if appropriate |
| Writing **String name() = "x";** inside an annotation | Incorrect syntax for declaring a default | Use **String name() default "x";** |
| Writing **String[] tags() default null;** | Annotation values cannot be null | Use **default {}** if an empty default is needed |
| Writing **new Category("x")** instead of an annotation value | Annotations are not applied using object creation syntax | Use **@Category("x")** |
| Applying an annotation to a location outside its Target scope | **@Target** does not permit that location | Choose an ElementType appropriate for the design intent |
| Reading metadata via reflection and getting null | Wrong class/type or the annotation does not have RUNTIME retention | Check the target location, type, and retention |
| Treating an annotation as self-executing logic | An annotation is metadata and does not yet have an interpreter component | Write or integrate an intentional metadata processing mechanism |

In particular, an **annotation with defaults on all elements** is still an annotation with elements. For example, **@interface Options { boolean enabled() default true; }** belongs to the single-element form, even though **@Options** can be used without writing arguments.

## 10. Self-Check Exercises

**Exercise 1.** Classify the three declarations:

~~~java
@interface Internal {}

@interface Code {
    String value();
}

@interface Feature {
    String name();
    boolean enabled() default true;
}
~~~

Answer: **Internal** is a marker (0 elements); **Code** is single-element (1 element); **Feature** is multi-element (2 elements). The fact that Feature has a default for enabled does not make it single-element.

**Exercise 2.** Given the declaration:

~~~java
@interface Author {
    String name();
    String email() default "";
}
~~~

Is writing **@Author(name = "Mai")** valid? Yes, because only **name()** is required. Can you write **@Author("Mai")**? No, because there is no **value()** element.

**Exercise 3.** Why does **@Category("shop")** work while **@Category** does not when Category.value() has no default? Because the first form provides the required value for the **value()** element, whereas the second form omits it.

**Exercise 4.** If you want users to mark a class while also passing a severity level **HIGH/LOW**, is a marker sufficient? No. You can create a single-element annotation with an enum type, such as **@interface Severity { Level value(); }**, and then use **@Severity(Level.HIGH)**. If a reason and a responsible person are also needed, consider a multi-element annotation with clear element names.

When making a design decision, ask yourself: **Does it need to store values? If so, is a single value sufficient to express the meaning? Which fields are required, and which should have defaults? Is the value type among those permitted by Java?** Answering these questions will help you choose correctly among marker, single-element, and multi-element annotations before adding applicability policies or metadata-processing code.
