# Keep Annotation Elements Few, Meaningful, and Appropriately Typed in Java

Annotations in Java are **metadata declared directly in source code**. Each parameterless method declared inside an **@interface** is an **annotation element**: it determines what information users can provide, with what data type, and whether it must be provided.

A well-designed annotation should help readers understand the **intent** right at the site where the annotation is applied, keep the API concise, limit invalid states, and allow the library to evolve without breaking large numbers of usage sites. The principle is not “the fewer elements the better at all costs”, but rather to **represent only concepts that truly belong to the same annotation**, name them clearly, and choose data types that are both valid in the Java language and appropriate for the problem domain.

## 1. What Is an Annotation Element?

Consider the declaration:

~~~java
@interface Endpoint {
    String path();
    boolean enabled() default true;
}
~~~

**path()** and **enabled()** are two elements. They are written like parameterless methods, but they only declare a metadata value and have no body. The **default** syntax specifies a default value rather than an implementation of a regular Java interface method.

Usage:

~~~java
@Endpoint(path = "/orders")
class OrdersApi {}
~~~

Here:

- **path** is required information, because **path()** has no default.
- **enabled** is optional information, because **enabled() default true**. If not provided, the effective value of enabled is true.
- The annotation does not automatically open an endpoint or run a server. The metadata-consuming component (a framework, annotation processor, or reflection code) must read it and execute the corresponding behavior.

An annotation type is a special form of interface, defined with **@interface**. Element values must conform to the set of data types permitted by Java, rather than arbitrarily using any type as in Java fields or methods.

## 2. Start from the Minimum Information Users Need to Provide

Before adding an element, you should answer:

1. **What is the annotation representing?** A classification marker, an identifier, or a closely related group of parameters?
2. **Which values must the user decide at the declaration site?** Only this information should become required elements.
3. **Which values already have a stable convention in the library?** That value can become a default, as long as the default does not hide a dangerous decision.
4. **Are two elements truly independent?** If they can always be derived from each other, consider keeping one element and computing the remaining value in the consuming code.
5. **Is the set of values bounded?** If the set of choices is fixed, an enum usually expresses meaning better than a free-form string.
6. **Is the information stable at compile time?** Configuration that varies by account, deployment environment, or runtime request may not be suitable to encode as an annotation.

Example of a design containing too much configuration that is not tightly bound to the same meaning:

~~~java
// Example of a hard-to-maintain API: mixing route, retry, logging, and UI.
@interface MegaConfig {
    String path();
    int attempts() default 3;
    long delayMillis() default 100;
    boolean audit() default false;
    String[] roles() default {};
    String theme() default "light";
}
~~~

Although syntactically valid, the MegaConfig type creates a confusing “configuration bag”: changing the UI and changing retry behavior both force sharing the same annotation API, while the properties belong to different responsibilities.

A design separated by responsibility is clearer:

~~~java
@interface Route {
    String value();
}

@interface Retry {
    int attempts();
    long delayMillis() default 100;
}

@interface Audited {
}
~~~

Each annotation is responsible for only one aspect. Usage sites can combine them explicitly:

~~~java
@Route("/orders")
@Retry(attempts = 3)
@Audited
class OrderEndpoint {}
~~~

This is a simplified declaration example; it does not yet include **@Target** and **@Retention**, so it does not fully represent a runtime API. During implementation, meta-annotations need to accurately reflect where and when the metadata is read. A good design must also avoid over-splitting: if two values always belong to the same contract and only make sense together, keeping them in a single annotation with a clear shared name is reasonable.

## 3. Choose a Marker, One Element, or Multiple Elements

There are three basic forms:

| Form | Declaration | Usage | When Appropriate |
| --- | --- | --- | --- |
| **Marker** | **@interface Audited {}** | **@Audited** | Only a yes/no mark is needed, without storing configuration |
| **One element** | **@interface Route { String value(); }** | **@Route("/orders")** | There is only one central piece of information |
| **Multiple elements** | **@interface Retry { int attempts(); long delayMillis() default 100; }** | **@Retry(attempts = 3)** | There are multiple independent properties with the same purpose |

### 3.1. Marker: Do Not Add a Redundant Boolean

If you only want to mark that a class/method will be audited, **@Audited** is enough. Consider before designing:

~~~java
@interface Audited {
    boolean enabled() default true;
}
~~~

The boolean form is appropriate **only when you truly need to represent both enabled=true and enabled=false at the usage site**. If the annotation merely indicates participation in a policy, **@Audited**/not applying the annotation is a simpler API.

Do not use a marker to promise behavior that the system does not implement. **@Audited** does not write logs by itself; a processing component is needed to understand this marker.

### 3.2. One Element: Choose the Name value() When It Is the Primary Value

~~~java
@interface Route {
    String value();
}

@Route("/orders")
class Orders {}
~~~

If the single element is named **value()**, Java allows omitting **value =**. **@Route("/orders")** is the shorthand form of **@Route(value = "/orders")**.

There is no automatic shorthand rule for other names:

~~~java
@interface Owner {
    String team();
}

@Owner(team = "payments")
class Payments {}
~~~

**@Owner("payments")** will not compile because Owner does not have a **value()** element. You should not rename **team()** to **value()** just to save a few characters if the name **team** is what accurately explains the meaning and the API is often expanded into multiple properties.

### 3.3. Multiple Elements: Concise Yet Sufficient to Describe the Contract

~~~java
@interface Retry {
    int attempts();
    long delayMillis() default 100;
}
~~~

**attempts** and **delayMillis** both describe retry behavior, so grouping them together makes sense. **attempts** is required if each usage site needs to actively choose the number of attempts; **delayMillis** is optional when the library has a consistent default value.

Conversely, adding **timeoutMillis**, **route**, **logLevel**, **roles**, and **visibleInMenu** just because they “might be needed” often bloats the API before any real requirement exists.

## 4. Name Elements to Clarify Units and Meaning

An element should have a name that describes **the actual data it holds**, rather than an ambiguous name or a name that leads to a different interpretation.

| Weak Name | Clearer Name | Reason |
| --- | --- | --- |
| **n()** | **attempts()** | Expresses that this is the number of attempts |
| **delay()** | **delayMillis()** | No need to guess the time unit |
| **flag()** | **audited()** or a marker **@Audited** | Avoids an ambiguous boolean |
| **name()** | **routeName()**, **ownerTeam()** if distinction is needed | Clarifies the role of the string |
| **type()** | **handlerType()** | Distinguishes the handler class from a business type |
| **mode()** with an arbitrary String type | **Backoff mode()** with an enum type | Both the name and type reflect the set of choices |

Longer names are not always better. **path()**, **value()**, and **role()** can all be good names if the annotation context makes their meaning clear.

For primitive types that are easily misunderstood, names containing units such as **delayMillis()**, **timeoutSeconds()**, and **maxBytes()** help readers avoid passing the wrong unit. An annotation element of type **long** does not know the time unit on its own. The designer must define it in the name and documentation.

If an element has a boolean value, you should choose a name that reads like a predicate, such as **required()**, **enabled()**, or **audited()**; avoid **isFeature()** or **setEnabled()** if the naming makes users think it is a business method.

## 5. Valid Data Types for Annotation Elements

Java restricts the return type of an annotation element. According to the Java Language Specification §9.6.1, the valid categories are:

1. **Primitive types**: **boolean, byte, short, int, long, char, float, double**.
2. **String**.
3. **Class** or a permitted parameterization of **Class**, for example **Class<?>** or **Class<? extends Handler>**.
4. **Enum type**.
5. **Another annotation type**.
6. **A one-dimensional array** of one of the above categories.

Example of valid declarations:

~~~java
enum Backoff {
    FIXED,
    EXPONENTIAL
}

@interface Header {
    String name();
    String value();
}

@interface Settings {
    boolean enabled() default true;
    int maxAttempts() default 3;
    long timeoutMillis() default 500;
    String label() default "default";
    Class<?> handlerType() default Object.class;
    Backoff backoff() default Backoff.FIXED;
    Header header() default @Header(name = "Accept", value = "application/json");
    String[] tags() default {};
}
~~~

Points to remember:

- **String** is a specially permitted reference type, not every Java class.
- For **Class<?>**, the passed value is usually a *class literal* such as **String.class** or **SomeHandler.class**, not an arbitrary object created with new.
- An element of **enum** type accepts an enum constant, for example **Backoff.EXPONENTIAL**.
- An element of another annotation type accepts an **annotation value**, for example **@Header(name="Accept", value="application/json")**.
- **String[]** is a one-dimensional array; Java supports multiple elements or an empty array through the annotation element values syntax.

Types that are **invalid** as element types:

~~~java
// Incorrect: do not use these declarations in a real @interface.
// @interface Invalid {
//     Object object();
//     java.util.List<String> names();
//     java.util.Map<String, String> options();
//     int[][] matrix();
//     void run();
//     String calculate(String input);
// }
~~~

**Object**, **List**, and **Map** are not in the set of permitted element types; **int[][]** is a two-dimensional array; **void** is not a value type; and an annotation element also cannot accept parameters. An annotation **cannot** be used like a regular Java configuration class with constructors, collections, and arbitrary object graphs.

**Design tip:** If the information requires a complex List/Map, mutable objects, or values loaded at runtime, an annotation may not be the appropriate storage mechanism. Consider a configuration file, a Java class with clear types, or a framework-managed registry.

## 6. Choose an Enum Instead of String When Values Form a Closed Set of Choices

Suppose a retry policy only allows two modes:

~~~java
enum Backoff {
    FIXED,
    EXPONENTIAL
}

@interface Retry {
    int attempts();
    Backoff mode() default Backoff.FIXED;
}
~~~

Usage:

~~~java
@Retry(attempts = 3, mode = Backoff.EXPONENTIAL)
class PaymentClient {}
~~~

**Advantages of an enum:**

- The compiler checks constant names. A typo like **Backoff.EXPONETIAL** produces a compile-time error instead of a valid string that is not understood by the library.
- An IDE can suggest the set of choices.
- Metadata-consuming tools do not need to parse strings themselves and match against numerous literals.
- The API clearly states the expected value domain.

Compared to:

~~~java
@interface Retry {
    String mode() default "FIXED";
}
~~~

The strings **"FIXED"**, **"fixed"**, and **"unknown"** are all valid in terms of type; additional checks are needed to detect unsupported modes. Using String is still reasonable if the value domain is intentionally extensible via external registration and cannot be enumerated with a stable enum.

**Cost of an enum:** Changing/removing a constant name already used in metadata can cause legacy source code or previously compiled applications to encounter issues when reading the annotation in a new version. Published enum constant names should be treated as part of the API contract, and a versioning plan should be considered.

## 7. Choose Class Instead of a String Class Name

If an annotation needs to specify a **Java type**, use **Class** or **Class with a type bound**:

~~~java
interface Handler {}

final class DefaultHandler implements Handler {}

@interface UseHandler {
    Class<? extends Handler> value();
}

@UseHandler(DefaultHandler.class)
class PaymentGateway {}
~~~

Advantages:

- The compiler checks that **DefaultHandler** is actually a type compatible with **Handler**.
- The IDE recognizes references to the class when renaming/moving code.
- Reduces errors caused by misspelling package or class names in strings.
- Reflection can return a **Class<? extends Handler>** object when reading the element value according to runtime rules.

A weaker approach when the information is actually a Java type:

~~~java
@interface UseHandlerName {
    String value();
}

// This string is not checked by the compiler to be an existing class.
// @UseHandlerName("com.example.handler.DefautHandler")
~~~

**Class does not always replace String**. If the value is a plugin ID defined by an external system or may not be on the compile classpath, String can be an intentional decision. However, when the input is an existing Java class, a class literal usually represents the information more accurately.

**Note on annotation processing:** In the compiler model, class literal values are processed via **TypeMirror/AnnotationMirror**; calling a class-valued element from a compiler model proxy can cause a **MirroredTypeException** because the source has not yet been loaded as a class. Do not try to use Class.forName on source that is being compiled. In runtime reflection, Java can return a Class, but you still need to handle errors related to types that no longer exist in the binary if the library changes.

## 8. Use Arrays When Metadata Has a Small Set of Same-Type Values

An annotation element does not accept **List<String>**, but it can accept **String[]**:

~~~java
@interface RolesAllowed {
    String[] value();
}

@RolesAllowed({"reader", "editor"})
class DocumentController {}
~~~

**value()** can still be written in shorthand form, even though the element type is an array. For **a single element**, Java allows the short syntax:

~~~java
@RolesAllowed("reader")
class ReadOnlyController {}
~~~

Equivalent in value to **@RolesAllowed({"reader"})**.

Usage:

~~~java
@interface Tags {
    String[] value() default {};
}

@Tags
class Untagged {}

@Tags({"public", "v1"})
class PublicApi {}
~~~

Arrays are suitable for a simple, homogeneous set that is not too large. You **should not** force an entire tabular or multi-level tree configuration into multiple parallel arrays:

~~~java
// Error-prone because the two arrays must keep the same number of elements and the same order.
@interface BadHeaders {
    String[] names();
    String[] values();
}
~~~

A better design is **an array of nested annotations** so that related values are grouped per record:

~~~java
@interface Header {
    String name();
    String value();
}

@interface Headers {
    Header[] value() default {};
}

@Headers({
    @Header(name = "Accept", value = "application/json"),
    @Header(name = "X-Client", value = "web")
})
class ClientHeaders {}
~~~

Each Header holds exactly one name/value pair. You cannot mistakenly pass mismatched lengths for the names and values arrays.

However, if configuration has many levels, complex relationships, or needs continuous updates, consider a configuration file or another DSL instead of continuing to add more layers of nested annotations.

## 9. Defaults Help Reduce the Elements You Must Write — But Must Not Hide Important Decisions

**default** should only be applied when there is a reasonable and consistent value for the majority of usage sites.

~~~java
@interface Retry {
    int attempts();
    long delayMillis() default 100;
}
~~~

**@Retry(attempts = 3)** is concise because delayMillis has a default. If every usage site needs to choose attempts according to business policy, not declaring a default for attempts may be better.

In another API, if most cases truly need the number of attempts = 3 and differences are the exception, you can choose **attempts() default 3**. That is a domain decision, not a mandatory requirement of Java syntax.

### When Should You Avoid a Default?

- A value is a **required identifier** such as an API path, event code, or resource name.
- A default optional value could create **risky behavior**, such as granting access or enabling a critical feature.
- There is no single default with a clear meaning across all contexts.
- A missing value needs to be caught by the compiler rather than silently producing a configuration.

A marker annotation with no elements does not need a default. An annotation where **every element has a default** is still an annotation with elements, not structurally a marker.

### Changing a Default Can Affect Older Classes

According to JLS §9.6.2, default values are applied **when the annotation is read**, rather than being copied into each usage site. For example:

~~~java
@interface Retry {
    int attempts() default 3;
}

@Retry
class Billing {}
~~~

If the library changes **default 3** to **default 5** and runs with the new annotation type, the old binary of Billing that did not explicitly declare attempts can be read with the value 5 **without recompiling Billing**. This is a behavioral change even if it is not necessarily a change that breaks binary linkage.

Conversely, **@Retry(attempts = 3)** explicitly recorded the number 3, so it is not overridden by the new default.

Therefore, treat default values as **part of the public contract**. Upgrading safely requires identifying which usage sites depend on the default and which components will interpret it.

## 10. An API Problem: From a Hard-to-Use Design to a Clear Design

Suppose there is a library for making HTTP calls. The initial design:

~~~java
@interface HttpAction {
    String name();
    String value();
    String retry();
    String delay();
    String mode();
    boolean a() default false;
}
~~~

Problems:

- **name()** and **value()** are both String, with unclear roles.
- **retry()** and **delay()** are String even though integers are needed; they can accept invalid values such as "many" or "sometime".
- **mode()** is String while the value domain could be closed.
- **a()** does not express behavior.
- Users always have to provide a lot of unnecessary data, even when they only want to declare a simple route.

A more concise design:

~~~java
enum Backoff {
    FIXED,
    EXPONENTIAL
}

@interface Route {
    String value();
}

@interface Retry {
    int attempts();
    long delayMillis() default 100;
    Backoff backoff() default Backoff.FIXED;
}

@interface Audited {
}
~~~

Usage:

~~~java
@Route("/orders")
@Retry(attempts = 3, backoff = Backoff.EXPONENTIAL)
@Audited
class Orders {}
~~~

Each piece of information is represented by the exact appropriate type. **Route** has an identifier string, **Retry** has integers and an enum, and **Audited** is a marker. Splitting into three annotations makes the API clearer instead of cramming them into one general-purpose structure.

This is not a rule that you must always split into three annotations. If a framework genuinely has a single configuration concept requiring three inseparable properties, a multi-element annotation can still be the right choice. What matters is semantic cohesion.

## 11. Standalone Java 17+ Example: Few Elements and Readable Design

Create the file **src/demo/AnnotationDesignDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Audited {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Route {
    String value();
}

enum Backoff {
    FIXED,
    EXPONENTIAL
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Retry {
    int attempts();
    long delayMillis() default 100;
    Backoff backoff() default Backoff.FIXED;
}

class Gateway {
    @Route("/orders")
    @Audited
    @Retry(attempts = 3, backoff = Backoff.EXPONENTIAL)
    public void submit() {
    }

    @Route("/health")
    public void health() {
    }
}

public class AnnotationDesignDemo {
    public static void main(String[] args)
            throws NoSuchMethodException {
        describe("submit");
        describe("health");
    }

    private static void describe(String methodName)
            throws NoSuchMethodException {

        Method method = Gateway.class.getDeclaredMethod(methodName);

        Route route = method.getAnnotation(Route.class);
        Retry retry = method.getAnnotation(Retry.class);
        boolean audited = method.isAnnotationPresent(Audited.class);

        String routeValue = route == null ? "<none>" : route.value();

        System.out.println(methodName
                + ": route=" + routeValue
                + ", audited=" + audited);

        if (retry == null) {
            System.out.println("retry=<none>");
            return;
        }

        if (retry.attempts() <= 0) {
            throw new IllegalStateException("attempts must be positive");
        }

        System.out.println("retry=" + retry.attempts()
                + ", delayMillis=" + retry.delayMillis()
                + ", backoff=" + retry.backoff());
    }
}
~~~

From the directory containing **src**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/AnnotationDesignDemo.java
java -cp out demo.AnnotationDesignDemo
~~~

**Stdout:**

~~~text
submit: route=/orders, audited=true
retry=3, delayMillis=100, backoff=EXPONENTIAL
health: route=/health, audited=false
retry=<none>
~~~

### Analysis of the Design Decisions

1. **Audited** is a marker, without a boolean element **enabled()**. You only need to check **isAnnotationPresent(Audited.class)**.
2. **Route** has exactly one element **value()**, allowing you to write **@Route("/orders")**. The path is required information, so no default is declared.
3. **Retry** has three elements that together describe retry behavior; **attempts()** is required, while **delayMillis()** and **backoff()** have defaults suited to the example.
4. **delayMillis()** uses **long** and clearly states the millisecond unit; **backoff()** uses **enum Backoff** instead of a free-form String.
5. **@Target(METHOD)** explicitly states that the annotations are intended for methods. If a user tries to apply them to a class, the compiler will reject it. This is a way to make valid usage locations clear.
6. **@Retention(RUNTIME)** allows reflection to read metadata values on a Method at runtime.
7. **Gateway.health()** does not have Retry, so **getAnnotation(Retry.class)** returns null. The program distinguishes **not applying the annotation** from having the annotation and using defaults.
8. **attempts > 0** is a business constraint in the consuming code. The **int** type only guarantees an integer value and **does not automatically forbid zero or negative numbers**. The annotation does not enforce this validation on its own.
9. The program does not automatically send HTTP requests, perform retries, or write audit logs. The annotations here only produce metadata to be printed and checked.

The file has one public class **AnnotationDesignDemo**; the supporting annotation types, enum, and class are non-public, so they can appear together in a single source file belonging to the demo package.

## 12. Appropriate Data Types Are Not Enough: Validity Constraints Must Be Defined

Even when an element has the right type, the set of values permitted by Java may be larger than the set of values that make business sense.

For example, **int attempts()** still allows a user to write:

~~~java
@Retry(attempts = -2)
class BadClient {}
~~~

Negative numbers are valid for the int type, so **javac does not inherently know** that -2 is an invalid retry configuration. If the library needs to prevent that configuration:

- Use an **annotation processor** to read the value at compile time and report an error via **Messager** with **Diagnostic.Kind.ERROR**.
- Or use **reflection** to check at application startup, then report the configuration error before processing requests.
- Clearly state the limits, for example **attempts must be greater than 0** and **delayMillis must be non-negative**, in the annotation type documentation.
- Do not claim that domain constraints are checked just because Java performs type checking.

**String path()** also allows an empty string or a string that does not start with "/". The String type does not validate HTTP path rules by itself. If a format is truly fixed and the compiler can verify it, use an appropriate processor or analysis tool.

## 13. Impact of Element Choices on API Upgradeability

An annotation can be a public API used by hundreds of classes. When changing an element, three dimensions must be considered: **whether new source code compiles**, **whether already-compiled binaries can still be read**, and **whether metadata-consuming behavior changes**.

| Change | Risks to Evaluate |
| --- | --- |
| Add an element with a **default** | Existing usage sites usually do not have to pass the new element when recompiling; however, consuming tools may change behavior |
| Add a **required** element (no default) | Existing source code that does not declare the new element may fail to recompile; older binaries may lack a value when read |
| Rename an element | Sites using the old name are no longer valid; consuming code must also be modified |
| Change type from **String** to enum | Changes the source contract and already-compiled annotation data; requires migration |
| Remove an element/default | Can cause software reading older metadata to encounter errors or missing values |
| Change **default** from 3 to 5 | Can change the effective value of the annotation in older binaries even without recompiling |
| Rename an enum constant | Older usage sites may fail to find the constant when reading metadata in the new version |
| Expand **@Target** | Allows additional usage locations, but you must make sure consuming tools understand the new locations |

A safer example when **adding optional information**:

~~~java
// Initial version
@interface RetryV1 {
    int attempts();
}

// Evolved version adding an element with a default
@interface RetryV2 {
    int attempts();
    long delayMillis() default 100;
}
~~~

The two declarations above use **different names to illustrate before-and-after in the same code snippet**, not as a mandatory migration pattern. In a real library, if you want to evolve a single **Retry** type, you will modify the **Retry** definition across versions and evaluate compatibility according to the Java API.

When you must add a required element, consider whether every usage site truly needs to provide that information. If not, adding a reasonable default usually reduces the impact on older source code. However, **do not choose a dummy default just to make old code compile** when the value does not have a safe meaning.

## 14. @Target and @Retention Are Also Part of Minimalist Design

A small number of elements does not mean an annotation is well designed if where it is used or the lifetime of the metadata is unclear.

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Timed {
    long warningMillis() default 250;
}
~~~

**@Target(METHOD)** states that the annotation belongs to methods, not arbitrarily placed on classes/fields. **@Retention(RUNTIME)** is only chosen when code or a runtime framework needs reflection to query it.

If an annotation is only used by an **annotation processor** to generate code at compile time, **@Retention(SOURCE)** may be enough. If runtime reflection is needed, **RUNTIME** must be used. The default for an annotation when **@Retention** is omitted is **RetentionPolicy.CLASS**, not RUNTIME.

Do not add meta-annotations such as **@Inherited** or **@Repeatable** just to make it look complete. They have specific semantics and add constraints when tools read metadata. Use them when actual usage requirements call for annotation inheritance or repetition.

**Do not confuse** the number of annotation elements with the number of meta-annotations. **@Target** and **@Retention** are applied to the annotation type definition, but they are not elements of the **Timed** type.

## 15. When Should You Not Store Data in Annotations?

Suppose you need to map 20 endpoints to URLs that vary by environment (dev/staging/prod), tokens, quotas, and user-provided conditional expressions. If all of that had to live inside an annotation:

- Every configuration change may require editing source code or recompiling/redeploying.
- Valid Java annotation elements do not support arbitrary data structures such as rich Maps/Lists.
- Configuration data can quickly exceed the clarity of an annotation.
- Secrets such as passwords/API keys should not be embedded directly in class file metadata or a source repository.

A sensible design usually lets the annotation serve as an **identifying key or binding description**, while runtime data resides in configuration or dependency injection:

~~~java
@interface ConfigurationKey {
    String value();
}

@ConfigurationKey("billing.retry-policy")
class BillingClient {}
~~~

Here, the annotation only specifies a **key**. Application code then looks up the parameters in an appropriate configuration source, instead of stuffing many runtime values into the declaration. This example shows a separation of responsibilities; **@ConfigurationKey** itself does not automatically read configuration files.

## 16. Design Checklist Before Publishing a New Annotation

Before publishing a shared annotation, you should review:

- **Single responsibility:** The annotation name clearly expresses one purpose and does not bundle unrelated concerns.
- **Reasonable minimum number of elements:** Each element has a clear consumer and meaning; remove elements that can be derived from other elements.
- **Self-explanatory names:** Can readers understand **attempts()**, **delayMillis()**, and **ownerTeam()** without guessing units or meaning?
- **Strong typing:** Choose an enum when the set of choices is closed, **Class<? extends ...>** when referencing a Java type, primitives when values are truly numbers/booleans, and a one-dimensional array for a small list.
- **Required values enforced:** Do not overuse defaults to hide mandatory data.
- **Safe and meaningful defaults:** Can be applied consistently, are documented, and are tested because changing defaults can affect older binaries.
- **Right target:** Allow only the declaration/type-use contexts that the consuming component supports.
- **Right retention:** SOURCE, CLASS, or RUNTIME matches when the metadata is read.
- **Domain validation:** Business-invalid values such as negative numbers or empty paths are caught by the processor or application.
- **Upgradeability:** Have a plan when adding/removing/renaming elements or enum constants.
- **Usage documentation:** At minimum, include an example of applying the annotation, explain important elements, and describe what happens when the annotation is absent.

You can apply the rule **“every element must answer a necessary question”**. If you cannot clearly state the question, that element may not belong in the public API yet.

## 17. Common Mistakes and How to Fix Them

| Mistake | Problem | How to Fix |
| --- | --- | --- |
| Cramming route, auth, retry, logging, and UI into one annotation | Too many responsibilities | Split annotations by cohesive meaning |
| Adding boolean **enabled() default true** to a marker that needs no data | Complicates the interface | Use a true marker if only representing presence/absence |
| Using **String delay()** | No numeric or unit constraints | Use **long delayMillis()** |
| Using **String mode()** for a fixed set of choices | Allows string typos | Use an enum |
| Using **String handlerClass()** for an existing Java class | Reference is not checked by the compiler | Use **Class<? extends Handler>** |
| Declaring **List<String>** or **Map<...>** in @interface | Invalid element type | Consider a one-dimensional array or external configuration |
| Trying to declare **int[][]** | Two-dimensional arrays are invalid | Redesign the structure, possibly using nested annotations |
| Using an arbitrary default for a required path | Missing configuration goes undetected | Remove the default so the compiler requires passing it explicitly |
| Expecting enum/int to enforce all business rules on their own | The compiler only checks type/constant name | Add validation in a processor or at runtime |
| Changing a default while ignoring older binaries | Defaults are applied when the annotation is read | Test older classes that did not explicitly pass the element |
| Thinking **@Target** or **@Retention** are elements | They are meta-annotations of the annotation type | Distinguish annotation type configuration from its elements |
| Using parallel arrays **names** and **values** | Easy for lengths/order to get out of sync | Use an annotation array **@Header(name, value)** |
| Storing tokens/secrets in annotations | Values can remain in source/class metadata | Use an out-of-source secret management mechanism |

## 18. Exercises and Self-Check Answers

**Exercise 1.** Design an annotation solely to mark a method for auditing. Should you choose:

~~~java
@interface Audited {}
~~~

or:

~~~java
@interface Audited {
    boolean enabled() default true;
    String code() default "";
}
~~~

**Answer:** Choose the marker if only presence/absence is needed. Only add elements when there is genuinely an independent configuration decision that users must declare.

**Exercise 2.** Design an annotation for a required path and an HTTP method from the set **GET, POST, DELETE**, defaulting to GET. One option:

~~~java
enum HttpMethod {
    GET, POST, DELETE
}

@interface HttpRoute {
    String value();
    HttpMethod method() default HttpMethod.GET;
}
~~~

Use **@HttpRoute("/orders")** or **@HttpRoute(value = "/orders", method = HttpMethod.POST)**. **value()** fits the primary path; the enum helps avoid typos in method.

**Exercise 3.** Is **@Retry(attempts = 0)** guaranteed to cause a compile-time error when attempts() is an int? **No**. 0 is valid for the int type; only a processor or framework performing domain validation will reject it.

**Exercise 4.** Why is **@UseHandler(DefaultHandler.class)** better than **@UseHandlerName("demo.DefautHandler")** when the API needs a Java class? A class literal and **Class<? extends Handler>** are type-checked and supported by refactoring tools, whereas a string can be wrong without the compiler detecting it.

**Exercise 5.** If you need to store HTTP header pairs, which option is less error-prone: two String arrays for names/values or **Header[]** of nested annotations? **Header[]**, because each pair is kept within the same structure and indices cannot drift out of sync between two arrays.

**Exercise 6.** When changing the default of retries from 3 to 5, what value can an older class using **@Retry** receive if run with the new annotation type? **5**, if retries was not explicitly passed and the library reads the new type. A class using **@Retry(retries = 3)** still has the value 3.

**Exercise 7.** An API has 11 elements, 9 of which are only used in one environment-configuration component. Is it strictly necessary to remove those 9 elements? Not mechanically; you must examine responsibilities and runtime requirements. However, this is a sign to re-evaluate: it may be better to keep the annotation as a key and move volatile configuration elsewhere.

## 19. Official References

- **Java Language Specification §9.6.1 — Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1 — permitted element types, syntax, and constraints of annotation interfaces.
- **Java Language Specification §9.6.2 — Defaults for Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2 — how defaults are declared and the rule for applying them dynamically when reading annotations.
- **Java Language Specification §9.7 — Annotations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7 — name–value pair structure, value shorthand, and annotation element values.
- **Java SE 17 — ElementType:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html — locations that @Target can declare.
- **Java SE 17 — RetentionPolicy:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html — the SOURCE, CLASS, and RUNTIME policies.

**Conclusion:** A good annotation is a **small yet meaningful** metadata interface. Each element should have an easy-to-understand name, a tight type within Java's limits, an intentional required/default status, and a clear reason to exist. Choose a marker when only marking is needed, use **value()** for a single central piece of information, use enums/Class/arrays/nested annotations when the model calls for them, and move volatile/complex configuration outside instead of turning an annotation into an all-purpose configuration object.
