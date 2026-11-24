# Sorting Tags, Operations, and Default Expansion Depth

Swagger UI organizes operations into tag groups and lets users expand each group to view request, response, and schema details. For APIs with many endpoints, tag order, operation order, and initial expansion state directly affect how easily information can be found. Springdoc-openapi provides configuration properties to sort tags/operations and control document expansion depth. These can be combined with the tag order declared in OpenAPI to create a consistent interface.

## 1. Three UI decisions to distinguish

When configuring Swagger UI, distinguish three concerns:

1. **Tag order:** the order in which groups such as Products, Orders, and Accounts appear.
2. **Operation order:** within a tag, how GET, POST, PUT, and DELETE endpoints are ordered.
3. **Initial expansion depth:** whether Swagger UI opens all operations by default, opens only group names, or collapses everything.

These are display options. They do not alter Spring MVC routing, access permissions, request execution order, or OpenAPI schema content.

| Goal | Swagger UI property | Common value |
|---|---|---|
| Sort tags by name | `tagsSorter` | `alpha` |
| Sort operations by path | `operationsSorter` | `alpha` |
| Sort operations by HTTP method | `operationsSorter` | `method` |
| Collapse all operations on page load | `docExpansion` | `none` |
| Expand tags while collapsing operations | `docExpansion` | `list` |
| Expand all tags and operations | `docExpansion` | `full` |
| Hide the Models section | `defaultModelsExpandDepth` | `-1` |
| Control schema depth in Models | `defaultModelExpandDepth` | `1` or an appropriate value |

Do not confuse `docExpansion` with `defaultModelsExpandDepth`: the former controls the operations list section, while the latter controls the Models section at the bottom of Swagger UI.

## 2. Tags are display groups for operations

In OpenAPI, an operation can carry one or more tags. Swagger UI uses tags to group operations into collapsible sections.

Example:

```yaml
paths:
  /api/products:
    get:
      tags:
        - Products
      summary: Search products
      responses:
        '200':
          description: Product list
    post:
      tags:
        - Products
      summary: Create product
      responses:
        '201':
          description: Product created
  /api/orders:
    get:
      tags:
        - Orders
      summary: Search orders
      responses:
        '200':
          description: Order list
```

Swagger UI will show a `Products` group containing two operations and an `Orders` group containing one operation. Tag names on operations must match tag names defined at the document level if you want to provide shared descriptions and metadata.

### Attaching tags with annotations

You can attach `@Tag` at the controller level so operations inside the controller share the same group:

```java
import io.swagger.v3.oas.annotations.tags.Tag;

@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Manage and look up products")
class ProductController {

    @GetMapping
    List<ProductResponse> search() {
        return productService.search();
    }

    @PostMapping
    ProductResponse create(@RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
```

If a controller has operations belonging to different groups, tags can be attached per operation:

```java
@Operation(tags = {"Products", "Catalog"})
@GetMapping("/{id}")
ProductResponse getById(@PathVariable UUID id) {
    return productService.getById(id);
}
```

An operation with multiple tags can appear under multiple groups in Swagger UI. Only do this when users genuinely need to locate the operation from multiple perspectives; excessive tagging duplicates entries and makes navigation harder.

## 3. Declaring tag order in OpenAPI

OpenAPI allows declaring a list of tags at the root document level. The element order in this list can represent the display order of operation groups. If you want a manual order, declare tags in the desired order and leave automatic `tagsSorter` disabled.

YAML example:

```yaml
openapi: 3.1.0
info:
  title: Store API
  version: 1.0.0
tags:
  - name: Products
    description: Create, update, and search products
  - name: Orders
    description: Manage orders and processing status
  - name: Accounts
    description: User accounts and profile details
paths:
  /api/products:
    get:
      tags: [Products]
      summary: Find products
      responses:
        '200':
          description: OK
  /api/orders:
    get:
      tags: [Orders]
      summary: Find orders
      responses:
        '200':
          description: OK
```

When Swagger UI does not apply `tagsSorter`, the tag declaration order in the OpenAPI document serves as the basis for displaying groups. If `tagsSorter: alpha` is set, the manual order can be overridden by alphabetical order.

### Declaring tag order with @OpenAPIDefinition

In Spring Boot, tag metadata can be declared in the OpenAPI configuration:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Store API", version = "1.0.0"),
    tags = {
        @Tag(name = "Products", description = "Product management"),
        @Tag(name = "Orders", description = "Order management"),
        @Tag(name = "Accounts", description = "Account management")
    }
)
class OpenApiConfiguration {}
```

The `tags` list is declared in the order Products, Orders, Accounts. Controllers/operations must use the matching tag names. After running the application, inspect the `tags` array in `/v3/api-docs` to verify the generated document order.

If you need business-logic ordering instead of alphabetical ordering, avoid enabling `tagsSorter: alpha`. When a sorter is enabled, Swagger UI sorts according to the sorter even if the tag list in OpenAPI is declared in another order.

## 4. Sorting tags with tagsSorter

`tagsSorter` is a Swagger UI option for sorting tag groups. Common values:

| Value | Behavior |
|---|---|
| Unset | Uses tag order in the OpenAPI document / Swagger UI default logic |
| `alpha` | Sorts tags alphabetically by name |

springdoc configuration in `application.yml`:

```yaml
springdoc:
  swagger-ui:
    tags-sorter: alpha
```

With this setting, the Accounts group can appear before Orders and Products alphabetically. If you want an order following a business flow such as Authentication → Products → Orders → Reports, declare the tag order at the OpenAPI level and leave `tags-sorter` unconfigured.

Do not rely on arbitrary controller scanning order or Java file order. Explicitly declare root tags whenever an intentional order is required.

## 5. Sorting operations with operationsSorter

`operationsSorter` controls operation order within a tag. Swagger UI provides two commonly used string options:

| Value | Behavior |
|---|---|
| Unset | Uses default order from OpenAPI document / Swagger UI |
| `alpha` | Sorts operations by path |
| `method` | Sorts by HTTP method |

Sorting by path:

```yaml
springdoc:
  swagger-ui:
    operations-sorter: alpha
```

Operations are then typically ordered by path, helping readers locate endpoints by URL. If an API has many CRUD endpoints and you want them grouped by HTTP method, you can use:

```yaml
springdoc:
  swagger-ui:
    operations-sorter: method
```

`method` sorts by HTTP verb according to Swagger UI's rules. Do not assume it enforces a custom business order like GET → POST → PATCH → DELETE across all versions; if a custom order is required, use Swagger UI's custom sorter capability and verify the specific integration setup.

### Example of multiple operations under one tag

```yaml
paths:
  /api/products:
    get:
      tags: [Products]
      summary: Search products
    post:
      tags: [Products]
      summary: Create product
  /api/products/{id}:
    get:
      tags: [Products]
      summary: View product details
    patch:
      tags: [Products]
      summary: Update product
    delete:
      tags: [Products]
      summary: Delete product
```

With `operationsSorter: alpha`, operations are sorted by path; with `method`, the order is determined by HTTP method. Sorter settings only change presentation in Swagger UI; they do not change route precedence or how Spring handles requests.

## 6. Controlling expansion depth with docExpansion

`docExpansion` determines how far Swagger UI expands tags and operations when users load the page.

| Value | Initial state | Best suited when |
|---|---|---|
| `none` | Collapses operation groups | Large documentation where users selectively open needed groups |
| `list` | Expands tag groups, collapses operations inside | You want users to see the list of groups right away |
| `full` | Expands tag groups and operation details | Small APIs or documentation meant to be viewed completely at once |

Example:

```yaml
springdoc:
  swagger-ui:
    doc-expansion: none
```

With `none`, Swagger UI loads more cleanly visually for docs with many operations; users open each tag to find endpoints. With `list`, tag names appear alongside a collapsible list of operations. With `full`, operations are expanded, making the page noticeably longer.

Swagger UI's common default is `list`. Declare it explicitly if you want the UI to preserve consistent behavior across environments or Swagger UI upgrades. `docExpansion` does not alter schema contents and does not control the Models section.

## 7. Distinguishing operation expansion from Models expansion

Swagger UI has a dedicated section for displaying schemas from `components.schemas`, typically near the bottom of the page labeled Models. Related options include:

| Property | Meaning |
|---|---|
| `defaultModelsExpandDepth` | Expansion depth of the Models section; `-1` hides this section |
| `defaultModelExpandDepth` | Expansion depth of each individual model/schema |
| `defaultModelRendering` | Selects whether `example` or `model` is shown initially |

Example hiding the Models section completely:

```yaml
springdoc:
  swagger-ui:
    default-models-expand-depth: -1
```

Example keeping Models visible while expanding only one level:

```yaml
springdoc:
  swagger-ui:
    default-models-expand-depth: 1
    default-model-expand-depth: 1
    default-model-rendering: example
```

These options are useful when the specification has deeply nested schemas. If Models is hidden, users can still inspect schemas through each operation's request/response sections; hiding the bottom section does not remove `components.schemas` from the OpenAPI document.

## 8. Combined configuration for an API with many endpoints

A practical configuration can combine alphabetical tags, operations by HTTP method, and initially collapsed operations:

```yaml
springdoc:
  swagger-ui:
    path: /swagger-ui.html
    tags-sorter: alpha
    operations-sorter: method
    doc-expansion: none
    default-models-expand-depth: -1
```

Meaning:

- Swagger UI is accessed via `/swagger-ui.html` per the application path config.
- Tags are sorted by name.
- Operations inside each tag are sorted by HTTP method.
- All operation groups start collapsed on page load.
- The Models section at the bottom of the page is hidden.

If prioritizing a business order declared in `@OpenAPIDefinition`, omit `tags-sorter: alpha`:

```yaml
springdoc:
  swagger-ui:
    operations-sorter: alpha
    doc-expansion: list
    default-models-expand-depth: 1
```

In this second setup, tags preserve the OpenAPI document order, operations are sorted by path, tags expand while operations remain collapsed, and the Models section remains visible.

YAML keys use kebab-case following Spring Boot configuration conventions. Property names in Swagger UI / Java configuration are commonly written in camelCase such as `tagsSorter`, `operationsSorter`, `docExpansion`, `defaultModelsExpandDepth`, and `defaultModelExpandDepth`.

## 9. Distinguishing global configuration from individual document groups

Springdoc can generate multiple OpenAPI documents via `GroupedOpenApi`, such as public, admin, and internal. Each document can contain a distinct set of tags/operations. Swagger UI displays the document selected via configuration or the group dropdown.

When organizing multiple groups:

- A tag only appears in documents containing operations with that tag.
- The root tag list and tag order may differ between groups.
- Component schemas and `$ref` entries belong to their respective document.
- Swagger UI options like sorters and doc expansion typically apply to the shared UI, rather than automatically creating separate business policies per group.
- If different tag orders are needed per group, produce each OpenAPI document with the appropriate tag list and test Swagger UI when switching groups.

Example group declarations:

```java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .build();
}
```

Each group has its own document endpoint, for example `/v3/api-docs/public` and `/v3/api-docs/admin`. Confirm actual paths based on `springdoc.api-docs.path` and group names. Creating groups does not automatically create two standalone Swagger UI pages; one interface can allow selecting between group documents.

## 10. Things to keep in mind about sorter configuration

`tagsSorter` and `operationsSorter` are presentation-side options in Swagger UI. Key points to remember:

- `alpha` for tags sorts by tag name.
- `alpha` for operations sorts by path.
- `method` for operations sorts by HTTP method.
- Leave sorters unset if you want to preserve OpenAPI document order or default ordering.
- A custom sorter as a JavaScript function is a Swagger UI capability; you cannot write an arbitrary function as a YAML string like `alpha` or `method`. Passing a function depends on how Swagger UI is integrated and the application's custom UI setup.
- Sorters do not alter `tags` or `paths` in the downloaded OpenAPI document; they only sort visual presentation.

If you need manual operation ordering by business priority, do not rename paths to force alphabetical sorting. Consider a Swagger UI custom sorter or split documents into groups when operation sets have clear boundaries.

## 11. Verifying configuration in Swagger UI

After updating `application.yml`, restart the application and open Swagger UI. Check in order:

1. Tags appear in the expected order.
2. Operations within each tag are sorted by path or method as configured.
3. Initial state of tags/operations matches `docExpansion`.
4. The Models section is shown or hidden according to `defaultModelsExpandDepth`.
5. If multiple groups exist, switch groups and confirm tags/operations belong to the right document.
6. Expand an operation and check that request, response, and schemas still render completely.

You can open `/v3/api-docs` to inspect the declared tag order:

```json
{
  "tags": [
    {"name": "Products", "description": "Product management"},
    {"name": "Orders", "description": "Order management"},
    {"name": "Accounts", "description": "Account management"}
  ]
}
```

If `tagsSorter` is `alpha`, Swagger UI may display alphabetically even though the `tags` array remains in Products, Orders, Accounts order. This is the difference between the OpenAPI document and UI presentation.

## 12. Common errors and how to handle them

| Symptom | Possible cause | Resolution |
|---|---|---|
| Tags do not follow declared order | `tagsSorter: alpha` overrides document order | Remove the sorter if manual ordering is desired |
| Tag does not appear despite declared metadata | Operations do not carry the exact tag name or group lacks those operations | Check `tags` on operations and the group's document |
| An operation appears in multiple groups | Operation is annotated with multiple tags | Keep only the necessary tags |
| Operations are not sorted by path | `operationsSorter` is set to `method` or not applied | Set `operations-sorter: alpha` and reload UI |
| Operations are not sorted by HTTP method | `operationsSorter` is set to `alpha` | Set `operations-sorter: method` |
| All operations expand despite wanting them collapsed | `docExpansion` is `full` or config was not bound | Set `doc-expansion: none` and inspect runtime config |
| Tags expand while operations remain collapsed | `docExpansion: list` | This is expected behavior; use `none` or `full` if needed |
| Models section still appears | `defaultModelsExpandDepth` is not set to `-1` | Set `default-models-expand-depth: -1` |
| Schemas are too long in Models | Model expand depth is too deep | Reduce `default-model-expand-depth` or hide Models |
| Changes in application.yml have no effect | Wrong key, active profile mismatch, or browser cache | Check active profile, relaxed binding keys, and hard refresh |
| A group is missing tags/operations | PathsToMatch or packagesToScan excludes endpoints from the group | Inspect that group's dedicated OpenAPI document |

## 13. Workflow for choosing the right configuration

When organizing Swagger UI, follow this sequence:

1. Identify the business groups clients need to see.
2. Choose short, stable tag names and apply them consistently across controllers/operations.
3. Declare root-level tag metadata with `@OpenAPIDefinition` if descriptions and manual ordering are needed.
4. Choose `tagsSorter: alpha` when there are many tags and users typically search by name; omit the sorter when business order is needed.
5. Choose `operationsSorter: alpha` to browse by path or `method` to group by HTTP verb.
6. Choose `docExpansion: none`, `list`, or `full` based on document size and how users explore endpoints.
7. Decide whether the Models section should be shown; use `defaultModelsExpandDepth: -1` to hide it.
8. Check each group and reload Swagger UI after changing settings.
9. Confirm `/v3/api-docs` still contains all tags, operations, and schemas; sorters do not alter the underlying document.

A well-tuned configuration helps users locate the right operation quickly without altering the API contract. Use tags for business grouping, sorters for clear ordering criteria, and doc expansion to control how much content appears when the page loads.

## 14. References

- [Swagger UI Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): `tagsSorter`, `operationsSorter`, `docExpansion`, and model expansion options.
- [OpenAPI Specification – Tag Object](https://spec.openapis.org/oas/latest.html#tag-object): declaring tags and metadata at the document level.
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): attaching tags to operations.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): `@OpenAPIDefinition`, `@Tag`, and `@Operation`.
- [Springdoc OpenAPI](https://springdoc.org/): configuring Swagger UI and generating OpenAPI documents from Spring Boot.
