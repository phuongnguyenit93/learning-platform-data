# Components và các thành phần dùng lại

Khi một API có nhiều endpoint, nhiều thao tác thường dùng chung một cấu trúc dữ liệu, một tham số, một response lỗi hoặc một cơ chế xác thực. Nếu mô tả lại từng thành phần ở mọi nơi, tài liệu OpenAPI sẽ dài, dễ sai khác và khó bảo trì. **Components** cung cấp nơi định nghĩa các thành phần có thể tái sử dụng; **$ref** cho phép endpoint tham chiếu đến định nghĩa đó.

Trong Spring Boot, springdoc-openapi có thể sinh schema từ DTO, kiểu trả về và annotation của controller. Bạn cũng có thể khai báo các thành phần dùng chung bằng annotation OpenAPI hoặc mô hình Java của thư viện swagger-core. Khi hiểu cách tổ chức Components, bạn có thể tạo hợp đồng nhất quán, giảm lặp và giúp Swagger UI cùng công cụ sinh client hiểu đúng cấu trúc API.

## Mục tiêu

Sau bài học, bạn có thể:

- Hiểu vai trò của đối tượng Components trong tài liệu OpenAPI.
- Phân biệt các nhóm thành phần có thể tái sử dụng và biết khi nào nên dùng từng nhóm.
- Dùng $ref để kết nối endpoint với schema, response, parameter, request body, header và security scheme.
- Tổ chức schema dùng chung, schema lồng nhau và schema đa hình.
- Tạo Components bằng YAML, annotation và cấu hình Java trong Spring Boot.
- Kiểm tra tham chiếu, tránh định nghĩa trùng lặp và duy trì tài liệu dễ mở rộng.

## 1. Components là gì?

Trong OpenAPI, đối tượng Components là một tập hợp các định nghĩa có tên. Mỗi định nghĩa có thể được tham chiếu từ một vị trí khác trong tài liệu bằng khóa $ref. Components không tự tạo endpoint và cũng không tự động áp dụng mọi định nghĩa lên toàn bộ API; một thành phần chỉ có hiệu lực tại nơi có tham chiếu đến nó.

Ví dụ, nhiều thao tác có thể trả về cùng một cấu trúc lỗi. Thay vì khai báo schema lỗi lặp lại, ta định nghĩa một lần trong components.schemas:

~~~yaml
components:
  schemas:
    ApiError:
      type: object
      required:
        - code
        - message
      properties:
        code:
          type: string
          example: PRODUCT_NOT_FOUND
        message:
          type: string
          example: Không tìm thấy sản phẩm
~~~

Một response có thể dùng lại schema đó:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '404':
          description: Không tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
~~~

Đường dẫn $ref ở trên là tham chiếu nội bộ đến một vị trí trong chính tài liệu OpenAPI. Nếu schema thay đổi, mọi nơi tham chiếu đến ApiError đều dùng cùng định nghĩa mới. Đây là lợi ích chính của việc chuẩn hóa thành phần dùng chung.

## 2. Các nhóm thành phần trong Components

OpenAPI 3.0 định nghĩa các nhóm chính sau trong Components:

| Nhóm | Dùng để tái sử dụng | Ví dụ |
|---|---|---|
| schemas | Cấu trúc dữ liệu | Product, PageResponse, ApiError |
| responses | Phản hồi HTTP | NotFound, ValidationError |
| parameters | Tham số path, query, header hoặc cookie | ProductId, PageSize |
| examples | Giá trị ví dụ | NewProduct, InvalidProduct |
| requestBodies | Nội dung request | CreateProductBody |
| headers | Header response | RetryAfter, RateLimitRemaining |
| securitySchemes | Cơ chế xác thực | bearerAuth, oauth2 |
| links | Liên kết từ response đến thao tác khác | GetCreatedProduct |
| callbacks | Các request callback do API phát ra | OrderStatusCallback |

OpenAPI 3.1 bổ sung nhóm pathItems để tái sử dụng Path Item Object. Nếu dự án sinh đặc tả OpenAPI 3.0, không nên đưa pathItems vào Components vì phiên bản đó chưa định nghĩa mục này. Hãy kiểm tra trường openapi ở đầu tài liệu để biết đặc tả dự án đang dùng.

Các thành phần thường gặp nhất trong API Spring Boot là schemas, responses, parameters, requestBodies, headers, examples và securitySchemes. Links, callbacks và pathItems hữu ích hơn trong API có quy trình nhiều bước, webhook hoặc cấu trúc đường dẫn cần dùng chung.

## 3. Cách hoạt động của $ref

Tham chiếu nội bộ thường có dạng:

~~~yaml
$ref: '#/components/schemas/Product'
~~~

Phần sau dấu # là JSON Pointer xác định vị trí trong tài liệu:

- # trỏ đến gốc tài liệu.
- /components đi vào đối tượng Components.
- /schemas đi vào nhóm schema.
- /Product chọn thành phần có tên Product.

Một tham chiếu đến response dùng dạng tương tự:

~~~yaml
$ref: '#/components/responses/NotFound'
~~~

Tên thành phần phân biệt chữ hoa và chữ thường. Để tránh lỗi khi tham chiếu, nên đặt tên dễ hiểu, không chứa dấu cách và ưu tiên các ký tự chữ, số, dấu chấm, gạch ngang hoặc gạch dưới. Nếu khóa có ký tự đặc biệt trong JSON Pointer, cần escape theo quy tắc JSON Pointer: dấu ngã thành ~0 và dấu gạch chéo thành ~1. Trong thực tế, đặt tên đơn giản sẽ dễ đọc và ít lỗi hơn.

### Tham chiếu nội bộ và tham chiếu bên ngoài

Tham chiếu nội bộ như #/components/schemas/Product nằm trong cùng tài liệu, thuận tiện khi xuất một file JSON/YAML độc lập. OpenAPI cũng cho phép tham chiếu đến tài liệu bên ngoài bằng URI, ví dụ:

~~~yaml
$ref: './common-schemas.yaml#/components/schemas/Address'
~~~

Tham chiếu ngoài hữu ích khi nhiều API thực sự chia sẻ một kho hợp đồng. Tuy nhiên, nó tạo thêm phụ thuộc vào vị trí, quyền truy cập và phiên bản của file ngoài. Nếu tải đặc tả về để gửi cho đối tác hoặc sinh client trong môi trường không có mạng nội bộ, cần bảo đảm các tham chiếu ngoài được phân phối cùng hoặc được bundle thành một tài liệu tự chứa.

### Quy tắc khi dùng $ref

- Đích tham chiếu phải tồn tại và đúng loại đối tượng mà vị trí đó yêu cầu.
- Tránh tham chiếu vòng không cần thiết, đặc biệt với các công cụ sinh client có giới hạn xử lý đệ quy.
- Không sao chép các thuộc tính của đối tượng vào cạnh một $ref với kỳ vọng chúng sẽ ghi đè định nghĩa gốc. Để tương thích rộng, hãy giữ đối tượng tham chiếu đơn giản; nếu cần kết hợp schema, dùng allOf, oneOf hoặc anyOf đúng mục đích.
- Kiểm tra tài liệu sau khi bundling hoặc chuyển đổi, vì một công cụ có thể thay đổi cách biểu diễn tham chiếu.

## 4. Tái sử dụng schema trong components.schemas

Schema mô tả cấu trúc dữ liệu của request hoặc response. Ví dụ API sản phẩm có thể dùng các schema sau:

~~~yaml
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
          type: integer
          format: int64
          example: 42
        name:
          type: string
          maxLength: 120
          example: Bàn phím cơ
        price:
          type: number
          format: double
          minimum: 0
          example: 1250000
    CreateProductRequest:
      type: object
      required:
        - name
        - price
      properties:
        name:
          type: string
          maxLength: 120
        price:
          type: number
          minimum: 0
    ApiError:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
        message:
          type: string
~~~

Các endpoint có thể dùng Product cho response đọc dữ liệu, CreateProductRequest cho body tạo mới và ApiError cho lỗi. Việc tách DTO đầu vào và đầu ra giúp hợp đồng phản ánh đúng trách nhiệm của từng thao tác. Ví dụ client không cần gửi id do máy chủ tạo khi tạo sản phẩm.

### Schema lồng nhau và collection

Schema có thể tham chiếu schema khác trong properties hoặc items:

~~~yaml
components:
  schemas:
    Category:
      type: object
      properties:
        id:
          type: integer
        name:
          type: string
    Product:
      type: object
      properties:
        id:
          type: integer
        category:
          $ref: '#/components/schemas/Category'
        tags:
          type: array
          items:
            type: string
    ProductPage:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/Product'
        page:
          type: integer
        totalElements:
          type: integer
          format: int64
~~~

Khi cùng một cấu trúc xuất hiện ở nhiều vị trí, tham chiếu schema giúp định nghĩa một nguồn duy nhất. Với cấu trúc chỉ xuất hiện một lần và rất nhỏ, schema inline vẫn có thể dễ đọc hơn. Không cần tách mọi object thành component; hãy tái sử dụng khi điều đó làm hợp đồng rõ hơn hoặc giảm trùng lặp có ý nghĩa.

### allOf, oneOf và anyOf

OpenAPI hỗ trợ kết hợp schema:

- allOf: một giá trị phải thỏa tất cả schema thành phần. Thường dùng để ghép các nhóm thuộc tính hoặc thể hiện cấu trúc mở rộng.
- oneOf: một giá trị phải khớp đúng một trong các schema được liệt kê.
- anyOf: một giá trị phải khớp ít nhất một schema được liệt kê.

Ví dụ một response có trường chung và phần dữ liệu chuyên biệt:

~~~yaml
components:
  schemas:
    BaseEvent:
      type: object
      required: [eventId, occurredAt, eventType]
      properties:
        eventId:
          type: string
        occurredAt:
          type: string
          format: date-time
        eventType:
          type: string
          enum: [PRODUCT_CREATED, PRODUCT_DELETED]
    ProductCreatedEvent:
      allOf:
        - $ref: '#/components/schemas/BaseEvent'
        - type: object
          required: [productId]
          properties:
            productId:
              type: integer
    ProductDeletedEvent:
      allOf:
        - $ref: '#/components/schemas/BaseEvent'
        - type: object
          required: [productId, reason]
          properties:
            productId:
              type: integer
            reason:
              type: string
~~~

allOf là phép kết hợp các ràng buộc schema, không tự động có nghĩa là kế thừa lớp Java theo mọi quy tắc của ngôn ngữ. Khi dùng oneOf cho nhiều loại sự kiện hoặc kết quả, hãy cân nhắc khai báo discriminator để client nhận diện kiểu dữ liệu:

~~~yaml
components:
  schemas:
    ProductEvent:
      oneOf:
        - $ref: '#/components/schemas/ProductCreatedEvent'
        - $ref: '#/components/schemas/ProductDeletedEvent'
      discriminator:
        propertyName: eventType
        mapping:
          PRODUCT_CREATED: '#/components/schemas/ProductCreatedEvent'
          PRODUCT_DELETED: '#/components/schemas/ProductDeletedEvent'
~~~

Trong các schema cụ thể, eventType phải có giá trị phù hợp với mapping. Nếu không, client có thể không phân biệt được các biến thể. Hãy kiểm tra cách công cụ sinh client xử lý allOf, oneOf, anyOf và discriminator vì mức hỗ trợ có thể khác nhau.

## 5. Tái sử dụng response trong components.responses

Response dùng chung thường là các lỗi phổ biến như không tìm thấy tài nguyên, validation thất bại hoặc vượt giới hạn tần suất:

~~~yaml
components:
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
          examples:
            productMissing:
              summary: Sản phẩm không tồn tại
              value:
                code: PRODUCT_NOT_FOUND
                message: Không tìm thấy sản phẩm
    ValidationError:
      description: Dữ liệu request không hợp lệ
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
    TooManyRequests:
      description: Vượt giới hạn tần suất request
      headers:
        Retry-After:
          $ref: '#/components/headers/RetryAfter'
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
~~~

Endpoint tham chiếu response:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '200':
          description: Tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '404':
          $ref: '#/components/responses/NotFound'
        '429':
          $ref: '#/components/responses/TooManyRequests'
~~~

Mỗi response được tham chiếu cần giữ đúng ngữ nghĩa cho thao tác. Một response NotFound có thể dùng ở nhiều endpoint nếu nội dung thực sự tương đương. Nếu thông điệp, schema hoặc header khác nhau đáng kể, hãy tạo component riêng hoặc dùng schema chung với ví dụ phù hợp.

Response tái sử dụng giúp thay đổi mô tả ở một nơi. Tuy nhiên, nó không khiến Spring tự trả status code đó. Controller, ResponseEntity hoặc exception handler vẫn phải tạo đúng status, header và body như hợp đồng đã công bố.

## 6. Tái sử dụng parameters trong components.parameters

Parameter Object mô tả tham số path, query, header hoặc cookie. Ví dụ tham số mã sản phẩm xuất hiện ở nhiều endpoint:

~~~yaml
components:
  parameters:
    ProductId:
      name: id
      in: path
      required: true
      description: Mã định danh sản phẩm
      schema:
        type: integer
        format: int64
      example: 42
    PageSize:
      name: size
      in: query
      required: false
      description: Số phần tử tối đa trong một trang
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
~~~

Sử dụng tham số đã định nghĩa:

~~~yaml
paths:
  /api/products/{id}:
    get:
      parameters:
        - $ref: '#/components/parameters/ProductId'
      responses:
        '200':
          description: Thành công
~~~

Với tham số nằm trong path, required phải là true. Một parameter được xác định duy nhất bởi cặp name và in trong phạm vi operation/path. Nếu một tham số query có cùng tên với tham số path, chúng vẫn là hai tham số khác nhau.

Không khai báo token xác thực như một header parameter thông thường. Với Authorization bearer token, hãy dùng security scheme để công cụ hiểu đúng semantics xác thực và hỗ trợ nút Authorize trong Swagger UI.

## 7. Tái sử dụng request body trong components.requestBodies

Khi nhiều endpoint nhận cùng một cấu trúc body, định nghĩa một Request Body Object:

~~~yaml
components:
  requestBodies:
    CreateProductBody:
      description: Thông tin tạo sản phẩm
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateProductRequest'
          examples:
            default:
              summary: Sản phẩm mới
              value:
                name: Bàn phím cơ
                price: 1250000
~~~

Tham chiếu trong operation:

~~~yaml
paths:
  /api/products:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateProductBody'
      responses:
        '201':
          description: Đã tạo sản phẩm
~~~

Request body có thể khai báo nhiều media type, ví dụ application/json và multipart/form-data. Khi tái sử dụng, hãy bảo đảm các endpoint nhận cùng định dạng, cùng ý nghĩa trường và cùng quy tắc bắt buộc. Nếu một endpoint cho phép body tùy chọn hoặc có giới hạn khác, nên dùng request body riêng.

## 8. Tái sử dụng examples trong components.examples

Ví dụ có thể được đặt inline ngay trong schema hoặc content. Khi cùng một ví dụ được dùng ở nhiều nơi, hãy định nghĩa trong components.examples:

~~~yaml
components:
  examples:
    ProductCreated:
      summary: Sản phẩm được tạo thành công
      description: Ví dụ response sau khi tạo một sản phẩm mới
      value:
        id: 42
        name: Bàn phím cơ
        price: 1250000
    ProductValidationError:
      summary: Tên sản phẩm bị bỏ trống
      value:
        code: VALIDATION_FAILED
        message: Tên sản phẩm không được để trống
~~~

Tham chiếu ví dụ từ media type:

~~~yaml
content:
  application/json:
    schema:
      $ref: '#/components/schemas/Product'
    examples:
      created:
        $ref: '#/components/examples/ProductCreated'
~~~

Một schema có thể có nhiều ví dụ để thể hiện trường hợp bình thường, biên và lỗi. Ví dụ phải phù hợp schema và không chứa dữ liệu thật của khách hàng, token hoặc thông tin nội bộ. Swagger UI dùng các ví dụ để hỗ trợ người đọc thử request và hiểu response.

## 9. Tái sử dụng headers trong components.headers

Header có thể được định nghĩa riêng khi nhiều response cùng trả một thông tin. Ví dụ:

~~~yaml
components:
  headers:
    RetryAfter:
      description: Số giây hoặc thời điểm HTTP mà client nên chờ trước khi thử lại
      schema:
        type: string
      example: '30'
    RateLimitRemaining:
      description: Số request còn lại trong cửa sổ giới hạn hiện tại
      schema:
        type: integer
      example: 12
~~~

Dùng header component trong response:

~~~yaml
components:
  responses:
    TooManyRequests:
      description: Vượt giới hạn request
      headers:
        Retry-After:
          $ref: '#/components/headers/RetryAfter'
        X-RateLimit-Remaining:
          $ref: '#/components/headers/RateLimitRemaining'
~~~

Header name không phân biệt chữ hoa và chữ thường theo HTTP. Dù vậy, hãy giữ cách viết nhất quán trong tài liệu. Với header chuẩn, mô tả đúng kiểu dữ liệu và semantics; chẳng hạn Retry-After có thể biểu diễn số giây hoặc một HTTP-date, vì vậy ví dụ và mô tả cần phản ánh cách server thực sự gửi.

## 10. Tái sử dụng securitySchemes

Security Scheme Object mô tả cơ chế xác thực mà API hỗ trợ. Các kiểu thường gặp:

- HTTP authentication: Basic hoặc Bearer.
- API key trong header, query hoặc cookie.
- OAuth2 với các flow và scope.
- OpenID Connect.

Ví dụ bearer JWT:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

Khai báo security requirement ở cấp API:

~~~yaml
security:
  - bearerAuth: []
~~~

Hoặc chỉ áp dụng cho operation cần bảo vệ:

~~~yaml
paths:
  /api/products:
    post:
      security:
        - bearerAuth: []
      responses:
        '201':
          description: Đã tạo sản phẩm
~~~

Với HTTP bearer, danh sách scope thường để rỗng. OAuth2 dùng tên scope cụ thể theo flow đã khai báo. Một operation có thể khai báo nhiều security requirement; các object trong danh sách biểu thị các lựa chọn thay thế, trong khi nhiều scheme đặt chung trong một object thường có nghĩa là cần đồng thời các cơ chế đó.

Để cho phép operation công khai ghi đè security áp dụng toàn API, OpenAPI có thể dùng:

~~~yaml
security: []
~~~

Security scheme chỉ mô tả hợp đồng xác thực. Nó không tự cấu hình Spring Security, không xác minh JWT và không cấp quyền cho người dùng. Hãy kiểm tra cấu hình bảo mật thật và bảo đảm danh sách operation công khai/riêng tư khớp với tài liệu.

## 11. Links và callbacks

### Links: chỉ ra thao tác tiếp theo

Link Object mô tả mối quan hệ từ một response đến operation khác. Ví dụ sau khi tạo sản phẩm, response có thể cung cấp id để client gọi thao tác xem chi tiết:

~~~yaml
components:
  links:
    GetCreatedProduct:
      operationId: getProductById
      parameters:
        id: '$response.body#/id'
      description: Lấy sản phẩm vừa được tạo
~~~

Response tham chiếu link:

~~~yaml
paths:
  /api/products:
    post:
      responses:
        '201':
          description: Đã tạo sản phẩm
          links:
            getCreatedProduct:
              $ref: '#/components/links/GetCreatedProduct'
~~~

operationId được tham chiếu phải tồn tại và duy nhất trong tài liệu. Link chỉ mô tả mối quan hệ và gợi ý cách gọi tiếp theo; nó không tự thực thi request hoặc bảo đảm tài nguyên còn tồn tại.

### Callbacks: mô tả request do API gửi đến client

Callback hữu ích khi một API nhận URL callback từ client rồi chủ động gửi thông báo đến URL đó khi một sự kiện xảy ra. Ví dụ, client đăng ký callbackUrl khi tạo đơn hàng:

~~~yaml
paths:
  /api/orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                callbackUrl:
                  type: string
                  format: uri
      callbacks:
        orderStatus:
          '{$request.body#/callbackUrl}':
            post:
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      $ref: '#/components/schemas/OrderStatusEvent'
              responses:
                '200':
                  description: Client đã nhận thông báo
~~~

Callbacks là chiều giao tiếp ngược do API khởi tạo. Khi dùng callback URL do client cung cấp, hệ thống cần xác thực URL đích và kiểm soát rủi ro request giả mạo hoặc truy cập mạng nội bộ. Hợp đồng nên mô tả chữ ký webhook, cách retry, timeout và cơ chế xác nhận nếu hệ thống có hỗ trợ.

Callbacks có thể được đặt trong components.callbacks rồi tham chiếu lại nếu cùng một cấu trúc callback xuất hiện ở nhiều operation. Cấu hình thực tế cần kiểm tra khả năng hỗ trợ của phiên bản OpenAPI và công cụ sinh tài liệu đang dùng.

## 12. PathItems trong OpenAPI 3.1

OpenAPI 3.1 cho phép tái sử dụng Path Item Object thông qua components.pathItems. Điều này có thể hữu ích khi nhiều tài liệu hoặc nhóm API dùng chung một cấu trúc đường dẫn. Ví dụ:

~~~yaml
components:
  pathItems:
    HealthCheck:
      get:
        operationId: healthCheck
        summary: Kiểm tra tình trạng dịch vụ
        responses:
          '200':
            description: Dịch vụ đang hoạt động
~~~

Sau đó tham chiếu tại path:

~~~yaml
paths:
  /health:
    $ref: '#/components/pathItems/HealthCheck'
~~~

Chỉ dùng thành phần này khi tài liệu khai báo OpenAPI 3.1 trở lên và các công cụ trong pipeline hỗ trợ nó. Với OpenAPI 3.0, có thể phải lặp lại Path Item hoặc tổ chức tài liệu bằng cách khác.

## 13. Sinh và tái sử dụng Components từ Spring Boot

springdoc-openapi đọc controller, kiểu dữ liệu Java và annotation để tạo đặc tả. Khi một DTO được dùng trong request hoặc response của nhiều endpoint, schema thường được đưa vào components.schemas và các operation tham chiếu đến schema đó.

Ví dụ DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

@Schema(name = "ProductResponse", description = "Thông tin sản phẩm trả về cho client")
public record ProductResponse(
    @Schema(description = "Mã sản phẩm", example = "42")
    Long id,

    @NotBlank
    @Schema(description = "Tên sản phẩm", example = "Bàn phím cơ")
    String name,

    @Positive
    @Schema(description = "Giá sản phẩm", example = "1250000")
    long price
) {}
~~~

Khi nhiều controller trả về ProductResponse, springdoc có thể dùng chung schema ProductResponse. Tên component có thể được tùy chỉnh bằng @Schema(name = "...") để tài liệu dễ đọc và ổn định hơn. Nếu nhiều lớp Java có cùng tên đơn giản, hãy đặt tên schema rõ ràng để tránh xung đột hoặc tên tự sinh khó hiểu.

### Khai báo response dùng lại bằng annotation

Bạn có thể đăng ký response component bằng cấu hình OpenAPI Java, sau đó tham chiếu từ annotation:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    OpenAPI applicationOpenApi() {
        Components components = new Components()
            .addResponses("NotFound",
                new io.swagger.v3.oas.models.responses.ApiResponse()
                    .description("Không tìm thấy tài nguyên")
                    .content(new Content().addMediaType(
                        "application/json",
                        new MediaType().schema(
                            new Schema<>().$ref("#/components/schemas/ApiError")
                        )
                    ))
            );

        return new OpenAPI().components(components);
    }
}
~~~

Định nghĩa schema ApiError phải được springdoc sinh ra từ DTO được dùng trong API hoặc được khai báo bổ sung trong Components. Không tham chiếu đến một schema chưa tồn tại. Khi dùng phiên bản thư viện khác, kiểm tra import và API model tương ứng.

Trong controller:

~~~java
@GetMapping("/{id}")
@ApiResponse(
    responseCode = "404",
    ref = "#/components/responses/NotFound"
)
public ProductResponse getById(@PathVariable long id) {
    return productService.getById(id);
}
~~~

Tham chiếu annotation giúp operation dùng định nghĩa response đã đăng ký. Cần xác nhận đặc tả được sinh ra có đúng response code và $ref như mong muốn. Đặc biệt, annotation mô tả response không thay thế exception handler xử lý lỗi lúc chạy.

### Tái sử dụng parameter bằng annotation

Với các tham số lặp lại, có thể khai báo Parameter Object trong Components rồi tham chiếu:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.media.Schema;

Components components = new Components()
    .addParameters("ProductId",
        new Parameter()
            .name("id")
            .in("path")
            .required(true)
            .description("Mã sản phẩm")
            .schema(new Schema<>().type("integer").format("int64"))
    );
~~~

Trong operation, annotation OpenAPI có thuộc tính ref để trỏ đến component parameter:

~~~java
@GetMapping("/{id}")
public ProductResponse getById(
    @Parameter(ref = "#/components/parameters/ProductId")
    @PathVariable long id
) {
    return productService.getById(id);
}
~~~

Đây là minh họa cho việc kết hợp cấu hình model và annotation; hãy kiểm tra bản OpenAPI JSON để bảo đảm Springdoc không tạo thêm một parameter trùng lặp.

### Tái sử dụng security scheme bằng annotation

Với HTTP bearer, có thể khai báo scheme bằng annotation:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class ApiSecurityDocumentation {
}
~~~

Áp dụng requirement ở controller hoặc operation cần bảo vệ:

~~~java
@RestController
@RequestMapping("/api/admin")
@SecurityRequirement(name = "bearerAuth")
public class AdminController {
    // Các operation yêu cầu bearer token.
}
~~~

Khai báo scheme tạo thành phần trong components.securitySchemes; requirement mới chỉ ra thao tác nào cần scheme đó. Nếu chỉ khai báo scheme mà không gắn requirement, Swagger UI biết cơ chế xác thực tồn tại nhưng không nhất thiết biết operation nào cần dùng.

### Khi nào cần OpenAPI bean hoặc customizer?

Dùng annotation khi metadata gắn trực tiếp với controller, DTO hoặc operation và dễ hiểu tại nơi khai báo. Dùng bean OpenAPI hoặc customizer khi cần đăng ký nhiều thành phần chung, áp dụng quy tắc theo môi trường, chuẩn hóa metadata hoặc điều chỉnh tài liệu sau khi springdoc sinh ra.

Nếu ứng dụng có nhiều GroupedOpenApi, hãy xác nhận customizer được áp dụng cho đúng nhóm. Một cấu hình chỉ tác động lên tài liệu mặc định có thể không xuất hiện trong đặc tả của nhóm khác. Dùng cơ chế customizer toàn cục hoặc cấu hình riêng cho từng nhóm theo phiên bản springdoc đang dùng.

## 14. Tổ chức Components để dễ bảo trì

Một cấu trúc tốt cần cân bằng giữa tái sử dụng và tính cụ thể của từng endpoint:

1. Đặt tên component theo vai trò nghiệp vụ, ví dụ ProductResponse, CreateProductRequest, ApiError, NotFound và PageSize.
2. Tách request và response khi chúng có vòng đời hoặc trường dữ liệu khác nhau.
3. Dùng chung schema khi cấu trúc và ý nghĩa thật sự giống nhau, không chỉ vì hai object tình cờ có cùng các trường.
4. Dùng chung response khi status, media type, schema, header và ý nghĩa tương đương.
5. Giữ ví dụ sát dữ liệu thực tế, có giá trị biên và không chứa bí mật.
6. Hạn chế schema quá tổng quát khiến client khó biết trường nào có mặt trong từng tình huống.
7. Kiểm tra tham chiếu và tên component khi đổi tên DTO hoặc package.
8. Gắn phiên bản và lưu artifact OpenAPI để biết chính xác component nào đã được phát hành.

### Tránh trùng tên schema

Nếu hai module Java có class Product nhưng mang ý nghĩa khác nhau, không nên để cả hai cùng cạnh tranh một tên component. Hãy đặt tên rõ ràng như CatalogProduct và OrderProduct bằng @Schema(name = "..."), hoặc dùng DTO riêng có tên phản ánh ngữ cảnh. Điều này giúp client generator tạo tên lớp ổn định và tránh ghi đè schema ngoài ý muốn.

### Tránh tái sử dụng quá mức

Một DTO dùng chung cho mọi request và response có thể làm lộ trường nội bộ hoặc khiến thay đổi ở một endpoint ảnh hưởng endpoint khác. Tương tự, một response tên GeneralError với mô tả mơ hồ có thể che mất sự khác nhau giữa lỗi validation, lỗi xác thực và lỗi xung đột. Tái sử dụng nên phản ánh một hợp đồng thực sự chung, không phải chỉ nhằm giảm số dòng YAML.

### Kiểm soát schema đệ quy

Một schema có thể tham chiếu chính nó, ví dụ Category có danh sách children cũng là Category. Điều này hợp lệ cho cấu trúc cây, nhưng một số công cụ sinh client hoặc hiển thị có thể gặp khó khăn với tham chiếu vòng. Hãy giữ độ sâu dữ liệu hợp lý, kiểm tra công cụ tích hợp và cân nhắc DTO dạng cây có giới hạn nếu client không xử lý tốt.

## 15. Kiểm tra Components và tham chiếu

Sau khi ứng dụng chạy, mở endpoint đặc tả, thường là /v3/api-docs, rồi kiểm tra:

- Các component cần thiết có nằm dưới components đúng nhóm hay không.
- Tên component có duy nhất và dễ hiểu không.
- Mọi $ref đều trỏ đến đối tượng tồn tại và đúng loại.
- Các operation tham chiếu đúng response, parameter, request body và schema.
- Security scheme có được khai báo và requirement có được gắn đúng phạm vi.
- Example có khớp schema và không chứa dữ liệu nhạy cảm.
- Không có response 204 khai báo content body.
- Các nhóm tài liệu đều chứa đủ component mà operation của nhóm tham chiếu đến.

### Kiểm tra bằng validator

Có thể tải đặc tả JSON:

~~~bash
curl http://localhost:8080/v3/api-docs -o openapi.json
~~~

Sau đó dùng OpenAPI validator hoặc linter phù hợp với phiên bản đặc tả. Công cụ kiểm tra có thể phát hiện tham chiếu không tồn tại, cấu trúc response sai, schema không hợp lệ hoặc quy tắc đặt tên không thống nhất. Validator không thay thế review nghiệp vụ: một tài liệu hợp lệ về cú pháp vẫn có thể mô tả sai hành vi thật của API.

### Kiểm tra trong Swagger UI

Swagger UI giúp quan sát các nhóm API, schema và response được render. Hãy thử mở phần Schemas, xem response của từng operation và kiểm tra ví dụ request. Nếu component không xuất hiện hoặc tham chiếu không render như mong đợi, đối chiếu trực tiếp JSON để xác định lỗi nằm ở quá trình sinh tài liệu hay giao diện.

### Kiểm tra tương thích khi thay đổi component

Thay đổi component có thể ảnh hưởng nhiều endpoint cùng lúc. Các thay đổi cần đánh giá kỹ:

- Xóa hoặc đổi tên schema, response, parameter hoặc security scheme đang được tham chiếu.
- Đổi kiểu dữ liệu, format, enum hoặc tên property.
- Thêm một trường bắt buộc hoặc siết chặt giới hạn dữ liệu.
- Thay đổi response code, media type hoặc header.
- Thay đổi discriminator hoặc cấu trúc oneOf/allOf.

Trước khi phát hành, so sánh OpenAPI mới với bản đã phát hành để nhận diện thay đổi có thể phá vỡ client. Nếu thay đổi không tương thích, cần có kế hoạch versioning, thời gian chuyển đổi và thông báo cho người tích hợp.

## 16. Bài thực hành tổng hợp

Hãy xây dựng một API quản lý sản phẩm có thao tác xem, tạo và xóa. Thực hiện:

1. Tạo các schema Product, CreateProductRequest, ProductPage và ApiError.
2. Dùng $ref để tái sử dụng schema trong request và response.
3. Tạo response components NotFound, ValidationError và TooManyRequests.
4. Tạo parameter component ProductId và PageSize.
5. Tạo requestBody component CreateProductBody.
6. Định nghĩa example ProductCreated và ProductValidationError.
7. Định nghĩa header component RetryAfter và dùng trong response 429.
8. Khai báo security scheme bearerAuth và gắn requirement cho endpoint cần xác thực.
9. Thêm một link từ response tạo sản phẩm đến thao tác lấy sản phẩm theo id.
10. Sinh đặc tả bằng springdoc-openapi, mở Swagger UI và chạy validator.
11. Đổi tên một schema đang được dùng ở nhiều nơi, cập nhật tham chiếu và so sánh đặc tả trước/sau.

### Tiêu chí hoàn thành

- [ ] Các nhóm component được đặt tên rõ ràng và nằm đúng vị trí trong components.
- [ ] Những schema, response, parameter và request body dùng chung được tham chiếu bằng $ref.
- [ ] Không có tham chiếu nội bộ bị thiếu hoặc sai loại đối tượng.
- [ ] Schema request và response phản ánh đúng DTO và validation.
- [ ] Security scheme và security requirement thể hiện đúng phạm vi xác thực.
- [ ] Header và example khớp với phản hồi HTTP thực tế.
- [ ] Swagger UI hiển thị được các schema và response dùng chung.
- [ ] OpenAPI validator xác nhận tài liệu hợp lệ.
- [ ] Thay đổi component được rà soát ảnh hưởng và lưu cùng phiên bản hợp đồng.

## Tiếp tục học

Sau bài này, hãy kết hợp Components với cấu trúc Paths, Operations, Parameters và Responses; tìm hiểu sâu hơn về schema composition, security, callbacks và customizer của springdoc-openapi. Mỗi lần thay đổi DTO hoặc annotation, hãy xem lại components và các $ref được sinh ra, sau đó kiểm tra tài liệu cùng hành vi HTTP để giữ hợp đồng nhất quán.
