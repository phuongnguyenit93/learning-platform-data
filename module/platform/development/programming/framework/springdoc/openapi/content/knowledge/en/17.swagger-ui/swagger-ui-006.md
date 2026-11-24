# Search, Filtering, and Schema Model Display

Swagger UI helps integrators locate operations, read requests/responses, and inspect data structures described by OpenAPI. When an API has many tags, operations, or shared schemas, organizing filters and model expansion behavior directly affects documentation discoverability.

Springdoc provides Swagger UI configuration via `springdoc.swagger-ui.*` properties. You can enable tag filtering, sort operation groups, choose how endpoint lists expand, and control how schemas/examples are displayed. These settings only alter the documentation UI; actual schemas are still generated from controllers, DTOs, OpenAPI annotations, and Springdoc metadata.

## 1. Built-in filter in Swagger UI

Swagger UI has a `filter` option to enable a filter input box at the top of the UI. Readers enter a tag name to narrow down the list of operation groups. Filtering is case-sensitive.

In `application.yml`:

```yaml
springdoc:
  swagger-ui:
    filter: true
```

Or in `application.properties`:

```properties
springdoc.swagger-ui.filter=true
```

When enabled, Swagger UI displays a tag filter box. For example, if an API has tags `Books`, `Orders`, and `Payments`, typing `Books` lets readers focus on the group matching that tag.

You can provide a default filter string instead of a boolean:

```yaml
springdoc:
  swagger-ui:
    filter: Books
```

This string serves as the initial filter value. If you only want to show the input box and let users search freely, use `true`.

Note that the built-in filter focuses on tags and operation groups. It is not a full-text search across every OpenAPI field such as summaries, descriptions, schema properties, or examples. To quickly find a term on the currently open page, readers can use the browser's find feature; if the product needs dedicated full-text search, a custom interface or plugin is required.

## 2. Good tags make operation filtering effective

Filtering is only helpful when operations are tagged clearly and consistently. Tags can be attached at the controller level using `@Tag`:

```java
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
@Tag(name = "Books", description = "Look up and manage books")
public class BookController {
    // Books API operations.
}
```

Or attached to an individual operation using `@Operation`:

```java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/reports/sales")
@Operation(
    summary = "Sales report",
    tags = {"Reports", "Sales"}
)
public String getSalesReport() {
    return "sales report";
}
```

In large projects, use stable, clear tag names following a shared convention. Avoid variants such as `Book`, `Books`, and `book-api` if they refer to the same functional area; differing names create separate groups and make filtering harder to use.

Tag descriptions can be declared centrally in `@OpenAPIDefinition`:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.tags.Tag;

@OpenAPIDefinition(
    tags = {
        @Tag(name = "Books", description = "Look up and manage books"),
        @Tag(name = "Orders", description = "Order management"),
        @Tag(name = "Payments", description = "Create and look up payments")
    }
)
```

Tags describe how operations are grouped in documentation. They do not change URLs, controller mappings, or API access permissions.

## 3. Sorting tags and operations for easier lookup

As the number of tags and operations grows, they can be sorted alphabetically or by HTTP method. Swagger UI supports `tagsSorter` and `operationsSorter`.

Example configuration:

```yaml
springdoc:
  swagger-ui:
    filter: true
    tags-sorter: alpha
    operations-sorter: alpha
```

Common values:

| Property | Value | Result |
| --- | --- | --- |
| `tags-sorter` | `alpha` | Sort tags alphabetically |
| `operations-sorter` | `alpha` | Sort operations alphabetically |
| `operations-sorter` | `method` | Sort operations by HTTP method |

If you want to keep the order decided by the specification or a plugin, no sorter configuration is needed. When customizing sorters with a JavaScript function, verify how configuration is passed for your Swagger UI/Springdoc version; string values are the simple option for `application.yml`.

## 4. Controlling how the operation list expands

The `doc-expansion` property determines how far operation groups are expanded on page load:

```yaml
springdoc:
  swagger-ui:
    doc-expansion: none
```

Common values:

| Value | Display behavior |
| --- | --- |
| `list` | Expand the tag list while keeping operation details collapsed |
| `full` | Expand tags and operations |
| `none` | Collapse operation groups initially |

For APIs with many endpoints, `none` keeps the page compact so readers expand only the groups they need. For small APIs or demo pages, `list` helps readers see available endpoints immediately.

`doc-expansion` controls the expansion state of the operation list. It does not determine how deeply underlying schema models expand; separate model/schema options govern that part.

## 5. Displaying model instead of example

For request bodies, Swagger UI can display either a sample payload or the model structure. The `default-model-rendering` property controls the default display mode:

```yaml
springdoc:
  swagger-ui:
    default-model-rendering: model
```

Two primary values:

- `example`: prioritize showing sample data.
- `model`: prioritize showing schema/model structure.

DTO example:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Schema(description = "Details of the book to create")
public record CreateBookRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(description = "Book title", example = "Spring Boot Fundamentals")
    String title,

    @Schema(description = "Publication year", example = "2025")
    Integer publicationYear
) {}
```

When displaying the model, readers focus on properties, data types, descriptions, and constraints. When displaying the example, they see a concrete payload ready to use as a starting point for a request. The two modes serve different purposes; readers can still switch modes in the UI if the Swagger UI version provides that control.

`default-model-rendering` is a presentation option. It does not generate examples and does not change the OpenAPI schema. To provide sample payloads, declare `@Schema(example = ...)`, `@ExampleObject`, or corresponding metadata.

## 6. Controlling schema expansion depth

Swagger UI has two options commonly used to control depth in the model section:

- `default-models-expand-depth`: expansion depth of the model/schema list.
- `default-model-expand-depth`: expansion depth inside a single model.

Example:

```yaml
springdoc:
  swagger-ui:
    default-models-expand-depth: 1
    default-model-expand-depth: 2
```

`default-models-expand-depth: -1` can be used to hide the model/schema list section in the UI completely. A value of `1` usually keeps the model section at a basic expansion level. `default-model-expand-depth` controls how deeply nested properties appear when opening a model.

Nested schema example:

```java
import java.util.List;

public record OrderResponse(
    Long id,
    CustomerSummary customer,
    List<OrderItemResponse> items
) {}

public record CustomerSummary(
    Long id,
    String displayName,
    AddressResponse address
) {}

public record AddressResponse(
    String city,
    String country
) {}

public record OrderItemResponse(
    Long productId,
    Integer quantity
) {}
```

If models have many nested levels, expanding everything deeply can make the page long and hard to read. Setting a moderate depth lets users inspect the main structure first, then expand nested objects as needed.

These values control the Swagger UI presentation. They do not change the number of schema levels in OpenAPI, strip properties, or modify Jackson serialization.

## 7. Displaying schema extensions and constraints

Swagger UI provides options to display extensions and certain schema attributes:

```yaml
springdoc:
  swagger-ui:
    show-extensions: true
    show-common-extensions: true
```

- `show-extensions` enables displaying specification extensions, such as `x-audience` or `x-internal`.
- `show-common-extensions` enables displaying common extensions recognized by Swagger UI, such as extra schema attributes depending on the version.

OpenAPI constraints such as `minLength`, `maxLength`, `minimum`, `maximum`, `minItems`, `maxItems`, `pattern`, `enum`, `format`, and `required` come from the schema. Swagger UI renders them so readers understand data limits. The data source remains the OpenAPI specification generated by Springdoc.

Example:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import io.swagger.v3.oas.annotations.media.Schema;

public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 80)
    @Schema(example = "Mechanical Keyboard")
    String name,

    @Min(1)
    @Max(100)
    Integer quantity
) {}
```

The schema can include `minLength`, `maxLength`, `minimum`, and `maximum` if Springdoc detects the corresponding constraints. If the UI does not display constraints as expected, check `/v3/api-docs` first to determine whether the metadata was generated.

## 8. Combined Swagger UI configuration

A balanced configuration for an API with many tags and schemas might look like this:

```yaml
springdoc:
  swagger-ui:
    path: /swagger-ui.html
    filter: true
    tags-sorter: alpha
    operations-sorter: alpha
    doc-expansion: none
    default-model-rendering: model
    default-models-expand-depth: 1
    default-model-expand-depth: 2
    show-extensions: true
    show-common-extensions: true
```

Meaning of this configuration:

1. Enable the tag filter box to find API groups.
2. Sort tags and operations alphabetically.
3. Collapse operations on page load to reduce initial page height.
4. Prioritize viewing the schema model when reading request bodies.
5. Expand models to a moderate depth.
6. Display extensions and extended constraints if present in the specification.

Not every API needs all options enabled. For small APIs, default settings may already be sufficient. Test against real documentation and choose settings that help integrators find endpoints, understand schemas, and send requests smoothly.

## 9. Verifying tags, filters, and schemas in Swagger UI

After the application starts, open the Swagger UI path, typically `/swagger-ui/index.html` or the path configured via `springdoc.swagger-ui.path`.

Verification steps:

1. Confirm the tag list appears with the expected names and descriptions.
2. Type part of a tag name into the Filter box and observe the groups narrow down.
3. Test case differences to understand filter behavior.
4. Clear the filter input and confirm all groups reappear.
5. Open an operation with a request body and toggle between example/model if the UI supports it.
6. Open the Schemas section and check properties, data types, descriptions, required fields, enums, formats, and constraints.
7. Expand nested schemas to confirm appropriate display depth.
8. If extensions are enabled, verify `x-...` properties appear as expected.

At the same time, inspect `/v3/api-docs` or `/v3/api-docs.yaml`. If tags or schemas are missing from OpenAPI, changing UI settings cannot create them. Fix the annotations/controllers/DTOs or specification customizers first.

## 10. When there are multiple document groups

Springdoc can produce multiple OpenAPI documents via `GroupedOpenApi`. Swagger UI can display a document selector so readers choose which group to inspect.

Example:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .build();
}
```

When a user selects the `partner` document, the tag filter and schema display apply to that currently open document. Users must pick the right group before searching for operations.

Group name and tag name are two distinct concepts:

- Group selects a separate OpenAPI document, such as `public` or `partner`.
- Tag categorizes operations inside a document, such as `Books`, `Orders`, or `Payments`.

Do not use tag filtering as a substitute for selecting a group. If an operation is not in the currently open group document, filtering tags will not make it appear.

## 11. Securing documentation and the Try it out button

Swagger UI is an API reading and testing interface. Enabling filters, hiding schemas, or collapsing operations is not a security measure. If documentation exposes internal endpoints, sensitive schemas, or architectural details, control access to both Swagger UI and the OpenAPI JSON/YAML endpoints.

Common deployment practices:

- Use Spring Security to require authentication for `/swagger-ui/**`, `/swagger-ui.html`, and `/v3/api-docs/**`.
- Disable Swagger UI or documentation endpoints in environments where documentation should not be published.
- Create appropriate document groups per audience and protect group endpoints with access policies.
- Do not place tokens, passwords, private keys, or production data into examples or schema descriptions.

If you want to disable sending requests from the UI, Swagger UI has the `supported-submit-methods` option. You can configure an empty list:

```yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
```

This setting disables the submit request button (`Try it out`) in the UI per Swagger UI configuration. It does not block HTTP requests to the API; access control and runtime policies must still be enforced at the server or gateway.

## 12. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Filter box is missing | `springdoc.swagger-ui.filter` is not enabled or config not loaded | Set `filter: true`, check profile, and reload UI |
| Filter does not match summary/description | Built-in filter focuses on tags | Use consistent tag names; use browser find or a dedicated full-text search tool |
| Filter is case-sensitive | Default filter behavior is case-sensitive | Enter exact tag casing or standardize tag naming conventions |
| Tags are split into similar-looking groups | Inconsistent tag names | Standardize tag names and declare `@Tag` centrally |
| Schema does not show expected properties | DTO or OpenAPI schema lacks those properties | Inspect `/v3/api-docs`, Jackson visibility, and `@Schema` |
| Schema is collapsed too deeply | `default-models-expand-depth` or `default-model-expand-depth` is too low | Increase depth appropriately or let readers expand manually |
| Schemas section is missing | `default-models-expand-depth` is set to `-1` | Reset to a value greater than or equal to `0` |
| Only example appears, not model structure | `default-model-rendering` is set to `example` | Set `default-model-rendering: model` |
| Extensions do not appear | `show-extensions` is not enabled or OpenAPI lacks extensions | Enable the option and inspect JSON/YAML |
| YAML settings have no effect | Wrong property name, profile, or library version | Check Spring Boot bound properties and Springdoc version |
| Docs exposed despite hiding tags/schemas | Confusing UI display options with security | Protect documentation endpoints with Spring Security or environment configuration |

## 13. Checklist for search, filtering, and schema display

- [ ] Enabled `springdoc.swagger-ui.filter` if a tag filter box is needed.
- [ ] Tag names are concise, consistent, and accurately describe operation groups.
- [ ] Configured `tags-sorter` and `operations-sorter` if sorting is needed.
- [ ] `doc-expansion` matches the number of operations.
- [ ] `default-model-rendering` matches whether readers prefer examples or schemas.
- [ ] `default-models-expand-depth` and `default-model-expand-depth` do not hide essential details.
- [ ] Enabled `show-extensions` if the specification uses `x-...` extensions.
- [ ] Verified schemas, properties, required fields, formats, enums, and constraints in `/v3/api-docs`.
- [ ] Tested tag filtering and model expansion in the actual Swagger UI.
- [ ] Selected the right group before searching for operations.
- [ ] Documentation is protected by proper access policies rather than relying on hiding UI elements.
- [ ] Disabled `Try it out` if the environment only permits reading documentation.

Swagger UI's filter helps readers narrow operations by tag; model/schema options control how structures and examples are displayed. When tags are organized consistently, schemas are well documented, and the UI is configured thoughtfully, integrators can find endpoints faster and clearly understand the data to send or receive.
