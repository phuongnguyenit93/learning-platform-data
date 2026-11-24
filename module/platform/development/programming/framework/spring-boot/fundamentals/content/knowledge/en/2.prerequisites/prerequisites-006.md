# Exceptions, Stack Traces, and How to Trace Root Causes

In Java and Spring Boot, seeing **Application run failed**, an HTTP **500 Internal Server Error**, or **Exception in thread "main"** only tells you *the system failed somewhere*. To fix the bug properly, you must identify what operation failed, where it failed, what led to it, and which component is responsible for supplying the missing data or configuration.

Three concepts form the foundation for investigation:

- **Exception**: an object representing an abnormal condition during execution.
- **Stack trace**: the chain of method calls recorded when an error object is created/captured.
- **Cause chain**: exceptions linked via their underlying cause, typically printed under **Caused by:** labels.

Spring Boot builds on Java's exception mechanism and Spring Framework's error-handling mechanisms. Therefore, when reading Spring Boot logs, you still need to understand how Java throws exceptions, how Spring wraps or translates exceptions, and how to trace back to the relevant point in application code.

## 1. What Is an Exception?

When a method cannot complete its work according to its contract, it can throw an exception. For example:

~~~java
public int parseQuantity(String rawQuantity) {
    return Integer.parseInt(rawQuantity);
}
~~~

With the string **"12"**, the method returns the integer **12**. With **"abc"**, **Integer.parseInt** throws a **NumberFormatException** because the string does not represent a valid integer.

An exception can contain:

| Component | Meaning |
|---|---|
| **Type** | The exception class, such as **NumberFormatException**. |
| **Message** | A message describing the error, which may be absent or incomplete. |
| **Stack trace** | Stack frames identifying the recorded method calls. |
| **Cause** | Another Throwable explaining why the current exception was created. |
| **Suppressed exceptions** | Secondary errors raised, such as while closing a resource after a primary error. |

An exception is a Java object. A UI error message, an HTTP status code, or a log line is usually just **how one layer of the application presents the exception**. For instance, the same parsing error can be translated by the web layer into HTTP **400 Bad Request** or allowed to propagate as HTTP **500**, depending on how the application handles it.

### 1.1. The Throwable Inheritance Hierarchy

~~~text
java.lang.Throwable
├── java.lang.Error
│   ├── OutOfMemoryError
│   ├── StackOverflowError
│   └── ...
└── java.lang.Exception
    ├── IOException
    ├── SQLException
    ├── ...
    └── java.lang.RuntimeException
        ├── NullPointerException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── IllegalStateException
        ├── IndexOutOfBoundsException
        └── ...
~~~

**Throwable** is the base class for both **Error** and **Exception**. It provides methods such as **getMessage()**, **getCause()**, **getStackTrace()**, and **printStackTrace()**.

- **Exception** typically represents error conditions an application can handle or propagate.
- **RuntimeException** is a branch of Exception not subject to the compiler's checked-exception rules.
- **Error** typically represents serious problems at the runtime or JVM level. Normally you should not catch every Error and try to continue as if nothing happened.

The name **Error** does not mean all programmer bugs live in that branch. For example, dereferencing a null reference causes **NullPointerException**, which is a RuntimeException.

### 1.2. Checked and Unchecked Exceptions

| Category | Examples | Compile-Time Responsibility |
|---|---|---|
| **Checked exception** | **IOException**, **SQLException** | Callers must catch it or declare **throws** if the exception can propagate out. |
| **Unchecked exception** | **NumberFormatException**, **NullPointerException**, **IllegalArgumentException** | The compiler does not require catching or declaring it. |
| **Error** | **OutOfMemoryError**, **StackOverflowError** | Not required to be caught or declared. |

By Java's definition, unchecked throwables include **RuntimeException** and its subclasses, plus **Error** and its subclasses. Other Exception classes not extending RuntimeException are checked exceptions.

Example of a checked exception:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public String readConfig(Path file) throws IOException {
    return Files.readString(file);
}
~~~

**Files.readString** can throw IOException; thus **readConfig** declares **throws IOException**. Conversely, **Integer.parseInt("abc")** can throw NumberFormatException without requiring a declaration.

**Checked** does not mean "less dangerous", and **unchecked** does not mean "safe to ignore". How you handle an exception still depends on whether the current layer has enough information to recover.

## 2. How Do Exceptions Propagate Through Methods?

Consider the class:

~~~java
public class OrderCalculator {
    public int calculateTotal(String quantityText, int price) {
        int quantity = parseQuantity(quantityText);
        return quantity * price;
    }

    private int parseQuantity(String quantityText) {
        return Integer.parseInt(quantityText);
    }
}
~~~

When called:

~~~java
new OrderCalculator().calculateTotal("abc", 100);
~~~

Execution flow:

~~~text
main()
  └─ calculateTotal("abc", 100)
       └─ parseQuantity("abc")
            └─ Integer.parseInt("abc")
                 └─ throw NumberFormatException
~~~

When an exception is thrown, Java looks for a matching **catch** block. If the current method does not catch it, the exception unwinds back to its caller. This process is called **stack unwinding**. If unhandled at a higher boundary, the exception can terminate the execution thread or be handled by a framework dispatcher.

Example of catching an expected error:

~~~java
try {
    int total = new OrderCalculator().calculateTotal("abc", 100);
    System.out.println(total);
} catch (NumberFormatException ex) {
    System.out.println("Quantity must be an integer.");
}
~~~

In a Spring MVC application, an exception escaping a controller usually passes through the **HandlerExceptionResolver** system and can be handled by an **@ExceptionHandler**. If no handler matches, the request may receive a server error response. Hence, an exception being thrown **does not necessarily stop the entire Spring Boot application**.

### 2.1. Distinguishing throw, throws, catch, and finally

| Syntax | Role |
|---|---|
| **throw new IllegalArgumentException("...");** | Throws a specific exception at runtime. |
| **void load() throws IOException** | Declares checked exceptions that may propagate from the method. |
| **catch (IOException ex)** | Catches and handles exceptions of a matching type. |
| **finally { ... }** | Performs cleanup normally when leaving try/catch; not an absolute guarantee if the JVM terminates abruptly. |

When catching an exception, you can fix the condition, translate it into a contractual failure result, rethrow it, or wrap it in an exception meaningful at the current layer. Catching without taking one of those intentional actions usually just hides the problem.

## 3. What Is a Stack Trace?

For each execution thread, the JVM tracks active method calls on the **call stack**. A Throwable's **stack trace** records the stack frames, typically showing class name, method name, source file, and line number.

Illustrative example for `OrderCalculator`:

~~~text
java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.NumberFormatException.forInputString(NumberFormatException.java:67)
    at java.base/java.lang.Integer.parseInt(Integer.java:668)
    at java.base/java.lang.Integer.parseInt(Integer.java:786)
    at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:8)
    at com.example.orders.OrderCalculator.calculateTotal(OrderCalculator.java:3)
    at com.example.orders.Main.main(Main.java:6)
~~~

*Line numbers and Java internal frames above are only for explaining structure; they may vary depending on JDK version, compilation, and actual source locations.*

### 3.1. First Line: Type and Message

~~~text
java.lang.NumberFormatException: For input string: "abc"
~~~

The part to the left of the colon is the **exception class name**, and the part to the right is the **message**. In this example, the message tells us the input data was the string **"abc"**. Some exceptions have no message or a very generic message, so you also need to read the frames and causes.

### 3.2. What Does a Stack Frame Contain?

~~~text
at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:8)
~~~

| Part | Interpretation |
|---|---|
| **com.example.orders.OrderCalculator** | Fully qualified class name. |
| **parseQuantity** | Method on the call stack. |
| **OrderCalculator.java** | Source file containing the method when compiled. |
| **8** | Relevant line number in the source version used for the build. |

Normally, the top lines of a stack trace are closest to where the Throwable captured its trace. Lines farther down are the callers higher up. Therefore, the **top-to-bottom display order** is the reverse of the **chronological call order**.

In the example above, **main** called **calculateTotal**, then **parseQuantity** called **Integer.parseInt**. Yet the trace prints **Integer.parseInt** before **parseQuantity**, followed by **calculateTotal** and **main**.

When investigating, locate the closest frame inside your **application package**:

~~~text
at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:8)
~~~

This is where application code directly interacted with the failing operation. It is not necessarily the **origin of the bad data**: the string **"abc"** could have come from a request, a config file, or an earlier mapping step.

### 3.3. Limitations of Stack Traces

Stack traces are very useful, but they are not a complete log of a request's entire life:

- They only capture frames from a single moment and a single thread of execution, not every variable assignment that occurred.
- Loggers, log aggregators, or monitoring platforms may truncate output.
- When an exception is created and rethrown later, the trace may reflect where it was originally constructed/captured rather than every subsequent throw site.
- A frame may show **Unknown Source** or **Native Method** without a specific Java line number.
- When work crosses to another thread, executor, or reactive pipeline, the trace may omit the full original call chain.
- Line numbers in a trace must be matched against the **exact source version running**, not necessarily the latest file on your machine.

Thus, a stack trace is a key starting piece of evidence, though you may still need before/after logs, input values, configuration, transactions, or trace IDs.

## 4. Caused by: Reading Nested Cause Chains

In larger applications, exceptions often cross multiple layers. A low-level layer throws a technical error; a higher layer wants to explain the error in more meaningful terms and wraps it:

~~~java
public int parseQuantity(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "quantity must be a valid integer",
                cause
        );
    }
}
~~~

**IllegalArgumentException** is the outer exception. **NumberFormatException** is stored as the **cause** via the two-argument constructor.

Logs may look like:

~~~text
java.lang.IllegalArgumentException: quantity must be a valid integer
    at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:12)
    at com.example.orders.OrderCalculator.calculateTotal(OrderCalculator.java:3)
    at com.example.orders.Main.main(Main.java:6)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.NumberFormatException.forInputString(NumberFormatException.java:67)
    at java.base/java.lang.Integer.parseInt(Integer.java:668)
    at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:8)
    ... 2 more
~~~

The two parts show two levels:

1. **Application-layer error:** a quantity violated the input contract; the application threw IllegalArgumentException.
2. **Underlying technical error:** parsing the number failed on the string **"abc"**.

If the service layer wraps IllegalArgumentException inside another business exception, the trace will contain multiple **Caused by:** sections. Do not stop at the outermost exception when it merely says "Operation failed" or "Error creating bean".

### 4.1. What Does the Ellipsis Line Mean?

~~~text
... 2 more
~~~

The **... N more** line in a cause trace normally means **the last N frames match the enclosing stack trace**, so they are elided to avoid repetition. It does not mean there are N more exceptions.

### 4.2. What Is the Root Cause?

The **root cause** in an exception chain is usually understood as the deepest exception linked via **getCause()**. You can walk the chain like this:

~~~java
Throwable current = exception;
while (current.getCause() != null && current.getCause() != current) {
    current = current.getCause();
}
System.out.println(current);
~~~

However, the deepest exception **does not by itself tell you the fix**. For example, **ConnectException: Connection refused** at the bottom of the chain could be caused by:

- Wrong database host or port.
- Database not started yet.
- A network policy or firewall blocking the connection.
- Application running in a container using the wrong hostname.

Keep these distinct:

| Term | Example |
|---|---|
| **Symptom** | The API returns HTTP 500. |
| **Outer exception** | Failed to fetch order list. |
| **Technical cause** | ConnectException: Connection refused. |
| **Actionable root issue** | The database URL points to an unreachable address in the deployment environment. |

Moving from the cause to the fix requires additional evidence about the environment and configuration rather than guessing from the class name alone.

## 5. How Suppressed Differs from Caused by

When multiple errors occur in a single operation, Java can record secondary exceptions under **Suppressed:**. For example, with **try-with-resources**, if the body throws an exception and closing the resource also throws an exception, the close failure becomes a suppressed exception.

~~~java
try (MyResource resource = openResource()) {
    process(resource); // Fails A
} // resource.close() also fails B
~~~

Illustrative trace format:

~~~text
java.lang.IllegalStateException: Failed to process data
    at com.example.demo.Importer.process(Importer.java:24)
    ...
    Suppressed: java.io.IOException: Failed to close resource
        at com.example.demo.MyResource.close(MyResource.java:41)
        ...
~~~

**Caused by** expresses *this exception was caused by that exception*. **Suppressed** retains an additional exception that occurred alongside, but was not chosen as the primary exception. When investigating, inspect both: the main error cause and any secondary effects that may need addressing.

## 6. Evidence-Based Error Tracing Workflow

An approach applicable to plain Java errors, Spring Boot startup errors, and request errors:

### Step 1: Identify When the Failure Happened

| Phase | Example Symptoms | Where to Start |
|---|---|---|
| **Compile/build** | **cannot find symbol**, **Compilation failed** | Compiler output; this may not be a runtime exception yet. |
| **Spring Boot startup** | **Application run failed**, **Failed to start ApplicationContext** | Startup exception and Caused by chain. |
| **HTTP request handling** | HTTP **400**, **404**, **500** | Request logs, exception handlers, inputs. |
| **Job or message consumer** | Task failure, message retry, dead-letter queue | Job/consumer logs and propagated cause. |

A compile error cannot be solved with **@ExceptionHandler** because the application is not running yet. Startup errors may come from bean initialization; request errors may come from data and business logic.

### Step 2: Gather Complete Facts

You need to know **what action**, **when**, and in **which environment** the error occurred. For requests, note the endpoint, HTTP method, status code, and request ID if available. For background tasks, note the task name, job ID, or message ID. For startup, check active profiles and configuration.

Preserve the **type, message, stack frames, Caused by, and Suppressed** sections. If only a single line like "Internal Server Error" or "Application run failed" remains, crucial diagnostic evidence is missing.

When collecting inputs or configuration, mask **passwords, tokens, personal data, and secrets**. You do not need to log secrets to check whether a property exists.

### Step 3: Identify the Reporting Layer

Read the outermost exception to learn:

- **BeanCreationException**: the container was creating a bean and failed.
- **UnsatisfiedDependencyException**: a required dependency could not be satisfied.
- **DataAccessException**: an issue reported by Spring at the data-access boundary.
- **HttpMessageNotReadableException**: reading/deserializing the HTTP request body failed.
- **IllegalArgumentException**: a method input precondition was violated.

This provides **direction**, not proof that the framework or library has a bug.

### Step 4: Walk Down the Caused by Chain

Look for the most specific remaining exception and details such as:

- Missing **property** name.
- Name of the **bean** that could not be created.
- Unreachable **host:port**.
- **Table**, **constraint**, SQL state, or driver message.
- Malformed **input** value.
- Missing **file** name or path.

Do not stop at **Failed to create bean** as a sufficient explanation when the cause underneath states **Could not resolve placeholder**.

### Step 5: Locate Frames in Application Packages

Example:

~~~text
at com.example.payment.PaymentConfig.paymentClient(PaymentConfig.java:31)
~~~

Open the exact file and running version, inspect the indicated line and surrounding lines. Key question: **what was this method doing**, where did its inputs come from, and why did it call the lower-level component?

When logs contain hundreds of frames from **java.base**, **org.springframework**, **org.hibernate**, and the server, locating application frames connects internal framework processing to your code. Yet if an error stems from framework configuration, do not force the blame onto an unrelated application frame.

### Step 6: Form a Testable Hypothesis

Instead of "Spring Boot is broken", form a concrete hypothesis:

> "The application cannot create PaymentClient because the runtime environment is missing the payment.api-key property."

Then check property declarations, configuration sources, environment variables, and profiles. For bad data, reproduce with the same input; for databases, check actual connectivity and constraints.

### Step 7: Fix the Cause and Reproduce the Scenario

Measure success by **correct behavior** after the fix, not by the log disappearing. A broad catch block returning HTTP **200** can silence every exception while silently losing data.

## 7. Spring Boot Example: Bean Creation Error at Startup

Suppose the application has a bean created from a required property:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PaymentConfig {
    @Bean
    public PaymentClient paymentClient(
            @Value("${payment.api-key}") String apiKey) {
        return new PaymentClient(apiKey);
    }
}
~~~

**PaymentClient** is an example application class. Spring must resolve **payment.api-key** before calling the bean factory method.

If the property does not exist in any active configuration source, startup logs may look like this (abbreviated):

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'paymentClient'
    at org.springframework.beans.factory.support...
    ...
Caused by: java.lang.IllegalArgumentException:
Could not resolve placeholder 'payment.api-key'
in value "${payment.api-key}"
    at org.springframework.util.PropertyPlaceholderHelper...
    ...
~~~

*This is an illustrative example of log structure. The actual outer exception type and frames depend on Spring version, injection style, and configuration.*

Reading layer by layer:

| Clue | Interpretation |
|---|---|
| **Application run failed** | Startup did not complete. |
| **BeanCreationException** | Spring failed to create a bean. |
| **paymentClient** | The bean directly affected. |
| **Could not resolve placeholder** | Spring could not find a required property. |
| **payment.api-key** | Property name to verify in the runtime environment. |

One way to supply the property via a configuration file is:

~~~yaml
payment:
  api-key: ${PAYMENT_API_KEY}
~~~

The deployment environment must then supply **PAYMENT_API_KEY** through an appropriate secrets mechanism. Do not hardcode real keys into source code, commit them to a repository, or print them to logs.

Suppose the bean graph is:

~~~text
PaymentController
       │ needs
       ▼
PaymentService
       │ needs
       ▼
PaymentClient
       │ needs
       ▼
payment.api-key
~~~

An **UnsatisfiedDependencyException** can surface at PaymentController even though the concrete failure occurred while creating PaymentClient. Editing the controller's constructor will not help while the leaf dependency is still missing configuration.

## 8. Spring Boot Example: Invalid Request Data

In an HTTP application, an exception can be mapped into a meaningful client response. Example of a service parsing quantity itself:

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public int calculateTotal(String quantityText, int unitPrice) {
        int quantity;
        try {
            quantity = Integer.parseInt(quantityText);
        } catch (NumberFormatException cause) {
            throw new InvalidQuantityException(
                    "Quantity must be an integer.",
                    cause
            );
        }

        if (quantity <= 0) {
            throw new InvalidQuantityException(
                    "Quantity must be greater than 0."
            );
        }

        return Math.multiplyExact(quantity, unitPrice);
    }
}
~~~

Business exception:

~~~java
package com.example.orders;

public class InvalidQuantityException extends RuntimeException {
    public InvalidQuantityException(String message) {
        super(message);
    }

    public InvalidQuantityException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Spring MVC controller:

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders/total")
    public int total(@RequestParam String quantity) {
        return orderService.calculateTotal(quantity, 100);
    }
}
~~~

When sending:

~~~http
GET /orders/total?quantity=abc HTTP/1.1
Host: localhost:8080
~~~

Error flow:

~~~text
HTTP request with quantity=abc
   ↓
OrderController.total()
   ↓
OrderService.calculateTotal()
   ↓
Integer.parseInt("abc")
   ↓
NumberFormatException
   ↓
InvalidQuantityException (preserving cause)
   ↓
Spring MVC exception handling
   ↓
HTTP response per API contract
~~~

Because **quantity** is accepted as a **String**, conversion occurs inside the service. If the controller accepted **@RequestParam int quantity**, Spring MVC would normally convert the type before invoking the method, potentially throwing **MethodArgumentTypeMismatchException** at the binding layer. The same invalid input string produces different exceptions depending on **where conversion happens**.

### 8.1. Mapping Business Errors to HTTP Responses

In Spring MVC, **@RestControllerAdvice** together with **@ExceptionHandler** enables centralized exception handling. Example with Spring Framework 6 / Spring Boot 3:

~~~java
package com.example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(InvalidQuantityException.class)
    public ResponseEntity<ProblemDetail> handleInvalidQuantity(
            InvalidQuantityException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage()
        );
        problem.setTitle("Invalid quantity");
        return ResponseEntity.badRequest().body(problem);
    }
}
~~~

Here the message in **InvalidQuantityException** is intentionally user-safe. **Do not return ex.getMessage() of arbitrary exceptions** to clients: technical messages can leak SQL, file paths, server internals, or secrets.

| Situation | Typically Appropriate Response |
|---|---|
| Request has invalid data or structure | HTTP **400 Bad Request** describing the constraint violation. |
| Requested resource does not exist | HTTP **404 Not Found** if matching the API contract. |
| Request conflicts with current state | May use HTTP **409 Conflict**. |
| Configuration error, bug, or unexpected dependency failure | Appropriate HTTP **5xx** with detailed server-side logging. |

You cannot determine status codes solely from Java exception class names. For example, **IllegalArgumentException** might reflect bad client input or internal code calling a method improperly. In larger applications, defining dedicated business exceptions allows more accurate classification.

### 8.2. Spring Can Wrap Exceptions Across Layers

~~~text
Database driver / HTTP client
         ↓
Spring data access or client abstraction
         ↓
Service: business rules
         ↓
Controller / @RestControllerAdvice
         ↓
HTTP response
~~~

A driver may report **SQLException**, the data layer translates it to **DataAccessException**, the service translates it into a business error, and controller advice produces the response. Preserving the cause when crossing layers enables investigators to trace back to the specific failure.

## 9. Common Exceptions and Investigation Directions

An exception's name is an initial pointer to where to look, but must be combined with its message, cause, and context before concluding.

| Error Type | Initial Meaning | What to Investigate? |
|---|---|---|
| **NullPointerException** | An operation required a non-null reference but received null. | Value origin, null assumptions, first application frame. |
| **NumberFormatException** | Could not parse string into the requested numeric format. | Input content and format, out-of-range values. |
| **IllegalArgumentException** | Input violated a method's preconditions. | Who called the method and its parameter contract. |
| **IllegalStateException** | Current state is invalid for the requested operation. | Operation order, state transitions, and cause. |
| **IndexOutOfBoundsException** | Accessed an index outside valid bounds. | Boundary conditions and data size. |
| **IOException** | An I/O operation did not complete. | Files, permissions, devices, connections, or environment. |
| **ConnectException** | Could not establish a TCP connection to the target. | Host, port, target service, network, and firewall. |
| **SocketTimeoutException** | A socket operation exceeded its timeout. | Timeout settings, network health, and target service responsiveness. |
| **BeanCreationException** | Spring failed to create/configure a bean. | Bean name, constructor/factory method, and cause. |
| **UnsatisfiedDependencyException** | Spring could not satisfy a required dependency. | Which bean is missing, failing to create, or has multiple candidates. |
| **NoSuchBeanDefinitionException** | No matching bean exists in the current context. | Component scan, bean registration, auto-configuration conditions. |
| **NoUniqueBeanDefinitionException** | Multiple matching beans exist without a single choice. | Whether **@Qualifier** or **@Primary** is needed. |
| **HttpMessageNotReadableException** | Spring MVC could not read/parse the request body as expected. | JSON payload, content type, DTO, and inner conversion errors. |
| **MethodArgumentNotValidException** | Argument validation failed along the applicable binding path. | Field errors, validation annotations, and submitted data. |
| **DataAccessException** and subclasses | Error reported through Spring's data-access abstraction. | Cause from JPA, JDBC, driver, or database. |

In practice, two errors of the same class can have completely different fixes. An **IllegalStateException** when a thread accesses uninitialized state is not the same as an IllegalStateException triggered by a third-party library condition. Even **ConnectException** can be either a misconfiguration or a temporary infrastructure outage.

### 9.1. When the Application Fails to Start

Common messages:

~~~text
APPLICATION FAILED TO START
~~~

or:

~~~text
Application run failed
~~~

These are **summaries of the final startup outcome**. When reading them:

1. Find the exception reported by Spring Boot.
2. Identify the affected bean name, configuration, or web server.
3. Walk through the **Caused by:** sections.
4. Locate the concrete error: missing property, missing bean, duplicate beans of the same type, port already in use, unreachable database, or a factory method throwing an exception.
5. Cross-check against actual configuration and environment conditions.

For example, a port held by another process can prevent the embedded server from binding. In that case, **Failed to start web server** alone is not enough; the underlying cause mentioning **BindException: Address already in use** or similar points you toward checking the port.

### 9.2. When Errors Originate in Repositories and Databases

~~~text
OrderService.saveOrder()
        ↓
OrderRepository.save(...)
        ↓
JPA / JDBC / driver
        ↓
Database
~~~

Spring can translate persistence failures into an exception in the **DataAccessException** family. The cause may originate from the JDBC driver and contain specifics like constraint names, SQL states, or connection failure reasons.

A common point of confusion: with JPA, calling **save** does not necessarily write to the database immediately on that line of code; database errors sometimes appear only at **flush** or **commit** time. Consequently, the frame where the exception surfaces may be far removed from where invalid data was placed into the object. Trace the data lifecycle, transaction boundaries, and database constraints.

### 9.3. When an External API Call Fails

Distinguish at least four cases:

- **Cannot connect**: DNS, TCP, TLS, or wrong port.
- **Connected but timed out**: slow server, slow network, or too short a timeout.
- **Target server returned an HTTP error**: inspect the status and response per that service's contract.
- **Valid response but application failed to parse**: mismatched DTO, data types, date formats, or missing required fields.

Each case leads to a different investigation path. Do not lump every HTTP client exception into "the API is down".

## 10. Logging to Preserve Evidence

In a Spring Boot application, logging preserves error traces after a request ends. Log messages must carry **context**, and the exception must be passed properly to the logger.

With SLF4J:

~~~java
try {
    paymentService.charge(orderId);
} catch (PaymentProviderException ex) {
    log.error("Payment failed, orderId={}", orderId, ex);
    throw ex;
}
~~~

Passing the exception as the final argument allows the logger to print the stack trace and causes per configuration. The following loses critical information:

~~~java
log.error("Payment failed: {}", ex.getMessage());
~~~

It only records the message string and omits the Throwable object from the logger.

### 10.1. Log at the Right Boundary

An exception can traverse repository, service, controller, and exception handler layers. If every layer logs the same stack trace at ERROR level, a single failure turns into multiple noisy events that are hard to correlate. Choose the **boundary responsible for observing failures** to log it, and let inner layers rethrow or translate exceptions as needed.

Do not treat logging as having handled an error. If an application logs an error and then continues returning a success result, actual system state can become corrupted.

### 10.2. Log Useful Details Without Exposing Sensitive Data

A good message answers: **what operation**, **which object**, and **at what stage**.

~~~text
Failed to update order, orderId=ORD-1052, stage=payment-confirmation
~~~

This message is far more useful than a generic line:

~~~text
Error!
~~~

Never log passwords, API tokens, access tokens, raw SQL containing secrets, or sensitive request bodies. If a message from an external library may contain user data, consider masking or limiting what gets logged.

### 10.3. Request ID and Correlation ID

In a service handling hundreds of concurrent requests, logs interleave. A **Request ID**, **correlation ID**, or **trace ID** ties together messages from the same execution:

~~~text
2026-11-13T10:15:31Z INFO  requestId=r-102 POST /orders
2026-11-13T10:15:31Z ERROR requestId=r-102 PaymentService - Payment failed
2026-11-13T10:15:31Z INFO  requestId=r-103 GET /catalog
~~~

If work moves across thread pools, callbacks, or reactive pipelines, tracing context/MDC propagation must be explicitly handled. **Do not assume ThreadLocal automatically propagates across threads or reactive operators.**

## 11. Exception-Handling Practices That Erase Error Trails

### 11.1. Catching and Ignoring

~~~java
try {
    repository.save(order);
} catch (Exception ex) {
    // Do nothing
}
~~~

This code misleads callers into believing the order saved successfully. Without a valid recovery strategy, this simply hides failure.

### 11.2. Throwing a New Exception Without Preserving the Cause

~~~java
catch (IOException ex) {
    throw new IllegalStateException("Unable to read configuration");
}
~~~

The new exception drops the link to the IOException. A better way when changing error semantics:

~~~java
catch (IOException ex) {
    throw new IllegalStateException("Unable to read configuration", ex);
}
~~~

When no extra meaning or handling is needed, let the exception propagate per the method contract rather than wrapping it pointlessly.

### 11.3. Recreating an Exception from Only Its Message

~~~java
catch (RuntimeException ex) {
    throw new RuntimeException(ex.getMessage());
}
~~~

Here the new exception type and new stack trace obscure the original error. If you only want to pass the existing exception along:

~~~java
catch (RuntimeException ex) {
    throw ex;
}
~~~

Or remove the catch block if it adds no useful behavior.

### 11.4. Logging the Error Yet Still Reporting Success

~~~java
try {
    paymentService.charge(orderId);
} catch (RuntimeException ex) {
    log.error("Charge failed", ex);
}
return "SUCCESS";
~~~

If payment is a required step, the returned result is false. Only recover from an exception when there is a **valid fallback** and data state remains consistent.

### 11.5. Mapping Every Exception to a Single HTTP Status

Do not catch broad **Exception** and treat everything as bad input returning HTTP 400. A **NullPointerException** from a bug and an **InvalidQuantityException** from user input are two distinct situations. Choose status codes according to **business semantics and API contracts**, not merely the fact that an exception was thrown.

### 11.6. Returning Stack Traces Directly to Clients

Stack traces can reveal package layouts, file paths, table names, SQL, internal messages, or internal services. In production, external responses usually only need **status, error code, safe message, and request ID**; full stack traces belong in access-controlled logging systems.

### 11.7. Using Exceptions for All Control Flow

Not every "not found" situation requires throwing an exception. You can return **Optional.empty()**, a strongly typed result, or a normal conditional branch when the contract allows it. Overusing exceptions blurs the line between valid empty outcomes and genuine faults.

## 12. Exceptions in Multithreading and Asynchronous Processing

In synchronous calls:

~~~text
Controller → Service → Repository → Driver
~~~

the stack trace typically spans multiple layers of the call chain on the same thread.

With asynchronous processing, however:

~~~text
Thread A
  └─ HTTP Controller
       └─ Submit task
              │
              ▼
Thread B
  └─ Executor
       └─ BackgroundJob.execute()
            └─ Exception
~~~

The stack trace on Thread B may contain only the executor and the task method, **without** the controller from Thread A. With **Future**, a task error may be delivered to the caller wrapped in **ExecutionException**; with **CompletableFuture**, you may see **CompletionException**. Their causes are essential to reading the inner error.

Example:

~~~java
try {
    resultFuture.join();
} catch (java.util.concurrent.CompletionException ex) {
    Throwable cause = ex.getCause();
    // Analyze or handle according to the task's contract.
}
~~~

When investigating, check where the task was created, the inputs passed to it, logs at the execution point, and correlations across events. With **Spring WebFlux/Reactor**, stack traces can include assembly or operator info when appropriate instrumentation is enabled, yet you still need to understand how synchronous call paths differ from asynchronous pipelines.

## 13. Tools for Pinpointing Root Causes

### 13.1. Debuggers and Exception Breakpoints

IDEs usually allow setting breakpoints on a line of code or pausing whenever an exception is thrown. When paused, you can inspect arguments, local variables, object state, and the call stack.

Exception breakpoints are especially helpful when a framework catches and rewraps an exception so that logs only display a high-level error. Still, libraries occasionally throw and catch exceptions during normal flows; not every pause on **throw** is a bug to fix.

### 13.2. Reading Logs as Complete Events

Find the timestamp, request ID, and the start of the stack trace; then read continuously through all **Caused by** and **Suppressed** sections. An **ERROR** keyword might appear only on the first line while subsequent stack lines have no log-level label.

If logs appear truncated mid-trace, check formatter or log collector limits before concluding "the exception has no cause".

### 13.3. Spring Boot Diagnostics

When startup fails, Spring Boot can display a description and suggested action for supported error types. Depending on configuration, running in debug mode can also produce a **condition evaluation report**, showing why certain auto-configurations matched or did not match.

This report supplements understanding Boot configuration; it does not replace reading a specific exception's stack trace and cause.

### 13.4. Writing a Test to Capture the Failing Scenario

Once you know an input that caused an error, you can document the expected contract in a unit test. Example for the earlier service:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class OrderServiceTest {
    private final OrderService service = new OrderService();

    @Test
    void rejectsNonNumericQuantity() {
        assertThrows(
                InvalidQuantityException.class,
                () -> service.calculateTotal("abc", 100)
        );
    }
}
~~~

This test demonstrates rejecting invalid input at the service layer. If the contract also covers HTTP status and response body, the web-layer handling must be tested separately. **A test verifying only the exception class does not prove the API or logging is right.**

## 14. End-to-End Case Study: Order Creation and Database Error

Suppose a client calls the order-creation API and receives:

~~~http
HTTP/1.1 500 Internal Server Error
~~~

Server logs show an illustrative trace:

~~~text
org.springframework.dao.DataIntegrityViolationException:
could not execute statement
    at org.springframework.orm.jpa...
    at com.example.orders.OrderService.create(OrderService.java:57)
    at com.example.orders.OrderController.create(OrderController.java:24)
    ...
Caused by: org.hibernate.exception.ConstraintViolationException:
could not execute statement
    ...
Caused by: java.sql.SQLException:
duplicate key value violates unique constraint "uk_orders_external_id"
    ...
~~~

*Exact exception classes and messages vary by database, JDBC driver, ORM, and integration versions. This example only illustrates nested cause structure.*

Following the evidence:

1. **Symptom:** client receives HTTP 500 when creating an order.
2. **Outer error layer:** Spring reports a data integrity violation.
3. **Inner cause:** the database rejected the row due to a duplicate value on unique constraint **uk_orders_external_id**.
4. **Application frame:** OrderService.create near the persistence call.
5. **Questions to verify:** does that external ID already exist? Did the client retry a request? Did two requests run concurrently? Does ID generation produce duplicates? Does the constraint match business rules?
6. **Solution depends on findings:** may require idempotency handling, fixing ID generation, pre-checking conflicts, or mapping duplicate conflicts to an appropriate HTTP response.

Do not drop a unique constraint just to "make the error go away" if that constraint protects data integrity. The stack trace shows where it failed; **business contracts and data models** determine the proper fix.

### 14.1. Where an Exception Surfaces May Not Be Where Bad Data Was Created

When using JPA and transactions, the database may detect the error only at **flush** or **commit** time. Duplicate data could have been produced in an earlier step. Therefore trace the pipeline:

~~~text
HTTP input / Message
       ↓
DTO + validation
       ↓
Domain service
       ↓
ID generation / mapping
       ↓
Repository + transaction
       ↓
Database constraint
~~~

Similarly, a startup error appearing in BeanFactory can originate from a missing environment variable needed before the application context finished initializing.

## 15. Stack Trace Reading Exercises

### Scenario 1: Unable to Parse Quantity

~~~text
java.lang.IllegalArgumentException: Invalid quantity
    at com.example.orders.OrderService.place(OrderService.java:35)
    at com.example.orders.OrderController.submit(OrderController.java:19)
Caused by: java.lang.NumberFormatException: For input string: "two"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at com.example.orders.OrderService.place(OrderService.java:31)
    ... 1 more
~~~

Identify the outer exception, inner cause, and the location in application code to inspect.

**How to read it:** the outer exception is **IllegalArgumentException**; the cause is **NumberFormatException**; code inside **OrderService.place** attempted to parse the string **"two"**. Check the source of quantity data, validation, and the expected response contract for invalid input.

### Scenario 2: Missing Dependency

~~~text
org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'reportController'
    ...
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.reports.ReportGenerator' available
    ...
~~~

**How to read it:** **reportController** is the affected bean; **ReportGenerator** is the missing dependency in the application context. Check bean implementations, component scan coverage, configuration conditions, and the module providing the implementation. There is no basis to blame Spring Framework itself.

### Scenario 3: Exception While Closing a Resource

~~~text
java.lang.IllegalStateException: Failed to export
    at com.example.export.ExportService.write(ExportService.java:44)
    Suppressed: java.io.IOException: Failed to close output
        at com.example.export.ExportWriter.close(ExportWriter.java:80)
~~~

**How to read it:** the export failure is the primary exception. The IOException while closing output is a **suppressed exception**. Inspect both, but do not treat Suppressed as Caused by.

## 16. Principles to Remember

- **Read the type, message, frames, and full Caused by chain** before deciding where the fault lies.
- **Find frames in your application code** and cross-check the exact running source version, inputs, configuration, and state.
- **Distinguish where an exception occurs from what created the failing condition**; this is especially critical for bean graphs, databases, and async processing.
- **Preserve the cause when wrapping an exception** in a new business-appropriate type.
- **Catch exceptions at boundaries capable of recovering or returning a contractual response**, avoiding catch-and-ignore.
- **Do not use HTTP status codes as a substitute for reading logs**; a 500 status is only a symptom.
- **Log with context and request ID**, minimize duplicate stack traces, and never expose secrets or stack traces to end users.
- **Verify hypotheses with reproducible scenarios**, rather than silencing logs or swallowing exceptions and assuming the issue is solved.

Once you understand exceptions, stack traces, and cause chains, long log output full of **java.base**, **org.springframework**, and **org.hibernate** classes becomes analyzable evidence. You can identify the failing layer, trace the cause, find the exact bad data or configuration, and fix the component truly responsible.
