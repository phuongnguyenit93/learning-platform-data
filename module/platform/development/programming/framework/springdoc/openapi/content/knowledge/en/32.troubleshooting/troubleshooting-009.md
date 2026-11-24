# Duplicate Schema Names or Broken `$ref` References

## 1. Why Do Schema and `$ref` Errors Break the API Contract?

Springdoc OpenAPI generates schemas from DTOs, Java types, Jackson metadata, Bean Validation, and Swagger annotations. Schemas are normally placed under `components.schemas` and reused across request bodies, responses, parameters, or nested schemas via `$ref` references.

This mechanism keeps documents concise and avoids duplicating definitions. However, if two different Java types map to the same component name, or a reference points to a nonexistent key, the OpenAPI document can become invalid or fail to describe the runtime payload accurately.

Common symptoms:

- Two DTOs in different packages share the same simple name and cause component name collisions.
- A `@Schema(name = "...")` duplicates another schema's name.
- A customizer adds a component using a key already used by Springdoc.
- A request or response references a schema name with wrong casing.
- `$ref` uses an incorrect path or JSON Pointer escaping.
- A component is renamed while referencing locations still use the old name.
- A document group omits a component referenced by a customizer.
- External references use relative paths that break after distributing files.

A document may parse cleanly as JSON/YAML yet still contain unresolved `$ref`s. Conversely, a reference may resolve yet point to the wrong schema with a different structure, causing client generators to build wrong models.

This lesson explains how Springdoc names and registers schemas, how to read `$ref`, how to resolve collisions, and how to validate the contract before publishing.

## 2. `components.schemas` Is the Shared Definition Store

OpenAPI stores reusable schemas in `components.schemas`. For example:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: "1.0.0"

paths:
  /api/orders/{id}:
    get:
      responses:
        "200":
          description: Order found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderResponse"

components:
  schemas:
    OrderResponse:
      type: object
      required:
        - id
        - status
      properties:
        id:
          type: string
        status:
          type: string
          enum:
            - NEW
            - SHIPPED
~~~

In the example, the response does not repeat the entire `OrderResponse` structure. It references the component keyed by `OrderResponse`.

Key points to remember:

- `components.schemas` is a map.
- Every key in the map is a public schema name in the document.
- `$ref` must point directly to that key.
- Key names are case-sensitive.
- Renaming a key is a contract change, as client generators may use that key as the model name.

One DTO can be used across multiple operations. Springdoc typically creates one component schema and references it from each usage site. When the same type appears in multiple responses, reusing the component keeps a single consistent definition.

## 3. Why Can Two Java Classes Share the Same Schema Name?

Simple Java class names are not guaranteed to be unique across an entire application. For example:

~~~text
com.acme.identity.dto.UserDto
com.acme.billing.dto.UserDto
~~~

These two classes share the simple name `UserDto` yet carry different meanings:

- Identity `UserDto` has `id`, `displayName`, and `roles`.
- Billing `UserDto` has `customerNumber`, `taxCode`, and `billingAddress`.

If both map to the same component key `UserDto`, one definition can collide with the other. Depending on the resolver and library version, the document may generate altered names, overwrite definitions, or fail to represent the model an operation needs.

Common sources of collisions:

- Two classes with the same simple name in different packages.
- Nested DTOs sharing a name with a top-level DTO.
- Two independent modules declaring schemas with the same name.
- Multiple `@Schema` annotations setting the same `name`.
- Customizers or `ModelConverter` implementations registering schemas with conflicting keys.
- A manual component colliding with a Springdoc-generated component.
- Refactoring package structures without checking published component names.

Do not rely on class scanning order or bean initialization order to resolve collisions. Output must stay deterministic across local, CI, and production.

## 4. Using Meaningful Schema Names with `@Schema(name)`

For public schemas, the easiest way to keep control is assigning explicit component names via `@Schema(name = "...")`.

Example of two DTOs sharing a Java name across different business domains:

~~~java
package com.acme.identity.dto;

@Schema(name = "IdentityUser")
public record UserDto(
    String id,
    String displayName,
    List<String> roles
) {
}
~~~

~~~java
package com.acme.billing.dto;

@Schema(name = "BillingCustomer")
public record UserDto(
    String customerNumber,
    String taxCode,
    BillingAddress billingAddress
) {
}
~~~

In the OpenAPI document, the two components are named `IdentityUser` and `BillingCustomer`. The Java classes can remain `UserDto` in their own packages while the contract names are explicit.

Naming rules should be:

- Unique across the entire document.
- Reflective of the business concept, not just package names.
- Stable across package refactorings.
- Readable in generated SDKs.
- Independent of environment or startup order.
- Used consistently in documentation and tests.

For already-published APIs, do not rename schemas arbitrarily. Renaming a component can change class names in client SDKs even when the JSON wire format does not change. Treat schema names as part of the contract experience and review diffs before changing them.

## 5. When to Consider Using Fully Qualified Class Names

Springdoc has a setting to use fully qualified names for schemas, typically controlled by `springdoc.use-fqn` in supported versions:

~~~yaml
springdoc:
  use-fqn: true
~~~

This distinguishes classes sharing a simple name using their full package-qualified names. For example, component names reflect packages rather than just `UserDto`.

This option can help in large multi-module codebases with many DTOs sharing simple names. However, weigh these trade-offs:

- Component names become long and coupled to internal package structure.
- Package refactorings can change schema names.
- Generated SDKs may produce long or altered model names.
- Enabling this on a published API can cause a large diff even with unchanged JSON payloads.
- Confirm the property is supported in your exact Springdoc version.

For public APIs requiring stable contract names, explicit `@Schema(name = "...")` usually gives better control. `use-fqn` fits cases where automatic disambiguation is preferred and package-tied schema names are acceptable.

Do not enable `use-fqn` merely to mask a collision without identifying its source. First find the classes or customizers registering the same component name.

## 6. Naming Schemas by Business Domain

A practical naming convention:

| Domain | Suggested component names |
|---|---|
| Identity | IdentityUser, IdentityRole |
| Billing | BillingCustomer, InvoiceSummary |
| Order | OrderResponse, OrderLine |
| Payment | PaymentRequest, PaymentResult |
| Shared primitives | Money, Address, PageMetadata |

Schema names do not need a `Dto` suffix. A component is a model name in the API contract; it may originate from a Java DTO without exposing internal class naming.

Avoid generic names like `Data`, `Result`, `Response`, or `Item` when multiple modules coexist. If schemas genuinely differ, name them to convey their scope or meaning.

Do not create multiple distinct components just to rename them if they share the exact same meaning and must stay synchronized. For truly shared types, reuse one shared schema. For two distinct business concepts, use two separate schemas even if their current fields happen to look identical.

## 7. Using `@Schema(implementation = ...)` to Clarify Types

When Springdoc cannot infer the right schema from wrappers or generic return types, specify `implementation` in the annotation.

Response example:

~~~java
@GetMapping("/{id}")
@ApiResponse(
    responseCode = "200",
    description = "Order found",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class)
    )
)
public ResponseEntity<?> findById(@PathVariable String id) {
    return ResponseEntity.ok(orderService.findById(id));
}
~~~

`implementation` specifies the class used to describe the response schema. It does not change the actual object returned by the controller.

If the controller returns `ApiEnvelope<OrderResponse>`, yet the annotation declares `OrderResponse` directly, the document will misrepresent the wrapper structure. Choose an implementation matching the actual JSON wire format.

For example:

~~~java
public record ApiEnvelope<T>(
    String requestId,
    T data
) {
}
~~~

If runtime JSON is an envelope containing `data`, OpenAPI must describe the corresponding wrapper. For complex generic schemas, inspect the document generated by your exact Springdoc version rather than assuming annotations resolved every type parameter.

## 8. Do Not Manually Register Components with Duplicate Names

A customizer can add schemas to `components`:

~~~java
@Bean
OpenApiCustomizer customSchemaCustomizer() {
    return openApi -> {
        if (openApi.getComponents() == null) {
            openApi.setComponents(new Components());
        }

        Schema<?> externalEvent = new ObjectSchema()
            .addProperty("eventId", new StringSchema())
            .addProperty("eventType", new StringSchema());

        openApi.getComponents()
            .addSchemas("ExternalEvent", externalEvent);
    };
}
~~~

This snippet illustrates adding the `ExternalEvent` component. Before registering, verify the key does not already exist.

If the key already exists, do not overwrite it silently. Check first:

~~~java
Map<String, Schema> schemas =
    openApi.getComponents().getSchemas();

if (schemas == null || !schemas.containsKey("ExternalEvent")) {
    openApi.getComponents()
        .addSchemas("ExternalEvent", externalEvent);
}
~~~

If the component already exists, explicitly decide whether to reuse the existing schema or fail with a configuration error. Do not simply check the key and skip without knowing whether the existing schema has the required structure.

In production applications, build a helper that checks component names and fails when two different sources register the same key. This catches collisions immediately during document generation.

## 9. Structure of Internal `$ref`

A local reference typically starts from the document root:

~~~yaml
$ref: "#/components/schemas/OrderResponse"
~~~

Parts of the reference:

- `#` points to the root of the current document.
- `/components` navigates to the `components` object.
- `/schemas` navigates to the `schemas` map.
- `/OrderResponse` selects the component keyed `OrderResponse`.

The reference must point to the exact node. The following is wrong if the component resides in `components.schemas`:

~~~yaml
$ref: "#/schemas/OrderResponse"
~~~

This is also wrong if the actual key is `OrderResponse`:

~~~yaml
$ref: "#/components/schemas/orderResponse"
~~~

JSON Pointer is case-sensitive. Copy the exact key defined in `components.schemas`.

## 10. JSON Pointer Escaping in Component Names

`$ref` uses URI fragments and JSON Pointer. If a key contains special characters, escape them per JSON Pointer rules:

- Replace `~` with `~0`.
- Replace `/` with `~1`.

Example key named:

~~~text
Legacy/Order~V1
~~~

The corresponding reference must encode the token:

~~~yaml
$ref: "#/components/schemas/Legacy~1Order~0V1"
~~~

To reduce errors, avoid slashes and tildes in component keys. Alphanumeric PascalCase names are easier to read, test, and compatible with more generators.

Do not use URL encoding in place of JSON Pointer escaping. The two mechanisms differ. When special keys exist, use an OpenAPI-aware parser to resolve references instead of splitting strings manually in scripts.

## 11. Common `$ref` Locations

Schemas can be referenced in many places:

**Response body**

~~~yaml
responses:
  "200":
    description: Success
    content:
      application/json:
        schema:
          $ref: "#/components/schemas/OrderResponse"
~~~

**Request body**

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: "#/components/schemas/CreateOrderRequest"
~~~

**Array item**

~~~yaml
type: array
items:
  $ref: "#/components/schemas/OrderLine"
~~~

**Nested property**

~~~yaml
properties:
  customer:
    $ref: "#/components/schemas/BillingCustomer"
~~~

**Composition**

~~~yaml
allOf:
  - $ref: "#/components/schemas/BaseEvent"
  - type: object
    properties:
      orderId:
        type: string
~~~

Not every `$ref` points to `components.schemas`. OpenAPI can also reference `parameters`, `responses`, `requestBodies`, `headers`, `examples`, and `securitySchemes`. When debugging, verify both the object kind and the exact `components` path.

## 12. Common Reference Mistakes

| Reference | Issue |
|---|---|
| #/components/schemas/Order | Valid if key Order exists |
| #/components/schema/Order | Wrong segment name: schemas is plural |
| #/components/schemas/order | Invalid if key is Order |
| #/schemas/Order | Missing components |
| #/components/schemas/OrderResponse | Invalid if component was renamed |
| #/components/responses/OrderResponse | Wrong component type if key is in schemas |
| #/components/schemas/Legacy~Order | Missing escaping if key contains ~ |
| #/components/schemas/Legacy/Order | Invalid if slash in key is unescaped |

A common mistake is changing `@Schema(name = "OrderView")` while a customizer or manual OpenAPI file still references `OrderResponse`. Search all usages of the old schema name and update them in the same change.

## 13. Avoid Hard-Coding `$ref` When Springdoc Can Infer It

When controllers use DTOs directly, Springdoc usually generates components and references automatically:

~~~java
@GetMapping("/{id}")
public OrderResponse getOrder(@PathVariable String id) {
    return orderService.getOrder(id);
}
~~~

When clearer response declarations are needed, use `implementation`:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Order found",
    content = @Content(
        schema = @Schema(implementation = OrderResponse.class)
    )
)
~~~

This binds the schema to a Java type, reducing the risk of mistyping a component name in a manual `$ref` string.

Hard-coding `$ref` may be needed when augmenting OpenAPI structures via customizers or referencing external documents. In those cases, manage component names and registration sites together.

Do not invent an assumed component key before checking how Springdoc actually names the schema. Inspect `/v3/api-docs` output or set explicit schema names.

## 14. `$ref` in OpenAPI 3.0 vs 3.1

Handling of sibling fields around `$ref` varies by version and context.

In OpenAPI 3.0, the Reference Object has strict limits; siblings alongside `$ref` are not treated as arbitrary properties. For example:

~~~yaml
$ref: "#/components/schemas/Order"
description: Order response
~~~

should not be used assuming `description` will always apply like a normal Schema Object across all 3.0 contexts.

OpenAPI 3.1 updates Reference Object to support `summary` and `description` under standard rules. Inside Schema Objects, `$ref` follows JSON Schema 2020-12 semantics, so sibling schema keywords are evaluated under JSON Schema rules.

When extra descriptions are needed, pick the right structure for the location and OpenAPI document version. Do not apply a single rule across every `$ref` type.

If an API supports both 3.0 and 3.1, validate each document with its corresponding validator. A valid 3.1 document does not mean older parsers interpret it the same way.

## 15. Distinguishing Broken References from Valid Recursive Schemas

Some models have recursive relationships:

~~~java
public record Category(
    String id,
    String name,
    Category parent
) {
}
~~~

The schema can reference itself:

~~~yaml
Category:
  type: object
  properties:
    id:
      type: string
    name:
      type: string
    parent:
      $ref: "#/components/schemas/Category"
~~~

This is a valid recursive schema when the structure and use case call for it. A circular `$ref` is not automatically a broken reference.

A broken reference is one that cannot resolve or points to the wrong node. A recursive reference resolves back to itself or a valid chain of components.

Do not infinitely inline recursion when bundling documents. Keep `$ref` to express relationships and use OpenAPI-aware tools for validation.

If a recursive schema could create overly deep payloads, consider enforcing depth limits in the API contract or application validation. OpenAPI schemas do not automatically bound runtime data size without explicit constraints.

## 16. External `$ref` and Paths During Distribution

OpenAPI can reference external files or URLs:

~~~yaml
$ref: "./schemas/common.yaml#/components/schemas/Address"
~~~

Or:

~~~yaml
$ref: "https://contracts.example.com/common/1.2.0.yaml#/components/schemas/Address"
~~~

External references introduce dependencies on the location and reachability of target files.

Common errors:

- `common.yaml` is not packaged with the artifact.
- Relative paths are resolved from a different base URI than expected.
- URLs require authentication that generators lack.
- URLs point to mutable content that changes over time.
- CI environments lack network access.
- Uploading documents to a portal alters directory layout and breaks relative refs.

For documents needing standalone distribution, external references can be bundled into a single resolved document if tooling and policy allow. If keeping external references, publish all dependencies and preserve URI structure.

Never use local file paths such as `C:/work/contracts/common.yaml` or `/home/runner/...` in public documents. Local paths are meaningless to clients and leak build environment details.

## 17. Checking Components Inside Document Groups

Springdoc can generate multiple documents via `GroupedOpenApi`. Each group includes only operations matching configured filters.

For example:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}
~~~

If a customizer adds an operation to the `public` group that references a component absent from that group, the document may end up with a broken `$ref`.

Similarly, a schema manually added to the default OpenAPI document does not necessarily appear in every group document. Check whether customizers apply globally or per group in your Springdoc version.

For each published group:

- Fetch the exact group endpoint.
- Check that referenced components exist in the same document.
- Resolve all local `$ref`s within the group.
- Verify no internal schemas leak into public groups.
- Run the validator independently for each group.

Do not use validation results from the default document to conclude all groups are valid.

## 18. Be Careful When Customizers Replace the Components Map

A customizer might intend to add a schema yet accidentally replace the entire `components` map:

~~~java
openApi.setComponents(new Components()
    .addSchemas("ExternalEvent", externalEvent));
~~~

If Springdoc had already generated `OrderResponse`, `Customer`, and other schemas, this snippet wipes them from the document.

Instead of replacing `Components`, retrieve the existing object and add the needed schema:

~~~java
Components components = openApi.getComponents();

if (components == null) {
    components = new Components();
    openApi.setComponents(components);
}

Map<String, Schema> schemas = components.getSchemas();

if (schemas == null || !schemas.containsKey("ExternalEvent")) {
    components.addSchemas("ExternalEvent", externalEvent);
}
~~~

If the name already exists, compare schemas and raise an error when two sources define different structures. Never overwrite silently because doing so can alter another operation's response schema.

Customizers should be deterministic: identical source code and configuration must yield identical components, keys, and references. Avoid depending on bean initialization order or request data.

## 19. Finding Collision Causes in Springdoc

When duplicate component names are detected:

1. Identify the colliding component key in OpenAPI output.
2. Search for DTOs with the corresponding simple name.
3. Check packages and nested classes.
4. Search for `@Schema(name = "...")` annotations with identical values.
5. Check `ModelConverter` and `OpenApiCustomizer` beans registering schemas manually.
6. Check dependencies/modules bringing in DTOs with the same name.
7. Compare documents before and after adding a module or dependency.
8. Assign explicit schema names to distinct models.
9. If using `use-fqn`, evaluate impacts on contract names and generated clients.
10. Reload the document and confirm each operation references the right component.

Do not merely edit component names in generated YAML output. The next generation run will recreate the collision if the root cause in Java annotations or customizers remains unfixed.

## 20. Testing `$ref` with MockMvc

You can test the OpenAPI endpoint generated by Springdoc using MockMvc.

Example verifying components exist:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.IdentityUser"
    ).exists())
    .andExpect(jsonPath(
        "$.components.schemas.BillingCustomer"
    ).exists());
~~~

Verify the operation references the right schema:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/identity/users/{id}'].get.responses['200']"
        + ".content['application/json'].schema['$ref']"
    ).value("#/components/schemas/IdentityUser"));
~~~

Adjust JSONPath expressions to match your application's actual paths and operations. Tests should verify both components and references, not just HTTP 200 status.

For document groups, call the group endpoint and run the same assertions for that group. For external references, test bundling or resolution matching how the artifact will be distributed.

## 21. Validating All References with OpenAPI Tools

MockMvc assertions are useful for key schemas yet do not replace resolving every reference.

You can use OpenAPI Generator CLI:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.yaml
~~~

Or Redocly CLI:

~~~bash
npx redocly lint target/openapi/openapi.yaml
~~~

Pin tool versions in CI. Choose versions that understand OpenAPI 3.0 or 3.1 matching your document.

For external references, configure resolvers and network policies explicitly. If the pipeline cannot reach external URLs, resolution failures must fail the job rather than being ignored.

Validators detect missing references, misplaced objects, and invalid schemas. Linters can add rules for naming, descriptions, and structure. Distinguish OpenAPI specification errors from internal convention warnings.

## 22. Common Errors and Resolutions

| Symptom | Possible cause | Resolution direction |
|---|---|---|
| Two DTOs in different packages share one component | Same simple name | Set unique `@Schema(name)` or evaluate `use-fqn` |
| Components vanish after customizer | Replaced entire `Components` | Add to existing object instead of replacing map |
| `$ref` returns unresolved error | Wrong key or wrong path | Match `components` and keys accurately |
| `$ref` wrong casing | Keys are case-sensitive | Use exact component name |
| Ref containing slash or tilde fails | Unescaped JSON Pointer | Use `~1` and `~0` per spec rules |
| Renaming `@Schema(name)` breaks document | Manual ref still uses old name | Update all references and tests |
| Response schema has wrong structure | `implementation` points to wrong DTO/wrapper | Describe accurate wire type |
| Group document lacks schema | Component not added to group | Use appropriate customizer and validate per group |
| External ref fails to resolve in CI | Wrong URL/path or access permissions | Bundle or publish dependencies with matching structure |
| Recursive model flagged as cycle | Tool handles recursion poorly | Use an OpenAPI-aware validator and keep refs |
| YAML contains duplicate keys | Two schemas share key in manual file | Use unique keys and a strict parser |
| Generated SDK renames models wholesale | Enabled `use-fqn` or changed naming convention | Review compatibility and keep contract names stable |

When investigating, save the OpenAPI JSON/YAML output and identify exactly which component key is missing or duplicated. Do not infer from annotations alone that the document was generated correctly.

## 23. Safe Remediation Procedure

When encountering schema collisions or broken `$ref`s:

1. Fetch the actual OpenAPI document from the right endpoint and group.
2. Identify the failing reference and expected component key.
3. Check whether the component exists in the same document.
4. Locate the DTOs, annotations, and customizers producing that component key.
5. Assign unique names to distinct models.
6. Preserve existing schema names if they are already stable public contracts.
7. Fix customizers so they do not overwrite `Components` or existing schemas.
8. Verify JSON Pointer escaping if keys contain special characters.
9. Verify external refs and relative base URIs.
10. Verify group-specific documents.
11. Run MockMvc tests for critical components and operations.
12. Run an OpenAPI validator/linter to resolve all references.
13. Review contract diffs before publishing.

If renaming a schema on an API already consumed by clients, treat it as a contract change. You may need to retain aliases or old components during a transition period, or release a new API version per organizational policy.

## 24. Principles for Keeping Schemas and References Stable

To prevent duplicate schema names and broken `$ref`s:

1. Assign unique, business-meaningful component names.
2. Use `@Schema(name)` when multiple classes share a simple name.
3. Only enable `springdoc.use-fqn` after evaluating contract impacts.
4. Use `@Schema(implementation)` matching runtime JSON.
5. Never register duplicate-key components via customizers.
6. Never replace the entire `Components` object when only adding a schema.
7. Verify `$ref` paths, casing, and JSON Pointer escaping.
8. Distinguish local references, external references, and recursive references.
9. Validate each document group independently.
10. Use MockMvc to test critical components and operations.
11. Run an OpenAPI-aware validator/linter in CI.
12. Review schema renames as API contract changes.

Schemas are the data models clients use to generate code and process requests/responses. A duplicate component name or broken `$ref` can break integration even while controllers continue running normally. Controlling schema names, keeping references synchronized, and validating Springdoc-generated documents keeps API contracts stable across module growth and code refactoring.

## 25. References

- Springdoc OpenAPI: https://springdoc.org/
- Springdoc Configuration Properties: https://springdoc.org/properties.html
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
- Swagger Core Annotations: https://github.com/swagger-api/swagger-core
- OpenAPI Generator CLI: https://openapi-generator.tech/docs/usage/

