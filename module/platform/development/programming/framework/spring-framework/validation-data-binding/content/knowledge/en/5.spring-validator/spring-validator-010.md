# Stateless Validators and Thread Safety Under Concurrency in Spring

## 1. Why Does a Spring Validator Need to Be Thread-Safe?

In a Spring MVC application, many HTTP requests can be processed concurrently on different threads. A class annotated with `@Component` is a **singleton in the Spring container** by default: the exact same bean instance can be referenced by multiple controllers, binders, and requests. If that bean implements `org.springframework.validation.Validator`, its `validate(Object, Errors)` method may be invoked nearly simultaneously with different input objects.

The goal of a **stateless validator** is to make each validation pass an isolated operation: inspect the current input object, evaluate rules, and record errors into the `Errors` object belonging to **that specific invocation**. Never store the object being validated or the `Errors` collector in shared fields.

For example: Request A validates an interval `start=2, end=5`, while Request B validates `start=8, end=3`. The same `IntervalValidator` instance can serve both. Desired outcome: A is valid, B has an error on `end`. If the validator kept `currentForm` or `currentErrors` in fields, thread A could accidentally read state just written by thread B, leading to wrong messages or mixed errors across users.

This article focuses on `Spring Validator`, the `supports(Class<?>)` / `validate(Object, Errors)` contract, registration in Spring MVC, stateless design, concurrency testing, and key boundaries. Examples use **Java 17+ and Spring Framework 6.x / Spring Boot 3.x**.

## 2. The `org.springframework.validation.Validator` Contract

Spring provides an interface (shown conceptually) with two methods:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

- `supports(Class<?>)` tells Spring which object types the validator can check. It must return a consistent answer based on type without mutating bean state.
- `validate(Object target, Errors errors)` validates the **target of the current invocation**, using `errors.reject(...)` for object-wide errors or `errors.rejectValue(...)` for single-field errors. The method returns nothing; results live inside `Errors`.
- `Errors` accumulates error information for a single validation pass. In MVC, `BindingResult` extends `Errors` and also holds binding metadata, rejected values, and field errors.
- Spring's `Validator` differs from Bean Validation's `jakarta.validation.Validator`, though `LocalValidatorFactoryBean` can bridge them. Do not confuse the two interfaces in imports.

The interface snippet above illustrates the contract, not a redefinition of Spring's source code. A real class simply declares `implements Validator`.

Typical execution flow:

~~~text
HTTP request A                   HTTP request B
     |                                |
  Bind A                           Bind B
     |                                |
Errors A                         Errors B
     |                                |
     +---------> same bean <----------+
                  Validator
                     |
          validate(target, errors)
          uses local variables per call
                     |
              separate results
         Errors A          Errors B
~~~

**Core principle:** sharing **rule code and read-only configuration** is fine; **inputs, temporary variables, and error results of each request** must stay independent. The same applies when a validator is called from services or batch jobs rather than MVC.

## 3. “Stateless” Does Not Mean “No Fields Allowed”

A stateless validator can still hold fields representing **immutable configuration** or **thread-safe dependencies**:

~~~java
public final class QuantityValidator implements Validator {
    private final int maxQuantity;

    public QuantityValidator(int maxQuantity) {
        if (maxQuantity <= 0) {
            throw new IllegalArgumentException("maxQuantity must be positive");
        }
        this.maxQuantity = maxQuantity;
    }

    // supports(...) and validate(...) use maxQuantity read-only.
}
~~~

This is a **partial illustrative snippet**; implement both `Validator` methods to form a complete compilable class. `maxQuantity` can be injected once as configuration. After the bean is constructed, every request only reads that value.

Distinguish three kinds of state:

| State | Examples | Should a singleton validator hold it? |
| --- | --- | --- |
| Immutable configuration | `private final int maxQuantity`, immutable set of valid codes | Yes, provided it is never mutated after initialization |
| Shared dependency | Thread-safe service/repository/cache | Conditionally: must verify the dependency itself and how it is used |
| Per-request state | `currentUser`, `lastInput`, `currentErrors`, `StringBuilder` accumulating errors | No |

`final` prevents **reassigning the reference**, not mutating the contents of an `ArrayList` or `HashMap`. For example, `private final Map<String, Rule> rules = new HashMap<>()` still allows map mutations. If you only need configuration lookup, create an unmodifiable snapshot during construction using `Map.copyOf(...)` or `Set.copyOf(...)`, and ensure contained elements are also used safely.

No annotation such as `@Component`, `@Service`, or `@Scope("singleton")` guarantees thread safety by itself. Singleton describes **instance lifecycle/sharing**, whereas thread safety is a property of the implementation and its dependencies.

## 4. Counterexample: Storing `Errors` and Target in Fields

The code below is **deliberately broken** to show how race conditions happen:

~~~java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class UnsafeIntervalValidator implements Validator {
    private Errors currentErrors;
    private IntervalForm currentForm;

    @Override
    public boolean supports(Class<?> clazz) {
        return IntervalForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        currentForm = (IntervalForm) target;
        currentErrors = errors;

        if (currentForm.getStart() > currentForm.getEnd()) {
            currentErrors.rejectValue(
                    "end", "interval.order",
                    "End must be >= start"
            );
        }
    }
}
~~~

This is a **fragment using the `IntervalForm` defined in section 6**, meant strictly for analysis; never register this class as a real bean.

A possible execution interleaving:

~~~text
Thread A: currentForm = formA
Thread A: currentErrors = errorsA
                   [paused]
Thread B: currentForm = formB
Thread B: currentErrors = errorsB
Thread B: checks formB, writes to errorsB
Thread A: resumes, reads currentForm (now formB)
Thread A: writes to currentErrors (now errorsB)
~~~

As a result, `errorsA` may miss the error it should have received, while `errorsB` gets duplicate or mismatched errors. You do not need thousands of requests to hit this bug: two overlapping calls suffice to trigger an unlucky interleaving.

The same bug occurs when storing fields such as `lastCheckedUsername`, `currentLocale`, `requestId`, `List<FieldError> pendingErrors`, a reusable `StringBuilder` buffer, non-thread-safe formatters, or a bean with mutable properties used to pass data implicitly across calls.

The default fix is **removing per-request state from the bean** and using local variables inside the method. Slapping `synchronized` on as a band-aid does not fix the flawed design and serializes all requests; moreover, any other method reading or writing shared fields can still bypass the lock.

## 5. Proper Validator Design: `final` Config, Local Variables, Caller's `Errors`

A proper implementation looks like:

~~~java
@Override
public void validate(Object target, Errors errors) {
    IntervalForm form = (IntervalForm) target;
    Integer start = form.getStart();
    Integer end = form.getEnd();

    if (start == null || end == null) {
        return;
    }
    if (end < start) {
        errors.rejectValue("end", "interval.order",
                "End must not be less than start");
    }
}
~~~

Here, `form`, `start`, `end`, and the `errors` parameter are **local variables / invocation parameters**. Each thread has its own stack frame, so those variables never overwrite each other. The validator class stores neither `form` nor `errors` as fields.

Note: local variables can still hold **references to shared objects**. Thus, merely using local variables is insufficient if the code mutates singletons, static maps, unsafe caches, or shared entities. In addition, the input object must belong to a single request or be isolated; **never reuse the same mutable DTO across concurrent requests**.

Practical design rules:

1. `supports` depends solely on the class type, never on the “last checked object”.
2. `validate` reads `target` and writes **only** to the `Errors` passed to the current call.
3. Stable configuration values should be `final` or immutable snapshots.
4. If querying a service or DB is required, evaluate service thread safety, transactions, and side effects independently of the stateless validator.
5. Validation results should be consistent for the same input and rule snapshot. If rules depend on time or system state, make that dependency explicit and test with controlled clocks/snapshots.

## 6. Complete Spring Boot Example

Consider an endpoint accepting a numeric interval with constraints:

- `label` must not be blank.
- `start` and `end` must be present integers.
- `end` must be greater than or equal to `start`.
- Interval span `end - start` must be at most 30.

The first two constraints fit Bean Validation; the latter two use a custom Spring `Validator`. One validator instance can be shared across all requests because it holds no mutable per-request fields.

The project requires Java 17+, Spring MVC, and a Bean Validation provider. With Gradle in Spring Boot 3.x, the primary dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

A project generated via Spring Initializr already includes the plugins, repositories, and Java setup. The Java files below live in package `com.example.validation`.

### 6.1. Application Bootstrap — `ValidationApplication.java`

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}
~~~

### 6.2. Per-Request DTO — `IntervalForm.java`

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class IntervalForm {
    @NotBlank
    private String label;

    @NotNull
    private Integer start;

    @NotNull
    private Integer end;

    public IntervalForm() {}

    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }

    public Integer getStart() {
        return start;
    }

    public void setStart(Integer start) {
        this.start = start;
    }

    public Integer getEnd() {
        return end;
    }

    public void setEnd(Integer end) {
        this.end = end;
    }
}
~~~

This is a per-request JavaBean, not shared validator state. When Spring creates `@ModelAttribute`, it can use the no-arg constructor and setters to bind form fields. `@NotBlank` and `@NotNull` belong to Jakarta Bean Validation.

Using `Integer` instead of `int` clearly separates missing input (`null`) from an actual `0` submitted by the user. Also check type-conversion failures like `start=abc`, since conversion runs before interval rules are evaluated.

### 6.3. Thread-Safe Singleton Validator — `IntervalValidator.java`

~~~java
package com.example.validation;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public final class IntervalValidator implements Validator {
    private static final int MAX_SPAN = 30;

    @Override
    public boolean supports(Class<?> clazz) {
        return IntervalForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        IntervalForm form = (IntervalForm) target;
        Integer start = form.getStart();
        Integer end = form.getEnd();

        if (start == null || end == null) {
            return; // @NotNull reports missing values.
        }

        if (end < start) {
            errors.rejectValue(
                    "end",
                    "interval.order",
                    "End must not be less than start"
            );
            return;
        }

        long span = (long) end - start;
        if (span > MAX_SPAN) {
            errors.rejectValue(
                    "end",
                    "interval.tooLong",
                    "Interval span must not exceed 30"
            );
        }
    }
}
~~~

Thread-safety analysis:

- `MAX_SPAN` is a constant; no instance field is written when `validate` executes.
- `form`, `start`, `end`, and `span` are per-invocation local variables, not shared across requests.
- `errors` is supplied by the current binder; the code only calls `errors.rejectValue(...)` on that parameter.
- There are no global counters, mutable caches, current-user fields, or last-result fields.
- Subtraction uses `long` to prevent integer overflow if a client sends extreme values.

`supports` uses `IntervalForm.class.isAssignableFrom(clazz)`, so it supports `IntervalForm` and compatible subtypes. `validate` can cast safely during Spring calls that check supported types; when calling manually, the caller must ensure a compatible target.

Returning early when `start` or `end` is `null` prevents the custom validator from throwing `NullPointerException` on missing input. `@NotNull` handles missing values; `IntervalValidator`'s responsibility is the relationship between the two numbers.

### 6.4. Controller Configuring the Validator — `IntervalController.java`

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IntervalController {
    private final IntervalValidator intervalValidator;

    public IntervalController(IntervalValidator intervalValidator) {
        this.intervalValidator = intervalValidator;
    }

    @InitBinder("intervalForm")
    void configureBinder(WebDataBinder binder) {
        binder.addValidators(intervalValidator);
    }

    @PostMapping(
            path = "/intervals",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("intervalForm") IntervalForm form,
            BindingResult errors
    ) {
        if (errors.hasErrors()) {
            var messages = errors.getFieldErrors().stream()
                    .map(e -> Map.of(
                            "field", e.getField(),
                            "code", Objects.toString(e.getCode(), "invalid"),
                            "message", Objects.toString(
                                    e.getDefaultMessage(), "Invalid")
                    ))
                    .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", messages));
        }

        return ResponseEntity.ok(Map.of(
                "label", form.getLabel(),
                "start", form.getStart(),
                "end", form.getEnd()
        ));
    }
}
~~~

Key points of the flow:

1. Spring registers `IntervalValidator` as a singleton bean by default; constructor injection gives the controller a stable reference.
2. Each time the model attribute is bound, Spring creates/configures a request-specific `WebDataBinder` and invokes `@InitBinder("intervalForm")`. `binder.addValidators(intervalValidator)` **registers** the existing validator without creating a shared `Errors` field.
3. Spring binds the incoming data into the current request's `IntervalForm`.
4. `@Valid` on the parameter triggers validation; `@NotBlank`/`@NotNull` are handled by Bean Validation, while custom `IntervalValidator` adds the cross-field rules.
5. `BindingResult` is **placed immediately after** `@ModelAttribute` so the controller can inspect and return errors directly. Every request gets its own error result.

Use `addValidators(...)` to **append** to the default configured validator. `setValidator(...)` replaces the binder's validator and can disable normal Bean Validation if used unintentionally.

### 6.5. Sending Requests and Reading Responses

Run the configured project:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. With Spring Boot defaults, the test endpoint is at `http://localhost:8080/intervals`.

Valid request:

~~~bash
curl -i -X POST http://localhost:8080/intervals -H "Content-Type: application/x-www-form-urlencoded" --data "label=demo&start=5&end=20"
~~~

Expected response is **HTTP 200**, with JSON containing the same fields (key order may vary):

~~~json
{"label":"demo","start":5,"end":20}
~~~

Request with inverted order:

~~~bash
curl -i -X POST http://localhost:8080/intervals -H "Content-Type: application/x-www-form-urlencoded" --data "label=demo&start=20&end=5"
~~~

Expected **HTTP 400**, `errors` list containing field `end` and related code `interval.order`. Exact codes are resolved hierarchically by object/field inside `BindingResult`, so client code should not depend solely on one fixed message string.

Request exceeding the allowed span:

~~~bash
curl -i -X POST http://localhost:8080/intervals -H "Content-Type: application/x-www-form-urlencoded" --data "label=demo&start=5&end=40"
~~~

Expected HTTP 400 with `interval.tooLong`. Request `label=&start=5&end=20` is flagged by Bean Validation for blank `label`. Request `start=abc` causes a type-conversion failure during data binding; do not describe that as an interval rule violation caught by `IntervalValidator`.

## 7. Why Must `Errors` and `BindingResult` Never Be Stored in Beans?

`Errors` is the **output object of a single check**. Even when a `Validator` is invoked concurrently, each call's `Errors` is **not shared storage**. In MVC, the binder manages the `BindingResult` tied to the bound input object.

Wrong:

~~~java
@Component
public class SharedErrorsHolder {
    private Errors lastErrors;

    public void remember(Errors errors) {
        this.lastErrors = errors;
    }
}
~~~

This snippet illustrates a dangerous design: `Errors` from Request A gets overwritten by Request B. This class has no place in the sample application.

Right: only pass `Errors` into `validate`; inspect `hasErrors()` and `getFieldErrors()` inside the handler/service handling that invocation. If you need aggregate statistics like validation failure counts, use a thread-safe metrics system and never put sensitive values into metric labels. **Metrics belong to system observability**, not per-request input/result storage.

To record multiple errors on one field, call `rejectValue` multiple times on the same invocation's `Errors`. There is no need to keep a `List<String> sharedMessages` inside the validator to accumulate errors.

## 8. Truly Testing with Multiple Threads

A single-request unit test proves rules work for one case. To catch shared-state bugs, invoke the **exact same validator instance** from multiple tasks while each task creates its own input and `BindingResult`.

The example below uses JUnit 5 and Spring Test dependencies already included in the project. File `src/test/java/com/example/validation/IntervalValidatorConcurrencyTest.java`:

~~~java
package com.example.validation;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;

import static org.junit.jupiter.api.Assertions.assertTrue;

class IntervalValidatorConcurrencyTest {

    @Test
    void sameValidatorCanBeUsedByParallelCalls() throws Exception {
        IntervalValidator validator = new IntervalValidator();
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch startGate = new CountDownLatch(1);
        List<Future<Boolean>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < 200; i++) {
                final int index = i;
                Callable<Boolean> caseTask = () -> {
                    startGate.await();

                    IntervalForm form = new IntervalForm();
                    form.setLabel("case-" + index);
                    form.setStart(100);
                    form.setEnd(index % 2 == 0 ? 99 : 101);

                    BeanPropertyBindingResult result =
                            new BeanPropertyBindingResult(
                                    form, "intervalForm");

                    validator.validate(form, result);
                    boolean expectError = index % 2 == 0;
                    return result.hasFieldErrors("end") == expectError;
                };
                futures.add(pool.submit(caseTask));
            }

            startGate.countDown();

            for (Future<Boolean> future : futures) {
                assertTrue(future.get(10, TimeUnit.SECONDS));
            }
        } finally {
            startGate.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
./gradlew test --tests com.example.validation.IntervalValidatorConcurrencyTest
~~~

On Windows the equivalent command is `gradlew.bat test --tests com.example.validation.IntervalValidatorConcurrencyTest`.

The test executes **200 calls** sharing a single `IntervalValidator` instance across an 8-thread pool. Even-indexed tasks have `end=99 < start=100` and must produce an `end` error; odd-indexed tasks have `end=101` and must have no `end` error. Each task constructs its own `IntervalForm` and `BeanPropertyBindingResult`, mirroring per-call state isolation.

**Proof limits:** repeated green runs provide useful evidence, not mathematical proof of absolute thread safety. Tests can miss rare race conditions; still review all mutable fields, object graphs, dependencies, and code paths. This unit test also **invokes only the custom Validator directly**; it does not start MVC, test `@InitBinder`, or run Bean Validation. Those belong to integration tests.

## 9. Spring MVC Integration Testing

`MockMvc` verifies that Spring registers and triggers the custom validator at the right moment. For the example above, add `src/test/java/com/example/validation/IntervalControllerTest.java`:

~~~java
package com.example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(IntervalController.class)
class IntervalControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void acceptsValidInterval() throws Exception {
        mvc.perform(post("/intervals")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("label", "demo")
                    .param("start", "5")
                    .param("end", "20"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.start").value(5))
                .andExpect(jsonPath("$.end").value(20));
    }

    @Test
    void rejectsInvalidIntervalOrder() throws Exception {
        mvc.perform(post("/intervals")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("label", "demo")
                    .param("start", "20")
                    .param("end", "5"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value("end"));
    }

    @Test
    void rejectsBlankLabelByBeanValidation() throws Exception {
        mvc.perform(post("/intervals")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("label", "")
                    .param("start", "5")
                    .param("end", "20"))
                .andExpect(status().isBadRequest());
    }
}
~~~

**Note on `@WebMvcTest`:** this test slice requires the `IntervalValidator` bean in its context. `@WebMvcTest(IntervalController.class)` does not scan arbitrary `@Component` classes; in a real project, add `@Import(IntervalValidator.class)` to the test class (importing `org.springframework.context.annotation.Import`), or configure the bean inside the slice. For the test above, **you must add `@Import(IntervalValidator.class)`** before running it standalone; the class declaration in this section illustrates the test body and assertions.

For a complete configuration, the class header becomes:

~~~java
@WebMvcTest(IntervalController.class)
@Import(IntervalValidator.class)
class IntervalControllerTest {
    // Fields and test methods presented above.
}
~~~

This snippet **replaces the three-line class header**, rather than being a second class to paste in full. When assembling runnable source, place `@Import(IntervalValidator.class)` on the single `IntervalControllerTest` class and add the import mentioned above.

Run:

~~~bash
./gradlew test --tests com.example.validation.IntervalControllerTest
~~~

In projects with Spring Security starter, configure test CSRF/auth according to your security policy; the minimal module example only declares Spring Web/Validation/Test.

Additionally, parallel HTTP-level tests can uncover accidental storage of `BindingResult` in controller or interceptor fields. Avoid mutable per-request singleton controllers even when the validator itself is stateless.

## 10. Validator Dependencies Must Also Be Thread-Safe

A validator that appears to have “no mutable fields” yet calls into a non-thread-safe service **can still be unsafe**. For instance, `validator.validate` calls a method updating a shared `HashMap` inside a singleton helper without synchronization. A race condition can happen inside the helper even though the validator only has `private final Helper helper`.

Audit carefully:

| Dependency / Behavior | Potential Problem | Mitigation |
| --- | --- | --- |
| Shared mutable `HashMap` / `ArrayList` | Races, corrupted data, `ConcurrentModificationException` | Keep config data immutable; use concurrent collections with proper semantics if needed |
| `SimpleDateFormat` in a field | Mutable and not thread-safe | Use immutable `java.time.format.DateTimeFormatter` or create formatters per invocation |
| Reused `StringBuilder` | Mixed messages across requests | Declare as local variable or allocate fresh |
| `lastResult` cache | Cross-request output leaks and stale data | Do not cache per-request results in validators; if caching is mandatory, design keys, expiry, and thread-safe structures |
| Service using per-user mutable state | User mix-ups under concurrent calls | Pass context explicitly; service must not store a shared `currentUser` |
| I/O or DB queries | Latency, state changing mid-check | Use thread-safe APIs and proper transaction boundaries; do not assume validation enforces final invariants |

In Spring, constructor injection and `final` fields are good practice for stable dependencies. Still, verify each dependency's thread-safety guarantees: Spring Data Repositories are designed to be shared, whereas an object managing a mutable buffer may need per-call instantiation.

If a validator must check whether a product code exists in the DB, it can safely call a read-only service, though the result can change right after validation. Rules for **uniqueness, balances, ownership, and inventory limits** must also be enforced inside transactions or via storage-level constraints. Request validation is only an early feedback layer for the user.

## 11. Stateless and Thread-Safe Are Related but Distinct Concepts

**Stateless**: an instance retains no state across invocations. Given a specific input, config, and dependency snapshot, a call is independent of previous requests.

**Thread-safe**: behavior remains correct when multiple threads invoke it concurrently as permitted by the API.

A pure validator that only reads independent inputs and immutable config and writes to an isolated `Errors` object can usually be shared safely as a singleton. However, the mere absence of mutable fields in the source file **is not enough to conclude** thread safety if internal dependencies or input references are shared and mutated concurrently.

Conversely, a class can be thread-safe via locks or synchronization while still being stateful. In most MVC validation, we **do not need to retain such state**, so stateless is simpler, avoids synchronization overhead, and is easier to test.

**Avoid using `ThreadLocal` to stash `Errors` or the current request**. Servlet containers reuse threads; forgetting `remove()` leaks data between requests. Async flows can also switch threads. Passing input and `Errors` explicitly via parameters is the natural design of Spring `Validator`.

## 12. Practical Questions on Registration and Usage

**Should we instantiate `new Validator()` per request to stay safe?** Not necessary when the validator is already stateless. Singletons avoid allocation overhead and simplify injection, while each request still gets its own DTO and `BindingResult`. Creating a new instance per call is justified only when an implementation genuinely owns per-call state by design.

**Is `@InitBinder` where validation runs?** No. It is a hook to configure `WebDataBinder` **before binding**. Attach validators with `addValidators` there; `@Valid` or `@Validated` on the handler triggers validation. When using `DataBinder` manually in Java code, call `binder.validate()` after `binder.bind(...)`.

**Can a validator be registered application-wide?** Yes. MVC supports configuring a global validator via `WebMvcConfigurer#getValidator()`; local `@InitBinder` configuration (in `@Controller` or `@ControllerAdvice`) is usually preferable when rules target specific DTOs. With a global validator, ensure `supports` matches the intended types and does not accidentally replace needed Bean Validation.

**Is `supports` allowed to query the DB or update a cache?** By design, no. It answers a *class* compatibility question, so it should be fast, deterministic, and side-effect-free. Business queries belong in `validate` or an appropriate service, depending on requirements.

**Should we mutate the target to “fix” input?** `Validator` exists to **report errors**, not to normalize data. To trim or canonicalize values, use converters, formatters, binders, or a dedicated normalization step prior to validation. Mutating DTOs inside validators makes validator ordering and testing unpredictable, especially with shared data.

**Do validators guarantee a stable error order?** Do not rely on ordering across multiple validators or Jakarta constraints. APIs should return meaningful fields and error codes, and tests should assert on the expected errors rather than assuming every request produces an error array in one fixed order.

**Are Jakarta constraints automatically thread-safe?** The Bean Validation provider manages `ConstraintValidator` lifecycles per its own rules; when writing custom `ConstraintValidator` implementations, also avoid mutable per-`isValid` state and keep configuration from `initialize` read-only. It is a different interface from Spring `Validator`, though the principle of not mixing invocation data is similar.

## 13. Singleton Validator Review Checklist

Before wiring a validator into a controller serving concurrent requests, verify:

1. Does the class have mutable fields like `currentErrors`, `currentForm`, `lastResult`, buffers, or request-specific collections? If so, remove them or turn them into local variables.
2. Do `final` fields hold mutable objects? If so, are they used immutably or guarded by clear thread-safety mechanisms?
3. Does `supports` rely solely on class type without remembering prior checks?
4. Does `validate` use only the `target` and `errors` passed in the current call, without mutating input beyond validation?
5. Are dependencies (services, caches, formatters, DB access) safe under concurrent calls?
6. Are input DTOs and `BindingResult` created and managed per request?
7. When a type conversion error or `null` field occurs, can the validator run without throwing a runtime exception?
8. Are there rule unit tests, Spring MVC request tests, and multi-threaded shared-instance tests?
9. If rules depend on DB state or authorization, does the service/transaction layer re-enforce mandatory invariants?
10. Are errors returned for the right request and field without leaking sensitive data?

## 14. Summary

A Spring `Validator` is suitable to share across requests when it holds only safe configuration/dependencies and uses **local variables plus the caller-supplied `Errors`** to process each invocation's data. Spring singleton beans are the standard model for such validators, provided neither the validator nor its dependencies share mutable per-request state.

Keeping `supports` pure, `validate` stateless, configuration immutable, `BindingResult` isolated, and concurrency tests in place minimizes the risk of mixing errors, inputs, and results across parallel requests.

### References

- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework — Java Bean Validation and DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
