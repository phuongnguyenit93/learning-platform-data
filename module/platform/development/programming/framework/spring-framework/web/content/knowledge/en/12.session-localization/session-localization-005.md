# LocaleResolver, LocaleContextResolver, and Language Selection in Spring MVC

## 1. The Problem: One Page, Multiple Languages

A user visits a website with the HTTP header:

```http
GET /welcome HTTP/1.1
Accept-Language: vi-VN,vi;q=0.9,en;q=0.7
```

They expect a greeting in Vietnamese. Another user sending `Accept-Language: en-US,en;q=0.8` expects English. Later, a user may select a language manually, and that choice should be remembered in a cookie or session. This requirement raises three distinct questions:

1. **How is the current language (locale) chosen?** Spring MVC uses a `LocaleResolver`.
2. **What if a time zone is needed in addition to language?** `LocaleContextResolver` extends the model to return a `LocaleContext`, which can also include a `TimeZone`.
3. **Once a locale is chosen, how is translated text rendered?** `MessageSource`, resource bundles, and template engines use the resolved locale to look up messages. A resolver itself does not translate text.

After this lesson, you will know the `AcceptHeaderLocaleResolver`, `CookieLocaleResolver`, `SessionLocaleResolver`, and `FixedLocaleResolver` strategies; how to configure `LocaleChangeInterceptor`; how to distinguish language/region from time zone; how to handle fallbacks and supported languages; how to apply `MessageSource` in controllers and Thymeleaf; and how to test using Spring Boot 3, Java 17, and MockMvc.

**Scope:** Spring MVC **Servlet stack**, Spring Framework 6.x (e.g., 6.2), and Spring Boot 3.x. Spring WebFlux also has an interface named `LocaleContextResolver`, but it lives in package `org.springframework.web.server.i18n` and uses `ServerWebExchange`; **do not accidentally import it** instead of the Servlet MVC package `org.springframework.web.servlet`.

## 2. What Is a Locale? Do Not Confuse It with Plain Language

`java.util.Locale` expresses language and cultural/regional information such as region, script, and variant where applicable:

| Language tag | Typical meaning | `Locale.forLanguageTag(...)` |
| --- | --- | --- |
| `vi` | Vietnamese, no country specified | `Locale.forLanguageTag("vi")` |
| `vi-VN` | Vietnamese in Vietnam | `Locale.forLanguageTag("vi-VN")` |
| `en` | English in general | `Locale.forLanguageTag("en")` |
| `en-US` | English in the United States | `Locale.forLanguageTag("en-US")` |
| `en-GB` | English in the United Kingdom | `Locale.forLanguageTag("en-GB")` |
| `ja-JP` | Japanese in Japan | `Locale.forLanguageTag("ja-JP")` |
| `zh-Hant-TW` | Traditional Chinese, Taiwan region | Locale with language/script/region |

Locale governs **message** selection and number, date, and currency formatting; it **does not necessarily determine the time zone**. With the same `en-US`, a user might be in New York, Seattle, or Hanoi. `TimeZone` represents an independent attribute such as `Asia/Ho_Chi_Minh` or `Europe/London`, which is especially important when rendering an `Instant` in local time.

To parse standard BCP 47 language tags, use:

```java
Locale vn = Locale.forLanguageTag("vi-VN");
Locale us = Locale.forLanguageTag("en-US");
System.out.println(vn.toLanguageTag());
System.out.println(us.getLanguage());
```

This illustrative snippet requires `import java.util.Locale;`, with corresponding stdout:

```text
vi-VN
en
```

This is illustrative Java logic; to run standalone, place it inside a class with `main`. In URL parameters and cookies, use consistent language tags such as `vi`, `en`, or `vi-VN`, rather than arbitrarily concatenating strings with underscores.

### 2.1. `Accept-Language` Is Not a Mandatory Selection

HTTP `Accept-Language` expresses the user agent's **preference** order; `q` from 0 to 1 denotes weight. The server can restrict supported languages and choose an appropriate fallback; a client requesting `fr-CA` does not obligate the application to have a `fr-CA` translation. Some API clients do not send this header at all. A manual choice in an account/cookie/session may take precedence over the header if that is the application's policy.

For an honest API, distinguish:

- **Requested locale:** the preference presented by the client.
- **Resolved locale:** the result selected by the Spring MVC strategy for the request.
- **Actual message bundle used:** bundles such as `messages_vi.properties`; a key may fall back to the default bundle even if the resolved locale is `vi-VN`.
- **User's time zone:** an independent attribute, not inferred from language.

## 3. Role of `LocaleResolver` in `DispatcherServlet`

The Servlet MVC interface:

```java
package org.springframework.web.servlet;

public interface LocaleResolver {
    Locale resolveLocale(HttpServletRequest request);

    void setLocale(HttpServletRequest request,
                   HttpServletResponse response,
                   Locale locale);
}
```

*This is an abbreviated signature to explain meaning, not full source (nullability annotations and docs are omitted).*

`resolveLocale(request)` returns the current locale according to a strategy: header, cookie, session, or fixed value. `setLocale(...)` requests changing the locale, though **not every implementation supports** this operation.

`DispatcherServlet` looks up a bean named exactly **`localeResolver`** in its context. If none is present, the framework defaults to `AcceptHeaderLocaleResolver`. This selection can be auto-configured by Spring Boot or overridden with a custom bean.

Simplified flow:

```text
HTTP request
    │
    ▼
DispatcherServlet
    │
    ├── Select HandlerMapping and controller
    │
    ├── LocaleResolver.resolveLocale(request)
    │       ├── Accept-Language
    │       ├── cookie
    │       ├── HttpSession
    │       └── fixed/fallback
    │
    ├── LocaleContextHolder / request context
    │       └── current locale of the request
    │
    ├── Controller, Validator, Formatter, Template View
    │       └── MessageSource.getMessage(code, args, locale)
    │
    ▼
HTML/JSON or messages in the selected language
```

**Never store a user's locale in a mutable field on a singleton controller.** Controller/service beans serve many requests concurrently. Read the locale from the current request or context, or pass `Locale` explicitly as a method parameter.

### 3.1. Obtaining the Locale in Application Code

Options:

```java
@GetMapping("/locale")
@ResponseBody
String locale(Locale locale) {
    return locale.toLanguageTag();
}
```

A `Locale` method argument is resolved by Spring MVC from the request. Related APIs:

- `LocaleContextHolder.getLocale()`: gets the locale bound to the current context, normally the Servlet request-processing thread.
- `RequestContextUtils.getLocale(request)`: gets the locale from the request via the registered MVC resolver.
- `RequestContextUtils.getTimeZone(request)`: gets the time zone if the resolver supports a time-zone context; may return null.

`LocaleContextHolder` is thread-context-based, so in `@Async`, executors, background tasks, or manually spawned threads, the HTTP request's locale **is not propagated automatically**. When using asynchronous processing, pass the locale explicitly or design proper context propagation; never retain `HttpServletRequest` for use after the request has completed.

## 4. How Does `LocaleContextResolver` Differ from `LocaleResolver`?

In **Servlet MVC**, `org.springframework.web.servlet.LocaleContextResolver` is an interface that **extends `LocaleResolver`** and adds support for `LocaleContext`:

```java
package org.springframework.web.servlet;

public interface LocaleContextResolver extends LocaleResolver {
    LocaleContext resolveLocaleContext(HttpServletRequest request);

    void setLocaleContext(HttpServletRequest request,
                          HttpServletResponse response,
                          LocaleContext localeContext);
}
```

*Signature simplified by omitting annotations and some default methods for clarity; `LocaleContext` belongs to `org.springframework.context.i18n`.*

`LocaleContext` provides `getLocale()`. When the context instance also implements `TimeZoneAwareLocaleContext`, it can provide `getTimeZone()`.

Relationship diagram:

```text
LocaleResolver
 ├── resolveLocale(request): Locale
 └── setLocale(request, response, locale)
          ▲
          │ extends
LocaleContextResolver
 ├── resolveLocaleContext(request): LocaleContext
 └── setLocaleContext(request, response, context)
       │
       └── LocaleContext
            ├── Locale getLocale()
            └── if TimeZoneAwareLocaleContext:
                 TimeZone getTimeZone()
```

In Spring MVC 6.x, `CookieLocaleResolver`, `SessionLocaleResolver`, and `FixedLocaleResolver` implement this extended interface via `AbstractLocaleContextResolver`. `AcceptHeaderLocaleResolver` implements the base `LocaleResolver`: it reads the language from the header and does not store a user's time zone or manual selection.

### 4.1. When Is a Time Zone Needed?

For example, a booking email at `2026-12-24T09:00:00Z`:

- In time zone `Asia/Ho_Chi_Minh`, the corresponding time is 16:00 on the same day.
- In `Europe/London` in December, the corresponding time is 09:00 (GMT standard time).

Locale specifies display language such as `vi` or `en`; to display an absolute timestamp, you must know the time zone. When converting an `Instant`, prefer `java.time.ZoneId`/`ZonedDateTime`. A `TimeZone` from `LocaleContext` can be converted to `ZoneId` via `timeZone.toZoneId()`.

Example reading the time zone from a request:

```java
TimeZone timeZone = RequestContextUtils.getTimeZone(request);
ZoneId zone = timeZone != null
        ? timeZone.toZoneId()
        : ZoneId.of("UTC");

String localTime = instant.atZone(zone).toString();
```

*Illustrative snippet requiring `HttpServletRequest request`, `Instant instant`, and imports. The UTC fallback here is a sample policy; do not assume every system should display times in UTC.*

**Distinguish clearly:** `LocaleChangeInterceptor` changes the *locale*, not a full interface for choosing a *time zone*. To change both, an application can call `LocaleContextResolver#setLocaleContext(...)` with `SimpleTimeZoneAwareLocaleContext` if the resolver supports it, or provide a separate endpoint/policy.

## 5. Four Common `LocaleResolver` Strategies

| Resolver | Locale source | Changeable via `setLocale`? | Retention lifetime | Has time-zone context? |
| --- | --- | --- | --- | --- |
| `AcceptHeaderLocaleResolver` | `Accept-Language` in the HTTP request | **No**; header is controlled by client | Per request | Does not implement `LocaleContextResolver` |
| `CookieLocaleResolver` | Cookie storing selection, fallback if absent | **Yes** | Per cookie; configurable max age | Yes |
| `SessionLocaleResolver` | `HttpSession` attribute, fallback if unset | **Yes** | Within the user's session | Yes |
| `FixedLocaleResolver` | Fixed locale configured by server | **No** dynamic changes | Fixed for all requests | Can have a default time zone |

All reside in package `org.springframework.web.servlet.i18n`. Choosing the right resolver depends on your goal: an API taking language from HTTP headers, a website letting visitors pick a language stored in a cookie, a website already using sessions, or an application serving a single language.

### 5.1. `AcceptHeaderLocaleResolver`

This is the familiar Spring MVC default when no other resolver is registered. It relies on `ServletRequest.getLocale()` and/or a configured list of supported locales.

```java
@Bean
LocaleResolver localeResolver() {
    AcceptHeaderLocaleResolver resolver =
            new AcceptHeaderLocaleResolver();
    resolver.setSupportedLocales(List.of(
            Locale.forLanguageTag("vi"),
            Locale.forLanguageTag("en")
    ));
    resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
    return resolver;
}
```

*This is a standalone alternative configuration; do not use it simultaneously with the cookie resolver in the Section 8 project.*

With `supportedLocales` configured, Spring finds a matching locale among `Accept-Language` preferences. An easy detail to miss: matching considers **language and country**; if you only declare `en-US`, a client sending `en-GB` will not match automatically. To enable language-level fallback, also include `en` in the supported list. When nothing matches, `defaultLocale` is used if set; otherwise it falls back to the request locale.

**Important:** `AcceptHeaderLocaleResolver#setLocale(...)` is unsupported and may throw `UnsupportedOperationException`. Do not blindly pair it with `LocaleChangeInterceptor` if the interceptor will invoke `setLocale(...)` on a query parameter.

### 5.2. `CookieLocaleResolver`

Cookies suit websites that want to remember language choices across requests without requiring a server session:

```java
@Bean
LocaleResolver localeResolver() {
    CookieLocaleResolver resolver =
            new CookieLocaleResolver("SITE_LANG");
    resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
    resolver.setCookieMaxAge(Duration.ofDays(30));
    resolver.setCookiePath("/");
    resolver.setCookieSameSite("Lax");
    resolver.setCookieHttpOnly(true);
    return resolver;
}
```

*Illustrative snippet inside `@Configuration`, requiring imports for `LocaleResolver`, `CookieLocaleResolver`, `Duration`, and `Locale`. Full runnable app is in Section 8.*

When a user selects `lang=en`, an interceptor/controller can call `setLocale(...)` and emit a `Set-Cookie` header to save the selected locale. Subsequent requests send back the cookie; the resolver reads that value. `maxAge` determines retention duration; if you want the cookie to live only for the browser session, choose the matching configuration rather than forcing a fixed duration.

Cookies carry user preferences, not proof of authentication or authorization. Do not use a locale cookie to trust security-sensitive fields. In production HTTPS, consider `Secure`, `SameSite`, `HttpOnly`, cookie path/domain, retention duration, and privacy policies. Responses may need `Vary: Cookie` or a tailored cache policy when HTML varies by locale cookie.

A saved cookie choice can **take precedence over `Accept-Language`**. If `defaultLocale` is fixed on the resolver, the fallback locale may use that value instead of the header. Document the precedence order clearly in your product.

### 5.3. `SessionLocaleResolver`

`SessionLocaleResolver` stores locale/timezone in `HttpSession`. An illustrative configuration:

```java
@Bean
LocaleResolver localeResolver() {
    SessionLocaleResolver resolver = new SessionLocaleResolver();
    resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
    return resolver;
}
```

Suitable for server-side apps that already use sessions and want to retain the selection temporarily for the session's lifetime. The selection is typically lost when the session expires or is cleared. If the system wants to avoid creating sessions, consider cookies or AcceptHeader. Do not equate session locale with a durable account profile language: if the user is logged in, you may need to sync the choice to a database and reload it in future sessions.

### 5.4. `FixedLocaleResolver`

`FixedLocaleResolver` always returns a fixed default locale, optionally with a default time zone:

```java
@Bean
LocaleResolver localeResolver() {
    return new FixedLocaleResolver(
            Locale.forLanguageTag("vi"),
            TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
    );
}
```

*Illustrative snippet requiring imports for `FixedLocaleResolver`, `Locale`, and `TimeZone`; do not run concurrently with other resolver beans.*

Use when the application has a single fixed language, or when deterministic behavior is needed in an environment. Do not use `LocaleChangeInterceptor` for dynamic switching with a fixed resolver because `setLocale` is unsupported.

## 6. `LocaleChangeInterceptor`: Letting Users Choose a Language

`org.springframework.web.servlet.i18n.LocaleChangeInterceptor` is a `HandlerInterceptor`. It inspects a configured query parameter (default `locale`), parses it into a `Locale`, and calls `LocaleResolver#setLocale(request, response, locale)`.

Example URLs:

```text
GET /welcome?lang=en
GET /welcome?lang=vi
```

Configuration:

```java
@Configuration
class WebLocaleConfig implements WebMvcConfigurer {

    @Bean
    LocaleResolver localeResolver() {
        CookieLocaleResolver resolver =
                new CookieLocaleResolver("SITE_LANG");
        resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
        return resolver;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        LocaleChangeInterceptor interceptor =
                new LocaleChangeInterceptor();
        interceptor.setParamName("lang");
        interceptor.setHttpMethods("GET");
        registry.addInterceptor(interceptor);
    }
}
```

*Illustrative configuration snippet; the complete project below includes imports and cookie options.*

### 6.1. Sequence During a Language-Change Request

```text
GET /welcome?lang=en
       │
       ▼
HandlerMapping selects controller + interceptor chain
       │
       ▼
LocaleChangeInterceptor.preHandle(...)
       ├── detects param lang=en
       ├── parses Locale("en")
       └── resolver.setLocale(request, response, Locale.ENGLISH)
                  ├── CookieLocaleResolver writes cookie
                  └── resolver stores locale for the current request
       │
       ▼
Controller or View uses the selected locale
       │
       ▼
MessageSource resolves message from messages_en.properties
```

Within the same request, the resolver updates the locale so the handler/view sees the new choice. The browser stores the cookie and sends it back afterward.

### 6.2. Avoid Pairing the Interceptor with Unmodifiable Resolvers

Table:

| Resolver | `?lang=en` with `LocaleChangeInterceptor` |
| --- | --- |
| `AcceptHeaderLocaleResolver` | Incompatible; `setLocale` may throw `UnsupportedOperationException` |
| `FixedLocaleResolver` | Incompatible; does not allow dynamic locale changes |
| `CookieLocaleResolver` | Compatible; writes cookie |
| `SessionLocaleResolver` | Compatible; stores in session |

`setParamName("lang")` changes the query parameter name. You can call `setHttpMethods("GET")` to restrict which HTTP methods may switch locale; `setIgnoreInvalidLocale(true)` ignores unparseable locale strings, yet **is not a supported-language whitelist**.

**Security/UX note:** never accept unbounded language tags from clients and use them in file paths, SQL, or business logic. Parsing a locale does not prove a message bundle exists for that language. Whitelist choices like `vi` and `en` in the UI and validate inputs on the server; when an unsupported language arrives, reject or fall back intentionally. If changing locale via GET writes a cookie, consider caching, crawlers, CSRF, and privacy, and define an appropriate contract rather than using it for critical state mutations.

## 7. `MessageSource` and Template Engines: Selecting a Locale Is Not Translation

`LocaleResolver` only picks the locale. Strings like `"Welcome"` or `"Xin chào"` live in **message bundles** managed by `MessageSource`, for example:

```properties
# messages.properties - default bundle
greeting=Welcome!
title=Locale demonstration
```

```properties
# messages_vi.properties
greeting=Xin chào!
title=Ví dụ ngôn ngữ
```

```properties
# messages_en.properties
greeting=Hello!
title=Language example
```

A controller can call:

```java
@GetMapping("/api/message")
Map<String, String> message(HttpServletRequest request) {
    Locale locale = RequestContextUtils.getLocale(request);
    String text = messageSource.getMessage("greeting", null, locale);
    return Map.of(
            "language", locale.getLanguage(),
            "message", text);
}
```

*This illustrates a handler in a controller with an injected `MessageSource messageSource` field; the full project is in Section 8.*

In Thymeleaf, use the `#{greeting}` expression:

```html
<h1 th:text="#{greeting}">Default greeting</h1>
```

That expression looks up the key in `MessageSource` using the request's locale. It differs from `${someModelValue}`, which accesses a model variable; `#` and `$` have different meanings.

### 7.1. Spring Boot `MessageSource` Auto-Configuration

Spring Boot normally looks for the default bundle `classpath:/messages.properties`. **If you only have `messages_vi.properties` and `messages_en.properties` without a default `messages.properties`, `MessageSource` auto-configuration may not activate as expected.** Define the default file to provide an intentional fallback.

Example configuration:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

- `spring.messages.basename`: one or more bundle base names.
- `encoding=UTF-8`: preserves Vietnamese diacritics.
- `fallback-to-system-locale=false`: prevents results from depending on the OS locale in certain fallback flows.
- `MessageSource` resolves by locale specificity when matching files exist, such as `messages_vi_VN.properties` and `messages_vi.properties`, then falls back per configuration and the default bundle.

A user selecting `vi-VN` can still resolve keys from `messages_vi.properties` if no region-specific file exists. Bundle filenames use underscores per Java resource bundle convention, whereas HTTP language tags use hyphens (`vi-VN`). Never construct file paths directly from arbitrary query parameters.

### 7.2. Locale Also Affects Numbers, Dates, and Validation Messages

- `Formatter`, `@NumberFormat`, and `@DateTimeFormat` can use locale for parsing/printing during web binding when configured accordingly. Formatting dates/times also requires a time zone to map the instant accurately.
- Constraint messages in Jakarta Bean Validation can integrate with Spring `MessageSource` or a separate validation bundle depending on validator configuration. Do not assume merely creating `messages_vi.properties` gives every Hibernate Validator message a custom Vietnamese translation.
- A JSON API request can choose a language for **error messages**, yet should keep error `code` stable so client logic does not depend on localized prose.
- For HTML caches/CDNs, responses varying by `Accept-Language` should consider the `Vary: Accept-Language` header; cookie-based responses must consider cookies/sessions. Caches can serve the wrong language across users if the cache key does not account for language.

## 8. Complete Example: Spring Boot 3 + Java 17 + `CookieLocaleResolver`

The small application provides:

- `GET /api/greeting`: JSON containing the current language and translated message from `MessageSource`.
- `GET /api/greeting?lang=en` or `?lang=vi`: interceptor switches locale and issues the `SITE_LANG` cookie.
- Subsequent requests sending the cookie receive the same language without needing a query parameter.
- `GET /api/context`: demonstrates `LocaleContext` and time zone.
- `GET /welcome`: Thymeleaf renders text using `#{greeting}` instead of placing a pre-translated string into the model.
- MockMvc tests proving default/fallback, language switching, cookie replay, message rendering, and timezone context.

Uses **Spring Boot 3.3.13**, Java 17+, and Maven. This models **one explicitly configured cookie resolver**, without simultaneously defining AcceptHeader/Session/Fixed resolvers in the same context.

### 8.1. Project Structure

```text
locale-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/LocaleDemoApplication.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       ├── messages_vi.properties
    │       ├── messages_en.properties
    │       └── templates/welcome.html
    └── test/java/example/LocaleDemoTest.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>locale-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
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

### 8.3. `application.properties` and Message Bundles

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false

spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.cache=false
```

`src/main/resources/messages.properties`:

```properties
greeting=Welcome!
title=Locale demonstration
```

`src/main/resources/messages_vi.properties`:

```properties
greeting=Xin chào!
title=Ví dụ ngôn ngữ
```

`src/main/resources/messages_en.properties`:

```properties
greeting=Hello!
title=Language example
```

Each key has a translation. With `lang=vi`, the response is `"Xin chào!"`. With `lang=en`, the response is `"Hello!"`. For other languages without a bundle, fallback rules may use `messages.properties`; the demo focuses only on `vi` and `en`.

### 8.4. `LocaleDemoApplication.java`

Place all of the following code in `src/main/java/example/LocaleDemoApplication.java`. Only the main class is a public top-level class; the remaining classes are package-private.

```java
package example;

import java.time.Duration;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.CookieLocaleResolver;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.support.RequestContextUtils;

@SpringBootApplication
public class LocaleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LocaleDemoApplication.class, args);
    }
}

@Configuration
class LocaleWebConfig implements WebMvcConfigurer {

    // Bean name "localeResolver" is recognized by DispatcherServlet.
    @Bean
    LocaleResolver localeResolver() {
        CookieLocaleResolver resolver =
                new CookieLocaleResolver("SITE_LANG");

        // Explicit default ensures the result does not depend on OS locale.
        resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
        resolver.setDefaultTimeZone(
                TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));

        resolver.setCookieMaxAge(Duration.ofDays(30));
        resolver.setCookiePath("/");
        resolver.setCookieSameSite("Lax");
        resolver.setCookieHttpOnly(true);

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

@RestController
class GreetingApiController {
    private final MessageSource messageSource;

    GreetingApiController(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @GetMapping("/api/greeting")
    Map<String, String> greeting(HttpServletRequest request) {
        Locale locale = RequestContextUtils.getLocale(request);

        String message =
                messageSource.getMessage("greeting", null, locale);

        return Map.of(
                "language", locale.getLanguage(),
                "message", message);
    }

    @GetMapping("/api/context")
    Map<String, String> context(HttpServletRequest request) {
        Locale locale = RequestContextUtils.getLocale(request);
        TimeZone zone = RequestContextUtils.getTimeZone(request);

        return Map.of(
                "language", locale.getLanguage(),
                "timeZone", zone != null ? zone.getID() : "unset");
    }
}

@Controller
class WelcomePageController {
    @GetMapping("/welcome")
    String welcome() {
        return "welcome";
    }
}
```

Explanation:

- The `localeResolver()` bean method takes the method name as its default bean name, matching the exact key `DispatcherServlet` looks up.
- `CookieLocaleResolver("SITE_LANG")` uses the non-deprecated constructor in Spring 6; no need to call `setCookieName(...)`, which was deprecated in 6.0.
- `setDefaultLocale(vi)` sets a fixed fallback locale. In this demo, **when no cookie is present**, that default takes precedence; therefore `Accept-Language: en` alone **does not guarantee** English selection. To prioritize the header, avoid configuring a fixed default this way or use `AcceptHeaderLocaleResolver` per your contract.
- `setDefaultTimeZone(...)` gives `LocaleContext` a fallback time zone. It does not change the language.
- `LocaleChangeInterceptor` reads `?lang=en`, asks the resolver to update the locale, and writes the cookie for future requests.
- `MessageSource` resolves the `greeting` key for the locale. Even for a JSON API body, locale can localize messages.
- The demo does not store a global locale in a mutable singleton; each handler reads from the request.

### 8.5. `templates/welcome.html`

File `src/main/resources/templates/welcome.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title th:text="#{title}">Demo</title>
</head>
<body>
  <h1 th:text="#{greeting}">Greeting</h1>
  <nav>
    <a th:href="@{/welcome(lang='vi')}">Tiếng Việt</a>
    <a th:href="@{/welcome(lang='en')}">English</a>
  </nav>
</body>
</html>
```

`th:text="#{greeting}"` looks up the key in `MessageSource` using the active locale; `th:href="@{/welcome(lang='en')}"` builds the language-switch link. The template sets a static `lang="vi"` for readability, yet **that is inaccurate** when the user views English. Real applications should add `th:lang="${#locale.language}"` so HTML `lang` reflects the selected language. If needed, replace the `<html>` tag with:

```html
<html xmlns:th="http://www.thymeleaf.org"
      th:lang="${#locale.language}">
```

At runtime, Thymeleaf binds `#locale` to the current locale automatically. Do not confuse `#{greeting}` (message expression) with `${#locale.language}` (variable expression).

### 8.6. Running and Observing

In the `locale-demo` directory:

```bash
mvn test
mvn spring-boot:run
```

Test the API:

```bash
curl -i http://localhost:8080/api/greeting
curl -i "http://localhost:8080/api/greeting?lang=en"
curl -i http://localhost:8080/api/context
```

Expected JSON response bodies:

- No cookie/param: `{"language":"vi","message":"Xin chào!"}` (JSON key order may vary).
- `?lang=en`: `{"language":"en","message":"Hello!"}` plus a `Set-Cookie` header for `SITE_LANG`.
- `/api/context` with default config: `{"language":"vi","timeZone":"Asia/Ho_Chi_Minh"}` when the request carries no cookie/param; the time zone can be carried in the locale context when supported by the resolver.

Use a cookie jar to prove the choice persists across requests:

```bash
curl -i -c locale-cookies.txt \
  "http://localhost:8080/api/greeting?lang=en"

curl -i -b locale-cookies.txt \
  http://localhost:8080/api/greeting

curl -i -b locale-cookies.txt \
  http://localhost:8080/welcome
```

Both GET requests using the cookie return English. On the Thymeleaf page, the heading and title contain `Language example` and `Hello!`. Opening `http://localhost:8080/welcome?lang=vi` directly causes the interceptor to update the cookie back to Vietnamese.

**Note:** the `curl` commands above assume a shell supporting `\` line continuation; on Windows PowerShell, use `curl.exe` and keep arguments on one line.

### 8.7. MockMvc: Verifying Cookies and Locale

File `src/test/java/example/LocaleDemoTest.java`:

```java
package example;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class LocaleDemoTest {
    @Autowired
    MockMvc mvc;

    @Test
    void fallbackLocaleIsVietnamese() throws Exception {
        mvc.perform(get("/api/greeting"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"))
            .andExpect(jsonPath("$.message").value("Xin chào!"));
    }

    @Test
    void queryParameterChangesLocaleOnCurrentRequest()
            throws Exception {
        mvc.perform(get("/api/greeting").param("lang", "en"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("en"))
            .andExpect(jsonPath("$.message").value("Hello!"));
    }

    @Test
    void chosenLocaleIsPersistedInCookie() throws Exception {
        MvcResult changed =
                mvc.perform(get("/api/greeting").param("lang", "en"))
                   .andExpect(status().isOk())
                   .andReturn();

        String header = changed.getResponse().getHeader("Set-Cookie");
        assertNotNull(header);
        assertTrue(header.startsWith("SITE_LANG="));

        // Parse only the first name=value pair in the Set-Cookie header;
        // demo cookie holds only a language tag, with no internal '=' sign.
        String value = header.split(";", 2)[0].split("=", 2)[1];

        mvc.perform(get("/api/greeting")
                    .cookie(new Cookie("SITE_LANG", value)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("en"))
            .andExpect(jsonPath("$.message").value("Hello!"));
    }

    @Test
    void defaultTimeZoneIsResolvedFromLocaleContext()
            throws Exception {
        mvc.perform(get("/api/context"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"))
            .andExpect(jsonPath("$.timeZone")
                    .value("Asia/Ho_Chi_Minh"));
    }

    @Test
    void thymeleafRendersLocalizedMessage() throws Exception {
        mvc.perform(get("/welcome").param("lang", "en"))
            .andExpect(status().isOk())
            .andExpect(view().name("welcome"))
            .andExpect(content().string(
                    containsString("<h1>Hello!</h1>")));
    }

    @Test
    void apiResponseIsJsonNotAView() throws Exception {
        mvc.perform(get("/api/greeting").param("lang", "en"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Hello!"));
    }
}
```

Run `mvn test`. The test suite verifies the default locale, switching within the same request, sending and reusing the cookie, fallback time zone, Thymeleaf message bundle rendering, and JSON APIs not being confused with view templates. Each MockMvc request does not automatically retain cookies from the previous request; the test intentionally copies the cookie value to the next request to simulate a browser.

When deployed behind a reverse proxy, cookie policies may add `Secure`/`Domain` or alter header handling. In production applications, prefer full integration tests using a real HTTP client for the cookie lifecycle, not only MockMvc.

## 9. When to Use Headers, Cookies, Sessions, or User Accounts?

### 9.1. Stateless REST APIs

A client can send:

```http
GET /api/products/7 HTTP/1.1
Accept-Language: en
```

The server uses `AcceptHeaderLocaleResolver` and `MessageSource` to localize messages while keeping JSON error codes stable. No server session is needed. For multi-client APIs, distinguish requested locale from actually supported languages; do not return entirely different business content solely due to `Accept-Language` unless specified in the contract.

Some APIs choose a custom header or user profile; define a clear precedence order, especially when both cookies and `Accept-Language` exist. Internationalization should never silently alter IDs, enum codes, or currencies.

### 9.2. Server-Rendered Websites

`CookieLocaleResolver` is convenient for websites that do not want to create a session just to remember language. Use links/buttons to select a locale, then render Thymeleaf with message expressions. When a user logs in, language can be saved to their profile, with the cookie acting as a temporary cache/preference.

### 9.3. Websites Already Using `HttpSession`

`SessionLocaleResolver` fits when sessions are already part of the design. The selected locale persists until the session expires. If the session changes on login/logout or load balancing, keep profile/cookie/session synchronized consistently.

### 9.4. Single-Language Applications

`FixedLocaleResolver` fits single-language services or fixed test environments. Omit `LocaleChangeInterceptor` when dynamic switching is not needed.

### 9.5. Clear Precedence Strategy

An example of a **custom product policy** (not a mandatory Spring default order):

```text
1. Explicit user preference saved in profile
2. User-selected language cookie
3. Accept-Language from HTTP request
4. Product default locale, for example vi
```

Implement this policy explicitly in a resolver or custom logic, especially when only `vi`/`en` are supported. Do not expect Spring to combine profile, cookie, and header in that order automatically unless you code it.

## 10. Common Errors and Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `?lang=en` throws `UnsupportedOperationException` | Using `LocaleChangeInterceptor` with AcceptHeader/Fixed resolver | Switch to Cookie/Session or disable dynamic locale switching |
| Using `LocaleContextResolver` with wrong import | Imported from WebFlux's `org.springframework.web.server.i18n` | Use `org.springframework.web.servlet.LocaleContextResolver` for Spring MVC |
| `en-GB` header does not select expected language | `supportedLocales` configured with only `en-US` | Configure language-only `en` or compatible region |
| Browser sends `Accept-Language: en` yet still gets `vi` | Old cookie or `defaultLocale(vi)` takes precedence | Check resolver, cookie, and fallback order |
| `MessageSource` not activated | Missing default `messages.properties` or wrong basename | Add default bundle and check `spring.messages.*` |
| UI renders `??greeting??` or missing code error | Missing key in bundle, or bundle not loaded | Check key, basename, and language suffix |
| Vietnamese characters appear garbled | Mismatched file/response encodings | Ensure UTF-8 across editor, bundles, HTML meta, and response |
| Time zone is always null | Basic `LocaleResolver` only, or no time zone configured | Use `LocaleContextResolver` + default/user time zone |
| `en-US` formats dates in the wrong time zone | Locale is not a time zone | Use `ZoneId`/`TimeZone` separately |
| Locale changed yet background threads use old language | `LocaleContextHolder` does not cross threads automatically | Pass locale into tasks or propagate context |
| HTML CDN serves wrong language across users | Cache does not vary by language/cookie | Add cache key/`Vary` header or disable shared caching |
| User sends odd locale and UI falls back unexpectedly | Supported locales are not whitelisted | Validate against supported list and respond/fall back intentionally |
| Test changes cookie yet next request reverts to default | MockMvc does not simulate a browser cookie jar | Pass the cookie to the subsequent request |
| Using `Locale.US` for all Vietnamese users | Confusing language/region with UI locale | Use proper language tags and bundles with clear fallbacks |

### 10.1. Layer-by-Layer Debugging

1. Check whether the request carries `Accept-Language`, cookie `SITE_LANG`, or query param `lang`.
2. Identify the **exact resolver bean** named `localeResolver` used by `DispatcherServlet`. Check its bean type and defaults.
3. If `LocaleChangeInterceptor` is used, verify it is registered in `WebMvcConfigurer#addInterceptors` and the parameter name matches.
4. Read the resolved locale with `RequestContextUtils.getLocale(request)`; if time-zone context is needed, check `getTimeZone(request)`.
5. Inspect `messages.properties`, `messages_vi.properties`, `messages_en.properties`, keys, and encoding.
6. If the controller returns the right message yet Thymeleaf is wrong, check template expressions `#{...}`, theme, model, view name, and template cache.
7. For APIs, check that error `code` stays independent of localized `message` and review client caching policy.
8. Write MockMvc tests covering query params, cookies, and requests with no selection.

### 10.2. Two Wrong-and-Fixed Examples

**Wrong:**

```java
@Bean
LocaleResolver localeResolver() {
    return new AcceptHeaderLocaleResolver();
}

@Override
public void addInterceptors(InterceptorRegistry registry) {
    LocaleChangeInterceptor interceptor = new LocaleChangeInterceptor();
    interceptor.setParamName("lang");
    registry.addInterceptor(interceptor);
}
```

When a URL includes `?lang=en`, the interceptor calls `setLocale` on a resolver that does not support it, raising an error. This snippet illustrates the mistake; **do not** put it in a runnable project.

**Right when you want users to switch languages and persist it:**

```java
@Bean
LocaleResolver localeResolver() {
    return new CookieLocaleResolver("SITE_LANG");
}
```

Add the interceptor as in the Section 8 project and configure cookie/security options as needed.

## 11. Security, Performance, and Internationalization UX

- **XSS:** translations from message bundles can contain markup if the application permits it; never render user-supplied data as unescaped HTML. Thymeleaf `th:text` escapes text by default.
- **Open redirects:** locale-switching endpoints must not redirect to arbitrary URLs supplied by the request. Redirect only to allowed routes/hosts.
- **Cookies:** store only low-sensitivity preferences, choosing `SameSite`/`Secure`/`HttpOnly`/maxAge/path per policy; never use a language cookie to grant permissions.
- **Caching:** HTML responses vary by locale; configure caching by cookie/header or use explicit language URLs for cacheability.
- **SEO:** public multilingual websites may choose language URLs like `/vi/...` and `/en/...`, combined with `hreflang`/canonical tags per SEO strategy. Cookie-based locales are not always ideal for crawling every variant.
- **A11y:** the HTML `lang` attribute must reflect the displayed content; use dynamic `th:lang` as shown above.
- **I18n message design:** avoid concatenating sentences from literal fragments; use placeholders/pluralization suited to your tooling and translate in context.
- **Timezone & currency:** separate `Locale` from actual time zone and currency. `Locale.US` does not mean a user pays in USD; business logic must use dedicated trusted data sources.
- **Validation:** never translate field names or error codes by language; localize only human-friendly display messages.
- **Operations:** log the selected language at a non-sensitive level to diagnose bundle distribution issues; never log raw cookies containing request tokens.

## 12. Self-Check

1. Does `LocaleResolver` translate text itself? **No.** It resolves the locale; `MessageSource`/templates perform message lookup.
2. Which interface does `LocaleContextResolver` extend? **`LocaleResolver`**, adding methods for `LocaleContext`.
3. Can WebFlux's `LocaleContextResolver` be used in Servlet MVC? **No**, the two APIs belong to different packages and request types.
4. Does `AcceptHeaderLocaleResolver` support `setLocale` from a query parameter? **No**, because headers are controlled by the client.
5. To let users select English and remember it across requests without a server session, what should you choose? **`CookieLocaleResolver`**.
6. To remember the selection inside an `HttpSession`, what should you choose? **`SessionLocaleResolver`**.
7. When an application always displays only Vietnamese, which resolver fits? **`FixedLocaleResolver`** or a fixed locale policy.
8. Why might `supportedLocales` with only `en-US` fail to match `en-GB`? **Matching checks language+country**, so include `en` if you want language-level fallback.
9. Does `vi-VN` imply the `Asia/Ho_Chi_Minh` time zone? **No**; locale and time zone are independent data.
10. In Thymeleaf, how does `#{greeting}` differ from `${name}`? **`#{...}` looks up a message code**, while `${...}` reads a model variable.
11. Why is `messages.properties` important in Boot? **A default bundle ensures auto-configuration and fallbacks work as expected.**
12. Which parameter name does `LocaleChangeInterceptor` read by default? **`locale`**; it can be changed with `setParamName("lang")`.
13. If the saved language cookie is `en` while the header is `vi`, which is used? **Depends on the resolver/policy**; with `CookieLocaleResolver`, the cookie normally wins.
14. Does `MockMvc` automatically retain cookies from the previous request like a browser? **No by default**; pass the cookie on the next request.
15. Which API retrieves the time zone in Servlet MVC? **`RequestContextUtils.getTimeZone(request)`**, returning null if unavailable.
16. Why are `Vary: Accept-Language` or cookie-aware caches needed? **To avoid serving one user's translation to another user.**
17. Does using `LocaleContextHolder` inside a thread pool always see the request locale? **Not guaranteed**; explicit passing or context propagation is needed.
18. If a client sends `lang=fr` when only `vi`/`en` bundles exist, will the server always throw an error? **No.** The resolver may accept the locale while `MessageSource` falls back if no bundle exists; whitelist explicitly if you want to reject it.
19. If you translate headings yet leave `<html lang="vi">` on the English page, is that a problem? **Yes**, `lang` no longer reflects the content, harming accessibility and SEO.
20. How do you prove i18n works end-to-end? **Test resolver selection, `MessageSource` output, cookie replay, and locale-aware template rendering.**

## 13. Official References

- [Spring Framework 6.2 — Locale Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/localeresolver.html): resolvers, cookie/session, locale change interceptor.
- [`LocaleResolver` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/LocaleResolver.html): the two methods `resolveLocale`/`setLocale`.
- [`LocaleContextResolver` (Servlet) Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/LocaleContextResolver.html): time-zone-aware context and changing context.
- [`AcceptHeaderLocaleResolver` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/i18n/AcceptHeaderLocaleResolver.html): `supportedLocales`, matching, `setLocale` restriction.
- [`CookieLocaleResolver` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/i18n/CookieLocaleResolver.html): cookie configuration, default locale/time zone.
- [`LocaleChangeInterceptor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/i18n/LocaleChangeInterceptor.html): parameter name, HTTP method filter, invalid-locale handling.
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/3.3/reference/features/internationalization.html): auto-configuring `MessageSource` from bundles and properties.
- [Thymeleaf + Spring Tutorial](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): message expressions `#{...}`, variables, and Spring MVC integration.
- [MDN Accept-Language](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language): HTTP language preference and q-values.

**Takeaway:** `LocaleResolver` selects the **locale** for a request. `LocaleContextResolver` extends it with **`LocaleContext` and an optional time zone**. `LocaleChangeInterceptor` works only with resolvers that **allow changing the locale**, such as cookie or session resolvers. `MessageSource` and template engines produce the actual localized text. Define a clear precedence order across headers, cookies, sessions, and user profiles, and test language switching across multiple requests.
