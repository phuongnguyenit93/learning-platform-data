# Testing Multilingual Messages and Sensitive-Data Masking in Spring Framework

## 1. Problem statement: right language without leaking raw input

A Spring API receives registration data including email, password, access token, and contact items. Users in Vietnam need Vietnamese error messages; users in the US need English error messages. At the same time, error responses **must not echo sensitive user input**.

**Completely synthetic** example request:

~~~json
{
  "email": "CANARY_EMAIL_77",
  "password": "CANARY_PASSWORD_88!",
  "apiToken": "CANARY_TOKEN_99!",
  "contacts": [{"name": "", "priority": 0}]
}
~~~

These distinct `CANARY_*` strings are chosen deliberately so leaks are easy to spot in tests; never use real credentials.

If a controller returns raw `BindingResult`, `FieldError`, `ConstraintViolation`, or `Exception#getMessage()`, the payload may leak `rejectedValue`, `invalidValue`, JSON parser excerpts, Java class names, or custom validator messages that interpolated the raw input. Doing so leaks data and couples clients to framework internals.

An **application-defined** response should look like:

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Yêu cầu không hợp lệ",
  "status": 400,
  "detail": "Hãy kiểm tra các trường được đánh dấu.",
  "code": "INVALID_REQUEST",
  "issues": [
    {
      "code": "INVALID_EMAIL",
      "path": "email",
      "location": "body",
      "message": "Địa chỉ email không hợp lệ"
    },
    {
      "code": "INVALID_FORMAT",
      "path": "password",
      "location": "body",
      "message": "Giá trị sai định dạng"
    }
  ]
}
~~~

This is an **abbreviated example**, not the full output for the request above: `apiToken` and `contacts` would also have issues. Spring 6.x `ProblemDetail` supports RFC 9457, while `code`, `issues`, `path`, and `location` are **API-chosen extensions**.

This lesson tests **two properties simultaneously**:
- *i18n correctness*: for the same error, `en-US` and `vi-VN` return localized messages while error codes and paths stay identical.
- *data minimization*: the entire response contains no submitted email/password/token, parser diagnostics, stack traces, or sensitive method/class names.

The lesson uses **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Jakarta Bean Validation, JUnit 5, and MockMvc**. A runnable project and expected outcomes are provided, without claiming Maven was executed.

## 2. Distinguishing data to keep vs data to mask

| Element | Should it be returned? | Why |
| --- | --- | --- |
| HTTP `status` and response code `INVALID_REQUEST` | Yes | Clients handle reliably |
| Issue codes `INVALID_EMAIL`, `REQUIRED` | Yes | Language-independent |
| Path `contacts[0].priority` after allowlisting | Yes | Frontend knows which element failed |
| `location` such as `body`, `form`, `query` | Yes | Identifies input source |
| Message from an approved server catalog | Yes | Multilingual and easy to test |
| `FieldError#getRejectedValue()` | **No** | May contain password/token/PII |
| `ConstraintViolation#getInvalidValue()` | **No** | May be a nested object |
| Raw `ObjectError#getArguments()` | **No** | Internal metadata/values |
| `MessageSourceResolvable#getArguments()` | **No** | Not a public schema |
| Arbitrary `FieldError#getDefaultMessage()` | **Not by default** | Custom validators can embed input |
| `Throwable#getMessage()`/cause/stack | **No** | Leaks parser/config/method details |
| Raw Map key inside field path | Needs review | Key may be an email/token |
| Constraint descriptor with regexp/groups/payload | Not by default | May expose validation policy |
| Server-generated request ID | Possible | Helps lookup when safely formatted |

**Note:** do not merely drop the `rejectedValue` property from JSON. A validator might produce a message like `"Bad value: CANARY_PASSWORD_88!"`, leaking data even when the response only exposes a `message` field. Therefore public messages must come from a **server-controlled catalog**, selected by allowlisted codes.

An anti-pattern:

~~~java
// Never use in public APIs:
return ResponseEntity.badRequest()
        .body(exception.getBindingResult().getFieldErrors());
~~~

Another anti-pattern:

~~~java
// Never rely on this as a security mechanism:
String publicText = exception.getMessage()
        .replace("password", "[redacted]");
~~~

String replacement fails to cover URL encoding, JSON-escaped text, nested errors, or unknown field names. The stronger defense is **never placing raw exception text into public DTOs in the first place**.

## 3. Two localization layers that must be tested separately

### 3.1. Bean Validation message interpolation

Constraint annotations can reference templates:

~~~java
@NotBlank(message = "{validation.required}")
@Email(message = "{validation.email}")
private String email;
~~~

`{validation.email}` is a resource bundle key. Spring Boot 3.5 integrates the application `MessageSource` into Bean Validation message resolution, after which the Jakarta provider finishes interpolation. With standard Boot config including `spring-boot-starter-validation` and valid `messages*.properties` files, manually declaring `LocalValidatorFactoryBean` solely for i18n is usually unnecessary.

In tests, inject the Spring-managed `jakarta.validation.Validator` and verify `ConstraintViolation#getMessage()` is interpolated and differs from `getMessageTemplate()`.

### 3.2. Public messages from the API mapper

Suppose `@Pattern` produces framework code `Pattern`. The mapper translates it:

~~~text
FieldError code "Pattern"
     |
     v
Public code "INVALID_FORMAT"
     |
     v
MessageSource "api.error.INVALID_FORMAT"
     |
     +-- Locale en-US: Value has an invalid format
     |
     +-- Locale vi-VN: Giá trị sai định dạng
~~~

At this layer the mapper **does not read `FieldError#getDefaultMessage()`**, preventing an unsafe custom validator message from reaching the public response.

Separate namespaces:
- `validation.*` serves Bean Validation interpolation.
- `api.error.*` and `api.problem.*` serve public API responses.

A passing Bean Validation test does not prove API responses are translated. A passing API response test does not prove annotation templates resolve properly. Test both.

### 3.3. Locale resolution in MVC

In MVC, `LocaleResolver` determines the locale from the request or app configuration. If header-based, the client sends:

~~~http
Accept-Language: vi-VN
~~~

Spring then sets the matching locale on `LocaleContextHolder` for the request thread. In `MockMvc`, `.locale(Locale.forLanguageTag("vi-VN"))` sets the locale explicitly; in unit tests outside a request, save and restore the locale context in `finally`.

Never rely on `Locale.getDefault()` to pick user messages; JVM/CI runners may run with different locales. In WebFlux, do not assume ThreadLocal propagates across every Reactor scheduler.

## 4. Designing an allowlist-oriented error contract

A minimal public issue:

~~~java
public record PublicIssue(
        String code,
        String path,
        String location,
        String message) {
}
~~~

This record **excludes** rejected/invalid values, causes, stack traces, and framework objects.

Application-defined error code contract:

| Framework code | Public code |
| --- | --- |
| `NotBlank`, `NotNull`, `NotEmpty` | `REQUIRED` |
| `Email` | `INVALID_EMAIL` |
| `Pattern` | `INVALID_FORMAT` |
| `Min` | `BELOW_MIN` |
| `typeMismatch` | `INVALID_TYPE` |
| Unrecognized error | `INVALID_VALUE` |
| Unreadable JSON | `INVALID_JSON` |
| Missing required query parameter | `MISSING_PARAMETER` |

Never return all of `FieldError#getCodes()`: specific codes can expose object names, Java types, and method signatures. Clients only need stable public codes.

**Paths need control too.** `contacts[0].name` helps the UI, whereas `contacts[private-email@example.com].name` leaks data embedded directly in the key. The demo permits only `email`, `password`, `apiToken`, `count`, and indexed `contacts[0..7].name/priority`. Paths outside the allowlist become empty strings rather than being echoed.

`location` is supplied by the advice from a vetted vocabulary (`body`, `form`, `query`), never raw request parameters. In larger apps with dynamic Map keys, use canonical public identifiers or tested escaping/parsing instead of reflecting arbitrary field names.

## 5. Project layout and Maven

The runnable project uses the **Spring MVC Servlet stack**.

~~~text
pom.xml
src/main/java/com/example/i18nsafe/
  I18nSafeApplication.java
  ContactInput.java
  RegistrationInput.java
  PublicIssue.java
  SafeIssueMapper.java
  RegistrationController.java
  SafeErrorAdvice.java
src/main/resources/
  application.properties
  messages.properties
  messages_en.properties
  messages_vi.properties
src/test/java/com/example/i18nsafe/
  SafeErrorIntegrationTest.java
  SafeIssueMapperTest.java
  BeanValidationLocaleTest.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>i18n-safe-validation</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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
</project>
~~~

No database is needed. `spring-boot-starter-web` provides MVC, `spring-boot-starter-validation` provides the Jakarta provider, and `spring-boot-starter-test` provides JUnit Jupiter, Hamcrest, JSONPath, and MockMvc.

### 5.2. Spring Boot application

~~~java
// src/main/java/com/example/i18nsafe/I18nSafeApplication.java
package com.example.i18nsafe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nSafeApplication {
    public static void main(String[] args) {
        SpringApplication.run(I18nSafeApplication.class, args);
    }
}
~~~

### 5.3. Nested DTO: `ContactInput.java`

~~~java
// src/main/java/com/example/i18nsafe/ContactInput.java
package com.example.i18nsafe;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ContactInput {

    @NotBlank(message = "{validation.required}")
    private String name;

    @NotNull(message = "{validation.required}")
    @Min(value = 1, message = "{validation.min}")
    private Integer priority;

    public ContactInput() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public Integer getPriority() { return priority; }
    public void setPriority(Integer priority) {
        this.priority = priority;
    }
}
~~~

`priority=0` parses to `Integer` yet violates `@Min(1)`. On a form sending `priority=CANARY_BAD_PRIORITY`, `WebDataBinder` fails conversion and records a `typeMismatch` error rather than `@Min`.

### 5.4. Input DTO: `RegistrationInput.java`

~~~java
// src/main/java/com/example/i18nsafe/RegistrationInput.java
package com.example.i18nsafe;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;

import java.util.ArrayList;
import java.util.List;

public class RegistrationInput {

    @NotBlank(message = "{validation.required}")
    @Email(message = "{validation.email}")
    private String email;

    @NotBlank(message = "{validation.required}")
    @Pattern(regexp = "[A-Za-z0-9]{12,40}",
             message = "{validation.format}")
    private String password;

    @NotBlank(message = "{validation.required}")
    @Pattern(regexp = "[A-Z0-9]{8,32}",
             message = "{validation.format}")
    private String apiToken;

    @NotEmpty(message = "{validation.required}")
    private List<@Valid ContactInput> contacts =
            new ArrayList<>();

    public RegistrationInput() {}

    public String getEmail() { return email; }
    public void setEmail(String email) {
        this.email = email;
    }

    public String getPassword() { return password; }
    public void setPassword(String password) {
        this.password = password;
    }

    public String getApiToken() { return apiToken; }
    public void setApiToken(String apiToken) {
        this.apiToken = apiToken;
    }

    public List<ContactInput> getContacts() {
        return contacts;
    }
    public void setContacts(List<ContactInput> contacts) {
        this.contacts = contacts;
    }
}
~~~

**Passwords/tokens in the demo use regexes solely to create test cases.** This is not a production design for credential security. Real systems need password hashing, token lifecycles, login rate limiting, authorization checks, and secret-free logs. Canary strings are synthetic data.

`List<@Valid ContactInput>` cascades validation into each element, creating indexed paths such as `contacts[0].name`. Do not strip indexes from allowlisted paths: the frontend needs to know which element failed.

### 5.5. Public DTO: `PublicIssue.java`

~~~java
// src/main/java/com/example/i18nsafe/PublicIssue.java
package com.example.i18nsafe;

public record PublicIssue(
        String code,
        String path,
        String location,
        String message) {
}
~~~

This DTO holds only approved public fields. Never add `Object rejectedValue`, `Throwable cause`, or raw `ObjectError` to the record "to help debugging".

## 6. Mapper code: read only code/path, never rejected values

### 6.1. `SafeIssueMapper.java`

~~~java
// src/main/java/com/example/i18nsafe/SafeIssueMapper.java
package com.example.i18nsafe;

import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceResolvable;
import org.springframework.stereotype.Component;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

import java.util.Locale;
import java.util.Set;

@Component
public final class SafeIssueMapper {

    private static final Set<String> PUBLIC_CODES = Set.of(
            "REQUIRED", "INVALID_EMAIL", "INVALID_FORMAT",
            "BELOW_MIN", "INVALID_TYPE", "INVALID_JSON",
            "MISSING_PARAMETER", "INVALID_VALUE");

    private final MessageSource messages;

    public SafeIssueMapper(MessageSource messages) {
        this.messages = messages;
    }

    public PublicIssue fromObjectError(
            ObjectError error, String location, Locale locale) {

        String code = frameworkCode(error.getCode());
        String path = error instanceof FieldError field
                ? safePath(field.getField()) : "";

        // Never read getDefaultMessage(), getArguments(),
        // or FieldError.getRejectedValue().
        return issue(code, path, location, locale);
    }

    public PublicIssue fromResolvable(
            MessageSourceResolvable error,
            String path, String location, Locale locale) {

        String code = "INVALID_VALUE";
        String[] candidates = error.getCodes();

        if (candidates != null) {
            for (int i = candidates.length - 1; i >= 0; i--) {
                String raw = candidates[i];
                if (raw == null) {
                    continue;
                }

                int dot = raw.indexOf('.');
                String base = dot >= 0
                        ? raw.substring(0, dot)
                        : raw;
                String mapped = frameworkCode(base);

                if (!"INVALID_VALUE".equals(mapped)) {
                    code = mapped;
                    break;
                }
            }
        }

        return issue(code, path, location, locale);
    }

    public PublicIssue issue(
            String code, String path,
            String location, Locale locale) {

        String approved = PUBLIC_CODES.contains(code)
                ? code : "INVALID_VALUE";
        String approvedPath = safePath(path);
        String message = messages.getMessage(
                "api.error." + approved,
                null,
                "Invalid input",
                locale);

        return new PublicIssue(
                approved, approvedPath, location, message);
    }

    private static String frameworkCode(String code) {
        if (code == null) {
            return "INVALID_VALUE";
        }
        return switch (code) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Email" -> "INVALID_EMAIL";
            case "Pattern" -> "INVALID_FORMAT";
            case "Min" -> "BELOW_MIN";
            case "typeMismatch" -> "INVALID_TYPE";
            default -> "INVALID_VALUE";
        };
    }

    static String safePath(String raw) {
        if (raw == null) {
            return "";
        }

        if ("email".equals(raw)
                || "password".equals(raw)
                || "apiToken".equals(raw)
                || "count".equals(raw)) {
            return raw;
        }

        for (int i = 0; i < 8; i++) {
            if (raw.equals("contacts[" + i + "].name")
                    || raw.equals("contacts[" + i + "].priority")) {
                return raw;
            }
        }

        return "";
    }
}
~~~

**Explanation:**
- `frameworkCode` maps only known source codes; unknowns become `INVALID_VALUE`.
- `fromObjectError` never reads raw rejected values or custom default messages.
- `fromResolvable` picks the base code from Spring's code list without exposing the full array. For direct `@Min`, base code `Min` maps to `BELOW_MIN`.
- `safePath` accepts only approved public paths. Direct comparisons avoid regex-escaping bugs in Java strings.
- `issue` resolves text from the server-owned `MessageSource` using an allowlisted public code. Text is never interpolated with raw user input.
- `location` is passed only as fixed vocabulary by the advice; when adding new input sources, extend the mapping under review.

In larger APIs, `safePath` can derive from API-controlled schema metadata instead of a hardcoded loop, but never replace it with `return raw;`. Map keys, URI template variables, and user-created identifiers can carry private data.

## 7. Controller producing scenarios to test

### 7.1. `RegistrationController.java`

~~~java
// src/main/java/com/example/i18nsafe/RegistrationController.java
package com.example.i18nsafe;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class RegistrationController {

    @InitBinder("registrationForm")
    void configureForm(WebDataBinder binder) {
        binder.setAllowedFields(
                "email", "password", "apiToken",
                "contacts[*].name",
                "contacts[*].priority");
        binder.setAutoGrowCollectionLimit(8);
    }

    @PostMapping(path = "/api/registrations",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> registerJson(
            @Valid @RequestBody RegistrationInput body) {
        return Map.of("accepted", true);
    }

    @PostMapping(path = "/api/registrations/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> registerForm(
            @Valid @ModelAttribute("registrationForm")
            RegistrationInput form) {
        return Map.of("accepted", true);
    }

    @GetMapping("/api/counts")
    public Map<String, Integer> count(
            @RequestParam(name = "count")
            @Min(value = 1, message = "{validation.min}")
            int count) {
        return Map.of("count", count);
    }

    @GetMapping("/api/invalid-return")
    @NotBlank
    public String invalidReturn() {
        return "";
    }
}
~~~

- JSON uses Jackson `@RequestBody`; form uses `@ModelAttribute` and `WebDataBinder`.
- `@InitBinder`/`setAllowedFields` applies only to form property binding, **not as a JSON deserialization allowlist**.
- Direct `@Min` on `@RequestParam` in Spring MVC 6.1+ normally routes through `HandlerMethodValidationException` on failure.
- `@NotBlank` on the return value creates a **server contract failure**; the response must be 500 without revealing method names or return values.
- Do not add `@Validated` on the controller class, as that can route method validation through AOP and alter the exception type.

Never store or return `password`/`apiToken` in successful responses; `{"accepted":true}` is solely for testing. Real products must handle secrets via a service with proper security controls.

## 8. Global exception handler with ProblemDetail

### 8.1. `SafeErrorAdvice.java`

~~~java
// src/main/java/com/example/i18nsafe/SafeErrorAdvice.java
package com.example.i18nsafe;

import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceResolvable;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.ObjectError;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.net.URI;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

@RestControllerAdvice
public class SafeErrorAdvice {

    private final MessageSource messages;
    private final SafeIssueMapper mapper;

    public SafeErrorAdvice(
            MessageSource messages, SafeIssueMapper mapper) {
        this.messages = messages;
        this.mapper = mapper;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> invalidObject(
            MethodArgumentNotValidException ex) {

        Locale locale = LocaleContextHolder.getLocale();
        String location =
                ex.getParameter().hasParameterAnnotation(
                        ModelAttribute.class) ? "form" : "body";

        List<PublicIssue> issues = new ArrayList<>();
        for (ObjectError raw :
                ex.getBindingResult().getAllErrors()) {
            issues.add(mapper.fromObjectError(
                    raw, location, locale));
        }
        return badRequest("INVALID_REQUEST", issues, locale);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> invalidMethod(
            HandlerMethodValidationException ex) {

        if (ex.isForReturnValue()) {
            // Server bug; never return method details or value.
            return internalFailure();
        }

        Locale locale = LocaleContextHolder.getLocale();
        List<PublicIssue> issues = new ArrayList<>();

        for (ParameterValidationResult result :
                ex.getParameterValidationResults()) {

            MethodParameter parameter =
                    result.getMethodParameter();
            String location = locationOf(parameter);
            String path = publicParameterName(parameter);

            if (result instanceof ParameterErrors nested) {
                for (ObjectError raw : nested.getAllErrors()) {
                    issues.add(mapper.fromObjectError(
                            raw, location, locale));
                }
            } else {
                for (MessageSourceResolvable raw :
                        result.getResolvableErrors()) {
                    issues.add(mapper.fromResolvable(
                            raw, path, location, locale));
                }
            }
        }

        for (MessageSourceResolvable ignored :
                ex.getCrossParameterValidationResults()) {
            issues.add(mapper.issue(
                    "INVALID_VALUE", "", "parameter", locale));
        }

        return badRequest("INVALID_REQUEST", issues, locale);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ProblemDetail> queryType(
            MethodArgumentTypeMismatchException ex) {

        Locale locale = LocaleContextHolder.getLocale();
        return badRequest("INVALID_REQUEST",
                List.of(mapper.issue(
                        "INVALID_TYPE", ex.getName(),
                        "query", locale)),
                locale);
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ProblemDetail> missingQuery(
            MissingServletRequestParameterException ex) {

        Locale locale = LocaleContextHolder.getLocale();
        return badRequest("INVALID_REQUEST",
                List.of(mapper.issue(
                        "MISSING_PARAMETER",
                        ex.getParameterName(), "query", locale)),
                locale);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ProblemDetail> malformedJson(
            HttpMessageNotReadableException ignored) {

        Locale locale = LocaleContextHolder.getLocale();
        return badRequest("INVALID_JSON",
                List.of(mapper.issue(
                        "INVALID_JSON", "", "body", locale)),
                locale);
    }

    private ResponseEntity<ProblemDetail> badRequest(
            String code, List<PublicIssue> issues, Locale locale) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setType(URI.create("urn:problem:invalid-request"));
        problem.setTitle(messages.getMessage(
                "api.problem.title", null,
                "Invalid request", locale));
        problem.setDetail(messages.getMessage(
                "api.problem.detail", null,
                "Correct the listed fields.", locale));
        problem.setProperty("code", code);

        List<PublicIssue> sorted = issues.stream()
                .sorted(Comparator
                        .comparing(PublicIssue::location)
                        .thenComparing(PublicIssue::path)
                        .thenComparing(PublicIssue::code))
                .toList();
        problem.setProperty("issues", sorted);

        return ResponseEntity.status(
                HttpStatus.BAD_REQUEST).body(problem);
    }

    private static ResponseEntity<ProblemDetail>
            internalFailure() {

        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setType(URI.create("urn:problem:internal-error"));
        problem.setTitle("Internal error");
        problem.setDetail(
                "The service could not complete the request.");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("issues", List.of());

        return ResponseEntity.status(
                HttpStatus.INTERNAL_SERVER_ERROR).body(problem);
    }

    private static String locationOf(MethodParameter parameter) {
        if (parameter.hasParameterAnnotation(RequestParam.class)) {
            return "query";
        }
        if (parameter.hasParameterAnnotation(ModelAttribute.class)) {
            return "form";
        }
        if (parameter.hasParameterAnnotation(RequestBody.class)) {
            return "body";
        }
        return "parameter";
    }

    private static String publicParameterName(
            MethodParameter parameter) {

        RequestParam annotation =
                parameter.getParameterAnnotation(RequestParam.class);
        if (annotation == null) {
            return "";
        }

        String name = annotation.name().isBlank()
                ? annotation.value() : annotation.name();
        return "count".equals(name) ? "count" : "";
    }
}
~~~

**Nowhere in the advice does it use `ex.getMessage()`, `FieldError#getRejectedValue()`, raw `MessageSourceResolvable#getArguments()`, or nested causes to construct responses.** Errors from JSON parsing, query type mismatches, and missing parameters each have dedicated public mappings.

`HandlerMethodValidationException#isForReturnValue()` is checked before reading errors: return-value validation is a server failure (500), never returned as 400 like client input errors.

`getAllErrors()` covers both field and global errors. For direct method constraints, `ParameterValidationResult#getResolvableErrors()` carries message-resolution codes; the mapper picks only the public code. When `ParameterErrors` contains nested fields, the advice delegates each object error to the mapper. For cross-parameter errors, a generic code and empty path avoid exposing method signatures.

In the demo, `locationOf` covers the active body/form/query sources. When adding header/path/cookie parameters to controllers, extend the annotation mapping explicitly and add tests rather than echoing arbitrary argument names.

**Caveat:** Spring may populate `ProblemDetail.instance` from the request path. Demo routes hold no secrets in URLs. For endpoints with tokens or sensitive data in URIs, fix the route design and control `instance`/logs; never assume ProblemDetail masks path data automatically.

## 9. Message bundles and localization configuration

Place **`messages.properties`**, **`messages_en.properties`**, and **`messages_vi.properties`** at `src/main/resources` root. `messages.properties` acts as the base bundle so Boot auto-creates `MessageSource` and falls back when translations are missing.

**`messages.properties`:**

~~~properties
api.problem.title=Invalid request
api.problem.detail=Correct the listed fields.
api.error.REQUIRED=This field is required
api.error.INVALID_EMAIL=Enter a valid email address
api.error.INVALID_FORMAT=Value has an invalid format
api.error.BELOW_MIN=Value is below the allowed minimum
api.error.INVALID_TYPE=Value has an invalid type
api.error.INVALID_JSON=Request body is not valid JSON
api.error.MISSING_PARAMETER=A required parameter is missing
api.error.INVALID_VALUE=Invalid input
validation.required=This field is required
validation.email=Invalid email
validation.format=Invalid format
validation.min=Value must be at least {value}
~~~

**`messages_en.properties`:**

~~~properties
api.problem.title=Invalid request
api.problem.detail=Correct the listed fields.
api.error.REQUIRED=This field is required
api.error.INVALID_EMAIL=Enter a valid email address
api.error.INVALID_FORMAT=Value has an invalid format
api.error.BELOW_MIN=Value is below the allowed minimum
api.error.INVALID_TYPE=Value has an invalid type
api.error.INVALID_JSON=Request body is not valid JSON
api.error.MISSING_PARAMETER=A required parameter is missing
api.error.INVALID_VALUE=Invalid input
validation.required=This field is required
validation.email=Invalid email
validation.format=Invalid format
validation.min=Value must be at least {value}
~~~

**`messages_vi.properties`:**

~~~properties
api.problem.title=Yêu cầu không hợp lệ
api.problem.detail=Hãy kiểm tra các trường được đánh dấu.
api.error.REQUIRED=Trường này là bắt buộc
api.error.INVALID_EMAIL=Địa chỉ email không hợp lệ
api.error.INVALID_FORMAT=Giá trị sai định dạng
api.error.BELOW_MIN=Giá trị thấp hơn mức tối thiểu
api.error.INVALID_TYPE=Giá trị sai kiểu dữ liệu
api.error.INVALID_JSON=Nội dung JSON không hợp lệ
api.error.MISSING_PARAMETER=Thiếu tham số bắt buộc
api.error.INVALID_VALUE=Dữ liệu không hợp lệ
validation.required=Trường này là bắt buộc
validation.email=Email không hợp lệ
validation.format=Định dạng không hợp lệ
validation.min=Giá trị phải từ {value} trở lên
~~~

**`application.properties`:**

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
~~~

Four points to note:
1. The bundle for `vi-VN` is `messages_vi.properties`; Spring resolves bundles by language/country rules.
2. `spring.messages.fallback-to-system-locale=false` avoids depending on the host machine's locale; unsupported locales fall back to the base bundle.
3. `{value}` in `validation.min` is `@Min(value=1)`'s constraint attribute interpolated by the Bean Validation provider, not raw user input.
4. `server.error.include-*` controls Boot's default error rendering paths, **never replacing a safe mapper** written by the application.

## 10. HTTP tests: English, Vietnamese, and fallback

### 10.1. `SafeErrorIntegrationTest.java`

~~~java
// src/test/java/com/example/i18nsafe/SafeErrorIntegrationTest.java
package com.example.i18nsafe;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeErrorIntegrationTest {

    @Autowired MockMvc mvc;

    private static final String BAD_JSON = """
        {
          "email":"CANARY_EMAIL_77",
          "password":"CANARY_PASSWORD_88!",
          "apiToken":"CANARY_TOKEN_99!",
          "contacts":[{"name":"","priority":0}]
        }
        """;

    @Test
    void englishErrorsKeepCodesAndDoNotLeakCanaries()
            throws Exception {

        mvc.perform(post("/api/registrations")
                    .locale(Locale.US)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(BAD_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.issues.length()").value(5))
                .andExpect(jsonPath("$.issues[*].path", hasItems(
                        "email", "password", "apiToken",
                        "contacts[0].name", "contacts[0].priority")))
                .andExpect(jsonPath("$.issues[*].code", hasItems(
                        "INVALID_EMAIL", "INVALID_FORMAT",
                        "REQUIRED", "BELOW_MIN")))
                .andExpect(jsonPath("$.issues[*].message",
                        hasItem("Enter a valid email address")))
                .andExpect(content().string(not(
                        containsString("CANARY_EMAIL_77"))))
                .andExpect(content().string(not(
                        containsString("CANARY_PASSWORD_88!"))))
                .andExpect(content().string(not(
                        containsString("CANARY_TOKEN_99!"))))
                .andExpect(content().string(not(
                        containsString("rejectedValue"))));
    }

    @Test
    void vietnameseErrorsTranslateButKeepSameCodes()
            throws Exception {

        mvc.perform(post("/api/registrations")
                    .locale(Locale.forLanguageTag("vi-VN"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(BAD_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.title")
                        .value("Yêu cầu không hợp lệ"))
                .andExpect(jsonPath("$.issues[*].code", hasItems(
                        "INVALID_EMAIL", "INVALID_FORMAT",
                        "REQUIRED", "BELOW_MIN")))
                .andExpect(jsonPath("$.issues[*].message",
                        hasItem("Địa chỉ email không hợp lệ")))
                .andExpect(jsonPath("$.issues[*].path",
                        hasItem("contacts[0].priority")))
                .andExpect(content().string(not(
                        containsString("CANARY_EMAIL_77"))))
                .andExpect(content().string(not(
                        containsString("CANARY_PASSWORD_88!"))))
                .andExpect(content().string(not(
                        containsString("CANARY_TOKEN_99!"))));
    }

    @Test
    void unknownLocaleFallsBackToBaseCatalog()
            throws Exception {

        mvc.perform(post("/api/registrations")
                    .locale(Locale.JAPAN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(BAD_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid request"))
                .andExpect(jsonPath("$.issues[*].message",
                        hasItem("Enter a valid email address")));
    }

    @Test
    void formTypeMismatchNeverEchoesBadNumber()
            throws Exception {

        mvc.perform(post("/api/registrations/form")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "lan@example.com")
                    .param("password", "ValidPassword123")
                    .param("apiToken", "TOKENABC123")
                    .param("contacts[0].name", "Lan")
                    .param("contacts[0].priority",
                            "CANARY_BAD_PRIORITY"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("INVALID_TYPE")))
                .andExpect(jsonPath("$.issues[*].path",
                        hasItem("contacts[0].priority")))
                .andExpect(jsonPath("$.issues[*].location",
                        hasItem("form")))
                .andExpect(content().string(not(
                        containsString("CANARY_BAD_PRIORITY"))));
    }

    @Test
    void malformedJsonNeverShowsParserExcerpt()
            throws Exception {

        mvc.perform(post("/api/registrations")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"email":"CANARY_JSON_EXCERPT",
                         "password":[
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("INVALID_JSON"))
                .andExpect(content().string(not(
                        containsString("CANARY_JSON_EXCERPT"))))
                .andExpect(content().string(not(
                        containsString("JsonParseException"))));
    }

    @Test
    void wrongQueryTypeDoesNotEchoValue() throws Exception {
        mvc.perform(get("/api/counts")
                    .param("count", "CANARY_QUERY_12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].code")
                        .value("INVALID_TYPE"))
                .andExpect(jsonPath("$.issues[0].path").value("count"))
                .andExpect(content().string(not(
                        containsString("CANARY_QUERY_12"))));
    }

    @Test
    void missingQueryGetsStableCode() throws Exception {
        mvc.perform(get("/api/counts"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues[0].path").value("count"));
    }

    @Test
    void minViolationUsesVietnameseMessageAndPublicCode()
            throws Exception {
        mvc.perform(get("/api/counts")
                    .locale(Locale.forLanguageTag("vi-VN"))
                    .param("count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].code")
                        .value("BELOW_MIN"))
                .andExpect(jsonPath("$.issues[0].path")
                        .value("count"))
                .andExpect(jsonPath("$.issues[0].message")
                        .value("Giá trị thấp hơn mức tối thiểu"));
    }

    @Test
    void invalidReturnIsInternalErrorWithoutDetails()
            throws Exception {
        mvc.perform(get("/api/invalid-return"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.issues.length()").value(0))
                .andExpect(content().string(not(
                        containsString("invalidReturn"))))
                .andExpect(content().string(not(
                        containsString("HandlerMethodValidationException"))));
    }

    @Test
    void validJsonAndFormDoNotEchoCredentials()
            throws Exception {
        mvc.perform(post("/api/registrations")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"email":"lan@example.com",
                         "password":"ValidPassword123",
                         "apiToken":"TOKENABC123",
                         "contacts":[{"name":"Lan","priority":1}]}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true))
                .andExpect(content().string(not(
                        containsString("ValidPassword123"))));

        mvc.perform(post("/api/registrations/form")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "lan@example.com")
                    .param("password", "ValidPassword123")
                    .param("apiToken", "TOKENABC123")
                    .param("contacts[0].name", "Lan")
                    .param("contacts[0].priority", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }
}
~~~

**These are 10 test methods**, with the last test executing two HTTP requests. Negative assertions across the entire response body catch markers even if injected into `message`, `detail`, or extension fields. Positive assertions ensure the API still returns useful codes/paths/messages instead of "fixing security" by returning empty bodies.

There is no need to assert Bean Validation violation ordering: use `hasItems` on the issues array rather than relying on `issues[0]`. The exception advice sorts for deterministic output, yet clients should still identify errors by `path` + `code`.

`MockMvc.locale(...)` tests request locale inside MVC. When running behind reverse proxies or custom resolvers in production, add tests sending real `Accept-Language` headers to verify the locale source.

## 11. Unit tests: leaked data inside defaultMessage or path

### 11.1. `SafeIssueMapperTest.java`

~~~java
// src/test/java/com/example/i18nsafe/SafeIssueMapperTest.java
package com.example.i18nsafe;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.FieldError;

import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class SafeIssueMapperTest {

    @Test
    void rejectedValueAndUnsafeDefaultMessageStayPrivate()
            throws Exception {

        String marker = "CANARY_REJECTED_PASSWORD_501";
        FieldError raw = new FieldError(
                "registrationInput",
                "password",
                marker,
                false,
                new String[]{"Pattern"},
                null,
                "Unsafe validation message: " + marker);

        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("api.error.INVALID_FORMAT",
                Locale.US, "Value has an invalid format");

        PublicIssue safe = new SafeIssueMapper(catalog)
                .fromObjectError(raw, "body", Locale.US);

        String json = new ObjectMapper()
                .writeValueAsString(safe);

        assertEquals("INVALID_FORMAT", safe.code());
        assertEquals("password", safe.path());
        assertEquals("Value has an invalid format",
                safe.message());
        assertFalse(json.contains(marker));
        assertFalse(json.contains("Unsafe validation message"));
        assertFalse(json.contains("rejectedValue"));
    }

    @Test
    void privateMapKeyIsNotAPublicPath() throws Exception {
        String key = "private-email@example.com";

        FieldError raw = new FieldError(
                "registrationInput",
                "contacts[" + key + "].name",
                "CANARY_PRIVATE_VALUE",
                false,
                new String[]{"NotBlank"},
                null,
                "CANARY_PRIVATE_VALUE");

        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("api.error.REQUIRED",
                Locale.US, "This field is required");

        PublicIssue safe = new SafeIssueMapper(catalog)
                .fromObjectError(raw, "body", Locale.US);

        String json = new ObjectMapper()
                .writeValueAsString(safe);
        assertEquals("", safe.path());
        assertEquals("REQUIRED", safe.code());
        assertFalse(json.contains(key));
        assertFalse(json.contains("CANARY_PRIVATE_VALUE"));
    }

    @Test
    void codesAndPathsStaySameAcrossLocales() {
        Locale vi = Locale.forLanguageTag("vi-VN");
        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("api.error.INVALID_FORMAT",
                Locale.US, "Value has an invalid format");
        catalog.addMessage("api.error.INVALID_FORMAT",
                vi, "Giá trị sai định dạng");

        FieldError raw = new FieldError(
                "registrationInput", "password",
                "CANARY_SENSITIVE",
                false,
                new String[]{"Pattern"},
                null,
                "CANARY_SENSITIVE");

        SafeIssueMapper mapper = new SafeIssueMapper(catalog);
        PublicIssue en = mapper.fromObjectError(
                raw, "body", Locale.US);
        PublicIssue vietnamese = mapper.fromObjectError(
                raw, "body", vi);

        assertEquals(en.code(), vietnamese.code());
        assertEquals(en.path(), vietnamese.path());
        assertEquals("Value has an invalid format",
                en.message());
        assertEquals("Giá trị sai định dạng",
                vietnamese.message());
    }
}
~~~

**These three unit tests need no HTTP server.** They force the mapper to handle a `FieldError` where:
- `rejectedValue` carries a sensitive marker;
- `defaultMessage` intentionally contains the same marker;
- `field path` embeds an email inside a Map key.

The mapper still emits only the approved code/path/message. An HTTP test alone is hard to craft for all these synthetic shapes, so both layers complement each other.

## 12. Testing Bean Validation interpolation separately

### 12.1. `BeanValidationLocaleTest.java`

~~~java
// src/test/java/com/example/i18nsafe/BeanValidationLocaleTest.java
package com.example.i18nsafe;

import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;

import java.util.List;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class BeanValidationLocaleTest {

    @Autowired Validator validator;

    private RegistrationInput inputWithBadEmail() {
        ContactInput contact = new ContactInput();
        contact.setName("Lan");
        contact.setPriority(1);

        RegistrationInput input = new RegistrationInput();
        input.setEmail("CANARY_BAD_EMAIL");
        input.setPassword("ValidPassword123");
        input.setApiToken("TOKENABC123");
        input.setContacts(List.of(contact));
        return input;
    }

    private String emailMessage() {
        return validator.validate(inputWithBadEmail()).stream()
                .filter(v -> "email".equals(
                        v.getPropertyPath().toString()))
                .findFirst()
                .orElseThrow()
                .getMessage();
    }

    @Test
    void vietnameseConstraintMessage() {
        LocaleContext previous =
                LocaleContextHolder.getLocaleContext();
        try {
            LocaleContextHolder.setLocale(
                    Locale.forLanguageTag("vi-VN"));
            assertEquals("Email không hợp lệ", emailMessage());
        } finally {
            LocaleContextHolder.setLocaleContext(previous);
        }
    }

    @Test
    void englishConstraintMessage() {
        LocaleContext previous =
                LocaleContextHolder.getLocaleContext();
        try {
            LocaleContextHolder.setLocale(Locale.US);
            assertEquals("Invalid email", emailMessage());
        } finally {
            LocaleContextHolder.setLocaleContext(previous);
        }
    }
}
~~~

These are **two tests directly on the Spring-managed Jakarta Validator**, verifying `{validation.email}` interpolates by locale. Do not use plain `Validation.buildDefaultValidatorFactory()` outside the Spring context when testing Spring `MessageSource` integration.

`LocaleContextHolder.setLocaleContext(previous)` restores the original context so other tests are not polluted. For asynchronous/reactive code, also test context propagation separately.

If direct validation tests pass while HTTP API messages are wrong, suspect the locale resolver, advice, or mapper. If API messages pass while direct constraint interpolation fails, `api.error.*` in the mapper may work while `validation.*` is unresolved. Never use one layer as proof for the other.

## 13. Running tests and reading results accurately

| Class | Tests |
| --- | ---: |
| `SafeErrorIntegrationTest` | 10 |
| `SafeIssueMapperTest` | 3 |
| `BeanValidationLocaleTest` | 2 |
| **Expected total** | **15** |

Run all:

~~~bash
mvn test
~~~

Run integration tests only:

~~~bash
mvn -Dtest=SafeErrorIntegrationTest test
~~~

Run mapper and message tests only:

~~~bash
mvn -Dtest=SafeIssueMapperTest,BeanValidationLocaleTest test
~~~

**Expected outcome: 15 JUnit tests PASS** per the code and APIs shown, though this is **not an executed Maven log**. In real CI, rely on Surefire XML reports and logs to verify outcomes; never mark unexecuted tests as "PASS".

Run the application:

~~~bash
mvn spring-boot:run
~~~

Example Vietnamese request:

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi-VN" \
  -d '{"email":"CANARY_EMAIL_77",
       "password":"CANARY_PASSWORD_88!",
       "apiToken":"CANARY_TOKEN_99!",
       "contacts":[{"name":"","priority":0}]}'
~~~

The expected HTTP 400 response contains `code="INVALID_REQUEST"` and Vietnamese issues, **with zero `CANARY_*` strings**. On PowerShell, line continuation and JSON escaping differ from Linux/macOS/Git Bash; use `curl.exe` or an appropriate single-line command.

## 14. Additional test scenarios needed in production

### 14.1. Request locales and fallback

Do not test only `en-US` and `vi-VN`. Include an untranslated locale (e.g., `ja-JP`) and verify base English fallback; test a key present in the base bundle yet missing in `messages_vi`. If the product requires different locale-specific fallback behavior, configure it explicitly and add tests.

A useful metamorphic test:

~~~text
Same invalid request + locale en-US
    -> issue identity set A (code, path, location)

Same invalid request + locale vi-VN
    -> issue identity set A

Only title/detail/message may differ by locale.
~~~

When multiple errors exist, never convert to `Map<path,message>`, as that drops simultaneous violations on the same field. Bean Validation violation ordering is not a contract; normalize/sort when the product requires deterministic output.

### 14.2. Unicode and encoding

Test inputs with emojis, Vietnamese names, combining accents, Unicode escapes, non-breaking spaces, and control characters. Use UTF-8 for resource bundles, response serialization, and test fixtures. Never assume JS and Java strings are identical across all normalization forms. When verifying markers do not leak, account for whether transport encodes/escapes markers; check both the decoded response body and parsed JSON model when appropriate.

### 14.3. Indexed paths and Map keys

Test `contacts[0].name`, `contacts[7].priority`, `contacts[8].name`, negative indexes, and keys containing emails/tokens. `safePath` allows only public identities; unapproved paths must collapse to an empty string or placeholder. If the product allows dynamic map keys, canonicalize keys or assign public IDs instead of echoing raw keys just for UI highlighting.

### 14.4. Malformed JSON and type mismatch

Syntactically invalid JSON typically raises `HttpMessageNotReadableException` before Jakarta Bean Validation runs. Form `priority=abc` is handled by `WebDataBinder` and can record `typeMismatch` in `BindingResult`. Query `count=abc` can raise `MethodArgumentTypeMismatchException`. **These three failures must not be forced into one ConstraintViolation category**.

Test status, code, path/location, and absence of raw input/parser details. Never return `ex.getMostSpecificCause()` or Jackson snippets in public messages.

### 14.5. Method input vs return validation

Spring MVC 6.1+ provides built-in method validation; input constraints normally return 400. A failing return-value constraint is a **server error**, typically 500. In advice, check `isForReturnValue()` before building issues so server Java method names, values, or constraint details never leak.

Adding `@Validated` at the controller class level can switch method validation to AOP and change the exception type. Whenever changing it, re-run integration tests against the real Spring context rather than editing tests to silence errors.

### 14.6. The response body is not the only place leaks happen

Check:
- `ProblemDetail.instance`: Spring can populate the request path; never put secrets in URLs.
- Access/proxy logs: raw queries, cookies, and Authorization headers.
- Exception logs: `FieldError#toString()` and `BindException#getMessage()` can carry rejected values.
- APM/traces/metrics: tag only public codes, statuses, and route templates—never raw inputs.
- Caching: responses localized by `Accept-Language` need proper cache policies/`Vary` headers, and endpoints handling private data should generally not cache errors.
- Frontend rendering: escape message text; never insert response strings into unsafe `innerHTML`.

Boot settings like `server.error.include-message=never` do not replace a safe mapper. A custom `@RestControllerAdvice` returning raw objects can still leak data regardless of those settings.

### 14.7. Volume and denial-of-service

A request with thousands of invalid list elements creates many issues. Production requires bounds on HTTP body size, form parameter counts, nesting depth, and collection auto-growth. Consider a truncation policy (e.g., max 50 issues) with a contracted `truncated` flag. Never try serializing arbitrary numbers of `ConstraintViolation`s or huge nested objects.

## 15. Troubleshooting table

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| UI is in Vietnamese but API errors are in English | Advice uses default locale | Use request locale and `MessageSource` |
| Violation message renders literally as `{validation.email}` | Missing bundle or validator wiring | Test injected Spring `Validator` |
| Error codes change when translated | Code derived from message text | Map framework code → public code |
| `messages_vi` is ignored | Wrong filename/path/encoding | `src/main/resources/messages_vi.properties`, UTF-8 |
| Unsupported locale uses server language | Fallback to JVM default | Verify `fallback-to-system-locale=false` |
| Secret appears in `message` | Custom validator embeds raw input | Load public messages from vetted catalog |
| Secret appears in `path` | Echoed client Map key | Allowlist/canonicalize paths |
| `rejectedValue` property present in response | Returned raw `FieldError` | Use a dedicated public DTO |
| JSON parse failure returns parser excerpt | Returned exception cause/`getMessage` | Return generic `INVALID_JSON` from handler |
| Form wrong type differs from JSON wrong type | Two different binding pipelines | Test converter vs Jackson separately |
| Direct query `@Min` misses expected handler | Class-level `@Validated` or version mismatch | Test MVC built-in validation and check AOP |
| Return validation returns 400 | Handler did not separate input/return | `isForReturnValue()` → 500 |
| HTTP tests pass while logs leak | Logging raw exceptions/headers | Audit filters, gateways, and APM |
| Adding a new locale breaks tests | Different catalog/fallback behavior | Test key coverage and fallback |
| Tests depend on error ordering | Used `issues[0]` for multiple violations | Assert sets or sorted contract |
| Only mapper unit tests pass | Another handler still returns raw errors | End-to-end MockMvc integration tests |
| Field path missing when unknown | Strict allowlist in mapper | If intentional to open, update public schema + tests |
| Vietnamese accents garbled | Inconsistent encoding | Use UTF-8 and test Unicode |
| Password appears in 200 response | Controller echoes full input | Return DTO containing only required fields |

## 16. Practice exercises

1. Add `@Size(min=12,max=40)` to password. Add public code `INVALID_LENGTH` and translate en/vi; never expose raw regex/descriptors.
2. Create a custom validator whose default message intentionally includes `CANARY_CUSTOM_VALUE`. Verify the mapper ignores the default message.
3. Write a `@ParameterizedTest` across `en-US`, `vi-VN`, `fr-FR`, and an unsupported locale, asserting invariant codes/paths.
4. Test `contacts[7].name` and `contacts[8].name`; verify path limits and auto-growth.
5. Pass an email-like Map key, test path normalization, and assert the key is absent from the response.
6. Write a `@RestControllerAdvice` for WebFlux using `WebTestClient` and reactive locale context propagation.
7. Write a test capturing logs to verify no rejected values or Authorization headers are logged.
8. Upgrade Spring/Jakarta providers on a test branch; compare exception mappings and messages across versions.
9. Check whether localized responses risk wrong-language CDN caching; design appropriate cache headers.
10. Trigger a JSON parser failure inside nested arrays carrying a Unicode secret marker; verify the decoded response body.

## 17. Adoption checklist

- [ ] Public error schema includes only approved codes/paths/locations/messages/metadata, no framework objects.
- [ ] Never read `getRejectedValue()`, `getInvalidValue()`, raw `getArguments()`, or raw `Exception#getMessage()`.
- [ ] Never trust `FieldError#getDefaultMessage()` when custom validators might embed user input.
- [ ] Error codes remain stable across locales without exposing Java class/method names from `getCodes()`.
- [ ] Paths and Map keys are allowlisted/canonicalized, preserving nested indexes only when permitted.
- [ ] Messages come from a server-controlled `MessageSource` with tested fallback.
- [ ] Bean Validation `validation.*` interpolation and public API `api.error.*` translation are tested separately.
- [ ] MockMvc tests assert both positive code/path/message and absence of canaries across the **entire response**.
- [ ] Tests cover invalid JSON/form/query, missing parameters, direct method validation, and 500 return-value failures.
- [ ] No real credentials appear in fixtures, CI reports, or logs.
- [ ] No raw requests, rejected values, stack traces, or exception messages enter public telemetry.
- [ ] ProblemDetail `instance`, per-locale caching, and frontend escaping are verified.
- [ ] Request size, nesting, collection length, and issue count are bounded where needed.
- [ ] Re-run all integration regression tests after upgrading Spring/Boot/Jackson/validators.

## 18. Conclusion

A high-quality Spring API satisfies two properties at the same time:

~~~text
Same error + different locales:
    code/path unchanged
    message/title/detail accurately translated

Same error + raw input containing sensitive values:
    safe mapper + allowlist + message catalog
    -> zero raw values/internal exceptions in response
~~~

Localization without data masking can leak passwords inside translated messages. Masking data while dropping codes/paths leaves clients unable to tell which field to fix. Combining **stable public codes, reliable message sources, path allowlists, and unit + HTTP tests** preserves both multilingual UX and data safety.

## 19. References

- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — Error Responses and ProblemDetail: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — FieldError Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 — ObjectError Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html
- Spring Framework 6.2 — HandlerMethodValidationException Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 — ParameterValidationResult Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Boot 3.5 — Bean Validation MessageSource integration: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Internationalization: https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html
- Jakarta Bean Validation 3.1 specification: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- OWASP Developer Guide — Handle all Errors and Exceptions: https://devguide.owasp.org/en/04-design/02-web-app-checklist/10-handle-errors-exceptions/
- MITRE CWE-209 — Error messages containing sensitive information: https://cwe.mitre.org/data/definitions/209.html
