# Filter, FilterChain, and the Rules of Calling `chain.doFilter` in Servlet

## 1. Why Understand FilterChain Before Learning Spring Security?

In a Servlet-based web application, an HTTP request does not necessarily go straight to an `HttpServlet` or a Spring MVC controller. The Servlet container (for example, Tomcat) can route the request through multiple `Filter` instances to handle cross-cutting concerns such as logging, character encoding, CORS, access control, or forwarding to security mechanisms. Those filters coordinate via `FilterChain`.

The central statement is **`chain.doFilter(request, response)`**: the current filter yields control to the rest of the chain. When this call finishes, execution returns right after the `chain.doFilter` line of the current filter, allowing a filter to perform work **before** and **after** downstream processing.

Understanding these three concepts clearly is a prerequisite for reading the Spring Security Servlet flow:

- **`Filter`**: an intercepting component at the Servlet layer; its `doFilter` method receives the request, response, and a `FilterChain`.
- **`FilterChain`**: an object provided by the runtime environment to invoke the next filter, or the final target of the chain (the target servlet / dispatch mechanism).
- **`chain.doFilter(...)`**: the operation that continues the chain; it does not automatically mean “access granted”, nor does it create a new HTTP request.

Diagram for a request with two filters registered in the order A then B:

```text
HTTP request
    |
    v
Filter A: pre-processing
    |
    | A calls chain.doFilter
    v
Filter B: pre-processing
    |
    | B calls chain.doFilter
    v
Servlet / Spring MVC DispatcherServlet
    |
    | processing complete, returns control
    v
Filter B: post-processing
    |
    v
Filter A: post-processing
    |
    v
HTTP response
```

Thus, “before” steps run in the order **A → B → target**, while “after” steps run in the order **target → B → A**. Actual execution order is determined by filter registration and dispatch type; class names or declaration order in examples do not automatically guarantee runtime order.

## 2. Servlet API Contract and Lifecycle

On Spring Boot 3 / Spring Framework 6 and modern Jakarta Servlet, the core types and methods live in `jakarta.servlet`:

```java
public interface Filter {
    void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain
    ) throws IOException, ServletException;
}

public interface FilterChain {
    void doFilter(
        ServletRequest request,
        ServletResponse response
    ) throws IOException, ServletException;
}
```

This is a **simplified excerpt of the relevant signatures**, not the full source of those interfaces. `Filter` also has lifecycle hooks `init(FilterConfig)` and `destroy()`; typical applications only need to override `doFilter` if no custom initialization/cleanup is required.

- **Initialization**: the container creates/initializes the filter per configuration; `init` can receive the filter's configuration.
- **Serving requests**: the container invokes `doFilter` for requests or dispatches matching its mapping. A single filter instance can serve multiple concurrent requests on different threads.
- **Destruction**: the container calls `destroy` when taking the filter out of service per its lifecycle.

**Thread-safety consequence:** never store per-request state in mutable fields of a shared filter, such as `private String currentUser` or `private long startTime`. Use local variables inside `doFilter`, request attributes when appropriate, or context-management mechanisms with proper cleanup.

`ServletRequest` and `ServletResponse` are general types. For an HTTP application, they are normally `HttpServletRequest` and `HttpServletResponse`; cast only when you are sure the filter handles HTTP. A filter can pass the original objects downstream or wrap them with `ServletRequestWrapper` / `ServletResponseWrapper` to alter reading/writing behavior. In all cases, the arguments passed to `chain.doFilter` determine what objects the next layer receives.

## 3. What Happens at `chain.doFilter`?

Consider this typical structure:

```java
// Illustrating the body of the doFilter method
before(request);
try {
    chain.doFilter(request, response);
} finally {
    after(request);
}
```

Here, `before` and `after` are simply operation names describing the sequence, **not a standalone Java program**. At runtime:

1. The current filter runs its pre-chain step.
2. `chain.doFilter` hands control to the remainder of the chain. The next filter may continue, return an error, wrap request/response, or stop processing.
3. When downstream returns normally or throws an exception, the current filter's `finally` block still runs.
4. If downstream throws an exception, once `finally` completes, the exception continues propagating unless another layer handles it.

Calling `chain.doFilter` is **not mandatory on every branch**. A filter is allowed to short-circuit a request if it has already produced a valid response. For example, a maintenance-blocking filter can return HTTP 503 and `return` without reaching the servlet. However, a filter meant for observation or logging normally needs to forward the request so the application works.

A useful practical rule:

> For **a single `doFilter` execution** along the normal forwarding path, call `chain.doFilter(request, response)` **exactly once**. Skip it only when intentionally terminating the request or handling a redirect/alternative response. Do not call it multiple times unless you have a specialized design and have verified the consequences.

This is a design rule for most filters rather than a syntactic constraint of the Java API: the interface does not prevent calling it 0 or 2 times, but those choices drastically alter control flow.

## 4. Real Servlet Filter Example: Measuring Processing Time

The following example targets a web environment running the **Jakarta Servlet API**. The class has no `main`; it is invoked by the Servlet container when a request matches the mapping.

```java
package example.web;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.annotation.WebFilter;
import jakarta.servlet.http.HttpServletRequest;

import java.io.IOException;

@WebFilter(
    urlPatterns = "/*",
    dispatcherTypes = DispatcherType.REQUEST
)
public final class RequestTimingFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain
    ) throws IOException, ServletException {
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        long startedAt = System.nanoTime();

        System.out.println("ENTER " + httpRequest.getRequestURI());
        try {
            // Pass the original request and response along.
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                    (System.nanoTime() - startedAt) / 1_000_000;
            System.out.println(
                    "EXIT  " + httpRequest.getRequestURI()
                    + " after " + elapsedMs + " ms"
            );
        }
    }
}
```

**Explanation:**

- `@WebFilter` describes the URL mapping. The pattern `/*` applies across application URLs for the `REQUEST` dispatch type; it **does not automatically guarantee** the filter is activated in every Spring Boot setup.
- In Spring Boot with an embedded servlet container, you need a matching registration mechanism, such as `@ServletComponentScan` to scan `@WebFilter`, **or** a `FilterRegistrationBean`. Pick one registration mechanism for the same filter to avoid duplicate execution.
- `try/finally` ensures the `EXIT` line is printed even if downstream throws an exception; it neither swallows the exception nor re-invokes the chain.
- Measured durations depend on runtime conditions; there is no fixed stdout to assert against. If a request starts asynchronous processing, this timing wraps only the current **synchronous call**, not necessarily all async work.
- In real applications, replace `System.out` with a proper logger and take care not to log sensitive data.

If compiling the class standalone outside Spring Boot, you must provide `jakarta.servlet-api` on the compile classpath (such as Jakarta Servlet 6.0 for a matching environment) and deploy to a Servlet container; **`java example.web.RequestTimingFilter` is not a valid run command** because the class has no `main`.

## 5. Standalone Java 17 Run: Observing the Exact Order

To see the execution flow yourself without Tomcat, the program below **simulates the chain continuation principle** using custom interfaces. `Step` / `Next` are **not** `jakarta.servlet.Filter` / `FilterChain`; this is a learning model runnable on Java 17 or newer.

Create `FilterChainDemo.java`:

```java
import java.util.List;

public class FilterChainDemo {
    record Request(String path) {}

    @FunctionalInterface
    interface Next {
        void run(Request request);
    }

    @FunctionalInterface
    interface Step {
        void run(Request request, Next chain);
    }

    static Next compose(List<Step> filters, Next endpoint) {
        Next next = endpoint;

        for (int i = filters.size() - 1; i >= 0; i--) {
            Step current = filters.get(i);
            Next remainder = next;
            next = request -> current.run(request, remainder);
        }
        return next;
    }

    public static void main(String[] args) {
        Step audit = (request, chain) -> {
            System.out.println("audit: before");
            try {
                chain.run(request);
            } finally {
                System.out.println("audit: after");
            }
        };

        Step guard = (request, chain) -> {
            if (request.path().equals("/blocked")) {
                System.out.println("guard: blocked");
                return;
            }
            System.out.println("guard: pass");
            chain.run(request);
        };

        Next endpoint = request ->
                System.out.println("endpoint: " + request.path());

        Next pipeline = compose(List.of(audit, guard), endpoint);

        System.out.println("=== /ok ===");
        pipeline.run(new Request("/ok"));
        System.out.println("=== /blocked ===");
        pipeline.run(new Request("/blocked"));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac FilterChainDemo.java
java FilterChainDemo
```

Exact stdout:

```text
=== /ok ===
audit: before
guard: pass
endpoint: /ok
audit: after
=== /blocked ===
audit: before
guard: blocked
audit: after
```

For `/ok`, `audit` invokes the remainder, `guard` continues, and the endpoint runs. For `/blocked`, `guard` returns immediately: the endpoint does **not** run, yet `audit` still continues in its `finally` block. That is how to read the call stack of `chain.doFilter` in a real servlet.

## 6. When Is It Allowed Not to Call the Chain?

A filter may terminate a request itself when intentionally producing a response, such as blocking a path under maintenance. Inside an HTTP `doFilter`, the following snippet illustrates a concrete decision:

```java
HttpServletRequest req = (HttpServletRequest) request;
HttpServletResponse res = (HttpServletResponse) response;

if (req.getRequestURI().equals(req.getContextPath() + "/maintenance")) {
    res.sendError(
            HttpServletResponse.SC_SERVICE_UNAVAILABLE,
            "Endpoint temporarily unavailable"
    );
    return; // Intentionally stop, do not call chain.doFilter.
}

chain.doFilter(request, response);
```

This is a **code snippet inside a `doFilter` method**, requiring imports for `jakarta.servlet.http.HttpServletRequest` / `HttpServletResponse` and an appropriate filter context to use; it is not a standalone class.

Three cases must be distinguished:

- **Forwarding:** call the chain exactly once so downstream filters/servlets handle the request.
- **Intentional blocking:** set a valid status, body, or redirect on the response and then end the branch. You may use `sendError`, `sendRedirect`, or write the response depending on the requirement; do not call the chain after deciding to block.
- **Unintended failure:** an exception is thrown/propagated; silently calling `return` easily creates situations where the controller does not run while the client receives an empty response or a misleading default status.

Do not use an arbitrary header-blocking example as a substitute for Spring Security authentication and authorization. The goal here is purely to distinguish **continuing the chain** from **ending the chain**.

## 7. Common Pitfalls with `chain.doFilter`

| Incorrect pattern or wrong assumption | Consequence / fix |
| --- | --- |
| Forgetting to call `chain.doFilter` in a logging filter | Controller/servlet is never called, even though the filter may report no error. Identify intentional blocking branches; normal branches must continue. |
| Calling `chain.doFilter` twice in the same branch | Downstream code may execute twice, write the response twice, or throw an error. Do not use the chain as a “retry function”. |
| Placing the chain call inside `finally` after running it in `try` | On normal return or exception, it will invoke the chain a second time. Put only necessary **cleanup** inside `finally`. |
| Calling `sendError` / `sendRedirect` and still calling the chain | Downstream layers may try to write to an already handled or committed response. `return` on the terminated branch. |
| Swallowing `IOException` / `ServletException` and treating the request as successful | Hides real errors. Catch only when handling intentionally; otherwise let the exception propagate. |
| Writing headers/body after `chain.doFilter` assuming the response is not sent yet | A downstream servlet may have committed the response; afterward, header/status changes are no longer guaranteed to take effect. Adjust at the right point or use a wrapper if truly needed. |
| Reading the entire request body in a filter and passing the unwrapped request downstream | Downstream servlet/controller may have no body left to read. Use a proper buffering/wrapper strategy if re-reading is needed. |
| Storing per-request data in a filter field | Concurrent requests can overwrite each other's data. Use local variables or request-scoped state. |
| Seeing a filter run multiple times and concluding `chain.doFilter` was called twice | Could be due to multiple dispatches, duplicate filter registration, multiple actual requests, or async/error handling. Check registration, dispatcher, and request ID first. |

**Why does `finally` still matter?** It is suited for releasing resources or clearing context set by the filter itself. If using `ThreadLocal` / MDC, clean it up in `finally` to prevent stale request data from leaking to other work on the same thread. However, in asynchronous processing, threads across stages may differ: do not treat a `ThreadLocal` as persistent context for the entire request.

## 8. Mapping, Order, and Dispatcher Types

A filter is not activated merely because a class implements `Filter`. The Servlet container must **register** the filter and **map** it to URLs/servlets and dispatch types. Common registration sources are `web.xml`, `@WebFilter` scanned by the container, or programmatic configuration such as `FilterRegistrationBean` in Spring Boot.

Servlet dispatch types include:

- `REQUEST`: an incoming request through the normal HTTP path.
- `FORWARD`: internal forwarding via `RequestDispatcher.forward`.
- `INCLUDE`: resource inclusion via `RequestDispatcher.include`.
- `ASYNC`: dispatch within an asynchronous processing flow.
- `ERROR`: dispatch for container-managed error handling.

Which dispatches invoke a filter depends on its mapped **dispatcherTypes**. Therefore, “each request runs a filter only once” is not a universal truth: one HTTP request can go through multiple dispatches, and each dispatch may match different filters. Likewise, calling `chain.doFilter` once **per invocation** does not mean the container will call the filter only once across the entire HTTP request lifecycle.

Order between filters must also be configured and verified. With Spring Boot, `FilterRegistrationBean#setOrder` is one way to adjust the order of **servlet container-level** filters. The order of filters **inside Spring Security** is determined by security configuration/infrastructure; do not infer it directly from container registration order.

**Remember about async and error:** `chain.doFilter` can return once the endpoint starts async processing while the response is not yet complete. Measuring total request duration or cleaning up context across multiple dispatches requires understanding `AsyncContext` / `AsyncListener`, dispatcher mappings, and the framework's async mechanics. When an error triggers an error dispatch, a filter may appear in another invocation if its mapping allows it.

## 9. Concrete Connection to Spring Security Servlet

Spring Security uses the exact Servlet filter contract while adding an internal orchestration layer. A common conceptual diagram:

```text
Servlet container FilterChain
  |
  v
DelegatingFilterProxy ("springSecurityFilterChain")
  |
  v
Spring bean FilterChainProxy
  |
  +--> selects the first SecurityFilterChain matching the request
          |
          +--> Security Filters in configured order
                    |
                    +--> continues to the rest of the Servlet FilterChain
                              |
                              v
                         DispatcherServlet / endpoint
```

These similar-sounding names have distinct responsibilities:

- **`jakarta.servlet.FilterChain`** is the chain-continuation contract at the Servlet layer.
- **`DelegatingFilterProxy`** is a Servlet Filter that delegates to a Spring bean; the commonly used bean name is `springSecurityFilterChain`.
- **`FilterChainProxy`** orchestrates security filters, selects the matching security chain for the request, and executes the filters in that chain.
- **`SecurityFilterChain`** in Spring Security represents a **list of security filters and a request-matching condition**. It is not the `chain` parameter passed directly into `Filter#doFilter`.

When a security filter calls `chain.doFilter`, it advances to the next step **in the chain it participates in**. Authentication, access denial, login redirect, or exception handling can stop the flow **from reaching the controller**. That is not necessarily a bug; inspect each filter's decision and the actual response.

**Two practical integration warnings:**

1. A custom filter can be registered directly with the **Servlet container** or placed inside the **Spring Security filter chain**, depending on its purpose. If it is both auto-registered by Boot as a Servlet Filter bean and added to the Security chain, it can run twice. Check the registration mechanism; if it is meant only for the Security chain, you may need to disable its separate servlet registration.
2. Spring provides `OncePerRequestFilter` to support “once-per-request” logic managed by the framework, but you must still understand `ASYNC` / `ERROR` handling and related hooks like `shouldNotFilterAsyncDispatch` and `shouldNotFilterErrorDispatch`. A class name does not replace understanding dispatchers and filter registration.

In this Servlet foundation lesson, the key takeaway is the **call down – return back up – optionally stop intentionally** mechanism. Detailed authentication, authorization, and security filter ordering configuration belong to their respective deep-dive lessons.

## 10. How to Read and Debug a Real Filter Chain

When an endpoint is not called or a filter appears twice, start from a reproducible request and verify step by step:

1. **Registration:** is the filter registered in the container, in Spring Security, or both? Check URL patterns and dispatcher types rather than just looking at annotations.
2. **Entry:** set a breakpoint/log at the start of `doFilter`; record method, URI, dispatcher type, and an appropriate request ID; avoid logging secrets such as tokens or session IDs.
3. **Continue:** identify which branch calls `chain.doFilter` and which branch does `return`, `sendError`, or `sendRedirect`; put breakpoints right before and after the call.
4. **Order:** with two filters, compare `before/after` logs; seeing A.before → B.before → B.after → A.after is the normal nested structure.
5. **Outcome:** distinguish thrown exceptions, committed responses, `ERROR` dispatches, and async processing; an `after` log line does not prove the client received the full response.
6. **Security:** if using Spring Security, check which `SecurityFilterChain` matches the request and whether any filter returns a response before the controller.

Dry-run reasoning examples without running a server:

- A calls chain; B calls chain; servlet returns → `A.before, B.before, servlet, B.after, A.after`.
- A calls chain; B sends 403 and returns → servlet does not run; A's code after `chain.doFilter` still runs.
- B throws `ServletException` → A's `finally` block still runs; the exception keeps propagating upward unless handled.
- A calls chain twice → you **cannot** assume it is two “harmless” filter passes; it can re-execute the endpoint or the remainder of the chain.

## 11. Knowledge Self-Check

**Scenario 1.** Filter A only logs before and after; Filter B blocks `/admin` and writes a 403 response. For a `/admin` request, does the controller run? Does Filter A still log after?

**Answer:** The controller does not run because B does not call the chain. If A uses `try/finally` around the chain call, A still logs after B returns control.

**Scenario 2.** You declare a custom filter as a Spring bean and also add it to `SecurityFilterChain`. Its logs appear twice. Is it certain that `chain.doFilter` was called twice in code?

**Answer:** Not necessarily. Check whether the filter is both auto-registered by the servlet container **and** run inside Spring Security; also check the dispatcher type and the number of actual requests.

**Scenario 3.** Why can you not claim “the filter's `finally` block finished running, which means the HTTP response is completely finished”?

**Answer:** `finally` only tells you that the synchronous downstream call returned or threw an error. Async processing may continue, or the container may still perform an error dispatch or finalize the response afterward.

## 12. Key Takeaways to Apply

- `Filter` wraps processing at the Servlet layer; `FilterChain` represents the remaining work.
- `chain.doFilter(request, response)` is the **handoff point**; once it returns, the current filter can run post-processing.
- On the normal continuation path, call the chain **once**; when intentionally blocking, produce a valid response and stop; never accidentally skip or duplicate the call.
- Use `try/finally` for cleanup, keeping exceptions, response commit, and async in mind; never put a second chain call inside `finally`.
- Check registration, order, dispatcher types, and thread safety before concluding a filter is “running wrong”.
- Spring Security builds on the same Servlet FilterChain principle while adding `DelegatingFilterProxy`, `FilterChainProxy`, and `SecurityFilterChain` to orchestrate security filters.
