# Describing Multiple Success Responses with Different Content

An HTTP operation can return multiple types of success responses depending on the processing state or the format requested by the client. For example, a report-generation command might return `200 OK` with the result if generated immediately, or `202 Accepted` with job details if background processing is needed. A content-download endpoint might return the same `200 OK` status, but with a JSON or PDF body depending on the `Accept` header.

OpenAPI represents these cases under `responses`: each status code is a separate response; inside a response, `content` maps each media type to its corresponding schema. With springdoc-openapi, you can describe these responses using `@ApiResponses`, `@ApiResponse`, `@Content`, `@Schema`, and `@Header`.

Annotations only describe the contract. The controller still has to return the right status, headers, media type, and body at runtime. Therefore, after declaring multiple responses, inspect both `/v3/api-docs` and the actual execution branches of the endpoint.

## 1. An Operation Can Have Multiple Success Responses

An HTTP status code indicates the protocol-level processing outcome. The 2xx codes do not all imply the same body type:

| Status | Common meaning | Possible body |
|---|---|---|
| `200 OK` | Request processed successfully | Result DTO, list, or file content. |
| `201 Created` | Resource created | Newly created resource DTO; often accompanied by `Location`. |
| `202 Accepted` | Accepted, processing not yet complete | DTO describing the job, status, or tracking URL. |
| `204 No Content` | Succeeded without returning a representation | No response body. |

Do not declare every 2xx code merely because it exists in HTTP. Only describe statuses that the endpoint can actually return. For example, a delete operation can return `204`; a create operation can return `201`; a background task can return `202`.

OpenAPI allows an operation to declare multiple response codes. Each response code has its own description, headers, and content. Clients can rely on the status to select the schema and next handling steps.

## 2. Declaring Multiple Status Codes with `@ApiResponses`

Suppose a report-generation API has two processing paths:

- If the report is generated immediately, return `200 OK` with `ReportResponse`.
- If background execution is required, return `202 Accepted` with `ReportJobResponse` so the client can track progress.

Two DTOs:

```java
public record ReportResponse(
        UUID reportId,
        String downloadUrl,
        Instant generatedAt
) {}

public record ReportJobResponse(
        UUID jobId,
        String status,
        String statusUrl
) {}
```

The controller can describe each response explicitly:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @PostMapping("/api/reports")
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Report generated immediately",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ReportResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "202",
            description = "Request accepted; the report will be generated in the background",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ReportJobResponse.class)
            )
        )
    })
    ResponseEntity<?> createReport(@RequestBody CreateReportRequest request) {
        if (reportService.canGenerateImmediately(request)) {
            ReportResponse result = reportService.generate(request);
            return ResponseEntity.ok(result);
        }

        ReportJobResponse job = reportService.enqueue(request);
        return ResponseEntity.accepted().body(job);
    }
}
```

In the example:

- `@ApiResponses` groups the operation's responses.
- Each `@ApiResponse` declares a status code and description.
- `@Content` specifies the body's media type.
- `@Schema(implementation = ...)` points to the DTO corresponding to that response.
- `ResponseEntity<?>` lets the method return different body types; `ResponseEntity` determines the actual status on each branch.

If a method always returns one fixed response type, do not use a wildcard just to enrich documentation. Use a concrete return type and describe only the statuses that can actually occur.

### 2.1. Distinguishing Inferred Return Types from Explicitly Declared Responses

Springdoc normally infers the default success response from the controller's return type. For example, a method returning `ReportResponse` can produce a `200` response with the `ReportResponse` schema without redeclaring everything.

When a method has multiple statuses or different bodies, the Java return type may not express the entire contract. In that case, declaring `@ApiResponses` with `responseCode`, `content`, and `schema` clarifies each branch.

If you combine inference with annotations, inspect the final document to avoid duplicate responses, unintended default schemas, or misdescribed response codes. How annotations and return types merge can depend on the springdoc/Swagger Core version.

## 3. One Status Code with Multiple Media Types

Many cases do not require multiple status codes. The same `200 OK` response can have different representations based on the `Accept` header:

- `application/json`: returns metadata or structured content.
- `application/pdf`: returns binary PDF data.

In OpenAPI, this is **one response code** with multiple entries under `content`. Do not create two separate `200` responses just because there are two media types.

Declaration example:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import java.util.UUID;

@GetMapping(
    path = "/api/reports/{id}/content",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_PDF_VALUE
    }
)
@ApiResponse(
    responseCode = "200",
    description = "Report content in the format accepted by the client",
    content = {
        @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ReportMetadata.class)
        ),
        @Content(
            mediaType = MediaType.APPLICATION_PDF_VALUE,
            schema = @Schema(type = "string", format = "binary")
        )
    }
)
ResponseEntity<?> getReportContent(@PathVariable UUID id,
                                   @RequestHeader(HttpHeaders.ACCEPT) String accept) {
    if (accept.contains(MediaType.APPLICATION_PDF_VALUE)) {
        byte[] pdf = reportService.renderPdf(id);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=report.pdf")
                .body(pdf);
    }

    ReportMetadata metadata = reportService.getMetadata(id);
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(metadata);
}
```

`produces` declares the media types that the handler can produce. `@Content` describes the corresponding schema for each media type. For PDF, the `string` schema with `format: binary` represents file content.

In a real application, use Spring's content negotiation and handle `Accept` according to media-type rules instead of simple substring matching as in the condensed example above. Spring can return `406 Not Acceptable` if the client requests an unsupported format.

### 3.1. Corresponding OpenAPI Shape

The response section in the document has a structure like this:

```yaml
responses:
  '200':
    description: Report content in the format accepted by the client
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ReportMetadata'
      application/pdf:
        schema:
          type: string
          format: binary
```

Clients send `Accept: application/json` to receive JSON or `Accept: application/pdf` to receive PDF. Each media type's schema tells the client how to read the body after receiving the response.

## 4. Combining Multiple Status Codes and Multiple Media Types

An operation can vary along both dimensions:

- `200`: synchronous success, supporting JSON or PDF.
- `202`: job accepted, returning JSON with job information.

OpenAPI structure example:

```yaml
responses:
  '200':
    description: Report ready
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ReportMetadata'
      application/pdf:
        schema:
          type: string
          format: binary
  '202':
    description: Report is being generated
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ReportJobResponse'
```

The corresponding annotations can group both response codes inside the same `@ApiResponses`; the `200` response contains two `@Content` entries, while the `202` response contains one `@Content`:

```java
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Report ready",
        content = {
            @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ReportMetadata.class)
            ),
            @Content(
                mediaType = "application/pdf",
                schema = @Schema(type = "string", format = "binary")
            )
        }
    ),
    @ApiResponse(
        responseCode = "202",
        description = "Report is being generated",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ReportJobResponse.class)
        )
    )
})
```

This organization helps clients separate two independent decisions: status indicates processing progress, while media type indicates the representation of the response body.

## 5. Describing `201 Created` Responses and the `Location` Header

When creating a new resource, `201 Created` is usually the appropriate status. The response can contain the resource DTO and a `Location` header pointing to the URI of the newly created resource.

```java
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import java.net.URI;
import java.util.UUID;

@PostMapping("/api/documents")
@ApiResponse(
    responseCode = "201",
    description = "Document created",
    headers = @Header(
        name = HttpHeaders.LOCATION,
        description = "URI of the new document",
        schema = @Schema(type = "string", format = "uri")
    ),
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = DocumentResponse.class)
    )
)
ResponseEntity<DocumentResponse> createDocument(
        @RequestBody CreateDocumentRequest request) {
    DocumentResponse created = documentService.create(request);
    URI location = URI.create("/api/documents/" + created.id());
    return ResponseEntity.created(location).body(created);
}
```

`ResponseEntity.created(location)` produces status `201` and the `Location` header. The `@Header` annotation only describes the header in OpenAPI; the method must still return the actual header.

If the API only returns `201` with the resource body, do not declare an extra `200` simply because springdoc commonly infers a default status. Describe the actual status that clients will receive.

## 6. Describing `204 No Content`

`204 No Content` indicates that the operation succeeded without a response body. Do not attach a JSON schema to this response:

```java
@DeleteMapping("/api/documents/{id}")
@ApiResponse(
    responseCode = "204",
    description = "Document deleted",
    content = @Content
)
ResponseEntity<Void> deleteDocument(@PathVariable UUID id) {
    documentService.delete(id);
    return ResponseEntity.noContent().build();
}
```

`ResponseEntity<Void>` expresses that the method returns no body. `content = @Content` clarifies in the documentation that the response has no representation. Do not declare `application/json` with a `schema` for a `204` response.

Some methods may return `200` with a status body instead of `204`. Choose a consistent contract; clients need to know whether there is a body to parse.

## 7. Describing List, Wrapper, or Binary Responses

### 7.1. Array Responses

If the response is a list, the schema can be an array of a DTO:

```java
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@ApiResponse(
    responseCode = "200",
    description = "Document list",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = DocumentResponse.class)
        )
    )
)
```

For a method returning `List<DocumentResponse>`, springdoc can usually infer the array schema from the generic type. Declare `@ArraySchema` explicitly when you need control over the docs or when the Java return type is overly general.

### 7.2. Paginated Wrapper Responses

If the application returns `PageResponse<DocumentResponse>`, describe both the wrapper and the concrete element type. Avoid using raw `Page` or `Object` if consumers need to know the structure of `items`, `page`, `size`, and `totalElements`.

```java
public record PageResponse<T>(
        List<T> items,
        int page,
        int size,
        long totalElements
) {}
```

With complex generics, you can use `@Schema(implementation = ...)` on the response or define a concrete DTO such as `DocumentPageResponse`. Concrete schemas help client generators produce more stable models.

### 7.3. File Responses

File downloads are usually described using a specific media type and a binary schema:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@ApiResponse(
    responseCode = "200",
    description = "PDF file generated",
    content = @Content(
        mediaType = "application/pdf",
        schema = @Schema(type = "string", format = "binary")
    )
)
```

When returning a file, check `Content-Type` and `Content-Disposition` at runtime. If you need to document `Content-Disposition`, declare the response header with `@Header`.

## 8. Describing Examples for Each Response

When two responses have different schemas, examples help users understand each concrete structure. You can use `@ExampleObject` inside `@Content`:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@ApiResponse(
    responseCode = "202",
    description = "Report generation request accepted",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ReportJobResponse.class),
        examples = @ExampleObject(
            name = "reportQueued",
            summary = "Job pending processing",
            value = """
                {
                  "jobId": "b9a8d0c2-4b42-4ad1-91f5-6a6d8d8e1001",
                  "status": "QUEUED",
                  "statusUrl": "/api/report-jobs/b9a8d0c2-4b42-4ad1-91f5-6a6d8d8e1001"
                }
                """
        )
    )
)
```

Examples must match the schema and runtime JSON. Do not put placeholder values such as tokens, real IDs, or sensitive data into public documentation.

## 9. Separating Response Documentation from Runtime Logic

The `@ApiResponse` and `@ApiResponses` annotations do not control the status code Spring returns. They only generate OpenAPI metadata.

To execute multiple responses, the controller must return the right result. Common options:

| Implementation approach | When appropriate |
|---|---|
| `ResponseEntity<T>` | Need to control status, headers, and body per branch. |
| `ResponseEntity<?>` or `ResponseEntity<Object>` | One method genuinely returns different body types depending on conditions. |
| `@ResponseStatus` | Fixed status for a method or exception handler. |
| `ResponseEntity<Void>` | Response without a body, such as `204`. |
| `HttpMessageConverter`/content negotiation | Select representation based on media types accepted by the client. |

If the controller always returns `ReportResponse` while OpenAPI declares `202 ReportJobResponse`, the documentation fails to reflect runtime. Conversely, if the method returns `ResponseEntity<?>`, springdoc cannot always infer every body type from the generic wildcard; declare schemas explicitly.

### 9.1. `produces` and `@Content` Must Be Consistent

`produces` on `@GetMapping` or `@RequestMapping` is a media-type mapping condition. `@Content(mediaType = ...)` describes the representation in documentation. Both must be compatible:

- If OpenAPI describes `application/pdf`, the handler must be able to return PDF with `Content-Type: application/pdf`.
- If the handler only sets `produces = application/json`, do not also describe `application/pdf` in `@Content`.
- If both JSON and PDF are supported, declare both in `produces` and `content`.
- If the client requests an unsupported media type, `406 Not Acceptable` may be returned; consider documenting that error response if it is public behavior that needs docs.

## 10. Inspecting the Generated OpenAPI Document

After adding annotations, open `/v3/api-docs` or your configured path. Locate the operation and check:

1. Each status code appears once in `responses`.
2. Each response's description matches the meaning of its status.
3. Each response's schema matches the DTO or runtime representation.
4. Media types appear under the right response code.
5. Binary responses use an appropriate schema, such as `string`/`binary`.
6. Bodyless responses such as `204` have no content.
7. Headers such as `Location` or `Content-Disposition` are documented if clients need them.
8. No duplicate or misinferred default responses remain.

Condensed OpenAPI JSON example:

```json
{
  "responses": {
    "200": {
      "description": "Report generated immediately",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ReportResponse"
          }
        }
      }
    },
    "202": {
      "description": "Report will be generated in the background",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ReportJobResponse"
          }
        }
      }
    }
  }
}
```

Component names can vary depending on `@Schema(name = ...)` and model configuration. Verify that `$ref` points to an actually existing component.

## 11. Testing All Response Branches at Runtime

The OpenAPI document does not prove that every controller branch works. Write integration tests for each important status and body.

Example with MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsImmediateReportWhenGenerationIsFast() throws Exception {
        mockMvc.perform(post("/api/reports")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                { "reportType": "SUMMARY", "async": false }
                                """))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.reportId").exists());
    }

    @Test
    void returnsJobWhenGenerationIsQueued() throws Exception {
        mockMvc.perform(post("/api/reports")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                { "reportType": "FULL", "async": true }
                                """))
                .andExpect(status().isAccepted())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.jobId").exists())
                .andExpect(jsonPath("$.status").value("QUEUED"));
    }
}
```

Sample requests should be adjusted to match your application's actual DTOs and logic. If using a mock service, configure each branch clearly so tests verify the exact status and body schema.

For content-negotiation endpoints, send `Accept: application/json` and `Accept: application/pdf` separately, then check `Content-Type` and body. For `204`, check the status and confirm the body is empty.

## 12. Common Pitfalls

- **Declaring multiple `@ApiResponse` annotations with the same response code to describe multiple media types**: one status should have one response object; place multiple `@Content` entries inside that response.
- **Using multiple statuses with the same schema due to default copying**: specify `schema = @Schema(implementation = ...)` for each response when bodies differ.
- **Relying on `ResponseEntity<?>` for springdoc to guess every body**: wildcards cannot convey full type details; declare schemas explicitly.
- **Documenting `204` with a JSON body**: `204 No Content` has no response body.
- **Declaring `application/pdf` while runtime returns JSON**: align `produces`, `Content-Type`, and body.
- **Adding annotations without updating the controller**: OpenAPI does not make a method automatically return `201`, `202`, or `204`.
- **Forgetting to document the `Location` header**: clients may need the new resource's URI after `201`.
- **Forgetting to check default responses inferred by springdoc**: inspect the final JSON to catch extra schemas or statuses.
- **Checking only Swagger UI**: inspect `/v3/api-docs` and run HTTP runtime tests.

## 13. Workflow for Designing Multiple Success Responses

1. **List processing branches**: identify the status codes that can actually be returned.
2. **Determine the body for each status**: DTO, array, wrapper, binary, or no body.
3. **Determine media types**: if the same status has multiple representations, list each media type in `content`.
4. **Declare annotations**: use `@ApiResponses` with one `@ApiResponse` per status code; use multiple `@Content` entries when one response has multiple media types.
5. **Document headers and examples**: add `@Header` or `@ExampleObject` where needed.
6. **Implement the controller**: use `ResponseEntity` or an appropriate mechanism to return the right status, headers, and body.
7. **Inspect `/v3/api-docs`**: confirm statuses, schemas, media types, and headers.
8. **Run runtime tests**: cover every status branch and every supported format.

## 14. Review Checklist

- [ ] Each status code describes an actual outcome of the operation.
- [ ] Each response has a clear description.
- [ ] Schemas are declared accurately for each status's body.
- [ ] One status with multiple media types is documented with multiple `@Content` entries in the same `@ApiResponse`.
- [ ] `produces` matches the published media types.
- [ ] Binary responses have an appropriate schema and return the right content type at runtime.
- [ ] `201` responses include `Location` if required by the contract.
- [ ] `204` responses have no body/content.
- [ ] Wildcard/generic responses have explicit schemas where needed.
- [ ] `/v3/api-docs` has no duplicate or misinferred responses.
- [ ] Integration tests verify status, content type, headers, and body for each branch.

## 15. References

- [OpenAPI Specification 3.1.2 – Responses Object](https://spec.openapis.org/oas/v3.1.2.html#responses-object)
- [OpenAPI Specification 3.1.2 – Response Object](https://spec.openapis.org/oas/v3.1.2.html#response-object)
- [OpenAPI Specification 3.1.2 – Media Type Object](https://spec.openapis.org/oas/v3.1.2.html#media-type-object)
- [Swagger Annotations – `@ApiResponse`](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/responses/ApiResponse.html)
- [Swagger Annotations – `@Content`](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/media/Content.html)
- [Spring Framework – ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [springdoc-openapi documentation](https://springdoc.org/)

An operation can have multiple success outcomes, but each status and representation must reflect actual HTTP behavior. Use one `@ApiResponse` per status code, multiple `@Content` entries when that response supports multiple media types, and test all controller branches so OpenAPI, Swagger UI, and integrating clients share the same contract.
