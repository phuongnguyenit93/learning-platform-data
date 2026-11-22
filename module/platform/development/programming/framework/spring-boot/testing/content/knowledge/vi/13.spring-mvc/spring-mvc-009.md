# Spring MVC: Multipart, upload và giới hạn dữ liệu trong kiểm thử Spring Boot

## Mục tiêu

Một API nhận file upload không chỉ cần trả HTTP 200 khi gửi tệp hợp lệ. Nó còn phải xử lý **multipart/form-data**, các trường biểu mẫu đi kèm, JSON metadata, file rỗng, sai loại dữ liệu, kích thước vượt giới hạn, file name không đáng tin và lỗi từ tầng Servlet container. Nếu chỉ test bằng một `MockMultipartFile` đúng định dạng, rất nhiều lỗi quan trọng sẽ bị bỏ sót.

Bài học này giúp bạn:

- Phân biệt request multipart với request JSON hoặc `application/x-www-form-urlencoded`.
- Sử dụng `@RequestParam`, `@RequestPart`, `MultipartFile`, `MockMultipartFile` và `MockMvcRequestBuilders.multipart(...)` đúng ngữ nghĩa.
- Viết kiểm thử upload theo đường đi thành công và lỗi: thiếu part, file rỗng, Content-Type không phù hợp, JSON metadata sai, dữ liệu vượt ngưỡng nghiệp vụ.
- Hiểu ba ngưỡng **file size**, **request size** và **file-size-threshold**, cùng đường đi từ `MultipartResolver` tới Servlet container.
- Biết vì sao **MockMvc không đủ để khẳng định container đã áp dụng `spring.servlet.multipart.max-file-size`**.
- Viết test dùng **Spring Boot/Java 17/JUnit Jupiter** có hai tầng: MVC slice và HTTP integration với embedded server trên port ngẫu nhiên.
- Thiết kế kiểm thử bảo mật, tài nguyên và xử lý lỗi upload để tránh lỗ hổng thường gặp.
- Chẩn đoán lỗi 400/413/415, parser, proxy, server và multipart boundaries trong CI.

**Ý chính:** Test controller với `MockMvc` để kiểm logic và MVC binding; test **HTTP thật** để kiểm parsing multipart và giới hạn do container áp dụng. Hai nhóm test bổ trợ cho nhau, không nên dùng một nhóm làm bằng chứng cho cả hai.

## 1. Multipart là gì?

Một HTTP request `multipart/form-data` chứa nhiều **part**, mỗi part có headers riêng và một vùng dữ liệu, được ngăn cách bằng một chuỗi `boundary`. Trình duyệt thường dùng cách này khi form chứa file cùng các field văn bản.

Ví dụ minh họa request:

~~~http
POST /api/uploads HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=DemoBoundary

--DemoBoundary
Content-Disposition: form-data; name="category"

docs
--DemoBoundary
Content-Disposition: form-data; name="file"; filename="note.txt"
Content-Type: text/plain

hello
--DemoBoundary--
~~~

Đây là **sơ đồ giao thức để đọc**, không phải tệp HTTP raw đã bao gồm mọi byte `\r\n` chính xác. Khi gửi thật, boundary trong header và body phải trùng nhau, các dòng phân cách dùng CRLF theo chuẩn MIME multipart. Ứng dụng hoặc HTTP client thường tạo framing hộ bạn.

Phân biệt:

| Kiểu request | Body điển hình | Controller thường nhận |
| --- | --- | --- |
| `application/json` | Một JSON document | `@RequestBody SomeDto` |
| `application/x-www-form-urlencoded` | `category=docs&count=2` | `@RequestParam`/`@ModelAttribute` |
| `multipart/form-data` | Nhiều part: field, file, có thể JSON | `@RequestParam`, `@RequestPart`, `MultipartFile` |
| `application/octet-stream` | Một luồng bytes đơn | `@RequestBody byte[]` hoặc `InputStream` theo thiết kế |

**Đừng nhầm content type của request với content type của một part.** Request có thể có `Content-Type: multipart/form-data`, còn part `file` có `Content-Type: text/plain`, và part `metadata` có `Content-Type: application/json`.

### Hai khái niệm về độ lớn

- **Kích thước một file:** số byte nội dung file upload, ví dụ `file.getSize()`.
- **Kích thước cả multipart request:** gồm phần dữ liệu các file, metadata, các trường text và overhead framing/headers/boundaries. Nó có thể **lớn hơn tổng kích thước file**.

Do đó một request chứa ba file, mỗi file 900 KB, có thể không vượt `max-file-size=1MB` cho từng file nhưng vẫn vượt `max-request-size` nếu tổng dữ liệu và overhead lớn hơn ngưỡng cấu hình.

## 2. Spring MVC xử lý multipart như thế nào?

Luồng thông dụng trong ứng dụng Spring Boot Servlet MVC:

~~~text
HTTP client
    |
    | POST multipart/form-data + boundary
    v
Reverse proxy / load balancer (có thể có body limit riêng)
    |
    v
Embedded Servlet container, ví dụ Tomcat
    |
    | đọc/parse multipart theo MultipartConfigElement
    | có thể kiểm maxFileSize/maxRequestSize
    v
DispatcherServlet + MultipartResolver
    |
    | cung cấp MultipartHttpServletRequest/MultipartFile
    v
Spring MVC argument binding
    |
    +-- @RequestParam("category") String
    +-- @RequestParam("file") MultipartFile
    +-- @RequestPart("metadata") UploadMetadata
    |
    v
Controller -> validation -> service/storage
    |
    v
HTTP response
~~~

Spring MVC cung cấp `MultipartResolver`. Với stack Servlet hiện đại, `StandardServletMultipartResolver` sử dụng cơ chế multipart của **Servlet container**. Spring Boot thông thường cấu hình hỗ trợ multipart và các thuộc tính `spring.servlet.multipart.*` cho môi trường Servlet. <u>Giới hạn container</u> có thể được kiểm **trước khi controller bắt đầu chạy**.

Những điểm test cần biết:

1. Parser có thể từ chối request vì quá kích thước hoặc multipart hỏng **trước khi tạo được `MultipartFile` hợp lệ**.
2. Sau khi đã parse, controller có thể áp dụng **giới hạn nghiệp vụ bổ sung**, ví dụ tối đa 8 byte cho một API demo.
3. Client/proxy có thể từ chối body trước khi request tới ứng dụng; khi đó `@ControllerAdvice` của Spring **không nhìn thấy request**.
4. `MockMvc` dùng các đối tượng Servlet giả để chạy MVC handler, **không mở socket và không thực hiện đầy đủ parsing multipart trên Tomcat**.

Vì thế assertion “MockMvc gửi file 100 MB mà vẫn nhận 200” không tự chứng minh rằng production upload limit bị vô hiệu; và assertion “MockMvc từ chối 100 MB vì controller kiểm `getSize()`” không chứng minh Tomcat `max-file-size` đã được cấu hình đúng.

## 3. Nhận file và metadata bằng annotation nào?

### `@RequestParam` cho file và field biểu mẫu

Với một file và một field thường:

~~~java
@PostMapping(
        path = "/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<String> upload(
        @RequestParam("file") MultipartFile file,
        @RequestParam("category") String category) {
    return ResponseEntity.ok(category + ":" + file.getSize());
}
~~~

Đây là snippet minh họa; các import/controller class và validation chưa được khai báo. `MultipartFile` cho phép lấy `getName()`, `getOriginalFilename()`, `getContentType()`, `getSize()`, `isEmpty()`, `getInputStream()` và `transferTo(...)`. **`getOriginalFilename()` là dữ liệu do client cung cấp, không được xem là đường dẫn an toàn để ghi file.**

### `@RequestPart` cho JSON metadata

Khi part `metadata` có `Content-Type: application/json`, `@RequestPart` cho phép Spring chuyển JSON thành object thông qua `HttpMessageConverter`:

~~~java
@PostMapping(
        path = "/files/with-meta",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<String> uploadWithMeta(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    return ResponseEntity.ok(
            metadata.category() + ":" + file.getSize());
}
~~~

Snippet cần `UploadMetadata` và imports thích hợp. `@RequestPart` với object dữ liệu khác `@RequestParam("metadata") String`: trường hợp đầu kích hoạt conversion/JSON binding theo media type của part; trường hợp sau chỉ nhận text và bạn tự parse nếu muốn.

Khi có Bean Validation dependency, có thể dùng `@Valid @RequestPart("metadata") UploadMetadata metadata` và các constraint như `@NotBlank`, `@Size` trên DTO. Với Spring MVC 6.x, lỗi validation trên request part thường được chuyển thành phản hồi 400 khi xử lý theo cơ chế mặc định, trừ khi ứng dụng có handler riêng. Đừng mặc định `@Valid` tự chạy nếu chưa khai báo validation starter/provider phù hợp.

### Khi upload nhiều file

Ví dụ API nhận các part cùng tên `files`:

~~~java
@PostMapping(
        path = "/batch",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<Integer> batch(
        @RequestParam("files") List<MultipartFile> files) {
    return ResponseEntity.ok(files.size());
}
~~~

Snippet này chỉ minh họa cú pháp, không phải endpoint an toàn đầy đủ. Với upload nhiều file cần kiểm **từng file**, **số lượng file**, **tổng byte**, giới hạn request và chi phí xử lý. `@RequestParam("files") List<MultipartFile>` nhận nhiều file dưới cùng tên part `files`; nếu client gửi `file` hoặc `file[]`, tên không tự luôn khớp.

## 4. Các thuộc tính giới hạn multipart của Spring Boot

Trong ứng dụng Spring Boot 3.3 Servlet MVC, các thuộc tính phổ biến gồm:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=1MB
spring.servlet.multipart.max-request-size=10MB
spring.servlet.multipart.file-size-threshold=0B
~~~

Đây là **giá trị mặc định điển hình của Boot 3.3**, được hiển thị để giải thích; thường không cần sao chép chúng vào `application.properties` nếu chấp nhận mặc định.

| Property | Mục đích | Giá trị mặc định Boot 3.3 |
| --- | --- | --- |
| `spring.servlet.multipart.enabled` | Bật hỗ trợ multipart trong Boot Servlet MVC | `true` |
| `spring.servlet.multipart.max-file-size` | Giới hạn dữ liệu của **một file** được upload | `1MB` |
| `spring.servlet.multipart.max-request-size` | Giới hạn toàn bộ request multipart | `10MB` |
| `spring.servlet.multipart.file-size-threshold` | Ngưỡng sau đó nội dung file được ghi ra đĩa tạm | `0B` |
| `spring.servlet.multipart.location` | Vị trí lưu file tạm trong quá trình parse | Không cố định; tùy cấu hình/hệ điều hành |
| `spring.servlet.multipart.resolve-lazily` | Có trì hoãn multipart parsing tới lúc truy cập part/parameter hay không | `false` |

Các kiểu giá trị `DataSize` thường chấp nhận `B`, `KB`, `MB`, `GB` theo parser/configuration của Boot. **“1MB” là đơn vị do Spring Boot xử lý**, không nên tùy tiện coi là một triệu byte khi viết test boundary; nếu cần precision, dùng `B` hoặc đọc `MultipartProperties.getMaxFileSize().toBytes()`.

Một ví dụ cấu hình riêng cho môi trường test:

~~~properties
spring.servlet.multipart.max-file-size=4B
spring.servlet.multipart.max-request-size=1KB
~~~

Cấu hình này có chủ đích rất nhỏ để thử hành vi: file 3 byte được cho phép theo ngưỡng file, file 5 byte sẽ vượt `max-file-size`. Tổng kích thước HTTP multipart, gồm headers/boundary, phải dưới `max-request-size=1KB` cho ca hợp lệ.

### `file-size-threshold` không phải ngưỡng từ chối

`file-size-threshold` kiểm **khi nào container đẩy dữ liệu upload ra disk tạm**, không phải “file lớn hơn ngưỡng này sẽ bị lỗi”. Ngưỡng từ chối tương ứng là `max-file-size` và `max-request-size`. Dù threshold là `0B`, ứng dụng vẫn cần có không gian đĩa tạm, quyền ghi và chính sách dọn file tạm phù hợp.

### Không nhầm đơn vị và số byte trong file UTF-8

Chuỗi `abc` có 3 byte UTF-8; ký tự tiếng Việt như `ấ` thường được mã hóa thành nhiều hơn một byte. `MultipartFile.getSize()` đo **byte**, không phải số `char` Java. Test giới hạn theo byte phải chuẩn bị `byte[]` xác định, dùng `StandardCharsets.UTF_8` nếu nguồn là chuỗi.

### Có nên đặt giới hạn vô hạn?

Một số phiên bản Boot hỗ trợ giá trị `-1` cho giới hạn không giới hạn ở tầng servlet multipart. Đây **không phải lựa chọn mặc định an toàn** cho API public: upload rất lớn có thể làm đầy disk, chiếm kết nối, tăng GC/memory pressure và gây denial of service. Khi cần upload dữ liệu lớn, hãy thiết kế streaming, quotas, multipart/chunked protocol hoặc object storage phù hợp, kết hợp giới hạn proxy và tầng application.

## 5. Chọn đúng tầng test

| Điều cần kiểm | Công cụ phù hợp | Bằng chứng thu được |
| --- | --- | --- |
| Binding `file`, `category` vào controller | `@WebMvcTest` + `MockMvc multipart` | Mapping, argument resolution, HTTP status/JSON |
| Thiếu file, file rỗng, sai part name | `MockMvc` | MVC/controller trả lỗi đúng |
| JSON part `metadata` được parse đúng | `MockMvc` + `MockMultipartFile` có `application/json` | `@RequestPart` và JSON conversion |
| File > 8 byte bị logic nghiệp vụ chặn | `MockMvc` | Guard trong controller/service hoạt động |
| Tomcat thật chặn file > `max-file-size` | `@SpringBootTest(RANDOM_PORT)` + HTTP client multipart thật | Hành vi parser/container trong môi trường tích hợp |
| Tổng request > `max-request-size` | HTTP integration test với nhiều part/headers | Giới hạn tổng body ở tầng server |
| Proxy/CDN chặn body quá lớn | Test qua đúng proxy/gateway triển khai | Kiểm chính sách upstream ngoài JVM |
| File được ghi và đọc lại đúng | Integration test storage adapter/object store/test directory | Persistence/storage behavior |
| Virus/malware scanning, content sniffing | Test adapter/scanner và integration theo hệ thống | Kiểm bảo mật nội dung, không chỉ MIME header |
| Tải song song, quota và tài nguyên disk | Load/resource test có fixture an toàn | Hành vi tài nguyên, không do một MockMvc test chứng minh |

Đừng tự mở `@SpringBootTest` cho mọi phép kiểm dữ liệu đầu vào nếu `@WebMvcTest` đã đủ; cũng đừng dùng một `MockMultipartFile` làm bằng chứng rằng Tomcat đã từ chối request multipart theo byte limit.

## 6. Ví dụ chạy được: Spring Boot 3.3.5 + Java 17 + JUnit Jupiter

Đây là một project độc lập với **12 test method** ở hai lớp:

- `UploadControllerMvcTest`: 9 test bằng `MockMvc`, không mở HTTP port.
- `UploadHttpIntegrationTest`: 3 test với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, gửi **multipart body thật** qua `java.net.http.HttpClient`. Đặt `max-file-size=4B` để thấy cách parser/container chặn trước business limit 8 byte.

Bài ví dụ **không lưu file xuống đĩa**, chỉ xử lý nội dung text cực nhỏ và trả JSON để tập trung vào binding và giới hạn. Đây không phải thiết kế đủ điều kiện cho hệ thống lưu tài liệu production.

### 6.1. Cấu trúc tệp

~~~text
spring-multipart-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/upload/
    │   ├── UploadApplication.java
    │   ├── UploadController.java
    │   └── UploadLimitAdvice.java
    └── test/java/com/example/upload/
        ├── UploadControllerMvcTest.java
        └── UploadHttpIntegrationTest.java
~~~

Dùng đúng đường dẫn/package khi chép các file. Các file Gradle Wrapper cần được tạo bởi Gradle thích hợp hoặc lấy từ repository đã cấu hình; không viết thủ công `gradle-wrapper.jar` vì đó là tệp nhị phân.

**`settings.gradle`**

~~~groovy
rootProject.name = 'spring-multipart-demo'
~~~

**`build.gradle`** — cấu hình cụ thể cho bài học Java 17, Spring Boot 3.3.5:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` mang Spring MVC, Tomcat embedded trong cấu hình mặc định và Jackson. `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring MVC Test/MockMvc và các công cụ test. Ví dụ không cần lưu file vào DB, không cần `spring-boot-starter-data-jpa` và không cần Mockito vì controller không có dependency ngoài.

**`src/main/java/com/example/upload/UploadApplication.java`**

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

Đặt `@SpringBootApplication` cùng package cha giúp Spring Boot test tìm được configuration và quét controller/advice tương ứng.

### 6.2. Controller nhận file, field và JSON part

**`src/main/java/com/example/upload/UploadController.java`**

~~~java
package com.example.upload;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    // Business rule của demo; độc lập với giới hạn Servlet.
    private static final long BUSINESS_LIMIT_BYTES = 8;

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadReceipt upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam(
                    value = "category",
                    defaultValue = "general") String category)
            throws IOException {
        return createReceipt(file, category);
    }

    @PostMapping(
            path = "/with-meta",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadReceipt uploadWithMeta(
            @RequestPart("metadata") UploadMetadata metadata,
            @RequestPart("file") MultipartFile file)
            throws IOException {
        return createReceipt(file, metadata.category());
    }

    private UploadReceipt createReceipt(
            MultipartFile file, String category)
            throws IOException {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "EMPTY_FILE");
        }

        if (file.getSize() > BUSINESS_LIMIT_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "BUSINESS_FILE_LIMIT");
        }

        if (!MediaType.TEXT_PLAIN_VALUE.equals(
                file.getContentType())) {
            throw new ResponseStatusException(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "TEXT_FILE_REQUIRED");
        }

        if (category == null || category.isBlank()
                || category.length() > 24) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "INVALID_CATEGORY");
        }

        // Chỉ demo: file tối đa 8 byte; không dùng kiểu này
        // để đọc trọn file lớn ở production.
        String text = new String(
                file.getBytes(), StandardCharsets.UTF_8);

        return new UploadReceipt(
                file.getSize(), category, text);
    }

    public record UploadMetadata(String category) {
    }

    public record UploadReceipt(
            long bytes, String category, String text) {
    }
}
~~~

**Giải thích thứ tự kiểm tra:**

1. File rỗng → 400 theo quy tắc demo.
2. File vượt 8 byte nhưng đã được parser chấp nhận → controller trả 413.
3. File part không có Content-Type đúng `text/plain` → 415.
4. `category` rỗng hoặc quá 24 ký tự → 400.
5. Dữ liệu hợp lệ → tạo DTO `UploadReceipt` để Spring/Jackson serialize thành JSON.

Chính sách kiểm Content-Type ở đây **cố ý đơn giản**: so đúng chuỗi header `text/plain`. Trong production, MIME header là **dữ liệu client tự khai báo**; cần content sniffing, parser theo định dạng và kiểm dữ liệu thật khi loại file có rủi ro. Không được kết luận file “an toàn” chỉ vì MIME header đúng.

`file.getBytes()` có thể tạo một mảng lớn trong RAM nếu dùng không kiểm soát. Ví dụ chỉ làm như vậy vì **business limit là 8 byte**. Với file lớn, nên dùng `getInputStream()`/`transferTo(...)` hoặc streaming/storage adapter và áp dụng giới hạn từ hạ tầng trước khi cấp nhiều tài nguyên.

### 6.3. Advice chuyển lỗi kích thước multipart của container thành HTTP 413

**`src/main/java/com/example/upload/UploadLimitAdvice.java`**

~~~java
package com.example.upload;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class UploadLimitAdvice {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<Map<String, String>> handleLimit(
            MaxUploadSizeExceededException exception) {
        return ResponseEntity.status(
                HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of(
                        "error", "MULTIPART_LIMIT_EXCEEDED"));
    }
}
~~~

Advice này chỉ xử lý `MaxUploadSizeExceededException` khi lỗi đã được Spring MVC đưa vào exception resolution. Nó **không bắt mọi lỗi** phát sinh từ proxy, servlet container hoặc TCP; một container/proxy có thể chặn trước khi Spring tạo response và trình bày lỗi khác. Đối với các test pinned demo với body nhỏ và Tomcat embedded mặc định, ta kỳ vọng parser báo lỗi kích thước theo đường Spring MVC để có HTTP 413.

Không gom mọi `MultipartException` thành 413 một cách mù quáng: multipart hỏng, missing boundary, I/O failure hay client đóng kết nối là **các tình huống khác**. Chỉ dùng mã 413 cho dữ liệu vượt giới hạn được xác định; với lỗi parser khác cần chính sách xử lý riêng.

## 7. Test MVC slice với `MockMvc` và `MockMultipartFile`

**`src/test/java/com/example/upload/UploadControllerMvcTest.java`**

~~~java
package com.example.upload;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(UploadController.class)
class UploadControllerMvcTest {

    @Autowired
    private MockMvc mockMvc;

    private static MockMultipartFile textFile(String body) {
        return new MockMultipartFile(
                "file",
                "note.txt",
                MediaType.TEXT_PLAIN_VALUE,
                body.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void validFileAndFormFieldReturnReceipt()
            throws Exception {
        mockMvc.perform(
                multipart("/api/uploads")
                        .file(textFile("hello"))
                        .param("category", "docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.bytes").value(5))
                .andExpect(jsonPath("$.category").value("docs"))
                .andExpect(jsonPath("$.text").value("hello"));
    }

    @Test
    void emptyFileIsRejected() throws Exception {
        mockMvc.perform(
                multipart("/api/uploads")
                        .file(textFile("")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingFilePartIsRejected() throws Exception {
        mockMvc.perform(
                multipart("/api/uploads")
                        .param("category", "docs"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void businessLimitAboveEightBytesReturns413()
            throws Exception {
        // Đây là business guard, KHÔNG phải container limit.
        mockMvc.perform(
                multipart("/api/uploads")
                        .file(textFile("123456789")))
                .andExpect(status().is(413));
    }

    @Test
    void disallowedFileContentTypeReturns415()
            throws Exception {
        MockMultipartFile invalid =
                new MockMultipartFile(
                        "file",
                        "report.bin",
                        MediaType.APPLICATION_OCTET_STREAM_VALUE,
                        new byte[] {1, 2, 3});

        mockMvc.perform(
                multipart("/api/uploads").file(invalid))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void blankCategoryIsRejected() throws Exception {
        mockMvc.perform(
                multipart("/api/uploads")
                        .file(textFile("ok"))
                        .param("category", "   "))
                .andExpect(status().isBadRequest());
    }

    @Test
    void jsonMetadataPartIsDeserialized() throws Exception {
        MockMultipartFile metadata =
                new MockMultipartFile(
                        "metadata",
                        "metadata.json",
                        MediaType.APPLICATION_JSON_VALUE,
                        "{\"category\":\"reports\"}".getBytes(
                                StandardCharsets.UTF_8));

        mockMvc.perform(
                multipart("/api/uploads/with-meta")
                        .file(textFile("abc"))
                        .file(metadata))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.bytes").value(3))
                .andExpect(jsonPath("$.category").value("reports"))
                .andExpect(jsonPath("$.text").value("abc"));
    }

    @Test
    void missingMetadataPartReturns400() throws Exception {
        mockMvc.perform(
                multipart("/api/uploads/with-meta")
                        .file(textFile("abc")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void malformedJsonMetadataReturns400() throws Exception {
        MockMultipartFile metadata =
                new MockMultipartFile(
                        "metadata",
                        "metadata.json",
                        MediaType.APPLICATION_JSON_VALUE,
                        "{not-json}".getBytes(
                                StandardCharsets.UTF_8));

        mockMvc.perform(
                multipart("/api/uploads/with-meta")
                        .file(textFile("abc"))
                        .file(metadata))
                .andExpect(status().isBadRequest());
    }
}
~~~

### Những bài test này chứng minh điều gì?

- **`validFileAndFormFieldReturnReceipt`**: MVC binding nhận file tên part `file`, form field `category` và trả JSON theo hợp đồng.
- **`emptyFileIsRejected`**: `MultipartFile.isEmpty()` được controller xử lý đúng.
- **`missingFilePartIsRejected`**: một part required bị thiếu được MVC argument resolver từ chối; khác với file có part nhưng dữ liệu 0 byte.
- **`businessLimitAboveEightBytesReturns413`**: 9 byte bị **guard trong controller** từ chối, vì business limit chỉ 8 byte. Điều này **không chứng minh** `spring.servlet.multipart.max-file-size` đã được thực thi.
- **`disallowedFileContentTypeReturns415`**: controller kiểm header part, nhưng không bảo đảm nội dung thực sự là text.
- **`blankCategoryIsRejected`**: form field đầu vào không hợp lệ.
- **`jsonMetadataPartIsDeserialized`**: part JSON được Jackson chuyển thành `UploadMetadata` qua `@RequestPart`.
- **`missingMetadataPartReturns400`**: MVC từ chối thiếu part required.
- **`malformedJsonMetadataReturns400`**: JSON không hợp lệ dẫn đến lỗi message conversion, theo xử lý mặc định trả 400.

**Tổng cộng 9 method `@Test` trong class này.** Các test chạy MVC handler trên mock request/response; không có TCP port thật, không ghi file ra disk. Kết quả lỗi được xác minh theo **status**, vì body mặc định cho `ResponseStatusException` và lỗi binding có thể thay đổi theo error handling của ứng dụng.

### Điều rất dễ hiểu sai về `MockMultipartFile`

`MockMultipartFile` là implementation giả của `MultipartFile` dành cho kiểm thử. Nó nhận `byte[]`, tên part, filename và content type rồi làm các giá trị đó có thể truy cập trong handler. `MockMvcRequestBuilders.multipart(...)` dùng `MockMultipartHttpServletRequest` để **giả lập dữ liệu multipart đã được dựng sẵn**.

Vì vậy:

- Một `MockMultipartFile` có 20 MB vẫn có thể đến được controller trong MockMvc dù Boot cấu hình `max-file-size=1MB`.
- Lý do là **không có đường parse multipart/limit enforcement đầy đủ của servlet container thật**, không phải vì property của Boot bị lỗi.
- Muốn kiểm business guard (ví dụ 8 byte) thì MockMvc thích hợp.
- Muốn kiểm container limit thì gửi HTTP multipart **thật** qua embedded server hoặc đường triển khai tương đương.

Nếu chỉ dùng `@AutoConfigureMockMvc` trong `@SpringBootTest` nhưng vẫn gọi `mockMvc.perform(multipart(...))`, bạn vẫn đang gọi MockMvc; việc tải full context **không tự biến request giả thành HTTP thật**.

## 8. Test HTTP integration: kiểm giới hạn do embedded Servlet container áp dụng

Để kiểm `spring.servlet.multipart.max-file-size`, cần chạy ứng dụng với HTTP server và gửi một request multipart thật. Trong ví dụ sau, Spring Boot chạy Tomcat embedded trên cổng ngẫu nhiên, Java 17 `HttpClient` tự tạo raw multipart body có boundary hợp lệ.

**`src/test/java/com/example/upload/UploadHttpIntegrationTest.java`**

~~~java
package com.example.upload;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.web.servlet.MultipartProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.util.unit.DataSize;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = UploadApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.servlet.multipart.max-file-size=4B",
                "spring.servlet.multipart.max-request-size=1KB"
        })
class UploadHttpIntegrationTest {

    private static final String BOUNDARY = "CaseBoundary";

    @LocalServerPort
    private int port;

    @Autowired
    private ObjectMapper mapper;

    @Autowired
    private MultipartProperties multipartProperties;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> sendFile(String text)
            throws Exception {

        byte[] prefix = (
                "--" + BOUNDARY + "\r\n"
                + "Content-Disposition: form-data;"
                + " name=\"file\"; filename=\"note.txt\"\r\n"
                + "Content-Type: text/plain\r\n\r\n"
        ).getBytes(StandardCharsets.UTF_8);

        byte[] payload =
                text.getBytes(StandardCharsets.UTF_8);

        byte[] suffix = (
                "\r\n--" + BOUNDARY + "--\r\n"
        ).getBytes(StandardCharsets.UTF_8);

        byte[] body = new byte[
                prefix.length + payload.length + suffix.length];

        System.arraycopy(
                prefix, 0, body, 0, prefix.length);

        System.arraycopy(
                payload, 0, body, prefix.length, payload.length);

        System.arraycopy(
                suffix, 0, body,
                prefix.length + payload.length,
                suffix.length);

        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/api/uploads");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .header(
                        "Content-Type",
                        "multipart/form-data; boundary=" + BOUNDARY)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void springBindsExplicitMultipartLimits() {
        assertTrue(port > 0);
        assertEquals(
                DataSize.ofBytes(4),
                multipartProperties.getMaxFileSize());
        assertEquals(
                DataSize.ofBytes(1024),
                multipartProperties.getMaxRequestSize());
    }

    @Test
    void realMultipartWithinFileLimitSucceeds()
            throws Exception {

        HttpResponse<String> response = sendFile("abc");

        assertEquals(200, response.statusCode());

        JsonNode json = mapper.readTree(response.body());
        assertEquals(3, json.path("bytes").asLong());
        assertEquals(
                "general",
                json.path("category").asText());
        assertEquals("abc", json.path("text").asText());
    }

    @Test
    void realMultipartAboveContainerLimitReturns413()
            throws Exception {

        // 5B vượt max-file-size=4B; nhưng vẫn dưới
        // business limit=8B, nên controller không là nguyên nhân.
        HttpResponse<String> response = sendFile("abcde");

        assertEquals(413, response.statusCode());
    }
}
~~~

### Cách đọc test HTTP thật

- Test 1 kiểm Boot đã bind **đúng cấu hình 4B và 1KB** vào `MultipartProperties`. Nó chưa chứng minh container thực thi giới hạn, vì vậy cần hai test sau.
- Test 2 gửi 3 byte qua **một HTTP request multipart có boundary hợp lệ**. Servlet container phải parse part, controller nhận `MultipartFile`, response trả 200 và JSON đúng.
- Test 3 gửi 5 byte. Vì 5 > `max-file-size=4B` nhưng 5 < **business limit=8B**, một response HTTP 413 cho thấy request bị chặn **trước hoặc tại tầng multipart của server**, theo đường lỗi được `UploadLimitAdvice` chuyển thành 413.
- `max-request-size=1KB` đủ lớn cho request demo (bao gồm headers của các part và framing). Test chưa có assertion riêng về việc **vượt tổng request size**; phần tiếp theo hướng dẫn cách bổ sung test đó.

Kết quả mong đợi ở trên gắn với **Spring Boot 3.3.5, Tomcat embedded mặc định và error advice của project mẫu**. Khi đổi container, proxy hoặc cấu hình connection-swallow, request quá lớn có thể bị ngắt trước khi controller/advice trả response JSON. Trong trường hợp như vậy, cần xác định **chính sách/HTTP behavior mong muốn** rồi điều chỉnh integration test theo hạ tầng thật; không nên khẳng định 413 là output tuyệt đối của mọi container và mọi proxy.

### Vì sao tự dựng multipart bytes?

Để bài ví dụ chỉ cần Java 17 và dependencies Boot chuẩn. `HttpClient` không tự cung cấp multipart builder cấp cao như một số thư viện khác; phần `prefix/payload/suffix` tạo request đúng boundary và dấu CRLF. Test thực tế có thể dùng RestAssured, Apache HttpClient, `TestRestTemplate` với `MultiValueMap` hoặc một client test khác; điều quyết định là request phải đi qua **HTTP server và parser thật**.

**Không dùng câu `client gửi 5 ký tự` làm bằng chứng số byte** nếu có Unicode: test này dùng chuỗi ASCII, nên 5 ký tự là 5 byte UTF-8. Với dữ liệu Unicode, hãy tạo byte array và kiểm `payload.length` đúng ngưỡng.

## 9. Cách test `max-request-size` riêng với `max-file-size`

Hai giới hạn nên có **hai tình huống kiểm thử khác nhau**, vì một lỗi có thể bị chặn ở file-level trước khi request-level được kích hoạt.

### Chọn case tách biệt

- **Case file-level:** một file có 5 byte, `max-file-size=4B`, `max-request-size=1KB` → vượt giới hạn mỗi file.
- **Case request-level:** mỗi file/part riêng lẻ **dưới `max-file-size`**, nhưng tổng body (kể cả form fields và boundaries) **lớn hơn `max-request-size`** → vượt tổng request.

Để kiểm request-level, có thể tạo một class integration test riêng với cấu hình:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.servlet.multipart.max-file-size=256B",
                "spring.servlet.multipart.max-request-size=180B"
        })
class TotalMultipartSizeLimitExample {
    // Dùng HTTP client multipart thật.
    // Tạo nhiều part nhỏ và xác nhận body tổng > 180 byte.
    // Kiểm response theo mapping của Servlet container/advice.
}
~~~

Đây là **snippet cấu hình minh họa**, không phải class runnable đầy đủ và không nằm trong số 12 method của project. Tùy độ dài tên file, Content-Disposition, boundary và headers, chỉ một part có thể đã chiếm nhiều byte framing. Vì vậy khi viết test cho `max-request-size`:

1. Chủ động dựng body với **nhiều part hoặc metadata đủ lớn** để biết chính xác tổng byte.
2. Kiểm tổng byte body thực tế **lớn hơn giới hạn request**.
3. Kiểm từng file part **không vượt `max-file-size`**.
4. Gửi request qua embedded server thật.
5. Xác minh response/error behavior của hạ tầng được chọn và kết quả nghiệp vụ **không được xử lý thành công**.
6. Đừng tự dùng `MockMvc.multipart(...).file(...).param(...)` để kết luận Servlet `max-request-size` đã được kiểm.

Một ứng dụng có upstream proxy giới hạn request riêng có thể từ chối trước Tomcat. Nếu mục tiêu là hợp đồng public qua gateway, phải chạy test qua đúng gateway/proxy, không chỉ embedded server.

## 10. Giới hạn “quá lớn” ở những tầng nào?

Một upload có thể bị từ chối ở nhiều lớp:

~~~text
Client
  |
  v
CDN / API gateway / reverse proxy
  |-- Giới hạn Content-Length/body, timeout, rate limit
  v
Servlet container multipart parser
  |-- maxFileSize, maxRequestSize, temp disk và parser constraints
  v
Spring MVC/controller/service
  |-- isEmpty, loại nội dung, byte limit nghiệp vụ, owner/ACL
  v
Storage adapter / object store
  |-- quota, antivirus scan, file naming, storage policy
  v
Audit, metadata, cleanup
~~~

HTTP 413 thường biểu thị “Content Too Large/Payload Too Large”, nhưng **không thể suy ra chính xác tầng nào chặn chỉ từ status code**. Khi cần chứng minh container-level, hãy tổ chức case sao cho app business guard **không tự chặn sớm**, như test 5B > 4B nhưng < 8B ở mục 8. Khi cần chứng minh proxy limit, phải gửi qua proxy và kiểm logs/test metadata phù hợp.

### Tại sao giới hạn ở nhiều tầng vẫn hữu ích?

Giới hạn ở proxy có thể chặn sớm trước khi tiêu tốn JVM resources. Giới hạn Servlet bảo vệ tài nguyên parsing/tạm lưu. Giới hạn business bảo vệ chính sách ứng dụng theo loại file, tenant hoặc use case. Quota ở storage bảo vệ dung lượng dài hạn. Chúng **không thay thế nhau**.

Với upload lớn/streaming, không nên để controller đầu tiên đọc toàn bộ file lên RAM mới áp dụng limit. Hãy kiểm kích thước công bố và thực tế bằng stream có bộ đếm, đồng thời dùng giới hạn container/proxy để chặn sớm và cleanup phần đã ghi khi thất bại.

## 11. Lỗi binding và status HTTP cần kiểm

| Tình huống | Hành vi cần kiểm | Mức test |
| --- | --- | --- |
| Part `file` hợp lệ | 2xx + metadata đúng | MockMvc và real HTTP |
| Có part `file` nhưng 0 byte | 400 theo policy demo | MockMvc |
| Không gửi part `file` | MVC báo thiếu part, thường 400 | MockMvc |
| Part name viết sai `document` | Controller đòi `file`, thường 400 | MockMvc |
| File Content-Type không cho phép | 415 theo policy demo | MockMvc |
| Metadata JSON hợp lệ | `@RequestPart` parse đúng DTO | MockMvc |
| Metadata thiếu/bị hỏng | 400 theo MVC/JSON conversion | MockMvc |
| File > business limit 8B | 413 do controller quy định | MockMvc |
| File > servlet max-file-size 4B nhưng < 8B | Bị từ chối trước logic thành công | Real HTTP |
| Tổng multipart > max-request-size | Bị từ chối trước xử lý thành công | Real HTTP |
| Request không phải `multipart/form-data` | 415 khi handler có `consumes` tương ứng | MockMvc/real HTTP |
| Auth không hợp lệ | 401/403 tùy security config | Test có Spring Security thực |
| File tên nguy hiểm/mime giả | Không được tạo đường dẫn tùy ý | Unit/service/storage integration |
| I/O storage hết chỗ/quyền | Không trả success giả, cleanup đúng | Storage/integration |

**Đừng gộp hai lỗi “thiếu file” và “file rỗng”.** Với file rỗng, part có thể vẫn tồn tại và `isEmpty()` là true. Khi thiếu part hoàn toàn, MVC có thể ném `MissingServletRequestPartException` trước khi gọi controller. Hai đường lỗi có thể cùng HTTP 400 nhưng đến từ **hai tầng xử lý khác nhau**.

### 400, 413, 415 có ý nghĩa gì trong bài ví dụ?

- **400 Bad Request:** không đủ input theo contract hoặc file rỗng/metadata/category không hợp lệ.
- **413 Payload Too Large:** vượt business byte limit hoặc Servlet multipart byte limit khi được chuyển thành response này.
- **415 Unsupported Media Type:** file part tự khai báo loại không phù hợp với contract demo.

Tùy ứng dụng, file type không hợp lệ có thể được thiết kế trả 400 hoặc 422; điều quan trọng là **quy ước API rõ ràng và test kiểm nhất quán**. Bài demo chọn 415 cho loại part không chấp nhận.

## 12. Multipart JSON metadata và Bean Validation

Một API upload có thể đính kèm metadata nhiều trường:

~~~json
{
  "category": "reports",
  "description": "Quarterly summary",
  "expiresInDays": 7
}
~~~

Để Spring deserialize vào DTO và kiểm Bean Validation, có thể định nghĩa một Java record:

~~~java
public record DocumentMetadata(
        @NotBlank String category,
        @Size(max = 100) String description,
        @Min(1) @Max(365) int expiresInDays) {
}
~~~

và controller:

~~~java
@PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<Void> upload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    return ResponseEntity.accepted().build();
}
~~~

Hai đoạn này **minh họa một thiết kế mở rộng**, không phải phần của project demo. Để dùng thực tế cần imports `jakarta.validation.*`, thư viện provider như `spring-boot-starter-validation` và code kiểm file/storage. Annotation `@Valid` không kiểm byte size của `MultipartFile` nếu không có constraint hoặc validation custom phù hợp; `@Size` trên field `description` chỉ kiểm trường metadata.

Trong MockMvc test, metadata là **JSON part** có `Content-Type: application/json`, không phải một `param("metadata", "{...}")` được Spring tự động diễn giải thành object mọi lúc. Khi test `@RequestPart`, hãy dùng đúng part tên và media type để thực sự kiểm HttpMessageConverter.

### Validate JSON metadata khác validate file

- DTO: kiểm category, description, số ngày, quan hệ giữa fields.
- File: kiểm byte size, rỗng, extension, MIME header, nội dung thực tế/magic bytes, checksum và policy lưu trữ.
- Request tổng: kiểm số part/file, kích thước tổng, quotas và timeout.
- Actor: kiểm quyền upload/tenant/quota; không coi metadata từ client là nguồn chân lý của quyền truy cập.

Một test chỉ khẳng định `@Valid` trả 400 khi mô tả quá dài **không chứng minh** file scanner hoặc container size limit hoạt động.

## 13. Tên file, đường dẫn và bảo mật upload

`MultipartFile.getOriginalFilename()` là **tên do client cung cấp**. Nó có thể rỗng, chứa đường dẫn tương đối/tuyệt đối, ký tự Unicode, dấu phân cách của nhiều hệ điều hành hoặc chuỗi gây nhầm extension.

**Không nên lưu file bằng lệnh ghép trực tiếp:**

~~~java
// MẪU KHÔNG AN TOÀN: không dùng trong production.
Path destination = uploadDir.resolve(
        multipartFile.getOriginalFilename());
multipartFile.transferTo(destination);
~~~

Nếu filename là `../../config.properties` hoặc có dấu phân cách bất thường, thao tác có thể gây **path traversal** hoặc ghi đè file khác nếu thiếu bảo vệ. Test cần có ca filename độc hại và khẳng định nó **không bao giờ quyết định trực tiếp đường dẫn lưu**.

Chiến lược phổ biến:

1. Server sinh tên lưu mới, ví dụ UUID/random token, **không lấy nguyên client filename làm path**.
2. Lưu metadata filename hiển thị riêng, được chuẩn hóa/escape cho UI, không dùng làm đường dẫn hệ thống.
3. Giới hạn loại file, kích thước, số file/request, quotas theo người dùng và tổ chức.
4. Lưu ngoài webroot hoặc object storage riêng, với quyền truy cập rõ ràng và thời hạn phù hợp.
5. Quét nội dung, dùng magic bytes/file parser khi chính sách yêu cầu, không tin MIME/extension.
6. Ghi xuống vùng tạm/cách ly, chỉ publish tài nguyên khi đã validate/scan và commit metadata thành công.
7. Khi lỗi giữa chừng, dọn file tạm và không trả success.
8. Không log raw file content, token, thông tin cá nhân hoặc path nhạy cảm trong CI.

**MockMvc có thể giúp kiểm filename input và validation logic.** Nhưng các quyền file system, object-store ACL, tính nguyên tử khi ghi và cleanup khi service fail phải kiểm ở tầng storage/integration tương ứng.

### Các dạng “file giả” cần kiểm

- Filename `report.pdf` nhưng content thật không phải PDF.
- MIME `image/png` nhưng bytes không có PNG signature.
- Zip có tỉ lệ giải nén cực lớn (zip bomb).
- File có payload active content, HTML/SVG hoặc macro.
- Filename gồm `..`, path separator, control characters hoặc chuỗi Unicode khó chuẩn hóa.
- Nhiều part cùng tên, trùng filename, part name dài bất thường.
- Multipart thiếu closing boundary hoặc headers hỏng.
- Client đóng kết nối giữa upload, storage hết quota hoặc disk tạm bị đầy.

Không phải mỗi tình huống đều nên viết chung một test controller. Hãy đặt test ở tầng có thể quan sát lỗi thật: parser/container, scanner, storage hoặc API gateway.

## 14. `MockMultipartFile`, `MockPart` và `Part` của Servlet

`MockMultipartFile` phù hợp khi controller nhận `MultipartFile`. Spring MVC cũng hỗ trợ `jakarta.servlet.http.Part` trên Servlet stack. Khi muốn kiểm API nhận `Part`, có thể dùng `MockPart`:

~~~java
MockPart part = new MockPart(
        "file",
        "note.txt",
        "abc".getBytes(StandardCharsets.UTF_8));

part.getHeaders().setContentType(MediaType.TEXT_PLAIN);

mockMvc.perform(
        multipart("/api/uploads/part").part(part))
        .andExpect(status().isOk());
~~~

Đoạn trên chỉ minh họa cách tạo `MockPart` và gửi bằng `multipart(...).part(...)`; endpoint `/api/uploads/part` **không có trong project runnable**, cần tự định nghĩa handler nhận `Part` nếu thực hành. API `MockPart` thuộc Spring Test.

**Khác biệt cần nhớ:**

- `MultipartFile` là abstraction của Spring thuận tiện cho file upload.
- `Part` là API của Jakarta Servlet.
- `MockMultipartFile`/`MockPart` đều là test doubles; chúng không bắt container thật parse raw boundary và áp toàn bộ giới hạn.
- Đừng chọn loại mock chỉ vì test dễ pass. Chọn theo đúng **controller argument type và mục tiêu kiểm chứng**.

## 15. Upload PUT/PATCH và khác biệt container

`MockMvcRequestBuilders.multipart(...)` tạo request multipart mặc định thường là POST; có thể chỉ định HTTP method khác trong API builder khi bài toán cần. Tuy nhiên, **đừng suy ra mọi Servlet container hỗ trợ multipart parsing trên PUT/PATCH giống POST**. Standard Servlet parsing và `StandardServletMultipartResolver` có các giới hạn về media type, method và container implementation; Boot/Spring versions cũng ảnh hưởng.

Với API public upload qua POST, test trước ở đường chuẩn `multipart/form-data`. Nếu nghiệp vụ yêu cầu PUT/PATCH, cần **integration test trên container mục tiêu**, xác minh cả request method, proxy behavior và parser chứ không chỉ sửa method trên MockMvc request.

### Form URL encoded có phải multipart không?

Không. `application/x-www-form-urlencoded` chứa các field được mã hóa trong một body thông thường; nó không truyền file bytes theo cấu trúc multipart với boundary. Khi controller có `consumes = MULTIPART_FORM_DATA_VALUE`, gửi JSON hoặc form URL-encoded vào endpoint đó thường bị từ chối theo content type. Nếu API cần hỗ trợ nhiều kiểu request, thiết kế mapping rõ ràng và viết test riêng từng loại; không nới lỏng `consumes` chỉ để vượt một bài test cấu hình sai.

## 16. Giới hạn file và request trong kiến trúc production

### Tài nguyên bộ nhớ

Đọc toàn bộ file bằng `getBytes()` dễ dùng trong test nhỏ nhưng có thể cấp phát mảng lớn. Với file 100 MB và nhiều request đồng thời, tổng RAM có thể tăng đột ngột. Khi upload lớn, ưu tiên streaming hoặc API chuyển file tới storage với giới hạn, không giữ toàn file trong memory.

### Tài nguyên đĩa tạm

Với `file-size-threshold=0B`, container có thể ghi phần file vào thư mục tạm trong quá trình parse, tùy implementation. Nếu thiếu dung lượng hoặc quyền ghi, request có thể fail trước controller. Test môi trường CI nên đảm bảo thư mục tạm tồn tại, có quyền, dung lượng hợp lý và được dọn theo lifecycle; test MockMvc không tái hiện đầy đủ áp lực disk này.

### Số lượng files/parts và concurrency

Ngay cả khi mỗi file nhỏ hơn ngưỡng, một request có quá nhiều part hoặc một số lượng lớn request đồng thời vẫn tiêu tốn CPU, RAM, file descriptors và disk. Ngoài byte limits, cân nhắc policy về **số file/request, số part, tổng bytes theo tenant, rate limiting, timeout**; thực thi ở tầng phù hợp.

### Reverse proxy có thể từ chối sớm

Một số hệ thống có Nginx/Envoy/CDN/API Gateway với body size limit và request timeout riêng. Nếu proxy giới hạn 2 MB nhưng Boot cho 5 MB, client vẫn có thể nhận 413 từ proxy trước khi controller thấy request. Test chỉ chạy trực tiếp `localhost:<random-port>` không kiểm được hành vi proxy; một deployment E2E test cần gọi đúng entrypoint public/private theo hợp đồng.

### Status response cho request quá lớn

Spring có exception như `MaxUploadSizeExceededException` ở tầng multipart. Tuy nhiên, một số server/proxy có thể đóng kết nối, trả error page riêng hoặc dùng 413 không đi qua `@ControllerAdvice`. Để tránh test quá phụ thuộc implementation, cần định nghĩa **phạm vi kỳ vọng**:

- Trong demo Tomcat embedded: advice xử lý exception size → kỳ vọng HTTP 413.
- Qua proxy: nếu policy cần response JSON chuẩn, phải cấu hình proxy hoặc gateway đưa thông điệp phù hợp; controller không thể tự đảm bảo body JSON cho request bị chặn từ trước.
- Nếu client chỉ nhận IOException/connection reset vì body bị từ chối rất sớm, hãy chẩn đoán hạ tầng trước khi kết luận business validation sai.
- Không coi “HTTP request thất bại” là đủ: phải phân biệt fail do **vượt giới hạn chủ đích** với fail do timeout hoặc server crash.

## 17. Chạy project và đọc kết quả

Tại thư mục có `settings.gradle`/`build.gradle` và Gradle Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng MVC slice:

~~~bash
./gradlew test --tests 'com.example.upload.UploadControllerMvcTest'
~~~

Chạy riêng HTTP integration:

~~~bash
./gradlew test --tests 'com.example.upload.UploadHttpIntegrationTest'
~~~

Với project đầy đủ như mục 6–8, dự kiến **9 + 3 = 12 lượt JUnit `@Test`**. Các test không gọi `System.out.println`, nên **không có stdout nghiệp vụ cố định**; Gradle có thể hiển thị `BUILD SUCCESSFUL` nếu mọi task thành công, hoặc hiển thị `UP-TO-DATE` khi tái sử dụng kết quả.

Xem báo cáo:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.upload.UploadControllerMvcTest.xml
    └── TEST-com.example.upload.UploadHttpIntegrationTest.xml
~~~

Với multi-project build, các thư mục nằm dưới `build` của module chứa test. Khi cần chạy lại để điều tra thay vì dùng kết quả cache:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu project chưa có Wrapper, dùng Gradle đã cài và phiên bản tương thích để tạo Wrapper; với demo Java 17/Spring Boot 3.3.x, ví dụ:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó commit script và `gradle-wrapper.jar`/`gradle-wrapper.properties` theo quy trình repository. Trong dự án thật, ưu tiên Wrapper sẵn có thay vì tự nâng version vì bài demo.

### Gửi HTTP thủ công bằng cURL để đối chiếu

Khi ứng dụng demo chạy thật bằng:

~~~bash
./gradlew bootRun
~~~

với cấu hình mặc định (không bật test property 4B), có thể gọi:

~~~bash
curl -i \
  -F "file=@note.txt;type=text/plain" \
  -F "category=docs" \
  http://127.0.0.1:8080/api/uploads
~~~

Lệnh giả định bạn đã có tệp `note.txt` chứa **1–8 byte** và ứng dụng đang lắng nghe trên port 8080. Nếu chưa tạo file hoặc đã đổi `server.port`, phải thay đúng input/port. Cấu hình của `@SpringBootTest(properties=...)` trong class test **không tự áp dụng cho `bootRun`**; đó là hai context khác nhau. Với `note.txt` dài quá 8 byte, controller sẽ trả 413 theo business limit.

Ví dụ gọi part JSON:

~~~bash
curl -i \
  -F 'file=@note.txt;type=text/plain' \
  -F 'metadata={"category":"reports"};type=application/json' \
  http://127.0.0.1:8080/api/uploads/with-meta
~~~

Cú pháp quote ở Linux/macOS shell khác Windows PowerShell/cmd. Khi test đang tự tạo random port, không dùng 8080 cố định; lấy port từ `@LocalServerPort` hoặc log/test context.

## 18. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa đúng |
| --- | --- | --- |
| 415 dù file có MIME đúng | Request thiếu `multipart/form-data` hoặc `consumes` không khớp | Kiểm **request Content-Type** và part Content-Type riêng |
| 400 `Required part 'file' is not present` | Sai tên part hoặc không gửi file | Gửi `name="file"` đúng như `@RequestParam("file")` |
| 400 với `@RequestPart` metadata | JSON part thiếu, sai media type, JSON sai cấu trúc | Dùng part `metadata` có `application/json`, DTO đúng |
| MockMvc test file lớn vẫn 200 | Request giả không qua container multipart parser/limit | Test business guard hoặc thêm real HTTP test |
| MockMvc 413 nhưng runtime vẫn nhận file lớn | Controller guard và Servlet maxFileSize là hai chính sách khác nhau | Kiểm property thực tế và real HTTP parser |
| `MaxUploadSizeExceededException` | File hoặc request vượt giới hạn | Kiểm chính sách, đối chiếu kích thước byte; map lỗi 413 khi phù hợp |
| 413 xuất hiện trước controller/advice | Proxy hoặc container từ chối sớm | Kiểm proxy logs, server limits và route thực tế |
| `Connection reset` khi gửi file lớn | Server/proxy đóng kết nối khi còn body chưa đọc | Kiểm network/container, max swallow/timeout và policy error |
| File 1 MB vẫn bị từ chối | Khác cách tính MB/B, multipart overhead hoặc max-request-size | Dùng kích thước byte chính xác và test boundary |
| Upload nhiều file tổng vượt limit | `max-request-size` nhỏ hơn tổng part data + framing | Tính/tạo payload toàn request và kiểm request-level |
| Lỗi disk temp/quyền | Container cần ghi file tạm, directory không phù hợp | Cấu hình `location`/quyền/dung lượng, dọn temp |
| Test chạy local nhưng CI thất bại | Port/hostname, temp disk, timeout, parallel tests | Dùng RANDOM_PORT, fixture, resource limit và cleanup |
| Test download lại file sai tên | Dùng original filename làm storage key/path | Sinh server-side storage id, metadata tách biệt |
| File MIME giả lọt qua | Chỉ tin header/extension do client gửi | Dùng content sniffing/parser/scanner phù hợp |
| Test đếm ký tự thay byte | Unicode UTF-8 có độ dài byte khác Java char | Dùng `file.getSize()` và byte array thật |
| Upload sai size nhưng HTTP 200 | Business validator chưa kiểm hoặc parse/config sai tầng | Viết assertion vi phạm chính sách tại tầng liên quan |
| GET endpoint upload trả 405 | Controller chỉ khai báo POST | Dùng đúng HTTP method và `multipart(...)` phù hợp |
| Test bảo mật nhận 401/403 | Security filter/CSRF yêu cầu auth/token | Dùng security test fixture/credentials; không tắt bảo mật vô cớ |
| Test fail vì file system state | Trùng tên/đường dẫn, không dọn dữ liệu cũ | Storage fixture độc lập, cleanup sau test |

### Cách debug theo thứ tự

1. **Kiểm HTTP method và Content-Type của request.** Với `consumes=multipart/form-data`, đừng gửi raw JSON.
2. **Kiểm part names và headers.** `file`, `metadata`, Content-Type từng part phải đúng; đọc request log đã được sanitize.
3. **Xác định lỗi xảy ra trước hay sau controller.** Nếu business guard không được gọi, xem parser, proxy, size limits và security.
4. **Kiểm byte size thật** của file, và tổng request size. Đừng chỉ đọc tên file hoặc số ký tự.
5. **Kiểm cấu hình được bind** qua `MultipartProperties`, log cấu hình không nhạy cảm và integration test.
6. **Kiểm container/proxy.** Một 413 của Nginx không giống exception được controller advice xử lý.
7. **Đọc root cause** của `MultipartException`, I/O exception hoặc HTTP error; đừng đổi status kỳ vọng chỉ để test xanh.
8. **Đặt test đúng tầng.** MockMvc để kiểm MVC/logic, HTTP integration để kiểm parser/limits, storage integration để kiểm persistence.

## 19. Bài tập tự luyện

**Bài A — file rỗng và part thiếu:** Chạy hai test `emptyFileIsRejected` và `missingFilePartIsRejected`. Giải thích vì sao cùng status 400 nhưng một case đã có `MultipartFile` rỗng, case kia bị MVC argument resolution chặn.

**Bài B — boundary business limit:** Gửi file 8 byte và 9 byte bằng MockMvc. Với code demo, 8 byte hợp lệ (nếu MIME là text/plain và category hợp lệ), 9 byte trả 413. Giải thích vì sao điều này **chưa kiểm** `max-file-size` của container.

**Bài C — boundary Servlet limit:** Giữ `spring.servlet.multipart.max-file-size=4B` trong HTTP integration. Gửi file 4 byte và 5 byte với request body hợp lệ. Kỳ vọng 4 byte qua container, 5 byte bị chặn. Kiểm controller business limit 8 byte để chứng minh 5 byte không vượt business threshold.

**Bài D — request tổng:** Chọn `max-file-size` đủ lớn cho từng part, đặt `max-request-size` nhỏ hơn tổng raw multipart body gồm field/file/boundary. Dùng real HTTP test và giải thích tại sao chỉ kiểm `sum(file.getSize())` có thể bỏ qua framing và fields.

**Bài E — JSON part:** Đổi `metadata` từ `application/json` thành `text/plain` khi controller nhận `UploadMetadata`. Quan sát lỗi conversion hoặc 415 tùy MVC configuration; sửa client Content-Type của **part**, không đổi Content-Type request thành JSON.

**Bài F — nhiều file:** Thêm endpoint nhận `List<MultipartFile>`. Viết tests cho không có file, một file, quá số lượng file và tổng byte lớn. Nêu rõ trường hợp nào thuộc controller business limit, trường hợp nào thuộc Servlet request limit.

**Bài G — tên file độc hại:** Test originalFilename là `../../secret.txt`. Viết storage abstraction sinh ID mới và verify path lưu không chứa chuỗi do client điều khiển. Không tạo file thật ngoài test temp directory khi thực hành.

**Bài H — lỗi lưu file:** Mô phỏng storage adapter hết quota hoặc ném IOException sau khi đã tạo file tạm. Kiểm API không trả success và cleanup đúng; xác định phần này nên dùng mock/fake và phần nào phải integration test với storage thật.

## 20. Checklist dành cho test upload Spring MVC

- [ ] Controller phân biệt `@RequestParam` form/file và `@RequestPart` JSON metadata?
- [ ] HTTP request có `multipart/form-data` và boundary; các part có tên, media type phù hợp?
- [ ] Test có case **file rỗng** lẫn **file part thiếu**, không gộp chúng?
- [ ] Test có xác minh byte size, file type, field validation và error status đúng contract?
- [ ] Tôi không coi `MockMultipartFile` là bằng chứng Servlet parser/file-size limit đã được kiểm?
- [ ] Tôi đã cấu hình `max-file-size` và `max-request-size` cho môi trường test có mục đích, không dùng giá trị production nguy hiểm?
- [ ] Tôi có **real HTTP integration test** cho các giới hạn phụ thuộc container khi đó là yêu cầu?
- [ ] `file-size-threshold` được hiểu là ngưỡng spill-to-disk, **không phải ngưỡng từ chối**?
- [ ] Test độ lớn dùng **byte**, không dùng số ký tự hay tự đo từ filename?
- [ ] Nếu có proxy/gateway, tôi biết giới hạn của proxy và của Boot là hai tầng?
- [ ] Tôi không tin originalFilename, MIME header hoặc extension của client như dữ liệu an toàn?
- [ ] Nội dung file lớn được xử lý streaming/bounded và có quota, scan, cleanup phù hợp?
- [ ] Test có bảo vệ trường hợp lỗi storage, thiếu quyền, thiếu temp disk và concurrency khi nghiệp vụ yêu cầu?
- [ ] Gradle/JUnit report xác nhận test thực thi, không chỉ task `UP-TO-DATE`?
- [ ] Mọi fixture/tệp thử nghiệm đều an toàn, không ghi đè file hay dữ liệu production?

## 21. Tài liệu tham khảo chính thức

Các nguồn sau giúp kiểm lại behavior với đúng dependency của dự án. Project demo dùng **Spring Boot 3.3.5/Spring Framework 6.1.x**, nên khi nâng version hoặc đổi Servlet container cần kiểm lại API/config theo phiên bản:

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.servlet.multipart.max-file-size`, `max-request-size`, `file-size-threshold`, `resolve-lazily`.
- [Spring Boot — Handling Multipart File Uploads](https://docs.spring.io/spring-boot/3.3/how-to/spring-mvc.html): cách Boot dùng Servlet `Part` API và cấu hình upload limits.
- [Spring Framework — Multipart Controller Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): `@RequestParam`, `@RequestPart`, `MultipartFile`, JSON metadata và validation.
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): `StandardServletMultipartResolver` và parser của container.
- [Spring Framework — MockMvc Performing Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): `multipart(...)` dùng mock request, không parse multipart request thật.
- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): phạm vi test MVC không cần server đang lắng nghe.

**Ghi nhớ:** `MockMvc.multipart(...)` giúp kiểm **Spring MVC binding và logic controller**, nhưng không tự chứng minh **kích thước upload do Servlet container áp dụng**. Cần phân biệt `max-file-size`, `max-request-size`, giới hạn nghiệp vụ và giới hạn gateway/proxy. Để một bài test upload đáng tin, hãy chọn đúng tầng, kiểm cả phản hồi thành công/lỗi, dùng dữ liệu byte xác định và có bảo vệ an toàn cho storage.
