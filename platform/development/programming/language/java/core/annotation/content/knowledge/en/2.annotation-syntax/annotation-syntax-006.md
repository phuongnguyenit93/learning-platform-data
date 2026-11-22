# Passing Nested Annotations as Values in Java

An **annotation can accept another annotation as the value of an element**. In its declaration, the outer annotation's element has an **annotation type** as its type. When using it, you write the `@AnnotationName(...)` syntax directly in place of that element's value.

Core example:

~~~java
@interface Retry {
    int attempts();
}

@interface Client {
    Retry retry();
}

@Client(retry = @Retry(attempts = 3))
class ApiService {}
~~~

In **@Client(retry = @Retry(attempts = 3))**, **Client** is the outer annotation; the **retry()** element has type **Retry**; **@Retry(attempts = 3)** is the value passed in. This is an **annotation-valued element**, not creating an object with `new`.

This lesson focuses on syntax, declarations, default values, arrays of nested annotations, how to access them, and common errors.

## 1. Mechanism: Annotations Are Also Valid Types for Annotation Elements

An annotation declaration in Java uses **@interface**:

~~~java
@interface Timeout {
    int millis();
}

@interface Command {
    String name();
    Timeout timeout();
}
~~~

Distinguish between the two structural layers:

- **Timeout** is an *annotation type* whose **millis()** element accepts an `int`.
- **Command** is an *annotation type* whose **timeout()** element accepts a value of the **Timeout** annotation type.
- When applying **@Command** to a declaration, you must provide both **name** and **timeout** because these elements do not have default values yet.
- In the **timeout = ...** position, the compiler requires an **annotation value** of the exact Timeout type; writing **@Timeout(millis = 800)** is valid.

~~~java
@Command(
    name = "sync",
    timeout = @Timeout(millis = 800)
)
class SyncCommand {}
~~~

The syntax is read from the inside out: **@Timeout(millis = 800)** describes the timeout configuration; that value is assigned to **timeout** of **@Command**. The **@** sign on the inner annotation is required.

According to Java's rules, an annotation element can have a primitive type, `String`, `Class` (including appropriate uses of `Class<?>`), an enum, an annotation type, or a **one-dimensional array** of those types. Therefore, annotation types such as **Timeout** and **Timeout[]** are accepted; arbitrary object types such as **Object**, **List<Timeout>**, or two-dimensional arrays like **Timeout[][]** are not valid as annotation element types.

An annotation element is declared as a **parameterless** method, such as **Timeout timeout();**; this is a metadata structure description, not a business method for assigning an object at runtime.

## 2. Syntax for Passing a Nested Annotation

General pattern:

~~~java
@Outer(inner = @Inner(key = "value"))
class Example {}
~~~

With the corresponding definitions:

~~~java
@interface Inner {
    String key();
}

@interface Outer {
    Inner inner();
}
~~~

Points to remember:

1. **inner =** is the element name of the outer annotation; it is required if that element has no `default`.
2. **@Inner(...)** has the exact type declared by **inner()**.
3. Values inside **@Inner** must also obey annotation value rules: for example, constant strings for `String`, compile-time constant expressions for integers, appropriate enum constants, and further nested annotations when the type permits.
4. The parentheses of **@Outer(...)** and **@Inner(...)** belong to two separate levels. Line breaks only serve readability and do not affect meaning.

**Do not** write `inner = new Inner(...)`: annotations are not instantiated with `new` in annotation application syntax. Also do not write `inner = Inner(...)` because the **@** sign is missing.

### An Element Named value()

Java supports shorthand syntax for an element named **value**:

~~~java
@interface Label {
    String value();
}

@interface Endpoint {
    Label label();
}

@Endpoint(label = @Label("public"))
class PublicEndpoint {}
~~~

Writing **@Label("public")** is equivalent to **@Label(value = "public")**. On the outside, **@Endpoint(label = ...)** must still specify the name **label**, because Endpoint's element is not named **value**.

If the outer annotation's own element is named **value**, the outer level can also be shortened:

~~~java
@interface Wrapper {
    Label value();
}

@Wrapper(@Label("public"))
class Example {}
~~~

This syntax is equivalent to **@Wrapper(value = @Label(value = "public"))**. Both shorthand levels are independent syntax rules.

## 3. Default Values of Nested Annotations

An annotation-valued element can have a default value right in its declaration:

~~~java
@interface RetryPolicy {
    int attempts() default 3;
    long delayMillis() default 100L;
}

@interface ClientConfig {
    RetryPolicy retry() default @RetryPolicy;
}
~~~

**@RetryPolicy** without parentheses is valid because all elements of RetryPolicy have default values. ClientConfig's **default @RetryPolicy** declaration is also valid: it is a default annotation value, not a constructor call.

When using it:

~~~java
@ClientConfig
class DefaultClient {}

@ClientConfig(retry = @RetryPolicy(attempts = 5))
class CustomizedClient {}
~~~

For **DefaultClient**, the **retry()** element uses the default annotation **@RetryPolicy**; inside it, **attempts()** defaults to **3** and **delayMillis()** defaults to **100**. For **CustomizedClient**, the entire RetryPolicy annotation is specified again to override attempts to **5**; delayMillis still uses the default **100**.

Do not confuse the two default levels:

- **default @RetryPolicy** is the default value of the **ClientConfig.retry()** element.
- **default 3** and **default 100L** are the default values of the **RetryPolicy.attempts()** and **RetryPolicy.delayMillis()** elements.

If **RetryPolicy** has a required element, the default value at the outer level must provide that required element. For example, when `int attempts();` has no default, the default expression must take the form **default @RetryPolicy(attempts = 3)**.

Annotation values, including default values, are determined according to Java syntax at compile time. You cannot write `default new RetryPolicy(...)`, cannot assign `null` as an annotation value, and cannot use the arbitrary result of a runtime method to populate metadata.

## 4. Passing Arrays of Nested Annotations

When the outer annotation needs multiple sub-configurations, declare an element of type **NestedAnnotation[]**:

~~~java
@interface Header {
    String name();
    String value();
}

@interface RequestConfig {
    Header[] headers() default {};
}
~~~

When using it, write the child annotations inside curly braces:

~~~java
@RequestConfig(headers = {
    @Header(name = "Accept", value = "application/json"),
    @Header(name = "X-Client", value = "learning")
})
class JsonRequest {}
~~~

Each element in **headers** must have type **Header**. Commas separate the elements, just like array initializer syntax in annotations. For an empty array:

~~~java
@RequestConfig(headers = {})
class NoHeaders {}
~~~

Java also allows **omitting the curly braces if an annotation array element is provided with exactly one value**:

~~~java
@RequestConfig(headers = @Header(name = "Accept", value = "text/plain"))
class TextRequest {}
~~~

The syntax above is equivalent to **headers = { @Header(...) }**, meaning it still creates an array value containing one annotation. When guiding beginners, using curly braces for array elements helps distinguish them clearly from elements that accept only a single annotation.

You must not pass two comma-separated annotations without curly braces, such as `headers = @Header(...), @Header(...)`; and you cannot assign **@Header** to an element of type **RetryPolicy** because the types do not match.

## 5. Complete Java 17+ Example: Client Configuration with Nested Annotations

Create a single file **src/demo/NestedAnnotationDemo.java** with the following content:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface Retry {
    int attempts() default 3;
    long delayMillis() default 100L;
}

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface Header {
    String name();
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface HttpClient {
    String baseUrl();
    Retry retry() default @Retry;
    Header[] headers() default {};
}

@HttpClient(
    baseUrl = "https://api.example.test",
    retry = @Retry(attempts = 5, delayMillis = 250L),
    headers = {
        @Header(name = "Accept", value = "application/json"),
        @Header(name = "X-App", value = "demo")
    }
)
class ApiService {}

@HttpClient(baseUrl = "https://backup.example.test")
class BackupService {}

public class NestedAnnotationDemo {
    public static void main(String[] args) {
        printConfig(ApiService.class);
        printConfig(BackupService.class);
    }

    private static void printConfig(Class<?> type) {
        HttpClient config = type.getAnnotation(HttpClient.class);
        if (config == null) {
            System.out.println(type.getSimpleName() + " has no @HttpClient");
            return;
        }

        System.out.println(type.getSimpleName() + " -> " + config.baseUrl());

        Retry retry = config.retry();
        System.out.println("retry: " + retry.attempts()
                + " / " + retry.delayMillis());

        for (Header header : config.headers()) {
            System.out.println("header: " + header.name()
                    + "=" + header.value());
        }
    }
}
~~~

Compile and run from the directory containing **src**:

~~~bash
javac -encoding UTF-8 -d out src/demo/NestedAnnotationDemo.java
java -cp out demo.NestedAnnotationDemo
~~~

Stdout output:

~~~text
ApiService -> https://api.example.test
retry: 5 / 250
header: Accept=application/json
header: X-App=demo
BackupService -> https://backup.example.test
retry: 3 / 100
~~~

**Step-by-step analysis:**

1. **@HttpClient** is the outer annotation, applied to classes thanks to **@Target(ElementType.TYPE)**. **Retry** and **Header** declare **@Target({})**, making them suitable as nested annotations inside annotation elements and not used directly on class/method/field declarations.
2. **retry = @Retry(...)** supplies a single value of type **Retry**. **headers = { @Header(...), @Header(...) }** supplies an array containing two values of type **Header**.
3. The annotations use **@Retention(RetentionPolicy.RUNTIME)** in the example so that reading metadata via reflection is clear; the outer annotation must have runtime retention to be retrieved via **Class.getAnnotation**.
4. **getAnnotation(HttpClient.class)** reads metadata on the specified class. **config.retry()** returns the child annotation value; **config.headers()** returns the array of child annotations, so you can call **attempts()**, **name()**, and **value()** accordingly.
5. **BackupService** does not pass **retry** or **headers**. It receives the default values of HttpClient's elements: **@Retry** with attempts=3/delayMillis=100 and an empty headers array. Consequently, the `for` loop does not print any header lines for BackupService.

The example reflects metadata configuration: Java does not automatically perform network retries or attach HTTP headers simply because the annotations are present. Only a framework or application code that reads and uses this configuration can produce actual behavior.

**Note on names and imports:** Retry and Header in the example are in the same package as HttpClient, so their simple names resolve directly. If Retry is in another package, import the exact Retry type or write the fully qualified name after the @ sign, for example **retry = @com.example.policy.Retry(...)**; the name resolution rules remain the same as for any other annotation type.

## 6. Nested Annotations Differ from Meta-Annotations and Repeatable Annotations

The following syntaxes are easily confused because they all involve multiple **@** symbols:

**An annotation as the value of an annotation element** — the scope of this lesson:

~~~java
@interface Constraint {
    int min();
}

@interface FieldRule {
    Constraint constraint();
}

@FieldRule(constraint = @Constraint(min = 1))
class Sample {}
~~~

Here **Constraint** is placed into the **constraint** element of FieldRule.

**Meta-annotation** — an annotation placed on the declaration of an annotation type:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Marker {}
~~~

In this case, **@Retention** describes the **Marker** declaration itself, rather than being passed as the value of an element named retention. The target metadata is different, even though both use the @ symbol.

**Repeatable annotation** — the same annotation type written multiple times on a single declaration when the type has been defined as `@Repeatable`. This is a separate Java mechanism and is not synonymous with declaring an element of type **Header[]** and passing multiple **@Header** values to that element.

## 7. Type Constraints and Common Compilation Errors

| Case | Problem | Correct Approach |
| --- | --- | --- |
| `retry = Retry(attempts = 2)` | Missing @ sign before the inner annotation | `retry = @Retry(attempts = 2)` |
| `retry = new Retry(2)` | Annotation values do not use object creation syntax | `retry = @Retry(attempts = 2)` |
| `retry = null` | An annotation value cannot be null | Provide a valid annotation or declare a **default** |
| `Retry retry() default null;` | A default value cannot be null | For example, `Retry retry() default @Retry;` |
| `retry = @Header(...)` | Type Header does not match element type Retry | Use **@Retry(...)** |
| `Header[][] headers();` | Two-dimensional array types are not valid for annotation elements | Use **Header[]** |
| `List<Header> headers();` | Annotation elements do not support List | Use **Header[]** |
| `headers = { @Header(name = "A") }` | Header is missing the required **value** element | Add `value = "..."` or define a default for that element |
| `@HttpClient(retry = @Retry)` when **baseUrl()** is required | Missing a required element at the outer level | Provide `baseUrl = "..."` |
| Reading **getAnnotation(...)** returns null | The outer annotation is absent or is not retained until runtime | Check the exact class, exact type, and `@Retention(RUNTIME)` |

When a nested annotation contains another nested annotation inside it, apply the same rules recursively regarding names, element types, **@** syntax, `default`, and valid values. Java does not impose a “one level of nesting only” rule; practical limits come from type definitions, valid representability, and configuration readability.

## 8. Self-Check Exercises

Given the following annotations:

~~~java
@interface Cache {
    int seconds() default 60;
}

@interface Route {
    String path();
    Cache cache() default @Cache;
}

@Route(path = "/users", cache = @Cache(seconds = 120))
class UserRoute {}
~~~

**Question 1.** What type is the value passed to **Route.cache()**? — The **Cache** annotation type, via the value **@Cache(seconds = 120)**.

**Question 2.** If it is changed to **@Route(path = "/users")**, will there be an error due to the missing cache? — No; **Route.cache()** defaults to **@Cache**, in which **seconds()** defaults to **60**.

**Question 3.** Can the cache value be replaced with `Cache.class`? — No. `Cache.class` has type **Class<Cache>**, whereas the **cache()** element requires **Cache**. If you want an element to hold a class literal, the element declaration must use **Class<?>** or an appropriate valid `Class` type.

**Question 4.** If you want Route to hold multiple Cache policies, what needs to change? — Change the declaration from **Cache cache()** to an element **Cache[] caches()** (for example with **default {}**) and pass an array **{ @Cache(seconds = 30), @Cache(seconds = 60) }**.

When encountering multi-level annotation syntax, read from the element declaration to see **what type it has**, and then compare it with the value after the **=** sign. If the element declares an annotation type, use **@ChildAnnotation(...)**; if it is an array of an annotation type, use **{ @ChildAnnotation(...), ... }**. This is the foundational rule for passing nested annotations in a type-safe and clear manner.
