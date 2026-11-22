# Nhiều kiểu nội dung cho cùng một operation

Một endpoint có thể nhận cùng một dữ liệu dưới nhiều định dạng. Ví dụ, operation tạo đơn hàng có thể nhận JSON từ ứng dụng web và XML từ một hệ thống tích hợp cũ. Trong OpenAPI, các định dạng request được khai báo trong `requestBody.content`; mỗi media type có thể dùng cùng một schema hoặc một schema riêng.

Với Spring Boot, cần đồng bộ ba phần: mapping của controller phải chấp nhận các `Content-Type` tương ứng, message converter phải đọc được từng định dạng, và tài liệu springdoc phải mô tả đúng các media type cùng schema. Chỉ khai báo một kiểu nội dung trong OpenAPI không làm cho máy chủ tự động hỗ trợ kiểu đó.

## 1. Phân biệt Content-Type và Accept

Hai header HTTP này điều khiển hai hướng khác nhau:

| Header | Hướng áp dụng | Ý nghĩa |
| --- | --- | --- |
| `Content-Type` | Request gửi lên server | Cho biết phần body đang được mã hóa theo định dạng nào. |
| `Accept` | Response server gửi về client | Cho biết client muốn nhận response ở định dạng nào. |

Ví dụ client gửi JSON:

```http
POST /api/orders
Content-Type: application/json
Accept: application/json

{"customerId":"C-100","items":[{"sku":"KB-01","quantity":2}]}
```

Nếu cùng operation cũng nhận XML, client có thể gửi:

```http
POST /api/orders
Content-Type: application/xml
Accept: application/json

<createOrderRequest>
  <customerId>C-100</customerId>
  <items>
    <item><sku>KB-01</sku><quantity>2</quantity></item>
  </items>
</createOrderRequest>
```

Trong ví dụ thứ hai, request body là XML nhưng response vẫn có thể là JSON vì `Content-Type` và `Accept` phục vụ hai mục đích khác nhau. Một API có thể nhận JSON và XML nhưng chỉ trả JSON; khi đó tài liệu request và response phải mô tả độc lập.

## 2. OpenAPI mô tả nhiều media type như thế nào?

Trong OpenAPI, `requestBody.content` là một map có khóa là media type. Mỗi khóa chứa schema và có thể có ví dụ hoặc encoding riêng:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
```

Một request HTTP chỉ có một định dạng body chính tại một thời điểm, được chỉ ra bởi `Content-Type`. Các mục JSON và XML trong tài liệu là những lựa chọn thay thế cho cùng operation, không phải hai body phải gửi đồng thời.

Mỗi media type có thể tham chiếu cùng một schema khi cấu trúc dữ liệu tương đương. Nếu định dạng có cấu trúc khác nhau, có thể khai báo schema riêng cho từng media type. Tuy nhiên, tài liệu phải phản ánh đúng dữ liệu mà controller và converter thực sự có thể đọc.

## 3. Chấp nhận JSON và XML trong cùng một controller method

Với Spring MVC, thuộc tính `consumes` trên mapping khai báo những media type mà method chấp nhận. Ví dụ, cả JSON và XML đều được chuyển thành cùng DTO `CreateOrderRequest`:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }, produces = MediaType.APPLICATION_JSON_VALUE)
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

Mapping trên cho phép Spring chọn method khi request có một trong hai `Content-Type` được khai báo. `produces` cho biết method trả response JSON. Phần body được đọc thành cùng một kiểu Java; service không cần biết client đã gửi JSON hay XML nếu hai converter tạo ra cùng DTO.

Spring Boot thường cấu hình Jackson JSON converter sẵn trong ứng dụng web. Để đọc XML bằng Jackson, dự án cần thêm module XML phù hợp, thường là `jackson-dataformat-xml`, và bảo đảm converter XML được đăng ký. Nếu không có converter phù hợp, dù `consumes` có khai báo XML, server vẫn không thể deserialize body như mong đợi.

Ví dụ dependency Maven cho XML:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
```

Khi dùng Spring Boot dependency management, thường không cần tự chỉ định version của module Jackson. Với cấu hình Gradle:

```kotlin
implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml")
```

Khả năng serialize/deserialize còn phụ thuộc annotation, tên phần tử XML và cấu trúc DTO. Hãy thử dữ liệu XML thật, đặc biệt với collection lồng nhau, namespace và thuộc tính XML.

## 4. Mô tả JSON và XML bằng springdoc

Springdoc có thể suy ra request body từ `@RequestBody`, kiểu DTO và `consumes` của mapping. Khi cần kiểm soát rõ schema theo từng media type, dùng `@Operation` với `@Content`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.http.MediaType;

@Operation(
    summary = "Tạo đơn hàng",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Thông tin đơn hàng, nhận JSON hoặc XML",
        required = true,
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreateOrderRequest.class)
            ),
            @Content(
                mediaType = MediaType.APPLICATION_XML_VALUE,
                schema = @Schema(implementation = CreateOrderRequest.class)
            )
        }
    )
)
```

Ở đây dùng tên đầy đủ `@io.swagger.v3.oas.annotations.parameters.RequestBody` để phân biệt annotation mô tả OpenAPI với `org.springframework.web.bind.annotation.RequestBody` dùng trên tham số controller. Hai annotation có vai trò khác nhau:

- Spring `@RequestBody` yêu cầu framework đọc HTTP body và bind vào argument.
- Swagger `@RequestBody` mô tả request body trong đặc tả OpenAPI, gồm description, required và content.

Đoạn `@Operation` cần được đặt trên method controller tương ứng. Nếu `consumes` trong mapping chỉ nhận JSON nhưng annotation lại công bố cả XML, tài liệu sẽ sai so với runtime. Hãy giữ danh sách media type ở hai nơi nhất quán hoặc dựa vào metadata tự suy ra khi không cần tùy biến.

OpenAPI sinh ra có thể tương tự:

```yaml
paths:
  /api/orders:
    post:
      summary: Tạo đơn hàng
      requestBody:
        required: true
        description: Thông tin đơn hàng, nhận JSON hoặc XML
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
          application/xml:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
```

## 5. Dùng schema riêng cho từng media type

Không bắt buộc mọi định dạng phải dùng chung schema. Ví dụ, API nhập dữ liệu cũ có thể nhận một cấu trúc XML phẳng, trong khi JSON sử dụng cấu trúc hiện đại. OpenAPI cho phép mô tả mỗi media type bằng schema tương ứng:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/LegacyOrderDocument'
```

Nếu method controller nhận một DTO duy nhất, ứng dụng phải có cơ chế chuyển đổi cả hai biểu diễn vào DTO đó, ví dụ custom `HttpMessageConverter`, deserializer hoặc adapter ở tầng tiếp nhận. Có thể nhận body dưới dạng `String` hoặc `byte[]` rồi tự phân tích, nhưng khi đó phải tự chịu trách nhiệm kiểm tra định dạng, lỗi parse, giới hạn kích thước và bảo mật dữ liệu đầu vào.

Khi hai định dạng có quy tắc nghiệp vụ khác nhau hoặc xử lý hoàn toàn khác nhau, cân nhắc tách thành operation/endpoint riêng thay vì công bố một operation có schema gây hiểu nhầm. OpenAPI chỉ có một operation cho mỗi cặp path và HTTP method; không nên tạo hai method Java cùng path và method chỉ để biểu diễn hai body rồi mong tài liệu luôn tự hợp nhất chính xác.

## 6. Nhận multipart/form-data có file và metadata

`multipart/form-data` thường dùng khi request chứa file cùng các trường metadata. Đây cũng là một media type của request body, nhưng schema thường khác với JSON/XML thông thường.

Ví dụ controller nhận một file và một phần metadata JSON:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@PostMapping(
    path = "/api/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
DocumentResponse upload(
        @RequestPart("file") MultipartFile file,
        @RequestPart("metadata") CreateDocumentMetadata metadata) {
    return documentService.upload(file, metadata);
}
```

DTO mô tả phần body multipart:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.multipart.MultipartFile;

public class UploadDocumentRequest {

    @Schema(type = "string", format = "binary", description = "Tệp cần tải lên")
    private MultipartFile file;

    @Schema(description = "Thông tin mô tả tài liệu")
    private CreateDocumentMetadata metadata;

    // Getter và setter
}
```

Có thể mô tả schema và encoding của từng part trong OpenAPI:

```java
@Operation(
    summary = "Tải tài liệu lên",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = UploadDocumentRequest.class),
            encoding = @Encoding(
                name = "metadata",
                contentType = MediaType.APPLICATION_JSON_VALUE
            )
        )
    )
)
```

Thêm import `io.swagger.v3.oas.annotations.media.Encoding` và đặt annotation trên method upload. `format: binary` cho biết part file chứa dữ liệu nhị phân; `encoding` cho biết part `metadata` được gửi dưới dạng JSON. Tên part trong schema phải khớp với tên trong `@RequestPart`.

Đặc tả tương ứng có thể có dạng:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        properties:
          file:
            type: string
            format: binary
          metadata:
            $ref: '#/components/schemas/CreateDocumentMetadata'
      encoding:
        metadata:
          contentType: application/json
```

Với multipart, boundary được client tạo trong header `Content-Type`; không tự đặt thủ công `multipart/form-data` mà bỏ boundary khi dùng `curl` hoặc browser FormData. Hãy để công cụ HTTP tự tạo boundary.

## 7. Nhận form-urlencoded, text/plain và dữ liệu nhị phân

Ngoài JSON/XML/multipart, một operation có thể nhận các loại body khác nếu ứng dụng có converter tương ứng.

### application/x-www-form-urlencoded

Định dạng này gửi các cặp key/value trong body. Spring cung cấp `FormHttpMessageConverter` có thể đọc `MultiValueMap`:

```java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
Receipt submitForm(@RequestBody MultiValueMap<String, String> form) {
    return formService.submit(form);
}
```

OpenAPI có thể mô tả body dưới dạng object:

```yaml
requestBody:
  required: true
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        required:
          - email
        properties:
          email:
            type: string
            format: email
          campaign:
            type: string
```

Nếu dùng `@ModelAttribute` để bind form fields, hãy kiểm tra cách springdoc biểu diễn chúng ở phiên bản đang dùng. Trong Spring MVC, `@ModelAttribute` thường bind dữ liệu từ request parameters; nó không đồng nghĩa trong mọi trường hợp với một `requestBody` được mô tả bằng `application/x-www-form-urlencoded`.

### text/plain

Với body văn bản thuần, controller có thể nhận `String`:

```java
@PostMapping(path = "/notes", consumes = MediaType.TEXT_PLAIN_VALUE)
void addNote(@RequestBody String content) {
    noteService.add(content);
}
```

Schema OpenAPI là chuỗi:

```yaml
requestBody:
  content:
    text/plain:
      schema:
        type: string
```

### application/octet-stream

Với body nhị phân thô, có thể nhận `byte[]` hoặc `Resource` tùy cách xử lý:

```java
@PostMapping(path = "/raw-file", consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
void uploadRaw(@RequestBody byte[] bytes) {
    fileService.store(bytes);
}
```

Schema OpenAPI thường dùng `type: string`, `format: binary`:

```yaml
requestBody:
  content:
    application/octet-stream:
      schema:
        type: string
        format: binary
```

Với file lớn, tránh đọc toàn bộ vào `byte[]` nếu điều đó gây áp lực bộ nhớ. Hãy cân nhắc streaming hoặc lưu trữ theo luồng và giới hạn kích thước upload ở cả proxy lẫn ứng dụng.

## 8. Khai báo consumes và produces nhất quán

`consumes` và `produces` trong mapping Spring điều khiển việc chọn handler theo media type:

```java
@PostMapping(
    path = "/api/orders",
    consumes = {"application/json", "application/xml"},
    produces = "application/json"
)
```

- `consumes` lọc request theo `Content-Type`.
- `produces` lọc response theo `Accept`.
- `requestBody.content` mô tả các định dạng body mà operation nhận.
- `responses.<status>.content` mô tả định dạng response mà operation trả về.

Không dùng `produces` để khai báo định dạng request. Cũng không thêm XML vào `requestBody.content` nếu controller không chấp nhận XML hoặc không có converter đọc XML.

Nếu `Content-Type` không được mapping chấp nhận, Spring thường trả HTTP 415 Unsupported Media Type. Nếu client yêu cầu response qua `Accept` nhưng method không thể tạo media type đó, Spring thường trả HTTP 406 Not Acceptable. Hai lỗi này khác với lỗi parse body (thường là 400) và lỗi validation dữ liệu.

Ví dụ operation nhận JSON/XML nhưng chỉ trả JSON:

```yaml
paths:
  /api/orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
          application/xml:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Đã tạo đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
```

Nếu operation trả cả JSON và XML, response cần liệt kê cả hai media type trong `responses.<status>.content`, và controller phải có converter/serializer cùng `produces` tương ứng.

## 9. Kiểm thử từng kiểu nội dung

Không chỉ kiểm tra Swagger UI có hiển thị nhiều lựa chọn hay không. Hãy gửi request thật với từng `Content-Type` và xác minh controller đọc được dữ liệu:

```bash
# JSON
curl -i http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"customerId":"C-100","items":[]}'

# XML
curl -i http://localhost:8080/api/orders \
  -H "Content-Type: application/xml" \
  -H "Accept: application/json" \
  -d '<createOrderRequest><customerId>C-100</customerId></createOrderRequest>'

# Multipart
curl -i http://localhost:8080/api/documents \
  -F "file=@document.pdf" \
  -F 'metadata={"title":"Contract"};type=application/json'
```

Sau đó lấy `/v3/api-docs` hoặc `/v3/api-docs.yaml` và đối chiếu:

1. Operation có đúng một path và HTTP method như controller không?
2. `requestBody.required` có đúng với việc body có bắt buộc không?
3. `requestBody.content` có liệt kê đủ media type thực sự được hỗ trợ không?
4. Schema của từng media type có đúng cấu trúc và kiểu dữ liệu không?
5. Với multipart, tên part, binary format và encoding có khớp controller không?
6. Response content có phản ánh `produces` và serializer thực tế không?
7. Request sai `Content-Type` có trả 415; body lỗi định dạng có được xử lý thành lỗi phù hợp không?

Nên có kiểm thử tích hợp riêng cho từng biểu diễn. Một test gửi JSON thành công không chứng minh XML hoặc multipart cũng hoạt động.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| OpenAPI hiển thị JSON và XML nhưng XML trả 415 | Mapping thiếu XML trong `consumes` | Bổ sung media type vào mapping nếu ứng dụng thật sự hỗ trợ |
| XML được chấp nhận nhưng không bind được DTO | Thiếu XML message converter hoặc DTO không tương thích cấu trúc XML | Cấu hình Jackson XML/JAXB converter và kiểm thử payload |
| Swagger UI chỉ hiện một định dạng | Metadata request body bị ghi đè hoặc chỉ suy ra một content type | Khai báo `@Operation`/`@Content` tường minh và kiểm tra JSON sinh ra |
| Multipart file hiện thành chuỗi thông thường | Schema không khai báo `format: binary` | Dùng `@Schema(type = "string", format = "binary")` |
| Metadata multipart parse sai | Tên part hoặc content type của part không khớp | Đồng bộ `@RequestPart`, schema và `encoding` |
| Request đúng nhưng response trả 406 | `Accept` không khớp `produces` hoặc converter response | Kiểm tra `Accept`, `produces` và response converter |
| Form-urlencoded bị mô tả thành query parameter | Dùng `@ModelAttribute` và suy luận tài liệu không đúng ý định | Kiểm tra đặc tả thực tế; mô tả request body rõ ràng nếu controller nhận body form |

## 11. Quy trình thiết kế nhiều kiểu nội dung

Khi một operation cần nhận nhiều định dạng, thực hiện theo trình tự:

1. Xác định các media type client thực sự cần gửi, ví dụ JSON và XML.
2. Quyết định các định dạng có cùng cấu trúc dữ liệu hay cần schema riêng.
3. Khai báo `consumes` trên mapping và bảo đảm message converter có thể đọc từng định dạng.
4. Dùng `@RequestBody` của Spring để bind body; bổ sung `@Operation` và `@Content` khi cần mô tả tường minh trong OpenAPI.
5. Mô tả riêng `responses.content` theo định dạng response và `produces`.
6. Kiểm tra đặc tả JSON/YAML, sau đó chạy kiểm thử tích hợp cho từng media type và các trường hợp lỗi.

Một operation có thể nhận nhiều biểu diễn, nhưng mỗi biểu diễn phải hoạt động thật ở runtime. Khi controller, converter và `requestBody.content` thống nhất, client có thể chọn định dạng phù hợp mà vẫn dùng chung hợp đồng operation.

## Tài liệu tham khảo

- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object)
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object)
- [Spring Framework – HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework – `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
