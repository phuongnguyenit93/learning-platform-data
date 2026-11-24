# onErrorMap to Convert Technical Errors into Business Errors

## 1. The Problem: Why Change the Error Type?

In a Spring WebFlux application, a service may receive **IOException** when reading data, **DataAccessException** when the database has trouble, **WebClientRequestException** when connecting to a partner fails, or **TimeoutException** from a time-bounded call. Those exceptions describe **technical** infrastructure details. Meanwhile, the business and API layers usually need to express stable semantics, such as **CatalogUnavailableException** (product catalog temporarily unavailable), **PaymentProviderUnavailableException** (cannot connect to payment service), or **ProductNotFoundException** (product does not exist).

**onErrorMap** in Project Reactor allows transforming an **onError(technicalException)** signal into **onError(domainException)** without altering the successful data of a Mono/Flux.

~~~text
Technical publisher
  |
  +-- onNext(value) ---------------> keeps value unchanged
  |
  +-- onComplete() ----------------> keeps complete unchanged
  |
  +-- onError(IOException) --------> onErrorMap
                                         |
                                  creates domain error
                                         |
                                         v
                               onError(CatalogUnavailableException)
                                         |
                                         v
                             service / controller / error handler
~~~

**Core takeaway:** onErrorMap **swaps the Throwable rather than recovering to success**. The error still terminates the subscription. This operator does not run retries on its own, does not add threads or schedulers, does not automatically return HTTP 404/503, and does not make the source keep emitting elements after the error.

Conceptual example:

~~~java
Mono<Product> result = repository.findById(id)
    .onErrorMap(DataAccessResourceFailureException.class,
        cause -> new CatalogUnavailableException(
            "Catalog temporarily unavailable", cause));
~~~

This is an **illustrative snippet** in a service: Product, repository, id, and CatalogUnavailableException must be defined, along with appropriate imports. If the repository emits DataAccessResourceFailureException, the result is the domain error; if the repository returns Mono.empty(), onErrorMap **does not run**, because there is no onError.

## 2. Reactive Streams: Error Is a Terminal Signal

Publisher/Subscriber exchange three main kinds of signals:

- **onNext(T):** delivers a successful element.
- **onComplete():** the source finishes normally.
- **onError(Throwable):** the source terminates with an error.

onComplete and onError are **two mutually exclusive ways to terminate** a subscription. After emitting onError, the source must not keep sending onNext for that subscription.

~~~text
Flux:
onNext("A") -> onNext("B") -> onError(IOException)
                                |
                            onErrorMap
                                |
onNext("A") -> onNext("B") -> onError(CatalogUnavailableException)
~~~

The two values A and B already emitted are preserved. There is no subsequent C value. This differs from **catching an exception inside a Java loop** to skip an element and continue the loop.

For a Mono with a value or Mono.empty(), the error mapper is not called because the source does not emit onError. For a Flux that errors after several values, the mapper is called when the error passes through that operator's position.

## 3. Three Overloads of onErrorMap

Both **Mono<T>** and **Flux<T>** support the following key variants:

~~~java
// Transform all errors:
onErrorMap(Function<? super Throwable, ? extends Throwable> mapper)

// Transform only errors of a matching type:
<E extends Throwable> onErrorMap(
    Class<E> type,
    Function<? super E, ? extends Throwable> mapper)

// Transform an error if a predicate matches:
onErrorMap(
    Predicate<? super Throwable> predicate,
    Function<? super Throwable, ? extends Throwable> mapper)
~~~

These are **parameter signature descriptions**, not full Java declarations; the return type will be the same Publisher type being called, Mono<T> or Flux<T>.

| Overload | Meaning | Recommendation |
| --- | --- | --- |
| **onErrorMap(mapper)** | Applies to every Throwable reaching the operator | Use when a boundary truly needs to normalize all errors; easy to accidentally wrap already-classified errors |
| **onErrorMap(Class, mapper)** | Only errors of the specified type, including matching subclasses | Prefer when the infrastructure error family is clearly identified |
| **onErrorMap(predicate, mapper)** | Only errors satisfying the condition | Use when checking type, error code, or reliable attributes |

If an error does not match the Class or predicate, the operator **lets the original error pass through**. If it matches, the mapper is invoked **synchronously** to create a new Throwable.

### 3.1. Filtering by error type

~~~java
Mono<String> result = Mono.<String>error(
        new java.io.IOException("connection failed"))
    .onErrorMap(java.io.IOException.class,
        cause -> new StorageUnavailableException(
            "Storage cannot be reached", cause));
~~~

This example snippet requires the StorageUnavailableException class. Subscribing produces **onError(StorageUnavailableException)**, not a String.

### 3.2. Using a predicate

~~~java
Mono<String> result = Mono.<String>error(
        new java.io.IOException("timed out"))
    .onErrorMap(
        error -> error instanceof java.io.IOException
                 && error.getMessage() != null
                 && error.getMessage().contains("timed out"),
        cause -> new PartnerTimeoutException(
            "Partner did not answer", cause));
~~~

The snippet above demonstrates predicate syntax; PartnerTimeoutException needs to be defined. In production, choose **exception type, error code, HTTP status, or stable data fields**. Checking only message strings as in the example can be brittle, because driver or vendor messages change across versions.

### 3.3. Avoid overusing the catch-all Throwable mapper

~~~java
Mono<String> result = networkCall()
    .onErrorMap(error ->
        new PartnerUnavailableException(
            "Partner unavailable", error));
~~~

This is an illustrative snippet. If networkCall can also emit validation errors, permission errors, or NullPointerException from a bug, this code turns **all of them** into "partner unavailable". Errors should be classified first; normally use a Class overload dedicated to specific technical errors.

## 4. Preserve the Cause for Diagnostics

A domain exception gives callers a **stable meaning**, while the original exception provides the **technical root cause** for operations. A sample class:

~~~java
public final class CatalogUnavailableException extends RuntimeException {
    public CatalogUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

When mapping:

~~~java
Mono<Catalog> catalog = repository.getCatalog()
    .onErrorMap(DataAccessResourceFailureException.class,
        cause -> new CatalogUnavailableException(
            "Catalog storage is temporarily unavailable", cause));
~~~

This is an illustrative snippet requiring repository, Catalog, and Spring DAO imports. The error chain becomes:

~~~text
CatalogUnavailableException
  message: "Catalog storage is temporarily unavailable"
  cause:
    DataAccessResourceFailureException
      cause:
        actual network / database driver error (if any)
~~~

**Do not return the entire cause chain or stack trace to the HTTP client.** Driver messages may contain SQL, hostnames, credentials, or internal data. The HTTP layer should return **contract error codes** and safe descriptions; internal logging/tracing systems retain the necessary details with a redaction policy.

If the mapper only constructs new CatalogUnavailableException("unavailable") and drops the cause, finding root causes in production becomes significantly harder. Always define a constructor taking Throwable for errors originating from infrastructure.

## 5. Distinguish "No Result" from "Could Not Retrieve Result"

Suppose a repository has the signature:

~~~java
Mono<Product> findById(String id);
~~~

There are at least three situations:

| Repository signal | Possible meaning | How to handle |
| --- | --- | --- |
| **onNext(Product) then onComplete** | Product found | Return Product to the service |
| **onComplete, no onNext** | No matching record | Use switchIfEmpty if the contract requires NotFound |
| **onError(DataAccess...)** | Data access error | Use onErrorMap to an appropriate unavailable error |

Example:

~~~java
Mono<Product> result = repository.findById(id)
    .onErrorMap(DataAccessResourceFailureException.class,
        e -> new CatalogUnavailableException(
            "Catalog storage unavailable", e))
    .switchIfEmpty(Mono.error(
        new ProductNotFoundException(id)));
~~~

The snippet above requires the application types. **Mono.empty() does not emit onError**, so onErrorMap does not turn empty into "not found". Conversely, failing to connect to the database **is not** proof that a product does not exist; do not map it to ProductNotFoundException just to return 404.

This rule is especially important in commerce APIs: returning 404 while storage is failing can cause clients to purge caches or mistakenly think a resource was deleted.

## 6. How onErrorMap Differs from onErrorResume, onErrorReturn, and doOnError

| Operator | What happens after onError? | Use case |
| --- | --- | --- |
| **onErrorMap** | Replaces Throwable with another Throwable, still terminates with error | Standardize technical -> domain errors |
| **onErrorResume** | Subscribes to a fallback Publisher, which may emit data/empty/another error | Data recovery, conditional fallback |
| **onErrorReturn** | Emits one fallback value then completes | Simple default value |
| **doOnError** | Runs a side effect, normally leaves the error unchanged | Logging, metrics, tracing |
| **onErrorComplete** | Turns selected errors into normal completion | Only when ignoring errors is allowed |
| **retry / retryWhen** | Resubscribes to the source per policy | Transient errors safe to repeat |
| **map** | Transforms successful onNext elements | Data transformation, does not handle onError |

Conceptual example:

~~~java
Mono<String> source =
    Mono.error(new java.io.IOException("offline"));

Mono<String> mapped = source.onErrorMap(
    java.io.IOException.class,
    error -> new StorageUnavailableException(
        "Storage unavailable", error));
// mapped still terminates with onError(StorageUnavailableException).

Mono<String> resumed = source.onErrorResume(
    java.io.IOException.class,
    error -> Mono.just("cached"));
// resumed emits "cached", then completes.

Mono<String> defaulted = source.onErrorReturn("default");
// defaulted emits "default", then completes.

Mono<String> observed = source.doOnError(
    error -> System.out.println("cause=" +
        error.getClass().getSimpleName()));
// observed still reports IOException.
~~~

This example is not standalone because StorageUnavailableException is not defined in the snippet. **onErrorMap is not used to return fallback data**; if you want a fallback, choose an operator with recovery semantics.

In Flux, **onErrorResume** replaces the tail of an errored stream. It does not automatically go back to the old source to process items after the error. To recover **per item**, place error handling inside the inner Publisher created by concatMap/flatMap, not solely outside the entire stream.

## 7. Complete Java 17+ Program with Concrete Output

The following example verifies four cases: success does not invoke the mapper; IOException is mapped to CatalogUnavailableException while preserving cause; a different error type passes through unchanged; a Flux emits a value before the error and a fallback after the error. No database or HTTP server is needed to run it.

Requires **JDK 17+**, **Maven 3.9+**:

~~~text
reactor-error-mapping/
  pom.xml
  src/main/java/example/OnErrorMapDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-error-mapping</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.17</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/OnErrorMapDemo.java**

~~~java
package example;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Signal;

public final class OnErrorMapDemo {
    static final class CatalogUnavailableException extends RuntimeException {
        CatalogUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        AtomicInteger mapperCalls = new AtomicInteger();

        Mono<String> healthy = Mono.fromSupplier(() -> "available")
            .onErrorMap(IOException.class, error -> {
                mapperCalls.incrementAndGet();
                return new CatalogUnavailableException("Catalog unavailable", error);
            });

        System.out.println("healthy=" + healthy.block());
        System.out.println("mapperCalls=" + mapperCalls.get());

        Mono<String> technical = Mono.fromCallable(() -> {
            throw new IOException("connection refused");
        });

        Mono<String> domain = technical.onErrorMap(
            IOException.class,
            error -> new CatalogUnavailableException(
                "Catalog service unavailable", error));

        Signal<String> signal = domain.materialize().block();
        Throwable mapped = signal.getThrowable();

        System.out.println("mapped.type=" + mapped.getClass().getSimpleName());
        System.out.println("mapped.message=" + mapped.getMessage());
        System.out.println("mapped.cause=" +
                mapped.getCause().getClass().getSimpleName());
        System.out.println("mapped.causeMessage=" +
                mapped.getCause().getMessage());

        Throwable unmatched = Mono.<String>error(
                new IllegalArgumentException("bad input"))
            .onErrorMap(IOException.class,
                error -> new CatalogUnavailableException("Storage failure", error))
            .materialize()
            .block()
            .getThrowable();

        System.out.println("unmatched.type=" +
                unmatched.getClass().getSimpleName());

        Flux<String> stream = Flux.concat(
                Flux.just("first"),
                Flux.<String>error(new IOException("stream read failed")),
                Flux.just("never"))
            .onErrorMap(IOException.class,
                error -> new CatalogUnavailableException("Read failed", error))
            .onErrorResume(CatalogUnavailableException.class,
                error -> Flux.just("fallback"));

        System.out.println("stream=" + stream.collectList().block());
    }
}
~~~

Command to run from the project directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.OnErrorMapDemo
~~~

**Lines printed by the program:**

~~~text
healthy=available
mapperCalls=0
mapped.type=CatalogUnavailableException
mapped.message=Catalog service unavailable
mapped.cause=IOException
mapped.causeMessage=connection refused
unmatched.type=IllegalArgumentException
stream=[first, fallback]
~~~

Explanation:

1. **healthy** only emits a value, so the mapper does not run and the counter is 0.
2. **Mono.fromCallable** turns the checked IOException thrown inside the Callable into an onError signal at subscription time.
3. **onErrorMap(IOException.class, ...)** changes the exception to CatalogUnavailableException while keeping IOException in **getCause()**.
4. **materialize()** turns the terminal signal into a Signal object for observation in this CLI example. You do not need materialize just to handle errors in a real application.
5. IllegalArgumentException is not an IOException, so it passes through the operator unchanged.
6. With Flux.concat, `"first"` is emitted; IOException terminates the source, onErrorMap transforms the error, and onErrorResume emits `"fallback"`. `"never"` is not emitted.

The program creates IOException intentionally so stdout is deterministic. It does not assume real-world network errors always have the message "connection refused".

## 8. Are Errors Before Creating a Mono Caught by onErrorMap?

Not necessarily. Look at the code:

~~~java
Mono<String> source = Mono.just(blockingOrThrow())
    .onErrorMap(e -> new StorageUnavailableException("failed", e));
~~~

Java evaluates **blockingOrThrow() first** before calling Mono.just. If the method throws an exception immediately, the Mono **has not been created yet**, so there is no pipeline for onErrorMap to handle.

Move the call into a lazy factory:

~~~java
Mono<String> source = Mono.fromCallable(() -> blockingOrThrow())
    .onErrorMap(java.io.IOException.class,
        e -> new StorageUnavailableException("failed", e));
~~~

Both snippets are **illustrative code** because blockingOrThrow and StorageUnavailableException must be declared. With fromCallable, an error thrown at subscribe time is turned into onError and passes through onErrorMap.

**WebFlux note:** "lazy" does not mean "non-blocking". If blockingOrThrow actually blocks a thread with JDBC or synchronous file I/O, use non-blocking drivers/APIs when appropriate, or isolate blocking work on a suitable bounded Scheduler (such as boundedElastic).

## 9. Spring WebFlux: From Domain Exception to HTTP Response

**A domain exception does not turn into an HTTP status by itself.** For the client to receive a 503 response when the catalog is unavailable, you need an **HTTP boundary** handling CatalogUnavailableException. You can use @RestControllerAdvice, @ExceptionHandler, ResponseStatusException, or ErrorResponse/ProblemDetail mechanisms.

### 9.1. Service only understands business semantics

~~~java
@Service
public class CatalogService {
    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> findProduct(String id) {
        return repository.findById(id)
            .onErrorMap(DataAccessResourceFailureException.class,
                cause -> new CatalogUnavailableException(
                    "Catalog temporarily unavailable", cause))
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)));
    }
}
~~~

This is **illustrative code in a Spring Boot WebFlux project**; it cannot run standalone because Product, CatalogRepository, the two domain exceptions, and imports are still required. The key point is **distinguishing database access errors from empty results**:

- If Product exists, emits Product.
- If not found and the repository completes empty, switchIfEmpty emits ProductNotFoundException.
- On DataAccessResourceFailureException, onErrorMap emits CatalogUnavailableException.
- Other non-matching errors pass through with their original type unless another operator handles them.

### 9.2. Controller advice selects status and body

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DomainErrorAdvice {
    @ExceptionHandler(CatalogUnavailableException.class)
    public ResponseEntity<ProblemDetail> unavailable(
            CatalogUnavailableException error) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Catalog temporarily unavailable");
        problem.setTitle("Catalog is unavailable");

        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }
}
~~~

This class works in a Spring WebFlux project when CatalogUnavailableException is present and imported, and component scanning finds the advice. ProblemDetail creates a standardized response body; ResponseEntity explicitly sets status 503. A separate handler for ProductNotFoundException is needed if the API requires HTTP 404.

Do not return raw technical exceptions or stack traces in JSON. You can add a **public error code** and correlation ID when policy permits, keeping the cause in internal logs.

### 9.3. ResponseStatusException at the controller boundary

~~~java
Mono<Product> response = catalogService.findProduct(id)
    .onErrorMap(CatalogUnavailableException.class,
        cause -> new ResponseStatusException(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Catalog temporarily unavailable", cause));
~~~

This is an illustrative controller snippet with the relevant service and types. ResponseStatusException ties an error to an HTTP status, but the service/domain core should not depend on HTTP if it also serves message consumers, batch jobs, or CLIs. Using advice is convenient when a centralized error policy is desired.

**Streaming Flux case:** if WebFlux has already written HTTP headers and some parts of the response body, and the Flux emits onError afterward, the framework cannot always replace an already-committed response with a 503 and a full ProblemDetail body. onErrorMap does not rewind bytes already sent. For streaming, design an appropriate error protocol/contract and commit point.

## 10. How to Classify Errors When Using WebClient

When calling external APIs, errors should not all be lumped together:

| Type | Example | What to consider |
| --- | --- | --- |
| **WebClientRequestException** | Cannot open connection, network problem | May need PartnerUnavailableException; pay attention to cause |
| **WebClientResponseException** | Server returns an HTTP error status via default retrieve | Inspect status: 404, 401, 403, 429, 5xx have different meanings |
| **TimeoutException** | Timeout emitted by an operator or another layer | Classify based on timeout location and actual error type |
| **Already-created domain exception** | PartnerRejectedException, OrderConflictException | Do not re-wrap as "unavailable" if it already has the right meaning |

Adapter example:

~~~java
Mono<PartnerPayload> payload = webClient.get()
    .uri("/partner/{id}", partnerId)
    .retrieve()
    .bodyToMono(PartnerPayload.class)
    .onErrorMap(WebClientRequestException.class,
        cause -> new PartnerUnavailableException(
            "Cannot reach partner", cause));
~~~

This is an illustrative snippet requiring definitions for WebClient, PartnerPayload, PartnerUnavailableException, and partnerId. For HTTP 404, 429, or 5xx errors, you can classify via **onStatus** during retrieve or a predicate on WebClientResponseException based on **status code**. Do not assume every 4xx/5xx is a transient retryable error; 401/403 are usually permission issues, 429 can involve quotas and Retry-After, and 404 can mean the resource does not exist per contract.

## 11. Operator Ordering Affects the Result

Consider two chains, assuming source is a Mono<String> emitting IOException:

~~~java
Mono<String> first = source
    .onErrorMap(IOException.class,
        e -> new CatalogUnavailableException("Storage down", e))
    .onErrorResume(CatalogUnavailableException.class,
        e -> Mono.just("cached"));
~~~

Here onErrorMap changes the error to CatalogUnavailableException, then onErrorResume **matches the new error** and emits `"cached"`.

~~~java
Mono<String> second = source
    .onErrorResume(CatalogUnavailableException.class,
        e -> Mono.just("cached"))
    .onErrorMap(IOException.class,
        e -> new CatalogUnavailableException("Storage down", e));
~~~

Here onErrorResume receives IOException before it is mapped, so it **does not match**, and the trailing onErrorMap converts the type; the result is still onError(CatalogUnavailableException), with no cached value.

Both snippets need the corresponding classes and application variables, so they are illustrative examples. Ordering matters similarly with retryWhen:

~~~text
source -> onErrorMap(IOException -> DomainException) -> retryWhen(filter IOException)
                         |
                 retry sees DomainException,
                 IOException filter may not match
~~~

If you place retry before mapping, you must watch out for **retry exhaustion**: RetrySpec may emit a wrapper error when retries are exhausted, causing a subsequent onErrorMap(IOException.class, ...) to no longer match the original error. Designing a retry policy requires testing immediate source failure, retry success, retry exhaustion, and non-retryable errors; sometimes you need to configure how the final error is emitted.

Retry creates **new subscriptions** to the retried portion of the source, which can repeat network calls or side effects. Do not automatically retry payment, email-sending, or data-writing operations without idempotency mechanisms and deadlines.

## 12. Recovering Errors Per Element Individually

With a multi-element Flux, placing a single error handler **outside the whole pipeline** and returning a fallback does not mean continuing all inputs after the error.

~~~java
Flux<String> result = Flux.just("ok", "bad", "later")
    .concatMap(value -> callOne(value))
    .onErrorResume(CatalogUnavailableException.class,
        e -> Flux.just("fallback"));
~~~

If callOne("bad") emits a terminal error, the outer source may stop before processing `"later"`. If business logic needs to **skip/recover each record** while still continuing later records, put recovery on the inner Publisher:

~~~java
Flux<String> result = Flux.just("ok", "bad", "later")
    .concatMap(value ->
        callOne(value).onErrorResume(
            CatalogUnavailableException.class,
            e -> Mono.just("failed:" + value)));
~~~

Both examples are **illustrative snippets**, where callOne(String) must be a method returning Mono<String>. In the second pattern, an individual inner error can recover into a value and concatMap still gets to process `"later"`. If an inner emits another uncaught error, the whole stream can still terminate.

**onErrorMap only swaps the error**; "continuing per element" is a separate design decision that cannot be solved merely by changing the terminal Throwable.

## 13. Classifying Business Errors to Choose HTTP Statuses

An example contract table for a catalog/order API:

| Situation | Domain exception | Suggested HTTP status | Explanation |
| --- | --- | --- | --- |
| No product for ID | ProductNotFoundException | 404 | Resource does not exist |
| Cannot access data store | CatalogUnavailableException | 503 | Dependency temporarily unavailable |
| Invalid request | InvalidQueryException | 400 | Client needs to fix input |
| Insufficient permissions | PermissionDeniedException | 403 | Not authorized |
| Conflicting order state | OrderStateConflictException | 409 | Business rule blocks the action |
| Unexpected bug/exception | Unexpected server error | 500 | Must not be disguised as 404 or 400 |

This table is **for guidance** and must follow the specific API contract. A business exception does not have to match the public error code in class name; you can use stable codes like CATALOG_UNAVAILABLE or PRODUCT_NOT_FOUND.

Do not map a **database IOException** into ProductNotFoundException. When data cannot be accessed, the service **does not know** whether the product exists or not.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking onErrorMap returns fallback data | Stream still errors | Use onErrorResume or onErrorReturn |
| Mapping all Throwables to "unavailable" | Hides bugs, permission errors, validation errors | Choose a sufficiently narrow Class/predicate |
| Dropping the technical exception cause | Loses trail of root cause | new DomainException(message, cause) |
| Returning full cause/stack trace over HTTP | Can leak SQL, tokens, hostnames | Return safe public code/detail; log internally |
| Thinking Mono.empty is an error to map | Mapper does not run | Use switchIfEmpty when not found is needed |
| Expecting Flux to keep running after onErrorMap | Error is still terminal | Recover the inner Publisher when per-item is needed |
| Mapping a domain exception a second time into another error | Loses accurate classification | Map at technical boundaries, use filters |
| Turning a database timeout into 404 | Client thinks data does not exist | Distinguish missing vs unavailable |
| Placing onErrorResume before onErrorMap and expecting it to catch the new type | Handler does not match | Order operators along the signal flow |
| Retrying after mapping with a filter that only accepts technical errors | Filter may miss the domain error | Design ordering and handle retry exhausted |
| Calling a throwing function before Mono.just | Error occurs before pipeline | Use fromCallable or defer in the right place |
| Mapper returns null or throws another unexpected error | Loses intended semantics | Return a valid Throwable and write tests |
| Logging the same error at too many layers | Duplicate logs and hard investigation | Pick a primary logging layer, keep correlation ID |
| Using onErrorMap to pick 503 without configuring an HTTP handler | Desired status mapping is missing | Use @ExceptionHandler or ResponseStatusException |

Avoid turning fatal errors or corrupted-program-state errors into ignorable business errors. The goal is to preserve **accurate error classification**, not to hide every incident under one generic message.

## 15. Testing Both Signals and Causes

Branches that should be verified:

1. Successful source: mapper is not called, value is preserved.
2. Source with matching error: downstream receives the exact domain exception.
3. Cause chain: getCause() points to the original Throwable.
4. Non-matching error: original exception passes through unchanged.
5. Mono.empty: mapper does not run; if switchIfEmpty is present, empty is handled separately.
6. Flux emitting some elements then erroring: values before the error still reach downstream, then it terminates.
7. Recovery and retry: test each operator order and retry exhaustion.
8. HTTP boundary: verify exact status/body and no leakage of infrastructure data.

With **reactor-test**, you can use StepVerifier:

~~~java
IOException original = new IOException("disconnected");

Mono<String> mapped = Mono.<String>error(original)
    .onErrorMap(IOException.class,
        e -> new CatalogUnavailableException(
            "Catalog unavailable", e));

StepVerifier.create(mapped)
    .expectErrorMatches(error ->
        error instanceof CatalogUnavailableException
        && error.getCause() == original
        && "Catalog unavailable".equals(error.getMessage()))
    .verify();
~~~

This is an **illustrative test snippet**, requiring the **io.projectreactor:reactor-test** dependency compatible with reactor-core, importing IOException, Mono, StepVerifier, and the CatalogUnavailableException class; it runs inside a JUnit test method. It is not a standalone class. With WebFlux, WebTestClient helps verify mapping from domain exceptions to HTTP 404/503 and ProblemDetail in controllers/advice.

## 16. Self-Check Questions

**1.** A Mono emits a value and completes; does onErrorMap invoke the mapper?

**No.** The mapper only runs when a matching onError signal occurs.

**2.** A repository returns Mono.empty() for a non-existent ID. Can you use onErrorMap(IOException.class, ...) to return 404?

**No.** Empty is an empty completion, not onError. Use switchIfEmpty(Mono.error(...)) and map the domain NotFound to 404 at the HTTP boundary.

**3.** When IOException is mapped to CatalogUnavailableException, where should the original exception live?

In the **cause** of the new exception, so internal diagnostics remain possible.

**4.** Does onErrorMap turn an error into the value "cached"?

**No.** Use onErrorResume with Mono.just("cached") when a fallback is a valid policy.

**5.** A Flux emits A, B and then errors. Does onErrorMap automatically emit C from the old source?

**No.** A terminal error ends that subscription. If per-element processing is needed, design recovery inside the inner Publisher.

**6.** Does mapping by IOException.class alter an IllegalArgumentException?

**No**, unless the actual error is a compatible subclass of the specified type (which is not the case for IllegalArgumentException).

**7.** Does creating CatalogUnavailableException in a service automatically make HTTP return 503?

**No.** Mapping at the HTTP boundary is required via advice, ResponseStatusException, or an equivalent mechanism.

**8.** Why shouldn't every Throwable be mapped to PartnerUnavailableException?

Because it can mask bugs, authentication errors, validation errors, and domain errors that already have accurate meaning.

**9.** When retryWhen comes after onErrorMap, what can happen to a filter that only accepts IOException?

The filter may receive the new domain exception and fail to match. If you place retry before mapping, you must also handle the exhausted-retries wrapper.

**10.** Why shouldn't driver messages/stack traces be returned in the response?

Because of the risk of leaking internal/sensitive information. APIs should only return safe error codes and descriptions, keeping diagnostics in protected logging systems.

## 17. References

- [Project Reactor 3.6.17: Mono.onErrorMap](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html) — three overloads and error signal transformation semantics.
- [Project Reactor 3.6.17: Flux API](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html) — onErrorMap on Flux.
- [Project Reactor Reference Guide: Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — comparing error mapping, fallback, and retry.
- [Spring WebFlux exception handling](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-exceptions.html) — @ExceptionHandler and @ControllerAdvice.
- [Spring WebFlux error responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html) — ProblemDetail and ErrorResponse.
- [Spring ResponseStatusException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ResponseStatusException.html) — exception carrying an HTTP status.

**Remember:** **onErrorMap synchronously replaces an onError signal containing a technical error with an onError containing a business error**, giving services clear contracts with less infrastructure coupling. It **does not produce fallback data, does not automatically retry, does not continue the source after an error, and does not decide HTTP status on its own**. Filter errors to the right scope, preserve the cause, distinguish empty sources from technical errors, verify operator ordering, and use a dedicated HTTP handler to return safe information to clients.