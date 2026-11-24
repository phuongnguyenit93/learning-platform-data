# Cleaning Up `RequestContextHolder` to Prevent State Leakage Between Tests

`RequestContextHolder` is Spring's mechanism for storing `RequestAttributes` bound to the current thread. In a Servlet application, components such as `DispatcherServlet`, `RequestContextFilter`, or `RequestContextListener` can bind request information to the holder so downstream code can access the current request without passing `HttpServletRequest` through every method.

Because this state is held in a `ThreadLocal` (or `InheritableThreadLocal` when requested), it must be cleared from the thread when the request or test finishes. If a test binds `RequestAttributes` manually and forgets to call `RequestContextHolder.resetRequestAttributes()`, the test thread may retain the stale request. When JUnit or an executor reuses that thread, the next test may see the previous test's tenant, locale, session, or request attributes.

In Spring MVC tests run via `MockMvc`, Spring manages binding and cleanup within the dispatch lifecycle. However, when tests invoke services directly, create `ServletRequestAttributes` manually, run tasks on an executor, or interact with `RequestContextHolder` directly, the test is responsible for the lifecycle of the bound state.

## 1. What Does `RequestContextHolder` Store?

`RequestContextHolder` is a static utility class providing access to the `RequestAttributes` bound to the current thread. In a Servlet environment, the bound object is typically `ServletRequestAttributes`, wrapping `HttpServletRequest` and optionally `HttpServletResponse`.

Key APIs:

| API | Meaning |
|---|---|
| `setRequestAttributes(attributes)` | Binds attributes to the current thread without inheriting to child threads. |
| `setRequestAttributes(attributes, true)` | Binds using `InheritableThreadLocal`, allowing child threads created while bound to inherit the reference. |
| `getRequestAttributes()` | Returns the current attributes or `null` if none are bound. |
| `currentRequestAttributes()` | Returns the current attributes; throws `IllegalStateException` if no active request context exists. |
| `resetRequestAttributes()` | Removes both regular and inheritable request attributes from the current thread. |

Example of reading request attributes:

```java
RequestAttributes attributes = RequestContextHolder.currentRequestAttributes();
Object tenantId = attributes.getAttribute("tenantId", RequestAttributes.SCOPE_REQUEST);
```

In Servlet code, the real request can be retrieved from `ServletRequestAttributes`:

```java
ServletRequestAttributes attributes =
        (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();

HttpServletRequest request = attributes.getRequest();
String requestId = request.getHeader("X-Request-Id");
```

The holder does not create new requests and does not manage sessions or transactions itself. It only provides a reference to the `RequestAttributes` currently bound on the thread. If there is no request context, calling `currentRequestAttributes()` fails rather than fabricating a dummy context.

## 2. Why Can State Leak Between Tests?

`ThreadLocal` stores values per thread, not per test method. JUnit often runs multiple test methods on worker threads that can be reused. If test A sets request attributes without resetting them, test B running on the same thread may read the leftover state.

```text
JUnit worker thread T1
    |
    +--> Test A: setRequestAttributes(request-A)
    |
    +--> Test A ends without resetting
    |
    +--> Test B runs on T1
             |
             +--> currentRequestAttributes() returns request-A
```

This can cause confusing failures:

- Test B mistakenly reads headers or request parameters from test A.
- Request-scoped beans access the wrong session or tenant.
- Locale or current-user resolution logic receives stale data.
- Tests become order-dependent and only fail when running the full suite.
- Tests pass individually yet fail when executed in parallel or in CI.

Because `RequestContextHolder` uses `ThreadLocal`, two tests running on separate threads usually do not see each other's state. Problems arise when the same thread is reused, or when `InheritableThreadLocal` is used and child threads are created while a context is bound.

## 3. Manual Binding and Resetting in Unit Tests

When testing a service that needs to read the request context without going through `DispatcherServlet`, you can create a `MockHttpServletRequest`, wrap it in `ServletRequestAttributes`, and bind it to the holder.

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class CurrentTenantServiceTest {

    @Test
    void readsTenantFromCurrentRequest() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Tenant", "tenant-a");
        ServletRequestAttributes attributes = new ServletRequestAttributes(request);

        try {
            RequestContextHolder.setRequestAttributes(attributes);

            assertThat(RequestContextHolder.currentRequestAttributes())
                    .isSameAs(attributes);

            HttpServletRequest currentRequest =
                    ((ServletRequestAttributes)
                            RequestContextHolder.currentRequestAttributes()).getRequest();
            assertThat(currentRequest.getHeader("X-Tenant")).isEqualTo("tenant-a");
        } finally {
            RequestContextHolder.resetRequestAttributes();
            attributes.requestCompleted();
        }
    }
}
```

The key point is that `resetRequestAttributes()` is inside `finally`. Even if an assertion throws or the code under test fails, cleanup still runs on the exact thread that bound the context.

`ServletRequestAttributes.requestCompleted()` signals that the request has finished and executes any applicable request-scope destruction callbacks. When a test creates `ServletRequestAttributes` manually, call this method during cleanup if the test uses request-scoped destruction callbacks or wants to simulate full request completion. For tests checking only a simple reference, resetting the holder is mandatory to prevent thread-local leaks; `requestCompleted()` completes the lifecycle for the created attributes.

Do not call `resetRequestAttributes()` on a thread other than the one that bound the context. `ThreadLocal` only clears the value on the current thread.

## 4. Using try-with-resources for Automatic Cleanup

If multiple tests need to bind a request context, you can create a small helper implementing `AutoCloseable` so cleanup always runs when exiting the block.

```java
final class BoundRequestContext implements AutoCloseable {

    private final ServletRequestAttributes attributes;

    BoundRequestContext(MockHttpServletRequest request) {
        this.attributes = new ServletRequestAttributes(request);
        RequestContextHolder.setRequestAttributes(attributes);
    }

    @Override
    public void close() {
        try {
            RequestContextHolder.resetRequestAttributes();
        } finally {
            attributes.requestCompleted();
        }
    }
}
```

Using the helper in a test:

```java
@Test
void readsRequestScopedData() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.addHeader("X-Tenant", "tenant-b");

    try (BoundRequestContext ignored = new BoundRequestContext(request)) {
        assertThat(tenantService.currentTenant()).isEqualTo("tenant-b");
    }

    assertThat(RequestContextHolder.getRequestAttributes()).isNull();
}
```

`close()` runs both when the block finishes normally and when an assertion throws an exception. This helper is designed for tests that own the request context on the current thread and are not nested inside another request context. If a test needs to support nested binding, explicitly save and restore the previous context instead of always resetting to `null`.

## 5. Restoring Previous State When a Nested Context Is Needed

Some helpers may be called inside an already bound scope. In that case, resetting straight to `null` would wipe out the caller's context. Save the previous value and restore it upon exiting the scope.

For the simple case without inheritable binding:

```java
final class NestedRequestContext implements AutoCloseable {

    private final RequestAttributes previous;
    private final ServletRequestAttributes current;

    NestedRequestContext(MockHttpServletRequest request) {
        previous = RequestContextHolder.getRequestAttributes();
        current = new ServletRequestAttributes(request);
        RequestContextHolder.setRequestAttributes(current, false);
    }

    @Override
    public void close() {
        try {
            if (previous == null) {
                RequestContextHolder.resetRequestAttributes();
            } else {
                RequestContextHolder.setRequestAttributes(previous, false);
            }
        } finally {
            current.requestCompleted();
        }
    }
}
```

This example saves the previous `RequestAttributes` object and restores it as non-inheritable. Use this approach only when the helper's contract guarantees the previous context was non-inheritable or switching back to non-inheritable is acceptable. `getRequestAttributes()` does not indicate whether the previous context was bound via a regular `ThreadLocal` or `InheritableThreadLocal`; if the exact binding mode must be preserved, avoid building a nested helper based on this getter. A safer option for most tests is to avoid nesting contexts and use an independent scope with an explicit `try/finally`.

## 6. Using JUnit Lifecycle to Clean Up State

If a test class has multiple methods that need to bind a request context, cleanup can be placed in `@AfterEach`:

```java
class RequestContextHolderTest {

    @AfterEach
    void clearRequestContext() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test
    void firstTest() {
        // Test can bind the request context.
    }

    @Test
    void secondTest() {
        // Starts with a thread that no longer has request attributes from the previous test.
    }
}
```

`@AfterEach` is the proper place to ensure cleanup after each test method. You can add `@BeforeEach` to guarantee a clean initial state:

```java
@BeforeEach
void ensureNoRequestContextIsBound() {
    RequestContextHolder.resetRequestAttributes();
}
```

However, cleanup in `@BeforeEach` does not replace cleanup in `@AfterEach`. If you only reset before a test, state leaked from the last test remains after the class finishes and can affect the next test class running on the same thread. In addition, resetting before a test can mask an earlier test that forgot to clean up. Therefore, place cleanup where the binding is created and/or in `@AfterEach`; use `@BeforeEach` only as an extra guard when there is a specific reason.

### Creating a Shared JUnit Extension

If many test classes need a policy for cleaning up the request context, an extension can be used:

```java
import org.junit.jupiter.api.extension.AfterEachCallback;
import org.junit.jupiter.api.extension.ExtensionContext;
import org.springframework.web.context.request.RequestContextHolder;

public class RequestContextCleanupExtension implements AfterEachCallback {

    @Override
    public void afterEach(ExtensionContext context) {
        RequestContextHolder.resetRequestAttributes();
    }
}
```

Applying it:

```java
@ExtendWith(RequestContextCleanupExtension.class)
class SomeServiceTest {
}
```

An extension is useful when a test suite manually binds request contexts in many places. It only cleans up the thread executing the JUnit callback. If a test creates worker threads and binds request contexts on those workers, each worker must clean up on its own thread.

## 7. Spring MVC and MockMvc Manage Request Context Automatically

When tests go through `MockMvc`, requests are handled by `DispatcherServlet` and Spring manages the request context during the dispatch lifecycle. Tests usually do not need to call `RequestContextHolder.setRequestAttributes(...)` themselves.

Example:

```java
@WebMvcTest(CurrentRequestController.class)
class CurrentRequestControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void controllerReadsCurrentRequestHeader() throws Exception {
        mockMvc.perform(get("/current-request")
                        .header("X-Request-Id", "req-42"))
                .andExpect(status().isOk())
                .andExpect(content().string("req-42"));
    }
}
```

The controller can read the request context:

```java
@RestController
class CurrentRequestController {

    @GetMapping("/current-request")
    String currentRequestId() {
        ServletRequestAttributes attributes =
                (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();
        return attributes.getRequest().getHeader("X-Request-Id");
    }
}
```

`MockMvc.perform(...)` runs the request through the Servlet MVC test infrastructure. Spring binds request attributes during processing and clears them after dispatch. Manually binding a different mock request before calling MockMvc can complicate tests or obscure the framework's actual behavior.

If a test needs to confirm that no request context remains after the request finishes, it can assert right after `perform(...)` on the same thread:

```java
mockMvc.perform(get("/current-request"))
        .andExpect(status().isOk());

assertThat(RequestContextHolder.getRequestAttributes()).isNull();
```

This check fits synchronous request dispatches in tests. With async MVC, separate lifecycles and execution threads apply, as covered below.

## 8. RequestContextFilter and RequestContextListener

In a Servlet application, the request context can be bound by one of the following Spring mechanisms:

- `DispatcherServlet` binds request attributes during MVC dispatch.
- `RequestContextFilter` is a Servlet filter that binds the context before the processing chain and resets it after the chain completes.
- `RequestContextListener` binds the context according to the Servlet request lifecycle.

`RequestContextFilter` is often useful when code needing the request context runs outside `DispatcherServlet`, such as another Servlet or downstream filter. The filter must be registered in the Servlet container or test context to take effect.

Spring manages bind/reset in these mechanisms. Do not manually call `resetRequestAttributes()` in the middle of request handling, as doing so can deprive downstream code of a valid request context. Manual cleanup should only occur at boundaries where the test or component owns the binding.

If an application uses multiple binding mechanisms, avoid unnecessary duplicate configuration. Identify which mechanism owns the request lifecycle and ensure it always resets state inside `finally`, even when the filter chain or controller throws an exception.

## 9. Thread Pools and `InheritableThreadLocal`

`RequestContextHolder` uses a regular ThreadLocal by default. The overloaded API with `inheritable = true` uses `InheritableThreadLocal`, meaning child threads created while the context is bound can inherit the attributes reference from the parent thread.

Example:

```java
RequestContextHolder.setRequestAttributes(attributes, true);

try {
    // Create child thread within this scope.
} finally {
    RequestContextHolder.resetRequestAttributes();
}
```

A common pitfall is that `InheritableThreadLocal` copies the value when a child thread is created, not each time a task is submitted to a thread pool. Thread pools typically create workers up front and reuse them. Consequently:

- Workers created before the request was bound may not receive the context.
- Workers created during a request may retain the request reference after the parent request resets.
- A reused worker may keep state from an old request if the task does not clean up.

Do not enable inheritable request contexts indiscriminately with shared thread pools. Request attributes may hold request/response and session objects that become invalid once the request completes. A child thread holding that reference past the request lifecycle can lead to errors or access to expired state.

### Cleanup Must Run on the Thread That Bound the Context

Suppose a worker thread binds the context while processing a task:

```java
executor.submit(() -> {
    RequestContextHolder.setRequestAttributes(attributes);
    try {
        service.process();
    } finally {
        RequestContextHolder.resetRequestAttributes();
    }
});
```

Cleanup in `finally` must be inside the task so it executes on the worker thread. If the thread calling `executor.submit(...)` resets the holder right after submitting, that operation only clears the calling thread's ThreadLocal, not the worker's ThreadLocal.

If an executor uses a `TaskDecorator` to propagate context, the decorator should snapshot only the permitted data, bind it during task execution, and restore/clear it in `finally`. Avoid passing raw `ServletRequestAttributes` across long-lived asynchronous boundaries if the task may run after the request finishes.

## 10. Async Requests Do Not Mean Automatic Request Context Propagation

`RequestContextHolder` is thread-bound. When a request transitions to async processing, work may continue on a different thread. Do not assume `RequestContextHolder.currentRequestAttributes()` always holds the same value on every processing thread.

In Spring MVC, `Callable`, `DeferredResult`, and `WebAsyncTask` have their own async lifecycles. Spring manages request/dispatch context at appropriate points in Servlet MVC, whereas a custom executor or manually submitted background task does not automatically share the same request context.

If a background task needs information such as tenant, user id, or correlation id, a more robust approach is to extract the needed values at the request boundary and pass them as parameters or an immutable context object:

```java
record JobContext(String tenantId, String requestId) {
}

@PostMapping("/jobs")
ResponseEntity<Void> startJob(HttpServletRequest request) {
    JobContext context = new JobContext(
            request.getHeader("X-Tenant"),
            request.getHeader("X-Request-Id"));

    jobService.submit(context);
    return ResponseEntity.accepted().build();
}
```

The worker uses explicit data rather than reading a request thread-local after the request has ended. This also clarifies which data is permitted to outlive the request.

## 11. Distinguishing RequestContextHolder from Other ThreadLocals

Spring has several holders storing per-thread state. Resetting one holder does not automatically reset the others.

| Holder | Typically stored state | Corresponding cleanup |
|---|---|---|
| `RequestContextHolder` | `RequestAttributes` of the current request | `RequestContextHolder.resetRequestAttributes()` |
| `SecurityContextHolder` | `SecurityContext` and authentication | `SecurityContextHolder.clearContext()` |
| `LocaleContextHolder` | Current locale and time zone | `LocaleContextHolder.resetLocaleContext()` |
| `TransactionSynchronizationManager` | Transaction resources and synchronization metadata | Managed by the transaction manager; do not reset arbitrarily in tests. |
| Logging framework MDC | Correlation/request metadata | Use the corresponding logging framework's clear/remove API. |

If a test binds multiple context types manually, each type must be cleaned up according to its own lifecycle. Do not call internal APIs to clear transaction resources while a transaction manager is still managing a transaction; let the transaction framework complete rollback/commit and cleanup.

`RequestContextHolder.resetRequestAttributes()` only removes request attributes. It does not clear `SecurityContext`, MDC, locale, or transaction state.

## 12. Verifying That the Context Was Cleaned Up

After cleanup, `getRequestAttributes()` should return `null` if the thread has no other request context. `currentRequestAttributes()` should throw `IllegalStateException`.

```java
@Test
void resetRemovesCurrentRequestAttributes() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    ServletRequestAttributes attributes = new ServletRequestAttributes(request);

    RequestContextHolder.setRequestAttributes(attributes);
    assertThat(RequestContextHolder.getRequestAttributes()).isSameAs(attributes);

    try {
        // Run the test logic that requires the request context.
    } finally {
        RequestContextHolder.resetRequestAttributes();
        attributes.requestCompleted();
    }

    assertThat(RequestContextHolder.getRequestAttributes()).isNull();
    assertThatThrownBy(RequestContextHolder::currentRequestAttributes)
            .isInstanceOf(IllegalStateException.class);
}
```

Asserting after cleanup is a useful part of a test helper: it confirms that state was removed. If a test class uses `@AfterEach`, you can write a dedicated test for the helper or extension to verify that the cleanup policy works.

Do not inspect `RequestContextHolder` from a different thread and conclude that the binding thread was cleaned up. Different threads have separate ThreadLocals; verify on the exact thread that owned the binding.

## 13. Common Mistakes

### Binding Context Without `finally`

If an assertion or test code throws an exception before the reset line, the thread keeps the request attributes. Put the reset inside `finally` or use `try-with-resources`.

### Resetting Only in `@BeforeEach`

Resetting before a test lets the thread start clean, yet does not guarantee the current test cleans up state when it finishes. Use post-test cleanup or cleanup at the scope where the binding is created.

### Resetting on the Calling Thread Instead of the Worker Thread

ThreadLocal belongs to the current thread. Cleanup from the test thread does not remove a binding created inside an executor worker. Place `finally` inside the task itself.

### Using Inheritable Context with Thread Pools

Thread pools reuse workers and do not create a new child thread per task. Inheritance may fail to behave as expected or retain stale request references. Avoid enabling inheritable mode on shared executors; pass data explicitly or use controlled context propagation.

### Binding Unnecessarily in MockMvc Tests

MockMvc already runs through Spring MVC infrastructure. Binding extra attributes manually can cause tests to read the test-created context by mistake. Bind manually only when tests invoke components directly outside request dispatch.

### Assuming Resetting RequestContextHolder Resets Every Context

Security, locale, transactions, and MDC have their own lifecycles. Clean up each corresponding holder separately.

### Using Request Attributes After the Request Has Completed

Retaining `ServletRequestAttributes` inside a background task can cause code to access the request/session after the container has completed the request. Extract needed values into immutable objects before submitting the task.

## 14. Cleanup Strategy by Test Type

| Test type | Appropriate management approach |
|---|---|
| Unit test of a service reading request context directly | Create `MockHttpServletRequest`, bind `ServletRequestAttributes`, clean up in `finally`. |
| Multiple test methods binding context manually | Use an `AutoCloseable` helper or `@AfterEach`/JUnit extension. |
| Spring MVC `MockMvc` test | Let `DispatcherServlet` and Spring Test manage request binding; assert cleanup after dispatch if needed. |
| Tests running code on an executor | Bind and reset inside the same worker task; avoid retaining request attributes after the task finishes. |
| Async jobs outliving the request | Extract tenant/user/correlation into explicit data; do not keep `ServletRequestAttributes`. |
| Nested request scope tests | Save and restore the previous context intentionally, taking inheritable mode into account. |

## 15. Checklist for RequestContextHolder in Tests

- [ ] Determine whether the test actually needs manual `RequestAttributes` binding or Spring MVC already manages the request context.
- [ ] When binding manually, use `try/finally` or `AutoCloseable` for cleanup.
- [ ] Call `RequestContextHolder.resetRequestAttributes()` on the exact thread that performed the binding.
- [ ] Call `ServletRequestAttributes.requestCompleted()` when the test owns the attributes lifecycle and needs to finish request-scope callbacks.
- [ ] Include an assertion verifying `getRequestAttributes()` returns `null` after cleanup if no outer context exists.
- [ ] Use `@AfterEach` or a JUnit extension for shared cleanup; do not reset only in `@BeforeEach`.
- [ ] Do not use `InheritableThreadLocal` indiscriminately with thread pools.
- [ ] If tasks run on workers, clean up inside the worker task itself.
- [ ] Do not retain request/session objects in background tasks beyond the request lifecycle.
- [ ] Clean up `SecurityContextHolder`, `LocaleContextHolder`, or MDC separately if the test bound them.
- [ ] Do not manually clear transaction state owned by a transaction manager.

`RequestContextHolder` is safe only when bindings have clear boundaries and are reset on the right thread. Spring manages the request context automatically during standard Servlet dispatch; tests that bind manually must clean up in `finally` or lifecycle callbacks. Especially with executors and async processing, do not pass raw request attributes beyond the request's lifetime. Keep only the required data, pass it explicitly, and clear every thread-local before threads are reused.
