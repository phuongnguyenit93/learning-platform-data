# Phân biệt @RequestBody của Spring với @RequestBody của Swagger annotations

Trong một controller Spring Boot, có hai annotation cùng tên `@RequestBody` nhưng thuộc hai thư viện và có nhiệm vụ khác nhau. `org.springframework.web.bind.annotation.RequestBody` yêu cầu Spring đọc HTTP request body và chuyển đổi nội dung thành đối tượng Java ở runtime. `io.swagger.v3.oas.annotations.parameters.RequestBody` mô tả request body trong tài liệu OpenAPI, chẳng hạn description, media type, schema và tính bắt buộc. Springdoc có thể suy luận tài liệu từ annotation Spring; annotation Swagger được dùng khi cần bổ sung hoặc kiểm soát mô tả hợp đồng.

Hai annotation không thay thế cho nhau. Một annotation tài liệu không khiến controller đọc được body, còn annotation Spring không cung cấp đầy đủ nội dung mô tả mà người dùng API cần xem trong Swagger UI.

## 1. Hai annotation cùng tên nhưng khác vai trò

| Tiêu chí | Spring `@RequestBody` | Swagger/OpenAPI `@RequestBody` |
|---|---|---|
| Package | `org.springframework.web.bind.annotation` | `io.swagger.v3.oas.annotations.parameters` |
| Mục đích | Binding HTTP request body vào tham số Java | Mô tả Request Body Object trong OpenAPI |
| Thời điểm tác động | Khi Spring xử lý request tại runtime | Khi springdoc/Swagger Core tạo tài liệu API |
| Thông tin chính | `required` | `description`, `required`, `content`, `ref`, `extensions` |
| Có đọc body không? | Có, thông qua `HttpMessageConverter` | Không |
| Có tự tạo schema từ DTO không? | Không tạo schema tài liệu; kiểu tham số là đầu vào để springdoc suy luận | Có thể chỉ định schema qua `@Content` và `@Schema` |
| Có thay đổi hành vi endpoint không? | Có ảnh hưởng tới cách binding body | Không, chỉ ảnh hưởng tài liệu |

Tên giống nhau do cả hai cùng mô tả request body, nhưng một bên thuộc tầng web runtime, một bên thuộc tầng mô tả hợp đồng API.

## 2. Spring @RequestBody xử lý dữ liệu gửi lên

Annotation của Spring được đặt trên tham số handler method. Khi request đến, Spring đọc body và dùng `HttpMessageConverter` phù hợp để chuyển đổi nội dung thành kiểu Java đã khai báo.

Ví dụ:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @PostMapping(
        path = "/api/products",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    ProductResponse create(@RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
```

Khi client gửi:

```http
POST /api/products HTTP/1.1
Content-Type: application/json

{"name":"Bút bi","price":12000}
```

Spring dùng converter JSON (thường là Jackson trong cấu hình Spring Boot phổ biến) để deserialize body thành `CreateProductRequest`, rồi truyền đối tượng đó vào phương thức `create`.

Nếu body không thể đọc hoặc chuyển đổi, request có thể bị từ chối trước khi logic nghiệp vụ chạy. Ví dụ JSON sai cú pháp hoặc kiểu field không chuyển đổi được thường dẫn tới `400 Bad Request`. Nếu media type không được mapping chấp nhận hoặc không có converter phù hợp, có thể nhận `415 Unsupported Media Type`.

### Thuộc tính required của Spring

`required` điều khiển việc body có bắt buộc phải xuất hiện trong request hay không. Mặc định của Spring `@RequestBody` là `true`:

```java
@PostMapping("/api/notes")
NoteResponse create(@RequestBody CreateNoteRequest request) {
    return noteService.create(request);
}
```

Nếu muốn cho phép request không có body, có thể khai báo:

```java
@PostMapping("/api/notes/search")
List<NoteResponse> search(
    @RequestBody(required = false) NoteSearchRequest request
) {
    return noteService.search(request);
}
```

Khi `required = false`, mã xử lý phải chấp nhận trường hợp không có body, chẳng hạn `request == null`. Cần thiết kế hành vi rõ ràng để tránh NullPointerException hoặc vô tình thực hiện tìm kiếm quá rộng.

### Kết hợp validation

Spring `@RequestBody` thường kết hợp với `@Valid` hoặc `@Validated` để yêu cầu validation DTO sau khi deserialize:

```java
@PostMapping("/api/products")
ProductResponse create(
    @Valid @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
```

Ví dụ DTO:

```java
public record CreateProductRequest(
    @NotBlank String name,
    @NotNull @DecimalMin("0.0") BigDecimal price
) {}
```

`@RequestBody` đảm nhiệm đọc và chuyển đổi body; `@Valid` kích hoạt validation theo các constraint trên DTO. Hai việc này liên quan nhưng không đồng nghĩa. Việc mô tả các constraint trong OpenAPI cần springdoc nhận diện được annotation validation hoặc được bổ sung bằng `@Schema`.

## 3. Swagger @RequestBody mô tả hợp đồng OpenAPI

Annotation của Swagger nằm trong package `io.swagger.v3.oas.annotations.parameters`. Nó cung cấp metadata cho Request Body Object trong tài liệu OpenAPI. Nó có thể mô tả:

- `description`: nội dung body và cách client cần gửi.
- `required`: body có bắt buộc theo hợp đồng hay không.
- `content`: các media type được chấp nhận và schema của từng media type.
- `ref`: tham chiếu tới request body component khi cấu hình theo cách phù hợp.
- `extensions`: metadata mở rộng theo quy ước của tổ chức.

Ví dụ mô tả body JSON:

```java
@Operation(
    summary = "Tạo sản phẩm",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Thông tin sản phẩm mới cần tạo",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateProductRequest.class)
        )
    )
)
```

Trong ví dụ này, `@RequestBody` của Swagger không deserialize JSON và không gọi service. Nó chỉ cho springdoc biết cách mô tả body trong OpenAPI. Spring vẫn cần annotation runtime trên tham số phương thức nếu controller phải đọc body.

## 4. Dùng đồng thời hai annotation trong một controller

Trường hợp phổ biến nhất là kết hợp Spring `@RequestBody` trên tham số với Swagger `@RequestBody` bên trong `@Operation`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @Operation(
        summary = "Tạo sản phẩm",
        description = "Tạo sản phẩm mới từ dữ liệu JSON.",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            description = "Payload chứa tên và giá sản phẩm",
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreateProductRequest.class)
            )
        )
    )
    @PostMapping(
        path = "/api/products",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
```

Đọc ví dụ theo hai tầng:

1. `@RequestBody` trên `CreateProductRequest request` là annotation Spring. Nó làm cho Spring đọc body JSON và binding vào tham số `request`.
2. `@Operation(requestBody = ...)` chứa annotation Swagger. Nó bổ sung mô tả, media type và schema mà Swagger UI hiển thị cho client.

`consumes = application/json` là điều kiện mapping runtime của Spring. `content.mediaType = application/json` là định nghĩa media type trong tài liệu. Hai giá trị nên thống nhất để hợp đồng công bố khớp với endpoint thật.

Springdoc thường có thể tự suy luận request body từ tham số Spring `@RequestBody`, kiểu DTO và điều kiện `consumes`. Vì vậy, không cần thêm annotation Swagger cho mọi endpoint. Hãy dùng annotation Swagger khi cần mô tả nghiệp vụ, ví dụ, media type hoặc schema cụ thể mà suy luận tự động chưa thể hiện đủ.

## 5. Tránh xung đột import vì hai tên giống nhau

Java không hỗ trợ import alias. Vì thế, không thể import đồng thời hai class cùng tên đơn giản `RequestBody` rồi dùng cả hai bằng tên ngắn trong cùng file.

Ví dụ import sau sẽ gây xung đột tên:

```java
import org.springframework.web.bind.annotation.RequestBody;
import io.swagger.v3.oas.annotations.parameters.RequestBody;
```

Trình biên dịch không thể phân biệt hai annotation khi bạn viết `@RequestBody`.

### Cách khuyến nghị: import Spring, viết đầy đủ tên Swagger

Đây là cách dễ đọc trong controller vì Spring `@RequestBody` thường xuất hiện trực tiếp trên tham số, còn Swagger `@RequestBody` thường được lồng trong `@Operation`:

```java
import org.springframework.web.bind.annotation.RequestBody;

@Operation(
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateProductRequest.class)
        )
    )
)
ProductResponse create(@RequestBody CreateProductRequest request) {
    // ...
}
```

### Cách khác: viết đầy đủ tên Spring

Nếu file đang dùng annotation Swagger dạng tên ngắn ở vị trí khác, có thể bỏ import Spring và viết fully qualified name cho annotation runtime:

```java
ProductResponse create(
    @org.springframework.web.bind.annotation.RequestBody
    CreateProductRequest request
) {
    // ...
}
```

Trong thực tế, nên thống nhất một quy ước trong nhóm. Tránh cố dùng hai tên ngắn giống nhau vì Java không có cú pháp alias như một số ngôn ngữ khác.

## 6. Phân biệt required của body với required của property

Một nhầm lẫn thường gặp là cho rằng body bắt buộc đồng nghĩa mọi trường trong DTO đều bắt buộc. Đây là hai cấp độ khác nhau:

| Cấp độ | Vị trí | Ý nghĩa |
|---|---|---|
| Request body bắt buộc | `@RequestBody(required = true)` của Spring hoặc `requestBody.required: true` của OpenAPI | Client phải gửi phần body |
| Property bắt buộc | Constraint validation hoặc `required` trong Schema Object | Object body phải chứa trường được chỉ định |

Ví dụ body bắt buộc nhưng chỉ có `name` là property bắt buộc:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - name
        properties:
          name:
            type: string
          description:
            type: string
```

Client phải gửi một JSON object, nhưng có thể bỏ `description`. Nếu bỏ toàn bộ body, request vi phạm `requestBody.required`. Nếu gửi `{}` thì body hiện diện nhưng thiếu `name`, vi phạm schema/validation.

Một điểm cần chú ý là giá trị mặc định của hai tầng không giống nhau: Spring `@RequestBody.required` mặc định là `true`, trong khi trường `required` của OpenAPI Request Body Object mặc định là `false`. Springdoc có thể suy luận tính bắt buộc từ annotation Spring; khi tự khai báo Swagger annotation, nên ghi rõ `required` để tài liệu không phụ thuộc vào mặc định hoặc cách merge metadata.

## 7. Khi nào nên dùng annotation Swagger?

Nếu controller và DTO đã thể hiện đầy đủ body, media type và schema, springdoc thường có thể tạo request body mà không cần annotation Swagger:

```java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
```

Nên bổ sung Swagger `@RequestBody` khi cần:

- Viết mô tả hướng dẫn client chuẩn bị payload.
- Chỉ rõ media type và schema cho từng định dạng body.
- Bổ sung ví dụ hoặc mô tả mà kiểu Java không thể hiện.
- Tùy chỉnh tính bắt buộc trong tài liệu theo hợp đồng đã thống nhất.
- Dùng schema hoặc request body component cụ thể cho tài liệu.

Không nên thêm annotation Swagger chỉ để lặp lại mọi thông tin mà springdoc đã suy luận chính xác. Metadata trùng lặp làm controller dài hơn và dễ bị lệch khi DTO hoặc mapping thay đổi.

## 8. Mô tả nhiều media type cho cùng một request body

Một operation có thể nhận nhiều định dạng. Khi đó, annotation Swagger có thể liệt kê nhiều `@Content` trong request body:

```java
@Operation(
    summary = "Nhập dữ liệu sản phẩm",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Có thể gửi dữ liệu dưới dạng JSON hoặc CSV",
        required = true,
        content = {
            @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ImportJsonRequest.class)
            ),
            @Content(
                mediaType = "text/csv",
                schema = @Schema(
                    type = "string",
                    description = "Các cột sku và quantity, mỗi bản ghi một dòng"
                )
            )
        }
    )
)
```

Trong OpenAPI, phần này trở thành `requestBody.content` với hai key media type. Tuy nhiên, annotation tài liệu không tự làm cho controller nhận được CSV. Ở runtime, Spring mapping phải cho phép `text/csv`, và tham số/converter phải đọc được nội dung. Nếu controller chỉ khai báo `consumes = application/json`, tài liệu không nên công bố thêm CSV.

Với upload file, body thường là `multipart/form-data`. Spring có thể dùng `@RequestPart` để bind từng phần; Swagger `@RequestBody` có thể mô tả schema multipart với thuộc tính file và metadata. Không nhầm `@RequestPart` với Spring `@RequestBody`: `@RequestPart` xử lý một phần của multipart message, còn `@RequestBody` xử lý toàn bộ body thông qua converter.

## 9. Những annotation liên quan nhưng không thay thế nhau

| Annotation | Vai trò |
|---|---|
| Spring `@RequestBody` | Đọc toàn bộ request body và binding vào tham số Java |
| Swagger `@RequestBody` | Mô tả request body trong OpenAPI |
| Spring `@RequestPart` | Binding một phần trong multipart request |
| Spring `@ModelAttribute` | Binding các field request vào object theo cơ chế data binding |
| Spring `@Valid` | Kích hoạt validation cho đối tượng đã binding |
| Swagger `@Content` | Mô tả media type và schema của request/response body |
| Swagger `@Schema` | Mô tả cấu trúc và thuộc tính dữ liệu |
| Spring `consumes` | Giới hạn media type request mà mapping nhận ở runtime |

Ví dụ, `@Valid` không tạo request body và `@Content` không đọc JSON. Mỗi annotation giải quyết một phần khác nhau trong chuỗi xử lý: routing, binding, validation hoặc mô tả hợp đồng.

## 10. Kiểm tra tài liệu OpenAPI và hành vi runtime

Sau khi cấu hình hai annotation, hãy xác minh riêng hai kết quả.

**Kiểm tra runtime:** gửi request có body hợp lệ và không hợp lệ để xác nhận Spring binding, validation và status code đúng như mong đợi.

```bash
curl -i -X POST http://localhost:8080/api/products \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Bút bi","price":12000}'
```

**Kiểm tra tài liệu:** tải `/v3/api-docs` hoặc `/v3/api-docs.yaml`, tìm operation `POST /api/products` và xác nhận:

- `requestBody.description` hiển thị đúng hướng dẫn.
- `requestBody.required` phản ánh body có bắt buộc không.
- `requestBody.content` có đúng media type.
- `schema` tham chiếu hoặc mô tả đúng DTO.
- Các property bắt buộc và giới hạn validation được mô tả phù hợp.

Trong Swagger UI, kiểm tra phần Request body và thử gọi endpoint. Swagger UI dựa vào tài liệu OpenAPI nên việc giao diện hiển thị đúng schema chưa chứng minh controller xử lý đúng. Cần kiểm tra cả response thực tế và header `Content-Type`.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| IDE báo trùng import `RequestBody` | Import cả hai annotation cùng tên | Import Spring và viết đầy đủ tên Swagger trong `@Operation` |
| Swagger UI không hiển thị mô tả body | Chỉ có Spring annotation và chưa khai báo mô tả bổ sung | Thêm Swagger `@RequestBody` trong `@Operation` khi cần |
| Swagger UI báo body không bắt buộc nhưng Spring từ chối body rỗng | `requestBody.required` trong tài liệu chưa đồng bộ với Spring `required` | Khai báo rõ hai giá trị và xác nhận cùng hợp đồng |
| Swagger UI hiển thị schema sai | `@Schema(implementation=...)` hoặc metadata `@Content` trỏ sai DTO/media type | Kiểm tra `/v3/api-docs` và sửa annotation |
| Controller không nhận body dù Swagger UI cho nhập | Chỉ khai báo Swagger annotation, thiếu Spring `@RequestBody` hoặc mapping/converter không phù hợp | Bổ sung annotation runtime và kiểm tra `consumes`, converter |
| Request gửi đúng JSON nhưng trả 400 | JSON không deserialize được hoặc DTO vi phạm validation | Kiểm tra cấu trúc payload, kiểu field và constraint |
| Request trả 415 | `Content-Type` không khớp `consumes` hoặc thiếu converter | Điều chỉnh media type hoặc cấu hình converter |
| Tài liệu công bố nhiều định dạng nhưng runtime chỉ nhận một | Swagger `content` không khớp mapping Spring | Đồng bộ `consumes` và `requestBody.content` |

Khi gặp sai lệch, xác định trước lỗi thuộc runtime hay tài liệu. Nếu request HTTP thất bại, kiểm tra mapping và binding. Nếu endpoint chạy đúng nhưng Swagger UI mô tả sai, kiểm tra OpenAPI JSON/YAML và annotation Swagger.

## 12. Quy trình lựa chọn annotation

Khi xây dựng controller, có thể áp dụng trình tự sau:

1. Dùng Spring `@RequestBody` trên tham số nếu handler cần đọc payload toàn bộ request body.
2. Chọn kiểu DTO cụ thể để Spring deserialize và springdoc suy luận schema.
3. Dùng `@Valid` cùng constraint validation nếu payload cần kiểm tra dữ liệu.
4. Khai báo `consumes` cho media type mà endpoint thực sự chấp nhận.
5. Chỉ bổ sung Swagger `@RequestBody` khi cần mô tả, media type hoặc schema chi tiết hơn suy luận tự động.
6. Ghi rõ `required` trong annotation Swagger và giữ đồng bộ với `required` của Spring.
7. Tránh xung đột import bằng cách viết đầy đủ tên Swagger annotation khi lồng trong `@Operation`.
8. Kiểm tra cả `/v3/api-docs` và request HTTP thực tế trước khi phát hành.

Spring `@RequestBody` quyết định cách ứng dụng tiếp nhận dữ liệu. Swagger `@RequestBody` quyết định cách hợp đồng mô tả dữ liệu đó cho client. Dùng đúng vai trò và đồng bộ hai lớp giúp controller hoạt động chính xác, tài liệu OpenAPI rõ ràng và Swagger UI cung cấp hướng dẫn đúng với API thực tế.

## 13. Tài liệu tham khảo

- [Spring Framework: @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): binding request body, message converter và validation.
- [Spring Framework: Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): điều kiện `consumes` và request mapping.
- [Swagger Core Annotations – RequestBody](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): annotation mô tả request body trong OpenAPI.
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object): `description`, `required` và `content` của request body.
- [Springdoc OpenAPI](https://springdoc.org/): suy luận và tùy chỉnh tài liệu OpenAPI từ Spring Boot.
