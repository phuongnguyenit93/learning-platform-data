# `@Min`, `@Max`, `@DecimalMin`, and `@DecimalMax` in Bean Validation

## 1. Goal and Context

These four annotations belong to the **built-in constraints** group of Jakarta Bean Validation, used to check whether a **numeric value falls within a minimum or maximum limit**. They frequently appear in Spring MVC models, DTOs, input forms, and business data:

- Product quantity must be at least 1: `@Min(1)`.
- Retry count must not exceed 5: `@Max(5)`.
- Unit price must be **greater than** `0.00` (excluding 0): `@DecimalMin(value = "0.00", inclusive = false)`.
- Discount rate must be **less than** `1.00` (excluding 100%): `@DecimalMax(value = "1.00", inclusive = false)`.

What matters is not just memorizing annotation names: you must choose the right **threshold type** (`long` or decimal numeric string), understand **whether the boundary is inclusive**, handle `null`, pick appropriate numeric types, and know at which stage Spring invokes Bean Validation after data binding.

After this lesson, you will be able to:
1. Fully distinguish the four annotations by comparison operator, `value` type, `inclusive`, and supported Java types.
2. Write interval constraints `[min, max]`, `(min, max)`, `[min, max)`, or `(min, max]` and test boundary points accurately.
3. Combine `@NotNull`, `@Digits`, conversion, and validation when needed, instead of expecting one annotation to do everything.
4. Run a Java 17+ program using Jakarta Validation with Hibernate Validator and compare `ConstraintViolation` with Spring's `FieldError`.
5. Avoid floating-point precision bugs, type mismatches, mixing `javax.validation` and `jakarta.validation`, or misunderstanding `BindingResult` in Spring.

## 2. Direct Comparison of the Four Annotations

| Annotation | Default Condition | `value` Attribute Type | Has `inclusive`? | Example |
| --- | --- | --- | --- | --- |
| `@Min` | `x >= value` | `long` | No; always inclusive | `@Min(1)` |
| `@Max` | `x <= value` | `long` | No; always inclusive | `@Max(100)` |
| `@DecimalMin` | `x >= value` | `String` in `BigDecimal` numeric format | Yes; defaults to `true` | `@DecimalMin("0.01")` |
| `@DecimalMax` | `x <= value` | `String` in `BigDecimal` numeric format | Yes; defaults to `true` | `@DecimalMax("999.99")` |

All four reside in the `jakarta.validation.constraints` package when using Jakarta Validation (standard with Spring Framework 6+). They are **value comparison constraints**, not annotations exclusively for `int`, nor string-to-number converters.

### 2.1. `@Min`: Value Not Less Than Threshold

```java
@Min(value = 1, message = "Quantity must be at least {value}")
private Integer quantity;
```

- `quantity = 1` → **valid**.
- `quantity = 0` → **violation**.
- `quantity = 100` → valid under `@Min` alone.
- `quantity = null` → **valid under `@Min` alone**; add `@NotNull` if input is required.

`@Min(1)` is shorthand for `@Min(value = 1)`. The `value` attribute has type `long`, so it can express negative thresholds and thresholds within `long` range, but **you cannot write** `@Min(0.1)` to set a decimal threshold.

### 2.2. `@Max`: Value Not Greater Than Threshold

```java
@Max(value = 100, message = "Value must not exceed {value}")
private Long count;
```

- `count = 100L` → valid.
- `count = 101L` → violation.
- `count = -1L` → valid under `@Max` alone; if negative numbers are disallowed, add a minimum constraint.
- `count = null` → valid under `@Max` alone.

`@Max(100)` does **not** have an `inclusive = false` variant; to directly express `< 100`, you can use `@DecimalMax(value = "100", inclusive = false)` on a supported type.

### 2.3. `@DecimalMin`: Decimal Thresholds and Open Boundaries

```java
@DecimalMin(value = "0.00", inclusive = false)
private BigDecimal price;
```

- `price = 0.00` → violation because `x > 0.00` is required.
- `price = 0.01` → valid.
- `price = -0.01` → violation.
- `price = null` → valid under `@DecimalMin` alone.

If `inclusive = false` is omitted, it defaults to `true`, making the condition `x >= 0.00`. Unlike `@Min`, `@DecimalMin`'s `value` is a **string representing a number**, such as `"0.10"`, `"1.2345"`, `"-0.005"`, or `"100000000000000000000"`.

The syntax inside the quotes must follow the format understood by `BigDecimal`; inside the annotation write `"0.01"` with a decimal dot, **not** `"0,01"` according to user locale.

### 2.4. `@DecimalMax`: Decimal Thresholds and Open Boundaries

```java
@DecimalMax(value = "1.00", inclusive = false)
private BigDecimal discountRate;
```

- `discountRate = 0.99` → valid.
- `discountRate = 1.00` → violation because `x < 1.00` is required.
- `discountRate = 1.01` → violation.
- `discountRate = null` → valid under `@DecimalMax` alone.

If `inclusive` is omitted, the maximum bound is included (`x <= value`). `@DecimalMax` uses the same `String`-based threshold representation as `@DecimalMin`.

## 3. Closed and Open Boundaries: Choosing the Right Annotation

For `BigDecimal amount`, intervals are expressed as follows:

| Desired Interval | Annotations |
| --- | --- |
| `[0, 100]` | `@DecimalMin("0")` and `@DecimalMax("100")` |
| `(0, 100)` | `@DecimalMin(value = "0", inclusive = false)` and `@DecimalMax(value = "100", inclusive = false)` |
| `[0, 100)` | `@DecimalMin("0")` and `@DecimalMax(value = "100", inclusive = false)` |
| `(0, 100]` | `@DecimalMin(value = "0", inclusive = false)` and `@DecimalMax("100")` |
| `1 <= x <= 10` with integer bounds | `@Min(1)` and `@Max(10)` |

A field can carry both minimum and maximum constraints simultaneously:

```java
@DecimalMin(value = "0.00", inclusive = false)
@DecimalMax(value = "1.00", inclusive = true)
private BigDecimal share;
```

In this example, `0.00` is invalid, `0.01` is valid, `1.00` is valid, and `1.01` is invalid. Constraints act as **simultaneous** conditions: data is only valid if all applicable constraints are satisfied.

**Do not infer boundaries from display formatting.** For instance, a form displaying `1.00` does not mean the value was rounded from `0.999`; the validator checks the **actual Java value after conversion**, unless the application explicitly runs a normalization/rounding step beforehand.

### 3.1. Two Boundary Points That Must Be Tested

If the requirement is `price > 0.10`:

```text
0.09  -> invalid
0.10  -> invalid because inclusive=false
0.11  -> valid
```

If the requirement is `stock <= 20`:

```text
19 -> valid
20 -> valid because @Max has a closed boundary
21 -> invalid
```

Test **right on the threshold**, **below the threshold**, and **above the threshold**. Testing only a value far outside the limit can miss a misconfigured `inclusive` flag.

## 4. Data Types Guaranteed to Be Supported by Jakarta Validation

According to Jakarta Bean Validation 3.0, the guaranteed standard type set is:

| Type to Validate | `@Min`/`@Max` | `@DecimalMin`/`@DecimalMax` | Notes |
| --- | --- | --- | --- |
| `byte`, `short`, `int`, `long`, and wrappers | Yes | Yes | When using wrappers, `null` is valid under this constraint alone |
| `BigInteger` | Yes | Yes | Useful for integers larger than `long` |
| `BigDecimal` | Yes | Yes | Compared by **numeric value**, not string/scale |
| `CharSequence` (`String`, ...) | **Not guaranteed by spec** | Yes | String value must represent a valid number per provider |
| `float`, `double`, and wrappers | **Not guaranteed by spec** | **Not guaranteed by spec** | Binary precision error; providers may offer approximate extensions |
| `Boolean`, `LocalDate`, `Duration`, arbitrary objects | No | No | Use constraints appropriate for those types |

**Important note:** Hibernate Validator may support **additional** types (for example `@Min` on numeric strings or certain `Number` subclasses). That is a provider extension, **not part of Jakarta Validation's portable contract**. If you may switch providers or need portability, stick to the standard types in the table.

`@Min(2)` on `BigDecimal("1.99")` still fails; `@Min` does not round numbers before comparing against `2`. Only the **threshold** is `long`. If you need a `1.99` boundary, use `@DecimalMin("1.99")`.

### 4.1. Why Use `BigDecimal` for Money and Exact Ratios?

`double`/`float` numbers cannot accurately represent many decimal fractions in binary. For limits like `0.1`, `1.005`, or `9999.99`, using `BigDecimal` avoids precision depending on floating-point representation. Construct from a string:

```java
BigDecimal price = new BigDecimal("0.10");
```

Avoid constructing directly from `double`:

```java
BigDecimal imprecise = new BigDecimal(0.1);
```

The second line can carry the imprecision of the `double` literal. If you already have a `double` and must convert it, `BigDecimal.valueOf(...)` is generally better than the `double` constructor, though monetary input should be parsed directly into `BigDecimal`.

`BigDecimal("1.0")` and `BigDecimal("1.00")` have the **same numeric value** (`compareTo() == 0`) but differ in `equals()` due to scale. Boundary constraints check arithmetic comparison; they **do not guarantee** decimal digit count, rounding mode, or canonical representation. To restrict digit counts, also use `@Digits(integer = ..., fraction = ...)` and appropriate business rules.

### 4.2. When Validating `String` with `@DecimalMin`

`@DecimalMin("1.5")` supports `CharSequence` per spec, but clearly it expects a **string representing a number**. It is not a locale-aware parser or general input normalizer for forms:

```java
@DecimalMin("1.5")
private String numericText;
```

If a user submits `"1,5"` under a comma-decimal locale, do not assume Jakarta Validation will interpret it as 1.5. In Spring MVC, it is usually better to bind a `BigDecimal` field using a locale-aware converter/formatter, and then run `@DecimalMin` **on the converted value**.

For non-numeric strings like `"hello"`, do not treat Bean Validation results as a complete normalization handler. Parsing/formatting rules, error text, and validation mechanisms must be defined separately, especially with `@ModelAttribute` or JSON APIs.

## 5. `null`, Whitespace, Primitives, and Error Groups

All four boundary constraints treat `null` as **valid**. This is intentional: numeric constraints are only responsible for comparing **when a value exists**. If the user must provide a value:

```java
@NotNull(message = "Value is required")
@DecimalMin("0.00")
private BigDecimal amount;
```

- `null` → violates `@NotNull`, does not violate `@DecimalMin`.
- `BigDecimal.ZERO` → valid under `@DecimalMin("0.00")` because `inclusive = true` by default.
- `new BigDecimal("-0.01")` → violates `@DecimalMin`.
- `""` and `"   "` are **not** `null` on all binding paths; the application must define its conversion/trim/blank policy.

For primitive `int`/`long`, the Java value cannot be null. If a form omits the field, it may remain at **default 0** on a new object; `@Min(1)` will catch 0, though that is not proof the user entered 0. If you need to distinguish *omitted* from *entered 0*, use `Integer`/`Long` and `@NotNull`.

Conversely, sending `"abc"` to an `Integer` field can trigger a `typeMismatch` conversion error in Spring **before** the validator receives a valid Integer. Therefore, handle both binding errors and Bean Validation errors.

### 5.1. Combinable Range Constraints

```java
@NotNull
@Min(1)
@Max(50)
private Integer retryCount;
```

This expresses **required value in `[1, 50]`**. If the field is optional yet must be within that range when present, omit `@NotNull`.

Adding `@Positive`/`@PositiveOrZero` is another option when you only need positivity/non-negativity. `@DecimalMin(value="0", inclusive=false)` expresses `x > 0`, though for code readability `@Positive` can be clearer. Pick a consistent contract and avoid unnecessary duplicate constraints.

## 6. Complete Java 17+ Program: Checking All Four Constraints and the Spring Adapter

The example uses **Jakarta Validation 3.0 / Hibernate Validator 8.0.2.Final** and **Spring Framework 6.2.14**, with no Spring Boot or web server needed. The program constructs values **right at or beyond boundaries** to show:
- `@Min(2)` and `@Max(20)` are always inclusive.
- `@DecimalMin("0.10", inclusive = false)` and `@DecimalMax("100.00", inclusive = false)` exclude the endpoint.
- `@NotNull` combines with `@DecimalMin` to catch missing values.
- Jakarta `ConstraintViolation` includes property path, invalid value, constraint name, and message.
- `SpringValidatorAdapter` translates those same violations into `FieldError` entries in a `BindingResult`.

### 6.1. Maven POM

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>numeric-bounds-validation</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Standalone Java Code

Create `src/main/java/example/NumericBoundsDemo.java`:

```java
package example;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.validation.DirectFieldBindingResult;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class NumericBoundsDemo {

    public static final class Limits {
        @Min(value = 2, message = "quantity must be >= {value}")
        Integer quantity = 1;

        @Max(value = 20, message = "stock must be <= {value}")
        Integer stock = 21;

        @DecimalMin(
                value = "0.10", inclusive = false,
                message = "price must be > {value}")
        BigDecimal price = new BigDecimal("0.10");

        @DecimalMax(
                value = "100.00", inclusive = false,
                message = "discount must be < {value}")
        BigDecimal discount = new BigDecimal("100.00");

        @NotNull(message = "tax is required")
        @DecimalMin(
                value = "0.00", message = "tax must be >= {value}")
        BigDecimal tax = null;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            Limits invalid = new Limits();

            List<ConstraintViolation<Limits>> violations =
                    new ArrayList<>(validator.validate(invalid));

            // Result set does not guarantee order.
            violations.sort(Comparator.comparing(
                    v -> v.getPropertyPath().toString()));

            require(violations.size() == 5,
                    "Expected 5 constraint violations");

            for (ConstraintViolation<Limits> violation : violations) {
                String annotation = violation.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .getSimpleName();
                System.out.println(
                        violation.getPropertyPath()
                        + " | value=" + violation.getInvalidValue()
                        + " | annotation=" + annotation
                        + " | template=" + violation.getMessageTemplate()
                        + " | message=" + violation.getMessage());
            }
            System.out.println("violationCount=" + violations.size());

            // Compare the same Validator with Spring's BindingResult.
            DirectFieldBindingResult result =
                    new DirectFieldBindingResult(invalid, "limits");
            new SpringValidatorAdapter(validator).validate(invalid, result);
            require(result.getFieldErrorCount() == 5,
                    "Expected 5 Spring field errors");
            System.out.println(
                    "springFieldErrors=" + result.getFieldErrorCount());

            // Closed boundaries are accepted; open boundaries must cross the threshold.
            Limits valid = new Limits();
            valid.quantity = 2;
            valid.stock = 20;
            valid.price = new BigDecimal("0.11");
            valid.discount = new BigDecimal("99.99");
            valid.tax = new BigDecimal("0.00");

            require(validator.validate(valid).isEmpty(),
                    "Expected valid numeric boundaries");
            System.out.println("validBoundaries=true");

            // The four numeric constraints allow null; @NotNull does not.
            Limits missing = new Limits();
            missing.quantity = null;
            missing.stock = null;
            missing.price = null;
            missing.discount = null;
            missing.tax = null;

            Set<ConstraintViolation<Limits>> missingErrors =
                    validator.validate(missing);
            require(missingErrors.size() == 1,
                    "Expected only tax's @NotNull violation");
            require(missingErrors.iterator().next()
                            .getPropertyPath().toString().equals("tax"),
                    "Expected tax field violation");
            System.out.println("nullOnlyErrors=" + missingErrors.size());

            System.out.println("CHECKS: PASS");
        }
    }
}
```

**Why does the example use `DirectFieldBindingResult`?** The example model intentionally declares fields and initializes them directly without getters/setters; `DirectFieldBindingResult` reads fields directly. For standard MVC beans with JavaBean getters/setters, `BeanPropertyBindingResult` or Spring MVC's binder is more common.

### 6.3. How to Run and Expected Output

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.NumericBoundsDemo
```

Program stdout after ignoring auxiliary library logs, if any:

```text
discount | value=100.00 | annotation=DecimalMax | template=discount must be < {value} | message=discount must be < 100.00
price | value=0.10 | annotation=DecimalMin | template=price must be > {value} | message=price must be > 0.10
quantity | value=1 | annotation=Min | template=quantity must be >= {value} | message=quantity must be >= 2
stock | value=21 | annotation=Max | template=stock must be <= {value} | message=stock must be <= 20
tax | value=null | annotation=NotNull | template=tax is required | message=tax is required
violationCount=5
springFieldErrors=5
validBoundaries=true
nullOnlyErrors=1
CHECKS: PASS
```

Interpretation:
1. `quantity = 1` fails because `< 2`; `stock = 21` fails because `> 20`.
2. `price = 0.10` and `discount = 100.00` lie **right on the boundary** yet fail because `inclusive = false`.
3. `tax = null` only violates `@NotNull`; `@DecimalMin("0.00")` does not catch null on its own.
4. `getMessageTemplate()` keeps `{value}`, while `getMessage()` interpolates it to `2`, `20`, `0.10`, and `100.00`.
5. `SpringValidatorAdapter` turns the five violations into five field errors in `BindingResult`.
6. The `valid` object holds valid closed-boundary points, while values at open boundaries are placed **strictly past the threshold**.
7. The `missing` object confirms exactly **one** required error; the other four numeric constraints accept null.

Results are sorted by property path for easy comparison; Jakarta Validation returns `Set<ConstraintViolation<?>>`, so **order is not guaranteed** without sorting.

### 6.4. What Happens with Large Values?

Because `@Min/@Max`'s `value` parameter is `long`, you cannot write `@Min` with a threshold larger than `Long.MAX_VALUE`. Even if the field is `BigInteger`, `@Min` is still limited **by the declared threshold**. `@DecimalMin(value = "100000000000000000000")` represents large thresholds as strings, suitable when the field is `BigInteger` or `BigDecimal` and supported by the provider per Jakarta Validation.

## 7. Spring MVC Integration and Data Binding Order

In Spring MVC, the typical pipeline:

```text
HTTP form / query parameter
         |
         v
Convert string -> Integer, Long, BigDecimal (ConversionService/Formatter)
         |
         v
Bean with bound data
         |
         v
@Valid / @Validated invokes Jakarta Bean Validation
         |
         v
BindingResult holds conversion or constraint errors
```

Example model (illustrative snippet with JavaBean getters/setters for Spring binding):

```java
public class ProductForm {
    @NotNull
    @Min(1)
    @Max(100)
    private Integer quantity;

    @NotNull
    @DecimalMin(value = "0.00", inclusive = false)
    @DecimalMax("999999.99")
    private BigDecimal unitPrice;

    // Getters/setters for quantity and unitPrice.
}
```

Key imports use `jakarta.validation.constraints.*` and `java.math.BigDecimal`. This is a model excerpt, not a standalone runnable program.

A controller receiving the form (illustrative snippet, requires Spring Web MVC):

```java
@PostMapping("/products")
String submit(@Valid @ModelAttribute("product") ProductForm product,
              BindingResult errors) {
    if (errors.hasErrors()) {
        return "products/form";
    }
    return "products/success";
}
```

Main imports: `jakarta.validation.Valid`, `org.springframework.web.bind.annotation.PostMapping`, `org.springframework.web.bind.annotation.ModelAttribute`, and `org.springframework.validation.BindingResult`.

`BindingResult` must appear **immediately after** the `@ModelAttribute` argument whose errors are handled. When a Bean Validation provider is on the classpath and MVC is properly configured, `@Valid` triggers validation for the bound object. With manual `DataBinder`, set the validator (`setValidator`/`addValidators`) and call `binder.validate()`; calling `bind(...)` alone does not run Bean Validation.

### 7.1. Distinguishing Type Mismatch Errors from Constraint Violations

Sending input `"abc"` to `quantity: Integer` is not a number. Spring can create a `FieldError` with a `typeMismatch`-style code because it cannot convert the string into an Integer. In this case, **there is no Integer value yet to compare against `@Min(1)`**.

Input `"0"` converts to `Integer 0`, then fails `@Min(1)`, producing a constraint error with a code based on `Min`. For sensible error reporting, separate:
- **Syntax/conversion error:** "Please enter a valid integer".
- **Boundary error:** "Quantity must be at least 1".

For `BigDecimal` input `"1,50"` in Vietnamese locale, success or failure depends on the configured formatter/conversion. The `@DecimalMin("1.00")` annotation compares the post-binding value; the annotation itself **does not** decide how commas and dots are parsed.

### 7.2. JSON `@RequestBody` Takes a Different Path

If the controller accepts `@Valid @RequestBody ProductForm`, JSON is deserialized by an HTTP message converter (usually Jackson) before validation, with its own JSON rules and configuration. A numeric JSON field `1.50` and a JSON string `"1,50"` are not equivalent. Form formatters are not necessarily used for JSON; test the parser, exception handler, and validation of JSON APIs separately.

## 8. Reading `ConstraintViolation` and Error Messages

Each Jakarta Validation violation provides:

```java
violation.getPropertyPath();
violation.getInvalidValue();
violation.getMessage();
violation.getMessageTemplate();
violation.getConstraintDescriptor();
```

With annotation:

```java
@DecimalMin(
    value = "0.10",
    inclusive = false,
    message = "Price must be greater than {value}"
)
private BigDecimal price;
```

When `price = new BigDecimal("0.10")`, `getMessageTemplate()` retains `"Price must be greater than {value}"`, while `getMessage()` interpolates to `"Price must be greater than 0.10"`. When using the default template, the provider looks up the message in bundles (typically the default English message or configured translations).

`getPropertyPath()` is a structured path; in nested forms it may look like `product.price`. `getInvalidValue()` returns the validated object, `BigDecimal` in this example. Do not return this raw value over an API or log it if the data could be sensitive.

Attributes `value`, `message`, `groups`, and `payload` are common constraint attributes. `inclusive` **exists only on** the two decimal annotations in this group. You can set a literal message or a resource bundle key (`"{product.price.min}"`) for internationalization.

In Spring, `FieldError.getField()`, `getRejectedValue()`, and `getDefaultMessage()` help display errors; error codes/arguments integrate with `MessageSource`. They do not map 1:1 to every `ConstraintViolation` property: `FieldError` also holds conversion errors, and `getCodes()` is not `getMessageTemplate()`.

## 9. Boundary Testing Matrix

| Test Case | Value | Annotation | Expectation |
| --- | --- | --- | --- |
| Exactly at min | `1` | `@Min(1)` | Pass |
| Below min | `0` | `@Min(1)` | Violation |
| Exactly at max | `5` | `@Max(5)` | Pass |
| Above max | `6` | `@Max(5)` | Violation |
| Closed decimal min | `0.10` | `@DecimalMin("0.10")` | Pass |
| Open decimal min | `0.10` | `@DecimalMin(value="0.10", inclusive=false)` | Violation |
| Open decimal min | `0.11` | Same as above | Pass |
| Closed decimal max | `99.99` | `@DecimalMax("99.99")` | Pass |
| Open decimal max | `99.99` | `@DecimalMax(value="99.99", inclusive=false)` | Violation |
| Open decimal max | `99.98` | Same as above | Pass |
| Different scale comparison | `1.00` vs threshold `"1.0"` | Inclusive decimal min/max | Based on numeric value; scale difference does not alter result |
| Integer bound on decimal | `1.99` | `@Min(2)` | Violation; no rounding |
| Null with range | `null` | `@Min(1)`, `@DecimalMax("10")` | Pass under these two constraints alone |
| Required null | `null` | `@NotNull @Min(1)` | `@NotNull` violation |
| `float`/`double` types | `double` with `@DecimalMin` | Portable Jakarta Validation | Not guaranteed by spec; avoid assumptions |
| Wrong-type string | `"abc"` → `Integer` | `@Min(1)` on target | Conversion error before validation |
| Locale-formatted decimal | `"1,20"` → `BigDecimal` | `@DecimalMin("1.00")` | Depends on formatter/parser, then compared |
| Negative value | `-1` | `@Max(10)` | Pass under `@Max` alone |
| Very large value | `BigInteger` larger than `long` | `@DecimalMin` with large string | Compared by value when provider/type is right |
| Unsupported type | `LocalDate` with `@Min` | Wrong constraint type | May throw `UnexpectedTypeException` on validation |

In automated tests, assert on annotation type and property path:

```java
boolean hasMinViolation = validator.validate(form).stream()
    .anyMatch(v ->
        v.getPropertyPath().toString().equals("quantity")
        && v.getConstraintDescriptor().getAnnotation()
                .annotationType() == Min.class);
```

This is an **illustrative Java snippet** inside a test that has `validator`, `form`, and `import jakarta.validation.constraints.Min`. Do not rely on `Set` iteration order or verbatim translated messages to identify a violation.

### 9.1. Testing `inclusive = false` with the Right Values

With threshold `"0.10"` and `inclusive=false`, if you only test `0.00` (fail) and `1.00` (pass), you have not proven the actual condition is `>` rather than `>=`. You must also test the exact boundary value `"0.10"` and verify it **fails**.

Similarly, with `@DecimalMax(value="100.00", inclusive=false)`, `100.00` must fail. This is where configuration bugs easily slip through if tests only cover out-of-range values.

## 10. Common Mistakes and Fixes

**1. Using `@Min(0.01)` or `@Max(99.99)`.** Their `value` attribute is `long` and does not accept fractional literals. Use `@DecimalMin("0.01")` or `@DecimalMax("99.99")`.

**2. Assuming `@DecimalMin("0.00")` means `x > 0`.** By default `inclusive=true`: `0.00` is still valid. If strict positivity is required, use `inclusive=false` or `@Positive` per contract.

**3. Forgetting `@NotNull`.** All four annotations allow `null`; to make input required, add `@NotNull`. With non-null primitives, distinguish missing input from default zero when designing forms.

**4. Using `double` for money and expecting exact validation.** The Jakarta spec does not guarantee support on float/double; even providers with extensions still suffer from rounding issues. Prefer `BigDecimal` with string thresholds.

**5. Using `@Min/@Max` on String and assuming portability.** The spec only guarantees `CharSequence` for the two decimal annotations. Hibernate Validator has some extensions, but switching providers can cause `UnexpectedTypeException`.

**6. Assuming `@DecimalMin` checks decimal digit count.** It only compares against a threshold. To allow at most 2 decimal places, look at `@Digits(integer=..., fraction=2)` or domain logic.

**7. Confusing `@Max` with collection element count or string length.** `@Max` checks numeric values, not size. For `List`, `String`, and `Map`, use `@Size(max = ...)` to limit size/length.

**8. Numeric input string errors not displaying properly.** `@Min` does not fix `typeMismatch`; configure formatters, binding, `BindingResult`, and separate conversion error messages.

**9. Mixing `javax.validation.constraints` with `jakarta.validation.constraints`.** Spring Framework 6+ uses Jakarta Validation (`jakarta.*`). Spring Framework 5.x typically uses `javax.validation.*`. Do not mix APIs/providers from the two namespaces on the same validation path.

**10. Assuming violations always produce a single error.** If multiple constraints are placed on one field, the same input can violate several conditions; the result is an unordered Set. Choose UI error priority intentionally rather than relying on iteration order.

**11. Attaching annotations to unsupported types.** Jakarta Validation can throw `UnexpectedTypeException`, which is a configuration/constraint mapping error, not "user data out of bounds". Verify Java types before deployment.

**12. Validating only on the frontend.** HTML `min`, `max`, and JS input validation help UX but can be bypassed by direct HTTP requests. The server needs validation per the API/domain contract, and must still enforce correctness when writing data.

## 11. Workflow for Applying to a New Field

1. **Determine the numeric domain:** `Integer`, `Long`, `BigInteger`, `BigDecimal`, or numeric string; avoid float/double when exact decimal boundaries are required.
2. **Define both bounds:** minimum/maximum thresholds and whether each bound is closed or open; do not pick annotations before clarifying requirements.
3. **Select constraints:** `@Min/@Max` for integer thresholds with closed bounds; `@DecimalMin/@DecimalMax` for fractional thresholds, open bounds, or thresholds exceeding `long`.
4. **Handle nullability:** if a value is required, add `@NotNull`, and ensure the binder can distinguish missing from 0 when needed.
5. **Define conversion:** form/JSON input according to locale and chosen numeric type; separate conversion errors from range errors.
6. **Set up server validation:** `@Valid`/`@Validated` on the right request path or manually call `Validator`/`DataBinder.validate()`.
7. **Write boundary tests:** exact threshold, just below/above threshold, null, negative numbers, overflow, scale, invalid input, and typed errors.
8. **Verify messages:** interpolated `getMessage()`, accurate message code/locale; do not leak sensitive raw values.
9. **Keep domain rules consistent:** the same valid range must be enforced across business logic, data imports, APIs, and other write paths.

## References

- Jakarta Bean Validation 3.0 — built-in constraints specification: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation 3.0 — `@Min`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/Min.html
- Jakarta Validation 3.0 — `@Max`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/Max.html
- Jakarta Validation 3.0 — `@DecimalMin`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/DecimalMin.html
- Jakarta Validation 3.0 — `@DecimalMax`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/DecimalMax.html
- Spring Framework 6.2 — Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — `DirectFieldBindingResult`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DirectFieldBindingResult.html
- Hibernate Validator 8.0 — Reference Guide: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
