# Distinguishing Document Groups from @Tag and API Versioning

When a Spring Boot application has many controllers, multiple user groups, or multiple endpoint versions, OpenAPI documentation can become long and hard to navigate. springdoc-openapi provides **document groups** to generate multiple OpenAPI documents from the same application. Within each document, **@Tag** categorizes operations by function. Meanwhile, **API versioning** defines the contract a client integrates against and how the server preserves compatible behavior.

These three concepts are related yet solve three different problems:

- Groups decide which operations appear in an OpenAPI document.
- Tags place operations into functional groups inside a single document.
- API versions define the contract version and endpoint behavior used by clients.

Understanding this boundary helps organize Swagger UI, maintain v1/v2 APIs, and avoid confusing documentation splitting with changing endpoints or access controls.

## 1. Distinguishing Groups, Tags, and API Versions

| Concept | Purpose | Common Declaration | Result |
|---|---|---|---|
| Document group | Create an OpenAPI document from a filtered set of operations | GroupedOpenApi, springdoc.group-configs | A separate document accessible via its group URL |
| Tag | Categorize operations by function within a document | @Tag, @Operation(tags = ...) | Operation groupings in Swagger UI and OpenAPI |
| API version | Manage API contracts by version | Path, header, media type, or other routing strategies | Endpoints/behaviors corresponding to each version |

For example, an e-commerce application can be organized as follows:

- Group public-v1 contains public endpoints of API v1.
- Group internal-v1 contains administrative and internal integration endpoints of API v1.
- Inside group public-v1, operations are tagged Catalog, Orders, and Customers.
- API v2 can change response structures or business rules and be published in group public-v2.

Groups do not create API versions automatically, tags do not filter endpoints out of a document, and creating groups does not alter runtime routes. Endpoints remain governed by Spring MVC and application configuration.

## 2. Document Groups in springdoc-openapi

A document group is a documentation view built from the application's endpoints. Each group can select controllers by package, path, or other filter criteria supported by the Springdoc version.

For example:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/v1/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
            .group("internal-v1")
            .pathsToMatch("/api/v1/internal/**")
            .build();
    }
}
~~~

These two beans generate two separate documents. Endpoints matching /api/v1/public/** go into group public-v1; endpoints matching /api/v1/internal/** go into group internal-v1. The group name is the identifier used in the document URL.

In Springdoc 2.x, GroupedOpenApi typically lives in org.springdoc.core.models. In older versions, the package may differ; use the API matching your project's actual dependency.

### 2.1. Filtering by Package and Path

You can select endpoints by controller package:

~~~java
@Bean
GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .packagesToScan("com.example.store.catalog.web")
        .build();
}
~~~

Or filter by path:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/partner/**", "/api/v1/partners/**")
        .pathsToExclude("/partner/internal/**")
        .build();
}
~~~

packagesToScan works well when package layout mirrors module boundaries. pathsToMatch works well when URLs express API boundaries. You can combine filter criteria if needed; always verify the final operation set in the generated document, especially when a controller defines multiple mappings.

Do not treat package names as a public contract for clients. Packages are a source-code organization choice and can change during refactoring. URLs and endpoint semantics are what clients integrate against.

## 3. Configuring Groups in application.yml

Besides creating beans, you can declare groups in configuration:

~~~yaml
springdoc:
  group-configs:
    - group: public-v1
      paths-to-match:
        - /api/v1/public/**
    - group: internal-v1
      paths-to-match:
        - /api/v1/internal/**
~~~

This configuration is equivalent in purpose to creating simple GroupedOpenApi beans. Pick one consistent management approach to avoid declaring duplicate groups in both YAML and Java config.

Other filtering properties may vary by springdoc version, such as scanned packages, excluded paths, or header/media type conditions. When using advanced properties, check the reference for your installed version and verify the /v3/api-docs/{group} output.

## 4. Document URLs for Each Group

springdoc typically serves the default document at:

~~~text
/v3/api-docs
~~~

For a group named public-v1, its document is typically accessed at:

~~~text
/v3/api-docs/public-v1
~~~

For group internal-v1:

~~~text
/v3/api-docs/internal-v1
~~~

Swagger UI can list documents for users to select:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API v1
        url: /v3/api-docs/public-v1
      - name: Internal API v1
        url: /v3/api-docs/internal-v1
~~~

Display names in Swagger UI can be more user-friendly than group names. Group names should stay short, stable, and suitable as URL segments.

Showing a group in the Swagger UI dropdown only helps pick a document. It does not create authorization. If internal docs must not be public, secure the documentation endpoints and Swagger UI through application or infrastructure security settings.

## 5. @Tag Categorizes Operations Inside a Document

@Tag defines a functional category to group related operations. This annotation is commonly placed at the controller level:

~~~java
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/products")
@Tag(
    name = "Catalog",
    description = "Query and manage product information."
)
public class ProductController {
    // Product endpoints.
}
~~~

In the OpenAPI document, the Catalog tag causes Swagger UI to display the controller's operations under one functional heading.

You can attach specific tags to an operation using the tags attribute of @Operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/featured")
@Operation(
    summary = "Get featured products",
    tags = {"Catalog"}
)
public List<ProductResponse> featured() {
    return productService.findFeatured();
}
~~~

If multiple tags are specified, the operation can appear under multiple tag sections within the same document. Tags do not alter URLs, HTTP methods, access permissions, or how Spring invokes controllers.

### 5.1. Declaring Tags at the Document Level

You can define tag descriptions at the OpenAPI level:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;

@OpenAPIDefinition(
    info = @Info(
        title = "Store API",
        version = "1.0.0"
    ),
    tags = {
        @Tag(
            name = "Catalog",
            description = "Operations related to products."
        ),
        @Tag(
            name = "Orders",
            description = "Operations related to orders."
        )
    }
)
public class OpenApiDefinition {
}
~~~

Defining tags at the document level helps maintain consistent tag names and descriptions. Declared tags can appear in the OpenAPI tag list without having to infer descriptions from individual controllers.

## 6. Combining Groups and Tags

A single group document can contain multiple tags. For example:

~~~text
Swagger UI
└── Public API v1 (document group)
    ├── Catalog (tag)
    │   ├── GET /api/v1/public/products
    │   └── GET /api/v1/public/products/{id}
    ├── Orders (tag)
    │   ├── POST /api/v1/public/orders
    │   └── GET /api/v1/public/orders/{id}
    └── Customers (tag)
        └── GET /api/v1/public/customers/me
~~~

The group determines which set of operations enters the Public API v1 document. Tags organize the operations already inside that document by business function.

An operation can belong to the same tag across multiple groups if it is included in multiple documents. For example, a product lookup endpoint can appear in both public and partner documents while carrying the Catalog tag in both.

Avoid creating a tag named Public API v1 merely to simulate a document group. Doing so only changes a grouping label inside Swagger UI; every operation still remains in the same OpenAPI document.

## 7. API Version Is the Version of the Contract

An API version represents a contract version that clients integrate against. A new version typically arises when introducing breaking changes such as:

- Renaming or removing a response field clients rely on.
- Changing a field's data type.
- Changing URLs or HTTP methods.
- Altering the business semantics of an operation.
- Changing validation rules or data formats in a way that breaks existing clients.

Not every change requires bumping the major version. Adding optional fields or new operations is often backward-compatible if clients are designed to ignore unknown fields. Specific rules should be defined in your API versioning policy.

Groups do not create API versions on their own. Naming a group v2 while still pointing at v1 operations does not make those endpoints v2. Conversely, /api/v2/products remains API v2 even if placed inside a group named public.

## 8. Distinguishing openapi Version and info.version

An OpenAPI document has two version fields that are easily confused:

| Field | Example | Meaning |
|---|---|---|
| openapi | 3.1.0 | OpenAPI Specification version used to write the document |
| info.version | 2.0.0 | Version of the API described by the document |

For example:

~~~yaml
openapi: 3.1.0
info:
  title: Store API
  version: 2.0.0
~~~

openapi: 3.1.0 does not mean the API itself is at version 3.1.0. It states that the document conforms to OpenAPI specification 3.1. info.version: 2.0.0 is the API version published by this document.

With springdoc, shared metadata can be declared via @OpenAPIDefinition or an OpenAPI bean. When multiple API versions are split into separate groups, ensure each document sets info.version to match the API it describes.

## 9. Versioning by URL Path

A straightforward strategy that is easy to group in documentation is placing the version in the URL:

~~~text
/api/v1/products
/api/v2/products
~~~

Controllers can be separated by version:

~~~java
@RestController
@RequestMapping("/api/v1/products")
public class ProductV1Controller {

    @GetMapping("/{id}")
    public ProductV1Response getById(@PathVariable Long id) {
        return productService.findV1Response(id);
    }
}
~~~

~~~java
@RestController
@RequestMapping("/api/v2/products")
public class ProductV2Controller {

    @GetMapping("/{id}")
    public ProductV2Response getById(@PathVariable Long id) {
        return productService.findV2Response(id);
    }
}
~~~

Then create one group per version:

~~~java
@Bean
GroupedOpenApi apiV1() {
    return GroupedOpenApi.builder()
        .group("public-v1")
        .pathsToMatch("/api/v1/**")
        .build();
}

@Bean
GroupedOpenApi apiV2() {
    return GroupedOpenApi.builder()
        .group("public-v2")
        .pathsToMatch("/api/v2/**")
        .build();
}
~~~

The advantage of path versioning is that URLs express the version explicitly, simplifying routing, caching, and document filtering. The trade-off is that the version becomes part of the URL and multiple routes may need maintenance during transition periods.

## 10. Configuring Per-Group info.version

When multiple groups represent different API versions, assign separate metadata so documents do not all display the same version. You can attach an OpenApiCustomizer to each group:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class VersionedOpenApiConfiguration {

    @Bean
    GroupedOpenApi publicV1() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/v1/**")
            .addOpenApiCustomizer(openApi -> openApi.info(
                new Info()
                    .title("Store Public API")
                    .version("1.0.0")
                    .description("Public API contract version 1.")
            ))
            .build();
    }

    @Bean
    GroupedOpenApi publicV2() {
        return GroupedOpenApi.builder()
            .group("public-v2")
            .pathsToMatch("/api/v2/**")
            .addOpenApiCustomizer(openApi -> openApi.info(
                new Info()
                    .title("Store Public API")
                    .version("2.0.0")
                    .description("Public API contract version 2.")
            ))
            .build();
    }
}
~~~

The customizers in this example are attached to each GroupedOpenApi, setting info metadata for the respective document. Verify /v3/api-docs/public-v1 and /v3/api-docs/public-v2 to ensure titles and info.version are not overwritten by other configuration.

If you use a shared @OpenAPIDefinition or OpenAPI bean, treat it as default metadata and apply per-group customizers whenever documents have distinct versions.

## 11. Versioning by Header or Media Type

Not all APIs put the version in the URL. Some systems select versions via headers:

~~~http
GET /api/products/42
X-API-Version: 2
~~~

Or via media types:

~~~http
GET /api/products/42
Accept: application/vnd.example.product-v2+json
~~~

These approaches keep URLs stable, though clients must send the proper header or media type. They also complicate testing, caching, and gateway rules unless the system follows strict conventions.

When versions share the same path and HTTP method, filtering by pathsToMatch alone cannot distinguish operations. You must separate controllers/packages or use header/media type filters and customizers supported by your springdoc version. Springdoc provides additional filters such as headersToMatch or producesToMatch in supported versions; verify syntax and actual output before relying on them.

Example Spring MVC mappings differentiating by header:

~~~java
@GetMapping(
    path = "/api/products/{id}",
    headers = "X-API-Version=1"
)
public ProductV1Response getV1(@PathVariable Long id) {
    return productService.findV1Response(id);
}

@GetMapping(
    path = "/api/products/{id}",
    headers = "X-API-Version=2"
)
public ProductV2Response getV2(@PathVariable Long id) {
    return productService.findV2Response(id);
}
~~~

This is an example of runtime routing. To generate two separate documents, ensure OpenAPI filters correctly distinguish the two mappings and each group contains only operations for its version. Do not assume pathsToMatch can tell them apart since the URL is identical.

## 12. Versioning by Package and Module Boundaries

If v1 and v2 controllers reside in separate packages, you can group by package:

~~~java
@Bean
GroupedOpenApi versionOne() {
    return GroupedOpenApi.builder()
        .group("v1")
        .packagesToScan("com.example.api.v1")
        .build();
}

@Bean
GroupedOpenApi versionTwo() {
    return GroupedOpenApi.builder()
        .group("v2")
        .packagesToScan("com.example.api.v2")
        .build();
}
~~~

This works well when source code already separates controllers by version. However, package filtering is a documentation generation rule, not a compatibility or routing guarantee. Runtime mappings must still be declared explicitly on controllers.

## 13. When Should Groups Not Equal Versions?

Groups can represent target audiences or product scopes while version remains an independent dimension. For example:

| Document | Scope | API Version |
|---|---|---|
| public-v1 | API for customer applications | 1.0.0 |
| public-v2 | API for customer applications | 2.0.0 |
| partner-v1 | API for partners | 1.0.0 |
| internal-v1 | API used internally | 1.0.0 |

One API version can appear across multiple groups when different user groups need different subsets of operations. Conversely, a single group can span multiple functional modules while sharing one contract version.

For example, group partner-v1 can include operations from both Catalog and Orders. Inside that document, tags can still be Catalog and Orders. Splitting public/partner is a document scope decision; version still describes the API contract.

If the number of group dimensions grows too fast—such as creating a separate document for every combination of audience, version, and module—Swagger UI becomes hard to navigate. Only create groups for genuine reading or distribution needs.

## 14. Marking Deprecated Operations

When an operation or field is scheduled for removal, mark it deprecated in OpenAPI:

~~~java
@GetMapping("/legacy-search")
@Operation(
    summary = "Search products using the legacy method",
    deprecated = true,
    description = "Use GET /api/v2/products/search for new integrations."
)
public List<ProductResponse> legacySearch() {
    return productService.legacySearch();
}
~~~

For a schema field:

~~~java
public record ProductV1Response(
    Long id,

    @Schema(
        description = "Legacy name; will be replaced in a future version.",
        deprecated = true
    )
    String legacyName
) {
}
~~~

deprecated = true informs documentation readers and client tooling. It does not block requests, remove endpoints, or automatically migrate clients to a newer version. Retirement requires separate timelines, notices, and runtime controls.

## 15. OpenAPI Example Showing Group, Tag, and Version

A condensed public-v2 group document might look like this:

~~~yaml
openapi: 3.1.0
info:
  title: Store Public API
  version: 2.0.0
  description: Public API contract version 2.
tags:
  - name: Catalog
    description: Query and manage products.
  - name: Orders
    description: Create and query orders.
paths:
  /api/v2/products:
    get:
      tags:
        - Catalog
      summary: List products
      responses:
        '200':
          description: List of products.
  /api/v2/orders:
    post:
      tags:
        - Orders
      summary: Create order
      responses:
        '201':
          description: Order created.
~~~

In this example:

- openapi is the OpenAPI specification version.
- info.version is the API version being described.
- tags defines functional categories.
- paths lists the operations included in the group document.
- The group name public-v2 is used in configuration and document URLs, not as a dedicated standard field inside the OpenAPI document.

## 16. Common Mistakes When Organizing Documentation

| Mistake | Consequence | Fix |
|---|---|---|
| Using tags instead of document groups | Swagger UI only categorizes operations; document still contains every endpoint | Create GroupedOpenApi or group-configs |
| Naming a group v2 while endpoints remain v1 | Readers misunderstand the contract version | Align group filters, routes, and info.version |
| Assuming groups create runtime routes | Clients call new URLs but server has no matching mapping | Declare routes/versioning explicitly in Spring MVC |
| Assuming groups act as authorization | Internal docs or endpoints remain accessible | Secure /v3/api-docs/{group} and Swagger UI with security rules |
| Filtering only by path when version is in a header | Multiple mappings on the same path land in the wrong group | Filter by mapping/header/media type or split packages |
| Using info.version for the OpenAPI spec version | Misstating document spec version vs API version | Distinguish openapi from info.version |
| Every controller invents different tag names | Swagger UI gets cluttered with duplicate-meaning sections | Standardize a tag dictionary and descriptions |
| Marking deprecated and deleting endpoint immediately | Clients without time to migrate break | Maintain transition windows and a deprecation policy |
| Creating too many groups | Users struggle to pick the right document | Create groups only for clear distribution/reading needs |

## 17. Workflow for Designing Multi-Group, Versioned Documentation

When organizing documentation for a large application, follow this sequence:

1. Identify supported API versions and compatibility boundaries between them.
2. Choose a runtime versioning strategy: path, header, media type, or an agreed routing scheme.
3. Identify readers and operation scopes to publish: public, partner, internal, or per-product.
4. Create groups via GroupedOpenApi or springdoc.group-configs using matching criteria.
5. Assign business tags to categorize operations inside each group.
6. Set per-document info.title and info.version where needed.
7. Configure Swagger UI so readers can pick the right document.
8. Protect documentation endpoints according to access policies.
9. Verify /v3/api-docs/{group} and test the corresponding runtime endpoints.
10. Mark older operations deprecated and enforce retirement dates per versioning policy.

## 18. Verifying Generated Documentation

After running the application, check the URLs:

~~~bash
curl -s http://localhost:8080/v3/api-docs/public-v1
curl -s http://localhost:8080/v3/api-docs/public-v2
~~~

For each document, confirm:

- The group contains only expected paths and operations.
- No intended endpoints are missing and no out-of-scope endpoints leaked in.
- Tags have accurate names, descriptions, and business categorization.
- info.version matches the API version.
- The openapi field matches the configured specification version.
- Deprecated operations are marked accurately.
- Schemas and responses align with runtime endpoints.
- Swagger UI lists the documents with clear, recognizable names.

When using header or media type versioning, call the same URL with each corresponding header/Accept value and verify each group's document describes only the right mapping. This step is vital when two operations share the same path and HTTP method.

## 19. Takeaways

- Document groups generate an OpenAPI document from a filtered set of operations.
- GroupedOpenApi and springdoc.group-configs are the two standard ways to declare groups.
- @Tag and @Operation(tags = ...) categorize operations inside a document.
- Groups do not create endpoints, change runtime behavior, or grant access permissions.
- API version is a contract version; it must stay consistent with actual routing strategy.
- openapi is the specification version; info.version is the described API version.
- Path versioning is easy to filter into groups; header/media type versioning needs matching filters because multiple mappings share a URL.
- One version can appear across multiple groups; one group can contain multiple tags.
- deprecated only marks documentation and does not disable endpoints.
- Always verify each /v3/api-docs/{group}, Swagger UI, and runtime behavior.

When designing springdoc-openapi documentation, use groups to partition documents by reader scope or product, use tags to categorize operations by business domain, and manage API versions as part of the integration contract. These three layers are organized separately yet must align across configuration, URLs, OpenAPI metadata, and Spring MVC behavior.
