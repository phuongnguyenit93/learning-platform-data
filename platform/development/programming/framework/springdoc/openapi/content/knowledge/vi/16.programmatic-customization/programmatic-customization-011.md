# Giữ tên, operationId và tham chiếu ổn định khi sửa mô hình

Springdoc-openapi tạo hợp đồng OpenAPI từ controller, DTO, annotation Spring và metadata Jackson. Khi refactor mã Java, đổi tên class hoặc tổ chức lại package, tài liệu được sinh ra có thể thay đổi theo dù hành vi HTTP không đổi. Ngược lại, một thay đổi nhỏ trong tên property JSON, đường dẫn hoặc `operationId` có thể ảnh hưởng trực tiếp tới client và công cụ sinh mã. Vì vậy, cần phân biệt tên nội bộ trong mã nguồn với tên công khai của API, đồng thời chủ động giữ ổn định `operationId`, schema component và các tham chiếu `$ref`.

## 1. Tên nội bộ và tên công khai thuộc hai hợp đồng khác nhau

Một endpoint có nhiều tên ở các lớp khác nhau:

| Thành phần | Ví dụ | Nơi ảnh hưởng |
|---|---|---|
| Tên method Java | `findProductById` | Mã nguồn; có thể ảnh hưởng operationId mặc định nếu không khai báo rõ |
| Tên class DTO | `ProductView` | Mã nguồn; có thể ảnh hưởng tên schema component mặc định |
| Tên property Java | `productCode` | Mã nguồn; có thể được Jackson chuyển thành tên JSON khác |
| Tên property JSON | `product_code` | Payload HTTP và OpenAPI schema |
| Path template | `/api/products/{productId}` | URL công khai và operation OpenAPI |
| `operationId` | `products_getById` | Định danh operation trong OpenAPI, client generator và liên kết operation |
| Tên schema component | `Product` | `components.schemas` và các `$ref` trỏ tới schema |
| Tên response component | `NotFound` | `components.responses` và các `$ref` response |

Không nên để việc đổi tên class hoặc method Java vô tình làm thay đổi các định danh mà client đang sử dụng. Một quy ước tốt là xem tên URL, tên JSON, operationId và component name như một phần của hợp đồng API; tên Java có thể thay đổi khi cần nhưng phải giữ ánh xạ công khai ổn định.

## 2. Vì sao operationId cần ổn định?

Mỗi operation trong OpenAPI có thể có `operationId` để định danh duy nhất. Công cụ sinh client thường dùng giá trị này để tạo tên hàm. Một số công cụ liên kết operation hoặc tạo SDK cũng dựa vào nó.

Ví dụ operation:

```yaml
paths:
  /api/products/{productId}:
    get:
      operationId: products_getById
      summary: Lấy sản phẩm theo ID
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Tìm thấy sản phẩm
```

Nếu bỏ `operationId`, springdoc có thể tạo giá trị dựa trên mapping hoặc tên method. Khi đổi tên method từ `findById` thành `getById`, operationId mặc định có thể thay đổi theo cách suy luận của phiên bản và cấu hình. Client được sinh lại có thể đổi tên method, khiến mã nguồn ứng dụng tiêu thụ SDK không còn biên dịch dù URL và JSON vẫn giữ nguyên.

Đặt operationId tường minh bằng `@Operation`:

```java
@Operation(
    operationId = "products_getById",
    summary = "Lấy sản phẩm theo ID"
)
@GetMapping("/{productId}")
ProductResponse getById(
    @PathVariable("productId") UUID productId
) {
    return productService.getById(productId);
}
```

Sau đó có thể đổi tên method Java, chuyển package hoặc tách service mà vẫn giữ operationId `products_getById`. Hãy chọn quy tắc đặt tên dễ dự đoán, duy nhất trong một tài liệu OpenAPI và không phụ thuộc tên class nội bộ.

### Quy tắc đặt operationId

- Dùng một quy ước nhất quán, chẳng hạn `products_getById`, `products_create`, `products_search`.
- Mỗi operation trong cùng một OpenAPI document phải có operationId duy nhất.
- Tránh tên quá chung như `get`, `create` hoặc `search` khi API có nhiều nhóm tài nguyên.
- Không đổi operationId chỉ vì đổi tên method Java hoặc tái cấu trúc package.
- Nếu thật sự cần đổi operationId, coi đó là thay đổi ảnh hưởng tới người dùng SDK và thông báo trong release notes.

OperationId không thay thế HTTP method hoặc path. Client vẫn gọi endpoint theo URL và method; operationId là định danh trong tài liệu, nhưng có thể trở thành API bề mặt của SDK được sinh ra.

## 3. Giữ tên schema component khi đổi tên DTO Java

Springdoc thường tạo component schema dựa trên kiểu Java. Nếu class `ProductResponse` được đổi thành `ProductView`, tên component sinh ra có thể đổi theo. Khi đó các tham chiếu như `#/components/schemas/ProductResponse` có thể biến mất, ảnh hưởng tài liệu khác, client generator hoặc công cụ kiểm tra hợp đồng.

Dùng `@Schema(name = ...)` để đặt tên component công khai ổn định:

```java
@Schema(
    name = "Product",
    description = "Thông tin sản phẩm được công bố qua API"
)
public record ProductResponse(
    UUID id,
    String name,
    BigDecimal price
) {}
```

Khi refactor tên Java:

```java
@Schema(
    name = "Product",
    description = "Thông tin sản phẩm được công bố qua API"
)
public record ProductView(
    UUID id,
    String name,
    BigDecimal price
) {}
```

Nếu chữ ký controller chuyển từ `ProductResponse` sang `ProductView`, schema vẫn có thể được công bố dưới tên `Product` vì tên component đã được khai báo tường minh. Cần xác minh kết quả thực tế trong `components.schemas`, vì các kiểu generic, schema wrapper, model converter và phiên bản springdoc có thể ảnh hưởng cách đặt tên.

### Tên component phải duy nhất

Hai class ở package khác nhau có thể cùng tên đơn giản, ví dụ `admin.ProductResponse` và `catalog.ProductResponse`. Nếu cả hai được công bố trong cùng tài liệu, tên component có thể bị thêm hậu tố hoặc điều chỉnh để tránh xung đột. Đừng dựa vào tên được tự động thêm hậu tố làm định danh lâu dài.

Hãy đặt tên rõ ràng và duy nhất:

```java
@Schema(name = "AdminProduct")
public record AdminProductResponse(Long id, String name, String internalStatus) {}

@Schema(name = "CatalogProduct")
public record CatalogProductResponse(Long id, String name, BigDecimal price) {}
```

Tên component nên mô tả khái niệm API, không nhất thiết phải trùng tên class hoặc bảng database.

## 4. Giữ tên property JSON độc lập với tên field Java

Tên property trong schema cần khớp với key JSON mà client thực sự gửi hoặc nhận. Nếu đổi tên field Java để phù hợp code style, có thể giữ tên wire format bằng `@JsonProperty`.

```java
public record ProductResponse(
    @JsonProperty("product_code") String productCode,
    @JsonProperty("display_name") String displayName
) {}
```

Payload công khai:

```json
{
  "product_code": "P-001",
  "display_name": "Bút bi"
}
```

Nếu refactor field Java từ `productCode` thành `sku`, giữ tên JSON bằng annotation:

```java
public record ProductResponse(
    @JsonProperty("product_code") String sku,
    @JsonProperty("display_name") String displayName
) {}
```

Client tiếp tục gửi/nhận `product_code`; thay đổi chỉ nằm trong mã Java. Springdoc thường sử dụng metadata Jackson để tạo property name, nhưng vẫn cần kiểm tra schema sau khi đổi naming strategy, mix-in hoặc custom serializer.

### Phân biệt @JsonProperty và @Schema(name)

- `@JsonProperty("product_code")` điều khiển tên property trong JSON runtime và cung cấp metadata cho công cụ introspection.
- `@Schema(name = "Product")` trên class đặt tên schema component.
- `@Schema` trên property chủ yếu mô tả kiểu, description, example, access mode và các ràng buộc; không dùng nó thay thế Jackson khi cần đổi tên key JSON runtime.

Nếu tài liệu hiển thị tên đúng nhưng JSON runtime vẫn khác, kiểm tra Jackson `ObjectMapper` và converter thực tế. Nếu JSON đúng nhưng schema sai, kiểm tra springdoc model converter và metadata annotation.

## 5. Giữ ổn định path và tên path parameter

Path là một phần trực tiếp của API. Đổi `/api/products/{id}` thành `/api/products/{productId}` có thể ảnh hưởng client, gateway, cache rule, policy và tài liệu tham chiếu, dù giá trị được truyền vẫn là cùng một UUID.

Để giữ path parameter nhất quán, đặt tên tường minh ở cả mapping và tham số:

```java
@GetMapping("/{productId}")
ProductResponse getById(
    @PathVariable("productId") UUID id
) {
    return productService.getById(id);
}
```

Tên biến Java là `id`, còn tên path parameter công khai vẫn là `productId`. Khi refactor tên biến Java thành `productKey`, mapping và annotation vẫn giữ `productId`:

```java
@GetMapping("/{productId}")
ProductResponse getById(
    @PathVariable("productId") UUID productKey
) {
    return productService.getById(productKey);
}
```

Tương tự, khai báo rõ tên query parameter và header:

```java
@GetMapping
List<ProductResponse> search(
    @RequestParam(name = "keyword", required = false) String term,
    @RequestHeader(name = "X-Request-Id", required = false) String requestId
) {
    return productService.search(term, requestId);
}
```

Đổi tên biến Java không làm thay đổi tên query `keyword` hoặc header `X-Request-Id`. Tránh phụ thuộc vào việc build có giữ lại tên parameter Java hay không; khai báo tên HTTP tường minh giúp tài liệu và runtime ổn định hơn.

## 6. Giữ tên parameter và response component dùng chung

Khi nhiều operation dùng cùng query parameter, header hoặc response, có thể định nghĩa component và tham chiếu bằng `$ref`. Tên component trở thành định danh mà tài liệu khác có thể phụ thuộc.

Ví dụ:

```yaml
components:
  parameters:
    PageSize:
      name: size
      in: query
      description: Số phần tử tối đa trong một trang
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
  responses:
    ProductNotFound:
      description: Không tìm thấy sản phẩm
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
```

Operation tham chiếu component:

```yaml
paths:
  /api/products/{productId}:
    get:
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - $ref: '#/components/parameters/PageSize'
      responses:
        '404':
          $ref: '#/components/responses/ProductNotFound'
```

Nếu đổi tên component `ProductNotFound` thành `NotFound`, mọi `$ref` trỏ tới tên cũ phải được cập nhật. Tài liệu ngoài hoặc pipeline khác cũng có thể đang tham chiếu tên đó. Khi cần giữ tương thích, có thể duy trì tên cũ như một alias component trỏ tới định nghĩa mới:

```yaml
components:
  responses:
    ProductNotFound:
      $ref: '#/components/responses/NotFound'
    NotFound:
      description: Không tìm thấy tài nguyên
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
```

Chỉ dùng alias khi cấu trúc và ngữ nghĩa tương thích. Không tạo chuỗi `$ref` vòng lặp hoặc alias trỏ ngược về chính nó.

## 7. Giữ ổn định schema $ref khi cấu trúc Java được tái tổ chức

Schema được tham chiếu thường xuất hiện dưới dạng:

```yaml
schema:
  $ref: '#/components/schemas/Product'
```

Nếu đổi package hoặc tên Java class nhưng component name được giữ, đường dẫn tham chiếu vẫn có thể ổn định. Có thể dùng `@Schema(name = "Product")` trên DTO để kiểm soát tên component. Tên class mới không nên tự động trở thành tên công khai nếu mục tiêu là giữ hợp đồng cũ.

Khi cần chuyển một schema sang mô hình mới, có thể giữ component cũ làm alias:

```yaml
components:
  schemas:
    ProductResponse:
      $ref: '#/components/schemas/Product'
    Product:
      type: object
      required: [id, name]
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
```

Các operation cũ hoặc tài liệu bên ngoài tiếp tục tham chiếu `ProductResponse`; operation mới có thể tham chiếu `Product`. Cần kiểm tra công cụ OpenAPI mà hệ thống sử dụng có xử lý schema `$ref` alias đúng cách không.

### Không đổi component name chỉ để phản ánh refactor nội bộ

Ví dụ, đổi `ProductResponse` thành `CatalogItemView` có thể là thay đổi tên Java thuần túy. Nếu payload không đổi, schema name không cần đổi. Ngược lại, nếu mô hình công khai thực sự có ngữ nghĩa khác, có thể tạo component mới và chuyển đổi có kế hoạch thay vì âm thầm đổi định danh cũ.

## 8. operationId còn được tham chiếu ở đâu?

`operationId` không chỉ dùng để sinh tên hàm client. OpenAPI Link Object có thể tham chiếu operation bằng `operationId`, và các công cụ có thể dùng nó để liên kết workflow hoặc tạo tài liệu.

Ví dụ Link Object:

```yaml
paths:
  /api/orders:
    post:
      operationId: orders_create
      responses:
        '201':
          description: Đơn hàng đã được tạo
          links:
            GetCreatedOrder:
              operationId: orders_getById
              parameters:
                orderId: '$response.body#/id'
  /api/orders/{orderId}:
    get:
      operationId: orders_getById
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Chi tiết đơn hàng
```

Nếu đổi `orders_getById`, Link Object trỏ tới operationId cũ sẽ không còn đúng. Vì vậy, khi đổi operationId, cần tìm và cập nhật các liên kết, callback, tài liệu tham chiếu và cấu hình client generator có liên quan.

## 9. Khai báo tên ổn định bằng annotation trong Springdoc

Một controller có thể đặt tên công khai cho operation, path parameter, response và schema:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @Operation(
        operationId = "products_getById",
        summary = "Lấy sản phẩm theo ID"
    )
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
            ref = "#/components/responses/ProductNotFound"
        )
    })
    @GetMapping("/{productId}")
    ProductResponse getById(
        @Parameter(description = "UUID của sản phẩm")
        @PathVariable("productId") UUID id
    ) {
        return productService.getById(id);
    }
}

@Schema(name = "Product", description = "Thông tin sản phẩm công khai")
public record ProductResponse(
    UUID id,
    @JsonProperty("product_code") String productCode,
    String name
) {}
```

Các định danh chính được khai báo tường minh:

- `operationId = "products_getById"` giữ định danh operation khi method Java đổi tên.
- `@GetMapping("/{productId}")` và `@PathVariable("productId")` giữ tên path công khai.
- `@Schema(name = "Product")` giữ tên schema component.
- `@JsonProperty("product_code")` giữ tên property trong JSON.
- `@ApiResponse(ref = ...)` dùng response component đã đặt tên ổn định.

Annotation chỉ mô tả hoặc ánh xạ hợp đồng. Response component được tham chiếu phải thực sự tồn tại trong OpenAPI cuối cùng; có thể được định nghĩa bằng `@ApiResponse` ở vị trí cấu hình phù hợp hoặc qua customizer. Luôn kiểm tra `$ref` sau khi springdoc tổng hợp tài liệu.

## 10. Dùng OpenApiCustomizer để giữ định danh theo quy tắc tập trung

Với hệ thống lớn, có thể dùng `OpenApiCustomizer` để chuẩn hóa metadata sau khi springdoc tạo OpenAPI model. Cách này hữu ích khi một số controller cũ chưa thể sửa annotation ngay hoặc khi cần áp dụng quy ước thống nhất cho một nhóm endpoint.

Ví dụ đặt operationId cho một operation theo path và HTTP method:

```java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiNamingConfiguration {

    @Bean
    OpenApiCustomizer stableProductOperationId() {
        return openApi -> {
            var pathItem = openApi.getPaths().get("/api/products/{productId}");
            if (pathItem != null && pathItem.getGet() != null) {
                pathItem.getGet().setOperationId("products_getById");
            }
        };
    }
}
```

Đây là ví dụ customizer cho tài liệu OpenAPI tương ứng. Nếu dùng nhiều `GroupedOpenApi`, hãy đăng ký customizer vào đúng group hoặc dùng cơ chế global phù hợp với phiên bản springdoc để áp dụng cho mọi group. Đường dẫn trong customizer phải khớp path đã được đưa vào OpenAPI, kể cả context path hoặc prefix nếu chúng được công bố.

Không nên tạo operationId bằng cách ghép tên method Java trong customizer nếu mục tiêu là giữ ổn định qua refactor. Hãy dùng bảng ánh xạ tường minh từ path/method sang ID công khai hoặc đặt `@Operation(operationId = ...)` trực tiếp tại controller.

### Tùy chỉnh schema component name

Tên component nên được đặt ở DTO bằng `@Schema(name = "...")` khi có thể. Nếu phải thay đổi model sau khi tạo OpenAPI, customizer có thể chỉnh `components.schemas`, nhưng cần cập nhật mọi `$ref` tương ứng. Chỉ đổi tên key trong `components.schemas` mà không sửa các tham chiếu sẽ làm tài liệu không hợp lệ.

Ví dụ logic khi đổi tên component trong model OpenAPI cần thực hiện đồng bộ:

1. Tạo hoặc chuyển schema sang tên mới.
2. Cập nhật mọi `$ref` trong request body, response, property lồng nhau và các component khác.
3. Giữ alias component cũ nếu cần tương thích.
4. Kiểm tra không còn tham chiếu tới key đã xóa.

Với cấu trúc nhiều schema lồng nhau, không nên viết một customizer đổi chuỗi `$ref` bằng thay thế văn bản đơn giản. Hãy duyệt model OpenAPI có kiểu hoặc dùng một bước xử lý tài liệu có kiểm tra tham chiếu.

## 11. Phân biệt đổi tên nội bộ với thay đổi hợp đồng

Không phải mọi thay đổi mã Java đều là breaking change. Bảng sau giúp phân loại:

| Thay đổi | Có thể giữ hợp đồng ổn định bằng cách nào? | Tác động nếu không kiểm soát |
|---|---|---|
| Đổi tên method controller | Giữ `@Operation(operationId = ...)` | SDK có thể đổi tên hàm |
| Đổi package hoặc tên DTO | Giữ `@Schema(name = ...)` | Component schema có thể đổi tên |
| Đổi tên field Java | Giữ `@JsonProperty` | JSON property và schema có thể đổi |
| Đổi tên biến tham số | Ghi rõ `@PathVariable("...")`, `@RequestParam(name = "...")` | Tên parameter có thể thay đổi theo metadata build/introspection |
| Đổi tên path placeholder | Giữ URL và tên parameter công khai | Client phải sửa URL template/parameter |
| Đổi `operationId` | Giữ ID hoặc cập nhật mọi consumer | SDK, link và tool tham chiếu có thể hỏng |
| Đổi schema component key | Giữ tên bằng `@Schema(name)` hoặc alias `$ref` | Tham chiếu tài liệu cũ không còn phân giải |
| Đổi JSON field name | Giữ tên wire format hoặc phát hành chuyển tiếp | Client không đọc/ghi được property cũ |
| Đổi kiểu dữ liệu hoặc format | Giữ representation cũ hoặc phát hành phiên bản mới | Client deserialize thất bại hoặc xử lý sai |

Một số thay đổi có thể được xem là additive nhưng vẫn cần đánh giá thực tế. Ví dụ thêm property response tùy chọn thường tương thích với client bỏ qua field lạ, nhưng có thể làm hỏng client cấu hình strict deserialization. Thêm property request bắt buộc có thể phá các client cũ chưa gửi field đó. Compatibility cần được đánh giá theo cả OpenAPI diff, hành vi runtime và chính sách của client.

## 12. Chiến lược chuyển đổi khi phải đổi tên property JSON

Đổi tên property công khai là thay đổi hợp đồng. Nếu cần chuyển từ `productCode` sang `product_code`, hãy lập kế hoạch theo chiều request và response riêng.

### Request: chấp nhận tên cũ trong giai đoạn chuyển tiếp

Jackson `@JsonAlias` có thể cho phép deserialize nhiều tên input trong khi serialize ra một tên chuẩn:

```java
public record UpdateProductRequest(
    @JsonProperty("product_code")
    @JsonAlias("productCode")
    String productCode
) {}
```

Server nhận được cả `product_code` và `productCode`, nhưng output theo tên chuẩn `product_code`. `@JsonAlias` không tạo hai property trong JSON response và không nhất thiết làm springdoc công bố alias cũ thành một property riêng. Nếu muốn client biết alias cũ vẫn được hỗ trợ, hãy ghi rõ trong description hoặc tài liệu migration.

### Response: duy trì field cũ trong thời gian chuyển tiếp

`@JsonAlias` không giữ hai tên trong response. Nếu client cũ vẫn cần đọc `productCode`, có thể tạm thời trả cả field cũ và field mới, đánh dấu field cũ deprecated trong OpenAPI:

```java
@Schema(name = "ProductResponse")
public record ProductResponse(
    @Schema(description = "Mã sản phẩm theo tên chuẩn")
    @JsonProperty("product_code") String productCode,

    @Deprecated
    @Schema(deprecated = true, description = "Dùng product_code; sẽ ngừng hỗ trợ theo lịch migration")
    @JsonProperty("productCode") String legacyProductCode
) {}
```

Trong thực tế, cần bảo đảm hai giá trị luôn đồng nhất và thông báo mốc ngừng hỗ trợ. Sau giai đoạn chuyển tiếp, có thể loại field cũ trong phiên bản API mới hoặc theo chính sách breaking change của hệ thống.

Không thêm hai field cùng tên Java hoặc dùng Jackson mix-in một cách mơ hồ để tạo hai wire name. Hãy dùng DTO response chuyển tiếp có mapping rõ ràng.

## 13. Giữ ổn định operation và component trong API có nhiều group

Springdoc có thể tạo nhiều tài liệu bằng `GroupedOpenApi`, chẳng hạn `public`, `admin` hoặc `internal`. Mỗi group là một OpenAPI document riêng với `paths` và `components` riêng.

Điều cần chú ý:

- OperationId phải duy nhất trong từng document; tốt nhất dùng quy tắc đặt tên duy nhất trên toàn hệ thống để tránh xung đột khi ghép tài liệu.
- Component chỉ có hiệu lực trong document chứa nó. Một `$ref` nội bộ của group `admin` không tự trỏ sang component trong group `public`.
- Customizer chỉ đăng ký cho một group có thể không tác động tới group khác.
- Khi thêm endpoint vào group hoặc chuyển endpoint giữa các group, kiểm tra các tham chiếu và schema được tạo trong document đích.

Ví dụ đăng ký customizer theo group (API builder tùy phiên bản springdoc):

```java
@Bean
GroupedOpenApi publicApi(OpenApiCustomizer publicNamingCustomizer) {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/**")
        .addOpenApiCustomizer(publicNamingCustomizer)
        .build();
}
```

Nếu cùng customizer cần áp dụng toàn bộ group, xem xét `GlobalOpenApiCustomizer` theo phiên bản springdoc đang dùng. Đừng đăng ký cả customizer cục bộ lẫn global nếu chúng cùng sửa một operation mà không có quy tắc rõ ràng.

## 14. Kiểm tra operationId, schema name và $ref sau khi refactor

Sau khi ứng dụng khởi động, tải `/v3/api-docs` hoặc endpoint tài liệu của group tương ứng. Kiểm tra các định danh công khai:

1. `paths` và HTTP method không đổi ngoài chủ đích.
2. Mỗi operation có `operationId` tường minh và duy nhất.
3. `components.schemas` có key ổn định, không bị thêm hậu tố ngoài dự kiến.
4. Property name khớp JSON thực tế, bao gồm naming strategy và `@JsonProperty`.
5. `components.parameters`, `components.responses` và `components.requestBodies` giữ tên ổn định nếu được tái sử dụng.
6. Mọi `$ref` đều phân giải được trong cùng document hoặc tới tài liệu ngoài hợp lệ.
7. Link Object và cấu hình khác tham chiếu operationId mới nhất.
8. Swagger UI hiển thị đúng tên operation, schema và response.

Có thể kiểm tra operationId bằng cách duyệt các path item trong OpenAPI JSON. Với CI, nên lưu snapshot hoặc sinh tài liệu chuẩn rồi so sánh diff với phiên bản trước. Một diff có thay đổi operationId hoặc component key cần được review giống như thay đổi schema.

Ví dụ cấu trúc kiểm tra kỳ vọng:

```yaml
paths:
  /api/products/{productId}:
    get:
      operationId: products_getById
      parameters:
        - name: productId
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
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
          format: uuid
        product_code:
          type: string
```

## 15. Kiểm thử thay đổi bằng OpenAPI diff và client generation

Để biết một refactor có làm đổi hợp đồng không, nên so sánh tài liệu OpenAPI trước và sau thay đổi. Việc so sánh cần chú ý:

- Operation mới/mất đi hoặc path/method thay đổi.
- operationId đổi hoặc bị trùng.
- Schema component đổi tên hoặc bị xóa.
- `$ref` không còn phân giải.
- Property bị đổi tên, đổi kiểu, đổi required hoặc enum.
- Response status, media type hoặc schema thay đổi.
- Security requirement hoặc parameter thay đổi.

Một quy trình CI có thể:

1. Khởi động ứng dụng hoặc tạo OpenAPI document từ build.
2. Xuất `/v3/api-docs` thành artifact JSON/YAML.
3. So sánh với tài liệu của nhánh chính hoặc release gần nhất bằng công cụ OpenAPI diff.
4. Phân loại breaking change và additive change theo chính sách dự án.
5. Sinh thử client SDK để phát hiện thay đổi tên method/model do operationId hoặc schema key.
6. Yêu cầu review khi thay đổi định danh công khai hoặc wire format.

Sinh client là một phép kiểm tra hữu ích nhưng không thay thế contract test. Một operationId đổi có thể làm SDK thay đổi dù request HTTP vẫn hoạt động; ngược lại, SDK sinh thành công không chứng minh server runtime trả đúng schema.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đổi tên method Java làm tên hàm SDK thay đổi | OperationId được suy luận thay vì khai báo rõ | Đặt `@Operation(operationId = ...)` tường minh |
| Đổi tên DTO làm `$ref` thay đổi | Component name lấy từ class name | Dùng `@Schema(name = "...")` ổn định |
| Component name bị thêm hậu tố | Nhiều class trùng tên trong cùng document | Đặt schema name duy nhất theo khái niệm API |
| Đổi tên field làm JSON key thay đổi | Không có `@JsonProperty` cố định | Giữ wire name bằng `@JsonProperty` và kiểm tra payload |
| Path parameter đổi tên sau refactor | Mapping/annotation phụ thuộc tên biến | Khai báo path placeholder và `@PathVariable("...")` tường minh |
| `$ref` bị lỗi sau khi đổi component | Chỉ đổi key, chưa cập nhật mọi tham chiếu | Cập nhật toàn bộ ref hoặc duy trì alias cũ |
| Link response không mở được operation | Link Object vẫn dùng operationId cũ | Tìm và cập nhật các tham chiếu operationId |
| Group public đúng nhưng group admin sai | Customizer chỉ áp dụng cho một document | Đăng ký customizer đúng group hoặc global |
| Schema OpenAPI đúng nhưng JSON runtime sai | Annotation tài liệu không thay đổi Jackson serialization | Kiểm tra ObjectMapper và HTTP response thực tế |
| JSON đúng nhưng schema sai | Model converter hoặc customizer không phản ánh metadata | Kiểm tra `/v3/api-docs` và cấu hình springdoc |

## 17. Quy trình refactor mà không làm đổi hợp đồng ngoài ý muốn

Khi đổi tên class, method hoặc property trong dự án Spring Boot, thực hiện theo thứ tự:

1. Chụp lại OpenAPI JSON/YAML hiện tại làm mốc so sánh.
2. Ghi nhận các định danh công khai: path, HTTP method, operationId, parameter name, schema component và `$ref`.
3. Đổi tên mã Java hoặc tổ chức lại package.
4. Giữ operationId bằng `@Operation(operationId = ...)`.
5. Giữ schema component bằng `@Schema(name = ...)`.
6. Giữ JSON property bằng `@JsonProperty` và tên HTTP parameter bằng `@PathVariable`, `@RequestParam`, `@RequestHeader` có tên tường minh.
7. Giữ hoặc tạo alias cho component `$ref` nếu có consumer tài liệu phụ thuộc tên cũ.
8. Kiểm tra Link Object và các tham chiếu operationId.
9. So sánh OpenAPI trước/sau, sinh client thử và chạy contract test.
10. Chỉ công bố thay đổi breaking khi đã có kế hoạch migration/versioning và thông báo cho consumer.

Mục tiêu của việc giữ định danh không phải đóng băng mã nguồn. Mã Java có thể được tái cấu trúc thường xuyên, miễn là các tên công khai mà client phụ thuộc vẫn được kiểm soát. Đặt tên rõ ràng trong annotation, dùng DTO có schema ổn định và kiểm tra diff OpenAPI giúp refactor an toàn hơn mà không làm SDK hoặc tài liệu tích hợp thay đổi ngoài dự kiến.

## 18. Tài liệu tham khảo

- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): `operationId` và metadata của operation.
- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object): schema, parameter, response và các component tái sử dụng.
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object): cú pháp và ngữ nghĩa `$ref`.
- [OpenAPI Specification – Link Object](https://spec.openapis.org/oas/latest.html#link-object): liên kết operation bằng operationId hoặc operationRef.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): `@Operation`, `@Schema`, `@Parameter` và response annotation.
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations): `@JsonProperty` và `@JsonAlias` cho tên property JSON.
- [Springdoc OpenAPI](https://springdoc.org/): cấu hình và tùy biến OpenAPI từ controller Spring Boot.
