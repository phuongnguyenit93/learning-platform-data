# Requiredness, Empty Values, and Absent Properties

When describing an HTTP contract with springdoc-openapi, it is important to distinguish three commonly confused states: a property omitted from the request, a property present with a <code>null</code> value, and a property present with an empty value such as the string <code>""</code>. These three states have different meanings in JSON and can lead to different business behavior.

OpenAPI describes these states using distinct concepts: <code>required</code> determines whether a value must be present; data type and nullability determine which values are valid when present; constraints such as <code>minLength</code> determine whether empty values are accepted. springdoc-openapi generates documentation from the Spring Boot application, yet the contract is only accurate when the schema reflects the exact rules the API enforces.

## 1. Distinguishing Absent, Null, and Empty Properties

Consider a JSON request with three properties <code>name</code>, <code>nickname</code>, and <code>description</code>:

~~~json
{
  "name": "Lan",
  "nickname": null,
  "description": ""
}
~~~

In this JSON object:

- <code>name</code> is present and holds a non-empty string.
- <code>nickname</code> is present and its value is <code>null</code>.
- <code>description</code> is present and holds an empty string, i.e., a string of length 0.
- If a property is omitted from the object altogether, that property is in the absent state.

These cases are not interchangeable:

| Representation | Meaning in JSON | Contract question to answer |
|---|---|---|
| Missing key <code>nickname</code> | Absent property | Is omitting the property allowed? |
| <code>"nickname": null</code> | Key present, null value | Is a null value allowed? |
| <code>"nickname": ""</code> | Key present, empty string | Is a zero-length string allowed? |
| <code>"nickname": "   "</code> | Key present, whitespace-only string | Is non-whitespace content required? |
| <code>"nickname": "Lan"</code> | Key present, string with content | Does the value satisfy other constraints? |

For arrays and objects, empty values also have their own forms:

~~~json
{
  "tags": [],
  "settings": {}
}
~~~

<code>[]</code> is an array with 0 elements; <code>{}</code> is an object with no properties. They differ from <code>null</code> and from omitting the <code>tags</code> or <code>settings</code> key.

## 2. <code>required</code> Governs Presence

In an OpenAPI Schema Object, <code>required</code> is a list of mandatory property names on an object. This list is declared at the same level as <code>properties</code>.

~~~yaml
type: object
required:
  - name
properties:
  name:
    type: string
  nickname:
    type: string
~~~

The schema above requires the object to have the <code>name</code> property. The <code>nickname</code> property may be absent. Both properties have type string, so when present, their values must be strings according to this schema. The fact that <code>nickname</code> is not listed in <code>required</code> does not mean it automatically accepts <code>null</code>.

Example:

~~~json
{ "name": "Lan" }
~~~

This is a valid object under the schema above. The following object is invalid because <code>name</code> is missing:

~~~json
{ "nickname": "L" }
~~~

<code>required</code> is not synonymous with <code>minLength</code>, <code>minItems</code>, or a content validation rule. A required string can still be an empty string if the schema places no length limit.

~~~yaml
type: object
required:
  - name
properties:
  name:
    type: string
~~~

With this schema, <code>{ "name": "" }</code> still satisfies type string and presence. If business rules require at least one character, add <code>minLength: 1</code>. If whitespace-only strings must also be rejected, a stronger rule is needed, such as <code>@NotBlank</code> at the Bean Validation layer.

## 3. Requiredness and Nullability Are Two Independent Decisions

A property can be required to appear while still allowing a <code>null</code> value. Conversely, a property can be allowed to be absent while requiring a non-null value if present.

The following table describes all four combinations:

| In <code>required</code>? | Does the schema accept null? | Meaning |
|---|---|---|
| Yes | No | Must be present and must not be null |
| Yes | Yes | Must be present; value may be null |
| No | No | May be absent; if present, must not be null |
| No | Yes | May be absent; if present, may be null |

### 3.1. OpenAPI 3.0: Using <code>nullable</code>

In OpenAPI 3.0, <code>nullable: true</code> can be used to allow null values for a schema that declares a <code>type</code>:

~~~yaml
type: object
required:
  - displayName
  - nickname
properties:
  displayName:
    type: string
    minLength: 1
  nickname:
    type: string
    nullable: true
  bio:
    type: string
~~~

Interpretation:

- <code>displayName</code> is required, non-null, and must have at least one character.
- <code>nickname</code> must have its key present, yet its value can be a string or <code>null</code>.
- <code>bio</code> may be absent; if present, it must be a non-null string. An empty string is still valid because <code>minLength</code> is not set.

The following example is valid:

~~~json
{
  "displayName": "Lan",
  "nickname": null,
  "bio": ""
}
~~~

The following example is invalid because the required property <code>nickname</code> is missing:

~~~json
{
  "displayName": "Lan"
}
~~~

The following example is invalid because <code>displayName</code> has length 0:

~~~json
{
  "displayName": "",
  "nickname": null
}
~~~

In OpenAPI 3.0, <code>nullable</code> only takes effect when <code>type</code> is explicitly declared in the same Schema Object. Do not use <code>nullable: true</code> as a substitute for <code>required</code>: these two properties solve two different concerns.

### 3.2. OpenAPI 3.1: Using Type Unions with Null

OpenAPI 3.1 is based on modern JSON Schema. To allow a value to be a string or null, represent the type as a list:

~~~yaml
openapi: 3.1.0
components:
  schemas:
    Profile:
      type: object
      required:
        - displayName
        - nickname
      properties:
        displayName:
          type: string
          minLength: 1
        nickname:
          type: [string, "null"]
        bio:
          type: string
~~~

<code>nickname</code> is still required to appear because it is in the <code>required</code> array, while <code>type: [string, "null"]</code> allows its value to be a string or null. <code>bio</code> remains an optional property and does not accept null under this schema.

When writing OpenAPI 3.1 documents, prefer the JSON Schema null type representation shown above. <code>nullable</code> is an OpenAPI 3.0 construct and is not a JSON Schema keyword replacing type unions in OpenAPI 3.1.

## 4. Distinguishing required Across Levels of the HTTP Contract

OpenAPI uses the word <code>required</code> in multiple places. Identify the exact level because each location controls something different.

| Location | Declaration | Meaning |
|---|---|---|
| Parameter Object | <code>required: true</code> | The path, query, header, or cookie parameter must be sent |
| Request Body Object | <code>required: true</code> | The client must send a request body |
| Object Schema Object | <code>required: [fieldA, fieldB]</code> | The listed properties must appear inside the object |

For path parameters, OpenAPI requires <code>required: true</code>. Query parameters are usually optional unless explicitly declared required:

~~~yaml
parameters:
  - name: customerId
    in: path
    required: true
    schema:
      type: string
  - name: keyword
    in: query
    required: false
    schema:
      type: string
~~~

<code>required: false</code> on <code>keyword</code> allows clients to omit the parameter. If the client sends <code>?keyword=</code>, the received value is an empty string under typical query parsing; it is not an absent parameter. How queries without an <code>=</code> sign are handled may depend on the framework and should be specified clearly if the API uses that case.

Request bodies have their own rules:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - name
        properties:
          name:
            type: string
~~~

Here, <code>requestBody.required: true</code> requires a body to be present. The <code>schema.required</code> array requires the <code>name</code> property inside the JSON body. If the body is an empty object <code>{}</code>, the request has a body yet still fails the schema because <code>name</code> is missing. If the client sends no body, the request violates the requirement at the Request Body level.

A body with zero bytes, a body containing JSON <code>null</code>, and a body containing an empty object <code>{}</code> are also three distinct cases. To accept JSON <code>null</code>, the body schema must allow the null type; <code>requestBody.required: true</code> by itself does not make the schema accept null.

## 5. Constraining Empty Strings and Whitespace-Only Content

A property that is present and of type string does not necessarily hold useful content. Use schema constraints to describe limits:

~~~yaml
type: string
minLength: 1
maxLength: 80
~~~

<code>minLength: 1</code> rejects the empty string <code>""</code>, yet still allows whitespace-only strings such as <code>"   "</code>. If at least one non-whitespace character is needed, express the corresponding rule with application validation and document it clearly.

Some commonly used Bean Validation annotations:

| Annotation | Runtime rule |
|---|---|
| <code>@NotNull</code> | Value must not be null; empty strings may still be valid |
| <code>@NotEmpty</code> | Value is non-null and has size greater than 0; whitespace-only strings may still be valid |
| <code>@NotBlank</code> | String is non-null and must contain at least one non-whitespace character |
| <code>@Size(min = 1)</code> | Size must be at least 1; this constraint accepts null if no other constraint forbids null |

DTO example:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
    @NotBlank
    @Size(max = 80)
    String name,

    @Size(max = 40)
    String nickname
) {}
~~~

The controller must trigger validation on the request:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    @PostMapping("/customers")
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateCustomerRequest request) {
        // Process the request after validation succeeds
        return ResponseEntity.accepted().build();
    }
}
~~~

<code>@NotBlank</code> ensures <code>name</code> cannot be null, empty, or whitespace-only when Bean Validation runs. <code>@Size(max = 40)</code> limits the size of nickname, though by itself it neither requires nickname to be present nor rejects null. These are application runtime rules; inspect the schema generated by springdoc to confirm the documentation accurately reflects the constraints.

## 6. Expressing Requirements Clearly in springdoc-openapi

springdoc-openapi reads Spring MVC/WebFlux structures and related annotations to build the specification. Bean Validation helps describe limits checked by the application at runtime. The <code>@Schema</code> annotation allows adding OpenAPI metadata when contract intent needs to be stated explicitly.

For example, using <code>requiredMode</code> to explicitly declare property presence:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

public record RegisterRequest(
    @Schema(
        description = "User display name",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    @NotBlank
    String displayName,

    @Schema(
        description = "Alternative name; may be omitted during registration",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    String nickname
) {}
~~~

<code>requiredMode</code> controls how the property is described in OpenAPI. It does not enforce validation itself when requests arrive at the server. Conversely, Bean Validation annotations only take effect at runtime when the application enables validation and triggers the appropriate checks. These two layers must stay aligned so documentation never promises behavior the endpoint does not enforce.

For nullable properties, choose the representation matching the OpenAPI version emitted by your application. Check the <code>openapi</code> field at the top of <code>/v3/api-docs</code>, then verify the schema:

- OpenAPI 3.0: check <code>nullable: true</code> alongside <code>type</code>.
- OpenAPI 3.1: check that the JSON Schema type includes <code>"null"</code> when needed.
- In both versions: check whether the property appears in the object's <code>required</code> array.

Do not assume a property accepts null merely because a Java DTO declares reference types such as <code>String</code>, <code>Integer</code>, or <code>LocalDate</code>. Java types, Jackson rules, Bean Validation, OpenAPI metadata, and business logic are separate layers. Review the generated specification to verify the final outcome.

## 7. Absent Properties and Null in Update Operations

The difference between absent and null is especially critical for partial update APIs. For example, a client wants to change a profile's nickname:

~~~json
{
  "nickname": "Lana"
}
~~~

If the client omits <code>nickname</code>, the API may interpret that as leaving this property unchanged. If the client sends <code>"nickname": null</code>, the API may interpret that as clearing the current value. If the client sends <code>"nickname": ""</code>, the API may store an empty string or reject it per business rules.

This is a convention of the update API; not every PATCH endpoint behaves this way automatically. The contract must clearly define each state. When using JSON Merge Patch per RFC 7396, omitted properties remain unchanged, while properties with null values indicate removing the corresponding member from the target object. If using a custom PATCH format, publish that format's rules.

In Java, an ordinary DTO may not preserve the distinction between an omitted property and a property sent as null: both cases can become a <code>null</code> field value after Jackson binds the payload. When business logic must distinguish them, you can read the payload as a <code>JsonNode</code> and check presence before checking the value:

~~~java
if (!patch.has("nickname")) {
    // Do not update nickname
} else if (patch.get("nickname").isNull()) {
    // Clear nickname according to API convention
} else {
    // Update with the submitted value
    String nickname = patch.get("nickname").asText();
}
~~~

The snippet assumes <code>patch</code> is a JSON object and the endpoint has validated data types appropriately. If using DTOs, wrappers, or custom deserializers, check how the library binds data to ensure all three states remain distinguishable.

## 8. Verifying the Generated Contract

After adding or changing annotations, inspect the actual document at <code>/v3/api-docs</code>. You can fetch the JSON with curl:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Focus on the following points:

1. The right OpenAPI 3.0 or 3.1 version is published in the <code>openapi</code> field.
2. The request body has the exact requiredness expected by the endpoint.
3. The object schema's <code>required</code> array contains the exact properties that must appear.
4. Nullable properties are represented appropriately for the OpenAPI version.
5. Strings have length limits, patterns, or formats matching runtime validation.
6. Request examples demonstrate absent properties, null, and empty strings when those cases are meaningful.

Test both sides of the contract. For requests, verify the server rejects rule-violating data. For responses, verify that actual payloads returned by controllers do not violate the published schema. Having <code>required</code> or <code>minLength</code> in the spec does not automatically guarantee every code path produces a valid response.

## 9. Pre-Release API Review Checklist

- [ ] Every property is clearly classified as required or optional.
- [ ] For optional properties, nullability when present has been decided.
- [ ] For string types, whether <code>""</code> or whitespace-only strings are accepted has been decided.
- [ ] For arrays and objects, whether <code>[]</code> and <code>{}</code> are accepted has been decided.
- [ ] <code>requestBody.required</code>, <code>Parameter.required</code>, and the <code>Schema.required</code> array are properly distinguished.
- [ ] PATCH contracts clearly define handling for absent, null, and empty properties.
- [ ] Runtime validation and the generated OpenAPI schema are consistent.
- [ ] Request/response examples illustrate important data states.

## References

- [OpenAPI Specification 3.0 – Schema Object](https://spec.openapis.org/oas/v3.0.3.html#schema-object): <code>required</code>, <code>nullable</code>, and schema constraints.
- [OpenAPI Specification 3.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object): JSON Schema-based Schema Object and data type descriptions.
- [JSON Schema – Required Properties](https://json-schema.org/understanding-json-schema/reference/object#required-properties): difference between required and optional properties.
- [JSON Schema – Null](https://json-schema.org/understanding-json-schema/reference/null): describing null values in schemas.
- [JSON Merge Patch – RFC 7396](https://www.rfc-editor.org/rfc/rfc7396): meaning of absent properties and null in JSON Merge Patch.
- [springdoc-openapi](https://springdoc.org/): OpenAPI integration with Spring Boot and documentation customization.
