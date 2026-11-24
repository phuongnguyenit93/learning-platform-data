# MessageSource, Locale, and UI Localization in Spring Boot

## 1. The Problem to Solve

A web application often has to present the same interface to users in Vietnam, the UK, the US, or other regions. Rather than hardcoding strings like "Sign in", "Welcome", or "Data not found" across many controllers and templates, Spring lets you separate **translatable content** from source code and select messages based on the request's **Locale**.

Three concepts play distinct roles:

- **Internationalization (i18n)**: designing an application so it can support multiple languages and regional conventions without rewriting logic; for example, using the message key `page.title` instead of a hardcoded string.
- **Localization (l10n)**: providing translations, formatting numbers/dates/currencies, and tailoring the experience for a specific locale; for example `vi-VN`, `en-US`, `en-GB`.
- **Locale**: a `java.util.Locale` object describing a language, region, and optionally script/variant. For instance, `vi` denotes Vietnamese; `vi-VN` denotes Vietnamese in the context of Vietnam. **Locale is not a time zone**, not UTF-8 encoding, and not user authorization.

**Two separate questions must be answered:**

1. **Which language does this request use?** Spring MVC uses `LocaleResolver`/`LocaleContextResolver`, typically reading `Accept-Language`, a session, or a cookie depending on configuration.
2. **For that language, how is "Hello" rendered?** Spring's `MessageSource` looks up the message code in the matching resource bundle and substitutes parameters.

Thymeleaf, JSP, server-rendered UIs, validation error messages, and even API responses can use this system. Localization **does not mean automatic text translation**: every translation still needs to be authored, tested, and maintained.

## 2. Processing Flow When a Browser Requests a Localized Page

```text
Browser (Accept-Language: vi-VN,vi;q=0.9,en;q=0.8)
                      |
                   HTTP GET /
                      |
                 Spring MVC
               DispatcherServlet
                      |
            LocaleResolver determines
                Locale vi-VN
                      |
          Controller -> model / view
                      |
          Thymeleaf: #{page.title}
                      |
                  MessageSource
                      |
      i18n/messages_vi_VN.properties (if present)
                    -> messages_vi.properties
                    -> messages.properties
                      |
                 "Chào mừng"
                      |
            HTML rendered and returned
```

The diagram shows the **high-level** precedence order when `fallback-to-system-locale=false`. JDK `ResourceBundle` and Spring settings may apply additional fallback rules; do not infer lookup order solely from filenames if fallback to the system locale is enabled.

Note: the **`Accept-Language`** header indicates preferred languages; the **`Accept`** header indicates media types such as `text/html` or `application/json`. These two headers serve different purposes.

## 3. What Is `MessageSource`?

`org.springframework.context.MessageSource` is the interface for resolving messages by **code + arguments + locale**. Spring's `ApplicationContext` also implements `MessageSource`; when a bean named `messageSource` exists, the context delegates lookups to that bean. Spring Boot can auto-configure a `MessageSource` bean from `.properties` files on the classpath.

Three key methods:

```java
// 1. Provides a fallback message if the code does not exist.
String a = messages.getMessage(
        "greeting.user", new Object[] {"Lan"}, "Hello!", locale);

// 2. No fallback message:
//    throws NoSuchMessageException if the code is missing.
String b = messages.getMessage(
        "greeting.user", new Object[] {"Lan"}, locale);

// 3. Uses MessageSourceResolvable, commonly seen in BindingResult.
String c = messages.getMessage(resolvable, locale);
```

These are **illustrative snippets**, not standalone runnable code, since `messages`, `locale`, and `resolvable` must be supplied.

| Component | Role | Example |
| --- | --- | --- |
| `code` | Stable key in the bundle | `greeting.user` |
| `args` | Values inserted into placeholders | `new Object[] {"Lan"}` |
| `locale` | Target language/region for lookup | `Locale.forLanguageTag("vi-VN")` |
| `defaultMessage` | Fallback text when key is missing | `"Hello!"` |
| `ResourceBundleMessageSource` | Implementation backed by standard Java resource bundles | `i18n/messages_vi.properties` |
| `ReloadableResourceBundleMessageSource` | More flexible implementation for resource locations and reloading | Suitable for custom message source setups |

In standard Spring Boot apps, **prefer auto-configuration** instead of manually defining `@Bean MessageSource`. Define the bean manually only for specialized storage sources, reload policies, or fallback rules.

### Codes, Messages, and Argument Values

Example `messages_vi.properties`:

```properties
greeting.user=Xin chào, {0}!
cart.items=Bạn có {0,number,integer} sản phẩm.
```

When called:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
String value = messages.getMessage(
        "greeting.user", new Object[] {"Lan"}, vi);
// value = "Xin chào, Lan!"
```

Placeholder `{0}` corresponds to the first element of the `args` array, `{1}` to the next, and so on. Spring uses **`java.text.MessageFormat`** to format arguments per locale; specifiers such as `{0,number,integer}` or `{0,date,short}` can be used. This is `MessageFormat` syntax, **not** Spring Expression Language `${...}` syntax.

### Single Quotes in `MessageFormat`

Single quotes have special meaning in `MessageFormat`. When `MessageFormat` is applied to a message, displaying a literal `'` requires writing `''` in the pattern:

```properties
sample.quote=Don''t remove ''{0}''.
```

Passing `new Object[]{"demo"}` formats the string as `Don't remove 'demo'.`. For messages **without arguments**, Spring by default may skip `MessageFormat` parsing (`spring.messages.always-use-message-format=false`). Establish a clear convention and test both parameterized and non-parameterized messages so apostrophes do not cause subtle bugs later when placeholders are added.

## 4. Resource Bundles: File Organization and Lookup Rules

### 4.1. File Structure

With basename `i18n/messages`, organize files as:

```text
src/main/resources/
├── application.properties
└── i18n/
    ├── messages.properties
    ├── messages_vi.properties
    ├── messages_en.properties
    └── messages_en_GB.properties   (optional)
```

Meaning:

- `messages.properties`: the **base bundle** and common fallback source; should always exist.
- `messages_vi.properties`: Vietnamese messages.
- `messages_en.properties`: English messages.
- `messages_en_GB.properties`: British English variant when regional wording differs (e.g., "postcode").
- `messages_vi_VN.properties` can be added if distinguishing Vietnamese by region.

Filenames follow `ResourceBundle` conventions using underscores (`vi_VN`), whereas HTTP `Accept-Language`/BCP 47 tags use hyphens (`vi-VN`). Do not name a file `messages_vi-VN.properties` expecting the JDK to locate it as a normal bundle.

### 4.2. Enabling Auto-Configuration Properly

`src/main/resources/application.properties`:

```properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

In a Spring Boot 3.5.x project, these are valid properties. `spring.messages.basename` **omits the `.properties` extension**; it locates the bundle group on the classpath. Boot supports multiple basenames, for example:

```properties
spring.messages.basename=i18n/messages,i18n/errors
```

When using separate files per basename, avoid unintentional duplicate keys because lookup order determines which bundle wins.

**Easy-to-miss condition:** Boot auto-configures `MessageSource` when a **base file without a language suffix** exists for at least one configured basename. If only `messages_vi.properties` exists without `messages.properties`, auto-configuration may not activate. Always create the base file even if most translations live in language-specific files.

### 4.3. Practical Fallback Rules

Suppose `spring.messages.fallback-to-system-locale=false` and the code resolves with `Locale.forLanguageTag("vi-VN")`:

1. Look up the specific `vi_VN` bundle if present.
2. Otherwise, look up the `vi` bundle.
3. If the key is still missing, look up `messages.properties`.
4. If the code does not appear anywhere, return the call's `defaultMessage`; if none was supplied, throw `NoSuchMessageException` (unless configured to use the code as the default message).

Example:

```properties
# messages.properties
page.title=Welcome
page.footer=Example application
```

```properties
# messages_vi.properties
page.title=Chào mừng
```

With `vi-VN`, `page.title` resolves to "Chào mừng", while `page.footer` still resolves to "Example application". Fallback works **per key**, not only when an entire file is missing.

Useful configuration properties:

| Property | Meaning | Notes |
| --- | --- | --- |
| `spring.messages.basename` | Specifies bundle sources | Defaults to `messages` at classpath root |
| `spring.messages.encoding` | File character encoding | Defaults to `UTF-8` in modern Boot |
| `spring.messages.fallback-to-system-locale` | Whether to try the OS locale when no matching bundle is found | Set `false` for predictable fallback to the base bundle |
| `spring.messages.cache-duration` | Bundle cache duration | Useful in development; production usually packages files inside the JAR |
| `spring.messages.always-use-message-format` | Always apply `MessageFormat` even without args | Requires consistent quote escaping |
| `spring.messages.use-code-as-default-message` | Display the code when translation is missing | Helpful for debugging; avoid hiding missing translations in production |

Despite Java's historical `.properties` encoding conventions, when Spring Boot configures `spring.messages.encoding=UTF-8`, files are read as UTF-8. Make sure your editor, build pipeline, and repository actually save the files in UTF-8.

## 5. Selecting the Request `Locale` in Spring MVC

**`MessageSource` does not determine the request's locale by itself.** Spring MVC uses a `LocaleResolver`, integrated with `DispatcherServlet`, to resolve the locale for web requests.

### 5.1. Default: `Accept-Language`

In standard Spring Boot MVC, the default locale resolver inspects the `Accept-Language` header. For example:

```http
GET / HTTP/1.1
Host: localhost:8080
Accept-Language: vi-VN,vi;q=0.9,en;q=0.8
```

With no other override configured, Spring can select `vi-VN` for message lookups. However, the server is **not forced to translate into every locale a browser asks for**; available bundles and fallback rules determine the actual output.

`AcceptHeaderLocaleResolver` **does not support changing the locale via `setLocale`**, because the language comes from the client's header. Thus, adding a `LocaleChangeInterceptor` to handle `?lang=vi` while keeping a header-only resolver will fail to switch languages as intended and can throw `UnsupportedOperationException`. To let users explicitly switch languages in the UI, use a stateful resolver such as session or cookie.

### 5.2. `SessionLocaleResolver` and `CookieLocaleResolver`

| Resolver | Locale Source | Pros | Considerations |
| --- | --- | --- | --- |
| `AcceptHeaderLocaleResolver` | HTTP `Accept-Language` | Natural for APIs; stores no language state on the server | Cannot be changed via `LocaleChangeInterceptor` |
| `SessionLocaleResolver` | `HttpSession`, with appropriate fallback when unset | Easy to build a language switcher for server-rendered UIs | Depends on session; lost when session expires |
| `CookieLocaleResolver` | Client-side cookie | Can persist choice across sessions when configured properly | Requires cookie/consent/security policy and value validation |
| Fixed resolver | A single configured locale | For single-language apps or tests | Not personalized per request |

`LocaleChangeInterceptor` detects a query parameter (default `locale`, configurable to `lang`) and asks the resolver to update the locale. The interceptor is only meaningful when the resolver supports changing state.

**Never treat locale as trusted evidence of country or identity.** Clients control headers, cookies, and query parameters; locale is not proof of geography, tax rules, or data access permissions.

### 5.3. Language, Region, and Time Zone

`Locale.forLanguageTag("en-GB")` and `Locale.forLanguageTag("en-US")` are both English yet differ in spelling and formatting. `TimeZone`/`ZoneId` is a separate concept: a user who prefers Vietnamese while living in London may still want schedules displayed in `Europe/London`.

To display dates and times accurately, pick both a **Locale for formatting** and a **ZoneId for the instant**. Never pass a timezone-less `LocalDateTime` into a formatter assuming it represents an absolute point in time.

## 6. Runnable Example: Spring Boot MVC + Thymeleaf + Language Switching

This complete example uses **Java 17**, **Maven**, **Spring Boot 3.5.16**, Spring MVC, and Thymeleaf. A specific version is pinned for reproducible POM execution; in production, pick a supported Spring Boot line and check compatibility. In Boot 4.x, some starter or API names may differ; do not mix dependencies from two major versions.

The application provides two features:

- `GET /`: returns a Thymeleaf page with localized title, description, and greeting.
- `GET /api/greeting?name=Lan`: returns text from `MessageSource` for the request locale.
- `GET /?lang=vi` and `GET /?lang=en`: switches the locale stored in the HTTP session.

### 6.1. Project Structure

```text
i18n-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/i18ndemo/
    │   ├── I18nDemoApplication.java
    │   ├── WebLocaleConfig.java
    │   └── PageController.java
    └── resources/
        ├── application.properties
        ├── i18n/
        │   ├── messages.properties
        │   ├── messages_en.properties
        │   └── messages_vi.properties
        └── templates/
            └── home.html
```

### 6.2. Complete Maven POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>i18n-demo</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

The Spring Boot parent manages Spring Framework, Thymeleaf, and related dependency versions. No explicit version is needed for Thymeleaf when using the matching starter/BOM.

### 6.3. Java Main

File `src/main/java/com/example/i18ndemo/I18nDemoApplication.java`:

```java
package com.example.i18ndemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(I18nDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` scans classes in the same package and subpackages, so adjacent controllers and configurations are discovered.

### 6.4. Locale Resolution and Switching Configuration

File `src/main/java/com/example/i18ndemo/WebLocaleConfig.java`:

```java
package com.example.i18ndemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration
public class WebLocaleConfig implements WebMvcConfigurer {

    @Bean
    public LocaleResolver localeResolver() {
        return new SessionLocaleResolver();
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        LocaleChangeInterceptor change = new LocaleChangeInterceptor();
        change.setParamName("lang");
        registry.addInterceptor(change);
    }
}
```

`SessionLocaleResolver` stores the choice in `HttpSession`. Before a user explicitly picks one, it can fall back to the request locale (typically derived from `Accept-Language`). When `?lang=vi` or `?lang=en` is sent, the interceptor calls `setLocale`, and the page renders in the new locale. Do not add `@EnableWebMvc`: that annotation can alter the MVC auto-configuration this example relies upon.

In production apps, restrict allowed languages, such as `vi` and `en` only, rather than blindly trusting arbitrary locale strings sent by clients.

### 6.5. Controller Serving Both HTML Pages and Text API

File `src/main/java/com/example/i18ndemo/PageController.java`:

```java
package com.example.i18ndemo;

import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class PageController {

    private final MessageSource messages;

    public PageController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/")
    public String home(Model model, Locale locale) {
        model.addAttribute("visitorName", "Lan");
        model.addAttribute("itemCount", 12);
        model.addAttribute("activeLanguage", locale.toLanguageTag());
        return "home";
    }

    @ResponseBody
    @GetMapping(value = "/api/greeting", produces = "text/plain;charset=UTF-8")
    public String greeting(
            @RequestParam(defaultValue = "Lan") String name,
            Locale locale) {
        return messages.getMessage(
                "greeting.user",
                new Object[] {name},
                locale
        );
    }
}
```

In `home`, `Locale locale` is an MVC argument resolved for the current request, and `Model` passes values to Thymeleaf. In `greeting`, `MessageSource` resolves the localized message; `@ResponseBody` writes the content straight to the HTTP response instead of looking up a template. `produces` specifies UTF-8 so Vietnamese characters render cleanly.

### 6.6. Configuration and Message Bundles

`src/main/resources/application.properties`:

```properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

`src/main/resources/i18n/messages.properties` (base bundle):

```properties
page.title=Welcome
page.description=This page uses Spring Boot and MessageSource.
greeting.user=Hello, {0}!
items.summary=You have {0,number,integer} items.
language.vi=Vietnamese
language.en=English
page.footer=Localization demo
```

`src/main/resources/i18n/messages_en.properties`:

```properties
page.title=Welcome
page.description=This page uses Spring Boot and MessageSource.
greeting.user=Hello, {0}!
items.summary=You have {0,number,integer} items.
language.vi=Vietnamese
language.en=English
```

`src/main/resources/i18n/messages_vi.properties`:

```properties
page.title=Chào mừng
page.description=Trang này dùng Spring Boot và MessageSource.
greeting.user=Xin chào, {0}!
items.summary=Bạn có {0,number,integer} sản phẩm.
language.vi=Tiếng Việt
language.en=Tiếng Anh
```

Both `messages_en.properties` and `messages_vi.properties` intentionally **omit `page.footer`** to demonstrate that a key lacking a translation still falls back to `messages.properties`. In real products, review translations carefully to avoid unintended mixed-language UIs.

Save files as **UTF-8**; do not write `\uXXXX` escapes unless a specific tool requires them. In UTF-8, accented Vietnamese text remains readable in Git.

### 6.7. Thymeleaf Template

File `src/main/resources/templates/home.html`:

```html
<!doctype html>
<html lang="en"
      xmlns:th="http://www.thymeleaf.org"
      th:lang="${#locale.language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title th:text="#{page.title}">Welcome</title>
</head>
<body>
  <main>
    <h1 th:text="#{page.title}">Welcome</h1>
    <p th:text="#{page.description}">
      This page uses Spring Boot and MessageSource.
    </p>

    <p th:text="#{greeting.user(${visitorName})}">
      Hello, visitor!
    </p>
    <p th:text="#{items.summary(${itemCount})}">
      You have items.
    </p>
    <p th:text="#{page.footer}">Localization demo</p>

    <nav aria-label="Language">
      <a th:href="@{/(lang='vi')}" th:text="#{language.vi}">
        Tiếng Việt
      </a>
      <a th:href="@{/(lang='en')}" th:text="#{language.en}">
        English
      </a>
    </nav>
  </main>
</body>
</html>
```

Thymeleaf uses:

- `#{page.title}`: resolves the translation from `MessageSource`.
- `#{greeting.user(${visitorName})}`: resolves a message with one parameter.
- `${visitorName}`: reads a variable from `Model`; **not** a bundle lookup.
- `@{/(lang='vi')}`: generates a context-path-aware URL with query parameter `lang=vi`.
- `th:text`: inserts HTML-escaped text; safer than `th:utext` whenever content may contain user input.
- `th:lang="${#locale.language}"`: sets the active language on the `<html>` element to give browsers and assistive tools proper semantics.

Thymeleaf locates the template automatically under `classpath:/templates/`. Do not add `@ResponseBody` to a handler returning the `"home"` view name.

### 6.8. Running the App and Verifying Output

In the `i18n-demo` directory, with JDK 17+ and Maven installed, run:

```bash
mvn spring-boot:run
```

Open `http://localhost:8080/?lang=vi` in a browser. Within the browser session, the main sections of the page display:

```text
Chào mừng
Trang này dùng Spring Boot và MessageSource.
Xin chào, Lan!
Bạn có 12 sản phẩm.
Localization demo
```

The final line stays in English because `page.footer` exists only in the base bundle. Switching to `http://localhost:8080/?lang=en` displays the heading `Welcome` and greeting `Hello, Lan!`.

Test the API **without a session** using headers:

```bash
curl -s -H "Accept-Language: vi" \
  "http://localhost:8080/api/greeting?name=Lan"
```

Exact body:

```text
Xin chào, Lan!
```

Test English:

```bash
curl -s -H "Accept-Language: en" \
  "http://localhost:8080/api/greeting?name=Lan"
```

Exact body:

```text
Hello, Lan!
```

The commands above send fresh requests without a session cookie storing a chosen locale. To test **persisting the selection across a session**, use a cookie jar:

```bash
curl -s -c cookies.txt "http://localhost:8080/?lang=vi" > /dev/null
curl -s -b cookies.txt "http://localhost:8080/api/greeting?name=Lan"
```

The body is `Xin chào, Lan!`. `cookies.txt` stores the `JSESSIONID` cookie so the second request shares the same HTTP session. If the server restarts without persistent sessions, the selection may be lost.

The commands above use Bash/Linux/macOS syntax. On PowerShell, use `curl.exe`, place multi-line `\` continuations onto a single line, and replace `/dev/null` with `NUL` or omit the redirect.

Package and run the executable JAR:

```bash
mvn clean package
java -jar target/i18n-demo-1.0.0.jar
```

Both `templates/home.html` and `i18n/messages*.properties` are packaged inside the application. Behind a reverse proxy or non-root context path, verify URLs against the actual deployment.

## 7. Resolving Messages in Services, APIs, and Validation

### 7.1. Services or Controllers Without Templates

When returning localized content explicitly:

```java
String text = messages.getMessage(
        "greeting.user",
        new Object[] {"Mai"},
        "Hello, Mai!",
        Locale.forLanguageTag("vi-VN")
);
```

This is an **illustrative snippet inside a class holding a `messages` field**. With the Vietnamese bundle, the resulting string is `Xin chào, Mai!`. Pass `Locale` explicitly across service/API boundaries, especially in asynchronous processing; never assume every worker thread has a request locale attached.

### 7.2. Validation Messages

When using Jakarta Bean Validation with `spring-boot-starter-validation`, messages can live in `messages.properties` and be referenced by key. In a DTO:

```java
@NotBlank(message = "{form.name.required}")
private String name;
```

Bundle files:

```properties
# messages.properties
form.name.required=Name is required.
```

```properties
# messages_vi.properties
form.name.required=Vui lòng nhập tên.
```

This is an **illustrative snippet**, not a standalone DTO. Import `jakarta.validation.constraints.NotBlank` and add the validation starter to compile it. Spring Boot wires the application's `MessageSource` into resolving `{...}` constraint message parameters; Bean Validation then performs its interpolation.

Also distinguish Spring's **binding error codes** (`NotBlank.userForm.name`, `typeMismatch...`, etc.) from **constraint annotation message templates** like `{form.name.required}`. `BindingResult` and `MessageCodesResolver` can generate multiple fallback keys in order. When a template renders form errors, use expressions like `th:errors` to retrieve the locale-resolved message.

### 7.3. API Error Responses: Stable Codes, Translatable Messages

An API should return a stable error code for programmatic handling:

```json
{
  "code": "USER_NOT_FOUND",
  "message": "User not found."
}
```

This is an **illustrative JSON example**, not emitted by the Section 6 controller. `code` should remain language-independent; `message` can be localized via `MessageSource`. Never branch business logic or have clients match exact error conditions on translated strings.

## 8. WebFlux Also Uses MessageSource, With a Different Locale Mechanism

Spring WebFlux supports i18n and `MessageSource`, yet the reactive stack uses `ServerWebExchange` and WebFlux's `LocaleContextResolver`. Do not copy Servlet MVC's `LocaleChangeInterceptor` or `SessionLocaleResolver` into a WebFlux application.

In a **WebFlux controller**, you can read the locale safely from the exchange:

```java
@GetMapping(value = "/reactive-greeting", produces = "text/plain;charset=UTF-8")
public Mono<String> greeting(ServerWebExchange exchange) {
    Locale requested = exchange.getLocaleContext().getLocale();
    Locale locale = requested != null ? requested : Locale.ENGLISH;

    String text = messages.getMessage(
            "greeting.user", new Object[] {"Lan"}, locale);
    return Mono.just(text);
}
```

This is an **illustrative method, not a standalone program**. It assumes the class has a `MessageSource messages` field and imports `Mono`, `ServerWebExchange`, `Locale`, and the mapping annotations. WebFlux typically resolves locale from `Accept-Language` according to HTTP configuration. Stateful language switching must be designed for WebFlux via session/cookie or a custom `LocaleContextResolver` if genuinely required.

**Caution in reactive programming:** `LocaleContextHolder` relies on thread-bound context in many Servlet scenarios and must not be relied upon to preserve the locale across `publishOn`/`subscribeOn` hops or async callbacks. Extract the locale from the request/exchange and pass it explicitly with data or via Reactor `Context` where appropriate.

Thymeleaf works on both stacks when view resolvers are configured properly, though the complete example in Section 6 uses **Spring MVC** to demonstrate session-based locale switching clearly.

## 9. Formatting Numbers, Dates, and Currencies Differs from Translating Text

A common design mistake is stuffing all formatting logic into message bundles:

- `MessageSource` fits UI labels, messages, and parameterized sentences.
- `NumberFormat`, `DateTimeFormatter`, `@NumberFormat`, `@DateTimeFormat`, and Spring's `ConversionService` format data values per locale.
- `ZoneId`/time zone specifies the time zone needed to display an instant accurately.

Standalone Java 17 example (`LocaleFormattingDemo.java`):

```java
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleFormattingDemo {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale en = Locale.forLanguageTag("en-US");

        System.out.println(NumberFormat.getIntegerInstance(vi).format(12345));
        System.out.println(NumberFormat.getIntegerInstance(en).format(12345));
    }
}
```

Run:

```bash
javac LocaleFormattingDemo.java
java LocaleFormattingDemo
```

On a JDK using standard CLDR locale data, stdout is:

```text
12.345
12,345
```

Locale data providers and JDK versions can affect formatting in specialized environments; pin the JDK and locale provider for critical tests. This example demonstrates that the **same number 12345** uses a different grouping separator by language/region.

For prices, **locale formatting does not select the business currency unit**. If a user chooses Vietnamese while paying in USD, preserve `USD` as the currency code and format according to product rules; never infer currency solely from locale.

## 10. Translation Architecture and Conventions for Real Projects

### 10.1. Designing Contextual Keys

Use stable, searchable keys:

```properties
nav.home=Home
auth.login.title=Sign in
auth.login.button=Continue
auth.error.invalid-credentials=Incorrect username or password.
order.summary.total=Total
order.error.not-found=Order was not found.
```

Avoid generic keys like `text1`, `text2`, or using full English sentences as keys, which break down as soon as copy is edited. Group keys by screen, domain, or module. Distinct groups can also live under multiple basenames such as `i18n/messages,i18n/errors`.

### 10.2. One Error Code, Multiple Presentations

Services should emit **error codes + data**, letting the web layer pick the locale and render the message. For example, a service raises `ORDER_NOT_FOUND` with an ID, and the controller maps it to key `order.error.not-found` with arguments. This keeps business logic independent of the active UI language.

### 10.3. Do Not Concatenate Sentences from Small Fragments

Avoid:

```java
String message = labelBefore + quantity + labelAfter;
```

Word order varies across languages. Put the **entire sentence** in the bundle, such as `items.summary=You have {0} items` and `items.summary=Bạn có {0} sản phẩm`. Translators can reorder placeholders without touching Java code.

For complex plurals or grammatical gender, standard `MessageFormat` and basic bundles have limits. Use dedicated pluralization logic or ICU `MessageFormat`; never expect a single `{0}` pattern to handle singular/plural grammar across all languages. For instance, `You have 1 items` is ungrammatical without a singular branch.

### 10.4. UI, HTML, and Accessibility

- Use `th:text` to escape HTML when rendering translated messages containing user data. Use `th:utext` only for reviewed, sanitized HTML.
- Set `lang` on the appropriate HTML element, and handle `dir="rtl"` when supporting right-to-left languages.
- Test longer translated strings, line wrapping, tight buttons, screen readers, and keyboard navigation; localization is more than swapping key values.
- Never treat `Accept-Language` as identity data. Language switching is a UI preference, never an authorization boundary.

### 10.5. Caching, Distribution, and Sessions

An HTML page can return different content depending on `Accept-Language`, cookies, or sessions. If a reverse proxy or CDN caches responses, configure cache rules properly; when language depends on a header and responses are cacheable, consider `Vary: Accept-Language`. When language relies on sessions or cookies, prevent shared caches from accidentally serving one user's language to another.

With `SessionLocaleResolver`, multiple backend instances need sticky sessions or a shared session store if language preference must persist across servers. For stateless frontends/APIs, `Accept-Language` is usually simpler than session locales.

## 11. Common Issues and Fixes

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| No translations appear despite creating `messages_vi.properties` | Missing `messages.properties` prevents Boot auto-config, or wrong basename | Create base bundle; check `spring.messages.basename` and classpath |
| Literal key `page.title` or error marker shown instead of text | Key missing or bundle not found | Check spelling, package, folder, and fallback |
| Vietnamese diacritics look garbled | File not actually UTF-8 or wrong HTTP response charset | Verify editor encoding, `spring.messages.encoding`, and response charset |
| Clicking `?lang=vi` does not switch language | Still using `AcceptHeaderLocaleResolver` or interceptor not registered | Use `SessionLocaleResolver`/`CookieLocaleResolver` and register `LocaleChangeInterceptor` |
| Language changes once, next request reverts | Client did not send session cookie or session expired | Check `JSESSIONID`, session store, and request client behavior |
| `Accept-Language: vi` header has no effect | Session already holds a different locale with higher precedence | Test in a clean session/without cookies; check active resolver |
| `{0}` placeholder appears literally | Arguments not passed properly or pattern not formatted as expected | Check `MessageSource.getMessage`, placeholders, and `MessageFormat` config |
| Apostrophe `'` disappears or mangles output | `MessageFormat` quote-escaping rule | Use `''` in formatted patterns and test with arguments |
| Changing locale still shows wrong time zone | Locale does not change `ZoneId` | Pick time zone separately when formatting dates/times |
| Thymeleaf cannot find `home` | Wrong `templates/home.html` path or missing Thymeleaf starter | Check dependencies, returned view name, and template path |
| Translation works in Java, wrong on page | Template uses literal text or wrong expression | Use `th:text="#{...}"` and check request locale |
| Validation errors on API show raw/wrong-locale text | Error-rendering layer does not use same `MessageSource`/locale | Standardize error codes, message resolution, and response types |
| Production only shows English | Resource bundles not packaged into executable JAR | Inspect `jar tf`, build resource filtering, profile, and packaging |
| CDN cache serves wrong language | Cache key ignores locale or caches personalized HTML | Adjust cache control, `Vary`, and cookie/session policy |

### Ordered Diagnostic Process

1. Confirm the **actual locale** of the request via logs or a temporary controller inspection; do not rely on the OS language.
2. Identify the locale source: `Accept-Language`, session, cookie, or custom resolver.
3. Verify the **basename and actual bundle files on the runtime classpath** in the project/executable JAR.
4. Check the key in both the base and translated bundles, and test `messages.getMessage(code, args, default, locale)` with an explicit locale.
5. Inspect Thymeleaf expressions, HTML/HTTP encoding, and caching; for parameterized messages, check `MessageFormat` escaping.
6. When everything works in the IDE yet fails in production, inspect packaging, sessions/reverse proxies, and request headers/cookies.

Do not "patch" localization by writing `if (locale.getLanguage().equals("vi"))` branches throughout controllers: that bypasses fallback, clutters UI code, and makes scaling translations painful.

## 12. Systematic Localization Testing

### 12.1. Core Test Case Matrix

| Case | Input | What to Verify |
| --- | --- | --- |
| Vietnamese via header | `Accept-Language: vi`, fresh session | `greeting.user` is "Xin chào, Lan!" |
| English via header | `Accept-Language: en` | `greeting.user` is "Hello, Lan!" |
| Regional English | `Accept-Language: en-GB` | Uses `messages_en_GB` if present, then falls back |
| Unsupported locale | `Accept-Language: fr-FR` | Falls back cleanly to base bundle without 500 |
| Key missing in `vi` file | `page.footer` with `vi` locale | Receives `Localization demo` from base bundle |
| Key missing in all bundles | `missing.key` | Uses default or throws `NoSuchMessageException` per overload |
| Query switching language | `/?lang=vi` then follow-up request with same cookie | Session retains the selection |
| Fresh request without cookie | New header or default locale | Does not accidentally retain previous user's locale |
| Argument with special characters | Name `<Lan>` in model | HTML escaped by `th:text` |
| Vietnamese text and numbers | Vietnamese accents, `{0,number,integer}` | UTF-8 renders cleanly and numbers format per locale |

### 12.2. Testing with `curl`

Start the server and test two requests with different languages:

```bash
curl -i -H "Accept-Language: vi" \
  "http://localhost:8080/api/greeting?name=Lan"

curl -i -H "Accept-Language: en" \
  "http://localhost:8080/api/greeting?name=Lan"
```

`-i` prints HTTP headers alongside the body; check `Content-Type` charset and the Vietnamese body. When testing session state, use `-c`/`-b` as in Section 6.8 instead of firing isolated requests and assuming sessions are broken.

In unit tests for message bundles, inject `MessageSource` and invoke it directly with `Locale.forLanguageTag("vi")` to isolate bundle resolution from HTTP/session concerns. In integration tests, send requests with varying headers and cookies, covering missing keys, fallback, and encoding.

### 12.3. Translation Quality Controls

- Check for missing keys or single-language-only keys in CI; document keys that intentionally rely on fallback.
- Ensure placeholders stay compatible across languages for each key: `{0}`, `{1}`, and format types.
- Avoid leaving unintended untranslated words in the UI.
- Verify how browsers, sessions, reverse proxies, and caches interact with locale selection.
- Test UI layouts on small screens, long strings, RTL scripts, and accessibility tools.

## 13. Self-Assessment Questions

1. **Do `MessageSource` and `LocaleResolver` have the same job?** No. The resolver determines the request's locale; `MessageSource` uses that locale to look up messages.
2. **With only `messages_vi.properties` and no `messages.properties`, is Boot guaranteed to auto-configure `MessageSource`?** No. Auto-configuration checks for a base bundle matching the basename.
3. **How does `messages_vi_VN.properties` differ from `messages_vi.properties`?** The first is country-specific; the second applies to Vietnamese generally.
4. **Why doesn't `?lang=vi` work with `AcceptHeaderLocaleResolver`?** That resolver does not support `setLocale`; choose a stateful mechanism like session or cookie.
5. **How do `getMessage(code,args,locale)` and `getMessage(code,args,default,locale)` differ?** The overload with a default returns fallback text when a key is missing; the overload without a default can throw `NoSuchMessageException`.
6. **What syntax is `{0}` in message files?** A `java.text.MessageFormat` placeholder, not Thymeleaf's `${...}`.
7. **Does choosing `vi-VN` automatically identify the user's time zone?** No. Handle `ZoneId`/time zone separately.
8. **Why shouldn't translated strings be used as API error codes?** Translations vary by locale and copy edits; machine-readable codes must remain stable.
9. **Can `MessageSource` be used in WebFlux?** Yes, though the request locale must be obtained via WebFlux mechanisms such as `ServerWebExchange`.
10. **If server-rendered HTML varies by header, what must caching consider?** Prevent mixing responses across locales/users, and consider `Vary: Accept-Language` and proper cache policies.

## 14. Official Documentation and Further Reading

- Spring Boot — [Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html): auto-configuration, base bundles, basenames, and fallback.
- Spring Boot 3.5 — [Common application properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.messages.*`.
- Spring Framework — [`ApplicationContext` and `MessageSource`](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): APIs, `ResourceBundle`, exceptions, and fallback.
- Spring Framework — [Spring MVC Locale Resolver and LocaleChangeInterceptor](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html): `Accept-Language`, session, cookie, and language switching.
- Spring Boot — [Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): using message bundles when resolving Bean Validation messages.
- Thymeleaf — [Tutorial: Thymeleaf + Spring](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): Spring `MessageSource` and template expressions.
- Thymeleaf — [Using Thymeleaf](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html): `#{...}`, `${...}`, `@{...}`, and message parameters.
- Spring Framework — [WebFlux configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): locale/formatting and differences from MVC.

**Key takeaway:** `LocaleResolver` (or the WebFlux locale context) answers **"Which locale is this request using?"**; `MessageSource` answers **"How does this key translate in that locale?"**; Thymeleaf/Controller decides **"Where is that message displayed?"**. Keeping these responsibilities separate makes Spring Boot UIs easy to localize, test, and maintain.