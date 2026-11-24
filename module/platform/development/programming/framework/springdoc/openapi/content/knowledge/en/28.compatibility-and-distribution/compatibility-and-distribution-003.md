# Narrowing Enums, Changing Types, Formats, or Status Codes

## 1. Why can small changes break clients?

A change in a Java DTO can alter the OpenAPI document even when the path and HTTP method stay the same. For example, the development team removes an enum value, changes a property from `integer` to `string`, changes a format from `date` to `date-time`, or replaces a `200` response with `204`.

These changes can make clients generated from the older OpenAPI document incompatible. Clients may fail to parse JSON, fail to deserialize the data type, reject a new enum value, or enter an error-handling branch when the server returns a different status.

When evaluating compatibility, look at which direction data flows:

- **Request**: clients send data; the server must continue accepting requests that old clients currently send.
- **Response**: the server sends data; old clients must continue reading and processing responses that the new server may return.

The same change can be safe in a request yet risky in a response. For instance, adding an enum value to the set accepted by the server usually expands the API's capabilities. However, adding an enum value that the server can return may break old clients if they use a closed enum and lack a fallback branch.

Springdoc OpenAPI reflects Java types, validation, and annotations into schemas, parameters, request bodies, and responses. Therefore, model or annotation changes should be inspected in the OpenAPI document and compared against the published contract.

## 2. Distinguishing request compatibility and response compatibility

You can use the following principle as a guide:

| Schema Location | What the new server must guarantee | Typically risky changes |
|---|---|---|
| Request body | Continue accepting valid requests from old clients | Adding required fields, removing accepted enum values, narrowing ranges or formats |
| Query/path/header parameter | Continue accepting old call styles | Renaming, changing type, changing location, or changing optional to required |
| Response body | Old clients continue reading every new response | Changing type, adding unknown enum outputs, removing fields clients need |
| Response status | Old clients handle statuses returned by the new server | Changing status, removing an old status, or changing body semantics |
| Response headers | Old clients do not lose needed metadata | Removing or changing headers clients depend on |

A change is compatible only when considering both schema and runtime behavior. For example, if OpenAPI marks a property nullable yet the server always omits the field or serializes it as an empty string, clients can still fail.

Do not assess compatibility solely by checking that the new document validates cleanly. Compare it against the old document and understand how clients consume the API.

## 3. How are enums in OpenAPI generated from Java?

A Java enum is usually converted by Springdoc into a string schema with a list of allowed values:

~~~java
public enum OrderStatus {
    NEW,
    CONFIRMED,
    SHIPPED,
    DELIVERED,
    CANCELLED
}
~~~

DTO:

~~~java
public record OrderResponse(
    String orderId,
    OrderStatus status
) {
}
~~~

The corresponding OpenAPI schema may look like:

~~~yaml
OrderResponse:
  type: object
  properties:
    orderId:
      type: string
    status:
      type: string
      enum:
        - NEW
        - CONFIRMED
        - SHIPPED
        - DELIVERED
        - CANCELLED
~~~

The enum list is part of the contract. Client generators can produce a corresponding enum type in Java, Kotlin, TypeScript, C#, or other languages.

If you rename a constant, remove a constant, or add a constant, the schema changes. Even though JSON still carries a string, clients with generated closed enums may reject values outside the list.

Treat enums as public API value sets, not merely internal Java details.

## 4. Narrowing an enum in a request is a breaking change

Suppose the old API accepted:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
    - CANCELLED
~~~

Old clients can send `CANCELLED`. If the new server removes that value:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
~~~

the server has narrowed the set of accepted requests. Old clients send a request that was valid under the previous contract but is rejected under the new contract.

This is a request-side breaking change. Similarly, if the server stops accepting any published enum value, a migration or a new API version is required.

A safer transition approach is:

1. Keep the old enum value during the transition period.
2. Mark the old value as deprecated in documentation if tooling supports it.
3. Announce the replacement value and removal deadline.
4. Monitor live requests still using the old value.
5. Remove it only after the support window expires or when releasing a new API version.

Do not delete an enum value just because internal applications no longer use it; external clients may still send it.

## 5. Adding enum values differs between requests and responses

Adding a value to a request enum usually expands the dataset the server accepts:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
    - RETURNED
~~~

Old clients can still send the old values. If the new server additionally accepts `RETURNED`, this is generally a compatible change on the request side.

However, adding a value to a response enum can break clients:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
    - RETURNED
~~~

The new server may return `RETURNED` for an order. Old clients generated from the old enum may:

- Throw an exception during deserialization.
- Map it to `null` or `UNKNOWN`.
- Reject the response.
- Fail to handle the new business branch.
- Overwrite data when re-serializing.

Therefore, adding a response enum value is a risky change and many compatibility tools warn about it. The severity depends on whether clients handle unknown enum values.

To extend response enums more safely, design clients with an `UNKNOWN` fallback, use `string` when appropriate, or add a new field instead of altering the existing enum. For published public APIs, treat adding a response enum value as a change requiring careful evaluation.

## 6. Removing an enum value in a response

If the new server no longer returns an old value, the response set may narrow:

~~~yaml
status:
  type: string
  enum:
    - NEW
    - CONFIRMED
    - SHIPPED
~~~

For clients that already handled all old values, the server no longer returning certain values usually does not cause client parsing errors when reading responses. However, a client might rely on that value to execute a business workflow, or the contract might promise that the status can still occur.

Thus, removing a response enum value is usually less dangerous for deserialization than adding a new value, yet can still be a behaviorally incompatible change.

Distinguish:

- **Schema compatibility**: whether clients can parse the value.
- **Behavioral compatibility**: whether clients still function properly when the value never or no longer appears.

A contract diff tool may classify enum changes using general rules. Results should be reviewed alongside business semantics.

## 7. Representing enums with `@Schema` in Springdoc

Springdoc usually infers enums from Java enums. When clearer descriptions are needed, you can use `@Schema`:

~~~java
@Schema(description = "Order status")
public enum OrderStatus {
    NEW,
    CONFIRMED,
    SHIPPED,
    DELIVERED,
    CANCELLED
}
~~~

You can describe `allowableValues` on a property:

~~~java
public record OrderFilter(
    @Schema(
        description = "Filter by status",
        allowableValues = {"NEW", "CONFIRMED", "SHIPPED"}
    )
    String status
) {
}
~~~

Be careful when using `allowableValues` to narrow a Java enum or string property. The annotation changes the published contract; it does not by itself guarantee that the service layer or validation actually rejects values outside the list.

If the API uses a Java enum as a request type, runtime validation and binding must stay in sync with the schema. If the schema states only three values are allowed while the controller still accepts others, the document does not reflect actual behavior.

Do not use `@Schema` to mask a breaking change. Update code, validation, OpenAPI, and tests according to the same rule.

## 8. Enums whose wire values differ from constant names

Some systems need to keep Java constant names different from public JSON strings. Example:

~~~java
public enum PaymentState {
    @JsonProperty("awaiting-payment")
    PENDING,

    @JsonProperty("paid")
    COMPLETED,

    @JsonProperty("payment-failed")
    FAILED
}
~~~

The wire values serialized/deserialized by Jackson can differ from the constant names. The OpenAPI document must reflect the actual JSON values clients send and receive.

Check `/v3/api-docs` after adding `@JsonProperty`. If the schema still displays `PENDING`, `COMPLETED`, `FAILED` while runtime JSON uses `awaiting-payment`, `paid`, `payment-failed`, the contract and serialization are out of sync.

Do not change wire values just to make Java names look cleaner. For published enums, JSON values are part of the contract and must be managed as an API change.

## 9. Changing data types is a contract change

The OpenAPI schema defines the `type` of properties and parameters. Example:

~~~yaml
quantity:
  type: integer
  format: int32
~~~

If the server changes it to:

~~~yaml
quantity:
  type: string
~~~

old clients may fail to parse responses or serialize requests with the wrong type. This is usually a breaking change.

Common type changes:

| Old Type | New Type | Risk |
|---|---|---|
| integer | string | Breaking: JSON type changes |
| string | integer | Breaking: clients send/read the wrong type |
| integer/int32 | integer/int64 | Potentially breaking due to range and generated code type changes |
| number/double | string | Breaking: numeric value becomes text |
| object | array | Breaking: JSON structure changes |
| array | object | Breaking: JSON structure changes |
| string | object | Breaking: scalar becomes object |
| boolean | string | Breaking: boolean becomes text |

Do not rely on a parser possibly performing automatic type coercion. Client generators, validation, and target languages behave differently.

If a type conversion is needed, usually create a new property, keep the old property during a transition period, and release a new API version if clients must migrate together.

## 10. Changing integer range and numeric precision

JSON has a single generic `number` type, whereas OpenAPI uses `type` and `format` to describe `integer`, `int32`, `int64`, `float`, or `double`.

Example:

~~~yaml
quantity:
  type: integer
  format: int32
price:
  type: number
  format: double
~~~

If `int32` changes to `int64`, payloads may still be JSON numbers, but client generators may switch from `Integer` to `Long` or from `number` to `bigint` depending on the language. Values exceeding the old range may not be representable in old clients.

Changing `double` to decimal or string can affect precision, serialization, and calculations. For currency, pick an explicit representation such as integer minor units or decimal strings per contract, and keep it stable.

If you only increase `maximum` in a request schema, the server can accept more values. This is usually a request-side expansion. However, if the server starts returning values beyond the range old clients support, that can be a response-side breaking change.

Check `type`, `format`, `minimum`, `maximum`, `multipleOf`, and runtime serialization together.

## 11. Changing string formats

OpenAPI commonly uses `type: string` with `format` to describe structured data:

~~~yaml
createdAt:
  type: string
  format: date-time
birthDate:
  type: string
  format: date
email:
  type: string
  format: email
uuid:
  type: string
  format: uuid
~~~

Changing `format` can affect code generation and validation:

| Old Format | New Format | Impact |
|---|---|---|
| date | date-time | Adds time and timezone; client type may change |
| date-time | date | Loses time information |
| uuid | unformatted string | May lose UUID type in clients |
| int64 | decimal or string | Changes parsing and range |
| binary | byte/base64 | May change encoding or media handling |

`format` is a meaningful hint to tooling. Not all validators enforce every format identically, yet client generators may map formats to native types.

Java DTO example:

~~~java
public record OrderResponse(
    LocalDate deliveryDate,
    OffsetDateTime createdAt
) {
}
~~~

Springdoc and Jackson can represent `LocalDate` as `date` and `OffsetDateTime` as `date-time` depending on converter configuration. Verify the actual JSON, timezone, and serialization format after changing Java types.

## 12. Changing `nullable` and `required`

`required` and `nullable` are two distinct concepts:

- `required` specifies whether a property must appear in an object.
- `nullable` specifies whether `null` values are accepted according to the schema/version.

Example of an optional but non-nullable property:

~~~yaml
nickname:
  type: string
~~~

A property that is `required` yet allows `null` in OpenAPI 3.1:

~~~yaml
required:
  - middleName
properties:
  middleName:
    type:
      - string
      - "null"
~~~

If the new server requires a field that old clients do not send, requests may be rejected. This is a request-side breaking change.

If the new response drops a field that old clients expect to always be present, clients may fail or display incorrect data. If a response field switches from non-null to nullable, old clients may encounter `null` unexpectedly.

When changing `required`/`nullable`, check JSON Schema, Jackson serialization, Bean Validation, and client generators together. Never treat optional and nullable as synonyms.

## 13. Changing validation constraints

Schemas can contain constraints such as:

~~~yaml
quantity:
  type: integer
  minimum: 1
  maximum: 100
name:
  type: string
  minLength: 1
  maxLength: 80
~~~

Tightening request constraints can cause the server to reject data old clients used to send:

- Decreasing `maximum`.
- Increasing `minimum`.
- Decreasing `maxLength`.
- Increasing `minLength`.
- Narrowing `pattern`.
- Reducing the maximum number of array items.
- Adding a `required` property.

These are usually request-side breaking changes.

Relaxing request constraints, such as increasing `maximum` or `maxLength`, usually allows more data and rarely breaks old clients. However, backend and database limits must support the new range.

For responses, narrowing the set of values the server can return usually does not cause parse errors, though it may alter business behavior. Widening response constraints may expose old clients to unknown values or data larger than they can process.

Jakarta validation annotations such as `@Min`, `@Max`, `@Size`, `@Pattern`, and `@NotNull` can be used by Springdoc to generate schema constraints. Inspect the document after changing annotations.

## 14. Changing HTTP status codes is a behavioral change

HTTP status codes are a vital part of the contract. Clients may rely on status codes to decide retries, error display, routing, or state updates.

Risky changes include:

| Change | Possible Impact |
|---|---|
| 200 to 201 | Clients may not expect Created or a `Location` header |
| 200 to 204 | Response body disappears |
| 404 to 200 with empty body | Clients can no longer identify non-existent resources |
| 400 to 422 | Client error classification logic changes |
| 401 to 403 | Client login/authorization flow may misfire |
| 409 to 200 | Conflict is no longer represented as before |
| Removing 429 | Clients no longer receive rate-limit signals |
| Adding a new status | Clients using closed `switch` statements may fail to handle it |

Do not treat statuses within the same 2xx or 4xx family as interchangeable. `200 OK`, `201 Created`, and `204 No Content` carry different semantics.

If you want to add a new status for a new scenario, document it in OpenAPI and ensure clients have a default branch handling unknown responses. If replacing an old status, assess migration and versioning.

## 15. Documenting response statuses with Springdoc

Springdoc can infer responses from return types and annotations, but important responses should be documented explicitly.

Example:

~~~java
@PostMapping
@Operation(summary = "Create order")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order created",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request"
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Order conflict"
    )
})
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    OrderResponse response = orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
}
~~~

Annotations describe the document; `ResponseEntity` and exception handlers determine the runtime status. Keep both parts consistent.

If the annotation says `201` while the controller actually returns `200`, clients receive an inaccurate contract. Test the actual HTTP status and the OpenAPI response together.

For default responses or error responses produced by `@ControllerAdvice`, you can use `@ApiResponse` or `OpenApiCustomizer` to document standard error schemas across operations.

## 16. Do not change `200` to `204` if the body is still needed

`204 No Content` means the response contains no content body. If the old API returned:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "status": "DELETED"
}
~~~

and the new API returns `204`, old clients no longer receive the JSON body to read `id` or `status`.

If the goal is merely to report operation success, `204` can be an appropriate design for a new API. For a published endpoint, however, this is a contract change. You can retain the old `200` response in the current version and use `204` for a new endpoint/version.

Similarly, do not change `204` to `200` with a body without checking client generators and client code. Some clients generate methods returning `void`; changing the response body may not be handled as expected.

## 17. Error responses and standard error schemas

Keep error responses consistent across operations. Example schema:

~~~java
public record ApiError(
    String code,
    String message,
    String traceId
) {
}
~~~

OpenAPI:

~~~yaml
responses:
  '400':
    description: Invalid request
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ApiError'
  '404':
    description: Resource not found
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ApiError'
  '409':
    description: Business conflict
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ApiError'
~~~

Changing an error body from an object to a string or renaming properties can break clients parsing `ApiError`. Changing an error status while keeping the body can still send clients down the wrong branch.

Define a stable error contract and reuse component schemas. If new error details are needed, consider retaining old properties and adding optional fields so old clients continue working.

## 18. Deprecation before removing enums, fields, or statuses

When removing an enum value, property, or operation, announce it in advance:

- Mark the operation/property `deprecated` if the OpenAPI element supports it.
- For enum values, use `description` or an extension following organizational conventions if tooling does not support per-value deprecation.
- Publish the replacement value or endpoint.
- Provide an end-of-support deadline.
- Monitor traffic to identify clients still using it.
- Provide a migration guide.
- Remove it only after the deadline expires and under an appropriate versioning policy.

Example of a `deprecated` property:

~~~java
public record PaymentRequest(
    @Schema(
        description = "Legacy status code, will be discontinued after the announced date.",
        deprecated = true
    )
    String legacyStatus
) {
}
~~~

Not every Swagger annotations version has a portable way to mark individual enum constants as deprecated. You can describe it clearly in the schema description or a vendor extension, but align conventions with tooling.

Deprecation is a signal for clients to plan migration; it does not automatically prevent the server from receiving old values.

## 19. Using versioned endpoints when compatibility cannot be kept

If a change must break the contract, you can release a new API version:

~~~text
/api/v1/orders
/api/v2/orders
~~~

For example, v1 uses the old status enum and v2 uses the new enum. Both versions can have separate DTOs, controllers, and OpenAPI document groups.

Springdoc can separate documents by group:

~~~java
@Bean
GroupedOpenApi v1Api() {
    return GroupedOpenApi.builder()
        .group("v1")
        .pathsToMatch("/api/v1/**")
        .build();
}

@Bean
GroupedOpenApi v2Api() {
    return GroupedOpenApi.builder()
        .group("v2")
        .pathsToMatch("/api/v2/**")
        .build();
}
~~~

Group documentation endpoints usually take the form `/v3/api-docs/v1` and `/v3/api-docs/v2`. Verify the exact URLs based on your Springdoc configuration.

Do not create a new version solely because the application build version increases. A new API version should reflect an intentional contract change with a client support plan.

## 20. Checking compatibility with OpenAPI diff

Contract diff compares the old and new documents to locate changes in paths, parameters, schemas, enums, responses, and security.

You can use `oasdiff`:

~~~bash
oasdiff breaking previous/openapi.yaml candidate/openapi.yaml
~~~

Pin the tool version in CI and store baselines of published releases. Do not compare a candidate against an untracked latest document of unclear origin.

When reviewing results, pay attention to:

- Enum values added or removed in requests or responses.
- Changes to property `type` and `format`.
- Changes to `required`, `nullable`, and validation constraints.
- Whether old status codes were removed or altered.
- Whether response content/media types changed.
- Whether security requirements force clients to obtain new credentials.

Diff tools do not know all business semantics or how clients deserialize. Warnings must be evaluated alongside contract tests and client behavior.

## 21. Testing schemas and statuses with `MockMvc`

You can test the OpenAPI document generated by Springdoc:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.OrderStatus.enum"
    ).isArray())
    .andExpect(jsonPath(
        "$.paths['/api/orders'].post.responses['201']"
    ).exists());
~~~

Schema and operation paths should be adjusted to match the actual document. If an enum lives inside another schema or is inlined, the JSONPath must point to the exact location.

Testing runtime responses:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "status": "NEW"
            }
            """))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.status").value("NEW"));
~~~

Add tests covering:

- Every request enum value still supported.
- Invalid enum values rejected per contract.
- Response enums containing values clients expect.
- Correct JSON serialization types.
- Correct date/time formats and timezones.
- Important status codes returned accurately.
- Response bodies present or absent matching the status.

Contract tests verify the document; integration tests verify runtime. Both should run in the pipeline.

## 22. Matrix for evaluating common changes

| Change | Request | Response |
|---|---|---|
| Remove enum value | Breaking: server rejects old input | Usually no parse error, but may change semantics |
| Add enum value | Usually expands accepted input | Potentially breaking for closed-enum clients |
| Change type | Usually breaking | Usually breaking |
| Increase numeric maximum | Expands input, usually compatible | May send numbers outside old client range |
| Decrease numeric maximum | Narrows input, breaking | Narrowing output may change semantics |
| Change `date` to `date-time` | Changes input format, usually breaking | Clients may fail to parse |
| Optional to required | Breaking | Not applicable the same way; disappearing response fields also carry risk |
| Non-null to nullable | Server may accept new nulls if request | Clients may encounter unexpected nulls |
| `200` to `204` | Not applicable to request body | Breaking if clients need response body |
| Add new response status | Not applicable | Potentially breaking for closed status handling |
| Remove old response status | Not applicable | May break client handling branches |

This matrix is an initial guide. Final compatibility also depends on clients, serializers, generators, validation, and business semantics.

## 23. Safe contract-change workflow

When you need to narrow an enum, change a type/format, or alter a status:

1. Retrieve the OpenAPI document of the currently supported release.
2. Determine whether the change is in the request or response.
3. Check which client generators and data types clients use.
4. Assess schema and semantic impact.
5. Prefer compatible extensions or adding new fields/endpoints.
6. Mark `deprecated` and announce migration if removal is needed.
7. Write tests for requests/responses and runtime statuses.
8. Generate the OpenAPI document from Springdoc.
9. Run validator, linter, and breaking-change diff.
10. Review all enum, type, format, and response-status warnings.
11. Increment the API contract version or create a new document group/version when needed.
12. Publish a migration guide and maintain a transition period.

Do not rely on the new server still compiling or internal unit tests passing. Old clients may be generated from the prior contract and must be checked separately.

## 24. Common mistakes

| Symptom | Root cause to check |
|---|---|
| Client deserialization error after adding enum | Client uses closed enum without an unknown fallback |
| Old request returns 400 after release | Server removed an enum value or tightened constraints |
| OpenAPI shows different enum than runtime JSON | Jackson `@JsonProperty` or custom serializer is out of sync |
| Client receives unexpected null | Response property became nullable or was omitted from JSON |
| Numeric overflow | Server returns value exceeding old client's type range |
| Date parse failure | Format or timezone representation changed |
| Client fails on 204 | Server dropped a response body the client still needs |
| Client errors on new status | `switch`/`case` lacks default handling |
| Swagger UI shows wrong response | `@ApiResponse` does not match `ResponseEntity` or exception handler |
| Contract diff misses changes | Wrong baseline, outdated tool version, or schema inlined/resolved differently |
| API version bumped without contract change | Confusing application version with API contract version |

When investigating, compare runtime JSON, the OpenAPI document, and generated client code. Checking only Java enums or annotations is not enough.

## 25. Principles for maintaining compatibility during schema and status changes

When managing enum, type, format, and HTTP status changes:

1. Evaluate request compatibility and response compatibility separately.
2. Do not remove request enum values in active client use without migration.
3. Treat new response enum values as changes to verify against closed-enum clients.
4. Do not change the `type` or `format` of published properties without a plan.
5. Keep numeric ranges and precision aligned with released clients.
6. Distinguish `required` from `nullable`.
7. Keep Bean Validation, Jackson serialization, and the OpenAPI schema in sync.
8. Do not treat `200`, `201`, `204`, or error statuses as interchangeable.
9. Document responses with `@ApiResponse` and verify runtime statuses.
10. Use deprecation, migration windows, and versioned APIs when needed.
11. Run OpenAPI diffs and contract tests before releasing.
12. Store baselines accurately by API version and audience.

Enums, types, formats, and status codes are all parts of the API contract. By evaluating changes along data flow direction, keeping Java DTOs, Jackson, validation, and OpenAPI synchronized, and verifying client compatibility prior to release, teams can evolve APIs while reducing the risk of breaking live integrations.

