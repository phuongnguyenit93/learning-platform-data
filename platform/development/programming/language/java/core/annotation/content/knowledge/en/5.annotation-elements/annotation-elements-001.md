# Valid Annotation Element Types and Values in Java

In Java, annotations are used to **attach structured metadata** to a permitted declaration or location. An annotation type is declared using `@interface`; the parameterless methods inside it are called **annotation elements**. When using an annotation, you assign values to these elements.

An important point: **the return type of an annotation element is strictly restricted by Java**, unlike regular Java methods. Java only permits the eight primitive types, `String`, `Class` (including certain parameterized forms), `enum` types, other annotation types, and **one-dimensional arrays** of those types. The assigned value must also follow the rules for annotation value expressions; not every Java expression that returns the right type can be used.

This article focuses on **which types and values are valid**, how the compiler checks them, and how to declare/use them properly.

## 1. What Is an Annotation Element?

Example:

```java
@interface RetryPolicy {
    int attempts();
    String reason() default "temporary";
}
```

- `attempts()` is an element of type `int`, **with no default value**. Every place that uses `@RetryPolicy` must provide `attempts`.
- `reason()` is an element of type `String`, with the **default value** `"temporary"`.
- Even though the syntax looks like a method, you do not write an implementation body, parameters, or computation logic in the elements.
- At the point of use, `@RetryPolicy(attempts = 3)` is valid; `reason` receives the default value.

Full usage form:

```java
@RetryPolicy(attempts = 3, reason = "network")
class NetworkJob {
}
```

An annotation declaration can declare multiple elements, but **each element must have a valid type**. The Java compiler checks this when compiling the annotation type, before a framework or Reflection is needed.

## 2. Complete List of Valid Element Types

According to Java's rules for annotation elements, a permitted return type belongs to one of the following categories:

| Category | Valid Declared Types | Example Values When Applying the Annotation |
| --- | --- | --- |
| Eight primitive types | `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `char` | `enabled = true`, `count = 3`, `letter = 'A'` |
| String | `String` | `name = "checkout"` |
| Class type | `Class` or a valid parameterization of `Class`, such as `Class<?>`, `Class<? extends Runnable>` | `type = String.class`, `handler = Thread.class` |
| Enum | A specific `enum` type | `priority = Priority.HIGH` |
| Annotation | An annotation type declared with `@interface` | `label = @Label("public")` |
| One-dimensional array | `T[]` where `T` is a type from the five categories above | `tags = {"java", "core"}`, `types = {String.class, Integer.class}` |

In the table, "eight primitive types" does not include `void`. The `Class` category refers to class objects in metadata, such as `String.class`, rather than an arbitrary return type of a Java method.

**Core rule:** if `T` is a valid non-array element type, then `T[]` is also a valid element type; however, `T[][]` is **invalid**, even though multidimensional arrays are valid types in regular Java.

### 2.1. Eight Primitive Types

An annotation can declare:

```java
@interface PrimitiveOptions {
    boolean enabled() default true;
    byte level() default 5;
    short threshold() default 100;
    int retries() default 3;
    long timeoutMillis() default 1000L;
    float ratio() default 0.5f;
    double factor() default 1.25;
    char separator() default ':';
}
```

The default values are all constant expressions compatible with the element type. For `byte` and `short`, Java applies a narrowing conversion rule for **integer constants within the value range of the target type**; for example, `byte level() default 127;` is valid, whereas `byte level() default 128;` is an error because it is out of range.

Note the distinction between primitive types and wrapper types: `int` is allowed; `Integer` is not allowed as an element type. Similarly, `boolean` is valid, while `Boolean` is invalid.

### 2.2. String

```java
@interface RouteInfo {
    String path();
    String description() default "Endpoint";
}
```

Used with `String` literals or constant expressions:

```java
@RouteInfo(path = "/api" + "/orders")
class OrdersEndpoint {
}
```

Concatenating string literals as shown above produces a valid constant expression. However, `path = System.getenv("ROUTE")` is invalid because the method is invoked at runtime and the result is not a constant that the compiler can use as an annotation value.

`String` is permitted; types such as `StringBuilder`, `CharSequence`, `Optional<String>`, or `List<String>` are **not permitted** as the return type of an annotation element.

### 2.3. Class and Class Literals

```java
@interface HandlerInfo {
    Class<?> type();
    Class<? extends Runnable> runnableType();
}
```

Usage:

```java
@HandlerInfo(type = String.class, runnableType = Thread.class)
class TaskDefinition {
}
```

- `String.class` represents the `String` type; **it does not create a `String` object**.
- `Thread.class` satisfies the `Class<? extends Runnable>` bound because `Thread` implements `Runnable`.
- `Class<?>` matches class literals of many types, such as `String.class`, `int.class`, or `String[].class`.
- `Class<? extends Runnable>` helps the compiler check a specific type constraint right at the annotation site.

You must write a **class literal** such as `String.class` instead of `new String()`, `String.class.getName()`, or the result of `Class.forName("...")`. Those latter forms are not permitted `Class` value syntax in annotations. `Class` is one of the special exceptions: a class literal is a kind of value permitted in annotations, even though it is not a regular compile-time constant expression like `1 + 2`.

### 2.4. Enum

Definition:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

@interface QueueConfig {
    Priority priority() default Priority.MEDIUM;
}
```

Usage:

```java
@QueueConfig(priority = Priority.HIGH)
class FastQueue {
}
```

The value must be an **enum constant** of the exact required type: `Priority.HIGH`. It cannot be replaced with `"HIGH"`, `Priority.valueOf("HIGH")`, or another method call, even if it produces the same enum constant at runtime.

`enum` is well suited when an annotation should only select one state from a finite list. If multiple states are needed at the same time, you can declare `Priority[]` and pass a one-dimensional array.

### 2.5. Nested Annotations as Values

An annotation can contain another annotation as an element value:

```java
@interface Label {
    String value();
}

@interface Endpoint {
    Label label();
}

@Endpoint(label = @Label("public"))
class PublicEndpoint {
}
```

`@Label("public")` is **an annotation value**, not an arbitrary object created with `new`. Its validity is checked against the `Label` declaration. If `Label` has multiple required elements, every element lacking a default must be provided.

When the outer annotation is read at runtime via Reflection, nested annotation values can be accessed through the corresponding element, provided the outer annotation type is retained until runtime and the type-loading configuration permits it. Usage and lifecycle constraints still need to be distinguished from the **set of permitted element types**.

## 3. One-Dimensional Arrays: The Most Easily Confused Rules

Example of a valid declaration:

```java
@interface BatchInfo {
    int[] retries();
    String[] tags() default {};
    Class<?>[] dependencies() default {};
    Priority[] priorities() default {Priority.LOW};
    Label[] labels() default {};
}
```

The expressions inside the array must have the corresponding valid element type. Example:

```java
@BatchInfo(
    retries = {1, 2, 3},
    tags = {"java", "annotations"},
    dependencies = {String.class, Integer.class},
    priorities = {Priority.HIGH},
    labels = {@Label("stable"), @Label("public")}
)
class BatchTask {
}
```

In this example, `Priority` and `Label` need to be declared as in the previous sections. This snippet illustrates how to apply the annotation, not a standalone program.

Things to remember:

1. **Empty arrays are valid:** `tags = {}`.
2. **Single-element arrays are valid:** `tags = {"java"}`.
3. **Curly braces can be omitted when passing a single matching value:** `tags = "java"` is equivalent in content to an array containing the single element `"java"` in annotation syntax.
4. **You cannot use `new` to create an array in an annotation:** `tags = new String[]{"java"}` is not an annotation array initializer form accepted by the language.
5. **Multidimensional arrays are invalid in element definitions:** `String[][] tags();` will be rejected by the compiler.
6. Each component value must satisfy the exact rules of the element type; for example, you cannot place `System.currentTimeMillis()` in an element of a `long[]` array.

The fact that regular Java allows `new String[] {...}` or `String[][]` does not change the specific rules for annotation values.

## 4. Runnable Example: All Five Type Categories and Arrays

Create a single file **`AnnotationElementTypesDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

enum Priority {
    LOW, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Profile {
    int retries() default 2;                      // Primitive
    String owner();                               // String
    Class<? extends Runnable> handler();          // Class
    Priority priority() default Priority.LOW;     // Enum
    Label label();                                // Annotation
    String[] tags() default {};                   // One-dimensional array
    boolean enabled() default true;               // Primitive
}

@Profile(
    owner = "core",
    handler = Thread.class,
    priority = Priority.HIGH,
    label = @Label("public"),
    tags = {"annotation", "java"}
)
public class AnnotationElementTypesDemo {
    public static void main(String[] args) {
        Profile profile =
                AnnotationElementTypesDemo.class.getAnnotation(Profile.class);

        System.out.println(profile.owner());
        System.out.println(profile.retries());
        System.out.println(profile.handler().getSimpleName());
        System.out.println(profile.priority());
        System.out.println(profile.label().value());
        System.out.println(String.join(", ", profile.tags()));
        System.out.println(profile.enabled());
    }
}
```

With JDK 17+:

```bash
javac --release 17 AnnotationElementTypesDemo.java
java AnnotationElementTypesDemo
```

Stdout:

```text
core
2
Thread
HIGH
public
annotation, java
true
```

**Line-by-line analysis:**

- `owner()` reads the supplied string `"core"`.
- `retries()` reads the **default** value `2`, because `@Profile` does not override this element.
- `handler()` returns `Class<? extends Runnable>` with the value `Thread.class`; `getSimpleName()` returns `Thread`.
- `priority()` receives the enum constant `Priority.HIGH`.
- `label()` returns the nested annotation; calling `value()` on it retrieves `"public"`.
- `tags()` is a `String[]` array provided with two elements.
- `enabled()` receives the default value `true`.

`@Retention(RetentionPolicy.RUNTIME)` is placed on `Profile` so that Reflection can retrieve `Profile` from the class. It is the code in `main` that **explicitly calls** `getAnnotation` and the accessors; the annotation does not print itself to stdout. `@Target(ElementType.TYPE)` restricts the places where `Profile` can be applied to matching type declarations.

## 5. value() Syntax, Single-Element Form, and Default Values

An annotation element named `value` has a special shorthand usage syntax:

```java
@interface Label {
    String value();
}
```

Two equivalent usages:

```java
@Label(value = "public")
class A {
}

@Label("public")
class B {
}
```

If the element name is **not `value`**, the name must be written explicitly:

```java
@interface Feature {
    String name();
}

@Feature(name = "billing")
class Billing {
}
```

`@Feature("billing")` is an error because `Feature` does not declare a `value()` element.

### 5.1. default Is an Annotation Value, Not a Method Body

```java
@interface Retry {
    int times() default 3;
    String[] errors() default {};
}
```

At the point of use, you can write `@Retry` without specifying any elements; when read, it receives the default `3` and an empty array.

The default value must be valid for the corresponding type category. Example:

```java
@interface Notification {
    String channel() default "email";
    Priority priority() default Priority.LOW;
    Class<?> payloadType() default String.class;
    Label label() default @Label("stable");
    int[] codes() default {200, 201};
}
```

All of these are valid given `Priority` and `Label` declared above.

**There is no `null` default value in annotations.** If you want to represent "unselected", design a clear, meaningful value such as an `UNKNOWN` enum value, an empty array, or a documented sentinel depending on your needs; you cannot write `String name() default null;`.

**Subtle point:** the default value belongs to the **annotation type declaration**; if the usage site does not specify the element, the system reading the annotation uses the default from the corresponding annotation definition. Changing a default can change the value observed at old usage sites when running with a new version of the annotation type, so defaults are also something to pay attention to when designing an API.

### 5.2. Array Values with value() Can Be Written Very Concisely

Standalone example: create the file **`AnnotationArrayShorthandDemo.java`**.

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@interface Aliases {
    String[] value() default {};
}

@Aliases("one")
class One {
}

@Aliases({"one", "two"})
class Two {
}

@Aliases
class Empty {
}

public class AnnotationArrayShorthandDemo {
    public static void main(String[] args) {
        System.out.println(Arrays.toString(
                One.class.getAnnotation(Aliases.class).value()));
        System.out.println(Arrays.toString(
                Two.class.getAnnotation(Aliases.class).value()));
        System.out.println(Arrays.toString(
                Empty.class.getAnnotation(Aliases.class).value()));
    }
}
```

Run:

```bash
javac --release 17 AnnotationArrayShorthandDemo.java
java AnnotationArrayShorthandDemo
```

Exact stdout:

```text
[one]
[one, two]
[]
```

Explanation:

- `@Aliases("one")` both omits the `value` name and uses the single-element shorthand for `String[]`.
- `@Aliases({"one", "two"})` supplies a two-element array using an annotation array initializer.
- `@Aliases` passes no value, so it receives the default empty array.
- `@Retention(RUNTIME)` enables the Reflection example to read the information at runtime.

For an `int[]` element, using `@Codes(404)` can also be valid if the annotation has `int[] value()`; however, `@Codes({404, 500})` is clearer when providing multiple values.

## 6. Annotation Values: "Right Type" Is Not Enough

Annotation values are generally **determined at compile time**. For primitive types and `String`, the compiler requires a valid **constant expression**. For `Class`, a class literal is required; for an enum, an enum constant; for a nested annotation, an annotation expression; and for an array, a permitted annotation initializer form.

### 6.1. Compile-Time Constants for Primitive Types and String

```java
final class ConfigConstants {
    static final int RETRIES = 1 + 2;
    static final String PREFIX = "/api";
}

@interface ApiSettings {
    int retries();
    String path();
}

@ApiSettings(
    retries = ConfigConstants.RETRIES,
    path = ConfigConstants.PREFIX + "/items"
)
class ItemApi {
}
```

The `static final` fields above are **constant variables** whose initializers are constant expressions, so the compiler can use them in annotations.

In contrast:

```java
class DynamicSettings {
    static final int RETRIES = Integer.parseInt("3");
}
```

Although `DynamicSettings.RETRIES` is `static final int`, it is **not a constant variable** in Java's sense because its initializer is a method call, so it cannot be used as the value of `retries = DynamicSettings.RETRIES` in an annotation. `final` by itself is not enough; the initializing expression must satisfy the compile-time constant conditions.

### 6.2. Invalid Value Forms

Suppose you have the declaration:

```java
@interface Settings {
    String name();
    Class<?> type();
    Priority priority();
}
```

The following usages **will all fail to compile**; each example illustrates an independent error:

```java
// Invalid: a method call is not a String constant.
@Settings(name = System.getProperty("name"),
          type = String.class, priority = Priority.HIGH)
class BadName {}

// Invalid: a method call is not a class literal.
@Settings(name = "ok",
          type = Class.forName("java.lang.String"),
          priority = Priority.HIGH)
class BadType {}

// Invalid: the result of a method call is not a direct enum constant.
@Settings(name = "ok",
          type = String.class,
          priority = Priority.valueOf("HIGH"))
class BadPriority {}
```

These are **deliberately invalid** examples to explain compiler rules, not runnable files. Beyond annotation rules, `Class.forName` also declares a checked exception in normal usage contexts; however, the sufficient reason to reject it here is that **it is not a permitted class literal**.

## 7. Forbidden Element Types and Why

The types below can be used in regular Java, but are **not permitted** as the return type of an annotation element:

| Deliberately Invalid Declaration | Why It Is Invalid | Appropriate Declaration Approach |
| --- | --- | --- |
| `Integer count();` | The `Integer` wrapper does not belong to the primitive category | `int count();` |
| `Object value();` | `Object` is not a permitted element type | Choose a valid explicit type, depending on the meaning |
| `List<String> tags();` | `List` does not belong to the permitted categories | `String[] tags();` |
| `Optional<String> name();` | `Optional` is not valid | `String name() default "";` when a sentinel is defined |
| `String[][] aliases();` | Multidimensional arrays are not permitted | `String[] aliases();` or a nested annotation model |
| `Runnable handler();` | An arbitrary interface is neither `Class` nor an annotation type | `Class<? extends Runnable> handler();` |
| `void run();` | `void` is not an annotation element type | Choose a valid return type; annotations do not contain behavior |
| `int[] values() default null;` | `null` is not a valid element value | `int[] values() default {};` |

**Example of interface instead of Class:** if you want metadata to represent a runnable *handler type*, `Class<? extends Runnable> handler();` stores the implementation type as `SomeRunnable.class`. It does not create an instance or invoke `run()` automatically; the processing code decides later how to instantiate and use it.

**Example of a complex structure:** instead of `Map<String, String>` (which is invalid), you can model it using nested annotations with valid elements:

```java
@interface Entry {
    String key();
    String value();
}

@interface Entries {
    Entry[] value();
}

@Entries({
    @Entry(key = "mode", value = "safe"),
    @Entry(key = "region", value = "apac")
})
class ServiceConfig {
}
```

This approach stores a key-value list at the metadata level; **it does not turn the annotation into a `Map` at all**. If duplicate-key checking or conversion to a Map is needed, the code consuming the annotation must handle it explicitly.

## 8. Annotation Elements Are Not Regular Methods

Beyond the return type, element methods also have their own restrictions:

- No parameters: `String name();` is valid, whereas `String name(int id);` is invalid.
- No method-level type parameters: you cannot declare `<T> T get();` as an element.
- No `throws` clause may be declared on an annotation element.
- No Java method body may be provided, even when you want to "compute a default value". An element's `default` keyword only accepts an **annotation value**, not a `default { ... }` statement block like an interface method.
- An invalid return type cannot be declared even if the element has a `default`. For example, `Integer count() default 3;` is still invalid.

Valid example:

```java
@interface RetryOptions {
    int limit() default 3;
    String[] reasons() default {};
}
```

This syntax describes static metadata. `RetryOptions` itself is not a callback, service, or functional interface containing processing logic.

## 9. Compile-Time Error Checking and Runtime Reading Are Two Different Steps

The compiler checks **the set of valid types and value expressions** when you declare/apply an annotation. For runtime code to read an annotation from an element via Reflection, the annotation also needs an appropriate retention policy:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface VisibleTag {
    String value();
}
```

Without declaring `@Retention`, the default retention is `CLASS`: the annotation may remain in the class file, but **standard Reflection does not see it**. Setting `RUNTIME` allows Reflection to query that metadata.

Two independent responsibilities:

1. **Compile-time type checking:** whether `String`, `Class`, `enum`, nested annotations, and one-dimensional arrays are valid; whether the expression satisfies the value rules.
2. **Runtime data reading:** whether the program has Reflection/a processor/a framework written to read that annotation; whether the retention is appropriate.

An annotation with valid types and `SOURCE` retention can be useful for source analysis tools, even though it cannot be read from compiled classes via Reflection. An annotation with `RUNTIME` retention still does not create business behavior on its own.

In the `AnnotationElementTypesDemo` example, the printed output comes from the calls `profile.owner()`, `profile.priority()`, and `profile.label().value()` after retrieving the annotation. They are **accessors that read metadata**, not calls executing the annotation's code.

## 10. Common Misconceptions

**"If a Java method can return a type, an annotation element can return it too."** False. `List<String>`, `Integer`, `Object`, or `Map` are regular Java types, but they do not belong to the categories permitted for elements.

**"Using a wrapper like `Integer` is equivalent to `int`."** False in annotation element declarations; you must use the specified primitive type.

**"`Class<?>` can store an object of the class."** False. It stores a **class literal**; getting an instance and runtime behavior requires separate processing code.

**"An enum in an annotation can also be passed as a string name."** False. `Priority.HIGH` is required, not `"HIGH"` or `Priority.valueOf("HIGH")`.

**"Every `static final` field is an annotation constant."** False. For primitive and string values, the initializer must be a compile-time constant expression according to Java rules.

**"You can use `new String[]{...}` because it is a valid String array."** False in annotation value expressions. Use `{...}` for arrays, or a single element when shorthand is permitted.

**"You can use `String[][]` as long as the innermost elements are String."** False. Annotation elements only support one-dimensional arrays.

**"You can use `null` to represent an absent option."** False. Annotation element values do not support `null`; design an appropriate default/sentinel.

**"Since annotations are read at runtime, the compiler probably doesn't check them."** False. Type and expression checking occur at compile time, whereas Reflection is the way metadata is consumed at runtime.

## 11. Self-Check Exercises

### Exercise 1 — Choose Valid Types

Mark the valid element types:

```java
// Read each line individually as an element declaration.
int retries();
Integer retryCount();
Class<? extends Runnable> handler();
String[] tags();
String[][] groups();
Priority priority();
Label label();
List<String> names();
char delimiter();
```

**Hint:** the valid ones are `int`, `Class<? extends Runnable>`, `String[]`, `Priority`, `Label`, and `char`; `Integer`, `String[][]`, and `List<String>` are forbidden.

### Exercise 2 — Constants and Computed Expressions

Which snippet is valid?

```java
static final int A = 2 + 3;
static final int B = Integer.parseInt("5");

@interface Limit {
    int value();
}

// Treat A and B as fields in a Constants class:
// @Limit(Constants.A)
// @Limit(Constants.B)
```

**Hint:** `A` is a constant variable, so it is allowed; `B` is assigned from a method call, so it is not a constant expression.

### Exercise 3 — Array Values

Given `@interface Tags { String[] value() default {}; }`, predict the resulting array contents of:

```java
@Tags
class NoTag {}

@Tags("java")
class OneTag {}

@Tags({"java", "core"})
class TwoTags {}
```

**Hint:** `[]`, `["java"]`, and `["java", "core"]`, respectively. This represents the array contents, not mandatory output syntax.

### Exercise 4 — Using Nested Annotations

Why is `@Endpoint(label = @Label("public"))` valid when `Endpoint.label()` returns the annotation type `Label`? Why is `label = new Label()` not an equivalent assignment?

**Hint:** elements directly support annotation expressions; annotation types are not instantiated like regular Java objects using `new`.

### Exercise 5 — Designing Metadata with a List of Key-Value Pairs

If `Map<String,String>` is not permitted, declare `@Entry(key, value)` and `@Entries(Entry[] value)` yourself as in Section 7. Try replacing `@Entries({@Entry(...), @Entry(...)})` with a single-element annotation. According to the array rules, you can write `@Entries(@Entry(key = "k", value = "v"))`.

## 12. Things to Remember When Designing Annotation Types

When you want to add an element to an annotation, check in order:

1. **Return type:** does it belong to primitives, `String`, `Class`, `enum`, annotations, or a one-dimensional array of those types?
2. **Value expression:** is it a valid primitive/String constant, class literal, enum constant, annotation expression, or array initializer?
3. **Default value:** if present, does it have the right type and avoid using `null`?
4. **Structural clarity:** would an `enum`, nested annotation, or `T[]` express the metadata better than cramming multiple values into a single `String`?
5. **Consumer:** who reads the annotation, at compile time or runtime, and is the retention appropriate?

Annotations help describe metadata clearly when types and values are validated early by the Java compiler. Choosing the right valid element types is the foundation for building readable annotations, avoiding compilation errors, and ensuring that the data received by tools/frameworks has a consistent structure.
