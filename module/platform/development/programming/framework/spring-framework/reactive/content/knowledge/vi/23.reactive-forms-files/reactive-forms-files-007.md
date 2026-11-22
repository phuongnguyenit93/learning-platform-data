# Giới hạn kích thước, số phần và tài nguyên tạm trong Spring WebFlux Multipart

## 1. Vì sao phải giới hạn multipart?

Một request multipart có thể chứa nhiều phần (part): trường văn bản, JSON metadata, ảnh, tài liệu hoặc nhiều file. Mỗi phần có header và body riêng. Nếu ứng dụng không đặt giới hạn, client có thể gửi file rất lớn làm đầy đĩa tạm, hàng nghìn part nhỏ làm tăng chi phí parse, trường văn bản lớn làm tăng heap, header part quá dài hoặc nhiều upload đồng thời khiến tài nguyên tăng theo concurrency.

Spring WebFlux có hai cách đọc chính. Reader thông thường tạo các đối tượng Part và có thể ghi file lớn ra thư mục tạm. Reader PartEvent phát dữ liệu tuần tự để ứng dụng xử lý từng chunk. Hai cách có giới hạn và vòng đời tài nguyên khác nhau.

Mục tiêu là kiểm soát đồng thời **bộ nhớ, dung lượng đĩa, số part, kích thước header, tổng request và số upload đồng thời**. Một giới hạn đơn lẻ không bảo vệ được toàn bộ hệ thống.

## 2. Multipart được đọc như thế nào?

Một request multipart có dạng khái quát:

~~~http
POST /uploads HTTP/1.1
Content-Type: multipart/form-data; boundary=----demo

------demo
Content-Disposition: form-data; name="description"

profile photo
------demo
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png

(binary file bytes)
------demo--
~~~

Mỗi ranh giới phân chia một part. Một part có header và nội dung; file part có thể chứa rất nhiều byte.

| Mô hình | API thường dùng | Cách xử lý |
| --- | --- | --- |
| Aggregate parts | @RequestPart, MultiValueMap<String, Part>, getMultipartData() | Parse các part rồi gom metadata/Part vào một map |
| Streaming parts | @RequestBody Flux<PartEvent> | Nhận event tuần tự, xử lý từng part và từng chunk |

### 2.1. Aggregate parts

MultipartHttpMessageReader ủy quyền việc parse cho DefaultPartHttpMessageReader, sau đó gom các Part vào MultiValueMap. File part lớn hơn ngưỡng bộ nhớ được lưu vào file tạm; các part nhỏ có thể nằm trong memory.

~~~java
@PostMapping(path = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<UploadResult> upload(
        @RequestPart("metadata") Mono<UploadMetadata> metadata,
        @RequestPart("file") FilePart file) {
    // Xử lý metadata và file.
}
~~~

Hoặc nhận tất cả part:

~~~java
@PostMapping(path = "/upload-all", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> uploadAll(
        @RequestBody Mono<MultiValueMap<String, Part>> parts) {
    // Duyệt các part theo tên.
    return Mono.empty();
}
~~~

ServerWebExchange cũng có getMultipartData(). Kết quả được cache để nhiều thành phần truy cập map đã parse. Sau khi multipart data đã được đọc, không thể quay lại đọc raw request body như thể body chưa bị tiêu thụ; hãy dùng nhất quán API multipart đã chọn.

### 2.2. Streaming với PartEvent

Nếu file lớn hoặc cần chuyển tiếp dữ liệu mà không gom toàn bộ multipart vào map, dùng Flux<PartEvent>. Form field thường tạo một FormPartEvent; file lớn có thể tạo nhiều FilePartEvent. Event cuối cùng của mỗi part có isLast() bằng true.

~~~java
@PostMapping(path = "/stream-upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> streamUpload(@RequestBody Flux<PartEvent> events) {
    return events
            .windowUntil(PartEvent::isLast)
            .concatMap(partEvents -> partEvents.switchOnFirst((signal, content) -> {
                if (!signal.hasValue()) {
                    return content.then();
                }

                PartEvent first = signal.get();

                if (first instanceof FormPartEvent form) {
                    validateField(form.name(), form.value());
                    return content.then();
                }

                if (first instanceof FilePartEvent file) {
                    String clientFilename = file.filename();
                    Flux<DataBuffer> chunks = content.map(PartEvent::content);
                    return storeChunks(chunks, clientFilename);
                }

                return Mono.error(new IllegalStateException("Unsupported part"));
            }))
            .then();
}
~~~

Đây là khung xử lý minh họa; validateField và storeChunks là logic của ứng dụng. Với từng part event, nội dung DataBuffer phải được consume, relay hoặc release hoàn toàn. Không bỏ qua chunk khi thoát sớm khỏi một nhánh xử lý.

Streaming giảm nhu cầu giữ toàn bộ file trong memory hoặc file tạm của multipart reader. Đổi lại, ứng dụng chịu trách nhiệm xử lý backpressure, ghi chunk, giới hạn tổng byte và cleanup khi lỗi hoặc cancel.

## 3. Các giới hạn trong Spring WebFlux

### 3.1. max-in-memory-size

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
~~~

Ý nghĩa phụ thuộc loại part trong DefaultPartHttpMessageReader:

- Với **non-file part** như trường văn bản hoặc JSON metadata, đây là giới hạn kích thước tối đa được giữ trong memory. Vượt ngưỡng thì part bị từ chối, thường phát DataBufferLimitException.
- Với **file part**, đây là ngưỡng trước khi nội dung được ghi ra file tạm. File lớn hơn ngưỡng không tự động bị từ chối chỉ vì vượt ngưỡng này.

Giá trị mặc định trong Spring Boot 3.5 là 256KB cho mỗi part. Đặt -1 sẽ giữ toàn bộ nội dung trong memory; cách này không phù hợp với upload file lớn hoặc tải đồng thời cao.

Đừng hiểu nhầm 256KB là giới hạn tổng của cả request. Một request có thể có nhiều part; memory sử dụng còn phụ thuộc số part và số request đồng thời.

### 3.2. max-disk-usage-per-part

~~~properties
spring.webflux.multipart.max-disk-usage-per-part=20MB
~~~

Giới hạn dung lượng đĩa được phép dùng cho **mỗi file part** khi reader ghi file ra thư mục tạm. Giá trị mặc định là -1, tức không giới hạn.

Đây không phải tổng dung lượng đĩa cho toàn bộ request. Ví dụ request có 4 file part và mỗi part được phép 20MB thì tổng dung lượng tạm có thể lên tới khoảng 80MB cho một request, chưa tính overhead. Với 50 request đồng thời, mức tối đa lý thuyết tăng theo số request.

Giới hạn này không có tác dụng khi max-in-memory-size được đặt -1 vì reader không chuyển file part sang đĩa. Với PartEvent streaming, ứng dụng xử lý trực tiếp event nên giới hạn disk usage per part và thư mục lưu file tạm không được dùng theo cùng cách.

### 3.3. max-parts

~~~properties
spring.webflux.multipart.max-parts=5
~~~

Giới hạn số lượng part trong một multipart request. Part bao gồm cả file và trường form/metadata; không chỉ đếm số file. Mặc định là -1, không giới hạn.

Một giới hạn nhỏ giúp tránh request có hàng nghìn trường nhỏ gây tốn CPU, object và bộ nhớ quản lý.

### 3.4. max-headers-size

~~~properties
spring.webflux.multipart.max-headers-size=10KB
~~~

Giới hạn lượng bộ nhớ dành cho phần header của **mỗi part**. Đây là header bên trong multipart, ví dụ Content-Disposition và Content-Type; nó không phải giới hạn header HTTP tổng của request.

Mặc định Spring Boot 3.5 là 10KB cho mỗi part. Không nên đặt -1 nếu client không thực sự cần header lớn.

### 3.5. file-storage-directory

~~~properties
spring.webflux.multipart.file-storage-directory=./var/tmp/demo-multipart-tmp
~~~

Chỉ định thư mục dùng để lưu file part lớn hơn max-in-memory-size. Nếu không cấu hình, Spring dùng một thư mục dưới system temporary directory.

Thư mục này cần đủ dung lượng và quota, có quyền truy cập tối thiểu, có monitoring dung lượng trống/inode/tốc độ ghi và có quy trình dọn file mồ côi sau sự cố. Đây là nơi lưu trung gian do multipart reader quản lý, khác với thư mục lưu file nghiệp vụ cuối cùng.

### 3.6. headers-charset

~~~properties
spring.webflux.multipart.headers-charset=UTF-8
~~~

Chọn charset dùng để giải mã header của các part. Mặc định là UTF-8. Hãy giữ mặc định trừ khi có client cũ cần charset cụ thể và đã được kiểm thử.

## 4. Cấu hình Spring Boot 3.5

Spring Boot cung cấp nhóm thuộc tính riêng cho WebFlux:

~~~yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 64KB
      max-disk-usage-per-part: 20MB
      max-parts: 5
      max-headers-size: 10KB
      headers-charset: UTF-8
      file-storage-directory: ./var/tmp/demo-multipart-tmp
~~~

Giải thích cấu hình mẫu:

- Non-file part lớn hơn 64KB bị từ chối.
- File part lớn hơn 64KB được ghi vào file tạm thay vì tiếp tục giữ toàn bộ trong memory.
- Mỗi file part dùng tối đa 20MB dung lượng tạm.
- Một request có tối đa 5 part, gồm cả metadata và file.
- Header của mỗi part có tối đa 10KB.
- File tạm nằm trong thư mục demo-multipart-tmp.

Giá trị trong ví dụ là điểm bắt đầu để minh họa, không phải giới hạn phù hợp cho mọi hệ thống. Hãy chọn theo loại file, số upload đồng thời, dung lượng volume và SLA.

### 4.1. Đừng nhầm cấu hình WebFlux với Spring MVC

| Spring MVC / Servlet | Spring WebFlux |
| --- | --- |
| spring.servlet.multipart.max-file-size | spring.webflux.multipart.max-disk-usage-per-part |
| spring.servlet.multipart.max-request-size | Không có thuộc tính WebFlux tương đương trong nhóm multipart Boot 3.5 |
| MultipartFile | FilePart |
| Servlet multipart temporary storage | DefaultPartHttpMessageReader và Part |

Không dùng spring.servlet.multipart.max-request-size để giới hạn upload của ứng dụng WebFlux. Đây là cấu hình của Servlet stack.

### 4.2. Không có một thuộc tính tổng request-size tương đương trong WebFlux multipart

Trong nhóm spring.webflux.multipart của Spring Boot 3.5 có giới hạn memory, disk per part, số part, header size và thư mục tạm. Không có spring.webflux.multipart.max-request-size tương đương spring.servlet.multipart.max-request-size.

Nếu cần giới hạn tổng byte của toàn bộ request, hãy thiết lập ở reverse proxy/API gateway và/hoặc bổ sung bộ đếm byte ở tầng ứng dụng. Không dựa vào Content-Length vì request có thể không gửi header này hoặc được truyền theo chunked transfer.

Cũng không được suy ra tổng dung lượng request chỉ từ max-disk-usage-per-part. Giới hạn per-part không phải quota tổng.

## 5. Mô hình tính tài nguyên

Giới hạn phải được xem cùng concurrency. Một phép ước lượng đơn giản:

~~~text
Memory tạm
≈ số request đồng thời
  × số non-file part có thể nằm trong memory
  × max-in-memory-size
  + header và overhead

Disk tạm
≈ số request đồng thời
  × số file part trong mỗi request
  × max-disk-usage-per-part
  + filesystem overhead
~~~

Ví dụ:

- 40 request upload đồng thời.
- Mỗi request có 3 non-file part có thể giữ trong memory.
- max-in-memory-size là 64KB.

Ước lượng thô cho phần dữ liệu non-file là 40 × 3 × 64KB = 7.5MB. Con số thực tế còn phụ thuộc thời điểm parse, buffer, object và overhead.

Nếu mỗi request có 2 file part, mỗi file tối đa 20MB, 40 request đồng thời có thể cần tới 40 × 2 × 20MB = 1.6GB dung lượng tạm trong trường hợp tất cả cùng đạt giới hạn. Vì vậy, đặt giới hạn cho mỗi part vẫn chưa đủ; cần quota volume và giới hạn concurrency.

Ngoài memory/disk, hãy xem xét số file descriptor, CPU parse multipart, băng thông, thời gian request giữ connection, số upload chờ antivirus/object storage và IOPS của volume.

## 6. Quản lý file tạm và vòng đời Part

Part biểu diễn một phần của multipart request. Các API hữu ích:

| API | Ý nghĩa |
| --- | --- |
| Part.content() | Flux<DataBuffer> chứa nội dung part |
| Part.headers() | Header của part |
| Part.name() | Tên trường multipart |
| Part.delete() | Mono<Void> xóa storage bên dưới khi đã dùng xong |
| FilePart.filename() | Tên file do client gửi |
| FilePart.transferTo(Path) | Copy nội dung file part tới đường dẫn đích |

Part.delete() trả về Publisher; phải subscribe vào Publisher đó bằng cách compose vào pipeline. Chỉ gọi part.delete() rồi bỏ qua Mono<Void> sẽ không thực hiện cleanup.

### 6.1. Dùng usingWhen để cleanup cả complete, error và cancel

~~~java
Mono<UploadReceipt> saveFile(FilePart file, Path destination) {
    String id = UUID.randomUUID().toString();
    String originalName = Objects.toString(file.filename(), "");

    return Mono.usingWhen(
            Mono.just(file),
            part -> part.transferTo(destination)
                    .thenReturn(new UploadReceipt(id, originalName)),
            part -> part.delete(),
            (part, error) -> part.delete(),
            part -> part.delete()
    );
}
~~~

Mono.usingWhen gắn cleanup bất đồng bộ với ba đường kết thúc: hoàn tất, lỗi và cancel. FilePart.transferTo là thao tác reactive; không gọi block() trong controller.

Đoạn code giả định file part đã được decode và ứng dụng sở hữu vòng đời Part trong phạm vi xử lý này. Nếu một component khác còn cần dùng Part, phải thiết kế quyền sở hữu và cleanup chung để không xóa storage quá sớm.

### 6.2. Đừng giữ Part hoặc FilePart trong field dùng chung

Part thuộc về một request. Không đưa FilePart, DataBuffer hoặc đường dẫn tạm của request vào singleton field hay cache toàn cục. Nhiều request đồng thời có thể dùng nhầm tài nguyên của nhau, giữ file lâu hơn cần thiết hoặc xóa file khi consumer khác còn đang đọc.

Nếu cần xử lý bất đồng bộ sau khi request kết thúc, hãy chuyển nội dung sang storage do ứng dụng quản lý, rồi truyền ID hoặc đường dẫn nội bộ an toàn cho tác vụ tiếp theo.

### 6.3. Không dùng filename của client làm đường dẫn

FilePart.filename() là dữ liệu do client cung cấp. Không nối trực tiếp giá trị này vào thư mục upload:

~~~java
// Không an toàn:
Path destination = uploadDir.resolve(file.filename());
~~~

Client có thể gửi tên chứa dấu phân cách thư mục, ký tự ".." hoặc chuỗi bất thường. Hãy tạo tên lưu trữ do server kiểm soát:

~~~java
String storageName = UUID.randomUUID() + ".upload";
Path destination = uploadDir.resolve(storageName).normalize();
~~~

Lưu tên gốc như metadata nếu nghiệp vụ cần, nhưng không dùng nó làm đường dẫn. Đồng thời kiểm tra content thực tế, MIME type, extension, quyền truy cập và chính sách lưu trữ.

## 7. Streaming với PartEvent và giới hạn từng part

PartEventHttpMessageReader hỗ trợ đọc multipart theo luồng. Trong Spring Framework 6.1 trở lên, reader có các giới hạn:

| API | Ý nghĩa | Mặc định |
| --- | --- | --- |
| setMaxInMemorySize(int) | Giới hạn bộ nhớ cho form field | 256KB |
| setMaxHeadersSize(int) | Giới hạn header mỗi part | 10KB |
| setMaxParts(int) | Giới hạn số part trong request | -1, không giới hạn |
| setMaxPartSize(long) | Giới hạn kích thước của mỗi part | -1, không giới hạn |

Với PartEvent streaming:

- File content được phát theo event/chunk để ứng dụng xử lý.
- max-in-memory-size áp dụng cho form field.
- max-part-size giới hạn kích thước mỗi part, bao gồm file part.
- File-storage-directory và max-disk-usage-per-part không được dùng theo cơ chế spool của DefaultPartHttpMessageReader.

Spring Boot 3.5 có các thuộc tính chung cho multipart reader nhưng ReactiveMultipartProperties không có thuộc tính max-part-size. Nếu dùng PartEvent và cần giới hạn riêng từng file part, cấu hình PartEventHttpMessageReader rõ ràng.

Ví dụ đăng ký reader tùy chỉnh:

~~~java
@Configuration
class StreamingMultipartLimits implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        PartEventHttpMessageReader reader = new PartEventHttpMessageReader();
        reader.setMaxInMemorySize(64 * 1024);
        reader.setMaxHeadersSize(10 * 1024);
        reader.setMaxParts(5);
        reader.setMaxPartSize(20L * 1024 * 1024);

        configurer.customCodecs().register(reader);
    }
}
~~~

Đây là cấu hình dành cho endpoint sử dụng Flux<PartEvent>. Khi tự đăng ký reader, hãy kiểm tra thứ tự ưu tiên codec và test endpoint thực tế để bảo đảm reader có giới hạn đang được dùng. Các giá trị ở đây phải đồng bộ với giới hạn tại gateway và chính sách upload của ứng dụng.

### 7.1. Vì sao PartEvent cần backpressure?

Một file lớn có thể được chia thành nhiều event. Nếu ứng dụng gom tất cả event vào List hoặc byte[] trước khi xử lý, lợi ích streaming biến mất và heap có thể tăng theo kích thước file.

Dùng các operator tuần tự như concatMap khi ghi từng part hoặc từng chunk. Không gọi subscribe() lồng nhau; hãy trả về Publisher để backpressure, error và cancellation đi xuyên suốt pipeline.

Nếu ứng dụng từ chối một part giữa chừng, cần tiêu thụ, relay hoặc release phần content còn lại theo contract. Không bỏ phần DataBuffer còn trong event window.

## 8. Ví dụ Java 17+ chạy được: upload file với giới hạn WebFlux

Ví dụ dùng Spring Boot 3.5.16, Java 17+ và WebFlux. Reader dùng cấu hình multipart trong application.yml; controller nhận FilePart, lưu file bằng tên do server tạo và cleanup Part sau khi transfer.

### 8.1. Cấu trúc dự án

~~~text
webflux-upload-limits/
├── pom.xml
└── src/
    ├── main/java/example/upload/
    │   ├── DemoApplication.java
    │   └── UploadController.java
    ├── main/resources/
    │   └── application.yml
    └── test/java/example/upload/
        └── UploadControllerTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-upload-limits</artifactId>
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
~~~

### 8.3. application.yml

~~~yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 64KB
      max-disk-usage-per-part: 20MB
      max-parts: 5
      max-headers-size: 10KB
      headers-charset: UTF-8
      file-storage-directory: ./var/tmp/demo-multipart-tmp
~~~

### 8.4. DemoApplication.java

~~~java
package example.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.5. UploadController.java

~~~java
package example.upload;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.Part;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class UploadController {

    private final Path uploadDir;

    public UploadController() {
        this.uploadDir = Path.of("./var/tmp/demo-uploads")
                .toAbsolutePath()
                .normalize();

        try {
            Files.createDirectories(this.uploadDir);
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    @PostMapping(
            path = "/uploads",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<UploadReceipt> upload(@RequestPart("file") FilePart file) {
        String id = UUID.randomUUID().toString();
        String originalFilename = Objects.toString(file.filename(), "");
        Path destination = uploadDir.resolve(id + ".upload").normalize();

        return Mono.usingWhen(
                Mono.just(file),
                part -> part.transferTo(destination)
                        .thenReturn(new UploadReceipt(id, originalFilename)),
                Part::delete,
                (part, error) -> part.delete(),
                Part::delete
        );
    }

    public record UploadReceipt(String id, String originalFilename) {
    }
}
~~~

Điểm quan trọng:

- Controller nhận FilePart thay vì MultipartFile.
- FilePart.transferTo trả Mono<Void>; không block thread xử lý request.
- Tên file lưu trữ là UUID do server tạo; tên do client gửi chỉ được giữ như metadata.
- Mono.usingWhen gọi Part.delete khi hoàn tất, lỗi hoặc cancel.
- Thư mục upload cuối cùng được tách khỏi thư mục multipart tạm của reader.

### 8.6. UploadControllerTest.java

~~~java
package example.upload;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class UploadControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void acceptsSmallFileAndReturnsServerGeneratedId() {
        MultipartBodyBuilder multipart = new MultipartBodyBuilder();

        multipart.part(
                "file",
                new ByteArrayResource("hello".getBytes(StandardCharsets.UTF_8)) {
                    @Override
                    public String getFilename() {
                        return "hello.txt";
                    }
                }
        );

        webTestClient.post()
                .uri("/uploads")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(multipart.build()))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isNotEmpty()
                .jsonPath("$.originalFilename").isEqualTo("hello.txt");
    }
}
~~~

Test tạo multipart request có file nhỏ, xác nhận endpoint nhận file và trả ID do server tạo. Các giới hạn 64KB, 20MB, 5 parts và 10KB header được cấu hình tại reader; hãy bổ sung test biên tương ứng với chính sách của ứng dụng.

### 8.7. Chạy và gửi request

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Tạo file hello.txt có nội dung hello, sau đó gửi:

~~~bash
curl -i -F "file=@hello.txt" http://localhost:8080/uploads
~~~

Response minh họa:

~~~json
{
  "id": "e2c7c6e0-8e39-4c8d-8d3d-5a2d5b5f4d13",
  "originalFilename": "hello.txt"
}
~~~

ID trong output là giá trị sinh ngẫu nhiên ở mỗi request; không cố định giữa các lần chạy.

Chạy integration test:

~~~bash
mvn test
~~~

## 9. Xử lý lỗi giới hạn và status HTTP

Khi vượt một giới hạn, reader có thể phát lỗi parse/codec như DataBufferLimitException hoặc lỗi multipart tương ứng. Không nên giả định mọi loại lỗi đều tự động được ánh xạ thành cùng một HTTP status trong mọi phiên bản và cấu hình.

Một API upload thường nên có error contract rõ ràng:

| Trường hợp | Status thường phù hợp |
| --- | --- |
| Request hoặc multipart không hợp lệ | 400 Bad Request |
| File/part vượt giới hạn | 413 Payload Too Large |
| Media type không được hỗ trợ | 415 Unsupported Media Type |
| Part bắt buộc bị thiếu | 400 Bad Request |
| Lỗi lưu trữ tạm hoặc volume hết dung lượng | 5xx tùy nguyên nhân |

Trong production, map các exception giới hạn đã xác định sang 413 tại exception handling layer của ứng dụng. Không chuyển mọi IOException hoặc mọi lỗi parser thành 413; lỗi disk full, permission denied và lỗi hệ thống cần được quan sát và xử lý riêng.

Không trả stack trace, đường dẫn file tạm hoặc thông tin filesystem nội bộ cho client.

## 10. Giới hạn tổng request và concurrency

Giới hạn per-part không giới hạn tổng request. Ví dụ một request có 5 file part, mỗi file 20MB, vẫn có thể sử dụng tới 100MB dung lượng tạm nếu các part đều đạt ngưỡng.

Một hệ thống upload nên có các lớp giới hạn:

1. **Edge proxy/API gateway:** giới hạn tổng byte request, thời gian upload, tốc độ và số connection.
2. **Multipart reader:** giới hạn bộ nhớ, đĩa per part, số part và header size.
3. **Application:** giới hạn tổng byte nghiệp vụ, loại file, số file theo user/tenant và quota lưu trữ.
4. **Storage:** quota volume, dung lượng trống, chính sách retention và cleanup.
5. **Concurrency:** giới hạn số upload đang xử lý, đặc biệt khi cần antivirus hoặc xử lý ảnh.

Content-Length chỉ có thể dùng để từ chối sớm. Vẫn phải có giới hạn thực tế ở proxy hoặc stream counter vì request có thể không khai báo độ dài hoặc dùng chunked transfer.

Nếu ứng dụng tự đếm byte của PartEvent, hãy đếm tổng byte qua toàn bộ event và dừng luồng khi vượt giới hạn. Khi dừng, phải tiêu thụ hoặc release phần buffer còn lại theo contract để không gây memory leak.

## 11. Bảo vệ tài nguyên tạm

### 11.1. Chọn thư mục tạm riêng

Không dùng thư mục public/static để lưu part tạm. Thư mục tạm nên có quyền truy cập tối thiểu, quota, monitoring và chính sách dọn file mồ côi sau crash. Nếu upload lớn có thể ảnh hưởng log hoặc database, cân nhắc volume tách biệt.

### 11.2. Cleanup đúng vòng đời

- Với Part/FilePart đã parse, gọi Part.delete khi ứng dụng không còn cần storage của part.
- Với PartEvent streaming, ứng dụng quản lý chunk và file đích; đóng tài nguyên lưu trữ khi complete/error/cancel.
- Không giữ FilePart trong singleton hoặc cache dài hạn.
- Không tạo file đích trước khi xác thực request nếu có thể tránh.
- Nếu ghi file đích thất bại giữa chừng, xóa file dở dang theo chính sách của ứng dụng.

### 11.3. Giới hạn đồng thời và theo dõi

Ngay cả khi mỗi upload bị giới hạn 20MB, hàng trăm upload đồng thời vẫn có thể tiêu thụ nhiều GB. Hãy áp dụng concurrency limit theo user/tenant, endpoint hoặc worker pool.

Nên theo dõi số request multipart đang xử lý, kích thước part, số request bị từ chối, dung lượng và inode thư mục tạm, thời gian parse/transfer/scan, số file tạm còn lại, lỗi permission/disk full và cancellation.

Không dùng filename, user-provided path hoặc raw form value làm metric label vì dữ liệu có thể nhạy cảm và cardinality rất cao.

## 12. Kiểm tra nội dung file và an toàn đường dẫn

Các giới hạn kích thước không chứng minh file an toàn. Sau khi nhận file:

- Không tin extension hoặc Content-Type do client gửi.
- Kiểm tra signature/magic bytes và định dạng thực tế.
- Áp dụng allowlist định dạng theo nghiệp vụ.
- Quét malware nếu hệ thống có yêu cầu.
- Giới hạn giải nén archive và kiểm tra zip bomb.
- Không dùng tên file client làm path.
- Không cho file upload ghi đè file hệ thống hoặc file của user khác.
- Chỉ công bố file sau khi xác thực và scan hoàn tất.
- Nếu file được truy cập lại, dùng ID ngẫu nhiên và authorization check.

Nếu lưu tên gốc, chuẩn hóa và giới hạn độ dài; tránh ghi tên đó vào log nếu không cần thiết.

## 13. Các lỗi cấu hình phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ đặt max-in-memory-size | File lớn vẫn có thể ghi nhiều dữ liệu ra disk | Đặt max-disk-usage-per-part |
| Đặt max-disk-usage-per-part nhưng bỏ max-parts | Một request có thể gửi nhiều file | Đặt max-parts |
| Nghĩ max-disk-usage-per-part là tổng request | Tổng dung lượng nhiều file vượt dự kiến | Thêm tổng request cap và storage quota |
| Đặt max-in-memory-size=-1 | File lớn được giữ trong memory | Dùng threshold hữu hạn và disk cap |
| Để max-parts=-1 | Không giới hạn số trường/file | Chọn số part tối đa theo API |
| Để max-disk-usage-per-part=-1 | File part không có giới hạn disk từ reader | Đặt ngưỡng phù hợp |
| Đặt max-headers-size=-1 | Header part không bị giới hạn bởi reader | Đặt giới hạn hữu hạn |
| Dùng spring.servlet.multipart trong WebFlux | Cấu hình không áp dụng cho reactive reader | Dùng spring.webflux.multipart |
| Tin Content-Length | Có thể bỏ sót request chunked hoặc thiếu header | Giới hạn ở proxy và đếm byte thực tế |
| Dùng file.filename() làm path | Có nguy cơ path traversal và ghi đè | Tạo tên file do server kiểm soát |
| Không gọi Part.delete() | File tạm có thể tồn tại lâu hơn cần thiết | Cleanup bằng usingWhen hoặc lifecycle tương đương |
| Chuyển sang PartEvent nhưng không xử lý chunk | Có thể rò buffer hoặc giữ tài nguyên | Consume, relay hoặc release toàn bộ content |
| Gọi block() trong controller upload | Chặn event loop và giảm throughput | Dùng FilePart.transferTo và reactive storage API |
| Không giới hạn upload đồng thời | Nhiều request nhỏ cũng có thể làm đầy disk | Thêm concurrency limit và quota |

## 14. Checklist trước khi đưa upload lên production

- [ ] Có giới hạn memory cho non-file part.
- [ ] File part có ngưỡng spill-to-disk và disk cap hữu hạn.
- [ ] Có giới hạn số part và kích thước header từng part.
- [ ] Có giới hạn tổng request ở proxy/gateway hoặc tầng đếm byte.
- [ ] Có giới hạn upload đồng thời theo tải và quota.
- [ ] Thư mục tạm nằm ngoài static/public path và có quota.
- [ ] Part/FilePart được cleanup khi complete, error và cancel.
- [ ] File lưu cuối dùng tên do server tạo.
- [ ] Có validation định dạng thực tế và scan theo chính sách.
- [ ] Có test cho file sát ngưỡng, vượt ngưỡng, nhiều part, header lớn và chunked request.
- [ ] Có monitoring dung lượng đĩa, inode, upload duration và lỗi cleanup.
- [ ] Có chính sách xóa file dở dang và file tạm mồ côi.

## 15. Ghi nhớ

- DefaultPartHttpMessageReader giữ part nhỏ trong memory và ghi file part lớn ra thư mục tạm.
- max-in-memory-size là giới hạn của non-file part và là ngưỡng spill-to-disk của file part.
- max-disk-usage-per-part giới hạn từng file part, không giới hạn tổng request.
- max-parts đếm tất cả part, gồm field và file; max-headers-size giới hạn header của từng part.
- Spring Boot 3.5 mặc định 256KB memory, 10KB header, -1 không giới hạn disk per part và -1 không giới hạn số part.
- file-storage-directory là vùng tạm; thư mục upload nghiệp vụ cuối cùng cần được quản lý riêng.
- Part.delete là reactive cleanup; compose nó vào pipeline để xử lý complete/error/cancel.
- FilePart.transferTo là cách chuyển file reactive; tên file client gửi không được dùng làm path.
- PartEvent phù hợp với streaming; setMaxPartSize giới hạn mỗi part, còn ứng dụng phải xử lý chunk và backpressure.
- Không có spring.webflux.multipart.max-request-size tương đương thuộc tính Servlet; cần giới hạn tổng request ở gateway hoặc tầng ứng dụng.
- Chọn giới hạn theo concurrency, memory, disk, IOPS và quota, không chỉ theo kích thước một file.

**Tài liệu chính thức:**
- [Spring Boot 3.5 — Common Application Properties: spring.webflux.multipart](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 3.5 — ReactiveMultipartProperties](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/ReactiveMultipartProperties.html)
- [Spring Framework 6.2 — Reactive Core: Multipart parsing and limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework — Multipart Content and PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 Javadoc — DefaultPartHttpMessageReader](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html)
- [Spring Framework 6.2 Javadoc — PartEventHttpMessageReader](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/multipart/PartEventHttpMessageReader.html)
- [Spring Framework 6.2 Javadoc — Part and FilePart](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/multipart/Part.html)
- [Spring Framework 6.2 Javadoc — FilePart](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/multipart/FilePart.html)
