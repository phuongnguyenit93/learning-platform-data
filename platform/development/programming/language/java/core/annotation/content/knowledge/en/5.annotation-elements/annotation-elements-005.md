# Constant Expressions, Class Literals, and Value Restrictions at Annotation Use Sites in Java

Annotations in Java do not accept every expression that a normal method call can accept. For example, a method with an `int` parameter can be called with `Integer.parseInt("3")`, but an `int` element in an annotation does **not** accept this call as a value. The reason is that Java needs to represent annotation values according to strict language rules and, depending on retention, write that metadata into the class file.

This lesson explains **what values are allowed directly at an annotation use site** (`@Config(...)`): when to use a constant expression, when `SomeType.class`, an enum constant, or a nested annotation is required; constraints on arrays, data types, defaults, and common compilation errors. Examples are based on Java 17 and later.

## 1. Two Steps to Distinguish: Declaring Elements and Passing Values

Suppose we have the definition:

~~~java
@interface Retry {
    int count();
    String reason() default "temporary";
}
~~~

This is an **annotation type declaration**: each parameterless method represents an element. At the use site, the element name is on the left of the `=` sign, and the expression on the right is the **element value**:

~~~java
@Retry(count = 2 + 1, reason = "network")
class Worker {
}
~~~

- `count = 2 + 1` is valid because `2 + 1` is a constant expression of type `int`.
- `reason = "network"` is valid because it is a `String` literal.
- `reason` can be omitted because this element has a default.
- **Do not omit** `count`: an element without a default must be provided at the use site.
- When an annotation only has an element named `value`, there is a shorthand syntax `@Name(argument)` instead of `@Name(value = argument)`. That shorthand syntax does not apply arbitrarily to an element with a different name.

For an annotation element of type `int`, the element's return type only determines the **data type domain**; the rules for using annotations also require the expression to be **constant at compile time**. Similarly, for an element of type `Class<?>`, having a variable of type `Class<?>` is not enough: a valid **class literal** must be provided.

## 2. Which Element Types Are Allowed by Java?

When declaring an annotation type, the return type of an element can only be:

| Category | Declaration Example | Valid Value Form at Use Site |
| --- | --- | --- |
| Primitive types | `int retries();`, `boolean enabled();`, `char separator();` | Type-compatible **constant expression** |
| `String` | `String name();` | **Constant expression** of type `String` |
| `Class` or a suitable parameterized form | `Class<?> handler();`, `Class<? extends Number> type();` | **Class literal**, e.g., `String.class`, `Integer.class` |
| Enum | `Mode mode();` | **Enum constant**, e.g., `Mode.SAFE` |
| Another annotation | `Owner owner();` | **Nested annotation**, e.g., `@Owner(name = "team")` |
| One-dimensional array of the types above | `String[] tags();`, `Class<?>[] types();` | **Array initializer** consisting of valid element values, e.g., `{"a", "b"}` |

Do not declare elements of type `Object`, `Object[]`, `List<String>`, `Map<String, String>`, a regular business class, or a multidimensional array such as `int[][]`. An annotation type also cannot define elements with parameters, generic methods, or `throws`.

The condition of a **valid element type** and a **valid element value** are two separate conditions. For example, `String title();` is a valid declaration, but `title = System.getenv("TITLE")` is still invalid at the use site.

## 3. Constant Expressions for Primitives and `String`

A **constant expression** according to the Java Language Specification (JLS §15.29) is an expression that yields a value of a primitive type or `String`, can be evaluated at compile time, and uses only the forms permitted by the specification.

Valid examples:

~~~java
@interface Limits {
    int max();
    String label();
    boolean active();
    char symbol();
}

@Limits(
    max = 2 * (3 + 1),
    label = "batch-" + 2026,
    active = (10 > 2) && true,
    symbol = 'A'
)
class BatchA {
}
~~~

Here `max = 8` and `label = "batch-2026"` can both be determined at compile time. Numeric addition, string concatenation, relational/logical expressions, and the conditional operator `?:` can participate in a constant expression when all required parts are valid according to the JLS.

### 3.1. `static final` Does Not Guarantee a Usable Constant

A **constant variable** must be a `final` variable of a primitive type or `String` that is initialized with a constant expression. A `static final` variable initialized with the result of a method call is **not** a constant variable.

~~~java
final class Settings {
    static final int FIXED = 2 * 3;                 // Valid.
    static final int COMPUTED = Integer.parseInt("6"); // Not a constant variable.
    static final String KEY = "service." + "timeout";   // Valid.
    static final String DYNAMIC = System.getProperty("app.name"); // Not constant.
}

@interface Level {
    int value();
}

@Level(Settings.FIXED)       // Valid: constant expression.
class JobA {
}

// @Level(Settings.COMPUTED) // Compilation error if // is removed.
// class JobB {}
~~~

`Settings.COMPUTED` is still an `int` and `static final`, but its initializer requires executing a method, so it does not satisfy the annotation rules. For `String`, concatenating constant strings is generally valid; a `String` created by a method call, such as `"abc".toUpperCase()`, is **not** a constant expression even though a developer can predict the result.

**Constant variables** can be referenced via the class name (`Constants.MAX`) when accessible. It is not required to write every value as a literal directly inside the annotation.

### 3.2. A Constant Expression Is Not Equivalent to Everything Known at Runtime

The following expressions are **not** valid as values for primitive/`String` annotation elements:

~~~java
// Intentionally invalid illustration, DO NOT put into a runnable file.
//
// @Level(Integer.parseInt("3"))    // Method invocation.
// @Level(new Integer(3))           // Object creation (and old constructor API).
// @Level(Math.abs(-3))              // Method invocation even though the result is easy to predict.
//
// int[] numbers = {3};
// @Level(numbers[0])                // Array access, not a constant expression.
~~~

For annotations, `final` only prevents reassigning the variable; it **does not turn** every runtime-initialized value into a compile-time constant. A `static` method, pure method, or getter is not automatically allowed to appear in an element value.

### 3.3. Type Compatibility and Narrowing of Constant Values

The expression must be compatible with the element type according to the assignment context rules permitted by annotations. For example:

~~~java
@interface Priority {
    byte value();
}

@Priority(120)
class NormalPriority {
}

// @Priority(128)   // Error: 128 exceeds the byte range.
// class TooLarge {}
~~~

Even though the literal `120` has type `int`, Java allows a **narrowing conversion of a constant expression of type `int`** to `byte` when the value is within the valid range. Do not assume that annotations allow every implicit type conversion: an out-of-range value, a non-constant expression, or an incompatible type will still be rejected.

## 4. Class Literals: `Type.class` Has Its Own Set of Rules

When an element has type `Class` or `Class<?>` (or a suitable parameterized type), the value must be a compatible **class literal**:

~~~java
@interface Codec {
    Class<?> value();
}

@Codec(String.class)
class TextCodec {
}

@Codec(int[].class)
class IntegerArrayCodec {
}
~~~

Common forms of class literals are `String.class`, `Integer.class`, `int.class`, `void.class`, `String[].class`. They are class literal expressions defined by the language, **not** primitive/`String` constant expressions from section 3.

If the element is declared as `Class<? extends Number>`, the compiler additionally checks the generic bound:

~~~java
@interface NumberFormat {
    Class<? extends Number> value();
}

@NumberFormat(Integer.class)
class IntegerFormat {
}

// @NumberFormat(String.class) // Type error: String does not extend Number.
// class BadFormat {}
~~~

The following approaches are not accepted in place of `Type.class`:

~~~java
// Intentionally invalid illustration:
//
// static final Class<?> TEXT = String.class;
// @Codec(TEXT)                     // Class variable, not a class literal.
// @Codec(Class.forName("java.lang.String")) // Method call.
// @Codec(new Object().getClass())  // Method call.
// @Codec(java.util.List<String>.class) // No class literal exists for a parameterized type.
~~~

`java.util.List.class` is a valid class literal; `List<String>.class` is not because Java does not have a separate class literal for a parameterized generic type. If you need to choose an implementation based on runtime config, use another design (for example, a validated key name and a registry mapping to the class), rather than trying to pass `Class.forName(...)` into an annotation.

## 5. Enum Constants: Must Explicitly Name an Enum Member

Given:

~~~java
enum Mode {
    FAST, SAFE
}

@interface Execution {
    Mode mode();
}

@Execution(mode = Mode.SAFE)
class SafeTask {
}
~~~

Java requires the value to be an **enum constant** compatible with the element. A `static final` variable holding an enum constant cannot substitute for an enum constant in an annotation:

~~~java
final class ModeSettings {
    static final Mode DEFAULT = Mode.SAFE;
}

// @Execution(mode = ModeSettings.DEFAULT) // Compilation error.
// class InvalidTask {}
~~~

Unlike primitive/`String` variables, enum variables do not fall under the constant variable concept of JLS §4.12.4. The value `Mode.SAFE` is valid because it is itself an **enum constant**, not because it is assigned to a `final` variable.

## 6. Nested Annotations and Array Values

### 6.1. Nested Annotations

An annotation element can have the type of another annotation. At the use site, write an annotation literal:

~~~java
@interface Owner {
    String name();
}

@interface Assigned {
    Owner owner();
}

@Assigned(owner = @Owner(name = "platform"))
class AssignedJob {
}
~~~

You cannot replace `@Owner(...)` with `new Owner(...)`, because an annotation is metadata represented through annotation syntax, not instantiated with a regular class constructor.

### 6.2. One-Dimensional Arrays

~~~java
@interface Labels {
    String[] value();
}

@Labels({"backend", "java"})
class ServiceA {
}

@Labels("backend")
class ServiceB {
}

@Labels({})
class ServiceC {
}
~~~

`@Labels({"backend", "java"})` uses the shorthand syntax because the element is named `value`. A single-element array can be written concisely as `@Labels("backend")`; `@Labels({})` is an empty array. The equivalent full form is: `@Labels(value = {"backend", "java"})`.

**Important limitation:** you can write an **array initializer** directly, but you cannot use an array variable, a method returning an array, or `new String[]{...}` as an annotation element value:

~~~java
// Intentionally invalid illustration:
// static final String[] TAGS = {"backend", "java"};
// @Labels(TAGS)                         // Invalid.
// @Labels(new String[]{"backend"})      // Invalid.
// @Labels(java.util.List.of("backend").toArray(String[]::new)) // Invalid.
~~~

Each element of the array must also obey its own category's rules. For example, `Class<?>[]` must accept class literals; `Mode[]` must accept enum constants; `Owner[]` must accept nested annotation values. Do not declare elements of type `String[][]` or `int[][]`.

### 6.3. `null` Is Not a Valid Annotation Value

A `null` value is not allowed for any annotation element, including `String`, `Class<?>`, annotation types, or arrays. To represent "not configured", consider `default ""`, `default {}`, an explicitly named enum sentinel, or moving customization policy to runtime configuration. A sentinel must have documented semantics, because `""` or an empty array could also be a valid business value.

## 7. Runnable Java 17 Example: All Value Categories

Create a single file named **`AnnotationValueDemo.java`** with the following contents:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

final class Constants {
    static final int BASE_RETRIES = 2;
    static final String PREFIX = "job-";
    private Constants() {}
}

enum Mode { FAST, SAFE }

@Retention(RetentionPolicy.RUNTIME)
@interface Owner {
    String name();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Task {
    int retries();
    String label();
    Class<? extends Number> numberType();
    Mode mode();
    Owner owner();
    String[] tags();
    int timeoutMs() default 1_000 * 2;
}

@Task(
    retries = Constants.BASE_RETRIES + 1,
    label = Constants.PREFIX + "sync",
    numberType = Integer.class,
    mode = Mode.SAFE,
    owner = @Owner(name = "platform"),
    tags = {"core", "batch"}
)
final class SyncJob {}

public class AnnotationValueDemo {
    public static void main(String[] args) {
        Task meta = SyncJob.class.getAnnotation(Task.class);
        System.out.println("retries=" + meta.retries());
        System.out.println("label=" + meta.label());
        System.out.println("numberType=" + meta.numberType().getSimpleName());
        System.out.println("mode=" + meta.mode());
        System.out.println("owner=" + meta.owner().name());
        System.out.println("tags=" + Arrays.toString(meta.tags()));
        System.out.println("timeoutMs=" + meta.timeoutMs());
    }
}
~~~

Compile/run from the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 AnnotationValueDemo.java
java AnnotationValueDemo
~~~

**Stdout verified with `javac --release 17`:**

~~~text
retries=3
label=job-sync
numberType=Integer
mode=SAFE
owner=platform
tags=[core, batch]
timeoutMs=2000
~~~

Explanation:

1. `retries = Constants.BASE_RETRIES + 1` and `label = Constants.PREFIX + "sync"` are two constant expressions from `static final` variables of primitive/`String` types with constant initializers.
2. `numberType = Integer.class` is a **class literal**, satisfying the `Class<? extends Number>` bound.
3. `mode = Mode.SAFE` is an **enum constant**; it does not need to be, and must not be, replaced by an enum alias variable.
4. `owner = @Owner(...)` is a **nested annotation**, not a method or constructor call.
5. `tags = {"core", "batch"}` is an **array initializer** containing two valid `String` literals.
6. `timeoutMs()` has a default of `1_000 * 2`, which is also a constant expression. The use site does not specify `timeoutMs`, so the program reads the value `2000`.

In this example, `@Retention(RetentionPolicy.RUNTIME)` is used to demonstrate reading metadata via reflection. **Retention is independent of element value validity**: even when retention is `SOURCE`, the element expression must still be valid at compile time; `RUNTIME` does not allow method calls or runtime variables as annotation values.

## 8. Common Compilation Errors at Use Sites

This table assumes the annotation element has already been declared with the corresponding type.

| Written in Annotation | Status | Reason |
| --- | --- | --- |
| `retries = 1 + 2` (`int`) | Valid | Constant expression |
| `retries = Constants.BASE_RETRIES` (`int`) | Valid | Reference to a constant variable |
| `retries = Integer.parseInt("3")` | Error | A method invocation is not a constant expression |
| `label = "job-" + "sync"` (`String`) | Valid | Concatenation of two String constants |
| `label = System.getenv("JOB_NAME")` | Error | Runtime value |
| `numberType = Integer.class` (`Class<? extends Number>`) | Valid | Class literal of a compatible type |
| `numberType = String.class` (`Class<? extends Number>`) | Error | Generic bound mismatch |
| `numberType = savedClass` (`Class<?>`) | Error | Class variable is not a class literal |
| `mode = Mode.FAST` (`Mode`) | Valid | Enum constant |
| `mode = ModeSettings.DEFAULT` (`Mode`) | Error | static final variable alias is not an enum constant |
| `owner = @Owner(name = "team")` | Valid | Nested annotation |
| `tags = {"a", "b"}` (`String[]`) | Valid | Annotation array initializer |
| `tags = "a"` (`String[]`) | Valid | Shorthand for a single-element array |
| `tags = someArray` (`String[]`) | Error | Array variable reference |
| `label = null` | Error | `null` is prohibited in annotation element values |

### A Small but Easy-to-Make Mistake: static final vs immutable reference

~~~java
final class Values {
    static final int COUNT = 3;
    static final Integer BOXED = 3;
    static final String TEXT = "count-" + COUNT;
    static final String FROM_METHOD = String.valueOf(COUNT);
}
~~~

- `COUNT` can be used for an element of type `int`.
- `BOXED` is **not** a constant variable (type `Integer`, not a primitive/`String`), even though the reference is `final`. An annotation element also cannot be declared with type `Integer`.
- `TEXT` can be used for an element of type `String`.
- `FROM_METHOD` cannot be used because its initializer is a method invocation.

Java can autobox some values in normal expressions, but the rules for annotation types/values remain much narrower.

## 9. Default Values, Compiler Tooling, and Constant Changes

An element default is declared with:

~~~java
@interface RetryPolicy {
    int maxAttempts() default 2 + 1;
    String[] labels() default {"safe", "internal"};
}
~~~

A default is also an **annotation element value** and is subject to the same rules regarding type and expression form. `default` in an annotation element declaration is **not a Java interface default method**: there is no method body; Java supplies the value when reading an annotation where the use site does not override that element.

When changing a default value in an annotation definition and compiling/deploying the new version of the definition, an annotation without an explicit value may be read with the new default, even if the annotated class has not been recompiled. Therefore, **changing a default changes metadata behavior** and compatibility must be considered. Conversely, a reference to a primitive/`String` constant variable at the use site may already have had its value baked into the metadata of the using class by the compiler; changing the constant in another source **does not guarantee** that already-compiled annotations will update accordingly. For this kind of change, classes using the annotation must be recompiled if synchronized metadata is desired.

Note: annotations are not a dynamic configuration mechanism. If values such as URLs, environment-specific timeouts, feature flags, or secrets need to change at deployment time, runtime configuration is usually required rather than trying to embed a `System.getenv` call into an annotation. You can use an annotation for a fixed key name and let a framework resolve the runtime value, but **the framework processes that string**; the Java compiler does not perform environment interpolation automatically.

## 10. Process for Checking an Annotation Value

When the compiler reports an error at `@Something(...)`, check in order:

1. **Does the element exist?** The name on the left of `=` must match the method name in the annotation type; required elements must be provided or have a default.
2. **Is the element type allowed to be declared?** Only primitives, `String`, `Class`, enums, annotation types, or one-dimensional arrays of valid types.
3. **Which category does the value belong to?** Primitive/`String` requires a constant expression; `Class` requires a class literal; enum requires an enum constant; nested annotation requires an annotation literal; array requires an initializer containing valid element values.
4. **Is the type compatible?** Check the generic bound of `Class<? extends ...>`, the numeric range when narrowing, the type of each array element, and the enum type.
5. **Are you putting a runtime value into metadata?** Method calls, `final` fields initialized at runtime, object/array creation, `Class` variables, or `null` are usually signs of an error.
6. **Did you overlook shorthand syntax?** Only an element named `value` can use the `@Annotation(argument)` form; a single-element array can omit the curly braces if the compiler accepts the corresponding single-element value form.

The best practice is to isolate a **minimal Java file** containing the annotation definition and the failing use case, then run `javac --release 17` to inspect the specific compile error message. There is no need to wait until running the application or reflection to discover errors that the language already catches at compile time.

## 11. Self-Check Questions

**1. Why is `@Retry(count = 2 * 3)` valid, whereas `@Retry(count = Math.max(2, 3))` is invalid?** Because operations between literals can form a constant expression, whereas a method invocation is not among the constant expression forms allowed by the JLS.

**2. Can `static final String NAME = "api" + "-v1";` be used in an annotation?** Yes, because it is a constant variable of type `String` with a constant initializer. If the initializer is changed to `System.getProperty("name")`, the answer becomes no.

**3. Why is `@Codec(String.class)` valid while `@Codec(Class.forName("java.lang.String"))` is not?** Annotations require a compatible class literal and do not accept a method returning `Class`.

**4. Why is `@Execution(mode = Mode.SAFE)` valid while `@Execution(mode = Holder.MODE)` is not, even though `Holder.MODE` is `static final`?** Because an enum element must be an enum constant; a variable reference to an enum is not an enum constant expression under annotation rules.

**5. To specify two tags, should you use `tags = {"a", "b"}` or `tags = new String[]{"a", "b"}`?** Choose the first one, the array initializer. Annotation element values do not allow array creation expressions.

**6. Can you set `null` to indicate an annotation element is not configured?** No. Define a default/sentinel with clear semantics, or move truly dynamic options to another configuration mechanism.

## Standard References

- **JLS §9.6.1 — Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.1
- **JLS §9.6.2 — Defaults for Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.2
- **JLS §9.7.1 — Normal Annotations, Element Values:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.1
- **JLS §15.29 — Constant Expressions:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29
- **JLS §4.12.4 — Constant Variables:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4

If an annotation value makes you hesitate, determine the **element return type** first and apply the corresponding rule category. `Class` literals, enum constants, and nested annotations are not "primitive/String constant expressions" yet are still valid because they have their own rules; confusing these categories is the root cause of many annotation syntax errors.
