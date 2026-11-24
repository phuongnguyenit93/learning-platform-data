# Validation for Structured Data Parts in Spring WebFlux Multipart Requests

## 1. Goal: Validating the Metadata Part in a Multipart Request

A `multipart/form-data` request typically contains multiple parts with different roles and formats. For example, a document upload API might receive:

- `metadata`: JSON describing the title, document category, revision, and business details.
- `file`: binary file content.
- `description`: an additional text field.
- `tags`: one or more repeated values.

When handling this request, three tasks should be separated:

1. **Multipart parsing**: reading boundaries, headers, and the content of each part.
2. **Decoding/binding**: converting part content into appropriate Java types, such as JSON into `UploadMetadata`, text into `String`, and files into `FilePart`.
3. **Validation**: checking whether the created DTO satisfies constraints like `@NotBlank`, `@Size`, `@Pattern`, and `@Valid`; then checking file rules and business rules.

Spring WebFlux supports `@RequestPart` to read an individual part. When a part contains JSON, declare the target type as a DTO so Spring uses the `HttpMessageReader` matching that part's `Content-Type`. You can combine `@RequestPart` with `jakarta.validation.Valid` or `@Validated` to trigger Bean Validation.

This lesson focuses on annotation-based WebFlux controllers, validating nested JSON parts, distinguishing decode errors from validation errors, binding form command objects containing `FilePart`, choosing between full parsing and streaming with `PartEvent`, resource limits, and testing with `WebTestClient`.

## 2. Multipart Consists of Multiple Parts, Each with Its Own Headers

A multipart request has an outer `Content-Type`, typically `multipart/form-data; boundary=...`. Each inner part has its own `Content-Disposition`, field name, optional filename, and its own `Content-Type`.

Example:

```http
POST /uploads HTTP/1.1
Content-Type: multipart/form-data; boundary=----upload-boundary

------upload-boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Quarterly report",
  "details": {
    "category": "report",
    "revision": 2
  }
}
------upload-boundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

...binary bytes...
------upload-boundary--
```

There are two different formats here:

- The overall request is `multipart/form-data`.
- The `metadata` part is `application/json`.
- The `file` part is `application/pdf`.

Setting `Content-Type: application/json` for the entire request is wrong because the body contains boundaries and multiple parts. The JSON media type must be set on the part that contains JSON.

A multipart request can use `multipart/mixed` or `multipart/related` where appropriate. WebFlux supports these multipart media types; for forms submitted from browsers, `multipart/form-data` is the standard choice.

### Two Types of Data Requiring Different Handling

| Part | Typical Java type | Work required |
|---|---|---|
| JSON metadata | DTO/record, e.g. `UploadMetadata` | Decode JSON then run Bean Validation |
| Text field | `String` | Decode text and validate length/value |
| File | `FilePart` | Inspect file metadata, stream, or transfer file to storage |
| Part of unknown structure | `Part` | Read headers/content manually when needed |
| Multiple parts with the same name | `List<Part>` or `MultiValueMap` | Handle repeated values |

`FilePart` is not a DTO holding all file bytes. It represents a file part and provides the filename, headers, content stream, and file transfer operations.

## 3. `@RequestPart`: Extracting and Decoding an Individual Part

### 3.1. Getting Raw Parts with `Part` or `FilePart`

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> upload(
        @RequestPart("metadata") Part metadata,
        @RequestPart("file") FilePart file) {

    return Mono.just(
            "metadata=" + metadata.name()
                    + ", file=" + file.filename());
}
```

Use `Part` when you need the raw headers or content of a part. Use `FilePart` when the part has a filename and you need file-specific operations.

The snippet above only demonstrates receiving parts; it does not yet decode JSON metadata into a DTO or validate the content.

### 3.2. Decoding a JSON Part into a DTO

If the `metadata` part contains JSON, you can declare the target type directly:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<UploadReceipt> upload(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") FilePart file) {

    return uploadService.save(metadata, file);
}
```

Spring uses the message reader/codec matching the part's media type to convert JSON into `UploadMetadata`. The part must declare `Content-Type: application/json`, and the body must have a structure compatible with the DTO.

If you use `Part` instead of a DTO, the application has to read and decode the content itself. Declaring a DTO lets Spring handle the HTTP message conversion step.

### 3.3. Using the Reactive Wrapper `Mono<DTO>`

WebFlux also supports:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<UploadReceipt> upload(
        @RequestPart("metadata") Mono<UploadMetadata> metadata,
        @RequestPart("file") FilePart file) {

    return metadata.flatMap(value ->
            uploadService.save(value, file));
}
```

This keeps part decoding inside the reactive pipeline. You can compose validation, service calls, error mapping, and file saving without calling `subscribe()` or `block()`.

For JSON metadata requiring Bean Validation, the common idiom is:

```java
@Valid @RequestPart("metadata") Mono<UploadMetadata> metadata
```

Spring Framework supports `@Valid` with `@RequestPart` for both direct DTOs and async wrappers such as `Mono<DTO>`.

## 4. Defining DTOs and Constraints for Structured Metadata

Suppose metadata requires these conditions:

- `title` is required, cannot be blank whitespace only, and has at most 80 characters.
- `details` is required.
- `details.category` accepts only `invoice`, `report`, or `other`.
- `details.revision` is non-negative.

You can define a record:

```java
public record UploadMetadata(
        @NotBlank
        @Size(max = 80)
        String title,

        @NotNull
        @Valid
        Details details) {

    public record Details(
            @NotBlank
            @Pattern(regexp = "invoice|report|other")
            String category,

            @Min(0)
            int revision) {
    }
}
```

Jakarta Bean Validation annotations:

| Annotation | Role |
|---|---|
| `@NotNull` | Value must not be null |
| `@NotBlank` | String must contain at least one non-whitespace character |
| `@Size(max = 80)` | Limits string length or collection size |
| `@Pattern` | String must match the regular expression |
| `@Min(0)` | Numeric value must be 0 or greater |
| `@Valid` | Cascades validation into nested objects |

### Why Must `@Valid` Be Placed on `details`?

Constraints inside `Details` are not automatically executed just because the parent object has `@Valid`. You must annotate the nested property so the validator descends into that object:

```java
@NotNull
@Valid
Details details
```

`@NotNull` checks that `details` exists; `@Valid` checks the fields inside it. The two annotations have distinct responsibilities.

### `@Valid` Does Not Replace Constraints

`@Valid` only requests cascading validation. If you want `title` to be non-empty, you must use `@NotBlank`. Writing only `@Valid String title` provides no constraints to check on the string.

### Validation Does Not Fix Malformed JSON

Bean Validation only runs after the part has been decoded into an object. If the JSON is missing a brace or has a token that cannot be converted into the target type, the decoder fails before the validator has an object to inspect.

## 5. Enabling Bean Validation on `@RequestPart`

Controller example:

```java
@RestController
@RequestMapping("/uploads")
public class UploadController {

    private final UploadService uploadService;

    public UploadController(UploadService uploadService) {
        this.uploadService = uploadService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<UploadReceipt> upload(
            @Valid @RequestPart("metadata") Mono<UploadMetadata> metadata,
            @RequestPart("file") FilePart file) {

        return metadata.flatMap(value ->
                uploadService.save(value, file));
    }
}
```

For Bean Validation to work, the application needs a Jakarta Bean Validation implementation on the classpath. With Spring Boot, typically add `spring-boot-starter-validation`.

When metadata violates a constraint, WebFlux throws `WebExchangeBindException` and by default returns HTTP 400 Bad Request. The exception holds a `BindingResult` containing field/global errors. With a reactive wrapper, you can use error operators in the pipeline or handle them centrally in `@RestControllerAdvice`.

### Valid Payload Example

```json
{
  "title": "Quarterly report",
  "details": {
    "category": "report",
    "revision": 2
  }
}
```

### Example Payload That Decodes Successfully but Fails Validation

```json
{
  "title": "   ",
  "details": {
    "category": "unknown",
    "revision": -1
  }
}
```

The JSON is valid and can instantiate the record. However:

- `title` violates `@NotBlank`.
- `category` does not match `@Pattern`.
- `revision` is less than 0.

This is a Bean Validation error, not a JSON decoding error.

## 6. Distinguishing Decode Errors, Missing Parts, and Validation Errors

A multipart endpoint can fail at several stages:

```text
Multipart request
      |
      v
Parse boundary and locate parts
      |
      +---- missing required part --------> input error
      |
      v
Read part Content-Type
      |
      +---- no matching reader -----------> media type error
      |
      v
Decode JSON/text into Java type
      |
      +---- malformed JSON/shape ---------> decoding error
      |
      v
Bean Validation on DTO
      |
      +---- constraint violated ----------> validation error
      |
      v
Validate file and business rules
      |
      +---- file/type/policy failed ------> domain/input error
      |
      v
Store or process file
```

| Case | Stage | Typical outcome |
|---|---|---|
| Required `metadata` part missing | Multipart binding | 400 Bad Request |
| Metadata part sends JSON but body has syntax errors | Decode | 400 Bad Request |
| Metadata part has an unsupported media type for the DTO | Message reader selection | 415 Unsupported Media Type |
| JSON decodes cleanly but `title` is blank | Bean Validation | 400 Bad Request |
| JSON decodes cleanly but `details` is null | Bean Validation | 400 Bad Request |
| File part has a media type rejected by API policy | File policy | API-defined status, e.g. 415 |
| File exceeds multipart limit | Multipart parser/resource limit | Depends on reader, server, and exception mapping |
| Syntactically valid SKU or category disallowed by business state | Business validation | Status per API contract |

Do not lump every failure into "metadata invalid". When logging or returning errors, distinguish parsing, binding, constraints, and business rules so callers know what to fix.

### Validation Exceptions in WebFlux

When validating an individual method parameter such as `@Valid @RequestPart("metadata") Mono<UploadMetadata>`, the exception is typically `WebExchangeBindException`.

If method validation applies because constraints are placed directly on method parameters, such as `@Min` or `@NotNull`, Spring may throw `HandlerMethodValidationException` instead. Applications should understand both types if controllers use method validation.

`@Valid` by itself is not a constraint and does not trigger method validation. Constraints like `@NotNull`, `@Min`, and `@NotBlank` are the annotations that define validation conditions.

## 7. Handling Validation Errors with `BindingResult` or Advice

### 7.1. Handling a Form Command Object with `BindingResult`

For browser form uploads, fields can be bound to a command object that also includes a `FilePart`:

```java
public class UploadForm {

    @NotBlank
    @Size(max = 80)
    private String title;

    @NotNull
    private FilePart file;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public FilePart getFile() {
        return file;
    }

    public void setFile(FilePart file) {
        this.file = file;
    }
}
```

The controller can accept `BindingResult` immediately after the object:

```java
@PostMapping(
        path = "/form-upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<ResponseEntity<?>> uploadForm(
        @Valid @ModelAttribute UploadForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(
                ResponseEntity.badRequest().body("Invalid form fields"));
    }

    return uploadService.storeForm(form)
            .thenReturn(ResponseEntity.accepted().build());
}
```

`BindingResult` must immediately follow the bound/validated argument. When errors exist, the controller can check `hasErrors()` and decide the response itself.

This example illustrates data binding for browser forms. For REST requests containing a separate structured JSON part, `@RequestPart` with a DTO is usually clearer.

### 7.2. Standardizing `WebExchangeBindException` with `@RestControllerAdvice`

```java
@RestControllerAdvice
public class MultipartValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ProblemDetail> handle(
            WebExchangeBindException exception) {

        List<Map<String, String>> errors =
                exception.getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "code", error.getCode() == null
                                        ? "invalid"
                                        : error.getCode()))
                        .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Multipart metadata does not satisfy validation rules.");

        problem.setTitle("Invalid multipart metadata");
        problem.setProperty("errors", errors);

        return ResponseEntity.badRequest()
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
```

Required imports include `List`, `Map`, `HttpStatus`, `MediaType`, `ProblemDetail`, `ResponseEntity`, `ExceptionHandler`, `RestControllerAdvice`, and `WebExchangeBindException`.

Example response:

```json
{
  "type": "about:blank",
  "title": "Invalid multipart metadata",
  "status": 400,
  "detail": "Multipart metadata does not satisfy validation rules.",
  "errors": [
    {"field": "title", "code": "NotBlank"},
    {"field": "details.category", "code": "Pattern"}
  ]
}
```

Do not return rejected values or the full body to the client if fields might contain personal data, tokens, or secrets. The field path and error code are usually enough for the UI to highlight what needs to be fixed.

In applications using method validation, also handle `HandlerMethodValidationException`. You can extend `ResponseEntityExceptionHandler` or add a dedicated handler, depending on how you standardize errors.

## 8. Validating the File Part: File Metadata Is Not File Content

Bean Validation on the metadata DTO does not automatically verify file content. For `FilePart`, the application usually needs separate checks:

- Is the part required?
- Is the filename blank?
- Is the declared Content-Type in the allowlist?
- Is the file size within limits?
- Does the actual content match an allowed format?
- Does the file contain malware or unsafe content?

### Both Filename and Content-Type Are Client-Supplied

Do not use the original filename as the storage path:

```java
// Do not use the client's filename as the destination path.
Path destination = uploadDirectory.resolve(file.filename());
```

Filenames can contain directory traversal characters or colliding names. Generate the storage name from a UUID or server-assigned ID, and store the original filename as sanitized metadata if the business logic needs to display it.

Similarly, `Content-Type: application/pdf` does not prove the bytes are actually a PDF. A client can send a forged header. Production systems need to check magic bytes or parse with an appropriate library, and potentially scan for malware before publishing the file.

### File Size

Do not read the entire file into a `byte[]` just to check its size. Enforce limits at the multipart reader, reverse proxy/API gateway, and storage layer; if exact measurement is needed, count bytes while streaming or use trusted metadata from storage.

A part's `Content-Length` may be absent or untrustworthy. Do not rely on it as the sole defense against oversized uploads.

### Part Names and Repeated Parts

If the API only expects a single `file` part, verify the contract and limit the number of parts. If the client sends multiple files with the same name, the API must decide whether to accept one or many. Do not assume `@RequestPart("file") FilePart` represents a contract for multiple repeated files.

## 9. Form Command Object vs. JSON Part: Choosing the Right Binding

WebFlux has two common request styles:

### Browser Form: Binding to a Command Object

A simple form with text fields and a file can bind into a command object:

```java
public class ProfileUploadForm {

    @NotBlank
    private String displayName;

    @NotNull
    private FilePart avatar;

    // getters and setters
}
```

```java
@PostMapping(
        path = "/profile",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<ResponseEntity<?>> updateProfile(
        @Valid @ModelAttribute ProfileUploadForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(ResponseEntity.badRequest().build());
    }

    return profileService.update(form)
            .thenReturn(ResponseEntity.noContent().build());
}
```

Spring binds form fields and the file part into the object. This is convenient for forms with many fields following a command structure.

### REST Multipart: JSON Metadata and File as Two Separate Parts

```java
@PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<ResponseEntity<UploadReceipt>> upload(
        @Valid @RequestPart("metadata") Mono<UploadMetadata> metadata,
        @RequestPart("file") FilePart file) {

    return metadata.flatMap(value ->
            documentService.store(value, file)
                    .map(receipt ->
                            ResponseEntity.accepted().body(receipt)));
}
```

This style fits when metadata has a clear JSON schema and the file is an independent binary part.

### Do Not Confuse `@RequestParam` with Multipart Form Fields in WebFlux

In WebFlux, `@RequestParam` binds URL query parameters. For multipart parts, use `@RequestPart` or bind a command object via `@ModelAttribute`. Do not take the Servlet request parameter model and apply it unchanged to WebFlux.

## 10. Reading the Entire Multipart Request as a `MultiValueMap`

If you need to access parts by name, WebFlux can read the entire multipart request into a `MultiValueMap<String, Part>`:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> inspect(
        @RequestBody Mono<MultiValueMap<String, Part>> parts) {

    return parts.map(map ->
            "part names=" + map.keySet());
}
```

`MultiValueMap` is useful when flexibly handling many part names or repeated parts. However, this approach requires the parser to build a map structure to access parts by name.

`ServerWebExchange.getMultipartData()` also provides `Mono<MultiValueMap<String, Part>>` and caches the parsed result for repeated access within the same exchange. Once multipart data has been parsed this way, the raw request body cannot subsequently be read as an independent stream.

For large files or uploads with many parts, consider streaming rather than collecting the entire multipart body into a map.

## 11. Streaming Multipart with `Flux<PartEvent>`

`PartEvent` enables sequential multipart processing without constructing a `MultiValueMap` holding all parts.

- A form field produces a `FormPartEvent` containing the field value.
- A file upload produces one or more `FilePartEvent` instances.
- Large files can be split across multiple events/buffers.
- The final event of each part has `isLast() == true`.

Model:

```text
Flux<PartEvent>
       |
       v
windowUntil(PartEvent::isLast)
       |
       +---- window for metadata/form field
       |
       +---- window for file part (possibly multiple buffers)
       |
       v
concatMap processes each part
       |
       v
consume / relay / release content buffers
```

Example of identifying part types:

```java
@PostMapping(
        path = "/stream-upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<Void> streamUpload(
        @RequestBody Flux<PartEvent> allEvents) {

    return allEvents
            .windowUntil(PartEvent::isLast)
            .concatMap(partEvents ->
                    partEvents.switchOnFirst((signal, window) -> {
                        if (!signal.hasValue()) {
                            return window.then();
                        }

                        PartEvent first = signal.get();

                        if (first instanceof FormPartEvent form) {
                            String name = form.name();
                            String value = form.value();

                            return validateAndStoreField(name, value)
                                    .then(window.then());
                        }

                        if (first instanceof FilePartEvent file) {
                            Flux<DataBuffer> contents =
                                    window.map(PartEvent::content);

                            return fileStorage.store(
                                    file.filename(), contents);
                        }

                        return Mono.error(
                                new IllegalStateException(
                                        "Unsupported multipart event"));
                    }))
            .then();
}
```

`validateAndStoreField` and `fileStorage.store` are application APIs to implement. The code illustrates the processing structure; in a real implementation, verify how consumers consume each `PartEvent` and buffer in the corresponding window.

**Important rule:** the content of `PartEvent` instances must be completely consumed, relayed elsewhere, or properly released. If file content is ignored or a `DataBuffer` is retained without managing ownership, the application can suffer memory leaks. With pooled buffers, do not release a buffer yourself while downstream still owns it.

### When Should `PartEvent` Be Used?

Use it when:

- Large files need to be written or forwarded as a stream.
- Requests have many parts and you do not want to parse everything into a map.
- Ordering and backpressure across parts need to be controlled.
- Multipart needs to be relayed to another service without aggregating files onto the heap.

For small form uploads or REST requests with one JSON metadata part and one file part, `@RequestPart` is usually easier to read and test.

### Validation in Streaming Differs from `@Valid @RequestPart`

`@Valid @RequestPart Mono<DTO>` lets Spring decode the part into a DTO and run Bean Validation automatically.

With `Flux<PartEvent>`, the application is working at the event/bytes level. There is no DTO metadata automatically bound by Spring annotations per window. If a part is JSON, the application must decode it with bounded size, create the DTO, and invoke the validator or validation service before proceeding.

Do not read an entire file part into a `String` or `byte[]` just to use the same validator. Structural metadata validation and binary file processing should be two separate responsibility flows.

## 12. Multipart and Memory Limits in Spring Boot

Multipart has separate limits from standard body codecs. In Spring Boot WebFlux, common properties live under `spring.webflux.multipart`.

Example:

```properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=20MB
spring.webflux.multipart.max-parts=3
spring.webflux.multipart.max-headers-size=10KB
spring.webflux.multipart.file-storage-directory=/var/app/multipart-tmp
```

Meaning:

| Property | Effect |
|---|---|
| `max-in-memory-size` | Memory limit for non-file parts; for file parts, the threshold before spilling to disk |
| `max-disk-usage-per-part` | Disk space limit for each part saved to disk |
| `max-parts` | Maximum number of parts in one multipart request |
| `max-headers-size` | Maximum memory allocated for headers of each part |
| `file-storage-directory` | Temporary directory for file parts exceeding the memory threshold |

In Spring Boot 3.3, common defaults are 256 KB for `max-in-memory-size` and 10 KB for headers; `max-disk-usage-per-part` and `max-parts` are unlimited (`-1`) by default. Production should configure finite limits according to actual needs.

`file-storage-directory` is a temporary directory for the multipart parser, not a long-term business file store. The application still needs to move valid files to object storage or a managed storage directory.

### Distinguishing Multipart Limits from Codec Limits

There are two configuration layers to distinguish:

1. `spring.webflux.multipart.*` controls parsing and storing multipart parts.
2. `spring.codec.max-in-memory-size` controls the buffer limit of default codecs used to decode/encode bodies, such as a JSON metadata part.

Increasing one limit does not automatically raise the limit at the other layer. If JSON metadata is large, inspect both the multipart part limit and the decoder limit; at the same time, constrain metadata schema and size instead of allowing arbitrary JSON.

### Total Request Limit

`max-in-memory-size` is not the total upload size. It is a per-part limit/buffer threshold. Also configure a total request limit at the reverse proxy, API gateway, or HTTP server suited to your infrastructure. Per-part limits, part count, disk usage, and total request limits protect different resources.

When using `PartEvent` streaming, the `file-storage-directory` of full parsing is not used in the same way; Spring Boot documentation explicitly notes that this setting is ignored for streaming support.

## 13. Errors and Statuses When Multipart Validation Fails

An API can standardize errors with `ProblemDetail`:

| Error | Typically appropriate status | Notes |
|---|---|---|
| Missing required part | 400 | Request does not satisfy the contract |
| Malformed JSON metadata | 400 | Decoder cannot create DTO |
| Metadata violates Bean Validation | 400 | `WebExchangeBindException` |
| Method validation failure | 400 | May be `HandlerMethodValidationException` |
| Unsupported part media type | 415 | No matching reader |
| File type rejected by API policy | 415 or 400 | Choose consistently per contract |
| File exceeds limit | 413 may be appropriate | Check the actual exception and map intentionally |
| Domain rule disallows upload | 409 or 422 | Depends on business semantics |

Do not assume every multipart limit violation automatically becomes HTTP 413. The parser may throw its own exception; the gateway may reject the request before WebFlux receives it. If you want a specific status, identify the actual exception in the version and reader in use and map it explicitly.

With `@Valid @RequestPart`, validation errors include a `BindingResult`; the response body can provide the field path and error code without returning the rejected value. For decode errors, `ServerWebInputException`/exception cause can be used for classification. Never return stack traces or raw multipart bodies.

## 14. Runnable Java 17+ Project: Validating JSON Metadata and Saving File Parts

The example below uses Java 17, Spring Boot 3.3.5, Spring WebFlux, Jakarta Validation, and `WebTestClient`.

The `POST /uploads` endpoint receives:

- `metadata` part: JSON `UploadMetadata`, validated including nested objects.
- `file` part: PDF `FilePart`, checked for filename and declared Content-Type, then saved under a server-generated name.

This sample saves files to a temporary directory so learners can run it standalone. Production applications should use persistent storage, retention policies, malware scanning, and actual file-format verification.

### 14.1. Project Structure

```text
webflux-multipart-validation/
├── pom.xml
└── src/
    ├── main/java/edu/demo/upload/
    │   ├── UploadApplication.java
    │   ├── UploadMetadata.java
    │   ├── UploadReceipt.java
    │   ├── UploadStorage.java
    │   ├── UploadController.java
    │   └── MultipartValidationAdvice.java
    └── test/java/edu/demo/upload/
        └── MultipartValidationTests.java
```

### 14.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-multipart-validation</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 14.3. `UploadApplication.java`

```java
package edu.demo.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UploadApplication {

    public static void main(String[] args) {
        SpringApplication.run(UploadApplication.class, args);
    }
}
```

### 14.4. `UploadMetadata.java`

```java
package edu.demo.upload;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record UploadMetadata(
        @NotBlank
        @Size(max = 80)
        String title,

        @NotNull
        @Valid
        Details details) {

    public record Details(
            @NotBlank
            @Pattern(regexp = "invoice|report|other")
            String category,

            @Min(0)
            int revision) {
    }
}
```

### 14.5. `UploadReceipt.java`

```java
package edu.demo.upload;

public record UploadReceipt(
        String id,
        String title,
        String category) {
}
```

### 14.6. `UploadStorage.java`

```java
package edu.demo.upload;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.http.codec.multipart.FilePart;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
public class UploadStorage {

    private final Path directory = Path.of(
            System.getProperty("java.io.tmpdir"),
            "webflux-multipart-validation-demo");

    public Mono<String> store(FilePart file) {
        return Mono.fromCallable(() -> {
                    Files.createDirectories(directory);
                    return UUID.randomUUID().toString();
                })
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(id -> file.transferTo(
                                directory.resolve(id + ".upload"))
                        .thenReturn(id));
    }
}
```

The directory is created on the bounded elastic scheduler because `Files.createDirectories` is a blocking filesystem operation. `FilePart.transferTo` returns `Mono<Void>` so file writing is composed into the reactive pipeline.

The storage name is generated with a UUID. The client's filename is never used as the destination path.

### 14.7. `UploadController.java`

```java
package edu.demo.upload;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import jakarta.validation.Valid;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/uploads")
public class UploadController {

    private final UploadStorage storage;

    public UploadController(UploadStorage storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<ResponseEntity<UploadReceipt>> upload(
            @Valid @RequestPart("metadata") Mono<UploadMetadata> metadata,
            @RequestPart("file") FilePart file) {

        if (file.filename() == null || file.filename().isBlank()) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "A file name is required."));
        }

        MediaType contentType = file.headers().getContentType();

        if (contentType == null
                || !MediaType.APPLICATION_PDF.isCompatibleWith(contentType)) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "Only PDF uploads are accepted."));
        }

        return metadata.flatMap(value ->
                storage.store(file)
                        .map(id -> ResponseEntity.accepted().body(
                                new UploadReceipt(
                                        id,
                                        value.title(),
                                        value.details().category()))));
    }
}
```

The controller performs three tasks at the HTTP boundary:

1. Accepts the JSON metadata and file part.
2. Quickly validates the file part metadata against the API contract.
3. Waits for metadata to be decoded/validated before invoking storage.

`@Valid` applies to the JSON metadata. If metadata violates constraints, WebFlux throws a validation exception and `storage.store` is never called.

Checking Content-Type here only checks the client-declared header. It does not prove the bytes are truly a PDF; production systems must verify file signatures or parse with a safe library.

### 14.8. `MultipartValidationAdvice.java`

```java
package edu.demo.upload;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;

@RestControllerAdvice
public class MultipartValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ProblemDetail> handle(
            WebExchangeBindException exception) {

        List<Map<String, String>> errors =
                exception.getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "code", error.getCode() == null
                                        ? "invalid"
                                        : error.getCode()))
                        .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Multipart metadata is invalid.");

        problem.setTitle("Invalid multipart metadata");
        problem.setProperty("errors", errors);

        return ResponseEntity.badRequest()
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
```

The advice builds an error response with the field path and code. It does not include rejected values in the response.

### 14.9. `MultipartValidationTests.java`

```java
package edu.demo.upload;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.util.MultiValueMap;
import org.springframework.http.HttpEntity;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class MultipartValidationTests {

    @Autowired
    WebTestClient client;

    @Test
    void validJsonMetadataAndPdfPartAreAccepted() {
        UploadMetadata metadata = new UploadMetadata(
                "Quarterly report",
                new UploadMetadata.Details("report", 2));

        client.post()
                .uri("/uploads")
                .body(BodyInserters.fromMultipartData(
                        parts(metadata, MediaType.APPLICATION_PDF)))
                .exchange()
                .expectStatus().isAccepted()
                .expectBody()
                .jsonPath("$.id").exists()
                .jsonPath("$.title").isEqualTo("Quarterly report")
                .jsonPath("$.category").isEqualTo("report");
    }

    @Test
    void beanValidationRejectsInvalidNestedMetadata() {
        UploadMetadata metadata = new UploadMetadata(
                " ",
                new UploadMetadata.Details("unknown", -1));

        client.post()
                .uri("/uploads")
                .body(BodyInserters.fromMultipartData(
                        parts(metadata, MediaType.APPLICATION_PDF)))
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("Invalid multipart metadata")
                .jsonPath("$.errors").isArray();
    }

    @Test
    void malformedJsonMetadataReturns400() {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();

        builder.part("metadata", "{\"title\":")
                .contentType(MediaType.APPLICATION_JSON);

        addPdfPart(builder);

        client.post()
                .uri("/uploads")
                .body(BodyInserters.fromMultipartData(builder.build()))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void unsupportedFileMediaTypeReturns415() {
        UploadMetadata metadata = new UploadMetadata(
                "Quarterly report",
                new UploadMetadata.Details("report", 2));

        client.post()
                .uri("/uploads")
                .body(BodyInserters.fromMultipartData(
                        parts(metadata, MediaType.TEXT_PLAIN)))
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    void missingRequiredFilePartReturns400() {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();

        builder.part(
                        "metadata",
                        new UploadMetadata(
                                "Quarterly report",
                                new UploadMetadata.Details("report", 2)))
                .contentType(MediaType.APPLICATION_JSON);

        client.post()
                .uri("/uploads")
                .body(BodyInserters.fromMultipartData(builder.build()))
                .exchange()
                .expectStatus().isBadRequest();
    }

    private MultiValueMap<String, HttpEntity<?>> parts(
            UploadMetadata metadata,
            MediaType fileType) {

        MultipartBodyBuilder builder = new MultipartBodyBuilder();

        builder.part("metadata", metadata)
                .contentType(MediaType.APPLICATION_JSON);

        addPdfPart(builder, fileType);

        return builder.build();
    }

    private void addPdfPart(MultipartBodyBuilder builder) {
        addPdfPart(builder, MediaType.APPLICATION_PDF);
    }

    private void addPdfPart(
            MultipartBodyBuilder builder,
            MediaType fileType) {

        ByteArrayResource resource = new ByteArrayResource(
                "sample file bytes".getBytes(StandardCharsets.UTF_8)) {
            @Override
            public String getFilename() {
                return "report.pdf";
            }
        };

        builder.part("file", resource)
                .contentType(fileType);
    }
}
```

The tests use `MultipartBodyBuilder` to construct two separate parts:

- `metadata` is encoded as JSON and has part Content-Type `application/json`.
- `file` is a resource with a filename and declared Content-Type.

The body inserter automatically generates the boundary for the outer multipart request. Do not manually set a `Content-Type: multipart/form-data` header lacking a boundary.

### 14.10. Running the Tests

From the directory containing `pom.xml`:

```bash
mvn test
```

When dependencies download successfully and assertions pass, Maven Surefire runs five tests:

1. Valid JSON metadata and PDF part are accepted.
2. Metadata violating constraints on both top-level fields and nested objects returns 400.
3. Malformed JSON part returns 400 at the decode step.
4. File part with an unaccepted media type returns 415.
5. Missing required file part returns 400.

Expected output:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

This is the expected result after running `mvn test`, not a confirmation that Maven was executed in the authoring environment.

### 14.11. Sending a Multipart Request with curl

```bash
curl -i -X POST "http://localhost:8080/uploads" \
  -F 'metadata={"title":"Quarterly report","details":{"category":"report","revision":2}};type=application/json' \
  -F 'file=@report.pdf;type=application/pdf'
```

`curl -F` automatically generates the boundary for the multipart request and sends a separate Content-Type for each part. Do not set `Content-Type: application/json` for the whole request.

Example success response:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "id": "c6d3...",
  "title": "Quarterly report",
  "category": "report"
}
```

The ID is generated randomly; the actual value changes on each upload.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to fix |
|---|---|---|
| Setting `Content-Type: application/json` for the entire multipart request | Parser cannot read the multipart boundary properly | Outer request uses multipart/form-data; JSON part has its own Content-Type |
| Receiving the JSON part as `Part` and assuming you already have a DTO | Application still holds the raw part | Declare `@RequestPart("metadata") Metadata` or decode explicitly |
| Forgetting `@Valid` on the metadata part | Constraints are not triggered in the argument resolver | Use `@Valid @RequestPart(...)` |
| Forgetting `@Valid` on a nested object | Constraints inside nested objects do not cascade | Place `@Valid` on the nested field/record component |
| Thinking `@Valid` is a constraint | No rules are checked if constraints are missing | Use `@NotBlank`, `@Size`, `@Min`, etc. |
| Confusing decode errors with validation errors | Returns misleading messages to clients | Distinguish JSON parsing, type conversion, and Bean Validation |
| Using `@RequestParam` to read multipart fields like in Servlet | Binding does not follow the WebFlux contract | Use `@RequestPart` or `@ModelAttribute` |
| Reading the file into `byte[]` to save it | Consumes heap proportional to file size | Use `FilePart.transferTo` or streaming |
| Using the client filename as the path | Allows path traversal or file overwrites | Generate storage names from a server UUID/ID |
| Trusting the file's Content-Type | Spoofed MIME files can bypass checks | Check actual signature/content and scan |
| Limiting only `max-in-memory-size` | Large files can still write to disk unbounded | Set `max-disk-usage-per-part`, `max-parts`, and total request limit |
| Using `MultiValueMap` for large streaming uploads | Parser must build a map of parts | Consider `Flux<PartEvent>` |
| Ignoring PartEvent content | Buffers are not consumed/released | Consume, relay, or release all part content |
| Handling only `WebExchangeBindException` in controllers with method validation | May miss `HandlerMethodValidationException` | Handle both when method validation is used |
| Testing only JSON metadata without the file part | Does not test the real multipart contract | Test metadata, file, media type, and required parts |

## 16. Production Readiness Checklist for Multipart Validation

### Contract and Binding

- Does the outer request have a multipart `Content-Type` with a valid boundary?
- Does every JSON part have Content-Type `application/json`?
- Are part names stable and documented?
- Which parts are required, which are optional, and which can repeat?
- Is a dedicated DTO used for metadata instead of exposing domain entities?
- Do nested objects have `@Valid` to cascade validation?

### Validation and Error Handling

- Is `spring-boot-starter-validation` or a compatible validator present?
- Are JSON decode failures and Bean Validation failures tested separately?
- Are `WebExchangeBindException` and `HandlerMethodValidationException` handled where needed?
- Does the error body include field path and code without exposing sensitive rejected values?
- Does the file policy check filename, media type, size, and signature?

### Resources and Security

- Are memory limits configured for non-file parts?
- Do file parts have disk usage limits?
- Are part count and header size limited?
- Is total request size limited at the gateway/server?
- Are files stored under server-generated names outside the webroot?
- Are antivirus/content scanning and retention/cleanup policies in place?
- Does the streaming path consume/relay/release every DataBuffer?
- Do you avoid loading entire files into the heap or aggregating many concurrent uploads?

### Testing and Operations

- Are there passing tests with metadata + file?
- Are there tests for missing metadata, malformed JSON, and constraint failures?
- Are there tests for missing file part, wrong part media type, and oversized files?
- Is multipart streaming tested if the endpoint uses `PartEvent`?
- Are correlation ID, route, and error category logged without logging files/bodies?
- Are metrics collected for upload size, upload count, validation errors, and storage failures?

## 17. Self-Check Exercises

**Exercise 1.** A multipart request has a `metadata` part containing JSON. Which parameter declaration lets Spring automatically decode it into a DTO?

**Answer:** `@RequestPart("metadata") UploadMetadata metadata` or `@Valid @RequestPart("metadata") Mono<UploadMetadata> metadata` when composing reactively.

**Exercise 2.** Why does a JSON part need its own Content-Type?

**Answer:** The outer request is multipart with a boundary; the message reader chooses the codec for each part based on that part's Content-Type. JSON metadata needs `application/json`.

**Exercise 3.** The JSON is valid, but `title=""` violates `@NotBlank`. What kind of error is this?

**Answer:** A Bean Validation failure. The decoder already constructed the DTO successfully.

**Exercise 4.** Why does `details` need both `@NotNull` and `@Valid`?

**Answer:** `@NotNull` requires the object to exist; `@Valid` cascades validation into the fields inside it.

**Exercise 5.** What exception does `@Valid @RequestPart Mono<Metadata>` typically throw when a constraint is violated?

**Answer:** `WebExchangeBindException`, usually mapped to 400. If method validation applies due to constraints directly on method parameters, it may be `HandlerMethodValidationException`.

**Exercise 6.** Should the original filename be used as the file storage path?

**Answer:** No. The filename is client-supplied and can contain path traversal or duplicate names. Generate the storage name from a server UUID/ID.

**Exercise 7.** Is `max-in-memory-size` the limit on total upload request size?

**Answer:** No. For multipart, it limits non-file parts and acts as the spill-to-disk threshold for file parts. You must limit disk usage, part count, and total request size at the appropriate layers.

**Exercise 8.** When should `Flux<PartEvent>` be used instead of `@RequestPart`?

**Answer:** When sequential and streaming multipart processing is needed, especially for large files or many parts. The application must consume, relay, or release each part's content.

**Exercise 9.** Does the `Content-Type: application/pdf` header prove the file is truly a PDF?

**Answer:** No. That is client-declared metadata. You must check the actual signature/content or parse with a safe library.

**Exercise 10.** Should 400 be returned for every multipart error?

**Answer:** No. You should distinguish decode errors, validation errors, unsupported media types, size limits, domain policies, and infrastructure errors; the status code must match the cause and API contract.

## 18. Takeaways

- Multipart is a single HTTP body containing multiple parts; each part has its own name, headers, and media type.
- `@RequestPart("metadata") Metadata` tells Spring to decode the part into a DTO; JSON parts need `Content-Type: application/json`.
- `@Valid @RequestPart("metadata") Mono<Metadata>` triggers Bean Validation on the DTO inside the reactive pipeline.
- Nested objects need `@Valid`; constraints like `@NotBlank`, `@Size`, `@Pattern`, and `@Min` define the actual validation rules.
- Validation failures are typically `WebExchangeBindException` and HTTP 400; method validation may use `HandlerMethodValidationException`.
- `FilePart` requires separate checks; metadata Bean Validation does not verify file bytes.
- Client-declared filename and Content-Type must not be trusted to determine storage paths or file authenticity.
- `@ModelAttribute` command objects suit browser forms; `@RequestPart` suits separate JSON and file parts.
- `MultiValueMap<String, Part>` is convenient for full parsing; `Flux<PartEvent>` suits streaming processing.
- `max-in-memory-size`, disk usage, max parts, and total request limits protect different resources.
- Every PartEvent/DataBuffer must be properly consumed, relayed, or released.

When designing a multipart endpoint, check in order: **outer multipart → each part's name and Content-Type → DTO decoding → Bean Validation → file policy → business rules → storage**. Separating each step helps return errors with the exact cause and avoids holding large files on the heap.

## Official Documentation

- Spring Framework 6.2, **WebFlux Multipart Content**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework 6.2, **WebFlux Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2, **WebFlux Reactive Core – Multipart and DataBuffer limits**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2, **Data Buffers and Codecs**: https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html
- Spring Boot 3.3, **Common Application Properties – WebFlux multipart**: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html