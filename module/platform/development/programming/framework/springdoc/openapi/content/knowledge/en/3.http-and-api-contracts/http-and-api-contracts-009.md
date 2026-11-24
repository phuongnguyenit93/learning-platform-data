# Contract Compatibility for API Consumers

An API contract defines how a caller sends requests and how the API provider responds. When the contract changes, the key concern is whether active clients can continue calling the API, and whether new clients can work with supported server versions. A seemingly minor change, such as adding an enum value or changing a status code, can still break applications consuming the API.

With `springdoc-openapi`, the contract is represented by the OpenAPI specification generated from controllers, DTOs, annotations, and Spring configuration. Managing compatibility therefore requires combining three practices: clear contract design, controlling specification changes, and testing real behavior between providers and consumers.

## 1. API Providers and Consumers

In an API interaction:

- **Provider** is the system exposing the endpoint and handling requests.
- **Consumer** is the application, service, or user calling that endpoint.
- **API contract** specifies paths, HTTP methods, parameters, request bodies, responses, schemas, status codes, media types, and security requirements.

For example, a storefront application calls `GET /api/products/42` to retrieve product details. The provider commits to returning a response matching the published schema. A consumer can be a frontend, mobile app, inventory service, or an SDK generated from the OpenAPI document.

Compatibility must be evaluated from the consumer's perspective. A change can be safe for older clients yet fail for newer clients when newer clients connect to an older server. Thus, two directions must be distinguished:

| Concept | Question to answer | Example |
|---|---|---|
| Backward compatibility | Can a newer server continue serving older clients? | Server adds an optional request field while still accepting older requests without that field |
| Forward compatibility | Can a newer client work with an older server? | Newer client still sends requests in the old format when connecting to a server not yet supporting the new field |

A change can only be deemed compatible after analyzing communication direction, data handling rules, and how clients are implemented. No universal rule guarantees every client ignores unknown fields or values.

## 2. Parts of the Contract That Must Stay Stable

An OpenAPI specification contains many parts that directly affect consumers:

| Component | Information consumers rely on | Changes that can break clients |
|---|---|---|
| `paths` and HTTP methods | Address and how to invoke an operation | Changing paths, changing methods, or removing endpoints |
| `parameters` | Name, location, type, and requiredness of parameters | Renaming query parameters or changing optional to required |
| `requestBody` | Payload structure, media types, and schemas | Removing accepted fields or adding required fields |
| `responses` | Status codes, headers, media types, and returned payloads | Removing fields, changing types, or changing status codes |
| `components.schemas` | Shared data structures | Changing required fields, enums, formats, or value bounds |
| `security` | Authentication method and required permissions | Adding auth requirements that reject uncredentialed old clients |
| `operationId` | Operation name that SDK generators may use | Renaming can rename generated client methods |

The contract also includes business semantics. For example, a `price` field remains an integer yet changes units from VND to thousands of VND; the schema may stay unchanged while consumer calculations silently go wrong. Similarly, changing timezones, rounding rules, default sort order, status meanings, or pagination behavior can all break compatibility.

## 3. Evaluating Request Changes

Requests are sent by the consumer to the provider. Check whether the new provider continues accepting every valid request that older clients currently send.

| Request change | Impact on older clients calling newer server | Common assessment |
|---|---|---|
| Adding an optional field accepted when absent | Older clients omitting the field keep working | Usually backward compatible |
| Adding a required field | Older clients omit the new field so requests are rejected or misprocessed | Breaking change |
| Making an optional field required | Older requests may omit the field | Breaking change |
| Removing a previously accepted request field | Older clients still send the removed field | Potentially breaking, especially if server rejects unknown fields |
| Renaming a field or parameter | Older clients keep sending the old name | Breaking change if the old name is no longer supported |
| Narrowing value range, pattern, or numeric limits | Previously valid values may be rejected | Breaking change |
| Adding an accepted value to a request enum | Older clients keep sending old values | Usually backward compatible; newer clients sending the new value to an older server may fail |
| Changing media type or payload structure | Older clients may send a format no longer accepted | Usually breaking |

For example, the initial version of a product creation API accepts this request:

```json
{
  "name": "Keyboard",
  "price": 1290000
}
```

The server can add an optional `description` field:

```json
{
  "name": "Keyboard",
  "price": 1290000,
  "description": "Mechanical keyboard"
}
```

Older clients still send payloads containing only `name` and `price`. For this change to be backward compatible, the new server must continue accepting requests lacking `description` and apply sensible handling when that field is absent.

In OpenAPI, distinguish allowed fields from required fields. For example, the schema below requires only `name` and `price`; `description` is optional:

```yaml
type: object
required:
  - name
  - price
properties:
  name:
    type: string
  price:
    type: integer
    format: int64
  description:
    type: string
```

When updating DTOs, annotations and validation must reflect this rule accurately. Adding `@NotNull` or placing `description` in `required` is a contract change that can prevent older clients from sending valid requests.

## 4. Evaluating Response Changes

Responses are sent by the provider to the consumer. For responses, verify whether older clients can handle new data and whether newer clients can operate against older servers.

| Response change | Impact on older clients | Common assessment |
|---|---|---|
| Adding an optional property | Clients ignoring unknown properties continue working | Usually backward compatible for tolerant clients |
| Removing or renaming a property | Clients reading the old property fail or lose data | Breaking change |
| Changing an always-present property to optional or nullable | Clients may not handle missing data cases | Breaking change |
| Changing data type or format | Decoders or client logic may become incompatible | Breaking change |
| Adding an enum value in response | Clients using exhaustive switches may fail to handle the new value | Breaking risk |
| Removing an enum value in response | SDKs or consumers relying on published values may need updates; check logic depending on old values | Potentially breaking depending on codegen and enum handling |
| Changing status code or response body | Client success/error handling logic may misbehave | Usually breaking |
| Adding a new response status | Clients may treat it as an unknown error | Check how clients handle unknown statuses |

Adding a property to a response is generally considered an additive change, yet it is safe only if consumers are built to ignore unknown properties. Some decoders, schema settings, or generated clients reject payloads containing unfamiliar fields. Therefore, test real clients and verify the system's tolerant-reader conventions.

Old response example:

```json
{
  "id": 42,
  "name": "Keyboard"
}
```

New response adding `description`:

```json
{
  "id": 42,
  "name": "Keyboard",
  "description": "Mechanical keyboard"
}
```

Clients reading only `id` and `name` generally continue working. However, newer clients relying on `description` will not receive that field when calling an older server. When client and server deployments are independent, consumers should treat the new field as potentially absent during the transition period.

## 5. Distinguishing Absent Fields, Null, and Default Values

A common source of bugs is treating these three states as identical:

1. Field absent from JSON.
2. Field present with value `null`.
3. Field present with a default value such as `0`, `false`, or an empty string.

Examples:

```json
{}
```

```json
{"description": null}
```

```json
{"description": ""}
```

These three payloads can carry different meanings. In update APIs, an absent field may mean keep the existing value; `null` may mean clear the value; an empty string may be an intentionally submitted value. Define this behavior explicitly in the contract and test it on both provider and consumer sides.

In OpenAPI, `required` controls whether a property must appear. Nullability is a separate dimension represented according to the OpenAPI/JSON Schema version in use. Never infer that a field omitted from `required` automatically permits `null`. Server DTOs, Jackson configuration, and validation must align with the published schema.

## 6. Enums, Data Types, and Schema Constraints

Enums in requests and responses carry different risk profiles. When a server adds an accepted enum value to a request, older clients can keep sending previous values. However, newer clients sending the newly added value to an older server will be rejected. For response enums, a newer server can return a value unfamiliar to older clients; generated enum code or switch expressions may fail to handle it.

Example:

```yaml
type: string
enum:
  - NEW
  - PROCESSING
  - COMPLETED
```

If the provider adds `CANCELLED`, verify whether consumers have a default fallback branch or fail deserializing unknown enum values. For public APIs or independently released clients, consider using strings with documented unknown-value handling rules, or designing enum extensibility suited to the SDK languages.

Other schema changes also require careful evaluation:

- Changing `integer` to `string` alters the data type clients receive or send.
- Changing `int32` to `int64` can cause issues for clients with integer limits or generators mapping types differently.
- Adding `minimum`, `maximum`, `minLength`, `maxLength`, or `pattern` can reject previously valid data.
- Changing date-time or numeric `format` can alter parsing and serialization.
- Changing `oneOf`, `anyOf`, `allOf`, or discriminators can heavily impact generated clients and polymorphic decoders.
- Changing units, precision, timezone, or property meaning is a semantic change even when the OpenAPI type remains unchanged.

When using `@Schema`, accurately describe actual types and bounds. Do not add constraints merely to make docs look stricter if the server does not enforce those exact rules.

## 7. HTTP Methods, Parameters, Status Codes, and Security

Compatibility does not reside solely in JSON bodies. HTTP protocol elements are also part of the contract:

- Changing paths or HTTP methods prevents clients calling old URLs from reaching the operation.
- Renaming query parameters, path parameters, or headers causes old requests to stop matching the contract.
- Changing a query parameter from optional to required can cause older clients to receive `400 Bad Request` or validation errors.
- Changing `Content-Type` or `Accept` can prevent client and server from negotiating media types.
- Changing from `200 OK` with a body to `204 No Content` breaks clients expecting to read a response body.
- Returning `200` for cases that previously returned `404`, or altering error response structures, can break consumer error-handling logic.
- Adding mandatory authentication or permissions can cause older clients to receive `401 Unauthorized` or `403 Forbidden`.

For example, a client is calling:

```http
GET /api/products?page=0&size=20
Accept: application/json
```

If the server renames `size` to `pageSize` without supporting the old name, clients must be updated. You can manage the transition by temporarily accepting both parameters, clearly defining precedence when both are present, and marking the old name deprecated before removal.

## 8. Compatible Changes vs. Breaking Changes

A practical evaluation method is asking whether existing consumers must modify code, change configuration, or re-release applications just to keep working.

| Change | Usually compatible? | Conditions to verify |
|---|---|---|
| Adding a new endpoint | Yes | Does not alter old routes or behavior |
| Adding an optional request field | Yes for older clients | Server accepts payloads without the new field |
| Adding a response field | Yes for tolerant clients | Older clients ignore unknown fields; schema decoder is not strict |
| Adding a response enum value | Risky | Consumers handle unknown values |
| Adding a required request field | No | Older clients cannot automatically send the new field |
| Removing or renaming a response field | No | Older clients may be reading that field |
| Changing path, method, or parameter | No if old interface is dropped | Clients must change requests |
| Narrowing valid value ranges | No if old data is rejected | Previously valid requests must continue to be accepted |
| Increasing security requirements | Potentially breaking | Whether older client credentials and permissions satisfy them |
| Changing business semantics | Usually breaking | Consumers may interpret the same data under old rules |

These are general assessments, not absolute laws. Actual impact depends on exact schemas, serialization/deserialization, validator settings, generated code, and how consumers handle unknown cases.

## 9. Using springdoc to Express a Stable Contract

Springdoc generates documentation from controllers, DTOs, Spring annotations, and Swagger annotations. Treat the generated specification as a public contract between provider and consumer. Example:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
@Tag(name = "Products")
class ProductController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "Get product by ID"
    )
    ProductResponse getById(@PathVariable Long id) {
        return productService.getById(id);
    }
}

@Schema(description = "Product details")
record ProductResponse(
    @Schema(description = "Product ID", example = "42")
    Long id,
    @Schema(description = "Product name", example = "Keyboard")
    String name,
    @Schema(description = "Product description", example = "Mechanical keyboard")
    String description
) {
}
```

Principles to apply:

- Keep `operationId` stable because client generators may use it for method names.
- Mark a property as required only when the server truly requires it or always guarantees returning it.
- Clearly document data types, formats, enums, limits, and examples.
- Publish key success and error responses, including status codes and body schemas.
- Keep paths, methods, parameters, and media types stable within the same contract version.
- Do not use annotations to document behavior that the controller or runtime configuration does not enforce.

### Marking an Operation as Deprecated

When preparing to replace an endpoint, you can mark the old operation as deprecated so consumers know to migrate:

```java
@GetMapping("/legacy/{id}")
@Operation(
    operationId = "getLegacyProductById",
    summary = "Get product via legacy endpoint",
    deprecated = true
)
ProductResponse getLegacyById(@PathVariable Long id) {
    return productService.getById(id);
}
```

The deprecated flag in OpenAPI is a signal for tools and documentation readers. It does not block requests automatically, nor does it communicate when the endpoint will be removed. The provider must publish the replacement path, support timeline, migration plan, and monitor old endpoint usage before removing it.

## 10. Contract Version Management

When a change cannot preserve compatibility, a versioning strategy is needed so consumers can migrate in a controlled manner. Common approaches:

| Versioning approach | Example | Characteristics |
|---|---|---|
| Path versioning | `/api/v1/products`, `/api/v2/products` | Easy to inspect, route, and operate in parallel |
| Header versioning | `X-API-Version: 2` | Keeps paths stable yet requires clear header management and docs |
| Media type versioning | `Accept: application/vnd.example.product-v2+json` | Ties versions to content representation, more complex to debug |

You do not need to bump the version for every additive change. You can stay on the same version when adding new operations or optional fields that meet the system's compatibility policy. When mandatory changes prevent older clients from functioning, publish a new contract version or provide an equivalent transition mechanism.

A version migration plan should include these steps:

1. Identify which changes cannot maintain compatibility and which consumers are affected.
2. Publish the new contract with request/response examples and migration guides.
3. Run old and new versions in parallel for the announced transition window.
4. Mark old operations or schemas as deprecated in the documentation.
5. Monitor traffic, errors, and consumers still calling the old version.
6. End support only after the deadline expires and published notice policies are met.

Retain the OpenAPI snapshot of every released version for accurate comparison. The current documentation cannot replace the historical contract that clients built against.

## 11. Testing Contract Compatibility

Validating OpenAPI syntax is necessary but insufficient. A document can be structurally valid while still containing breaking changes or misrepresenting server behavior. Test across multiple layers:

1. **Validate specification:** check that JSON/YAML conforms to OpenAPI structure, schemas, and valid references.
2. **Diff specification:** compare the current document against the released version to catch changed endpoints, fields, parameters, enums, statuses, or security requirements.
3. **Classify changes:** evaluate request and response impact in both directions (old client calling new server and new client calling old server).
4. **Provider tests:** send requests per the contract and verify the server returns the documented statuses, headers, and bodies.
5. **Consumer tests:** verify clients handle actual responses, missing fields, new fields, and unknown enum values according to the chosen policy.
6. **Integration tests:** run critical consumers against the new provider version before release.

For example, a pipeline can fetch the OpenAPI document from the application running in a test environment:

```bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o build/openapi.json
```

Then save or fetch the baseline contract of the released version and run validate/diff tools in CI. When diff detects changes, the development team should review their meaning rather than automatically assuming every difference is breaking or safe.

### Scenarios to Include in the Test Suite

- Old requests lacking a newly added field are still accepted by the new server.
- New responses with an added property do not break deserialization in old clients.
- Clients handle unknown enums or status codes via designed fallback rules.
- Optional parameters, default values, and limits are enforced as documented.
- Error responses maintain a stable structure for published status codes.
- Consumer credentials, scopes, and permissions are preserved or have a migration path.
- New clients behave properly when connecting to an old server during parallel rollouts.

## 12. Workflow for Reviewing a Contract Change

Before merging controller or DTO changes, reviewers can follow this workflow:

1. Regenerate OpenAPI from the application and inspect the diff against the released contract.
2. Identify whether the change affects requests, responses, HTTP operations, security, or data semantics.
3. For each change, simulate old clients calling the new server and new clients calling the old server.
4. Check whether generated SDKs, frontends, and integrated services depend on changed fields, enums, `operationId`, or statuses.
5. Add provider/consumer tests for risky scenarios.
6. If incompatible, update versioning, migration docs, and support timelines.
7. Publish documentation alongside the application version so consumers can retrieve the matching contract.

A change is considered safe when evidence shows supported consumers continue working under the product's compatibility policy. For APIs used by multiple teams or customers, account for older clients that remain active after the server upgrades.

## 13. Compatibility Maintenance Checklist

- [ ] Provider, consumer, and compatibility direction under evaluation are identified.
- [ ] Old requests remain accepted after server changes.
- [ ] New responses do not break parsing or handling in existing clients.
- [ ] Required, optional, nullable fields, and default values are clearly defined.
- [ ] Enums, data types, formats, and schema limits are evaluated when changed.
- [ ] Paths, methods, parameters, status codes, headers, and media types are kept stable or have a migration plan.
- [ ] Business meaning changes are treated as contract changes.
- [ ] `operationId` stays stable if used for SDK generation.
- [ ] OpenAPI has been validated and diffed against the released version.
- [ ] Provider/consumer tests exist for risky scenarios.
- [ ] Breaking changes have a new version, migration guide, and appropriate support window.
- [ ] OpenAPI documents for each released version are archived for reference.

Contract compatibility determines whether independent applications can evolve together without disrupting integrations. Springdoc helps express the contract from Spring Boot source code; review workflows, specification diffs, and provider/consumer testing catch dangerous changes before release. By evaluating from both old-client and new-client directions, development teams can evolve APIs in a controlled way and keep services reliable for active consumers.
