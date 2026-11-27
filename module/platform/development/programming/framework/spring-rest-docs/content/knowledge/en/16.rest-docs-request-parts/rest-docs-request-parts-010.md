# Organizing Readable Multipart Snippets

## Learning Objectives

After this lesson, you will be able to:

- Explain the structure of `multipart/form-data` and the role of each part in a request.
- Use Spring REST Docs to document the list of parts with `requestParts(...)` and `partWithName(...)`.
- Document the JSON structure inside a part with `requestPartFields(...)`, and know when to record a part's raw body.
- Design MockMvc documentation tests for file uploads with accompanying metadata.
- Split snippets by responsibility: multipart overview, metadata fields, part content, and HTTP request example.
- Organize document identifiers and Asciidoctor includes so documentation pages are easy to read and maintain.
- Avoid leaking binary files, personal information, or sensitive data into published snippets.

## 1. What Problem Does a Multipart Request Solve?

An API may need to accept multiple types of data in a single HTTP request. For example, creating a user profile might accept an avatar image file, a JSON part containing display name and profile options, and a text part containing notes.

The `multipart/form-data` format divides the request body into multiple independent sections. Each section has its own headers and content; boundaries between parts are defined by the `boundary` in `Content-Type`.

Simplified example request:

```http
POST /api/profiles HTTP/1.1
Content-Type: multipart/form-data; boundary=----profile-boundary
Accept: application/json

------profile-boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"displayName":"Lan","visibility":"PUBLIC"}
------profile-boundary
Content-Disposition: form-data; name="avatar"; filename="avatar.png"
Content-Type: image/png

<binary image bytes>
------profile-boundary--
```

In the example:

| Part | Content-Disposition | Content-Type | Content |
| --- | --- | --- | --- |
| metadata | name="metadata" | application/json | JSON describing the profile |
| avatar | name="avatar", filename="avatar.png" | image/png | Binary file data |

Multipart does not simply mean a single file upload. A request can contain multiple files, text fields, and structured JSON/XML parts. Documentation must state part names, content types, roles, whether each is required, and validation rules for each part.

## 2. Why Organize Separate Snippets for Each Part?

If the entire multipart request is dumped into one long example, readers struggle to see which parts are required, which parts contain files, which part contains JSON fields, which file formats and sizes are supported, or whether an optional part can be omitted.

Spring REST Docs provides dedicated descriptors and snippets:

| API | Purpose |
| --- | --- |
| requestParts(...) | Documents the parts present in the request |
| partWithName(...) | Declares a descriptor for a part by name |
| requestPartFields(...) | Documents fields of a structured part, typically JSON |
| relaxedRequestPartFields(...) | Documents a subset of fields when intentionally skipping full part payload verification |
| requestPartBody(...) | Records the body of a specific part when raw content needs to be illustrated |

Snippets have distinct responsibilities. The request parts table answers which parts the request contains; the part fields table answers which fields exist in the JSON metadata; the body snippet illustrates concrete content when a field table is not enough.

There is no need to put raw binary files into documentation. For file uploads, part name, sample filename, media type, and file rule descriptions are much more useful than raw bytes.

## 3. Describing the Part Overview with `requestParts`

Suppose the profile creation endpoint accepts `metadata` and `avatar` parts. You can declare:

```java
requestParts(
    partWithName("metadata")
        .description("JSON metadata of the profile"),
    partWithName("avatar")
        .description("Profile avatar image; PNG or JPEG format")
)
```

Each descriptor represents a part name. Its description should explain the role and constraints consumers need to know:

- Does the part contain JSON or a file?
- Which media types are supported?
- Is the part required?
- Are there size or count limits?
- When the part is missing or malformed, how does the API respond?

Do not rely on part names to guess media types. Check the actual part's `Content-Type` and document the contract explicitly.

### 3.1. Optional Parts

If `avatar` can be absent, the descriptor can be marked optional:

```java
requestParts(
    partWithName("metadata")
        .description("JSON metadata of the profile"),
    partWithName("avatar")
        .description("Optional avatar image; PNG or JPEG")
        .optional()
)
```

`optional()` documents that a part may be absent in the documented request. It does not automatically configure the controller to accept a missing file, does not skip validation, and does not create a default file. A separate test should send a request containing only `metadata` and verify server behavior.

### 3.2. Strict and Relaxed Behavior

`requestParts(...)` documents the parts sent in the exchange. When using strict documentation, actual parts must be fully documented; a newly introduced part can prevent the test from generating snippets as expected. This is a useful signal when the multipart contract changes.

Do not switch all tests to relaxed just to avoid updating documentation. If the API adds a `signature` part, the team must decide whether consumers must send it and update the descriptors.

## 4. Documenting JSON Fields Inside a Part

Metadata is usually a dedicated JSON part inside multipart. Example:

```json
{
  "displayName": "Lan",
  "visibility": "PUBLIC",
  "notifyByEmail": true
}
```

Use `requestPartFields(...)` to document fields belonging to the `metadata` part:

```java
requestPartFields("metadata",
    fieldWithPath("displayName")
        .description("Profile display name"),
    fieldWithPath("visibility")
        .description("Visibility scope: PUBLIC or PRIVATE"),
    fieldWithPath("notifyByEmail")
        .description("Whether to send email notifications")
)
```

The part name passed to `requestPartFields` is `metadata`; field paths inside are evaluated from the JSON body of that part, without a `metadata.` prefix.

For example, if the JSON part has the structure:

```json
{
  "address": {
    "city": "Da Nang",
    "countryCode": "VN"
  }
}
```

Descriptor paths are `address.city` and `address.countryCode`, not `metadata.address.city`.

### 4.1. Optional Fields in Metadata

If `notifyByEmail` may be absent:

```java
requestPartFields("metadata",
    fieldWithPath("displayName")
        .description("Display name"),
    fieldWithPath("visibility")
        .description("Visibility scope")
        .optional(),
    fieldWithPath("notifyByEmail")
        .description("Whether to send email notifications")
        .optional()
)
```

Optional field and optional part are two different levels:

| Level | Example | Meaning |
| --- | --- | --- |
| Optional part | avatar | The entire part may not appear |
| Optional field | notifyByEmail inside metadata | The metadata part is still present, but this field may be absent |

Do not mark the entire part optional just because one field inside the JSON is optional. Nor should `optional()` replace checking for `null`, empty strings, or default values.

## 5. Complete Example with MockMvc

Suppose the `POST /api/profiles` API accepts `metadata` as a required JSON part and `avatar` as an optional PNG/JPEG file part.

Example test:

```java
@Test
void createsProfileWithAvatar() throws Exception {
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {
              "displayName": "Lan",
              "visibility": "PUBLIC",
              "notifyByEmail": true
            }
            """.getBytes(StandardCharsets.UTF_8)
    );

    MockMultipartFile avatar = new MockMultipartFile(
            "avatar",
            "avatar.png",
            MediaType.IMAGE_PNG_VALUE,
            validPngBytes()
    );

    mockMvc.perform(multipart("/api/profiles")
                    .file(metadata)
                    .file(avatar)
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isCreated())
            .andDo(document("profiles-create",
                    requestParts(
                            partWithName("metadata")
                                    .description("JSON metadata of the profile"),
                            partWithName("avatar")
                                    .description("PNG or JPEG avatar image")
                                    .optional()
                    ),
                    requestPartFields("metadata",
                            fieldWithPath("displayName")
                                    .description("Display name"),
                            fieldWithPath("visibility")
                                    .description("Visibility scope"),
                            fieldWithPath("notifyByEmail")
                                    .description("Whether to send email notifications")
                    )
            ));
}
```

This is a structural example; controller, service, response assertions, and static imports must be declared according to your project. `validPngBytes()` is a fixture helper returning valid PNG content; do not use an arbitrary byte array if the application checks image decoding or file signatures.

Commonly needed imports:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

In addition, `MockMvc`, `MockMultipartFile`, `MediaType`, `StandardCharsets`, `Test`, and the application's response/assertion types are needed.

## 6. Organizing Document Identifiers and Snippet Output

The name in `document(...)` determines the directory storing snippets for the exchange:

```java
document("profiles-create", ...)
```

The output directory typically looks like:

```text
build/generated-snippets/
└── profiles-create/
    ├── curl-request.adoc
    ├── http-request.adoc
    ├── request-parts.adoc
    └── ...
```

Additional snippets produced by `requestPartFields(...)` are placed in the same operation output directory according to the snippet naming rules of your REST Docs version and project configuration. Inspect the `generated-snippets` directory after tests run to verify exact filenames before writing includes; do not guess output filenames from Java method names.

### 6.1. One Document Identifier per Scenario

Use identifiers that express the endpoint and behavior:

| Identifier | Scenario |
| --- | --- |
| profiles-create | Create profile with metadata and avatar |
| profiles-create-without-avatar | Create profile with metadata only |
| profiles-create-invalid-metadata | Malformed JSON metadata or missing field |
| profiles-create-unsupported-avatar | File with unsupported media type |

Stable identifiers help readers and maintainers find the right snippet. Avoid overly generic names such as `upload`, `test1`, or names tied to execution order.

### 6.2. Do Not Write Raw Binary Data as Text Snippets

Do not use raw body snippets to dump large binary content into documentation. For image/PDF files, documentation should describe the part name, sample filename or extension, supported Content-Types, size limits, and content validation rules.

If you need to illustrate a small text part, `requestPartBody(...)` can generate a body snippet for that part. Only use raw part bodies when the content is readable, helpful, and free of sensitive data. For JSON metadata, `requestPartFields(...)` usually produces better-structured documentation.

## 7. When to Use `requestPartBody`?

Some parts are not JSON objects yet still have text-based bodies, such as XML, CSV, manifests, or descriptive text accompanying an upload.

When you need to display the raw content of a part, you can use:

```java
document("imports-create",
    requestParts(
        partWithName("manifest")
            .description("CSV manifest describing import data")
    ),
    requestPartBody("manifest")
)
```

This example fits if `manifest` is short text. If the part is a binary file or lengthy content, avoid dumping the entire body into a snippet; document the part's metadata or provide a sanitized abbreviated example in prose.

## 8. Structuring Asciidoctor So Readers Follow the Right Order

A readable multipart page should flow from overview to detail:

1. Describe the endpoint and upload purpose.
2. Display the list of parts.
3. Document JSON metadata fields.
4. Document the file part: media types, size, and limits.
5. Display sample HTTP request and response.

AsciiDoc example:

```asciidoc
== Create Profile

Endpoint accepts JSON metadata and an optional avatar image.

=== Request parts
include::{snippets}/profiles-create/request-parts.adoc[]

=== Metadata fields
include::{snippets}/profiles-create/metadata-fields.adoc[]

=== HTTP request
include::{snippets}/profiles-create/http-request.adoc[]

=== HTTP response
include::{snippets}/profiles-create/http-response.adoc[]
```

The `metadata-fields.adoc` path above is an illustrative name. Exact snippet names depend on your REST Docs version and snippet naming configuration; check the actual output before including. If the actual output has a different name, use that exact filename.

There is no need to include every generated snippet. Only pull in snippets that help readers understand the contract. Documentation can be split into separate sections to avoid one long page filled with repetitive tables.

## 9. Multipart Part Validation Must Also Be Documented

REST Docs describes the tested request; it does not enforce validation on files or metadata by itself. The application must perform separate checks:

| Item | Example Rule | Recommended Test |
| --- | --- | --- |
| Required part | metadata must be present | Request missing metadata |
| Optional part | avatar may be absent | Request with metadata only |
| Media type | avatar accepts only image/png or image/jpeg | Upload text/plain or application/octet-stream |
| File size | Max 5 MB | Files smaller than, equal to, and exceeding limit |
| Filename | Never use client-sent path as storage path | Filename containing ../ or absolute path |
| File content | Verify signature/content rather than trusting Content-Type alone | Spoofed MIME file or corrupted file |
| Metadata fields | displayName required, visibility in enum | Missing field, invalid enum |
| File count | At most one avatar | Send multiple avatar parts if endpoint does not support them |

Do not document a limit such as 5 MB unless the implementation enforces it and tests verify it. Descriptions must reflect the agreed-upon contract.

### 9.1. Testing Missing Required Part

Example:

```java
@Test
void rejectsMissingMetadataPart() throws Exception {
    mockMvc.perform(multipart("/api/profiles")
                    .file(new MockMultipartFile(
                            "avatar",
                            "avatar.png",
                            MediaType.IMAGE_PNG_VALUE,
                            validPngBytes()
                    )))
            .andExpect(status().isBadRequest());
}
```

Status and error body must match the actual API. If documentation needs to publish the missing-part error, use a separate document identifier and add descriptors for the error response.

### 9.2. Testing Absent Optional Part

```java
@Test
void createsProfileWithoutAvatar() throws Exception {
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"displayName":"Lan","visibility":"PUBLIC"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/profiles")
                    .file(metadata)
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isCreated())
            .andDo(document("profiles-create-without-avatar",
                    requestParts(
                            partWithName("metadata")
                                    .description("JSON metadata of the profile"),
                            partWithName("avatar")
                                    .description("Optional avatar image")
                                    .optional()
                    )
            ));
}
```

This test proves the no-avatar scenario if the controller actually accepts the request. An optional descriptor cannot replace status assertions or response verification.

## 10. Keeping Snippets Maintainable as Multipart Evolves

As the API evolves, parts may be added, removed, or change media types. A few principles keep documentation pages stable:

- Use meaningful part names; avoid cryptic short names like `p1` or `data2`.
- Keep document identifiers tied to behavior rather than test method names.
- Place part descriptors in a centralized location within tests to avoid inconsistent duplicate descriptions.
- Write separate tests for important variants: missing file, malformed file, invalid metadata.
- Use strict descriptors for contract surfaces that need full verification.
- Only use `relaxedRequestPartFields(...)` when a snippet intentionally documents a subset of metadata and the remainder is explained elsewhere.
- Inspect fresh output after upgrading REST Docs versions or changing snippet naming conventions.

If a JSON part has multiple levels, you can use nested field paths or subsection descriptors to partition the documentation surface. Do not dump a large JSON payload into prose while skipping a field table when consumers need to look up individual fields.

## 11. Protecting Data in Multipart Snippets

Multipart requests often carry user data or private files. Use synthetic data reserved strictly for tests:

- Never upload ID photos, real user pictures, or real documents.
- Never use filenames containing real names, emails, or personal identifiers.
- Strip EXIF/geolocation metadata from image fixtures unless testing that metadata specifically.
- Never record PDF/CSV contents containing real data in `requestPartBody`.
- Never put real tokens or cookies into request headers when generating snippets.
- Mask sensitive fields in metadata using preprocessors if they appear in body snippets.

Example test metadata:

```json
{
  "displayName": "Example User",
  "contactEmail": "user@example.test",
  "visibility": "PUBLIC"
}
```

This is example data. If emails, phone numbers, or sensitive info appear in payloads, use dummy fixtures and verify snippets contain no real data.

## 12. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Part missing from request-parts snippet | Part name in descriptor differs from actual multipart name | Compare names in MockMultipartFile and partWithName |
| `requestPartFields` cannot find field | JSON part has wrong structure or wrong path | Inspect serialized part body; paths start from the part root |
| Strict `requestParts` fails when adding a new part | New part is not yet documented | Confirm contract and add descriptor |
| Optional part still causes endpoint error | Application does not yet support absent part | Fix implementation or document exact requirement |
| Metadata snippet mixed with file part | Sharing raw body without splitting by part | Use requestPartFields for JSON and requestParts for overview |
| Raw file bytes appear in artifacts | Recording binary part as a raw snippet | Do not generate body snippets for binary files; document metadata only |
| Asciidoctor include cannot find file | Guessing snippet filename instead of inspecting real output | Check generated-snippets directory and fix include |
| Tests only pass with invalid dummy file | Application does not validate file content or fixture is unrepresentative | Use valid fixtures and test MIME/content/size |

## 13. Checklist for Organizing Multipart Snippets

- [ ] Give each part a clear name.
- [ ] Use `requestParts(...)` to document the list of parts.
- [ ] Use `requestPartFields(...)` for structured JSON parts.
- [ ] Only use `requestPartBody(...)` for short, useful text content.
- [ ] Mark optional at the right level: part or field.
- [ ] Have tests for missing parts, optional parts, and invalid files.
- [ ] Document media type, filename, size, and content rules.
- [ ] Use stable document identifiers by scenario.
- [ ] Inspect actual snippets before writing Asciidoctor includes.
- [ ] Never write binary files or personal data into artifacts.
- [ ] Render documentation and verify every include in CI.

## 14. Practice Exercise

Endpoint `POST /api/documents` accepts:

- `metadata`: JSON containing `title`, `category`, and `tags`.
- `document`: required PDF file.
- `thumbnail`: optional image file.

Complete the following:

1. Write a MockMvc test using three representative `MockMultipartFile` instances.
2. Use `requestParts(...)` to document `metadata`, `document`, and `thumbnail`; mark `thumbnail` optional.
3. Use `requestPartFields("metadata", ...)` to document `title`, `category`, and `tags`.
4. Document MIME type and size limits for PDF/thumbnail in prose cross-checked against real validation.
5. Create tests for missing `document`, absent `thumbnail`, PDF with wrong media type, and `metadata` missing `title`.
6. Generate snippets, verify actual output filenames, and include them in Asciidoctor in the order: overview → metadata → file rules → HTTP exchange.
7. Scan artifacts to ensure no real filenames or real document contents remain.

**Self-Check Question:** Should you use `requestPartBody("document")` to record the full bytes of a PDF in documentation? No. Binary bytes do not help consumers understand the contract and can make artifacts huge or expose sensitive data. Document the part name, media type, sample filename, limits, and validation; only use raw body snippets for short text parts when genuinely useful.

## Conclusion

A readable multipart snippet cleanly separates the part list, metadata structure, and file content. Spring REST Docs provides `requestParts(...)` to document parts, `requestPartFields(...)` to document JSON fields inside a part, and `requestPartBody(...)` for raw bodies where appropriate. Organize document identifiers by scenario, inspect actual output before writing includes, and structure pages from overview to detail. HTTP tests must verify required/optional parts, media types, sizes, and validation; binary files and personal data must be replaced with dummy fixtures. Following these steps ensures multipart documentation both reflects tested requests and stays clear enough for clients to implement uploads.
