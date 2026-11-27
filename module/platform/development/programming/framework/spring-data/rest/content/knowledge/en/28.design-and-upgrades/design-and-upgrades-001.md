# Distinguishing Repository-Exposed APIs and Custom-Designed Business APIs

Spring Data REST can automatically expose repositories as REST APIs. This approach is very convenient when an application needs convention-based read, create, update, and delete operations on data. However, a system's API is not just a collection of CRUD operations on tables or entities. Many features represent specific workflows, policies, and business semantics.

Therefore, when designing with Spring Data REST, it is necessary to distinguish between two types of APIs:

- **Repository API exposed by Spring Data REST:** resources and operations generated from repositories, entities, and associations.
- **Custom-designed Business API:** endpoints defined by the application to express a specific use case or business rule.

Both types of APIs can coexist within a single application. The key is drawing the right boundary: repository APIs fit simple data operations; business APIs fit the behaviors and workflows that clients need to execute.

## 1. What Is an Exposed Repository API?

Spring Data REST inspects exported repositories and creates corresponding HTTP resources. With a repository such as:

~~~java
@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products"
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Spring Data REST can provide resources by convention:

| Resource | Example | Purpose |
|---|---|---|
| Collection | \`GET /products\` | Read list of Products |
| Item | \`GET /products/10\` | Read a single Product |
| Collection create | \`POST /products\` | Create a Product |
| Item update | \`PUT /products/10\`, \`PATCH /products/10\` | Update a Product |
| Item delete | \`DELETE /products/10\` | Delete a Product |
| Search | \`GET /products/search/by-category?category=book\` | Invoke an exported query method |

The exact paths and methods depend on the repository, export configuration, associations, and application version. Clients should discover links in the HAL response rather than treating illustrative URLs as a fixed contract.

Spring Data REST typically returns a HAL representation. HAL contains data and hypermedia links such as \`self\`, links to collections, associations, or search resources. As a result, clients can discover exposed operations from the response.

Repository APIs have the following advantages:

- Reduce the amount of manual controller and CRUD mapping code to write.
- Leverage Spring Data conventions and the repository abstraction.
- Support pagination, sorting, and exported search resources.
- Provide hypermedia links for clients to discover resources.
- Fit resources with simple, straightforward data operations and minimal multi-step workflow dependencies.

For example, an internal product catalog management API may only need to read lists, view details, add, edit, and delete Products. A repository API can meet most of those needs without having to write a separate CRUD controller.

## 2. What Is a Custom-Designed Business API?

A business API describes functionality in the language of the business domain. Endpoints typically correspond to an action, a workflow, or a data view that the client needs.

For example, with orders:

~~~http
POST /api/orders
POST /api/orders/1001/confirm
POST /api/orders/1001/cancel
GET  /api/customers/42/order-summary
~~~

These endpoints express business meaning:

- Create an order.
- Confirm an order.
- Cancel an order according to policy.
- Retrieve an order summary for a customer.

An operation such as confirming an order may need to check the current status, inventory, payment, credit limits, user permissions, and record history. This is no longer a simple update of a few fields. A business API allows encapsulating that entire workflow into a clear use case.

Example controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderCommandsController {

    private final ConfirmOrderService confirmOrderService;

    public OrderCommandsController(
            ConfirmOrderService confirmOrderService) {
        this.confirmOrderService = confirmOrderService;
    }

    @PostMapping("/{id}/confirm")
    public OrderView confirm(@PathVariable Long id) {
        return confirmOrderService.confirm(id);
    }
}
~~~

Application service executing the use case:

~~~java
@Service
public class ConfirmOrderService {

    private final OrderRepository orderRepository;

    public ConfirmOrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderView confirm(Long id) {
        Order order = orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

        order.confirm();

        return OrderView.from(order);
    }
}
~~~

Here:

- The controller receives the HTTP request and delegates to the application service.
- The application service orchestrates the use case within a transaction.
- The domain object enforces state transition rules through \`order.confirm()\`.
- The response DTO \`OrderView\` defines the data returned to the client.

This example omits details such as authorization checks, inventory checks, and error handling per the API contract. In a real application, business steps must be implemented according to domain rules.

## 3. Comparing the Two API Approaches

| Criterion | Repository API (Spring Data REST) | Custom-Designed Business API |
|---|---|---|
| Starting point | Repository and domain entity | Use case and client contract |
| Goal | Resource operations via CRUD and associations | Execute business behaviors or workflows |
| Endpoints | Primarily follows repository conventions | Designed by the application |
| Request/response | Representation generated by Spring Data REST, customizable via projections | DTOs and schemas controlled by the application |
| Multi-step logic | Not a strength of default CRUD endpoints | Well-suited for orchestration via application services |
| Hypermedia | HAL and links generated by Spring Data REST | Designed by the application if needed |
| Pagination/search | Built-in via repository mechanisms and exported query methods | Defined by the application or reusing existing components |
| Contract control | Depends on repository configuration and representation | Explicitly controlled per endpoint |
| Initial cost | Low for standard CRUD | Higher because it must be designed and implemented |
| Best suited for | Simple CRUD, reference data, internal tools | Workflows, commands, summary reports, stable integration APIs |

You should not assume a business API is better in every case or that a repository API is always simpler in the long run. The right choice depends on the semantics of the operation, contract stability, and the level of control clients require.

## 4. When Should You Use a Repository API?

A repository API is a reasonable choice when most of the following conditions hold:

1. The resource has a relatively simple lifecycle and operations.
2. Clients genuinely need direct CRUD on that resource.
3. The representation closely matches the data the API intends to expose.
4. No multi-step workflow orchestration is needed per request.
5. Access permissions and data policies can be clearly controlled on the repository resource.
6. Clients can work with HAL and Spring Data REST hypermedia conventions.

Suitable examples:

- Managing lists of countries, provinces/states, or product categories.
- Looking up reference data.
- CRUD for internal configuration objects.
- APIs for admin tools with well-defined permission scopes.
- Resources with simple associations that can be represented with links.

Even with CRUD, you still need to decide which fields are allowed to be read or written, which repositories are exported, and which search methods are exposed.

### Example: Exposing a Restricted Repository

~~~java
@RepositoryRestResource(
    path = "categories",
    collectionResourceRel = "categories"
)
public interface CategoryRepository
        extends JpaRepository<Category, Long> {

    Optional<Category> findByCode(String code);

    @RestResource(exported = false)
    Optional<Category> findByInternalNote(String internalNote);
}
~~~

The query method \`findByCode\` can be exposed as a search resource by convention. The method \`findByInternalNote\` is marked \`exported = false\` so no corresponding search endpoint is generated.

If you do not want to export the entire repository, you can use:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
~~~

This is how you restrict the API surface at the repository level. Do not rely on clients not knowing the URL to protect an internal repository or method.

## 5. When Should You Design a Business API?

Use a dedicated business endpoint when a request represents a meaningful action beyond simply saving an entity.

Common indicators:

- An operation must coordinate multiple repositories or multiple aggregates.
- There are state transition conditions, e.g., an order can only be confirmed after payment.
- External services must be called or side effects must be produced.
- The request is a business-meaningful command, such as approve, publish, confirm, or cancel.
- The response is aggregated data from multiple sources.
- Different user groups are allowed to view or edit different fields.
- The external contract must remain stable even when internal entity structures change.
- Use-case-specific versioning, idempotency, auditing, or error models are required.

For example, if a client sends:

~~~http
PATCH /orders/1001
Content-Type: application/json

{
  "status": "CONFIRMED"
}
~~~

then the API is allowing the client to assign the status directly. This approach can bypass the domain confirmation workflow. A clearer endpoint is:

~~~http
POST /api/orders/1001/confirm
~~~

The server checks whether the order can be confirmed, executes the necessary steps, and changes the status through domain behavior.

Not every field update requires a command endpoint. Renaming a note or updating an attribute that does not affect business rules may fit a standard resource update. Base the choice on the meaning of the action rather than just lines of code.

## 6. Designing with a Hybrid Approach

An application can use Spring Data REST for standard data operations and a business API for critical use cases.

Example:

~~~text
Client
  |
  +-- GET /products
  |      |
  |      +--> Spring Data REST
  |               |
  |               +--> ProductRepository
  |
  +-- POST /orders/1001/confirm
         |
         +--> OrderCommandsController
                  |
                  +--> ConfirmOrderService
                           |
                           +--> OrderRepository
                           +--> InventoryService
                           +--> PaymentService
~~~

In this model:

- The Product collection is a resource that can be managed via the repository API.
- Confirming an order is a rule-heavy use case handled by the business API.
- Both can share repositories and the domain model.
- Business logic should reside in domain/application services according to responsibility, not duplicated between custom controllers and auto-generated endpoints.

A helpful rule of thumb is: **a repository is a data-access mechanism; a business API is the system's action contract**. Business services may use repositories, but clients should not have to understand repository structure to complete a business workflow.

### Separating Paths and Endpoint Ownership

If the same application exposes both types of APIs, establish clear path conventions. For example:

- \`/data/products\`: CRUD resource exposed by Spring Data REST.
- \`/api/orders/{id}/confirm\`: business endpoint designed by the application.

This is only an illustrative convention. Base paths and mappings must be configured consistently in the application; regular \`@RestController\` classes and controllers integrated into Spring Data REST have different mapping rules. Avoid having two controllers or repositories own the same path.

## 7. Customizing the Repository API Without Turning It into a Workflow Controller

Spring Data REST provides several useful extension points:

- \`@RepositoryRestResource\`: customize path, relation name, and repository export.
- \`@RestResource\`: customize relation/path name or disable export of a method/property.
- \`@Projection\`: reshape the representation to a published subset of properties.
- \`RepositoryRestConfigurer\`: customize Spring Data REST configuration.
- Repository event handlers: handle specific events before or after repository operations.

These mechanisms help tailor how repositories are exposed. They should not become the place holding entire complex business workflows.

For example, a projection can ensure a response contains only the fields needed by a list screen. However, a projection does not solve authorization on its own, does not replace a workflow service, and is not a sole security boundary. If a request requires multiple steps, create a dedicated use case and call a domain/application service.

Repository event handlers can be used for validation or reactions tied to repository operations. If the logic requires multi-step orchestration, retries, external service calls, transaction control, or explicit business results, an explicit application service is usually easier to read and test.

## 8. Do Not Expose the Entire Domain Model Just Because Repositories Exist

A common design mistake is exporting every repository and treating the generated endpoints as the default public API.

This can lead to:

- Clients accessing internal data unnecessarily.
- Query methods accidentally becoming search endpoints.
- Internal entities and associations turning into external contracts.
- Domain model changes altering representations that clients depend on.
- Clients performing CRUD operations that bypass business workflows.
- Difficulty controlling permissions per use case or per data field.

Only export the repositories the application actually intends to expose. Disable export for internal repositories, methods, or associations when not needed. For sensitive data, design controlled response DTOs or projections and enforce authorization on the server.

Measures like \`@JsonIgnore\`, hiding links in the UI, or using hard-to-guess URLs do not replace authorization. The server must verify whether the caller is allowed to read or modify a specific resource.

## 9. DTOs and Entities in Business APIs

Repository APIs typically represent entities via representations generated by Spring Data REST. Business APIs should treat requests/responses as endpoint-specific contracts.

Example DTOs for an order creation request:

~~~java
public record CreateOrderRequest(
    Long customerId,
    List<CreateOrderLineRequest> lines
) {
}

public record CreateOrderLineRequest(
    Long productId,
    int quantity
) {
}

public record OrderView(
    Long id,
    String orderNumber,
    String status,
    BigDecimal total
) {
}
~~~

The client sends the information needed to create an order. The server is responsible for:

- Checking that the customer and products exist.
- Validating quantities and inventory rules.
- Calculating prices according to system policies.
- Creating the entity and persisting it via the repository.
- Returning OrderView according to the API contract.

The client does not need to send a complete Order entity with internal fields such as server-calculated totals, confirmed status, or audit timestamps.

DTOs allow the application to retain control over the contract even when entities change. They also allow each use case to accept and return exactly the required data.

## 10. Security and Authorization

Whether using a repository API or a business API, security must still be enforced server-side.

For repository APIs:

- Export only necessary repositories.
- Disable query methods that should not be exposed.
- Configure authorization for collections, items, searches, and associations.
- Check permissions on individual resources, not only whether the user is authenticated.
- Do not expose sensitive fields via entities, projections, or nested associations.
- Review write operations that could alter domain state.

For business APIs:

- Authorize per use case and specific resource.
- Validate input data.
- Do not trust sensitive values sent by clients such as ownerId, price, status, or role.
- Handle errors according to a stable contract without returning stack traces or internal details.
- Use transactions for operations requiring consistency.
- Consider idempotency for commands that clients might retry.

If the application uses Spring Security, request authorization can be combined with method-level authorization such as \`@PreAuthorize\`. Specific policies must reflect domain roles and access rules.

## 11. Testing Both Types of APIs

Repository APIs need tests verifying what is actually exported:

- Root and collections have the expected links.
- Items and associations return the correct relations.
- Query methods are exposed with the right names and parameters.
- Internal repositories/methods do not appear.
- Pagination, sorting, and projections work according to the contract.
- Unauthorized callers cannot read or write resources.

Business APIs need tests verifying use case behavior:

- Valid requests produce the expected results.
- Requests in an invalid state are rejected.
- Callers lacking permissions cannot execute commands.
- Transactions roll back when a critical step fails.
- Response DTOs do not contain internal fields.
- Error responses preserve the documented status and structure.

Integration tests should be written at the HTTP boundary to confirm that routing, serialization, security, and persistence work together. Unit tests for application services verify business rules without depending on HTTP.

## 12. Decision-Making Process

You can use the following questions when choosing an API type:

1. Does the client only need to read or edit resource data with simple CRUD? If yes, consider a repository API.
2. Does the request carry a business action name like approve, confirm, cancel, publish, or settle? If yes, a business API is usually better.
3. Must a single request coordinate multiple aggregates or services? Use an application service and a business endpoint.
4. Does the response require aggregation or heavy customization for a specific use case? Use DTOs and a business API.
5. Is the resource internal-only or containing sensitive data? Restrict exposure and authorization; consider a dedicated endpoint with a controlled contract.
6. Do clients need HAL resource discovery and repository operations? Spring Data REST is a good fit.

If the answers fall between the two groups, you can combine them. For example, collection GET can use Spring Data REST while the publish command uses a dedicated business endpoint.

## 13. Feature Classification Examples

| Feature | Typically Suitable Design | Reason |
|---|---|---|
| View Category list | Repository API | Simple CRUD/read |
| View Product details | Repository API or DTO GET | Depends on representation and permissions |
| Find Product by code | Repository search or business query | Choose based on stability and query semantics |
| Create Order from cart | Business API | Needs validation of multiple data sources and rules |
| Confirm payment | Business API | Command with side effects and state control |
| Cancel Order | Business API | Has conditions, policies, and reversal logic |
| Rename an internal label | Repository API if simple CRUD | No separate workflow needed |
| Period revenue report | Business API | Aggregated data and custom contract |
| Manage reference data | Restricted Repository API | Independent resource, minimal workflow |
| Manage user permissions | Business API or dedicated admin API | Strict authorization and audit requirements |

These are initial selection guidelines. Specific domains may change the decision if an apparently CRUD operation carries business significance or special security requirements.

## 14. Conclusion

Spring Data REST helps expose repositories quickly as REST resources with conventions and hypermedia. It fits simple data operations that the application intentionally wants to export. Custom-designed business APIs fit use cases, workflows, commands, reports, and contracts requiring explicit control.

A system can use both. Let the repository API serve appropriate resource operations, let the business API express system behavior, and let application/domain services hold business rules. Only expose the repositories, methods, and data that clients truly need; always enforce access control on the server.

## References

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): how Spring Data REST exposes collection, item, association, and search resources.
- [Spring Data REST Reference — Exposing repository resources](https://docs.spring.io/spring-data/rest/reference/exposure.html): controlling which repositories and methods are exported.
- [Spring Data REST Reference — Configuring the REST URL path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html): customizing paths and REST API configuration.
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html): event handlers in the repository operation lifecycle.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): server-side authentication and authorization mechanisms.