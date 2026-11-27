# Adding Links and Representations with RepresentationModelProcessor

## Objectives

After this lesson, you will be able to:

- Explain the role of RepresentationModelProcessor in Spring HATEOAS and Spring Data REST.
- Add custom links to an entity's representation.
- Build URLs using WebMvcLinkBuilder and controller method mappings.
- Add conditional links based on business state.
- Distinguish adding hypermedia links from changing JSON data structures.
- Test links appearing in HAL responses.

## 1. Representations in Spring Data REST

Spring Data REST automatically publishes repositories as REST resources. When a client calls an item endpoint, the response typically includes entity data along with hypermedia links under the **_links** property.

Example:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

The response may contain:

~~~json
{
  "id": 42,
  "status": "SHIPPED",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "purchaseOrder": {
      "href": "http://localhost:8080/orders/42"
    },
    "customer": {
      "href": "http://localhost:8080/orders/42/customer"
    }
  }
}
~~~

Links indicate which resources the client can navigate to. Clients should rely on the relations and hrefs provided by the server instead of constructing URLs from internal conventions.

However, an API sometimes needs to advertise an additional business action or resource for which the repository does not automatically generate links, for example:

- A link to view shipping details for an order.
- A link to download an invoice once the order is paid.
- A link to view processing history or moderation status.
- A link to invoke a business operation provided by a custom controller.

Spring HATEOAS provides **RepresentationModelProcessor** to add or adjust hypermedia links on a representation before the response is returned to the client.

## 2. How Does RepresentationModelProcessor Work?

RepresentationModelProcessor is a Spring HATEOAS extension point. The processor receives a representation model object, processes that model, and returns a model.

General declaration:

~~~java
public interface RepresentationModelProcessor<T extends RepresentationModel<?>>
        extends Ordered {

    T process(T model);
}
~~~

In a Spring Data REST application, common representation types include:

- **EntityModel<T>**: represents a single entity or object.
- **CollectionModel<T>**: represents a collection resource.
- **PagedModel<T>**: represents a collection with pagination information.
- A custom class extending **RepresentationModel<T>**.

A processor is typically registered as a Spring bean using **@Component**. Spring HATEOAS finds processors matching the representation type being constructed and invokes the **process** method.

Inside a processor, you can:

1. Read the representation's content if needed.
2. Inspect state or data already present in the model.
3. Create one or more Links.
4. Add links via **model.add(...)**.
5. Return the model.

A processor normally enriches hypermedia metadata. It does not create endpoints itself, persist data, or replace business logic in controllers or services.

## 3. Creating a Business Endpoint So the Link Has a Target

Suppose the application has a PurchaseOrder and needs to expose a link to view shipping information when the order has been shipped.

First, create the controller providing the corresponding endpoint:

~~~java
@RestController
@RequestMapping("/order-operations")
public class OrderOperationsController {

    private final OrderTrackingService trackingService;

    public OrderOperationsController(OrderTrackingService trackingService) {
        this.trackingService = trackingService;
    }

    @GetMapping("/{orderId}/tracking")
    public ResponseEntity<TrackingView> tracking(
            @PathVariable Long orderId) {

        TrackingView tracking = trackingService.findByOrderId(orderId);
        return ResponseEntity.ok(tracking);
    }
}
~~~

This endpoint handles the actual request. RepresentationModelProcessor only advertises the path to that endpoint to clients.

If the controller does not yet exist or the route does not handle requests, the link added to the response can still lead to a 404. Therefore, test both the link and the target endpoint.

## 4. Adding Links to EntityModel

For the PurchaseOrder item resource, you can write a processor as follows:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class PurchaseOrderRepresentationProcessor
        implements RepresentationModelProcessor<EntityModel<PurchaseOrder>> {

    @Override
    public EntityModel<PurchaseOrder> process(
            EntityModel<PurchaseOrder> model) {

        PurchaseOrder order = model.getContent();

        if (order != null && order.getStatus() == OrderStatus.SHIPPED) {
            model.add(
                linkTo(methodOn(OrderOperationsController.class)
                    .tracking(order.getId()))
                    .withRel("tracking")
            );
        }

        return model;
    }
}
~~~

Explanation:

- **RepresentationModelProcessor<EntityModel<PurchaseOrder>>** scopes the processor to single representations wrapping PurchaseOrder.
- **model.getContent()** retrieves the entity wrapped by the current representation.
- The **OrderStatus.SHIPPED** condition determines when the tracking link is advertised.
- **methodOn(...)** describes a call to the controller method so Spring HATEOAS can determine the link target.
- **linkTo(...)** constructs the link based on the controller's mapping.
- **withRel("tracking")** sets the relation name clients use to identify the link.
- **model.add(...)** adds the link to the representation.
- Returning the same model preserves default links and links added by other processors.

When an order has status SHIPPED, the HAL response may include:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "tracking": {
      "href": "http://localhost:8080/order-operations/42/tracking"
    }
  }
}
~~~

When the order is not yet shipped, the processor does not add the tracking relation. Clients can use the presence of the link to know whether that action is advertised in the current state.

## 5. Why Should You Use WebMvcLinkBuilder?

You can create a link from a static URL string:

~~~java
model.add(Link.of(
    "/order-operations/" + order.getId() + "/tracking"
).withRel("tracking"));
~~~

This approach is simple, but couples the processor directly to the path. When the controller changes its base path, mapping, or the application runs under a different context path, the URL string can become stale.

With **WebMvcLinkBuilder**, you can reference the controller method directly:

~~~java
Link trackingLink = linkTo(
    methodOn(OrderOperationsController.class)
        .tracking(order.getId())
).withRel("tracking");

model.add(trackingLink);
~~~

Benefits:

- The URL is derived from the controller mapping.
- Reduces path duplication across multiple places.
- Makes refactoring endpoints easier.
- Links are generated according to the application's current web configuration.

For an external URI or a URI supplied from configuration, **Link.of(uri).withRel("...")** remains a good option. Avoid constructing URLs via string concatenation when you can reference a controller method.

## 6. Adding Multiple Links and Conditional Links

A representation can advertise multiple navigation capabilities:

~~~java
@Override
public EntityModel<PurchaseOrder> process(
        EntityModel<PurchaseOrder> model) {

    PurchaseOrder order = model.getContent();

    if (order == null) {
        return model;
    }

    if (order.getStatus() == OrderStatus.SHIPPED) {
        model.add(
            linkTo(methodOn(OrderOperationsController.class)
                .tracking(order.getId()))
                .withRel("tracking")
        );
    }

    if (order.getStatus() == OrderStatus.PAID) {
        model.add(
            linkTo(methodOn(OrderOperationsController.class)
                .invoice(order.getId()))
                .withRel("invoice")
        );
    }

    return model;
}
~~~

This example assumes the controller has corresponding **tracking(...)** and **invoice(...)** methods.

You can apply the following principles:

- Advertise a link only when the action is valid for the business state.
- Use concise, stable, and meaningful relation names.
- Avoid adding multiple links with duplicate relations unless clients have clear handling rules.
- Keep link visibility conditions aligned with business rules at the endpoint.
- The target endpoint must still check permissions and state when a request is actually sent.

Hiding a link is not an authorization mechanism. Clients can construct requests to known URLs themselves; the controller/service must authenticate and reject invalid operations.

## 7. Adding Links to Collection and Paged Representations

Besides item resources, you sometimes need to add links at the collection level, for example:

- A link to create a new order.
- A link to download a summary report.
- A link to documentation or advanced filters.
- A link to an operation applying to the entire collection.

Spring HATEOAS lets you write processors for different representation models, such as **CollectionModel** or **PagedModel**.

Illustrative declaration example:

~~~java
@Component
public class PurchaseOrderCollectionProcessor
        implements RepresentationModelProcessor<
            CollectionModel<EntityModel<PurchaseOrder>>> {

    @Override
    public CollectionModel<EntityModel<PurchaseOrder>> process(
            CollectionModel<EntityModel<PurchaseOrder>> model) {

        model.add(
            linkTo(methodOn(OrderOperationsController.class)
                .createOrderDocumentation())
                .withRel("create-order-guide")
        );

        return model;
    }
}
~~~

The illustrative example above assumes the controller has a corresponding method for building the link. In a real project, the generic type must match the representation used by your Spring Data REST version.

In particular, paginated collections may be represented using **PagedModel**. If a processor is not invoked, check the actual model type and the processor's generic type. Do not assume a processor targeting a regular collection will automatically match every paged representation.

Verify item resources, collection resources, and search resources separately if the API needs to add links across multiple response types.

## 8. Custom Representation Models

RepresentationModelProcessor processes an already-created representation. If you need to change the JSON data structure—such as returning only a subset of fields or building an aggregated DTO—use a projection or a custom controller returning its own model.

Example of a custom model:

~~~java
public class OrderSummaryModel
        extends RepresentationModel<OrderSummaryModel> {

    private final Long id;
    private final String status;
    private final String customerName;

    public OrderSummaryModel(
            Long id,
            String status,
            String customerName) {
        this.id = id;
        this.status = status;
        this.customerName = customerName;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public String getCustomerName() {
        return customerName;
    }
}
~~~

A custom controller can return this model:

~~~java
@GetMapping("/{id}/summary")
public OrderSummaryModel summary(@PathVariable Long id) {
    OrderSummary summary = orderService.getSummary(id);

    return new OrderSummaryModel(
        summary.id(),
        summary.status(),
        summary.customerName()
    );
}
~~~

Then you can write a processor for **OrderSummaryModel** to add links:

~~~java
@Component
public class OrderSummaryProcessor
        implements RepresentationModelProcessor<OrderSummaryModel> {

    @Override
    public OrderSummaryModel process(OrderSummaryModel model) {
        model.add(
            linkTo(methodOn(OrderOperationsController.class)
                .tracking(model.getId()))
                .withRel("tracking")
        );

        return model;
    }
}
~~~

This separates two distinct responsibilities:

- The custom controller/DTO decides which data appears in the body.
- RepresentationModelProcessor adds hypermedia links to that model.

Do not use a processor as a substitute for projections or serializers when your main goal is to change the data schema.

## 9. Implementation Considerations

### Keep Processors Lightweight

A processor can be invoked while building representations. If processing each entity queries an extra repository or calls an external service, collection responses can incur N+1 queries or significant latency.

Do:

- Prefer using fields already present in the model.
- Avoid separate database queries per entity.
- If extra data is needed, consider batch queries or preparing data in the appropriate service layer.
- Do not perform data writes or side effects inside a processor.

### Do Not Lose Existing Links

If you only need to add links, call **model.add(...)** on the existing model and return it. Creating a new model from the entity can accidentally discard self links, association links, or links generated by Spring Data REST.

### Watch Out for Lazy Loading

Reading lazy entity properties inside a processor can trigger extra queries or fail if the persistence context is closed. Only access needed fields and clarify how data is fetched.

### Ensure Links Are Usable

An advertised link must point to an endpoint that actually exists. Verify:

- The HTTP method supported by the endpoint.
- Path variables and query parameters.
- Base path/context path.
- Response media type.
- Access permissions and business preconditions.

### Protect Data

Do not place secrets, tokens, credentials, or internal data inside hrefs. Relations and links should describe navigation capabilities the client is permitted to know about.

## 10. Testing RepresentationModelProcessor

Test both the case where the link is added and the case where it is not added.

Example with MockMvc:

~~~java
@WebMvcTest
class PurchaseOrderRepresentationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private PurchaseOrderRepository repository;

    @Test
    void shouldExposeTrackingLinkWhenOrderIsShipped() throws Exception {
        PurchaseOrder order = new PurchaseOrder(
            42L,
            OrderStatus.SHIPPED
        );

        given(repository.findById(42L))
            .willReturn(Optional.of(order));

        mockMvc.perform(
                get("/orders/42")
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.tracking.href").exists());
    }
}
~~~

This is an illustrative test structure; constructors, repositories, and test configuration must be adapted to your application. If the repository endpoint is configured differently, use the actual route.

Add tests for these scenarios:

1. A SHIPPED order includes the tracking link.
2. An order not yet SHIPPED does not include the tracking link.
3. The tracking link points to the correct endpoint and ID.
4. Requests to the tracking endpoint are handled properly.
5. Collection responses retain default pagination links.
6. Default Spring Data REST association links remain intact after the processor runs.
7. Unauthorized users are still rejected at the endpoint, even if they know the URL.

You can verify HAL responses using JSONPath, for example:

~~~java
jsonPath("$._links.self.href").exists()
jsonPath("$._links.tracking.href").exists()
jsonPath("$._links.customer.href").exists()
~~~

Beyond checking that a link appears, invoke the target endpoint to verify the link is genuinely navigable.

## 11. Practical Implementation Workflow

1. Identify the resource representation to extend: item, collection, paged collection, or custom model.
2. Choose a meaningful relation name and the corresponding target endpoint.
3. Create or verify the controller method handling the target endpoint.
4. Write a processor with a generic type matching the representation to process.
5. Register the processor with **@Component** in a Spring-scanned package.
6. Use **linkTo(methodOn(...))** to build links from controller mappings.
7. Add links via **model.add(...)** and return the model.
8. Verify business conditions, access permissions, and performance.
9. Call the repository endpoint with **Accept: application/hal+json**.
10. Verify relations and hrefs in the response; invoke the target endpoint.
11. Verify default links are not lost and collection pagination still works.

## 12. Practice Exercises

Given a PurchaseOrder with statuses CREATED, PAID, SHIPPED, and COMPLETED:

1. Create a custom endpoint to return tracking details for an order.
2. Write a **RepresentationModelProcessor<EntityModel<PurchaseOrder>>** to add the tracking relation when the order is in SHIPPED status.
3. Add an invoice relation when the order is PAID.
4. Explain why a processor does not replace permission checks in the controller.
5. Create a custom representation model containing ID, status, and customerName.
6. Write a processor for the custom model to add a link to the order details page.
7. Write tests verifying the links appear in the right states and hrefs point to the right endpoints.
8. Explain why querying a repository for each entity inside a processor can cause N+1 queries.

**Key Takeaway:** RepresentationModelProcessor is the place to extend hypermedia links on representations. Use an EntityModel processor for item resources, choose the right collection/paged model when processing collections, and use custom DTOs/models when you want to change data structure. Links help clients discover API capabilities; endpoints remain responsible for authentication, authorization, and business execution.

## References

- [Spring HATEOAS — Representation Models](https://docs.spring.io/spring-hateoas/reference/server/representation-models.html)
- [Spring HATEOAS — Hypermedia and Link Building](https://docs.spring.io/spring-hateoas/reference/server/links.html)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)
