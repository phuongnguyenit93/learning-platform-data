# Constants, Enums, and Member Types Inside a Java `@interface`

An annotation type declared with `@interface` is a **special form of interface**. Inside its body, in addition to methods that declare *annotation elements* such as `String name();`, Java also allows declaring **constants, enums, and member types** (`class`, `interface`, nested annotations). They help group related names, conventional values, and data types directly inside the annotation definition.

Key point to understand first: **not every member in `@interface` is an element that can be passed in `@Annotation(...)`**. Only methods that declare elements become name–value pairs when the annotation is used. Constants and nested types are members of the **Java type**, supporting naming, organization, and element declarations.

## 1. Components That Can Be Declared Inside `@interface`

A valid structure:

```java
@interface ExportRule {
    int DEFAULT_LIMIT = 25;           // Constant (field)
    String DEFAULT_OWNER = "platform";

    enum Format { CSV, JSON }          // Nested enum type

    @interface Reviewer {             // Nested annotation type
        String value();
    }

    Format format() default Format.JSON;                    // Element
    int limit() default DEFAULT_LIMIT;                      // Element
    Reviewer reviewer() default @Reviewer(DEFAULT_OWNER);   // Element
}
```

Here:

| Declaration | Role | Used in `@ExportRule(...)` as an element name? |
| --- | --- | --- |
| `DEFAULT_LIMIT`, `DEFAULT_OWNER` | Constant fields of `ExportRule` | **No**: these are fields, not elements. |
| `enum Format` | Defines an enum type, providing `CSV`/`JSON` | **No**: it is a type name used as the return type of the `format()` element. |
| `@interface Reviewer` | Defines another annotation type nested inside `ExportRule` | **No**: it is the data type of the `reviewer()` element. |
| `format()`, `limit()`, `reviewer()` | Element declarations | **Yes**: when using the annotation, you can write `format = ...`, `limit = ...`, `reviewer = ...`. |

The `@interface` syntax does not automatically turn fields or enums into runtime configuration. The data only takes on meaning when an annotation processor or application code reads and processes it.

## 2. Constants in Annotations: `public static final` by Default

A field declared directly inside `@interface` follows the rules for interface fields: **it is implicitly `public static final`**. You can write these modifiers out in full, though it is not necessary.

```java
@interface Limits {
    int DEFAULT_RETRIES = 3;
    String PREFIX = "api-";

    int retries() default DEFAULT_RETRIES;
    String label() default PREFIX + "default";
}
```

In this example:

- `Limits.DEFAULT_RETRIES` is a **field** accessed through the type name.
- `retries()` is an **annotation element**; when reading the annotation, that element has the default value `3`.
- `PREFIX` is a constant string and `PREFIX + "default"` is a valid constant expression for a `String` element.

Writing `int DEFAULT_RETRIES = 3;` has the same meaning as `public static final int DEFAULT_RETRIES = 3;`. This is something it shares with regular interfaces.

When applying the annotation:

```java
@Limits(retries = Limits.DEFAULT_RETRIES, label = Limits.PREFIX + "user")
class RetryConfig {
}
```

Both values are valid because they are **compile-time constant expressions**. Conversely, `@Limits(DEFAULT_RETRIES = 5)` is invalid: the field `DEFAULT_RETRIES` is not an element named `DEFAULT_RETRIES()`.

### A `final` Field Is Not Necessarily a *Constant Variable*

Java only considers a field a *constant variable* when it is `final`, has a primitive type or `String`, and is initialized with a **constant expression**. Therefore, not every initializer expression of a `public static final` field can be used as an annotation value.

```java
@interface Port {
    int FIXED = 8080;                     // Constant variable
    int DYNAMIC = Integer.parseInt("8080"); // final, but not a constant variable

    int value() default FIXED;            // Valid
    // int other() default DYNAMIC;       // Compilation error
}
```

The lines with error comments here are illustrative; the code without the error lines remains valid syntax. `DYNAMIC` is computed via a method call in its initializer, so it is not a compile-time constant expression, even though the field cannot be reassigned.

Arrays are also reference objects: a field `String[] NAMES = {"a", "b"};` can exist in an interface and prevents reassigning the `NAMES` reference, yet the array elements can still be modified; the field itself **is not** a *constant variable*. For a `String[]` element, write `default {"a", "b"}` directly instead of `default NAMES`.

### Why Not Use `private` or Instance Fields?

```java
@interface WrongFields {
    // private int secret = 1;  // Invalid: interface fields cannot be private
    // int count;               // Invalid: interface fields must have an initializer
}
```

Fields in an annotation cannot be state variables that vary per instance. An annotation is used to describe fixed metadata at the declaration level, not a stateful configuration object.

## 3. Nested Enums: Modeling Finite Values

An enum nested inside `@interface` is useful when an element should only accept a known set of states. Instead of letting users pass arbitrary strings such as `"CSV"`/`"JSON"`, declare an enum:

```java
@interface Serialization {
    enum Format {
        CSV, JSON, XML
    }

    Format value() default Format.JSON;
}
```

Using it from elsewhere:

```java
@Serialization(Serialization.Format.CSV)
class CsvDocument {
}
```

Here `Serialization.Format` is a **member enum type** declared in `Serialization`, while `Format.CSV` is an enum constant. Because the element is named `value`, the shorthand syntax `@Serialization(...)` is allowed. Writing it in full is also valid:

```java
@Serialization(value = Serialization.Format.CSV)
class AnotherCsvDocument {
}
```

A few things to remember:

1. `enum Format` resides inside the annotation but is still **a Java enum type**, accessed via `Serialization.Format`.
2. Member enum types of an interface are implicitly `public static`: no instance of the annotation is needed to access the enum.
3. The `Format value()` element is valid because Java allows an enum as the return type of an annotation element.
4. The value passed to an enum element must be an **enum constant**, such as `Serialization.Format.CSV`. Do not use a string `"CSV"` or an enum variable computed at runtime.
5. You can place the enum at package level or in a separate file if multiple annotations share it; nesting the enum is convenient when it only makes sense within a single annotation.

Note: `Serialization.Format.CSV` is an enum value; `Serialization.Format` is a type name. You cannot assign `Format.class` to an element that requires `Format`, because `Class` and `enum` are two different types.

## 4. Nested Annotation Types: Describing Structured Data

If an element needs multiple related properties, you can create a **nested annotation type** and then use it as the return type of the outer element.

```java
@interface AuditSpec {
    @interface Reviewer {
        String name();
        boolean required() default true;
    }

    Reviewer reviewer();
}
```

Usage:

```java
@AuditSpec(
    reviewer = @AuditSpec.Reviewer(
        name = "qa-team",
        required = true
    )
)
class AuditedService {
}
```

`@AuditSpec.Reviewer(...)` is an **annotation literal used as a value**, not a constructor call `new Reviewer(...)`. The compiler checks that `name` has type `String` and `required` has type `boolean`, just as when using a standalone annotation.

The nested `Reviewer` type is a **member annotation interface**; by the rules for member types in interfaces, it is implicitly `public static`. It can be accessed by its qualified name `AuditSpec.Reviewer`.

If you need a collection of multiple reviewers, declare `Reviewer[] reviewers();` and use a list of annotation literals inside `{ ... }`. Java permits elements of an annotation type and **one-dimensional** arrays of annotations.

## 5. Complete Example: Constants + Enum + Nested Annotation

The following example is written as **a complete Java 17+ program**. It declares an annotation marking how data is exported, containing constants, a format enum, and an annotation type describing a reviewer.

Create the file **`AnnotationMemberKindsDemo.java`** with the following content:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ExportRule {
    int DEFAULT_BATCH_SIZE = 25;
    String DEFAULT_TEAM = "platform";

    enum Format {
        CSV, JSON
    }

    @Retention(RetentionPolicy.RUNTIME)
    @interface Reviewer {
        String value();
        boolean required() default true;
    }

    Format format() default Format.JSON;
    int batchSize() default DEFAULT_BATCH_SIZE;
    Reviewer reviewer() default @Reviewer(DEFAULT_TEAM);
}

@ExportRule(
    format = ExportRule.Format.CSV,
    reviewer = @ExportRule.Reviewer("billing")
)
class PaymentExport {
}

public class AnnotationMemberKindsDemo {
    public static void main(String[] args) {
        ExportRule rule = PaymentExport.class.getAnnotation(ExportRule.class);

        System.out.println("format=" + rule.format());
        System.out.println("batchSize=" + rule.batchSize());
        System.out.println("reviewer=" + rule.reviewer().value());
        System.out.println("required=" + rule.reviewer().required());
        System.out.println("constant=" + ExportRule.DEFAULT_BATCH_SIZE);
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 AnnotationMemberKindsDemo.java
java AnnotationMemberKindsDemo
```

`stdout` output:

```text
format=CSV
batchSize=25
reviewer=billing
required=true
constant=25
```

Where does each value come from?

- `format=CSV`: the usage site specifies `format = ExportRule.Format.CSV`, **overriding** the default `Format.JSON`.
- `batchSize=25`: `batchSize` is not passed, so Java uses `DEFAULT_BATCH_SIZE` as the element's default value.
- `reviewer=billing`: the `reviewer()` element contains a nested `@ExportRule.Reviewer("billing")` annotation. Its `value()` returns `"billing"`.
- `required=true`: inside `Reviewer`, the `required()` element has `default true`; no other value is passed from outside.
- `constant=25`: `ExportRule.DEFAULT_BATCH_SIZE` reads the **constant field**, unlike `rule.batchSize()`, which reads the value of the **annotation element**.

`@Retention(RUNTIME)` on the outer annotation allows the program to retrieve it via reflection. Declaring nested enums or constants inside `@interface` does not automatically give an annotation `RUNTIME` retention; each annotation type has its own retention and must specify it when needed.

This program illustrates metadata; Java does not perform CSV exporting or approval by `"billing"`. To get that behavior, the program must read `ExportRule` itself and handle it accordingly.

## 6. Other Member Classes and Interfaces That Can Appear Inside `@interface`

Besides nested enums and annotations, Java syntax also permits **member classes and interfaces** directly inside `@interface`. Standalone illustrative example:

```java
@interface DocumentHint {
    String NAME = "document";

    class TextUtil {
        static String trim(String input) {
            return input.trim();
        }
    }

    interface Formatter {
        String format(String value);
    }

    Class<? extends Formatter> formatter();
}
```

`DocumentHint.TextUtil` and `DocumentHint.Formatter` are **member types**, implicitly `public static` because they are declared inside an interface. To call `DocumentHint.TextUtil.trim(" x ")` from outside the package, the `trim` method would need to be declared `public`; in this example it has default package access. The syntax for declaring a member type is completely different from the syntax for declaring an annotation element.

The final line `Class<? extends Formatter> formatter();` is **valid**: the element's type is `Class` with a generic bound, not `Formatter` itself. Only the following types are allowed as the return type of an annotation element: primitive types, `String`, `Class` (including `Class<?...>`), enums, annotations, and one-dimensional arrays of those types.

Therefore, the following declarations are **invalid** if placed directly as annotation elements:

```java
// Formatter formatter(); // Invalid: Formatter is a regular interface
// TextUtil helper();      // Invalid: TextUtil is a regular class
// java.util.List<String> names(); // Invalid: List is not a valid element type
```

Meanwhile, `String[] names() default {};` is valid, as long as you place it inside an `@interface` type.

### Access Rules

According to the Java Language Specification, member classes and member interfaces declared inside an interface are implicitly `public static`. Therefore:

- You can use `OuterAnnotation.NestedType` from elsewhere if the remaining access constraints allow it.
- You cannot declare `private class Helper` or `protected interface Formatter` directly at the member level of an annotation/interface.
- Enums and nested annotations also belong to the member type category; they are not object instances attached to a specific annotation usage.
- A nested annotation type can be used as **an element's type**; an arbitrary nested interface/class cannot, unless you use `Class<?>` to store its **class literal**.

You do not need to create an object of type `OuterAnnotation` to access these members. When using constants or enums from elsewhere, it is best to write their qualified names (`ExportRule.Format.JSON`, `ExportRule.DEFAULT_BATCH_SIZE`) to avoid confusion with identically named items in other code.

## 7. Why Is `@interface` Not a Class for Holding Logic?

Methods declared directly inside `@interface` **must be annotation elements**. They cannot have parameters, a method body, type parameters, or a `throws` clause; you cannot declare `static`, `private`, or `default` methods as in a regular interface.

```java
@interface ApiFlag {
    int priority() default 1;

    // int calculate(int input);  // Invalid: elements cannot take parameters
    // static int twice(int n) { return n * 2; } // Invalid at the @interface level
}
```

The `default` keyword in `int priority() default 1;` specifies the **default element value**, not an interface `default` method with a body.

If supporting logic is truly needed, place it in a member class, an external class, or a processor instead of turning elements into computational methods. Declaring `class TextUtil` inside `@interface` is valid, though for larger applications you should consider separating helpers into standalone classes to avoid mixing processing utilities with metadata definitions.

In addition, an annotation type does not freely support generic parameters such as `@interface Box<T>` and cannot specify `extends SomeInterface`; it has its own rules because every annotation type relates to `java.lang.annotation.Annotation`.

## 8. Easy-to-Confuse Invalid Cases

| Code or Assumption | Conclusion |
| --- | --- |
| `@ExportRule(DEFAULT_BATCH_SIZE = 50)` | **Invalid**: a constant field name is not an element name. The correct form is `batchSize = 50`. |
| `ExportRule.Format.CSV` is a `String` | **False**: it is an enum constant of type `ExportRule.Format`. |
| `format = "CSV"` for an element of type `Format` | **Type mismatch**: use `format = ExportRule.Format.CSV`. |
| `reviewer = new ExportRule.Reviewer(...)` | **Invalid**: an annotation literal uses the syntax `@ExportRule.Reviewer(...)` and cannot be instantiated with `new`. |
| `int limit() default Math.max(1, 2);` | **Invalid**: a primitive value for an element or default requires a compile-time constant expression. |
| `String[] tags() default TAGS;` where `TAGS` is a `String[]` field | **Invalid**: do not use an array reference as an annotation element value; use `default {"a", "b"}`. |
| `Format format() default "JSON";` | **Type mismatch**: the default must be an enum constant such as `Format.JSON`. |
| `Formatter formatter();` where `Formatter` is a regular interface | **Invalid element type**: you can use `Class<? extends Formatter> formatter();` if you want to store a class literal. |
| `private static final int LIMIT = 3;` inside `@interface` | **Invalid modifier**: interface fields are always `public static final`; `private` is not allowed. |
| Applying `@ExportRule` makes Java automatically export a CSV file | **False**: annotations only provide metadata; separate code is required to execute the business logic. |

A practical checklist rule when designing an annotation is to identify which category each declaration belongs to: **constant field**, **member type**, or **element**. Then verify each element's type against the set of types Java allows, and check whether the values used where the annotation is declared are valid at compile time.

## 9. Quick Self-Check Exercise

Given the definition:

```java
@interface Job {
    int DEFAULT_PRIORITY = 2;
    enum Mode { SYNC, ASYNC }

    Mode mode() default Mode.SYNC;
    int priority() default DEFAULT_PRIORITY;
}
```

Consider the following expressions:

1. `@Job` — **Valid**: both elements have defaults.
2. `@Job(mode = Job.Mode.ASYNC)` — **Valid**: uses an enum constant.
3. `@Job(priority = Job.DEFAULT_PRIORITY + 1)` — **Valid**: addition on a constant variable produces the constant expression `3`.
4. `@Job(mode = "ASYNC")` — **Invalid**: a string is not an enum.
5. `@Job(DEFAULT_PRIORITY = 10)` — **Invalid**: `DEFAULT_PRIORITY` is a field, not an element.

This exercise shows that **constants provide compile-time expressions**, **enums constrain the value domain**, **nested annotation types represent structured metadata**, and **elements** are the only part that accepts values via `@Job(...)` or `@ExportRule(...)`.

Authoritative reference for the rules above: [Java Language Specification 21 – §9.3 Field Declarations, §9.5 Member Class and Interface Declarations, §9.6 Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html). These are rules of the Java language itself, independent of Spring or any specific annotation-processing library.
