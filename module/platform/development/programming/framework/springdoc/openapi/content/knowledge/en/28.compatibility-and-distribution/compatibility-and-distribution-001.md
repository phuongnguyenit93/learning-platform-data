# Identifying Consumer-Breaking Contract Changes

A change in OpenAPI can keep the provider running normally while causing existing consumers to fail to call the API or read responses properly. For example, adding a required query parameter, removing a response field, changing a data type, or requiring a new scope can all break an existing integration.

To evaluate properly, view the change from the consumer's perspective: will a client sending a request under the old contract still be accepted, and can a client reading a response under the old contract still process it? Request schemas and response schemas have opposite compatibility directions. The provider should continue accepting previously valid requests; new responses should remain within the range that existing consumers can understand.

This lesson explains how to identify breaking changes in paths, methods, parameters, request bodies, responses, schemas, security, and metadata used for SDK generation. It also guides you through comparing an OpenAPI document against a released baseline, integrating checks into CI, and managing exceptions when incompatible changes are necessary.

## 1. What is contract compatibility?

OpenAPI describes the contract between the provider and the consumer. The provider implements the endpoints; the consumer uses the contract to construct requests, parse responses, generate SDKs, or run integration tests.

A backward-compatible change generally allows consumers built against the prior contract to continue working without modifying code or configuration. A breaking change makes at least one behavior that was valid under the old contract unsupported, or prevents old consumers from processing the new response.

Three concepts should be distinguished:

| Concept | Question |
|---|---|
| Backward compatibility | Do old consumers continue working with the new provider? |
| Forward compatibility | To what extent can new consumers work with the old provider? |
| Contract compatibility | Do actual requests/responses still conform to the contract the consumer relies on? |

In API development, evaluation usually focuses on provider backward compatibility: upgrading the server without forcing all active consumers to upgrade simultaneously.

There is no single rule that holds true for every client. Clients generated from OpenAPI, hand-written clients, strict schema-validating clients, and clients that ignore unknown fields may react differently. Therefore, distinguish wire contract changes from changes that affect generated SDKs or usage conventions.

## 2. Evaluating request contracts and response contracts separately

The provider receives requests from consumers and returns responses to consumers. Because data flows in opposite directions, the same kind of change can yield different compatibility outcomes.

| Contract Area | What the provider must guarantee to preserve old consumers |
|---|---|
| Request | Continue accepting requests valid under the old schema |
| Response | Continue returning data that old consumers can read and process |
| Authentication | Old credentials and permissions remain sufficient under the committed policy |
| Routing | Old paths, methods, and server URLs remain accessible |
| Serialization | Old field names, data types, and media types do not change unexpectedly |

Examples:
- Adding an accepted value to a request enum usually expands what the provider can accept.
- Adding a new enum value to a response expands what the provider can return; old consumers might not recognize that value.
- Adding an optional request field usually does not require old clients to send it.
- Removing a response field that old clients read can cause client errors or data loss.

Do not evaluate compatibility merely by checking whether the OpenAPI document is still valid or whether the server still returns HTTP 200. Consider the set of requests and responses that can occur before and after the change.

## 3. Changes to paths, HTTP methods, and operations

These changes usually directly affect every consumer calling the endpoint:

| Change | Typical Assessment | Reason |
|---|---|---|
| Remove a published path | Breaking | Consumers no longer have the old endpoint |
| Rename/change a path | Breaking | The URL clients call no longer matches |
| Remove an HTTP method on a path | Breaking | The old request method is no longer supported |
| Change method GET to POST | Breaking | Old clients send a different method than the new route expects |
| Add a new path/method | Usually non-breaking | Old consumers are not forced to use the new operation |
| Change trailing slash or path casing | Potentially breaking | Routing and proxies may distinguish URLs |
| Change server URL | Potentially breaking | Clients may continue calling the old host/base path |

Baseline example:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      responses:
        "200":
          description: Order found
~~~

The new version moves the endpoint to `/api/order/{id}`:

~~~yaml
paths:
  /api/order/{id}:
    get:
      operationId: getOrderById
      responses:
        "200":
          description: Order found
~~~

Even though the response is unchanged, old clients still call `/api/orders/{id}`. This is a routing breaking change.

A safer transition is to keep the old path for a period, publish the new path, monitor usage of the old path, and only remove it after an announced migration deadline. If URL versioning is needed, keep the old version running in parallel during the transition period.

## 4. Parameter changes

A parameter is defined by its name, location (`in`), data type, `required` flag, serialization, and constraints. Changing any of these attributes can affect the requests consumers construct.

### 4.1. Adding a required parameter

Baseline:

~~~yaml
parameters:
  - name: id
    in: path
    required: true
    schema:
      type: string
~~~

The new version adds a required tenant header:

~~~yaml
parameters:
  - name: id
    in: path
    required: true
    schema:
      type: string
  - name: X-Tenant-Id
    in: header
    required: true
    schema:
      type: string
~~~

Old clients do not send `X-Tenant-Id`, so requests may be rejected. This is a breaking change if the provider previously accepted requests without this header.

If tenant context needs to be added, you can implement a mechanism to infer the tenant from existing credentials or allow the header to be optional during a transition period. Only mark it required once consumers are sending the property and the rollout plan permits it.

### 4.2. Changing parameter name, location, or type

The following changes typically break existing requests:
- Renaming query parameter `page` to `pageNumber`.
- Renaming header `X-Client-Id` to `X-Partner-Id`.
- Moving a parameter from query to header.
- Changing type `string` to `integer`.
- Renaming a path placeholder from `/orders/{id}` to `/orders/{orderId}` usually does not change the actual wire URL, but can rename parameters in generated SDKs or consumer code.
- Changing `style`, `explode`, or array/object encoding so requests are serialized differently.

To transition a parameter name, you can temporarily accept both the old and new names. However, if both values are sent together, the provider must clearly define precedence or return an error to avoid ambiguous behavior.

### 4.3. Adding an optional parameter

Adding an optional query parameter is usually compatible with old consumers because old requests can omit the parameter:

~~~yaml
- name: includeArchived
  in: query
  required: false
  schema:
    type: boolean
    default: false
~~~

This is only safe if the provider actually has appropriate default behavior when the parameter is omitted and does not alter the meaning of old requests. An optional parameter that changes the endpoint's default behavior can still be a behavioral breaking change even if schema diff reports no error.

## 5. Request body and request schema changes

The request schema describes the data the provider accepts. When upgrading a provider, maintaining compatibility usually means not rejecting payloads that were valid under the old schema.

### 5.1. Adding a required property

Baseline:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId]
  properties:
    customerId:
      type: string
~~~

New version:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, source]
  properties:
    customerId:
      type: string
    note:
      type: string
    source:
      type: string
~~~

Old consumers only send `customerId`; previously valid payloads are now rejected. This is a breaking change.

If the new property can have a default value, keep it optional and handle missing values on the server during the transition period. Once consumers are sending the property, you can consider raising it to `required` in a major version.

### 5.2. Tightening request constraints

Suppose the server previously accepted name strings up to 120 characters:

~~~yaml
name:
  type: string
  maxLength: 120
~~~

The new version reduces it to 40:

~~~yaml
name:
  type: string
  maxLength: 40
~~~

Old consumers may send 80-character names that were previously valid requests. Now the provider rejects them. This is a request contract breaking change.

Changes that narrow the set of valid requests typically need to be flagged:
- Adding `required`.
- Increasing `minLength`, `minimum`, `minItems`.
- Decreasing `maxLength`, `maximum`, `maxItems`.
- Adding `pattern` or a new constraint.
- Removing a value from an allowed enum.
- Changing a schema from nullable to non-nullable.
- Setting `additionalProperties: false` so old fields are no longer accepted.

Conversely, relaxing constraints generally widens the set of requests the provider accepts. For example, increasing `maxLength`, removing a limit, or allowing additional enum values in a request usually does not force old clients to change.

### 5.3. Removing or renaming a request property

Removing a property that consumers still send can cause requests to fail if the provider rejects unknown fields, or cause data to be ignored and alter business behavior.

Renaming a property has a similar effect:
- Old clients send `customerId`.
- The new server only reads `clientId`.
- The old value is not bound or validation fails.

For transition, you can temporarily accept both fields, clearly define precedence, and emit a warning when clients use the old name. Do not keep two alias fields indefinitely if they can carry conflicting values.

## 6. Response schema changes

The response schema describes the data the provider can return. Old consumers typically depend on published fields, data types, enums, and status codes.

### 6.1. Removing a response property

Baseline:

~~~yaml
OrderResponse:
  type: object
  properties:
    id:
      type: string
    status:
      type: string
    total:
      type: number
~~~

The new version removes `total`. Old clients reading `total` may receive null, suffer mapping errors, or lose business data. This is a breaking change.

If `total` needs to be replaced by a new structure, you can add the new field alongside it, keep the old field marked `deprecated`, and schedule its removal in a subsequent major version.

### 6.2. Changing a response property's type

Changes such as:
- `integer` to `string`.
- `number` to a Money object.
- `string` to an array.
- `date` to `date-time`.
- Object becoming nullable or potentially missing.

can all cause clients to parse responses incorrectly or change generated SDK types. Treat them as breaking changes unless there is evidence that the consumer contract permits the transition.

### 6.3. Removing `required` from a response property

If a response previously guaranteed that `id` is always present:

~~~yaml
required: [id, status]
~~~

and the new version removes `id` from `required`, the provider is permitted to omit `id`. Old consumers relying on this guarantee may fail when the field is absent. This is usually a breaking change because the provider has weakened a response guarantee.

Conversely, adding a property to a response's `required` list makes the provider commit to returning that property, which is generally a guarantee-strengthening change. However, check the actual runtime serializer and generated clients before concluding it is safe.

### 6.4. Adding a response property

Adding an optional field to a JSON response is usually considered an additive change:

~~~yaml
properties:
  id:
    type: string
  status:
    type: string
  trackingUrl:
    type: string
~~~

However, some consumers use strict deserializers and reject unknown properties. Therefore, this change is generally compatible with tolerant clients rather than an absolute guarantee for every consumer. If the ecosystem has strict deserialization, check the Jackson configuration or SDK generator in use.

## 7. Enum changes: requests and responses have opposite impact directions

Enums are an often-overlooked source of breaking changes.

### Request enum

If a provider accepts `statusFilter` with values `NEW`, `PAID`, `CANCELLED`, removing `CANCELLED` causes old requests using that value to be rejected. This is a breaking change.

Adding a request enum value usually expands the set of values the provider accepts. Old consumers do not need to use the new value, so they are generally unaffected.

### Response enum

If a provider can return `status: NEW | PAID`, and then adds `REFUNDED`, the response value set expands. Old clients using exhaustive `switch` statements or generated enums may fail to handle the new value. This can be a breaking change for strict consumers.

Removing a response enum value narrows the output set, which is usually lower risk because consumers will no longer encounter that value. However, if consumers rely on a specific status appearing to complete a workflow, this change can still affect behavior.

| Enum Location | Add value | Remove value |
|---|---|---|
| Request | Usually additive: provider accepts more inputs | Usually breaking: provider rejects old inputs |
| Response | Potentially breaking for strict/exhaustive clients | Usually narrows output, but workflow impact must be checked |

For response enums, encourage consumers to have a fallback branch handling unrecognized values. For request enums, the provider should maintain old values during the committed migration period.

## 8. Changes to response codes, media types, and headers

Consumers often dispatch logic based on status code and content type. Changing them can break clients even when the JSON body is unchanged.

| Change | Impact |
|---|---|
| Remove a published response code | Clients no longer receive the old behavior |
| Change 200 to 204 | Clients may still expect a response body |
| Change 201 to 200 | Clients handling creation/`Location` may break |
| Remove `application/json` media type | Clients no longer receive the old representation |
| Change response body media type | Parser/client content negotiation may fail |
| Remove a response header used by consumers | Clients lose metadata such as `Location` or `ETag` |
| Add a new response code | Usually additive, but strict clients may need to handle the new branch |

Adding a new response code usually does not break tolerant clients, though some SDKs generating union types or code requiring all statuses to be handled may be affected upon regeneration.

If changing error behavior, preserve old status codes and error schemas during a transition period or publish clear migration guidance. Do not replace 404 with 200 and an empty body just to avoid returning an error; that alters semantics consumers may rely on.

## 9. Changes to security requirements and access permissions

Adding or tightening authentication can prevent old clients from calling the API:

- A previously public endpoint now requires a Bearer token.
- Old scope `orders:read` is replaced with a new scope `orders:read:all`.
- An API key moves from an old header to a new header.
- The OAuth2 flow or issuer changes.
- Token audience or client registration changes so existing tokens are no longer accepted.

These are usually breaking changes in the runtime contract, even if paths and schemas do not change.

Conversely, removing a security requirement may not break old consumers' ability to call the API, but can create a security vulnerability. Compatibility is not the only criterion when deciding on a security change.

When changing a scope or scheme:
1. Announce the new scope and transition deadline.
2. Allow both old and new credentials to work concurrently if security policy permits.
3. Update clients and test 401/403 responses.
4. Monitor usage of the old scope.
5. Revoke the old scope on the announced schedule.

## 10. `operationId`, schema names, and impact on generated SDKs

Not every breaking change causes HTTP requests to fail. Some changes affect SDK source code generated from OpenAPI.

Examples:
- Renaming `operationId: getOrderById` to `readOrder`.
- Renaming component schema `OrderResponse` to `OrderView`.
- Changing tags that alter package/class grouping in some generators.
- Renaming properties or enum constants.
- Changing discriminator mappings.

If clients regenerate their SDK, method/class names may change and break compilation even though the wire contract remains compatible. Therefore, for projects distributing SDKs, `operationId`, component schema names, and tags should be treated as part of the compatibility policy.

Purely descriptive changes such as editing `summary`/`description`, adding examples, or fixing typos usually do not break the wire contract. However, if a generator uses metadata to name symbols, even `operationId`/tag changes can affect source compatibility.

When evaluating a diff, separate two layers:
- **Wire compatibility:** do HTTP requests and responses still work?
- **SDK/source compatibility:** do consumers regenerating clients have to modify their code?

## 11. Combined example: which change should be blocked?

Suppose the baseline has an order creation operation:

~~~yaml
paths:
  /api/orders:
    post:
      operationId: createOrder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        "201":
          description: Created
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId]
      properties:
        customerId:
          type: string
        note:
          type: string
~~~

The new version adds `channel` to `required`:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, channel]
  properties:
    customerId:
      type: string
    note:
      type: string
    channel:
      type: string
      enum: [WEB, MOBILE]
~~~

Old consumers only send `customerId`, so old payloads are no longer valid. This is a breaking change.

If `channel` is added without being in `required`, the server can assign a default when old clients omit it. This is usually an additive change:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId]
  properties:
    customerId:
      type: string
    note:
      type: string
    channel:
      type: string
      enum: [WEB, MOBILE]
      default: WEB
~~~

Even so, the default must be enforced in runtime code; the `default` value in OpenAPI is primarily metadata and does not automatically make Spring populate the value in the request DTO.

## 12. Distinguishing breaking, non-breaking, and behavioral changes

A diff tool marking a change as non-breaking does not mean the change cannot affect consumers. Distinguish:

| Change Type | Example | How to Handle |
|---|---|---|
| Breaking wire change | Remove path, add required request field, change response type | Major version or timed migration |
| Additive contract change | Add operation, add optional request parameter | Usually minor version; still check strict clients |
| Documentation-only | Edit description, example, or typo | Usually patch/documentation update |
| Behavioral change | Same schema but changed default, processing order, status semantics | Contract tests and release notes |
| Security change | Require new scope or change issuer | Evaluate separately; usually requires migration |
| SDK source change | Rename `operationId`, schema name, or tag | Check generated SDK compilation |

OpenAPI diff primarily compares document structure. It does not know full business semantics, side effects, rate limits, latency, or actual runtime data returned by the provider. Therefore, combine diff checks with contract tests, integration tests, and consumer impact assessments.

## 13. Comparing against a baseline with an OpenAPI diff tool

Do not compare the current file only against an arbitrary previous commit. The baseline should be the released contract or the one consumers rely on as the standard, such as the OpenAPI artifact from the latest production release.

A popular tool is `oasdiff`. Basic command:

~~~bash
oasdiff breaking openapi-released.yaml openapi-current.yaml
~~~

The tool compares the baseline and the current document, then reports changes classified as breaking according to that tool version's rule set.

You can inspect the general diff:

~~~bash
oasdiff diff openapi-released.yaml openapi-current.yaml
~~~

Place baseline and current in the right order:
- Baseline: the released document.
- Current: the document generated from the branch under check.

Read the output rather than relying solely on the exit code. Some changes may be classified as breaking by the tool yet conditionally accepted by the project; conversely, behavioral changes or SDK naming changes may require manual review even if the tool does not flag them.

Pin the `oasdiff` version in CI so the rule set does not silently change between builds. When upgrading the tool version, re-run it on several known baseline/current pairs to understand classification differences.

## 14. Integrating breaking-change checks into CI

A basic pipeline might include:

~~~mermaid
flowchart TD
    A[Build Spring Boot application] --> B[Export OpenAPI document]
    B --> C[Validate OpenAPI syntax]
    C --> D[Compare with released baseline]
    D --> E{Breaking change?}
    E -- No --> F[Run contract tests]
    E -- Yes --> G[Require version/migration review]
    G --> H{Approved exception?}
    H -- No --> I[Fail pipeline]
    H -- Yes --> F
    F --> J[Publish artifact and report]
~~~

Shell example in CI:

~~~bash
# Generate the OpenAPI document from the started test application
curl -fsS http://localhost:8080/v3/api-docs -o openapi-current.json

# Compare against the artifact from the latest release
oasdiff breaking openapi-released.json openapi-current.json
~~~

If the tool returns a non-zero exit code when breaking changes are detected, CI can fail the job. Check the exit code behavior of the pinned tool version and configure the pipeline according to that version's documentation.

The pipeline should store:
- The baseline artifact and its corresponding release version.
- The new OpenAPI document.
- The diff report.
- The validator/diff tool version.
- Contract test results.
- Any acceptance or exception decisions.

Do not generate a new baseline from the branch being tested and compare against itself; doing so eliminates the ability to detect changes against the released contract.

## 15. Managing versions and migrations for breaking changes

If a breaking change is necessary, manage the transition process:

1. Identify which consumers use the affected operation or schema.
2. Announce the reason, timeline, and migration guide.
3. Create a new API version or a parallel compatibility period according to policy.
4. Maintain the old endpoint/schema for the announced duration.
5. Provide new request/response examples and mappings from old fields to new fields.
6. Monitor usage of the old version.
7. Remove it only after consumers have migrated or the support window expires.

SemVer is often applied to API or SDK versions according to product policy:
- Major: incompatible changes.
- Minor: compatible feature additions.
- Patch: bug fixes or updates that do not alter the contract under policy.

The `info.version` field in OpenAPI is the project-managed API version. The `openapi` field is the specification format version. Changing `openapi: 3.0.3` to `3.1.0` does not automatically constitute a major API release; conversely, changing `info.version` does not automatically give runtime endpoints a new version.

If using URL versioning such as `/v1` and `/v2`, maintain routes and documentation for each version. If versioning via headers or media types, clearly document how representations are selected and test content negotiation properly.

## 16. When are exceptions needed?

Not every breaking change can be avoided. For example, security vulnerabilities, corrupted data, or invalid endpoints may force the provider to change quickly.

An exception should clearly document:
- Which diff rule is exempted.
- Affected path/operation/schema.
- Impacted consumers and owner.
- Reason compatibility cannot be maintained.
- Version or effective date.
- Migration path and deadline.
- Approver and tracking ticket.

Do not disable the entire breaking-change check just because one operation needs to change. Create a narrow, time-bounded allowlist scoped by rule/path/version; if supported by the tool, store the exception configuration file alongside code-owner reviews.

## 17. Checklist for reviewing an OpenAPI diff

- [ ] Compare against the released baseline, not just an arbitrary document from a prior branch.
- [ ] Old paths and HTTP methods still exist.
- [ ] Old parameters retain their names, locations, types, and serialization.
- [ ] No unplanned required request parameters were added.
- [ ] Old request bodies are still accepted.
- [ ] No request enums or constraints currently used by consumers were tightened.
- [ ] Important response codes and media types remain supported.
- [ ] Old response properties were not unexpectedly removed or retyped.
- [ ] New response enums have been evaluated against strict clients.
- [ ] Security schemes and scopes have not changed unexpectedly.
- [ ] `operationId`, schema names, and tags are reviewed if SDKs are generated.
- [ ] Server URLs and versioning strategy remain accurate.
- [ ] Diff tool and validator versions are pinned.
- [ ] Contract tests cover happy paths and important responses.
- [ ] Breaking changes have a migration guide, version plan, and approval.

## References

- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): structure of paths, operations, parameters, request bodies, responses, and schemas.
- [oasdiff](https://github.com/Tufin/oasdiff): tool for comparing OpenAPI documents and detecting breaking changes.
- [Google Cloud – API Design Guide](https://cloud.google.com/apis/design): guidelines for designing stable and compatible APIs.
- [Microsoft REST API Guidelines](https://github.com/microsoft/api-guidelines): conventions for API design and evolution.
- [Semantic Versioning](https://semver.org/): rules for major, minor, and patch versions.
- [Pact – Consumer Driven Contracts](https://docs.pact.io/): contract testing between consumers and providers.
