# StreamingResponseBody, Resource và Content-Disposition khi tải xuống trong Spring MVC

## 1. Mục tiêu và phạm vi

Khi xây dựng API tải xuống tài liệu, báo cáo CSV, ảnh hoặc file lưu trong storage, controller Spring MVC phải quyết định **dữ liệu lấy từ đâu**, **ghi HTTP response body theo cách nào**, và **trình duyệt sẽ hiển thị hay tải về file**. Ba công cụ liên quan trực tiếp:

- **`Resource`**: abstraction của Spring cho một nguồn dữ liệu như file, classpath resource, mảng byte hoặc stream; có thể trả qua `ResponseEntity<Resource>`.
- **`StreamingResponseBody`**: callback để ứng dụng ghi từng phần vào `OutputStream` của response, thích hợp khi tạo hoặc chuyển dữ liệu lớn mà không dựng toàn bộ body trong heap.
- **`Content-Disposition`**: response header chỉ dẫn cách xử lý nội dung, đặc biệt `attachment` cùng tên file tải xuống hoặc `inline` khi phù hợp.

Sau bài này, bạn sẽ hiểu luồng render/download của Spring MVC, cách đặt `Content-Type`, `Content-Length`, `Content-Disposition`, sự khác nhau giữa buffered và streaming, các trường hợp HTTP Range, cơ chế bất đồng bộ của Servlet stack, và cách kiểm thử **status + headers + bytes thực tế** bằng MockMvc.

**Phiên bản mã minh họa:** Java 17+, Spring Framework 6.x, Spring Boot 3.x, **Spring MVC Servlet stack** (`spring-boot-starter-web`). Đây không phải ví dụ WebFlux: `Flux<DataBuffer>`, reactive backpressure và `ServerResponse` thuộc cơ chế khác.

## 2. Download thực chất là một HTTP response

Một response tải file bình thường có thể trông như sau:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Disposition: attachment; filename="sample.txt"
Content-Length: 17
X-Content-Type-Options: nosniff

Hello Spring MVC
~~~

Các điểm cần hiểu:

1. **HTTP status** biểu diễn kết quả: `200 OK` khi có toàn bộ file, `206 Partial Content` cho một range hợp lệ được xử lý, `404 Not Found` khi không có resource được phép tải, `403 Forbidden` khi không có quyền, `416 Range Not Satisfiable` khi yêu cầu range không thể đáp ứng theo quy tắc HTTP.
2. **`Content-Type`** mô tả định dạng bytes. Ví dụ `application/pdf`, `image/png`, `text/csv` hoặc `application/octet-stream` khi chỉ muốn biểu diễn dữ liệu nhị phân chung. Header này **khác** với tên file.
3. **`Content-Disposition`** quyết định hướng xử lý `attachment`/ `inline`, đồng thời truyền filename nếu cần. Trình duyệt có thể áp dụng chính sách của nó; header không đảm bảo luôn hiện một hộp thoại “Save As”.
4. **`Content-Length`** là số byte của response representation **nếu biết và có thể khai báo đúng**. Ví dụ `Hello Spring MVC\n` dùng UTF-8 gồm 17 byte, với ký tự xuống dòng LF.
5. Body có thể là bytes đọc từ file, sinh từ báo cáo hoặc lấy từ object storage. Không nhất thiết là JSON; `ResponseEntity<byte[]>`, `ResponseEntity<Resource>` và `ResponseEntity<StreamingResponseBody>` đều có thể trả file.
6. `HEAD` và HTTP Range, cache, proxy, reverse proxy, content compression là những vấn đề khác cần xét theo hợp đồng API.

Đối với response file, **không** gói raw file bytes vào một JSON string rồi hy vọng browser tự hiểu là file. Nếu metadata cần đi cùng file, có thể cung cấp một API metadata riêng hoặc headers được định nghĩa rõ; tránh thay đổi tùy tiện media type của body.

## 3. `Resource`: abstraction đọc bytes từ một nguồn

Giao diện `org.springframework.core.io.Resource` kế thừa `InputStreamSource`, cung cấp các khả năng như:

| API | Vai trò | Lưu ý |
| --- | --- | --- |
| `getInputStream()` | Mở stream để đọc nội dung | Người đọc thường phải đóng stream đúng vòng đời |
| `exists()` | Kiểm tra resource hiện diện | Không thay cho kiểm tra quyền truy cập |
| `isReadable()` | Có thể đọc hay không | Có thể thay đổi giữa lúc kiểm tra và đọc |
| `contentLength()` | Xác định kích thước nếu nguồn hỗ trợ | Một số dạng stream có thể tiêu thụ nội dung để tính length |
| `getFilename()` | Lấy tên resource nếu biết | Không được mặc nhiên tin tên từ client |
| `getURI()`, `getURL()` | Vị trí resource nếu hỗ trợ | Không phải lúc nào cũng có filesystem path |
| `isFile()`, `getFile()` | Kiểm tra/truy cập nguồn file thật khi phù hợp | Resource trong JAR thường không phải file rời |

Các implementation quan trọng:

| Implementation | Nguồn dữ liệu | Dùng khi |
| --- | --- | --- |
| `ByteArrayResource` | Mảng byte đã có trong memory | Nội dung nhỏ, dữ liệu test, file sinh sẵn trong memory |
| `FileSystemResource` | File trên filesystem | Download từ vùng lưu trữ server có kiểm soát |
| `PathResource` | `java.nio.file.Path` | Khi code thao tác qua Path |
| `ClassPathResource` | Resource đóng gói trong classpath/JAR | Download fixture/file phân phối cùng ứng dụng |
| `UrlResource` | URL có thể truy cập | Chỉ với URL server kiểm soát; tránh SSRF từ URL user nhập |
| `InputStreamResource` | Stream đang mở/nguồn stream | **Cần đặc biệt thận trọng** với stream một lần và `contentLength()` |

Controller Spring MVC thường trả:

~~~java
@GetMapping("/sample")
public ResponseEntity<Resource> sample() {
    Resource resource = new ClassPathResource("downloads/sample.txt");
    return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"sample.txt\"")
            .body(resource);
}
~~~

Đây là **handler minh họa**, cần import `Resource`, `ClassPathResource`, `ResponseEntity`, `MediaType`, `HttpHeaders`, `GetMapping`. File `src/main/resources/downloads/sample.txt` phải tồn tại. Trong ứng dụng thật, kiểm tra resource tồn tại, quyền truy cập và xử lý IOException; không để trường hợp thiếu file lộ stack trace hoặc đường dẫn nội bộ.

Khi trả `Resource`, Spring MVC thường dùng **`ResourceHttpMessageConverter`** để đọc source và ghi body response. Tùy resource/type/header, Spring có thể cung cấp metadata và hỗ trợ Range requests. Đây **không** đồng nghĩa Spring tự phân quyền file hoặc bảo vệ path traversal.

### Vì sao `ByteArrayResource` không thích hợp cho file rất lớn?

~~~java
byte[] wholeFile = Files.readAllBytes(path);
Resource resource = new ByteArrayResource(wholeFile);
~~~

Đây là đoạn minh họa trong method với `Path path`. `Files.readAllBytes` đọc toàn file vào heap. Nếu 200 người cùng tải file 200 MiB, dung lượng heap có thể tăng không kiểm soát. Với file đã có trên disk, `FileSystemResource`/`PathResource` thường tránh phải dựng một bản sao toàn bộ file trong byte array. Nếu dữ liệu được **sinh dần**, `StreamingResponseBody` thường biểu đạt ý định rõ hơn.

## 4. `Content-Disposition`: attachment, inline và tên file

HTTP response header thường gặp:

~~~http
Content-Disposition: attachment; filename="report.csv"
~~~

hoặc:

~~~http
Content-Disposition: inline; filename="diagram.png"
~~~

- **`attachment`**: gợi ý user agent xử lý response như một nội dung có thể lưu/tải xuống, thường sử dụng `filename` làm tên gợi ý.
- **`inline`**: cho phép trình duyệt hiển thị nội dung nếu trình duyệt có khả năng và chính sách cho phép, chẳng hạn ảnh/PDF. Không bảo đảm hiển thị ở mọi môi trường.
- **`filename`** chỉ là **tên gợi ý**, không phải đường dẫn file hệ thống, không phải quyền truy cập và không phải giá trị bảo mật có thể tin tuyệt đối.
- **`filename*`** theo encoding phù hợp giúp truyền tên có ký tự Unicode, ví dụ tên tiếng Việt. User agent có thể có khác biệt về ưu tiên `filename`/ `filename*`.

### 4.1. Dùng `ContentDisposition` builder của Spring

Thay vì ghép một chuỗi header với dấu nháy và dấu phân tách bằng tay:

~~~java
String disposition = ContentDisposition.attachment()
        .filename("report.csv")
        .build()
        .toString();

return ResponseEntity.ok()
        .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
        .body(resource);
~~~

Đây là **đoạn minh họa trong method** có biến `Resource resource`; cần import `org.springframework.http.ContentDisposition`, `HttpHeaders`, `ResponseEntity`. Builder giúp tạo cú pháp header đúng và escape ký tự trong filename theo quy tắc implementation.

Nếu tên có Unicode, Spring Framework 6.x hỗ trợ:

~~~java
String disposition = ContentDisposition.attachment()
        .filename("báo-cáo.csv", StandardCharsets.UTF_8)
        .build()
        .toString();
~~~

Theo Javadoc, `filename(String, Charset)` encode tên theo RFC 5987; hỗ trợ UTF-8 và các charset được API cho phép. Khi tải xuống qua `Content-Disposition` của HTTP response, cách này có thể hữu ích. **Đừng áp dụng overload này cho phần `Content-Disposition` của multipart/form-data request**, vì RFC 7578 không cho dùng cơ chế `filename*` của RFC 5987 trong multipart form upload.

**Tránh ghép filename thô từ input người dùng:** filename có thể chứa dấu nháy, CR/LF, dấu phân tách đường dẫn hoặc chuỗi điều khiển. Builder xử lý escaping header, nhưng ứng dụng vẫn phải giới hạn tên hiển thị, ký tự nguy hiểm và luôn sử dụng **tên/path ở server được quản lý**. Không cho một tham số `filename` từ request quyết định file nào được đọc.

### 4.2. `Content-Type` không được lựa chọn tùy tiện theo extension

Ví dụ file PDF có MIME `application/pdf`; CSV có thể dùng `text/csv`; dữ liệu không biết rõ có thể dùng `application/octet-stream`. Đừng tin hoàn toàn `MultipartFile.getContentType()`, đuôi tên file hoặc dữ liệu metadata do client nhập từ bước upload trước.

Nếu server trả file do user upload, cần xác thực loại file và quyết định `Content-Type` phù hợp. Với nội dung không đáng render inline, chọn `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` và storage/download origin có chính sách bảo mật thích hợp. `attachment` hoặc `nosniff` là lớp phòng vệ, không bảo đảm mọi trình duyệt ngăn mọi tấn công nếu response chứa active content nguy hiểm.

## 5. `Resource`, Range và giới hạn của `StreamingResponseBody`

Với một `ResponseEntity<Resource>` phù hợp, Spring MVC có thể xử lý một HTTP `Range` request để trả một phần file, hỗ trợ tải tiếp và media seeking. Ví dụ client xin `Range: bytes=0-4` trên representation dài 17 bytes; phản hồi thành công một vùng thường là:

```http
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-4/17
Content-Length: 5

Hello
```

Đây là **byte offsets**, không phải chỉ số ký tự Unicode. `206` chỉ đúng khi server thực sự phục vụ range tương ứng; range không thể đáp ứng có thể dẫn tới `416 Range Not Satisfiable`. Điều kiện cache như `ETag`, `If-Range` và representation encoding phải được xét khi cần download resume an toàn.

Điểm khác biệt cần nhớ để chọn API download: một `Resource` có thể được Spring MVC hỗ trợ Range qua message converters thích hợp, còn `StreamingResponseBody` chỉ là callback ghi vào `OutputStream` — **không tự tạo khả năng HTTP Range/206**. `InputStreamResource` một-lần-đọc cũng không nên được đối xử như `FileSystemResource` có thể truy xuất byte ranges và tính kích thước lặp lại. Chi tiết xử lý các dạng Range, multi-range response, `ResourceRegion` và `416` thuộc bài chuyên sâu ngay sau phần download trong chương.

## 6. `StreamingResponseBody`: ghi trực tiếp vào OutputStream

Spring MVC cung cấp functional interface:

~~~java
@FunctionalInterface
public interface StreamingResponseBody {
    void writeTo(OutputStream outputStream) throws IOException;
}
~~~

Đây là **biểu diễn chữ ký rút gọn**, không phải toàn bộ source của thư viện Spring. Handler có thể trả `StreamingResponseBody` hoặc `ResponseEntity<StreamingResponseBody>`:

~~~java
@GetMapping("/download-stream")
public ResponseEntity<StreamingResponseBody> download() {
    StreamingResponseBody body = outputStream -> {
        for (int i = 1; i <= 3; i++) {
            byte[] bytes = ("row-" + i + "\n")
                    .getBytes(StandardCharsets.UTF_8);
            outputStream.write(bytes);
        }
        outputStream.flush();
    };

    return ResponseEntity.ok()
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment()
                            .filename("rows.txt").build().toString())
            .contentType(MediaType.TEXT_PLAIN)
            .body(body);
}
~~~

Đây là đoạn handler minh họa trong controller, cần imports và một ứng dụng Spring MVC có async support. Nó sẽ gửi:

~~~text
row-1
row-2
row-3
~~~

Thứ tự bytes là tất định vì callback ghi tuần tự theo vòng for. Đây **không phải** luồng SSE, không mở một kết nối gửi sự kiện không kết thúc; chỉ là response file được ghi theo từng đoạn.

### 6.1. Điểm mạnh

- Không cần `ByteArrayOutputStream` gom toàn bộ file hoặc CSV lớn rồi mới gửi.
- Có thể copy từ một `InputStream` mở trong callback, hoặc tạo từng dòng báo cáo ngay khi đang ghi.
- Có thể kết hợp `ResponseEntity` để đặt status, headers, MIME type và filename **trước lúc ghi body**.
- Giảm nhu cầu giữ toàn bộ bytes trên heap; phù hợp với dữ liệu được tạo tuần tự hoặc đọc từ kho dữ liệu lớn.

### 6.2. Điều `StreamingResponseBody` không làm

- Đây là **Servlet MVC asynchronous request processing**, nhưng bản thân việc gọi `OutputStream.write(...)` thông thường vẫn có thể **blocking**. Nó không tự động biến server thành non-blocking reactive I/O hay cấp backpressure kiểu Reactor.
- Không tự implement HTTP Range, virus scanning, authentication, rate limiting, checksum, compression hoặc retry/resume.
- Không tự giải quyết việc client ngắt kết nối, storage bị lỗi, connection timeout hoặc thread pool quá tải.
- Không tạo `Content-Length` nếu bạn không biết trước kích thước. Response có thể dùng chunked transfer trong HTTP/1.1 hoặc cơ chế framing khác trong HTTP/2.
- Không đảm bảo rằng browser bắt đầu nhận bytes ngay sau mỗi lần `write`; buffer của Servlet container, proxy, HTTP stack và client có thể trì hoãn.

### 6.3. Stream file hiện hữu bằng `Files.copy`

Nếu bạn đã xác thực quyền truy cập và có một `Path` an toàn trỏ đến file hiện hữu:

~~~java
StreamingResponseBody body = outputStream -> {
    try (InputStream input = Files.newInputStream(authorizedPath)) {
        input.transferTo(outputStream);
    }
    outputStream.flush();
};
~~~

Đây là đoạn minh họa trong một method có biến `Path authorizedPath` đã được chọn từ metadata server và đã kiểm tra quyền. `InputStream.transferTo` dùng một buffer hợp lý để copy stream; không bắt buộc gom cả file vào byte array.

**Mở input bên trong callback** là quan trọng vì callback có thể chạy trên executor **sau khi controller method trả về**. Không mở một `InputStream` trong try-with-resources của method handler rồi đóng nó trước khi task streaming bắt đầu.

Không tự đóng `outputStream` do container sở hữu trong các handler thông thường; flush khi thích hợp, để framework/container quản lý vòng đời response.

## 7. Async Servlet, thread pool và thời hạn xử lý

Khi handler trả `StreamingResponseBody`, Spring MVC dùng cơ chế async request để thực hiện callback trong một task. Thread xử lý request ban đầu có thể được trả về container, trong khi callback vẫn đang ghi dữ liệu trên một thread từ **AsyncTaskExecutor**.

Đối với production, tài liệu Spring MVC khuyến nghị **cấu hình rõ executor phù hợp**. Không dựa vào executor mặc định không phù hợp với tải thực tế nếu hệ thống có nhiều request streaming kéo dài. Một ví dụ dùng Spring MVC Java config:

~~~java
@Configuration
public class DownloadAsyncConfig implements WebMvcConfigurer {

    private final AsyncTaskExecutor executor;

    public DownloadAsyncConfig(
            @Qualifier("downloadExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Bean(name = "downloadExecutor")
    public static ThreadPoolTaskExecutor downloadExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("download-");
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(60_000L);
    }
}
~~~

Đây là class minh họa đầy đủ về cấu trúc cấu hình; cần import Spring `@Configuration`, `@Bean`, `@Qualifier`, `AsyncTaskExecutor`, `ThreadPoolTaskExecutor`, `WebMvcConfigurer`, `AsyncSupportConfigurer`. Phần 9 sẽ cung cấp các import đầy đủ cho ứng dụng runnable.

**Lưu ý:** core/max pool 4/8, queue 64 và timeout 60 giây là thông số demo, **không phải tối ưu mặc định cho mọi ứng dụng**. Kích thước executor phải dựa trên tốc độ lưu trữ, thời gian truyền, số client đồng thời, memory, backpressure/throttling tại application và thời hạn ở reverse proxy. Timeout của Servlet container/proxy có thể khác thời hạn cấu hình MVC.

Nếu có Spring Security, Servlet filters hoặc MDC/tracing dùng `ThreadLocal`, cần kiểm tra async dispatch và **context propagation**. Không giả định mọi thread-local được sao chép tự động sang worker thread. Dùng cơ chế tích hợp của Spring Security/Micrometer và cấu hình filter dispatch types phù hợp.

### Lỗi sau khi response đã commit

Khi response body đã bắt đầu được gửi, status và headers có thể đã được **commit**. Nếu file bị mất giữa chừng hoặc output stream ném `IOException`, server **không thể đơn giản đổi** từ 200 sang 500 kèm JSON lỗi sạch. Client có thể nhận response bị cắt hoặc lỗi kết nối.

Do đó:

1. Kiểm tra quyền, existence, metadata, content type và kích thước phù hợp **trước khi trả body**.
2. Trong callback, sử dụng `try/finally` hoặc try-with-resources để đóng **nguồn input**.
3. Để IOException lan ra đúng cơ chế lỗi/log thay vì nuốt rồi tuyên bố file hoàn chỉnh.
4. Client phải xử lý nội dung chưa đầy đủ, timeout và checksum khi use case yêu cầu.
5. Với báo cáo sinh động có khả năng fail cao, cân nhắc tạo file/job hoàn chỉnh ở backend trước, sau đó cung cấp URL download khi báo cáo sẵn sàng.

## 8. So sánh `Resource`, `byte[]`, `StreamingResponseBody`

| Tiêu chí | `ResponseEntity<byte[]>` | `ResponseEntity<Resource>` | `ResponseEntity<StreamingResponseBody>` |
| --- | --- | --- | --- |
| Dạng dữ liệu | Toàn bytes đã ở bộ nhớ | Resource abstraction | Callback ghi từng đoạn |
| Bộ nhớ khi file lớn | Thường cao nếu dựng toàn bộ byte[] | Tùy Resource: file có thể đọc theo stream | Có thể giữ bộ nhớ thấp |
| Tạo báo cáo theo dòng | Cần gom bytes trước | Có thể dùng resource đã tạo | Rất phù hợp |
| Chuyển file từ disk | Có thể dùng nhưng không tối ưu | `FileSystemResource`/`PathResource` thường hợp lý | `Files.copy` khi cần logic streaming riêng |
| Content-Length | Biết nếu có byte[] | Có thể biết qua Resource | Chỉ đặt nếu tính chính xác từ trước |
| Range requests | Không mặc định tự áp dụng theo byte[] như Resource | Spring MVC hỗ trợ với resource phù hợp | Ứng dụng tự xử lý nếu cần |
| Async callback | Không | Không phải API streaming callback này | Có, trên Servlet async processing |
| Độ phức tạp | Thấp | Thấp-vừa | Cao hơn: executor, timeout, stream lifecycle |
| Dữ liệu nhạy cảm | Phải kiểm tra quyền | Phải kiểm tra quyền | Phải kiểm tra quyền |

Không có lựa chọn “luôn tốt nhất”. Với file có sẵn trong storage, trả `Resource` có thể đơn giản và đáng tin hơn. Với báo cáo CSV được sinh ngay trong lúc response đang ghi hoặc dữ liệu từ nguồn lớn được đọc tuần tự, `StreamingResponseBody` thường là lựa chọn sáng sủa.

## 9. Ví dụ chạy được: file Resource và báo cáo CSV streaming

Ứng dụng mẫu có hai endpoint:

- `GET /api/downloads/resource`: trả nội dung `Hello Spring MVC\n` dạng text file bằng `ByteArrayResource`, có `Content-Disposition: attachment`, `Content-Length` xác định.
- `GET /api/downloads/stream`: sinh CSV ba dòng dữ liệu bằng `StreamingResponseBody`, đặt `Content-Disposition`, không gom toàn bộ báo cáo vào RAM.
- `GET /api/downloads/inline`: thể hiện `Content-Disposition: inline` với một đoạn text, khác attachment.
  
Demo sử dụng bytes xác định để có thể kiểm thử kết quả chính xác mà không phải đọc file tùy ý của máy. **Đối với file lớn production, thay ByteArrayResource bằng FileSystemResource/PathResource hoặc đọc stream từ storage có kiểm soát.**

Tạo project Spring Initializr:

- Java: **17+**.
- Spring Boot: **3.x**.
- Build: Maven.
- Dependencies: **Spring Web**, **Spring Boot Starter Test**.
- Base package: `com.example.demo`.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/DownloadAsyncConfig.java
src/main/java/com/example/demo/DownloadController.java
src/test/java/com/example/demo/DownloadControllerTest.java
~~~

### 9.1. Khởi động `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.2. Cấu hình executor `DownloadAsyncConfig.java`

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class DownloadAsyncConfig implements WebMvcConfigurer {

    private final AsyncTaskExecutor executor;

    public DownloadAsyncConfig(
            @Qualifier("downloadExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Bean(name = "downloadExecutor")
    public static ThreadPoolTaskExecutor downloadExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("download-");
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(60_000L);
    }
}
~~~

`ThreadPoolTaskExecutor` được Spring quản lý vòng đời khi đăng ký qua `@Bean`. `@Bean` là static để tránh vòng khởi tạo giữa instance `@Configuration` và dependency executor do chính class cấu hình đó tạo ra. Khi application context khởi động, Spring cung cấp instance executor cho constructor.

### 9.3. Hai đường tải file trong `DownloadController.java`

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/api/downloads")
public class DownloadController {

    private static final byte[] SAMPLE =
            "Hello Spring MVC\n".getBytes(StandardCharsets.UTF_8);

    private static final String NOSNIFF = "X-Content-Type-Options";

    @GetMapping("/resource")
    public ResponseEntity<Resource> resource() {
        Resource body = new ByteArrayResource(SAMPLE);

        String disposition = ContentDisposition.attachment()
                .filename("sample.txt")
                .build()
                .toString();

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .contentLength(SAMPLE.length)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header(NOSNIFF, "nosniff")
                .body(body);
    }

    @GetMapping("/stream")
    public ResponseEntity<StreamingResponseBody> stream() {

        StreamingResponseBody body = out -> {
            out.write("id,name\n".getBytes(StandardCharsets.UTF_8));

            for (int i = 1; i <= 3; i++) {
                String line = i + ",item-" + i + "\n";
                out.write(line.getBytes(StandardCharsets.UTF_8));
            }
            out.flush();
        };

        String disposition = ContentDisposition.attachment()
                .filename("report.csv")
                .build()
                .toString();

        return ResponseEntity.ok()
                .contentType(
                        MediaType.parseMediaType("text/csv;charset=UTF-8"))
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header(NOSNIFF, "nosniff")
                .body(body);
    }

    @GetMapping("/inline")
    public ResponseEntity<Resource> inline() {
        Resource body = new ByteArrayResource(
                "Preview\n".getBytes(StandardCharsets.UTF_8));

        String disposition = ContentDisposition.inline()
                .filename("preview.txt")
                .build()
                .toString();

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header(NOSNIFF, "nosniff")
                .body(body);
    }
}
~~~

**Chi tiết quan trọng:**

1. Cả ba endpoint trả bytes, không chuyển dữ liệu thành JSON. `@RestController` khiến return values được Spring MVC xử lý như HTTP response; với `ResponseEntity<Resource>`, converter phù hợp đọc resource và ghi bytes.
2. `SAMPLE` chứa **17 byte UTF-8**, gồm text `Hello Spring MVC` 16 ký tự ASCII và một LF. Vì biết size chính xác, endpoint resource đặt `Content-Length: 17`.
3. `ByteArrayResource` trong bài mẫu chỉ chứa dữ liệu nhỏ cố định. Trong production với file lớn, thay bằng nguồn stream/file phù hợp, không đọc file lớn thành `byte[]`.
4. `/stream` sinh một header CSV rồi ba dòng; callback ghi từng dòng vào output. `Content-Length` không được đặt vì demo không cần precompute kích thước; HTTP stack chọn framing phù hợp.
5. `Content-Disposition.attachment()` tạo filename gợi ý để download. `ContentDisposition.inline()` cho phép browser xem text khi phù hợp, không nhất thiết mở dialog lưu file.
6. `X-Content-Type-Options: nosniff` là lớp phòng vệ cho MIME, không phải thay thế validation/authorization.
7. Pool cấu hình riêng cho StreamingResponseBody cần được giám sát nếu số lượng kết nối kéo dài tăng. Trong ứng dụng thật, xử lý client disconnect và timeout một cách có chủ đích.

## 10. Thử bằng curl

Khởi chạy từ thư mục có `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`; nếu không có Maven Wrapper, dùng `mvn spring-boot:run` khi đã cài Maven.

### 10.1. Tải `Resource`

~~~bash
curl -i http://localhost:8080/api/downloads/resource
~~~

Status **200 OK**, `Content-Type: text/plain`, `Content-Disposition` với `attachment; filename="sample.txt"`, `Content-Length: 17`, body:

~~~text
Hello Spring MVC
~~~

Đoạn Markdown hiển thị một dòng text; **bytes thực tế có LF cuối dòng**. Với file binary, không dùng `curl -i` để nhìn body trực tiếp trong terminal, vì các control bytes có thể làm terminal hiển thị sai; dùng:

~~~bash
curl -fL -D headers.txt   -o sample.txt   http://localhost:8080/api/downloads/resource
~~~

`-D headers.txt` lưu headers, `-o sample.txt` lưu bytes, `-f` báo lỗi HTTP 4xx/5xx. Nếu không chỉ định `-o`, `curl` ghi body ra stdout.

### 10.2. Tải báo cáo CSV streaming

~~~bash
curl -i http://localhost:8080/api/downloads/stream
~~~

Kết quả body kỳ vọng:

~~~csv
id,name
1,item-1
2,item-2
3,item-3
~~~

Header `Content-Disposition` gợi ý tên `report.csv`. Client chỉ có thể khẳng định file hoàn chỉnh khi đã đọc hết body đúng cách và không gặp lỗi. Không tự mặc định có `Content-Length` trên streaming response.

### 10.3. Thử `inline`

~~~bash
curl -i http://localhost:8080/api/downloads/inline
~~~

Trình duyệt có thể hiển thị `Preview` thay vì ép tải xuống nếu hỗ trợ text/plain và không có chính sách khác cản trở. `curl` chỉ hiển thị bytes, **không bắt chước chính xác quyết định hiển thị của browser**.

### 10.4. Thử byte Range với Resource

~~~bash
curl -i   -H "Range: bytes=0-4"   http://localhost:8080/api/downloads/resource
~~~

Với Spring MVC xử lý range cho `ByteArrayResource`, response thường là **206 Partial Content**, `Content-Range: bytes 0-4/17` và body đúng `Hello`. Nếu endpoint hoặc filter/proxy thay đổi body/headers, cần test integration thực tế để xác nhận. `StreamingResponseBody` không tự tạo cơ chế range tương tự.

Các lệnh shell ở trên dùng `\` để nối dòng trên Linux/macOS/Git Bash. Trên Windows PowerShell, dùng `curl.exe` với tham số trên một dòng hoặc ký tự nối dòng thích hợp.

## 11. MockMvc: kiểm tra headers, bytes, asyncDispatch và Range

Tạo file **`src/test/java/com/example/demo/DownloadControllerTest.java`**:

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DownloadControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void resourceReturnsAttachmentAndExpectedBytes() throws Exception {
        mockMvc.perform(get("/api/downloads/resource"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"sample.txt\""))
                .andExpect(header().longValue(
                        HttpHeaders.CONTENT_LENGTH, 17L))
                .andExpect(content().bytes(
                        "Hello Spring MVC\n".getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void streamReturnsCsvAsynchronously() throws Exception {
        MvcResult pending = mockMvc.perform(get("/api/downloads/stream"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"report.csv\""))
                .andExpect(content().string(
                        "id,name\n"
                        + "1,item-1\n"
                        + "2,item-2\n"
                        + "3,item-3\n"));
    }

    @Test
    void inlineResponseUsesInlineDisposition() throws Exception {
        mockMvc.perform(get("/api/downloads/inline"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "inline; filename=\"preview.txt\""))
                .andExpect(content().string("Preview\n"));
    }

    @Test
    void resourceHandlesSingleByteRange() throws Exception {
        mockMvc.perform(get("/api/downloads/resource")
                        .header(HttpHeaders.RANGE, "bytes=0-4"))
                .andExpect(status().isPartialContent())
                .andExpect(header().string(
                        HttpHeaders.CONTENT_RANGE, "bytes 0-4/17"))
                .andExpect(content().bytes(
                        "Hello".getBytes(StandardCharsets.UTF_8)));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

**Điểm then chốt của test:**

- Kiểm tra **status** và **đúng bytes**, không chỉ xem Content-Disposition.
- Kiểm tra `attachment` và `inline` là hai disposition khác nhau.
- Với `StreamingResponseBody`, controller bắt đầu **async processing**. Trong MockMvc phải chờ và thực hiện `asyncDispatch(pending)` rồi mới assert response hoàn chỉnh. Nếu test chỉ kiểm tra kết quả ngay sau `perform(...)` có thể thấy body chưa hoàn tất.
- Test Range xác minh resource có khả năng đáp ứng `206 Partial Content` cho đoạn bytes hợp lệ trong cấu hình mẫu.
- `@SpringBootTest` + `@AutoConfigureMockMvc` chạy MVC context với executor config thực tế của dự án. Nếu có Spring Security, các test GET có thể cần authentication theo rule đã cấu hình.
- MockMvc không chứng minh streaming qua mạng sẽ có throughput tốt hoặc hoạt động y hệt reverse proxy/Servlet connector; cần HTTP integration/performance tests khi tải file lớn thực.

## 12. Download file thật từ filesystem: xử lý path và quyền

Ứng dụng thật thường có file trong storage và nhận request kiểu `GET /api/documents/{id}/download`. **Không nhận trực tiếp absolute path từ client.** Hãy tra metadata bằng ID do server quản lý, kiểm tra người dùng hiện tại có quyền với document, rồi lấy storage key đã xác nhận.

Ví dụ **minh họa tách biệt với project ở phần 9**:

~~~java
@GetMapping("/documents/{id}/download")
public ResponseEntity<Resource> download(@PathVariable UUID id)
        throws IOException {

    DocumentRecord record = documentService.findAuthorized(id);
    Path file = storageService.resolveApprovedPath(record.storageKey());

    if (!Files.isRegularFile(file) || !Files.isReadable(file)) {
        return ResponseEntity.notFound().build();
    }

    Resource resource = new FileSystemResource(file);
    String header = ContentDisposition.attachment()
            .filename(record.safeDownloadName(), StandardCharsets.UTF_8)
            .build().toString();

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .contentLength(Files.size(file))
            .header(HttpHeaders.CONTENT_DISPOSITION, header)
            .header("X-Content-Type-Options", "nosniff")
            .body(resource);
}
~~~

**Đây chỉ là controller method minh họa:** `DocumentRecord`, `documentService`, `storageService` cần được định nghĩa; không phải file Java chạy độc lập. Các kiểu cần import gồm `UUID`, `Path`, `Files`, `IOException`, `Resource`, `FileSystemResource`, `ContentDisposition`, `StandardCharsets`, `ResponseEntity`, `MediaType`, `HttpHeaders`, `GetMapping`, `PathVariable`.

Lưu ý bảo mật:

1. **Tra quyền trước khi stream.** Không trả khác biệt nhạy cảm giữa 403 và 404 nếu chính sách yêu cầu không tiết lộ sự tồn tại của resource.
2. `storageKey` do server quản lý và dùng allowlist/canonical path. `root.resolve(input).normalize().startsWith(root)` chỉ kiểm tra **lexical path**, không đủ khi có symlink hoặc race. Với filesystem có attacker-controlled symlinks, cần storage isolation và cơ chế open file an toàn (canonical real path, `SecureDirectoryStream` khi thích hợp, quyền hệ điều hành).
3. **Không dùng `MultipartFile.getOriginalFilename()` trực tiếp làm file path** và không tự ghép `Content-Disposition` từ raw filename.
4. `Files.isRegularFile` rồi `Files.size` và mở file có thể gặp **TOCTOU race**: file có thể đổi giữa các bước. Trong storage có nhiều concurrent writes, cần cơ chế versioning/locking/object immutability nếu phải bảo đảm size/ETag khớp.
5. Nếu metadata xác nhận MIME đáng tin, có thể trả media type đúng; nếu không, `application/octet-stream` cùng `attachment` và `nosniff` thường thận trọng.
6. Log một `documentId`/request ID thay vì log full storage path, token hoặc nội dung file.
7. Với tải xuống rất lớn từ S3/GCS/object storage, cân nhắc **presigned URL ngắn hạn** khi mô hình bảo mật cho phép, thay vì proxy tất cả bytes qua Spring server; validate quyền trước khi cấp URL.

## 13. Không nên dùng `InputStreamResource` như một `FileSystemResource` thông thường

`InputStreamResource` biểu diễn nguồn stream đang mở và thường có tính **đọc một lần**. Một anti-pattern:

~~~java
InputStream input = Files.newInputStream(file);
Resource resource = new InputStreamResource(input);

// Tránh tự gọi resource.contentLength() trong hoàn cảnh này:
long length = resource.contentLength();
~~~

Đây là đoạn minh họa. Vì việc tính `contentLength()` trên một stream một lần có thể tiêu thụ stream, body có thể không còn đủ bytes để gửi. Spring Framework có xử lý đặc biệt ở một số nơi cho `InputStreamResource` chính xác (exact class), nhưng các subclass hoặc trường hợp gọi độ dài thủ công vẫn dễ mắc lỗi.

Tài liệu `ResponseEntity` khuyến nghị nếu phải dùng `InputStreamResource`, hãy cân nhắc **on-demand `InputStreamSource`**, và với custom subclass phải kiểm soát `contentLength()` để không tiêu thụ stream. Trong nhiều trường hợp:
- File trên disk → `FileSystemResource`/`PathResource`.
- File nhỏ trong memory → `ByteArrayResource`.
- Stream sinh/đọc tuần tự có logic riêng → `StreamingResponseBody` với nguồn input mở trong callback.

Đừng giả định Resource nào cũng hỗ trợ reopen, repeatable stream hoặc range giống nhau. Đặc tính của source quyết định.

## 14. `Content-Length`, Transfer-Encoding, HTTP/2 và buffering

### Biết chính xác kích thước

Với byte array, `contentLength(bytes.length)` là chính xác. Với file ổn định có `Files.size(file)`, size có thể phù hợp nhưng phải xét file có bị sửa trong lúc download hay không.

### Không biết trước kích thước

Với CSV sinh trên đường truyền, không cần dựng toàn file chỉ để biết `Content-Length`. Bỏ header này và để container/proxy dùng cơ chế HTTP phù hợp. Trong HTTP/1.1, response có thể dùng `Transfer-Encoding: chunked`; trong HTTP/2 không có `Transfer-Encoding: chunked` theo cách HTTP/1.1.

**Không tự đặt `Transfer-Encoding`** từ controller như một yêu cầu ứng dụng: HTTP server kiểm soát framing. Đừng tự gán một Content-Length ước lượng; client có thể nhận file hỏng nếu bytes không khớp header.

### Buffering nhiều lớp

`OutputStream.flush()` có thể đẩy buffer phía server, nhưng không đảm bảo dữ liệu vượt qua reverse proxy/CDN/browser ngay lập tức. Với streaming thật cần đo tại client và cấu hình proxy buffering, timeout phù hợp. Nhiều request streaming dài sẽ chiếm thread của executor và network resources, nên cần concurrency controls, rate limiting và telemetry.

### Compression và content encoding

Khi response được nén (`Content-Encoding: gzip`), `Content-Length`, Range và ETag phải xét **encoded representation bytes**. Tránh khai báo Content-Length của bytes chưa nén nếu HTTP middleware sẽ thay đổi payload trên wire. Test end-to-end khi bật gzip ở proxy/container.

## 15. HTTP caching, ETag và conditional requests

Download API có thể hỗ trợ cache để giảm băng thông nếu tài nguyên không nhạy cảm hoặc đã được phân quyền/cache an toàn:

- `ETag` nhận diện version của representation.
- `Last-Modified` cho biết thời gian sửa đổi.
- `Cache-Control` quy định khả năng cache và thời hạn.
- `If-None-Match` hoặc `If-Modified-Since` có thể dẫn đến `304 Not Modified` khi đủ điều kiện.
- `If-Range` kết hợp Range để bảo đảm client không ghép bytes của hai phiên bản file khác nhau.

Ví dụ metadata cho file công khai có version:

~~~http
HTTP/1.1 200 OK
ETag: "report-v3"
Cache-Control: public, max-age=3600
Content-Disposition: attachment; filename="report-v3.csv"
~~~

Đây chỉ là **ví dụ header**: trên production, `ETag` phải thực sự gắn với nội dung/version. Với file nhạy cảm, thường cần `Cache-Control: private` hoặc `no-store` theo threat model, không để shared cache/CDN lưu dữ liệu cá nhân vô tình.

Không làm ETag bằng cách đọc toàn bộ file lớn sau mỗi request chỉ để tính hash; có thể lưu content hash/version trong metadata khi upload/publish. Đừng tự trả 304 nếu request chưa được kiểm tra đúng preconditions của HTTP.

## 16. Chọn status và xử lý lỗi download

| Tình huống | HTTP status thường phù hợp | Ghi chú |
| --- | --- | --- |
| Resource tồn tại, được phép đọc toàn bộ | 200 | Body là bytes file |
| Một byte Range hợp lệ được đáp ứng | 206 | Có `Content-Range` tương ứng |
| Client xin range vượt giới hạn | 416 | Xem quy tắc response range và representation |
| ID không tồn tại hoặc không công khai sự tồn tại | 404 | Không lộ filesystem path |
| Có resource nhưng user không có quyền | 403 hoặc 404 theo chính sách | Phân quyền trước khi gửi bytes |
| Backend storage lỗi trước khi response commit | 500/503 tùy bản chất | Error response có thể nhất quán nếu chưa commit |
| Stream lỗi khi body đã gửi một phần | Có thể kết nối bị ngắt/body thiếu | Không còn đổi status tùy ý được |
| Backend tạo báo cáo chưa xong | 202 hoặc endpoint trạng thái job | Không cố stream response chưa xác định khi nghiệp vụ cần job |

Bảo đảm ứng dụng xử lý exception một cách nhất quán; tuy nhiên khi đã gửi bytes một phần, một `@RestControllerAdvice` không thể bảo đảm chuyển kết quả thành JSON body hợp lệ. Client download quan trọng cần kiểm tra tổng byte length, checksum/version hoặc thông tin integrity riêng.

## 17. Các lỗi thường gặp

### 17.1. Download “rỗng” dù controller trả 200

Có thể do `InputStream` bị đóng trước khi callback chạy, đã bị `contentLength()` tiêu thụ, hoặc file tạm upload đã bị cleanup trước khi download. Kiểm tra lifecycle của nguồn và nơi mở stream, dùng `FileSystemResource`/on-demand stream đúng cách.

### 17.2. Browser hiển thị PDF/HTML thay vì tải về

Có thể `Content-Disposition` thiếu `attachment`, `Content-Type` không phù hợp, hoặc browser có chính sách riêng. Dùng builder `ContentDisposition.attachment().filename(...)` khi sản phẩm thực sự yêu cầu download.

### 17.3. Tên file tải về chứa ký tự lỗi

Không ghép filename Unicode thô vào header theo cách không encode. Dùng `ContentDisposition.attachment().filename(name, UTF_8)` theo API Spring 6.x và kiểm thử với browsers mục tiêu. Chọn tên hiển thị đã kiểm tra, không coi filename là đường dẫn.

### 17.4. `StreamingResponseBody` chạy ổn trong dev nhưng treo khi nhiều client

Callback ghi output bằng blocking I/O trên async executor. Executor ít thread/queue quá lớn, storage chậm, client tải chậm hoặc proxy buffering có thể gây nghẽn. Cấu hình executor có giới hạn, timeouts, metrics và backpressure ở tầng ứng dụng.

### 17.5. MockMvc test stream có body rỗng

Nếu test không thực hiện `asyncDispatch`, có thể nó đang kiểm tra request **trước khi callback hoàn tất**. Dùng `request().asyncStarted()`, `MvcResult` và `asyncDispatch` rồi mới assert bytes.

### 17.6. Cứ `Resource` là tự hỗ trợ resumable download

Sai. Tùy Resource implementation, cấu hình converter, conditional request, reverse proxy và source có đủ metadata/repeatability. Đặc biệt `InputStreamResource` không thay thế hoàn toàn `FileSystemResource` cho Range.

### 17.7. Tin filename client để đọc file server

Sai. Không dùng `root.resolve(request.getParameter("path"))` hoặc `getOriginalFilename()` từ upload làm đường dẫn download. Dùng ID do server ánh xạ tới storage key và kiểm tra ACL/canonical path/symlink.

### 17.8. Cố đổi response thành 500 JSON sau khi stream đã commit

Không khả thi một cách đáng tin. Thực hiện preflight trước khi stream, báo lỗi vận hành qua log/metrics, và thiết kế client phát hiện download không đầy đủ.

### 17.9. Dùng `ByteArrayResource` cho mọi file lớn

Nếu bytes được dựng bằng `Files.readAllBytes`, bộ nhớ tăng theo kích thước file và số request đồng thời. Chọn file-backed Resource hoặc streaming phù hợp.

### 17.10. Đặt `Content-Length` và `Content-Encoding` không nhất quán

Nếu gzip middleware thay đổi bytes, Content-Length phải phản ánh representation gửi thực tế; nếu không chắc, không tự đặt size. Test sau reverse proxy thay vì chỉ kiểm tra MockMvc.

## 18. Câu hỏi ôn tập

**1. `Resource` và `StreamingResponseBody` khác nhau ở đâu?**

`Resource` mô tả nguồn dữ liệu để Spring `HttpMessageConverter` ghi ra response; `StreamingResponseBody` cho ứng dụng trực tiếp quyết định cách ghi từng đoạn vào `OutputStream` dưới cơ chế async MVC.

**2. `Content-Disposition: attachment` có bảo đảm browser chắc chắn mở hộp thoại Save As?**

Không. Nó là hướng dẫn disposition; browser và cấu hình người dùng có thể tự tải vào thư mục hoặc dùng cơ chế khác.

**3. Vì sao cần đặt filename qua `ContentDisposition` builder?**

Builder giúp tạo header đúng cú pháp, quote/escape filename; overload nhận UTF-8 hỗ trợ encode tên Unicode. Tên file vẫn cần được kiểm soát và không phải dữ liệu dùng để chọn storage path.

**4. `StreamingResponseBody` có phải non-blocking WebFlux?**

Không. Nó sử dụng Servlet async processing và thực hiện callback trên executor, còn ghi OutputStream thường vẫn blocking.

**5. Vì sao `InputStreamResource` có thể gây lỗi khi tính độ dài?**

Vì nguồn stream thường đọc một lần; một số thao tác tính `contentLength()` có thể đọc hết stream. Không tự gọi trên nguồn không repeatable.

**6. Khi nào client nhận 206?**

Khi server xử lý Range request hợp lệ, chỉ trả một phần bytes và báo `Content-Range` phù hợp. Streaming theo từng đoạn không tự dẫn đến 206.

**7. Có nên đặt `Content-Length` trên báo cáo CSV được sinh dần?**

Chỉ khi biết chính xác số bytes sẽ gửi và không có tầng biến đổi representation làm thay đổi nó. Nếu không biết trước, để server chọn HTTP framing.

**8. Nếu lỗi xảy ra sau khi đã gửi 100 KiB đầu của file thì trả JSON 500 được không?**

Không đáng tin. Response có thể đã commit. Cần xử lý log, failure/cancellation và phía client cần phát hiện incomplete download.

## 19. Checklist production

- Chọn `ResponseEntity<Resource>` khi nguồn là file/resource thích hợp; chọn `StreamingResponseBody` khi cần tạo/chuyển dữ liệu tuần tự mà không buffer toàn bộ.
- Đặt `Content-Type` phù hợp với nội dung đã xác minh; dùng `ContentDisposition` builder để gửi filename và disposition.
- Chỉ khai báo `Content-Length` khi biết chính xác; kiểm thử sau content encoding/proxy nếu có.
- Kiểm tra quyền truy cập, metadata, file existence và storage path **trước khi body bắt đầu**.
- Với storage file lớn, tránh `Files.readAllBytes`/memory buffering và `InputStreamResource` không repeatable khi cần Range.
- Nếu cần resume/range, chọn Resource phù hợp, kiểm tra `206`, `Content-Range`, `ETag`/`If-Range` và phản hồi cho range không hợp lệ.
- Cấu hình async executor, timeout, quotas, metrics và reverse-proxy buffering cho StreamingResponseBody.
- Không trả active content nguy hiểm inline trừ khi sản phẩm yêu cầu và đã có bảo vệ phù hợp; dùng `attachment`, `nosniff`, authorization và origin isolation khi cần.
- Test **status + filename/header + MIME + bytes** và dùng `asyncDispatch` cho streaming trong MockMvc.
- Với file rất lớn hoặc lượng người tải cao, cân nhắc object storage/CDN/presigned URL, immutable versions và kiểm tra toàn vẹn dữ liệu.
- Không để tên file do client điều khiển quyết định đường dẫn đọc file hay viết header thô.
- Thiết kế xử lý lỗi streaming không thể rollback sau response commit.

## Tài liệu chính thức

- [Spring Framework 6.2 — Asynchronous Requests và StreamingResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.2 — HTTP Range Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-range.html)
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework 6.2 — StreamingResponseBody Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/StreamingResponseBody.html)
- [Spring Framework 6.2 — ContentDisposition.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ContentDisposition.Builder.html)
- [Spring Framework — Core Resource interface](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [RFC 9110 — HTTP Semantics (Content-Disposition, Range, caching)](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 6266 — Content-Disposition in HTTP](https://www.rfc-editor.org/rfc/rfc6266.html)
- [OWASP — File Upload Cheat Sheet (liên quan file lưu trữ và download)](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
