# Truyền multipart theo Flux<PartEvent> trong Spring WebFlux

## 1. Vì sao cần truyền multipart theo luồng?

Một HTTP request dạng multipart chứa nhiều **part** trong cùng một body. Một part có thể là trường văn bản, metadata JSON hoặc file. Trình duyệt thường gửi form upload với \`Content-Type: multipart/form-data\`; mỗi part có header riêng như \`Content-Disposition\`, \`Content-Type\` và phần nội dung tương ứng.

Với file nhỏ, cách bind multipart thành object hoặc map các part thường thuận tiện. Nhưng nếu request chứa file lớn hoặc nhiều file, việc parse toàn bộ multipart thành cấu trúc tập hợp trước khi xử lý có thể làm tăng bộ nhớ và trì hoãn thời điểm ứng dụng bắt đầu tiêu thụ nội dung.

Spring WebFlux cung cấp **\`Flux<PartEvent>\`** để đọc multipart tuần tự, theo luồng. Mỗi part được biểu diễn bằng một hoặc nhiều event. Ứng dụng có thể nhận một phần dữ liệu, xử lý hoặc chuyển tiếp phần đó rồi mới tiếp tục nhận phần tiếp theo, thay vì phải gom toàn bộ file vào một object trong RAM.

Các lợi ích chính:

- Xử lý file lớn theo từng buffer.
- Xử lý các part theo thứ tự xuất hiện trong request.
- Có thể ghi dữ liệu xuống storage hoặc relay sang service khác khi dữ liệu đến.
- Dùng Reactive Streams để phối hợp demand và cancellation.
- Không cần tạo một \`MultiValueMap<String, Part>\` chứa toàn bộ multipart trước khi xử lý.

**Điểm quan trọng:** \`Flux<PartEvent>\` biểu diễn stream các sự kiện của multipart body. Nó không tự động lưu file, không tự kiểm tra quyền, không giới hạn dung lượng nghiệp vụ và không tự giải phóng mọi buffer do ứng dụng giữ lại. Handler phải tiêu thụ, chuyển tiếp hoặc release nội dung từng part đúng cách.

## 2. PartEvent, FormPartEvent và FilePartEvent

Spring Framework 6 giới thiệu \`PartEvent\` trong package:

~~~java
org.springframework.http.codec.multipart
~~~

Các kiểu chính:

| Kiểu | Ý nghĩa | Dữ liệu đặc trưng |
| --- | --- | --- |
| \`PartEvent\` | Event cơ sở đại diện một phần của multipart request | Headers, DataBuffer content, tên part và cờ cuối part |
| \`FormPartEvent\` | Một trường form thông thường | Giá trị dạng String qua \`value()\` |
| \`FilePartEvent\` | Một phần dữ liệu file upload | Tên file gốc qua \`filename()\`, headers và content buffer |

Các method quan trọng của \`PartEvent\`:

- \`name()\`: tên trường multipart theo tham số \`name\` của Content-Disposition.
- \`headers()\`: headers của part.
- \`content()\`: \`DataBuffer\` chứa nội dung của event hiện tại.
- \`isLast()\`: cho biết event này có phải event cuối cùng của part hay không.

\`FormPartEvent\` có thêm \`value()\` để lấy giá trị văn bản của form field. \`FilePartEvent\` có thêm \`filename()\` để lấy tên file gốc do client gửi lên.

Một trường form thông thường tạo ra một \`FormPartEvent\`. Một file upload có thể tạo ra **một hoặc nhiều \`FilePartEvent\`**. Nếu file lớn được chia thành nhiều buffer, event đầu tiên có thể chỉ chứa một phần file; các event tiếp theo mang các phần còn lại.

Không được giả định một \`FilePartEvent\` tương đương toàn bộ file.

## 3. isLast() và cách chia event theo từng part

Đây là quy tắc quan trọng để xử lý multipart đúng ranh giới:

**Event cuối cùng của mỗi part có \`isLast() == true\`.** Sau event đó, stream có thể tiếp tục bằng event thuộc part kế tiếp.

Vì vậy, Reactor có thể dùng:

~~~java
allPartEvents.windowUntil(PartEvent::isLast)
~~~

\`windowUntil\` tạo một window cho từng part. Mỗi window chứa toàn bộ event thuộc part đó, bao gồm event cuối có \`isLast() == true\`.

Ví dụ một request gồm trường mô tả và file lớn:

~~~text
Multipart request
    |
    +-- FormPartEvent(description, isLast=true)
    |
    +-- FilePartEvent(file, buffer 1, isLast=false)
    +-- FilePartEvent(file, buffer 2, isLast=false)
    +-- FilePartEvent(file, buffer 3, isLast=true)
    |
    +-- FormPartEvent(category, isLast=true)
~~~

Sau \`windowUntil(PartEvent::isLast)\`:

~~~text
Window 1: [FormPartEvent(description)]
Window 2: [FilePartEvent(buffer 1), FilePartEvent(buffer 2),
           FilePartEvent(buffer 3)]
Window 3: [FormPartEvent(category)]
~~~

Nhờ vậy, ứng dụng có thể xử lý một part hoàn chỉnh trước khi chuyển sang part tiếp theo. Với file nhiều buffer, tất cả buffer của file vẫn thuộc cùng một window.

Không dùng \`windowUntil\` với điều kiện tùy ý như kiểm tra loại event hoặc tên file. Điều kiện \`isLast()\` phản ánh đúng ranh giới part theo hợp đồng của Spring.

## 4. switchOnFirst() để nhận diện loại part

Sau khi có một window, cần biết part đó là trường văn bản hay file. Reactor cung cấp \`switchOnFirst()\`:

~~~java
partEvents.switchOnFirst((signal, events) -> {
    if (signal.hasValue()) {
        PartEvent first = signal.get();

        if (first instanceof FormPartEvent formEvent) {
            String value = formEvent.value();
            // Xử lý trường văn bản
        }
        else if (first instanceof FilePartEvent fileEvent) {
            String filename = fileEvent.filename();
            Flux<DataBuffer> contents =
                events.map(PartEvent::content);
            // Xử lý nội dung file
        }
    }

    return Mono.empty();
});
~~~

\`switchOnFirst\` cho phép xem event đầu tiên của window trước khi quyết định cách tiêu thụ phần còn lại. Tham số \`events\` là publisher của các event thuộc window đó, bao gồm event đầu tiên.

Cách xử lý thường dùng:

1. Lấy event đầu tiên từ \`signal\`.
2. Kiểm tra \`instanceof FormPartEvent\` hoặc \`instanceof FilePartEvent\`.
3. Nếu là form field, đọc \`value()\` và hoàn tất việc tiêu thụ part.
4. Nếu là file, lấy \`Flux<DataBuffer>\` từ \`events.map(PartEvent::content)\`.
5. Ghi, relay hoặc release toàn bộ buffer.
6. Chỉ chuyển sang part kế tiếp sau khi publisher xử lý part hiện tại hoàn tất.

Nếu event đầu tiên không có giá trị vì window đã complete hoặc error, hãy chuyển tiếp terminal signal từ \`events\`, không tự tạo dữ liệu giả.

## 5. concatMap giữ thứ tự và phối hợp backpressure

Kết hợp hai operator:

~~~java
allPartEvents
    .windowUntil(PartEvent::isLast)
    .concatMap(part -> part.switchOnFirst((signal, events) -> {
        // Xử lý một part
        return Mono.empty();
    }));
~~~

\`concatMap\` xử lý từng window theo thứ tự và chờ publisher xử lý part hiện tại hoàn tất trước khi xử lý part tiếp theo.

Điều này hữu ích khi:

- File cần được ghi hoàn chỉnh trước khi xử lý metadata part tiếp theo.
- Các part phụ thuộc thứ tự.
- Muốn giữ pipeline đơn giản và hạn chế số file đang mở đồng thời.
- Muốn tránh nhiều thao tác ghi storage chạy song song ngoài ý muốn.

Có thể dùng \`flatMap\` nếu các part độc lập và nghiệp vụ cho phép xử lý đồng thời. Tuy nhiên, cần giới hạn concurrency, quản lý nhiều file/handle cùng lúc và xử lý thứ tự kết quả. Với upload thông thường, \`concatMap\` là lựa chọn dễ kiểm soát hơn.

Backpressure cho phép downstream điều tiết tốc độ tiêu thụ event. Tuy nhiên, nó không thay thế giới hạn dung lượng file, số part, thời gian upload hoặc quota người dùng.

## 6. Đọc multipart streaming bằng @RequestBody Flux<PartEvent>

Trong annotated controller, khai báo:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<UploadResult> upload(
        @RequestBody Flux<PartEvent> allPartEvents) {
    // Xử lý theo luồng
}
~~~

Spring chọn \`PartEventHttpMessageReader\` để giải mã multipart body thành stream \`PartEvent\`.

Điểm đáng chú ý:

- \`@RequestBody Flux<PartEvent>\` cho phép đọc các part tuần tự.
- Không cần gom toàn bộ request vào \`MultiValueMap\`.
- File lớn có thể được biểu diễn bằng nhiều event và buffer.
- Content-Type của request phải là \`multipart/form-data\` với boundary hợp lệ.
- Body chỉ nên được tiêu thụ một lần; không đọc cùng request body ở nhiều nơi độc lập.

Ví dụ request HTTP:

~~~http
POST /api/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----demo-boundary

------demo-boundary
Content-Disposition: form-data; name="description"

Quarterly report
------demo-boundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

...file bytes...
------demo-boundary--
~~~

Boundary được client tạo để phân tách các part. Khi dùng cURL hoặc WebClient, hãy để công cụ multipart tự tạo boundary và header tương ứng. Không tự đặt một boundary tùy ý rồi gửi body không khớp.

## 7. Khi nào dùng PartEvent thay vì @RequestPart hoặc MultiValueMap?

Spring có nhiều cách đọc multipart. Chọn theo cách ứng dụng cần tiêu thụ dữ liệu:

| Cách đọc | Đặc điểm | Phù hợp |
| --- | --- | --- |
| \`@RequestPart\` | Bind một part theo tên vào tham số như DTO hoặc \`FilePart\` | Form upload đơn giản, file vừa/nhỏ, code dễ đọc |
| \`Mono<MultiValueMap<String, Part>>\` | Parse multipart thành map các part | Cần truy cập nhiều part theo tên hoặc cần cấu trúc map |
| \`ServerWebExchange.getMultipartData()\` | Lấy multipart data đã parse và cache trong exchange | Nhiều thành phần cần truy cập map-like multipart data |
| \`@RequestBody Flux<PartEvent>\` | Đọc từng event theo thứ tự, không gom toàn bộ multipart thành map | File lớn, xử lý tuần tự, relay hoặc streaming upload |

Ví dụ \`@RequestPart\`:

~~~java
@PostMapping("/simple-upload")
public Mono<String> upload(
        @RequestPart("description") String description,
        @RequestPart("file") FilePart file) {
    return file.transferTo(Path.of("uploads", "fixed-name"))
        .thenReturn("Uploaded: " + description);
}
~~~

Đây là ví dụ minh họa; tên file lưu cần được sinh an toàn trong ứng dụng thật. Cách này dễ dùng, nhưng không phải ví dụ xử lý event tuần tự bằng \`PartEvent\`.

Khi dùng \`MultipartHttpMessageReader\`, framework parse các part rồi thu thập chúng thành \`MultiValueMap\`. Với upload rất lớn, nếu muốn xử lý nội dung ngay khi nhận, \`Flux<PartEvent>\` phù hợp hơn.

Một khi đã gọi \`ServerWebExchange.getMultipartData()\` để parse và cache map-like multipart data, không thể tiếp tục đọc raw request body như một stream mới độc lập. Chọn một cách tiêu thụ body ngay từ đầu.

## 8. Quản lý DataBuffer: không để rò rỉ bộ nhớ

\`PartEvent.content()\` trả về \`DataBuffer\`. Trên một số server như Reactor Netty, buffer có thể được pool và reference-counted. Khi buffer đã được tiêu thụ, cần release đúng lifecycle.

Quy tắc của Spring:

**Nội dung buffer của mỗi PartEvent phải được tiêu thụ hoàn toàn, relay sang nơi khác hoặc release.**

Nếu bỏ qua content hoặc dừng xử lý một part giữa chừng mà không dọn buffer, ứng dụng có thể bị memory leak hoặc giữ tài nguyên pooled buffer quá lâu.

### Khi ghi file bằng DataBufferUtils.write

Có thể chuyển stream buffer trực tiếp xuống file bằng overload nhận \`Path\`:

~~~java
Flux<DataBuffer> contents =
    partEvents.map(PartEvent::content);

Mono<Void> write =
    DataBufferUtils.write(
        contents,
        destination,
        StandardOpenOption.CREATE_NEW
    );
~~~

Publisher hoàn tất khi ghi xong hoặc phát lỗi khi thao tác ghi thất bại. Overload nhận \`Path\` quản lý việc ghi file qua channel nội bộ; hãy compose publisher này vào pipeline, không tự subscribe.

### Khi tự ghi qua channel hoặc OutputStream

Các overload \`DataBufferUtils.write(..., channel)\` và \`write(..., OutputStream)\` trả về stream buffer và không tự release các buffer nguồn. Nếu tự dùng những overload này, cần tiêu thụ publisher trả về với release consumer, đồng thời quản lý đóng channel/stream:

~~~java
DataBufferUtils.write(contents, outputStream)
    .doOnNext(DataBufferUtils.releaseConsumer())
    .then();
~~~

Đây chỉ là đoạn minh họa. \`OutputStream\` là API blocking; không thực hiện ghi đồng bộ trực tiếp trên event-loop. Với file path, ưu tiên overload phù hợp của \`DataBufferUtils\` hoặc một storage client reactive.

### Khi bỏ qua hoặc discard buffer

Nếu pipeline dùng operator có thể loại bỏ buffer, cần cấu hình cleanup discard phù hợp:

~~~java
.doOnDiscard(DataBuffer.class, DataBufferUtils::release)
~~~

Chỉ thêm discard hook khi pipeline có khả năng discard buffer chưa được tiêu thụ; tránh release hai lần đối với buffer mà writer hoặc consumer đã sở hữu và giải phóng.

## 9. Ghi file theo luồng và bảo vệ tên file

Không sử dụng trực tiếp tên file client gửi lên để tạo đường dẫn:

~~~java
Path destination = uploadDirectory.resolve(fileEvent.filename());
~~~

Đây là cách nguy hiểm. Tên file có thể chứa đường dẫn, \`..\`, ký tự đặc biệt hoặc tên nhằm ghi đè file khác. Tên file từ client chỉ nên được coi là metadata không đáng tin cậy.

Một chiến lược an toàn hơn:

1. Sinh storage key từ UUID hoặc ID do server quản lý.
2. Lưu file trong một thư mục cố định do server cấu hình.
3. Không cho client quyết định thư mục đích.
4. Chỉ lưu tên file gốc như metadata nếu nghiệp vụ cần hiển thị.
5. Kiểm tra quyền upload và quyền truy cập file.
6. Giới hạn dung lượng, số file, số part và quota.
7. Xác minh loại nội dung bằng kiểm tra thực tế, không chỉ dựa vào Content-Type client gửi.
8. Quét malware hoặc xử lý nội dung không tin cậy theo chính sách hệ thống.

Ví dụ sinh tên file:

~~~java
String storageKey = UUID.randomUUID().toString();
Path destination = uploadDirectory.resolve(storageKey);
~~~

Tên gốc \`report.pdf\` có thể được lưu trong database cùng storage key. File vật lý được lưu dưới tên do server tạo.

## 10. Xử lý giới hạn multipart

Streaming giúp tránh gom toàn bộ file vào heap, nhưng không có nghĩa request được phép có dung lượng vô hạn. Cần giới hạn nhiều lớp:

- Kích thước tối đa của từng file.
- Kích thước tối đa của mỗi form field.
- Kích thước phần headers của mỗi part.
- Tổng số part trong request.
- Tổng dung lượng upload theo user/tenant.
- Thời gian tối đa để gửi request.
- Số request upload đồng thời.
- Dung lượng lưu trữ và chính sách dọn file tạm.

\`PartEventHttpMessageReader\` cung cấp các cấu hình như:

| Cấu hình | Ý nghĩa |
| --- | --- |
| \`setMaxInMemorySize(...)\` | Giới hạn bộ nhớ cho form field |
| \`setMaxHeadersSize(...)\` | Giới hạn kích thước headers của mỗi part |
| \`setMaxParts(...)\` | Giới hạn số part trong một request |
| \`setMaxPartSize(...)\` | Giới hạn kích thước tối đa mỗi part |

Theo Javadoc Spring Framework 6.2, giới hạn bộ nhớ mặc định cho form fields là 256 KiB, giới hạn headers mặc định là 10 KiB. \`maxParts\` và \`maxPartSize\` mặc định không giới hạn trong các phiên bản có các cấu hình đó. Hãy đặt giới hạn phù hợp với workload thay vì dựa vào mặc định.

Ví dụ cấu hình reader:

~~~java
PartEventHttpMessageReader reader =
    new PartEventHttpMessageReader();

reader.setMaxInMemorySize(256 * 1024);
reader.setMaxHeadersSize(10 * 1024);
reader.setMaxParts(10);
reader.setMaxPartSize(50L * 1024 * 1024);
~~~

Đây là đoạn cấu hình reader; cần đưa đúng instance vào codec registry của server theo cấu hình Spring Framework/Boot đang dùng. Tránh đăng ký một reader trùng lặp mà không kiểm tra thứ tự reader hiện có.

Ngoài giới hạn của reader, hãy đặt request size limit ở reverse proxy/API gateway và quota nghiệp vụ ở service. Một giới hạn tại một tầng không thay thế các giới hạn còn lại.

## 11. Xử lý form field và file theo từng window

Một controller có thể dùng \`windowUntil\` và \`switchOnFirst\` như sau:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<UploadSummary> upload(
        @RequestBody Flux<PartEvent> allEvents) {

    Map<String, String> fields = new LinkedHashMap<>();
    List<StoredFile> files = new ArrayList<>();

    return allEvents
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
            processPart(partEvents, fields, files)
        )
        .then(Mono.fromSupplier(() ->
            new UploadSummary(
                Map.copyOf(fields),
                List.copyOf(files)
            )
        ));
}
~~~

Hàm xử lý một part:

~~~java
private Mono<Void> processPart(
        Flux<PartEvent> partEvents,
        Map<String, String> fields,
        List<StoredFile> files) {

    return partEvents.switchOnFirst((signal, events) -> {
        if (!signal.hasValue()) {
            return events.then();
        }

        PartEvent first = signal.get();

        if (first instanceof FormPartEvent form) {
            fields.put(form.name(), form.value());
            return events.then();
        }

        if (first instanceof FilePartEvent file) {
            String originalFilename =
                Objects.requireNonNullElse(file.filename(), "");

            String contentType = Optional
                .ofNullable(file.headers().getContentType())
                .map(MediaType::toString)
                .orElse(MediaType.APPLICATION_OCTET_STREAM_VALUE);

            Path destination =
                uploadDirectory.resolve(UUID.randomUUID().toString());

            Flux<DataBuffer> contents =
                events.map(PartEvent::content);

            return Mono.fromCallable(
                    () -> Files.createDirectories(uploadDirectory)
                )
                .subscribeOn(Schedulers.boundedElastic())
                .then(DataBufferUtils.write(
                    contents,
                    destination,
                    StandardOpenOption.CREATE_NEW
                ))
                .then(Mono.fromRunnable(() ->
                    files.add(new StoredFile(
                        file.name(),
                        originalFilename,
                        destination.getFileName().toString(),
                        contentType
                    ))
                ));
        }

        return events
            .map(PartEvent::content)
            .doOnNext(DataBufferUtils.releaseConsumer())
            .then(Mono.<Void>error(
                new IllegalArgumentException("Unsupported multipart part")
            ));
    });
}
~~~

Ví dụ này tập trung vào cấu trúc xử lý. Trong code production, cần xác định rõ cách tiêu thụ/release buffer của form part theo reader đang dùng; cần cleanup file dở dang khi write lỗi hoặc request bị cancel; và phải áp dụng validation, size limit, authorization cùng quota.

Các kiểu dữ liệu trả về có thể định nghĩa:

~~~java
public record StoredFile(
    String partName,
    String originalFilename,
    String storageKey,
    String contentType
) {}

public record UploadSummary(
    Map<String, String> fields,
    List<StoredFile> files
) {}
~~~

Ở đây \`fields\` dùng map đơn giản nên nếu client gửi nhiều giá trị trùng tên, giá trị sau sẽ ghi đè giá trị trước. Nếu hợp đồng cho phép nhiều field cùng tên, hãy dùng \`MultiValueMap<String, String>\` hoặc cấu trúc danh sách.

## 12. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ dưới đây tạo endpoint nhận multipart gồm một trường \`description\` và một file:

- \`POST /api/uploads\`: đọc body dưới dạng \`Flux<PartEvent>\`.
- Form field được đọc qua \`FormPartEvent.value()\`.
- File được chia theo các event và ghi tuần tự bằng \`DataBufferUtils.write\`.
- Storage key do server tạo bằng UUID, không dùng tên file client làm path.
- Response trả metadata upload sau khi tất cả part được xử lý.

Cấu trúc:

~~~text
part-event-upload/
├── pom.xml
└── src/main/java/com/example/partev/
    ├── PartEventApplication.java
    └── UploadController.java
~~~

File \`pom.xml\` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>part-event-upload</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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

File \`src/main/java/com/example/partev/PartEventApplication.java\`:

~~~java
package com.example.partev;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PartEventApplication {
    public static void main(String[] args) {
        SpringApplication.run(PartEventApplication.class, args);
    }
}
~~~

File \`src/main/java/com/example/partev/UploadController.java\`:

~~~java
package com.example.partev;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.codec.multipart.FilePartEvent;
import org.springframework.http.codec.multipart.FormPartEvent;
import org.springframework.http.codec.multipart.PartEvent;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private final Path uploadDirectory =
        Path.of("uploads").toAbsolutePath().normalize();

    public record StoredFile(
        String partName,
        String originalFilename,
        String storageKey,
        String contentType
    ) {}

    public record UploadSummary(
        Map<String, String> fields,
        List<StoredFile> files
    ) {}

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<UploadSummary> upload(
            @RequestBody Flux<PartEvent> allEvents) {

        Map<String, String> fields = new LinkedHashMap<>();
        List<StoredFile> files = new ArrayList<>();

        return allEvents
            .windowUntil(PartEvent::isLast)
            .concatMap(partEvents ->
                processPart(partEvents, fields, files)
            )
            .then(Mono.fromSupplier(() ->
                new UploadSummary(
                    Map.copyOf(fields),
                    List.copyOf(files)
                )
            ));
    }

    private Mono<Void> processPart(
            Flux<PartEvent> partEvents,
            Map<String, String> fields,
            List<StoredFile> files) {

        return partEvents.switchOnFirst((signal, events) -> {
            if (!signal.hasValue()) {
                return events.then();
            }

            PartEvent first = signal.get();

            if (first instanceof FormPartEvent form) {
                fields.put(form.name(), form.value());
                return events.then();
            }

            if (first instanceof FilePartEvent file) {
                String originalFilename =
                    Objects.requireNonNullElse(file.filename(), "");

                String contentType = Optional
                    .ofNullable(file.headers().getContentType())
                    .map(MediaType::toString)
                    .orElse(MediaType.APPLICATION_OCTET_STREAM_VALUE);

                Path destination =
                    uploadDirectory.resolve(UUID.randomUUID().toString());

                Flux<DataBuffer> contents =
                    events.map(PartEvent::content);

                return Mono.fromCallable(
                        () -> Files.createDirectories(uploadDirectory)
                    )
                    .subscribeOn(Schedulers.boundedElastic())
                    .then(DataBufferUtils.write(
                        contents,
                        destination,
                        StandardOpenOption.CREATE_NEW
                    ))
                    .then(Mono.fromRunnable(() ->
                        files.add(new StoredFile(
                            file.name(),
                            originalFilename,
                            destination.getFileName().toString(),
                            contentType
                        ))
                    ));
            }

            return events
                .map(PartEvent::content)
                .doOnNext(DataBufferUtils.releaseConsumer())
                .then(Mono.<Void>error(
                    new IllegalArgumentException(
                        "Unsupported multipart part"
                    )
                ));
        });
    }
}
~~~

Chạy từ thư mục \`part-event-upload\` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

### Gửi multipart bằng cURL

~~~bash
curl -i -X POST http://localhost:8080/api/uploads \
  -F "description=Quarterly report" \
  -F "file=@./report.pdf;type=application/pdf"
~~~

cURL tự tạo boundary và Content-Type multipart phù hợp. Không đặt thủ công header \`Content-Type: multipart/form-data\` nếu không tự tạo boundary đúng.

Response JSON có dạng:

~~~json
{
  "fields": {
    "description": "Quarterly report"
  },
  "files": [
    {
      "partName": "file",
      "originalFilename": "report.pdf",
      "storageKey": "<server-generated-uuid>",
      "contentType": "application/pdf"
    }
  ]
}
~~~

Storage key là UUID được sinh ở server, nên giá trị cụ thể thay đổi mỗi lần upload. File được lưu trong thư mục \`uploads\` của working directory. Demo chưa có database, authentication, virus scan hoặc cleanup file dở dang; cần bổ sung trước khi triển khai production.

## 13. Gửi multipart streaming bằng WebClient

Spring WebFlux cũng hỗ trợ tạo multipart body từ \`PartEvent\` ở phía client. Có thể dùng:

- \`FormPartEvent.create(name, value)\` cho trường form.
- \`FilePartEvent.create(name, Path)\` hoặc \`FilePartEvent.create(name, Resource)\` cho file.
- \`Flux.concat(...)\` để nối các event thành một publisher.

Ví dụ:

~~~java
Path file = Path.of("report.pdf");

Flux<PartEvent> multipart = Flux.concat(
    FormPartEvent.create("description", "Quarterly report"),
    FilePartEvent.create("file", file)
);

Mono<UploadController.UploadSummary> result =
    webClient.post()
        .uri("http://localhost:8080/api/uploads")
        .body(multipart, PartEvent.class)
        .retrieve()
        .bodyToMono(UploadController.UploadSummary.class);
~~~

\`webClient\` là một instance \`WebClient\` đã được cấu hình trong ứng dụng. Multipart writer tạo boundary và serialize các PartEvent thành request body. Không cần tự dựng raw multipart bytes.

Nếu server nhận multipart và cần relay sang service khác, có thể truyền tiếp publisher event:

~~~java
Mono<Void> relay(Flux<PartEvent> incoming) {
    return webClient.post()
        .uri("http://storage-service/internal/upload")
        .body(incoming, PartEvent.class)
        .retrieve()
        .bodyToMono(Void.class);
}
~~~

Đây là ví dụ relay trực tiếp. Khi relay, publisher incoming chỉ được tiêu thụ một lần; không subscribe riêng để log rồi subscribe lần nữa để gửi. Nếu cần quan sát metadata, dùng các operator trong cùng một pipeline và bảo đảm buffer vẫn được chuyển tiếp hoặc giải phóng đúng ownership.

## 14. Multipart browser form và client

HTML form cần khai báo:

~~~html
<form method="post" enctype="multipart/form-data" action="/api/uploads">
  <label>
    Description
    <input type="text" name="description">
  </label>

  <label>
    File
    <input type="file" name="file">
  </label>

  <button type="submit">Upload</button>
</form>
~~~

Khi browser submit form, trình duyệt tự tạo multipart boundary và gửi từng part. Nếu dùng JavaScript \`fetch\` với \`FormData\`, cũng không tự đặt header Content-Type:

~~~javascript
const form = new FormData();
form.append("description", "Quarterly report");
form.append("file", fileInput.files[0]);

const response = await fetch("/api/uploads", {
  method: "POST",
  body: form
});
~~~

Browser cần tự đặt boundary trong header. Nếu code tự ghi đè Content-Type thành \`multipart/form-data\` mà không có boundary, server không thể phân tách các part đúng cách.

## 15. Xử lý lỗi, cancellation và file dở dang

Multipart upload có thể thất bại giữa chừng vì:

- Client ngắt kết nối.
- Request bị timeout.
- File vượt giới hạn.
- Storage hết dung lượng hoặc không ghi được.
- Permission filesystem bị từ chối.
- Dữ liệu multipart sai định dạng.
- Service downstream ngừng hoạt động khi đang relay.

Khi request bị cancel hoặc ghi file lỗi, ứng dụng cần có chính sách dọn dữ liệu đã ghi một phần. Một thiết kế thực tế có thể:

1. Ghi vào file tạm với storage key do server tạo.
2. Chỉ đánh dấu upload hoàn tất sau khi toàn bộ part đã được ghi thành công.
3. Nếu lỗi/cancel, xóa file tạm bằng cleanup publisher.
4. Khi thành công, atomically move file tạm sang vị trí đã xác nhận nếu filesystem hỗ trợ.
5. Ghi metadata vào database sau khi file hoàn tất hoặc dùng trạng thái upload để khôi phục nếu process dừng giữa chừng.

Không nên coi việc nhận được event đầu tiên là upload thành công. File chỉ hoàn tất khi event cuối của part đã được xử lý và writer hoàn tất.

Nếu relay sang service khác, lỗi downstream phải lan theo pipeline. Không nuốt lỗi rồi trả response thành công khi file chưa được nhận đầy đủ.

## 16. Phân biệt streaming với lưu tạm trên đĩa

\`Flux<PartEvent>\` cho phép ứng dụng xử lý nội dung theo luồng. Điều đó không có nghĩa toàn bộ request luôn nằm trong RAM, cũng không có nghĩa mọi part tự động được ghi vào một file tạm theo cùng chính sách.

Một số API multipart khác có thể parse part và lưu file lớn vào temporary storage tùy reader/configuration. Trong khi đó, \`PartEventHttpMessageReader\` cung cấp stream event cho ứng dụng tự tiêu thụ.

So sánh:

| Cách tiếp cận | Nơi giữ dữ liệu | Quyền kiểm soát |
| --- | --- | --- |
| \`@RequestBody Mono<MultiValueMap<String, Part>>\` | Multipart được parse thành map; reader có thể quản lý part storage | Dễ truy cập theo tên nhưng cần cấu hình giới hạn |
| \`@RequestPart FilePart\` | Part abstraction do multipart reader quản lý | API thuận tiện cho upload thông thường |
| \`@RequestBody Flux<PartEvent>\` | Event và buffer được phát tuần tự | Ứng dụng quyết định ghi, relay, release và cleanup |

Nếu mục tiêu chỉ là upload file vừa phải, \`FilePart\` thường đơn giản hơn. Nếu cần xử lý streaming, relay, kiểm tra từng phần hoặc tránh gom toàn bộ multipart vào map, \`Flux<PartEvent>\` cho quyền kiểm soát rõ hơn.

## 17. Những lỗi thường gặp

1. **Coi một FilePartEvent là toàn bộ file:** file lớn có thể được chia thành nhiều event. Dùng \`windowUntil(PartEvent::isLast)\` để gom event theo part.
2. **Không kiểm tra isLast():** có thể xử lý file khi nội dung vẫn chưa hoàn tất. Chờ window của part hoàn thành.
3. **Dùng collectList() cho toàn bộ PartEvent:** gom cả request vào bộ nhớ và làm mất lợi ích streaming. Xử lý từng window bằng \`concatMap\`.
4. **Dùng @RequestPart khi yêu cầu xử lý từng event:** \`@RequestPart\` tiện cho named part nhưng không phải API tuần tự theo PartEvent. Dùng \`@RequestBody Flux<PartEvent>\`.
5. **Đọc multipart thành MultiValueMap rồi tiếp tục đọc raw body:** body đã được parse/cache; không thể coi raw request body là một stream mới.
6. **Không consume hoặc release DataBuffer:** có thể gây leak pooled buffer. Mọi content phải được ghi, relay hoặc release.
7. **Gọi subscribe() trong controller:** tách upload khỏi lifecycle HTTP, làm cancellation và lỗi khó quản lý. Trả publisher để WebFlux quản lý.
8. **Gọi block() khi ghi file hoặc xử lý part:** có thể chặn event-loop. Dùng API reactive; đưa thao tác filesystem blocking như tạo thư mục sang boundedElastic.
9. **Dùng tên file client gửi làm path:** có nguy cơ path traversal hoặc ghi đè. Sinh storage key an toàn từ server.
10. **Tin Content-Type do client gửi:** header có thể giả mạo. Kiểm tra nội dung thực tế và chính sách file type.
11. **Không giới hạn số part:** request có thể gửi rất nhiều field/file. Cấu hình maxParts và quota.
12. **Không giới hạn form field:** trường văn bản có thể lớn bất thường. Đặt maxInMemorySize.
13. **Không giới hạn kích thước file:** streaming không có nghĩa file vô hạn. Đặt maxPartSize và request limit ở gateway.
14. **Dùng flatMap không giới hạn cho file:** có thể mở quá nhiều file writer và tăng áp lực storage. Dùng concatMap hoặc flatMap có concurrency hữu hạn.
15. **Không cleanup khi client cancel:** file dở dang có thể chiếm storage lâu dài. Gắn cleanup với lifecycle upload.
16. **Ghi file trước khi kiểm tra quyền:** có thể cho phép user không hợp lệ tiêu tốn storage. Xác thực/ủy quyền và quota trước hoặc trong quá trình upload.
17. **Relay cùng publisher nhiều lần:** request body là stream một lần. Không subscribe để log rồi subscribe lần nữa để gửi.
18. **Đặt Content-Type multipart thủ công thiếu boundary:** server không parse được các part. Để cURL, browser hoặc WebClient tạo boundary.
19. **Cho rằng PartEvent tự lưu file:** PartEvent chỉ là event API. Ứng dụng phải chọn nơi lưu và thực hiện write/relay.
20. **Không phân biệt form field và file part:** dùng \`switchOnFirst\` và kiểm tra subtype trước khi đọc nội dung.

## 18. Checklist triển khai multipart streaming

Trước khi đưa endpoint upload vào production, kiểm tra:

- Endpoint nhận đúng \`multipart/form-data\`.
- Handler dùng \`Flux<PartEvent>\` khi cần xử lý tuần tự.
- Dùng \`windowUntil(PartEvent::isLast)\` để chia đúng part.
- Dùng \`switchOnFirst\` để phân loại FormPartEvent và FilePartEvent.
- Mỗi file được xử lý hết tất cả event, không chỉ event đầu.
- Mọi DataBuffer được consume, relay hoặc release.
- Không gom toàn bộ file vào \`byte[]\`, \`String\` hoặc \`List<DataBuffer>\`.
- File được lưu bằng storage key do server tạo.
- Có giới hạn form field, headers, số part và kích thước file.
- Có quota, timeout, authorization và kiểm tra nội dung.
- Có cleanup file tạm khi lỗi/cancel.
- Có chính sách tên file gốc và metadata.
- Client không tự đặt multipart boundary.
- Không subscribe/block thủ công trong controller.
- Có test cho file nhiều buffer, part rỗng, form field, upload lớn, lỗi ghi và cancellation.

## 19. Câu hỏi tự kiểm tra

**1.** \`PartEvent\` là gì? Event đại diện một phần của multipart request, gồm headers và DataBuffer content.

**2.** Form field tạo event nào? \`FormPartEvent\`, có thể đọc giá trị bằng \`value()\`.

**3.** File upload tạo event nào? \`FilePartEvent\`; file lớn có thể phát nhiều event.

**4.** \`isLast()\` biểu thị gì? Event hiện tại là event cuối cùng của part đó.

**5.** Vì sao dùng \`windowUntil(PartEvent::isLast)\`? Để nhóm toàn bộ event thuộc cùng một part thành một window.

**6.** \`switchOnFirst()\` giúp gì? Nhận diện loại part qua event đầu tiên trước khi chọn cách xử lý.

**7.** Vì sao \`concatMap\` thường phù hợp? Nó xử lý từng part theo thứ tự và chờ part trước hoàn tất.

**8.** Có nên dùng \`collectList()\` với multipart file lớn không? Không nếu mục tiêu là streaming; nó gom dữ liệu vào bộ nhớ.

**9.** Tại sao phải tiêu thụ hoặc release DataBuffer? Trên một số server, buffer được pool và reference-counted; bỏ quên có thể gây memory leak.

**10.** Tên file gốc có nên dùng trực tiếp làm đường dẫn không? Không. Hãy sinh storage key phía server và giữ tên gốc như metadata.

**11.** \`@RequestPart\` có giống \`Flux<PartEvent>\` không? Không. RequestPart thuận tiện cho named part; Flux<PartEvent> xử lý event tuần tự.

**12.** Client có cần tự tạo boundary khi dùng cURL hoặc WebClient không? Không. Để client multipart writer tạo boundary và Content-Type.

**13.** Nếu upload bị cancel giữa file thì sao? Dừng upstream và cleanup file tạm/partial theo lifecycle.

**14.** Streaming có bỏ qua giới hạn kích thước không? Không. Vẫn cần giới hạn form field, headers, số part, kích thước file, quota và timeout.

**15.** Khi relay PartEvent bằng WebClient, có thể subscribe publisher nhiều lần không? Không. Body là stream một lần; compose cùng một pipeline.

**Ghi nhớ:** \`Flux<PartEvent>\` cho phép đọc multipart theo luồng. Mỗi form field thường tạo một \`FormPartEvent\`; file lớn có thể tạo nhiều \`FilePartEvent\`. Dùng \`windowUntil(PartEvent::isLast)\` để chia part, \`switchOnFirst\` để phân loại, và \`concatMap\` để xử lý tuần tự. Mọi DataBuffer phải được ghi, relay hoặc release. Hãy sinh tên lưu file từ server, đặt giới hạn multipart, xử lý cancellation và cleanup, đồng thời để cURL/browser/WebClient tự tạo boundary.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — Multipart Content in WebFlux Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 — Multipart Streaming in Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Framework 6.2 — Reactive Core and Multipart Readers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [PartEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/PartEvent.html)
- [PartEventHttpMessageReader Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/PartEventHttpMessageReader.html)
- [DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [WebClient Multipart Request Body](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-body.html).