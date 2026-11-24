# WebMvcConfigurer to Extend Existing MVC Configuration

## 1. Problem and Core Principle

Spring Boot auto-configures Spring MVC for most Servlet applications: registering DispatcherServlet, HandlerMapping/HandlerAdapter instances, message converters, static resource handling, formatters, and several other utilities. When an application needs to add an interceptor, CORS policy, formatter, resource handler, or view controller, you usually only need to **add a WebMvcConfigurer**.

In Spring Boot, the common approach is:

```java
@Configuration(proxyBeanMethods = false)
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Register additional interceptors.
    }
}
```

Key point to remember: **do not add @EnableWebMvc** to the configuration above if your goal is to keep the MVC customizations provided by Spring Boot. WebMvcConfigurer is a callback API to contribute configuration into the existing MVC infrastructure; it is not a signal asking to replace the entire default configuration.

@EnableWebMvc has a different purpose: enabling Java-based MVC configuration at the Spring Framework level so the application takes full control of configuration itself. In Boot, this annotation brings WebMvcConfigurationSupport into the context; WebMvcAutoConfiguration has a condition to run only when no bean of that type exists, so declaring custom MVC configuration this way causes Boot's auto-configuration to back off.

## 2. Where Does WebMvcConfigurer Live in Spring MVC?

WebMvcConfigurer belongs to the package:

```java
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
```

It is an interface with default methods. Applications override only the callbacks they need. There is no need to implement the entire interface and no need to manually create DispatcherServlet, RequestMappingHandlerMapping, or RequestMappingHandlerAdapter for ordinary customizations.

You can visualize the processing flow as follows:

```text
HTTP request
     |
     v
Servlet filters (e.g., Spring Security filter chain)
     |
     v
DispatcherServlet
     |
     v
HandlerMapping finds controller/handler
     |
     +--> HandlerInterceptor.preHandle(...)
     |
     v
HandlerAdapter invokes controller
     |
     +--> argument resolvers / data binding / validation
     |
     v
Controller returns result
     |
     +--> HttpMessageConverter writes response
     |
     v
HandlerInterceptor.afterCompletion(...)
     |
     v
HTTP response
```

WebMvcConfigurer callbacks contribute configuration to components in this pipeline. For instance, addInterceptors registers interceptors with handler mappings; addFormatters adds conversion/formatting; addCorsMappings declares CORS; extendMessageConverters modifies the converter list after MVC has set up the default list.

Not every extension point lives at the same layer. Servlet Filters run before DispatcherServlet; HandlerInterceptors run after Spring MVC has selected a handler. Choose the right layer according to the purpose.

## 3. Why Does Spring Boot Recommend WebMvcConfigurer Over @EnableWebMvc?

### 3.1. What Boot Adds

Spring Boot MVC auto-configuration builds on Spring Framework's Java MVC configuration and adds many conveniences, typically including:

- ContentNegotiatingViewResolver and BeanNameViewResolver when appropriate.
- Serving static resources and WebJars.
- Automatic registration of Converter, GenericConverter, and Formatter beans.
- Integration of HttpMessageConverters.
- MessageCodesResolver and ConfigurableWebBindingInitializer per configuration.
- Static index.html support.
- The spring.mvc.* and spring.web.* properties.

Specific features depend on the classpath and application configuration.

### 3.2. How to Preserve Boot Defaults

Create one or more @Configuration classes implementing WebMvcConfigurer, without @EnableWebMvc:

```java
@Configuration(proxyBeanMethods = false)
public class ApiMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://ui.example.test")
                .allowedMethods("GET", "POST");
    }
}

@Configuration(proxyBeanMethods = false)
public class WebInterceptorConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new RequestMarkerInterceptor())
                .addPathPatterns("/api/**");
    }
}
```

Multiple configurers contribute together into the MVC Java configuration. Separating them by responsibility makes them easier to read and test. If multiple callbacks modify the same configuration, check ordering rules and avoid having multiple places compete to modify the same setting.

### 3.3. When to Use @EnableWebMvc?

Use @EnableWebMvc when a plain Spring MVC application needs to enable MVC Java configuration, or when a Spring Boot application **intentionally wants to take full responsibility for all MVC configuration** and does not want to use WebMvcAutoConfiguration.

In a Boot application, before adding this annotation, determine whether you are ready to reconfigure the parts Boot used to provide yourself: static resources, message converters, formatters, view resolvers, binding initializers, content negotiation, and MVC properties.

If you only want to replace a specific component such as RequestMappingHandlerMapping, RequestMappingHandlerAdapter, or ExceptionHandlerExceptionResolver while keeping the rest of Boot, look at WebMvcRegistrations. Boot lets you provide custom implementations via this hook and continues applying appropriate MVC configuration steps. Afterward, you can still use WebMvcConfigurer for the remaining callbacks.

## 4. Commonly Used Callbacks

The groups below are common callbacks in Spring Framework 6.2 / Spring Boot 3.5.

| Requirement | Callback | Example |
| --- | --- | --- |
| Add interceptor | addInterceptors | Request marker, locale, or timing |
| Global CORS configuration | addCorsMappings | Allowed origins/methods/headers |
| Add conversion/formatting type | addFormatters | String to value object, date/time |
| Add static resource mapping | addResourceHandlers | /assets/** to resource locations |
| Register view controller | addViewControllers | Simple page forward |
| Adjust path matching | configurePathMatch | URL matching rules |
| Content negotiation | configureContentNegotiation | Default media type |
| Async MVC | configureAsyncSupport | Timeout and executor for async requests |
| View resolver | configureViewResolvers | Template rendering |
| Add converter to existing list | extendMessageConverters | JSON/XML converter |
| Extend exception resolvers | extendHandlerExceptionResolvers | Additional resolver |
| Add custom argument resolver | addArgumentResolvers | Custom controller parameter type |
| Add custom return value handler | addReturnValueHandlers | Custom controller return type |

Some important callbacks:

### 4.1. Interceptor

```java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(new RequestMarkerInterceptor())
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/health");
}
```

- addPathPatterns restricts the paths where the interceptor applies.
- excludePathPatterns excludes paths.
- You can register multiple interceptors and configure their application order.
- Interceptors are typically shared beans; do not store per-request data in mutable fields of the interceptor.

HandlerInterceptor has preHandle, postHandle, and afterCompletion callbacks. Returning false from preHandle blocks invoking subsequent handlers; the application must complete the appropriate response itself. postHandle runs after the controller but before the view is rendered; for REST response bodies, content is typically handled via message converters during response writing. afterCompletion is suitable for cleanup after the request completes.

**Do not use HandlerInterceptor as the primary authorization protection layer.** The Spring Security filter chain runs at the Servlet filter layer before MVC and has dedicated security mechanisms. Interceptors only handle requests that reach Spring MVC handler mapping; they do not cover every request type the way a filter/security chain does.

### 4.2. CORS

```java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://ui.example.test")
            .allowedMethods("GET", "POST", "PUT")
            .allowedHeaders("Content-Type", "Authorization")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
}
```

The configuration above allows a specific origin to access /api/** endpoints. Some concepts:

- allowedOrigins: permitted origins; includes scheme, host, and port if any.
- allowedMethods: methods permitted in CORS.
- allowedHeaders: headers the client is allowed to send.
- exposedHeaders: response headers that browser-side JavaScript is allowed to read.
- allowCredentials: allows sending credentials such as cookies per CORS policy.
- maxAge: duration the browser can cache preflight results.

When credentials are enabled, do not use allowedOrigins("*"); declare specific origins or consider allowedOriginPatterns under a controlled policy. CORS is a browser mechanism controlling whether JavaScript can read responses; it does not replace authentication/authorization and does not block non-browser clients.

If the application uses Spring Security, integrate CORS configuration into the security chain appropriately (e.g., http.cors(...) together with CorsConfigurationSource when needed). Declaring MVC CORS alone without checking filter order may fail to resolve preflights blocked at the security layer.

### 4.3. Formatter and Converter

Use addFormatters when controllers need to convert a string type to a domain type or format data:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(String.class, RegionCode.class,
            source -> new RegionCode(source.trim().toUpperCase(Locale.ROOT)));
}
```

This is an illustrative example; RegionCode is an application-defined type. Converter<S,T> is usually suitable for simple one-way conversion. Formatter<T> is more suitable when both locale-aware parsing and printing are needed.

Do not put complex business rules into converters. Converters should transform representations; validation/domain services remain responsible for determining whether data is business-valid.

### 4.4. Message Converters

Message converters read request bodies and write response bodies, such as JSON via Jackson. When you only need to **add to or adjust the existing converter list**, prefer extendMessageConverters:

```java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {

    // You can find a matching converter in the list and configure it,
    // or add a specialized converter at the appropriate position.
}
```

configureMessageConverters is a callback to configure the converter list. In plain Spring MVC, when adding converters via this method, registration of default converters may be disabled. In Boot applications, WebMvcAutoConfiguration also contributes converter beans and default converters; nevertheless, if your goal is to adjust the already-built list, extendMessageConverters states the intent clearly and helps preserve default converters.

Converter order matters: an earlier matching converter can handle the response first, especially when the client sends Accept: */*. Do not insert an overly broad converter at the front of the list if it might claim media types that Jackson or default converters handle well.

Spring Boot also supports contributing HttpMessageConverter as beans and the HttpMessageConverters mechanism to customize converters at the Boot level. If you only need to configure ObjectMapper, look at the corresponding Jackson/Boot mechanism before replacing the entire converter list.

### 4.5. Argument Resolvers and Return Value Handlers

addArgumentResolvers adds resolvers for custom controller parameter types. addReturnValueHandlers adds handlers for custom return types. Both callbacks **supplement** support; they do not replace built-in mechanisms for parameters/return values already supported by Spring MVC.

If you need to change how Spring handles built-in types, you must inspect deeper RequestMappingHandlerAdapter configuration and consider impacts on default resolvers. Do not override the entire list just to handle one small type.

## 5. Runnable Example: Adding Interceptor and CORS While Keeping Default JSON

The example uses **Java 17 and Spring Boot 3.5.0**. The application has an endpoint returning JSON; WebMvcConfigurer adds an interceptor setting a response header and a CORS policy for the frontend. Tests use MockMvc to verify:

1. The endpoint still serializes JSON with the default converter.
2. The interceptor is applied to /api/**.
3. The response includes the CORS header when the request sends an allowed Origin.

### Directory Structure

```text
webmvc-configurer-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── WebMvcConfigurerDemoTest.java
```

### File pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webmvc-configurer-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

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
</project>
```

### File src/test/java/example/WebMvcConfigurerDemoTest.java

```java
package example;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = WebMvcConfigurerDemoTest.TestApplication.class)
@AutoConfigureMockMvc
class WebMvcConfigurerDemoTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void addsInterceptorAndKeepsDefaultJsonConversion() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content()
                        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Hello from MVC"))
                .andExpect(header().string("X-MVC-Extension", "active"));
    }

    @Test
    void appliesCorsPolicyForAllowedOrigin() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .header("Origin", "https://ui.example.test"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Access-Control-Allow-Origin",
                        "https://ui.example.test"
                ));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({GreetingController.class, MvcExtensionConfiguration.class})
    public static class TestApplication {
    }

    public record Greeting(String message) {
    }

    @RestController
    public static class GreetingController {

        @GetMapping("/api/greeting")
        public Greeting greeting() {
            return new Greeting("Hello from MVC");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class MvcExtensionConfiguration
            implements WebMvcConfigurer {

        @Override
        public void addInterceptors(InterceptorRegistry registry) {
            registry.addInterceptor(new HandlerInterceptor() {
                @Override
                public boolean preHandle(
                        HttpServletRequest request,
                        HttpServletResponse response,
                        Object handler) {

                    response.setHeader("X-MVC-Extension", "active");
                    return true;
                }
            }).addPathPatterns("/api/**");
        }

        @Override
        public void addCorsMappings(CorsRegistry registry) {
            registry.addMapping("/api/**")
                    .allowedOrigins("https://ui.example.test")
                    .allowedMethods("GET");
        }
    }
}
```

### Running the Tests

In the directory containing pom.xml, using JDK 17+ and Maven:

```bash
java -version
mvn -version
mvn test
```

**Expected result:** two JUnit tests pass and Maven finishes with BUILD SUCCESS if dependencies download successfully. The code does not call System.out.println, so there is no fixed business stdout; detailed reports are in target/surefire-reports.

### Test Explanation

- addsInterceptorAndKeepsDefaultJsonConversion: verifies the endpoint still returns JSON and the header set by the interceptor. This proves the application added callbacks while still using MVC message conversion.
- appliesCorsPolicyForAllowedOrigin: sends an allowed frontend Origin header and checks that the response contains Access-Control-Allow-Origin.
- TestApplication uses @EnableAutoConfiguration but **does not** use @EnableWebMvc. Therefore, WebMvcAutoConfiguration still participates in the context.
- MvcExtensionConfiguration overrides only the two needed callbacks; the remaining callbacks keep default behavior.

The example does not open a real server; MockMvc runs requests through Spring MVC inside the test context. When deploying CORS with Spring Security, also test OPTIONS preflight and security filter ordering in the real configuration.

## 6. Other Extension Points Worth Knowing

### 6.1. Static Resources

Use addResourceHandlers when you need to map a URL pattern to a resource location:

```java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/manual/**")
            .addResourceLocations("classpath:/manual/");
}
```

This example serves resources under src/main/resources/manual/ at URL /manual/**. Pay attention to cache control, versioning, content types, and public scope of resources. Spring Boot already has default static resource handling for supported locations; add mappings only for specific needs.

### 6.2. View Controllers

addViewControllers suits simple routes that just forward to a view without needing controller logic:

```java
@Override
public void addViewControllers(ViewControllerRegistry registry) {
    registry.addViewController("/help").setViewName("help");
}
```

The snippet above assumes the application has a view named help and an appropriate ViewResolver. It does not create templates automatically.

### 6.3. Path Matching and Content Negotiation

configurePathMatch adjusts how Spring MVC matches paths. Before changing rules such as trailing slash or parsed PathPattern, check existing routes, proxies/reverse proxies, and integration tests.

configureContentNegotiation controls how MVC decides media types based on the request. For REST APIs, prefer Accept headers and explicit content types; avoid enabling path extension negotiation without a specific compatibility reason.

### 6.4. Async Request Handling

configureAsyncSupport configures timeouts and executors for controllers returning async types such as Callable or DeferredResult. Do not confuse the MVC async executor with the @Async executor or scheduler; they have separate lifecycles and configurations. If providing a custom executor, bound resources, handle shutdown, and monitor queue/latency.

### 6.5. Exception Resolvers

extendHandlerExceptionResolvers is appropriate when you want to append resolvers after the default list. configureHandlerExceptionResolvers is a callback to configure the list; when adding resolvers manually, understand how default resolver registration is affected. For REST APIs, @RestControllerAdvice is usually a more readable choice for controller/application exception handling than replacing the entire resolver chain.

## 7. When You Need to Replace an MVC Infrastructure Component

If your requirement goes beyond WebMvcConfigurer callbacks, consider in order:

1. Is there a property or bean extension point provided by Boot for this goal?
2. Can the corresponding WebMvcConfigurer callback be used?
3. If you need to replace certain core components while keeping other Boot parts, check WebMvcRegistrations.
4. Use @EnableWebMvc only when you want to take full control of MVC configuration yourself.
5. Avoid declaring WebMvcConfigurationSupport or subclassing infrastructure classes yourself unless truly needed; it can make Boot auto-configuration back off.

WebMvcRegistrations is Spring Boot's hook to replace RequestMappingHandlerMapping, RequestMappingHandlerAdapter, or ExceptionHandlerExceptionResolver implementations. Custom instances are still initialized/configured by MVC through the appropriate pipeline. This is a narrower choice than turning off all Boot MVC auto-configuration.

## 8. Distinguishing WebMvcConfigurer from Filter and WebFluxConfigurer

| Tool | Layer | When Appropriate |
| --- | --- | --- |
| WebMvcConfigurer | Spring MVC / Servlet DispatcherServlet | Interceptors, MVC CORS, formatters, converters, views, path matching |
| Servlet Filter | Servlet container before DispatcherServlet | Request/response wrapping, correlation id, cross-cutting HTTP processing |
| Spring Security SecurityFilterChain | Security filter chain | Authentication, authorization, security headers, CSRF |
| WebFluxConfigurer | Reactive Spring WebFlux | Reactive routers/handlers, codecs, WebFlux CORS, and reactive configurations |

Do not use WebMvcConfigurer in a pure WebFlux application; the two stacks have different configuration APIs. If an application has both Servlet and Reactive dependencies, check which web application type Boot selects and test the right stack.

## 9. Common Pitfalls

1. **Adding @EnableWebMvc just to register an interceptor.** This can cause Boot MVC auto-configuration to back off. You only need @Configuration implements WebMvcConfigurer.
2. **Subclassing WebMvcConfigurationSupport without understanding the impact.** In Boot, a bean of this type makes WebMvcAutoConfiguration fail the missing-bean condition.
3. **Overriding configureMessageConverters to add one converter.** This can alter default converter registration in plain Spring MVC. Prefer extendMessageConverters or converter beans/HttpMessageConverters in Boot.
4. **Adding an overly broad or misordered converter.** An earlier converter may claim media types and alter JSON/XML responses. Check the Accept header and converter order.
5. **Using interceptors as a security layer.** Interceptors do not cover all requests like a filter chain; use Spring Security for authorization.
6. **Allowing CORS * with credentials.** CORS credentials require a specific origin policy; do not use wildcard origins with credentials.
7. **Forgetting CORS at the Spring Security layer.** Preflights may be rejected by filters before reaching MVC.
8. **Storing request state in a singleton interceptor field.** Multiple requests can run concurrently; use request attributes or local variables.
9. **Creating an interceptor without path restrictions.** Without specifying patterns, it may apply more broadly than intended, including unrelated routes.
10. **Adding an argument resolver to replace a built-in resolver.** addArgumentResolvers is an additive mechanism; replacing built-in support requires deeper adapter configuration.
11. **Adding a resource handler colliding with default mappings.** This can alter static resource resolution or cache behavior. Check URL patterns and locations.
12. **Using Servlet APIs in WebFlux.** WebMvcConfigurer is only for the Spring MVC Servlet stack; use WebFluxConfigurer for the reactive stack.
13. **Not testing that Boot defaults still work.** Testing only the interceptor is insufficient; test JSON conversion, static resources, or Boot features the application needs to keep.
14. **Relying on unverified configurer order.** If multiple configurers edit the same list/setting, assign clear responsibilities and test the final result.

## 10. How to Diagnose When Configuration Has No Effect

1. Confirm whether the application is running Servlet MVC or WebFlux.
2. Check if @EnableWebMvc or a WebMvcConfigurationSupport bean is causing Boot auto-configuration to back off.
3. Check whether the @Configuration class implementing WebMvcConfigurer is component-scanned or imported into the context.
4. Check the interceptor's addPathPatterns/excludePathPatterns and the actual routes.
5. Test CORS with a request carrying Origin; for preflight use OPTIONS, Access-Control-Request-Method, and Access-Control-Request-Headers.
6. If JSON does not serialize as expected, inspect the HttpMessageConverter list, its order, and the Accept header.
7. Use --debug to inspect Spring Boot's condition evaluation report; if the Actuator conditions endpoint is enabled, check /actuator/conditions.
8. Check the security filter chain ahead of MVC if requests are blocked before reaching the controller.
9. Inspect logs for DispatcherServlet, handler mappings, and exception resolvers when routes are not found.

## 11. Checklist Before Adding WebMvcConfigurer

- [ ] Confirmed this is a Spring MVC application on the Servlet stack.
- [ ] Used @Configuration implementing WebMvcConfigurer.
- [ ] Did not add @EnableWebMvc if Boot MVC auto-configuration should be preserved.
- [ ] Overrode only the needed callbacks.
- [ ] Interceptors have appropriate path includes/excludes and do not replace Spring Security.
- [ ] CORS uses intentional origins/methods/headers; credentials are not paired with wildcard origin.
- [ ] If adding converters, checked extendMessageConverters or the HttpMessageConverters mechanism.
- [ ] If replacing HandlerMapping/Adapter/ExceptionResolver, checked WebMvcRegistrations.
- [ ] Tested JSON conversion and Boot utilities the application needs to preserve.
- [ ] If using Spring Security, tested both regular requests and CORS preflights through the filter chain.
- [ ] Included tests for routes, interceptors, CORS, converters, and static resources per actual needs.

## 12. Self-Check Questions

**Question 1.** To add an interceptor in Spring Boot while keeping default MVC configuration, which annotation is needed?  
**Answer:** Create a @Configuration implementing WebMvcConfigurer; do not add @EnableWebMvc.

**Question 2.** Why can @EnableWebMvc cause WebMvcAutoConfiguration to back off?  
**Answer:** It imports MVC configuration based on WebMvcConfigurationSupport; Boot's auto-configuration has a missing-bean condition for that type.

**Question 3.** To add a converter while keeping default converters, which callback should you look at?  
**Answer:** extendMessageConverters, or contributing an HttpMessageConverter bean/HttpMessageConverters per Boot's mechanism.

**Question 4.** How do HandlerInterceptor and Servlet Filter differ?  
**Answer:** Filters run at the Servlet layer before DispatcherServlet; interceptors run inside Spring MVC after a handler has been selected.

**Question 5.** Should interceptors be used to decide whether a user has permission to access an endpoint?  
**Answer:** Do not use them as the primary security layer; use the Spring Security filter chain.

**Question 6.** Does addArgumentResolvers replace Spring MVC's built-in resolvers?  
**Answer:** No. It adds resolvers supporting custom parameter types; replacing built-in support requires deeper RequestMappingHandlerAdapter configuration.

**Question 7.** When needing a custom RequestMappingHandlerAdapter while still keeping Boot MVC customizations, what should you look at?  
**Answer:** WebMvcRegistrations.

**Question 8.** Can WebMvcConfigurer be used in a pure WebFlux application?  
**Answer:** No. WebFlux has WebFluxConfigurer and a separate reactive pipeline.

## Official References

- Spring Boot 3.5 Reference — Servlet Web Applications, Spring MVC Auto-configuration section: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 API — WebMvcAutoConfiguration and @ConditionalOnMissingBean(WebMvcConfigurationSupport.class) condition: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html
- Spring Boot 3.5 Reference — Spring MVC how-to, converters, and switching off default MVC configuration: https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html
- Spring Boot 3.5 Reference — Testing Spring Boot Applications, @WebMvcTest: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 Reference — MVC Config: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config.html
- Spring Framework 6.2 Javadoc — WebMvcConfigurer: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html
- Spring Framework 6.2 Reference — Message Converters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html
- Spring Framework 6.2 Reference — Interceptors: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html

**Takeaway:** In Spring Boot, WebMvcConfigurer is the way to extend existing MVC configuration. Use @Configuration and override only the needed callbacks; reserve @EnableWebMvc for cases where you want to manage all of MVC yourself. When adding converters, prefer extendMessageConverters; when securing requests, use Spring Security instead of interceptors.
