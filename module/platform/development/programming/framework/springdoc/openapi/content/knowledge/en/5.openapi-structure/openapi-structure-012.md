# Distinguishing `info.version` from the OpenAPI Version and Route Version

In a Spring Boot project using `springdoc-openapi`, the phrase "API version" can refer to several different concepts. The `openapi` field at the top of the document states which version of the OpenAPI Specification the document conforms to. The `info.version` field describes the version of the OpenAPI document. Meanwhile, the route version is the convention the application uses to route requests to a specific API contract or implementation, such as `/api/v1/orders`.

These three values can change independently. Upgrading the OpenAPI Specification version does not automatically create a `/v2` endpoint; changing `info.version` does not automatically alter controllers; and adding a `/api/v2` route does not require switching the document to OpenAPI 3.1. Understanding this boundary helps you manage contracts, generate clients, and release APIs without misleading tools or integrators.

## 1. Three Version Concepts with Different Purposes

| Location or Concept | What Does It Describe? | Examples | What Determines It |
|---|---|---|---|
| `openapi` | Version of the OpenAPI language/specification used to express the document | `3.0.3`, `3.1.0` | The OpenAPI version output by the doc generator |
| `info.version` | Version of the OpenAPI document | `1.4.0`, `2026.11` | Development team managing document versions |
| Route version | Contract variant chosen when a client calls the API | `/api/v1/orders`, `/api/v2/orders` | Routing design and application implementation |

Besides these three concepts, a project also has versions for the application, Maven/Gradle artifacts, Spring Boot, Springdoc, and Swagger UI. Those versions relate to building and operations, and cannot substitute for the three fields or conventions in the table above.

## 2. The `openapi` Field: Version of the OpenAPI Specification

An OpenAPI document starts with the `openapi` field, for example:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths: {}
```

The value `3.1.0` states that the document is written according to OpenAPI Specification version 3.1.0. It defines the syntax, object structures, data types, and rules that validators, parsers, Swagger UI, or client generators must understand.

Specification versions can differ in schema expressiveness, how JSON Schema is referenced, supported keywords, and document-processing rules. Therefore, tools reading the document must be compatible with the declared specification version.

`openapi` is not the service's release version. For example, a team can upgrade a document from OpenAPI 3.0.3 to 3.1.0 to use newer specification capabilities while `/api/v1/...` routes and API behavior stay unchanged. Conversely, a team can release `/api/v2/...` while staying on OpenAPI 3.0.3 if the schemas and features used remain compatible with 3.0.3.

In a Springdoc application, the specification version is emitted by the library version and corresponding configuration. Avoid manually editing the `openapi` field in the output JSON/YAML to force a version change. If you need a different specification version, check support in the Springdoc branch in use, the official configuration for that branch, and compatibility with downstream tools.

## 3. The `info.version` Field: Version of the OpenAPI Document

`info.version` is a required field in the Info Object. By OpenAPI's definition, it represents the version of the OpenAPI document and differs from both the OpenAPI Specification version and the API implementation version.

Example:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: 2026.11
  description: Contract document for the order service.
paths: {}
```

Here:

- `openapi: 3.1.0` states that the document uses OpenAPI Specification 3.1.0 syntax.
- `info.version: 2026.11` is the version of the published OpenAPI document.
- Neither of these fields declares that the application must route requests to `/api/v1` or `/api/v2`.

In practice, many teams adopt the convention of matching `info.version` with the published API release version, such as `1.2.0`. This is a helpful management convention because readers can easily correlate the documentation with the corresponding release. However, the specification does not require this value to match the route version or the running binary version.

A document may have its descriptions, examples, contact info, or schema annotations updated without changing API behavior. A team may bump the document version to record that update, or keep `info.version` unchanged if policy only bumps it when the API contract changes. What matters is defining a consistent rule and communicating how to read it to documentation users.

### Setting `info.version` with Springdoc

You can declare document metadata using annotations:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.4.0",
        description = "Order management API"
    )
)
class OpenApiMetadataConfiguration {
}
```

Or declare an OpenAPI model bean:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI orderApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Order API")
                .version("1.4.0")
                .description("Order management API"));
    }
}
```

Both approaches add document-level metadata. Pick the one that fits the project structure and avoid declaring two competing `Info` sources. You can manage the version value in build metadata or application configuration to avoid editing strings in multiple places, while ensuring the value packaged into the document reflects the intended release version.

## 4. Route Version: How the Application Selects an API Contract

The route version determines which API variant the client is invoking. It is part of HTTP and routing design. It can be expressed in several ways, most commonly by putting the version in the URL path.

Example of two routes:

```java
@RestController
class OrderV1Controller {

    @GetMapping("/api/v1/orders/{id}")
    OrderV1Response getOrder(@PathVariable Long id) {
        // Handle according to v1 contract
        return orderService.getV1(id);
    }
}

@RestController
class OrderV2Controller {

    @GetMapping("/api/v2/orders/{id}")
    OrderV2Response getOrder(@PathVariable Long id) {
        // Handle according to v2 contract
        return orderService.getV2(id);
    }
}
```

An application can maintain both routes during a transition period so older clients continue working while newer clients migrate to v2. Controllers may share internal services or domain models, while DTOs and response mappings must accurately reflect each version's contract.

### Common Versioning Strategies

| Strategy | Request Example | How Spring Can Route | Considerations |
|---|---|---|---|
| URI/path versioning | `/api/v1/orders` | `@RequestMapping("/api/v1/orders")` | Visible, easy to cache, and easy to distinguish in logs |
| Header versioning | `X-API-Version: 2` | Mapping via `headers` or custom routing logic | URL stays unchanged, yet clients must send the right header |
| Media type versioning | `Accept: application/vnd.example.order-v2+json` | Mapping via `produces` or content negotiation | Expresses version via content representation; requires clear media type conventions |

Header-based mapping example:

```java
@RestController
@RequestMapping("/api/orders")
class VersionedOrderController {

    @GetMapping(value = "/{id}", headers = "X-API-Version=1")
    OrderV1Response getV1(@PathVariable Long id) {
        return orderService.getV1(id);
    }

    @GetMapping(value = "/{id}", headers = "X-API-Version=2")
    OrderV2Response getV2(@PathVariable Long id) {
        return orderService.getV2(id);
    }
}
```

This example illustrates Spring MVC mapping conditions. In real systems, clearly define behavior when clients omit the header, send an unsupported version, or send conflicting values. Return structured errors and document the rules in the API documentation.

No single strategy fits every system. URI versioning is usually easy to observe and implement; header or media type versioning may suit existing integration conventions. What matters is that the chosen version has clear rules, is tested, and is reflected in the OpenAPI contract.

## 5. Relationship Between `servers`, `paths`, and Route Version

In OpenAPI, `servers` describes the base URL clients use to call the API; `paths` describes paths relative to that server URL. If the version lives in the path, it usually belongs in `paths`.

Example:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: 2.0.0
servers:
  - url: https://api.example.com
paths:
  /api/v2/orders/{id}:
    get:
      summary: Get order by ID
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Order found
```

In the example, `https://api.example.com` is the server URL and `/api/v2/orders/{id}` is the path. Clients combine the two to build the request URL. `info.version: 2.0.0` is the document version; the route version is `v2` in the path.

Avoid placing `/api/v2` in both `servers.url` and `paths` unless intentional, because clients may combine them into `/api/v2/api/v2/...`. When the application runs behind a reverse proxy or context path, verify that the generated server URL and paths match the public URL.

With header versioning, `paths` may stay unchanged while operations must declare the corresponding header parameter or media types so clients know how to select the contract. Documentation must fully describe routing conditions; otherwise, clients see only one URL and cannot tell how to request the desired version.

## 6. One Route Version Can Have Many Documentation Updates

Not every documentation update requires creating a new route version. For example, API v1 may receive improved descriptions, examples, existing error responses, or clarified field formats without breaking backward-compatible behavior. In that case, the team can publish a new documentation version while continuing to serve the `/api/v1` route.

Conversely, a breaking compatibility change usually warrants a clearly announced API versioning strategy. Examples:

- API v1 returns `customerName` as a string; v2 changes it to a multi-property `customer` object.
- API v1 accepts a field optionally or leniently; v2 tightens validation rules so old requests become invalid.
- API v1 returns status codes or error payloads clients rely on; v2 alters how responses are structured.
- API v1 assigns one meaning to a parameter; v2 changes the unit or interpretation of that value.

Such changes require client impact analysis. Two routes can run side by side or follow the chosen versioning strategy so clients migrate on a clear roadmap. Merely bumping `info.version` does not route old requests to a new implementation and does not preserve compatibility.

## 7. Managing Multiple Route Versions with Grouped Documents

Springdoc can generate multiple OpenAPI documents using `GroupedOpenApi`. Groups split documentation by endpoint scope, package, or other filter criteria. Example:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiVersionDocumentation {

    @Bean
    GroupedOpenApi orderV1Docs() {
        return GroupedOpenApi.builder()
            .group("orders-v1")
            .pathsToMatch("/api/v1/**")
            .build();
    }

    @Bean
    GroupedOpenApi orderV2Docs() {
        return GroupedOpenApi.builder()
            .group("orders-v2")
            .pathsToMatch("/api/v2/**")
            .build();
    }
}
```

Grouped documentation endpoints typically look like:

```text
/v3/api-docs/orders-v1
/v3/api-docs/orders-v2
```

You can configure Swagger UI to select documents:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders API v1
        url: /v3/api-docs/orders-v1
      - name: Orders API v2
        url: /v3/api-docs/orders-v2
    urls-primary-name: Orders API v2
```

A group name only names the generated document; it does not create the corresponding route or change controller mappings. For instance, declaring group `orders-v2` will not make `/api/v2/orders` appear if the application lacks a matching controller or handler.

If each group's document needs a different `info.version`, configure per-group metadata using the customizer mechanism suited to your Springdoc version. Do not assume the group name is automatically copied into `info.version` or that Springdoc infers the API release version from `/v2` in the URL.

## 8. Conventions for Setting `info.version`

OpenAPI defines `info.version` as a string. Development teams may use Semantic Versioning, calendar releases, or another internal convention. If choosing SemVer, clarify whether the version applies to the document, the API contract, or the API release according to organizational policy.

A common practice is synchronizing `info.version` with the published API contract version:

| Value | Interpretation Under Team Convention | Example |
|---|---|---|
| `1.0.0` | First published contract release | API v1 launch |
| `1.1.0` | Backward-compatible additions | Added endpoint or optional field |
| `1.1.1` | Documentation fixes or clarifications without contract changes per team policy | Fixed wrong example or description |
| `2.0.0` | Breaking compatibility changes | Released new contract requiring client updates |

This is an illustrative convention, not an OpenAPI requirement. If the organization needs to track document revisions separately from API versions, `info.version` can track the document revision while the API version is noted in `description`, an extension such as `x-api-version`, or another agreed metadata field. When doing so, keep the presentation clear so users do not get confused.

Do not mechanically use Springdoc's library version as `info.version`. For example, `springdoc-openapi` `2.x` is the documentation-generator library version; it does not mean the Order API service itself is at version `2.x`.

## 9. Scenarios Where the Three Versions Change Independently

| Scenario | `openapi` | `info.version` | Route | Meaning |
|---|---|---|---|---|
| Upgrading library/document representation | `3.0.3` → `3.1.0` | Can stay `1.4.0` | Keep `/api/v1` | Upgraded specification version; API retains existing contract |
| Editing documentation content | Keep `3.1.0` | `1.4.0` → `1.4.1` per convention | Keep `/api/v1` | New document revision; routing unchanged |
| Releasing a new API route | Can stay `3.1.0` | E.g. `2.0.0` | Add `/api/v2` | New route contract; spec keeps the same OpenAPI version |
| Upgrading both spec and contract | `3.0.3` → `3.1.0` | `1.4.0` → `2.0.0` | `/api/v1` and `/api/v2` coexist | Changed both documentation and API contract axes together |

The key point is recording the reason for each change. A commit changing `openapi` may only aim to adopt a newer schema dialect; a commit changing routes may target new clients; a commit changing `info.version` may be solely a documentation revision. Reviews should evaluate each item by its exact impact.

## 10. Verifying Consistency Between Documentation and Routes

When releasing an API version, inspect three separate layers:

1. **Specification:** the `openapi` field has a version supported by the team's validator and tools; document structure is valid.
2. **Metadata:** `info.version` follows team conventions and aligns with release notes or release artifacts.
3. **Routing:** routes actually exist, requests reach the right implementation, and documentation accurately states the paths, headers, or media types used to select versions.

Example testing actual endpoints:

```bash
curl -i http://localhost:8080/api/v1/orders/42
curl -i http://localhost:8080/api/v2/orders/42
```

If using header versioning:

```bash
curl -i -H "X-API-Version: 1" http://localhost:8080/api/orders/42
curl -i -H "X-API-Version: 2" http://localhost:8080/api/orders/42
```

Then fetch the corresponding documents:

```bash
curl http://localhost:8080/v3/api-docs/orders-v1
curl http://localhost:8080/v3/api-docs/orders-v2
```

Do not inspect only `info.version` in JSON and conclude the route is implemented. Nor should you only call a route successfully and assume the documentation accurately reflects requests and responses. Cross-check both sides.

## 11. Common Misconceptions

| Misconception | Reality |
|---|---|
| `openapi: 3.1.0` means the API is at v3.1 | That is the OpenAPI Specification version |
| `info.version: 2.0.0` automatically creates route `/v2` | That is document metadata; routes must be implemented separately |
| Changing `/api/v1` to `/api/v2` makes Springdoc auto-bump `info.version` | Springdoc should not be treated as an automatic API release version manager |
| Group name `v2` equals route v2 | Groups only filter and name documents; controllers must supply routes |
| Upgrading Springdoc from `2.x` to `3.x` upgrades the application's API | That is a library version; evaluate spec and runtime impacts separately |
| `info.version` must always equal the version in the URL | That may be a project convention, not a mandatory OpenAPI requirement |

## 12. Version Management Checklist

- [ ] Distinguished the `openapi` field from `info.version` in the document.
- [ ] Explicitly defined whether `info.version` tracks doc revisions or aligns with the API contract version.
- [ ] Selected a route versioning strategy: URI, header, or media type.
- [ ] Controllers and mappings actually implement every published route version.
- [ ] `servers` and `paths` combine into valid URLs in deployment environments.
- [ ] Grouped docs filter the right endpoints without confusing group names with route versions.
- [ ] Swagger UI serves the right document for each supported API version.
- [ ] Validators and client generators are compatible with the OpenAPI version in the document.
- [ ] Breaking changes have clear release, migration, and deprecation plans.
- [ ] Tested both live endpoints and the exported OpenAPI documentation.

When all three versioning axes are managed cleanly, teams can upgrade specification formats, update document revisions, and release new API routes on independent schedules. `openapi` tells tools how to parse the document, `info.version` identifies the published document version, and route versions determine which contract handles incoming requests. Springdoc documents implemented routes; the team's release workflow keeps metadata, documentation, and API behavior consistent.
