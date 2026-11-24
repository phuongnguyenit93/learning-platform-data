# @Positive, @PositiveOrZero, @Negative, and @NegativeOrZero in Bean Validation

## 1. Goals and Use Cases

In Spring systems, a value of type `Integer`, `Long`, or `BigDecimal` can still be invalid in terms of business meaning: order quantity must be greater than 0, inventory count cannot be negative, downward adjustment amount must be less than 0, or balance change may be negative or zero. Jakarta Bean Validation provides four built-in annotations that express those exact four value domains.

Examples:
- `quantity = 3`: valid when quantity must be greater than 0.
- `quantity = 0`: invalid with `@Positive`, yet valid with `@PositiveOrZero`.
- `stock = -1`: invalid when stock must be greater than or equal to 0.
- `outflow = -50`: valid with `@Negative`, while `outflow = 0` is invalid under this constraint.
- `balanceAdjustment = 0`: valid with `@NegativeOrZero`.

After this lesson, you should be able to distinguish sign and the 0 boundary accurately; know the supported numeric types, the meaning of `null`, and how to combine `@NotNull` and other constraints; trigger validation in Spring MVC; and verify actual behavior using Java 17+, JUnit, and MockMvc examples.

> Examples use `jakarta.validation.constraints.*` from Jakarta Bean Validation 3.x and Spring Framework 6+/Spring Boot 3.x. For older applications using Bean Validation 2.x/Spring Boot 2.x, the package is usually `javax.validation.constraints.*`; do not mix the two namespaces in the same dependency graph.

## 2. Comparing the Four Constraints via Inequalities

| Annotation | Accepted Value Domain | Interpretation | Value 0 |
| --- | --- | --- | --- |
| `@Positive` | `x > 0` | Strictly positive | **Rejected** |
| `@PositiveOrZero` | `x >= 0` | Non-negative | **Valid** |
| `@Negative` | `x < 0` | Strictly negative | **Rejected** |
| `@NegativeOrZero` | `x <= 0` | Non-positive | **Valid** |

Truth table for an ordinary finite number:

| Value | `@Positive` | `@PositiveOrZero` | `@Negative` | `@NegativeOrZero` |
| --- | --- | --- | --- | --- |
| `-12` | False | False | True | True |
| `-0.01` | False | False | True | True |
| `0` | False | True | False | True |
| `0.0001` | True | True | False | False |
| `25` | True | True | False | False |

Easily confused pairs:
- **Positive differs from PositiveOrZero only at the 0 boundary**. Do not use `@Positive` when 0 is allowed.
- **Negative differs from NegativeOrZero only at the 0 boundary**. Do not use `@Negative` when 0 means no change.
- Both `@PositiveOrZero` and `@NegativeOrZero` accept 0. Combining both on the same value effectively accepts only 0, which is not the clearest way to express an equality-to-zero constraint.
- `@Positive` and `@Negative` on the same field are contradictory for every finite numeric value. Do not use that combination in place of a business constraint.

These four annotations are **standard constraints introduced in Bean Validation 2.0**. They check sign; they do not automatically limit magnitude, measurement units, decimal digits, cross-field relationships, or validity within a business state.

## 3. Placing Annotations on Fields, Properties, or Record Components

A simple DTO:

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.Negative;
import jakarta.validation.constraints.NegativeOrZero;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record InventoryPolicy(
        @NotNull @Positive Integer minimumOrderQuantity,
        @NotNull @PositiveOrZero BigDecimal availableQuantity,
        @NotNull @Negative BigDecimal mandatoryDecrease,
        @NotNull @NegativeOrZero BigDecimal permittedAdjustment) {
}
```

This is a Java 17+ fragment: a complete file needs the name `InventoryPolicy.java` and an appropriate package. Constraints on `record` components are supported by Bean Validation providers via corresponding metadata; similarly, they can be placed on fields/getters of a JavaBean.

Explanation:
1. `minimumOrderQuantity` must have a value and be greater than 0; a minimum order of 0 usually makes no sense.
2. `availableQuantity` must have a value and be non-negative; inventory can be out of stock, so 0 is still valid.
3. `mandatoryDecrease` must have a value and be strictly negative, e.g., `-3.5`; 0 does not represent an actual decrease.
4. `permittedAdjustment` can be negative or zero, e.g., for an adjustment type that may only subtract, never add.

`@NotNull` is not required for the sign check mechanism, yet it is crucial for the input contract. Without it, all four constraints treat `null` as valid per the Jakarta Bean Validation specification.

### 3.1. Is Null Valid?

**Yes, for all four annotations**, and this detail is easily overlooked:

```java
import jakarta.validation.constraints.Positive;

class Product {
    @Positive
    Integer reorderLevel;
}
```

If `reorderLevel == null`, there is no `@Positive` error. To require the field to both exist and be positive:

```java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

class Product {
    @NotNull
    @Positive
    Integer reorderLevel;
}
```

The two constraints answer two independent questions: `@NotNull` asks "is there a value?"; `@Positive` asks "if there is a value, is it greater than 0?". Allowing null lets sign constraints be used on **optional** fields, which does not mean empty business data is always acceptable.

A primitive `int`/`long` field cannot hold `null`. When deserializing JSON with a missing primitive field, the value can become 0 depending on object construction/Jackson configuration, making it impossible to distinguish "omitted" from "sent 0". For request data that must distinguish both cases, use wrapper `Integer`/`Long` with `@NotNull` when appropriate.

### 3.2. Constraints Do Not Run Automatically on Object Construction

Declaring:

```java
InventoryPolicy policy = new InventoryPolicy(
        0,
        new BigDecimal("-2"),
        BigDecimal.ZERO,
        new BigDecimal("1"));
```

only creates a Java object. No exception is automatically thrown by `@Positive` or `@Negative` at the `new` statement. There must be a **validation trigger** such as `jakarta.validation.Validator.validate(policy)`, `@Valid @RequestBody` in Spring MVC, or configured method validation.

Likewise, `@Positive` does not turn negative numbers into positive numbers and does not clamp `-1` to `0`. It merely describes the condition to check and can produce a `ConstraintViolation` when the condition fails.

## 4. Data Types Supported per Jakarta Bean Validation

The four constraints apply to **numeric types**; the portable list defined by the specification includes:

- `BigDecimal` and `BigInteger`.
- Primitives `byte`, `short`, `int`, `long`, `float`, `double`.
- Corresponding wrappers `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`.

Valid examples in terms of annotation placement:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.NegativeOrZero;

class Measurements {
    @Positive long itemCount;
    @Positive BigInteger sequence;
    @Positive BigDecimal unitPrice;

    @NegativeOrZero int signedAdjustment;
    @NegativeOrZero Double correction;
}
```

**Do not apply to `String` as a portable guarantee.** Hibernate Validator may additionally support types such as `CharSequence` or other `Number` subtypes depending on provider/version, but the specification does not mandate supporting those extensions. If a request sends `"quantity": "5"`, let conversion/deserialization convert it to the proper numeric type and validate the constraint on the numeric type rather than relying on an extension.

If an annotation is applied to a type with no compatible validator, the provider may report `UnexpectedTypeException` when validation starts. This is a configuration/type error, **not** an ordinary client sign violation.

### 4.1. Should You Use BigDecimal or float/double?

For money and domains requiring decimal precision, `BigDecimal` is usually better suited than `double` because it stores decimals with application-controlled precision. For example:

```java
new BigDecimal("0.01");  // exact decimal value
new BigDecimal("-0.01"); // exact negative number
```

By contrast, `float`/`double` use binary floating point; arithmetic can introduce tiny inaccuracies around 0. Do not evaluate sign from a floating-point calculation without accounting for business-acceptable tolerance.

Special values `Double.NaN`, `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY`, and signed zero such as `-0.0d` can cause surprises in comparison logic or validator execution; do not use the sign table for **ordinary finite numbers** to claim all special values behave identically across all providers. If an API accepts `Float`/`Double`, explicitly design a finiteness policy (e.g., `Double.isFinite(...)`) and test on your exact provider/version.

With `BigDecimal`, `new BigDecimal("-0.00").signum()` equals 0; this value may format differently from `0.00` yet arithmetically is not strictly negative. Do not use `equals` for numeric comparison of `BigDecimal` values with different scales; `compareTo(BigDecimal.ZERO)` or `signum()` is better for sign checks.

## 5. Distinguishing Sign Checks from Min, DecimalMin, and Magnitude Limits

`@Positive` corresponds to "greater than 0", but is not equivalent to every positive-threshold constraint.

| Requirement | Appropriate Annotation | Notes |
| --- | --- | --- |
| Integer at least 1 | `@Min(1)` or `@Positive` on integer types | Both express the same threshold for integers |
| Decimal greater than 0 | `@Positive` or `@DecimalMin(value = "0", inclusive = false)` | Allows `0.00001` |
| Amount at least 0.01 | `@DecimalMin("0.01")` | `@Positive` alone **does not** guarantee a 0.01 minimum |
| Non-negative number | `@PositiveOrZero` or `@DecimalMin("0")` | Includes 0 |
| Negative number | `@Negative` or `@DecimalMax(value = "0", inclusive = false)` | Excludes 0 |
| Negative or 0 | `@NegativeOrZero` or `@DecimalMax("0")` | Includes 0 |
| Discount percentage from 0 to 100 | `@PositiveOrZero` combined with `@Max(100)` or equivalent | Both endpoints needed |
| Maximum stock quantity | `@PositiveOrZero` + `@Max(...)` | Sign alone does not express upper bound |

Example:

```java
import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

class MoneyRequest {
    @NotNull
    @DecimalMin("0.01")
    @Digits(integer = 10, fraction = 2)
    BigDecimal unitPrice;

    @NotNull
    @Positive
    Integer quantity;
}
```

Here:
- `@DecimalMin("0.01")` rejects `0.001` even though it is positive; `@Positive` would **not** reject this value.
- `@Digits(integer = 10, fraction = 2)` limits digits by numeric format. It does not auto-round invalid values.
- `@Positive` on `quantity` requires quantity > 0, without imposing an upper bound.

`@Min`/`@Max` have no portable contract for `float`/`double` per the Bean Validation specification (some providers extend them); when decimal thresholds are needed, prefer `BigDecimal` and `@DecimalMin`/`@DecimalMax`.

## 6. Standalone Maven + Java 17 Example Outside Spring

This example uses the Jakarta Validation API and Hibernate Validator 8 to produce stable reports for all four constraints. Because this is Bean Validation, the program **requires dependencies and a provider**, and will not run with bare `javac` without a classpath.

Structure:

```text
sign-validation-demo/
├── pom.xml
└── src/main/java/example/SignValidationDemo.java
```

### 6.1. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sign-validation-demo</artifactId>
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
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`expressly` provides the Jakarta EL implementation for validation messages; Hibernate Validator is the provider. In a Spring Boot 3.x application with a dependency management BOM, use `spring-boot-starter-validation` instead of copying the pinned versions from this example.

### 6.2. File src/main/java/example/SignValidationDemo.java

```java
package example;

import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Negative;
import jakarta.validation.constraints.NegativeOrZero;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public final class SignValidationDemo {

    public record Signs(
            @NotNull @Positive Integer requiredPositive,
            @PositiveOrZero BigDecimal nonNegative,
            @Negative BigDecimal strictlyNegative,
            @NegativeOrZero BigDecimal nonPositive) {
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Signs valid = new Signs(
                    5,
                    BigDecimal.ZERO,
                    new BigDecimal("-0.01"),
                    BigDecimal.ZERO);

            Signs invalid = new Signs(
                    0,
                    new BigDecimal("-0.01"),
                    BigDecimal.ZERO,
                    new BigDecimal("0.01"));

            Signs missing = new Signs(
                    null,
                    BigDecimal.ZERO,
                    new BigDecimal("-1"),
                    BigDecimal.ZERO);

            System.out.println("validViolations="
                    + validator.validate(valid).size());

            Set<ConstraintViolation<Signs>> invalids =
                    validator.validate(invalid);

            System.out.println("invalidViolations="
                    + invalids.size());

            String invalidFields = invalids.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .sorted()
                    .collect(Collectors.joining(","));

            System.out.println("invalidFields=" + invalidFields);

            Set<ConstraintViolation<Signs>> missingErrors =
                    validator.validate(missing);

            System.out.println("missingViolations="
                    + missingErrors.size());
            System.out.println("missingField="
                    + missingErrors.iterator().next()
                            .getPropertyPath().toString());
        }
    }
}
```

Run command in `sign-validation-demo` with Maven and JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.SignValidationDemo
```

Stdout **from the program's println calls** (Maven/provider may emit separate logs):

```text
validViolations=0
invalidViolations=4
invalidFields=nonNegative,nonPositive,requiredPositive,strictlyNegative
missingViolations=1
missingField=requiredPositive
```

Why are there four errors? `requiredPositive = 0` violates `@Positive`; `nonNegative = -0.01` violates `@PositiveOrZero`; `strictlyNegative = 0` violates `@Negative`; `nonPositive = 0.01` violates `@NegativeOrZero`.

Why `missingViolations=1`? The value `requiredPositive = null` is valid under `@Positive` alone, yet violates `@NotNull`. The remaining fields are valid. The code sorts field names before printing so it does not depend on `Set<ConstraintViolation>` iteration order, which should not be treated as stable.

## 7. Unit Testing the 0 Boundary and Decimal Values

Testing only large positive numbers does not prove the boundary between the four constraints. We need at least negative numbers, 0, and positive numbers, plus `null` and decimals close to 0.

The following JUnit Jupiter example belongs in a project with Hibernate Validator 8/JUnit 5. Create `src/test/java/example/SignConstraintsTest.java` and ensure the test classpath includes JUnit Jupiter (such as `spring-boot-starter-test` in a Boot project).

```java
package example;

import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Negative;
import jakarta.validation.constraints.NegativeOrZero;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SignConstraintsTest {

    record FourSigns(
            @Positive BigDecimal positive,
            @PositiveOrZero BigDecimal positiveOrZero,
            @Negative BigDecimal negative,
            @NegativeOrZero BigDecimal negativeOrZero) {
    }

    private static Set<String> badFields(
            Validator validator, BigDecimal value) {

        return validator.validate(new FourSigns(
                        value, value, value, value))
                .stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    @Test
    void verifiesZeroAndBothSides() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(
                    Set.of("positive", "positiveOrZero"),
                    badFields(validator, new BigDecimal("-0.01")));

            assertEquals(
                    Set.of("positive", "negative"),
                    badFields(validator, BigDecimal.ZERO));

            assertEquals(
                    Set.of("negative", "negativeOrZero"),
                    badFields(validator, new BigDecimal("0.01")));
        }
    }

    @Test
    void nullIsValidForAllFourConstraints() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            assertEquals(0,
                    validator.validate(
                            new FourSigns(null, null, null, null)).size());
        }
    }
}
```

The test for 0 shows `@Positive` and `@Negative` fail; the two `OrZero` constraints accept it. The null test confirms all four ignore null by default.

For integration-level testing in a Boot app, add `@Valid @RequestBody` tests with 0, negative, positive, null, tiny decimals (e.g., 0.0001), and wrong-type inputs. Testing Bean Validation via `Validator` proves the constraint; HTTP testing proves Spring **actually triggered** it.

## 8. Spring MVC: Validation Only Runs After Type Conversion

A JSON request can contain numeric fields. Jackson reads JSON into the DTO first, and then Spring MVC can invoke the Bean Validation provider when a method parameter uses `@Valid` or `@Validated` in the right context.

Spring Boot 3.x dependencies example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

This is a **dependency fragment** in a Boot project that already has a BOM/parent and application entrypoint, not a standalone Maven file. DTO and controller can reside in package `com.example.pricing`.

**File `src/main/java/com/example/pricing/PricePreviewRequest.java`:**

```java
package com.example.pricing;

import java.math.BigDecimal;

import jakarta.validation.constraints.NegativeOrZero;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record PricePreviewRequest(
        @NotNull @Positive Integer quantity,
        @NotNull @Positive BigDecimal unitPrice,
        @NotNull @PositiveOrZero BigDecimal discount,
        @NotNull @NegativeOrZero BigDecimal adjustment) {
}
```

**File `src/main/java/com/example/pricing/PriceController.java`:**

```java
package com.example.pricing;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PriceController {

    @PostMapping("/prices/preview")
    public ResponseEntity<Void> preview(
            @Valid @RequestBody PricePreviewRequest request) {
        // Illustrates validation only; does not calculate prices.
        return ResponseEntity.noContent().build();
    }
}
```

Valid request:

```http
POST /prices/preview
Content-Type: application/json

{
  "quantity": 2,
  "unitPrice": 19.99,
  "discount": 0,
  "adjustment": -1.25
}
```

When the Bean Validation provider is configured, the controller returns **HTTP 204 No Content** per the code above.

Invalid request:

```http
POST /prices/preview
Content-Type: application/json

{
  "quantity": 0,
  "unitPrice": 19.99,
  "discount": -0.01,
  "adjustment": 0.10
}
```

Deserialization produces the DTO; Bean Validation detects three fields: `quantity` violates `@Positive`; `discount` violates `@PositiveOrZero`; `adjustment` violates `@NegativeOrZero`. With `@Valid @RequestBody` in standard Spring MVC, this scenario typically returns **HTTP 400 Bad Request**, and the controller body does not execute.

**Do not assume a single default JSON error structure.** It depends on Spring Boot version, Problem Details configuration, exception handlers, and `MessageSource`. The exception class commonly seen for `@RequestBody` object validation is `MethodArgumentNotValidException`. If a method has constraints directly on parameters/return values requiring method validation (Spring MVC 6.1+), the exception may be `HandlerMethodValidationException`.

### 8.1. MockMvc Test for the Three Invalid Fields

**File `src/test/java/com/example/pricing/PriceControllerTest.java`:**

```java
package com.example.pricing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PriceController.class)
class PriceControllerTest {

    @Autowired MockMvc mvc;

    @Test
    void acceptsValidSigns() throws Exception {
        mvc.perform(post("/prices/preview")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "quantity": 2,
                          "unitPrice": 19.99,
                          "discount": 0,
                          "adjustment": -1.25
                        }
                        """))
                .andExpect(status().isNoContent());
    }

    @Test
    void rejectsWrongSigns() throws Exception {
        mvc.perform(post("/prices/preview")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "quantity": 0,
                          "unitPrice": 19.99,
                          "discount": -0.01,
                          "adjustment": 0.10
                        }
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(result -> {
                    assertTrue(result.getResolvedException()
                            instanceof MethodArgumentNotValidException);
                    var ex = (MethodArgumentNotValidException)
                            result.getResolvedException();

                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("quantity"));
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("discount"));
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("adjustment"));
                });
    }
}
```

`@WebMvcTest` requires Boot's test dependency (usually `spring-boot-starter-test`), and a Bean Validation provider must be present on the test runtime classpath. The test asserts field errors rather than depending on locale-translated message text.

### 8.2. How Is Validation for @RequestParam Different?

With constraints directly on a method parameter:

```java
import jakarta.validation.constraints.Positive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/stock")
public String stock(@RequestParam @Positive Integer count) {
    return "count=" + count;
}
```

This is only a **controller fragment**, and `@Positive` sits **directly on the method parameter**. Spring MVC 6.1+ includes built-in method validation for this kind of constraint, where errors may go through `HandlerMethodValidationException`. In older applications or the service layer, check what method validation/AOP mechanism is configured. Do not treat `@Valid` alone on an `Integer` as a replacement for `@Positive`.

If a request sends `count=abc`, Spring cannot convert `String` to `Integer`; this is a **type conversion/binding** error, different from having the number 0 fail the sign constraint. Real tests should distinguish these two error categories clearly.

## 9. Using with Collections and Nested Objects

Sign constraints can be placed directly on the **type argument** of a collection, for example:

```java
import java.math.BigDecimal;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record BatchOrderRequest(
        @NotEmpty List<@NotNull @Positive Integer> quantities,
        @NotNull @Valid WarehousePolicy policy) {
}

public record WarehousePolicy(
        @PositiveOrZero BigDecimal availableStock) {
}
```

The `record` types above belong in **two separate Java files** if both are `public`; or declare them package-private in one practice file. This is an illustrative Bean Validation fragment, not a runnable app with just this snippet.

Explanation:
- `@NotEmpty` requires the `quantities` list to have elements; it does not check the sign of each element.
- `List<@NotNull @Positive Integer>` requires every element to be non-null and greater than 0. Element `0` or `-2` fails.
- `@NotNull @Valid WarehousePolicy policy` requires a policy object and **cascades** into `availableStock` to run `@PositiveOrZero`.
- If `@Valid` is omitted on `policy`, root validation only sees `@NotNull` on `policy`; constraints inside `policy` may not be evaluated on this path.
- If `availableStock == null`, `@PositiveOrZero` alone allows null; add `@NotNull` if stock must always be specified.

When handling responses containing field paths like `quantities[0]` or `policy.availableStock`, test with your actual provider. Do not rely on the ordering of the `ConstraintViolation` collection when building responses.

## 10. When Are @Valid, @Validated, and Validation Groups Needed?

`@Positive`/`@Negative` are **constraint annotations**. `@Valid` triggers cascading in an object graph and commonly triggers DTO validation at Spring MVC entrypoints. `@Validated` is Spring's annotation that supports selecting validation groups and plays a role in method validation.

Controller example:

```java
@PostMapping("/prices/preview")
public ResponseEntity<Void> preview(
        @Valid @RequestBody PricePreviewRequest request) {
    return ResponseEntity.noContent().build();
}
```

`@Valid` on the request tells Spring to validate the DTO at the entrypoint. The `@Positive`/`@PositiveOrZero`... annotations on record components actually express the numeric conditions.

When applying different constraint groups for create/update contexts, set `groups = ...` on constraints and select the group at the validation point. Do not overuse groups if the sign contract is identical across operations.

Group configuration example (fragment):

```java
import jakarta.validation.constraints.Positive;
import org.springframework.validation.annotation.Validated;

interface CreateGroup {}

class Draft {
    @Positive(groups = CreateGroup.class)
    Integer requestedQuantity;
}

void handle(@Validated(CreateGroup.class) Draft request) {
    // Used at an appropriate Spring integration point;
    // this is an illustrative signature only, not a complete endpoint.
}
```

Note that `@Positive(groups = CreateGroup.class)` only runs when the provider validates the `CreateGroup` group (or an inheriting/converted group); a call validating only the `Default` group does not automatically trigger constraints declared solely for `CreateGroup`.

For service beans, method validation typically requires supporting configuration and invocation through a Spring proxy. Creating objects with `new` or self-invocation can bypass the proxy. Spring MVC 6.1+ has built-in method validation for controllers; do not assume service beans behave identically to handler methods.

## 11. Edge Cases That Must Be Tested

### 11.1. Zero, Very Small Negative Numbers, and Very Small Positive Numbers

If the policy is `@Positive`, any value **greater than 0** satisfies the inequality, including `0.000001`. If business rules require at least 0.01, `@Positive` is **not enough**.

With `BigDecimal`, test:
- `new BigDecimal("-0.0001")`: negative.
- `BigDecimal.ZERO`: equal to 0.
- `new BigDecimal("0.0001")`: positive.
- `new BigDecimal("0.00")`: numerically equal to 0, despite different scale.
- `new BigDecimal("-0.00")`: `signum() == 0`, not strictly negative.

### 11.2. Negative Numeric Data Represented as Strings

JSON `"amount": -1` and `"amount": "-1"` do not have the same type. Jackson may coerce or reject numeric strings depending on configuration. Bean Validation only evaluates the value after deserialization. Do not use a successful string-typed request to assume all clients can send numbers as strings.

### 11.3. Null and Missing Fields

With wrapper `Integer`/`BigDecimal`, missing fields can yield null. The four sign constraints do not report missing values on their own; add `@NotNull` if that is an error. Do not rely on `@Positive` in place of presence checks.

### 11.4. Numbers Overflowing Data Types

JSON sending an integer exceeding `Integer.MAX_VALUE` can fail deserialization before validation. `@Positive` does not prevent overflow and is not a type-bounds constraint. If values can be large, pick a wider type like `Long`/`BigInteger` and set explicit upper limits as needed.

### 11.5. Computed Values Differing from Request Values

Constraints on inputs do not guarantee all derived calculations are valid. For example, `@Positive price` and `@Positive quantity` can still produce a total exceeding limits, or a discount larger than the subtotal if cross-field constraints are absent. Verify at the business layer and add additional invariants.

### 11.6. Primitives, Wrappers, and Negative Zero

`int` cannot be null; `Integer` can be null. For floating-point, `-0.0` has a negative sign bit yet compares numerically equal to 0 under `==`. Algorithms/providers may represent or classify this value differently from how humans read `"-0.0"`. For money-related data, prefer `BigDecimal` and explicit zero policies; check NaN/Infinity if the system has floating-point inputs.

### 11.7. Requiring Non-Negative Integers, Not Non-Negative Decimals

`@PositiveOrZero BigDecimal` accepts `0.5`; if a count is required, choose `Integer`/`Long` or add matching constraints. Sign does not enforce integrality.

## 12. Recommended Testing Matrix

| Case | Input | Expected |
| --- | --- | --- |
| Positive negative | `-1` | Invalid |
| Positive 0 | `0` | Invalid |
| Positive positive | `1` | Valid |
| PositiveOrZero negative | `-0.01` | Invalid |
| PositiveOrZero 0 | `0` | Valid |
| PositiveOrZero positive | `0.01` | Valid |
| Negative negative | `-1` | Valid |
| Negative 0 | `0` | Invalid |
| Negative positive | `1` | Invalid |
| NegativeOrZero negative | `-1` | Valid |
| NegativeOrZero 0 | `0` | Valid |
| NegativeOrZero positive | `1` | Invalid |
| Four constraints and null | `null` | All valid when used alone |
| `@NotNull @Positive` with null | `null` | Invalid due to NotNull |
| Very small decimal | `0.000001` | Accepted by Positive; does not guarantee currency min |
| Different BigDecimal scale | `0.00` and `-0.00` | Arithmetically zero |
| Unsupported type | Numeric constraint on non-numeric object | Configuration/type validator error, not a sign error |
| Wrong-type JSON | `"quantity":"abc"` | Deserialization/binding error before constraint |
| DTO with invalid field | Valid JSON, `quantity=0` | HTTP 400 when `@Valid` and provider are active |
| Collection | `quantities=[1,0,2]` with List<@Positive Integer> | Error on element equal to 0 |
| Child bean | Field inside policy equals `-2` | Requires `@Valid` path from root |
| Missing provider | Annotations only, no Bean Validation runtime | Cannot assume validation executed |

A good test suite checks both the **provider level** (count, property path) and **HTTP level** (status/field errors), while keeping assertions independent of locale-translated messages.

## 13. Common Mistakes and Fixes

1. **Choosing `@Positive` when 0 should be accepted:** switch to `@PositiveOrZero`.
2. **Choosing `@Negative` when "not increasing" is meant:** if 0 is valid, use `@NegativeOrZero`.
3. **Omitting `@NotNull` on required values:** all four sign constraints treat null as valid; add a separate constraint.
4. **Placing constraints on `String` assuming portability:** the specification requires numeric types; relying on provider extensions makes migration harder.
5. **Using `@Positive` for a minimum price of 0.01:** use `@DecimalMin("0.01")` and digit rules if needed.
6. **Using `double` for money and relying on sign accuracy:** prefer `BigDecimal`; handle non-finite values explicitly if present.
7. **Assuming annotations run during `new DTO(...)`:** a `Validator` or Spring integration must actually invoke validation.
8. **Forgetting `@Valid` on `@RequestBody` parameters:** in standard MVC, DTO constraints do not run at the entrypoint without the proper trigger.
9. **Forgetting `@Valid` cascade for nested objects:** deep constraints in the object graph are not traversed from the root.
10. **Confusing conversion errors with constraint violations:** `"abc"` for `Integer` fails during binding.
11. **Confusing method validation with object validation:** `@Positive` directly on `@RequestParam` follows a different exception flow than `@Valid @RequestBody` in Spring MVC.
12. **Testing only one positive number:** fails to catch `Positive`/`PositiveOrZero` or `Negative`/`NegativeOrZero` mistakes at 0.
13. **Forgetting upper bounds or cross-field invariants:** a positive number can still be nonsensical in business context.
14. **Asserting stable violation ordering:** `Set<ConstraintViolation>` does not guarantee order; sort for stable display/debugging.

## 14. Practical Implementation Checklist

1. Express the requirement as an inequality: `>0`, `>=0`, `<0`, `<=0`; clarify what 0 means.
2. Pick the appropriate numeric type, preferring `BigDecimal` for money; avoid representing numbers as Strings unnecessarily.
3. If missing fields are disallowed, add `@NotNull` (and use wrappers when missing/null distinction matters).
4. If thresholds other than 0 are needed, combine `@DecimalMin`/`@DecimalMax`/`@Min`/`@Max` or a custom business constraint.
5. Ensure a Bean Validation provider is installed and validation is triggered at the right entrypoint; for Spring MVC request DTOs, typically `@Valid @RequestBody`.
6. For collections and child objects, place constraints on type arguments and `@Valid` on paths needing cascade.
7. Test at least negative, 0, positive, and null; add tiny decimals, type limits, wrong-type JSON, overflow, and cross-field cases as needed.
8. When handling responses, distinguish binding errors, Bean Validation constraint violations, and provider configuration errors; do not expose internal stack traces to clients.

### References

- [Jakarta Bean Validation 3.0 Specification — @Positive/@PositiveOrZero/@Negative/@NegativeOrZero constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Jakarta Validation — @Positive API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/positive).
- [Jakarta Validation — @PositiveOrZero API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/positiveorzero).
- [Jakarta Validation — @Negative API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/negative).
- [Jakarta Validation — @NegativeOrZero API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/negativeorzero).
- [Hibernate Validator 8 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/).
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Spring Framework — @RequestBody combined with @Valid](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
