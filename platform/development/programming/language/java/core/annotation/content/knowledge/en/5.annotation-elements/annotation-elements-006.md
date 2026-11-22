# Why Are `null`, Method Calls, and Arbitrary Objects Invalid in Java Annotation Values?

## 1. Annotations Are Metadata Declared Under Specific Rules

A Java annotation attaches information to a declaration or a type. When declaring an annotation using `@interface`, the parameterless methods inside it define **elements**; each element has a type and may have a `default` value. For example:

```java
@interface Task {
    String name();
    int retryCount() default 3;
}
```

At the annotation use site, `@Task(name = "compile")` supplies a value for `name()`, while `retryCount()` takes the default `3`.

Unlike arguments passed to a regular Java method, **annotation values must be representable according to language rules at compile time**. It is not a position that allows supplying any arbitrary Java expression. Three cases that easily cause confusion are:

- `null`: not a valid value for any annotation element, including elements with a reference type.
- **Method calls**: `method()`, `System.getProperty(...)`, `SomeEnum.valueOf(...)` do not constitute valid annotation values, even if the result has a matching type and the computation seems simple.
- **Arbitrary objects**: annotation elements cannot be declared with `Object`, `List<String>`, `LocalDate`, or arbitrary classes; `new SomeClass(...)` expressions are also not valid annotation values.

To understand why, we need to distinguish two layers: **the types allowed for an element** and **the expressions allowed to be assigned to that element**.

## 2. Which Types Are Allowed to Be Declared as Elements?

Java restricts the return type of an element in `@interface` to the following categories:

| Element type | Valid declaration | Example valid values |
|---|---|---|
| Primitive types | `int level();`, `boolean enabled();` | `3`, `true` |
| `String` | `String name();` | `"compile"` |
| `Class` or an appropriate parameterized form | `Class<?> type();` | `String.class` |
| An enum type | `Mode mode();` | `Mode.FAST` |
| Another annotation type | `Info info();` | `@Info("core")` |
| A **one-dimensional** array of one of the above categories | `String[] tags();` | `{"java", "core"}` |

Examples of valid definitions:

```java
enum Mode { FAST, SAFE }

@interface Info {
    String value();
}

@interface Config {
    String name();
    int attempts() default 1;
    Class<?> implementation();
    Mode mode() default Mode.SAFE;
    String[] tags() default {};
    Info info() default @Info("none");
}
```

You must not extrapolate from how Java generics or polymorphism work to assume that any `Object` can be used in an annotation. The following declarations are **intentionally invalid**, for illustration only, and cannot compile:

```java
@interface InvalidConfig {
    Object anything();              // Invalid: Object is not a valid element type
    java.time.LocalDate date();     // Invalid: regular class
    java.util.List<String> tags();  // Invalid: List<String>
    String[][] matrix();            // Invalid: multidimensional array
}
```

A common point of confusion: a `Class<?> implementation()` element is **valid**, even though a `Class` object is still a reference type. However, the supplied value must be a **class literal** such as `String.class`, not a reference to an arbitrary `Class` object that is computed or stored in advance.

The restrictions on element types are defined in the Java Language Specification (JLS) §9.6.1; the restrictions on values are in §9.7.1. They are not rules specific to Spring or any framework.

## 3. Why Is `null` Always Invalid?

Regular Java allows `null` for reference types:

```java
String text = null;       // Valid in regular Java code
Class<?> target = null;   // Valid in regular Java code
```

However, the JLS specifies that **the value of an annotation element cannot be `null`**. This condition applies even when the element has type `String`, `Class<?>`, enum, a nested annotation, or an array. It also applies to `default` values.

```java
@interface Label {
    String value();
}

@Label("ready")
class ValidLabel {}

// INVALID: null is not an annotation element value
@Label(null)
class InvalidLabel {}
```

A default value cannot be `null` either:

```java
@interface InvalidDefaults {
    String name() default null;  // INVALID
}
```

An expression that produces `null` does not resolve this either:

```java
@interface Name {
    String value();
}

// INVALID: expression has a null value
@Name((String) null)
class InvalidName {}
```

**Why does this restriction exist?** Annotations are metadata represented by the compiler using well-defined value forms in class files and interpreted by the standard annotation API according to a restricted set of types. Under this model, `null` does not belong to the set of *element values* permitted by the JLS. Precisely speaking, the formal reason is a rule of the **Java language**, not because every reference object in the JVM cannot hold `null`.

When you want to represent an “unspecified” state, use an **explicit convention in the annotation API**, for example:

```java
@interface Endpoint {
    String description() default "";
    String[] tags() default {};
}
```

Here `""` is an empty string and `{}` is an empty array; both **are valid**. They do not automatically carry the meaning of `null`: the meaning of “undeclared” or “no elements” must be defined by documentation and the annotation-processing code. The string `"null"` is also just a **text string**, completely different from the `null` value.

If distinguishing between “not provided” and “provided as empty” is an important requirement, design the annotation API with an appropriate convention or separate element, because an element with `default` provides no way to accept `null` as an annotation value.

## 4. Why Can't You Pass Method Calls?

Consider this annotation:

```java
@interface Label {
    String value();
}
```

**Invalid** example:

```java
class Texts {
    static String generate() {
        return "compile";
    }
}

// INVALID: a method call is not a compile-time constant
@Label(Texts.generate())
class InvalidTask {}
```

Even though `generate()` always returns the same string at runtime, it is still a **runtime method call**, not a **constant expression** according to the JLS. The Java compiler does not execute developer-written methods just to obtain annotation values, even when the method is `static`, `final`, very short, or “side-effect-free”.

Some similarly invalid expressions (each declaration is a separate example):

```java
@Label(System.getProperty("app.name"))
class FromProperty {}    // INVALID

@Label(String.valueOf(123))
class FromConversion {}  // INVALID

@Label("abc".toUpperCase())
class FromMethod {}      // INVALID
```

You need to distinguish **the final value** from **how the value is produced**. `"ABC"` is a string literal and is therefore valid; `"abc".toUpperCase()`, even though we know it will return `"ABC"`, is syntactically a method call and therefore does not qualify as a valid constant expression for a `String` element.

### 4.1. Replace with a Compile-Time Constant Expression

Expressions such as literals, operations on constants, and string concatenation of constants can be evaluated by Java at compile time:

```java
final class Names {
    static final String PREFIX = "java";
    static final String MODULE = PREFIX + "-core";
    static final int RETRIES = 1 + 2;
}

@interface Build {
    String name();
    int retries();
}

@Build(name = Names.MODULE, retries = Names.RETRIES)
class JavaBuild {}
```

The `name` element receives `"java-core"`; `retries` receives `3`. The fields referenced here are **constant variables** (`final` variables of primitive type or `String`, initialized with a constant expression).

### 4.2. `static final` Is Not Enough to Make Every Value a Compile-Time Constant

Consider two declarations:

```java
class Names {
    static final String GOOD = "compile" + "-ready";
    static final String NOT_CONSTANT = new String("compile-ready");
}
```

`GOOD` is a constant variable. `NOT_CONSTANT` is also a `static final String` and cannot be reassigned after initialization, but creating `new String(...)` makes **the initializer not a constant expression**.

```java
@Label(Names.GOOD)
class ValidBuild {}

// INVALID: the NOT_CONSTANT field is not a constant variable
@Label(Names.NOT_CONSTANT)
class InvalidBuild {}
```

Similarly, `static final String S = System.getenv("APP")` and `static final int N = Integer.parseInt("3")` **are not compile-time constants**. The `final` keyword only restricts reassignment of the variable; it does not require the JVM to have the value at compile time.

### 4.3. Conditional Expressions Can Also Be Valid

Not **every expression containing operators** is forbidden. When all operands satisfy the rules for constant expressions, a conditional expression can also be valid:

```java
@Label(true ? "fast" : "safe")
class FixedChoice {}
```

Conversely, if the condition depends on a method such as `Boolean.getBoolean("fast")`, the expression is no longer a constant expression and cannot be used for a `String` element. The rule to check is “**is it a constant expression?**”, not simply “only literals may be used”.

## 5. Exceptions with Special Forms: `Class`, Enums, Nested Annotations, and Arrays

The constant expression requirement for **primitive types or `String`** does not mean that all annotation values must be numeric or string literals. Other type categories have **specific valid syntax** according to the JLS.

### 5.1. `Class<?> `: use a `.class` class literal

```java
@interface Handler {
    Class<?> value();
}

@Handler(String.class)
class StringHandler {}

@Handler(int.class)
class PrimitiveHandler {}
```

`String.class` and `int.class` are **class literal expressions**, which Java permits directly for `Class`-typed annotation elements. Conversely, the following are invalid:

```java
class Types {
    static final Class<?> STRING_TYPE = String.class;
    static Class<?> lookup() { return String.class; }
}

// INVALID: referencing a Class-typed variable, even if static final
@Handler(Types.STRING_TYPE)
class FieldBasedHandler {}

// INVALID: method call
@Handler(Types.lookup())
class DynamicHandler {}
```

`Class` is a reference type, and Java does not support `Class`-typed **constant variables**, since the definition of a constant variable applies only to primitives and `String`. Therefore, even if a `static final Class<?>` field always holds `String.class`, at the annotation use site you must still write a **class literal**.

### 5.2. Enums: use an enum constant

```java
enum Mode { FAST, SAFE }

@interface RunMode {
    Mode value();
}

@RunMode(Mode.FAST)
class QuickTask {}
```

`Mode.FAST` is an **enum constant**, which is valid. The expressions below are invalid:

```java
class Modes {
    static final Mode DEFAULT = Mode.FAST;
}

// INVALID: a final variable of an enum type is not a direct enum constant
@RunMode(Modes.DEFAULT)
class FromAlias {}

// INVALID: a method call is not an enum constant
@RunMode(Mode.valueOf("FAST"))
class FromMethod {}
```

Here `Mode.FAST` is not a `String` constant expression. It is valid because the JLS has a specific rule for enum elements: it must be an **enum constant** of the appropriate type.

### 5.3. Nested annotations: use annotation syntax

```java
@interface Info {
    String value();
}

@interface Detail {
    Info value();
}

@Detail(@Info("verified"))
class Document {}
```

An annotation is a supported value type for nesting inside another annotation. The form `@Info("verified")` is an **annotation expression** with its own syntax, not a constructor call like `new Info(...)`, and cannot be replaced by an object returned from a method either.

### 5.4. Arrays: use an initializer in the annotation

```java
@interface Tags {
    String[] value();
}

@Tags({"java", "core"})
class MultiTags {}

@Tags("java")
class OneTag {}

@Tags({})
class NoTags {}
```

`@Tags("java")` is a permitted shorthand syntax: for an array-typed element, a single element value can stand in for a single-element array. Therefore, reading `value()` still yields `String[]`. For multiple values or an empty array, use `{...}`.

The following forms are **invalid**:

```java
@Tags({null})
class NullElement {}      // null is invalid even inside an array

@Tags(new String[]{"java"})
class ConstructedArray {} // cannot use new String[] for an annotation element

class TagStore {
    static final String[] VALUES = {"java"};
}

@Tags(TagStore.VALUES)
class ArrayField {}       // cannot use a variable referencing an array
```

It is not because `new String[]` cannot create an array, but because an **annotation element value** requires an *element-value array initializer* `{...}` or a single *element value* valid for the element type, rather than an arbitrary object/array creation expression.

## 6. Complete Runnable Example on Java 17+

Create the file **Main.java**:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@interface Detail {
    String value();
}

enum Policy {
    STRICT, LENIENT
}

final class Const {
    static final String TITLE = "module" + "-A";
    static final int RETRIES = 1 + 2;

    // The following two fields are references and cannot be passed by field name
    // as annotation element values:
    static final Class<?> TYPE = String.class;
    static final Policy DEFAULT_POLICY = Policy.STRICT;
}

@Retention(RetentionPolicy.RUNTIME)
@interface Stamp {
    String title();
    int retries() default 2;
    Class<?> target();
    Policy policy();
    String[] tags() default {};
    Detail detail() default @Detail("none");
}

@Stamp(
        title = Const.TITLE,
        retries = Const.RETRIES,
        target = String.class,
        policy = Policy.STRICT,
        tags = {"java", "annotation"},
        detail = @Detail("checked")
)
class Job {}

public class Main {
    public static void main(String[] args) {
        Stamp stamp = Job.class.getAnnotation(Stamp.class);
        System.out.println("title=" + stamp.title());
        System.out.println("retries=" + stamp.retries());
        System.out.println("target=" + stamp.target().getName());
        System.out.println("policy=" + stamp.policy());
        System.out.println("tags=" + Arrays.toString(stamp.tags()));
        System.out.println("detail=" + stamp.detail().value());
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Expected output:

```text
title=module-A
retries=3
target=java.lang.String
policy=STRICT
tags=[java, annotation]
detail=checked
```

**Explanation for each value:**

1. `Const.TITLE` is evaluated by the compiler to `"module-A"`, and `Const.RETRIES` to `3`: both `String`/`int` fields are constant variables.
2. `String.class` is a class literal. The code does not use `Const.TYPE`, because a reference to a `Class<?>`-typed field is invalid in an annotation.
3. `Policy.STRICT` is a direct enum constant. The code does not use `Const.DEFAULT_POLICY`, even though it is `static final`.
4. `{"java", "annotation"}` is an array initializer in which each element is valid.
5. `@Detail("checked")` is a nested annotation. `@Retention(RUNTIME)` allows inspecting the metadata via reflection in this example; the valid value rules apply even when reflection is not used.

This example shows that annotations store **structured metadata checked at compile time**, rather than executing methods when reading the annotation. At runtime, `getAnnotation()` returns the annotation representation to access the declared values.

## 7. The Same Rules Apply to `default`

It is easy to make mistakes when focusing on checking values at the use site while overlooking the `default` clauses in the `@interface` definition.

Valid example:

```java
enum State { READY, PAUSED }

@interface Feature {
    String name() default "unknown";
    int timeout() default 2 * 30;
    Class<?> handler() default String.class;
    State state() default State.READY;
    String[] tags() default {};
}
```

Invalid example, for analysis only and **cannot compile**:

```java
@interface InvalidFeature {
    String name() default null;                // null is forbidden
    String title() default System.getProperty("title"); // method call
    Class<?> handler() default Object.class.getClass(); // method call
}
```

If you want an “unset” value, consider a default value with a clear meaning such as `""`, `{}`, an `UNSPECIFIED` enum constant, or a sentinel class such as `Void.class` (if the API contract specifies it). **Do not assume every framework interprets `Void.class` or an empty string the same way**.

## 8. How to Check an Annotation Value Error

When you see the error `element value must be a constant expression` or a similar message, check in the following order:

1. **Is the element type** in `@interface` one of the categories supported by Java? If it is `Object`, `List`, a wrapper such as `Integer`, a domain class type, or a two-dimensional array, fix the definition.
2. **Is there a `null`?** `null` is forbidden for every kind of element, including individual array elements.
3. **If it is a primitive/`String`**: is it a constant expression? Literals, valid operators, and `final` primitive/`String` variables initialized from constants can be used; method calls, `new`, and fetching runtime configuration data cannot.
4. **If it is a `Class`**: are you writing `Type.class` (or a primitive class literal) directly? Do not substitute a `static final Class<?> TYPE` field or a method returning `Class`.
5. **If it is an enum**: are you using the enum constant itself (`Mode.FAST`)? Avoid alias fields, `valueOf()` results, or factory methods.
6. **If it is an annotation or an array**: use `@Nested(...)` and `{...}` with proper syntax; ensure each child element also satisfies the corresponding rules.
7. **Read the compiler warning/error carefully**: messages may differ between `javac` and IDEs, but the root cause should be checked against JLS §9.6.1 and §9.7.1.

### Self-Check Exercise

Given:

```java
@interface Label {
    String value();
}

class Constants {
    static final String A = "java" + "-17";
    static final String B = new String("java-17");
    static String get() { return "java-17"; }
}
```

Identify which lines compile (the lines below are **independent examples**, some of which are invalid):

```java
@Label("java-17")       // (1) valid: literal
@Label(Constants.A)     // (2) valid: constant variable
@Label(Constants.B)     // (3) invalid: initializer uses new
@Label(Constants.get()) // (4) invalid: method call
@Label(null)            // (5) invalid: null
@Label("java" + "-17")  // (6) valid: concatenation of constant strings
```

There is no meaningful runtime difference among the three valid forms (1), (2), and (6): all of them represent the same `String` value in the annotation. The three invalid forms do not become valid by arbitrarily adding `static` or `final`.

## 9. Official References

- [Java Language Specification 17, §9.6.1 — Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1): valid return types of annotation elements.
- [Java Language Specification 17, §9.7.1 — Normal Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1): the *commensurate* condition for element values, in which `null` is excluded; `Class`, enums, and arrays have specific rules.
- [Java Language Specification 17, §15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29): constant expressions and operations permitted for primitive/`String` elements.
- [Java Language Specification 17, §4.12.4 — `final` Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): definition of a **constant variable**.

**Key takeaway:** Annotation values are subject to stricter constraints than regular method arguments. `null` is never valid. Primitives and `String` must be **constant expressions**; `Class`, enums, nested annotations, and arrays have fixed syntactic forms. A method call or a `static final` object reference does not automatically become valid metadata just because its result is known in advance.
