# External Example Files and Accessibility from Rendering Tools

Request and response examples help integrators understand the data an API expects without having to guess from schemas. For small payloads, examples can be embedded directly into the OpenAPI document. For large payloads, multiple formats, or when sharing the same sample across multiple endpoints, you can store the content in a separate file and reference it via the **externalValue** property of the Example Object.

When using springdoc-openapi, the **@ExampleObject** annotation lets you declare `externalValue` along with a name, description, and summary. springdoc writes this reference into the generated specification; browsers and rendering tools such as Swagger UI are responsible for fetching the file's URL. Therefore, having a URL exist on the application server is not enough: the URL must be reachable from where the rendering tool runs, and the renderer version must support that reference mechanism.

## 1. Distinguishing inline examples, externalValue, and $ref

OpenAPI offers several ways to provide examples. The approaches below serve different purposes:

| Declaration | Meaning | When to use |
| --- | --- | --- |
| **example** | A direct illustrative value, concise for simple cases | A single sample value |
| **examples** with **value** | One or more Example Objects containing data directly inside the specification | Need multiple named samples, descriptions, or contexts |
| **examples** with **externalValue** | Example Object pointing to a URL containing the actual sample content | Large payloads, XML, CSV, PDF, images, or separately managed files |
| **examples** with **$ref** | Reference to a reusable Example Object in **components.examples** or another OpenAPI document | Need to reuse the same example across multiple operations |

**externalValue** is a URI pointing to example content. It is not a filesystem path to a file on the machine running Spring Boot. For example, **src/main/resources/static/examples/order.json** is a source path inside the project; the URL that tools need to access might be **https://api.example.com/examples/order.json**.

Do not confuse **externalValue** with **$ref**. **$ref** is used to reference a component or part of an OpenAPI document; **externalValue** points to raw sample data. Writing **value: { $ref: "./examples/order.json" }** does not load the JSON file as the example value. To point to file content, use `externalValue`.

In an Example Object, **value** and **externalValue** are mutually exclusive. If both are declared, the data source becomes ambiguous and tools may ignore one field. For external examples, only declare `externalValue` along with `summary` and `description` if needed.

An Example Object can be placed inside the **examples** property of a Parameter Object, Header Object, or Media Type Object. For parameters and headers, the example should reflect the serialized value according to the corresponding transmission rules. On these objects, the single **example** field and the map-typed **examples** field are also mutually exclusive; choose one declaration style per location.

## 2. Where to store sample files in a Spring Boot project?

A straightforward approach is storing examples in the application's static directory:

~~~text
src/
  main/
    resources/
      static/
        examples/
          orders/
            create-order.json
            order-created.json
            validation-error.json
~~~

With Spring Boot's default static resource configuration, the file **src/main/resources/static/examples/orders/create-order.json** can be served at the URL:

~~~text
https://api.example.com/examples/orders/create-order.json
~~~

Example contents of `create-order.json`:

~~~json
{
  "customerId": "CUS-100",
  "items": [
    {
      "productId": "PRD-001",
      "quantity": 2
    },
    {
      "productId": "PRD-008",
      "quantity": 1
    }
  ],
  "note": "Deliver during business hours"
}
~~~

Example files are packaged with the application and can be served through the static resource handler. Check the project's **spring.web.resources** configuration, since the application may have disabled static mappings or changed resource locations. If Swagger UI is served from a different host, examples can be stored on a web server or object storage dedicated to documentation.

Do not use filesystem paths like **C:\\project\\src\\main\\resources\\static\\examples\\orders\\create-order.json**, classpath paths like **classpath:/static/examples/...**, or **file://** URLs in `externalValue`. A user's browser cannot read the filesystem or classpath inside the Spring Boot server.

## 3. Declaring externalValue in OpenAPI YAML

The following example describes an order creation request using an external JSON file:

~~~yaml
paths:
  /api/orders:
    post:
      summary: Create order
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
            examples:
              standardOrder:
                summary: Standard order
                description: Contains two products and a delivery note.
                externalValue: https://api.example.com/examples/orders/create-order.json
      responses:
        '201':
          description: Order created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
              examples:
                createdOrder:
                  summary: Created order
                  externalValue: https://api.example.com/examples/orders/order-created.json
~~~

In a Media Type Object, **examples** is a named map. Each key such as `standardOrder` or `createdOrder` helps readers identify the choice. An Example Object can contain `summary`, `description`, `value`, or `externalValue`. The external content should be compatible with the schema of the corresponding media type.

An operation can have multiple examples:

~~~yaml
examples:
  standardOrder:
    summary: Standard order
    externalValue: https://api.example.com/examples/orders/create-order-standard.json
  giftOrder:
    summary: Order with gift wrapping request
    externalValue: https://api.example.com/examples/orders/create-order-gift.json
~~~

The samples above must both conform to the `CreateOrderRequest` contract. If you want to illustrate a malformed request or error response, place that sample on the error response with the corresponding error schema; do not attach an invalid payload to the success request schema if doing so contradicts the contract.

## 4. Using components.examples for reuse

If an example is used across multiple operations, you can declare it once in **components.examples** and reference it with **$ref**:

~~~yaml
components:
  examples:
    CreatedOrder:
      summary: Created order
      description: Successful response after creating an order.
      externalValue: https://api.example.com/examples/orders/order-created.json

    ValidationError:
      summary: Data validation error
      externalValue: https://api.example.com/examples/errors/validation-error.json

paths:
  /api/orders:
    post:
      responses:
        '201':
          description: Order created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
              examples:
                created:
                  $ref: '#/components/examples/CreatedOrder'
        '400':
          description: Invalid data
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
              examples:
                invalidRequest:
                  $ref: '#/components/examples/ValidationError'
~~~

**components.examples** only holds reusable Example Object definitions; operations use them via **$ref**. That is a reference to an Example Object inside the OpenAPI document, distinct from using `externalValue` to fetch file content. The two mechanisms can be combined: the operation references the component, and the component contains `externalValue`.

When updating an external file, every operation using that component will display the new sample if the URL stays the same. Therefore, manage versions of example files and avoid changing contents in a contract-breaking way without checking all consumers.

## 5. Declaring externalValue with annotations in Spring Boot

**@ExampleObject** from `swagger-annotations` has `name`, `summary`, `description`, `value`, `externalValue`, and `ref` attributes. Examples can be attached to a request body or response content.

Example declaring request and response:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @PostMapping(
        value = "/api/orders",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    @Operation(
        summary = "Create order",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreateOrderRequest.class),
                examples = {
                    @ExampleObject(
                        name = "standardOrder",
                        summary = "Standard order",
                        description = "JSON sample creating an order with multiple items.",
                        externalValue = "https://api.example.com/examples/orders/create-order.json"
                    )
                }
            )
        )
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Order created",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = OrderResponse.class),
                examples = {
                    @ExampleObject(
                        name = "createdOrder",
                        summary = "Created order",
                        externalValue = "https://api.example.com/examples/orders/order-created.json"
                    )
                }
            )
        )
    })
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        return ResponseEntity.status(201).body(orderService.create(request));
    }
}
~~~

The example uses Spring's `RequestBody` annotation on the method parameter. Inside **@Operation**, the request body section uses OpenAPI's annotation with its fully qualified name **io.swagger.v3.oas.annotations.parameters.RequestBody** to avoid confusing the two annotations with the same simple name.

If you need to embed a small example directly, you can use `value`:

~~~java
@ExampleObject(
    name = "minimalOrder",
    summary = "Minimal order",
    value = "{\"customerId\":\"CUS-100\",\"items\":[{\"productId\":\"PRD-001\",\"quantity\":1}]}"
)
~~~

Do not declare `value` alongside `externalValue` for the same Example Object. With `externalValue`, the annotation only writes the URL into the documentation; it neither copies the file from `src/main/resources` into the specification nor makes the file automatically served over HTTP.

## 6. Example file formats and media types

The example file must match the media type of the request or response. Several cases:

| Media type | Commonly used example file | Notes |
| --- | --- | --- |
| **application/json** | .json | Content must be valid JSON and match the schema |
| **application/xml** | .xml | XML must conform to the published structure and encoding |
| **text/plain** | .txt | Contains plain text, without wrapping in extra JSON |
| **text/csv** | .csv | Headers, delimiter, and encoding must be consistent |
| **application/pdf** | .pdf | Use a schema and media type describing binary content |
| **image/png**, **image/jpeg** | .png, .jpg | Renderer must support displaying images or providing a download link |

For JSON, the example should be an actual payload that the client sends or receives. For XML or CSV, preserve the original format instead of converting the content into a JSON object. For PDF or images, `externalValue` points to the binary file; whether Swagger UI renders it inline or only offers a download depends on the renderer's capabilities and media type.

If the API uses `multipart/form-data`, examples for individual parts may require separate encoding and content type configuration. Do not assume a single external JSON file can represent the entire multipart request without describing the part structure.

## 7. Conditions for Swagger UI to access external files

`externalValue` is written into the OpenAPI document, but Swagger UI must fetch the file URL from the browser. Check the following conditions:

1. The URL uses a protocol allowed by the environment, preferring HTTPS when the documentation page also runs over HTTPS.
2. The URL is public or has appropriate access permissions from the user's browser.
3. A GET request to the URL returns `200 OK` and the actual file content, not a login page or HTML error page.
4. If the file is on a different origin from Swagger UI, the file server must allow CORS from Swagger UI's origin.
5. Proxies, gateways, CDNs, or WAFs do not block the path or file fetch request.
6. The response `Content-Type` and content match the example's media type.
7. The URL does not require a secret token embedded in OpenAPI or a cookie that the browser cannot send.

If Swagger UI and the sample file share the same origin—for example, both served from **https://api.example.com**—CORS configuration is usually unnecessary for the file fetch request. If Swagger UI is at **https://docs.example.com** while the file is at **https://api.example.com**, the file server needs to return appropriate CORS headers, such as:

~~~http
Access-Control-Allow-Origin: https://docs.example.com
~~~

In access-controlled environments, only allow known documentation origins and the required `GET` method. Do not open CORS wider than your organization's policy. Also check the documentation page's Content Security Policy if `connect-src` restricts which hosts the browser may call.

Never put real customer data, access tokens, payment information, or sensitive internal data in public example files. Files in static resources or on a CDN can be downloaded directly without passing through business-endpoint authorization.

## 8. Absolute URLs, relative URLs, and context paths

OpenAPI permits URI references, yet how each tool resolves relative URLs can differ. Swagger UI currently lists relative path support for external files as an unimplemented limitation. Consequently, absolute URLs are usually easier to operate and verify:

~~~yaml
externalValue: https://api.example.com/examples/orders/create-order.json
~~~

Do not assume the following URL will be resolved identically by every renderer:

~~~yaml
externalValue: ./examples/orders/create-order.json
~~~

Relative URLs can be affected by the base URL, `servers`, the OpenAPI document address, reverse proxies, and the Swagger UI version. When an application is deployed under a context path such as `/store`, an absolute URL must include the proper public prefix:

~~~text
https://api.example.com/store/examples/orders/create-order.json
~~~

If multiple environments have different hosts, you can generate environment-specific specifications or use a stable documentation host to distribute examples. Avoid leaving URLs pointing to `localhost`, private network IPs, or hostnames that only exist in development.

## 9. Support across tool versions

The OpenAPI specification defines `externalValue`, but the ability to fetch and display content depends on the renderer:

| Tool / format | Notes |
| --- | --- |
| OpenAPI 3.1 and Swagger UI 5 | Swagger UI 5 supports external examples in OpenAPI 3.1 definitions; recent releases support current 3.1 versions |
| OpenAPI 3.0.x and Swagger UI | `externalValue` support has varied across versions; verify the exact Swagger UI version and `swagger-client` resolution behavior |
| Older Swagger UI | May show the URL or an empty field instead of the file content |
| Other tools | May read `externalValue`, display only the URL, or skip fetching the file |

In particular, an OpenAPI 3.1 document does not mean every renderer automatically supports every 3.1 capability. Check the `openapi` field in `/v3/api-docs` and the actual Swagger UI version bundled with the starter or served from a CDN.

If the renderer cannot load external examples, you can keep examples directly in the document using `components.examples`:

~~~yaml
components:
  examples:
    CreatedOrder:
      summary: Order created
      value:
        id: 4201
        orderNumber: ORD-2026-0042
        status: CONFIRMED
~~~

Then reference it:

~~~yaml
examples:
  created:
    $ref: '#/components/examples/CreatedOrder'
~~~

This is a more broadly compatible fallback because the sample data lives inside the specification itself. If you need to keep external files as the source of truth, you can create a build step to sync their contents into `components.examples` before distributing the documentation.

## 10. Verifying sample files and browser requests

Check the file URL independently before opening Swagger UI:

~~~bash
curl -i https://api.example.com/examples/orders/create-order.json
~~~

Confirm:

- Status is `200`.
- `Content-Type` is `application/json` or the appropriate media type for the file.
- The body is the expected JSON content, not HTML returned by login, a proxy, or a routing error.
- The file is reachable from the network and origin that Swagger UI users use.

Then open `/v3/api-docs` and verify `externalValue` was generated properly by springdoc. In Swagger UI, open Developer Tools, select the Network tab, and reload the documentation. Filter requests by the example filename to check:

- Whether the request URL has the right host, context path, and filename.
- Whether the request is blocked by CORS, CSP, TLS, or a proxy.
- Whether the status and response body are correct.
- Whether the browser reports any parse or rendering errors.

Finally, test both the example presentation and the **Try it out** flow. A renderer may display a link yet be unable to use the file content to populate the request body; this behavior depends on version and plugins. Try sending a request in a test environment and verify the sent payload is correct.

## 11. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Swagger UI displays the URL instead of sample content | Renderer does not support or does not handle `externalValue` for the current OpenAPI version | Check Swagger UI and OpenAPI versions; use inline examples if compatibility is required |
| File fetch request returns 404 | Generated URL is wrong or static resources are not being served | Open the URL directly, check static mappings and context path |
| File fetch request blocked by CORS | File and Swagger UI are on different origins | Configure CORS on the file server for the documentation origin |
| Request returns 200 but the example is HTML | Proxy or auth system redirects to a login/error page | Check body and `Content-Type`; configure an appropriately accessible file path |
| URL works on dev machine but fails when deployed | Using `localhost`, internal hostname, or wrong prefix | Use the public URL of the deployment environment |
| File loads but example does not fit schema | Outdated sample file or payload out of sync with contract | Validate the file against the schema and update samples alongside the API |
| `externalValue` has no effect when using `value: {$ref: ...}` | Confused file reference with Reference Object | Use `externalValue` for data files or `$ref` to `components.examples` |
| Example disappears after upgrading Swagger UI | OpenAPI 3.0/3.1 support differences or renderer change | Check UI version, `openapi` field, and Network requests |
| Sample file exposes data that should not be public | Static resource or CDN allows broad access | Use synthetic data and review access permissions before publishing |

## 12. Workflow for managing external examples

To keep examples aligned with the API contract, you can follow this workflow:

1. Identify important requests/responses to illustrate and their corresponding schemas.
2. Create sample files using synthetic data, naming them clearly by purpose and format.
3. Store files in `src/main/resources/static/examples` or an appropriate documentation distribution store.
4. Put an accessible URL into `@ExampleObject(externalValue = "...")` or the Example Object in YAML.
5. Verify the file URL, `Content-Type`, access permissions, and CORS from the Swagger UI origin.
6. Load `/v3/api-docs`, confirm `externalValue`, and inspect on the exact target Swagger UI version.
7. Validate sample payloads against schemas and test **Try it out** in a suitable environment.
8. When updating schemas, update example files and check operations reusing components.

Use versioned URLs or immutable filenames when examples are hosted on a CDN. For example, **examples/v1/orders/create-order.json** lets readers of older docs continue receiving the right content. If a URL stays unchanged while its contents are replaced, CDN or browser caches may cause some users to see stale examples for a period of time.

## 13. Pre-publication checklist

- [ ] `externalValue` is a URI pointing to actual sample content.
- [ ] Example Object does not declare both `value` and `externalValue`.
- [ ] Sample file has the right format for the media type and matches the schema.
- [ ] URL uses a public host and context path, not `localhost` or a filesystem path.
- [ ] Swagger UI users' browsers can access the URL.
- [ ] CORS and CSP allow fetching the file when needed.
- [ ] Swagger UI version supports this `externalValue` usage and the emitted OpenAPI version.
- [ ] No sensitive data is included in examples.
- [ ] Files follow a versioning process and are updated alongside the API contract.
- [ ] An inline `components.examples` fallback exists if the renderer cannot fetch external files.

## 14. Official references

- [OpenAPI Specification 3.1.2 — Example Object](https://spec.openapis.org/oas/v3.1.2.html#example-object) — `value`, `externalValue`, mutual exclusivity, and usage in parameters/headers/media types.
- [OpenAPI Specification 3.1.2 — Components Object](https://spec.openapis.org/oas/v3.1.2.html#components-object) — storing reusable Example Objects in `components.examples`.
- [Swagger Docs — Adding Examples](https://swagger.io/docs/specification/v3_0/adding-examples/) — inline and external examples for JSON, PDF, and other media types.
- [Swagger UI — External Example Support](https://github.com/swagger-api/swagger-ui/issues/5433) — history of `externalValue` support, OpenAPI 3.0/3.1 differences, and behavior by Swagger UI version.
- [Swagger UI — CORS](https://swagger.io/docs/open-source-tools/swagger-ui/usage/cors/) — cases where CORS must be enabled for documentation and resources loaded from another origin.
- [Swagger Annotations — ExampleObject](https://docs.swagger.io/swagger-core/v2.2.25/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html) — `name`, `summary`, `description`, `value`, `externalValue`, and `ref` attributes.
- [Springdoc-openapi — Introduction](https://springdoc.org/intro.html) — how the library generates OpenAPI from Spring Boot structure and annotations.

External example files keep documentation concise, reusable, and supportive of content that is difficult to embed directly into YAML/JSON. The value of this approach depends on stable URLs, browser accessibility, proper CORS, and renderer support. Test both the OpenAPI specification and Swagger UI behavior before treating external examples as a finished part of the integration experience.
