# Creating Resources with PUT and the disablePutForCreation Configuration

Spring Data REST can allow clients to create resources by sending a PUT to an item resource's URI. This differs from POST to a collection resource: with POST, the server typically chooses the ID for the new resource; with PUT, the client specifies the target URI and the resource is created at that URI if the configuration and repository allow it.

The disablePutForCreation property in RepositoryRestConfiguration controls this behavior. When enabled, PUT can still update existing resources, but cannot be used to create a new resource at a nonexistent item URI. This is a useful option when an API wants to reserve POST for creation and keep PUT for replacing existing resources.

## 1. Distinguishing POST, PUT, and PATCH

The three common HTTP methods for writing resources have different purposes:

| Method | Typical URI | Purpose |
|---|---|---|
| POST | /api/products | Requests creating a new resource in the collection; the server usually assigns an ID and returns a link to the new item. |
| PUT | /api/products/42 | Sets the representation of the resource at a specific URI; can update an existing item and, if permitted, create a new item at that URI. |
| PATCH | /api/products/42 | Partially updates the representation of an existing item, keeping unsent properties according to the API's processing rules. |

For example, a repository exposed at /api/products:

~~~java
@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

A client can use POST to ask the server to create a product:

~~~http
POST /api/products
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "price": 120
}
~~~

The server typically generates a new ID, saves the product, and returns a success response with Location pointing to the new item resource, such as /api/products/42.

With PUT, the client specifies the item URI:

~~~http
PUT /api/products/42
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "price": 120
}
~~~

If product 42 already exists, PUT updates that resource's representation. If product 42 does not exist yet, Spring Data REST can by default create the resource at this URI when the repository and ID type support creation with a specified ID.

PATCH also targets the item URI, but is suitable when the client only wants to change part of the data. For example, updating the price without resending the product name:

~~~http
PATCH /api/products/42
Content-Type: application/merge-patch+json

{
  "price": 135
}
~~~

The supported PATCH syntax and media types depend on configuration and application version. Regardless of format, the intent of PATCH is a partial update; PUT represents replacing the resource at the target URI.

## 2. When can PUT create a resource?

When receiving a PUT to an item URI that does not yet exist, Spring Data REST can treat that request as creating a new resource at the specified URI. This capability is commonly called PUT for creation.

For example, a client sends:

~~~http
PUT /api/products/9001
Content-Type: application/json

{
  "name": "USB-C Hub",
  "price": 45
}
~~~

If PUT for creation is allowed and the repository can save an entity with identifier 9001, the server can create the new product at /api/products/9001.

This approach is useful when the client already knows the resource identifier beforehand, such as synchronizing data from another system or creating resources with business-assigned IDs. Because the target URI is known in advance, the client can resend the same PUT request to the same address without creating another item at a different URI.

However, PUT for creation requires careful consideration. It allows clients to choose the URI/ID of the new resource. If the system wants the server to manage ID assignment and accept creation only via the collection endpoint, disable this behavior using disablePutForCreation.

## 3. Disabling PUT for creation with disablePutForCreation

Spring Data REST provides the setDisablePutForCreation method on RepositoryRestConfiguration. Set it to true to prevent PUT from creating resources at nonexistent item URIs.

This can be configured via RepositoryRestConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestConfig implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDisablePutForCreation(true);
    }
}
~~~

After configuring this, behavior works as follows:

- PUT to an existing item URI: still used to update the resource according to PUT rules.
- PUT to a nonexistent item URI: does not create a new item; Spring Data REST rejects the creation attempt at that URI, typically with a 404 Not Found response.
- POST to a collection resource: remains the standard way to create new resources.
- PATCH to an item URI: remains for partial updates of existing resources.

This configuration adjusts REST repository exposure behavior. It does not disable the repository's save method in the Java layer, nor does it forbid internal services from creating new entities.

## 4. Verification examples before and after enabling the setting

Suppose the API has the collection /api/products and IDs are Long.

**Before enabling disablePutForCreation**

When product 9001 does not exist yet, send:

~~~bash
curl -i -X PUT http://localhost:8080/api/products/9001 \
  -H "Content-Type: application/json" \
  -d '{"name":"USB-C Hub","price":45}'
~~~

If the repository supports creating with an ID and the default configuration allows PUT for creation, the request can create product 9001. A success response will indicate the resource was created; inspect Location or call GET on the item URI to confirm.

**After enabling disablePutForCreation(true)**

Send PUT again to a nonexistent item URI:

~~~bash
curl -i -X PUT http://localhost:8080/api/products/9002 \
  -H "Content-Type: application/json" \
  -d '{"name":"USB-C Hub","price":45}'
~~~

The request is not used to create product 9002. Spring Data REST typically returns 404 Not Found because the target item resource does not exist.

However, PUT to an existing item still works:

~~~bash
curl -i -X PUT http://localhost:8080/api/products/42 \
  -H "Content-Type: application/json" \
  -d '{"name":"Mechanical Keyboard","price":135}'
~~~

Product 42 is updated according to the sent representation. To verify clearly, call GET /api/products/42 after PUT and confirm the data changed.

Finally, POST to the collection can still create a new item:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"USB-C Hub","price":45}'
~~~

The server assigns an identifier according to the repository's mechanism and returns the link to the new item. This is the creation flow to use when clients do not need to decide the ID themselves.

## 5. Why distinguish update PUT from creation PUT?

Both requests use PUT, but the initial state of the URI differs:

| Item URI state | disablePutForCreation=false | disablePutForCreation=true |
|---|---|---|
| Item already exists | PUT updates the item. | PUT updates the item. |
| Item does not exist | May create the item at the URI if the repository supports it. | Does not create the item; the request is rejected. |

When disablePutForCreation is enabled, the API contract is more predictable: clients must POST to the collection to create new resources, while PUT is used only for existing items. This also avoids a client accidentally creating a resource by sending a wrong ID or sending PUT to an unregistered URI.

If business requirements genuinely need clients to create resources with client-supplied IDs, consider keeping PUT for creation while controlling access permissions, ID rules, uniqueness, and data validation. Do not rely on unpredictable IDs to protect endpoints.

## 6. PUT is resource replacement; PATCH is partial update

In HTTP semantics, PUT is used to set the representation state of the resource at the target URI. Therefore, clients should send the full representation per the endpoint contract. If properties are omitted, the outcome for those properties depends on how Spring Data REST, Jackson, and the entity model handle missing values; do not assume all properties are automatically preserved.

Example entity:

~~~java
public class Product {
    private String name;
    private BigDecimal price;
    private String description;
}
~~~

If the client only wants to change price, sending a PUT containing only price may cause name or description to be set to default/null depending on binding. For partial updates, PATCH expresses the intent more clearly:

~~~http
PATCH /api/products/42
Content-Type: application/merge-patch+json

{
  "price": 135
}
~~~

When updating the entire representation, use PUT. When changing only a subset of properties, use PATCH with a media type and semantics supported by the API. The disablePutForCreation setting only decides whether PUT can create new resources; it does not turn PUT into PATCH.

## 7. Relationship between REST configuration and Java repositories

Repositories still provide persistence methods such as save, findById, and delete. disablePutForCreation only affects how Spring Data REST handles HTTP requests to exposed resources.

For example, an internal service can still create products:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product create(Product product) {
        return repository.save(product);
    }
}
~~~

Even with disablePutForCreation enabled, the service can still call save to persist new entities. If you want to restrict who can create data, you need to design authorization for controllers/services and configure Spring Security appropriately. Disabling PUT for creation does not replace authentication or authorization.

In addition, this setting does not prevent POST from creating resources. If the API needs to restrict creation in general, control POST via security policies or hide exposed methods according to the endpoint design.

## 8. When should disablePutForCreation be enabled?

Consider enabling it when:

- The server needs to manage ID assignment for new resources.
- Clients are only allowed to create via POST to the collection resource.
- The API wants a clear convention: POST creates new resources, PUT updates existing items.
- You do not want a PUT with a mistaken ID to create an unintended resource.
- Clients have no need to create resources at URIs they specify themselves.

You can keep PUT for creation when:

- Clients have stable identifiers and are allowed to choose the URI of new resources.
- Synchronization systems need to write resources to a known ID.
- The API has clear ID control rules, authentication, and authorization.
- Clients understand the PUT contract that it can both create and replace resources.

The decision should be based on how the system manages identifiers and client needs. Do not enable or disable it merely for HTTP method naming consistency; consider how resources are created and who has the right to choose URIs.

## 9. Implementation checklist

1. Determine whether clients need to specify IDs for new resources themselves.
2. If creation should happen only via collections, configure RepositoryRestConfigurer and call setDisablePutForCreation(true).
3. Verify that PUT to an existing item URI still updates properly.
4. Verify that PUT to a nonexistent item URI does not create a resource and returns an appropriate response.
5. Verify that POST to the collection still creates new resources according to application policy.
6. Verify PATCH partial updates if supported by the endpoint.
7. Verify internal services continue working per business requirements; REST configuration does not alter the repository persistence contract.
8. Update API documentation so clients know how to create, fully update, and partially update resources.

disablePutForCreation is a small configuration setting that changes Spring Data REST's resource creation contract. When enabled, PUT only updates existing items; POST remains the creation flow via collections. Test both existing and nonexistent URI cases to confirm the API responds in line with the application's identifier policy.