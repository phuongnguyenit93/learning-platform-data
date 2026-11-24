# Distinguishing Listing Multiple Specifications from Merging Them into One

When a system has multiple API groups or multiple microservices, Swagger UI can display multiple OpenAPI documents for users to choose from. Displaying multiple documents in a single interface **does not turn them into a single unified specification**. If you need a combined contract for an API Gateway, you must run a merge step to produce a new OpenAPI document.

With Spring Boot and `springdoc-openapi`, three organizational approaches are common:

1. **Splitting groups within one application** using `GroupedOpenApi`: each group generates its own OpenAPI document.
2. **Listing multiple documents in Swagger UI** using `springdoc.swagger-ui.urls`: users choose one document to view; the documents remain independent.
3. **Merging documents** using an OpenAPI merge tool: corresponding paths, components, and metadata are combined into one new OpenAPI document.

Choosing the right approach keeps API boundaries clear and avoids creating an unintended monolithic document or mistakenly assuming a Swagger UI dropdown constitutes an API Gateway contract.

## 1. Three concepts with different outcomes

| Approach | Input | Output | When Suitable |
|---|---|---|---|
| `GroupedOpenApi` | Controllers, DTOs, and configuration in one Spring Boot application | Multiple separate OpenAPI documents, each with its own group name and URL | Monolith with public/admin/internal APIs or multiple bounded contexts. |
| Swagger UI `urls` | Multiple independent OpenAPI URLs, within the same app or across services | One Swagger UI with a document selector list | Developer portal browsing APIs across multiple services. |
| Merge OpenAPI | Multiple OpenAPI JSON/YAML files | One consolidated OpenAPI document | Gateway or facade publishing a single unified API contract. |

Key points:

- Grouping determines which operations belong to which document.
- Listing determines which documents Swagger UI lets users choose from.
- Merging produces a new document containing the combined operations.

## 2. Splitting multiple documents with `GroupedOpenApi`

`GroupedOpenApi` lets you partition APIs by package scan, path matching, or a combination of both. Each group must have a unique name. Springdoc serves documents by default at:

    /v3/api-docs/{groupName}

Example of a Catalog application with product management APIs and admin APIs:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi catalogApi() {
        return GroupedOpenApi.builder()
                .group("catalog")
                .pathsToMatch("/api/catalog/**")
                .build();
    }

    @Bean
    GroupedOpenApi catalogAdminApi() {
        return GroupedOpenApi.builder()
                .group("catalog-admin")
                .pathsToMatch("/api/admin/catalog/**")
                .build();
    }
}
~~~

The application exposes two independent documents:

| Group | URL |
|---|---|
| `catalog` | `/v3/api-docs/catalog` |
| `catalog-admin` | `/v3/api-docs/catalog-admin` |

The `catalog` group does not automatically include `catalog-admin` operations. If a path matches both groups' criteria, that operation can appear in both documents. That is the result of two independent filters, not merging.

### 2.1. Splitting groups by package

When packages reflect module boundaries, you can use `packagesToScan`:

~~~java
@Bean
GroupedOpenApi billingApi() {
    return GroupedOpenApi.builder()
            .group("billing")
            .packagesToScan("com.example.billing.api")
            .build();
}
~~~

You can combine packages and paths:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
            .group("partner")
            .packagesToScan(
                    "com.example.catalog.api",
                    "com.example.billing.api"
            )
            .pathsToMatch("/partner/**")
            .build();
}
~~~

Package and path conditions help scope each document's operations. Base rules on the API structure the team intends to publish, not solely on Java folder layout.

### 2.2. Declaring groups in `application.yml`

For simple configurations, you can use `springdoc.group-configs`:

~~~yaml
springdoc:
  group-configs:
    - group: catalog
      paths-to-match:
        - /api/catalog/**
    - group: billing
      packages-to-scan:
        - com.example.billing.api
~~~

Corresponding property names in `springdoc` documentation include `springdoc.group-configs[0].group`, `packages-to-scan`, `paths-to-match`, and `paths-to-exclude`. For more complex conditions, customizers or `GroupedOpenApi` beans enable Java-based configuration.

### 2.3. Groups do not replace security boundaries

A group named `internal` does not secure the document on its own. The `/v3/api-docs/internal` endpoint still must be protected with Spring Security or appropriate network policies. Similarly, hiding a document from the Swagger UI dropdown does not disable the document URL.

Distinguish:

- Group filter: which operations are included in the document.
- Swagger UI listing: which documents are shown for selection.
- Authorization: who is permitted to fetch the document or invoke the API.

## 3. Listing multiple documents in one Swagger UI

Springdoc supports the `springdoc.swagger-ui.urls` property. Each entry has a `name` and `url`; Swagger UI uses the Topbar plugin so users can choose an API definition.

Example for an application with two groups:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Catalog API
        url: /v3/api-docs/catalog
      - name: Billing API
        url: /v3/api-docs/billing
    urls-primary-name: Catalog API
~~~

When opening `/swagger-ui.html`, users can pick Catalog API or Billing API. `urls-primary-name` determines which document opens by default. Names and URLs in the list must be unique.

### 3.1. Listing documents from multiple microservices

Swagger UI can pull documents from other services:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Catalog
        url: https://catalog.example.com/v3/api-docs
      - name: Billing
        url: https://billing.example.com/v3/api-docs
      - name: Identity
        url: https://identity.example.com/v3/api-docs
    urls-primary-name: Catalog
~~~

In this case, Swagger UI acts as a shared entry point for browsing APIs. Whenever a user picks an entry, the UI fetches that document and renders its operations. `urls` does not copy paths together or create shared components.

If Swagger UI and the services reside on different origins, browsers must be able to fetch documents via CORS. CORS configuration on each OpenAPI-providing service must allow Swagger UI's origin. If documents require authentication, configure access permissions and credentials per source.

### 3.2. `urls` and `url` have different precedence

Swagger UI supports:

- `springdoc.swagger-ui.url`: a single custom OpenAPI file.
- `springdoc.swagger-ui.urls`: a list of multiple OpenAPI definitions.
- `springdoc.swagger-ui.urls-primary-name`: name of the default selected document in the list.

When `urls` is configured, the `url` property is ignored. Do not declare both expecting Swagger UI to merge them automatically.

### 3.3. Listing multiple documents does not create a shared server URL

Each document retains its own `servers`, security schemes, and API version. When users pick Catalog, Try it out uses the server URL in the Catalog document; when picking Billing, the UI uses the Billing document's server URL.

This fits a portal listing multiple independent services. If the goal is calling every operation through one API Gateway hostname/path, design a gateway contract and consider merging or creating a dedicated facade document.

## 4. Merging multiple OpenAPI documents into one

Merging processes input documents and produces a new OpenAPI document. For example, three services publish:

- `catalog.yaml`
- `billing.yaml`
- `identity.yaml`

An API Gateway wants to publish them jointly under:

`https://api.example.com/platform`

The merged result can then contain paths:

~~~yaml
paths:
  /catalog/products:
    get:
      operationId: listProducts
  /billing/invoices:
    get:
      operationId: listInvoices
  /identity/users/me:
    get:
      operationId: getCurrentUser
~~~

This is a single OpenAPI document with one unified `paths` object. Consumers can download one file to discover every facade operation.

**Merging specifications does not implement routing.** The API Gateway must still route `/catalog/**` to the Catalog service, `/billing/**` to the Billing service, and `/identity/**` to the Identity service. If OpenAPI paths do not match the gateway, the merged document describes an API that does not exist at runtime.

## 5. Using `openapi-merge-cli`

One tool dedicated to the merge step is `openapi-merge-cli`. It takes multiple OpenAPI 3.0, 3.1, or 3.2 documents, applies combination rules, and writes a new file. Inputs must share the same major.minor OpenAPI version.

Install as a development dependency:

~~~bash
npm install --save-dev openapi-merge-cli
~~~

Create configuration file `openapi-merge.yaml`:

~~~yaml
inputs:
  - inputFile: ./specs/gateway.yaml
  - inputFile: ./specs/catalog.yaml
    pathModification:
      stripStart: /api
      prepend: /catalog
    dispute:
      prefix: Catalog
  - inputFile: ./specs/billing.yaml
    pathModification:
      stripStart: /api
      prepend: /billing
    dispute:
      prefix: Billing
  - inputFile: ./specs/identity.yaml
    pathModification:
      stripStart: /api
      prepend: /identity
    dispute:
      prefix: Identity

output: ./dist/platform-api.yaml
serversStrategy: first
securitySchemesStrategy: merge
resolveExternalReferences: true
inputRoot: ./specs
outputRoot: ./dist
~~~

`gateway.yaml` at the top of the list serves as the base document for the facade. Example:

~~~yaml
openapi: 3.1.0
info:
  title: Platform API
  version: 1.0.0
servers:
  - url: https://api.example.com/platform
    description: Public API Gateway
paths: {}
~~~

The base document provides `info` and `servers` for the output. Subsequent service documents contribute `paths`, `operations`, and `components`.

Run:

~~~bash
npx openapi-merge-cli --config openapi-merge.yaml
~~~

Configuration meaning:

- `inputs`: order and list of input documents.
- `info` and `servers`: taken from the first input by default; therefore `gateway.yaml` is placed first to define the facade's metadata and public server.
- `pathModification`: `stripStart` removes the service's `/api` prefix and `prepend` adds the per-service prefix to match gateway routes.
- `dispute.prefix`: creates distinct names when components share a name yet have differing definitions.
- `output`: path to the resulting document.
- `serversStrategy: first`: keeps `servers` from the first input; place the gateway contract first when that is intended.
- `securitySchemesStrategy: merge`: combines security schemes according to the tool's strategy.
- `resolveExternalReferences`: follows `$ref` pointers into other files to bring needed components into the output.
- `inputRoot` and `outputRoot`: restricts the scope of files read and the output file written.

`openapi-merge-cli` also provides an `init` command to scaffold sample configuration:

~~~bash
npx openapi-merge-cli init
~~~

The merge command reads the configuration file and generates the output. Commit the merge configuration alongside the pipeline so outputs remain reproducible.

## 6. Conflicts that must be resolved when merging

Two independent documents can each be valid yet conflict when combined. The merge tool must detect conflicts or apply clear resolution rules.

### 6.1. Duplicate paths and HTTP methods

Suppose two services both define:

`GET /health`

If merged verbatim, a path/method will collide. You can:

- Add per-service prefixes, such as `/catalog/health` and `/billing/health`.
- Select the operation belonging to the gateway facade and exclude the other.
- Use merge rules when sharing a path whose HTTP methods do not overlap and whose path-level fields are compatible.

`openapi-merge-cli` provides `duplicatePathHandling` with options such as `error`, `skip-later`, `prefer-later`, and `merge-operations`. By default, let conflicts fail the merge so the team reviews them. `skip-later` or `prefer-later` can silently drop operations if used without checks.

### 6.2. Duplicate component names

Two services might both declare `ErrorResponse` with different schemas. Do not assume they are identical merely because their names match.

A safe strategy is renaming components per service:

- `CatalogErrorResponse`
- `BillingErrorResponse`
- `IdentityErrorResponse`

A merge tool can deduplicate structurally identical components and apply prefixes/suffixes to conflicting component names. When renaming, every `$ref` pointing to that component must be updated. Inspect the output to ensure no broken references remain.

### 6.3. Duplicate `operationId` values

`operationId` should be unique within an OpenAPI document. If two services both declare `getById`, client generators may produce duplicate method names or fail.

Use namespaced or contextual `operationId` values:

- `catalogGetProductById`
- `billingGetInvoiceById`
- `identityGetUserById`

Do not merely rewrite paths while leaving duplicate `operationId` values intact. Verify uniqueness after merging.

### 6.4. Internal and cross-document `$ref`

A component can reference:

~~~yaml
$ref: "#/components/schemas/Product"
~~~

This is a local reference within the same document. When merging multiple files, the tool must preserve or rewrite `$ref` to the component's new location.

An input can also reference an external file:

~~~yaml
$ref: "../common/errors.yaml#/components/schemas/ApiProblem"
~~~

If the referenced file is included in `inputs`, the merge tool can rewrite the reference to the component imported into the combined document. If the file is not declared, `resolveExternalReferences` can instruct the tool to load the file and inline/pull the referenced component.

Do not enable resolving external references on untrusted inputs. Following `$ref` can expand the set of files or URLs the tool reads. Keep `inputRoot` to confine local files read and only process reviewed spec sources.

## 7. `servers` and `security` when merging

### 7.1. Selecting API Gateway `servers`

Each microservice may publish its own server:

~~~yaml
servers:
  - url: https://catalog.internal.example.com
~~~

~~~yaml
servers:
  - url: https://billing.internal.example.com
~~~

Yet the combined gateway document may need:

~~~yaml
servers:
  - url: https://api.example.com/platform
    description: Public API Gateway
~~~

Thus, the default merge strategy keeping `servers` from the first input is an important design choice. Place the gateway-level document first or configure the strategy to retain/combine servers as needed. Do not mechanically merge every server URL if clients should only call through the gateway.

### 7.2. Security schemes may share names with different meanings

For example, both Catalog and Billing use a scheme named `bearerAuth`, yet one service expects a different audience or uses a dedicated API key. When scheme definitions differ, do not silently overwrite them.

Steps:

1. Inspect each `components.securitySchemes`.
2. Standardize scheme names when they genuinely share semantics.
3. Rename schemes per service if configurations differ.
4. Inspect root-level and operation-level `security` after merging.
5. Verify the API Gateway enforces the exact policy documented.

Merging security schemes does not automatically implement authentication, token exchange, or authorization on the gateway.

## 8. `info` and `version` of the merged document

Each service may have:

~~~yaml
info:
  title: Catalog API
  version: 2.1.0
~~~

~~~yaml
info:
  title: Billing API
  version: 4.0.0
~~~

A merged document has only one `info` object. You cannot keep two `info.title` and two `info.version` fields at the same level as if the document were still two separate files.

For a gateway facade, pick representative metadata:

~~~yaml
info:
  title: Platform API
  version: 1.0.0
  description: Combined contract for APIs published through the Platform Gateway.
~~~

The merged document's `info.version` should represent the facade API contract version. Individual service versions should be stored in release metadata, an API catalog, or a standardized vendor extension. Do not pick one service's version and assume it represents the entire platform.

Inputs must also share the same OpenAPI major.minor version as required by the merge tool. That is the specification language version, independent of each API's `info.version`.

## 9. When to choose listing vs. merging?

| Need | Suitable Approach | Reason |
|---|---|---|
| Monolith with public and admin APIs | `GroupedOpenApi` | Each audience gets its own document and path filters. |
| Developer portal for multiple independent microservices | Swagger UI `urls` | Easy selection per service; no need to build a facade contract. |
| API Gateway exposing one unified surface | Merge OpenAPI | One document reflects the paths the gateway actually exposes. |
| One service offering both JSON and YAML | Springdoc endpoints | The same document in two output formats. |
| Inlining external `$ref` inside one root document | Bundling tool | Resolves references within one root spec rather than combining independent APIs. |

If you only need one shared UI to browse APIs, merging is unnecessary. If consumers need a single contract to generate an SDK or validate a gateway, a Swagger UI dropdown will not satisfy that goal.

## 10. Verifying results after grouping, listing, or merging

### 10.1. Checking each group

Call each group's endpoint:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/catalog \
  -o build/openapi/catalog.json

curl -fsS http://localhost:8080/v3/api-docs/billing \
  -o build/openapi/billing.json
~~~

Verify `paths` in each file contains only operations belonging to that group. If intentional overlap exists, document the reason and ensure no internal endpoints leak.

### 10.2. Checking Swagger UI configuration

Swagger UI fetches configuration at `/v3/api-docs/swagger-config`. When using multiple URLs, verify the configuration contains:

- Every desired `name` and `url`.
- No duplicate names or URLs.
- `urlsPrimaryName` pointing to an existing entry.
- External URLs reachable from browsers.
- Proper CORS and authentication on source services.

Swagger UI config only holds a list of URLs; do not treat it as proof that paths were merged.

### 10.3. Validating the merged document

After merging, run a validator/linter on the output:

~~~bash
openapi-generator-cli validate \
  -i dist/platform-api.yaml \
  --recommend
~~~

Beyond syntax validation, verify:

- Every path and method appears only once.
- `operationId` values have no duplicates.
- Every `$ref` resolves cleanly.
- Component collisions were handled.
- `servers` reflects the gateway URL.
- Security schemes and requirements were not lost.
- All inputs share the same OpenAPI major.minor version.
- Rewritten paths match actual gateway routes.

### 10.4. Contract testing through the gateway

A merged document can be syntactically valid yet inaccurate at runtime. Run tests calling the real gateway:

- `/catalog/products` routes to the Catalog service.
- `/billing/invoices` routes to the Billing service.
- Authentication headers are forwarded properly by the gateway.
- Response statuses, media types, and schemas match the merged document.
- Error responses from each service are not altered by the gateway beyond what is documented.

If the gateway rewrites statuses, headers, or error payloads, the merged contract must describe the external behavior consumers actually observe.

## 11. Common mistakes

- **Confusing `GroupedOpenApi` with merging**: each group remains a separate document.
- **Confusing Swagger UI `urls` with merging**: the Topbar only lets you pick one document to view.
- **Using `springdoc.swagger-ui.url` alongside `urls`**: `url` is ignored when `urls` is configured.
- **Duplicate names or URLs in `urls`**: Swagger UI requires unique identifiers.
- **Not enabling CORS for external specs**: browsers cannot load documents from cross-origin services.
- **Assuming group names protect documents**: Spring Security/network policies are still required.
- **Merging duplicate paths while ignoring warnings**: operations may be dropped or overwritten.
- **Duplicate component names with differing schemas**: `$ref` may point to the wrong model without renaming and rewriting.
- **Duplicate `operationId` values**: SDK generators may produce duplicate methods or fail.
- **Keeping internal server URLs in the merged spec**: clients get directed to unreachable hosts.
- **Merging security schemes without inspection**: requirements may change meaning or reference wrong schemes.
- **Using one service's `info.version` as the platform version**: facade metadata fails to reflect the combined release.
- **Mixing OpenAPI 3.0 and 3.1**: merge tools may reject mismatched major.minor versions.
- **Enabling external ref resolution on untrusted inputs**: tools may read files or URLs outside intended boundaries.
- **Assuming merging creates gateway routing**: runtime gateway routing must still be configured and tested.
- **Validating syntax only**: a spec can be valid yet mismatch actual paths or server behavior.

## 12. Documentation distribution workflow for multi-service systems

1. **Classify APIs**: monolith groups, independent microservices, or gateway facade.
2. **Choose documentation topology**: single document, multiple groups, UI listing, or merged spec.
3. **Export per-service documents**: fetch JSON/YAML from `springdoc` and store versioned artifacts.
4. **Standardize OpenAPI version**: merge inputs must share the same major.minor version.
5. **Standardize paths and servers**: define gateway prefixes and public server URLs.
6. **Handle component/security collisions**: rename, merge, or fail for review.
7. **Build the merged document**: run the merge tool with source-controlled config.
8. **Validate and lint**: verify `$ref`, `operationId`, `paths`, `components`, `servers`, and `security`.
9. **Test runtime**: call APIs through the gateway to verify against the merged contract.
10. **Publish**: release the consolidated spec alongside release metadata of source services.

## 13. Review checklist

- [ ] Clarified whether the goal is grouping, listing documents, or genuinely merging.
- [ ] Every `GroupedOpenApi` has a unique group name.
- [ ] Group path/package filters reflect the intended audience.
- [ ] Internal documents are protected by security policy.
- [ ] Swagger UI `urls` have unique names and URLs.
- [ ] `urlsPrimaryName` points to an existing document.
- [ ] CORS is configured for external specs.
- [ ] If merging, all inputs share the same OpenAPI major.minor version.
- [ ] Path collisions have explicit policy and do not drop operations.
- [ ] Component collisions are renamed/deduplicated under control.
- [ ] All `$ref` pointers resolve after merging.
- [ ] `operationId` values are unique in the merged document.
- [ ] `servers` and paths match the public gateway.
- [ ] Security schemes and requirements preserve accurate semantics.
- [ ] `info.version` represents the facade contract, not a single service version.
- [ ] Merged document is validated, diffed, and stored as an artifact.
- [ ] Gateway contract is tested with real runtime requests/responses.

## 14. References

- [springdoc-openapi – Multiple OpenAPI definitions and GroupedOpenApi](https://springdoc.org/index.html#how-can-i-define-multiple-openapi-definitions-in-one-spring-boot-project)
- [springdoc-openapi – Configuration properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Aggregating external OpenAPI endpoints](https://springdoc.org/index.html#how-can-i-aggregate-external-endpoints-exposing-openapi-3-spec-inside-one-single-application)
- [Swagger UI – Configuration: url and urls](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [openapi-merge-cli – Getting started and configuration](https://github.com/robertmassaioli/openapi-merge/blob/main/packages/openapi-merge-cli/README.md)
- [openapi-merge – Merging behaviour and conflict handling](https://robertmassaioli.github.io/openapi-merge/library/merging-behaviour)
- [openapi-merge – CLI configuration reference](https://robertmassaioli.github.io/openapi-merge/cli/configuration)
- [OpenAPI Specification](https://spec.openapis.org/oas/)

Listing multiple documents lets users select and browse each API independently; merging creates a new consolidated contract. Use `GroupedOpenApi` to partition docs within an application, `swagger-ui.urls` to build a multi-service catalog, and a merge tool when one unified document is needed for a gateway or SDK. Before distributing a merged spec, resolve path/component/`operationId` conflicts, `$ref` pointers, `servers`, and `security`, then test it against real HTTP routing.
