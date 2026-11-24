# Info: title, summary when supported, description, and version

## 1. Role of the Info Object in OpenAPI

An OpenAPI document describes the contract that clients use to call an API. Alongside the list of endpoints, parameters, request bodies, and responses, the document needs identifying information about the API: what the API is called, what purpose it serves, what its high-level description is, and which version the contract is at.

OpenAPI places this information in the **Info Object**, located at the root **info** field of the document. With Spring Boot, Springdoc OpenAPI generates this section from Java configuration, annotations, or an `OpenAPI` bean provided by the application.

The Info Object helps:

- Readers identify the right API when a system has multiple services.
- Swagger UI display the title and overview description at the top of the documentation page.
- Clients, developer portals, and automated tools have information to distinguish contracts.
- Development teams publish the API contract version and responsible contact information.

Info is metadata describing the entire API covered by the document. It does not replace per-endpoint descriptions. For example, `Info.description` states that the API manages products and orders, whereas `Operation.summary` specifically describes what the `GET /products/{id}` endpoint does.

## 2. Position and Structure of the Info Object

An OpenAPI document typically has root fields **openapi**, **info**, **servers**, **paths**, and may have **components**, **security**, or **tags**. The Info section sits directly under the root:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  summary: Online store API
  description: |
    API allowing applications to manage products, categories, and orders.
    This document describes the HTTP contract for integrating systems.
  version: "1.4.0"
paths: {}
~~~

In this example:

- **openapi: 3.1.0** indicates that the document uses OpenAPI Specification version 3.1.0.
- **info.title** is the API name.
- **info.summary** is the short summary, if supported by the OpenAPI version.
- **info.description** is the more detailed description of the API.
- **info.version** is the version of the API described in the document.

Distinguish **openapi** at the root level from **info.version**. The `openapi` field indicates which version of the OpenAPI Specification the document follows; `info.version` indicates the version of the API contract the organization is publishing. Both values serve different purposes and can change independently.

## 3. title: a Clear and Stable API Name

The **title** field is the official name of the API and is a required field in the Info Object. This name usually appears prominently in Swagger UI and OpenAPI reading tools.

Example:

~~~yaml
info:
  title: Product Catalog API
  version: "1.0.0"
~~~

A good title should:

- Clearly state the business domain or main capability.
- Distinguish the API from other services in the same system.
- Use consistent naming across environments and document versions.
- Avoid putting environment names like `local`, `staging`, or `production` into `title` if the same contract is deployed across multiple environments.

Some examples:

| Unclear Name | Clearer Name |
|---|---|
| Backend API | Customer Management API |
| Service | Order API |
| API v1 | Inventory API |
| My Application | Payment Gateway API |

The API title does not need to cram every capability into one line. Details such as target consumers, endpoint scope, or business constraints should be explained in `summary` and `description`.

## 4. summary: Short Summary When Supported

**summary** is a short summary sentence about the API at the Info Object level. This field was added in OpenAPI Specification 3.1.0. Therefore, not every OpenAPI 3.0 document or every version of an OpenAPI model library can represent this field.

Example:

~~~yaml
info:
  title: Shop API
  summary: Store catalog and order management API
  version: "1.4.0"
~~~

Summary should concisely answer what purpose the API serves. One sentence is usually enough. Avoid repeating `title` verbatim or turning `summary` into a long instruction paragraph.

Distinguish between two kinds of summary:

- **Info.summary** summarizes the entire API in the document.
- **Operation.summary** summarizes a specific HTTP operation, declared via the **@Operation** annotation or the `summary` field of an Operation Object.

For example, `Info.summary` might be "Online store management API", while `Operation.summary` for the order creation endpoint is "Create new order".

### 4.1. When the Document Uses OpenAPI 3.0

OpenAPI 3.0 does not define the **info.summary** field. If the application generates a 3.0 document, place the short introductory sentence at the beginning of **info.description** and do not assume Swagger UI will understand an arbitrary `summary` field.

### 4.2. When the Document Uses OpenAPI 3.1

OpenAPI 3.1.0 and later define `Info.summary`. To use it, ensure that the version of Springdoc along with the `swagger-models` or `openapi-annotations` library used by your project supports this property, and that the generated document actually declares the corresponding OpenAPI version.

Do not rely solely on the Java code compiling. Download the OpenAPI JSON/YAML and verify whether the **info.summary** field appears in the right place. If the library in use does not yet have the corresponding API, upgrade according to the compatibility matrix before calling the `summary` property in source code.

## 5. description: Describing API Scope and Usage

The **description** field provides a more detailed explanation of the API. This is the place to describe:

- Business objectives and scope of the API.
- Groups of capabilities or resources provided.
- Intended client consumers.
- Common conventions such as time zones, data formats, or error handling.
- Links to integration guides, policies, or supplementary documentation when appropriate.

Example:

~~~yaml
info:
  title: Shop API
  description: |
    API for retail applications and integrating systems.

    Main functional groups:
    - Manage products and categories.
    - Create and track orders.
    - Look up payment status.

    Timestamps in responses use ISO 8601 format.
    Endpoints requiring authentication are described using security schemes.
  version: "1.4.0"
~~~

According to the OpenAPI Specification, `description` supports CommonMark. Therefore, you can use Markdown to create paragraphs, lists, links, and emphasis. When writing multiline YAML, the block scalar **|** helps keep the structure readable.

The description should provide enough context for integrators to start using the API. Endpoint-specific details should still be placed in **@Operation.description**, parameter descriptions, or corresponding schema descriptions.

Avoid putting secrets, active sample tokens, internal system addresses, or infrastructure details not meant for documentation readers. If `description` contains links, use stable URLs and verify access permissions for the recipients of the documentation.

## 6. version: Version of the Described API

The **version** field is a required field in the Info Object and has a string type. It identifies the version of the API that the document is describing.

Example:

~~~yaml
info:
  title: Shop API
  version: "1.4.0"
~~~

`version` should be set as a string with a clear convention. A project may use Semantic Versioning or its own numbering policy, as long as the development team and clients share the same meaning.

If applying a convention similar to Semantic Versioning:

- Increment the major version when making breaking compatibility changes.
- Increment minor when adding backward-compatible functionality per the API's policy.
- Increment patch when fixing bugs or updating descriptions without changing the contract under the agreed policy.

This is a versioning policy chosen by the API team; OpenAPI itself does not enforce how versions are incremented. Even a seemingly additive change must be evaluated against actual client behavior—for instance, adding a required field to a request can break older clients.

### 6.1. Distinguishing Version Types

| Value | Meaning |
|---|---|
| Root field `openapi` | OpenAPI Specification version the document conforms to, e.g., 3.0.3 or 3.1.0 |
| `info.version` | Version of the API or contract being described |
| Application version | Build or release version of the software implementing the API |
| URL version | Version expressed in the path, e.g., `/api/v1` or `/api/v2` |

These values do not have to be identical. For example, an application build 2.8.5 can continue serving API contract v1.4.0; that document can use OpenAPI 3.1.0.

**info.version does not automatically create endpoint versioning.** Setting `info.version` to `2.0.0` does not automatically move path `/api/v1` to `/api/v2`, create new controllers, or maintain two API versions in parallel. Version routing must be implemented in controllers, paths, headers, media types, or whichever versioning mechanism the application chooses.

## 7. Adding Related Metadata

The Info Object also has several optional fields that tell readers where to reach out and the terms of use for the documentation:

- **termsOfService**: URL to the terms of service.
- **contact**: name, email, or URL of the team responsible for the API.
- **license**: license name and URL or identifier information per the supported specification version.

Example:

~~~yaml
info:
  title: Shop API
  description: Product and order management API.
  version: "1.4.0"
  termsOfService: https://example.com/terms
  contact:
    name: API Support
    url: https://example.com/support
    email: api-support@example.com
  license:
    name: Apache 2.0
    url: https://www.apache.org/licenses/LICENSE-2.0.html
~~~

The URLs in the example are illustrative addresses. When deploying, replace them with real pages and ensure the contact information belongs to the right responsible team.

It is not mandatory to declare all optional fields. Publish only information that has been approved by the organization and remains valid. For internal APIs, `contact` can be an internal support channel; for public APIs, support and license information should match publication policies.

## 8. Configuring Info with Annotations in Spring Boot

Springdoc can extract metadata from the **@OpenAPIDefinition** and **@Info** annotations in the **io.swagger.v3.oas.annotations** package.

Example:

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Shop API",
        version = "1.4.0",
        description = "API for retail applications and integrating systems. "
            + "Provides product, category, and order management capabilities. "
            + "Timestamps in responses use ISO 8601 format."
    )
)
public class OpenApiConfiguration {
}
~~~

This approach works well when metadata can be declared statically via annotations. The `title`, `version`, and `description` fields give the document basic identification and introductory information.

If the **@Info** annotation version in use supports the `summary` attribute and the document is exported as OpenAPI 3.1.0 or higher, you can add `summary` directly in the annotation. If the compiler reports a missing attribute or the generated document lacks that field, check the library version and specification version in use before changing dependencies.

## 9. Configuring Info with an OpenAPI Bean

Another option is to declare an **OpenAPI** bean and construct the **Info** object in Java:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI shopOpenAPI() {
        Info info = new Info()
            .title("Shop API")
            .version("1.4.0")
            .description("API for retail applications and integrating systems. "
                + "Provides product, category, and order management capabilities.");

        return new OpenAPI()
            .info(info);
    }
}
~~~

This approach fits when you need to build metadata in code, reuse configuration values, or conditionally add information.

If the `swagger-models` version in use supports `Info.summary` and the application outputs OpenAPI 3.1.0 or higher, you can additionally set:

~~~java
info.setSummary("Product, category, and order management API");
~~~

The method above only works when the model version has the `summary` property. With OpenAPI 3.0 or an unsupported library, omit this configuration and put the summary sentence into `description`.

Choose a single primary configuration source for Info to avoid declaring metadata redundantly in multiple places. If the application uses both annotations and an `OpenAPI` bean, inspect the generated output to ensure no values are unexpectedly overwritten.

## 10. Verifying Info in OpenAPI JSON and YAML

After starting the application, access Springdoc's default documentation endpoint:

~~~http
GET /v3/api-docs
~~~

If configured to export YAML, you can fetch the document at:

~~~http
GET /v3/api-docs.yaml
~~~

Locate the **info** section at the root level and verify:

- Does `title` show the correct API name?
- Does `summary` appear when using OpenAPI 3.1 and a supporting library?
- Does `description` preserve multiline content and links properly?
- Does `version` match the published contract version?
- Are `contact`, `license`, and `termsOfService` accurate if declared?
- Does the root `openapi` field match the specification version expected by the team?

Expected document excerpt example:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  summary: Product, category, and order management API
  description: |
    API for retail applications and integrating systems.
  version: "1.4.0"
~~~

Swagger UI typically displays `title` and `description` at the top of the interface. `Summary` may be displayed depending on the Swagger UI version and configuration; therefore, verify both the OpenAPI document content and the actual UI.

## 11. Common Mistakes When Configuring Info

| Symptom | Cause to Check |
|---|---|
| Swagger UI shows default API name | Info not declared or configuration not scanned/loaded by Spring |
| Title is right but version is wrong | Multiple configuration sources or another `OpenAPI` bean provides Info |
| Summary does not appear | Document uses OpenAPI 3.0 or model/annotation library does not support `Info.summary` |
| Description loses formatting | YAML multiline or concatenated Java strings formatted differently than expected |
| Version is parsed as a number | YAML does not quote `version`; declare it explicitly as a string |
| Info.version changes but URL does not | `Info.version` is only metadata and does not perform version routing |
| Swagger UI does not reflect updates | Application not restarted, cached, or reading from another endpoint/group |

When investigating, inspect the OpenAPI JSON/YAML directly first. If the data in the document is already correct but the UI does not display it as expected, check the Swagger UI version and UI configuration. If the document itself is wrong, inspect the Info configuration source and which bean or annotation Springdoc actually loaded.

## 12. Guidelines for Maintainable Metadata

A good Info Object should be concise, properly scoped, and consistent:

1. Use `title` to clearly identify the API and business domain.
2. Use `summary` as a short introductory sentence if OpenAPI 3.1 and the library support it.
3. Use `description` to explain scope, common conventions, and needed links.
4. Use `version` to specify the API contract version, without confusing it with the OpenAPI version or build version.
5. Declare `contact`, `license`, and `termsOfService` only when the information is confirmed.
6. Manage metadata in a single primary configuration source.
7. Check the `info` section in the JSON/YAML document after every relevant change.

The Info Object is the starting point for users to understand the API before diving into individual endpoints. When `title`, `summary`, `description`, and `version` are clearly defined, Springdoc can produce documentation that is easy to recognize, easy to distribute, and convenient for managing API contracts over time.

