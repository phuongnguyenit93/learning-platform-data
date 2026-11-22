# Ví dụ thân yêu cầu theo từng media type

Một REST API có thể nhận nhiều định dạng dữ liệu. Client gửi định dạng của request body qua header `Content-Type`; Spring MVC chọn bộ chuyển đổi phù hợp để đọc dữ liệu, còn Springdoc mô tả định dạng đó trong OpenAPI. Mỗi media type có thể dùng một schema và ví dụ riêng, vì vậy tài liệu cần phản ánh đúng những gì endpoint thực sự hỗ trợ.

Trong Springdoc, phần request body được khai báo bằng `@io.swagger.v3.oas.annotations.parameters.RequestBody`. Các mục `@Content` bên trong xác định media type; `@Schema` mô tả cấu trúc dữ liệu; `@ExampleObject` cung cấp payload mẫu; `@Encoding` mô tả cách mã hóa từng phần của multipart request. Controller vẫn dùng annotation Spring như `@RequestBody`, `@ModelAttribute` hoặc `@RequestPart` để nhận dữ liệu thực tế.

## 1. Phân biệt `Content-Type` và `Accept`

Hai header thường xuất hiện trong request nhưng có ý nghĩa khác nhau:

- `Content-Type` mô tả định dạng nội dung mà client đang gửi lên server.
- `Accept` mô tả định dạng response mà client muốn nhận từ server.

Ví dụ:

```http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "title": "Spring Boot căn bản"
}
```

Ở đây, `Content-Type` cho biết body là JSON; `Accept` cho biết client muốn response JSON. Trong Spring MVC, thuộc tính `consumes` của `@PostMapping` thường ràng buộc media type request, còn `produces` ràng buộc media type response.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Content-Type` | Định dạng body gửi lên | `application/json` |
| `Accept` | Định dạng response mong muốn | `application/json` |
| `consumes` | Media type endpoint chấp nhận | `application/json`, `application/xml` |
| `produces` | Media type endpoint có thể trả về | `application/json` |
| `requestBody.content` | Các media type được công bố trong OpenAPI | `application/json`, `multipart/form-data` |

Nếu client gửi `Content-Type` mà endpoint không chấp nhận, Spring thường trả về `415 Unsupported Media Type`. Nếu server không thể tạo response theo `Accept`, có thể xảy ra `406 Not Acceptable`. Tài liệu cần liệt kê đúng định dạng được triển khai để client chọn request phù hợp.

## 2. Cấu trúc nhiều media type trong OpenAPI

OpenAPI đặt các định dạng được hỗ trợ bên trong `requestBody.content`. Mỗi key là một media type và mỗi value chứa schema, ví dụ hoặc encoding tương ứng:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/BookRequest'
      example:
        title: Spring Boot căn bản
    application/xml:
      schema:
        $ref: '#/components/schemas/BookRequest'
      example: <BookRequest><title>Spring Boot căn bản</title></BookRequest>
```

Hai media type có thể biểu diễn cùng một thông tin nghiệp vụ nhưng dùng cú pháp payload khác nhau. JSON sử dụng object và property; XML sử dụng element và attribute. Việc dùng chung một schema chỉ phù hợp khi cấu trúc dữ liệu của hai biểu diễn thực sự tương ứng.

## 3. `application/json`: DTO và `@RequestBody`

JSON là định dạng phổ biến cho REST API. Spring MVC dùng `@RequestBody` để chuyển JSON thành DTO thông qua `HttpMessageConverter`, thường là Jackson trong ứng dụng Spring Boot Web.

DTO minh họa:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Thông tin sách cần tạo")
public record BookRequest(
    @Schema(description = "Tên sách", example = "Spring Boot căn bản")
    String title,

    @Schema(description = "Năm xuất bản", example = "2025")
    Integer publicationYear
) {}
```

Controller có thể khai báo:

```java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Tạo sách bằng JSON",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Payload JSON của sách",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = BookRequest.class),
            examples = @ExampleObject(
                name = "BookJson",
                summary = "Sách có năm xuất bản",
                value = "{\"title\":\"Spring Boot căn bản\",\"publicationYear\":2025}"
            )
        )
    )
)
public BookResponse createJson(@RequestBody BookRequest request) {
    return new BookResponse(request.title(), request.publicationYear());
}
```

Trong code có hai annotation `RequestBody`: annotation Spring trên tham số method đọc HTTP body; annotation OpenAPI bên trong `@Operation` mô tả hợp đồng. Nếu Springdoc đã suy ra đúng JSON schema từ DTO, không bắt buộc phải khai báo lại toàn bộ `@Content`; cấu hình tường minh hữu ích khi cần mô tả, media type hoặc example cụ thể.

Request mẫu:

```bash
curl -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"title":"Spring Boot căn bản","publicationYear":2025}'
```

## 4. `application/xml`: XML body và message converter

Nếu API cần nhận XML, khai báo `application/xml` trong `consumes` và mô tả media type này trong OpenAPI. Spring MVC phải có `HttpMessageConverter` hỗ trợ XML. Với Spring Boot, một lựa chọn thường dùng là thêm Jackson XML:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
```

Khi dùng Spring Boot dependency management, để Boot quản lý phiên bản Jackson tương thích. Việc thêm media type vào annotation OpenAPI tự nó không cài converter và không khiến endpoint có thể đọc XML.

Ví dụ controller nhận cùng DTO dưới dạng XML:

```java
@PostMapping(
    path = "/api/books/xml",
    consumes = MediaType.APPLICATION_XML_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Tạo sách bằng XML",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Payload XML của sách",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_XML_VALUE,
            schema = @Schema(implementation = BookRequest.class),
            examples = @ExampleObject(
                name = "BookXml",
                summary = "Sách ở định dạng XML",
                value = "<BookRequest><title>Spring Boot căn bản</title><publicationYear>2025</publicationYear></BookRequest>"
            )
        )
    )
)
public BookResponse createXml(@RequestBody BookRequest request) {
    return new BookResponse(request.title(), request.publicationYear());
}
```

Ví dụ XML cần khớp với quy tắc mapping của converter và DTO. Với XML có namespace, attribute, wrapper hoặc tên element tùy chỉnh, cần cấu hình Jackson XML/JAXB tương ứng và kiểm tra payload thực tế. Schema OpenAPI dạng JSON Schema không mô tả mọi chi tiết XML một cách tự động; nếu cấu trúc XML có quy tắc đặc biệt, hãy bổ sung metadata XML phù hợp và xác minh tài liệu được sinh ra.

Request mẫu:

```bash
curl -X POST http://localhost:8080/api/books/xml \
  -H "Content-Type: application/xml" \
  -H "Accept: application/json" \
  -d '<BookRequest><title>Spring Boot căn bản</title><publicationYear>2025</publicationYear></BookRequest>'
```

## 5. Một operation nhận cả JSON và XML

Nếu cùng một endpoint hỗ trợ cả hai định dạng, khai báo cả hai trong `consumes` và có hai `@Content` riêng trong OpenAPI request body:

```java
@PostMapping(
    path = "/api/books/import",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    },
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Nhập sách bằng JSON hoặc XML",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = BookRequest.class),
                examples = @ExampleObject(
                    name = "JsonPayload",
                    value = "{\"title\":\"Spring Boot căn bản\",\"publicationYear\":2025}"
                )
            ),
            @Content(
                mediaType = MediaType.APPLICATION_XML_VALUE,
                schema = @Schema(implementation = BookRequest.class),
                examples = @ExampleObject(
                    name = "XmlPayload",
                    value = "<BookRequest><title>Spring Boot căn bản</title><publicationYear>2025</publicationYear></BookRequest>"
                )
            )
        }
    )
)
public BookResponse importBook(@RequestBody BookRequest request) {
    return new BookResponse(request.title(), request.publicationYear());
}
```

Spring chọn converter dựa trên `Content-Type` của request. Cả JSON và XML converter phải hoạt động trong runtime. Trong Swagger UI, người dùng có thể chọn media type và payload ví dụ tương ứng.

Không khai báo nhiều `@Content` chỉ vì muốn cung cấp nhiều ví dụ. Nhiều `@Content` là nhiều media type; nhiều payload của cùng một media type nên dùng nhiều `@ExampleObject` bên trong một `@Content`.

## 6. `application/x-www-form-urlencoded`: dữ liệu form đơn giản

`application/x-www-form-urlencoded` thường được dùng bởi HTML form. Các field được gửi thành cặp key/value, ví dụ:

```http
POST /api/contact HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Lan&email=lan%40example.com&message=Hello
```

Trong Spring MVC, form URL encoded thường được đọc qua request parameters và bind vào `@ModelAttribute` hoặc các tham số `@RequestParam`. Đây là cách xử lý phù hợp với cơ chế Servlet; không nên mặc định dùng `@RequestBody` để đọc raw form body trong ứng dụng MVC.

DTO form:

```java
public class ContactForm {
    private String name;
    private String email;
    private String message;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
}
```

Controller:

```java
@PostMapping(
    path = "/api/contact",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
@Operation(
    summary = "Gửi biểu mẫu liên hệ",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Các trường của biểu mẫu liên hệ",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            schema = @Schema(implementation = ContactForm.class),
            examples = @ExampleObject(
                name = "ContactFormExample",
                value = "{\"name\":\"Lan\",\"email\":\"lan@example.com\",\"message\":\"Hello\"}"
            )
        )
    )
)
public ResponseEntity<Void> contact(@ModelAttribute ContactForm form) {
    // Xử lý form đã được Spring bind.
    return ResponseEntity.noContent().build();
}
```

Trong OpenAPI, schema form là object có các property tương ứng. Tên field phải khớp với thuộc tính DTO và cách bind của Spring. Springdoc có thể suy ra `@ModelAttribute` thành các parameter tùy phiên bản và cấu hình; khi hợp đồng cần thể hiện một request body `application/x-www-form-urlencoded`, hãy kiểm tra `/v3/api-docs` và dùng metadata request body tường minh như ví dụ. Tránh để tài liệu đồng thời mô tả cùng field vừa là query parameter vừa là form body nếu đó không phải hành vi thực tế.

Request mẫu:

```bash
curl -X POST http://localhost:8080/api/contact \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "message=Hello"
```

## 7. `multipart/form-data`: file và metadata

`multipart/form-data` cho phép gửi nhiều part trong một request, thường dùng khi tải file cùng metadata. Mỗi part có tên và có thể có content type riêng. Trong Spring MVC, dùng `MultipartFile` để nhận file và `@RequestPart` để nhận một part cụ thể.

DTO dùng để mô tả schema multipart:

```java
import io.swagger.v3.oas.annotations.media.Encoding;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.multipart.MultipartFile;

@Schema(description = "File và metadata của sách cần tải lên")
public record UploadBookRequest(
    @Schema(type = "string", format = "binary", description = "File bìa sách")
    MultipartFile file,

    @Schema(description = "Metadata sách ở định dạng JSON")
    CreateBookRequest metadata
) {}
```

Controller:

```java
import io.swagger.v3.oas.annotations.media.Encoding;

@PostMapping(
    path = "/api/books/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
@Operation(
    summary = "Tải file sách kèm metadata",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "File bìa và metadata sách",
        required = true,
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = UploadBookRequest.class),
            encoding = {
                @Encoding(name = "file", contentType = "image/png, image/jpeg"),
                @Encoding(name = "metadata", contentType = MediaType.APPLICATION_JSON_VALUE)
            }
        )
    )
)
public ResponseEntity<Void> uploadBook(
        @RequestPart("file") MultipartFile file,
        @RequestPart("metadata") CreateBookRequest metadata) {
    // Kiểm tra file và xử lý metadata.
    return ResponseEntity.accepted().build();
}
```

`@Encoding` mô tả content type của từng part. File thường được biểu diễn trong schema là `type: string`, `format: binary`; metadata JSON là object theo schema `CreateBookRequest`. Tên part trong schema và `@RequestPart` phải trùng nhau. Cấu hình multipart của Spring Boot và giới hạn kích thước file cũng phải phù hợp với nhu cầu triển khai.

Request mẫu:

```bash
curl -X POST http://localhost:8080/api/books/upload \
  -F "file=@cover.jpg;type=image/jpeg" \
  -F 'metadata={"title":"Spring Boot căn bản","publicationYear":2025};type=application/json'
```

Không tự đặt header `Content-Type: multipart/form-data` trong curl khi dùng `-F`; curl cần tự tạo boundary và thêm boundary vào header. Nếu tự đặt header mà thiếu boundary, server có thể không phân tách được các part.

## 8. `text/plain`: nội dung văn bản thuần

Một endpoint có thể nhận một chuỗi văn bản thuần, chẳng hạn nội dung ghi chú hoặc thông điệp đơn giản. Spring dùng `@RequestBody String` và media type `text/plain`:

```java
@PostMapping(
    path = "/api/notes",
    consumes = MediaType.TEXT_PLAIN_VALUE
)
@Operation(
    summary = "Tạo ghi chú văn bản",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Nội dung ghi chú dạng văn bản thuần",
        required = true,
        content = @Content(
            mediaType = MediaType.TEXT_PLAIN_VALUE,
            schema = @Schema(type = "string", example = "Gọi lại khách hàng vào ngày mai")
        )
    )
)
public ResponseEntity<Void> createNote(@RequestBody String note) {
    return ResponseEntity.accepted().build();
}
```

Request mẫu:

```bash
curl -X POST http://localhost:8080/api/notes \
  -H "Content-Type: text/plain; charset=UTF-8" \
  --data "Gọi lại khách hàng vào ngày mai"
```

Schema của body là `string`, không phải object JSON. Nếu chuỗi chứa cấu trúc dữ liệu có quy tắc, hãy cân nhắc định nghĩa định dạng rõ ràng hoặc dùng JSON thay vì để client tự suy đoán cách phân tích.

## 9. `application/octet-stream`: dữ liệu nhị phân

Khi endpoint nhận nội dung nhị phân thô, ví dụ file mà không cần multipart, có thể dùng `byte[]` hoặc kiểu stream phù hợp. OpenAPI thường biểu diễn payload này bằng schema `type: string`, `format: binary`:

```java
@PostMapping(
    path = "/api/archive",
    consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
@Operation(
    summary = "Tải lên dữ liệu nhị phân",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Nội dung file dạng binary",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            schema = @Schema(type = "string", format = "binary")
        )
    )
)
public ResponseEntity<Void> uploadArchive(@RequestBody byte[] content) {
    return ResponseEntity.accepted().build();
}
```

Với file lớn, nên cân nhắc cách xử lý stream hoặc lưu trữ theo luồng thay vì đọc toàn bộ file vào `byte[]`, để tránh tiêu thụ bộ nhớ quá mức. Giới hạn kích thước, kiểm tra loại file và quyền tải lên vẫn cần được thực thi ở server.

## 10. Vendor-specific media type

Một API có thể dùng media type riêng của tổ chức, ví dụ `application/vnd.example.book+json`. Hậu tố `+json` cho biết nội dung sử dụng cú pháp JSON, nhưng media type riêng có thể mang ý nghĩa về phiên bản hoặc hợp đồng chuyên biệt.

```java
public static final String BOOK_MEDIA_TYPE = "application/vnd.example.book+json";

@PostMapping(
    path = "/api/books/vendor",
    consumes = BOOK_MEDIA_TYPE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Tạo sách bằng vendor media type",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = BOOK_MEDIA_TYPE,
            schema = @Schema(implementation = BookRequest.class),
            examples = @ExampleObject(
                value = "{\"title\":\"Spring Boot căn bản\",\"publicationYear\":2025}"
            )
        )
    )
)
public BookResponse createVendor(@RequestBody BookRequest request) {
    return new BookResponse(request.title(), request.publicationYear());
}
```

Client phải gửi đúng `Content-Type` được công bố. Kiểm tra cấu hình message converter và content negotiation của ứng dụng để bảo đảm media type riêng được chấp nhận như mong đợi; hậu tố `+json` không tự bảo đảm mọi converter hoặc gateway đều chấp nhận nó.

## 11. Chọn annotation Spring phù hợp với từng loại body

| Media type | Cách nhận thường gặp trong Spring MVC | Dạng dữ liệu |
| --- | --- | --- |
| `application/json` | `@RequestBody` | DTO hoặc object |
| `application/xml` | `@RequestBody` với XML converter | DTO hoặc object |
| `application/x-www-form-urlencoded` | `@ModelAttribute`, `@RequestParam` | Các field form |
| `multipart/form-data` | `@RequestPart`, `MultipartFile`, đôi khi `@RequestParam` | Nhiều part, file và metadata |
| `text/plain` | `@RequestBody String` | Chuỗi văn bản |
| `application/octet-stream` | `@RequestBody byte[]` hoặc kiểu stream | Dữ liệu nhị phân |
| Vendor media type `+json` | `@RequestBody` với converter tương thích | DTO hoặc object JSON |

Springdoc có thể suy ra nhiều request body từ chữ ký controller. Khi cách bind của Spring không tương ứng trực tiếp với một OpenAPI request body, như form-urlencoded với `@ModelAttribute`, hãy mô tả tường minh và kiểm tra tài liệu sinh ra. Không để metadata OpenAPI mô tả một body mà controller không thực sự nhận.

## 12. Kiểm tra request body trong OpenAPI và Swagger UI

Sau khi chạy ứng dụng, mở `/v3/api-docs` hoặc `/v3/api-docs.yaml` và kiểm tra operation tương ứng. Với mỗi request body, xác minh:

1. `requestBody.required` có phản ánh đúng việc body có bắt buộc hay không.
2. `requestBody.content` liệt kê đúng các media type mà endpoint hỗ trợ.
3. Mỗi media type có schema phù hợp với payload thực tế.
4. Example hợp lệ với cú pháp và schema của media type.
5. Với multipart, tên part và `encoding` khớp với `@RequestPart`.
6. Với XML hoặc vendor media type, converter thực tế có hỗ trợ định dạng đã công bố.

Trong Swagger UI, mở operation và chọn media type phù hợp trong phần Request body. Kiểm tra payload mẫu được hiển thị đúng. Khi dùng **Try it out**, gửi request đến môi trường thử nghiệm và xem header `Content-Type` cùng body trong Network để xác minh UI gửi đúng định dạng.

Ví dụ kiểm tra nhanh bằng curl:

```bash
# JSON
curl -H "Content-Type: application/json" -d '{"title":"Book"}' http://localhost:8080/api/books

# XML
curl -H "Content-Type: application/xml" -d '<BookRequest><title>Book</title></BookRequest>' http://localhost:8080/api/books/xml

# Văn bản thuần
curl -H "Content-Type: text/plain" --data "A note" http://localhost:8080/api/notes
```

Các URL và payload cần điều chỉnh theo mapping thực tế của ứng dụng. Curl chỉ kiểm tra request đến server; tài liệu OpenAPI vẫn cần được kiểm tra riêng.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `415 Unsupported Media Type` | `Content-Type` không nằm trong `consumes` hoặc thiếu converter | Đồng bộ media type và cấu hình converter |
| `406 Not Acceptable` | Server không thể trả định dạng mà client yêu cầu qua `Accept` | Kiểm tra `produces` và response converter |
| XML được công bố nhưng request XML thất bại | Chưa cài hoặc cấu hình XML message converter | Thêm và cấu hình Jackson XML/JAXB phù hợp |
| Form field xuất hiện thành query parameter | Springdoc suy ra `@ModelAttribute` theo dạng parameter | Kiểm tra OpenAPI; mô tả request body form tường minh khi hợp đồng yêu cầu |
| Multipart thiếu part hoặc sai content type | Tên `@RequestPart`, schema hoặc `@Encoding` không khớp | Đồng bộ tên part và kiểm tra request thực tế |
| Multipart báo thiếu boundary | Client tự đặt header `Content-Type` mà không có boundary | Để trình duyệt hoặc curl tự tạo boundary |
| File lớn gây tốn bộ nhớ | Đọc toàn bộ payload vào `byte[]` hoặc giới hạn multipart quá thấp | Dùng streaming/lưu trữ theo luồng và cấu hình giới hạn hợp lý |
| Swagger UI chỉ hiển thị một định dạng | `requestBody.content` chỉ có một media type hoặc UI tải tài liệu cũ | Kiểm tra JSON OpenAPI và tải lại UI |
| Vendor media type không được nhận | Converter hoặc gateway không chấp nhận media type riêng | Kiểm tra cấu hình content negotiation và converter |

## 14. Checklist mô tả ví dụ theo media type

- [ ] `consumes` của endpoint khớp với media type request body.
- [ ] `Content-Type` được phân biệt rõ với `Accept` và `produces`.
- [ ] Mỗi media type trong `requestBody.content` có schema đúng.
- [ ] Ví dụ payload hợp lệ với cú pháp của JSON, XML, form hoặc định dạng tương ứng.
- [ ] JSON/XML được nhận qua converter phù hợp.
- [ ] Form-urlencoded được bind đúng qua `@ModelAttribute` hoặc `@RequestParam`.
- [ ] Multipart có tên part, schema file và `@Encoding` chính xác.
- [ ] Text và binary dùng schema tương ứng (`string` hoặc `string/binary`).
- [ ] Vendor media type được hỗ trợ thật ở runtime.
- [ ] Đã kiểm tra `/v3/api-docs`, Swagger UI và request thực tế.

Mỗi media type là một hợp đồng về cách client gửi dữ liệu. Spring MVC quyết định cách tiếp nhận và chuyển đổi payload; Springdoc mô tả các định dạng, schema và ví dụ để client tích hợp. Khi hai phần được giữ đồng bộ, Swagger UI có thể hướng dẫn người dùng chọn đúng định dạng và gửi đúng request cho từng operation.
