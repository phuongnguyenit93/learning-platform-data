# Mô tả bộ lọc dạng DTO truy vấn

Khi API cần nhiều điều kiện tìm kiếm, khai báo từng `@RequestParam` trực tiếp trên controller có thể làm chữ ký method dài và khó duy trì. Spring MVC cho phép gom các tham số query vào một DTO bằng `@ModelAttribute`; springdoc-openapi có thể trải các property của DTO thành những query parameter riêng trong tài liệu bằng `@ParameterObject`. Cách này giúp gom validation, giá trị mặc định và mô tả bộ lọc vào một mô hình rõ ràng, đồng thời giữ đúng hình thức HTTP: client vẫn gửi các cặp key-value trên URL.

## 1. Bộ lọc query DTO là gì?

Giả sử API tìm kiếm sản phẩm cần các điều kiện:

- Từ khóa `keyword`.
- Danh sách trạng thái `status`.
- Mã danh mục `categoryId`.
- Khoảng giá `minPrice` và `maxPrice`.
- Khoảng ngày tạo `createdFrom` và `createdTo`.
- Số trang và kích thước trang.

Nếu khai báo từng tham số, controller có thể trở nên dài:

```java
@GetMapping("/api/products")
Page<ProductResponse> search(
    @RequestParam(required = false) String keyword,
    @RequestParam(required = false) List<ProductStatus> status,
    @RequestParam(required = false) Long categoryId,
    @RequestParam(required = false) BigDecimal minPrice,
    @RequestParam(required = false) BigDecimal maxPrice,
    @RequestParam(required = false) LocalDate createdFrom,
    @RequestParam(required = false) LocalDate createdTo,
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size
) {
    // ...
}
```

Có thể gom các điều kiện lọc thành một class:

```java
public class ProductFilter {
    private String keyword;
    private List<ProductStatus> status;
    private Long categoryId;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
    private LocalDate createdFrom;
    private LocalDate createdTo;

    // getters và setters
}
```

Client vẫn gọi endpoint bằng query string:

```http
GET /api/products?keyword=pen&status=ACTIVE&status=DRAFT&categoryId=5&minPrice=10000&maxPrice=50000&createdFrom=2026-01-01&createdTo=2026-12-31&page=0&size=20
```

DTO chỉ gom dữ liệu đầu vào ở phía Java. Nó không biến query string thành JSON body và không thay đổi cách HTTP request được gửi.

## 2. Phân biệt @ModelAttribute và @ParameterObject

Hai annotation thường được dùng cùng nhau nhưng thuộc hai lớp khác nhau:

| Annotation | Package | Vai trò |
|---|---|---|
| Spring `@ModelAttribute` | `org.springframework.web.bind.annotation` | Binding query parameter/form field vào object ở runtime |
| springdoc `@ParameterObject` | `org.springdoc.core.annotations` trong springdoc 2.x | Yêu cầu springdoc trải property của object thành các parameter riêng trong OpenAPI |
| Swagger `@Parameter` | `io.swagger.v3.oas.annotations` | Bổ sung metadata cho một parameter cụ thể |
| Swagger `@Schema` | `io.swagger.v3.oas.annotations.media` | Mô tả kiểu, format, giới hạn, ví dụ và nội dung property |

`@ModelAttribute` ảnh hưởng cách Spring xử lý request. `@ParameterObject` chỉ ảnh hưởng cách springdoc tạo tài liệu; nó không thực hiện binding và không thay thế `@ModelAttribute`.

Package của `@ParameterObject` thay đổi giữa các dòng springdoc: springdoc 2.x dùng `org.springdoc.core.annotations.ParameterObject`; các bản 1.x dùng `org.springdoc.api.annotations.ParameterObject`. Hãy dùng import đúng với major version trong dependency của dự án.

Ví dụ:

```java
@GetMapping("/api/products")
Page<ProductResponse> search(
    @Valid
    @ModelAttribute
    @ParameterObject
    ProductFilter filter,
    @ParameterObject Pageable pageable
) {
    return productService.search(filter, pageable);
}
```

Ở runtime, Spring bind các query parameter vào `ProductFilter` và `Pageable`. Trong OpenAPI, springdoc trình bày các property như `keyword`, `status`, `categoryId`, `minPrice` thành các parameter `in: query` độc lập.

Với POJO dùng làm query object, nên ghi rõ `@ModelAttribute` để người đọc dễ nhận ra nguồn dữ liệu và tránh nhầm với `@RequestBody`. `@ParameterObject` là annotation dành cho springdoc; nó không làm cho một class bất kỳ tự động trở thành nguồn query parameter ở runtime.

## 3. Thiết kế DTO bộ lọc

DTO nên biểu diễn đúng những điều kiện client được phép sử dụng. Không nên đưa trực tiếp entity hoặc đối tượng repository vào query DTO.

Ví dụ đầy đủ:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.format.annotation.DateTimeFormat;

public class ProductFilter {

    @Schema(description = "Từ khóa tìm trong tên hoặc mã sản phẩm", example = "pen")
    private String keyword;

    @Schema(description = "Các trạng thái cần lấy")
    private List<ProductStatus> status;

    @Schema(description = "Mã danh mục", example = "5", minimum = "1")
    private Long categoryId;

    @Schema(description = "Giá bán tối thiểu", example = "10000", minimum = "0")
    private BigDecimal minPrice;

    @Schema(description = "Giá bán tối đa", example = "50000", minimum = "0")
    private BigDecimal maxPrice;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    @Schema(description = "Ngày tạo từ (bao gồm)", type = "string", format = "date", example = "2026-01-01")
    private LocalDate createdFrom;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    @Schema(description = "Ngày tạo đến (bao gồm)", type = "string", format = "date", example = "2026-12-31")
    private LocalDate createdTo;

    // getters và setters
}
```

`@Schema` cung cấp thông tin cho OpenAPI, còn `@DateTimeFormat` hướng dẫn Spring chuyển chuỗi query thành `LocalDate`. Các kiểu số, enum và collection được Spring chuyển đổi thông qua `ConversionService` và các converter phù hợp.

### Vì sao nên dùng JavaBean DTO cho query binding?

Spring MVC hỗ trợ binding model attribute qua constructor hoặc property access tùy kiểu class và phiên bản. JavaBean có constructor không tham số cùng getter/setter là cách dễ hiểu và tương thích rộng cho ví dụ query DTO. Nếu dùng record hoặc constructor binding, hãy xác nhận Spring Framework version và quy tắc binding đang áp dụng trong dự án.

Không nên để client gửi trực tiếp các field kỹ thuật như tên cột database, JPQL fragment, tên property entity tùy ý hoặc biểu thức sort chưa được kiểm soát. DTO nên chứa những lựa chọn API đã được xác định.

## 4. Tích hợp DTO với controller và springdoc

Controller có thể khai báo DTO filter và `Pageable`:

```java
import jakarta.validation.Valid;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductQueryController {

    private final ProductService productService;

    ProductQueryController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    Page<ProductResponse> search(
        @Valid @ModelAttribute @ParameterObject ProductFilter filter,
        @ParameterObject @PageableDefault(size = 20, sort = "name") Pageable pageable
    ) {
        return productService.search(filter, pageable);
    }
}
```

Trong ví dụ này, `@PageableDefault` đặt giá trị mặc định cho phân trang ở runtime. Springdoc có thể mô tả các tham số `page`, `size`, `sort` của `Pageable`; `@ParameterObject` giúp chúng được trình bày như query parameter. Cần kiểm tra tài liệu sinh ra theo phiên bản springdoc và cấu hình Spring Data Web đang dùng.

Nếu không sử dụng Spring Data `Pageable`, có thể đưa `page` và `size` vào chính filter DTO. Khi đó cần quy định rõ chỉ số trang bắt đầu từ 0 hay 1 và giới hạn kích thước tối đa.

## 5. OpenAPI biểu diễn DTO thành các query parameter

OpenAPI không dùng request body để thay thế query string cho một GET thông thường. Một Parameter Object vẫn có thể mô tả schema object với cách serialize phù hợp, nhưng `@ParameterObject` của springdoc thường trải các property của POJO thành các Parameter Object riêng:

```yaml
paths:
  /api/products:
    get:
      parameters:
        - name: keyword
          in: query
          description: Từ khóa tìm trong tên hoặc mã sản phẩm
          schema:
            type: string
          example: pen
        - name: status
          in: query
          description: Các trạng thái cần lấy
          schema:
            type: array
            items:
              $ref: '#/components/schemas/ProductStatus'
          style: form
          explode: true
        - name: categoryId
          in: query
          schema:
            type: integer
            format: int64
        - name: minPrice
          in: query
          schema:
            type: number
        - name: maxPrice
          in: query
          schema:
            type: number
        - name: createdFrom
          in: query
          schema:
            type: string
            format: date
        - name: createdTo
          in: query
          schema:
            type: string
            format: date
      responses:
        '200':
          description: Trang kết quả tìm kiếm
```

Đây là ví dụ cấu trúc minh họa. Springdoc có thể thêm các parameter `page`, `size`, `sort` và response schema của `Page` theo cấu hình thực tế. Tên, description, required và schema cuối cùng cần được kiểm tra ở `/v3/api-docs`.

Điểm quan trọng là DTO filter được thể hiện thành nhiều parameter `in: query`, không phải một parameter duy nhất có schema object và cũng không phải `requestBody`.

## 6. Kiểu dữ liệu và quy tắc chuyển đổi query string

Query string luôn truyền dữ liệu dưới dạng văn bản. Spring chuyển đổi chuỗi sang kiểu Java dựa trên converter và formatter.

| Kiểu DTO | Ví dụ query | Lưu ý |
|---|---|---|
| `String` | `keyword=pen` | Có thể trim hoặc chuẩn hóa trong service nếu hợp đồng yêu cầu |
| `Long` | `categoryId=5` | Giá trị không phải số thường gây lỗi binding 400 |
| `BigDecimal` | `minPrice=12500.50` | Quy ước dấu thập phân phụ thuộc converter/locale; API thường nên dùng dạng số chuẩn với dấu chấm |
| `Boolean` | `available=true` | Nên thống nhất giá trị true/false |
| `Enum` | `status=ACTIVE` | Giá trị thường được chuyển theo tên enum; cần kiểm tra converter nếu dùng code riêng |
| `LocalDate` | `createdFrom=2026-01-01` | Dùng `@DateTimeFormat(iso = ISO.DATE)` hoặc pattern rõ ràng |
| `LocalDateTime` | `createdAt=2026-01-01T10:30:00` | Không mang offset/múi giờ |
| `List<Long>` | `categoryId=5&categoryId=8` | Cần thống nhất cách serialize danh sách |

Jackson `@JsonFormat` chủ yếu điều khiển JSON serialization/deserialization; nó không thay thế formatter của Spring MVC khi bind query parameter. Với query date/time, dùng `@DateTimeFormat` hoặc converter/formatter của Spring. Đây là khác biệt quan trọng khi cùng một DTO được dùng nhầm cho cả JSON body và query string.

### Enum filter

Ví dụ:

```java
public enum ProductStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
```

Client gửi `status=ACTIVE`. Nếu API dùng code như `active` hoặc `archived`, hãy đăng ký converter `String -> ProductStatus` và mô tả đúng giá trị được chấp nhận trong OpenAPI. Đừng chỉ dùng `@JsonValue` rồi giả định Spring MVC query binding sẽ tự dùng Jackson serializer; query conversion và JSON serialization là hai cơ chế riêng.

## 7. Danh sách và cách serialize nhiều giá trị

Một filter có thể nhận nhiều giá trị, ví dụ nhiều trạng thái hoặc nhiều mã danh mục. OpenAPI mô tả cách serialize array bằng `style` và `explode`.

### Lặp lại cùng một key

Với `style: form` và `explode: true`, client gửi:

```http
GET /api/products?status=ACTIVE&status=DRAFT
```

OpenAPI:

```yaml
- name: status
  in: query
  style: form
  explode: true
  schema:
    type: array
    items:
      type: string
      enum: [DRAFT, ACTIVE, ARCHIVED]
```

### Dạng phân tách bằng dấu phẩy

Với `style: form` và `explode: false`, client có thể gửi:

```http
GET /api/products?status=ACTIVE,DRAFT
```

Hai dạng này không tự động tương đương ở mọi stack. Spring MVC có thể chuyển chuỗi phân tách bằng dấu phẩy thành collection qua converter mặc định trong nhiều trường hợp, nhưng cần kiểm tra chính xác khi dùng custom converter, enum hoặc giá trị chứa dấu phẩy. Hãy chọn một quy ước duy nhất cho API, khai báo đúng `style`/`explode` và test request thực tế.

Với `List<String>`, nếu giá trị có thể chứa dấu phẩy hoặc ký tự đặc biệt, dạng lặp key thường dễ hiểu và tránh nhập nhằng hơn. Các ký tự trong URL vẫn cần percent-encoding đúng chuẩn.

## 8. Khoảng giá, khoảng ngày và quy tắc kết hợp filter

DTO chỉ nhận giá trị; service cần định nghĩa cách các giá trị phối hợp.

Ví dụ khoảng giá:

- Chỉ có `minPrice`: giá phải lớn hơn hoặc bằng mức tối thiểu.
- Chỉ có `maxPrice`: giá phải nhỏ hơn hoặc bằng mức tối đa.
- Có cả hai: giá nằm trong khoảng đóng `[minPrice, maxPrice]`.
- `minPrice > maxPrice`: request không hợp lệ.

Khoảng ngày cũng cần quy định rõ. Nếu `createdFrom` và `createdTo` là ngày bao gồm cả hai đầu, truy vấn timestamp thường cần chuyển thành khoảng từ đầu ngày `createdFrom` tới trước đầu ngày kế tiếp của `createdTo`, theo múi giờ nghiệp vụ đã chọn. Tránh dùng đầu ngày `createdTo` làm mốc kết thúc bao gồm, vì cách đó có thể bỏ sót các bản ghi trong phần còn lại của ngày kết thúc.

Để kiểm tra quan hệ giữa nhiều field, nên tạo class-level constraint, ví dụ `@ValidProductFilter`, rồi viết `ConstraintValidator<ValidProductFilter, ProductFilter>` để so sánh `minPrice` với `maxPrice` và `createdFrom` với `createdTo`. Cách này giữ quy tắc liên trường ở một nơi và tránh tạo các getter boolean công khai như `isPriceRangeValid()` chỉ để dùng `@AssertTrue`; getter kiểu đó có thể bị introspection xem như một property bổ sung khi springdoc phân tích query DTO.

`@Schema(minimum = ...)` hoặc `maximum` chỉ mô tả ràng buộc trong OpenAPI; chúng không thay thế Bean Validation. Ngược lại, `@Min`, `@DecimalMin` hoặc custom validator mới thực thi kiểm tra ở runtime. Có thể kết hợp cả hai để schema và runtime thống nhất.

## 9. Giá trị mặc định, optional và required

Query filter thường là optional: client chỉ gửi những điều kiện muốn áp dụng. Cần phân biệt:

- Không gửi parameter: không áp dụng điều kiện đó hoặc dùng giá trị mặc định.
- Gửi parameter rỗng: ví dụ `keyword=`; hành vi cần được quy định rõ, có thể xem như chuỗi rỗng hoặc bỏ qua.
- Gửi giá trị sai định dạng: Spring không chuyển đổi được và thường trả 400.
- Gửi giá trị ngoài miền cho phép: validation trả lỗi 400.

Ví dụ DTO có mặc định:

```java
public class ProductFilter {
    private String keyword;
    private Integer page = 0;
    private Integer size = 20;

    // getters và setters
}
```

Tuy nhiên, nếu controller dùng `Pageable` cùng `@PageableDefault`, nên để giá trị mặc định phân trang ở một nơi để tránh `page`/`size` trong DTO mâu thuẫn với `Pageable`.

OpenAPI parameter có `required: false` khi client không bắt buộc phải gửi. Query parameter thông thường không required trừ khi khai báo bắt buộc. Đối với DTO, springdoc suy luận từ metadata và cấu hình; hãy kiểm tra `required` trong tài liệu sinh ra thay vì giả định mọi field Java không null đều trở thành required.

## 10. Validation và xử lý lỗi cho query DTO

Có thể áp dụng constraint trực tiếp lên field:

```java
public class ProductFilter {

    @Size(max = 100)
    private String keyword;

    @Min(1)
    private Long categoryId;

    @DecimalMin("0.0")
    private BigDecimal minPrice;

    @DecimalMin("0.0")
    private BigDecimal maxPrice;

    @Min(0)
    private Integer page = 0;

    @Min(1)
    @Max(100)
    private Integer size = 20;

    // getters và setters
}
```

Controller đánh dấu `@Valid` để kích hoạt validation cho model attribute. Nếu cần xử lý lỗi ngay trong method, có thể đặt `BindingResult` ngay sau tham số DTO:

```java
@GetMapping
Page<ProductResponse> search(
    @Valid @ModelAttribute @ParameterObject ProductFilter filter,
    BindingResult bindingResult,
    @ParameterObject Pageable pageable
) {
    if (bindingResult.hasErrors()) {
        throw new InvalidProductFilterException(bindingResult.getAllErrors());
    }
    return productService.search(filter, pageable);
}
```

Nếu không khai báo `BindingResult` ngay sau model attribute, Spring có thể ném exception binding/validation để exception handler xử lý. Cần kiểm tra loại exception cụ thể theo phiên bản Spring MVC và cách khai báo method. Lỗi chuyển đổi kiểu, ví dụ `categoryId=abc`, cũng có thể xuất hiện trong `BindingResult` hoặc exception binding.

Trong OpenAPI, các giới hạn như `maximum`, `minLength` và `format` giúp client hiểu miền giá trị. Tuy nhiên, các quy tắc liên trường như `minPrice <= maxPrice` thường cần description/example hoặc schema phức tạp hơn; không phải mọi custom validator đều tự chuyển thành constraint OpenAPI.

## 11. Mô tả parameter chi tiết bằng Swagger annotations

`@Schema` phù hợp để mô tả property của DTO. Nếu cần kiểm soát metadata ở mức Parameter Object như tên, `in`, `style`, `explode`, `allowEmptyValue`, `deprecated` hoặc `example`, có thể dùng `@Parameter` ở vị trí được Swagger Core hỗ trợ hoặc khai báo qua OpenAPI customizer.

Ví dụ mô tả một query parameter độc lập:

```java
@GetMapping("/api/products")
List<ProductResponse> search(
    @Parameter(
        name = "keyword",
        description = "Từ khóa tìm theo tên hoặc mã sản phẩm",
        example = "pen",
        in = ParameterIn.QUERY
    )
    @RequestParam(required = false) String keyword
) {
    return productService.search(keyword);
}
```

Khi dùng `@ParameterObject`, metadata property thường được lấy từ `@Schema` và các annotation hỗ trợ trên DTO. Nếu một property cần quy tắc serialize array riêng, hãy kiểm tra annotation được springdoc nhận diện trong phiên bản đang dùng. Có thể mô tả chính xác parameter sau khi tạo bằng `OpenApiCustomizer` nếu annotation trên DTO không đủ biểu đạt.

Không khai báo cùng một query parameter hai lần, vừa qua `@ParameterObject` vừa qua `@RequestParam` riêng, vì tài liệu có thể tạo duplicate parameter hoặc runtime nhận hai nguồn giá trị khác nhau.

## 12. Giới hạn với DTO lồng nhau

Spring MVC hỗ trợ binding property lồng nhau theo quy ước property path trong một số kiểu model attribute, ví dụ:

```http
GET /api/products?priceRange.min=10000&priceRange.max=50000
```

Tuy nhiên, `@ParameterObject` của springdoc có giới hạn với nested parameter objects; không nên giả định một DTO lồng nhau sẽ tự động được trải thành các query parameter theo đúng cấu trúc mong muốn trong mọi phiên bản.

Có ba cách xử lý:

1. **Làm phẳng DTO:** dùng `minPrice`, `maxPrice`, `categoryId` ở cấp cao nhất. Đây thường là cách đơn giản nhất cho API filter.
2. **Khai báo parameter tường minh:** dùng `@RequestParam`/`@Parameter` cho từng key khi cần giữ tên như `priceRange.min`.
3. **Tùy chỉnh OpenAPI:** dùng `OpenApiCustomizer` để thêm parameter đúng tên, schema, style và explode, sau đó xác nhận Spring MVC thực sự bind đúng key đó.

Ví dụ DTO phẳng:

```java
public class ProductFilter {
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
    private Long categoryId;
}
```

DTO phẳng giúp URL ngắn, schema dễ đọc và client generator dễ tạo model. Nếu hợp đồng yêu cầu object query có cấu trúc sâu, cần kiểm tra cả khả năng serialize của client lẫn binding của Spring thay vì chỉ sửa OpenAPI.

## 13. Sort và phân trang an toàn

`Pageable` thường hỗ trợ các query parameter `page`, `size` và `sort`. Ví dụ:

```http
GET /api/products?page=0&size=20&sort=name,asc&sort=createdAt,desc
```

Spring Data có thể nhận nhiều điều kiện sort. Nhưng không nên cho client truyền tùy ý tên cột SQL hoặc biểu thức truy vấn. Chỉ cho phép sort theo danh sách property API đã công bố, rồi ánh xạ sang property persistence tương ứng.

Ví dụ allowlist:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "name",
    "sellingPrice",
    "createdAt"
);

private Sort validateSort(Sort requestedSort) {
    for (Sort.Order order : requestedSort) {
        if (!ALLOWED_SORTS.contains(order.getProperty())) {
            throw new InvalidSortFieldException(order.getProperty());
        }
    }
    return requestedSort;
}
```

Trong thực tế, có thể ánh xạ tên API như `price` sang entity property `sellingPrice`, thay vì để client biết tên field persistence. Cũng cần giới hạn `size` để tránh client yêu cầu hàng trăm nghìn bản ghi trong một request.

Nếu dùng DTO filter và `Pageable` cùng lúc, tài liệu phải tránh khai báo trùng `page`, `size`, `sort`. Hãy chọn một nguồn sở hữu các parameter phân trang.

## 14. Ví dụ OpenAPI đầy đủ cho bộ lọc

Một operation tìm kiếm có thể được mô tả như sau:

```yaml
paths:
  /api/products:
    get:
      summary: Tìm kiếm sản phẩm
      description: Chỉ áp dụng các điều kiện lọc được gửi trong query string.
      parameters:
        - name: keyword
          in: query
          required: false
          description: Từ khóa tìm trong tên hoặc mã sản phẩm
          schema:
            type: string
            maxLength: 100
        - name: status
          in: query
          required: false
          description: Lọc theo một hoặc nhiều trạng thái
          style: form
          explode: true
          schema:
            type: array
            items:
              type: string
              enum: [DRAFT, ACTIVE, ARCHIVED]
        - name: categoryId
          in: query
          schema:
            type: integer
            format: int64
            minimum: 1
        - name: minPrice
          in: query
          schema:
            type: number
            minimum: 0
        - name: maxPrice
          in: query
          schema:
            type: number
            minimum: 0
        - name: createdFrom
          in: query
          description: Ngày bắt đầu, bao gồm ngày này
          schema:
            type: string
            format: date
        - name: createdTo
          in: query
          description: Ngày kết thúc, bao gồm ngày này
          schema:
            type: string
            format: date
        - name: page
          in: query
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: sort
          in: query
          description: Property và hướng sắp xếp; chỉ hỗ trợ các field được API công bố
          schema:
            type: array
            items:
              type: string
          style: form
          explode: true
      responses:
        '200':
          description: Trang sản phẩm phù hợp với bộ lọc
        '400':
          description: Query parameter sai định dạng hoặc vi phạm validation
```

Ví dụ này thể hiện hợp đồng mong muốn. `Pageable` của Spring Data có thể tạo schema response page và cách mô tả sort khác theo cấu hình springdoc. Nếu cần định dạng response phân trang ổn định giữa các phiên bản, hãy dùng response DTO riêng thay vì phụ thuộc trực tiếp vào cấu trúc nội bộ của `Page`.

## 15. Kiểm tra tài liệu và binding runtime

Sau khi chạy ứng dụng, mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`. Tìm `GET /api/products` và kiểm tra:

1. Mỗi property filter xuất hiện thành một parameter `in: query`.
2. Tên parameter đúng với tên client cần gửi.
3. `required`, `description`, `example`, `format`, `enum`, `minimum` và `maximum` đúng.
4. Array có `style` và `explode` phù hợp với cách client gửi.
5. Không có query parameter trùng lặp.
6. `page`, `size`, `sort` có default và giới hạn đúng.
7. Không có property nội bộ của entity hoặc DTO không thuộc hợp đồng.

Sau đó thử request thực tế:

```bash
curl -G 'http://localhost:8080/api/products' \
  --data-urlencode 'keyword=blue pen' \
  --data-urlencode 'status=ACTIVE' \
  --data-urlencode 'status=DRAFT' \
  --data-urlencode 'minPrice=10000' \
  --data-urlencode 'maxPrice=50000' \
  --data-urlencode 'createdFrom=2026-01-01' \
  --data-urlencode 'createdTo=2026-12-31' \
  --data-urlencode 'page=0' \
  --data-urlencode 'size=20'
```

Kiểm tra các trường hợp:

- Không gửi filter nào: API trả danh sách mặc định.
- Gửi một điều kiện: chỉ điều kiện đó được áp dụng.
- Gửi nhiều điều kiện: các điều kiện kết hợp theo logic đã công bố, thường là AND giữa nhóm filter và OR giữa các giá trị cùng một filter.
- Gửi enum không tồn tại, số không hợp lệ hoặc ngày sai định dạng: nhận lỗi 400 theo cấu trúc lỗi chuẩn.
- Gửi `minPrice > maxPrice` hoặc `createdFrom > createdTo`: validation liên trường từ chối request.
- Gửi `size` vượt giới hạn hoặc sort field không được hỗ trợ: server từ chối theo chính sách API.

Swagger UI chỉ cho biết parameter mà tài liệu mô tả. Hãy thử gọi endpoint từ UI hoặc curl và xác nhận Spring bind đúng giá trị, service áp dụng đúng logic, response phân trang đúng.

## 16. Kiểm thử query DTO bằng MockMvc

Ví dụ kiểm tra binding nhiều query parameter:

```java
@WebMvcTest(ProductQueryController.class)
class ProductQueryControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ProductService productService;

    @Test
    void bindsRepeatedStatusAndDateFilters() throws Exception {
        given(productService.search(any(ProductFilter.class), any(Pageable.class)))
            .willReturn(Page.empty());

        mockMvc.perform(get("/api/products")
                .param("status", "ACTIVE", "DRAFT")
                .param("createdFrom", "2026-01-01")
                .param("createdTo", "2026-12-31")
                .param("page", "0")
                .param("size", "20"))
            .andExpect(status().isOk());

        then(productService).should().search(
            argThat(filter -> filter.getStatus().equals(
                List.of(ProductStatus.ACTIVE, ProductStatus.DRAFT)
            ) && filter.getCreatedFrom().equals(LocalDate.of(2026, 1, 1))),
            any(Pageable.class)
        );
    }
}
```

Đây là ví dụ kiểm thử định hướng; cần cấu hình mock, response page và matcher theo service thực tế. Nếu dùng Spring Boot phiên bản cũ, thay `@MockitoBean` bằng annotation mock bean được phiên bản đó hỗ trợ.

Kiểm tra query sai kiểu:

```java
mockMvc.perform(get("/api/products").param("categoryId", "not-a-number"))
    .andExpect(status().isBadRequest());
```

Kiểm tra OpenAPI parameter:

```java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/products'].get.parameters[?(@.name == 'keyword' && @.in == 'query')]"
    ).exists())
    .andExpect(jsonPath(
        "$.paths['/api/products'].get.parameters[?(@.name == 'createdFrom')]"
    ).exists());
```

JSONPath filter expression có thể khác nhau giữa implementation và phiên bản test library. Nếu matcher không hỗ trợ biểu thức đó, đọc mảng `parameters` rồi assert theo `name` và `in`. Điều cần kiểm tra là tài liệu sinh ra có các parameter riêng, đúng tên và schema.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| DTO không được bind từ query string | Thiếu `@ModelAttribute`, property không có setter/constructor binding phù hợp hoặc tên query sai | Kiểm tra cách binding và JavaBean property |
| Swagger UI hiển thị một object thay vì các query parameter riêng | Thiếu `@ParameterObject` hoặc phiên bản springdoc không nhận diện DTO | Thêm annotation, kiểm tra `/v3/api-docs` và version tương thích |
| DTO được bind đúng nhưng tài liệu thiếu field | Property visibility/annotation hoặc model converter không nhận diện | Kiểm tra getter, `@Schema` và cấu hình springdoc |
| Ngày hợp lệ trong JSON nhưng query date lỗi | Dùng `@JsonFormat` thay cho Spring formatter | Dùng `@DateTimeFormat` hoặc Converter/Formatter |
| Enum code không được bind | Query conversion không dùng `@JsonValue` của Jackson | Đăng ký `Converter<String, Enum>` và mô tả đúng enum |
| Danh sách không nhận đủ giá trị | Client gửi CSV nhưng server mong repeated key, hoặc ngược lại | Đồng bộ `style`, `explode` và cách gửi query |
| Nested DTO không hiện đúng trong OpenAPI | `@ParameterObject` có giới hạn với nested parameter object | Làm phẳng DTO hoặc khai báo parameter tường minh/customizer |
| Query parameter bị lặp trong tài liệu | Cùng field được khai báo qua DTO và `@RequestParam` riêng | Chỉ chọn một nguồn khai báo |
| Client sort theo field nội bộ | Sort parameter công bố trực tiếp tên entity property | Dùng allowlist và ánh xạ tên API sang persistence |
| Tài liệu ghi giới hạn nhưng runtime không từ chối | Chỉ có `@Schema` mà thiếu validation | Bổ sung Bean Validation hoặc logic kiểm tra |

## 18. Quy trình thiết kế filter DTO

Khi thêm endpoint tìm kiếm, thực hiện theo thứ tự:

1. Liệt kê điều kiện lọc mà client thực sự cần; tránh phơi bày trực tiếp field entity.
2. Tạo DTO query với kiểu Java phù hợp, tên property ổn định và getter/setter rõ ràng.
3. Dùng `@ModelAttribute` để Spring bind query string và `@ParameterObject` để springdoc tạo parameter riêng.
4. Bổ sung `@DateTimeFormat`, converter enum hoặc formatter cho kiểu query đặc biệt.
5. Dùng Bean Validation cho từng field và quy tắc liên trường.
6. Mô tả property bằng `@Schema`; kiểm soát `style`/`explode` cho array.
7. Tách phân trang/sort bằng `Pageable` hoặc DTO riêng, tránh khai báo trùng.
8. Giới hạn sort field và kích thước trang theo allowlist/chính sách API.
9. Kiểm tra `/v3/api-docs`, Swagger UI và request HTTP thực tế.
10. Kiểm thử filter rỗng, từng điều kiện, kết hợp nhiều điều kiện và dữ liệu sai định dạng.

Filter DTO giúp controller gọn, validation tập trung và mô tả OpenAPI nhất quán. Spring MVC chịu trách nhiệm binding query string vào object; `@ParameterObject` giúp springdoc biểu diễn từng property thành query parameter; `@Schema` mô tả miền dữ liệu. Khi ba phần được cấu hình và kiểm tra đồng bộ, client có thể sử dụng bộ lọc đúng cách mà không cần biết cấu trúc entity hoặc truy vấn phía server.

## 19. Tài liệu tham khảo

- [Spring Framework – Model Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding request parameter vào model attribute.
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `ConversionService`, Formatter và chuyển đổi kiểu dữ liệu web.
- [Spring Data – Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html): tích hợp `Pageable`, `Sort` và web binding.
- [Springdoc OpenAPI – FAQ](https://springdoc.org/#faq): sử dụng `@ParameterObject` cho POJO và Pageable.
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object): `in`, `style`, `explode`, `schema` và ví dụ của query parameter.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): `@Parameter`, `@Schema` và metadata cho OpenAPI.
