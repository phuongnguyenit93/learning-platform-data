# Testing Pure Validation and Data Conversion Rules

Validation and data conversion are two rule groups that appear across many layers of a Spring application. Validation determines whether data satisfies business or structural conditions; data conversion transforms one representation into a data type the rest of the application can use. These rules can usually be tested directly with unit tests without starting a Spring `ApplicationContext`.

For example, a registration form may require that the email not be blank, the password meet a minimum length, and the date of birth not be in the future. A converter may transform the status string `" pending "` into the enum `PENDING`, or a formatter may convert a user-formatted date string into a `LocalDate`. You can verify these rules with concrete inputs, outputs, or errors, and separately test how Spring registers and invokes them at the integration layer when needed.

## 1. Distinguishing Validation from Data Conversion

These two operations often appear consecutively in a processing flow, yet they serve different purposes.

| Operation | Question to Answer | Example | Typical Outcome |
|---|---|---|---|
| Validation | Is the existing data valid according to the rules? | Is the email well-formed? Is the quantity greater than 0? | Valid, a list of errors, or `ConstraintViolation` |
| Conversion | Which target value corresponds to the source representation? | String `"42"` to `Integer`; `"2026-11-12"` to `LocalDate` | Target value or conversion error |
| Formatting | How is a value represented as text in a specific locale? | `LocalDate` to `12/11/2026` | String or parse error |

Conversion does not automatically mean validation is complete. Converting the string `"0"` to the integer `0` succeeds as a type conversion, yet business rules may require quantity to be greater than 0. Conversely, a date string may be properly formatted yet represent a date disallowed by business rules.

A typical HTTP flow might look like:

```text
Text / JSON request
          |
          v
Convert to Java data types
          |
          v
Validate structure and business rules
          |
          v
Call service when data is valid
```

Depending on the endpoint type and binding mechanism, the exact order may vary. The important point when designing unit tests is to identify which rule is being tested: converter, formatter, validator, or the full web-layer binding process.

## 2. Defining the Contract to Test

Before writing tests, clearly describe the input data, valid outcomes, and behavior on invalid data.

For validation, determine:

- The target object and fields being checked.
- Validity conditions, such as requiredness, length, value ranges, or cross-field relationships.
- How `null`, empty strings, and whitespace-only strings are handled.
- Error codes, property paths, or constraint groups to return.
- Whether multiple errors are reported together or only the first error.
- Whether validation depends on external state or solely on the object's own data.

For conversion and formatting, determine:

- Source and target types.
- Normalization rules such as trimming, letter casing, or measurement units.
- Boundary values and precision.
- Behavior with `null`, empty strings, and whitespace.
- How unconvertible inputs are handled.
- Which locale, time zone, or format affects the result.
- Whether round-tripping is required: must parsing then printing recover the same representation or the same value?

A test case can be written using a template:

| Field | Example Content |
|---|---|
| Rule | Order quantity must be greater than 0 |
| Input | `0` |
| Other conditions | No external state needed |
| Expected result | Error on field `quantity` |
| Side effects | Do not call repository or persistence service |

For a converter:

| Field | Example Content |
|---|---|
| Rule | Status string is normalized then mapped to enum |
| Input | `" pending "` |
| Target type | `OrderStatus` |
| Expected result | `OrderStatus.PENDING` |
| Invalid input | `"unknown"` |
| Error result | `IllegalArgumentException` per converter contract |

When the contract is clear, tests focus on the behavior that needs protection rather than merely checking that a method was called.

## 3. Testing Pure Spring Validators

Spring Framework provides the `org.springframework.validation.Validator` interface for custom validators. This interface has two main methods:

- `supports(Class<?> clazz)`: indicates whether the validator supports the requested object type.
- `validate(Object target, Errors errors)`: checks the object and records any errors into `Errors`.

A validator can be tested using `BeanPropertyBindingResult` without a Spring context. The test creates the input object, creates the error container, calls `validate`, and then inspects errors by field or object.

### 3.1. Example validator for a registration form

Suppose the form has an email and a password:

```java
public class RegistrationForm {

    private String email;
    private String password;

    public RegistrationForm(String email, String password) {
        this.email = email;
        this.password = password;
    }

    public String getEmail() {
        return email;
    }

    public String getPassword() {
        return password;
    }
}
```

The validator enforces concrete rules:

```java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component
public class RegistrationFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return RegistrationForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "email", "email.required");

        if (!errors.hasFieldErrors("email")
                && !form.getEmail().matches("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")) {
            errors.rejectValue("email", "email.invalid");
        }

        String password = form.getPassword();
        if (password == null || password.length() < 12) {
            errors.rejectValue("password", "password.tooShort");
        }
    }
}
```

The regex in the example is merely an illustrative rule for a simple validator, not a full email checker covering every standard. Real applications should choose an email policy suited to their business rules and address-verification workflow.

### 3.2. Testing the validator with JUnit Jupiter

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;

import static org.junit.jupiter.api.Assertions.*;

class RegistrationFormValidatorTest {

    private RegistrationFormValidator validator;

    @BeforeEach
    void setUp() {
        validator = new RegistrationFormValidator();
    }

    @Test
    void supportsRegistrationForm() {
        assertTrue(validator.supports(RegistrationForm.class));
    }

    @Test
    void rejectsBlankEmailAndShortPassword() {
        var form = new RegistrationForm("   ", "short");
        Errors errors = new BeanPropertyBindingResult(form, "registrationForm");

        validator.validate(form, errors);

        assertTrue(errors.hasFieldErrors("email"));
        assertEquals("email.required", errors.getFieldError("email").getCode());
        assertTrue(errors.hasFieldErrors("password"));
        assertEquals("password.tooShort", errors.getFieldError("password").getCode());
    }

    @Test
    void acceptsValidForm() {
        var form = new RegistrationForm("user@example.com", "long-password-123");
        Errors errors = new BeanPropertyBindingResult(form, "registrationForm");

        validator.validate(form, errors);

        assertFalse(errors.hasErrors());
    }
}
```

`BeanPropertyBindingResult` is the right implementation for testing errors bound to JavaBean properties. The test checks stable error codes emitted by the validator; user-facing messages are typically resolved via `MessageSource` in the configuration or web layer, so validator unit tests do not need to lock onto a translated message sentence.

### 3.3. Partitioning validator inputs

A validator usually requires more input groups than the two examples above. For email, you can build a matrix:

| Group | Representative Data | Expected Outcome |
|---|---|---|
| `null` | `null` | Required error |
| Empty | `""` | Required error |
| Whitespace only | `"   "` | Required error |
| Missing local part | `"@example.com"` | Format error |
| Missing domain | `"user@"` | Format error |
| Valid per chosen rule | `"user@example.com"` | No errors |

For a password with a minimum length of 12 characters, test 11, 12, and 13 characters to catch off-by-one boundary bugs. Also clarify whether leading/trailing whitespace counts toward length or must be normalized beforehand. That decision belongs to the business contract and must be reflected in the tests.

`@ParameterizedTest` can be used to test multiple inputs against the same rule:

```java
@ParameterizedTest
@NullAndEmptySource
@ValueSource(strings = {" ", "   ", "\t"})
void rejectsMissingEmail(String email) {
    var form = new RegistrationForm(email, "long-password-123");
    Errors errors = new BeanPropertyBindingResult(form, "registrationForm");

    validator.validate(form, errors);

    assertEquals("email.required", errors.getFieldError("email").getCode());
}
```

`@NullAndEmptySource` and `@ValueSource` are JUnit Jupiter parameter sources. If the project uses the aggregator `junit-jupiter` dependency, the parameterized test module is usually already included in the test configuration.

### 3.4. Testing object-level errors and cross-field relationships

Some rules do not belong to a single field. For example, the end date must be after the start date, or at least one of two contact methods must be provided. For such rules, the validator can call `errors.reject(...)` to record an object error instead of `rejectValue(...)`.

```java
if (form.getStartDate() != null
        && form.getEndDate() != null
        && !form.getEndDate().isAfter(form.getStartDate())) {
    errors.reject("dateRange.invalid");
}
```

Tests should check `errors.hasGlobalErrors()` and the corresponding error code. If the UI contract ties the rule to a specific field, use `rejectValue` so the error carries the expected field path.

For nested errors, check field paths such as `address.postalCode`. Construct the nested objects properly and verify the validator produces the path expected by the binding layer.

## 4. Testing Jakarta Bean Validation

Beyond `org.springframework.validation.Validator`, Spring integrates with Jakarta Bean Validation (formerly Bean Validation API) via a corresponding provider. Constraints such as `@NotBlank`, `@Email`, `@Size`, `@Min`, `@Max`, and `@NotNull` are placed on fields, getters, parameters, or types.

When only testing constraints, you can use `jakarta.validation.Validator` directly. This checks Bean Validation rules without starting the entire Spring `ApplicationContext`.

### 4.1. Object with constraints

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class CreateAccountRequest {

    @NotBlank
    @Email
    private String email;

    @NotBlank
    @Size(min = 12, max = 72)
    private String password;

    public CreateAccountRequest(String email, String password) {
        this.email = email;
        this.password = password;
    }

    public String getEmail() {
        return email;
    }

    public String getPassword() {
        return password;
    }
}
```

The `max = 72` limit here merely illustrates a specific contract; actual limits must match the password storage algorithm and application requirements. Do not copy example limits without checking your security policy.

### 4.2. Creating a Validator and checking ConstraintViolation

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import java.util.stream.Collectors;

class CreateAccountRequestValidationTest {

    @Test
    void reportsEmailAndPasswordViolations() {
        try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new CreateAccountRequest(" ", "short");

            var violations = validator.validate(request);
            Set<String> invalidProperties = violations.stream()
                    .map(violation -> violation.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertTrue(invalidProperties.contains("email"));
            assertTrue(invalidProperties.contains("password"));
        }
    }

    @Test
    void acceptsRequestWithValidValues() {
        try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new CreateAccountRequest(
                    "user@example.com", "a-long-valid-password");

            assertTrue(validator.validate(request).isEmpty());
        }
    }
}
```

This example assumes a Bean Validation provider is present on the test runtime classpath. `Validation.buildDefaultValidatorFactory()` discovers a provider via the Jakarta Validation mechanism; if only the API is present without a provider, the test cannot create a validator. `ValidatorFactory` should be closed after use, so the example uses try-with-resources.

When checking constraints, prefer asserting property paths, annotation/constraint descriptors, or application-defined error codes. Message text can vary by locale and translation bundles. Assert exact message strings only when that text is part of a contract to protect.

### 4.3. Testing custom constraints

When defining a custom constraint, test both the annotation and its `ConstraintValidator`. For example, `@ValidPhoneNumber` might use `PhoneNumberValidator` to check formatting per system policy.

Test cases should include:

- Typical valid values.
- `null`, depending on whether the contract allows or rejects `null`.
- Empty strings and whitespace.
- Minimum length, maximum length, and just-outside boundaries.
- Unsupported characters.
- Values with valid syntax that violate business rules.

For custom constraints, verify `@Constraint(validatedBy = ...)`, target types, and `null` handling. In Bean Validation, validators usually treat `null` as valid so another constraint like `@NotNull` handles requiredness; however, if a custom constraint has a different contract, document it and test accordingly.

### 4.4. Groups, nested objects, and class-level constraints

Bean Validation supports validation groups to apply different constraint sets by context, such as creation versus update. When testing groups, call `validator.validate(object, Create.class)` or the relevant group and verify which constraints apply. If a group sequence exists, test the ordering and short-circuiting when an earlier group fails.

For nested properties, `@Valid` instructs the validator to validate child objects as well. Tests should construct both parent and child objects, then verify the full property path, such as `address.postalCode`.

For class-level constraints, the result is usually a violation at the object level or at a property node configured by the validator. Verify the exact path required by the API or form contract.

### 4.5. When do you need LocalValidatorFactoryBean or a Spring context?

`LocalValidatorFactoryBean` is Spring's adapter for Jakarta Bean Validation and Spring `Validator`. If the goal is simply testing constraints and the provider, a validator from `Validation.buildDefaultValidatorFactory()` is enough. If you need to verify Spring's validator configuration, `MessageSource` integration, validator injection into beans, or Spring-managed provider configuration, test `LocalValidatorFactoryBean` in an appropriate Spring test.

Similarly, method validation based on `@Validated` typically requires a Spring AOP proxy and method validation configuration. A unit test calling the Java object directly bypasses the proxy and will not prove the interceptor enforced parameter constraints. That requires an integration test with a Spring context or an explicitly configured proxy test.

## 5. Testing Spring Converters

Spring Core provides the `org.springframework.core.convert.converter.Converter<S, T>` interface to convert a source value of type `S` to target type `T`.

```java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
```

A converter is typically a plain Java component: it accepts one value and returns the corresponding value. If the converter has no external dependencies, it can be instantiated directly in tests to verify outcomes.

### 5.1. Example converting a string to an enum

```java
import org.springframework.core.convert.converter.Converter;

import java.util.Locale;

public class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Order status is required");
        }

        try {
            return OrderStatus.valueOf(source.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(
                    "Unsupported order status: " + source, exception);
        }
    }
}
```

Assumed enum:

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}
```

Direct test:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class StringToOrderStatusConverterTest {

    private final StringToOrderStatusConverter converter =
            new StringToOrderStatusConverter();

    @Test
    void trimsAndNormalizesInput() {
        assertEquals(OrderStatus.PENDING, converter.convert(" pending "));
        assertEquals(OrderStatus.CONFIRMED, converter.convert("CONFIRMED"));
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("   "));
    }

    @Test
    void rejectsUnknownValue() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("ARCHIVED"));
    }
}
```

This example intentionally defines the converter to reject `null` and blank strings. In a flow using `ConversionService`, the framework may handle `null` before invoking the converter; thus testing the converter directly versus through the service can yield different observable behavior for `null`. Define the contract at the exact boundary under test.

### 5.2. Testing a Converter through ConversionService

When you need to verify that a converter is registered and selected properly by `ConversionService`, use a lightweight implementation such as `DefaultConversionService`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.core.convert.support.DefaultConversionService;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderStatusConversionServiceTest {

    @Test
    void convertsStringWhenCustomConverterIsRegistered() {
        var conversionService = new DefaultConversionService();
        conversionService.addConverter(new StringToOrderStatusConverter());

        OrderStatus result = conversionService.convert(
                " pending ", OrderStatus.class);

        assertEquals(OrderStatus.PENDING, result);
    }
}
```

This test still requires no `ApplicationContext`. It additionally verifies registering the converter in the registry and converting through the API that Spring components use.

Split the two goals into separate tests when clear diagnostics are needed:

- Direct converter tests protect the conversion algorithm.
- `ConversionService` tests protect converter registration and selection.

If the converter works directly but the service test fails, check whether the registry contains the converter, whether the source/target type pair matches, and whether another converter is competing.

### 5.3. ConverterFactory and GenericConverter

`ConverterFactory<S, R>` fits when one source type can convert to multiple target types in the same family. For example, converting strings to different enums can use a general factory. Tests should verify multiple target types, not just a single concrete enum.

`GenericConverter` fits when declaring multiple source/target pairs or needing `TypeDescriptor` information, such as collection or annotation metadata. When testing it, verify:

- `getConvertibleTypes()` declares the expected type pairs.
- The converter is selected for the right source/target pair.
- Generic types or required metadata are preserved properly.
- Unsupported cases are not accidentally routed to a different converter.

Do not use `GenericConverter` if a simple `Converter<S, T>` expresses the rule completely. The more general the API, the more explicitly tests must cover the type pairs and metadata it relies on.

## 6. Testing Formatters and Locale Rules

Spring's `Formatter<T>` combines both directions: parsing a string into an object and printing an object into a string. Formatters often depend on locale, so the same value may display differently across languages or regions.

The interface has two main methods:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
    // print(T object, Locale locale)
    // parse(String text, Locale locale) throws ParseException
}
```

### 6.1. Example date formatter

```java
import org.springframework.format.Formatter;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class LocalDateFormatter implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(String text, Locale locale) throws ParseException {
        DateTimeFormatter formatter = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", locale);
        try {
            return LocalDate.parse(text, formatter);
        } catch (DateTimeParseException exception) {
            ParseException parseException = new ParseException(
                    "Invalid date: " + text, exception.getErrorIndex());
            parseException.initCause(exception);
            throw parseException;
        }
    }

    @Override
    public String print(LocalDate object, Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale).format(object);
    }
}
```

In this example, the pattern is fixed to illustrate passing `locale` to the formatter. For regional date conventions, you can use `DateTimeFormatter.ofLocalizedDate(...)` and an appropriate `FormatStyle`. Choose a consistent policy between input and output.

### 6.2. Testing parse and print

```java
import org.junit.jupiter.api.Test;

import java.text.ParseException;
import java.time.LocalDate;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.*;

class LocalDateFormatterTest {

    private final LocalDateFormatter formatter = new LocalDateFormatter();

    @Test
    void parsesDateUsingExpectedPattern() throws ParseException {
        LocalDate result = formatter.parse("12/11/2026", Locale.forLanguageTag("vi-VN"));

        assertEquals(LocalDate.of(2026, 11, 12), result);
    }

    @Test
    void printsDateUsingExpectedPattern() {
        String result = formatter.print(
                LocalDate.of(2026, 11, 12), Locale.forLanguageTag("vi-VN"));

        assertEquals("12/11/2026", result);
    }

    @Test
    void rejectsImpossibleDate() {
        assertThrows(ParseException.class,
                () -> formatter.parse("31/02/2026", Locale.ROOT));
    }
}
```

These tests check the formatter's contract directly without relying on the machine's default locale. Avoid calling `Locale.getDefault()` in tests targeting a specific locale, as results may differ between personal machines and CI.

### 6.3. Locale and global state

When testing formatters via Spring's `FormattingConversionService`, some formatters receive the locale from `LocaleContextHolder`. This is thread-local state and can affect subsequent tests if not restored.

If a test must temporarily set a locale:

```java
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;

import java.util.Locale;

LocaleContext previous = LocaleContextHolder.getLocaleContext();
try {
    LocaleContextHolder.setLocale(Locale.forLanguageTag("vi-VN"));
    // perform conversion/formatting requiring locale
} finally {
    LocaleContextHolder.setLocaleContext(previous);
}
```

If a test does not need Spring's locale context, calling `parse(text, locale)` and `print(value, locale)` directly is simpler and avoids shared state.

## 7. Testing Edge Cases in Data Conversion

A converter may work on ordinary inputs yet fail on whitespace, large values, precision, or special characters. Group test cases according to data type and actual rules.

### 7.1. Strings and enums

- Empty strings, whitespace-only strings, `null`.
- Uppercase/lowercase variations and leading/trailing whitespace.
- Valid values, unsupported values, and Unicode characters if allowed.
- Aliases or legacy names if the system supports backward compatibility.

### 7.2. Numbers and currency

- Negative integers, zero, positive integers, and data type limits.
- Decimals with more fractional digits than the allowed scale.
- Locale-specific decimal separators and grouping separators.
- Rounding rules or rejecting excess fractional digits.
- Currency units, decimal places, and unit conversions.

For currency, use `BigDecimal` instead of `double` to avoid binary floating-point inaccuracies. Tests should compare via `compareTo` when the contract only cares about numeric value and not a specific scale; if scale is part of the contract, assert `scale()` or the normalized representation as well.

```java
BigDecimal expected = new BigDecimal("1234.50");
BigDecimal actual = converter.convert("1234.50");

assertEquals(0, expected.compareTo(actual));
```

If the rule requires preserving a scale of two digits, add an assertion for scale or the matching representation. Avoid `new BigDecimal(0.1)` in currency tests; use decimal strings to create deterministic values.

### 7.3. Dates, times, and time zones

- Valid dates and nonexistent dates, such as February 31.
- Leap years and February 29.
- Start/end of month and start/end of year.
- Instants with different offsets or zones.
- Daylight saving time (DST) transitions if the application uses DST zones.
- Supported locales and patterns.

`LocalDate` represents a calendar date without a time zone; `LocalDateTime` represents date and time without a time zone; `Instant` is a point on the timeline; `ZonedDateTime` and `OffsetDateTime` carry zone or offset metadata. Do not convert among these types while ignoring time-zone semantics. Tests should fix both zone and instant when results depend on time.

### 7.4. Collections and generic types

When converting lists or sets, determine:

- Is element order preserved?
- Are duplicates removed?
- Does one invalid element fail the whole collection or get skipped?
- Do an empty collection and `null` carry different meanings?
- Is the target element type fully resolved?

Especially with `GenericConverter`, `TypeDescriptor` can carry generic metadata that a single `Class<?>` cannot represent. Tests must pass the right descriptor if converter behavior depends on element types or metadata.

## 8. Testing Conversion and Validation as Independent Steps

Successful conversion does not prove data is valid. For example, the string `"-5"` converts cleanly to an integer, yet negative product quantities may be rejected. Conversely, a value might be business-valid yet unparseable due to bad formatting.

Separate tests by responsibility:

1. **Converter/Formatter tests:** verify source representations convert to target values or parse errors per contract.
2. **Validator tests:** verify the converted Java values satisfy business rules.
3. **Binding/integration tests:** verify Spring combines conversion and validation in a request flow when that behavior needs protection.

For example, with `quantity`:

| Input String | Conversion to `Integer` | Validation `quantity > 0` |
|---|---|---|
| `"5"` | Succeeds, value 5 | Valid |
| `"0"` | Succeeds, value 0 | Invalid |
| `"-2"` | Succeeds, value -2 | Invalid |
| `"abc"` | Conversion error | No Integer value yet to validate |
| `""` | Depends on binding/converter rule | Must define how null/empty is handled |

This separation pinpoints which step failed and avoids writing oversized tests that only show the final request failed.

## 9. Verifying Converter and Validator Registration in Spring

Direct unit tests prove a class's rules. However, a correct converter or validator can still go unused by Spring if registration configuration is missing or scoped improperly.

### 9.1. Registering converters in ConversionService

Spring allows registering converters with `ConversionService` or through `ConverterRegistry`. In an application, registration may come from Java configuration, `WebMvcConfigurer#addFormatters`, or appropriate auto-configuration.

For lightweight verification, create a `DefaultConversionService`, call `addConverter`, and verify the conversion pair. For application configuration tests, load the Spring context and inject `ConversionService` to confirm the converter is actually registered.

There is no need to load the entire context just to test a converter's algorithm. Use integration tests only when the goal includes bean configuration, registration ordering, or web binding behavior.

### 9.2. Registering Validators in the web layer

An `org.springframework.validation.Validator` can be invoked manually in a controller, registered via MVC configuration, or applied in the appropriate binding flow. Testing `validate()` directly does not prove the controller invoked that validator.

When web-layer verification is needed:

- Use Spring MVC Test/`MockMvc` to send requests.
- Assert status codes and error responses per the API contract.
- Check returned field paths or error codes if exposed publicly.
- Verify the service is not called when validation fails.

With `@Valid` or `@Validated`, verify the right target object and annotation placement. For method validation, Spring AOP/method validation configuration is required so calls go through a proxy. A unit test invoking the validator directly remains valuable, as it protects a different layer of responsibility.

## 10. Writing Readable Tests with Arrange–Act–Assert

Every test should clearly present three parts:

- **Arrange:** create the object, validator/converter, locale, and input data.
- **Act:** invoke the single behavior under test.
- **Assert:** verify values, errors, property paths, or side effects.

Example test name:

```java
@Test
void validate_whenPasswordIsTooShort_addsPasswordFieldError() {
    // Arrange
    var form = new RegistrationForm("user@example.com", "short");
    Errors errors = new BeanPropertyBindingResult(form, "form");

    // Act
    validator.validate(form, errors);

    // Assert
    assertTrue(errors.hasFieldErrors("password"));
}
```

A test name that describes condition and outcome helps reports identify which rule failed. Avoid generic names like `testValidation` or `testConvert`, which fail to convey the scenario being guarded.

Use parameterized tests for multiple inputs sharing one rule. For cases with substantially different setup or outcomes, separate test methods are easier to read than a method full of `if` branches.

## 11. Common Mistakes When Testing Validation and Conversion

**Testing only valid data.** A validator typically has multiple rejection branches; a converter needs to handle malformed input. Test equivalence partitions and boundary values.

**Confusing conversion errors with validation errors.** `"abc"` failing to parse as an integer is a conversion error; `-1` parsing cleanly yet failing a quantity check is a validation error. APIs may render these two errors differently.

**Leaving behavior for `null` and empty strings undefined.** Some converters are not invoked for `null` sources through `ConversionService`; validators may treat `null` as valid so `@NotNull` handles it. Tests must reflect the exact API boundary.

**Relying on the machine's default locale.** Tests passing locally may differ in CI. Pass `Locale` explicitly or set and restore `LocaleContextHolder` when required.

**Comparing decimals with `double`.** For currency and precision-sensitive data, use `BigDecimal` and explicitly define scale and rounding modes.

**Asserting literal translated messages.** Messages can vary across bundles and locales. Prefer checking error codes, property paths, and constraint descriptors unless exact message wording is part of the contract.

**Booting the entire Spring context for pure rules.** Validators or converters without Spring dependencies can be instantiated directly. Load a context only when verifying integration or configuration.

**Testing a converter in isolation while ignoring registration.** Direct tests do not prove a converter is registered. If registration carries risk, add a `ConversionService` test or a configuration integration test.

**Leaking global state between tests.** Locale, system properties, time zones, and caches can affect subsequent tests. Restore state in `finally` or use resource-managing extensions.

## 12. Workflow for Building the Test Suite

When implementing tests for validation and data conversion in a Spring project, you can follow this sequence:

1. Determine whether the rule belongs to validation, conversion, or formatting.
2. Document source/target types, fields, boundary data, and `null`/empty behavior.
3. Decouple pure rules from web binding, external dependencies, and Spring context where possible.
4. Write direct unit tests for validators, converters, or formatters using JUnit Jupiter.
5. Use parameterized tests for input groups sharing the same expected outcome.
6. Assert stable error codes, property paths, target values, or exceptions per contract.
7. Add `ConversionService` or `LocalValidatorFactoryBean` tests if verifying Spring adapters/registries is needed.
8. Add MVC or Spring context integration tests when protecting registration, binding, `@Valid`, `@Validated`, or method validation.
9. Ensure tests are independent of locale, time zone, shared data, and execution order.

When these steps are clearly separated, tests pinpoint exactly which rule broke: unparseable input, an invalid converted value, a validator flagging the wrong field, or Spring failing to register the component. This forms the foundation for protecting data rules in a Spring application with fast, readable, and stable unit tests.
