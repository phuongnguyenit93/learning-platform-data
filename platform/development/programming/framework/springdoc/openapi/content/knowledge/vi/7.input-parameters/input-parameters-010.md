# Đối tượng truy vấn và @ParameterObject

Một endpoint tìm kiếm thường nhận nhiều query parameter có liên quan: từ khóa, trạng thái, khoảng ngày, mức giá, số trang và kích thước trang. Nếu khai báo từng tham số trong chữ ký controller, method có thể trở nên dài và khó mở rộng. Spring MVC cho phép gom các giá trị này vào một đối tượng truy vấn (query object hoặc model attribute). Với springdoc-openapi, annotation **@ParameterObject** giúp mô tả các thuộc tính của đối tượng đó thành những query parameter riêng trong đặc tả OpenAPI.

Bài này giải thích vai trò của model attribute trong Spring MVC, cách @ParameterObject tạo metadata cho OpenAPI, cách kết hợp với validation, định dạng ngày và Pageable, cùng những giới hạn cần lưu ý khi thiết kế query object.

## 1. Vì sao nên gom query parameter thành đối tượng?

Giả sử API tìm kiếm đơn hàng nhận các tham số:

- keyword: từ khóa tìm theo mã hoặc tên người mua.
- status: trạng thái đơn hàng.
- createdFrom và createdTo: khoảng ngày tạo.
- minTotal: tổng tiền tối thiểu.
- page, size và sort: phân trang và sắp xếp.

Nếu khai báo từng tham số riêng, controller có thể có chữ ký dài:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @RequestParam(required = false) String keyword,
    @RequestParam(required = false) OrderStatus status,
    @RequestParam(required = false) LocalDate createdFrom,
    @RequestParam(required = false) LocalDate createdTo,
    @RequestParam(required = false) BigDecimal minTotal,
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size
) {
    // Tìm kiếm đơn hàng.
    return Page.empty();
}
~~~

Khi số bộ lọc tăng, method khó đọc và khó tái sử dụng. Có thể gom các điều kiện tìm kiếm vào một lớp:

~~~java
public class OrderSearchCriteria {
    private String keyword;
    private OrderStatus status;
    private LocalDate createdFrom;
    private LocalDate createdTo;
    private BigDecimal minTotal;

    // Constructor mặc định, getters và setters.
}
~~~

Controller nhận một đối tượng thay cho nhiều tham số:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @ModelAttribute OrderSearchCriteria criteria
) {
    return orderService.search(criteria);
}
~~~

Trong Spring MVC, @ModelAttribute yêu cầu Spring bind dữ liệu request vào các thuộc tính của đối tượng. Với request GET, các query parameter như keyword, status và createdFrom được ánh xạ vào các property tương ứng. Đối tượng này thường được gọi là query object, filter object hoặc search criteria.

Việc gom tham số làm chữ ký controller gọn hơn, cho phép tái sử dụng cùng kiểu filter ở nhiều endpoint và tập trung logic kiểm tra dữ liệu vào một lớp.

## 2. @ModelAttribute và @ParameterObject có vai trò khác nhau

Hai annotation thường xuất hiện cùng nhau nhưng phục vụ hai công việc khác nhau:

| Annotation | Vai trò |
|---|---|
| @ModelAttribute | Spring MVC bind dữ liệu request vào object và đưa object vào model của controller |
| @ParameterObject | Springdoc phân tích thuộc tính của object để tạo các query parameter trong OpenAPI |

Ví dụ:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @ParameterObject
    @ModelAttribute
    OrderSearchCriteria criteria
) {
    return orderService.search(criteria);
}
~~~

Khi client gửi:

~~~http
GET /api/orders?keyword=keyboard&status=PAID&minTotal=100000
~~~

Spring MVC bind các giá trị vào OrderSearchCriteria. Springdoc đọc @ParameterObject và mô tả keyword, status, minTotal thành những parameter riêng trong tài liệu OpenAPI.

**@ParameterObject không tự thực hiện binding dữ liệu và không thay đổi hành vi HTTP.** Nó là chỉ dẫn cho quá trình tạo tài liệu. Nếu bỏ @ModelAttribute trong trường hợp Spring MVC cần binding model attribute tường minh, hãy hiểu rõ quy tắc binding mặc định của Spring trước khi dựa vào chữ ký rút gọn.

Trong nhiều controller Spring MVC, một tham số kiểu object không có annotation đặc biệt có thể được suy ra là model attribute. Dù vậy, dùng @ModelAttribute tường minh giúp người đọc thấy rõ ý định binding. Để OpenAPI thể hiện object thành các query parameter, thêm @ParameterObject.

## 3. Khai báo query object

Một query object thông thường là JavaBean có constructor mặc định và các getter/setter. Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Size;
import org.springframework.format.annotation.DateTimeFormat;

import java.math.BigDecimal;
import java.time.LocalDate;

public class OrderSearchCriteria {

    @Parameter(
        description = "Tìm theo mã đơn hàng hoặc tên người mua",
        example = "ORD-2026"
    )
    @Size(max = 100)
    private String keyword;

    @Parameter(
        description = "Lọc theo trạng thái đơn hàng",
        example = "PAID"
    )
    private OrderStatus status;

    @Parameter(
        description = "Ngày tạo từ, bao gồm ngày này",
        example = "2026-01-01"
    )
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdFrom;

    @Parameter(
        description = "Ngày tạo đến, bao gồm ngày này",
        example = "2026-01-31"
    )
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdTo;

    @Parameter(
        description = "Tổng tiền tối thiểu",
        example = "100000"
    )
    @DecimalMin("0.00")
    private BigDecimal minTotal;

    public OrderSearchCriteria() {
    }

    // Bổ sung getters và setters cho các thuộc tính.
}
~~~

Các thuộc tính được Spring bind theo tên query parameter. Ví dụ, request có keyword=ORD-2026 sẽ gán giá trị đó vào property keyword.

Một số nguyên tắc thiết kế:

- Dùng kiểu wrapper như Integer, Boolean hoặc BigDecimal khi cần phân biệt tham số bị bỏ qua với giá trị 0 hoặc false.
- Chọn kiểu Java phù hợp với dữ liệu: LocalDate cho ngày, Instant cho thời điểm tuyệt đối, enum cho tập trạng thái cố định.
- Giữ query object tập trung vào điều kiện tìm kiếm; tránh đưa entity persistence hoặc service vào lớp này.
- Đặt giới hạn kích thước và giá trị để tránh request không hợp lệ hoặc truy vấn quá tốn tài nguyên.
- Dùng constructor mặc định và getter/setter theo cơ chế binding JavaBean phổ biến của Spring MVC.

Ví dụ enum:

~~~java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    PAID,
    CANCELLED
}
~~~

OpenAPI có thể biểu diễn enum thành danh sách giá trị hợp lệ. Khi đó, người dùng Swagger UI có thể nhìn thấy các trạng thái có thể chọn.

## 4. Dùng @ParameterObject trong controller

Sau khi có query object, gắn @ParameterObject lên tham số controller:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders")
    @Operation(
        summary = "Tìm kiếm đơn hàng",
        description = "Lọc đơn hàng theo từ khóa, trạng thái, ngày tạo và tổng tiền."
    )
    public Page<OrderResponse> searchOrders(
        @ParameterObject @ModelAttribute OrderSearchCriteria criteria
    ) {
        return orderService.search(criteria);
    }
}
~~~

Trong ví dụ này:

- @ModelAttribute giúp Spring bind query string vào criteria.
- @ParameterObject yêu cầu springdoc mô tả các property của criteria như query parameter.
- @Operation cung cấp summary và description cho operation.
- OrderService thực hiện truy vấn nghiệp vụ.

Với springdoc-openapi v2, import @ParameterObject từ package org.springdoc.core.annotations. Nếu dự án đang dùng springdoc v1, package annotation có thể khác; hãy kiểm tra tài liệu migration của đúng phiên bản thay vì sao chép import từ một dòng major khác.

## 5. OpenAPI JSON được sinh ra như thế nào?

Giả sử controller nhận OrderSearchCriteria như trên, phần OpenAPI tương ứng có thể được biểu diễn rút gọn như sau:

~~~json
{
  "paths": {
    "/api/orders": {
      "get": {
        "summary": "Tìm kiếm đơn hàng",
        "parameters": [
          {
            "name": "keyword",
            "in": "query",
            "required": false,
            "description": "Tìm theo mã đơn hàng hoặc tên người mua",
            "schema": {
              "type": "string",
              "maxLength": 100
            }
          },
          {
            "name": "status",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "enum": [
                "PENDING",
                "CONFIRMED",
                "PAID",
                "CANCELLED"
              ]
            }
          },
          {
            "name": "createdFrom",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "format": "date"
            }
          },
          {
            "name": "minTotal",
            "in": "query",
            "required": false,
            "schema": {
              "type": "number",
              "minimum": 0
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Danh sách đơn hàng"
          }
        }
      }
    }
  }
}
~~~

Điểm quan trọng là các property xuất hiện trong mảng parameters, mỗi property có:

- name: tên query parameter.
- in: vị trí truyền dữ liệu, ở đây là query.
- required: tham số có bắt buộc hay không.
- description: nội dung mô tả nếu được khai báo.
- schema: kiểu dữ liệu, enum, format và các ràng buộc có thể suy ra.

Query object không nhất thiết xuất hiện dưới dạng một schema request body. Với GET endpoint, các thuộc tính được biểu diễn thành query parameter riêng để client truyền qua URL.

## 6. Mô tả từng thuộc tính bằng @Parameter

Có thể đặt annotation @Parameter lên field hoặc property để bổ sung mô tả, ví dụ, tên hiển thị và trạng thái required cho tài liệu.

~~~java
public class ProductSearchCriteria {

    @Parameter(
        name = "q",
        description = "Từ khóa tìm tên hoặc SKU sản phẩm",
        example = "wireless mouse"
    )
    private String keyword;

    @Parameter(
        description = "Chỉ lấy sản phẩm còn hàng",
        example = "true"
    )
    private Boolean inStock;

    @Parameter(
        description = "Số lượng kết quả tối đa",
        example = "50"
    )
    private Integer limit;

    // Constructor, getters và setters.
}
~~~

Nếu đổi tên parameter bằng thuộc tính name, hãy kiểm tra binding thực tế. Metadata OpenAPI có thể trình bày tên khác với property Java, trong khi Spring MVC vẫn bind theo tên property trừ khi bạn cấu hình cơ chế binding tương ứng. Không thay đổi tên tài liệu mà không bảo đảm request gửi theo tên đó được ứng dụng tiếp nhận.

Có thể khai báo required trong metadata:

~~~java
@Parameter(
    description = "Mã cửa hàng bắt buộc",
    required = true,
    example = "HCM-01"
)
private String storeCode;
~~~

Tuy nhiên, required trong OpenAPI là hợp đồng mô tả. Để ứng dụng thực sự từ chối khi thiếu dữ liệu, cần kết hợp validation và kiểm tra ở tầng xử lý request.

## 7. Kết hợp Bean Validation

Query object có thể dùng Bean Validation để giới hạn dữ liệu đầu vào. Ví dụ:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;

public class ProductSearchCriteria {

    @Size(max = 80)
    private String keyword;

    @Min(0)
    private Integer minPrice;

    @Min(1)
    @Max(100)
    private Integer limit = 20;

    // Getters và setters.
}
~~~

Kích hoạt validation trên tham số controller:

~~~java
@GetMapping("/api/products")
public List<ProductResponse> searchProducts(
    @Valid @ParameterObject @ModelAttribute ProductSearchCriteria criteria
) {
    return productService.search(criteria);
}
~~~

Để validation hoạt động, dự án cần có Bean Validation implementation, thường được thêm qua starter validation của Spring Boot. Nếu validation không chạy, kiểm tra dependency validation, annotation @Valid và cách controller được cấu hình.

Các annotation phổ biến:

| Annotation | Tác dụng |
|---|---|
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi phải có ít nhất một ký tự không phải khoảng trắng |
| @Size | Giới hạn độ dài chuỗi hoặc kích thước collection |
| @Min / @Max | Giới hạn số nguyên hoặc giá trị số |
| @DecimalMin / @DecimalMax | Giới hạn số thập phân |
| @Positive / @PositiveOrZero | Yêu cầu số dương hoặc không âm |
| @Pattern | Kiểm tra chuỗi theo regular expression |

Không phải mọi annotation validation đều tự động trở thành ràng buộc OpenAPI theo cùng một cách ở mọi phiên bản. Hãy kiểm tra JSON được sinh ra và xác minh cả hành vi runtime bằng request hợp lệ lẫn request không hợp lệ.

## 8. Định dạng ngày, thời gian và enum

Query parameter được truyền qua URL dưới dạng chuỗi. Spring cần chuyển chuỗi đó sang kiểu Java tương ứng. Đối với ngày, nên thống nhất định dạng ISO để client dễ sử dụng.

Ví dụ:

~~~java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate createdFrom;

@DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
private LocalDateTime createdAtFrom;
~~~

Request mẫu:

~~~http
GET /api/orders?createdFrom=2026-01-01&createdAtFrom=2026-01-01T08:30:00
~~~

LocalDate biểu diễn ngày lịch, không chứa múi giờ. LocalDateTime biểu diễn ngày và giờ nhưng không gắn offset hoặc timezone. Nếu API cần thời điểm tuyệt đối giữa nhiều múi giờ, cân nhắc Instant hoặc OffsetDateTime và mô tả rõ định dạng, quy ước UTC/offset trong hợp đồng.

Enum giúp giới hạn giá trị đầu vào:

~~~java
public enum PaymentStatus {
    PENDING,
    SUCCESS,
    FAILED,
    REFUNDED
}
~~~

Nếu client gửi giá trị không tồn tại trong enum, Spring có thể trả lỗi chuyển đổi kiểu. Hãy mô tả các giá trị hợp lệ và chuẩn hóa chữ hoa/chữ thường theo quy ước của API.

## 9. Dùng @ParameterObject với Pageable

Các API danh sách thường cần phân trang và sắp xếp. Spring Data cung cấp Pageable để gom page, size và sort vào một đối tượng.

Ví dụ:

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
    @ParameterObject @ModelAttribute OrderSearchCriteria criteria,
    @ParameterObject
    @PageableDefault(
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.search(criteria, pageable);
}
~~~

Với springdoc, Pageable có thể được mô tả thành các query parameter riêng như:

| Parameter | Ý nghĩa | Ví dụ |
|---|---|---|
| page | Số trang, thường bắt đầu từ 0 | page=0 |
| size | Số phần tử mỗi trang | size=20 |
| sort | Thuộc tính và hướng sắp xếp | sort=createdAt,desc |

Request kết hợp filter và pagination:

~~~http
GET /api/orders?keyword=ORD&status=PAID&page=0&size=20&sort=createdAt,desc
~~~

@PageableDefault định nghĩa giá trị mặc định cho Pageable. Hãy bảo đảm giới hạn kích thước trang trong ứng dụng để client không yêu cầu một page quá lớn. Cấu hình Spring Data Web và springdoc có thể ảnh hưởng cách các tham số Pageable xuất hiện; kiểm tra đặc tả thực tế tại /v3/api-docs.

## 10. Khi nào không nên dùng @ParameterObject?

@ParameterObject phù hợp với một tập thuộc tính query phẳng, có tên rõ ràng. Không phải mọi cấu trúc object đều thích hợp để tự động chuyển thành query parameter.

Cần cân nhắc các trường hợp:

- **Object lồng nhau:** các query object lồng nhau không được hỗ trợ hoặc không được làm phẳng theo cách mà client mong đợi trong mọi trường hợp. Hãy làm phẳng DTO hoặc khai báo parameter tường minh.
- **Cấu trúc phức tạp:** filter có nhiều cấp, điều kiện AND/OR hoặc biểu thức tìm kiếm nên dùng request body trên endpoint phù hợp, hoặc một cú pháp query được thiết kế rõ ràng.
- **Tên thuộc tính trùng nhau:** nhiều parameter object có property cùng tên có thể tạo tên query parameter xung đột.
- **Dữ liệu lớn:** danh sách điều kiện phức tạp không phù hợp với URL dài; cân nhắc POST search với request body nếu thiết kế API cho phép.
- **Cần định dạng đặc biệt:** map, object tùy biến hoặc kiểu dữ liệu không có quy tắc chuyển đổi rõ ràng cần được mô tả tường minh.

Ví dụ về cấu trúc lồng nhau:

~~~java
public class OrderSearchCriteria {
    private CustomerFilter customer;
    private DateRange createdAt;
}
~~~

Không giả định springdoc sẽ tự tạo tên query như customer.name hoặc createdAt.from đúng với quy ước backend. Nếu API thực sự nhận các tên đó, cần thiết kế cách binding rõ ràng và xác minh tài liệu OpenAPI. Một lựa chọn đơn giản hơn là làm phẳng:

~~~java
public class OrderSearchCriteria {
    private String customerName;
    private LocalDate createdFrom;
    private LocalDate createdTo;

    // Getters và setters.
}
~~~

Khi filter phức tạp tới mức cần biểu diễn nhiều nhóm điều kiện, request body thường dễ hiểu và dễ mở rộng hơn query string.

## 11. Query object không phải request body

Một lỗi thiết kế thường gặp là nghĩ rằng khi controller nhận một object thì client phải gửi JSON. Điều đó phụ thuộc annotation và quy tắc binding của Spring.

| Cách khai báo | Vị trí dữ liệu | Cách client gửi |
|---|---|---|
| @ModelAttribute + @ParameterObject | Query parameter hoặc form fields theo binding của Spring MVC | URL query string |
| @RequestBody | HTTP request body | JSON, XML hoặc media type được khai báo |
| @PathVariable | Path segment | Một phần của URL |
| @RequestHeader | HTTP header | Header của request |

Ví dụ query object:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> search(
    @ParameterObject @ModelAttribute OrderSearchCriteria criteria
) {
    return orderService.search(criteria);
}
~~~

Client gọi:

~~~http
GET /api/orders?status=PAID&keyword=ORD
~~~

Ví dụ request body:

~~~java
@PostMapping("/api/orders/search")
public List<OrderResponse> advancedSearch(
    @RequestBody AdvancedOrderSearchRequest request
) {
    return orderService.advancedSearch(request);
}
~~~

Client gửi JSON:

~~~http
POST /api/orders/search
Content-Type: application/json

{
  "statuses": ["PAID", "CONFIRMED"],
  "created": {
    "from": "2026-01-01",
    "to": "2026-01-31"
  }
}
~~~

Hãy chọn cách truyền dữ liệu dựa trên ngữ nghĩa và độ phức tạp của API. GET với query parameter phù hợp cho bộ lọc đơn giản, có thể bookmark và cache theo URL. POST với request body có thể phù hợp cho truy vấn phức tạp hoặc payload lớn.

## 12. Kiểm tra kết quả trong OpenAPI JSON và Swagger UI

Sau khi khởi động ứng dụng, lưu đặc tả:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Dùng jq xem các parameter của operation:

~~~bash
jq '.paths["/api/orders"].get.parameters' openapi.json
~~~

Liệt kê tên và vị trí của parameter:

~~~bash
jq -r '
  .paths["/api/orders"].get.parameters[]
  | [.name, .in, (.required // false)]
  | @tsv
' openapi.json
~~~

Đối chiếu kết quả với query object:

- Tất cả property cần công bố đã xuất hiện chưa?
- Tên parameter có khớp tên mà controller nhận không?
- Tất cả parameter có in=query không?
- Enum có liệt kê đúng giá trị không?
- Ngày có format date hoặc date-time phù hợp không?
- Validation constraint có được thể hiện nếu thư viện hỗ trợ không?
- Pageable có page, size và sort như mong đợi không?

Mở Swagger UI và kiểm tra các trường được hiển thị. Nếu một property không xuất hiện, xem lại getter/setter, phạm vi truy cập, annotation @ParameterObject, kiểu dữ liệu và cấu hình springdoc. Sau đó gửi request thử để xác nhận Spring MVC thực sự bind đúng giá trị.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Query object không xuất hiện trong OpenAPI | Thiếu @ParameterObject hoặc controller parameter được phân tích theo một cơ chế khác. |
| Chỉ thấy một parameter object chung | springdoc chưa làm phẳng object theo cách mong muốn; kiểm tra annotation và kiểu tham số. |
| Một số property bị thiếu | Getter/setter không có, field không được introspect, property bị ẩn hoặc kiểu dữ liệu không được hỗ trợ. |
| Swagger UI hiển thị query parameter nhưng Spring nhận null | Tên parameter không khớp property hoặc binding model attribute không đúng. |
| Ngày bị lỗi chuyển đổi | Thiếu @DateTimeFormat hoặc chuỗi không đúng định dạng. |
| Validation không chạy | Thiếu Bean Validation implementation, @Valid hoặc cấu hình validation phù hợp. |
| Pageable không hiển thị đúng | Kiểm tra spring-data-commons, @ParameterObject, @PageableDefault và cấu hình springdoc. |
| Nested object không được biểu diễn đúng | Làm phẳng query DTO hoặc khai báo các parameter tường minh. |
| Hai filter tạo query parameter trùng tên | Đổi tên property hoặc gom các filter vào một object có namespace rõ ràng. |

Khi điều tra, hãy tách hai câu hỏi: tài liệu OpenAPI có mô tả parameter đúng không, và Spring MVC có bind request thành object đúng không. Một bên đúng không đồng nghĩa bên còn lại chắc chắn đúng.

## 14. Checklist thiết kế query object

- [ ] Query object chỉ chứa dữ liệu lọc, tìm kiếm hoặc phân trang cần thiết.
- [ ] Tên property rõ ràng và ổn định như tên query parameter.
- [ ] Có constructor và getter/setter phù hợp với cơ chế binding.
- [ ] Dùng kiểu Java phù hợp cho ngày, thời điểm, số và enum.
- [ ] Dùng @ParameterObject trên tham số cần được mô tả thành query parameter.
- [ ] Dùng @ModelAttribute rõ ràng khi muốn chỉ định Spring MVC binding.
- [ ] Mô tả parameter bằng @Parameter khi cần thêm description hoặc example.
- [ ] Áp dụng validation và giới hạn kích thước trang.
- [ ] Không giả định object lồng nhau tự động được làm phẳng đúng.
- [ ] Không trộn query object với request body.
- [ ] Đã kiểm tra parameters trong /v3/api-docs.
- [ ] Đã gửi request thực tế để xác minh binding và validation.

## 15. Nguồn tra cứu

- [springdoc-openapi – Documentation](https://springdoc.org/)
- [springdoc-openapi – FAQ](https://springdoc.org/#faq)
- [Spring Framework – Model Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Data – Web Support và Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)

@ParameterObject giúp springdoc biểu diễn một đối tượng query thành các parameter riêng trong OpenAPI. Spring MVC vẫn chịu trách nhiệm bind và kiểm tra dữ liệu thực tế. Khi thay đổi cấu trúc query object hoặc nâng cấp springdoc, hãy xác minh cả đặc tả JSON lẫn request runtime để bảo đảm client có thể gửi đúng dữ liệu.
