# Gửi form và multipart bằng BodyInserters, MultipartBodyBuilder

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Gửi yêu cầu WebClient

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt form URL-encoded với multipart/form-data và chọn đúng định dạng cho dữ liệu gửi đi.
2. Dùng `BodyInserters.fromFormData` để gửi form có một hoặc nhiều giá trị cho cùng một key.
3. Dùng `BodyInserters.fromMultipartData` và `MultipartBodyBuilder` để tạo multipart request có text, JSON metadata và file.
4. Thiết lập content type, filename và header riêng cho từng part; hiểu vì sao multipart boundary phải do writer tạo.
5. Chọn `Resource` phù hợp cho file upload, nhận biết resource có thể đọc lại và publisher chỉ phát một lần.
6. Gửi part bất đồng bộ, giữ streaming và tránh gom file lớn vào heap.
7. Xử lý response, lỗi 4xx/5xx, timeout và retry của WebClient theo đúng semantics của request body.
8. Kiểm thử request form và multipart bằng một receiver WebFlux cùng `WebTestClient`.

## 1. Hai định dạng gửi form thường gặp

Một form HTML hoặc HTTP client có thể gửi dữ liệu theo hai định dạng phổ biến:

| Định dạng | Content-Type | Cách biểu diễn | Dùng khi |
| --- | --- | --- | --- |
| URL-encoded form | `application/x-www-form-urlencoded` | Các cặp key/value được encode trong body | Form chủ yếu là text, số, lựa chọn đơn giản. |
| Multipart form | `multipart/form-data; boundary=...` | Body gồm nhiều part, mỗi part có header và nội dung riêng | Form có file, JSON metadata hoặc nhiều loại payload. |

### 1.1. URL-encoded form

Ví dụ dữ liệu:

```text
name=Lan&city=Ha+Noi&tag=java&tag=reactive
```

Mỗi cặp key/value được encode theo quy tắc form URL-encoded. Dấu cách thường được biểu diễn bằng `+`; các ký tự đặc biệt được percent-encode. Một key có thể xuất hiện nhiều lần, ví dụ `tag` trong ví dụ trên có hai giá trị.

Định dạng này gọn, dễ xử lý và phù hợp với form chỉ chứa text. Nó không cung cấp cấu trúc part độc lập để gắn filename hoặc content type riêng cho từng file.

### 1.2. Multipart form

Multipart chia body thành các part. Mỗi part có header riêng như `Content-Disposition` và có thể có `Content-Type`:

```text
--boundary
Content-Disposition: form-data; name="description"

Monthly report
--boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"category":"finance","confidential":true}
--boundary
Content-Disposition: form-data; name="file"; filename="report.txt"
Content-Type: text/plain

...file bytes...
--boundary--
```

`boundary` là chuỗi phân cách do multipart writer tạo và đặt trong Content-Type của toàn request. Mỗi part có thể chứa text, JSON, byte array hoặc Resource. Multipart phù hợp khi một thao tác cần gửi cả metadata có cấu trúc và file.

Không tự nối chuỗi boundary hoặc tự dựng body multipart bằng string. Writer của Spring chịu trách nhiệm escape header, encode part, thêm boundary và kết thúc body đúng định dạng.

## 2. BodyInserters nằm ở đâu trong WebClient?

`WebClient` xây dựng request bằng fluent API. Khi cần gửi body, `RequestBodySpec` có thể nhận một object qua `bodyValue` hoặc nhận một `BodyInserter` qua `body`.

`BodyInserters` cung cấp các factory method để tạo inserter theo định dạng body:

- `fromValue(object)`: serialize một object thông thường bằng codec phù hợp.
- `fromPublisher(publisher, elementClass)`: ghi dữ liệu từ publisher.
- `fromFormData(key, value)` hoặc `fromFormData(multiValueMap)`: tạo URL-encoded form.
- `fromMultipartData(key, value)` hoặc `fromMultipartData(multiValueMap)`: tạo multipart body.

Ví dụ một request URL-encoded:

```java
webClient.post()
        .uri("/registrations")
        .body(BodyInserters.fromFormData("name", "Lan")
                .with("city", "Ha Noi"))
        .retrieve()
        .bodyToMono(RegistrationResult.class);
```

`BodyInserters.fromFormData` trả về form inserter. Gọi `with` để thêm field khác; gọi `with` nhiều lần cùng key để gửi nhiều giá trị cho key đó.

Không cần tự serialize form thành chuỗi rồi đặt vào `bodyValue`. Form inserter chọn writer tương ứng và thiết lập media type phù hợp.

## 3. Gửi URL-encoded form bằng BodyInserters

### 3.1. Form có vài field

Ví dụ:

```java
Mono<RegistrationResult> result = webClient.post()
        .uri("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .body(BodyInserters.fromFormData("name", "Lan")
                .with("email", "lan@example.com")
                .with("city", "Ha Noi"))
        .retrieve()
        .bodyToMono(RegistrationResult.class);
```

`contentType` có thể khai báo rõ định dạng mong muốn. Form inserter cũng biết cách ghi URL-encoded form. Khi dùng form inserter, không cần tự gọi `URLEncoder` cho từng field; writer xử lý việc encode.

### 3.2. Gửi nhiều giá trị cho cùng một key

HTML checkbox, multi-select hoặc một số API có thể nhận một key với nhiều giá trị. Dùng `with` nhiều lần:

```java
BodyInserters.FormInserter<String> form =
        BodyInserters.fromFormData("name", "Lan")
                .with("tag", "java")
                .with("tag", "spring")
                .with("tag", "reactive");

Mono<RegistrationResult> result = webClient.post()
        .uri("/registrations")
        .body(form)
        .retrieve()
        .bodyToMono(RegistrationResult.class);
```

Server nhận ba giá trị cho key `tag`. Không chuyển thành chuỗi phân tách bằng dấu phẩy nếu contract của server mong đợi các giá trị lặp; dấu phẩy có thể là dữ liệu hợp lệ bên trong một value.

### 3.3. Dùng MultiValueMap

Khi form đã có sẵn trong một cấu trúc dữ liệu, dùng `MultiValueMap<String, String>`:

```java
MultiValueMap<String, String> fields = new LinkedMultiValueMap<>();
fields.add("name", "Lan");
fields.add("tag", "java");
fields.add("tag", "reactive");

Mono<RegistrationResult> result = webClient.post()
        .uri("/registrations")
        .body(BodyInserters.fromFormData(fields))
        .retrieve()
        .bodyToMono(RegistrationResult.class);
```

`LinkedMultiValueMap` giữ nhiều value cho một key. Phương thức `add` thêm một giá trị; `set` thay các giá trị hiện có bằng một giá trị duy nhất.

### 3.4. Khi nào không dùng URL-encoded?

Không chọn URL-encoded nếu cần gửi file binary hoặc mỗi field có content type riêng. Có thể encode file thành Base64 trong một field text, nhưng cách đó làm payload lớn hơn, tạo thêm chi phí encode/decode và thường buộc server giữ một chuỗi lớn trong bộ nhớ. Với file upload, multipart hoặc giao thức streaming chuyên biệt phù hợp hơn.

## 4. Gửi multipart bằng BodyInserters.fromMultipartData

Multipart inserter có thể được tạo trực tiếp từ key/value:

```java
Mono<UploadReceipt> result = webClient.post()
        .uri("/uploads")
        .body(BodyInserters.fromMultipartData("description", "Monthly report")
                .with("category", "finance")
                .with("file", resource))
        .retrieve()
        .bodyToMono(UploadReceipt.class);
```

Cách này phù hợp với multipart đơn giản. Khi cần nhiều cấu hình trên từng part, chẳng hạn JSON metadata, filename hoặc content type riêng, `MultipartBodyBuilder` dễ đọc và dễ mở rộng hơn.

## 5. MultipartBodyBuilder: xây dựng từng part

`MultipartBodyBuilder` tạo `MultiValueMap<String, HttpEntity<?>>`. Mỗi part có thể có body và headers riêng.

Ví dụ:

```java
MultipartBodyBuilder builder = new MultipartBodyBuilder();

builder.part("description", "Monthly report");

builder.part("metadata", new UploadMetadata("finance", true))
        .contentType(MediaType.APPLICATION_JSON);

builder.part("file", resource)
        .filename("report.txt")
        .contentType(MediaType.TEXT_PLAIN);

MultiValueMap<String, HttpEntity<?>> parts = builder.build();

Mono<UploadReceipt> result = webClient.post()
        .uri("/uploads")
        .body(BodyInserters.fromMultipartData(parts))
        .retrieve()
        .bodyToMono(UploadReceipt.class);
```

Ở đây:

- `description` là part text.
- `metadata` là object được serialize thành JSON vì part có content type `application/json`.
- `file` là Resource; part có filename và media type riêng.
- `build()` tạo map dùng làm input cho multipart inserter.

Mỗi part có thể được cấu hình bằng các method trên builder trả về từ `part`:

| Method | Ý nghĩa |
| --- | --- |
| `contentType(MediaType)` | Đặt Content-Type cho part. |
| `filename(String)` | Đặt filename trong Content-Disposition. |
| `header(name, value)` | Thêm header riêng cho part. |
| `headers(Consumer<HttpHeaders>)` | Điều chỉnh headers của part. |

Tên field phải khớp contract của server. Ví dụ server nhận `@RequestPart("metadata")` thì client phải gửi part tên `metadata`; đổi thành `meta` sẽ khiến server không tìm thấy part.

### 5.1. Part JSON

Khi gửi object metadata, khai báo content type rõ ràng:

```java
builder.part("metadata", new UploadMetadata("finance", true))
        .contentType(MediaType.APPLICATION_JSON);
```

Codec JSON sẽ serialize object thành JSON part. Nếu server mong đợi một chuỗi text thay vì JSON object, hãy gửi string với content type tương ứng. Không mặc định mọi part đều là text/plain.

Nếu part có custom header hoặc cần điều khiển disposition, dùng `headers`/`header` trên PartBuilder. Chỉ thêm header mà server contract thực sự cần.

### 5.2. Filename và Content-Disposition

File part thường có header tương tự:

```http
Content-Disposition: form-data; name="file"; filename="report.txt"
Content-Type: text/plain
```

Filename là metadata do client gửi. Server không được xem filename là đường dẫn lưu file đáng tin cậy. Khi lưu file, tạo tên đích do server kiểm soát, chuẩn hóa hoặc loại bỏ path component, kiểm tra quyền và giới hạn kích thước. Không ghép trực tiếp filename từ client vào đường dẫn filesystem.

### 5.3. Boundary do writer tạo

Một multipart request có Content-Type ở mức toàn request như:

```text
Content-Type: multipart/form-data; boundary=generated-boundary
```

Mỗi part được phân cách bằng boundary đó. Với `BodyInserters.fromMultipartData` và `MultipartBodyBuilder`, Spring multipart writer chịu trách nhiệm tạo boundary và ghi header phù hợp.

Không tự đặt một boundary trong header nhưng lại ghi body bằng boundary khác. Không tự đặt `Content-Length` nếu chưa biết chính xác số byte sau khi serialize. Khi có Resource hoặc publisher streaming, độ dài có thể không biết trước và transport có thể dùng cơ chế truyền phù hợp.

Thông thường, hãy để multipart writer tự thiết lập Content-Type và boundary. Nếu có lý do phải đặt media type, chỉ đặt `MediaType.MULTIPART_FORM_DATA` và để writer bổ sung boundary; không tự chế giá trị boundary.

## 6. Chọn Resource cho file upload

`Resource` là abstraction của Spring cho dữ liệu như file, classpath resource hoặc byte array. Một vài lựa chọn thường gặp:

| Resource | Nguồn dữ liệu | Lưu ý |
| --- | --- | --- |
| `FileSystemResource` | File trên filesystem | Thích hợp cho file có thể mở lại; thường biết filename và có thể biết content length. |
| `ClassPathResource` | File trong classpath | Phù hợp file mẫu/asset đi cùng ứng dụng. |
| `ByteArrayResource` | Mảng byte trong memory | Dễ test và có thể đọc lại; toàn bộ payload đã ở trong heap. |
| `InputStreamResource` | InputStream | Thường chỉ đọc một lần; retry hoặc ghi lại body có thể thất bại. |

Ví dụ file trên filesystem:

```java
Resource file = new FileSystemResource("/data/reports/report.pdf");

MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("file", file)
        .filename("report.pdf")
        .contentType(MediaType.APPLICATION_PDF);
```

Ví dụ byte array trong test:

```java
Resource file = new ByteArrayResource(
        "hello multipart".getBytes(StandardCharsets.UTF_8)) {
    @Override
    public String getFilename() {
        return "hello.txt";
    }
};
```

`ByteArrayResource` mặc định không nhất thiết có filename phù hợp cho upload. Có thể override `getFilename()` hoặc gọi `filename` trên part builder.

### 6.1. Repeatability và retry

WebClient có thể retry request khi lỗi tạm thời, nhưng body upload phải có khả năng được tạo lại. `FileSystemResource` thường có thể mở file lại. `ByteArrayResource` có thể đọc lại vì dữ liệu nằm trong mảng byte. `InputStreamResource` thường dựa trên một stream đã tiêu thụ và không thể phát lại.

Không retry mù quáng một multipart upload. Cần xem xét:

- Body publisher có thể subscribe lại không?
- Resource có thể mở lại từ đầu không?
- Server đã nhận và xử lý request trước khi kết nối bị đứt chưa?
- Endpoint có hỗ trợ idempotency key hoặc kiểm tra upload trùng không?

Một timeout ở phía client không chứng minh server chưa lưu file. Với thao tác tạo tài nguyên, retry có thể tạo bản ghi hoặc file trùng nếu API không có cơ chế idempotency.

## 7. Gửi part bất đồng bộ và streaming

`MultipartBodyBuilder` còn hỗ trợ `asyncPart` để gửi nội dung từ Publisher. Đây là lựa chọn khi dữ liệu part đến từ một stream thay vì một object có sẵn:

```java
Flux<DataBuffer> fileContent = dataBufferPublisher;

MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("description", "Streaming upload");

builder.asyncPart("file", fileContent, DataBuffer.class)
        .filename("stream.bin")
        .contentType(MediaType.APPLICATION_OCTET_STREAM);

Mono<UploadReceipt> result = webClient.post()
        .uri("/uploads")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .retrieve()
        .bodyToMono(UploadReceipt.class);
```

Đây là **đoạn minh họa**; `dataBufferPublisher` phải cung cấp buffer theo lifecycle hợp lệ. Publisher chỉ nên được tiêu thụ theo subscription do WebClient quản lý. Không gọi `subscribe()` riêng để đẩy file vào request.

Khi làm việc trực tiếp với `DataBuffer`:

- Không giữ buffer pooled sau khi publisher đã chuyển quyền sở hữu.
- Không release buffer trước khi writer đọc xong.
- Nếu tự tạo buffer thay thế, xác định rõ buffer cũ và mới do thành phần nào release.
- Truyền error và cancellation từ nguồn dữ liệu lên request.
- Giới hạn tốc độ và bộ nhớ của nguồn; không gom toàn bộ stream vào `byte[]` chỉ để tạo multipart.

Với file lớn, dùng Resource hoặc publisher streaming phù hợp và kiểm thử với file gần giới hạn thực tế. Đừng dùng `ByteArrayResource` cho file nhiều gigabyte vì nó yêu cầu payload nằm trong heap.

## 8. Nhận multipart ở phía WebFlux server

Client multipart chỉ thành công nếu server hiểu tên part và kiểu dữ liệu tương ứng. Annotated controller có thể dùng `@RequestPart` cho field thông thường, JSON part và file part:

```java
@PostMapping(
        value = "/uploads",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<UploadReceipt> upload(
        @RequestPart("description") String description,
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") FilePart file) {

    return Mono.just(new UploadReceipt(
            description,
            metadata.category(),
            file.filename(),
            0L));
}
```

`@RequestPart` dùng message reader phù hợp để giải mã part. JSON part cần content type phù hợp để codec JSON chọn đúng reader. File part được biểu diễn bằng `FilePart`, có filename, headers và publisher nội dung.

Nếu muốn lưu file, dùng `FilePart.transferTo(destination)` hoặc streaming sang storage service. Tạo destination path từ ID/tên do server sinh; không tin path client gửi. Ví dụ ý tưởng:

```java
Path destination = uploadDirectory.resolve(serverGeneratedName);

return file.transferTo(destination)
        .thenReturn(new UploadReceipt(
                description,
                metadata.category(),
                serverGeneratedName,
                knownSize));
```

Đây là **đoạn minh họa**; `uploadDirectory` phải là thư mục đã cấu hình, `serverGeneratedName` phải được tạo an toàn và `knownSize` phải được xác định bằng cách phù hợp. Thực tế cần kiểm tra dung lượng, quyền, loại file, tên file, antivirus/scanning khi phù hợp và xử lý file dở dang nếu transfer lỗi.

### 8.1. Nhận URL-encoded form

Với form text, controller có thể nhận `MultiValueMap<String, String>`:

```java
@PostMapping(
        value = "/registrations",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public Mono<RegistrationResult> register(
        @RequestBody MultiValueMap<String, String> form) {

    return Mono.just(new RegistrationResult(
            form.getFirst("name"),
            form.getOrDefault("tag", List.of())));
}
```

`getFirst` lấy giá trị đầu tiên; `get("tag")` có thể chứa nhiều giá trị. Kiểm tra field bắt buộc và validate dữ liệu ở server. Client có thể gửi payload tùy ý, nên không coi việc form được serialize đúng định dạng là bằng chứng dữ liệu hợp lệ.

## 9. Xử lý response và lỗi từ WebClient

Gửi body thành công không đồng nghĩa server đã chấp nhận nghiệp vụ. Hãy đọc status và response body theo contract.

### 9.1. retrieve() và lỗi 4xx/5xx

`retrieve()` mặc định chuyển response 4xx/5xx thành `WebClientResponseException` nếu không cấu hình status handler:

```java
Mono<UploadReceipt> result = webClient.post()
        .uri("/uploads")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .retrieve()
        .onStatus(HttpStatusCode::is4xxClientError, response ->
                response.bodyToMono(String.class)
                        .defaultIfEmpty("Upload rejected")
                        .map(UploadRejectedException::new))
        .onStatus(HttpStatusCode::is5xxServerError, response ->
                Mono.error(new UploadServiceException(
                        "Upload service failed")))
        .bodyToMono(UploadReceipt.class);
```

Đây là **đoạn minh họa**; exception constructor và error DTO do ứng dụng định nghĩa. Handler 4xx có thể đọc response body để tạo exception nghiệp vụ; handler 5xx có thể che chi tiết nội bộ bằng lỗi ổn định. Nếu không cần custom mapping, giữ mặc định và xử lý `WebClientResponseException` ở tầng gọi.

### 9.2. exchangeToMono() khi cần kiểm soát toàn response

`exchangeToMono` phù hợp khi cần phân nhánh theo status hoặc headers:

```java
Mono<UploadReceipt> result = webClient.post()
        .uri("/uploads")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(UploadReceipt.class);
            }
            return response.createError();
        });
```

Sau callback, WebClient quản lý việc giải phóng response body theo contract của API. Nếu tự đọc body, không bỏ quên trường hợp status lỗi. Chỉ dùng `exchangeToMono` khi cần kiểm soát response; nếu mapping đơn giản, `retrieve` ngắn hơn.

### 9.3. Timeout và retry

Có thể đặt timeout cho toàn thao tác:

```java
webClient.post()
        .uri("/uploads")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .retrieve()
        .bodyToMono(UploadReceipt.class)
        .timeout(Duration.ofSeconds(30));
```

Timeout phải phù hợp với kích thước file và tốc độ mạng. Một upload lớn có thể cần timeout dài hoặc chính sách idle timeout riêng. Không retry mọi exception: lỗi validation 400 không tự hết khi thử lại, còn lỗi kết nối sau khi server đã lưu file có thể gây upload trùng. Dùng retry có giới hạn, backoff và idempotency khi contract hỗ trợ.

## 10. Chương trình Spring Boot 3.3.5 chạy được

Ví dụ dưới đây dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5** và WebFlux. Ứng dụng có receiver nhận URL-encoded form và multipart; một WebClient sender gọi hai endpoint đó. Integration test chạy WebClient thật tới server random port và kiểm tra các field nhận được.

Cấu trúc:

```text
webclient-form-multipart/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── FormMultipartApplication.java
    │   ├── UploadMetadata.java
    │   ├── UploadReceipt.java
    │   ├── FormReceipt.java
    │   ├── UploadController.java
    │   ├── UploadClient.java
    │   └── DemoController.java
    └── test/java/demo/
        └── UploadClientIntegrationTest.java
```

### 10.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webclient-form-multipart</artifactId>
    <version>1.0.0</version>

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

### 10.2. FormMultipartApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormMultipartApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormMultipartApplication.class, args);
    }
}
```

### 10.3. UploadMetadata.java

```java
package demo;

public record UploadMetadata(String category, boolean confidential) {}
```

### 10.4. UploadReceipt.java

```java
package demo;

public record UploadReceipt(
        String description,
        String category,
        String filename,
        long bytes) {}
```

### 10.5. FormReceipt.java

```java
package demo;

import java.util.List;

public record FormReceipt(String name, List<String> tags) {}
```

### 10.6. UploadController.java

```java
package demo;

import java.util.List;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class UploadController {

    @PostMapping(
            value = "/receive/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<FormReceipt> receiveForm(
            @RequestBody MultiValueMap<String, String> form) {

        return Mono.just(new FormReceipt(
                form.getFirst("name"),
                form.getOrDefault("tag", List.of())));
    }

    @PostMapping(
            value = "/receive/multipart",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<UploadReceipt> receiveMultipart(
            @RequestPart("description") String description,
            @RequestPart("metadata") UploadMetadata metadata,
            @RequestPart("file") FilePart file) {

        return file.content()
                .map(buffer -> {
                    long size = buffer.readableByteCount();
                    DataBufferUtils.release(buffer);
                    return size;
                })
                .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
                .reduce(0L, Long::sum)
                .map(bytes -> new UploadReceipt(
                        description,
                        metadata.category(),
                        file.filename(),
                        bytes));
    }
}
```

Receiver đọc form thành MultiValueMap. Multipart endpoint giải mã JSON metadata và nhận file dưới dạng FilePart. Ví dụ đếm byte của file stream mà không gom toàn bộ file vào một mảng; mỗi DataBuffer được release sau khi đọc metadata về kích thước. Ứng dụng lưu file thật nên dùng storage transfer/streaming có kiểm soát thay vì chỉ đếm byte.

### 10.7. UploadClient.java

```java
package demo;

import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class UploadClient {
    private final WebClient client;

    public UploadClient(
            WebClient.Builder builder,
            @Value("http://localhost:8080") String receiverBaseUrl) {
        this.client = builder.baseUrl(receiverBaseUrl).build();
    }

    public Mono<FormReceipt> sendForm(String name, List<String> tags) {
        BodyInserters.FormInserter<String> form =
                BodyInserters.fromFormData("name", name);

        tags.forEach(tag -> form.with("tag", tag));

        return client.post()
                .uri("/receive/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(form)
                .retrieve()
                .bodyToMono(FormReceipt.class);
    }

    public Mono<UploadReceipt> sendMultipart(
            String description,
            UploadMetadata metadata,
            Resource file) {

        MultipartBodyBuilder builder = new MultipartBodyBuilder();

        builder.part("description", description);

        builder.part("metadata", metadata)
                .contentType(MediaType.APPLICATION_JSON);

        builder.part("file", file)
                .filename(file.getFilename() == null
                        ? "upload.bin"
                        : file.getFilename())
                .contentType(MediaType.APPLICATION_OCTET_STREAM);

        return client.post()
                .uri("/receive/multipart")
                .body(BodyInserters.fromMultipartData(builder.build()))
                .retrieve()
                .bodyToMono(UploadReceipt.class);
    }

    public Mono<UploadReceipt> sendSampleMultipart() {
        Resource file = new ByteArrayResource(
                "hello multipart".getBytes(java.nio.charset.StandardCharsets.UTF_8)) {
            @Override
            public String getFilename() {
                return "hello.txt";
            }
        };

        return sendMultipart(
                "Monthly report",
                new UploadMetadata("finance", true),
                file);
    }
}
```

`UploadClient` minh họa cả hai cách gửi. Base URL được cấu hình trong constructor; ví dụ mặc định chạy receiver trên cổng 8080. Trong môi trường thật, lấy URL từ cấu hình ứng dụng và dùng WebClient.Builder do Spring quản lý để giữ cấu hình connector, filter, TLS và timeout.

### 10.8. DemoController.java

```java
package demo;

import java.util.List;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    private final UploadClient uploadClient;

    public DemoController(UploadClient uploadClient) {
        this.uploadClient = uploadClient;
    }

    @PostMapping("/demo/send-form")
    public Mono<FormReceipt> sendForm() {
        return uploadClient.sendForm(
                "Lan",
                List.of("java", "spring", "reactive"));
    }

    @PostMapping("/demo/send-multipart")
    public Mono<UploadReceipt> sendMultipart() {
        return uploadClient.sendSampleMultipart();
    }
}
```

Hai endpoint demo gọi WebClient tới receiver cùng ứng dụng. Khi chạy mặc định trên cổng 8080, có thể gọi `POST /demo/send-form` và `POST /demo/send-multipart` để quan sát request client gửi và dữ liệu server nhận.

### 10.9. UploadClientIntegrationTest.java

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.web.reactive.function.client.WebClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UploadClientIntegrationTest {
    @LocalServerPort
    int port;

    private UploadClient client;

    @BeforeEach
    void setUp() {
        client = new UploadClient(
                WebClient.builder(),
                "http://localhost:" + port);
    }

    @Test
    void sendsUrlEncodedFormWithRepeatedKeys() {
        FormReceipt result = client.sendForm(
                        "Lan",
                        List.of("java", "reactive"))
                .block(Duration.ofSeconds(5));

        assertThat(result.name()).isEqualTo("Lan");
        assertThat(result.tags()).containsExactly("java", "reactive");
    }

    @Test
    void sendsMultipartTextJsonAndFileParts() {
        Resource file = new ByteArrayResource(
                "hello multipart".getBytes(StandardCharsets.UTF_8)) {
            @Override
            public String getFilename() {
                return "hello.txt";
            }
        };

        UploadReceipt result = client.sendMultipart(
                        "Monthly report",
                        new UploadMetadata("finance", true),
                        file)
                .block(Duration.ofSeconds(5));

        assertThat(result.description()).isEqualTo("Monthly report");
        assertThat(result.category()).isEqualTo("finance");
        assertThat(result.filename()).isEqualTo("hello.txt");
        assertThat(result.bytes()).isEqualTo(15);
    }
}
```

Trong test, `block` chỉ dùng để đợi kết quả trong test method. Code ứng dụng vẫn trả publisher và không block event loop. Test chạy server trên cổng ngẫu nhiên rồi tạo UploadClient trỏ đúng cổng đó, nhờ vậy không phụ thuộc cổng 8080 đang rảnh.

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

Thử gửi form:

```bash
curl -i -X POST http://localhost:8080/demo/send-form
```

Response có dữ liệu đã nhận:

```json
{
  "name": "Lan",
  "tags": ["java", "spring", "reactive"]
}
```

Thử gửi multipart:

```bash
curl -i -X POST http://localhost:8080/demo/send-multipart
```

Response minh họa:

```json
{
  "description": "Monthly report",
  "category": "finance",
  "filename": "hello.txt",
  "bytes": 15
}
```

Chạy integration test:

```bash
mvn test
```

Hai test thực hiện request qua WebClient tới WebFlux server thật. Test form xác nhận key lặp được giữ thành nhiều giá trị; test multipart xác nhận text, JSON metadata, filename và số byte file đều được giải mã đúng.

## 11. Giới hạn kích thước và bảo vệ file upload

Multipart giúp gửi nhiều loại dữ liệu trong một request, nhưng không tự làm upload an toàn. Server cần áp dụng giới hạn và kiểm tra theo contract:

- Giới hạn tổng request bytes, số part, kích thước từng part và header part.
- Cấu hình multipart reader để quyết định dữ liệu nhỏ giữ trong memory hay dữ liệu lớn ghi ra disk; theo dõi disk quota và dọn file tạm.
- Xác thực và phân quyền trước khi nhận upload lớn khi có thể.
- Không tin filename, extension hoặc Content-Type do client gửi. Kiểm tra nội dung thực tế theo nhu cầu nghiệp vụ.
- Sinh tên file lưu trữ ở server; tránh path traversal, ghi đè file khác và truy cập ngoài thư mục đích.
- Cân nhắc virus/malware scanning, checksum, quota theo user/tenant và retention.
- Dùng streaming để tránh gom toàn bộ file vào heap; giới hạn concurrent upload để kiểm soát disk, memory và kết nối.

`spring.codec.max-in-memory-size` có thể điều chỉnh giới hạn buffer của một số codec, nhưng không nên xem nó là quota tổng thể cho mọi multipart upload hoặc mọi byte đi qua server. Hãy cấu hình multipart reader và giới hạn transport/proxy theo phiên bản Spring đang dùng.

## 12. Các lỗi thường gặp và cách xử lý

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gửi file bằng URL-encoded text | Payload phình to và khó streaming | Dùng multipart hoặc upload protocol chuyên dụng. |
| Dùng `bodyValue` với chuỗi tự nối multipart | Boundary/header dễ sai và dữ liệu có thể hỏng | Dùng BodyInserters và MultipartBodyBuilder. |
| Quên field name khớp với server | `@RequestPart` không tìm thấy part | Đồng bộ tên part giữa client và receiver. |
| Gửi object metadata nhưng không đặt JSON content type | Server có thể chọn sai reader | Đặt `contentType(APPLICATION_JSON)` cho part. |
| Tự đặt boundary trong Content-Type | Boundary header và body có thể không khớp | Để multipart writer tạo boundary. |
| Gộp nhiều giá trị form thành một chuỗi | Server không nhận được repeated keys đúng contract | Dùng `with` nhiều lần hoặc MultiValueMap. |
| Dùng `InputStreamResource` rồi retry upload | Stream đã tiêu thụ, lần retry không có dữ liệu | Dùng Resource có thể mở lại hoặc tạo publisher mới. |
| Dùng ByteArrayResource cho file rất lớn | Giữ toàn bộ file trong heap | Dùng FileSystemResource hoặc publisher streaming. |
| Tự subscribe vào file publisher | Body tách khỏi WebClient request lifecycle | Truyền publisher vào asyncPart và để WebClient subscribe. |
| Quên filename | Server nhận part thiếu filename hoặc tên mặc định | Đặt filename rõ ràng khi contract cần. |
| Tự đặt Content-Length sai | Server có thể đọc thiếu hoặc chờ thêm byte | Để writer/transport tính độ dài khi có thể. |
| Retry upload không có idempotency | Có thể tạo file/bản ghi trùng | Dùng idempotency key và retry có giới hạn. |
| Không đọc response lỗi | Bỏ mất thông tin 4xx/5xx hữu ích | Dùng retrieve/onStatus hoặc exchangeToMono. |
| Dùng block trong service reactive | Chặn event loop và giảm throughput | Trả Mono/Flux, chỉ block ở ranh giới imperative/test. |
| Tin filename hoặc MIME type của client | Có thể ghi file nguy hiểm hoặc sai vị trí | Xác minh nội dung, tạo tên lưu trữ phía server và giới hạn upload. |
| Gom toàn bộ file vào byte array để đếm | Tăng memory theo kích thước file | Đếm/stream từng DataBuffer hoặc dùng storage transfer. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào nên dùng URL-encoded form?  
**Đáp án:** Khi body chủ yếu là các field text đơn giản và không cần metadata riêng cho từng part hoặc file binary.

**Câu 2.** Khi nào nên dùng multipart/form-data?  
**Đáp án:** Khi một request cần nhiều part độc lập, đặc biệt có file, JSON metadata và text field.

**Câu 3.** `BodyInserters.fromFormData` xử lý điều gì?  
**Đáp án:** Tạo form inserter URL-encoded, encode các cặp key/value và hỗ trợ nhiều giá trị cho cùng key qua `with`.

**Câu 4.** Vai trò của `MultipartBodyBuilder` là gì?  
**Đáp án:** Xây dựng từng part cùng body và headers riêng, sau đó tạo MultiValueMap cho multipart inserter.

**Câu 5.** Ai tạo multipart boundary?  
**Đáp án:** Multipart writer của Spring khi ghi request; không tự dựng boundary hoặc nối body multipart bằng chuỗi.

**Câu 6.** Làm sao gửi object metadata dưới dạng JSON part?  
**Đáp án:** Dùng `builder.part("metadata", object).contentType(MediaType.APPLICATION_JSON)`.

**Câu 7.** Vì sao `InputStreamResource` có thể gây vấn đề khi retry?  
**Đáp án:** InputStream thường chỉ đọc một lần. Request body retry có thể không tạo lại được dữ liệu đã tiêu thụ.

**Câu 8.** `FilePart` ở server đại diện cho gì?  
**Đáp án:** Một file part đã được multipart reader giải mã, có filename, headers và publisher nội dung; có thể chuyển sang storage bằng transferTo hoặc streaming.

**Câu 9.** `limitRate` hoặc backpressure có thay thế giới hạn kích thước upload không?  
**Đáp án:** Không. Demand đếm phần tử; server vẫn cần giới hạn byte, part count, disk usage và concurrent uploads.

**Câu 10.** Vì sao không nên retry upload sau timeout một cách vô điều kiện?  
**Đáp án:** Server có thể đã nhận và lưu file trước khi client timeout. Retry có thể tạo bản ghi/file trùng nếu API không có idempotency.

## Ghi nhớ

- Dùng `BodyInserters.fromFormData` cho URL-encoded form text; dùng `fromMultipartData` hoặc `MultipartBodyBuilder` cho multipart có nhiều part và file.
- Dùng `MultipartBodyBuilder.part` để đặt content type, filename và headers riêng. JSON metadata cần content type JSON để server chọn đúng codec.
- Để Spring multipart writer tạo boundary và xử lý encoding; không tự ghép body hoặc đặt boundary thủ công.
- Chọn Resource theo nguồn dữ liệu và khả năng đọc lại. File lớn nên streaming; InputStreamResource thường không phù hợp với retry.
- WebClient giữ request trong reactive lifecycle. Không tự subscribe hoặc block trong code ứng dụng; xử lý response lỗi và retry theo idempotency contract.
- Server phải giới hạn kích thước, số part và concurrent upload; không tin filename, extension hoặc MIME type từ client.

### Tài liệu tham khảo

1. [Spring Framework – WebClient Request Body](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html): gửi request body và BodyInserters.
2. [Spring Framework – Multipart Data](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html#webflux-client-body-multipart): multipart request và MultipartBodyBuilder.
3. [Spring Framework – WebFlux Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html): nhận multipart, @RequestPart và FilePart.
4. [Spring Framework – WebClient Response](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): retrieve, onStatus và xử lý response.
5. [Spring Framework – WebClient Exchange](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): exchangeToMono và kiểm soát response.
6. [Spring Framework – Resource Abstraction](https://docs.spring.io/spring-framework/reference/core/resources.html): Resource, FileSystemResource và ByteArrayResource.
7. [Spring Framework – MultipartBodyBuilder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/MultipartBodyBuilder.html): part, asyncPart và builder API.
