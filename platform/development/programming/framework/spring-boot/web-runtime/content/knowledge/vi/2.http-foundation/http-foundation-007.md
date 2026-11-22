# Query parameter, form data, JSON và multipart trong Spring Boot

**Ngữ cảnh:** Spring Boot web-runtime → Nền tảng HTTP. Bài này sử dụng **Spring MVC trên Servlet stack**, Java 17+ và Spring Boot 3.5.x; phần lớn cơ chế cũng áp dụng với những phiên bản Spring MVC mới. Cần phân biệt với WebFlux ở một số chi tiết về cách đọc form data.

## 1. Bốn cách gửi dữ liệu trong HTTP

Một HTTP request gồm request line (method, path và query string), headers và phần body tùy chọn. **`Content-Type` mô tả định dạng body gửi lên**; nó không mô tả query string. Bốn cách gửi dữ liệu phổ biến:

| Loại dữ liệu | Vị trí và định dạng | Spring MVC thường dùng | Tình huống phù hợp |
| --- | --- | --- | --- |
| **Query parameter** | Sau dấu `?` của URL, ví dụ `?q=java&page=2` | `@RequestParam` | Tìm kiếm, lọc, phân trang, tùy chọn đọc |
| **Form URL-encoded** | Body với `application/x-www-form-urlencoded`, ví dụ `name=Lan&email=...` | `@RequestParam` hoặc `@ModelAttribute` | Form HTML đơn giản, dữ liệu trường văn bản |
| **JSON** | Body với `application/json`, ví dụ `{"productId":"P-7","quantity":3}` | `@RequestBody` | API gửi đối tượng, mảng, dữ liệu có cấu trúc |
| **Multipart** | Body với `multipart/form-data`, gồm nhiều **part** và `boundary` | `@RequestParam MultipartFile`, `@RequestPart` | Upload file, gửi file kèm text/JSON |

Ví dụ cùng thông tin người dùng có thể được truyền theo ba cách khác nhau, nhưng **cách đặt dữ liệu trên wire quyết định cách controller đọc nó**:

~~~http
GET /api/products?q=spring&page=2 HTTP/1.1
Host: localhost:8080
~~~

~~~http
POST /api/contacts HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Lan&email=lan%40example.com
~~~

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"productId":"P-7","quantity":3}
~~~

Ở ví dụ multipart, một part có thể là text và part khác là file nhị phân. Dấu phân cách `boundary` được khai báo trong header và bao quanh từng part. **Không tự viết header multipart với boundary giả khi dùng client như `curl -F` hoặc `FormData`**; client sẽ tạo boundary khớp với body.

> `@PathVariable` đọc một thành phần nằm trong đường dẫn, ví dụ `/products/42`; `@RequestHeader` đọc header. Hai nguồn dữ liệu này khác với query, form và body JSON.

## 2. Query parameter — tham số trên URL

**Cú pháp:** phần sau `?` là các cặp `key=value`, ngăn nhau bởi `&`. Ví dụ `/api/products?q=java%20web&page=2&tag=spring&tag=http` mang một từ khóa, số trang và hai giá trị `tag`.

Trong **Spring MVC Servlet**, `@RequestParam` đọc Servlet request parameters: chủ yếu là query string và trường form đã được parse. Với `GET`, query thường là nguồn cần đọc. Query không chỉ dành riêng cho `GET`: request `POST` vẫn có thể mang query trên URL.

~~~java
@GetMapping("/products")
public SearchResponse search(
        @RequestParam(defaultValue = "") String q,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(name = "tag", required = false) List<String> tags) {
    if (page < 1) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "page must be positive");
    }
    return new SearchResponse(q, page, tags == null ? List.of() : tags);
}
~~~

Giải thích:
- `@RequestParam("q")` hoặc `@RequestParam(name = "q")` chỉ rõ tên khóa trên request, không phụ thuộc tên biến Java. Thiếu tham số **required** mặc định gây lỗi HTTP 400; `required = false` hoặc `Optional<T>` cho phép vắng mặt.
- `defaultValue` cấp giá trị khi tham số vắng mặt hoặc rỗng và làm tham số trở thành không bắt buộc. Chuỗi nhận được được chuyển kiểu, ví dụ `page` từ text thành `int`.
- Với nhiều khóa cùng tên như `tag=spring&tag=http`, dùng `List<String>`, mảng hoặc `MultiValueMap<String,String>` nếu cần giữ toàn bộ giá trị.
- Dữ liệu đầu vào luôn không đáng tin: kiểm tra giới hạn `page`, `size`, sort field theo danh sách cho phép; tránh cho phép client điều khiển trực tiếp tên cột SQL.

**Mã hóa URL:** ký tự đặc biệt cần percent-encoding (dấu cách thường thành `%20`, ký tự `&` trong một giá trị thành `%26`). Quy tắc form-url-encoding có thể dùng `+` cho dấu cách; dấu `+` thực sự phải được mã hóa thành `%2B`. Phần fragment `#...` trên URL **không được trình duyệt gửi lên server**. Để tránh lỗi, dùng `URLSearchParams` hoặc client HTTP tự encode.

**Thiết kế API:** query thích hợp cho lọc, sắp xếp và phân trang, vì URL có thể liên kết hoặc bookmark. Không đặt mật khẩu, access token hoặc dữ liệu nhạy cảm trong URL: URL có thể xuất hiện ở history, access logs hay hệ thống giám sát. Đừng dùng query để chứa payload lớn.

## 3. Form data — `application/x-www-form-urlencoded`

Form HTML mặc định (không chọn `enctype` khác) gửi các trường thành cặp tên/giá trị trong body; cách mã hóa ký tự giống URL-encoded. Ví dụ body `name=Lan&email=lan%40example.com`. Browser dùng định dạng này cho nhiều form thông thường.

Có hai cách nhận trong Spring MVC:

~~~java
@PostMapping(path = "/quick-contact",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public String quickContact(
        @RequestParam("name") String name,
        @RequestParam("email") String email) {
    return name + " <" + email + ">";
}
~~~

Với nhiều trường, thường dùng **`@ModelAttribute` + form DTO** để Spring bind tên field sang thuộc tính Java, rồi Bean Validation kiểm tra:

~~~java
@PostMapping(path = "/contacts",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ContactResponse createContact(@Valid @ModelAttribute ContactForm form) {
    return new ContactResponse(form.getName(), form.getEmail());
}
~~~

`ContactForm` cần cấu trúc phù hợp để data binder khởi tạo và gán trường (ví dụ JavaBean có constructor không tham số, getter/setter). `@NotBlank` và `@Email` kiểm tra dữ liệu sau khi bind. Trong ví dụ đầy đủ ở phần 6 có định nghĩa DTO này.

**Điểm dễ nhầm:** `@RequestParam` trên Spring MVC Servlet có thể nhìn thấy cả query lẫn form URL-encoded vì Servlet API dùng khái niệm chung `request parameter`. Nếu cùng một key xuất hiện ở cả URL và body, đừng dựa vào thứ tự hoặc ưu tiên ngầm; hãy thiết kế hợp đồng API để không có tên trùng mơ hồ. Trên **Spring WebFlux**, `@RequestParam` chỉ đọc query; form và multipart có đường truy cập riêng.

**Không dùng `@RequestBody` để thay cho `@RequestParam` khi nhận form URL-encoded** trong Servlet MVC. Việc Servlet container parse request parameters có thể tiêu thụ body khiến việc đọc body trực tiếp không ổn định. `@ModelAttribute` cũng không phải parser JSON: nó là cơ chế bind request parameters vào object.

Một form HTML đơn giản:

~~~html
<form method="post" action="/api/contacts">
  <input name="name" required>
  <input name="email" type="email" required>
  <button type="submit">Gửi</button>
</form>
~~~

Ví dụ trên gửi form URL-encoded mặc định; phía API đang trả JSON, nên nếu cần trải nghiệm browser hoàn chỉnh, frontend thường gửi bằng `fetch` và tự xử lý JSON trả về. Nếu ứng dụng sử dụng cookie/session authentication, các POST form thay đổi trạng thái cần xem xét bảo vệ **CSRF** theo cấu hình Spring Security.

## 4. JSON — `application/json` và `@RequestBody`

Trong REST API, JSON phù hợp khi dữ liệu có cấu trúc, có object lồng nhau, danh sách, boolean hoặc số. Client gửi header `Content-Type: application/json` và body JSON hợp lệ. Spring MVC dùng `HttpMessageConverter` để deserialize body sang Java object; với Spring Boot MVC thông dụng, Jackson xử lý JSON.

~~~java
public record OrderInput(
        @NotBlank String productId,
        @Min(1) int quantity) {}

@PostMapping(path = "/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
public OrderResponse createOrder(@Valid @RequestBody OrderInput input) {
    return new OrderResponse(
            input.productId(), input.quantity(), input.quantity() * 1000L);
}
~~~

`@RequestBody` đọc **request body** một lần dưới dạng mà converter hỗ trợ; `@Valid` kích hoạt validation nếu project có Bean Validation provider. Lỗi cú pháp JSON, kiểu không chuyển đổi được hoặc body bắt buộc bị thiếu thường trả **400 Bad Request**. Nếu body gửi `text/plain` trong khi endpoint yêu cầu `application/json`, thường là **415 Unsupported Media Type**. DTO có trường hợp lệ về cú pháp nhưng sai quy tắc (ví dụ `quantity=0`) cũng có thể trả 400 do validation.

Phân biệt các header và thuộc tính:
- `Content-Type`: client **đang gửi** body ở dạng gì.
- `Accept`: client **muốn nhận** representation nào; không thay thế `Content-Type`.
- `consumes` trong `@PostMapping`: endpoint **chấp nhận** media type nào.
- `produces`: endpoint **tạo ra** representation nào.
- `@RestController`: giá trị trả về được serialize thành response body; với `@Controller` thông thường, trả `String` có thể được hiểu là view name.

JSON number, string, boolean và `null` khác nhau. `{"quantity":"3"}` là string, `{"quantity":3}` mới là number; đừng dựa vào cơ chế chuyển kiểu quá thoáng. Dùng DTO riêng cho request, tránh bind trực tiếp domain entity có trường nhạy cảm (ID nội bộ, quyền, trạng thái thanh toán...). Với input cần phân biệt **không truyền trường** và **truyền null**, cân nhắc dùng kiểu wrapper/validation phù hợp thay vì primitive `int`.

## 5. Multipart — file kèm trường text và JSON

`multipart/form-data` chia body thành nhiều part. Mỗi part có headers của riêng nó, thường gồm `Content-Disposition: form-data; name="..."`; file part có thể có `filename` và `Content-Type`. Khi upload file, Spring MVC cho phép dùng:
- `@RequestParam("file") MultipartFile file` để lấy file part, hoặc `List<MultipartFile>` nếu nhiều file cùng một tên.
- `@RequestParam("description") String description` để đọc trường text bên cạnh.
- `@RequestPart("metadata") DocumentMeta metadata` để deserialize **part JSON** bằng converter, tương tự `@RequestBody` nhưng phạm vi chỉ một part; gửi `Content-Type: application/json` trên part ấy.
- `jakarta.servlet.http.Part` nếu cần API chuẩn Servlet ở mức part.

~~~java
@PostMapping(path = "/uploads", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public UploadResponse upload(
        @RequestParam("description") String description,
        @RequestParam("file") MultipartFile file) {
    if (file.isEmpty()) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "file is empty");
    }
    return new UploadResponse(
            description, file.getOriginalFilename(), file.getSize());
}

@PostMapping(path = "/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public DocumentResponse document(
        @Valid @RequestPart("metadata") DocumentMeta metadata,
        @RequestPart("file") MultipartFile file) {
    if (file.isEmpty()) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "file is empty");
    }
    return new DocumentResponse(metadata.title(), file.getSize());
}
~~~

Hai method trên chỉ **trả metadata để học cơ chế binding**, chưa lưu file. Khi cần lưu thật, chuyển stream sang hệ thống lưu trữ đã chọn, tạo ID/tên lưu an toàn và xử lý lỗi I/O. `MultipartFile` là dữ liệu tạm trong vòng đời request; không giữ object đó để xử lý sau khi request kết thúc.

Ví dụ multipart thô rút gọn (boundary và byte file chỉ là minh họa, **không phải request hoàn chỉnh để copy nguyên văn**):

~~~http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=abc123

--abc123
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Hoa don"}
--abc123
Content-Disposition: form-data; name="file"; filename="sample.txt"
Content-Type: text/plain

hello
--abc123--
~~~

**Giới hạn upload và an toàn:**
- Spring Boot servlet mặc định bật multipart, giới hạn **1MB/file** và **10MB/request**; giới hạn cũng có thể tồn tại ở reverse proxy/gateway. Đặt giới hạn phù hợp nghiệp vụ, ví dụ:

~~~properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=20MB
~~~

- Kiểm tra `file.isEmpty()`, kích thước, loại file được phép và nội dung thực tế; `file.getContentType()` và `getOriginalFilename()` do client cung cấp, **không đáng tin**. Không dùng original filename làm đường dẫn lưu trực tiếp; phòng path traversal, file thực thi độc hại và ghi đè file.
- Kiểm soát quyền upload/download, giới hạn số file, quét malware khi nghiệp vụ yêu cầu, và tránh tải toàn bộ file lớn vào RAM bằng `getBytes()` khi không cần thiết.
- Lỗi vượt kích thước có thể được ứng dụng/container biểu diễn thành **413 Payload Too Large**, hoặc exception multipart cần được ánh xạ bởi handler của ứng dụng. Đừng hứa một mã lỗi duy nhất nếu chưa xác nhận stack/gateway cụ thể.
- Với browser `fetch` và `FormData`, **không tự đặt `Content-Type: multipart/form-data`**: trình duyệt phải thêm boundary thực tế.

## 6. Ví dụ chạy được: một ứng dụng, bốn kiểu đầu vào

Ví dụ cố định ở **Spring Boot 3.5.0, Java 17** để có project Maven tái hiện được. Sử dụng Spring MVC (Servlet), không cần database. Cây file:

~~~text
http-inputs/
├─ pom.xml
└─ src/main/java/com/example/httpinputs/
   ├─ DemoApplication.java
   └─ HttpInputsController.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>http-inputs</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
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

**`src/main/java/com/example/httpinputs/DemoApplication.java`**

~~~java
package com.example.httpinputs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/httpinputs/HttpInputsController.java`**

~~~java
package com.example.httpinputs;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class HttpInputsController {

    @GetMapping("/products")
    public SearchResponse search(
            @RequestParam(defaultValue = "") String q,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "tag", required = false) List<String> tags) {
        if (page < 1) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "page must be positive");
        }
        return new SearchResponse(q, page, tags == null ? List.of() : tags);
    }

    @PostMapping(
            path = "/contacts",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ContactResponse createContact(
            @Valid @ModelAttribute ContactForm form) {
        return new ContactResponse(form.getName(), form.getEmail());
    }

    @PostMapping(
            path = "/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public OrderResponse createOrder(@Valid @RequestBody OrderInput input) {
        return new OrderResponse(
                input.productId(), input.quantity(),
                input.quantity() * 1000L);
    }

    @PostMapping(
            path = "/uploads",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadResponse upload(
            @RequestParam("description") String description,
            @RequestParam("file") MultipartFile file) {
        requireNonEmpty(file);
        return new UploadResponse(
                description, file.getOriginalFilename(), file.getSize());
    }

    @PostMapping(
            path = "/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public DocumentResponse document(
            @Valid @RequestPart("metadata") DocumentMeta metadata,
            @RequestPart("file") MultipartFile file) {
        requireNonEmpty(file);
        return new DocumentResponse(metadata.title(), file.getSize());
    }

    private static void requireNonEmpty(MultipartFile file) {
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "file is empty");
        }
    }

    public record SearchResponse(String q, int page, List<String> tags) {}
    public record ContactResponse(String name, String email) {}
    public record OrderInput(
            @NotBlank String productId,
            @Min(1) int quantity) {}
    public record OrderResponse(
            String productId, int quantity, long totalCents) {}
    public record UploadResponse(
            String description, String originalFilename, long size) {}
    public record DocumentMeta(@NotBlank String title) {}
    public record DocumentResponse(String title, long size) {}

    public static class ContactForm {
        @NotBlank
        private String name;

        @NotBlank
        @Email
        private String email;

        public ContactForm() {}

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }
}
~~~

Lệnh chạy tại thư mục có `pom.xml` (cần JDK 17+ và Maven):

~~~bash
java -version
mvn spring-boot:run
~~~

Mở terminal thứ hai để gửi request. Các lệnh dưới đây dùng **bash/curl**; trên Windows có thể dùng `curl.exe` và sửa cách đặt dấu nháy theo PowerShell/CMD. Ví dụ response chỉ thể hiện JSON body; các header và dữ liệu động của server được lược bỏ.

**A. Query parameter**

~~~bash
curl -s "http://localhost:8080/api/products?q=java%20web&page=2&tag=spring&tag=http"
~~~

~~~json
{"q":"java web","page":2,"tags":["spring","http"]}
~~~

Nếu bỏ `page` thì nhận giá trị mặc định 1. Nếu truyền `page=abc`, chuyển kiểu sang `int` thất bại và server trả 400. Nếu truyền `page=0`, nhánh kiểm tra của controller trả 400.

**B. Form URL-encoded**

~~~bash
curl -s -X POST http://localhost:8080/api/contacts \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "email=lan@example.com"
~~~

~~~json
{"name":"Lan","email":"lan@example.com"}
~~~

`--data-urlencode` giúp encode dữ liệu người dùng. `email` sai định dạng hoặc `name` chỉ chứa khoảng trắng sẽ không qua `@Valid` và trả 400.

**C. JSON**

~~~bash
curl -s -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"productId":"P-7","quantity":3}'
~~~

~~~json
{"productId":"P-7","quantity":3,"totalCents":3000}
~~~

`totalCents` ở đây chỉ là **công thức minh họa cố định 1000 cent/đơn vị**, không phải phép tính giá thực tế. Gửi `quantity=0` sẽ vi phạm `@Min(1)`. Gửi JSON vào endpoint `/api/contacts` không phù hợp `consumes`; ngược lại gửi URL-encoded vào `/api/orders` cũng sai media type.

**D. Multipart text + file**

~~~bash
printf hello > sample.txt
curl -s -X POST http://localhost:8080/api/uploads \
  -F "description=Hoa don" \
  -F "file=@sample.txt;type=text/plain"
~~~

~~~json
{"description":"Hoa don","originalFilename":"sample.txt","size":5}
~~~

Lệnh `printf hello` tạo đúng **5 byte** trong file. Tên file và kích thước trong response đến từ file thực tế client upload; nếu tạo file theo cách khác, `size` có thể thay đổi.

**E. Multipart JSON part + file part**

~~~bash
curl -s -X POST http://localhost:8080/api/documents \
  -F 'metadata={"title":"Hoa don"};type=application/json' \
  -F 'file=@sample.txt;type=text/plain'
~~~

~~~json
{"title":"Hoa don","size":5}
~~~

`;type=application/json` trên part `metadata` là điểm mấu chốt: Spring dùng converter để chuyển JSON part thành `DocumentMeta`. Nếu gửi part ấy chỉ như text thông thường, media type của part có thể không tương thích và trả 415.

## 7. Browser client: chọn cách gửi đúng

**JSON từ `fetch`:**

~~~javascript
const response = await fetch("/api/orders", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ productId: "P-7", quantity: 3 })
});
if (!response.ok) throw new Error("Request failed: " + response.status);
const order = await response.json();
~~~

**Multipart từ `FormData`:**

~~~javascript
const data = new FormData();
data.append("description", "Hoa don");
data.append("file", fileInput.files[0]); // fileInput là <input type="file">
const response = await fetch("/api/uploads", { method: "POST", body: data });
// Không tự thêm Content-Type: browser sẽ tạo boundary.
~~~

Nếu cần JSON part trong browser, dùng `Blob` có media type rõ ràng:

~~~javascript
const form = new FormData();
form.append(
  "metadata",
  new Blob([JSON.stringify({ title: "Hoa don" })],
           { type: "application/json" }));
form.append("file", fileInput.files[0]);
await fetch("/api/documents", { method: "POST", body: form });
~~~

## 8. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| HTTP **400** và thiếu `@RequestParam` | Tên key khác với annotation hoặc thiếu tham số bắt buộc | So tên trong URL/form, đặt `required=false` hoặc `defaultValue` khi đúng nghiệp vụ |
| HTTP **400** khi `page=abc` | Không chuyển text sang `int` được | Kiểm tra dữ liệu trước khi gửi, phản hồi lỗi đầu vào rõ ràng |
| HTTP **400** với `@Valid` | DTO vi phạm `@NotBlank`, `@Min`, `@Email`… | Sửa payload; ứng dụng có thể chuẩn hóa lỗi qua `@RestControllerAdvice` |
| HTTP **400** do JSON malformed | JSON thiếu dấu, body rỗng, kiểu dữ liệu không khớp | Dùng JSON validator và kiểm tra `Content-Type` |
| HTTP **415** | `consumes` không khớp `Content-Type`, hoặc JSON multipart part thiếu media type | Gửi đúng media type cả request và từng part |
| HTTP **413** hoặc lỗi multipart size | File/request vượt giới hạn app, container hoặc proxy | Thiết lập giới hạn phù hợp và đồng bộ giữa các tầng |
| `@RequestBody` không nhận form | Form URL-encoded không tương ứng JSON conversion | Dùng `@RequestParam`/`@ModelAttribute` cho form |
| `@RequestPart` không bind JSON | Part `metadata` là text/plain thay vì application/json | Gửi part với `Content-Type: application/json` |
| Mất dấu tiếng Việt/ký tự `+` | Encode không đúng hoặc decode thủ công nhiều lần | Dùng client hỗ trợ UTF-8 và URL encoding, chỉ decode một lần |
| Upload thành công nhưng file không tồn tại | Controller chỉ đọc `MultipartFile`, chưa lưu bền vững | Ghi stream vào storage trong request, lưu metadata riêng |
| File chứa nội dung nguy hiểm/path traversal | Tin tên/loại file do client cung cấp | Kiểm tra nội dung, quyền, tên lưu do server sinh, thư mục an toàn |

**Validation và xử lý lỗi:** `@Valid` với `@RequestBody`/`@RequestPart`/`@ModelAttribute` có thể phát sinh `MethodArgumentNotValidException`. Với constraints đặt trực tiếp trên method parameters, Spring MVC còn có thể dùng `HandlerMethodValidationException`. API nên chuẩn hóa response lỗi thông qua `@RestControllerAdvice` hoặc `ResponseEntityExceptionHandler`, nhưng không cần tự xử lý từng exception để học bốn cơ chế binding này.

## 9. Nguyên tắc chọn giải pháp và bài tập tự kiểm tra

Chọn theo **nguồn dữ liệu và mục đích**: điều kiện tìm kiếm → **query**; form trường text đơn giản → **URL-encoded form**; cấu trúc object/list cho REST API → **JSON**; file nhị phân và thông tin đi kèm → **multipart**. `@RequestParam` trên Servlet MVC có thể cùng xử lý query/form; `@RequestBody` đọc JSON body; `@RequestPart` chuyển đổi từng multipart part.

Tự kiểm tra với ứng dụng mẫu:
1. Gửi `GET /api/products?tag=A&tag=B`; dự đoán `tags` và `page`; thử `page=0` hoặc `page=xyz`.
2. Gửi form `name=   ` và `email=not-email`; quan sát HTTP 400 từ Bean Validation.
3. Gửi `POST /api/orders` với body JSON nhưng không đặt header `Content-Type`; so sánh với header chính xác.
4. Gửi `metadata` của multipart như plain text, rồi thêm `;type=application/json` để so kết quả.
5. Tạo file lớn hơn cấu hình `spring.servlet.multipart.max-file-size` và xác định tầng nào từ chối request trong môi trường của bạn.

**Tài liệu chính thức để đối chiếu:**
- Spring MVC `@RequestParam`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring MVC `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring MVC multipart và `@RequestPart`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring MVC validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot multipart configuration: https://docs.spring.io/spring-boot/appendix/application-properties/
