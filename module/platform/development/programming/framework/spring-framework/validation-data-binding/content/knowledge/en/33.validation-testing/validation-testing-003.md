# Testing DataBinder with Valid, Invalid-Type, and Missing-Field Values

## 1. Lesson Objectives

In Spring Framework, `org.springframework.validation.DataBinder` is the component that takes property-name/value pairs, performs **binding** onto a Java object, and collects errors via `BindingResult`. Testing a form in a browser only reveals the end behavior of the HTTP API; testing `DataBinder` directly helps separate **type conversion errors**, **missing-field errors**, **business validation errors**, and **fields rejected from binding**.

After this lesson, you will be able to:

1. Create a standalone binder for a JavaBean using `new DataBinder(target, objectName)`.
2. Supply simulated request data using `MutablePropertyValues` and call `binder.bind(values)`.
3. Test the valid case: `String "3"` is converted to `Integer 3` with no errors.
4. Test the invalid-type case: `"abc"` fails to convert to `Integer`, creating a `FieldError` with the base code `typeMismatch`.
5. Test missing required fields: `setRequiredFields("quantity")` creates a `required` error during binding.
6. Distinguish "field not sent" from "empty field sent", "`null` value", and "bound successfully but violating business rules".
7. Explicitly call `binder.validate()` to run the registered Spring `Validator` and separate validation errors from binding errors.
8. Test `setAllowedFields(...)` and `getSuppressedFields()`, preventing over-posting during tests.
9. Write JUnit 5 tests runnable with Maven, without depending on a web server or database.

**Key takeaway:** `DataBinder#bind(...)` **is not synonymous** with `DataBinder#validate()`. A successfully bound object can still violate business rules; an object missing a field might not yet have a `FieldError` if you have not configured `requiredFields` or a corresponding validator.

## 2. DataBinder and participating classes

### 2.1. APIs to know

| API | Role |
| --- | --- |
| `DataBinder` | Configures and performs property binding and validation |
| `MutablePropertyValues` | Input property-name/value pairs, similar to form parameters |
| `DataBinder#bind(PropertyValues)` | Binds data onto the target and may record binding errors |
| `DataBinder#setRequiredFields(...)` | Declares properties that must be present during binding |
| `DataBinder#setAllowedFields(...)` | Restricts which properties may be bound |
| `DataBinder#setValidator(...)` | Sets the validator applied when `validate()` is explicitly called |
| `DataBinder#validate()` | Runs the registered validator and appends errors |
| `DataBinder#getBindingResult()` | Reads the `BindingResult` holding errors and field state |
| `BindingResult#getFieldError("quantity")` | Retrieves the first error for the specified field |
| `FieldError#getCode()` | Retrieves the base error code, e.g., `typeMismatch` |
| `FieldError#getCodes()` | Retrieves the code array for i18n, from most specific to most general |
| `FieldError#isBindingFailure()` | Distinguishes binding/conversion errors from validation rejections |
| `BindingResult#getSuppressedFields()` | Names of input properties blocked by the binder's field restrictions |

`DataBinder` resides in `spring-context` and works outside a web environment. `WebDataBinder` extends it for Spring MVC, so testing `DataBinder` directly is a great way to verify the **core mechanism** without booting Spring Boot.

### 2.2. Basic processing flow

```text
new OrderForm()
      |
      v
new DataBinder(orderForm, "orderForm")
      |
      +-- setAllowedFields("code", "quantity")
      +-- setRequiredFields("code", "quantity")
      +-- setValidator(new OrderValidator())
      |
      v
MutablePropertyValues: code="OR-101", quantity="3"
      |
      v
binder.bind(values)
      |
      +-- drop disallowed fields => suppressedFields
      +-- check required fields => FieldError("required")
      +-- convert types and call setters => possible FieldError("typeMismatch")
      |
      v
binder.validate()   <-- SEPARATE STEP
      |
      +-- run Spring Validator / record FieldError from rejectValue()
      |
      v
BindingResult: field errors, global errors, suppressed fields
```

This is the flow for **property binding onto a JavaBean with setters**. Since Spring 6.1, `DataBinder` also supports constructor binding via `construct(...)`, though it constructs targets and evaluates parameters differently from `bind(PropertyValues)`.

No Spring MVC controller is needed to run the JUnit tests in section 7.

## 3. First test: valid data

Suppose the object is:

```java
public class OrderForm {
    private String code;
    private Integer quantity;

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

This is a JavaBean fragment (each public class needs its own file); the complete runnable example uses a nested static class inside `DataBinderDemo.java`.

Create data and bind:

```java
OrderForm form = new OrderForm();
DataBinder binder = new DataBinder(form, "orderForm");

MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "OR-101");
values.add("quantity", "3");

binder.bind(values);

BindingResult result = binder.getBindingResult();
System.out.println(form.getQuantity()); // 3
System.out.println(result.hasErrors()); // false
```

What to understand:

- `MutablePropertyValues` carries `quantity` as a **String**.
- `OrderForm.quantity` is an **Integer**.
- Spring uses the available type conversion/property editors in `DataBinder` to assign the Integer.
- A newly created binder does not automatically run Bean Validation just because the class has `@Min` or `@NotNull`. You must configure and invoke validation through the appropriate path.

Tests should verify the **target Java type**, not just compare strings: `assertEquals(Integer.valueOf(3), form.getQuantity())`. That proves conversion actually happened.

## 4. Testing invalid type: String cannot convert to Integer

Replace `quantity="3"` with `quantity="abc"`:

```java
MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "OR-101");
values.add("quantity", "abc");

binder.bind(values);
FieldError error =
    binder.getBindingResult().getFieldError("quantity");
```

On the default property binding path, Spring records conversion errors into `BindingResult` instead of immediately letting every `TypeMismatchException` escape `bind()`.

Required assertions:

```java
assertNotNull(error);
assertEquals("typeMismatch", error.getCode());
assertTrue(error.isBindingFailure());
assertNull(form.getQuantity());
```

These are JUnit fragments; `binder`, `form`, and static imports must be declared. The runnable version is in section 7.

### 4.1. Why does isBindingFailure() matter?

`FieldError#isBindingFailure()` tells you the error occurred while converting/assigning data onto the target, distinguishing it from errors produced by `errors.rejectValue(...)` inside a validator. With `quantity="abc"`, Spring does not yet have a valid `Integer` for `@Min(1)` or a custom min validator to evaluate.

Common binding errors:

| Scenario | Typical base error code |
| --- | --- |
| Missing required field | `required` |
| Value cannot convert to target type | `typeMismatch` |
| Setter/property method throws an exception | `methodInvocation` |

The actual error code depends on the `BindingErrorProcessor` and `MessageCodesResolver` in use. The names in the table are Spring's defaults. A `FieldError` also has `getCodes()`, an array of codes for localization rather than a single String.

### 4.2. Do not rely on rejected values for business logic

For a type mismatch, `FieldError#getRejectedValue()` can contain the rejected text input. It is helpful for debugging/testing, but should not be blindly logged or returned in HTTP responses because it may contain tokens, emails, account numbers, or sensitive data.

For API error responses, map `typeMismatch` to a stable public error code and a locale-appropriate message.

## 5. Testing missing fields with setRequiredFields

Spring distinguishes **a property absent from the input data** from **a property whose value is null**.

Configuration:

```java
DataBinder binder = new DataBinder(new OrderForm(), "orderForm");
binder.setRequiredFields("code", "quantity");
```

Send only `code`, without `quantity`:

```java
MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "OR-101");

binder.bind(values);

FieldError error =
    binder.getBindingResult().getFieldError("quantity");
```

When `quantity` is listed in `requiredFields` but absent from the bind values, the default binding error processor creates an error with code `required`. The target still has `quantity == null` because no data was available to bind.

**This check happens during binding**, not via Jakarta `@NotNull`, and does not require calling `binder.validate()` to produce `required`.

### 5.1. Missing field without setRequiredFields

Another binder:

```java
DataBinder binder = new DataBinder(new OrderForm(), "orderForm");

MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "OR-101");

binder.bind(values);
```

Without required fields or a validator running, `quantity` can remain `null` while `BindingResult#hasErrors()` is still `false`. This aligns with the mechanism: **omitting a field is not automatically an error** unless the contract requires it.

When you do not configure `requiredFields` but want to reject a missing quantity, you can use:

- `@NotNull`/Jakarta Bean Validation, triggered after binding.
- A custom Spring `Validator`, followed by `binder.validate()`.
- Required argument semantics on web annotations, such as `@RequestParam(required=true)` in MVC; this is a different mechanism from generic `DataBinder`.

### 5.2. "Missing", "empty", and "wrong type" are not synonymous

| Input | Scenario | What to test |
| --- | --- | --- |
| No `quantity` key | Missing property | If `setRequiredFields("quantity")`, check `required` |
| `quantity=""` | Key present with empty string | Result depends on conversion/required processing; test actual behavior |
| `quantity="abc"` | String present but cannot parse as Integer | `typeMismatch` |
| `quantity="0"` | Converts to Integer, but may violate business rule | `binder.validate()` creates `minQuantity` or `@Min` |
| `quantity="3"` | Valid type conversion | Field holds Integer 3 |
| `quantity=null` on target before bind | Initial Java state | Does not mean the client sent null |
| `quantity=" 3 "` | Contains whitespace | Parsing depends on conversion service; test normalization policy |

**Do not assume every empty String always converts to null across all converters.** For HTTP data, empty values are also affected by MVC argument resolvers and converters. This lesson uses explicit presence/absence of keys in tests to avoid confusing missing with blank.

### 5.3. Integer or int?

In form DTOs, use `Integer` instead of primitive `int` when you need to distinguish "no input provided" from "entered 0". With `int`, Java's default value is 0 and can be mistaken for real input.

`@NotNull` has no useful effect on primitives because primitives cannot be null. When designing DTOs and tests, choose data types that match your missing-field semantics.

## 6. Binding differs from validation: two-step testing

A Spring `Validator` can verify that quantity is non-null and at least 1:

```java
public final class OrderValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return OrderForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        OrderForm form = (OrderForm) target;

        if (errors.hasFieldErrors("quantity")) {
            return; // Already has a binding error; avoid noisy business errors.
        }
        if (form.getQuantity() == null) {
            errors.rejectValue("quantity", "requiredByValidator");
        } else if (form.getQuantity() < 1) {
            errors.rejectValue("quantity", "minQuantity");
        }
    }
}
```

This is a fragment; imports for `Validator`, `Errors`, and class `OrderForm` are required. The complete version is in section 7.

Wiring the validator:

```java
binder.setValidator(new OrderValidator());
binder.bind(values);

// After bind: only binding errors exist.
// After validate: semantic validation errors are added.
binder.validate();

BindingResult result = binder.getBindingResult();
```

Case `quantity="0"`:

1. The binder parses `"0"` into Integer 0, so there is no `typeMismatch` error.
2. When `validate()` runs, the validator checks `0 < 1` and calls `errors.rejectValue("quantity","minQuantity")`.
3. `FieldError#getCode()` is `minQuantity`, and `isBindingFailure()` is typically `false` because the validator rejected it rather than a conversion failure.

If you only call `bind()` without calling `validate()`, the `minQuantity` error will not appear automatically in a generic DataBinder.

### 6.1. DataBinder does not run @Valid automatically

In Spring MVC, a controller parameter annotated with `@Valid @ModelAttribute(...)` triggers validation through MVC infrastructure. However, a generic `DataBinder` constructed in a test **is unaware of `@Valid` or a Bean Validation provider** unless you attach a validator and call `validate()`.

If you want to test Jakarta constraints directly, you can use `LocalValidatorFactoryBean` (with a Jakarta Bean Validation provider on the classpath) and call `binder.setValidator(beanValidator); binder.validate();`. That is a broader setup; the runnable sample here uses a plain Spring `Validator` to keep the mechanisms clearly separated.

### 6.2. Avoiding spurious stacked errors

When quantity has an invalid type `"abc"`, `target.quantity` may remain null. If a custom validator sees null and also adds `requiredByValidator`, tests or the API end up with two errors for one cause. That is why the example uses `errors.hasFieldErrors("quantity")` to skip business checks on a field that already failed binding.

That is a **decision of the example's custom validator**, not a behavior automatically applied by every Bean Validation provider. When testing combined flows, define your application's error policy and avoid relying on error object ordering unnecessarily.

## 7. Standalone runnable example: Java 17, Spring Framework 6.2, and JUnit 5

### 7.1. Structure

```text
data-binder-tests/
├── pom.xml
└── src/
    ├── main/java/demo/binding/
    │   └── DataBinderDemo.java
    └── test/java/demo/binding/
        └── DataBinderDemoTest.java
```

There is just one source file and one test file. No Spring Boot, database, or server is needed because the focus is the `DataBinder` API.

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>demo</groupId>
  <artifactId>data-binder-tests</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.8</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.12.2</version>
      <scope>test</scope>
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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Because Spring DataBinder belongs to Spring Framework core/context infrastructure, `spring-context` and its transitive dependencies provide the required classes. JUnit Jupiter is in test scope. Java 17 is the baseline for Spring Framework 6.x.

### 7.3. DataBinderDemo.java

```java
package demo.binding;

import java.util.Arrays;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public class DataBinderDemo {

    public static class OrderForm {
        private String code;
        private Integer quantity;

        public OrderForm() {
        }

        public String getCode() {
            return code;
        }

        public void setCode(String code) {
            this.code = code;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    public static class OrderValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return OrderForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            OrderForm form = (OrderForm) target;

            if (errors.hasFieldErrors("quantity")) {
                return;
            }

            if (form.getQuantity() == null) {
                errors.rejectValue("quantity", "requiredByValidator");
            } else if (form.getQuantity() < 1) {
                errors.rejectValue("quantity", "minQuantity");
            }
        }
    }

    // Each test/case must use a fresh binder and target.
    public static DataBinder newBinder(OrderForm target,
                                       boolean requiredFields) {
        DataBinder binder = new DataBinder(target, "orderForm");

        binder.setAllowedFields("code", "quantity");
        if (requiredFields) {
            binder.setRequiredFields("code", "quantity");
        }
        binder.setValidator(new OrderValidator());

        return binder;
    }

    public static MutablePropertyValues values(
            String code, String quantity) {

        MutablePropertyValues pvs = new MutablePropertyValues();

        if (code != null) {
            pvs.add("code", code);
        }
        if (quantity != null) {
            pvs.add("quantity", quantity);
        }

        return pvs;
    }

    private static String errorCode(
            BindingResult result, String field) {

        FieldError error = result.getFieldError(field);
        return error == null ? "none" : error.getCode();
    }

    private static void validCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        binder.bind(values("OR-101", "3"));
        binder.validate();

        System.out.println(
            "VALID | code=" + target.getCode()
            + " | quantity=" + target.getQuantity()
            + " | errors=" + binder.getBindingResult().getErrorCount());
    }

    private static void wrongTypeCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        binder.bind(values("OR-101", "abc"));

        System.out.println(
            "WRONG_TYPE | quantity=" + target.getQuantity()
            + " | error=" + errorCode(
                binder.getBindingResult(), "quantity"));
    }

    private static void missingRequiredCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        // Do not add the quantity key to MutablePropertyValues.
        binder.bind(values("OR-101", null));

        System.out.println(
            "MISSING_REQUIRED | quantity=" + target.getQuantity()
            + " | error=" + errorCode(
                binder.getBindingResult(), "quantity"));
    }

    private static void missingWithoutRuleCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, false);

        binder.bind(values("OR-101", null));

        System.out.println(
            "MISSING_WITHOUT_RULE | quantity=" + target.getQuantity()
            + " | errors=" + binder.getBindingResult().getErrorCount());

        // Only when validate() is explicitly called does the custom Validator record the error.
        binder.validate();
        System.out.println(
            "MISSING_AFTER_VALIDATE | error=" + errorCode(
                binder.getBindingResult(), "quantity"));
    }

    private static void invalidBusinessCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        binder.bind(values("OR-101", "0"));
        binder.validate();

        System.out.println(
            "SEMANTIC_INVALID | quantity=" + target.getQuantity()
            + " | error=" + errorCode(
                binder.getBindingResult(), "quantity"));
    }

    private static void suppressedFieldCase() {
        OrderForm target = new OrderForm();
        DataBinder binder = newBinder(target, true);

        MutablePropertyValues pvs = values("OR-101", "3");
        pvs.add("role", "ADMIN");

        binder.bind(pvs);

        String[] suppressed =
            binder.getBindingResult().getSuppressedFields();
        Arrays.sort(suppressed);

        System.out.println(
            "SUPPRESSED | fields=" + String.join(",", suppressed)
            + " | errors=" + binder.getBindingResult().getErrorCount());
    }

    public static void main(String[] args) {
        validCase();
        wrongTypeCase();
        missingRequiredCase();
        missingWithoutRuleCase();
        invalidBusinessCase();
        suppressedFieldCase();
    }
}
```

### 7.4. Program design explanation

- `OrderForm` has a default constructor and setters, matching JavaBeans property binding.
- `DataBinderDemo#values(...)` creates a **new MutablePropertyValues** each time to avoid a binder mutating a reused instance.
- `newBinder(...)` lets separate tests toggle `requiredFields`. `setAllowedFields("code","quantity")` blocks fields outside the list.
- `OrderValidator` checks whether `quantity` is null or less than 1 **when validate() is called**, not during `bind()`.
- `wrongTypeCase()` omits `validate()` to confirm `typeMismatch` is purely a binding error.
- `missingRequiredCase()` omits `validate()`: the `required` error comes from binder configuration.
- `missingWithoutRuleCase()` shows that the bind step reports no error for a missing field when required fields are not configured; after `validate()`, `requiredByValidator` appears.
- `suppressedFieldCase()` shows that input `role` is filtered out by the allowlist and appears in suppressed fields **without automatically creating a FieldError**.

### 7.5. Running the program

Requires Java 17+, Maven 3.x, and Maven repository access to download dependencies on the first run. In the directory containing `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java \
  -Dexec.mainClass=demo.binding.DataBinderDemo
```

The `System.out.println` lines from the demo code look like this, excluding Maven/plugin logging:

```text
VALID | code=OR-101 | quantity=3 | errors=0
WRONG_TYPE | quantity=null | error=typeMismatch
MISSING_REQUIRED | quantity=null | error=required
MISSING_WITHOUT_RULE | quantity=null | errors=0
MISSING_AFTER_VALIDATE | error=requiredByValidator
SEMANTIC_INVALID | quantity=0 | error=minQuantity
SUPPRESSED | fields=role | errors=0
```

The `SUPPRESSED` case with `errors=0` is an important security lesson. If an API wants to reject requests carrying fields outside the allowlist, it must **explicitly check `getSuppressedFields()`** and return HTTP 4xx/skip side effects. `hasErrors() == false` does not mean every client-sent input was accepted.

### 7.6. DataBinderDemoTest.java — JUnit 5 tests

```java
package demo.binding;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

class DataBinderDemoTest {

    @Test
    void validInputConvertsStringToInteger() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        binder.bind(DataBinderDemo.values("OR-101", "3"));
        binder.validate();

        assertFalse(binder.getBindingResult().hasErrors());
        assertEquals("OR-101", target.getCode());
        assertEquals(Integer.valueOf(3), target.getQuantity());
    }

    @Test
    void incompatibleTypeCreatesTypeMismatch() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        binder.bind(DataBinderDemo.values("OR-101", "abc"));

        BindingResult result = binder.getBindingResult();
        FieldError error = result.getFieldError("quantity");

        assertNotNull(error);
        assertEquals("typeMismatch", error.getCode());
        assertTrue(error.isBindingFailure());
        assertNull(target.getQuantity());
        assertEquals(1, result.getErrorCount());
    }

    @Test
    void missingConfiguredFieldCreatesRequiredErrorDuringBind() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        binder.bind(DataBinderDemo.values("OR-101", null));

        FieldError error =
            binder.getBindingResult().getFieldError("quantity");

        assertNotNull(error);
        assertEquals("required", error.getCode());
        assertNull(target.getQuantity());
        assertEquals(1, binder.getBindingResult().getErrorCount());
    }

    @Test
    void missingFieldCanBeSilentUntilValidation() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, false);

        binder.bind(DataBinderDemo.values("OR-101", null));
        assertFalse(binder.getBindingResult().hasErrors());

        binder.validate();

        FieldError error =
            binder.getBindingResult().getFieldError("quantity");

        assertNotNull(error);
        assertEquals("requiredByValidator", error.getCode());
        assertFalse(error.isBindingFailure());
    }

    @Test
    void numericValueCanBindButFailSemanticValidation() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        binder.bind(DataBinderDemo.values("OR-101", "0"));
        assertFalse(binder.getBindingResult().hasErrors());

        binder.validate();

        assertEquals(Integer.valueOf(0), target.getQuantity());
        FieldError error =
            binder.getBindingResult().getFieldError("quantity");
        assertNotNull(error);
        assertEquals("minQuantity", error.getCode());
        assertFalse(error.isBindingFailure());
    }

    @Test
    void additionalFieldIsSuppressedAndMustBeCheckedExplicitly() {
        DataBinderDemo.OrderForm target = new DataBinderDemo.OrderForm();
        DataBinder binder = DataBinderDemo.newBinder(target, true);

        MutablePropertyValues input =
            DataBinderDemo.values("OR-101", "3");
        input.add("role", "ADMIN");

        binder.bind(input);

        assertEquals(
            0, binder.getBindingResult().getErrorCount());
        assertEquals(
            1, binder.getBindingResult().getSuppressedFields().length);
        assertEquals(
            "role",
            binder.getBindingResult().getSuppressedFields()[0]);
        assertEquals(Integer.valueOf(3), target.getQuantity());
    }
}
```

The tests need no Spring application context, `@SpringBootTest`, `MockMvc`, or H2. Each test instantiates a fresh target/binder, preventing state from leaking across tests.

### 7.7. Running and reading test results

```bash
mvn -q test
```

On success, Maven returns **exit code 0**. In quiet mode `-q`, do not assume fixed stdout like "6 tests passed"; inspect the XML/TXT reports generated by Surefire in `target/surefire-reports`.

This test suite contains **6 test methods**:

1. Valid binding and conversion.
2. Wrong type creates `typeMismatch`.
3. Missing required field creates `required`.
4. Missing field is not treated as an error until custom validation runs.
5. Numeric value has valid type but violates the `minQuantity` rule.
6. Field outside the allowlist appears in suppressed fields without automatically producing a binding error.

Expected values are explicitly stated in assertions rather than relying on log ordering or exception text.

## 8. Layered testing strategy

### 8.1. DataBinder unit tests (no web server)

Advantages:

- Fast, minimal dependencies, no Spring container needed.
- Separates conversion, missing fields, validator rules, and suppressed fields in a narrow layer.
- Easy to assert `FieldError#getCode()`, `getCodes()`, `getRejectedValue()`, `isBindingFailure()`.
- Easy to create a fresh binder per case, reducing flaky tests.

Limitations: this style of test **does not prove** Spring MVC selected the right controller, invoked `@InitBinder`, or returned the expected HTTP status. It directly tests the binder setup you wrote inside the test.

### 8.2. MVC integration tests

In a Spring Boot MVC project, use `MockMvc` to confirm:

- `@InitBinder("orderForm")` actually applies to the right model attribute.
- `@Valid`/`@Validated` triggers the appropriate validator.
- `BindingResult` sits immediately after the parameter whose errors it captures.
- HTTP body, status, and content type match the API contract.
- Validation/parse failures do not persist data.
- Fields outside the allowlist are rejected according to policy.

Example controller signature:

```java
@PostMapping("/orders")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest().body("EXTRA_FIELDS");
    }
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("INVALID");
    }
    return ResponseEntity.ok("ACCEPT");
}
```

This is an **MVC fragment**, requiring imports and the corresponding classes/configuration. The generic `DataBinder` created in section 7 does not attach itself to a controller simply by naming a method `newBinder`. To make MVC enforce those rules, configure them via `@InitBinder`/MVC binding infrastructure or appropriate validation configuration.

Example `@InitBinder` needed in MVC:

```java
@InitBinder("orderForm")
void initOrderForm(WebDataBinder binder) {
    binder.setAllowedFields("code", "quantity");
    binder.setRequiredFields("code", "quantity");
    binder.addValidators(orderValidator);
}
```

This fragment lives inside the controller, with `orderValidator` as a Spring-managed bean. Use `addValidators` to preserve existing global validators; calling `setValidator` unintentionally can overwrite the default validation list. Once `@InitBinder` is applied, MVC performs binding and triggers validation when requested by argument annotations.

### 8.3. @RequestBody JSON does not follow the same binding path

With:

```java
@PostMapping("/api/orders")
public ResponseEntity<?> submit(
        @Valid @RequestBody OrderRequest body) {
    // ...
    return ResponseEntity.ok().build();
}
```

JSON is decoded via HTTP message converters (usually Jackson), not via property binding from `MutablePropertyValues` in the same way as `@ModelAttribute`. Therefore:

- `DataBinder`'s `setRequiredFields(...)` is not the mechanism governing whether Jackson allows missing JSON fields.
- `@NotNull`/constructor validation on the DTO and Jackson configuration are what need testing for JSON.
- JSON parse errors may raise `HttpMessageNotReadableException` before Bean Validation runs.
- `setAllowedFields(...)` should not be treated as the sole defense against mass assignment over JSON.

Never treat a `DataBinder#bind` unit test as proof for a `@RequestBody` endpoint.

## 9. Which assertions are reliable and which are brittle?

### 9.1. Assert error codes instead of localized default messages

Prefer:

```java
assertEquals("typeMismatch", error.getCode());
assertEquals("required", missingError.getCode());
```

Avoid:

```java
assertEquals(
    "Failed to convert property value of type ...",
    error.getDefaultMessage());
```

The latter is a fragment illustrating a **brittle** assertion, not a guaranteed exact Spring message. Wording can change across Spring versions, `MessageSource`/locales, or custom binding error processors.

If your application actually has a message text contract, test i18n in a dedicated layer with an explicit `MessageSource`/locale.

### 9.2. Assert field, code, and count intentionally

An error can carry a code array:

```text
typeMismatch.orderForm.quantity
typeMismatch.quantity
typeMismatch.java.lang.Integer
typeMismatch
```

That is a **typical example** when the target object name is `orderForm` and the field type is `Integer`. If you configure a different `MessageCodesResolver`, the array can differ. `FieldError#getCode()` usually returns the final base code.

In unit tests that do not depend on detailed code conventions, assert the base code and field name. In i18n-specific tests, test the full `getCodes()` when that is the contract being protected.

### 9.3. Do not depend on error ordering

When a form has multiple errors, use `getFieldErrors()` and group/sort before comparing. Do not assume different validators will always record errors in the exact order a developer expects.

Example:

```java
List<String> codes = result.getFieldErrors().stream()
    .map(e -> e.getField() + ":" + e.getCode())
    .sorted()
    .toList();
```

This is a fragment requiring a `List` import and an existing `result` object. For tests checking a single field, `getFieldError("quantity")` is simpler and clearer.

### 9.4. Assert no side effects on error

In MVC integration tests, beyond HTTP 400 or validation errors, verify that the database/service receives no write commands if the binder has errors or suppressed fields. A system might return the right error while having already mutated a managed JPA entity before checking `BindingResult` — which is why you should bind into DTOs rather than directly into domain entities.

## 10. Extended edge-case scenarios

### 10.1. Sending a key with null value instead of omitting the key

In generic `MutablePropertyValues`, a property can be present with Java `null` as its value:

```java
MutablePropertyValues pvs = new MutablePropertyValues();
pvs.add("code", "OR-101");
pvs.add("quantity", null);
```

This case **differs** from omitting the `quantity` key. Depending on `requiredFields` rules and the binding processor, the result may be treated as missing or converted/assigned as null. To know your app's exact contract, add a separate test rather than guessing from `null` on the target.

### 10.2. Empty strings and whitespace

With `quantity=""` or `quantity="  "`, the conversion service/property editor may convert to null or raise an error depending on target type and configuration. Therefore test them separately:

```java
pvs.add("quantity", "");
pvs.add("quantity", "  ");
```

The two lines above represent **two alternative cases**; do not add both properties to the same `MutablePropertyValues` when aiming for independent tests. In Spring MVC, `StringTrimmerEditor`, formatters, or custom converters can alter the outcome; normalization needs an explicit policy.

### 10.3. Unknown fields and ignoreUnknownFields

By default, the binder can ignore non-existent properties when `ignoreUnknownFields=true`. If you want to detect unexpected input, choose a strategy:

- Use `setAllowedFields(...)` to filter and check `getSuppressedFields()`.
- Consider `setIgnoreUnknownFields(false)` when the contract must block unknown properties; its exception behavior differs from suppressed fields, so test them separately.
- Design minimal request DTOs without sensitive setters.

**Do not equate** "unknown property" with "known property disallowed from binding": the two cases can take different error paths.

### 10.4. Primitive vs wrapper

If `quantity` is `int`, a new target defaults to 0. With `Integer`, an unbound target can remain null. When testing missing fields, know exactly how the target was initialized rather than concluding solely from a `0` in the result.

### 10.5. Nested properties and collections

A form with `address.zipCode` or `items[0].quantity` requires preparing nested objects or considering `autoGrowNestedPaths`, collection limits, allowedFields, and error field paths. When testing:

- Case where nested target is not yet initialized.
- Case where collection index is invalid/oversized.
- Case where a custom converter fails on a nested field.
- Case where a field outside the allowlist appears at a nested path.

Nested paths can expand the mass-assignment surface; do not allow arbitrary binding across the whole object graph.

### 10.6. Declarative/constructor binding

Spring Framework 6.1+ supports `DataBinder#setDeclarativeBinding(true)`, making property binding run only when explicit allowed fields exist; constructor binding still follows its own rules. Tests calling `bind(PropertyValues)` on a JavaBean with setters **do not directly test** `construct(ValueResolver)` on immutable DTOs.

For Java records or input constructors with parameters, write dedicated constructor-binding tests instead of merely turning `OrderForm` into a record and keeping `binder.bind(...)`. A binder created with a `null` target and target type needs `setTargetType(...)` and `construct(...)` per the Spring 6.1+ API.

### 10.7. Testing custom converters/formatters

If you have a custom `Converter<String, OrderId>` or `Formatter<LocalDate>`, configure the `ConversionService`/formatter on the test binder to replicate how MVC parses values. Test valid values, malformed values, boundaries, locales, and null handling. Do not assume a generic binder automatically picks up every custom converter auto-configured by Spring Boot in an MVC ApplicationContext.

## 11. Common testing pitfalls

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `quantity=abc` throws out of the test instead of recording an error | Test invokes converter directly or uses custom binding config | Call `binder.bind(...)` and inspect `BindingResult`; separate pure conversion |
| Missing quantity produces no error | `setRequiredFields` not configured and `validate` not called | Test missing separately, add `requiredFields` or validator |
| Value 0 is not rejected | Conversion succeeded, `validate()` never called | Attach `Validator` and call `validate()` |
| `@NotNull` test does not run on generic binder | Bean Validation provider/validator not configured | Create `LocalValidatorFactoryBean`/initialize provider and call validate |
| Both `typeMismatch` and `requiredByValidator` appear | Validator runs on a field that already failed conversion | Check `errors.hasFieldErrors(field)` if policy requires avoiding duplicates |
| Form primitive int holds 0 even when unsent | Primitive default value | Use `Integer` when missing needs to be represented |
| `getFieldError(...)` returns null and test dereferences it | Field has no error or binder config mismatches | `assertNotNull` before inspecting code |
| English message comparison test fails across locales | Used `getDefaultMessage()` as contract | Assert code; test i18n in a separate layer |
| Added `role` field yet `hasErrors()` is still false | Suppressed fields are not automatically FieldErrors | Inspect `getSuppressedFields()` |
| `@InitBinder` has no effect in plain test | Generic `DataBinder` does not invoke controller annotations | Use MockMvc integration tests |
| JSON endpoint behaves differently from form test | Jackson decoder differs from property binder | Test `@RequestBody`/Jackson separately |
| Reused `MutablePropertyValues` across tests | Binder may filter/modify values list | Create a fresh instance for each bind |
| Error order changes across implementations | Relied on FieldError creation order | Sort or assert by field |
| Calling `validate()` multiple times duplicates errors | Validator is not idempotent or ran repeatedly | Control validate call count, create a fresh binder per test |
| Bound directly onto entity before checking errors | State may mutate before error inspection | Use a DTO and block saving/flushing on error |

## 12. Checklist before concluding tests pass

1. Have a JavaBean target with getters/setters or an explicitly configured binding mode.
2. Each case creates a fresh target and DataBinder; never share mutable state.
3. Input `MutablePropertyValues` is created fresh for every bind.
4. For successful conversion, assert **target value and type**, not just `hasErrors() == false`.
5. For invalid type, assert field, code `typeMismatch`, and `isBindingFailure()`.
6. For missing required fields, assert `setRequiredFields` was configured **before** `bind()`.
7. Include a missing-field test **without** required configured to understand the difference.
8. For semantic violations, assert the error only appears after calling `validate()`.
9. Verify business logic does not proceed when binding/validation errors exist.
10. Check `getSuppressedFields()` and do not treat `hasErrors()==false` as accepting all input.
11. For MVC integration, verify `@InitBinder` scope, `@ModelAttribute` name, `BindingResult` placement, and status.
12. For `@RequestBody` JSON, test decoding/constraints separately; do not rely on `MutablePropertyValues`.
13. Do not serialize `FieldError#getRejectedValue()` into public HTTP responses.
14. Do not assert localized error messages in core binder unit tests when the goal is only the error code.
15. Run the Maven test suite with exit code 0; when reviewing detailed results, inspect `target/surefire-reports`.

## 13. Summary

**`DataBinder#bind(...)`** handles binding/conversion and can record `typeMismatch` or `required` into `BindingResult`. **`setRequiredFields(...)`** determines which fields must be present during property binding, while **`DataBinder#validate()`** is a separate step to apply registered Spring `Validator` instances.

A solid test suite does not lump all failures into "invalid input", but separates at least: **valid values**, **wrong type**, **missing required field**, **missing without rule**, **valid type but invalid business validation**, and **fields outside the allowlist**. The Java 17/JUnit 5 sample in section 7 creates a fresh binder per case, asserts stable error codes, and has no HTTP/web server dependencies.

When extending to Spring MVC, remember to verify the `@InitBinder`/`@Valid`/`BindingResult` wiring and HTTP response via MockMvc. Never use binder unit tests as a substitute for integration or security tests.

## Official references

- Spring Framework 6.2 — Validation, Data Binding and Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/core/validation.html
- Spring Framework 6.2 — Data Binding, constructor vs property binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html
- Spring Framework 6.2 — Configuring DataBinder and Validator: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 Javadoc — `DataBinder`, `setRequiredFields`, `bind`, `validate`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 Javadoc — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.2 Javadoc — `FieldError`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 Javadoc — `DefaultBindingErrorProcessor`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/DefaultBindingErrorProcessor.html
- Spring Framework 6.2 — `@InitBinder` in MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — `@ModelAttribute` and security: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/