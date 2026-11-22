# MultipartFile, form multipart và trường bị thiếu trong Spring MVC

## 1. Mục tiêu và tình huống thực tế

Một form HTML gửi tên tài liệu và tệp đính kèm có thể trông rất đơn giản:

```html
<form action="/api/uploads/form"
      method="post"
      enctype="multipart/form-data">
  <label>Tiêu đề:
    <input type="text" name="title">
  </label>
  <label>Tệp:
    <input type="file" name="file">
  </label>
  <button type="submit">Gửi</button>
</form>
```

Nhưng ở phía Spring MVC, các tình huống sau **khác nhau**:

1. Client không gửi trường `title`.
2. Client gửi `title` với chuỗi rỗng `""` hoặc toàn khoảng trắng.
3. Client không gửi part tên `file`.
4. Client gửi part `file` nhưng không chọn tệp hoặc gửi một tệp có kích thước 0 byte.
5. Client gửi tệp hợp lệ nhưng đặt tên part là `attachment` thay vì `file`.
6. Client gửi JSON thuần với `Content-Type: application/json` thay cho form multipart.
7. Client gửi part metadata JSON, tệp upload, rồi muốn áp Jakarta Validation lên metadata.

Nếu gộp tất cả thành “trường bị thiếu”, ứng dụng dễ trả sai lỗi, xử lý `null` không an toàn hoặc chấp nhận một tệp rỗng dù nghiệp vụ yêu cầu tệp có nội dung.

**Mục tiêu bài học:** nắm cơ chế `multipart/form-data` và `MultipartFile`, chọn `@RequestParam`, `@RequestPart` hoặc `@ModelAttribute` phù hợp, phân biệt **missing**, **present-but-empty** và **invalid**, dùng `BindingResult`/`@Valid`, kiểm thử chính xác các nhánh đó bằng Spring MVC `MockMvc`.

Phạm vi chính là **Spring MVC Servlet stack** (Spring Framework 6.x và Spring Boot 3.x với Java 17+). Spring WebFlux dùng các API khác như `FilePart`; không áp nguyên xi ví dụ `MultipartFile` vào endpoint reactive.

## 2. HTTP `multipart/form-data` thực chất là gì?

Một request có header tương tự:

```http
POST /api/uploads/required HTTP/1.1
Content-Type: multipart/form-data; boundary=example-boundary
```

Phần thân gồm nhiều *part*, mỗi part có các header riêng và nội dung riêng. Ví dụ đơn giản hóa:

```http
--example-boundary
Content-Disposition: form-data; name="title"

Report
--example-boundary
Content-Disposition: form-data; name="file"; filename="report.txt"
Content-Type: text/plain

abc
--example-boundary--
```

Trong đó:
- `title` là một **form field**.
- `file` là **file part** với tên form field `file` và tên tệp do client khai báo `report.txt`.
- `boundary` cho phép parser xác định phần nào thuộc trường nào.
- Nội dung thật có thể là dữ liệu nhị phân; ví dụ trên chỉ minh họa cấu trúc.

**Tên part phải khớp.** Nếu controller khai báo `@RequestParam("file")`, một part có `name="attachment"` không được coi là part `file`.

Trình duyệt và thư viện HTTP thường tự tạo boundary. Khi dùng `FormData` trong JavaScript hoặc `curl -F`, **không tự đặt thủ công** `Content-Type: multipart/form-data` mà bỏ quên boundary; để client tự tạo đầy đủ header.

Khác với `application/x-www-form-urlencoded`, multipart có thể chứa file bytes, nhiều part cùng tên, hoặc một part JSON được đánh dấu `Content-Type: application/json` để Spring dùng message converter.

## 3. Đường đi multipart trong Spring MVC

Về mặt khái niệm:

```text
HTTP POST multipart/form-data
           |
           v
Servlet container + multipart config
           |
           v
MultipartResolver / Servlet part parsing
           |
           v
DispatcherServlet
           |
       Handler method
    /       |        \
@RequestParam @RequestPart @ModelAttribute
    |         |          |
form/file  part +      WebDataBinder
values     converter   form object + files
           |
         validation nếu được kích hoạt
           |
           v
        Controller
```

Spring MVC có chiến lược `MultipartResolver`; với Servlet stack hiện đại, `StandardServletMultipartResolver` dùng khả năng parse multipart của Servlet container. Spring Boot thường tự cấu hình multipart support khi dùng `spring-boot-starter-web` và cấu hình mặc định, còn Spring Framework thuần cần thiết lập resolver/Servlet multipart configuration thích hợp.

Khi một phần bắt buộc vắng mặt, lỗi có thể xuất hiện ở **khâu resolve argument trước khi gọi controller**. Trái lại, nếu một `MultipartFile` đã được bind nhưng `isEmpty() == true`, controller vẫn có thể được gọi và bạn phải kiểm tra nghiệp vụ.

Đừng nhầm ba giai đoạn:
- **Parsing:** Đọc và phân tách request theo boundary; có thể lỗi nếu request sai định dạng, vượt hạn mức.
- **Binding:** Gán `title` và `file` vào tham số phương thức hoặc DTO.
- **Validation:** Kiểm tra `@NotBlank`, ràng buộc nghiệp vụ “file không rỗng”, kích thước/định dạng cho phép.

## 4. Giao diện `MultipartFile`

`MultipartFile` thuộc package `org.springframework.web.multipart`. Các phương thức thường dùng:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getName()` | **Tên field/part** trong form, ví dụ `file` | Dùng để đối chiếu binding; không phải tên tệp thực |
| `getOriginalFilename()` | Tên tệp do client khai báo | Có thể `null`/rỗng; **không đáng tin** để dùng trực tiếp làm đường dẫn lưu |
| `getContentType()` | Content type do client cung cấp, có thể `null` | Không coi đây là bằng chứng chắc chắn về loại file |
| `isEmpty()` | `true` nếu không chọn tệp hoặc nội dung upload rỗng | Không phân biệt chắc chắn “không chọn” với “tệp 0 byte” |
| `getSize()` | Số byte của tệp, kiểu `long` | `0` với file rỗng |
| `getInputStream()` | Đọc nội dung qua stream | Thích hợp xử lý tệp lớn mà không giữ toàn bộ bytes trong heap |
| `getBytes()` | Đọc toàn bộ bytes vào `byte[]` | Cẩn trọng với tệp lớn, tốn bộ nhớ |
| `transferTo(...)` | Chuyển/copy file upload tới đích lưu | Kiểm soát đường dẫn, tên do server tạo, quyền truy cập và lỗi I/O |

**Đặc biệt quan trọng:**
- `file == null` là **không có đối tượng MultipartFile được bind** ở vị trí đó.
- `file != null && file.isEmpty()` nghĩa là **có đối tượng** nhưng nội dung được xem là rỗng. Tùy client/browser/Servlet container, việc không chọn tệp có thể tạo part rỗng hoặc không gửi part; đừng giả định có đúng một hành vi cho mọi client.
- `file != null && !file.isEmpty()` chứng minh có byte nội dung, **không chứng minh** nội dung an toàn hay đúng định dạng.

Dữ liệu multipart thường có tài nguyên tạm theo vòng đời request. Nếu phải dùng tệp sau khi HTTP request kết thúc, hãy lưu/copy nội dung tới vị trí được kiểm soát trong khi request còn hiệu lực.

## 5. Ba cách nhận multipart ở controller

### 5.1. `@RequestParam`: form field và file part đơn giản

```java
@PostMapping(path = "/required",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @RequestParam("title") String title,
        @RequestParam("file") MultipartFile file) {
    // ...
}
```

`@RequestParam` thích hợp cho cặp `title`/`file` đơn giản. Với tham số mặc định `required = true`:
- Không có `title` thường dẫn tới lỗi thiếu request parameter trước khi vào body.
- Không có part `file` thường dẫn tới lỗi thiếu request part.
- `title=""` vẫn có thể **được bind** nhưng chưa đạt `@NotBlank` nếu bạn kích hoạt validation hoặc kiểm tra thủ công.
- Part `file` tồn tại với 0 byte có thể được bind thành `MultipartFile` nhưng `isEmpty()` là `true`. `required=true` chủ yếu yêu cầu **part tồn tại**, không thay cho kiểm tra kích thước.

Tên trường trong HTML, `curl -F` hoặc JavaScript `FormData.append(name, ...)` phải khớp chính xác các tên `title` và `file` này.

### 5.2. `@RequestPart`: file và part có dữ liệu cần chuyển đổi

`@RequestPart` cũng có thể nhận `MultipartFile`, nhưng đặc biệt hữu ích khi có part JSON:

```java
public record Metadata(@NotBlank String label) {}

@PostMapping(path = "/metadata",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> uploadWithMetadata(
        @Valid @RequestPart("metadata") Metadata metadata,
        @RequestPart("file") MultipartFile file) {
    // ...
}
```

Nếu part `metadata` có `Content-Type: application/json` và body `{"label":"Report"}`, Spring dùng `HttpMessageConverter` (thường là Jackson) để chuyển JSON thành `Metadata`. `@Valid` kích hoạt Bean Validation cho object đã được chuyển đổi; JSON sai cú pháp hoặc content type không phù hợp có thể gây lỗi **trước** khi vào controller.

`@RequestPart("file") MultipartFile file` và `@RequestParam("file") MultipartFile file` đều hợp lệ cho file. Sự khác biệt quan trọng nổi lên với **object part**: `@RequestPart` dựa vào content type của *từng part* để đọc bằng message converter, trong khi `@RequestParam` thiên về tham số và type conversion thông thường.

### 5.3. `@ModelAttribute`: bind form vào DTO

Khi form có nhiều trường:

```java
public class UploadForm {

    @NotBlank(message = "title.blank")
    private String title;

    private MultipartFile file;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public MultipartFile getFile() { return file; }
    public void setFile(MultipartFile file) { this.file = file; }
}
```

Controller:

```java
@PostMapping(path = "/form",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> form(
        @Valid @ModelAttribute UploadForm form,
        BindingResult errors) {
    // ...
}
```

Spring `WebDataBinder` gán các form fields/files tương ứng vào DTO. `@Valid` chạy các constraint có hỗ trợ, ví dụ `@NotBlank` cho title. `BindingResult` phải đặt **ngay sau** argument `@ModelAttribute` được validate nếu bạn muốn xử lý lỗi locally.

Trong DTO mới được bind, nếu field `file` không có trong request, thường `form.getFile() == null`; nếu nhận part rỗng thì `form.getFile().isEmpty()` là `true`. Đừng sử dụng `form.getFile().isEmpty()` mà chưa xét `null`.

### 5.4. Chọn API theo dạng dữ liệu

| Client gửi | Khai báo phù hợp | Vì sao |
| --- | --- | --- |
| Text field + một file | `@RequestParam String` + `@RequestParam MultipartFile` | Rõ ràng, gọn |
| Form nhiều field + file + kiểm tra DTO | `@Valid @ModelAttribute UploadForm` | `WebDataBinder` tạo object form |
| Metadata là part JSON + file | `@Valid @RequestPart Metadata` + `@RequestPart MultipartFile` | `HttpMessageConverter` đọc JSON part |
| Nhiều file dưới cùng field name | `@RequestParam("files") List<MultipartFile>` | Lấy nhiều file cùng tên |
| Cần upload optional | `required=false` hoặc `Optional<MultipartFile>` theo argument resolver | Phân biệt vắng part và có part nhưng rỗng |

**Tránh dùng `@RequestBody UploadForm` để đọc cả một request `multipart/form-data` như JSON thuần.** `@RequestBody` đọc request body theo message converter; với multipart, chọn `@RequestPart` cho JSON part hoặc `@ModelAttribute` cho form fields.

## 6. Trường bị thiếu, trường rỗng và file 0 byte

### 6.1. Bảng đối chiếu trạng thái

| Dữ liệu đầu vào | `@RequestParam(required=true)` / `@RequestPart(required=true)` | `required=false` / DTO mới |
| --- | --- | --- |
| Không gửi field `title` | Thường trả **400** do thiếu request parameter | `String` có thể `null`; `@NotBlank` trên DTO sẽ phát hiện nếu có `@Valid` |
| Gửi `title=""` | Argument thường được bind; tự kiểm tra blank/validation | Chuỗi rỗng có thể vẫn được bind |
| Gửi `title="   "` | Vẫn có parameter; `@NotBlank` mới chặn toàn khoảng trắng | `isBlank()`/`@NotBlank` mới chặn |
| Không có part tên `file` | Thường **400** do thiếu request part | `MultipartFile` có thể `null` |
| Có part `file`, nội dung 0 byte | Có thể bind được; `file.isEmpty() == true` | Có đối tượng nhưng `isEmpty() == true` |
| Chỉ gửi `attachment` nhưng controller cần `file` | Tương đương **thiếu part file** | `file` không được bind |
| Gửi part file có nội dung | Có đối tượng `MultipartFile`, `isEmpty() == false` | Tương tự |

Bảng mô tả luồng Spring MVC Servlet thông thường; cách client mã hóa một input HTML chưa chọn file có thể khác giữa client. Phân biệt **không có part** với **part rỗng** dựa trên request thực tế và test, không chỉ dựa vào HTML.

### 6.2. `required=false` chỉ bỏ yêu cầu có mặt

```java
@PostMapping(path = "/optional",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Map<String, String> optional(
        @RequestParam(name = "title", required = false) String title,
        @RequestPart(name = "file", required = false) MultipartFile file) {

    String titleState =
            title == null ? "missing"
            : title.isBlank() ? "blank" : "present";

    String fileState =
            file == null ? "missing"
            : file.isEmpty() ? "empty" : "present";

    return Map.of("titleState", titleState, "fileState", fileState);
}
```

Đây là **đoạn minh họa** của một handler, không phải toàn bộ ứng dụng. Khi dùng `required=false`, controller được quyền tự quyết phần nào bắt buộc theo nghiệp vụ và có thể trả lỗi riêng cho từng trạng thái. Nếu không muốn nhận file rỗng, phải kiểm tra `isEmpty()` dù `required=true` hay `required=false`.

Với form HTML, trường văn bản **có tên nhưng rỗng** khác trường **không tồn tại**. Ví dụ:
- `<input name="title" value="">` có thể gửi `title=""`.
- Không có control gửi trường `title` thì không có parameter ấy.
- Input file không chọn có thể được biểu diễn thành part với tên file rỗng và 0 byte, hoặc bị bỏ qua tùy client.

### 6.3. Kiểm tra nghiệp vụ cho file

Một cách rõ ràng là:

```java
if (file == null) {
    // File part không được bind.
    return ResponseEntity.badRequest()
            .body(Map.of("error", "file.missing"));
}
if (file.isEmpty()) {
    // File part có mặt nhưng không có nội dung.
    return ResponseEntity.badRequest()
            .body(Map.of("error", "file.empty"));
}
```

Đây là fragment cho một controller có biến `file` và các import Spring/Java collections. Với `@RequestParam(required=true)`, nhánh `file == null` thường không được vào tới controller vì Spring đã báo thiếu part; nhánh này hữu ích với optional binding hoặc DTO.

**Không dùng `@NotBlank MultipartFile file`:** `@NotBlank` dành cho `CharSequence`, không có validator chuẩn cho `MultipartFile`. `@NotNull` chỉ bắt null, không bắt file 0 byte. Các annotation như `@NotEmpty` không tự trở thành constraint cho `MultipartFile` nếu provider không có validator phù hợp. Muốn kiểm tra “có tệp thực và có byte”, dùng `isEmpty()` hoặc tự viết constraint validator cho `MultipartFile`.

## 7. Ví dụ Spring Boot 3.5.6 + Java 17 chạy được

Dự án nhỏ này có bốn endpoint:
- `POST /api/uploads/required`: field và file bắt buộc; kiểm tra chuỗi rỗng và file rỗng.
- `POST /api/uploads/optional`: trả về trạng thái missing/empty/present.
- `POST /api/uploads/form`: bind vào DTO qua `@ModelAttribute` và xử lý `BindingResult`.
- `POST /api/uploads/metadata`: part JSON (có `@Valid`) và part file.

Ứng dụng **không lưu dữ liệu upload lên đĩa**, chỉ kiểm tra và trả về số byte. Khi cần lưu file thật, phải bổ sung quy tắc về loại tệp, giới hạn dung lượng, nơi lưu, quyền truy cập và quét nội dung.

Cấu trúc:

```text
multipart-demo/
├── pom.xml
├── src/main/java/demo/upload/
│   ├── UploadApplication.java
│   ├── UploadForm.java
│   └── UploadController.java
└── src/test/java/demo/upload/
    └── UploadControllerTest.java
```

### 7.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>multipart-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

Dùng starter validation để `@Valid`/`@NotBlank` thực sự được provider xử lý. `spring-boot-starter-web` mang vào Spring MVC và embedded Servlet container.

### 7.2. `UploadApplication.java`

```java
package demo.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UploadApplication {

    public static void main(String[] args) {
        SpringApplication.run(UploadApplication.class, args);
    }
}
```

### 7.3. `UploadForm.java`

```java
package demo.upload;

import jakarta.validation.constraints.NotBlank;
import org.springframework.web.multipart.MultipartFile;

public class UploadForm {

    @NotBlank(message = "title.blank")
    private String title;

    private MultipartFile file;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public MultipartFile getFile() {
        return file;
    }

    public void setFile(MultipartFile file) {
        this.file = file;
    }
}
```

Không gắn `@NotBlank` cho `file`: đây không phải chuỗi. Chương trình cố ý phân biệt null và rỗng trong controller.

### 7.4. `UploadController.java`

```java
package demo.upload;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    public record Metadata(@NotBlank String label) {}

    @PostMapping(
        path = "/required",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<Map<String, Object>> required(
            @RequestParam("title") String title,
            @RequestParam("file") MultipartFile file) {

        if (title.isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "title.blank"));
        }
        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "file.empty"));
        }

        return ResponseEntity.ok(
                Map.of("title", title, "bytes", file.getSize()));
    }

    @PostMapping(
        path = "/optional",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public Map<String, String> optional(
            @RequestParam(name = "title", required = false)
            String title,
            @RequestPart(name = "file", required = false)
            MultipartFile file) {

        String titleState = title == null
                ? "missing"
                : title.isBlank() ? "blank" : "present";

        String fileState = file == null
                ? "missing"
                : file.isEmpty() ? "empty" : "present";

        return Map.of(
                "titleState", titleState,
                "fileState", fileState);
    }

    @PostMapping(
        path = "/form",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<Map<String, Object>> form(
            @Valid @ModelAttribute UploadForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "title.blank"));
        }

        if (form.getFile() == null) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "file.missing"));
        }

        if (form.getFile().isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "file.empty"));
        }

        return ResponseEntity.ok(Map.of(
                "title", form.getTitle(),
                "bytes", form.getFile().getSize()));
    }

    @PostMapping(
        path = "/metadata",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<Map<String, Object>> metadata(
            @Valid @RequestPart("metadata") Metadata metadata,
            @RequestPart("file") MultipartFile file) {

        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "file.empty"));
        }

        return ResponseEntity.ok(Map.of(
                "label", metadata.label(),
                "bytes", file.getSize()));
    }
}
```

**Giải thích quan trọng:**
- Với `required()`, Spring xử lý lỗi part/parameter **vắng mặt** trước khi gọi handler. Các nhánh `isBlank()` và `isEmpty()` xử lý dữ liệu **có mặt nhưng không đạt nghiệp vụ**.
- Với `optional()`, handler được gọi cả khi thiếu `file`; trả về `missing` nếu `file == null` và `empty` nếu part rỗng.
- `form()` cho thấy cách `WebDataBinder` đưa giá trị vào DTO. `BindingResult` nằm **ngay sau** `@ModelAttribute`. Vì ví dụ chỉ đặt constraint `@NotBlank` lên `title`, code trả `title.blank` khi có lỗi binding/validation. Dự án thật nên duyệt `FieldError` để trả đúng mã lỗi của từng trường.
- `metadata()` dùng converter đọc part JSON để thành `Metadata` và `@Valid` kiểm tra `label`. Đừng gửi part metadata dưới dạng text/plain nếu muốn nó được parse như JSON.
- Không endpoint nào lưu tệp hoặc tin `getOriginalFilename()` là đường dẫn hợp lệ.

## 8. Kiểm tra các trường hợp bằng MockMvc

`MockMvc` mô phỏng việc request đi qua Spring MVC mà không cần khởi động server trên một cổng mạng. Dùng `MockMultipartFile` để kiểm soát chính xác **part có mặt hay vắng mặt**, và kích thước payload là 0 hay lớn hơn 0.

### 8.1. `UploadControllerTest.java`

```java
package demo.upload;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UploadControllerTest {

    @Autowired
    private MockMvc mvc;

    private static MockMultipartFile validFile() {
        return new MockMultipartFile(
                "file", "report.txt", "text/plain",
                "abc".getBytes(StandardCharsets.UTF_8));
    }

    private static MockMultipartFile emptyFile() {
        return new MockMultipartFile(
                "file", "empty.txt", "text/plain", new byte[0]);
    }

    @Test
    void requiredWithFileAndTitleSucceeds() throws Exception {
        mvc.perform(multipart("/api/uploads/required")
                        .file(validFile())
                        .param("title", "Report"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Report"))
                .andExpect(jsonPath("$.bytes").value(3));
    }

    @Test
    void missingRequiredFileIsBadRequest() throws Exception {
        mvc.perform(multipart("/api/uploads/required")
                        .param("title", "Report"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredTitleIsBadRequest() throws Exception {
        mvc.perform(multipart("/api/uploads/required")
                        .file(validFile()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void emptyRequiredFileReachesBusinessCheck() throws Exception {
        mvc.perform(multipart("/api/uploads/required")
                        .file(emptyFile())
                        .param("title", "Report"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("file.empty"));
    }

    @Test
    void optionalMissingFileAndTitleAreVisible() throws Exception {
        mvc.perform(multipart("/api/uploads/optional"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.titleState").value("missing"))
                .andExpect(jsonPath("$.fileState").value("missing"));
    }

    @Test
    void optionalEmptyFileIsDifferentFromMissing() throws Exception {
        mvc.perform(multipart("/api/uploads/optional")
                        .file(emptyFile())
                        .param("title", ""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.titleState").value("blank"))
                .andExpect(jsonPath("$.fileState").value("empty"));
    }

    @Test
    void modelAttributeRejectsBlankTitle() throws Exception {
        mvc.perform(multipart("/api/uploads/form")
                        .file(validFile())
                        .param("title", "   "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("title.blank"));
    }

    @Test
    void modelAttributeDetectsMissingFile() throws Exception {
        mvc.perform(multipart("/api/uploads/form")
                        .param("title", "Report"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("file.missing"));
    }

    @Test
    void modelAttributeAcceptsValidForm() throws Exception {
        mvc.perform(multipart("/api/uploads/form")
                        .file(validFile())
                        .param("title", "Report"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.bytes").value(3));
    }

    @Test
    void jsonMetadataPartIsDeserializedAndValidated()
            throws Exception {

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", "application/json",
                "{\"label\":\"Report\"}"
                        .getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/uploads/metadata")
                        .file(metadata)
                        .file(validFile()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.label").value("Report"))
                .andExpect(jsonPath("$.bytes").value(3));
    }

    @Test
    void missingMetadataPartIsBadRequest() throws Exception {
        mvc.perform(multipart("/api/uploads/metadata")
                        .file(validFile()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void blankJsonMetadataLabelIsBadRequest()
            throws Exception {

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", "application/json",
                "{\"label\":\"\"}"
                        .getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/uploads/metadata")
                        .file(metadata)
                        .file(validFile()))
                .andExpect(status().isBadRequest());
    }
}
```

Chạy tại thư mục `multipart-demo`:

```bash
mvn test
```

**Kỳ vọng:** 12 test cases đều đạt các assertion HTTP status/JSON như định nghĩa. Kết quả chạy Maven cụ thể có thể phụ thuộc môi trường; không giả định thứ tự log. Với ví dụ này, assertion `missingRequiredFileIsBadRequest` và `emptyRequiredFileReachesBusinessCheck` **cùng status 400** nhưng nguyên nhân khác nhau:
- Part thiếu bị Spring MVC chặn khi resolve required argument.
- Part tồn tại mà rỗng được controller nhận và trả lỗi nghiệp vụ `file.empty`.

Bằng cách test từng nhánh, ta không nhầm hai trường hợp dù HTTP status giống nhau.

## 9. Thử request thực bằng curl

Khởi động ứng dụng:

```bash
mvn spring-boot:run
```

Chuẩn bị một tệp `report.txt` chứa vài ký tự. Các lệnh sau chạy trong shell Unix/macOS; trên PowerShell Windows có thể dùng `curl.exe` thay cho `curl` để tránh alias cũ.

### 9.1. Gửi đúng field và file

```bash
curl -i -F 'title=Report' \
  -F 'file=@report.txt;type=text/plain' \
  http://localhost:8080/api/uploads/required
```

Kỳ vọng HTTP **200 OK** và JSON có `title="Report"`, `bytes` bằng kích thước thực của `report.txt`. Giá trị bytes không cố định nếu nội dung tệp khác.

### 9.2. Bỏ hẳn file part

```bash
curl -i -F 'title=Report' \
  http://localhost:8080/api/uploads/required
```

Kỳ vọng HTTP **400 Bad Request** vì `@RequestParam("file")` bắt buộc mà request không có part tên `file`. Handler `required()` thường **chưa được gọi**.

Gửi request tương tự đến endpoint optional:

```bash
curl -i -F 'title=Report' \
  http://localhost:8080/api/uploads/optional
```

Kỳ vọng HTTP **200** với `fileState="missing"`. Với `@RequestPart(required=false)`, thiếu file không phải lỗi tự động.

### 9.3. Gửi tệp 0 byte

Tạo một file `empty.txt` không có nội dung, rồi gửi:

```bash
curl -i -F 'title=Report' \
  -F 'file=@empty.txt;type=text/plain' \
  http://localhost:8080/api/uploads/required
```

Kỳ vọng HTTP **400** với JSON `{"error":"file.empty"}`. Part có mặt, nhưng `MultipartFile.isEmpty()` là `true` nên code nghiệp vụ chặn.

### 9.4. Gửi metadata JSON cùng file

```bash
curl -i \
  -F 'metadata={"label":"Report"};type=application/json' \
  -F 'file=@report.txt;type=text/plain' \
  http://localhost:8080/api/uploads/metadata
```

Kỳ vọng HTTP **200** với `label="Report"`, `bytes` bằng kích thước file. Nếu bỏ part metadata, request thiếu `@RequestPart("metadata")` và thường nhận 400. Nếu label là chuỗi rỗng, `@Valid` + `@NotBlank` trả lỗi validation.

**Đừng tự thêm header `Content-Type: multipart/form-data` khi dùng `-F`**: curl tự tạo boundary phù hợp.

## 10. JavaScript FormData và HTML: vì sao missing khác empty?

Với trình duyệt:

```javascript
const titleInput = document.querySelector("#title");
const fileInput = document.querySelector("#file");
const data = new FormData();

data.append("title", titleInput.value);

if (fileInput.files.length > 0) {
  data.append("file", fileInput.files[0]);
}

const response = await fetch("/api/uploads/form", {
  method: "POST",
  body: data
});
```

Đây là đoạn minh họa giả sử HTML có hai input với `id="title"`/`id="file"` và được thực thi trong một hàm bất đồng bộ hoặc top-level môi trường hỗ trợ `await`.

- `data.append("title", titleInput.value)` luôn tạo form field `title`, ngay cả khi `value == ""`.
- Điều kiện `files.length > 0` quyết định **không thêm part file** khi chưa chọn file; lúc đó server có thể thấy `file == null` nếu binding optional/DTO.
- Nếu người dùng chọn tệp thật nhưng file có kích thước 0 byte, `FormData` vẫn mang part `file`, và `MultipartFile.isEmpty()` vẫn là `true`.
- `fetch` sẽ tự đặt `Content-Type` cùng boundary. Không gán header multipart thủ công.

Một form HTML submit truyền thống có thể xử lý input file chưa chọn theo cách khác với đoạn JavaScript điều kiện ở trên. Vì vậy **test cả request không có part và request có part 0 byte**.

## 11. BindingResult, Bean Validation và nơi báo lỗi

### 11.1. `@NotBlank` kiểm tra gì?

- `@NotBlank String title`: không được `null`, rỗng hoặc toàn whitespace.
- `@NotNull MultipartFile file`: chỉ xác minh object không `null`, **không** xác minh số byte.
- `@Valid @ModelAttribute UploadForm form`: yêu cầu provider kiểm tra các constraint trên DTO.
- `BindingResult`: cho phép handler xem binding và validation errors. Nó phải đặt **liền sau** object đang được bind/validate.

Ví dụ đọc lỗi theo field:

```java
if (errors.hasErrors()) {
    for (var fieldError : errors.getFieldErrors()) {
        System.out.println(
                fieldError.getField() + ": "
                        + fieldError.getDefaultMessage());
    }
}
```

Đây là fragment nằm trong handler có biến `BindingResult errors`. Ứng dụng thật nên chuyển field errors thành cấu trúc JSON với mã ổn định thay vì chỉ ghi log.

Nếu không khai báo `BindingResult` ngay sau một đối số `@Valid @ModelAttribute`/`@RequestPart` và validation thất bại, Spring MVC thường ném `MethodArgumentNotValidException`; nếu method validation áp dụng do có constraint trực tiếp trên các method parameters/return, có thể là `HandlerMethodValidationException`. Chọn cách xử lý dựa trên chữ ký handler và phiên bản Spring.

### 11.2. Muốn tự khai báo constraint “file không rỗng”

Có thể viết custom Jakarta Validation constraint ví dụ `@NonEmptyUpload` và `ConstraintValidator<NonEmptyUpload, MultipartFile>`:

```java
public class NonEmptyUploadValidator
        implements ConstraintValidator<NonEmptyUpload, MultipartFile> {

    @Override
    public boolean isValid(
            MultipartFile file, ConstraintValidatorContext context) {
        return file != null && !file.isEmpty();
    }
}
```

Đây là **đoạn lõi validator minh họa**; để biên dịch cần định nghĩa annotation `@NonEmptyUpload` với `@Constraint(validatedBy=NonEmptyUploadValidator.class)`, `@Target`, `@Retention(RUNTIME)`, `message`, `groups`, `payload` và import Jakarta Validation/Spring MultipartFile. Nó không nằm trong dự án chạy ở mục 7.

Với rule trên, annotation được đặt trên field `MultipartFile` của DTO. Nếu muốn cho phép field vắng mặt ở một số workflow, constraint có thể chỉ xử lý nội dung không rỗng còn `@NotNull` kiểm tra sự hiện diện; cần quyết định rõ hợp đồng nghiệp vụ trước khi viết validator.

## 12. Lỗi thường gặp và các ngoại lệ tương ứng

| Trạng thái | Lỗi thường gặp ở Spring MVC | Phản hồi mặc định thường thấy |
| --- | --- | --- |
| Thiếu `@RequestParam("title")` bắt buộc | `MissingServletRequestParameterException` | 400 |
| Thiếu `@RequestParam("file") MultipartFile` hoặc `@RequestPart("file")` bắt buộc | `MissingServletRequestPartException` | 400 |
| Multipart body sai định dạng/không parse được | `MultipartException` hoặc lỗi multipart liên quan | Thường 4xx/5xx tùy nguyên nhân và cấu hình |
| Content type không phù hợp `consumes` hoặc converter | `HttpMediaTypeNotSupportedException` | 415 |
| JSON part sai cú pháp/không đọc được | `HttpMessageNotReadableException` | 400 |
| `@Valid @RequestPart Metadata` / DTO validation thất bại | `MethodArgumentNotValidException` (hoặc nhánh method validation tùy chữ ký) | 400 |
| File vượt giới hạn upload | `MaxUploadSizeExceededException`/lỗi upload container | Có thể chuyển thành 413 trong handler phù hợp |
| File có mặt nhưng `isEmpty()` | **Không nhất thiết có exception framework** | Controller/custom validator cần tự từ chối |

Không nên hard-code mọi trường hợp thành cùng một exception. Đặc biệt, **missing file** và **empty file** cần cơ chế xử lý khác nhau nếu API có hợp đồng phân biệt chúng.

Một `@RestControllerAdvice` có thể chuẩn hóa lỗi khi cần:

```java
@RestControllerAdvice
class UploadErrorAdvice {

    @ExceptionHandler(MissingServletRequestPartException.class)
    ResponseEntity<Map<String, String>> missing(
            MissingServletRequestPartException e) {

        return ResponseEntity.badRequest().body(
                Map.of("error", "part.missing",
                       "part", e.getRequestPartName()));
    }
}
```

Đây là **đoạn minh họa độc lập với dự án mục 7** (nếu ghép vào dự án thì cần import `@RestControllerAdvice`, `@ExceptionHandler`, exception, `ResponseEntity` và `Map`). Với ứng dụng thật, có thể dùng `ProblemDetail` để trả cấu trúc lỗi thống nhất. Kiểm thử response của handler do bạn tự thêm sẽ khác response mặc định, nên cần đồng bộ test.

## 13. Giới hạn kích thước, định dạng và lưu tệp

Khi chạy Spring Boot 3.x, multipart support được cấu hình bằng nhóm thuộc tính `spring.servlet.multipart.*`. Ví dụ tùy chỉnh:

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=8MB
spring.servlet.multipart.file-size-threshold=0B
```

Đây là **cấu hình minh họa**, không phải giá trị mặc định. Ở Spring Boot 3.5, mặc định tài liệu mô tả `max-file-size=1MB` và `max-request-size=10MB`; tùy chỉnh theo nhu cầu ứng dụng. Dung lượng vượt trần có thể bị chặn **trong khi parser đọc request**, trước cả `@Valid` hay controller.

Ngoài `file.isEmpty()`, upload thực tế cần:
- **Giới hạn size:** kiểm tra `getSize()` ở tầng nghiệp vụ (nếu yêu cầu khác cấu hình toàn cục) và cấu hình mức tối đa ở parser để tránh quá tải.
- **Loại tệp:** `getContentType()` và phần mở rộng từ `getOriginalFilename()` là dữ liệu do client cung cấp, chỉ dùng như tín hiệu ban đầu. Kiểm tra thực tế bằng cách đọc định dạng/magic bytes khi cần.
- **Tên và đường dẫn lưu:** tự tạo tên đích (UUID hoặc ID server), ngăn path traversal, chuẩn hóa và xác minh thư mục đích; không sử dụng trực tiếp chuỗi do client cung cấp.
- **Lưu trữ:** cân nhắc stream để tránh giữ file lớn trong RAM; lưu tệp tạm và chuyển sang lưu bền vững trong request; đảm bảo xử lý lỗi I/O.
- **Chính sách truy cập:** kiểm soát người upload, loại dữ liệu được phép, quyền đọc sau upload và quét malware nếu môi trường yêu cầu.
- **Ghi nhận metadata:** lưu tên gốc chỉ như thông tin hiển thị đã xử lý, không làm định danh tệp bền vững.

Một tên file được đưa đến server **không phải đường dẫn tin cậy**. `getOriginalFilename()` có thể rỗng, `null` hoặc chứa path segments theo client. Sử dụng trực tiếp nó để ghi file có thể gây ghi đè hoặc path traversal.

## 14. Checklist debug khi file/field bị “mất” trong Spring MVC

1. **Kiểm tra HTTP Content-Type:** có phải `multipart/form-data` với boundary hợp lệ không? Nếu dùng `fetch(FormData)`, để browser tự đặt header.
2. **Kiểm tra form field names:** `name="file"` có đúng với `@RequestParam("file")`/`@RequestPart("file")` không? Chữ hoa/chữ thường và tên cần nhất quán.
3. **Kiểm tra part có thực sự được gửi:** đọc raw request ở môi trường test hoặc dùng `MockMultipartFile`. Tách case không có part với part 0 byte.
4. **Kiểm tra `required`:** `true` có thể chặn trước controller; `false` thì cần xử lý `null` ở controller.
5. **Kiểm tra `@ModelAttribute`:** DTO có setter/constructor binding thích hợp? Field name trùng tên parameter? `BindingResult` đặt ngay sau DTO?
6. **Kiểm tra `@Valid`:** Với DTO có `@NotBlank`, đã bật provider và annotation ở nơi kích hoạt validation chưa? Với file rỗng, có custom rule/`isEmpty()` không?
7. **Kiểm tra JSON part:** Có đúng `Content-Type: application/json` cho part metadata? DTO có thể được deserialize bởi Jackson không?
8. **Kiểm tra upload limits:** Parser có từ chối file quá lớn trước controller không? Xem `spring.servlet.multipart.max-file-size` và `max-request-size`.
9. **Kiểm tra error handler:** `@ControllerAdvice` có đổi status/message làm hai lỗi trông giống nhau không?
10. **Kiểm tra stack:** Ứng dụng là Spring MVC Servlet hay WebFlux? `MultipartFile` và `FilePart` thuộc hai cơ chế khác nhau.

## 15. Bài tập củng cố

1. Đổi `@RequestParam("file")` thành `@RequestParam(name="file", required=false)` ở endpoint required; tự thêm nhánh `file == null` rồi dùng MockMvc xác nhận lỗi tùy chỉnh.
2. Gửi file `empty.txt` 0 byte, nhưng vẫn có filename. So sánh `file.getOriginalFilename()`, `getSize()` và `isEmpty()`; vì sao filename không chứng minh file có nội dung?
3. Đổi form field `file` thành `attachment` ở HTML mà không đổi controller; giải thích vì sao Spring coi `file` là thiếu.
4. Bỏ `@Valid` khỏi `@ModelAttribute UploadForm`; gửi `title="   "` và xác định constraint `@NotBlank` có tự chạy không.
5. Đổi `@RequestPart("metadata")` thành `@RequestParam("metadata") Metadata` mà không viết converter; giải thích vì sao JSON part không còn được đọc theo cơ chế `HttpMessageConverter` tương đương.
6. Gửi part metadata `text/plain` chứa chuỗi JSON. Quan sát phản hồi khi converter không phù hợp và sửa lại `Content-Type` của chính part.
7. Thêm endpoint nhận `List<MultipartFile>`, thử 0, 1 và 2 files cùng tên `files`; đừng chỉ dựa vào độ dài list mà phải kiểm tra từng `MultipartFile.isEmpty()`.
8. Thêm cấu hình max file 1MB; tạo test/request lớn hơn giới hạn để chứng minh parser có thể từ chối trước controller.
9. Viết custom constraint cho `MultipartFile`, kiểm tra cả `null` và file 0 byte rồi so sánh cách bắt lỗi với `@NotNull`.

**Ghi nhớ:** `@RequestParam` và `@RequestPart` quyết định **cách tìm/đọc part**, `@ModelAttribute` quyết định **cách bind form vào object**, `@Valid`/`BindingResult` quyết định **cách kiểm tra và đọc lỗi DTO**. Một part bắt buộc **vắng mặt** và một `MultipartFile` **có mặt nhưng rỗng** là hai trạng thái khác nhau; phải test và xử lý riêng theo hợp đồng API.

## Tài liệu tham khảo

- [Spring Framework — Multipart requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework — `@ModelAttribute` binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — `MultipartFile` JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html)
- [Spring Framework — Controller method validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Multipart application properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot 3.5 — Testing with MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)