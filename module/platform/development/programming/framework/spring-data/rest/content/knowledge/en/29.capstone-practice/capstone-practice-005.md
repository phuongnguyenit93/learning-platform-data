# Adding Validation, Auditing, and Data-Handling Events in Spring Data REST

## 1. Objective and How the Three Mechanisms Work Together

Spring Data REST exports repositories as REST resources. When a client creates or updates an entity, applications typically need three categories of behavior:

- **Validation:** checking input data and business rules before the repository saves the entity.
- **Auditing:** automatically recording who created, who modified, and when creation/modification occurred.
- **Repository events:** executing logic tied to request lifecycle steps such as before create, after save, or after delete.

Each mechanism serves a distinct purpose. Validation decides whether data is allowed to be written. Auditing records system-managed metadata. Event handlers connect exporter actions to application logic. Do not use event handlers to replace all validation, nor populate audit fields from client-supplied data.

Typical flow:

1. The request is converted into an entity by Spring Data REST.
2. The validator for the matching event checks the data before writing.
3. JPA lifecycle callbacks update audit metadata on persist/update.
4. The repository completes the save operation.
5. Spring Data REST publishes the corresponding event, allowing the application to run post-processing logic.
6. If external side effects must only run after transaction commit, forward an application event to a listener using transaction phase AFTER_COMMIT.

## 2. Validation for Repository Endpoints

### 2.1. Registering a Spring Validator by Bean Name

Spring Data REST provides a mechanism to register Validators by bean name. The bean name starts with the target event, followed by the domain type name and the Validator suffix.

Examples:

- beforeCreateOrderValidator: validates Order before creation.
- beforeSaveOrderValidator: validates Order before update.
- beforeCreatePersonValidator: validates Person before creation.

Example validator checking order number and total amount:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component("beforeCreateOrderValidator")
public class OrderBeforeCreateValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Order.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Order order = (Order) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "orderNumber", "order.number.required",
                "Order number is required"
        );

        if (order.getTotal() == null || order.getTotal().signum() <= 0) {
            errors.rejectValue(
                    "total", "order.total.positive",
                    "Order total must be greater than zero"
            );
        }
    }
}
~~~

Spring Data REST detects beans with the beforeCreate prefix and registers them for the corresponding creation event. A Validator must be a Spring bean; using @Component with an explicit name avoids mismatches from default bean naming rules.

If validation is needed on both create and update, register a separate validator for beforeSave or extract shared validation logic into a service called by both validators. Do not assume a beforeCreate validator automatically runs on update operations.

### 2.2. Using Jakarta Bean Validation

For common constraints like @NotBlank, @Size, @Email, and @Positive, you can use Jakarta Bean Validation. In Spring Boot, add the validation dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Place constraints on the entity or DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public class OrderInput {

    @NotBlank
    @Size(max = 40)
    private String orderNumber;

    @Positive
    private BigDecimal total;

    // getters and setters
}
~~~

Spring Data REST uses its own validating repository event listener. For Jakarta constraints to run during the exporter lifecycle, register a Spring Validator compatible with Bean Validation using an event-prefixed bean name. For example, LocalValidatorFactoryBean implements both Jakarta Validator and Spring Validator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration(proxyBeanMethods = false)
public class OrderValidationConfiguration {

    @Bean("beforeCreateOrderValidator")
    LocalValidatorFactoryBean beforeCreateOrderValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean("beforeSaveOrderValidator")
    LocalValidatorFactoryBean beforeSaveOrderValidator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

If you only need custom validation for a single event, you can use a Spring Validator directly as shown earlier. Do not mistake having @NotBlank on a field for every persistence path automatically running Bean Validation: verify that the validator is wired into the intended request path. Standard Spring MVC controllers also have their own @Valid mechanism; that mechanism does not replace Spring Data REST's validating repository event listener configuration.

### 2.3. Registering Validators Manually via RepositoryRestConfigurer

If you want centralized registration control in one configuration class, implement RepositoryRestConfigurer and add validators to the desired events:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;

@Configuration
public class RepositoryRestValidationConfiguration
        implements RepositoryRestConfigurer {

    private final OrderBeforeCreateValidator orderValidator;

    public RepositoryRestValidationConfiguration(
            OrderBeforeCreateValidator orderValidator) {
        this.orderValidator = orderValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeCreate", orderValidator);
    }
}
~~~

Use one of the two registration approaches: event-prefixed bean naming or manual registration. Do not register the same validator twice without an explicit reason, as the same validation may execute repeatedly.

### 2.4. Handling Validation Errors

When a validator adds errors to Errors, Spring Data REST rejects the write operation and returns validation errors to the client. Verify the actual HTTP status and response body for your Spring Data REST version; clients should never receive a generic 500 error for invalid input data.

Error messages should:

- Identify the invalid field and violated rule.
- Use stable error codes so clients can handle them programmatically.
- Avoid leaking internal details, SQL, or stack traces.
- Follow consistent conventions across repository resources and custom controllers.

## 3. Auditing with Spring Data JPA

Spring Data auditing can record timestamps and the principal performing changes. Core annotations:

| Annotation | Meaning |
|---|---|
| @CreatedBy | Entity creator |
| @CreatedDate | Creation timestamp |
| @LastModifiedBy | Most recent modifier |
| @LastModifiedDate | Most recent modification timestamp |

If you only need creation and modification timestamps, implementing AuditorAware is not required. AuditorAware is only needed when using @CreatedBy or @LastModifiedBy to determine the acting principal.

### 3.1. Declaring Metadata on the Entity

Example JPA entity Order:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    @CreatedBy
    @Column(updatable = false)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String createdBy;

    @CreatedDate
    @Column(updatable = false)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Instant createdAt;

    @LastModifiedBy
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String lastModifiedBy;

    @LastModifiedDate
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Instant lastModifiedAt;

    protected Order() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
~~~

@EntityListeners(AuditingEntityListener.class) connects the entity to Spring Data JPA's auditing callbacks. Listeners can be registered per entity with @EntityListeners or shared via orm.xml. Annotation-based metadata keeps entities less coupled than implementing the Auditable interface.

Audit fields are marked READ_ONLY so Jackson ignores values written in incoming requests. This provides a protection layer at JSON binding; you still need DTO design, access control, and update rules at the application layer. Never let clients dictate createdBy or createdAt.

### 3.2. Enabling Auditing

Declare @EnableJpaAuditing in configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {
}
~~~

When using @CreatedBy or @LastModifiedBy, provide an AuditorAware bean whose return type matches the audit field type:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

@Configuration
public class AuditorConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.of("system");
            }

            return Optional.of(authentication.getName());
        };
    }
}
~~~

This example uses the username from Spring Security. If the application stores a User entity in @CreatedBy, return the matching User type and look up the appropriate principal. For background tasks, you can return an explicit system account instead of null.

If the application does not use Spring Security, AuditorAware can read the actor from a dedicated context or return a system principal. Avoid trusting a username from a client-supplied request header unless that header is verified by an upstream gateway.

### 3.3. Controlling Timestamps and Data Types

Auditing supports temporal types such as Instant, Java 8 date/time types, long/Long, and certain legacy types. The default DateTimeProvider uses the current system time. You can configure dateTimeProviderRef if you need a custom clock for testing or timezone normalization.

Prefer storing timestamps as Instant or UTC and converting to display timezones at the API/UI layer. If tests require deterministic timestamps, provide a controllable DateTimeProvider/Clock rather than relying on the system clock.

## 4. Handling Repository Lifecycle Events

The Spring Data REST exporter publishes eight events when operating on entities:

| Event | Timing |
|---|---|
| BeforeCreateEvent | Before creating an entity |
| AfterCreateEvent | After creating an entity |
| BeforeSaveEvent | Before saving/updating an entity |
| AfterSaveEvent | After saving/updating an entity |
| BeforeLinkSaveEvent | Before saving an association |
| AfterLinkSaveEvent | After saving an association |
| BeforeDeleteEvent | Before deleting an entity |
| AfterDeleteEvent | After deleting an entity |

There are two primary ways to subscribe to events:

- Extend AbstractRepositoryEventListener and override the corresponding callbacks. This approach receives multiple domain types, so you must check the entity type yourself.
- Use @RepositoryEventHandler with annotations such as @HandleBeforeCreate or @HandleAfterSave. This allows declaring methods typed to specific domain classes and is usually easier to read.

### 4.1. Annotated Repository Event Handler

Example normalizing data before creation and publishing an application event after saving:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleAfterSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler(Order.class)
public class OrderRepositoryEventHandler {

    private final ApplicationEventPublisher eventPublisher;

    public OrderRepositoryEventHandler(
            ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @HandleBeforeCreate
    public void beforeCreate(Order order) {
        // Normalize required fields before saving.
    }

    @HandleAfterSave
    public void afterSave(Order order) {
        eventPublisher.publishEvent(new OrderChanged(order.getId()));
    }
}
~~~

Declare the application event:

~~~java
public record OrderChanged(Long orderId) {
}
~~~

Spring Data REST discovers beans annotated with @RepositoryEventHandler and registers methods with matching event annotations. The type of the method's first parameter determines the domain type. The bean must be Spring-managed, such as via @Component or @Bean.

Do not place email sending, HTTP calls, or message broker publishing directly inside these callbacks if those side effects must only run after commit. AfterSaveEvent marks a point in the exporter's lifecycle; the event name alone does not guarantee the transaction has committed.

### 4.2. Running Tasks After Commit

If the request runs inside a transaction, a listener can bind to the AFTER_COMMIT phase:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderChangedListener {

    private final OrderIndexService orderIndexService;

    public OrderChangedListener(OrderIndexService orderIndexService) {
        this.orderIndexService = orderIndexService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderChanged event) {
        orderIndexService.refresh(event.orderId());
    }
}
~~~

The listener is invoked only after the transaction commits successfully. If no transaction is active when the event is published, the listener does not run by default. Verify the actual transaction boundary of the Spring Data REST endpoint. Do not enable fallbackExecution=true unless executing even without a transaction is intentional.

If the listener needs to write to the database after commit, call a separate service bean using Propagation.REQUIRES_NEW. If an action must be reliably delivered to a broker even if the process crashes right after commit, consider a transactional outbox rather than relying solely on in-memory events.

## 5. Execution Order and Avoiding Metadata Overwrites

When creating or updating an entity through Spring Data REST, keep each mechanism scoped to its proper responsibility:

- Validators verify client-supplied data and domain rules before writes.
- AuditingEntityListener updates metadata during JPA lifecycle callbacks.
- Repository event handlers execute logic tied to exporter operations.
- Transactional event listeners run work dependent on transaction commit.

Do not set audit timestamps or usernames inside @HandleBeforeCreate / @HandleBeforeSave. Doing so can duplicate audit logic, produce wrong timestamps, or be overwritten by JPA callbacks. Likewise, do not rely on a post-save callback to check data that should have been rejected prior to writing.

For business rules that must hold across all write paths (REST, batch jobs, message consumers, internal services), enforce critical invariants in the domain/service layer or via database constraints. Spring Data REST validators only protect requests flowing through the exporter.

## 6. Testing Validation, Auditing, and Events

### 6.1. Testing Validators

You can unit test a Spring Validator independently using BeanPropertyBindingResult:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;

import static org.assertj.core.api.Assertions.assertThat;

class OrderBeforeCreateValidatorTests {

    private final OrderBeforeCreateValidator validator =
            new OrderBeforeCreateValidator();

    @Test
    void rejectsMissingOrderNumber() {
        Order order = new Order();
        BeanPropertyBindingResult errors =
                new BeanPropertyBindingResult(order, "order");

        validator.validate(order, errors);

        assertThat(errors.hasFieldErrors("orderNumber")).isTrue();
    }
}
~~~

Unit tests verify isolated rules. In addition, write integration tests to confirm Spring Data REST actually registers the validator by bean name and returns errors on HTTP requests.

### 6.2. Testing via MockMvc

Example testing the /orders repository resource endpoint:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderRepositoryValidationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsOrderWithoutOrderNumber() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"orderNumber\":\"\",\"total\":0}"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Adjust paths, JSON payloads, and status codes to match your resource mapping and Spring Data REST version. If the API uses a base path, prepend it to the URL. Inspect the response body to ensure clients receive meaningful field names and error codes. More importantly, verify that the entity is not persisted when validation fails.

### 6.3. Testing Auditing

Use a repository test to save an entity, flush, and read it back from a fresh persistence context:

~~~java
@DataJpaTest
@Import({JpaAuditingConfiguration.class, AuditorConfiguration.class})
class OrderAuditingTests {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void storesCreationAndModificationMetadata() {
        Order order = new Order();
        // Set required entity fields.

        Order saved = orderRepository.saveAndFlush(order);

        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("system");
    }
}
~~~

This example assumes the auditor returns system when no principal is logged in. If testing with a Spring Security principal, populate SecurityContext before saving and assert that createdBy/lastModifiedBy match the user. A fixed Clock can be used to test exact timestamps.

### 6.4. Testing Event Handlers

Verify both parts: the handler is registered and the right method executes when repository operations go through Spring Data REST. Use Spring's application event recorder or a test listener to capture OrderChanged. If the listener uses @TransactionalEventListener, test both commit and rollback; test transactions roll back by default at the end of a test, so commit explicitly if verifying AFTER_COMMIT behavior.

## 7. Common Errors and Fixes

| Symptom | Common Cause | Resolution |
|---|---|---|
| Validator does not run on POST | Bean name lacks beforeCreate prefix or has wrong domain type suffix | Check exact bean name, component scan, and create event |
| Validator runs on create but not on update | Only beforeCreate was registered | Register beforeSave separately or configure multiple events |
| @NotBlank is not enforced via repository endpoint | Constraint added without wiring Bean Validation to the validating repository event listener | Register LocalValidatorFactoryBean or Spring Validator with event-prefixed bean names |
| Validation runs twice | Same validator registered via both bean name and manual configuration | Pick a single registration mechanism |
| Valid entity is still rejected | supports() rejects the domain type or field path is wrong | Check supports(), property names, and Errors |
| createdAt or createdBy is always null | @EnableJpaAuditing not enabled or entity lacks AuditingEntityListener | Check configuration and entity listener registration |
| lastModifiedDate never changes | Entity is not dirty/updated or field mapping is wrong | Check transaction, dirty checking, flush, and callbacks |
| createdBy records the wrong actor | AuditorAware reads wrong principal or request lacks SecurityContext | Check authentication, anonymous handling, and principal type |
| Client overwrites audit fields | Fields are deserialized from JSON | Mark READ_ONLY, use DTOs, or block updates to system fields |
| Repository event handler is not invoked | Bean is not Spring-managed or annotation/domain type is wrong | Check @Component, component scan, and first method parameter type |
| External task runs even on database rollback | Invoked directly in AfterSave handler or via standard listener | Use @TransactionalEventListener(AFTER_COMMIT) |
| AFTER_COMMIT listener never runs | Event was published outside a transaction | Check transaction boundaries and publishing site |
| Audit test has no timestamps | Test slice did not import auditing config or listener is unregistered | Import config, check @EntityListeners, and flush the entity |

## 8. Implementation Checklist

1. Choose where validation rules live—DTO, entity, or service level—based on what needs protection.
2. Register Spring Validators for the appropriate events via event-prefixed bean names or RepositoryRestConfigurer.
3. If using Jakarta Bean Validation, ensure a provider is on the classpath and LocalValidatorFactoryBean is bound to the relevant events.
4. Enable auditing with @EnableJpaAuditing and register AuditingEntityListener on entities or the persistence unit.
5. Use AuditorAware when tracking creator/modifier; clearly define principals for users, anonymous requests, and background jobs.
6. Prevent clients from updating auditing metadata.
7. Use @RepositoryEventHandler for domain-specific lifecycle logic; ensure beans are Spring-managed.
8. Use @TransactionalEventListener(AFTER_COMMIT) for tasks that must run only after commit.
9. Write unit tests for validators and HTTP/repository integration tests for validation, audit metadata, and events.
10. Test error flows, rollbacks, unauthenticated requests, and write paths outside Spring Data REST.

## Official Documentation

- [Spring Data REST – Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST – Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST – RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data JPA – Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
- [Spring Data JPA – EnableJpaAuditing API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/config/EnableJpaAuditing.html)
- [Spring Data JPA – AuditingEntityListener API](https://docs.spring.io/spring-data/data-jpa/docs/current/api/org/springframework/data/jpa/domain/support/AuditingEntityListener.html)
- [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Framework – Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html)