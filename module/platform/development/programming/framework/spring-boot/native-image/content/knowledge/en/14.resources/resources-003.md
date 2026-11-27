# ResourceBundle, Internationalization, and Locale Data

A Spring Boot application may display messages in multiple languages, format dates and numbers by region, or select content based on the user's locale. Java provides **ResourceBundle** to look up messages by language; Spring provides **MessageSource** to integrate messages into the application context. When compiling an application into a GraalVM Native Image, you must understand two distinct groups of data: **resource bundles containing application content** and **JDK locale data containing region-specific formatting rules**.

This lesson explains how to organize multilingual properties files, the fallback mechanism of `ResourceBundle`, integration with Spring Boot, registering resource bundle hints, and adding locale data for the native executable. The goal is to ensure that the same binary can serve the right messages and formatting for the locales the application commits to supporting.

## 1. Locale and ResourceBundle Solve Two Different Problems

A **Locale** describes language and regional conventions, typically consisting of language, country/region, and optionally a script or variant. For example:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi");
Locale vietnameseVietnam = Locale.forLanguageTag("vi-VN");
Locale englishUnitedStates = Locale.forLanguageTag("en-US");
Locale japaneseJapan = Locale.forLanguageTag("ja-JP");
~~~

A `Locale` does not itself contain translated text. It is metadata used by an application or library to choose the appropriate messages and formatting rules.

A **ResourceBundle** is a mechanism for looking up a group of resources by base name and locale. For properties-based bundles, each locale can have its own file:

~~~text
src/main/resources/
└── i18n/
    ├── messages.properties
    ├── messages_en.properties
    ├── messages_en_US.properties
    ├── messages_vi.properties
    ├── messages_vi_VN.properties
    └── messages_ja.properties
~~~

The base bundle name in Java is `i18n.messages`, corresponding to the resource path `i18n/messages.properties`. When requesting locale `vi-VN`, Java searches for a matching bundle across locale variants and falls back to the base bundle when needed.

Distinction:

| Component | Question it answers | Example |
| --- | --- | --- |
| Locale | Which language/region is the user using? | `vi-VN` |
| ResourceBundle | What is the message text for that locale? | `greeting=Xin chào, {0}!` |
| JDK locale data | Which conventions format dates, numbers, and currencies? | `23/11/2026` or `1.234,56` |
| MessageSource | How does a Spring application retrieve messages by code and locale? | `messageSource.getMessage(...)` |

**Key point for Native Image:** registering a message bundle does not automatically include all JDK locale data; conversely, adding JDK locale data does not automatically package translation files provided by the application.

## 2. Organizing ResourceBundle with Properties

Each properties file contains stable keys and language-specific content. For example:

**`src/main/resources/i18n/messages.properties`** — base bundle:

~~~properties
greeting=Hello, {0}!
order.created=Order {0} has been created.
validation.required=This field is required.
~~~

**`messages_en.properties`**:

~~~properties
greeting=Hello, {0}!
order.created=Order {0} has been created.
validation.required=This field is required.
~~~

**`messages_vi.properties`**:

~~~properties
greeting=Xin chào, {0}!
order.created=Đơn hàng {0} đã được tạo.
validation.required=Trường này là bắt buộc.
~~~

**`messages_vi_VN.properties`**:

~~~properties
greeting=Xin chào {0}!
order.created=Đơn hàng {0} đã được tạo tại Việt Nam.
validation.required=Vui lòng nhập trường này.
~~~

**`messages_ja.properties`**:

~~~properties
greeting=こんにちは、{0}さん！
order.created=注文 {0} を作成しました。
validation.required=この項目は必須です。
~~~

In this example, `messages.properties` is the base bundle serving as a fallback when no specific translation exists. `messages_vi.properties` applies to Vietnamese in general; `messages_vi_VN.properties` can override content specifically for Vietnam.

### Keys Should Remain Stable; Only Content Varies by Locale

Do not use full English sentences as keys and try to match translated strings against them. Instead, use business-meaningful keys:

- `greeting`
- `order.created`
- `validation.required`
- `payment.declined`

Keeping the same set of keys across locale files helps avoid missing-translation bugs. For large applications, you can maintain a key-check table via tests or a validation step in CI.

### Encoding

With Java 9 and later, properties files used by `PropertyResourceBundle` default to reading UTF-8 per standard JDK behavior. Spring Boot also allows configuring the encoding of the message source. Save files as UTF-8 and declare it explicitly:

~~~properties
spring.messages.encoding=UTF-8
~~~

If supporting older JDKs or other properties-processing tools, verify encoding end-to-end; do not convert non-ASCII content into escape sequences just to work around editor encoding issues.

## 3. How ResourceBundle Finds Bundles and Falls Back Across Locales

Call:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "i18n.messages",
        Locale.forLanguageTag("vi-VN")
);

String greeting = bundle.getString("greeting");
System.out.println(greeting);
~~~

Java uses the base name `i18n.messages` and the requested locale to locate a matching bundle. For the properties files in the example, the typical candidate order for `vi-VN` is:

~~~text
i18n/messages_vi_VN.properties
i18n/messages_vi.properties
i18n/messages.properties
~~~

If no bundle matches the requested locale, the `ResourceBundle` mechanism may also try falling back to the **JVM's default locale** before reverting to the base bundle. This behavior can make results depend on machine/container configuration if the application does not explicitly determine the locale and fallback policy.

For example, if the machine running the native binary has a default locale of `en-US` while the test machine has `vi-VN`, a key missing from the Vietnamese bundle may resolve to different content depending on the default locale and available bundles.

### Design a Clear Fallback Policy

- Provide the base bundle `messages.properties` as the final fallback.
- Only include bundles for locales the product actually supports.
- Verify that critical keys exist in every required bundle.
- Do not rely on the host's default locale to select the user's language.
- If consistent behavior is required, configure Spring `MessageSource`'s fallback policy or use a `ResourceBundle` invocation suited to your requirements.

In Spring Boot, you can set:

~~~properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

`fallback-to-system-locale=false` prevents the Spring message source from trying the operating system's default language as a fallback step between the requested locale and the base bundle. Verify the exact property name for your project's Spring Boot version.

## 4. Using ResourceBundle Directly in Java

A small service can accept an explicit locale and look up messages:

~~~java
package com.example.nativeimage;

import java.util.Locale;
import java.util.ResourceBundle;

public final class GreetingCatalog {

    public String greeting(String name, Locale locale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("i18n.messages", locale);
        return bundle.getString("greeting").replace("{0}", name);
    }
}
~~~

To format complex parameters, dates, or numbers, do not replace strings manually. You can use `MessageFormat` with a locale:

~~~java
package com.example.nativeimage;

import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public final class GreetingCatalog {

    public String greeting(String name, Locale locale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("i18n.messages", locale);

        String pattern = bundle.getString("greeting");
        MessageFormat formatter = new MessageFormat(pattern, locale);

        return formatter.format(new Object[] { name });
    }
}
~~~

`MessageFormat` uses the locale to interpret formatting elements in the pattern. If a message includes dates, numbers, or currency, test the output against target locales and do not concatenate formatted strings manually.

In a web application, the locale should be determined from an explicit source, such as the `Accept-Language` header, saved user preferences, or business configuration. Do not accept an arbitrary locale string and assume it is valid or supported; parse, validate, and apply a fallback policy.

## 5. Integrating ResourceBundle with Spring MessageSource

Spring provides `MessageSource` so beans can retrieve messages by message code, arguments, and locale. Spring Boot can auto-configure a message source when it finds a matching bundle basename.

Configuration:

~~~properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Service using `MessageSource`:

~~~java
package com.example.nativeimage;

import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final MessageSource messageSource;

    public GreetingService(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String greeting(String name, Locale locale) {
        return messageSource.getMessage(
                "greeting",
                new Object[] { name },
                locale
        );
    }
}
~~~

A controller can receive the locale that Spring MVC resolves from the request:

~~~java
package com.example.nativeimage;

import java.util.Locale;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(defaultValue = "friend") String name,
            Locale locale) {
        return greetingService.greeting(name, locale);
    }
}
~~~

With the default header-based MVC configuration, a client can send:

~~~http
GET /greeting?name=Lan HTTP/1.1
Accept-Language: vi-VN
~~~

The application returns the message from the matching bundle. The locale resolver mechanism can be customized; if the product stores language in a user profile or cookie, configure the corresponding resolver and test it separately.

### ResourceBundleMessageSource and Resource-Based Message Sources

Distinguish how Spring loads messages:

- `ResourceBundleMessageSource` uses the `java.util.ResourceBundle` mechanism and a base name. This is the case directly related to resource bundle hints.
- `ReloadableResourceBundleMessageSource` loads properties through Spring's resource abstraction and has its own reload/caching behavior. With this approach, check the resource patterns/hints needed for the properties paths.
- `MessageSource` is the interface that services use; do not assume every implementation uses the same resource loading mechanism.

Spring Boot auto-configuration and libraries may contribute hints for some cases. Verify against your actual Spring Boot version and message source; add hints for custom bundles when they are not already registered by the framework or libraries.

## 6. Registering ResourceBundleHints for GraalVM Native Image

GraalVM Native Image needs to know which resource bundles must be packaged. Spring provides an API in `RuntimeHints`:

~~~java
hints.resources().registerResourceBundle("i18n.messages");
~~~

The name passed in is the bundle **base name**, not an individual properties file name and without the `.properties` extension.

You can create a registrar:

~~~java
package com.example.nativeimage;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class MessageBundleHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerResourceBundle("i18n.messages");
    }
}
~~~

Register the registrar with the Spring context:

~~~java
package com.example.nativeimage;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(MessageBundleHints.class)
public class NativeMessageConfiguration {
}
~~~

When Spring AOT analyzes the configuration, the registrar contributes the hint for the `i18n.messages` bundle. Native Image can then include the bundle's locale variants in the binary according to the metadata received by the build tool.

If the application has multiple base names:

~~~java
@Override
public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
    hints.resources().registerResourceBundle("i18n.messages");
    hints.resources().registerResourceBundle("i18n.validation");
    hints.resources().registerResourceBundle("i18n.notifications");
}
~~~

Register the exact base names the application actually uses. There is no need to create a hint for each locale file when the API takes the bundle's base name.

### When to Use registerPattern Instead of registerResourceBundle?

The two APIs serve different kinds of resources:

| API | Target | Example |
| --- | --- | --- |
| `registerResourceBundle("i18n.messages")` | Bundles loaded via the Java `ResourceBundle` mechanism | `i18n/messages_vi.properties` |
| `registerPattern("templates/.*")` | Resource files read by path | HTML templates on the classpath |
| `registerPattern("rules/.*\\.json")` | Static set of JSON files | JSON rules/configuration |
| Reflection hints | Dynamic class/member access | DTOs accessed via reflection |

Registering a broad resource pattern is not a good replacement for a resource bundle hint if the application calls `ResourceBundle.getBundle`. Choose the API that matches the actual mechanism.

## 7. JDK Locale Data in Native Image

In addition to application-provided messages, the JDK contains locale data for APIs such as:

- `NumberFormat` and `DecimalFormat` for formatting numbers.
- `DateFormat`, `DateTimeFormatter`, and `Calendar` for formatting dates and times.
- `Currency` for representing currencies.
- `Collator` for comparing/sorting strings according to language rules.
- APIs related to symbols, month names, days of the week, and regional rules.

Native Image may not include all JDK locale data by default. Depending on the GraalVM version, you need to specify the supported locales via the appropriate option, usually `-H:IncludeLocales`.

For example, to include Vietnamese and English locale data in the native executable:

~~~text
-H:IncludeLocales=vi,en
~~~

This is an example for Native Image versions that support this option. Exact syntax and the supported locale list depend on the GraalVM release; verify with the help/options of your exact toolchain before adding it to a pipeline.

### Configuring with Maven Native Build Tools

In the `native-maven-plugin` configuration, you can pass a build argument:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-H:IncludeLocales=vi,en</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

If the project already has a plugin configuration, add the build argument to the existing configuration rather than declaring a duplicate plugin. Check the `native-image` log to confirm the argument is passed to the compiler.

### Configuring with Gradle Native Build Tools

Groovy DSL example:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-H:IncludeLocales=vi,en")
        }
    }
}
~~~

Binary names and DSL details may vary by plugin version; check the Gradle Native Build Tools version in use and the compile task logs. If the project uses Kotlin DSL, translate the configuration to the plugin's typed API.

**Note:** `-H:IncludeLocales` adds JDK locale data; it does not replace `hints.resources().registerResourceBundle(...)` for application message bundles. Conversely, `ResourceBundleHints` does not guarantee that date/number formatting APIs have the required locale data.

## 8. Formatting Numbers, Currency, and Dates by Locale

When an application displays data, the same value can be presented differently depending on the locale:

~~~java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public class LocaleFormattingExample {

    public static void main(String[] args) {
        Locale vietnam = Locale.forLanguageTag("vi-VN");
        Locale us = Locale.forLanguageTag("en-US");

        NumberFormat vietnamNumber = NumberFormat.getNumberInstance(vietnam);
        NumberFormat usNumber = NumberFormat.getNumberInstance(us);

        NumberFormat vietnamCurrency =
                NumberFormat.getCurrencyInstance(vietnam);
        vietnamCurrency.setCurrency(Currency.getInstance("VND"));

        DateTimeFormatter vietnamDate =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(vietnam);

        LocalDate date = LocalDate.of(2026, 11, 23);

        System.out.println("vi number=" + vietnamNumber.format(1234567.89));
        System.out.println("en number=" + usNumber.format(1234567.89));
        System.out.println("vi currency=" + vietnamCurrency.format(125000));
        System.out.println("vi date=" + vietnamDate.format(date));
    }
}
~~~

Do not hardcode formatted string results in tests if JDK/CLDR versions can change separators, whitespace, or currency symbols. Instead:

- Verify that the right locale is being used.
- Verify the formatting style and currency code.
- Record the JDK/GraalVM version when snapshotting display outputs.
- If the product requires exact formatting by contract, use test fixtures aligned with the version and upgrade policy.

With a native executable, run the same code on the binary and compare against the JVM on the same toolchain. If a locale is not included, APIs may fall back or use reduced data depending on the version; do not assume everything works just because the message bundle renders correctly.

## 9. Determining Input Locale and Stable Fallback

A server application typically serves multiple users simultaneously. Avoid changing the global default locale per request with `Locale.setDefault(...)`; this can affect other threads and the entire process.

Instead, pass the locale per request or context:

~~~java
public String messageFor(String code, Object[] args, Locale locale) {
    return messageSource.getMessage(code, args, locale);
}
~~~

Common locale sources:

| Source | Advantage | What to control |
| --- | --- | --- |
| `Accept-Language` | HTTP standard; client sends preference automatically | Header parsing, quality priority, and unsupported locales |
| User profile | Preserves language choice across sessions | Value validation and precedence over headers |
| Cookie/session | Useful for web UIs | Expiration, privacy, and fallback |
| Server configuration | Used for background jobs or system notifications | Do not use as a shared locale for all requests |

Define a clear precedence order, such as user preference → `Accept-Language` → product default locale. Normalize locales using BCP 47 language tags like `vi-VN`, `en-US`; do not concatenate locale strings in arbitrary formats.

### Recommended Fallback Policy

Suppose the product supports `vi` and `en`:

1. If the user selects `vi-VN`, use the `vi_VN` bundle if present.
2. If not present, use `vi`.
3. If the key is still missing, use the base bundle or a defined fallback message.
4. If the locale is unsupported, switch to the product default locale (for example `en`).
5. Catch missing message keys in tests/CI rather than letting errors surface only in production.

Do not use the build machine's language as a fallback for users. The default locale should be a testable product decision, not an accidental side effect of the container image.

## 10. Testing ResourceBundle and Locales on Native Image

A passing JVM test only proves the current JVM classpath/runtime can read the bundle. You must test the native executable after AOT and Native Image compilation complete.

### Testing ResourceBundle Directly

~~~java
@Test
void loadsVietnameseBundle() {
    Locale locale = Locale.forLanguageTag("vi-VN");

    ResourceBundle bundle =
            ResourceBundle.getBundle("i18n.messages", locale);

    assertEquals("Xin chào, Lan!", 
            new MessageFormat(bundle.getString("greeting"), locale)
                    .format(new Object[] { "Lan" }));
}
~~~

This test assumes `messages_vi.properties` contains the pattern `Xin chào, {0}!`. If `messages_vi_VN.properties` defines this key, it will take precedence. Verify results against the project's actual bundle files and fallback policy.

### Testing Spring MessageSource

~~~java
@SpringBootTest
class GreetingMessageTests {

    @Autowired
    MessageSource messageSource;

    @Test
    void resolvesVietnameseMessage() {
        String message = messageSource.getMessage(
                "greeting",
                new Object[] { "Lan" },
                Locale.forLanguageTag("vi-VN")
        );

        assertEquals("Xin chào, Lan!", message);
    }
}
~~~

This test verifies Spring message source integration, basename, and locale. If the base bundle has different content, use an expected value matching the chosen fixture.

### Testing on the Native Executable

At minimum, cover these scenarios:

| Scenario | What to verify |
| --- | --- |
| Base bundle | Native finds the base bundle |
| Locale `vi` | Vietnamese content is selected |
| Locale `vi-VN` | Regional bundle takes precedence if present |
| Locale `en-US` | English content is accurate |
| Missing key | Fallback follows policy |
| Unsupported locale | Falls back to the defined default locale |
| MessageFormat | Arguments are substituted properly |
| Number/date formatting | JDK locale data is present in the native image |
| HTTP Accept-Language | Locale resolver passes the right locale to `MessageSource` |

Include critical tests in native integration tests or launch the executable and call the endpoints. JVM tests alone do not prove the resource bundle was packaged into the native image.

## 11. Diagnosing Common Errors

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| JVM finds bundle, native reports missing bundle | Missing resource bundle metadata or hint not discovered by AOT | Check base name and registrar; verify native build receives hints |
| Always returns base bundle content | No matching locale file, wrong filename, or incorrect input locale | Check `messages_vi.properties`, base name, and locale tag |
| Outputs Vietnamese on dev machine, English in container | Default locale/fallback depends on environment | Pass locale explicitly and configure `fallback-to-system-locale` |
| Messages display right, dates/numbers use wrong locale | Bundle present, but JDK locale data not included in native | Check `-H:IncludeLocales` and GraalVM version |
| Resource pattern fails to resolve bundle | Wrong metadata type registered | Use `registerResourceBundle` for `ResourceBundle`; use patterns for resource paths |
| Spring `MessageSource` cannot find message | Wrong basename, missing base bundle, or nonexistent key | Check `spring.messages.basename`, files, and message code |
| Corrupted Vietnamese diacritics | Inconsistent encoding | Save properties as UTF-8 and check encoding at build/runtime |
| Native build reports invalid locale option | Option differs by GraalVM version or unsupported locale | Check `native-image` help and toolchain release notes |
| JVM test passes, native fails | Test not run on native or hints not included in binary | Add native integration test and rebuild after fixing hints |

### Investigation Workflow

1. Determine whether the code uses `ResourceBundle` directly or Spring `MessageSource`.
2. Identify the base name, locale tag, and exact expected bundle file.
3. Verify the base bundle and locale files exist in the build's resources.
4. Verify `registerResourceBundle` is registered and the registrar is discovered by Spring AOT.
5. If the issue involves date/number formatting, check locale data and build arguments separately.
6. Rebuild the native executable and run with the exact payload/locale causing the error.
7. Check the fallback policy to rule out interference from the host's default locale.

## 12. Hands-On Exercise: Supporting Vietnamese and English in a Native Executable

Create a Spring Boot application with a `GET /greeting` endpoint returning messages based on `Accept-Language`. Prepare:

- `i18n/messages.properties`: base bundle.
- `i18n/messages_vi.properties`: Vietnamese.
- `i18n/messages_en.properties`: English.
- A service using `MessageSource`.
- A configuration registering a `RuntimeHintsRegistrar` for the `i18n.messages` base name.
- Native build configuration to include `vi,en` locale data in the binary if the application uses corresponding date/number formatting APIs.

Steps:

1. Run the application on the JVM and send requests with `Accept-Language: vi-VN`, `en-US`.
2. Check message codes, parameters, and fallback when keys are missing.
3. Build the native executable with Maven or Gradle configured for Spring AOT.
4. Send the same requests to the native build and compare content and HTTP status.
5. Call an additional endpoint testing number/date formatting with `NumberFormat` and `DateTimeFormatter`.
6. Try running a container with a different default locale than the dev machine; verify responses still follow the request locale.
7. Disable or remove the hint on a test branch to observe how resource bundle errors appear; then restore the proper configuration and rebuild.
8. Record the Spring Boot and GraalVM versions, locale list, bundle base names, and native test results.

### Self-Check Questions

1. How does a `Locale` differ from a `ResourceBundle`?
2. Why is the base bundle `messages.properties` necessary?
3. How does `ResourceBundleHints` differ from resource pattern hints?
4. Why does registering `i18n.messages` not guarantee that `NumberFormat` has Vietnamese data?
5. What problem does `-H:IncludeLocales=vi,en` solve?
6. Why shouldn't the container's default locale be used as the user's language?
7. If an application only uses Spring `MessageSource`, why do you need to identify the message source implementation before choosing hints?
8. How can you prove that bundles and locale data actually work in the native executable?

**Pass criteria:** able to organize `ResourceBundle` by base name and locale; explain candidate lookup/fallback; integrate `MessageSource` with Spring Boot; register resource bundles with `RuntimeHints`; distinguish message bundles from JDK locale data; configure required locales for Native Image; and test multilingual messages and date/number formatting directly on the native executable.
