# Required Elements and Declaring Default Values with `default` in Java Annotations

## 1. Understanding the Problem

An **annotation type** in Java is declared using `@interface`. Inside it are **annotation elements** that look like parameterless method declarations, such as `String name();` or `int priority() default 5;`. When applying an annotation to a declaration, the developer provides values for the elements that the annotation requires.

Example:

```java
@interface TaskInfo {
    String name();                     // Required
    int priority() default 5;          // Has a default value
    boolean enabled() default true;    // Has a default value
}
```

Valid usage:

```java
@TaskInfo(name = "send-report")
class ReportJob {}

@TaskInfo(name = "sync-data", priority = 9, enabled = false)
class SyncJob {}
```

- `name()` **does not have `default`**, so when using `@TaskInfo`, you must explicitly specify `name = ...`.
- `priority()` has `default 5`: if `priority` is not passed, the effective value is `5`; when needed, it can be overridden with `priority = 9`.
- `enabled()` has `default true`: if not passed, the result is `true`; `enabled = false` is an explicit choice.
- These values are **annotation metadata**; they do not by themselves cause a task to run or change its priority. An annotation processor, framework, or program that reads the annotation must interpret the metadata to produce behavior.

Key point: **a required element is an element without a declared default value; an optional element is an element declared with `default`.** Java does not apply a rule such as "`int` defaults to `0`, `boolean` defaults to `false`, or `String` defaults to `null`" to automatically populate values for unspecified annotation elements.

## 2. Syntax for Declaring Elements and `default`

An element in an annotation type has the basic form:

```java
KiểuTraVe tenPhanTu() [default giaTriMacDinh];
```

The square brackets in the line above are only notation indicating the optional part, **not Java syntax to copy verbatim**.

Example annotation declaration:

```java
public @interface EndpointInfo {
    String path();                             // Required
    String httpMethod() default "GET";         // Optional
    int timeoutMillis() default 1500;          // Optional
    String[] tags() default {};                // Optional, empty array
}
```

In an annotation type:

1. An element is declared like a method **with no parameters and no body**; the return type describes the data type of the attribute.
2. The `default` keyword is placed **after `()`** and before the `;`, attaching a valid value to **that element itself**.
3. You cannot declare an element such as `String path(String prefix);`; an annotation element does not accept parameters.
4. You cannot declare an element with `throws`, type parameters, or a return type not permitted by Java for annotation elements.
5. All annotation elements have `public abstract` semantics in an annotation type, even though those two keywords do not need to be written. There are no constructors, setters, or getters with custom logic to generate default values.

`default` in `String path() default "/";` is **completely different** from `default` used to declare a method with a body in a regular interface:

```java
interface Greeting {
    default String hello() {
        return "hello";
    }
}
```

This is a regular interface with a **default method that has a body**. In an annotation type, `default` attaches a **default value to the element**, while the element still has no method body.

## 3. When Using an Annotation: What Must Be Provided?

Consider the `EndpointInfo` annotation above. All of the following usages are valid:

```java
@EndpointInfo(path = "/users")
class ListUsers {}

@EndpointInfo(path = "/users", httpMethod = "POST")
class CreateUser {}

@EndpointInfo(
    path = "/audit",
    httpMethod = "POST",
    timeoutMillis = 4000,
    tags = {"security", "write"}
)
class AuditLog {}
```

Elements can be provided in any order. The name written at the usage site is the element name **without parentheses**, for example `path = "/users"`, not `path() = ...`.

When writing only:

```java
@EndpointInfo(path = "/users")
```

the effective values are:

| Element | Has `default`? | Effective value |
| --- | --- | --- |
| `path()` | No | `"/users"` provided at the usage site |
| `httpMethod()` | Yes, `"GET"` | `"GET"` |
| `timeoutMillis()` | Yes, `1500` | `1500` |
| `tags()` | Yes, `{}` | Empty `String` array |

The following snippet is **intentionally invalid**:

```java
@EndpointInfo
class MissingPath {}
```

`javac` rejects it because `path` is a required element and was not provided. Using `@EndpointInfo()` does not fix the issue either: empty parentheses do not automatically supply a value for `path`.

If `path` truly needs to be optional, the designer must define the meaning of a default value, such as `String path() default "/";`; whether such a default should be chosen depends on the specific contract.

## 4. Java 17+: Complete Compilable and Runnable Example

This example demonstrates three behaviors in a single run: a required element, a defaulted element, and an element passed an explicit value. It also uses reflection to show the difference between **the value on an applied annotation** and **the default value declared in the annotation type**.

Save the entire snippet below to a file named **`AnnotationDefaultsDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface EndpointInfo {
    String path();
    String httpMethod() default "GET";
    int timeoutMillis() default 1500;
    String[] tags() default {};
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Label {
    String value();
    String language() default "vi";
}

@EndpointInfo(path = "/orders")
class ListOrders {}

@EndpointInfo(
        path = "/orders",
        httpMethod = "POST",
        timeoutMillis = 3000,
        tags = {"write", "audit"}
)
class CreateOrder {}

@Label("orders")
class OrderModule {}

public class AnnotationDefaultsDemo {
    private static void showEndpoint(Class<?> type) {
        EndpointInfo info = type.getAnnotation(EndpointInfo.class);
        System.out.println(
                info.httpMethod() + " " + info.path()
                + " | timeout=" + info.timeoutMillis()
                + " | tags=" + Arrays.toString(info.tags())
        );
    }

    public static void main(String[] args) throws NoSuchMethodException {
        showEndpoint(ListOrders.class);
        showEndpoint(CreateOrder.class);

        Label label = OrderModule.class.getAnnotation(Label.class);
        System.out.println(label.value() + " | " + label.language());

        System.out.println(
                EndpointInfo.class.getDeclaredMethod("path").getDefaultValue()
        );
        System.out.println(
                EndpointInfo.class.getDeclaredMethod("httpMethod").getDefaultValue()
        );
    }
}
```

Compile and run using JDK 17 or later in the directory containing the file:

```bash
javac --release 17 AnnotationDefaultsDemo.java
java AnnotationDefaultsDemo
```

**Exact stdout:**

```text
GET /orders | timeout=1500 | tags=[]
POST /orders | timeout=3000 | tags=[write, audit]
orders | vi
null
GET
```

Line-by-line explanation:

1. `ListOrders` only provides `path`, so `httpMethod`, `timeoutMillis`, and `tags` take the default values `GET`, `1500`, and `{}`.
2. `CreateOrder` provides explicit values for all four elements; the values specified at the usage site take effect instead of the corresponding default values.
3. `@Label("orders")` is shorthand syntax for `@Label(value = "orders")`; the `language()` element uses the default `"vi"`.
4. `getDefaultValue()` on the method representing `path` returns `null` because it **has no default**; this does not mean the `path` value of a validly applied annotation can be `null`.
5. `getDefaultValue()` for `httpMethod` returns `"GET"` because the annotation type declares that as its default.

Because the example uses `@Retention(RetentionPolicy.RUNTIME)`, the runtime can retrieve the annotation via `getAnnotation`. If an annotation is not present on a class, `Class.getAnnotation(...)` can return `null`; in this program, both classes passed to `showEndpoint` carry the annotation, so no `null` access error occurs.

## 5. The Special `value()` Element and Shorthand Syntax

If an annotation has an element named exactly `value`, Java allows omitting `value =` in an appropriate usage form:

```java
@interface Category {
    String value();
    boolean visible() default true;
}

@Category("payments")
class PaymentFeature {}

@Category(value = "reports", visible = false)
class ReportFeature {}
```

Here:

- `@Category("payments")` is equivalent to `@Category(value = "payments")`.
- If additional elements such as `visible` need to be provided, use the full **name–value pair** syntax as in `ReportFeature`.
- Naming an element `value()` **does not make it automatically optional**; because there is no `default`, `value` is still required.
- If `String value() default "general";`, then both `@Category` and `@Category()` can be valid (provided there are no other required elements), and `value` will have the default value `"general"`.

Do not confuse shorthand syntax with permission to omit other required elements. For example:

```java
@interface OwnerInfo {
    String value();
    String team();
}
```

`@OwnerInfo("alice")` is **invalid** because `team` is missing. You must write `@OwnerInfo(value = "alice", team = "backend")`.

## 6. Valid Data Types and Values for `default`

Java strictly restricts the return types of annotation elements. These are **static metadata values**, not a place to execute arbitrary code.

| Valid element type | Example `default` declaration |
| --- | --- |
| Primitive types (except `void`) | `int retries() default 3;`, `boolean enabled() default true;` |
| `String` | `String name() default "anonymous";` |
| `Class` or an appropriately parameterized form | `Class<?> handler() default Object.class;` |
| An enum type | `Level level() default Level.BASIC;` |
| An annotation type | `Policy policy() default @Policy("safe");` |
| A **one-dimensional** array of a permitted type | `String[] tags() default {};`, `int[] levels() default {1, 2};` |

The following snippet illustrates those types; these are **supporting declarations**, not a standalone program with `main`:

```java
enum Level {
    BASIC, STRICT
}

@interface Policy {
    String value();
}

@interface AuditOptions {
    Level level() default Level.BASIC;
    Class<?> handler() default Object.class;
    String[] tags() default {"audit"};
    Policy policy() default @Policy("standard");
}
```

For primitive or `String` elements, the default expression must satisfy compile-time constant expression rules; for an enum, it must be an enum constant; for `Class`, a class literal is typically used; for a nested annotation, an annotation value such as `@Policy("standard")` is used. Array values are written as a list of valid elements inside `{...}`.

**Types that cannot be used as an annotation element** include `Object`, `List<String>`, `Map<...>`, an arbitrary object class, a type variable `T`, or a multidimensional array `String[][]`. Constructors or the results of arbitrary method calls cannot be used to construct a default.

### 6.1. Arrays and Value Syntax at the Usage Site

Given the declaration:

```java
@interface Roles {
    String[] value() default {};
}
```

The following usages are valid:

```java
@Roles
class PublicResource {}

@Roles("ADMIN")
class AdminResource {}

@Roles({"ADMIN", "AUDITOR"})
class RestrictedResource {}
```

- `@Roles` uses the default value: an empty array.
- `@Roles("ADMIN")` is a valid shorthand form when an array-typed annotation element receives **a single element value**.
- `@Roles({"ADMIN", "AUDITOR"})` provides an array containing two values.
- `default {}` means no elements, which is **different from** `default {""}`, an array containing one empty string.
- When you need to represent "unspecified" separately from "empty list", design an explicit contract rather than assuming the two cases can always be distinguished from reading the annotation.

### 6.2. No `null` in Annotation Values

The following are **invalid**:

```java
@interface BadDefaults {
    String missing() default null;           // Invalid
    int count() default Integer.parseInt("2"); // Invalid
    String[] nested() default {null};        // Invalid
}
```

Java does not allow `null` as an annotation value or a default value. A call like `Integer.parseInt("2")` is not a compile-time constant expression, even though it would evaluate to `2` at runtime. Writing `default 2` directly is valid.

If the domain logic needs a "no value" meaning, common options include a conventional string such as `""` (with documentation), an empty array, an enum constant like `UNSPECIFIED`, or an appropriate sentinel `Class` type. Each approach requires explaining its meaning, because these are real values.

## 7. Where Is `default` Checked and Applied?

There are three points in time to distinguish:

**When compiling the annotation type declaration:** the compiler checks the element type as well as the type and validity of the default expression. If you declare `int timeout() default "slow";`, `javac` reports an error because `String` is incompatible with `int`.

**When compiling the annotation usage site:** the compiler requires every element **without a default** to have an appropriate value. Elements with a default can be omitted or passed an explicit value. For example, `@EndpointInfo(httpMethod = "POST")` fails because `path` is missing, whereas `@EndpointInfo(path = "/")` is valid.

**When reading an existing annotation:** if a value was not explicitly written at the usage site, the default value is obtained from the annotation type declaration. At runtime, you can use `annotation.httpMethod()` to get the effective value, or `EndpointInfo.class.getDeclaredMethod("httpMethod").getDefaultValue()` to get the declared default itself.

Under Java's mechanism, default values **are not copied into every annotation usage**. They belong to the annotation type definition and are applied when read. Therefore, modifying the `default` of a library annotation can change the values observed from previously compiled usage sites (if those sites did not provide explicit values). For a public API, changing a default is a contract change and must be evaluated carefully.

For example, suppose initially `int timeoutMillis() default 1500;`, and many classes only write `@EndpointInfo(path = "/")`. If a later library version changes the default to `3000`, sites that did not pass `timeoutMillis` can receive `3000` when using the new definition. Sites that passed `timeoutMillis = 1000` still retain their explicit value.

## 8. `default` Does Not Mean Values Are Always Valid for Business Logic

The compiler checks the **types** and that the required elements are provided, but generally has no knowledge of the metadata's business constraints.

Example:

```java
@interface RetryPolicy {
    int maxAttempts() default 3;
}
```

`@RetryPolicy(maxAttempts = -5)` is type-valid in Java because `-5` is an `int`, but it may be meaningless to the retry processor. If constraints such as a positive retry count are needed, validate them where the metadata is consumed or apply an appropriate validation tool. An annotation element does not allow placing a method body with validation logic inside it.

A good default has a clear meaning, causes minimal surprise, and can be used safely in the vast majority of cases. If there is no sensible shared value, **keep the element required** to force callers to state their intent. For example, an endpoint's `path()` should usually be required if a suitable common path cannot be inferred.

## 9. Common Compilation Errors and How to Fix Them

| Situation | Why is it wrong or confusing? | How to resolve |
| --- | --- | --- |
| `@EndpointInfo` when `path()` has no default | Missing required value | `@EndpointInfo(path = "/orders")` |
| `String path() default null;` | `null` is not a valid annotation element value | Choose a documented sentinel or do not declare a default |
| `int delay() default loadConfig();` | A method call is not a compile-time constant | Use a valid constant or let the system handle dynamic values outside the annotation |
| `String[] tags() default null;` | Annotation arrays also do not accept `null` | Use `default {}` if "empty" is the intended meaning |
| `List<String> tags() default ...;` | `List` is not a valid annotation element return type | Switch to `String[]` if appropriate |
| `@OwnerInfo("alice")` when `team()` is also required | Shorthand `value` syntax does not waive other required elements | Use `@OwnerInfo(value = "alice", team = "backend")` |
| `@EndpointInfo(path = "/orders", timeoutMillis = "1500")` | A `String` value is incompatible with `int` | Use `timeoutMillis = 1500` |
| Assuming `@Retention(RUNTIME)` automatically adds defaults | Retention only controls how long the annotation is retained | Declare `default` on the specific element that should be optional |
| Assuming `default` executes behavior automatically | Metadata does not execute business logic by itself | Build a processor, framework integration, or metadata-reading logic |

Another example of an error is **duplicate assignment of an element**:

```java
@EndpointInfo(path = "/a", path = "/b") // Invalid: path is specified twice
class DuplicatePath {}
```

Each element can only be specified once in a given annotation. To support multiple values, design the element as an array if the contract allows it.

## 10. Guidelines for Designing and Testing Annotations with Defaults

When creating an annotation for use in Java or within a framework:

1. List the metadata that **the caller must always decide**. Declare them without `default`.
2. For metadata that can use a clear common policy, declare `default` directly on the element and document its meaning.
3. Choose element types from the set supported by Java. If multiple values are needed, consider a one-dimensional array, enum, or nested annotation.
4. Consider whether `value()` is genuinely the primary component of the annotation before using shorthand syntax; an explicit descriptive name is sometimes easier to understand.
5. Compile both a minimal example filling only the required elements and an example customizing all elements. Also test a case where a required element is intentionally omitted to verify that the compiler catches the error.
6. If a tool reads the annotation at runtime, set an appropriate retention policy (usually `RUNTIME`), read the metadata, and validate business constraints separately.
7. For a published annotation, consider the impact of **adding a new required element**: existing usage sites will become invalid upon recompilation. Adding an element with a default is generally easier to keep source-compatible, but any API change still needs to be tested with consumers.
8. When modifying a default, evaluate callers that do not pass an explicit value, as they may receive new behavior without modifying their source code.

**Key takeaway:** In an annotation type, `String name();` creates a **required** element, whereas `String name() default "guest";` allows the usage site to **omit** that element to receive the default value. The compiler is responsible for checking validity; the system consuming the annotation determines what the metadata means and what business impact it has.
