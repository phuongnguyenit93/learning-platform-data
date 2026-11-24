# Relationship Between spring.mvc.*, spring.web.*, and Java Spring MVC Configuration

## 1. Objectives and Context

In a Spring Boot application using **Spring MVC (Servlet stack)**, HTTP behavior can be tuned across three different layers:

1. **`spring.mvc.*`**: properties dedicated to Spring MVC such as date/time parameter formatting, content negotiation, static resource URL mapping, `DispatcherServlet` settings, and MVC error handling.
2. **`spring.web.*`**: broader web properties, notably locale and the static resource system (file locations, HTTP caching, resource chains). Some groups are shared by both MVC and WebFlux.
3. **Java configuration**: `@Configuration`, `WebMvcConfigurer`, `Converter`, `Formatter`, `HttpMessageConverter`, `HandlerInterceptor`, `WebMvcRegistrations`, and specific extension beans.

These three layers **are not three independent competing mechanisms**. Spring Boot reads properties, creates auto-configuration beans, and together with Spring Framework aggregates Java configurations to assemble the MVC infrastructure. Two seemingly similar settings may complement each other, override one another, or not interact at all, depending on the **component and configuration order**.

For consistent illustration, the runnable example below uses **Spring Boot 3.5.x, Spring MVC, Java 17+**. In Spring Boot 4.x, many property names remain, yet starters and some Boot packages have changed; consult the documentation for the version you are using.

## 2. Configuration Namespace Map

| Property Group | Primary Target | Examples | Extensible via Java |
|---|---|---|---|
| `spring.mvc.*` | Spring MVC and `DispatcherServlet` | `spring.mvc.format.date`, `spring.mvc.static-path-pattern`, `spring.mvc.contentnegotiation.*` | `WebMvcConfigurer`, `ConversionService`, `WebMvcRegistrations` |
| `spring.web.locale*` | Default locale and how request locale is resolved | `spring.web.locale`, `spring.web.locale-resolver` | `LocaleResolver` bean, interceptors, and i18n configuration |
| `spring.web.resources.*` | Static resource handling and HTTP caching | `spring.web.resources.static-locations`, `spring.web.resources.cache.period` | `WebMvcConfigurer.addResourceHandlers`, `ResourceHandlerRegistry` |
| `spring.webflux.*` | Spring WebFlux/reactive | `spring.webflux.static-path-pattern`, `spring.webflux.base-path` | `WebFluxConfigurer`; **not `WebMvcConfigurer`** |
| `server.*` | Embedded HTTP server and Servlet container | `server.port`, `server.servlet.context-path` | `WebServerFactoryCustomizer`, filters, servlet registrations |
| `spring.servlet.multipart.*` | Multipart upload configuration | `spring.servlet.multipart.max-file-size` | `MultipartConfigElement` and specialized beans when truly needed |
| `spring.jackson.*` in Boot 3.5 | JSON serialization/deserialization via Jackson | `spring.jackson.default-property-inclusion` | `ObjectMapper`, `Jackson2ObjectMapperBuilderCustomizer` per version |
| Application configuration beans | Custom logic | `@Bean Converter<...>`, `WebMvcConfigurer` | Spring Framework invokes the corresponding hooks |

**Do not classify purely by names containing "web":** `spring.mvc.static-path-pattern` determines the **public URL** of static files in MVC, whereas `spring.web.resources.static-locations` determines **where to find the files**. The two properties work together; they are not an old name and new name for the same feature.

`spring.web.resources.*` can serve both Servlet MVC and WebFlux, yet URL mappings are separate: MVC uses `spring.mvc.static-path-pattern`, while WebFlux uses `spring.webflux.static-path-pattern`. An MVC app with `WebClient` does not turn into WebFlux; do not set `spring.webflux.*` expecting it to configure `DispatcherServlet`.

## 3. How Does Spring Boot Turn Properties into MVC Infrastructure?

High-level configuration flow:

~~~text
application.properties / application.yaml / ENV / CLI
                  |
                  v
             Spring Environment
                  |
                  v
       @ConfigurationProperties binding
         WebMvcProperties / WebProperties
                  |
                  v
          WebMvcAutoConfiguration
              + Spring MVC
                  |
                  +-- Boot's WebMvcConfigurer instances
                  +-- application's WebMvcConfigurer instances
                  +-- Converter / Formatter / ... beans
                  |
                  v
     RequestMappingHandlerMapping, HandlerAdapter,
     ConversionService, ResourceHttpRequestHandler,
     HandlerExceptionResolver, ...
                  |
                  v
             DispatcherServlet
                  |
                  v
             HTTP request/response
~~~

In Spring Boot 3.5, `WebMvcAutoConfiguration` evaluates conditions tied to a Servlet application, the presence of `DispatcherServlet` and `WebMvcConfigurer`, and applies only when no application-supplied `WebMvcConfigurationSupport` replaces it. It consumes configuration bound into classes such as `WebMvcProperties` and `WebProperties`.

You can picture the stages as:

1. **Reading and merging configuration sources** per Boot's externalized configuration rules. Profiles, environment variables, and CLI args can change property values without editing source code.
2. **Binding**: values like `spring.mvc.static-path-pattern=/assets/**` are bound into the corresponding properties class. Severe binding errors can prevent startup.
3. **Auto-configuration**: Boot adds default conventions and framework hooks; conditional beans still depend on classpath and application type.
4. **Java customization**: Spring MVC invokes `WebMvcConfigurer` beans and extension beans. Depending on the callback, they may add logic or adjust the same objects configured by Boot.
5. **Runtime verification**: only inspecting actual requests, created beans, and HTTP responses confirms the final result.

**There is no universal rule that "Java beats properties" or "properties beat Java."** Application order and the specific extension point decide the outcome. Java configuration can extend a non-conflicting area, such as adding an interceptor, while `spring.mvc.format.date` still governs conversion.

## 4. spring.mvc.*: Features Specific to MVC

### 4.1. Formatting Request Parameters and Model Binding

~~~properties
spring.mvc.format.date=dd/MM/yyyy
spring.mvc.format.time=HH:mm:ss
spring.mvc.format.date-time=dd/MM/yyyy HH:mm:ss
~~~

These patterns are formatting conventions for the corresponding date/time types when Spring MVC binds/converts request data into parameters or models, such as `@RequestParam LocalDate`. They **do not automatically change the JSON date format** of `@RequestBody` or values serialized by `ObjectMapper`.

Example controller:

~~~java
@GetMapping("/api/day")
public String day(@RequestParam("value") java.time.LocalDate value) {
    return value.toString();
}
~~~

With `spring.mvc.format.date=dd/MM/yyyy`, input `value=31/12/2026` binds to `LocalDate.of(2026, 12, 31)`, and the method returns `2026-12-31`. This method snippet is illustrative and must be placed inside a `@RestController` class.

If one endpoint needs a different format without changing the whole app, use annotations such as `@DateTimeFormat` on the parameter; to convert a domain type from `String`, add a `Converter` via `WebMvcConfigurer.addFormatters`.

**Two distinct `ConversionService` instances:** Spring MVC has its own conversion service for request binding; `@ConfigurationProperties` uses a separate configuration conversion mechanism. Therefore, do not assume properties formatting like `Duration` or `DataSize` in configuration matches MVC request parameter parsing.

### 4.2. Content Negotiation

Example allowing clients to request a representation via a query parameter when genuinely required:

~~~properties
spring.mvc.contentnegotiation.favor-parameter=true
spring.mvc.contentnegotiation.parameter-name=format
spring.mvc.contentnegotiation.media-types.markdown=text/markdown
~~~

Clients can then pass `?format=markdown`; Spring MVC uses content negotiation to select a media type according to configuration and what handlers/converters actually support. **Properties do not automatically create a Markdown converter.** If the app only has a JSON converter and no handler producing `text/markdown`, adding the media type mapping is insufficient to serve Markdown responses.

By default, Spring MVC prefers the `Accept` header to determine the requested media type. Avoid inferring content types from URL file extensions due to ambiguity and security implications.

The Java equivalent uses:

~~~java
@Override
public void configureContentNegotiation(
        org.springframework.web.servlet.config.annotation.ContentNegotiationConfigurer configurer) {
    configurer.favorParameter(true)
            .parameterName("format")
            .mediaType("markdown", org.springframework.http.MediaType.parseMediaType("text/markdown"));
}
~~~

This is only a **method snippet** for a `WebMvcConfigurer` class, not a complete application. If setting both properties and Java config for the exact same option, inspect how each configurer applies and its configuration order; do not put contradictory values in two places to guess which wins.

### 4.3. Servlet Path and Static Resource URLs

~~~properties
spring.mvc.static-path-pattern=/assets/**
~~~

With this, `src/main/resources/static/logo.svg` is normally served at `/assets/logo.svg` while default static locations remain active. This property **does not alter controller mappings** such as `@GetMapping("/api/status")`.

There is also:

~~~properties
spring.mvc.servlet.path=/
~~~

This controls the mapping path of `DispatcherServlet`, which **differs** from `server.servlet.context-path` (the application's context root in the Servlet container) and `spring.mvc.static-path-pattern` (URL matching for resource handlers). Notably in Boot 3.5, setting `spring.mvc.servlet.path` to a non-default value has compatibility constraints with `PathPatternParser`; follow the path matching documentation when changing the servlet path.

### 4.4. Other MVC Properties

| Property in Spring Boot 3.5 | Meaning |
|---|---|
| `spring.mvc.pathmatch.matching-strategy` | Selects request mapping matching strategy; defaults to `path-pattern-parser` |
| `spring.mvc.async.request-timeout` | Timeout for MVC asynchronous request processing |
| `spring.mvc.hiddenmethod.filter.enabled` | Enables/disables `HiddenHttpMethodFilter` for form method overrides |
| `spring.mvc.formcontent.filter.enabled` | Enables/disables `FormContentFilter` for form-encoded bodies on applicable HTTP methods |
| `spring.mvc.problemdetails.enabled` | Enables Problem Details support for applicable MVC error handling |
| `spring.mvc.message-codes-resolver-format` | How message codes are generated for binding errors |
| `spring.mvc.view.prefix` and `spring.mvc.view.suffix` | Supports resolving view names where applicable; does not affect `@ResponseBody` |
| `spring.mvc.log-request-details` | Allows logging detailed request info at DEBUG/TRACE; may contain sensitive data, do not enable carelessly |

These properties are examples, not an immutable list across all Boot versions. MVC mechanisms can change if the application declares replacement infrastructure beans.

## 5. spring.web.*: Locale and Shared Resources

### 5.1. Locale

~~~properties
spring.web.locale=vi_VN
spring.web.locale-resolver=accept-header
~~~

By default, `accept-header` prefers the HTTP `Accept-Language` header; the configured locale acts as fallback. To always fix the locale regardless of headers:

~~~properties
spring.web.locale=vi_VN
spring.web.locale-resolver=fixed
~~~

The two approaches represent different policies: client-driven multilingual responses or a fixed single-locale UI. `spring.web.locale` does not automatically translate strings hard-coded in controllers. Real i18n requires message bundles, `MessageSource`, locale resolution, and locale-aware message lookup.

You can register a custom `LocaleResolver` bean in Java when complex policies are needed, but verify how the custom bean interacts with Boot's auto-configuration. Do not declare a custom bean and still expect every `spring.web.locale-resolver` setting to dictate final behavior.

### 5.2. Physical Locations of Static Files

~~~properties
spring.web.resources.static-locations=classpath:/site/
~~~

This is the **classpath location where files are read**, not the URL. This property replaces the default location list; per Boot's Servlet docs, the `ServletContext` root can also be included as a location. Typical default locations are `classpath:/META-INF/resources/`, `classpath:/resources/`, `classpath:/static/`, and `classpath:/public/`.

If `src/main/resources/site/` contains `hello.txt` and `spring.mvc.static-path-pattern=/assets/**`, Spring MVC can serve the resource at `GET /assets/hello.txt`. Conversely, `GET /site/hello.txt` is not automatically a valid URL just because the internal folder is named `site`.

### 5.3. Caching and Resource Chains

~~~properties
spring.web.resources.cache.period=3600s
spring.web.resources.cache.cachecontrol.cache-public=true
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
~~~

These properties adjust **static resource** handling via Boot's configured handler: cache headers, content-based versioning strategies, and resource chains. They do not automatically configure caching for controller JSON APIs.

Notes:

- `spring.web.resources.cache.period` sets the caching duration; if `cache.cachecontrol.*` is configured, fine-grained `Cache-Control` settings can override `period` behavior.
- `spring.web.resources.chain.strategy.content.enabled=true` equips resource handling with content-based versioning. Rewriting URLs inside HTML/templates still requires template/filter integration; do not assume URLs inside arbitrary HTML strings are rewritten automatically.
- `spring.web.resources.add-mappings=false` disables **Boot's default static resource mappings**. A manually written `WebMvcConfigurer.addResourceHandlers` can still register custom resource handlers.
- If you manually register a handler for the exact same pattern managed by Boot, check the result and order; Java config can cause Boot to skip its default mapping for that pattern, meaning property-based caching/locations no longer apply as expected.

### 5.4. WebFlux Reuses Resource Settings While Java Config Differs

WebFlux applications also use `spring.web.resources.static-locations` to locate files. However, WebFlux URL mapping uses `spring.webflux.static-path-pattern` and its extension API is `WebFluxConfigurer`, not `WebMvcConfigurer`. Therefore:

- `spring.web.resources.static-locations` is not an MVC-only property.
- `spring.mvc.static-path-pattern` applies only to Spring MVC.
- `spring.webflux.static-path-pattern` applies only to reactive WebFlux.
- Do not see Netty on the classpath and conclude the app is running WebFlux; Netty HTTP clients can exist alongside the Spring MVC Servlet stack.

## 6. Java Configuration: Three Levels of Intervention

### Level 1 — Additional Beans or WebMvcConfigurer

When you want to add interceptors, formatters, CORS mappings, view controllers, or new resource mappings:

~~~java
@Configuration(proxyBeanMethods = false)
public class MyMvcConfiguration implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MyInterceptor())
                .addPathPatterns("/api/**");
    }
}
~~~

This is a snippet requiring `MyInterceptor` and corresponding imports. Boot continues managing MVC defaults. **Do not place `@EnableWebMvc`** just to add a `WebMvcConfigurer`.

Commonly used hooks:

| Hook in WebMvcConfigurer | Purpose | Notes |
|---|---|---|
| `addInterceptors` | Add `HandlerInterceptor` around handlers | Does not replace the Spring Security filter chain |
| `addFormatters` | Add `Converter`/`Formatter` | Be careful with global formats affecting binding |
| `addCorsMappings` | Configure CORS for MVC handlers | Does not replace authentication/authorization checks |
| `addArgumentResolvers` | Add custom controller arguments | Not designed to replace all built-in resolvers |
| `addResourceHandlers` | Add static file mappings | Avoid colliding URL patterns with existing mappings |
| `configureContentNegotiation` | Customize media type selection | Can interact with `spring.mvc.contentnegotiation.*` |
| `extendMessageConverters` | Adjust existing converter list | Usually safer than replacing the whole list |
| `configureMessageConverters` | Configure converter list | Understand how Boot contributes defaults before replacing the list |
| `addViewControllers` | Create simple routes to views or redirects | Not suitable when complex business logic is needed |

### Level 2 — Replacing Part of Infrastructure via Specialized Beans

If you want to replace a primary implementation such as `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, or `ExceptionHandlerExceptionResolver` while preserving Spring Boot customizations, documentation recommends `WebMvcRegistrations` where appropriate. Created components are still processed further by Spring MVC and customizers.

This is an advanced option. When replacing an infrastructure bean, do not assume property binding and every hook behave identically to the default classes. Thoroughly test handler mappings, validation, formatters, error handling, resource serving, and startup.

### Level 3 — Full MVC Control with @EnableWebMvc

~~~java
@Configuration
@EnableWebMvc
public class FullControlMvcConfiguration implements WebMvcConfigurer {
    // The application takes responsibility for necessary MVC configuration.
}
~~~

**This illustrates a mode change, not a recommended setup for ordinary Spring Boot projects.** `@EnableWebMvc` introduces `WebMvcConfigurationSupport` into the context and causes Boot's `WebMvcAutoConfiguration` to back off. The application must actively review Boot-configured features such as default resource handlers, conversion, view resolvers, and converter customizations. Spring Framework MVC still supplies its own defaults, so it is inaccurate to claim every handler or JSON converter disappears; however, **Boot's additions are no longer preserved automatically**.

If you only need an interceptor, converter, or path mapping, use `WebMvcConfigurer` **without `@EnableWebMvc`**.

## 7. "Do Properties or Java Take Precedence?" — Resolve by Mechanism, Not Slogans

| Situation | Safe Conclusion |
|---|---|
| Set `spring.mvc.format.date=dd/MM/yyyy`, Java only adds an interceptor | Both typically work together because they affect different components |
| Set `spring.web.resources.static-locations`, Java adds a resource mapping with a **different** pattern | Default resource mapping and custom mapping can coexist |
| Set `spring.mvc.static-path-pattern=/assets/**`, Java registers the exact same `/assets/**` | Potential conflict or one mapping wins; check registry and actual HTTP behavior |
| Set `spring.web.locale-resolver=fixed` and declare a custom `LocaleResolver` bean | Custom bean can alter Boot's selected mechanism; inspect the actual bean |
| Set `spring.mvc.contentnegotiation.*` and Java also alters content negotiation | Outcome depends on how configurers add/override and their order |
| Declare `@EnableWebMvc` in a Boot app | Boot MVC auto-configuration backs off; do not assume `spring.mvc.*` and `spring.web.resources.*` still apply fully as before |
| Set `server.port=9090` alongside Java `WebMvcConfigurer` | `WebMvcConfigurer` is not a tool for changing the embedded server port; `server.port` belongs to the server layer |
| Try to change JSON field naming with `spring.mvc.format.date` | Wrong layer; use dedicated JSON serialization/deserialization configuration |

**Two distinct kinds of "precedence":**

1. **Precedence among external config sources**: `application.properties`, profiles, environment variables, command line, test properties, etc. are merged by Spring Boot according to externalized configuration order.
2. **Precedence between Java components and auto-configuration**: Spring uses conditional bean creation, callback ordering, and API registration. It is not a simple rule that a property above overrides a `@Bean` below.

When an actual conflict occurs, identify **which bean/hook produces the behavior** and test at runtime; do not conclude simply by looking at two config lines.

## 8. Complete Example: Boot 3.5 + Java 17 + Properties and WebMvcConfigurer

This example uses non-conflicting additions to clearly demonstrate all three layers:

- `spring.mvc.format.date` formats `LocalDate` request parameters.
- `spring.mvc.static-path-pattern` picks the URL for default static files.
- `spring.web.resources.static-locations` picks the directory containing the files.
- `spring.web.resources.cache.period` adjusts default static resource caching.
- Java `WebMvcConfigurer` adds an interceptor for APIs and adds **one** separate resource mapping to prove Java can extend without breaking property-configured mappings.

### 8.1. Project Structure

~~~text
mvc-config-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvcdemo/
    │   │   ├── MvcDemoApplication.java
    │   │   ├── DayController.java
    │   │   └── ExtraMvcConfiguration.java
    │   └── resources/
    │       ├── application.properties
    │       ├── site/info.txt
    │       └── manual/extra.txt
    └── test/
        └── java/com/example/mvcdemo/
            └── MvcConfigurationTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-config-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

This example targets Boot 3.5.x; do not mechanically reuse the same imports/starter structure when upgrading to 4.x.

### 8.3. application.properties

File `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.mvc.format.date=dd/MM/yyyy
spring.mvc.static-path-pattern=/assets/**

spring.web.resources.static-locations=classpath:/site/
spring.web.resources.cache.period=3600s
~~~

The four properties after `server.port` belong to two namespaces yet work together in one MVC application. File `src/main/resources/site/info.txt` contains:

~~~text
assets-ok
~~~

File `src/main/resources/manual/extra.txt` contains:

~~~text
manual-ok
~~~

Text file contents may include a trailing newline; the tests below use substring checks so they do not depend on that trailing newline.

### 8.4. Spring Boot Entry Point

File `src/main/java/com/example/mvcdemo/MvcDemoApplication.java`:

~~~java
package com.example.mvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

### 8.5. Controller: Request Parameter Using spring.mvc.format.date

File `src/main/java/com/example/mvcdemo/DayController.java`:

~~~java
package com.example.mvcdemo;

import java.time.LocalDate;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DayController {
    @GetMapping("/api/day")
    String day(@RequestParam("value") LocalDate value) {
        return value.toString();
    }

    @GetMapping("/api/status")
    String status() {
        return "mvc-config-ok";
    }
}
~~~

Spring MVC parses the query string using the configured `dd/MM/yyyy` format. `LocalDate.toString()` outputs ISO `yyyy-MM-dd`; this is an **output format produced directly by the controller**, not JSON serialization.

### 8.6. Java Config: Adding an Interceptor and Custom Resource Handler

File `src/main/java/com/example/mvcdemo/ExtraMvcConfiguration.java`:

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ExtraMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler) {
                response.setHeader("X-App-Mvc", "on");
                return true;
            }
        }).addPathPatterns("/api/**");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manual/**")
                .addResourceLocations("classpath:/manual/")
                .setCachePeriod(300);
    }
}
~~~

Explanation:

- `ExtraMvcConfiguration` has no `@EnableWebMvc`, so it does not intentionally replace `WebMvcAutoConfiguration`.
- `addInterceptors` adds HTTP header `X-App-Mvc: on` to `/api/**` controller mappings. It does not change query parameter formatting and does not block unauthorized requests automatically.
- `addResourceHandlers` separately registers `/manual/**` → `classpath:/manual/`. The pattern differs from `/assets/**`, so it does not compete for Boot's mapping.
- The 300-second cache is set directly on the manual resource mapping. Meanwhile, `spring.web.resources.cache.period=3600s` is used when Boot creates the default resource mapping for `/assets/**`. Do not assume manually registered mappings inherit all `spring.web.resources.*` settings.

### 8.7. Running the Project and Manual Checks

Requires Maven and JDK 17+. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Once the server starts on port 8080, send:

~~~bash
curl -i "http://localhost:8080/api/status"
curl -i "http://localhost:8080/api/day?value=31/12/2026"
curl -i "http://localhost:8080/assets/info.txt"
curl -i "http://localhost:8080/manual/extra.txt"
~~~

Deterministic HTTP bodies produced by controllers:

~~~text
/api/status          -> mvc-config-ok
/api/day?value=31/12/2026 -> 2026-12-31
~~~

Above, the right-hand side of `->` shows the expected body; it is not verbatim stdout of `curl -i`. The two static file requests return their respective file contents: `assets-ok` and `manual-ok`, possibly with a trailing newline. The `X-App-Mvc: on` header appears on API requests matched by the interceptor. Cache headers and other server headers may vary depending on runtime version and configuration.

If requesting `/static/info.txt`, `/site/info.txt`, or `/info.txt`, do not assume those URLs are valid merely because the file exists on the classpath: the static mapping in this example is `/assets/**`.

### 8.8. Integration Tests with MockMvc

File `src/test/java/com/example/mvcdemo/MvcConfigurationTest.java`:

~~~java
package com.example.mvcdemo;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MvcConfigurationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void propertiesAndJavaConfigurerCoexist() throws Exception {
        mvc.perform(get("/api/day").param("value", "31/12/2026"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-App-Mvc", "on"))
                .andExpect(content().string("2026-12-31"));
    }

    @Test
    void bootStaticResourceMappingUsesMvcAndWebProperties() throws Exception {
        mvc.perform(get("/assets/info.txt"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("assets-ok")));
    }

    @Test
    void javaResourceHandlerIsAdditional() throws Exception {
        mvc.perform(get("/manual/extra.txt"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("manual-ok")));
    }

    @Test
    void invalidDateIsNotAccepted() throws Exception {
        mvc.perform(get("/api/day").param("value", "not-a-date"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

If the project includes Maven Wrapper, use `./mvnw test` (Windows: `mvnw.cmd test`). These tests prove that the same application context combines `spring.mvc.format.date`, `spring.mvc.static-path-pattern`, `spring.web.resources.static-locations`, `WebMvcConfigurer.addInterceptors`, and `addResourceHandlers`.

`MockMvc` does not start a real TCP server. With `@SpringBootTest` and `@AutoConfigureMockMvc` (Boot 3.5), it tests MVC request handling in the test context; to verify real ports, proxies, TLS, and network caching directly, add a `RANDOM_PORT` integration test.

## 9. When Java Config Touches the Exact Same Point Boot Controls

### 9.1. Adding a Mapping with a Different Pattern: Usually Safe

The example in Section 8 picked `/assets/**` for Boot and `/manual/**` for Java, making it easy to predict which handler processes each request.

### 9.2. Adding a Mapping with the Same Pattern: Needs Real Verification

If you change `/manual/**` to `/assets/**` in `addResourceHandlers`, you are asking Java to configure the exact same pattern as `spring.mvc.static-path-pattern`. Boot has logic to avoid registering duplicate handlers for the same pattern in order, so the custom mapping may block the default or produce unpredictable behavior if you do not understand registration order. **Do not assume** `spring.web.resources.static-locations` and property-based caching will still apply untouched to the manually created handler.

### 9.3. Adding a Converter: Does Not Replace All of MVC

If a request uses `@RequestParam OrderId id`, a `Converter<String, OrderId>` can be registered via `addFormatters`, or in Spring Boot as an auto-detected `Converter` bean. `@EnableWebMvc` is not needed just to parse a new data type.

### 9.4. configureMessageConverters and extendMessageConverters

When taking manual control of the `HttpMessageConverter` list without understanding how Boot adds defaults, you can unexpectedly alter JSON/XML/string responses. If you only need to add or tweak a specific converter, consider `extendMessageConverters`, converter beans, or customizers supported by your Boot version. `@ResponseBody` and `@RequestBody` use message conversion; they are not automatically governed by `spring.mvc.format.date` like request parameters are.

### 9.5. CORS and Security

CORS can be configured in Java:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/public/**")
            .allowedOrigins("https://client.example")
            .allowedMethods("GET", "POST");
}
~~~

This is an illustrative method snippet for `WebMvcConfigurer`, not part of the complete project in Section 8. When using Spring Security, configure CORS integration with the security filter chain, as preflight requests can be blocked by filters before reaching MVC. CORS is not authorization; non-browser clients can still call HTTP endpoints unless blocked by authentication/authorization mechanisms.

## 10. Upgrading from Spring Boot 3.x to 4.x: What Must Be Reviewed?

Properties such as `spring.mvc.static-path-pattern`, `spring.mvc.format.date`, `spring.web.resources.static-locations`, and `spring.web.locale-resolver` still appear in Spring Boot 4.1's Common Application Properties table. That **does not mean upgrading is merely bumping a version**:

- **Starters:** 3.5 typically uses `spring-boot-starter-web` for Spring MVC. In 4.1, `spring-boot-starter-webmvc` is preferred; the older `spring-boot-starter-web` is deprecated.
- **Modules/packages:** Boot 4 is modularized, so auto-configuration classes and certain Boot APIs changed packages; code directly importing `org.springframework.boot.autoconfigure...` may require updates.
- **Java/Servlet/Framework:** runtime and API requirements vary across lines; verify the BOM and System Requirements of the specific version.
- **MVC core:** `WebMvcConfigurer` belongs to Spring Framework and remains the primary extension mechanism; still review hooks/options changed in Spring Framework 7.
- **Properties:** check Boot 4.1's appendix directly during migration rather than relying on 3.5 project metadata or 2.x docs.
- **Tests:** test starter/module organization changed in Boot 4; test imports from the Boot 3.5 example are not guaranteed to work verbatim in every 4.x project.

During a migration review, create a table mapping **existing property → runtime component → related Java config → integration test**. Pay special attention to static resources, paths, locales, JSON/formatting, and CORS because they directly affect HTTP behavior.

## 11. Debugging When Properties Are Set Yet Behavior Differs

### 11.1. Verify Property Sources and Effective Values

Check `application.properties`/`application.yaml`, `application-prod.yaml` profiles, environment variables, system properties, and command-line arguments. For example, `--spring.mvc.static-path-pattern=/public/**` can override file values depending on active configuration sources.

If using Actuator `env` and `configprops`, enable/allow access only in appropriate environments and with proper authorization; these endpoints can expose sensitive configuration if security is misconfigured.

### 11.2. Verify Whether Boot MVC Auto-Configuration Is Still Running

Enable debug mode to inspect the Condition Evaluation Report:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

The syntax above is for the Maven plugin in a configured project; you can also run the packaged JAR with `java -jar app.jar --debug`. Search for `WebMvcAutoConfiguration` and matched/not-matched conditions; if `@EnableWebMvc` was added, conditions involving `WebMvcConfigurationSupport` are usually the direct clue.

### 11.3. Check the URL Before Checking the File

If `GET /assets/info.txt` returns 404:

1. Verify `spring.mvc.static-path-pattern` actually equals `/assets/**`.
2. Verify `spring.web.resources.static-locations` points to `classpath:/site/`.
3. Verify the file was copied into the build output/JAR at the right path.
4. Check whether `spring.web.resources.add-mappings` is `false`.
5. Check for `@EnableWebMvc`, `addResourceHandlers`, and overlapping mappings.
6. Check security filters, reverse proxies, and servlet context path; 404 may originate from another layer.

**A 404 does not prove the file is missing on disk**; distinguish URL mapping, physical resource location, packaging, and request routing.

### 11.4. Check Request Formatting and JSON Separately

If `/api/day?value=31/12/2026` returns 400, inspect the conversion service, `spring.mvc.format.date`, `@DateTimeFormat` on the controller, the actual URL-encoded parameter, and custom converters. If `@RequestBody` JSON dates differ from expectations, inspect Jackson and `HttpMessageConverter` beans instead of changing `spring.mvc.format.date`.

### 11.5. Check Interceptors and Filters

`HandlerInterceptor` executes inside Spring MVC handler processing; Servlet `Filter` runs at an earlier layer. Interceptors cannot replace Spring Security filters, do not cover non-MVC servlets, and can be scoped by URL patterns. If the `X-App-Mvc` header is absent on static files in the example, that is because the interceptor only applies to `/api/**`, not evidence that Java config is broken.

## 12. Common Misconceptions and Mistakes

| Misconception | Accurate Understanding |
|---|---|
| `spring.mvc.*` and `spring.web.*` are two spellings of the same namespace | Two configuration groups targeting different components; read each specific property |
| `spring.web.resources.static-locations` sets the public URL | It sets where files are loaded from; the URL in MVC belongs to `spring.mvc.static-path-pattern` |
| `spring.mvc.static-path-pattern` also changes controller URLs | It only sets the static resource mapping pattern; controllers use `@RequestMapping` |
| `spring.mvc.format.date` changes JSON formatting for every DTO | It primarily configures MVC formatting/binding; JSON uses message conversion |
| `WebMvcConfigurer` turns off Boot auto-configuration | `WebMvcConfigurer` without `@EnableWebMvc` is the recommended extension path |
| `@EnableWebMvc` just enables extra MVC features with no side effects | It takes over MVC configuration and causes Boot's `WebMvcAutoConfiguration` to back off |
| Java config always beats `application.properties` | There is no universal rule; inspect binding, bean conditions, registration, and ordering |
| `spring.web.resources.add-mappings=false` blocks all Java resource handlers | It disables Boot's default mappings; the app can still add custom handlers |
| Setting `spring.web.resources.cache.period` adds `Cache-Control` to JSON controllers | The property primarily applies to static resource handling, not automatically to APIs |
| WebFlux can be extended with `WebMvcConfigurer` | WebFlux uses its own APIs such as `WebFluxConfigurer` |
| CORS configuration equals authentication/authorization | CORS is a browser mechanism, not backend access control |
| Testing only status 200 proves configuration is right | You must also verify body, headers, routing, MIME types, caching, security, and data sources |

## 13. Process for Choosing a Customization Method

1. **Identify the layer:** are you configuring the HTTP listener (`server.*`), MVC (`spring.mvc.*`), static resources/locale (`spring.web.*`), JSON serialization, or business logic?
2. **Consult official properties for your exact Boot version.** Prefer properties for standard configuration; they are easier to manage per environment than code edits.
3. **If no suitable property exists, use `WebMvcConfigurer`** to add interceptors, formatters, mappings, CORS, or argument resolvers without replacing the MVC infrastructure.
4. **When writing Java, choose the smallest extension hook.** Do not arbitrarily replace `RequestMappingHandlerAdapter` or enable `@EnableWebMvc`.
5. **Avoid duplicating functionality across multiple places**; if combining them is unavoidable, clearly document ownership and ordering.
6. **Write integration tests for actual behavior**, such as resource HTTP paths, input formats, locale fallbacks, interceptor headers, and response content types.
7. **When upgrading Boot**, audit BOM/starters/packages, property metadata, the Condition Evaluation Report, and all critical tests.

**Conclusion:** `spring.mvc.*` defines conventions specific to Spring MVC, `spring.web.*` supplies shared web policies such as locale and static resources, and Java configuration provides programmatic extension or replacement at targeted points. In a typical Spring Boot project, the lowest-risk pattern is **keeping auto-configuration + using properties for standard conventions + adding `WebMvcConfigurer` for specialized behavior**, switching to `@EnableWebMvc` only when intentionally taking on the entire MVC configuration.

## Official Documentation

- Spring Boot 3.5 — Servlet Web Applications, MVC Auto-configuration, formatting, static content, and content negotiation: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Common Application Properties, `spring.mvc.*` and `spring.web.*`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 4.1 — Common Application Properties: https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html
- Spring Boot 4.1 — Servlet Web Applications: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot — How-to, Spring MVC customization: https://docs.spring.io/spring-boot/how-to/spring-mvc.html
- Spring Boot — Reactive Web Applications, static content: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework — Enable MVC Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html
- Spring Framework — Static Resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Framework — Content Types/Negotiation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html
- Spring Framework — WebMvcConfigurer API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html
