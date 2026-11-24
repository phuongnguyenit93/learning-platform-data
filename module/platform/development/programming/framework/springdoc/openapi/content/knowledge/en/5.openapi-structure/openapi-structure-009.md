# `$ref` References and How References Are Resolved

In OpenAPI, `$ref` allows one part of a specification to reuse a schema, parameter, response, or component defined elsewhere. References keep documents concise, avoid duplicate declarations, and maintain consistent data models. Springdoc also commonly generates shared schemas in `components` and links to them with `$ref` when describing complex Java types.

To read or organize a specification with many `$ref` pointers, you must understand three parts: the URI identifying the target document, the JSON Pointer identifying the location inside that document, and the resolver loading/reading the target and validating the object type. A syntactically valid reference can still fail to resolve if the file does not exist, the fragment is wrong, or the tool cannot access external resources.

## 1. What Is `$ref` Used For?

`$ref` is a URI value pointing to another object. The target object may reside in the current OpenAPI file, in another JSON/YAML file, or at an external URI.

Common benefits:

- **Reuse**: multiple operations reference the same `Address` schema or `NotFound` response.
- **Consistency**: editing a shared definition once updates its description everywhere it is referenced.
- **Document organization**: split schemas, paths, responses, and parameters into separate files when a specification grows large.
- **Reduced duplication**: avoid copying the same request/response structure across many endpoints.
- **Recursive model support**: a schema can reference itself, such as a category tree containing a list of child categories.

The shortest example is a response using a schema defined in `components`:

```yaml
openapi: 3.1.0
info:
  title: Shop API
  version: 1.0.0
paths:
  /products/{id}:
    get:
      responses:
        '200':
          description: Product found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
```

In this example, `Product` is defined only once in `components.schemas`. The `200` response points to that definition using `#/components/schemas/Product`.

## 2. Structure of a Reference

A typical reference has two parts:

```text
<Document URI>#<location fragment>
```

- The part before `#` identifies the document. This part can be empty when referencing within the current document.
- The part after `#` identifies the location inside the document, typically using a JSON Pointer.

| Form | Example | Meaning |
|---|---|---|
| Same-document reference | `#/components/schemas/Product` | Look up schema `Product` inside `components` of the current file. |
| Relative file reference | `./schemas/product.yaml` | Take the root object from `product.yaml` in the `schemas` subdirectory. |
| Relative file with fragment | `./common.yaml#/components/schemas/Address` | Open `common.yaml`, then look up schema `Address`. |
| Parent-directory file reference | `../shared/errors.yaml#/components/responses/NotFound` | Go up one directory, then look up response `NotFound`. |
| Absolute URI reference | `https://api.example.com/openapi/common.yaml#/components/schemas/Address` | Fetch the schema from the document at the stated URI. |

The `$ref` value must be a valid URI. For relative references, resolvers use the base URI of the document containing the reference. Therefore, when moving an OpenAPI file to another directory, relative paths may need to be updated.

In YAML, enclose URIs containing fragments in single or double quotes:

```yaml
$ref: '#/components/schemas/Product'
```

This prevents `#` from being interpreted by YAML as the start of a comment in ambiguous positions.

## 3. JSON Pointer: Pinpointing the Exact Location in a Document

JSON Pointer is a syntax for identifying a specific value inside a JSON tree. In OpenAPI, a common fragment like `#/components/schemas/Product` means starting at the document root, traversing the `components` property, then `schemas`, and retrieving the entry named `Product`.

Tokens in a JSON Pointer are separated by `/`:

```text
#/components/schemas/Product
  └ components
      └ schemas
          └ Product
```

If a key name contains special characters, JSON Pointer requires escaping:

| Character in Key Name | Written in JSON Pointer |
|---|---|
| `~` | `~0` |
| `/` | `~1` |

For example, if a component is named `Order/Item`, the reference must be written:

```yaml
$ref: '#/components/schemas/Order~1Item'
```

If the component name is `Legacy~Product`, use:

```yaml
$ref: '#/components/schemas/Legacy~0Product'
```

When a key contains both characters, escape each character according to JSON Pointer rules. Do not replace `/` with a hyphen or omit `~`; doing so points to a different key and causes the reference to fail resolution.

JSON Pointer can also address array elements by index, such as `#/paths/~1products/get/parameters/0`. However, referencing named components inside `components` is usually much easier to maintain because it does not depend on array element order.

## 4. Types of Elements Commonly Referenced

OpenAPI provides the `components` area to store reusable definitions. Common groups include:

| Location | Content | Usage Example |
|---|---|---|
| `components/schemas` | Request/response data structures | `schema` inside `content` |
| `components/parameters` | Path, query, header, or cookie parameters | `parameters` array of Path Item/Operation |
| `components/responses` | Shared HTTP response descriptions | Values inside `responses` |
| `components/requestBodies` | Shared request bodies | `requestBody` of an operation |
| `components/headers` | Shared response headers | `headers` inside Response Object |
| `components/examples` | Shared request/response examples | `examples` inside Media Type Object |
| `components/securitySchemes` | Authentication methods such as Bearer, API key, or OAuth2 | `security` at document or operation level |
| `components/links` | Links to follow-up operations | `links` inside Response Object |
| `components/callbacks` | Shared callback descriptions | `callbacks` of an operation |

Example reusing a parameter and a response:

```yaml
paths:
  /orders:
    get:
      parameters:
        - $ref: '#/components/parameters/PageSize'
      responses:
        '404':
          $ref: '#/components/responses/NotFound'

components:
  parameters:
    PageSize:
      name: size
      in: query
      description: Maximum items per page
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
  responses:
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
  schemas:
    ApiError:
      type: object
      properties:
        code:
          type: string
        message:
          type: string
```

A definition sitting inside `components` does not create an endpoint or appear in the consumer API contract on its own. It only takes effect when referenced from a place used by OpenAPI.

## 5. Distinguishing a Reference Object from a Schema Object with `$ref`

This is an easy point of confusion. `$ref` can appear inside a Reference Object—such as when a response reuses another response—or as a keyword inside a Schema Object to reuse a schema. Rules for handling sibling properties next to `$ref` differ by OpenAPI version.

### 5.1. Reference Object in OpenAPI 3.0

In OpenAPI 3.0, a Reference Object has only the `$ref` field. Other fields placed beside it are ignored by the specification. The following example cannot use `description` to override the referenced response's description:

```yaml
responses:
  '404':
    $ref: '#/components/responses/NotFound'
    description: Order not found
```

With OpenAPI 3.0, place the desired description inside the target component or create a separate response if the semantics differ.

### 5.2. Reference Object in OpenAPI 3.1

In OpenAPI 3.1, a Reference Object allows adding `summary` and `description`; these fields can override the corresponding values on the referenced object. Other arbitrary fields are still not considered valid extensions of a Reference Object.

```yaml
responses:
  '404':
    $ref: '#/components/responses/NotFound'
    description: No order found with the provided ID
```

This example uses OpenAPI 3.1 Reference Object rules. If the document must remain compatible with OpenAPI 3.0, put the description inside the component or define a separate response.

### 5.3. `$ref` Inside a Schema Object

The Schema Object in OpenAPI 3.1 is based on JSON Schema. Therefore, other keywords can be applied alongside `$ref` following JSON Schema rules. Example:

```yaml
components:
  schemas:
    DetailedAddress:
      $ref: '#/components/schemas/Address'
      description: Shipping address for the order
```

OpenAPI 3.0 uses an older subset of JSON Schema and handles `$ref` differently. To add metadata or constraints around a referenced schema while staying compatible with 3.0, use `allOf`:

```yaml
components:
  schemas:
    DetailedAddress:
      description: Shipping address for the order
      allOf:
        - $ref: '#/components/schemas/Address'
```

`allOf` combines subschemas into a schema that must satisfy all components. Do not use `allOf` merely to mask a broken reference; the target schema must still exist and be valid.

Before relying on sibling keywords alongside `$ref`, inspect the `openapi` field in the exported document. Springdoc provides `springdoc.api-docs.version` to choose between OpenAPI 3.0 and 3.1; exact configuration values and support depend on the application's springdoc branch.

## 6. How Does Springdoc Generate and Use `$ref`?

When controllers accept or return complex Java types, springdoc typically creates schemas in `components.schemas` and uses local `$ref` pointers to link schemas. This lets DTOs sharing nested types reuse a single definition.

DTO example:

```java
public record OrderResponse(
        String id,
        AddressResponse shippingAddress,
        AddressResponse billingAddress
) {}

public record AddressResponse(
        String street,
        String city,
        String postalCode
) {}
```

The generated specification may look similar to:

```yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        id:
          type: string
        shippingAddress:
          $ref: '#/components/schemas/AddressResponse'
        billingAddress:
          $ref: '#/components/schemas/AddressResponse'
    AddressResponse:
      type: object
      properties:
        street:
          type: string
        city:
          type: string
        postalCode:
          type: string
```

This illustrates the output structure; exact schema names and property details depend on Java types, annotations, Jackson configuration, model converters, and the springdoc version. You can use `@Schema` to add names, descriptions, examples, or model metadata. If you need to define components manually, add schemas to `OpenAPI.components` via a configuration bean or customizer.

Springdoc provides `SpringDocAnnotationsUtils.extractSchema` to build a schema from a Java type using the same annotation and converter pipeline springdoc uses for controllers. This helper also registers nested schemas in `Components` and returns the corresponding reference schema. That is useful when manually adding operations not declared via controllers, such as endpoints served by filters.

Springdoc primarily generates local references within the application's OpenAPI document. If you split the document across files yourself or introduce `$ref` pointing to remote resources, use an OpenAPI parser/resolver that supports external references. Never assume Swagger UI or every consumer can fetch arbitrary external URIs.

## 7. Referencing External Files

When a specification is large, schemas or paths can be split into separate files. Example directory layout:

```text
openapi/
├── openapi.yaml
├── paths/
│   └── orders.yaml
└── schemas/
    ├── order.yaml
    └── address.yaml
```

The root file can reference a path item:

```yaml
paths:
  /orders:
    $ref: './paths/orders.yaml'
```

Inside `paths/orders.yaml`, a schema can be referenced from its own schema file:

```yaml
get:
  responses:
    '200':
      description: Order list
      content:
        application/json:
          schema:
            type: array
            items:
              $ref: '../schemas/order.yaml'
```

If `order.yaml` is a complete schema, the file URI can point directly to the root object of the file. If the file holds multiple components, append a JSON Pointer fragment:

```yaml
$ref: '../common.yaml#/components/schemas/Address'
```

Rules when splitting files:

- Compute relative paths from the file containing the `$ref`, not always from the root file.
- Keep directory layout and filenames stable so CI, IDEs, and documentation tools resolve them consistently.
- Use valid URI/JSON Pointer syntax and check case sensitivity across build environments.
- Avoid HTTP references to mutable resources or resources unavailable in CI builds.
- For specifications distributed standalone, consider bundling external references into a self-contained document.

## 8. Resolving References and Bundling Documents

A `$ref` resolver typically performs these steps:

1. Read the root OpenAPI document.
2. Locate every `$ref` field in positions permitted by OpenAPI.
3. Parse the URI to determine the document and fragment.
4. Load or read the target document, then apply the JSON Pointer to retrieve the referenced object.
5. Verify that the target object has the right type for the usage context, e.g., a Schema Object in a schema position.
6. Continue processing nested references and report errors if resolution fails.

Distinguish three common operations:

| Operation | Outcome |
|---|---|
| **Resolve** | Locate and load referenced objects so a tool can understand the document. Depending on the tool, external references may be converted into internal references. |
| **Bundle** | Combine multiple files into one distributable document, typically turning external references into local references within the same document. |
| **Dereference** | Replace references with the target object's contents at each usage site. The output may repeat the same schema many times and struggle with recursive references. |

Exact names and outputs vary across tools. When choosing a tool, check explicitly whether it keeps `$ref`, converts external `$ref` into local references, or inlines everything.

### 8.1. Resolving Example with Swagger Parser

Swagger Parser can read OpenAPI JSON/YAML and enable resolve mode to handle relative or remote references. Java example:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.parser.OpenAPIV3Parser;
import io.swagger.v3.parser.core.models.ParseOptions;
import io.swagger.v3.parser.core.models.SwaggerParseResult;

ParseOptions options = new ParseOptions();
options.setResolve(true);

SwaggerParseResult result = new OpenAPIV3Parser().readLocation(
        "openapi/openapi.yaml",
        null,
        options
);

if (result.getMessages() != null && !result.getMessages().isEmpty()) {
    result.getMessages().forEach(System.err::println);
}

OpenAPI openAPI = result.getOpenAPI();
if (openAPI == null) {
    throw new IllegalStateException("Unable to read or resolve OpenAPI");
}
```

With `resolve=true`, the parser attempts to read relative or remote references, adds resolved objects to `components`, and replaces external references with local references. Inspect the messages returned by the parser; do not treat receiving a non-null `OpenAPI` object as proof that all warnings are harmless.

Resolving references and validating are related yet distinct steps. After resolving, still run a validator compatible with the target OpenAPI version and verify API business rules.

### 8.2. When Should You Bundle?

Bundling is useful when sending a single OpenAPI file to partners, uploading to an API portal, or feeding a code generator that does not support multi-file specs. A bundled document can still preserve local `$ref` pointers to reuse schemas within a single file.

Full dereferencing is rarely necessary. Keeping local references usually makes the document easier to read, avoids copying the same schema into multiple places, and preserves reusable structures.

## 9. Recursive References and Cycles

A schema can reference itself or reference across several other schemas. This is a valid pattern when actual data has a recursive structure.

Example of a category containing a list of subcategories:

```yaml
components:
  schemas:
    Category:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        children:
          type: array
          items:
            $ref: '#/components/schemas/Category'
```

`Category` references `Category` through `children.items`. This models a tree of arbitrary depth. Tooling must recognize this as a recursive reference rather than looping infinitely while expanding the schema.

A chain of references can also form an indirect cycle: `A` references `B`, `B` references `C`, and `C` references `A`. Verify whether the data model genuinely permits that relationship or whether it resulted from an accidental definition.

Errors commonly surface when a tool attempts to dereference recursion into an unbounded inline structure. In such cases, preserve `$ref` and use validators/generators that support recursive schemas. Never remove a reference just to silence an older tool if doing so distorts the data model.

## 10. Common `$ref` Resolution Errors

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| `Could not resolve reference` | Target file does not exist, wrong URI, or resource is unreachable | Check relative paths, base URI, and access permissions. |
| Fragment not found | JSON Pointer has wrong key, wrong nesting level, or unescaped `~`/`/` | Compare against actual JSON/YAML structure and fix the pointer. |
| Schema not recognized at reference site | `$ref` points to a Response Object or Parameter Object instead of a Schema Object | Point to the right component type for the context. |
| Works locally but fails in CI | Referenced file uncommitted, casing differs, or CI runs from a different directory | Verify files in repository and paths relative to the `$ref`-containing file. |
| Swagger UI fails to load document | UI or browser cannot reach external URI, CORS issue, or wrong root doc path | Check network requests, permissions, and try resolving with a parser in the build. |
| Bundling generates suffixed component names | Multiple files contain components with the same name | Rename components to be unique or review tool-generated mappings. |
| Dereferencing loops infinitely or produces huge files | Schema contains recursive references or is shared in many places | Keep local `$ref`, use cycle-aware tools, and avoid full inlining. |

Several practices help avoid errors:

- Component names should be simple, stable, and unique within their scope.
- Never use local developer machine paths in `$ref`; use repository-relative paths or URIs reachable across all environments.
- Do not reference a component solely by matching name; verify the exact file, fragment, and object type.
- When a file is renamed or moved, search all dependent `$ref` pointers and re-run the resolver.
- Integrate OpenAPI verification into CI so broken references are caught before release.

## 11. Workflow for `$ref` in a Spring Boot Project

When using springdoc to generate documentation and needing reuse or file splitting, apply this workflow:

1. **Generate the base document**: run the application and fetch `/v3/api-docs` or `/v3/api-docs.yaml` as configured.
2. **Check the OpenAPI version**: read the `openapi` field at the top; verify consumers support that version.
3. **Inspect components**: examine `components.schemas`, `responses`, `parameters`, and shared sections created by springdoc.
4. **Verify local references**: confirm every `#/components/...` points to an existing component of the right type.
5. **Split files if needed**: move definitions into separate files, updating relative URIs and fragments for the new layout.
6. **Resolve and validate**: use a parser/validator to read the whole document and catch broken references, invalid structures, or incompatibilities.
7. **Bundle if single-file distribution is needed**: inspect local references after bundling and confirm no developer-machine paths remain.
8. **Test with consumers**: verify Swagger UI, SDK generators, API portals, or actual integration tools against the release file.

In the CI pipeline, archive the resolved or bundled OpenAPI spec as a versioned artifact and diff contract changes against the previous release. If the document includes remote URIs, ensure those resources are managed and reliably accessible in CI.

## 12. Reference Review Checklist

- [ ] Every `$ref` is a valid URI.
- [ ] Relative URIs are computed from the exact document containing the reference.
- [ ] JSON Pointer fragments point to the exact location in JSON/YAML.
- [ ] Keys containing `~` or `/` are escaped as `~0` or `~1`.
- [ ] Target components exist and match the expected object type for the context.
- [ ] The document follows the `$ref` rules of OpenAPI 3.0 or 3.1 as appropriate.
- [ ] Components inside `components` are referenced from their usage sites.
- [ ] Recursive references are intentional and supported by verification tools.
- [ ] All external files are committed to the repository or hosted at reliably accessible URIs.
- [ ] Resolver and validator pass in CI.
- [ ] Release bundle files have no dependency on local developer paths.

## 13. References

- [OpenAPI Specification 3.1.2 – Reference Object](https://spec.openapis.org/oas/v3.1.2.html#reference-object)
- [OpenAPI Specification 3.0.4 – Reference Object](https://spec.openapis.org/oas/v3.0.4.html#reference-object)
- [RFC 6901 – JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901)
- [OpenAPI Initiative – Referencing overview](https://learn.openapis.org/referencing/overview.html)
- [Swagger Parser – Resolve external and relative references](https://github.com/swagger-api/swagger-parser)
- [springdoc-openapi FAQ – Reusable component schemas](https://springdoc.org/faq.html)
- [springdoc-openapi configuration properties](https://springdoc.org/properties.html)

`$ref` is the mechanism connecting parts of an OpenAPI contract. By specifying valid URIs, accurate JSON Pointers, and distinguishing OpenAPI 3.0 from 3.1 rules, you can reuse schemas safely, split documentation across files, and package reliable specifications for downstream tools.
