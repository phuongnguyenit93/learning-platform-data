# Testing Validators, Mappers, and Data Transformations

## 1. Why Are These Three Test Groups Important?

In a Spring Boot application, many business bugs occur not in controllers or database queries, but when **validating inputs**, **converting DTOs into other models**, or **normalizing data**. For example: a SKU containing whitespace gets stored in the wrong format, a price gets rounded incorrectly, a field is forgotten during mapping, or a negative quantity slips past a validator.

Three responsibilities can be separated for independent testing:

1. **Validators** inspect data and determine whether it satisfies constraints. The result may be an error list, a valid/invalid outcome, or a designed exception.
2. **Mappers** convert a source object into a target object, ensuring fields are copied accurately and data types and defaults match the contract.
3. **Data transformations** normalize or compute values from inputs, such as `trim`, SKU normalization, currency formatting, rounding, or computing line totals.

Separating these responsibilities lets each unit test answer one clear question. A **validator** should not silently mutate data; a **mapper** should not drop fields; a **transformation** should not produce results that implicitly depend on locale, timezone, or previous runs.

This lesson covers **business unit testing**: calling plain Java methods directly with JUnit Jupiter assertions. If a Spring ApplicationContext is not needed to execute the logic, do not add `@SpringBootTest`. Automatic validation at the HTTP boundary and generated mappers can be tested separately at integration scope when required.

## 2. Define the Contract Before Writing Assertions

A good test relies on predefined rules rather than guessing outcomes after execution. Consider an order-line input:

| Field | Raw data | Rule |
| --- | --- | --- |
| `sku` | `" ab-7 "` | Must contain non-whitespace characters; when mapping, strip leading/trailing whitespace and uppercase using `Locale.ROOT` |
| `quantity` | `3` | Must be greater than 0 |
| `unitPriceText` | `"12.345"` | Must be a valid decimal greater than 0; when converting to unit price, round to 2 decimal places using `HALF_UP` |

In **this learning example**, the line-total rule is:

~~~text
round unit price first: 12.345 -> 12.35
line total = 12.35 × 3 = 37.05
~~~

Rounding the unit price **before multiplying** is a deliberate business choice for this example. Another system might multiply first and round the total; never change the rule without updating both the specification and tests.

To verify properly, express the scenario in Given/When/Then form:

- **Given:** a request with SKU `" ab-7 "`, quantity `3`, price `"12.345"`.
- **When:** the validator checks it, then the mapper converts the valid request into an order line.
- **Then:** the validator reports no errors; the result has SKU `"AB-7"`, quantity `3`, unit price `12.35`, line total `37.05`.

You must also add **negative/boundary** cases: null request, blank SKU, zero or negative quantity, non-numeric price, zero price, negative price, letter casing, decimal places, and values near rounding thresholds.

## 3. Testing Validators: Confirming Proper Acceptance and Rejection

A validator can return a list of error codes so tests easily identify violated rules. Example contract:

| Input condition | Validator result |
| --- | --- |
| Null request | `["request.required"]` |
| Null, empty, or blank SKU | Contains `"sku.required"` |
| Quantity ≤ 0 | Contains `"quantity.positive"` |
| Null or blank price | Contains `"price.required"` |
| Price cannot be parsed as `BigDecimal` | Contains `"price.invalid"` |
| Price ≤ 0 | Contains `"price.positive"` |
| All conditions valid | Empty error list |

When multiple conditions fail simultaneously, the test should verify **all expected errors**. If error ordering is part of the API contract, assert in order. If order is not part of the contract, use a set or `containsExactlyInAnyOrder` from an appropriate assertion library instead of enforcing unnecessary ordering.

**Two rules:**

- Never just assert `errors.isEmpty() == false` for invalid data: that does not prove the right **error type** was detected.
- Do not couple tests to user-facing translated messages when stable error codes are the actual contract; display wording or language can change.

A plain Java validator can be tested via `new OrderValidator()`. There is no need to mock plain Java classes or start a web server. For Jakarta Bean Validation annotations, you must invoke the **validation engine** or cross the integration boundary; section 9 explains the distinction.

## 4. Testing Mappers: Checking Full Results and Ensuring No Data Loss

Mappers convert one data type to another, such as request DTO → domain model, entity → response DTO, or CSV row → import model.

Common bugs:

- Assigning `quantity` to the wrong field, forgetting to map `sku`, or mis-mapping prices.
- Turning `null` into the string `"null"` or inventing wrong defaults.
- Using a money type or scale that differs from the spec.
- Unintentionally mutating the input object.
- Assuming the mapper performs validation that does not actually exist.

For this example, **the validator is responsible for catching invalid data before the mapper is called**. The mapper is allowed to assume the request has already been validated; this is a documented precondition. Accordingly, mapper tests focus on the **concrete target object** rather than repeating every invalid case from the validator.

A mapper test passes when all essential target fields are checked:

~~~text
OrderRequest(" ab-7 ", 3, "12.345")
  -> OrderLine(
       sku = "AB-7",
       quantity = 3,
       unitPrice = 12.35,
       lineTotal = 37.05
     )
~~~

If you only assert that the target object is non-`null`, the test still passes when the mapper drops fields. Compare **target values**, using `assertAll` for related fields. With Java records, comparing the whole record is also helpful when all components implement `equals` properly, though per-field assertions pinpoint failures faster.

**Do not mock the mapper itself when testing mapping.** Whether using MapStruct or a hand-written mapper, test the real mapper implementation. If the target under test is a service that depends on a mapper, you may mock the mapper to isolate service logic; that is a different test.

## 5. Testing Transformations: Rounding, Normalization, and Pure Functions

Transformations should have deterministic input/output behavior. Examples:

- `normalizeSku(" ab-7 ")` returns `"AB-7"`.
- `money("1.004")` returns `1.00`.
- `money("1.005")` returns `1.01` with `RoundingMode.HALF_UP`.
- `money("1.006")` returns `1.01`.
- `money("12.345")` returns `12.35`.

Test values **just below**, **exact at**, and **just above** the rounding boundary. A single happy path cannot safeguard rounding rules.

For money, use `new BigDecimal(String)` instead of `new BigDecimal(double)` when parsing decimal text. Binary floating point cannot represent many decimal fractions accurately; passing a `double` into `BigDecimal` can preserve unwanted precision errors. Also decide **scale** and **rounding mode** by contract rather than relying on implicit defaults.

When normalizing identifiers or search keywords, pass `Locale.ROOT` to `toUpperCase`/`toLowerCase` if the requirement calls for locale-independent machine rules. `String.strip()` handles Java whitespace definitions, whereas `trim()` handles a different character set; tests should match the input characters the system actually supports.

A pure function—one that does not depend on databases/network/time and mutates no external data—is ideal for **parameterized tests**. You can also verify idempotency where applicable, e.g., normalizing a SKU twice produces the same result: `normalizeSku(normalizeSku(x)) == normalizeSku(x)`. **Do not assume every transformation is idempotent**; adding fees or currency conversions may not satisfy that property.

## 6. Complete Java 17 Example: Request, Validator, Mapper, and Transformation

The following files belong to package `com.example.testing` and can be used in a Spring Boot 3.x/Java 17+ project with JUnit Jupiter. Because the production code is plain Java, no Spring context is required.

### 6.1. Input DTO and result model

**File `src/main/java/com/example/testing/OrderRequest.java`:**

~~~java
package com.example.testing;

public record OrderRequest(
        String sku,
        int quantity,
        String unitPriceText
) {
}
~~~

**File `src/main/java/com/example/testing/OrderLine.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal lineTotal
) {
}
~~~

A `record` generates constructor, accessors (e.g., `sku()`), and component-based `equals`. Records work well for data models in this example, but they do not automatically enforce constraints; `new OrderRequest(null, 0, null)` still constructs a record unless checks are explicitly written in the constructor.

### 6.2. Plain Java validator

**File `src/main/java/com/example/testing/OrderValidator.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public final class OrderValidator {
    public List<String> validate(OrderRequest request) {
        if (request == null) {
            return List.of("request.required");
        }

        List<String> errors = new ArrayList<>();

        if (request.sku() == null || request.sku().isBlank()) {
            errors.add("sku.required");
        }

        if (request.quantity() <= 0) {
            errors.add("quantity.positive");
        }

        String priceText = request.unitPriceText();

        if (priceText == null || priceText.isBlank()) {
            errors.add("price.required");
        } else {
            try {
                BigDecimal price = new BigDecimal(priceText.strip());
                if (price.signum() <= 0) {
                    errors.add("price.positive");
                }
            } catch (NumberFormatException ex) {
                errors.add("price.invalid");
            }
        }

        return List.copyOf(errors);
    }
}
~~~

Error codes appear in the order `sku`, `quantity`, `price` when multiple fields are invalid. Tests can assert this ordering because it is the concrete behavior of this example. The validator neither modifies the request nor creates an `OrderLine`.

In a real system, you might add constraints on max quantity, SKU length, decimal scale, price ceiling, or currency. Only add constraints to tests when they actually belong to business requirements.

### 6.3. Transformations extracted into small functions

**File `src/main/java/com/example/testing/OrderTransforms.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public final class OrderTransforms {
    private OrderTransforms() {
    }

    public static String normalizeSku(String sku) {
        return sku.strip().toUpperCase(Locale.ROOT);
    }

    public static BigDecimal money(String rawPrice) {
        return new BigDecimal(rawPrice.strip())
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Both methods have preconditions: arguments must be non-`null`; for `money`, the string must be a valid number. The validation step checks that before mapping. Neither reads Spring configuration nor mutates shared state, making them straightforward to test individually.

### 6.4. Mapper enforcing the mapping contract

**File `src/main/java/com/example/testing/OrderMapper.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.util.Objects;

public final class OrderMapper {
    public OrderLine toLine(OrderRequest request) {
        Objects.requireNonNull(request, "request");

        String sku = OrderTransforms.normalizeSku(request.sku());
        BigDecimal unitPrice = OrderTransforms.money(
                request.unitPriceText()
        );
        BigDecimal lineTotal = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity())
        );

        return new OrderLine(
                sku,
                request.quantity(),
                unitPrice,
                lineTotal
        );
    }
}
~~~

Under this example's contract, the validator must be called and return an empty list **before** `toLine` is invoked in the business flow. The mapper does not replace validation and does not re-check every rule. `BigDecimal.multiply` preserves the proper result scale for these two numbers in the example: `12.35 × 3 = 37.05`.

### 6.5. How the two responsibilities compose

The snippet below illustrates the connection point in the business flow; it is **not a standalone Java file**:

~~~java
OrderRequest request = new OrderRequest(" ab-7 ", 3, "12.345");
OrderValidator validator = new OrderValidator();

List<String> errors = validator.validate(request);
if (!errors.isEmpty()) {
    throw new IllegalArgumentException(String.join(", ", errors));
}

OrderLine line = new OrderMapper().toLine(request);
~~~

If placed inside a Java class, imports for `java.util.List` and the same-package classes are required. The principle here is: **reject first, map second**, preventing the mapper from having to handle invalid values outside its scope.

## 7. JUnit Jupiter: Testing the Validator Across Valid, Invalid, and Boundary Cases

**File `src/test/java/com/example/testing/OrderValidatorTest.java`:**

~~~java
package com.example.testing;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderValidatorTest {
    private final OrderValidator validator = new OrderValidator();

    @Test
    void validate_whenRequestIsValid_returnsNoErrors() {
        OrderRequest request = new OrderRequest(
                " ab-7 ", 3, "12.345"
        );

        assertTrue(validator.validate(request).isEmpty());
    }

    @Test
    void validate_whenRequestIsNull_returnsRequiredError() {
        assertEquals(
                List.of("request.required"),
                validator.validate(null)
        );
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = { "  " })
    void validate_whenSkuIsBlank_returnsSkuRequired(String sku) {
        OrderRequest request = new OrderRequest(sku, 1, "2.50");

        assertEquals(
                List.of("sku.required"),
                validator.validate(request)
        );
    }

    @ParameterizedTest
    @ValueSource(ints = { 0, -1 })
    void validate_whenQuantityIsNotPositive_returnsQuantityError(
            int quantity
    ) {
        OrderRequest request = new OrderRequest(
                "SKU-1", quantity, "2.50"
        );

        assertEquals(
                List.of("quantity.positive"),
                validator.validate(request)
        );
    }

    @ParameterizedTest
    @ValueSource(strings = { "abc", "12,50" })
    void validate_whenPriceCannotBeParsed_returnsInvalidPrice(
            String rawPrice
    ) {
        OrderRequest request = new OrderRequest("SKU-1", 1, rawPrice);

        assertEquals(
                List.of("price.invalid"),
                validator.validate(request)
        );
    }

    @ParameterizedTest
    @ValueSource(strings = { "0", "-0.01" })
    void validate_whenPriceIsNotPositive_returnsPositivePriceError(
            String rawPrice
    ) {
        OrderRequest request = new OrderRequest("SKU-1", 1, rawPrice);

        assertEquals(
                List.of("price.positive"),
                validator.validate(request)
        );
    }

    @Test
    void validate_whenSeveralFieldsAreInvalid_returnsAllErrors() {
        OrderRequest request = new OrderRequest(" ", 0, null);

        assertEquals(
                List.of(
                        "sku.required",
                        "quantity.positive",
                        "price.required"
                ),
                validator.validate(request)
        );
    }
}
~~~

### Why are these assertions meaningful?

- The **valid** case proves the validator does not reject good data, preventing “everything is invalid” bugs.
- The **null request** case proves the logic does not throw an unintended `NullPointerException`.
- `@NullAndEmptySource` and `@ValueSource` cover null, empty string, and whitespace.
- `"12,50"` is rejected because `BigDecimal(String)` under this contract expects dot-decimal notation and does not guess locales.
- The multi-error case ensures the validator does not return early and omit remaining invalid fields.

`@ParameterizedTest` executes once per value, so the test name should describe the **general rule**. Avoid writing separate test methods for every similar value when one parameterized test expresses it more clearly.

## 8. JUnit Jupiter: Testing the Mapper and Transformations

**File `src/test/java/com/example/testing/OrderMapperTest.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderMapperTest {
    private final OrderMapper mapper = new OrderMapper();

    @Test
    void toLine_whenRequestIsValid_mapsAllFields() {
        OrderRequest request = new OrderRequest(
                " ab-7 ", 3, "12.345"
        );

        OrderLine result = mapper.toLine(request);

        assertAll(
                () -> assertEquals("AB-7", result.sku()),
                () -> assertEquals(3, result.quantity()),
                () -> assertEquals(
                        new BigDecimal("12.35"),
                        result.unitPrice()
                ),
                () -> assertEquals(
                        new BigDecimal("37.05"),
                        result.lineTotal()
                )
        );

        // The mapper does not mutate the source record's values.
        assertEquals(" ab-7 ", request.sku());
        assertEquals("12.345", request.unitPriceText());
    }

    @Test
    void toLine_whenInputIsNull_throwsNullPointerException() {
        assertThrows(
                NullPointerException.class,
                () -> mapper.toLine(null)
        );
    }
}
~~~

This test checks **every essential target field** and confirms the input data is not mutated. `assertAll` groups related assertions while keeping a single goal: verifying the mapping contract for one request.

`OrderLine` is constructed fresh, so no mock repository or Spring bean is needed to verify mapping. For mappers with more complex logic, add cases ensuring no fields are dropped, `null` is preserved per agreed rules, or lists are mapped in the right order.

**File `src/test/java/com/example/testing/OrderTransformsTest.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderTransformsTest {

    @Test
    void normalizeSku_whenLowercaseAndPadded_returnsCanonicalSku() {
        assertEquals(
                "AB-7",
                OrderTransforms.normalizeSku(" ab-7 ")
        );
    }

    @Test
    void normalizeSku_whenAlreadyCanonical_remainsUnchanged() {
        assertEquals(
                "AB-7",
                OrderTransforms.normalizeSku("AB-7")
        );
    }

    @ParameterizedTest
    @CsvSource({
            "1.004, 1.00",
            "1.005, 1.01",
            "1.006, 1.01",
            "12.345, 12.35",
            "2, 2.00"
    })
    void money_whenGivenDecimal_roundsHalfUpToTwoPlaces(
            String input,
            String expected
    ) {
        assertEquals(
                new BigDecimal(expected),
                OrderTransforms.money(input)
        );
    }

    @Test
    void money_whenInputIsPadded_acceptsWhitespace() {
        assertEquals(
                new BigDecimal("1.20"),
                OrderTransforms.money(" 1.2 ")
        );
    }
}
~~~

`@CsvSource` supplies string values, avoiding `double` conversion before constructing `BigDecimal`. `assertEquals(new BigDecimal("2.00"), ...)` also verifies **scale 2**, because `BigDecimal.equals` checks both value and scale (`2.0` and `2.00` are not equal under `equals`). This is appropriate when unit-price scale is part of the contract.

If only numerical equality matters regardless of scale, compare using `compareTo(...) == 0`. Never alter the comparison style without understanding the output contract.

## 9. When Using Jakarta Bean Validation in Spring Boot

For Spring Boot 3.x applications, Jakarta Bean Validation annotations such as `@NotBlank`, `@Positive`, and `@Valid` live in package **`jakarta.validation`** (unlike `javax.validation` in older Spring Boot 2.x projects).

DTO example:

~~~java
package com.example.testing;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateOrderDto(
        @NotBlank String sku,
        @Positive int quantity
) {
}
~~~

This is a **separate file `CreateOrderDto.java`**. Annotations are **constraint metadata**; calling `new CreateOrderDto(" ", 0)` by itself **does not trigger Bean Validation**. To test the rules, invoke `jakarta.validation.Validator` with a provider (typically Hibernate Validator via the validation starter).

Example testing Bean Validation directly:

~~~java
package com.example.testing;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CreateOrderDtoValidationTest {

    @Test
    void validate_whenSkuBlankAndQuantityZero_reportsBothFields() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Set<String> invalidFields = validator
                    .validate(new CreateOrderDto(" ", 0))
                    .stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertEquals(Set.of("sku", "quantity"), invalidFields);
        }
    }
}
~~~

The test uses a **set of field names** because the order of `ConstraintViolation` items is not a business order and should not be asserted by index. Both the annotations and a provider must exist on the test classpath; placing annotations in code without an implementation is not enough to execute validation.

In a Spring Boot 3.x project's `build.gradle` (Gradle Groovy DSL), the relevant dependencies are typically:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This covers only the **validation/test slice**, assuming the project already configures the Spring Boot plugin, dependency management/repositories, and an appropriate Java toolchain. `spring-boot-starter-validation` supplies the validation API and implementation; `spring-boot-starter-test` supplies JUnit Jupiter and testing utilities.

If you need to verify that an **HTTP request** is automatically validated and returns HTTP 400 per application configuration, that belongs in a web-layer test using `@WebMvcTest`/`MockMvc` or an appropriate integration test. Assertions there should check status, response body, and the error-handler contract; a unit test calling `Validator` directly **does not prove** the controller has configured `@Valid` properly.

## 10. Generated Mappers (MapStruct) vs Hand-Written Mappers: How to Test?

For hand-written mappers like `OrderMapper` above, instantiate with `new OrderMapper()`. For **MapStruct**, the annotation processor generates the implementation class during build; to test mapping, use the **actual generated implementation** rather than mocking the mapper interface.

Scenarios to cover:

| Scenario | Suggested assertion |
| --- | --- |
| Valid source object | Every important field on target is right |
| Source has `null` | Result/null/default adheres to `nullValueMappingStrategy` or actual mapping config |
| Renamed source/target fields | Target still receives the right value from the designated source field |
| Collection mapping | Size, order, and each item match the contract |
| Numeric/date mapping | Precision, scale, timezone/format are right |
| Enum mapping | All supported values map accurately; unsupported branches behave clearly |
| Mapping into an existing object | Fields outside the update scope are preserved or updated per spec |

No need to write individual tests for every trivial 1:1 setter; focus on **critical mapping rules, data boundaries, and easily missed fields**. With generated mappers, configuration errors may surface at compile time. Unit tests remain valuable to prove **runtime output** is right.

Distinguish **mapping tests** from **service tests that use a mapper**: in mapping tests, run the real mapper; in a separate service test, mocking the mapper can isolate the service. If the mapper is managed by Spring via `componentModel = "spring"`, start a Spring context only when testing wiring or bean-dependent behavior; simple mapper logic can usually be tested directly via the generated implementation and its dependencies.

## 11. Designing Additional Transformation Tests Around Real Boundaries

Transformations frequently carry boundaries beyond the SKU/money example:

| Transformation kind | Cases to try | Common mistakes |
| --- | --- | --- |
| Strings | null, empty, blank, Unicode, whitespace, upper/lower case | Using machine locale so casing varies across environments |
| Money | 0, negative, very small/large values, 1.004/1.005, scale | Using `double` and rounding inaccurately |
| Date/time | Near midnight, date rollover, DST, timezone | Using `ZoneId.systemDefault()` when a fixed timezone is required |
| Collections | Empty, single item, duplicates, ordering | Accidentally dropping or reordering elements |
| Status/enum | All valid values and unsupported values | Silently mapping unknown values to a wrong default |
| Nullable data | Null object, null field, missing field | NPE or fabricating data instead of following the agreed null policy |
| Structured data | Nested objects, IDs, optional fields | Dropping nested fields or creating shared mutable references |

For timezones, **specify `ZoneId` or `Clock` explicitly** and use fixed dates/times in tests. Never call `LocalDateTime.now()` and assert against a hardcoded string, as tests can flake across second/day boundaries.

For normalized data, consider useful properties when they match the contract:

- **Deterministic:** identical input and configuration always yield identical output.
- **Idempotent:** normalizing a second time does not change the first result (when the rule has this property).
- **Non-mutating:** does not modify the source when the mapper/transform is designed to be pure.
- **Total vs partial:** clarify which inputs are accepted and which throw errors. If a function is defined only for valid inputs, test exceptions per contract rather than forcing it to accept arbitrary invalid inputs.

Properties guide test design; they do not replace concrete example and edge-case tests.

## 12. Common Mistakes When Testing Validators, Mappers, and Transformations

1. **Testing only the happy path.** For validators, this easily misses null, blank, negative numbers, and malformed prices. **Fix:** build an equivalence-partition table of valid/invalid classes and boundary values.
2. **Not checking exact error codes.** Asserting only that the error list is non-empty leaves tests green when the wrong rule triggers. **Fix:** assert exact error codes or field paths per contract.
3. **Mocking the validator/mapper inside its own unit test.** That only verifies mock return values. **Fix:** use the real implementation for the component under test.
4. **Lumping validator and mapper into one single test.** When it fails, it is harder to isolate whether input validation or mapping broke. **Fix:** unit test each responsibility; add a few integration tests for combined flow when required.
5. **Forgetting money scale and rounding mode.** Using `assertEquals(12.35, someDouble)` invites precision bugs and hides rounding mode. **Fix:** `BigDecimal(String)`, `setScale`, and scale-aware assertions.
6. **Depending on machine locale or timezone.** Tests pass locally on a dev laptop but fail in CI. **Fix:** pass `Locale`, `ZoneId`, or `Clock` per contract.
7. **Assuming Jakarta annotations run automatically upon DTO instantiation.** `new` does not trigger Bean Validation. **Fix:** invoke `Validator.validate` or test at the Spring validation boundary.
8. **Asserting violation order without an ordering contract.** Order can change across implementations or versions. **Fix:** compare sets or order-independent contents.
9. **Mapper tests that only assert non-null result.** Dropped fields still pass. **Fix:** assert all essential business fields.
10. **Bringing real I/O into unit tests of pure transformations.** Slows tests down and adds environment flakiness. **Fix:** isolate data logic into pure functions; test DB/HTTP/files separately when integration proof is needed.
11. **Changing assertions to match current output when a test turns red.** That can legitimize a bug. **Fix:** compare against approved rules, determine whether code or test is wrong, then fix.
12. **Test inputs without stated preconditions.** One test expects the mapper to validate while another assumes input is already validated. **Fix:** document preconditions and responsibility boundaries for each class.

## 13. Running Tests and Self-Checking Scope

The files in sections 6–8 share package `com.example.testing` in their respective `main`/`test` source sets. `CreateOrderDto.java` and the Jakarta test in section 9 are only needed when the validation starter is present.

Run each class individually from a directory with Gradle Wrapper on macOS/Linux:

~~~bash
./gradlew test --tests "com.example.testing.OrderValidatorTest"
./gradlew test --tests "com.example.testing.OrderMapperTest"
./gradlew test --tests "com.example.testing.OrderTransformsTest"
./gradlew test --tests "com.example.testing.CreateOrderDtoValidationTest"
~~~

On Windows, use `gradlew.bat` instead of `./gradlew`. The final class requires `spring-boot-starter-validation` and a Jakarta provider. These tests do not call `System.out.println`, so there is no fixed application stdout string. The test runner reports PASS/FAIL and detailed outcomes depending on Gradle/JUnit/IDE.

Before finalizing each test suite, verify:

- [ ] Contracts for validator, mapper, and transformation are stated separately and clearly.
- [ ] Valid cases, error cases, and practical boundaries exist for each rule.
- [ ] The validator returns the exact expected errors, including when multiple fields are invalid.
- [ ] The mapper populates **every essential field** accurately; no silent data loss.
- [ ] Precision, scale, rounding mode, locale, and timezone are defined and asserted where relevant.
- [ ] Tests do not mock the function/class being proven.
- [ ] Tests run independently without relying on stale state or CI environment defaults.
- [ ] Unit tests do not claim to prove HTTP validation or Spring wiring if that layer has not been exercised.

**Remember:** validators protect **validity conditions**; mappers protect **accuracy and completeness of mapping**; transformations protect **normalization/calculation rules**. Test each responsibility with purposeful inputs, specific assertions, and boundary values, adding coordination tests only where an end-to-end business flow needs to be proven.