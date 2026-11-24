# Dividing Contracts by Business Domain or Target Audience

When a Spring Boot application has many controllers, multiple business domains, or diverse groups of integrators, a single OpenAPI document can become too large and difficult to navigate. Users who only need the order API might have to scroll through hundreds of operations for billing, administration, and operations. Some endpoints are also intended exclusively for partners or internal systems and are inappropriate to expose in public documentation.

springdoc-openapi supports splitting an application into multiple OpenAPI documents using GroupedOpenApi. Each group is a contract generated from a selected set of controllers or paths, and can have its own descriptive metadata and customizations. Grouping keeps documentation aligned with its audience, easier to navigate, and simpler to manage across its lifecycle.

## 1. Why Split OpenAPI Documentation?

Grouping is useful when you have one or more of the following needs:

- Separate business domains such as catalog, orders, billing, and identity so readers only see relevant operations.
- Provide dedicated contracts for each integrator audience, such as public clients, partners, and internal operations teams.
- Differentiate APIs by version or release stage when the contracts genuinely differ.
- Reduce document complexity, making it easier to find endpoints and review changes.
- Apply separate metadata, descriptions, tags, or release workflows to each contract.
- Control which documents are published on a developer portal or provided to a specific user group.

For example, an e-commerce system might have:

| Document Group | Target Audience | Contents |
| --- | --- | --- |
| public-api | Web/mobile applications and integrating customers | View products, create orders, track orders |
| partner-api | Shipping or sales partners | Query authorized orders, update delivery status |
| admin-api | Administrative staff | Manage catalogs, process refunds, configure system settings |
| internal-api | Internal services | Data synchronization and operational tasks |

This is a way to organize documentation contracts. Actual access control for each endpoint is still enforced by Spring Security, the gateway, and application policies.

## 2. How Do Document Groups Differ from Tags and Packages?

These three mechanisms serve different roles:

| Mechanism | Scope | Purpose |
| --- | --- | --- |
| GroupedOpenApi | Entire generated OpenAPI document | Select a set of operations to form a separate contract |
| Tag | Inside a single document | Group operations by topic for easier navigation |
| Java package | Source code structure | Organize controllers and Java components |

For example, the public-api group might contain the Products, Orders, and Accounts tags. The Products tag further groups operations for viewing, searching, and filtering products. One package can contain multiple controllers; one group can pull controllers from multiple packages if they belong to the same contract.

There is no need to create a group just because there is a new controller or tag. A group should represent a contract boundary that is meaningful to API consumers.

## 3. Defining Group Boundaries by Business Domain

Splitting by business domain works well when parts of the system have relatively independent functionality and data models.

For example:

- Catalog: products, categories, attributes, and visible inventory.
- Orders: shopping carts, orders, statuses, and order history.
- Billing: payments, invoices, and refunds.
- Identity: accounts, profiles, and access permissions.

One implementation approach is to organize controllers by package:

~~~text
com.example.shop.api
  catalog
    ProductController.java
    CategoryController.java
  orders
    OrderController.java
    CartController.java
  billing
    PaymentController.java
    InvoiceController.java
~~~

When packages accurately reflect business boundaries, you can create one group per domain. This keeps document groups less dependent on path naming, though it requires that packages are not mixed across domains.

If controllers are organized by technical layer rather than domain—for example, all controllers reside in a single package—you can use pathsToMatch and pathsToExclude to select operations by URL. In practice, you can combine package and path filtering to clarify boundaries.

## 4. Defining Boundaries by Target Audience

A single business domain may serve multiple user groups with different permission levels and needs. In that case, splitting documentation by audience can be more useful than dividing purely by package.

For example:

| Audience | Documentation Needs | Appropriate Operations |
| --- | --- | --- |
| Public client | Integrate basic flows | View products, create orders, read order status |
| Partner | Integrate partner-coordinated flows | Accept assigned orders, confirm delivery, submit reconciliation codes |
| Administrator | Administer data and configuration | Create categories, lock accounts, adjust statuses |
| Internal service | Inter-service communication | Synchronization, event processing, internal queries |

Do not include endpoints in a group based solely on role names. Identify the exact set of operations that the audience is allowed to know about and needs to use. An endpoint can appear in multiple groups if multiple audiences require that contract; this does not grant additional permissions to call the endpoint.

## 5. Declaring GroupedOpenApi with Java Configuration

In springdoc-openapi 2.x and 3.x, GroupedOpenApi is in the org.springdoc.core.models package. You can create a bean for each group:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .packagesToScan(
                "com.example.shop.api.catalog",
                "com.example.shop.api.orders"
            )
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-api")
            .packagesToScan("com.example.shop.api.partner")
            .pathsToMatch("/api/partner/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin-api")
            .packagesToScan("com.example.shop.api.admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
~~~

Each bean creates a separate document. The group name is the identifier used in the URL to retrieve the document, so choose stable, readable names without spaces or characters requiring URL encoding.

In springdoc 1.x, the package for GroupedOpenApi differs from newer releases. Older projects typically use org.springdoc.core.GroupedOpenApi. Use the import matching your installed dependency version; do not copy imports across major versions without checking.

## 6. Filtering by Package and Path

GroupedOpenApi supports common filters:

| Filter | Effect |
| --- | --- |
| packagesToScan | Include only controllers in the specified packages |
| packagesToExclude | Exclude controllers in the specified packages |
| pathsToMatch | Include only paths matching the patterns |
| pathsToExclude | Exclude paths matching the patterns |

For example, to publish only public catalog endpoints while excluding experimental endpoints:

~~~java
@Bean
GroupedOpenApi catalogPublicApi() {
    return GroupedOpenApi.builder()
        .group("catalog-public")
        .packagesToScan("com.example.shop.api.catalog")
        .pathsToMatch("/api/catalog/**")
        .pathsToExclude(
            "/api/catalog/internal/**",
            "/api/catalog/debug/**"
        )
        .build();
}
~~~

When declaring multiple filters, treat them as conditions that narrow the set of operations: the controller must fall within the selected package scope and the path must match the path filters. Exact matching behavior also depends on configuration and library version; always verify the actual contents of the group document.

Path patterns should be based on the URL mapping exposed by Spring, not on Java method names. If a controller has a context path or a deployment-layer prefix, inspect the paths in the OpenAPI output to choose the right patterns. Document filters do not alter the runtime URL of any controller.

## 7. Splitting Documentation with Multiple GroupedOpenApi Beans

You can create multiple groups by domain:

~~~java
@Bean
GroupedOpenApi ordersApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .packagesToScan("com.example.shop.api.orders")
        .build();
}

@Bean
GroupedOpenApi billingApi() {
    return GroupedOpenApi.builder()
        .group("billing")
        .packagesToScan("com.example.shop.api.billing")
        .build();
}
~~~

Or create groups by audience:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/catalog/**", "/api/orders/**")
        .pathsToExclude("/api/orders/{orderId}/internal/**")
        .build();
}

@Bean
GroupedOpenApi operationsApi() {
    return GroupedOpenApi.builder()
        .group("operations")
        .pathsToMatch("/api/**/admin/**", "/api/operations/**")
        .build();
}
~~~

These path examples only illustrate operation selection rules. Before using them, cross-check against your actual controller mappings and avoid letting a broad pattern accidentally pull internal endpoints into public documentation.

A controller can appear in multiple groups if it satisfies the filters of those groups. Conversely, a controller that matches no group filter may still appear in the default document if the application configuration continues to expose a default OpenAPI document.

## 8. Document URLs for Each Group

With default paths, springdoc typically serves:

| URL | Contents |
| --- | --- |
| /v3/api-docs | Default OpenAPI document of the application |
| /v3/api-docs/public-api | Document for the public-api group |
| /v3/api-docs/partner-api | Document for the partner-api group |
| /v3/api-docs/admin-api | Document for the admin-api group |
| /swagger-ui.html | Swagger UI entry point |

If you have changed springdoc.api-docs.path, the URLs of the default document and all groups will change according to that prefix. Check your application configuration instead of assuming /v3/api-docs is always used.

Swagger UI can display a list of registered groups so users can select the document to view. This list is provided through the Swagger UI configuration generated by springdoc. If a group does not appear, check whether the GroupedOpenApi bean is initialized by Spring, whether the group name is unique, and whether the Swagger UI config endpoint returns the expected list.

You can fetch each document with curl:

~~~bash
curl -sS http://localhost:8080/v3/api-docs/public-api
curl -sS http://localhost:8080/v3/api-docs/partner-api
curl -sS http://localhost:8080/v3/api-docs/admin-api
~~~

If the application sits behind a context path, reverse proxy, or API gateway, prepend the corresponding public prefix to the URL.

## 9. Customizing Metadata Per Group

Each group document may require its own title, version, or description. You can attach an OpenApiCustomizer directly to GroupedOpenApi:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi billingApi() {
    return GroupedOpenApi.builder()
        .group("billing")
        .packagesToScan("com.example.shop.api.billing")
        .addOpenApiCustomizer(openApi ->
            openApi.info(new Info()
                .title("Billing API")
                .version("v1")
                .description("API contract for payment operations.")
            )
        )
        .build();
}
~~~

A customizer attached on the builder adjusts the corresponding group's document. This is the right place to change metadata or add information that applies only to one contract.

If you need a customization applied across all documents, you can use the global customizer mechanism appropriate for your springdoc version. Distinguish global customizers from group-specific customizers to avoid overwriting metadata of other groups.

## 10. Groups Do Not Replace Endpoint Security

This is especially important to note when creating public-api and internal-api. Omitting an endpoint from documentation does not mean the endpoint is disabled or protected.

For example:

- pathsToExclude only removes operations from the generated document.
- packagesToScan only restricts which controllers are included in the group contract.
- Users can still call the endpoint URL if the application and gateway allow it.
- OpenAPI documents can also leak path names, schemas, or internal workflows if published to the wrong audience.

Therefore, combine:

1. GroupedOpenApi to generate the right contract for each audience.
2. Spring Security to authenticate and authorize endpoints.
3. A gateway or reverse proxy to control network access if needed.
4. Security schemes in OpenAPI to describe how clients authenticate.
5. Separate access permissions for documentation endpoints if a contract is not public.

Do not use hiding endpoints from Swagger UI as a security measure. Test direct requests to internal endpoints using an unauthorized identity to confirm the server returns 401 or 403 per policy.

## 11. Grouping by API Version

You can create groups for API versions if the application genuinely serves multiple distinct contracts, such as /api/v1/** and /api/v2/**:

~~~java
@Bean
GroupedOpenApi apiV1() {
    return GroupedOpenApi.builder()
        .group("api-v1")
        .pathsToMatch("/api/v1/**")
        .build();
}

@Bean
GroupedOpenApi apiV2() {
    return GroupedOpenApi.builder()
        .group("api-v2")
        .pathsToMatch("/api/v2/**")
        .build();
}
~~~

The group names api-v1 and api-v2 only identify two documents. They do not automatically create endpoint versioning and do not alter routes. The application must implement actual mapping/versioning, manage compatibility, and maintain a separate deprecation policy.

If an API uses header versioning or media type versioning instead of path versioning, you may need appropriate filters or customizers to separate contracts. Verify that each group contains only operations of the intended version and that schemas are not mixed across versions.

## 12. When Should You Not Split into Groups?

Avoid over-splitting if groups would only differ by sorting or tags. Too many documents make it hard for users to know which one to open and increase maintenance overhead.

Keep a single document and use tags when:

- The API shares the same user audience and access policy.
- Operations only need topical categorization.
- There are no differences in contract, lifecycle, or publishing permissions.
- Integrators frequently need to view the entire API within a single workflow.

Create separate groups when there are genuine differences in domain, audience, version, metadata, publishing permissions, or release process. A good boundary is one where consumers immediately understand why a separate document exists.

## 13. Verifying Each Group's Contents

After configuring the beans, verify each OpenAPI endpoint:

~~~bash
# Public group document
curl -sS http://localhost:8080/v3/api-docs/public-api

# Partner group document
curl -sS http://localhost:8080/v3/api-docs/partner-api

# Admin group document
curl -sS http://localhost:8080/v3/api-docs/admin-api
~~~

Check each document:

1. Are the title, version, and description appropriate for the target audience?
2. Do paths contain only the expected operations?
3. Did any internal or experimental endpoints slip in by mistake?
4. Are schemas, parameters, request bodies, and responses complete?
5. Do security schemes and security requirements fit the group?
6. Do all $refs point to components that exist within that group's document?
7. Does Swagger UI list the groups and open the right document?
8. Are runtime endpoints genuinely protected independently of documentation visibility?

You can write integration tests that fetch each group's OpenAPI document and assert on key paths. This catches cases where a new controller accidentally leaks into public docs or an endpoint is dropped from partner docs after a package or path refactor.

Example of inspecting contents with jq:

~~~bash
curl -sS http://localhost:8080/v3/api-docs/public-api \
  | jq -r '.paths | keys[]'
~~~

If jq is unavailable, load the JSON inside a test and inspect the paths object using your project's JSON library.

## 14. Common Issues

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Group does not appear in Swagger UI | Bean not picked up by component scan or group name misconfigured | Check @Configuration, bean definition, and the swagger-config endpoint |
| Group has no operations | packagesToScan or pathsToMatch does not match actual controllers/paths | Inspect packages and paths in the default document |
| Internal endpoint appears in public-api | Path pattern too broad or shared package | Narrow filters and write tests against the path list |
| An operation appears in multiple groups | Group filters overlap | Decide whether overlap is intentional or needs exclusion |
| Renaming a group breaks old URLs | Group name is part of the document URL | Treat group names as a contract endpoint |
| Document returns 401/403 | Security matcher blocks docs endpoints | Configure documentation access permissions per audience |
| Hidden endpoint is still callable | Groups only filter docs, not lock down endpoints | Protect routes using Spring Security or a gateway |
| Group uses wrong title/version | Default metadata or customizer override | Customize per group and verify each generated document |

## 15. Workflow for Designing Document Groups

When splitting an application into multiple OpenAPI contracts:

1. List the business domains, target audiences, and API versions being served.
2. Determine who needs to read each contract and which operations belong in that scope.
3. Choose boundaries based on packages, paths, or a combination of both.
4. Assign stable, clear, and unique group names.
5. Declare each GroupedOpenApi bean, its filters, and group-specific metadata if needed.
6. Verify each group's document URL and the generated list of operations.
7. Configure Spring Security or gateway rules independently of document filters.
8. Add tests to guard group boundaries when controllers or paths change.

Dividing documentation by business domain or audience gives each integrator group a focused, usable contract. Once boundaries are clearly defined, GroupedOpenApi lets you generate distinct documents from the same application while maintaining a single unified controller codebase.

## References

- [springdoc-openapi – Multiple OpenAPI Definitions / GroupedOpenApi](https://springdoc.org/)
- [springdoc-openapi – FAQ and Configuration Properties](https://springdoc.org/faq.html)
- [OpenAPI Specification – OpenAPI Object](https://spec.openapis.org/oas/latest.html#openapi-object)
- [Spring Boot Reference – Auto-configuration and component scanning](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Security – Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
