# LocalValidatorFactoryBean's validationMessageSource: Multilingual Validation Messages in Spring

## 1. Lesson Objectives

An application serving Vietnamese and international users needs to display input errors in the corresponding language, for example:

~~~text
Request with locale=vi:
  name=" "   -> Họ tên không được để trống
  age=16     -> Tuổi phải từ 18 trở lên

Request with locale=en:
  name=" "   -> Name must not be blank
  age=16     -> Age must be at least 18
~~~

The same Java DTO, annotations, and validation rules apply, yet the **message changes by `Locale`**. At the Bean Validation (Jakarta Validation) layer, messages in `@NotBlank(message=...)` or `@Min(message=...)` are turned into text via `MessageInterpolator`. At the Spring layer, `MessageSource` supplies the localized message catalog. `LocalValidatorFactoryBean` is the bridge between these two systems.

Core API:

~~~java
LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
validator.setValidationMessageSource(messageSource);
~~~

**`validationMessageSource` is a JavaBean property of `LocalValidatorFactoryBean`**, configured via `setValidationMessageSource(MessageSource)`. It is **not** a required Spring bean name, nor a default filename. You can pass the application's `messageSource` bean, or a dedicated `MessageSource` reserved for validation.

This lesson clarifies:
1. The roles of `LocalValidatorFactoryBean`, `MessageSource`, and `MessageInterpolator`.
2. How to configure `setValidationMessageSource` and bundles `messages.properties`, `messages_vi.properties`, `messages_en.properties`.
3. How templates like `{signup.name.required}` and constraint parameters like `{value}` work.
4. How the locale is selected when invoking the validator directly or when requests flow through Spring MVC.
5. Differences between Boot auto-configuration and manual configuration.
6. How to accurately test two locales, fallbacks, and the `@Valid @RequestBody` path.
7. Common i18n/validation errors and how to diagnose them.

The main example uses **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Jakarta Validation**. Knowledge of `LocalValidatorFactoryBean` also applies to Spring MVC/WebFlux and Spring services, though the runnable HTTP example uses Spring MVC to avoid mixing Servlet and reactive stacks.

## 2. Four Concepts Not to Confuse

### 2.1. Jakarta Bean Validation Constraint Message

Example:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class SignupRequest {
    @NotBlank(message = "{signup.name.required}")
    private String name;

    @Min(value = 18, message = "{signup.age.min}")
    private int age;
}
~~~

`@NotBlank` and `@Min` describe the **validity condition**. The `message` attribute holds a **message template**, which can be a literal string or a key referencing a resource bundle. Curly braces such as `{signup.age.min}` denote a code looked up in the message source to produce user-facing text.

If you use a literal message:

~~~java
@NotBlank(message = "Name is required")
private String name;
~~~

the literal string will not automatically turn into Vietnamese when the locale is `vi`. For flexible i18n, prefer **stably named keys**, such as `{signup.name.required}`.

### 2.2. Spring `MessageSource`

`org.springframework.context.MessageSource` provides methods such as:

~~~java
String getMessage(
        String code,
        Object[] args,
        Locale locale);
~~~

In a Spring Boot application, `MessageSource` usually reads a group of files:

~~~text
src/main/resources/
  messages.properties
  messages_en.properties
  messages_vi.properties
~~~

With locale `vi`, key `signup.name.required` is looked up in the Vietnamese bundle. With locale `en`, the corresponding key is looked up in the English bundle, followed by configured fallbacks.

`MessageSource` does not run validation itself. It only **looks up and formats messages**; detecting invalid data belongs to `Validator`.

### 2.3. `MessageInterpolator` in Bean Validation

`jakarta.validation.MessageInterpolator` takes the message template, constraint context, and locale to produce the final message. A provider such as Hibernate Validator implements interpolation that can:
- Look up keys like `{signup.age.min}` in a message resource bundle.
- Substitute annotation attributes such as `{value}` from `@Min(value = 18)` with `18`.
- Process Bean Validation expressions and escapes per the specification and provider.

Do not equate Bean Validation interpolation with Spring's `MessageFormat`. For example, `{value}` is a **constraint attribute** in Bean Validation, whereas `{0}` is typically a **positional argument** when calling Spring `MessageSource#getMessage(code,args,locale)`. Both syntaxes may appear in the same system, yet they have different meanings.

### 2.4. `LocalValidatorFactoryBean`

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` is Spring's adapter for Jakarta Bean Validation. It:
- Creates and manages a provider `ValidatorFactory`.
- Exposes an object compatible with `jakarta.validation.Validator`.
- Implements `org.springframework.validation.SmartValidator` for Spring binding/validation.
- Participates in `@Valid`/`@Validated` in Spring integrations.
- Allows configuring the provider, message source, message interpolator, constraint validator factory, and other options.

Key method:

~~~java
void setValidationMessageSource(MessageSource messageSource);
~~~

According to Spring Javadoc, it uses a **Spring `MessageSource` to resolve validation messages instead of relying solely on Jakarta Validation's default `ValidationMessages.properties`**. In Spring Framework 6.2, this integration relies on Hibernate Validator's interpolation support class; if using another provider, ensure Hibernate Validator's resource-bundle interpolation classes are available as noted in the Javadoc.

## 3. Message Resolution Diagram

~~~text
User sends request, Spring selects Locale
             |
             v
@Valid @RequestBody SignupRequest
             |
             v
LocalValidatorFactoryBean
             |
             v
Jakarta Validator / Hibernate Validator
             |
             +--> @NotBlank(message="{signup.name.required}")
             |       |
             |       v
             |    MessageSource (messages_vi, messages_en...)
             |       |
             |       v
             |    "Họ tên không được để trống"
             |
             +--> @Min(value=18, message="{signup.age.min}")
                     |
                     v
                  MessageSource
                     |
                     v
                  "Tuổi phải từ {value} trở lên"
                     |
                     v
                  Provider interpolation
                     |
                     v
                  "Tuổi phải từ 18 trở lên"
             |
             v
ConstraintViolation.getMessage()
             |
             v
Spring BindingResult / FieldError / HTTP error response
~~~

Important: `ConstraintViolation#getMessageTemplate()` returns the **original template** (e.g., `"{signup.age.min}"`), whereas `getMessage()` returns the **interpolated content** for the locale, e.g., `"Tuổi phải từ 18 trở lên"`. If an application sends `getMessageTemplate()` straight to the UI without resolving it, users will see a raw key instead of a message.

Similarly, `FieldError#getDefaultMessage()` in Spring MVC is usually the message transferred from the constraint violation (or a binding error message), while `FieldError#getCodes()` also carries codes for Spring's `MessageCodesResolver`. Do not treat them as a single undifferentiated string: codes and messages serve two different purposes.

## 4. How to Configure `setValidationMessageSource`

### 4.1. Basic Java Configuration

~~~java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator(MessageSource messageSource) {
        LocalValidatorFactoryBean bean = new LocalValidatorFactoryBean();
        bean.setValidationMessageSource(messageSource);
        return bean;
    }
}
~~~

This is a **standalone configuration file** assuming the project has a Spring context, a Jakarta Validation provider, and a `MessageSource`. Declare `LocalValidatorFactoryBean` as a Spring bean so Spring manages its lifecycle (including initializing the provider after properties are set). Do not instantiate it with `new` and call `validate` immediately before the factory is initialized.

**Do not manually call `afterPropertiesSet()` on a Spring-managed bean** just to “be safe”; Spring runs the init lifecycle automatically. In plain tests outside Spring, if you use `new LocalValidatorFactoryBean()`, complete its lifecycle appropriately.

### 4.2. JavaBean Property Differs from Spring Bean Name

In historical XML configuration, the property is `validationMessageSource`:

~~~xml
<bean id="validator"
      class="org.springframework.validation.beanvalidation.LocalValidatorFactoryBean">
    <property name="validationMessageSource" ref="messageSource"/>
</bean>
~~~

The property name corresponds to the setter `setValidationMessageSource`. In Java configuration, however, `messageSource` may be the bean name created by Spring Boot from `messages.properties`, while the validator bean may be named `validator`, `localValidatorFactoryBean`, or something else.

If you declare a bean named `validationMessageSource` without **wiring it into the validator**, the name alone will not make Bean Validation find the resource bundle.

### 4.3. Shared Source or Dedicated Source?

**Shared:** pass the application `MessageSource` that serves UI labels and error messages. The advantage is a single unified i18n system. The disadvantage is needing key namespaces to avoid collisions.

**Dedicated:** configure a `MessageSource` solely for validation, such as `validation-messages.properties` and its localized variants. The advantage is separating content ownership and lifecycle. When using a dedicated source, ensure it has proper fallbacks and still resolves provider defaults properly.

A dedicated setup might look like:

~~~java
@Bean("validationTextSource")
MessageSource validationTextSource() {
    ReloadableResourceBundleMessageSource source =
            new ReloadableResourceBundleMessageSource();
    source.setBasename("classpath:validation-messages");
    source.setDefaultEncoding("UTF-8");
    source.setFallbackToSystemLocale(false);
    return source;
}

@Bean
LocalValidatorFactoryBean validator(
        @Qualifier("validationTextSource") MessageSource source) {
    LocalValidatorFactoryBean bean = new LocalValidatorFactoryBean();
    bean.setValidationMessageSource(source);
    return bean;
}
~~~

The snippet above is an **illustrative alternative**, requiring imports for `@Qualifier` and `ReloadableResourceBundleMessageSource`, and must not be pasted on top of the `validator` bean in Section 6's runnable example. Pick **only one** option per context to avoid duplicate bean definitions.

### 4.4. Do Not Configure Both Interpolator Paths at Once

`LocalValidatorFactoryBean` Javadoc requires choosing one of two options:
- `setValidationMessageSource(messageSource)`; **or**
- `setMessageInterpolator(customInterpolator)`.

Do not set both on the same factory. If you need a custom `MessageInterpolator`, learn how to build one with a Spring-backed `ResourceBundleLocator` or use the provider's appropriate API. Layering both settings makes the message selection path ambiguous.

### 4.5. Specifically: `useCodeAsDefaultMessage`

If configuring a custom `MessageSource`, do not enable `useCodeAsDefaultMessage=true` on the source passed to `LocalValidatorFactoryBean`. Spring Javadoc warns this can **prevent fallback to Hibernate Validator's default messages** when a key does not exist.

Pattern to avoid:

~~~java
ReloadableResourceBundleMessageSource source =
        new ReloadableResourceBundleMessageSource();
source.setBasename("classpath:validation-messages");
source.setUseCodeAsDefaultMessage(true); // Not recommended for validation.
~~~

If the provider needs to look up `{jakarta.validation.constraints.NotNull.message}` and `MessageSource` returns the literal code as a “found” message, fallback may fail to occur. Let optional lookup report “not found” when a key is absent so the provider can use its own default bundle.

## 5. Message Files and Fallback Rules

### 5.1. Bundle Structure

In Spring Boot, the default basename is `messages` at the classpath root. Place:

~~~text
src/main/resources/
  application.properties
  messages.properties
  messages_en.properties
  messages_vi.properties
~~~

`messages.properties` is the **root bundle** and also serves as the fallback when no locale-specific entry exists. Spring Boot auto-configures `MessageSource` when an appropriate base bundle exists; if you create only `messages_vi.properties` without `messages.properties`, Boot may **not auto-configure** the message source as expected.

### 5.2. `messages.properties`

~~~properties
signup.name.required=Name must not be blank
signup.age.min=Age must be at least {value}
signup.received=Registration received
~~~

### 5.3. `messages_en.properties`

~~~properties
signup.name.required=Name must not be blank
signup.age.min=Age must be at least {value}
signup.received=Registration received
~~~

### 5.4. `messages_vi.properties`

~~~properties
signup.name.required=Họ tên không được để trống
signup.age.min=Tuổi phải từ {value} trở lên
signup.received=Đã nhận đăng ký
~~~

**Note on `{value}`:** this is the attribute name in `@Min(value=18)`. Spring `MessageSource` supplies the template, and Hibernate Validator performs Bean Validation substitution; the expected output is `"Tuổi phải từ 18 trở lên"`. Do not hardcode `{value}` as a fixed number if you want to reuse the rule with different thresholds.

Do not confuse `{value}` with `MessageFormat`'s `{0}`. When calling `messageSource.getMessage("some.code", new Object[]{18}, locale)`, `{0}` has meaning to Spring `MessageSource` itself. Bean Validation interpolation, however, has its own rule set covering constraint attributes, bundle parameters, and provider limits.

### 5.5. `application.properties`

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

- `basename` points to `messages.properties` and language variants sharing that base.
- `encoding=UTF-8` supports files with Vietnamese diacritics; also verify your IDE/build pipeline saves UTF-8.
- `fallback-to-system-locale=false` makes behavior predictable: if a locale lacks a translation, fall back to the base bundle rather than using the OS locale where the server happens to run.

Do not change the entire JVM's default locale just to test messages. In tests, set the locale per request or set `LocaleContextHolder` with `finally` so context does not leak into other tests.

### 5.6. How Do `ValidationMessages.properties` Files Differ?

The Jakarta Validation specification expects the default bundle **`ValidationMessages.properties`**. When using directly:

~~~java
try (ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();
}
~~~

the provider resolves defaults using Jakarta Validation bundles. It **has no automatic awareness of the Spring `messageSource` bean** in the application context.

When `LocalValidatorFactoryBean#setValidationMessageSource` is called, Spring plugs the application's message source into the provider's interpolation mechanism instead of the default path that only checks `ValidationMessages.properties`. If an application has both resource sets, identify which source is used in each flow and test migrations. Do not copy something that “worked by chance” with `Validation.buildDefaultValidatorFactory()` to `LocalValidatorFactoryBean` assuming both read the same source.

## 6. Runnable Project: Java 17 + Spring Boot 3.5.7 + MVC

The demo project explicitly configures `setValidationMessageSource`, wires the same validator into Spring MVC, sends requests in two locales, and verifies with `MockMvc`. It uses `spring-boot-starter-validation` and Spring MVC. No database is required.

### 6.1. Directory Tree

~~~text
pom.xml
src/main/
  java/com/example/i18n/
    I18nApplication.java
    SignupRequest.java
    ValidationConfiguration.java
    SignupController.java
    ApiValidationAdvice.java
  resources/
    application.properties
    messages.properties
    messages_en.properties
    messages_vi.properties
src/test/java/com/example/i18n/
  ValidationMessageSourceTest.java
  SignupControllerTest.java
~~~

### 6.2. Maven `pom.xml`

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
    <artifactId>validation-message-source-demo</artifactId>
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

`spring-boot-starter-web` sets up Servlet Spring MVC, `spring-boot-starter-validation` brings a Jakarta Validation provider (usually Hibernate Validator) onto the classpath, and `spring-boot-starter-test` provides JUnit and `MockMvc`.

### 6.3. Main Application

~~~java
// src/main/java/com/example/i18n/I18nApplication.java
package com.example.i18n;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nApplication {
    public static void main(String[] args) {
        SpringApplication.run(I18nApplication.class, args);
    }
}
~~~

### 6.4. Request DTO with Message Templates

~~~java
// src/main/java/com/example/i18n/SignupRequest.java
package com.example.i18n;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class SignupRequest {

    @NotBlank(message = "{signup.name.required}")
    private String name;

    @Min(value = 18, message = "{signup.age.min}")
    private int age;

    // No custom message defined to test provider default.
    @Email
    private String email;

    public SignupRequest() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

`@Email` normally allows `null`; to require an email, add `@NotBlank` or `@NotNull` as needed. In this article, the `email` field tests the **provider default validation message**: not every constraint needs a custom key in the application catalog.

### 6.5. `ValidationConfiguration`: Wiring the MessageSource Bean to the Factory

~~~java
// src/main/java/com/example/i18n/ValidationConfiguration.java
package com.example.i18n;

import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator(
            MessageSource messageSource) {

        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setValidationMessageSource(messageSource);
        return factory;
    }

    @Bean
    public WebMvcConfigurer mvcValidatorConfigurer(
            LocalValidatorFactoryBean validator) {

        return new WebMvcConfigurer() {
            @Override
            public org.springframework.validation.Validator
                    getValidator() {
                return validator;
            }
        };
    }
}
~~~

**Why are there two beans?**

1. The `LocalValidatorFactoryBean` bean demonstrates `setValidationMessageSource(messageSource)` **directly**. Spring initializes the provider after setting the property, and the factory can be injected to call `validator.validate(...)`.
2. `WebMvcConfigurer#getValidator()` guarantees MVC argument validation uses this exact factory. As a result, `@Valid @RequestBody` in the example receives the same message bundles as the direct validation tests.

This configuration provides a **transparent demo**, not a requirement that every Spring Boot project write its own `WebMvcConfigurer`. In Spring Boot 3.5, when a Bean Validation provider is on the classpath, auto-configuration already integrates the application `MessageSource` with constraint message parameters. If you simply want to use `messages.properties` for message templates without custom wiring, **many applications do not need to declare a `LocalValidatorFactoryBean` manually**.

Once you explicitly declare the factory and global MVC validator as above, avoid declaring another `LocalValidatorFactoryBean` or a competing `WebMvcConfigurer` returning a different validator. In large projects, review bean precedence and test that `@Valid` uses the intended instance.

### 6.6. REST Controller

~~~java
// src/main/java/com/example/i18n/SignupController.java
package com.example.i18n;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/signups")
public class SignupController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> create(
            @Valid @RequestBody SignupRequest request) {

        return Map.of("status", "accepted");
    }
}
~~~

If `name` is whitespace-only or `age` is less than 18, Bean Validation blocks the handler and Spring MVC typically throws `MethodArgumentNotValidException` because this is **validation on a request object** with no other direct method constraints. The handler does not manually `try/catch` to throw errors: Spring MVC triggers validation when processing `@Valid`.

### 6.7. Handling Errors into a Structured API Response

~~~java
// src/main/java/com/example/i18n/ApiValidationAdvice.java
package com.example.i18n;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.LinkedHashMap;
import java.util.Map;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidBody(
            MethodArgumentNotValidException ex) {

        Map<String, String> messages = new LinkedHashMap<>();

        for (FieldError error :
                ex.getBindingResult().getFieldErrors()) {
            messages.putIfAbsent(
                    error.getField(),
                    error.getDefaultMessage());
        }

        return ResponseEntity.badRequest().body(messages);
    }
}
~~~

`FieldError#getDefaultMessage()` here reflects the message interpolated for the request's locale. We return only **field name + message**, without `getRejectedValue()`, raw request body, tokens, or stack traces. In production APIs, consider returning stable error codes separate from translations: prose text is not a good contract for client branching logic.

If a controller has direct method constraints in Spring MVC 6.1+, it may throw `HandlerMethodValidationException`. This demo intentionally tests only object-level `@Valid @RequestBody` and handles `MethodArgumentNotValidException`; do not force one handler onto every error kind.

### 6.8. Placing Bundles in the Right Directory

Contents of **`src/main/resources/application.properties`**:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Contents of **`src/main/resources/messages.properties`**:

~~~properties
signup.name.required=Name must not be blank
signup.age.min=Age must be at least {value}
signup.received=Registration received
~~~

Contents of **`src/main/resources/messages_en.properties`**:

~~~properties
signup.name.required=Name must not be blank
signup.age.min=Age must be at least {value}
signup.received=Registration received
~~~

Contents of **`src/main/resources/messages_vi.properties`**:

~~~properties
signup.name.required=Họ tên không được để trống
signup.age.min=Tuổi phải từ {value} trở lên
signup.received=Đã nhận đăng ký
~~~

Spell the bundle name `messages_vi.properties` accurately (underscore, **not** `messages-vi.properties`) and place files under the `src/main/resources` root; after a Maven build, they must appear on the classpath.

### 6.9. Running the Application and Sending HTTP Requests

~~~bash
mvn spring-boot:run
~~~

Vietnamese request:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":" ","age":16,"email":"test@example.com"}'
~~~

Expected JSON body (field order not guaranteed):

~~~json
{
  "name": "Họ tên không được để trống",
  "age": "Tuổi phải từ 18 trở lên"
}
~~~

English request:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/json" \
  -H "Accept-Language: en" \
  -d '{"name":" ","age":16,"email":"test@example.com"}'
~~~

Expected JSON body:

~~~json
{
  "name": "Name must not be blank",
  "age": "Age must be at least 18"
}
~~~

Both return HTTP **400** because the input is invalid. A valid request such as `{"name":"Lan","age":21,"email":"test@example.com"}` receives JSON `{"status":"accepted"}` and HTTP 200.

**Note:** `Accept-Language` in this example works with the standard default locale resolution in Spring MVC/Boot. If the application customizes `LocaleResolver`, a cookie, another header, or a logged-in user preference may determine the locale. Do not assume `Accept-Language` always overrides a custom language selection mechanism.

## 7. Testing i18n Directly on LocalValidatorFactoryBean

### 7.1. Testing with Spring LocaleContextHolder

Spring provides `LocaleContextMessageInterpolator`, a wrapper that applies the Spring-managed locale to the provider's interpolator. In an HTTP handler, the framework sets the corresponding request locale; in a direct unit/integration test, you can set `LocaleContextHolder` temporarily.

~~~java
// src/test/java/com/example/i18n/ValidationMessageSourceTest.java
package com.example.i18n;

import jakarta.validation.ConstraintViolation;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ValidationMessageSourceTest {

    @Autowired
    LocalValidatorFactoryBean validator;

    private SignupRequest invalidSignup() {
        SignupRequest input = new SignupRequest();
        input.setName(" ");
        input.setAge(16);
        input.setEmail("test@example.com");
        return input;
    }

    private Map<String, String> messages(
            Set<ConstraintViolation<SignupRequest>> violations) {

        return violations.stream().collect(
                Collectors.toMap(
                        v -> v.getPropertyPath().toString(),
                        ConstraintViolation::getMessage));
    }

    @Test
    void vietnameseMessagesAndConstraintAttributes() {
        LocaleContextHolder.setLocale(
                Locale.forLanguageTag("vi"));
        try {
            Map<String, String> errors =
                    messages(validator.validate(invalidSignup()));
            assertEquals(2, errors.size());
            assertEquals("Họ tên không được để trống",
                    errors.get("name"));
            assertEquals("Tuổi phải từ 18 trở lên",
                    errors.get("age"));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }

    @Test
    void englishMessagesAreResolvedFromSameConstraints() {
        LocaleContextHolder.setLocale(Locale.ENGLISH);
        try {
            Map<String, String> errors =
                    messages(validator.validate(invalidSignup()));
            assertEquals(2, errors.size());
            assertEquals("Name must not be blank",
                    errors.get("name"));
            assertEquals("Age must be at least 18",
                    errors.get("age"));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }

    @Test
    void originalTemplateRemainsAccessible() {
        LocaleContextHolder.setLocale(Locale.ENGLISH);
        try {
            var violation = validator.validate(invalidSignup())
                    .stream()
                    .filter(v -> "name".equals(
                            v.getPropertyPath().toString()))
                    .findFirst()
                    .orElseThrow();

            assertEquals("{signup.name.required}",
                    violation.getMessageTemplate());
            assertEquals("Name must not be blank",
                    violation.getMessage());
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }

    @Test
    void providerDefaultStillResolvesWithoutCustomKey() {
        LocaleContextHolder.setLocale(Locale.ENGLISH);
        try {
            SignupRequest input = new SignupRequest();
            input.setName("Valid");
            input.setAge(21);
            input.setEmail("not-an-email");

            var violations = validator.validate(input);
            assertEquals(1, violations.size());
            var emailViolation = violations.iterator().next();

            assertEquals("email",
                    emailViolation.getPropertyPath().toString());
            assertTrue(
                    !emailViolation.getMessage().isBlank());
            assertTrue(
                    !emailViolation.getMessage().startsWith("{"));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
~~~

Points to remember:
- `LocaleContextHolder.resetLocaleContext()` in `finally` prevents locale state from leaking to other tests/threads.
- Tests 1 and 2 verify **the same DTO, same constraints, different locales**.
- Test 3 shows `messageTemplate` and `message` are distinct.
- Test 4 checks the provider fallback for `@Email` when the app defines no custom key; do not assert the exact Hibernate Validator sentence verbatim because wording can change by version/locale.

`LocaleContextHolder` uses a `ThreadLocal`. With asynchronous processing, Reactor/WebFlux, thread switching, or queue consumers, **do not assume the locale propagates across every thread automatically**; use appropriate locale/context propagation and test it in practice. Here, direct tests run on a single thread and always reset in `finally`.

### 7.2. Why Not Use `Validation.buildDefaultValidatorFactory()` in This Test?

If a test writes:

~~~java
try (var factory =
        jakarta.validation.Validation.buildDefaultValidatorFactory()) {
    var standalone = factory.getValidator();
    // Does not automatically connect Spring MessageSource to this factory.
}
~~~

a plain Jakarta factory **is not part of the Spring context**, so it does not receive the `messageSource` bean we configured. If you only want to test whether the Bean Validation provider can run, this is fine; however, it is **not a test for `setValidationMessageSource`**.

To verify the actual integration, inject `LocalValidatorFactoryBean` itself (or the Spring-managed `jakarta.validation.Validator` bean) from the Spring context and check messages per locale.

## 8. HTTP Testing with MockMvc

~~~java
// src/test/java/com/example/i18n/SignupControllerTest.java
package com.example.i18n;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    MockMvc mvc;

    private static final String INVALID_JSON = """
        {"name":" ","age":16,"email":"test@example.com"}
        """;

    @Test
    void vietnameseRequestGetsVietnameseValidationErrors()
            throws Exception {

        mvc.perform(post("/api/signups")
                    .locale(Locale.forLanguageTag("vi"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(INVALID_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.name")
                        .value("Họ tên không được để trống"))
                .andExpect(jsonPath("$.age")
                        .value("Tuổi phải từ 18 trở lên"));
    }

    @Test
    void englishRequestGetsEnglishValidationErrors()
            throws Exception {

        mvc.perform(post("/api/signups")
                    .locale(Locale.ENGLISH)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(INVALID_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.name")
                        .value("Name must not be blank"))
                .andExpect(jsonPath("$.age")
                        .value("Age must be at least 18"));
    }

    @Test
    void validBodyDoesNotReturnErrors() throws Exception {

        mvc.perform(post("/api/signups")
                    .locale(Locale.ENGLISH)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"name":"Lan","age":21,
                         "email":"test@example.com"}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }
}
~~~

In `MockMvc`, `.locale(...)` sets the mock request locale explicitly for stable testing, whereas `curl` in Section 6 demonstrates `Accept-Language` over HTTP. These are **two ways of selecting locale** for the same contract. In a system with a custom locale resolver, tests must exercise the actual production locale mechanism.

Run:

~~~bash
mvn test
~~~

**Expected result: 7 JUnit tests PASS** (4 tests on `LocalValidatorFactoryBean` and 3 `MockMvc` tests) when all code and bundles are placed as in Sections 6–8. This is the **expected outcome based on API and logic**, not a report of an actual Maven run. To run only one test class:

~~~bash
mvn -Dtest=ValidationMessageSourceTest test
~~~

The HTTP tests prove that message resolution works not only when calling `validator.validate(...)` manually, but also when requests go through Spring MVC's `@Valid @RequestBody`.

## 9. Boot Auto-Configuration vs. Custom Validator: When to Choose Which?

### 9.1. What Can Spring Boot 3.5 Do by Default?

Spring Boot Validation documentation states clearly: **the application `MessageSource` is used when resolving `{parameters}` in constraint messages**, enabling your application's `messages.properties` in Bean Validation. Once those parameters are resolved, the provider still performs interpolation.

Therefore, for basic use cases:

~~~java
@NotBlank(message = "{signup.name.required}")
private String name;
~~~

with valid `messages.properties`/`messages_vi.properties` on the classpath, **you may not need to write a manual `LocalValidatorFactoryBean` bean**. Boot already provides the integration. Do not write custom configuration just because older guides say you must call `setValidationMessageSource`.

### 9.2. When Is Explicit `setValidationMessageSource` Needed?

Valid scenarios:
- Separating a validation-specific text source from UI labels.
- Configuring Spring Framework **without Boot** or managing validators yourself.
- Explicitly customizing provider settings or custom interpolation.
- Testing/controlling the exact factory bean shared across controllers and services.
- Migrating from legacy `ValidationMessages.properties` to a unified `MessageSource`.

When declaring it yourself, ensure there are no competing factory beans and that MVC/WebFlux configuration actually uses the intended factory.

### 9.3. Choosing `MessageSource` or a Custom `MessageInterpolator`?

| Need | Choice |
| --- | --- |
| Translate the same message key into multiple languages | Spring `MessageSource` |
| Use `messages_vi`/`messages_en` message bundles | `MessageSource` |
| Replace the entire Bean Validation interpolation algorithm | Custom `MessageInterpolator` |
| Only change text for `@NotBlank` | `message="{...}"` key in annotations |
| Change HTTP locale resolution/precedence | `LocaleResolver`/request locale strategy |
| Add a new data validation rule | Jakarta constraint/`ConstraintValidator` or Spring `Validator`, not `MessageSource` |

`MessageSource` only supplies text; it cannot validate a field that has no constraint. If a locale lacks a translation, update the bundle/fallback; never modify a `ConstraintValidator` to “translate” errors.

## 10. Locale: HTTP Requests, Tests, Batch Jobs, and Async

### 10.1. In Spring MVC

An MVC application has a `LocaleResolver`, commonly using the `Accept-Language` header or a custom cookie/session/profile mechanism. `LocalValidatorFactoryBean` uses a wrapped `MessageInterpolator` to obtain the **Spring-managed locale** when appropriate, via `LocaleContextHolder`.

~~~text
Accept-Language: vi
       |
       v
Spring MVC LocaleResolver
       |
       v
LocaleContextHolder (locale=vi)
       |
       v
LocalValidatorFactoryBean / MessageInterpolator
       |
       v
messages_vi.properties -> ConstraintViolation message
~~~

If the frontend switches languages via `?lang=vi`, do not just read the query parameter and expect messages to switch automatically; configure the resolver/interceptor or handle locale explicitly. Never treat the server's default locale as the standard for all users.

### 10.2. In a Service or Command-Line Job

A service method not running under an HTTP request may use the JVM default locale or whatever locale is bound to `LocaleContextHolder`. If Vietnamese is needed for an isolated task, scope the context carefully:

~~~java
Locale previous = LocaleContextHolder.getLocale();
try {
    LocaleContextHolder.setLocale(
            Locale.forLanguageTag("vi"));
    // validator.validate(bean)
} finally {
    LocaleContextHolder.setLocale(previous);
}
~~~

This is an illustrative snippet, suitable when you control a synchronous context. To restore the full locale context (including timezone), save and restore `LocaleContext` instead of only `Locale`; in simple tests, `resetLocaleContext()` can be used when you are sure no prior context existed.

### 10.3. Spring WebFlux and Reactor

Spring WebFlux should not rely on `ThreadLocal` moving automatically along a reactive chain: execution may switch threads. WebFlux has its own locale mechanism from `ServerWebExchange` and matching validation integration; when building custom reactive infrastructure, check how locale context is passed into the interpolator and use Reactor Context/locale propagation properly.

This article uses MVC for the runnable example and does not claim that `LocaleContextHolder.setLocale(...)` inside an arbitrary async `flatMap` is portable. With WebFlux, write integration tests using `WebTestClient` with `Accept-Language` to verify real behavior.

## 11. Advanced Scenarios: Templates, Fallbacks, Message Codes

### 11.1. Messages with `{value}`, `{min}`, and `{max}`

Example:

~~~java
@Size(min = 3, max = 20,
      message = "{signup.username.size}")
private String username;
~~~

Bundle:

~~~properties
signup.username.size=Username must contain {min} to {max} characters
~~~

After interpolation, the expected result is `Username must contain 3 to 20 characters`. The words `min` and `max` are **attribute names of `@Size`**, not positional placeholders `{0}`, `{1}`.

For a Vietnamese translation:

~~~properties
signup.username.size=Tên đăng nhập cần từ {min} đến {max} ký tự
~~~

Keep the attribute names unchanged so the provider substitutes the numbers properly. For custom constraints, only attributes actually present on the annotation can be substituted per provider rules.

### 11.2. EL Interpolation and Safety

Hibernate Validator and Bean Validation have advanced rules for expression language and dynamic values. Never concatenate user-entered input into a message template and let the provider evaluate it as an expression. Bundle content is **trusted code/config**, whereas client-submitted names, emails, or product codes are **untrusted data**.

If you need to insert a dynamic value into an error message, use the constraint validation/provider API as documented (e.g., `addMessageParameter` where supported) to avoid template injection. In most APIs, returning **field + error code + translated message** is enough; there is no need to echo raw rejected values.

### 11.3. Spring `FieldError#getCodes()` Is Not `messageTemplate`

When `@Valid @RequestBody` fails, Spring can provide prioritized codes from specific to general, such as:

~~~text
NotBlank.signupRequest.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
~~~

This is the **Spring binding message codes** model, which varies by `MessageCodesResolver`, object name, and type. By contrast, `ConstraintViolation#getMessageTemplate()` in the example is `{signup.name.required}`. Do not inspect a Spring code and assume it must equal Bean Validation's `signup.name.required` key.

An application can use `MessageSource` a second time to translate Spring binding errors (such as `typeMismatch`); that is a **separate resolution pass** from messages already interpolated by Hibernate Validator.

### 11.4. Multilingual Binding Errors

When a client sends `age=abc` for an `Integer`/`int` property, the error is a **conversion** error, not `@Min(18)`. `LocalValidatorFactoryBean#setValidationMessageSource` primarily wires **Bean Validation constraint messages**; it does not automatically translate every `typeMismatch` from `DataBinder`.

To translate binding errors, add keys like `typeMismatch`/`typeMismatch.signupRequest.age` to Spring `MessageSource` and ensure your resolver/controller advice resolves the appropriate codes:

~~~properties
typeMismatch=Invalid value format
typeMismatch.signupRequest.age=Age must be a number
~~~

Vietnamese version:

~~~properties
typeMismatch=Giá trị sai định dạng
typeMismatch.signupRequest.age=Tuổi phải là số
~~~

This complements—and **does not replace**—`setValidationMessageSource`. Test both type conversion errors and constraint violations to keep the multilingual API truly consistent.

### 11.5. Fallback When Locale or Key Does Not Exist

With `spring.messages.fallback-to-system-locale=false`, missing `messages_fr.properties` lets the default `messages.properties` bundle supply the key. If a key is missing in `messages_vi`, Spring also searches appropriate bundles per fallback rules.

When a message key does not exist anywhere:
- `MessageSource#getMessage(...)` may throw `NoSuchMessageException` or return a default depending on the overload.
- The `ResourceBundle` locator for Hibernate Validator normally needs **optional resolution** so the provider can fall back.
- If the template still prints `{signup.name.required}` verbatim, check bundle paths, basename, bean instance, and provider interpolation.

### 11.6. Changing Locale Does Not Mean Recompiling Annotations

Annotation message templates do not vary by locale; the provider interpolates the message when validating constraints. Do not create separate `SignupRequestVi` and `SignupRequestEn` DTO classes just to change error wording. Keep rules shared, translate the catalog separately, and let the locale resolver pick the translation.

## 12. Common Pitfalls and How to Diagnose Them

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Response shows `{signup.name.required}` | Key not found or validator not using intended `MessageSource` | Check basename, bundles, factory bean, and annotation template |
| `messages_vi.properties` is not read | Wrong filename/folder, missing base `messages.properties`, wrong locale | Place under `src/main/resources`, check Boot message source |
| Garbled Vietnamese diacritics | Resource bundle/build/editor encoding | Use UTF-8, check file bytes and `spring.messages.encoding` |
| Messages always appear in English | Request locale is not `vi`, default locale/fallback, different provider | Check `LocaleResolver`, `LocaleContextHolder`, integration tests |
| `{value}` stays unreplaced | Bypassed Bean Validation interpolation, template not part of constraint metadata | Route through `LocalValidatorFactoryBean` and proper provider |
| Test with `Validation.buildDefaultValidatorFactory()` ignores `messages_vi` | Plain Jakarta factory does not use Spring context | Inject `LocalValidatorFactoryBean` from Spring |
| `@NotBlank` translated yet `typeMismatch` stays English | Binding errors use Spring message codes, not only constraint templates | Add Spring binding error messages |
| Custom bean breaks `@Valid` in controller | MVC/WebFlux picked another validator or bean config overrode it | Configure the proper global validator, test HTTP |
| Provider default `@Email` becomes literal code | `MessageSource` enabled `useCodeAsDefaultMessage` or misconfigured interpolation | Disable that option, keep provider fallback |
| Both `validationMessageSource` and `messageInterpolator` set | Two competing configuration paths | Choose one; if custom interpolator, use a Spring bundle locator |
| Locale in async code ignores request | `ThreadLocal` does not propagate automatically | Use proper reactive/context propagation and test |
| Message contains personal data | Concatenating raw rejected values into response/logs | Return safe field/code/message |
| `MessageSource` exists yet keys fail to resolve | Wrong key or only renamed bean without wiring | Check `setValidationMessageSource` or Boot auto-config |
| Translation contains `{min}` when annotation lacks `min` | Placeholder does not match constraint attribute | Review annotation type and test interpolation |
| Vietnamese/English wording diverges in rules | Translations drifted, reviewer checked only one locale | Test all locales, use stable error codes, and review text |
| HTTP 500 returned for normal input errors | Wrong exception mapping or provider runtime error | Distinguish binding, method validation, config, and domain errors |

### Repeatable Debugging Workflow

1. Check the Spring Boot/Spring Framework version and the `spring-boot-starter-validation` dependency.
2. Verify the `MessageSource` bean is created and the classpath contains `messages.properties` plus locale variants.
3. Inspect `@Constraint(message="{...}")` to confirm the key and attributes.
4. Inject `LocalValidatorFactoryBean` and test directly with `LocaleContextHolder` for `vi` and `en`.
5. Compare `ConstraintViolation#getMessageTemplate()` with `getMessage()`.
6. If direct tests pass while HTTP fails, check the global MVC/WebFlux validator and locale resolver.
7. If binding errors have the wrong language, inspect Spring `FieldError#getCodes()` separately.
8. If provider defaults fail, check `useCodeAsDefaultMessage` and whether two interpolators were set.
9. Test fallback for a locale without a bundle and a field without a custom message.
10. Do not patch hardcoded strings in individual controllers; fix the message catalog and keep multilingual tests.

## 13. Code Review Checklist

- [ ] Constraint messages needing i18n use stable `{namespace.key}` keys rather than hardcoded multilingual text in annotations.
- [ ] `messages.properties` exists at the classpath root for Boot `MessageSource` auto-config, alongside `messages_vi.properties`/`messages_en.properties`.
- [ ] Declare a manual `LocalValidatorFactoryBean` only when truly needed; if present, use `setValidationMessageSource` and test wiring.
- [ ] Do not configure both `setValidationMessageSource` and `setMessageInterpolator` on the same factory.
- [ ] Any `MessageSource` used for validation does not enable `useCodeAsDefaultMessage=true`.
- [ ] Placeholders `{value}`, `{min}`, `{max}` match constraint attributes.
- [ ] Request locale is resolved explicitly; test at least `vi` and `en` without relying on the JVM default.
- [ ] Test both direct `ConstraintViolation` and `@Valid` HTTP integration, not only one layer.
- [ ] Keep Bean Validation messages separate from `typeMismatch`/binding errors.
- [ ] API never returns raw rejected values, personal info, or stack traces in validation responses.
- [ ] Test fallbacks when a key or locale is missing, as well as provider default messages.
- [ ] For reactive/async code, define an explicit locale context propagation strategy.

## 14. References

- Spring Framework 6.2, `LocalValidatorFactoryBean` Javadoc, `setValidationMessageSource`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework 6.2, `LocaleContextMessageInterpolator` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/beanvalidation/LocaleContextMessageInterpolator.html
- Spring Framework 6.2, Bean Validation support: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2, Spring MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot 3.5, Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5, Internationalization: https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html
- Jakarta Validation 3.1 specification, Message interpolation: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Hibernate Validator reference, Message interpolation: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation
