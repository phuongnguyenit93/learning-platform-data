# Registering Interceptors, View Controllers, and Resource Handlers in Spring Boot MVC

## 1. Three Extension Points Solving Three Different Jobs

In a Spring Boot application using **Spring MVC (Servlet stack)**, extending HTTP handling does not always require writing a new controller for every path. Spring MVC provides the `WebMvcConfigurer` interface to register interceptors, map URLs directly to views, and configure how static resources are served.

| Extension Point | Method on WebMvcConfigurer | Role | Example |
|---|---|---|---|
| Handler interceptor | addInterceptors(InterceptorRegistry) | Execute logic before/after an MVC handler for selected URL scopes | Attach observability metadata, measure MVC processing time |
| View controller | addViewControllers(ViewControllerRegistry) | Bind a URL to a view name or simple redirect without a business-logic controller | /welcome → welcome template; /old → redirect /welcome |
| Resource handler | addResourceHandlers(ResourceHandlerRegistry) | Map URLs to static resources from the classpath or permitted directories | /demo-assets/site.css → classpath:/demo-assets/site.css |

All three mechanisms belong to **Spring MVC**. Do not use `WebMvcConfigurer`, `HandlerInterceptor`, or Servlet API classes directly in a WebFlux-only application. WebFlux has its own configuration and filter mechanisms.

General processing flow in MVC:

~~~text
Client sends HTTP request
         |
         v
Servlet Filter chain (including Spring Security if enabled)
         |
         v
DispatcherServlet
         |
         v
HandlerMapping selects matching handler and interceptors
         |
         +--> preHandle(...) of interceptors
         |
         +--> HandlerAdapter invokes handler:
         |      - @Controller / @RestController
         |      - ViewController
         |      - ResourceHttpRequestHandler
         |
         +--> postHandle(...) when applicable
         |
         +--> ViewResolver / view rendering if any
         |
         +--> afterCompletion(...) when request finishes
         |
         v
HTTP response to client
~~~

The diagram depicts a normal, synchronous MVC request. With asynchronous processing, callback ordering has additional branches, explained below.

## 2. Configuring MVC in Spring Boot: Use WebMvcConfigurer

In Spring Boot 3.5.x, the common extension mechanism is creating a `@Configuration implements WebMvcConfigurer` class and overriding the needed methods:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcConfiguration implements WebMvcConfigurer {
    // Override methods that need customization.
}
~~~

Spring Boot automatically integrates `WebMvcConfigurer` beans into the auto-configured MVC setup. Multiple `WebMvcConfigurer` beans can exist across different modules; Spring aggregates the configurations when building the MVC infrastructure.

**Do not add @EnableWebMvc just to register an interceptor, view controller, or resource handler.** In Spring Boot, that annotation switches to self-managed Spring MVC configuration, disabling several of Boot's default MVC auto-configurations, such as certain static resource settings, view resolvers, and web conventions. Only use `@EnableWebMvc` when you intentionally want to configure MVC completely on your own.

Recommended approach:

- Use `WebMvcConfigurer` when you want to **add** features while preserving Spring Boot's MVC auto-configuration.
- Use `@Controller`/`@RestController` when a URL needs business processing, dynamic data, or JSON responses.
- Use `application.yaml` and built-in properties for simple customizations, such as changing the default static path pattern.
- Only replace deeper framework configuration when truly necessary and when you understand the impact on `HandlerMapping`, `ViewResolver`, message converters, and related mechanisms.

In the examples, packages and APIs target **Spring Boot 3.5.x, Spring Framework 6.2, Java 17+**. They require appropriate Spring Boot dependencies; they are not standalone programs compilable with plain `javac` without the Spring classpath.

## 3. HandlerInterceptor: Purpose and Lifecycle

`HandlerInterceptor` lets the application run logic around a handler managed by `HandlerMapping`. It does not replace controllers; it supports cross-cutting request tasks.

Three main callbacks:

| Callback | When It Runs | Practical Use |
|---|---|---|
| preHandle(request, response, handler) | After selecting the handler, before invoking the handler | Prepare request context, add observability data, check auxiliary conditions |
| postHandle(request, response, handler, modelAndView) | After the handler runs normally and before rendering the view in a synchronous flow | Add data to ModelAndView if present; usually no view exists for @ResponseBody |
| afterCompletion(request, response, handler, exception) | When synchronous MVC processing completes, after rendering if any | Clean up request-bound resources, log/record completion metrics |

`preHandle` returns **true** to continue the execution chain. If it returns **false**, `DispatcherServlet` stops processing the handler at this step; the interceptor must ensure an appropriate response is set if needed. Do not assume returning `false` automatically produces HTTP 403 or structured error JSON.

When multiple interceptors are registered, `preHandle` methods are typically called in order, while completion callbacks run in reverse order for interceptors whose `preHandle` succeeded. An interceptor returning `false` prevents subsequent interceptors and the handler from running.

`postHandle` is not guaranteed to be able to alter status or body once the response has already been written/committed. In controllers returning JSON via `@ResponseBody`, `ModelAndView` is typically `null`; model-modifying logic is only relevant when a view is rendered.

### How Do Interceptors and Servlet Filters Differ?

- **Servlet Filter** sits before `DispatcherServlet` in the servlet filter chain, can handle requests that never reach an MVC `HandlerMapping`, and fits security/cross-cutting concerns at the servlet layer.
- **HandlerInterceptor** applies only to handler mappings managed by Spring MVC's configuration, has access to the selected handler object, and uses MVC patterns to scope URLs.
- **Controller** executes the business logic of a specific endpoint.

Do not use an interceptor as the sole protection layer for authentication or authorization. Spring Framework recommends Spring Security or mechanisms built on the Servlet filter chain to avoid interceptor path patterns missing endpoints that need protection.

## 4. Registering Interceptors with InterceptorRegistry

Registration pattern:

~~~java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(demoInterceptor)
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/public/**")
            .order(0);
}
~~~

Where:

- `addInterceptor` accepts a `HandlerInterceptor` instance, usually managed by Spring as a bean so dependency injection can be used.
- `addPathPatterns("/api/**")` applies only to API paths under `/api`.
- `excludePathPatterns("/api/public/**")` excludes public URLs from this interceptor.
- `order(0)` sets the priority of the interceptor registration; lower order numbers run first in `preHandle`.

Patterns apply to the request path segment matched by MVC, not the full URL with scheme, hostname, or query string. When a servlet context path or custom servlet mapping is configured, test the actual paths; do not manually prepend the context path to every pattern.

For example, with pattern `/api/**`:

| Request | Interceptor Runs in Example? |
|---|---|
| GET /api/hello | Yes |
| GET /api/orders/42 | Yes |
| GET /api/public/ping | No, excluded |
| GET /welcome | No |
| GET /demo-assets/site.css | No |

When applying an interceptor globally with `/**`, it can affect view controllers and static resource handlers as well, because they are also MVC handlers. Therefore, use `addPathPatterns`/`excludePathPatterns` deliberately; do not register `/**` and branch on paths with `if` statements inside `preHandle` when clear pattern configuration is possible.

Modern Spring MVC versions use `PathPatternParser` and dedicated path matching strategies. Do not assume all legacy Ant-style patterns behave identically after switching matching strategies. Test real routes, especially multiple `/` characters, path variables, extensions, and encoded URLs.

## 5. ViewControllerRegistry: Serving Views Without Business Logic

A view controller is useful when a URL only needs to render a static template or redirect to another URL. It avoids writing a controller just to return a view-name string.

Example:

~~~java
@Override
public void addViewControllers(ViewControllerRegistry registry) {
    registry.addViewController("/welcome").setViewName("welcome");
    registry.addRedirectViewController("/old-welcome", "/welcome");
}
~~~

- `/welcome` maps to view name `welcome`.
- A `ViewResolver` must be able to locate and render that view, such as Thymeleaf resolving `src/main/resources/templates/welcome.html`.
- `/old-welcome` creates a redirect to `/welcome`. The client receives an HTTP redirect response (typically 3xx) and can then issue a new request to `Location`.

**A view name is a logical view name, not an absolute file path and not a REST API response body.** If using Thymeleaf, the appropriate dependency and template must exist. If the template is missing or `ViewResolver` cannot resolve it, the mapping exists yet the request will fail during rendering.

Notes:

- View controllers are not suitable when you need to fetch data from a database, attach user-specific models, run business logic, or handle complex request parameters; use `@Controller` for those tasks.
- Do not share the same URL between a `@RequestMapping` controller and a view controller. Controller mappings may take precedence and own the URL, causing 405/415 or unexpected results.
- Do not use view controllers as a page security mechanism. Access permissions must be enforced via appropriate security configuration.
- If an endpoint only needs to return an HTTP status without a view, use a proper controller or the status controller mechanism supported by your API version instead of creating an unnecessary template.
- If the application has a context path, prefer generating links via the template engine's URL mechanism rather than hard-coding host and port.

## 6. ResourceHandlerRegistry: Mapping URLs to Static Files

Resource handlers serve static assets such as CSS, JavaScript, images, and public documents. Spring MVC uses `ResourceHttpRequestHandler` along with `ResourceResolver`/`ResourceTransformer` when a resource chain is configured.

Example:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/demo-assets/**")
            .addResourceLocations("classpath:/demo-assets/")
            .setCacheControl(
                    CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic()
            );
}
~~~

How to read this:

- `addResourceHandler("/demo-assets/**")` registers the URL pattern. The part after the prefix is used to locate the matching resource.
- `addResourceLocations("classpath:/demo-assets/")` specifies where packaged files live on the classpath.
- The trailing `/` on the resource location directory ensures the root directory is resolved properly.
- `Cache-Control` instructs caches to store the response for 10 minutes. Actual caching behavior can also be affected by proxies, global settings, and other headers.

For `src/main/resources/demo-assets/site.css`, the corresponding URL is `/demo-assets/site.css`.

When a resource does not exist, the handler typically returns 404 (such as `NoResourceFoundException` in modern Spring MVC versions). There is no need to write `@GetMapping` for every CSS or JavaScript file.

### Spring Boot's Default Resources

While keeping MVC auto-configuration, Spring Boot 3.5 serves static content by default from common classpath locations:

- `classpath:/static/`
- `classpath:/public/`
- `classpath:/resources/`
- `classpath:/META-INF/resources/`

In standard configuration, default resources are mapped under `/**`. You can adjust this with:

~~~yaml
spring:
  mvc:
    static-path-pattern: "/static/**"
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "classpath:/public/"
~~~

The configuration above changes the pattern and location list for **the default resource mapping created by Spring Boot**. Meanwhile, `addResourceHandlers` registers an additional mapping with developer-chosen URL/locations. Adding a custom handler does not force you to drop all of Boot's static locations.

**Avoid registering a `/**` handler arbitrarily** because it can conflict with default static mappings and make mistyped API paths look like missing-resource errors. Using distinct prefixes like `/demo-assets/**`, `/docs-assets/**`, or `/images/**` is clearer and easier to control.

### Resources Outside the JAR

File system resource locations can be used in appropriate environments, for example:

~~~java
registry.addResourceHandler("/manuals/**")
        .addResourceLocations("file:/srv/public-manuals/");
~~~

This is an OS- and deployment-dependent illustration. You must verify that the directory exists, read permissions are set, files are intended to be public, and access is restricted properly. Never point a resource handler to a directory containing secrets, internal configuration, source code, or unvetted user uploads. Never concatenate user-supplied paths arbitrarily onto a filesystem-backed location.

### Resource Caching and Fingerprinting

For assets whose content changes while keeping the same URL, overly long cache lifetimes can cause clients to use stale versions after deployment. For assets versioned by content hash, longer cache lifetimes are safe.

Spring MVC supports resource chains with `VersionResourceResolver`, shown in a separate example:

~~~java
registry.addResourceHandler("/build-assets/**")
        .addResourceLocations("classpath:/build-assets/")
        .resourceChain(true)
        .addResolver(
                new VersionResourceResolver()
                        .addContentVersionStrategy("/**")
        );
~~~

With the content version strategy, a hash is generated from the resource content. For templates to generate versioned URLs, integrate `ResourceUrlProvider` or `ResourceUrlEncodingFilter` according to your framework/template engine. Do not simply add `VersionResourceResolver` and assume every HTML link will automatically rewrite its URL. This is a different configuration option; do not insert the same pattern into two duplicate registrations.

## 7. Complete Example: Spring Boot 3.5.x and Java 17+

To run and observe all three mechanisms, create a Spring Boot 3.5.x project with Maven (or use an existing project) with dependencies:

- `spring-boot-starter-web`: Spring MVC and embedded servlet server.
- `spring-boot-starter-thymeleaf`: `ViewResolver` for HTML templates.
- `spring-boot-starter-test`: used for the test examples in the next section.

The classes below are placed in package `example.mvc`. Required files:

~~~text
src/
  main/
    java/example/mvc/
      MvcDemoApplication.java
      DemoInterceptor.java
      MvcConfiguration.java
      DemoApiController.java
    resources/
      templates/welcome.html
      demo-assets/site.css
  test/
    java/example/mvc/
      MvcConfigurationTest.java
~~~

### 7.1. Main Application

File `src/main/java/example/mvc/MvcDemoApplication.java`:

~~~java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

So Spring Boot component scanning finds the `@Component`, `@Configuration`, and `@RestController` classes below, place them in the same package or subpackages of the `@SpringBootApplication` class.

### 7.2. Interceptor as a Spring Bean

File `src/main/java/example/mvc/DemoInterceptor.java`:

~~~java
package example.mvc;

import java.util.concurrent.TimeUnit;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class DemoInterceptor implements HandlerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(DemoInterceptor.class);

    private static final String START_NANOS =
            DemoInterceptor.class.getName() + ".startNanos";

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        request.setAttribute(START_NANOS, System.nanoTime());
        response.setHeader("X-Demo-Interceptor", "applied");
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        Object value = request.getAttribute(START_NANOS);
        if (value instanceof Long start) {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start
            );
            log.debug("MVC handler completed in {} ms", elapsedMs);
        }
    }
}
~~~

Purpose of the example:

- `preHandle` sets a request attribute to record the start timestamp and adds an observable response header with a deterministic value.
- `afterCompletion` reads the timestamp and logs a debug message about the time spent passing through the MVC handler.
- The interceptor is managed by Spring via `@Component` and injected into the configuration, allowing other dependencies to be injected if needed.
- The `X-Demo-Interceptor` response header is an observable signal to verify the mapping, not a security mechanism.

The millisecond count in the log is not fixed. This measurement covers a slice of the MVC lifecycle, not total latency from the browser across the network and reverse proxies. If standardized metrics or async requests are required, choose a more appropriate measurement point.

### 7.3. Registering All Three Extension Points

File `src/main/java/example/mvc/MvcConfiguration.java`:

~~~java
package example.mvc;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcConfiguration implements WebMvcConfigurer {

    private final DemoInterceptor demoInterceptor;

    public MvcConfiguration(DemoInterceptor demoInterceptor) {
        this.demoInterceptor = demoInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(demoInterceptor)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**")
                .order(0);
    }

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addViewController("/welcome")
                .setViewName("welcome");

        registry.addRedirectViewController(
                "/old-welcome", "/welcome"
        );
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/demo-assets/**")
                .addResourceLocations("classpath:/demo-assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(10))
                                .cachePublic()
                );
    }
}
~~~

Explanation:

- A single `WebMvcConfigurer` can override all three methods together, or they can be split across multiple `@Configuration` classes as the application grows.
- The interceptor applies only to `/api/**`, excluding `/api/public/**`.
- `/welcome` and `/old-welcome` are mapped directly to a view or redirect.
- Resources in `classpath:/demo-assets/` are exposed under the `/demo-assets/**` prefix with a 10-minute cache policy.

The class does not have `@EnableWebMvc`, thus keeping Spring Boot's standard MVC auto-configuration model.

### 7.4. API Controller to Test the Interceptor

File `src/main/java/example/mvc/DemoApiController.java`:

~~~java
package example.mvc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoApiController {

    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Because `@RestController` writes return values directly, the results of the two endpoints are the response bodies `hello` and `pong`. They do not look up view templates of the same name.

### 7.5. HTML View for the View Controller

File `src/main/resources/templates/welcome.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Welcome</title>
    <link rel="stylesheet" th:href="@{/demo-assets/site.css}">
</head>
<body>
    <h1>Welcome Page</h1>
    <p>This is the view mapped to /welcome.</p>
</body>
</html>
~~~

Thymeleaf resolves view name `welcome` to template `welcome.html` when the appropriate starter is on the classpath. The `th:href` expression computes asset URLs relative to the application's context path rather than forcing a hard-coded `/` root.

### 7.6. CSS File in Custom Resource Location

File `src/main/resources/demo-assets/site.css`:

~~~css
body {
    font-family: sans-serif;
    margin: 2rem;
}

h1 {
    color: #245a92;
}
~~~

The resource handler maps `/demo-assets/site.css` to the `site.css` file above. No `@GetMapping` is needed to serve it.

### 7.7. Running and Observing Results

In a Maven project with Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

By default, the server uses port 8080 if not overridden. Adjust the URLs in the commands below to match your project's `server.port` configuration.

Check the intercepted endpoint:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Key expected parts of the response include:

~~~text
HTTP/1.1 200
X-Demo-Interceptor: applied

hello
~~~

This is a selective illustration, not verbatim output of every HTTP header on every embedded server. Other headers, header ordering, charset, or protocol details may vary.

Check the excluded route:

~~~bash
curl -i http://localhost:8080/api/public/ping
~~~

The body is `pong`; the `X-Demo-Interceptor` header will not be added by `DemoInterceptor` in the example because `/api/public/**` is excluded.

Check the view:

~~~bash
curl -i http://localhost:8080/welcome
~~~

If the Thymeleaf dependency and template are packaged properly, the response contains the HTML of the welcome page.

Check the redirect:

~~~bash
curl -i http://localhost:8080/old-welcome
~~~

The response will be an HTTP redirect with `Location` pointing to `/welcome`. Use `curl -L` to tell `curl` to follow redirects.

Check the static asset:

~~~bash
curl -i http://localhost:8080/demo-assets/site.css
~~~

If the resource exists, the response contains the CSS. `Cache-Control` may contain `max-age=600` and `public` due to the 10-minute cache setting. In practice, browsers/proxies may apply additional caching policies.

## 8. Automated Testing with MockMvc

You can verify the mapping mechanisms clearly with `MockMvc`. The example below targets the project in Section 7, with `spring-boot-starter-test`.

File `src/test/java/example/mvc/MvcConfigurationTest.java`:

~~~java
package example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcConfigurationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void interceptorRunsForApiRoute() throws Exception {
        mvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Demo-Interceptor", "applied"))
                .andExpect(content().string("hello"));
    }

    @Test
    void excludedPathDoesNotRunInterceptor() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        "X-Demo-Interceptor"))
                .andExpect(content().string("pong"));
    }

    @Test
    void viewControllerResolvesViewName() throws Exception {
        mvc.perform(get("/welcome"))
                .andExpect(status().isOk())
                .andExpect(view().name("welcome"));
    }

    @Test
    void redirectViewControllerRedirects() throws Exception {
        mvc.perform(get("/old-welcome"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/welcome"));
    }

    @Test
    void resourceHandlerServesCss() throws Exception {
        mvc.perform(get("/demo-assets/site.css"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("text/css"));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

On Windows, use `mvnw.cmd test`. If Spring Security is added to the project later, `MockMvc` tests may need mock user configuration or matching security policies; a request rejected by Spring Security before `DispatcherServlet` does not prove the MVC registration is wrong.

`MockMvc` tests mappings and processing at the Spring MVC layer; it does not replace end-to-end testing over real HTTP sockets, reverse proxies, caches/CDNs, file permissions, or TLS in production deployments.

## 9. Interceptors in Asynchronous Requests

The example in Section 7 uses synchronous requests. For controllers returning `Callable`, `DeferredResult`, `WebAsyncTask`, or other asynchronous types in Spring MVC, the interceptor lifecycle has additional details to watch.

When a handler begins asynchronous processing:

- The request may release the initial servlet thread before the response is finished.
- `postHandle` and `afterCompletion` callbacks do not necessarily run during the initial dispatch.
- If the interceptor implements `AsyncHandlerInterceptor`, `afterConcurrentHandlingStarted` can be invoked when MVC switches to concurrent processing.
- When the async result is dispatched back, the interceptor can be invoked again; logic must not assume `preHandle` runs only once over the entire lifecycle of a request.

Therefore, measuring duration via a request attribute in the example should be viewed as a practice exercise for standard requests. For async requests, design measurements around the appropriate lifecycle so metrics are not double-recorded or lost on timeouts/disconnects.

When cleanup must be guaranteed even on async timeouts and errors, look at callbacks and APIs such as `DeferredResultProcessingInterceptor` or `CallableProcessingInterceptor` if using MVC async; do not rely solely on `finally` on the initial thread.

## 10. View Controllers, Redirects, and ViewResolver Boundaries

A view controller runs no business logic, yet still passes through `DispatcherServlet` and can trigger matching interceptors. To return HTML:

1. Request matches `/welcome`.
2. MVC selects the view controller.
3. The view controller supplies view name `welcome`.
4. `ViewResolver` (for example, `ThymeleafViewResolver`) locates the matching template.
5. The view is rendered into an HTML response.

If `spring-boot-starter-thymeleaf` is removed without a replacement `ViewResolver`, `/welcome` will not automatically turn into a response body `"welcome"`. A logical view name requires an actual view engine or resolver.

Redirect differs from rendering HTML:

- Rendering a view typically returns a response containing the HTML of the current page.
- A redirect returns 3xx with `Location`, and the client decides whether to send a new request.
- Fixed redirects like `/old-welcome` → `/welcome` are appropriate for legacy paths.
- If a redirect URL is constructed from user input, validate the destination to prevent open redirects.

When using a servlet context path such as `/shop`, test redirect and asset URLs within that context. Do not assume every URL starting with `/` will be treated identically to public URLs at an external proxy.

If you need to return JSON, specific status codes, per-request models, or paginated data, use `@Controller`/`@RestController` and `ResponseEntity` instead of overusing view controllers.

## 11. Resource Handlers, Default Static Mapping, and 404 Handling

Several common points of confusion:

**(1) Placing CSS under src/main/resources/templates/**

`templates/` is for view engines. Files inside `templates/` are not automatically served as static files over URLs. In the example, CSS resides under `demo-assets/` and is served by the custom resource handler.

**(2) Registering a custom resource handler but requesting the wrong URL**

If configured with `addResourceHandler("/demo-assets/**")` and file `site.css`, the correct URL is `/demo-assets/site.css`. Not `/demo-assets/demo-assets/site.css`.

**(3) Missing trailing / on classpath location**

Write `"classpath:/demo-assets/"` to indicate the root directory clearly. An incorrect location can leave the file packaged inside the JAR while the URL returns 404.

**(4) Default /** handler "catching" wrong requests**

Spring Boot typically maps default static resources under `/**`. If a URL matches no controller, the request can reach `ResourceHttpRequestHandler` and throw a missing-resource error such as `NoResourceFoundException`. That does not necessarily mean a controller was supposed to handle that URL.

When investigating the difference between `NoHandlerFoundException` and `NoResourceFoundException`, check `spring.mvc.static-path-pattern` and `spring.web.resources.add-mappings`. Disabling default static mappings can change the exception type when no handler is found. Do not arbitrarily disable all mappings just to fix a single 404.

**(5) Registering /** manually and overriding normal resources**

An overly broad `/**` handler can compete with default resource mappings or claim unintended URLs. Only register the scope you need, and inspect `HandlerMapping` and existing patterns.

**(6) Clients receive stale CSS after deployment**

Configuring a large `max-age` for unversioned URLs can prevent clients from fetching updates. Use reasonable cache durations, purge CDNs, or fingerprint assets.

**(7) Files outside the JAR classpath**

When using external resources outside the JAR, configure valid `file:` locations and mount the directory into the container upon deployment. A local file path on a developer machine does not automatically exist inside an image or Pod.

## 12. Interaction with Spring Security and Servlet Filters

Interceptors are used for observability or augmenting MVC logic; authentication/authorization policies should be handled by Spring Security.

For example, suppose the app requires users to log in to view `/welcome`. The view controller is only responsible for selecting the view; it does not automatically require login. `SecurityFilterChain` must specify who is allowed to call `/welcome`.

Similarly, `/demo-assets/**` can be public or private depending on policy. Spring MVC simply locates and returns the file; if a URL contains sensitive content, it should not be exposed directly via a resource handler. Just because a file exists in a resource directory does not mean it is safe to make public.

Notes:

- Requests blocked by a filter before `DispatcherServlet` will never run MVC interceptors.
- Excluding a URL in `addInterceptors` does **not** mean that URL is `permitAll` in Spring Security; the two configuration layers are independent.
- CORS, CSRF, session management, access control, and API protection should use the appropriate security APIs.
- If logic truly must run for all Servlet traffic, a Servlet `Filter` may be a more accurate extension point than `HandlerInterceptor`.

## 13. Extending Registries in Multi-Module Applications

In large projects, configurations can be split into separate `@Configuration` classes:

~~~java
@Configuration(proxyBeanMethods = false)
class ApiInterceptorConfiguration implements WebMvcConfigurer {
    // addInterceptors(...)
}

@Configuration(proxyBeanMethods = false)
class ViewRouteConfiguration implements WebMvcConfigurer {
    // addViewControllers(...)
}

@Configuration(proxyBeanMethods = false)
class StaticAssetConfiguration implements WebMvcConfigurer {
    // addResourceHandlers(...)
}
~~~

The classes above only illustrate structure; method bodies are omitted. They are not standalone runnable programs.

Splitting classes helps manage scope and dependencies, but avoid:

- Two view controllers claiming the same URL.
- A URL shared between `@RequestMapping` and a view controller.
- Two resource registrations with the same pattern yet different locations/caching, making behavior order-dependent.
- Duplicate interceptors performing the same work or recording metrics twice.

When an interceptor depends on a service, inject that bean via constructor into the interceptor bean, then inject the interceptor into `WebMvcConfigurer`. Creating interceptors with `new` in multiple places scatters state and bypasses dependency injection.

If ordering between multiple interceptors must be changed, declare `order` explicitly and verify with tests. Since `preHandle` runs forward and completion runs in reverse, tasks like creating/closing request context must be managed carefully.

## 14. Quick Troubleshooting Guide

| Symptom | What to Check |
|---|---|
| Interceptor does not run | Is `@Configuration` component-scanned? Does pattern match MVC URL? Is it excluded? Did a Security Filter block it first? |
| Interceptor runs on unwanted static assets | Pattern `/**` is too broad; scope to `/api/**` or exclude `/demo-assets/**` |
| preHandle returns false yet status is unexpected | Missing `setStatus`/`sendError` or appropriate response body before halting the chain |
| postHandle has no ModelAndView | `@RestController`/`@ResponseBody` writes the body directly; `ModelAndView` may be null |
| afterCompletion missing log on async requests | Check `AsyncHandlerInterceptor`, timeouts, and async dispatches |
| /welcome returns 500 or does not render | Missing Thymeleaf/`ViewResolver`, wrong view name, or wrong `templates/welcome.html` location |
| /welcome reports unusual mapping | URL collision between view controller and `@RequestMapping` |
| /old-welcome redirects incorrectly | Check target URL, context path, proxy, and `Location` |
| /demo-assets/site.css returns 404 | Wrong prefix, wrong `classpath:/demo-assets/`, file not packaged, or case mismatch |
| CSS loads but is stale | `Cache-Control`, CDN, browser cache, fingerprinting/versioning |
| Adding @EnableWebMvc breaks static files | `@EnableWebMvc` changed the auto-configuration model; remove it when only customizing |
| Unmapped API throws NoResourceFoundException | Default static mapping `/**` may accept requests when no controller matches |
| Works locally but fails in JAR | File not under `src/main/resources` or machine-specific `file:` path configuration |

When diagnosing, enable logs for Spring MVC handler mappings and inspect registered request mappings if Actuator is enabled/permitted. Do not modify or expose public Actuator endpoints just to inspect a single route.

## 15. Pre-Production Checklist

1. **Right stack:** application actually runs Spring MVC, not WebFlux-only.
2. **Keep auto-configuration:** use `WebMvcConfigurer` without `@EnableWebMvc` when only extending MVC.
3. **Clear interceptor scope:** include/exclude patterns are tested; do not replace `SecurityFilterChain`.
4. **Correct lifecycle callbacks:** understand `preHandle`, `postHandle`, `afterCompletion`, and async behavior.
5. **Simple view controllers:** no business logic, backed by a real `ViewResolver`/template.
6. **Intentional redirects:** explicit targets, never open redirects from user input.
7. **Narrow resource handlers:** dedicated URL prefixes and safe resource locations, never exposing secrets.
8. **Appropriate caching:** TTL aligned with asset immutability; fingerprinting when using long cache lifetimes.
9. **No mapping conflicts:** verify `@RequestMapping`, view controllers, static resource mappings, and context paths.
10. **Two-layer testing:** `MockMvc` for registration; HTTP integration tests to verify server/proxy/caching as needed.

## 16. Official References

- [Spring Boot 3.5 – Servlet Web Applications, MVC auto-configuration, and static content](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Framework 6.2 – Interceptors](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html)
- [Spring Framework – View Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/view-controller.html)
- [Spring Framework 6.2 – Static Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html)
- [Spring Framework – HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html)

The complete code snippets in Sections 7 and 8 assume a Spring Boot 3.5.x project with Java 17+, matching the stated dependencies and package structure. If migrating to Spring Boot 4.x or Spring Framework 7.x, verify package/API changes, migration guides, and real tests before copying configurations.

Understanding these three extension points keeps controllers focused on business logic, adds cross-cutting behavior in the right scope, and serves HTML/static assets with existing MVC infrastructure while preserving Spring Boot's helpful defaults.
