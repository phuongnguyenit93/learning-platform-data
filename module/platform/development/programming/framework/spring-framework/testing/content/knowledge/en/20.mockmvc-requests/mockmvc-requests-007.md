# Locale and Testing Localized Messages

In a Spring MVC application, the same request may need to return messages in multiple languages. For example, `/api/greeting` returns `Hello` when the user chooses English and `Bonjour` when the request uses French. When testing with MockMvc, verify both steps: that Spring selects the right locale for the request and that `MessageSource` resolves the right translation for that locale.

A locale represents language and regional conventions, such as `fr`, `fr-CA`, or `en-US`. It affects resource bundle selection, number/date formatting, and message content. Locale is not synonymous with timezone; a user may use the `en-GB` locale while in a timezone in another region.

## Locale Resolution Flow in Spring MVC

A localized request typically passes through the following steps:

1. The request carries preferred language information, usually via the HTTP `Accept-Language` header, or a locale already stored in the session or a cookie.
2. `DispatcherServlet` uses the application's `LocaleResolver` to determine the locale for the request.
3. Spring binds the locale context to the current request; `LocaleContextHolder` lets code executing within the request retrieve that locale.
4. The controller or service passes the locale to `MessageSource` to retrieve the appropriate message.
5. The controller returns the localized result; MockMvc inspects the response content.

These two components have distinct responsibilities:

| Component | Responsibility |
|---|---|
| `LocaleResolver` | Determines the locale used for the request and, depending on the implementation, may persist locale changes |
| `MessageSource` | Resolves message text by message code, arguments, and locale |

If the resolver picks the wrong locale, `MessageSource` may work properly yet still return an unintended translation. Conversely, the resolver may pick the right locale, but the resource bundle may lack the corresponding key. Therefore, tests should verify the final response rather than testing only one of the two components.

## Preparing Resource Bundles

Spring commonly uses properties files as resource bundles. Suppose the application has files in `src/main/resources/i18n/`:

`messages.properties`:

```properties
greeting.message=Hello
greeting.welcome=Welcome, {0}.
product.name.required=Product name is required.
```

`messages_fr.properties`:

```properties
greeting.message=Bonjour
greeting.welcome=Bienvenue, {0}.
product.name.required=Le nom du produit est obligatoire.
```

`messages_fr_CA.properties`:

```properties
greeting.message=Allô
greeting.welcome=Bienvenue, {0}.
```

The filenames represent locales: `messages_fr.properties` is for French in general, while `messages_fr_CA.properties` is for Canadian French. When the locale is `fr-CA`, the more specific resource bundle can be selected first; if a key does not exist in the specific bundle, resource bundle fallback can look up the key in the parent language bundle and then the default bundle.

`MessageSource` supports parameters using `MessageFormat` syntax. For example, `greeting.welcome=Welcome, {0}.` allows passing the user's name when resolving the message. Translations must preserve the correct count and order of placeholders to avoid displaying garbled data.

### Configuring MessageSource in Spring Boot

Spring Boot can auto-configure `MessageSource` from properties:

```properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Provide `messages.properties` as the default bundle so Boot's message source auto-configuration is activated. Setting `fallback-to-system-locale=false` prevents test outcomes from depending on the locale of the machine running the tests. Without disabling this fallback, environments with different system locales can change which bundle is chosen when a specific translation is not found.

### Configuring MessageSource in Plain Spring MVC

For applications not using Spring Boot, register a bean named `messageSource`:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.ResourceBundleMessageSource;

@Configuration
class MessageConfig {

    @Bean
    MessageSource messageSource() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();
        source.setBasename("i18n/messages");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);
        return source;
    }
}
```

The bean name `messageSource` has special meaning in the ApplicationContext: Spring uses this bean as the default message source. When changing the basename, ensure the path corresponds to the resource location on the classpath and do not append the `.properties` extension to the basename.

## Selecting Locale via Accept-Language

For stateless applications, a common approach is using `AcceptHeaderLocaleResolver`. This resolver reads the request's preferred locales, supplied by the servlet container based on the `Accept-Language` header. Supported locales and a default locale can be configured:

```java
import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration
class WebLocaleConfig {

    @Bean
    LocaleResolver localeResolver() {
        AcceptHeaderLocaleResolver resolver =
                new AcceptHeaderLocaleResolver();
        resolver.setDefaultLocale(Locale.ENGLISH);
        resolver.setSupportedLocales(List.of(
                Locale.ENGLISH,
                Locale.FRENCH,
                Locale.CANADA_FRENCH
        ));
        return resolver;
    }
}
```

Spring MVC looks up the resolver by the bean name `localeResolver`. If no custom resolver is declared, `DispatcherServlet`'s default strategy is `AcceptHeaderLocaleResolver`. When deterministic test behavior is needed, explicitly declare the resolver, supported locales, and default locale.

`AcceptHeaderLocaleResolver` does not support changing the locale by calling `setLocale`, because the header is client-sent information. If the application needs to let users switch languages via a parameter such as `?lang=fr` and persist that choice for subsequent requests, use a stateful resolver such as `SessionLocaleResolver` or `CookieLocaleResolver`.

### Retrieving Locale in a Controller or Service

`DispatcherServlet` sets up the locale context while processing the request. Code can read the current locale using `LocaleContextHolder`:

```java
import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    private final MessageSource messages;

    GreetingController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/api/greeting")
    GreetingResponse greeting() {
        Locale locale = LocaleContextHolder.getLocale();
        String message = messages.getMessage(
                "greeting.message", null, locale);
        return new GreetingResponse(message);
    }
}

record GreetingResponse(String message) {}
```

`LocaleContextHolder` uses the context bound to the current request when processed by Spring MVC. Do not manually set a locale on the static holder in a test and forget to restore it, because that value could leak into other tests or requests on the same thread. Let `DispatcherServlet` establish and clear the locale context according to the request lifecycle.

## Testing Locales with MockMvc

When using MockMvc, the `.locale(...)` method on the request builder sets the preferred locales of the mock servlet request. This is a reliable way to simulate the locale that `HttpServletRequest#getLocale()` provides to `AcceptHeaderLocaleResolver`.

The following example uses a Spring Boot application context and builds MockMvc directly from `WebApplicationContext`:

```java
import java.util.Locale;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringBootTest
class GreetingLocaleMvcTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = webAppContextSetup(webApplicationContext).build();
    }

    @Test
    void returnsFrenchMessage() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .locale(Locale.FRENCH)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Bonjour"));
    }

    @Test
    void returnsCanadianFrenchMessage() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .locale(Locale.CANADA_FRENCH))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Allô"));
    }

    @Test
    void usesDefaultLocaleForUnsupportedLanguage() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .locale(Locale.JAPANESE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello"));
    }
}
```

The assertions verify the final returned message. The third test confirms behavior when the locale is not in the supported list: the resolver falls back to the configured default locale of English.

`.locale(Locale.FRENCH)` sets the preferred locale at the mock servlet request layer; it is not a test of a servlet container's HTTP parser for the raw header string, including `q` weights. If you need to verify how the container actually interprets `Accept-Language` over HTTP, add tests running the application on a real server. For MVC testing via MockMvc, `.locale(...)` is the direct way to verify how Spring handles a locale already resolved by the servlet request.

## Testing Parameters in Messages

Messages often contain placeholders to insert names, quantities, or business values. The controller can pass arguments to `MessageSource`:

```java
@GetMapping("/api/greeting/{name}")
GreetingResponse greeting(@PathVariable String name) {
    Locale locale = LocaleContextHolder.getLocale();
    String message = messages.getMessage(
            "greeting.welcome", new Object[]{name}, locale);
    return new GreetingResponse(message);
}
```

MockMvc verifies both the translation and the substituted parameter:

```java
mockMvc.perform(get("/api/greeting/{name}", "Mai")
                .locale(Locale.FRENCH))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.message")
                .value("Bienvenue, Mai."));
```

Use deterministic usernames or test values so assertions do not depend on external data. When a translation uses single quotes or `MessageFormat` syntax, check `MessageFormat` escaping rules; an unescaped single quote can alter how placeholders are interpreted.

## Changing Locale with Session and LocaleChangeInterceptor

Some applications allow users to choose a language from the UI. In that case, `LocaleChangeInterceptor` can read a request parameter and ask `LocaleResolver` to update the locale. `SessionLocaleResolver` stores the selection in the HTTP session so subsequent requests continue using that locale.

```java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration
class SessionLocaleConfig implements WebMvcConfigurer {

    @Bean
    LocaleResolver localeResolver() {
        SessionLocaleResolver resolver = new SessionLocaleResolver();
        resolver.setDefaultLocale(Locale.ENGLISH);
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
```

In this configuration, a request with `?lang=fr` requests switching to French. `LocaleChangeInterceptor` calls `setLocale` on the resolver. Because the resolver is `SessionLocaleResolver`, the choice is saved in the session. Do not use this configuration with `AcceptHeaderLocaleResolver`, because a header-based resolver cannot override the client-sent locale.

MockMvc can test locale persistence across two requests sharing the same `MockHttpSession`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void keepsSelectedLocaleInSession() throws Exception {
    MockHttpSession session = new MockHttpSession();

    // First request asks to change locale and stores the selection in the session.
    mockMvc.perform(get("/api/greeting")
                    .param("lang", "fr")
                    .session(session))
            .andExpect(status().isOk());

    // Next request uses the same session and therefore receives the French locale.
    mockMvc.perform(get("/api/greeting").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Bonjour"));
}
```

What must be preserved in the test is that the same session object is attached to both requests. If a new session is created for the second request, the test no longer verifies session-based locale persistence. Also verify the locale on the subsequent request, since that is clear proof the resolver stored the choice and reused it.

`CookieLocaleResolver` is another option when you want to store the locale selection in a cookie instead of the session. With this resolver, the test needs to send the cookie received from the previous response on the next request, and verify cookie attributes if that is part of the application contract.

## Testing Localized Validation Messages

Validation messages also need the right locale. For example, a DTO declares a message code instead of hardcoding an English sentence:

```java
import jakarta.validation.constraints.NotBlank;

class CreateProductRequest {

    @NotBlank(message = "{product.name.required}")
    private String name;

    // Constructor, getter, and setter as required by the application.
}
```

When using plain Spring MVC, you can configure `LocalValidatorFactoryBean` to resolve messages from the same `MessageSource`:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ValidationMessageConfig implements WebMvcConfigurer {

    private final LocalValidatorFactoryBean validator;

    ValidationMessageConfig(MessageSource messageSource) {
        validator = new LocalValidatorFactoryBean();
        validator.setValidationMessageSource(messageSource);
    }

    @Bean
    LocalValidatorFactoryBean applicationValidator() {
        return validator;
    }

    @Override
    public Validator getValidator() {
        return validator;
    }
}
```

In Spring Boot, validation is usually auto-configured when a validation provider is on the classpath. If you want to ensure Bean Validation message codes resolve from the application bundle, configure the integration of `LocalValidatorFactoryBean` with `MessageSource` according to the project's validator setup.

A controller can accept the DTO with `@Valid` and convert validation errors into a response via `@RestControllerAdvice`. For instance, the error response has a `message` field containing the localized text. The test sends an invalid request with the French locale:

```java
mockMvc.perform(post("/api/products")
                .locale(Locale.FRENCH)
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":""}
                        """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.message")
                .value("Le nom du produit est obligatoire."));
```

This assertion assumes the application's exception handler returns errors in a JSON structure with a `message` field. If the application returns a list of field errors, assert against the appropriate JSON path, such as `$.errors[0].message`. The key is verifying the actual message text received by the client.

## Locale Affects Data Formatting

Messages are not the only localized output. Some APIs or HTML pages format numbers, currencies, and dates according to locale. For example, decimal numbers may use a comma in the French locale and a dot in the English locale. When the application intentionally formats values by locale, test the output at the response boundary:

```java
NumberFormat formatter = NumberFormat.getNumberInstance(locale);
String formatted = formatter.format(1234.5);
```

Do not assume every client wants pre-formatted numbers in JSON. For APIs, JSON numeric fields should usually remain raw numbers so the client formats them; test formatted strings only when that is an intentional response contract of the application. For HTML or text messages, locale-based formatting is more common.

Locale also does not change timezone automatically. If a message includes a timestamp, explicitly specify which timezone the application uses and test timezone separately from locale. Avoid letting tests depend on the machine's default timezone.

## Common Errors When Testing Locales

| Symptom | Possible cause | How to resolve |
|---|---|---|
| French request still returns English message | Resolver did not receive the expected locale or locale is not in supported list | Check `LocaleResolver`, supported locales list, and `.locale(...)` on the request builder |
| Right locale, but message is not translated | Missing bundle file or mismatched message code | Check basename, filenames, and message keys |
| Tests differ between local machine and CI | Fallback to system locale or default timezone | Configure explicit fallback and set test timezone intentionally |
| Message parameter does not render properly | `MessageFormat` placeholder or argument mismatch | Check `{0}`, `{1}`, and single-quote escaping |
| `LocaleChangeInterceptor` throws an error when switching locale | Currently using `AcceptHeaderLocaleResolver` | Choose `SessionLocaleResolver`, `CookieLocaleResolver`, or a resolver supporting `setLocale` |
| Second request reverts to default locale | Test created a new session or did not resend the cookie | Reuse the same `MockHttpSession` or send the cookie from the prior request |
| Validation always shows the default message | Validator is not integrated with `MessageSource` or message code does not exist | Configure `LocalValidatorFactoryBean` and the validation bundle |
| Test manually setting `LocaleContextHolder` affects other tests | Locale context was not restored | Let `DispatcherServlet` manage the context during MockMvc requests |

## Organizing the Test Suite

Organize tests by locale selection mechanism and by the localized outputs being protected:

- For `AcceptHeaderLocaleResolver`, test supported locales, region-specific locales, and the default locale when the request sends an unsupported language.
- For `SessionLocaleResolver` or `CookieLocaleResolver`, test that the selection is persisted and reused on subsequent requests.
- For `MessageSource`, test key message codes, parameter substitution, and bundle fallback.
- For validation or exception handlers, send invalid requests and confirm the response contains messages in the expected language.
- For formatted dates, times, and numbers, verify locale and timezone according to the application's display contract.

A good MockMvc test runs through `DispatcherServlet` with the application context's locale and message source configuration, sends a request with a specific locale, and verifies the response content the user actually receives. This approach catches both locale-resolution bugs and translation-lookup bugs within the same MVC processing flow.
