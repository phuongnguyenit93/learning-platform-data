# Linking and Unlinking Products and Categories by URI

## 1. Objective

In a Spring Data REST API, a product often belongs to a category. For example, the product "Notebook" is assigned to the category "Stationery". We need to create two independent resources, then link or unlink them via the HTTP API.

Spring Data REST provides an association resource for every association it detects on a domain resource. For the Product.category relationship, the product resource has a link named category. Clients use the association link URI to perform operations and send the Category resource URI in the body. This keeps clients working with resource URIs published by the server instead of sending an entire Category object or guessing IDs.

Example URIs used in this guide:

- Product collection: http://localhost:8080/products
- Product resource: http://localhost:8080/products/42
- Category collection: http://localhost:8080/categories
- Category resource: http://localhost:8080/categories/3
- Category association resource on product 42: http://localhost:8080/products/42/category

IDs and hosts are examples only. In real applications, discover URIs from HAL responses and use the exact URIs returned by the API.

## 2. Product and Category Data Model

The example below uses Spring Data JPA. A product may be uncategorized or belong to one category; multiple products can reference the same category. Therefore, Product.category is a many-to-one relationship and is the owning side of the link in JPA mapping.

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

@Entity
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Category() {
    }

    public Category(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "category_id", nullable = true)
    private Category category;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Category getCategory() {
        return category;
    }
}
~~~

In this example:

- @ManyToOne indicates that multiple Products can reference the same Category.
- optional = true allows a product to have no category.
- nullable = true allows the category_id column in the database to accept NULL. Actual schema migrations must also allow NULL values if unlinking is supported.
- Product is the owning side of the relationship because @JoinColumn resides on Product.category. When modifying the link via Product's association resource, Spring Data REST updates this property.
- Category does not need a products collection to support this link/unlink flow. If a bidirectional relationship is added via @OneToMany(mappedBy = "category"), that is the inverse side; business code must keep both sides synchronized in memory when needed.

Do not add CascadeType.REMOVE from Product to Category just to support linking/unlinking. A Category may be shared by many Products; unlinking a product does not mean deleting the Category. Likewise, deleting a Product should not automatically delete a Category used by other products.

If a Product must always belong to a Category, configure optional = false and a NOT NULL database column. In that case, an association DELETE operation to remove the category is inappropriate, and Spring Data REST may reject it because the association is non-optional.

## 3. Exporting Repositories so Spring Data REST Publishes Resources

Create repositories for both domain object types:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "categories")
public interface CategoryRepository extends JpaRepository<Category, Long> {
}
~~~

Spring Data REST exports repositories as collection resources and item resources. Under the default configuration, eligible public repositories are discovered automatically; @RepositoryRestResource here clarifies the path names used in the example. If an application sets the detection strategy to only export annotated repositories, both repositories already carry the appropriate annotation.

An association can only be manipulated as a resource link when the association is recognized by Spring Data REST and the target resource is accessible via an exported repository. If the association does not appear in HAL, check the domain mapping, the target type's repository, the detection strategy, and the property's exported configuration.

You can customize the path or relation name using @RestResource on the association property. Without customization, the association resource name defaults to the property name—category in this example.

## 4. Discovering URIs via HAL Before Updating

Start from the API root:

~~~bash
curl -i -H 'Accept: application/hal+json' \
  http://localhost:8080/
~~~

The root response publishes the collection links, for example:

~~~json
{
  "_links": {
    "products": {
      "href": "http://localhost:8080/products"
    },
    "categories": {
      "href": "http://localhost:8080/categories"
    }
  }
}
~~~

Create or find a Category, then extract the resource URI from the Location response header or self link:

~~~bash
curl -i -X POST http://localhost:8080/categories \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/hal+json' \
  --data '{"name":"Stationery"}'
~~~

A resource creation response usually has status 201 Created and a Location header pointing to the newly created resource. If the response includes a HAL body, use the self link in the body. Illustrative example:

    Location: http://localhost:8080/categories/3

Create a Product without a category:

~~~bash
curl -i -X POST http://localhost:8080/products \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/hal+json' \
  --data '{"name":"Notebook"}'
~~~

Assume the server returns:

    Location: http://localhost:8080/products/42

Read the product resource:

~~~bash
curl -i -H 'Accept: application/hal+json' \
  http://localhost:8080/products/42
~~~

The HAL representation of Product can publish the association link:

~~~json
{
  "name": "Notebook",
  "_links": {
    "self": {
      "href": "http://localhost:8080/products/42"
    },
    "category": {
      "href": "http://localhost:8080/products/42/category"
    }
  }
}
~~~

The category link here is the URI of the association resource, not the Category URI. The client must keep track of both URIs:

- Association URI: where PUT or DELETE is sent to modify the link.
- Category URI: the target resource URI sent in the PUT body.

Do not hardcode association paths in the frontend if you can follow links from HAL. When the server changes the base path or association name via @RestResource, clients relying on published links are much less likely to break.

## 5. Linking a Product to a Category with PUT and text/uri-list

To assign product 42 to category 3, send a PUT request to the product's association URI. The body contains the Category URI and Content-Type is text/uri-list:

~~~bash
curl -i -X PUT \
  http://localhost:8080/products/42/category \
  -H 'Content-Type: text/uri-list' \
  --data-binary 'http://localhost:8080/categories/3'
~~~

Meaning of the request:

- The PUT target is the association resource /products/42/category.
- The body is the target resource URI /categories/3.
- Content-Type must be text/uri-list.
- For a to-one relationship like Product.category, send only one URI.

Spring Data REST uses the URI in the body to locate the Category resource and bind it to the association. If the association currently points to another Category, PUT updates the link to the specified Category.

A to-one association cannot accept multiple URIs. If the body contains multiple URIs for Product.category, Spring Data REST returns 400 Bad Request. If multiple linked resources are needed, the domain property must be a collection association and API calls must follow collection semantics.

After a successful PUT, re-read the product or association resource:

~~~bash
curl -i -H 'Accept: application/hal+json' \
  http://localhost:8080/products/42/category
~~~

Or read the item resource:

~~~bash
curl -i -H 'Accept: application/hal+json' \
  http://localhost:8080/products/42
~~~

Verify that the association points to the expected Category URI. Do not rely solely on the status code; re-reading the resource confirms the relationship was saved in the persistence layer.

If the client uses an HTTP library, configure equivalent headers and body:

~~~text
Method: PUT
URL: <association href obtained from HAL>
Content-Type: text/uri-list
Body: <category self href obtained from HAL>
~~~

Do not send a JSON object like {"id":3} to an association resource. Association endpoints accept a URI list, not a JSON Category object.

## 6. Unlinking a Product from a Category with DELETE

When Product.category is an optional association, send DELETE to the association resource:

~~~bash
curl -i -X DELETE \
  http://localhost:8080/products/42/category
~~~

DELETE removes the link between the Product and Category. It does not delete the Category resource from the repository and does not affect other products using the same Category.

After the operation, re-GET the Product and check the category state. Applications may represent an unbound association differently depending on representation and configuration; what matters is that Product.category is now null in the persistence layer.

If the relationship is required, DELETE cannot set the property to null. Spring Data REST responds with 405 Method Not Allowed when the association is non-optional. In that case, the client must bind another valid Category using PUT or use a dedicated business workflow to update required data.

If the database schema defines category_id as NOT NULL while the entity declares optional = true, an unlink request may pass object-level validation and then fail on database write. Annotations and schema migrations must stay consistent.

## 7. Distinguishing PUT, POST, and DELETE on Association Resources

Spring Data REST supports GET, PUT, POST, and DELETE on association resources:

| Method | Purpose | Content-Type | Scope |
|---|---|---|---|
| GET | Read link state | application/hal+json or application/json | To-one and collection |
| PUT | Bind resource URI(s) to the association | text/uri-list | Single URI for to-one; URI list for appropriate associations |
| POST | Add a new element to a collection association | text/uri-list | Collection associations only |
| DELETE | Unbind association | No body needed | Association resource |

Rules to remember:

- PUT is the right choice for Product.category because it is a to-one association.
- POST is only supported for collection associations and appends an item to the collection.
- PUT with multiple URIs on a to-one association returns 400 Bad Request.
- DELETE unbinds the association; if the association is non-optional, Spring Data REST may return 405 Method Not Allowed.
- Association resource GET supports application/hal+json and application/json.
- Association resource PUT and POST accept text/uri-list, not JSON objects.

If Category has a collection association products, POST to the collection's association URI can add a Product by Product URI. However, with bidirectional JPA mappings, pay attention to the owning side. In the Product.category example, Product is the owning side. Modifying only the inverse collection Category.products in memory does not automatically ensure the foreign key category_id is updated. API design and mappings should update the owning side or synchronize both sides in business logic.

DELETE on an association resource is an unbind operation under Spring Data REST's contract. If an application needs to delete a specific element from a collection association, design and test the specific collection semantics in the model; do not assume deleting an item resource will automatically remove the relationship without deleting the target entity.

## 8. Integration Testing

Test through real Spring Data REST HTTP endpoints to confirm the association resource is exported and URI binding works. Example test cases for the Product.category model:

| Test Case | Request | Expected Result |
|---|---|---|
| Discover link | GET /products/{id} | HAL contains a category link pointing to the association resource |
| Read link | GET /products/{id}/category | Returns current association state |
| Bind category | PUT association with one Category URI and text/uri-list | Request succeeds; Product references the correct Category |
| Change category | PUT association with a different Category URI | Product references the new Category |
| Unbind optional category | DELETE association | Product.category becomes null; Category still exists |
| Multiple URIs for to-one | PUT body containing two URIs | 400 Bad Request |
| Unbind required category | DELETE non-optional association | Rejected, typically 405 per contract |
| Wrong media type | PUT sending JSON object instead of text/uri-list | Request rejected due to invalid media type/body |

The integration test example below assumes the application has ProductRepository and CategoryRepository. Use the repositories to seed test data, call the HTTP association endpoint, and then read back the persisted data.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ProductCategoryAssociationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ProductRepository products;

    @Autowired
    CategoryRepository categories;

    @Test
    void bindsAndUnbindsCategoryByUri() throws Exception {
        Category category = categories.save(new Category("Stationery"));
        Product product = products.save(new Product("Notebook"));

        String associationPath =
                "/products/" + product.getId() + "/category";
        String categoryUri =
                "http://localhost/categories/" + category.getId();

        mockMvc.perform(put(associationPath)
                .contentType("text/uri-list")
                .content(categoryUri))
            .andExpect(status().is2xxSuccessful());

        Product linked = products.findById(product.getId()).orElseThrow();
        assertThat(linked.getCategory().getId()).isEqualTo(category.getId());

        mockMvc.perform(delete(associationPath))
            .andExpect(status().is2xxSuccessful());

        Product unlinked = products.findById(product.getId()).orElseThrow();
        assertThat(unlinked.getCategory()).isNull();

        assertThat(categories.findById(category.getId())).isPresent();
    }
}
~~~

In a real project, configure an isolated test database and verify transaction boundaries. If the entity relation is lazy-loaded, perform assertions within a transaction or use an appropriate query/projection. This test assumes the category property is nullable and the test schema allows NULL in category_id.

Add tests for required associations, multiple URIs in to-one associations, and authorization. If using Spring Security, call endpoints as an authorized principal and also test 401/403 cases. Do not let exported association resources accidentally allow users to link products to categories they are not authorized to use.

## 9. Troubleshooting

| Symptom | Common Cause | How to Check and Fix |
|---|---|---|
| GET Product has no category link | Association is not recognized by Spring Data REST or is hidden | Check JPA mapping, exported Category repository, detection strategy, and @RestResource(exported = false). |
| PUT returns 415 Unsupported Media Type | Sending application/json instead of text/uri-list | Set Content-Type: text/uri-list and send the plain URI in the body. |
| PUT returns 400 Bad Request | Sending multiple URIs to a to-one association or malformed URI list body | Send exactly one Category URI for Product.category; check newlines and URI syntax. |
| PUT cannot find Category | Wrong target URI, resource does not exist, or repository is not exported | GET the Category URI first, use the self href published by HAL, and verify repository mapping. |
| PUT succeeds but data does not change | Sent to wrong association URI, checking wrong database, or mapping is not the owning side | Read back the association resource, check Product.category, and check the foreign key in the test database. |
| DELETE returns 405 | Association is declared non-optional or operation is not exported | Check optional, nullable, schema constraints, and association resource contract. |
| DELETE causes a database constraint error | Entity allows null but category_id column is still NOT NULL | Align JPA mapping and schema migration; only allow unlinking if business rules permit null. |
| Deleting a Product also deletes Category | Cascade REMOVE configured on a shared many-to-one relationship | Review cascades; never cascade remove from Product to a shared Category. |
| Association link missing in HAL | Target repository not exported, property hidden, or mapping is not a linkable association | Check repository and property mapping; inspect the item resource HAL response. |
| Frontend sends ID instead of URI | Client treats association as a JSON foreign-key field | Obtain Category self href from HAL and send that URI with text/uri-list. |
| Product and Category appear out of sync in JPA | Bidirectional relationship updated on only one side in memory | Update the owning side Product.category; if an inverse collection exists, sync both sides in a domain helper/service. |

## 10. Implementation Checklist

- [ ] ProductRepository and CategoryRepository are exported at the expected paths.
- [ ] Product.category is published by Spring Data REST as an association link.
- [ ] Clients discover the association href and Category self href from HAL.
- [ ] PUT requests use Content-Type text/uri-list.
- [ ] To-one associations accept exactly one URI.
- [ ] Product.category is optional and category_id column is nullable if business rules allow unlinking.
- [ ] Association DELETE only removes the link without deleting the Category.
- [ ] JPA mapping updates the owning side.
- [ ] Cascade remove is not used to delete shared Categories.
- [ ] Authorization checks permissions on both Product and target Category.
- [ ] Integration tests cover linking, re-linking, unlinking, and error cases.
- [ ] Clients re-read the resource after operations to confirm link state.

## 11. Official References

- [Spring Data REST — Repository resources / The Association Resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): association sub-resources, GET/PUT/POST/DELETE methods, text/uri-list media type, and bind/unbind behavior.
- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): repository detection, exporting resources, and base path configuration.
- [Jakarta Persistence — ManyToOne](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/manytoone): mapping many-to-one relationships and the optional attribute.
- [Jakarta Persistence — JoinColumn](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/joincolumn): mapping foreign-key columns and nullable constraints.
- [Spring Data REST — Customizing](https://docs.spring.io/spring-data/rest/reference/customizing/index.html): customizing how Spring Data REST exports repositories, resources, and associations.