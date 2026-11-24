# Method Validation and the Role of Proxies in Spring Boot

A Java method can still receive invalid arguments even after initial inputs pass HTTP validation. For example, a payment service might be invoked by a REST controller, batch job, scheduler, message listener, or another service. Placing constraints only on REST API DTOs leaves every non-controller call path unprotected.

**Method validation** lets you place Bean Validation constraints directly on method parameters and return values. In a Spring Boot application with Spring-managed services, this validation is commonly enforced via an **AOP proxy**: callers invoke a proxy object, the proxy intercepts the call, validates inputs, delegates to the target method, and then validates the return value.

Because of this, not only annotations but also the **call path** determines whether validation executes. A method annotated with `@NotNull` or `@Positive` might not be validated when called via `this.method()` in the same class, when instantiated with `new`, or when the method cannot be intercepted by a proxy.

This lesson explains how method validation works, proxy limitations, differences between controller and service validation, cascading and groups, common pitfalls, and testing strategies. Examples use Java 17+ and the `jakarta.validation` namespace of modern Spring Boot; legacy Spring Boot 2 codebases often use `javax.validation`.

## 1. What Problem Does Method Validation Solve?

Suppose we have a pricing service:

~~~java
@Service
public class PricingService {

    public BigDecimal calculateTotal(
            BigDecimal unitPrice,
            int quantity
    ) {
        return unitPrice.multiply(
                BigDecimal.valueOf(quantity)
        );
    }
}
~~~

If `unitPrice == null`, this throws `NullPointerException`. If `unitPrice` is negative or `quantity` is 0, the arithmetic runs yet violates business rules.

We want to state the input contract right on the method:

~~~java
@Service
@Validated
public class PricingService {

    public BigDecimal calculateTotal(
            @NotNull @Positive BigDecimal unitPrice,
            @Min(1) int quantity
    ) {
        return unitPrice.multiply(
                BigDecimal.valueOf(quantity)
        );
    }
}
~~~

The parameter constraints express:

- `@NotNull`: value must not be `null`.
- `@Positive`: number must be strictly greater than 0.
- `@Min(1)`: number must be greater than or equal to 1.
- `@Validated`: in Spring's service method validation mechanism, marks the bean as a target for the method-validation interceptor.

Calling through a Spring bean:

~~~java
BigDecimal total =
        pricingService.calculateTotal(
                new BigDecimal("12.50"),
                3
        );
~~~

Valid result is `37.50`. But calling:

~~~java
pricingService.calculateTotal(
        new BigDecimal("-12.50"),
        3
);
~~~

lets the validation interceptor catch the constraint violation **before the method body executes**.

Its primary value is not replacing `if` everywhere, but making method contracts explicit and enforcing them consistently across calls routed through Spring method validation.

## 2. Distinguishing Bean Validation, Method Validation, and Proxies

Three concepts are often conflated.

### Bean Validation: constraints and evaluator

Jakarta Bean Validation provides annotations and APIs such as:

~~~java
@NotNull
@NotBlank
@Size(min = 2, max = 80)
@Positive
@Min(1)
@Valid
~~~

An implementation like Hibernate Validator evaluates these constraints.

DTO example:

~~~java
public record CreateProductRequest(
        @NotBlank String name,
        @NotNull @Positive BigDecimal price
) {}
~~~

Annotations declare data rules. By themselves, they do not ensure every Java object is automatically checked.

### Method validation: validating parameters and return values

Bean Validation includes an executable-validation API, typically accessed via `ExecutableValidator`:

~~~java
ExecutableValidator executableValidator =
        validator.forExecutables();
~~~

This API can explicitly validate method parameters, return values, or constructors.

### Spring AOP proxy: automatic interception

Instead of calling `ExecutableValidator` manually everywhere, Spring can wrap bean methods with an interceptor:

~~~text
Caller
   |
   v
Spring-managed proxy
   |
   +--> Validate method arguments
   |
   +--> Invoke target method
   |
   +--> Validate return value
   |
   v
Return to caller
~~~

Key classes in Spring's service method-validation mechanism are `MethodValidationPostProcessor` and `MethodValidationInterceptor`. The post-processor detects eligible beans and configures the interceptor/proxy; the interceptor invokes Bean Validation when methods run.

**Summary of this section:** constraints are rules, the validator executes the rules, and the proxy is how Spring hooks validation into method calls without requiring services to call `validator.validate(...)` manually.

## 3. Required Dependencies in Spring Boot

In a Maven-based Spring Boot app, typically add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

With Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

The starter supplies the standard Bean Validation implementation dependencies. In recent Spring Boot releases, do not assume `spring-boot-starter-web` always brings a full Bean Validation provider; declare the validation starter explicitly when needed.

Example imports for a service:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;
~~~

`@Validated` is a **Spring** annotation; `@Valid`, `@NotNull`, and `@Positive` belong to **Jakarta Validation**.

### What does Spring Boot auto-configure?

When classpath and bean conditions are met, Spring Boot auto-configures a `Validator` and method validation infrastructure for Spring beans. In a standard Spring Boot setup, `MethodValidationPostProcessor` enables proxying for beans marked `@Validated`.

In a plain Spring Framework app or custom configuration lacking the post-processor, merely adding `@Validated` to a class will not create a validation interceptor. Verify the actual registered infrastructure, not just the annotations.

## 4. @Valid and @Validated Differ

The two annotations have similar names yet distinct roles.

| Annotation | Namespace | Role |
|---|---|---|
| `@Valid` | `jakarta.validation.Valid` | Requests cascading validation into nested objects/values |
| `@Validated` | `org.springframework.validation.annotation.Validated` | Spring marker for validation, supports validation groups; on service types typically activates AOP method validation |
| `@NotNull` | `jakarta.validation.constraints.NotNull` | Non-null constraint |
| `@Positive` | `jakarta.validation.constraints.Positive` | Strictly positive constraint |

Example:

~~~java
public record Address(
        @NotBlank String city,
        @NotBlank String street
) {}

public record CreateCustomerCommand(
        @NotBlank String name,
        @NotNull @Valid Address address
) {}
~~~

`@Valid` on `address` instructs the validator to descend into `Address`'s constraints. It does not by itself prove `CreateCustomerCommand` passed through a validation trigger.

Service:

~~~java
@Service
@Validated
public class CustomerRegistrationService {

    public UUID register(
            @NotNull @Valid CreateCustomerCommand command
    ) {
        // ...
        return UUID.randomUUID();
    }
}
~~~

When `register(...)` is called through Spring's method-validation proxy, the validator can:

1. Check `command` is non-null.
2. Descend into `CreateCustomerCommand`'s fields because of `@Valid`.
3. Validate `name` and `address`.
4. Descend into `Address` to validate `city` and `street`.

**Important:** `@Valid` does not mean non-null. If `address` is required, use `@NotNull @Valid` as shown.

## 5. End-to-End Service-Layer Example

Suppose a system handles product registration. Multiple entry points share one service.

### 5.1. Command carrying input data

~~~java
package com.example.catalog.application;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;

public record CreateProductCommand(
        @NotBlank String sku,
        @NotBlank String name,
        @NotNull @Positive BigDecimal price
) {}
~~~

`CreateProductCommand` represents input data for an application service. It could come from a REST request, message, or file import.

### 5.2. Service with method validation

~~~java
package com.example.catalog.application;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class ProductRegistrationService {

    private final ProductRepository repository;

    public ProductRegistrationService(
            ProductRepository repository
    ) {
        this.repository = repository;
    }

    @Transactional
    @NotNull
    public Long create(
            @NotNull @Valid CreateProductCommand command
    ) {
        Product saved = repository.save(
                Product.create(
                        command.sku(),
                        command.name(),
                        command.price()
                )
        );

        return saved.getId();
    }

    @NotNull
    public BigDecimal discountedPrice(
            @NotNull @Positive BigDecimal original,
            @Min(0) int discountPercent
    ) {
        if (discountPercent > 100) {
            throw new IllegalArgumentException(
                    "discountPercent must not exceed 100"
            );
        }

        return original.multiply(
                BigDecimal.valueOf(
                        100 - discountPercent
                )
        ).divide(BigDecimal.valueOf(100));
    }
}
~~~

`Product` and `ProductRepository` are illustrative domain abstractions. Notice `discountedPrice` uses `@Min(0)` while manually checking the upper limit; we could express that more cleanly with `@Max(100)`. That illustrates matching annotations to the full valid domain range.

Here `@NotNull` on `create(...)` and `discountedPrice(...)` is a **return-value constraint**. It is checked after the method completes, provided the call went through the proxy.

### 5.3. REST controller calling the service

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductRegistrationService service;

    public ProductController(
            ProductRegistrationService service
    ) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Map<String, Long>> create(
            @Valid @RequestBody CreateProductCommand command
    ) {
        Long id = service.create(command);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(Map.of("id", id));
    }
}
~~~

The controller has `@Valid` to check HTTP request input. The service has `@Validated` and method constraints to protect its contract **even when the caller is not an HTTP controller**.

Both layers can enforce the same rules. While this can validate twice on HTTP paths, each serves a distinct boundary:

- Controller validation protects **HTTP input** and typically yields HTTP 400.
- Service method validation protects the **use-case/service contract** for all callers routed through the proxy.

In complex apps, use separate HTTP DTOs and service commands to avoid coupling domain models directly to API contracts.

## 6. MethodValidationPostProcessor and Proxy Creation Flow

In Spring, `MethodValidationPostProcessor` is an advisor-based `BeanPostProcessor`. It participates in bean initialization and attaches the method-validation interceptor to eligible beans—typically those annotated with `@Validated` at the type level.

Conceptually:

~~~text
Spring Boot prepares ApplicationContext
                 |
                 v
    Register Validator and validation infrastructure
                 |
                 v
  Spring creates ProductRegistrationService bean
                 |
                 v
       MethodValidationPostProcessor
        detects @Validated annotation
                 |
                 v
         Create or augment AOP proxy
                 |
                 v
  Spring injects proxy into ProductController
                 |
                 v
  controller -> proxy -> validator -> target
~~~

Because validation is applied via an interceptor, `create(...)`'s body needs no manual validator calls.

### A proxy is not an independent copy of business logic

A proxy is an intermediary adding before/after behavior around calls. Business logic still runs on the underlying target according to proxy mechanics.

A bean can carry **multiple advisors**: method validation, transaction management, caching, security, or metrics. Spring creates/coordinates the proxy and advisor chain. Consequently, interceptor ordering and transaction boundaries can influence the exact point at which an exception is thrown.

### Class-level @Validated is the key signal for Spring AOP method validation

Example:

~~~java
@Service
@Validated
public class InventoryService {

    public void reserve(
            @NotBlank String sku,
            @Positive int quantity
    ) {
        // ...
    }
}
~~~

Constraints on method arguments specify what to validate. Class-level `@Validated` signals Spring's method-validation infrastructure to proxy this bean.

Omitting `@Validated` in standard service configurations leaves the constraint metadata intact, yet **service calls may no longer be intercepted automatically**.

## 7. How Is the Proxy Invoked?

Consider a bean:

~~~java
@Service
@Validated
public class InventoryService {

    public void reserve(
            @NotBlank String sku,
            @Positive int quantity
    ) {
        // Inventory reservation logic.
    }
}
~~~

Another service injects it:

~~~java
@Service
public class CheckoutService {

    private final InventoryService inventoryService;

    public CheckoutService(
            InventoryService inventoryService
    ) {
        this.inventoryService = inventoryService;
    }

    public void checkout() {
        inventoryService.reserve("ABC-123", -3);
    }
}
~~~

With method-validation proxying active, Spring injects the proxy. When `checkout()` calls `reserve(...)`, the call passes through the interceptor and `-3` violates `@Positive`.

Flow:

~~~text
CheckoutService
      |
      | inventoryService.reserve("ABC-123", -3)
      v
InventoryService proxy
      |
      +--> ExecutableValidator.validateParameters(...)
      |            |
      |        Violation
      |            |
      v            v
    Target?     Exception
      |
  Skipped on violation
~~~

When parameters are valid, the interceptor proceeds to the target method. After the target returns, if return-value constraints exist, the interceptor validates the return value.

### Key point: callers must go through the proxy

Standard AOP proxies intercept only external calls entering through the proxy reference. Calling the target directly or calling another method inside the same object can bypass validation.

## 8. Self-Invocation: A Common Reason Validation Fails to Run

Consider a service:

~~~java
@Service
@Validated
public class CustomerService {

    public void importMany(List<String> emails) {
        for (String email : emails) {
            registerOne(email);
        }
    }

    public void registerOne(
            @NotBlank @Email String email
    ) {
        // Create customer.
    }
}
~~~

When another bean calls `customerService.registerOne("bad")` through the proxy, method validation runs.

Inside `importMany(...)`, however, the line:

~~~java
registerOne(email);
~~~

is an internal call on `this`. It invokes the target method directly, **without re-entering the Spring proxy**. Hence constraints on `registerOne(...)` may not be evaluated along that call path.

Diagram:

~~~text
External caller
   |
   v
CustomerService proxy
   |
   v
importMany(...)
   |
   | this.registerOne(email)
   v
registerOne(...) on target
   |
   X Bypasses validation interceptor
~~~

### Why doesn't @Validated solve self-invocation?

`@Validated` tells Spring to wrap the bean in a proxy with a validation interceptor. It does not rewrite internal Java bytecode calls into proxy invocations.

The same principle affects other Spring proxy-based features like `@Transactional`, `@Async`, and `@Cacheable` under self-invocation.

### Preferred fix: extract responsibility into another bean

~~~java
@Service
@Validated
public class CustomerRegistrationService {

    public void registerOne(
            @NotBlank @Email String email
    ) {
        // Create one customer.
    }
}
~~~

~~~java
@Service
public class CustomerImportService {

    private final CustomerRegistrationService registrationService;

    public CustomerImportService(
            CustomerRegistrationService registrationService
    ) {
        this.registrationService = registrationService;
    }

    public void importMany(List<String> emails) {
        for (String email : emails) {
            registrationService.registerOne(email);
        }
    }
}
~~~

Calls from `CustomerImportService` to `CustomerRegistrationService` pass through the Spring-injected dependency and therefore cross the validation proxy.

Splitting beans is usually cleaner than self-injection or looking up the proxy from `ApplicationContext`.

### Alternative: explicit programmatic validation

If a method must be called internally and splitting beans is undesirable, validate explicitly with `Validator` or `ExecutableValidator`. That is a sound design choice when validation is required across internal boundaries.

Avoid reaching for `AopContext.currentProxy()` as a blanket fix for self-invocation. That couples services to AOP infrastructure, requires exposing proxies in config, and complicates testing.

## 9. Calling with new Has No Spring Proxy

Example:

~~~java
CustomerRegistrationService service =
        new CustomerRegistrationService();

service.registerOne("not-an-email");
~~~

Even if the class has `@Validated`, instantiating it with `new` keeps it outside Spring management. No `MethodValidationPostProcessor` attaches a proxy to manually constructed objects.

Compare with:

~~~java
CustomerRegistrationService service =
        applicationContext.getBean(
                CustomerRegistrationService.class
        );
~~~

Retrieving a bean from the context returns the proxy when eligible. In normal code, use constructor injection rather than looking up beans manually.

### Unit tests instantiating services with new

Unit tests checking plain Java logic can write:

~~~java
CustomerRegistrationService service =
        new CustomerRegistrationService(...);
~~~

Yet such a test **does not prove** Spring method validation works. Testing the interceptor requires a Spring context with validation infrastructure or calling `ExecutableValidator` explicitly.

## 10. JDK Dynamic Proxies vs. CGLIB / Class-Based Proxies

Spring AOP uses two main proxy mechanisms:

- **JDK dynamic proxy:** proxies interfaces implemented by the target.
- **Class-based proxy (CGLIB):** generates a subclass of the target class to intercept eligible methods.

### Interface-based proxying

~~~java
public interface ShippingService {
    void createShipment(String orderId);
}
~~~

~~~java
@Service
@Validated
public class ShippingServiceImpl
        implements ShippingService {

    @Override
    public void createShipment(
            @NotBlank String orderId
    ) {
        // ...
    }
}
~~~

With JDK proxies, callers typically inject the interface type:

~~~java
private final ShippingService shippingService;
~~~

However, Bean Validation constraints on inherited/overridden methods must obey Bean Validation's method-inheritance rules. Never arbitrarily add or tighten **parameter constraints** on an overriding method compared to the interface declaration; the provider may reject the constraint configuration.

A clean pattern is declaring parameter contracts on the interface:

~~~java
public interface ShippingService {

    void createShipment(
            @NotBlank String orderId
    );
}
~~~

~~~java
@Service
@Validated
public class ShippingServiceImpl
        implements ShippingService {

    @Override
    public void createShipment(String orderId) {
        // ...
    }
}
~~~

Here constraints live on the public interface contract, aligning with callers and avoiding declaration/override conflicts.

### Class-based proxying

With class-based proxies, Spring subclasses the bean to intercept calls. Methods that cannot be overridden lack the same interception capability.

Common configuration property:

~~~properties
spring.aop.proxy-target-class=true
~~~

This setting relates to proxy mode selection in Spring AOP configuration. However, proxy creation also depends on infrastructure, extension points, and auto-configuration post-processors. Never treat this property as a switch that makes `private` or `final` methods interceptable.

### Class-based proxies cannot bypass visibility/finality limits

CGLIB cannot override `final` or `private` methods, nor subclass a `final` class. Even with annotations on those methods, interception can silently fail or proxy creation can fail.

## 11. Visibility: public, private, final, and static

For predictable method validation via Spring AOP proxies, **prefer `public` methods invoked from other beans**.

| Case | Can interceptor run? | Recommendation |
|---|---|---|
| `public` method on Spring bean, called via proxy | Normally yes | Standard pattern |
| `public` method called internally via `this` | Normally bypasses proxy | Extract bean or validate explicitly |
| `private` method | Not a normal proxy-overridable join point | Do not rely on AOP validation |
| `final` method with class-based proxy | Cannot be overridden | Use non-final methods or interfaces |
| `final` class with class-based proxy | Cannot be subclassed | Use proxyable types or interfaces |
| `static` method | Not intercepted like instance methods | Validate explicitly if needed |
| Object created with `new` | Not post-processed by Spring | Inject bean or validate explicitly |

Interception behavior for `protected` or package-private methods depends on proxy type and Spring version. For public service contracts, avoid relying on edge-case visibility to keep behavior stable.

### Annotations on private methods do not give automatic validation

~~~java
@Service
@Validated
public class RegistrationService {

    private void validateInternal(
            @NotBlank String value
    ) {
        // ...
    }
}
~~~

`@NotBlank` remains metadata, yet Spring's method-validation proxy does not intercept calls to this private method. If validation is required, put it on a public boundary or call the validator directly.

## 12. Return-Value Validation

Method validation is not just for inputs. It can also validate **return values**.

~~~java
@Service
@Validated
public class ExchangeRateService {

    @NotNull
    @Positive
    public BigDecimal currentRate(String currency) {
        return fetchRate(currency);
    }

    private BigDecimal fetchRate(String currency) {
        // Example: data fetched from an external source.
        return BigDecimal.ONE;
    }
}
~~~

When `currentRate(...)` is called through the proxy:

1. Spring validates parameter constraints.
2. Target method runs.
3. Spring validates the return value.
4. If the return value violates constraints, the interceptor throws an exception instead of returning it.

### Return-value validation does not undo side effects

If a method already wrote to a database, sent an HTTP request, or mutated state before returning an invalid value, return-value validation detects the bug **only after the method body ran**.

Example:

~~~java
@NotNull
public Receipt createReceipt(Order order) {
    repository.save(order);
    return null; // Violates return constraint.
}
~~~

If a transaction wraps the method and the exception triggers rollback per config, database writes may roll back. External non-transactional side effects are not automatically undone.

Therefore, return-value constraints are useful contract checks, not a system-wide atomicity guarantee.

### Cascading on return values

You can request validating the returned object:

~~~java
@NotNull
@Valid
public InvoiceView createInvoice(...) {
    return new InvoiceView(...);
}
~~~

`@Valid` cascades into constraints on `InvoiceView`. Keep in mind output validation carries cost, and failures indicate a server/service bug rather than a client input error.

## 13. Cascading Validation with Nested Objects

A method can accept a structured command:

~~~java
public record CustomerAddress(
        @NotBlank String city,
        @NotBlank String postalCode
) {}
~~~

~~~java
public record RegisterCustomerCommand(
        @NotBlank String email,
        @NotNull @Valid CustomerAddress address
) {}
~~~

Service:

~~~java
@Service
@Validated
public class CustomerService {

    public UUID register(
            @NotNull @Valid RegisterCustomerCommand command
    ) {
        // ...
        return UUID.randomUUID();
    }
}
~~~

If `command.address().city()` is blank, executable validation detects the violation inside the nested object.

### @NotNull and @Valid complement each other

| Configuration | Is null a violation? | Validated when non-null? |
|---|---|---|
| `@Valid Address address` | No (only `@Valid`) | Yes |
| `@NotNull Address address` | Yes | Does not cascade automatically |
| `@NotNull @Valid Address address` | Yes | Yes |

This is a frequent mistake: writing only `@Valid` and being surprised when a null field raises no error.

### Collection and container element constraints

Constraints can target individual elements:

~~~java
public record BulkReserveCommand(
        @NotEmpty
        List<@NotBlank String> skus
) {}
~~~

Here:

- `@NotEmpty` requires a non-empty list.
- `@NotBlank` validates each string element using the Bean Validation provider's value extraction.

When elements are nested objects:

~~~java
public record CreateBatchCommand(
        @NotEmpty
        List<@Valid CreateProductCommand> products
) {}
~~~

When the batch command is validated, the validator checks each `CreateProductCommand`.

Never assume that merely receiving a `List` causes Bean Validation to inspect elements without cascading or container-element annotations.

## 14. Validation Groups and @Validated

An object may need different rules when saving a draft versus publishing.

Validation groups example:

~~~java
public interface DraftChecks {}
public interface PublishChecks {}
~~~

Command:

~~~java
public record ArticleCommand(
        @NotBlank(groups = {
                DraftChecks.class,
                PublishChecks.class
        })
        String title,

        @NotBlank(groups = PublishChecks.class)
        String content
) {}
~~~

In Spring services, `@Validated` selects groups per the annotation and method-validation infrastructure contract.

Two entry points can be split across services:

~~~java
@Service
@Validated(DraftChecks.class)
public class DraftArticleService {

    public void saveDraft(
            @NotNull @Valid ArticleCommand command
    ) {
        // Save draft.
    }
}
~~~

~~~java
@Service
@Validated(PublishChecks.class)
public class PublishArticleService {

    public void publish(
            @NotNull @Valid ArticleCommand command
    ) {
        // Publish article.
    }
}
~~~

Under `DraftChecks`, only `title` is validated. Under `PublishChecks`, both `title` and `content` are validated.

### Constraints without groups belong to Default

Bean Validation assigns constraints without explicit `groups` to `Default`. If you run validation with only a custom group, `Default` constraints do not run automatically unless included or linked via group inheritance/sequences.

Example:

~~~java
@NotBlank
String title;
~~~

will not automatically run when validating only `PublishChecks.class`.

This is a subtle pitfall with validation groups: ensure group definitions match business policies.

### Groups do not replace clean command separation

If an object accumulates many groups, complex combinations, and fields with different meanings per use case, splitting into `CreateDraftCommand` and `PublishArticleCommand` is often cleaner. Use groups when contexts genuinely share one stable structure.

## 15. When Does ConstraintViolationException Occur?

In typical Spring AOP method validation, parameter or return-value violations throw `jakarta.validation.ConstraintViolationException` by default.

Example:

~~~java
try {
    pricingService.calculateTotal(
            new BigDecimal("-5"),
            2
    );
} catch (ConstraintViolationException ex) {
    for (ConstraintViolation<?> violation
            : ex.getConstraintViolations()) {

        System.out.println(
                violation.getPropertyPath()
                        + " : "
                        + violation.getMessage()
        );
    }
}
~~~

`ConstraintViolation` exposes details including:

- `getPropertyPath()`: path across method, parameter, nested field, or return value.
- `getMessage()`: interpolated message.
- `getInvalidValue()`: rejected value.
- `getConstraintDescriptor()`: constraint metadata.

Never log raw `getInvalidValue()` in production if it could contain passwords, tokens, or personal data.

### Modern Spring Framework can use another exception

Some method-validation configurations support **adaptation** to Spring's validation result API, throwing `MethodValidationException` instead of `ConstraintViolationException`.

Keep these distinct:

1. Service method validation via standard AOP interceptor commonly throws `ConstraintViolationException`.
2. Method validation configured to adapt to Spring's validation API can throw `MethodValidationException`.
3. Spring MVC 6.1+ uses native handler-method validation and `HandlerMethodValidationException`.

Never write a global handler assuming every method-validation failure across the app always throws one single exception class. Check the layer and framework version in use.

## 16. Validation at HTTP Controllers vs. Services Differs

A REST controller might use:

~~~java
@PostMapping("/customers")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateCustomerRequest request
) {
    service.create(request.toCommand());
    return ResponseEntity.accepted().build();
}
~~~

In Spring MVC, body validation runs during argument resolution/binding. Under standard setups, `@Valid @RequestBody` failures produce `MethodArgumentNotValidException` and map to HTTP 400.

Service:

~~~java
@Service
@Validated
public class CustomerService {

    public void create(
            @NotNull @Valid CreateCustomerCommand command
    ) {
        // ...
    }
}
~~~

Service method validation uses an AOP proxy to protect business calls whether callers are HTTP, jobs, or message listeners. Its exception types and handling differ from controller argument validation.

### Not every service error is HTTP 400

If the server itself computes a bad value and passes it to a service, that is a server bug, not a client error. Catching every `ConstraintViolationException` and returning 400 can mask internal bugs.

Identify data origin and boundaries: client input errors deserve client 4xx responses; contract violations between internal components may warrant HTTP 500 and investigation as bugs.

### Both controller and service may validate

That does not make their semantics identical. Controllers handle HTTP binding and input formatting errors; services protect reusable contracts. If performance or architecture argues against double validation, refine boundaries explicitly rather than deleting method validation arbitrarily.

## 17. Spring MVC 6.1+ Has Native Handler-Method Validation

A common point of confusion in newer versions: **method validation on Spring MVC controllers does not necessarily use the same AOP proxy as service validation**.

Spring Framework 6.1+ supports built-in method validation during MVC handler-method invocation. Example:

~~~java
@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping("/{id}")
    public ItemView find(
            @PathVariable @Positive Long id
    ) {
        return itemService.find(id);
    }
}
~~~

Constraints placed directly on `@PathVariable` can be evaluated by MVC while invoking the handler method. When handler-method validation triggers, modern Spring MVC throws `HandlerMethodValidationException`.

### Why revisit @Validated on controllers?

In Spring MVC 6.1+, Spring documentation recommends **removing `@Validated` at the controller class level if you want native MVC method validation**, because type-level `@Validated` can route the controller through legacy AOP validation instead.

This does not conflict with putting `@Validated` on services for Spring AOP method validation. The two layers use separate infrastructure:

~~~text
HTTP request
    |
    v
Spring MVC binding / handler invocation
    |
    +--> Native MVC validation (Spring 6.1+)
    |
    v
Controller method
    |
    v
Service proxy
    |
    +--> AOP method validation if service has @Validated
    |
    v
Service target
~~~

In older Spring Boot generations, controller method validation worked differently. Do not copy exception handlers from an older Boot release to a newer one without verifying which layer runs validation.

### MethodArgumentNotValidException vs. HandlerMethodValidationException

In modern Spring MVC:

- `MethodArgumentNotValidException` typically appears when a single argument such as `@RequestBody` with `@Valid` is handled by argument-resolver validation.
- `HandlerMethodValidationException` appears when handler-method-level validation triggers on constraints like `@Min` on `@RequestParam` or `@Positive` on `@PathVariable`.

The combination of annotations and Spring version determines the exact exception. Use structured Spring MVC exception handling to map client errors cleanly without accidentally swallowing internal service bugs.

## 18. @Validated and @Transactional Together

A service often carries both transaction and method-validation annotations:

~~~java
@Service
@Validated
public class WalletService {

    private final WalletRepository repository;

    public WalletService(WalletRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(
            @NotNull UUID fromWalletId,
            @NotNull UUID toWalletId,
            @Positive BigDecimal amount
    ) {
        // Debit, credit, and save changes.
    }
}
~~~

Spring can apply both transaction advice and validation advice to the same bean.

Conceptual flow:

~~~text
Caller
   |
   v
Spring AOP proxy / advisors
   |
   +--> Validation advice
   |
   +--> Transaction advice
   |
   v
WalletService.transfer(...)
~~~

**Never guess actual advisor ordering from annotation order in source code.** Ordering depends on advisor order and infrastructure setup. Regardless of whether validation runs before or after transaction start, input contracts must still reject bad inputs before side effects occur.

### Do validation exceptions trigger rollback?

Under standard declarative transaction defaults, unchecked exceptions like `ConstraintViolationException` can trigger rollback if thrown inside a Spring-managed transaction boundary.

Distinguish three cases:

- If validation advice throws **before the transaction begins**, no transaction was started to roll back.
- If a return-value violation occurs **inside transaction advice**, the transaction can roll back per rollback rules.
- If return-value validation executes **after the transaction already committed**, detecting the error cannot undo the committed transaction.

Thus advisor ordering and transaction propagation—not annotations alone—determine exact rollback behavior.

### Do not use validation to replace business invariants

A constraint like `@Positive amount` checks input shape and sign, not whether a wallet has enough balance or whether two updates commit consistently.

Invariants involving database state, locking, or isolation must be handled in domain/service logic and transactions. Method validation never solves race conditions or database consistency on its own.

## 19. Validation at the Data and Database Layers

In "Resources and Data", distinguish three constraint layers:

1. **Input/application method validation:** verifies contract before a service runs.
2. **Entity validation:** validates constraints on entity state, optionally integrated into persistence lifecycle depending on provider/config.
3. **Database constraints:** enforces storage integrity, such as `NOT NULL`, `UNIQUE`, or `CHECK`.

Example:

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    @Column(nullable = false)
    private String sku;

    @NotNull
    @Positive
    @Column(nullable = false)
    private BigDecimal price;

    // Constructors, getters, domain behavior...
}
~~~

`@NotBlank` and `@Positive` are Bean Validation constraints. `@Column(nullable = false)` is ORM metadata describing column nullability, which **does not replace database migrations** applied properly to the real schema.

### Method validation does not guard every write path

An import script, admin tool, manual SQL, or another service can write to the database without calling your Spring service method. Critical invariants must be backed by database constraints and domain checks.

For instance, if `sku` must be unique, a database `UNIQUE` constraint prevents races that `repository.existsBySku(...)` alone cannot eliminate.

### Do not make entities the default API DTOs

Putting validation on entities can be helpful, yet reusing entities directly for every HTTP request tightly couples HTTP contracts, domain models, and persistence. Distinguish request DTOs, service commands, and entities, placing constraints at each layer as appropriate.

## 20. ConstraintViolationException vs. Persistence Exceptions

A Jakarta Validation `ConstraintViolationException` means **a Bean Validation constraint failed**.

Hibernate ORM and databases use nearly identical exception names for foreign-key, unique-index, or NOT NULL database violations.

Do not confuse:

~~~java
jakarta.validation.ConstraintViolationException
~~~

with persistence-provider exceptions such as:

~~~java
org.hibernate.exception.ConstraintViolationException
~~~

or Spring's `DataAccessException` wrappers.

Despite similar names, they come from completely different layers:

| Error | Common source |
|---|---|
| Jakarta `ConstraintViolationException` | Bean Validation, including AOP method validation |
| Hibernate ORM constraint violation | SQL/database constraint |
| Spring `DataIntegrityViolationException` | Persistence-layer data integrity abstraction |
| Spring MVC `MethodArgumentNotValidException` | Validation during argument binding |
| Spring MVC `HandlerMethodValidationException` | Native method validation in modern MVC |

Exception handlers and retry policies must match the exact class and layer.

## 21. Programmatic Method Validation Without a Proxy

When code must validate a method not invoked through a Spring proxy, call `ExecutableValidator` directly.

Plain Java class example:

~~~java
public class ShippingCalculator {

    public BigDecimal calculate(
            @NotNull @Positive BigDecimal weight,
            @Positive int distanceKm
    ) {
        return weight.multiply(
                BigDecimal.valueOf(distanceKm)
        );
    }
}
~~~

Validating arguments:

~~~java
Validator validator =
        Validation.buildDefaultValidatorFactory()
                .getValidator();

ExecutableValidator executableValidator =
        validator.forExecutables();

ShippingCalculator target =
        new ShippingCalculator();

Method method = ShippingCalculator.class.getMethod(
        "calculate",
        BigDecimal.class,
        int.class
);

Object[] arguments = {
        new BigDecimal("-2"),
        10
};

Set<ConstraintViolation<ShippingCalculator>> violations =
        executableValidator.validateParameters(
                target,
                method,
                arguments
        );
~~~

Inside a Spring Boot application, **inject the Spring-managed `Validator`** and call `validator.forExecutables()` instead of building a new `ValidatorFactory` every time.

If creating a standalone `ValidatorFactory`, real code must close it when finished:

~~~java
try (ValidatorFactory factory =
             Validation.buildDefaultValidatorFactory()) {

    Validator validator = factory.getValidator();
    // ...
}
~~~

Programmatic validation is useful when:

- The object is not a Spring bean.
- You want explicit validation at a specific step.
- Self-invocation occurs and extracting a bean is unwanted.
- Writing a Java library independent of Spring AOP.

However, your code must explicitly execute the check; annotations alone never invoke this API.

### Validating return values programmatically

~~~java
BigDecimal value = target.calculate(
        new BigDecimal("2"),
        10
);

Set<ConstraintViolation<ShippingCalculator>> returnViolations =
        executableValidator.validateReturnValue(
                target,
                method,
                value
        );
~~~

Here the caller decides what to do if `returnViolations` is non-empty. Spring AOP method validation handles this automatically via its interceptor.

## 22. Validation on Interfaces and Method Inheritance

When a service implements an interface, constraint declarations must obey Jakarta Bean Validation method-inheritance rules.

Interface:

~~~java
public interface PaymentService {

    Receipt charge(
            @NotNull @Positive BigDecimal amount
    );
}
~~~

Implementation:

~~~java
@Service
@Validated
public class DefaultPaymentService implements PaymentService {

    @Override
    public Receipt charge(BigDecimal amount) {
        // ...
        return new Receipt();
    }
}
~~~

The parameter contract resides on the interface. This is clean because every implementation obeys the same contract.

### Do not arbitrarily strengthen parameter constraints on overrides

The following can violate Bean Validation rules:

~~~java
public interface PaymentService {
    Receipt charge(BigDecimal amount);
}
~~~

~~~java
public class DefaultPaymentService implements PaymentService {

    @Override
    public Receipt charge(
            @Positive BigDecimal amount
    ) {
        // ...
        return new Receipt();
    }
}
~~~

Providers like Hibernate Validator can reject this executable constraint configuration because the implementation adds stricter preconditions than the inherited interface contract.

This relates to the Liskov Substitution Principle: implementations must not surprise callers with stricter input requirements than the interface promises.

Return-value constraints follow different inheritance rules and may be strengthened within specification limits. Across complex interface hierarchies, declare constraints clearly on the shared contract and avoid conflicting annotations across layers.

## 23. Annotations on an Interface While the Bean Uses a Class-Based Proxy?

Spring and Bean Validation providers can read constraint metadata across hierarchies and interfaces. Still, **whether a method gets intercepted** depends on how Spring builds the proxy and how callers reference the bean.

When multiple implementations exist:

1. Place executable parameter constraints on the shared contract interface where fitting.
2. Ensure implementations are Spring-managed.
3. Mark the appropriate type with `@Validated` per the method-validation infrastructure in use.
4. Inject the abstraction exposed by the proxy.
5. Test an actual invocation through `ApplicationContext`.

Do not deduce behavior solely by checking whether annotations sit directly on the runtime class; Spring AOP and Bean Validation inspect metadata across multiple locations.

## 24. Groups Do Not Make Spring Dispatch to a Different Method

Validation groups select **which constraints to evaluate**, not method overloads or business routing.

Example:

~~~java
@Validated(PublishChecks.class)
public class PublishService {

    public void publish(
            @NotNull @Valid ArticleCommand command
    ) {
        // ...
    }
}
~~~

If constraints fail, the interceptor rejects the call. If they pass, the same method executes. Spring does not select an alternate method dedicated to `PublishChecks`.

When draft and publish workflows differ, write distinct, clearly named methods or services instead of hiding workflow differences behind groups.

## 25. Validation Exceptions and API Error Handling

When errors occur in controller binding, use Spring MVC's exception-handling mechanism to return 400 responses with safe field details.

Handler skeleton:

~~~java
@RestControllerAdvice
public class ApiValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleInvalidBody(
            MethodArgumentNotValidException ex
    ) {
        Map<String, String> errors = new LinkedHashMap<>();

        ex.getBindingResult()
                .getFieldErrors()
                .forEach(error ->
                        errors.putIfAbsent(
                                error.getField(),
                                error.getDefaultMessage()
                        )
                );

        return ResponseEntity
                .badRequest()
                .body(errors);
    }
}
~~~

This illustrates a concise error response; production systems should use a unified error contract, avoid leaking sensitive values, and consider multiple errors on the same field.

With Spring MVC 6.1+, also handle `HandlerMethodValidationException` for native method validation. For AOP service method validation, handle `ConstraintViolationException` or the adapted exception matching your config.

**Never map every `ConstraintViolationException` from services to HTTP 400 automatically.** If another service passed bad data or return-value validation failed, that may be a server bug. Separate client input boundaries from internal invariants.

### Message interpolation and internationalization

Bean Validation supports default messages and message templates:

~~~java
@NotBlank(message = "SKU must not be blank")
String sku;
~~~

You can integrate message bundles for i18n. Still, user-facing messages should never expose sensitive values from `invalidValue`. A stable API exposes machine-readable error codes alongside human-readable messages.

## 26. Do Not Overuse Annotations for All Business Rules

Built-in constraints fit **local rules determinable from the immediate data**:

- Non-null.
- Non-blank strings.
- Valid lengths.
- Numeric ranges.
- Reasonable email format.
- Cascading validation on commands.

Rules like "SKU does not exist in the database", "order stays within customer credit limit", or "account is not locked" require querying system state and handling race conditions. Stuffing them into custom validators couples validation to databases, transactions, and bean creation timing.

Custom Bean Validation constraints can be valuable when chosen thoughtfully, provided you evaluate:

- Does the validator have side effects?
- Does it depend on services, repositories, or transactions?
- Does it require locking/consistency under concurrent requests?
- Should failures return input validation errors or domain exceptions?

Enforce business invariants in domain/application services and the database where appropriate; method validation is just one defensive layer.

## 27. Testing Method Validation Through the Spring Proxy

A unit test instantiating a service directly skips the proxy. To verify Spring enforces method constraints, use a Spring test context with Bean Validation infrastructure enabled.

Example:

~~~java
@SpringBootTest
class PricingServiceMethodValidationTest {

    @Autowired
    PricingService pricingService;

    @Test
    void rejectsNegativePrice() {
        assertThrows(
                ConstraintViolationException.class,
                () -> pricingService.calculateTotal(
                        new BigDecimal("-1"),
                        2
                )
        );
    }

    @Test
    void acceptsValidArguments() {
        BigDecimal total =
                pricingService.calculateTotal(
                        new BigDecimal("12.50"),
                        3
                );

        assertEquals(
                new BigDecimal("37.50"),
                total
        );
    }
}
~~~

This test assumes `PricingService` is a Spring bean with `@Validated`, the validation starter is present, and default config throws `ConstraintViolationException`. If your app adapts exceptions or alters infrastructure, assert the corresponding exception type.

### Why does @SpringBootTest matter here?

Testing through a Spring context routes calls through the real proxy and post-processors. A test calling:

~~~java
new PricingService().calculateTotal(
        new BigDecimal("-1"),
        2
);
~~~

does not test Spring AOP at all; it only executes the raw Java method body.

### Technical proxy inspection

For diagnostics, Spring offers:

~~~java
boolean proxied = AopUtils.isAopProxy(pricingService);
~~~

This reveals whether a reference is an AOP proxy. However, **being proxied does not prove every method has validation advice**: a proxy might exist for transactions, security, or caching, or a specific method might be skipped due to visibility or self-invocation.

Stronger verification calls the method on the injected bean with violating arguments and asserts the exception.

## 28. Testing Self-Invocation and Fixing It

Suppose:

~~~java
@Service
@Validated
public class CouponService {

    public void process(String code) {
        validateCode(code); // Self-invocation.
    }

    public void validateCode(
            @NotBlank String code
    ) {
        // ...
    }
}
~~~

A test calling:

~~~java
couponService.validateCode("");
~~~

receives a violation, whereas:

~~~java
couponService.process("");
~~~

may not trigger `validateCode(...)` validation if `process(...)` has no constraints itself and the internal call bypasses the proxy.

To protect `process(...)`, put the constraint on the public entry point:

~~~java
public void process(@NotBlank String code) {
    validateCode(code);
}
~~~

or extract `validateCode` into another Spring bean as shown earlier.

**Takeaway:** tests should verify not only "the annotation exists", but also **the actual caller execution path**.

## 29. Validation in Async, Scheduled, and Message Listeners

Spring Boot has many entry points beyond REST controllers:

- `@Scheduled` methods.
- `@Async` methods.
- Kafka/RabbitMQ message listeners.
- `ApplicationRunner` or `CommandLineRunner`.
- Domain event listeners.

When these components delegate data to an `@Validated` service via its Spring proxy, method validation guards the service boundary. If a method inside the same class calls another constrained method internally, self-invocation still bypasses the interceptor.

### @Async and AOP

`@Async` also relies on proxies. When method validation and async advice share a bean, advisor ordering and thread handoff dictate where exceptions surface and how callers observe them.

Example:

~~~java
@Service
@Validated
public class ExportService {

    @Async
    public CompletableFuture<String> export(
            @NotBlank String exportId
    ) {
        return CompletableFuture.completedFuture(
                "export-" + exportId
        );
    }
}
~~~

Never guess whether invalid arguments throw synchronously to the caller or complete the `CompletableFuture` exceptionally; check advisor ordering and async configuration. For `void` async methods, exceptions go to the configured async uncaught exception handler rather than the caller.

### Scheduled methods usually take no scheduler arguments

`@Scheduled` methods normally have no parameters passed by the scheduler. Parameter constraints on the scheduled entry point itself are therefore rarely useful. Put validation on the reusable services invoked by the scheduled job.

### Message consumers need contract error handling

When a message listener calls a validated service and receives `ConstraintViolationException`, the consumer must apply a reject, retry, or dead-letter policy. Never let malformed messages retry endlessly just because the exception is a `RuntimeException`.

Method validation detects the violation; **how to respond** belongs to messaging infrastructure and business rules.

## 30. Diagnostic Workflow When Validation Fails to Run

If constraints exist yet calls pass through unvalidated, check step by step:

~~~text
Method has constraints
       |
       v
Is Bean Validation provider present?
       |
       v
Is MethodValidationPostProcessor active?
       |
       v
Is the bean Spring-managed?
       |
       v
Does the type have @Validated?
       |
       v
Is the caller reference a proxy?
       |
       v
Did the call enter from outside through the proxy?
       |
       v
Is the method interceptable?
       |
       v
Is the constraint/group active?
       |
       v
Was the error caught/swallowed elsewhere?
~~~

Specific scenarios:

| Symptom | Possible cause | Fix |
|---|---|---|
| `@NotNull` fails to block null input | Missing method validation infrastructure or `@Validated` | Check starter and bean configuration |
| Direct call rejects invalid args, caller method does not | Self-invocation | Move constraint to public entry point or extract bean |
| Unit test with `new` passes invalid args | No Spring proxy | Test through context or validate explicitly |
| Bean cannot be proxied | `final` class/method or incompatible proxy type | Make types/methods proxyable |
| Bean lookup by implementation class fails | JDK interface proxy active | Inject interface or adjust proxy config |
| `@Valid` still permits null | `@Valid` only cascades | Add `@NotNull` |
| Nested object in method arg not checked | Missing cascade or container constraints | Add `@Valid` in the right place |
| Constraint skipped when using groups | Constraint in another group or `Default` | Review group declarations |
| Service throws violation yet controller skips 400 | Different validation/exception layer | Build exception handler per source |
| Return violation discovered after commit | Advisor ordering differs from expectations | Manage transaction/validation boundaries |
| Spring 6.1+ controller throws unexpected exception | Native MVC method validation | Distinguish `HandlerMethodValidationException` from AOP |
| Scheduled/listener call skips constraint | Internal call or non-proxied target | Extract validated service |

Watch infrastructure scope too: in multi-context or parent/child `ApplicationContext` setups, `MethodValidationPostProcessor` must live in the context managing the target beans.

## 31. Misconceptions to Avoid

### "Having @Valid means service methods auto-validate"

Not always. `@Valid` requests cascading; automatic service method validation depends on Spring's method-validation infrastructure and proxy invocation.

### "@Validated only needs to be placed on parameters"

Not the standard way to enable AOP method validation on a Spring service. For service method-validation proxies, type-level `@Validated` is the critical signal. Parameter-level `@Validated` belongs to MVC/data-binding group selection.

### "Any proxy intercepts every method"

False. Proxies intercept only eligible calls/methods. `private`/`final`/`static` methods and self-invocation have well-defined limits depending on proxy type.

### "@Transactional and @Validated always execute in source annotation order"

False. Annotation source order does not dictate advisor order. Exact transaction boundaries depend on infrastructure advisor ordering.

### "ConstraintViolationException always comes from the database"

False. Jakarta Bean Validation and ORM/databases define similarly named exceptions at completely different layers.

### "Every validation failure is a client error"

False. Return-value violations and broken internal service contracts are server bugs. HTTP 400 fits invalid client inputs, not every method constraint violation.

### "Validation replaces database unique constraints"

False. Method validation cannot prevent all write paths or race conditions. Data integrity requires database constraints and transactions.

## 32. Design Principles for Maintainable Method Validation

1. **Place constraints at boundaries with clear contracts.** Public service methods shared across entry points are ideal spots.
2. **Separate annotations from execution mechanics mentally.** Declaring constraints does not mean Spring has invoked a validator.
3. **Use `@Validated` on Spring services for AOP method validation** in standard setups.
4. **Keep public methods proxy-interceptable.** Avoid relying on `private`/`final` methods.
5. **Never expect self-invocation to be intercepted.** Extract collaborator beans or validate explicitly.
6. **Use `@NotNull @Valid` when a nested object is both required and cascaded.**
7. **Follow contract inheritance rules.** On interfaces, avoid tightening parameter preconditions in overrides.
8. **Evaluate groups carefully before broad adoption.** `Default` constraints may be skipped when validating custom groups.
9. **Separate controller and service validation.** MVC 6.1+ uses native handler-method validation; services rely on AOP concerns.
10. **Do not map every method validation error to HTTP 400.** Distinguish client input errors from internal server bugs.
11. **Do not rely on annotations to guard transactional/database invariants.** Check state and use locking/constraints appropriately.
12. **Remember return-value validation timing.** It enforces output contracts yet does not undo prior side effects automatically.
13. **Test invocations through a Spring context.** Unit tests using `new` do not verify proxy behavior.
14. **Inspect proxies and exceptions per layer.** `ConstraintViolationException`, `MethodValidationException`, and `HandlerMethodValidationException` belong to distinct contexts.
15. **Handle validation failures properly in async/messaging.** Validation detects violations; retry/dead-letter policies handle operations.

## 33. Realistic Scenario: REST, Batch, and Messaging Sharing One Service

Suppose a resource allocation system has three entry points for allocation requests:

~~~text
HTTP POST /allocations
        |
        v
AllocationController
        |
        +-------------------------------+
                                        |
CSV import -> AllocationBatchRunner ----+--> AllocationService proxy
                                        |          |
Message -> AllocationMessageListener ---+          v
                                               Method validation
                                                    |
                                                Domain checks
                                                    |
                                               Database transaction
~~~

Service contract:

~~~java
@Service
@Validated
public class AllocationService {

    private final AllocationRepository repository;

    public AllocationService(AllocationRepository repository) {
        this.repository = repository;
    }

    @Transactional
    @NotNull
    public UUID allocate(
            @NotNull UUID resourceId,
            @NotNull UUID ownerId,
            @Positive int quantity
    ) {
        Allocation allocation =
                Allocation.create(resourceId, ownerId, quantity);

        repository.save(allocation);

        return allocation.getId();
    }
}
~~~

HTTP controller DTO validation rejects bad inputs early. Meanwhile, the batch runner and message listener bypass HTTP binding. Because all three inject the Spring-managed `AllocationService`, the same method contract is enforced via the proxy.

Inside `allocate(...)`, business invariants like "sufficient resource quota remains" still must check database state. `@Positive quantity` only rules out negative and zero values—it cannot ensure valid allocation under concurrent requests.

If a listener receives a malformed message, error handling must avoid endless retries on unfixable payloads. If a transaction fails due to a unique constraint, that is a data integrity error distinct from method parameter violations.

This scenario highlights where method validation shines: guarding **reusable service boundaries** while Spring proxies, the database, and entry-point adapters each fulfill their own responsibilities.

## Conclusion

Method validation lets you place Bean Validation constraints directly on parameters, nested objects, and return values of methods. In Spring Boot, `@Validated` services are typically wired by `MethodValidationPostProcessor` and `MethodValidationInterceptor` using an **AOP proxy**. External callers entering through the proxy are checked before/after the target method; self-invocation, manually instantiated objects via `new`, or non-interceptable methods bypass validation.

Keep the roles distinct: `@Valid` triggers cascading, `@Validated` signals Spring integration and group selection, and constraints like `@NotNull` and `@Positive` declare the rules. In modern Spring MVC, controller handler-method validation can run natively inside MVC rather than through the service AOP path, producing different exception types and handling patterns.

Method validation is a contract-enforcement layer between components, never a substitute for transactions, domain invariants, or database constraints. Understanding call paths, proxy types, validation groups, advisor ordering, and exception boundaries lets you apply method validation consistently across REST, batch, scheduled, and messaging entry points without being surprised by annotations that "are there yet don't run".
