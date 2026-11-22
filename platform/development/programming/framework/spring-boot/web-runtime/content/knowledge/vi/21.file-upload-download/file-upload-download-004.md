# FilePart, Part và nhận multipart trong WebFlux

## 1. Mục tiêu và bối cảnh

Khi người dùng tải lên một ảnh kèm ghi chú, HTTP request thường có `Content-Type: multipart/form-data`. Body được chia thành các **part**: một part chứa file, part khác chứa văn bản hoặc JSON. Trong **Spring WebFlux**, các abstraction chính để nhận multipart là `Part`, `FilePart`, `FormFieldPart` và, khi xử lý từng sự kiện của luồng dữ liệu, `PartEvent`.

Sau bài học, bạn có thể:

- Đọc cấu trúc `multipart/form-data`, phân biệt tên trường (part name) với tên file (filename) và phân biệt multipart với JSON body thông thường.
- Dùng `@RequestPart` để nhận một `FilePart` và một `FormFieldPart` trong Spring WebFlux.
- Hiểu các phương thức `Part.name()`, `Part.headers()`, `Part.content()`, `Part.delete()`; `FilePart.filename()` và `FilePart.transferTo(...)`.
- Chọn `@RequestBody Mono<MultiValueMap<String, Part>>` khi cần xử lý tập hợp part, hoặc `@RequestBody Flux<PartEvent>` khi cần duyệt multipart theo luồng.
- Viết endpoint Java 17+/Spring Boot 3.x để lưu file bằng tên sinh trên server, không chặn event loop bằng `block()` hoặc các thao tác file đồng bộ trên event loop.
- Đặt giới hạn dung lượng, số part, xử lý lỗi, xác thực và phân quyền để upload an toàn.

**Phạm vi:** Spring Boot WebFlux reactive, ví dụ dùng Reactor Netty. Không dùng `MultipartFile` hay `jakarta.servlet.http.Part` của Servlet/MVC để thay thế cho các interface multipart của WebFlux.

## 2. Multipart là gì?

Một HTTP request JSON thông thường có **một body** được biểu diễn theo `application/json`. Multipart cũng chỉ là **một HTTP request**, nhưng body của nó có nhiều phần. Mỗi phần có header riêng và body riêng.

Ví dụ rút gọn một request upload file và ghi chú:

~~~http
POST /api/uploads HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=MyBoundary123

--MyBoundary123
Content-Disposition: form-data; name="note"

Bài thực hành WebFlux
--MyBoundary123
Content-Disposition: form-data; name="file"; filename="example.txt"
Content-Type: text/plain

Xin chào từ một file.
--MyBoundary123--
~~~

Trong request thực tế, giữa header và body có dòng trống chuẩn CRLF; dấu boundary kết thúc xác định ranh giới part. Đoạn trên phục vụ đọc hiểu, không phải tệp raw bytes cần gửi thủ công.

Đọc từ trên xuống:

1. `Content-Type` của **toàn request** là `multipart/form-data`, mang tham số `boundary`.
2. `name="note"` và `name="file"` là **tên part**; server sử dụng tên này để tìm và bind tham số.
3. `filename="example.txt"` là **tên tệp mà client khai báo**; nó không phải đường dẫn lưu trữ tin cậy.
4. Part file có thể khai báo `Content-Type: text/plain`; đây cũng là dữ liệu **do client cung cấp**, cần kiểm tra trước khi tin tưởng.
5. Boundary đầu và cuối do HTTP client/browser tạo. Không tự đặt header `Content-Type: multipart/form-data` mà quên boundary; hãy để `curl -F` hoặc browser `FormData` thiết lập đúng.

Một request có thể có nhiều file với **cùng part name** (`files`) hoặc các tên khác nhau. Vì vậy, tập hợp multipart tổng quát là **multi-value map**, không chỉ `Map<String, Part>` đơn trị.

Không nhầm:

| Định dạng body | Ý nghĩa |
| --- | --- |
| `application/json` | Một tài liệu JSON thông thường |
| `application/x-www-form-urlencoded` | Form text encode cặp khóa–giá trị, không phải file multipart |
| `multipart/form-data` | Form có nhiều part, thường gồm file và text |
| `multipart/mixed` | Tập hợp các phần theo quy ước multipart khác, ví dụ file + JSON trong API |
| `multipart/related` | Các phần có quan hệ nội dung với nhau |

Spring WebFlux có codec hỗ trợ nhiều loại multipart; nhưng endpoint khai báo `consumes = multipart/form-data` sẽ chỉ chấp nhận media type phù hợp điều kiện đó.

## 3. Part, FilePart, FormFieldPart và PartEvent

Nhập đúng package WebFlux:

~~~java
import org.springframework.http.codec.multipart.Part;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.FormFieldPart;
import org.springframework.http.codec.multipart.PartEvent;
~~~

Các interface này **khác** `org.springframework.web.multipart.MultipartFile` và `jakarta.servlet.http.Part` trong stack Servlet.

| Kiểu | Mô tả | Thông tin/hành động chính |
| --- | --- | --- |
| `Part` | Interface chung cho một part đã được parser nhận dạng | `name()`, `headers()`, `content()`, `delete()` |
| `FilePart extends Part` | Part đại diện cho tệp upload | `filename()`, `transferTo(Path)`, thừa hưởng các phương thức `Part` |
| `FormFieldPart extends Part` | Part là trường form văn bản | `value()` trả giá trị chuỗi đã giải mã |
| `PartEvent` | Sự kiện trong luồng multipart khi đọc từng part/đoạn dữ liệu | `headers()`, `content()`, `isLast()` |
| `FilePartEvent` / `FormPartEvent` | Sự kiện của file / form field | `filename()` hoặc `value()` tương ứng |

### 3.1. Part.name() khác FilePart.filename()

Với:

~~~http
Content-Disposition: form-data; name="file"; filename="invoice.pdf"
~~~

- `part.name()` trả `"file"`: tên trường mà `@RequestPart("file")` tìm.
- `filePart.filename()` trả tên file do client khai báo, ví dụ `"invoice.pdf"`.
- Không có API nào trong hai phương thức này tự quyết định nơi lưu file trên server.

Client có thể tự gửi `filename="../../secret.txt"` hoặc chuỗi chứa ký tự bất thường. **Không ghép `file.filename()` vào đường dẫn lưu trữ** rồi gọi `transferTo(...)`. Hãy sinh tên bằng UUID/ID do server quản lý, kiểm tra quyền truy cập và chỉ lưu tên gốc dưới dạng metadata nếu cần.

### 3.2. Part.content(): dữ liệu dưới dạng publisher

`Part.content()` trả `Flux<DataBuffer>`. `DataBuffer` biểu diễn các đoạn byte; nó không có nghĩa toàn file đã được gom thành một mảng byte trong RAM. Khi bạn subscribe/compose pipeline, dữ liệu được tiêu thụ theo quy tắc của publisher.

- Có thể xử lý từng buffer, chuyển tiếp qua WebClient hoặc ghi xuống storage.
- Một số buffer (ví dụ trên Reactor Netty) được pool và quản lý bằng reference count; khi code tự xử lý buffer phải bảo đảm **consume/relay/release** đúng cách.
- Đừng tùy tiện `collectList()`, `DataBufferUtils.join(...)` hoặc chuyển cả file thành `byte[]` với file lớn: đó có thể là điểm dồn dữ liệu vào bộ nhớ.
- Không subscribe thủ công bên trong controller rồi trả response thành công ngay. Hãy **return Mono/Flux** đại diện cho quá trình xử lý để Spring theo dõi hoàn thành hoặc thất bại.

### 3.3. FilePart.transferTo(...)

`FilePart.transferTo(Path destination)` trả `Mono<Void>`: khi publisher hoàn thành, thao tác chuyển/lưu file tại đích đã kết thúc theo hợp đồng API. Code thường nên ghép tiếp `then(...)` hoặc `thenReturn(...)` thay vì gọi `block()`.

Không khẳng định mọi hệ thống file/storage đều non-blocking tuyệt đối: I/O đĩa có thể phải dùng cơ chế asynchronous I/O hoặc worker phù hợp. Nhưng ở tầng controller WebFlux, hãy compose publisher thay vì chặn event loop.

`Part.delete()` cũng trả publisher, phục vụ xóa tài nguyên được lưu tạm liên quan đến part khi cần. Quản lý tài nguyên tạm còn phụ thuộc codec và lifecycle request; không nên coi file upload đã nằm trong kho lưu bền vững trước khi pipeline ghi thành công.

## 4. Cách WebFlux xử lý multipart trước khi vào controller

Luồng xử lý khái quát:

~~~text
Client (FormData/curl -F)
    |
    v
HTTP request: Content-Type: multipart/form-data; boundary=...
    |
    v
Reactor Netty + WebFlux HTTP codecs
    |
    +--> đọc headers, boundary và các part
    |      |
    |      +--> form field -> FormFieldPart
    |      '--> file -> FilePart
    |
    v
@RequestPart("file") và @RequestPart("note")
    |
    v
Controller trả Mono/Flux
    |
    +--> validate metadata, chọn đường dẫn lưu
    +--> file.transferTo(target)
    '--> khi ghi xong: trả JSON/status
~~~

Các lớp xử lý thực tế gồm decoder/reader, argument resolver, Reactor publisher và storage. Đừng hiểu sơ đồ trên là “toàn bộ file luôn phải được nạp vào RAM trước controller”. Khi parser multipart dùng chiến lược bộ nhớ/tệp tạm, file lớn có thể được spool xuống đĩa. Ngược lại, **map-based multipart** có thể buộc framework nhận diện toàn bộ cấu trúc parts trước khi trả về tập hợp; đó không giống luồng `PartEvent`.

Ba lối vào thường gặp:

1. `@RequestPart("file") FilePart file`: lấy đúng một part tên `file`, lý tưởng cho form upload thông dụng.
2. `@RequestBody Mono<MultiValueMap<String, Part>> parts` hoặc `ServerWebExchange.getMultipartData()`: cần xem toàn bộ các part theo tên, kể cả tên lặp.
3. `@RequestBody Flux<PartEvent> events`: muốn xử lý **tuần tự theo sự kiện** và kiểm soát streaming cho tải lớn hoặc chuyển tiếp.

## 5. Ví dụ hoàn chỉnh: WebFlux nhận file và form field

Thực hành với **Java 17+**, **Spring Boot 3.3.5**, Maven và `spring-boot-starter-webflux`. Ví dụ dùng một thư mục tương đối `uploaded-files` ở working directory khi chạy ứng dụng. Không cần database và không có tệp upload được phục vụ công khai tự động.

### 5.1. Cấu trúc dự án

~~~text
webflux-upload/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/upload/
        │   ├── UploadApplication.java
        │   └── UploadController.java
        └── resources/
            └── application.properties
~~~

**Tệp `pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>com.example</groupId>
    <artifactId>webflux-upload</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Chỉ thêm starter WebFlux cho lab. Nếu đồng thời thêm `spring-boot-starter-web`, Spring Boot thông thường sẽ ưu tiên stack MVC theo classpath; điều này có thể làm bạn tưởng đang học WebFlux nhưng thực tế controller chạy trên Servlet stack.

**Tệp `src/main/resources/application.properties`**

~~~properties
server.port=8080

# Các giới hạn minh họa cho multipart WebFlux
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=10MB
spring.webflux.multipart.max-parts=8
~~~

Ba thuộc tính liên quan đến parser multipart của WebFlux:

- `max-in-memory-size` giới hạn kích thước part không phải file có thể giữ trong bộ nhớ; với file, giá trị này dùng làm **ngưỡng chuyển sang lưu tạm trên đĩa** trong chế độ parser thông thường.
- `max-disk-usage-per-part` giới hạn dung lượng lưu tạm trên đĩa cho **mỗi part** phù hợp; đây không nhất thiết là giới hạn tổng toàn request.
- `max-parts` giới hạn số lượng part trong một request.

Giá trị 10MB/8 part chỉ là cấu hình cho bài lab. Đối với production, phải tính thêm tổng request size, gateway/proxy limits, dung lượng đĩa, tốc độ upload và giới hạn kinh doanh. Với luồng `PartEvent`, một số giới hạn lưu tạm trên đĩa của kiểu reader map-based **không còn là lớp bảo vệ giống nhau**; cần tự thực thi giới hạn byte khi stream.

**Tệp `src/main/java/com/example/upload/UploadApplication.java`**

~~~java
package com.example.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadApplication.class, args);
    }
}
~~~

**Tệp `src/main/java/com/example/upload/UploadController.java`**

~~~java
package com.example.upload;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.FormFieldPart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api")
public class UploadController {

    // Không đặt dưới static/public của web application.
    private final Path storageRoot = Path.of("uploaded-files")
            .toAbsolutePath()
            .normalize();

    @PostMapping(
            path = "/uploads",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<UploadReceipt>> upload(
            @RequestPart("file") FilePart file,
            @RequestPart("note") FormFieldPart note) {

        String originalName = file.filename();
        String noteValue = note.value();

        if (originalName == null || originalName.isBlank()) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Tên tệp không hợp lệ"));
        }
        if (noteValue.length() > 200) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Ghi chú quá 200 ký tự"));
        }

        // ID do server sinh; KHÔNG dùng filename của client làm path.
        String fileId = UUID.randomUUID().toString();
        Path target = storageRoot.resolve(fileId + ".bin");

        // Files.createDirectories là I/O đồng bộ:
        // chuyển thao tác này sang boundedElastic.
        Mono<Path> prepareDirectory = Mono.fromCallable(
                () -> Files.createDirectories(storageRoot))
                .subscribeOn(Schedulers.boundedElastic());

        return prepareDirectory
                .then(file.transferTo(target))
                .thenReturn(ResponseEntity.status(HttpStatus.CREATED)
                        .body(new UploadReceipt(
                                fileId, originalName, noteValue)));
    }

    public record UploadReceipt(
            String fileId, String originalFilename, String note) {}
}
~~~

**Tại sao code trên có những lựa chọn này?**

1. `@RequestPart("file")` khớp `name="file"` trong multipart; kiểu `FilePart` cho phép biết tên file và transfer dữ liệu.
2. `@RequestPart("note") FormFieldPart` nhận một form field văn bản; `note.value()` lấy chuỗi đã được giải mã.
3. `Files.createDirectories(...)` là thao tác filesystem đồng bộ, nên được bọc trong `Mono.fromCallable(...)` và chạy qua `Schedulers.boundedElastic()`. Đây là phần cần tránh làm ngay trên event loop khi tải cao.
4. `file.transferTo(target)` trả `Mono<Void>`. `then(...)` chỉ tiếp tục sau khi chuẩn bị thư mục xong; `thenReturn(...)` chỉ trả response sau khi transfer hoàn thành.
5. `fileId` do server sinh, còn `originalFilename` chỉ để minh họa metadata nhận được. Trong hệ thống thật, bạn vẫn nên giới hạn/chuẩn hóa tên hiển thị và không dùng nó như tên tệp tin cậy.
6. `ResponseEntity.status(HttpStatus.CREATED)` tạo status 201 cho bản ghi upload thành công, body JSON do Jackson serialize từ `record`.

**Giới hạn của ví dụ:** minh họa giao thức, không phải dịch vụ lưu trữ production. Chưa có xác thực, kiểm tra content signatures, virus scanning, quota, retry/idempotency, lưu metadata database hoặc dọn file orphan khi request bị hủy sau lúc ghi. Nếu cần bảo đảm tuyệt đối file không bị ghi đè trong hệ thống nhiều node, dùng kho lưu trữ và thao tác tạo mới có cơ chế atomic phù hợp; UUID ở đây chủ yếu để tránh dùng tên client.

### 5.2. Chạy và kiểm tra bằng curl

Trong thư mục `webflux-upload`, cần JDK 17+ và Maven, chạy:

~~~bash
mvn spring-boot:run
~~~

Tạo file để tải lên; ví dụ trong Bash:

~~~bash
printf 'Xin chao WebFlux\n' > sample.txt
~~~

Trên Windows PowerShell, có thể tạo nội dung tương tự bằng `Set-Content -Path sample.txt -Value 'Xin chao WebFlux'`, hoặc dùng file bất kỳ có sẵn trên máy.

Gửi multipart:

~~~bash
curl -i -X POST http://localhost:8080/api/uploads \
  -F "file=@sample.txt;type=text/plain" \
  -F "note=Hoc WebFlux"
~~~

Lệnh nhiều dòng phía trên theo cách xuống dòng của Bash; có thể viết thành một dòng trên Windows PowerShell:

~~~powershell
curl.exe -i -X POST http://localhost:8080/api/uploads -F "file=@sample.txt;type=text/plain" -F "note=Hoc WebFlux"
~~~

Khi endpoint và filesystem hoạt động, kỳ vọng:

- Status **201 Created**.
- Response `Content-Type` tương thích JSON.
- Body có ba field `fileId`, `originalFilename`, `note`. `fileId` là UUID mới ở mỗi lần gọi, không có giá trị stdout cố định.
- Tệp lưu trong thư mục `uploaded-files` với tên dạng `<UUID>.bin`. Nội dung byte đúng theo `sample.txt`; phần mở rộng `.bin` là tên lưu trữ chủ động, không xác nhận media type.

Ví dụ **cấu trúc** body (UUID thật sẽ thay đổi):

~~~json
{
  "fileId": "9244ab23-1d77-4bfb-b03e-556179eac90f",
  "originalFilename": "sample.txt",
  "note": "Hoc WebFlux"
}
~~~

Không tự gõ `Content-Type: multipart/form-data` trong request `curl -F`: curl tự tạo boundary chính xác. Nếu tự áp header không chứa boundary, parser có thể báo body multipart không hợp lệ.

### 5.3. Kiểm tra các lỗi cơ bản

**Thiếu part bắt buộc `file`:**

~~~bash
curl -i -F "note=Hoc WebFlux" http://localhost:8080/api/uploads
~~~

Thông thường nhận lỗi 400 do thiếu request part bắt buộc; body lỗi cụ thể thay đổi theo cấu hình Spring Boot.

**Gửi JSON vào endpoint chỉ nhận multipart:**

~~~bash
curl -i -H "Content-Type: application/json" \
  --data '{"note":"Hoc WebFlux"}' \
  http://localhost:8080/api/uploads
~~~

Vì mapping `consumes = multipart/form-data`, kỳ vọng **415 Unsupported Media Type** trong cấu hình lab.

**File quá lớn so với giới hạn parser:** server hoặc tầng proxy có thể từ chối trong lúc đọc multipart. Mã status và lỗi chính xác cần xác minh trên bản Spring Boot/server/proxy và exception handler đang dùng; không nên khẳng định mọi giới hạn upload luôn trả một mã cố định.

**Ghi file lỗi:** khi thư mục không có quyền ghi hoặc đĩa đầy, publisher `transferTo` sẽ báo lỗi; nếu không xử lý riêng, server thường trả lỗi phía server. Đừng trả `201` khi thao tác lưu chưa hoàn thành.

## 6. @RequestPart và @RequestParam khác nhau trong WebFlux

Trong Spring MVC Servlet, `@RequestParam` có thể nhận form field và `MultipartFile` theo cách phổ biến. Nhưng **WebFlux `@RequestParam` chủ yếu liên kết query parameters**, vì các nguồn dữ liệu (query/form/multipart) được mô hình hóa tách biệt. Để nhận part rõ ràng trong WebFlux, dùng `@RequestPart` hoặc data binding cho command object khi phù hợp.

| Mục đích | Chữ ký điển hình trong WebFlux |
| --- | --- |
| Query parameter `?page=2` | `@RequestParam("page") int page` |
| Một file multipart tên `file` | `@RequestPart("file") FilePart file` |
| Một form field multipart tên `note` | `@RequestPart("note") FormFieldPart note` |
| Một JSON part có `Content-Type: application/json` | `@RequestPart("metadata") MetaData metadata` |
| Cần mọi part theo tên | `@RequestBody Mono<MultiValueMap<String, Part>> body` |
| Duyệt part theo thứ tự và buffer | `@RequestBody Flux<PartEvent> events` |

**JSON part:** nếu một part tên `metadata` chứa JSON, ví dụ `{"title":"hướng dẫn","public":false}` và header của **chính part** là `Content-Type: application/json`, WebFlux có thể deserialize trực tiếp thành Java object nhờ message reader.

Mẫu chữ ký sau là **minh họa**, cần có controller, record/POJO và logic lưu file trước khi chạy độc lập:

~~~java
record MetaData(String title, boolean isPublic) {}

@PostMapping(path = "/with-meta",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> withMeta(
        @RequestPart("metadata") Mono<MetaData> metadata,
        @RequestPart("file") FilePart file) {
    return metadata.map(m -> m.title());
}
~~~

Trong đoạn ngắn này, `file` chỉ là tham số minh họa và **không được lưu**; không sử dụng nguyên đoạn như upload endpoint production. Điểm cần học là `@RequestPart("metadata") Mono<MetaData>` có thể giải mã JSON của **một part** qua codec và sử dụng reactive chain. Khi thử:

~~~bash
curl -i -F 'metadata={"title":"guide","isPublic":false};type=application/json' \
  -F "file=@sample.txt" http://localhost:8080/api/with-meta
~~~

Đây là cú pháp của Bash, dùng khi bạn đã thực sự bổ sung handler trên cùng đường dẫn vào controller. Nếu dùng PowerShell, cách đặt nháy kép/escape JSON khác Bash; cần xem raw multipart trong HTTP client nếu gặp lỗi.

Có thể thêm `@Valid` cùng `@RequestPart` khi khai báo validation; lỗi validation trong WebFlux có thể thành `WebExchangeBindException` và status 400 hoặc loại lỗi validation phương thức khác tùy signature. Không trộn cách bắt `MethodArgumentNotValidException` điển hình của MVC vào mọi trường hợp WebFlux.

## 7. Xử lý toàn bộ request dưới dạng MultiValueMap<String, Part>

Khi cần nhận **nhiều part**, bao gồm các tên part lặp, WebFlux hỗ trợ:

~~~java
@PostMapping(path = "/inspect",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<Integer> inspect(
        @RequestBody Mono<MultiValueMap<String, Part>> body) {
    return body.map(parts ->
            parts.values().stream().mapToInt(List::size).sum());
}
~~~

Đây là **đoạn method minh họa**, cần đặt vào một `@RestController` và import `Mono`, `MultiValueMap`, `Part`, `List` cùng `MediaType`/`PostMapping`/`RequestBody` để biên dịch. Kết quả là **số lượng part**, ví dụ một file và một ghi chú trả `2`. Đoạn minh họa này **không lưu file**, không đọc nội dung file và chưa áp dụng giới hạn nghiệp vụ; không sử dụng để thay thế endpoint upload cần lưu dữ liệu.

Ví dụ map có thể chứa:

~~~text
"file"   -> [FilePart(filename="a.txt"), FilePart(filename="b.txt")]
"note"   -> [FormFieldPart(value="Hai file")]
~~~

Đây là cấu trúc khái niệm, không phải `toString()` chuẩn của các class. Dùng `parts.get("file")` để lấy danh sách cùng tên thay vì giả định chỉ có một file.

Khi gọi `ServerWebExchange.getMultipartData()`, framework phân tích body rồi **cache kết quả multipart data để truy cập lại** thông qua exchange. Sau đó không nên cố đọc lại raw request body riêng từ `getRequest().getBody()`: request body là dòng dữ liệu tiêu thụ một lần, và đường truy cập qua multipart cache mới là cơ chế phù hợp.

**Lưu ý về bộ nhớ:** `Mono<MultiValueMap<String, Part>>` đại diện một **bộ sưu tập part đã nhận diện**, không đồng nghĩa toàn bộ file bytes đều là một `byte[]` trên heap. Parser có thể chuyển file lớn sang tệp tạm. Tuy vậy, toàn bộ cấu trúc multipart phải được phân tích/thu thập và có thể tạo áp lực memory/disk; nếu cần xử lý từng buffer của stream lớn thì xem `PartEvent`.

## 8. FilePart.content(), DataBuffer và việc giải phóng tài nguyên

Giả sử bạn muốn đọc byte file bằng API mức thấp:

~~~java
Flux<DataBuffer> buffers = file.content();
~~~

Đây là **đoạn minh họa tại nơi đã có biến `FilePart file`**; chưa phải một ứng dụng hoàn chỉnh. Một `DataBuffer` là đoạn dữ liệu, không nhất thiết tương ứng với một file hoặc một part đầy đủ.

**Cần xử lý đúng lifecycle buffer.** Khi dùng codec và `FilePart.transferTo(...)` ở mức cao, framework đảm nhiệm nhiều chi tiết vòng đời. Khi bạn trực tiếp giữ/thao tác `DataBuffer`, phải bảo đảm buffer được tiêu thụ/chuyển tiếp/giải phóng theo API đã chọn, bao gồm đường lỗi/hủy.

Ví dụ chống mẫu nên tránh:

~~~java
// KHÔNG LÀM trong WebFlux request handler:
byte[] allBytes = file.content()
        .map(buffer -> {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return bytes;
        })
        .collectList()
        .block()
        .get(0);
~~~

Đoạn trên **cố tình sai** để nhận diện lỗi:

1. `block()` gây blocking và có thể bị từ chối trên event-loop thread của Reactor.
2. `collectList()` giữ dữ liệu trong memory, không phù hợp file lớn.
3. `get(0)` chỉ lấy buffer đầu, **không phải toàn bộ file**.
4. Không giải phóng các `DataBuffer` sau khi đọc thủ công, có thể gây rò rỉ memory/buffer pool.

Nếu chỉ cần lưu file vào filesystem, ưu tiên `transferTo(target)`. Nếu cần nội dung để gửi đến object storage, kiểm virus, tính hash hay chuyển tiếp network, thiết kế pipeline streaming rõ ràng, xác định giới hạn byte, quản lý buffer, retry/cancellation và API storage phù hợp.

**Không tự subscribe rồi trả thành công trước khi công việc xong:**

~~~java
// KHÔNG LÀM:
file.transferTo(target).subscribe();
return Mono.just("OK");
~~~

Server có thể trả `OK` trước khi ghi xong; lỗi trong subscription có thể xảy ra sau response và khó theo dõi. Thay bằng:

~~~java
// Đúng trong handler đã có biến file và target:
return file.transferTo(target).thenReturn("OK");
~~~

Bản đúng chỉ hoàn thành sau khi ghi thành công, và lỗi ghi sẽ truyền qua publisher.

## 9. Streaming multipart bằng PartEvent

Với `@RequestBody Flux<PartEvent>`, bạn không yêu cầu WebFlux gom các part thành `MultiValueMap` trước khi bắt đầu xử lý. Mỗi part tạo một hoặc nhiều event:

- `FormPartEvent`: thông thường một event mang giá trị của một trường văn bản.
- `FilePartEvent`: một hoặc nhiều event mang từng đoạn file; event đầu có thể dùng để xác định filename và các header.
- `PartEvent.isLast()` cho biết event cuối cùng của **part hiện tại**, không nhất thiết là event cuối của cả request.

Một mẫu phân nhóm khái niệm:

~~~java
Flux<Flux<PartEvent>> windows =
        allEvents.windowUntil(PartEvent::isLast);
~~~

Trong đó `allEvents` là tham số kiểu `Flux<PartEvent>` đã được inject vào controller. Mỗi window ứng với các event của một part; để xử lý lần lượt và tránh nuốt stream, dùng `concatMap`. Có thể dùng `switchOnFirst` để đọc event đầu, xem đó là file hay form field, rồi tiếp tục xử lý đủ các event của window.

### 9.1. Ví dụ độc lập về tiêu thụ events mà không lưu file

Nếu chỉ cần đếm **event** (không phải file/part), có thể thêm method sau vào một `@RestController` WebFlux đã import `Flux`, `Mono`, `PartEvent`, `DataBufferUtils` và các annotation:

~~~java
@PostMapping(path = "/count-events",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<Long> countEvents(
        @RequestBody Flux<PartEvent> events) {
    return events
            .doOnNext(event ->
                    DataBufferUtils.release(event.content()))
            .count();
}
~~~

Endpoint này **cố ý tiêu thụ và release từng buffer** mà không lưu payload; response là số event quan sát được. File lớn có thể sinh nhiều event, nên **không được dùng con số đó làm số lượng file**. Trong một ứng dụng thật, cần thêm giới hạn tổng byte để ngăn client upload dữ liệu lớn kéo dài. Khi viết pipeline phức tạp với cancellation, phải rà soát cả đường discard và lỗi để không làm rò rỉ buffer.

### 9.2. Khi thực sự chuyển file thành luồng

Pipeline streaming điển hình ở mức thiết kế:

~~~text
Flux<PartEvent> từ request
    |
    v
windowUntil(PartEvent::isLast)
    |
    v
switchOnFirst để xem FormPartEvent / FilePartEvent
    |
    +--> FormPartEvent: đọc value, kiểm tra giới hạn
    |
    '--> FilePartEvent:
           - đọc filename (metadata không tin cậy)
           - lấy từng DataBuffer trong đúng window
           - đếm byte, giới hạn dung lượng
           - chuyển tiếp/ghi xuống storage
           - tiêu thụ hoặc release toàn bộ buffer
           - xử lý lỗi, hủy và file ghi dở
    |
    v
Hoàn thành Mono -> response
~~~

Đây là flow thiết kế, không phải code production sẵn có. Nếu implement streaming thật, nên có bộ đếm byte cho từng part và tổng request, xử lý window tuần tự khi cần, giữ giới hạn đồng thời, tách I/O blocking khỏi event loop, đồng thời xóa file ghi dở nếu upload thất bại.

**Quan trọng:** Một số property về temporary storage của multipart map-based reader, ví dụ `file-storage-directory` và `max-disk-usage-per-part`, không phải lớp giới hạn tương đương cho `PartEvent` streaming. Không mặc định rằng bật ngưỡng đĩa của parser sẽ bảo vệ mọi endpoint streaming.

## 10. Hệ thống reactive không đồng nghĩa không còn I/O blocking

WebFlux hướng tới xử lý I/O theo publisher và số lượng event-loop threads hạn chế. Nhưng code do bạn viết có thể vẫn blocking:

| Thao tác | Nguy cơ | Cách xử lý |
| --- | --- | --- |
| `FilePart.transferTo(Path)` | Có publisher theo hợp đồng API; không chặn controller bằng `block()` | Return/compose `Mono<Void>` và theo dõi lỗi |
| `Files.createDirectories`, `Files.exists`, `Files.readAllBytes` | API filesystem đồng bộ | Với việc cần làm trong request, dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` hoặc giải pháp async |
| JDBC truyền thống | Blocking database I/O | Dùng R2DBC nếu phù hợp hoặc cô lập blocking worker/pool |
| SDK object-storage đồng bộ | Chiếm thread khi gọi mạng/ghi đĩa | Dùng async client nếu có; nếu bắt buộc, offload và giới hạn concurrency |
| `Mono.block()` trong handler | Chặn thread và phá luồng reactive | Ghép `flatMap`, `then`, `thenReturn`, `onErrorResume` |
| Gọi `subscribe()` tùy tiện bên trong handler | Công việc “fire-and-forget” khó quản lý lỗi/hủy | Return publisher đại diện cho toàn bộ nghiệp vụ |

Ví dụ quan trọng trong `UploadController`:

~~~java
Mono<Path> prepareDirectory = Mono.fromCallable(
        () -> Files.createDirectories(storageRoot))
        .subscribeOn(Schedulers.boundedElastic());

return prepareDirectory
        .then(file.transferTo(target))
        .thenReturn(receipt);
~~~

Đây là **đoạn minh họa thuộc controller đã có biến `receipt`**, không phải method đầy đủ. `subscribeOn(boundedElastic)` đưa thao tác tạo thư mục blocking sang scheduler thích hợp; `then(...)` giữ thứ tự chuẩn bị rồi lưu file. Cũng cần xem giới hạn số task khi có hàng ngàn upload đồng thời; offload không làm đĩa hoặc network nhanh vô hạn.

## 11. Giới hạn tài nguyên và bảo vệ endpoint upload

Không nên dựa vào một property duy nhất để tuyên bố upload an toàn.

### 11.1. Các thuộc tính WebFlux thường dùng trong Spring Boot 3.3

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=10MB
spring.webflux.multipart.max-parts=8
spring.webflux.multipart.max-headers-size=10KB
# Nếu cần, có thể chỉ định thư mục tạm:
# spring.webflux.multipart.file-storage-directory=/var/tmp/webflux-multipart
~~~

Ý nghĩa:

- `max-in-memory-size` điều tiết bộ nhớ của **non-file part** và ngưỡng spool-to-disk cho **file part** trong parser thông thường.
- `max-disk-usage-per-part` giới hạn đĩa tạm cho **mỗi part** trong chế độ reader tương ứng.
- `max-parts` chống gửi quá nhiều part trong một request.
- `max-headers-size` hạn chế header lớn trong từng part.
- `file-storage-directory` là nơi đặt file tạm của multipart parser; khác với thư mục **lưu bền vững** mà service tự chọn.

Các giới hạn này **không thay** giới hạn tổng bytes toàn HTTP request của proxy/gateway/server hoặc giới hạn nghiệp vụ theo user. Những giá trị mặc định phụ thuộc phiên bản; kiểm tra tài liệu tương ứng trước khi quyết định production.

### 11.2. Tránh nhầm thuộc tính Servlet

Trong WebFlux thuần, đừng áp các ví dụ Servlet rồi nghĩ chúng sẽ giới hạn `FilePart`:

~~~properties
# Những dòng dưới thuộc stack Servlet/MVC,
# không phải bộ cấu hình chính cho WebFlux multipart:
spring.servlet.multipart.max-file-size=10MB
spring.servlet.multipart.max-request-size=20MB
~~~

Đúng với ví dụ WebFlux là nhóm `spring.webflux.multipart.*`. Nếu ứng dụng chạy Spring MVC do classpath chứa cả WebFlux và MVC, hãy xác định **stack đang chạy thật** trước khi điều chỉnh cấu hình.

### 11.3. Kiểm soát bảo mật

- **Xác thực và phân quyền:** ai được upload, upload vào thư mục/kho nào, và ai được đọc file về sau? Kiểm tra ở tầng nghiệp vụ, không dựa vào tên file.
- **Path traversal:** không bao giờ lấy `FilePart.filename()` để ghép trực tiếp thành `storageRoot.resolve(filename)`. Kẻ tấn công có thể dùng `../`, separator, ký tự unicode lạ hoặc tên đặc biệt.
- **Content type giả mạo:** `FilePart.headers().getContentType()` là dữ liệu client tự khai báo. Nếu chỉ cho phép PNG/PDF, cần kiểm tra **nội dung byte**, định dạng hợp lệ và chính sách nghiệp vụ.
- **Quét mã độc / nội dung hoạt động:** dữ liệu upload có thể chứa nội dung độc hại; cân nhắc malware scanning, sandbox và kiểm soát tải xuống.
- **Giới hạn tài nguyên:** đặt tổng size, từng file, số part, thời gian request, quota/user, giới hạn upload đồng thời và rate limit.
- **Tệp công khai:** không lưu file vào `src/main/resources/static` hoặc public web root rồi vô tình cung cấp URL truy cập trực tiếp, đặc biệt với dữ liệu riêng tư.
- **Xử lý lỗi:** tệp ghi dở khi mất kết nối hoặc vượt quota cần dọn. Gắn metadata vào DB/object storage theo trình tự và độ bền thích hợp.
- **Logging:** log request ID, kích thước, trạng thái và ID file do server sinh; tránh đưa toàn bộ nội dung hoặc filename nhạy cảm vào log.
- **Tải xuống:** đặt `Content-Disposition`, kiểm soát media type và các header an toàn để browser không diễn giải nội dung không đáng tin theo cách ngoài dự kiến.

## 12. Các mã lỗi và cách chẩn đoán

| Hiện tượng | Giải thích cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| 400 khi thiếu `file` hoặc `note` | `@RequestPart` bắt buộc không tìm thấy tên part phù hợp | So chính xác `name` trong multipart với annotation |
| 400 khi boundary/body hỏng | Parser không tách được các part đúng cấu trúc | Để HTTP client tự tạo boundary, xem raw request |
| 415 khi gửi JSON vào endpoint `consumes=multipart/form-data` | Sai media type của request | Dùng `curl -F`/`FormData` hoặc sửa hợp đồng API |
| Lỗi kích thước part / HTTP 413 hoặc status khác | Parser/proxy đã áp giới hạn; mã cụ thể tùy tầng xử lý | Xem log, exception và giới hạn WebFlux/gateway thực tế |
| 500 khi ghi file | Quyền thư mục, đĩa đầy, storage bị lỗi hoặc bug | Theo dõi error signal từ `transferTo` và thiết kế cleanup |
| Có status 201 nhưng file chưa được lưu | Gọi `subscribe()` rồi trả thành công quá sớm | Trả về publisher chứa toàn bộ tác vụ lưu |
| Event-loop warning / latency p99 tăng | Gọi blocking I/O/`block()` trong handler | Profile thread, offload blocking hoặc dùng async client |
| Không bind được trường `note` | Nhầm `@RequestParam` với `@RequestPart` trong WebFlux | Nhận `FormFieldPart` hoặc command object phù hợp |
| Tên file bị thay đổi/chèn `../` | Tin dữ liệu `filename` từ client | Sinh ID/path server-side và chuẩn hóa metadata |
| Hết bộ nhớ khi file lớn | Dồn `DataBuffer` vào một array/collection | Dùng `transferTo` hoặc streaming có giới hạn |
| `Flux<PartEvent>` gây memory leak | Buffer không được tiêu thụ/release | Rà soát lifecycle buffer, error/cancel/discard |
| Local tốt, production lỗi | Proxy size limit, temp dir, container filesystem/permission | Đo từng tầng, cấu hình quota và dùng storage phù hợp |

**Quy trình gỡ lỗi theo thứ tự:**

1. Xác nhận ứng dụng thật sự chạy **WebFlux** và controller thuộc stack reactive.
2. Xem HTTP request: `Content-Type`, boundary, part names, part headers và payload size.
3. Đối chiếu annotation: `@RequestPart("file")` trùng với `name="file"`, media type trùng `consumes`.
4. Xem nguyên nhân exception ở parser, argument binding, validation hay I/O file; đừng chỉ dựa vào status code.
5. Kiểm tra thư mục tạm do parser sử dụng và thư mục lưu của service; đây có thể là **hai nơi khác nhau**.
6. Thử file nhỏ, file vượt giới hạn, nhiều part và request bị ngắt giữa chừng; xác minh không để lại file lỗi và không trả thành công sai.

## 13. Nhiều file, form binding và functional endpoints

### 13.1. Nhiều file cùng tên

Client có thể gửi:

~~~bash
curl -i -F "files=@a.txt" -F "files=@b.txt" \
  http://localhost:8080/api/batch
~~~

Lệnh chỉ là **minh họa giao thức**, vì ứng dụng ví dụ mục 5 không định nghĩa `/api/batch`. Ở server, cần thiết kế handler có khả năng xử lý **nhiều part** tên `files`; `MultiValueMap<String, Part>` phù hợp khi cần giữ thông tin theo tên lặp. Khi lưu, chọn tuần tự `concatMap` nếu cần thứ tự và dễ kiểm soát dung lượng/đĩa, hoặc `flatMap` với **concurrency được giới hạn rõ** nếu muốn đồng thời.

Đừng sử dụng `parts.getFirst("files")` rồi tin rằng request chỉ có một file: client hoàn toàn có thể gửi thêm part cùng tên. Hãy quy định và thực thi số file tối đa cũng như cách trả lỗi khi vượt giới hạn.

### 13.2. Form binding

WebFlux hỗ trợ data binding command object chứa một `FilePart` và các form field nếu mô hình form phù hợp. Điều này thuận tiện khi form nhiều trường. Tuy nhiên, với API upload đơn giản, `@RequestPart` thể hiện rõ hợp đồng part name và kiểu dữ liệu, dễ kiểm thử qua `curl` hơn.

### 13.3. Functional routing

Không nhất thiết dùng annotated controller. Với `RouterFunction` và `HandlerFunction`, WebFlux có API trên `ServerRequest` để nhận:

~~~java
Mono<MultiValueMap<String, Part>> parts = request.multipartData();
~~~

Đây là **một biểu thức trong functional handler**, không phải chương trình Java độc lập. Khi cần streaming events, có thể dùng `request.bodyToFlux(PartEvent.class)`. Nguyên tắc validate, giới hạn byte, bảo mật filename, buffer release và không chặn event loop **không đổi**.

## 14. So sánh nhanh WebFlux và Spring MVC

| Khía cạnh | Spring WebFlux | Spring MVC / Servlet |
| --- | --- | --- |
| Class nhận file phổ biến | `org.springframework.http.codec.multipart.FilePart` | `org.springframework.web.multipart.MultipartFile` |
| Interface part | `org.springframework.http.codec.multipart.Part` | `jakarta.servlet.http.Part` nếu dùng Servlet API |
| Đọc content | `Flux<DataBuffer>` hoặc `FilePart.transferTo(Path)` | `InputStream`, `getBytes()`, `transferTo(...)` tùy API |
| Lưu file | Compose `Mono<Void>`, không `block()` trên event loop | Controller synchronous thường thực hiện I/O blocking |
| Đọc nhiều part | `Mono<MultiValueMap<String, Part>>` | Servlet multipart resolver / request parts |
| Streaming events | `Flux<PartEvent>` | Cơ chế Servlet streams/parts khác |
| Config Spring Boot | `spring.webflux.multipart.*` | `spring.servlet.multipart.*` |
| `@RequestParam` | Liên kết query parameters trong WebFlux | Có thể liên kết form/multipart theo cơ chế Servlet |

Cả hai stack có thể trả API upload tốt nếu được thiết kế, kiểm soát quota và lưu trữ đúng. **Reactive không tự làm file upload an toàn hoặc nhanh hơn**, nhưng API publisher cho phép ghép chuỗi xử lý, streaming và backpressure rõ ràng trong kiến trúc phù hợp.

## 15. Bài tập tự kiểm tra

**Câu 1.** Với part `name="avatar"; filename="pic.png"`, `Part.name()` và `FilePart.filename()` trả giá trị gì? Vì sao không thể dùng `filename()` làm path lưu tin cậy?

**Câu 2.** Trong WebFlux, vì sao dùng `@RequestParam("note") String note` để nhận text part có thể sai mục tiêu, còn `@RequestPart("note") FormFieldPart note` thể hiện ý định rõ hơn?

**Câu 3.** `file.transferTo(target)` trả kiểu gì? Nếu controller gọi `.subscribe()` rồi ngay lập tức trả 201, có rủi ro gì?

**Câu 4.** Bạn nhận 4 file cùng tên part `files`. Tại sao cấu trúc `MultiValueMap<String, Part>` phù hợp hơn `Map<String, Part>` khi duyệt toàn bộ request?

**Câu 5.** `spring.webflux.multipart.max-in-memory-size=256KB` có luôn đồng nghĩa “file lớn hơn 256KB bị từ chối” không? Vì sao?

**Câu 6.** Vì sao cần release `DataBuffer` khi tự thao tác trực tiếp với `Flux<PartEvent>`?

**Câu 7.** Khi nào nên cân nhắc `Flux<PartEvent>` thay cho `Mono<MultiValueMap<String, Part>>`?

**Câu 8.** Một endpoint WebFlux dùng `FilePart` nhưng cấu hình chỉ có `spring.servlet.multipart.max-file-size`. Cần kiểm tra lại điều gì?

**Đáp án định hướng:**

1. `avatar` và `pic.png`; tên do client khai báo có thể chứa path traversal/tên độc hại, cần sinh ID lưu trên server.
2. WebFlux phân biệt query param với multipart; `@RequestPart` chọn đúng body part theo `name`.
3. `Mono<Void>`; subscribe riêng làm công việc lưu tách khỏi response, có thể báo thành công trước khi ghi xong và bỏ sót lỗi.
4. Một tên part có thể xuất hiện nhiều lần; `MultiValueMap` giữ danh sách các part cùng tên.
5. Không. Với parser multipart thông thường, ngưỡng này liên quan memory/spool-to-disk cho file part, không phải lệnh cấm upload file lớn hơn ngưỡng.
6. Buffer có thể nằm trong pool với reference count; không release đúng gây memory leak, nhất là khi cancel/error.
7. Khi muốn xử lý từng part/event theo stream và tránh thu thập toàn bộ cấu trúc part trước, ví dụ tệp lớn/chuyển tiếp trực tiếp.
8. Xác nhận stack WebFlux thật sự đang chạy và sử dụng cấu hình `spring.webflux.multipart.*` cùng các giới hạn gateway.

## 16. Ghi nhớ

- `multipart/form-data` chứa nhiều part với header và body riêng; `boundary` do HTTP client thiết lập.
- `Part` là interface chung; `FilePart` dùng cho file, `FormFieldPart` dùng cho text; `PartEvent` dùng cho streaming event.
- `@RequestPart("file")` khớp **part name**, không khớp filename. `FilePart.filename()` không phải path lưu an toàn.
- `FilePart.transferTo(Path)` trả `Mono<Void>`: compose vào pipeline, trả status thành công **sau** khi ghi xong.
- `@RequestBody Mono<MultiValueMap<String, Part>>` phù hợp khi cần toàn bộ part map; `Flux<PartEvent>` hữu ích cho xử lý theo stream, nhưng tăng trách nhiệm quản lý buffer và giới hạn byte.
- Không dùng `MultipartFile`/`jakarta.servlet.http.Part` của MVC cho code mẫu WebFlux; không áp nhầm `spring.servlet.multipart.*`.
- Hãy kiểm soát authentication, quota, file content, content type, filename, path, timeout, temp storage, errors và cancellation.

## 17. Tài liệu tham khảo

- Spring Framework — WebFlux Multipart Content, `@RequestPart`, `PartEvent`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework — Reactive Core, Multipart Readers, buffer limits và streaming: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — Functional Endpoints, `ServerRequest.multipartData()`: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework — WebFlux `@RequestParam`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html
- Spring Boot 3.3 — Common Application Properties, `spring.webflux.multipart.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework — FilePart API, file name safety and transfer behavior: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/FilePart.html
