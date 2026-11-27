# Reducing Returned Data with Projections and Page Size Limits

A Spring Data REST API can return far too much data if each resource contains many properties and collections return too many elements in a single response. Two essential controls are projections and page size limits.

A projection determines which properties are included in each resource's representation. Page size determines the maximum number of resources returned on a single page. Combining both reduces payload size, serialization time, bandwidth, and the amount of data clients must process.

The two mechanisms act along different dimensions: projections reduce the number of fields per item; page size reduces the number of items per response. Using only one mechanism can still leave responses large if the other dimension remains unbounded.

## 1. Why Reduce API Payloads?

Suppose Product has the following properties:

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String description;
    private BigDecimal price;
    private BigDecimal internalCost;
    private String supplierNotes;
    private boolean active;

    // getters and setters
}
~~~

A product listing screen may only need id, name, price, and active. If the API returns the long description, internalCost, and supplierNotes for every product, the response contains unnecessary data.

The problem grows when a collection contains thousands of products. If every item carries many fields, responses become large, consume serialization time and network bandwidth, and force clients to parse unused data.

Design representations around the needs of each screen or use case. Listing screens typically need a compact summary; detail screens may need description or additional attributes.

## 2. What Is a Projection in Spring Data REST?

A projection is an interface describing the set of properties exposed in a representation. Spring Data REST can use projections to present an entity in a slimmer structure without modifying the entity or creating a separate endpoint for every data shape.

Example projection for a product list:

~~~java
import java.math.BigDecimal;

import org.springframework.data.rest.core.config.Projection;

@Projection(name = "productSummary", types = Product.class)
public interface ProductSummary {

    Long getId();

    String getName();

    BigDecimal getPrice();

    boolean isActive();
}
~~~

ProductSummary exposes only id, name, price, and active. The properties description, internalCost, and supplierNotes are not in this projection, so they do not appear in representations built with it.

Place the projection in the domain type's package or a subpackage according to Spring Data REST's projection discovery rules. The name in @Projection is what clients use to request the projection; the interface name and projection name do not have to match.

A projection interface typically uses getters whose names correspond to properties on the domain object. For instance, getName() maps to the name property; isActive() maps to the boolean active property.

## 3. Requesting a Projection via the projection Parameter

Once a projection is discovered, clients can select it via the projection query parameter.

Fetching a collection:

~~~http
GET /api/products?projection=productSummary
~~~

Fetching a single resource:

~~~http
GET /api/products/42?projection=productSummary
~~~

Illustrative response:

~~~json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 120.00,
  "active": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/42"
    }
  }
}
~~~

The client receives a representation containing only the fields declared by ProductSummary, along with HATEOAS links matching the Spring Data REST configuration.

If an unknown projection name is sent or the projection is not discovered by the framework, the request may not produce the expected result. Check the name in @Projection, the domain type in types, and the package containing the interface.

Projections can be requested for collections or items. In applications with multiple projections, give them clear purpose-driven names such as productSummary, productDetail, or productCard.

## 4. Using excerptProjection as the Default Collection Representation

If you want embedded items in a collection to use a projection by default, declare excerptProjection on the repository:

~~~java
@RepositoryRestResource(
    path = "products",
    excerptProjection = ProductSummary.class
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

When clients read the /api/products collection, the excerpt projection is used for the condensed representation of items embedded in the collection. That way, clients do not need to append ?projection=productSummary to every collection request to get the default summary shape.

Distinguish excerpt projections from explicitly requested projections:

- excerptProjection sets the default representation shape for embedded items inside a collection resource.
- The projection parameter allows clients to request an exposed projection for a specific request.
- An excerpt projection does not automatically turn every item endpoint or every other representation into the same structure.

For example, the collection can use ProductSummary to display a list; a client opens /api/products/42?projection=productSummary to request the same summary shape for an item. Another detailed projection can be exposed for a detail screen if needed.

Avoid putting all properties into an excerpt projection. Collections typically return many items, so every redundant field is multiplied by the element count.

## 5. How Do Projections Reduce Data?

Suppose a Product has 20 properties, while a list view needs only 4. If each property holds sizable data, shrinking the representation from 20 fields to 4 makes the response smaller and reduces JSON processing work on the client.

Common benefits:

- Fewer bytes transferred over the network.
- Reduced JSON serialization and parsing time.
- Less client memory spent on unnecessary data.
- API contracts better tailored to individual screens.
- Reduced risk of accidentally exposing internal fields in selected representations.

However, projections primarily govern the returned representation. Do not assume every projection causes the database to read only the declared columns. Query optimization depends on the projection type, repository type, query, and underlying store.

A closed interface projection declaring accessors only for existing properties can allow Spring Data to optimize certain queries. Projections using @Value or SpEL can access multiple properties on the target, reducing the ability to predetermine which columns need to be read. Nested relationships can also trigger lazy loading or extra queries.

If the goal is precise control over SQL and columns read from the database, consider DTO/class-based projections or queries selecting only required fields. Measure actual queries rather than assuming a slim payload always means fewer columns read by the database.

## 6. Limiting Page Size in Spring Data REST

Projections reduce the number of fields per item, while page size limits the number of items returned in a collection response. Spring Data REST supports configuring default and maximum page sizes via RepositoryRestConfiguration.

Example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RepositoryRestConfig implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultPageSize(20);
        config.setMaxPageSize(100);
    }
}
~~~

In this example:

- setDefaultPageSize(20) uses 20 elements when the client omits the page size parameter.
- setMaxPageSize(100) sets an upper bound of 100 elements per page.

With this configuration, clients can request fewer than 100 items per page. If a client sends a size larger than the limit, Spring Data REST enforces the configured maximum instead of allowing a single request to pull an arbitrarily large page.

Limiting page size does not limit the total number of records in the collection. It only caps the number of elements in each response; clients can still traverse multiple pages using navigation links.

## 7. Using page, size, and sort When Querying

Spring Data REST provides common parameters:

- page: zero-based page index.
- size: requested number of elements on the page.
- sort: property and sort direction.

Example:

~~~http
GET /api/products?page=0&size=20&sort=name,asc
~~~

This request fetches the first page, requests 20 products, and sorts by name ascending.

Clients can request the next page:

~~~http
GET /api/products?page=1&size=20&sort=name,asc
~~~

If size is omitted, the server uses the default page size. If size exceeds max page size, the server caps it per configuration. If sort is invalid or a property is not sortable, the request may be rejected depending on handling behavior and Spring Data version.

You can combine projections and paging in the same request:

~~~http
GET /api/products?projection=productSummary&page=0&size=20&sort=name,asc
~~~

This request simultaneously caps the number of items on the page and limits the fields presented for each item. This is a common pattern for creating lightweight collection responses for list UIs.

## 8. Reading Pagination Metadata and Links in HAL

A paginated collection can return embedded items, page metadata, and navigation links. Illustrative example:

~~~json
{
  "_embedded": {
    "products": [
      {
        "id": 42,
        "name": "Mechanical Keyboard",
        "price": 120.00,
        "active": true
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products?page=0&size=20"
    },
    "next": {
      "href": "http://localhost:8080/api/products?page=1&size=20"
    },
    "last": {
      "href": "http://localhost:8080/api/products?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 95,
    "totalPages": 5,
    "number": 0
  }
}
~~~

The page fields typically indicate:

- size: applied page size.
- totalElements: total number of elements matching the collection query.
- totalPages: total number of pages.
- number: current zero-based page index.

The first, prev, next, and last links appear depending on page position. The first page may omit prev; the last page omits next. Clients should follow server-provided hrefs to keep filter, sort, and page size parameters consistent.

The totalElements and totalPages metadata are helpful for UIs, but computing totals may require a count query. For large datasets, weigh the cost of count queries and pick a pagination strategy suited to product requirements.

## 9. Consistent Parameter Naming and Configuration

Spring Data REST lets you customize page, size, and sort parameter names via RepositoryRestConfiguration:

~~~java
config.setPageParamName("page");
config.setLimitParamName("limit");
config.setSortParamName("sort");
~~~

If limit is used instead of size, clients must pass the configured parameter name. Document parameter names in the API specification and keep them consistent across endpoints.

Do not rename parameters out of personal preference once multiple clients have integrated. Changing them can break existing requests. If a contract change is necessary, plan for compatibility and notify clients clearly.

For custom Spring MVC controllers accepting Pageable directly, enforce limits in the corresponding Spring Data Web/Pageable resolver configuration or validate parameters at the endpoint. Do not assume Spring Data REST's configuration automatically protects every custom controller in the application.

## 10. Projections Do Not Replace Data Security

Projections help shape returned data, but they are not an authorization mechanism. A slim projection does not guarantee users cannot access the same entity through another endpoint or another projection.

For example, ProductSummary omits internalCost, but if the default representation or another projection still exposes internalCost, that field can still leak.

To protect sensitive data:

- Do not include confidential fields in public projections.
- Review the default representation when clients omit the projection parameter.
- Use Spring Security to control who can access resources or perform operations.
- Use DTOs/custom controllers when responses must vary by role.
- You can use serialization configuration such as @JsonIgnore for properties that must never appear, while checking its impact on deserialization and other endpoints.
- Do not rely on clients omitting a field as a security measure.

If visibility of individual properties depends on the user, design role-aware representations at the service/controller layer and check permissions before returning data. Public projections should contain only fields safe to share with every caller permitted to invoke that endpoint.

## 11. When Are Projections or Page Size Limits Not Enough?

Projections and page sizes address most collection payload reduction needs, yet certain scenarios require additional design:

- A large text field can still bloat an item summary; exclude that field from the projection.
- A projection accessing lazy relationships can trigger many queries; check SQL and fetch strategies.
- A small page size where clients must fetch thousands of pages can generate excessive requests; consider search, filtering, or cursor/keyset pagination where appropriate.
- A custom endpoint returning List directly may bypass Spring Data REST limits; use Pageable and configure resolvers.
- A response embedding rich relationship data can still be large even when the root collection is paginated; limit nesting depth and pick suitable projections.

If clients only need a subset of products, combine filtering/searching with paging so the database returns only matching results. Never load an entire collection into server or client memory and slice pages there.

## 12. Verification Workflow for Payloads and Page Limits

After declaring ProductSummary and configuring RepositoryRestConfiguration:

1. Call GET /api/products?projection=productSummary and confirm the response contains only id, name, price, and active per the projection.
2. Call GET /api/products/42?projection=productSummary to verify the projection on an item resource.
3. Read GET /api/products and confirm excerptProjection is used for embedded items in the collection if configured.
4. Call GET /api/products?page=0 without size; confirm the server applies the default page size.
5. Call GET /api/products?page=0&size=10; confirm the page contains at most 10 items.
6. Send a size greater than maxPageSize; confirm the size is capped according to configuration.
7. Combine projection, page, size, and sort in the same request; confirm both item contents and item count match expectations.
8. Inspect page metadata and next/last links on the first, middle, and last pages.
9. Measure response size before and after applying the projection to confirm payload reduction.
10. Inspect the default representation and other endpoints to ensure sensitive fields do not leak via an alternate access path.

Projections reduce the number of properties in each resource's representation; page size limits reduce the number of resources in a response. Combining summary projections, excerptProjection, and max page size keeps collection APIs leaner, more predictable, and aligned with client needs. Verify actual payloads, database queries, and alternate access paths so performance optimizations never weaken data security.
