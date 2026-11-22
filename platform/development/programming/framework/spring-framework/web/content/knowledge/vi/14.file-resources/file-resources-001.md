# MultipartResolver và cấu hình multipart của Servlet container trong Spring MVC

## 1. Mục tiêu

Khi client gửi form có file (ảnh, tài liệu, CSV...) đến một endpoint Spring MVC, request thường có `Content-Type: multipart/form-data`. Để `@RequestParam MultipartFile` hoặc `@RequestPart` nhận được dữ liệu, không chỉ controller mà cả **Servlet container** và cơ chế **`MultipartResolver`** phải phối hợp đúng.

Sau bài này, bạn có thể:

1. Đọc cấu trúc multipart, phân biệt **HTTP part**, `jakarta.servlet.http.Part`, `MultipartFile` và `MultipartHttpServletRequest`.
2. Giải thích chính xác việc **`DispatcherServlet` nhận diện resolver mang bean name `multipartResolver`** và **Servlet container thực hiện phân tích body**.
3. Cấu hình kích thước, thư mục tạm, ngưỡng ghi đĩa bằng **Servlet multipart config**, không nhầm với phương thức của `StandardServletMultipartResolver`.
4. Dùng `spring.servlet.multipart.*` trên **Spring Boot 3.x**, biết điều gì đã được auto-configured và khi nào cần bean `StandardServletMultipartResolver` tự khai báo.
5. Phân biệt `resolveLazily` và `strictServletCompliance` cùng tác động đến thời điểm phát sinh lỗi và tính portable.
6. Xây dựng ứng dụng Java 17+ có endpoint upload thông thường và upload file kèm JSON part, gọi bằng `curl -F`, kiểm thử với MockMvc.
7. Nhận diện lỗi 400/413/415, giới hạn kích thước, dữ liệu tạm và rủi ro filename giả, path traversal, dung lượng lớn hoặc file độc hại.

**Phiên bản bài học:** Spring Framework **6.x**, Spring Boot **3.x**, Servlet API `jakarta.servlet.*`, Java 17+. Spring Framework 6 đã loại `CommonsMultipartResolver` cũ; triển khai được hướng dẫn ở đây là **`StandardServletMultipartResolver`** dựa trên Servlet `Part`. Ví dụ không thuộc Spring WebFlux (WebFlux dùng API multipart reactive riêng).

## 2. Multipart/form-data là gì?

Một form HTML upload tệp có thể được viết:

~~~html
<form method="post" action="/api/uploads/simple"
      enctype="multipart/form-data">
  <input type="file" name="file">
  <input type="text" name="note">
  <button type="submit">Upload</button>
</form>
~~~

`enctype="multipart/form-data"` là điểm khác biệt so với form URL-encoded thông thường. Body thực tế được chia thành các **part** bằng boundary do client sinh ra:

~~~http
POST /api/uploads/simple HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=demoBoundary

--demoBoundary
Content-Disposition: form-data; name="note"

document
--demoBoundary
Content-Disposition: form-data; name="file"; filename="hello.txt"
Content-Type: text/plain

Hello Spring
--demoBoundary--
~~~

Ví dụ trên để **giải thích cấu trúc wire**, không phải yêu cầu tự gõ boundary bằng tay. Trong request thực, line ending dùng CRLF và phần chứa file có thể là **binary bytes**, không phải text dễ đọc.

Mỗi part có header riêng. `Content-Disposition` thường chứa `name` khớp với field của form; file part có thể mang `filename` do client cung cấp. `Content-Type` của part cho biết loại dữ liệu client tuyên bố, nhưng **không chứng minh file an toàn hoặc đúng MIME**.

**Không tự đặt** header `Content-Type: multipart/form-data` khi dùng `curl -F` hay JavaScript `FormData`: client phải thêm `boundary` phù hợp với body. Đặt Content-Type thủ công mà thiếu boundary là nguyên nhân phổ biến khiến container không parse được request.

## 3. Ai thực sự parse multipart: container hay Spring?

Trong Spring MVC 6.x:

~~~text
HTTP multipart request
        |
        v
Servlet container (Tomcat/Jetty/Undertow ...)
        |
        v
DispatcherServlet
        |
        +-- tìm bean có tên "multipartResolver"
        |          |
        |          v
        |  StandardServletMultipartResolver
        |          |
        |          v
        |  Servlet request.getParts() / Part
        |          |
        |          v
        |  MultipartHttpServletRequest
        |
        v
Handler adapter --> @RequestParam MultipartFile /
                    @RequestPart / Part
        |
        v
Controller --> Response
~~~

**Phân công trách nhiệm:**

- **Servlet container** (ví dụ embedded Tomcat của Boot) cung cấp parsing theo Servlet multipart API. Nó được cấu hình trên **servlet registration** bằng `MultipartConfigElement`, `<multipart-config>` trong `web.xml`, hoặc cơ chế Servlet tương ứng. Đây là nơi đặt **max file size, max request size, temporary storage location, file size threshold**.
- **`StandardServletMultipartResolver`** là adapter/chiến lược của Spring MVC dựa trên `request.getParts()`. Nó nhận diện request phù hợp, yêu cầu parse (ngay hoặc lazy), bao bọc request thành `MultipartHttpServletRequest`, và phối hợp giải phóng tài nguyên.
- **`DispatcherServlet`** sử dụng resolver tìm được theo **bean name cố định `multipartResolver`**. Nó không tự chọn một bean `MultipartResolver` đặt tên tùy ý trong cấu hình MVC thuần.
- **Controller** nhận phần đã xử lý dưới dạng `MultipartFile`, `Part`, dữ liệu form hoặc DTO JSON từ một part phù hợp.

Một resolver của Spring **không thay thế parser của Servlet container**. Nếu không bật multipart parsing ở servlet registration, chỉ thêm `new StandardServletMultipartResolver()` thường vẫn không đủ.

Ngược lại, khi Servlet hỗ trợ `getParts()` nhưng Spring MVC không có resolver như mong đợi, controller dùng `MultipartFile` có thể không bind đúng theo luồng multipart MVC; dùng `Part` trực tiếp là một cơ chế khác dựa trên Servlet. Hãy xác định hướng tích hợp thay vì sửa ngẫu nhiên annotation handler.

## 4. `MultipartResolver` và `StandardServletMultipartResolver`

Giao diện `org.springframework.web.multipart.MultipartResolver` là hợp đồng chiến lược có các method chủ chốt:

| API | Ý nghĩa |
| --- | --- |
| `isMultipart(HttpServletRequest)` | Request có phù hợp tiêu chí multipart của resolver không |
| `resolveMultipart(HttpServletRequest)` | Parse/wrap request thành `MultipartHttpServletRequest` |
| `cleanupMultipart(MultipartHttpServletRequest)` | Dọn tài nguyên tạm sau xử lý khi thích hợp |

`StandardServletMultipartResolver` là implementation theo Servlet Part API trong Spring MVC 6.x. Hai tùy chọn đáng nhớ:

### 4.1. `setResolveLazily(boolean)`

- **Mặc định `false`**: Spring cố gắng parse các part ngay trong giai đoạn `resolveMultipart`. Lỗi multipart do parsing thường xuất hiện sớm, trước khi vào handler.
- **`true`**: trì hoãn việc parse cho tới khi ứng dụng truy cập file/parameter/part. Lỗi kích thước hoặc body hỏng có thể phát sinh **muộn hơn**.

Lưu ý: lazy không có nghĩa container tuyệt đối không đọc request sớm; middleware, filter hoặc code khác có thể truy cập parameters/parts trước, kích hoạt xử lý. Điều thay đổi chính là **thời điểm Spring yêu cầu parse**. Khi debug exception, phải hiểu request lifecycle.

### 4.2. `setStrictServletCompliance(boolean)`

- **Mặc định `false`**: resolver thử xử lý các request có `multipart/*` tùy khả năng parser của container.
- **`true`**: chỉ wrap các request **`multipart/form-data`**, cho phép những multipart subtype khác được xử lý bởi đường custom nếu cần.

Các container không giống nhau ở những media type ngoài `multipart/form-data`. Theo Javadoc Spring, ví dụ Tomcat có thể chấp nhận những request multipart khác mà Jetty không chấp nhận. Dùng `strictServletCompliance=true` khi muốn rõ chuẩn form upload và tính portable cao hơn; nếu ứng dụng có `multipart/mixed` chuyên biệt, phải tự thiết kế đường xử lý thích hợp.

**Đừng hiểu strict=true là tăng độ bảo mật file upload**: nó chỉ thay tiêu chí resolver áp dụng cho media type, không scan virus hay xác thực nội dung file.

### 4.3. Khai báo bean trong MVC không dùng Boot auto-config

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.multipart.MultipartResolver;
import org.springframework.web.multipart.support.StandardServletMultipartResolver;

@Configuration
public class MultipartResolverConfig {

    @Bean(name = "multipartResolver")
    public MultipartResolver multipartResolver() {
        StandardServletMultipartResolver resolver =
                new StandardServletMultipartResolver();
        resolver.setResolveLazily(false);
        resolver.setStrictServletCompliance(true);
        return resolver;
    }
}
~~~

Đây là **class Java hoàn chỉnh** theo Spring Framework 6.x, nhưng muốn upload chạy cần thêm **Servlet multipart config trên DispatcherServlet registration** và cấu hình controller/web context khác. Bean tên `multipartResolver` là điều kiện quan trọng.

**Không nên sao chép bean này vào mọi Spring Boot application**: Boot 3.x thường đã tự đăng ký resolver khi bật multipart và thỏa auto-configuration. Khai báo thêm có thể làm bạn vô tình thay hành vi đã cấu hình bằng properties.

## 5. Servlet container: đặt limit và thư mục tạm ở đâu?

Trong Servlet API Jakarta, `MultipartConfigElement` nhận tham số:

~~~java
new MultipartConfigElement(
        "/var/tmp/my-app-upload", // location
        2L * 1024 * 1024,         // maxFileSize: 2 MiB
        3L * 1024 * 1024,         // maxRequestSize: 3 MiB
        0                         // fileSizeThreshold: ghi tạm lên disk
);
~~~

Đây là **biểu thức Java minh họa**, không phải một file ứng dụng riêng. Các tham số size ở đây là **số byte** trong constructor Servlet, không phải Spring Boot DataSize string.

- **`location`**: thư mục container dùng để lưu các part được ghi ra đĩa/tệp tạm. Thư mục phải tồn tại hoặc được container quản lý theo cách hỗ trợ, writable bởi tiến trình server, đủ dung lượng và được quản trị quyền truy cập.
- **`maxFileSize`**: kích thước tối đa **mỗi file/part** theo parser container (bytes).
- **`maxRequestSize`**: kích thước tối đa **toàn multipart request**, gồm các part và overhead boundary/headers; thường cần lớn hơn giới hạn file đơn.
- **`fileSizeThreshold`**: ngưỡng trước khi các part được container ghi ra disk; ngưỡng 0 có thể khiến container dùng disk rất sớm. Hành vi thực tế tùy container.

**Quan trọng:** Không có API `setMaxUploadSize(...)` tương đương trên `StandardServletMultipartResolver` của Spring 6 để thay giới hạn Servlet registration. Những hướng dẫn cấu hình `CommonsMultipartResolver#setMaxUploadSize` cho Spring cũ **không còn áp dụng** với Framework 6.

### 5.1. Cấu hình Servlet registration bằng Java (không dùng Boot)

Ví dụ minh họa trong một initializer thuần Spring MVC:

~~~java
import jakarta.servlet.MultipartConfigElement;
import jakarta.servlet.ServletRegistration;
import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class AppInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return null;
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[]{MvcConfig.class};
    }

    @Override
    protected String[] getServletMappings() {
        return new String[]{"/"};
    }

    @Override
    protected void customizeRegistration(
            ServletRegistration.Dynamic registration) {

        registration.setMultipartConfig(new MultipartConfigElement(
                "/var/tmp/my-app-upload",
                2L * 1024 * 1024,
                3L * 1024 * 1024,
                0
        ));
    }
}
~~~

**Đây là đoạn minh họa MVC thuần**, không dùng trực tiếp trong project Boot thực hành ở phần 7. Bạn cần tự định nghĩa bean config `MvcConfig` phù hợp (chứa resolver và MVC controllers), bảo đảm directory tồn tại/quyền ghi, cài Servlet container triển khai; không thể biên dịch file riêng nếu chưa có `MvcConfig`.

Tùy kiến trúc, có thể cấu hình `<multipart-config>` ngay trong đăng ký servlet ở `web.xml`. Đối với **Spring Boot embedded Servlet**, cách nên ưu tiên là properties ở phần tiếp theo, tránh song song cấu hình cùng một giới hạn ở nhiều nơi.

## 6. Spring Boot 3.x tự cấu hình những gì?

Với dependency `spring-boot-starter-web` và multipart enabled, Spring Boot có **`MultipartAutoConfiguration`** chịu trách nhiệm tạo `MultipartConfigElement` và `StandardServletMultipartResolver` khi cần, dựa trên `MultipartProperties` (`spring.servlet.multipart.*`). Boot cũng dùng những điều kiện auto-configuration để **không** tạo duplicate bean khi ứng dụng đã có cấu hình riêng tương ứng.

Điểm phân biệt:

| Câu hỏi | Spring MVC thuần | Spring Boot 3.x thường gặp |
| --- | --- | --- |
| Ai thêm bean `multipartResolver`? | Chính bạn khai báo | Boot thường auto-configure |
| Ai bật multipart trên Servlet? | Initializer / `web.xml` | Boot tạo `MultipartConfigElement` |
| Giới hạn upload nằm đâu? | Registration config | `spring.servlet.multipart.max-*` |
| Resolver parse body bằng gì? | Servlet `Part` | Cũng là Servlet `Part` |
| Có nên thêm `@EnableWebMvc` để bật upload? | Chỉ khi cần cấu hình MVC thuần | **Không** cần và có thể làm mất auto-config khác |
| Có cần Commons FileUpload library không? | Không | Không |

### 6.1. Thuộc tính chính trong `application.properties`

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true
~~~

**Giải thích từng dòng:**

- `enabled=true`: cho phép Boot auto-configure multipart handling (mặc định thường bật).
- `max-file-size=2MB`: giới hạn mỗi file khoảng 2 MiB theo cơ chế `DataSize` của Boot (hậu tố đơn vị phải hiểu theo quy tắc Boot, không coi là miligiây hoặc số file).
- `max-request-size=3MB`: giới hạn toàn request; cần tính cả các part text/JSON và phần overhead. Nếu cho phép 2 file mỗi file 2MB, tổng request 3MB **không đủ**.
- `file-size-threshold=0B`: ngưỡng ghi tạm; có thể chọn giá trị khác khi hiểu giới hạn memory/disk.
- `resolve-lazily=false`: parse multipart sớm ở giai đoạn resolver.
- `strict-servlet-compliance=true`: resolver chỉ wrap dạng `multipart/form-data`, tránh khác biệt subtype giữa containers.

Theo tài liệu `MultipartProperties` của Spring Boot 3.5, **mặc định** file size là **1MB**, request size **10MB**, threshold **0**. Đừng nhầm các mặc định này với chính sách sản phẩm; nếu ứng dụng cho phép nhiều file/loại file khác nhau, phải chọn giới hạn hợp lý theo threat model.

### 6.2. Cấu hình thư mục tạm

Có thể thêm:

~~~properties
spring.servlet.multipart.location=/var/tmp/myapp-multipart
~~~

**Không bật dòng này mù quáng trên Windows hoặc máy không có thư mục tương ứng.** Khi không khai báo, Boot/Servlet container thường dùng thư mục tạm mặc định. Với production, nên cấp directory riêng trên volume có quota, quyền tối thiểu, cơ chế dọn rác và giám sát dung lượng.

Giá trị `location` của multipart **không phải** thư mục đích lưu file vĩnh viễn. Đừng coi request đã upload thành công chỉ vì Servlet tạo một temporary file. Muốn lưu lâu dài, ứng dụng phải chủ động validate và lưu bằng cơ chế riêng.

### 6.3. Không nhầm với các size limit khác

Một request lớn có thể bị chặn trước khi tới resolver do:
- Reverse proxy (ví dụ Nginx, API gateway, ingress) có giới hạn body riêng.
- Servlet connector/container có các tham số khác hoặc giới hạn tổng request.
- WAF/bảo mật hệ thống.
- Application validation/business rules sau khi parse.

Do đó, `spring.servlet.multipart.max-file-size=2MB` **không đủ để kết luận status HTTP chính xác** trong mọi triển khai. Response có thể là 413, 400, một lỗi khác, hoặc kết nối bị ngắt trước khi vào Spring tùy tầng từ chối và cách xử lý exception.

## 7. Ứng dụng Spring Boot 3.x chạy được

Bài thực hành có hai endpoint:

- `POST /api/uploads/simple`: nhận một file và ghi chú form.
- `POST /api/uploads/with-json`: nhận file và một **JSON part** theo `@RequestPart`.

Để dễ kiểm tra, controller **không lưu file vĩnh viễn**; nó chỉ đọc metadata để xác nhận body được parse/bind đúng. Điều này tránh giả định file temporary có thể dùng lâu sau request. Bản production cần lưu nội dung thật an toàn sau kiểm tra.

Tạo project Spring Initializr với **Java 17+**, **Spring Boot 3.x**, **Maven**, dependencies **Spring Web** và **Spring Boot Starter Test**; package `com.example.demo`.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/UploadController.java
src/main/resources/application.properties
src/test/java/com/example/demo/UploadControllerTest.java
~~~

### 7.1. `DemoApplication.java`

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

### 7.2. `application.properties`

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true
~~~

Không cần tạo bean `StandardServletMultipartResolver` thủ công khi giữ cấu hình Boot mặc định này.

### 7.3. `UploadController.java`

~~~java
package com.example.demo;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    @PostMapping(
            path = "/simple",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> simple(
            @RequestParam("file") MultipartFile file,
            @RequestParam(name = "note", defaultValue = "") String note) {

        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(new UploadError("EMPTY_FILE"));
        }
        if (note.length() > 100) {
            return ResponseEntity.badRequest()
                    .body(new UploadError("NOTE_TOO_LONG"));
        }

        return ResponseEntity.ok(new UploadReceipt(
                file.getOriginalFilename(), file.getSize(), note));
    }

    @PostMapping(
            path = "/with-json",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> withJson(
            @RequestPart("file") MultipartFile file,
            @RequestPart("metadata") UploadMetadata metadata) {

        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(new UploadError("EMPTY_FILE"));
        }
        if (metadata.label() == null ||
                metadata.label().isBlank() ||
                metadata.label().length() > 100) {
            return ResponseEntity.badRequest()
                    .body(new UploadError("INVALID_LABEL"));
        }

        return ResponseEntity.ok(new UploadReceipt(
                file.getOriginalFilename(),
                file.getSize(),
                metadata.label()));
    }

    public record UploadMetadata(String label) {}
    public record UploadReceipt(String originalName, long size, String note) {}
    public record UploadError(String code) {}
}
~~~

**Giải thích:**

- `@RequestParam("file") MultipartFile` đọc file part theo tên form field. `MultipartFile` cung cấp `isEmpty()`, `getSize()`, `getOriginalFilename()`, `getContentType()`, `getInputStream()`, `transferTo(...)`.
- `@RequestParam("note") String` đọc một form parameter thông thường; trong ví dụ `defaultValue=""` cho phép bỏ ghi chú.
- `@RequestPart("metadata") UploadMetadata` dùng **`HttpMessageConverter`** cho nội dung part, thường là Jackson khi part khai báo `Content-Type: application/json`. Không nhầm JSON part với một field form chứa chuỗi JSON nhưng không có content type thích hợp.
- `@RequestPart("file") MultipartFile` cũng nhận file part; cả `@RequestParam` và `@RequestPart` có vai trò phù hợp cho trường hợp file, còn DTO JSON nên sử dụng `@RequestPart` rõ ràng.
- `file.getOriginalFilename()` do **client cung cấp**, có thể chứa đường dẫn/ký tự đặc biệt và không được tin để tạo disk path. Ở đây trả về JSON **chỉ để quan sát kết quả**, không dùng như tên file lưu vĩnh viễn.
- `file.getContentType()` là dữ liệu từ request; không xác thực bản chất file. Kiểm tra size và label trong ví dụ chỉ là **minh họa**, production cần kiểm soát chặt hơn.
- `file.isEmpty()` là true cho file rỗng/không có nội dung, không phải quy tắc xác định malware. Nếu file được phép rỗng theo nghiệp vụ, điều kiện phải đổi.
- Bài này không tạo database/storage, nên “upload thành công” trong ví dụ có nghĩa **đã parse và đọc metadata**, không phải đã lưu tài nguyên.

### 7.4. Chạy và gọi bằng `curl -F`

Chạy trong thư mục có `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`; nếu máy cài Maven nhưng không có wrapper, dùng `mvn spring-boot:run`.

Tạo file UTF-8 có nội dung `Hello Spring` tên `hello.txt`. Gọi:

~~~bash
curl -i -X POST "http://localhost:8080/api/uploads/simple"   -F "file=@hello.txt;type=text/plain"   -F "note=demo"
~~~

Khi file chứa 12 byte `Hello Spring`, kết quả kỳ vọng **HTTP 200 OK** và body JSON tương đương:

~~~json
{"originalName":"hello.txt","size":12,"note":"demo"}
~~~

Lưu ý: nếu file có newline cuối, BOM, hoặc encoding/bytes khác thì `size` khác 12. Không đưa kích thước của file thực tế vào ví dụ mà không kiểm tra bytes.

Đối với endpoint kèm JSON part:

~~~bash
curl -i -X POST "http://localhost:8080/api/uploads/with-json"   -F "file=@hello.txt;type=text/plain"   -F 'metadata={"label":"report"};type=application/json'
~~~

Kết quả kỳ vọng HTTP 200 với `note="report"` và `size=12` nếu file đúng 12 byte:

~~~json
{"originalName":"hello.txt","size":12,"note":"report"}
~~~

**Không thêm** `-H "Content-Type: multipart/form-data"` bằng tay vì `curl -F` sẽ tự tạo boundary cho đúng body.

Trường hợp file thiếu hoặc part sai tên có thể tạo lỗi argument resolution (thường HTTP 400) trước khi code `file.isEmpty()` chạy. Trường hợp file có tên nhưng body rỗng sẽ đi vào nhánh trả JSON `{"code":"EMPTY_FILE"}` nếu request parse thành công.

### 7.5. Gửi multipart từ browser

~~~javascript
async function sendFile(file, note) {
  const form = new FormData();
  form.append("file", file);
  form.append("note", note);

  const response = await fetch("/api/uploads/simple", {
    method: "POST",
    body: form
  });

  if (!response.ok) {
    throw new Error("Upload failed: " + response.status);
  }
  return await response.json();
}
~~~

Trình duyệt tự tạo boundary khi `body` là `FormData`. Nếu gửi JSON part, bạn có thể làm:

~~~javascript
const form = new FormData();
form.append("file", chosenFile);
form.append(
  "metadata",
  new Blob([JSON.stringify({label: "report"})], {
    type: "application/json"
  })
);

await fetch("/api/uploads/with-json", {
  method: "POST",
  body: form
});
~~~

Đây là đoạn minh họa trong browser nơi `chosenFile` đã lấy từ input file hoặc File API. `Blob` giúp tạo part có media type `application/json`. Không cần serialize toàn bộ `FormData` thành JSON.

## 8. Kiểm thử controller với MockMvc

Tạo file **`src/test/java/com/example/demo/UploadControllerTest.java`**:

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(UploadController.class)
class UploadControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readsFormFileAndNote() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "hello.txt",
                "text/plain",
                "Hello Spring".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/uploads/simple")
                        .file(file)
                        .param("note", "demo"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.originalName").value("hello.txt"))
                .andExpect(jsonPath("$.size").value(12))
                .andExpect(jsonPath("$.note").value("demo"));
    }

    @Test
    void readsJsonPartThroughMessageConverter() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "hello.txt", "text/plain",
                "Hello Spring".getBytes(StandardCharsets.UTF_8));

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "",
                "application/json",
                "{\"label\":\"report\"}".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/uploads/with-json")
                        .file(file)
                        .file(metadata))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.size").value(12))
                .andExpect(jsonPath("$.note").value("report"));
    }

    @Test
    void rejectsEmptyFile() throws Exception {
        MockMultipartFile empty = new MockMultipartFile(
                "file", "empty.txt", "text/plain", new byte[0]);

        mockMvc.perform(multipart("/api/uploads/simple")
                        .file(empty))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("EMPTY_FILE"));
    }

    @Test
    void rejectsOversizedNoteByBusinessRule() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "one.txt", "text/plain", new byte[]{65});

        mockMvc.perform(multipart("/api/uploads/simple")
                        .file(file)
                        .param("note", "x".repeat(101)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("NOTE_TOO_LONG"));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

MockMvc giúp kiểm tra **argument binding, file part, JSON part và controller logic** mà không cần mở một HTTP socket thật. Test `readsJsonPartThroughMessageConverter` chứng minh part `metadata` được parse thành Java record qua Jackson khi media type chính xác.

### 8.1. Tại sao MockMvc không đủ để kiểm tra max-file-size của container?

`MockMultipartFile` và `MockMultipartHttpServletRequest` thường tạo multipart data đã parse trong bộ nhớ test. **Chúng không mô phỏng trọn Servlet connector, disk storage và multipart parser thật của Tomcat/Jetty/Undertow.** Vì vậy một test MockMvc upload 5MB có thể **không** bị giới hạn bởi `spring.servlet.multipart.max-file-size=2MB` dù môi trường production chặn.

Để test kích thước thực, cần:
- Chạy **embedded server trên HTTP socket thật**, ví dụ `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client gửi multipart thật.
- Hoặc chạy server và dùng `curl -F` với file lớn hơn giới hạn, kiểm tra response **và log tại container/proxy**.
- Test riêng request lớn hơn `max-request-size`, nhiều file nhỏ có tổng vượt hạn mức, file zero-byte, part JSON malformed và thiếu boundary.

Không tự assert 413 cứng trong MockMvc controller slice; status của request vượt hạn mức còn phụ thuộc **tầng từ chối và exception handling**.

## 9. Hai giới hạn `max-file-size` và `max-request-size`

| Cấu hình | Đo lường | Ví dụ |
| --- | --- | --- |
| `max-file-size=2MB` | Mỗi file riêng lẻ | File 2,5MB có thể bị từ chối |
| `max-request-size=3MB` | Tổng request multipart | Hai file 1,8MB mỗi file có thể vượt tổng |
| `file-size-threshold=0B` | Ngưỡng memory → disk theo container | Có thể tạo tệp tạm ngay |
| Reverse proxy max body | Toàn HTTP body trước app | Có thể từ chối trước Spring |
| Validation controller | Sau khi parse request | Có thể từ chối file dù dưới parser limit |

**Đặt limit thành nhiều lớp:** reverse proxy, Servlet, nghiệp vụ và storage quota. Chỉ một limit trong controller là quá muộn: container có thể đã đọc/lưu tạm dữ liệu rất lớn trước khi handler chạy. Khi có nhiều file, nhớ giới hạn cả **số lượng file, dung lượng tổng và tổng tài nguyên người dùng có thể tiêu thụ**.

Nếu cần upload nhiều GB, phải thiết kế riêng: streaming, chunk/resumable uploads, storage trực tiếp có URL ký có hạn, quota và anti-malware pipeline. Không chỉ nâng `max-file-size` lên vài GB rồi gọi `MultipartFile.getBytes()` trên toàn file, vì `getBytes()` đưa nội dung vào heap.

## 10. Lazy parsing và cách xử lý exception

### 10.1. Parse eager (mặc định)

`spring.servlet.multipart.resolve-lazily=false` tương ứng `resolver.setResolveLazily(false)`. Khi `DispatcherServlet` nhận request multipart, resolver có thể yêu cầu parse ngay. Lỗi kích thước, boundary thiếu, thư mục tạm lỗi hoặc permission có thể phát sinh **trước lúc controller được gọi**.

Do đó đoạn `try/catch` bên trong handler:

~~~java
@PostMapping("/upload")
public String upload(@RequestParam MultipartFile file) {
    try {
        return "OK";
    } catch (Exception ex) {
        return "ERROR";
    }
}
~~~

Đây là **mẫu minh họa không phù hợp để xử lý mọi lỗi multipart**: nếu parse thất bại trước khi vào method, `catch` này không thể nhận exception. Nên dùng exception handling của MVC nếu exception đi qua `DispatcherServlet`; còn lỗi bị proxy/container chặn trước Spring cần xử lý ở tầng đó.

### 10.2. Parse lazy

`spring.servlet.multipart.resolve-lazily=true` khiến Spring trì hoãn parse tới khi cần truy cập parameter/file. Nó có thể thay đổi vị trí stack trace và nơi `MultipartException` xuất hiện, **không tăng size limit** và không làm parsing chắc chắn thành công.

Cấu hình lazy hữu ích trong một số luồng xử lý đặc biệt, nhưng khó debug hơn nếu nhiều interceptor/filter truy cập request parameters. Đừng bật lazy như cách “sửa lỗi 413”; phải kiểm tra giới hạn thực tế.

### 10.3. `MaxUploadSizeExceededException` và HTTP 413

Trong những trường hợp được Spring MVC bắt và nhận diện dưới dạng `MaxUploadSizeExceededException`, bạn có thể ánh xạ sang **413 Payload Too Large** qua `@RestControllerAdvice`:

~~~java
@RestControllerAdvice
public class UploadExceptionAdvice {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<Map<String, String>> tooLarge(
            MaxUploadSizeExceededException ex) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "FILE_TOO_LARGE"));
    }
}
~~~

**Đây là class minh họa bổ sung, không thuộc bản chạy ở phần 7.** Cần import `org.springframework.web.multipart.MaxUploadSizeExceededException`, `java.util.Map`, `org.springframework.http.HttpStatus`, `ResponseEntity`, `@ExceptionHandler`, `@RestControllerAdvice`. Khi server/Servlet container ném exception khác hoặc proxy từ chối trước MVC, handler này **không bảo đảm** chạy. Cần log an toàn và kiểm thử end-to-end với container thật.

Dùng `413` khi body lớn hơn chính sách có thể được ứng dụng phản hồi được. Đừng dựa vào mọi kích thước vượt hạn mức luôn tạo `MaxUploadSizeExceededException`; một số connector có thể đóng kết nối hoặc phát lỗi trước.

## 11. Thư mục tạm, vòng đời `MultipartFile` và lưu file lâu dài

`MultipartFile` đại diện dữ liệu upload trong **request hiện tại**, có thể được giữ trong memory hoặc file tạm tùy parser và threshold.

Các điểm cốt lõi:
- **Temporary upload storage** không phải kho dữ liệu bền vững. Framework/container có thể cleanup sau khi request kết thúc.
- Không giữ reference `MultipartFile` trong singleton, queue hoặc task bất đồng bộ để đọc ở thời điểm không còn request. Nếu cần tác vụ nền, phải **di chuyển/copy dữ liệu vào storage có kiểm soát trước**, có transaction/cleanup rõ ràng.
- `transferTo(Path/File)` có thể dùng để lưu dữ liệu, nhưng semantics move/copy và đường dẫn tương đối phụ thuộc implementation. Khi cần ổn định, dùng đường dẫn tuyệt đối chuẩn hóa trong vùng storage được phép và thiết kế atomic move phù hợp.
- File được upload chưa chắc là tài nguyên được public. Không phục vụ lại bằng static resource handler khi chưa kiểm soát truy cập và Content-Type/Content-Disposition của response.
- Khi xảy ra exception giữa chừng, lưu file tạm của ứng dụng phải có cleanup và quota; cleanup của resolver đối với request multipart không tự dọn mọi bản copy do ứng dụng tạo.

### 11.1. Không tin filename do client gửi

`file.getOriginalFilename()` có thể chứa `../`, dấu phân tách đường dẫn, ký tự Unicode bất thường hoặc tên trùng. Trên hệ thống thực, đừng viết:

~~~java
// KHÔNG AN TOÀN
Path target = uploadRoot.resolve(file.getOriginalFilename());
file.transferTo(target);
~~~

Đây là **mẫu phản diện** minh họa path traversal/collision/overwrite. Không chỉ xóa chuỗi `../` bằng replace đơn giản rồi coi là an toàn; cần chuẩn hóa path, lựa chọn tên server-side và chính sách lưu rõ.

Phương án tốt hơn thường là:
1. Server sinh **ID ngẫu nhiên không đoán trước**, ví dụ UUID, làm storage key.
2. Nếu giữ extension, lấy extension từ chính sách loại file hợp lệ và **xác định loại file thật** chứ không tin tên/Content-Type của client.
3. Lưu dưới thư mục nằm ngoài public document root, phân quyền tối thiểu, kiểm soát symlink và canonical path.
4. Lưu original display name **là metadata không đáng tin**, escape khi đưa vào HTML hoặc header.
5. Dùng `Content-Disposition: attachment` thích hợp khi download tài liệu không đáng render inline; kết hợp `X-Content-Type-Options: nosniff` và MIME hợp lệ.

### 11.2. Kiểm tra file upload nhiều lớp

- **Kích thước:** giới hạn tại proxy/container trước controller, cộng quota theo user/tenant.
- **Loại file:** extension + MIME do client khai báo chỉ là gợi ý; kiểm tra magic bytes/parser theo loại thực, chặn dạng không mong muốn.
- **Nội dung nguy hiểm:** scanner/antivirus và sandbox khi phù hợp; với ảnh, cân nhắc decode và re-encode để loại bỏ payload không cần thiết.
- **Archive:** phòng zip bomb, path traversal trong archive entry và tài nguyên CPU/memory.
- **Quyền truy cập:** xác thực và phân quyền upload/download, kiểm soát ownership.
- **CSRF:** nếu authentication dùng cookie trên trình duyệt, POST upload thay đổi trạng thái cần CSRF protection phù hợp.
- **Storage:** directory/volume riêng có quota, tên server-side, backup/lifecycle, cleanup.
- **Thông báo lỗi:** không tiết lộ absolute path, storage credential hoặc stack trace trong JSON lỗi.

Việc giải mã body thành công **không** có nghĩa tệp an toàn để lưu hoặc mở. Đây là tầng nghiệp vụ/bảo mật bên trên `MultipartResolver`.

## 12. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Controller nhận file null/missing | Tên part khác `@RequestParam("file")`, thiếu part, sai Content-Type/boundary | Đối chiếu `name`, `curl -F`, header request thực |
| Lỗi multipart parse trước controller | Container chưa được bật multipart hoặc body/part hỏng | Kiểm tra servlet multipart config, logs, cause |
| `MaxUploadSizeExceededException` hoặc 413 | Vượt `max-file-size`, `max-request-size`, limit proxy | So size file và toàn body, đúng tầng từ chối |
| File nhỏ vẫn vượt `max-request-size` | Nhiều part hoặc overhead; tổng lớn hơn limit | Tính toàn request, không chỉ file lớn nhất |
| `@RequestPart` JSON bị 415 | Part `metadata` không có `Content-Type: application/json` hoặc thiếu converter | Dùng `curl -F 'metadata=...;type=application/json'` |
| Multipart vượt qua controller nhưng không còn file sau request | File nằm ở temp storage và đã cleanup | Copy/transfer trước khi request kết thúc |
| Upload thành công ở Tomcat nhưng fail ở Jetty | Multipart subtype/HTTP method mà container parse khác nhau | Cân nhắc `strict-servlet-compliance=true`, test container |
| Thêm resolver bean nhưng vẫn không parse | Chưa có `MultipartConfigElement` trên servlet registration | Cấu hình hai tầng, kiểm tra startup |
| Dùng `setMaxUploadSize` không compile | API của `CommonsMultipartResolver` cũ | Dùng Servlet/Boot multipart properties |
| `@RequestBody` DTO không đọc toàn multipart | `@RequestBody` thích hợp cho body đơn định dạng; JSON là part | Dùng `@RequestPart` cho JSON part |
| `MockMvc` cho phép file vượt size limit | Mocked multipart bypass container parser | Test với HTTP thật trên embedded server |
| Disk đầy hoặc permission denied | Temp upload location không writable/volume thiếu quota | Kiểm tra user chạy server, mount và cleanup |
| 400/413/415 không ổn định giữa môi trường | Proxy/container/exception handlers khác nhau | Đo HTTP + logs tại từng tầng |
| Filename có dấu `../` hoặc tên tuyệt đối | Client kiểm soát `getOriginalFilename()` | Sinh storage key server-side và validate |
| `multipartResolver` không được tìm thấy | Bean sai tên hoặc khác context của `DispatcherServlet` | Kiểm tra bean name chính xác và context |

### Quy trình debug thực tế

1. Xác minh **client** có gửi `multipart/form-data; boundary=...` và body thật sự có part đúng tên.
2. Xác minh **Servlet registration** đã bật multipart, giới hạn file/request và temp location có quyền ghi.
3. Với Spring MVC thuần, xác minh bean **`multipartResolver`**; với Boot xem auto-config và property `spring.servlet.multipart.enabled`.
4. Kiểm tra `resolve-lazily` quyết định thời điểm parse; `strict-servlet-compliance` và container quyết định media subtype.
5. Đọc exception gốc tại **proxy/container** và Spring; không giả định mọi lỗi đều do controller.
6. Kiểm tra đúng `@RequestParam`, `@RequestPart`, media type của JSON part, validation và file handling.
7. Test bằng HTTP thật với file lớn, nhiều file và request form bất thường; không suy kết luận limit từ MockMvc.
8. Bảo đảm dữ liệu được lưu vào storage quản lý nếu ứng dụng cần giữ lâu; đừng dựa vào thư mục tạm.

## 13. Câu hỏi ôn tập

**1. `StandardServletMultipartResolver` có tự thay thế Servlet container multipart parser không?**

Không. Nó dùng `jakarta.servlet.http.Part`/`request.getParts()` của container. Container phải được cấu hình để parse multipart.

**2. Vì sao bean resolver cần tên `multipartResolver` trong Spring MVC thuần?**

Vì `DispatcherServlet` tìm resolver theo bean name quy ước đó. Bean đặt tên khác có thể không được tự động dùng làm multipart strategy.

**3. Muốn giới hạn 2 MiB mỗi file trong Spring Boot 3.x thì dùng phương án nào?**

Đặt `spring.servlet.multipart.max-file-size=2MB`; giới hạn được áp dụng vào Servlet multipart configuration. Không gọi method `setMaxUploadSize` trên `StandardServletMultipartResolver` (không tồn tại).

**4. `resolve-lazily=true` có giải quyết lỗi quá kích thước không?**

Không. Nó thay đổi thời điểm parse/lỗi xuất hiện, không tăng hoặc bỏ giới hạn size của container.

**5. `strict-servlet-compliance=true` xử lý những media type nào?**

Resolver chỉ wrap multipart form upload với `multipart/form-data`. Các subtype multipart khác không được Spring resolver này bao bọc, thuận tiện nếu ứng dụng có xử lý riêng.

**6. Vì sao MockMvc không chứng minh được size limit của Servlet container?**

Vì MockMvc thường cấp multipart object đã dựng sẵn mà không đi qua parser/connector HTTP thật. Muốn kiểm thử size limit cần server thực và HTTP multipart thật.

**7. Tại sao `getOriginalFilename()` không được dùng trực tiếp làm storage path?**

Vì client kiểm soát giá trị đó; có thể gây path traversal, ghi đè, tên không hợp lệ hoặc giả mạo extension. Nên sinh storage key phía server và xác thực loại file.

## 14. Checklist trước khi triển khai

- Phân biệt resolver của **Spring MVC** và parser/limits của **Servlet container**; cấu hình đủ hai tầng khi không dùng Spring Boot auto-config.
- Trên Boot 3.x, ưu tiên `spring.servlet.multipart.*` và chỉ khai báo bean tùy chỉnh nếu có nhu cầu rõ.
- Cấu hình `max-file-size`, `max-request-size`, temp `location` và `file-size-threshold` theo tài nguyên thật, thêm quota/proxy limit.
- Chọn `resolve-lazily` theo vị trí xử lý lỗi mong muốn, `strict-servlet-compliance` theo yêu cầu tính portable và media subtype.
- Dùng `@RequestParam MultipartFile` cho file/form field và `@RequestPart` cho JSON part với content type phù hợp.
- Không tự đặt multipart Content-Type header khi dùng `curl -F` hoặc browser `FormData`.
- Kiểm tra empty file, size, type thực, filename, nội dung nguy hiểm, quyền upload và storage path.
- Lưu file lâu dài trước khi request kết thúc nếu nghiệp vụ yêu cầu; quản trị temp disk và cleanup.
- Test cả controller và HTTP thật qua container/proxy, đặc biệt lỗi upload vượt giới hạn hoặc multipart malformed.
- Không sử dụng ví dụ `CommonsMultipartResolver`/Javax Servlet từ Spring 5 để cấu hình Spring 6/Jakarta.

## Nguồn tham khảo chính thức

- [Spring Framework 6.2 — Multipart Resolver](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework 6.2 — Multipart Forms](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — StandardServletMultipartResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/multipart/support/StandardServletMultipartResolver.html)
- [Spring Framework — MultipartResolver interface](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/multipart/MultipartResolver.html)
- [Spring Boot 3.5 — MultipartProperties Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Framework 6.0 — Release Notes (CommonsMultipartResolver removed)](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes)
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
