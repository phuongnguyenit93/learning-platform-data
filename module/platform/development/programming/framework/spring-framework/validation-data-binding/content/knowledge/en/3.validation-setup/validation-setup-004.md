# Configuring LocalValidatorFactoryBean Using Java Configuration in Spring Framework

`LocalValidatorFactoryBean` is the bridge between **Jakarta Bean Validation** and the **Spring Validation** system. When configuring via Java, you declare it as a Spring bean using `@Configuration` and `@Bean`, and you can then use the same validator at the Spring MVC layer and in services that need to validate objects.

Lesson goals: create and customize `LocalValidatorFactoryBean` using Java Configuration; understand the relationship between Spring `Validator`, Jakarta `Validator`, and the Bean Validation provider; wire the validator into Spring MVC; configure error messages via `MessageSource`; know when manual configuration is needed, how to test it, and how to avoid common integration pitfalls.

## 1. Understanding the Role of LocalValidatorFactoryBean

An HTTP request may be deserialized into a Java object while still violating constraints—such as a blank name or an age that is too young. Annotations like `@NotBlank`, `@Email`, and `@Min` describe **rules**; a Bean Validation provider (typically Hibernate Validator) performs **rule evaluation**. Spring needs a way to connect that provider to object validation, data binding, and MVC.

```text
DTO with jakarta.validation.constraints.* annotations
          │
          ▼
      @Valid / @Validated
          │
          ▼
Spring MVC / Spring Validation needs a Validator
          │
          ▼
LocalValidatorFactoryBean (Spring bean)
          │ initializes and manages ValidatorFactory
          ▼
Jakarta Bean Validation provider (e.g., Hibernate Validator)
          │
          ▼
ConstraintViolation / Spring Errors / BindingResult
```

Components to distinguish:

| Component | Role |
| --- | --- |
| `jakarta.validation.Valid` | Requests constraint validation of an object or nested validation; it is not a constraint itself. |
| `jakarta.validation.constraints.*` | Annotations declaring validity conditions, such as `@NotBlank` or `@Min`. |
| `jakarta.validation.Validator` | Jakarta API for calling `validate(object)` and receiving `Set<ConstraintViolation<T>>`. |
| `org.springframework.validation.Validator` | Spring's contract with `supports(Class<?>)` and `validate(Object, Errors)`; used for binding/MVC integration. |
| `LocalValidatorFactoryBean` | Adapter implementing both validator roles mentioned above, while also managing `jakarta.validation.ValidatorFactory`. |
| Bean Validation provider | Actual implementation executing constraints; having only the annotations/API without a provider is insufficient. |
| `WebMvcConfigurer#getValidator()` | Extension point to declare the global validator that Spring MVC will use. |

`LocalValidatorFactoryBean` extends `SpringValidatorAdapter` and also provides `SmartValidator`. When Spring manages the bean, initialization invokes `afterPropertiesSet()` to bootstrap the validator factory; when the context closes, Spring invokes the destruction callback. Therefore, **do not call lifecycle methods manually** and do not instantiate `new LocalValidatorFactoryBean()` per request.

## 2. When Is Java Configuration Needed?

If a Bean Validation provider is already on the classpath, Spring MVC usually creates a global validator automatically for `@Valid` and `@Validated`. Spring Boot provides a validation starter to supply the standard configuration. **Manually declaring `LocalValidatorFactoryBean` is not mandatory for every project.**

Java configuration is useful when you need to:

- Register a `Validator` bean to inject into other components and manage it explicitly.
- Customize validation message content through Spring's `MessageSource` or provider-specific settings.
- Explicitly specify the validator Spring MVC uses, instead of relying on the default choice.
- Configure advanced settings such as the provider, mappings, `ConstraintValidatorFactory`, or validation configuration properties.

The examples below use **Spring Framework 6.x / Spring Boot 3.x and Java 17+**, so annotations belong to the `jakarta.validation` namespace. In Spring Framework 5 / Boot 2, the namespace was `javax.validation`; do not mix the two at compile time.

### Required Dependencies

In a Spring Boot 3.x project configured with the Spring Boot Gradle plugin, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

The web starter provides Spring MVC and HTTP/JSON infrastructure; the validation starter provides the API together with a Bean Validation provider matching the Boot version. In a plain Spring Framework project, you must supply `spring-webmvc`, the Jakarta Validation API, and a compatible provider yourself. A missing-provider error cannot be solved merely by adding the `@Valid` annotation.

## 3. Basic Configuration with @Configuration and @Bean

The simplest case only needs defining the bean:

```java
package demo.validation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class BasicValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

This is **a Java configuration file**, not a standalone program with `main`. Spring must scan/register the `@Configuration` class in the application context. The `validator` bean is then created exactly once in the default singleton scope, receives lifecycle callbacks, and can be injected elsewhere.

For example, a service wishing to validate a DTO manually can inject `jakarta.validation.Validator`:

```java
package demo.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class InputCheckService {

    private final Validator validator;

    public InputCheckService(Validator validator) {
        this.validator = validator;
    }

    public <T> Set<ConstraintViolation<T>> check(T input) {
        return validator.validate(input);
    }
}
```

`validate` returns the set of violations; it **does not automatically turn service-level checks into HTTP 400**, does not persist data, and does not replace business rules. When using constructor injection, ensure there is only one matching bean or explicitly indicate the preferred bean.

To guarantee that **Spring MVC** uses the customized validator, you can implement `WebMvcConfigurer` and return the validator in `getValidator()`. The complete example next illustrates both this wiring and `MessageSource` usage.

## 4. Complete Example: Java Config Validator with Vietnamese Messages

File structure in a Spring Boot 3.x project:

```text
src/main/
├── java/demo/validation/
│   ├── ValidationDemoApplication.java
│   ├── ValidationConfiguration.java
│   ├── RegistrationRequest.java
│   ├── RegistrationController.java
│   └── ValidationErrorHandler.java
└── resources/
    └── messages.properties
```

### 4.1. Application Entry Point

File `src/main/java/demo/validation/ValidationDemoApplication.java`:

```java
package demo.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}
```

This class is placed in the same package as the remaining components so Spring Boot's component scanning discovers the controller, advice, and configuration.

### 4.2. Declaring MessageSource and LocalValidatorFactoryBean

File `src/main/java/demo/validation/ValidationConfiguration.java`:

```java
package demo.validation;

import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.context.support.ReloadableResourceBundleMessageSource;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ValidationConfiguration implements WebMvcConfigurer {

    @Bean
    public MessageSource messageSource() {
        ReloadableResourceBundleMessageSource source =
                new ReloadableResourceBundleMessageSource();
        source.setBasename("classpath:messages");
        source.setDefaultEncoding("UTF-8");
        return source;
    }

    @Bean
    @Primary
    public LocalValidatorFactoryBean validator() {
        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setValidationMessageSource(messageSource());
        return factory;
    }

    @Override
    public Validator getValidator() {
        return validator();
    }
}
```

Meaning of each point:

1. `@Configuration` registers the configuration class in the Spring application context.
2. `messageSource()` declares a bean reading messages from `messages.properties`. We use `ReloadableResourceBundleMessageSource` and explicitly set UTF-8 so we can write Vietnamese messages.
3. `validator()` creates `LocalValidatorFactoryBean` once and calls `setValidationMessageSource(...)` so message codes in constraints are resolved via Spring's `MessageSource`.
4. `@Primary` prioritizes this bean when an injection point requests a validator type and multiple matching beans exist. This annotation **does not replace** specifying MVC's global validator.
5. `getValidator()` is a method of `WebMvcConfigurer`; Spring MVC calls it to use the configured validator as the global validator.

In this example, `getValidator()` calls `validator()` and `validator()` calls `messageSource()`. This is safe because `@Configuration` uses the default proxy bean methods mode: `@Bean` method calls within the same class are routed by Spring to the managed singleton bean. **If changed to `@Configuration(proxyBeanMethods = false)`, do not invoke bean methods directly like this**; switch to dependency injection between configuration classes or use `ObjectProvider`. Do not arbitrarily change the proxy mode; keep the code above as shown.

### 4.3. Declaring the DTO and Constraints

File `src/main/java/demo/validation/RegistrationRequest.java`:

```java
package demo.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationRequest(
        @NotBlank(message = "{registration.name.required}")
        String name,

        @NotBlank(message = "{registration.email.required}")
        @Email(message = "{registration.email.invalid}")
        String email,

        @NotNull(message = "{registration.age.required}")
        @Min(value = 18, message = "{registration.age.min}")
        Integer age
) {}
```

The codes in `message = "{...}"` are not hardcoded Vietnamese text in Java. The validator resolves those codes via the configured message interpolation mechanism. Here `Integer` is used so `@NotNull` detects a missing `age` field; `@Min` does not by itself require a non-`null` value.

File `src/main/resources/messages.properties`:

```properties
registration.name.required=Tên không được để trống
registration.email.required=Email không được để trống
registration.email.invalid=Email không đúng định dạng
registration.age.required=Tuổi là bắt buộc
registration.age.min=Phải đủ 18 tuổi
```

Message codes must match **exactly** between `message` on the DTO and the keys in the properties file. Do not set `setUseCodeAsDefaultMessage(true)` on the `MessageSource` used here: it can prevent interpolation from properly falling back to Hibernate Validator's standard messages. If multiple languages are needed, you can add locale-specific bundles such as `messages_en.properties` and verify locale selection in the application.

### 4.4. Using the Validator in Spring MVC

File `src/main/java/demo/validation/RegistrationController.java`:

```java
package demo.validation;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @PostMapping
    public ResponseEntity<Map<String, String>> register(
            @Valid @RequestBody RegistrationRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED).body(
                Map.of("status", "accepted", "name", request.name()));
    }
}
```

When receiving syntactically valid JSON that can be deserialized into `RegistrationRequest`, Spring runs the Bean Validation constraints because the parameter has `@Valid`. If valid, the controller returns HTTP 201. This is an illustrative endpoint: **it does not persist to a database, does not check for duplicate emails, and has no real registration business logic**.

### 4.5. Returning Structured Validation Errors

If no custom handler is defined, Spring MVC typically returns HTTP 400 when `@Valid @RequestBody` fails, though the default error body varies by version and configuration. To illustrate customized messages, create `src/main/java/demo/validation/ValidationErrorHandler.java`:

```java
package demo.validation;

import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationErrorHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> invalid(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> errors = exception
                .getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "message", error.getDefaultMessage() == null
                                ? "Invalid data"
                                : error.getDefaultMessage()))
                .toList();

        Map<String, Object> body = Map.of("errors", errors);
        return ResponseEntity.badRequest().body(body);
    }
}
```

`MethodArgumentNotValidException` is the typical exception when a `@RequestBody` object annotated with `@Valid` violates Bean Validation. The handler above returns field names along with interpolated messages. The ordering of multiple errors is not a contract to depend on; in a real application, you can sort errors by field name and standardize custom error codes. You also need separate handling for unreadable JSON errors, type conversion errors, and method validation cases.

## 5. Running and Verifying End-to-End

In a project configured with the Spring Boot Gradle plugin, run:

```bash
./gradlew bootRun
```

The following commands use Bash or Git Bash; equivalent JSON payloads can be sent via another HTTP client.

**Valid case:**

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","age":20}'
```

Expect HTTP **201 Created**. The response JSON contains `status` equal to `"accepted"` and `name` equal to `"Lan"` (key order in JSON may vary).

**Single constraint violation case:**

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":" ","email":"lan@example.com","age":20}'
```

Expect HTTP **400 Bad Request** with error details for the `name` field:

```json
{"errors":[{"field":"name","message":"Tên không được để trống"}]}
```

This verifies the entire chain: `@Valid` triggers validation → `LocalValidatorFactoryBean` invokes the provider → the message key is looked up via `MessageSource` → `ValidationErrorHandler` extracts the result and builds JSON.

**Multiple constraint violations case:**

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"","email":"bad-email","age":16}'
```

Expect HTTP 400 and three corresponding messages for `name`, `email`, and `age`. The order of items in `errors` is not fixed; do not write tests relying on that order.

**Pre-validation failure case:**

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","age":"abc"}'
```

For type `Integer`, the string `"abc"` cannot be converted to an age value. Spring/Jackson typically reports a body reading or conversion error (`HttpMessageNotReadableException`) and HTTP 400; the handler dedicated to `MethodArgumentNotValidException` above **does not handle this error**. That distinguishes input syntax/type errors from constraint violations on a successfully constructed DTO.

## 6. Where the Bean Is Used and Integration Approaches

### 6.1. Global Validator in Spring MVC

`WebMvcConfigurer#getValidator()` selects the validator applied to MVC's object validation pipeline. When `@Valid` appears on `@RequestBody`, `@ModelAttribute`, or `@RequestPart` in supported cases, MVC delegates validation to the appropriate validator. Some cases with `BindingResult` placed immediately after the target object can capture errors for the controller to handle instead of throwing an exception.

Do not add `@EnableWebMvc` to a **Spring Boot** application just to configure a validator: that annotation hands MVC configuration control to the application and alters many of Boot's auto-configuration mechanisms. In a plain Spring MVC application managed with Java Configuration, `@EnableWebMvc` can be part of the MVC setup. The Boot example above only needs `@Configuration` and `WebMvcConfigurer`.

### 6.2. Injected Validator for Manual Checks

You can inject the same bean via `jakarta.validation.Validator` or `LocalValidatorFactoryBean` to validate objects outside controllers. Calling `validator.validate(entity)` returns a set of `ConstraintViolation`, not a `BindingResult`. If those violations need to be translated into business logic or HTTP responses, the caller layer must decide how to process the violation set.

At the same time, `LocalValidatorFactoryBean` also implements Spring's `Validator`/`SmartValidator` API, suitable for integration with `Errors` and `DataBinder`. Import the right type for the method being used:
- `org.springframework.validation.Validator` for `WebMvcConfigurer#getValidator()`.
- `jakarta.validation.Validator` for `validate(object)` and `ConstraintViolation`.
- `jakarta.validation.Valid` for the DTO validation annotation.

### 6.3. Local Validators and Method Validation

Alongside the global validator, a controller can register additional Spring `Validator` instances using `@InitBinder` when a form has specialized binding rules. This does not require creating a separate global validator.

Validating constraints placed directly on method parameters, such as `@RequestParam @Min(1) int page`, belongs to **method validation** and can raise `HandlerMethodValidationException` in Spring MVC 6.1+. On services, `@Validated` combined with the appropriate method validation/AOP infrastructure is a separate topic; having a `LocalValidatorFactoryBean` bean does not guarantee every service method is automatically intercepted and checked. When building a unified error API, consider both `MethodArgumentNotValidException` and `HandlerMethodValidationException` if controller signatures use both validation styles.

## 7. Advanced Configurations and Their Limitations

### 7.1. Messages and Interpolation

`setValidationMessageSource(MessageSource)` lets you reuse Spring message bundles instead of relying solely on Bean Validation's default `ValidationMessages.properties`. This feature relies on Hibernate Validator's interpolation support; if switching providers, verify compatibility. Do not configure `setValidationMessageSource(...)` and `setMessageInterpolator(...)` simultaneously because they are two ways of controlling the same interpolator component.

If the project only needs standard messages, omitting `setValidationMessageSource` and using `new LocalValidatorFactoryBean()` is sufficient. If an existing `messageSource` bean is already provided by the application, **reuse the existing bean** rather than declaring another bean with the same name. The example above declares one explicitly so it is easy to understand and runs standalone in the sample project.

### 7.2. Provider, Mappings, and Other Settings

`LocalValidatorFactoryBean` provides extension points such as `setProviderClass(...)` to specify a compatible provider, `setMappingLocations(...)` to load XML constraint mappings, `setConstraintValidatorFactory(...)` to customize how constraint validators are instantiated, and `setValidationPropertyMap(...)` to pass configuration properties to the provider. Do not use these methods merely to "enable @Valid": basic applications generally do not need them.

By default, the factory supports Spring-integrated `ConstraintValidator` instantiation so custom validators can use dependency injection. Replacing `ConstraintValidatorFactory` without reason can break injection of required dependencies. Provider-specific properties for Hibernate Validator must be checked against the running provider version.

### 7.3. Multiple Validator Beans and Bean Selection

There may be a default validator built by MVC, an application-defined validator, or a controller-local validator. `@Primary` resolves priority for **type-based dependency injection**, while `getValidator()` specifies **MVC's global validator**. If multiple `WebMvcConfigurer` classes each return different validators, choosing a single global validator can become confusing; centralize this configuration in one intentional place.

## 8. Testing the Configuration: What Should Be Proven?

Do not stop at verifying that the application context starts up. An application integration test should prove:

| Scenario | Expected verification outcome |
| --- | --- |
| Valid JSON | Controller is invoked; response succeeds per contract. |
| `name` contains only whitespace | Returns 400 and the message from `messages.properties`. |
| Malformed `email` | Violates `@Email`; does not reach success handling. |
| `age` missing or under 18 | Rejected by `@NotNull` or `@Min` respectively. |
| `age` cannot decode to `Integer` | Conversion/body error, distinct from `MethodArgumentNotValidException`. |
| Injecting `jakarta.validation.Validator` into a service | Appropriate bean exists and `validate(...)` returns expected violations. |
| Using another locale | Expected bundle/language is used if the system supports multiple languages. |

With Spring Boot, you can use `@SpringBootTest` and `MockMvc` to verify validator wiring, HTTP statuses, and response bodies. A test that simply calls `new LocalValidatorFactoryBean()` does not substitute for an integration test because it does not prove MVC is using the configured bean. When pure constraint logic needs testing, a direct test via `jakarta.validation.Validator` is very appropriate.

## 9. Common Errors and How to Diagnose Them

1. **`@Valid` is present but no errors appear:** check starter/provider, DTO types, placement of `@Valid`, and MVC invocation. Do not confuse `javax.validation.*` with `jakarta.validation.*` imports in Spring 6.
2. **Startup fails unable to find a provider:** add a compatible Bean Validation provider; having only the API/annotations is not enough.
3. **Returned message is the raw code in curly braces:** check resource bundle name, keys, encoding, `messageSource` bean, and `setValidationMessageSource` configuration.
4. **Injecting `Validator` is ambiguous:** check the two identically named interfaces, bean count, and apply `@Primary` or `@Qualifier` intentionally.
5. **`getValidator()` creates a different object from the injected bean:** check whether `new` is called each time or `@Configuration(proxyBeanMethods = false)` is used while invoking `@Bean` methods directly.
6. **Adding `@EnableWebMvc` changes Boot's behavior:** use `WebMvcConfigurer` to extend rather than unintentionally replacing Boot-provided MVC configuration.
7. **Catching only `MethodArgumentNotValidException` misses other errors:** type conversion/body reading errors and method validation throw their own exceptions; standardize responses per group.
8. **Using Bean Validation for all business rules:** DTO constraints do not replace authentication, authorization, duplicate checks, or database invariants.
9. **Using `@NotNull` on a string thinking it forbids empty strings:** use `@NotBlank` when whitespace-only strings must be rejected.
10. **Creating custom beans in Boot unnecessarily:** default configuration suffices for many applications; add Java Configuration only when there is an actual requirement.

## 10. Process Checklist

A sound configuration answers four questions: **Is the provider present?** → **Which validator does Spring manage?** → **Are Spring MVC and services actually using that validator?** → **Have constraints, messages, and error paths been verified?**

- When default `@Valid` is enough: add the appropriate starter/provider and use DTO constraints.
- When a shared bean is needed: declare `@Bean LocalValidatorFactoryBean` in `@Configuration`.
- When MVC control is needed: implement `WebMvcConfigurer#getValidator()`.
- When custom messages are needed: configure `MessageSource` and `setValidationMessageSource(...)`, then verify via real failing requests.

**Official documentation for deeper reading:**
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring MVC — Validation Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring MVC — Validating Controller Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
