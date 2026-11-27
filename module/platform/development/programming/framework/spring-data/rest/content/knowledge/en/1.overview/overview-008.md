# Limitations of Spring Data REST with Multi-Step Workflows, Public Contracts, and Complex Domain Models

## Goal and scope

Spring Data REST automatically exports Spring Data repositories as HTTP resources. With a repository managing `Order`, an application can get a collection resource like `/orders`, an item resource like `/orders/{id}`, and search resources for published query methods. HTTP operations are typically mapped from CRUD repositories: reading collections/items, creating with `POST`, updating with `PUT` or `PATCH`, and deleting with `DELETE`.

Default representations typically use HAL, providing links for clients to discover resources. Spring Data REST also supports pagination, sorting, ALPS/JSON Schema metadata, projections, excerpts, validation, and REST lifecycle events.

This approach significantly reduces CRUD boilerplate when repositories and the domain model match the data clients need to access. It is useful for internal APIs, admin tools, or data services with simple write rules.

Limitations emerge when the API must express business intent, protect a stable public contract, or hide a complex domain structure. Spring Data REST exports resources based on repositories; it does not determine use cases, workflows, business permissions, or aggregate boundaries on behalf of the application.

## 1. CRUD cannot express multi-step business workflows

CRUD describes operations on the state of a resource:

- `POST /orders`: create an order.
- `GET /orders/{id}`: read an order.
- `PUT /orders/{id}`: replace the resource representation.
- `PATCH /orders/{id}`: partially update the resource.
- `DELETE /orders/{id}`: delete the resource.

A business workflow describes valid actions and the preconditions required to execute them. For example, an order may move through states `DRAFT → SUBMITTED → APPROVED → SHIPPED`. Only submitted orders can be approved; only approved orders can be shipped. If a client can send `PATCH {"status":"SHIPPED"}`, it could bypass inventory checks, approval permissions, payment, or state transition rules.

State transition rules should live inside the aggregate/domain object. Domain methods must reject invalid state transitions regardless of whether the call comes from a REST controller, a background job, or an internal use case. That way, invariants are protected at the authoritative owner of the object's state.

The Java 17 example below illustrates a domain object with valid state transitions. Save it as `OrderWorkflowDemo.java`:

```java
import java.util.Objects;
import java.util.UUID;

enum OrderStatus {
    DRAFT, SUBMITTED, APPROVED, SHIPPED
}

final class Order {
    private final UUID id;
    private OrderStatus status = OrderStatus.DRAFT;

    Order(UUID id) {
        this.id = Objects.requireNonNull(id);
    }

    void submit() {
        transition(OrderStatus.DRAFT, OrderStatus.SUBMITTED);
    }

    void approve() {
        transition(OrderStatus.SUBMITTED, OrderStatus.APPROVED);
    }

    void ship() {
        transition(OrderStatus.APPROVED, OrderStatus.SHIPPED);
    }

    UUID getId() {
        return id;
    }

    OrderStatus status() {
        return status;
    }

    private void transition(OrderStatus expected, OrderStatus next) {
        if (status != expected) {
            throw new IllegalStateException(
                "Cannot change order from " + status + " to " + next
            );
        }
        status = next;
    }
}

public class OrderWorkflowDemo {
    public static void main(String[] args) {
        Order order = new Order(UUID.fromString(
            "00000000-0000-0000-0000-000000000001"
        ));

        order.submit();
        order.approve();

        System.out.println(order.status());
    }
}
```

Compile and run with JDK 17 or later:

```text
javac OrderWorkflowDemo.java
java OrderWorkflowDemo
```

Exact output:

```text
APPROVED
```

If you call `ship()` right after creating the order, or call `approve()` twice, the domain object throws `IllegalStateException`. This standalone example focuses on invariants; in a real application, the aggregate typically includes JPA mappings, additional properties, a repository, and other domain rules.

### Placing actions in an application service

The controller should accept a command, validate input, and call an application service. The service loads the aggregate, invokes domain behavior, saves the result, and returns a DTO. Transaction boundaries are usually placed on the application service so database operations belonging to the same use case commit or roll back together.

The Spring integration skeleton below omits imports, JPA mappings, and full entity declarations:

```java
@RepositoryRestResource(exported = false)
interface OrderRepository extends JpaRepository<Order, UUID> {
}

record OrderView(UUID id, OrderStatus status) {
}

@Service
class OrderApplicationService {
    private final OrderRepository orders;

    OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public OrderView approve(UUID id) {
        Order order = orders.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found"
            ));

        order.approve();
        orders.save(order);

        return new OrderView(order.getId(), order.status());
    }
}

@RestController
@RequestMapping("/api/v1/orders")
class OrderCommandController {
    private final OrderApplicationService service;

    OrderCommandController(OrderApplicationService service) {
        this.service = service;
    }

    @PostMapping("/{id}/approve")
    public OrderView approve(@PathVariable UUID id) {
        return service.approve(id);
    }
}
```

The repository is still injected and used internally, while `@RepositoryRestResource(exported = false)` prevents Spring Data REST from exporting it as a REST resource. The dedicated controller provides the command endpoint `POST /api/v1/orders/{id}/approve`. If you want the controller to reside within Spring Data REST's namespace and use its base path configuration, you can use `@RepositoryRestController`; that controller is served under Spring Data REST's base path. Clearly choose one endpoint organization style to avoid accidentally exposing both CRUD and command endpoints for the same aggregate.

Endpoint names should express intent, such as `POST /orders/{id}/approve`, `POST /orders/{id}/cancel`, or `POST /orders/{id}/ship`. Do not let clients directly assign internal status fields. Request/response DTOs restrict the fields a use case accepts and returns, while reducing coupling between public JSON and persistence entities.

### Long-running workflows or workflows spanning multiple systems

A database transaction suits a short, clearly bounded use case. Never hold a transaction open while waiting on a payment gateway, shipping carrier, or remote service. For long-running workflows or multi-system coordination, consider:

- Persisting workflow progress state and coordinating steps with a process manager, workflow engine, or saga.
- Using a transactional outbox to record events to publish in the same transaction that updates data; a worker publishes events afterward with retry support.
- Designing idempotent commands or supporting an idempotency key so retries do not create duplicate side effects.
- Using optimistic locking, such as a `@Version` field, or version preconditions to detect two concurrent requests modifying the same aggregate.
- Explicitly defining intermediate states, timeouts, retries, compensations, and how to handle unresponsive external services.

If the workflow has not finished when the HTTP request ends, the API can return `202 Accepted` along with a link or identifier to poll progress status. If processed synchronously, clearly specify success outcomes and business errors; for example, `409 Conflict` for an invalid state transition. Status codes and error structures must be consistent across the API contract.

## 2. Events and validation: useful hooks, not a replacement for use cases

Spring Data REST emits events during the REST processing lifecycle, including `BeforeCreateEvent`, `AfterCreateEvent`, `BeforeSaveEvent`, `AfterSaveEvent`, `BeforeLinkSaveEvent`, `AfterLinkSaveEvent`, `BeforeDeleteEvent`, and `AfterDeleteEvent`. You can listen with `AbstractRepositoryEventListener` or use `@RepositoryEventHandler` alongside annotations such as `@HandleBeforeSave` and `@HandleAfterCreate`.

These hooks fit logic tied directly to the REST lifecycle: simple data normalization, extra checks, audit logging, or lightweight post-operation reactions. Spring Data REST also supports registering `Validator` instances per event, such as a validator before creating or saving a resource.

Do not hide entire payment, order approval, shipping, or multi-aggregate coordination workflows inside event handlers. Such logic is hard to see from endpoints, hard to reuse from internal flows, and hard to manage for retries and transactions. REST exporter events should also not be treated as a general-purpose domain event bus for all repository calls in the application. Let application services orchestrate use cases, domain objects enforce invariants, and domain events/outbox publish information outside transaction boundaries.

Bean Validation fits input data constraints such as required fields, lengths, formats, or numeric bounds. Domain methods fit rules dependent on state and business relationships. For example, checking that an order code string has a valid length is input validation; disallowing shipment of a canceled order is a domain invariant. These two layers of checks complement each other.

## 3. Public contracts can change along with repositories and entities

By default, Spring Data REST detects eligible repositories and builds resources based on them. Collection names are usually derived from domain class names; repository methods determine which HTTP operations and search resources can be exported. If a repository inherits full CRUD, the API may open up many read/write operations the moment the repository is added.

This creates coupling between persistence structure and the HTTP contract:

- Renaming an entity or repository can affect URIs, collection relations, or search resources.
- Adding a public method to a repository can cause a new search endpoint to appear.
- Adding, removing, or changing the type of an entity property can alter serialized JSON.
- Changing an association can affect how representations carry links or nested data.
- Changing an ID type or ID generation strategy can impact resource URIs and clients storing those URIs.

For a public API, internal changes can become breaking changes for clients. Hypermedia helps clients discover links and reduces URL hard-coding, yet it does not create a versioning, deprecation, or backward-compatibility policy on its own. HATEOAS does not replace API contract management.

### Controlling exported repositories and methods

Spring Data REST provides several mechanisms to limit the API surface:

- Use `@RepositoryRestResource(exported = false)` to keep a repository for the application without exporting it as a REST resource.
- Use `@RestResource(exported = false)` on repository methods or associations that must not be public.
- Configure `RepositoryDetectionStrategy.ANNOTATED` to export only repositories explicitly annotated with `@RepositoryRestResource`.
- Use `RepositoryRestConfiguration.getExposureConfiguration()` to disable HTTP methods globally or per domain type.
- Use `@RepositoryRestResource(path = "...", collectionResourceRel = "...")` and `@RestResource(path = "...", rel = "...")` when intentionally naming paths or relations.

These mechanisms control resource and method exposure; they do not replace authorization. You must configure Spring Security, method security, and test permissions for every operation. When securing repositories with method security, check all CRUD overloads that could be exported; securing one method does not automatically secure every similar method. Permissions must also be checked on association resources and search resources, not only collection/item resources.

### Designing a stable public contract

If an API serves partners or external clients, it is usually better to use dedicated controllers and DTOs:

1. Define request/response DTOs in business language rather than mirroring the entire entity.
2. Choose endpoints and HTTP methods by action; specify status codes, errors, pagination, and idempotency rules.
3. Version explicitly, such as `/api/v1`, and maintain a deprecation policy.
4. Map DTOs to application services/aggregates; do not bind requests directly onto entities containing internal or sensitive fields.
5. Write contract tests for JSON, status codes, links, and error scenarios to catch unintended changes.
6. Document compatibility guarantees and how clients should handle new fields, deprecated fields, or validation errors.

Spring Data REST provides ALPS and JSON Schema metadata, along with HAL for API discovery. These are useful aids for clients and tooling, but they do not replace the contract documentation, compatibility rules, and version testing a public API requires.

## 4. Complex domain models need clear representation boundaries

Spring Data REST organizes resources around repositories and domain objects. For associations, the API can provide links to related resources and association resources to read or modify relationships. If the related type has its own repository, representations typically use URI links; if not, related data may be embedded directly into the parent object's representation.

This is convenient for simple models, but can cause difficulties when:

- Aggregates have many bidirectional relationships, large collections, or deep nesting.
- Persistence entities contain internal fields, computed state, or role-specific data.
- Clients need an aggregated view tailored to a use case, differing from the entity/table structure.
- A change in the domain model must not break the public API.
- Reading a representation triggers loading many associations, causing N+1 queries or oversized payloads.
- Updating an association directly can bypass aggregate root rules.

Identify aggregate roots and relationship ownership rules. If an association may only be modified through aggregate root behavior, do not expose the association resource in a way that lets clients update it directly. If clients need an aggregated view, create a DTO/query model matching the use case rather than forcing representations to mirror the entire object graph.

### Using projections and excerpts appropriately

Projections let you select which properties appear in a representation. A projection can create a slimmer view, combine data into virtual properties, or include additional data needed for a screen. An excerpt projection can be applied by default to collection resources to produce a preview.

An excerpt projection configured for a collection does not automatically apply to a single item resource. Clients may need to specify a projection when reading an item. Test both collections and items to avoid assuming their representations are identical.

Projections are a tool for shaping returned data, not a security boundary. A projection can expose properties omitted by the default representation, including fields annotated with `@JsonIgnore` in certain configurations. Therefore, review every projection as an exported data surface. Never include passwords, tokens, secrets, or sensitive personal data in a projection simply because the original field is hidden.

Projections also do not replace command DTOs or domain behavior. If clients need a request structure different from the entity, or require operations governed by business rules, use dedicated DTOs and endpoints. For sensitive data or multiple access roles, explicit DTOs are usually easier to govern than shared projections.

## 5. Choosing an approach by API type

| Need | Suitable approach |
| --- | --- |
| Internal CRUD, simple entities, minimal write rules | Spring Data REST can export repositories directly. |
| Attribute-based search and simple pagination | Repository query methods and search resources may fit. |
| Multi-step workflows, state transitions, approvals, or payments | Command endpoints invoking application services and domain methods. |
| Public API needing versioning and backward compatibility | Dedicated controllers/DTOs; explicitly control paths, payloads, errors, and versioning policy. |
| Entities with many relationships or sensitive data | Restrict repository exposure; use reviewed DTOs/projections. |
| Application needing convenient CRUD alongside specialized use cases | Combine Spring Data REST for suitable CRUD with dedicated controllers/services for commands. |

You do not need to remove Spring Data REST from the entire application just because one workflow is complex. You can export repositories that genuinely fit and hide repositories that must go through dedicated use cases. The key is deciding explicitly which resources are public and ensuring all write paths preserve domain invariants.

## 6. Checklist before exporting a repository

- Does this repository truly represent a resource clients should read/write directly?
- Should clients be allowed to call every exported CRUD method? Do `save`, `delete`, or specific methods need to be disabled?
- Can the entity change without altering the public JSON contract?
- Do associations expose persistence structure or allow modifying relationships past business rules?
- Could projections/excerpts expose sensitive fields or trigger excessive data loading?
- Does authorization cover every method, search resource, and association resource?
- Do actions like approve, cancel, pay, and ship have explicit endpoints/use cases that enforce invariants?
- Do transactions span the proper use-case boundary? Do long workflows need outbox, saga, or idempotency support?
- Are there contract tests for HAL links, payloads, status codes, validation errors, and access permissions?
- Is there a versioning and deprecation policy for external clients?

If many answers remain unclear, restrict exports first and design the API through services/DTOs. Exporting a repository should be an intentional architectural decision, not an accidental side effect of creating an interface.

## References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing repository exposure and HTTP methods](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Overriding response handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html)
