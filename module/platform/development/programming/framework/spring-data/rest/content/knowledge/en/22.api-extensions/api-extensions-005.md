# Returning EntityModel, CollectionModel, PagedModel, and ResponseEntity

When building APIs with Spring MVC, an endpoint can return domain data directly or use Spring HATEOAS types to describe resources along with navigation links. EntityModel, CollectionModel, and PagedModel represent resources in HAL/HATEOAS format; ResponseEntity lets you control the HTTP status, headers, and response body.

These four types address two separate layers of concern. HATEOAS models describe the content and links that clients can discover. ResponseEntity describes how the server sends the result over HTTP. You can combine them—for example, returning `ResponseEntity<EntityModel<OrderSummary>>` when you need both resource links and a specific status or header.

## 1. Why Do We Need Spring HATEOAS Model Types?

A basic REST API might return entity JSON:

~~~json
{
  "id": 42,
  "status": "CONFIRMED",
  "total": 125.50
}
~~~

The client receives the data, but must know the URLs ahead of time to perform subsequent actions. When using HATEOAS, the response can contain links such as self, collection, cancel, or payment. The client discovers available actions from the links provided by the server.

For example:

~~~json
{
  "id": 42,
  "status": "CONFIRMED",
  "total": 125.50,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/42"
    },
    "orders": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
~~~

Spring HATEOAS provides model classes for attaching links to representations:

- EntityModel<T> wraps a single resource.
- CollectionModel<T> represents a collection of resources without standard pagination metadata.
- PagedModel<T> represents a page of resources, with page metadata and navigation links.
- ResponseEntity<T> wraps an HTTP response, allowing you to set the status, headers, and body of type T.

EntityModel, CollectionModel, and PagedModel belong to Spring HATEOAS. ResponseEntity belongs to Spring MVC, in the org.springframework.http package. Do not treat ResponseEntity as a HATEOAS model type.

## 2. Returning a Single Resource with EntityModel

EntityModel<T> is suitable when an endpoint returns a single resource along with its links. Create the model using EntityModel.of(content), then add the required links.

Example domain DTO:

~~~java
public record OrderSummary(
    Long id,
    String status,
    BigDecimal total
) {
}
~~~

A controller can return EntityModel:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderSummary> getOrder(@PathVariable Long id) {
        OrderSummary order = orderService.findSummary(id);

        return EntityModel.of(
            order,
            linkTo(methodOn(OrderController.class).getOrder(id))
                .withSelfRel(),
            linkTo(methodOn(OrderController.class).listOrders())
                .withRel("orders")
        );
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderSummary>> listOrders() {
        return CollectionModel.empty();
    }
}
~~~

In this example:

- EntityModel.of(order, links...) builds the representation for an order.
- withSelfRel() creates the self relation pointing to the current resource.
- withRel("orders") creates a relation named orders.
- linkTo(methodOn(...)) builds URLs from the controller mapping, avoiding manual URL string concatenation.

Key imports:

~~~java
import org.springframework.hateoas.EntityModel;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

When the response is converted using the appropriate Spring HATEOAS configuration, the model is serialized into a representation containing the resource content and the _links section. If the API uses HAL, ensure the application configures the corresponding HAL message converter and media type.

EntityModel does not automatically fetch data from a repository or decide access permissions. The controller or service must still retrieve data, enforce business rules, and assemble the model.

## 3. Returning a Collection with CollectionModel

CollectionModel<T> is used when an endpoint returns multiple resources without requiring Page-style pagination metadata. T is commonly EntityModel<OrderSummary>, though it can also be another representation model.

Example creating each item model and wrapping them in CollectionModel:

~~~java
@GetMapping
public CollectionModel<EntityModel<OrderSummary>> listOrders() {
    List<OrderSummary> orders = orderService.findAllSummaries();

    List<EntityModel<OrderSummary>> items = orders.stream()
        .map(order -> EntityModel.of(
            order,
            linkTo(methodOn(OrderController.class).getOrder(order.id()))
                .withSelfRel()
        ))
        .toList();

    return CollectionModel.of(
        items,
        linkTo(methodOn(OrderController.class).listOrders())
            .withSelfRel()
    );
}
~~~

CollectionModel.of(items, links...) creates a collection representation. Each element can carry its own self link; the collection also has its own self link.

An illustrative HAL response:

~~~json
{
  "_embedded": {
    "orderSummaryList": [
      {
        "id": 42,
        "status": "CONFIRMED",
        "total": 125.50,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/42"
          }
        }
      },
      {
        "id": 43,
        "status": "DRAFT",
        "total": 80.00,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
~~~

The property name under _embedded can be customized using appropriate rel configuration or collection models. The example above only illustrates the HAL structure, not a mandatory rel name for every application.

CollectionModel suits small lists or unpaginated result sets. For large collections, paginate at the query layer instead of loading all records and packing them into a single response.

## 4. Returning Paginated Data with PagedModel

PagedModel<T> represents the contents of a single page along with metadata and navigation links. It fits when clients need to know the current page, page size, total elements, and how to move to other pages.

In Spring Data, a repository can return Page<T>:

~~~java
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(
        OrderStatus status,
        Pageable pageable
    );
}
~~~

In an MVC controller, you can use PagedResourcesAssembler<T> to convert Page<T> into PagedModel<R>. For example:

~~~java
@GetMapping("/search")
public PagedModel<EntityModel<OrderSummary>> searchOrders(
        @RequestParam OrderStatus status,
        Pageable pageable,
        PagedResourcesAssembler<PurchaseOrder> assembler) {

    Page<PurchaseOrder> page =
        orderRepository.findByStatus(status, pageable);

    return assembler.toModel(page, orderModelAssembler);
}
~~~

orderModelAssembler converts each PurchaseOrder into EntityModel<OrderSummary>:

~~~java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<
            PurchaseOrder,
            EntityModel<OrderSummary>> {

    @Override
    public EntityModel<OrderSummary> toModel(PurchaseOrder order) {
        OrderSummary summary = new OrderSummary(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        return EntityModel.of(
            summary,
            linkTo(methodOn(OrderController.class).getOrder(order.getId()))
                .withSelfRel()
        );
    }
}
~~~

Commonly used types:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
~~~

PagedResourcesAssembler.toModel(page, assembler) builds a PagedModel from a Page and applies the assembler to each element. The result can contain page metadata along with first, prev, self, next, and last links depending on the current position.

Illustrative HAL structure:

~~~json
{
  "_embedded": {
    "orderSummaryList": [
      {
        "id": 42,
        "status": "CONFIRMED",
        "total": 125.50,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/search?page=0&size=10"
    },
    "next": {
      "href": "http://localhost:8080/api/orders/search?page=1&size=10"
    },
    "last": {
      "href": "http://localhost:8080/api/orders/search?page=4&size=10"
    }
  },
  "page": {
    "size": 10,
    "totalElements": 45,
    "totalPages": 5,
    "number": 0
  }
}
~~~

PagedModel lets clients navigate based on server-provided links without deriving next-page URLs themselves. Page metadata also helps user interfaces display page numbers or total result counts.

If you do not use PagedResourcesAssembler, you can construct PagedModel manually with appropriate content and metadata. However, ensure navigation links and page info stay consistent with the actual query results.

## 5. Distinguishing CollectionModel and PagedModel

Both represent multiple resources, but their purposes differ:

| Type | Content | Pagination Metadata | Suitable Use Case |
|---|---|---|---|
| CollectionModel<T> | A collection of items. | No standard Page metadata. | Small lists or unpaginated result sets. |
| PagedModel<T> | Items of a single page. | Includes page metadata and navigation links when built properly. | Large datasets, queried page by page. |

Do not use CollectionModel to hold tens of thousands of records just because an endpoint needs to return a collection. Paginate at the repository using Pageable, then use PagedModel to represent the result.

PagedModel does not execute database queries itself. It only represents a page that has already been queried. The repository/service layer remains responsible for limiting records, sorting, and counting total elements as required.

## 6. Using ResponseEntity to Control the HTTP Response

ResponseEntity<T> lets the controller determine:

- HTTP status code.
- Response headers.
- Response body of type T.

Example returning a single resource with status 200:

~~~java
@GetMapping("/{id}")
public ResponseEntity<EntityModel<OrderSummary>> getOrder(
        @PathVariable Long id) {

    OrderSummary order = orderService.findSummary(id);
    EntityModel<OrderSummary> model = orderModelAssembler.toModel(order);

    return ResponseEntity.ok(model);
}
~~~

ResponseEntity.ok(body) produces an HTTP 200 OK response with the given body.

When creating a new resource, you can return 201 Created and Location:

~~~java
@PostMapping
public ResponseEntity<EntityModel<OrderSummary>> createOrder(
        @RequestBody CreateOrderRequest request) {

    OrderSummary created = orderService.create(request);
    EntityModel<OrderSummary> model =
        orderModelAssembler.toModel(created);

    URI location = linkTo(
        methodOn(OrderController.class).getOrder(created.id())
    ).toUri();

    return ResponseEntity.created(location).body(model);
}
~~~

ResponseEntity.created(location) sets status 201 Created and the Location header. body(model) attaches the representation with HATEOAS links.

Other ways to return responses:

~~~java
return ResponseEntity.noContent().build();          // 204 No Content
return ResponseEntity.notFound().build();           // 404 Not Found
return ResponseEntity.accepted().body(result);      // 202 Accepted
return ResponseEntity.status(HttpStatus.CONFLICT)
    .body(errorModel);                              // 409 Conflict
~~~

You can add custom headers:

~~~java
return ResponseEntity.ok()
    .header("X-Request-Id", requestId)
    .body(model);
~~~

Do not use status 200 for every scenario. Choose statuses that reflect the HTTP outcome: 201 when creating a resource, 202 when accepting asynchronous processing, 204 when succeeding without a body, 404 when not found, and 409 for appropriate business conflicts.

## 7. Combining ResponseEntity with HATEOAS Models

ResponseEntity accepts any body type. Therefore, it can be combined with EntityModel, CollectionModel, or PagedModel.

Examples:

~~~java
ResponseEntity<EntityModel<OrderSummary>>
ResponseEntity<CollectionModel<EntityModel<OrderSummary>>>
ResponseEntity<PagedModel<EntityModel<OrderSummary>>>
~~~

These types express:

- ResponseEntity manages HTTP status and headers.
- EntityModel, CollectionModel, or PagedModel manages representation and links.

Example search endpoint returning a page of results:

~~~java
@GetMapping("/search")
public ResponseEntity<PagedModel<EntityModel<OrderSummary>>> search(
        Pageable pageable,
        PagedResourcesAssembler<PurchaseOrder> assembler) {

    Page<PurchaseOrder> page = orderService.findPage(pageable);
    PagedModel<EntityModel<OrderSummary>> model =
        assembler.toModel(page, orderModelAssembler);

    return ResponseEntity.ok()
        .header("X-Result-Count", Long.toString(page.getTotalElements()))
        .body(model);
}
~~~

Here, PagedModel holds the items and pagination links; ResponseEntity sets status 200 and adds the X-Result-Count header.

If no status or header adjustment is needed, the controller can return EntityModel, CollectionModel, or PagedModel directly. Spring MVC serializes the object into the response body. Use ResponseEntity when the endpoint needs explicit control over the HTTP response.

## 8. When Should You Use DTOs and RepresentationModelAssembler?

You should not always return JPA entities directly from an API. Entities can contain lazy relationships, internal fields, sensitive data, or persistence structures unsuitable for a public contract.

DTOs define the exact data returned:

~~~java
public record OrderSummary(
    Long id,
    String status,
    BigDecimal total
) {
}
~~~

RepresentationModelAssembler<T, D> separates converting a domain object into a representation model:

~~~java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<
            PurchaseOrder,
            EntityModel<OrderSummary>> {

    @Override
    public EntityModel<OrderSummary> toModel(PurchaseOrder order) {
        OrderSummary summary = new OrderSummary(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        return EntityModel.of(
            summary,
            linkTo(methodOn(OrderController.class).getOrder(order.getId()))
                .withSelfRel()
        );
    }
}
~~~

Benefits:

- Cleaner controllers without duplicated link-building logic.
- Representations do not depend directly on entity structure.
- Internal or sensitive fields can be hidden.
- The same assembler can be reused for both items and collections.
- Links or DTOs can change with minimal impact on services and persistence.

An assembler only shapes the representation. Querying, authorization checks, business logic, and transactions still belong to the appropriate service/repository.

## 9. Default Spring Data REST vs. Custom Controllers

Spring Data REST automatically publishes repositories as REST resources and generates HAL links for supported operations. For standard repository endpoints, the framework already constructs representations and link discovery according to its configuration.

EntityModel, CollectionModel, and PagedModel commonly appear when an application builds custom controllers or customizes representations. You can use @RestController for standalone endpoints and return HATEOAS models as shown above.

If you use @RepositoryRestController to extend endpoints inside the Spring Data REST base path area, pay attention to mapping configuration and message converters to avoid conflicts with automatic repository controllers. Choose the controller type based on endpoint scope and verify actual URLs after application startup.

There is no need to manually wrap every default repository response in ResponseEntity just to add HATEOAS. Use custom endpoints when there is a distinct business or representation requirement; let Spring Data REST's automatic endpoints follow the framework's standard mechanism.

## 10. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Response lacks _links | Returning DTO/entity directly or missing HATEOAS/HAL configuration. | Return a HATEOAS model and check message converter/media type. |
| Wrong self link URL | Manual URL string concatenation or controller mapping changed. | Use linkTo(methodOn(...)) to derive links from mappings. |
| Collection returns too much data | Using CollectionModel for a large result set. | Paginate at the repository and return PagedModel. |
| PagedModel missing metadata or links | Building the model manually without passing page metadata or navigation links. | Use PagedResourcesAssembler or construct metadata/links consistently. |
| ResponseEntity returns wrong status | Using ok() for create, delete, and conflict cases alike. | Choose status based on HTTP and business outcome. |
| Serialization error on entity relations | Returning JPA entity with lazy relationships or circular references. | Use DTOs and RepresentationModelAssembler. |
| Duplicate or wrong rel links | Adding multiple links with the same relation or inconsistent rel names. | Standardize rel names and verify the returned representation. |
| Controller is not invoked | Mapping conflicts with an automatic repository endpoint. | Check base path, controller mapping, and controller type. |

## 11. Response Verification Workflow

After building the controller:

1. Call GET on a single order and verify the response contains content and a self link.
2. Call GET on the collection and verify items appear under _embedded and the collection has a self link.
3. Call the paginated endpoint and verify page metadata along with appropriate first/prev/next/last links.
4. Send POST to create an order and verify status 201 and the Location header.
5. Call an endpoint returning 204 and verify the response has no body.
6. Inspect the Content-Type and HAL structure that clients actually receive.
7. Verify DTOs do not expose internal fields or sensitive data in responses.
8. Issue requests for the first, middle, and last pages to verify navigation links.
9. Verify response statuses and headers match success, not found, and business conflict cases.

EntityModel is for a single resource with links; CollectionModel is for a collection without standard page metadata; PagedModel is for paginated results; ResponseEntity controls HTTP status, headers, and body. Combining these types enables custom Spring MVC endpoints to return discoverable representations, clear pagination, and accurate HTTP outcomes.
