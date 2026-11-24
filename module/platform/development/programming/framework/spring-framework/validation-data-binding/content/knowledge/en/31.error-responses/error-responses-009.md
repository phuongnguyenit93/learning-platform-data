# Never Rely on `Set<ConstraintViolation>` Iteration Order When Building Error Responses

## 1. Nature of the problem

In Jakarta Validation, when validating an object:

```java
Set<ConstraintViolation<OrderInput>> violations =
        validator.validate(input);
```

the result is a **`Set<ConstraintViolation<T>>`**, not a `List`. A `Set` represents the **set** of discovered violations; the API does not guarantee that the first element corresponds to the first declared field, the highest-priority constraint, or the top field in a form.

In the context of Spring Framework **error responses**, this matters because JSON errors are usually an ordered array. For example, a request:

```json
{
  "sku": " ",
  "quantity": 0,
  "customerEmail": "not-an-email"
}
```

can produce three errors from `@NotBlank`, `@Min(1)`, and `@Email`. If an application iterates directly over the `Set` to build the response, the JSON array order becomes an implementation detail of the provider/runtime:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {"field": "sku", "code": "NotBlank"},
    {"field": "customerEmail", "code": "Email"},
    {"field": "quantity", "code": "Min"}
  ]
}
```

Another run can return an array with the exact same three errors in a different order. The **observed** order does not necessarily change on every single request: a provider may happen to preserve an order many times in a row. Yet any observed stability is **not a contractual guarantee**.

Consequences:

- JSON snapshot tests risk becoming flaky when upgrading the provider/JDK or changing metadata.
- The frontend displays errors inconsistently.
- Picking the "first error" may pick an error that violates UX priorities.
- Payload comparison, caching, hashing, or logging systems may treat two semantically identical arrays as different.
- Clients inadvertently become coupled to Hibernate Validator's internal behavior.

**Core principle:** treat `Set<ConstraintViolation>` as data **without presentation order**, normalize it into error DTOs, **sort with an explicit comparator**, and serialize a `List`.

**Scope:** Jakarta Validation 3.x, Java 17+, Spring Framework 6.1–6.2, Spring Boot 3.x, and Spring MVC. Examples use Spring Boot 3.3.6 with `spring-boot-starter-validation`. Besides plain Jakarta `ConstraintViolation`, this lesson also shows where Spring MVC builds `BindingResult`/`FieldError` instead of returning a `Set`.

## 2. Three commonly assumed guarantees that do not exist

### 2.1. Field declaration order does not guarantee result order

```java
public record OrderInput(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity,
        @Email String customerEmail
) {}
```

Do not assume the provider evaluates or emits `sku` before `quantity` and `customerEmail`. Annotation metadata, caching, object graph traversal, and provider-specific optimizations establish no ordering contract. Jakarta Validation focuses on evaluating constraints and collecting violations, not preserving `Set` iteration order for UI presentation.

### 2.2. Different `Set` implementations do not fix the data source

| Structure | Property | Guarantees API error order? |
| --- | --- | --- |
| `HashSet` | No iteration order guarantee | No |
| `LinkedHashSet` | Preserves **insertion** order | Only if the initial insertion order is contracted |
| `TreeSet` | Sorts by comparator, treating comparator `0` as duplicates | Risks dropping violations |
| `new ArrayList<>(set)` | Copies the exact iterator order at copy time | No, unless sorted afterward |
| `stream().sorted(comparator).toList()` | `List` sorted by comparator | Yes, with properly designed keys |

Do not try to "fix" this by wrapping the result in a `LinkedHashSet`; it merely preserves an insertion order that already came from the input `Set`'s iteration order.

### 2.3. **Evaluation** order differs from **display** order

Jakarta Validation provides `@GroupSequence` to control the evaluation order of **constraint groups**. That is not a mechanism forcing the returned `Set` to iterate in field order. When the goal is simply keeping JSON errors ordered by field name or UI order, sorting the response **after** validation is the right solution.

## 3. Anti-patterns that tie responses to `Set` order

### 3.1. Taking the first element

```java
ConstraintViolation<OrderInput> first =
        violations.iterator().next();
```

If `violations` is empty, that line throws `NoSuchElementException`. If non-empty, it grabs whichever element the iterator yields first, **not** the highest-priority error.

These alternatives offer no priority guarantee either:

```java
violations.stream().findFirst();
violations.toArray()[0];
new ArrayList<>(violations).get(0);
```

If the API only wants one error, sort by an explicit priority first and then call `findFirst()`. If multiple errors are needed, do not discard elements just to keep the UI tidy.

### 3.2. Mapping directly to a `List` without sorting

```java
List<String> messages = violations.stream()
        .map(ConstraintViolation::getMessage)
        .toList();
```

`toList()` only preserves the stream's encounter order; it does not impose an order. Moreover, keeping only messages drops field paths and machine-readable codes.

### 3.3. Sorting and then collecting back into a `Set`

```java
Set<String> fields = violations.stream()
        .map(v -> v.getPropertyPath().toString())
        .sorted()
        .collect(java.util.stream.Collectors.toSet());
```

`Collectors.toSet()` makes no ordering guarantees. It also collapses distinct violations on the **same field**.

Right direction:

```java
List<String> fields = violations.stream()
        .map(v -> v.getPropertyPath().toString())
        .sorted()
        .toList();
```

This snippet illustrates only field sorting; a full adapter preserves code and message as well.

### 3.4. Sorting by translated message as the primary key

```java
violations.stream()
        .sorted(Comparator.comparing(
                ConstraintViolation::getMessage))
        .toList();
```

This compiles, but is unsuitable as a presentation contract: `getMessage()` depends on `Locale`, message bundles, providers, and copywriting. Updating a translation can flip error order.

Prefer **canonical field path**, **error code**, **annotation type**, or an API-owned **priority**. You may use the message as a final tie-breaker for deterministic order within **a single locale**, while noting that absolute order across locales can differ when earlier keys tie.

### 3.5. `TreeSet` can silently drop errors

Do not use a field-only comparator to populate a `TreeSet`:

```java
Comparator<ConstraintViolation<?>> byField =
        Comparator.comparing(v ->
                v.getPropertyPath().toString());
```

One field can violate both `@NotBlank` and `@Size`. When the comparator returns `0` for two violations on the same field, `TreeSet` retains only one. **Sorting** and **deduplicating** must remain two separate decisions.

## 4. Designing a stable error JSON contract

Do not serialize `ConstraintViolation` directly, as it holds invalid values, root beans, and provider metadata. Define a public DTO:

```java
public record ApiViolation(
        String field,
        String code,
        String message
) {}
```

A clean response:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "field": "customerEmail",
      "code": "Email",
      "message": "must be a well-formed email address"
    },
    {
      "field": "quantity",
      "code": "Min",
      "message": "must be greater than or equal to 1"
    },
    {
      "field": "sku",
      "code": "NotBlank",
      "message": "must not be blank"
    }
  ]
}
```

This example uses typical English messages from Hibernate Validator; exact text can vary by translation, provider, and version. The **array order** is controlled by the application: `customerEmail`, `quantity`, `sku`.

### 4.1. Sort keys

A practical four-level comparator uses:

1. `ConstraintViolation#getPropertyPath().toString()`.
2. Full annotation type name from `getConstraintDescriptor().getAnnotation().annotationType().getName()`.
3. `ConstraintViolation#getMessageTemplate()`.
4. `ConstraintViolation#getMessage()` as a final tie-breaker, only when needed.

Why?

- Path identifies the failing field/location.
- Full annotation name avoids collisions between two custom annotations sharing a simple name in different packages.
- Uninterpolated message templates are usually more stable than translated text.
- Message at the end distinguishes entries that still tie on earlier keys within the same locale.
- Never sort by `getInvalidValue()`: it could be a password, token, or object without a stable string form.
- Never use `System.identityHashCode` or instance `hashCode()`: those depend on object identity/JVM.

If two distinct violations tie on every sort key yet produce **identical public DTOs**, swapping them does not change the JSON. If they produce distinct public DTOs, add a deterministic domain tie-breaker; never fall back to iteration order.

### 4.2. Lexicographical order is not UX order

Alphabetical order puts `customerEmail` before `quantity` before `sku`. If the actual form wants `sku` first, define a priority map:

```java
Map<String, Integer> priority = Map.of(
        "sku", 0,
        "quantity", 1,
        "customerEmail", 2
);

Comparator<ApiViolation> uxOrder =
        Comparator.comparingInt((ApiViolation e) ->
                priority.getOrDefault(e.field(), 100))
                .thenComparing(ApiViolation::field)
                .thenComparing(ApiViolation::code)
                .thenComparing(ApiViolation::message);
```

This is an illustrative snippet requiring `Map` and `Comparator` imports. Any undefined field gets rank 100 and is sorted deterministically by the secondary keys. If priority is part of the frontend contract, document, version, and test it.

## 5. Runnable Spring Boot project

The application demonstrates two paths:

- `POST /api/orders/manual`: calls `Validator#validate` directly, receives `Set<ConstraintViolation<OrderInput>>`, and normalizes it into a `List`.
- `POST /api/orders/automatic`: uses `@Valid @RequestBody` in Spring MVC; `MethodArgumentNotValidException` carries a `BindingResult`, which must also be sorted if the application dictates response order.
- `MockMvc` verifies JSON ordering.
- JUnit tests the normalizer against **different permutations** of the same `Set`, rather than relying on the provider happening to keep one order.

### 5.1. Structure

```text
ordered-errors-demo/
  settings.gradle
  build.gradle
  src/
    main/java/com/example/orderederrors/
      OrderedErrorsApplication.java
      OrderInput.java
      ApiViolation.java
      ApiError.java
      ViolationNormalizer.java
      OrderController.java
      ValidationAdvice.java
    test/java/com/example/orderederrors/
      OrderValidationTest.java
```

### 5.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'ordered-errors-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` brings in the Jakarta API and typically Hibernate Validator as the provider. No Hibernate Validator proprietary API is needed for the normalizer: `ConstraintViolation`, `Validator`, and `ConstraintDescriptor` belong to Jakarta Validation.

### 5.3. Main application

`src/main/java/com/example/orderederrors/OrderedErrorsApplication.java`:

```java
package com.example.orderederrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderedErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderedErrorsApplication.class, args);
    }
}
```

### 5.4. Data DTO

`src/main/java/com/example/orderederrors/OrderInput.java`:

```java
package com.example.orderederrors;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OrderInput(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity,
        @Email String customerEmail
) {}
```

`sku=" "` violates `NotBlank`; `quantity=0` violates `Min`; `customerEmail="not-an-email"` violates `Email`. `@NotNull` is added on `quantity` because `@Min` itself treats null as valid. `@Email` in the demo allows null: if email is required, add `@NotBlank` or `@NotNull` per domain rules.

### 5.5. Response DTOs

`src/main/java/com/example/orderederrors/ApiViolation.java`:

```java
package com.example.orderederrors;

public record ApiViolation(
        String field,
        String code,
        String message
) {}
```

`src/main/java/com/example/orderederrors/ApiError.java`:

```java
package com.example.orderederrors;

import java.util.List;

public record ApiError(
        String code,
        List<ApiViolation> errors
) {}
```

`ApiError.code` is `VALIDATION_ERROR` or `OK`. `ApiViolation.code` in the demo takes the simple annotation name such as `Min`; for a long-lived public API contract, map to stable business codes (such as `MIN_QUANTITY`) to avoid coupling the frontend to annotation implementations.

### 5.6. `ViolationNormalizer.java`

`src/main/java/com/example/orderederrors/ViolationNormalizer.java`:

```java
package com.example.orderederrors;

import jakarta.validation.ConstraintViolation;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

public final class ViolationNormalizer {

    private ViolationNormalizer() {}

    public static <T> List<ApiViolation> normalize(
            Set<ConstraintViolation<T>> violations) {

        return violations.stream()
                .map(v -> new SortEntry(
                        v.getPropertyPath().toString(),
                        v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getName(),
                        v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getSimpleName(),
                        v.getMessageTemplate(),
                        v.getMessage()
                ))
                .sorted(
                        Comparator.comparing(SortEntry::field)
                                .thenComparing(SortEntry::annotationType)
                                .thenComparing(SortEntry::messageTemplate)
                                .thenComparing(SortEntry::message)
                )
                .map(e -> new ApiViolation(
                        e.field(), e.code(), e.message()
                ))
                .toList();
    }

    private record SortEntry(
            String field,
            String annotationType,
            String code,
            String messageTemplate,
            String message
    ) {}
}
```

Key steps:

1. Accept `Set<ConstraintViolation<T>>` from `validator.validate(input)`.
2. Project to an internal `SortEntry` DTO holding only necessary metadata, omitting `invalidValue` and `rootBean`.
3. Sort by `field`, full annotation name, `messageTemplate`, and `message`.
4. Map to the public DTO **after sorting**.
5. Keep the result as a `List`; never call `distinct()` or collect back into a `Set`.
6. If the project requires invariant ordering across all locales, replace the `message` tie-breaker with a translation-independent ID or priority.

`getPropertyPath().toString()` works well for illustrating simple fields. For nested lists/maps and highly portable APIs, build a canonical path from `jakarta.validation.Path.Node`, inspecting `getKind()`, `getIndex()`, and `getKey()`.

### 5.7. Controller: manual Jakarta validation and Spring MVC validation

`src/main/java/com/example/orderederrors/OrderController.java`:

```java
package com.example.orderederrors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validator;
import java.util.List;
import java.util.Set;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final Validator validator;

    public OrderController(Validator validator) {
        this.validator = validator;
    }

    @PostMapping("/manual")
    public ResponseEntity<ApiError> manual(
            @RequestBody OrderInput input) {

        // Omit @Valid on this argument so Validator is called explicitly.
        Set<ConstraintViolation<OrderInput>> violations =
                validator.validate(input);

        if (!violations.isEmpty()) {
            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "VALIDATION_ERROR",
                            ViolationNormalizer.normalize(violations)
                    )
            );
        }

        return ResponseEntity.ok(
                new ApiError("OK", List.of())
        );
    }

    @PostMapping("/automatic")
    public ResponseEntity<ApiError> automatic(
            @Valid @RequestBody OrderInput input) {

        // @Valid errors are handled by Spring before this method runs.
        return ResponseEntity.ok(
                new ApiError("OK", List.of())
        );
    }
}
```

Key point: `/manual` validates an already-deserialized DTO; `/automatic` delegates to Spring MVC argument validation. Malformed JSON is a decoding error on both paths, not a `ConstraintViolation`.

### 5.8. `ValidationAdvice.java` for Spring MVC argument errors

`src/main/java/com/example/orderederrors/ValidationAdvice.java`:

```java
package com.example.orderederrors;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception) {

        List<ApiViolation> errors = exception.getBindingResult()
                .getAllErrors()
                .stream()
                .map(this::toViolation)
                .sorted(
                        Comparator.comparing(ApiViolation::field)
                                .thenComparing(ApiViolation::code)
                                .thenComparing(ApiViolation::message)
                )
                .toList();

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_ERROR", errors));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_JSON", List.of()));
    }

    private ApiViolation toViolation(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(error.getCode(), "invalid");
        String message = Objects.toString(
                error.getDefaultMessage(), "Invalid value"
        );

        return new ApiViolation(field, code, message);
    }
}
```

`BindingResult#getAllErrors()` includes both `FieldError` and `ObjectError`, avoiding dropping class-level constraints. It returns Spring errors, **not** `Set<ConstraintViolation>`. Still, to standardize HTTP JSON order, the advice should sort explicitly.

In apps using `MessageSource` to translate messages, `FieldError`/`ObjectError` implement `MessageSourceResolvable` and can be resolved via `messageSource.getMessage(error, locale)`. Do not treat text from `getDefaultMessage()` as a stable sort key across all languages. In the demo, cross-locale invariance is not needed because sorting by `field` and `code` already separates the three distinct fields.

## 6. Testing with `MockMvc` and input permutations

File `src/test/java/com/example/orderederrors/OrderValidationTest.java`:

```java
package com.example.orderederrors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderValidationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    Validator validator;

    private static final String INVALID = """
            {
              "sku": " ",
              "quantity": 0,
              "customerEmail": "not-an-email"
            }
            """;

    private static final String VALID = """
            {
              "sku": "SKU-17",
              "quantity": 2,
              "customerEmail": "lan@example.org"
            }
            """;

    @Test
    void manualResponseHasDefinedFieldOrder() throws Exception {
        mvc.perform(post("/api/orders/manual")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INVALID))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(3))
            .andExpect(jsonPath("$.errors[0].field")
                    .value("customerEmail"))
            .andExpect(jsonPath("$.errors[0].code").value("Email"))
            .andExpect(jsonPath("$.errors[1].field")
                    .value("quantity"))
            .andExpect(jsonPath("$.errors[1].code").value("Min"))
            .andExpect(jsonPath("$.errors[2].field").value("sku"))
            .andExpect(jsonPath("$.errors[2].code")
                    .value("NotBlank"));
    }

    @Test
    void springMvcResponseHasDefinedFieldOrder() throws Exception {
        mvc.perform(post("/api/orders/automatic")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INVALID))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(3))
            .andExpect(jsonPath("$.errors[0].field")
                    .value("customerEmail"))
            .andExpect(jsonPath("$.errors[1].field")
                    .value("quantity"))
            .andExpect(jsonPath("$.errors[2].field")
                    .value("sku"));
    }

    @Test
    void permutationsOfSetProduceExactlyTheSameList() {
        OrderInput input = new OrderInput(
                " ", 0, "not-an-email"
        );

        Set<ConstraintViolation<OrderInput>> raw =
                validator.validate(input);

        assertEquals(3, raw.size());
        List<ApiViolation> expected =
                ViolationNormalizer.normalize(raw);

        List<ConstraintViolation<OrderInput>> items =
                new ArrayList<>(raw);

        for (int seed = 0; seed < 20; seed++) {
            Collections.shuffle(items, new Random(seed));

            Set<ConstraintViolation<OrderInput>> permuted =
                    new LinkedHashSet<>(items);

            assertEquals(
                    expected,
                    ViolationNormalizer.normalize(permuted),
                    "Changed order for seed " + seed
            );
        }
    }

    @Test
    void reverseOrderDoesNotAffectOutput() {
        Set<ConstraintViolation<OrderInput>> raw =
                validator.validate(
                        new OrderInput(" ", 0, "not-an-email")
                );

        List<ConstraintViolation<OrderInput>> reversed =
                new ArrayList<>(raw);
        Collections.reverse(reversed);

        assertEquals(
                ViolationNormalizer.normalize(raw),
                ViolationNormalizer.normalize(
                        new LinkedHashSet<>(reversed))
        );
    }

    @Test
    void validManualRequestReturnsEmptyErrors() throws Exception {
        mvc.perform(post("/api/orders/manual")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("OK"))
            .andExpect(jsonPath("$.errors.length()").value(0));
    }

    @Test
    void validAutomaticRequestReturnsEmptyErrors()
            throws Exception {

        mvc.perform(post("/api/orders/automatic")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("OK"))
            .andExpect(jsonPath("$.errors.length()").value(0));
    }

    @Test
    void malformedJsonIsNotAConstraintViolation()
            throws Exception {

        mvc.perform(post("/api/orders/manual")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"S1\",\"quantity\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"))
            .andExpect(jsonPath("$.errors.length()").value(0));
    }

    @Test
    void missingQuantityIsNotNullViolation() {
        Set<ConstraintViolation<OrderInput>> raw =
                validator.validate(new OrderInput(
                        "SKU-17", null, "lan@example.org"
                ));

        assertEquals(1, raw.size());
        ApiViolation error =
                ViolationNormalizer.normalize(raw).get(0);

        assertEquals("quantity", error.field());
        assertEquals("NotNull", error.code());
    }
}
```

Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If the project lacks a Gradle wrapper yet, use an installed Gradle binary to generate one or run `gradle test`. **All eight tests are expected to PASS** with the corresponding configuration. This is the expected outcome of the sample lesson, not a claim that JUnit/Gradle was executed during authoring.

### 6.1. Why is permutation testing stronger than repeating the endpoint call?

A test calling the same endpoint 100 times and seeing identical responses does not prove your code is independent of `Set` order; Hibernate Validator may simply happen to emit the same iteration order on a single JVM. `permutationsOfSetProduceExactlyTheSameList` actively:

1. Obtains a real set of violations.
2. Constructs multiple `LinkedHashSet` instances holding the same elements in different insertion orders.
3. Runs the normalizer on each permutation.
4. Asserts the resulting `List<ApiViolation>` is identical.

This is a **metamorphic test**: a factor that must not affect the result (insertion order) is varied deliberately while the output contract stays invariant. This test catches someone removing `sorted(...)` even when the provider happens not to reorder on a single run.

### 6.2. Testing `Set` membership directly when order is not contracted

If a pure Jakarta-layer test only needs to verify that three fields failed:

```java
Set<String> fields = validator.validate(
        new OrderInput(" ", 0, "not-an-email")
).stream()
 .map(v -> v.getPropertyPath().toString())
 .collect(java.util.stream.Collectors.toSet());

assertEquals(
        Set.of("sku", "quantity", "customerEmail"),
        fields
);
```

This snippet assumes `validator` and a static import of `assertEquals` are in scope. Compare `Set`s when ordering is not required. Only assert JSON array indices when the application **has defined and enforced** an ordering policy.

## 7. A Java console example using the same normalizer

Beyond HTTP, `ViolationNormalizer` works in plain Java applications too. With a compatible Jakarta Validation provider:

```java
try (ValidatorFactory factory =
             Validation.buildDefaultValidatorFactory()) {

    Validator validator = factory.getValidator();

    Set<ConstraintViolation<OrderInput>> violations =
            validator.validate(
                    new OrderInput(" ", 0, "not-an-email")
            );

    ViolationNormalizer.normalize(violations)
            .forEach(e -> System.out.println(
                    e.field() + " -> " + e.code()
            ));
}
```

This snippet uses the project's classes and requires imports for `jakarta.validation.Validation`, `ValidatorFactory`, `Validator`, `ConstraintViolation`, and `java.util.Set`. `ValidatorFactory` must be closed after use; in Spring Boot, let the container manage the validator rather than creating a new factory per request.

Expected stdout for the field/code lines **after sorting**:

```text
customerEmail -> Email
quantity -> Min
sku -> NotBlank
```

Messages are omitted from expected stdout because default messages depend on locale, bundle, and provider. **Never** call `violations.iterator().next()` to decide the first line.

## 8. Fail-fast and `@GroupSequence` do not turn a `Set` into a stable list

### 8.1. `@GroupSequence` defines group evaluation order

Illustrative example:

```java
public interface BasicChecks {}

public interface DetailedChecks {}

@GroupSequence({BasicChecks.class, DetailedChecks.class})
public interface OrderedChecks {}
```

When validating with `OrderedChecks.class`, `BasicChecks` constraints are evaluated first; if that group produces a violation, the provider skips evaluating the subsequent `DetailedChecks` constraints per group-sequence semantics.

However:

- This does **not** define iteration order among violations within a group.
- `@GroupSequence` does not require the returned `Set` to be sorted.
- Group sequences change which constraints are evaluated, not merely JSON presentation.
- If you only want alphabetical field order, **sort the response**; never alter validation group semantics just for display.

### 8.2. Hibernate Validator fail-fast

Hibernate Validator offers fail-fast (a provider extension) to stop after the first violation. According to its reference guide, when multiple constraints fail, **there is no guarantee which error is detected first**. Therefore:

- Enabling fail-fast and sorting a single-element list **does not make the chosen error deterministic**.
- If the API must return all errors, do not enable fail-fast on the validator used for responses.
- If only one prioritized error should be returned, define an explicit policy: group sequences or well-designed ordered validation steps.
- Never rely on annotation declaration order or `iterator().next()` as error priority.

## 9. Nested paths, collection indices, and string comparison

With a nested DTO:

```java
public record Address(@NotBlank String city) {}

public record DeliveryInput(
        @NotBlank String sku,
        @NotNull @Valid Address address
) {}
```

A violation on `address.city` typically has a path formatted as:

```text
address.city
```

With a collection:

```java
public record OrderLine(@NotBlank String sku) {}

public record BatchInput(
        @NotEmpty List<@Valid OrderLine> lines
) {}
```

You can get:

```text
lines[0].sku
lines[2].sku
lines[10].sku
```

`Path#toString()` is not a **canonical JSON Pointer** published by default by the API. For portable mapping across providers, traverse `jakarta.validation.Path.Node` and format explicitly:

- `node.getKind()`: `PROPERTY`, `BEAN`, `CONTAINER_ELEMENT`, `PARAMETER`, `RETURN_VALUE`...
- `node.isInIterable()`: whether the node is inside a collection/map.
- `node.getIndex()` and `node.getKey()`: index/key position.
- Public schema choosing `field`, `location`, or escaped JSON Pointer.

One limitation of lexicographical sorting: `lines[10].sku` sorts before `lines[2].sku`. It is still **deterministic**, yet does not match the natural numeric order expected by UIs. If your API needs ascending numeric index order, compare `Path.Node#getIndex()` numerically rather than relying solely on `toString()`.

### 9.1. Class-level constraints and method validation

Class-level constraints can produce an empty path or a bean node rather than pointing to a single property. With Jakarta `ExecutableValidator`, violations on method parameters/return values can include method, parameter, and return-value nodes.

If the violation is a server **return-value contract violation**, never turn it into HTTP 400 merely because it shares a normalization layer. Spring MVC 6.1+ provides `HandlerMethodValidationException#isForReturnValue()`; input method violations are usually 400, while return-value violations are usually 500. Classify responsibility before building the response.

## 10. Multiple constraints on the same field: never drop errors

```java
@NotBlank
@Size(min = 5)
String sku;
```

If `sku=" "`, both `NotBlank` and `Size` can fail. If an adapter uses:

```java
Map<String, String> errors = new HashMap<>();
for (ConstraintViolation<?> v : violations) {
    errors.put(v.getPropertyPath().toString(), v.getMessage());
}
```

the later error overwrites the earlier one, and which one is "later" depends on `Set` iteration order. Not only is deterministic ordering lost, the API drops data.

If you want **one error per field**, assign explicit priorities to rule categories—for example, Required before Format before Length—and select one error via a well-defined comparator. If you need **all errors**, keep a `List` and allow multiple entries with the same `field`.

**Note on `equals`/comparators:** `TreeSet` treats comparator `0` as a duplicate element, so use `TreeSet` only when the comparator accurately defines both identity and deduplication semantics. In most error APIs, sorting a `List` is simpler and safer.

## 11. Stability across locales and providers

`ConstraintViolation#getMessage()` is normally interpolated text; `getMessageTemplate()` is the raw template. If using Spring's `MessageSource` to translate `FieldError`, the final message also depends on the request's resolved `Locale`.

To keep responses sound:

- `code` should be a stable, business-oriented machine-readable identifier.
- `field` should be the API-defined canonical path.
- `message` is content that may vary by locale.
- Comparators should rely primarily on language-independent `code`/`path`/priority.
- If multiple entries share the same `field`/`code`/`template` with different messages, a message tie-breaker makes ordering stable **within one locale**, though not necessarily identical across two locales.
- If the contract requires locale-invariant ordering, introduce a **translation-independent error ID or sort rank** capable of distinguishing every case.

Different providers or configurations can produce different **violation sets** (e.g., custom constraints, groups, fail-fast). Normalization cannot make two different sets yield identical responses; it ensures that the order of **the same error set** never depends on traversal order.

## 12. Checklist and common mistakes

| Common mistake | Consequence | Right approach |
| --- | --- | --- |
| Calling `iterator().next()` | Picks an arbitrary unprioritized error | Sort first, then take the first element |
| Assuming record field order is preserved | Coupled to provider | Rely on a comparator |
| Copying to `ArrayList` and using as-is | Copies an uncontracted order | Sort the list |
| Wrapping in `LinkedHashSet` | Preserves arbitrary insertion order | Sort explicitly |
| Using `TreeSet` with a path-only comparator | Drops other errors on the same field | Sort a `List`, do not deduplicate |
| Sorting and collecting with `toSet()` | Loses presentation order | Keep a `List` |
| Sorting by message | Locale changes alter order | Sort by code/path/priority first |
| Using `hashCode` as a tie-breaker | Unstable order across JVMs | Use stable metadata/IDs |
| Sorting by invalid value | Leaks data, unpredictable null/`toString` | Never use `invalidValue` |
| Silently mapping by field | Overwrites multiple constraints | Use a `List` or explicit single-error policy |
| Asserting only HTTP 400 | Misses error-order regressions | Assert the sorted JSON array |
| Testing only a single violation | Hides ordering issues | Test ≥ 2 violations |
| Repeating the same request in tests | May pass by chance due to provider stability | Permute insertion order actively |
| Thinking `@GroupSequence` sorts the `Set` | Confuses validation evaluation with presentation | Sort the response separately |
| Enabling fail-fast and expecting a fixed first error | Selected error can vary | Disable fail-fast or control groups |
| Using `Path#toString()` as a default JSON Pointer | Risk of differences across nodes/providers | Canonicalize `Path.Node` |
| Sorting `items[10]` as plain text | Wrong numeric ordering | Parse indices / sort structurally |
| Serializing raw `ConstraintViolation` | Leaks bean/invalid values/provider metadata | Use minimal public DTOs |
| Ignoring `ObjectError` | Drops class-level violations | Read `getAllErrors()` |
| Mapping every `ConstraintViolationException` to 400 | Masks server return-contract bugs | Separate input vs. return errors |

### Code review checklist

1. Does every place receiving `Set<ConstraintViolation<T>>` make its ordering behavior explicit?
2. Is there any `iterator().next()`, `findFirst()`, or `toArray()[0]` without a defined priority?
3. Is a `Set` mapped straight into a JSON array?
4. Does the comparator use stable path/code/template keys and an appropriate tie-breaker?
5. Are `invalidValue`, `rootBean`, and raw exceptions kept out of the payload?
6. Are all violations preserved when a single field has multiple constraints?
7. Are there permutation tests on the input `Set` and tests with multiple violations?
8. Are parse/conversion errors separated from Bean Validation?
9. For `@Valid @RequestBody`, are `BindingResult`/`MethodArgumentNotValidException` handled properly?
10. For direct method validation, are `HandlerMethodValidationException` input vs. return errors separated?
11. Is there a fallback policy for localized messages and stable error codes?
12. If a UI rank map is needed, is it documented and tested?
13. Do nested lists need numeric index sorting instead of lexicographical sorting?
14. When upgrading Spring or Hibernate Validator, are provider-independent ordering tests re-run?

**Conclusion:** `Set<ConstraintViolation>` holds a **set of errors**, not a list pre-sorted for the frontend. Never treat iteration order as business priority. Map each violation to a safe DTO, **sort with an explicit comparator**, keep it in a `List` for serialization, and test using permutations of the same `Set`. This eliminates a subtle source of instability in error response APIs while decoupling your contract from provider internals and constraint declaration order.

## Official references

- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): `Set` returned by `Validator`, constraint evaluation, groups, and property paths.
- [Jakarta Validation — Validator API](https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.1.1/jakarta/validation/Validator.html): `validate(...)` returns `Set<ConstraintViolation<T>>`.
- [Hibernate Validator 8.0 Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): validation groups, group sequences, fail-fast, and notes on unguaranteed constraint evaluation order.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): distinguishing argument validation and method validation.
- [Spring Framework — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/BindingResult.html): field errors, global errors, and binding metadata.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): `MethodArgumentNotValidException`, `HandlerMethodValidationException`, and API error handling.
