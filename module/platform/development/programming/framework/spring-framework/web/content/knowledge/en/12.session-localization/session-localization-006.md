# MessageSource, Validation Messages, and UI Localization in Spring MVC

## 1. Objectives and Context

In a Spring MVC application with HTML forms, a single screen may need to display the same content in both Vietnamese and English. Field labels, buttons, form validation error messages, and save confirmation notices all need translations. Hardcoding every string in controllers or views forces you to change logic in many places whenever adding a new language.

Spring provides three layers of responsibility:

1. **Locale** describes the language/region currently in use (for example `vi`, `vi-VN`, `en`).
2. **LocaleResolver** determines the `Locale` for each HTTP request; `LocaleChangeInterceptor` can let users pick a language via a query parameter when the resolver permits it.
3. **MessageSource** looks up text from resource bundles by message key and `Locale`; Spring MVC/Thymeleaf also integrates with `MessageSource` to display errors from `BindingResult`.

This lesson focuses on **Spring Web MVC (Servlet stack)**, `MessageSource`, form validation errors, and server-rendered UI i18n with Thymeleaf. The runnable example uses Java 17, Spring Boot 3.3.5, and Spring Framework 6.1.x.

Desired experience:

```text
GET /contacts/new?lang=vi
→ Tạo liên hệ / Họ và tên / Lưu liên hệ

GET /contacts/new?lang=en
→ Create contact / Name / Save contact

POST /contacts with name too short
→ still displays the form, but validation errors are translated
```

**i18n** (internationalization) is designing an application capable of serving multiple languages; **l10n** (localization) is adapting content and formatting for each `Locale`. `MessageSource` is not an automatic translation engine: developers must supply translations and fallback rules.

## 2. `MessageSource` and Resource Bundles

The `org.springframework.context.MessageSource` interface defines message lookups by code, arguments, and `Locale`:

```java
String getMessage(
        String code, Object[] args,
        String defaultMessage, Locale locale);

String getMessage(
        String code, Object[] args, Locale locale)
        throws NoSuchMessageException;

String getMessage(
        MessageSourceResolvable resolvable, Locale locale)
        throws NoSuchMessageException;
```

This is an **API signature excerpt**, not a standalone Java class with full imports. Suppose the Vietnamese file contains:

```properties
contact.heading=Tạo liên hệ
contact.saved=Đã lưu liên hệ {0}.
```

And the English file:

```properties
contact.heading=Create contact
contact.saved=Saved contact for {0}.
```

Calling:

```java
String vi = messageSource.getMessage(
    "contact.saved", new Object[]{"Lan"}, Locale.forLanguageTag("vi"));
String en = messageSource.getMessage(
    "contact.saved", new Object[]{"Lan"}, Locale.ENGLISH);
```

Output:

```text
Đã lưu liên hệ Lan.
Saved contact for Lan.
```

`{0}` is a placeholder following `java.text.MessageFormat` rules. Mind single-quote escaping rules: in `MessageFormat` patterns, two single quotes `''` represent one literal apostrophe; always test translations containing apostrophes or complex braces.

If a key is not found:

- The overload with `defaultMessage` returns the supplied fallback.
- Overloads without a default may throw `NoSuchMessageException`.
- Setting `useCodeAsDefaultMessage` can render the key code itself, though using it indiscriminately hides missing translations.

Do not use translated sentence text as the identifier—for example, never name a key `Tạo liên hệ`. Use stable, semantic codes like `contact.heading`, `contact.submit`, and `contact.error.email`.

### Spring Boot `MessageSource` Configuration

Spring Boot auto-configures `MessageSource` when it finds a base bundle matching the configured basename, defaulting to `messages`. You can create:

```text
src/main/resources/
├── application.properties
├── messages.properties
├── messages_en.properties
└── messages_vi.properties
```

**`messages.properties` is required**, even if most translations live in `messages_en.properties` and `messages_vi.properties`. If only locale-suffixed files exist, Boot auto-configuration may not activate.

`application.properties`:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

- `basename` can point to multiple bundles, such as `messages,validation`.
- UTF-8 preserves Vietnamese diacritics.
- `fallback-to-system-locale=false` reduces dependence on the server OS locale; lookups can still fall back to the base bundle.
- Resource bundles are not online translation services: loading a messages file does not automatically translate database strings or arbitrary UI text.

## 3. `LocaleResolver` and Choosing the Request's Language

Spring MVC resolves locale via `LocaleResolver`:

| Resolver | Locale source | Can `?lang=vi` change it? |
| --- | --- | --- |
| `AcceptHeaderLocaleResolver` | Client's HTTP `Accept-Language` | **No**; does not support `setLocale` via interceptor |
| `SessionLocaleResolver` | Session attribute, then fallback | **Yes** |
| `CookieLocaleResolver` | Client cookie, then fallback | **Yes**, subject to cookie policy |

For apps that simply follow the browser's header, `AcceptHeaderLocaleResolver` is usually sufficient; no session is needed just to read a header. When providing a "Tiếng Việt / English" toggle on a traditional website, `SessionLocaleResolver` paired with `LocaleChangeInterceptor` is straightforward.

Warning: adding `LocaleChangeInterceptor` while keeping `AcceptHeaderLocaleResolver` causes `?lang=vi` to throw `UnsupportedOperationException`, because the server cannot rewrite the browser's `Accept-Language` request header.

Locale is not a time zone or nationality. Two users both using `vi-VN` can sit in different time zones. `Accept-Language` does not prove user identity either; it is merely a client preference.

## 4. `BindingResult` and Localizing Validation Messages

A form controller may have the signature:

```java
@PostMapping("/contacts")
public String submit(
        @Valid @ModelAttribute("contactForm") ContactForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "contacts/new";
    }
    return "redirect:/contacts/done";
}
```

This is a **snippet**; the full controller appears in Section 6. Processing sequence:

```text
HTTP POST form fields
   |
   v
@ModelAttribute: binds strings from request into ContactForm
   |
   v
@Valid: Jakarta Bean Validation checks constraints
   |
   v
BindingResult contains FieldError or ObjectError
   |
   v
Controller returns the form view when errors exist
   |
   v
Thymeleaf th:errors and Spring MessageSource
   |
   v
Messages in the request's Locale
```

A common confusion arises because there are **two message resolution paths**:

1. **Bean Validation message interpolation** performed by the provider (such as Hibernate Validator) when processing `@NotBlank(message = "...")`. Jakarta Validation's standard bundle is typically `ValidationMessages.properties`, or it can be bridged to Spring `MessageSource` via `LocalValidatorFactoryBean`.
2. **Spring `MessageSource` resolution on `BindingResult`**: `FieldError` carries a prioritized list of **error codes**, and Thymeleaf `th:errors` can resolve those codes from `messages*.properties` by locale.

Suppose a DTO has:

```java
@NotBlank
@Size(min = 2, max = 40)
private String name;
```

A `@NotBlank` violation on `contactForm.name` typically generates codes in priority order such as:

```text
NotBlank.contactForm.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

When `messages_vi.properties` contains:

```properties
NotBlank.contactForm.name=Vui lòng nhập họ và tên.
Size.contactForm.name=Tên phải có từ 2 đến 40 ký tự.
```

Thymeleaf can display those corresponding localized messages for each error type. You do not have to hardcode `message="Vui lòng nhập..."` directly on the Java DTO.

**Type conversion errors** also land in `BindingResult`. If a form has an `int age` field and the user enters `xyz`, the error may carry code `typeMismatch.contactForm.age`, which differs from `@Min` or `@NotNull`. Translating validation errors requires knowing which codes are actually generated.

`BindingResult` must appear **immediately after** its corresponding `@Valid @ModelAttribute` parameter for the controller method to receive errors. If validation fails and you redirect anyway, the new request will not automatically retain `BindingResult` — the simple approach is to re-render the same view, keeping errors in the current request.

## 5. Distinguishing `MessageSource` Arguments from Validation Placeholders

Messages from Spring `MessageSource` use `{0}`, `{1}`... per `MessageFormat`:

```properties
contact.saved=Saved contact for {0}.
```

Bean Validation message templates can use constraint attribute placeholders such as `{min}` and `{max}`:

```java
@Size(min = 2, max = 40, message = "Length must be {min} to {max}")
private String name;
```

When using Spring `MessageSource` to supply Bean Validation messages, provider interpolation and `MessageFormat` handling can interact. Do not assume putting `{min}` into any `messages.properties` file means `MessageSource.getMessage` automatically knows `min`. In the runnable example below, errors displayed on the view use **Spring `FieldError` codes** with complete static messages so resolution is predictable and easy to verify.

## 6. Runnable Application: Java 17 + Spring MVC + Thymeleaf

The application creates a contact, allows switching between two languages via `?lang=vi`/`?lang=en`, and translates form labels and errors. No database is used; when valid, the app simulates saving and redirects.

### 6.1. Project Structure

```text
mvc-i18n-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/i18n/
    │   │   ├── I18nApplication.java
    │   │   ├── LocaleConfig.java
    │   │   ├── ContactForm.java
    │   │   └── ContactController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       ├── messages_en.properties
    │       ├── messages_vi.properties
    │       └── templates/contacts/
    │           ├── new.html
    │           └── done.html
    └── test/java/example/i18n/
        └── I18nWebTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>mvc-i18n-demo</artifactId>
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
```

**`src/main/java/example/i18n/I18nApplication.java`**

```java
package example.i18n;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nApplication {
    public static void main(String[] args) {
        SpringApplication.run(I18nApplication.class, args);
    }
}
```

### 6.2. Configuring Session-Based Language Selection

**`src/main/java/example/i18n/LocaleConfig.java`**

```java
package example.i18n;

import java.util.Locale;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration
public class LocaleConfig implements WebMvcConfigurer {

    @Bean
    public LocaleResolver localeResolver() {
        SessionLocaleResolver resolver = new SessionLocaleResolver();
        resolver.setDefaultLocale(Locale.ENGLISH);
        return resolver;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        LocaleChangeInterceptor change = new LocaleChangeInterceptor();
        change.setParamName("lang");
        change.setHttpMethods("GET");
        registry.addInterceptor(change);
    }
}
```

The bean named `localeResolver` lets MVC use `SessionLocaleResolver`. When a user visits `GET /contacts/new?lang=vi`, the interceptor updates the session's locale. Subsequent requests in the same session (with the matching cookie) use that locale. Fixing the default to English keeps the example independent of the host machine's locale.

For stateless REST apps, reading `Accept-Language` directly is usually more appropriate than sessions. When only `vi`/`en` are supported, validate/restrict accepted locales from inputs in real designs rather than allowing arbitrary locale codes.

### 6.3. DTO and Controller

**`src/main/java/example/i18n/ContactForm.java`**

```java
package example.i18n;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ContactForm {
    @NotBlank
    @Size(min = 2, max = 40)
    private String name;

    @NotBlank
    @Email
    private String email;

    public ContactForm() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

**`src/main/java/example/i18n/ContactController.java`**

```java
package example.i18n;

import java.util.Locale;
import java.util.Map;

import jakarta.validation.Valid;
import org.springframework.context.MessageSource;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/contacts")
public class ContactController {
    private final MessageSource messages;

    public ContactController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("contactForm", new ContactForm());
        return "contacts/new";
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("contactForm") ContactForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "contacts/new";
        }

        // Demo: no repository, simulate saving successfully.
        redirectAttributes.addFlashAttribute(
                "savedName", form.getName().strip());
        return "redirect:/contacts/done";
    }

    @GetMapping("/done")
    public String done() {
        return "contacts/done";
    }

    @GetMapping("/label")
    @ResponseBody
    public Map<String, String> label(Locale locale) {
        String heading = messages.getMessage(
                "contact.heading", null, locale);
        return Map.of("heading", heading);
    }
}
```

When POST input is invalid, Spring keeps `ContactForm` and `BindingResult` in the request's model, and the controller re-renders the form. When valid, redirecting prevents browser refresh from resubmitting the POST, while the `savedName` flash attribute serves the immediate GET. Since the app does not persist data durably, the done endpoint is only an example confirmation screen, not a real contact management system.

The `GET /contacts/label` endpoint demonstrates calling `MessageSource` directly with the MVC-resolved `Locale`. `@ResponseBody` is required because the class is `@Controller` and this method returns JSON rather than a view name.

### 6.4. All Resource Bundles

**`src/main/resources/application.properties`**

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

**`src/main/resources/messages.properties`** — English fallback:

```properties
contact.heading=Create contact
contact.name=Name
contact.email=Email
contact.submit=Save contact
contact.done=Completed
contact.saved=Saved contact for {0}.
NotBlank.contactForm.name=Name is required.
Size.contactForm.name=Name must have 2 to 40 characters.
NotBlank.contactForm.email=Email is required.
Email.contactForm.email=Enter a valid email address.
```

**`src/main/resources/messages_en.properties`**

```properties
contact.heading=Create contact
contact.name=Name
contact.email=Email
contact.submit=Save contact
contact.done=Completed
contact.saved=Saved contact for {0}.
NotBlank.contactForm.name=Name is required.
Size.contactForm.name=Name must have 2 to 40 characters.
NotBlank.contactForm.email=Email is required.
Email.contactForm.email=Enter a valid email address.
```

**`src/main/resources/messages_vi.properties`**

```properties
contact.heading=Tạo liên hệ
contact.name=Họ và tên
contact.email=Địa chỉ email
contact.submit=Lưu liên hệ
contact.done=Hoàn tất
contact.saved=Đã lưu liên hệ {0}.
NotBlank.contactForm.name=Vui lòng nhập họ và tên.
Size.contactForm.name=Tên phải có từ 2 đến 40 ký tự.
NotBlank.contactForm.email=Vui lòng nhập email.
Email.contactForm.email=Email không đúng định dạng.
```

The `contactForm` name in `NotBlank.contactForm.name` **must match** the model attribute name passed in the controller. `@Size` errors on `name` and `@Email` errors on `email` resolve their matching keys. A single invalid field can produce multiple errors; never assume there is always only one `FieldError`.

### 6.5. Thymeleaf Templates with Messages and Validation Errors

**`src/main/resources/templates/contacts/new.html`**

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="#{contact.heading}">Create contact</title>
</head>
<body>
    <nav>
        <a th:href="@{/contacts/new(lang='vi')}">Tiếng Việt</a>
        <a th:href="@{/contacts/new(lang='en')}">English</a>
    </nav>
    <h1 th:text="#{contact.heading}">Create contact</h1>

    <form th:action="@{/contacts}"
          th:object="${contactForm}" method="post">
        <label for="name" th:text="#{contact.name}">Name</label>
        <input id="name" th:field="*{name}" type="text">
        <p th:if="${#fields.hasErrors('name')}"
           th:errors="*{name}">Name error</p>

        <label for="email" th:text="#{contact.email}">Email</label>
        <input id="email" th:field="*{email}" type="email">
        <p th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}">Email error</p>

        <button type="submit" th:text="#{contact.submit}">
            Save contact
        </button>
    </form>
</body>
</html>
```

Three Thymeleaf expression types to remember:

- `#{contact.heading}` looks up a message key in the bundles using the active locale.
- `${contactForm}` references an object in the Spring model.
- `*{name}` selects a property of the object bound by `th:object`.

`th:field` binds inputs and preserves values when the form re-renders with errors. `#fields.hasErrors('name')` and `th:errors="*{name}"` read Spring `BindingResult`, displaying messages resolved through `MessageSource`.

This demo page hardcodes `html lang="en"`; in production, dynamically set `lang` to match the displayed locale, for example by exposing `htmlLang` from the controller and using `th:lang="${htmlLang}"`. This matters for screen readers and accessibility, even though message lookup still works in the demo.

**`src/main/resources/templates/contacts/done.html`**

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="#{contact.done}">Completed</title>
</head>
<body>
    <h1 th:text="#{contact.done}">Completed</h1>
    <p th:if="${savedName}"
       th:text="#{contact.saved(${savedName})}">
       Saved contact
    </p>
    <a th:href="@{/contacts/new}"
       th:text="#{contact.heading}">Create contact</a>
</body>
</html>
```

`#{contact.saved(${savedName})}` passes `savedName` into the message's `{0}` placeholder. The template uses `th:text` to escape HTML; never use `th:utext` for user-entered strings. Flash attributes live only for the redirect target: refreshing the done page does not guarantee the notice will reappear.

## 7. Running and Expected Output

In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Run both commands **sequentially**. Once running, open:

```text
http://localhost:8080/contacts/new?lang=vi
```

Main text elements:

```text
Tiếng Việt  English
Tạo liên hệ
Họ và tên
Địa chỉ email
Lưu liên hệ
```

Click the English link; within the same session, the UI switches to:

```text
Tiếng Việt  English
Create contact
Name
Email
Save contact
```

Try submitting POST with `name=A` and `email=not-an-email`. `A` is one character, violating `@Size(min=2,max=40)`; `not-an-email` violates `@Email`. Under the Vietnamese locale, the errors render from the bundle:

```text
Tên phải có từ 2 đến 40 ký tự.
Email không đúng định dạng.
```

With a valid form like `name=Lan`, `email=lan@example.com`, the server redirects to `/contacts/done`. On the subsequent GET confirmation page, the expected message in Vietnamese is:

```text
Đã lưu liên hệ Lan.
```

Under the English locale, the corresponding output is:

```text
Saved contact for Lan.
```

Note that the browser must retain the session cookie. If you switch `?lang=vi` in browser A and then run `curl` without browser A's cookie, the `curl` request will revert to the default English locale.

### Calling `MessageSource` Directly via an Illustrative JSON API

`GET /contacts/label` returns a JSON object:

```json
{"heading":"Tạo liên hệ"}
```

or:

```json
{"heading":"Create contact"}
```

Depending on the session `Locale`. Using `curl` with a cookie jar on Bash:

```bash
curl -s -c cookies.txt -b cookies.txt \
  'http://localhost:8080/contacts/new?lang=vi' > /dev/null

curl -s -b cookies.txt \
  'http://localhost:8080/contacts/label'
```

The response body is typically `{"heading":"Tạo liên hệ"}`. In PowerShell, passing session cookies differs and `/dev/null` is not the standard null output path; you can use `Invoke-WebRequest` with `-WebSession`.

## 8. MockMvc Tests: Two Languages and Validation

**`src/test/java/example/i18n/I18nWebTest.java`**

```java
package example.i18n;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.MessageSource;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class I18nWebTest {
    @Autowired MockMvc mvc;
    @Autowired MessageSource messages;

    @Test
    void messagesExistInEnglishAndVietnamese() {
        assertEquals("Create contact", messages.getMessage(
                "contact.heading", null, Locale.ENGLISH));
        assertEquals("Tạo liên hệ", messages.getMessage(
                "contact.heading", null, Locale.forLanguageTag("vi")));
    }

    @Test
    void vietnameseFormRendersTranslatedHeading() throws Exception {
        mvc.perform(get("/contacts/new").param("lang", "vi"))
           .andExpect(status().isOk())
           .andExpect(view().name("contacts/new"))
           .andExpect(content().string(containsString("Tạo liên hệ")));
    }

    @Test
    void englishFormRendersTranslatedHeading() throws Exception {
        mvc.perform(get("/contacts/new").param("lang", "en"))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("Create contact")));
    }

    @Test
    void invalidFormRendersVietnameseMessages() throws Exception {
        MockHttpSession session = (MockHttpSession) mvc
                .perform(get("/contacts/new").param("lang", "vi"))
                .andReturn().getRequest().getSession(false);

        mvc.perform(post("/contacts").session(session)
                        .param("name", "A")
                        .param("email", "not-an-email"))
           .andExpect(status().isOk())
           .andExpect(model().attributeHasFieldErrors(
                   "contactForm", "name", "email"))
           .andExpect(content().string(containsString(
                   "Tên phải có từ 2 đến 40 ký tự.")))
           .andExpect(content().string(containsString(
                   "Email không đúng định dạng.")));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/contacts")
                        .param("name", "Lan")
                        .param("email", "lan@example.com"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrl("/contacts/done"));
    }
}
```

Run `mvn test`. The class contains **5 test methods**; if all pass, Maven exits with code `0`. Do not rely on test execution order, console output, or timings. The validation test creates a session via `GET ?lang=vi`, then sends `POST` **with the same session** to verify actual view translation.

In real projects, add tests checking that every message key is translated, missing-key fallbacks, unsupported locales, apostrophes, UI accessibility, language preservation across redirects, and other validation types such as `typeMismatch`.

## 9. When You Need Localized Messages Directly from the Bean Validation Provider

In the form example, errors render via Spring `BindingResult` codes. If you want translations **directly in `ConstraintViolation.getMessage()`** or want annotations to reference custom templates:

```java
@NotBlank(message = "{contact.name.required}")
private String name;
```

then you must understand **Jakarta Bean Validation message interpolation** as a separate mechanism. By convention, the provider reads `ValidationMessages.properties` and its locale variants; Spring can connect `MessageSource` via `LocalValidatorFactoryBean.setValidationMessageSource(...)`.

**Optional** configuration snippet for projects needing this (not required to run the Section 6 example):

```java
@Bean
public LocalValidatorFactoryBean applicationValidator(
        MessageSource messageSource) {
    LocalValidatorFactoryBean validator =
            new LocalValidatorFactoryBean();
    validator.setValidationMessageSource(messageSource);
    return validator;
}
```

Required imports:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
```

When using this optional configuration, make sure MVC `@Valid` actually uses the configured validator (some apps need `WebMvcConfigurer.getValidator()`), avoid competing validator beans unintentionally, and run integration tests. Do not configure both `setValidationMessageSource` and `setMessageInterpolator` on the same factory when the two options conflict.

Add keys to the bundles:

```properties
contact.name.required=Please enter your name.
```

```properties
contact.name.required=Vui lòng nhập họ và tên.
```

Those two snippets belong in `messages_en.properties` and `messages_vi.properties` respectively when using the optional bridge. Spring can use the request's `LocaleContextHolder` for message interpolation through the integrated provider; if you use a custom `ValidatorFactory` outside Spring or in async flows, the locale must be passed/configured properly.

**Do not assume** every `FieldError.getDefaultMessage()` string is automatically localized just because Thymeleaf displays errors properly. For REST APIs, to produce a locale-specific message, you can call `MessageSource.getMessage(error, locale)` (where `error` is an `ObjectError` or `FieldError` — i.e., `MessageSourceResolvable`), and return an error DTO with a stable `code` and a translated `message`. If extending `ResponseEntityExceptionHandler`, override the appropriate handler method rather than registering a duplicate `@ExceptionHandler` for an exception already handled by the base class.

## 10. Formatting Differs from Translating

`MessageSource` translates **text**. When displaying dates, times, numbers, or money, use appropriate formatters/converters. Complete standalone Java 17 example:

**`LocaleNumberDemo.java`**

```java
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleNumberDemo {
    public static void main(String[] args) {
        double number = 1234.5;
        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat germany = NumberFormat.getNumberInstance(Locale.GERMANY);
        us.setMinimumFractionDigits(2);
        germany.setMinimumFractionDigits(2);
        System.out.println(us.format(number));
        System.out.println(germany.format(number));
    }
}
```

Run:

```bash
javac LocaleNumberDemo.java
java LocaleNumberDemo
```

Typical output on a JDK with CLDR locale data:

```text
1,234.50
1.234,50
```

The example uses `double` solely to demonstrate number separators. For real money, use `BigDecimal` with explicit currency and rounding rules. Never turn `VND` into `USD` merely by swapping currency symbols.

In Spring MVC, `@DateTimeFormat`, `@NumberFormat`, `Formatter`, and `ConversionService` support form binding and formatting; they solve a different problem from message-code lookup.

## 11. Real-World Application Limitations

### 11.1. Language Selection Does Not Replace Security

`lang` is request data and can be modified arbitrarily. Never treat locale as an indicator of permissions, nationality, or tenant isolation. When using sessions/cookies, understand CSRF, session lifetimes, cache policies, and user state. If a website needs to remember locale across devices, consider storing a preference on the user account.

With `spring-boot-starter-security` and session login, form POSTs may require a CSRF token; the demo omits Spring Security so it does not include tokens. Never disable CSRF in a real application just to make a POST example work.

### 11.2. HTML Escaping and Accessibility

Thymeleaf's `th:text` escapes HTML output, preventing many XSS bugs when interpolating user input into translated strings. Never use `th:utext` on unsanitized content. Set HTML `lang` dynamically to match the actual locale, associate errors using `aria-describedby`/`aria-invalid`, and test with screen readers; an interface that translates text while keeping the wrong `lang` metadata is incomplete localization.

### 11.3. Caching and Response Representations

If HTML/JSON varies by `Accept-Language`, CDNs/reverse proxies may need `Vary: Accept-Language` or locale-aware cache keys; if locale lives in session/cookies, handle caching appropriately for personalized responses. Never share one public cache key across responses in different languages and serve user A's content to user B.

### 11.4. Background Jobs and Thread Context

`LocaleContextHolder` normally binds locale to the request thread. An email-sending task running on another worker thread **does not automatically inherit the original request's locale**; pass the recipient's `Locale` into the content-rendering function. Never use the server's default locale to translate emails for all users.

### 11.5. Pluralization and Context

`MessageFormat` supports parameters, but does not automatically solve all pluralization, gender, and grammar rules. For complex languages, consider ICU `MessageFormat` or suitable message variants. Never stitch translated fragments randomly into sentences, because word order and grammar differ across languages.

## 12. Common Errors

| Symptom | Cause | What to check |
| --- | --- | --- |
| UI displays `contact.heading` | Missing key or resolver cannot find bundle | Check basename, classpath, key, fallback |
| Only `messages_vi.properties` exists; `MessageSource` not auto-configured | Missing default bundle `messages.properties` | Add base file and test bean |
| Vietnamese diacritics appear corrupted | Wrong encoding | Save as UTF-8, set `spring.messages.encoding=UTF-8` |
| `?lang=vi` throws an exception | Interceptor changing locale on `AcceptHeaderLocaleResolver` | Use `SessionLocaleResolver` or a resolver supporting `setLocale` |
| Form uses a different locale from validation messages | Mismatched message source/validator locale, or session cookie not sent | Inspect `BindingResult.codes`, locale resolver, and cookies |
| `th:errors` shows English while labels are Vietnamese | Missing `Size.contactForm.name` key or wrong model object name | Check `FieldError.getCodes()` and bundles |
| No errors shown after submit | `BindingResult` misplaced or controller redirected when invalid | Place right after `@Valid`, re-render same view |
| `@NotBlank(message="{key}")` prints literal key | Jakarta validator cannot see bundle for interpolation | Use `ValidationMessages*.properties`/`LocalValidatorFactoryBean` |
| JSON errors are not translated | Returning `getDefaultMessage()` directly | Use `MessageSource.getMessage(error, locale)` or configure validator |
| Only one page switches language; another does not | Remaining hardcoded strings, caching, or different session | Audit all templates, bundles, and HTTP headers |
| `MessageFormat` drops apostrophes | Single-quote escaping syntax | Use `''` and write tests |
| Flash message gone after refresh | Flash only passes short-lived data to the next GET | Do not use flash as durable state |
| Returning raw `error.getRejectedValue()` in errors | Echoing sensitive input | Return only safe field/code/message and minimize logging |
| Number formatting right, currency unit wrong | Locale used in place of business currency | Carry currency explicitly and format per business context |

Systematic debugging steps:

1. Print/inspect the `Locale` returned by `LocaleResolver`.
2. Confirm `messages.properties`, `messages_en.properties`, and `messages_vi.properties` are all on the classpath.
3. Verify `spring.messages.basename` and encoding.
4. Unit-test `messageSource.getMessage("contact.heading", null, locale)`.
5. For validation, inspect `BindingResult.getFieldError("name").getCodes()` and the keys searched in bundles.
6. Distinguish `FieldError.getDefaultMessage()` from `MessageSource.getMessage(error, locale)`.
7. Render HTML and inspect `th:errors` in both locales rather than checking only JSON/Java objects.
8. Keep the same session when switching languages via `?lang=...`; also test fallback locales.
9. Check for remaining hardcoded strings, caches, or background threads reading the wrong locale context.
10. For public APIs, define stable error codes; never force clients to parse localized prose.

## 13. Pre-Deployment i18n Checklist

1. Message keys are named by domain/action, independent of translated wording.
2. Base bundle always exists; bundles for supported languages are reasonably complete.
3. All files are saved as UTF-8; Vietnamese diacritics and apostrophes are tested.
4. Resolver fits requirements: browser header, session, or cookie.
5. Language switching does not conflict with `AcceptHeaderLocaleResolver`.
6. Validation tests assert exact field codes and messages per locale.
7. Valid POST logic uses PRG where appropriate; invalid forms retain `BindingResult`.
8. Error JSON separates machine-readable codes from localized text.
9. HTML `lang`, labels, and errors support accessibility.
10. Dates, currency, units, and time zones are formatted by dedicated rules.
11. Caching, CSRF, authentication, and sessions are verified separately.
12. Background jobs receive the user's `Locale` explicitly rather than relying on the default server thread.

## 14. Self-Assessment Exercises

1. How do `LocaleResolver` and `MessageSource` differ?
2. Why does Spring Boot need the default bundle `messages.properties`?
3. How do `#{contact.heading}` and `${contactForm}` differ in Thymeleaf?
4. Why is `NotBlank.contactForm.name` used with `BindingResult` not quite the same as `@NotBlank(message="{contact.name.required}")`?
5. Why can `?lang=vi` fail when using `AcceptHeaderLocaleResolver`?
6. When validation fails, how do you preserve errors on the HTML page?
7. Why should you test locale within the same session when using `SessionLocaleResolver`?
8. How is `MessageSource.getMessage(error, locale)` helpful when constructing JSON error responses?
9. Why does `Locale` not automatically determine time zone and currency?
10. When sending an email from an async job, where should you obtain the `Locale`?

**Hints:** (1) Resolver picks the `Locale`; `MessageSource` returns text. (2) Acts as fallback and triggers auto-configuration. (3) Message key vs. model attribute. (4) Spring field error codes vs. Jakarta Bean Validation interpolation. (5) Request headers cannot be mutated from the server. (6) Place `BindingResult` immediately after `@Valid @ModelAttribute` and re-render the same form. (7) The language choice is stored in the session. (8) Resolves messages from error codes by locale instead of using a provider-dependent `defaultMessage`. (9) Business data, currency, and time zone must be tracked separately. (10) Load the user's saved preference or pass the `Locale` explicitly to the worker.

## 15. Official Documentation

- [Spring Framework — `MessageSource` interface](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/MessageSource.html)
- [Spring Framework — MVC Locale Resolution](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html)
- [Spring Framework — Binding and Validation](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework — `LocalValidatorFactoryBean`](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework — `SessionLocaleResolver`](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/i18n/SessionLocaleResolver.html)
- [Spring Framework — `LocaleChangeInterceptor`](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/i18n/LocaleChangeInterceptor.html)
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html)
- [Thymeleaf — Using Thymeleaf: Message Expressions](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html)
- [Jakarta Bean Validation 3.0](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)

**Summary:** Spring MVC uses `LocaleResolver` to determine the request language, `MessageSource` to retrieve text by code, and `BindingResult`/Thymeleaf to render localized form errors. Understand the difference between resolving `FieldError` codes and Bean Validation provider message interpolation; a complete multilingual application must also handle fallbacks, encoding, HTTP sessions, accessibility, and real tests in each locale.
