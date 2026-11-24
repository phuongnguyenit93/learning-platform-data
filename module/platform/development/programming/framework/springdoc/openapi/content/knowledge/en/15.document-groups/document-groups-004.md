# Filtering with packagesToScan and packagesToExclude

In a Spring Boot application, controllers are typically organized by business domain or functional layer: customers, orders, payments, administration, and internal integrations. When an application exposes multiple API groups, a single OpenAPI document can contain too many endpoints or reveal operations not meant for external integrators. **springdoc-openapi** lets you filter controllers by package using **packagesToScan** and **packagesToExclude**, producing OpenAPI documents with clear boundaries.

These two properties can be configured globally or per document group:

- **springdoc.packages-to-scan** selects packages to scan for the default document.
- **springdoc.packages-to-exclude** excludes packages from global scanning.
- **springdoc.group-configs[n].packages-to-scan** and **packages-to-exclude** configure the package scope of a group declared in application configuration.
- **GroupedOpenApi.Builder.packagesToScan(...)** and **packagesToExclude(...)** configure packages in Java.

Package filtering only determines which controllers are included in documentation. It does not register beans, change URLs, block clients from calling endpoints, or replace Spring Security.

## 1. Why Filter by Package?

Suppose an e-commerce application has this package structure:

~~~text
com.example.shop
├── api
│   ├── customer
│   │   ├── CustomerController.java
│   │   └── AddressController.java
│   ├── order
│   │   └── OrderController.java
│   └── admin
│       └── AdminOrderController.java
├── internal
│   ├── health
│   │   └── InternalHealthController.java
│   └── integration
│       └── PartnerCallbackController.java
└── application
    └── ...
~~~

These controllers may serve different documentation audiences:

- Integrating partners only need customer and order APIs.
- Administrators also need management endpoints.
- Internal endpoints must not appear in public documentation.

If springdoc scans every controller, the default document may expose internal endpoints as well. Package filtering establishes an initial boundary aligned with source code organization.

Package filtering is especially helpful when packages reflect stable module boundaries. If the package layout does not reflect API boundaries, consider using **pathsToMatch** and **pathsToExclude** by URL or combining both filters.

## 2. Distinguishing packagesToScan and packagesToExclude

**packagesToScan** defines which packages are included in scanning. **packagesToExclude** removes packages that should not be published in documentation.

| Property | Purpose | Example |
| --- | --- | --- |
| **packagesToScan** | Select packages containing controllers to document | **com.example.shop.api.customer** |
| **packagesToExclude** | Exclude packages from documentation | **com.example.shop.api.admin** |

You can visualize the selected scope as follows:

1. Start with the controllers that springdoc can discover.
2. Keep controllers in packages selected by **packagesToScan**; if no include list is specified, the default scope can cover all packages.
3. Exclude controllers in packages specified by **packagesToExclude**.
4. If the group also configures URL filters such as **pathsToMatch** or **pathsToExclude**, apply those path conditions as well.

When a package appears in both include and exclude lists, structure the configuration so intent is unambiguous and verify the output on your springdoc version. A maintainable pattern is selecting a parent package as the include scope and excluding unpublished subpackages.

The springdoc v2 property reference notes:

- **springdoc.packages-to-scan** defaults to an asterisk (*).
- **springdoc.packages-to-exclude** defaults to no exclusions.
- The same properties are available inside each **springdoc.group-configs** entry.

Therefore, without package filters configured, the default document typically scans all controller packages discovered by springdoc.

## 3. Package Filtering for the Default Document

You can configure this directly in **application.yml**:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.shop.api.customer
    - com.example.shop.api.order
  packages-to-exclude:
    - com.example.shop.api.admin
    - com.example.shop.internal
~~~

Or using **application.properties**:

~~~properties
springdoc.packages-to-scan=com.example.shop.api.customer,com.example.shop.api.order
springdoc.packages-to-exclude=com.example.shop.api.admin,com.example.shop.internal
~~~

In this example, the default OpenAPI document focuses only on controllers in the customer and order packages while excluding the admin and internal packages.

The default document endpoint is typically:

~~~text
GET /v3/api-docs
~~~

If the application overrides **springdoc.api-docs.path** or uses a context path, use the URL matching that configuration.

Global properties fit when the application only needs one default document scope or when every document shares the same baseline boundary. If each API group has a distinct scope, configure packages per group instead.

## 4. Package Filtering Per Document Group in application.yml

Springdoc supports declaring multiple groups in **springdoc.group-configs**. You do not need to create **GroupedOpenApi** beans when using this configuration style.

Example creating two separate documents for customers and administrators:

~~~yaml
springdoc:
  group-configs:
    - group: customer-api
      display-name: Customer API
      packages-to-scan:
        - com.example.shop.api.customer
        - com.example.shop.api.order
      packages-to-exclude:
        - com.example.shop.api.customer.internal

    - group: admin-api
      display-name: Admin API
      packages-to-scan:
        - com.example.shop.api.admin
      packages-to-exclude:
        - com.example.shop.api.admin.maintenance
~~~

This produces two documents with distinct package scopes:

| Group | Included Packages | Excluded Packages |
| --- | --- | --- |
| **customer-api** | **api.customer**, **api.order** | **api.customer.internal** |
| **admin-api** | **api.admin** | **api.admin.maintenance** |

Per the springdoc v2 property reference, a group's **packages-to-scan** also defaults to an asterisk (*), while **packages-to-exclude** defaults to empty. Consequently, if a group omits package scope, it may include controllers from across the entire application subject to other filters. Explicitly declare include packages for each group when building a narrow-scope document.

Under default settings, each group's document can be accessed at:

~~~text
GET /v3/api-docs/customer-api
GET /v3/api-docs/admin-api
~~~

The group name is used in the URL, so keep it short, stable, and unique. **display-name** serves as the display label in certain integrated UIs; it does not replace the **group** identifier.

You can declare groups with equivalent properties syntax:

~~~properties
springdoc.group-configs[0].group=customer-api
springdoc.group-configs[0].display-name=Customer API
springdoc.group-configs[0].packages-to-scan=com.example.shop.api.customer,com.example.shop.api.order
springdoc.group-configs[0].packages-to-exclude=com.example.shop.api.customer.internal

springdoc.group-configs[1].group=admin-api
springdoc.group-configs[1].display-name=Admin API
springdoc.group-configs[1].packages-to-scan=com.example.shop.api.admin
springdoc.group-configs[1].packages-to-exclude=com.example.shop.api.admin.maintenance
~~~

When using group configs in configuration files, do not also create a **GroupedOpenApi** bean for the same group. Avoid declaring two configuration sources with the same name, which makes document scope difficult to control.

## 5. Package Filtering with GroupedOpenApi in Java

If you prefer configuring groups in Java, create **GroupedOpenApi** beans and pass package lists to the builder:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi customerApi() {
        return GroupedOpenApi.builder()
            .group("customer-api")
            .packagesToScan(
                "com.example.shop.api.customer",
                "com.example.shop.api.order"
            )
            .packagesToExclude(
                "com.example.shop.api.customer.internal"
            )
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin-api")
            .packagesToScan("com.example.shop.api.admin")
            .packagesToExclude(
                "com.example.shop.api.admin.maintenance"
            )
            .build();
    }
}
~~~

In springdoc v2, **GroupedOpenApi** belongs to package **org.springdoc.core.models**. In springdoc v1, its Java package differs; use the import matching your project's major version. Common builder methods include:

- **group(...)**: sets the group name.
- **packagesToScan(...)**: selects packages.
- **packagesToExclude(...)**: excludes packages.
- **pathsToMatch(...)**: selects URL paths.
- **pathsToExclude(...)**: excludes URL paths.
- **build()**: creates the group configuration.

If the application needs dynamic filter conditions or profile-driven configuration, you can construct beans from Spring configuration. Whether you choose application.yml or Java config, maintain one clear source of configuration per group.

## 6. Combining Package Filters with Path Filters

Packages and paths answer two different questions:

- Package filter: in which area of source code is the controller declared?
- Path filter: which URL prefix or pattern does the endpoint match?

Springdoc supports combining both. For example, include only controllers in the customer package and only endpoints under **/api/v1/**:

~~~java
@Bean
GroupedOpenApi customerV1Api() {
    return GroupedOpenApi.builder()
        .group("customer-v1")
        .packagesToScan("com.example.shop.api.customer")
        .pathsToMatch("/api/v1/**")
        .pathsToExclude("/api/v1/internal/**")
        .build();
}
~~~

Or in YAML:

~~~yaml
springdoc:
  group-configs:
    - group: customer-v1
      packages-to-scan:
        - com.example.shop.api.customer
      paths-to-match:
        - /api/v1/**
      paths-to-exclude:
        - /api/v1/internal/**
~~~

A controller must be within the selected package scope and its path must satisfy the URL criteria for an operation to belong to the group. If a controller is in the right package but its URL does not match **paths-to-match**, that operation will not be included in the group. Conversely, a matching path whose controller lies outside the selected packages will not be included either.

Do not pass URL paths such as **/api/customer/** to **packagesToScan**. Those are path patterns and belong in **pathsToMatch**. Packages are Java namespaces, such as **com.example.shop.api.customer**.

## 7. Understanding Package Filter Boundaries

Package filters target the controllers and handlers collected by springdoc. They do not mean every class outside the selected packages disappears from OpenAPI.

For example:

~~~java
package com.example.shop.api.customer;

@RestController
class CustomerController {

    @GetMapping("/api/customers/{id}")
    CustomerView find(@PathVariable String id) {
        return customerService.find(id);
    }
}
~~~

DTOs can reside in a shared package:

~~~java
package com.example.shop.contract.customer;

public record CustomerView(
    String id,
    String displayName
) {}
~~~

When the controller is included in the group, the schema for **CustomerView** still needs to appear because the operation references that type. Package filtering is not a standalone filter for stripping schemas by DTO package.

Similarly, excluding a controller package from documentation does not remove the Spring bean and does not alter the application's component scanning. The controller can still be registered and endpoints remain callable if Spring MVC/WebFlux and security allow it.

## 8. Package Organization Rules for Maintainable Filtering

A clean package layout keeps documentation configuration straightforward:

~~~text
com.example.shop.api
├── public
│   ├── customer
│   ├── order
│   └── catalog
├── partner
│   ├── fulfillment
│   └── payment
├── admin
└── internal
    ├── health
    └── maintenance
~~~

Configuration can target the parent package **com.example.shop.api.public** or individual subpackages. If selecting a parent package, verify whether unintended subpackages are included under your springdoc version's filtering rules; use **packagesToExclude** to explicitly exclude unpublished areas.

Recommended practices:

1. Group controllers by API domain or audience rather than placing every controller in one large boundaryless package.
2. Place internal controllers in a dedicated package so they are easy to exclude from docs.
3. Use full package names with exact casing.
4. Do not rely on package wildcards unless that behavior is confirmed for your library version.
5. Use package filters for source code boundaries and path filters for URL boundaries.
6. Keep configured package lists in sync when moving controllers between packages.

If a single controller contains endpoints for multiple audiences, package filters cannot split methods within the same class by package. In that case, use path filters, split the controller, or apply an appropriate customizer.

## 9. Example: Splitting Documentation by Business Domain

An application with three API domains:

| Domain | Package | Group |
| --- | --- | --- |
| Customer | **com.example.shop.api.customer** | **customer-api** |
| Order | **com.example.shop.api.order** | **order-api** |
| Shipping Partner | **com.example.shop.api.partner.shipping** | **shipping-partner-api** |

Can be configured in application.yml:

~~~yaml
springdoc:
  group-configs:
    - group: customer-api
      display-name: Customer API
      packages-to-scan:
        - com.example.shop.api.customer

    - group: order-api
      display-name: Order API
      packages-to-scan:
        - com.example.shop.api.order

    - group: shipping-partner-api
      display-name: Shipping Partner API
      packages-to-scan:
        - com.example.shop.api.partner.shipping
      packages-to-exclude:
        - com.example.shop.api.partner.shipping.internal
~~~

Each group produces an independent document:

~~~text
/v3/api-docs/customer-api
/v3/api-docs/order-api
/v3/api-docs/shipping-partner-api
~~~

This allows each integrating team to fetch only the contract they need. However, if an operation must appear in multiple documents, you can select the same package in multiple groups or define group scopes using both packages and paths. A controller appearing in multiple documents does not create duplicate runtime endpoints.

## 10. Verifying Package Filtering Results

After configuring filters, restart the application so Spring loads the updated settings. Fetch the default document and each group document:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o default-openapi.json
curl -sS http://localhost:8080/v3/api-docs/customer-api -o customer-openapi.json
curl -sS http://localhost:8080/v3/api-docs/admin-api -o admin-openapi.json
~~~

List the paths in each document:

~~~bash
jq -r '.paths | keys[]' customer-openapi.json
jq -r '.paths | keys[]' admin-openapi.json
~~~

Quickly check the operation count:

~~~bash
jq '[.paths[] | to_entries[]] | length' customer-openapi.json
~~~

Cross-check the results:

- The customer group contains only paths belonging to controllers in the customer package and any other included packages.
- The admin group excludes controllers in excluded packages.
- Shared DTOs still have schemas when operations in the group reference them.
- An endpoint may appear in multiple groups if their include configurations select the same controller.
- The default document and group documents have separate scopes; verify the right URL before concluding a configuration has no effect.

If using a context path, reverse proxy, or customized **springdoc.api-docs.path**, adjust the access URLs accordingly. If the endpoint returns 404, check the group name, API docs configuration, and access permissions for documentation endpoints.

## 11. Automated Testing of Each Group's Boundaries

You can use MockMvc to call a group's documentation endpoint and assert which paths are included or excluded:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiGroupPackageFilterTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void customerGroupContainsOnlyExpectedOperations() throws Exception {
        MvcResult result = mockMvc.perform(get("/v3/api-docs/customer-api"))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode openApi = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );
        JsonNode paths = openApi.path("paths");

        assertThat(paths.has("/api/customers/{id}")).isTrue();
        assertThat(paths.has("/api/admin/users")).isFalse();
    }
}
~~~

The paths in these assertions are hypothetical API examples; replace them with your application's actual paths. Tests should include at least one included endpoint, one endpoint excluded by package, and one endpoint excluded by path if the group uses both filter types.

If the same controller is used across multiple groups, write assertions per group contract rather than assuming each controller appears in only one document.

## 12. Common Mistakes

**Using URL paths as packages.** **packagesToScan** takes Java package names, not **/api/**. Use **pathsToMatch** for URLs.

**Using DTO packages instead of controller packages.** The filter selects which controllers/handlers to document. DTOs referenced by operations will still have schemas generated even if they reside in another package.

**Excluded package still appears in documentation.** Check the actual package of the controller class registered by Spring, verify spelling in configuration, and confirm you are inspecting the configured group rather than the default document.

**Group has no operations.** Check whether **packages-to-scan**, **packages-to-exclude**, **paths-to-match**, and **paths-to-exclude** are filtering out all controllers. Verify that Spring recognizes the controller as a REST endpoint.

**Global configuration does not adjust groups as expected.** When each group needs its own scope, declare packages directly on **springdoc.group-configs[n]** or on the **GroupedOpenApi** builder.

**Duplicate group declarations in YAML and Java.** Choose one declaration method per group, assign unique names, and avoid defining two configuration sources for the same scope.

**Hiding documentation and assuming endpoints are locked down.** Package filters only affect OpenAPI output. Use Spring Security, a gateway, or authorization mechanisms to protect actual endpoints.

**Controller moved to another package without docs updating as expected.** Sync package include/exclude lists, restart the application, and check the right documentation endpoint.

## 13. Checklist for Configuring packagesToScan and packagesToExclude

- [ ] Identify the actual packages containing controllers to publish.
- [ ] Select packages to scan with **packagesToScan**.
- [ ] Exclude unpublished packages with **packagesToExclude**.
- [ ] Use global configuration for the default document or per-group configuration for individual groups.
- [ ] Choose application.yml, application.properties, or **GroupedOpenApi** as a single clear configuration source.
- [ ] Use **pathsToMatch**/**pathsToExclude** when URL filtering is needed.
- [ ] Assign unique and stable group names.
- [ ] Never treat package filtering as an endpoint security mechanism.
- [ ] Inspect **/v3/api-docs** and **/v3/api-docs/{group}** after changes.
- [ ] Write tests verifying included and excluded operations.

## 14. Conclusion

**packagesToScan** and **packagesToExclude** let you divide OpenAPI documentation along controller package boundaries. You can apply filters to the default document, configure them per group in **springdoc.group-configs**, or use the **GroupedOpenApi** builder. When you need to constrain by both source code and URL, combine package filters with path filters. Finally, verify each group's **/v3/api-docs** endpoint to ensure documentation accurately reflects the API scope consumers need to integrate.

## 15. References

- [Springdoc OpenAPI v2 — Core Properties Reference](https://springdoc.org/v2/core-properties.html): defaults and semantics of **springdoc.packages-to-scan**, **springdoc.packages-to-exclude**, and per-group package properties.
- [Springdoc OpenAPI v2 — FAQ](https://springdoc.org/v2/faq.html): creating multiple OpenAPI definitions by package and path using **GroupedOpenApi** or **springdoc.group-configs**.
- [Springdoc OpenAPI v2 — Documentation](https://springdoc.org/v2/): configuring springdoc for Spring Boot 3 applications.
