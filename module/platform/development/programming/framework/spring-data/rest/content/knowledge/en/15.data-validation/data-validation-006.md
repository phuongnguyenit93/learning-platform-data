# Validation for Creation, Updates, and Association Changes

## Objective

Spring Data REST lets you validate data before a repository persists an entity and before changing associations. Validation should reside on the server side so every client must obey the same rules, regardless of whether requests come from a web UI, mobile app, or HTTP tool.

There are three flows to handle separately:

- **Creation:** validate the entity before saving via `POST`.
- **Update:** validate the entity state before saving via `PUT` or `PATCH`.
- **Association changes:** validate both the source resource and target resource before adding, replacing, or removing an association.

## Validation Layers

It is useful to distinguish four groups of checks:

1. **Request structure:** valid JSON, correct data types, syntactically valid association URIs, and existing target resources.
2. **Property constraints:** required fields, lengths, formats, value ranges, or counts.
3. **Business rules:** end date must be after start date, order number must be unique, or whether the current status allows transitioning to a new status.
4. **Relationship rules:** whether two resources are allowed to be linked, whether they belong to the same tenant, link count limits, or whether the target resource is in an allowed state.

Do not rely on UI validation to protect data. Clients can bypass the UI and call REST endpoints directly.

## Validation on Creation

When a client sends `POST` to a collection resource, Spring Data REST emits the `beforeCreate` event before the new entity is saved. This is the appropriate place to check conditions that only apply at creation time, such as required codes, valid initial state, or rules against duplicate creation.

Example `Order` entity using Bean Validation:

    import jakarta.validation.Valid;
    import jakarta.validation.constraints.NotBlank;
    import jakarta.validation.constraints.NotEmpty;
    import jakarta.validation.constraints.Positive;
    import jakarta.validation.constraints.Size;

    public class Order {
        @NotBlank
        @Size(max = 40)
        private String orderNumber;

        @NotEmpty
        @Valid
        private List<OrderLine> lines;

        @Positive
        private BigDecimal total;

        // getters and setters
    }

`@NotBlank` requires a string with non-whitespace content; `@Size` limits length; `@NotEmpty` requires a non-empty collection; `@Positive` requires a positive number; `@Valid` cascades validation to nested elements. Spring Boot 2 or older stacks use `javax.validation`; the example above uses the `jakarta.validation` namespace of newer versions.

To use these annotations, the application needs a Bean Validation provider, typically added via the `spring-boot-starter-validation` dependency. Make sure the validator is actually invoked in the Spring Data REST save flow; simply adding annotations to an entity does not replace configuring a validator for repository events.

## Registering Validators by Bean Name

Spring Data REST supports attaching a Spring `Validator` to an event using a bean naming convention. The name starts with the event, followed by the simple name of the domain type and the `Validator` suffix.

Example validator that only runs before creating an `Order`:

    import org.springframework.stereotype.Component;
    import org.springframework.validation.Errors;
    import org.springframework.validation.Validator;

    @Component("beforeCreateOrderValidator")
    public class BeforeCreateOrderValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Order.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Order order = (Order) target;
            if (order.getLines() == null || order.getLines().isEmpty()) {
                errors.rejectValue(
                    "lines",
                    "order.lines.required",
                    "An order must contain at least one line.");
            }
        }
    }

Spring Data REST recognizes the `beforeCreate` prefix and attaches this validator to the creation event. The name `Order` in the bean name must match the domain type the validator supports.

If you want to use a Bean Validation provider via a Spring Validator, you can register `LocalValidatorFactoryBean` with the corresponding event name. Example configuring two validators for both creation and update:

    @Configuration
    public class OrderValidationConfiguration {

        @Bean("beforeCreateOrderValidator")
        LocalValidatorFactoryBean validateOrderOnCreate() {
            return new LocalValidatorFactoryBean();
        }

        @Bean("beforeSaveOrderValidator")
        LocalValidatorFactoryBean validateOrderOnSave() {
            return new LocalValidatorFactoryBean();
        }
    }

Validators are invoked by event bean name; therefore verify your application has a provider and configuration matching your Spring version. If custom business rules are needed, you can write a custom Spring `Validator` as shown above or combine it with Bean Validation.

## Validation on Update

When a client updates an item resource using `PUT` or `PATCH`, Spring Data REST emits the `beforeSave` event before saving the entity. Register a validator named `beforeSaveOrderValidator` to inspect the state about to be saved.

Example:

    @Component("beforeSaveOrderValidator")
    public class BeforeSaveOrderValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Order.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Order order = (Order) target;
            if (order.getStatus() == OrderStatus.SHIPPED
                    && order.getShippingAddress() == null) {
                errors.rejectValue(
                    "shippingAddress",
                    "order.shippingAddress.required",
                    "A shipping address is required before shipping.");
            }
        }
    }

The condition in the example is a state-dependent business rule. It is checked right before the entity is saved, so it applies to both requests modifying a single property and requests replacing the representation.

With `PATCH`, the payload usually contains only the fields to change. Validate the entity state after changes have been applied, rather than requiring every field to appear in the JSON patch. For example, if the client only updates `status`, the validator can still inspect `shippingAddress` already present on the entity. With `PUT`, fields omitted from the representation may be treated as replaced values depending on binding; required constraints should accurately reflect the API's PUT contract.

Do not mechanically apply the exact same rules for create and update. A field might be required on creation yet immutable on update; a status might be valid initially yet disallowed from reverting once an order has shipped.

## Validation on Association Changes

Association changes have their own lifecycle. Spring Data REST emits the `beforeLinkSave` event when linking a source resource to a target resource. The event provides both objects: the parent and the linked object. This is the right place to check rules involving a pair of resources, such as whether an order and customer belong to the same tenant or whether the customer is active.

Example using a repository event handler:

    import org.springframework.data.rest.core.annotation.HandleBeforeLinkSave;
    import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
    import org.springframework.stereotype.Component;
    import org.springframework.web.server.ResponseStatusException;
    import org.springframework.http.HttpStatus;

    @Component
    @RepositoryEventHandler(Order.class)
    public class OrderAssociationHandler {

        @HandleBeforeLinkSave
        public void validateCustomerLink(Order order, Customer customer) {
            if (!order.getTenantId().equals(customer.getTenantId())) {
                throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Order and customer must belong to the same tenant.");
            }

            if (!customer.isActive()) {
                throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "An inactive customer cannot be linked to an order.");
            }
        }
    }

The first parameter is the source resource (`Order`); the next parameter is the linked resource (`Customer`). The domain type of the first parameter helps Spring Data REST select the corresponding handler. Use the association URIs published by the API and validate the exact objects resolved from the URIs.

For unlinking operations, current Spring Data REST versions also have the `beforeLinkDelete` event and `@HandleBeforeLinkDelete` annotation. You can enforce rules such as disallowing removing a customer from a locked order or disallowing clearing a required link. Verify the event/annotation exists in your application's dependency version before using it, as event APIs can differ across versions.

## Manual Validator Registration

If you prefer not to rely on bean naming conventions, you can register validators directly via `RepositoryRestConfigurer`:

    @Configuration
    public class RepositoryValidationConfiguration
            implements RepositoryRestConfigurer {

        private final Validator orderCreateValidator;
        private final Validator orderSaveValidator;

        public RepositoryValidationConfiguration(
                @Qualifier("orderCreateValidator") Validator createValidator,
                @Qualifier("orderSaveValidator") Validator saveValidator) {
            this.orderCreateValidator = createValidator;
            this.orderSaveValidator = saveValidator;
        }

        @Override
        public void configureValidatingRepositoryEventListener(
                ValidatingRepositoryEventListener listener) {
            listener.addValidator("beforeCreate", orderCreateValidator);
            listener.addValidator("beforeSave", orderSaveValidator);
        }
    }

This is an alternative to the bean name prefix. Do not register the same validator multiple times via both approaches unless you intend for validation logic to run repeatedly.

## Handling Validation Errors

When a validator detects an error, add the error to `Errors` using `reject` or `rejectValue`. Spring Data REST halts the save operation when validation fails and returns an error response to the client. Clients should inspect error details to know which field or rule failed.

For example, an error on the `lines` field might indicate:

    {
      "errors": [
        {
          "entity": "Order",
          "property": "lines",
          "message": "An order must contain at least one line."
        }
      ]
    }

The exact response structure depends on the Spring Data REST version and exception handling configuration. Verify actual status codes and bodies in integration tests; do not couple clients to a fixed error message if the API does not commit to an error schema.

Distinguish validation errors from other errors:

- Malformed data or business rule violations are usually returned as client errors (4xx).
- A nonexistent association URI may return `404 Not Found`.
- Unique key violations or data conflicts may raise database or conflict errors; map them clearly at the API layer.
- System failures such as an unavailable database should not be turned into generic validation messages.

Messages returned to clients should identify actionable fields and rules, without exposing SQL, internal table names, stack traces, or sensitive data.

## Validation Does Not Replace Database Constraints and Authorization

Application-level validation helps return friendly errors, but it is not the only line of defense:

- Use `NOT NULL`, `UNIQUE`, foreign keys, and appropriate constraints in the database to protect data integrity.
- Uniqueness checks in validators can encounter race conditions if two concurrent requests check before saving. Database unique constraints remain necessary; handle commit-time exceptions to return an appropriate conflict error.
- Use Spring Security and authorization to determine who can create, edit, or link resources. A business-valid association can still be forbidden to an insufficiently privileged caller.
- Perform tenant or ownership checks on the server based on authenticated identity, without trusting client-submitted tenant IDs.
- Place critical business logic in the service/domain layer so other REST flows and internal repository callers can share it.

## Verifying with Integration Tests

Test all three flows over HTTP, not just by calling validator methods directly:

1. `POST` an entity missing a required field: request is rejected and no new entity is saved.
2. `POST` a valid entity: receive a success response and data is persisted.
3. `PUT` or `PATCH` producing an invalid state: request is rejected and old data is preserved.
4. `PATCH` changing only one field: other fields retain their values and validation runs on the post-update state.
5. Changing an association with a valid URI that violates a business rule: handler rejects and the link does not change.
6. Changing an association validly: the link is saved and can be read back from the association resource.
7. Removing a forbidden association: handler rejects and the link remains.
8. Sending a request with an unauthorized user: authorization rejects even if data passes validation.

Example testing an invalid creation request with MockMvc:

    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "orderNumber": "",
                  "total": -10
                }
                """))
        .andExpect(status().is4xxClientError());

Adjust the payload, media type, and expected status to match the actual API. Beyond the status, verify the entity was not saved, the error response indicates the proper errors, and valid requests continue to work.

## Implementation Workflow

1. Declare constraints for simple data on entities or value objects.
2. Register `beforeCreate<DomainType>` validators for creation rules.
3. Register `beforeSave<DomainType>` validators for post-update state.
4. Use `@HandleBeforeLinkSave` and, when needed, `@HandleBeforeLinkDelete` to check resource pairs when changing associations.
5. Place shared rules in the service/domain layer; keep authorization in the security layer.
6. Keep database constraints for integrity and handle save-time conflicts.
7. Write integration tests for valid requests, invalid requests, PATCH, link, and unlink.

Spring Data REST validation should block invalid data right before saving or changing links. `beforeCreate`, `beforeSave`, and link events provide the exact hook points for the three flows; database constraints and authorization continue protecting integrity and access permissions.