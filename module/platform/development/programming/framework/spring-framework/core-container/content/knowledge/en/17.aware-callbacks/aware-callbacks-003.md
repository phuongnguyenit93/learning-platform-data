# EnvironmentAware, ResourceLoaderAware, and MessageSourceAware in Spring Framework Core Container

## 1. What Are Aware Callbacks and When Are They Used?

The Spring IoC Container normally passes dependencies to a bean via constructor injection, setter injection, or `@Bean` declarations. Beyond business dependencies, an **infrastructure** component sometimes needs to know the runtime environment, open a resource whose path is determined at runtime, or look up messages in the user's language. Spring supports a group of callback interfaces suffixed with **Aware** so the container can actively supply the corresponding framework objects.

The three interfaces in this lesson:

| Interface | Callback method | Spring-provided object | Purpose |
| --- | --- | --- | --- |
| `EnvironmentAware` | `void setEnvironment(Environment environment)` | `org.springframework.core.env.Environment` | Read properties, active/default profiles, check profiles |
| `ResourceLoaderAware` | `void setResourceLoader(ResourceLoader resourceLoader)` | `org.springframework.core.io.ResourceLoader` | Resolve URIs/paths into `Resource` (classpath, file, URL…) |
| `MessageSourceAware` | `void setMessageSource(MessageSource messageSource)` | `org.springframework.context.MessageSource` | Look up messages, parameters, and locales (i18n) |

All three interfaces belong to package `org.springframework.context` and extend the marker interface `org.springframework.beans.factory.Aware`. The `Aware` marker **contains no logic itself**: a Spring container together with an appropriate processor must recognize and invoke the callbacks. Objects instantiated with `new` do not have these methods called automatically by Spring.

Conceptual example:

```text
Spring ApplicationContext creates bean InfrastructureReporter
    |
    +-- constructor / @Bean factory method
    +-- inject regular dependencies/properties
    |
    +-- setEnvironment(context.getEnvironment())
    +-- setResourceLoader(context)
    +-- setMessageSource(context)
    |     (context itself implements ResourceLoader and MessageSource)
    |
    +-- @PostConstruct (if present)
    +-- InitializingBean.afterPropertiesSet() (if present)
    +-- custom init-method (if present)
    |
    +-- bean ready for use
```

When running in a standard `ApplicationContext`, the three callbacks are executed **after populating bean properties** and **before initialization callbacks**. They do not mean the context has finished the entire `refresh()`, do not prove all other singletons have finished creation, and do not replace dependency injection for general services.

**Design rule:** Aware is very useful for adapters, registrars, loaders, message resolvers, or framework components; in business services, prefer passing the specific `Environment`, `ResourceLoader`, `MessageSource`, or required values through the constructor to make dependencies explicit and simplify unit testing.

## 2. How Spring Invokes Aware Callbacks and Exact Timing

In a Spring `ApplicationContext`, `ApplicationContextAwareProcessor` participates in `BeanPostProcessor.postProcessBeforeInitialization` to handle multiple context-level Aware interfaces, including the three covered here. It retrieves the current context's infrastructure objects and invokes the bean's setter callbacks.

Typical lifecycle of a normal bean:

```text
1. Parse bean definition
2. Select constructor/factory method and create instance
3. Population: @Autowired, @Value, setters, property values...
4. BeanFactory Aware callbacks such as BeanNameAware/BeanFactoryAware
5. BeanPostProcessor before initialization
     - ApplicationContextAwareProcessor handles:
       EnvironmentAware
       EmbeddedValueResolverAware (if present)
       ResourceLoaderAware
       ApplicationEventPublisherAware (if present)
       MessageSourceAware
       ApplicationContextAware (if present)
     - CommonAnnotationBeanPostProcessor may handle @PostConstruct
6. InitializingBean.afterPropertiesSet()
7. custom init method (@Bean(initMethod = "..."))
8. BeanPostProcessor after initialization (may create proxy)
9. Bean is initialized and can be supplied to consumers
```

For this trio on the same bean in Spring `ApplicationContextAwareProcessor`'s standard path, the invocation order is **`setEnvironment` → `setResourceLoader` → `setMessageSource`** (the processor may invoke other interfaces in between if the bean implements them). Do not generalize this order into a universal rule for all custom `BeanPostProcessor`s: processor order also depends on priority/order and how the context is configured.

`ApplicationContext`-level callbacks are processed before initialization (such as `@PostConstruct` in default configurations), so you can use the supplied references inside init methods. Do not put heavy business logic inside Aware setters if that logic requires other initialized dependencies or a fully refreshed context; setters should **receive and store references**, then defer processing to the appropriate phase.

**Distinguishing BeanFactory from ApplicationContext:** `BeanNameAware` and `BeanFactoryAware` are supported directly by `BeanFactory` during initialization. For `EnvironmentAware`, `ResourceLoaderAware`, and `MessageSourceAware`, standard handling relies on `ApplicationContext` infrastructure. A standalone low-level `DefaultListableBeanFactory` that does not register context-level processors will not automatically run these three callbacks.

## 3. EnvironmentAware: Obtaining the Context's Environment

API signature:

```java
import org.springframework.context.EnvironmentAware;
import org.springframework.core.env.Environment;

public class FeatureReporter implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    public boolean isDemoProfile() {
        return environment.acceptsProfiles(
                org.springframework.core.env.Profiles.of("demo"));
    }
}
```

This is a Java class that compiles when `spring-context` is present, though to observe Spring calling `setEnvironment`, the class must be registered as a bean in an `ApplicationContext`. `Environment` describes **profiles** and how **properties** are resolved from the active property sources in the context. `setEnvironment` receives the `Environment` object, not a point-in-time snapshot of properties.

### 3.1. Properties and Precedence Order

`Environment.getProperty("app.mode")` searches for the key across `PropertySource` entries in order. Common sources include: command-line arguments (depending on the framework), Java system properties, OS environment variables, properties added by `@PropertySource` or Spring Boot, and application-declared sources.

```java
String mode = environment.getProperty("app.mode", "normal");
int limit = environment.getProperty("app.limit", Integer.class, 100);
String required = environment.getRequiredProperty("app.region");
```

These three lines are a fragment inside a bean that already has an `Environment environment` field. `getProperty(key, default)` supplies a fallback when the key is missing; `getRequiredProperty` throws `IllegalStateException` if not found; overloads taking `Class<T>` use a conversion service to convert types when applicable. Converting `"not-a-number"` to `Integer` can raise a conversion error—do not assume the default value handles malformed configuration data.

`EnvironmentAware` does not automatically "re-refresh" `@Value` fields or recreate beans if a property source changes after startup. Bean creation rules via `@Profile`/`@Conditional` are normally evaluated while processing bean definitions. Changing active profiles after `refresh()` does not rewind already-initialized configuration back to the definition selection stage.

### 3.2. Active and Default Profiles

`Environment` provides `getActiveProfiles()`, `getDefaultProfiles()`, and `acceptsProfiles(Profiles.of("..."))`. When no active profile is set, default profiles are used during profile evaluation per the Spring contract.

```java
boolean production = environment.acceptsProfiles(
        org.springframework.core.env.Profiles.of("prod"));
boolean notProduction = environment.acceptsProfiles(
        org.springframework.core.env.Profiles.of("!prod"));
```

Profile expressions can combine `!`, `&`, `|` according to `Profiles.of(...)` rules; use parentheses when needed to avoid ambiguity. If you only want bound values, constructor injection with `@Value` or a validated `@ConfigurationProperties` bean in Spring Boot is usually clearer than holding the entire `Environment`.

### 3.3. Using in the Right Context

Use `EnvironmentAware` when an infrastructure component needs to query multiple dynamic properties or make profile decisions during initialization steps. If a service only needs `app.discount-rate`, inject the exact value or typed configuration. Do not turn `setEnvironment` into a place that calls databases, starts threads, or rescans the `BeanFactory`.

## 4. ResourceLoaderAware: Resolving Resources Instead of Depending on Physical Files

`ResourceLoaderAware` receives `ResourceLoader`, whose central method `getResource(String location)` returns a `Resource`. In a standard `ApplicationContext`, Spring passes the context itself (which implements `ResourceLoader`).

```java
import org.springframework.context.ResourceLoaderAware;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

public class TemplateLocationResolver implements ResourceLoaderAware {
    private ResourceLoader loader;

    @Override
    public void setResourceLoader(ResourceLoader loader) {
        this.loader = loader;
    }

    public Resource loadTemplate(String name) {
        return loader.getResource("classpath:templates/" + name);
    }
}
```

This is an illustrative class, not a standalone runnable program: it requires a Spring-managed bean and an actual resource on the classpath. When constructing paths from untrusted names, you must validate/allowlist `name`; the example does not illustrate security controls.

### 4.1. Common Location Prefixes

| Location | Meaning | Notes |
| --- | --- | --- |
| `classpath:lesson/banner.txt` | A resource from the classpath via `ClassPathResource` | Works inside a JAR when read as a stream |
| `file:/opt/app/config.properties` | Resource from the filesystem via `FileSystemResource` | File may not exist or may lack read permissions |
| `https://example.org/data.txt` | URL resource, when supported by the loader | Network I/O, timeouts, and SSRF risk if URI comes from user input |
| `lesson/banner.txt` | Prefix-less path, depends on the specific `ResourceLoader` | `ClassPathXmlApplicationContext` and web contexts may resolve differently |
| `classpath*:META-INF/spring/*.xml` | Multi-resource pattern, **do not use `getResource` for patterns** | Use `ResourcePatternResolver.getResources(...)` |

`ResourceLoader.getResource(location)` obtains **a single** `Resource` handle; it does not open the file or guarantee the resource exists. `Resource` provides `exists()`, `getInputStream()`, `contentLength()`, and metadata/URL/file access methods depending on the implementation.

**Do not assume `resource.getFile()` works for classpath resources:** when packaging an application as an executable JAR, a resource can be an entry inside the archive with no standalone filesystem path. Use `getInputStream()` with try-with-resources to read packaged resources:

```java
Resource resource = loader.getResource("classpath:lesson/banner.txt");
try (java.io.InputStream in = resource.getInputStream()) {
    String text = new String(in.readAllBytes(),
            java.nio.charset.StandardCharsets.UTF_8);
    System.out.println(text.strip());
}
```

This fragment requires a `loader` field and an existing resource. `getInputStream` can throw `IOException`; check and handle errors according to application requirements. Do not keep streams open across requests, and do not assume every `Resource` can be read multiple times (for instance, `InputStreamResource` is typically backed by a single stream).

### 4.2. ResourcePatternResolver Is Not a Single-Resource ResourceLoader

If you need to load multiple resources matching a pattern, use the `ResourcePatternResolver` interface with `getResources("classpath*:META-INF/spring/*.xml")`. A standard `ApplicationContext` is also a `ResourcePatternResolver`, and `ResourceLoaderAware` receives the context so this type check can succeed. However, casting depends on the actual loader; if the application runs with an alternative loader, do not assume every `ResourceLoader` is a `ResourcePatternResolver`.

```java
if (loader instanceof org.springframework.core.io.support.ResourcePatternResolver patternLoader) {
    Resource[] matching =
            patternLoader.getResources("classpath*:META-INF/spring/*.xml");
    // Process each Resource individually; watch out for IOExceptions.
}
```

This is a fragment that must be inside a method declaring/handling `IOException` with `Resource` imported. It illustrates the difference between a single resource and a resource pattern. Restrict filesystem/network access when locations come from untrusted input.

### 4.3. When to Choose Another Injection Approach?

For a fixed resource:

```java
@Component
class HelpDocument {
    private final Resource resource;

    HelpDocument(@Value("classpath:docs/help.txt") Resource resource) {
        this.resource = resource;
    }
}
```

This code illustrates a component dependency, requiring `Component`/`Value` imports and an actual resource file. Advantage: it makes clear which resource the bean depends on without retaining the whole loader. For multiple dynamic resources per plugin/tenant, receiving `ResourceLoader` may be more suitable.

## 5. MessageSourceAware: Obtaining the Message Resolver and Using Locale

`MessageSourceAware` receives the context's `MessageSource`, typically the `ApplicationContext` itself implementing this interface; you can then call `getMessage` to look up keys, substitute placeholders, and select a language.

```java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceAware;

public class LocalizedPresenter implements MessageSourceAware {
    private MessageSource messages;

    @Override
    public void setMessageSource(MessageSource messageSource) {
        this.messages = messageSource;
    }

    public String greet(String name, Locale locale) {
        return messages.getMessage("hello", new Object[]{name}, locale);
    }
}
```

This class must be registered as a Spring bean with a message source containing the `hello` key. If the code is missing and you use an overload without a default, `NoSuchMessageException` can be thrown. `MessageSource` does not automatically detect the current HTTP locale: your code must supply the appropriate `Locale` (or obtain it from a resolver/web request per your application).

### 5.1. Sources and the `messageSource` Bean Name

In an `ApplicationContext`, the conventional bean name **`messageSource`** carries special significance. If you declare a `MessageSource` bean with that name, Spring uses it to resolve messages. If none is declared, Spring provides a default delegating message source to integrate parent/default messages as configured; do not expect it to contain keys automatically.

Common implementations:
- `StaticMessageSource`: adds messages directly in Java config; convenient for demos and tests.
- `ResourceBundleMessageSource`: loads from `messages.properties`, `messages_vi.properties`, or corresponding basenames.
- `ReloadableResourceBundleMessageSource`: supports cache/refresh configuration when the underlying resource source permits.

Example i18n code table:

| Code | Locale | Text pattern |
| --- | --- | --- |
| `hello` | `vi-VN` | `Xin chào {0}!` |
| `hello` | `en-US` | `Hello {0}!` |
| `error.required` | `vi-VN` | `Trường {0} là bắt buộc.` |

`getMessage("hello", new Object[]{"Mai"}, Locale.forLanguageTag("vi-VN"))` produces the text `Xin chào Mai!` with a `MessageSource` containing the translations above. Placeholders use `MessageFormat`, so syntax and single-quote escaping must be handled properly when translations contain literal apostrophes.

### 5.2. Overload with Fallback

```java
String text = messages.getMessage(
        "notice.unknown", null, "Không có bản dịch", Locale.forLanguageTag("vi-VN"));
```

This is a fragment assuming the `messages` field has been injected. Overloads with `defaultMessage` return a fallback string when the code is not found. With the `getMessage(code, args, locale)` overload lacking a default, a missing code throws `NoSuchMessageException`; choose the overload based on your application's error policy.

### 5.3. MessageSource Is Not a Message Broker

`MessageSource` is for **internationalization/text messages**, unrelated to Kafka/JMS/STOMP message transport. `MessageSourceAware` does not register consumers, send to message queues, or manage application events; those are separate features. The word "message" here means user-facing localized text.

## 6. Complete Runnable Spring Core Example with Java 17+

This example integrates **all three Aware interfaces in a single bean**, proving Spring invokes the callbacks before `InitializingBean.afterPropertiesSet()`. It uses Java 17+, Maven 3.9+, and Spring Framework 6.2.18, with no Spring Boot, servlet container, database, or runtime internet needed. Maven dependencies must be downloaded on first run.

Project:

```text
aware-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/edu/example/aware/
        │   ├── AppConfig.java
        │   ├── AwareReport.java
        │   └── Main.java
        └── resources/lesson/
            └── banner.txt
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>aware-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>edu.example.aware.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/resources/lesson/banner.txt**

```text
READY
```

**src/main/java/edu/example/aware/AwareReport.java**

```java
package edu.example.aware;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.EnvironmentAware;
import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceAware;
import org.springframework.context.ResourceLoaderAware;
import org.springframework.core.env.Environment;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

public final class AwareReport implements EnvironmentAware,
        ResourceLoaderAware, MessageSourceAware, InitializingBean {

    private Environment environment;
    private ResourceLoader resourceLoader;
    private MessageSource messageSource;
    private boolean ready;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
        System.out.println("aware: environment");
    }

    @Override
    public void setResourceLoader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
        System.out.println("aware: resourceLoader");
    }

    @Override
    public void setMessageSource(MessageSource messageSource) {
        this.messageSource = messageSource;
        System.out.println("aware: messageSource");
    }

    @Override
    public void afterPropertiesSet() throws Exception {
        String mode = environment.getRequiredProperty("app.mode");
        Resource resource =
                resourceLoader.getResource("classpath:lesson/banner.txt");

        String banner;
        try (InputStream input = resource.getInputStream()) {
            banner = new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }

        String greeting = messageSource.getMessage(
                "hello", new Object[]{"Spring"}, Locale.forLanguageTag("vi-VN"));

        if (!"learning".equals(mode) || !"READY".equals(banner)) {
            throw new IllegalStateException("Invalid demo configuration");
        }

        System.out.println("init: mode=" + mode);
        System.out.println("init: resource=" + banner);
        System.out.println("init: message=" + greeting);
        ready = true;
    }

    public boolean isReady() {
        return ready;
    }
}
```

**src/main/java/edu/example/aware/AppConfig.java**

```java
package edu.example.aware;

import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.StaticMessageSource;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean(name = "messageSource")
    public MessageSource messageSource() {
        StaticMessageSource source = new StaticMessageSource();
        source.addMessage(
                "hello", Locale.forLanguageTag("vi-VN"), "Xin chào {0}!");
        return source;
    }

    @Bean
    public AwareReport awareReport() {
        return new AwareReport();
    }
}
```

**src/main/java/edu/example/aware/Main.java**

```java
package edu.example.aware;

import java.util.Map;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;

public final class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo", Map.of("app.mode", "learning")));
            context.getEnvironment().setActiveProfiles("demo");
            context.register(AppConfig.class);
            context.refresh();

            AwareReport report = context.getBean(AwareReport.class);
            System.out.println("main: ready=" + report.isReady());
        }
    }
}
```

In the `aware-demo` directory, run:

```bash
mvn -q compile exec:java
```

**Lines printed to `System.out` by the program itself, in order:**

```text
aware: environment
aware: resourceLoader
aware: messageSource
init: mode=learning
init: resource=READY
init: message=Xin chào Spring!
main: ready=true
```

Additional Maven/Spring logs may appear depending on the environment. The lines above are deterministic because Spring calls the three callbacks on the same `AwareReport` inside `ApplicationContextAwareProcessor`, then runs `afterPropertiesSet()`, and then `Main` retrieves the created bean.

Explanation:
1. `new AnnotationConfigApplicationContext()` creates an unrefreshed context. We add `MapPropertySource` beforehand so `app.mode` has the value `learning`.
2. `context.register(AppConfig.class)` declares the Java configuration; it does not yet finalize all beans.
3. `context.refresh()` processes bean definitions, prepares the bean factory and message source, and instantiates the eager singleton `awareReport`.
4. `AwareReport` receives the three infrastructure dependencies via Aware setter callbacks; the illustrative code only prints callback names and does not perform I/O inside setters.
5. `afterPropertiesSet()` runs after the callbacks are processed; it reads `app.mode`, opens the classpath resource via stream, and looks up the message for `vi-VN`.
6. After `refresh()`, `getBean(...)` returns the initialized bean, so `ready=true`.
7. `try-with-resources` closes the context properly; because the example registers no logging destroy callback, no additional `System.out` line appears after `main`.

**Reliability of the example:** Requires no HTTP request, does not rely on the working directory to read files, and avoids `Resource.getFile()`. The `banner.txt` file in `src/main/resources/lesson/` is placed on the classpath by Maven. `MessageSource` uses `StaticMessageSource` so the example stays independent of i18n properties files. Removing the resource file causes an `IOException` during init; omitting the message causes the `hello` lookup without fallback to fail to find the code, failing bean initialization.

## 7. Using @Autowired / Constructor Injection Instead of Aware When Appropriate

Spring does not force every service needing `Environment`, `ResourceLoader`, or `MessageSource` to implement Aware. In a context with autowiring enabled, these types can be injected like any other dependency:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class NoticeService {
    private final Environment environment;
    private final ResourceLoader resourceLoader;
    private final MessageSource messages;

    public NoticeService(Environment environment,
                         ResourceLoader resourceLoader,
                         MessageSource messages) {
        this.environment = environment;
        this.resourceLoader = resourceLoader;
        this.messages = messages;
    }

    public String describe(Locale locale) {
        String mode = environment.getProperty("app.mode", "normal");
        String greeting =
                messages.getMessage("hello", null, "Hello", locale);
        return greeting + " / mode=" + mode;
    }

    // resourceLoader can be used in other methods if dynamic resources are needed.
}
```

This is a syntactically self-contained Spring component when dependencies are valid; it requires a context with an appropriate `messageSource` code to yield the expected output. Constructor injection makes mandatory dependencies explicit, keeps fields `final`, and makes mocking/faking easy in unit tests. If a service only needs one configuration key, passing the bound value is better than passing the entire `Environment`.

| Scenario | Preferred Approach |
| --- | --- |
| Infrastructure adapter needs to query many keys/profiles at runtime | `EnvironmentAware` or inject `Environment` |
| Service only needs one required value | Typed configuration/constructor argument |
| Loader must resolve multiple dynamic resources | `ResourceLoaderAware` or inject `ResourceLoader` |
| Only needs a single known classpath file | Inject `Resource` with `@Value("classpath:...")` |
| Infrastructure component needs to translate text across locales | `MessageSourceAware` or inject `MessageSource` |
| Web controller needs a localized message | Inject `MessageSource`, obtain `Locale` from request/resolver |
| Need `ApplicationContext` only to get these three services | Pick the specialized interface or inject directly; avoid pulling the whole context |
| Want unit tests to run without Spring | Constructor injection with stub dependencies |

A practical note: placing an `@Autowired` constructor on a class implementing `Aware` still works, but if the same dependency type is already supplied via constructor, the Aware callback can be redundant and create two wiring paths that are hard to maintain. Combine them only when there is a clear technical reason, such as a framework contract that must support both container-aware and standalone modes.

## 8. Using MessageSource in Real-World i18n

With `ResourceBundleMessageSource`, you can create files:

```text
src/main/resources/i18n/messages.properties
src/main/resources/i18n/messages_vi.properties
src/main/resources/i18n/messages_en.properties
```

Example:

```properties
# i18n/messages_vi.properties
hello=Xin chào {0}!
error.required=Trường {0} là bắt buộc.
```

```properties
# i18n/messages_en.properties
hello=Hello {0}!
error.required=Field {0} is required.
```

Config:

```java
@Bean(name = "messageSource")
MessageSource messageSource() {
    ResourceBundleMessageSource source = new ResourceBundleMessageSource();
    source.setBasename("i18n/messages");
    source.setDefaultEncoding("UTF-8");
    return source;
}
```

This is a fragment requiring imports for `MessageSource`, `ResourceBundleMessageSource`, and `Bean`; it is not a second configuration to insert alongside the `StaticMessageSource` example in Section 6. Choose **one** `messageSource` bean by design. `Locale.forLanguageTag("vi-VN")` normally falls back to language `vi` if no separate `vi_VN` bundle exists. Fallback rules also depend on how the loader and default locale are configured; test with your application's actual locales.

When using Spring Boot, the `messages.properties` file convention and `spring.messages.basename` setting can be auto-configured by Boot; this lesson focuses on **Spring Framework Core Container**, so message sources are declared explicitly.

### Missing Messages and Consistency

For non-existent error codes, choose among:
- Throwing an explicit exception to catch missing translations in CI/tests.
- Providing a sensible `defaultMessage` to avoid failing a request over a minor missing translation.
- Logging metrics for missing codes and writing tests covering all required locales.

Do not use translated text as a business key or database key. A message key like `error.required` is far more stable than language-specific text; translation belongs strictly to the presentation layer.

## 9. Scope, Proxies, Lifecycle, and Thread Safety

### 9.1. Singleton, Prototype, Request, and Session

For a typical eager singleton, the target's Aware callbacks are invoked when the target is first created in the container. For a prototype, each time Spring actually instantiates a prototype target, the corresponding callbacks are processed. For a request/session-scoped target, callbacks belong to the creation of the **scoped target**, not every method invocation on the scoped proxy.

For instance, a singleton injecting a request-scoped bean through a proxy may hold the proxy long-term; `Environment`, `ResourceLoader`, and `MessageSource` references still belong to the context, whereas request data appears on the target upon resolution. Do not assume Aware creates a request-specific `Environment` or `MessageSource` per request.

### 9.2. Can These References Be Read from Multiple Threads?

All three dependencies are generally shared infrastructure used to read config, resolve resources, and look up messages. Multiple singletons can receive the same references. That does **not** mean every operation you write inside a callback is thread-safe: if your component maintains a mutable cache, mutates property sources, or edits translation catalogs at runtime, you must manage synchronization/publication properly.

Example of what not to write in a setter:

```java
@Override
public void setEnvironment(Environment environment) {
    this.environment = environment;
    this.lastUser = environment.getProperty("user"); // Wrong per-request model.
}
```

This fragment illustrates an anti-pattern relying on a `lastUser` field. `Environment` holds application configuration, not per-HTTP-user storage. For user/request data, use method parameters, the authentication principal, or a properly designed request-scoped context.

### 9.3. Proxies/AOP Do Not Intercept Callbacks Automatically

Aware methods are invoked by Spring during target bean initialization, before some final proxies are created. Do not rely on `@Transactional`, `@Async`, or `@Cacheable` placed directly on `setEnvironment`/`setResourceLoader`/`setMessageSource` to trigger AOP advice. If a callback calls another method on `this`, it can bypass the proxy. Keep callbacks simple and avoid triggering business side effects from them.

### 9.4. Does Not Mean the Application Is Ready

Callbacks run when **a single bean** is created; the context may still be inside `refresh()`. For example, a bean needing to load an external translation service can use a local `MessageSource` fallback first and move startup/readiness checks to a post-refresh mechanism or appropriate lifecycle component if needed.

## 10. BeanFactory, Custom Contexts, and Testing

### 10.1. When Using Only BeanFactory

A low-level `BeanFactory` is not itself an `ApplicationContext`, `MessageSource`, or `ResourceLoader`. A bean implementing context-level Aware interfaces may **not receive callbacks** if no recognizing processor is present. Conversely, `BeanNameAware`/`BeanFactoryAware` are handled by core bean factory mechanics. Do not use a unit test that simply calls `new AwareReport()` to verify Spring callback ordering.

### 10.2. Simple Unit Testing of Aware

You can test the logic by calling the setters manually with fake dependencies:

```java
AwareReport report = new AwareReport();
report.setEnvironment(testEnvironment);
report.setResourceLoader(testResourceLoader);
report.setMessageSource(testMessageSource);
report.afterPropertiesSet();
```

This is only a **test fragment**, not runnable without the three test variables and matching resources/messages. It tests dependency-handling logic but does not prove the container invokes the callbacks automatically. An integration test verifying real lifecycle behavior must create an `AnnotationConfigApplicationContext`, register `AppConfig`, call `refresh()`, and assert the target's state.

### 10.3. Verifying Callbacks Against the Right Context

With parent-child `ApplicationContext`s, each bean belongs to the context that creates it. A bean's `EnvironmentAware`, `ResourceLoaderAware`, and `MessageSourceAware` receive the corresponding context/infrastructure; having parent and child share property sources or `messageSource` inheritance does not mean they share the same bean instance. A child may override message codes or property sources. Do not cache references globally and assume they apply to every context.

### 10.4. Mocking and Dependency Visibility

With Aware callbacks, fields are usually non-final because Spring invokes setters after the constructor. If you need the invariant "cannot construct the bean without dependencies", constructor injection expresses that contract more clearly. With an Aware bean, you can validate inside `afterPropertiesSet()` and throw an exception if an expected callback was missed:

```java
@Override
public void afterPropertiesSet() {
    if (environment == null || resourceLoader == null ||
            messageSource == null) {
        throw new IllegalStateException(
                "Aware infrastructure not initialized");
    }
}
```

This illustrative fragment belongs to a class that already has those fields; it is only needed when container wiring is not guaranteed to be ready or the bean must support running in multiple environments.

## 11. Common Issues and Fixes

| Symptom | Common Cause | Solution |
| --- | --- | --- |
| `setEnvironment` does not run | Bean created with `new` or not processed by ApplicationContext | Declare `@Bean`/`@Component`, use the proper context |
| `setResourceLoader` does not run | Using a raw BeanFactory without registered processors | Use ApplicationContext or add appropriate infrastructure |
| `setMessageSource` receives an object other than the `messageSource` bean | Callback typically receives ApplicationContext as a MessageSource façade | Call the `getMessage` interface; do not cast to the bean's implementation |
| `getProperty` returns null | Key does not exist or source precedence differs from expectations | Check property sources, profiles, spelling, and defaults |
| Changing active profile after startup does not swap beans | `@Profile` is evaluated when selecting definitions | Set profiles before refresh; design separate runtime config |
| `@Value` and `Environment` produce different results | Different resolution timing or property source configuration | Clarify binding semantics; avoid mutating config arbitrarily after init |
| `Resource.getFile()` fails when packaged as a JAR | Classpath resource is not a standalone file | Use `getInputStream()` and close the stream |
| `getResource("classpath*:...")` does not return a list | The API only returns a single resource | Use `ResourcePatternResolver.getResources(...)` |
| `IOException` when opening a resource | Wrong location, missing resource, permission/network issue | Check location, `exists()`, and handle I/O |
| `NoSuchMessageException` | Missing code/bundle or locale lacks fallback | Add translation, `defaultMessage`, or check basename |
| Message does not change when locale changes | Using a fixed locale or resolver not passing the right locale | Pass the appropriate `Locale` per request |
| Confusing `MessageSource` with Kafka/JMS | Two APIs with different purposes | Use the appropriate messaging API |
| Callback runs while App is not yet ready | Aware belongs to single-bean initialization | Use appropriate context/startup lifecycle callbacks |
| Callback calls a `@Transactional` method on `this` with no transaction | Initialization/self-invocation bypasses AOP proxy | Move business logic to a bean invoked via proxy after startup |
| Lazy bean has not received Aware yet | Target has not been instantiated | Callbacks run when the bean actually instantiates |
| Internal logic stores mutable shared state | Aware does not make objects thread-safe | Design immutable snapshots or synchronize properly |
| Unit test using `new` fails with null fields | Test bypasses Spring | Inject mocks via constructor or invoke test setters explicitly |

## 12. Design Checklist and Self-Assessment Exercises

Before using Aware in a component, ask yourself:
1. Does the component truly need infrastructure APIs, or just a fixed value?
2. Is it created by a Spring `ApplicationContext`, or can it be instantiated with `new`?
3. Is the callback doing heavy work/side effects before context refresh completes?
4. Is the bean using `Environment` to read config, or mixing in request/user state?
5. Is the resource guaranteed to exist in a packaged JAR and read via stream?
6. Does the resource path come from untrusted input?
7. Does `MessageSource` have the `messageSource` bean name and proper translations/default policy?
8. Are you using the right `Locale`, testing missing codes, Vietnamese diacritics, and placeholders?
9. Is there a way in unit tests to inject stubs without booting a context?
10. With parent-child contexts, which context owns the bean and what is the property/message precedence?

**Practice Questions:**

1. Does a bean implementing `EnvironmentAware` receive the callback if instantiated solely via constructor `new`?
2. Why does `setEnvironment` run after the constructor? Does it run before or after `afterPropertiesSet()`?
3. How does `Environment.getProperty("timeout", Integer.class, 30)` differ from `getRequiredProperty("timeout")`?
4. To enable a `@Profile("dev")` bean, should the active profile be set before or after `refresh()`?
5. Does `ResourceLoaderAware` receive a `Resource` directly or an object capable of resolving multiple resources?
6. Should a resource inside an executable JAR be read via `getFile()` or `getInputStream()`?
7. If you need to search `classpath*:META-INF/spring/*.xml`, which interface should you use?
8. What is the significance of the bean name `messageSource` in an `ApplicationContext`?
9. Which exception can `getMessage("unknown", null, locale)` throw?
10. To produce a Vietnamese greeting, which `Locale` must be provided and what should the message pattern look like?
11. Can a bean implementing all three Aware interfaces use those three dependencies inside `@PostConstruct`?
12. Does an Aware callback mean the entire application has finished starting up successfully?
13. Why is constructor injection more advantageous than Aware for an ordinary service?
14. For a proxied request-scoped bean, when do the target's Aware callbacks run?
15. Why does `MessageSourceAware` not help subscribe to a Kafka topic?

**Answers:** (1) No, Spring does not manage that object. (2) Because the context-level processor invokes it during initialization after property population, before `afterPropertiesSet()`. (3) The first overload has a default + type conversion; the latter requires the key to be present. (4) Before. (5) `ResourceLoader`. (6) `InputStream`. (7) `ResourcePatternResolver`. (8) Spring uses it as the message lookup strategy. (9) `NoSuchMessageException`. (10) `vi-VN` (with `vi` language fallback depending on the bundle) and pattern `Xin chào {0}!`. (11) Yes, in the standard Spring path. (12) Not yet. (13) Explicit dependencies, immutable fields, and simple unit testing. (14) When the real target is created per scope, not on every method call on the proxy. (15) `MessageSource` only provides i18n text lookup.

## Official References

- Spring Framework — Customizing the Nature of a Bean, Other Aware Interfaces: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Resources / ResourceLoaderAware Interface: https://docs.spring.io/spring-framework/reference/core/resources.html
- Spring Framework — Internationalization using MessageSource: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2 — EnvironmentAware Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/EnvironmentAware.html
- Spring Framework 6.2 — ResourceLoaderAware Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/ResourceLoaderAware.html
- Spring Framework 6.2 — MessageSourceAware Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/MessageSourceAware.html
- Spring Framework 6.2 — ApplicationContextAwareProcessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/support/ApplicationContextAwareProcessor.html
- Spring Framework 6.2 — ResourcePatternResolver Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/io/support/ResourcePatternResolver.html
- Spring Framework 6.2 — MessageSource Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/MessageSource.html
