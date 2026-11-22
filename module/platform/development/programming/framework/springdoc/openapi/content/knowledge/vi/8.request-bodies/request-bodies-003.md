# Mô tả `application/json` bằng `@Content` và `@Schema`

Khi một REST API nhận dữ liệu JSON, client gửi nội dung trong HTTP request body với media type thường là `application/json`. Spring MVC dùng `@RequestBody` để chuyển JSON thành một đối tượng Java. Springdoc dựa vào kiểu DTO và metadata OpenAPI để mô tả request body trong tài liệu; khi cần kiểm soát rõ media type, schema, ví dụ và tính bắt buộc, có thể dùng `@Content` và `@Schema`.

Điểm quan trọng là phân biệt hai nhiệm vụ: annotation Spring điều khiển cách ứng dụng nhận request thực tế, còn annotation OpenAPI mô tả hợp đồng cho client. Hai phần cần phản ánh cùng một hành vi. Tài liệu có thể khai báo request body bắt buộc và schema rất chi tiết, nhưng controller vẫn phải nhận và kiểm tra dữ liệu đúng như hợp đồng đó.

## 1. Request body JSON trong HTTP và OpenAPI

Một request tạo sách có thể được gửi như sau:

```http
POST /api/books HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "title": "Spring Boot căn bản",
  "publicationYear": 2025
}
```

Trong request này:

- `POST /api/books` xác định operation được gọi.
- `Content-Type: application/json` cho server biết định dạng của request body.
- `Accept: application/json` cho biết client muốn nhận response JSON.
- Phần JSON chứa dữ liệu tạo sách.

Trong OpenAPI 3, request body được mô tả ở thuộc tính `requestBody` của operation. Media type được khai báo bên trong `requestBody.content`, còn schema mô tả cấu trúc dữ liệu:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateBookRequest'
```

`required: true` cho biết client phải gửi request body. `application/json` xác định định dạng nội dung. `$ref` trỏ đến schema được định nghĩa trong `components.schemas`.

## 2. Nhận JSON bằng `@RequestBody` của Spring

Trong Spring MVC, `@org.springframework.web.bind.annotation.RequestBody` yêu cầu Spring đọc body và chuyển đổi nó thành kiểu Java tương ứng. Ví dụ:

```java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(
        @RequestBody CreateBookRequest request) {
    // Xử lý dữ liệu request.
    return new BookResponse(1L, request.title());
}
```

Spring sử dụng `HttpMessageConverter` để chuyển JSON thành `CreateBookRequest`. Jackson thường là converter được dùng trong ứng dụng Spring Boot Web mặc định. Kiểu DTO cung cấp cấu trúc cơ sở để Springdoc suy ra schema của request body.

Thuộc tính `consumes` trên `@PostMapping` giới hạn media type mà endpoint nhận. Khi đặt `consumes = application/json`, client cần gửi request với `Content-Type: application/json` phù hợp. Nếu không khai báo `consumes`, Spring vẫn có thể nhận JSON nhờ converter, nhưng khai báo rõ giúp hợp đồng và mapping dễ hiểu hơn.

## 3. Khai báo DTO và schema bằng `@Schema`

DTO mô tả các trường mà client có thể gửi. `@Schema` thuộc OpenAPI 3 annotations, dùng để bổ sung tên, mô tả, ví dụ, định dạng và các ràng buộc cho schema.

Ví dụ `CreateBookRequest.java`:

```java
package com.example.books.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Schema(description = "Dữ liệu client gửi để tạo sách mới")
public record CreateBookRequest(

    @NotBlank
    @Size(max = 120)
    @Schema(
        description = "Tên sách, không được để trống và tối đa 120 ký tự",
        example = "Spring Boot căn bản"
    )
    String title,

    @Min(1)
    @Schema(
        description = "Năm xuất bản, nếu có",
        example = "2025"
    )
    Integer publicationYear
) {}
```

Trong ví dụ:

- `@Schema` trên record mô tả toàn bộ object.
- `@Schema` trên từng component giải thích ý nghĩa và cung cấp ví dụ.
- `@NotBlank` yêu cầu `title` có giá trị văn bản không rỗng.
- `@Size(max = 120)` giới hạn độ dài tên sách.
- `@Min(1)` yêu cầu năm xuất bản nếu được cung cấp phải có giá trị từ 1 trở lên.

Springdoc có thể đọc các annotation Bean Validation phổ biến để đưa ràng buộc vào schema OpenAPI. Tuy nhiên, validation chỉ được thực thi khi ứng dụng kích hoạt validation, ví dụ có dependency `spring-boot-starter-validation` và tham số controller được đánh dấu `@Valid`. Không nên nghĩ rằng chỉ thêm `@Schema` sẽ khiến Spring tự kiểm tra dữ liệu.

## 4. Mô tả request body bằng `@Content` và `@Schema`

Springdoc có thể suy ra request body từ tham số `@RequestBody` và kiểu DTO. Khi cần chỉ định rõ media type, mô tả hoặc ví dụ, khai báo request body OpenAPI trong `@Operation`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Tạo sách mới",
    description = "Nhận dữ liệu JSON và tạo một bản ghi sách",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Thông tin sách cần tạo",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateBookRequest.class),
            examples = @ExampleObject(
                name = "NewBook",
                summary = "Dữ liệu tạo sách",
                value = "{\"title\":\"Spring Boot căn bản\",\"publicationYear\":2025}"
            )
        )
    )
)
public BookResponse create(
        @RequestBody CreateBookRequest request) {
    return new BookResponse(1L, request.title());
}
```

Trong đoạn code có hai annotation tên `RequestBody` thuộc hai package khác nhau:

- `org.springframework.web.bind.annotation.RequestBody` đặt trên tham số method để Spring đọc body HTTP.
- `io.swagger.v3.oas.annotations.parameters.RequestBody` nằm trong `@Operation` để mô tả request body của hợp đồng OpenAPI.

Ví dụ dùng tên đầy đủ cho annotation OpenAPI nhằm tránh nhầm lẫn khi import. `@Content` xác định nội dung theo media type; `@Schema(implementation = CreateBookRequest.class)` chỉ ra kiểu DTO làm schema; `@ExampleObject` cung cấp một payload mẫu để Swagger UI hiển thị.

`required = true` trong annotation OpenAPI cần nhất quán với hành vi của controller. Với tham số Spring `@RequestBody`, mặc định `required` là `true`. Nếu endpoint cho phép bỏ qua body, cần điều chỉnh cả annotation Spring và metadata OpenAPI, đồng thời xử lý trường hợp `null` trong code.

## 5. Vai trò của `@Content`

`@Content` mô tả nội dung được gửi hoặc nhận theo một media type. Trong request body, nó thường được đặt bên trong annotation OpenAPI `@RequestBody` và có thể chứa schema, ví dụ hoặc encoding.

Các thuộc tính thường dùng:

| Thuộc tính | Vai trò |
| --- | --- |
| `mediaType` | Kiểu nội dung, ví dụ `application/json` |
| `schema` | Cấu trúc dữ liệu của nội dung |
| `examples` | Một hoặc nhiều ví dụ payload |
| `example` | Ví dụ đơn giản cho nội dung |
| `encoding` | Quy tắc encoding cho các property, thường hữu ích với multipart/form data |

Với API JSON thông thường, `mediaType = MediaType.APPLICATION_JSON_VALUE` và schema DTO thường là đủ. Không cần tạo `@Content` riêng nếu Springdoc đã suy ra đúng nội dung từ `@RequestBody` và kiểu tham số. Hãy bổ sung cấu hình tường minh khi muốn kiểm soát chính xác media type, mô tả hoặc ví dụ.

Một request body có thể hỗ trợ nhiều media type. Ví dụ, API có thể nhận JSON và một định dạng khác. Khi đó, khai báo nhiều `@Content` trong mảng `content` của OpenAPI request body, mỗi phần tử có `mediaType` và schema phù hợp. Mapping Spring cũng phải thực sự hỗ trợ các định dạng đó; chỉ thêm media type vào tài liệu không khiến converter tự xử lý định dạng mới.

## 6. Vai trò của `@Schema(implementation = ...)`

`@Schema` mô tả cấu trúc dữ liệu. Khi đặt `implementation = CreateBookRequest.class`, bạn yêu cầu OpenAPI dùng schema của lớp đó cho nội dung request.

Ví dụ rút gọn:

```java
@Content(
    mediaType = "application/json",
    schema = @Schema(implementation = CreateBookRequest.class)
)
```

Springdoc sẽ tạo hoặc tham chiếu schema tương ứng trong `components.schemas`, thường dùng `$ref` thay vì lặp lại toàn bộ cấu trúc trong từng operation. Cách này giúp nhiều endpoint tái sử dụng cùng DTO và giữ tài liệu nhất quán.

Một số thuộc tính `@Schema` thường gặp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `name` | Tên hiển thị hoặc tên schema theo ngữ cảnh |
| `description` | Mô tả object hoặc field |
| `example` | Một giá trị minh họa |
| `type` | Kiểu dữ liệu OpenAPI khi cần chỉ định tường minh |
| `format` | Định dạng chi tiết như `date`, `date-time`, `email` |
| `implementation` | Kiểu Java được dùng làm schema |
| `requiredMode` | Xác định cách đánh dấu field bắt buộc trong schema |
| `accessMode` | Thể hiện field chỉ đọc, chỉ ghi hoặc đọc/ghi |

Với DTO, nên để Springdoc suy ra kiểu dữ liệu từ Java và chỉ ghi rõ những metadata có ích. Nếu đặt `type` hoặc `implementation` không phù hợp với kiểu thực tế, schema có thể mâu thuẫn với JSON mà Jackson serialize/deserialize.

## 7. Ví dụ controller hoàn chỉnh có validation

Ví dụ sau kết hợp DTO, `@RequestBody` của Spring, `@Valid`, `@Content`, `@Schema` và response metadata:

```java
package com.example.books;

import com.example.books.dto.CreateBookRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
        summary = "Tạo sách mới",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            description = "Thông tin sách ở định dạng JSON",
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreateBookRequest.class)
            )
        )
    )
    @ApiResponses({
        @ApiResponse(responseCode = "201", description = "Tạo sách thành công"),
        @ApiResponse(responseCode = "400", description = "JSON không hợp lệ hoặc dữ liệu không đạt validation")
    })
    public ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        BookResponse response = new BookResponse(
            1L,
            request.title(),
            request.publicationYear()
        );

        return ResponseEntity.status(201).body(response);
    }

    public record BookResponse(
        long id,
        String title,
        Integer publicationYear
    ) {}
}
```

Controller trả về `201 Created` khi tạo thành công. Với JSON sai cú pháp hoặc dữ liệu không đạt validation, Spring thường trả về `400 Bad Request` nếu ứng dụng dùng cấu hình xử lý lỗi mặc định hoặc exception handler tương ứng. Nếu dự án có định dạng lỗi riêng, hãy mô tả response lỗi bằng schema lỗi thực tế thay vì chỉ ghi mô tả chung.

Đảm bảo dự án có dependency validation, ví dụ:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Không thêm dependency này chỉ để tạo tài liệu; nó cần thiết khi muốn thực thi các annotation validation như `@NotBlank`, `@Size` hoặc `@Min`.

## 8. Request body bắt buộc, tùy chọn và schema required

Có hai khái niệm `required` khác nhau cần phân biệt:

- `requestBody.required`: cho biết toàn bộ body có bắt buộc phải xuất hiện trong request hay không.
- `schema.required`: danh sách tên các field bắt buộc bên trong JSON object.

Ví dụ body bắt buộc nhưng field `publicationYear` tùy chọn:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - title
        properties:
          title:
            type: string
          publicationYear:
            type: integer
            format: int32
```

Request phải có JSON body, nhưng không nhất thiết phải có `publicationYear`. Field `title` phải xuất hiện trong object. Khi dùng record hoặc class DTO, các annotation validation, kiểu dữ liệu và cấu hình `@Schema(requiredMode = ...)` có thể ảnh hưởng đến schema được sinh ra. Hãy kiểm tra kết quả OpenAPI thay vì chỉ suy luận từ constructor hoặc kiểu Java.

Nếu body thực sự tùy chọn, Spring có thể khai báo:

```java
public ResponseEntity<Void> updateNote(
        @RequestBody(required = false) UpdateNoteRequest request) {
    // Xử lý request null theo hợp đồng.
    return ResponseEntity.noContent().build();
}
```

Trong trường hợp đó, annotation OpenAPI request body cũng cần `required = false`. Nếu một bên ghi bắt buộc và bên kia cho phép thiếu body, tài liệu sẽ gây hiểu nhầm và có thể khiến client tích hợp sai.

## 9. Ví dụ JSON và `@ExampleObject`

Ví dụ payload giúp người dùng Swagger UI hiểu dữ liệu cần gửi. Có thể khai báo một ví dụ:

```java
@Content(
    mediaType = MediaType.APPLICATION_JSON_VALUE,
    schema = @Schema(implementation = CreateBookRequest.class),
    examples = @ExampleObject(
        name = "CreateBook",
        summary = "Tạo sách có năm xuất bản",
        value = "{\"title\":\"Spring Boot căn bản\",\"publicationYear\":2025}"
    )
)
```

Hoặc khai báo nhiều ví dụ cho các tình huống khác nhau:

```java
@Content(
    mediaType = "application/json",
    schema = @Schema(implementation = CreateBookRequest.class),
    examples = {
        @ExampleObject(
            name = "WithYear",
            summary = "Có năm xuất bản",
            value = "{\"title\":\"Spring Boot căn bản\",\"publicationYear\":2025}"
        ),
        @ExampleObject(
            name = "WithoutYear",
            summary = "Không cung cấp năm xuất bản",
            value = "{\"title\":\"REST API thực hành\"}"
        )
    }
)
```

Ví dụ phải là JSON hợp lệ và phù hợp schema. Không đưa token, mật khẩu, dữ liệu cá nhân hoặc thông tin thật của khách hàng vào example. Nếu có nhiều tình huống validation, có thể ghi rõ ví dụ hợp lệ và giải thích riêng các điều kiện bị từ chối.

## 10. Cấu trúc OpenAPI sinh ra

Sau khi khởi chạy ứng dụng, truy cập `/v3/api-docs` và tìm operation POST. Kết quả rút gọn có thể giống cấu trúc sau:

```yaml
paths:
  /api/books:
    post:
      requestBody:
        description: Thông tin sách ở định dạng JSON
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateBookRequest'
      responses:
        '201':
          description: Tạo sách thành công
        '400':
          description: JSON không hợp lệ hoặc dữ liệu không đạt validation
components:
  schemas:
    CreateBookRequest:
      type: object
      properties:
        title:
          type: string
          description: Tên sách
          example: Spring Boot căn bản
        publicationYear:
          type: integer
          format: int32
          example: 2025
```

Đây là cấu trúc minh họa. Tên schema, danh sách required, mô tả và ví dụ thực tế phụ thuộc DTO, annotation, cấu hình Jackson, Bean Validation và phiên bản Springdoc.

Trong Swagger UI, operation POST sẽ có phần Request body với media type `application/json` và schema tương ứng. Người dùng có thể chọn **Try it out**, chỉnh payload và gửi request nếu server cho phép.

## 11. Lỗi thường gặp khi mô tả JSON request body

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy request body trong OpenAPI | Method thiếu Spring `@RequestBody`, tham số bị nhận diện như parameter khác hoặc metadata override không đúng | Kiểm tra chữ ký controller và `/v3/api-docs` |
| Swagger UI hiển thị schema rỗng | DTO không được nhận diện, kiểu generic phức tạp hoặc `@Schema(implementation = ...)` trỏ sai class | Kiểm tra schema trong `components.schemas` |
| Media type hiển thị không đúng | `consumes` hoặc `@Content.mediaType` không khớp | Đồng bộ mapping Spring và metadata OpenAPI |
| Tài liệu ghi body bắt buộc nhưng server cho phép bỏ qua | `requestBody.required` không khớp `@RequestBody(required = false)` | Đồng bộ hai annotation |
| JSON hợp lệ nhưng request trả về `400` | Kiểu dữ liệu không chuyển đổi được hoặc Bean Validation từ chối dữ liệu | Kiểm tra response lỗi, DTO và các constraint |
| Field bắt buộc không được thể hiện đúng | Chưa khai báo validation hoặc schema required mode phù hợp | Kiểm tra `required` của schema và annotation DTO |
| Example không xuất hiện hoặc sai định dạng | JSON trong `@ExampleObject` không hợp lệ hoặc không khớp schema | Kiểm tra chuỗi JSON và tài liệu OpenAPI đầu ra |
| API hỗ trợ nhiều định dạng nhưng tài liệu chỉ có JSON | Chỉ khai báo một `@Content` hoặc mapping chưa khai báo đúng `consumes` | Khai báo từng media type và kiểm tra converter thực tế |

Khi gặp vấn đề, hãy kiểm tra JSON OpenAPI trước rồi so sánh với hành vi controller. Nếu đặc tả đã đúng nhưng request thực tế thất bại, tập trung vào mapping, converter, DTO và validation. Nếu request chạy đúng nhưng tài liệu sai, kiểm tra annotation OpenAPI và cách Springdoc suy ra schema.

## 12. Checklist mô tả `application/json`

- [ ] Controller dùng Spring `@RequestBody` cho tham số chứa JSON.
- [ ] `consumes` phản ánh media type endpoint thực sự hỗ trợ.
- [ ] DTO có kiểu dữ liệu và tên field phù hợp với JSON thực tế.
- [ ] `@Schema` mô tả object, field và ví dụ cần thiết.
- [ ] `@Content` khai báo `application/json` và schema đúng khi cần mô tả tường minh.
- [ ] OpenAPI `@RequestBody.required` khớp với hành vi của Spring `@RequestBody`.
- [ ] Phân biệt request body bắt buộc với các field bắt buộc trong schema.
- [ ] Ví dụ JSON hợp lệ và không chứa dữ liệu nhạy cảm.
- [ ] Bean Validation được kích hoạt nếu hợp đồng có constraint cần thực thi.
- [ ] Đã kiểm tra `/v3/api-docs` và Request body trong Swagger UI.
- [ ] Response lỗi phản ánh định dạng lỗi thực tế của ứng dụng.

`@Content` xác định media type và nội dung của request body, còn `@Schema` mô tả cấu trúc JSON. Kết hợp hai annotation này với `@RequestBody` của Spring và DTO rõ ràng giúp Springdoc tạo hợp đồng dễ hiểu, để client biết chính xác cần gửi dữ liệu nào, theo định dạng gì và field nào bắt buộc.
