# `$ref` and Sibling Properties by Context and Version

In OpenAPI, `$ref` enables reusing schemas, parameters, responses, request bodies, and many other components by referencing an existing definition. However, properties placed alongside `$ref` do not always take effect. How they are processed depends on the **context where `$ref` appears** and the **OpenAPI version** declared by the document.

The first distinction to make is:

- **Reference Object**: a reference object used at locations such as `responses`, `parameters`, `requestBody`, `headers`, or `examples`.
- **Schema Object**: an object describing data, where `$ref` is a JSON Schema keyword in OpenAPI 3.1.

In OpenAPI 3.0, properties placed alongside `$ref` are usually ignored. OpenAPI 3.1 changes behavior significantly for `$ref` inside a Schema Object: sibling schema keywords are evaluated alongside the referenced schema. Meanwhile, Reference Objects still have their own rules, permitting only `summary` and `description` as documentation override properties.

## 1. What is `$ref` used for?

Instead of repeating a schema or response across multiple operations, you can define it once in `components` and reference it with `$ref`.

Example of a reusable schema:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
components:
  schemas:
    Order:
      type: object
      required:
        - id
        - status
      properties:
        id:
          type: integer
          format: int64
        status:
          type: string
```

`#/components/schemas/Order` is a JSON Pointer pointing to the `Order` schema within the same OpenAPI document. When an operation references this schema, tools can share the definition without duplicating the entire structure.

Common locations for `$ref` include:

| Location | Example component |
|---|---|
| Schema | `#/components/schemas/Order` |
| Parameter | `#/components/parameters/PageSize` |
| Request body | `#/components/requestBodies/CreateOrder` |
| Response | `#/components/responses/NotFound` |
| Header | `#/components/headers/RateLimit` |
| Example | `#/components/examples/OrderExample` |
| Link | `#/components/links/OrderDetails` |
| Callback | `#/components/callbacks/OrderEvent` |

A component is just a named definition. Placing an object in `components` does not automatically expose it in the API; an operation must reference that component or use it through an appropriate mechanism.

Security schemes are a case to distinguish: an operation does not use `$ref` to reference a security scheme. It uses the scheme's key name in a Security Requirement Object, e.g. `security: [{ bearerAuth: [] }]`, while the scheme definition resides at `components.securitySchemes.bearerAuth`.

## 2. Before examining siblings, determine the `$ref` context

The syntax `$ref` is the same, yet rules can vary depending on position.

### `$ref` at a Reference Object position

Example referencing a response:

```yaml
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
components:
  responses:
    NotFound:
      description: Order not found
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
```

The object at `responses['404']` is a Reference Object because this position accepts a Response Object or a Reference Object. `$ref` points to the reusable response.

Similar positions are elements in `parameters`, `requestBody` at the operation level, `headers`, `examples`, `callbacks`, and corresponding components.

### `$ref` inside a Schema Object

Example referencing a schema property:

```yaml
components:
  schemas:
    Customer:
      type: object
      properties:
        address:
          $ref: '#/components/schemas/Address'
    Address:
      type: object
      properties:
        city:
          type: string
        country:
          type: string
```

The object at `properties.address` is a Schema Object. In OpenAPI 3.1, `$ref` here follows JSON Schema keyword rules and can appear alongside other schema keywords. In OpenAPI 3.0, sibling properties of `$ref` do not take effect per Reference Object rules.

Do not apply Schema Object rules to response or parameter Reference Objects. Conversely, do not assume every `$ref` in a 3.1 schema may only have `summary` and `description` like a Reference Object.

## 3. Rules in OpenAPI 3.0

OpenAPI 3.0 defines its own Reference Object. In a Reference Object context, `$ref` is required; other added properties are ignored.

Example:

```yaml
openapi: 3.0.3
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
          description: Order does not exist
components:
  responses:
    NotFound:
      description: Resource not found
```

In OpenAPI 3.0, `description` placed beside `$ref` in a response reference does not override the component's description. Reference Objects are strictly for referencing; siblings such as `description`, `summary`, `content`, `headers`, or `required` are not used to customize the referenced object.

The same rule applies when `$ref` appears in a Schema Object position in OpenAPI 3.0: do not rely on siblings to add constraints or metadata. The example below does not mean the schema both references `Address` and gains a new `description`:

```yaml
properties:
  shippingAddress:
    $ref: '#/components/schemas/Address'
    description: Shipping address
```

With OpenAPI 3.0, the sibling `description` is ignored. If you need to add descriptions or constraints, use a compatible composition approach such as `allOf` or define a dedicated component.

## 4. Rules in OpenAPI 3.1: Reference Object

OpenAPI 3.1 adds two special properties to Reference Object:

- `summary`: a summary that overrides the referenced object's summary when rendering documentation.
- `description`: a description that overrides the referenced object's description when rendering documentation.

Example response reference:

```yaml
openapi: 3.1.0
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
          description: Requested order was not found.
components:
  responses:
    NotFound:
      description: Resource not found.
```

In OpenAPI 3.1, `description` on a Reference Object can replace the description of the referenced response at that usage site. The original component definition stays intact so other sites can use the original description.

Do not overgeneralize this rule to “every sibling works”. For Reference Objects, `summary` and `description` are the two specified properties; other additional properties are still ignored.

The following example is not a valid way to customize a response using siblings:

```yaml
responses:
  '404':
    $ref: '#/components/responses/NotFound'
    content:
      application/json:
        schema:
          type: object
```

`content` is not an allowed override property of a Reference Object. If a different response is needed, create a separate response component or define the response inline.

## 5. Rules in OpenAPI 3.1: `$ref` inside a Schema Object

OpenAPI 3.1 aligns the Schema Object with JSON Schema Draft 2020-12. Therefore, when `$ref` is used as a keyword inside a Schema Object, sibling keywords are applied alongside the referenced schema instead of being ignored.

Example adding `description` and a length limit to a referenced schema:

```yaml
openapi: 3.1.0
components:
  schemas:
    ShortCode:
      type: string
      minLength: 1
    CreateOrderRequest:
      type: object
      properties:
        code:
          $ref: '#/components/schemas/ShortCode'
          description: Order code issued by the partner system.
          maxLength: 20
```

The schema at `code` is evaluated against both the `ShortCode` schema and the sibling keyword `maxLength: 20`. Consequently, values must satisfy `type: string` and `minLength: 1` from the referenced schema as well as `maxLength: 20` from the local schema.

Example adding an `enum` constraint:

```yaml
properties:
  status:
    $ref: '#/components/schemas/OrderStatus'
    enum:
      - NEW
      - PAID
```

In OpenAPI 3.1, the sibling `enum` is an additional schema constraint. Valid values must satisfy both the referenced schema and the local `enum` simultaneously. It does not replace the `enum` inside the component; the two constraint sets combine under JSON Schema's logical AND.

Siblings can be validation keywords (`maxLength`, `minimum`, `pattern`, `enum`, `required`, `properties`, `items`, `additionalProperties`, etc.) or annotation keywords (`title`, `description`, `default`, `examples`, `deprecated`, `readOnly`, `writeOnly`, etc.) provided the keyword is valid in the Schema Object and active dialect.

Do not place `summary` inside a Schema Object merely because a 3.1 Reference Object supports `summary`; `summary` is not a standard JSON Schema keyword for Schema Objects.

## 6. Comparison table of siblings by context and version

| Context | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Reference Object at `responses`, `parameters`, `requestBody`, etc. | Relies solely on `$ref`; other siblings are ignored | `summary` and `description` can override documentation content; other siblings are ignored |
| `$ref` inside a Schema Object | Do not rely on siblings; accompanying properties are not applied as schema constraints | Sibling schema keywords are evaluated alongside the referenced schema |
| `description` beside `$ref` in a response reference | Ignored | Overrides `description` for display at the reference site |
| `description` beside `$ref` in a property schema | Ignored | Applied as a Schema Object annotation |
| `maxLength` beside `$ref` in a property schema | Ignored | Applied as an additional validation keyword |
| `content` beside `$ref` in a response reference | Ignored | Still ignored; not an allowed Reference Object override property |

When reading an OpenAPI document, answer in order: which version the document declares, whether `$ref` is at a Reference Object or Schema Object position, and whether the sibling is a permitted property in that context.

## 7. Writing compatible OpenAPI 3.0 and 3.1 documents

If a document must be consumed by both OpenAPI 3.0 and 3.1 tools, the safe approach is not to depend on `$ref` siblings to add metadata or constraints. Place metadata inside shared components or create separate schemas/components.

For example, instead of:

```yaml
properties:
  externalCode:
    $ref: '#/components/schemas/Code'
    description: Code provided by partner
    maxLength: 30
```

create a separate schema using `allOf`:

```yaml
components:
  schemas:
    Code:
      type: string
      minLength: 1
    ExternalCode:
      allOf:
        - $ref: '#/components/schemas/Code'
        - type: string
          maxLength: 30
      description: Code provided by partner
```

Then the property references the new schema:

```yaml
properties:
  externalCode:
    $ref: '#/components/schemas/ExternalCode'
```

`allOf` is a Schema Object composition keyword, not an arbitrary sibling on a Reference Object. All schemas in `allOf` must be satisfied simultaneously. `ExternalCode` therefore satisfies both `Code` and the additional length constraint.

If you only need to change the description for a response in OpenAPI 3.0, you can create another response component with its own description or define the response inline instead of attempting a sibling override.

## 8. `allOf`, `oneOf`, `anyOf`, and `$ref`

Composition keywords help combine multiple schemas. They frequently appear alongside `$ref`, yet each keyword has a distinct meaning:

| Keyword | Meaning |
|---|---|
| `allOf` | Instance must be valid against all subschemas |
| `oneOf` | Instance must be valid against exactly one subschema |
| `anyOf` | Instance must be valid against at least one subschema |
| `not` | Instance must not be valid against the specified schema |

Example using `allOf` to add properties:

```yaml
components:
  schemas:
    Person:
      type: object
      required: [name]
      properties:
        name:
          type: string
    Employee:
      allOf:
        - $ref: '#/components/schemas/Person'
        - type: object
          required: [employeeId]
          properties:
            employeeId:
              type: string
```

`Employee` must satisfy both `Person` and the supplemental schema. `allOf` is not an object-oriented class inheritance mechanism; it is a validation intersection.

One important caveat: if a constituent schema sets `additionalProperties: false`, adding properties in another schema inside `allOf` may be rejected by that constituent schema because those properties are not declared inside its own object schema. For complex extensible models, design `additionalProperties` and composition deliberately; in OpenAPI 3.1, `unevaluatedProperties` may fit better in some cases, though validator and client generator support must be checked.

## 9. `$ref` in Parameters, Responses, and Request Bodies

Reference Objects allow reusing HTTP structures, not just schemas.

Example of a shared parameter:

```yaml
components:
  parameters:
    PageSize:
      name: pageSize
      in: query
      description: Maximum number of items per page.
      required: false
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
paths:
  /orders:
    get:
      parameters:
        - $ref: '#/components/parameters/PageSize'
      responses:
        '200':
          description: Order list
```

Example of a shared request body:

```yaml
components:
  requestBodies:
    CreateOrder:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateOrderRequest'
paths:
  /orders:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateOrder'
      responses:
        '201':
          description: Order created
```

Example of a shared response:

```yaml
components:
  responses:
    NotFound:
      description: Resource not found
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
```

In the examples above, `$ref` in `parameters`, `requestBody`, and `responses` is a Reference Object. If you need to change `required`, `schema`, `content`, or `headers` at one usage site, create another component or declare the object directly. Do not add those properties beside `$ref` expecting them to override the component.

## 10. Reference paths: JSON Pointer and URI

A `$ref` value is a URI-reference. It can point to:

- A location within the same document using a fragment, e.g. `#/components/schemas/Order`.
- Another file relative to the current document, e.g. `./common-schemas.yaml#/components/schemas/Address`.
- A resource at an absolute URL, e.g. `https://schemas.example.com/common.yaml#/components/schemas/Address`.

Example of an external reference:

```yaml
components:
  schemas:
    Address:
      $ref: './schemas/address.yaml#/Address'
```

Relative paths are resolved against the base URI of the document containing the reference, not necessarily the application's working directory or source code folder. When moving OpenAPI files, re-verify relative references.

Fragments starting with `#` typically use JSON Pointer. In JSON Pointer:

- `~` is escaped as `~0`.
- `/` is escaped as `~1`.

For example, a component with the key `Order/Item` must be referenced as:

```yaml
$ref: '#/components/schemas/Order~1Item'
```

If a key contains `~`, it must be escaped first per JSON Pointer rules—for instance, `A~B` becomes `A~0B`. Because `$ref` is a URI-reference, characters needing URI encoding must also be handled properly. Do not concatenate path strings manually while skipping JSON Pointer escaping.

## 11. External references and document bundling

External references help split large schemas into multiple files, though they add distribution requirements:

- Referenced resources must exist at locations accessible to consumers.
- Relative URLs must remain valid after publishing or moving documents.
- If a browser loads cross-origin files, CORS may affect resolution.
- Bundle/validator tools must be configured to read local files or remote URLs according to policy.
- Build pipelines must package all referenced files or bundle them if consumers only accept a single file.

Do not assume the `/v3/api-docs` endpoint automatically embeds the contents of every external `$ref`. Springdoc may generate a document containing references; resolving or bundling external resources depends on configuration and downstream tools. Inspect the final OpenAPI JSON/YAML and test loading it from the actual deployment environment.

For references to external URLs, consider stability, access control, caching, and supply-chain risk. A schema URL whose contents change can alter your application's contract without a commit in your repository. If reproducibility is needed, pin resources by version or keep controlled copies in source/artifacts.

## 12. Recursive references and nested schemas

`$ref` can reference a schema that references itself back. This is how tree structures or recursive relationships are described.

```yaml
components:
  schemas:
    Category:
      type: object
      required: [id, name]
      properties:
        id:
          type: integer
        name:
          type: string
        children:
          type: array
          items:
            $ref: '#/components/schemas/Category'
```

The `Category` schema can contain a list of `children`, each of which is also a `Category`. This is a valid recursive reference. Client generators or schema renderers must support recursive models; some tools may display or generate code differently.

Distinguish intentional recursion from broken reference cycles. For example, a `$ref` pointing to a nonexistent key, an unreachable external file, or a malformed fragment is an unresolvable reference. With recursion, the reference path still resolves to a valid schema—the schema simply contains a reference to itself.

## 13. `$ref` and discriminator in polymorphism

When a field can hold multiple object types, `$ref` is typically combined with `oneOf` or `anyOf`, and `discriminator` can be used to help tools identify the subtype.

```yaml
components:
  schemas:
    PaymentMethod:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransfer'
      discriminator:
        propertyName: type
        mapping:
          card: '#/components/schemas/CardPayment'
          bank-transfer: '#/components/schemas/BankTransfer'
    CardPayment:
      type: object
      required: [type, last4]
      properties:
        type:
          type: string
          const: card
        last4:
          type: string
    BankTransfer:
      type: object
      required: [type, accountNumber]
      properties:
        type:
          type: string
          const: bank-transfer
        accountNumber:
          type: string
```

In this example, `oneOf` requires payloads to be valid against exactly one subschema. `discriminator` provides subtype mapping hints based on the `type` property; it does not replace `oneOf` validation. Ensure subschemas are distinguishable and mappings point to valid references.

JSON Schema keywords like `const` exist in OpenAPI 3.1 but are not part of the OpenAPI 3.0 Schema Object subset. If 3.0 compatibility is required, a single-element `enum` can represent a fixed value, and output should be re-checked for the target version.

## 14. Impact of JSON Schema dialects in OpenAPI 3.1

OpenAPI 3.1 aligns the Schema Object with JSON Schema Draft 2020-12 and supports declaring a dialect via `jsonSchemaDialect` at the document level. If omitted, OpenAPI uses the base dialect defined for OAS 3.1.

This matters because keywords such as `$ref`, `$id`, `$anchor`, `$dynamicRef`, `unevaluatedProperties`, `prefixItems`, or custom vocabularies can affect how schemas are resolved and evaluated. Not every OpenAPI tool supports all of JSON Schema 2020-12 or custom dialects equally.

For example, `$id` can define the base URI of a schema resource in JSON Schema. When using nested `$id` or external schema resources, reference resolution rules can differ from simply appending a fragment to the original OpenAPI URL. Use a dialect-aware validator and verify base URLs when schemas contain `$id`.

`$dynamicRef` and `$dynamicAnchor` are advanced mechanisms of JSON Schema 2020-12, useful in certain extensible recursive schemas. They are not general-purpose replacements for `$ref`; use them only when you understand dynamic scoping and have confirmed validator/client generator support.

## 15. How does Springdoc generate and use `$ref`?

Springdoc analyzes controllers, DTO types, Swagger annotations, and model converters to create an OpenAPI document. When a DTO is used as a request or response schema, Springdoc typically places the reusable definition in `components.schemas` and references it via `$ref`.

Example Java DTO:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "OrderSummary", description = "Order summary information")
public record OrderSummary(
    Long id,
    String status,
    String customerName
) {
}
```

A controller can use the same DTO across multiple operations:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{id}")
    OrderSummary getOrder(@PathVariable Long id) {
        return orderService.getSummary(id);
    }

    @GetMapping("/api/orders/recent")
    List<OrderSummary> recentOrders() {
        return orderService.findRecentSummaries();
    }
}
```

The generated document typically contains an `OrderSummary` schema component; responses of both operations reference that component, with the list operation using an array schema whose `items.$ref` points to it.

Component names can be influenced by model converters, generic types, packages, and Springdoc settings. Use `@Schema(name = "...")` when stable, meaningful schema names are required. Do not edit generated JSON output directly as a primary source of truth; update DTOs, annotations, or customizers so changes are reproduced every time the application starts.

If using `@Schema` with `implementation`, `ref`, or `allOf`, check the Swagger Annotations and Springdoc versions in use. Annotations can produce different Schema Objects depending on context; what matters is inspecting the actual OpenAPI document, especially `$ref` siblings and the root `openapi` version.

## 16. Inspecting `$ref` in a Springdoc document

After the application starts, fetch the OpenAPI JSON:

```bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
```

Check the document version:

```bash
jq -r '.openapi' openapi.json
```

Check a component schema:

```bash
jq '.components.schemas.OrderSummary' openapi.json
```

Check an operation's response schema:

```bash
jq '.paths["/api/orders/{id}"].get.responses["200"].content["application/json"].schema' openapi.json
```

Check generated `$ref` entries:

```bash
jq '.. | objects | select(has("$ref")) | ."$ref"' openapi.json
```

When you see a `$ref` with siblings, check the exact context:

1. Read `.openapi` to know whether the document is 3.0 or 3.1.
2. Determine whether the object containing `$ref` is a Reference Object or a Schema Object.
3. Determine whether the sibling is an allowed property in that context.
4. Check whether downstream tools support the corresponding semantics.
5. Run a validator or contract test against the final document.

Do not rely solely on Swagger UI to conclude `$ref` is processed correctly. The UI might hide invalid siblings or display the description from the original component, making issues hard to spot. Inspect raw JSON/YAML and validation output.

## 17. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| `description` beside `$ref` does not appear in OpenAPI 3.0 | Reference Object siblings are ignored | Place `description` in the component or create a separate component |
| `maxLength` beside `$ref` does not constrain schema in 3.0 | Schema `$ref` siblings are not applied | Use `allOf` with an additional schema or a separate component |
| `content` beside a response `$ref` does not change the response component | `content` is not an allowed override sibling on a Reference Object | Create another response component or declare the response inline |
| Sibling `description` works in 3.1 but not in 3.0 | Version rule difference | Check the `openapi` field and adjust schemas to match the version |
| Sibling constraints in a 3.1 Schema Object are ignored by validator | Tool uses an OAS 3.0 parser or older JSON Schema dialect | Upgrade/configure the validator to support OAS 3.1 |
| `$ref` does not resolve | Wrong JSON Pointer, file path, URL, or access permissions | Check base URI, escaping, and target resource |
| Reference with key containing `/` fails to resolve | Did not escape JSON Pointer token to `~1` | Escape `/` as `~1` and `~` as `~0` |
| External ref works locally but breaks when published | Relative path changed or file was not packaged | Bundle or distribute all external resources |
| `allOf` schema rejects extended properties | `additionalProperties: false` in a subschema | Redesign composition; consider `unevaluatedProperties` with OAS 3.1 |
| Recursive schema breaks client generator | Downstream tool lacks good recursion support | Check recursive model support or adjust the contract for the target client |
| `oneOf` fails to distinguish subtypes | Overlapping subschemas or wrong discriminator mapping | Design discriminator/properties and verify each branch |

## 18. Checklist for using `$ref` safely

- [ ] Verified whether the OpenAPI document is 3.0.x or 3.1.x.
- [ ] Identified whether `$ref` sits inside a Reference Object or a Schema Object.
- [ ] Avoided arbitrary siblings on Reference Objects.
- [ ] For 3.1 Reference Objects, relied only on the specified `summary`/`description` overrides.
- [ ] For 3.1 Schema Objects, ensured siblings are valid keywords in the active dialect.
- [ ] For 3.0 documents, used `allOf` or separate components to add constraints/metadata.
- [ ] Component names and JSON Pointer fragments match exactly.
- [ ] Escaped `~` as `~0` and `/` as `~1` in JSON Pointer tokens.
- [ ] External references have valid base URIs and packaged/served resources.
- [ ] Recursion is intentional and supported by downstream tools.
- [ ] `allOf`, `oneOf`, and `anyOf` are used according to proper validation semantics.
- [ ] `discriminator` mappings point to valid schemas and branches are distinguishable.
- [ ] Springdoc output is inspected after changing DTOs, annotations, or customizers.
- [ ] Validators and client generators support the OpenAPI/JSON Schema version declared by the document.

`$ref` does not have a single sibling rule for every location. In Reference Objects, OpenAPI 3.0 ignores accompanying properties, whereas OpenAPI 3.1 allows `summary` and `description` to override documentation text. In OpenAPI 3.1 Schema Objects, `$ref` follows JSON Schema and sibling schema keywords are applied alongside the referenced schema. By identifying the exact context and version before writing references, using `allOf` when 3.0 compatibility is needed, and checking raw Springdoc documents with validators and client generators, contracts become far easier to reuse and less error-prone.

## References

- [OpenAPI Specification 3.0.4 – Reference Object](https://spec.openapis.org/oas/v3.0.4.html#reference-object)
- [OpenAPI Specification 3.1.1 – Reference Object](https://spec.openapis.org/oas/v3.1.1.html#reference-object)
- [OpenAPI Specification 3.1.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object)
- [OpenAPI Specification 3.1.1 – Relative References in URLs](https://spec.openapis.org/oas/v3.1.1.html#relative-references-in-urls)
- [JSON Schema 2020-12 – Core, `$ref` and base URI](https://json-schema.org/draft/2020-12/json-schema-core.html)
- [JSON Schema 2020-12 – Validation](https://json-schema.org/draft/2020-12/json-schema-validation.html)
- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
