# `GroupedOpenApi` and Unique Group Identifiers

A Spring Boot application can expose multiple API groups for different purposes. For example, the `stores` group serves store operations, the `users` group serves user features, and the `admin` group serves administration. Each group needs its own OpenAPI document so readers see only the operations relevant to their scope.

`springdoc-openapi` supports this via `GroupedOpenApi`. Each `GroupedOpenApi` bean defines a document group using a group identifier and endpoint filtering criteria. Springdoc generates one OpenAPI document per group, typically accessible at `/v3/api-docs/{group}`. The group identifier must be unique within the application because it is used to distinguish documents and construct access paths.

## 1. What Problem Do Document Groups Solve?

When an application has many controllers, a single document containing every endpoint can become long and unwieldy. Document groups let you partition the specification by domain, version, audience, or deployment scope.

For example, an e-commerce system may have these controllers:

| Scope | Example Package | Example Path | Document Group |
| --- | --- | --- | --- |
| Stores | `com.example.api.store` | `/api/stores/**` | `stores` |
| Users | `com.example.api.user` | `/api/users/**` | `users` |
| Administration | `com.example.api.admin` | `/api/admin/**` | `admin` |

Each group can be loaded independently to generate client SDKs, review contracts, export documentation, or distribute to a specific development team. The controllers still run in the same Spring Boot application; grouping only organizes the generated documentation.

A document group is not a separate application, does not create additional runtime routes, and does not automatically enforce access permissions. Endpoints are still registered by Spring MVC according to controller mappings. Spring Security or other security mechanisms continue to determine who can call each endpoint.

## 2. What Is `GroupedOpenApi`?

`GroupedOpenApi` is springdoc's configuration mechanism for generating an OpenAPI document from a selected set of endpoints. Typically, you declare each group as a bean inside a `@Configuration` class:

```java
@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi storesApi() {
        return GroupedOpenApi.builder()
            .group("stores")
            .pathsToMatch("/api/stores/**")
            .build();
    }

    @Bean
    GroupedOpenApi usersApi() {
        return GroupedOpenApi.builder()
            .group("users")
            .pathsToMatch("/api/users/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
```

In this example:

- `GroupedOpenApi.builder()` creates a builder for a document group.
- `group("stores")` sets the identifier of the group.
- `pathsToMatch(...)` selects the API paths belonging to the group.
- `build()` finalizes the configuration so Spring registers the bean.

Springdoc detects `GroupedOpenApi` beans in the application context and generates the corresponding documents. You do not need to create a new controller for each group.

## 3. Group Identifiers Must Be Unique

The identifier passed to `.group("...")` is the lookup key for the document. Each group in the same application requires a distinct value:

```java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public-v1")
        .pathsToMatch("/api/v1/public/**")
        .build();
}

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin-v1")
        .pathsToMatch("/api/v1/admin/**")
        .build();
}
```

These two groups have different identifiers, so they get separate documentation endpoints. If two beans both declare `group("public")`, they compete for the same identifier. Do not rely on bean initialization order or override behavior to determine the final document; fix the configuration so every group has a unique name.

Useful naming conventions include:

- Use lowercase letters and hyphens, such as `store-v1` or `admin-v1`.
- Keep names short and reflective of the domain or version.
- Keep names stable because clients, pipelines, and documentation links may reference them directly.
- Do not use the Java bean method name as an identifier in place of `.group(...)`; the two serve different purposes.
- When adding a new group, check all existing `GroupedOpenApi` configurations to prevent name collisions.

The group identifier is also distinct from `info.title` in OpenAPI. `group` routes to the document; `info.title` is the descriptive API title inside the document. You can have a group named `stores-v1` whose `info.title` is `Store Management API`.

## 4. Selecting Endpoints by URL Path

`pathsToMatch` accepts one or more patterns to select API paths to include in the document:

```java
@Bean
GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .pathsToMatch("/api/products/**", "/api/categories/**")
        .build();
}
```

The `catalog` group includes operations whose paths match one of the declared patterns. Path-based filtering works well when URL structure already reflects the API domain or version.

You can exclude subpaths from a group with `pathsToExclude`:

```java
@Bean
GroupedOpenApi publicCatalogApi() {
    return GroupedOpenApi.builder()
        .group("public-catalog")
        .pathsToMatch("/api/**")
        .pathsToExclude("/api/internal/**", "/api/admin/**")
        .build();
}
```

In this example, the group selects paths under `/api/**` and excludes internal and administrative paths. Use exclusions when multiple endpoints share a URL area but certain endpoints should not appear in the published document.

Patterns are evaluated against the API paths discovered by springdoc. If the application uses a context path, servlet path, or reverse proxy configuration, verify the paths appearing in `/v3/api-docs` and adjust patterns to match the operation paths in the specification.

## 5. Selecting Endpoints by Controller Package

If Java packages are already organized by domain, you can use `packagesToScan`:

```java
@Bean
GroupedOpenApi userApi() {
    return GroupedOpenApi.builder()
        .group("users")
        .packagesToScan("com.example.api.user")
        .build();
}
```

Springdoc includes controllers belonging to the specified package in the group. You can specify multiple packages:

```java
@Bean
GroupedOpenApi accountApi() {
    return GroupedOpenApi.builder()
        .group("accounts")
        .packagesToScan(
            "com.example.api.account",
            "com.example.api.profile"
        )
        .build();
}
```

To exclude a package from a group, use `packagesToExclude`:

```java
@Bean
GroupedOpenApi externalApi() {
    return GroupedOpenApi.builder()
        .group("external")
        .packagesToScan("com.example.api")
        .packagesToExclude("com.example.api.internal")
        .build();
}
```

Package filtering works best when source code structure clearly mirrors domains. Path filtering works best when URL conventions serve as the main boundary. You can combine both filter types when you need to constrain both controller packages and operation paths.

## 6. Combining Package and Path Filters in the Same Group

A single group can use both `packagesToScan` and `pathsToMatch`:

```java
@Bean
GroupedOpenApi storeV1Api() {
    return GroupedOpenApi.builder()
        .group("store-v1")
        .packagesToScan("com.example.api.store")
        .pathsToMatch("/api/v1/**")
        .pathsToExclude("/api/v1/store/internal/**")
        .build();
}
```

This configuration restricts the document to controllers in the store package and operations with matching paths, while excluding internal paths. When combining multiple filters, think of them as scope-narrowing conditions. If an endpoint is missing, check both the controller's declared package and the mapping's actual path.

Other builder filters can be used to filter by media type or header when supported by your springdoc version, such as `producesToMatch`, `consumesToMatch`, and `headersToMatch`. Add extra filters only when explicitly needed; combining many filter conditions makes it harder to diagnose why an endpoint was excluded from a group.

## 7. An Endpoint Can Appear in Multiple Groups

Groups are independent documents generated from the same application. If the filter criteria of multiple groups match the same operation, that operation can appear in multiple documents.

For example, a store lookup endpoint might belong to both the `stores` group and the `public-v1` group:

```java
@Bean
GroupedOpenApi storesApi() {
    return GroupedOpenApi.builder()
        .group("stores")
        .pathsToMatch("/api/stores/**")
        .build();
}

@Bean
GroupedOpenApi publicV1Api() {
    return GroupedOpenApi.builder()
        .group("public-v1")
        .pathsToMatch("/api/v1/public/**", "/api/stores/**")
        .build();
}
```

This does not register the endpoint twice and does not create two controller instances. It simply includes the same operation in two documents to serve two different audiences.

If you do not want an endpoint to appear in multiple documents, design non-overlapping path/package filters or use exclusions. If appearing in multiple groups is intentional, keep schemas and descriptions consistent across those groups.

## 8. Defining Groups in `application.yml`

Besides Java beans, springdoc allows defining groups dynamically in Spring Boot configuration using `springdoc.group-configs`. With this approach, you do not need to create separate `GroupedOpenApi` beans for the groups listed in configuration:

```yaml
springdoc:
  group-configs:
    - group: stores
      paths-to-match:
        - /api/stores/**
    - group: users
      packages-to-scan:
        - com.example.api.user
    - group: admin
      paths-to-match:
        - /api/admin/**
      packages-to-scan:
        - com.example.api.admin
```

Each entry has a unique `group` and its corresponding filter criteria. YAML configuration fits well when groups only need static per-environment declarations or centralized management in config files.

Avoid declaring the same group via both `springdoc.group-configs` and a `GroupedOpenApi` bean unless you have a clear reason. Choose one management style per group to prevent duplicate configuration or identifier conflicts.

## 9. Document URLs for Each Group

For the group id `stores`, the default documentation endpoint is typically:

```text
/v3/api-docs/stores
```

For the group id `users`:

```text
/v3/api-docs/users
```

YAML specifications can be fetched via endpoints with the `.yaml` suffix, for example:

```text
/v3/api-docs/stores.yaml
/v3/api-docs/users.yaml
```

If the application configures a context path, these URLs are mounted under that context path. If `springdoc.api-docs.path` is changed, the base path of the documentation endpoints changes accordingly; the group id is still appended to identify the corresponding document.

Swagger UI can display discovered groups in a document selector dropdown. Users pick `stores`, `users`, or `admin` to open the corresponding specification. You can also verify JSON/YAML independently of the UI by calling the group's URL directly.

## 10. Distinguishing Group IDs from OpenAPI Metadata

Groups can share common metadata or each have their own. Fields like `info.title`, `info.version`, and `info.description` describe the API content inside the document; they do not replace the group id.

For example, two documents might use group names and metadata like this:

| Group id | `info.title` | `info.version` |
| --- | --- | --- |
| `store-v1` | `Store API` | `1.0` |
| `admin-v1` | `Admin API` | `1.0` |

An `OpenAPI` bean can provide shared metadata or components across groups. If you need to customize metadata specifically for one group, attach a customizer to the corresponding `GroupedOpenApi` configuration. Clearly distinguish which components are shared application-wide and which belong to a single document.

## 11. Document Groups Are Not Security Boundaries

A dangerous misconception is assuming that if an endpoint is absent from the public group, public users cannot invoke that endpoint. Group filters only control which operations are included in the OpenAPI document.

For example:

- `pathsToExclude("/api/admin/**")` only removes administrative paths from the public group's document.
- It does not block HTTP requests to `/api/admin/**`.
- It does not require a token, check roles, or create any rule in Spring Security.

If administrative endpoints require restricted access, configure authentication and authorization at runtime. You can also protect documentation endpoints such as `/v3/api-docs/**` and Swagger UI with Spring Security if your deployment policy requires it. Publishing or hiding documentation should be treated as an information distribution decision; API protection remains the responsibility of the security layer.

## 12. Verifying Groups After Configuration

After adding or modifying `GroupedOpenApi`, verify each group independently:

1. Start the application and check logs to ensure group configuration beans are created.
2. Call `/v3/api-docs/{group}` for each group id and confirm an OpenAPI document is returned.
3. Inspect `paths` in the document and verify only operations within the intended scope are present.
4. Check that `components.schemas`, responses, security schemes, and required `$ref` targets are present.
5. Verify an endpoint outside the path/package filters to confirm it does not appear in the group.
6. Check any endpoint intentionally included in multiple groups to confirm expected overlap behavior.
7. Open Swagger UI and confirm the group selector has clear names and each selection loads the right document.
8. Call runtime endpoints directly to verify that group filters are not mistaken for access rules.

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `/v3/api-docs/{group}` returns not found | Group id does not exist or bean/config was not loaded | Check `.group(...)`, `springdoc.group-configs`, and the application context. |
| Two groups share the same document or show unexpected results | Duplicate group identifiers | Assign a unique group id to each `GroupedOpenApi`. |
| Group has no operations | `pathsToMatch` or `packagesToScan` does not match controllers | Check actual path mappings and packages; relax filters step by step. |
| Internal operation still appears in public group | Missing `pathsToExclude` or `packagesToExclude` | Add exclusion criteria and verify the generated document. |
| Operation appears in two groups | Filters of two groups overlap | Determine whether this is intentional or an unintended filter overlap. |
| Swagger UI lacks group selection | Groups not registered, UI disabled, or custom URL configuration incorrect | Test group docs directly first, then inspect Swagger UI configuration. |
| Endpoint hidden from docs is still callable | Group filters only affect documentation | Configure Spring Security or runtime protection mechanisms. |
| Group-specific metadata looks identical across groups | Only a global `OpenAPI` bean is declared | Use a group-specific customizer for groups needing distinct metadata. |

## 13. Guidelines for Application

- Create one `GroupedOpenApi` per document you need to publish separately.
- Set `.group(...)` to a unique, stable, and readable identifier.
- Choose `pathsToMatch` when boundaries align with URLs; choose `packagesToScan` when boundaries align with controller package structure.
- Use `pathsToExclude` and `packagesToExclude` to remove out-of-scope endpoints.
- Combine multiple filters only when you clearly understand their intersection.
- Define groups via Java beans or `springdoc.group-configs`; avoid managing the same group with both mechanisms.
- Use `/v3/api-docs/{group}` to inspect each document and Swagger UI to navigate between groups.
- Never use hiding operations from documentation as an endpoint security mechanism.
- Verify group ids, paths, packages, and schemas in every document after each change.

`GroupedOpenApi` enables a single Spring Boot application to publish multiple OpenAPI documents across different scopes. Unique group ids establish stable routes and identities for each document, while path/package filters determine which operations appear in each group. With clear group design and per-document verification, development teams can distribute leaner documentation while maintaining one consistent application and endpoint codebase.

## References

- [Springdoc OpenAPI FAQ – Multiple OpenAPI Definitions and GroupedOpenApi](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 FAQ – Groups for Spring Boot 3](https://springdoc.org/v2/faq.html)
- [Springdoc OpenAPI – Official Documentation](https://springdoc.org/)
