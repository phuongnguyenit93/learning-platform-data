# Ordered, @Order, and Verifying Actual Execution Order of Filters and Interceptors in Spring Boot

## Learning Objectives

When a Spring Boot application has multiple Filters, HandlerInterceptors, WebFilters, or SecurityFilterChains, **execution order** directly affects logging, correlation IDs, CORS, authentication, authorization, request wrapping, exception handling, and response payloads. Simply adding @Order and assuming every component will execute in numeric order on a single list is not enough: Spring MVC, the Servlet container, Spring Security, and Spring WebFlux have **different processing chains**.

This lesson helps you:

- Understand the meaning of **Ordered**, **@Order**, **PriorityOrdered**, **HIGHEST_PRECEDENCE**, and **LOWEST_PRECEDENCE**.
- Distinguish bean/list injection order from Servlet filter registration order, MVC interceptor registration order, and Spring Security filter chain order.
- Configure Servlet Filters using @Order on the class, Ordered, or FilterRegistrationBean.setOrder.
- Use InterceptorRegistration.order(int) to order HandlerInterceptors.
- Explain why requests enter A → B while post-handler processing normally runs B → A.
- Distinguish @Order on a SecurityFilterChain from filter ordering **inside** Spring Security.
- Recognize how @Order/Ordered applies to Spring WebFlux's WebFilter.
- Verify **actual runtime order** via startup logs, request-scoped traces, and integration tests against an embedded Servlet container.
- Avoid double-registration, wrong dispatcher types, overly early processing, and incorrect assumptions about async/error dispatches.

The primary runnable example uses **Java 17+ and Spring Boot 3.5.x on Servlet/Spring MVC**. Sections on Spring WebFlux and Spring Security explain their mechanisms separately to avoid mixing concepts.

## 1. First: What Does Numeric Order Mean?

Spring Framework defines **org.springframework.core.Ordered**:

~~~java
public interface Ordered {
    int getOrder();
}
~~~

An implementation simply returns an integer:

~~~java
public final class HighPriorityTask implements Ordered {

    @Override
    public int getOrder() {
        return 10;
    }
}
~~~

The **org.springframework.core.annotation.Order** annotation declares a fixed order on a class, method, or other supported target:

~~~java
@Order(10)
public final class AnotherTask {
}
~~~

Rule across places using Spring's order comparator:

**Smaller values generally take higher precedence and run first.**

| Value | Relative Priority |
|---|---|
| Ordered.HIGHEST_PRECEDENCE | Integer.MIN_VALUE; highest priority |
| -100 | Before 0 and 10 |
| 0 | Before 10 and 100 |
| 10 | After 0, before 20 |
| 20 | After 10 |
| Ordered.LOWEST_PRECEDENCE | Integer.MAX_VALUE; lowest priority |

There is no rule that "100 has higher priority than 10 because it is bigger." Within a single system sorted in ascending order, A=10 and B=20 means **A enters before B**.

### HIGHEST_PRECEDENCE Should Not Be Used Indiscriminately

Placing a request-body-reading filter at Ordered.HIGHEST_PRECEDENCE can cause it to run before character encoding configuration or other foundational Boot filters. Boot documentation advises against doing so. If a filter wraps the request, there are also Boot-version-specific order constraints around request wrappers to verify.

Do not use Integer.MIN_VALUE just to "guarantee my filter goes first." Pick a clear order value, inspect the other filters in the application, and avoid breaking built-in framework mechanisms.

## 2. How @Order, Ordered, and PriorityOrdered Differ

### @Order: Static Metadata

~~~java
@Component
@Order(25)
public class SomeComponent {
    // ...
}
~~~

Spring can read this annotation when it **needs to sort a collection of components**. However, an annotation does not mean every framework or Servlet container automatically inspects that metadata.

### Ordered: Instance-Determined Order

~~~java
@Component
public class DynamicOrderComponent implements Ordered {

    @Override
    public int getOrder() {
        return 25;
    }
}
~~~

Ordered is appropriate when the order is decided by an instance's constructor/configuration or when a framework has a contract that interacts directly with Ordered. In several Spring comparators, Ordered on an instance is evaluated ahead of class-level annotation metadata.

### PriorityOrdered

**PriorityOrdered** extends Ordered. In sorting contracts that support it, PriorityOrdered objects are processed as a higher-priority group **ahead of objects that only implement Ordered**, with getOrder() values compared within each respective group.

Simply implementing PriorityOrdered on an arbitrary Filter does not mean the Servlet container automatically honors it: what matters is whether **the component registering and sorting it** honors that contract.

### When Two Components Share the Same Order

If two interceptors or filters both use order=10, never write business logic relying on class A always running before B based on component scanning, filenames, alphabetical order, bean creation order, or startup order. Results can be affected by registration/collection/traversal mechanics and change across version upgrades.

If A-before-B matters, **use distinct order values, document it, and write an integration test**. Using @DependsOn to force initialization order is not an equivalent solution for the runtime filter chain.

## 3. @Order Does Not Control Every Kind of Order

Several similarly named concepts exist:

| Kind of Order | Who Decides | Appropriate Configuration |
|---|---|---|
| Bean ordering in List<T> injection | Spring bean factory / dependency ordering | @Order, Ordered, sometimes @Priority |
| Singleton bean initialization | Dependency graph, @DependsOn, and lifecycle | Do not rely on @Order |
| Boot-registered Servlet Filter | Boot/container Servlet filter registration | @Order on **Filter class**, Ordered, FilterRegistrationBean.setOrder |
| Spring MVC HandlerInterceptor | InterceptorRegistry/HandlerMapping | addInterceptor(...).order(int) |
| Multiple Spring Security SecurityFilterChains | Chain selection order + RequestMatcher | @Order on SecurityFilterChain bean |
| Security Filters inside one chain | HttpSecurity/FilterChainProxy | addFilterBefore, addFilterAfter, addFilterAt, and built-in order |
| WebFlux WebFilter | WebFlux WebFilter chain | @Order on WebFilter / Ordered |
| @ControllerAdvice precedence | Spring advice resolver | @Order/Ordered per contract |
| ResponseBodyAdvice, exception resolvers, etc. | Each specific extension point | Consult each component's contract |

**An order number only has meaning within its own sorted chain.** For example, Servlet filter order=10 and MVC interceptor order=5 **does not** mean the interceptor runs before the filter. Servlet filters sit outside DispatcherServlet; HandlerInterceptors sit inside Spring MVC.

## 4. Servlet Filter: Order Is Determined by Container Registration

Servlet Filters belong to **jakarta.servlet.Filter** (Spring Boot 3.x/4.x). Each Filter implements doFilter(request, response, chain) and can execute logic both before and after calling chain.doFilter(...).

Model with two filters A and B:

~~~text
Client
  |
  v
Filter A - before
  |
  v
Filter B - before
  |
  v
DispatcherServlet / Handler
  |
  v
Filter B - after
  |
  v
Filter A - after
  |
  v
Client
~~~

Illustrative code:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    log("A before");
    try {
        chain.doFilter(request, response);
    } finally {
        log("A after");
    }
}
~~~

This snippet is a method inside a class implementing Filter; log is an illustrative helper. try/finally ensures cleanup runs after the chain even when the chain throws an error. It **does not guarantee** the response is uncommitted or that the client has read all bytes.

### Three Common Options to Set Servlet Filter Order in Boot

**Option A: @Order on the Filter Class Itself**

~~~java
@Component
@Order(10)
public class AuditFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

This illustrative class needs jakarta.servlet.* imports and Spring annotations. When Boot auto-registers the Filter bean through supported mechanisms, `@Order` metadata **on the Filter class** can be used by Boot to determine registration order.

**Option B: implement Ordered**

~~~java
@Component
public class AnotherAuditFilter implements Filter, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

The code requires corresponding imports. Orders 10 and 20 mean AuditFilter is registered to run before AnotherAuditFilter in the same Servlet filter chain, assuming both their URL patterns and dispatcher types match.

**Option C: FilterRegistrationBean.setOrder(int)**

This is the clearest option when you want explicit control over order, URL patterns, dispatcher types, and enabled state:

~~~java
@Bean
FilterRegistrationBean<Filter> auditRegistration() {
    FilterRegistrationBean<Filter> bean =
        new FilterRegistrationBean<>(new AuditFilter());

    bean.setName("audit");
    bean.addUrlPatterns("/api/*");
    bean.setOrder(10);
    return bean;
}
~~~

This is an illustrative method. If AuditFilter already has @Component and is auto-registered by Boot, do not add a second registration that accidentally creates two registration paths; choose **one** deliberate registration mechanism. The runnable example later creates Filters directly inside FilterRegistrationBean and **omits** @Component on the Filter.

### Important Trap: @Order on a @Bean Method Returning a Filter

According to Spring Boot documentation, the following **is not a reliable way to control Servlet Filter registration order**:

~~~java
@Bean
@Order(10)
Filter auditFilter() {
    return new AuditFilter();
}
~~~

@Order on a `@Bean` method may influence some Spring injection/collection sorting, yet Spring Boot explicitly states: **do not set a Servlet Filter's order merely by placing @Order on its bean method**. If you cannot modify the Filter class to implement Ordered or put @Order on the class, use FilterRegistrationBean#setOrder(int), or @FilterRegistration with its order attribute in supported Boot versions.

This is one of the strongest reasons to **verify the actual runtime order**, not merely read annotations.

## 5. FilterRegistrationBean: Order and URL / Dispatcher Type Scope

Boot's FilterRegistrationBean allows configuring:

- setOrder(int): registration order.
- addUrlPatterns(...): Servlet paths the filter applies to.
- setDispatcherTypes(...): applies to REQUEST, ERROR, ASYNC, FORWARD, INCLUDE as designed.
- setEnabled(boolean): enable/disable the registration.
- setName(...): filter registration name.
- asyncSupported and init parameters as needed.

Example:

~~~java
registration.addUrlPatterns("/api/*");
registration.setDispatcherTypes(DispatcherType.REQUEST);
registration.setOrder(20);
~~~

**URL patterns follow Servlet rules**, not Spring MVC's `@GetMapping` patterns. If a filter maps only `/api/*`, requests to `/actuator/health` or `/login` will not go through it.

When dispatcher types are unspecified, Boot documentation notes REQUEST is the default for standard registrations. However, some frameworks or libraries create separate registrations for ERROR/ASYNC, so do not guess solely from a Filter class name.

### REQUEST, ERROR, and ASYNC

An HTTP request can traverse multiple dispatcher types:

| DispatcherType | Situation |
|---|---|
| REQUEST | Initial HTTP request |
| ERROR | Internal Servlet container dispatch to error page, e.g. /error |
| ASYNC | Resumed processing via Servlet asynchronous dispatch |
| FORWARD | Internally forwarded request |
| INCLUDE | Servlet includes another resource |

A Filter mapped for REQUEST and ERROR may be invoked in both passes if URL mapping and dispatcher type match. **Counting filter invocations is not the same as counting client HTTP requests.**

For OncePerRequestFilter, the class name does not mean every async/error redispatch is always suppressed uniformly. The hooks shouldNotFilterAsyncDispatch/shouldNotFilterErrorDispatch and the dispatcher types registration still matter greatly.

### Request-Wrapping Filters and Character Encoding

Wrapper filters or body-reading filters must pay attention to their order relative to encoding, form-content, and security filters. Boot warns against placing a request-body-reading filter at HIGHEST_PRECEDENCE; moreover, reading the entire body in a filter can prevent the controller from reading it.

When you need to read the body and still let downstream read it, use a proper HttpServletRequestWrapper/caching design with memory bounds and no secret logging. Changing order cannot fix a consumed InputStream.

## 6. HandlerInterceptor: A Separate Chain Inside Spring MVC

HandlerInterceptor belongs to **org.springframework.web.servlet.HandlerInterceptor**. It participates in the handler lifecycle after Servlet filters have allowed the request to reach DispatcherServlet.

Three common callbacks:

~~~java
boolean preHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler
);

void postHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    ModelAndView modelAndView
);

void afterCompletion(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    Exception ex
);
~~~

In real Java code, these methods declare signatures/throws matching the Spring Framework version.

- **preHandle**: before the handler. Return true to proceed; false to halt the handler chain after the interceptor handles the response per contract.
- **postHandle**: after HandlerAdapter/handler and before view rendering in normal flows.
- **afterCompletion**: cleanup callback when request handling finishes, for interceptors whose preHandle succeeded; async handling behaves differently.

### Recommended Ordering Approach

In Spring Boot MVC:

~~~java
@Configuration
class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new FirstInterceptor())
            .addPathPatterns("/api/**")
            .order(10);

        registry.addInterceptor(new SecondInterceptor())
            .addPathPatterns("/api/**")
            .order(20);
    }
}
~~~

This is an illustrative snippet requiring FirstInterceptor/SecondInterceptor definitions and imports, not a standalone runnable file. **InterceptorRegistration.order(int)** is the explicit control point; the default order is 0 if omitted.

Do not place `@Order` on a HandlerInterceptor class and expect every HandlerMapping to auto-enroll and sort that bean like a Servlet Filter. You must verify **how the interceptor is registered**. When calling registry.addInterceptor(...), set `.order(...)` on the registration.

### Callback Order

With interceptors A=10 and B=20 on a normal synchronous request:

~~~text
A.preHandle
B.preHandle
Controller
B.postHandle
A.postHandle
B.afterCompletion
A.afterCompletion
~~~

Inbound callbacks run A → B, while cleanup and post-processing run in reverse order B → A. **This describes the interceptor chain lifecycle**, and does not mean postHandle always has the ability to modify the response.

Specifically, for `@ResponseBody`/`ResponseEntity`, Spring Framework notes that the response may already be written and committed inside HandlerAdapter **before postHandle**. To modify the response body, consider ResponseBodyAdvice; to guarantee headers are set before commit, place them at the right stage rather than waiting for afterCompletion.

### preHandle Returns false

Suppose A.preHandle returns true and B.preHandle returns false:

- The controller does not run.
- Interceptors that have not yet run preHandle do not run.
- Cleanup callbacks apply per contract only to interceptors whose preHandle succeeded.
- Do not assume all postHandle/afterCompletion callbacks run as in the success branch.

Under async handling, AsyncHandlerInterceptor provides `afterConcurrentHandlingStarted`; the lifecycle may involve redispatches. Do not use a simple synchronous diagram to predict every log line of a streaming/async endpoint.

## 7. Combining Servlet Filters and MVC Interceptors: Never Compare Numbers Across Layers

Suppose two Servlet Filters have orders 10 and 20, and two MVC HandlerInterceptors also have orders 10 and 20.

~~~text
HTTP request
     |
     v
Servlet Filter A (order=10): before
     |
     v
Servlet Filter B (order=20): before
     |
     v
DispatcherServlet
     |
     v
MVC Interceptor A (order=10): preHandle
     |
     v
MVC Interceptor B (order=20): preHandle
     |
     v
Controller
     |
     v
MVC Interceptor B: postHandle
MVC Interceptor A: postHandle
MVC Interceptor B: afterCompletion
MVC Interceptor A: afterCompletion
     |
     v
Servlet Filter B: after
Servlet Filter A: after
     |
     v
HTTP client
~~~

The Servlet container runs the Filter chain before DispatcherServlet; Spring MVC runs the HandlerInterceptor chain for the selected handler inside. Consequently, MVC interceptor order=0 still **does not** sit outside Servlet Filter order=1000.

If logic must run before Spring Security and before MVC routing, check the **Servlet Filter** and **Security Filter Chain** positions. If logic depends on HandlerMethod or route annotations, HandlerInterceptor may fit, though it should not serve as the primary security layer.

## 8. Runnable Example: Verifying Order on Embedded Tomcat

This section uses **Spring Boot 3.5.x, Java 17+, spring-boot-starter-web** (MVC Servlet). Do not add Spring Security or WebFlux to this demo project so ordering stays straightforward to observe. The demo URLs are **/trace** and **/trace/result/{id}**.

Design:

1. Two Servlet Filters registered via FilterRegistrationBean with order=10 and 20; scoped strictly to `/trace`.
2. Two HandlerInterceptors registered in WebMvcConfigurer with order=10 and 20; also scoped to `/trace`.
3. A request-scoped list records events in actual execution order.
4. The controller returns a snapshot of events that occurred **before generating the response body**.
5. The outermost filter saves the complete record **after all components have unwound** into a demo store for subsequent retrieval.
6. An HTTP test starts a real server and asserts both inbound and reverse callbacks.

The store keeps data in RAM without a TTL, strictly for learning and testing. Never keep an unbounded store like this in production; enforce expiration, entry limits, and do not store sensitive data.

### 8.1. Project Setup

From Spring Initializr, select Java 17+, Spring Boot 3.5.x, and dependencies **Spring Web** and **Spring Boot Test**. In a Maven project using the Spring Boot parent/BOM:

~~~xml
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
~~~

Each public class below belongs in its own file under package com.example.ordering.

### 8.2. OrderingApplication.java

File: src/main/java/com/example/ordering/OrderingApplication.java

~~~java
package com.example.ordering;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderingApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderingApplication.class, args);
    }
}
~~~

### 8.3. TraceState.java: Per-HTTP-Request Event Storage

File: src/main/java/com/example/ordering/TraceState.java

~~~java
package com.example.ordering;

import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

public final class TraceState {

    public static final String ID =
        TraceState.class.getName() + ".id";

    private static final String EVENTS =
        TraceState.class.getName() + ".events";

    private TraceState() {
    }

    @SuppressWarnings("unchecked")
    private static List<String> events(HttpServletRequest request) {
        Object current = request.getAttribute(EVENTS);

        if (current != null) {
            return (List<String>) current;
        }

        List<String> created = new ArrayList<>();
        request.setAttribute(EVENTS, created);
        return created;
    }

    public static void add(HttpServletRequest request, String event) {
        events(request).add(event);
    }

    public static List<String> snapshot(HttpServletRequest request) {
        return List.copyOf(events(request));
    }

    public static String id(HttpServletRequest request) {
        return (String) request.getAttribute(ID);
    }
}
~~~

Request attributes hold state for **one synchronous request**. The demo does not use Servlet async or concurrent threads mutating the list; async code requires thread-safe collections and proper lifecycle management.

### 8.4. TraceStore.java: Saving Results After Filter Completion

File: src/main/java/com/example/ordering/TraceStore.java

~~~java
package com.example.ordering;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class TraceStore {

    private final ConcurrentHashMap<String, List<String>> traces =
        new ConcurrentHashMap<>();

    public void save(String id, List<String> events) {
        traces.put(id, events);
    }

    public List<String> find(String id) {
        return traces.get(id);
    }
}
~~~

ConcurrentHashMap only ensures thread-safe map operations; it does not make an unbounded in-memory trace store production-ready. In real systems, enforce retention bounds and access control over traces.

### 8.5. TraceConfiguration.java: Two Filters and Two Interceptors

File: src/main/java/com/example/ordering/TraceConfiguration.java

~~~java
package com.example.ordering;

import java.util.UUID;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class TraceConfiguration implements WebMvcConfigurer {

    @Bean
    FilterRegistrationBean<Filter> outerFilter(TraceStore store) {
        Filter filter = (request, response, chain) -> {
            HttpServletRequest http =
                (HttpServletRequest) request;

            String id = UUID.randomUUID().toString();
            http.setAttribute(TraceState.ID, id);
            TraceState.add(http, "filter-A.before");

            try {
                chain.doFilter(request, response);
            } finally {
                TraceState.add(http, "filter-A.after");
                store.save(id, TraceState.snapshot(http));
            }
        };

        return registration(filter, "trace-outer", 10);
    }

    @Bean
    FilterRegistrationBean<Filter> innerFilter() {
        Filter filter = (request, response, chain) -> {
            HttpServletRequest http =
                (HttpServletRequest) request;

            TraceState.add(http, "filter-B.before");

            try {
                chain.doFilter(request, response);
            } finally {
                TraceState.add(http, "filter-B.after");
            }
        };

        return registration(filter, "trace-inner", 20);
    }

    private static FilterRegistrationBean<Filter> registration(
            Filter filter, String name, int order) {

        FilterRegistrationBean<Filter> bean =
            new FilterRegistrationBean<>(filter);

        bean.setName(name);
        bean.addUrlPatterns("/trace");
        bean.setDispatcherTypes(DispatcherType.REQUEST);
        bean.setOrder(order);
        return bean;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new RecordingInterceptor("A"))
            .addPathPatterns("/trace")
            .order(10);

        registry.addInterceptor(new RecordingInterceptor("B"))
            .addPathPatterns("/trace")
            .order(20);
    }

    private static final class RecordingInterceptor
            implements HandlerInterceptor {

        private final String label;

        RecordingInterceptor(String label) {
            this.label = label;
        }

        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {

            TraceState.add(request,
                "interceptor-" + label + ".pre");
            return true;
        }

        @Override
        public void postHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler,
                ModelAndView modelAndView) {

            TraceState.add(request,
                "interceptor-" + label + ".post");
        }

        @Override
        public void afterCompletion(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler,
                Exception exception) {

            TraceState.add(request,
                "interceptor-" + label + ".after");
        }
    }
}
~~~

**Why is this code more reliable than placing @Order on a bean method?**

- Filters are created inside **FilterRegistrationBean**; the registration bean itself sets order=10/20 and the URL mapping.
- Filters are not annotated with @Component, avoiding accidental automatic filter registration.
- The two interceptors receive explicit orders in **InterceptorRegistry**, without relying on @Order on a class.
- Both filters and interceptors match only /trace; the trace-lookup endpoint will not generate additional demo events.
- Dispatcher type is REQUEST only, so the demo does not count extra ERROR dispatches.
- Because the handler uses synchronous HTTP, the request-scoped list is never modified concurrently by multiple async threads.

### 8.6. TraceController.java

File: src/main/java/com/example/ordering/TraceController.java

~~~java
package com.example.ordering;

import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class TraceController {

    private final TraceStore store;

    public TraceController(TraceStore store) {
        this.store = store;
    }

    public record TracePayload(
        String id,
        List<String> beforeResponse
    ) {
    }

    @GetMapping("/trace")
    public TracePayload trace(HttpServletRequest request) {
        TraceState.add(request, "controller");

        return new TracePayload(
            TraceState.id(request),
            TraceState.snapshot(request)
        );
    }

    @GetMapping("/trace/result/{id}")
    public List<String> completed(@PathVariable String id) {
        List<String> events = store.find(id);

        if (events == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Trace not yet available"
            );
        }

        return events;
    }
}
~~~

**Why are there two endpoints?**

GET /trace returns a snapshot taken inside the controller. At that moment, postHandle, afterCompletion, and both filters' finally blocks **have not completed yet**, so the JSON body contains only the inbound events.

GET /trace/result/{id} is called after the first request, reading the snapshot saved by the outer Filter in its finally block. Because this URL is outside the `/trace` registration mapping, it does not trigger additional trace events.

### 8.7. Running with Maven

~~~bash
./mvnw spring-boot:run
~~~

On Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Assuming the server listens on the default port 8080 with no context path:

~~~bash
curl -sS http://localhost:8080/trace
~~~

Expected body has a distinct UUID id per request and a beforeResponse array **in this exact order**:

~~~json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "beforeResponse": [
    "filter-A.before",
    "filter-B.before",
    "interceptor-A.pre",
    "interceptor-B.pre",
    "controller"
  ]
}
~~~

id is illustrative; actual UUIDs are randomly generated and will differ.

Use the actual id returned to call:

~~~bash
curl -sS http://localhost:8080/trace/result/123e4567-e89b-12d3-a456-426614174000
~~~

Result after /trace completes:

~~~json
[
  "filter-A.before",
  "filter-B.before",
  "interceptor-A.pre",
  "interceptor-B.pre",
  "controller",
  "interceptor-B.post",
  "interceptor-A.post",
  "interceptor-B.after",
  "interceptor-A.after",
  "filter-B.after",
  "filter-A.after"
]
~~~

This list illustrates the exact difference between **before the handler** and **post-handler unwinding** in a synchronous demo. Do not treat this 11-event sequence as a universal claim for exceptions, async processing, or every security/proxy setup.

### 8.8. Integration Test on Embedded Servlet Container

MockMvc can test the HandlerInterceptor chain, but if your goal is verifying **actual Servlet filter registration**, use an HTTP integration test against a real server.

File: src/test/java/com/example/ordering/TraceIntegrationTest.java

~~~java
package com.example.ordering;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class TraceIntegrationTest {

    @Autowired
    private TestRestTemplate client;

    @Autowired
    private TraceStore store;

    @Test
    void verifiesRealFilterAndInterceptorOrder() {
        TraceController.TracePayload response = client.getForObject(
            "/trace", TraceController.TracePayload.class
        );

        assertThat(response).isNotNull();
        assertThat(response.id()).isNotBlank();
        assertThat(response.beforeResponse()).containsExactly(
            "filter-A.before",
            "filter-B.before",
            "interceptor-A.pre",
            "interceptor-B.pre",
            "controller"
        );

        await().atMost(Duration.ofSeconds(3))
            .untilAsserted(() ->
                assertThat(store.find(response.id())).containsExactly(
                    "filter-A.before",
                    "filter-B.before",
                    "interceptor-A.pre",
                    "interceptor-B.pre",
                    "controller",
                    "interceptor-B.post",
                    "interceptor-A.post",
                    "interceptor-B.after",
                    "interceptor-A.after",
                    "filter-B.after",
                    "filter-A.after"
                )
            );
    }
}
~~~

TestRestTemplate + AssertJ + Awaitility are provided in standard spring-boot-starter-test 3.5.x test setups. The test makes a real HTTP request to the embedded container, reads the snapshot, and uses Awaitility to wait for the store to update after the outer filter and callbacks complete.

Do not replace this test with mere assertions that FilterRegistrationBean.getOrder() returns 10/20. A getter only proves **intended configuration**, not that a real request actually traversed the filters in that order.

## 9. Changing Order and Predicting the Outcome

If you change:

~~~java
return registration(filter, "trace-inner", 5);
~~~

for Filter B, inbound order flips: Filter B is registered ahead of Filter A. However, **the current demo assumes Filter A generates the trace ID and saves the snapshot at the end**. When B runs before A, Filter B creates request-scoped events before a trace ID exists; those still record, yet the snapshot saved in A's finally executes **before** B's finally adds B's final event. Therefore, you must update the recorder logic and tests whenever you change the outer filter's relative order.

This reveals a deeper lesson: changing filter order changes not only log order, but also **who wraps whom, who owns the lifecycle, when cleanup runs, and when the response commits**.

Whenever you test the impact of changing order, write a new test for the updated order rather than changing a number and assuming everything stays valid.

## 10. Checking Servlet Filter Order in Startup Logs

Spring Boot recommends enabling debug logging for the web logging group to inspect Filter registrations. In development:

~~~properties
logging.level.web=debug
~~~

Or when running:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--logging.level.web=debug
~~~

Startup logs can list Filter registrations, orders, and URL patterns. Logger names and log line formats depend on Boot version and server, so do not assert against a hardcoded log string.

When the security starter is present, the web logging group **does not** show the full order of internal security filters inside FilterChainProxy. You need Spring Security's own logging when investigating the security chain.

Cross-check three types of evidence:

1. **Registration metadata**: class, URL pattern, order, dispatcher types.
2. **Runtime trace**: which filters/handlers/interceptors actually receive a request.
3. **HTTP outcome**: response status, headers, body, and error/async redispatches.

Looking only at an order field on a bean is insufficient to know whether a route matches or whether a filter is skipped by dispatcher type.

## 11. Spring Security: Two Levels of Ordering

If the application includes spring-boot-starter-security, there is typically a Servlet Filter representing security integration using **DelegatingFilterProxy** and **FilterChainProxy**.

~~~text
Servlet container filter chain
      |
      +-- Application Filter A
      |
      +-- Spring Security DelegatingFilterProxy
      |       |
      |       v
      |    FilterChainProxy
      |       |
      |       +-- selects first SecurityFilterChain matching request
      |                |
      |                +-- Security Filter 1
      |                +-- Security Filter 2
      |                +-- Security Filter 3
      |
      +-- Application Filter B
      |
      v
DispatcherServlet / MVC Interceptors
~~~

There are **two distinct decisions**:

1. The Servlet container decides DelegatingFilterProxy's position in the Servlet Filter chain.
2. Spring Security decides **which SecurityFilterChain** is selected and in what order **the security filters inside that chain** execute.

### @Order on SecurityFilterChain

Illustrative example with two chains:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    http.securityMatcher("/api/**");
    // Configure API-specific rules.
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browserSecurity(HttpSecurity http)
        throws Exception {
    // Configure rules for remaining requests.
    return http.build();
}
~~~

These snippets are **illustrative skeletons**, not secure configurations or standalone runnable projects; they require dependencies, imports, and concrete authorization rules. @Order(1) and @Order(2) control **the evaluation order of SecurityFilterChain beans**. Spring Security picks **the first chain whose RequestMatcher matches** and does not also run later chains simply because they might also match.

### Filter Ordering Inside a SecurityFilterChain

Spring Security establishes internal filter ordering via predefined slots. To insert a custom filter at the right spot, use:

- http.addFilterBefore(customFilter, KnownFilter.class)
- http.addFilterAfter(customFilter, KnownFilter.class)
- http.addFilterAt(customFilter, KnownFilter.class) when you understand the exact semantics.

**@Order on a custom Filter class does not guarantee its position inside FilterChainProxy.** Moreover, if a custom Filter is both a `@Component` and passed into HttpSecurity, Boot may also register it as a **separate Servlet Filter**, causing execution outside the security chain or double registration. Prevent this by designing registration intentionally (e.g., disabling standalone servlet registration if the filter belongs strictly in the security chain).

Do not use HandlerInterceptor as a primary security boundary. Spring Security handles authentication/authorization in the filter chain, which is far better suited to protecting requests before MVC routing.

## 12. Spring WebFlux: WebFilter Uses a Different Ordering System

Spring WebFlux defines **org.springframework.web.server.WebFilter**:

~~~java
Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
);
~~~

Unlike a Servlet Filter, WebFilter returns a **Mono<Void>** describing reactive processing; it does not use jakarta.servlet.FilterChain.

Example:

~~~java
@Component
@Order(10)
public class FirstWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        System.out.println("webfilter-A.before");

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println("webfilter-A.finally:" + signal)
            );
    }
}
~~~

This is an illustrative class requiring Reactor/Spring imports and a proper logger in production. When the framework subscribes, lower-order WebFilters can precede higher-order ones in the WebFlux WebFilter chain. Post-chain hooks depend on completion/error/cancellation; never assume all callbacks execute on the same thread or synchronously like Servlets.

With two WebFilters A=10 and B=20:

~~~text
WebFilter A -> WebFilter B -> WebHandler/DispatcherHandler
       \___________________________/
     publishers complete per lifecycle
~~~

A WebFilter can short-circuit by not calling chain.filter(exchange), preventing downstream WebFilters and handlers from running. Adding a filter with a lower order does not guarantee it observes the final response as expected if the chain is cancelled or another filter mutates the exchange.

Spring WebFlux Security also uses **SecurityWebFilterChain**, with its own chain selection order and internal filter positions; never copy Servlet HttpSecurity examples as instructions for ServerHttpSecurity.

**Do not apply Servlet FilterRegistrationBean or MVC InterceptorRegistry to a pure WebFlux app running on Reactor Netty.** The web stack dictates the appropriate interface and ordering mechanism.

## 13. @Order on WebMvcConfigurer and @ControllerAdvice Means Something Different

### WebMvcConfigurer

Spring can sort WebMvcConfigurer beans when collecting configurers to apply configuration. However, an @Order on a WebMvcConfigurer class does not automatically define the order of **individual HandlerInterceptors** registered across different configurers.

If interceptor A must precede B, use **InterceptorRegistration.order(int)** on each registration instead of relying on configurer bean order.

### @ControllerAdvice

In exception-handling extension points, @Order can decide which advice is considered first when multiple advices apply. This is **exception resolution order**, not Servlet Filter order.

Furthermore, an `@ExceptionHandler` returning a successful response can prevent the request from passing through /error; thus a filter mapped only to DispatcherType.ERROR may never see errors handled by advice.

### @Order Is Not @Primary

@Primary selects a preferred bean when multiple dependency candidates of the same type exist; @Order primarily **sorts collections or pipelines** where supported. Using @Order(0) is not a substitute for @Primary at a single injection point.

### @Order Is Not @DependsOn

@DependsOn affects init/dependency order; @Order is for supported sorters/pipelines. Placing @DependsOn("filterA") on Filter B does not prove Filter A will run before B on every request.

## 14. Situations Where Actual Traces Differ from Expectations

| Symptom | Common Cause | What to Check |
|---|---|---|
| Filter B enters before A even though A's @Bean method has smaller @Order | @Bean method annotation does not set Servlet filter registration order | @Order on Filter class, Ordered, or FilterRegistrationBean.setOrder |
| Interceptor runs after filter despite smaller interceptor order | Two independent ordering layers | Filter chain sits outside DispatcherServlet |
| MVC interceptor with @Order(1) does not run first | Not registered or registry order differs | WebMvcConfigurer.addInterceptors(...).order(1) |
| Custom security filter runs twice | Both auto-registered Servlet Filter and added to HttpSecurity | Single registration mechanism or disabled container registration |
| Handler responds but filter never runs | URL pattern/dispatcher type mismatch, filter disabled | FilterRegistrationBean patterns/types |
| Filter logs appear twice | REQUEST and ERROR or ASYNC redispatch | DispatcherType and filter mapping |
| preHandle runs but postHandle is missing | Another preHandle returned false, exception, or async path | HandlerExecutionChain lifecycle and exceptions |
| Header added in postHandle does not appear | @ResponseBody/ResponseEntity already committed | Set header earlier or use ResponseBodyAdvice |
| Changing order causes full trace to miss last event | Recorder sits in a filter no longer outermost | Move recorder to proper lifecycle owner or update tests |
| SecurityFilterChain order changed but auth rules still wrong | Different RequestMatcher or internal filter order | Security chain selection + internal filters |
| WebFilter doFinally did not run when expected | Reactive subscription/cancellation | Reactor signals, schedulers, chain completion |
| Filters with same order swap after upgrade | Relied on tie-breaking/registration order instead of explicit order | Assign distinct orders and add integration tests |

## 15. Production Order-Investigation Workflow

1. **Identify the web stack:** MVC Servlet or WebFlux? Are both MVC and WebFlux starters present? Boot normally picks MVC by default when both appear.
2. **Inventory every layer:** Servlet Filters, Spring Security FilterChainProxy, HandlerInterceptors, controllers, advice, response writers.
3. **Check registration sources:** @Component Filter, @FilterRegistration, FilterRegistrationBean, InterceptorRegistry, SecurityFilterChain, or WebFilter beans.
4. **Check scope:** URL patterns, servlet path/context path, dispatcher types, security RequestMatchers, and WebFlux routes.
5. **Check effective order:** @Order on the right class, Ordered.getOrder(), registrationBean.setOrder, or registry.order.
6. **Enable targeted logs:** logging.level.web=debug for filter registrations; Spring Security DEBUG/TRACE when needed and permitted.
7. **Attach a per-request correlation ID:** log before/after, dispatcher type, thread, path, filter/interceptor name, and elapsed time.
8. **Run real HTTP tests:** hit an endpoint that triggers before/after callbacks, verifying actual trace and response.
9. **Test error branches:** 401, 403, 404, 500, validation errors, and /error dispatches to see if order changes.
10. **Check async and streaming if used:** never treat synchronous request results as proof for reactive or Servlet async signals.
11. **Never log sensitive data:** avoid passwords, Authorization headers, cookies, raw bodies, and user details.
12. **Add regression tests:** whenever adding a security starter, swapping containers, upgrading Spring Boot, or changing filters/interceptors.

### Recommended Log Format

~~~text
traceId=req-123 dispatcher=REQUEST stage=filter-A.before path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=filter-B.before path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=interceptor-A.pre path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=controller path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=interceptor-A.after path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=filter-B.after path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=filter-A.after path=/api/orders
~~~

This is a **format example**, not empirical output. In an app that also includes interceptor B, its events should appear as well. Logging stage alongside traceId lets you group per request; never rely on global line order across concurrent requests.

## 16. Self-Check Exercises

**Q1.** Two Servlet Filters have orders 10 and 20. During a REQUEST dispatch, which one enters first?

**Q2.** When two filters use try/finally and chain.doFilter, what is the finally execution order?

**Q3.** Is @Order(10) on a @Bean method returning a Filter sufficient to set Servlet Filter registration order?

**Q4.** Which API should you use to set order for a HandlerInterceptor when using WebMvcConfigurer?

**Q5.** MVC Interceptor A has order 1 and Servlet Filter B has order 100. Does that mean A runs before B?

**Q6.** How does PriorityOrdered differ from standard Ordered in supported comparators?

**Q7.** Does @Order guarantee singleton beans initialize in that order?

**Q8.** Will a Filter mapped only to /api/* run on /actuator/health if no other registration exists?

**Q9.** Why might a filter mapped to REQUEST and ERROR see two invocations for a single failed request?

**Q10.** What does @Order on SecurityFilterChain control? Which API inserts a custom security filter before a standard filter?

**Q11.** Why does @ResponseBody/ResponseEntity make postHandle unreliable for setting response headers?

**Q12.** How do you verify order on an embedded container instead of just checking getOrder getters?

**Q13.** What is the risk of annotating a Filter class with @Component and also passing it to HttpSecurity.addFilterBefore?

**Q14.** Does WebFlux's WebFilter use Servlet FilterRegistrationBean?

**Q15.** When two components share order=10, should critical code depend on which runs first?

### Answers

1. Order 10 enters before order 20, provided both match the URL and dispatcher type.
2. Filter 20 finally runs, then Filter 10 finally in the nested chain model.
3. No. Boot instructs using @Order on the **Filter class**, implementing Ordered, or calling FilterRegistrationBean.setOrder.
4. registry.addInterceptor(interceptor).order(value).
5. No; the Servlet filter chain sits outside the Spring MVC interceptor chain.
6. PriorityOrdered belongs to a special priority group, typically sorted ahead of regular Ordered instances per the comparator contract.
7. No; bean creation order follows the dependency graph/lifecycle, not @Order.
8. No, assuming the pattern does not match and no other mapping applies.
9. The container may perform an internal ERROR dispatch after REQUEST; filter registration controls which dispatcher types apply.
10. It sets the evaluation order of SecurityFilterChain beans; use HttpSecurity.addFilterBefore/After to insert a filter into a chain.
11. Body/status/headers may already have been written in HandlerAdapter before postHandle.
12. Use `@SpringBootTest(RANDOM_PORT)` with TestRestTemplate or a real HTTP client, record a request-scoped trace, and assert event order.
13. Double registration or execution in two different chains; manage registrations deliberately.
14. No. WebFilter uses the reactive WebFilterChain and @Order/Ordered per WebFlux.
15. No; assign distinct order values and verify at runtime whenever relative ordering matters.

## 17. Official References

- [Spring Framework — Ordered Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html): order values, HIGHEST_PRECEDENCE and LOWEST_PRECEDENCE constants.
- [Spring Framework — @Order Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html): ordering metadata and distinction from singleton startup.
- [Spring Framework — PriorityOrdered Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/PriorityOrdered.html): priority grouping and Comparator behavior.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Filter registration, @Order on Filter classes, FilterRegistrationBean, and startup debug logging.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): Filter registration and DispatcherType.
- [Spring Framework — MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-interceptor.html): preHandle/postHandle/afterCompletion and committed responses.
- [Spring Framework — InterceptorRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/config/annotation/InterceptorRegistration.html): order(int), default 0, and path patterns.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy, SecurityFilterChain selection, and addFilterBefore/After.
- [Spring Framework — WebFlux WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html): reactive WebFilter chain.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): embedded-server integration tests.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): FilterChain and DispatcherType.