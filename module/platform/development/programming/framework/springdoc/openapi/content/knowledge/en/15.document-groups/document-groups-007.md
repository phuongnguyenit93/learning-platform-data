# Group Specification Paths and Group Selection in Swagger UI

A Spring Boot application can expose multiple API groups with different target audiences and scopes. For example, an order management application may have a public API for customers, an administrative API for staff, and an internal API for other services. Putting every operation into a single OpenAPI document makes it harder for readers to locate needed endpoints and exposes sections unrelated to their role.

Springdoc-openapi supports generating multiple specification documents via `GroupedOpenApi`. Each group has its own name, a selected set of endpoints, and a dedicated document path. Swagger UI can display a dropdown list of documents so users can choose which group to view. This article covers defining groups, accessing per-group JSON/YAML, configuring the Swagger UI group selector, and controlling document publication.

## 1. What Is an OpenAPI Document Group?

A document group (API group) is a subset of operations selected from Spring controllers. Springdoc generates a separate OpenAPI document for each group. Grouping can be based on:

- Endpoint paths, such as `/api/public/**` or `/api/admin/**`.
- Controller packages, such as `com.example.api.publicapi`.
- Additional filtering conditions or document customizations.

For example, an application with three areas:

| Group | Example Path | Document Audience |
|---|---|---|
| `public` | `/api/public/**` | External clients |
| `admin` | `/api/admin/**` | Admin UI and staff |
| `internal` | `/internal/**` | Internal services or operations teams |

Each group can have its own `info`, `servers`, `paths`, `components`, security, and descriptions. Operations that do not match a group's filters will not appear in that group's document.

Document groups only partition OpenAPI contents. Placing an endpoint in the `internal` group does not protect that endpoint from external callers. API authentication and authorization must still be configured with Spring Security or an equivalent protection layer.

## 2. Creating Groups with `GroupedOpenApi`

The common approach is declaring a `GroupedOpenApi` bean per group. For example:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

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

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/internal/**")
                .build();
    }
}
```

In this example, `group(...)` sets the group name, and `pathsToMatch(...)` selects endpoints whose paths match the pattern. Each bean creates an independent document. When adding a new group, use a unique name and a filter with clear intent.

In springdoc 2.x, `GroupedOpenApi` resides in `org.springdoc.core.models.GroupedOpenApi`. Projects using springdoc 1.x may have a different API package; use the import matching your installed version rather than copying imports across major versions.

## 3. Filtering Groups by Path and Package

`GroupedOpenApi.Builder` supports common filter conditions:

| Method | Purpose |
|---|---|
| `pathsToMatch(...)` | Include only endpoints whose paths match the patterns |
| `pathsToExclude(...)` | Exclude endpoints whose paths match the patterns from the group |
| `packagesToScan(...)` | Include only controllers in the specified packages |
| `packagesToExclude(...)` | Exclude controllers belonging to the specified packages |
| `addOpenApiCustomizer(...)` | Customize the group's OpenAPI document |

### Path Filtering

When URLs clearly express business boundaries, path filtering is straightforward to read:

```java
@Bean
GroupedOpenApi customerApi() {
    return GroupedOpenApi.builder()
            .group("customer")
            .pathsToMatch("/api/customers/**")
            .pathsToExclude("/api/customers/internal/**")
            .build();
}
```

This example selects customer endpoints while excluding an internal branch. Verify the effective paths formed by combining class-level mappings, method-level mappings, and context paths; filters must match the paths exposed by Spring MVC.

### Package Filtering

If source code already separates controllers by package, you can select packages:

```java
@Bean
GroupedOpenApi billingApi() {
    return GroupedOpenApi.builder()
            .group("billing")
            .packagesToScan("com.example.application.billing.controller")
            .build();
}
```

Package filtering helps when paths across modules look similar or when groups are managed by code structure. However, moving a controller to another package can remove its endpoints from a group without changing any URL. Treat package moves as changes that can affect documentation.

### Combining Includes and Excludes

You can use includes to select a broad range and excludes to remove specific endpoints. Avoid overlapping patterns that are hard to reason about. If an endpoint matches multiple groups, it can appear in multiple documents; this is valid when sharing operations is intentional.

## 4. Configuring Groups in Application YAML

Besides beans, you can configure groups via `springdoc.group-configs` in `application.yml`:

```yaml
springdoc:
  group-configs:
    - group: public
      paths-to-match:
        - /api/public/**
    - group: admin
      paths-to-match:
        - /api/admin/**
    - group: internal
      paths-to-match:
        - /internal/**
```

This keeps group filters centralized in one place and works well for simple grouping rules. If you need customizers, method filters, or complex Java logic, declaring `GroupedOpenApi` beans is more flexible.

Pick one primary configuration method per group. Avoid declaring the same group simultaneously as both a bean and a property unless intentionally designed, as duplicate declarations cause confusion or group name conflicts.

## 5. JSON Paths for Each Group

By default, springdoc serves the overall JSON document at:

```text
/v3/api-docs
```

For a group named `public`, the group document is accessed at:

```text
/v3/api-docs/public
```

For the `admin` group:

```text
/v3/api-docs/admin
```

The path follows `/v3/api-docs/{groupName}`. `{groupName}` must match the value passed to `group(...)` or the `group` property in `group-configs`.

Example verification with curl:

```bash
curl -fS http://localhost:8080/v3/api-docs/public
curl -fS http://localhost:8080/v3/api-docs/admin
```

A group document is a complete OpenAPI document scoped to the selected operations. You can feed this URL to validators, code generators, mock servers, or per-group artifact pipelines.

## 6. YAML Paths for Each Group

Springdoc also supports fetching YAML documents. For group `public`, the YAML endpoint is typically:

```text
/v3/api-docs/public.yaml
```

For group `admin`:

```text
/v3/api-docs/admin.yaml
```

Example downloading both formats:

```bash
curl -fS http://localhost:8080/v3/api-docs/public -o public-openapi.json
curl -fS http://localhost:8080/v3/api-docs/public.yaml -o public-openapi.yaml
```

The JSON and YAML for a given group represent the same OpenAPI model. Choose the format matching your consuming tools and storage conventions. If a pipeline compares both formats, parse them into data structures and compare semantically rather than diffing raw text.

If `springdoc.api-docs.path` has been changed, the base path of documentation endpoints changes as well. For example:

```yaml
springdoc:
  api-docs:
    path: /api-docs
```

Then group endpoints use the `/api-docs` prefix instead of `/v3/api-docs`; verify the active URLs against your running configuration.

## 7. Adding Groups to the Swagger UI Selector

When multiple documents exist, Swagger UI can show a dropdown allowing users to switch groups. You can declare the URL list in `application.yml`:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
      - name: Internal API
        url: /v3/api-docs/internal
    urls-primary-name: Public API
```

Each entry has:

- `name`: display label in the Swagger UI selector.
- `url`: path to the corresponding OpenAPI document.

`urls-primary-name` selects the document opened by default using the exact `name` in the list. This value is case-sensitive relative to the declared names; keep them identical.

When groups are already registered in springdoc, URLs can point directly to the corresponding group endpoints. When configuring `urls` manually, ensure every URL is valid and reachable from the browser opening Swagger UI.

## 8. Distinguishing Swagger UI `url` and `urls`

Swagger UI can load either a single document or a list of documents:

| Property | Purpose | Use Case |
|---|---|---|
| `springdoc.swagger-ui.url` | URL of a single OpenAPI document | Single document or single primary source |
| `springdoc.swagger-ui.urls` | List of document names and URLs | Multiple groups requiring a selector |
| `springdoc.swagger-ui.urls-primary-name` | Name of the initially selected document in the list | Opening a specific default group |

Single-document configuration example:

```yaml
springdoc:
  swagger-ui:
    url: /v3/api-docs/public
```

Multi-document configuration example:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
```

When using `urls`, do not also set `url` pointing to the same document unless you have a specific configuration reason. Avoid having `url` and `urls` compete, which makes it unclear which source the UI is loading.

You can disable Swagger UI's default sample URL with:

```yaml
springdoc:
  swagger-ui:
    disable-swagger-default-url: true
```

This prevents the UI from displaying a default sample document if the application's document source is misconfigured.

## 9. Swagger UI Path and Specification Path Are Distinct

The Swagger UI page path is typically `/swagger-ui.html` (which redirects to the UI page) or `/swagger-ui/index.html`. The default OpenAPI document path is `/v3/api-docs`; per-group document paths are `/v3/api-docs/{group}`.

You can customize the UI path:

```yaml
springdoc:
  swagger-ui:
    path: /docs
```

Changing `swagger-ui.path` only changes the UI URL. It does not automatically change OpenAPI document URLs. Likewise, changing `springdoc.api-docs.path` only changes specification endpoints; update URLs in the Swagger UI list if paths are configured explicitly.

If the application runs under a context path such as `/service`, or receives a prefix from a reverse proxy, the browser-visible URL may be `/service/v3/api-docs/public`. Configure relative URLs suited to the public path and set up forwarded headers/proxy rules properly so Swagger UI can load documents.

## 10. Configuring `GroupedOpenApi` with Group-Specific Customizers

A group may require its own details or content, such as title, description, servers, or security metadata. You can attach an `OpenApiCustomizer` to the group builder:

```java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(openApi -> {
                openApi.getInfo()
                        .title("Partner API")
                        .description("API for integrating partners");
            })
            .build();
}
```

Customizers let you update the group's OpenAPI model. Ensure objects such as `info` already exist before calling setters; in practice, instantiate `Info` if it is not yet present. Avoid modifying document contents with overly broad conditions that cause one group to affect another.

If you have a shared `OpenAPI` configuration, common details can apply across multiple documents, while group customizers tailor what differs. After customizing, inspect each group's JSON/YAML endpoint to verify only the intended group was affected.

## 11. Checking Which Group Contains Which Endpoint

When configuring multiple filters, inspect the generated documents rather than merely reading config files. An endpoint may:

- Appear in exactly one group if its path/package matches only one filter.
- Appear in multiple groups if intentionally shared.
- Appear in no group if it matches no filters.
- Be excluded from a group due to `pathsToExclude` or `packagesToExclude`.

Verification steps:

1. Call each group's JSON endpoint.
2. Inspect `paths` in the document and list published operations.
3. Compare paths against group objectives.
4. Confirm excluded operations are truly absent.
5. Verify schemas in `components` are validly referenced.
6. Open Swagger UI and select each group in turn.
7. Confirm the UI displays the right title, endpoints, and schemas for the selected group.

Example using `jq` to inspect a document's path list:

```bash
curl -s http://localhost:8080/v3/api-docs/public | jq -r '.paths | keys[]'
```

This command only checks path keys; full verification requires checking HTTP methods, parameters, schemas, security, and responses of each operation.

## 12. Protecting Group Documents with Spring Security

The `internal` or `admin` groups may contain information not meant for everyone. Hiding a group from Swagger UI is insufficient to secure the documentation endpoint. Users can still request `/v3/api-docs/internal` directly if the server permits it.

Illustrative example securing internal documentation endpoints:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                            "/v3/api-docs/internal",
                            "/v3/api-docs/internal.yaml"
                    ).hasRole("ADMIN")
                    .requestMatchers(
                            "/v3/api-docs/public",
                            "/v3/api-docs/public.yaml"
                    ).permitAll()
                    .anyRequest().authenticated()
            )
            .build();
}
```

This is a condensed example; integrate it with your application's existing filter chains and security rules. If you changed `springdoc.api-docs.path`, context path, or reverse proxy prefix, update request matchers to match the URLs the server receives. Verify both JSON and YAML as well as related Swagger UI config endpoints.

Key points to remember:

- Grouping is documentation organization, not an authorization mechanism.
- Swagger UI can be secured separately from JSON/YAML endpoints.
- If internal docs must not be publicly accessible, protect the direct specification paths as well.
- Runtime APIs still need their own authorization rules; protecting docs does not protect business endpoints.
- Never place credentials, real tokens, or secrets in documentation examples or descriptions.

## 13. Group Paths When Configuration Changes

Document paths can be affected by several settings:

| Setting | Impact |
|---|---|
| `GroupedOpenApi.group(...)` or `group-configs[].group` | Group name in document URL and group identifier |
| `springdoc.api-docs.path` | Prefix of JSON/YAML endpoints |
| `server.servlet.context-path` | Application URL prefix in Spring Boot |
| Reverse proxy path prefix | Public prefix seen by browsers/clients |
| `springdoc.swagger-ui.path` | Swagger UI URL, not specification URL |
| `springdoc.swagger-ui.urls` | List of document URLs offered by the UI selector |

Renaming a group from `admin` to `backoffice` changes the document URL as well. You must update `springdoc.swagger-ui.urls`, Spring Security request matchers, artifact-fetching pipelines, and any clients/tools calling the old URL.

Do not rename a group just to change its display label in Swagger UI. If you want a different label, keep the group URL stable and set the display `name` separately inside `urls`.

## 14. Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `/v3/api-docs/{group}` returns 404 | Group not registered or URL name mismatch | Check bean/properties and group name |
| Group document lacks expected endpoints | `pathsToMatch` or `packagesToScan` does not match | Check final path mappings and controller packages |
| Endpoint appears in multiple groups | Group filters overlap | Decide whether sharing is intentional or needs exclusion |
| Swagger UI has no group selector | `urls` list misconfigured or UI config not loaded | Check `springdoc.swagger-ui.urls` and swagger-config |
| Selecting group fails to load document | Wrong URL in `urls`, missing context path, or blocked by security | Call the URL directly and inspect network response |
| UI always opens the wrong group | `urls-primary-name` does not match `name` in the list | Match the exact default group name |
| Changed `swagger-ui.path` but docs URL unchanged | The two settings serve separate purposes | Adjust `springdoc.api-docs.path` to change docs endpoints |
| Group YAML fails to load | Wrong suffix or prefix after customizing api-docs path | Check YAML URL for the specific group and springdoc version |
| Internal group remains publicly accessible | Only hidden in UI without securing docs endpoint | Add Spring Security matchers for JSON/YAML |
| Group document misses shared schemas | Schema no longer referenced in group or removed by customizer | Inspect `$ref` targets and `components.schemas` of that document |
| Swagger UI shows Petstore or sample docs | UI is falling back to its default sample URL | Configure `url`/`urls` and consider `disable-swagger-default-url` |

## 15. Complete Configuration and Verification Workflow

A practical workflow for creating groups and exposing them in Swagger UI:

1. Define group boundaries by audience, module, or publishing policy.
2. Choose path or package filters; pick stable, readable group names.
3. Register `GroupedOpenApi` beans or declare `springdoc.group-configs`.
4. Start the application and call each group's JSON endpoint.
5. Call the corresponding YAML endpoints and confirm identical content.
6. Configure `springdoc.swagger-ui.urls` with labels and URLs for each document.
7. Set `urls-primary-name` if a default group should open initially.
8. Open Swagger UI, verify the selector list, and inspect each group.
9. Protect specification and UI endpoints according to access policy.
10. Update URLs in pipelines, validators, code generators, and integration docs whenever group names or prefixes change.

Combined configuration example:

```yaml
springdoc:
  api-docs:
    path: /v3/api-docs
  group-configs:
    - group: public
      paths-to-match:
        - /api/public/**
    - group: admin
      paths-to-match:
        - /api/admin/**
  swagger-ui:
    path: /swagger-ui.html
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
    disable-swagger-default-url: true
```

After applying, verify at least these URLs:

```text
GET /v3/api-docs/public
GET /v3/api-docs/public.yaml
GET /v3/api-docs/admin
GET /v3/api-docs/admin.yaml
GET /swagger-ui.html
```

Actual URLs may differ if the application sets a context path, overrides `springdoc.api-docs.path`, or adds a prefix behind a reverse proxy. Use the real addresses accessed by clients.

## 16. Principles for Designing Document Groups

- Base groups on meaningful consumers or publishing scopes, not arbitrary package names.
- Keep group names short, stable, space-free, and URL-friendly.
- Use `pathsToMatch` when API boundaries are clear in URLs; use `packagesToScan` when controller layout mirrors module boundaries.
- Use excludes deliberately and check for overlapping filters.
- Keep Swagger UI labels (`urls[].name`) separate from group URL names when friendlier display titles are needed.
- Configure `urls-primary-name` so users land on the right default document.
- Distinguish UI paths from JSON/YAML specification paths.
- Verify group JSON and YAML independently since each group is its own document.
- Secure docs endpoints with Spring Security; never treat grouping as authorization.
- Update pipelines and clients whenever group names or endpoint prefixes change.

## Conclusion

`GroupedOpenApi` lets springdoc-openapi generate dedicated documents per controller or path group. Each group exposes JSON and YAML endpoints keyed by group name; Swagger UI can present a document selector via `springdoc.swagger-ui.urls` and pick a default group via `urls-primary-name`. When configuring groups, keep filters crisp, distinguish UI URLs from specification URLs, account for context paths or reverse proxies, and secure internal documentation with Spring Security. Inspecting every group document alongside Swagger UI ensures users see the exact API subset intended for publication.
