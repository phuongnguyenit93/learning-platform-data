# Avoiding Blocking Queries or Operations in Spring WebFlux Converters and Validators

## 1. Why Is This Critical in WebFlux?

**Spring WebFlux** is designed for asynchronous I/O with a reactive model (`Mono`/`Flux`), typically running on a bounded number of event-loop threads when using Reactor Netty. One event-loop thread can serve many connections/requests. If it must **wait** on a JDBC query, a synchronous HTTP call, `Thread.sleep(...)`, or `Mono#block()`, many other requests sharing that thread slow down as well.

One place easily overlooked is a **type converter** or **validator** invoked automatically by the framework while processing HTTP inputs:

- Converters transform `String` from query/path/header/form into enums, IDs, date/time types, or value objects.
- Validators check `@Valid`/`@Validated`, `@NotBlank`, `@Size`, custom constraint rules, or form objects.
- Standard converter/validator APIs have **synchronous contracts**. They have nowhere to return a `Mono` and await databases/networks reactively.
- In WebFlux, these callbacks can execute on the thread serving the reactive request pipeline, including the event loop. You must never assume the framework always shifts them onto a worker thread safe for blocking I/O.

**Core rule:** **converters and validators should only perform local, short, non-blocking checks/conversions**. When a rule requires querying a database, fetching data from another API, or significant I/O, implement it in the **service layer using reactive composition** after inputs are parsed and structurally validated.

This lesson explains the boundary between type conversion, Bean Validation, and asynchronous business checks, how to handle legacy blocking APIs, and how to test on Java 17+ / Spring Boot WebFlux.

## 2. Three Contracts Commonly Confused with Async Operations

| Component | Method / Contract | Result | Suitable Work | What Not to Do |
| --- | --- | --- | --- | --- |
| Spring `Converter<S,T>` | `T convert(S source)` | A direct `T` | String parsing, enum/ID mapping, input normalization/canonicalization. | JDBC/JPA lookups, REST API calls, file/network reads, lock waits. |
| Spring `Validator` | `void validate(Object target, Errors errors)` | Records errors synchronously into `Errors` | Fast CPU-only field/cross-field checks. | I/O lookups to see if a value exists, `Future#get`, `sleep`. |
| Jakarta `ConstraintValidator<A,T>` | `boolean isValid(T value, ConstraintValidatorContext context)` | Synchronous `true/false` | Pure data constraints: length, pattern, date comparisons. | `reactiveRepository.exists(...).block()`, `WebClient...block()`. |
| Reactive service/repository | `Mono<T>`, `Flux<T>`, `flatMap` | Publisher subscribed later | R2DBC lookups, WebClient calls, availability checks, I/O business logic. | Calling `.block()` to force a synchronous value. |
| Legacy blocking adapter | `Mono.fromCallable(...).subscribeOn(boundedElastic())` | Publisher running source on a blocking-dedicated worker | Temporary bridge for APIs lacking non-blocking versions. | Placing blocking calls directly inside converters/validators. |

These signatures dictate the architecture:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}

// Jakarta Validation:
public interface ConstraintValidator<A extends Annotation, T> {
    boolean isValid(T value, ConstraintValidatorContext context);
}
~~~

These are **simplified snippets to explain the contracts**, not verbatim copies of the original interfaces, which carry additional metadata/default methods or bounds. The key point is that none of these conversion/validation methods **return `Mono` or `Flux`**.

### Type conversion vs domain validation

For example, an endpoint receiving `@RequestParam("plan") Plan plan`:

- **Type conversion**: `"pro"` → `Plan.PRO`; `"unknown"` → conversion error.
- **Bean Validation**: `@NotBlank`/`@Min` or a custom constraint validating the already-present input value.
- **I/O-bound domain rule**: "Is the current user authorized for `Plan.PRO`?" or "Does this registration name already exist in the database?" → belongs in a reactive service after binding.

Do not stuff permission or DB queries into a converter just because Spring is converting `String` into `Plan`/`UserId`. **Converting an `id` into a value object does not mean loading the entity from a database**.

## 3. What Happens When Blocking the Event Loop?

Proper request processing diagram:

~~~text
HTTP request
   |
   v
WebFlux argument resolution / bind / validate   [fast, synchronous, no I/O]
   |
   v
Controller receives typed DTO/argument
   |
   v
Reactive service: repository.exists(...) / WebClient...   [non-blocking]
   |
   v
flatMap / map / switchIfEmpty / onErrorResume
   |
   v
HTTP response
~~~

Bad flow:

~~~text
HTTP request
   |
   v
Converter or ConstraintValidator
   |
   +-- JDBC query / RestTemplate / Thread.sleep / future.get()
   |      |
   |      +-- Processing thread is held WAITING
   |
   v
Controller (only runs after waiting finishes)
~~~

Blocking the event loop can cause:

1. **Increased tail latency**: one request waiting on I/O delays other connections sharing the same thread.
2. **Reduced throughput** as event-loop threads sit idle waiting instead of handling network events.
3. **Misplaced queueing/backpressure**: instead of coordinating via reactive publishers, synchronous code pins threads.
4. **Cascading timeouts**, holding connections open and inflating pending requests when upstream stalls.
5. **Harder diagnostics** because stack traces point to a converter/validator while the real culprit is misplaced I/O.

Reactor marks certain threads as **non-blocking**. Calling APIs like `Mono#block()` or `Flux#blockFirst()` on a `NonBlocking`-marked thread typically throws `IllegalStateException` ("blocking is not supported"). However, **not every blocking call throws automatically**: `Thread.sleep`, JDBC, or locks can silently occupy the thread. Therefore **"no exception" does not prove code is safe**.

**Do not assert that every WebFlux request always runs on exactly one event-loop thread.** Schedulers, security, custom operators, adapters, and server runtimes can switch execution contexts. Design must remain safe whenever callbacks run on the event loop.

## 4. Anti-Pattern in `Converter`: Using a Parser as a Repository

Example assuming `BlockingUserRepository`:

~~~java
// WRONG — illustrative snippet, not a complete file.
public final class BadUserConverter
        implements Converter<String, User> {

    private final BlockingUserRepository repository;

    public BadUserConverter(BlockingUserRepository repository) {
        this.repository = repository;
    }

    @Override
    public User convert(String idText) {
        long id = Long.parseLong(idText);
        return repository.findById(id).orElseThrow(); // BLOCKING!
    }
}
~~~

**The problem:** merely declaring `@PathVariable User user` or `@RequestParam User user` with this converter triggers entity loading **during argument resolution**, before the controller orchestrates asynchronous processing. Never use type conversion to read mutable state, verify permissions, or query databases.

### Fix: converter creates a value object, service performs lookup

~~~java
public record UserId(long value) {
    public UserId {
        if (value <= 0) {
            throw new IllegalArgumentException("ID must be positive");
        }
    }
}

public final class UserIdConverter
        implements Converter<String, UserId> {

    @Override
    public UserId convert(String text) {
        return new UserId(Long.parseLong(text));
    }
}
~~~

This is **logically self-contained Java**, needing imports and Spring converter registration to work with WebFlux. `UserIdConverter` performs no I/O—it only parses and constructs the value object. The reactive repository is called after `UserId` exists:

~~~java
@GetMapping("/users/{id}")
public Mono<UserView> findUser(@PathVariable("id") UserId id) {
    return userService.findById(id);
}
~~~

The snippet assumes `userService.findById(UserId)` returns `Mono<UserView>`. The service can use R2DBC or WebClient to look up data without blocking:

~~~java
public Mono<UserView> findById(UserId id) {
    return reactiveRepository.findById(id.value())
            .map(entity -> new UserView(entity.id(), entity.name()));
}
~~~

`UserView`/`reactiveRepository` are assumed in this architectural example; it is not a full program. **Do not make `Mono<User>` the target of `Converter<String,User>`**, as that return type does not fit Spring's ConversionService contract.

### What is safe to do inside a converter

- `String.trim()`, small alias normalization, format checks.
- `Long.parseLong`, `UUID.fromString`, `LocalDate.parse` with explicit format/locale.
- Enum mapping via `switch` or immutable `Map`, with zero I/O.
- Creating value objects with local invariants.

A converter can still slow down the event loop if it executes heavy CPU work (catastrophic regex backtracking on unbounded input, huge encryption/decryption, massive loops). **"No I/O" is not enough if computation is overly CPU-intensive**; bound input sizes and keep conversions fast with predictable complexity.

## 5. Anti-Pattern in `ConstraintValidator`: Checking Uniqueness via DB

Suppose a DTO has a custom annotation `@UsernameAvailable`. A common yet dangerous implementation:

~~~java
// WRONG — snippet intentionally illustrating a design flaw, not standalone.
@Override
public boolean isValid(
        String username, ConstraintValidatorContext context) {

    if (username == null || username.isBlank()) {
        return true;
    }

    Boolean exists =
            reactiveUserRepository.existsByUsername(username).block();
    return !Boolean.TRUE.equals(exists);
}
~~~

**Why is this wrong?**

1. `ConstraintValidator#isValid(...)` returns `boolean` **immediately**, not `Mono<Boolean>`. `.block()` forces an event-driven lookup into a synchronous wait.
2. Validators can be invoked by the Spring/Jakarta engine while processing `@Valid @RequestBody`, `@ModelAttribute`, or method validation; that is no place to block waiting on a query.
3. Calling `.block()` on a Reactor non-blocking thread can throw `IllegalStateException`; on other workers it might not throw yet still destroys concurrency and risks thread exhaustion.
4. Checking "username does not exist yet" **cannot guarantee uniqueness at write time**: two concurrent requests can both pass the check and then insert. The database must still enforce a **unique constraint/index**.
5. If the DB is slow or down, the validator can fail with an infrastructure error instead of "invalid username". Never disguise a DB failure as a normal constraint state via `catch (Exception) { return true; }`.

Swapping `.block()` for another reactive helper inside `isValid` still fails if you must return a boolean before the query completes. `@Async` on `isValid` does not turn a boolean signature into an async contract; calling `subscribe()` manually and returning `true` creates a **race condition**, letting the request proceed before the check even finishes.

### Right approach: separate syntax checks from async lookups

In the DTO, use Bean Validation for rules **computable from the input itself**:

~~~java
public record RegistrationInput(
        @NotBlank
        @Size(max = 40)
        @Pattern(regexp = "[a-zA-Z0-9_]+")
        String username,

        @Min(18)
        int age) {
}
~~~

This is an illustrative DTO with appropriate Jakarta Validation imports. Once the DTO is bound/validated, the service checks username availability via reactive lookup:

~~~java
public Mono<RegistrationOutcome> register(RegistrationInput input) {
    return userRepository.existsByUsername(input.username())
            .flatMap(exists -> {
                if (exists) {
                    return Mono.just(
                            RegistrationOutcome.USERNAME_TAKEN);
                }
                return userRepository.insertNew(input)
                        .thenReturn(RegistrationOutcome.CREATED);
            });
}
~~~

This snippet assumes a reactive repository and `RegistrationOutcome` enum exist. Crucial point: both lookup and insert live inside the **reactive chain** subscribed by WebFlux; `.block()` is never called. **Authoritative uniqueness must still be enforced by the DB**: if an insert hits a unique index violation due to a race, catch the duplicate-key error at the persistence layer and map it to an appropriate business response (typically 409 Conflict). Pre-checks only improve UX early; they never replace DB constraints.

If "username must not already exist" is a business validation rule, name it clearly (e.g., `UsernameAvailabilityService`) and design an explicit response; do not cram an async query into a custom `ConstraintValidator` just to emit a default field error.

## 6. Spring `Validator` Is Also Synchronous

Spring provides the interface:

~~~java
public final class RegistrationValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationInput.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationInput input = (RegistrationInput) target;

        if (input.username() != null
                && input.username().length() > 40) {
            errors.rejectValue("username", "tooLong");
        }
    }
}
~~~

This is a **snippet** requiring matching imports and `RegistrationInput`. The logic runs locally without I/O. The `validate(..., Errors)` contract returns `void`, so it cannot `return Mono<Void>` or await external APIs without blocking threads.

When checking multiple fields within a DTO—such as `startDate <= endDate`—a Spring `Validator` or custom class-level Bean Validation constraint fits well **since all required data is already inside the object**. If DB/network access is needed, move it to the reactive service.

**Note on nulls:** local custom validators should handle nulls explicitly so they do not throw `NullPointerException` at the infrastructure layer. In Bean Validation, `@NotNull`/`@NotBlank` normally catch missing values while other constraints avoid duplicate errors; that is a design convention, not guaranteed for every custom constraint.

## 7. Safe Pipeline: `map` for Pure Data Work, `flatMap` for I/O

A typical WebFlux pipeline:

~~~java
@PostMapping("/signup")
public Mono<ResponseEntity<SignupResult>> signup(
        @Valid @RequestBody Mono<SignupRequest> request) {

    return request
            .map(this::normalizeFast)        // light CPU, non-blocking
            .flatMap(signupService::create) // async DB/WebClient...
            .map(result -> ResponseEntity
                    .status(HttpStatus.CREATED).body(result));
}
~~~

This snippet assumes supporting classes/services. `normalizeFast` only transforms local text; `signupService.create` must be genuinely asynchronous, e.g., using Spring Data R2DBC/WebClient, not calling JDBC and wrapping with `Mono.just(...)`.

**Distinguishing operators:**

- `map(fn)`: `fn` receives one value and returns a value immediately. Use for pure/lightweight work. Writing `.map(value -> legacyDao.load(value))` is still blocking if `legacyDao.load` waits on I/O.
- `flatMap(fn)`: `fn` returns `Mono<R>` and the reactive chain composes the async result without `.block()`.
- `Mono.defer(...)`/`Mono.fromSupplier(...)`: defers execution until subscription time; **does not move code to another thread** and **does not turn blocking operations into non-blocking ones**.
- `subscribeOn(scheduler)`: specifies the scheduler for source subscription/upstream; use properly when bridging blocking legacy code.
- `publishOn(scheduler)`: switches execution context for **downstream** operators after it; cannot undo blocking that already occurred upstream.
- `onErrorResume`: handles pipeline errors under explicit policies; never swallow infrastructure failures with `onErrorReturn(true)` during permission/uniqueness checks.
- `timeout(...)`: bounds wait time on a reactive publisher; does not necessarily abort driver-level blocking I/O already in flight.

Never call `subscribe()` manually inside a controller to "run a check in the background" and immediately return a response; the framework subscribes to the publisher **returned** from the handler. Manual subscriptions lose error propagation, cancellation, and request lifecycle tracking.

## 8. Necessary Bridge for Legacy Blocking APIs: `boundedElastic`

Not every project has reactive repositories/drivers. If you must call JDBC, JPA, synchronous SDKs, or blocking file I/O in a WebFlux flow, **isolate blocking work off the event loop**, never hiding it inside converters/validators.

### Recommended Reactor pattern

~~~java
public Mono<Boolean> usernameExists(String username) {
    return Mono.fromCallable(
            () -> blockingUserDao.existsByUsername(username))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

This snippet is for an adapter with an injected `blockingUserDao`. `Mono.fromCallable` defers invoking the DAO until subscription, while `subscribeOn(Schedulers.boundedElastic())` runs the **source** on a scheduler built for blocking tasks. `boundedElastic` caps threads/queues to avoid unbounded thread creation.

**Misleading wrong versions:**

~~~java
public Mono<Boolean> wrongEager(String username) {
    // DAO already blocked BEFORE creating Mono!
    return Mono.just(blockingUserDao.existsByUsername(username));
}

public Mono<Boolean> wrongDeferred(String username) {
    // Defers execution time but still runs on the subscriber thread.
    return Mono.fromCallable(
            () -> blockingUserDao.existsByUsername(username));
}
~~~

Both are **anti-pattern snippets** when callers may execute on the event loop; the second is only safe if subscribed on a blocking-capable scheduler prior to execution. Never assume a `Mono` return type automatically guarantees non-blocking behavior.

**Cost of bridging:** the legacy API still holds a thread while waiting on I/O. `boundedElastic` is a **temporary isolation measure**, not a magic reactive upgrade for JDBC. Under higher load, thread/queue/connection pools saturate and require monitoring; migrate to R2DBC/reactive SDKs when architecture and requirements permit.

### Place the scheduler at the right boundary

~~~java
Mono.fromCallable(() -> blockingUserDao.existsByUsername(username))
        .subscribeOn(Schedulers.boundedElastic())
        .map(exists -> exists ? "taken" : "free");
~~~

Note: placing `publishOn(boundedElastic())` **after** `.map(x -> blockingCall())` cannot rescue a blocking call that already ran. Similarly, if a controller invokes a converter before returning a `Mono`, you cannot offload that converter to `boundedElastic` by putting `subscribeOn` **at the end of the controller body**.

Never create `Schedulers.newBoundedElastic(...)` per request; use shared or lifecycle-managed schedulers to prevent thread/queue leaks. Whenever a native reactive driver is viable, prefer it over bridging.

## 9. Runnable Example: Spring Boot 3.x + Java 17+ WebFlux

The example below demonstrates a **fully synchronous, purely local converter**, **Bean Validation inspecting only the DTO**, and a **reactive service boundary** checking "username taken" outside the validator.

To run **without a database**, `DemoUsernameLookup` returns a `Mono<Boolean>` backed by an **immutable in-memory set**, intentionally performing no I/O. In production, swap only that implementation with real R2DBC/WebClient; **do not swap in JDBC inside `Mono.fromSupplier` and call it non-blocking**.

### 9.1. Maven dependencies

Create a **Spring Boot 3.x**, **Java 17+**, Maven project (parent or BOM managing versions). Include only the WebFlux starter without the MVC starter so the web application type does not switch:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Add the following files under `src/main/java/com/example/nonblocking/` and tests under `src/test/java/com/example/nonblocking/`. Each public top-level type matches its filename and uses the Jakarta namespace.

### 9.2. `NonBlockingApplication.java`

~~~java
package com.example.nonblocking;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NonBlockingApplication {

    public static void main(String[] args) {
        SpringApplication.run(NonBlockingApplication.class, args);
    }
}
~~~

### 9.3. `AccountTier.java`

~~~java
package com.example.nonblocking;

public enum AccountTier {
    BASIC,
    PREMIUM
}
~~~

### 9.4. `ConversionConfig.java`: converter with no I/O

~~~java
package com.example.nonblocking;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import java.util.Locale;

@Configuration
public class ConversionConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, AccountTier.class,
                raw -> switch (raw.trim().toLowerCase(Locale.ROOT)) {
                    case "basic", "b" -> AccountTier.BASIC;
                    case "premium", "p" -> AccountTier.PREMIUM;
                    default -> throw new IllegalArgumentException(
                            "Unknown tier");
                });
    }
}
~~~

Spring WebFlux picks up the converter via `WebFluxConfigurer#addFormatters`. Here `convert` only trims, lowercases, and maps the enum. It can run concurrently across requests without holding mutable state. If input is not a valid alias, the conversion exception triggers an argument binding failure, typically HTTP 400. Note `String.trim()` is tiny local work with zero DB or network dependency.

### 9.5. `DemoUsernameLookup.java`: mock reactive repository

~~~java
package com.example.nonblocking;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

import java.util.Locale;
import java.util.Set;

@Component
public class DemoUsernameLookup {

    private static final Set<String> TAKEN =
            Set.of("taken", "reserved");

    public Mono<Boolean> exists(String username) {
        return Mono.fromSupplier(() ->
                TAKEN.contains(
                        username.toLowerCase(Locale.ROOT)));
    }
}
~~~

The immutable `Set` is just demo data; the in-memory lookup is instant and safe on request threads. `Mono.fromSupplier` **does not make code inside it asynchronous**; here none is needed because there is no I/O. When backed by a DB, use a reactive repository:

~~~java
// Architectural snippet, not a standalone Java file.
public Mono<Boolean> exists(String username) {
    return reactiveUserRepository
            .existsByUsername(username);
}
~~~

With Spring Data R2DBC, both repository and driver must be truly reactive. Never wrap a blocking JPA repository in `Mono.fromSupplier` without isolating it as in section 8.

### 9.6. `SignupController.java`: bind/validate then look up in Mono

~~~java
package com.example.nonblocking;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class SignupController {

    private final DemoUsernameLookup lookup;

    public SignupController(DemoUsernameLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping("/tier")
    public String tier(@RequestParam("value") AccountTier value) {
        return "TIER:" + value;
    }

    @PostMapping(
            path = "/signups",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<SignupReply>> signup(
            @Valid @RequestBody Mono<SignupRequest> body) {

        return body.flatMap(request ->
                lookup.exists(request.username())
                        .map(taken -> taken
                                ? ResponseEntity.status(
                                        HttpStatus.CONFLICT)
                                        .body(new SignupReply(
                                                "username_taken"))
                                : ResponseEntity.status(
                                        HttpStatus.CREATED)
                                        .body(new SignupReply(
                                                "created"))));
    }

    public record SignupRequest(
            @NotBlank String username,
            @Min(18) int age) {
    }

    public record SignupReply(String status) {
    }
}
~~~

**Flow explanation:**

1. `GET /api/tier?value=p`: WebFlux invokes the synchronous `String → AccountTier` converter to get `PREMIUM`; the controller returns `TIER:PREMIUM`. No query occurs.
2. `POST /api/signups`: WebFlux decodes the JSON body via codecs and checks `@Valid` on `Mono<SignupRequest>` once materialized. This is the reactive `@RequestBody` pattern supported by Spring WebFlux.
3. `@NotBlank`/`@Min(18)` are **pure data validation**; if they fail, WebFlux raises `WebExchangeBindException` and returns HTTP 400 when no custom handler overrides it.
4. Only when the body is valid does the controller call `lookup.exists(...)` inside `flatMap`; "username taken" is an **async business rule** mapped to 409 Conflict, not crammed into a `ConstraintValidator`.
5. The result from `lookup` flows through `map` (transforming the emitted Boolean into a response) without blocking the request thread.
6. `SignupReply` is the response DTO, and `ResponseEntity` sets the status per business outcome.

**Demo limitation:** the fake lookup only checks existence and **does not create a real user**, so `"created"` illustrates the decision branch. In a real system, add a reactive persistence step before returning 201 Created, enforce a unique index in the database, handle duplicate insert errors, and return 201 only after persistence succeeds. Never treat a pre-check result as proof the record was saved.

If an app wants to catch missing `age` rather than defaulting primitive `int` to 0, use `Integer age` with `@NotNull` and `@Min(18)`; the demo uses `int` to keep focus on separating converters/validators from async lookups while still catching underage values via `@Min`.

## 10. WebTestClient Testing for Conversion, Validation, and Async Domain Rules

Create `src/test/java/com/example/nonblocking/NonBlockingApplicationTest.java`:

~~~java
package com.example.nonblocking;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NonBlockingApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void convertsAliasWithoutLookup() {
        client.get()
                .uri("/api/tier?value=p")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("TIER:PREMIUM");
    }

    @Test
    void convertsSecondAlias() {
        client.get()
                .uri("/api/tier?value=basic")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("TIER:BASIC");
    }

    @Test
    void invalidAliasIsBadRequest() {
        client.get()
                .uri("/api/tier?value=unknown")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void missingQueryIsBadRequest() {
        client.get()
                .uri("/api/tier")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void registrationPassesPureValidationThenLookup() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"username":"fresh","age":22}
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.status").isEqualTo("created");
    }

    @Test
    void takenUsernameIsBusinessConflict() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"username":"taken","age":22}
                        """)
                .exchange()
                .expectStatus().isEqualTo(409)
                .expectBody()
                .jsonPath("$.status").isEqualTo(
                        "username_taken");
    }

    @Test
    void blankUsernameIsBeanValidationError() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"username":"","age":22}
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void underageIsBeanValidationError() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"username":"fresh","age":16}
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void malformedJsonFailsBeforeBeanValidation() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"username\":")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void missingRequiredBodyFailsBeforeController() {
        client.post()
                .uri("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Run from the root of the Maven-configured project:

~~~bash
./mvnw test -Dtest=NonBlockingApplicationTest
~~~

On Windows use `mvnw.cmd test -Dtest=NonBlockingApplicationTest`; if Maven is installed you can use `mvn test -Dtest=NonBlockingApplicationTest`.

With Spring Boot 3.x + WebFlux + Validation + Test configured as above, **10 tests are designed to pass**:

| Scenario | Expected HTTP Status | What It Proves |
| --- | --- | --- |
| `?value=p` | 200, `TIER:PREMIUM` | Converter parses local alias. |
| `?value=basic` | 200, `TIER:BASIC` | Simple conversion without I/O. |
| `?value=unknown` | 400 | Conversion failure, not a DB lookup failure. |
| Omitted `value` | 400 | Required query parameter. |
| `username=fresh, age=22` | 201, `created` | Valid input → in-memory domain lookup via Mono. |
| `username=taken, age=22` | 409, `username_taken` | Domain conflict separated from Bean Validation. |
| `username=""` | 400 | `@NotBlank` fails on reactive body. |
| `age=16` | 400 | `@Min(18)` fails. |
| Malformed JSON body | 400 | JSON decoding fails before validator. |
| Missing required body | 400 | Body read error, not "username available". |

These tests primarily verify **HTTP contracts and separation of responsibilities**; they do not measure performance or prove an entire production system is non-blocking. To detect real blocking, add profilers, metrics, and runtime tools in an appropriate environment.

### Trying with curl

Start with `./mvnw spring-boot:run`, then:

~~~bash
curl -i "http://localhost:8080/api/tier?value=p"

curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  -d '{"username":"fresh","age":22}'

curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  -d '{"username":"taken","age":22}'

curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  -d '{"username":"","age":22}'
~~~

Unix shell commands; on PowerShell use `curl.exe` or adjust quoting/line continuation. Expect HTTP statuses **200**, **201**, **409**, and **400** respectively under the demo's default settings. Default 400 error bodies from WebFlux vary by version/configuration, so the tests assert status codes on those cases.

## 11. Working with R2DBC and WebClient Instead of Blocking

In production, a reactive repository looks like:

~~~java
public interface UserRepository
        extends ReactiveCrudRepository<UserEntity, Long> {

    Mono<Boolean> existsByUsername(String username);
}
~~~

This is an **architectural snippet** requiring an entity, R2DBC driver, dependencies, `ReactiveCrudRepository` import, and DB schema. `ReactiveCrudRepository` belongs to Spring Data Reactive; verify the underlying module/driver performs true reactive I/O rather than wrapping JDBC/JPA waits underneath.

A service verifying via another API can use `WebClient`:

~~~java
public Mono<Boolean> isAllowed(String username) {
    return webClient.get()
            .uri("/permissions/{username}", username)
            .retrieve()
            .bodyToMono(Boolean.class);
}
~~~

This snippet assumes a configured `WebClient` and Boolean response API. `bodyToMono(Boolean.class)` **does not block**. In production, add timeouts, authentication, concurrency limits, backoff, rate limiting, circuit breakers where appropriate, and distinguish upstream 4xx vs 5xx errors. Never call `.block()` on the result to coerce it into a boolean for `isValid`.

### Distinguishing user errors from system errors

- `username=""` or `age=16`: **invalid data** → 400 with appropriate validation details.
- `username=taken`: **business conflict** → typically 409; use a distinct error code so users can pick another name.
- **DB/permission API unreachable, connection pool exhausted, timeout**: infrastructure failure → typically 5xx/503 per error policy; **never pretend the username is valid** or turn it into "username already exists".
- **Duplicate key on insert**: handle reliably at the database and map to 409. Never trust a pre-check alone to prevent races.

If policy requires an availability check during registration, structure a clear domain service instead of using a custom constraint whose error message implies uniqueness is a purely local immutable property.

## 12. Detecting Blocking with Tests, Profilers, and Observability

### 12.1. Observing the event loop and boundedElastic

During local debugging, logs can record thread names, request IDs, and spans across conversion/service steps, yet **do not rely on fixed thread names like `reactor-http-nio-3`** to decide code correctness. Thread names depend on runtime and schedulers.

Inspection tips:

- Reactor Netty **event loop busy/stalled** metrics and request latency percentiles (p95/p99).
- Connection pool wait time, DB query durations, and pending tasks on `boundedElastic`.
- Thread dumps / JFR / flame graphs when requests stall to catch stacks with `Thread.sleep`, `java.sql`, `RestTemplate`, `Future#get`, or `Mono#block()` inside converters/validators.
- Before/after metrics when separating I/O from binding to measure tail latency under concurrent load.
- Controlled logging and distributed tracing to separate 400 validation errors from 409 business conflicts and 5xx upstream failures.

### 12.2. BlockHound: helpful, not a substitute for code review

**BlockHound** is an optional tool that can detect certain blocking calls executing on instrumented non-blocking threads. It requires compatible JVM/library setup and instrumentation; some Java versions need extra agent/JVM flags. It does not prove every driver or custom method is non-blocking and can have false positives or false negatives.

When integrating BlockHound into tests or dev environments:

1. Verify version compatibility and installation flags.
2. Exercise both conversion and validation paths under concurrent load.
3. Combine with profiling and call-graph review: `@Converter` → DB/HTTP or `@Valid` → `block()` should be caught during code review.
4. Never disable all warnings just to make tests pass; understand the blocking source and fix it at the right layer.

### 12.3. Testing async behavior matters more than seeing `Mono`

Section 10's `WebTestClient` tests verify response contracts. To prove queries are genuinely asynchronous, run integration tests against a **real reactive driver**, concurrency load tests, and thread/pool monitoring. `Mono.fromSupplier(() -> jdbcCall())` and `Mono.just(jdbcCall())` still return `Mono` while **blocking all the same**.

With the `fromCallable + boundedElastic` blocking adapter, test in an environment with realistic resources; if worker/queue limits are tight, latency climbs under load. Never call `.block()` in a handler just to inspect a result or "keep tests simple" when tests do not control schedulers.

### 12.4. Avoid unbounded per-item I/O checks in `Flux`

When one request carries many records and you write:

~~~java
return Flux.fromIterable(inputs)
        .flatMap(input -> reactiveService.check(input));
~~~

this is an illustrative snippet; for large inputs, **bound concurrency** and batch according to downstream capacity, for example:

~~~java
return Flux.fromIterable(inputs)
        .flatMap(input -> reactiveService.check(input), 8);
~~~

`flatMap(..., 8)` caps the number of concurrent inner publishers; it does not replace overall input size limits, timeouts, or connection pool sizing. Fast local checks can run via `map` before `flatMap` performs I/O. Never build a `ConstraintValidator` that fires N API calls for N fields and blocks waiting.

## 13. Common Mistakes and Fixes

| Anti-Pattern | Why It Fails | Replacement |
| --- | --- | --- |
| `Converter#convert` calls JPA/JDBC | Blocks during binding, risking event-loop stalls. | Parse to ID/value object; do reactive lookup in service. |
| `ConstraintValidator#isValid` calls `reactiveRepo.exists(...).block()` | Forces reactive publisher into synchronous wait. | Bean Validation checks data only; async uniqueness in `flatMap`. |
| `Spring Validator#validate` calls `RestTemplate` | Synchronous contract holds thread waiting on network. | Use `WebClient` in the service layer. |
| `Mono.just(blockingDao.load())` | Blocking runs **eagerly**, before the Publisher is created. | Temporarily use `Mono.fromCallable(...).subscribeOn(boundedElastic())`. |
| `Mono.fromSupplier(() -> jdbcCall())` with no scheduler | Lazy ≠ asynchronous/non-blocking. | Offload legacy at the proper boundary, or use a reactive driver. |
| `publishOn(boundedElastic())` after blocking `map` | Source already blocked upstream before scheduler switch. | Put `subscribeOn` at the blocking source. |
| `isValid` calls `subscribe()` and returns `true` | Check finishes after request was already accepted. | Compose publishers and await via `flatMap`. |
| Moving entire request onto `boundedElastic` | Hides architectural flaw, wastes threads, raises contention. | Keep conversion/validation lightweight; offload only unavoidable blocking sources. |
| Catching DB errors and returning `false` in validator | Turns infrastructure failures into user input errors. | Propagate/map proper 5xx errors in service/advice. |
| Checking uniqueness without a DB unique index | Concurrent requests both pass pre-check and insert duplicates. | Add DB unique constraint + duplicate-key handling. |
| Heavy CPU regex/normalization in converter | No I/O yet still hogs event loop. | Bound input, use linear-time algorithms; offload heavy work properly. |
| Wrapping `isValid` with `@Async` | Does not change synchronous `boolean` signature into reactive contract. | Move async business checks into the post-binding pipeline. |

## 14. Non-Blocking WebFlux Design Checklist

- [ ] `Converter#convert` performs only parsing, normalization, and immutable map lookups—no JDBC/JPA, sync HTTP, file I/O, `sleep`, or `Future#get`.
- [ ] Spring `Validator#validate` and Jakarta `ConstraintValidator#isValid` inspect already-present data only—never call `block()`.
- [ ] `@PathVariable`/`@RequestParam` values convert to value objects; entities are loaded by reactive services after binding.
- [ ] DTOs use `@NotBlank`, `@Size`, `@Min`/`@Pattern` for local structural constraints.
- [ ] Rules requiring DB/remote APIs are implemented with `Mono`/`Flux` and `flatMap`, never manual `subscribe()`.
- [ ] If legacy blocking APIs remain, isolate with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` at the **boundary** and monitor threads/queues/pools.
- [ ] Do not assume `Mono.just`/`Mono.defer`/`Mono.fromSupplier` automatically turn blocking operations into non-blocking ones.
- [ ] Maintain clear error policies separating 400 bad input, 409 business conflict, and 5xx infrastructure failures.
- [ ] Enforce unique indexes/constraints in the database rather than relying solely on availability pre-checks.
- [ ] Test valid inputs, conversion errors, Bean Validation failures, domain conflicts, and malformed bodies.
- [ ] Code reviews/observability track event-loop stalls, p95/p99 latency, thread dumps, `boundedElastic` queues, and downstream latency.
- [ ] Keep CPU work in converters/validators bounded and fast; keep shared state thread-safe and never store per-request data in singleton validators.

**Conclusion:** **Converters/validators have synchronous contracts; reactive lookups have asynchronous contracts.** In WebFlux, keep type conversion and pure data validation fast, and compose database/network checks in services using `Mono`/`Flux`. `boundedElastic` is strictly a bridge for unavoidable legacy blocking calls—never an excuse to perform I/O inside `isValid` or `convert`.

## References

- Spring Framework Reference — WebFlux Type Conversion (`ConversionService`/formatters): https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html
- Spring Framework Reference — WebFlux `@RequestBody`, reactive arguments, and `@Valid`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework Reference — WebFlux Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework Reference — Spring `Validator`: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Reference — Jakarta Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Project Reactor Reference — **How Do I Wrap a Synchronous, Blocking Call?** (`fromCallable` + `boundedElastic`): https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/
- Project Reactor Reference — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Spring Data R2DBC Reference: https://docs.spring.io/spring-data/relational/reference/r2dbc.html
