# Filtering with pathsToMatch and pathsToExclude

In a Spring Boot application, controllers can serve multiple user groups and purposes: public APIs for customers, administrative APIs, internal endpoints for other services, or operational endpoints. When springdoc-openapi generates OpenAPI documentation, teams do not always want every endpoint in a single specification. Path filters let you select which endpoints to publish and exclude branches that fall outside the document's scope.

The two primary properties are **pathsToMatch** and **pathsToExclude**. The first specifies which paths to include; the second excludes paths that should not appear. They can be configured application-wide, per document group using **GroupedOpenApi**, or via **springdoc.group-configs** in application.yml.

## 1. Distinguishing Path Filtering and Package Filtering

springdoc-openapi can constrain documentation by endpoint path or by controller package:

| Configuration | Purpose | Example |
| --- | --- | --- |
| **pathsToMatch** | Select endpoint paths to include in documentation | `/api/public/**` |
| **pathsToExclude** | Exclude paths from documentation | `/api/internal/**` |
| **packagesToScan** | Scan only controllers in specified packages | **com.example.orders.api** |
| **packagesToExclude** | Skip controllers in specified packages | **com.example.internal.web** |

Path filtering fits well when the URL structure clearly reflects API scope, such as `/api/v1/**`, `/api/admin/**`, and `/internal/**`. Package filtering is useful when controllers are organized by module or business domain even if URLs lack distinct prefixes.

A group can combine both path and package filters. For instance, a group selecting endpoints under `/api/v1/**` and controllers in **com.example.orders.api** is constrained by both conditions. Combining them helps when an application has multiple controllers sharing a URL prefix or multiple modules containing endpoints with similar URL structures.

## 2. Understanding pathsToMatch and pathsToExclude

**pathsToMatch** accepts one or more path patterns. When declared, the document group includes only endpoints matching the selected patterns. **pathsToExclude** accepts a list of patterns to exclude from the result.

For example, a public API might have these paths:

| Endpoint | Purpose |
| --- | --- |
| **/api/orders** | Create or list orders |
| **/api/orders/{id}** | View order details |
| **/api/catalog/products** | List products |
| **/api/internal/reconciliation** | Internal reconciliation |
| **/api/admin/users** | Manage admin users |

If documentation for external clients only needs orders and catalog, you can include `/api/**` and exclude `/api/internal/**` and `/api/admin/**`. Include patterns can list multiple branches; exclude patterns remove branches outside the target scope.

Common patterns include:

| Pattern | Usage |
| --- | --- |
| `/api/v1/**` | Select endpoints under the API version 1 branch |
| `/api/orders/**` | Select endpoints in the orders branch |
| `/api/internal/**` | Identify the internal branch to exclude from public docs |
| `/api/admin/**` | Identify the administrative branch |
| **/api/health** | Include or exclude a specific path |
| **/api/orders/{id}** | Path with a path variable matching controller mapping |

These examples use wildcards following Spring ecosystem path matching conventions. The `/**` pattern is typically used to cover a branch and its subpaths. Do not treat pattern strings as regular expressions. When using complex syntax or upgrading Spring Framework, verify the output because Spring MVC matching mechanisms such as PathPattern and AntPathMatcher have version-specific differences.

Paths in filters correspond to controller mapping paths, such as **/api/orders/{id}**. Do not include scheme, hostname, or query strings in patterns. If the application runs behind a context path or reverse proxy, inspect the generated OpenAPI endpoint to confirm the exact paths springdoc uses during filtering.

## 3. Filtering the Entire Document in application.yml

If you want to apply the same scope to the application's default document, configure both properties under **springdoc**:

~~~yaml
springdoc:
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
    - /api/admin/**
~~~

In this example, springdoc includes only endpoints under `/api/**` in the default document, then excludes the internal and admin branches. This configuration fits when the application has a single document or when all documentation shares the same filtering rules.

You can list multiple path patterns in YAML. When using a properties file, lists can be specified as comma-separated strings per springdoc's configuration docs:

~~~properties
springdoc.paths-to-match=/api/**,/catalog/**
springdoc.paths-to-exclude=/api/internal/**,/catalog/private/**
~~~

Kebab-case property names such as **paths-to-match** and **paths-to-exclude** are the preferred format in application.yml and application.properties. Older FAQ examples sometimes show camelCase **pathsToMatch**; for new configurations, use the standard names from the Configuration Properties table of your springdoc version.

Note: global configuration affects the scope of documentation generated at the application level. If each group needs a different set of endpoints, place filters on each group rather than applying an overly narrow global rule and trying to widen it per group.

## 4. Filtering Per Group with GroupedOpenApi

When an application serves multiple documents, the clearest approach is declaring each **GroupedOpenApi** with its own group name, include patterns, and exclude patterns.

The example below creates a document for the public API:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    public GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/**")
            .pathsToExclude(
                "/api/internal/**",
                "/api/admin/**"
            )
            .build();
    }
}
~~~

In this configuration:

- **group("public")** names the document group public.
- **pathsToMatch("/api/**")** selects endpoints under the API branch.
- **pathsToExclude(...)** removes internal and administrative branches from the group.

By default, this group's specification is served at:

~~~text
http://localhost:8080/v3/api-docs/public
~~~

Group names must be unique within the application. If **springdoc.api-docs.path** has been changed, the group endpoint uses the new base path instead of **/v3/api-docs**.

You can declare multiple groups with distinct scopes:

~~~java
@Bean
public GroupedOpenApi customerApi() {
    return GroupedOpenApi.builder()
        .group("customer")
        .pathsToMatch(
            "/api/orders/**",
            "/api/catalog/**"
        )
        .pathsToExclude("/api/orders/internal/**")
        .build();
}

@Bean
public GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .build();
}
~~~

The customer group contains orders and catalog APIs, while the admin group contains administrative endpoints. An endpoint can appear in multiple groups if patterns across multiple groups select it. Appearing in one group does not automatically exclude an endpoint from another group.

With springdoc-openapi v2 on Spring Boot 3, the **GroupedOpenApi** import is typically **org.springdoc.core.models.GroupedOpenApi**. The springdoc 1.x line uses a different package; when working with legacy projects, match the import to your installed version.

## 5. Declaring Groups and Filters in application.yml

Creating **GroupedOpenApi** beans is optional if you prefer declaring groups via Spring Boot configuration. springdoc supports the **springdoc.group-configs** list:

~~~yaml
springdoc:
  group-configs:
    - group: customer
      display-name: Customer API
      paths-to-match:
        - /api/orders/**
        - /api/catalog/**
      paths-to-exclude:
        - /api/orders/internal/**

    - group: admin
      display-name: Admin API
      paths-to-match:
        - /api/admin/**

    - group: partner
      display-name: Partner API
      paths-to-match:
        - /partner/**
      paths-to-exclude:
        - /partner/internal/**
~~~

Each item in **group-configs** defines one group:

- **group** is the unique identifier used in the document URL.
- **display-name** is the label shown in Swagger UI's group selector when the UI is configured to use groups.
- **paths-to-match** selects the endpoint branches for the group.
- **paths-to-exclude** removes branches you do not want included in the group.

With the configuration above, the default document URLs are:

~~~text
/v3/api-docs/customer
/v3/api-docs/admin
/v3/api-docs/partner
~~~

You can add **packages-to-scan** or **packages-to-exclude** within each group to combine with package filtering. Do not redeclare the same group as a bean if it is already defined via **springdoc.group-configs**; pick one configuration source per group so it stays clear which definition is registered.

## 6. Combining Path Filters with Package Filters

Paths represent URL structure, whereas packages represent controller location in source code. For example, a project might place order controllers in **com.example.order.api** and catalog controllers in **com.example.catalog.api**, while both use the `/api/v1/**` prefix.

You can constrain a group by both conditions:

~~~java
@Bean
public GroupedOpenApi orderV1Api() {
    return GroupedOpenApi.builder()
        .group("order-v1")
        .packagesToScan("com.example.order.api")
        .pathsToMatch("/api/v1/**")
        .pathsToExclude("/api/v1/orders/internal/**")
        .build();
}
~~~

The group picks only controllers in the order package whose endpoints match `/api/v1/**`. The internal branch is further removed via **pathsToExclude**. This reduces the chance that a new controller in another module accidentally shows up in the document merely because its URL shares a prefix.

If a controller moves to another package while keeping the same URL, the package filter can cause the endpoint to disappear from the group. Conversely, if the URL changes while the package stays the same, the path filter may no longer match. Whenever refactoring code layout or API paths, verify both conditions.

## 7. Choosing Between Path Filters and @Hidden

Not every case requires path patterns. If you only need to hide a specific controller or operation, the **@Hidden** annotation or the hidden attribute on an operation annotation can be more readable:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InternalDiagnosticsController {

    @Hidden
    @GetMapping("/api/internal/diagnostics")
    public String diagnostics() {
        return "internal";
    }
}
~~~

Comparison:

| Approach | Best Suited When |
| --- | --- |
| **pathsToMatch / pathsToExclude** | Managing batches of endpoints by URL structure or API group |
| **packagesToScan / packagesToExclude** | Module boundaries are expressed through packages |
| **@Hidden** | Only a single controller or operation needs to be hidden from docs |

Path filtering manages scope at the group level. **@Hidden** expresses intent directly in the endpoint's source code. You can combine them if needed, but keep the rules easy to explain so maintainers know why an endpoint appears or disappears.

## 8. Path Filtering Is Not Endpoint Security

This distinction must be clear: **pathsToExclude** only controls the generated OpenAPI specification content. It does not block HTTP requests to the endpoint, does not replace Spring Security, does not hide the endpoint from someone who already knows the URL, and does not protect data.

For example, excluding `/api/admin/**` from customer documentation does not stop a customer user from calling an admin endpoint. Access rights must still be enforced at runtime by Spring Security, authorization rules, service-level permission checks, or equivalent protection mechanisms.

Similarly, hiding Swagger UI or omitting a path from OpenAPI is not a security measure. If documentation contains internal endpoints, protect both the **/v3/api-docs** endpoint and group URLs according to access policy. Filters only help produce the right documentation for each consumer audience.

## 9. Verifying Filter Results in OpenAPI JSON

After configuring filters, inspect each group's specification directly. Do not rely solely on the application starting up or Swagger UI showing the group name.

For the customer group:

~~~bash
curl -s http://localhost:8080/v3/api-docs/customer
~~~

For the admin group:

~~~bash
curl -s http://localhost:8080/v3/api-docs/admin
~~~

In the JSON response, inspect the **paths** key:

- Included endpoints must be present.
- Endpoints matching exclusions must be absent.
- Endpoints belonging to other groups must not appear unless matched by an include pattern.
- If multiple HTTP methods share the same path, verify that the expected operations remain present.

If **jq** is available, list the paths with:

~~~bash
curl -s http://localhost:8080/v3/api-docs/customer | jq -r '.paths | keys[]'
~~~

Compare the output list against controller mappings. If using a context path, reverse proxy, or custom base path, use the actual URL exposed by the deployment environment.

An integration test suite should include representative endpoints for each case:

| Test Endpoint | Expected in Customer Group |
| --- | --- |
| **/api/orders** | Present |
| **/api/catalog/products** | Present |
| **/api/orders/internal/reconcile** | Absent |
| **/api/admin/users** | Absent |
| **/internal/metrics** | Absent |

Automate verification of critical path sets during builds or in CI. If the API contract changes, tests will catch endpoints added or excluded unexpectedly.

## 10. Common Issues and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Group contains no endpoints | Include pattern does not match path mappings or package config is too narrow | Check full paths combining class-level and method-level mappings; broaden include patterns deliberately |
| Internal endpoint still appears | Exclude pattern does not match exact prefix or misses an actual branch | Open **/v3/api-docs/{group}** and compare exact paths under **paths** |
| Needed endpoint was excluded | A broad exclude pattern covers a valid branch | Narrow the exclude pattern or separate endpoints with clearer path structure |
| Group contains endpoints from unwanted packages | Filtering by path only while multiple modules share a prefix | Combine **packagesToScan** with **pathsToMatch** |
| YAML changed but output did not update | Application has not reloaded or document is cached | Restart the application in development and re-check the docs endpoint |
| Group missing in Swagger UI | Group not registered or UI not configured to list groups | Check **/v3/api-docs/{group}** first, then inspect Swagger UI configuration |
| One path has multiple operations but only one method should be hidden | Path filters operate at the path level, not individual methods | Use **@Hidden**/operation metadata or restructure the endpoint |
| Assuming exclude secures the endpoint | Confusing document filtering with runtime authorization | Configure Spring Security and test HTTP access permissions separately |

## 11. Workflow for Designing Project Filters

When organizing documentation for multiple API groups, follow this sequence:

1. List actual endpoints from controller mappings or from **/v3/api-docs**.
2. Categorize endpoints by consumer audience: public, partner, admin, internal, or actuator.
3. Identify path prefixes representing each group; if paths are shared, identify the corresponding controller packages.
4. Choose configuration scope: application-wide via **springdoc.paths-to-match**/**springdoc.paths-to-exclude**, or per group via **GroupedOpenApi**/**springdoc.group-configs**.
5. Set include patterns for branches to publish and exclude patterns for branches to omit from the group.
6. Create uniquely named groups and inspect the **/v3/api-docs/{group}** endpoints.
7. Write tests asserting that required paths are present and excluded paths are absent.
8. Verify runtime security independently of OpenAPI documentation.

Avoid starting with an overly broad include pattern and only adding exclusions reactively as issues are discovered. Once you have a clear list of endpoints, select the branches to publish first, then add targeted exclusions with clear rationale. This keeps filters maintainable as the project adds new controllers or API versions.

## 12. Pre-Publication Checklist for Document Groups

- [ ] Group names are unique and meaningful to consumers.
- [ ] **pathsToMatch** covers all intended API branches.
- [ ] **pathsToExclude** removes internal or out-of-scope endpoints.
- [ ] Where needed, **packagesToScan** and **packagesToExclude** are combined accurately.
- [ ] No domains, query strings, or incorrect context paths are used in patterns.
- [ ] JSON output at **/v3/api-docs/{group}** has been verified.
- [ ] Expected endpoints appear and excluded endpoints do not appear.
- [ ] Runtime endpoints and Spring Security have been tested independently.
- [ ] Groups do not unintentionally publish the same endpoint.
- [ ] CI validates critical path sets if documentation serves as a release contract.

## 13. Official References

- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — **springdoc.paths-to-match**, **springdoc.paths-to-exclude**, and per-group filtering properties.
- [springdoc-openapi FAQ v2](https://springdoc.org/v2/faq.html) — creating multiple OpenAPI definitions with **GroupedOpenApi**, combining paths and packages, and group document URLs.
- [springdoc-openapi Features v2](https://springdoc.org/v2/features.html) — selecting REST controllers via package or path configuration and the **@Hidden** annotation.
- [Spring Framework — Path Matching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html) — path matching mechanisms in Spring MVC, **PathPatternParser**, and **AntPathMatcher**.
- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html) — URL patterns and declaring controller mappings.

**pathsToMatch** and **pathsToExclude** ensure each OpenAPI specification contains only endpoints within its intended scope. By combining path filters with package filters, clear document groups, and JSON output checks in CI, springdoc-openapi can deliver tailored documentation for customers, partners, and operations teams from a single Spring Boot application.
