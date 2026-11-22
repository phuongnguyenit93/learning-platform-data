# Phản hồi văn bản, JSON, XML và nhiều media type

Một REST API có thể trả về văn bản thuần, JSON, XML hoặc nhiều định dạng cho cùng một operation. Trong Spring MVC, kiểu dữ liệu trả về, `ResponseEntity`, thuộc tính `produces` và các `HttpMessageConverter` quyết định nội dung response thực tế. Springdoc mô tả những định dạng đó trong phần `responses.content` của OpenAPI để client biết có thể nhận loại dữ liệu nào.

Khi mô tả response, cần giữ ba phần nhất quán: controller phải tạo đúng nội dung, Spring phải chọn được converter phù hợp, và OpenAPI phải công bố đúng media type cùng schema. Thêm một `@Content` vào tài liệu không tự làm ứng dụng có khả năng serialize XML hoặc trả về văn bản thuần.

## 1. Response media type trong HTTP và OpenAPI

Response HTTP có status code, header và có thể có body. Header `Content-Type` cho biết định dạng của body thực tế:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "title": "Spring Boot căn bản"
}
```

Trong OpenAPI 3, nội dung response được mô tả theo từng status code và media type:

```yaml
responses:
  '200':
    description: Tìm thấy sách
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/BookResponse'
```

Mỗi key trong `content` là một media type mà operation có thể trả về. Giá trị của nó chứa schema và có thể chứa `example`, `examples` hoặc encoding phù hợp. Một response có thể công bố nhiều media type.

| Thành phần | Vai trò |
| --- | --- |
| `Content-Type` của response | Định dạng body server thực sự gửi |
| `Accept` của request | Định dạng response client muốn nhận |
| `produces` trong Spring mapping | Giới hạn media type response mà handler công bố hỗ trợ |
| `responses.content` trong OpenAPI | Mô tả media type, schema và ví dụ của response |
| `HttpMessageConverter` | Chuyển đối tượng Java thành body theo media type |

Không nhầm `requestBody.content` với `responses.content`: phần thứ nhất mô tả dữ liệu client gửi lên, phần thứ hai mô tả dữ liệu server trả về.

## 2. Phản hồi văn bản thuần với `text/plain`

Với endpoint trả về một chuỗi văn bản thuần, có thể dùng `String` và khai báo `produces = MediaType.TEXT_PLAIN_VALUE`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping(path = "/api/status", produces = MediaType.TEXT_PLAIN_VALUE)
    @Operation(
        summary = "Lấy trạng thái dịch vụ",
        responses = @ApiResponse(
            responseCode = "200",
            description = "Trạng thái dạng văn bản",
            content = @Content(
                mediaType = MediaType.TEXT_PLAIN_VALUE,
                schema = @Schema(type = "string", example = "UP"),
                examples = @ExampleObject(value = "UP")
            )
        )
    )
    public ResponseEntity<String> status() {
        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .body("UP");
    }
}
```

Response thực tế có body là `UP` và `Content-Type: text/plain`. Trong OpenAPI, schema có kiểu `string`. Không mô tả body này như một object JSON.

Thử bằng curl:

```bash
curl -i -H "Accept: text/plain" http://localhost:8080/api/status
```

Nếu endpoint trả về `String` nhưng không khai báo rõ `produces` hoặc media type, việc chọn converter và định dạng có thể không như người đọc dự đoán. Với API công khai, hãy khai báo rõ media type và kiểm tra `Content-Type` thực tế.

## 3. Phản hồi JSON bằng DTO

JSON thường được dùng cho response có cấu trúc. Nên trả về DTO thay vì ghép chuỗi JSON thủ công:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Thông tin sách trả về cho client")
public record BookResponse(
    @Schema(description = "Mã sách", example = "42")
    long id,

    @Schema(description = "Tên sách", example = "Spring Boot căn bản")
    String title
) {}
```

Controller:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookQueryController {

    @GetMapping(path = "/api/books/42", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
        summary = "Lấy thông tin sách",
        responses = @ApiResponse(
            responseCode = "200",
            description = "Thông tin sách",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = BookResponse.class),
                examples = @ExampleObject(
                    name = "BookJson",
                    summary = "Thông tin sách ở dạng JSON",
                    value = "{\"id\":42,\"title\":\"Spring Boot căn bản\"}"
                )
            )
        )
    )
    public ResponseEntity<BookResponse> getBook() {
        return ResponseEntity.ok(new BookResponse(42L, "Spring Boot căn bản"));
    }
}
```

Spring Boot thường dùng Jackson để chuyển DTO thành JSON. Springdoc có thể suy ra schema từ kiểu trả về; `@Schema` và `@ExampleObject` bổ sung mô tả và payload mẫu cho người tích hợp.

Request thử:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/api/books/42
```

Response có `Content-Type: application/json` và object JSON. Không nên trả một chuỗi đã nối thủ công như `"{\"id\":42}"` rồi kỳ vọng đó tương đương với một DTO; kiểu trả về `String` và kiểu trả về object có thể được xử lý bởi converter khác nhau.

## 4. Phản hồi XML và cấu hình message converter

Để trả XML, ứng dụng cần một converter XML. Với Spring Boot dùng Jackson, có thể thêm dependency sau và để Spring Boot quản lý phiên bản:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
```

DTO có thể dùng annotation Jackson XML để xác định tên root element và property:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.media.XML;

@JacksonXmlRootElement(localName = "book")
@Schema(xml = @XML(name = "book"))
public class BookRepresentation {

    private long id;

    @JacksonXmlProperty(localName = "title")
    private String title;

    public BookRepresentation() {}

    public BookRepresentation(long id, String title) {
        this.id = id;
        this.title = title;
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

Controller:

```java
@GetMapping(path = "/api/books/42.xml", produces = MediaType.APPLICATION_XML_VALUE)
@Operation(
    summary = "Lấy thông tin sách ở dạng XML",
    responses = @ApiResponse(
        responseCode = "200",
        description = "Thông tin sách ở dạng XML",
        content = @Content(
            mediaType = MediaType.APPLICATION_XML_VALUE,
            schema = @Schema(implementation = BookRepresentation.class),
            examples = @ExampleObject(
                name = "BookXml",
                value = "<book><id>42</id><title>Spring Boot căn bản</title></book>"
            )
        )
    )
)
public ResponseEntity<BookRepresentation> getBookXml() {
    return ResponseEntity.ok(new BookRepresentation(42L, "Spring Boot căn bản"));
}
```

XML response mẫu:

```xml
<book>
    <id>42</id>
    <title>Spring Boot căn bản</title>
</book>
```

Thử request:

```bash
curl -i -H "Accept: application/xml" http://localhost:8080/api/books/42.xml
```

`produces = application/xml` và `@Content(mediaType = application/xml)` chỉ mô tả mapping và hợp đồng. Nếu converter XML chưa được cài hoặc cấu hình, Spring không thể tự serialize object thành XML. Với XML có namespace, attribute hoặc cấu trúc lồng phức tạp, cần cấu hình Jackson XML/JAXB và kiểm tra body thực tế.

## 5. Một operation trả JSON hoặc XML

Nếu cùng một operation hỗ trợ JSON và XML, khai báo cả hai media type trong `produces`. Trong OpenAPI, một response có thể chứa nhiều mục `@Content`, mỗi mục mô tả schema và ví dụ cho một định dạng:

```java
@GetMapping(
    path = "/api/books/42",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
@Operation(
    summary = "Lấy thông tin sách",
    responses = @ApiResponse(
        responseCode = "200",
        description = "Thông tin sách",
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = BookRepresentation.class),
                examples = @ExampleObject(
                    name = "BookJson",
                    value = "{\"id\":42,\"title\":\"Spring Boot căn bản\"}"
                )
            ),
            @Content(
                mediaType = MediaType.APPLICATION_XML_VALUE,
                schema = @Schema(implementation = BookRepresentation.class),
                examples = @ExampleObject(
                    name = "BookXml",
                    value = "<book><id>42</id><title>Spring Boot căn bản</title></book>"
                )
            )
        }
    )
)
public ResponseEntity<BookRepresentation> getBookByNegotiation() {
    // Cùng DTO được serialize thành JSON hoặc XML theo Accept;
    // XML converter sử dụng các annotation Jackson XML trên DTO.
    return ResponseEntity.ok(new BookRepresentation(42L, "Spring Boot căn bản"));
}
```

Đoạn code trên minh họa metadata OpenAPI cho hai representation. Khi triển khai, chọn một DTO và converter thực sự hỗ trợ cả hai định dạng, hoặc dùng các kiểu response tương ứng với thiết kế API. Không khai báo `application/xml` nếu converter không thể tạo đúng XML theo schema và example.

Nếu dùng cùng một DTO cho JSON và XML, hãy kiểm tra cách Jackson JSON và Jackson XML serialize DTO đó. Với XML cần tên root element hoặc tên field riêng, có thể dùng annotation Jackson XML; bảo đảm thay đổi đó không làm sai JSON response.

Trong OpenAPI, kết quả có dạng:

```yaml
responses:
  '200':
    description: Thông tin sách
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/BookRepresentation'
        example:
          id: 42
          title: Spring Boot căn bản
      application/xml:
        schema:
          $ref: '#/components/schemas/BookRepresentation'
        example: <book><id>42</id><title>Spring Boot căn bản</title></book>
```

## 6. Content negotiation với header `Accept`

Client có thể gửi `Accept` để nêu định dạng response mong muốn:

```http
GET /api/books/42 HTTP/1.1
Accept: application/xml
```

Nếu handler khai báo hỗ trợ JSON và XML, Spring MVC sẽ chọn representation phù hợp dựa trên `Accept`, `produces` và các converter có sẵn. Khi client yêu cầu định dạng không được hỗ trợ, Spring có thể trả `406 Not Acceptable`.

Ví dụ kiểm tra cùng endpoint:

```bash
# Yêu cầu JSON
curl -i -H "Accept: application/json" http://localhost:8080/api/books/42

# Yêu cầu XML
curl -i -H "Accept: application/xml" http://localhost:8080/api/books/42

# Yêu cầu định dạng không được hỗ trợ
curl -i -H "Accept: text/csv" http://localhost:8080/api/books/42
```

Khi kiểm tra, quan sát `Content-Type` response thực tế. `Accept` là yêu cầu ưu tiên từ client; `Content-Type` là định dạng server đã gửi. Nếu request có nhiều media type kèm quality factor (`q`), Spring content negotiation có thể chọn định dạng phù hợp theo mức ưu tiên và cấu hình. Không nên giả định client luôn nhận định dạng đầu tiên nếu mapping hoặc converter không hỗ trợ nó.

## 7. Nhiều ví dụ cho cùng một media type

Nếu response chỉ có một media type nhưng cần nhiều ví dụ, khai báo nhiều `@ExampleObject` bên trong một `@Content`:

```java
@ApiResponse(
    responseCode = "200",
    description = "Thông tin sản phẩm",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class),
        examples = {
            @ExampleObject(
                name = "AvailableProduct",
                summary = "Sản phẩm còn hàng",
                value = "{\"id\":1,\"name\":\"Keyboard\",\"available\":true}"
            ),
            @ExampleObject(
                name = "UnavailableProduct",
                summary = "Sản phẩm hết hàng",
                value = "{\"id\":2,\"name\":\"Mouse\",\"available\":false}"
            )
        }
    )
)
```

Hai ví dụ cùng thuộc `application/json`; chúng không phải hai media type. Nếu response hỗ trợ XML, hãy thêm một `@Content(mediaType = application/xml, ...)` riêng.

Ví dụ phải phù hợp schema và thể hiện dữ liệu mà server thực sự có thể trả. Không đưa thông tin cá nhân, token, cookie phiên hoặc dữ liệu khách hàng thật vào example công khai.

## 8. Phản hồi lỗi cũng cần mô tả media type

Response lỗi thường có cấu trúc riêng. Ví dụ ứng dụng dùng một DTO lỗi:

```java
public record ApiError(
    String code,
    String message
) {}
```

Có thể mô tả response lỗi bằng `@ApiResponse`:

```java
@ApiResponse(
    responseCode = "404",
    description = "Không tìm thấy sách",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiError.class),
        examples = @ExampleObject(
            value = "{\"code\":\"BOOK_NOT_FOUND\",\"message\":\"Không tìm thấy sách\"}"
        )
    )
)
```

Nếu exception handler trả lỗi dưới dạng `application/problem+json`, hãy công bố đúng media type và schema của Problem Details. Nếu lỗi được trả bằng `text/plain`, schema phải là `string`. Metadata response phải khớp với `@RestControllerAdvice`, gateway hoặc cơ chế xử lý lỗi đang được sử dụng.

Không khai báo response body cho status không có body. Ví dụ `204 No Content` thường chỉ cần mô tả status và description, không cần `content`:

```java
@ApiResponse(responseCode = "204", description = "Xóa thành công")
```

## 9. Dùng `ResponseEntity` để kiểm soát status và header

`ResponseEntity` cho phép controller quyết định status code, header và body. Điều này hữu ích khi API trả nhiều media type hoặc cần đặt `Content-Type` cụ thể:

```java
return ResponseEntity.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(new BookResponse(42L, "Spring Boot căn bản"));
```

Hoặc response văn bản:

```java
return ResponseEntity.ok()
    .contentType(MediaType.TEXT_PLAIN)
    .body("UP");
```

Khi dùng content negotiation, thường để Spring chọn media type theo `Accept` và converter; không ép `Content-Type` cố định nếu cùng operation cần trả nhiều representation. Nếu code tự đặt content type, hãy bảo đảm body thực sự khớp định dạng đó.

`ResponseEntity` không tự tạo tài liệu OpenAPI. Dùng `@ApiResponse` và `@Content` để mô tả status, media type và schema tương ứng.

## 10. Vai trò của `@ApiResponse`, `@Content` và `@Schema`

| Annotation | Vai trò trong response documentation |
| --- | --- |
| `@ApiResponse` | Mô tả một HTTP status code và ý nghĩa của response |
| `@ApiResponses` | Gom nhiều response status cho một operation |
| `@Content` | Mô tả nội dung theo media type |
| `@Schema` | Chỉ định cấu trúc dữ liệu response |
| `@ExampleObject` | Cung cấp payload mẫu cho một media type |
| `@Operation` | Gắn các response metadata với operation |

Springdoc có thể suy ra response schema từ kiểu trả về của controller. Khi dùng `ResponseEntity<BookResponse>`, thư viện có thể đọc kiểu body `BookResponse`. Dùng `@ApiResponse` tường minh khi cần mô tả nhiều status, media type, ví dụ hoặc schema khác với suy luận mặc định.

Không nên khai báo lại metadata phức tạp ở nhiều nơi nếu kết quả suy ra đã chính xác. Nếu annotation tường minh override kết quả tự động, kiểm tra tài liệu cuối cùng để chắc chắn không bị mất response hoặc media type.

## 11. Cấu hình converter và mapping phải khớp tài liệu

Spring MVC sử dụng `HttpMessageConverter` để chuyển đối tượng Java thành response body. Một số converter thường gặp:

| Converter | Dữ liệu thường xử lý |
| --- | --- |
| `StringHttpMessageConverter` | Chuỗi văn bản |
| `MappingJackson2HttpMessageConverter` | JSON qua Jackson |
| `MappingJackson2XmlHttpMessageConverter` | XML qua Jackson XML khi dependency và converter được cấu hình |
| `ByteArrayHttpMessageConverter` | Dữ liệu byte/binary |

Danh sách converter thực tế phụ thuộc dependency, cấu hình MVC và các bean do ứng dụng đăng ký. Một media type có trong `produces` nhưng không có converter phù hợp vẫn có thể gây lỗi khi ghi response.

Khi bổ sung converter tùy chỉnh, kiểm tra cả thứ tự và media type mà converter hỗ trợ. Converter có thể hỗ trợ nhiều media type hoặc ưu tiên kiểu dữ liệu nhất định; điều này đặc biệt quan trọng khi controller trả `String` hoặc kiểu chung.

## 12. Kiểm tra response trong OpenAPI và Swagger UI

Sau khi khởi động ứng dụng, mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`. Với từng operation, kiểm tra:

1. Mã response (`200`, `201`, `204`, `400`, `404`...) có đúng với hành vi controller.
2. `responses.content` liệt kê đúng media type.
3. Schema của JSON/XML/text phản ánh body thực tế.
4. Example hợp lệ với schema và media type tương ứng.
5. Response không có body không bị khai báo `content` sai.
6. Error response khớp định dạng do exception handler trả về.

Trong Swagger UI, mở phần Responses để xem các status và media type. Một số phiên bản UI cho phép xem ví dụ response, nhưng Swagger UI không tự chứng minh server thực sự trả payload đó. Hãy gửi request và kiểm tra header `Content-Type`, status code và body.

Ví dụ lệnh kiểm tra:

```bash
# Văn bản thuần
curl -i -H "Accept: text/plain" http://localhost:8080/api/status

# JSON
curl -i -H "Accept: application/json" http://localhost:8080/api/books/42

# XML
curl -i -H "Accept: application/xml" http://localhost:8080/api/books/42
```

Điều chỉnh URL theo mapping thực tế. Nếu dùng cùng endpoint cho JSON và XML, gọi cùng URL với các giá trị `Accept` khác nhau và so sánh `Content-Type` trả về.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Response body là JSON nhưng tài liệu ghi XML | `@Content.mediaType` hoặc `produces` không khớp | Đồng bộ mapping, metadata và converter |
| Request XML nhận `406 Not Acceptable` | Client gửi `Accept` không được endpoint hỗ trợ | Kiểm tra `Accept` và `produces` |
| Không serialize được XML | Thiếu XML converter hoặc DTO không tương thích | Thêm/configure Jackson XML hoặc JAXB và kiểm tra DTO |
| `Content-Type` response không như mong đợi | Converter được chọn khác dự kiến hoặc code đặt header không đúng | Kiểm tra converter, `produces` và response thực tế |
| Swagger UI không hiển thị media type | `responses.content` thiếu `@Content` tương ứng hoặc UI tải tài liệu cũ | Kiểm tra `/v3/api-docs` và tải lại UI |
| Response `String` bị xử lý khác JSON object | String converter và Jackson converter có cách ghi khác nhau | Dùng DTO cho JSON; khai báo rõ `text/plain` cho văn bản |
| Tài liệu công bố response lỗi không tồn tại | `@ApiResponse` không khớp exception handler | Mô tả response lỗi thực tế hoặc cập nhật handler |
| `204` hiển thị body không cần thiết | Khai báo `content` cho response không có body | Bỏ `content` và chỉ mô tả status/description |
| Client không nhận được media type mong muốn | Media type không được converter hỗ trợ hoặc `Accept` không khớp | Kiểm tra negotiation và converter runtime |

## 14. Checklist cho phản hồi nhiều định dạng

- [ ] `produces` liệt kê đúng media type mà endpoint thực sự trả.
- [ ] `Accept` được hiểu là yêu cầu định dạng response từ client.
- [ ] `responses.content` có một mục cho mỗi media type được hỗ trợ.
- [ ] JSON dùng schema DTO phù hợp.
- [ ] XML có converter và mapping XML được cấu hình, kiểm thử.
- [ ] Văn bản thuần dùng `text/plain` và schema `string`.
- [ ] Nhiều ví dụ của cùng định dạng được đặt trong một `@Content`; nhiều định dạng dùng nhiều `@Content`.
- [ ] Error response và response thành công có status, media type và schema chính xác.
- [ ] Response không có body như `204` không khai báo content.
- [ ] Đã kiểm tra OpenAPI JSON/YAML, Swagger UI và response HTTP thực tế.

Springdoc công bố response media type và schema để client hiểu định dạng server có thể trả. Spring MVC cùng các message converter quyết định body thực tế. Khi `produces`, converter, `ResponseEntity` và `@ApiResponse` được đồng bộ, API có thể hỗ trợ văn bản, JSON, XML hoặc nhiều representation mà tài liệu vẫn phản ánh đúng hành vi.
