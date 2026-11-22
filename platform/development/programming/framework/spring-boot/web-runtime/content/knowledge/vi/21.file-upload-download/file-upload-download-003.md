# spring.servlet.multipart.*: kích thước tệp, kích thước yêu cầu và nơi lưu tạm

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Tải và nhận tệp

## 1. Bài toán: một upload có thể thất bại trước khi vào controller

Một API Spring MVC nhận ảnh hoặc tài liệu theo **multipart/form-data**. Tệp 500 KB gửi thành công, nhưng tệp 2 MB bị từ chối; hoặc hai tệp 7 MB đều hợp lệ khi gửi riêng, còn gửi chung trong một request lại thất bại. Có lúc ứng dụng báo hết dung lượng đĩa mặc dù bạn không hề chủ động ghi file vào thư mục lưu trữ cuối cùng.

Để giải thích được các tình huống đó phải phân biệt ba câu hỏi:

1. **Mỗi tệp riêng lẻ được phép có tối đa bao nhiêu byte?** → **spring.servlet.multipart.max-file-size**.
2. **Cả HTTP multipart request, gồm nhiều part và phần bao gói, được phép lớn đến đâu?** → **spring.servlet.multipart.max-request-size**.
3. **Trong lúc Servlet container phân tích nội dung, dữ liệu tạm nằm đâu và từ mức nào được ghi ra đĩa?** → **spring.servlet.multipart.location** và **spring.servlet.multipart.file-size-threshold**.

Các thuộc tính này thuộc cơ chế **Servlet multipart** của Spring Boot. Chúng giúp kiểm soát tài nguyên khi nhận body và không tự cung cấp kho lưu tệp bền vững, kiểm tra an toàn tệp, giới hạn tại proxy hoặc xử lý upload trong WebFlux.

Sau bài học, bạn có thể đọc và cấu hình các thuộc tính **spring.servlet.multipart.***; viết API nhận **MultipartFile**; kiểm tra ba giới hạn bằng HTTP thật; phân biệt nơi lưu tạm với nơi lưu cuối và xử lý lỗi vượt giới hạn.

## 2. Multipart/form-data gồm những gì?

Một form HTML hoặc HTTP client gửi dữ liệu theo **multipart/form-data**, trong đó một request body có thể chứa nhiều **part**. Mỗi part có header riêng (**Content-Disposition**, có thể có **Content-Type**) và body.

~~~http
POST /api/uploads/files HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=boundary123

--boundary123
Content-Disposition: form-data; name="description"

Tai lieu mau
--boundary123
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<noi-dung-nhi-phan-cua-report.pdf>
--boundary123--
~~~

Đây là hình minh họa logic; **boundary** và byte kết thúc dòng trên wire do client tạo đúng theo chuẩn, còn chuỗi **<noi-dung-nhi-phan-cua-report.pdf>** đại diện bytes thực.

**Một request có thể chứa nhiều file và form field**. Trong Spring MVC, **@RequestParam("file") MultipartFile file** nhận một part file; **List<MultipartFile>** nhận nhiều file cùng tên; **@RequestPart** hữu ích khi part có JSON cần chuyển đổi qua message converter.

Đường đi khi nhận upload trong Spring Boot Servlet:

~~~text
Client / browser
    |
    | POST multipart/form-data
    v
CDN / reverse proxy / ingress (nếu có giới hạn body)
    |
    v
Servlet container: Tomcat / Jetty / Undertow
    |
    | MultipartConfigElement:
    |  - maxFileSize
    |  - maxRequestSize
    |  - fileSizeThreshold
    |  - location
    v
Spring MVC multipartResolver và DispatcherServlet
    |
    v
Controller @RequestParam MultipartFile
    |
    v
Validation nghiệp vụ, antivirus/quét nội dung, lưu đích cuối
~~~

**Giới hạn multipart có thể được kiểm tra ở tầng container trước khi controller chạy.** Bởi vậy, controller tự gọi **file.getSize()** để từ chối file lớn chỉ là một lớp kiểm tra nghiệp vụ bổ sung, **không thay thế** cấu hình giới hạn nhận body.

## 3. Bảng thuộc tính spring.servlet.multipart.* trong Spring Boot 3.x

Các giá trị mặc định dưới đây theo Spring Boot **3.3**:

| Thuộc tính | Mặc định | Ý nghĩa |
| --- | --- | --- |
| **spring.servlet.multipart.enabled** | **true** | Bật cấu hình multipart tự động trên Servlet stack của Spring Boot. |
| **spring.servlet.multipart.max-file-size** | **1MB** | Kích thước lớn nhất của **mỗi tệp** được upload. |
| **spring.servlet.multipart.max-request-size** | **10MB** | Kích thước lớn nhất của **toàn bộ multipart request**. |
| **spring.servlet.multipart.file-size-threshold** | **0B** | Ngưỡng dữ liệu tệp từ đó container ghi nội dung tạm ra đĩa. |
| **spring.servlet.multipart.location** | Không khai báo | Thư mục trung gian; container sử dụng thư mục tạm mặc định khi không đặt giá trị. |
| **spring.servlet.multipart.resolve-lazily** | **false** | Mặc định phân giải multipart sớm; **true** trì hoãn việc phân giải tới lúc truy cập file/parameter. |
| **spring.servlet.multipart.strict-servlet-compliance** | **false** | **true** giới hạn cách nhận diện multipart theo chuẩn Servlet cho **multipart/form-data**. |

**Các mặc định 1MB, 10MB, 0B là mặc định cấu hình, không phải bảo đảm dung lượng lưu trữ luôn sẵn có.** Trên cùng một server, nginx, ingress hoặc proxy có thể đặt trần nhỏ hơn; Servlet container có thêm giới hạn riêng về kết nối, số part, body hay disk.

Spring Boot bind kích thước thông qua kiểu **DataSize**. Các hậu tố thường dùng là **B**, **KB**, **MB**, **GB**. Ở đây là đơn vị nhị phân:

- **1KB = 1.024 byte**.
- **1MB = 1.048.576 byte**, vì vậy **8MB = 8.388.608 byte**.
- **1GB = 1.073.741.824 byte**.

Dùng chuỗi có đơn vị rõ ràng như **8MB** hoặc **256KB**, tránh viết một số trần khiến người bảo trì khó biết đó là byte hay megabyte.

## 4. Khác biệt giữa max-file-size và max-request-size

**max-file-size** áp dụng cho **từng file part**. **max-request-size** áp dụng cho **request multipart như một tổng thể**, gồm các file part, form field và phần bao gói theo cách Servlet container tính kích thước.

Giả sử:

~~~properties
spring.servlet.multipart.max-file-size=8MB
spring.servlet.multipart.max-request-size=12MB
~~~

| Tình huống | Theo max-file-size | Theo max-request-size | Kết luận |
| --- | --- | --- | --- |
| Một file 7 MB | 7 ≤ 8 | Body khoảng 7 MB cộng overhead ≤ 12 | Thường hợp lệ. |
| Một file 9 MB | 9 > 8 | Body có thể nhỏ hơn 12 | Bị từ chối vì **giới hạn từng file**. |
| Hai file 7 MB cùng request | Mỗi file ≤ 8 | Tổng trên 14 MB > 12 | Bị từ chối vì **giới hạn request**. |
| Một file đúng 8 MB | Vừa bằng giới hạn file | Request lớn hơn 8 MB do header/boundary | Chỉ thành công nếu giới hạn request còn đủ chỗ cho overhead. |
| Một file 11 MB trong request 12 MB | File > 8 | Tổng có thể chưa vượt 12 | Vẫn bị từ chối do giới hạn file. |

**Đừng đặt max-request-size bằng đúng max-file-size** nếu client còn gửi metadata hoặc nhiều part: ngay cả một tệp đúng mức trần vẫn có phần overhead. Trong thực tế, phải chừa khoảng hợp lý theo hợp đồng API, nhưng không mở trần tổng quá lớn so với nhu cầu.

Các giới hạn độc lập với **Content-Length**: request dạng chunked hoặc proxy truyền từng đoạn vẫn phải chịu giới hạn khi server đọc/parse. Client có thể nói sai kích thước hoặc ngắt giữa chừng; vì vậy không tin duy nhất vào header do client cung cấp.

Khi đặt cấu hình, câu hỏi đầu tiên phải là **nghiệp vụ cho phép tệp lớn nhất bao nhiêu và một request được chứa tối đa mấy tệp**, tiếp theo mới xét overhead, concurrency và sức chứa tạm.

## 5. Nơi lưu tạm và ngưỡng ghi đĩa: location, file-size-threshold

### 5.1. location là nơi trung gian, không phải nơi lưu cuối

**spring.servlet.multipart.location** xác định thư mục để Servlet container lưu dữ liệu upload tạm trong quá trình parse. Ví dụ Linux:

~~~properties
spring.servlet.multipart.location=/tmp/boot-multipart-work
~~~

Đường dẫn trên cần tồn tại và tiến trình ứng dụng cần quyền ghi. Trong demo, tạo trước:

~~~bash
mkdir -p /tmp/boot-multipart-work
~~~

Với Windows, đặt một đường dẫn hợp lệ phù hợp máy đang chạy, ví dụ **C:/upload-demo-temp**, và tạo thư mục đó trước khi khởi động. Với Docker/Kubernetes, xem **/tmp** có thực sự là volume hay filesystem tạm bị giới hạn dung lượng/inode.

Khi request hoàn tất, **tệp tạm do container quản lý thường được dọn theo vòng đời multipart request**. Không nên lưu đường dẫn tạm trong database rồi sử dụng lâu dài, cũng không giữ **MultipartFile** để xử lý bất đồng bộ sau khi request đã kết thúc mà chưa sao chép dữ liệu tới nơi an toàn.

**Nơi lưu cuối** là đích do ứng dụng tự định nghĩa, ví dụ **./var/saved-files**, một object storage bucket hoặc kho file ngoài JVM. **location không tự động biến thành kho dữ liệu bền vững**. Nếu API trả thành công nhưng chỉ dựa vào temporary location, tệp có thể mất sau khi request kết thúc hoặc khi container bị xóa.

### 5.2. file-size-threshold không phải giới hạn file

~~~properties
spring.servlet.multipart.file-size-threshold=256KB
~~~

Ý nghĩa: khi dữ liệu tệp vượt ngưỡng theo triển khai multipart của container, nó được spool từ vùng tạm phù hợp sang **disk**. Mặc định **0B** có nghĩa container được cấu hình để ghi tệp tạm ra đĩa ngay theo cơ chế multipart của nó. Tuy nhiên implementation vẫn có buffer I/O nội bộ; đừng suy từ **0B** rằng ứng dụng hoàn toàn không dùng RAM cho upload.

**Giá trị 256KB KHÔNG cấm tệp lớn hơn 256KB**; chỉ nói về bộ nhớ/đĩa trung gian. **max-file-size** mới là trần của file. Nếu đặt threshold vài MB, nhiều request đồng thời có thể cùng dùng RAM để giữ phần dữ liệu chưa được spool; cần xét memory, heap/direct buffers và workload thực tế.

Ví dụ một request hợp lệ có file 7MB với threshold 256KB: file vẫn được chấp nhận nếu dưới max-file-size/max-request-size, nhưng dữ liệu tạm có thể nằm trên disk. Sau khi controller lưu bền vững, data copy riêng có thể sử dụng thêm dung lượng đĩa.

### 5.3. Quy hoạch sức chứa nơi lưu tạm

Cần ước lượng sức chứa theo **đồng thời**, không chỉ theo kích thước tệp lớn nhất:

~~~text
Sức chứa tạm cần thiết (ước lượng ban đầu)
≈ số upload đang hoạt động * dữ liệu tạm trung bình mỗi upload
  + dự phòng cho overhead, ghi đồng thời, retry và các request chưa dọn.
~~~

Ví dụ 100 request đồng thời, mỗi request có thể dùng khoảng 8 MB temporary data: riêng phần payload có thể chiếm xấp xỉ **800 MB**, chưa tính metadata, retry hoặc vị trí lưu cuối. Nếu container có giới hạn ephemeral storage thấp hơn, có thể gặp lỗi ghi tệp dù memory/CPU vẫn còn. Đây là phép ước lượng capacity, **không** phải cam kết mỗi request sẽ tiêu thụ đúng bằng kích thước file.

Lựa chọn thư mục tạm nên xét quyền ghi tối thiểu, dung lượng, inode, lifecycle, backup, mount và monitoring. Không đặt temporary upload cạnh file cấu hình nhạy cảm hoặc trong thư mục có thể được server public trực tiếp.

## 6. Cấu hình demo Spring Boot 3.x + Java 17

Ví dụ sau sử dụng **Spring MVC với embedded Tomcat** và **spring-boot-starter-web**. Nó dùng hai vị trí khác nhau:

- **/tmp/boot-multipart-work**: nơi container lưu file tạm khi phân tích multipart (ví dụ Linux).
- **./var/saved-files**: nơi ứng dụng chủ động lưu file sau khi kiểm tra request.

### 6.1. Dependency

Với project Gradle Spring Boot 3.x đã có Java 17+, Gradle wrapper, Spring Boot plugin và repository, thêm vào **build.gradle** (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter Web cung cấp Spring MVC và embedded Servlet container theo cấu hình mặc định. Không phải thêm Apache Commons FileUpload chỉ để chạy demo này: Spring MVC với Boot 3 dùng cơ chế **Servlet Part** qua **StandardServletMultipartResolver**.

### 6.2. application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
server.port=8080

spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=8MB
spring.servlet.multipart.max-request-size=12MB
spring.servlet.multipart.file-size-threshold=256KB
spring.servlet.multipart.location=/tmp/boot-multipart-work
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true

# Noi luu sau khi ung dung chap nhan upload, tach biet noi tam.
app.upload.storage-dir=./var/saved-files
~~~

**enabled=true** là mặc định, ghi rõ để bài học dễ theo dõi. **strict-servlet-compliance=true** là lựa chọn cho demo chỉ nhận **multipart/form-data**, giúp hành vi nhất quán hơn với cách Servlet specification nhận diện dạng multipart; nếu nghiệp vụ thật cần **multipart/mixed**, hãy đánh giá hỗ trợ container và cấu hình trước khi áp dụng.

**resolve-lazily=false** nghĩa lỗi parse/giới hạn thường xuất hiện sớm khi Spring xử lý multipart request. Nếu bật true, phân giải có thể xảy ra lúc controller hoặc framework truy cập part. Cờ này **không tăng trần file**, không bỏ qua giới hạn container và cũng không bảo đảm mọi lỗi đều được controller advice xử lý.

Với hệ điều hành khác, thay **spring.servlet.multipart.location** bằng đường dẫn tuyệt đối đã tạo sẵn có quyền ghi, rồi mới chạy thử.

### 6.3. Một ứng dụng Java 17+ có thể chạy

Tạo duy nhất file **src/main/java/com/example/upload/UploadDemoApplication.java**:

~~~java
package com.example.upload;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
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
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.MultipartFile;

@SpringBootApplication
public class UploadDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/uploads")
class UploadController {

    private final Path storageDir;

    UploadController(
            @Value("${app.upload.storage-dir:./var/saved-files}") String directory
    ) throws IOException {
        storageDir = Path.of(directory).toAbsolutePath().normalize();
        Files.createDirectories(storageDir);
    }

    @PostMapping(
            value = "/files",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<StoredFile> upload(
            @RequestParam("file") MultipartFile file
    ) throws IOException {
        if (file.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }

        // Khong dung originalFilename lam duong dan do client kiem soat.
        String storageKey = UUID.randomUUID() + ".bin";
        Path destination = storageDir.resolve(storageKey);

        try (InputStream input = file.getInputStream()) {
            // Tao file moi; khong ghi de file da ton tai.
            Files.copy(input, destination);
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new StoredFile(storageKey, file.getSize()));
    }

    @PostMapping(
            value = "/batch-info",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    UploadSummary batchInfo(
            @RequestParam("files") List<MultipartFile> files
    ) {
        long totalFileBytes = files.stream()
                .mapToLong(MultipartFile::getSize)
                .sum();
        return new UploadSummary(files.size(), totalFileBytes);
    }

    record StoredFile(String storageKey, long bytes) {}

    record UploadSummary(int count, long totalFileBytes) {}
}

@RestControllerAdvice
class UploadErrorHandler {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<Map<String, String>> handleTooLarge(
            MaxUploadSizeExceededException ex
    ) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "multipart size limit exceeded"));
    }
}
~~~

**Giải thích:**

- **@RequestParam("file") MultipartFile** nhận một file part tên **file**. **batch-info** dùng nhiều part cùng tên **files** và minh họa tổng file bytes; nó không ghi file vào persistent storage.
- **file.isEmpty()** loại tệp rỗng theo yêu cầu demo. Phần kiểm tra này không thay giới hạn container.
- **UUID** tạo storage key không dựa trên **getOriginalFilename()**; không cho client điều khiển thư mục đích, giảm nguy cơ path traversal hoặc ghi đè file người khác.
- **Files.copy(InputStream, Path)** copy dữ liệu sang thư mục lưu cuối được tạo ở constructor, còn temporary file do Servlet container quản lý. Trước khi đưa vào production cần thêm validation loại tệp, kiểm tra nội dung thực, malware scanning, quota theo người dùng, authentication/authorization và xử lý lỗi/transaction khi storage thất bại.
- **getSize()** là kích thước file part theo bytes. Nó khác **kích thước toàn bộ multipart request**, vì request còn boundary/header/field khác.
- **@RestControllerAdvice** cố trả **413 Payload Too Large** khi **MaxUploadSizeExceededException** tới Spring MVC. Thực tế một proxy hoặc container có thể từ chối request trước tầng advice; vì vậy **không cam kết mọi request vượt giới hạn đều nhận chính xác JSON trên**.
- Demo dùng một file Java có một public class khớp tên file và các class còn lại package-private. Không cần tệp Controller riêng cho ví dụ tối thiểu.

**Không dùng file.getBytes() cho tệp lớn** nếu không cần có toàn bộ dữ liệu trong RAM. **InputStream** cho phép đọc tuần tự, nhưng multipart body có thể đã được container buffer/spool trước khi vào controller; điều này khác streaming end-to-end không cần temporary disk.

### 6.4. Chạy demo

Trên Linux/macOS hoặc môi trường có đường dẫn **/tmp**:

~~~bash
mkdir -p /tmp/boot-multipart-work
./gradlew bootRun
~~~

Khi khởi động, ứng dụng sẽ tạo **./var/saved-files** nếu chưa có. Trong Windows, sửa location sang thư mục tuyệt đối tương ứng và tạo nó; chạy wrapper phù hợp hệ điều hành (**gradlew.bat bootRun** khi dùng cmd/PowerShell).

## 7. Thử ba tình huống khác nhau bằng curl và file thật

Dùng curl hỗ trợ tùy chọn **-F** để gửi multipart/form-data. Trên Linux, tạo file nhị phân mẫu với dd (lệnh chỉ dùng để tạo dữ liệu thử):

~~~bash
dd if=/dev/zero of=seven.bin bs=1048576 count=7
dd if=/dev/zero of=nine.bin bs=1048576 count=9
~~~

**seven.bin** có **7.340.032 byte (7MB)**; **nine.bin** có **9.437.184 byte (9MB)**.

### Case A: một file 7MB — thành công

~~~bash
curl -i -F "file=@seven.bin" http://localhost:8080/api/uploads/files
~~~

Response kỳ vọng:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"storageKey":"<uuid-moi>.bin","bytes":7340032}
~~~

Chuỗi **<uuid-moi>** thay đổi ở mỗi request; đây là output dạng minh họa, không phải UUID có thể đoán trước. Kết quả được ghi vào **./var/saved-files**. **7MB < 8MB** và toàn bộ request cộng overhead nhỏ hơn 12MB nên thông thường thành công.

### Case B: một file 9MB — vượt max-file-size

~~~bash
curl -i -F "file=@nine.bin" http://localhost:8080/api/uploads/files
~~~

File 9MB > trần 8MB. Expect request bị từ chối vì **max-file-size** dù tổng request có thể chưa quá 12MB. Trong điều kiện lỗi đi qua advice có thể thấy:

~~~http
HTTP/1.1 413 Payload Too Large
Content-Type: application/json

{"error":"multipart size limit exceeded"}
~~~

Nếu server thực tế trả thông điệp khác, đóng kết nối, hoặc proxy trả trang HTML 413, cần kiểm tra **tầng nào đã từ chối request**, không mặc định controller advice đã chạy.

### Case C: hai file 7MB — từng file hợp lệ nhưng request quá lớn

~~~bash
curl -i \
  -F "files=@seven.bin" \
  -F "files=@seven.bin" \
  http://localhost:8080/api/uploads/batch-info
~~~

Từng file 7MB < 8MB. Tuy nhiên tổng data khoảng 14MB chưa kể multipart overhead > 12MB, nên **max-request-size** phải chặn request. **batch-info** không thể trả kết quả bình thường.

### Case D: request nhỏ, chỉ số file khác tổng request

~~~bash
printf "hello" > tiny.txt
curl -i -F "files=@tiny.txt" -F "files=@tiny.txt" \
     http://localhost:8080/api/uploads/batch-info
~~~

Body JSON kỳ vọng:

~~~json
{"count":2,"totalFileBytes":10}
~~~

Hai file có mỗi file 5 bytes. Body HTTP thực lớn hơn 10 bytes vì cần boundary và header của các part. Điều này minh họa **file.getSize() không phải kích thước toàn bộ HTTP request**.

### Case E: form HTML tương đương

~~~html
<form method="post" action="/api/uploads/files"
      enctype="multipart/form-data">
    <input type="file" name="file" required>
    <button type="submit">Upload</button>
</form>
~~~

Tên input phải khớp **@RequestParam("file")**. Nếu gửi **application/json** hay quên **enctype=multipart/form-data**, endpoint này không nhận file theo cách đang cấu hình và có thể trả 400 hoặc 415. **Content-Type** với boundary phải do browser/curl xác lập đúng; không nên hardcode header multipart/form-data rồi bỏ mất boundary.

## 8. Vì sao lỗi 413 có thể đến từ nhiều nơi?

Không phải mọi upload quá lớn đều bị Spring Boot chặn đầu tiên. Tùy hệ thống:

~~~text
Browser/Client
    |
    v
CDN/WAF          -> body-size policy, upload timeout
    |
    v
Ingress/Nginx    -> client_max_body_size, buffering/temp files
    |
    v
Servlet container -> multipart max-file/max-request, disk temp
    |
    v
Spring MVC        -> MultipartFile, handler validation
    |
    v
Application store -> per-user quota, disk/object-storage policy
~~~

Ví dụ **Nginx** có thể có **client_max_body_size** khác Spring Boot. Nếu proxy đặt 4MB còn Spring đặt 8MB/file và 12MB/request, client gửi 7MB sẽ bị proxy từ chối **trước khi Spring nhìn thấy upload**. Tăng max-file-size ở Boot lúc này không giải quyết lỗi.

Một số lớp có thể trả 413, 400, 500 hoặc kết thúc kết nối tuỳ server và cấu hình. Phân tích nguyên nhân bằng request ID, access log proxy, error log container và log application. Nếu controller không được gọi, không tiếp tục sửa **file.getSize()** mà phải tìm **giới hạn thấp hơn ở upstream**.

**Đừng chỉ dựa vào UI hiển thị “Upload failed”**: đo HTTP status, response headers và xác định request chạm tầng nào. Với upload lớn, proxy buffering, request timeout, connection timeout và slow client cũng có thể tạo triệu chứng khác size limit.

## 9. Tệp tạm khác tệp bền vững: vòng đời và quyền sở hữu

Cần xác định rạch ròi ba lớp:

| Lớp | Đơn vị sở hữu | Vòng đời | Ví dụ |
| --- | --- | --- | --- |
| **Multipart temporary data** | Servlet container/parser | Theo request hoặc quy tắc cleanup của container | **/tmp/boot-multipart-work** |
| **Application storage** | Service nghiệp vụ | Theo quy tắc retention/transaction của hệ thống | **./var/saved-files**, mounted volume, S3 |
| **Client original filename** | Dữ liệu từ client | Metadata không đáng tin | **invoice.pdf**, có thể bị thao túng |

Sau khi controller nhận **MultipartFile**, nếu cần giữ lâu, hãy lưu bằng **getInputStream()** hoặc **transferTo(...)** vào nơi bền vững được quản lý. **MultipartFile.transferTo(...)** có thể copy hoặc move tùy triển khai và tài nguyên nền; không mặc định có thể gọi lại nhiều lần hoặc có thể giữ part nguyên trạng sau request.

**Tên file client gửi không đáng tin**. **getOriginalFilename()** có thể chứa đường dẫn, ký tự bất thường hoặc tên trùng. Không dùng trực tiếp làm tên file trên disk; đặt ID mới, giữ metadata gốc riêng nếu được phép, xác thực loại tệp và tránh công khai thư mục storage.

**MIME type từ client cũng không đáng tin**; nếu giới hạn PDF/ảnh, cần kiểm tra extension/filename, signature thực tế, giới hạn giải nén và có thể quét độc hại. Upload thành công về mặt multipart mới chỉ chứng minh request được nhận, chưa chứng minh tài liệu an toàn.

**Xóa tệp tạm:** không tự tìm xóa mọi file trong temp directory khi ứng dụng đang hoạt động, vì có thể có request khác còn dùng. Nếu quy trình storage bất đồng bộ, trước khi kết thúc request phải chuyển dữ liệu sang staging storage có lifecycle do ứng dụng quản lý; không giữ MultipartFile vào queue rồi mong temporary bytes tồn tại mãi.

## 10. Tuning file-size-threshold: đổi RAM lấy I/O

**Threshold nhỏ (0B hoặc 256KB)** thường giúp tránh giữ nhiều file lớn trong bộ nhớ ở tầng multipart parser, nhưng tốn I/O và cần đủ disk. **Threshold lớn** có thể giảm I/O cho file nhỏ, song với hàng trăm upload đồng thời có nguy cơ tăng memory footprint. Đừng chọn chỉ bằng cảm giác.

Ví dụ chính sách hợp lý cho hệ thống nhận ảnh tối đa 8MB có 20 upload cùng lúc:

- Đặt file limit theo nghiệp vụ (**8MB**).
- Đặt request limit đủ cho số part/ảnh mỗi API (**12MB** trong demo một file, riêng batch cần giới hạn khác nếu hỗ trợ nhiều file).
- Đặt threshold nhỏ (**0B** hoặc **256KB**) nếu disk đáng tin và muốn hạn chế buffering bộ nhớ.
- Dự toán temp disk theo đồng thời (ví dụ 20 x khoảng 8MB là khoảng 160MB chưa overhead), kiểm tra container ephemeral storage và số inode.
- Đặt concurrency/timeout và quota người dùng để chống flood những request hợp lệ nhưng rất nhiều.

**0B không có nghĩa không dùng RAM; 256KB không phải “mỗi request tiêu thụ tối đa 256KB”; 8MB không có nghĩa “mỗi request chỉ tốn 8MB disk”.** Đó là các khái niệm khác nhau và thực tế còn phụ thuộc container, parsing, copy sang final storage và số request đồng thời.

Giám sát **disk usage/inodes** tại location, tình trạng filesystem full/read-only, số upload đang xử lý, tỷ lệ 413, exception parse, request duration, thời gian copy sang storage, số request bị cancel và mức sử dụng heap/direct memory.

## 11. Docker/Kubernetes và nhiều instance

Trong container, đường **/tmp** thường thuộc lớp filesystem của container hoặc volume tạm. Khi pod được tái tạo, file tạm và các file lưu cuối trong filesystem ephemeral có thể mất. Phân biệt:

- **Temporary path:** có thể dùng emptyDir/ephemeral volume với sizeLimit phù hợp và giới hạn tổng ephemeral storage của pod.
- **Persistent path:** dùng persistent volume hoặc object storage khi cần dữ liệu tồn tại qua restart, rollout và nhiều replica.
- **Security context:** user chạy ứng dụng phải có quyền ghi temporary directory; không chạy container bằng root chỉ để tránh sửa permission.
- **Replicas:** nếu lưu file cuối ở disk riêng của từng pod, request tải file sau đó có thể đến pod khác không có dữ liệu. Dùng shared store hoặc routing được thiết kế, không lấy multipart location làm shared storage.
- **Quota riêng:** dù container memory còn dư, đĩa tạm có thể đầy; dù disk còn dư, storage cuối có thể từ chối vì permission/quota.

Một số hệ thống mount **/tmp** lên **tmpfs** nên cái gọi là “ghi ra đĩa” thực tế lại tiêu thụ RAM do filesystem quản lý. Không kết luận threshold=0 bảo đảm dữ liệu luôn được đặt trên ổ đĩa vật lý.

Nếu muốn file rất lớn hoặc upload kéo dài/hàng trăm MB đến GB, nên đánh giá **direct-to-object-storage upload có URL ký trước**, multi-part/resumable upload ở tầng storage, virus scan và callback xác nhận; không mở max-file-size=-1 rồi chuyển toàn bộ tải qua Servlet container mà thiếu giới hạn mới.

## 12. resolve-lazily và strict-servlet-compliance có tác dụng gì?

### resolve-lazily

Theo mặc định **false**, Spring MultipartResolver thường cố phân tích multipart request sớm. Khi đặt:

~~~properties
spring.servlet.multipart.resolve-lazily=true
~~~

Việc phân tích có thể được trì hoãn tới lúc truy cập parameter hoặc file. Điều này có thể làm **thay đổi thời điểm** và vị trí call stack phát sinh exception, nhất là với request lớn hoặc dữ liệu malformed. **Không làm tăng kích thước chấp nhận** và không biến một request lỗi thành request hợp lệ.

Nếu có code muốn bắt lỗi ở filter/interceptor/advice, cần test thực tế với container vì parse sớm/muộn ảnh hưởng luồng exception; không suy đoán chắc chắn mọi MaxUploadSizeExceededException đều được advice nhận.

### strict-servlet-compliance

~~~properties
spring.servlet.multipart.strict-servlet-compliance=true
~~~

Khi bật, resolver chỉ nhận các multipart request theo phạm vi **multipart/form-data** chuẩn Servlet để tránh phụ thuộc những kiểu multipart khác giữa container. Trong demo upload form, đây là lựa chọn phù hợp. Nếu API nhận **multipart/mixed**, hãy kiểm tra yêu cầu thực tế và hành vi parser/container; không bật cờ này một cách vô thức rồi tự hỏi vì sao multipart/mixed không được xử lý giống multipart/form-data.

### enabled

~~~properties
spring.servlet.multipart.enabled=false
~~~

Giá trị false tắt auto-configuration multipart của Spring Boot Servlet. Nó **không phải cách tăng giới hạn size**. Nếu ứng dụng cần multipart mà bạn tắt auto-config, phải tự chịu trách nhiệm cấu hình Servlet multipart và resolver tương ứng, nếu không controller nhận MultipartFile có thể không hoạt động như mong đợi.

## 13. Servlet MVC khác WebFlux ở cấu hình upload

**spring.servlet.multipart.*** thuộc hệ thống **Servlet Part** trong Spring Boot. Khi project dùng **spring-boot-starter-web**, MultipartAutoConfiguration thường cấu hình **MultipartConfigElement** và **StandardServletMultipartResolver** để Spring MVC nhận **MultipartFile**.

**Spring WebFlux** với Reactor Netty dùng reactive multipart model, ví dụ **FilePart** và **Part** trong package **org.springframework.http.codec.multipart**. Điều này khác Servlet **MultipartFile/jakarta.servlet.http.Part**. Không suy luận các thuộc tính **spring.servlet.multipart.max-file-size**, **max-request-size** và **location** sẽ điều khiển WebFlux chạy trên Reactor Netty.

Trong WebFlux, giới hạn decoder, **maxInMemorySize** và multipart codec settings được cấu hình theo reactive stack; khi làm nội dung cho WebFlux cần đọc tài liệu tương ứng và kiểm tra dữ liệu được spool/stream thế nào. Nếu project thêm cả web starter và webflux starter, Spring Boot có thể ưu tiên Servlet MVC theo mặc định; xác nhận **ApplicationContext/web stack thực sự** trước khi điều chỉnh các property.

**Sửa sai stack là lỗi phổ biến:** đặt spring.servlet.multipart.max-file-size=50MB trong một dịch vụ WebFlux/Netty rồi cho rằng đã giới hạn file upload 50MB là kết luận không có cơ sở.

## 14. Thiết kế test đúng: MockMvc chưa đủ để kiểm giới hạn container

Có thể viết unit test controller với MockMultipartFile/MockMvc để kiểm tra:

- Mapping nhận part tên **file** hay không.
- Khi **file.isEmpty()** thì trả 400.
- Service tạo storage key và gọi logic lưu theo giả lập.
- JSON response/validation phù hợp.

Nhưng **MockMvc.multipart(...) thường xây request giả trực tiếp**, không đi qua một request HTTP thật được Servlet container parse từ socket. Vì vậy test MockMvc thành công **không chứng minh** **max-file-size** hay **max-request-size** sẽ chặn ở Tomcat đúng như production.

Muốn kiểm trần này, chạy integration test bằng **server thực và HTTP client thật**:

1. Khởi động embedded Tomcat trên một cổng HTTP và xác nhận nó dùng application.properties dự kiến.
2. Gửi file nhỏ dưới giới hạn, xác nhận 201 và bytes lưu cuối.
3. Gửi file vượt max-file-size nhưng request dưới max-request-size, xác nhận bị từ chối tại đúng tầng.
4. Gửi hai file mà từng file hợp lệ nhưng tổng request vượt max-request-size, xác nhận bị từ chối.
5. Kiểm tra temp path có quyền ghi, giám sát disk trong khi upload, và xác nhận file final không bị phụ thuộc vào temp sau request.
6. Chạy lại qua proxy/ingress với limits thực; chỉ test localhost không kiểm được CDN/nginx hoặc body buffering.
7. Test request bị ngắt, thiếu dung lượng temp, file rỗng, tên file lạ và nhiều upload đồng thời theo giới hạn an toàn của môi trường test.

Không cần sinh file test khổng lồ vô hạn để “thử đến khi sập máy”: dùng vài file có kích thước có tính toán và cô lập môi trường test.

## 15. Chẩn đoán các lỗi phổ biến

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| File 2MB bị từ chối khi chưa cấu hình gì | Mặc định **max-file-size=1MB**. | Đặt trần theo nghiệp vụ, kiểm tra thêm giới hạn proxy và request. |
| Hai file riêng đều upload được, gửi chung bị lỗi | **max-request-size** nhỏ hơn tổng các part. | Tính tổng file + multipart overhead; cân nhắc endpoint batch riêng hoặc upload từng file. |
| File bằng đúng max-file-size vẫn lỗi | Tổng body có header/boundary/field vượt max-request-size. | Chừa headroom phù hợp cho request; đo kích thước thực. |
| Controller không vào, chỉ thấy HTTP 413 | Proxy hoặc container từ chối trước tầng handler. | Kiểm tra logs và limits theo từng hop. |
| Thư mục tạm đầy, file cuối chưa xuất hiện | Servlet container spool body vào **location** trước khi controller lưu. | Cấp đủ temp disk/volume, monitor concurrency và cleanup. |
| File upload thành công rồi biến mất | Đã giữ đường dẫn temp/MultiPartFile thay vì lưu bền vững. | Copy/transfer data sang storage có lifecycle riêng trong request. |
| OOM khi upload đồng thời | Threshold/buffering quá lớn, app dùng **getBytes()** hoặc giữ dữ liệu nhiều request. | Dùng stream, giảm memory buffering, giới hạn concurrent uploads. |
| API dùng WebFlux nhưng property Servlet không tác dụng | Sai web stack, decoder/config khác. | Xác nhận Reactor Netty/WebFlux và giới hạn codec phù hợp. |
| Permission denied dù thư mục có tồn tại | User chạy app không có quyền ghi vào location/final store. | Kiểm tra user/group, mount, read-only rootfs, SELinux/permissions nếu có. |
| Lỗi upload chỉ xuất hiện trong Kubernetes | Ephemeral storage, tmpfs, disk quota, ingress limit hoặc replica storage không chung. | Kiểm tra pod resources, volumes, ingress và object storage. |
| Exception handler không trả JSON 413 mong đợi | Parser/container/proxy ném lỗi hoặc ngắt kết nối trước Spring advice. | Ghi log, kiểm request path thực; không ép mọi lỗi thành lỗi nghiệp vụ. |
| Dùng filename gửi từ client tạo đường dẫn | Path traversal, tên trùng, ký tự không hợp lệ. | Sinh storage key mới, validate và lưu metadata riêng. |

## 16. Câu hỏi tự kiểm tra

1. **max-file-size=8MB** có cho phép hai file 7MB trong một request nếu **max-request-size=12MB** không? **Không**: từng file hợp lệ nhưng tổng request quá lớn.
2. **file-size-threshold=256KB** có cấm upload 1MB không? **Không**: threshold là ranh giới spool, không phải giới hạn kích thước được chấp nhận.
3. **location** có thay thế **storage-dir** trong controller không? **Không**: location là nơi lưu trung gian do container quản lý; ứng dụng phải tự lưu vào nơi bền vững.
4. **no-store**, cache HTTP hay static-resource chain có liên quan trực tiếp đến upload multipart không? **Không phải cơ chế kiểm size**. Multipart là body được nhận/parse, còn cache tĩnh là bài toán phục vụ response.
5. **getOriginalFilename()** có an toàn để dùng làm Path trực tiếp không? **Không**, vì được gửi từ client; cần sinh key mới và kiểm tra tên/loại tệp.
6. Vì sao 413 có thể không vào **@RestControllerAdvice**? Vì request có thể bị chặn trước khi đến Spring MVC.
7. Tại sao upload nhỏ trên laptop chạy được nhưng pod lại lỗi ghi file tạm? Có thể **volume/quota/permission** khác nhau.
8. Nếu dùng **WebFlux/Reactor Netty**, có nên mặc định dùng **spring.servlet.multipart.***? **Không**; phải dùng cấu hình multipart reactive tương ứng.
9. Vì sao **MockMvc** không đủ để chứng minh giới hạn multipart Servlet? Vì request mock không nhất thiết đi qua parser/limits của container qua HTTP thật.
10. Có nên đặt **max-file-size=-1** để tránh lỗi người dùng? Chỉ khi đã thiết kế cơ chế giới hạn, tài nguyên và an toàn khác; với upload công khai thông thường **không nên bỏ giới hạn tùy tiện**.

## 17. Tài liệu tham khảo chính thống

- **Spring Boot 3.3 – Common Application Properties, Servlet Multipart:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- **Spring Boot – How-to: Handling Multipart File Uploads:** https://docs.spring.io/spring-boot/how-to/spring-mvc.html
- **Spring Boot – MultipartProperties API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html
- **Spring Framework – MVC Multipart Resolver:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
- **Spring Framework – Controller Multipart Forms:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- **Spring Framework – DataSize (binary prefixes):** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/util/unit/DataSize.html
- **Spring Framework – MultipartFile Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/multipart/MultipartFile.html
