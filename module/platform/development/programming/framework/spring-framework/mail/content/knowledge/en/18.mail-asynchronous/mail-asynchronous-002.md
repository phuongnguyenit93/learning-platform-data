# When Offloading Mail Sending to Asynchronous Tasks

Sending emails over SMTP can take time because of DNS resolution, opening a connection, authentication, transferring the MIME message, and waiting for the mail server to respond. If all of this happens directly on the HTTP request-handling thread, users have to wait longer and requests may time out even after the core business logic has completed.

In Spring, you can offload mail sending to a task running on another thread using the **@Async** annotation. The main thread then records the send request and continues its work; an executor picks up the task and performs template rendering, MIME message creation, and calling **JavaMailSender** in the background.

However, being asynchronous only changes **when and on which thread execution occurs**. It does not automatically create a durable queue, does not guarantee tasks will not be lost when the application stops, does not automatically retry safely, and does not guarantee the email reached the Inbox. You must choose the right model according to your application's reliability requirements.

## 1. Why Offload Mail Sending from the Main Flow?

Suppose a user confirms an order. The application needs to update the order status and send a confirmation email.

If sent synchronously:

```text
HTTP request
    |
    v
Validate and confirm order
    |
    v
Create MIME message
    |
    v
Connect to SMTP and send email
    |
    v
Wait for SMTP response
    |
    v
Return HTTP response
```

The HTTP response time includes mail-sending time. If SMTP is slow, the request slows down too. Some consequences:

- Users have to wait even though the order data has already been saved.
- Gateways or browsers may time out and resend the request.
- The HTTP-handling thread is occupied while waiting on the network.
- A large mail burst can degrade the ability to serve other requests.
- SMTP errors can directly affect the business operation's response.

When offloading mail sending to an asynchronous task:

```text
HTTP request
    |
    v
Confirm order
    |
    v
Record mail send request
    |
    +-----------------------> Return HTTP response
    |
    v
Mail executor / worker
    |
    v
Render template
    |
    v
JavaMailSender.send(...)
    |
    v
Record outcome
```

The main thread can return a response early after recording the work. The worker performs mail sending independently.

### Suitable Use Cases

- Sending confirmation emails after a business operation has been recorded.
- Sending notifications that do not need the SMTP result immediately in the response.
- Sending reports or digests whose content generation takes a long time.
- Sending multiple emails after a business event.
- Sending emails with attachments that must be built from data or files.
- Reducing how long HTTP requests are held when SMTP responds slowly.

### When Should You Not Rely Only on @Async?

If the requirement is not to lose emails on application restart, to retry after failures, to handle backlogs, track status, and scale workers independently, an in-memory executor is usually not enough. In that case, store send requests in a database/outbox or a durable message broker and process them with workers.

## 2. Asynchronous Does Not Mean Faster Sending

@Async prevents the calling thread from waiting for the send operation to complete. It does not make SMTP transfer data any faster. Worker execution time still depends on:

- DNS and network connectivity.
- The SMTP server and authentication.
- Size of HTML, inline images, and attachments.
- Number of recipients.
- Provider rate limits.
- Template rendering or file reading time.

If the executor has too few threads or too small a queue, tasks may have to wait before starting. If there are too many threads, the application may open too many SMTP connections and exceed the provider's quota.

Therefore, the goal of async is **decoupling mail-sending wait time from the main flow and controlling load**, not eliminating send time.

## 3. How Does @Async Work in Spring?

Spring supports asynchronous method execution via the @Async annotation and a TaskExecutor. When a method is called through a Spring proxy, the proxy submits the call to the configured executor and returns control to the caller according to the method's return type.

To enable this feature, use @EnableAsync:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

A service can annotate a method:

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncMailService {

    @Async
    public void sendNotification(String recipient) {
        // Build message and send mail on an executor thread.
    }
}
```

When another bean calls this method through the Spring bean proxy, the method body executes on an executor thread. The caller does not have to wait for the void method to finish.

### @Async Is Proxy-Based

In the default proxy configuration, the call must pass through a Spring proxy. The following example usually does not run asynchronously:

```java
@Service
public class MailService {

    public void processOrder() {
        sendConfirmation(); // self-invocation
    }

    @Async
    public void sendConfirmation() {
        // Internal call within the same object.
    }
}
```

The internal call from processOrder() to sendConfirmation() does not go through the proxy, so the annotation may not be applied.

A clearer organization is to place the async task in a separate bean:

```java
@Service
public class OrderService {

    private final AsyncMailService asyncMailService;

    public OrderService(AsyncMailService asyncMailService) {
        this.asyncMailService = asyncMailService;
    }

    public void confirmOrder(Order order) {
        // Save and confirm business state.
        asyncMailService.sendConfirmation(order.getCustomerEmail());
    }
}

@Service
public class AsyncMailService {

    @Async("mailTaskExecutor")
    public void sendConfirmation(String recipient) {
        // Create and send email.
    }
}
```

Here, the call from OrderService to AsyncMailService goes through the async bean's proxy.

### Common Prerequisites

- @EnableAsync or equivalent async configuration is present.
- The method is called through a Spring proxy.
- The bean is managed by Spring.
- The method has visibility and signature compatible with the proxy mechanism in use.
- The executor is configured and still has capacity to accept tasks.

Do not assume that simply adding @Async to any method automatically runs it on another thread.

## 4. Configuring a Dedicated Executor for Mail Sending

If no executor is specified, Spring may use a default executor found in the application context or a fallback mechanism. For production applications, configure a dedicated executor for mail to control threads, queue capacity, and overload policies.

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailTaskExecutor")
    public Executor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );

        return executor;
    }
}
```

Then specify the executor name:

```java
@Async("mailTaskExecutor")
public void sendWelcomeEmail(String recipient) {
    // ...
}
```

The numbers in the example are only a starting point. Measure send times, email volume, SMTP quota, and server resources to tune them.

### Meaning of Configuration Settings

| Setting | Meaning |
| --- | --- |
| corePoolSize | Number of baseline threads maintained per configuration |
| maxPoolSize | Maximum thread limit when load increases |
| queueCapacity | Number of tasks that can wait in the queue |
| threadNamePrefix | Prefix to help identify mail threads in logs and thread dumps |
| waitForTasksToCompleteOnShutdown | Instructs the executor to wait for accepted tasks to finish on shutdown as configured |
| awaitTerminationSeconds | Maximum wait time during the shutdown phase |

With ThreadPoolTaskExecutor, when core threads are busy, tasks are usually placed in the queue first; only when the queue is full does the executor spawn additional threads up to max pool size. When both the queue and pool are full, the rejection policy is applied.

### Do Not Set an Unbounded Queue Arbitrarily

An unbounded queue can cause the application to keep accepting tasks while SMTP cannot keep up. Memory will grow steadily, wait times will lengthen, and the application may encounter OutOfMemoryError.

A bounded queue provides backpressure. When the queue is full, the application must have a clear policy:

- Reject new tasks and record the error.
- Route the request to a durable outbox/broker.
- Rate-limit notification creation.
- Use a policy that runs the task on the caller thread if blocking the caller is acceptable.

Do not use a silent discard policy for critical business emails, because tasks can be dropped without clear indication.

## 5. Policies When the Executor Is Overloaded

An executor cannot accept more tasks once both the thread pool and queue are full. Some rejection policies:

| Policy | Behavior | Impact |
| --- | --- | --- |
| Abort | Throws an exception when the task cannot be accepted | Caller knows enqueuing failed and can handle it |
| CallerRuns | The calling thread runs the task | Creates backpressure but can slow down requests |
| Discard | Drops the new task | Risks silently losing emails |
| DiscardOldest | Drops the oldest task in the queue and retries accepting the new one | Risks losing a waiting request |

For transactional emails, an explicit rejection policy or saving to an outbox is usually easier to control than silently dropping tasks.

Example Abort configuration:

```java
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy()
);
```

When rejected, the caller must handle the exception or record the request in a durable location. Do not catch the exception and ignore it.

### Is CallerRuns Appropriate?

CallerRuns can help slow down the producer because the calling thread must run the task itself. However, if the caller is an HTTP request thread, the request may end up waiting on SMTP again. This can be intentional backpressure, but timeouts and user experience must be evaluated.

If send requests must be preserved when the executor is overloaded, write to the notification/outbox table first; the executor is only a way to wake up workers or process batches.

## 6. Using CompletableFuture to Receive Asynchronous Results

Methods returning void fit when the caller does not need a direct result. If you want to observe the result or exception, you can use CompletableFuture.

Example:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncMailService {

    @Async("mailTaskExecutor")
    public CompletableFuture<String> sendReceipt(
            String recipient
    ) {
        // mailSender.send(message);
        return CompletableFuture.completedFuture(
                "SMTP submission completed for " + recipient
        );
    }
}
```

Spring executes the method on the executor and provides a future to the caller. When the method finishes, the future completes; if the method throws an exception, the future completes exceptionally.

The caller can register a callback:

```java
CompletableFuture<String> result =
        asyncMailService.sendReceipt(recipient);

result.whenComplete((value, error) -> {
    if (error != null) {
        // Log/correlate or update status appropriately.
        return;
    }

    // Handle the received result.
});
```

Do not call join() or get() immediately after calling an async method if the goal is to return an early response:

```java
// Negates the asynchronous benefit:
asyncMailService.sendReceipt(recipient).join();
```

This call makes the caller wait for the future to complete. Wait only when the business flow genuinely needs the result before continuing.

### CompletableFuture Is Not a Durable Queue

A future only represents the result of a computation in the current process. If the process is killed, futures and in-memory tasks can be lost. Do not use a future instead of a database/outbox when work must be recovered after a restart.

### Avoid Sharing a Pool for Heavy Callbacks

Callbacks such as thenApplyAsync or whenCompleteAsync may run on another executor depending on which overload is used. If a callback performs heavy I/O or CPU work, specify an appropriate executor so it does not starve the common pool or the mail executor.

## 7. Complete Example: Sending a Confirmation Email Asynchronously

Suppose the application has confirmed an order and needs to email the customer. The example uses:

- JavaMailSender to send via SMTP.
- MimeMessageHelper to create HTML and plain text.
- Thymeleaf to render the template.
- A dedicated executor named mailTaskExecutor.

### 7.1. Executor Configuration

```java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailTaskExecutor")
    public Executor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );
        return executor;
    }
}
```

Spring manages the lifecycle of the executor bean; in this configuration you do not need to manually call initialize() when the bean is initialized via Spring's normal lifecycle.

### 7.2. DTO Passed to the Worker

Do not pass a managed JPA entity to a background thread and access lazy relationships after the request's transaction ends. Prepare the necessary data as an immutable DTO:

```java
import java.util.Locale;

public record OrderConfirmationMail(
        String recipient,
        String customerName,
        String orderCode,
        String orderUrl,
        String totalAmountLabel,
        Locale locale
) {}
```

The DTO contains only the data the mail worker needs. This avoids depending on another thread's persistence context and makes it clear what data is used when sending.

### 7.3. Async Mail Service

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

@Service
public class AsyncOrderMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;

    public AsyncOrderMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine
    ) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
    }

    @Async("mailTaskExecutor")
    public CompletableFuture<Void> sendConfirmation(
            OrderConfirmationMail data
    ) throws MessagingException {
        Context context = new Context(data.locale());
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderCode", data.orderCode());
        context.setVariable("orderUrl", data.orderUrl());
        context.setVariable(
                "totalAmountLabel",
                data.totalAmountLabel()
        );

        String html = templateEngine.process(
                "mail/order-confirmation",
                context
        );

        String plain = "Hello " + data.customerName() + ".\n"
                + "Order " + data.orderCode()
                + " has been confirmed.\n"
                + "Total amount: " + data.totalAmountLabel() + "\n"
                + "View order: " + data.orderUrl();

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name()
        );
        helper.setFrom("notifications@example.org");
        helper.setTo(data.recipient());
        helper.setSubject(
                "Order confirmation " + data.orderCode()
        );
        helper.setText(plain, html);

        mailSender.send(message);
        return CompletableFuture.completedFuture(null);
    }
}
```

In this example, the method only completes the future after mailSender.send returns. This outcome indicates that the SMTP transport accepted the send operation as observed by the application; it does not prove the message reached the Inbox.

The sender address is an example and must be replaced with an address authorized by the provider. URL data must be generated by the backend from a trusted domain; template content uses th:text for text values.

### 7.4. Calling from the Business Service

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final AsyncOrderMailService asyncMailService;

    public OrderApplicationService(
            OrderRepository orderRepository,
            AsyncOrderMailService asyncMailService
    ) {
        this.orderRepository = orderRepository;
        this.asyncMailService = asyncMailService;
    }

    @Transactional
    public UUID confirmOrder(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();
        orderRepository.save(order);

        OrderConfirmationMail mailData =
                new OrderConfirmationMail(
                        order.getCustomerEmail(),
                        order.getCustomerName(),
                        order.getCode(),
                        buildOrderUrl(order.getId()),
                        formatAmount(order.getTotalAmount()),
                        Locale.forLanguageTag("vi-VN")
                );

        asyncMailService.sendConfirmation(mailData);
        return order.getId();
    }
}
```

This snippet illustrates how to build a DTO and call an async bean. However, there is an important transaction point: the async method may start running **before the caller's transaction commits**. If the worker needs to re-read newly written data, it may not see the changes or may read stale state.

In this example, the DTO already contains a snapshot of the data needed for rendering so the worker does not need to re-read the entity. Still, calling async before commit can still send a confirmation email for a transaction that later rolls back. The next section presents the proper way to handle cases where sending must be tied to the business commit.

## 8. Relationship Between @Async and @Transactional

@Transactional and @Async control two different aspects:

- @Transactional manages transactions for resources participating in a transaction manager, typically a database.
- @Async moves the method to an executor thread.

The caller's transaction thread **is not automatically propagated to the async thread**. The worker runs on a different thread and needs its own transaction if it must access the database.

Example:

```java
@Async("mailTaskExecutor")
@Transactional
public CompletableFuture<Void> sendAndRecord(
        MailNotification notification
) {
    // This transaction belongs to the worker thread.
}
```

If annotations are applied via proxies and the method is called properly, a transaction is opened in the worker according to the transaction manager configuration. It is not a continuation of the caller's transaction.

### Do Not Send Email Before Business Commit If Consistency Is Required

Consider the flow:

```text
Caller transaction
  update order
  call async mail
       |
       +---- worker may start sending
       |
  transaction rollback
       |
       v
Confirmation email may have already been sent
while the order was not confirmed
```

If an email must only be sent after the business transaction commits, a coordination mechanism is needed:

- Write the notification/outbox in the same transaction and have the worker read it after commit.
- Or use an event listener running after commit when losing events on a process crash is acceptable.

### @TransactionalEventListener(AFTER_COMMIT)

For lightweight tasks where durability limits are acceptable, you can publish an application event inside the transaction and handle it after commit:

```java
public record OrderConfirmedEvent(
        UUID orderId,
        String recipient,
        String customerName,
        String orderCode,
        String orderUrl
) {}
```

Publish the event:

```java
applicationEventPublisher.publishEvent(
        new OrderConfirmedEvent(
                order.getId(),
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getCode(),
                buildOrderUrl(order.getId())
        )
);
```

Listener:

```java
@Component
public class OrderMailListener {

    private final AsyncOrderMailService mailService;

    public OrderMailListener(AsyncOrderMailService mailService) {
        this.mailService = mailService;
    }

    @Async("mailTaskExecutor")
    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        OrderConfirmationMail data =
                new OrderConfirmationMail(
                        event.recipient(),
                        event.customerName(),
                        event.orderCode(),
                        event.orderUrl(),
                        null,
                        Locale.forLanguageTag("vi-VN")
                );
        mailService.sendConfirmation(data);
    }
}
```

This is an example illustrating the event mechanism. You also need to verify how annotations and proxies combine in your Spring configuration.

AFTER_COMMIT ensures the listener only runs after the transaction commits. However, application events normally reside in the process's memory. If the application dies after commit and before the listener runs, the notification can be lost. For critical emails, a transactional outbox is more reliable.

## 9. Transactional Outbox for Durable Mail Sending Tasks

If an email must not be lost when the application restarts, write the send request to the database in the same transaction as the business logic. A worker reads the outbox and sends it.

Flow:

```text
Business transaction
  |
  +-- update order
  +-- create PENDING mail_notification
  +-- create outbox row
  |
  v
COMMIT
  |
  v
Outbox worker / scheduler
  |
  v
Claim notification
  |
  v
Render and send via JavaMailSender
  |
  v
Record SUBMITTED / RETRY_WAIT / FAILED / UNKNOWN
```

Because the notification and business change commit together, the system avoids the case where an order is committed while the send request only exists in an async thread's memory.

### Example Outbox Write

```java
@Transactional
public UUID confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    UUID notificationId = UUID.randomUUID();
    MailPayload payload = MailPayload.from(order);

    mailNotificationRepository.insertPending(
            notificationId,
            "ORDER_CONFIRMED",
            order.getId().toString(),
            payload
    );

    outboxRepository.insert(
            UUID.randomUUID(),
            notificationId,
            "MAIL_NOTIFICATION_CREATED"
    );

    return notificationId;
}
```

This is an abbreviated example. A unique constraint per business event is needed so two calls to confirmOrder or two listeners do not create the same notification. If confirming an order is already idempotent, the order status and notification must be updated under the same rules.

### Outbox Does Not Guarantee Emails Are Sent Only Once

An outbox guarantees the send request is not lost when the business transaction commits. Workers typically process in an at-least-once model: an event may be re-read if a worker crashes or loses its acknowledgment. Therefore, the worker still needs a stable notification ID, a claim mechanism, and send-outcome handling.

Outbox solves atomicity between the database and work recording; it does not turn SMTP into an exactly-once system.

## 10. Passing Data to Async Threads

An async thread does not share the entire context of the HTTP thread. Do not pass objects that depend on an ended request or persistence context.

### Passing Immutable DTOs

Prepare the required values before calling async:

```java
public record WelcomeMailData(
        String recipient,
        String displayName,
        String activationUrl,
        Locale locale
) {}
```

Worker receives the DTO:

```java
@Async("mailTaskExecutor")
public CompletableFuture<Void> sendWelcome(WelcomeMailData data) {
    // Only use data in the DTO and thread-safe beans.
    return CompletableFuture.completedFuture(null);
}
```

This prevents the worker from needing to access:

- HttpServletRequest or request-scoped beans after the request ends.
- JPA entities with lazy relationships outside a persistence context.
- Mutable collections that the caller continues to modify.
- Closed streams or file handles.

### Do Not Pass JPA Entities to Workers for Lazy Loading

Error-prone example:

```java
@Async("mailTaskExecutor")
public void sendOrderMail(Order order) {
    String customerName = order.getCustomer().getName();
    // May fail with LazyInitializationException.
}
```

Load and normalize data inside the caller transaction, then pass a DTO. If the worker needs to query the database, it can call a service/repository in its own transaction using the necessary ID.

### Resources and Streams

If an email has attachments:

- Use resources with a clear lifecycle.
- Do not pass an InputStream that has been read or is about to be closed.
- You can store files in object storage and pass a storage key.
- Or read data into a byte array if the size is appropriate.
- Limit file sizes to avoid consuming too much heap in queues/tasks.

Do not share a single stream across multiple concurrent tasks.

## 11. Propagating SecurityContext, MDC, and Tracing Information

Some contexts do not automatically follow to a new thread:

- MDC containing correlation IDs.
- Spring Security's SecurityContext.
- Trace/span context of the observability framework.
- Application-managed locale or tenant context.

If worker logs need the correlation ID, you can use TaskDecorator to copy MDC:

```java
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

import java.util.Map;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> contextMap = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (contextMap != null) {
                    MDC.setContextMap(contextMap);
                } else {
                    MDC.clear();
                }
                task.run();
            } finally {
                if (previous != null) {
                    MDC.setContextMap(previous);
                } else {
                    MDC.clear();
                }
            }
        };
    }
}
```

Attach the decorator to the executor:

```java
executor.setTaskDecorator(new MdcTaskDecorator());
```

This is an example for MDC. For tracing, prefer context propagation integrations provided by the observability framework in use. For Spring Security, you can use DelegatingSecurityContextAsyncTaskExecutor when carrying SecurityContext to the worker is genuinely needed.

Do not manually copy transaction contexts across threads. Transaction resources are usually bound to threads and the transaction manager; workers should open their own transactions when needed.

### Should SecurityContext Be Passed to the Mail Worker?

Usually, the worker only needs the business data and tenant that were already authenticated/authorized when creating the notification. If the worker needs SecurityContext for a specific reason, use controlled propagation and avoid retaining credentials longer than necessary.

## 12. Handling Exceptions in @Async

Exceptions in a worker do not automatically propagate back to the caller's call stack like a synchronous method.

### Methods Returning void

```java
@Async("mailTaskExecutor")
public void sendNotice(String recipient) {
    mailSender.send(buildMessage(recipient));
}
```

The caller generally cannot catch exceptions occurring after the method has been dispatched. For void methods, you can configure AsyncUncaughtExceptionHandler to record errors:

```java
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;

import java.lang.reflect.Method;
import java.util.concurrent.Executor;

@Configuration
public class AsyncErrorConfiguration implements AsyncConfigurer {

    @Override
    public Executor getAsyncExecutor() {
        return mailTaskExecutor();
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, params) -> {
            // Log method, exception, and correlation ID.
        };
    }
}
```

This is an illustrative structure; if the application already declares multiple named executors, keep @Async("mailTaskExecutor") explicit and avoid accidentally creating another default executor.

The handler only helps observe exceptions. It does not automatically retry, persist failed notifications, or recover tasks after a restart.

### Methods Returning CompletableFuture

With a future, an exception is represented in its exceptional state:

```java
@Async("mailTaskExecutor")
public CompletableFuture<Void> sendNotice(String recipient) {
    mailSender.send(buildMessage(recipient));
    return CompletableFuture.completedFuture(null);
}
```

The caller can observe it:

```java
asyncMailService.sendNotice(recipient)
        .whenComplete((result, error) -> {
            if (error != null) {
                // Record error or transition state.
            }
        });
```

Do not let the callback only log and consider it handled if the business requires retries. A notification record or outbox is needed to know which tasks must be reprocessed.

## 13. Async Mail Sending and HTTP Responses

If an endpoint only needs to confirm that the send request has been recorded, it can return 202 Accepted:

```java
@PostMapping("/orders/{orderId}/send-confirmation")
public ResponseEntity<MailRequestReceipt> sendConfirmation(
        @PathVariable UUID orderId
) {
    MailRequestReceipt receipt =
            orderApplicationService.requestConfirmation(orderId);

    return ResponseEntity.accepted().body(receipt);
}
```

The response may contain:

```json
{
  "notificationId": "7f6b9c5e-...",
  "status": "PENDING"
}
```

This means the server has recorded the send request per the API contract. It does not mean the email was accepted by SMTP or reached the Inbox.

The client can use the notification ID to query status via a separate endpoint, after the server checks access permissions.

### Avoid Returning a Success Send Result Too Early

Do not return status SENT immediately after calling an @Async method. At that point, the worker may not have started yet, the queue may be full, or SMTP may fail. Use ACCEPTED/PENDING statuses to describe request acceptance.

## 14. Rate Limiting and Controlling Concurrent Emails

SMTP providers typically have quotas:

- Concurrent connections.
- Messages per second/minute.
- Recipients per message.
- Total daily sending volume.
- Message size limits.

If maxPoolSize is configured too high, many workers may connect to SMTP simultaneously and exceed limits. This can cause 4xx errors, throttling, or temporary account suspension.

Tune the executor according to:

1. Actual throughput of the SMTP/provider.
2. Average and percentile duration of a send operation.
3. Queue size.
4. Application CPU, memory, and connection resources.
5. Number of running instances.

If there are multiple instances, total workers equal the sum of pool sizes across all instances. For example, three instances with max pool size 8 each can create up to 24 concurrent send tasks.

### System-Wide Limits

A thread pool only limits concurrency within one instance. If system-wide or per-tenant limits are needed, you need a rate limiter/distributed coordination or appropriately configured broker consumer concurrency.

Do not just increase the thread pool to clear a backlog. If the provider is throttling, increasing concurrency can cause even more errors.

## 15. Monitoring Queues, Send Duration, and Outcomes

An async system must make waiting and running tasks observable.

Useful metrics:

| Metric | Meaning |
| --- | --- |
| Active threads | Number of threads currently executing |
| Pool size | Current number of threads |
| Queue size | Number of waiting tasks |
| Queue remaining capacity | Remaining capacity |
| Task rejection count | Number of tasks rejected by the executor |
| Mail submission duration | Time for send call to complete |
| Mail success/failure count | Number of accepted/failed submissions |
| Retry count | Number of retry attempts |
| Outbox lag | Delay from notification creation to processing |
| Unknown outcome count | Number of times SMTP outcome was undetermined |

Logs should include a notification ID or correlation ID:

```text
notificationId=N-123
template=order-confirmation/v2
executor=mailTaskExecutor
thread=mail-3
attempt=1
result=SUBMITTED
```

Do not log full email contents, passwords, tokens, or unnecessary personal data.

### Thread Name Prefixes Help Investigation

When a thread is named mail-3, thread dumps and logs show the work belongs to the mail executor. This is a small but helpful detail when an application has multiple executors for different background tasks.

## 16. Application Shutdown and Deployment

When an application shuts down, an executor can:

- Stop accepting new tasks.
- Wait for running tasks to complete.
- Wait for queued tasks according to configuration.
- Cancel or reject remaining tasks when shutdown time expires.

waitForTasksToCompleteOnShutdown and awaitTerminationSeconds help handle orderly shutdown when the process is allowed to shut down normally. However, they do not guarantee tasks survive when:

- The server powers off abruptly.
- The container is killed before the grace period expires.
- The process crashes.
- The OOM killer stops the JVM.
- The orchestrator force-stops after timeout.

Tasks residing only in executor memory can be lost in these situations. If emails must still be sent after a restart, persist requests in an outbox or durable broker.

### Setting an Appropriate Graceful Shutdown Duration

Shutdown wait time should correlate with:

- SMTP connect/read/write timeouts.
- Attachment sizes.
- Rendering time.
- Number of running tasks.
- Container/orchestrator grace period.

If a task can hang longer than the shutdown duration, network timeouts and a clear recovery policy are needed. Do not rely on waiting indefinitely.

## 17. Retries for Async Tasks

A failed @Async method is not automatically re-queued into the executor. Retrying requires a separate mechanism.

### In-Memory Retry

You can re-invoke a method or use a retry framework, but tasks and state still depend on the current process. On restart, in-memory retry schedules can be lost.

### Notification/Outbox-Based Retry

For business emails, a more durable approach:

1. Write the notification with a stable ID.
2. Worker claims the notification.
3. Send via SMTP.
4. Classify the error.
5. If it is a known transient error, record RETRY_WAIT and next_attempt_at.
6. Worker picks it up again when due.
7. If the outcome is unknown, record UNKNOWN and reconcile.

SMTP may have accepted the message while the response was lost. Do not blindly retry every timeout because that can cause duplicates. If the provider offers an idempotency API, use a stable key per notification according to the provider's contract.

### Backoff and Attempt Limits

Example retry schedule:

```text
Attempt 1: initial send
Attempt 2: after 30 seconds
Attempt 3: after 2 minutes
Attempt 4: after 10 minutes
Attempt 5: after 30 minutes
```

The specific schedule depends on the provider and email type. Add jitter, attempt limits, and a dead-letter/review flow. Authentication errors, broken templates, or invalid recipients usually require fixing configuration/data rather than continuous retries.

## 18. Distinguishing Task Status from Email Status

An async task may have finished calling SMTP, yet the email is not guaranteed to have been delivered to the mailbox.

| Status | Meaning |
| --- | --- |
| PENDING | Request has been recorded |
| QUEUED | Waiting for executor/worker |
| PROCESSING | Worker is processing |
| SUBMITTED | SMTP/provider accepted the message |
| DELIVERED | Provider has evidence of delivery to the receiving system, if event support is available |
| BOUNCED | Provider received bounce information |
| RETRY_WAIT | Waiting for the next attempt |
| FAILED | Final failure per policy |
| UNKNOWN | Unable to determine whether SMTP/provider received it |

Do not transition status to DELIVERED just because JavaMailSender.send() did not throw an exception. SMTP acceptance and delivery are two distinct events.

If using only @Async without database records, task status typically exists only via futures or logs. For APIs that need to display progress to users, persist notification statuses durably.

## 19. Testing Asynchronous Tasks

Tests should verify that the method actually runs through the executor, the message is constructed properly, and errors are observable.

### 19.1. Unit Testing Message Construction

Separate rendering/message-building logic from sending logic to verify:

- Correct subject.
- Correct recipient.
- Plain text and HTML have corresponding content.
- Appropriate charset.
- Correct CID/attachments if present.
- Dynamic data is escaped in templates.

### 19.2. Integration Testing with a Mock SMTP Server

You can use GreenMail, Mailpit, or MailHog to receive emails in test environments. Verify the actual message sent to the SMTP test server:

```java
@Test
void asyncMailIsSubmitted() throws Exception {
    // Arrange:
    // - Start the SMTP test server.
    // - Configure JavaMailSender to point to that server.
    // - Call asyncMailService and keep the CompletableFuture.

    // Act:
    // - Wait for the future to complete with a bounded timeout.

    // Assert:
    // - The SMTP test server received exactly one message.
    // - Recipient and subject are correct.
    // - Both text/plain and text/html are present.
}
```

This is a test skeleton; exact configuration depends on the project's GreenMail or SMTP test server version.

### 19.3. Verifying Asynchrony

You can check the thread name or use a latch/future to confirm work runs on the executor. Do not use Thread.sleep(...) arbitrarily because tests become flaky and slow.

Conceptual example:

```java
CompletableFuture<Void> future =
        asyncMailService.sendConfirmation(data);

assertThat(future).isNotNull();
future.get(5, TimeUnit.SECONDS);
```

In real tests, timeouts must fit the environment and the message must be checked on the SMTP test server. Checking only that the future completed is not enough to prove the MIME message is correct.

### 19.4. Testing Overload

With an executor having a small queue, you can test:

- Tasks are accepted when capacity remains.
- Tasks are rejected when both pool and queue are full.
- Rejections are logged/written to the outbox or return an appropriate error.
- No tasks are silently discarded.

There is no need to test every thread pool setting with mock tests; focus on policies and behavior when the system hits limits.

### 19.5. Testing Shutdown and Recovery

If using an outbox, verify the worker can resume PENDING notifications after an application restart. With a pure in-memory executor, understand that unstarted tasks can be lost on process stop; tests should not claim durability that the architecture does not provide.

## 20. Common Pitfalls When Using @Async

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Method still runs synchronously | Self-invocation or async not enabled | Call through bean proxy and configure @EnableAsync |
| Caller cannot catch exception | Method returns void and error occurs in worker | Use future or AsyncUncaughtExceptionHandler |
| Emails lost after deployment | Tasks lived only in executor memory | Use durable outbox/broker |
| Queue grows continuously | Slow SMTP or executor too small | Measure throughput, limit load, and scale workers appropriately |
| HTTP request stays slow | Caller calls get()/join() or CallerRuns runs the task | Do not wait on future unnecessarily; review rejection policy |
| LazyInitializationException | Passed JPA entity to background thread | Pass DTO or ID and query in worker transaction |
| Worker does not see newly saved data | Task ran before transaction commit | Use outbox or controlled post-commit processing |
| Email sent despite transaction rollback | Async started before commit | Write outbox in the same transaction |
| Logs missing correlation ID | MDC not propagated | Use TaskDecorator or tracing integration |
| SecurityContext lost | New thread lacks caller context | Pass needed data or use appropriate delegate executor |
| SMTP throttled | Too many concurrent send tasks | Limit concurrency/rate per provider |
| Tasks dropped when queue is full | Discard rejection policy | Use explicit rejection or outbox |
| Shutdown loses tasks | Process stopped before executor finished | Graceful shutdown and persistence for critical tasks |
| Retries send duplicates | Ambiguous timeout blindly retried | UNKNOWN state, reconciliation, and provider idempotency if available |
| Two instances run the same job | Scheduler runs on every instance | Use atomic claim/leader coordination/broker |

## 21. When to Choose @Async vs. a Message Broker?

Not every task needs Kafka, RabbitMQ, or a dedicated queue system. Choose based on requirements.

| Criterion | @Async + executor | Database outbox/worker | Message broker |
| --- | --- | --- | --- |
| Implementation | Simple, lives in the application | Needs tables and worker | Needs broker and consumers |
| Waiting tasks in memory | Yes | No, stored in database | No, stored in broker |
| Recovery after restart | Not guaranteed for incomplete tasks | Can re-read from database | Per broker durability/config |
| Retry | Custom-designed | Store attempts and retry schedule | Broker/consumer policy combined with state |
| Independent worker scaling | Limited within the same app | Can run separate workers | Good, consumers scale independently |
| Backpressure | Thread pool/queue | Database backlog and claiming | Broker lag/consumer concurrency |
| Business status tracking | Must persist separately | Natural via notification table | Needs combination with business state |
| Suitable for | Lightweight background tasks where loss on stop is acceptable | Transactional emails needing durability | High volume or multiple consuming systems |

### Choose @Async When

- Emails do not have high durability requirements.
- The application is small and only needs to free HTTP threads.
- Losing incomplete tasks on a process crash is acceptable.
- Error observability and executor bounds are in place.

### Choose Outbox When

- Emails are tightly tied to business transactions.
- Send requests must not be lost after database commit.
- Retries, auditing, and status tracking are needed.
- You want to avoid relying on in-memory-only events.

### Choose a Broker When

- Notification volume is high or there are multiple consumers.
- Independent scaling is required.
- Message broker infrastructure already exists.
- Routing, partitioning, or buffering across multiple services is needed.

You can combine them: the transaction writes to the outbox, a publisher forwards events to the broker, and a consumer sends mail with JavaMailSender.

## 22. Example Worker Structure with Outbox and Executor

A design can use a scheduler to read a batch from the outbox and dispatch each notification to a mail executor:

```java
@Component
public class MailOutboxDispatcher {

    private final MailNotificationRepository repository;
    private final AsyncNotificationProcessor processor;

    public MailOutboxDispatcher(
            MailNotificationRepository repository,
            AsyncNotificationProcessor processor
    ) {
        this.repository = repository;
        this.processor = processor;
    }

    @Scheduled(fixedDelayString = "1000")
    public void dispatch() {
        List<ClaimedNotification> batch =
                repository.claimNextBatch(20);

        for (ClaimedNotification item : batch) {
            processor.process(item);
        }
    }
}
```

Processor:

```java
@Service
public class AsyncNotificationProcessor {

    private final MailNotificationRepository repository;
    private final JavaMailSender mailSender;

    public AsyncNotificationProcessor(
            MailNotificationRepository repository,
            JavaMailSender mailSender
    ) {
        this.repository = repository;
        this.mailSender = mailSender;
    }

    @Async("mailTaskExecutor")
    public CompletableFuture<Void> process(
            ClaimedNotification item
    ) {
        try {
            MimeMessage message = buildMessage(item);
            mailSender.send(message);
            repository.markSubmitted(
                    item.notificationId(),
                    item.claimToken()
            );
            return CompletableFuture.completedFuture(null);
        } catch (MailException ex) {
            repository.recordFailure(
                    item.notificationId(),
                    item.claimToken(),
                    classify(ex)
            );
            return CompletableFuture.failedFuture(ex);
        } catch (MessagingException ex) {
            repository.markFailed(
                    item.notificationId(),
                    item.claimToken(),
                    "MIME message construction failed"
            );
            return CompletableFuture.failedFuture(ex);
        }
    }
}
```

This is an architectural example; appropriate transaction boundaries and claim implementation must be added. Do not call repository.markSubmitted in the same long transaction that covers SMTP. Status-updating methods should be short transactions that verify the claim token so an old worker cannot overwrite a newer worker's result.

Also, if the dispatcher claims 20 rows and the executor can only accept 5 tasks because the queue is full, the remaining 15 rows must not be stranded. Claiming/dispatching must be designed around capacity or have a lease-release mechanism when tasks are not accepted. One option is to have workers directly fetch a batch matching available slots rather than claiming more than the executor can handle.

## 23. Practical Design Principles

1. **Use a dedicated executor for mail.** Avoid letting slow SMTP stall unrelated background tasks.
2. **Bound pools and queues.** Choose values according to throughput and provider quotas.
3. **Never silently discard.** On overload, know that tasks were rejected and have a recovery path.
4. **Pass immutable DTOs.** Do not pass request objects, open streams, or JPA entities needing lazy loading.
5. **Do not assume transactions propagate to workers.** Workers need their own transactions when querying/updating the database.
6. **Send only after business commit.** Use an outbox when notifications must not be lost.
7. **Handle exceptions in workers.** Futures/handlers provide observability; persistence enables retries.
8. **Set network timeouts.** Avoid tasks holding threads indefinitely when SMTP hangs.
9. **Monitor queues and send durations.** Use metrics, notification IDs, and correlation IDs.
10. **Distinguish accepted from delivered.** SMTP acceptance does not prove Inbox delivery.
11. **Design stateful retries.** A timeout outcome may be UNKNOWN; do not retry blindly.
12. **Keep graceful shutdown.** Yet use an outbox/broker for durability across crashes.

## 24. Practice Scenarios

### Scenario A: HTTP response still waits despite @Async on the method

**Troubleshooting approach:** check whether the caller calls future.get() or join(); check for self-invocation; check whether the executor uses CallerRunsPolicy on overload. Verify the call passes through a Spring proxy.

### Scenario B: Order rolls back but confirmation email was already sent

**Troubleshooting approach:** the async worker started before the caller's transaction committed. Write the notification/outbox in the same transaction and only let the worker process it after commit.

### Scenario C: Worker encounters LazyInitializationException

**Troubleshooting approach:** do not pass entities for the worker to access lazy relations. Build a DTO inside the caller transaction or pass the ID and query in a separate worker transaction.

### Scenario D: Emails are lost after deployment

**Troubleshooting approach:** check whether tasks only lived in executor memory or were persisted durably. If tasks are lost when the process stops, switch to an outbox/broker and build a recovery mechanism.

### Scenario E: Queue grows continuously

**Troubleshooting approach:** measure send duration and task arrival/completion rates; check for SMTP throttling; tune concurrency/rate; bound the queue; consider scaling workers or provider capacity.

### Scenario F: Caller does not receive SMTP exceptions

**Troubleshooting approach:** if the method returns void, configure AsyncUncaughtExceptionHandler; if result observation is needed, use CompletableFuture. For business emails, record failures in notification state for retry/reconciliation.

### Scenario G: SMTP times out and it is unknown whether the email was received

**Troubleshooting approach:** mark as UNKNOWN, look up provider events/message ID if available, and apply reconciliation. Do not assume every timeout definitely means unsent.

### Scenario H: Application has three instances, each with a pool max of 10 threads

**Troubleshooting approach:** total concurrency can reach 30 concurrent send tasks. Calculate the total across the entire system and limit according to SMTP quota, not just a single instance's pool.

## 25. Conclusion

Offloading mail sending to asynchronous tasks prevents HTTP threads from waiting on SMTP completion and lets the application control concurrent sending tasks. In Spring, @EnableAsync, @Async, and TaskExecutor are the core building blocks; CompletableFuture helps callers observe results and exceptions when needed. A dedicated executor, bounded queue, clear rejection policy, and network timeouts keep tasks under control.

For business-tied emails, pay attention to transaction commit timing, data passed to new threads, exceptions, retries, and shutdown. @Async only executes tasks within the current process; it does not guarantee task survival across crashes. A transactional outbox or broker is more suitable when send requests must be stored durably and recovered. Distinguish between a recorded request, SMTP acceptance, and email delivery. Choosing the right model gives the application better responsiveness along with clear tracking and handling for mail-sending failures.
