# Encoding Object and Per-Part Content Types

When an API receives `multipart/form-data` or `application/x-www-form-urlencoded`, a request body can contain multiple fields with different representations. For instance, an upload request might include a PDF file, JSON metadata, and a list of text labels. OpenAPI describes field structures with the Schema Object, while the **Encoding Object** specifies how each property in the body is encoded—including media type, per-part headers, and how arrays or objects are serialized. Springdoc-openapi can generate documentation from Spring Boot controllers while also letting you add Encoding Objects via Swagger annotations when granular contract control is needed.

## 1. Why do we need the Encoding Object?

With standard JSON, the entire body typically shares a single media type:

```http
POST /api/products HTTP/1.1
Content-Type: application/json

{"name":"Ballpoint pen","price":12000}
```

However, `multipart/form-data` splits the body into multiple parts. Each part has a field name, content, and potentially its own media type. A document upload request might send:

- `file`: PDF or image content.
- `metadata`: a JSON object containing title, document category, and description.
- `labels`: one or more text values.

The request-level header states that the overall body is multipart; each part's headers indicate how to read that part's content. If you only declare the schema without specifying how complex properties are encoded, clients might not know whether to send `metadata` as JSON or as a form string.

The Encoding Object solves this by attaching encoding rules to each property in the request body's schema. It does not redefine the data structure; the Schema Object still describes field names, types, and constraints.

## 2. Distinguishing request `Content-Type` from per-part `Content-Type`

A multipart request has two levels of media types:

1. **Overall media type:** usually `multipart/form-data` with a `boundary` parameter to separate parts.
2. **Per-part media type:** such as `application/pdf`, `image/png`, `application/json`, or `text/plain`.

Condensed example:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=Boundary-123

--Boundary-123
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

...PDF file bytes...
--Boundary-123
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"User guide","category":"manual"}
--Boundary-123
Content-Disposition: form-data; name="labels"
Content-Type: text/plain

internal
--Boundary-123--
```

The `Content-Type: multipart/form-data; boundary=...` header describes the entire request. `Content-Type: application/pdf` and `Content-Type: application/json` sit inside individual parts. These two levels do not replace one another.

When using a browser or curl to construct a multipart request, the client typically generates the boundary automatically. Do not manually set `Content-Type: multipart/form-data` without a boundary, or the server will not know how to split the parts.

## 3. Where does the Encoding Object live in OpenAPI?

The Encoding Object is declared under `encoding` of a Media Type Object inside the Request Body Object's `content`. Each key in `encoding` must match a property name in the body schema.

Example:

```yaml
paths:
  /api/documents:
    post:
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required: [file, metadata]
              properties:
                file:
                  type: string
                  format: binary
                metadata:
                  $ref: '#/components/schemas/DocumentMetadata'
            encoding:
              file:
                contentType: application/pdf
              metadata:
                contentType: application/json
```

In this example, `schema.properties` defines two fields: `file` and `metadata`. `encoding.file` specifies that the `file` part is sent as PDF; `encoding.metadata` specifies that the `metadata` part has the JSON media type. The names `file` and `metadata` must match the property names in the schema.

The Encoding Object is meaningful only for `multipart/form-data` and `application/x-www-form-urlencoded` request bodies. For standard JSON bodies, describe the structure with a JSON schema; do not use `encoding` to replace JSON `properties` or `content`.

## 4. Properties of the Encoding Object

The Encoding Object has the following main properties:

| Property | Meaning | Common usage |
|---|---|---|
| `contentType` | Media type of the property or part | Choosing JSON for metadata, PDF for files, or text for string fields |
| `headers` | Additional headers applied to individual multipart parts | Describing checksum, language, or part-specific metadata headers |
| `style` | Serialization rule for arrays/objects | Choosing how objects or lists are represented in form bodies |
| `explode` | Determines whether array/object values are split into multiple fields or combined | Controlling how lists or objects are sent per style |
| `allowReserved` | Allows keeping certain reserved characters unencoded instead of percent-encoding | Meaningful for `application/x-www-form-urlencoded` |

These properties do not change the data types in the schema. They only describe how a property's value is serialized into the request content for the declared media type.

### `contentType`: media type of a property

`contentType` specifies the media type used to encode a property. Its value can be a single media type or a comma-separated list of media types if the property accepts multiple formats.

```yaml
encoding:
  file:
    contentType: application/pdf, image/png
  metadata:
    contentType: application/json
  comment:
    contentType: text/plain; charset=UTF-8
```

In this example, the client can send the file as PDF or PNG; metadata is JSON; comment is UTF-8 text. Published formats must match what the endpoint actually processes.

If `contentType` is omitted, OpenAPI defines defaults based on the property schema:

- Primitive types or arrays of primitives typically default to `text/plain`.
- Object types or arrays of objects typically default to `application/json`.
- Strings with `format: binary` typically default to `application/octet-stream`.

When the contract requires a specific media type, declare it explicitly so clients do not rely on defaults. For PDF or image files, declaring `application/pdf` or `image/png` helps integrators understand which file types are accepted.

### `headers`: per-part headers

`headers` is a map of Header Objects applied to individual parts of a multipart request. For example, an API might ask clients to send a file checksum in a dedicated part header:

```yaml
encoding:
  file:
    contentType: application/pdf
    headers:
      X-Checksum-SHA256:
        description: SHA-256 of the file content
        schema:
          type: string
          pattern: '^[a-fA-F0-9]{64}$'
```

This header belongs to the `file` part, not to the request level. Do not confuse `headers` inside the Encoding Object with operation-level `parameters`. Header parameters describe headers of the entire request; Encoding Object headers describe headers of individual multipart parts.

A part's `Content-Type` is controlled by `contentType`. If `Content-Type` is declared under `encoding.headers`, it is ignored per the OpenAPI specification. Standard multipart headers such as `Content-Disposition` are usually generated by the client from property and file names; only document custom headers when the API actually requires them.

### `style` and `explode`: array/object serialization

`style` determines how array or object values are represented. The default in the Encoding Object is `form`. `explode` decides whether objects or arrays are split into separate values; it defaults to `true` when `style` is `form`, and `false` for other styles.

Example schema with a list of labels:

```yaml
schema:
  type: object
  properties:
    labels:
      type: array
      items:
        type: string
encoding:
  labels:
    style: form
    explode: true
```

With `form` and `explode: true`, elements can be sent as multiple values under the same field name, such as `labels=internal` and `labels=approved`. With `explode: false`, the list is joined into a single value according to the style's serialization rule, such as a comma-separated string.

For objects, `style` and `explode` also affect how properties are represented. Pick a serialization style supported by both the framework and clients; do not declare `deepObject`, `spaceDelimited`, or `pipeDelimited` out of habit if the media type and processing tools do not support those rules.

### `allowReserved`: reserved characters in URL-encoded forms

`allowReserved` controls whether reserved characters in values may remain unencoded instead of being percent-encoded. Its default is `false`. This property is meaningful only for `application/x-www-form-urlencoded`.

Example:

```yaml
content:
  application/x-www-form-urlencoded:
    schema:
      type: object
      properties:
        callback:
          type: string
    encoding:
      callback:
        allowReserved: false
```

Normally keep it `false` to prevent characters like `&`, `=`, `?`, or `#` from altering form/query parsing. Enable `true` only when the contract has a clear reason and client/server agree on how to interpret the value.

## 5. Multipart example: PDF file, JSON metadata, and label list

An upload endpoint typically has an overall object schema. The file property uses `type: string` and `format: binary`; metadata references a JSON schema; labels is an array of strings.

```yaml
paths:
  /api/documents:
    post:
      summary: Upload document
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required:
                - file
                - metadata
              properties:
                file:
                  type: string
                  format: binary
                  description: PDF file to upload
                metadata:
                  $ref: '#/components/schemas/DocumentMetadata'
                labels:
                  type: array
                  items:
                    type: string
            encoding:
              file:
                contentType: application/pdf
                headers:
                  X-Checksum-SHA256:
                    description: SHA-256 of the file
                    schema:
                      type: string
              metadata:
                contentType: application/json
              labels:
                style: form
                explode: true
      responses:
        '201':
          description: Document saved
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DocumentResponse'
components:
  schemas:
    DocumentMetadata:
      type: object
      required: [title, category]
      properties:
        title:
          type: string
        category:
          type: string
          enum: [manual, invoice, contract]
        description:
          type: string
    DocumentResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        fileName:
          type: string
```

Here, `file` is sent with media type `application/pdf`; `metadata` is sent as a JSON part; `labels` is serialized as separate form values. `X-Checksum-SHA256` is a header on the file part. The operation's response remains regular JSON and is unrelated to the request's Encoding Object.

### Sample curl request

```bash
curl -i -X POST http://localhost:8080/api/documents \
  -H 'Accept: application/json' \
  -F 'file=@guide.pdf;type=application/pdf' \
  -F 'metadata={"title":"User guide","category":"manual"};type=application/json' \
  -F 'labels=internal' \
  -F 'labels=approved'
```

curl automatically generates the boundary for the multipart request. In this example, `type=application/json` attaches the JSON media type to the metadata part; two `labels` fields are sent repeatedly to represent an array with `explode: true`. If the API requires a checksum, the client must send it as a header on the file part following the convention the server expects. The ability to attach custom per-part headers depends on the client tool; the standard browser `FormData` API does not provide a way to set arbitrary per-part headers.

## 6. Mapping the Encoding Object in Spring Boot

In Spring MVC, `@RequestPart` is usually suitable when a multipart part needs conversion into a DTO via an `HttpMessageConverter`. `MultipartFile` receives the file content; the JSON metadata part can be deserialized into a separate DTO.

```java
@RestController
@RequestMapping("/api/documents")
class DocumentController {

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    DocumentResponse upload(
        @RequestPart("file") MultipartFile file,
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestParam(value = "labels", required = false) List<String> labels
    ) {
        return documentService.store(file, metadata, labels);
    }
}
```

`@RequestPart("metadata")` lets Spring select a converter matching the part's media type to turn JSON into `DocumentMetadata`. `@RequestPart("file")` receives the file as `MultipartFile`. `@RequestParam("labels")` fits repeated form fields with the same name and can bind them into `List<String>`.

If metadata is sent as JSON, the client must set `Content-Type: application/json` on the metadata part. If sent as `text/plain`, Spring may fail to find a JSON converter or fail to deserialize into the DTO.

Spring's `consumes = multipart/form-data` determines the media type of the entire request. The Encoding Object in OpenAPI describes the media type and serialization of each property. These two parts must align, though they perform different roles.

## 7. Adding the Encoding Object with Swagger annotations

Swagger Core provides the `@Encoding` annotation, placed inside the `encoding` attribute of `@Content`. This annotation lets you describe `contentType`, `headers`, `style`, `explode`, and `allowReserved` for each property.

Example:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Encoding;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.headers.Header;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Operation(
    summary = "Upload document",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = DocumentUploadSchema.class),
            encoding = {
                @Encoding(
                    name = "file",
                    contentType = "application/pdf",
                    headers = @Header(
                        name = "X-Checksum-SHA256",
                        description = "SHA-256 of the file",
                        schema = @Schema(type = "string")
                    )
                ),
                @Encoding(
                    name = "metadata",
                    contentType = MediaType.APPLICATION_JSON_VALUE
                ),
                @Encoding(
                    name = "labels",
                    style = "form",
                    explode = true
                )
            }
        )
    )
)
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
DocumentResponse upload(
    @RequestPart("file") MultipartFile file,
    @Valid @RequestPart("metadata") DocumentMetadata metadata,
    @RequestParam(value = "labels", required = false) List<String> labels
) {
    return documentService.store(file, metadata, labels);
}
```

The example uses `jakarta.validation.Valid`, suitable for Spring Boot 3 and above; Spring Boot 2 projects use the corresponding `javax.validation.Valid` package.

In this example, `DocumentUploadSchema` is the type used to describe the body structure in OpenAPI. You can define this schema separately with a binary `file` property, `metadata` as `DocumentMetadata`, and `labels` as a list of strings. The controller still binds parts into separate parameters using `@RequestPart`.

Example schema dedicated to documentation:

```java
public class DocumentUploadSchema {
    @Schema(type = "string", format = "binary", description = "PDF file")
    private MultipartFile file;

    private DocumentMetadata metadata;

    private List<String> labels;
}
```

The `@Encoding` annotation does not itself alter how Spring reads parts. It only tells clients how to transmit each part. Runtime behavior still depends on `@RequestPart`, converters, the multipart resolver, and file-handling logic.

## 8. `application/x-www-form-urlencoded` and the Encoding Object

The Encoding Object can also describe how properties of `application/x-www-form-urlencoded` are serialized. This body type is not split into MIME parts like multipart; fields are sent as an encoded key-value string in a form body.

Example schema:

```yaml
requestBody:
  required: true
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        properties:
          username:
            type: string
          roles:
            type: array
            items:
              type: string
          address:
            type: object
            properties:
              city:
                type: string
              postalCode:
                type: string
      encoding:
        roles:
          style: form
          explode: true
        address:
          style: deepObject
          explode: true
```

For `roles`, `form` and `explode: true` allow repeating the key to represent multiple values. For the `address` object, `deepObject` represents nested properties using bracketed keys such as `address[city]=...`, if both client and server support this convention.

Do not use `headers` to describe URL-encoded form fields, because those fields are not separate MIME parts with headers. `allowReserved` can adjust encoding of reserved characters in form values; consider carefully so it does not interfere with how parsers split keys and values.

## 9. Default rules and common misconceptions

Several rules help read and write Encoding Objects accurately:

| Case | How to interpret |
|---|---|
| No `encoding` for a property | Uses OpenAPI's default encoding rules based on schema and media type |
| Property is `string` with `format: binary` | Default media type is typically `application/octet-stream` |
| Property is an object | Default media type is typically `application/json` |
| Property is primitive or array of primitives | Default media type is typically `text/plain` |
| `style` is omitted | Defaults to `form` |
| `explode` is omitted and style is `form` | Defaults to `true` |
| `explode` is omitted and style is not `form` | Defaults to `false` |
| `allowReserved` is omitted | Defaults to `false` |
| `Content-Type` placed in `encoding.headers` | Ignored; use `encoding.contentType` |

Do not confuse `encoding` with `schema`:

- `schema` answers: which properties exist, what data types they have, and whether they are required?
- `encoding` answers: how is each property serialized into request content?

Do not confuse the request's media type with a part's media type:

- `content.multipart/form-data` is the overall request format.
- `encoding.file.contentType` is the format of the `file` part.
- `encoding.metadata.contentType` is the format of the `metadata` part.

Do not declare `encoding` for a property that does not exist in the schema. Keys in `encoding` must match property names defined in that media type's schema.

## 10. Limitations and tool compatibility

The Encoding Object is part of the OpenAPI contract, yet UI and code generator support can vary. Some tools render file uploads without letting users pick a per-part media type; some generators may ignore `headers`, `style`, or `explode` when generating clients.

When using OpenAPI 3.0.x or 3.1.x, check the versions of Swagger UI, springdoc-openapi, and code generators in use. Files are commonly represented with `type: string`, `format: binary`, though binary schema handling can differ across tools and specification versions.

The Encoding Object does not validate file contents, check actual byte MIME types, or replace upload security checks. Applications must still verify extensions, sizes, content signatures, checksums if applicable, access rights, and storage policies. Client-sent `contentType` values are spoofable metadata; the server should inspect actual contents per business requirements.

## 11. Verifying the Encoding Object in docs and real requests

Once the application starts, fetch `/v3/api-docs` or `/v3/api-docs.yaml` and inspect the upload operation:

1. Does the request body have the overall media type `multipart/form-data`?
2. Does the schema include `file`, `metadata`, `labels`, and `required` constraints?
3. Does `encoding.file.contentType` match accepted file types?
4. Is `encoding.metadata.contentType` set to `application/json` if the server deserializes metadata into a DTO?
5. Do `encoding.labels.style` and `explode` match how the server binds lists?
6. Are headers under `encoding.<property>.headers` truly per-part headers?
7. Do Swagger UI and client generators display/send each part according to the contract?

Then send real requests using curl or Postman. Observe the multipart request to verify the boundary, part names, `Content-Disposition`, per-part `Content-Type`, and repetition of array fields. If the docs are right but server binding fails, inspect `@RequestPart`, converters, and multipart configuration. If the server works properly but docs lack encoding details, add `@Encoding` or customize OpenAPI.

## 12. Common errors and fixes

| Symptom | Possible cause | Fix |
|---|---|---|
| JSON metadata fails to deserialize into DTO | Metadata part sent as `text/plain` or missing proper Content-Type | Set `Content-Type: application/json` on the part and declare `encoding.metadata.contentType` |
| File renders as a plain string in Swagger UI | File schema lacks `format: binary` or tool does not support the representation used | Inspect schema and Swagger UI/code generator versions |
| Server cannot split multipart request | Client manually set Content-Type without boundary | Let the client generate the boundary automatically |
| List receives only one value | Client sent a combined string while server expects multiple parts, or `explode` mismatches | Align `style`, `explode`, and repeated field transmission |
| Checksum header never reaches server | Header declared at request level instead of part encoding, or client does not support part headers | Inspect per-part headers and client capabilities |
| Changing `encoding.contentType` leaves runtime still accepting wrong format | Encoding only changes documentation | Adjust how clients send parts and configure converters/server |
| Swagger UI renders properly yet upload is rejected | Server validation or file checks reject content | Check logs, MIME detection, size, checksum, and business rules |

## 13. Workflow for designing multi-part request bodies

When designing an endpoint receiving multipart or URL-encoded forms, follow this sequence:

1. Identify the overall media type of the request body.
2. Design the object schema with stable property names, data types, and required fields.
3. For multipart, explicitly specify `contentType` for files and complex objects where needed.
4. Use `headers` to describe custom part headers, not as a substitute for `contentType`.
5. Choose `style` and `explode` matching how clients send arrays/objects and how Spring binds data.
6. For URL-encoded forms, consider `allowReserved` and how nested objects are serialized.
7. Map each part to `MultipartFile`, `@RequestPart`, or appropriate form parameters in Spring.
8. Inspect OpenAPI JSON/YAML, Swagger UI, real requests, and code generator behavior.

The Encoding Object lets the OpenAPI contract specify precisely how each form field is transmitted over HTTP. Combining schemas, per-part media types, and Spring Boot binding helps clients send accurate payloads while ensuring the server receives data matching the published structure.

## 14. References

- [OpenAPI Specification – Encoding Object](https://spec.openapis.org/oas/latest.html#encoding-object): `contentType`, `headers`, `style`, `explode`, and `allowReserved` properties.
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object): `schema`, `example`, `examples`, and `encoding`.
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object): describing request bodies and media types.
- [Spring Framework: Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): how Spring MVC receives multipart requests.
- [Spring Framework: @RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): binding individual parts of a multipart request.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): `@Content`, `@Encoding`, and schema annotations for OpenAPI docs.
- [Springdoc OpenAPI](https://springdoc.org/): generating and customizing OpenAPI documentation from Spring Boot controllers.
