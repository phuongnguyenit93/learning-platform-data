# Hiding Associations with @RestResource and Controlling Remaining Write Paths

Spring Data REST can expose an association as both a link and a dedicated association resource. When clients should not directly read or modify that relationship through an association endpoint, you can annotate the relationship property with `@RestResource(exported = false)`. However, hiding an association resource neither removes the relationship from the JPA model nor serves as a complete authorization policy. You must identify any remaining open write paths and control them according to business rules.

## 1. How Is an Association Resource Exposed?

Suppose an order has many products:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    private Set<Product> items = new LinkedHashSet<>();

    // getters and setters
}
~~~

If the `PurchaseOrder` repository is exposed via Spring Data REST, the order's representation may include an association link:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "items": {
      "href": "/api/orders/42/items"
    }
  }
}
~~~

Clients can follow the `href` of `items` to read or modify the collection association using the HTTP methods supported by Spring Data REST. For collection associations, `POST` usually adds target element URIs; `PUT` can replace the linked set; `DELETE` can remove links per association resource semantics.

If the relationship should not be exposed as an independent API, you can hide it directly on the persistent property.

## 2. Hiding an Association with @RestResource(exported = false)

Place `@RestResource(exported = false)` on the association property mapped by Spring Data REST:

~~~java
import org.springframework.data.rest.core.annotation.RestResource;

@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    @RestResource(exported = false)
    private Set<Product> items = new LinkedHashSet<>();

    // getters and setters
}
~~~

For mappings using property access, place the annotation on the corresponding accessor rather than the field, following the same JPA access strategy in use:

~~~java
@ManyToMany
public Set<Product> getItems() {
    return items;
}

@RestResource(exported = false)
public void setItems(Set<Product> items) {
    this.items = items;
}
~~~

In real code, the annotation must be placed on the persistent association property in a way Spring Data REST can inspect. Avoid placing annotations inconsistently between fields and accessors when an entity uses a specific JPA access strategy.

When an association is marked non-exported:

- Spring Data REST does not expose that association resource as a standalone REST path.
- Clients are not provided the corresponding association link in the HAL representation.
- The JPA relationship still exists in the entity mapping and in the database.
- The target entity's repository, such as `ProductRepository`, can still be exported independently.
- Internal services can still modify the relationship through entities and repositories if application logic allows it.

For example, hiding `items` does not hide all of `/api/products`. Clients can still access the `Product` repository if that repository is exported. This annotation controls association exposure; it does not automatically hide the target entity or every API that could affect related data.

## 3. Hiding an Association Does Not Close All Write Paths

After hiding the association link, examine other write paths that could mutate the same data. A relationship can still be altered indirectly via:

1. **PUT or PATCH on the parent resource.** If the `PurchaseOrder` representation allows binding the relationship property, an order update request can affect the association depending on configuration and how Spring Data REST handles the property.
2. **Repository collection and item endpoints of the related entity.** `ProductRepository` may still allow `POST`, `PUT`, or `DELETE` on `Product`. Those operations can affect the relationship per JPA mappings and constraint rules.
3. **Exported repository methods.** Write methods like `save` or `delete` can still provide repository write paths unless hidden or restricted.
4. **Custom controllers or services.** Application-defined endpoints can still modify the association.
5. **Internal tasks.** Batch jobs, message consumers, or other services can change the same data without going through the association resource.

Therefore, do not conclude "the association is safe from writes" simply because the link no longer appears in HAL. Identify which actors are permitted to modify the relationship and which HTTP or service paths remain able to perform that operation.

## 4. Controlling PUT and PATCH on the Parent Resource

If clients are allowed to update other fields of an order but must not change `items`, restrict how the parent resource can be updated. You can use Spring Security to control HTTP methods by endpoint and caller authorities:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("ORDER_READ")
            .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                .hasAuthority("ORDER_WRITE")
            .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                .hasAuthority("ORDER_WRITE")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

This is an example of endpoint-level authorization. If everyone with `ORDER_WRITE` may edit orders but must not edit `items`, checking an authority at the URL level is not enough to distinguish which properties may change. In that case, you need payload control or a dedicated write API with a DTO containing only allowed fields.

Example DTO for updating shipping details without the `items` association:

~~~java
public record UpdateOrderRequest(
    String shippingNote,
    String deliveryAddress
) {
}
~~~

A controller accepts this DTO and calls a service that updates only the permitted fields. Because the DTO does not accept a list of `Product`s, clients cannot use this endpoint to submit association changes.

If you still allow Spring Data REST's default `PUT`/`PATCH` on the parent resource, explicitly verify and control association binding; do not rely solely on the association link being hidden.

## 5. Hiding Repository Write Operations When Needed

If a repository should not accept write operations via Spring Data REST, you can override inherited methods and mark them non-exported:

~~~java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Override
    @RestResource(exported = false)
    <S extends PurchaseOrder> S save(S entity);
}
~~~

Hiding `save` makes write flows backed by that repository via Spring Data REST unavailable, including create or update operations that need to save the entity. Other methods such as `delete` also need separate review if deletion should not be exposed.

Example hiding deletion by ID:

~~~java
@Override
@RestResource(exported = false)
void deleteById(Long id);
~~~

This is a repository-method-level decision with broader impact than hiding a single association. If you only want to lock down one relationship while still allowing updates to other order fields, do not hide `save` indiscriminately; design a write path with appropriate DTOs and permissions instead.

If you need to hide the entire repository from Spring Data REST, use `@RepositoryRestResource(exported = false)` on the repository. This neither removes the repository bean nor prevents internal services from injecting it, but clients can no longer use that repository as a Spring Data REST resource.

## 6. Creating a Dedicated Write Path for Association Changes

When business rules still require allowing certain users to add products to an order, you can hide the default association resource and expose a dedicated endpoint. This endpoint accepts business identifiers, checks permissions, verifies both entities exist, and applies domain rules before updating the relationship.

Example request DTO:

~~~java
public record AddOrderItemRequest(Long productId) {
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/order-management/orders")
public class OrderItemController {

    private final OrderService orderService;

    public OrderItemController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/{orderId}/items")
    @PreAuthorize("hasAuthority('ORDER_EDIT_ITEMS')")
    public ResponseEntity<Void> addItem(
            @PathVariable Long orderId,
            @RequestBody AddOrderItemRequest request) {

        orderService.addItem(orderId, request.productId());
        return ResponseEntity.noContent().build();
    }
}
~~~

Service performing the update within a transaction:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;
    private final ProductRepository products;

    public OrderService(
            PurchaseOrderRepository orders,
            ProductRepository products) {
        this.orders = orders;
        this.products = products;
    }

    @Transactional
    public void addItem(Long orderId, Long productId) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));

        Product product = products.findById(productId)
            .orElseThrow(() -> new EntityNotFoundException("Product not found"));

        // Check order status, ownership, and business rules here.
        order.getItems().add(product);
    }
}
~~~

The example above assumes `PurchaseOrder` is the owning side of the relationship and the `items` collection can be mutated directly. If the mapping uses a different owning side, update the owning side properly and synchronize the inverse side if required by the application. The repository or service must also ensure the entity is saved within the transaction according to the project's persistence setup.

Advantages of a dedicated write path:

- Only a specific authority, such as `ORDER_EDIT_ITEMS`, permits modifying the association.
- The request DTO prevents clients from arbitrarily submitting the entire entity.
- The service can verify whether the order is still in a modifiable state.
- It can check whether the product belongs to the appropriate catalog, warehouse, or tenant.
- It can record audit logs and publish business events at the exact right moment.

If the API only needs to read the association, you can keep a dedicated read endpoint or include appropriate link/summary information in another representation. Hiding the default association resource does not force the application to drop all ability to read related data.

## 7. Controlling the Target Entity Repository as Well

Hiding the association on `PurchaseOrder` does not automatically prevent clients from modifying `Product` through `ProductRepository`. If `Product` is exposed independently, clients may still have operations on `/api/products` or `/api/products/{id}`.

Define the scope that needs protection:

- If you only need to prevent clients from altering the link, protect `PurchaseOrder`'s write paths and association.
- If you need to prevent clients from editing `Product` data, control `POST`, `PUT`, `PATCH`, and `DELETE` on `ProductRepository`.
- If `Product` is strictly internal, consider hiding its repository with `@RepositoryRestResource(exported = false)`.
- If different user groups have different permissions, use Spring Security and check resource-level authorization in the service layer.

For instance, `Product` could remain publicly readable while write operations are restricted to `PRODUCT_ADMIN`. You can assign permissions by HTTP method on the `Product` endpoint or hide write methods on the repository, depending on the API contract you need to maintain.

## 8. Verification Workflow After Hiding an Association

After configuring `@RestResource(exported = false)`, verify every read and write path:

1. `GET` the parent resource, e.g., `/api/orders/42`; confirm the `items` association link is no longer advertised.
2. Try accessing the old association URL; confirm Spring Data REST no longer serves that association resource.
3. `GET` `Product` via its own repository if `Product` remains exported; confirm hiding the association did not break the target repository.
4. Try `PUT`/`PATCH` on the parent resource with a payload updating only allowed fields.
5. Try a payload containing `items` to confirm clients cannot bypass the policy through parent updates.
6. Try `POST`/`PUT`/`PATCH`/`DELETE` on related repositories under each role's permissions.
7. Call the dedicated write endpoint if one exists; confirm callers without `ORDER_EDIT_ITEMS` are rejected.
8. Re-read the parent resource and persistence data to confirm the relationship only changes through permitted write paths.

When testing, test with both authorized and unauthorized users. Check both status codes and post-request data; a `2xx` response alone is not enough to prove the association was persisted according to business rules.

## 9. Common Misconceptions

- **Treating link hiding as deleting the relationship.** The annotation only controls association exposure in Spring Data REST; the JPA mapping and relationship data still exist.
- **Treating association hiding as blocking all writes.** Parent `PUT`/`PATCH`, repository methods, custom controllers, and internal services can still be write paths.
- **Treating association hiding as hiding the target entity.** `ProductRepository` can continue to be exposed independently.
- **Checking only the HAL response.** Directly test endpoints and write payloads that may still be active.
- **Using a single permission for all operations.** Reading an order, editing order fields, and changing the product list may require separate authorities.
- **Forgetting the JPA owning side.** Updating the inverse side without updating the owning side may fail to persist changes to the database.

`@RestResource(exported = false)` is a concise way to remove an association from the automatic REST surface. A complete write policy needs to cover the parent resource, related entity repositories, and custom endpoints. Choose one permitted write path clearly, place authorization checks and business rules on that path, and verify with real requests.
