# No Suitable Converter Found or Converter Not Registered in Spring Framework

## 1. Diagnostic Goal

In Spring Framework, much of the data at the application boundary starts out as **strings**: path variables, query parameters, form fields, or configuration values. To pass them into Java objects, the framework must know how to convert from a **source type** to a **target type**.

For example, an API receives:

```text
GET /tickets/TKT-42
```

In the controller:

```java
@GetMapping("/tickets/{key}")
public String detail(@PathVariable TicketKey key) {
    return "Ticket " + key.value();
}
```

This is an illustrative snippet. `TicketKey` is an application value object, not a built-in Spring type. To map the string `"TKT-42"` into `TicketKey(42)`, Spring needs a conversion applicable in the **ConversionService that this processing flow actually uses**.

If the conversion does not exist or is not registered in the right place, binding can fail. If a converter is present yet the submitted value has the wrong format, an error still occurs—but that is **a different cause**.

This article accurately distinguishes and diagnoses:

1. **No conversion path exists** for the source/target type pair—`ConverterNotFoundException` may occur.
2. **A converter exists, yet the content is invalid**—`ConversionFailedException` may occur.
3. **Conversion error collected by DataBinder into a FieldError**—commonly `typeMismatch`.
4. **Converter was written but never registered, or registered on the wrong ConversionService**.
5. **Converter was registered with the wrong generic source/target, wrong scope, or shadowed by another Jackson/Formatter/PropertyEditor pipeline**.

You will get a standalone runnable **Java 17 + Spring Framework 6.2 + Maven + JUnit 5** example, followed by how to integrate a converter properly into Spring MVC and a symptom-based diagnostic checklist.

## 2. Core Components

Spring Core defines a dedicated type conversion system around the `ConversionService` interface. For straightforward one-way conversions, developers typically implement `Converter<S,T>`.

| API / class | Role |
| --- | --- |
| `ConversionService` | Queries `canConvert(...)` and executes `convert(...)` |
| `Converter<S,T>` | Contract to convert an object of type S into type T |
| `ConverterRegistry` | Registers converters or converter factories |
| `GenericConversionService` | Extensible ConversionService capable of managing a registry |
| `DefaultConversionService` | Includes common converters, such as String ↔ numbers, enums, collections |
| `FormattingConversionService` | Adds `Formatter`, parser/printer, and formatting support |
| `Formatter<T>` | Converts text ↔ values possibly depending on `Locale` |
| `ConverterFactory<S,R>` | Creates converters for a family of target types |
| `GenericConverter` | Handles broader type pairs using `TypeDescriptor` |
| `ConditionalGenericConverter` | Applies only when type metadata/conditions match |
| `DataBinder` / `WebDataBinder` | Binds input values onto properties or a target object |
| `BindingResult` / `FieldError` | Stores binding/validation errors instead of always throwing exceptions |
| `WebMvcConfigurer#addFormatters` | Registers converters/formatters for Spring MVC infrastructure |

**The condition for a converter to be invoked is not merely "the class exists in source code."** It must exist in the registry of the right ConversionService, the type pair must match, and the processing path must actually go through that registry.

## 3. Distinguishing the Three Most Easily Confused Errors

### 3.1. `ConverterNotFoundException`: No Conversion Path

Scenario:

```java
DefaultConversionService cs = new DefaultConversionService();
TicketKey result = cs.convert("TKT-42", TicketKey.class);
```

This is a fragment; `TicketKey` is defined in the sample program below. Assuming there is no default converter or eligible factory/constructor to build `TicketKey` from String, `convert(...)` throws:

```text
org.springframework.core.convert.ConverterNotFoundException
```

This exception describes the requested **sourceType** and **targetType** pair, helping trace which converter is missing.

Check:

- Does `cs.canConvert(String.class, TicketKey.class)` return `false`?
- Does a `Converter<String,TicketKey>` exist?
- Was `registry.addConverter(...)` or equivalent Spring configuration called?
- Are you using **the exact service instance** where the converter was registered?
- Is the actual Java type received `String`, and is the actual target type `TicketKey`?

### 3.2. `ConversionFailedException`: Converter Selected, Yet Conversion Failed

When the converter is registered but the input is malformed:

```java
cs.addConverter(new StringToTicketKeyConverter());
cs.convert("BAD-42", TicketKey.class);
```

A converter should throw `IllegalArgumentException` for invalid input per its contract. The conversion infrastructure may wrap that exception in `ConversionFailedException` with the inner cause.

Here `canConvert(String.class,TicketKey.class)` usually returns **true**, yet `convert(...)` still fails. **`canConvert` only asserts that a converter exists for the types, not that every concrete value will convert successfully.**

### 3.3. `FieldError`/`typeMismatch`: Binding Collects Errors

When form input is bound onto an object via `DataBinder`, type conversion failures are normally collected into `BindingResult`:

```java
FieldError error =
    binder.getBindingResult().getFieldError("ticketKey");

String code = error.getCode(); // Usually "typeMismatch".
boolean bindingFailure = error.isBindingFailure();
```

This is a fragment; `binder` must be created/configured beforehand. In a controller using `@ModelAttribute`, you normally observe a `FieldError` or MVC binding error rather than `ConverterNotFoundException` surfacing directly to the REST response layer.

Therefore, do not rely on a single exception message string as the sole identifier. Look at **which layer** the error originates from:

| Call site | Scenario | Signal |
| --- | --- | --- |
| Direct `conversionService.convert(...)` | Missing converter | `ConverterNotFoundException` |
| Direct `conversionService.convert(...)` | Converter present, bad data | `ConversionFailedException` |
| `DataBinder#bind(...)` | Property conversion failed | `BindingResult` has `typeMismatch` |
| MVC `@PathVariable`/`@RequestParam` scalar | Resolver could not convert | Possibly `MethodArgumentTypeMismatchException`, usually HTTP 400 |
| MVC `@ModelAttribute` | Property could not be parsed | `BindingResult` / argument binding error |
| MVC `@RequestBody` JSON | Jackson could not decode JSON | Typically `HttpMessageNotReadableException` |
| Spring Boot `@ConfigurationProperties` | Config binding failed | Boot Binder/BindException errors depending on path |

The outermost exception name may vary with wrapper classes, handlers, versions, or configuration. When diagnosing, follow the **cause chain** and identify the exact source/target types.

## 4. Why Is the Converter Not Found Automatically?

### 4.1. Spring Has Default Converters, Not Arbitrary Domain Types

`DefaultConversionService` supports many common conversions, for instance:

```java
DefaultConversionService cs = new DefaultConversionService();

Integer quantity = cs.convert("3", Integer.class);
Boolean enabled = cs.convert("true", Boolean.class);
```

However, `TicketKey`, `CustomerCode`, `MoneyAmount`, `TenantKey`, or a specialized value object needs its own strategy unless a fallback converter applies.

Spring has fallback mechanisms such as converting via an eligible factory method or constructor in certain cases. Thus **not every custom type strictly requires a hand-written converter**. Still, relying implicitly on heuristics can create brittle coupling; an explicit converter is easier to test and control formatting.

### 4.2. A Bean Existing Does Not Mean It Is Registered

Suppose you write:

```java
public final class StringToTicketKeyConverter
        implements Converter<String, TicketKey> {
    // ...
}
```

The Java compiler knows the class, but the registry does not automatically contain it in a program created with `new DefaultConversionService()`. You must call:

```java
cs.addConverter(new StringToTicketKeyConverter());
```

In Spring MVC, register it in `WebMvcConfigurer#addFormatters(FormatterRegistry)`. A converter annotated with `@Component` may be auto-detected in some Boot contexts/auto-configurations, but **never assume** it automatically appears in every `ConversionService` across MVC, bean binding, and Spring Boot configuration binding.

### 4.3. Registered on the Wrong Service Instance

Example:

```java
DefaultConversionService first = new DefaultConversionService();
DefaultConversionService second = new DefaultConversionService();

first.addConverter(new StringToTicketKeyConverter());

System.out.println(
    first.canConvert(String.class, TicketKey.class)); // true
System.out.println(
    second.canConvert(String.class, TicketKey.class)); // false
```

This is a fragment of the later example. Registering on `first` does not modify `second`. A `DataBinder` or MVC argument resolver using `second` still lacks the converter, even though a unit test running against `first` passes.

### 4.4. Registered on a Layer That Does Not Use That Converter

In Spring Boot, distinguish:

- **MVC FormattingConversionService** for path/query/form binding.
- **Application/property configuration binding** for `application.properties`/`@ConfigurationProperties`, which has a separate conversion strategy and registration point.
- **JavaBean property binding** if the application creates a `DataBinder` manually and passes its own service.
- **Jackson HTTP message converters** for `@RequestBody` JSON payloads.

A converter registered for MVC is not guaranteed to be used by Boot Binder; a custom Jackson deserializer is not a `Converter<String,TicketKey>` understood automatically by `DataBinder`.

## 5. Eight-Step Diagnostic Workflow

### Step 1 — Identify Where the Error Is Thrown

Record the processing path: direct convert, `@PathVariable`, `@RequestParam`, `@ModelAttribute`, `@RequestBody`, or `@ConfigurationProperties`. Do not start by adding converters everywhere.

Example:

```text
GET /tickets/TKT-42
    -> @PathVariable TicketKey
    -> MVC ConversionService
    -> Converter<String, TicketKey>
```

Unlike:

```text
POST /tickets
Content-Type: application/json
{"key": {"value": 42}}
    -> Jackson deserialization
    -> TicketRequest JSON fields
```

### Step 2 — Record the Exact Type Pair

Check:

```java
conversionService.canConvert(
    String.class, TicketKey.class);
```

In some cases the target type is `List<TicketKey>`, `Optional<TicketKey>`, or a field with a formatting annotation, where plain `Class` is insufficient. Use the `canConvert(TypeDescriptor, TypeDescriptor)` overload to account for generic metadata or annotations when needed.

If `sourceType` is `Integer` while the converter was written for `String`, naturally it may not match.

### Step 3 — Inspect the Actual Registry

Verify the converter was added to **the registry of the ConversionService used by the active flow**:

```java
registry.addConverter(new StringToTicketKeyConverter());
```

If registration code sits in a `@Configuration` class:

- Is the class within the application's component scan/imports?
- Is the `WebMvcConfigurer` bean actually created?
- Does `addFormatters` run during MVC initialization?
- Is there a second MVC configuration or `@EnableWebMvc` altering auto-configuration?

### Step 4 — Distinguish Missing Converter from Parsing Failure

Test two questions:

```java
boolean supported = cs.canConvert(
    String.class, TicketKey.class);

TicketKey key = cs.convert(
    "TKT-42", TicketKey.class);
```

- `supported=false`: check registration/source/target.
- `supported=true` yet conversion fails: check parser, pattern, null/blank, locale, overflow, and exception cause.

### Step 5 — Check Other Conversion Paths

- Does `String → Integer` work properly?
- Is `String → TicketKey` affected by a legacy fallback constructor/factory?
- Was another converter registered after or before for the same type pair?
- Is a local `Formatter<T>` or `PropertyEditor` on the binder affecting the result?
- Is the request going through Jackson instead of WebDataBinder?

When a new converter replaces an older mapping, include regression tests for both valid and invalid values.

### Step 6 — Separate Binding Errors from Validation Errors

If a form has:

```java
@NotNull
private TicketKey ticketKey;
```

`@NotNull` checks only **the value once created**; it does not teach Spring how to turn `"TKT-42"` into `TicketKey`. If conversion fails, you may get `typeMismatch` before the constraint even has a meaningful value to evaluate.

In a standalone `DataBinder`, `bind(...)` and `validate()` are two separate steps. Do not expect `@Valid` to run automatically when simply creating a binder in a unit test.

### Step 7 — Check How Errors Are Presented at the HTTP Boundary

In `@ControllerAdvice`, distinguish:

- Bad path/query value → return HTTP 400 with a stable error code.
- Form field type failure → map `FieldError.getCode()` / `BindingResult`.
- Malformed JSON body → handle `HttpMessageNotReadableException`.
- Never return raw stack traces, raw rejected values, tokens, or internal class names to clients.

A normal client conversion error should not turn into HTTP 500 simply because you caught `Exception.class` too broadly without classification.

### Step 8 — Write Regression Tests

At minimum cover:

1. `canConvert=false` before registration.
2. `ConverterNotFoundException` when calling `convert` directly in the missing case.
3. `canConvert=true` after registration.
4. Converting `"TKT-42"` to `TicketKey(42)`.
5. Malformed value producing `ConversionFailedException`.
6. `DataBinder` reporting `typeMismatch` when unable to convert.
7. `DataBinder` succeeding with the service that registered the converter.
8. Another ConversionService not picking up the registration.
9. Missing required field yielding `required` (when `setRequiredFields` is used), **not** missing converter.
10. MVC integration test ensuring `addFormatters` ran in the real context.

## 6. Designing a Clean Converter: Short, Clear, Thread-Safe

Value object:

```java
public record TicketKey(long value) {}
```

We intentionally **omit** a constructor accepting `String` or static `valueOf(String)` / `of(String)` so Spring has no built-in convenience path from text to this type by default.

Converter:

```java
public final class StringToTicketKeyConverter
        implements Converter<String, TicketKey> {

    private static final Pattern FORMAT =
        Pattern.compile("TKT-[0-9]{1,5}");

    @Override
    public TicketKey convert(String source) {
        if (!FORMAT.matcher(source).matches()) {
            throw new IllegalArgumentException(
                "Ticket key must match TKT-<1..5 digits>");
        }
        return new TicketKey(
            Long.parseLong(source.substring(4)));
    }
}
```

This is a fragment extracted from the full program in Section 9. `Converter#convert(S)` is called with a **non-null** source under Spring's default contract; do not mutate input or read request state. `Pattern` can be reused safely; a new `Matcher` is created per call.

Parsing rules in the example:

| Input | Result |
| --- | --- |
| `TKT-42` | TicketKey with `value=42` |
| `TKT-00042` | TicketKey with `value=42` — leading zeros are lost in numeric form |
| `TKT-0` | TicketKey with `value=0` per regex, unless forbidden by domain |
| `TKT-12345` | Valid, value 12345 |
| `TKT-123456` | Invalid because over five digits |
| `TKT-abc` | Invalid because not digits |
| `tkt-42` | Invalid because rule is case-sensitive |
| `BAD-42` | Wrong prefix |
| `" TKT-42 "` | Invalid because example does not auto-trim |

If leading zeros in an ID carry business meaning, do **not** store it as a `long` like this demo. Use a String value object with explicit canonicalization.

Do not write a converter that silently returns `null` for every malformed value: that can turn "invalid input" into "missing field" and hide the cause. Throw `IllegalArgumentException` or an appropriate unchecked exception so Spring produces a diagnosable conversion error.

## 7. Registering the Converter in the Right Place

### 7.1. In a Plain Java Program

```java
DefaultConversionService cs = new DefaultConversionService();
cs.addConverter(new StringToTicketKeyConverter());
TicketKey key = cs.convert("TKT-42", TicketKey.class);
```

Just use one service consistently. Do not add to `DefaultConversionService.getSharedInstance()` because that accessor is meant for general read-only fallback; create a dedicated instance for your application/tests.

### 7.2. In Spring MVC / Spring Boot

An explicit MVC configuration:

```java
package demo.web;

import demo.ConversionDebugLab.StringToTicketKeyConverter;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToTicketKeyConverter());
    }
}
```

This is an **illustrative Spring MVC file**, not part of the plain Java program in Section 9. In Spring Boot, ensure `WebMvcConfigurer` is scanned by the app (or imported into the context). Normally **there is no need to add `@EnableWebMvc`** in Boot just to register a converter; `@EnableWebMvc` can alter Boot's default MVC configuration.

Illustrative controller:

```java
package demo.web;

import demo.ConversionDebugLab.TicketKey;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TicketController {

    @GetMapping("/tickets/{key}")
    public String get(@PathVariable("key") TicketKey key) {
        return "TICKET:" + key.value();
    }
}
```

With the converter configuration above and `GET /tickets/TKT-42`, the method receives `TicketKey(42)` and returns `TICKET:42`. With `GET /tickets/BAD-42`, argument conversion fails and MVC normally returns HTTP 400. **This is an integration fragment**: it requires a full Spring Boot Web app, scanned dependencies/controllers, and HTTP tests.

### 7.3. `@InitBinder` for Narrow Scope

If a rule applies only to one controller/form and you want control close to its usage, you can configure `WebDataBinder` inside `@InitBinder`:

```java
@InitBinder("ticketForm")
void customize(WebDataBinder binder) {
    // Example: binder.registerCustomEditor(
    //     TicketKey.class, new TicketKeyEditor());
}
```

This is a snippet showing the **extension point**, not a full editor declaration. A `PropertyEditor` is typically a stateful object created per binder/request and should not be shared arbitrarily across threads. For rules reusable across endpoints, `Converter<String,TicketKey>` + `WebMvcConfigurer#addFormatters` is usually cleaner.

**Important:** `DataBinder#setConversionService(...)` can only be set once on a binder when no conversion service is set yet; in MVC, use the official configuration infrastructure rather than trying to overwrite an active binder's ConversionService.

### 7.4. When to Use `Formatter` Instead of `Converter`?

Use `Converter<String,TicketKey>` when parsing **is locale-independent**. Use `Formatter<T>` when text parsing/printing requires `Locale`, such as dates, currencies, or decimal numbers.

```java
public final class PriceFormatter implements Formatter<BigDecimal> {

    @Override
    public BigDecimal parse(String text, Locale locale)
            throws ParseException {
        // Parse according to the application's specific locale policy.
        throw new UnsupportedOperationException(
            "Only an API-shape example");
    }

    @Override
    public String print(BigDecimal object, Locale locale) {
        return object.toPlainString();
    }
}
```

This is a **signature-illustration snippet**, with an intentional exception and not a complete formatter. Do not add this class to the runnable program in Section 9; its purpose is to show that `parse`/`print` receive `Locale`.

For standard dates and times, before writing your own formatter, check `@DateTimeFormat`, `@NumberFormat`, and the formatters Spring MVC already registers. When a format annotation is placed on a property, `TypeDescriptor` carries annotation metadata affecting parser selection.

### 7.5. When to Use `ConverterFactory` / `GenericConverter`?

- `ConverterFactory<S,R>` fits when one conversion produces multiple target subtypes, such as an enum family.
- `GenericConverter` fits when handling multiple source/target pairs or needing `TypeDescriptor`.
- `ConditionalGenericConverter` applies only if the target type or annotations meet certain conditions.

Do not jump immediately to `GenericConverter` simply because you do not know why a simple `Converter` has not run yet. First verify the generic type pair and registry.

## 8. Spring Boot Specifics

### 8.1. Spring MVC Differs from `@ConfigurationProperties`

Spring Boot documentation emphasizes that the MVC conversion service **differs** from the conversion service used to bind `application.properties` and `application.yaml`. Therefore:

```java
@ConfigurationProperties(prefix = "tickets")
public record TicketSettings(TicketKey defaultKey) {}
```

This is a fragment; for Boot Binder to understand `tickets.default-key=TKT-42`, the converter must be registered through the appropriate configuration-properties binding mechanism, such as `@ConfigurationPropertiesBinding` in a proper configuration or a custom `ConversionService` used by Boot Binder.

A converter registered via `WebMvcConfigurer#addFormatters` only covers the MVC conversion path and **does not automatically cover** Boot configuration binding. Do not confuse an MVC unit test with a `@ConfigurationProperties` test.

### 8.2. The `conversionService` Bean and Boot Auto-Configuration

A bean named `conversionService` can affect conversion in the application context, yet creating a fresh one and replacing all default converters carelessly can break conversions that previously worked (String ↔ numbers, dates/times, collections...).

When you only need to add a converter for MVC, **use `addFormatters`**. When you need a custom application `ConversionService`, start from an implementation with default converters and **add** the needed rules; do not replace it with an empty `GenericConversionService` without understanding the consequences.

### 8.3. `@Component` Is Not Proof MVC Picked It Up

In some Boot configurations, custom converter beans are discovered and added to the registry automatically. In other setups, component scanning, bean lifecycle, or a separate conversion service can still leave you with `typeMismatch`.

Therefore, to diagnose reliably, **test the real MVC context** with MockMvc/integration tests. Never assume "it has `@Component` so it must be running."

## 9. Complete Project: Java 17 + Maven + Spring 6.2 + JUnit 5

This lab runs **without Spring Boot** to clearly isolate registry behavior, conversion exceptions, and binding errors.

### 9.1. File Structure

```text
converter-debug-lab/
├── pom.xml
└── src/
    ├── main/java/demo/ConversionDebugLab.java
    └── test/java/demo/ConversionDebugLabTest.java
```

There is no database, REST endpoint, or required config file. The converter is registered **manually** inside each test to compare both states.

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>demo</groupId>
  <artifactId>converter-debug-lab</artifactId>
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

`spring-context` brings in Spring Core and Beans required for conversion and `DataBinder`. JUnit Jupiter is in test scope only. Java 17 is compatible with Spring Framework 6.

### 9.3. `ConversionDebugLab.java`

```java
package demo;

import java.util.regex.Pattern;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConverterNotFoundException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class ConversionDebugLab {

    // No String constructor/static valueOf/of/from(String).
    public record TicketKey(long value) {
    }

    public static final class StringToTicketKeyConverter
            implements Converter<String, TicketKey> {

        private static final Pattern FORMAT =
            Pattern.compile("TKT-[0-9]{1,5}");

        @Override
        public TicketKey convert(String source) {
            if (!FORMAT.matcher(source).matches()) {
                throw new IllegalArgumentException(
                    "Ticket key must match TKT-<digits>");
            }
            return new TicketKey(
                Long.parseLong(source.substring(4)));
        }
    }

    public static final class TicketForm {

        private TicketKey ticketKey;
        private Integer quantity;

        public TicketForm() {
        }

        public TicketKey getTicketKey() {
            return ticketKey;
        }

        public void setTicketKey(TicketKey ticketKey) {
            this.ticketKey = ticketKey;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    // Helper used in main and JUnit: creates a fresh DataBinder
    // and attaches the passed-in ConversionService.
    public static BindingResult bind(
            DefaultConversionService conversionService,
            TicketForm target,
            String keyText,
            String quantityText) {

        DataBinder binder = new DataBinder(
            target, "ticketForm");

        binder.setConversionService(conversionService);
        binder.setAllowedFields("ticketKey", "quantity");

        MutablePropertyValues input =
            new MutablePropertyValues();

        if (keyText != null) {
            input.add("ticketKey", keyText);
        }

        if (quantityText != null) {
            input.add("quantity", quantityText);
        }

        binder.bind(input);
        return binder.getBindingResult();
    }

    private static String errorCode(
            BindingResult result, String field) {

        FieldError error = result.getFieldError(field);
        return error == null ? "none" : error.getCode();
    }

    public static void main(String[] args) {

        DefaultConversionService service =
            new DefaultConversionService();

        // 1. Converter does not exist on this service instance yet.
        System.out.println(
            "BEFORE_CAN_CONVERT=" + service.canConvert(
                String.class, TicketKey.class));

        try {
            service.convert("TKT-42", TicketKey.class);
        } catch (ConverterNotFoundException ex) {
            System.out.println(
                "BEFORE_EXCEPTION="
                + ex.getClass().getSimpleName());
        }

        TicketForm before = new TicketForm();
        BindingResult beforeResult = bind(
            service, before, "TKT-42", "3");

        System.out.println(
            "BEFORE_BIND_ERROR="
            + errorCode(beforeResult, "ticketKey"));

        // 2. Register converter on the right instance.
        service.addConverter(
            new StringToTicketKeyConverter());

        System.out.println(
            "AFTER_CAN_CONVERT=" + service.canConvert(
                String.class, TicketKey.class));

        TicketKey key = service.convert(
            "TKT-42", TicketKey.class);

        System.out.println(
            "AFTER_CONVERT_VALUE=" + key.value());

        TicketForm form = new TicketForm();
        BindingResult afterResult = bind(
            service, form, "TKT-42", "3");

        System.out.println(
            "AFTER_BIND_VALUE=" + form.getTicketKey().value()
            + ",quantity=" + form.getQuantity()
            + ",errors=" + afterResult.getErrorCount());

        // 3. Converter exists, but input cannot be parsed.
        try {
            service.convert("BAD-42", TicketKey.class);
        } catch (ConversionFailedException ex) {
            System.out.println(
                "INVALID_EXCEPTION="
                + ex.getClass().getSimpleName());
        }

        TicketForm invalid = new TicketForm();
        BindingResult invalidResult = bind(
            service, invalid, "BAD-42", "3");

        System.out.println(
            "INVALID_BIND_ERROR="
            + errorCode(invalidResult, "ticketKey"));

        // 4. Another ConversionService still has no registration.
        DefaultConversionService independent =
            new DefaultConversionService();

        System.out.println(
            "OTHER_INSTANCE_CAN_CONVERT="
            + independent.canConvert(
                String.class, TicketKey.class));
    }
}
```

### 9.4. How the Program Demonstrates the Errors

- `TicketKey` is a record with a canonical `long` constructor and **no String constructor**; custom String-to-TicketKey conversion must be registered.
- Before registration, `service.canConvert(String.class,TicketKey.class)` is false.
- Calling `convert` directly without a converter demonstrates `ConverterNotFoundException`.
- Binding a form with that service collects the conversion failure into a `FieldError` with default code `typeMismatch`.
- `service.addConverter(...)` equips the service with the new type pair; both direct `convert` and `DataBinder` using **the same service** begin working.
- The converter throws `IllegalArgumentException` for `BAD-42`; calling `convert` directly produces `ConversionFailedException`, while form binding records `typeMismatch`.
- `DefaultConversionService independent` does not inherit the other instance's registration.

### 9.5. Run Commands

In the `converter-debug-lab` directory, requiring Java 17+ and Maven 3.x:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java \
  -Dexec.mainClass=demo.ConversionDebugLab
```

Lines from `System.out.println` of the program (excluding Maven logging):

```text
BEFORE_CAN_CONVERT=false
BEFORE_EXCEPTION=ConverterNotFoundException
BEFORE_BIND_ERROR=typeMismatch
AFTER_CAN_CONVERT=true
AFTER_CONVERT_VALUE=42
AFTER_BIND_VALUE=42,quantity=3,errors=0
INVALID_EXCEPTION=ConversionFailedException
INVALID_BIND_ERROR=typeMismatch
OTHER_INSTANCE_CAN_CONVERT=false
```

This is the expected output based on the code and Spring 6.2 API contract; in real usage, run the command to verify your environment, Maven versions, and configuration. Do **not** assert `exception.getMessage()` as a fixed stdout line because wording can vary across versions.

### 9.6. `ConversionDebugLabTest.java`

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConverterNotFoundException;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

class ConversionDebugLabTest {

    private static DefaultConversionService freshWithConverter() {
        DefaultConversionService service =
            new DefaultConversionService();

        service.addConverter(
            new ConversionDebugLab.StringToTicketKeyConverter());

        return service;
    }

    @Test
    void absentConverterReportsNotFound() {
        DefaultConversionService service =
            new DefaultConversionService();

        assertFalse(service.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));

        assertThrows(
            ConverterNotFoundException.class,
            () -> service.convert(
                "TKT-42",
                ConversionDebugLab.TicketKey.class));
    }

    @Test
    void defaultServiceStillConvertsBuiltInNumbers() {
        DefaultConversionService service =
            new DefaultConversionService();

        assertEquals(
            Integer.valueOf(3),
            service.convert("3", Integer.class));

        assertFalse(service.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));
    }

    @Test
    void missingConverterBecomesBindingTypeMismatch() {
        DefaultConversionService service =
            new DefaultConversionService();

        var target = new ConversionDebugLab.TicketForm();
        BindingResult result = ConversionDebugLab.bind(
            service, target, "TKT-42", "3");

        FieldError error = result.getFieldError("ticketKey");

        assertNotNull(error);
        assertEquals("typeMismatch", error.getCode());
        assertTrue(error.isBindingFailure());
        assertNull(target.getTicketKey());
        assertEquals(Integer.valueOf(3), target.getQuantity());
    }

    @Test
    void registrationMakesCorrectTypeConvertible() {
        DefaultConversionService service = freshWithConverter();

        assertTrue(service.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));

        var converted = service.convert(
            "TKT-42",
            ConversionDebugLab.TicketKey.class);

        assertNotNull(converted);
        assertEquals(42L, converted.value());
    }

    @Test
    void registeredConverterStillRejectsBadInput() {
        DefaultConversionService service = freshWithConverter();

        ConversionFailedException error = assertThrows(
            ConversionFailedException.class,
            () -> service.convert(
                "BAD-42",
                ConversionDebugLab.TicketKey.class));

        assertNotNull(error.getCause());
        assertTrue(error.getCause()
            instanceof IllegalArgumentException);
    }

    @Test
    void binderUsesRegisteredConversionService() {
        DefaultConversionService service = freshWithConverter();
        var target = new ConversionDebugLab.TicketForm();

        BindingResult result = ConversionDebugLab.bind(
            service, target, "TKT-42", "3");

        assertFalse(result.hasErrors());
        assertNotNull(target.getTicketKey());
        assertEquals(42L, target.getTicketKey().value());
        assertEquals(Integer.valueOf(3), target.getQuantity());
    }

    @Test
    void invalidInputWithConverterStillGetsTypeMismatch() {
        DefaultConversionService service = freshWithConverter();
        var target = new ConversionDebugLab.TicketForm();

        BindingResult result = ConversionDebugLab.bind(
            service, target, "BAD-42", "2");

        FieldError error = result.getFieldError("ticketKey");

        assertNotNull(error);
        assertEquals("typeMismatch", error.getCode());
        assertTrue(error.isBindingFailure());
        assertNull(target.getTicketKey());
    }

    @Test
    void registrationIsScopedToConversionServiceInstance() {
        DefaultConversionService first = freshWithConverter();
        DefaultConversionService second =
            new DefaultConversionService();

        assertTrue(first.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));

        assertFalse(second.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));
    }

    @Test
    void missingRequiredFieldIsDifferentFromMissingConverter() {
        DefaultConversionService service = freshWithConverter();
        var target = new ConversionDebugLab.TicketForm();
        DataBinder binder = new DataBinder(target, "ticketForm");

        binder.setConversionService(service);
        binder.setRequiredFields("ticketKey");

        MutablePropertyValues input =
            new MutablePropertyValues();
        input.add("quantity", "2");  // ticketKey omitted.

        binder.bind(input);

        FieldError error =
            binder.getBindingResult().getFieldError("ticketKey");

        assertNotNull(error);
        assertEquals("required", error.getCode());
        assertNull(target.getTicketKey());
    }

    @Test
    void canConvertDoesNotValidateSourceText() {
        DefaultConversionService service = freshWithConverter();

        assertTrue(service.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));

        assertThrows(
            ConversionFailedException.class,
            () -> service.convert(
                "TKT-123456",
                ConversionDebugLab.TicketKey.class));
    }
}
```

The test suite has **10 JUnit 5 methods**. Each test creates its own ConversionService and target so it never depends on state mutated by another test.

### 9.7. Running JUnit

```bash
mvn -q test
```

If all assertions pass, Maven exits with code 0; Surefire reports are located in `target/surefire-reports/`. When using `-q`, Maven's stdout is not a fixed string to copy into the lesson.

These tests verify both the direct API and `DataBinder`; however, they **do not prove** that real Spring MVC loaded `MvcConversionConfig`. For MVC, a separate integration test using `MockMvc` is required.

## 10. Spring MVC Integration Test: Proving the Converter Is Wired Properly

To verify MVC registration, you can build a Spring Boot app with:

- `spring-boot-starter-web`;
- `MvcConversionConfig implements WebMvcConfigurer` with `addFormatters`;
- `TicketController` with `@PathVariable TicketKey`;
- `spring-boot-starter-test` and `@SpringBootTest` / `@AutoConfigureMockMvc`.

An illustrative JUnit fragment:

```java
@SpringBootTest
@AutoConfigureMockMvc
class TicketMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ticketPathVariableUsesRegisteredConverter()
            throws Exception {

        mvc.perform(get("/tickets/TKT-42"))
            .andExpect(status().isOk())
            .andExpect(content().string("TICKET:42"));
    }

    @Test
    void invalidTicketKeyReturnsClientError()
            throws Exception {

        mvc.perform(get("/tickets/BAD-42"))
            .andExpect(status().isBadRequest());
    }
}
```

This is a **fragment** requiring static imports, a Spring Boot context, and test dependencies; it is not in the two Java files of the runnable lab. It verifies the real Spring MVC request pipeline and context.

If the first test fails while the standalone converter unit test passes, suspect **the config class was not scanned**, `addFormatters` did not run, or MVC is using a different conversion service. If the first test passes yet the second does not return 400, inspect custom exception handlers / controller advice and status mapping.

### 10.1. Checking Which Converter the Context Actually Uses

Set breakpoints at:

- `MvcConversionConfig#addFormatters`;
- `StringToTicketKeyConverter#convert`;
- the controller method;
- the exception resolver if the response is wrong.

If the converter breakpoint is never hit, trace from route/argument resolver to the service instance rather than changing regex logic. If the breakpoint hits and throws `IllegalArgumentException`, the converter is registered—the issue is the parser/value, not missing registration.

## 11. Debug Logging and Safe Error Observation

When tracing the failure chain in development, you can enable DEBUG or TRACE logging for MVC/Beans/Conversion packages according to your framework version:

```properties
logging.level.org.springframework.web=DEBUG
logging.level.org.springframework.validation=DEBUG
logging.level.org.springframework.core.convert=TRACE
```

This is a **diagnostic configuration suggestion**, with no guarantee every converter class logs everything at TRACE. First use breakpoints, targeted tests, and structured logs emitted by the application; never enable overly verbose logging in production.

Safe minimal logging:

```text
requestId=... field=ticketKey sourceType=String targetType=TicketKey
code=typeMismatch status=400
```

Do not log raw rejected values if a field may contain tokens, passwords, or PII. If logging public identifier input is needed, apply redaction/rate-limiting policies and avoid log injection.

### 11.1. Inspecting the Cause Chain

If catching an outer exception:

```java
Throwable cause = error;
while (cause != null) {
    System.out.println(cause.getClass().getName());
    cause = cause.getCause();
}
```

This is a debugging fragment using an existing `error` variable. Print cause class names locally; in production use a logger/correlation ID and classify the error before recording details.

Typically:

- `ConverterNotFoundException`: check source/target and registry.
- `ConversionFailedException`: check target, source, and root cause.
- `TypeMismatchException` or `FieldError(typeMismatch)`: check binder/argument resolver.
- `HttpMessageNotReadableException`: check JSON deserializer and payload shape.

### 11.2. Do Not Use Exception Text as an API Contract

A message such as "Failed to convert property value of type String to TicketKey" is a technical description that can change. Clients should receive a stable code like `INVALID_TICKET_KEY` or `INVALID_PARAMETER`, status 400, and a simple, localizable message.

## 12. Advanced Scenarios That Easily Cause Misdiagnosis

### 12.1. Source and Target Have the Same Short Name in Different Packages

Two classes `demo.api.TicketKey` and `demo.domain.TicketKey` are two distinct Java types. `Converter<String,demo.api.TicketKey>` will not handle `demo.domain.TicketKey`. Always check fully qualified names in exceptions/logs/IDE.

### 12.2. Generic Collections and `TypeDescriptor`

When the target is `List<TicketKey>`, testing only `canConvert(String.class, TicketKey.class)` may be insufficient. Spring has converters for collection/array elements and uses `TypeDescriptor` to determine element types when necessary.

Conceptual example:

```java
TypeDescriptor source =
    TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(String.class));

TypeDescriptor target =
    TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(TicketKey.class));

boolean supported = cs.canConvert(source, target);
```

This fragment requires imports `TypeDescriptor`, `List`, variable `cs`, and class `TicketKey`. Both the element converter and collection conversion must be configured. Do not assume the converter is called once for the entire list; conversion normally processes each element individually.

### 12.3. Locale and Date/Time Formatting

A `Formatter<LocalDate>` can parse according to locale, and `@DateTimeFormat` can specify a pattern. If an error occurs only in one locale:

- Check the request's actual locale.
- Check format annotations on the field.
- Check the formatters registered in the MVC service.
- Test each date string with the exact locale/pattern.

Do not write a `Converter<String,LocalDate>` with ad-hoc regex if `@DateTimeFormat` or ISO formatting already meets the need.

### 12.4. `null` Alone Does Not Prove a Missing Converter

Some `convert(null, TargetType.class)` overloads may return null for reference types without looking up an actual converter. Therefore, **never use null to probe** for a missing conversion; use a real value such as `"TKT-42"` and query `canConvert`.

### 12.5. `@ModelAttribute` and `BindingResult`

With a controller:

```java
@PostMapping("/tickets")
public ResponseEntity<?> create(
        @Valid @ModelAttribute("ticketForm") TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("INVALID");
    }
    return ResponseEntity.ok("OK");
}
```

This is a fragment; it requires `TicketForm`, imports, and annotation configuration. `BindingResult` stands **immediately after** the model attribute so MVC places binding/validation errors there instead of always throwing an exception. Even when `@Valid` runs, it does not install a converter for `TicketKey` on its own.

Do not automatically expose `FieldError#getRejectedValue()`, stack traces, or converter exception text in JSON responses.

### 12.6. Unknown Fields and Missing Fields Are Not Missing Converters

If a request omits the `ticketKey` property, `DataBinder` does not need to convert an absent field. If `setRequiredFields("ticketKey")` is configured, the binder can record `required`.

If a client sends a property absent from the DTO, the binder may ignore or reject it depending on `ignoreUnknownFields` and allowlists. Do not add a Converter just to fix `required` or "unknown property" errors.

### 12.7. Overwritten Converters and Registration Order

When multiple converters are registered for the same type pair, the framework applies registry selection rules. Registering another converter can alter behavior of an existing working conversion. Maintain a single source of truth per type pair, avoid duplicate registrations, and test edge cases.

### 12.8. Do Not Lose Default Converters When Building Your Own Service

If you use an empty `GenericConversionService`:

```java
GenericConversionService empty = new GenericConversionService();
```

even String-to-Integer conversions may fail because default converters are absent. If a custom application service is needed, usually start from `DefaultConversionService` or `DefaultFormattingConversionService` and add converters on top. In MVC, use `addFormatters` to preserve framework formatters.

### 12.9. `@RequestBody` JSON and Jackson

Do not assume `WebMvcConfigurer#addFormatters` always changes how Jackson decodes a custom-type JSON property. Jackson relies on constructors, records, deserializers, modules, and its own annotations. When the request is JSON:

- Verify the target DTO matches the JSON structure.
- Use Jackson annotations/custom deserializers if needed.
- Test actual `HttpMessageNotReadableException`/binding behavior.
- Do not use the same `typeMismatch` error name to describe all JSON decode failures.

### 12.10. `@ConfigurationProperties` and Conditional Converter Registration

Spring Boot Binder uses a separate ConversionService/config conversion setup; for Boot configuration properties, registration mechanisms like `@ConfigurationPropertiesBinding` may be appropriate. If a converter is only used in MVC, do not try to register it globally across every layer. If needed in both, configure registration in both scopes explicitly and test each separately.

## 13. Code Review Checklist

1. Which request path is failing—path, query, form, JSON, or config?
2. What are the actual source type and target type?
3. What does `canConvert(source,target)` return on **the exact instance**?
4. Does the converter implement `Converter<S,T>` with the exact type arguments?
5. If the converter is missing, is the configuration class scanned by Spring and did `addFormatters` execute?
6. If conversion fails, is the cause regex, overflow, blank input, locale, or parser logic?
7. Is another PropertyEditor/Formatter/ConverterFactory interfering?
8. Are you using a converter for a Java custom type that already has a factory method or default constructor causing unexpected behavior?
9. Was a new ConversionService created after registering the converter on an older instance?
10. Was the default service accidentally replaced with an empty one?
11. Is this a generic collection or annotated property requiring `TypeDescriptor`?
12. With `@ModelAttribute`, do errors go into `BindingResult` or get thrown outside the controller?
13. With `@RequestBody`, have you checked Jackson deserialization rather than `DataBinder`?
14. Are both valid and invalid values tested on the same converter?
15. Are HTTP error responses standardized as 4xx without leaking internal details?

## 14. Quick Troubleshooting Table

| Symptom | Check first | Resolution direction |
| --- | --- | --- |
| `canConvert=false` for custom value object | Registry and `S,T` pair | Register `Converter<String,Target>` on right service |
| `ConverterNotFoundException` on direct convert | `getSourceType/getTargetType` | Verify converter registration/source/target |
| `canConvert=true` yet bad input fails | Parser and nested cause | Fix input or converter; test boundaries |
| `ConversionFailedException` | Root cause, format/locale | Return semantically right input error, no stack trace to client |
| `FieldError.code=typeMismatch` | DataBinder conversion path | Check converter on binder's conversionService |
| Unit test passes, MockMvc fails | Spring MVC config/scan | `WebMvcConfigurer#addFormatters` and integration test |
| MVC passes, `@ConfigurationProperties` fails | Boot config Binder uses different service | Register via Boot configuration binding mechanism |
| Form passes, JSON fails | Jackson does not use same ConversionService | Fix DTO/Jackson deserialization |
| String→Integer fails after custom config | Default converters lost | Use DefaultConversionService/FormattingConversionService |
| Only `dd/MM/yyyy` dates fail | Formatting/Locale/annotation | `@DateTimeFormat` and suitable Formatter |
| Missing field creates `required` | Not a missing converter | Fix HTTP request/required-field policy |
| Unknown property or over-posting | Wrong DTO/binder scope | Input DTO, allowlist, test suppressed fields |

## 15. Summary

**"No suitable converter or converter not registered" is an error about *conversion capability and registration scope*, distinct from malformed input values.** With `ConversionService`, check `canConvert(...)` and call `convert(...)` on the right instance:

- `ConverterNotFoundException`: no matching conversion path found.
- `ConversionFailedException`: path exists, yet actual conversion failed.
- `FieldError(typeMismatch)`: conversion failure collected by DataBinder for a property.
- `MethodArgumentTypeMismatchException`: a possible manifestation of path/query argument errors in Spring MVC.

The solution is to write a converter/formatter with a clear contract, register it in **the registry actually used by the pipeline**, preserve default converters, and write integration tests for MVC or Boot Binder depending on where data enters. `@Valid` validates already-bound data; it **does not** replace converter registration. When data is JSON, remember Jackson uses a different conversion mechanism.

## References

- Spring Framework 6.2 — Type Conversion (Converter SPI, ConversionService API, registration): https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html
- Spring Framework 6.2 — Spring MVC Type Conversion, addFormatters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html
- Spring Framework 6.2 Javadoc — `ConversionService`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework 6.2 Javadoc — `ConverterNotFoundException`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/core/convert/ConverterNotFoundException.html
- Spring Framework 6.2 Javadoc — `ConversionFailedException`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/core/convert/ConversionFailedException.html
- Spring Framework 6.2 Javadoc — `DefaultConversionService`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html
- Spring Framework 6.2 Javadoc — `DataBinder`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 — MVC `@InitBinder` and data binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Boot Reference — MVC Conversion Service differs from application.properties conversion: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/