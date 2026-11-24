# Registering Interceptors, Path Scope, and AsyncHandlerInterceptor in Spring MVC

## 1. Purpose and Use Cases

In Spring MVC, an application may want to record controller processing time, attach trace/correlation metadata, inject context before a handler executes, or observe request completion. `HandlerInterceptor` is an extension point attached to a Spring MVC `HandlerExecutionChain`. It differs from a `Servlet Filter` because an interceptor is selected after Spring locates the handler, whereas a filter lives in the Servlet filter chain outside `DispatcherServlet`.

Suppose the application has four routes:

~~~text
GET /api/orders/7         => interceptor applied
GET /api/reports/async    => interceptor applied and async processing
GET /api/public/ping      => intentionally excluded
GET /health               => outside /api/** scope
~~~

This lesson explains registration with `WebMvcConfigurer`, `InterceptorRegistry`, `addPathPatterns`/`excludePathPatterns`, callback ordering and lifecycle, differences when a controller returns `Callable`/`DeferredResult`, `ThreadLocal` cleanup on thread switches, timeout/network error limitations, and accurate testing with MockMvc.

**Scope:** Spring MVC Servlet stack, Java 17+, Spring Boot 3.x, and Spring Framework 6.x with the `jakarta.servlet` namespace. Spring WebFlux has a different request model. `@Async` on a service method does not automatically mean Servlet async request processing.

## 2. Interceptor Position in the HTTP Pipeline

`HandlerInterceptor` belongs to Spring MVC's `HandlerExecutionChain`: Servlet Filters have already run at the container layer; `DispatcherServlet` and `HandlerMapping` identify the handler before the interceptor is invoked. Therefore, an interceptor can know the selected `HandlerMethod`, yet it does not automatically cover requests rejected early by Security/Servlet Filters.

~~~text
Servlet Filter chain
    → DispatcherServlet / HandlerMapping
    → A.preHandle → B.preHandle
    → MVC handler + return value handling
    → B.postHandle → A.postHandle   (successful synchronous path)
    → view rendering if applicable
    → B.afterCompletion → A.afterCompletion
~~~

The three callbacks play distinct roles: `preHandle` returns `true` to proceed or `false` to stop (and must complete the response and clean up its own work); `postHandle` receives `ModelAndView`, which may be null, and in REST it may be too late to alter body/headers; `afterCompletion` runs only for interceptors that completed `preHandle=true`, and its `ex` parameter may be null even if an error was handled by an MVC resolver. `handler` is not necessarily a `HandlerMethod`, e.g., static resource handlers.

With A then B, the pre-handler direction is A→B and the post direction is B→A. If B returns `false`, A can still receive `afterCompletion`, while B does not; the handler and `postHandle` do not run. If the handler throws an exception, `postHandle` normally does not run, while cleanup applies to active interceptors. That is the foundation for **registration/path matching** in Sections 3–4 and **ASYNC redispatch** in Section 5; the main examples for individual callback branches, ordering, and errors are in the dedicated `preHandle`/`postHandle`/`afterCompletion` article.

## 3. Registering via WebMvcConfigurer in Spring Boot

Typical approach:

~~~java
@Configuration(proxyBeanMethods = false)
public class MvcConfiguration implements WebMvcConfigurer {

    private final AuditInterceptor audit;

    public MvcConfiguration(AuditInterceptor audit) {
        this.audit = audit;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(audit)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**")
                .order(0);
    }
}
~~~

This is a **fragment**, requiring an already-defined `AuditInterceptor` and corresponding imports. Details:
- `addInterceptor(audit)` registers the interceptor instance in the MVC chain.
- `addPathPatterns("/api/**")` selects routes within the API scope.
- `excludePathPatterns("/api/public/**")` omits the interceptor for the public URL subset.
- `order(0)` sets relative order against other registrations.
- Omitting include patterns generally means applying to paths handled by the corresponding MVC handler mapping, not every request across the entire server.

Place the config class in a package scanned by `@SpringBootApplication`. Make the interceptor a Spring bean when it needs dependency injection rather than instantiating `new` instances across multiple configurations.

**Do not add `@EnableWebMvc` just to register an interceptor.** In Spring Boot, that annotation generally puts you in full control of MVC configuration and can disable many Boot MVC auto-configurations. `WebMvcConfigurer` lets you add configuration while keeping Boot's default behavior.

### 3.1. Registration Ordering

~~~java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(first)
            .addPathPatterns("/api/**")
            .order(0);

    registry.addInterceptor(second)
            .addPathPatterns("/api/admin/**")
            .order(10);
}
~~~

This fragment requires beans `first` and `second`. For `/api/admin/report`, both can match; `preHandle` runs from `first` to `second`, and completion callbacks run in reverse. Smaller order values have earlier priority in the registry. Servlet filter ordering is unaffected by `order` here.

### 3.2. MappedInterceptor Bean

Beyond Java config, Spring MVC supports `MappedInterceptor`: a bean holding include/exclude patterns and a delegate interceptor. Example:

~~~java
@Bean
MappedInterceptor monitoringMapping(AuditInterceptor delegate) {
    return new MappedInterceptor(
            new String[]{"/api/**"},
            new String[]{"/api/public/**"},
            delegate);
}
~~~

This is a fragment requiring `@Bean` and `MappedInterceptor` imports; do not copy it into the Section 8 demo at the same time. Spring documentation notes the distinction: Java `addInterceptors` generally registers into `HandlerMapping` beans managed by MVC Java configuration, whereas a `MappedInterceptor` bean can also be detected by other `HandlerMapping` implementations, including third-party framework integrations.

**Do not register the same interceptor twice** via both a `MappedInterceptor` bean and `registry.addInterceptor` for the same scope: callbacks could repeat and metrics could double-count. Choose one strategy, then integration-test against the application's actual mappings.

## 4. Path Scope and Pattern Matching

With this configuration:

~~~java
registry.addInterceptor(audit)
        .addPathPatterns("/api/**")
        .excludePathPatterns("/api/public/**");
~~~

Expectations in a standard MVC application:

| Path | Applied? | Explanation |
| --- | --- | --- |
| `/api/orders/7` | Yes | Matches `/api/**` |
| `/api/reports/async` | Yes | Matches include |
| `/api/public/ping` | No | Excluded |
| `/health` | No | Outside include |
| `/api/deep/nested/path` | Yes | Multi-segment wildcard |
| `/app/api/orders/7` with context path `/app` | Typically still evaluated on app-relative path `/api/orders/7` | Do not confuse context path with route |

`/api/*` normally matches a single path segment, whereas `/api/**` matches multiple segments according to the configured path matcher. Pattern matching occurs within `HandlerMapping`'s context and should not be replaced with `request.getRequestURI().startsWith(...)` due to context paths, URL encoding, and servlet mappings.

### 4.1. PathPatternParser and AntPathMatcher

Spring MVC 6 commonly uses `PathPatternParser`, differing from older configurations using `AntPathMatcher`. When upgrading:
- Do not assume `/api/items` and `/api/items/` always match identically; trailing slash behavior changed in newer versions.
- Certain wildcard patterns, encoding, matrix parameters, and servlet mappings have different semantics between the two matching engines.
- `**` in parsed patterns has specific positional constraints; do not port complex Ant patterns to `PathPattern` without testing.
- When running under a context path or reverse proxy, verify the exact route seen by `HandlerMapping`.

Test include, exclude, and slash variants with MockMvc/integration tests appropriate for your version. Do not build security logic on raw string path comparisons.

### 4.2. Path Exclusions Are Not Authorization

`excludePathPatterns("/api/public/**")` only excludes **the interceptor in question**; it does not create a “permit all” or “deny all” policy. In particular, Spring officially warns that interceptors are not the ideal place to implement the primary security layer because controller path matching and protection rules can diverge.

For authentication/authorization, use Spring Security filter chains/authorization rules. For request metrics or intercepting controller metadata, an interceptor is appropriate. A request rejected by a security filter may never reach the interceptor.

### 4.3. Requests That Bypass the Expected Handler Mapping

An interceptor may not see:
- Requests blocked early by a Filter/Spring Security.
- Static resources handled by the Servlet/container or another `HandlerMapping`.
- CORS preflight requests handled by MVC on a special branch.
- `ERROR`/`FORWARD` dispatches depending on configuration.
- Actuator endpoints on a separate management port/context.

If you need to observe every HTTP request regardless of whether a controller is involved, consider a Filter or integrated observability at the appropriate layer. Do not conclude from an interceptor not running that a request never reached the server.

## 5. How Does AsyncHandlerInterceptor Differ from HandlerInterceptor?

`AsyncHandlerInterceptor` extends `HandlerInterceptor` and adds:

~~~java
void afterConcurrentHandlingStarted(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception;
~~~

When a controller returns `Callable<T>`, `WebAsyncTask<T>`, or `DeferredResult<T>` and MVC initiates Servlet async processing, the initial Servlet thread is released while the HTTP response may not yet be complete. Consequently, the normal lifecycle is split across multiple dispatches.

### 5.1. Synchronous Request

~~~text
REQUEST dispatch
  interceptor.preHandle()
  controller runs and returns result
  MVC processes return value / view
  interceptor.postHandle()
  interceptor.afterCompletion()
  request handling completes
~~~

This is the standard success path when `preHandle` returns true and no error occurs.

### 5.2. Successful Asynchronous Request

~~~text
INITIAL REQUEST DISPATCH — servlet thread:
  preHandle()                             DispatcherType.REQUEST
  controller returns Callable / DeferredResult
  Spring MVC starts async handling
  afterConcurrentHandlingStarted()
  servlet request thread is released

ASYNC COMPUTATION:
  Callable computes result on executor thread,
  or DeferredResult completed by another producer

ASYNC DISPATCH — servlet thread (may be a different thread):
  preHandle()                             DispatcherType.ASYNC
  Spring MVC resumes using concurrent result
  postHandle()                            normal successful completion
  afterCompletion()                       final MVC processing
~~~

**Key points:**
1. On the initial pass that starts async, `postHandle` and `afterCompletion` are **not called immediately**; `afterConcurrentHandlingStarted` is called instead.
2. When the result is ready, the container dispatches again to `DispatcherServlet`; `preHandle` usually runs **a second time** in the `ASYNC` dispatch.
3. The controller method is **not necessarily invoked again** during the redispatch pass; Spring processes the result produced by the worker/event.
4. Do not assume “one HTTP request calls `preHandle` once.” If you count requests, create traces, or check TTLs per `preHandle` invocation, async redispatches can skew statistics.
5. The diagram does not require three strictly distinct physical threads; thread pools may reuse threads.

Use `request.getDispatcherType()` to distinguish `REQUEST` and `ASYNC` when needed. Servlet also has other dispatcher types (`FORWARD`, `INCLUDE`, `ERROR`) depending on container/filter mappings.

### 5.3. Why Clean Up in afterConcurrentHandlingStarted?

An interceptor may set thread-bound data such as MDC/logging context/`ThreadLocal`. When async starts, the initial servlet thread is about to return to the pool, so **data attached to that thread by the interceptor must be cleaned up**. Cleaning up only in `afterCompletion` misses the initial request pass; the thread risks retaining client A's context and leaking it to request B.

Conceptual example:

~~~java
@Override
public void afterConcurrentHandlingStarted(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {
    MDC.remove("traceId");
}
~~~

The snippet above is a fragment, suitable only if this interceptor **owns and set** the `traceId` key; requires importing `org.slf4j.MDC`. Do not arbitrarily clear context managed by another tracing library. After cleaning the initial thread, **that does not mean context automatically appears in the `Callable` worker**: metadata must be propagated explicitly or via Micrometer Context Propagation/`TaskDecorator` with proper capture/restore.

If state is still needed across dispatches, small values can be stored in a request attribute. Do not delete the attribute in `afterConcurrentHandlingStarted` and expect the redispatch to still read it.

### 5.4. Timeouts and Network Errors

For async requests, the Servlet container can time out or lose the connection. Some error paths **have no successful redispatch**, so `postHandle`/`afterCompletion` are not guaranteed to execute like on the success branch.

To capture those events, use the proper extensions:
- `DeferredResult.onTimeout(Runnable)`, `DeferredResult.onCompletion(Runnable)`.
- `WebAsyncTask` callbacks and timeout for `Callable`.
- `WebAsyncManager.registerCallableInterceptor(...)` or `registerDeferredResultInterceptor(...)` for deeper observation.
- Filter/container async lifecycle if responsibility belongs at the Servlet layer, with accurate dispatch mappings.

Do not place critical resource cleanup **solely** in `afterCompletion` and assume every connection/lock is always released. For late-completing requests, completion callbacks are typically only for cleanup/observation, and writing a new HTTP result may no longer be allowed.

### 5.5. Async MVC Does Not Mean Reactive Non-Blocking

`Callable` runs on an executor; JDBC/blocking HTTP calls still block the worker thread. `DeferredResult` lets an external event complete the response without holding a Servlet request thread while waiting. Spring WebFlux is a different framework and does not reuse Servlet MVC's `AsyncHandlerInterceptor` hooks as-is.

Production setups should configure a bounded `AsyncTaskExecutor`, default timeouts, queue policies, and error handling. Do not use an unbounded executor in an application with many slow blocking requests simply to increase concurrency.

## 6. Common Design Pitfalls to Avoid Up Front

| Symptom | Cause | Solution |
| --- | --- | --- |
| Headers/body unchanged when written in `postHandle` | Response body already written by converter | Use `ResponseBodyAdvice` if body changes are truly needed |
| Request metrics double-counted on async APIs | `preHandle` runs on REQUEST then ASYNC dispatch | Count one logical request; inspect dispatcher type |
| MDC leaks to another user | Initial thread not cleaned on async start | Use `afterConcurrentHandlingStarted` with clear context ownership |
| Async thread lacks trace context | No propagation | Explicit capture/restore or Micrometer/`TaskDecorator` |
| Timeouts skip cleanup | Relying solely on `afterCompletion` | Async timeout/completion hooks |
| Interceptor has no effect on static resources | Resources go through another mapping | Put logic in a Filter if whole-Servlet scope is needed |
| Security bypassed via path exclusions | Using interceptor as an ACL | Spring Security filter chain |
| Sync callbacks unexpectedly repeated | Same bean registered twice | Pick either registry or `MappedInterceptor` |
| Boot MVC loses converters | Arbitrarily adding `@EnableWebMvc` | Use `WebMvcConfigurer` |
| Casting `handler` throws `ClassCastException` | Handler is not a `HandlerMethod` | Use `instanceof` |
| Handler skipped yet response is empty | `preHandle` returned false without setting response | Send an explicit status/body |

## 7. Illustrative Java 17 + Spring Boot Application

The app has four routes to test scope and async lifecycle:
- `GET /api/items/{id}`: sync JSON, interceptor active.
- `GET /api/async/report`: `Callable<Report>`, interceptor runs across two normal dispatches.
- `GET /api/public/ping`: excluded, no demo interceptor.
- `GET /health`: outside include, no demo interceptor.

Uses Spring Boot 3.3.5, Spring MVC, and MockMvc, **with no database needed**. Headers `X-Mvc-Interceptor` and `X-Mvc-Pre-Visits` are strictly for technical observation; never use them as tokens or authorization state.

### 7.1. Directory Structure

~~~text
interceptor-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/interceptordemo/
    │   ├── InterceptorDemoApplication.java
    │   └── web/
    │       ├── RequestTraceInterceptor.java
    │       ├── MvcConfiguration.java
    │       └── DemoController.java
    └── test/java/com/example/interceptordemo/web/
        └── DemoControllerTest.java
~~~

### 7.2. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'interceptor-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use a Gradle wrapper compatible with Java 17/Spring Boot 3.3. On Linux/macOS run `./gradlew bootRun`, `./gradlew test`; on Windows run `.\gradlew.bat bootRun`, `.\gradlew.bat test`. Because the code depends on Spring, do not run `javac` directly without the classpath.

### 7.3. Application Entry Point

`src/main/java/com/example/interceptordemo/InterceptorDemoApplication.java`:

~~~java
package com.example.interceptordemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InterceptorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InterceptorDemoApplication.class, args);
    }
}
~~~

### 7.4. RequestTraceInterceptor

`src/main/java/com/example/interceptordemo/web/RequestTraceInterceptor.java`:

~~~java
package com.example.interceptordemo.web;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

@Component
public class RequestTraceInterceptor implements AsyncHandlerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(RequestTraceInterceptor.class);
    private static final String STATE_KEY =
            RequestTraceInterceptor.class.getName() + ".state";

    private static final class State {
        private final long startNanos = System.nanoTime();
        private int preVisits;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        State state = (State) request.getAttribute(STATE_KEY);
        if (state == null) {
            state = new State();
            request.setAttribute(STATE_KEY, state);
        }
        state.preVisits++;

        response.setHeader("X-Mvc-Interceptor", "active");
        response.setHeader(
                "X-Mvc-Pre-Visits", Integer.toString(state.preVisits));
        log.debug("pre path={} dispatch={} visits={}",
                request.getRequestURI(), request.getDispatcherType(),
                state.preVisits);
        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) {
        log.debug("post path={} dispatch={}",
                request.getRequestURI(), request.getDispatcherType());
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        log.debug("async-start path={} dispatch={}",
                request.getRequestURI(), request.getDispatcherType());
        // If you set MDC/ThreadLocal in preHandle,
        // clean up the context owned by the initial Servlet thread here.
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        State state = (State) request.getAttribute(STATE_KEY);
        if (state != null) {
            long elapsedMs =
                    (System.nanoTime() - state.startNanos) / 1_000_000L;
            log.debug("complete status={} dispatch={} elapsedMs={}",
                    response.getStatus(), request.getDispatcherType(),
                    elapsedMs);
        }
    }
}
~~~

Analysis:
- `State` is attached to a **request attribute**, not stored in a singleton bean field shared across all users.
- `preVisits` increments on each `preHandle` pass; sync is normally 1, and a successful async after redispatch is normally 2. Do not use that counter as a total HTTP request metric.
- `postHandle` and `afterCompletion` only log, without attempting to modify JSON after the converter may have written it.
- `afterConcurrentHandlingStarted` logs the async start step and is the appropriate place to clean up thread-bound state **created by this interceptor**.
- Do not log cookies, `Authorization` headers, raw request bodies, or session IDs. For production metrics, prefer MVC route templates over raw URIs containing IDs.

### 7.5. MvcConfiguration

`src/main/java/com/example/interceptordemo/web/MvcConfiguration.java`:

~~~java
package com.example.interceptordemo.web;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcConfiguration implements WebMvcConfigurer {

    private final RequestTraceInterceptor trace;

    public MvcConfiguration(RequestTraceInterceptor trace) {
        this.trace = trace;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(trace)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**")
                .order(0);
    }
}
~~~

This config selects both synchronous and async routes under `/api/**`, excluding the public branch. Do not register the interceptor via `MappedInterceptor` a second time.

### 7.6. Controller

`src/main/java/com/example/interceptordemo/web/DemoController.java`:

~~~java
package com.example.interceptordemo.web;

import java.util.Map;
import java.util.concurrent.Callable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    public record Item(long id, String status) {}
    public record Report(String status) {}

    @GetMapping("/api/items/{id}")
    public Item item(@PathVariable("id") long id) {
        return new Item(id, "ok");
    }

    @GetMapping("/api/async/report")
    public Callable<Report> asyncReport() {
        return () -> new Report("ready");
    }

    @GetMapping("/api/public/ping")
    public String publicPing() {
        return "pong";
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "up");
    }
}
~~~

`asyncReport` directly returns `Callable<Report>` to Spring MVC, triggering Servlet async processing, after which the `Report` result is serialized on the completion pass. Do not confuse this with calling an `@Async` service method and blocking for the result.

### 7.7. Testing with MockMvc

`src/test/java/com/example/interceptordemo/web/DemoControllerTest.java`:

~~~java
package com.example.interceptordemo.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void includedApiRouteRunsInterceptor() throws Exception {
        mvc.perform(get("/api/items/7"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Mvc-Interceptor", "active"))
                .andExpect(header().string("X-Mvc-Pre-Visits", "1"))
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void excludedPublicRouteHasNoInterceptorHeader() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist("X-Mvc-Interceptor"))
                .andExpect(content().string("pong"));
    }

    @Test
    void routeOutsideIncludeHasNoInterceptorHeader() throws Exception {
        mvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist("X-Mvc-Interceptor"))
                .andExpect(jsonPath("$.status").value("up"));
    }

    @Test
    void asyncDispatchRunsASecondPreHandle() throws Exception {
        MvcResult first = mvc.perform(get("/api/async/report"))
                .andExpect(request().asyncStarted())
                .andExpect(header().string("X-Mvc-Interceptor", "active"))
                .andReturn();

        mvc.perform(asyncDispatch(first))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ready"))
                .andExpect(header().string("X-Mvc-Interceptor", "active"))
                .andExpect(header().string("X-Mvc-Pre-Visits", "2"));
    }
}
~~~

What the tests verify:
- Header is present on the included route, absent on the excluded and outside routes.
- `request().asyncStarted()` verifies MVC started async.
- `asyncDispatch(first)` continues **the same logical HTTP request**, not a new GET request.
- Two `preHandle` passes reflect the initial REQUEST and ASYNC completion in the sample path. With errors/timeouts or custom dispatches, do not treat the count of two as an invariant rule.

Run `./gradlew test`. MockMvc does not replace integration tests against a Servlet container/load balancer when studying thread pools, timeouts, and network disconnects.

### 7.8. Observing with curl

~~~bash
curl -i 'http://localhost:8080/api/items/7'
curl -i 'http://localhost:8080/api/async/report'
curl -i 'http://localhost:8080/api/public/ping'
curl -i 'http://localhost:8080/health'
~~~

Expected output:
- `/api/items/7`: HTTP 200, `{"id":7,"status":"ok"}`, with `X-Mvc-Interceptor: active` and `X-Mvc-Pre-Visits: 1`.
- `/api/async/report`: HTTP 200, `{"status":"ready"}`, typically final header visits of 2 after a successful async dispatch.
- `/api/public/ping`: HTTP 200, text body `pong`, no interceptor headers.
- `/health`: HTTP 200, JSON `{"status":"up"}`, no interceptor headers.

Thread names and `elapsedMs` in debug logs are not fixed. Demo endpoints do not enforce security, and headers exist solely to observe MVC mechanics.

## 8. Configuring Executor and Timeout for Production

Spring MVC allows extending `WebMvcConfigurer#configureAsyncSupport`. Example **fragment** (not included in Section 7's app source):

~~~java
@Override
public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
    configurer.setTaskExecutor(mvcAsyncExecutor);
    configurer.setDefaultTimeout(5_000L);
}
~~~

`mvcAsyncExecutor` is an `AsyncTaskExecutor` injected from another bean; requires importing `AsyncSupportConfigurer`. Illustrative thread pool bean:

~~~java
@Bean
public ThreadPoolTaskExecutor mvcAsyncExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("mvc-async-");
    executor.initialize();
    return executor;
}
~~~

This is also a fragment, requiring `@Bean` and `ThreadPoolTaskExecutor` imports. When integrating into a real app, ensure the bean is managed once, has proper shutdown/rejection policies, the executor is properly injected, and numbers are tuned for load and I/O latency. Spring MVC's default executor for some async tasks is unsuitable for production with heavy blocking work.

If using `DeferredResult`, also identify the producer/event source completing the response and clean up state on timeout/cancellation.

### 8.1. DeferredResult and Callbacks

~~~java
@GetMapping("/api/deferred")
public DeferredResult<String> deferred() {
    DeferredResult<String> result = new DeferredResult<>(5_000L);
    result.onTimeout(() -> result.setErrorResult(
            new IllegalStateException("Deferred response timed out")));
    result.onCompletion(() -> {
        // Clean up resources tied to the deferred operation.
    });
    return result;
}
~~~

Non-standalone fragment: requires importing `DeferredResult` and having an event/worker actively call `setResult` before timeout when ready. If nothing completes it, it times out. `onCompletion` may be called after the response has already finished, so do not expect to write additional body content there.

## 9. ThreadLocal, MDC, and Context Propagation

A `ThreadLocal` appears to work for sync handlers because the entire request runs on one thread. For async, consider at least three phases: the initial Servlet thread, the worker thread, and the redispatch Servlet thread. They are **not guaranteed to be the same thread**.

If an interceptor sets `MDC.put("traceId", ...)` in `preHandle`:
1. Clean it on the initial Servlet thread when async starts (typically `afterConcurrentHandlingStarted`).
2. Use explicit context propagation if the `Callable` needs the trace ID.
3. On redispatch, rebuild MDC from the request attribute/tracing context if needed.
4. Remove the exact key at the end of the respective lifecycle; do not erase context owned by other components.

Micrometer Context Propagation, `TaskDecorator`, or Spring Security context propagation mechanisms can help; API choice depends on version and tracing stack. Do not assume Java automatically copies `ThreadLocal` across thread pools.

A small request attribute can carry request IDs/timestamps across async dispatches, but it does not replace cleaning up thread-bound state and should never store credentials or large mutable objects. If multiple async callbacks touch the same object, ensure proper synchronization or immutable state.

## 10. Do Not Use Interceptors as the Primary Security Layer

Spring Framework explicitly notes that interceptors are not ideal for implementing security because MVC mapping paths can differ from protection layer request matching. A request can be blocked by a filter before the interceptor; similarly, static resources or alternate `HandlerMapping` beans can bypass an MVC-only interceptor.

Use:
- **Spring Security** for authentication, authorization, and CSRF policy.
- **Servlet Filters** for handling outside MVC handlers and Servlet-level request/response wrapping.
- **HandlerInterceptor** for metadata/observation or hooks tied to specific MVC handlers.
- **ResponseBodyAdvice** when transforming response bodies during message conversion instead of modifying JSON late in `postHandle`.
- **ControllerAdvice/HandlerExceptionResolver** for HTTP error contracts.

If inspecting annotations on a handler, use `handler instanceof HandlerMethod`, never a blind cast:

~~~java
if (handler instanceof HandlerMethod method) {
    String name = method.getMethod().getName();
    // Use method name only as intentional internal metadata.
}
~~~

This snippet is a fragment requiring `org.springframework.web.method.HandlerMethod`.

## 11. Additional Testing Scenarios

For larger applications, add regression tests covering:
- Two ordered interceptors; verify forward order of `preHandle` and reverse order of `postHandle`/`afterCompletion`.
- Interceptor B returning false; handler does not run, A is cleaned up, B cleans up its own resources.
- Handler throwing an exception handled by a resolver; do not assume `afterCompletion`'s `ex` holds the original exception.
- Paths with context path, servlet mapping, trailing slashes, and with/without encoded characters.
- `OPTIONS`/CORS preflight requests, static resources, and separately mapped Actuator endpoints.
- Async error returns and timeouts: completion/interceptor callbacks run per actual policy.
- `Callable` worker uses logging/security context properly; Servlet thread is cleaned before reuse.
- Production bounded executor, circuit breaker/downstream timeout, and behavior when the queue is full.

Do not check only HTTP 200. An interceptor might “run” on one branch yet fail to execute expected cleanup. Use test doubles or a per-request recorder when full callback ordering must be asserted.

## 12. Common Errors and Troubleshooting

| Symptom | Possible Cause | Solution |
| --- | --- | --- |
| Interceptor never runs | Config not component-scanned or path mismatch | Check bean, mappings, and include tests |
| Exclude has no effect | Wrong pattern, duplicate registration, or different matcher | Verify paths and registrations |
| Each async request counted twice | Initial REQUEST + ASYNC redispatch | Distinguish dispatcher type; use request-scoped marker |
| `postHandle` does not run when returning `Callable` | Async started | Use `afterConcurrentHandlingStarted` |
| `afterCompletion` does not run on timeout | No successful final dispatch | Use async-specific callbacks |
| Response header set in `postHandle` is lost | Response already committed | Set earlier when appropriate or in the right response hook |
| User A's MDC appears in User B | `ThreadLocal` not cleaned | Clean thread context on async start/completion |
| Async worker lacks locale/security context | Context not propagated | Explicit propagation/`TaskDecorator` |
| `Callable` result never completes | Executor/timeouts/missing async support | Check queue, thread pool, timeout, Servlet async config |
| `@EnableWebMvc` breaks MVC converters | Boot auto-configuration disabled | Use `WebMvcConfigurer` when only adding interceptors |
| Filter sees request, interceptor does not | Rejected early or different mapping | Pick the right hook layer |
| Authorization can be bypassed | Rules placed in interceptor lack full coverage | Spring Security |
| Runtime error casting handler | Handler is not a `HandlerMethod` | Use `instanceof` |

### Debugging Sequence

1. Confirm the URL and HTTP method match a handler in Spring MVC.
2. Check the config class/interceptor bean in the application context.
3. Compare include/exclude patterns against the route recognized by `HandlerMapping`.
4. Carefully log `DispatcherType` in `preHandle` to distinguish REQUEST and ASYNC.
5. For async, verify `request().asyncStarted()`, the executor, and `asyncDispatch` in tests.
6. For timeouts, use callbacks beyond `afterCompletion`.
7. Verify thread-bound cleanup/propagation does not leak.
8. If the goal is security or all HTTP traffic, move the hook to the appropriate Filter/Security layer.

## 13. Self-Check Questions

**1.** Does `WebMvcConfigurer#addInterceptors` require `@EnableWebMvc` in Spring Boot?

**Answer:** Usually no. Just implement `WebMvcConfigurer` to add interceptors while preserving Boot MVC auto-configuration.

**2.** Does `excludePathPatterns("/api/public/**")` replace Spring Security authorization rules?

**Answer:** No. It only adjusts the scope of that interceptor.

**3.** With A then B, what is the normal synchronous callback order?

**Answer:** `A.pre → B.pre → handler → B.post → A.post → B.complete → A.complete`.

**4.** Why can a request returning `Callable` call `preHandle` twice?

**Answer:** MVC handles the initial REQUEST pass, starts async, and then performs an ASYNC redispatch once the result is ready.

**5.** On the initial pass that starts async, which callback runs instead of `postHandle`/`afterCompletion`?

**Answer:** `AsyncHandlerInterceptor.afterConcurrentHandlingStarted()`.

**6.** Do timeouts and client disconnects guarantee `postHandle`/`afterCompletion`?

**Answer:** No. Design dedicated callbacks and verify container/error paths.

**7.** Does clearing `ThreadLocal` on the Servlet thread automatically move state to the `Callable` worker?

**Answer:** No. Explicit propagation is required.

**8.** If you want to modify a REST JSON body after serialization, should you default to `postHandle`?

**Answer:** No. It may be too late; `ResponseBodyAdvice` or the message-converter layer is more appropriate.

## 14. Official References

- [Spring Framework — MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): `WebMvcConfigurer`, registration, patterns, and security warnings.
- [Spring Framework 6.1 — AsyncHandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html): callbacks on async start, ASYNC dispatch, and timeout caveats.
- [Spring Framework 6.1 — HandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html): `preHandle`, `postHandle`, and `afterCompletion`.
- [Spring Framework — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, executors, timeouts, context propagation.
- [Spring Framework — MVC Java Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html): `WebMvcConfigurer` and `@EnableWebMvc`.
- [Spring Framework 6.1 — MappedInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/handler/MappedInterceptor.html): bean usage with include/exclude.
- [Jakarta Servlet 6 — DispatcherType](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/dispatchertype): REQUEST, ASYNC, and other dispatch types.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): Filter chain and security boundary.

**Key takeaway:** interceptors operate around Spring MVC handlers, can be scoped with include/exclude patterns, and do not replace Filters or Security. When a handler starts async processing, `afterConcurrentHandlingStarted` is invoked instead of the first pass's completion callbacks; `preHandle` may run again on the ASYNC redispatch, and timeouts/thread context cleanup need dedicated mechanisms. Test both path scoping and the async lifecycle before deploying an interceptor to production.
