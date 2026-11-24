# Verifying Every `$ref` Reference Resolves Cleanly

In OpenAPI, `$ref` lets you reuse schemas, parameters, responses, request bodies, and many other components without duplicating definitions everywhere. A specification can be split into multiple files for organization, or kept in a single file with internal references. Either way, every reference must point to a readable resource and a location that actually exists.

An OpenAPI document may parse successfully yet still contain broken references. For example, an `Order` schema references `#/components/schemas/Customer` after `Customer` was renamed; a root file moves to another directory so relative paths break; or a JSON Pointer contains an unescaped slash. These defects often surface only when Swagger UI, code generators, validators, or API catalogs attempt to load and consume the referenced schema.

Verifying `$ref` resolution must therefore be a dedicated step in contract testing. This lesson covers identifying references, resolving URIs and JSON Pointers, distinguishing OpenAPI 3.0/3.1 rules, recognizing valid circular references, validating targets, and integrating checks into CI.

## 1. What Problem Does `$ref` Solve?

References let you define a component once and reuse it across multiple locations. For instance, many operations return a standard error:

~~~yaml
components:
  schemas:
    ApiError:
      type: object
      properties:
        code:
          type: string
        message:
          type: string
      required:
        - code
        - message
  responses:
    CommonError:
      description: Request cannot be processed.
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
~~~

An operation can reuse that response:

~~~yaml
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/CommonError'
~~~

When multiple operations share `ApiError`, editing the schema in one place propagates across all references. This keeps documentation consistent and reduces duplication.

In return, every `$ref` creates a dependency. If a target is deleted, renamed, moved, or unreachable, downstream tools may fail to process the entire document properly.

## 2. Where Can `$ref` Appear?

Not every `$ref` points to a Schema Object. OpenAPI supports reusing several kinds of components:

| Location | Expected Target |
|---|---|
| Schema Object | A schema |
| Parameter Object | A parameter |
| Request Body Object | A request body |
| Response Object | A response |
| Header Object | A header |
| Example Object | An example |
| Link Object | A link |
| Callback Object | A callback |
| Path Item Object | A path item, in OpenAPI versions supporting this component |

Schema reference example:

~~~yaml
schema:
  $ref: '#/components/schemas/Order'
~~~

Parameter reference example:

~~~yaml
parameters:
  - $ref: '#/components/parameters/OrderId'
~~~

Request body reference example:

~~~yaml
requestBody:
  $ref: '#/components/requestBodies/CreateOrder'
~~~

A reference can resolve cleanly as a URI yet still have the wrong type. For example, a `responses` entry expects a Response Object but points to a Schema Object. Therefore, checks must verify both that the target exists and that its object type fits the usage site.

## 3. Internal References Within the Same Document

Internal references typically start with `#` and use a JSON Pointer to locate a node inside the current document:

~~~yaml
components:
  schemas:
    Order:
      type: object
      properties:
        id:
          type: string
        customer:
          $ref: '#/components/schemas/Customer'
    Customer:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
~~~

The reference:

~~~yaml
$ref: '#/components/schemas/Customer'
~~~

is evaluated step by step:

1. `#` indicates a fragment of the current document.
2. `/` begins the JSON Pointer.
3. `components` selects the root `components` object.
4. `schemas` selects the schema map.
5. `Customer` selects the schema named `Customer`.

If any level is missing or a name does not match exactly, the reference fails to resolve. Keys in JSON Pointer are case-sensitive.

## 4. JSON Pointer and Escaping Key Names

The fragment of an internal reference usually contains a JSON Pointer. Within each JSON Pointer token, two characters must be escaped:

| Character in Key | Escaped Form |
|---|---|
| ~ | ~0 |
| / | ~1 |

Example component whose name contains a slash:

~~~yaml
components:
  schemas:
    Order/Line:
      type: object
      properties:
        sku:
          type: string
~~~

Correct reference:

~~~yaml
$ref: '#/components/schemas/Order~1Line'
~~~

If a key contains a tilde:

~~~yaml
components:
  schemas:
    Version~Legacy:
      type: string
~~~

the reference must use:

~~~yaml
$ref: '#/components/schemas/Version~0Legacy'
~~~

When constructing a token, escape `~` first and then `/`. Never leave an unescaped slash inside a key name; JSON Pointer interprets it as a hierarchy separator.

## 5. URI Fragment Escaping and JSON Pointer Are Two Separate Layers

A JSON Pointer inside a URI fragment is also subject to URI encoding rules. For names containing spaces or Unicode characters, the fragment may require percent-encoding in addition to JSON Pointer escaping.

Example key with a space:

~~~yaml
components:
  schemas:
    Order Summary:
      type: object
~~~

The reference can use a percent-encoded fragment:

~~~yaml
$ref: '#/components/schemas/Order%20Summary'
~~~

Keep the distinction clear:

- JSON Pointer escaping handles `~` and `/` inside a token.
- Percent-encoding handles characters requiring encoding in a URI fragment.

Do not blindly replace every `/` in the entire URI with `~1`. Only `/` characters belonging to a JSON Pointer token name need escaping to `~1`. Slashes separating pointer levels must remain unchanged.

## 6. Referencing Another File

An OpenAPI document can split schemas or paths across multiple files. Example layout:

~~~text
api/
├── openapi.yaml
├── schemas/
│   ├── order.yaml
│   └── customer.yaml
└── responses/
    └── errors.yaml
~~~

The root document references schemas in external files:

~~~yaml
components:
  schemas:
    Order:
      $ref: './schemas/order.yaml'
    Customer:
      $ref: './schemas/customer.yaml'
  responses:
    CommonError:
      $ref: './responses/errors.yaml#/CommonError'
~~~

If `order.yaml` holds a root schema:

~~~yaml
type: object
properties:
  id:
    type: string
  customer:
    $ref: './customer.yaml'
~~~

then `customer.yaml` resolves relative to the base URI of the schema resource/file containing the reference. When organizing multiple files, keep relative paths consistent.

Loading a file successfully does not mean every reference inside that file is valid. The resolver must traverse nested references until the entire reference graph has been verified.

## 7. Absolute and Relative References

A URI-reference can take these forms:

| Form | Example | Resolution |
|---|---|---|
| Internal fragment | `#/components/schemas/Order` | Within current document |
| Relative file | `./schemas/order.yaml` | Relative to base URI |
| Parent-directory file | `../common/error.yaml` | Moves up one level from base URI |
| Absolute URL | `https://schemas.example.com/order.yaml` | Fetched from absolute URI |
| File URI | `file:///workspace/api/order.yaml` | Read from permitted file location |

For relative references, the resolver needs the base URI of the document holding the reference. If the root document is read from `/workspace/api/openapi.yaml`, `./schemas/order.yaml` typically resolves from `/workspace/api`.

Never use server URLs from the OpenAPI `servers` field as the base URI for `$ref`. Server URLs describe where to invoke the API, not where OpenAPI documents or schema resources live.

## 8. Base URI and the Effect of `$id` in OpenAPI 3.1

OpenAPI 3.1 adopts JSON Schema semantics for Schema Objects. A schema resource can declare `$id` to identify the resource and establish the base URI used when resolving relative references inside that resource.

Example:

~~~yaml
components:
  schemas:
    Customer:
      $id: https://schemas.example.com/customer
      type: object
      properties:
        address:
          $ref: ./address.yaml
~~~

For a schema resource with `$id` like this example, the relative reference `./address.yaml` resolves against the schema resource's base URI—not necessarily against the physical location of the root file.

This matters when sharing 3.1 schemas across multiple documents. Moving a file while keeping `$id` unchanged can keep URI resolution anchored to that identifier. Conversely, changing `$id` can alter the target of every relative reference inside the schema.

OpenAPI 3.0 lacks the full JSON Schema resource and `$id` model of OAS 3.1. When checking 3.0 documents, follow 3.0 reference rules and do not assume Draft 2020-12 `$id` semantics.

## 9. Deep JSON Pointer References

You do not always have to reference a top-level component. You can point to a specific subschema:

~~~yaml
$ref: '#/components/schemas/Order/properties/customer'
~~~

The pointer traverses:

1. `components`
2. `schemas`
3. `Order`
4. `properties`
5. `customer`

The target type must suit the usage site. If `requestBody.content.application/json.schema` references the `customer` subschema, that target must be a valid Schema Object.

Deep references increase sensitivity to structural edits. Renaming the `customer` property to `buyer` breaks the deep pointer even though `Order` still exists. For widely reused elements, prefer creating a dedicated component schema rather than deep-pointing into internal properties.

## 10. Referencing Paths Containing Slashes

When referencing a Path Item under `paths`, the `/` characters of the URL are part of the key name and must be escaped as `~1` in JSON Pointer.

Example path:

~~~yaml
paths:
  /orders/{id}:
    get:
      responses:
        '200':
          description: Order found.
~~~

If you need to reference this Path Item where Path Item references are supported, the pointer must use:

~~~yaml
$ref: '#/paths/~1orders~1{id}'
~~~

JSON Pointer hierarchy slashes remain separators, while slashes inside the path key become `~1`. Forgetting to escape causes the resolver to look for nested `orders` and `{id}` keys instead of the single `/orders/{id}` key.

## 11. Distinguishing Reference Object vs. Schema Object with `$ref`

In OpenAPI, `$ref` appears in at least two distinct contexts:

- A Reference Object replaces a referenceable OpenAPI object such as a parameter or response.
- A Schema Object uses `$ref` under JSON Schema semantics in OpenAPI 3.1.

This distinction affects sibling fields placed alongside `$ref`.

In OpenAPI 3.0, a Reference Object defines only `$ref`; extra properties are outside the supported model and are typically ignored. In OpenAPI 3.1, a Reference Object supports `summary` and `description`; other siblings are not automatically merged into the target object.

Inside an OpenAPI 3.1 Schema Object, `$ref` follows JSON Schema 2020-12, so sibling keywords continue to apply:

~~~yaml
schema:
  $ref: '#/components/schemas/Order'
  description: Order in search results.
~~~

Do not apply Reference Object rules to all Schema Objects or vice versa. When checking siblings, know the OpenAPI version and the exact location of `$ref`.

## 12. Verifying Target Existence

Every reference should be checked through a clear sequence of steps:

1. Read the `$ref` value as a URI-reference.
2. Determine the current document/resource and base URI.
3. Resolve the URI portion to the target resource.
4. Load the resource if it is an external document.
5. Resolve the fragment, JSON Pointer, or anchor.
6. Confirm the target exists.
7. Confirm the target has the right object type for the usage site.
8. Recursively check any `$ref` entries inside the target.

Example:

~~~yaml
requestBody:
  $ref: '#/components/requestBodies/CreateOrder'
~~~

If the pointer finds `components.requestBodies.CreateOrder` yet the actual value is a string rather than a Request Body Object, the reference resolved to a node but the document is still invalid.

Checking existence and checking structure are separate steps. An OpenAPI validator should perform both to the extent supported by its version.

## 13. Anchors and Non-JSON-Pointer References

In JSON Schema 2020-12, a schema resource can declare an anchor:

~~~yaml
$id: https://schemas.example.com/order
$anchor: orderIdentity
type: object
properties:
  id:
    type: string
~~~

A reference can use the anchor fragment:

~~~yaml
$ref: 'https://schemas.example.com/order#orderIdentity'
~~~

When anchors are used, the resolver must locate the anchor within the schema resource according to the active dialect and JSON Schema rules. Never assume every fragment is a JSON Pointer starting with `/`.

Advanced features such as `$dynamicAnchor` and `$dynamicRef` introduce dynamic scoping for recursive or extensible schemas. A simple JSON Pointer-only tool may not suffice to fully verify those references.

## 14. Circular References: Not Always an Error

A reference graph can contain valid cycles. For example, a `Node` schema can contain child `Node`s:

~~~yaml
components:
  schemas:
    Node:
      type: object
      properties:
        value:
          type: string
        children:
          type: array
          items:
            $ref: '#/components/schemas/Node'
~~~

This is a valid recursive schema in many cases. If a validator flags every cycle as an error, it can reject legitimate tree or graph models.

Distinguish clearly between:

- **Unresolved reference:** the referenced resource or location cannot be found. This is an error.
- **Circular reference:** a reference leads back to a previously visited schema. Often valid, especially for recursive schemas.
- **Unsupported cycle:** a downstream tool cannot process a cycle during a specific operation such as code generation or dereferencing. This is a tool limitation, not automatic proof that the OpenAPI document is invalid.

A resolver should track visited URIs/resources to avoid infinite recursion. Upon encountering a node currently in progress, record the cycle and apply the appropriate policy instead of reporting it as unresolved.

## 15. Distinguishing Resolve, Validate, and Dereference

These operations are not identical:

| Operation | Purpose |
|---|---|
| Resolve | Locate the resource and target pointed to by `$ref` |
| Validate | Check whether the document and schemas comply with specification rules |
| Dereference | Replace references with target contents in an expanded structure |
| Bundle | Combine related documents into a single distributable output, often preserving some internal `$ref`s |

A reference can resolve cleanly while the target has the wrong type or violates a schema rule. In that case, resolution succeeds while validation fails.

Full dereferencing can produce cyclic object graphs or duplicate identical schemas multiple times. Some tools cannot serialize a fully dereferenced recursive graph into finite JSON/YAML. Bundling is usually preferable when producing a single distributable file while preserving internal references.

Never treat a successful bundle as sole proof that the entire contract is valid. Always validate the document after bundling.

## 16. Organizing Multiple Files for Maintainability

One layout for multi-file specifications:

~~~text
openapi/
├── openapi.yaml
├── paths/
│   ├── orders.yaml
│   └── customers.yaml
├── schemas/
│   ├── order.yaml
│   ├── order-line.yaml
│   └── customer.yaml
└── responses/
    └── api-error.yaml
~~~

The root document can reference Path Items or components in the manner supported by your OpenAPI version. Each file should have a clear responsibility and predictable relative paths.

Organizational guidelines:

- Keep filenames stable; avoid arbitrary renames.
- Follow a consistent convention for `paths`, `schemas`, and `responses` directories.
- Avoid creating duplicate copies of the same schema under different names.
- Minimize unnecessary cross-file circular references.
- Clearly designate the root document used for linting, bundling, and publishing.
- Keep all referenced files in source control or the corresponding artifact.

If you publish only the root `openapi.yaml` without publishing its dependent files, clients cannot resolve relative `$ref`s after downloading the artifact.

## 17. Checking with Lint and Bundle Tools

Use an OpenAPI-aware tool rather than grepping for `$ref` strings. A parser distinguishes real references from payload examples or text descriptions that happen to contain a `$ref` key.

Example with Redocly CLI:

~~~bash
npx @redocly/cli lint openapi/openapi.yaml
~~~

The `lint` command analyzes the document and reports issues based on the CLI's parser, ruleset, and version support.

You can bundle into a single file to verify all references resolve:

~~~bash
npx @redocly/cli bundle openapi/openapi.yaml -o target/openapi-bundled.yaml
~~~

After bundling, lint the bundled artifact again:

~~~bash
npx @redocly/cli lint target/openapi-bundled.yaml
~~~

Pin the CLI version in CI, such as via a package lockfile or your project's version manager. Avoid pulling unpinned versions per build because resolver behavior and rulesets can change.

If you use another tool, verify its support for OpenAPI 3.0 vs. 3.1, JSON Schema dialects, external file refs, URI anchors, and recursive refs.

## 18. Verifying OpenAPI Files Generated by Springdoc

With springdoc-openapi, runtime documentation is usually retrieved from an endpoint like `/v3/api-docs` or exported via a Maven plugin during build. Validate the exact final artifact that CI will consume or publish.

Recommended workflow:

1. Start the application with a contract-testing profile.
2. Fetch OpenAPI JSON from the endpoint or exported artifact.
3. Save it to the build directory.
4. Run a parser/linter supporting the document's OpenAPI version.
5. Check all internal `$ref` entries.
6. If external refs exist, run the resolver from the proper directory and base URI.
7. Bundle into a distributable artifact if required.
8. Re-validate the bundled file.

For example, if a Maven plugin outputs:

~~~text
target/openapi/openapi.json
~~~

then validation commands must target that exact file. Do not lint only a stale source file under `src` when the published contract is Springdoc's runtime output.

When Springdoc generates internal schemas under `components.schemas`, confirm every `#/components/schemas/...` reference finds its target. If an `OpenApiCustomizer` introduces `$ref` pointers to external files, ensure those files ship in the artifact and the resolver uses the proper base URI.

## 19. Automated Verification in CI

Reference verification can run right after the export step in your pipeline:

~~~text
Start Spring Boot
      |
      v
Fetch /v3/api-docs
      |
      v
Save OpenAPI artifact
      |
      v
Parse and lint document
      |
      v
Resolve all local and external $ref
      |
      v
Bundle if distribution requires it
      |
      v
Validate bundled document
      |
      v
Publish artifact
~~~

Example script:

~~~bash
mvn clean verify
npx @redocly/cli lint target/openapi/openapi.json
npx @redocly/cli bundle target/openapi/openapi.json -o target/openapi/bundled.yaml
npx @redocly/cli lint target/openapi/bundled.yaml
~~~

These commands assume Maven generates `target/openapi/openapi.json` and Redocly CLI is installed in the build environment. Adjust paths to match your actual plugin configuration.

If the document contains relative external refs, ensure referenced files sit at the proper relative locations with respect to the root document. Do not copy only the root file into a temp directory and run lint without copying its dependencies.

## 20. Verifying Target Type and Usage Site

When validating `$ref`, beyond confirming the target exists, verify it is used in a valid context:

~~~yaml
paths:
  /orders:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateOrder'
      responses:
        '201':
          $ref: '#/components/responses/OrderCreated'
components:
  requestBodies:
    CreateOrder:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateOrder'
  responses:
    OrderCreated:
      description: Order created.
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Order'
  schemas:
    CreateOrder:
      type: object
    Order:
      type: object
~~~

In this example:

- `requestBody` points to a Request Body Object.
- The `201` response points to a Response Object.
- `schema` inside `content` points to a Schema Object.

If `CreateOrder` were mistakenly referenced directly as a schema under `requestBody`, the site would become structurally invalid. A resolver that only checks URI existence might miss this type of error; an OpenAPI validator is required.

## 21. Catching Broken References After Renames or Moves

The following edits commonly break `$ref` entries:

- Renaming a component under `components.schemas` while forgetting to update references.
- Moving a schema file to another folder while keeping the old relative URI.
- Renaming a property referenced by a deep JSON Pointer.
- Changing filename or directory casing on Linux environments.
- Changing `$id`, shifting a schema resource's base URI.
- Bundling a document without updating dependent paths.
- Deleting a component still used by an operation or another component.

Some bugs do not reproduce on Windows because its filesystem is typically case-insensitive unlike Linux. CI running on Linux will expose casing mismatches. Always verify references on the same OS family or container image used for release.

When refactoring schema names, use reference search in your IDE or an OpenAPI-aware tool and run the linter immediately after the edit. Never update only a string in the root file when references may reside deep inside included files.

## 22. Hardening Resolvers Handling External Refs

External `$ref` entries can point to URLs or local filesystem paths. Automatically fetching arbitrary URIs from untrusted specifications introduces risks:

- SSRF: CI is tricked into querying internal services via a document-supplied URL.
- Path traversal: a file reference attempts to escape the allowed specification directory.
- Data disclosure: the resolver reads unrelated config files or secrets.
- Supply-chain risk: an external schema changes without review.
- Build instability: an external schema server becomes temporarily unreachable.

For specifications from pull requests or untrusted sources:

1. Restrict the resolver to the allowed specification directory.
2. Allowlist permitted hosts/domains for network fetches.
3. Block access to metadata services and sensitive internal networks.
4. Enforce limits on file size, fetch timeout, and URI count.
5. Disallow credentials or tokens inside URIs.
6. Pin or vendor external schemas into the repository when reproducibility is needed.
7. Record the source and checksum of fetched schemas.

Do not disable network protections just to make an external ref resolve. If a schema is an official dependency, manage it like a versioned dependency with clear provenance.

## 23. External Refs and Build Reproducibility

If every build downloads a schema from a mutable URL, the same commit can yield different contracts on different days.

For reproducible builds:

- Reference a specific version or release of the external schema.
- Prefer immutable URLs or commit a reviewed copy into the repository.
- Record checksums to detect unexpected content changes.
- Cache external dependencies under an explicit TTL policy.
- Log the resolver version and document sources.
- Fail explicitly when a source is unreachable rather than silently falling back to an untracked stale copy.

If using `latest` URLs or a `main` branch, treat them as time-varying dependencies. That may suit continuously updated docs, but not deterministic artifact releases.

## 24. Common Pitfalls

| Error | Cause | Resolution |
|---|---|---|
| Unresolved reference | Target does not exist | Verify component name, file, and fragment |
| 404 fetching external ref | Wrong URL or missing file on server | Verify URI and access permissions |
| Relative ref works locally but fails in CI | Different base URI or directory layout | Preserve file layout and invoke resolver from root document |
| JSON Pointer fails on key containing `/` | Slash was not escaped as `~1` | Escape tokens per JSON Pointer rules |
| Key containing `~` is not found | `~` was not escaped as `~0` | Escape `~` before escaping `/` |
| Case mismatch in ref | Key or filename casing differs | Align casing and verify on Linux |
| Ref resolves yet validator fails | Wrong target type or invalid structure | Check object type expected at usage site |
| Ref siblings ignored | Confusing Reference Object with Schema Object | Check OAS 3.0/3.1 rules and `$ref` location |
| Validator flags circular reference | Tool lacks support or policy blocks cycles | Distinguish valid recursive schemas from broken refs |
| Bundle succeeds yet document is invalid | Validation was skipped after bundling | Lint/validate the final bundled artifact |
| Root file published without child files | External relative refs were not packaged | Bundle or distribute the entire dependent file tree |
| Resolver accesses unexpected external hosts | External URIs are unrestricted | Allowlist domains and sandbox network access |
| Flaky builds | External schema URL mutates or is unstable | Pin versions, vendor, or verify checksums |
| Grepping for `$ref` | Strings in examples/descriptions cause false positives | Use an OpenAPI parser to traverse structure |

## 25. Checklist Before Accepting an OpenAPI Contract

Before releasing a specification:

1. Identify the root OpenAPI document and OAS version.
2. Parse YAML/JSON with a parser supporting that version.
3. Traverse every location that can hold a Reference Object or a Schema Object with `$ref`.
4. Resolve relative URIs against the proper base URI.
5. Apply `$id` and dialect rules when handling OAS 3.1 schema resources.
6. Decode fragments, JSON Pointers, and anchors properly.
7. Verify each target exists.
8. Verify each target has the expected object type.
9. Recursively traverse nested references.
10. Permit valid cycles while catching unresolved references.
11. Restrict external URIs to permitted network/file boundaries.
12. Bundle if a single self-contained file must be distributed.
13. Re-validate the artifact after bundling.
14. Test with Swagger UI, code generators, or actual consumers if used downstream.
15. Archive resolver results and versions in CI logs/artifacts.

## 26. Key Takeaways

- `$ref` enables reuse of schemas and OpenAPI components.
- Internal references typically use JSON Pointers starting with `#/`.
- `~` in a token escapes to `~0`; `/` in a token name escapes to `~1`.
- URI fragments may also require percent-encoding.
- Relative refs resolve against the document/resource base URI; OAS 3.1 also accounts for schema resource `$id`.
- Do not use `servers` URLs as the base URI for `$ref`.
- Verify both target existence and object type.
- Distinguish Reference Objects from Schema Objects with `$ref`, especially regarding siblings in OAS 3.0 and 3.1.
- Anchors and dynamic keywords require a resolver that understands the active JSON Schema dialect.
- Circular schemas can be valid; unresolved references always require fixing.
- Resolve, validate, bundle, and dereference are distinct operations.
- Use an OpenAPI parser/linter instead of string grep to verify refs.
- Restrict external resolvers to prevent SSRF, path traversal, and unstable dependencies.
- Validate the final Springdoc-generated artifact, not merely source stubs.

To confirm every `$ref` reference resolves cleanly, verify the generated document with a resolver that understands your OpenAPI version and JSON Schema dialect. Validate URIs, fragments, JSON Pointers, target types, and nested references while distinguishing valid schema cycles from missing targets. Finally, lint and validate the output artifact in CI while constraining file and network access for external refs.
