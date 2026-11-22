# Schema, parameter, response, requestBody và securityScheme trong components

OpenAPI cho phép khai báo các thành phần có thể tái sử dụng trong đối tượng `components`. Những thành phần như schema, parameter, response, request body và security scheme giúp nhiều operation dùng chung một định nghĩa, giữ hợp đồng nhất quán và giảm lặp nội dung trong tài liệu. Springdoc-openapi có thể suy luận nhiều thành phần từ controller và DTO Spring Boot; khi cần một hợp đồng rõ ràng, ta có thể bổ sung annotation hoặc cấu hình để mô tả và tham chiếu chúng.

## 1. Components là kho định nghĩa dùng chung

Trong OpenAPI, `components` là nơi đặt các định nghĩa có thể được tham chiếu từ nhiều vị trí trong tài liệu. Các thành phần thường dùng gồm:

| Nhóm | Khóa trong `components` | Mục đích |
|---|---|---|
| Schema | `schemas` | Mô tả cấu trúc dữ liệu, DTO, enum và kiểu lồng nhau |
| Parameter | `parameters` | Tái sử dụng path, query, header hoặc cookie parameter |
| Response | `responses` | Tái sử dụng mô tả response theo status code |
| Request body | `requestBodies` | Tái sử dụng body request cùng media type và schema |
| Security scheme | `securitySchemes` | Khai báo cách xác thực như API key, Basic, Bearer, OAuth2 hoặc OpenID Connect |
| Các nhóm khác | `examples`, `headers`, `links`, `callbacks` | Tái sử dụng ví dụ, header response, liên kết operation và callback |

Một định nghĩa nằm trong `components` chưa tự tạo endpoint và cũng chưa tự áp dụng cho operation. Nó chỉ có hiệu lực khi được tham chiếu bằng `$ref` hoặc được dùng trong cấu hình tương ứng. Ví dụ, khai báo `Product` trong `components.schemas` chưa làm cho response của `GET /products/{id}` tự động có schema đó; operation phải trỏ tới `#/components/schemas/Product`.

Ví dụ cấu trúc:

```yaml
openapi: 3.1.0
info:
  title: Store API
  version: 1.0.0
paths: {}
components:
  schemas: {}
  parameters: {}
  responses: {}
  requestBodies: {}
  securitySchemes: {}
```

Tên component là khóa do người viết tài liệu đặt, có phân biệt chữ hoa và chữ thường. Nên đặt tên thể hiện vai trò và dùng nhất quán, chẳng hạn `Product`, `CreateProductRequest`, `ProductNotFound` hoặc `BearerAuth`.

## 2. $ref kết nối operation với component

`$ref` là tham chiếu tới một đối tượng được định nghĩa ở vị trí khác. Với component trong cùng tài liệu, cú pháp thường dùng là JSON Pointer bắt đầu bằng `#/components/`:

```yaml
schema:
  $ref: '#/components/schemas/Product'
```

Một số đường dẫn tham chiếu thường gặp:

| Đối tượng được tham chiếu | Đường dẫn |
|---|---|
| Schema `Product` | `#/components/schemas/Product` |
| Parameter `PageSize` | `#/components/parameters/PageSize` |
| Response `NotFound` | `#/components/responses/NotFound` |
| Request body `CreateProduct` | `#/components/requestBodies/CreateProduct` |
| Security scheme `BearerAuth` | `#/components/securitySchemes/BearerAuth` |

Ví dụ cùng một schema được sử dụng trong hai response:

```yaml
paths:
  /products/{id}:
    get:
      responses:
        '200':
          description: Tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
  /products:
    post:
      responses:
        '201':
          description: Sản phẩm đã được tạo
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
```

Khi component thay đổi, mọi operation tham chiếu đến nó đều nhận định nghĩa mới. Điều này giúp tránh sao chép schema nhưng cũng có nghĩa một thay đổi trong component dùng chung có thể ảnh hưởng nhiều endpoint. Hãy xem xét tác động của thay đổi trước khi chỉnh component được dùng rộng rãi.

## 3. Schema mô tả cấu trúc dữ liệu

Schema trong OpenAPI mô tả kiểu dữ liệu, thuộc tính, ràng buộc và quan hệ giữa các giá trị. Với API Spring Boot, schema thường tương ứng với DTO request, DTO response, enum hoặc kiểu dữ liệu lồng nhau.

Ví dụ component schema cho sản phẩm:

```yaml
components:
  schemas:
    Product:
      type: object
      required:
        - id
        - name
        - price
      properties:
        id:
          type: string
          format: uuid
          description: Mã định danh sản phẩm
        name:
          type: string
          minLength: 1
          maxLength: 120
          example: Bút bi
        price:
          type: number
          minimum: 0
          example: 12000
        active:
          type: boolean
          default: true
```

Các trường quan trọng:

- `type` xác định kiểu như `object`, `string`, `integer`, `number`, `boolean` hoặc `array`.
- `properties` liệt kê các thuộc tính của object.
- `required` liệt kê các thuộc tính bắt buộc phải có trong object. Một property không nằm trong danh sách này thường là tùy chọn.
- `format` bổ sung định dạng như `uuid`, `date`, `date-time`, `int32` hoặc `int64`.
- `enum` giới hạn các giá trị được phép.
- `minimum`, `maximum`, `minLength`, `maxLength`, `minItems` và `maxItems` mô tả giới hạn dữ liệu.
- `description`, `example` và `default` giúp người đọc hiểu cách sử dụng trường.

Schema không tự thực thi validation trong controller. Ví dụ, `minimum: 0` mô tả giá trị tối thiểu trong hợp đồng; ứng dụng vẫn cần validation hoặc logic nghiệp vụ để từ chối giá trị âm.

### Mảng và object lồng nhau

Một property có thể tham chiếu schema khác hoặc mô tả trực tiếp mảng:

```yaml
components:
  schemas:
    ProductLine:
      type: object
      required: [product, quantity]
      properties:
        product:
          $ref: '#/components/schemas/Product'
        quantity:
          type: integer
          minimum: 1
    ProductOrder:
      type: object
      properties:
        orderId:
          type: string
        lines:
          type: array
          items:
            $ref: '#/components/schemas/ProductLine'
```

### Enum và các kiểu kết hợp

Enum thể hiện tập giá trị hữu hạn:

```yaml
components:
  schemas:
    ProductStatus:
      type: string
      enum:
        - DRAFT
        - ACTIVE
        - ARCHIVED
```

Khi một schema có nhiều dạng hợp lệ, OpenAPI hỗ trợ các cấu trúc như `oneOf`, `anyOf` và `allOf`:

```yaml
components:
  schemas:
    PaymentMethod:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransfer'
    AuditedEntity:
      type: object
      properties:
        createdAt:
          type: string
          format: date-time
    AuditedProduct:
      allOf:
        - $ref: '#/components/schemas/Product'
        - $ref: '#/components/schemas/AuditedEntity'
```

`oneOf` yêu cầu dữ liệu khớp đúng một schema trong danh sách; `anyOf` cho phép khớp một hoặc nhiều schema; `allOf` kết hợp các schema thành một mô hình. Khi dùng kiểu đa hình, cân nhắc thêm discriminator để client generator nhận biết subtype. Cần kiểm tra khả năng hỗ trợ của các công cụ đọc OpenAPI, vì không phải generator nào cũng xử lý mọi cấu trúc giống nhau.

## 4. Parameter mô tả dữ liệu trên URL, header và cookie

OpenAPI Parameter Object mô tả một giá trị được truyền cùng request ngoài request body. Parameter có bốn vị trí phổ biến:

| `in` | Vị trí | Ví dụ |
|---|---|---|
| `path` | Thành phần trong đường dẫn | `/products/{id}` |
| `query` | Query string | `?page=0&size=20` |
| `header` | HTTP header | `X-Request-Id: abc-123` |
| `cookie` | Cookie | `sessionId=...` |

Ví dụ parameter query có thể tái sử dụng:

```yaml
components:
  parameters:
    PageNumber:
      name: page
      in: query
      required: false
      description: Số trang bắt đầu từ 0
      schema:
        type: integer
        minimum: 0
        default: 0
    PageSize:
      name: size
      in: query
      required: false
      description: Số phần tử trong một trang
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
```

Operation sử dụng parameter bằng `$ref`:

```yaml
paths:
  /products:
    get:
      parameters:
        - $ref: '#/components/parameters/PageNumber'
        - $ref: '#/components/parameters/PageSize'
      responses:
        '200':
          description: Danh sách sản phẩm
```

Một số quy tắc cần nhớ:

- Parameter `path` luôn phải có `required: true`, vì nó là một phần của URL được khai báo.
- Cặp `name` và `in` xác định một parameter. Cùng tên nhưng ở vị trí khác là parameter khác.
- Parameter có thể dùng `schema` cho kiểu dữ liệu đơn giản hoặc `content` cho representation phức tạp theo media type; thông thường query/path/header dùng `schema`.
- `style` và `explode` điều khiển cách serialize mảng hoặc object trong URL/header. Chỉ khai báo khi cần định dạng cụ thể.
- Không dùng Parameter Object để mô tả JSON body. Body thuộc `requestBody`.
- Các header `Accept`, `Content-Type` và `Authorization` được OpenAPI dành cho cơ chế content negotiation hoặc security; khai báo chúng như header parameter thông thường sẽ bị bỏ qua theo đặc tả. Dùng `requestBody.content`/response `content` cho media type và `securitySchemes` cho xác thực.

Trong Spring MVC, `@PathVariable`, `@RequestParam`, `@RequestHeader` và `@CookieValue` giúp springdoc suy luận parameter. Có thể bổ sung `@Parameter` để mô tả ý nghĩa, ví dụ, schema hoặc tính bắt buộc. Với parameter dùng lại ở nhiều operation, component `parameters` giữ một định nghĩa chung.

## 5. RequestBody mô tả nội dung client gửi lên

Request Body Object mô tả payload của request, thường được dùng với POST, PUT hoặc PATCH. Nó có các thuộc tính quan trọng:

- `description`: mô tả nội dung cần gửi.
- `required`: cho biết body có bắt buộc hay không.
- `content`: ánh xạ media type sang schema và metadata tương ứng.

Ví dụ request body JSON:

```yaml
components:
  requestBodies:
    CreateProduct:
      description: Thông tin sản phẩm cần tạo
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateProductRequest'
```

Operation tham chiếu request body đó:

```yaml
paths:
  /products:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateProduct'
      responses:
        '201':
          description: Đã tạo sản phẩm
```

Một request body có thể hỗ trợ nhiều media type:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/ProductXml'
```

Mỗi media type có thể tham chiếu một schema riêng. Khai báo nhiều định dạng trong OpenAPI phải khớp với khả năng thực tế của controller, `consumes` và `HttpMessageConverter`.

### Multipart và form body

Với upload file, request body thường dùng `multipart/form-data`:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required: [file, metadata]
        properties:
          file:
            type: string
            format: binary
          metadata:
            $ref: '#/components/schemas/UploadMetadata'
```

Với form URL encoded, media type là `application/x-www-form-urlencoded`; schema thường là object có các property tương ứng với trường form. Đối với multipart, có thể dùng `encoding` để mô tả media type hoặc header của từng phần khi cần.

Theo thực hành HTTP, request body thường được dùng với POST, PUT và PATCH. OpenAPI có thể biểu diễn request body ở operation khác, nhưng ngữ nghĩa body của GET, HEAD và DELETE không được HTTP định nghĩa thống nhất và một số client/proxy không hỗ trợ. Chỉ thiết kế như vậy khi hệ thống tham gia có thỏa thuận rõ ràng.

## 6. Response mô tả các kết quả server có thể trả

Responses Object là bản đồ giữa status code và Response Object. Mỗi response cần có `description`; nếu có body thì khai báo `content` theo media type và schema.

Ví dụ response tái sử dụng:

```yaml
components:
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
    ValidationError:
      description: Dữ liệu request không hợp lệ
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
```

Operation tham chiếu response:

```yaml
paths:
  /products/{id}:
    get:
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '404':
          $ref: '#/components/responses/NotFound'
        default:
          description: Lỗi không được mô tả riêng
```

Các status code thường gặp:

| Status | Ý nghĩa thường gặp | Body |
|---|---|---|
| `200` | Request thành công | Có thể có representation |
| `201` | Đã tạo tài nguyên | Thường trả representation hoặc header `Location` |
| `202` | Đã chấp nhận xử lý bất đồng bộ | Có thể mô tả thông tin theo dõi tác vụ |
| `204` | Thành công, không có nội dung | Không khai báo `content` |
| `400` | Request không hợp lệ | Thường có mô tả lỗi |
| `401` | Chưa xác thực hoặc thông tin xác thực không hợp lệ | Có thể kèm thông tin lỗi |
| `403` | Không được phép thực hiện hành động | Có thể kèm thông tin lỗi |
| `404` | Không tìm thấy tài nguyên | Có thể kèm thông tin lỗi |
| `409` | Xung đột trạng thái hoặc dữ liệu | Có thể kèm chi tiết xung đột |
| `415` | Media type request không được hỗ trợ | Có thể kèm mô tả lỗi |
| `500` | Lỗi máy chủ ngoài dự kiến | Thường dùng schema lỗi chung |

`default` có thể mô tả response cho các status không được liệt kê riêng. Không nên chỉ khai báo response thành công nếu API thực tế có các lỗi nghiệp vụ quan trọng. Khi response không có body, chẳng hạn `204 No Content`, chỉ mô tả `description` và các header cần thiết, không khai báo một schema body giả.

Response có thể chứa `headers` để mô tả header trả về, ví dụ `Location`, `ETag` hoặc `X-RateLimit-Remaining`. Có thể dùng `links` để mô tả cách lấy operation khác từ dữ liệu trong response.

## 7. SecurityScheme khai báo cơ chế xác thực

`securitySchemes` mô tả cách client cung cấp thông tin xác thực. Khai báo security scheme chỉ định nghĩa cơ chế trong hợp đồng; nó không tự bật Spring Security, không tạo token và không bảo vệ endpoint ở runtime.

Các loại phổ biến:

| Loại | Trường quan trọng | Ví dụ sử dụng |
|---|---|---|
| API key | `type: apiKey`, `in`, `name` | API key trong header `X-API-Key`, query hoặc cookie |
| HTTP Basic | `type: http`, `scheme: basic` | Tên người dùng và mật khẩu qua HTTP Basic |
| HTTP Bearer | `type: http`, `scheme: bearer`, có thể có `bearerFormat` | JWT bearer token trong Authorization header |
| OAuth2 | `type: oauth2`, `flows` | Authorization Code, Client Credentials, Password hoặc Implicit theo cấu hình hỗ trợ |
| OpenID Connect | `type: openIdConnect`, `openIdConnectUrl` | Phát hiện cấu hình OpenID Connect từ URL discovery |

### API key

```yaml
components:
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
```

Client gửi header `X-API-Key` theo yêu cầu của API. Nếu API key nằm trong query hoặc cookie, thay `in` và `name` cho đúng thiết kế thực tế.

### HTTP Bearer và Basic

```yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
    BasicAuth:
      type: http
      scheme: basic
```

Với Bearer, client thường gửi `Authorization: Bearer <token>`. `bearerFormat: JWT` chỉ là gợi ý cho người đọc; OpenAPI không xác minh cấu trúc hoặc chữ ký JWT.

### OAuth2

OAuth2 khai báo một hoặc nhiều flow. Ví dụ Client Credentials:

```yaml
components:
  securitySchemes:
    OAuth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.test/oauth2/token
          scopes:
            products:read: Đọc sản phẩm
            products:write: Tạo và cập nhật sản phẩm
```

`tokenUrl` và scope phải phản ánh authorization server thực tế. Các flow khác có thuộc tính riêng, chẳng hạn `authorizationUrl` cho Authorization Code hoặc Implicit. Chỉ công bố những flow mà hệ thống thật sự hỗ trợ.

### OpenID Connect

```yaml
components:
  securitySchemes:
    OpenID:
      type: openIdConnect
      openIdConnectUrl: https://identity.example.test/.well-known/openid-configuration
```

Đường dẫn discovery phải trỏ tới tài liệu cấu hình OpenID Connect hợp lệ của identity provider.

## 8. Áp dụng security requirement cho API

Khai báo scheme trong `components.securitySchemes` chưa bắt buộc operation dùng scheme đó. Muốn yêu cầu xác thực, cần gắn Security Requirement ở cấp toàn tài liệu hoặc cấp operation.

Yêu cầu Bearer cho toàn bộ API:

```yaml
security:
  - BearerAuth: []
```

Yêu cầu OAuth2 scope cụ thể:

```yaml
security:
  - OAuth2:
      - products:read
```

Chỉ áp dụng cho một operation:

```yaml
paths:
  /products:
    get:
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Danh sách sản phẩm
```

Nếu tài liệu có security ở cấp toàn cục, operation có thể ghi `security: []` để bỏ yêu cầu xác thực được kế thừa:

```yaml
paths:
  /health:
    get:
      security: []
      responses:
        '200':
          description: Dịch vụ đang hoạt động
```

Trong Security Requirement Object, nhiều scheme đặt chung trong một object có nghĩa client phải đáp ứng tất cả scheme trong object đó. Nhiều object trong danh sách biểu thị các lựa chọn thay thế (OR). Ví dụ:

```yaml
security:
  - BearerAuth: []
  - ApiKeyAuth: []
```

Ví dụ trên cho phép dùng Bearer hoặc API key. Nếu cần cả hai cùng lúc:

```yaml
security:
  - BearerAuth: []
    ApiKeyAuth: []
```

Đối với OAuth2, danh sách scope cho biết quyền cần thiết cho operation. Với API key và HTTP authentication, mảng scope thường để rỗng.

## 9. Kết nối components với springdoc-openapi

Springdoc tự tạo nhiều schema từ DTO và các mapping. Khi cần mô tả chi tiết hơn, dùng annotation của Swagger Core. Các annotation thường gặp:

| Annotation | Vị trí sử dụng | Mục đích |
|---|---|---|
| `@Schema` | DTO, field, record component, kiểu dữ liệu | Mô tả schema, property, example, enum và ràng buộc |
| `@Parameter` | Tham số handler | Bổ sung mô tả parameter |
| `@ApiResponse` / `@ApiResponses` | Phương thức controller | Mô tả response theo status code |
| `@Content` | Request body hoặc response | Mô tả media type và schema |
| `@io.swagger.v3.oas.annotations.parameters.RequestBody` | Phương thức hoặc tham số theo mục đích | Tùy chỉnh request body trong OpenAPI |
| `@SecurityScheme` | Lớp cấu hình hoặc vị trí được annotation hỗ trợ | Đăng ký security scheme |
| `@SecurityRequirement` | Lớp hoặc phương thức | Yêu cầu scheme cho API hoặc operation |
| `@OpenAPIDefinition` | Lớp cấu hình | Metadata và security mặc định của tài liệu |

### Mô tả schema bằng @Schema

```java
public record ProductResponse(
    @Schema(description = "Mã sản phẩm", format = "uuid")
    UUID id,

    @Schema(description = "Tên sản phẩm", example = "Bút bi", maxLength = 120)
    String name,

    @Schema(description = "Trạng thái", allowableValues = {"ACTIVE", "ARCHIVED"})
    String status
) {}
```

### Định nghĩa và áp dụng Bearer scheme bằng annotation

```java
@Configuration
@SecurityScheme(
    name = "BearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {
}
```

Áp dụng cho toàn bộ controller:

```java
@RestController
@RequestMapping("/api/products")
@SecurityRequirement(name = "BearerAuth")
class ProductController {
    // Các endpoint yêu cầu Bearer token
}
```

Hoặc chỉ áp dụng cho một operation bằng cách đặt `@SecurityRequirement` trên phương thức. Với endpoint công khai, không gắn requirement hoặc cấu hình rõ `security = {}` tùy cách tổ chức tài liệu.

### Mô tả response và request body

```java
public record ApiError(String code, String message) {}

@Operation(summary = "Lấy sản phẩm theo ID")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy sản phẩm",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm",
        content = @Content(
            mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
@GetMapping("/{id}")
ProductResponse find(@PathVariable UUID id) {
    return productService.findById(id);
}
```

Khi cần mô tả request body rõ hơn, dùng annotation `RequestBody` của package Swagger với tên đầy đủ để tránh nhầm với `org.springframework.web.bind.annotation.RequestBody` của Spring. Annotation OpenAPI chỉ điều khiển tài liệu; việc đọc body, kiểm tra token và phân quyền vẫn do Spring MVC, converter và Spring Security đảm nhiệm.

## 10. Ví dụ components hoàn chỉnh được nhiều operation dùng chung

Ví dụ sau ghép schema, parameter, request body, response và security scheme trong cùng một tài liệu:

```yaml
openapi: 3.1.0
info:
  title: Store API
  version: 1.0.0
paths:
  /products:
    get:
      summary: Liệt kê sản phẩm
      security:
        - BearerAuth: []
      parameters:
        - $ref: '#/components/parameters/PageNumber'
        - $ref: '#/components/parameters/PageSize'
      responses:
        '200':
          description: Danh sách sản phẩm
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Product'
    post:
      summary: Tạo sản phẩm
      security:
        - BearerAuth: []
      requestBody:
        $ref: '#/components/requestBodies/CreateProduct'
      responses:
        '201':
          description: Đã tạo sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '400':
          $ref: '#/components/responses/ValidationError'
  /products/{id}:
    get:
      summary: Xem chi tiết sản phẩm
      security:
        - BearerAuth: []
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '404':
          $ref: '#/components/responses/NotFound'
  /health:
    get:
      summary: Kiểm tra tình trạng dịch vụ
      security: []
      responses:
        '200':
          description: Dịch vụ đang hoạt động
components:
  schemas:
    Product:
      type: object
      required: [id, name, price]
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
          minLength: 1
        price:
          type: number
          minimum: 0
    CreateProductRequest:
      type: object
      required: [name, price]
      properties:
        name:
          type: string
        price:
          type: number
          minimum: 0
    ProblemDetail:
      type: object
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
  parameters:
    PageNumber:
      name: page
      in: query
      schema:
        type: integer
        minimum: 0
        default: 0
    PageSize:
      name: size
      in: query
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
  requestBodies:
    CreateProduct:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateProductRequest'
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
    ValidationError:
      description: Dữ liệu không hợp lệ
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

Điểm quan trọng trong ví dụ là mỗi component có một nhiệm vụ rõ ràng và được dùng bằng `$ref`. Schema `Product` dùng cho response; `CreateProductRequest` dùng cho request; `PageNumber` và `PageSize` dùng chung cho truy vấn phân trang; response lỗi được định nghĩa một lần; `BearerAuth` được gắn vào các operation cần xác thực. Endpoint `/health` công khai bằng `security: []`.

## 11. Kiểm tra components trong tài liệu được sinh ra

Sau khi ứng dụng Spring Boot khởi động, tải tài liệu JSON tại `/v3/api-docs` hoặc YAML tại `/v3/api-docs.yaml`. Trong phần `components`, kiểm tra:

1. **schemas:** tên schema, property, kiểu dữ liệu, `required`, enum, format và các ràng buộc có khớp DTO không?
2. **parameters:** tên, vị trí, kiểu, default và tính bắt buộc có đúng với tham số controller không?
3. **requestBodies:** media type và schema có khớp body mà endpoint thực sự đọc không?
4. **responses:** các status code, mô tả, media type và schema có phản ánh kết quả thật không?
5. **securitySchemes:** loại xác thực, tên header, URL token hoặc scope có khớp cấu hình identity provider không?
6. **references:** mọi `$ref` đều trỏ tới component tồn tại và không có lỗi chính tả hoặc sai chữ hoa/thường không?

Swagger UI là cách thuận tiện để xem và thử operation, nhưng JSON/YAML mới là tài liệu hợp đồng cần kiểm tra. Nếu Swagger UI không hiển thị schema như mong đợi, hãy xác định trước xem dữ liệu trong `/v3/api-docs` đã đúng chưa.

## 12. Lỗi thường gặp khi tổ chức components

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| `$ref` không được phân giải | Sai tên component, sai đường dẫn JSON Pointer hoặc sai chữ hoa/thường | Đối chiếu khóa thực tế trong `components` |
| Component được khai báo nhưng không xuất hiện trong operation | Chưa tham chiếu component từ path, request body, response hoặc security | Thêm `$ref` hoặc Security Requirement phù hợp |
| Response thành công có schema nhưng lỗi không có body | Chưa khai báo `content` cho status lỗi | Tạo schema lỗi và response dùng chung nếu API trả payload lỗi |
| Parameter body bị mô tả như query | Dùng nhầm annotation hoặc đặt sai vị trí dữ liệu | Dùng `@RequestBody` cho body; `@RequestParam` cho query |
| Swagger UI yêu cầu xác thực cho endpoint công khai | Security Requirement toàn cục được kế thừa | Đặt `security: []` cho operation công khai hoặc điều chỉnh phạm vi requirement |
| Tài liệu có Bearer scheme nhưng API vẫn cho gọi không token | Chỉ khai báo tài liệu mà chưa cấu hình bảo mật runtime | Cấu hình Spring Security và kiểm thử quyền truy cập thực tế |
| Schema dùng chung làm thay đổi nhiều endpoint | Nhiều operation tham chiếu cùng component | Đánh giá tác động hợp đồng và cân nhắc schema riêng khi mô hình thực sự khác nhau |
| Trùng schema tên gần giống nhau | Nhiều DTO hoặc generic cùng tên đơn giản | Dùng tên component rõ ràng và kiểm tra quy tắc đặt tên schema của springdoc |

Không nên sao chép component chỉ để tránh một thay đổi có chủ đích. Hãy tái sử dụng khi các operation thực sự có cùng hợp đồng; nếu hai DTO có ý nghĩa nghiệp vụ hoặc vòng đời khác nhau, schema riêng có thể giúp thay đổi độc lập và tránh vô tình làm rộng hợp đồng.

## 13. Quy trình thiết kế và duy trì components

Khi xây dựng hợp đồng API, có thể thực hiện theo trình tự:

1. Xác định các DTO và schema được dùng lặp lại giữa nhiều operation.
2. Định nghĩa parameter dùng chung như phân trang, lọc, request ID hoặc tenant ID.
3. Tạo request body component cho payload được tái sử dụng và khai báo đúng media type.
4. Chuẩn hóa response thành công và lỗi, đặc biệt các response lỗi phổ biến như validation, not found và conflict.
5. Khai báo security scheme tương ứng với cơ chế xác thực thực tế.
6. Gắn component vào operation bằng `$ref` và Security Requirement.
7. Kiểm tra tài liệu JSON/YAML, xác nhận mọi tham chiếu hợp lệ và so sánh hợp đồng giữa các lần phát hành.

Components là nền tảng để tài liệu OpenAPI có cấu trúc, dễ đọc và nhất quán. Kết hợp suy luận từ DTO/controller của Spring Boot với các component dùng chung giúp giảm lặp, nhưng mỗi định nghĩa vẫn cần phản ánh chính xác hành vi HTTP và chính sách bảo mật của ứng dụng.

## 14. Tài liệu tham khảo

- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object): danh sách component có thể tái sử dụng và quy tắc tham chiếu.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): kiểu dữ liệu, thuộc tính, composition và ràng buộc schema.
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object): vị trí, serialization và schema của parameter.
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object): mô tả body và media type của request.
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object): mô tả kết quả HTTP theo status code.
- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object): API key, HTTP authentication, OAuth2 và OpenID Connect.
- [Springdoc OpenAPI](https://springdoc.org/): tích hợp Spring Boot, annotation và cấu hình tài liệu OpenAPI.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): annotation để bổ sung metadata cho schema, response và security.
