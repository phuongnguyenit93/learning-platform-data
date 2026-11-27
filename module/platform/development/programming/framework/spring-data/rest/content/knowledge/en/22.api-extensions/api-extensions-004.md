# Writing Custom Business Endpoints Through the Service Layer

Spring Data REST automatically exposes repositories as REST resources, which works well for standard CRUD operations and query methods. When business requirements call for a domain-specific action — such as approving an order, confirming a payment, locking an account, or completing a workflow — you should create a custom endpoint and delegate processing to the service layer.

A common organization is:

1. **Controller** receives the HTTP request, validates input data, and translates the request into an application call.
2. **Service** executes the use case, enforces business rules, coordinates multiple repositories, and manages transactions.
3. **Repository** reads or persists entities via Spring Data.
4. **DTO/response model** defines the data accepted and returned by the API, keeping the HTTP contract decoupled from entity structure.

Controllers should remain thin and services should not depend on HTTP. That way, the same business logic can be invoked from Spring Data REST, other controllers, message consumers, or background tasks.

## 1. When Do You Need a Custom Endpoint?

Default repository resources work very well when clients need to create, read, update, or delete an entity following a CRUD model. Query methods fit searches with clear parameters.

However, many business actions do not map to a simple CRUD operation:

- Approving an order only when it is in PENDING status and the approver has permission.
- Confirming payment requires checking the transaction and updating the order status.
- Completing an order requires checking inventory, recording the timestamp, and creating history entries.
- Locking an account may require revoking login sessions and recording a reason.
- Cancelling a booking may require calculating fees, updating availability, and emitting an event.

In these cases, you should not force clients to call multiple repository endpoints in sequence to form a workflow. The server should execute the use case inside a service so business rules are enforced consistently.

## 2. Controller → Service → Repository Architecture

The processing flow should have clear boundaries:

~~~text
HTTP request
    |
    v
Custom controller
    |  bind, validate, map input
    v
Application service
    |  authorization, business rules, transaction
    v
Domain model + repositories
    |  load, change state, persist
    v
DTO / response model
    |
    v
HTTP response
~~~

Responsibilities of each layer:

| Component | Responsibility |
|---|---|
| Controller | URL mapping, HTTP method, request/response, status code |
| Request DTO | Describes the data clients are allowed to send |
| Service | Executes the use case, coordinates business logic and transactions |
| Domain entity | Enforces invariants and valid state transitions |
| Repository | Queries and persists data |
| Response DTO | Publishes API data according to the contract |

Do not place complex queries, state transition rules, or chains of repository operations directly inside controllers. Likewise, do not pass `HttpServletRequest`, `ResponseEntity`, or HTTP status codes into services.

## 3. Creating a Custom Endpoint in Spring Data REST

If the endpoint needs to sit under the Spring Data REST base path and use Spring Data REST's integration mechanism, you can use **`@RepositoryRestController`**.

Example of an order approval API:

~~~java
import jakarta.validation.Valid;

import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;

@RepositoryRestController
@RequestMapping("/orders")
public class OrderWorkflowController {

    private final OrderApplicationService orderService;

    public OrderWorkflowController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/{id}/approve")
    public ResponseEntity<OrderView> approve(
            @PathVariable Long id,
            @Valid @RequestBody ApproveOrderRequest request,
            Authentication authentication) {

        OrderView result = orderService.approve(
                id,
                request.getNote(),
                authentication.getName()
        );

        return ResponseEntity.ok(result);
    }
}
~~~

With the default base path configuration, the endpoint looks like:

~~~http
POST /orders/42/approve
Content-Type: application/json
Accept: application/json
~~~

Example body:

~~~json
{
  "note": "Order details verified"
}
~~~

**`@RepositoryRestController`** allows Spring Data REST to apply the base path and integrate the controller through its own mechanism. If you use a standard Spring MVC **`@RestController`**, the endpoint belongs to Spring MVC mappings; you must determine its URL, base path, CORS, and integration with your application configuration yourself.

Choose the annotation based on the endpoint's placement and desired contract. There is no need to create a custom controller if repository resources already satisfy the use case completely.

## 4. Using DTOs to Control Requests and Responses

You should not accept a JPA entity directly as the request body for a business action. DTOs help restrict the fields a client can send and prevent clients from overwriting internal properties.

Request DTO:

~~~java
import jakarta.validation.constraints.Size;

public class ApproveOrderRequest {

    @Size(max = 500)
    private String note;

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Response DTO:

~~~java
import java.time.Instant;

public class OrderView {

    private final Long id;
    private final String status;
    private final Instant approvedAt;
    private final String approvedBy;

    public OrderView(
            Long id,
            String status,
            Instant approvedAt,
            String approvedBy) {
        this.id = id;
        this.status = status;
        this.approvedAt = approvedAt;
        this.approvedBy = approvedBy;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public Instant getApprovedAt() {
        return approvedAt;
    }

    public String getApprovedBy() {
        return approvedBy;
    }
}
~~~

The controller uses **`@Valid`** to validate the request DTO before invoking the service. Important rules must still be checked in the service/domain because a use case can be invoked from multiple entry points.

The response DTO publishes only the data clients need. Do not return password hashes, internal tokens, sensitive audit information, or the entire entity object graph.

## 5. Placing Business Logic and Transactions in the Service

The service executes the use case. Example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;

    public OrderApplicationService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderView approve(Long orderId, String note, String actor) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() ->
                        new OrderNotFoundException(orderId));

        order.approve(actor, note);

        return new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getApprovedAt(),
                order.getApprovedBy()
        );
    }
}
~~~

The entity is responsible for enforcing state transition rules:

~~~java
public void approve(String actor, String note) {
    if (status != OrderStatus.PENDING) {
        throw new InvalidOrderStateException(
                "Only pending orders can be approved"
        );
    }

    this.status = OrderStatus.APPROVED;
    this.approvedBy = actor;
    this.approvedAt = Instant.now();
    this.approvalNote = note;
}
~~~

In this example:

- The service loads the entity inside a transaction.
- The domain method checks the current state before transitioning to APPROVED.
- The transaction spans both the read and modification operations.
- JPA dirty checking persists the changes when the transaction flushes/commits.
- The service returns a view, not a `ResponseEntity`.

If the use case needs to save multiple entities, update inventory, or record payments, coordinate them in the same service and define an appropriate transaction boundary.

## 6. Coordinating Multiple Repositories in One Use Case

A business workflow often spans multiple aggregates or repositories. For example, confirming an order requires checking the payment, updating the order, and recording an audit entry:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final PaymentRepository paymentRepository;
    private final OrderHistoryRepository historyRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            PaymentRepository paymentRepository,
            OrderHistoryRepository historyRepository) {
        this.orderRepository = orderRepository;
        this.paymentRepository = paymentRepository;
        this.historyRepository = historyRepository;
    }

    @Transactional
    public OrderView confirmPayment(Long orderId, String actor) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        Payment payment = paymentRepository.findSuccessfulByOrderId(orderId)
                .orElseThrow(() -> new PaymentNotConfirmedException(orderId));

        order.confirmPayment(payment.getId(), actor);

        historyRepository.save(
                OrderHistory.paymentConfirmed(order, actor)
        );

        return OrderView.from(order);
    }
}
~~~

This is a structural example; method and factory names must match your actual domain model.

**`@Transactional`** ensures database changes in the same transaction commit or roll back together. However, a database transaction cannot automatically roll back calls to payment gateways, email systems, or external services. For side effects outside the transaction, consider the outbox pattern, controlled retries, or an appropriate saga.

## 7. Choosing HTTP Methods and Response Statuses

Design endpoints according to the semantics of the operation:

| Intent | Common HTTP Method | Example |
|---|---|---|
| Send a command to perform an action | POST | **`POST /orders/42/approve`** |
| Idempotently set a state/value at a URI | PUT | **`PUT /orders/42/approval`** |
| Read a result or state | GET | **`GET /orders/42`** |
| Delete a resource or association | DELETE | **`DELETE /orders/42`** |

POST fits commands that trigger a business execution. If a client retries due to a timeout, the server may receive the same command multiple times; for payment or transaction-creating operations, design an idempotency key or duplicate-processing guard.

Choose response statuses based on the outcome:

- **`200 OK`**: the operation succeeded and returns a result representation.
- **`201 Created`**: the operation created a new resource; return **`Location`** pointing to that resource.
- **`202 Accepted`**: the command was accepted, but asynchronous processing is not yet complete.
- **`204 No Content`**: the operation succeeded and no response body is needed.
- **`400 Bad Request`**: invalid request.
- **`404 Not Found`**: target resource does not exist.
- **`409 Conflict`**: current state conflicts with the requested operation.
- **`403 Forbidden`**: user is authenticated but lacks permission.

Do not return 200 for every case. Status codes let clients understand outcomes without parsing arbitrary messages.

## 8. Validation, Authorization, and Error Handling

Controllers should validate input shape using Jakarta Bean Validation:

~~~java
@PostMapping("/{id}/approve")
public ResponseEntity<OrderView> approve(
        @PathVariable Long id,
        @Valid @RequestBody ApproveOrderRequest request,
        Authentication authentication) {
    // Call service
}
~~~

The service/domain continues checking business preconditions such as:

- Does the order exist?
- Is the order in a state that permits approval?
- Does the caller have permission to approve this order?
- Has the payment succeeded?
- Do related records satisfy invariants?

Authorization can be placed on the service method:

~~~java
@PreAuthorize("hasAuthority('order:approve')")
@Transactional
public OrderView approve(Long orderId, String note, String actor) {
    // Execute use case
}
~~~

Ensure method security is enabled with **`@EnableMethodSecurity`**. If permissions depend on ownership or tenant, check data scope in the service/repository instead of relying solely on broad roles.

Use meaningful business exceptions and map them to appropriate HTTP responses through an exception handler. For example:

- **`OrderNotFoundException`** → 404.
- **`InvalidOrderStateException`** → 409.
- **`PaymentNotConfirmedException`** → 409.
- **`AccessDeniedException`** → 403.

Never let the controller return stack traces or database details to clients.

## 9. Interacting with Default Repository Resources

Custom endpoints can coexist alongside repository resources:

~~~http
GET  /orders
GET  /orders/42
POST /orders
PUT  /orders/42
PATCH /orders/42
POST /orders/42/approve
~~~

CRUD endpoints still serve general data operations. The **`/approve`** endpoint expresses a dedicated business command.

Consider preventing clients from directly modifying sensitive status fields via generic PUT/PATCH if doing so could bypass the workflow. You can use DTOs/projections, **`@ReadOnlyProperty`**, security rules, or custom repository/controller policies to protect those fields per the API contract.

Do not create two endpoints with the same mapping and method, as that causes handler conflicts. Check the Spring Data REST base path and your custom controller's URL mappings to avoid overlap.

## 10. Recording Events and Side Effects

A use case may need to send emails, emit domain events, or notify another system. Do not place all external integration logic directly inside the controller.

You can publish an application event from the service after modifying domain state:

~~~java
public record OrderApprovedEvent(
        Long orderId,
        String approvedBy
) {
}
~~~

~~~java
@Service
public class OrderApplicationService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderApplicationService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void approve(Long orderId, String actor) {
        // Load order, validate, and update status...
        eventPublisher.publishEvent(
                new OrderApprovedEvent(orderId, actor)
        );
    }
}
~~~

If a listener performs side effects after commit, you can use **`@TransactionalEventListener(phase = AFTER_COMMIT)`**. When events must never be lost if the application stops between commit and publish, consider a transactional outbox rather than relying solely on in-memory events.

Do not use listeners to hide core logic that readers of the use case need to see. Rules governing whether an order can be approved belong in the service/domain; listeners are suited for secondary reactions after the event.

## 11. Testing Endpoints and Services

Both the HTTP layer and business logic should be tested.

**Service unit tests** verify domain rules:

- A PENDING order is approved successfully.
- A CANCELLED order cannot be approved.
- An unconfirmed payment cannot be confirmed.
- Repositories are called correctly and history is recorded.

**Controller integration tests** verify the HTTP contract:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderWorkflowControllerTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void approveOrderReturnsUpdatedView() throws Exception {
        mockMvc.perform(post("/orders/42/approve")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"note":"Checked"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("APPROVED"));
    }
}
~~~

This example assumes the endpoint mapping and test data have been set up. If the endpoint requires authentication or authorities, add a security test context and test 401/403 cases as well.

Also test:

- Invalid request DTOs are rejected.
- Non-existent IDs return 404.
- Invalid state transitions return 409.
- Transactions roll back when a database step fails.
- Retried commands do not produce duplicate side effects if the use case requires idempotency.

## 12. Common Pitfalls and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Controller contains heavy business rules | Logic placed in the wrong layer | Move the use case into the service/domain |
| Multiple endpoints duplicate the same rule | Business logic scattered across controllers | Reuse a single service method |
| Partial data saved when a later step fails | Transaction does not span all database operations | Place **`@Transactional`** boundaries on the service |
| Calling service from batch runs without a transaction | Transaction placed only on controller or not invoked through proxy | Place transaction on the service method and call via Spring bean |
| Client can modify sensitive status via PUT | Entity bound directly or generic update is too broad | Use DTOs, read-only fields, and dedicated command endpoints |
| Retries process payment twice | Command lacks an idempotency strategy | Use an idempotency key or appropriate lock/unique constraint |
| Custom endpoint is not under the base path | Wrong controller stereotype used | Use **`@RepositoryRestController`** for endpoints tied to Spring Data REST or configure MVC separately |
| HTTP returns success despite business failure | Exception swallowed or status code fails to reflect error | Use exception mapping and verify the response contract |

## 13. Design Checklist

- Create a custom endpoint only when repository CRUD/query resources cannot express the use case.
- Choose **`@RepositoryRestController`** if the endpoint belongs under the base path and integrates with Spring Data REST.
- Keep controllers thin: bind requests, validate input, call the service, and build responses.
- Use request/response DTOs to control the contract and writable fields.
- Place business rules and transactions in the service/domain.
- Use repositories for data access; do not let controllers orchestrate multiple repositories.
- Check authorization at the service or via method security when the use case needs protection.
- Choose HTTP methods, status codes, and idempotency based on business semantics.
- Isolate external side effects outside transactions and use an outbox when event delivery must be guaranteed.
- Test the service, HTTP contract, validation, authorization, and rollback behavior.

Official References:

- [Spring Data REST — Customizing the REST API](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-api.html)
- [Spring Data REST — Customizing HTTP endpoints](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Security — Method security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
