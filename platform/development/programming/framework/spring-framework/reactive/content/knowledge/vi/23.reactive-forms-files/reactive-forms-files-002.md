# Đọc multipart bằng @RequestPart, Part và FilePart trong Spring WebFlux

## 1. Multipart là gì?

HTTP multipart cho phép một request body chứa nhiều phần (part). Mỗi part có header và nội dung riêng. Trình duyệt thường dùng `multipart/form-data` khi form có file upload; API cũng có thể dùng `multipart/mixed` hoặc `multipart/related` khi một request chứa JSON, ảnh, tài liệu hay dữ liệu thuộc nhiều media type khác nhau.

Ví dụ một request upload tài liệu có metadata JSON và một file:

~~~http
POST /api/uploads HTTP/1.1
Content-Type: multipart/form-data; boundary=----upload-boundary

------upload-boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Hướng dẫn WebFlux","category":"manual"}
------upload-boundary
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

<binary file content>
------upload-boundary--
~~~

Các khái niệm:

- **Boundary**: chuỗi phân cách các part. Client tạo boundary và đưa nó vào Content-Type của toàn request.
- **Part name**: tên của trường, ví dụ `metadata` hoặc `file`.
- **Content-Disposition**: mô tả part là field nào và có filename hay không.
- **Part Content-Type**: loại dữ liệu của riêng part đó, ví dụ `application/json` hoặc `application/pdf`.
- **Part body**: dữ liệu text, JSON hoặc bytes của file.

Không được tự đặt header `Content-Type: multipart/form-data` khi gửi từ trình duyệt bằng FormData, vì browser cần tự thêm boundary vào header. Nếu tự đặt mà thiếu boundary, server không thể phân tích request đúng cách.

## 2. WebFlux phân tích multipart như thế nào?

Spring WebFlux dùng hệ thống HTTP message reader/codec để đọc multipart. Luồng khái quát:

~~~text
HTTP request body
  Content-Type: multipart/form-data; boundary=...
              |
              v
      MultipartHttpMessageReader
              |
              v
       PartHttpMessageReader
              |
              v
       Part / FilePart objects
              |
       +------+-------------------+
       |                          |
       v                          v
  @RequestPart                MultiValueMap
  theo tên part               tất cả các part
       |
       v
  HttpMessageReader
  giải mã part nếu target
  là DTO cụ thể
~~~

Trong cấu hình mặc định, `DefaultPartHttpMessageReader` đọc các part thành `Part`. `MultipartHttpMessageReader` gom các part thành `MultiValueMap<String, Part>` để có thể truy cập theo tên.

Điều này giải thích vì sao có hai cách tiếp cận:

1. **Truy cập theo tên part** bằng `@RequestPart` hoặc `ServerWebExchange.getMultipartData()`. Cách này tiện khi endpoint cần một tập part có cấu trúc rõ.
2. **Đọc tuần tự dạng streaming** bằng `Flux<PartEvent>`. Cách này phù hợp với file lớn hoặc proxy cần chuyển tiếp dữ liệu mà không gom toàn bộ part vào một map.

`@RequestPart` thường yêu cầu xử lý multipart theo kiểu truy cập map-like, tức parser phải phân tích multipart và cung cấp các part theo tên. Nếu cần streaming từng event ngay khi nhận, hãy cân nhắc `PartEvent`.

## 3. @RequestPart dùng để làm gì?

`@RequestPart` liên kết một part có tên trong multipart request với tham số của controller method.

Ví dụ:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") FilePart file) {
    // ...
}
~~~

Spring tìm part tên `metadata` và `file`, sau đó giải quyết tham số tương ứng.

`@RequestPart` tương tự `@RequestBody` ở chỗ nó có thể dùng HTTP message reader để giải mã nội dung part sang một kiểu Java cụ thể. Khác biệt là `@RequestBody` đọc body của cả request, còn `@RequestPart` đọc một part trong multipart body.

### 3.1. Giải mã JSON part thành DTO

Nếu part `metadata` có Content-Type là `application/json`, bạn có thể khai báo kiểu DTO:

~~~java
public record UploadMetadata(
        String title,
        String category) {
}

@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @RequestPart("metadata") UploadMetadata metadata) {
    return Mono.just(metadata.title());
}
~~~

Spring dùng codec JSON (thường là Jackson khi dependency tương ứng có mặt) để giải mã nội dung part thành `UploadMetadata`.

Điều kiện quan trọng: **Content-Type của part phải phù hợp với kiểu target**. Nếu client gửi JSON nhưng part lại bị đánh dấu `text/plain` hoặc không có media type phù hợp, codec có thể không tìm được reader tương ứng.

Với browser FormData, hãy thêm metadata dưới dạng Blob có Content-Type JSON:

~~~javascript
const form = new FormData();

form.append(
  "metadata",
  new Blob(
    [JSON.stringify({
      title: "Hướng dẫn WebFlux",
      category: "manual"
    })],
    { type: "application/json" }
  )
);

form.append("file", fileInput.files[0]);

await fetch("/api/uploads", {
  method: "POST",
  body: form
});
~~~

Không tự thêm header `Content-Type` vào fetch ở ví dụ này. Browser tự tạo multipart boundary và gắn vào header.

### 3.2. Validation cho JSON part

Có thể kết hợp `@Valid` hoặc `@Validated` với `@RequestPart`:

~~~java
public record UploadMetadata(
        @NotBlank
        @Size(max = 100)
        String title,

        @NotBlank
        @Size(max = 40)
        String category) {
}

@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @Valid @RequestPart("metadata") UploadMetadata metadata) {
    return Mono.just("accepted: " + metadata.title());
}
~~~

Khi validation thất bại, WebFlux phát `WebExchangeBindException` và mặc định ánh xạ thành HTTP 400. Nếu method validation áp dụng do các tham số khác có constraint annotation, lỗi có thể là `HandlerMethodValidationException`.

Với xử lý reactive, có thể khai báo argument là `Mono<UploadMetadata>`:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @Valid @RequestPart("metadata") Mono<UploadMetadata> metadata) {

    return metadata.map(value -> "accepted: " + value.title());
}
~~~

Cách này giúp xử lý lỗi giải mã/validation trong pipeline bằng `onErrorMap`, `onErrorResume` hoặc error handler chung. Không gọi `block()` để lấy metadata.

### 3.3. Khi nào dùng @RequestPart với kiểu Part?

Khi không muốn Spring giải mã part thành DTO mà cần thao tác trực tiếp với header và nội dung thô, khai báo `Part`:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> inspect(
        @RequestPart("metadata") Part metadata) {

    String contentType =
            String.valueOf(metadata.headers().getContentType());

    return Mono.just(
            metadata.name() + ":" + contentType);
}
~~~

`Part` cho phép:

- Lấy tên part bằng `name()`.
- Đọc headers bằng `headers()`.
- Đọc body qua `content()` dưới dạng `Flux<DataBuffer>`.
- Xóa storage nền của part bằng `delete()`.

`Part` không giả định part đó là file. Nó có thể là field text, JSON, PDF hoặc dữ liệu khác.

## 4. Part, FormFieldPart và FilePart khác nhau thế nào?

`Part` là interface chung. Hai specialization thường gặp:

- `FormFieldPart`: part dạng field văn bản; có method `value()` để lấy giá trị text.
- `FilePart`: part đại diện cho file upload; có `filename()` và `transferTo(Path)`.

| Kiểu | Dữ liệu | API thường dùng |
| --- | --- | --- |
| `Part` | Bất kỳ part nào | `name()`, `headers()`, `content()`, `delete()` |
| `FormFieldPart` | Field văn bản | `value()` |
| `FilePart` | File upload | `filename()`, `transferTo(Path)`, `content()` |

### 4.1. Part

Một `Part` cung cấp:

~~~java
String name();
HttpHeaders headers();
Flux<DataBuffer> content();
Mono<Void> delete();
~~~

`content()` trả về stream DataBuffer. Nội dung part không phải lúc nào cũng là một byte array nhỏ nằm trong heap. Nó có thể là stream hoặc dữ liệu được lưu tạm trên đĩa tùy reader và cấu hình.

Nếu tự tiêu thụ `content()` ở mức DataBuffer, phải tuân thủ ownership và release của DataBuffer. Nếu chỉ cần chuyển file sang đích, ưu tiên `FilePart.transferTo` thay vì tự viết vòng đọc/ghi bytes.

### 4.2. FormFieldPart

`FormFieldPart` mở rộng `Part` cho field văn bản:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> submit(
        @RequestPart("comment") FormFieldPart comment) {

    return Mono.just(comment.value());
}
~~~

`value()` tiện hơn đọc `content()` rồi tự chuyển bytes thành String.

Không dùng `FormFieldPart` cho file upload. Nếu client gửi part có filename, Spring thường biểu diễn nó bằng `FilePart`.

### 4.3. FilePart

`FilePart` là specialization của `Part`:

~~~java
String filename();
Mono<Void> transferTo(Path destination);
~~~

`filename()` trả tên file gốc do client cung cấp. Giá trị này **không đáng tin cậy**: có thể chứa đường dẫn, `..`, dấu phân cách hoặc ký tự nguy hiểm. Không dùng trực tiếp filename làm đường dẫn lưu trữ.

`transferTo(Path)` ghi nội dung file vào destination và trả `Mono<Void>` khi hoàn tất. Nếu file đích đã tồn tại, nội dung file đích sẽ bị truncate trước khi ghi. Vì vậy nên tạo tên đích duy nhất từ server, ví dụ UUID, thay vì dùng tên do client gửi.

Ví dụ:

~~~java
String id = UUID.randomUUID().toString();
Path destination = uploadDirectory.resolve(id + ".bin");

return filePart.transferTo(destination);
~~~

`FilePart` không có API `size()` như một số multipart abstraction của Servlet. Nếu cần giới hạn kích thước, cấu hình multipart reader/server và cân nhắc streaming/đếm byte theo đúng contract; đừng suy ra size từ filename hoặc Content-Length của toàn request.

## 5. Đọc từng part bằng @RequestPart

Một endpoint có thể nhận nhiều part với nhiều loại dữ liệu:

~~~java
@PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<ResponseEntity<String>> upload(
        @Valid @RequestPart("metadata") Mono<DocumentMetadata> metadata,
        @RequestPart("document") FilePart document,
        @RequestPart("attachment") Part attachment) {

    return metadata.map(value ->
            ResponseEntity.accepted().body(
                    "received " + value.title()
                            + ", file=" + document.filename()
                            + ", attachment=" + attachment.name()));
}
~~~

Đây là ví dụ về hình dạng tham số, không phải controller lưu file hoàn chỉnh. Mỗi tên trong annotation phải khớp chính xác với `name` của part client gửi.

Có thể dùng `@RequestPart(required = false)` cho part tùy chọn khi contract cho phép. Nếu part bắt buộc nhưng client không gửi, argument resolution thất bại trước khi handler xử lý bình thường. Hãy định nghĩa rõ part nào bắt buộc và part nào tùy chọn.

### 5.1. Tên part có dấu gạch nối

Tên part không cần trùng tên biến Java:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @RequestPart("meta-data") DocumentMetadata metadata,
        @RequestPart("file-data") FilePart file) {
    return Mono.just(metadata.title());
}
~~~

Client phải gửi đúng `meta-data` và `file-data`. Tên part là một phần của API contract; đổi tên cần được xem như thay đổi hợp đồng với client.

### 5.2. Một tên part có thể xuất hiện nhiều lần

Multipart có thể chứa nhiều part cùng tên, ví dụ nhiều file dưới field `files`. Khi cần truy cập toàn bộ danh sách hoặc tất cả part, dùng `MultiValueMap<String, Part>` qua `ServerWebExchange.getMultipartData()` hoặc `@RequestBody Mono<MultiValueMap<String, Part>>`.

Đừng giả định mỗi key chỉ có một value. Nếu API chỉ chấp nhận một file, hãy kiểm tra số lượng part tương ứng và từ chối dữ liệu dư theo contract.

## 6. Truy cập tất cả part bằng MultiValueMap

Nếu controller cần duyệt các part theo tên thay vì khai báo từng tham số, có thể nhận:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @RequestBody Mono<MultiValueMap<String, Part>> partsMono) {

    return partsMono.map(parts -> {
        Part metadata = parts.getFirst("metadata");
        List<Part> files = parts.get("files");
        return "metadata=" + metadata.name()
                + ", files=" + (files == null ? 0 : files.size());
    });
}
~~~

Hoặc dùng `ServerWebExchange`:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> inspect(ServerWebExchange exchange) {
    return exchange.getMultipartData()
            .map(parts -> "part names=" + parts.keySet());
}
~~~

`getMultipartData()` trả `Mono<MultiValueMap<String, Part>>`. Khi gọi, Spring phân tích multipart request và cache map để có thể truy cập map nhiều lần. Tuy nhiên, **nội dung của từng part không được cache và chỉ có thể đọc một lần**.

Sau khi đã dùng `getMultipartData()`, không thể quay lại đọc raw request body như thể nó chưa bị tiêu thụ. Hãy nhất quán: dùng multipart map access cho các lần đọc theo tên, hoặc dùng streaming reader nếu cần đọc tuần tự.

### 6.1. Cleanup khi tự truy cập Part

`Part.delete()` trả về `Mono<Void>` để xóa storage nền của part. `ServerWebExchange.cleanupMultipart()` cũng cung cấp thao tác cleanup storage được dùng cho multipart handling.

Khi dùng API cấp thấp như `BodyExtractors.toMultipartData()` hoặc `BodyExtractors.toParts()`, tài nguyên dùng cho part (ví dụ file tạm) không tự động được xóa chỉ vì bạn đã nhận object Part; cần compose cleanup bằng `Part.delete()` hoặc cơ chế cleanup tương ứng.

Ví dụ khái niệm:

~~~java
Mono<Void> cleanup = part.delete();
~~~

Phải đưa Publisher cleanup vào pipeline để nó được subscribe. Không gọi `part.delete()` rồi bỏ qua Mono trả về. Với nhiều part, dọn từng part bằng `concatMap(Part::delete)` hoặc `flatMap` theo chính sách phù hợp; cần đảm bảo cleanup cũng được thực hiện khi pipeline lỗi hoặc bị cancel.

## 7. FilePart.transferTo: cách upload file thông dụng

Với một file upload thông thường, `FilePart.transferTo(Path)` là API thuận tiện:

~~~java
@PostMapping(
        path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<ResponseEntity<String>> upload(
        @RequestPart("file") FilePart file) {

    Path destination = uploadDirectory.resolve(
            UUID.randomUUID() + ".bin");

    return file.transferTo(destination)
            .thenReturn(ResponseEntity.created(
                    URI.create("/files/" + destination.getFileName()))
                    .body("uploaded"));
}
~~~

Điểm quan trọng:

- Không dùng filename do client gửi để tạo destination path.
- Không gọi `block()` trên `transferTo`.
- Chỉ trả response thành công sau khi Mono transfer hoàn tất.
- Dùng tên file server-generated để tránh ghi đè file khác hoặc path traversal.
- Đặt thư mục upload ngoài web root; file upload không nên tự động trở thành nội dung có thể thực thi.
- Nếu transfer thất bại, xử lý file đích dở dang theo chính sách storage của ứng dụng.

`transferTo` trả về một Mono đại diện cho quá trình ghi. Hãy compose nó với các bước lưu metadata, quét file hoặc cập nhật database theo đúng thứ tự. Nếu file phải được scan trước khi công bố, đừng đánh dấu tài nguyên là sẵn sàng ngay khi mới nhận request.

## 8. Multipart parser, bộ nhớ và file tạm

WebFlux mặc định dùng `DefaultPartHttpMessageReader` để đọc part. Trong chế độ không streaming:

- Nội dung part nhỏ hơn ngưỡng `maxInMemorySize` được giữ trong bộ nhớ.
- File part lớn hơn ngưỡng được ghi vào file tạm.
- Non-file part vượt ngưỡng bị từ chối bằng `DataBufferLimitException`.
- Có thể cấu hình thư mục lưu trữ tạm.
- Có thể giới hạn số part và dung lượng đĩa của mỗi file part.

Theo JavaDoc Spring Framework 7.0.8:

| Thuộc tính | Giá trị mặc định | Ý nghĩa |
| --- | --- | --- |
| `maxInMemorySize` | 256 KiB | Ngưỡng bộ nhớ cho mỗi part; file lớn hơn được ghi tạm, non-file part vượt ngưỡng bị từ chối |
| `maxDiskUsagePerPart` | -1 | Không giới hạn dung lượng đĩa mỗi file part |
| `maxParts` | -1 | Không giới hạn số part |
| `fileStorageDirectory` | Thư mục `spring-webflux-multipart` dưới system temp directory | Nơi lưu part lớn hơn ngưỡng bộ nhớ |
| `maxHeadersSize` | Theo cấu hình reader | Giới hạn bộ nhớ cho header của từng part |

Không nên để giới hạn đĩa và số part ở trạng thái không giới hạn cho endpoint public. Một request có thể chứa nhiều part, file rất lớn hoặc metadata quá dài. Giới hạn cần phù hợp với nghiệp vụ và cả tầng reverse proxy/gateway.

### 8.1. Cấu hình giới hạn multipart

Có thể cung cấp một `MultipartHttpMessageReader` được cấu hình riêng thông qua `ServerCodecConfigurer`:

~~~java
@Configuration
class MultipartLimitsConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        DefaultPartHttpMessageReader partReader =
                new DefaultPartHttpMessageReader();

        partReader.setMaxInMemorySize(256 * 1024);
        partReader.setMaxDiskUsagePerPart(25L * 1024 * 1024);
        partReader.setMaxParts(5);
        partReader.setMaxHeadersSize(10 * 1024);

        MultipartHttpMessageReader multipartReader =
                new MultipartHttpMessageReader(partReader);

        configurer.customCodecs().reader(multipartReader);
    }
}
~~~

Ý nghĩa của cấu hình minh họa:

- Mỗi non-file part chỉ được giữ tối đa 256 KiB trong memory.
- File part vượt ngưỡng memory được ghi vào temp storage.
- Mỗi file part không được vượt quá 25 MiB trên đĩa.
- Một request không được có quá 5 part.
- Header của từng part bị giới hạn 10 KiB.

Đây là cấu hình reader, không thay thế giới hạn tổng request body của gateway, load balancer hoặc server. Nếu API cần tổng dung lượng tối đa 50 MiB, phải bảo đảm tổng giới hạn đó được thực thi ở tầng phù hợp; `maxDiskUsagePerPart` chỉ giới hạn từng file part, không phải tổng tất cả file trong request.

Nếu thay reader mặc định, hãy integration test lại cả `@RequestPart`, `getMultipartData()` và endpoint streaming để chắc chắn reader được đăng ký đúng thứ tự và đúng phạm vi.

## 9. Streaming multipart bằng Flux<PartEvent>

Với file lớn, xử lý multipart thành `MultiValueMap<String, Part>` có thể không phải lựa chọn tối ưu. Spring WebFlux cung cấp `PartEventHttpMessageReader` để đọc các part tuần tự:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> uploadStream(@RequestBody Flux<PartEvent> allPartEvents) {
    // xử lý từng part event theo thứ tự nhận được
}
~~~

Mỗi part tạo ít nhất một `PartEvent`:

- Form field tạo một `FormPartEvent` chứa giá trị field.
- File upload tạo một hoặc nhiều `FilePartEvent`.
- Nếu file đủ lớn để chia thành nhiều buffer, event đầu tiên có thể được theo sau bởi các event tiếp theo.
- Event cuối cùng của một part có `isLast()` bằng true.

Có thể dùng `windowUntil(PartEvent::isLast)` để chia stream thành từng nhóm event thuộc một part:

~~~java
allPartEvents
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
                partEvents.switchOnFirst((signal, events) -> {
                    if (!signal.hasValue()) {
                        return events.then();
                    }

                    PartEvent first = signal.get();

                    if (first instanceof FormPartEvent form) {
                        String value = form.value();
                        // Xử lý field text.
                        return events.then();
                    }

                    if (first instanceof FilePartEvent file) {
                        String filename = file.filename();

                        Flux<DataBuffer> content =
                                events.map(PartEvent::content);

                        // Chuyển content sang storage hoặc service đích.
                        // Storage consumer phải tiêu thụ hoặc release mọi buffer.
                        return fileStorageService.store(
                                filename, content);
                    }

                    return Mono.error(
                            new IllegalArgumentException(
                                    "Unsupported multipart event"));
                }));
~~~

Đây là **đoạn minh họa cấu trúc streaming**, giả định có `fileStorageService.store(...)` trả `Mono<Void>` và thực sự tiêu thụ/relay mọi DataBuffer. Nó không phải controller độc lập để copy nguyên văn.

Lưu ý ownership:

- Mỗi `PartEvent` chứa một `DataBuffer`.
- Nội dung file có thể trải qua nhiều event.
- Body buffer phải được tiêu thụ hoàn toàn, chuyển tiếp tới service khác hoặc release; nếu bỏ qua buffer, có thể gây memory leak.
- Không gom toàn bộ event thành một List chỉ để xử lý tuần tự.
- Dùng `concatMap` khi cần xử lý part theo thứ tự; chỉ tăng concurrency khi storage và contract cho phép.

`PartEvent` phù hợp cho file lớn, streaming proxy hoặc pipeline cần kiểm soát backpressure. `@RequestPart` phù hợp hơn khi cần truy cập một số part có tên và dữ liệu vừa phải.

## 10. Chương trình Spring Boot WebFlux Java 17+ có thể chạy

Ví dụ này tạo endpoint:

~~~text
POST /api/uploads
Content-Type: multipart/form-data
~~~

Endpoint nhận:

- `metadata`: JSON part được giải mã thành record và validation.
- `file`: FilePart được chuyển vào thư mục upload bằng tên file do server tạo.

### 10.1. Cấu trúc dự án

~~~text
webflux-multipart-demo/
  pom.xml
  src/main/java/example/upload/MultipartDemoApplication.java
  src/main/java/example/upload/UploadController.java
  src/test/java/example/upload/UploadControllerTest.java
~~~

Yêu cầu: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. Trong dự án thật, chọn patch release được tổ chức hỗ trợ và để Boot BOM quản lý Spring Framework, Reactor và các dependency tương thích.

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-multipart-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
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
~~~

### 10.3. Class khởi động

**src/main/java/example/upload/MultipartDemoApplication.java**

~~~java
package example.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultipartDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MultipartDemoApplication.class, args);
    }
}
~~~

### 10.4. Controller nhận JSON và file

**src/main/java/example/upload/UploadController.java**

~~~java
package example.upload;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.Part;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private final Path uploadDirectory;

    public UploadController() throws IOException {
        this.uploadDirectory = Path.of(
                System.getProperty("java.io.tmpdir"),
                "webflux-multipart-demo");

        Files.createDirectories(uploadDirectory);
    }

    public record UploadMetadata(
            @NotBlank
            @Size(max = 100)
            String title,

            @NotBlank
            @Size(max = 40)
            String category) {
    }

    public record UploadReceipt(
            String id,
            String title,
            String storedAs) {
    }

    @PostMapping(
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<ResponseEntity<UploadReceipt>> upload(
            @Valid
            @RequestPart("metadata")
            Mono<UploadMetadata> metadata,

            @RequestPart("file")
            FilePart file) {

        return metadata.flatMap(value -> {
            String id = UUID.randomUUID().toString();
            String storedName = id + ".bin";
            Path destination = uploadDirectory.resolve(storedName);

            UploadReceipt receipt = new UploadReceipt(
                    id, value.title(), storedName);

            Mono<UploadReceipt> saveAndCleanup = Mono.usingWhen(
                    Mono.just(file),
                    part -> part.transferTo(destination)
                            .thenReturn(receipt),
                    Part::delete,
                    (part, error) -> part.delete(),
                    Part::delete);

            return saveAndCleanup.map(saved ->
                    ResponseEntity
                            .created(URI.create("/api/uploads/" + id))
                            .body(saved));
        });
    }
}
~~~

Giải thích:

- `@RequestPart("metadata") Mono<UploadMetadata>` yêu cầu part JSON tên `metadata`. Spring giải mã nó thành record.
- `@Valid` kích hoạt validation cho các trường metadata.
- `@RequestPart("file") FilePart` lấy file part có tên `file`.
- Tên đích được tạo từ UUID, không lấy từ `file.filename()`.
- `transferTo(destination)` trả Mono, vì vậy toàn bộ thao tác lưu vẫn nằm trong reactive pipeline.
- `Mono.usingWhen` gọi `Part.delete()` sau khi thành công, lỗi hoặc cancellation để dọn storage nền của part sau khi nội dung đã được xử lý.

Đây là ví dụ lưu file đơn giản. Ứng dụng production còn cần xác thực người dùng, giới hạn dung lượng, kiểm tra loại file thực tế, quét malware nếu phù hợp, quản lý quota và lưu metadata vào database.

### 10.5. Chạy ứng dụng và gửi file bằng curl

Trong thư mục chứa `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Gửi request:

~~~bash
curl -i -X POST http://localhost:8080/api/uploads \
  -F 'metadata={"title":"WebFlux guide","category":"manual"};type=application/json' \
  -F 'file=@./guide.pdf;type=application/pdf'
~~~

Curl tự tạo boundary và multipart Content-Type.

Response có dạng:

~~~http
HTTP/1.1 201 Created
Location: /api/uploads/<generated-id>
Content-Type: application/json
~~~

Body có dạng:

~~~json
{
  "id": "<generated-id>",
  "title": "WebFlux guide",
  "storedAs": "<generated-id>.bin"
}
~~~

Tên ID thực tế được tạo ngẫu nhiên. Server lưu file trong thư mục `java.io.tmpdir/webflux-multipart-demo`; tên file gốc của client không được dùng làm đường dẫn.

### 10.6. Kiểm thử bằng WebTestClient

**src/test/java/example/upload/UploadControllerTest.java**

~~~java
package example.upload;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UploadControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptsJsonMetadataAndFile() {
        MultipartBodyBuilder multipart =
                new MultipartBodyBuilder();

        multipart.part(
                "metadata",
                new UploadController.UploadMetadata(
                        "Guide", "manual"))
                .contentType(MediaType.APPLICATION_JSON);

        multipart.part(
                "file",
                new ByteArrayResource(
                        "hello".getBytes(StandardCharsets.UTF_8)) {
                    @Override
                    public String getFilename() {
                        return "guide.txt";
                    }
                })
                .contentType(MediaType.TEXT_PLAIN);

        client.post()
                .uri("/api/uploads")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(
                        multipart.build()))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Guide")
                .jsonPath("$.storedAs").exists();
    }
}
~~~

Test này kiểm tra đường đi HTTP thực tế: multipart writer tạo các part, JSON part được giải mã, FilePart được chuyển vào storage và response trả HTTP 201.

## 11. Gửi multipart bằng WebClient

`WebClient` có thể gửi multipart bằng `MultipartBodyBuilder`:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();

builder.part("metadata", metadata)
        .contentType(MediaType.APPLICATION_JSON);

builder.part("file", resource)
        .filename("guide.pdf")
        .contentType(MediaType.APPLICATION_PDF);

Mono<UploadReceipt> result = webClient.post()
        .uri("/api/uploads")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(BodyInserters.fromMultipartData(builder.build()))
        .retrieve()
        .bodyToMono(UploadReceipt.class);
~~~

Trong ví dụ:

- `metadata` được serialize theo JSON codec vì part có Content-Type JSON.
- `file` được gửi như một Resource.
- `MultipartBodyBuilder` tạo multipart parts và writer tạo boundary.
- `retrieve().bodyToMono(...)` giải mã response.

Đây là đoạn minh họa phía client; cần khai báo `webClient`, `metadata`, `resource` và `UploadReceipt`. Với file lớn, hãy chọn Resource/Publisher phù hợp và test streaming thay vì đọc toàn bộ file vào byte[] trước khi gửi.

## 12. Phân biệt @RequestPart, @RequestBody, @RequestParam và PartEvent

| API | Dùng khi | Hình dạng dữ liệu |
| --- | --- | --- |
| `@RequestPart("metadata") DTO` | Cần giải mã một part thành object | Một part có Content-Type tương ứng |
| `@RequestPart("file") FilePart` | Cần lưu hoặc chuyển tiếp file upload | FilePart |
| `@RequestPart("part") Part` | Cần headers/content thô của một part | Part |
| `@RequestBody Mono<MultiValueMap<String, Part>>` | Cần tất cả part theo tên trong một map | MultiValueMap |
| `ServerWebExchange.getMultipartData()` | Cần truy cập map multipart ở mức exchange | Mono<MultiValueMap> |
| `@RequestBody Flux<PartEvent>` | Cần đọc multipart tuần tự, streaming | Flux<PartEvent> |
| `@ModelAttribute` | Form upload theo command object | DTO có field text và FilePart |

Chọn API theo cách sử dụng:

- Form nhỏ, có metadata và một file: `@RequestPart` là lựa chọn rõ ràng.
- Cần duyệt nhiều file hoặc nhiều part cùng tên: map access có thể thuận tiện.
- File lớn hoặc relay multipart sang service khác: `PartEvent` giúp giữ streaming và backpressure.
- Chỉ cần một field văn bản đơn giản: `FormFieldPart.value()` hoặc DTO phù hợp.

## 13. Bảo mật khi nhận file upload

Multipart upload là một ranh giới nhận dữ liệu không đáng tin cậy. Các giá trị như filename, Content-Type, metadata và bytes đều do client kiểm soát.

### 13.1. Không tin filename

`FilePart.filename()` là tên do client gửi. Không dùng trực tiếp nó trong:

~~~java
Path destination = uploadDirectory.resolve(file.filename());
~~~

Cách này có thể mở đường cho path traversal, ghi đè file hoặc tạo tên khó kiểm soát. Hãy tạo tên ngẫu nhiên từ server:

~~~java
Path destination = uploadDirectory.resolve(
        UUID.randomUUID() + ".bin");
~~~

Nếu cần giữ tên gốc để hiển thị, lưu như metadata đã sanitize; không dùng nó làm path.

### 13.2. Không tin Content-Type

Client có thể gửi `Content-Type: image/png` cho nội dung không phải PNG. Kiểm tra MIME header chỉ là bước đầu.

Với loại file quan trọng:

- Kiểm tra magic bytes hoặc signature thực tế.
- Kiểm tra cấu trúc file bằng parser phù hợp.
- Giới hạn loại file theo allowlist.
- Không chỉ dựa vào extension.
- Không phục vụ file upload dưới cùng origin với nội dung ứng dụng nếu không cần.
- Quét malware hoặc kiểm tra nội dung theo yêu cầu nghiệp vụ.

### 13.3. Giới hạn dung lượng và số lượng

Đặt giới hạn cho:

- Tổng request body ở gateway/server.
- Số lượng part.
- Dung lượng non-file part trong memory.
- Dung lượng file part trên disk.
- Số file mỗi user hoặc mỗi request.
- Thời gian upload và tốc độ tối thiểu nếu hệ thống cần chống slow upload.
- Dung lượng lưu trữ theo user/tenant.

`maxInMemorySize` không phải tổng request size. `maxDiskUsagePerPart` không phải tổng dung lượng tất cả file part. Hãy kết hợp nhiều lớp limit.

### 13.4. Chống path traversal và ghi đè

- Dùng tên server-generated.
- Lưu file ngoài thư mục web root.
- Không ghép input trực tiếp vào path.
- Nếu bắt buộc dùng tên client làm phần metadata, chuẩn hóa và sanitize trước khi hiển thị.
- Kiểm tra quyền truy cập theo user/tenant.
- Dùng thao tác tạo file an toàn để tránh overwrite.
- Xử lý file dở dang nếu upload lỗi hoặc bị cancel.

### 13.5. Temporary storage và cleanup

Reader có thể ghi file part lớn ra thư mục tạm. Cần:

- Chọn thư mục temp có quyền truy cập phù hợp.
- Theo dõi dung lượng đĩa.
- Cấu hình maxDiskUsagePerPart.
- Dọn part storage sau khi xử lý nếu code tự quản lý Part.
- Xử lý error/cancel để không giữ file tạm vô hạn.
- Không coi temp directory là kho lưu trữ lâu dài.

### 13.6. Không block event loop

Không dùng `Files.copy`, `InputStream.read` hoặc `block()` trực tiếp trên event-loop trong controller reactive. Dùng `FilePart.transferTo` hoặc API streaming reactive. Nếu có thư viện blocking bắt buộc, chuyển công việc đó sang scheduler phù hợp và giới hạn concurrency.

## 14. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| HTTP 415 Unsupported Media Type | Request hoặc part có Content-Type không phù hợp | Kiểm tra Content-Type toàn request và từng part |
| JSON part không deserialize được | Part metadata không có `application/json` hoặc codec không hỗ trợ | Đặt Content-Type cho part và kiểm tra Jackson/codec |
| Không tìm thấy part | Tên trong `@RequestPart` khác `name` client gửi | Đồng bộ tên part trong API contract |
| FilePart bị null hoặc argument resolution fail | Part không có filename hoặc không phải file part | Kiểm tra cách client tạo multipart file |
| Upload bị DataBufferLimitException | Non-file part vượt maxInMemorySize | Giới hạn metadata hoặc cấu hình reader phù hợp |
| Hết dung lượng temp storage | File part lớn, nhiều upload đồng thời hoặc thiếu cleanup | Giới hạn disk, quota, temp directory và lifecycle |
| File ghi đè file khác | Dùng filename client làm destination | Tạo tên đích server-generated |
| Path traversal | Filename chứa đường dẫn hoặc `..` | Không dùng filename làm path |
| Client gửi file giả MIME | Tin Content-Type từ request | Kiểm tra signature/nội dung thực tế |
| Controller không còn đọc được raw body | Đã gọi getMultipartData hoặc body đã được parse | Chọn một cách đọc multipart nhất quán |
| Upload lớn dùng quá nhiều memory | Gom toàn bộ multipart vào map hoặc byte[] | Dùng PartEvent streaming và backpressure |
| Temp file không được xóa | Tự đọc Part nhưng bỏ qua delete/cleanup | Compose Part.delete hoặc cleanupMultipart |
| Dữ liệu bị đọc hai lần | Part content không được cache như MultiValueMap | Chỉ consume nội dung part một lần |
| Event stream bị leak buffer | PartEvent content không được consume/relay/release | Xử lý mọi DataBuffer và quản lý cancellation |
| Dùng @RequestBody DTO cho multipart | DTO body không tương đương multipart part binding | Dùng @RequestPart hoặc PartEvent |
| Gọi block trong controller | Chặn event-loop | Compose Mono/Flux và dùng transferTo |

## 15. Kiểm thử multipart có ý nghĩa

Một bộ test nên bao gồm:

1. JSON metadata hợp lệ và file hợp lệ.
2. Thiếu part bắt buộc `metadata`.
3. Thiếu file part.
4. JSON part sai Content-Type.
5. JSON sai cấu trúc hoặc validation thất bại.
6. File rỗng.
7. Nhiều file cùng tên part.
8. Part count vượt giới hạn.
9. Non-file metadata vượt maxInMemorySize.
10. File vượt maxDiskUsagePerPart.
11. Filename chứa `../`, backslash hoặc ký tự lạ.
12. Content-Type giả mạo.
13. Upload bị cancel giữa chừng.
14. Transfer lỗi do thư mục đích không ghi được.
15. Cleanup file tạm sau success/error/cancel.
16. Streaming PartEvent với file chia thành nhiều event.

Dùng `WebTestClient` để gửi multipart request thực. Với file lớn hoặc cancellation, nên có integration test qua server runtime và proxy tương tự production; unit test đơn lẻ không tái hiện đầy đủ buffer, disk và network behavior.

## 16. Checklist trước khi đưa multipart upload vào production

- [ ] Endpoint khai báo đúng `consumes = multipart/form-data` hoặc media type contract cần thiết.
- [ ] Tên part được định nghĩa rõ và nhất quán với client.
- [ ] JSON part có Content-Type đúng và được giải mã vào DTO riêng.
- [ ] Metadata dùng Bean Validation.
- [ ] File part được nhận bằng `FilePart` khi cần transferTo.
- [ ] Destination path do server tạo, không dựa trên filename client.
- [ ] File type được kiểm tra bằng nội dung thực tế khi cần.
- [ ] Có giới hạn memory, disk, part count và tổng request.
- [ ] Temp directory có quyền và dung lượng phù hợp.
- [ ] Part storage được cleanup theo lifecycle.
- [ ] PartEvent buffer được tiêu thụ, relay hoặc release.
- [ ] Không block event loop.
- [ ] Có authentication, authorization, quota và rate limit.
- [ ] Có xử lý file dở dang khi lỗi/cancel.
- [ ] Test success, validation error, missing part, size limit và cancellation.
- [ ] Không log nội dung file, token hoặc metadata nhạy cảm.

## 17. Tự kiểm tra

**Câu 1.** `@RequestPart("metadata") UploadMetadata` làm gì?

Lấy part tên metadata và giải mã nội dung theo Content-Type của part thành UploadMetadata.

**Câu 2.** Vì sao JSON part cần Content-Type `application/json`?

Vì Spring chọn HTTP message reader dựa trên target type và media type của part. Content-Type không phù hợp có thể khiến không có codec nào đọc được.

**Câu 3.** `Part` và `FilePart` khác nhau thế nào?

FilePart mở rộng Part, đại diện file upload và bổ sung filename cùng transferTo(Path).

**Câu 4.** Có nên dùng `file.filename()` làm đường dẫn lưu file không?

Không. Filename do client cung cấp và có thể chứa path traversal hoặc ký tự nguy hiểm. Tạo tên lưu trữ từ server.

**Câu 5.** `FilePart.transferTo(Path)` trả về gì?

`Mono<Void>` báo quá trình ghi file hoàn tất hoặc lỗi.

**Câu 6.** `Part.content()` trả kiểu gì?

`Flux<DataBuffer>`. Khi tự đọc raw buffer, phải quản lý việc consume/release đúng ownership.

**Câu 7.** `ServerWebExchange.getMultipartData()` có đọc body thành map không?

Có. Nó trả `Mono<MultiValueMap<String, Part>>` và cache map; nội dung từng part không được cache và chỉ đọc một lần.

**Câu 8.** Muốn đọc multipart tuần tự mà không gom vào MultiValueMap thì dùng gì?

`@RequestBody Flux<PartEvent>` với PartEventHttpMessageReader.

**Câu 9.** `maxInMemorySize` có phải tổng dung lượng request không?

Không. Nó giới hạn phần bộ nhớ cho mỗi part theo cách DefaultPartHttpMessageReader xử lý; file part lớn có thể được ghi ra temp storage.

**Câu 10.** Khi tự dùng Part qua BodyExtractors, làm sao xóa file tạm?

Compose `Part.delete()` hoặc cơ chế `ServerWebExchange.cleanupMultipart()` vào pipeline cleanup; không gọi Mono cleanup rồi bỏ qua.

**Câu 11.** Vì sao không nên dùng `@RequestPart` cho mọi file cực lớn?

Vì named-part access theo map cần phân tích multipart và cung cấp part theo tên. `Flux<PartEvent>` cho phép xử lý tuần tự với backpressure.

**Câu 12.** Một PartEvent file có thể có nhiều event không?

Có. File lớn có thể được chia thành nhiều FilePartEvent; event cuối của part có `isLast()` bằng true.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — Multipart Content trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html): @RequestPart, Part, FilePart, DTO JSON, validation, MultiValueMap và PartEvent.
- [Spring Framework — Reactive Core: Multipart Data](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): ServerWebExchange.getMultipartData, reader mặc định, streaming PartEvent, codec và giới hạn multipart.
- [DefaultPartHttpMessageReader JavaDoc](https://docs.spring.io/spring-framework/docs/7.0.8/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html): maxInMemorySize, maxDiskUsagePerPart, maxParts, file storage directory và header limit.
- [Part JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/Part.html): name, headers, content và delete.
- [FilePart JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/FilePart.html): filename và transferTo.
- [PartEvent JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/PartEvent.html): event, content buffer và isLast.
- [ServerWebExchange JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): getMultipartData và cleanupMultipart.
- [RFC 7578 — Returning Values from Forms: multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578.html): định dạng multipart/form-data, boundary, Content-Disposition và filename.

**Ghi nhớ:** `@RequestPart` truy cập một part theo tên và có thể giải mã JSON part thành DTO; `Part` đại diện mọi loại part với headers/content/delete; `FilePart` bổ sung filename và transferTo. Named-part access tiện cho form upload thông thường, còn `Flux<PartEvent>` phù hợp với streaming file lớn. Luôn đặt giới hạn memory/disk/part count, không tin filename hoặc Content-Type từ client, và quản lý cleanup của part cùng DataBuffer theo đúng lifecycle.