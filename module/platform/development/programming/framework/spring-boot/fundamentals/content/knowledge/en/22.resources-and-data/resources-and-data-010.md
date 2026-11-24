# MessageSource, Error Messages, and Locale Selection

A Spring Boot application may serve Vietnamese users, English-speaking users, or customers across many countries. If messages are hard-coded inside services, controllers, and validation annotations, the application quickly struggles whenever wording needs updates, languages change, or new translations are added.

For instance, the same business error "user not found" should be presented differently depending on the user:

~~~text
Vietnamese: Không tìm thấy người dùng có mã 42.
English:    User with ID 42 was not found.
~~~

Meanwhile, the **business error code** should stay constant, such as `USER_NOT_FOUND`. Error codes let systems, logs, and clients identify the error case programmatically; **translated messages** help humans understand and act on it.

Spring Framework provides **`MessageSource`** to resolve messages by code, arguments, and `Locale`. Spring Boot auto-configures message sources from `messages*.properties` files. Combined with Spring MVC and Bean Validation, this supports multilingual error messages without scattering `if/else` language branches through business logic.

This lesson in **Spring Boot Fundamentals → Resources and Data** focuses on practical questions:

- How does `MessageSource` work?
- Where do message files live and how are keys (message codes) structured?
- How is `Locale` resolved from `Accept-Language`, query parameters, or user preferences?
- How do exceptions or `@Valid` errors translate into localized API responses?
- How do you handle missing translations, placeholders, UTF-8 encoding, caching, and testing?
- How do you keep message translation from leaking coupling back into business logic?

## 1. Three Core Concepts: Message Code, Arguments, and Locale

A localized message typically has three parts.

**Message code** is a stable key representing meaning, for example:

~~~text
error.user.not-found
error.request.invalid
validation.user.email.invalid
notification.order.created
~~~

**Arguments** are dynamic values inserted into the sentence, such as a user ID, quantity, or object name.

**Locale** describes language and regional conventions, for example:

~~~text
vi        Vietnamese
vi-VN     Vietnamese in Vietnam
en        English
en-US     English in the United States
en-GB     English in the United Kingdom
~~~

Spring combines these pieces:

~~~text
Message code: error.user.not-found
Arguments:    [42]
Locale:       vi-VN
               |
               v
          MessageSource
               |
               v
"Không tìm thấy người dùng có mã 42."
~~~

Same code and arguments, but with `en-US`:

~~~text
"User with ID 42 was not found."
~~~

Thus, the service decides only **what happened**, while the presentation layer decides **how to phrase it in a given language**.

## 2. What Is MessageSource?

`MessageSource` is a Spring Framework interface in the package:

~~~java
org.springframework.context.MessageSource
~~~

Key methods:

~~~java
String getMessage(
        String code,
        Object[] args,
        String defaultMessage,
        Locale locale
);

String getMessage(
        String code,
        Object[] args,
        Locale locale
) throws NoSuchMessageException;

String getMessage(
        MessageSourceResolvable resolvable,
        Locale locale
) throws NoSuchMessageException;
~~~

Meaning:

| Parameter or type | Role |
|---|---|
| `code` | Lookup key for the message |
| `args` | Values substituted into placeholders like `{0}`, `{1}` |
| `defaultMessage` | Fallback sentence when the code is not found |
| `locale` | Language/region used to look up the translation |
| `MessageSourceResolvable` | Object encapsulating candidate codes, arguments, and default message |
| `NoSuchMessageException` | Exception thrown when no message is found and no valid fallback exists |

Usage example:

~~~java
String message = messageSource.getMessage(
        "error.user.not-found",
        new Object[] {42L},
        Locale.forLanguageTag("vi-VN")
);
~~~

If the bundle defines the matching entry, the output is:

~~~text
Không tìm thấy người dùng có mã 42.
~~~

### MessageSource is not a business data store

`MessageSource` does not replace databases, object storage, or general file storage. It is designed solely to **resolve messages by code and locale**, typically from resource bundles.

For example:

- "User was not found" is a fitting message.
- "Username must not be blank" is a fitting message.
- A million-row pricing table does not belong in a message bundle.
- A large JSON file holding an entire product catalog should not be treated as an i18n message bundle either.

An application may use both `ResourceLoader` to read data files and `MessageSource` to translate text. The two abstractions serve distinct purposes.

## 3. Minimal Configuration in Spring Boot

In a typical Spring Boot application, create the files under `src/main/resources`:

~~~text
src/
  main/
    java/
      com/example/DemoApplication.java
    resources/
      application.properties
      messages.properties
      messages_vi.properties
      messages_vi_VN.properties
~~~

Base file `messages.properties`:

~~~properties
error.user.not-found=User with ID {0} was not found.
error.request.invalid=The request contains invalid data.
error.common.unexpected=An unexpected error occurred.
validation.user.name.required=User name is required.
validation.user.email.required=Email is required.
validation.user.email.invalid=Email address is invalid.
notification.order.created=Order {0} was created successfully.
~~~

File `messages_vi.properties`:

~~~properties
error.user.not-found=Không tìm thấy người dùng có mã {0}.
error.request.invalid=Dữ liệu yêu cầu không hợp lệ.
error.common.unexpected=Đã xảy ra lỗi không mong muốn.
validation.user.name.required=Tên người dùng không được để trống.
validation.user.email.required=Email không được để trống.
validation.user.email.invalid=Địa chỉ email không hợp lệ.
notification.order.created=Đã tạo đơn hàng {0} thành công.
~~~

File `messages_vi_VN.properties` is optional, used when Vietnam-specific phrasing is needed:

~~~properties
notification.order.created=Đơn hàng số {0} đã được tạo thành công.
~~~

If you do not need to distinguish `vi` and `vi-VN`, using `messages_vi.properties` alone is completely fine.

### Why must messages.properties exist?

With Spring Boot's default message-source auto-configuration, **the base file `messages.properties` must be present** for default bundle discovery to activate as expected. Creating only `messages_vi.properties` without the base bundle can prevent auto-configuration from creating the message source bean as you expect.

Once an appropriate bundle exists, Spring Boot provides a `MessageSource` bean ready to inject into application beans without defining a manual `@Bean`.

If a project configures another basename, create the corresponding base bundle, such as `i18n/messages.properties`.

### Default vs. explicit configuration

In `application.properties`, you can declare:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Meaning:

- `spring.messages.basename=messages`: base bundle name is `messages`, without the `.properties` suffix.
- `spring.messages.encoding=UTF-8`: explicit encoding for reading message bundles.
- `spring.messages.fallback-to-system-locale=false`: avoids depending on the host OS's default locale during fallback.

Modern Spring Boot versions already pick sensible defaults for several of these properties. Declaring them explicitly makes the active configuration clear to readers.

## 4. How Does Spring Select Message Files by Locale?

Suppose the current request has locale `vi-VN` and the app includes three files:

~~~text
messages_vi_VN.properties
messages_vi.properties
messages.properties
~~~

When resolving a code, Spring searches from the most specific locale file down to the base bundle.

For example, `notification.order.created` exists in `messages_vi_VN.properties`, so the resolved sentence is:

~~~text
Đơn hàng số 108 đã được tạo thành công.
~~~

For `error.user.not-found`, which is absent from `messages_vi_VN.properties` yet present in `messages_vi.properties`, it resolves to:

~~~text
Không tìm thấy người dùng có mã 42.
~~~

If no matching translation exists in the Vietnamese files, the base bundle is used.

Illustrative diagram:

~~~text
Locale vi-VN, code error.user.not-found
                |
                v
messages_vi_VN.properties
     Code not found
                |
                v
messages_vi.properties
     Code found
                |
                v
"Không tìm thấy người dùng có mã 42."
~~~

Actual fallback resolution is also affected by settings like `fallback-to-system-locale`, default locale, or custom `MessageSource` bean configuration.

### The base bundle should be clear and consistent

If you decide `messages.properties` holds default English text, keep that convention consistent. That ensures the application always has clear messages even when a new translation lags behind.

If a product prioritizes Vietnamese, Vietnamese can be the base bundle content—just be explicit about your fallback policy and product default locale. **The base filename does not force its content to be English.**

## 5. Substituting Parameters with MessageFormat

In message bundles, `{0}`, `{1}`, ... are placeholders for arguments.

Example:

~~~properties
error.order.not-allowed=Cannot process order {0} in status {1}.
~~~

Call:

~~~java
String message = messageSource.getMessage(
        "error.order.not-allowed",
        new Object[] {1507L, "CANCELLED"},
        Locale.ENGLISH
);
~~~

Output:

~~~text
Cannot process order 1,507 in status CANCELLED.
~~~

Note: with `MessageFormat`, numeric formatting depends on locale; the output above illustrates English thousands separators. If an identifier must preserve exact digits without grouping commas, pass it as a `String` instead of a formatted number.

### Do not concatenate translated fragments to build sentences

Avoid:

~~~java
String message =
        messageSource.getMessage("error.prefix", null, locale)
        + userId
        + messageSource.getMessage("error.suffix", null, locale);
~~~

This assumes all languages share identical word order. Translators may need to place IDs or object names in a different position.

Better:

~~~properties
# messages.properties
error.user.not-found=User with ID {0} was not found.
~~~

~~~properties
# messages_vi.properties
error.user.not-found=Không tìm thấy người dùng có mã {0}.
~~~

Each translation controls where `{0}` appears in the sentence.

### Single quotes in MessageFormat

`MessageFormat` syntax treats single quotes as escape/quoting delimiters. Pay special attention to `'` in messages containing placeholders.

Example placing single quotes around an interpolated code:

~~~properties
error.code.invalid=Code ''{0}'' is invalid.
~~~

Processed by `MessageFormat`, doubled `''` renders a literal single quote. Writing `'{0}'` causes `{0}` to be treated as literal text rather than substituted with the argument.

Test messages containing apostrophes, braces, numbers, and dates. Avoid replacing `MessageFormat` with `String.replace(...)` if you want real i18n.

## 6. Injecting MessageSource into a Service

In Spring Boot, the standard way is constructor injection:

~~~java
package com.example.i18n;

import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.stereotype.Service;

@Service
public class LocalizedMessageService {

    private final MessageSource messageSource;

    public LocalizedMessageService(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String userNotFound(long userId, Locale locale) {
        return messageSource.getMessage(
                "error.user.not-found",
                new Object[] {userId},
                locale
        );
    }

    public String orderCreated(long orderId, Locale locale) {
        return messageSource.getMessage(
                "notification.order.created",
                new Object[] {orderId},
                locale
        );
    }
}
~~~

The service does not pick `messages_vi.properties` or `messages.properties` manually. It provides only the code, arguments, and locale.

### Why pass Locale as a method argument?

Passing `Locale` explicitly makes it obvious which language drives the output. This is especially helpful for:

- Background workers decoupled from HTTP requests.
- Emails sent after an HTTP request has completed.
- Scheduled jobs generating notifications for many accounts.
- Tests targeting a fixed locale.
- Actions sending a notification to a recipient whose language differs from the actor's.

Deep business services should not implicitly depend on HTTP headers. Application layers can pass a verified `Locale` or preference down to message-rendering layers.

## 7. What Is Locale, and What Is It Not?

`java.util.Locale` captures language and country/region details, typically constructed with:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale englishUS = Locale.forLanguageTag("en-US");
Locale englishUK = Locale.forLanguageTag("en-GB");
~~~

You can inspect:

~~~java
System.out.println(vietnamese.getLanguage()); // vi
System.out.println(vietnamese.getCountry());  // VN
~~~

`Locale` influences:

- Message language resolved by `MessageSource`.
- Number and date formatting rules.
- Regional currency or presentation conventions.
- Selection of specific bundles like `messages_vi_VN.properties`.

**Locale is not a time zone.** A Vietnamese speaker may live in Europe; an English-configured user may want Vietnam time. In real applications, language, region, time zone, and currency preference are separate concepts even when configured together.

**Locale is also not an authorization credential.** Never use `Accept-Language` or a bundle name to make access-control decisions or restrict which data a caller may view.

## 8. Where Does Spring MVC Get Locale?

In a Spring MVC application, a `LocaleResolver` determines the request's locale. Under standard MVC configuration, if no custom resolver is defined, Spring resolves locale from the `Accept-Language` header.

HTTP example:

~~~http
GET /api/users/42 HTTP/1.1
Host: localhost:8080
Accept-Language: vi-VN,vi;q=0.9,en;q=0.8
~~~

This header expresses the client's language preference order:

- `vi-VN` highest priority.
- `vi` next priority.
- `en` as fallback.

Inside a Spring MVC controller, you can accept `Locale` directly as a parameter:

~~~java
@GetMapping("/greeting")
public String greeting(Locale locale) {
    return messageSource.getMessage(
            "greeting.hello",
            null,
            locale
    );
}
~~~

Add keys:

~~~properties
# messages.properties
greeting.hello=Hello!
~~~

~~~properties
# messages_vi.properties
greeting.hello=Xin chào!
~~~

Sample requests:

~~~bash
curl -H "Accept-Language: vi-VN" \
     http://localhost:8080/greeting
~~~

Expected output:

~~~text
Xin chào!
~~~

If sending:

~~~bash
curl -H "Accept-Language: en-US" \
     http://localhost:8080/greeting
~~~

Expected output is:

~~~text
Hello!
~~~

Remember that **`Locale` is resolved by Spring MVC from the request**—the controller does not manually parse headers in these examples.

### Why not parse the raw header String manually?

This only retrieves the raw header:

~~~java
@RequestHeader("Accept-Language") String rawHeader
~~~

Headers can include multiple language ranges and `q` quality weights. Splitting by comma and grabbing the first entry ignores full locale matching, supported-locale filtering, and fallback rules.

Accepting a `Locale` parameter backed by a proper `LocaleResolver` is cleaner and more consistent.

## 9. AcceptHeaderLocaleResolver and Stateless Applications

`AcceptHeaderLocaleResolver` inspects `Accept-Language` to determine locale. It fits stateless APIs where clients explicitly indicate their desired language per request.

Typical flow:

~~~text
Mobile App / Browser
    |
    | Accept-Language: vi-VN
    v
Spring MVC
    |
    v
LocaleResolver -> Locale vi-VN
    |
    v
Controller / ExceptionHandler
    |
    v
MessageSource
    |
    v
HTTP response with Vietnamese message
~~~

Advantages:

- No server-side session state needed for language.
- Every request can specify its own language.
- Clean fit when diverse clients share one backend.

Limitations:

- The header is a **client-supplied preference**, not authenticated identity data.
- If the app supports only a subset of languages, configure supported locales and fallback explicitly.
- When authenticated users save a language preference in their profile, balance saved preferences against per-request headers.

### Configuring supported locales

Explicit resolver configuration example:

~~~java
package com.example.i18n;

import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration(proxyBeanMethods = false)
public class LocaleConfiguration {

    @Bean
    LocaleResolver localeResolver() {
        AcceptHeaderLocaleResolver resolver =
                new AcceptHeaderLocaleResolver();

        resolver.setSupportedLocales(List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.forLanguageTag("en-US")
        ));

        resolver.setDefaultLocale(Locale.forLanguageTag("vi-VN"));
        return resolver;
    }
}
~~~

`setSupportedLocales(...)` restricts locales the app intends to support, and `setDefaultLocale(...)` defines the fallback.

**Note:** understand how the resolver matches language and country tags. If supported locales contain only `en-US`, do not assume `en-GB` automatically maps to `en-US` by guesswork. Test the exact language tags your product permits.

### Can you switch language with ?lang=vi on AcceptHeaderLocaleResolver?

Do not expect that to work. `AcceptHeaderLocaleResolver` reads the request header; it is not designed to persist server-side locale changes via `setLocale(...)`.

If users must switch language with a query parameter and persist that choice across subsequent requests, use a stateful resolver such as session or cookie, or build a custom preference mechanism. Never pair `LocaleChangeInterceptor` with a resolver that rejects `setLocale` and expect it to work.

## 10. Selecting Language via Query Parameter, Session, or Cookie

An HTML-rendered website might let users switch languages from the UI:

~~~text
https://example.org/home?lang=vi-VN
https://example.org/home?lang=en-US
~~~

In Spring MVC, you can use `SessionLocaleResolver` and `LocaleChangeInterceptor`.

Example configuration:

~~~java
package com.example.i18n;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration(proxyBeanMethods = false)
public class LanguageSelectionConfiguration
        implements WebMvcConfigurer {

    @Bean
    LocaleResolver localeResolver() {
        SessionLocaleResolver resolver = new SessionLocaleResolver();
        resolver.setDefaultLocale(Locale.forLanguageTag("vi-VN"));
        return resolver;
    }

    @Bean
    LocaleChangeInterceptor localeChangeInterceptor() {
        LocaleChangeInterceptor interceptor =
                new LocaleChangeInterceptor();
        interceptor.setParamName("lang");
        return interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(localeChangeInterceptor());
    }
}
~~~

How it works:

1. Request arrives with `?lang=en-US`.
2. Interceptor reads the `lang` parameter.
3. `SessionLocaleResolver` stores the selected locale in the HTTP session.
4. Subsequent requests in that session reuse the selected locale.
5. `MessageSource` resolves matching translations.

This is **an alternative** to the `Accept-Language` resolver in section 9. Never declare two `LocaleResolver` beans with the same name in one application expecting Spring to guess which one to use.

### Are sessions and cookies right for every API?

Not necessarily. Stateless APIs typically prefer headers, explicit locale parameters, or saved preferences from the authenticated user's profile. Traditional server-rendered sites with sessions or cookies fit `SessionLocaleResolver` or `CookieLocaleResolver` better.

When using cookies, plan expiration, domain, cookie security flags, and unauthenticated users. When using sessions, account for distributed session replication when scaling horizontally.

**How Locale is determined is an application design choice**, not inherent to `MessageSource`.

## 11. When to Use LocaleContextHolder?

Spring provides `LocaleContextHolder` to access the locale bound to the current thread/context:

~~~java
import java.util.Locale;
import org.springframework.context.i18n.LocaleContextHolder;

Locale locale = LocaleContextHolder.getLocale();
~~~

Inside Spring MVC request processing, the framework binds the request locale context so downstream code can access it.

Example:

~~~java
String text = messageSource.getMessage(
        "error.request.invalid",
        null,
        LocaleContextHolder.getLocale()
);
~~~

However, keep an important limitation in mind: `LocaleContextHolder` uses thread-bound context and **does not automatically propagate across executors, `@Async`, schedulers, or arbitrary async pipelines**.

If a background worker emails a user after the HTTP request finished:

~~~java
public void sendEmail(long userId, Locale recipientLocale) {
    String subject = messageSource.getMessage(
            "notification.order.created",
            new Object[] {userId},
            recipientLocale
    );

    // Send email with subject via an appropriate email service.
}
~~~

Passing the recipient's locale explicitly to the task is much easier to reason about than grabbing a locale on a background thread. Without a request context, `LocaleContextHolder.getLocale()` can fall back to the JVM default or an unexpected context.

Never store a request's locale in a shared static variable; concurrent requests would overwrite each other.

## 12. Designing Error Responses: Keep Codes Stable, Translate Messages

For REST APIs, distinguish:

- **HTTP status**: `400`, `404`, `409`, or `500`.
- **Business error code**: e.g., `USER_NOT_FOUND`, `VALIDATION_ERROR`.
- **Localized message**: human-readable text for the end user.
- **Details**: field error list or extra structured info if needed.

Vietnamese response example:

~~~json
{
  "code": "USER_NOT_FOUND",
  "message": "Không tìm thấy người dùng có mã 42.",
  "details": []
}
~~~

English response example:

~~~json
{
  "code": "USER_NOT_FOUND",
  "message": "User with ID 42 was not found.",
  "details": []
}
~~~

In both responses:

- HTTP status stays `404 Not Found`.
- `code` stays `USER_NOT_FOUND`.
- Only `message` changes by locale.

### Why never use translated text as an error code?

A frontend might redirect to a re-registration screen upon receiving `ACCOUNT_LOCKED`. If it branches on the string "Tài khoản đã bị khóa", tweaking wording in a translation file can silently break frontend logic.

Stable error codes belong to programmatic control and log aggregation. Translated text belongs to display. Never merge the two.

Moreover, internal exception messages are often unsafe to return verbatim to clients. Technical messages can expose connection strings, file paths, table names, or sensitive details; always map them to controlled public messages.

## 13. Spring Boot REST Example: Localizing Not-Found Errors

Let's build a small app structured as:

~~~text
src/main/java/com/example/
  DemoApplication.java
  user/
    UserController.java
    UserNotFoundException.java
  web/
    ApiExceptionHandler.java

src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
~~~

### 13.1. Define a business exception

`UserNotFoundException.java`:

~~~java
package com.example.user;

public class UserNotFoundException extends RuntimeException {

    private final long userId;

    public UserNotFoundException(long userId) {
        super("User not found");
        this.userId = userId;
    }

    public long getUserId() {
        return userId;
    }
}
~~~

The exception holds structured data `userId`. Here the English constructor message is purely for technical logs; the HTTP handler constructs the client-facing message via `MessageSource`.

Larger systems often define a base exception containing an `errorCode` and argument array so individual exceptions are not coupled to translations.

### 13.2. Illustrative controller

`UserController.java`:

~~~java
package com.example.user;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
public class UserController {

    @GetMapping("/{id}")
    public String findUser(@PathVariable long id) {
        // Illustrate the not-found case.
        throw new UserNotFoundException(id);
    }
}
~~~

The controller deliberately throws to illustrate error handling without a database query.

### 13.3. Exception handler translating the message

`ApiExceptionHandler.java`:

~~~java
package com.example.web;

import java.util.List;
import java.util.Locale;

import com.example.user.UserNotFoundException;
import org.springframework.context.MessageSource;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    private final MessageSource messageSource;

    public ApiExceptionHandler(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @ExceptionHandler(UserNotFoundException.class)
    public ResponseEntity<ApiError> userNotFound(
            UserNotFoundException exception,
            Locale locale
    ) {
        String message = messageSource.getMessage(
                "error.user.not-found",
                new Object[] {exception.getUserId()},
                locale
        );

        ApiError body = new ApiError(
                "USER_NOT_FOUND",
                message,
                List.of()
        );

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(body);
    }

    public record ApiError(
            String code,
            String message,
            List<?> details
    ) {
    }
}
~~~

Spring MVC supplies the current `Locale` to the exception handler. `MessageSource` resolves the matching bundle for that locale. `List<?>` is used here because this response carries no field-level details; the validation section introduces a dedicated detail type.

This example targets Spring Boot with Spring MVC and Jackson. For Spring WebFlux, locale context and handler APIs differ; never copy MVC configuration blindly to WebFlux.

### 13.4. Testing with curl

Vietnamese request:

~~~bash
curl -i \
     -H "Accept-Language: vi-VN" \
     http://localhost:8080/api/users/42
~~~

Illustrative response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"USER_NOT_FOUND","message":"Không tìm thấy người dùng có mã 42.","details":[]}
~~~

English request:

~~~bash
curl -i \
     -H "Accept-Language: en-US" \
     http://localhost:8080/api/users/42
~~~

Illustrative response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"USER_NOT_FOUND","message":"User with ID 42 was not found.","details":[]}
~~~

Only `message` changes, while HTTP status and business error code stay identical.

## 14. Bean Validation and Multilingual Error Messages

A large share of REST API error messages comes from input validation.

Examples:

- Name must not be blank.
- Email format is invalid.
- Age must meet a minimum threshold.
- Quantity must fall within a range.

In Spring Boot 3.x, Bean Validation uses the `jakarta.validation` namespace. Projects need the corresponding dependency, e.g., in Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

In Gradle Groovy DSL:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

If Spring MVC is not yet included, REST apps also need an appropriate web starter such as `spring-boot-starter-web`.

### 14.1. Define the request DTO

`CreateUserRequest.java`:

~~~java
package com.example.user;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record CreateUserRequest(

        @NotBlank(message = "{validation.user.name.required}")
        String name,

        @NotBlank(message = "{validation.user.email.required}")
        @Email(message = "{validation.user.email.invalid}")
        String email
) {
}
~~~

The syntax `message = "{validation.user.name.required}"` tells Bean Validation to resolve a message template key instead of a hard-coded string inside the annotation.

Keys defined in the bundles:

~~~properties
# messages.properties
validation.user.name.required=User name is required.
validation.user.email.required=Email is required.
validation.user.email.invalid=Email address is invalid.
~~~

~~~properties
# messages_vi.properties
validation.user.name.required=Tên người dùng không được để trống.
validation.user.email.required=Email không được để trống.
validation.user.email.invalid=Địa chỉ email không hợp lệ.
~~~

With standard Spring Boot validation auto-configuration, message interpolation integrates with the application's `MessageSource`. If a project declares a custom validator or message interpolator manually, make sure it connects to the right message source.

### 14.2. Trigger validation in the controller

~~~java
package com.example.user;

import jakarta.validation.Valid;

import java.util.Map;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
public class UserCreationController {

    @PostMapping
    public Map<String, String> create(
            @Valid @RequestBody CreateUserRequest request
    ) {
        // Simple example: not persisted to a database yet.
        return Map.of("name", request.name());
    }
}
~~~

In Spring MVC, when `@Valid` detects invalid data in the request body, the framework throws `MethodArgumentNotValidException` before the controller finishes executing.

Handling that exception in `@RestControllerAdvice` gives consistent error responses.

## 15. Translating Field-Level Validation Errors in @RestControllerAdvice

A validation failure needs more than "Invalid request"; it should also identify which fields failed.

Response schema example:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ.",
  "details": [
    {"field": "name", "message": "Tên người dùng không được để trống."},
    {"field": "email", "message": "Địa chỉ email không hợp lệ."}
  ]
}
~~~

In Spring MVC, `FieldError` extends `DefaultMessageSourceResolvable` and carries binding/validation message codes and arguments.

Hence you can call the overload:

~~~java
messageSource.getMessage(fieldError, locale)
~~~

### Exception handler example

In a real app, add this handler to an existing `@RestControllerAdvice` or combine it with section 13's handler. For standalone illustration:

~~~java
package com.example.web;

import java.util.List;
import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationExceptionHandler {

    private final MessageSource messageSource;

    public ValidationExceptionHandler(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalidRequest(
            MethodArgumentNotValidException exception,
            Locale locale
    ) {
        String summary = messageSource.getMessage(
                "error.request.invalid",
                null,
                locale
        );

        List<FieldIssue> details = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        messageSource.getMessage(error, locale)
                ))
                .toList();

        ApiError body = new ApiError(
                "VALIDATION_ERROR",
                summary,
                details
        );

        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(body);
    }

    public record FieldIssue(
            String field,
            String message
    ) {
    }

    public record ApiError(
            String code,
            String message,
            List<FieldIssue> details
    ) {
    }
}
~~~

Here:

1. `error.request.invalid` builds the summary message.
2. `FieldError.getField()` provides the failing request field name.
3. `messageSource.getMessage(error, locale)` resolves the field error's message codes and falls back to its default message if needed.
4. `ResponseEntity` returns `400 Bad Request`.
5. The `VALIDATION_ERROR` code stays stable across locales.

When assembling examples into a real project, share a single response class and `@RestControllerAdvice`. The two `ApiError` records sit in separate handler classes here so their types need not match; production APIs should unify the schema.

### Testing with curl

~~~bash
curl -i -X POST \
     -H "Content-Type: application/json" \
     -H "Accept-Language: vi-VN" \
     -d '{"name":"","email":"not-an-email"}' \
     http://localhost:8080/api/users
~~~

Illustrative response:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ.",
  "details": [
    {
      "field": "name",
      "message": "Tên người dùng không được để trống."
    },
    {
      "field": "email",
      "message": "Địa chỉ email không hợp lệ."
    }
  ]
}
~~~

The order of items in `details` depends on validation execution and error aggregation; clients should never depend on an implicit ordering of field errors.

**Note:** Bean Validation also has its own message interpolation. When an annotation specifies a template and the validator interpolates with the right locale, `FieldError.getDefaultMessage()` already contains the translated text. Calling `getMessage(error, locale)` leverages Spring's code hierarchy; when customizing validators, check how both interact to avoid double translation or unexpected fallbacks.

## 16. Should You Call getDefaultMessage() Directly?

Given a `FieldError`, you might write:

~~~java
String text = fieldError.getDefaultMessage();
~~~

This can already return a translated sentence if Bean Validation performed interpolation.

Still, understand the difference:

| Usage | Meaning |
|---|---|
| `fieldError.getDefaultMessage()` | Gets the default message attached to the error by binding/validation |
| `messageSource.getMessage(fieldError, locale)` | Attempts to resolve the error's message codes via `MessageSource`, then falls back |
| `messageSource.getMessage("error.request.invalid", null, locale)` | Looks up an application message by explicit code |

If your team wants fine-grained code resolution order across field/type/constraint combinations, `MessageSourceResolvable` helps. If Bean Validation's interpolated message is already sufficient, `getDefaultMessage()` works cleanly in many cases.

What matters is picking **one consistent strategy**, rather than randomly mixing pre-interpolated defaults and ad-hoc code overrides.

### Different kinds of validation errors

Not every request error goes through `MethodArgumentNotValidException`:

- `@RequestBody` validation typically raises `MethodArgumentNotValidException`.
- Form object binding/validation can surface via `BindingResult` and related exceptions.
- Direct method parameter constraints can follow a different path depending on Spring version and method-validation setup.
- Malformed JSON can throw `HttpMessageNotReadableException` before Bean Validation ever runs.

A complete error handler explicitly defines every failure path you want mapped to public messages. `MessageSource` only translates messages; it does not decide which exception maps to which HTTP status.

## 17. Missing Messages: defaultMessage, Exceptions, and Fallbacks

A common bug is looking up an undeclared message code.

Example:

~~~java
messageSource.getMessage(
        "error.payment.unknown",
        null,
        Locale.forLanguageTag("vi-VN")
);
~~~

If the code is absent from all matching bundles and no fallback is supplied, the overload without `defaultMessage` throws `NoSuchMessageException`.

### Supplying an explicit default message

~~~java
String text = messageSource.getMessage(
        "error.payment.unknown",
        null,
        "Unable to process payment.",
        Locale.forLanguageTag("vi-VN")
);
~~~

This keeps features running when a translation is missing. However, scattering ad-hoc fallback strings everywhere makes copy hard to manage and hides missing translations.

### Using the code itself as the default message

Spring Boot offers an option:

~~~properties
spring.messages.use-code-as-default-message=true
~~~

When enabled in compatible configs, the key itself is returned instead of failing on missing messages.

For example, users might see:

~~~text
error.payment.unknown
~~~

This helps during development to spot untranslated keys, though it is usually poor UX for end users. Establish clear team conventions for when a missing translation should fail tests versus fall back gracefully.

### Practical fallback strategy

A straightforward strategy:

1. The base bundle contains every essential public key.
2. Locale-specific bundles override translated sentences.
3. Automated tests or content checks catch missing keys.
4. Log/alert on missing keys without exposing sensitive arguments.
5. Reserve generic fallback text only for technical errors never meant to reveal details to end users.

Having a bundle file on disk does not guarantee every code is defined inside it.

## 18. Organizing Multiple Bundles with basename

Larger applications can split translations by group, such as general UI messages and error messages:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  errors.properties
  errors_vi.properties
~~~

In `application.properties`:

~~~properties
spring.messages.basename=messages,errors
spring.messages.encoding=UTF-8
~~~

`MessageSource` searches codes across all declared basenames. Splitting bundles lets separate teams maintain different sets of messages independently.

Example:

~~~properties
# messages.properties
button.save=Save
notification.saved=Saved successfully.
~~~

~~~properties
# errors.properties
error.user.not-found=User with ID {0} was not found.
error.request.invalid=The request contains invalid data.
~~~

Avoid declaring **the same key with two different meanings** across bundles. Basename order and resolution rules can pick a different bundle than you intended.

### Message key naming conventions

A helpful convention:

~~~text
error.<domain>.<condition>
validation.<entity>.<field>.<rule>
notification.<domain>.<action>
label.<screen>.<name>
~~~

Examples:

~~~text
error.user.not-found
error.order.invalid-state
validation.user.email.invalid
notification.invoice.sent
label.profile.display-name
~~~

Keys should express **stable semantic meaning**, not literal English or Vietnamese wording. Updating phrasing without changing meaning should not require renaming keys.

## 19. Encoding and Vietnamese Characters

Translation files containing Vietnamese must be saved with the right encoding. In modern projects, **UTF-8** is the right choice.

Example:

~~~properties
greeting.hello=Xin chào!
error.user.not-found=Không tìm thấy người dùng có mã {0}.
~~~

And:

~~~properties
spring.messages.encoding=UTF-8
~~~

If an editor saves the file in another encoding while the application reads UTF-8, messages turn into garbled characters:

~~~text
KhÃ´ng tÃ¬m tháº¥y ...
~~~

Steps to enforce:

- Ensure `.properties` files are actually saved as UTF-8.
- Ensure `MessageSource` config uses the matching encoding.
- Add tests asserting Vietnamese strings after loading.
- Never patch encoding bugs by string-replacing broken characters in outputs.
- Distinguish source-bundle encoding bugs from HTTP response encoding bugs.

In modern Java/Spring, avoid blindly following outdated advice claiming all `.properties` files must escape Unicode with `\uXXXX`. Bundle loading and encoding depend on the implementation; configure and test explicitly.

## 20. When Translations Load and Update

Message bundles packaged inside an executable JAR are **application resources**. With Spring Boot auto-configuration and `ResourceBundleMessageSource`, these files ship alongside the application release.

If you edit `src/main/resources/messages_vi.properties` in source code while running an older JAR, the change does not appear in the running process automatically. You normally rebuild and redeploy the artifact with the updated bundle.

Spring Boot provides a cache-duration property:

~~~properties
spring.messages.cache-duration=10s
~~~

However, **cache duration does not turn an immutable resource inside a JAR into runtime-editable data**. It only governs how the underlying implementation caches resolved messages.

In production, shipping bundles inside versioned artifacts makes releases and rollbacks safer than editing files directly on live servers.

## 21. When Translations Must Live Outside the JAR: ReloadableResourceBundleMessageSource

If an application specifically requires loading translation files from a runtime-updatable directory, Spring Framework provides `ReloadableResourceBundleMessageSource`.

Explicit bean configuration example:

~~~java
package com.example.i18n;

import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.ReloadableResourceBundleMessageSource;

@Configuration(proxyBeanMethods = false)
public class ExternalMessagesConfiguration {

    @Bean(name = "messageSource")
    MessageSource messageSource() {
        ReloadableResourceBundleMessageSource source =
                new ReloadableResourceBundleMessageSource();

        source.setBasenames("file:/opt/app/i18n/messages");
        source.setDefaultEncoding("UTF-8");
        source.setCacheSeconds(60);
        source.setFallbackToSystemLocale(false);

        return source;
    }
}
~~~

If the directory contains:

~~~text
/opt/app/i18n/messages.properties
/opt/app/i18n/messages_vi.properties
/opt/app/i18n/messages_en.properties
~~~

Spring loads the external files by basename. Refreshing depends on cache settings, file availability, and filesystem mechanics.

Important notes:

- Declaring a bean named `messageSource` replaces or suppresses Boot's default auto-configured `MessageSource` bean.
- Files must exist and be readable **on the process/container filesystem**, not on the developer machine.
- Never update files while partially written; use atomic deployment replacements.
- Restrict write permissions on the i18n directory; translations are user-facing output.
- Filesystem caching and modification detection vary across operating systems and deployment environments.

Only adopt reloadable external bundles when operations truly demand it. For most apps, JAR-packaged bundles are simpler and less error-prone.

## 22. Where Should Business Error Messages Be Translated?

Two common designs exist.

### Approach A: translate directly inside the business service

~~~java
public String registerUser(Locale locale) {
    if (userAlreadyExists()) {
        return messageSource.getMessage(
                "error.user.duplicate",
                null,
                locale
        );
    }

    return "OK";
}
~~~

Simple for tiny apps, yet the business service becomes coupled to locales and presentation phrasing.

### Approach B: service throws coded errors; HTTP/notification layer translates

~~~text
Domain Service
    |
    +-- detects USER_DUPLICATE
              |
              v
      Domain Exception
        code + args
              |
              v
        API Adapter
              |
              +-- HTTP status
              +-- MessageSource + Locale
              |
              v
      { code, message, details }
~~~

Structured exception example:

~~~java
public class BusinessException extends RuntimeException {

    private final String code;
    private final Object[] arguments;

    public BusinessException(String code, Object... arguments) {
        super(code);
        this.code = code;
        this.arguments = arguments.clone();
    }

    public String getCode() {
        return code;
    }

    public Object[] getArguments() {
        return arguments.clone();
    }
}
~~~

Service:

~~~java
if (userAlreadyExists()) {
    throw new BusinessException(
            "error.user.duplicate",
            requestedEmail
    );
}
~~~

The HTTP adapter uses `MessageSource` to translate the code for the request locale. An email worker translates the exact same code for the recipient's locale. Business logic stays completely unaware of user language.

**Protect data arguments.** `requestedEmail` may be personal data; avoid blindly echoing it into every public message or log.

In larger APIs, separate a stable client-facing `publicErrorCode` from a `messageCode` used for translation. Not every technical exception should map straight to a public message code.

## 23. Selecting Language for Notifications and Emails

REST requests usually carry `Accept-Language`. Emails or push notifications sent asynchronously lack an active HTTP request.

Suppose user A acts in English, while recipient B prefers Vietnamese. An email to B should use **B's preferred language**, not inherit A's locale.

Simple pattern:

~~~java
public void notifyOrderCreated(
        long orderId,
        Locale recipientLocale
) {
    String text = messageSource.getMessage(
            "notification.order.created",
            new Object[] {orderId},
            recipientLocale
    );

    notificationGateway.send(text);
}
~~~

`notificationGateway` is an illustrative application-defined dependency.

In production systems, resolve locale via a clear policy:

1. Recipient's saved profile preference, if valid.
2. Language configured on the tenant/customer group, if defined.
3. Product default language when no preference exists.
4. For direct interactive requests: honor `Accept-Language` where appropriate.

Do not rigidly infer language from IP geolocation. Users in one country often prefer another language.

## 24. Formatting Numbers, Dates, and Units in Messages

Language selection sometimes interacts with formatting conventions.

Example:

~~~properties
notification.items.count=You have {0} items.
~~~

With `MessageFormat`, numeric, date, or other typed arguments can be formatted per locale.

Illustrative message format:

~~~properties
report.generated-at=Report generated at {0,date,short}.
~~~

Passing `java.util.Date`:

~~~java
String text = messageSource.getMessage(
        "report.generated-at",
        new Object[] {new java.util.Date()},
        Locale.US
);
~~~

Date separators and ordering vary by locale.

### Do not confuse formatting with business semantics

Transaction currency must never change just because `Accept-Language` switched from `vi-VN` to `en-US`. Currency codes, amounts, and accounting rules are dictated by business data.

Similarly, handle time zones explicitly when formatting timestamps. `Locale` does not provide each user's time zone.

For complex grammatical pluralization rules, traditional `MessageFormat` has limitations. Do not assume adding one `{0}` placeholder handles every language cleanly. Systems requiring rich pluralization should consider specialized i18n tooling and professional localization workflows.

## 25. Testing MessageSource Without an HTTP Server

You can test message bundles directly once the application initializes `MessageSource`.

Spring Boot Test + JUnit 5 example:

~~~java
package com.example.i18n;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.MessageSource;

@SpringBootTest
class MessageSourceTest {

    @Autowired
    MessageSource messageSource;

    @Test
    void resolvesVietnameseMessage() {
        String actual = messageSource.getMessage(
                "error.user.not-found",
                new Object[] {"42"},
                Locale.forLanguageTag("vi-VN")
        );

        assertEquals(
                "Không tìm thấy người dùng có mã 42.",
                actual
        );
    }

    @Test
    void resolvesEnglishMessage() {
        String actual = messageSource.getMessage(
                "error.user.not-found",
                new Object[] {"42"},
                Locale.US
        );

        assertEquals(
                "User with ID 42 was not found.",
                actual
        );
    }
}
~~~

Here `"42"` is passed as a String to avoid locale-dependent number formatting in assertions.

Tests catch:

- Missing keys in bundles.
- Vietnamese encoding corruption.
- Unsubstituted placeholders.
- Misconfigured fallbacks or missing `MessageSource` bean.
- Unexpected differences between `vi-VN` and `en-US`.

Never assert only that `getMessage(...)` returns a non-empty string, because with `use-code-as-default-message` enabled, that string could just be an untranslated key.

## 26. Testing Locale at the Spring MVC Layer

For section 13's REST API, use `MockMvc` to verify `Accept-Language` drives the HTTP response.

Example:

~~~java
package com.example.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LocalizedApiTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsVietnameseError() throws Exception {
        mvc.perform(get("/api/users/42")
                .header("Accept-Language", "vi-VN"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value("USER_NOT_FOUND"))
            .andExpect(jsonPath("$.message").value(
                    "Không tìm thấy người dùng có mã 42."
            ));
    }

    @Test
    void returnsEnglishError() throws Exception {
        mvc.perform(get("/api/users/42")
                .header("Accept-Language", "en-US"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value("USER_NOT_FOUND"))
            .andExpect(jsonPath("$.message").value(
                    "User with ID 42 was not found."
            ));
    }
}
~~~

This example targets Spring Boot 3.x and Spring MVC. In newer library versions, some test packages or annotations may differ; use variants compatible with your project's version.

These tests verify two independent behaviors:

1. `MessageSource` resolves codes and locales accurately.
2. Spring MVC turns `Accept-Language` into the `Locale` consumed by the exception handler.

Testing `MessageSource` alone does not verify end-to-end HTTP locale handling.

## 27. Common Issues and How to Investigate Them

| Symptom | Possible cause | What to check |
|---|---|---|
| `NoSuchMessageException` | Missing key or no fallback | Check basename, key name, and locale files |
| Returns raw `error.user.not-found` | `use-code-as-default-message` enabled or missing translation | Inspect bundles and fallback config |
| Vietnamese diacritics corrupted | Wrong file encoding or wrong decoder | Verify UTF-8 in source files and `MessageSource` config |
| `Accept-Language` header has no effect | Controller/handler uses fixed locale or wrong resolver | Check `LocaleResolver` and injected `Locale` |
| `?lang=vi` does nothing | Resolver uses `Accept-Language` and ignores `setLocale` | Use session/cookie resolver or send header |
| Validation messages stay English | `MessageSource`/validator not wired or missing key | Check annotation template and validation config |
| `{0}` prints literally | Missing args, syntax error, or unescaped quotes | Check overload, bundle, and `MessageFormat` quoting |
| Right locale, weird number format | `MessageFormat` formats numbers by region | Pass identifiers as Strings to preserve raw digits |
| Works in IDE, JAR lacks bundle | File excluded from classpath packaging | Inspect `src/main/resources` and packaged artifact |
| Updated translation, running app unchanged | Old bundle inside JAR or cached | Redeploy or use reloadable bundle if required |
| Background job uses wrong language | Background thread has no HTTP locale context | Pass recipient `Locale` explicitly |
| API leaks technical exception text | Returning raw `exception.getMessage()` | Map errors to stable codes and public messages |

### Layer-by-layer diagnostic checklist

**Resource layer:** Are bundle files named properly and packaged on the classpath?

**MessageSource layer:** Does the `messageSource` bean exist? What are its basename, encoding, and fallback settings?

**Locale layer:** What `Accept-Language` header was sent? Which `LocaleResolver` is active? Which `Locale` did the handler receive?

**Lookup layer:** Does the code match? Are arguments in the right order and types?

**API layer:** Does the exception handler translate via `MessageSource` or return raw exception messages?

**Validation layer:** Is Bean Validation interpolating templates through the expected message source?

Separating these layers makes debugging systematic instead of randomly editing `messages_vi.properties` or renaming message keys.

## 28. Security and Operational Considerations

### Never translate or return sensitive technical details publicly

A database exception can expose SQL, schema names, or internal endpoints. Passing raw `exception.getMessage()` to clients creates information disclosure risks regardless of `MessageSource`.

In APIs:

- Return a defined **public error code**.
- Serve localized public phrasing revealing zero implementation details.
- Record technical specifics in access-controlled server logs.
- Correlate logs via request ID or trace ID for investigation.
- Never pass passwords, access tokens, or unnecessary personal data into message arguments.

### Keep machine-consumed stable values untranslated

Machine-parsed tokens must remain invariant:

~~~text
USER_NOT_FOUND
VALIDATION_ERROR
payment.status=CANCELLED
HTTP 404
traceId=...
~~~

Keep them in dedicated `code` or `details` fields. Translating them breaks client integrations.

### Translations are product content

Bundles often hold copy maintained by content or localization teams. As apps grow, establish:

- Review processes for user-facing wording.
- Automated checks for missing or duplicate keys.
- Checks for placeholder parity across locales.
- UI testing for shorter and longer translated strings.
- Bundle versioning aligned with application releases.
- Clear documentation of supported and fallback locales.

Do not treat translations as arbitrary strings only developers may touch.

## 29. Practice Exercise: Bilingual Error API

### Exercise 1 — Create base and translated bundles

Create:

~~~text
src/main/resources/messages.properties
src/main/resources/messages_vi.properties
~~~

Add keys:

~~~properties
# messages.properties
error.product.not-found=Product {0} was not found.
~~~

~~~properties
# messages_vi.properties
error.product.not-found=Không tìm thấy sản phẩm {0}.
~~~

Inject `MessageSource` and call it with `Locale.ENGLISH` and `Locale.forLanguageTag("vi-VN")`.

**Goal:** produce two localized messages from the same code and argument.

### Exercise 2 — Use Accept-Language in a controller

Add an endpoint:

~~~java
@GetMapping("/api/demo/product-error/{id}")
public String productError(
        @PathVariable String id,
        Locale locale
) {
    return messageSource.getMessage(
            "error.product.not-found",
            new Object[] {id},
            locale
    );
}
~~~

Test with:

~~~bash
curl -H "Accept-Language: vi-VN" \
     http://localhost:8080/api/demo/product-error/P100
~~~

And:

~~~bash
curl -H "Accept-Language: en-US" \
     http://localhost:8080/api/demo/product-error/P100
~~~

**Goal:** confirm the request `Locale` flows into `MessageSource`. The demo endpoint returns a plain String; real APIs should return structured error responses with proper status and error codes.

### Exercise 3 — Test a missing key

Call:

~~~java
messageSource.getMessage(
        "error.unknown.code",
        null,
        Locale.US
);
~~~

Observe missing-message behavior. Then test the overload accepting `defaultMessage`.

**Goal:** understand the difference between fallback defaults and `NoSuchMessageException`.

### Exercise 4 — Test Bean Validation errors

Add `@NotBlank(message = "{validation.user.name.required}")` to a DTO, then submit an empty `name` with two different headers. Trace whether the message is interpolated at the Bean Validation layer or resolved via Spring `MessageSourceResolvable`.

**Goal:** return localized field-level messages, not only generic summary messages.

### Exercise 5 — Switch language via session

Configure `SessionLocaleResolver` and `LocaleChangeInterceptor`, then send:

~~~text
GET /greeting?lang=vi-VN
GET /greeting?lang=en-US
~~~

Verify subsequent requests within the same HTTP session.

**Goal:** contrast header-driven per-request locale with session-persisted locale.

### Exercise 6 — Background notifications

Simulate a job emailing two recipients with different locales. Pass each recipient's locale explicitly into the message builder instead of reading `LocaleContextHolder`.

**Goal:** prevent mixing languages across recipients or threads.

## 30. Recommended Source Organization

A clean, extensible layout:

~~~text
src/main/java/com/example/
  DemoApplication.java
  i18n/
    LocaleConfiguration.java
    LocalizedMessageService.java
  user/
    CreateUserRequest.java
    UserController.java
    UserNotFoundException.java
  web/
    ApiExceptionHandler.java
    ValidationExceptionHandler.java

src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
  messages_vi_VN.properties
~~~

Responsibility boundaries:

| Component | Responsibility |
|---|---|
| `messages*.properties` | Message copy and placeholders |
| `MessageSource` | Resolves messages by code, arguments, and locale |
| `LocaleResolver` | Determines HTTP request locale |
| Domain/service | Determines business state and error conditions |
| Exception handler | Selects HTTP status, public error code, localized message |
| Bean Validation | Validates input constraints |
| Background notification | Selects recipient locale and builds messages outside HTTP requests |

When messages span multiple channels, a small wrapper service around `MessageSource` helps prevent raw key strings from scattering everywhere. Do not over-engineer abstractions for tiny apps, yet keep keys consistent across controllers, services, and workers.

## 31. Common Misconceptions

**"MessageSource automatically knows each user's language."** No. The caller or Spring environment supplies `Locale`, and the app defines its locale-selection policy.

**"Accept-Language always reflects the user's saved profile language."** No. It is a per-request client hint. Saved profile preferences may differ.

**"Just creating messages_vi.properties guarantees Spring Boot auto-configures it."** Not in every setup. A base bundle or matching message-source configuration is needed.

**"@Value and MessageSource are the same."** No. `@Value` injects configuration properties or resources; `MessageSource` resolves localized messages.

**"String.format() works fine for every language."** No. Word order, numbers, and regional rules differ. Message bundles plus `MessageFormat` let each translation arrange sentences naturally.

**"Having MessageSource in ApplicationContext means all exceptions translate automatically."** No. Exception handlers, validation, or presentation layers must explicitly invoke it.

**"HTTP request Locale follows @Async automatically."** Never guaranteed. Pass the target locale explicitly into background tasks.

**"Missing translations always fall back to English."** Only if your base bundle and fallback policy are structured that way. Otherwise you may hit `NoSuchMessageException` or get raw keys.

**"Locale vi-VN implies timezone Asia/Ho_Chi_Minh."** No. Language/region and time zone are independent concepts.

**"You can switch language with ?lang=vi using any LocaleResolver."** No. Header-based resolvers do not support stateful locale updates the way session/cookie resolvers do.

**"Error codes and translated sentences are interchangeable."** Never. Stable codes serve programs; translated sentences serve users.

**"Changing cache-duration live-reloads bundles inside a deployed JAR."** No. Packaged bundles in immutable artifacts do not change because of cache settings.

## Conclusion

**`MessageSource`** is Spring's standard mechanism for resolving messages from **message code + arguments + Locale**. In Spring Boot, creating bundles such as `messages.properties` and `messages_vi.properties` separates display copy from Java code and organizes multilingual support cleanly.

In web applications, **`LocaleResolver`** determines the request locale; the common stateless API choice is reading `Accept-Language`. For websites remembering user selections across requests via query parameters, sessions, or cookies, pick an appropriate stateful resolver. For emails and background jobs, pass the recipient's `Locale` explicitly.

For error responses, keep **HTTP status** and **business error codes** stable while localizing only **message**. Pair `MessageSource` with `@RestControllerAdvice` and Bean Validation to deliver helpful per-field feedback while safeguarding fallback behavior, encoding, placeholder quoting, and sensitive data.

When the boundaries among **error semantics**, **translations**, and **locale selection** are cleanly separated, Spring Boot serves diverse audiences while keeping APIs predictable, maintainable, and consistent.
