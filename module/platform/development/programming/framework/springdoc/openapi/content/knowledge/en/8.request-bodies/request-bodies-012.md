# Choosing a Clear Documentation Model for PATCH and Partial Updates

HTTP `PATCH` is used when a client wants to modify only part of a resource. However, the phrase "part of" is not enough to define what a request body means. When a client omits a field, does the server preserve the existing value or delete that field? When a client sends `null`, does the server interpret it as clearing the value, storing null, or rejecting the request? If the body is an array of operations, in what order are they applied?

A PATCH API must choose and clearly publish an update model. Common choices are JSON Merge Patch per RFC 7396, JSON Patch per RFC 6902, or an application-defined partial update DTO. Springdoc can describe the media type, schema, fields, and responses of each model. Documentation is useful only when the semantics in OpenAPI match how the controller actually applies the request.

## 1. How does PATCH differ from PUT?

`PUT` typically represents replacing the state of the resource at a URI with the representation sent by the client. `PATCH` represents a set of changes to apply to the existing resource. This difference directly affects the request schema and the meaning of omitted fields.

Example existing resource:

```json
{
  "id": 42,
  "name": "Keyboard",
  "description": "Mechanical keyboard",
  "price": 1290000,
  "active": true
}
```

A `PUT` request might send the full representation:

```http
PUT /api/products/42
Content-Type: application/json
```

```json
{
  "name": "Keyboard Pro",
  "description": "Wireless mechanical keyboard",
  "price": 1590000,
  "active": true
}
```

Meanwhile, a `PATCH` request might send only the field to change:

```http
PATCH /api/products/42
Content-Type: application/merge-patch+json
```

```json
{
  "price": 1590000
}
```

Clients must know the exact rules of the PATCH body. Otherwise, omitting `description` or sending `description: null` can produce unexpected outcomes.

## 2. Three states to distinguish in partial updates

For an editable field, a request often needs to express three intentions:

| State in request | Common meaning |
|---|---|
| Field omitted | Keep the current value |
| Field present with non-null value | Update to the new value |
| Field present with `null` | Clear the value, set null, or reject per published API rules |

The challenge is that many ordinary Java DTOs do not preserve the distinction between "field omitted" and "field explicitly sent as null". When Jackson deserializes JSON into a `String` property, both cases can become Java `null`.

Simple DTO example:

```java
public record ProductPatchRequest(
    String name,
    String description
) {
}
```

With this DTO, after deserialization, `description == null` does not tell you whether the client omitted the field or sent:

```json
{
  "description": null
}
```

If business logic needs to distinguish those two intentions, you need a data model capable of representing "not provided" separately from "provided as null".

## 3. Choosing one of three request body models

| Model | Typical media type | Body structure | When appropriate |
|---|---|---|---|
| JSON Merge Patch | `application/merge-patch+json` | Object representing fields to merge; `null` means delete member | Updating objects with simple, widely understood merge rules |
| JSON Patch | `application/json-patch+json` | Array of operations such as `add`, `remove`, `replace`, `move`, `copy`, `test` | Needing exact paths, ordering, or operations on arrays/nested values |
| Custom PATCH DTO | Usually `application/json` | Dedicated object containing only updatable fields | Wanting a simple contract, restricted fields, and custom business rules |

Do not reuse the same media type for bodies with different semantics without documenting clearly. `application/json` by itself does not indicate whether a body is JSON Merge Patch or JSON Patch. If the API uses a custom DTO, clearly state the meaning of missing fields and `null` fields in the description/schema.

## 4. JSON Merge Patch per RFC 7396

JSON Merge Patch uses the `application/merge-patch+json` media type. The body is usually a JSON object containing the fields to change. Core rules:

- Fields absent from the patch retain their current values.
- Fields with non-null values are added or replaced in the target resource.
- Fields with `null` values are removed from the target object.
- Nested objects are merged recursively.
- Arrays are replaced as a whole value; Merge Patch does not update individual array elements by index.

Example existing resource:

```json
{
  "name": "Keyboard",
  "description": "Mechanical keyboard",
  "manufacturer": {
    "name": "Acme",
    "country": "VN"
  },
  "tags": ["office", "wireless"]
}
```

Patch:

```json
{
  "name": "Keyboard Pro",
  "description": null,
  "manufacturer": {
    "country": "JP"
  },
  "tags": ["wireless", "gaming"]
}
```

Result after applying:

```json
{
  "name": "Keyboard Pro",
  "manufacturer": {
    "name": "Acme",
    "country": "JP"
  },
  "tags": ["wireless", "gaming"]
}
```

`description` is removed; `manufacturer.name` is preserved because it was absent from the patch; `manufacturer.country` is updated; the entire `tags` array is replaced.

### Limitations of JSON Merge Patch

Per RFC 7396, `null` means removing a member. Therefore, JSON Merge Patch cannot directly distinguish between "setting a field to JSON `null`" and "removing a field from an object". If business rules need to store a meaningful `null` value, choose JSON Patch or a custom DTO with explicit semantics.

Additionally, a patch document at the root level can be any JSON value per the RFC; if the API only permits updating a resource object, the server should verify the body is an object and reject other data types. This should be reflected in the schema and endpoint description.

## 5. Describing JSON Merge Patch in Springdoc

In Spring MVC, you can receive the body as a `JsonNode` to preserve structure and distinguish omitted fields from `null`-valued fields. `JsonNode` also works well when passing the patch document to an RFC 7396-compliant library or processor.

Example schema for documentation:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "ProductMergePatch", description = "Product fields updatable via JSON Merge Patch")
public class ProductMergePatchDocument {

    @Schema(
        description = "New name; omit to keep unchanged, null removes field if business rules allow",
        nullable = true
    )
    public String name;

    @Schema(
        description = "New description; omit to keep unchanged, null removes description",
        nullable = true
    )
    public String description;

    @Schema(
        description = "New price; omit to keep unchanged",
        nullable = true,
        example = "1590000"
    )
    public Long price;
}
```

The controller can declare the media type and request schema explicitly:

```java
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @PatchMapping(
        value = "/{id}",
        consumes = "application/merge-patch+json"
    )
    @Operation(
        summary = "Partially update product",
        description = "Applies JSON Merge Patch per RFC 7396. Omitted fields remain unchanged; null fields are removed per Merge Patch rules."
    )
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        description = "JSON Merge Patch document",
        content = @Content(
            mediaType = "application/merge-patch+json",
            schema = @Schema(implementation = ProductMergePatchDocument.class)
        )
    )
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Updated successfully"),
        @ApiResponse(responseCode = "400", description = "Invalid patch document"),
        @ApiResponse(responseCode = "404", description = "Product not found"),
        @ApiResponse(responseCode = "409", description = "Conflict with current state"),
        @ApiResponse(responseCode = "415", description = "Unsupported media type")
    })
    ResponseEntity<ProductResponse> patch(
        @PathVariable Long id,
        @org.springframework.web.bind.annotation.RequestBody JsonNode patchDocument
    ) {
        if (!patchDocument.isObject()) {
            return ResponseEntity.badRequest().build();
        }

        ProductResponse updated = productService.applyMergePatch(id, patchDocument);
        return ResponseEntity.ok(updated);
    }
}
```

`ProductMergePatchDocument` describes the public schema; the controller receives `JsonNode` to handle each member's state accurately. `productService.applyMergePatch` represents the business logic: fetching the current resource, applying the RFC 7396 algorithm, verifying editable fields, and saving the result. Use a tested Merge Patch implementation or write an RFC-compliant processor; do not merely deserialize into a regular DTO and guess which fields were sent.

`consumes` ensures the Spring mapping and documentation display the right media type. The Swagger `RequestBody` annotation here is written in full to avoid confusion with Spring MVC's `@RequestBody`. `required = true` states that the HTTP request must have a body; it does not mean every field in the schema is required.

## 6. JSON Patch per RFC 6902

JSON Patch uses the `application/json-patch+json` media type. The body is an array of operations applied sequentially to the resource. Standard operations include:

| Operation | Meaning | Additional fields |
|---|---|---|
| `add` | Adds a value at path; for objects, can replace an existing member value | `value` |
| `remove` | Removes the value at path | None |
| `replace` | Replaces the value at an existing path | `value` |
| `move` | Moves a value from source path to destination path | `from` |
| `copy` | Copies a value from source path to destination path | `from` |
| `test` | Checks whether the value at path equals the expected value | `value` |

Example:

```http
PATCH /api/products/42 HTTP/1.1
Content-Type: application/json-patch+json
```

```json
[
  { "op": "replace", "path": "/name", "value": "Keyboard Pro" },
  { "op": "remove", "path": "/description" },
  { "op": "add", "path": "/tags/-", "value": "featured" }
]
```

Operations are applied in array order. `path` and `from` use JSON Pointer. `/` characters in member names are escaped as `~1`, and `~` is escaped as `~0`. A `-` token at the end of an array path appends an element to the end of the array.

JSON Patch suits cases where clients need to modify a specific array element, move values, or test preconditions before editing. In return, the body is more complex and the server must validate paths, operations, per-field update permissions, and operation limits. Never allow clients to arbitrarily modify internal properties or sensitive fields simply because a JSON Pointer can reach them.

### Describing JSON Patch in OpenAPI

A simplified operation schema for presentation might look like:

```java
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "JsonPatchOperation")
public class JsonPatchOperationDocument {

    @Schema(
        description = "Operation type",
        allowableValues = {"add", "remove", "replace", "move", "copy", "test"},
        example = "replace"
    )
    public String op;

    @Schema(description = "JSON Pointer to target location", example = "/name")
    public String path;

    @Schema(description = "Value used for add, replace, or test")
    public JsonNode value;

    @Schema(description = "Source JSON Pointer used for move or copy", example = "/oldName")
    public String from;
}
```

An actual operation object has different field requirements depending on `op`: `remove` does not need `value`, whereas `move` and `copy` need `from`. A flat DTO listing all fields cannot fully express these conditions. For strict contracts, describe the schema using `oneOf` for each operation variant or use a tested standard JSON Patch schema.

The controller can describe the body as an array of operations:

```java
@PatchMapping(value = "/{id}", consumes = "application/json-patch+json")
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    required = true,
    description = "List of JSON Patch operations per RFC 6902",
    content = @Content(
        mediaType = "application/json-patch+json",
        array = @io.swagger.v3.oas.annotations.media.ArraySchema(
            schema = @Schema(implementation = JsonPatchOperationDocument.class)
        )
    )
)
ResponseEntity<ProductResponse> patchJson(
    @PathVariable Long id,
    @org.springframework.web.bind.annotation.RequestBody JsonNode operations
) {
    ProductResponse updated = productService.applyJsonPatch(id, operations);
    return ResponseEntity.ok(updated);
}
```

`applyJsonPatch` must use an RFC 6902-compliant library or processor, applying operations in order and rejecting malformed patches or invalid paths. Avoid writing a stripped-down custom JSON Pointer/JSON Patch processor for production if it does not cover all RFC rules.

## 7. Custom PATCH DTO for simple business logic

Not every API needs full RFC 7396 or RFC 6902. If only a few fields may change and you want a simple contract, you can create a dedicated PATCH DTO.

Example body:

```http
PATCH /api/products/42
Content-Type: application/json
```

```json
{
  "name": "Keyboard Pro",
  "active": false
}
```

The contract can stipulate:

- Omitted fields keep their current values.
- Fields with valid values are updated.
- `null` fields are rejected or used to clear values on a per-field basis.
- Fields not permitted to be modified are rejected or ignored per published policy.

If `null` always means "do not update", a standard DTO may suffice. If you need to distinguish omitted fields from explicitly `null` fields, you can use the `JsonNullable<T>` wrapper from the `jackson-databind-nullable` library.

### Distinguishing `undefined` and `null` with `JsonNullable`

Maven dependency:

```xml
<dependency>
    <groupId>org.openapitools</groupId>
    <artifactId>jackson-databind-nullable</artifactId>
    <version>${jackson-databind-nullable.version}</version>
</dependency>
```

Register the Jackson module:

```java
import com.fasterxml.jackson.databind.Module;
import org.openapitools.jackson.nullable.JsonNullableModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonConfiguration {

    @Bean
    Module jsonNullableModule() {
        return new JsonNullableModule();
    }
}
```

The DTO must initialize properties to `undefined` so missing fields are still recognized as unprovided:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import org.openapitools.jackson.nullable.JsonNullable;

public class ProductPatchRequest {

    @Schema(
        description = "New name; undefined keeps unchanged, null handled per clear rules",
        nullable = true
    )
    private JsonNullable<String> name = JsonNullable.undefined();

    @Schema(
        description = "New description; undefined keeps unchanged, null clears description",
        nullable = true
    )
    private JsonNullable<String> description = JsonNullable.undefined();

    public JsonNullable<String> getName() {
        return name;
    }

    public void setName(JsonNullable<String> name) {
        this.name = name;
    }

    public JsonNullable<String> getDescription() {
        return description;
    }

    public void setDescription(JsonNullable<String> description) {
        this.description = description;
    }
}
```

Once the module is registered and Jackson deserializes properly:

- JSON without `name`: property stays `JsonNullable.undefined()`.
- JSON with `"name": null`: property represents a provided `null` value.
- JSON with `"name": "Keyboard Pro"`: property represents the new value.

Patch application logic must check presence before reading the value:

```java
if (patch.getName().isPresent()) {
    String newName = patch.getName().get();
    if (newName == null) {
        product.clearName();
    } else {
        product.rename(newName);
    }
}
```

This snippet illustrates business rules: an undefined field makes no change; a `null` field clears the name; a string renames it. If the domain forbids null names, return a validation error instead of calling `clearName()`.

When using `JsonNullable`, inspect the schema Springdoc generates. Wrapper types, nullability, and requiredness can render differently depending on library versions and OpenAPI dialects. Customize the schema if the documentation fails to convey the three supported states clearly. Do not rely on Java types alone to assume the schema is right.

## 8. Describing Request Body and media types with Springdoc

Springdoc typically infers the request body from `@RequestBody`, the parameter type, and `consumes` on the Spring mapping. When an API uses specialized media types or bodies with distinct semantics, describe them explicitly using Swagger `@RequestBody` and `@Content`.

| Detail | Where to describe |
|---|---|
| HTTP method and path | Spring `@PatchMapping` or `@RequestMapping` |
| Accepted media types | `consumes` attribute and `requestBody.content` |
| Body schema | DTO, `@Schema`, `@ArraySchema`, or custom schema |
| Whether body is required | Swagger `@RequestBody(required = true)` and Spring binding |
| Meaning of missing/null fields | Request body/property descriptions and business rules |
| Success/error responses | `@ApiResponse`, `@ApiResponses`, response type |

There are two annotations named `RequestBody`:

```java
org.springframework.web.bind.annotation.RequestBody
```

The Spring annotation binds the HTTP body to the controller parameter.

```java
io.swagger.v3.oas.annotations.parameters.RequestBody
```

The Swagger annotation describes the body in OpenAPI. When using both on the same method, import one and fully qualify the other to avoid confusion.

`required = true` on the Request Body Object states that the request must contain a body. It does not automatically make every DTO property required. For PATCH, the body is normally required while individual fields may all be optional; the schema should reflect that.

## 9. Validation when applying a patch

PATCH validation must inspect both the request document and the resulting resource state after the update.

**Check the request document:**

- Does the body have the right media type?
- Is the body the right JSON object or array per the chosen model?
- Are there fields not allowed to be updated?
- Does JSON Patch have valid operations, paths, `from`, and values?
- Are body size, operation count, or nesting depth limits enforced?

**Check the state after updating:**

- Are domain-required fields still valid?
- Are cross-field rules satisfied?
- Are new values within permitted ranges?
- Is the state transition valid—for instance, disallowing edits to completed orders?

Do not mechanically apply `@NotNull` or `@NotBlank` to a PATCH DTO when omitted fields are valid. With JSON Merge Patch, `null` means removing a member; after merging, a domain validator must check whether the resource remains valid. With a custom DTO, validate only provided fields and then validate the complete aggregate/resource.

Common responses to document include:

| HTTP status | Scenario |
|---|---|
| `200 OK` | PATCH succeeded and returns updated representation |
| `204 No Content` | PATCH succeeded with no response body |
| `400 Bad Request` | Malformed JSON or invalid patch document |
| `404 Not Found` | Resource not found |
| `409 Conflict` | Conflict with current state or business rules |
| `412 Precondition Failed` | `If-Match` condition not satisfied |
| `415 Unsupported Media Type` | Client sent a media type unsupported by the endpoint |
| `422 Unprocessable Content` | Syntactically valid content that cannot be applied per business rules |

Choose status codes based on API policy and application error handling; not every endpoint needs to return all codes.

## 10. Controlling concurrent updates with `ETag` and `If-Match`

Two clients can read the same resource and submit patches based on the same stale state. If the server applies them sequentially without version checks, the later update can overwrite the earlier client's changes.

`ETag` and `If-Match` support optimistic concurrency. The server returns an `ETag` when reading the resource; the client sends that `ETag` back in the PATCH request. If the resource has changed and the `ETag` no longer matches, the server returns `412 Precondition Failed`.

Example:

```http
PATCH /api/products/42 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "product-42-v7"
```

`If-Match` is a standard HTTP conditional header, not credentials. It can be documented as a header parameter:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;

@Parameter(
    name = "If-Match",
    in = ParameterIn.HEADER,
    description = "Current ETag of the resource to prevent overwriting concurrent updates",
    required = true,
    example = "\"product-42-v7\""
)
```

Place `@Parameter` on the controller parameter corresponding to `@RequestHeader("If-Match")`. The server must actually compare the validator against the current version and return `412` on mismatch; merely adding the parameter to OpenAPI does not enforce concurrency control.

## 11. Is PATCH idempotent?

Do not assume every PATCH is idempotent. Idempotency depends on the patch document's semantics and how the server applies it.

- A JSON Merge Patch setting `price` to the same value usually leaves the resource in the same state if sent repeatedly.
- A JSON Patch `replace /name` with the same value usually yields the same final state.
- A JSON Patch `add /tags/-` can append a new element on each request, so repeated submissions yield different states.
- Side effects like audit logging, notifications, or billing can cause repeated requests to create extra impact even if the final resource looks identical.

If clients need safe retries, design clear semantics, consider `If-Match` or idempotency keys where appropriate, and handle side effects inside transactions or an outbox. API documentation should clarify retry constraints clients need to know.

## 12. Inspecting OpenAPI and testing PATCH requests

After configuring, open `/v3/api-docs` and check:

- Does the operation have the right `patch` method and path?
- Is `requestBody.required` accurate?
- Does `requestBody.content` have the right media types?
- Does the schema express a Merge Patch object, JSON Patch array, or custom DTO?
- Are optional fields mistakenly marked required?
- Does the description clearly explain missing and `null` fields?
- Do responses document the status codes the server actually returns?
- Is the `If-Match` header documented if the endpoint uses optimistic concurrency?

Example testing JSON Merge Patch:

```bash
curl -i -X PATCH http://localhost:8080/api/products/42 \
  -H "Content-Type: application/merge-patch+json" \
  -d '{"price":1590000,"description":null}'
```

Example testing JSON Patch:

```bash
curl -i -X PATCH http://localhost:8080/api/products/42 \
  -H "Content-Type: application/json-patch+json" \
  -d '[{"op":"replace","path":"/name","value":"Keyboard Pro"}]'
```

Example testing a custom PATCH DTO:

```bash
curl -i -X PATCH http://localhost:8080/api/products/42 \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard Pro","active":false}'
```

Do not mix media types across the three examples. Sending JSON Merge Patch to an endpoint accepting only `application/json` may cause Spring to return `415 Unsupported Media Type` depending on mapping settings.

## 13. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| Sending one field clears other fields | DTO deserializes missing fields as `null` and service treats `null` as deletion | Distinguish `undefined`/`null` or use standards-compliant JSON Merge Patch |
| Cannot set a field to `null` | JSON Merge Patch treats `null` as deleting the member | Use JSON Patch or a custom DTO if set-null semantics are needed |
| Replacing one array item wipes out the rest | JSON Merge Patch replaces the entire array | Use JSON Patch or a dedicated collection endpoint |
| Swagger UI shows body as `application/json` | `consumes` or `@Content.mediaType` not declared explicitly | Synchronize media types in Spring mapping and OpenAPI |
| All PATCH fields marked required | Schema inherited create/replace DTO or wrong required annotations | Use a dedicated PATCH schema and mark fields optional |
| JSON Patch fails on path | Wrong JSON Pointer, bad escaping, or non-existent path | Check `path`, `from`, operation order, and resource schema |
| Valid body fails to persist | Post-merge state violates validation/domain rules | Validate the resource after applying the patch |
| Two clients overwrite each other's edits | Missing optimistic concurrency control | Use `ETag`/`If-Match` or an appropriate versioning mechanism |

## 14. Checklist for choosing and documenting a PATCH model

- [ ] Decided whether the API uses JSON Merge Patch, JSON Patch, or a custom PATCH DTO.
- [ ] Selected the media type matching the body semantics.
- [ ] Clearly defined what omitted fields mean.
- [ ] Clearly defined whether `null` fields mean remove, set to null, or reject.
- [ ] Defined how nested objects and arrays are handled.
- [ ] OpenAPI schema accurately reflects optional, nullable, and operation body fields.
- [ ] `@PatchMapping(consumes = ...)` matches `requestBody.content`.
- [ ] Responses document syntax, validation, state, and media type errors appropriately.
- [ ] Verified per-field update permissions and patch document limits.
- [ ] Validated resource state after applying the patch.
- [ ] Put a concurrency protection strategy in place if required by business rules.
- [ ] Tested real requests and cross-checked generated OpenAPI JSON/YAML.

A sound PATCH contract tells clients exactly how the body is interpreted. JSON Merge Patch suits object updates following merge rules; JSON Patch suits precise sequences of operations; custom PATCH DTOs suit constrained business rules. Springdoc publishes the media types, schemas, and responses, while the controller and service are responsible for enforcing the documented semantics.
