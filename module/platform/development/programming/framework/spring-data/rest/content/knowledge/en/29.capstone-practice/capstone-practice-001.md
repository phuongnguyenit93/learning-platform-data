# Building a Catalog Management API with Entities, Repositories, and HAL

## Objective

This practice builds a product catalog management API using Spring Data REST. The application declares domain entities and Spring Data repositories; Spring Data REST automatically exports repositories as REST resources, generates HTTP endpoints for CRUD, search, and associations, and returns HAL JSON representations.

The example model has two entities:

- `Category`: product category, consisting of a code, name, description, and active status.
- `Product`: product, with a many-to-one relationship to `Category`.

The API allows clients to discover resources from the root URL, read category lists and details, create/update/delete categories, search by name, read products, and link a product to a category by URI. Package names, database names, and fields can be adjusted to fit real-world projects.

## 1. How Does Spring Data REST Work?

Spring Data REST exports Spring Data repositories as REST resources via Spring MVC. The repository is the primary declaration point: the domain type and repository methods determine which resources are exported and which HTTP methods are supported.

Example:

```java
public interface CategoryRepository
        extends CrudRepository<Category, Long> {
}
```

Without customization, Spring Data REST creates a collection resource using the lowercase pluralized domain class name, such as `/categories`, along with item resources following the pattern `/categories/{id}`. You can change the path and relation using `@RepositoryRestResource`.

Spring Data REST uses HAL as the default hypermedia representation. HAL JSON commonly includes the following sections:

- `_links`: links to related resources, profiles, or actions.
- `_embedded`: resources embedded within a collection representation.
- `page`: pagination metadata when the response is paged.

Clients should discover and follow these links to navigate to subsequent resources instead of constructing URLs from naming conventions.

## 2. Creating the Project and Dependencies

With Spring Boot, add the Spring Data REST starter and the persistence store starter. For example, using Spring Data JPA and H2 for the practice environment:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

When using Spring Boot dependency management, you do not need to declare versions for the starters manually. With Gradle, the corresponding dependencies are `implementation("org.springframework.boot:spring-boot-starter-data-rest")`, `implementation("org.springframework.boot:spring-boot-starter-data-jpa")`, and `runtimeOnly("com.h2database:h2")`.

In production, replace H2 with an appropriate database driver and use a migration tool such as Flyway or Liquibase to manage the schema. Spring Data REST does not create a persistence store on its own; it exports the repositories configured in the application.

Minimal configuration for a local environment:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:catalogdb
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: update
  data:
    rest:
      base-path: /api
```

With the configuration above, the Spring Data REST root is `/api`. Do not use `ddl-auto: update` as a production schema management strategy when controlled migrations are needed.

## 3. Designing the Entities

Place the entities in a package scanned by Spring Boot component/entity scanning, such as `com.example.catalog.domain`.

### 3.1. Category

```java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 40)
    @Column(nullable = false, unique = true, length = 40)
    private String code;

    @NotBlank
    @Size(max = 120)
    @Column(nullable = false, length = 120)
    private String name;

    @Size(max = 500)
    @Column(length = 500)
    private String description;

    @Column(nullable = false)
    private boolean active = true;

    protected Category() {
        // Required by JPA.
    }

    public Category(String code, String name, String description) {
        this.code = code;
        this.name = name;
        this.description = description;
        this.active = true;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Key points to note:

- `@Entity` marks a persistence entity.
- `@Id` and `@GeneratedValue` define the primary key.
- `@Column(nullable = false, unique = true)` creates database-level constraints for the category code.
- `@NotBlank` and `@Size` describe data constraints. A Bean Validation provider and appropriate validator configuration are required for these constraints to be enforced in the REST flow.
- The no-argument constructor has `protected` visibility so JPA can instantiate the entity. Clients do not need to send `id` because the database generates the key.

### 3.2. Product and Relationship to Category

```java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String sku;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
    }

    public Product(String sku, String name, BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public Category getCategory() {
        return category;
    }

    public void setCategory(Category category) {
        this.category = category;
    }
}
```

The `@ManyToOne` relationship allows multiple products to belong to the same category. When both `Product` and `Category` have exported repositories, Spring Data REST can represent the relationship as an association link. Clients follow this link to read or update the association.

This example does not add a `products` collection to `Category` to avoid an unnecessary bidirectional object graph in an introductory exercise. With a bidirectional domain model, you must consider lazy loading, JSON recursion, projections, and how associations are exposed.

## 4. Declaring Repositories and REST Paths

Create the `com.example.catalog.repository` package.

### 4.1. CategoryRepository

```java
package com.example.catalog.repository;

import com.example.catalog.domain.Category;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.jpa.repository.JpaRepository;

@RepositoryRestResource(
    path = "categories",
    collectionResourceRel = "categories"
)
public interface CategoryRepository
        extends JpaRepository<Category, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    Page<Category> findByNameContainingIgnoreCase(
            @Param("name") String name,
            Pageable pageable
    );
}
```

Explanation:

- `JpaRepository<Category, Long>` provides CRUD, paging, and sorting for the `Category` entity.
- `path = "categories"` defines the collection path.
- `collectionResourceRel = "categories"` defines the relation name in the HAL collection.
- `@RestResource(path = "by-name", rel = "by-name")` gives a readable name to the query resource.
- `@Param("name")` defines the query parameter sent by the client.
- `Page<Category>` together with `Pageable` allows the search endpoint to return paginated results.

Spring Data REST creates a search resource if the repository exports query methods. The query method above can be called at `/categories/search/by-name?name=book`.

### 4.2. ProductRepository

```java
package com.example.catalog.repository;

import com.example.catalog.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products"
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

When the application starts, Spring Data REST scans for repository interfaces and exports repositories that match the repository detection strategy. Under the default configuration, public repositories are generally exported unless explicitly marked not to be exported.

If you do not want to export a repository, declare `@RepositoryRestResource(exported = false)`. If you want to keep a repository method for internal use without creating an HTTP endpoint, apply `@RestResource(exported = false)` on the appropriate method. Carefully review inherited CRUD methods before exposing an API to production.

## 5. Generated Resources

With `spring.data.rest.base-path=/api`, the example API exposes the following URLs:

| Resource | URL | Purpose |
|---|---|---|
| API root | `GET /api` | Discover resource links |
| Category collection | `GET /api/categories` | List categories |
| Category item | `GET /api/categories/{id}` | Details of a single category |
| Create category | `POST /api/categories` | Create a category |
| Update category | `PUT /api/categories/{id}` | Replace category data |
| Partial update | `PATCH /api/categories/{id}` | Partially update a category |
| Delete category | `DELETE /api/categories/{id}` | Delete a category |
| Search by name | `GET /api/categories/search/by-name?name=...` | Search by name |
| Product collection | `GET /api/products` | List products |
| Product item | `GET /api/products/{id}` | Product details |
| Product category association | `GET/PUT /api/products/{id}/category` | Read or assign a category to a product |

Actual paths also depend on the servlet context path, custom base path, repository annotations, and export configuration.

## 6. Discovering the API with HAL

Call the API root with the HAL media type:

```bash
curl -i   -H "Accept: application/hal+json"   http://localhost:8080/api
```

The root response may look similar to:

```json
{
  "_links": {
    "categories": {
      "href": "http://localhost:8080/api/categories"
    },
    "products": {
      "href": "http://localhost:8080/api/products"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile"
    }
  }
}
```

This is an illustrative example. Actual links are generated from exported repositories and application configuration.

Clients can start from the root, read the `categories` relation, and follow its `href` link. When needing resource descriptions, clients follow the `profile` link. Spring Data REST provides ALPS metadata for repository resources; some profile endpoints can also return JSON Schema when the client sends `Accept: application/schema+json`.

### 6.1. Reading a Collection

```bash
curl -i   -H "Accept: application/hal+json"   "http://localhost:8080/api/categories?page=0&size=10&sort=name,asc"
```

A HAL collection response typically has the form:

```json
{
  "_embedded": {
    "categories": [
      {
        "code": "BOOKS",
        "name": "Books",
        "description": "Printed and digital books",
        "active": true,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/categories/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/categories{?page,size,sort}",
      "templated": true
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/categories"
    }
  },
  "page": {
    "size": 10,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
```

The `_embedded.categories` and `page` properties inform the client of the data and page state. The relation name `categories` is set via `collectionResourceRel`. Clients should use `next` or `prev` links when present instead of computing the next page URL manually.

## 7. Creating and Updating Categories

### 7.1. POST to Create

```bash
curl -i -X POST http://localhost:8080/api/categories   -H "Content-Type: application/json"   -H "Accept: application/hal+json"   --data '{
    "code": "BOOKS",
    "name": "Books",
    "description": "Printed and digital books",
    "active": true
  }'
```

The request body contains the entity fields. Clients do not need to send `id` because the key is generated by the database. On success, Spring Data REST typically returns `201 Created` and a `Location` header pointing to the newly created item resource. When `Accept` is provided, the response body includes the representation by default; if `Accept` is omitted, the body may be empty and the client follows `Location` to read the resource.

### 7.2. GET Item

```bash
curl -i   -H "Accept: application/hal+json"   http://localhost:8080/api/categories/1
```

### 7.3. PUT to Replace an Item

```bash
curl -i -X PUT http://localhost:8080/api/categories/1   -H "Content-Type: application/json"   -H "Accept: application/hal+json"   --data '{
    "code": "BOOKS",
    "name": "Books and Media",
    "description": "Updated category description",
    "active": true
  }'
```

`PUT` replaces the state of the resource with the submitted body. Ensure the body includes all fields that should be preserved, because fields omitted from the body may be interpreted as empty/default values depending on the mapping and entity.

### 7.4. PATCH for Partial Update

```bash
curl -i -X PATCH http://localhost:8080/api/categories/1   -H "Content-Type: application/merge-patch+json"   -H "Accept: application/hal+json"   --data '{"active": false}'
```

Use the media type and body that match JSON Merge Patch semantics. Spring Data REST supports JSON Patch and JSON Merge Patch media types for item PATCH; do not change the header if the body does not match the corresponding format.

### 7.5. DELETE to Remove a Category

```bash
curl -i -X DELETE http://localhost:8080/api/categories/1
```

Deletion may be rejected by foreign key constraints if products still reference the category. Category deletion rules in real-world applications should be designed according to business requirements: blocking deletion, reassigning products to another category, or applying an archive/soft-delete policy. Do not automatically enable cascade delete without understanding the data impact.

## 8. Searching, Pagination, and Sorting

The query method in `CategoryRepository` creates a search resource. Call:

```bash
curl -i   -H "Accept: application/hal+json"   "http://localhost:8080/api/categories/search/by-name?name=book&page=0&size=10"
```

Parameters:

- `name`: value bound to `@Param("name")`.
- `page`: page number, zero-based by default.
- `size`: number of items per page, typically defaulting to 20.
- `sort`: property and sort direction, such as `sort=name,asc`.

Search and sorting example:

```bash
curl -i   -H "Accept: application/hal+json"   "http://localhost:8080/api/categories/search/by-name?name=book&sort=name,asc&page=0&size=5"
```

If the repository method returns `Page` or `Slice` and accepts `Pageable`, Spring Data REST can provide metadata and navigation links. Configure an appropriate maximum page size to prevent clients from requesting excessively large datasets.

## 9. Managing Associations Between Product and Category

Because `Product` has a `category` field referencing an entity with an exported repository, the product item resource exposes an association link. Reading a product:

```bash
curl -i   -H "Accept: application/hal+json"   http://localhost:8080/api/products/10
```

The representation may include a link similar to:

```json
{
  "sku": "BOOK-001",
  "name": "Spring in Practice",
  "price": 29.90,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/10"
    },
    "category": {
      "href": "http://localhost:8080/api/products/10/category"
    }
  }
}
```

The `category` link points to the association resource. To assign a product to a category, send the category's URI:

```bash
curl -i -X PUT http://localhost:8080/api/products/10/category   -H "Content-Type: text/uri-list"   --data 'http://localhost:8080/api/categories/1'
```

Association `PUT` uses `text/uri-list`. This is a request to link an existing resource, not a JSON body to create an entity. After assigning, GET the association resource or re-GET the product to confirm the link.

## 10. Validation, Projections, and Metadata

### 10.1. Validation

You can use Jakarta Bean Validation annotations such as `@NotBlank`, `@Size`, and `@Positive` to declare data constraints. For business rules that depend on repositories or other state, Spring Data REST supports registering `Validator` beans by repository event such as `beforeCreate` and `beforeSave`.

Example of an event-named validator bean:

```java
@Component("beforeCreateCategoryValidator")
class CategoryCreateValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Category.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Category category = (Category) target;
        if (category.getCode() != null
                && category.getCode().contains(" ")) {
            errors.rejectValue(
                "code",
                "category.code.whitespace",
                "Category code must not contain spaces"
            );
        }
    }
}
```

The bean name uses the `beforeCreate` prefix so Spring Data REST attaches the validator to the creation event. If validation is also needed before updates, use the appropriate event such as `beforeSave`. Configure the validator according to your Spring Data REST version and verify returned errors with integration tests.

### 10.2. Projections and Excerpts

By default, Spring Data REST can expose exported domain properties. When clients need a condensed view, define a projection interface:

```java
@Projection(name = "summary", types = Category.class)
public interface CategorySummary {
    String getCode();
    String getName();
    boolean isActive();
}
```

The projection must be discoverable by Spring Data REST—for example, placed in the same package or a sub-package of the entity, or registered manually. Clients can request the item resource with `?projection=summary`.

Do not include sensitive data such as passwords, tokens, or internal-only fields in entity representations. Projections can expose fields even when they are hidden by another serialization configuration; only declare projections for fields that are genuinely allowed to be public.

### 10.3. Profile, ALPS, and JSON Schema

The root resource provides a `profile` link. By following this link, clients can discover metadata describing repository resources. Spring Data REST provides ALPS for repository transitions and properties; JSON Schema can be requested with `Accept: application/schema+json` on the appropriate profile resource.

Metadata helps clients understand resources and fields without guessing from Java class names. Even so, the public API contract should still be documented and version-controlled against breaking changes.

## 11. Controlling Repository Exposure and Security

Spring Data REST can export many CRUD methods simply by declaring a repository. That is convenient for simple APIs, but it means any eligible public repository can become an HTTP API.

Before deploying:

- Only export repositories intended for the public API.
- Use `@RepositoryRestResource(exported = false)` to hide repositories that should not be public.
- Use `@RestResource(exported = false)` to hide query methods or operations that should not expose endpoints.
- Review the repository detection strategy if the application has many internal repositories.
- Configure Spring Security for each resource group and HTTP method.
- Authorize DELETE, PUT, and PATCH according to business rules; do not assume an automatically generated endpoint is meant to be publicly accessible.

Spring Data REST supports method-level security with `@PreAuthorize` and `@Secured`. If you place a security annotation at the repository level and override a method to change permissions, note that method-level settings override repository-level settings; they do not combine automatically. Inherited delete methods have multiple overloads, so make sure all deletion paths are protected.

Spring Data REST works best when CRUD repositories accurately reflect the API contract. For multi-step workflows, orchestration, complex authorization checks, or business logic that cannot be expressed as CRUD, use a service layer and a custom controller rather than directly exporting every persistence operation.

## 12. Testing the API with MockMvc

Use `@SpringBootTest` and `@AutoConfigureMockMvc` to test Spring Data REST through the application context. The example assumes a test database and `CategoryRepository` are configured:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CatalogApiTests {

    private static final MediaType HAL_JSON =
            MediaType.parseMediaType("application/hal+json");

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private CategoryRepository categoryRepository;

    @BeforeEach
    void setUp() {
        categoryRepository.deleteAll();
        categoryRepository.save(
            new Category("BOOKS", "Books", "Printed books")
        );
    }

    @Test
    void rootPublishesCategoryLink() throws Exception {
        mockMvc.perform(get("/api").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.categories.href").exists());
    }

    @Test
    void listsCategoriesAsHalCollection() throws Exception {
        mockMvc.perform(get("/api/categories").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(HAL_JSON))
            .andExpect(jsonPath("$._embedded.categories[0].code")
                .value("BOOKS"));
    }

    @Test
    void createsCategory() throws Exception {
        mockMvc.perform(post("/api/categories")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(HAL_JSON)
                .content("""
                    {
                      "code": "GAMES",
                      "name": "Games",
                      "description": "Board and video games",
                      "active": true
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"));
    }

    @Test
    void searchesCategoriesByName() throws Exception {
        mockMvc.perform(get("/api/categories/search/by-name")
                .param("name", "book")
                .accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._embedded.categories[0].name")
                .value("Books"));
    }
}
```

Key imports:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Run the tests with `./mvnw test` or `./gradlew test` depending on your build tool. If tests receive 404, check repository detection, package scanning, and base path. If GET returns JSON without `_embedded.categories`, check the relation name in `@RepositoryRestResource` and the test data. If POST returns 400, inspect validation errors and the request body; if it returns 405, check whether the repository method is exported.

Beyond the tests above, consider adding tests for:

- Category item GET/PUT/PATCH/DELETE.
- Query methods when there are no results and across multiple pages.
- Product association GET/PUT and non-existent URIs.
- Validation when `code` or `name` is blank or exceeds max length.
- Access permissions for regular users and administrators.
- Confirming that repositories or methods marked `exported = false` do not expose public endpoints.

## 13. Common Errors

| Symptom | Cause to Check |
|---|---|
| GET root does not include the `categories` link | Repository is not exported, wrong package scan, or detection strategy |
| GET `/categories` returns 404 | Incorrect base path, path annotation, or repository detection |
| POST returns 405 | Repository does not export `save`, or the method is hidden |
| POST returns 400 | Invalid JSON, wrong field mapping, or validation failure |
| POST returns 415 | Unsupported `Content-Type`; collection POST typically accepts JSON/HAL JSON |
| PATCH returns 415 | Incorrect media type or JSON Patch/Merge Patch structure |
| Association PUT returns 415 | Must use `Content-Type: text/uri-list` |
| Association PUT returns 400 | Invalid URI list or multiple URIs sent to a to-one association |
| Collection response has no embedded data | No records exist, different relation name, or customized representation |
| Search link is missing | Repository has not declared an exported query method |
| Sensitive data appears in HAL | Entity is exposing fields that should not be public; check Jackson mapping and projections |

## 14. Practice Completion Checklist

- [ ] Added Spring Data REST and the appropriate persistence starter.
- [ ] Created the `Category` entity with primary key, unique code, and required fields.
- [ ] Created the `Product` entity and its relationship to `Category`.
- [ ] Declared `CategoryRepository` and `ProductRepository`.
- [ ] Explicitly configured collection paths and relation names.
- [ ] GET root returns HAL links to categories, products, and profile.
- [ ] GET collection and item return HAL JSON.
- [ ] POST creates a category and returns `Location`.
- [ ] PUT/PATCH/DELETE behave according to the chosen contract.
- [ ] Search query method is discoverable via the search resource.
- [ ] `Product` → `Category` association is updated using a URI list.
- [ ] Restricted exported data and configured access permissions.
- [ ] Wrote integration tests for core operations and common error cases.

## Official Documentation

1. [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): starter, auto-configuration, repository detection, and base path.
2. [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): how repositories become collection, item, association, search, and query resources.
3. [Spring Data REST — Domain Object Representations](https://docs.spring.io/spring-data/rest/reference/representations.html): JSON representation and how Spring Data REST maps domain objects.
4. [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): defining projections and excerpts to customize representations.
5. [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): page, size, sort, and navigation links.
6. [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html): ALPS and JSON Schema.
7. [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): registering validators by repository events.
8. [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html): method-level security with Spring Security.
9. [Spring Data JPA — Defining Repository Interfaces](https://docs.spring.io/spring-data/jpa/reference/repositories/definition.html): domain-specific repositories, CRUD interfaces, and paging/sorting interfaces.
10. [Spring Framework — MockMvc](https://docs.spring.io/spring/reference/testing/mockmvc.html): testing Spring MVC requests/responses within the application context.

*Examples use Spring Boot, Spring Data JPA, and Jakarta Persistence. Verify packages, starters, and documentation versions against your application's actual dependencies before deploying.*