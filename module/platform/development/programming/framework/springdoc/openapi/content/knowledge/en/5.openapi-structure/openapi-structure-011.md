# x-* Extensions and Their Intended Usage

## 1. Why Does OpenAPI Have Extensions?

OpenAPI defines a common structure for describing APIs: overview info, servers, endpoints, requests, responses, schemas, and security. However, each organization may need extra metadata to support internal workflows. Examples:

- Marking endpoints as belonging to an internal or public group.
- Recording the owning team, system code, or business documentation path.
- Supplying code samples, rate-limit metadata, or display labels for a developer portal.
- Instructing an SDK generator, API gateway, or governance platform to process the document per custom conventions.

If you add an arbitrary property outside the standard structure, OpenAPI tools may treat the document as invalid. To extend the document while preserving a compatible structure, OpenAPI defines **Specification Extensions**, commonly called **vendor extensions** or **x-*** extensions.

An extension is a metadata field whose name starts with the **x-** prefix. Its value can be a string, number, boolean, array, or JSON/YAML object. Tools that understand the extension can use this data for custom behavior; tools that do not understand it can normally ignore the extension and keep reading the standard OpenAPI fields.

Extensions let organizations add information without altering the standard schema or inventing a proprietary OpenAPI fork. However, an extension is only meaningful when the document producer and consumer agree on how to interpret it.

## 2. Basic Rules of x-* Extensions

An extension should follow these principles:

1. The field name must start with **x-**.
2. Extension names are case-sensitive; standardize on one naming style, typically lowercase with hyphens.
3. Values can be any valid JSON data type: string, number, boolean, array, object, or null if appropriate for consumers.
4. Extensions should only be placed on OpenAPI objects that allow specification extensions.
5. Extensions do not alter the meaning of standard fields unless a specific tool defines additional interpretation rules.
6. Documentation readers should know which extensions are custom conventions and which tools support them.

Example of a simple extension:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  version: "1.0.0"
  x-api-owner: platform-team
paths: {}
~~~

In the example, **x-api-owner** is custom metadata indicating the team that owns the API. OpenAPI does not predefine the meaning of this name. An internal API portal may read that field to associate documentation with the responsible team; standard Swagger UI may not display it.

You must not place an arbitrary field name such as **owner** in a location OpenAPI does not define. Using the `x-` prefix separates extension metadata from specification fields.

## 3. Where Can Extensions Appear?

OpenAPI permits specification extensions on many objects in a document. Common locations include:

| Location | Example Purpose |
|---|---|
| OpenAPI Object (document level) | System code, owning team, or pipeline metadata |
| Info Object | Logo, support group, or supplementary doc links |
| Server Object | Environment- or gateway-specific metadata |
| Tag Object | Functional group, categorization, or developer portal metadata |
| Path Item and Operation Object | Endpoint-owning team, business code, code samples |
| Parameter and Header Object | Display hints or client generator metadata |
| Request Body and Response Object | Custom processing rules or example links |
| Schema Object | Display labels, UI widgets, or model generator metadata |
| Security Scheme Object | Extra integration details for the authentication system |

This list helps illustrate common places; during implementation, check the exact OpenAPI version and specific object type to confirm extensions are allowed at that location.

Operation-level extension example:

~~~yaml
paths:
  /products:
    get:
      summary: Search products
      operationId: searchProducts
      x-internal-owner:
        team: catalog
        contact: platform-api
      responses:
        "200":
          description: Success
~~~

The **x-internal-owner** extension sits inside the Operation Object and therefore applies only to `GET /products`. Another operation can have a different owning team or metadata.

## 4. Value Types of Extensions

Extensions are not restricted to strings. Choose the data structure suited to consumer needs.

### 4.1. Primitive Values

~~~yaml
x-api-owner: platform-team
x-internal-only: true
x-priority: 2
~~~

These values fit short metadata such as a team name, boolean flag, or priority level.

### 4.2. Object Values

~~~yaml
x-governance:
  owner: catalog-team
  data-classification: internal
  review-cycle: quarterly
~~~

An object fits when a group of metadata has multiple related attributes. Nested properties do not need an `x-` prefix because they live inside the value of the `x-governance` extension; however, the internal schema of the object still needs to be clearly defined.

### 4.3. Array Values

~~~yaml
x-code-samples:
  - lang: curl
    label: Call API with curl
    source: |
      curl -X GET https://api.example.com/products
  - lang: javascript
    label: Call API with fetch
    source: |
      fetch("https://api.example.com/products")
~~~

Arrays fit lists of examples, labels, or ordered configuration items. Consuming tools need to know the name and type of each property inside array elements.

### 4.4. The Same Extension in JSON

OpenAPI JSON and YAML represent the same data model. Example:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Shop API",
    "version": "1.0.0"
  },
  "x-api-owner": "platform-team",
  "paths": {}
}
~~~

When converting JSON to YAML or vice versa, extensions should preserve their exact name, type, and value structure. Avoid serializing an object as a JSON string simply because an export tool does not understand the extension.

## 5. Distinguishing Extensions from Standard Fields and Regular Metadata

Not every extra piece of information needs an extension. OpenAPI already provides many standard fields for describing APIs:

- **info.description** describes the whole API.
- **operation.description** describes a single operation.
- **externalDocs** links to external documentation.
- **tags** groups endpoints.
- **deprecated** marks an operation or parameter as deprecated.
- **security** and **securitySchemes** describe security requirements.

Prefer standard fields whenever they already satisfy the need. For instance, describing which capability an endpoint belongs to should use `tags`; there is no need to invent `x-feature-group` if `tags` already expresses the exact meaning.

Create an extension only when metadata is needed that the specification does not provide or when an integrating tool requires a custom convention. Creating too many extensions that duplicate standard fields makes the document harder to read and can introduce two conflicting sources of truth.

An extension is not a way to declare a new field in a request or response payload. If clients must send a business data field, describe that field in the Schema Object. Use an extension on a Schema Object only to attach metadata about the schema itself.

## 6. Examples of Extensions for Documentation Tools

Some documentation tools define their own extensions to control rendering. For example, ReDoc supports the **x-logo** extension in the Info Object to display a logo:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  version: "1.0.0"
  x-logo:
    url: https://example.com/assets/shop-api-logo.png
    altText: Shop API
paths: {}
~~~

This extension is meaningful to tools supporting `x-logo`. Another OpenAPI reader can ignore it and still render the documentation using `title`, `description`, and `paths`.

Another example is the `x-codeSamples` extension supported by some documentation platforms to present request examples in multiple languages. The exact structure must follow the consuming tool's documentation; there is no single mandatory `x-codeSamples` schema across all OpenAPI tools.

When using third-party extensions, document:

- Exact name and data type of the extension.
- Tool versions that support the extension.
- Which OpenAPI object the extension is placed on.
- Expected behavior when a tool does not recognize the extension.

Do not assume an extension from one tool behaves identically across Swagger UI, ReDoc, API gateways, or other SDK generators.

## 7. Declaring Extensions with Springdoc OpenAPI

Springdoc uses Swagger/OpenAPI annotations to describe APIs. The **@Extension** and **@ExtensionProperty** annotations allow declaring extension metadata on annotations that support extensions, such as **@Operation** or **@Schema**.

Example attaching metadata to an operation:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping
    @Operation(
        summary = "Search products",
        extensions = {
            @Extension(
                name = "x-internal-owner",
                properties = {
                    @ExtensionProperty(
                        name = "team",
                        value = "catalog"
                    ),
                    @ExtensionProperty(
                        name = "contact",
                        value = "platform-api"
                    )
                }
            )
        }
    )
    public List<ProductResponse> search() {
        return productService.search();
    }
}
~~~

The OpenAPI output may contain a section similar to:

~~~yaml
paths:
  /api/products:
    get:
      summary: Search products
      x-internal-owner:
        team: catalog
        contact: platform-api
      responses:
        "200":
          description: Success
~~~

Here, the extension name is **x-internal-owner**; the `team` and `contact` properties form the extension's object value. The extension name must have the `x-` prefix.

You can declare extensions on a schema when the corresponding annotation supports them:

~~~java
@Schema(
    description = "Product details",
    extensions = {
        @Extension(
            name = "x-ui-hint",
            properties = {
                @ExtensionProperty(
                    name = "component",
                    value = "product-card"
                )
            }
        )
    }
)
public record ProductResponse(
    Long id,
    String name
) {}
~~~

The `x-ui-hint` extension is a custom hint for a UI tool that understands this convention. It does not change the data types or validation of `ProductResponse`.

These annotations are imported from **io.swagger.v3.oas.annotations** and **io.swagger.v3.oas.annotations.extensions**. Attribute names or support may vary by the `swagger-annotations` version used by Springdoc; check the API of your project's exact version before applying.

## 8. Adding Extensions with OpenApiCustomizer

When metadata needs to be produced programmatically, you can use a Springdoc customizer to add extensions to the OpenAPI model.

Example adding a document-level extension:

~~~java
@Configuration
public class OpenApiExtensionConfiguration {

    @Bean
    public OpenApiCustomizer apiOwnerExtension() {
        return openApi ->
            openApi.addExtension("x-api-owner", "platform-team");
    }
}
~~~

The customizer receives the `OpenAPI` model and adds an extension field to the document. This is useful when values come from configuration or must be computed at application startup.

You can add an object instead of a string:

~~~java
Map<String, Object> governance = new LinkedHashMap<>();
governance.put("owner", "catalog-team");
governance.put("classification", "internal");

openApi.addExtension("x-governance", governance);
~~~

The second snippet illustrates the body to place inside a customizer lambda or appropriate configuration method; remember to import `Map` and `LinkedHashMap`. Object values serialize into JSON/YAML objects.

In an application with multiple document groups, verify which groups the customizer applies to. Springdoc provides customizers for different scopes; if the extension must appear in every group, choose the global customizer suited to your version and inspect each group's document endpoint.

Avoid generating the same extension from multiple sources if those sources might overwrite one another. Choose a single place responsible for producing that metadata to prevent inconsistent output.

## 9. Designing Extension Conventions for an Organization

Custom extensions need clear conventions. A good convention should document:

| Item | Question to Answer |
|---|---|
| Name | What is the extension name starting with `x-`? |
| Location | Is it allowed at the document, operation, or schema level? |
| Type | Is the value a string, boolean, object, or array? |
| Meaning | What business meaning does each property carry? |
| Owner | Which team defines and maintains the extension? |
| Consumers | Which tools read and act on the extension? |
| Versioning | How are structural changes to the extension managed? |
| Default | What is the behavior when the extension or a property is absent? |

For example, an organization might define `x-internal-owner` as follows:

~~~yaml
x-internal-owner:
  team: catalog
  contact: platform-api
  visibility: internal
~~~

The accompanying convention should explain that `team` is a centrally managed team code, `contact` is the support channel, and `visibility` governs publishing scope in the internal portal. If a consuming tool uses `visibility` to filter documentation, ensure that metadata is verified before publishing.

Use a meaningful namespace to reduce collision risk with third-party extensions. For instance, an organization can prefix internal extensions with `x-company-` or `x-platform-`. Avoid generic names like `x-config` when multiple teams co-author documentation.

## 10. Impact on Compatibility

One advantage of extensions is that tools unaware of an extension can usually ignore it and continue processing standard OpenAPI parts. This allows the document to work across a variety of tools.

However, do not assume every tool preserves extensions when reading and re-writing a document. Some tools strip unrecognized fields, normalize data types, or support extensions only at certain locations.

When designing extensions:

- Do not put information required to call the API exclusively inside extensions.
- Do not use extensions to replace standard `paths`, methods, `parameters`, `requestBody`, `responses`, or `security`.
- Do not require clients to understand an extension just to make a valid request, unless it is an explicitly published custom contract.
- Check that extensions survive intact after passing through generators, formatters, converters, or developer portals.
- Manage structural changes to extensions to avoid breaking internal tools that consume them.

For example, if an endpoint requires a JWT, declare the `securitySchemes` and `security` requirement per OpenAPI. Adding `x-auth-mode: jwt` can only supplement metadata for a custom system; it does not replace standard security and does not make Spring Security validate tokens automatically.

## 11. Testing and Validating Extensions

After generating the document, verify both OpenAPI document validity and extension conventions.

Verify by:

1. Downloading OpenAPI JSON or YAML from the Springdoc endpoint.
2. Checking that extension names start with `x-` and sit on the right objects.
3. Checking value data types and structure against internal conventions.
4. Running an OpenAPI validator to confirm the document remains valid.
5. Running tools that consume the extension and confirming expected behavior.
6. Checking whether converted or distributed documents retain extensions.

Common mistakes:

| Symptom | Cause to Check |
|---|---|
| Validator reports invalid property | Extension name lacks `x-` prefix or is placed on an object that disallows extensions |
| Extension appears as a string instead of an object | Value was constructed or serialized with the wrong type |
| Swagger UI does not render metadata | UI does not support that extension or lacks a handling plugin |
| Extension disappears after a build step | Generator, formatter, or converter stripped unknown fields |
| Metadata differs across API groups | Customizer applies to only one scope or config sources overwrite each other |
| Internal tool fails to process extension | Name, location, type, or convention version mismatch |

OpenAPI validators primarily check specification structure. They do not automatically enforce custom business rules for `x-internal-owner` or `x-governance`. If an extension has an internal schema, add dedicated checks in CI or documentation governance tooling.

## 12. Principles for Using x-* in Springdoc Projects

When using extensions in a Spring Boot project, apply these principles:

1. Prefer standard OpenAPI fields before creating a new extension.
2. Prefix extension names with `x-` and keep casing consistent.
3. Choose clearly structured data types; avoid packing objects into strings.
4. Document the meaning, placement, owner, and consumers of each extension.
5. Use `@Extension`/`@ExtensionProperty` when metadata attaches to an operation or schema.
6. Use `OpenApiCustomizer` when adding metadata programmatically at the document level or a specific scope.
7. Never put secrets or sensitive data in extensions since OpenAPI documents may be widely distributed.
8. Verify with validators, JSON/YAML output, and the tools that actually read the extension.
9. Manage extension changes alongside API contract review and release processes.

Specification Extensions allow OpenAPI to adapt to an organization's specific needs while keeping a standard structure. When designed with clear conventions, `x-*` fields can support developer portals, code generators, governance workflows, and internal documentation without obscuring the core HTTP contract.

