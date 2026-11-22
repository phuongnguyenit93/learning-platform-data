# @RequestPart và tham số multipart trong Spring MVC

## Mục tiêu

Sau bài này, bạn có thể giải thích `multipart/form-data` gồm những phần nào, khi nào sử dụng `@RequestPart` thay cho `@RequestParam` hay `@ModelAttribute`, nhận file và JSON metadata trong cùng một HTTP request, khai báo phần bắt buộc/tùy chọn, xử lý nhiều file, xác thực đầu vào, cấu hình giới hạn dung lượng và kiểm thử upload bằng MockMvc.

Bài tập trung vào **Spring MVC chạy trên Servlet stack**, sử dụng **Java 17+**, **Spring Boot 3.x**, `jakarta.servlet`. Spring WebFlux có kiểu `FilePart` và cơ chế reactive riêng; không thay `MultipartFile` trong các ví dụ MVC dưới đây bằng `FilePart`.

## 1. Multipart request là gì?

Request có body kiểu `multipart/form-data` gồm nhiều **part**. Mỗi part có header riêng (chẳng hạn `Content-Disposition`, `Content-Type`) và phần dữ liệu riêng. Header `Content-Type` của *request* chứa `boundary` để máy chủ xác định ranh giới giữa các part.

Ví dụ giản lược (chuỗi boundary chỉ là ví dụ):

~~~http
POST /api/uploads HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=BoundaryDemo

--BoundaryDemo
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Spring MVC","category":"notes"}
--BoundaryDemo
Content-Disposition: form-data; name="file"; filename="note.txt"
Content-Type: text/plain

Hello Spring!
--BoundaryDemo
Content-Disposition: form-data; name="comment"
Content-Type: text/plain

first upload
--BoundaryDemo--
~~~

Trong request này, `metadata`, `file` và `comment` là **tên part**. Một part có thể chứa chuỗi, JSON, tệp nhị phân hoặc nội dung khác. `filename` là thông tin do client gửi kèm, không phải đường dẫn được tin cậy để ghi file.

Ở phía server Spring MVC, multipart request được Servlet container và cơ chế `MultipartResolver` xử lý để controller truy cập từng part. Spring Boot thường tự cấu hình multipart support khi có Spring MVC; nếu bạn tự cấu hình Spring MVC/Servlet, có thể cần khai báo `MultipartResolver` và multipart configuration cho Servlet.

**Lưu ý:** Đừng tự đặt header request `Content-Type: multipart/form-data` mà thiếu `boundary`. Hãy để `curl -F`, trình duyệt `FormData` hoặc HTTP client tạo boundary và body khớp nhau.

## 2. `@RequestPart` đọc gì và binding diễn ra thế nào?

Một endpoint có thể khai báo:

~~~java
@PostMapping(path = "/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public String upload(
        @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    return metadata.title() + ": " + file.getSize();
}
~~~

Đây là đoạn minh họa nằm trong một controller; `DocumentMetadata` cần được định nghĩa riêng.

- `@RequestPart("metadata")` tìm part có **name = metadata** rồi dùng `HttpMessageConverter` phù hợp với `Content-Type` của **part đó** để chuyển body sang `DocumentMetadata` (ví dụ JSON nhờ Jackson).
- `@RequestPart("file") MultipartFile` lấy dữ liệu upload dưới dạng đối tượng Spring `MultipartFile`, cung cấp `getInputStream()`, `getSize()`, `getContentType()`, `getOriginalFilename()`, `isEmpty()` và `transferTo(...)`.
- Cũng có thể nhận `jakarta.servlet.http.Part` với Servlet multipart parsing khi cần API Servlet và header của part.
- `name` và `value` là hai cách chỉ tên part; `@RequestPart("metadata")` là cú pháp gọn của `@RequestPart(name = "metadata")`.
- `required = true` là mặc định; phần bắt buộc bị thiếu thường gây **400 Bad Request** (`MissingServletRequestPartException`). `required = false` cho phép không có part, tham số tham chiếu có thể là `null`; có thể sử dụng `Optional<T>` theo hỗ trợ binding của Spring.
- **Không có thuộc tính `defaultValue` trên `@RequestPart`**. Nếu muốn fallback, hãy xử lý sau khi bind hoặc dùng kiểu cơ chế input phù hợp.

`@RequestPart` rất gần `@RequestBody` về **chuyển đổi payload bằng message converter**, nhưng `@RequestBody` nhắm vào body toàn request; còn `@RequestPart` nhắm vào **một phần cụ thể** bên trong multipart body. Header `Content-Type` của từng part quan trọng: JSON metadata nên đặt `application/json`; gửi JSON dưới dạng `text/plain` không bảo đảm bind được sang DTO JSON.

## 3. So sánh `@RequestPart`, `@RequestParam`, `@ModelAttribute` và `@RequestBody`

| Tình huống | Cách chọn thông dụng | Lý do |
| --- | --- | --- |
| Form upload có trường `description` là chuỗi và một file | `@RequestParam String description`, `@RequestParam MultipartFile file` | Bind tham số form đơn giản; Spring MVC hỗ trợ file multipart với `@RequestParam` |
| Upload file đi cùng part `metadata` mang JSON | `@RequestPart UploadMetadata metadata`, `@RequestPart MultipartFile file` | JSON part được deserialization bằng `HttpMessageConverter` |
| Form HTML nhiều trường được bind thành object | `@ModelAttribute UploadForm form` (có trường `MultipartFile`) | Data binding từ các form field vào thuộc tính của object |
| Request body JSON thuần, không có multipart | `@RequestBody UploadMetadata metadata` | Chuyển đổi body duy nhất của HTTP request |
| Cần API Servlet mức thấp | `@RequestPart Part part` hoặc `HttpServletRequest` | Làm việc trực tiếp với `Part` và metadata theo Servlet API |

Cả `@RequestParam MultipartFile` và `@RequestPart MultipartFile` đều có thể nhận file. **Sự khác nhau rõ nhất là với object JSON trong một part:** `@RequestPart` đọc payload theo media type của part để dùng converter; `@RequestParam` thiên về request parameter và type conversion của form data.

Không nên gửi JSON trong part rồi giả định `@ModelAttribute` tự giải mã JSON ấy như một `@RequestPart` DTO. Ngược lại, nếu frontend gửi các field `title` và `category` thông thường, một DTO `@ModelAttribute` có thể phù hợp hơn việc cố ghép chúng thành JSON.

## 4. Ví dụ Spring Boot 3.x chạy được: JSON metadata + một file

Tạo dự án Maven bằng Spring Initializr, chọn **Java 17 hoặc cao hơn**, **Spring Boot 3.x**, các dependency **Spring Web** và **Validation**; nếu muốn chạy phần kiểm thử bên dưới, thêm **Spring Boot Starter Test**. `spring-boot-starter-web` cung cấp Spring MVC, Tomcat và hỗ trợ JSON; `spring-boot-starter-validation` cung cấp Jakarta Bean Validation.

Cấu trúc tối thiểu:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/UploadController.java
src/main/resources/application.properties
src/test/java/com/example/demo/UploadControllerTest.java
~~~

**`src/main/java/com/example/demo/DemoApplication.java`**

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

**`src/main/java/com/example/demo/UploadController.java`**

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<UploadResult> create(
            @Valid @RequestPart("metadata") UploadMetadata metadata,
            @RequestPart("file") MultipartFile file,
            @RequestPart(name = "comment", required = false) String comment) {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "File must not be empty");
        }

        UploadResult result = new UploadResult(
                metadata.title(),
                metadata.category(),
                comment,
                file.getSize(),
                file.getContentType());

        // Chỉ báo nhận thành công; ví dụ không lưu file xuống đĩa.
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @PostMapping(path = "/many",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Long> many(
            @RequestPart("files") List<MultipartFile> files) {

        if (files.isEmpty() || files.stream().anyMatch(MultipartFile::isEmpty)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Files must not be empty");
        }

        return Map.of(
                "count", (long) files.size(),
                "totalBytes",
                files.stream().mapToLong(MultipartFile::getSize).sum());
    }

    public record UploadMetadata(
            @NotBlank String title,
            @NotBlank String category) {
    }

    public record UploadResult(
            String title,
            String category,
            String comment,
            long bytes,
            String mediaType) {
    }
}
~~~

Các điểm cần chú ý:

1. `consumes = MediaType.MULTIPART_FORM_DATA_VALUE` tuyên bố endpoint xử lý request multipart/form-data; request JSON đơn thuần không khớp media type này.
2. Part `metadata` phải có nội dung JSON phù hợp với record `UploadMetadata`. Annotation `@Valid` yêu cầu kiểm tra `@NotBlank`; metadata không hợp lệ thường bị trả **400**.
3. `file` là part bắt buộc về sự hiện diện. Tuy nhiên một part file rỗng **có thể vẫn tồn tại**, nên kiểm tra `file.isEmpty()` riêng.
4. `comment` là part tùy chọn; thiếu part có thể cho `null`. Nếu ứng dụng muốn giá trị `""`, tự chuẩn hóa trong business logic.
5. Kết quả trả về chỉ chứng minh **binding/validation và metadata**; file **chưa được lưu**. Để có API lưu file thực tế, cần storage service, kiểm tra quyền và chính sách an toàn file.
6. `mediaType` từ `file.getContentType()` là metadata do client khai báo, có thể `null` hoặc sai; đừng sử dụng nó như bằng chứng loại tệp.

**`src/main/resources/application.properties`** (giới hạn minh họa)

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=10MB
~~~

Giới hạn `max-file-size` áp dụng mỗi file; `max-request-size` áp dụng toàn request multipart, gồm dữ liệu các part và overhead. Spring Boot thường bật multipart theo mặc định. Giá trị mặc định thông dụng khi không cấu hình là **1MB/file và 10MB/request**, nhưng hãy đối chiếu phiên bản/config triển khai.

Trong thư mục dự án, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`; nếu không có Maven Wrapper, dùng `mvn spring-boot:run` sau khi cài Maven.

Tạo file mẫu `note.txt` chứa chuỗi `Hello Spring!` theo cách phù hợp hệ điều hành rồi gửi request:

~~~bash
curl -i -X POST "http://localhost:8080/api/uploads" \
  -F 'metadata={"title":"Spring MVC","category":"notes"};type=application/json' \
  -F 'file=@note.txt;type=text/plain' \
  -F 'comment=first upload'
~~~

Lệnh trên viết theo cú pháp shell hỗ trợ dấu `\` để xuống dòng (Linux/macOS/Git Bash). Trên PowerShell, chạy `curl.exe` và gõ một dòng hoặc dùng cú pháp nối dòng của PowerShell; dấu nháy và escaping trong `-F` cũng cần theo shell. Đặc biệt, `;type=application/json` gắn media type vào **part metadata**, không phải vào toàn request.

Phản hồi thành công có HTTP status **201 Created**. Body minh họa, giả sử file UTF-8 có đúng 13 byte (chuỗi `Hello Spring!` không có newline):

~~~json
{
  "title": "Spring MVC",
  "category": "notes",
  "comment": "first upload",
  "bytes": 13,
  "mediaType": "text/plain"
}
~~~

Nếu tạo file có newline hoặc nội dung khác, `bytes` sẽ thay đổi; JSON property order không có ý nghĩa. Khi không gửi `comment`, cấu hình Jackson mặc định thường biểu diễn `comment: null`.

## 5. Kết nối frontend bằng `FormData`

Khi dùng trình duyệt, `FormData` tạo multipart body. Ví dụ trong frontend có `fileInput` trỏ đến một `<input type="file">`:

~~~javascript
const file = fileInput.files[0];

const form = new FormData();
form.append("metadata", new Blob(
  [JSON.stringify({ title: "Spring MVC", category: "notes" })],
  { type: "application/json" }
));
form.append("file", file);
form.append("comment", "first upload");

const response = await fetch("/api/uploads", {
  method: "POST",
  body: form
});

if (!response.ok) {
  throw new Error("Upload failed: HTTP " + response.status);
}
console.log(await response.json());
~~~

Dùng `Blob` với `type: "application/json"` bảo đảm Spring thấy metadata part là JSON và có thể chọn converter. Nếu chỉ dùng `form.append("metadata", JSON.stringify(object))`, trình duyệt sẽ gửi **text field**, thường thiếu media type JSON phù hợp và có thể dẫn đến lỗi chuyển DTO.

**Không tự khai báo** `Content-Type` của request khi dùng `fetch` với `FormData`; trình duyệt sẽ tự đặt multipart boundary. Với frontend và backend khác origin, xem xét CORS, cấu hình credentials/cookie và CSRF theo Spring Security; xử lý frontend không thay thế chính sách bảo mật server.

## 6. Một file, nhiều file và Servlet `Part`

Đối với một file, các kiểu tham số phổ biến:

~~~java
@RequestPart("file") MultipartFile file
@RequestParam("file") MultipartFile file
@RequestPart("file") jakarta.servlet.http.Part file
~~~

Đây là **các khai báo tham số**, dùng bên trong một handler method thích hợp. `MultipartFile` là abstraction của Spring; `Part` là API Servlet, có `getInputStream()`, `getSize()`, `getSubmittedFileName()`, `getHeader(...)`. Không dùng `org.springframework.http.codec.multipart.FilePart` trong Spring MVC: đó là abstraction cho WebFlux.

Nếu một tên part xuất hiện nhiều lần, có thể nhận nhiều file qua `List<MultipartFile>` hoặc `MultipartFile[]`. Ví dụ endpoint `/api/uploads/many` ở trên:

~~~bash
curl -i -X POST "http://localhost:8080/api/uploads/many" \
  -F 'files=@first.txt' \
  -F 'files=@second.txt'
~~~

Cả hai part đều dùng **name = files**. Body phản hồi chứa `count = 2` và tổng kích thước byte của hai file. Không nhầm với hai part tên `file1`, `file2`, vì chúng **không tự động** bind vào cùng một tham số `files`.

Muốn nhận các file mang tên khác nhau, có thể dùng `@RequestParam MultiValueMap<String, MultipartFile>` hoặc `Map<String, MultipartFile>` không chỉ định tên tham số (phân biệt: map thường chỉ một giá trị mỗi tên, multivalue map giữ danh sách). Chỉ sử dụng khi API thật sự cho phép tên part động; với API xác định rõ tên, tham số cụ thể dễ kiểm soát hơn.

**Không coi `file.getSize() > 0` là xác minh file hợp lệ.** Một file có thể không rỗng nhưng nội dung, tên, encoding hoặc định dạng vẫn nguy hiểm hoặc sai nghiệp vụ.

## 7. Xử lý lỗi khi thiếu part, sai định dạng hoặc quá lớn

| Tình huống | Nguyên nhân thường gặp | Phản hồi/kết quả |
| --- | --- | --- |
| Thiếu `metadata` hoặc `file` bắt buộc | Tên field sai hoặc client không gửi part | Thường **400**, `MissingServletRequestPartException` |
| Không có `comment` | Được khai báo `required=false` | Controller nhận `null` |
| Metadata không phải JSON hợp lệ | `HttpMessageConverter` đọc JSON thất bại | Thường **400** với lỗi body không đọc được |
| JSON đúng cú pháp nhưng sai `@NotBlank` | Jakarta Bean Validation trên `@Valid @RequestPart` | Thường **400**, `MethodArgumentNotValidException` |
| Metadata JSON gửi với `Content-Type: text/plain` | Không có converter phù hợp cho DTO | Thường **415 Unsupported Media Type** |
| Request dùng `application/json` thay `multipart/form-data` | Không khớp `consumes` của handler | Thường **415 Unsupported Media Type** |
| File part rỗng | Part tồn tại nhưng không có bytes | Ví dụ controller chủ động trả **400** |
| File hoặc toàn request vượt giới hạn | Multipart parser/container từ chối | Lỗi upload/size; **413 Content Too Large** là status hợp lý khi được cấu hình/ánh xạ |
| Request multipart có boundary lỗi | Parser không tách được part | Lỗi parse multipart; status phụ thuộc cấu hình container và error handler |

Các status ở bảng là **hành vi điển hình**, không phải lời hứa về mọi body lỗi trong mọi cấu hình Spring Boot, Servlet container, reverse proxy hoặc custom exception handler. Với upload quá lớn, `MaxUploadSizeExceededException` có thể xuất hiện; HTTP 413 phụ thuộc cách stack xử lý và ánh xạ exception. Cấu hình server/proxy (ví dụ giới hạn body) có thể từ chối trước khi request tới controller.

Nếu muốn chuẩn hóa body lỗi cho API, dùng `@RestControllerAdvice` và ánh xạ chính xác các ngoại lệ cần thiết. Tránh catch chung mọi `Exception` rồi đổi thành 200 hoặc 400, vì như vậy sẽ che lỗi server. Với multipart validation, có thể đặt `BindingResult` ngay sau tham số DTO `@Valid @RequestPart` nếu thật sự cần xử lý lỗi validation tại handler, nhưng nhánh này phải được thiết kế và kiểm thử rõ.

## 8. Kiểm thử `@RequestPart` với MockMvc

Cần `spring-boot-starter-test`. Thêm file **`src/test/java/com/example/demo/UploadControllerTest.java`**:

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

    private static MockMultipartFile metadata(String json, String contentType) {
        return new MockMultipartFile(
                "metadata",
                "",
                contentType,
                json.getBytes(StandardCharsets.UTF_8));
    }

    private static MockMultipartFile file() {
        return new MockMultipartFile(
                "file",
                "note.txt",
                "text/plain",
                "Hello".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void uploadsValidJsonAndFile() throws Exception {
        mockMvc.perform(multipart("/api/uploads")
                        .file(metadata(
                                "{\"title\":\"Spring MVC\",\"category\":\"notes\"}",
                                "application/json"))
                        .file(file())
                        .file(new MockMultipartFile(
                                "comment",
                                "",
                                "text/plain",
                                "first upload".getBytes(StandardCharsets.UTF_8))))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Spring MVC"))
                .andExpect(jsonPath("$.category").value("notes"))
                .andExpect(jsonPath("$.comment").value("first upload"))
                .andExpect(jsonPath("$.bytes").value(5));
    }

    @Test
    void missingRequiredFileReturnsBadRequest() throws Exception {
        mockMvc.perform(multipart("/api/uploads")
                        .file(metadata(
                                "{\"title\":\"Spring MVC\",\"category\":\"notes\"}",
                                "application/json")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void invalidJsonMetadataReturnsBadRequest() throws Exception {
        mockMvc.perform(multipart("/api/uploads")
                        .file(metadata("{invalid-json", "application/json"))
                        .file(file()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void beanValidationRejectsBlankTitle() throws Exception {
        mockMvc.perform(multipart("/api/uploads")
                        .file(metadata(
                                "{\"title\":\"\",\"category\":\"notes\"}",
                                "application/json"))
                        .file(file()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void acceptsTwoFilesWithSamePartName() throws Exception {
        MockMultipartFile one = new MockMultipartFile(
                "files", "a.txt", "text/plain", new byte[] {1, 2});
        MockMultipartFile two = new MockMultipartFile(
                "files", "b.txt", "text/plain", new byte[] {3});

        mockMvc.perform(multipart("/api/uploads/many")
                        .file(one).file(two))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2))
                .andExpect(jsonPath("$.totalBytes").value(3));
    }
}
~~~

Chạy test:

~~~bash
./mvnw test
~~~

Kiểm thử chú ý `MockMultipartFile` có tên part đầu tiên: `"metadata"`, `"file"`, `"comment"` phải **khớp chính xác** tên trên annotation. `MockMultipartFile("metadata", "", "application/json", ...)` giúp JSON part được đọc bằng converter tương ứng. Trong test nhiều file, cả hai file phải cùng tên `"files"`.

**Giới hạn của MockMvc:** test chủ yếu xác minh argument resolution, conversion, validation và logic controller. Việc Servlet container xử lý upload thật, lưu tạm, giới hạn body ở reverse proxy và lỗi upload quá lớn nên được kiểm thử tích hợp thêm trong môi trường có server thật.

## 9. Lưu file an toàn trong ứng dụng thật

Ví dụ trên cố ý **không lưu** file. Khi triển khai storage, cần chú ý:

1. **Không nối trực tiếp `getOriginalFilename()` vào đường dẫn đích.** Tên gốc do client kiểm soát, có thể rỗng, có ký tự phân cách đường dẫn hoặc chuỗi `../`. Sinh tên lưu trữ độc lập (ví dụ UUID), dùng thư mục được cấu hình rõ và kiểm soát quyền.
2. **Giới hạn kích thước ở nhiều lớp.** Đặt `spring.servlet.multipart.max-file-size`, `spring.servlet.multipart.max-request-size` phù hợp, và đối chiếu giới hạn Servlet container/reverse proxy. Nếu xử lý ảnh/video hoặc nhiều file, thiết kế timeout và quota hợp lý.
3. **Không chỉ tin MIME type hoặc extension được client khai báo.** Đối chiếu loại nội dung dựa trên dữ liệu thực (đọc magic bytes/parser phù hợp), whitelist định dạng được phép, cân nhắc quét malware khi cần, và giới hạn thao tác giải nén với archive.
4. **Không giữ file tạm như storage lâu dài.** `MultipartFile` có thể được lưu tạm trong bộ nhớ hoặc trên đĩa và thường có vòng đời gắn với request. Nếu cần lưu, đọc stream/copy sang storage được quản lý trong lúc xử lý request; có chính sách dọn dẹp tài nguyên.
5. **Không gọi `getBytes()` với file lớn chỉ để sao chép.** Xem xét `getInputStream()` và streaming/copy có giới hạn để giảm áp lực bộ nhớ; cần quản lý tài nguyên và ngoại lệ I/O.
6. **Bảo vệ endpoint.** Xác thực, phân quyền, quota, logging metadata an toàn, kiểm tra CSRF theo ngữ cảnh trình duyệt; không cho client quyết định storage path hoặc file owner tùy ý.
7. **Trả file tải xuống có kiểm soát.** Nếu phục vụ file người dùng tải lên, thiết lập content type, content disposition và chính sách browser phù hợp để giảm rủi ro nội dung chủ động được thực thi.
8. **Không coi multipart upload là giao dịch nguyên tử.** Nếu đã lưu file rồi ghi database lỗi (hoặc ngược lại), cần có chiến lược rollback/cleanup/compensation để tránh file mồ côi.

Có thể lưu ra file qua `transferTo(...)`, nhưng phương thức này không thay cho việc kiểm soát đường dẫn và validation. Nếu dùng cloud object storage, thiết kế giới hạn/streaming phù hợp SDK và kiểm soát quyền truy cập bucket.

## 10. Các lỗi thường gặp và cách tự chẩn đoán

- **`MissingServletRequestPartException`:** so lại chính xác tên trong `-F "metadata=..."` hoặc `form.append("metadata", ...)` với `@RequestPart("metadata")`; kiểm tra request có đúng multipart và có boundary.
- **Lỗi 415 khi metadata đã là JSON:** nhìn vào `Content-Type` **riêng của metadata part** trong tab Network hoặc HTTP client; dùng `application/json`.
- **DTO null hoặc không được bind như dự kiến:** đối chiếu JSON property names với record/POJO, Jackson và constructor/binding; phân biệt gửi JSON part với nhiều text field.
- **Gửi multipart từ frontend nhưng server không nhận:** đừng tự set `Content-Type` toàn request khi dùng `FormData`; kiểm tra CORS/credentials và giới hạn proxy.
- **File trống:** đối chiếu client chọn file chưa, `MultipartFile.isEmpty()`, cũng như trường hợp file có kích thước 0 hợp lệ theo nghiệp vụ hay không.
- **Lỗi 400 dù có đủ part:** JSON sai, validation thất bại hoặc tên part đúng nhưng media type/nội dung không tương thích; kiểm tra log exception và phản hồi lỗi.
- **Quá giới hạn kích thước:** kiểm tra cả `max-file-size`, `max-request-size` và giới hạn tầng proxy/server; đừng tăng vô hạn chỉ để bỏ lỗi.
- **Nhiều file chỉ nhận một:** chắc rằng gửi lặp cùng tên part `files` và handler nhận `List<MultipartFile>` hoặc kiểu collection thích hợp.

## 11. Checklist chọn và triển khai

1. Xác định request có thật sự là `multipart/form-data` và frontend/client tạo boundary hợp lệ.
2. Với JSON metadata, dùng `@RequestPart` DTO và gắn `Content-Type: application/json` cho **part**; với form text đơn giản, cân nhắc `@RequestParam` hoặc `@ModelAttribute`.
3. Với file, dùng `MultipartFile` hoặc `jakarta.servlet.http.Part`; thiết lập tên part chính xác và `required` phù hợp.
4. Validate dữ liệu JSON, độ rỗng và nội dung file; giới hạn từng file và toàn request; không tin tên/MIME type do client gửi.
5. Kiểm thử request hợp lệ, thiếu part, JSON/validation sai, nhiều file và các giới hạn trong môi trường chạy thật.

## Tài liệu chính thức

- [Spring Framework — Multipart trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html)
- [Spring Boot — Handling Multipart File Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html#howto.webserver.configure-multipart-file-uploads)
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
