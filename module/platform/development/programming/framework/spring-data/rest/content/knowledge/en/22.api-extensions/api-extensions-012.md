# The Boundary Between Extending Spring Data REST and Moving to a Custom DTO-Based API

## Context

Spring Data REST can publish Spring Data repositories as REST APIs with collection resources, item resources, association links, pagination, sorting, and hypermedia. This enables building CRUD APIs quickly and consistently while reducing handwritten controller boilerplate.

However, repositories and domain models are designed for persistence and internal application logic. They are not always the right API contract for every client. When an API requires a different data shape, multi-step business workflows, contextual access control, or long-term compatibility, continuing to extend repository resources directly can make the boundary between domain and API hard to manage.

Three directions are commonly used:

1. **Keep using Spring Data REST** when CRUD resources closely match the domain and public contract.
2. **Extend Spring Data REST** when you still want hypermedia/repository resources, but need additional metadata, projections, validation, event handling, or an operation closely tied to an existing resource.
3. **Create a dedicated DTO-based API** when clients need a contract decoupled from entities, use cases require explicit orchestration, or representations no longer fit the repository model.

There is no rule that DTOs are always better than entities or that custom controllers are always better than Spring Data REST. The decision should rest on the API contract, use case complexity, security, evolvability, and maintenance cost.

## 1. Start with the Domain Boundary and API Contract

Distinguish three layers:

| Layer | Responsibility | Example |
| --- | --- | --- |
| Domain model | State model and business rules | Order, Customer, OrderLine |
| Persistence model | How data is stored and queried | JPA entity, repository, association |
| API contract | Data and operations clients are allowed to use | JSON response, request DTO, HAL links |

In a simple application, these three layers can look nearly identical. Spring Data REST takes advantage of that to publish repositories directly. As a system grows, however, these layers develop different reasons to change:

- Entities change for schemas, relationships, or query optimization.
- The domain changes for business rules.
- The API changes for client needs, versioning, security requirements, or compatibility.

If a public API depends directly on every entity change, a persistence refactor can inadvertently become a breaking change for clients.

For example, an Order entity might contain customer, internalNote, paymentToken, and a list of line items. Public clients only need orderNumber, status, total amount, and creation date. Returning the raw entity forces strict control over which fields get serialized and risks leaking internal data.

DTOs establish an explicit contract:

    public record OrderSummaryDto(
        Long id,
        String orderNumber,
        String status,
        BigDecimal total,
        Instant createdAt
    ) {}

The API can return the exact fields needed without forcing clients to depend on entity structure.

## 2. When Should You Keep Spring Data REST?

Keep repository resources when the following conditions largely hold:

- Resources closely mirror the aggregates/domain objects managed by repositories.
- Standard CRUD is the primary way clients interact.
- Association links reflect the relationships clients need to discover.
- Pagination, sorting, search resources, and hypermedia already meet requirements.
- Read/write permissions can be expressed cleanly at the repository, domain, and security layers.
- Requests do not need to trigger complex multi-step business workflows.
- Representation shapes can be controlled without exposing persistence details.

For example, an internal catalog management application may fit repository resources well:

    @RepositoryRestResource(
        path = "products",
        collectionResourceRel = "products"
    )
    public interface ProductRepository
            extends JpaRepository<Product, Long> {
    }

Clients can discover collections, read items, follow association links, and use paging/sorting without manual CRUD controllers.

A good sign to stay with Spring Data REST is when clients genuinely benefit from hypermedia and operations are primarily reading and writing resources. If every client calls a set of handcrafted endpoints and ignores repository links and metadata, the benefit of publishing repositories directly diminishes.

## 3. Extensions That Still Fit Within Spring Data REST

Before building a completely separate API, check whether requirements can be solved with existing extension mechanisms.

### 3.1 Projections for Read Representations

Projections let you expose a restricted view of a resource without changing the entity:

    @Projection(
        name = "summary",
        types = Product.class
    )
    public interface ProductSummary {

        String getName();

        BigDecimal getPrice();

        String getCategory();
    }

Clients can request a projection via the `projection` parameter if the projection is exposed per Spring Data REST configuration:

    GET /products/42?projection=summary

Projections fit when:

- You only need to select a different subset of fields for read representations.
- The structure remains a view of the same single resource.
- No complex business calculations or multi-source coordination are required.
- Spring Data REST's projection mechanics are acceptable.

A projection does not automatically become a write DTO. It does not replace input validation, authorization, or a dedicated command model. For responses with a completely different structure or aggregating multiple aggregates, a dedicated DTO is usually clearer.

### 3.2 Excerpt Projections

Excerpt projections can define the default representation for items embedded in a collection resource. This is useful when collections need to show fewer fields than item details.

    @RepositoryRestResource(
        path = "products",
        excerptProjection = ProductSummary.class
    )
    public interface ProductRepository
            extends JpaRepository<Product, Long> {
    }

Clarify whether clients need a summary for a collection or a dedicated aggregation API. Excerpt projections address the representation shape of repository resources, not a business workflow.

### 3.3 Resource Processors and Hypermedia Links

If the resource already fits, but needs extra links or navigational metadata, you can use `RepresentationModelProcessor`:

    @Component
    public class ProductModelProcessor
            implements RepresentationModelProcessor<EntityModel<Product>> {

        @Override
        public EntityModel<Product> process(
                EntityModel<Product> model) {

            model.add(Link.of("/catalog/help")
                    .withRel("catalog-help"));

            return model;
        }
    }

The example only illustrates the idea of adding a link; in real applications, build links using an appropriate URI builder/hypermedia mechanism to avoid hardcoding hosts or base paths.

Resource processors fit when enriching representations with links, affordances, or metadata. They should not become a place to perform write business logic or heavy aggregation queries.

### 3.4 Repository Event Handlers

Spring Data REST provides repository event handlers such as `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleAfterCreate`, and `@HandleAfterSave`.

Example:

    @Component
    public class ProductEventHandler {

        @HandleBeforeCreate
        public void beforeCreate(Product product) {
            product.normalizeName();
        }
    }

Event handlers are useful for logic directly tied to the repository save lifecycle, such as normalizing a value or checking a simple condition.

Do not put an entire use case inside an event handler. If an operation needs to coordinate multiple repositories, call a payment service, emit events, control transactions, and return a custom result, an application service with API DTOs is much clearer.

### 3.5 Custom Controllers in the Spring Data REST Space

When you still want to add an endpoint tied to a repository resource and Spring Data REST routing, consider `@RepositoryRestController`. This mechanism fits small extensions within the same hypermedia model.

Conceptual example:

    @RepositoryRestController
    public class ProductRestController {

        private final ProductService productService;

        public ProductRestController(ProductService productService) {
            this.productService = productService;
        }

        // Additional endpoint mapped under the Spring Data REST
        // base path according to application configuration.
    }

Custom controllers still need clear boundaries. If an endpoint has an independent contract, its own DTOs, independent versioning, and a large workflow, a `@RestController` at the API layer is usually easier to understand than forcing everything into the repository namespace.

## 4. When Should You Move to a Custom DTO-Based API?

Consider a custom API when one or more of the following signs appear:

### 4.1 Representations Differ Significantly from Entities

Clients need an aggregated response spanning multiple aggregates, repositories, or systems:

    {
      "orderId": 42,
      "customer": {
        "displayName": "An Nguyen"
      },
      "items": [
        {
          "productName": "Keyboard",
          "quantity": 2
        }
      ],
      "payment": {
        "displayStatus": "PAID"
      },
      "availableActions": [
        "cancel",
        "download-invoice"
      ]
    }

This is a view model for a use case. It does not necessarily correspond to a single entity or repository. DTOs let you name and structure the response according to client needs.

### 4.2 Requests Are Commands, Not Entity Updates

For example, a user confirms an order:

    public record ConfirmOrderRequest(
        String confirmationCode,
        String note
    ) {}

    public record ConfirmOrderResponse(
        Long orderId,
        String status,
        Instant confirmedAt
    ) {}

Endpoint:

    POST /api/v1/orders/42/confirm

This is a business command. Clients should not submit the entire Order entity to request a state transition. The application service checks permissions, current state, confirmation code, and other conditions before performing the transition.

### 4.3 Multi-Step or Multi-Aggregate Orchestration Is Needed

A single request may need to:

1. Load the Order.
2. Check state and user permissions.
3. Verify inventory.
4. Call a payment service.
5. Update Order status.
6. Write audit logs and emit domain events.
7. Return results according to the use case contract.

This is application-layer orchestration. Placing this logic inside repository event handlers or entity setters makes the execution flow difficult to observe and test.

### 4.4 Strict Input/Output Control Is Required

DTOs let you define explicitly:

- Which fields clients may submit.
- Which fields the server computes itself.
- Which fields appear only in responses.
- Use-case-specific validation.
- Default values and compatibility rules.
- How errors are represented.

This is especially valuable for sensitive data, internal fields, read-only fields, or operations with side effects.

### 4.5 Independent Versioning and Client Compatibility Are Needed

A public API may need to maintain `/api/v1` while entities continue evolving. DTOs allow keeping the v1 contract stable and introducing v2 with a different representation without preserving the old persistence structure.

### 4.6 Specialized Queries or Performance Optimization Are Needed

A dashboard may require aggregations, SQL projections, read models, or caching very different from repository CRUD. A DTO API can call an optimized query service for that use case rather than forcing repository resources to serialize a large entity graph.

## 5. Designing a Custom DTO-Based API

A custom API typically has this structure:

    @RestController
    @RequestMapping("/api/v1/orders")
    public class OrderApiController {

        private final OrderApplicationService orderService;

        public OrderApiController(
                OrderApplicationService orderService) {
            this.orderService = orderService;
        }

        @GetMapping("/{id}")
        public OrderDetailDto getOrder(@PathVariable Long id) {
            return orderService.getDetail(id);
        }

        @PostMapping("/{id}/confirm")
        public ConfirmOrderResponse confirm(
                @PathVariable Long id,
                @Valid @RequestBody ConfirmOrderRequest request) {
            return orderService.confirm(id, request);
        }
    }

The controller handles HTTP concerns: routing, status codes, request binding, and responses. The application service coordinates the use case. The repository remains the data access port.

Illustrative package structure:

    order/
      api/
        OrderApiController.java
        OrderDetailDto.java
        ConfirmOrderRequest.java
        ConfirmOrderResponse.java
      application/
        OrderApplicationService.java
      domain/
        Order.java
        OrderStatus.java
      persistence/
        OrderRepository.java

This is a reference layering approach; you can organize by feature or module depending on existing architecture. What matters is that the API layer does not directly manipulate persistence arbitrarily.

## 6. Mapping Between Entities and DTOs

Mapping should occur at the application/API boundary using explicit code or a controlled mapper.

Example:

    public record OrderDetailDto(
        Long id,
        String orderNumber,
        String status,
        BigDecimal total
    ) {}

    public final class OrderMapper {

        private OrderMapper() {
        }

        public static OrderDetailDto toDetail(Order order) {
            return new OrderDetailDto(
                order.getId(),
                order.getOrderNumber(),
                order.getStatus().name(),
                order.getTotal()
            );
        }
    }

Application service:

    @Service
    public class OrderApplicationService {

        private final OrderRepository repository;

        public OrderApplicationService(OrderRepository repository) {
            this.repository = repository;
        }

        @Transactional(readOnly = true)
        public OrderDetailDto getDetail(Long id) {
            Order order = repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

            return OrderMapper.toDetail(order);
        }
    }

Explicit mapping lets readers see the exact fields exposed externally. For large mappings, you can use MapStruct or similar tools, while still reviewing mappings as part of the API contract.

Avoid returning JPA entities directly from custom APIs just to save a few lines of code. Lazy loading, bidirectional relationships, JSON circular references, sensitive fields, and schema changes can all make responses difficult to control.

## 7. Validation and Errors in DTO APIs

Request DTOs can use Jakarta Bean Validation:

    public record CreateProductRequest(
        @NotBlank
        String name,

        @NotNull
        @DecimalMin("0.01")
        BigDecimal price
    ) {}

Controller accepting requests:

    @PostMapping
    public ResponseEntity<ProductDto> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductDto created = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }

DTO validation checks input structure and constraints. Business rules such as “cannot confirm a cancelled order” should still be enforced in the domain/application service, because those rules must hold whether the command arrives from REST, a message consumer, or a batch job.

Custom APIs can also standardize errors using `@RestControllerAdvice` and Problem Details:

    @RestControllerAdvice
    public class ApiExceptionHandler {

        @ExceptionHandler(OrderNotFoundException.class)
        public ProblemDetail handleNotFound(
                OrderNotFoundException exception) {
            ProblemDetail problem = ProblemDetail
                    .forStatus(HttpStatus.NOT_FOUND);
            problem.setTitle("Order not found");
            problem.setDetail(exception.getMessage());
            return problem;
        }
    }

Keep error messages informative enough for clients without leaking SQL, stack traces, tokens, or internal data.

## 8. Security and Access Control

Whether using Spring Data REST or a custom DTO API, authorization must still be designed around resources and actions.

With Spring Data REST, you can combine Spring Security, repository events, method security, and exposure configuration. However, hiding a link or a field does not replace server-side authorization.

With custom APIs, you can protect methods/use cases:

    @PreAuthorize("@orderAuthorization.canRead(#id, authentication)")
    public OrderDetailDto getDetail(Long id) {
        // ...
    }

This example illustrates access control in an application service; the exact expression depends on your security beans and policies.

DTOs help restrict returned data, but do not prevent unauthorized access on their own. Always verify permissions before loading/returning sensitive data and before every command with side effects.

## 9. Can Both API Styles Be Used Side by Side?

Yes. An application can continue publishing repository resources for internal CRUD while simultaneously providing custom APIs for complex use cases.

Example:

    /data/products
    /data/products/42

    /api/v1/catalog/search
    /api/v1/orders/42/confirm
    /api/v1/orders/42/summary

In this example:

- `/data` is the base path dedicated to Spring Data REST repository resources.
- `/api/v1` is the namespace for application-managed API contracts.
- Custom APIs can invoke the same application services/domain logic as other flows.
- Do not maintain two conflicting sets of business rules for the same operation simply because there are two endpoints.

Separating namespaces helps operators and clients distinguish repository-generated APIs from use-case contracts. If both have write access to the same aggregate, ensure validation, transactions, and domain invariants are shared.

## 10. Decision Table

| Requirement | Appropriate Direction |
| --- | --- |
| Simple CRUD, resources close to domain | Spring Data REST |
| Changing read field sets of the same resource | Projection or excerpt projection |
| Adding hypermedia links/metadata | RepresentationModelProcessor |
| Simple logic tied to repository lifecycle | Repository event handler |
| Small endpoint tied to a repository resource | @RepositoryRestController |
| Request/response differs markedly from entity | Custom API with DTOs |
| Multi-step business command | Controller + application service + DTOs |
| Aggregating multiple aggregates or data sources | Query service/read model + DTOs |
| API versioning independent of entities | Custom API with DTOs |
| Permissions and returned data depend on use case | Custom API with DTOs and explicit authorization |

A practical rule of thumb: if a requirement only changes how the same repository resource is presented or navigated, prefer Spring Data REST extension points. If the requirement defines an independent use case and contract, create a custom API.

## 11. Warning Signs of Extending in the Wrong Place

Re-evaluate boundaries when you notice signs like these:

- Projections contain heavy calculation logic and call services.
- Repository event handlers coordinate multiple repositories or call external systems.
- Entities accumulate fields meant only for a specific UI screen.
- Clients have to submit an entire entity just to execute a single command.
- Controllers manually strip sensitive fields on every endpoint.
- Custom endpoints keep getting attached to repository resources even though hypermedia is no longer used.
- A single entity change causes breaking changes for unrelated clients.
- The same business rule executes differently between repository events and custom controllers.

These signs do not automatically prove a design is broken. They are signals to review layer responsibilities and real-world maintenance costs.

## 12. Safe Migration Path

When migrating an endpoint from a repository resource to a DTO API, proceed step by step:

1. Document the existing contract: URI, method, status codes, representation, links, validation, and authorization.
2. Identify the actual use case clients need, including inputs, outputs, and side effects.
3. Design request/response DTOs decoupled from entities.
4. Move business logic into a shared application service or domain service.
5. Create the new endpoint under a clear namespace/version.
6. Test mapping, validation, access permissions, transactions, and errors.
7. Migrate clients to the new endpoint according to a compatibility plan.
8. Monitor usage and stop exporting the old endpoint only once there is evidence no clients depend on it.

If the old endpoint is a public API, avoid sudden representation changes. You can maintain both paths during a transition period, provided they share business logic and have a defined end-of-support timeline.

## 13. Practice Exercise

Suppose a system has `OrderRepository` published by Spring Data REST. Clients currently use:

    GET /data/orders/42
    PATCH /data/orders/42

The product owner adds two requirements:

- The admin screen needs an aggregated response combining Order, Customer, Payment, and available actions.
- Users need to confirm an order using a confirmation code; this operation must verify inventory, payment, and order state.

Tasks:

1. Identify which parts still fit repository resources.
2. Design `OrderSummaryDto` for the admin screen.
3. Design `ConfirmOrderRequest` and `ConfirmOrderResponse`.
4. Build `OrderApplicationService` to orchestrate confirmation.
5. Create `POST /api/v1/orders/{id}/confirm`.
6. Keep `OrderRepository` as the persistence port and share domain invariants.
7. Verify read permissions for the summary and execution permissions for the command.
8. Write tests for successful confirmation, invalid code, out of stock, failed payment, and cancelled orders.
9. Decide which endpoints continue using Spring Data REST and which belong to the custom API.

Self-check questions:

- When is a projection sufficient, and when is a separate DTO required?
- Why shouldn't a command like confirming an order be modeled by having the client resend the entire entity?
- Should multi-step logic live in a controller, a repository event handler, or an application service?
- How do DTOs shield an API from entity changes?
- Can Spring Data REST and a custom API coexist in the same application?
- When migrating an old endpoint, what contract details must be preserved to avoid breaking changes?

## References

- [Spring Data REST Reference — Customizing the exposed REST API](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Framework Reference — REST Clients and Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
