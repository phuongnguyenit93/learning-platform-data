# Mảng, Collection và @ArraySchema

## 1. Vì sao cần mô tả mảng và Collection?

Nhiều API trao đổi dữ liệu theo danh sách: danh sách sản phẩm, dòng hàng trong đơn, các vai trò của người dùng, ảnh đính kèm hoặc tập mã trạng thái cần lọc. Trong Java, dữ liệu đó thường được biểu diễn bằng array, `List`, `Set` hoặc một kiểu `Collection` khác.

JSON dùng kiểu **array** để biểu diễn một dãy giá trị có thứ tự. OpenAPI mô tả kiểu dữ liệu này bằng schema có `type: array` và schema con `items` để xác định kiểu của từng phần tử. Khi Springdoc OpenAPI đọc chữ ký controller và DTO, thư viện có thể suy luận cấu trúc array từ kiểu Java. Annotation **`@ArraySchema`** cho phép mô tả rõ hơn cả mảng và phần tử bên trong.

Việc mô tả đúng array schema giúp client biết:

- Response trả về một danh sách kiểu dữ liệu nào.
- Request cần gửi mảng chuỗi, số, enum hay object.
- Mảng có được phép rỗng không và số phần tử tối thiểu/tối đa.
- Các phần tử có phải duy nhất không.
- Mỗi phần tử có schema, format, ví dụ và ràng buộc nào.

Nếu chỉ ghi “danh sách dữ liệu” mà không mô tả kiểu phần tử, client phải đoán cấu trúc JSON. Nếu schema cho phép mảng rỗng trong khi backend yêu cầu ít nhất một phần tử, tài liệu và runtime sẽ không thống nhất.

## 2. Array trong JSON và Array Schema trong OpenAPI

Trong JSON, array được viết bằng dấu ngoặc vuông. Các phần tử có thể là chuỗi, số, boolean, object, array lồng nhau hoặc giá trị null nếu schema cho phép.

Ví dụ:

~~~json
{
  "productIds": [101, 102, 103],
  "tags": ["new", "featured"],
  "items": [
    {
      "productId": 101,
      "quantity": 2
    },
    {
      "productId": 102,
      "quantity": 1
    }
  ]
}
~~~

OpenAPI mô tả một mảng bằng `type: array`. Trường `items` là schema của từng phần tử:

~~~yaml
type: array
items:
  type: integer
  format: int64
~~~

Schema trên mô tả một mảng số nguyên 64-bit. Ví dụ JSON hợp lệ là `[101, 102, 103]`.

Với mảng object, `items` tham chiếu schema của object:

~~~yaml
type: array
items:
  $ref: '#/components/schemas/OrderItem'
~~~

Mỗi phần tử trong mảng phải tuân theo schema `OrderItem`. Cấu trúc này thường xuất hiện khi endpoint trả về danh sách DTO hoặc nhận một danh sách object trong request body.

## 3. Java array và Collection được Springdoc suy luận như thế nào?

Java có nhiều cách biểu diễn một dãy dữ liệu. Các kiểu thường gặp:

| Kiểu Java | Ý nghĩa | Hình dạng JSON thường gặp |
|---|---|---|
| `ProductResponse[]` | Mảng Java có kích thước cố định sau khi tạo | Array |
| `List<ProductResponse>` | Danh sách có thứ tự, cho phép phần tử lặp | Array |
| `Set<ProductResponse>` | Tập hợp không cho phép phần tử trùng; thứ tự phụ thuộc implementation | Array |
| `Collection<String>` | Giao diện collection tổng quát | Array |
| `List<String>` | Danh sách chuỗi | Array |
| `List<List<Long>>` | Mảng lồng nhau | Array chứa array |

Ví dụ một controller trả về danh sách:

~~~java
@GetMapping("/api/products")
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

Springdoc thường suy luận response schema là array và schema của `items` là `ProductResponse`. Trong OpenAPI document, phần tử có thể được tham chiếu đến `components.schemas.ProductResponse`.

Một khai báo dùng Java array cũng tạo hình dạng JSON array:

~~~java
@GetMapping("/api/product-codes")
public String[] getProductCodes() {
    return productService.getProductCodes();
}
~~~

Đối với client, JSON array không thể hiện trực tiếp việc backend dùng `List`, `Set` hay Java array. Sự khác biệt chủ yếu nằm ở ngữ nghĩa và hành vi trong Java. Hợp đồng OpenAPI nên mô tả cấu trúc JSON và các quy tắc mà client cần tuân thủ.

## 4. Cấu trúc items: mô tả kiểu của từng phần tử

Trong Array Schema, `items` xác định kiểu và ràng buộc của từng phần tử. Đây là phần quan trọng nhất để client hiểu một danh sách chứa dữ liệu gì.

### 4.1. Mảng chuỗi

~~~yaml
type: array
items:
  type: string
  example: featured
~~~

JSON tương ứng:

~~~json
["new", "featured", "sale"]
~~~

### 4.2. Mảng số

~~~yaml
type: array
items:
  type: number
  format: double
~~~

JSON tương ứng:

~~~json
[12.5, 18.75, 20.0]
~~~

### 4.3. Mảng enum

~~~yaml
type: array
items:
  type: string
  enum:
    - DRAFT
    - ACTIVE
    - ARCHIVED
~~~

Mỗi phần tử chỉ được nhận một trong các giá trị enum được công bố.

### 4.4. Mảng object

~~~yaml
type: array
items:
  $ref: '#/components/schemas/OrderItem'
~~~

Mỗi phần tử phải có cấu trúc theo schema `OrderItem`. Không nên mô tả mảng object chỉ bằng `type: object` nếu client cần biết các thuộc tính con.

### 4.5. Mảng có phần tử là mảng

~~~yaml
type: array
items:
  type: array
  items:
    type: integer
~~~

JSON tương ứng:

~~~json
[
  [1, 2, 3],
  [4, 5, 6]
]
~~~

Với mảng lồng nhau, mỗi cấp array cần có schema `items` riêng. Cần mô tả rõ số chiều và ý nghĩa của từng cấp để client không nhầm mảng ma trận với danh sách object.

## 5. @ArraySchema dùng để làm gì?

Annotation **`@ArraySchema`** thuộc gói `io.swagger.v3.oas.annotations.media`. Nó dùng để mô tả schema của một array trong OpenAPI, bao gồm:

- Schema của phần tử thông qua thuộc tính `schema`.
- Metadata của chính array thông qua `arraySchema`.
- Các ràng buộc số lượng phần tử như `minItems`, `maxItems`.
- Quy tắc các phần tử phải duy nhất thông qua `uniqueItems`.

Có thể hiểu hai thuộc tính quan trọng như sau:

| Thuộc tính | Mô tả |
|---|---|
| `schema` | Schema của mỗi phần tử trong mảng |
| `arraySchema` | Schema của chính mảng, chẳng hạn description hoặc metadata tổng thể |

Ví dụ mô tả danh sách mã sản phẩm:

~~~java
@ArraySchema(
    arraySchema = @Schema(
        description = "Danh sách mã sản phẩm"
    ),
    schema = @Schema(
        type = "integer",
        format = "int64",
        example = "101"
    ),
    minItems = 1,
    maxItems = 100,
    uniqueItems = true
)
private List<Long> productIds;
~~~

Ở đây, `arraySchema` mô tả danh sách tổng thể; `schema` mô tả một mã sản phẩm. `minItems` yêu cầu ít nhất một phần tử, `maxItems` giới hạn tối đa 100 phần tử và `uniqueItems` khai báo các phần tử phải duy nhất.

Các thuộc tính annotation được hỗ trợ phụ thuộc phiên bản `swagger-annotations` mà dự án đang dùng. Khi nâng cấp thư viện, hãy kiểm tra API annotation và tài liệu OpenAPI sinh ra.

## 6. Mô tả array trong DTO request

Một request body thường chứa danh sách object. Ví dụ, khi tạo đơn hàng, client gửi các dòng hàng trong thuộc tính `items`.

DTO:

~~~java
public record CreateOrderRequest(
    @NotEmpty
    @Size(min = 1, max = 50)
    @ArraySchema(
        arraySchema = @Schema(
            description = "Các dòng sản phẩm của đơn hàng"
        ),
        schema = @Schema(
            implementation = OrderItemRequest.class
        ),
        minItems = 1,
        maxItems = 50
    )
    List<@Valid OrderItemRequest> items
) {}

public record OrderItemRequest(
    @NotNull
    @Positive
    @Schema(description = "Mã sản phẩm", example = "101")
    Long productId,

    @NotNull
    @Min(1)
    @Schema(description = "Số lượng đặt mua", example = "2")
    Integer quantity
) {}
~~~

Controller nhận request:

~~~java
@PostMapping("/api/orders")
public OrderResponse createOrder(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Springdoc có thể tạo schema array cho `items` và tham chiếu schema `OrderItemRequest` cho từng phần tử. Khi client xem tài liệu, họ biết mỗi phần tử cần có productId và quantity.

Trong ví dụ, các annotation có nhiệm vụ khác nhau:

- `@ArraySchema` mô tả cấu trúc array trong OpenAPI.
- `@Schema` mô tả phần tử hoặc metadata của mảng.
- `@NotEmpty` yêu cầu collection không null và không rỗng khi validation chạy.
- `@Size` giới hạn số phần tử ở backend.
- `@Valid` trên phần tử collection kích hoạt validation lồng nhau cho từng `OrderItemRequest`.

Ràng buộc tài liệu và validation nên thống nhất. Nếu chỉ khai báo `minItems = 1` trong OpenAPI mà backend không kiểm tra, client có thể gửi mảng rỗng và nhận kết quả khác với điều tài liệu hứa hẹn.

## 7. Phân biệt required, minItems và nullable

Ba khái niệm thường bị nhầm khi mô tả một thuộc tính array trong object.

| Quy tắc | Ý nghĩa |
|---|---|
| `required` của object | Thuộc tính array có bắt buộc phải xuất hiện trong JSON object không |
| `minItems` | Mảng có tối thiểu bao nhiêu phần tử |
| `nullable` hoặc type chứa null | Giá trị của thuộc tính array có được phép là null không |

Ví dụ:

~~~yaml
type: object
required:
  - tags
properties:
  tags:
    type: array
    minItems: 1
    items:
      type: string
~~~

Schema này yêu cầu thuộc tính `tags` phải xuất hiện và chứa ít nhất một chuỗi.

Nếu bỏ `tags` khỏi danh sách `required`, thuộc tính có thể không xuất hiện. Nếu giữ required nhưng không khai báo minItems, mảng rỗng vẫn có thể hợp lệ.

Trong OpenAPI 3.0, có thể dùng `nullable: true` để cho phép thuộc tính array nhận null. Trong OpenAPI 3.1, biểu diễn null theo JSON Schema, ví dụ `type: [array, "null"]`. Việc thuộc tính có bắt buộc xuất hiện hay không vẫn được xác định riêng bằng danh sách `required` của object.

Vì vậy, khi thiết kế DTO, cần phân biệt:

- `List<String> tags` có thể không null hoặc null tùy constructor, binding và validation.
- `@NotNull` yêu cầu collection không null.
- `@NotEmpty` yêu cầu collection không null và có ít nhất một phần tử.
- `@Size(min = 1, max = 10)` giới hạn số phần tử; nếu muốn cấm null, cần ràng buộc riêng.

## 8. minItems, maxItems và uniqueItems

OpenAPI cung cấp các keyword dành riêng cho array schema:

| Keyword | Ý nghĩa |
|---|---|
| `minItems` | Số phần tử tối thiểu |
| `maxItems` | Số phần tử tối đa |
| `uniqueItems` | Yêu cầu các phần tử không trùng nhau |

Ví dụ:

~~~yaml
type: array
minItems: 1
maxItems: 20
uniqueItems: true
items:
  type: string
~~~

Mảng phải có từ 1 đến 20 chuỗi và không có hai phần tử trùng nhau theo quy tắc so sánh JSON Schema.

Có thể ánh xạ một số ràng buộc từ Bean Validation:

| Bean Validation | Ràng buộc array tương ứng |
|---|---|
| `@NotNull` | Collection không được null; không tương đương minItems |
| `@NotEmpty` | Không null và có ít nhất một phần tử |
| `@Size(min = 1)` | Tối thiểu một phần tử |
| `@Size(max = 20)` | Tối đa 20 phần tử |
| `@UniqueElements` nếu dùng Hibernate Validator | Các phần tử không trùng theo validator |

Springdoc có thể suy luận một số giới hạn từ Bean Validation, tùy phiên bản và cấu hình. `@UniqueElements` không thuộc Bean Validation chuẩn; đây là constraint của Hibernate Validator. Nếu dùng, cần bảo đảm dependency validator có mặt và kiểm tra xem Springdoc có chuyển constraint đó thành `uniqueItems` trong tài liệu hay không. Có thể khai báo `uniqueItems` trực tiếp trong `@ArraySchema` để mô tả rõ hợp đồng.

## 9. Mô tả Collection Set và ý nghĩa uniqueness

Java `Set` thường biểu diễn một tập hợp không chứa phần tử trùng theo quy tắc `equals/hashCode` của phần tử. JSON không có kiểu Set riêng; khi serialize, Set thường được biểu diễn thành array.

Ví dụ:

~~~java
public record ProductFilter(
    Set<String> categories
) {}
~~~

JSON:

~~~json
{
  "categories": ["keyboard", "mouse", "monitor"]
}
~~~

Tuy nhiên, việc Java dùng Set không tự động có nghĩa client được bảo đảm thứ tự ổn định. Một số implementation như HashSet không cam kết thứ tự lặp. Nếu thứ tự có ý nghĩa trong hợp đồng, hãy dùng List và mô tả thứ tự đó trong description.

Nếu tính duy nhất là quy tắc quan trọng đối với client, nên thể hiện rõ bằng `uniqueItems: true` hoặc `@ArraySchema(uniqueItems = true)`. Đừng chỉ dựa vào kiểu Set vì tài liệu OpenAPI cần công bố quy tắc này cho mọi client, kể cả client viết bằng ngôn ngữ khác.

Cũng cần lưu ý rằng uniqueness của JSON Schema là so sánh giá trị JSON. Với object, hai object có nội dung tương đương được xem là trùng theo quy tắc JSON Schema, trong khi Java Set có thể dùng quy tắc equals riêng. Hãy kiểm tra sự tương ứng nếu phần tử là object.

## 10. Mô tả array trong response

Một endpoint có thể trả về danh sách trực tiếp:

~~~java
@GetMapping("/api/products")
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

Springdoc thường suy luận response là array có item schema `ProductResponse`. Nếu muốn bổ sung description hoặc ràng buộc cho mảng response, có thể dùng `@ArraySchema` trên phương thức:

~~~java
@GetMapping("/api/products")
@Operation(summary = "Lấy danh sách sản phẩm")
@ArraySchema(
    arraySchema = @Schema(
        description = "Danh sách sản phẩm hiện có"
    ),
    schema = @Schema(
        implementation = ProductResponse.class
    )
)
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

Với response dạng object bọc danh sách, chẳng hạn:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Bàn phím cơ"
    }
  ],
  "totalElements": 1
}
~~~

thì `content` là array property bên trong object, không phải toàn bộ response là array. Hãy dùng `@ArraySchema` trên thuộc tính `content` trong DTO wrapper và dùng `@Schema` cho object bao ngoài.

Cần phân biệt `List<ProductResponse>` với `Page<ProductResponse>`. Kiểu Page thường được biểu diễn thành object có metadata phân trang; không nên mô tả toàn bộ response của Page như một array thuần.

## 11. Mảng lồng nhau và Collection phức hợp

Một array có thể chứa array hoặc object có các thuộc tính array. Ví dụ dữ liệu tọa độ theo nhiều tuyến đường:

~~~yaml
type: array
items:
  type: array
  items:
    type: number
    format: double
~~~

Hoặc một object chứa nhiều danh sách:

~~~yaml
type: object
properties:
  images:
    type: array
    items:
      type: string
      format: uri
  variants:
    type: array
    items:
      $ref: '#/components/schemas/ProductVariant'
~~~

Trong Java:

~~~java
public record ProductResponse(
    Long id,
    List<String> images,
    List<ProductVariant> variants
) {}
~~~

Springdoc thường suy luận từng thuộc tính array từ generic type. Nếu cấu trúc lồng nhau phức tạp hoặc cần mô tả riêng cấp array và cấp item, hãy dùng `@ArraySchema` và `@Schema` tại vị trí phù hợp, rồi kiểm tra JSON/YAML sinh ra.

Không nên lạm dụng mảng nhiều chiều nếu một object có tên trường rõ nghĩa giúp client hiểu dữ liệu tốt hơn. Ví dụ, thay vì trả `[[1,2],[3,4]]`, có thể trả danh sách object có `latitude` và `longitude` nếu đó là tọa độ địa lý.

## 12. Ví dụ và mô tả phần tử array

Mảng thường cần ví dụ để client hiểu hình dạng dữ liệu. Có thể dùng example ở cấp array hoặc ví dụ cho từng item.

Ví dụ OpenAPI:

~~~yaml
type: array
description: Danh sách mã trạng thái cần lọc
minItems: 1
items:
  type: string
  enum:
    - ACTIVE
    - INACTIVE
    - ARCHIVED
example:
  - ACTIVE
  - ARCHIVED
~~~

Trong Java, có thể dùng `@ArraySchema` cho cấu trúc và `@ExampleObject` ở media type của request/response để cung cấp ví dụ hoàn chỉnh. Ví dụ cần khớp với schema, bao gồm kiểu phần tử, enum, giới hạn số lượng và uniqueness.

Không nhầm ví dụ mảng với ví dụ item. Nếu schema là array, example phải là một mảng như `["ACTIVE", "ARCHIVED"]`, không phải một chuỗi đơn như `"ACTIVE"`.

## 13. Các lỗi thường gặp khi mô tả array

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI hiển thị item là object rỗng | Springdoc không suy luận được generic type hoặc cần khai báo implementation |
| Array bị mô tả thành một object | Dùng annotation sai vị trí hoặc schema override không đúng |
| Thiếu giới hạn số phần tử | Chưa khai báo minItems/maxItems hoặc constraint không được suy luận |
| Set không thể hiện uniqueness | Chưa khai báo uniqueItems hoặc công cụ không suy luận từ kiểu Java |
| Array response bị bọc thành object | Kiểu trả về thực tế là wrapper như Page hoặc DTO |
| Mảng lồng nhau sai số chiều | Schema items ở các cấp chưa được khai báo đúng |
| Example không hợp lệ | Example là một item đơn thay vì một array hoặc không khớp item schema |
| Backend nhận mảng rỗng nhưng tài liệu cấm | minItems/validation không đồng nhất |
| Backend loại phần tử trùng nhưng tài liệu không nói | Chưa công bố uniqueItems hoặc mô tả quy tắc xử lý trùng |

Khi gặp vấn đề, hãy kiểm tra OpenAPI JSON/YAML trước, sau đó so sánh với kiểu Java, annotation và validation thực tế. Đừng chỉ dựa vào cách Swagger UI trình bày vì giao diện có thể ẩn một số chi tiết của schema.

## 14. Kiểm tra array schema trong OpenAPI document

Sau khi khởi động ứng dụng, tải tài liệu:

~~~http
GET /v3/api-docs
~~~

Với mỗi array property hoặc operation trả về array, kiểm tra:

1. Schema có `type: array`.
2. Có `items` mô tả kiểu phần tử.
3. Item schema tham chiếu đúng component nếu là DTO.
4. `minItems`, `maxItems` và `uniqueItems` đúng với quy tắc backend.
5. `required` của object phản ánh việc thuộc tính array có phải xuất hiện không.
6. Nullable được mô tả theo phiên bản OpenAPI đang dùng.
7. Example là array hợp lệ và các item khớp schema.
8. Array lồng nhau có đúng số cấp `items`.

Có thể kết hợp validator OpenAPI và integration test:

- Gửi mảng rỗng.
- Gửi số phần tử đúng giới hạn và vượt giới hạn.
- Gửi phần tử sai kiểu.
- Gửi phần tử trùng nếu uniqueness được yêu cầu.
- Gửi phần tử null nếu schema cho phép hoặc cấm.
- Kiểm tra response array và thứ tự phần tử nếu thứ tự là một phần hợp đồng.

## 15. Nguyên tắc sử dụng @ArraySchema trong dự án

Khi mô tả array và Collection với Springdoc, hãy giữ các nguyên tắc:

1. Để Springdoc suy luận từ Java array hoặc generic Collection khi kiểu phần tử đã rõ.
2. Dùng `@ArraySchema` khi cần mô tả array container, item schema hoặc các ràng buộc riêng.
3. Dùng `schema` để mô tả phần tử và `arraySchema` để mô tả toàn bộ mảng.
4. Phân biệt thuộc tính array required với minItems và nullable.
5. Chỉ khai báo uniqueItems khi backend thực sự bảo đảm hoặc kiểm tra uniqueness.
6. Dùng Bean Validation để thực thi min/max size và validation lồng nhau ở runtime.
7. Mô tả rõ array lồng nhau và generic Collection phức hợp.
8. Dùng examples có hình dạng array đúng với schema.
9. Kiểm tra OpenAPI JSON/YAML và hành vi runtime sau khi thay đổi annotation.

Java array, List và Set đều có thể được biểu diễn thành JSON array, nhưng ngữ nghĩa về thứ tự, phần tử lặp và validation có thể khác nhau. Khi Springdoc kết hợp suy luận kiểu Java với `@ArraySchema` và các ràng buộc phù hợp, tài liệu OpenAPI sẽ mô tả chính xác cả cấu trúc mảng lẫn quy tắc mà client cần tuân thủ.

