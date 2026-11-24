# Declaring Groups via Beans or group-configs Properties

## 1. Why Split OpenAPI Documentation into Groups?

A Spring Boot application may serve several endpoint groups: public APIs for customers, administrative APIs, internal APIs between services, and partner APIs. If every endpoint appears in a single OpenAPI document, readers must manually filter out irrelevant parts and may see operations outside their integration scope.

Springdoc OpenAPI supports **document groups** to generate multiple OpenAPI documents from the same application. Each group selects a subset of operations using criteria such as URL paths or controller packages. Each group's document can be opened via its own URL and displayed in Swagger UI.

There are two common ways to declare groups:

- **GroupedOpenApi bean**: Java-based group configuration, suited for code-driven logic, conditions, or customizers.
- **springdoc.group-configs**: declarative group configuration in application.yml or application.properties, suited for static filters and centralized settings.

Both approaches create document groups in Springdoc. Pick the approach that fits your project structure, use stable group names, and verify the documentation endpoints once the application starts.

## 2. GroupedOpenApi and Operation Selection Principles

A document group is identified by its group name. A group can constrain operations by:

- **pathsToMatch**: include API paths matching the given patterns.
- **pathsToExclude**: exclude paths you do not want in the group.
- **packagesToScan**: inspect only controllers in the specified packages.
- **packagesToExclude**: exclude controllers belonging to specified packages.
- Additional media type or header conditions if supported by your Springdoc version.

For example, a public group selecting only endpoints under `/api/public`:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}
~~~

An admin group can be selected by both path and package:

~~~java
@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .packagesToScan("com.example.shop.api.admin")
        .pathsToMatch("/api/admin/**")
        .build();
}
~~~

The group name is the identifier used when accessing documentation. Use short, stable names without spaces that reflect business scope—for example public, admin, partner, or internal.

When combining multiple filters, treat them as conditions narrowing the operation set and verify the result in the generated document. Do not assume an endpoint is placed in the right group based solely on package or group names.

## 3. Declaring GroupedOpenApi via Beans

GroupedOpenApi is a Spring-managed bean. Springdoc discovers these beans and generates a separate OpenAPI document for each group.

Example configuring two groups:

~~~java
@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    public GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    public GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
~~~

In Springdoc 2.x, GroupedOpenApi lives in package org.springdoc.core.models. In Springdoc 1.x, the package may differ. Use the import matching your project's dependency version rather than copying imports across major versions.

Every bean should have a unique group name. If two beans share the same group name, group registration and document routing may conflict or yield unexpected output.

A clear group configuration should express:

- Selected endpoint scope.
- Target controller packages if using package filters.
- Paths to exclude.
- Group-specific customizers if the document requires distinct metadata.
- Verification checks to ensure endpoints are neither missing nor leaked accidentally.

## 4. Filtering by Package with packagesToScan

When controllers are organized by business package, you can select a group via packagesToScan:

~~~java
@Bean
public GroupedOpenApi orderApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .packagesToScan(
            "com.example.shop.api.orders",
            "com.example.shop.api.ordertracking"
        )
        .build();
}
~~~

This configuration selects controllers in the declared packages. It works well when source code layout clearly mirrors API boundaries.

However, Java packages are a source organization detail. A package refactoring can drop operations from a group document even when API URLs stay unchanged. Therefore:

- Keep package filters synchronized with controller structure.
- Add tests checking key operations in each group.
- Never treat package names as security boundaries.
- Add path filters when you need to guarantee a group only contains a specific URL region.

If a controller in the same package contains both public and internal endpoints, using packagesToScan alone may pull both into the same group. In that case, split packages, combine with pathsToMatch/pathsToExclude, or use more targeted filter rules.

## 5. Filtering by Path with pathsToMatch and pathsToExclude

Path filters fit well when group boundaries are defined by API URLs.

For example:

~~~java
@Bean
public GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .pathsToMatch("/api/products/**", "/api/categories/**")
        .pathsToExclude("/api/products/internal/**")
        .build();
}
~~~

In this example:

- The group selects operations under /api/products and /api/categories.
- Operations under /api/products/internal are excluded from the group.

Patterns are typically written in the path-matching syntax supported by Springdoc. Verify actual output when using wildcards, path variables, or application-configured base paths.

Paths are matched against operation paths in OpenAPI. If the application has a custom context path or servlet path, verify the paths appearing in documentation and how your Springdoc version applies filters.

Avoid selecting a broad prefix such as /api/** if that same prefix contains internal APIs, admin routes, or experimental endpoints. Use explicit includes and excludes to minimize accidental publication of operations.

## 6. Declaring Groups via springdoc.group-configs in YAML

If groups only need static filters, you can declare them in application.yml:

~~~yaml
springdoc:
  group-configs:
    - group: public
      paths-to-match:
        - /api/public/**
    - group: admin
      packages-to-scan:
        - com.example.shop.api.admin
      paths-to-match:
        - /api/admin/**
    - group: partner
      paths-to-match:
        - /api/partner/**
      paths-to-exclude:
        - /api/partner/internal/**
~~~

Each item in group-configs describes a group. The group field is the group identifier; packages-to-scan, paths-to-match, and paths-to-exclude define which operations belong to that document.

You can specify lists of multiple packages or path patterns. For instance, a partner group could include both /api/partner/v1/** and /api/partner/v2/** if they belong to the same documentation contract.

YAML configuration works well when:

- Groups rely solely on package/path filters.
- You want to vary documentation scope by profile or environment.
- You want configuration managed alongside other Spring Boot properties.
- No Java logic is needed to construct groups.

Supported property names and filters may vary across Springdoc versions. Check the configuration reference for your exact dependency version before using properties beyond the basic examples.

## 7. Declaring Groups in application.properties

The same configuration can be written in application.properties:

~~~properties
springdoc.group-configs[0].group=public
springdoc.group-configs[0].paths-to-match[0]=/api/public/**

springdoc.group-configs[1].group=admin
springdoc.group-configs[1].packages-to-scan[0]=com.example.shop.api.admin
springdoc.group-configs[1].paths-to-match[0]=/api/admin/**

springdoc.group-configs[2].group=partner
springdoc.group-configs[2].paths-to-match[0]=/api/partner/**
springdoc.group-configs[2].paths-to-exclude[0]=/api/partner/internal/**
~~~

Indices on group-configs identify list entries; indices on paths-to-match or packages-to-scan identify pattern list elements.

When configuring multiple groups, ensure indices do not collide or leave unintended gaps. With YAML, list syntax is usually easier to read; if a project standardizes on properties files, keep consistent indexing conventions.

Avoid declaring the same group in both a GroupedOpenApi bean and group-configs without a clear reason. Dual configuration sources can create duplicate groups or confuse maintainers about which configuration takes effect. Pick one authoritative source per group.

## 8. Combining Multiple Filter Conditions

A group may need to constrain both package and path:

~~~java
@Bean
public GroupedOpenApi customerApi() {
    return GroupedOpenApi.builder()
        .group("customers")
        .packagesToScan("com.example.shop.api.customer")
        .pathsToMatch("/api/customers/**")
        .pathsToExclude("/api/customers/internal/**")
        .build();
}
~~~

This combination helps when a package contains multiple controllers or a path prefix is shared across modules. It aligns the document group with both source code layout and URL contracts.

Verify filter semantics in your Springdoc version. In practice, an operation must satisfy all applicable filter conditions to appear. If a group is empty or missing endpoints, check package, path, and exclude patterns individually instead of loosening every filter at once.

You can draft an expectation table before configuring:

| Group | Expected Package | Expected Path | Excluded Path |
|---|---|---|---|
| public | api.public | /api/public/** | /api/public/internal/** |
| admin | api.admin | /api/admin/** | None |
| partner | api.partner | /api/partner/** | /api/partner/internal/** |

This table becomes the baseline for writing tests verifying each group contains the right operations.

## 9. Customizing Metadata Per Group

Each group is an independent OpenAPI document. You may need distinct titles, descriptions, or metadata for public, admin, and partner documents.

With the GroupedOpenApi builder, you can attach an OpenApiCustomizer to the group:

~~~java
@Bean
public GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(openApi ->
            openApi.info(new Info()
                .title("Partner API")
                .description("API for integrating partners")
                .version("1.0.0")
            )
        )
        .build();
}
~~~

OpenApiCustomizer lets you modify the OpenAPI model before the document is returned. Here, Info metadata for the partner group is customized independently.

Customizers can also add tags, servers, extensions, or other metadata as needed. Keep configuration predictable: each customizer should have a clear group scope and avoid inadvertently overwriting another group's content.

If multiple groups share common metadata, you can reuse a helper function or builder utility for Info. Check the customizer API for your Springdoc version, as package names and registration hooks can differ across major versions.

## 10. Documentation Endpoints for Each Group

When a group named public is declared, Springdoc exposes a dedicated document for it. With default endpoints:

| Document | Typical URL |
|---|---|
| Default OpenAPI JSON | /v3/api-docs |
| Default OpenAPI YAML | /v3/api-docs.yaml |
| OpenAPI JSON for public group | /v3/api-docs/public |
| OpenAPI YAML for public group | /v3/api-docs/public.yaml |
| OpenAPI JSON for admin group | /v3/api-docs/admin |
| OpenAPI YAML for admin group | /v3/api-docs/admin.yaml |

These URLs assume springdoc.api-docs.path is unchanged and no extra context path is set. If the application configures a custom docs path, group paths follow that base configuration.

Example fetching the public document:

~~~http
GET /v3/api-docs/public
~~~

Fetching the admin YAML document:

~~~http
GET /v3/api-docs/admin.yaml
~~~

Open each URL and inspect paths inside. Receiving HTTP 200 alone does not prove the group contains the expected endpoints; the document could be valid yet empty or missing operations due to misconfigured filters.

## 11. Displaying Groups in Swagger UI

Swagger UI can display a selector list of group documents for users to switch between. Springdoc provides Swagger UI configuration and a swagger-config endpoint so the UI knows which documents are available.

Under default settings, the UI is typically served at:

~~~text
/swagger-ui.html
~~~

or at the custom UI path configured via springdoc.swagger-ui.path.

When multiple GroupedOpenApi beans exist, verify:

- Does Swagger UI list each group's name?
- Does selecting a group load the right /v3/api-docs/{group} URL?
- Do operations shown in the UI match the group's JSON/YAML?
- Are server URLs and security schemes accurate for the active document?
- Are there any duplicate group names or stale cached documents?

You can inspect the Swagger UI configuration endpoint—typically /v3/api-docs/swagger-config—to check the URL list served to the UI. If the UI does not display groups, check swagger-config and relevant springdoc.swagger-ui properties.

Swagger UI is solely a viewer and interactive client. It does not decide which operations belong to a group; operation selection happens when Springdoc builds each document.

## 12. Distinguishing Document Groups from API Versions

Groups and versions solve two distinct problems:

- **Group** partitions documentation by scope, audience, or business domain.
- **API version** represents a contract version, typically expressed in path, header, or media type according to application policy.

For example, an application might have:

| Group | Paths | Purpose |
|---|---|---|
| public-v1 | /api/v1/public/** | Public API version 1 |
| public-v2 | /api/v2/public/** | Public API version 2 |
| admin | /api/admin/** | Administrative API |
| partner | /api/partner/** | Partner integration API |

A group name can include a version marker so readers recognize it easily, but naming a group does not create route versioning or change controller behavior.

If an API uses URL versioning, controller mappings must actually define those versioned paths. If it uses header or media type versioning, ensure both routing and OpenAPI documentation accurately reflect how clients send requests.

## 13. Groups Are Not Security Boundaries

A serious design mistake is assuming an endpoint absent from the public group is protected. Groups only filter OpenAPI document contents; they do not block HTTP requests.

For example, excluding /api/admin/** from the public group does not prevent clients from calling admin endpoints. Access rights must be enforced via Spring Security, authorization rules, method security, or gateway policies.

You should also protect documentation endpoints themselves if OpenAPI documents contain internal details. Configure Spring Security to restrict access to /v3/api-docs/** and Swagger UI in environments that require it. Security rules should be tested separately for both the default document and per-group documents.

Never use paths-to-exclude as a substitute for authorization. An endpoint hidden from Swagger UI remains callable if the application permits it.

## 14. Common Issues When Configuring Groups

| Symptom | Causes to Check |
|---|---|
| Group does not appear | Bean not scanned by Spring or malformed group-configs structure |
| Group appears but has no operations | paths-to-match or packages-to-scan does not match |
| Endpoint is missing | paths-to-exclude or packages-to-exclude filtered it out unintentionally |
| Endpoint appears in multiple groups | Group filters overlap |
| Two documents share the same group name | Duplicate group name across beans and config properties |
| Swagger UI lacks the group list | swagger-config does not return group URLs or UI uses a custom config |
| Group document URL returns 404 | Wrong group name, wrong api-docs path, or missing context path |
| JSON works but YAML is unreachable | Suffix path or YAML export config mismatch for version |
| Group Info metadata is wrong | Customizer not applied or overwritten by another customizer |
| Internal API appears in public docs | Filter too broad or controllers share package/path |
| Hidden group endpoint is still callable | Grouping only affects docs; runtime security rule is missing |

When troubleshooting, check in order: whether bean/configuration is loaded, group name, package filters, path filters, group JSON endpoint, and finally Swagger UI. This isolates whether the issue lies in group registration, operation selection, or UI rendering.

## 15. Testing Each Group's Contents

Do not merely assert that the documentation URL returns 200. Verify that the set of operations matches the intended scope.

A straightforward approach is fetching OpenAPI JSON and asserting on key paths:

~~~java
mockMvc.perform(get("/v3/api-docs/public"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.paths['/api/public/products']").exists())
    .andExpect(jsonPath("$.paths['/api/admin/users']").doesNotExist());
~~~

This test checks one path that must exist and one path that must not appear. Replace path names with your application's actual mappings.

For each group, maintain an expectation checklist:

- Required paths that must appear.
- Paths that must not appear.
- Expected HTTP operations.
- Key schemas and security schemes.
- Document title, version, and server URLs.

When using package scanning, tests catch package refactors that leave a group empty. When using path patterns, tests catch new endpoints that accidentally leak into public docs.

You can also diff each group's OpenAPI document in CI to detect unintended contract changes before release.

## 16. Choosing Between Beans and group-configs

Both configuration styles serve the same goal but suit different needs:

| Criterion | GroupedOpenApi bean | springdoc.group-configs |
|---|---|---|
| Declaration | Java configuration | application.yml/properties |
| Package/path filters | Yes | Yes, depending on version properties |
| Dynamic group creation logic | More flexible | Not suited for dynamic logic |
| Group-specific OpenApiCustomizer | Attached directly via builder | Needs extra Java config for custom logic |
| Profile-based management | Supported via Spring beans/profiles | Convenient with Spring Boot config |
| Best suited for | Groups needing customizers or code conditions | Static groups, simple configuration |

If you only need to split by path or package, group-configs is usually concise and easy to manage. If you need customizers, method filters, or programmatic group creation, GroupedOpenApi beans offer greater flexibility.

You do not need both mechanisms for the same group. If a project uses both, assign clear ownership: e.g., group-configs for static groups and beans for special groups with customizers. Then verify there are no duplicate group names.

## 17. Workflow for Implementing Document Groups

A practical workflow:

1. Identify documentation audiences: public, admin, partner, or internal.
2. Select group boundaries by path or package.
3. Choose unique, stable, and clear group names.
4. Pick GroupedOpenApi beans or springdoc.group-configs.
5. Declare explicit include/exclude filters.
6. Attach group-specific OpenApiCustomizers if distinct metadata is needed.
7. Start the application and fetch each /v3/api-docs/{group} endpoint.
8. Verify Swagger UI and swagger-config.
9. Write tests asserting required paths and excluded paths.
10. Verify security for both documentation endpoints and business endpoints.
11. Add OpenAPI group checks to CI to catch unintended changes.

Whenever adding a new endpoint, determine which group it belongs to. Without a clear rule, endpoints can either be omitted from docs or land in the wrong group.

## 18. Principles for Maintaining Document Groups

When using Springdoc to generate multiple OpenAPI documents, follow these principles:

1. Use a unique group name for each document.
2. Choose path/package filters that reflect true API boundaries.
3. Combine includes and excludes deliberately.
4. Use beans when Java logic or customizers are needed; use group-configs for static configuration.
5. Avoid declaring the same group across multiple configuration sources without a clear convention.
6. Verify each group's JSON/YAML endpoints independently.
7. Verify Swagger UI and swagger-config.
8. Never treat groups as a security or API versioning mechanism.
9. Test both required paths and disallowed paths.
10. Keep documentation and security rules evolving together as the API grows.

GroupedOpenApi beans and springdoc.group-configs make it straightforward to serve distinct OpenAPI documents from a single Spring Boot application. With clear group boundaries, unique names, and intentional filters, each integrator group gets exactly the relevant API contract. Inspecting per-group JSON/YAML and securing documentation endpoints keeps API contract distribution well-controlled.

