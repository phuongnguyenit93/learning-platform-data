# Validation cho phần dữ liệu có cấu trúc trong multipart của Spring WebFlux

## 1. Mục tiêu: validate đúng phần metadata trong một request multipart

Một request `multipart/form-data` thường chứa nhiều phần (part) với vai trò và định dạng khác nhau. Ví dụ một API tải tài liệu có thể nhận:

- `metadata`: JSON mô tả tiêu đề, loại tài liệu, phiên bản và thông tin nghiệp vụ.
- `file`: nội dung file nhị phân.
- `description`: một trường text bổ sung.
- `tags`: một hoặc nhiều giá trị lặp.

Khi xử lý request này, cần tách ba công việc:

1. **Multipart parsing**: đọc boundary, headers và nội dung từng part.
2. **Decoding/binding**: chuyển nội dung part sang kiểu Java phù hợp, chẳng hạn JSON thành `UploadMetadata`, text thành `String`, file thành `FilePart`.
3. **Validation**: kiểm tra DTO đã được tạo có thỏa các constraint như `@NotBlank`, `@Size`, `@Pattern`, `@Valid` hay không; sau đó kiểm tra thêm quy tắc của file và nghiệp vụ.

Spring WebFlux hỗ trợ `@RequestPart` để đọc một part riêng lẻ. Khi part chứa JSON, khai báo kiểu đích là DTO để Spring dùng `HttpMessageReader` tương ứng với `Content-Type` của chính part đó. Có thể kết hợp `@RequestPart` với `jakarta.validation.Valid` hoặc `@Validated` để kích hoạt Bean Validation.

Bài học tập trung vào annotation-based WebFlux controllers, cách validate JSON part lồng nhau, phân biệt lỗi decode với lỗi validation, cách bind form command object có `FilePart`, lựa chọn giữa parsing đầy đủ và streaming bằng `PartEvent`, giới hạn tài nguyên và kiểm thử bằng `WebTestClient`.

## 2. Multipart gồm nhiều part, mỗi part có header riêng

Request multipart có một `Content-Type` bên ngoài, thường là `multipart/form-data; boundary=...`. Mỗi part bên trong lại có `Content-Disposition`, tên field, có thể có filename và `Content-Type` riêng.

Ví dụ:

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

Ở đây có hai định dạng khác nhau:

- Toàn request là `multipart/form-data`.
- Part `metadata` là `application/json`.
- Part `file` là `application/pdf`.

Đặt `Content-Type: application/json` cho toàn request là sai vì body có boundary và nhiều part. JSON media type phải được đặt trên part chứa JSON.

Một multipart request có thể dùng `multipart/mixed` hoặc `multipart/related` trong các trường hợp phù hợp. WebFlux có hỗ trợ các media type multipart này; với form gửi từ trình duyệt, `multipart/form-data` là lựa chọn phổ biến.

### Hai loại dữ liệu cần xử lý khác nhau

| Part | Kiểu Java thường dùng | Công việc |
|---|---|---|
| JSON metadata | DTO/record, ví dụ `UploadMetadata` | Decode JSON rồi Bean Validation |
| Text field | `String` | Decode text và kiểm tra độ dài/giá trị |
| File | `FilePart` | Kiểm tra metadata file, stream hoặc chuyển file sang storage |
| Part chưa biết cấu trúc | `Part` | Tự đọc headers/content khi cần |
| Nhiều part cùng tên | `List<Part>` hoặc `MultiValueMap` | Xử lý các giá trị lặp |

`FilePart` không phải DTO chứa toàn bộ file bytes. Nó biểu diễn một file part và cung cấp tên file, headers, content stream và thao tác chuyển file.

## 3. `@RequestPart`: lấy và decode một part riêng lẻ

### 3.1. Lấy part thô bằng `Part` hoặc `FilePart`

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

Dùng `Part` khi cần headers hoặc content thô của part. Dùng `FilePart` khi part có filename và cần các thao tác dành cho file.

Đoạn trên chỉ minh họa cách nhận part; nó chưa decode JSON metadata thành DTO và chưa validate nội dung.

### 3.2. Decode JSON part thành DTO

Nếu part `metadata` chứa JSON, có thể khai báo trực tiếp kiểu đích:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<UploadReceipt> upload(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") FilePart file) {

    return uploadService.save(metadata, file);
}
```

Spring dùng message reader/codec tương ứng với media type của part để chuyển JSON thành `UploadMetadata`. Part cần khai báo `Content-Type: application/json` và body phải có cấu trúc tương thích với DTO.

Nếu dùng `Part` thay cho DTO, ứng dụng phải tự đọc và decode nội dung. Khai báo DTO giúp Spring đảm nhiệm bước HTTP message conversion.

### 3.3. Dùng reactive wrapper `Mono<DTO>`

WebFlux cũng hỗ trợ:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<UploadReceipt> upload(
        @RequestPart("metadata") Mono<UploadMetadata> metadata,
        @RequestPart("file") FilePart file) {

    return metadata.flatMap(value ->
            uploadService.save(value, file));
}
```

Cách này giữ việc decode part trong reactive pipeline. Có thể compose thêm validation, service call, error mapping và lưu file mà không gọi `subscribe()` hoặc `block()`.

Đối với JSON metadata cần Bean Validation, cách viết thường dùng là:

```java
@Valid @RequestPart("metadata") Mono<UploadMetadata> metadata
```

Spring Framework hỗ trợ `@Valid` cùng `@RequestPart` cho cả DTO trực tiếp và async wrapper như `Mono<DTO>`.

## 4. Định nghĩa DTO và constraint cho metadata có cấu trúc

Giả sử metadata cần các điều kiện:

- `title` bắt buộc, không chỉ chứa khoảng trắng và tối đa 80 ký tự.
- `details` bắt buộc.
- `details.category` chỉ nhận `invoice`, `report` hoặc `other`.
- `details.revision` không âm.

Có thể định nghĩa record:

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

Các annotation thuộc Jakarta Bean Validation:

| Annotation | Vai trò |
|---|---|
| `@NotNull` | Giá trị không được null |
| `@NotBlank` | Chuỗi phải có ít nhất một ký tự không phải whitespace |
| `@Size(max = 80)` | Giới hạn độ dài chuỗi hoặc kích thước collection |
| `@Pattern` | Chuỗi phải khớp regular expression |
| `@Min(0)` | Giá trị số phải từ 0 trở lên |
| `@Valid` | Cascade validation vào object lồng nhau |

### Vì sao phải có `@Valid` trên `details`?

Constraint đặt trong `Details` không tự động được chạy chỉ vì object cha có `@Valid`. Cần đánh dấu thuộc tính lồng nhau để validator đi sâu vào object đó:

```java
@NotNull
@Valid
Details details
```

`@NotNull` kiểm tra `details` có tồn tại; `@Valid` kiểm tra tiếp các field bên trong. Hai annotation có trách nhiệm khác nhau.

### `@Valid` không thay thế constraint

`@Valid` chỉ yêu cầu cascade validation. Nếu muốn `title` không được rỗng, phải dùng `@NotBlank`. Nếu chỉ viết `@Valid String title`, không có constraint nào để kiểm tra chuỗi.

### Validation không sửa JSON sai cú pháp

Bean Validation chỉ chạy sau khi part đã được decode thành object. Nếu JSON thiếu dấu ngoặc hoặc có token không thể chuyển thành kiểu đích, decoder thất bại trước khi validator có object để kiểm tra.

## 5. Kích hoạt Bean Validation trên `@RequestPart`

Ví dụ controller:

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

Để Bean Validation hoạt động, ứng dụng cần có implementation Jakarta Bean Validation trên classpath. Với Spring Boot, thường thêm `spring-boot-starter-validation`.

Khi metadata vi phạm constraint, WebFlux phát `WebExchangeBindException` và mặc định trả HTTP 400 Bad Request. Exception có `BindingResult` chứa các lỗi field/global. Với reactive wrapper, có thể dùng các operator lỗi trong pipeline hoặc xử lý tập trung ở `@RestControllerAdvice`.

### Ví dụ payload hợp lệ

```json
{
  "title": "Quarterly report",
  "details": {
    "category": "report",
    "revision": 2
  }
}
```

### Ví dụ payload decode được nhưng validation thất bại

```json
{
  "title": "   ",
  "details": {
    "category": "unknown",
    "revision": -1
  }
}
```

JSON hợp lệ và có thể tạo record. Tuy nhiên:

- `title` vi phạm `@NotBlank`.
- `category` không khớp `@Pattern`.
- `revision` nhỏ hơn 0.

Đây là lỗi Bean Validation, không phải lỗi JSON decoding.

## 6. Phân biệt decode error, missing part và validation error

Một multipart endpoint có thể thất bại ở nhiều giai đoạn:

```text
Multipart request
      |
      v
Parse boundary và tìm part
      |
      +---- thiếu part bắt buộc ----------> input error
      |
      v
Đọc Content-Type của part
      |
      +---- không có reader phù hợp ------> media type error
      |
      v
Decode JSON/text thành kiểu Java
      |
      +---- JSON sai cú pháp/shape -------> decoding error
      |
      v
Bean Validation trên DTO
      |
      +---- constraint không đạt --------> validation error
      |
      v
Kiểm tra file và quy tắc nghiệp vụ
      |
      +---- file/type/policy không đạt ---> domain/input error
      |
      v
Lưu trữ hoặc xử lý file
```

| Tình huống | Giai đoạn | Kết quả thường gặp |
|---|---|---|
| Không có part `metadata` bắt buộc | Multipart binding | 400 Bad Request |
| Metadata part gửi JSON nhưng body sai cú pháp | Decode | 400 Bad Request |
| Metadata part có media type không hỗ trợ cho DTO | Chọn message reader | 415 Unsupported Media Type |
| JSON decode được nhưng `title` blank | Bean Validation | 400 Bad Request |
| JSON decode được nhưng `details` null | Bean Validation | 400 Bad Request |
| File part có media type bị API từ chối | File policy | Status do API quy định, ví dụ 415 |
| File vượt giới hạn multipart | Multipart parser/resource limit | Phụ thuộc reader, server và exception mapping |
| SKU hoặc category hợp lệ về cú pháp nhưng không được phép theo trạng thái nghiệp vụ | Business validation | Status theo API contract |

Không nên gộp mọi trường hợp thành “metadata invalid”. Khi log hoặc trả lỗi, hãy phân biệt parse, binding, constraint và business rule để người gọi biết cần sửa gì.

### Exception validation trong WebFlux

Với validation một method parameter riêng lẻ như `@Valid @RequestPart("metadata") Mono<UploadMetadata>`, exception thường là `WebExchangeBindException`.

Nếu method validation áp dụng do có constraint trực tiếp trên các method parameter, ví dụ `@Min`, `@NotNull`, Spring có thể phát `HandlerMethodValidationException` thay thế. Ứng dụng nên hiểu cả hai loại nếu controller sử dụng method validation.

`@Valid` tự nó không phải constraint và không kích hoạt method validation. Constraint như `@NotNull`, `@Min`, `@NotBlank` mới là annotation xác định điều kiện validation.

## 7. Xử lý lỗi validation bằng `BindingResult` hoặc advice

### 7.1. Xử lý command object của form bằng `BindingResult`

Với form upload từ trình duyệt, có thể bind các field vào một command object có cả `FilePart`:

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

Controller có thể nhận `BindingResult` ngay sau object:

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

`BindingResult` phải nằm ngay sau argument được bind/validate. Khi có lỗi, controller có thể kiểm tra `hasErrors()` và tự quyết định response.

Ví dụ này minh họa data binding cho browser form. Với REST request có một JSON part có cấu trúc riêng, `@RequestPart` với DTO thường rõ ràng hơn.

### 7.2. Chuẩn hóa `WebExchangeBindException` bằng `@RestControllerAdvice`

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

Các import cần thiết gồm `List`, `Map`, `HttpStatus`, `MediaType`, `ProblemDetail`, `ResponseEntity`, `ExceptionHandler`, `RestControllerAdvice` và `WebExchangeBindException`.

Response ví dụ:

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

Không trả rejected value hoặc toàn bộ body cho client nếu field có thể chứa dữ liệu cá nhân, token hay bí mật. Field path và error code thường đủ để giao diện đánh dấu vị trí cần sửa.

Trong ứng dụng có method validation, cần xử lý thêm `HandlerMethodValidationException`. Có thể mở rộng `ResponseEntityExceptionHandler` hoặc thêm handler riêng, tùy cách muốn chuẩn hóa lỗi.

## 8. Validate file part: metadata file không phải nội dung file

Bean Validation trên DTO metadata không tự xác nhận nội dung file. Với `FilePart`, ứng dụng thường phải kiểm tra riêng:

- Part có bắt buộc không?
- Filename có rỗng không?
- Content-Type được khai báo có nằm trong allowlist không?
- Kích thước file có nằm trong giới hạn không?
- Nội dung thực tế có đúng định dạng được phép không?
- File có chứa mã độc hoặc nội dung không an toàn không?

### Filename và Content-Type đều do client cung cấp

Không dùng filename gốc làm đường dẫn lưu file:

```java
// Không dùng filename của client làm destination path.
Path destination = uploadDirectory.resolve(file.filename());
```

Filename có thể chứa ký tự điều hướng thư mục hoặc tên trùng. Hãy tạo tên lưu trữ từ UUID hoặc ID do server cấp, lưu filename gốc như metadata đã được làm sạch nếu nghiệp vụ cần hiển thị.

Tương tự, `Content-Type: application/pdf` không chứng minh bytes thực sự là PDF. Client có thể gửi header giả. Production cần kiểm tra magic bytes hoặc parse bằng thư viện phù hợp, và có thể quét malware trước khi công bố file.

### Kích thước file

Không nên đọc toàn bộ file thành `byte[]` chỉ để kiểm tra kích thước. Hãy giới hạn tại multipart reader, reverse proxy/API gateway và tầng lưu trữ; nếu cần đo chính xác, đếm bytes khi stream hoặc dùng metadata đáng tin cậy từ storage.

`Content-Length` của part có thể vắng mặt hoặc không đáng tin cậy. Đừng dùng nó làm biện pháp duy nhất để chống upload quá lớn.

### Tên part và part lặp

Nếu API chỉ nhận một part `file`, kiểm tra contract và giới hạn số part. Nếu client gửi nhiều file cùng tên, API cần quyết định chấp nhận một hay nhiều file. Đừng mặc định rằng `@RequestPart("file") FilePart` là hợp đồng cho nhiều file lặp.

## 9. Form command object và JSON part: chọn cách bind phù hợp

WebFlux có hai kiểu request phổ biến:

### Browser form: bind vào command object

Một form đơn giản có các field text và một file có thể bind thành command object:

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

Spring bind form fields và file part vào object. Đây là cách tiện cho các biểu mẫu có nhiều field cùng một cấu trúc command.

### REST multipart: JSON metadata và file là hai part riêng

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

Cách này phù hợp khi metadata có JSON schema rõ ràng và file là binary part độc lập.

### Không nhầm `@RequestParam` với multipart form field trong WebFlux

Trong WebFlux, `@RequestParam` dùng để bind query parameters của URL. Với multipart part, dùng `@RequestPart` hoặc bind command object qua `@ModelAttribute`. Không lấy mô hình Servlet request parameter rồi áp dụng nguyên xi vào WebFlux.

## 10. Đọc toàn bộ multipart dưới dạng `MultiValueMap`

Nếu cần truy cập các part theo tên, WebFlux có thể đọc toàn bộ multipart thành `MultiValueMap<String, Part>`:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> inspect(
        @RequestBody Mono<MultiValueMap<String, Part>> parts) {

    return parts.map(map ->
            "part names=" + map.keySet());
}
```

`MultiValueMap` hữu ích khi cần xử lý linh hoạt nhiều tên part hoặc part lặp. Tuy nhiên, cách này yêu cầu parser tạo cấu trúc map để truy cập các part theo tên.

`ServerWebExchange.getMultipartData()` cũng cung cấp `Mono<MultiValueMap<String, Part>>` và cache kết quả parse để có thể truy cập lại trong cùng exchange. Sau khi multipart data đã được parse theo cách này, không thể tiếp tục đọc raw request body như một stream độc lập.

Với file lớn hoặc upload có nhiều part, cân nhắc streaming thay vì gom toàn bộ multipart thành map.

## 11. Streaming multipart bằng `Flux<PartEvent>`

`PartEvent` cho phép xử lý multipart tuần tự, không cần tạo `MultiValueMap` chứa toàn bộ parts.

- Form field tạo một `FormPartEvent` chứa giá trị field.
- File upload tạo một hoặc nhiều `FilePartEvent`.
- File lớn có thể được chia thành nhiều event/buffer.
- Event cuối cùng của mỗi part có `isLast() == true`.

Mô hình:

```text
Flux<PartEvent>
       |
       v
windowUntil(PartEvent::isLast)
       |
       +---- window cho metadata/form field
       |
       +---- window cho file part (có thể nhiều buffer)
       |
       v
concatMap xử lý từng part
       |
       v
consume / relay / release content buffers
```

Ví dụ nhận diện loại part:

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

`validateAndStoreField` và `fileStorage.store` là API của ứng dụng cần triển khai. Đoạn code minh họa cấu trúc xử lý; khi triển khai thật, cần xác minh cách consumer tiêu thụ từng `PartEvent` và buffer trong window tương ứng.

**Quy tắc quan trọng:** nội dung của các `PartEvent` phải được consume hoàn toàn, relay sang nơi khác hoặc release đúng cách. Nếu bỏ qua file content hoặc giữ `DataBuffer` mà không quản lý ownership, ứng dụng có thể bị memory leak. Với pooled buffer, không tự release buffer mà downstream vẫn còn sở hữu.

### Khi nào nên dùng `PartEvent`?

Dùng khi:

- File lớn cần được ghi hoặc chuyển tiếp theo luồng.
- Request có nhiều part và không muốn parse toàn bộ thành map.
- Cần kiểm soát thứ tự và backpressure giữa các part.
- Cần relay multipart sang một service khác mà không aggregate file vào heap.

Với form upload nhỏ hoặc REST request có một JSON metadata part và một file part, `@RequestPart` thường dễ đọc và dễ kiểm thử hơn.

### Validation trong streaming khác `@Valid @RequestPart`

`@Valid @RequestPart Mono<DTO>` để Spring decode part thành DTO rồi tự chạy Bean Validation.

Với `Flux<PartEvent>`, ứng dụng đang làm việc ở mức event/bytes. Không có DTO metadata được Spring tự bind theo annotation cho từng window. Nếu part là JSON, ứng dụng cần tự decode có giới hạn, tạo DTO rồi gọi validator hoặc service validation trước khi xử lý tiếp.

Không nên đọc toàn bộ file part vào `String` hoặc `byte[]` chỉ để dùng cùng validator. Validation cấu trúc metadata và xử lý file binary nên là hai luồng trách nhiệm riêng.

## 12. Giới hạn multipart và bộ nhớ trong Spring Boot

Multipart có giới hạn riêng với codec body thông thường. Trong Spring Boot WebFlux, các thuộc tính thường dùng nằm dưới `spring.webflux.multipart`.

Ví dụ:

```properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=20MB
spring.webflux.multipart.max-parts=3
spring.webflux.multipart.max-headers-size=10KB
spring.webflux.multipart.file-storage-directory=/var/app/multipart-tmp
```

Ý nghĩa:

| Thuộc tính | Tác dụng |
|---|---|
| `max-in-memory-size` | Giới hạn bộ nhớ cho non-file part; với file part là ngưỡng trước khi ghi ra disk |
| `max-disk-usage-per-part` | Giới hạn dung lượng disk cho mỗi part được lưu xuống disk |
| `max-parts` | Giới hạn số part trong một multipart request |
| `max-headers-size` | Giới hạn lượng memory dành cho headers của mỗi part |
| `file-storage-directory` | Thư mục tạm để lưu file part vượt ngưỡng memory |

Trong Spring Boot 3.3, mặc định thường gặp là 256 KB cho `max-in-memory-size`, 10 KB cho headers; `max-disk-usage-per-part` và `max-parts` mặc định không giới hạn (`-1`). Production nên đặt giới hạn hữu hạn theo nhu cầu thực tế.

`file-storage-directory` là thư mục tạm của multipart parser, không phải kho file nghiệp vụ lâu dài. Ứng dụng vẫn cần chuyển file hợp lệ sang object storage hoặc thư mục lưu trữ được quản lý.

### Phân biệt multipart limits với codec limits

Có hai tầng cấu hình cần phân biệt:

1. `spring.webflux.multipart.*` điều khiển việc parse và lưu các part của multipart.
2. `spring.codec.max-in-memory-size` điều khiển giới hạn buffer của các codec mặc định dùng để decode/encode body, ví dụ JSON metadata part.

Tăng một giới hạn không tự động tăng giới hạn ở tầng còn lại. Nếu metadata JSON quá lớn, cần xem cả multipart part limit lẫn decoder limit; đồng thời nên giới hạn schema và kích thước metadata thay vì cho phép JSON tùy ý.

### Giới hạn tổng request

`max-in-memory-size` không phải tổng dung lượng upload. Nó là giới hạn theo part/ngưỡng buffer. Hãy đặt thêm giới hạn tổng request ở reverse proxy, API gateway hoặc HTTP server phù hợp với hạ tầng. Giới hạn từng part, số part, dung lượng disk và tổng request bảo vệ các tài nguyên khác nhau.

Khi dùng `PartEvent` streaming, thư mục `file-storage-directory` của cơ chế parse đầy đủ không được dùng theo cùng cách; tài liệu Spring Boot ghi rõ cấu hình này bị bỏ qua cho streaming support.

## 13. Lỗi và status khi multipart validation thất bại

Một API có thể chuẩn hóa lỗi bằng `ProblemDetail`:

| Lỗi | Status thường phù hợp | Ghi chú |
|---|---:|---|
| Thiếu part bắt buộc | 400 | Request không đáp ứng contract |
| JSON metadata sai cú pháp | 400 | Decoder không tạo được DTO |
| Metadata vi phạm Bean Validation | 400 | `WebExchangeBindException` |
| Method validation thất bại | 400 | Có thể là `HandlerMethodValidationException` |
| Part media type không được hỗ trợ | 415 | Không có reader phù hợp |
| File type bị chính sách API từ chối | 415 hoặc 400 | Chọn nhất quán theo contract |
| File vượt giới hạn | 413 có thể phù hợp | Cần kiểm tra exception và ánh xạ có chủ đích |
| Domain rule không cho phép upload | 409 hoặc 422 | Phụ thuộc ý nghĩa nghiệp vụ |

Không giả định mọi lỗi vượt giới hạn multipart đều tự động thành HTTP 413. Parser có thể phát exception riêng; gateway có thể từ chối request trước khi WebFlux nhận được. Nếu muốn một status cụ thể, hãy xác định exception thực tế trong phiên bản và reader đang dùng rồi ánh xạ rõ ràng.

Với `@Valid @RequestPart`, lỗi validation có `BindingResult`; response body có thể cung cấp field path và error code mà không cần trả rejected value. Với lỗi decode, có thể dùng `ServerWebInputException`/exception cause để phân loại. Không nên trả stack trace hoặc raw multipart body.

## 14. Dự án Java 17+ chạy được: validate JSON metadata và lưu file part

Ví dụ dưới đây dùng Java 17, Spring Boot 3.3.5, Spring WebFlux, Jakarta Validation và `WebTestClient`.

Endpoint `POST /uploads` nhận:

- Part `metadata`: JSON `UploadMetadata`, được validate cả nested object.
- Part `file`: PDF `FilePart`, kiểm tra filename và Content-Type khai báo, sau đó lưu bằng tên do server tạo.

Mẫu này lưu vào thư mục tạm để người học chạy độc lập. Ứng dụng production nên dùng storage bền vững, retention policy, quét malware và xác minh định dạng file thực tế.

### 14.1. Cấu trúc dự án

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

Thư mục được tạo trên bounded elastic scheduler vì `Files.createDirectories` là thao tác filesystem blocking. `FilePart.transferTo` trả về `Mono<Void>` để việc ghi file được compose vào reactive pipeline.

Tên lưu trữ được sinh bằng UUID. Không dùng filename từ client làm destination path.

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

Controller làm ba việc ở biên HTTP:

1. Nhận JSON metadata và file part.
2. Kiểm tra nhanh metadata của file part theo contract API.
3. Chờ metadata được decode/validate rồi gọi storage.

`@Valid` áp dụng cho JSON metadata. Nếu metadata vi phạm constraint, WebFlux phát validation exception và `storage.store` không được gọi.

Kiểm tra Content-Type ở đây chỉ kiểm tra header do client khai báo. Nó không chứng minh bytes thật sự là PDF; production phải xác minh chữ ký file hoặc parse bằng thư viện an toàn.

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

Advice tạo response lỗi có field path và code. Nó không đưa rejected value vào response.

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

Test dùng `MultipartBodyBuilder` để tạo hai part riêng:

- `metadata` được encode thành JSON và có part Content-Type `application/json`.
- `file` là resource có filename và Content-Type được khai báo.

Body inserter tự tạo boundary cho outer multipart request. Không tự đặt header `Content-Type: multipart/form-data` thiếu boundary.

### 14.10. Chạy test

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Khi dependencies tải thành công và assertion đúng, Maven Surefire sẽ chạy năm test:

1. JSON metadata hợp lệ và PDF part được chấp nhận.
2. Metadata sai constraint ở cả field cấp cao và nested object bị trả 400.
3. JSON part sai cú pháp bị trả 400 ở bước decode.
4. File part có media type không được API chấp nhận bị trả 415.
5. Thiếu file part bắt buộc bị trả 400.

Kết quả mong đợi:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

Đây là kết quả kỳ vọng sau khi chạy `mvn test`, không phải xác nhận Maven đã được thực thi trong môi trường biên soạn tài liệu.

### 14.11. Gửi multipart request bằng curl

```bash
curl -i -X POST "http://localhost:8080/uploads" \
  -F 'metadata={"title":"Quarterly report","details":{"category":"report","revision":2}};type=application/json' \
  -F 'file=@report.pdf;type=application/pdf'
```

`curl -F` tự tạo boundary cho multipart request và gửi Content-Type riêng cho từng part. Không đặt `Content-Type: application/json` cho toàn request.

Response thành công ví dụ:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "id": "c6d3...",
  "title": "Quarterly report",
  "category": "report"
}
```

ID được tạo ngẫu nhiên; giá trị thực tế thay đổi theo lần upload.

## 15. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Đặt `Content-Type: application/json` cho toàn multipart request | Parser không nhận đúng multipart boundary | Outer request dùng multipart/form-data; JSON part có Content-Type riêng |
| Nhận JSON part bằng `Part` rồi giả định đã có DTO | Ứng dụng vẫn đang giữ part thô | Khai báo `@RequestPart("metadata") Metadata` hoặc decode rõ ràng |
| Quên `@Valid` trên metadata part | Constraint không được kích hoạt ở argument resolver | Dùng `@Valid @RequestPart(...)` |
| Quên `@Valid` trên nested object | Constraint bên trong object lồng nhau không cascade | Đặt `@Valid` trên field/record component lồng nhau |
| Nghĩ `@Valid` là constraint | Không có rule nào được kiểm tra nếu thiếu constraint | Dùng `@NotBlank`, `@Size`, `@Min`... |
| Nhầm decode error với validation error | Trả thông báo sai cho client | Phân biệt JSON parse, type conversion và Bean Validation |
| Dùng `@RequestParam` để lấy multipart field theo mô hình Servlet | Binding không theo contract WebFlux | Dùng `@RequestPart` hoặc `@ModelAttribute` |
| Đọc file thành `byte[]` để lưu | Tốn heap theo kích thước file | Dùng `FilePart.transferTo` hoặc streaming |
| Dùng filename client làm path | Có thể path traversal hoặc ghi đè file | Sinh tên lưu trữ từ UUID/ID server |
| Tin Content-Type của file | File giả MIME có thể vượt kiểm tra | Kiểm tra signature/nội dung thực tế và scan |
| Chỉ giới hạn `max-in-memory-size` | File lớn có thể vẫn ghi xuống disk không giới hạn | Đặt `max-disk-usage-per-part`, `max-parts` và tổng request limit |
| Dùng `MultiValueMap` cho upload streaming lớn | Parser phải tạo map các parts | Cân nhắc `Flux<PartEvent>` |
| Bỏ qua PartEvent content | Buffer không được consume/release | Consume, relay hoặc release mọi part content |
| Chỉ xử lý `WebExchangeBindException` trong controller có method validation | Có thể bỏ sót `HandlerMethodValidationException` | Xử lý cả hai khi method validation được dùng |
| Test chỉ metadata JSON mà không có file part | Không kiểm tra multipart contract thật | Test cả metadata, file, media type và part bắt buộc |

## 16. Checklist trước khi đưa multipart validation vào production

### Contract và binding

- Outer request có `Content-Type` multipart với boundary hợp lệ không?
- Mỗi JSON part có Content-Type `application/json` không?
- Tên part có ổn định và được tài liệu hóa không?
- Part nào bắt buộc, part nào optional, part nào có thể lặp?
- Có dùng DTO riêng cho metadata thay vì expose domain entity không?
- Nested object có `@Valid` để cascade không?

### Validation và error handling

- Có `spring-boot-starter-validation` hoặc validator tương thích không?
- Có test JSON decode failure và Bean Validation failure riêng không?
- Có xử lý `WebExchangeBindException` và `HandlerMethodValidationException` khi cần không?
- Error body có field path và code nhưng không chứa rejected value nhạy cảm không?
- File policy có kiểm tra filename, media type, size và signature không?

### Resource và security

- Có giới hạn memory cho non-file part không?
- File part có giới hạn disk usage không?
- Số part và header size có giới hạn không?
- Tổng request size có giới hạn ở gateway/server không?
- File được lưu bằng tên do server tạo và ở vị trí ngoài webroot không?
- Có antivirus/content scanning và retention/cleanup policy phù hợp không?
- Streaming path có consume/relay/release mọi DataBuffer không?
- Có tránh đọc toàn bộ file vào heap hoặc aggregate nhiều upload đồng thời không?

### Testing và vận hành

- Có test thành công với metadata + file?
- Có test metadata thiếu, JSON sai cú pháp và constraint fail?
- Có test thiếu file part, sai part media type và file quá lớn?
- Có test multipart streaming nếu endpoint dùng `PartEvent`?
- Có log correlation ID, route và error category mà không log file/body?
- Có metric cho upload size, số upload, lỗi validation và storage failure không?

## 17. Bài tập tự kiểm tra

**Bài 1.** Một multipart request có part `metadata` chứa JSON. Nên khai báo kiểu nào nếu muốn Spring tự decode thành DTO?

**Đáp án:** `@RequestPart("metadata") UploadMetadata metadata` hoặc `@Valid @RequestPart("metadata") Mono<UploadMetadata> metadata` nếu muốn compose reactive.

**Bài 2.** Vì sao part JSON cần Content-Type riêng?

**Đáp án:** Outer request là multipart có boundary; message reader chọn codec cho từng part dựa trên Content-Type của part. JSON metadata cần `application/json`.

**Bài 3.** JSON hợp lệ nhưng `title=""` vi phạm `@NotBlank`. Đây là lỗi gì?

**Đáp án:** Bean Validation failure. Decoder đã tạo DTO thành công.

**Bài 4.** Vì sao `details` cần cả `@NotNull` và `@Valid`?

**Đáp án:** `@NotNull` yêu cầu object tồn tại; `@Valid` cascade validation vào các field bên trong.

**Bài 5.** `@Valid @RequestPart Mono<Metadata>` vi phạm constraint thường phát exception nào?

**Đáp án:** `WebExchangeBindException`, thường được ánh xạ thành 400. Nếu method validation áp dụng do constraint trực tiếp trên method parameter, có thể là `HandlerMethodValidationException`.

**Bài 6.** Có nên dùng filename gốc làm path lưu file?

**Đáp án:** Không. Filename do client cung cấp và có thể chứa path traversal hoặc tên trùng. Sinh tên lưu trữ từ UUID/ID server.

**Bài 7.** `max-in-memory-size` có phải giới hạn tổng request upload không?

**Đáp án:** Không. Với multipart, nó giới hạn non-file part và là ngưỡng spill-to-disk cho file part. Cần giới hạn disk, số part và tổng request ở các tầng phù hợp.

**Bài 8.** Khi nào nên dùng `Flux<PartEvent>` thay vì `@RequestPart`?

**Đáp án:** Khi cần xử lý multipart tuần tự và streaming, đặc biệt với file lớn hoặc nhiều part. Ứng dụng phải consume, relay hoặc release nội dung từng part.

**Bài 9.** Header `Content-Type: application/pdf` có chứng minh file thật sự là PDF không?

**Đáp án:** Không. Đó là metadata do client khai báo. Cần kiểm tra signature/nội dung thực tế hoặc parse bằng thư viện an toàn.

**Bài 10.** Có thể trả 400 cho mọi lỗi multipart không?

**Đáp án:** Không nên. Cần phân biệt decode, validation, unsupported media type, size limit, domain policy và lỗi hạ tầng; status phải phù hợp với nguyên nhân và API contract.

## 18. Ghi nhớ

- Multipart là một HTTP body gồm nhiều part; mỗi part có tên, headers và media type riêng.
- `@RequestPart("metadata") Metadata` để Spring decode part thành DTO; part JSON cần `Content-Type: application/json`.
- `@Valid @RequestPart("metadata") Mono<Metadata>` kích hoạt Bean Validation trên DTO trong reactive pipeline.
- Nested object cần `@Valid`; constraint như `@NotBlank`, `@Size`, `@Pattern`, `@Min` mới định nghĩa điều kiện.
- Validation failure thường là `WebExchangeBindException` và HTTP 400; method validation có thể dùng `HandlerMethodValidationException`.
- FilePart cần kiểm tra riêng; Bean Validation của metadata không xác minh bytes file.
- Filename và Content-Type do client khai báo, không được tin để quyết định path hoặc tính xác thực của file.
- `@ModelAttribute` command object phù hợp với browser form; `@RequestPart` phù hợp với JSON part và file part tách biệt.
- `MultiValueMap<String, Part>` thuận tiện cho parsing đầy đủ; `Flux<PartEvent>` phù hợp xử lý streaming.
- `max-in-memory-size`, disk usage, max parts và tổng request limit bảo vệ các tài nguyên khác nhau.
- Mọi PartEvent/DataBuffer phải được consume, relay hoặc release đúng cách.

Khi thiết kế multipart endpoint, hãy kiểm tra theo thứ tự: **outer multipart → tên và Content-Type của từng part → decode DTO → Bean Validation → file policy → business rules → storage**. Phân tách từng bước giúp trả lỗi đúng nguyên nhân và tránh giữ file lớn trong heap.

## Tài liệu chính thức

- Spring Framework 6.2, **WebFlux Multipart Content**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework 6.2, **WebFlux Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2, **WebFlux Reactive Core – Multipart and DataBuffer limits**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2, **Data Buffers and Codecs**: https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html
- Spring Boot 3.3, **Common Application Properties – WebFlux multipart**: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html