# Media Type or Header Conditions When Supported

Springdoc can generate multiple independent OpenAPI documents from the same Spring Boot application. Beyond filtering by package or URL path, `GroupedOpenApi` also supports filtering operations by request media type (`consumes`), response media type (`produces`), and Spring MVC mapping header conditions (`headers`). These filters are useful when a system has JSON/XML APIs, file upload endpoints, or API versions selected via request headers.

An important distinction is that group filters only decide which operations appear in the generated document. They do not register converters, alter responses, produce headers, or secure endpoints. Actual HTTP behavior is still governed by controller mappings, message converters, and application security configuration.

## 1. Three Types of Filter Conditions

`GroupedOpenApi.Builder` provides the following methods in Springdoc versions that support them:

| Method | Condition Evaluated | Typical Corresponding Spring Mapping Attribute |
| --- | --- | --- |
| `consumesToMatch(...)` | Media types accepted by the endpoint in the request body | `consumes` |
| `producesToMatch(...)` | Media types the endpoint can return | `produces` |
| `headersToMatch(...)` | Conditions on HTTP request headers | `headers` |

For example, `consumes = "application/json"` indicates the endpoint accepts JSON; `produces = "application/xml"` indicates the endpoint can return XML; `headers = "X-API-VERSION=v2"` restricts the mapping to requests carrying an `X-API-VERSION` header with value `v2`.

These filter methods complement familiar filters such as `pathsToMatch`, `pathsToExclude`, `packagesToScan`, and `packagesToExclude`. When combining multiple filter dimensions, treat them as conditions narrowing the group's scope: an operation must satisfy the path/package filters as well as the configured media type/header conditions. If multiple values are supplied within the same condition type, verify the resulting group in your Springdoc version to confirm how they are combined.

## 2. Distinguishing `consumes`, `produces`, and `headers`

Spring MVC provides these attributes on `@RequestMapping` and composed annotations such as `@GetMapping` and `@PostMapping`:

- `consumes` matches the request's `Content-Type`, i.e., the body format sent by the client.
- `produces` matches the request's `Accept` header and describes the response format the handler can produce.
- `headers` matches other request headers according to declared expressions.

For example:

```java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(@RequestBody CreateBookRequest request) {
    // Process the JSON request and return a JSON response.
    return new BookResponse(1L, request.title());
}
```

In this case, `consumesToMatch("application/json")` filters by request format; `producesToMatch("application/json")` filters by response format. Do not use `headersToMatch("Content-Type=application/json")` or `headersToMatch("Accept=application/json")` in place of these two dedicated media type filters. Spring MVC already models those two headers through `consumes` and `produces`.

## 3. Filtering Groups by Response Media Type with `producesToMatch`

Suppose the same system has endpoints returning JSON and endpoints returning XML. You can split the documentation into two groups so integrators only see operations with the relevant representation.

JSON controller:

```java
@RestController
@RequestMapping(path = "/api/books", produces = MediaType.APPLICATION_JSON_VALUE)
class JsonBookController {

    @GetMapping
    List<BookResponse> list() {
        return List.of(new BookResponse(1L, "Spring Boot Fundamentals"));
    }
}
```

XML controller:

```java
@RestController
@RequestMapping(path = "/api/books/export", produces = MediaType.APPLICATION_XML_VALUE)
class XmlBookController {

    @GetMapping
    BookXmlResponse export() {
        return new BookXmlResponse(1L, "Spring Boot Fundamentals");
    }
}
```

Group declarations in Springdoc 2.x:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi jsonApi() {
        return GroupedOpenApi.builder()
            .group("books-json")
            .pathsToMatch("/api/**")
            .producesToMatch("application/json")
            .build();
    }

    @Bean
    GroupedOpenApi xmlApi() {
        return GroupedOpenApi.builder()
            .group("books-xml")
            .pathsToMatch("/api/**")
            .producesToMatch("application/xml")
            .build();
    }
}
```

The `books-json` group focuses on operations with a `produces` mapping matching JSON; `books-xml` focuses on operations with an XML mapping. This example assumes controllers and converters are already configured to actually produce those respective formats.

If an operation declares support for both JSON and XML, it can match both groups and appear in both documents. Grouping does not mean each operation belongs to at most one document.

## 4. Filtering Groups by Request Media Type with `consumesToMatch`

`consumesToMatch` is useful when an application has endpoints accepting different payload types, such as JSON, XML, or multipart uploads.

Example file-upload endpoint:

```java
@RestController
@RequestMapping("/api/imports")
class ImportController {

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<Void> upload(
            @RequestPart("file") MultipartFile file) {
        return ResponseEntity.accepted().build();
    }
}
```

Creating a group dedicated to operations accepting multipart:

```java
@Bean
GroupedOpenApi uploadApi() {
    return GroupedOpenApi.builder()
        .group("file-uploads")
        .pathsToMatch("/api/**")
        .consumesToMatch(MediaType.MULTIPART_FORM_DATA_VALUE)
        .build();
}
```

You can create another group for operations accepting JSON:

```java
@Bean
GroupedOpenApi jsonRequestApi() {
    return GroupedOpenApi.builder()
        .group("json-requests")
        .pathsToMatch("/api/**")
        .consumesToMatch(MediaType.APPLICATION_JSON_VALUE)
        .build();
}
```

`consumesToMatch` filters based on the mapping's `consumes` condition. If an endpoint does not declare `consumes`, Spring MVC may still parse JSON via message converters, but the mapping does not advertise an explicit media type condition for this filter to inspect. When grouping by request format, declare `consumes` explicitly and verify the generated document.

## 5. Filtering Groups by Header with `headersToMatch`

Header mapping works well when an API selects handlers via a custom header, such as an API version or compatibility mode. Spring MVC supports header expressions in the `headers` attribute of `@RequestMapping`.

Common expression forms include:

| Expression | Meaning |
| --- | --- |
| `X-API-VERSION` | Request must include this header |
| `X-API-VERSION=v2` | Header must have value `v2` |
| `X-API-VERSION!=v1` | Header must have a value other than `v1` |
| `!X-API-VERSION` | Request must not include this header |

Example controller serving only version v2:

```java
@RestController
@RequestMapping(
    path = "/api/books",
    headers = "X-API-VERSION=v2"
)
class BooksV2Controller {

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    List<BookResponse> list(
            @RequestHeader("X-API-VERSION") String apiVersion) {
        return List.of(new BookResponse(1L, "Spring Boot Fundamentals"));
    }
}
```

Corresponding group:

```java
@Bean
GroupedOpenApi booksV2Api() {
    return GroupedOpenApi.builder()
        .group("books-v2")
        .pathsToMatch("/api/books/**")
        .headersToMatch("X-API-VERSION=v2")
        .build();
}
```

The `headers` mapping controls which requests Spring dispatches to this controller. `headersToMatch` lets the document group select operations with the matching header condition. `@RequestHeader` on the parameter lets the controller read the value and helps Springdoc document the header parameter for integrators.

Note: merely placing `@RequestHeader("X-API-VERSION")` on a method parameter is not equivalent to the mapping condition `headers = "X-API-VERSION=v2"`. Without a condition on `@RequestMapping`, `headersToMatch("X-API-VERSION=v2")` has no mapping condition to filter against. Conversely, a mapping condition can constrain a header without automatically producing an explicit OpenAPI parameter in every configuration; inspect `/v3/api-docs/{group}` and add parameter metadata if needed.

## 6. Do Not Use `headersToMatch` as a Substitute for Content Negotiation

`Accept` and `Content-Type` are two special headers already modeled in Spring MVC via `produces` and `consumes`. Choose the right filter:

| Requirement | Spring Mapping | Group Filter |
| --- | --- | --- |
| Document only APIs accepting JSON | `consumes = "application/json"` | `consumesToMatch("application/json")` |
| Document only APIs returning JSON | `produces = "application/json"` | `producesToMatch("application/json")` |
| Document only APIs accepting multipart | `consumes = "multipart/form-data"` | `consumesToMatch("multipart/form-data")` |
| Document only APIs requiring v2 header | `headers = "X-API-VERSION=v2"` | `headersToMatch("X-API-VERSION=v2")` |

For example, if a client sends `Accept: application/xml`, Spring content negotiation selects the XML representation when the handler supports it. `producesToMatch("application/xml")` filters documentation by the mapping's `produces` condition. There is no need to write `headersToMatch("Accept=application/xml")`.

Similarly, `Content-Type: application/json` maps to `consumes`; do not use `headersToMatch("Content-Type=application/json")`.

## 7. Combining Multiple Conditions in One Group

A group can combine path, media type, and header filters to narrow operation scope:

```java
@Bean
GroupedOpenApi partnerV2JsonApi() {
    return GroupedOpenApi.builder()
        .group("partner-v2-json")
        .pathsToMatch("/api/partner/**")
        .producesToMatch(MediaType.APPLICATION_JSON_VALUE)
        .consumesToMatch(MediaType.APPLICATION_JSON_VALUE)
        .headersToMatch("X-API-VERSION=v2")
        .build();
}
```

This group targets operations under `/api/partner/**` that accept JSON, return JSON, and declare the v2 version header mapping. If an operation omits any corresponding condition or fails one of the filter criteria, it may be excluded from the group.

Avoid making groups so narrow that users struggle to locate documentation. Combine multiple conditions only when they represent a meaningful boundary, such as a specific partner contract or a set of endpoints sharing an exchange format.

## 8. Configuring Groups in `application.properties`

Besides Java beans, Springdoc allows declaring groups in configuration. For example:

```properties
springdoc.group-configs[0].group=books-json
springdoc.group-configs[0].paths-to-match=/api/**
springdoc.group-configs[0].produces-to-match=application/json

springdoc.group-configs[1].group=file-uploads
springdoc.group-configs[1].paths-to-match=/api/**
springdoc.group-configs[1].consumes-to-match=multipart/form-data

springdoc.group-configs[2].group=books-v2
springdoc.group-configs[2].paths-to-match=/api/books/**
springdoc.group-configs[2].headers-to-match=X-API-VERSION=v2
```

Property names and support for each filter depend on the Springdoc version in use. If your IDE or current version's configuration binding does not recognize `headers-to-match`, check the `GroupedOpenApi` API and configuration metadata for your exact version; use a Java bean if the builder exposes the corresponding method.

Do not declare the same group via both a Java bean and `springdoc.group-configs` unless there is a clear reason. Each group needs a unique name and maintainable configuration.

## 9. Accessing Each Group's Document

For a group named `books-json`, Springdoc typically serves the JSON document at:

```text
/v3/api-docs/books-json
```

The group's YAML document can be accessed at:

```text
/v3/api-docs/books-json.yaml
```

Swagger UI can display the list of configured group documents. You can open the UI directly and select the group to inspect; when configuring a custom URL list, group names must match the registered group names.

Verify each group independently:

1. Open the `/v3/api-docs/{group}` endpoint.
2. Inspect the `paths` list and included operations.
3. Verify `requestBody.content` and `responses.content` have the expected media types.
4. Verify header parameters are documented when operations require headers.
5. Compare groups to spot missing operations or unexpected inclusions.

Groups only produce separate documentation; they do not create new runtime URLs for controllers. If the same controller appears in multiple groups, its actual HTTP URL remains unchanged.

## 10. Limitations and Cases Requiring Careful Verification

Media type and header filters rely on mapping metadata that Springdoc can inspect. Several cases require testing against your actual version and routing model:

- **Mappings without `consumes` or `produces`:** default converters may still handle JSON, but mapping-based filters might not recognize the operation as explicitly declaring that media type.
- **Headers read solely via `@RequestHeader`:** this does not create a mapping condition for `headersToMatch`; declare `headers` on the mapping if you want to filter by header expression.
- **Functional endpoints or custom handlers:** filtering behavior may differ from Spring MVC controllers using `@RequestMapping`. Verify support for your Springdoc version and endpoint style.
- **One mapping with multiple media types:** the operation may match multiple groups. Check each group's document rather than assuming mutual exclusivity.
- **Wildcard media types:** conditions such as `application/*` or `*/*` depend on Spring/Springdoc matching behavior; verify the actual result.
- **Mappings inherited across class and method levels:** Spring merges mapping conditions from both levels; check the effective condition of the handler.
- **Custom `OpenApiCustomizer` or `OperationCustomizer`:** customizers can alter the document after filtering. Check ordering and the final group output.

If a group is empty or missing operations, inspect controller mapping conditions first, then group filters, and finally customizers. Do not add arbitrary documentation annotations just to force an operation to appear if runtime mappings do not reflect that condition.

## 11. Distinguishing Document Groups from Security and Routing

Grouping is a way to organize OpenAPI contracts. A group named `internal-v2` does not automatically make an endpoint internal or protect it with authentication. Likewise, `headersToMatch` in group configuration only filters operations in documentation; runtime constraints must be declared on Spring mappings or enforced in security/gateway layers.

| Configuration | Effect |
| --- | --- |
| `GroupedOpenApi.headersToMatch(...)` | Selects operations for a document group |
| `@RequestMapping(headers = ...)` | Constrains which requests match the Spring MVC handler |
| `@RequestHeader` | Binds header values in method arguments and aids parameter documentation |
| Spring Security | Authenticates and authorizes requests |
| Gateway / reverse proxy | May route, filter, or enforce policies at the system edge |

If a version header selects the API version, ensure v1/v2 mappings do not collide, have separate documentation, and have tests sending valid and invalid headers. If a header only categorizes documentation without runtime enforcement, clients may invoke operations under conditions different from what the group document implies.

## 12. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JSON group lacks expected operations | Mapping does not declare matching `produces` or `consumes` | Explicitly declare media types on the mapping and re-check the group |
| Endpoint accepts JSON but misses the `consumes` group | JSON is handled by default converters without `consumes` on the mapping | Add `consumes = application/json` if that is the true contract |
| Header-based group is empty | Only `@RequestHeader` is present without `headers` mapping | Add header conditions to `@RequestMapping` if runtime enforcement is desired |
| Misusing `headersToMatch("Accept=...")` | Using header filter instead of `produces` | Switch to `producesToMatch` |
| Misusing `headersToMatch("Content-Type=...")` | Using header filter instead of `consumes` | Switch to `consumesToMatch` |
| Operation appears in multiple groups | Mapping supports multiple media types or group filters overlap | Clarify group boundaries; overlap may be intentional |
| Group missing at `/v3/api-docs/{group}` | Wrong group name, bean not created, or group config failed to bind | Check the group name and Springdoc configuration |
| Header parameter missing in documentation | Mapping condition does not auto-generate a parameter under current config | Add `@RequestHeader`/`@Parameter` and inspect OpenAPI output |
| Functional endpoints not filtered like controllers | Mapping-metadata filters do not apply identically | Check version support and use an appropriate customizer |

## 13. Checklist for Media Type or Header Groups

- [ ] Choose the right filter: `consumesToMatch`, `producesToMatch`, or `headersToMatch`.
- [ ] Controller `consumes` reflects actual accepted request `Content-Type`.
- [ ] `produces` reflects representations the endpoint can actually return.
- [ ] Custom headers are declared in `@RequestMapping(headers = ...)` if filtering by header condition.
- [ ] Do not use `headersToMatch` in place of dedicated `Accept`/`Content-Type` conditions.
- [ ] Combine path/package filters to give groups clear boundaries.
- [ ] Check operations with multiple media types and potential presence across multiple groups.
- [ ] Verify your Springdoc version supports the builder methods or properties used.
- [ ] Inspect each document at `/v3/api-docs/{group}` and Swagger UI.
- [ ] Never confuse document filters with runtime routing, authentication, or authorization.

`consumesToMatch`, `producesToMatch`, and `headersToMatch` let you partition OpenAPI documentation by how operations accept data, return representations, or match header mappings. When Spring mappings clearly express runtime conditions and groups use the matching filters, each document group accurately reflects the contract tailored to each client type or API version.
