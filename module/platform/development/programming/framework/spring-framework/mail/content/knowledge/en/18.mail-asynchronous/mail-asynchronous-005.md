# Do Not Self-Invoke @Async Methods Within the Same Bean

In Spring Framework Mail, sending an email is an I/O operation: the application must build MIME content, connect to an SMTP server or mail service, transmit data, and wait for a transport response. Doing all of this on the HTTP request-handling thread can noticeably increase response times when SMTP is slow or the network has issues. Spring supports **@Async** to hand a method call off to a **TaskExecutor**, so the calling thread does not have to wait for the entire mail-sending operation.

However, there is a very common bug: **one method in a bean directly calls another method annotated with @Async in the same bean**. Even though the method is annotated with @Async, this internal call typically still **runs synchronously on the current thread** because it does not go through the Spring AOP proxy.

This lesson explains the cause of self-invocation, how to fix it by extracting the mail-sending task into a separate bean, how to configure an executor and verify the method truly runs asynchronously, along with notes on transactions, exceptions, ThreadLocal, and reliability when sending emails.

## 1. The Problem: @Async Is Present Yet Mail Sending Still Blocks Requests

Suppose an account registration service both saves a user and sends a welcome email:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final UserRepository userRepository;
    private final JavaMailSender mailSender;

    public RegistrationService(
            UserRepository userRepository,
            JavaMailSender mailSender
    ) {
        this.userRepository = userRepository;
        this.mailSender = mailSender;
    }

    public void register(RegisterCommand command) {
        User user = userRepository.save(User.from(command));

        // Calling another method on the current object itself.
        sendWelcomeEmailAsync(user.getEmail());
    }

    @Async("mailExecutor")
    public void sendWelcomeEmailAsync(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("welcome@example.test");
        message.setTo(recipient);
        message.setSubject("Welcome");
        message.setText("Your account has been created.");
        mailSender.send(message);
    }
}
~~~

Corresponding mail imports:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
~~~

At first glance, **sendWelcomeEmailAsync(...)** has @Async, and the application may already have an executor configured properly. Yet the line:

~~~java
sendWelcomeEmailAsync(user.getEmail());
~~~

is a call from one method to another method on the **same instance**. It is equivalent to:

~~~java
this.sendWelcomeEmailAsync(user.getEmail());
~~~

In Spring's default proxy mode, this call **is not intercepted by a Spring proxy to be handed to the executor**. As a result, **mailSender.send(...) runs right on the thread executing register(...)**. If SMTP takes three seconds to respond, the current thread may be blocked for nearly three seconds.

### Signs to Recognize

Common signs of a self-invocation bug:

- The method has @Async, yet requests still wait until email sending finishes.
- Logs inside the mail-sending method show the same thread name as the calling method.
- SMTP exceptions surface directly on the calling thread instead of being handled by the async mechanism.
- The executor is configured, yet no corresponding tasks appear to be submitted.
- Calling the @Async method from **another bean** behaves as expected.

This is not a bug in JavaMailSender or SMTP. The cause lies in **the method call path through the Spring AOP proxy**.

## 2. How Does Spring @Async Work?

With **annotation-driven asynchronous execution** in proxy mode, Spring creates a proxy around beans that have methods eligible for @Async. When another component calls the method through the proxy:

1. The proxy receives the call.
2. The @Async interceptor resolves which executor to use.
3. The task is submitted to the executor.
4. A worker thread executes the actual method.
5. The calling thread returns according to the async method's contract without waiting for the task to finish.

Diagram of a call through the proxy:

~~~text
Controller / Service A
         |
         | call mailDispatchService.sendAsync(...)
         v
    Spring AOP proxy
         |
         | @Async interceptor
         v
      TaskExecutor
         |
         | submit task
         v
    Worker thread
         |
         v
    Target MailDispatchService
         |
         v
      JavaMailSender
         |
         v
       SMTP
~~~

The object another bean receives via dependency injection is usually a **proxy**, not necessarily the direct target instance. The proxy creates the interception point for Spring to apply @Async behavior.

### Why Does Self-Invocation Bypass the Proxy?

When a Spring proxy invokes the target method of a bean, inside that method, **this** points to the object executing the bean's logic. A call to another method on **this** is not a new external call passing through the proxy.

~~~text
Service A
    |
    v
Spring proxy of RegistrationService
    |
    v
RegistrationService.register(...)
    |
    | this.sendWelcomeEmailAsync(...)
    v
RegistrationService.sendWelcomeEmailAsync(...)
    |
    v
JavaMailSender.send(...)

No second pass through the @Async interceptor.
~~~

Key point: **@Async does not alter the nature of a Java method**. The annotation is metadata for Spring's infrastructure to apply an interceptor when a call passes through the appropriate mechanism. Bypassing the proxy means the annotation does not spawn a new thread.

### Does Every Method with @Async Run on Another Thread?

No. Appropriate conditions must all hold simultaneously:

- The bean is managed by Spring.
- @Async processing infrastructure is enabled.
- The method has a compatible signature and can be intercepted by the proxy.
- The call passes through the proxy (in default proxy mode).
- The executor accepts the task.

If any of these conditions is missing, actual behavior may differ from expectations.

## 3. Checking Threads to See the Bug Occur

Thread names help illustrate the call path, though they are not the only criterion to prove asynchrony.

~~~java
public void register(RegisterCommand command) {
    log.info(
            "register thread={}",
            Thread.currentThread().getName()
    );

    sendWelcomeEmailAsync(command.email());
}

@Async("mailExecutor")
public void sendWelcomeEmailAsync(String recipient) {
    log.info(
            "sendWelcomeEmailAsync thread={}",
            Thread.currentThread().getName()
    );
    // Send mail...
}
~~~

When self-invocation bypasses the proxy, logs may look like:

~~~text
register thread=http-nio-8080-exec-3
sendWelcomeEmailAsync thread=http-nio-8080-exec-3
~~~

When the call passes through the proxy and the executor processes it:

~~~text
register thread=http-nio-8080-exec-3
sendWelcomeEmailAsync thread=mail-1
~~~

Specific thread names depend on the web server, executor, thread factory configuration, and runtime environment. Do not write business logic depending on thread name strings. Tests should verify completion signals, executor invocations, or non-blocking behavior rather than requiring a fixed thread name string.

## 4. Preferred Fix: Extract the Mail Sender into Another Bean

To avoid self-invocation, split the responsibilities of **account registration** and **asynchronous email sending** into two Spring beans. The registration bean calls the Spring-injected mail-sending bean; the call passes through the mail bean's proxy.

### Bean Performing Email Sending

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncWelcomeMailService {

    private final JavaMailSender mailSender;

    public AsyncWelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public void sendWelcomeEmail(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("welcome@example.test");
        message.setTo(recipient);
        message.setSubject("Welcome");
        message.setText("Your account has been created.");

        mailSender.send(message);
    }
}
~~~

### Bean Invoking the Async Task

~~~java
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final UserRepository userRepository;
    private final AsyncWelcomeMailService asyncWelcomeMailService;

    public RegistrationService(
            UserRepository userRepository,
            AsyncWelcomeMailService asyncWelcomeMailService
    ) {
        this.userRepository = userRepository;
        this.asyncWelcomeMailService = asyncWelcomeMailService;
    }

    public void register(RegisterCommand command) {
        User user = userRepository.save(User.from(command));

        // Call passes through the injected Spring bean.
        asyncWelcomeMailService.sendWelcomeEmail(user.getEmail());
    }
}
~~~

Flow after splitting:

~~~text
RegistrationService.register()
         |
         v
AsyncWelcomeMailService proxy
         |
         v
@Async interceptor
         |
         v
mailExecutor.submit(...)
         |
         v
Worker thread calls JavaMailSender
~~~

This is an easy-to-understand and maintainable design: the business service does not handle SMTP directly, while the mail service can receive test mocks and its own executor.

### Why Is Splitting Beans Useful Beyond @Async?

- **Separation of concerns:** registration business logic does not depend on how MIME messages are constructed.
- **Easier testing:** AsyncWelcomeMailService can be mocked when testing registration; mail sending is tested in a separate layer.
- **Easier monitoring:** mail tasks have their own executor and logging.
- **Easier replacement:** you can switch from direct SMTP to a queue/outbox with minimal impact on business services.
- **Avoids dependency cycles:** no need to self-inject or ask ApplicationContext for your own proxy.

**Important note:** this example only fixes the self-invocation problem. If the registration method runs inside a database transaction and the email must only be sent after commit, you must add an **AFTER_COMMIT** boundary, explained later. Splitting beans and using @Async **does not automatically guarantee the transaction committed before the email is sent**.

## 5. Enabling @Async and Explicitly Configuring an Executor

To use @Async in an annotation-driven way, the application must enable asynchronous execution infrastructure. In Spring Java configuration, use **@EnableAsync**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.initialize();
        return executor;
    }
}
~~~

When a method has:

~~~java
@Async("mailExecutor")
public void sendWelcomeEmail(String recipient) {
    // ...
}
~~~

Spring locates the executor matching that qualifier/name and submits work to it. The values **2/8/200** above are illustrative only, not a pre-optimized configuration for every mail service. Tune them based on SMTP speed, connection limits, memory, load, and provider policies.

### Meaning of Key Parameters

| Parameter | Meaning | Considerations |
| --- | --- | --- |
| **corePoolSize** | Core worker count | I/O-bound mail tasks may need more workers than CPU-bound tasks |
| **maxPoolSize** | Maximum worker count | Caps concurrency, avoiding overloading SMTP/provider |
| **queueCapacity** | Waiting task count | Overly large queues increase latency and memory usage |
| **threadNamePrefix** | Worker name prefix | Helpful when reading logs and thread dumps |
| **waitForTasksToCompleteOnShutdown** | Policy to wait for tasks on shutdown | Does not guarantee saving tasks if the process is killed abruptly |

With ThreadPoolTaskExecutor using a positive-capacity queue, the executor normally prefers using core workers and queuing tasks before expanding toward maxPoolSize. Thus, configuring a very large queue can leave maxPoolSize rarely used. Do not set an unbounded queue just to avoid rejections.

### What If mailExecutor Is Not Configured?

A method with **@Async("mailExecutor")** requires an executor Spring can resolve by that qualifier. If no matching executor is found, execution can fail due to configuration. If you omit the qualifier and use **@Async**, Spring selects an executor using the async infrastructure's default resolution mechanism. Depending on the environment and Spring Boot auto-configuration, the default executor may differ.

For production mail flows, **naming a dedicated executor** usually makes load limits and monitoring easier to configure than relying on the application's shared executor.

### Having @EnableAsync Does Not Mean Every @Async Applies

@EnableAsync enables annotation-processing infrastructure, yet **cannot fix self-invocation**. Even after configuring an executor properly, calling **this.sendWelcomeEmailAsync(...)** still goes straight to the target in proxy mode. Fix the call path, not just by adding annotations or enlarging the pool.

## 6. Conditions for a Method to Be Intercepted

In typical Spring AOP proxy mode, the proxy must be able to intercept the method call.

### Public Methods Are the Safe Choice

For @Async, prefer **public** methods on Spring-managed beans and call them through that bean from another component.

~~~java
@Service
public class AsyncMailSender {

    @Async("mailExecutor")
    public void sendReceipt(String recipient) {
        // Send mail...
    }
}
~~~

Do not rely on @Async placed on **private** methods, because proxies do not intercept private calls under normal mechanisms. **final** methods or **final** classes can prevent class-based proxies from overriding and intercepting. With JDK dynamic proxies, the method must appear on the interface exposed by the proxy. Exact details depend on proxy type and Spring version.

### JDK Dynamic Proxy vs. Class-Based Proxy

Spring can use two common proxy types:

| Proxy Type | Core Mechanism | Notes |
| --- | --- | --- |
| **JDK dynamic proxy** | Proxy implements the bean's interfaces | Called through the proxy-exposed interface |
| **Class-based proxy** (CGLIB) | Proxy subclasses the target class | Cannot/hard to intercept certain final or private methods |

Common rule: **self-invocation does not cross the proxy boundary from the outside**. Switching from JDK proxies to CGLIB is not a fundamental fix for `this.method()` calls.

### Calling in a Constructor or @PostConstruct

Do not expect @Async to apply when called from a constructor or during bean initialization:

~~~java
@PostConstruct
void init() {
    sendWelcomeEmail("admin@example.test");
}

@Async("mailExecutor")
public void sendWelcomeEmail(String recipient) {
    // ...
}
~~~

This is still an internal call within the same bean, and initialization timing may occur before all proxy/lifecycle components are ready. If work must be started once the application is ready, use an appropriate lifecycle/event mechanism and call a separate async bean. Do not use bean initialization methods to send transactional emails.

### Manually Instantiated Objects Are Not Spring Beans

Example:

~~~java
AsyncWelcomeMailService sender = new AsyncWelcomeMailService(mailSender);
sender.sendWelcomeEmail("user@example.test");
~~~

This is a Java object created with new, not a Spring-managed bean, so it has no AOP proxy for @Async. Obtain dependencies through constructor injection from the Spring container.

### Annotating an Internally Called Method Does Not Create a Separate Thread

Adding @Async multiple times does not change the call path:

~~~java
@Async
public void first() {
    second(); // still a call on this
}

@Async
public void second() {
    // ...
}
~~~

If another bean calls **first()** through the proxy, the entire first method runs on a worker thread. However, when **first()** calls **second()** internally, second usually runs **on the same worker thread executing first**, rather than being submitted as a second async task.

This is not necessarily wrong if the goal is merely running the whole chain in the background. But if **second()** is expected to run independently with its own executor or error policy, call it through an appropriate proxy.

## 7. Return-Type Contract of @Async

An @Async method should not return an arbitrary type just because Java allows it. In annotation-driven proxy mode, commonly supported return types are:

- **void**: the caller does not directly receive the send outcome.
- **Future<T>**: the caller has a handle to the asynchronous result.
- **CompletableFuture<T>**: the caller can compose, handle errors, and track completion.

### Using void for Emails Where the Caller Does Not Wait

~~~java
@Async("mailExecutor")
public void sendWelcomeEmail(String recipient) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setTo(recipient);
    message.setSubject("Welcome");
    message.setText("Hello!");
    mailSender.send(message);
}
~~~

Caller invokes:

~~~java
asyncWelcomeMailService.sendWelcomeEmail(email);
// Caller continues if the task was accepted by the executor.
~~~

When the worker throws an exception, the caller has no Future to catch it. Configure exception handling for **void-return async methods** or catch and record errors inside the worker.

### Using CompletableFuture to Receive Results

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;

@Async("mailExecutor")
public CompletableFuture<Void> sendReceiptAsync(String recipient) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setTo(recipient);
    message.setSubject("Receipt");
    message.setText("Your receipt was created successfully.");

    mailSender.send(message);
    return CompletableFuture.completedFuture(null);
}
~~~

Call from another bean:

~~~java
CompletableFuture<Void> result =
        asyncMailSender.sendReceiptAsync(recipient);

result.whenComplete((ignored, error) -> {
    if (error != null) {
        log.error("Unable to submit receipt email", error);
    }
});
~~~

The Spring proxy returns a handle representing the submitted task. Inside the worker, the target method can return **CompletableFuture.completedFuture(null)** after mailSender.send(...) finishes; if mailSender throws an error, the outer handle completes exceptionally.

**Do not call result.join() or result.get() immediately inside an HTTP request** if the goal is not blocking the request. Both methods wait for task completion, diminishing or negating the benefit of async. Waiting intentionally can make sense in tests, batch jobs, or when business logic truly requires the outcome before proceeding.

### Do Not Use @Async to Turn Failures into Successes

If the caller returns HTTP 200 right after submitting the task, that only means the request progressed as far as submitting the task, **not that the email was accepted by SMTP**. API design should distinguish states:

~~~text
REQUEST_ACCEPTED
      |
      v
ASYNC_TASK_QUEUED
      |
      v
SMTP_SUBMISSION_ATTEMPTED
      |
      +-- SUCCESS (transport accepted)
      |
      '-- FAILURE (retry/alert)
~~~

Choose responses/statuses aligned with the business contract; do not state “email sent successfully” the moment an async method is called.

## 8. Combining @Async with @Transactional: Do Not Send Mail Before Commit

Fixing self-invocation makes @Async genuinely submit tasks to the executor. Yet that is **not a complete solution for transaction consistency**.

Consider this case:

~~~java
@Transactional
public void register(RegisterCommand command) {
    User user = userRepository.save(User.from(command));

    // Call goes through @Async proxy, may run on worker immediately.
    asyncWelcomeMailService.sendWelcomeEmail(user.getEmail());

    // A later step may fail.
    validateRegistrationLimit(command);
}
~~~

If the executor runs the task quickly, the email can be sent **before the database transaction commits**. If validateRegistrationLimit(...) then throws an exception causing the transaction to roll back, the user may still receive a confirmation email for an account that does not exist in the database.

### Two Independent Boundaries

**@Async** answers the question: *which thread does the task run on, and does it block the caller?*

**Transaction commit** answers the question: *has data been durably written and is post-commit work permitted to run?*

These two factors are not identical:

~~~text
HTTP thread
    |
    v
BEGIN TRANSACTION
    |
    v
Save user
    |
    +-- submit async mail task ---> Worker thread
    |                                   |
    |                                   v
    |                              SMTP accepted
    v
Validation fails
    |
    v
ROLLBACK

Mail already sent even though user was not committed.
~~~

Moving the mail service to a separate bean solves proxying; **waiting for commit before submitting the task** solves sending emails for rolled-back transactions.

### How to Combine: Publish an Event Inside the Transaction, Call the Async Bean After Commit

Registration service publishes an event:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountRegistrationService {

    private final UserRepository userRepository;
    private final ApplicationEventPublisher eventPublisher;

    public AccountRegistrationService(
            UserRepository userRepository,
            ApplicationEventPublisher eventPublisher
    ) {
        this.userRepository = userRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Long register(RegisterCommand command) {
        User user = userRepository.save(User.from(command));

        eventPublisher.publishEvent(
                new AccountRegisteredEvent(
                        user.getId(),
                        user.getEmail()
                )
        );

        return user.getId();
    }
}

public record AccountRegisteredEvent(Long userId, String email) {
}
~~~

Listener waits for transaction commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AccountRegisteredMailListener {

    private final AsyncWelcomeMailService asyncWelcomeMailService;

    public AccountRegisteredMailListener(
            AsyncWelcomeMailService asyncWelcomeMailService
    ) {
        this.asyncWelcomeMailService = asyncWelcomeMailService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onRegistered(AccountRegisteredEvent event) {
        // Call separate @Async bean, through that bean's proxy.
        asyncWelcomeMailService.sendWelcomeEmail(event.email());
    }
}
~~~

Execution flow:

~~~text
AccountRegistrationService.register()
        |
        v
BEGIN TRANSACTION
        |
        v
Save user + publish AccountRegisteredEvent
        |
        +----- rollback ------> AFTER_COMMIT listener does not run
        |
        '-- commit succeeds
                   |
                   v
           @TransactionalEventListener
                   |
                   v
           AsyncWelcomeMailService proxy
                   |
                   v
                mailExecutor
                   |
                   v
              JavaMailSender
~~~

This approach combines three separate responsibilities:

- The business service decides when the account is created.
- The transactional event listener waits for **AFTER_COMMIT**.
- The async mail bean offloads mail sending to the executor.

**Note:** a post-commit event listener does not automatically make the async call durable. If the process stops right after commit but before the mail task runs, in-memory notifications can be lost. For transactional emails requiring guaranteed retries, use a transactional outbox or durable messaging.

### Transaction Context Does Not Automatically Move to the Worker Thread

Spring transactions in imperative models are typically bound to a thread. The @Async worker thread does not automatically join the HTTP thread's original transaction.

This means:

- Do not pass a JDBC Connection or EntityManager belonging to the old transaction to the worker.
- Do not rely on JPA lazy-loading from entities held in events.
- Only pass IDs or immutable DTOs containing the data needed for the email.
- If the worker must read the database, call a service/repository with appropriate transaction boundaries.
- If recording send status after commit from a synchronous listener, note that resources from the just-committed transaction may still be bound; open a new transaction when writing separately.

Putting @Async and @Transactional on the same method can also obscure transaction boundaries due to proxy advisor ordering. For mail-sending needs, keep business transactions and mail workers in components with clear responsibilities.

## 9. Error Handling When an @Async Task Sends Email

Moving work to the background means errors no longer necessarily surface at the caller. If SMTP times out or JavaMailSender throws **MailException**, the worker must have a handling strategy.

### For void Methods

Example:

~~~java
@Async("mailExecutor")
public void sendWelcomeEmail(String recipient) {
    mailSender.send(createMessage(recipient));
}
~~~

If mailSender.send(...) throws a runtime exception, the caller has already returned and has no Future to catch it. Spring supports **AsyncUncaughtExceptionHandler** for uncaught exceptions in void @Async methods.

Configuration example:

~~~java
import java.lang.reflect.Method;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {

    private static final Logger log =
            LoggerFactory.getLogger(AsyncErrorConfiguration.class);

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (Throwable ex, Method method, Object... params) -> {
            log.error(
                    "Async method {} failed",
                    method.getName(),
                    ex
            );
        };
    }
}
~~~

This illustrates configuring the handler; an application should only have appropriate @EnableAsync configuration, avoiding accidentally creating multiple unnecessary async configurations. If you already have an @EnableAsync class from earlier, you can integrate AsyncConfigurer there.

**AsyncUncaughtExceptionHandler is not a retry mechanism.** It records exceptions from void methods. Retrying requires a separate mechanism with explicit limits, retry intervals, and classification of transient/permanent errors.

### For CompletableFuture

Callers can handle errors on the Future:

~~~java
CompletableFuture<Void> task =
        asyncMailSender.sendReceiptAsync(recipient);

task.exceptionally(error -> {
    log.error("Unable to send receipt", error);
    return null;
});
~~~

Or:

~~~java
task.whenComplete((unused, error) -> {
    if (error == null) {
        metrics.recordMailSubmissionSuccess();
    } else {
        metrics.recordMailSubmissionFailure(error);
    }
});
~~~

The functions above illustrate handling on a Future; **metrics** is an application-defined component. The whenComplete method may run on the thread completing the Future; if the callback performs heavy work, offload it to an appropriate executor using async variants of CompletableFuture.

### Distinguishing Error Types

| Error | Where It Occurs | Handling Approach |
| --- | --- | --- |
| Unable to resolve executor | Before/when submitting task | Fix bean/qualifier configuration |
| Executor rejects task | At submission time | Backpressure, durable queue, clear response |
| SMTP timeout | Inside worker | Bound timeouts, retry per policy |
| Invalid email address | During preparation or sending | Validate and classify as error not to retry endlessly |
| Template rendering failure | Inside worker or before submit, depending on design | Record template/data issue |
| Provider accepts then bounces | After SMTP submission | Track provider events/bounces |

An important point: **executor rejection can throw an exception right at the proxy call**, before a worker is spawned. Therefore, do not assume every async error only appears later inside the worker.

### Timeouts Matter More Than Just Adding Threads

@Async does not make SMTP faster. If a worker is blocked waiting on the network for too long, the pool loses free workers and the queue can fill up.

Example timeout configuration for JavaMailSender/Spring Boot:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

The values above are in milliseconds and are only examples that must be tuned to system requirements. You also need SMTP authentication/TLS matching the server; do not put passwords in source code.

### Do Not Log Sensitive Information

Exceptions or async parameters can contain email addresses, password reset tokens, or personal content. Handlers should log the error type, event/correlation ID, and minimal metadata needed for investigation; avoid dumping full bodies, credentials, or secret links.

## 10. Alternatives and Trouble-Prone Workarounds

**Extracting a separate bean** is the preferred choice when proxy-style @Async is needed. Several alternatives exist, though their trade-offs must be understood.

### Option A — Calling TaskExecutor Directly

Using @Async is not mandatory. You can inject TaskExecutor and submit work explicitly:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailPublisher {

    private final TaskExecutor mailExecutor;
    private final BlockingWelcomeMailSender blockingSender;

    public WelcomeMailPublisher(
            @Qualifier("mailExecutor") TaskExecutor mailExecutor,
            BlockingWelcomeMailSender blockingSender
    ) {
        this.mailExecutor = mailExecutor;
        this.blockingSender = blockingSender;
    }

    public void enqueueWelcomeEmail(String recipient) {
        mailExecutor.execute(
                () -> blockingSender.sendWelcomeEmail(recipient)
        );
    }
}
~~~

In this case, task submission is **explicit**. There is no @Async self-invocation issue because it does not rely on an AOP interceptor. This is a reasonable choice when you want control over task scheduling, executor selection, and error policy right at the call site.

However, this approach still has the limits of an in-memory executor: it can reject tasks, lose tasks if the process dies, does not automatically wait for database commits, and does not automatically retry on SMTP errors.

### Option B — Self-Injection (Not Recommended as Default)

Some examples attempt to inject the bean into itself:

~~~java
@Service
public class RegistrationService {

    private final RegistrationService selfProxy;

    // ...
}
~~~

The goal is calling **selfProxy.sendAsync(...)** instead of **this.sendAsync(...)** to go through the proxy. However:

- Easily creates circular dependencies and complicates bean initialization.
- Depends on proxy type, injection mechanism, and bean lifecycle management.
- As the class evolves, it becomes unclear why a component injects itself.
- Easily copied as a general anti-pattern for both @Async and @Transactional.

Techniques like lazy injection or querying the container for the proxy exist, yet are usually technical workarounds for special cases. For mail sending, **splitting out a separate async bean is cleaner**.

### Option C — Looking Up the Bean from ApplicationContext

Example:

~~~java
RegistrationService proxy =
        applicationContext.getBean(RegistrationService.class);
proxy.sendWelcomeEmailAsync(recipient);
~~~

This technique can go through the proxy in suitable setups, yet couples the service directly to the container and proxy type. If the bean is proxied by interface, looking up by concrete class may not behave as expected. It also makes testing and dependency tracing harder.

**Constructor injection via another bean** is better in most application designs.

### Option D — AopContext.currentProxy()

Spring AOP provides a mechanism to access the current proxy when appropriate exposeProxy configuration is enabled. However, this creates direct coupling to Spring AOP and can throw an error if the current call does not execute in a context where the proxy is exposed.

Do not use it as a default solution for mail sending; consider it only with a clear technical reason and acceptance of the coupling cost.

### Option E — AspectJ Weaving

**@EnableAsync** can be configured to use AspectJ mode instead of proxies if the application has the appropriate dependencies and compile-time/load-time weaving. Because advice is woven into bytecode, this mechanism can handle self-invocation differently from proxies.

However, AspectJ requires separate build/runtime configuration, increasing deployment and debugging complexity. There is no need to switch the entire AOP mode just to fix one same-bean email call if splitting a bean already meets requirements.

### Comparing Options

| Approach | Strengths | Limitations |
| --- | --- | --- |
| **Separate async bean** | Clear, easy to test, idiomatic Spring DI | Requires an extra class/bean |
| **TaskExecutor.execute(...)** | Explicit submission, proxy-independent | Manual management of errors and task lifecycle |
| **Self-injection** | Can invoke the bean's own proxy | Circular dependency, coupling, harder to read |
| **ApplicationContext lookup** | Can retrieve proxy from container | Service locator, proxy/config dependency |
| **AopContext.currentProxy()** | Can call back via proxy when configured | Strong AOP coupling, special configuration |
| **AspectJ weaving** | Can apply advice on self-calls | Increases build and runtime complexity |

## 11. Testing That Calls Actually Go Through the Proxy

To test @Async, verify behavior in a **Spring context with async enabled**, not merely by calling a Java object created with new.

### Testing with a Thread-Probing Bean

A simple component to observe the worker thread:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class AsyncThreadProbe {

    @Async("mailExecutor")
    public CompletableFuture<String> workerThreadName() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
        );
    }

    public CompletableFuture<String> callWithinSameBean() {
        // Internal call does not go through the @Async proxy.
        return workerThreadName();
    }
}
~~~

Integration test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class AsyncProxyIntegrationTest {

    @Autowired
    private AsyncThreadProbe probe;

    @Test
    void externalCallUsesMailExecutor() throws Exception {
        String workerName =
                probe.workerThreadName().get(5, TimeUnit.SECONDS);

        assertTrue(workerName.startsWith("mail-"));
    }

    @Test
    void selfInvocationDoesNotUseAsyncInterceptor() throws Exception {
        String currentThread = Thread.currentThread().getName();

        String invokedThread =
                probe.callWithinSameBean().get(5, TimeUnit.SECONDS);

        assertEquals(currentThread, invokedThread);
    }
}
~~~

The test assumes **mailExecutor** with prefix **mail-** exists in the Spring context. It illustrates two call paths:

- From test through proxy to **workerThreadName()**: the task executes on a worker.
- From test through **callWithinSameBean()**, where target calls workerThreadName() on itself: the internal call runs on the current thread.

This style of test is useful for confirming understanding of the proxy mechanism. In real application tests, also check that **mailSender.send(...)** is called properly, errors are recorded, and business logic does not claim mail was delivered when only the task was submitted.

### Unit Testing RegistrationService

Once **AsyncWelcomeMailService** has been extracted:

~~~java
@Test
void registerRequestsWelcomeMail() {
    UserRepository repository = mock(UserRepository.class);
    AsyncWelcomeMailService mail = mock(AsyncWelcomeMailService.class);

    User savedUser = sampleUser("learner@example.test");
    when(repository.save(any(User.class))).thenReturn(savedUser);

    RegistrationService registration =
            new RegistrationService(repository, mail);

    registration.register(sampleRegisterCommand());

    verify(mail).sendWelcomeEmail("learner@example.test");
}
~~~

In a unit test, mail is a mock and there is no Spring AOP proxy. This test only checks **whether the business service called its dependency properly**; it does not prove the @Async method runs on another thread. Therefore, combine dependency unit tests with proxy/executor integration tests at two separate levels.

### Testing Email Sending Without Real SMTP

You can mock JavaMailSender to verify message content or use an SMTP test server/capture in integration tests. Avoid sending real emails to external addresses during automated tests.

If a test must wait for an async task to finish, use **CompletableFuture.get(timeout, unit)**, **CountDownLatch**, or waiting utilities with timeouts. Do not use fixed Thread.sleep assuming workers always finish after an exact number of milliseconds; that easily produces flaky tests.

### Testing @TransactionalEventListener

If triggering email via **AFTER_COMMIT**, test separately:

- Event is published in the transaction, yet the mail task is not submitted before commit.
- Transaction commits successfully: listener calls the async bean.
- Transaction rolls back: AFTER_COMMIT listener does not call the async bean.
- Publishing outside a transaction with default fallbackExecution false: listener does not run.

Note that a Spring test marked **@Transactional** normally rolls back when the test ends. Thus, to test AFTER_COMMIT, explicitly commit using TransactionTemplate or appropriate TestTransaction utilities; otherwise, the listener not running is correct rollback behavior, not an @Async bug.

## 12. ThreadLocal, SecurityContext, and Data Passed to Async Tasks

When @Async works properly, the worker runs on a different thread. This affects information stored in **ThreadLocal** on the request thread.

Examples of data commonly tied to execution context:

| Data | Note with @Async |
| --- | --- |
| **Transaction context** | Does not automatically move to the worker thread |
| **SecurityContext** | Not guaranteed to carry the same authentication unless context propagation is configured |
| **MDC/correlation ID** | Needs a context-propagation mechanism if worker logs need the same trace |
| **Locale/timezone** | Should be passed explicitly for consistent email rendering |
| **Request-scoped bean** | May not exist or be safe when the worker runs after the request |
| **JPA entity/lazy association** | May no longer have an active persistence context |

### Do Not Pass HttpServletRequest to an Async Worker

Avoid this design:

~~~java
@Async("mailExecutor")
public void sendWelcomeEmail(HttpServletRequest request) {
    String recipient = request.getParameter("email");
    // ...
}
~~~

The worker may run after the request has already completed. Request objects, sessions, or security state have lifecycles and synchronization properties unsuitable for arbitrary sharing.

Prepare data in the service before submitting:

~~~java
public record WelcomeMailCommand(
        String recipient,
        String displayName,
        String localeTag,
        String correlationId
) {
}
~~~

~~~java
WelcomeMailCommand command = new WelcomeMailCommand(
        user.getEmail(),
        user.getDisplayName(),
        locale.toLanguageTag(),
        correlationId
);

asyncWelcomeMailService.sendWelcomeEmail(command);
~~~

The worker constructs Locale from localeTag, prepares the template context, and sends mail. If the command is an immutable record holding the required values, the worker does not need to depend on the request thread.

### Watch Out for SecurityContext

If the worker needs access to resources restricted to the current user, do not assume SecurityContext from the HTTP thread will exist in the worker. Wrappers/delegating executors exist to propagate security context per Spring Security configuration. However, for transactional emails, it is usually better to **verify access permissions before enqueuing and pass authorized IDs/data** into the task, rather than making the worker depend on the user's login session.

### Watch Out for MDC

MDC logs can use correlation IDs to tie HTTP logs and SMTP logs together. If correlation IDs must be preserved in workers, configure a TaskDecorator or appropriate context propagation mechanism. When copying MDC, **restore/clear context** after the task to avoid leaving previous request data on pooled threads reused later.

Avoid putting full request headers or sensitive personal data into MDC. Use only trace IDs and safe metadata.

## 13. An In-Memory Executor Is Not a Durable Queue

A common misconception is: once self-invocation is fixed, the email “will definitely be sent”. In reality, @Async typically only hands the task to an executor **inside the running process**.

### Cases Where Tasks May Not Complete

- Executor runs out of queue capacity and rejects the task.
- Application is killed, host loses power, or container restarts.
- SMTP server times out causing workers to stall for a long time.
- Worker throws an exception with no retry.
- Application shuts down before queued tasks finish.
- Task is canceled per application policy.

**@Async solves concurrency; it does not automatically solve durability.**

### Solution for Critical Emails: Transactional Outbox

If an email contains an invoice, payment notice, or activation link that the system must retry, a more durable design is:

~~~text
Business transaction
      |
      +-- Save order/account
      |
      '-- Write OutboxEvent(PENDING)
                |
                v
              COMMIT
                |
                v
         Background outbox worker
                |
                v
         Render + send email
                |
          +-----+------+
          |            |
        SUCCESS       FAILURE
          |            |
          v            v
       Mark SENT    Retry/backoff
~~~

The outbox event is written in the same transaction as business data. If the transaction rolls back, the event rolls back too; if committed, the event exists durably for workers to process after application restarts.

A mail worker can still use @Async internally to parallelize processing, yet **the durable source of work** is the outbox/queue rather than the Java thread pool.

### Duplicate Sending and Idempotency

Suppose SMTP received the email, yet the application died before updating the outbox to SENT. After restart, the worker reads the PENDING event and sends again. The recipient may receive two messages.

Therefore, do not claim an outbox guarantees **exactly-once email delivery**. Typically you need:

- Unique event ID.
- Work-claiming mechanism preventing multiple workers from sending simultaneously.
- Retries with backoff and attempt limits.
- Recording send status separately from business status.
- Idempotency keys when the mail provider/API supports them.
- Rules for handling duplicates when single delivery cannot be guaranteed.

### When Is @Async Alone Enough?

A low-importance email such as an optional welcome notification can use async directly if the product accepts occasional missed sends and has appropriate operational monitoring. For emails with legal, transactional, or security requirements, consider an outbox/durable messaging from the start.

## 14. Common Mistakes Table for Self-Invoking @Async

| Symptom or Practice | Problem | Resolution |
| --- | --- | --- |
| Calling this.sendEmailAsync() | Bypasses Spring proxy | Call a separate async bean |
| Omitting this yet still calling sendEmailAsync() internally | Still self-invocation | Split bean |
| Only adding @EnableAsync | Does not change call path | Enable async **and** call via proxy |
| Using new AsyncMailService(...) | Object not managed by Spring proxy | Inject Spring-managed bean |
| Putting @Async on a private method | Normal proxies do not intercept private | Use public method on separate bean |
| Putting @Async on a final method with class-based proxy | Cannot override to intercept | Remove final or redesign |
| Injecting a bean into itself | Risk of circular dependency/coupling | Separate responsibilities |
| Switching proxy from JDK to CGLIB to fix this-calls | Self-calls still bypass proxy | Change bean/call boundary |
| @Async runs yet sends before commit | Transaction not finished | AFTER_COMMIT or outbox |
| Calling CompletableFuture.get() immediately | Caller blocks waiting for result | Wait only when business requires |
| Void @Async throws error unseen by HTTP | Error occurs on worker | Handler, logs, metrics, retry |
| Executor full | Task rejected | Capacity/backpressure/durable queue |
| Task lacks SecurityContext/MDC | ThreadLocal not propagated automatically | Controlled context propagation |
| Unit testing with new then claiming async works/fails | No Spring proxy in test | Integration test with Spring context |
| SMTP accepts then bounces later | Delivery is a separate phase | Track provider events |

### Do Not Rely on Annotations to Hide Unclear Design

A service that simultaneously confirms transactions, renders HTML, builds MIME messages, opens SMTP connections, writes audits, and manages retries makes it very hard to separate transaction scope from async scope. Separating roles lets @Async serve as a meaningful execution boundary instead of an annotation placed on an arbitrary method.

## 15. Troubleshooting Workflow When @Async Does Not Run

When you see an @Async mail-sending call still taking synchronous time, check in order:

1. **Trace the exact call path**: is the caller invoking an injected bean or calling this.method() on the same object?
2. **Verify the bean is Spring-managed**: not an object manually created with new.
3. **Verify @EnableAsync**: async infrastructure is enabled in the appropriate context.
4. **Verify method visibility/proxy**: public method, not restricted by final/private under the proxy mechanism.
5. **Check the executor**: does the qualifier resolve properly, is the queue full, or has the executor shut down?
6. **Observe threads**: log thread names and a correlation ID in both caller and worker.
7. **Confirm caller does not wait on Future immediately**: get/join can block the calling thread.
8. **Check SMTP timeouts**: async workers can still block on I/O.
9. **Check transaction boundaries**: if sending after commit, inspect event phase and callback registration.
10. **Test at the right layer**: unit test logic separately; integration test AOP proxy and executor.

### Short Decision Diagram

~~~text
Method has @Async
          |
          v
Bean managed by Spring?
     |              |
    No             Yes
     |              |
     v              v
   No proxy      @EnableAsync enabled?
                     |          |
                    No         Yes
                     |          |
                     v          v
                 Configure    Call through proxy?
                                  |          |
                                 No         Yes
                                  |          |
                                  v          v
                              Self-call    Executor resolves?
                              runs sync       |          |
                                             No         Yes
                                              |          |
                                              v          v
                                          Fix config  Task submitted
                                                        |
                                                        v
                                                 Check queue/errors
~~~

If TaskExecutor is invoked yet HTTP still waits, check whether the caller synchronously awaits the Future, performs heavy work **before** the async call, or executes another direct email send elsewhere. Not every HTTP delay is caused by self-invocation.

## 16. Practice Scenarios

### Scenario A — Does removing the `this` keyword fix it?

Original code:

~~~java
this.sendWelcomeEmailAsync(email);
~~~

Changed to:

~~~java
sendWelcomeEmailAsync(email);
~~~

**Answer:** no. Both are calls on the same instance. In proxy mode, both bypass the @Async interceptor.

### Scenario B — @EnableAsync is enabled and 10 workers are configured

The call still runs on the HTTP thread.

**Question:** should maxPoolSize be increased?

**Answer:** not as the first fix. Check for self-invocation and confirm the call goes through a Spring proxy. A larger pool does not help a call that was never submitted.

### Scenario C — Async bean extracted, yet emails sent for rolled-back transactions

RegistrationService has @Transactional and calls the async bean before commit.

**Question:** what problem remains?

**Answer:** the task runs asynchronously but can start before commit. Publish an event inside the transaction, handle it at AFTER_COMMIT to call the async bean, or use an outbox if durability is required.

### Scenario D — An @Async method in the same bean calls another @Async method

A bean is called externally through the proxy into firstAsync(), and inside firstAsync() it calls secondAsync().

**Question:** is secondAsync() submitted as an independent task?

**Answer:** usually not in proxy mode. firstAsync() can run on a worker, yet the internal secondAsync() call still runs on that same worker.

### Scenario E — Mail method returns CompletableFuture yet requests remain slow

Caller uses:

~~~java
asyncMailSender.sendReceiptAsync(email).join();
~~~

**Question:** why does the request wait?

**Answer:** join() waits for the Future to complete. If the goal is returning an immediate response, do not wait for the result in the request; process status afterward.

### Scenario F — Mail sending fails yet HTTP sees no exception

The async method returns void and sending fails on the worker.

**Question:** what should be done?

**Answer:** use AsyncUncaughtExceptionHandler or catch errors inside the worker to log/record/retry. The prior HTTP request should not be expected to receive worker exceptions by default.

### Scenario G — Test instantiates MailService with new and calls @Async

The test observes the method running on the test thread.

**Question:** does this prove the annotation fails in the real application?

**Answer:** no. Objects created with new have no Spring proxy. To test interception, obtain the bean from a Spring context with @EnableAsync enabled.

### Scenario H — Worker cannot read user info

The service passes HttpServletRequest or a JPA entity with lazy properties to the worker.

**Question:** how should this be fixed?

**Answer:** pass an immutable mail command containing required data or IDs. If re-querying is necessary, open a transaction in the worker instead of relying on old request/transaction contexts.

### Scenario I — Process is killed after task is enqueued

**Question:** does @Async automatically recover tasks after restart?

**Answer:** no. An in-memory thread pool is not a durable queue. Use an outbox or a durable queue when notifications must not be lost.

### Scenario J — Can TaskExecutor be used instead of @Async?

**Answer:** yes. Submitting tasks explicitly via TaskExecutor.execute(...) does not depend on an @Async proxy, though the caller must design error handling, backpressure, cancellation, and transaction boundaries itself.

## 17. Principles for Implementing Asynchronous Spring Mail

~~~text
CORRECT CALL

BusinessService
      |
      v
Spring proxy of AsyncMailService
      |
      v
TaskExecutor
      |
      v
Worker thread
      |
      v
JavaMailSender


INCORRECT CALL

BusinessService.methodA()
      |
      v
this.methodB()   <-- @Async on methodB is bypassed
      |
      v
JavaMailSender runs synchronously
~~~

For emails tied to database transactions, add one more boundary:

~~~text
Business transaction COMMIT
          |
          v
AFTER_COMMIT listener
          |
          v
AsyncMailService proxy
          |
          v
mailExecutor / worker
          |
          v
JavaMailSender
~~~

**Do not self-invoke @Async methods within the same bean** is a key rule of Spring AOP proxy mode. An internal call through **this** does not cross the proxy, so the @Async annotation does not take effect as expected. Place the mail-sending task in a **separate Spring bean**, inject that bean, and call it through the proxy; configure a clearly bounded executor, test threads/errors at the proper layer, and use AFTER_COMMIT if emails may only be sent after a transaction succeeds. When crash recovery and durable retries are required, use a transactional outbox or durable queue rather than relying solely on @Async.
