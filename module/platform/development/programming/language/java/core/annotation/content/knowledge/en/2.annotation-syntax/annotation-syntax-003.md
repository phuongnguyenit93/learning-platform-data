# Normal Annotations with Name-Value Pairs in Java

In Java, annotations can carry **metadata** through name-value pairs, written in parentheses after the annotation name. This syntax is commonly used when an annotation needs to describe multiple attributes: API paths, timeouts, priority levels, column names, etc. This section focuses on **how to declare annotation elements and how to pass multiple `ten = giaTri` pairs when using them**; the values must follow Java's rules at compile time.

## 1. Syntax Form

```java
@TenAnnotation(tenElement1 = giaTri1, tenElement2 = giaTri2)
```

- `TenAnnotation` is an annotation type defined with `@interface`, or a predefined annotation type provided in a library.
- `tenElement1`, `tenElement2` must match **exactly** the element names declared in the annotation type.
- The `=` sign assigns a value to an element; the comma `,` separates the pairs. Do not use JSON-style `:`.
- Each element may be specified at most **once** in a single annotation application; the order of the pairs can be changed.
- The value must match the element's type. An element without `default` must be provided, unless there is no other valid usage.

Standard annotation example from the JDK:

```java
@Deprecated(since = "17", forRemoval = false)
public void oldMethod() {
}
```

Here `since` accepts a `String`, and `forRemoval` accepts a `boolean`. `@Deprecated` provides information to the compiler and development tools; the annotation itself does not prevent the method from being called.

## 2. Defining and Applying a Custom Multi-Element Annotation

An **element** in an `@interface` declaration looks like a parameterless method with no method body. Default values are placed after `default`.

Create the file `AnnotationPairsDemo.java` with the full code below:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ApiRoute {
    String path();                   // Value is required
    String method() default "GET";  // Uses "GET" if not passed
    int timeoutMs() default 1000;   // Uses 1000 if not passed
}

@ApiRoute(path = "/products", method = "POST", timeoutMs = 1500)
class ProductResource {
}

public class AnnotationPairsDemo {
    public static void main(String[] args) {
        ApiRoute route = ProductResource.class.getAnnotation(ApiRoute.class);

        System.out.println("path=" + route.path());
        System.out.println("method=" + route.method());
        System.out.println("timeoutMs=" + route.timeoutMs());
    }
}
```

Compile and run with Java 17 or later in the directory containing the file:

```bash
javac -encoding UTF-8 AnnotationPairsDemo.java
java AnnotationPairsDemo
```

`stdout` output:

```text
path=/products
method=POST
timeoutMs=1500
```

Explanation of the mechanism:

1. `@interface ApiRoute` defines three elements named `path`, `method`, and `timeoutMs`; the pair names in `@ApiRoute(...)` must match these three names.
2. `@ApiRoute(path = "/products", method = "POST", timeoutMs = 1500)` attaches **specific values** to the `ProductResource` class. Adding line breaks or changing the order of the pairs does not affect the assignment.
3. `@Target(ElementType.TYPE)` allows `ApiRoute` to be placed on a type declaration (a class in this example). You cannot arbitrarily place it where `@Target` forbids.
4. `@Retention(RetentionPolicy.RUNTIME)` retains the annotation until runtime; `getAnnotation(ApiRoute.class)` retrieves the metadata reflected on the class.
5. `route.path()` and the other calls read the **annotation's elements**, rather than calling business methods of `ProductResource`.

The name `method` here is merely a program-defined `String` element name. Java does not turn `"POST"` into an HTTP endpoint. A framework or application code must read the metadata and handle route registration and processing itself.

## 3. Required Elements and Default Values

In `ApiRoute`, `path()` has no `default`, so it must be provided in every usage. The other two elements have default values. Therefore, the following form is valid:

```java
@ApiRoute(path = "/items")
class ItemResource {
}
```

When reading `ApiRoute` on `ItemResource`, `path()` returns `"/items"`, `method()` returns `"GET"`, and `timeoutMs()` returns `1000`. Default values are declared on the **annotation type**, rather than having to be written at each usage site.

The following examples are **separate cases that do not compile**:

```java
@ApiRoute                       // Missing required path
@ApiRoute(method = "POST")      // Missing path
@ApiRoute(path = 123)           // path() requires String
@ApiRoute(path = "/", verb = "POST")  // No verb() element
@ApiRoute(path = "/a", path = "/b")   // Duplicate assignment to element path
```

If you want to change the order, just keep all the names and values:

```java
@ApiRoute(timeoutMs = 2000, path = "/orders", method = "PUT")
class OrderResource {
}
```

`default` is syntax for **declaring** an annotation type. When **using** it, write `ten = giaTri`, not `default`.

## 4. Value Types Allowed by Java

The return type of an annotation element may only belong to the following categories: primitive types (`int`, `boolean`, ...), `String`, `Class` (including `Class<?>`), an `enum` type, another annotation type, or a **one-dimensional array** of those types. Examples of common categories:

| Element type | Valid value |
| --- | --- |
| `int priority()` | `priority = 2` |
| `boolean enabled()` | `enabled = true` |
| `String name()` | `name = "core"` |
| `Class<?> type()` | `type = String.class` |
| `Severity level()` | `level = Severity.WARNING` |
| `String[] tags()` | `tags = {"java", "core"}` |

Standalone illustration of declaration and value-assignment syntax (this snippet has no `main`):

```java
enum Severity {
    INFO, WARNING
}

@interface Meta {
    String[] tags() default {};
    Class<?> targetType() default Object.class;
    Severity severity() default Severity.INFO;
    int priority() default 1;
}

@Meta(
    tags = {"java", "annotation"},
    targetType = String.class,
    severity = Severity.WARNING,
    priority = 2
)
class AnnotatedExample {
}
```

The values are, respectively, a `String` array, a class literal, an enum constant, and an integer. You cannot declare an element of type `List<String>`, `Map<String, String>`, an arbitrary POJO object, or a two-dimensional array `String[][]`; nor can you use `null` as an element value.

## 5. Special Case of an Element Named `value`

If an annotation type has an element named exactly `value`, you can **omit the name and the `=` sign** when passing only that element:

```java
@interface Label {
    String value();
    int weight() default 1;
}

@Label("core")  // Equivalent to @Label(value = "core")
class CoreTopic {
}

@Label(value = "advanced", weight = 2)
class AdvancedTopic {
}
```

In the `AdvancedTopic` usage, because both `value` and `weight` must be passed, the **full name-value pairs** syntax must be used. `@Label("advanced", weight = 2)` is invalid Java syntax.

`value` is not a required name for every annotation: the `ApiRoute` type does not have a `value` element, so `@ApiRoute("/items")` is **invalid**; you must use `@ApiRoute(path = "/items")`.

A familiar example in the JDK: `@SuppressWarnings("unchecked")` is equivalent to `@SuppressWarnings(value = "unchecked")`, because `SuppressWarnings` declares a `value()` element of type `String[]`.

## 6. Array-Typed Elements

Arrays are normally written inside `{}` with elements separated by commas:

```java
@Meta(tags = {"core", "reflection"})
class MultipleTags {
}
```

For **a single** element, Java allows omitting the curly braces on the array element's value:

```java
@Meta(tags = "core")  // Equivalent to tags = {"core"}
class OneTag {
}
```

An empty array is written as `tags = {}`. Because the `Meta` example declares `tags() default {}`, you can also omit `tags` to receive the empty array default. Omitting `{}` for a single element does not change the declared type: `tags()` still returns `String[]`.

## 7. Constant Expressions and Values Determined at Compile Time

An element value of a primitive type or `String` must be a **compile-time compatible constant expression**. You can use a `static final` constant initialized by a constant expression:

```java
final class ApiPaths {
    static final String PRODUCTS = "/products";
}

@ApiRoute(path = ApiPaths.PRODUCTS)
class ConstantPathResource {
}
```

`ApiPaths.PRODUCTS` is a valid constant variable. Conversely, the following does not compile because calling a method only produces a result when the program runs:

```java
@ApiRoute(path = System.getenv("API_PATH"))  // Not a compile-time constant
class RuntimePathResource {
}
```

For a `Class<?>` element, use a class literal such as `String.class`; for an enum, use an enum constant directly such as `Severity.INFO`; for a nested annotation, use an appropriate annotation literal. Do not use `new String(...)`, a value from a request, a runtime configuration variable, or `null` as an annotation value.

The compiler checks element names, duplicate names, value types, and required elements right during compilation; this helps identify misconfigurations early.

## 8. Annotations Do Not Create Behavior on Their Own

There are three common retention levels:

- `RetentionPolicy.SOURCE`: exists only in the source code; not stored in the `.class` file.
- `RetentionPolicy.CLASS`: stored in the `.class` file, but cannot be read by normal reflection at runtime. This is the default level if `@Retention` is not declared.
- `RetentionPolicy.RUNTIME`: can be retrieved via reflection at runtime, as in `AnnotationPairsDemo`.

An annotation processor can process metadata at compile time; a library or framework can process runtime metadata where appropriate. `@Target` determines which **locations** an annotation can be placed on, whereas name-value pairs describe the **data** the annotation carries. These two concerns are independent.

A class bearing `@ApiRoute` is still a regular Java class; without code that processes the annotation, the `path`, `method`, and `timeoutMs` pairs do not automatically trigger routing, timeouts, or HTTP handling.

## 9. Common Mistakes

| Case | Correct syntax / understanding |
| --- | --- |
| `@ApiRoute(path: "/x")` | Use `=`: `@ApiRoute(path = "/x")`. |
| `@ApiRoute("/x")` | There is no `value()` element; use `@ApiRoute(path = "/x")`. |
| `@ApiRoute(path = "/x", path = "/y")` | Each element can only be assigned once. |
| `@ApiRoute(path = "/x", timeoutMs = "1000")` | `timeoutMs` is an `int`, so you must write `1000`. |
| `@Label("core", weight = 2)` | Write `@Label(value = "core", weight = 2)`. |
| Using `System.getenv(...)` as a `String` value | Use a compile-time constant expression. |
| Omitting `@Retention(RUNTIME)` and then reading with reflection | The default retention is `CLASS`; runtime reflection cannot read it. |
| Assuming annotations execute business logic automatically | There must be a processor/framework/code to process the metadata. |

**Self-check:** `@ApiRoute(path = "/health", timeoutMs = 500)` provides two pairs, where `path = "/health"` and `timeoutMs = 500`; the `method` element receives the default `"GET"`. Changing it to `@ApiRoute(method = "GET")` will cause a compilation error because `path` is missing. From this, we can see that **the element name clearly identifies the value being passed**, and Java validates it right at compile time.
