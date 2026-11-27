# Limitations of the REST Exporter for Multi-Step Business Workflows and Cross-Resource Transactions in Spring Data REST

## Objectives

After this lesson, you will be able to recognize when the Spring Data REST repository exporter is no longer suitable for a use case; distinguish CRUD resources from business commands; organize multi-step workflows in application services; define transaction boundaries when multiple aggregates or resources change together; handle side effects and cross-database transactions with outbox/saga patterns; and design APIs that can evolve without leaking the persistence model.

## 1. What Does the Spring Data REST Exporter Solve Well?

Spring Data REST automatically generates REST resources from Spring Data repositories. For exported repositories, the framework can provide:

- Collection resources for reading lists and creating entities.
- Item resources for reading, updating, or deleting entities.
- Association resources for accessing or modifying links between entities.
- Search resources for exposed query methods.
- HAL links, profile metadata, pagination, and conditional request support.

This approach enables rapid CRUD API development for relatively simple domain models. Clients can discover resources through hypermedia without the application having to write controllers for each repository.

Example:

```java
@RepositoryRestResource(path = "products")
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Spring Data REST can export the `/products` collection and `/products/{id}` item resources. This is a suitable choice when HTTP operations closely mirror CRUD operations on a single aggregate and do not require complex business workflows.

## 2. When Is a CRUD Exporter Not Enough?

A multi-step business operation is usually not equivalent to a simple save call. For example, confirming an order may need to:

1. Check the Order status.
2. Verify the Customer is active.
3. Check and reserve inventory across multiple Products.
4. Calculate shipping fees and taxes.
5. Record a PaymentIntent.
6. Transition the Order status to CONFIRMED.
7. Emit an event for shipping and notification systems to continue processing.

If you only expose `PUT /orders/{id}` letting clients change the `status` field to `CONFIRMED`, clients can bypass inventory checks, payment checks, or authorization. The API permits mutating persistence state without representing the actual business operation.

Signs that the exporter is no longer sufficient:

- One operation must call multiple repositories or aggregates.
- Step ordering carries business significance.
- State transition conditions and invariants must be protected.
- A transaction must span multiple writes.
- There are side effects to a message broker or external system.
- The use case's input/output differs from the entity shape.
- Idempotency, retries, compensation, or workflow state is needed.
- Execution permissions depend on specific states or roles.

In these cases, creating a command endpoint that calls an application service expresses the business operation much more clearly.

## 3. Distinguishing Resource Operations and Business Commands

Resource operations act on a resource representation—for instance, GETting an Order or PATCHing a shipping address. Business commands ask the system to execute a meaningful action, such as:

- `POST /orders/{id}/confirm`
- `POST /orders/{id}/cancel`
- `POST /payments/{id}/capture`
- `POST /shipments/{id}/dispatch`

Commands typically have distinct inputs and outcomes. They do not necessarily allow clients to set internal status fields directly.

Example request:

```http
POST /api/orders/42/confirm
Content-Type: application/json
Idempotency-Key: 7f4f2b1c-...

{
  "paymentReference": "pay_123",
  "shippingMethod": "EXPRESS"
}
```

The response can return the Order representation after confirmation or a resource describing the accepted operation. The HTTP status depends on the synchronicity of the use case: `200 OK` if completed and returning the result, `202 Accepted` if the workflow continues asynchronously, or `409 Conflict` if the current state does not allow confirmation.

Command endpoints help APIs express intent and enforce business rules. Resource CRUD can still be used alongside them for simple, safe operations.

## 4. Moving Workflows into Application Services

The controller receives the HTTP request, translates it into a command, and calls the service. The service orchestrates repositories, domain operations, and transactions.

Example:

```java
public record ConfirmOrderCommand(
    Long orderId,
    String paymentReference,
    ShippingMethod shippingMethod) {
}
```

Service:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;
    private final PaymentRepository payments;

    public OrderApplicationService(
            OrderRepository orders,
            InventoryRepository inventory,
            PaymentRepository payments) {
        this.orders = orders;
        this.inventory = inventory;
        this.payments = payments;
    }

    @Transactional
    public Order confirm(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFoundException(
                command.orderId()));

        order.requireConfirmable();

        inventory.reserve(order.getLines());
        payments.recordAuthorization(
            order.getId(),
            command.paymentReference());

        order.confirm(command.shippingMethod());

        return orders.save(order);
    }
}
```

This example is abbreviated to show orchestration. In real applications, Payment may be an external system; in that case, do not call a payment provider and assume it rolls back with the database transaction. See the outbox/saga sections.

The service serves as a shared entry point for REST controllers, scheduled jobs, message consumers, or other workflows. Consequently, the same business operation is not implemented inconsistently across adapters.

## 5. Creating Custom Endpoints Alongside the Repository Exporter

With Spring Data REST, you can use `@BasePathAwareController` for controllers placed under Spring Data REST's configured base path:

```java
@BasePathAwareController
@RequestMapping("/orders")
public class OrderCommandController {

    private final OrderApplicationService orderService;

    public OrderCommandController(
            OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/{id}/confirm")
    public ResponseEntity<OrderResponse> confirm(
            @PathVariable Long id,
            @RequestBody ConfirmOrderRequest request) {

        Order order = orderService.confirm(
            new ConfirmOrderCommand(
                id,
                request.paymentReference(),
                request.shippingMethod()));

        return ResponseEntity.ok(OrderResponse.from(order));
    }
}
```

If using a regular `@RestController`, define the base path and routes to avoid conflicting with repository resources. Choose a clear command URL such as `/api/orders/{id}/confirm`, and decide whether that endpoint belongs to Spring MVC or the Spring Data REST base path.

Do not let controllers call multiple repositories directly. Controllers handle only the HTTP protocol, binding, request-level validation, and responses. Business rules, transactions, and orchestration belong in the application service/domain layer.

## 6. Restricting CRUD Operations That Could Bypass Workflows

If the repository exporter still lets clients edit sensitive fields directly, a custom command endpoint does not guarantee clients will go through the workflow. You must restrict the exposure of repository methods or fields.

Example hiding a repository method:

```java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Override
    @RestResource(exported = false)
    <S extends Order> S save(S entity);
}
```

This is only an illustrative example. Hiding `save` can affect create/update operations provided by Spring Data REST and requires testing behavior per version. You can hide the entire repository with `@RepositoryRestResource(exported = false)` if you want to expose only custom APIs, or use events, authorization, or custom repository designs for appropriate control.

Another option is using `@RestResource(exported = false)` for methods or associations that should not be exposed. For properties, use appropriate projections/input models so clients cannot modify internal fields like `status`, `approvedBy`, `paymentState`, or audit metadata.

Hiding endpoints does not replace authorization. Services must still verify that the actor has permission to execute commands on the specific resource.

## 7. Transaction Boundaries When Multiple Aggregates Change Together

If multiple repositories share one relational database and the same transaction manager, a single `@Transactional` on the service entry point can span the entire operation.

```java
@Transactional
public Order cancel(Long orderId) {
    Order order = orders.findById(orderId)
        .orElseThrow();

    order.requireCancelable();

    inventory.release(order.getLines());
    order.cancel();

    return orders.save(order);
}
```

When the method completes normally, the transaction commits. If an unchecked exception escapes the method, Spring rolls back the transaction by default. Checked exceptions do not trigger rollback automatically by default; configure `rollbackFor` if needed.

```java
@Transactional(rollbackFor = Exception.class)
public Order cancel(Long orderId) throws Exception {
    // Business steps
}
```

A transaction guarantees that changes belonging to the same transactional resource commit or roll back together. It does not automatically turn multiple databases or HTTP services into a single atomic transaction.

Do not wrap each repository operation in a separate transaction if the use case requires end-to-end atomicity. Repositories participate in the active transaction when managed by the corresponding transaction manager.

## 8. Multiple Datasources and Cross-Resource Transactions

An application may use multiple databases—for example, Order in PostgreSQL, Inventory in another database, and Payment in an external service. `@Transactional` by default manages only the selected transaction manager; it does not automatically coordinate every datasource.

Determine:

- Which repository uses which datasource and transaction manager?
- Do the operations share the same database transaction resource?
- Is true atomic commit across resources required?
- If one step succeeds and another fails, how will the system recover?

With multiple independent datasources, XA/JTA can be used if supported by the environment and drivers, but distributed transactions increase operational complexity and coupling. Many systems choose eventual consistency using outbox/saga patterns and compensating actions.

Never claim that "the entire workflow rolls back" if an HTTP payment request or message publish has already completed outside the database transaction. A database rollback cannot automatically undo those side effects.

## 9. Transactional Outbox for Post-Commit Events

Suppose creating an Order requires publishing `OrderCreated` to a message broker. Saving the Order and publishing the message inside the same method introduces two failure modes:

- The database commit succeeds, but publishing to the broker fails.
- The broker receives the message, but the database transaction subsequently rolls back.

The Transactional Outbox pattern closes this gap by storing the Order and the event record in the same database transaction:

```java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orders.save(Order.create(command));

    outbox.save(OutboxEvent.orderCreated(order.getId()));

    return order;
}
```

A background publisher reads unsent outbox records, publishes them to the broker, and marks them sent. If the publisher crashes after the broker receives the message but before updating the status, the message may be redelivered. Consumers need idempotency or deduplication.

Outbox guarantees that the database commit coincides with the intent to emit an event; it does not by itself guarantee exactly-once delivery.

CDC (Change Data Capture) can read the outbox table instead of polling. Choose the approach matching your infrastructure, throughput, and operational requirements.

## 10. Sagas for Multi-Service Workflows

A Saga models a distributed workflow as a sequence of local transactions. Each step commits in the service owning the data, then emits a command/event for the next step.

Example order placement:

1. Order service creates an Order in PENDING state.
2. Inventory service reserves stock.
3. Payment service authorizes payment.
4. Order service confirms the Order.
5. Shipping service creates a shipment.

If Payment fails after Inventory has reserved stock, the saga issues compensating commands to release stock and transitions the Order to PAYMENT_FAILED.

Sagas can be coordinated in two ways:

- **Choreography:** services react to each other's events; no central coordinator, though the overall flow becomes harder to observe as steps grow.
- **Orchestration:** a saga orchestrator coordinates commands, stores workflow state, and decides the next step; easier to track, at the cost of an added coordination component.

Compensating actions are separate business operations. For example, refunding money or releasing stock is not an ACID rollback of the prior transaction. Compensation itself can fail and requires retries, timeouts, manual intervention, or pending states.

## 11. Idempotency, Retries, and Duplicate Request Handling

Clients may retry on timeout even when the server already completed the command. If the command is not idempotent, retries can create duplicate payments or duplicate shipments.

You can accept an `Idempotency-Key` from clients:

```http
POST /api/orders/42/confirm
Idempotency-Key: 3a0f2f3d-...
Content-Type: application/json
```

The server stores the key along with the actor, operation, request fingerprint, and result. If the same key is resent with the same payload, return the recorded result. If the key matches but the payload differs, reject according to the contract.

Idempotency records should be stored in the same transaction as the business change whenever possible. For asynchronous workflows, the key can reference the operation resource so clients can poll its status.

Do not rely on HTTP POST being "called only once." Network retries, client refreshes, and message redeliveries can all produce duplicate requests.

## 12. Validation and Authorization at the Command Boundary

Command endpoints must validate inputs and execution permissions. Example:

```java
public record ConfirmOrderRequest(
    @NotBlank String paymentReference,
    @NotNull ShippingMethod shippingMethod) {
}
```

The controller uses `@Valid`:

```java
@PostMapping("/{id}/confirm")
public ResponseEntity<OrderResponse> confirm(
        @PathVariable Long id,
        @Valid @RequestBody ConfirmOrderRequest request) {
    // Call application service
}
```

The service must verify state-dependent invariants:

- The Order belongs to the current tenant.
- The Order is in a state that permits confirmation.
- The actor has permission to confirm.
- The payment reference belongs to the Order and has not been used by another operation.
- Inventory and business conditions remain valid at commit time.

Authorization must not rely solely on a user having `ROLE_USER`. Verify ownership/tenant and permissions on the specific resource. If a command runs from a background job or message consumer, identify the corresponding principal/service identity.

## 13. Returning Responses for Synchronous and Asynchronous Commands

If the command completes within the request, you can return the current representation:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

If the system only accepts the command and continues background processing, return `202 Accepted` with a link to an operation/status resource:

```http
HTTP/1.1 202 Accepted
Location: /api/operations/op-123
```

Clients follow the operation link to check statuses such as PENDING, RUNNING, SUCCEEDED, or FAILED. Retry-After or polling intervals can be used per contract.

Do not return `200 OK` with a CONFIRMED status if the workflow has only been enqueued. Responses must distinguish "accepted for processing" from "business operation completed."

## 14. Preserving HAL and Hypermedia in Custom Workflows

Custom endpoints can still return hypermedia representations. Spring HATEOAS supports `EntityModel`, `CollectionModel`, `RepresentationModel`, and link builders to generate links with the proper base path/context path.

Example response model:

```java
public EntityModel<OrderResponse> toModel(Order order) {
    OrderResponse body = OrderResponse.from(order);

    EntityModel<OrderResponse> model = EntityModel.of(body);
    model.add(linkTo(methodOn(OrderQueryController.class)
        .get(order.getId())).withSelfRel());

    if (order.canBeCancelled()) {
        model.add(linkTo(methodOn(OrderCommandController.class)
            .cancel(order.getId())).withRel("cancel"));
    }

    return model;
}
```

This is an illustrative example; controller method signatures and mappings must match your application. Expose command links only when the action makes sense in the current state. The server must still recheck conditions when receiving the command because state can change after the response was generated.

Hypermedia helps clients discover operations; it does not replace validation, transactions, or authorization.

## 15. API Evolution and Protecting the Domain Model

When the repository exporter exposes entities directly, mapping changes can unintentionally alter the HTTP contract:

- Adding a field can cause it to appear in representations.
- Adding an association can create new links.
- Changing repository paths changes URLs.
- Renaming enums or properties affects clients.
- Changing fetch strategies affects latency and serialization.

For public APIs or those needing long-term stability, consider:

- Using projections to control read representations.
- Using input DTOs/commands to control write data.
- Hiding repository methods/associations that should not be exported.
- Using custom controllers for workflows and contracts requiring versioning.
- Maintaining backward compatibility when changing relations, fields, or status codes.
- Writing contract tests for critical endpoints.

Do not let persistence entities accidentally become the API contract. Domain models can change due to database or business needs; APIs must be managed around consumer compatibility.

## 16. When Should You Still Use the Repository Exporter?

The repository exporter remains suitable when:

- Resources have simple CRUD.
- Operations primarily read/write a single aggregate.
- Associations and query methods have clear semantics.
- No multi-step workflows or out-of-transaction side effects are needed.
- Clients benefit from hypermedia discovery and pagination.
- Repository exposure can be bounded with authorization/projections.

An application can combine the repository exporter for reads and basic CRUD with custom command endpoints for sensitive workflows. There is no need to rewrite the entire API as manual controllers just because one use case is complex.

## 17. Common Design Pitfalls

**Allowing clients to PATCH internal status fields**

Clients can bypass workflows. Use command endpoints and restrict writable fields.

**Controllers orchestrating multiple repositories**

Business logic becomes tied to HTTP and hard to reuse. Move orchestration into application services.

**Assuming @Transactional spans multiple databases or HTTP services**

Identify actual transaction managers and resources. Use outbox/saga when distributed consistency is required.

**Publishing events directly inside a transaction and assuming atomicity**

Use a transactional outbox and idempotent consumers.

**Retrying commands without idempotency**

Duplicate requests can cause repeated effects. Use idempotency keys and store results.

**Hiding repository endpoints while forgetting custom endpoint authorization**

Enforce permission checks at the command/service boundary and every resource access path.

**Returning 200 when a workflow was only enqueued**

Use 202 and an operation resource to represent asynchronous processing state.

**Treating the entity model as an immutable API contract**

Use projections, DTOs, and contract tests to control representation changes.

## Summary

- Spring Data REST exporter fits simple CRUD resources; multi-step workflows need business commands and application services.
- Custom endpoints should accept commands, invoke services, and return responses accurately reflecting synchronous/asynchronous state.
- Restrict repository write exposure so clients cannot bypass business workflows.
- `@Transactional` manages only the resources of its transaction manager; multiple datasources or external services need dedicated consistency strategies.
- Transactional Outbox persists event intent within the database transaction; publishers/consumers need retries and idempotency.
- Sagas coordinate local transactions across services and use compensation when later steps fail.
- Use idempotency keys for retryable commands; verify validation, ownership, and authorization at the service boundary.
- Custom command endpoints can still return HAL links; hypermedia does not replace state and permission checks.
- Combine repository exporters for suitable CRUD with custom endpoints for complex business logic, while managing API evolution with projections, DTOs, and contract tests.

## References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing and extending](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring HATEOAS — Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Microservices.io — Saga pattern](https://microservices.io/patterns/data/saga.html)