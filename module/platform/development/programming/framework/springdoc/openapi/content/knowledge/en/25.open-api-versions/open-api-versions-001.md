# Distinguishing Specification Capabilities from Springdoc and UI Capabilities

When saying an API “supports OpenAPI 3.1”, you need to identify which layer is being discussed. The **OpenAPI Specification (OAS)** defines the structure and semantics of the API description document. **springdoc-openapi** inspects the Spring Boot application and generates a document according to the capabilities the library supports. **Swagger UI** reads that document to render it and let users try calling the API. These three components are related, but they do not share the same scope of responsibility.

A feature defined in OAS does not automatically mean springdoc can infer it from a controller, or that Swagger UI can render and execute it completely. Conversely, a UI option such as enabling the Try it out button does not change the OpenAPI contract. To accurately assess system capabilities, you must inspect the specification, document generator, UI, and consuming tools separately.

## 1. Three layers in the API documentation pipeline

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["springdoc-openapi"]
    B --> C["OpenAPI Description JSON/YAML"]
    C --> D["Swagger UI"]
    C --> E["Validator / Linter"]
    C --> F["Client generator"]
    C --> G["Contract tests / API gateway"]
    D --> H["Browser renders documentation"]
    D --> I["Try it out sends HTTP request"]
    I --> A
~~~

| Component | Primary role | What does it NOT do on its own? |
|---|---|---|
| **OpenAPI Specification** | Defines the standard for describing HTTP APIs, objects, fields, and interpretation rules | Does not create controllers, run a server, or validate requests |
| **springdoc-openapi** | Analyzes Spring applications, annotations, and configuration to generate an OpenAPI Description | Does not replace the specification, and does not automatically know all business rules hidden in code |
| **Swagger UI** | Reads an OpenAPI Description, renders operations/schemas, and provides an interactive UI | Does not generate a contract from controllers, and does not change server routes or access permissions |

An OpenAPI Description can be used independently by many tools such as validators, code generators, API gateways, contract tests, or developer portals. Swagger UI is only one way of consuming that document.

## 2. What does the OpenAPI Specification define?

OAS is a programming-language-agnostic standard for describing HTTP API interfaces. An OpenAPI document can be represented in JSON or YAML. Common objects include:

- **openapi**: the version of the OpenAPI Specification that the document uses.
- **info**: the title, description, contact, and version of the API document.
- **servers**: the server addresses that clients can call.
- **paths**: paths, HTTP methods, and operations.
- **components**: reusable schemas, responses, parameters, request bodies, and security schemes.
- **security**: security requirements at the document or operation level.
- **tags**: logical groupings of operations for documentation.

Example of a small document:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: 2.4.0
  description: Product catalog management API.
servers:
  - url: https://api.example.com
paths:
  /products:
    get:
      operationId: listProducts
      summary: List products
      responses:
        "200":
          description: Product list
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
~~~

The document above describes a GET operation and a Product schema. It does not create a `/products` endpoint in the application. If the server has not implemented that route yet, the OpenAPI document can still describe it, but actual requests will fail.

### The specification defines the contract, not contract enforcement

For example, a schema with `required`, `minimum`, `format`, or a 404 response helps clients understand valid data and possible outcomes. However, whether the server actually rejects invalid data, returns the right status code, or checks permissions depends on the implementation and runtime testing.

Similarly:

- **security** describes protection mechanisms; it does not enable Spring Security.
- **servers** describes addresses; it does not configure DNS, TLS, or a reverse proxy.
- **deprecated: true** indicates that an operation is deprecated; it does not automatically disable the route.
- **readOnly** and **writeOnly** describe schema usage; they do not automatically prevent code from writing or reading a property.

## 3. What does Springdoc do with a Spring Boot application?

springdoc-openapi is a Spring Boot integration library. It analyzes the information that the application exposes, such as:

- Mappings from @RestController, @RequestMapping, @GetMapping, @PostMapping.
- Parameter types, @PathVariable, @RequestParam, @RequestHeader, and request bodies.
- Return types and response metadata.
- Swagger/OpenAPI annotations such as @Operation, @Parameter, @Schema, @ApiResponse.
- Bean Validation constraints and certain serialization conventions.
- OpenAPI configuration, GroupedOpenApi, customizers, and supported integrations.

From that information, springdoc generates an OpenAPI Description, typically served at `/v3/api-docs` and `/v3/api-docs.yaml`. It can generate multiple documents by group, enrich metadata via annotations or customizers, and serve Swagger UI if a UI-enabled starter is used.

### Springdoc can only generate what it can observe

Some behavior resides in services, filters, converters, custom routers, or conditional logic that cannot be fully inferred from controllers. For example:

- A handler returns `ResponseEntity<?>` while the actual payload varies by business branch.
- Functional routes or custom endpoints require explicit metadata.
- Exception handlers return custom status codes.
- Serializers rename or omit fields depending on the user role.
- Access permissions depend on tenant, scope, or data state.

When springdoc cannot infer accurately, add annotations or use an appropriate extension point such as `OperationCustomizer`, `OpenApiCustomizer`, or declaring an `OpenAPI` model. Then compare the document against actual runtime responses and behavior. Do not assume an automatically generated document always reflects all business logic.

### Springdoc is not the OpenAPI Specification

springdoc may support a subset of OAS objects and features, and the exact scope of support depends on the library version, `swagger-core`, and how the application declares metadata. A feature present in the standard but not yet automatically generated by springdoc may still require manual declaration or a customizer, provided the library version has the corresponding model.

Conversely, a springdoc-specific property such as `springdoc.paths-to-match` or `springdoc.api-docs.version` is a configuration setting of the document generator. These properties are not fields in an OpenAPI document.

## 4. What does Swagger UI do with an OpenAPI Description?

Swagger UI is a web application that reads an OpenAPI Description and builds a user interface. It typically:

- Displays title, version, servers, and descriptive information.
- Groups operations by tag.
- Displays paths, methods, parameters, request bodies, responses, and schemas.
- Provides an Authorize button based on the described security schemes.
- Allows sending test HTTP requests via the Try it out feature if enabled.
- Supports customizing layout, sorter, filter, theme, and plugins.

Swagger UI does not generate an OpenAPI document from Spring controllers. It takes an existing document and renders it according to the capabilities of the UI version.

By default, Swagger UI does not replace an OpenAPI validator. A separate validator can be configured, but the fact that the UI loads and renders a document is not proof that the document complies with all OAS rules.

### The UI can restrict interactions without changing the specification

For example, Swagger UI has a `supportedSubmitMethods` setting. If this list is empty, the Try it out button can be disabled for all operations. The operations still remain in the OpenAPI document and can still be displayed.

Similarly, `tryItOutEnabled` controls the default state of the request-testing section. It does not delete operations, change the methods supported by the API, or alter the contract.

If Try it out does not work, check the UI configuration, CORS, `servers`, authentication, and connectivity to the API. Do not conclude that the OpenAPI Specification does not support an operation just because the UI cannot send the request.

## 5. Four versions that must not be confused

Within a single project, multiple version numbers can coexist simultaneously:

| Location | Example | Meaning |
|---|---|---|
| `openapi` field | 3.1.0 | OpenAPI Specification version of the document |
| `info.version` field | 2.4.0 | Version of the OpenAPI document; projects often use it to represent the API version |
| springdoc dependency | 2.x or 3.x | Spring Boot integration library version |
| Swagger UI assets | 5.x | Version of the packaged or served UI application |

In addition, the project also has versions for Spring Boot, Spring Framework, `swagger-core`, validators, and client generators. Each component has its own lifecycle and compatibility matrix.

### openapi is not info.version

In this example:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: 2.4.0
~~~

`3.1.0` states that the document uses OpenAPI 3.1 syntax and semantics. `2.4.0` is the version of the document described in the Info Object. Many projects set `info.version` to match the API release version so clients can identify it easily, but the two fields still have different meanings.

Changing `info.version` does not automatically convert a document from OpenAPI 3.0 to 3.1. Editing the `openapi` field as a string also does not automatically convert schemas or make the document generator support new features.

### The springdoc version is not the OpenAPI version

Upgrading springdoc may upgrade `swagger-core`, Swagger UI, and change how documents are generated. However, the dependency version is not the `openapi` field in the document. You must inspect the output document to know the actual OAS version.

Similarly, upgrading Swagger UI does not automatically upgrade the OAS document served by the server. The UI may understand newer specification versions, but it does not modify the document contents.

## 6. Differences between OpenAPI versions affect schemas

Different OAS versions can define how schemas are represented differently. A common example is nullable values.

In OpenAPI 3.0, schemas typically use `nullable: true`:

~~~yaml
type: string
nullable: true
~~~

In OpenAPI 3.1, the Schema Object is based on a more modern JSON Schema; a `null` value can be represented in `type`:

~~~yaml
type:
  - string
  - "null"
~~~

This is a difference in the specification language. Document generators, validators, UIs, and client generators must understand the exact version to interpret schemas properly. If you change the `openapi` field while keeping the old representation, the document may become invalid or be interpreted differently across tools.

OpenAPI 3.1 also changes how the Schema Object aligns with JSON Schema, expanding the ability to use JSON Schema vocabularies and structures. You should not assume every validator or generator fully supports all JSON Schema features simply because it accepts a document labeled 3.1.

## 7. Choosing the OpenAPI version in springdoc

With springdoc, the document version is configured using the property:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

In springdoc 2.x configuration documentation, `springdoc.api-docs.version` is described as choosing between OpenAPI 3.0 and 3.1; the default value is documented as `openapi_3_1`. Example configuration for 3.0:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Check the documentation for the exact springdoc branch you are using. Do not assume a new OAS version is supported just because that specification version has been released by the OpenAPI Initiative.

This property only selects the document version that springdoc generates within what the library version supports. It does not:

- Change the API version in `info.version`.
- Upgrade Spring Boot or the springdoc dependency.
- Upgrade Swagger UI assets.
- Guarantee that downstream validators and code generators support the same version.
- Automatically migrate every custom schema or extension to the new semantics.

After changing the property, inspect `/v3/api-docs` to verify the `openapi` field and check version-sensitive schemas.

## 8. Compatibility matrices must cover the entire chain

A system may use a new specification while one consuming component is older. For example:

| Layer | What to verify |
|---|---|
| Spring Boot | Is this version supported by the springdoc branch in use? |
| springdoc-openapi | Can it generate the right OAS version and needed objects? |
| swagger-core/model | Do the Java model and serializer preserve the required fields/schemas? |
| Swagger UI | Do the parser and renderer support the OAS version and used features? |
| Validator/linter | Does it validate against the right OAS version and dialect? |
| Client generator | Does it generate clients with accurate schemas, parameters, and security? |
| API gateway/contract test | Does it understand the same document and enforce policies properly? |

For example, the current springdoc compatibility matrix distinguishes the 2.x branch for Spring Boot 3.x and the 3.x branch for Spring Boot 4.x. For older projects on Spring Boot 2.x/1.x, follow the corresponding supported branch instead of simply upgrading springdoc to the latest version.

### Example of version gaps at the time of writing

As of 2026-11-20:

- The OpenAPI Specification has released version 3.2.1.
- The current springdoc configuration page documents `springdoc.api-docs.version` for selecting OpenAPI 3.0 or 3.1.
- The Swagger UI 5.32.0 compatibility table lists support up to OpenAPI 3.2.0.

These milestones show that the release of a new specification version does not mean every generator and UI already supports that same version. When targeting OAS 3.2.x, check the exact versions of springdoc, `swagger-core`, and Swagger UI in use; do not rely solely on the latest version of the standard.

Compatibility matrices change with each release. Check the documentation and actual dependencies of your project at upgrade time.

## 9. Distinguishing OAS features from automatic generation capabilities

Some features can be described in OpenAPI but are not automatically inferred from Spring controllers:

| Feature in OAS | What can springdoc do? | When must it be added manually? |
|---|---|---|
| servers | Can generate or accept server configuration depending on deployment | When there are multiple environments, proxy prefixes, or static server URLs |
| securitySchemes | Can read annotations or an OpenAPI bean | When custom security mechanisms are not inferred from Spring Security |
| callbacks | May require explicit metadata declarations | When an operation triggers callbacks to an external endpoint |
| webhooks | Must explicitly describe webhooks emitted by the service | When the API actively sends events to consumers |
| links | Requires metadata expressing relationships between a response and the next operation | When describing workflows between operations |
| oneOf, anyOf, allOf | Can be generated from schemas/annotations and supported model converters | When polymorphism or union types are not inferred accurately |
| Vendor extensions x-* | Can be added via annotations or customizers | When gateways or tooling require custom metadata |

Do not interpret this table as meaning every springdoc version supports all features in the same way. These are objects/concepts at the specification layer; how they are generated, serialized, and rendered depends on each tool's version.

## 10. Distinguishing OAS features from Swagger UI display capabilities

Swagger UI is a renderer and request-testing tool. It is not the standard that defines how every document must be presented.

| OpenAPI content | What Swagger UI can do | Limits to remember |
|---|---|---|
| Tags and operations | Displays lists and groups operations | Sorters only change UI ordering |
| Schemas and examples | Displays models, examples, and fields | Presentation depends on the UI version |
| Security schemes | Displays Authorize and attaches credentials to requests | Does not validate tokens in place of the server |
| Servers | Selects or uses a server URL to send requests | URL must be reachable and match the environment |
| Request/response | Displays structure and responses | Does not guarantee the server implements the schema accurately |
| Try it out | Sends real HTTP requests to the server | Depends on CORS, auth, network, and UI settings |
| Vendor extensions | May display if corresponding config is enabled | Not every extension has dedicated UI rendering |

An operation can still be valid in OpenAPI even if Swagger UI does not provide a suitable interactive control. A document can also be consumed cleanly by code generators even if the UI does not display it nicely.

Conversely, the UI displaying a schema does not prove the schema is valid under the standard. Use an appropriate validator/linter to verify the document.

## 11. Example of a feature that exists in the standard without the UI enforcing it for the server

Suppose a document has this operation:

~~~yaml
paths:
  /orders:
    post:
      operationId: createOrder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - productId
              properties:
                productId:
                  type: string
      responses:
        "201":
          description: Order created
~~~

Swagger UI can render a form or request body input area. When the user clicks Execute, the UI sends a request to the server URL. If the server has no `POST /orders` route, the request returns 404 even though the document displays the operation.

If the UI disables Try it out, the document still contains `POST /orders`; client generators can still create a method for that operation. Disabling the button only affects sending requests from the UI.

## 12. How to verify the version of each layer

Do not infer the entire pipeline from a single number in `pom.xml`. Check each place separately.

### Check the OpenAPI document

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '{openapi, infoVersion: .info.version}'
~~~

Example output:

~~~json
{
  "openapi": "3.1.0",
  "infoVersion": "2.4.0"
}
~~~

Check YAML if the application exposes it:

~~~bash
curl -s http://localhost:8080/v3/api-docs.yaml
~~~

### Check springdoc and transitive dependencies

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Look for these dependencies:

- springdoc-openapi-starter: the springdoc version.
- swagger-core or swagger models: the OpenAPI model/serializer library.
- swagger-ui or the WebJar containing assets: the actual UI version.
- Spring Boot and Spring Framework: the compatibility platform.

The dependency tree reveals the final resolved versions, not just directly declared versions. A BOM or dependency management can alter transitive versions.

### Check the Swagger UI being loaded

Open Developer Tools, go to the Network tab, filter for `swagger-ui`, or inspect loaded JavaScript/CSS resources. Cross-check the assets against the dependency tree or WebJar metadata. Do not guess the UI version solely from the springdoc version.

## 13. Validating documents with validators and real consumers

A sound verification workflow has multiple layers:

1. **Check version fields:** read `openapi` in the output JSON.
2. **Validate the document:** use a validator matching the OAS version and schema dialect.
3. **Check rendering:** open the document using the exact Swagger UI being packaged.
4. **Check code generation:** run the generator that real consumers will use.
5. **Check the contract:** compare runtime requests/responses against the document.
6. **Check interactivity:** test Authorize and Try it out in an environment with proper CORS and permissions.

Do not substitute the result of one step for the other steps:

- A document passing validation does not prove the server adheres to the contract.
- Swagger UI rendering successfully does not prove every other tool understands the document.
- A client generator running successfully does not prove runtime requests will succeed.
- Runtime requests succeeding does not prove the OpenAPI document is complete or accurate.

### Example of checking a version-sensitive schema

If a project migrates from OAS 3.0 to 3.1:

- Find schemas containing `nullable`.
- Check union types, `$ref`, and composition.
- Verify the JSON Schema dialect is supported by consuming tools.
- Run a validator for OAS 3.1.
- Generate clients using the exact downstream generator planned for use.
- Compare requests/responses before and after the change.

Do not simply change `openapi` to `3.1.0` and consider migration finished. You must convert schema representations and verify all related tools.

## 14. Common mistakes when confusing the three layers

| Symptom | Misconception | How to investigate |
|---|---|---|
| OAS defines a field, but springdoc does not generate it | Thinking the standard makes the app emit metadata automatically | Add annotations, beans, or customizers; check the springdoc version |
| Swagger UI does not display a feature | Concluding OAS does not support the feature | Check the UI version and renderer capabilities |
| UI lacks Try it out | Thinking the operation does not exist | Check `supportedSubmitMethods`, `tryItOutEnabled`, and the document |
| UI displays an operation, but the server returns 404 | Thinking the UI creates routes | Check Spring mappings and the server URL |
| `info.version` changes, but OAS remains 3.0 | Thinking the specification version was upgraded | Check the `openapi` field and `springdoc.api-docs.version` |
| springdoc is upgraded, but UI remains old | Thinking the starter always uses the newest UI | Check transitive dependencies and dependency management |
| Swagger UI parses it, but codegen fails | Thinking successful UI rendering is enough | Check generator feature support |
| Document validates, but API returns wrong payloads | Thinking schemas enforce runtime behavior automatically | Check serializers, validation, and contract tests |
| Manually writing `openapi: 3.2.1` | Thinking changing the label enables 3.2.1 support | Check whether models, serializers, validators, and UI actually support it |

## 15. Process for choosing and upgrading versions

When a project wants to adopt a new OpenAPI feature, follow this order:

1. **Identify the required feature:** locate the field or object in OAS and the first version that defines it.
2. **Choose the OAS version:** prefer a version that all critical consumers can support.
3. **Check springdoc:** verify the library branch is compatible with Spring Boot and can generate or allow adding the required feature.
4. **Check models/serializers:** ensure `swagger-core` and serializers do not drop the fields.
5. **Check Swagger UI:** verify the parser and renderer support the document version.
6. **Check validators and generators:** use the exact versions that will run in CI and on the consumer side.
7. **Create a fixture or sample document:** verify the new feature before rolling it out to the entire API.
8. **Run runtime tests:** ensure the server still fulfills the contract.
9. **Announce the change:** explicitly document the OAS version, API/document version, and toolchain requirements if consumers must upgrade.

If a key consumer does not yet support the new OAS version, you can continue publishing the older OAS version during a transition period or provide separate documents per consumer group. Do not silently downgrade if doing so loses schema or security semantics.

## 16. Checklist for identifying the right responsible layer

- [ ] Distinguished the `openapi` field from `info.version`.
- [ ] Identified the Spring Boot and springdoc versions in use.
- [ ] Checked transitive dependencies of `swagger-core` and Swagger UI.
- [ ] Identified which OAS version defines the needed feature.
- [ ] Verified springdoc can generate or allow adding that feature.
- [ ] Verified Swagger UI can parse and render the document.
- [ ] Verified validators/linters support the same OAS version.
- [ ] Ran the client generator if the project publishes SDKs.
- [ ] Verified the runtime contract separately from document validation.
- [ ] Avoided using UI options to draw conclusions about specification contents.
- [ ] Avoided editing the `openapi` field by hand to fake upgrade support.
- [ ] Documented compatibility requirements for consumers.

## 17. Official references

- [OpenAPI Specification – current version](https://spec.openapis.org/oas/latest.html): definitions of objects, fields, and semantics of an OpenAPI Description.
- [OpenAPI Specification 3.0](https://spec.openapis.org/oas/v3.0.4.html): specification documentation for the 3.0 branch.
- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.2.html): specification documentation for the 3.1 branch and Schema Object based on JSON Schema.
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html): current properties for document generation and Swagger UI.
- [springdoc-openapi v2 – Core Properties](https://springdoc.org/v2/core-properties.html): configuration for the springdoc branch targeting Spring Boot 3.x.
- [springdoc-openapi – Compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): relationship between springdoc branches and Spring Boot.
- [Swagger UI – Compatibility](https://github.com/swagger-api/swagger-ui#compatibility): support matrix between Swagger UI versions and the OpenAPI Specification.

## Conclusion

The OpenAPI Specification defines the contract and document semantics; springdoc-openapi generates the document from metadata provided by the Spring application; Swagger UI reads the document to display it and send test requests. The `openapi` version, `info.version`, springdoc dependency, and Swagger UI are separate axes. A feature present in the standard is not guaranteed to be auto-generated by springdoc or fully supported by the UI; a disabled UI button also does not remove an operation from the contract. Inspect the output document, dependency tree, and compatibility matrices of the UI, validators, generators, and runtime behavior before concluding that the entire system supports an OpenAPI version.
