# Synchronizing Binding Configuration Between Application and Tests in Spring MVC

## 1. The Problem: Tests Pass While Real Requests Bind Differently

A Spring MVC controller can behave properly in the live application yet produce different results in tests. The culprit is not always the controller: **the test environment's data-binding configuration may differ from runtime**.

Typical scenarios:

- Production registers `Converter<String, MemberCode>` to normalize codes to uppercase, but `MockMvcBuilders.standaloneSetup(...)` does not load that converter.
- The controller uses `@InitBinder("registration")` to restrict `allowedFields`, yet a test constructs `DataBinder` manually without calling the initializer; as a result, the test accepts a field that real requests suppress.
- Bean Validation runs via `@Valid` at runtime, whereas a test does `new RegistrationController()` and invokes the Java method directly; that bypasses MVC argument resolution, binders, and validation.
- `@WebMvcTest` builds an **MVC slice** whose beans differ from the full context; a separate `@Configuration` containing `WebMvcConfigurer`, formatters, or validators may need to be imported explicitly.
- Tests construct an `ObjectMapper`, `ConversionService`, `Validator`, or `Locale` different from the application's, causing numbers/dates, enums, error messages, or constraint rules to behave differently.
- A `@ControllerAdvice` in the application holds a global `@InitBinder`, yet a standalone test forgets to register the advice.
- The code path uses `@ModelAttribute` for form binding while the test sends `@RequestBody` JSON: **two non-equivalent conversion pipelines**.

**Goal** of this guide: maintain **a single source of binding configuration** for Spring MVC, choose the right test level, reuse actual production components rather than duplicating config in tests, and write tests that catch missing or mismatched configuration. Examples use **Java 17, Spring Boot 3.4.x, Spring Framework 6.x, MockMvc, JUnit 5, and Jakarta Validation**.

## 2. Binding Is a Pipeline, Not Just a Property Setter Call

For a `form-urlencoded` request and `@ModelAttribute`, the overall path is:

```text
Client POST /registrations
Content-Type: application/x-www-form-urlencoded
   |
   v
DispatcherServlet -> controller handler
   |
   v
Argument resolver creates/locates @ModelAttribute("registration")
   |
   v
WebDataBinder + objectName "registration"
   |
   +--> MVC ConversionService (Converter / Formatter)
   +--> @ControllerAdvice @InitBinder (if present)
   +--> Controller @InitBinder("registration")
   +--> allowedFields / fieldMarker / fieldDefault
   +--> BindingResult: errors + suppressedFields
   |
   v
@Valid / @Validated
   |
   +--> Jakarta Bean Validation provider
   +--> Spring Validator added via binder
   |
   v
Controller receives RegistrationForm and BindingResult
   |
   +--> reject request if binding/validation fails
   |
   v
Service / persistence / response
```

When testing, the question is not just **"what status does the controller return?"** but also:

1. Does the test use the **same `objectName`, data types, and media type** as real requests?
2. Does it use the **same `ConversionService`, formatters, validators, `@InitBinder`, and `@ControllerAdvice`** as the application?
3. Does the test inspect **`BindingResult`**, type-conversion errors, and suppressed fields?
4. Are things skipped by the test **intentional** (pure unit tests) or **accidental configuration drift**?

Tests do not need to boot the entire application for every scenario, but the test level must match the claims it makes.

## 3. Three Common Testing Approaches and Parity Levels

| Testing Approach | Spring Context | Actual MVC Configuration | Best Suited For |
| --- | --- | --- | --- |
| `@SpringBootTest + @AutoConfigureMockMvc` | Full application context | Most real MVC config, plus beans and application properties | Integration/contract tests for binding, advice, converters, and validation |
| `@WebMvcTest(Controller.class)` | MVC test slice | MVC infrastructure and selected beans; custom config may need `@Import` | Fast web-layer tests with required dependencies |
| `MockMvcBuilders.standaloneSetup(controller)` | Does not auto-load application context | Requires **manual configuration** of components outside the controller | Testing a controller in isolation, fast iteration, targeted debugging |
| Direct call `controller.method(...)` | No MVC infrastructure | No automatic argument resolution or binding | Unit testing plain Java logic; **insufficient** to prove Spring binding works |
| `MockMvcBuilders.webAppContextSetup(wac)` | Real `WebApplicationContext` | Uses MVC infrastructure and context | Full-configuration integration tests |

Spring Test distinguishes two `MockMvc` setup styles: **web application context** and **standalone**. Standalone is a focused simulation that does not automatically inherit full application configuration; therefore, standalone tests must be backed by integration tests proving application wiring works.

### 3.1. `@SpringBootTest + @AutoConfigureMockMvc`

```java
@SpringBootTest
@AutoConfigureMockMvc
class RegistrationApplicationTest {
    @Autowired MockMvc mvc;
}
```

This is a test class fragment. Spring Boot boots the context (usually without opening a real HTTP port) and configures `MockMvc` with real MVC beans. If a converter is registered via `WebMvcConfigurer` in the application context, this test style typically uses that exact converter.

It is closer to runtime than slice/standalone tests, yet **still does not go over a real HTTP port**. Filters, security, locale, profiles, property overrides, and mock beans in tests can still affect behavior. Do not equate full-context tests with 100% production deployment.

### 3.2. `@WebMvcTest`

```java
@WebMvcTest(RegistrationController.class)
@Import(RegistrationBindingConfig.class)
class RegistrationSliceTest {
    @Autowired MockMvc mvc;
}
```

This is a fragment assuming the needed imports. `@WebMvcTest` limits component scanning and auto-configuration to the web layer. It typically picks up controllers, `@ControllerAdvice`, `Converter`s, `WebMvcConfigurer`s, and related web bean types per Spring Boot's rules, but **does not load all `@Service`/`@Configuration` beans by default**.

**Do not claim `@WebMvcTest` always excludes every converter or every `WebMvcConfigurer`**: many web components are included in the slice by bean type. When application configuration is packaged in a dedicated `@Configuration` class, `@Import(RegistrationBindingConfig.class)` makes the dependency **explicit** rather than relying on scan assumptions.

### 3.3. Standalone `MockMvc`

```java
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new RegistrationController())
        .build();
```

This is the simplest fragment. It sets up basic MVC infrastructure around the instantiated controller. However, it **does not load application-wide `@Configuration`**, so converters/formatters registered only via `WebMvcConfigurer` will be missing. Local `@InitBinder` methods on the controller are still detected by standalone setup, whereas global converters, advice, and validators require explicit setup.

Takeaway: **test the actual environment you intend to verify**, rather than "making tests green" by wiring arbitrary fake defaults in test setup.

## 4. Which Configuration Sources Must Stay Synchronized?

| Configuration | Typical Runtime Registration Point | Signs It Is Missing in Tests |
| --- | --- | --- |
| `Converter<S,T>` | `WebMvcConfigurer#addFormatters`, `ConversionService` bean | Wrong bound type, unnormalized codes, `typeMismatch` |
| `Formatter<T>` | `addFormatters`, `@DateTimeFormat` | Locale-sensitive dates/numbers parse differently |
| Local `@InitBinder` | Controller | Different `allowedFields`, custom editors, or validators |
| Global `@InitBinder` | `@ControllerAdvice` | Shared rules do not run in standalone tests |
| Jakarta Validation | `LocalValidatorFactoryBean`/Boot validation starter | `@NotBlank`, `@Min` fail to produce production errors |
| Spring `Validator` | `@InitBinder#addValidators`, MVC config | Custom `rejectValue`/`reject` errors are missing |
| `MessageSource` and `LocaleResolver` | Boot config / MVC config | Different Vietnamese/English messages or number/date formats |
| Binder security policy | `setAllowedFields` / DTO / `setDeclarativeBinding` | Sensitive fields get bound in tests |
| Field marker/default | `WebDataBinder` prefix setup | Unchecked checkboxes do not reset like real requests |
| Global exception translation | `@ControllerAdvice` | Different status/body when conversion/validation fails |

Every row must be verified **by observable behavior**, not merely by asserting that a bean of a given name exists in the test context. A converter can exist in the context yet **never be used by MVC** if wired incorrectly.

## 5. Designing for Parity: Extracting Reusable Configuration

A practical rule set:

- Place shared converters/formatters in a **production MVC configuration class** implementing `WebMvcConfigurer`.
- Place **model-attribute-specific** rules in `@InitBinder("objectName")` near the controller; if shared across controllers, consider a narrowly scoped `@ControllerAdvice`.
- Extract custom Spring `Validator`s into standalone, independently testable classes, and register the **same implementation** at runtime and in tests.
- In slice tests, **import the production config class itself**; never write a fake test converter with different behavior.
- In standalone tests, invoke the **same configuration method** or construct a `ConversionService` from a shared factory—and still maintain a full-context test to verify wiring.

**Do not** duplicate normalization logic like "trim and uppercase" in two places: once in production `MemberCodeConverter` and again manually in `MockMvc` test assertions. Doing so lets tests pass even if runtime configuration changes.

### Single Source of Truth for Conversion

Example:

```java
@Configuration(proxyBeanMethods = false)
public class RegistrationBindingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new MemberCodeConverter());
    }
}
```

When the application runs, Spring MVC applies this configuration to the `FormattingConversionService` used for binding. In slice tests, import **`RegistrationBindingConfig.class` directly**. Standalone tests can create a conversion service and call `new RegistrationBindingConfig().addFormatters(service)`, while taking care not to omit other required components.

This lesson implements that full pattern in the project below.

## 6. Runnable Java 17 Example: Full Context, MVC Slice, and Standalone Using the Same Rules

We build a `POST /registrations` endpoint accepting `form-urlencoded`:

- `name`: non-blank `String`, whitespace-trimmed on bind.
- `age`: required `Integer`, minimum 18.
- `memberCode`: a value object formatted as two letters + hyphen + two digits, e.g., `AB-12`. The converter trims, uppercases, and rejects invalid patterns.
- `role`: property with a setter on the form **solely to demonstrate mass-assignment risk**, defaulting to `USER`; must not be bindable from requests.
- `name=admin`: custom Spring `Validator` adds a field error in addition to Jakarta constraints.
- `@InitBinder("registration")`: `allowedFields`, `StringTrimmerEditor`, and custom validator applied to that exact form.
- Three test suites: full-context, `@WebMvcTest` importing the same config, and standalone showing how to reuse conversion config.

The goal is not building a real registration system. There is no database, API security, or real authorization; all responses are constructed in the controller to isolate binding and validation differences.

### 6.1. Project Structure

```text
binding-parity/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── BindingParityApplication.java
    │   ├── MemberCode.java
    │   ├── MemberCodeConverter.java
    │   ├── RegistrationBindingConfig.java
    │   ├── RegistrationForm.java
    │   ├── RegistrationPolicyValidator.java
    │   └── RegistrationController.java
    └── test/java/demo/
        ├── RegistrationApplicationTest.java
        ├── RegistrationSliceTest.java
        └── RegistrationStandaloneTest.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>binding-parity</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` enables Spring MVC (Servlet stack). `spring-boot-starter-validation` supplies the Jakarta Validation provider; `spring-boot-starter-test` includes JUnit 5 and `MockMvc`. The Spring Boot parent aligns Spring/Jackson/Validator versions to avoid manual version mismatches.

### 6.3. `BindingParityApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingParityApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingParityApplication.class, args);
    }
}
```

The main class sits in package `demo`, so component scanning discovers `RegistrationBindingConfig` and `RegistrationController` in the same package in the full context.

### 6.4. `MemberCode.java`

```java
package demo;

public record MemberCode(String value) {}
```

This record wraps the converted code. Format checking and normalization live in the converter; the record does not lowercase-to-uppercase itself. Therefore tests must observe results after passing through the MVC conversion service, rather than only checking Java object instantiation.

### 6.5. `MemberCodeConverter.java`

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class MemberCodeConverter
        implements Converter<String, MemberCode> {

    @Override
    public MemberCode convert(String source) {
        String normalized =
                source.strip().toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z]{2}-[0-9]{2}")) {
            throw new IllegalArgumentException(
                    "memberCode must match AA-00");
        }

        return new MemberCode(normalized);
    }
}
```

Example inputs:

| Request String | `MemberCode.value()` After Conversion |
| --- | --- |
| `" ab-12 "` | `"AB-12"` |
| `"XY-09"` | `"XY-09"` |
| `"xx"` | Conversion error |
| `"ABC-12"` | Conversion error |
| `"AB-1"` | Conversion error |

The fixed pattern is strictly for this demo. Production contracts may use different value-object types, digit checks, and localized messages. **Converters do not replace authorization**, and client input remains untrusted until fully validated.

### 6.6. `RegistrationBindingConfig.java`

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class RegistrationBindingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new MemberCodeConverter());
    }
}
```

This is the **shared configuration source** used in both production and tests. `WebMvcConfigurer#addFormatters` adds the converter/formatter to the MVC conversion infrastructure. Never copy `convert(...)` logic into controllers or tests.

**Why `@Configuration`?** The full application context detects it via component scanning. For the MVC slice, we use `@Import(RegistrationBindingConfig.class)` to state explicitly that this converter is **required** for the controller's contract. In standalone setup, we invoke `addFormatters(...)` on the same class.

### 6.7. `RegistrationForm.java`

```java
package demo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    @NotNull
    private MemberCode memberCode;

    // Intentionally has a setter to prove allowedFields blocks overwrites.
    private String role = "USER";

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public MemberCode getMemberCode() {
        return memberCode;
    }

    public void setMemberCode(MemberCode memberCode) {
        this.memberCode = memberCode;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }
}
```

Uses `Integer` to distinguish missing values (`null`, `@NotNull`) from underage values (`@Min`). When receiving `age=abc`, the binder cannot parse an integer and records `typeMismatch` in `BindingResult`; that is a binding error, not Jakarta `@Min`.

The `role="USER"` property is intentionally included in the DTO to test suppressing `role=ADMIN`. **In real applications, it is better not to have a `role` setter on Internet-facing forms at all**; use a dedicated DTO and map to domain objects after authorization.

### 6.8. `RegistrationPolicyValidator.java`

```java
package demo;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class RegistrationPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;

        if ("admin".equalsIgnoreCase(form.getName())) {
            errors.rejectValue(
                    "name",
                    "name.reserved",
                    "Name is reserved"
            );
        }
    }
}
```

`RegistrationPolicyValidator` uses Spring's `Validator` interface, distinct from `jakarta.validation.Validator`. It is registered on `WebDataBinder` via `addValidators(...)`. This validator produces a field error; it does not handle HTTP itself.

Rules requiring database or I/O access should not perform blocking calls inside validators on an event loop; this example uses Spring MVC Servlet with an in-memory check, so there is no I/O. For database-dependent business validation, handle it in the service layer after basic binding and constraint checks.

### 6.9. `RegistrationController.java`

```java
package demo;

import jakarta.validation.Valid;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    @InitBinder("registration")
    public void initRegistration(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "memberCode");
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(false));
        binder.addValidators(new RegistrationPolicyValidator());
    }

    @PostMapping(
            path = "/registrations",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> register(
            @Valid @ModelAttribute("registration")
                    RegistrationForm form,
            BindingResult result) {

        if (result.getSuppressedFields().length > 0) {
            List<String> names = Arrays.stream(
                    result.getSuppressedFields())
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "code", "SUPPRESSED_FIELDS",
                    "fields", names
            ));
        }

        if (result.hasErrors()) {
            List<String> fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            List<String> bindingFailures =
                    result.getFieldErrors().stream()
                            .filter(FieldError::isBindingFailure)
                            .map(FieldError::getField)
                            .distinct()
                            .sorted()
                            .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_FORM",
                    "fields", fields,
                    "bindingFailures", bindingFailures
            ));
        }

        return ResponseEntity.ok(Map.of(
                "code", "OK",
                "name", form.getName(),
                "age", form.getAge(),
                "memberCode", form.getMemberCode().value(),
                "role", form.getRole()
        ));
    }
}
```

Why use `objectName` `registration`? Because `@InitBinder("registration")` selects only the binder with that exact name. If you rename `@ModelAttribute("registration")` to `@ModelAttribute("form")` without updating the initializer, the allowlist, editor, and custom validator will no longer apply.

**Guarantees that tests must prove:**

1. `name` is trimmed by the custom `StringTrimmerEditor(false)`.
2. `memberCode` is converted by `RegistrationBindingConfig`'s global converter.
3. `age` is converted to `Integer` and validated with `@Min(18)`.
4. `@Valid` triggers Jakarta Validation on the form; the custom Spring `Validator` adds the rule for `admin`.
5. `role` is not bound, and requests attempting to send it are rejected by the controller based on `getSuppressedFields()`.
6. `BindingResult` sits immediately after `@ModelAttribute` so the controller can inspect errors instead of letting Spring throw a default exception.
7. The success response reflects **actual post-binding values**, not raw request strings.

The controller returns JSON for easy test inspection, yet **the request input is `form-urlencoded`**. Do not confuse this with Jackson deserializing a JSON `@RequestBody`; `allowedFields` and `StringTrimmerEditor` here apply to property binding on the form object.

### 6.10. `RegistrationApplicationTest.java` — Full-Context Testing

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void productionConfigConvertsAndTrims() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "  Lan  ")
                        .param("age", "20")
                        .param("memberCode", " ab-12 "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("OK"))
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.memberCode").value("AB-12"))
                .andExpect(jsonPath("$.age").value(20))
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void jakartaMinConstraintIsActive() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "17")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields", hasItem("age")));
    }

    @Test
    void springValidatorIsActive() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "admin")
                        .param("age", "20")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields", hasItem("name")));
    }

    @Test
    void unknownBusinessFieldIsSuppressed() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "20")
                        .param("memberCode", "AB-12")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("SUPPRESSED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("role")));
    }

    @Test
    void wrongMemberCodeIsBindingFailure() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "20")
                        .param("memberCode", "bad"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.bindingFailures",
                        hasItem("memberCode")));
    }

    @Test
    void missingAgeViolatesNotNull() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItem("age")));
    }
}
```

These six integration tests verify conversion, trimming, Jakarta constraints, the custom Spring `Validator`, the allowlist, and binding failures via **real requests through the `DispatcherServlet` test infrastructure**, rather than calling the controller directly.

### 6.11. `RegistrationSliceTest.java` — Same Config in an MVC Slice

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@Import(RegistrationBindingConfig.class)
class RegistrationSliceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void sliceUsesProductionConverterAndLocalBinder() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", " Lan ")
                        .param("age", "21")
                        .param("memberCode", " xy-09 "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.memberCode").value("XY-09"));
    }

    @Test
    void sliceKeepsAllowedFieldsPolicy() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "21")
                        .param("memberCode", "AB-12")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("SUPPRESSED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("role")));
    }

    @Test
    void sliceRetainsCustomSpringValidation() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "admin")
                        .param("age", "21")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItem("name")));
    }

    @Test
    void sliceRetainsJakartaValidation() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "17")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItem("age")));
    }
}
```

`@Import(RegistrationBindingConfig.class)` is key: it registers the **exact production converter class**, rather than a test-only converter. The slice test also picks up local `@InitBinder("registration")` from the loaded controller, so allowed fields, string trimming, and the policy validator still operate.

The slice here has no service/repository collaborators outside the controller; in a real project with constructor-injected collaborators on the controller, use mock/test beans or import the needed dependencies per the test's goal. **Never use a mock converter with behavior differing from production** just to make a test pass.

### 6.12. `RegistrationStandaloneTest.java` — Reusing Config When Standalone Is Needed

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class RegistrationStandaloneTest {

    private MockMvc mvc;

    @BeforeEach
    void createMvcUsingRealBinderRules() {
        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();

        // Reuse the production method;
        // do not redefine conversion logic in the test.
        new RegistrationBindingConfig()
                .addFormatters(conversionService);

        // Create Jakarta Validator for standalone infrastructure.
        LocalValidatorFactoryBean validator =
                new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();

        mvc = MockMvcBuilders
                .standaloneSetup(new RegistrationController())
                .setConversionService(conversionService)
                .setValidator(validator)
                .build();
    }

    @Test
    void standaloneConvertsUsingProductionConfig() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", " Lan ")
                        .param("age", "20")
                        .param("memberCode", " ab-12 "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.memberCode").value("AB-12"));
    }

    @Test
    void standaloneStillUsesLocalInitBinder() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "20")
                        .param("memberCode", "AB-12")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("SUPPRESSED_FIELDS"));
    }
}
```

This is a standalone test with essential configuration **explicitly supplied**:

- Uses `DefaultFormattingConversionService` as the base for standard converters, then calls production's `addFormatters(...)` to add `MemberCodeConverter`.
- Uses `LocalValidatorFactoryBean` because standalone setup does not automatically load the global Jakarta Validation provider from a full Boot context.
- Uses the real `RegistrationController` so local `@InitBinder("registration")` still runs.
- Does not load `@ControllerAdvice`, security filter chains, custom `HandlerMethodArgumentResolver`s, or anything else from runtime unless registered explicitly.

**Do not treat standalone as a complete production replica.** These two tests verify only the paths explicitly configured here. Any project with MVC customizations must maintain at least one full-context suite to catch missing components, annotation scanning, profiles, and wiring bugs. When debugging elusive issues, prefer `@SpringBootTest`/`@AutoConfigureMockMvc` or `webAppContextSetup(wac)` over building a lookalike standalone setup that misses real details.

### 6.13. Running All Tests

With Java 17+ and Maven in the directory containing `pom.xml`:

```bash
mvn -q clean test
```

**Expected:** a total of **12 tests** pass (6 full-context + 4 slice + 2 standalone), and Maven exits with code 0 when dependencies and environment are available. This is an **expected outcome from the test design**, not measured stdout from a live run; run the actual build to confirm. Do not assert fixed Maven/JUnit console text since Surefire and logging formats vary by version.

Run the application:

```bash
mvn spring-boot:run
```

Submit a valid form:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name= Lan ' \
  --data-urlencode 'age=20' \
  --data-urlencode 'memberCode= ab-12 '
```

Expected HTTP 200 body:

```json
{
  "code": "OK",
  "name": "Lan",
  "age": 20,
  "memberCode": "AB-12",
  "role": "USER"
}
```

Try a disallowed field:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Lan' \
  --data-urlencode 'age=20' \
  --data-urlencode 'memberCode=AB-12' \
  --data-urlencode 'role=ADMIN'
```

Expected HTTP 400 body:

```json
{
  "code": "SUPPRESSED_FIELDS",
  "fields": ["role"]
}
```

Sending `age=abc` fails conversion to `Integer`, so the controller receives conversion errors in `BindingResult` and returns `INVALID_FORM`. Sending `memberCode=bad` causes the registered converter to throw a conversion error; `bindingFailures` includes `memberCode`. Sending `name=admin` causes the custom Spring `Validator` to record a field error, also returning `INVALID_FORM`.

**Keeping tests stable:** instead of matching exact locale-interpolated message text, tests primarily assert status, field names, `bindingFailures` markers, and normalized values. Key order in JSON objects is not guaranteed.

## 7. Why Can the Same Configuration Source Still Behave Differently?

### 7.1. Different Spring Profiles / Application Properties

Runtime may activate the `prod` profile while tests use `test`. An `@Profile("prod")` on an MVC configuration bean or a conditional property can make a converter exist only in production. That may be an **intentional difference**, yet it still requires an integration test running under the matching profile to verify.

If a converter is part of the **shared API contract**, do not mark it as test-only or production-only lightly. If a feature flag genuinely alters the contract, test **both branches**.

### 7.2. Tests Overriding a `ConversionService` Bean

A test might define a `@TestConfiguration` or another `@Primary ConversionService` bean, causing MVC to use a different configuration than production. Similarly, `@MockBean`/`@MockitoBean` can replace a service and inadvertently alter a validator that depends on it.

Mock only the necessary **business collaborators**, never the converter or validator you are trying to prove. For the conversion service, use production configuration or a clearly configured shared factory.

### 7.3. Different `Locale`/`TimeZone`

Formatters converting dates, currencies, or decimals depend on `Locale` or `TimeZone`. For example, `1,234` means different things across locales. Never rely on a CI machine's default locale.

In `MockMvc`, specify the locale explicitly when testing locale-dependent semantics:

```java
mvc.perform(post("/amounts")
        .locale(Locale.GERMANY)
        .param("amount", "1,23"));
```

This is a fragment; the endpoint and `AmountForm` would be defined in another application. Specify the locale explicitly alongside production formatters; never turn local machine parsing defaults into an implicit contract. For time zones, use UTC or explicit zones whenever the API requires them.

### 7.4. Different Request `Content-Type`

`@ModelAttribute` normally binds from query/form parameters. If a test sends:

```java
post("/registrations")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Lan\"}");
```

that is **not an equivalent request** to `form-urlencoded` using `.param("name","Lan")`. With `@RequestBody`, Jackson performs JSON deserialization; `WebDataBinder#setAllowedFields` does not filter JSON properties prior to Jackson constructing the DTO the way form property binding does.

Never "fix" a test by changing the content type arbitrarily just to get the expected status. Tests must use the **exact media type defined by the API contract**.

### 7.5. Different `@ModelAttribute` Name

If the controller uses `@InitBinder("registration")` while a standalone test creates a binder manually:

```java
WebDataBinder binder =
        new WebDataBinder(new RegistrationForm(), "form");
```

then `objectName` is `form`, **not `registration`**. If a test invokes an initializer by hand and binds data, it bypasses MVC's `objectName`-based init-binder selection. Use a real handler with `@ModelAttribute("registration")` or clearly bound the scope of the unit test.

### 7.6. Different Controller/Advice Scanning

`@ControllerAdvice` can hold global `@InitBinder`, `@ExceptionHandler`, or `@ModelAttribute` methods. `@WebMvcTest` can automatically include some advices in the slice, while standalone setup needs `.setControllerAdvice(...)` to apply them. Without the advice, HTTP status codes and error bodies can differ even when binding succeeds or fails by the same rules.

Advice classes can also carry **controller-targeting selectors**: `assignableTypes`, `basePackages`, `annotations`. If a test configures advice for a different controller, the initializer will not run. Test both matched controllers and excluded controllers whenever logic depends on selectors.

### 7.7. Different Validators

`@Valid` does not enforce constraints when a test calls a Java method directly. MVC requires a validator and argument-resolution machinery to trigger it. In standalone tests, configure `LocalValidatorFactoryBean` or an appropriate Spring `Validator`; in full-context tests, `spring-boot-starter-validation` provides the configured provider.

If a test merely invokes the controller method directly:

```java
RegistrationController controller = new RegistrationController();
// Cannot automatically construct BindingResult / @ModelAttribute like MVC.
```

that only instantiates an object. Without `DispatcherServlet`/argument resolvers, it proves nothing about converters or `@InitBinder`.

## 8. Testing Binders Directly with `DataBinder`: Benefits and Limits

A direct `WebDataBinder`/`DataBinder` test is helpful for isolating a single rule:

```java
RegistrationForm form = new RegistrationForm();
WebDataBinder binder =
        new WebDataBinder(form, "registration");

binder.setAllowedFields("name", "age", "memberCode");
binder.bind(new MutablePropertyValues(Map.of(
        "name", "Lan",
        "age", "20",
        "role", "ADMIN"
)));
```

This is a binder API fragment requiring the matching Spring imports. Because it **has not registered production's converters, editors, and validators**, it proves only the manually configured allowlist—**not** full controller binding parity.

To unit test a converter in isolation, you can write:

```java
MemberCode result =
        new MemberCodeConverter().convert(" ab-12 ");
// result.value() == "AB-12"
```

This test validates the **converter logic**, yet **does not prove the converter is registered in MVC's `ConversionService`**. That is why the integration tests in section 6 assert outputs through the endpoint.

A well-balanced test strategy consists of:

1. Fast unit tests for complex converter/formatter/validator logic.
2. One or more MVC slice tests verifying configuration is wired to the controller.
3. Full-context integration tests for critical binding contracts.
4. When behavior involves real browsers, security filters, or reverse proxies, add HTTP end-to-end tests in an appropriate environment.

## 9. Parity Between Spring `Validator` and Jakarta Bean Validation

In MVC, both forms of validation can participate together:

| Component | Registration | Purpose |
| --- | --- | --- |
| Jakarta `@NotBlank`/`@Min` | Constraints on DTO + `@Valid`/`@Validated` + provider | Declarative rules on the model |
| Spring `Validator` | `@InitBinder#addValidators(...)` or global config | Custom rules recording errors into `Errors` |
| `BindingResult` | Created by Spring alongside the model attribute | Aggregates binding/validation errors and suppressed fields |
| Business policies in services | Invoked explicitly after input validation | Domain rules or persistence-dependent checks |

`@InitBinder("registration")` calls `addValidators(new RegistrationPolicyValidator())`, so Spring MVC runs the extra validator when validating the command object. Use **`addValidators`** to combine with the global validator; `setValidator` sets a single validator and can replace the preconfigured list, creating divergence between app and tests if unchecked.

Another mistake is confusing the two `Validator` interfaces from different packages:

- `org.springframework.validation.Validator`: defines `supports(Class<?>)` and `validate(Object, Errors)`.
- `jakarta.validation.Validator`: defines `validate(Object, Class<?>... groups)` and returns `Set<ConstraintViolation<T>>`.

They serve different APIs. Spring provides an adapter integrating Jakarta Validation into MVC, so never implement a fake class matching one interface in tests and claim real wiring has been verified.

## 10. Synchronizing Custom Binders via `@ControllerAdvice` and Global Config

Across many controllers, configuration splits naturally into two tiers:

### 10.1. Shared Configuration

Use `WebMvcConfigurer#addFormatters` for converters/formatters independent of a specific form. For instance, `MemberCodeConverter` normalizes a value object, so global registration makes sense when endpoints share that format contract.

If a converter matters only for **one very specific field**, register a custom editor inside `@InitBinder("objectName")`. Tests must then use the exact binder name and matching controller/advice bean.

### 10.2. Per-Controller / Per-Attribute Binder Policy

```java
@ControllerAdvice(assignableTypes = RegistrationController.class)
public class RegistrationBinderAdvice {

    @InitBinder("registration")
    public void init(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "memberCode");
    }
}
```

This is a **fragment illustrating moving the policy into advice**; **do not add it to the runnable project in section 6**, as it duplicates `RegistrationController`'s local `@InitBinder`. `assignableTypes` selects the target controller, while `@InitBinder("registration")` selects the binder with the matching `objectName`.

When moving config from a controller into advice:

- Update slice tests to ensure the advice is scanned or explicitly imported.
- In standalone tests, register the advice with `.setControllerAdvice(new RegistrationBinderAdvice())`.
- Never let both local and global methods call `setAllowedFields(...)` with conflicting lists; global init-binders usually run before local ones, so establish clear ownership.
- Re-check `BindingResult.getSuppressedFields()` and negative tests for sensitive fields.

Tests should **catch missing advice**, rather than creating a test-only advice with different rules to "paper over" failures.

## 11. Dangerous Drift Scenarios That Need Tests

### 11.1. Tests Accidentally Loosening `allowedFields`

In production:

```java
binder.setAllowedFields("name", "age", "memberCode");
```

In a test constructing a binder manually, omitting the allowlist lets default property binding populate every matching public writable property, turning `role=ADMIN` into a vulnerability. Run a **negative test** submitting an extra non-allowlisted field through the real endpoint and assert the controller returns the proper rejection.

`getSuppressedFields()` reports skipped fields; **it does not automatically make `hasErrors()` return `true`**. The runnable example explicitly returns `SUPPRESSED_FIELDS` whenever that array is non-empty.

### 11.2. Converter Test Passes Yet Converter Is Unregistered

Unit test:

```java
assertEquals(
        "AB-12",
        new MemberCodeConverter().convert(" ab-12 ").value()
);
```

This JUnit fragment requires statically importing `Assertions.assertEquals`. It proves only the **conversion function**. If `RegistrationBindingConfig` is not loaded into MVC, the API may retain unnormalized values or throw type-conversion errors depending on defaults. To catch this, an MVC test must submit `" ab-12 "` and assert the `"AB-12"` output.

### 11.3. Testing Only the Happy Path

A form can return 200 for valid inputs even when validation is completely absent. Tests must therefore include **deliberately invalid inputs**:

- `age=17`: verifies Jakarta `@Min`.
- `age=abc`: verifies type-conversion failure.
- `name=admin`: verifies the custom Spring `Validator`.
- `role=ADMIN`: verifies `allowedFields`.
- `memberCode=bad`: verifies custom converter rejection.
- `name=   `: verifies trimming + `@NotBlank`.

Good tests assert **post-binding state and error branches**, not just default HTTP status codes.

### 11.4. Using `@WebMvcTest` When Controller Collaborators Are Not Imported

If a controller requires services via its constructor, the slice does not automatically scan all services/repositories. Use the test double supported by your Spring Boot version (such as `@MockitoBean` in supported Spring Framework/Boot releases) or import a lightweight service. Never mock **the binding configuration itself** that you are trying to verify.

### 11.5. Relying on Standalone Tests as Sole Integration Proof

Standalone setup typically lacks filter chains, global controller advice, full MVC configuration, `LocaleResolver`, and application-specific beans. Never watch standalone tests pass and conclude "all production requests bind properly." Spring Framework docs recommend combining integration tests or using `webAppContextSetup(wac)` when verifying real configuration behavior.

### 11.6. Using JSON to Test Form Rules

`@RequestBody` payloads are deserialized by Jackson; `@ModelAttribute`'s `setAllowedFields` property-binding rules are not a JSON field whitelist. Compare the two formats only to verify **two separate contracts**. Never assume `_checkbox`, `!defaultField`, or editor behavior carries over to JSON deserialization.

### 11.7. Timezone and Date-Format Drift

For `LocalDate`, `ZonedDateTime`, `BigDecimal`, or currencies, tests must verify locale, time zone, and formatters. A test parsing only `2026-01-01` under the default locale can miss failures on localized input. Prefer ISO formats in APIs unless required otherwise, and declare formatters and locales explicitly.

## 12. Practical Test Matrix for Real Projects

| Test Area | Full Context | MVC Slice | Standalone | What to Verify |
| --- | --- | --- | --- | --- |
| Valid request | Yes | Yes | Yes | Post-conversion values and status |
| Global converter/formatter | **Required if part of contract** | Real `@Import` | Register manually if used | Production `ConversionService` is active |
| Local `@InitBinder` | Yes | Yes | Possible | Exact `objectName` and initializer |
| Global `@ControllerAdvice` binder | Yes | Import/scan per scope | Register manually | Advice targets the right controllers |
| Jakarta constraints | Yes | Yes with provider | Set `Validator` | `@Valid` is not skipped |
| Custom Spring `Validator` | Yes | Yes | Yes if binder selected | Rules independent of Jakarta |
| Suppressed fields | Yes | Yes | Yes | Prevents mass assignment |
| Wrong type / `typeMismatch` | Yes | Yes | Yes if conversion matches | Distinguish binding vs. constraints |
| Message localization | Test locale | Test locale | Configure manually | `MessageSource`/`Locale` |
| Security filters | Per config | Slice may differ | Not present by default | Test authorization/CSRF separately |
| Actual HTTP/network behavior | No (`MockMvc`) | No | No | Add live-port tests when needed |

You do not need every cell of this matrix for every service. However, **security-sensitive rules and API contracts**—allowlists, validation, and conversion—must have at least one verification running through realistic infrastructure.

## 13. Test Organization Strategy to Avoid Duplication

A large project can organize code as:

```text
src/main/java/...
  web/RegistrationBindingConfig.java
  web/RegistrationController.java
  validation/RegistrationPolicyValidator.java
  type/MemberCodeConverter.java

src/test/java/...
  conversion/MemberCodeConverterTest.java
  web/RegistrationSliceTest.java
  web/RegistrationApplicationTest.java
  web/RegistrationStandaloneTest.java
```

**Do not** duplicate dozens of identical tests across all three layers. Instead:

1. Fast unit tests for intricate converter/formatter/validator logic.
2. Slice tests for controller/argument-resolver conditions needing verification.
3. Integration tests for **wiring and parity** on critical paths.
4. Standalone tests only where they aid debugging or reduce cost for simple logic.

If you use an abstract test contract across multiple MVC setups, ensure each subclass still uses a single authoritative configuration source; never build an abstract base class that spins up a fake `ConversionService` and defeats integration testing.

A useful "canary test" pattern: submit an input requiring a **production converter**, such as a lowercase code with spaces, and assert the uppercase response. If someone refactors `@WebMvcTest` and drops `@Import`, the test catches the discrepancy immediately.

## 14. Troubleshooting When Tests and Runtime Diverge

Trace from request to binder rather than looking only at the final exception:

1. **Verify request shape:** method, path, content type, body, query/form parameters, headers, and locale.
2. **Verify controller handler:** which mapping actually matched? Does `@ModelAttribute("registration")` have the exact `objectName`?
3. **Verify binder creation:** did local `@InitBinder` or global advice run?
4. **Verify conversion:** does MVC `ConversionService` have production's converters/formatters? Assert normalized values.
5. **Verify `allowedFields`:** were fields outside the allowlist suppressed? Did the controller reject them explicitly?
6. **Verify validation provider:** did `@Valid`/`@Validated` execute with the expected group and `Validator`?
7. **Verify custom Spring `Validator`s:** does `supports(...)` match the class, and did `addValidators(...)` attach to the right binder?
8. **Verify slice test imports:** does `@WebMvcTest` import required config, advice, and collaborators?
9. **Verify standalone setup:** are `setConversionService`, `setValidator`, and `setControllerAdvice` configured where needed?
10. **Verify profiles/config overrides:** are profile-gated, property-gated, or test-annotation-conditional beans missing?
11. **Verify `BindingResult`:** inspect field errors, global errors, `isBindingFailure()`, and `getSuppressedFields()` rather than only `hasErrors()`.
12. **Run a full-context test** with the exact same payload as the slice/standalone test to separate a "business bug" from "drifted test infrastructure."

### Example: Parse Failure Is Not a Constraint Violation

Sending `age=abc` in `form-urlencoded` typically produces a conversion error for `Integer age`. Even though `@Min(18)` exists, this is not "a number less than 18." Inspect `FieldError#isBindingFailure`. For a JSON `@RequestBody` with `age="abc"`, the failure occurs in Jackson/`HttpMessageConverter` before reaching the controller and does not produce the same `BindingResult`; do not extrapolate from one pipeline to the other.

### Tips When Failures Happen Only on CI

Check Java version, Spring Boot BOM versions, Maven dependency tree, locale, time zone, active profiles, environment properties, and test context caching. Never weaken validator strictness to "make CI happy" before confirming **the exact same binding configuration** is active.

## 15. Security: Binding Parity Is Part of the Input Contract

Binding is not merely a type-conversion convenience. If production enforces an allowlist while tests omit it, tests can miss **mass assignment** (clients overwriting restricted fields). Thus, binder configuration parity directly affects security.

Principles:

- Use dedicated DTOs instead of binding directly onto JPA entities with setters for `role`, `balance`, `ownerId`, or `status`.
- Use `setAllowedFields(...)` whenever property binding is used to restrict public writable fields.
- Do not rely on `setDisallowedFields(...)` with an incomplete denylist as your sole defense.
- With constructor/record binding, expose only request-contract fields on the constructor; `allowedFields` primarily governs **property binding**.
- Inspect `getSuppressedFields()` and write negative tests submitting disallowed fields.
- Validation constraints never replace authorization: a type-valid `role=ADMIN` must still be forbidden if the caller lacks permission.
- Never log raw rejected values from `FieldError`; they may contain sensitive data.
- If Spring Security CSRF protection is enabled on forms, tests must supply valid CSRF tokens matching security configuration; never disable security in tests just to bypass 403 and treat 200 as proof that the binder works.
- Never handle malformed user input by silently turning exceptions into HTTP 200; tests should assert status + error codes.

## 16. Completion Checklist

- [ ] **One production class** owns shared converters/formatters and is reused in tests.
- [ ] `@InitBinder` lives on a clearly scoped controller/advice with matching `objectName`.
- [ ] `@WebMvcTest` imports critical application configurations not auto-included by the slice.
- [ ] Standalone tests register required MVC infrastructure explicitly without pretending to be a full context.
- [ ] At least one `@SpringBootTest + @AutoConfigureMockMvc` test verifies end-to-end wiring for key requests.
- [ ] Tests assert **post-conversion values**, not merely HTTP 200.
- [ ] Tests cover both Jakarta constraints and custom Spring `Validator`s.
- [ ] Tests cover wrong-type inputs and distinguish `isBindingFailure()`.
- [ ] Tests submit fields outside the allowlist and verify suppressed fields.
- [ ] JSON requests are never substituted for `form-urlencoded` contracts.
- [ ] Locale, time zone, and profiles are verified wherever they affect binding.
- [ ] When moving config into `@ControllerAdvice`, slice/standalone tests are updated to include that advice.
- [ ] Tests remain independent of locale-specific message strings and unspecified field ordering.
- [ ] Production conversion logic is never duplicated inside test-specific mocks.
- [ ] Before release, integration tests run against the profile and dependency set matching deployment.

## 17. Conclusion

**Synchronizing binding configuration does not mean every test must boot the full application context.** It means tests proving an input contract must use **the exact relevant production configurations** at the appropriate test layer:

- `@SpringBootTest + @AutoConfigureMockMvc` verifies wiring close to the running application.
- `@WebMvcTest + @Import` enables fast web-slice checks while explicitly using **production configuration**.
- `standaloneSetup` helps isolate controller logic, provided converters, validators, and advice are **manually wired** whenever they are part of the tested behavior.
- Isolated unit tests for converters/validators verify component logic only, not that MVC actually registered and used them.

By keeping a single source of configuration, naming `@ModelAttribute`/`@InitBinder` consistently, and testing both successful conversions and negative cases (constraints, conversion failures, suppressed fields), you catch drift between the live app and tests early—especially drift that could cause data corruption or security gaps.

## References

- [Spring Framework 6.2 — MockMvc Setup Options: WebApplicationContext vs Standalone](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html)
- [Spring Framework 6.2 — MVC @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — MVC Data Binding / Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html)
- [Spring Framework 6.2 — MVC @ModelAttribute Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — WebMvcConfigurer API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Boot 3.4 — WebMvcTest API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html)
- [Spring Framework — WebDataBinder API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
