# Resource Bundles and Message File Conventions in Spring Framework

## Objectives

**Internationalized messages** in a Java/Spring application should be managed using stable **message codes** and **resource bundles** rather than hardcoding text in controllers, templates, or services. With a code like `signup.title`, the system can return `Đăng ký` for Vietnamese, `Sign up` for English, and a default sentence when the requested locale lacks a translation.

After this lesson, you will know:

- How to name `messages.properties`, `messages_en.properties`, `messages_vi.properties`, and `messages_vi_VN.properties`.
- The roles of basename, locale, base file, fallback, and UTF-8 charset.
- How to configure `spring.messages.basename` and `spring.messages.*` properties in Spring Boot.
- How to call `MessageSource.getMessage(...)`, pass arguments, and handle `NoSuchMessageException`.
- The difference between Spring `messages*.properties` and Jakarta Bean Validation `ValidationMessages*.properties`.
- How to display `BindingResult` and `FieldError` errors with Thymeleaf according to the request locale.
- How to test a Java 17+ / Spring Boot 3.5.7 application using MockMvc and `Accept-Language`.

## 1. Resource Bundle, Message Code, and Locale

A **message code** is a logical key, not the full display sentence:

~~~properties
signup.title=Sign up
signup.submit=Submit
signup.welcome=Hello {0}!
~~~

Namespacing codes helps avoid collisions:

~~~text
common.action.save
common.action.cancel
signup.title
signup.name
signup.validation.age
checkout.payment.failed
orders.delivery.estimated
~~~

This is an application-defined convention, not required Java syntax. Keep keys stable when translators edit text, and avoid vague names like `message1` or `error` in large projects.

A **resource bundle** is a collection of translations for keys by `Locale`. In Maven:

~~~text
src/main/resources/
├── messages.properties
├── messages_en.properties
├── messages_vi.properties
└── messages_vi_VN.properties
~~~

- `messages` is the **basename**.
- `messages.properties` is the base file without a locale suffix.
- `messages_en.properties` is for English.
- `messages_vi.properties` is for Vietnamese in general.
- `messages_vi_VN.properties` holds content that applies only when the locale is Vietnamese in Vietnam.

Language/region tags over HTTP are usually written `vi-VN`. In Java `ResourceBundle` filenames, the standard form is `vi_VN` with an underscore; do not rename it to `messages_vi-VN.properties`.

Example creating `Locale`:

~~~java
Locale vi = Locale.forLanguageTag("vi");
Locale viVN = Locale.forLanguageTag("vi-VN");
Locale enUS = Locale.forLanguageTag("en-US");
~~~

Requires importing `java.util.Locale`. `Locale` does not contain the application's translations itself: it is an input telling `MessageSource` which bundle to choose. `Locale` also affects date, number, and currency formatting, though translating resource bundles does not automatically configure every data type.

## 2. Base File and Spring Boot Auto-Configuration

Spring Boot 3.5 searches for basename `messages` at the classpath root by default. In a Maven layout, the base file belongs at:

~~~text
src/main/resources/messages.properties
~~~

**Easy-to-miss detail:** Spring Boot documentation requires a **default properties file** matching the basename in order to auto-configure `MessageSource`. If you only create `messages_vi.properties` and `messages_en.properties` without `messages.properties`, do not assume Boot will detect and auto-configure `MessageSource` properly.

The base file also acts as a fallback when a key has no locale-specific translation. You can use English as the fallback language as in the demo, though choosing the base language is a product decision.

### Changing the Basename

To store files in a dedicated folder:

~~~text
src/main/resources/i18n/ui.properties
src/main/resources/i18n/ui_vi.properties
src/main/resources/i18n/ui_en.properties
~~~

configure:

~~~properties
spring.messages.basename=i18n/ui
~~~

Do not include `.properties`, `_vi`, or the `src/main/resources` prefix in the basename value.

Multiple basenames can be declared:

~~~text
src/main/resources/messages.properties
src/main/resources/messages_vi.properties
src/main/resources/i18n/errors.properties
src/main/resources/i18n/errors_vi.properties
~~~

~~~properties
spring.messages.basename=messages,i18n/errors
~~~

When multiple bundles define the same key, precedence depends on `MessageSource` and basename ordering. Do not rely on accidental collisions; namespace keys by feature and write tests when overriding intentionally.

### Distinguishing Configuration from Translation Data

~~~properties
# application.properties - configuration
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

~~~properties
# messages.properties - data
signup.title=Sign up
signup.submit=Submit
~~~

Putting `signup.title` inside `application.properties` does not turn it into a Spring `MessageSource` translation. The two files serve different purposes.

## 3. Locale Fallback and File Lookup Order

Suppose:

~~~properties
# messages.properties
signup.title=Sign up
signup.region=General message
~~~

~~~properties
# messages_vi.properties
signup.title=Đăng ký
signup.region=Thông điệp chung cho tiếng Việt
~~~

~~~properties
# messages_vi_VN.properties
signup.region=Thông điệp riêng cho Việt Nam
~~~

Looking up `signup.region` with locale `vi-VN` prefers the region-specific translation and falls back step by step to the more general ones:

~~~text
messages_vi_VN.properties
     ↓ key missing?
messages_vi.properties
     ↓ key missing?
messages.properties
     ↓ key missing?
default message / NoSuchMessageException
~~~

| Locale | Key | Result |
| --- | --- | --- |
| `vi-VN` | `signup.region` | Thông điệp riêng cho Việt Nam |
| `vi` | `signup.region` | Thông điệp chung cho tiếng Việt |
| `vi-VN` | `signup.title` | Đăng ký |
| `en-US` | `signup.title` | Sign up, if `en` does not override |
| `fr-FR` | `signup.title` | Sign up, per fallback in the demo |

**Language/country fallback differs from falling back to the server's locale.** Some implementations may try the JVM default locale when no matching variant exists, causing the same `fr-FR` request on machines with Vietnamese vs. English OS locales to return different content.

For consistent testing and operations:

~~~properties
spring.messages.fallback-to-system-locale=false
~~~

Then the app prefers the requested locale's bundle, followed by the base file, independent of the OS locale. If business logic intentionally uses the system locale, document that policy and test accordingly.

You do not need to create `messages_en_GB.properties` for every country: only create one when there are real differences. For locales with complex scripts or variants, Java's candidate bundle lookup has additional branches; verify with unit tests rather than assembling filenames manually.

## 4. MessageSource API

`org.springframework.context.MessageSource` provides key overloads.

### With Caller-Provided Fallback

~~~java
String text = messageSource.getMessage(
        "signup.title",
        null,
        "Registration",
        Locale.forLanguageTag("vi"));
~~~

If `signup.title` is found in the Vietnamese bundle, it returns `Đăng ký`. If the key is not found in the matching files, it returns `Registration`.

### Without Fallback

~~~java
String text = messageSource.getMessage(
        "signup.title",
        null,
        Locale.ENGLISH);
~~~

If the key is not found, this overload throws `NoSuchMessageException`. **Not having a file for a locale** does not mean an error: the key can still come from `messages.properties`.

### MessageSourceResolvable

~~~java
MessageSourceResolvable resolvable =
        new DefaultMessageSourceResolvable(
                new String[] {
                    "signup.title", "common.title"
                },
                null,
                "Sign up");

String text = messageSource.getMessage(
        resolvable, Locale.ENGLISH);
~~~

This snippet requires importing `MessageSourceResolvable` and `DefaultMessageSourceResolvable` from Spring. A resolvable carries multiple codes in priority order, arguments, and a default message. `FieldError`/`ObjectError` in Spring Validation also provide this same mechanism.

Do not cache translated strings in static fields at startup if the server needs to serve multiple locales concurrently. Resolve at the request boundary or pass `Locale` explicitly from the caller.

## 5. Parameterized Messages and MessageFormat

A message can accept arguments:

~~~properties
signup.welcome=Hello {0}!
orders.summary=Order {0} contains {1,number} items.
~~~

~~~java
String message = messageSource.getMessage(
        "signup.welcome",
        new Object[] {"Lan"},
        Locale.ENGLISH);
~~~

Result:

~~~text
Hello Lan!
~~~

`{0}` is the first argument, `{1}` is the second argument. Expressions such as `{0,number}`, `{1,date,short}` use `java.text.MessageFormat` rules with the appropriate `Locale`. Pass suitable value types; Java Time's `LocalDate` is not automatically a `java.util.Date` across all `MessageFormat` APIs.

### Single Quotes

`MessageFormat` uses `'` for quoting. To render a literal single quote in a parameterized message, you normally must double it:

~~~properties
orders.ready=You''ve got {0} orders.
~~~

With argument `2`, the result is:

~~~text
You've got 2 orders.
~~~

To print a literal `{0}` instead of substituting an argument, follow `MessageFormat` quoting/escaping rules. Do not use JavaScript or Thymeleaf variable syntax in `.properties` files expecting `MessageFormat` to evaluate them.

Spring Boot has:

~~~properties
spring.messages.always-use-message-format=false
~~~

When left at the default, Spring can optimize messages that need no arguments. If set to `true`, even static messages pass through `MessageFormat` and apostrophe escaping behavior can differ. Test messages containing `'` or braces whenever changing this setting.

## 6. Vietnamese Encoding

Spring Boot 3.5 supports UTF-8 for message bundles; set it explicitly:

~~~properties
spring.messages.encoding=UTF-8
~~~

A UTF-8 file can directly contain:

~~~properties
signup.title=Đăng ký
signup.name=Họ và tên
signup.success=Đã tiếp nhận
~~~

Some legacy projects use Unicode escapes such as `\u0110\u0103ng k\u00fd`; with UTF-8 configured properly, you do not need to convert every translation into hard-to-read escapes.

`.properties` files accept `=` or `:` as key/value delimiters; `#`/`!` start comments; backslashes are used for escaping and line continuation. Verify encoding across your editor, Git, Maven, and runtime; do not assume non-Spring properties loaders obey `spring.messages.encoding`.

## 7. Spring `messages` and Jakarta `ValidationMessages` Are Two Conventions

This is a critical distinction in **validation-data-binding**.

### 7.1. Spring `BindingResult` Error Codes

Suppose the DTO is:

~~~java
public class SignupForm {
    @NotBlank
    private String name;
}
~~~

If `name=""`, Spring generates a `FieldError` with message codes at varying levels of specificity, for example:

~~~text
NotBlank.signupForm.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
~~~

Put in the Spring message bundle:

~~~properties
# messages_vi.properties
NotBlank.signupForm.name=Tên không được để trống
~~~

Thymeleaf `th:errors="*{name}"` can resolve `FieldError` via `MessageSource` in the `vi` locale. Object/field-specific codes let you customize messages per form while falling back to general codes when omitted.

`signupForm` is the model attribute name in the controller. If you rename it, specific keys can change; check `FieldError.getCodes()` in tests rather than guessing.

### 7.2. Jakarta Validation Uses Separate Files

A constraint with a message template:

~~~java
@NotBlank(message = "{customer.name.required}")
private String name;
~~~

When using `jakarta.validation.Validator` with the default `MessageInterpolator`, the key `customer.name.required` is normally searched in:

~~~text
src/main/resources/ValidationMessages.properties
src/main/resources/ValidationMessages_vi.properties
src/main/resources/ValidationMessages_en.properties
~~~

Example:

~~~properties
# ValidationMessages.properties
customer.name.required=Customer name is required
~~~

~~~properties
# ValidationMessages_vi.properties
customer.name.required=Cần nhập tên khách hàng
~~~

**Spring's `messages*.properties` and Jakarta's `ValidationMessages*.properties` are not the same source by default.** Just having a key in `messages_vi.properties` does not mean a raw Jakarta `Validator` call will read it.

### 7.3. Sharing Messages Intentionally

Spring's `LocalValidatorFactoryBean` supports `setValidationMessageSource(...)`:

~~~java
@Configuration
class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator(
            MessageSource messages) {

        LocalValidatorFactoryBean bean =
                new LocalValidatorFactoryBean();
        bean.setValidationMessageSource(messages);
        return bean;
    }
}
~~~

This is a **conceptual standalone configuration snippet**, not part of the runnable demo. In real usage, add imports, verify Spring Boot auto-configuration, and avoid registering competing validators. Avoid casually enabling `useCodeAsDefaultMessage` on a `MessageSource` used for Jakarta interpolation: it can prevent fallback to the provider's built-in messages from working as expected.

A project should clearly decide its message sources: `messages` for UI and Spring `FieldError`, `ValidationMessages` for Jakarta constraint templates, or a tested bridge configuration.

## 8. Locale in Spring MVC: Accept-Language

Spring MVC uses a `LocaleResolver` to obtain the request's locale. In common setups, clients specify it via:

~~~http
GET /signup/welcome?name=Lan
Accept-Language: vi-VN,vi;q=0.9,en;q=0.8
~~~

A handler can accept `Locale`:

~~~java
@GetMapping("/welcome")
@ResponseBody
String welcome(@RequestParam String name,
               Locale locale) {
    return messageSource.getMessage(
            "signup.welcome",
            new Object[] {name},
            locale);
}
~~~

The snippet assumes `messageSource` has been injected.

**Do not confuse `Accept-Language` with `?lang=vi`.** When using `AcceptHeaderLocaleResolver`, the `lang` query parameter does not change the locale automatically. To switch via query/session, you need `LocaleChangeInterceptor` paired with a `LocaleResolver` that supports changing locales (such as `SessionLocaleResolver`), or a custom locale strategy. `AcceptHeaderLocaleResolver` does not support `setLocale` that way.

In background jobs or message consumers, there is no HTTP request to infer a locale: pass `Locale` explicitly or apply a business default policy. Locale only controls presentation, not authentication/authorization.

## 9. Java 17+ / Spring Boot 3.5.7 Project

The demo application has a name/email/age form and two text endpoints to test parameterized messages and regional fallback. It uses Spring MVC, Thymeleaf, and Jakarta Validation. **You do not need to define a new `MessageSource` bean** when the base `messages.properties` file is present.

### 9.1. Structure

~~~text
localized-signup/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/i18n/
    │   │   ├── Application.java
    │   │   ├── SignupForm.java
    │   │   └── SignupController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       ├── messages_en.properties
    │       ├── messages_vi.properties
    │       ├── messages_vi_VN.properties
    │       └── templates/signup.html
    └── test/
        └── java/com/example/i18n/
            └── SignupControllerTest.java
~~~

### 9.2. pom.xml

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
    <artifactId>localized-signup</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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
~~~

This is a Servlet/Spring MVC application, not WebFlux. Spring Boot manages dependency versions; use JDK 17+. Production projects should track Boot patch releases according to support/security policy rather than blindly pinning the demo version.

### 9.3. Application.java

~~~java
package com.example.i18n;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 9.4. SignupForm.java

~~~java
package com.example.i18n;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

The annotations use default Jakarta constraint messages. Spring MVC creates `FieldError` codes such as `NotBlank.signupForm.name`; in the template, `MessageSource` can prioritize the keys defined in `messages_vi.properties`.

### 9.5. SignupController.java

~~~java
package com.example.i18n;

import jakarta.validation.Valid;
import org.springframework.context.MessageSource;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import java.util.Locale;

@Controller
@RequestMapping("/signup")
public class SignupController {

    private final MessageSource messages;

    public SignupController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping
    public String form(Model model) {
        model.addAttribute("signupForm", new SignupForm());
        return "signup";
    }

    @PostMapping
    public String submit(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "signup";
        }
        return "redirect:/signup/success";
    }

    @GetMapping(
            value = "/welcome",
            produces = "text/plain;charset=UTF-8")
    @ResponseBody
    public String welcome(
            @RequestParam(defaultValue = "Lan") String name,
            Locale locale) {

        return messages.getMessage(
                "signup.welcome",
                new Object[] {name},
                locale);
    }

    @GetMapping(
            value = "/region",
            produces = "text/plain;charset=UTF-8")
    @ResponseBody
    public String region(Locale locale) {
        return messages.getMessage(
                "signup.region", null, locale);
    }

    @GetMapping(
            value = "/success",
            produces = "text/plain;charset=UTF-8")
    @ResponseBody
    public String success(Locale locale) {
        return messages.getMessage(
                "signup.success", null, locale);
    }
}
~~~

`@Valid` and `BindingResult` must sit side by side for the controller to handle form errors. On error, it returns the same `signup` view to preserve input and `FieldError`s; when valid, it redirects. `Locale locale` is resolved by Spring MVC per request. `produces` includes an explicit charset for endpoints returning Vietnamese text directly.

### 9.6. application.properties

~~~properties
server.port=8080
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
spring.thymeleaf.cache=false
~~~

Disabling Thymeleaf cache is only for convenience while learning and editing templates.

### 9.7. messages.properties

~~~properties
# src/main/resources/messages.properties
signup.title=Sign up
signup.name=Full name
signup.email=Email
signup.age=Age
signup.submit=Submit
signup.success=Accepted
signup.welcome=Hello {0}!
signup.region=General message

NotBlank.signupForm.name=Name is required
NotBlank.signupForm.email=Email is required
Email.signupForm.email=Email is not valid
NotNull.signupForm.age=Age is required
Min.signupForm.age=Age must be at least 18
typeMismatch.signupForm.age=Age must be an integer
~~~

The base file provides default translations; keys like `NotBlank.signupForm.name` are Spring field-error codes, not `ValidationMessages` file entries.

### 9.8. messages_en.properties

~~~properties
# src/main/resources/messages_en.properties
signup.welcome=Hello {0}!
signup.region=English message
~~~

These two keys override the base file for English. `signup.title` is not in the `en` file, so it falls back to `Sign up` from `messages.properties`. Language/region files do not have to duplicate every key if the policy permits fallback.

### 9.9. messages_vi.properties

~~~properties
# src/main/resources/messages_vi.properties
signup.title=Đăng ký
signup.name=Họ và tên
signup.email=Email
signup.age=Tuổi
signup.submit=Gửi
signup.success=Đã tiếp nhận
signup.welcome=Chào {0}!
signup.region=Thông điệp chung cho tiếng Việt

NotBlank.signupForm.name=Tên không được để trống
NotBlank.signupForm.email=Cần nhập Email
Email.signupForm.email=Email không hợp lệ
NotNull.signupForm.age=Cần nhập tuổi
Min.signupForm.age=Tuổi phải từ 18
typeMismatch.signupForm.age=Tuổi phải là số nguyên
~~~

The Vietnamese file uses UTF-8. Keys specific to `signupForm` are picked by Thymeleaf's `th:errors` via Spring `MessageSource`; not all validation exceptions outside MVC read this file automatically.

### 9.10. messages_vi_VN.properties

~~~properties
# src/main/resources/messages_vi_VN.properties
signup.region=Thông điệp riêng cho Việt Nam
~~~

Locale `vi-VN` picks the regional key for `signup.region`, while taking `signup.title` from `messages_vi.properties` because the regional file does not define that key.

### 9.11. templates/signup.html

~~~html
<!DOCTYPE html>
<html lang="en"
      th:lang="${#locale.language}"
      xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="#{signup.title}">Sign up</title>
    <style>
        .error { color: #b00020; }
        .invalid { border: 1px solid #b00020; }
    </style>
</head>
<body>
<h1 th:text="#{signup.title}">Sign up</h1>

<form th:action="@{/signup}"
      th:object="${signupForm}"
      method="post">

    <div>
        <label for="name"
               th:text="#{signup.name}">Full name</label>
        <input type="text"
               th:field="*{name}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('name')}"
           th:errors="*{name}"></p>
    </div>

    <div>
        <label for="email"
               th:text="#{signup.email}">Email</label>
        <input type="text"
               th:field="*{email}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}"></p>
    </div>

    <div>
        <label for="age"
               th:text="#{signup.age}">Age</label>
        <input type="text"
               inputmode="numeric"
               th:field="*{age}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('age')}"
           th:errors="*{age}"></p>
    </div>

    <button type="submit"
            th:text="#{signup.submit}">Submit</button>
</form>
</body>
</html>
~~~

- `#{signup.title}` resolves the message by locale.
- `${signupForm}` is the form model variable.
- `*{name}` is a property of the selected form object.
- `th:errors` renders `FieldError`s resolved through `MessageSource`.
- `th:field` uses Spring binding status to redisplay input, including the rejected value when `age=abc` cannot be converted to `Integer`.
- `${#locale.language}` keeps the HTML `lang` attribute aligned with the language.

Do not replace `th:field` with plain Java getter reads if you need to retain invalid input values. The view applies appropriate escaping; avoid `th:utext` with untrusted data to prevent XSS.

## 10. HTTP Smoke Test

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Send:

~~~bash
curl -s -H "Accept-Language: vi" \
  "http://localhost:8080/signup/welcome?name=Lan"

curl -s -H "Accept-Language: en" \
  "http://localhost:8080/signup/welcome?name=Lan"

curl -s -H "Accept-Language: vi-VN" \
  "http://localhost:8080/signup/region"

curl -s -H "Accept-Language: vi" \
  "http://localhost:8080/signup/region"

curl -s -H "Accept-Language: fr-FR" \
  "http://localhost:8080/signup/region"
~~~

Five separate **response bodies**:

~~~text
Chào Lan!
Hello Lan!
Thông điệp riêng cho Việt Nam
Thông điệp chung cho tiếng Việt
General message
~~~

`curl -s` does not necessarily append newlines; these five lines are listed for comparison, not as a Spring Boot log output.

### Translated Form Errors

~~~bash
curl -i -X POST "http://localhost:8080/signup" \
  -H "Accept-Language: vi" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=" \
  --data-urlencode "email=sai-email" \
  --data-urlencode "age=16"
~~~

The HTML form will contain these error sentences:

~~~text
Tên không được để trống
Email không hợp lệ
Tuổi phải từ 18
~~~

In the demo, the controller intentionally renders the view again with HTTP 200 when the form is invalid. That is a handler policy, not a rule that all `@Valid` errors must return 200. With `age=abc`, `BindingResult` holds a `typeMismatch` error and can preserve the rejected input `abc` for `th:field`; the displayed message is `Tuổi phải là số nguyên`.

## 11. MockMvc Testing for Locale and Fallback

File `src/test/java/com/example/i18n/SignupControllerTest.java`:

~~~java
package com.example.i18n;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.MessageSource;
import org.springframework.context.NoSuchMessageException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.servlet.ModelAndView;

import java.util.Locale;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MessageSource messages;

    @Test
    void vietnameseTitle() {
        assertEquals("Đăng ký", messages.getMessage(
                "signup.title", null,
                Locale.forLanguageTag("vi")));
    }

    @Test
    void englishTitleFallsBackToBase() {
        assertEquals("Sign up", messages.getMessage(
                "signup.title", null, Locale.ENGLISH));
    }

    @Test
    void regionOverrideWins() {
        assertEquals("Thông điệp riêng cho Việt Nam",
                messages.getMessage(
                    "signup.region", null,
                    Locale.forLanguageTag("vi-VN")));
    }

    @Test
    void unknownLocaleFallsBackToBase() {
        assertEquals("General message",
                messages.getMessage(
                    "signup.region", null,
                    Locale.forLanguageTag("fr-FR")));
    }

    @Test
    void welcomeUsesAcceptLanguage() throws Exception {
        mvc.perform(get("/signup/welcome")
                        .param("name", "Lan")
                        .header("Accept-Language", "vi"))
                .andExpect(status().isOk())
                .andExpect(content().string("Chào Lan!"));

        mvc.perform(get("/signup/welcome")
                        .param("name", "Lan")
                        .header("Accept-Language", "en"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello Lan!"));
    }

    @Test
    void formLabelsAreLocalized() throws Exception {
        mvc.perform(get("/signup")
                        .header("Accept-Language", "vi"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup"))
                .andExpect(content().string(
                        containsString("Đăng ký")));
    }

    @Test
    void validationErrorsUseMessageCodes()
            throws Exception {

        mvc.perform(post("/signup")
                        .header("Accept-Language", "vi")
                        .param("name", "")
                        .param("email", "sai-email")
                        .param("age", "16"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup"))
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "name", "email", "age"))
                .andExpect(content().string(
                        containsString("Tên không được để trống")))
                .andExpect(content().string(
                        containsString("Email không hợp lệ")))
                .andExpect(content().string(
                        containsString("Tuổi phải từ 18")));
    }

    @Test
    void conversionErrorKeepsRawInput()
            throws Exception {

        var response = mvc.perform(post("/signup")
                        .header("Accept-Language", "vi")
                        .param("name", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "abc"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "age"))
                .andExpect(content().string(
                        containsString("Tuổi phải là số nguyên")))
                .andReturn();

        ModelAndView mav = response.getModelAndView();
        assertNotNull(mav);

        BindingResult errors = (BindingResult)
                mav.getModel().get(
                        BindingResult.MODEL_KEY_PREFIX
                        + "signupForm");
        assertNotNull(errors);

        FieldError conversion = errors.getFieldErrors("age")
                .stream()
                .filter(FieldError::isBindingFailure)
                .findFirst()
                .orElseThrow();

        assertEquals("abc", conversion.getRejectedValue());
        assertEquals("abc", errors.getFieldValue("age"));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/signup")
                        .param("name", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "22"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/signup/success"));
    }

    @Test
    void missingCodeUsesExplicitFallback() {
        assertEquals("Fallback",
                messages.getMessage(
                        "missing.code", null, "Fallback",
                        Locale.ENGLISH));
    }

    @Test
    void missingCodeWithoutFallbackThrows() {
        assertThrows(NoSuchMessageException.class,
                () -> messages.getMessage(
                        "missing.code", null,
                        Locale.ENGLISH));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

This suite of **11 tests** demonstrates base-file lookup, `en` fallback, `vi-VN` override, unsupported locale fallback, `MessageFormat` `{0}`, HTML labels, Vietnamese Bean Validation/`BindingResult` errors, `typeMismatch`, redirects, and missing keys. It does not depend on violation order. If Spring Security is added later, POST tests may require a CSRF token; HTTP 403 errors from CSRF occur before controller validation runs.

## 12. Multiple Message Groups, Caching, and Operations

Large projects can split files by module:

~~~text
src/main/resources/
├── messages.properties
├── messages_vi.properties
└── i18n/
    ├── checkout.properties
    ├── checkout_vi.properties
    ├── validation.properties
    └── validation_vi.properties
~~~

~~~properties
spring.messages.basename=messages,i18n/checkout,i18n/validation
~~~

Keys like `checkout.payment.failed` and `signup.validation.age` avoid collisions. Spring Boot 3.5 offers `spring.messages.common-messages` for locale-independent message resources; use it only when you genuinely have shared content.

Spring Framework provides `ResourceBundleMessageSource` backed by Java `ResourceBundle` and `ReloadableResourceBundleMessageSource` for use cases needing more flexible reloading. For typical apps, you do not need to declare a bean yourself just to use `messages_vi.properties`. The property:

~~~properties
spring.messages.cache-duration=10s
~~~

controls caching, though **it does not mean files packaged inside a JAR will hot-reload** when edited on the filesystem. An external resource mechanism or redeploy is required to update translations in production.

`spring.messages.use-code-as-default-message=true` is useful for debugging missing keys, but should not be used to mask missing translations in production. When the same `MessageSource` is also used for Jakarta validation interpolation, returning the raw code can interfere with the provider's default fallback.

## 13. Checklist and Common Pitfalls

| Symptom | Cause | How to Handle |
| --- | --- | --- |
| Template renders `??signup.title??` | Key or bundle did not resolve | Check basename, classpath, `messages.properties` |
| Only `messages_vi.properties` exists | Missing base file for auto-configuration | Create `messages.properties` |
| `messages_vi-VN.properties` is not picked up | Wrong filename convention | Use `messages_vi_VN.properties` |
| `fr-FR` returns different text across machines | JVM locale fallback | Disable `fallback-to-system-locale` |
| Garbled Vietnamese diacritics | Inconsistent encoding | Use UTF-8 and test after build |
| `{0}` is not replaced with name | Args omitted or wrong escaping | Pass `Object[]` and use `MessageFormat` |
| Single quotes disappear | `MessageFormat` quoting | Check doubled quotes `''` |
| `?lang=vi` does not change locale | Query-based strategy not configured | Use `Accept-Language` or proper `LocaleChangeInterceptor` |
| Constraint message stays in English | Missing Spring field error key or using Jakarta `ValidationMessages` | Inspect `getCodes()` and both bundle families |
| Renaming model object breaks messages | Specific key depends on `objectName` | Update keys or fallback codes |
| Edits to bundle show no effect | Cache or packaged JAR | Check reload strategy or redeploy |
| Duplicate keys across basenames | Key collision | Namespace keys and test precedence |
| No validation errors produced | Missing starter/constraint/`@Valid` | Check Bean Validation provider and `BindingResult` |
| Translation rendered as HTML | Unescaped output used | Prefer `th:text` and escape output against XSS |
| Email/token leaked in error | Echoing raw invalid value | Return only approved field/code/message |

A QA checklist should cover the base file, `vi`/`en`/`vi-VN`/`fr` locales, UTF-8, placeholder indices, `MessageFormat` apostrophes, `FieldError.getCodes()`, and actual HTML responses. Regional files only override keys that genuinely differ; there is no need to copy every key when fallback is allowed.

## 14. Self-Check Questions

**1.** Why must `messages.properties` exist even if the application mainly serves Vietnamese?  
Because it acts as the fallback and lets Spring Boot recognize the basename when auto-configuring `MessageSource`.

**2.** Where does `vi-VN` look for messages?  
In standard order: `messages_vi_VN.properties` → `messages_vi.properties` → `messages.properties`.

**3.** Which files correspond to `spring.messages.basename=i18n/ui`?  
`src/main/resources/i18n/ui.properties` and variants such as `ui_vi.properties` on the classpath.

**4.** Does `application.properties` replace `messages.properties`?  
No. One holds configuration, while the other holds message keys and translations.

**5.** How do the two `MessageSource.getMessage` overloads (with and without a default) differ?  
With a default, it returns the caller's fallback; without a default, it can throw `NoSuchMessageException`.

**6.** Why is `#{signup.title}` different from `${signupForm.name}`?  
`#{...}` resolves a message; `${...}` accesses a model variable.

**7.** Who uses `ValidationMessages_vi.properties`?  
Jakarta Bean Validation's `MessageInterpolator` by convention, separate from Spring's regular message bundles.

**8.** Why should you inspect `FieldError.getCodes()`?  
Because Spring generates multiple error codes at varying specificity levels, which can change when renaming objects or fields.

**9.** Can you use just `?lang=vi` to switch locales under the default `Accept-Language` configuration?  
No; a locale resolution strategy supporting query parameters is required.

**10.** How do you ensure fallback responses are identical across servers?  
Provide a base file, disable system-locale fallback, and test with an untranslated locale.

## Conclusion

~~~text
message code signup.title
      |
      v
MessageSource + Locale
      |
      +-- messages_vi_VN.properties
      +-- messages_vi.properties
      +-- messages.properties
      |
      v
Đăng ký / Sign up / fallback

Spring MVC @Valid → BindingResult → FieldError codes
      |
      v
MessageSource → th:errors by request locale
~~~

Keep **basenames stable**, maintain a base file, use proper suffixes, UTF-8, clear fallbacks, and namespaced codes. **Message translation** and **data validation** are two independent responsibilities: Spring `MessageSource` can translate errors in views, while Jakarta Validation uses `ValidationMessages` under its own convention. Verify both the Java API and HTTP/HTML responses to be sure users actually see the right language.

## References

- [Spring Boot 3.5 — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html)
- [Spring Framework — MessageSource API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/context/MessageSource.html)
- [Spring Framework — Error Code Resolution](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring Framework — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Hibernate Validator 8 — Message interpolation](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation)
- [Java 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Java 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html)
