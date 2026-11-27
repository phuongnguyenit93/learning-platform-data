# Writing Business Endpoints via Services and Adding HAL Links

## Objective

Spring Data REST automatically exports Spring Data repositories as REST resources. However, a business use case often involves more steps than basic CRUD: checking state, enforcing domain rules, coordinating multiple repositories, or calling other services, then returning a result with links so the client can continue its workflow.

For this type of use case, create a dedicated HTTP endpoint that delegates to an application service. The service is responsible for executing business logic and managing transactions; the controller is responsible for translating HTTP requests into service calls and formatting responses. When a response needs hypermedia, use Spring HATEOAS to build HAL links using APIs aware of controller or repository routes.

The example in this guide uses an order confirmation operation: `POST /orders/{id}/confirm`. This is an illustrative example; replace the domain, routes, DTOs, and business rules with your application's actual use case.

## 1. Separating Responsibilities Across Controller, Service, and Repository

A business endpoint typically spans three layers:

| Component | Responsibility |
|---|---|
| Controller / HTTP adapter | Declare route and HTTP method, parse/validate input, invoke service, select status/headers, and return representation |
| Application service | Execute use case, enforce permissions/business rules, coordinate repositories and external systems, define transaction boundaries |
| Repository | Read and write aggregate/domain data via Spring Data |

Controllers should not contain rules like "an order can only be confirmed once paid", nor should they coordinate multiple repositories directly. Place those rules in the domain/service layer so they can be invoked from HTTP, background jobs, or message handlers with identical behavior.

Services should return a business result or a DTO tailored to the use case. The controller converts that result into an HTTP representation. For public APIs, DTOs help control exposed fields and avoid accidentally serializing entire entities or lazy associations.

Example service:

~~~java
@Service
public class ConfirmOrderService {

    private final OrderRepository orders;

    public ConfirmOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public OrderSummary confirm(Long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm(); // Domain checks state and confirmation rules.
        Order saved = orders.save(order);

        return OrderSummary.from(saved);
    }
}
~~~

In this example, `Order.confirm()` protects domain invariants. The service orchestrates the operation and establishes the transaction boundary. If a use case needs to write multiple aggregates or emit events, keep all work requiring atomicity within the appropriate transaction; handle off-transaction work using a suitable consistency mechanism.

Do not let controllers call `repository.save()` and check state directly. Doing so couples business logic to HTTP and makes it easy to bypass when the use case is invoked elsewhere.

## 2. Choosing the Right Controller Annotation for Spring Data REST

Spring Data REST provides two key annotations for custom controllers:

- **`@RepositoryRestController`:** use when a custom handler belongs to the URI space of exported repositories—for example, adding an operation under `/orders/{id}` or overriding a handler for a specific resource/search. The controller is served under Spring Data REST's base path and participates in integrations such as message converters, exception handling, and CORS configured for repositories.
- **`@BasePathAwareController`:** use for custom operations placed under the base path that are not tied to a specific repository resource, such as an aggregated business workflow or orchestration endpoint.

A standard `@RestController` sits outside Spring Data REST's dedicated handling pipeline. It remains a valid Spring MVC API, but does not automatically receive Spring Data REST's request handling, message converters, and exception handling. Clearly decide which API pipeline owns a controller so two handlers do not compete for the same route.

For confirming an order, the route sits directly beneath the `orders` collection resource, so the example uses `@RepositoryRestController`:

~~~java
@RepositoryRestController
public class OrderBusinessController {

    private final ConfirmOrderService confirmOrder;
    private final RepositoryEntityLinks repositoryLinks;

    public OrderBusinessController(
            ConfirmOrderService confirmOrder,
            RepositoryEntityLinks repositoryLinks) {
        this.confirmOrder = confirmOrder;
        this.repositoryLinks = repositoryLinks;
    }

    @PostMapping("/orders/{id}/confirm")
    public ResponseEntity<EntityModel<OrderSummary>> confirm(
            @PathVariable Long id) {

        OrderSummary summary = confirmOrder.confirm(id);

        EntityModel<OrderSummary> model = EntityModel.of(summary);
        model.add(repositoryLinks
            .linkToItemResource(Order.class, id)
            .withRel("order"));
        model.add(repositoryLinks
            .linkToCollectionResource(Order.class)
            .withRel("orders"));
        model.add(linkTo(methodOn(OrderBusinessController.class)
            .confirm(id))
            .withRel("confirm"));

        return ResponseEntity.ok(model);
    }
}
~~~

This is a skeleton illustrating how to wire the components; add imports, validation, authorization, and exception mapping appropriate for your Spring Boot/Spring Data version. The example assumes the default collection relation is `orders`, the repository exports domain type `Order`, and corresponding services/DTOs exist.

If the route does not belong in a repository's URI space, switch to `@BasePathAwareController`. Do not apply `@RepositoryRestController` merely to share a URL prefix; that annotation also affects Spring Data REST handler mapping and integration behavior.

## 3. Generating HAL Links via APIs Instead of Manual String Concatenation

HAL uses `_links` to represent navigable relations. A business response can return a DTO alongside relevant links:

~~~json
{
  "id": 42,
  "status": "CONFIRMED",
  "total": 125.50,
  "_links": {
    "order": {
      "href": "https://api.example.test/orders/42"
    },
    "orders": {
      "href": "https://api.example.test/orders"
    },
    "confirm": {
      "href": "https://api.example.test/orders/42/confirm"
    }
  }
}
~~~

The URLs above are examples illustrating HAL structure. In code, use link-building APIs:

### Links to Repository Resources: `RepositoryEntityLinks`

Spring Data REST provides `RepositoryEntityLinks` to build links to repository-exported resources:

~~~java
repositoryLinks.linkToCollectionResource(Order.class);
repositoryLinks.linkToItemResource(Order.class, orderId);
repositoryLinks.linkToSearchResource(Order.class, "findByStatus");
repositoryLinks.linksToSearchResources(Order.class);
~~~

These methods generate links to a repository's collection, item, and search resources. They are aware of Spring Data REST's export configuration and reduce the risk of broken links when base paths, collection paths, or search paths change.

### Links to Custom Controllers: `WebMvcLinkBuilder`

When linking to a custom Spring MVC controller method, use `linkTo(methodOn(...))`:

~~~java
Link confirmLink = linkTo(
    methodOn(OrderBusinessController.class).confirm(orderId)
).withRel("confirm");
~~~

Spring HATEOAS inspects the controller/method mapping to construct the URI. If the route changes, the generated link updates from the mapping instead of duplicating URL strings in multiple places.

Never concatenate URLs via `"/orders/" + id` or hardcode host/port values. That breaks easily under base paths, servlet context paths, reverse proxies, or varying deployment configurations. Spring Data REST recommends `RepositoryEntityLinks` for repository-exported resources; Spring HATEOAS `linkTo` fits custom MVC endpoints written by the application.

### Choosing Meaningful Relation Names

Use stable, client-friendly relation names:

- `self`: the resource described by the current representation.
- `order`: link to the order resource.
- `orders`: link back to the collection.
- `confirm`: next business action available.
- `receipt`: link to a receipt if the use case generates one.

Do not use Java class names or internal method names as relations if they are meaningless to clients. If a custom link relation is shared across many clients, consider publishing documentation or a profile explaining its semantics.

## 4. Using RepresentationModel for Hypermedia Responses

Spring HATEOAS provides these core model types:

| Type | When to Use |
|---|---|
| `EntityModel<T>` | A single object/DTO accompanied by links |
| `CollectionModel<T>` | A collection accompanied by collection-level links |
| `PagedModel<T>` | A collection with pagination metadata |
| `RepresentationModel<T>` | Base type when defining custom representation models |

If multiple endpoints convert the same entity type into the same HAL structure, extract representation-building logic into a `RepresentationModelAssembler` rather than duplicating links across controllers:

~~~java
@Component
public class OrderSummaryAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderSummary>> {

    private final RepositoryEntityLinks repositoryLinks;

    public OrderSummaryAssembler(RepositoryEntityLinks repositoryLinks) {
        this.repositoryLinks = repositoryLinks;
    }

    @Override
    public EntityModel<OrderSummary> toModel(Order order) {
        OrderSummary summary = OrderSummary.from(order);

        return EntityModel.of(summary,
            repositoryLinks
                .linkToItemResource(Order.class, order.getId())
                .withSelfRel(),
            repositoryLinks
                .linkToCollectionResource(Order.class)
                .withRel("orders"));
    }
}
~~~

The assembler accepts a domain object and produces a consistently structured representation. For collections, use `toCollectionModel(Iterable)` to wrap a list into a `CollectionModel` containing the item models.

If an endpoint returns a business outcome that is not an entity, you can build `EntityModel<YourDto>` directly or create a dedicated DTO assembler. Do not force every response into an entity model if a DTO expresses the use case more cleanly.

## 5. Adding Links to Default Spring Data REST Representations

If the goal is simply to append a link to an entity representation already exported by Spring Data REST, you do not need to create a new CRUD endpoint. Use `RepresentationModelProcessor`:

~~~java
@Configuration
public class OrderRepresentationConfiguration {

    @Bean
    RepresentationModelProcessor<EntityModel<Order>> orderLinks(
            RepositoryEntityLinks repositoryLinks) {

        return model -> {
            model.getContent().ifPresent(order -> {
                model.add(repositoryLinks
                    .linkToCollectionResource(Order.class)
                    .withRel("orders"));
            });
            return model;
        };
    }
}
~~~

This example simply adds a collection link to the Order representation. In real applications, add links to workflows or related resources when sufficient data and preconditions are met. Spring Data REST discovers processors and invokes them when the exporter builds the corresponding representation.

Use a processor when enriching default responses across requests. Use a custom controller when introducing a new business operation with dedicated request/response semantics. Avoid creating a controller merely to duplicate data already served by a repository resource.

If a link should only appear when an order is in a confirmable state, evaluate that business condition before adding the link. Links serve as navigation hints for clients; the service must still re-verify the state when the action request arrives, because state may have changed between reading and acting.

## 6. Error Handling, Validation, and Consistency

A custom endpoint requires a clear error contract:

- Non-existent ID: return an appropriate not-found error.
- Invalid request body or parameter: return a validation error with understandable field/constraint details.
- Domain state prohibits the operation: return conflict or a business error per API policy.
- Unauthorized caller: return unauthorized/forbidden per security configuration.
- Infrastructure failures: preserve server error boundaries without leaking stack traces or internal details.

Validate input at the HTTP boundary using Bean Validation where appropriate, but do not rely on DTO validation to replace domain invariants. Services and domain objects must enforce rules even when invoked from other entry points.

Place transaction boundaries on application services or use case methods so commit/rollback aligns with business units of work. Avoid holding transactions open while calling external HTTP services whenever possible; consider outbox/event patterns or appropriate orchestration mechanisms when coordinating external systems.

For operations such as confirm, cancel, or pay, explicitly define idempotency, concurrency, and retry behavior. If two requests act on the same order simultaneously, the service must handle concurrent state transitions via optimistic locking, appropriate locking, or domain rules so the transition cannot execute twice.

## 7. Testing Endpoints and HAL Links

Use `@SpringBootTest` with `@AutoConfigureMockMvc` to test endpoints within the real application context. MockMvc exercises Spring MVC request handling without starting a real server.

Example verifying response data and links:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderBusinessControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void confirmReturnsOrderSummaryAndHalLinks() throws Exception {
        long orderId = 42L; // Fixture already created in the test database.

        mvc.perform(post("/api/orders/{id}/confirm", orderId)
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith("application/hal+json"))
            .andExpect(jsonPath("$.id").value(orderId))
            .andExpect(jsonPath("$.status").value("CONFIRMED"))
            .andExpect(jsonPath("$._links.order.href").exists())
            .andExpect(jsonPath("$._links.orders.href").exists())
            .andExpect(jsonPath("$._links.confirm.href").exists());
    }
}
~~~

In this example, `/api` is an assumed base path. Adjust the URL to match your application's `RepositoryRestConfiguration`/Spring Boot properties. Fixtures must be created in the test, and post-request state must be verified via the repository or corresponding read endpoint.

Add test cases for:

1. Valid ID and permitted state: service executes, response includes DTO and expected links.
2. Non-existent ID: not-found status, no data persisted.
3. Invalid state: business error returned and state remains unchanged.
4. Unauthorized caller: request rejected; use case is not executed when blocked at the HTTP boundary.
5. Two competing requests: only one state transition succeeds, or behavior matches the idempotency policy.
6. Links carry the proper base path and do not hardcode host/port.
7. Representation uses the HAL media type and accurate relation names.

You can use Mockito in narrow unit tests to verify the controller passes expected arguments to the service; still include integration tests with real services/repositories to verify transactions, serialization, security, and link mapping working together.

When deploying behind a reverse proxy or testing against a live server, add real HTTP-level tests for forwarded headers, HTTPS, and base paths. MockMvc does not simulate full servlet container or proxy behavior.

## 8. Workflow for Implementing a Business Endpoint

1. Define the use case, actors, pre/postconditions, and business errors.
2. Determine whether the endpoint belongs in a repository's URI space to choose between `@RepositoryRestController` and `@BasePathAwareController`.
3. Create request/response DTOs and appropriate validation; expose only necessary fields.
4. Implement the service to execute the use case, enforce domain rules, and manage transactions.
5. Write a thin controller: accept the request, call the service, build the response and status/headers.
6. Generate repository links with `RepositoryEntityLinks` and custom controller links with `WebMvcLinkBuilder`.
7. Use `EntityModel`/`CollectionModel` or an assembler to produce HAL representations.
8. Write tests covering success, error cases, security, concurrency, and link mapping.
9. Inspect the API root/collection and live responses to confirm clients can discover the endpoint/links.

## 9. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Custom route is not invoked | Controller annotation/mapping does not match URI space or base path | Check `@RepositoryRestController`/`@BasePathAwareController`, mappings, and base path |
| Route runs without expected converters/exception handling | Used `@RestController` outside Spring Data REST pipeline | Use the appropriate annotation if the route belongs under the API base path |
| Returned links have wrong host or missing base path | Manual URL concatenation or missing forwarded header config | Use `RepositoryEntityLinks`/`WebMvcLinkBuilder`; check proxy configuration |
| HAL response lacks `_links` | Returned a plain DTO/POJO or content negotiation mismatch | Return `EntityModel`/`CollectionModel` and request the HAL media type |
| Collection has links but individual items do not | Added links only at the collection level | Use an assembler to wrap each item in an `EntityModel` |
| Link appears even when action is invalid | Link added without checking state or permissions | Generate links conditionally; still re-check rules in the service at execution time |
| Controller contains too much logic | Domain rules and repository coordination placed inside the HTTP adapter | Move use case logic into an application service/domain object |
| Partial data updates occur on errors | Wrong transaction boundary or service calls external systems inside transaction | Wrap atomic writes in a transaction; design outbox/saga patterns for external systems |
| Tests pass but production links are wrong | MockMvc does not simulate proxies/ingress or real base paths | Add live-server/ingress tests and check forwarded headers |

## Official Documentation

- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html): `@RepositoryRestController`, `@BasePathAwareController`, response models, and aggregate references.
- [Spring Data REST — Integration](https://docs.spring.io/spring-data/rest/reference/integration.html): building links to collection, item, and search resources with `RepositoryEntityLinks`.
- [Spring Data REST — Customizing the JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html): `RepresentationModelProcessor` and adding links to default representations.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): resource model and HTTP behavior of repository exports.
- [Spring HATEOAS — EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html): single model containing content and links.
- [Spring HATEOAS — CollectionModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html): model for collections.
- [Spring HATEOAS — RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html): converting domain objects into representation models.
- [Spring HATEOAS — WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html): building links to Spring MVC controller methods with `linkTo` and `methodOn`.
- [Spring Framework — MockMvc](https://docs.spring.io/spring/reference/testing/mockmvc.html): testing Spring MVC requests/responses without starting a real server.