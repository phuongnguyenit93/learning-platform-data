# Controlling Which Repository Resources Appear in the Contract

Spring Data repositories are designed for data access inside an application. When Spring Data REST is added, some repositories are also exported as HTTP resources with collection, item, search, and association paths. This is convenient for quickly building CRUD APIs, but it also means a repository interface can unintentionally become a public API surface.

In a Spring Boot application using `springdoc-openapi`, two separate concerns must be controlled: **which repositories Spring Data REST exports as HTTP resources** and **which resources appear in the OpenAPI documentation**. Hiding a path from OpenAPI does not disable the runtime endpoint. Conversely, if a repository is not exported at runtime, springdoc should not document that endpoint as a callable API.

## 1. A Repository Is Not Automatically an API Contract

A repository like the following is primarily a data-access abstraction:

~~~java
public interface ProductRepository extends JpaRepository<Product, UUID> {
    Optional<Product> findBySku(String sku);
}
~~~

If the application only uses Spring Data JPA, this interface does not automatically create HTTP endpoints. Services and controllers can call the repository internally:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductRepository products;

    ProductController(ProductRepository products) {
        this.products = products;
    }

    @GetMapping("/{id}")
    ProductResponse get(@PathVariable UUID id) {
        Product product = products.findById(id)
                .orElseThrow(ProductNotFoundException::new);
        return ProductResponse.from(product);
    }
}
~~~

With Spring Data REST present, a repository can be exported as a resource without a hand-written controller. For example, a public repository can generate:

- A collection resource to list and create resources.
- An item resource to read, update, or delete a single resource.
- A search resource for exported query methods.
- An association resource to navigate or update relationships.

Therefore, repository export must be treated as an API design decision. Do not let whether an interface is `public` or extends `CrudRepository` accidentally determine the client-facing contract.

## 2. Which Resources Does Spring Data REST Generate?

Suppose the application configures the base path as `/data` and has the repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import java.util.Optional;
import java.util.UUID;

@RepositoryRestResource(
        path = "products",
        collectionResourceRel = "products",
        itemResourceRel = "product"
)
public interface ProductRepository extends JpaRepository<Product, UUID> {

    @RestResource(path = "by-sku", rel = "by-sku")
    Optional<Product> findBySku(String sku);
}
~~~

Spring Data REST can generate URLs such as:

| Resource | Illustrative URL | Purpose |
|---|---|---|
| Collection | `GET /data/products` | Retrieve the list of products. |
| Item | `GET /data/products/{id}` | Retrieve a single product. |
| Search root | `GET /data/products/search` | Discover exported query methods. |
| Finder | `GET /data/products/search/by-sku?sku=...` | Find a product by SKU. |

Actual paths and HTTP methods depend on the repository, annotations, configuration, and Spring Data REST version. Spring Data REST typically represents resources using HAL, consisting of data and links in `_links`. Thus, the contract is not just flat JSON DTOs; clients can also navigate by link relations.

### 2.1. Repository Methods Can Become Endpoints

A finder method can be exported as a search resource. For example, `findBySku` above is placed under `/search/by-sku`. The `@RestResource` annotation can change the path and relation name, or disable exporting the method with `exported = false`.

Not every internal method should become an endpoint. Methods used for batch jobs, business processing, internal lookups, or administrative queries should remain in the repository without being exposed over HTTP.

### 2.2. Collection and Item Resources Can Have Different HTTP Method Sets

Spring Data REST infers HTTP methods based on supported repository methods. For example, if a repository does not provide an appropriate delete capability, the item resource does not necessarily support DELETE. However, for repositories extending `CrudRepository`/`JpaRepository`, many CRUD methods are inherited by default.

If the API is read-only, or does not allow clients to delete directly, configure exposure explicitly. Do not rely on the UI not showing a delete button to consider an endpoint disabled.

## 3. Disabling Export for an Entire Repository

If a repository only serves internal business logic, mark `exported=false` at the repository level:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import java.util.UUID;

@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, UUID> {
}
~~~

The repository can still be injected and used in services, jobs, or listeners. This annotation prevents Spring Data REST from exporting it as an HTTP resource. It does not remove the repository bean and does not prevent internal data access through application code.

A repository that is not exported will have no corresponding collection/item/search resources for springdoc to describe. After making changes, verify both HTTP endpoints and the OpenAPI documentation to confirm the result.

## 4. Switching from Default to Opt-In

By default, Spring Data REST exports public repositories that match the default detection rules. This is convenient for simple CRUD applications, but makes it easy to accidentally create new APIs whenever the team adds a public repository.

You can configure the repository detection strategy to restrict which repositories are exported:

| Strategy | Meaning |
|---|---|
| DEFAULT | Export public repositories or repositories annotated with RepositoryRestResource, unless exported=false. |
| ALL | Consider all repositories, regardless of visibility or annotations. |
| VISIBILITY | Only consider public repository interfaces. |
| ANNOTATED | Only export repositories annotated with RepositoryRestResource or RestResource that are not marked exported=false. |

For a clear opt-in policy, Spring Data REST 3.1 and later provide `disableDefaultExposure()`. This method switches detection to `ANNOTATED` and disables default exposure of repository methods; repositories and methods must be explicitly annotated.

~~~java
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Component
class RepositoryExposureConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.disableDefaultExposure();
        config.setBasePath("/data");
        config.setDefaultPageSize(20);
        config.setMaxPageSize(100);
    }
}
~~~

With the configuration above:

- Repositories not explicitly marked will not automatically become resources.
- Exported repositories must be declared with `@RepositoryRestResource`.
- Query methods must be annotated with `@RestResource` if default method exposure is disabled.
- The base path is `/data`.
- The default page size is 20 and cannot exceed 100 via Spring Data REST configuration.

If you are using Spring Data REST prior to 3.1, check the API for that version. You can configure the `ANNOTATED` detection strategy directly, but verify the repository method exposure policy separately because `disableDefaultExposure()` also disables default method exposure.

### 4.1. Using ANNOTATED Alone May Not Be Enough

`setRepositoryDetectionStrategy(ANNOTATED)` controls which repositories are considered for export. If the application still enables default repository method exposure, CRUD methods of selected repositories may continue to be exported under default rules.

If the goal is opt-in at both repository and method levels, use `disableDefaultExposure()` on supported versions. This makes the intent to publish an API explicit in the source code.

## 5. Disabling a Query Method While Keeping the Repository

A repository may need to keep a finder method for internal services while disallowing direct client calls. Use `@RestResource(exported = false)` on the method:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import java.util.List;
import java.util.UUID;

@RepositoryRestResource(path = "users")
public interface UserRepository extends JpaRepository<User, UUID> {

    @RestResource(path = "by-status", rel = "by-status")
    List<User> findByStatus(UserStatus status);

    @RestResource(exported = false)
    List<User> findByEmail(String email);
}
~~~

In the example, the finder method by status can still be exported under default rules, while the finder by email remains usable from Java code without being exported as a search endpoint.

Check both the search root and the finder path. If a method is disabled, the corresponding link relation should not appear in the HAL search resource and that path should not exist in OpenAPI.

## 6. Controlling CRUD Methods and HTTP Methods

When a repository extends `CrudRepository` or `JpaRepository`, methods like `save` and `delete` can enable POST, PUT, PATCH, or DELETE capabilities. If you want to keep the repository while restricting client operations, there are two approaches:

1. Override the relevant CRUD methods and annotate with `@RestResource(exported = false)` according to the Spring Data version API in use.
2. Use `RepositoryRestConfiguration.getExposureConfiguration()` to restrict HTTP methods on collection or item resources.

Example disabling PATCH for item resources:

~~~java
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.HttpMethod;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
class RestMethodExposureConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.getExposureConfiguration()
                .withItemExposure((metadata, methods) ->
                        methods.disable(HttpMethod.PATCH));
    }
}
~~~

This example applies to item exposure globally. If you only want to restrict a single domain type, use the type-specific APIs of `ExposureConfiguration`, such as configuring `forDomainType(Product.class)`, and verify the exact methods provided by your Spring Data REST version.

Do not assume that disabling one Java method always disables one exact HTTP method. Some repository methods may be shared to implement multiple HTTP operations. Spring Data REST documentation notes that disabling inherited CRUD methods requires overriding all corresponding overloads; for `delete`, check both the ID-based and entity-based forms according to your version.

### 6.1. Restricting PUT Creation and PATCH Updates

Spring Data REST provides exposure configuration to control certain item resource behaviors:

~~~java
config.getExposureConfiguration()
        .forDomainType(Product.class)
        .disablePutForCreation();
~~~

The call above disables using PUT to directly create item resources for the `Product` domain type. Global or type-specific rules can be combined to allow only operations that fit the contract.

If the API needs complex business workflows such as order approval, refunds, publishing, or state transitions, a dedicated controller endpoint usually expresses the intent better than opening direct CRUD on the entity.

## 7. Hiding Association Resources and Non-Client Fields

Spring Data REST can export links to entity associations. For example, `Product` has a relationship to `Supplier` or `Review`. If a relationship is for internal use only, annotate the property with `@RestResource(exported = false)`:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import org.springframework.data.rest.core.annotation.RestResource;
import java.util.UUID;

@Entity
class Product {

    @Id
    @GeneratedValue
    private UUID id;

    private String name;

    @ManyToOne
    @RestResource(exported = false)
    private Supplier supplier;
}
~~~

This controls exporting the property/association through Spring Data REST. Verify the actual HAL representation and association resources after configuration.

### 7.1. Do Not Use Hiding Associations as a Substitute for Protecting Sensitive Data

Hiding an association link does not mean every sensitive field of the entity is protected. If an entity has a password hash, secret, internal note, or private information, design a public representation that includes only necessary fields.

Options:

- Use a dedicated DTO in a controller.
- Use a projection that selects only fields allowed to be exported.
- Use appropriate Jackson annotations for fields that must not be serialized.
- Separate persistence entities from client-facing representations.

Spring Data REST may allow projections to expose fields differently from the default representation. Therefore, when hiding a field with `@RestResource(exported = false)`, review all related projections and do not re-introduce sensitive fields through a projection.

## 8. Projections Change Representation, Not Exposure Policy

Projections let you select a subset of fields to include in the representation. For example:

~~~java
import org.springframework.data.rest.core.config.Projection;
import java.math.BigDecimal;

@Projection(name = "summary", types = Product.class)
interface ProductSummary {
    String getName();
    BigDecimal getPrice();
}
~~~

A projection can be used as the default excerpt:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import java.util.UUID;

@RepositoryRestResource(
        path = "products",
        excerptProjection = ProductSummary.class
)
interface ProductRepository extends JpaRepository<Product, UUID> {
}
~~~

Projections make collection representations more compact, but do not automatically hide repositories, finders, CRUD methods, or association resources. If clients can request other projections, verify which projections are discovered and which fields they return.

Do not use projections as an authorization layer. If one group of clients is allowed to view different fields than another, a security policy or separate permission-based API representations are required; a public projection does not distinguish client identities on its own.

## 9. Limiting Pagination and Sorting on Repository Resources

Spring Data REST typically supports `page`, `size`, and `sort` parameters on collection resources. Without limits, clients can request overly large pages or sort on inappropriate fields.

You can configure this via `application.yml`:

~~~yaml
spring:
  data:
    rest:
      base-path: /data
      default-page-size: 20
      max-page-size: 100
~~~

Or configure base path and page size in `RepositoryRestConfigurer` as shown earlier. Maintain only one primary source of configuration to avoid mismatched values between properties and Java config.

Spring Data REST provides sorting by domain properties. If the contract only allows certain sort fields, enforce it at the query/repository layer or move the endpoint to a dedicated controller with an allow-list. Do not assume that setting a max page size also restricts sort fields.

For public APIs, consider using DTO responses and explicit query parameters if strict sort/filter rules are needed, rather than letting the entire repository structure dictate the contract.

## 10. Springdoc Integration with Spring Data REST

Springdoc includes support for integrating Spring Data REST. The `springdoc.enable-data-rest` property enables/disables this integration; the published default value in springdoc documentation is `true` when the feature and corresponding classes are present.

Example keeping the integration:

~~~yaml
springdoc:
  enable-data-rest: true
~~~

If you do not want springdoc to include Spring Data REST endpoints in the documentation:

~~~yaml
springdoc:
  enable-data-rest: false
~~~

**Note:** `springdoc.enable-data-rest: false` only disables Springdoc's integration for Spring Data REST. It does not disable the HTTP resources already exported by Spring Data REST. To prevent clients from calling resources, you must change exposure in Spring Data REST or protect endpoints with Spring Security.

### 10.1. Distinguishing the Three Control Layers

| Mechanism | Effect | No effect on |
|---|---|---|
| `@RepositoryRestResource(exported = false)` | Does not export the repository as HTTP resources. | Does not remove the repository bean or forbid internal services from using it. |
| `@RestResource(exported = false)` | Hides a repository method or property/association from Spring Data REST. | Does not automatically change access permissions of other controller endpoints. |
| `springdoc.enable-data-rest=false` | Excludes Spring Data REST endpoints brought in via springdoc's integration. | Does not disable runtime HTTP resources. |
| `GroupedOpenApi.pathsToExclude(...)` | Excludes paths from an OpenAPI group. | Does not delete endpoints and does not create authorization. |
| Spring Security | Blocks or allows runtime requests by identity/authority. | Does not automatically remove operations from OpenAPI unless documentation is also configured. |

These are distinct layers. When you want a resource to completely not exist for clients, control Spring Data REST exposure and authorization. When you only want public documentation not to display an operation while internal teams still use the endpoint, split groups and secure the corresponding group.

## 11. Controlling OpenAPI Content by Group

If the application has both public and internal resources, create groups according to approved paths:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class RepositoryOpenApiGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/data/products/**")
                .pathsToExclude("/data/products/search/internal")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/data/**")
                .build();
    }
}
~~~

The example illustrates path selection; specific exclude patterns need to be tested against your springdoc version's matcher and actual paths. If the public API only consists of a few resources, allow-listing specific paths is usually easier to review than excluding broad patterns.

The `public` group can be served at `/v3/api-docs/public` and the `internal` group at `/v3/api-docs/internal`. Protect internal documentation URLs with Spring Security; groups are not access controls.

## 12. Testing OpenAPI and Runtime After Restricting Exposure

After every repository exposure change, test both HTTP endpoints and OpenAPI:

1. Repositories allowed to be exported have the correct collection paths.
2. Item resources have the exact allowed HTTP methods.
3. Hidden query methods do not appear under the search root.
4. Hidden associations no longer have corresponding links/representations.
5. `exported=false` repositories no longer have collection/item/search resources.
6. Springdoc accurately reflects remaining paths and methods.
7. Projections do not leak fields removed from public representations.
8. Public groups do not contain internal paths.

Suppose the base path is `/data` and `ProductRepository` is exported:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.hamcrest.Matchers.containsString;

@SpringBootTest
@AutoConfigureMockMvc
class RepositoryExposureContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesProductCollectionAndDocumentsIt() throws Exception {
        mockMvc.perform(get("/data/products"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("/data/products")));
    }

    @Test
    void doesNotExposeInternalAuditRepository() throws Exception {
        mockMvc.perform(get("/data/internal-audit-records"))
                .andExpect(status().isNotFound());

        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        containsString("/data/internal-audit-records"))));
    }
}
~~~

The test above assumes the audit repository has been disabled via `@RepositoryRestResource(exported = false)` and the application has no other controller using the same path. Spring Data REST may return different statuses depending on mappings and security configuration; the important thing is verifying the endpoint cannot perform operations and is no longer published in the documentation.

### 12.1. Testing Search Resources and HAL Links

For a finder method with path `by-sku`, test the search resource:

~~~java
mockMvc.perform(get("/data/products/search"))
        .andExpect(status().isOk())
        .andExpect(content().string(containsString("by-sku")));
~~~

If the method is annotated with `@RestResource(exported = false)`, the corresponding link relation should not appear. Checking HAL responses helps detect endpoints that remain discoverable even if the OpenAPI path was filtered.

### 12.2. Testing Whether OpenAPI Includes Data REST

When `springdoc.enable-data-rest=true`, check repository resource paths in `/v3/api-docs`. When set to `false`, verify they no longer appear from this integration; then still call the runtime endpoint to confirm Spring Data REST remains active if that is intended.

Do not test only JSON. Verify actual HTTP methods, HAL links, status codes, and access permissions.

## 13. Common Mistakes

- **Assuming every repository is internal-only**: Spring Data REST can export public repositories as HTTP resources.
- **Assuming springdoc only documents controllers**: when Data REST integration is enabled, documentation can include resources generated from repositories.
- **Only hiding paths from OpenAPI**: runtime endpoints remain callable.
- **Only setting springdoc.enable-data-rest=false**: Spring Data REST's HTTP export feature remains active.
- **Using ANNOTATED while forgetting method exposure**: selected repositories may still export CRUD/query methods under default settings.
- **Forgetting exported=false on sensitive repositories**: collection and item resources may be exposed.
- **Forgetting to hide internal finder methods**: methods may appear in `/search`.
- **Hiding only one delete overload**: another method may still support HTTP DELETE depending on version and mappings.
- **Hiding an association while a projection still returns the field**: another representation may bring the field back.
- **Using projections as authorization**: projections do not enforce per-user permissions.
- **Not checking HAL links**: resources may remain discoverable via link relations.
- **Not limiting page size and sort**: clients can send oversized requests or expensive queries.
- **Using groups as a security boundary**: OpenAPI groups only filter documentation, not HTTP requests.

## 14. Repository Review Process Before Exposing an API

1. **List repositories**: determine which interfaces are internal-only and which are designed for HTTP.
2. **Choose an exposure policy**: use opt-in with `disableDefaultExposure()` if repositories and methods should be explicitly annotated.
3. **Annotate repositories**: only add `@RepositoryRestResource` to approved resources; use `exported=false` for internal repositories.
4. **Review query methods**: hide non-client finders with `@RestResource(exported = false)`.
5. **Review CRUD methods**: restrict POST, PUT, PATCH, and DELETE according to business rules.
6. **Review associations and fields**: do not export unnecessary relationships or sensitive data.
7. **Review projections**: ensure hidden fields are not reintroduced.
8. **Limit queries**: set page sizes, review sort/filter options and query cost.
9. **Configure springdoc**: enable/disable Data REST integration intentionally and split groups by audience.
10. **Run runtime and contract tests**: verify resources, HAL links, HTTP methods, and `/v3/api-docs`.

## 15. Review Checklist

- [ ] Each repository is classified as internal, public, or partner-facing.
- [ ] Repositories not intended for HTTP have `exported=false`.
- [ ] Detection strategy matches the opt-in/opt-out policy.
- [ ] If using opt-in, default repository method exposure is disabled.
- [ ] Internal query methods do not appear in the search resource.
- [ ] CRUD HTTP methods match business requirements.
- [ ] Associations and sensitive fields are not exported unintentionally.
- [ ] Projections do not re-expose hidden fields.
- [ ] Page size and sort/filter are appropriately limited.
- [ ] `springdoc.enable-data-rest` is configured intentionally.
- [ ] OpenAPI groups are not mistaken for authorization mechanisms.
- [ ] Tests verify HAL links, runtime endpoints, and OpenAPI paths.

## 16. References

- [Spring Data REST – Customizing repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST – Configuring the REST URL path and hiding resources](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST – RepositoryDetectionStrategy](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/mapping/RepositoryDetectionStrategy.RepositoryDetectionStrategies.html)
- [Spring Data REST – RepositoryRestConfiguration](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [springdoc-openapi – Core properties](https://springdoc.org/core-properties.html)
- [springdoc-openapi v2 – Core properties](https://springdoc.org/v2/core-properties.html)
- [OpenAPI Specification 3.1.2](https://spec.openapis.org/oas/v3.1.2.html)

Repositories are data-access components; Spring Data REST decides which repositories become HTTP resources; springdoc integrates and describes exported resources. Set exposure to opt-in, restrict methods and associations, inspect projections, and verify both runtime HAL and OpenAPI together. When these three layers align, the contract publishes only the resources that clients are permitted to use.
