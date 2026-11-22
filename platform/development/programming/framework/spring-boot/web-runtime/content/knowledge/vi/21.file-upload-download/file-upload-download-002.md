# MultipartResolver, MultipartFile và cấu hình multipart của Servlet

## 1. Bài toán: nhận một file HTTP không chỉ là đọc request body

Khi trình duyệt hoặc client gửi file lên một ứng dụng **Spring Boot MVC/Servlet**, request thường dùng **Content-Type: multipart/form-data**. Body không còn là một JSON hoặc byte[] đơn lẻ; nó chứa **nhiều phần (part)**, mỗi phần có header và nội dung riêng. Một part có thể là trường văn bản, một part là ảnh hoặc tài liệu được tải lên.

Đường xử lý có những trách nhiệm tách biệt:

- **Servlet container** (Tomcat/Jetty/Undertow tùy ứng dụng) nhận request và cung cấp cơ chế phân tích multipart theo API **jakarta.servlet.http.Part**.
- **MultipartConfigElement** khai báo cho Servlet việc hỗ trợ multipart, giới hạn kích thước và vị trí lưu tạm.
- **MultipartResolver** tích hợp việc phân tích đó với **Spring MVC DispatcherServlet**.
- **StandardServletMultipartResolver** sử dụng multipart parser của Servlet container.
- **MultipartFile** là giao diện ứng dụng dùng để xem metadata và đọc/chuyển nội dung một file part.
- **Controller và tầng lưu trữ** kiểm tra dữ liệu và quyết định lưu bền vững hay từ chối upload.

Hiểu rõ các lớp này giúp xử lý đúng câu hỏi: vì sao file nhỏ upload được nhưng file lớn báo lỗi, vì sao file tạm biến mất khi request xong, vì sao Controller chưa được gọi khi body quá lớn, và vì sao **MultipartFile.getOriginalFilename()** không thể dùng trực tiếp làm đường dẫn đích.

Bài này áp dụng cho **Spring Boot 3.3.x + Spring MVC + Servlet API Jakarta + Java 17+**, đặc biệt khi dùng embedded Tomcat mặc định từ spring-boot-starter-web. **Spring WebFlux** có cơ chế reactive riêng với **FilePart/Part** trong package org.springframework.http.codec.multipart; đừng dùng MultipartResolver của Servlet làm mẫu cho WebFlux.

## 2. Request multipart/form-data được mã hóa ra sao?

Một form gửi trường tên và file có thể có HTML như sau:

~~~html
<form action="/api/uploads" method="post" enctype="multipart/form-data">
  <label>Ghi chú: <input name="note" type="text"></label>
  <label>Tệp: <input name="file" type="file"></label>
  <button type="submit">Upload</button>
</form>
~~~

Trên đường truyền, client tạo một **boundary** để ngăn cách các part. Minh họa rút gọn:

~~~http
POST /api/uploads HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=demoBoundary

--demoBoundary
Content-Disposition: form-data; name="note"

Bản scan tháng 11
--demoBoundary
Content-Disposition: form-data; name="file"; filename="scan.txt"
Content-Type: text/plain

hello upload
--demoBoundary--
~~~

Ví dụ trên nhằm đọc cấu trúc, đã lược bớt chi tiết vận chuyển byte; request thực tuân thủ CRLF đúng quy cách và boundary do client tạo. **Không** gửi header Content-Type thủ công khi dùng tùy chọn **curl -F**: curl tự tạo boundary và body đồng bộ với nhau. Header khai báo multipart nhưng thiếu/sai boundary có thể làm Servlet parser không tách được part.

Một số điểm cần nhớ:

1. **name="file"** là tên trường trong form; nó phải khớp với **@RequestParam("file")** hoặc **@RequestPart("file")**.
2. **filename="scan.txt"** là tên client tự cung cấp. Nó có thể thiếu, giả mạo, chứa đường dẫn, ký tự kỳ lạ hoặc chuỗi khai thác.
3. **Content-Type: text/plain** ở file part cũng do client cung cấp, không xác nhận thực chất nội dung.
4. Một request có thể chứa **nhiều file và nhiều trường**, cùng lúc chịu hạn mức mỗi file và hạn mức tổng request.
5. HTTP multipart không đồng nghĩa file được lưu bền vững. Parser có thể giữ nội dung trong RAM hoặc file tạm, và tầng nghiệp vụ phải chủ động lưu khi cần.

Multipart/form-data không phải giao thức upload theo từng chunk theo nghĩa resumable upload. Một body multipart vẫn có thể được gửi bằng nhiều packet TCP, nhưng việc chia packet không tự cung cấp cơ chế tiếp tục upload từ byte đang dở.

## 3. Chuỗi xử lý: Servlet container → MultipartResolver → MultipartFile

Trong ứng dụng Spring MVC đã bật multipart:

1. Client tạo request với **multipart/form-data** và các part.
2. Container nhận bytes từ socket, giới hạn/đệm dữ liệu theo cấu hình HTTP và Servlet.
3. **DispatcherServlet** tra Bean tên **multipartResolver**; nếu resolver nhận dạng request multipart, Spring yêu cầu giải quyết các part và bọc request thành **MultipartHttpServletRequest**.
4. Với **StandardServletMultipartResolver**, phần phân tích dùng Servlet **request.getParts()** và **Part**; Spring cung cấp **MultipartFile** cho Controller.
5. Spring MVC binding ánh xạ form fields và file parts vào tham số annotated như **@RequestParam**/**@RequestPart**.
6. Controller thực hiện validation, chuyển file sang vị trí lưu trữ bền vững nếu được chấp nhận, sau đó tạo response.
7. Spring/Servlet container dọn những tài nguyên multipart tạm theo vòng đời request; ứng dụng không giữ MultipartFile để đọc lại về sau.

Sơ đồ:

~~~text
Client multipart/form-data
           |
           v
Web server / Servlet container
           | multipart-config: limits, temp location, threshold
           v
DispatcherServlet
           | multipartResolver
           v
StandardServletMultipartResolver
           | Servlet request.getParts() / Part
           v
MultipartHttpServletRequest
           | MultipartFile, form fields
           v
Controller / Service
           | validate -> persist -> response
           v
Cleanup temporary multipart storage
~~~

Đây là mô hình trách nhiệm, không khẳng định parser luôn đọc toàn bộ file ngay tại cùng một mốc: **resolve-lazily** và cách container xử lý có thể làm thời điểm phân tích/lỗi khác nhau.

### 3.1. Vai trò của MultipartResolver

**org.springframework.web.multipart.MultipartResolver** là chiến lược Spring MVC phát hiện và phân tích multipart request. Các phương thức quan trọng gồm:

- **isMultipart(request):** kiểm tra request có thuộc loại multipart mà resolver sẽ xử lý không.
- **resolveMultipart(request):** chuyển HttpServletRequest thành MultipartHttpServletRequest thích hợp.
- **cleanupMultipart(request):** dọn các phần/tài nguyên tạm sau khi xử lý.

**DispatcherServlet** phát hiện resolver theo tên Bean **multipartResolver**. Trong Spring Boot MVC thông thường, auto-configuration chuẩn bị resolver phù hợp. Không cần tự viết Bean mỗi khi xây upload endpoint.

### 3.2. StandardServletMultipartResolver không tự đặt giới hạn file

**StandardServletMultipartResolver** là triển khai sử dụng **jakarta.servlet.http.Part**. Nó **không** tự chứa giá trị max file size hay temp directory để cấu hình trên Bean như một multipart engine độc lập. Các giới hạn thuộc cấu hình Servlet thông qua **MultipartConfigElement**, được Boot tạo từ **spring.servlet.multipart.***.

Điểm dễ nhầm: chỉ đăng ký một StandardServletMultipartResolver mà **không** cấu hình multipart cho Servlet có thể dẫn đến lỗi ở request.getParts() tùy container. Khi dùng Spring Boot starter-web ở cấu hình mặc định, Boot xử lý cả hai phần.

Từ Spring Framework 6, **CommonsMultipartResolver** cũ không còn là resolver tích hợp chuẩn của Spring MVC. Các ví dụ cũ dùng dependency Apache Commons FileUpload và CommonsMultipartResolver có thể không áp dụng cho Spring Boot 3.x; ưu tiên resolver dựa trên Servlet Part.

### 3.3. resolve-lazily thay đổi thời điểm xuất hiện lỗi

- **resolve-lazily: false** (mặc định): Spring cố gắng phân tích part khi giải quyết multipart request; lỗi malformed multipart/quá giới hạn có thể xảy ra trước khi Controller chạy.
- **resolve-lazily: true:** trì hoãn phân tích tới lúc code truy cập file hoặc multipart parameter; lỗi có thể xuất hiện muộn hơn.

Lazy parsing **không** loại bỏ giới hạn kích thước và không biến parser thành streaming upload end-to-end. Nó cũng không bảo đảm Controller luôn được gọi trước mọi lỗi: reverse proxy/connector còn có thể chặn request từ trước.

### 3.4. strict-servlet-compliance và khả năng di động giữa container

StandardServletMultipartResolver mặc định có thể cố xử lý loại Content-Type bắt đầu bằng **multipart/** rộng hơn multipart/form-data, phụ thuộc container. Một số container xử lý multipart/mixed khác với Tomcat. Khi đặt **strict-servlet-compliance: true**, resolver chỉ áp dụng cho **multipart/form-data**, giúp nhất quán hơn với Servlet multipart forms; các loại multipart khác có thể được phần code chuyên biệt xử lý.

Không tự coi request multipart/mixed được hỗ trợ đồng nhất giữa mọi Servlet container nếu chưa kiểm thử.

## 4. MultipartFile: dữ liệu, metadata và vòng đời

**org.springframework.web.multipart.MultipartFile** đại diện cho file part đã nhận ở một request. Các API thiết yếu:

| API | Ý nghĩa | Rủi ro/lưu ý |
| --- | --- | --- |
| getName() | Tên trường multipart, ví dụ file | Khác tên file gốc |
| getOriginalFilename() | Tên file client gửi; có thể null | Không tin cậy; tránh dùng làm Path đích |
| getContentType() | Media type do client khai báo; có thể null | Không đủ để xác thực định dạng file |
| getSize() | Kích thước part theo byte | Có thể là 0; còn phải có hạn mức server |
| isEmpty() | Không có file hoặc file không có nội dung | Cần quy tắc nghiệp vụ cho file rỗng |
| getBytes() | Đọc toàn bộ bytes vào byte[] | Tốn heap theo kích thước file; không phù hợp file lớn |
| getInputStream() | Mở stream để đọc nội dung | Đóng bằng try-with-resources; thích hợp copy/stream |
| transferTo(File) | Chuyển file vào đích, có thể move/copy tùy provider | Dùng đích tuyệt đối, kiểm tra path và chỉ gọi một lần |
| transferTo(Path) | Lưu vào Path qua giao diện Spring | Trong implementation chuẩn có thể copy stream; không giả định thao tác move giống File |

Lưu trữ của MultipartFile có thể ở **memory** hoặc **file tạm**. Sau khi request kết thúc, hệ thống có quyền dọn dữ liệu tạm. Vì vậy:

- **Không** đặt MultipartFile vào session hoặc singleton để lần sau đọc.
- **Không** giao MultipartFile cho background job thực thi sau khi HTTP request đã kết thúc rồi hy vọng temp file còn tồn tại.
- Nếu phải xử lý async sau response, hãy **lưu nội dung vào nơi bền vững trước**, đưa ID/path/metadata đáng tin cậy cho job queue.
- Nếu cần đọc nhiều lần, biết rõ implementation và vòng đời; mặc định nên thiết kế **một lượt đọc/chuyển** có kiểm soát.

**MultipartFile** là dữ liệu nhận từ client, không phải chứng cứ rằng file an toàn. Kiểm tra nghiệp vụ và an ninh phải diễn ra trước khi mở công khai hoặc xử lý bằng thư viện parser phức tạp.

### 4.1. Vì sao getBytes() nguy hiểm với file lớn?

Ví dụ upload file 20 MiB rồi gọi **getBytes()** tạo một byte[] kích thước xấp xỉ 20 MiB, có thể thêm bản sao của buffer/parser. Nếu 100 request upload đồng thời, heap có thể tăng rất mạnh. Đọc stream bằng **getInputStream()** và **Files.copy(...)** giảm nhu cầu giữ cả file trong byte[] của ứng dụng, dù Servlet container có thể đã spool dữ liệu vào file tạm.

Nhấn mạnh: ứng dụng đọc bằng stream **không đồng nghĩa** toàn bộ luồng HTTP được xử lý theo kiểu reactive/non-blocking. Spring MVC trên Servlet là mô hình khác WebFlux.

### 4.2. transferTo(...) không phải một hành động vô hại có thể gọi lặp

**transferTo(File)** có thể di chuyển file tạm đến destination, copy từ memory hoặc ghi đè destination tùy implementation. Nếu resource đã được move, lần thứ hai có thể thất bại. Các đường đích tương đối có thể được diễn giải theo thư mục tạm của Servlet container. Vì vậy:

- Chuẩn hóa và chọn **absolute destination** do server kiểm soát.
- Không dùng getOriginalFilename() trực tiếp làm đích.
- Gọi transferTo **một lần** như một thao tác lưu có chủ đích.
- Với nhu cầu kiểm soát tránh overwrite và cách ghi, **getInputStream() + Files.copy(...)** thường rõ ràng hơn.
- Nếu ghi file thất bại, cần loại bỏ file chưa hoàn chỉnh và trả lỗi phù hợp.

## 5. Cấu hình Servlet multipart trong Spring Boot

### 5.1. Các property quan trọng

Với Spring Boot 3.3, nhóm property chính là **spring.servlet.multipart**:

| Property | Mặc định tham khảo Boot 3.3 | Tác dụng |
| --- | --- | --- |
| enabled | true | Bật hỗ trợ multipart auto-configuration |
| max-file-size | 1MB | Giới hạn kích thước mỗi file part |
| max-request-size | 10MB | Giới hạn tổng kích thước multipart request |
| file-size-threshold | 0B | Ngưỡng dữ liệu file trước khi ghi ra disk theo container |
| location | Không cấu hình; dùng vị trí tạm phù hợp | Nơi container lưu dữ liệu multipart tạm |
| resolve-lazily | false | Đọc part ngay hay khi truy cập |
| strict-servlet-compliance | false | Chỉ nhận dạng multipart/form-data qua resolver khi bật true |

Lưu ý: **max-file-size** và **max-request-size** là hai hạn mức khác nhau. Ví dụ một request gửi 3 file, mỗi file 900 KiB: tất cả file đều dưới 1MB, nhưng tổng request gồm các part, headers và boundary; vẫn có thể vượt một **max-request-size** được đặt thấp hơn.

Giới hạn mặc định là đặc điểm của Spring Boot 3.3, không phải hợp đồng của toàn bộ Servlet API hoặc mọi phiên bản Boot. Kiểm tra property metadata của phiên bản ứng dụng thực tế khi nâng cấp.

### 5.2. application.yml minh họa

~~~yaml
server:
  port: 8080

spring:
  servlet:
    multipart:
      enabled: true
      max-file-size: 2MB
      max-request-size: 3MB
      file-size-threshold: 0B
      resolve-lazily: false
      strict-servlet-compliance: true

demo:
  upload-directory: ./runtime-uploads
~~~

Ý nghĩa:

- Mỗi file part phải nằm trong giới hạn **2MB**.
- Toàn multipart request, gồm file và các field/overhead, phải nằm trong giới hạn **3MB**.
- Ngưỡng **0B** khiến cơ chế multipart Servlet hướng về lưu tạm trên disk ngay từ ngưỡng thấp; chi tiết cấp phát vẫn phụ thuộc container.
- **strict-servlet-compliance: true** chỉ để minh họa trường hợp chỉ muốn xử lý multipart/form-data đúng phạm vi form.
- **demo.upload-directory** là property tự định nghĩa của ứng dụng mẫu cho **nơi lưu bền vững**, hoàn toàn khác **spring.servlet.multipart.location** dành cho dữ liệu tạm. Không nhầm hai đường dẫn này.

Không thiết lập **location** trong ví dụ để container dùng thư mục tạm phù hợp. Nếu cấu hình location, hãy dùng directory tồn tại và writable trong môi trường deploy, với dung lượng/permission đáp ứng peak upload. Chỉ tăng hạn mức file khi đã tính ngân sách disk/RAM/network và bảo mật.

### 5.3. Spring Boot tạo cấu hình Servlet như thế nào?

Trong môi trường MVC thông thường, **MultipartAutoConfiguration** dựa vào MultipartProperties để cung cấp **MultipartConfigElement** và **StandardServletMultipartResolver** khi điều kiện phù hợp và chưa có cấu hình thay thế. MultipartConfigElement được gắn vào Servlet registration để container có thông tin file size/request size/location/threshold. Resolver có Bean tên multipartResolver để DispatcherServlet nhận ra.

Đây là **hai lớp phối hợp**, không phải hai thư viện parser cạnh tranh nhau. Khi bạn tự tùy biến Servlet registration, cần bảo đảm multipart-config vẫn được gắn đúng Servlet nhận upload. Khi tự khai báo resolver, cần kiểm tra cấu hình còn phù hợp với MultipartConfigElement và có tên Bean đúng.

Nếu bạn tắt **spring.servlet.multipart.enabled**, Spring Boot sẽ không còn tự chuẩn bị multipart theo cách mặc định đó. Không nên tắt chỉ vì muốn upload lớn hơn; hãy sửa giới hạn thay vì loại bỏ toàn bộ cơ chế rồi phụ thuộc cấu hình tình cờ có sẵn.

### 5.4. Cấu hình tại reverse proxy và web server cũng quan trọng

Giới hạn trong application.yml chưa phải giới hạn đầu tiên client gặp. Nginx/Ingress/API gateway, load balancer, WAF và connector có thể có **body size limit**, **timeout**, **max header size** và cách xử lý kết nối khác. Nếu proxy chặn request quá lớn, Controller và @ControllerAdvice của ứng dụng **không bao giờ nhận được request** đó.

Tương tự, storage disk tạm đầy hoặc hết inode có thể gây lỗi upload dù kích thước dưới hạn mức. Phải đo và cấu hình cả đường nhận upload, không chỉ riêng Spring property.

## 6. Khi nào dùng @RequestParam, @RequestPart hay Servlet Part?

### 6.1. Một file đơn và form field

~~~java
@PostMapping(
        path = "/forms",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> handle(
        @RequestParam("title") String title,
        @RequestParam("file") MultipartFile file
) {
    // Kiểm tra title, file rồi lưu.
    return ResponseEntity.accepted().build();
}
~~~

Đây là **fragment trong Controller** đã import các annotation/type liên quan, chưa phải chương trình độc lập. Với upload thông thường **@RequestParam("file") MultipartFile** là cách rõ ràng và phổ biến. Tên **file** phải trùng name của multipart part.

### 6.2. Nhiều file cùng field name

~~~java
@PostMapping(
        path = "/batch",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> batch(
        @RequestParam("files") List<MultipartFile> files
) {
    // Kiểm tra số file, từng file, tổng dung lượng, rồi lưu.
    return ResponseEntity.accepted().build();
}
~~~

Client gửi nhiều part **name="files"**, hoặc form field multiple tương ứng. **max-file-size** áp cho từng file; **max-request-size** áp tổng request. Ngoài ra cần **giới hạn số lượng file** để tránh một request có hàng nghìn part bé gây overhead; giới hạn này phụ thuộc policy/container và validation của ứng dụng.

### 6.3. File kèm metadata JSON

~~~java
public record UploadMetadata(String title, String category) {}

@PostMapping(
        path = "/with-metadata",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> uploadWithMetadata(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") MultipartFile file
) {
    // JSON part được message converter chuyển thành UploadMetadata.
    return ResponseEntity.accepted().build();
}
~~~

Đây là **fragment**: record cần đặt ở vị trí Java hợp lệ, ví dụ một nested record hoặc file riêng, và cần có Controller, imports và Jackson/message converter phù hợp. Với **@RequestPart**, các header của part (đặc biệt **Content-Type: application/json**) giúp converter giải mã metadata thành object. Nếu client gửi JSON như text/plain, có thể nhận 415/400 tùy cấu hình; không phải cứ tên metadata đúng là Spring tự đoán JSON.

**@RequestBody** phù hợp khi toàn bộ request body là một JSON hoặc nội dung duy nhất, không phải cách nhận file part riêng lẻ của multipart/form-data.

### 6.4. Servlet Part và MultipartHttpServletRequest

Có thể nhận **jakarta.servlet.http.Part** trực tiếp qua Servlet API, hoặc dùng MultipartHttpServletRequest để truy cập các part/parameter sau khi resolver xử lý. API Part có getInputStream(), getSubmittedFileName(), getSize(), write(...) và delete(); nó gần với container hơn. MultipartFile là facade Spring tiện lợi cho Controller/service. Chọn **một mô hình rõ ràng** và kiểm thử với container thực.

**Không nhầm** javax.servlet.http.Part của tài liệu Java EE cũ với **jakarta.servlet.http.Part** của Spring Boot 3.x; Boot 3 dùng namespace Jakarta.

## 7. Ứng dụng Java 17+ đầy đủ: nhận file rồi lưu bên ngoài JAR

Ví dụ dưới đây là một dự án Maven Spring Boot 3.3.13 + Spring MVC. Mục tiêu:
- Nhận **một file** multipart/form-data.
- Chặn file rỗng và áp dụng giới hạn qua Servlet multipart config.
- Không sử dụng filename của client làm đường dẫn lưu.
- Copy qua InputStream vào **thư mục ngoài classpath** với tên do server tạo.
- Trả về metadata nhỏ (tên lưu và số byte) mà không tự public hóa file.
- Minh họa ánh xạ lỗi vượt giới hạn về HTTP 413 tại tầng MVC khi exception tới được Spring.

**Đây là demo kỹ thuật, không phải dịch vụ upload tài liệu riêng tư hoàn thiện**: production còn cần xác thực, kiểm tra nội dung, quét file, quota, kiểm toán và kho lưu trữ bền vững.

### 7.1. Cấu trúc

~~~text
multipart-servlet-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/upload/
    │   └── UploadDemoApplication.java
    └── resources/
        └── application.yml
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>multipart-servlet-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

spring:
  servlet:
    multipart:
      enabled: true
      max-file-size: 2MB
      max-request-size: 3MB
      file-size-threshold: 0B
      resolve-lazily: false
      strict-servlet-compliance: true

demo:
  upload-directory: ./runtime-uploads
~~~

Đường dẫn **./runtime-uploads** được resolve tương đối với **working directory của JVM**, không phải thư mục chứa JAR. Ví dụ dùng nó để thử local. Production nên truyền đường dẫn tuyệt đối tới volume hoặc object-storage abstraction phù hợp.

**src/main/java/com/example/upload/UploadDemoApplication.java**:

~~~java
package com.example.upload;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class UploadDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadDemoApplication.class, args);
    }
}

@RestController
class UploadController {
    private final Path root;

    UploadController(@Value("${demo.upload-directory}") String configuredPath)
            throws IOException {
        root = Path.of(configuredPath).toAbsolutePath().normalize();
        Files.createDirectories(root);
    }

    @PostMapping(
            path = "/api/uploads",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    ResponseEntity<UploadReceipt> upload(
            @RequestParam("file") MultipartFile file
    ) throws IOException {
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "File must not be empty"
            );
        }

        String generatedName = UUID.randomUUID() + ".bin";
        Path destination = root.resolve(generatedName);

        try (InputStream input = file.getInputStream()) {
            Files.copy(input, destination);
        } catch (IOException error) {
            Files.deleteIfExists(destination);
            throw error;
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new UploadReceipt(
                        generatedName,
                        file.getSize()
                ));
    }

    public record UploadReceipt(String storedName, long sizeBytes) {}
}

@RestControllerAdvice
class UploadExceptionAdvice {
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<Map<String, String>> tooLarge() {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "multipart_too_large"));
    }
}
~~~

### 7.2. Phân tích từng lựa chọn trong mã

- **@RequestParam("file") MultipartFile:** Spring MVC bind đúng file part tên file, dựa trên multipart resolver.
- **isEmpty():** kiểm tra trường hợp không có nội dung hoặc file rỗng. Nếu client không gửi part bắt buộc, Spring có thể phát lỗi parameter/part missing trước khi vào method.
- **UUID + .bin:** tên lưu do server tạo; không đưa getOriginalFilename vào đường dẫn, tránh path traversal và ghi đè tên do client chọn. Đuôi .bin không xác thực định dạng file; chỉ giúp demo không dựa vào extension của client.
- **Path.toAbsolutePath().normalize():** làm rõ storage root tại startup. Folder là **private directory**, không nằm trong classpath:/static và không được WebMvcConfigurer public hóa.
- **Files.createDirectories:** tạo nơi lưu bền vững ở lúc khởi tạo Bean; nếu thiếu quyền thì startup thất bại thay vì âm thầm lưu chỗ khác.
- **getInputStream() + Files.copy:** copy nội dung mà code Controller không tạo một mảng byte[] lớn. Files.copy không mặc định ghi đè khi destination đã tồn tại; với tên UUID, nguy cơ trùng cực thấp, nhưng production vẫn phải thiết kế collision/idempotency.
- **try-with-resources:** đóng luồng đọc MultipartFile; nếu có IOException thì cố loại bỏ file đích chưa hoàn chỉnh.
- **ResponseEntity 201:** chỉ trả sau khi copy thành công; điều đó **chưa** chứng minh dữ liệu đã được đồng bộ bền vững tới mọi ổ đĩa/replica hay đã quét an toàn.
- **MaxUploadSizeExceededException:** khi exception xuất hiện trong MVC, advice có thể trả HTTP 413. Container/proxy có thể chặn trước MVC hoặc làm kết nối bị ngắt theo cách khác, nên không khẳng định mọi request quá lớn đều chắc chắn nhận JSON 413 từ advice.
- **Không có endpoint download:** một tên file trong JSON không tự làm nội dung upload public. Sau này nếu thêm download, phải có kiểm tra authorization, Content-Disposition và chính sách storage.

Cần phân biệt hai vị trí: phần **file tạm** được Servlet tạo theo spring.servlet.multipart.location và threshold; phần **file bền vững** tại demo.upload-directory do code ứng dụng quyết định. Sau khi copy, file lưu được quản lý độc lập với vòng đời request. Spring không tự dọn file bền vững do Controller tạo.

### 7.3. Chạy local và kiểm tra bằng curl

Tại thư mục **multipart-servlet-demo**, yêu cầu JDK 17+, Maven và cổng 8080 chưa bị chiếm:

~~~bash
mvn package
java -jar target/multipart-servlet-demo-1.0.0.jar
~~~

Tạo **sample.txt** chứa đúng 12 byte ASCII **hello upload**, không có newline. Trên Linux/macOS:

~~~bash
printf 'hello upload' > sample.txt
~~~

Trên Windows PowerShell 5.1:

~~~powershell
[System.IO.File]::WriteAllText(
  "sample.txt",
  "hello upload",
  [System.Text.Encoding]::ASCII
)
~~~

Gửi multipart bằng curl (nếu trên PowerShell, dùng **curl.exe**):

~~~bash
curl -i -F "file=@sample.txt;type=text/plain" http://localhost:8080/api/uploads
~~~

Ở ứng dụng mẫu chưa bật Spring Security, request hợp lệ và lưu thành công sẽ trả **HTTP 201 Created** và JSON có hai trường **storedName** (một UUID ngẫu nhiên kèm .bin) và **sizeBytes** là **12**. Giá trị storedName thay đổi mỗi lần gọi, vì vậy không thể ghi một chuỗi stdout cố định cho mọi lượt thử.

Kiểm tra thư mục **runtime-uploads** trong working directory của tiến trình đang chạy. Bạn sẽ thấy file tên ngẫu nhiên với **12 byte** nội dung. Việc có file ở đây xác nhận ứng dụng đã copy; đây **không** phải file tạm của Servlet.

Thử gửi thiếu file:

~~~bash
curl -i -X POST http://localhost:8080/api/uploads
~~~

Request này không có multipart/form-data part tên file; nó có thể bị từ chối do **Content-Type không phù hợp (415)** hoặc lỗi missing part, tùy chính xác headers/client. Muốn kiểm tra trường hợp multipart có file rỗng, tạo file rỗng rồi gửi bằng **curl -F "file=@empty.txt"**; code kiểm tra isEmpty() sẽ trả **400 Bad Request** khi resolver đã bind file thành công.

Thử body vượt giới hạn: tạo một file **lớn hơn 2 MB** rồi gửi bằng curl -F; hạn mức max-file-size sẽ bị áp tại Servlet layer. Khi lỗi đến được Spring MVC advice, có thể trả **413 multipart_too_large**. Nếu proxy hoặc Tomcat từ chối/đóng kết nối sớm, phía client có thể quan sát lỗi khác. Chỉ nâng giới hạn khi đã xác định chính xác tầng đang chặn và ngân sách tài nguyên.

### 7.4. Thử tổng request và số file

Dù ví dụ Controller nhận một file, cấu hình vẫn giới hạn **tổng multipart request**. Khi phát triển API nhiều file, thử trường hợp mỗi file dưới 2MB nhưng tổng vượt 3MB, hoặc nhiều trường text lớn làm vượt max-request-size. Cả hai giới hạn đều cần kiểm tra ở container thực.

Trên local, đổi **spring.servlet.multipart.max-file-size** mà không restart ứng dụng không đảm bảo config mới được nạp; các giới hạn được gắn vào Servlet registration khi khởi động. Muốn đổi, cập nhật cấu hình và khởi động/deploy lại phù hợp.

## 8. Khi cần đăng ký resolver hoặc Servlet multipart config thủ công

Khi dùng Spring Boot starter-web mặc định, thường **không cần** khai báo thủ công. Nhưng nếu tạo DispatcherServlet riêng, thiết lập ServletRegistrationBean tùy biến hoặc dùng Spring MVC ngoài Boot, phải bảo đảm hai thành phần:

1. **Servlet registration có multipart-config** (ví dụ MultipartConfigElement với temp location và limits).
2. **DispatcherServlet có resolver tên multipartResolver** hoặc cơ chế binding Part tương ứng.

Ví dụ **chỉ để minh họa** khai báo resolver tùy biến trong một lớp @Configuration; nếu thêm vào Boot, cần hiểu cơ chế auto-configuration backs off và đảm bảo thuộc tính Servlet vẫn được áp dụng:

~~~java
@Bean(name = "multipartResolver")
StandardServletMultipartResolver multipartResolver() {
    StandardServletMultipartResolver resolver =
            new StandardServletMultipartResolver();
    resolver.setResolveLazily(false);
    resolver.setStrictServletCompliance(true);
    return resolver;
}
~~~

Đoạn này là **fragment**, cần import @Bean, StandardServletMultipartResolver và đặt trong lớp cấu hình. Nó không thiết lập max-file-size, max-request-size hoặc vị trí temp. Khi chỉ muốn điều chỉnh lazy/strict trong Spring Boot 3.3, **ưu tiên property** thay vì viết Bean trùng trách nhiệm.

Cấu hình thủ công cho Servlet registration ngoài Boot có thể sử dụng **jakarta.servlet.MultipartConfigElement**, ví dụ:

~~~java
registration.setMultipartConfig(
        new MultipartConfigElement(
                "/srv/myapp/upload-tmp",
                2L * 1024 * 1024,
                3L * 1024 * 1024,
                0
        )
);
~~~

Đây cũng là **fragment** cho một ServletRegistration.Dynamic hợp lệ, không phải chương trình độc lập. Đường dẫn temp phải tồn tại/writable theo yêu cầu container. Trong ứng dụng Boot thông thường, không áp dụng lại đoạn này cùng cấu hình properties một cách tùy tiện; có thể gây bất nhất.

## 9. Upload an toàn: dữ liệu client không được biến thành đường dẫn tùy ý

### 9.1. Không tin getOriginalFilename()

Client có thể gửi tên như một đường dẫn có thành phần **../**, đường dẫn tuyệt đối, ký tự Unicode gây nhầm lẫn, hoặc chuỗi trông như tên file hợp lệ nhưng thực chất trỏ vị trí khác. Đoạn sau nguy hiểm:

~~~java
// SAI: chỉ là minh họa anti-pattern.
Path target = Path.of(uploadRoot, file.getOriginalFilename());
file.transferTo(target);
~~~

Nó có thể cho phép ghi ra ngoài root, ghi đè file cũ hoặc gây lỗi hệ thống. Ngay cả dùng Path.getFileName() để lấy basename vẫn chưa đủ: cần chính sách tên, độ dài, loại nội dung, quyền và đích lưu. Khuyến nghị dùng **ID phía server** làm tên lưu, lưu original filename dưới dạng metadata đã giới hạn/escape nếu có nhu cầu hiển thị.

### 9.2. Content-Type và extension là thông tin khai báo

Một file tải lên có thể ghi **image/png** nhưng chứa HTML, mã nhị phân hoặc nội dung độc hại. Validation cần dựa trên **nội dung thực**, định dạng cho phép, kích thước, độ sâu nén (zip bomb), và các kiểm tra chuyên ngành. Nếu cho upload ảnh, có thể decode/re-encode qua thư viện xử lý ảnh an toàn thay vì lưu và phục vụ nguyên xi mọi byte gửi lên. Quét malware khi phù hợp với rủi ro và cơ chế vận hành.

Đừng cho trình duyệt thực thi file do người dùng tải lên như HTML/SVG/script dưới origin nhạy cảm nếu không có chính sách bảo vệ. Nếu phải cung cấp download, dùng Authorization và Content-Disposition attachment khi thích hợp, Content-Type được quyết định an toàn, X-Content-Type-Options và các header bảo vệ liên quan.

### 9.3. Không trộn nơi lưu upload với static public

Thư mục **src/main/resources/static/** dành cho asset đóng gói theo phiên bản code; đừng lưu file upload vào đó. Khi chạy executable JAR, resource được đóng gói không phải một thư mục disk writable thông thường. Nếu cấu hình **spring.web.resources.static-locations** hoặc resource handler trỏ trực tiếp vào directory upload, bạn có thể vô tình biến mọi file upload thành public.

Trong ví dụ, **runtime-uploads** nằm ngoài classpath, không có mapping static. Một API download sau này phải lấy ID từ DB hoặc metadata tin cậy, xác thực chủ file và resolve path trong root an toàn. Với production nhiều replica, nên dùng object storage/PVC chia sẻ hoặc storage service tùy yêu cầu, không mặc định tất cả Pod nhìn thấy một directory.

### 9.4. Giới hạn nhiều tầng để chống lạm dụng

Bên cạnh max-file-size và max-request-size, cân nhắc:

- Số file/part tối đa trong một request và số request đồng thời.
- Quota theo người dùng/tenant, token bucket và rate limit.
- Timeout nhận body ở proxy/server; tránh client gửi cực chậm giữ connection lâu.
- Phân vùng temp và storage chính; giám sát bytes, inode, quyền, cleanup.
- Giới hạn kích thước file **sau giải nén/giải mã** nếu xử lý archive/media.
- Cơ chế kiểm soát file trùng, ID/authorization, retention và xóa dữ liệu theo chính sách.

Không nên đặt giá trị **-1** để bỏ hoàn toàn giới hạn chỉ nhằm khắc phục lỗi “file quá lớn” trong quá trình thử nghiệm; cấu hình cần phù hợp ngân sách tài nguyên và tình huống nghiệp vụ đã xác định.

## 10. Vòng đời temp file, cleanup và chuyển sang xử lý nền

### 10.1. Multipart temp storage không phải database

Nếu container lưu part lớn ra temp directory, dữ liệu đó thuộc **request handling lifecycle**. Khi request hoàn tất, multipart resolver/container thực hiện cleanup tương ứng. Bạn không nên giữ đường dẫn temp hoặc đối tượng MultipartFile như một tài liệu đã lưu. Temp directory cần đủ dung lượng khi nhiều upload diễn ra đồng thời, nhưng nội dung ở đó không nên được coi là bền vững.

Thư mục tạm có thể dùng disk trong container; khi filesystem đầy, upload thất bại dù heap còn dư. Ngược lại, nếu threshold cho phép giữ nhiều file nhỏ trong memory, rất nhiều request đồng thời có thể tăng áp lực heap. Chọn threshold/location dựa trên phép đo và khả năng filesystem, không chỉ dựa trên tốc độ tối ưu của một request.

### 10.2. Async processing sau khi HTTP đã trả lời

Sai lầm:

~~~java
// SAI nếu tác vụ chạy sau request nhưng giữ MultipartFile của request.
jobQueue.submit(() -> parseLater(file.getInputStream()));
return ResponseEntity.accepted().build();
~~~

Không những fragment trên thiếu xử lý IOException và return type phù hợp, mà ý tưởng chính là sai: file tạm có thể bị dọn sau request, và luồng đọc chưa chắc còn hợp lệ.

Cách đúng về kiến trúc: **lưu part bền vững trước**, ghi metadata/ID và gửi message/job chứa **ID hoặc đường dẫn tài nguyên bền vững**, không chuyển MultipartFile cho worker. Nếu upload cần antivirus hoặc chuyển mã lâu, cân nhắc trạng thái **PENDING_SCAN**, lưu ở khu vực quarantine, và chỉ công bố sau validation/scan thành công.

### 10.3. Lưu file an toàn hơn trong hệ thống thật

Thực hành thông thường:
1. Ghi upload tới **file tạm của riêng ứng dụng** trong khu vực kiểm soát, không phải static public.
2. Áp validation, scanning, checksum, quota và metadata.
3. Khi đạt điều kiện, phát hành tới nơi lưu chính bằng bước chuyển đổi có kiểm soát (rename/move nguyên tử khi filesystem cho phép, hoặc commit object storage).
4. Ghi metadata và kết quả về DB; dọn file bị từ chối hoặc file dở dang.
5. Có job dọn orphan/temp/đã hết hạn nếu tiến trình chết giữa chừng.

Ví dụ runnable ở phần 7 copy thẳng vào tên ngẫu nhiên cho đơn giản. Đó là minh họa API multipart và không thay thế quy trình quarantine/commit ở production.

## 11. Lỗi kích thước, lỗi parse và HTTP response

Một số triệu chứng thường gặp:

| Triệu chứng | Có thể phát sinh ở tầng nào? | Cách kiểm tra |
| --- | --- | --- |
| HTTP 413 trước khi vào Controller | Proxy, ingress, Servlet parser, Spring MVC exception handling | Xem access log của proxy/container, property size limits, test trực tiếp vào app |
| MaxUploadSizeExceededException | Spring MVC/Spring multipart processing | Kiểm tra cả max-file-size và max-request-size, MultipartConfigElement |
| Request multipart malformed / missing boundary | Client và parser Servlet | Kiểm tra Content-Type, boundary thực tế, client dùng curl -F đúng |
| MissingServletRequestPartException | Request không có part được yêu cầu | Đối chiếu name file với @RequestParam/@RequestPart |
| HttpMediaTypeNotSupportedException/415 | Endpoint consumes khác Content-Type của request | Dùng multipart/form-data, không gửi JSON thuần |
| getInputStream() hoặc Files.copy ném IOException | Storage/temp/permission/disk | Kiểm tra mount, quyền, dung lượng và đường dẫn đích |
| File rỗng nhưng request nhận thành công | Form gửi part rỗng | Kiểm tra isEmpty() theo quy tắc nghiệp vụ |
| File lưu sai vị trí | Đường dẫn tương đối và working directory | Log absolute normalized path một cách an toàn |
| HTTP client bị reset khi upload quá lớn | Container/proxy có thể đóng hoặc từ chối đọc body | Xem connector/proxy logs, đừng giả định advice luôn trả JSON |
| Temp directory tăng liên tục | Request chưa kết thúc, cleanup lỗi, tải đồng thời cao hoặc file tồn khác | Theo dõi filesystem, request lifecycle và dung lượng upload |

Khi đặt **resolve-lazily=true**, một số exception parse có thể xuất hiện **khi Controller truy cập file**. Khi false, có thể xảy ra trước binding. **@ExceptionHandler** chỉ có hiệu lực khi exception tới được Spring MVC; không thể xử lý lỗi bị chặn hoàn toàn ở reverse proxy.

Nếu cần ánh xạ MaxUploadSizeExceededException ra JSON thống nhất, dùng @RestControllerAdvice như ví dụ. Với lỗi vượt ngưỡng ở tầng proxy, cấu hình thông điệp lỗi tại proxy/gateway tương ứng. Hãy giữ số đo/traces đủ để biết request đã qua thành phần nào.

## 12. Kiểm thử đúng: happy path, boundary và tình huống production

### 12.1. Test thủ công trên embedded Tomcat thật

Để kiểm tra các hạn mức Servlet, chạy **một server thật** rồi gửi multipart bằng curl hoặc HTTP client. Tối thiểu kiểm tra:

1. Một file hợp lệ dưới giới hạn → 201, file có đúng số byte.
2. File rỗng → 400 theo validation của API mẫu.
3. Thiếu part file → lỗi 4xx do missing part/binding hoặc sai media type.
4. File lớn hơn max-file-size → bị từ chối; ghi nhận tầng và trạng thái/lỗi thực tế.
5. Nhiều part làm vượt max-request-size → bị từ chối.
6. Sai boundary hoặc Content-Type → lỗi parse/415 tùy request.
7. Directory ngoài không writable hoặc disk đầy → server/log phản ánh lỗi I/O, không báo thành công giả.
8. Gửi đồng thời nhiều request → quan sát disk, heap, latency và số file đã ghi.

Một số container có chính sách riêng về giới hạn part count, max swallow size và xử lý kết nối. Kiểm thử bằng đúng embedded server sẽ phát hiện các khác biệt mà unit test thuần không cho thấy.

### 12.2. MockMvc kiểm tra binding và nghiệp vụ, không thay thế container limit test

Trong unit/integration test dùng **MockMvc multipart(...)** và **MockMultipartFile**, ta có thể kiểm tra Controller nhận file, phản hồi và validation. Tuy nhiên request mock **không đi qua cùng Servlet container parser và temp storage như upload HTTP thật**, nên không nên coi một bài MockMvc thành công là bằng chứng về MultipartConfigElement, ngưỡng ghi disk hoặc lỗi kích thước ở Tomcat.

Ví dụ fragment test:

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file",
        "demo.txt",
        "text/plain",
        "hello upload".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/uploads").file(file))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.sizeBytes").value(12));
~~~

Cần đặt đoạn trong một test có MockMvc đã được inject/cấu hình và import MockMultipartFile, StandardCharsets, multipart, status, jsonPath; **không phải file tự biên dịch**. Trên môi trường chạy test, storage directory cũng phải là vị trí tạm riêng cho test để không rác vào dữ liệu thật.

### 12.3. Quan sát ở môi trường triển khai

Theo dõi:
- Số request upload và tỷ lệ 2xx/4xx/5xx; tách riêng 413.
- Kích thước file/request, độ trễ p95/p99 và số upload đồng thời.
- Lượng dữ liệu temp và storage chính; dung lượng disk/inode còn lại.
- Tốc độ client gửi, timeout, lỗi proxy/connector và IOException.
- Thời gian validation/scan, backlog job và số file pending/orphan.
- Sự khác biệt về cấu hình giới hạn giữa môi trường và replica.

Đừng log nội dung file hoặc token/cookie nhạy cảm. Filename do client cung cấp nên được sanitize trước khi đưa vào log, hạn chế độ dài để tránh log injection; dùng request ID để tương quan log an toàn.

## 13. Phân biệt Servlet multipart với WebFlux multipart

Hai stack cùng nói tới multipart/form-data nhưng API không hoán đổi:

| Spring MVC Servlet | Spring WebFlux reactive |
| --- | --- |
| jakarta.servlet.http.Part | org.springframework.http.codec.multipart.Part |
| org.springframework.web.multipart.MultipartFile | org.springframework.http.codec.multipart.FilePart |
| MultipartResolver / StandardServletMultipartResolver | Reactive multipart decoding qua HTTP message readers |
| MultipartConfigElement trên Servlet registration | WebFlux codecs/limits và server reactive tương ứng |
| InputStream/Files.copy thường blocking trên worker Servlet | Flux<DataBuffer>, FilePart.transferTo(...) theo Publisher |
| spring.servlet.multipart.* | Các cấu hình codec/reactive tương ứng, không dùng nhóm Servlet multipart để điều khiển |

Nếu dự án có cả spring-boot-starter-web và spring-boot-starter-webflux, Spring Boot thông thường ưu tiên Spring MVC trừ khi đã chọn cấu hình application type khác; xác định **web application type thực** trước khi áp một property upload. Không chuyển nguyên code MultipartFile/MultipartResolver sang WebFlux và kỳ vọng nó non-blocking.

## 14. Checklist trước khi đưa upload endpoint vào production

- **Content-Type:** Client gửi multipart/form-data có boundary hợp lệ; tên part khớp annotation.
- **Servlet setup:** Có MultipartConfigElement thực sự trên Servlet; MultipartResolver được cấu hình phù hợp, Boot auto-configuration không bị tắt ngoài ý muốn.
- **Hạn mức:** Đặt max-file-size, max-request-size, số part, quota và timeout cả ở proxy lẫn app; test trên server thật.
- **Temp:** Chọn location/threshold có tính toán disk/heap và quyền; giám sát cleanup, concurrency và disk full.
- **Vòng đời:** Đọc/lưu MultipartFile trong request; không giữ file tạm qua response hoặc chuyển raw MultipartFile cho job async.
- **Path:** Tạo tên server-side, không dùng original filename làm đường dẫn; kiểm soát root, symlink, overwrite và file dở dang.
- **Security:** Xác thực/ủy quyền, CSRF cho form browser khi cần, loại file cho phép, xác minh nội dung, malware scanning, quota.
- **Lưu bền vững:** Thư mục hoặc object storage nằm ngoài JAR và ngoài static public, có backup/retention, phục hồi và multi-replica strategy.
- **Errors:** Có thông điệp 4xx/413 hợp lý ở tầng nhận lỗi; không cho rằng mọi lỗi parse được catch ở Controller.
- **Tests:** Có happy path, rỗng, thiếu part, sai media type, quá giới hạn, disk failure, concurrency và smoke test sau deploy.
- **Observability:** Biết request đã dừng ở proxy/container/resolver/binding/service; không log file body hoặc dữ liệu nhạy cảm.

**Ghi nhớ:** MultipartResolver là cầu nối giữa **DispatcherServlet** và Servlet multipart parser; **MultipartConfigElement** đặt giới hạn/thư mục tạm ở Servlet; **MultipartFile** là giao diện đọc file part của một request. File chỉ tồn tại bền vững khi **ứng dụng chủ động lưu** nó ở nơi được quản lý, sau khi đã xác thực dữ liệu và quyền.

## Tài liệu tham khảo chính thức

- Spring Framework 6 — Multipart Resolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
- Spring Framework 6 — Multipart Forms / @RequestParam / @RequestPart: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring Framework 6.1 — MultipartFile Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- Spring Framework 6 — StandardServletMultipartResolver Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/multipart/support/StandardServletMultipartResolver.html
- Spring Boot 3.3 — Application Properties, spring.servlet.multipart.*: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot — Handling Multipart File Uploads: https://docs.spring.io/spring-boot/how-to/spring-mvc.html
