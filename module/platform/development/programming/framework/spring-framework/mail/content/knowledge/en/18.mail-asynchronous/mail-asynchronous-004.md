# @Async and the Proxy Boundary of Asynchronous Calls

When a Spring application confirms an order, the HTTP-handling layer should generally not have to wait for the entire time needed to connect to SMTP, send the content, and receive a response from the mail server. Spring provides the `@Async` annotation to request executing a method on a thread managed by a `TaskExecutor`, rather than continuing directly on the calling thread.

However, **`@Async` is not simply slapping an annotation onto a method and having every call run in the background automatically**. Under Spring's default mechanism, `@Async` relies on a **Spring AOP proxy**: the call must pass **through Spring's proxy object** to be intercepted and handed off to an executor. If a method in the same object calls a method annotated with `@Async` on itself, the call usually goes straight to `this`, bypassing the proxy and running synchronously.

This is especially important in **Spring Framework Mail**, because `JavaMailSender.send(...)` is inherently an SMTP send operation that can block a thread while connecting or exchanging data. When `@Async` is used properly, the caller can return early, yet **the SMTP send work remains a blocking operation on the executor thread**. The annotation does not turn SMTP into a non-blocking protocol, nor does it provide a durable queue or guarantee the email eventually reaches the inbox.

This lesson explains `@EnableAsync`, proxy boundaries, self-invocation, executors, return types, error handling, transactions, cross-thread context, and controllable asynchronous email-sending designs.

## 1. Where Do Synchronous and Asynchronous Differ?

A synchronous mail-sending flow might proceed as follows:

~~~text
HTTP request
  → Controller
  → OrderApplicationService
  → JavaMailSender.send(...)
  → SMTP server responds
  → Controller returns response
~~~

In this flow, the request thread may have to wait until `send(...)` finishes or throws an error. Wait time is affected by network connectivity, TLS, authentication, SMTP relay speed, and message size.

When offloading the send step to an executor:

~~~text
HTTP request thread
  → Controller
  → OrderApplicationService
  → call MailWorker proxy
  → work is handed to executor
  → Controller can return response

Executor thread
  → MailWorker.send(...)
  → JavaMailSender.send(...)
  → SMTP relay
~~~

**Asynchrony here changes the execution thread and when the caller regains control**; it does not change the nature of SMTP.

Key distinctions:

| Aspect | Synchronous sending | Sending with `@Async` |
| --- | --- | --- |
| Thread executing `JavaMailSender.send` | Calling thread | Executor thread |
| Caller waits for the entire send operation | Usually yes | Not necessarily |
| Seeing exceptions on direct call | Can catch immediately in caller | Depends on return type and how future is observed |
| Work survives application crash | Not guaranteed by itself | Also not guaranteed by itself |
| Does SMTP become non-blocking | No | No |
| Needs load and error management | Yes | Even more so due to added executor and queue |

With an `@Async` `void` method, the caller usually only knows the work was scheduled successfully. With a method returning `CompletableFuture`, the caller can observe completion or failure through the future. Both differ from the SMTP relay confirming delivery to the recipient's mailbox.

## 2. The Role of the Spring AOP Proxy

When async support is enabled, Spring can create a proxy wrapping a bean that has methods annotated with `@Async`. The proxy acts as an intermediary:

~~~mermaid
flowchart LR
    A["Another bean / Controller"] --> B["Spring proxy of MailWorker"]
    B --> C["Async interceptor"]
    C --> D["TaskExecutor"]
    D --> E["Actual MailWorker"]
    E --> F["JavaMailSender.send"]
~~~

When a method is invoked through the proxy, the interceptor resolves the executor, creates or dispatches the task, and lets an executor thread invoke the actual method.

An overview flow:

1. Spring initializes the bean and applies the async infrastructure.
2. Another bean receives a reference to the proxied bean.
3. The caller invokes the `@Async`-annotated method through that reference.
4. The interceptor submits the task to the appropriate executor.
5. An executor thread runs the method body.
6. The result/error is returned or published according to the return-type contract.

**Core requirement:** the call must pass through the proxy. Having the annotation in source code alone is not enough if the object is instantiated with `new` or called internally via `this`.

### Distinguishing the Real Bean from the Proxy Bean

Suppose:

~~~java
@Service
public class MailWorker {

    @Async
    public void sendNotice() {
        // Mail-sending work.
    }
}
~~~

The object Spring injects into another bean can be a proxy. Inside `MailWorker`, however, the `this` keyword still refers to the instance currently executing the method; calling itself does not go through the proxy.

Proxying does not mean Spring rewrites bytecode at every call site to that method. Under the default `AdviceMode.PROXY` mode, Spring primarily intercepts calls entering through the proxy.

## 3. Enabling @Async with @EnableAsync

In a Spring application, declare the configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Or place `@EnableAsync` on an appropriate configuration class in the application.

Simply adding `spring-boot-starter-mail` does not mean `@Async` methods are enabled. `@EnableAsync` activates the infrastructure to process async annotations.

Example bean:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class MailWorker {

    @Async
    public void sendNotice() {
        System.out.println(
                "Mail-sending thread: "
                        + Thread.currentThread().getName()
        );
    }
}
~~~

If the bean is called **through the proxy** from another bean, the method can run on an executor thread. If called directly from the bean itself or created with `new MailWorker()`, the annotation does not automatically produce background execution.

### The Default Executor Is Not Automatically Optimal for Production

When `@Async` does not specify an executor, Spring must locate an appropriate executor in the context. Executor selection rules depend on Spring configuration, available `TaskExecutor` beans, conventional bean names, and Spring Boot auto-configuration. If no suitable executor exists, the framework has fallback behavior; do not assume the application definitely has a thread pool bounded the way you want.

In a production mail-sending flow, create a dedicated executor or configure the used executor explicitly, controlling thread count, queue size, timeouts, shutdown, and overload behavior.

## 4. The Proxy Boundary: External Calls vs. Self-Invocation

This is the most common source of confusion.

### 4.1. Calls from Another Bean — Normally Intercepted by the Proxy

~~~java
@Service
public class OrderNotificationService {

    private final MailWorker mailWorker;

    public OrderNotificationService(MailWorker mailWorker) {
        this.mailWorker = mailWorker;
    }

    public void requestMail(OrderMailCommand command) {
        // mailWorker is a Spring-injected bean.
        mailWorker.sendOrderConfirmation(command);
    }
}
~~~

If `MailWorker.sendOrderConfirmation` is annotated with `@Async`, async infrastructure is enabled, and Spring injects the appropriate proxy, this call goes through the proxy and is dispatched to the executor.

### 4.2. Self-Calls Within the Same Bean — Usually NOT Asynchronous

Example with mistaken expectations:

~~~java
@Service
public class OrderService {

    public void confirmOrder(OrderMailCommand command) {
        // Process order ...

        sendEmail(command);
    }

    @Async
    public void sendEmail(OrderMailCommand command) {
        // JavaMailSender.send(...).
    }
}
~~~

`confirmOrder` calls `sendEmail` on the same instance. At execution time, that is equivalent to `this.sendEmail(command)`, not a call going through the proxy.

The typical result is:

- `sendEmail` runs on the current thread.
- `confirmOrder` still has to wait on SMTP.
- `@Async` does not produce the expected asynchronous effect.
- Error handling may also behave differently from expectations because the async interceptor was bypassed.

This is the **self-invocation** phenomenon.

~~~mermaid
flowchart TD
    A["Caller"] --> B["OrderService proxy"]
    B --> C["confirmOrder on target"]
    C --> D["this.sendEmail"]
    D --> E["Target method runs directly"]
    E --> F["Bypasses async interceptor"]
~~~

Even if a controller calls `confirmOrder` through a proxy, **the call inside `confirmOrder` to `sendEmail` is still an internal call**. A proxy only intercepts external entry points corresponding to advised methods; it does not intercept every method-to-method call within the target object.

## 5. How to Fix Self-Invocation: Extract the Worker Bean

The clearest fix is to move the async method to another bean:

~~~java
@Service
public class OrderService {

    private final MailWorker mailWorker;

    public OrderService(MailWorker mailWorker) {
        this.mailWorker = mailWorker;
    }

    public void confirmOrder(OrderMailCommand command) {
        // Update order / validate business logic.
        mailWorker.sendOrderConfirmation(command);
    }
}
~~~

~~~java
@Service
public class MailWorker {

    @Async("mailExecutor")
    public CompletableFuture<Void> sendOrderConfirmation(
            OrderMailCommand command) {

        // Build MIME message and send via SMTP.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Now `OrderService` calls another Spring bean through an injected reference. `MailWorker`'s proxy has the opportunity to intercept the call and hand the work to `mailExecutor`.

Advantages:

- The sync → async boundary is explicit in the class structure.
- The application service and mail worker can be tested separately.
- `MailWorker` is solely responsible for the delegated task.
- Easy to configure executor, timeouts, logging, retry policy, and metrics for mail.
- Avoids hard-to-follow workarounds such as fetching the bean's own proxy from the application context.

### Self-Injection of a Bean into Itself Is Discouraged

Some examples use self-injection or `AopContext.currentProxy()` to call back through the proxy. Those techniques can depend on proxy configuration, make code harder to understand, or introduce dependency cycle issues. If architecture permits, **splitting into a separate bean** is the more maintainable choice.

### Special Case: AspectJ Weaving

`@EnableAsync` supports the default `PROXY` mode and can be configured to `ASPECTJ` when weaving and corresponding dependencies are integrated. Weaving can apply advice to internal calls differently from proxies. However, that is a distinct build and runtime mechanism; do not switch to AspectJ just to avoid separating a mail-sending bean.

## 6. Which Methods Should Carry @Async?

In standard Spring proxy-based designs, annotate **public non-final methods** on Spring-managed beans.

~~~java
@Service
public class MailWorker {

    @Async("mailExecutor")
    public CompletableFuture<Void> send(OrderMailCommand command) {
        // ...
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Cases that easily cause confusion:

| Situation | What to remember |
| --- | --- |
| Method called via Spring bean proxy | Can be handled by the async interceptor |
| Called via `this.method()` | Bypasses proxy in proxy mode |
| Object created with `new` | Not a Spring-managed proxy |
| `private` method | Not a normal proxy interception entry point |
| `final` method when using class-based proxy | Cannot be overridden to intercept via subclass proxy |
| `final` class when class-based proxy is needed | Cannot generate subclass proxy |
| Called inside constructor or `@PostConstruct` | Do not expect the async proxy to be active yet at that point |
| Method not exposed by JDK interface proxy | Caller cannot access that method through the corresponding interface proxy |

Spring AOP can create a **JDK dynamic proxy** for interfaces or a **class-based proxy** under certain configurations. Interception capability depends on proxy type, visibility, and how the method is invoked. For mail workers, using a public non-final method and injecting via an appropriate interface/bean is the simplest choice.

### Annotations on Interfaces vs. Implementations

You may encounter projects placing `@Async` on an interface or on an implementation. Annotation detection and proxy application can depend on proxy/weaving mode; when wanting clear behavior in a specific application service, annotate the Spring-managed implementation method and verify the proxy configuration in use.

Do not treat a call on an arbitrary Java object as an AOP-intercepted call. Dependency injection and the Spring bean lifecycle are part of the `@Async` usage contract.

## 7. Configuring a Dedicated mailExecutor

Sending over SMTP is blocking I/O work. Sharing an executor with other tasks such as report generation, image resizing, or CPU-heavy jobs allows one group of tasks to consume all threads and impact the rest.

You can create a dedicated `ThreadPoolTaskExecutor` for mail sending:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);

        executor.initialize();
        return executor;
    }
}
~~~

The numbers `4`, `8`, `100`, and `20` are only examples to explain the configuration; suitable values must be based on traffic, SMTP latency, provider limits, and application memory.

Using the named executor:

~~~java
@Async("mailExecutor")
public CompletableFuture<Void> sendOrderConfirmation(
        OrderMailCommand command) {
    // ...
}
~~~

The name `"mailExecutor"` in `@Async` must resolve to the corresponding executor in the Spring context.

### 7.1. Understanding ThreadPoolTaskExecutor's Load-Growth Order

For a thread pool with a bounded-capacity queue, general behavior is:

1. Create threads up to `corePoolSize` when work arrives.
2. When core threads are busy, tasks are normally placed in the queue.
3. When the queue is full and thread count has not reached `maxPoolSize`, the pool can create additional threads.
4. When both pool and queue reach their limits, the executor applies the rejection policy.

Therefore, increasing `maxPoolSize` does not guarantee the pool will expand to that limit before the queue fills. This detail is frequently misunderstood when configuring large queues.

### 7.2. Rejection Is Not an SMTP Failure

If the queue is full, a task can be rejected **right when the caller attempts to schedule it**, before the `@Async` method body ever executes. The caller must handle this situation separately from errors occurring inside the executor thread.

Spring may represent rejection with `TaskRejectedException` or an exception related to the executor and rejection policy. Do not assume every `@Async` call is accepted and will run.

### 7.3. Do Not Use CallerRunsPolicy Mindlessly

The `CallerRunsPolicy` policy can cause a rejected task to execute directly on the calling thread instead of in the pool. This is a form of backpressure, but **it can cause the request thread to run SMTP synchronously**, contrary to latency expectations.

If the goal is fast requests and bounded load, you need an explicit saturation strategy: controlled rejection, durable job recording, returning an appropriate status, or intentionally accepting backpressure. Do not mask this mechanism by simply making the queue unbounded.

## 8. Complete Example: Spring Mail with @Async at the Right Boundary

Suppose an application wants to send an order confirmation email. We separate:

- `OrderNotificationService`: receives the business request, determines the recipient, and creates a content snapshot.
- `AsyncMailWorker`: another Spring bean containing the `@Async` method.
- `JavaMailSender`: performs blocking SMTP inside the worker thread.
- `mailExecutor`: manages worker threads and the queue.

### 8.1. Spring Mail Dependency

In Spring Boot with Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

`@EnableAsync`, `@Async`, and `ThreadPoolTaskExecutor` belong to the relevant Spring framework modules that a typical Spring Boot application already provides. There is no need to add a separate async mail library just to use `@Async`.

### 8.2. Immutable Input Data

~~~java
public record OrderMailCommand(
        String recipient,
        String customerName,
        String orderCode) {
}
~~~

This is the data snapshot the worker uses to send the email. Values must be verified before placing them in the command: recipient belongs to the rightful addressee, orderCode comes from an authoritative domain source, and customerName conforms to business rules. Do not store a mutable JPA entity or HTTP request object in the command for later use by a background thread.

### 8.3. Async Mail Worker

~~~java
import java.util.concurrent.CompletableFuture;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncMailWorker {

    private final JavaMailSender mailSender;

    public AsyncMailWorker(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public CompletableFuture<Void> sendOrderConfirmation(
            OrderMailCommand command) {

        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");

            helper.setFrom("orders@example.org");
            helper.setTo(command.recipient());
            helper.setSubject(
                    "Order " + command.orderCode()
                    + " has been confirmed"
            );

            String body = """
                    Hello %s,

                    Order %s has been confirmed.
                    Thank you for using our service.
                    """.formatted(
                    command.customerName(),
                    command.orderCode()
            );

            helper.setText(body);
            mailSender.send(message);

            // Completion value from body; the proxy manages
            // the CompletableFuture received by the caller.
            return CompletableFuture.completedFuture(null);

        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Unable to prepare MIME message", ex
            );
        }
    }
}
~~~

This example sends `text/plain` to stay focused on the async boundary. For HTML alongside plain text, use the helper in multipart mode and `setText(plainText, htmlText)`. When using HTML, escape dynamic data according to context or use a template engine with appropriate escaping.

`JavaMailSender.send(message)` can throw an unchecked `MailException`; that exception occurs on the worker thread and must be observed through the future or an appropriate error-reporting mechanism.

### 8.4. Application Service Calling Through the Proxy

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.stereotype.Service;

@Service
public class OrderNotificationService {

    private final AsyncMailWorker mailWorker;

    public OrderNotificationService(AsyncMailWorker mailWorker) {
        this.mailWorker = mailWorker;
    }

    public CompletableFuture<Void> notifyConfirmedOrder(
            String verifiedRecipient,
            String customerName,
            String orderCode) {

        OrderMailCommand command = new OrderMailCommand(
                verifiedRecipient,
                customerName,
                orderCode
        );

        // Calling another bean: the call goes through the proxy.
        return mailWorker.sendOrderConfirmation(command);
    }
}
~~~

`OrderNotificationService` does not call an `@Async` method on the same instance. The `AsyncMailWorker` bean is injected by Spring and proxied per configuration. That makes the handoff boundary to the executor clear.

In production code, the application service should load and verify data from the domain/repository, applying authorization/recipient policies before creating the command. Do not treat a parameter named `verifiedRecipient` as proof that validation already occurred.

### 8.5. Caller Observing the Future

~~~java
CompletableFuture<Void> future =
        orderNotificationService.notifyConfirmedOrder(
                recipient,
                customerName,
                orderCode
        );

future.whenComplete((ignored, error) -> {
    if (error != null) {
        // Record error with request ID, do not log credentials
        // or full email content.
        reportMailFailure(error);
    }
});
~~~

`whenComplete` does not force the caller to wait, yet allows observing the result later. Depending on timing, the callback may run on the thread completing the future or the thread registering the callback if the future is already complete; do not assume the callback always runs on the request thread.

For tasks needing durable tracking guarantees, an in-process future is insufficient. When the application restarts, in-process futures and queues are not automatically recovered.

## 9. Return Types of @Async Methods

Spring supports specific return types for async methods, most commonly:

- `void`: the caller receives no future to track completion.
- `Future<T>`: the caller can wait and retrieve the result.
- `CompletableFuture<T>`: the caller can attach callbacks and handle errors in completion-stage style.

Examples:

~~~java
@Async("mailExecutor")
public void sendNotice(NoticeCommand command) {
    // Send mail; caller has no future to observe.
}
~~~

~~~java
@Async("mailExecutor")
public CompletableFuture<String> sendWithReference(
        NoticeCommand command) {

    String providerReference = sendAndGetReference(command);
    return CompletableFuture.completedFuture(providerReference);
}
~~~

An `@Async` method declared to return `String` directly does not match the return-type contract of Spring's async interceptor:

~~~java
// Unsuitable for Spring @Async:
@Async("mailExecutor")
public String sendMail(NoticeCommand command) {
    return "sent";
}
~~~

Choose `CompletableFuture<Void>` when no value is needed but completion or failure status is required.

### 9.1. Why Does the Body Return completedFuture Right After Sending?

In the worker example, `JavaMailSender.send` runs on the executor thread. After sending finishes, the method returns `CompletableFuture.completedFuture(null)`. That is an **interim result from the method body** to satisfy the signature. The future received by the caller is the future created/managed by Spring's async infrastructure to reflect background task execution.

There is no need to manually call `CompletableFuture.runAsync(...)` inside a method already annotated with `@Async` just to introduce another thread pool. Nesting two mechanisms makes it harder to determine the executor, trace errors, and control saturation.

### 9.2. What Does a Completed Future Mean?

If the worker completes normally after `mailSender.send`, the future generally signifies **the application-level send operation completed**. It does not prove the email was delivered to the inbox or opened by the recipient.

Many SMTP relays only confirm they accepted the message for further processing. Bounces or delivery failures can occur afterward. You need provider callbacks, bounce handling, or a delivery tracking system if the product needs to know actual delivery status.

## 10. Exceptions with @Async: Callers Cannot Catch Them Like Synchronous Calls

A misleading example:

~~~java
try {
    mailWorker.sendOrderConfirmation(command);
} catch (MailException ex) {
    // Not the place to catch SMTP errors that occur later
    // inside the executor thread.
}
~~~

If the call was handed off to an executor, exceptions from `JavaMailSender.send` occur later on a worker thread. A `try/catch` around the scheduling call does not automatically catch asynchronous errors.

Distinguish two groups:

| Error group | Timing | How to observe |
| --- | --- | --- |
| Scheduling / executor rejection error | While the caller submits the task | Can surface immediately at the caller |
| Runtime error inside async method | On the worker thread | Exceptional future completion, handler, or job status record |
| Temporary SMTP send error | When the worker calls `send` | Handle via future/job and retry policy |
| Bounce after relay accepted | After initial SMTP response | Separate provider feedback/bounce processing |

### 10.1. Returning CompletableFuture

~~~java
CompletableFuture<Void> future =
        mailWorker.sendOrderConfirmation(command);

future.exceptionally(error -> {
    recordFailure(command.orderCode(), error);
    return null;
});
~~~

This is how to observe a future's error within the same process. Do not ignore the future in flows where send failures must be detected.

If you call `join()` or `get()` right inside the controller to wait for completion, the caller waits for the result and forfeits the latency benefit of asynchrony. Waiting intentionally can fit some use cases, but that trade-off must be understood.

### 10.2. Returning void

With `@Async void`, the caller has no future. Spring provides `AsyncUncaughtExceptionHandler` to handle uncaught exceptions from `void` methods. If unconfigured, the framework may use a default handler to log exceptions.

You can configure an appropriate handler via `AsyncConfigurer`:

~~~java
@Configuration
@EnableAsync
public class AsyncErrorConfiguration
        implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
    getAsyncUncaughtExceptionHandler() {

        return (error, method, params) -> {
            // Controlled logging/metrics;
            // avoid dumping params containing tokens or PII.
            recordAsyncFailure(method.getName(), error);
        };
    }
}
~~~

`recordAsyncFailure` is an illustrative application-implemented function. This handler does not turn a task into a durable job, does not replace retries, and does not return the exception as a response to an already-completed HTTP request.

If mail failures must be tracked explicitly, using `CompletableFuture` or a durable job record is usually easier to design than relying solely on `void` logging.

## 11. @Async Does Not Inherit the Caller's Transaction

Another thread does not automatically carry the request thread's transaction. Example:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    orderRepository.markConfirmed(orderId);
    mailWorker.sendOrderConfirmation(createCommand(orderId));
}
~~~

If `mailWorker` is called through an async proxy, the executor can start running **before `confirmOrder`'s transaction commits**. Consequently:

- The worker may read stale state if it queries the database again.
- The uncommitted order may not yet be visible to another transaction.
- The caller may roll back after dispatching the task, yet the email may still have been sent.
- A success notification email may be sent for an operation that ultimately rolled back.

This is a **transaction boundary and side-effect timing bug**, not just a threading bug.

~~~mermaid
sequenceDiagram
    participant C as Application service
    participant DB as Database
    participant E as Async executor
    participant S as SMTP
    C->>DB: Update order in transaction
    C->>E: Schedule mail
    E->>S: May send before commit
    C-->>DB: Commit or rollback later
~~~

### 11.1. @Transactional on the Worker Does Not “Carry Over the Transaction”

You can place `@Transactional` on a method invoked via proxy on a worker thread to **create a separate transaction at the execution site**, depending on Spring configuration and advice ordering. However, that is not the same transaction open on the request thread.

Avoid keeping a database transaction open throughout blocking SMTP calls when unnecessary. It is usually better to read required data into a snapshot, close the transaction, and send mail outside any transaction.

### 11.2. After Commit and Outbox

If sending must only happen after a transaction succeeds, you can structure the flow around post-commit events. For instance, Spring supports `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` for listeners triggered once a transaction has committed. This can be combined with async processing under proper configuration, yet an after-commit listener only changes processing timing and **does not guarantee job survival if the process dies**.

When notifications must not be dropped, the **transactional outbox** pattern is usually more suitable:

1. In the same transaction as the business change, save an outbox record.
2. Commit the database.
3. A worker reads committed outbox records.
4. Resolve needed data, render, and send.
5. Update status, retry per policy, and avoid duplicates where possible.

Outboxes also face “at least once” delivery concerns and require idempotency; do not claim an outbox guarantees absolute exactly-once SMTP sending.

## 12. Thread Context: SecurityContext, MDC, and Request Data

Spring and many libraries use `ThreadLocal` to store thread-bound context, for example:

- Security context of the authenticated user.
- MDC/trace ID for logging.
- Request attributes.
- Transaction context.
- Locale or other thread-bound information.

When switching from a request thread to an executor thread, **never assume all thread-local context travels along automatically**.

Example potential bug:

~~~java
@Async("mailExecutor")
public void sendNotice(UUID orderId) {
    Authentication auth =
            SecurityContextHolder.getContext()
                    .getAuthentication();

    // auth may be missing or not the expected context.
}
~~~

Similarly, reading `RequestContextHolder.currentRequestAttributes()` inside a background worker can fail because the HTTP request has ended.

### 12.1. Passing Required Data via Commands

A straightforward approach is passing resolved data before dispatching:

~~~java
public record MailJobCommand(
        UUID orderId,
        UUID requestedBy,
        UUID recipientContactId,
        Locale locale,
        String correlationId) {
}
~~~

The application service checks permissions and gathers necessary data before delegating work. If the worker needs to re-verify permissions or recipient policies at send time, it can load data via authoritative IDs instead of relying on a SecurityContext attached to the request thread.

Do not put passwords, session tokens, or entire principals into commands just to “preserve context”.

### 12.2. When Intentional Propagation Is Needed

Spring Security provides executor wrappers such as `DelegatingSecurityContextAsyncTaskExecutor` to propagate security context under explicit configuration. Logging can use `TaskDecorator` or observability integrations to carry metadata such as correlation IDs.

Propagation must be an intentional decision considering privacy, context lifetime, and thread reuse risks. Do not assume every `ThreadLocal` is safe to copy to workers.

### 12.3. Do Not Read Request Data After Dispatch

A `MultipartFile`, `HttpServletRequest`, input stream, or persistence-context-attached entity may no longer be valid once the request completes. For emails with attachments, save the file to managed storage before dispatching, verify permissions, and pass a file ID/storage key that can be resolved later.

## 13. Immutable Data Boundaries Between Threads

Because caller and worker run at different times, objects crossing the async boundary should have clear contracts and minimize mutable state.

Suboptimal example:

~~~java
public void requestMail(MutableOrderDto dto) {
    mailWorker.send(dto);
    dto.setRecipient("another@example.org");
}
~~~

If the worker starts after the caller mutates the object, content/recipient may differ from when sending was requested. This is a race condition caused by sharing mutable objects.

Use an immutable snapshot:

~~~java
public record MailSnapshot(
        String recipient,
        String subject,
        String plainText,
        String html) {
}
~~~

~~~java
MailSnapshot snapshot = new MailSnapshot(
        approvedRecipient,
        subject,
        plainText,
        html
);

mailWorker.send(snapshot);
~~~

If a record contains a `List` or mutable object, make a defensive copy:

~~~java
public record BulkMailCommand(
        List<String> recipientAddresses,
        String messageCode) {

    public BulkMailCommand {
        recipientAddresses = List.copyOf(recipientAddresses);
    }
}
~~~

`List.copyOf` creates an unmodifiable list through that reference, though it does not make element objects immutable if they hold mutable state. Prefer value objects/IDs for data crossing async boundaries.

## 14. Transactions and Email Sending Belong to Two Different Systems

Some developers mistakenly believe adding `@Transactional` to a mail service makes SMTP roll back alongside the database. That is not true for standard SMTP.

Database transactions manage changes inside the database. Calling `JavaMailSender.send(...)` is a side effect to an SMTP relay and does not participate in a database transaction in a way that can roll back with the database.

For example, if the SMTP relay already accepted the mail and the DB transaction later rolls back, the system cannot automatically “recall” the mail via rollback.

Therefore, you must decide:

- Which emails are merely best-effort notifications?
- Which emails must be tied to committed state?
- Which emails need durable retries and auditing?
- Which emails must not be duplicated or need deduplication?
- At what point in time must displayed data be snapshotted?

`@Async` only solves handing work off to an executor thread. **It does not replace consistency design between the database and the mail system.**

## 15. Operational Limitations of @Async

### 15.1. In-Memory Queues

`ThreadPoolTaskExecutor` uses a thread pool and queue inside the JVM process. When the application is killed, the host restarts, or a new version deploys, pending work is not guaranteed to be preserved or replayed. Graceful shutdown settings can wait for some tasks during normal shutdowns, but cannot guarantee survival across power loss or crashes.

If critical notifications must be recoverable, persisted jobs/outboxes or a message broker are required as designed.

### 15.2. Producer Speed vs. SMTP Provider Speed

HTTP requests can generate work faster than the SMTP relay can process it. Queues can grow, send latency can stretch, or the executor can reject tasks. Avoid merely increasing thread count to “speed up” when a provider enforces quotas/throttling; that can increase transient errors and system load.

Set concurrency limits, queue capacities, rate limits, and retries with backoff.

### 15.3. SMTP Timeouts

If a worker hangs for a long time while connecting or writing data, the thread pool can become exhausted. Configure mail transport timeouts:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

The illustrative hostname must be replaced with a real SMTP relay. Environment variables must be managed with proper secret handling; never commit credentials to source code. Timeouts are example values (milliseconds) and must match network characteristics and provider behavior.

### 15.4. Monitoring Status

You should measure:

- Active task count and executor queue size.
- Accepted/rejected task counts.
- Queue wait time.
- MIME preparation duration and SMTP duration.
- Mail send success/failure counts by type.
- Transient/permanent error types and retry counts.
- Time from business event to relay acceptance of the send request.

Do not log SMTP passwords, email tokens, full message contents, or personal data solely for debugging.

## 16. When Is @Async Enough, and When Is a Queue/Outbox Needed?

| Requirement | `@Async` with executor | Durable queue/outbox |
| --- | --- | --- |
| Want HTTP to return faster than SMTP | Suitable | Suitable, though more complex |
| Low mail volume, losing a few notifications on crash is acceptable | Usually sufficient | May be overkill |
| Need job recovery after restart | Not guaranteed automatically | Designed to meet this |
| Need scheduled retries, backoff, and audit | Must implement separately | Easier to organize with persisted state |
| Need status tracking by request ID | In-process future or auxiliary system | Explicit job record |
| Need duplicate prevention across redelivery | Not guaranteed automatically | Still requires idempotency design |
| Need to cap SMTP load | Executor + rate limiting | Worker concurrency + queue controls |

**There is no single right solution for every system.** For low-stakes notifications at low volume, `@Async` may be enough. For important transaction confirmations, invoices, tracked notifications, or operational obligations, a persisted outbox/job is usually worth considering.

An outbox flow can still use `@Async` internally to increase worker concurrency, but in that case the outbox is the durable source of state. Do not confuse these two roles.

## 17. What HTTP Status Should a Controller Return When Sending Asynchronously?

When a controller calls an application service and the service hands the task to an executor, the response should accurately express the level of guarantee.

Controller example:

~~~java
@PostMapping("/orders/{id}/email-confirmation")
public ResponseEntity<Void> requestMail(
        @PathVariable UUID id,
        @AuthenticationPrincipal AppPrincipal principal) {

    notificationService.requestConfirmation(
            id,
            principal.userId()
    );

    return ResponseEntity.accepted().build();
}
~~~

HTTP `202 Accepted` can be appropriate to state **the request has been accepted for processing**, not that the email was successfully delivered to the inbox.

However:

- If calling only `@Async` with an in-memory queue, “accepted” does not mean a persisted job.
- If the executor rejects immediately upon submission, the controller should not still return 202 as if the job were accepted.
- If policy rejects the recipient or the actor lacks permission, return an appropriate business error response.
- If clients need to look up status later, provide a request/job ID and an endpoint reading status from storage.
- If using a transaction/outbox, the point of returning 202 must align with successful commit.

Do not call `future.join()` right before returning the response if the goal is not waiting on SMTP. When the application genuinely needs send confirmation at HTTP response time, consider a synchronous call or a different API contract.

## 18. Testing the Proxy Boundary Properly

Email functionality can be tested at three different levels.

### 18.1. Unit Testing the Method Body

Instantiate `AsyncMailWorker` via its regular constructor and call the method:

~~~java
AsyncMailWorker worker = new AsyncMailWorker(fakeMailSender);
worker.sendOrderConfirmation(command);
~~~

This test can verify MIME-building logic, but **does not verify `@Async` is working**. An object created with `new` does not go through a Spring proxy.

### 18.2. Spring Integration Test Checking Thread Boundaries

A test running with a Spring context and `@EnableAsync` can inject the proxied async bean. Use a dedicated executor in the test environment or a synchronization primitive like `CountDownLatch` to observe the thread.

Example body of a bean for testing:

~~~java
@Service
public class AsyncProbe {

    @Async("mailExecutor")
    public CompletableFuture<String> threadName() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
        );
    }
}
~~~

Test injecting the Spring bean:

~~~java
@Autowired
AsyncProbe asyncProbe;

@Test
void runsOnExecutorThread() {
    String thread = asyncProbe.threadName().join();

    assertTrue(thread.startsWith("mail-worker-"));
}
~~~

This example assumes the test executor uses the `mail-worker-` prefix. In a test suite with multiple executors, configure the test context to explicitly control which bean is selected. Checking thread names is only illustrative; synchronization/latches can provide stronger verification when confirming non-blocking behavior.

### 18.3. Testing Self-Invocation

You can create a method making an internal call and measure the thread or completion timing to demonstrate self-invocation bypasses the proxy in default mode.

Example:

~~~java
@Service
public class SelfInvocationExample {

    public String callInternally() {
        return annotatedMethod();
    }

    @Async("mailExecutor")
    public CompletableFuture<String> annotatedMethod() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
        );
    }
}
~~~

The example above illustrates a `CompletableFuture` return type, though `callInternally` must handle the future rather than returning a string directly; a valid version:

~~~java
public CompletableFuture<String> callInternally() {
    return annotatedMethod(); // Bypasses proxy on self-call.
}
~~~

When testing, compare calling `callInternally()` versus calling `annotatedMethod()` through the bean proxy and observe the threads. The goal is recognizing **the call path**, not just seeing an annotation in source code.

### 18.4. Testing SMTP Without Sending Real Emails

Separate proxy-boundary testing from SMTP testing. You can use a fake `JavaMailSender`, an SMTP test server, or an appropriate test mail transport to verify MIME, subject, recipients, and error handling. Never let integration tests accidentally send emails to production addresses.

## 19. Common Misconceptions

### 19.1. “Just adding @Async guarantees the method always runs in the background”

False in proxy mode. The method must be called through Spring's proxy. Self-invocation and objects created with `new` bypass that mechanism.

### 19.2. “Calling an @Async method from another method in the same class works fine”

Usually not. Internal calls use `this`, bypassing the proxy. Extract the async worker into a separate bean so calls are intercepted.

### 19.3. “Putting @Async on a private method still works”

Private methods are not valid entry points for standard proxy interception. Use public non-final methods on Spring-managed beans.

### 19.4. “Having Spring Boot mail starter enables @Async automatically”

Do not assume that. Async support must be enabled with `@EnableAsync` in appropriate configuration.

### 19.5. “@Async makes SMTP sending non-blocking”

No. `JavaMailSender.send` still blocks on the executor thread. It only avoids blocking the calling thread once the task is dispatched.

### 19.6. “Future completed means the recipient received the email”

No. It only reflects the application/SMTP relay operation outcome at that point; final delivery can happen later.

### 19.7. “A try/catch around an @Async call catches later SMTP errors”

No. Errors on the executor thread do not unwind back to the synchronous call stack. Observe `CompletableFuture` or job status; handle submission rejections separately.

### 19.8. “@Transactional from the controller carries over to the worker thread”

No. Transaction contexts do not automatically move across threads. Workers can run before commit and read stale data or send before the caller rolls back.

### 19.9. “SecurityContext and RequestContextHolder are always present in the worker”

No. Thread-local contexts do not propagate automatically. Use explicit command data or intentionally configured propagation.

### 19.10. “A large executor queue means the system handles load better”

Not necessarily. Large queues can increase wait times and hold many objects in memory while the SMTP provider remains the bottleneck.

### 19.11. “@Async provides a durable queue”

No. Typical executor queues live in-process. Crashes or restarts can lose unprocessed work.

### 19.12. “Calling an @Async method in @PostConstruct is a reliable way to start background work”

Not recommended. Bean initialization and proxy application follow specific lifecycle ordering; self-calls during initialization are not valid proxy paths. If background work must start once the app is ready, use an appropriate lifecycle hook/event and another Spring bean called through its proxy.

### 19.13. “Setting a huge maxPoolSize solves saturation”

No. With positive queue capacity, the pool may wait for the queue to fill before expanding beyond core size. Understand the queue model, provider limits, timeouts, and backpressure.

## 20. Practice Scenarios

**Scenario A — Order confirmed inside a transaction**

The service executes:

~~~java
@Transactional
public void confirm(UUID id) {
    orderRepository.confirm(id);
    mailWorker.sendOrderConfirmation(createCommand(id));
}
~~~

What can go wrong?

The worker can run before commit and send based on state not yet durably confirmed. If the transaction rolls back, the email may have already been sent. For critical requirements, use an after-commit event or an outbox with proper semantics.

**Scenario B — @Async inside the same class**

~~~java
public void createAndNotify() {
    notifyAsync();
}

@Async("mailExecutor")
public void notifyAsync() {
    // ...
}
~~~

Why might the call run synchronously?

Because it is self-invocation, going through `this` instead of the proxy. Move `notifyAsync` to a worker bean and inject the worker into the service.

**Scenario C — Calling via new**

~~~java
MailWorker worker = new MailWorker(mailSender);
worker.sendOrderConfirmation(command);
~~~

Does `@Async` work automatically?

Not under Spring proxy mode, because this object is not Spring-managed and is not a proxy.

**Scenario D — Executor is overloaded**

If the queue is full and the executor rejects, may the caller unconditionally return 202?

No. Rejection must be handled and an appropriate HTTP response/job status chosen; do not report the work was accepted if it actually was not.

**Scenario E — Controller needs to report results immediately**

The controller calls `future.join()` before returning the response. Is that still non-blocking for the request?

No. The request thread waits for the future to complete. That can be an intentional choice, yet it forfeits the latency benefit of offloading SMTP to a worker.

**Scenario F — Method returns void**

If SMTP throws an exception on the worker thread, where can it be observed?

Not in a standard `try/catch` at the caller. You can use `AsyncUncaughtExceptionHandler` and logging/metrics; if structured tracking is needed, choose `CompletableFuture` or persisted jobs.

**Scenario G — Worker needs user ID**

Should it read `SecurityContextHolder` inside the worker or pass the ID in the command?

It is usually better to pass an ID and metadata already resolved/authorized at the application boundary, then re-check when necessary. Do not assume request-thread context traveled with the executor.

**Scenario H — Attached image from request**

The controller passes `MultipartFile` directly to the worker and returns HTTP 202. What is the risk?

Uploaded data may depend on request lifecycle or closed streams. Validate it, save it to managed storage, and pass a file ID for the worker to read later; do not hold references to request-scoped resources.

**Scenario I — SMTP provider limits message rate**

Should the pool be raised to 100 threads to send faster?

Not by default. If the provider enforces rate limits, more threads can trigger throttling/rejections. Proper rate limiting, concurrency control, and retries are required.

**Scenario J — Application restarts with 500 emails still in the queue**

Does `@Async` automatically resume sending the 500 emails after restart?

No. With standard executors, the queue is memory-only. Recovery requires persisted jobs, an outbox, or a message broker by design.

## 21. Boundary Model to Remember

~~~mermaid
flowchart TD
    A["HTTP / Event / Scheduler"] --> B["Application service"]
    B --> C["Validate permissions, recipient, data"]
    C --> D["Snapshot command"]
    D --> E["Spring bean proxy"]
    E --> F["Async interceptor"]
    F --> G["mailExecutor"]
    G --> H["AsyncMailWorker"]
    H --> I["JavaMailSender.send (blocking)"]
    I --> J["SMTP relay"]
    E -. "Future / scheduling result" .-> B
~~~

Core principles:

1. **`@Async` in Spring proxy mode requires calls through the proxy.** The annotation has no effect on self-invocation or objects instantiated with `new`.
2. **Separate the worker into its own Spring bean**, called from the application service via dependency injection so the async boundary is clear.
3. **Use `@EnableAsync` and a bounded executor**, preferring a dedicated executor for mail when load management is needed.
4. **SMTP remains blocking on the worker thread**; handle timeouts, saturation, and rate limits.
5. **Choose the right return type**: `void` for fire-and-forget with separate error handling, `CompletableFuture` to observe completion/failure.
6. **Distinguish scheduling errors from runtime errors**; worker exceptions are not automatically caught by the caller.
7. **Transactions, SecurityContext, MDC, and request data do not cross threads automatically**; explicitly design snapshots, propagation, and commit timing.
8. **Do not use `@Async` as a durable queue**; for critical recovery/retry/audit needs, use persisted jobs or an outbox.
9. **Test through a Spring context** when verifying the proxy is actually applied; calling `new` instances only tests the method body.
10. **Do not equate “SMTP accepted” with “delivered”**; futures and send results only reflect status at their respective layers.

In a Spring Framework Mail application, let the application service decide **what email to send, to whom, and after which business state**, then pass a well-defined data command to `AsyncMailWorker` through the Spring proxy. `@Async` and `TaskExecutor` move the work to a worker thread; `JavaMailSender` performs SMTP; and the job/outbox mechanism plus monitoring govern recovery, tracking, and retries in production.
