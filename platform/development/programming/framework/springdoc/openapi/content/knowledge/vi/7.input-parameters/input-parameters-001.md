# @Parameter và mối liên hệ với annotation binding của Spring

## 1. Hai lớp trách nhiệm trong khai báo tham số

Khi xây dựng REST API bằng Spring Boot, controller nhận dữ liệu từ HTTP request thông qua các annotation binding như `@PathVariable`, `@RequestParam`, `@RequestHeader` và `@CookieValue`. Các annotation này cho Spring biết lấy giá trị từ đâu, chuyển đổi sang kiểu Java nào và tham số có bắt buộc hay không.

OpenAPI cần mô tả cùng tham số đó để client biết phải gửi dữ liệu như thế nào. Springdoc OpenAPI đọc metadata của Spring và chữ ký controller để tạo Parameter Object trong tài liệu. Annotation **`@Parameter`** bổ sung thông tin mô tả mà Spring binding không thể hiện đầy đủ, chẳng hạn ý nghĩa nghiệp vụ, ví dụ, giới hạn, kiểu serialize hoặc cách hiển thị.

Hai lớp annotation liên quan nhưng có mục đích khác nhau:

- **Annotation binding của Spring** quyết định cách ứng dụng nhận và xử lý giá trị khi request đi vào.
- **`@Parameter` của Swagger/OpenAPI** mô tả tham số trong hợp đồng OpenAPI để con người và công cụ hiểu cách gọi API.

`@Parameter` không tự đọc query string, không bind giá trị vào biến Java và không thay thế validation. Ngược lại, `@RequestParam` có thể bind một giá trị hoàn chỉnh nhưng không nhất thiết giải thích rõ ý nghĩa nghiệp vụ của nó cho người đọc tài liệu.

Ví dụ, `@RequestParam(name = "status")` giúp Spring lấy query parameter `status`; `@Parameter(description = "Trạng thái sản phẩm")` giúp Swagger UI giải thích trường đó cho client.

## 2. Parameter Object trong OpenAPI

Trong OpenAPI, một tham số của operation được mô tả bằng **Parameter Object**. Các thuộc tính thường dùng gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `name` | Tên tham số trong HTTP request |
| `in` | Vị trí: `path`, `query`, `header` hoặc `cookie` |
| `description` | Giải thích mục đích và cách sử dụng |
| `required` | Tham số có bắt buộc hay không |
| `deprecated` | Đánh dấu tham số đã lỗi thời |
| `schema` | Kiểu dữ liệu, định dạng và ràng buộc |
| `example` / `examples` | Giá trị minh họa |
| `style` / `explode` | Cách serialize giá trị vào URL hoặc header |
| `allowReserved` | Cho phép ký tự reserved trong query parameter theo quy tắc OpenAPI |

Một parameter được nhận diện bởi cặp **name + in**. Vì vậy, query parameter `id` và header `id` là hai tham số khác nhau.

OpenAPI quy định path parameter luôn phải có `required: true`. Các vị trí query, header và cookie có thể là bắt buộc hoặc tùy chọn theo hợp đồng API. Tài liệu phải phản ánh đúng hành vi của controller.

Ví dụ một operation có query parameter:

~~~yaml
paths:
  /products:
    get:
      summary: Tìm kiếm sản phẩm
      parameters:
        - name: keyword
          in: query
          description: Từ khóa tìm trong tên sản phẩm
          required: false
          schema:
            type: string
          example: keyboard
      responses:
        "200":
          description: Thành công
~~~

Springdoc tạo phần tương đương từ controller và annotation. Khi cần kiểm soát mô tả chi tiết, có thể đặt `@Parameter` ngay trên tham số phương thức.

## 3. Spring binding annotation được ánh xạ vào vị trí nào?

Springdoc thường suy luận vị trí parameter từ annotation binding của Spring MVC:

| Annotation Spring | Vị trí OpenAPI | Cách client truyền dữ liệu |
|---|---|---|
| `@PathVariable` | `path` | Một phần của URL path |
| `@RequestParam` | `query` | Query string sau dấu `?` |
| `@RequestHeader` | `header` | HTTP request header |
| `@CookieValue` | `cookie` | Cookie của request |
| `@ModelAttribute` | Bind các trường từ request parameter; dùng thêm `@ParameterObject` để mô tả từng trường thành query parameter | Các trường của object được bind từ request parameter |
| `@RequestBody` | Request Body Object, không phải Parameter Object | Dữ liệu trong HTTP body |
| `@RequestPart` | Thành phần của request body, thường dùng multipart | Một phần của multipart body |

Ví dụ:

~~~java
@GetMapping("/products/{productId}")
public ProductResponse findProduct(
    @PathVariable("productId") Long productId,
    @RequestParam(name = "includeInactive", required = false) boolean includeInactive,
    @RequestHeader(name = "X-Request-Id", required = false) String requestId,
    @CookieValue(name = "locale", required = false) String locale
) {
    return productService.find(productId, includeInactive, requestId, locale);
}
~~~

Springdoc có thể nhận diện:

- `productId` là path parameter.
- `includeInactive` là query parameter.
- `X-Request-Id` là header parameter.
- `locale` là cookie parameter.

Tên được khai báo rõ bằng `name` hoặc `value` giúp tránh phụ thuộc vào tên biến Java và cấu hình compiler. Nếu tên tham số trong hợp đồng khác tên biến Java, hãy kiểm tra kết quả OpenAPI JSON để bảo đảm đúng tên client cần gửi.

## 4. Bổ sung mô tả bằng @Parameter

Annotation `@Parameter` thuộc gói `io.swagger.v3.oas.annotations`. Nó thường được đặt ngay trước annotation binding trên cùng tham số phương thức.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping("/{productId}")
    @Operation(summary = "Lấy thông tin sản phẩm")
    public ProductResponse findProduct(
        @Parameter(
            description = "Mã định danh duy nhất của sản phẩm",
            example = "42"
        )
        @PathVariable("productId")
        Long productId,

        @Parameter(
            description = "Có bao gồm sản phẩm đã ngừng kinh doanh hay không",
            example = "false"
        )
        @RequestParam(
            name = "includeInactive",
            required = false,
            defaultValue = "false"
        )
        boolean includeInactive
    ) {
        return productService.find(productId, includeInactive);
    }
}
~~~

Ở đây, Spring binding annotation xác định vị trí và hành vi runtime. `@Parameter` bổ sung mô tả và ví dụ cho tài liệu. Springdoc kết hợp thông tin từ cả hai nguồn để tạo parameter trong OpenAPI.

Một số thuộc tính thường dùng của `@Parameter`:

~~~java
@Parameter(
    name = "keyword",
    description = "Tìm trong tên và mã sản phẩm",
    example = "mechanical keyboard",
    required = false,
    deprecated = false
)
@RequestParam(name = "keyword", required = false)
String keyword
~~~

Không cần khai báo lại tất cả thuộc tính nếu Springdoc đã suy luận đúng. Hãy bổ sung những thông tin thực sự giúp client hiểu cách sử dụng và giữ tên, vị trí, trạng thái bắt buộc thống nhất với binding annotation.

## 5. Mối liên hệ với từng annotation binding

### 5.1. @PathVariable: tham số nằm trong đường dẫn

`@PathVariable` bind một biến trong URL path vào tham số Java:

~~~java
@GetMapping("/orders/{orderId}")
public OrderResponse getOrder(
    @Parameter(
        description = "Mã đơn hàng",
        example = "ORD-2026-001"
    )
    @PathVariable("orderId")
    String orderId
) {
    return orderService.findById(orderId);
}
~~~

OpenAPI biểu diễn tham số này với `in: path` và `required: true`. Path parameter là một phần của cấu trúc đường dẫn, vì vậy không thể tùy ý đánh dấu nó là optional trong OpenAPI.

Nếu có hai dạng URL, chẳng hạn `/orders` và `/orders/{orderId}`, hãy mô tả thành các path hoặc operation phù hợp. Không nên dùng `required = false` trong tài liệu để giả lập một path segment tùy chọn.

### 5.2. @RequestParam: tham số query

`@RequestParam` bind dữ liệu từ query string:

~~~java
@GetMapping("/products")
public List<ProductResponse> search(
    @Parameter(
        description = "Từ khóa tìm kiếm",
        example = "keyboard"
    )
    @RequestParam(name = "keyword", required = false)
    String keyword,

    @Parameter(
        description = "Số bản ghi tối đa cần trả về",
        example = "20"
    )
    @RequestParam(name = "size", defaultValue = "20")
    @Min(1) @Max(100)
    int size
) {
    return productService.search(keyword, size);
}
~~~

Spring mặc định xem `@RequestParam` là bắt buộc nếu không có `required = false` hoặc `defaultValue`. Khi có `defaultValue`, Spring coi tham số là không bắt buộc và dùng giá trị mặc định nếu parameter bị thiếu hoặc rỗng theo quy tắc binding.

Cần phân biệt:

- `defaultValue` của Spring ảnh hưởng hành vi runtime.
- `example` của `@Parameter` chỉ minh họa giá trị trong tài liệu.
- `description` giải thích ý nghĩa, không thay đổi giá trị được bind.

Nếu API nhận nhiều giá trị, ví dụ `?status=ACTIVE&status=INACTIVE`, có thể dùng `List<String>` hoặc `List<ProductStatus>`. Khi đó cần mô tả cách serialize phù hợp bằng thuộc tính `style` và `explode` nếu công cụ không suy luận đúng.

~~~java
@Parameter(
    description = "Các trạng thái cần lọc; có thể lặp tham số",
    style = ParameterStyle.FORM,
    explode = Explode.TRUE
)
@RequestParam(name = "status", required = false)
List<ProductStatus> statuses
~~~

Với `style = form` và `explode = true`, cách biểu diễn thông thường là:

~~~http
GET /api/products?status=ACTIVE&status=INACTIVE
~~~

Trong ví dụ, `ParameterStyle`, `Explode` và `ParameterIn` thuộc gói `io.swagger.v3.oas.annotations.enums`. Nếu hợp đồng dùng một chuỗi phân tách bằng dấu phẩy, ví dụ `status=ACTIVE,INACTIVE`, cần chọn cách serialize tương ứng và xác minh tài liệu sinh ra.

### 5.3. @RequestHeader: tham số trong HTTP header

`@RequestHeader` bind một giá trị từ HTTP header:

~~~java
@GetMapping("/reports")
public ReportResponse getReport(
    @Parameter(
        description = "Mã tương quan để theo dõi request qua các dịch vụ",
        example = "req-8f21a6"
    )
    @RequestHeader(name = "X-Request-Id", required = false)
    String requestId
) {
    return reportService.create(requestId);
}
~~~

Springdoc có thể mô tả tham số này với `in: header`. Tên header trong tài liệu phải khớp với tên client gửi.

Với header xác thực như `Authorization: Bearer ...`, nên mô tả bằng **Security Scheme** và **Security Requirement** của OpenAPI. Không nên mô tả token xác thực như một header tùy ý ở từng operation nếu API thực sự dùng cơ chế Bearer authentication chung.

### 5.4. @CookieValue: tham số lấy từ cookie

`@CookieValue` bind giá trị cookie vào tham số Java:

~~~java
@GetMapping("/preferences")
public PreferenceResponse getPreferences(
    @Parameter(
        description = "Mã ngôn ngữ giao diện lưu trong cookie",
        example = "vi"
    )
    @CookieValue(name = "locale", required = false)
    String locale
) {
    return preferenceService.find(locale);
}
~~~

OpenAPI biểu diễn cookie parameter với `in: cookie`. Hãy ghi rõ cookie có bắt buộc không, được tạo ở đâu và thời hạn hoặc cách sử dụng nếu client cần biết. Thông tin cookie nhạy cảm không nên đưa vào ví dụ công khai.

## 6. Tham số object với @ModelAttribute và @ParameterObject

Một form tìm kiếm có thể chứa nhiều trường. Thay vì khai báo tất cả thành tham số riêng lẻ, Spring MVC cho phép bind chúng vào một object bằng `@ModelAttribute`:

~~~java
public class ProductSearchCriteria {

    private String keyword;
    private ProductStatus status;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;

    // Getter và setter
}
~~~

Controller:

~~~java
@GetMapping("/products")
public List<ProductResponse> search(
    @ModelAttribute ProductSearchCriteria criteria
) {
    return productService.search(criteria);
}
~~~

Spring MVC bind các request parameter vào các thuộc tính của object. Với GET endpoint, các thuộc tính thường được truyền qua query string. Tuy nhiên, một object Java không tự động nói rõ cách mỗi thuộc tính cần xuất hiện trong OpenAPI.

Springdoc hỗ trợ annotation **`@ParameterObject`** để mở rộng object thành các query parameter riêng:

~~~java
@GetMapping("/products")
public List<ProductResponse> search(
    @ParameterObject
    @ModelAttribute ProductSearchCriteria criteria
) {
    return productService.search(criteria);
}
~~~

Tài liệu có thể hiển thị các trường keyword, status, minPrice và maxPrice như những query parameter riêng. Có thể dùng `@Schema` trên thuộc tính của criteria để mô tả kiểu, ví dụ và ý nghĩa từng trường.

`@ParameterObject` là chỉ dẫn cho quá trình tạo tài liệu của Springdoc; `@ModelAttribute` vẫn đảm nhiệm binding ở runtime. Cần kiểm tra phiên bản Springdoc đang dùng và JSON sinh ra, nhất là với object lồng nhau, collection hoặc thuộc tính tùy biến.

## 7. Phân biệt @Parameter với @RequestBody và @RequestPart

Không phải mọi dữ liệu đầu vào đều là Parameter Object. Trong OpenAPI, path, query, header và cookie là các vị trí của parameter. Request body được mô tả riêng bằng **Request Body Object**.

Ví dụ:

~~~java
@PostMapping("/products")
public ProductResponse create(
    @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Springdoc suy luận request body từ `@RequestBody` và kiểu DTO. Có thể bổ sung mô tả bằng annotation **`@io.swagger.v3.oas.annotations.parameters.RequestBody`** hoặc mô tả schema của DTO bằng `@Schema`.

Đối với multipart upload, `@RequestPart` cũng mô tả một phần của request body theo media type phù hợp, không phải query parameter.

Không dùng `@Parameter` để mô tả JSON body như thể client gửi nó trong query string. Chọn đúng loại OpenAPI object giúp Swagger UI hiển thị form nhập liệu và content type chính xác.

## 8. Khi nào cần khai báo in, name hoặc parameters tường minh?

Thông thường, Springdoc có thể suy luận `name` và `in` từ Spring binding annotation. Có thể khai báo tường minh trong `@Parameter` khi cần bổ sung hoặc điều chỉnh mô tả:

~~~java
@Parameter(
    name = "X-Tenant-Id",
    in = ParameterIn.HEADER,
    description = "Mã tenant của request",
    required = true,
    example = "tenant-01"
)
@RequestHeader(name = "X-Tenant-Id")
String tenantId
~~~

Ở ví dụ này, `@RequestHeader` quyết định giá trị được lấy từ header; `@Parameter` mô tả chính xác tên, vị trí và yêu cầu trong OpenAPI. Hai khai báo phải khớp nhau.

Cũng có thể khai báo parameter ở cấp operation thông qua `@Operation(parameters = ...)` khi cần mô tả một tham số chung hoặc tham số không xuất hiện trực tiếp trong chữ ký controller:

~~~java
@Operation(
    summary = "Lấy báo cáo",
    parameters = {
        @Parameter(
            name = "X-Client-Version",
            in = ParameterIn.HEADER,
            description = "Phiên bản client gọi API",
            required = false,
            example = "2.4.0"
        )
    }
)
@GetMapping("/reports")
public ReportResponse getReport() {
    return reportService.create();
}
~~~

Khai báo ở cấp operation chỉ bổ sung tài liệu. Nó không tự tạo cơ chế đọc header trong Spring. Nếu ứng dụng thực sự cần giá trị đó, phải có binding annotation, filter, interceptor hoặc cơ chế runtime phù hợp. Tránh mô tả một parameter mà server không đọc hoặc không xử lý.

Không nên khai báo cùng một parameter nhiều lần với các giá trị `name`, `in` hoặc `required` mâu thuẫn. Nếu tham số đã được suy luận từ chữ ký phương thức, ưu tiên bổ sung mô tả ngay tại tham số đó.

## 9. Điều chỉnh schema, ví dụ và ràng buộc

`@Parameter` có thể kết hợp với `@Schema` để mô tả kiểu dữ liệu của tham số:

~~~java
@Parameter(
    description = "Số lượng sản phẩm cần lấy",
    schema = @Schema(
        type = "integer",
        minimum = "1",
        maximum = "100",
        defaultValue = "20",
        example = "20"
    )
)
@RequestParam(name = "size", defaultValue = "20")
@Min(1) @Max(100)
int size
~~~

Trong ví dụ:

- `@RequestParam(defaultValue = "20")` thiết lập giá trị runtime khi client không truyền size.
- `@Min(1)` và `@Max(100)` là validation constraint ở backend.
- `@Schema` cung cấp schema và thông tin giới hạn trong OpenAPI.
- `@Parameter.description` giải thích mục đích của tham số.

Springdoc có thể suy luận một số constraint từ Bean Validation, nhưng mức độ hỗ trợ phụ thuộc phiên bản và cấu hình. Hãy kiểm tra schema được sinh ra để tránh tài liệu và validation thực tế khác nhau.

Ví dụ chỉ là dữ liệu minh họa. Nếu đặt `example` khác với `defaultValue`, client cần hiểu rằng giá trị ví dụ không nhất thiết là giá trị server tự áp dụng.

## 10. Ẩn hoặc đánh dấu tham số đã lỗi thời

Có thể dùng `@Parameter(hidden = true)` để loại một tham số khỏi tài liệu OpenAPI khi có lý do phù hợp:

~~~java
@GetMapping("/internal-report")
public ReportResponse getInternalReport(
    @Parameter(hidden = true)
    @RequestParam(name = "legacyMode", required = false)
    boolean legacyMode
) {
    return reportService.create(legacyMode);
}
~~~

Việc ẩn tham số chỉ ảnh hưởng tài liệu được sinh. Spring vẫn có thể bind và xử lý tham số đó nếu client gửi request. Ẩn không phải biện pháp bảo mật hoặc kiểm soát quyền truy cập.

Nếu tham số vẫn được hỗ trợ nhưng không khuyến khích dùng, có thể đánh dấu `deprecated = true` và mô tả phương án thay thế:

~~~java
@Parameter(
    description = "Tham số cũ; hãy dùng responseFormat",
    deprecated = true
)
@RequestParam(name = "format", required = false)
String format
~~~

Khi loại bỏ tham số, cần xem xét tương thích client, thông báo thời gian chuyển đổi và cập nhật hợp đồng API theo chính sách versioning của dự án.

## 11. Kiểm tra tài liệu được Springdoc sinh ra

Sau khi khai báo controller, không nên chỉ nhìn annotation rồi kết luận tài liệu đã đúng. Hãy truy cập OpenAPI JSON mặc định:

~~~http
GET /v3/api-docs
~~~

Tìm operation tương ứng và xác minh:

- Path parameter có `in: path` và `required: true`.
- Query parameter có đúng tên, kiểu, default và required.
- Header và cookie có đúng vị trí.
- Description, example và schema constraints có đầy đủ.
- Array parameter có đúng style/explode.
- Request body xuất hiện trong `requestBody`, không bị nhầm thành parameter.
- Không có parameter trùng lặp hoặc khai báo sai vị trí.

Một số lỗi thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Tên parameter không đúng | Thiếu `name/value` trong Spring annotation hoặc cấu hình tên bị lệch với `@Parameter` |
| Parameter bị đánh dấu required sai | `required` trong binding annotation không khớp `@Parameter`; có defaultValue nhưng tài liệu chưa phản ánh |
| Path parameter không hợp lệ | Thiếu biến tương ứng trong path hoặc mô tả required sai |
| Header xuất hiện thành query | Dùng sai Spring binding annotation hoặc override `in` không đúng |
| Object tìm kiếm không được bung thành các field | Thiếu `@ParameterObject` hoặc cấu trúc object không được phiên bản Springdoc hỗ trợ |
| Request body xuất hiện như parameter | Dùng nhầm annotation hoặc mô hình hóa dữ liệu đầu vào sai |
| Ví dụ hoặc giới hạn không hiển thị | Annotation chưa đặt đúng đối tượng hoặc phiên bản thư viện chưa hỗ trợ thuộc tính |

Nên kết hợp kiểm tra OpenAPI document với integration test gửi request thật. Một parameter được mô tả là optional nhưng controller vẫn trả 400 khi thiếu là dấu hiệu hợp đồng và runtime chưa thống nhất.

## 12. Nguyên tắc sử dụng @Parameter trong dự án

Khi mô tả tham số đầu vào bằng Springdoc, hãy áp dụng các nguyên tắc:

1. Dùng Spring binding annotation để xác định nguồn dữ liệu và hành vi runtime.
2. Dùng `@Parameter` để bổ sung mô tả, ví dụ, schema, trạng thái deprecated hoặc cách serialize.
3. Giữ `name`, `in` và `required` trong OpenAPI nhất quán với controller.
4. Dùng `@ParameterObject` khi muốn mở rộng object tìm kiếm thành query parameter riêng.
5. Dùng Request Body Object để mô tả `@RequestBody` và `@RequestPart`.
6. Dùng security scheme cho cơ chế xác thực chung thay vì khai báo token như parameter thông thường.
7. Kiểm tra OpenAPI JSON/YAML và hành vi runtime sau khi thay đổi annotation.

Spring binding annotation cho biết ứng dụng nhận dữ liệu ở đâu; `@Parameter` cho biết client cần gửi dữ liệu đó như thế nào và ý nghĩa của nó là gì. Khi hai lớp mô tả được giữ nhất quán, Springdoc có thể tạo hợp đồng API rõ ràng, Swagger UI hiển thị form nhập liệu phù hợp và các client tích hợp giảm được lỗi khi gọi endpoint.

