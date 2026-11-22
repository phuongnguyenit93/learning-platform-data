# Dùng lại responses trong components

Trong một API Spring Boot, nhiều operation thường trả cùng một kiểu phản hồi. Ví dụ, nhiều endpoint có thể trả `401 Unauthorized`, `403 Forbidden`, `404 Not Found` hoặc `500 Internal Server Error` với cùng cấu trúc lỗi. Nếu mô tả lặp lại toàn bộ response ở từng controller method, tài liệu OpenAPI nhanh chóng dài, khó cập nhật và dễ lệch nhau.

OpenAPI cung cấp `components.responses` để định nghĩa một Response Object có thể tái sử dụng. Mỗi operation tham chiếu tới định nghĩa đó bằng `$ref`. Springdoc-openapi có thể đưa các component này vào tài liệu được sinh ra thông qua cấu hình `OpenAPI` và sử dụng chúng từ annotation `@ApiResponse(ref = ...)`.

Điểm cần nhớ: component mô tả nội dung response; status code vẫn được khai báo tại operation. Cùng một response component có thể được dùng ở nhiều operation khi ngữ nghĩa, body, header và media type thực sự giống nhau.

## 1. Vì sao nên dùng `components.responses`?

Giả sử ứng dụng có các endpoint:

- `GET /api/documents/{id}` lấy tài liệu.
- `DELETE /api/documents/{id}` xóa tài liệu.
- `GET /api/users/{id}` lấy người dùng.
- `GET /api/orders/{id}` lấy đơn hàng.

Cả bốn endpoint có thể trả `404 Not Found` với cùng cấu trúc lỗi gồm `code`, `message`, `timestamp` và `path`. Nếu mỗi operation tự định nghĩa schema và ví dụ, cùng một quy tắc có thể bị sao chép nhiều lần.

Tái sử dụng response mang lại các lợi ích:

- **Nhất quán**: mọi operation dùng chung một cấu trúc response lỗi.
- **Dễ bảo trì**: thay đổi mô tả, header hoặc ví dụ tại một component.
- **Dễ đọc**: phần `responses` của operation ngắn hơn và tập trung vào các kết quả riêng của endpoint.
- **Hỗ trợ kiểm tra hợp đồng**: có thể kiểm tra các operation cùng tham chiếu một response component chuẩn.
- **Giảm sai lệch**: tránh trường hợp endpoint này mô tả lỗi `404` có field `message`, endpoint khác lại dùng `detail` dù runtime trả cùng một JSON.

Không nên tái sử dụng chỉ để giảm số dòng. Nếu hai response có ý nghĩa hoặc cấu trúc khác nhau, hãy định nghĩa hai component riêng, dù chúng cùng dùng một schema lỗi bên dưới.

## 2. Cấu trúc `components.responses`

Trong OpenAPI, `components` là nơi chứa các định nghĩa có thể dùng lại. `components.responses` chứa Response Object được đặt tên:

```yaml
components:
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
      content:
        application/json:
          schema:
            type: object
            properties:
              code:
                type: string
              message:
                type: string
```

Một Response Object thường có các thành phần:

| Thành phần | Mục đích |
|---|---|
| `description` | Mô tả ý nghĩa của phản hồi. Đây là trường bắt buộc. |
| `headers` | Mô tả các header được trả về ngoài những header chuẩn đã được xử lý riêng. |
| `content` | Ánh xạ media type tới schema và ví dụ của body. |
| `links` | Mô tả liên kết tới operation khác có thể thực hiện tiếp theo. |

Response component không chứa status code. Status được đặt làm key trong `responses` của operation, ví dụ `'404'`, `'401'` hoặc `default`.

## 3. Định nghĩa response dùng chung và tham chiếu bằng `$ref`

Ví dụ dưới đây định nghĩa một schema lỗi và ba response có thể dùng lại:

```yaml
openapi: 3.1.0
info:
  title: Document API
  version: 1.0.0
paths:
  /api/documents/{id}:
    get:
      summary: Lấy tài liệu theo mã
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Tìm thấy tài liệu
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DocumentResponse'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '404':
          $ref: '#/components/responses/NotFound'
        '500':
          $ref: '#/components/responses/InternalServerError'

components:
  schemas:
    DocumentResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
    ApiError:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
        message:
          type: string
        timestamp:
          type: string
          format: date-time
        path:
          type: string
  responses:
    Unauthorized:
      description: Yêu cầu chưa được xác thực hoặc thông tin xác thực không hợp lệ
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
    NotFound:
      description: Không tìm thấy tài nguyên theo mã đã cung cấp
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
    InternalServerError:
      description: Đã xảy ra lỗi ngoài dự kiến khi xử lý yêu cầu
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
```

Ở đây:

- `components.schemas.ApiError` định nghĩa cấu trúc body lỗi dùng chung.
- `components.responses.NotFound` định nghĩa response hoàn chỉnh, bao gồm mô tả và content.
- Operation dùng `$ref: '#/components/responses/NotFound'` để tham chiếu response đó.
- `404` vẫn được khai báo tại operation; component `NotFound` không tự quyết định status code.

Một schema có thể được dùng trong nhiều response component. Ví dụ `ApiError` có thể là body của `Unauthorized`, `NotFound` và `InternalServerError`, trong khi mỗi response có description riêng.

## 4. Tái sử dụng response ở nhiều operation

Khi nhiều operation có cùng ý nghĩa phản hồi, cùng media type và cùng cấu trúc, chúng có thể tham chiếu một component:

```yaml
paths:
  /api/documents/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
    delete:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'

  /api/users/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
```

Cả ba operation cùng dùng một định nghĩa `NotFound`. Nếu sau này response lỗi bổ sung header hoặc đổi media type, chỉ cần cập nhật component rồi kiểm tra lại các operation phụ thuộc.

Tuy nhiên, nếu một endpoint trả `404` với thông điệp “Không tìm thấy tài liệu”, endpoint khác trả `404` với thông điệp “Không tìm thấy người dùng”, hãy cân nhắc một response component tổng quát có description trung lập, hoặc tạo component riêng nếu ý nghĩa cần được thể hiện cụ thể. Tránh dùng một description quá đặc thù cho mọi endpoint.

## 5. Định nghĩa component trong ứng dụng Spring Boot

Khi springdoc sinh tài liệu từ controller, có thể đăng ký các response dùng chung bằng một bean `OpenAPI`. Springdoc kết hợp component này vào tài liệu được xuất ra.

### 5.1. Khai báo component bằng OpenAPI model

Ví dụ tạo schema lỗi và response `NotFound`/`Unauthorized` bằng Swagger Core model:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.IntegerSchema;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiResponseConfiguration {

    @Bean
    OpenAPI openAPI() {
        Schema<?> errorSchema = new Schema<>()
                .type("object")
                .addRequiredItem("code")
                .addRequiredItem("message")
                .addProperty("code", new StringSchema()
                        .example("DOCUMENT_NOT_FOUND"))
                .addProperty("message", new StringSchema()
                        .example("Không tìm thấy tài liệu"))
                .addProperty("status", new IntegerSchema()
                        .example(404));

        Content errorContent = new Content().addMediaType(
                "application/json",
                new MediaType().schema(
                        new Schema<>().$ref("#/components/schemas/ApiError")
                )
        );

        ApiResponse notFound = new ApiResponse()
                .description("Không tìm thấy tài nguyên")
                .content(errorContent);

        ApiResponse unauthorized = new ApiResponse()
                .description("Yêu cầu chưa được xác thực")
                .content(errorContent);

        Components components = new Components()
                .addSchemas("ApiError", errorSchema)
                .addResponses("NotFound", notFound)
                .addResponses("Unauthorized", unauthorized);

        return new OpenAPI()
                .info(new Info().title("Document API").version("1.0.0"))
                .components(components);
    }
}
```

`Components.addResponses(name, response)` đăng ký response theo tên. `Components.addSchemas(name, schema)` đăng ký schema lỗi được response tham chiếu. Tên `NotFound`, `Unauthorized` và `ApiError` phải nhất quán với các `$ref` trong tài liệu.

Ví dụ trên dùng `application/json` và schema `ApiError` để minh họa. Trong ứng dụng thực tế, hãy điều chỉnh media type, field và ví dụ cho khớp với error DTO mà controller hoặc `@RestControllerAdvice` thật sự trả về.

### 5.2. Sử dụng response component trong controller

Sau khi component đã được đăng ký, method có thể tham chiếu tới nó bằng `@ApiResponse(ref = ...)`:

```java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import java.util.UUID;

@RestController
class DocumentController {

    @GetMapping("/api/documents/{id}")
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy tài liệu",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = DocumentResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "401",
            ref = "#/components/responses/Unauthorized"
        ),
        @ApiResponse(
            responseCode = "404",
            ref = "#/components/responses/NotFound"
        )
    })
    DocumentResponse findById(@PathVariable UUID id) {
        return documentService.findById(id);
    }
}
```

`responseCode` xác định key trong `responses` của operation; `ref` trỏ tới response component. Với các response có body phức tạp, tham chiếu giúp tránh lặp lại `content`, `schema` và ví dụ ở từng method.

Kết quả OpenAPI mong đợi có dạng:

```yaml
responses:
  '200':
    description: Tìm thấy tài liệu
  '401':
    $ref: '#/components/responses/Unauthorized'
  '404':
    $ref: '#/components/responses/NotFound'
```

Hãy kiểm tra output thực tế của phiên bản springdoc và Swagger Annotations đang dùng. Nếu `$ref` không xuất hiện như mong đợi, xác nhận component đã được đăng ký trong đúng tài liệu OpenAPI và annotation đang dùng đúng thuộc tính `ref`.

## 6. Tái sử dụng response chứa nhiều media type

Một response component có thể định nghĩa nhiều representation trong `content`, giống một response được khai báo trực tiếp ở operation:

```yaml
components:
  responses:
    ExportReady:
      description: Tệp xuất đã sẵn sàng
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ExportMetadata'
        application/zip:
          schema:
            type: string
            format: binary
```

Khi operation tham chiếu `ExportReady`, nó kế thừa mô tả và cả hai media type. Client có thể chọn representation theo `Accept` header nếu endpoint thực sự hỗ trợ cả JSON và ZIP.

Trong controller, `produces` phải khớp với các media type được mô tả:

```java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import java.util.UUID;

@GetMapping(
        path = "/api/exports/{id}",
        produces = {
            MediaType.APPLICATION_JSON_VALUE,
            "application/zip"
        }
)
@ApiResponse(
        responseCode = "200",
        ref = "#/components/responses/ExportReady"
)
ResponseEntity<?> downloadExport(@PathVariable UUID id) {
    // Trả JSON hoặc ZIP theo content negotiation.
    return exportService.getRepresentation(id);
}
```

Response component mô tả representation có thể trả về; controller và message converter vẫn phải thực hiện content negotiation và trả đúng `Content-Type`.

## 7. Tái sử dụng headers và examples bên trong response

Response component có thể chứa header, content và ví dụ. Điều đó giúp tái sử dụng cả thông tin đi kèm body.

### 7.1. Response header

Ví dụ response `429 Too Many Requests` có header `Retry-After`:

```yaml
components:
  responses:
    TooManyRequests:
      description: Đã vượt giới hạn số request
      headers:
        Retry-After:
          description: Số giây cần chờ trước khi gửi lại request
          schema:
            type: integer
            minimum: 1
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
```

Khi operation tham chiếu `TooManyRequests`, client biết cần đọc `Retry-After` trước khi retry. Ở runtime, server hoặc gateway phải thực sự trả header này; khai báo trong OpenAPI không tự thêm header vào HTTP response.

### 7.2. Ví dụ response dùng chung

Có thể đặt ví dụ ngay trong Media Type Object của response component:

```yaml
components:
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
          examples:
            documentMissing:
              summary: Tài liệu không tồn tại
              value:
                code: DOCUMENT_NOT_FOUND
                message: Không tìm thấy tài liệu
                status: 404
```

Ví dụ được dùng chung ở mọi operation tham chiếu component. Nếu ví dụ cần thay đổi theo từng tài nguyên, cân nhắc tạo response component riêng hoặc dùng schema dùng chung nhưng mô tả/example ở cấp operation theo cách phù hợp với phiên bản OpenAPI.

## 8. Dùng response component với `default`

OpenAPI hỗ trợ key `default` trong `responses` để mô tả phản hồi cho những status không được liệt kê riêng. Có thể tham chiếu một response dùng chung:

```yaml
paths:
  /api/documents/{id}:
    get:
      responses:
        '200':
          description: Tìm thấy tài liệu
        '404':
          $ref: '#/components/responses/NotFound'
        default:
          $ref: '#/components/responses/UnexpectedError'
```

`default` không phải một status code cụ thể. Nó là response dự phòng cho các status không được khai báo riêng. Nếu API có các lỗi quan trọng như `400`, `401`, `403`, `404` hoặc `409`, thường nên mô tả tường minh để client biết cách xử lý từng trường hợp; `default` chỉ nên làm lớp dự phòng.

Ví dụ trên giả định `components.responses.UnexpectedError` đã được định nghĩa trong cùng tài liệu OpenAPI.

Không dùng `default` để che giấu một response thành công hoặc lỗi đã biết. Client generator có thể xử lý response cụ thể và default theo cách khác nhau.

## 9. Khi nào nên tách response component?

Không phải mọi response dùng chung schema đều nên gộp vào một response component. Hãy phân biệt việc tái sử dụng **Response Object** với tái sử dụng **Schema Object**:

| Nhu cầu | Nên tái sử dụng |
|---|---|
| Cùng body lỗi, cùng media type, cùng header và cùng ý nghĩa | Response component, ví dụ `NotFound`. |
| Cùng cấu trúc body nhưng mô tả khác theo endpoint | Schema component dùng chung; tạo response riêng cho từng operation. |
| Cùng response nhưng có thêm header khác nhau theo operation | Response component cơ sở hoặc schema dùng chung; định nghĩa response riêng nếu header khác là một phần hợp đồng. |
| Cùng status nhưng body khác nhau theo ngữ cảnh | Response component riêng cho từng ngữ cảnh. |
| Chỉ cùng status code nhưng ý nghĩa khác | Không dùng chung response chỉ dựa trên status. |

Ví dụ, `404` cho tài liệu và `404` cho đơn hàng đều có thể dùng schema `ApiError`, nhưng description có thể khác. Có thể tạo hai response:

```yaml
components:
  responses:
    DocumentNotFound:
      description: Không tìm thấy tài liệu
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
    OrderNotFound:
      description: Không tìm thấy đơn hàng
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
```

Hai response component dùng chung schema nhưng giữ đúng ngữ nghĩa của từng tài nguyên.

## 10. Quy tắc `$ref` khi dùng Response Object

Response component được tham chiếu bằng Reference Object. Ví dụ:

```yaml
'404':
  $ref: '#/components/responses/NotFound'
```

Một số điểm cần lưu ý:

- Local reference bắt đầu bằng `#/components/responses/` và tên component phải tồn tại.
- Key trong `components.responses` phân biệt chữ hoa/chữ thường; `NotFound` và `notFound` là hai tên khác nhau.
- Component phải là Response Object hợp lệ, tối thiểu có `description`.
- Không trỏ response tới `components.schemas`; schema và response là hai loại object khác nhau.
- Trong OpenAPI 3.0, các sibling field đặt cạnh `$ref` trong Reference Object bị bỏ qua.
- Trong OpenAPI 3.1, Reference Object cho phép `summary` và `description` để ghi đè metadata tương ứng; các field tùy ý khác không được xem là phần mở rộng hợp lệ.

Ví dụ sau không có tác dụng ghi đè `content` trong OpenAPI 3.0:

```yaml
'404':
  $ref: '#/components/responses/NotFound'
  content:
    application/problem+json:
      schema:
        $ref: '#/components/schemas/Problem'
```

Nếu cần body hoặc header khác, tạo component response riêng. Với OpenAPI 3.1, có thể ghi đè `description` hoặc `summary` theo quy tắc Reference Object, nhưng không thể tùy ý ghi đè toàn bộ `content` bằng sibling fields.

## 11. Kiểm tra response component được springdoc xuất ra

Sau khi đăng ký component và thêm `@ApiResponse(ref = ...)`, mở `/v3/api-docs` hoặc endpoint tài liệu đã cấu hình. Kiểm tra hai phía:

1. `components.responses` có component với tên mong đợi.
2. Component có `description`, `content`, schema, headers và examples đúng.
3. Mỗi `$ref` từ operation trỏ tới component có thật.
4. Response code của operation đúng với nhánh runtime.
5. Schema được tham chiếu trong response component tồn tại trong `components.schemas`.
6. Media type trong component khớp với `Content-Type` server thực sự trả.
7. Header được mô tả có mặt trong response runtime khi điều kiện tương ứng xảy ra.

Ví dụ kiểm tra bằng MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReusableResponseOpenApiTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsNotFoundAsReusableResponse() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.components.responses.NotFound.description"
                ).value("Không tìm thấy tài nguyên"))
                .andExpect(jsonPath(
                        "$.paths['/api/documents/{id}'].get.responses['404']['$ref']"
                ).value("#/components/responses/NotFound"));
    }
}
```

Tên path, group và description trong test phải khớp với tài liệu thực tế. Nếu tài liệu được chia thành nhiều `GroupedOpenApi`, hãy kiểm tra đúng URL `/v3/api-docs/{group}` và bảo đảm component được thêm vào từng tài liệu cần dùng.

## 12. Kiểm tra response runtime

Một `$ref` hợp lệ không chứng minh endpoint thực sự trả response tương ứng. Cần kiểm tra runtime với các tình huống tạo ra status đó:

```java
@Test
void returnsDocumentNotFoundResponse() throws Exception {
    mockMvc.perform(get("/api/documents/{id}", UUID.randomUUID()))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("DOCUMENT_NOT_FOUND"))
            .andExpect(jsonPath("$.message").exists());
}
```

Test này giả định ứng dụng chuyển lỗi không tìm thấy thành response JSON có `code` và `message`. Nếu ứng dụng dùng `ProblemDetail`, `application/problem+json` hoặc error envelope khác, điều chỉnh assertion và component tương ứng.

Nên kiểm tra thêm các trường hợp:

- `401` có body và `WWW-Authenticate` nếu cơ chế xác thực yêu cầu.
- `403` phản ánh đúng lỗi thiếu quyền.
- `429` có `Retry-After` nếu API công bố khả năng retry.
- `500` dùng error body đã chuẩn hóa và không để lộ stack trace hoặc thông tin nội bộ.
- Các response dùng chung từ `@RestControllerAdvice` thực sự có cùng cấu trúc với component đã khai báo.

## 13. Dùng response component trong tài liệu tĩnh hoặc nhiều group

Nếu nhóm phát triển quản lý một file OpenAPI YAML/JSON tĩnh thay vì sinh toàn bộ từ controller, có thể định nghĩa `components.responses` trực tiếp trong file rồi tham chiếu bằng `$ref` như ví dụ ở phần 3.

Nếu ứng dụng dùng nhiều `GroupedOpenApi`, mỗi group có thể tạo một tài liệu riêng. Khi đó, kiểm tra component response đã được đăng ký trong tài liệu mà operation thuộc về. Một `$ref` trong group `internal` không tự động có nghĩa component đã xuất hiện trong group `public`.

Với cấu hình bằng code, có thể dùng `OpenApiCustomizer` cho tài liệu mặc định hoặc customizer gắn với group theo cấu hình dự án. Chọn đúng loại customizer và kiểm tra tài liệu từng group; không giả định một bean cấu hình đã tác động đến mọi tài liệu mà ứng dụng xuất ra.

## 14. Những lỗi thường gặp

- **Đặt response trong `components.schemas`**: schema chỉ mô tả body; response component phải nằm trong `components.responses`.
- **Quên `description`**: Response Object cần có mô tả.
- **Tham chiếu sai tên hoặc sai chữ hoa/chữ thường**: `$ref` không phân giải được nếu tên component không khớp.
- **Dùng `$ref` tới schema ở vị trí response**: trỏ tới `#/components/responses/...`, hoặc định nghĩa response object bao gồm schema.
- **Khai báo component nhưng không tham chiếu**: component không tự gắn vào operation và không tạo response runtime.
- **Khai báo `$ref` nhưng chưa đăng ký component**: tài liệu có tham chiếu hỏng hoặc validator báo lỗi.
- **Tái sử dụng response chỉ vì cùng status**: status `404` không có nghĩa mọi endpoint có cùng description, body và header.
- **Đặt `content` bên cạnh `$ref` để ghi đè**: sibling fields bị bỏ qua theo quy tắc Reference Object; dùng component riêng nếu nội dung khác.
- **Cho rằng response annotation thay đổi runtime**: `@ApiResponse` chỉ mô tả OpenAPI; controller/advice vẫn phải trả đúng status và body.
- **Quên group tài liệu**: component có thể có trong tài liệu mặc định nhưng thiếu trong group được kiểm tra.

## 15. Quy trình triển khai response dùng chung

1. **Tìm các response lặp lại**: xác định những response có cùng ý nghĩa, media type, schema và header.
2. **Tách schema dùng chung**: tạo `components.schemas` cho body nếu nhiều response cùng dùng cấu trúc đó.
3. **Tạo Response Object**: thêm mô tả, content, headers, examples hoặc links vào `components.responses`.
4. **Đăng ký component**: khai báo trong OpenAPI YAML hoặc thêm bằng bean `OpenAPI`/customizer của springdoc.
5. **Tham chiếu tại operation**: dùng `$ref` trong YAML hoặc `@ApiResponse(ref = "#/components/responses/...")`.
6. **Kiểm tra tài liệu sinh ra**: xác nhận component tồn tại và tất cả reference đều phân giải được.
7. **Kiểm thử runtime**: xác nhận controller hoặc exception handler trả đúng status, content type, body và header.
8. **Review thay đổi hợp đồng**: nếu sửa component dùng chung, đánh giá tất cả operation đang tham chiếu vì thay đổi có thể ảnh hưởng nhiều client.

## 16. Checklist review

- [ ] Response dùng chung được đặt trong `components.responses`.
- [ ] Schema body dùng chung được đặt trong `components.schemas`.
- [ ] Mỗi Response Object có `description` rõ ràng.
- [ ] Media type và schema phản ánh body runtime.
- [ ] Header và example được khai báo khi client cần.
- [ ] Operation tham chiếu đúng component bằng `$ref` hoặc `@ApiResponse(ref = ...)`.
- [ ] Status code vẫn được khai báo tại operation.
- [ ] Tên component và JSON Pointer đúng chữ hoa/chữ thường.
- [ ] Không đặt sibling `content` hoặc field tùy ý cạnh `$ref` với kỳ vọng ghi đè.
- [ ] Component có mặt trong từng tài liệu/group cần công bố.
- [ ] `/v3/api-docs` không chứa reference hỏng.
- [ ] Integration test kiểm tra response runtime và OpenAPI reference.

## 17. Tài liệu tham khảo

- [OpenAPI Specification 3.1.2 – Components Object](https://spec.openapis.org/oas/v3.1.2.html#components-object)
- [OpenAPI Specification 3.1.2 – Response Object](https://spec.openapis.org/oas/v3.1.2.html#response-object)
- [OpenAPI Specification 3.1.2 – Reference Object](https://spec.openapis.org/oas/v3.1.2.html#reference-object)
- [Swagger Annotations – `@ApiResponse`](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/responses/ApiResponse.html)
- [Swagger Core – OpenAPI model](https://github.com/swagger-api/swagger-core)
- [springdoc-openapi documentation](https://springdoc.org/)

`components.responses` giúp định nghĩa một Response Object duy nhất và dùng lại ở nhiều operation. Hãy tái sử dụng khi ngữ nghĩa, schema, media type và header thực sự giống nhau; tách response riêng khi mô tả khác nhau nhưng vẫn có thể dùng chung schema. Cuối cùng, xác minh `$ref` trong OpenAPI và response HTTP thực tế để bảo đảm tài liệu và ứng dụng cùng thực hiện một hợp đồng.
