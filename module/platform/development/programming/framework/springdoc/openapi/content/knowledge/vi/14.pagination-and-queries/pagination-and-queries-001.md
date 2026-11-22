# Pageable, Sort và cách chúng được thể hiện trong tài liệu

Danh sách dữ liệu thường cần hỗ trợ phân trang và sắp xếp để client không phải tải toàn bộ bản ghi trong một lần gọi. Trong Spring Data, **Pageable** mô tả trang cần lấy, kích thước trang và thứ tự sắp xếp; **Sort** mô tả một hoặc nhiều tiêu chí sắp xếp. Spring MVC chuyển các query parameter thành những đối tượng này trước khi gọi controller.

Với springdoc-openapi, tham số Pageable có thể được trình bày thành các query parameter riêng để người dùng Swagger UI biết cách gọi API. Annotation **@ParameterObject** giúp Springdoc phân rã một tham số phức hợp thành các tham số truy vấn. Tài liệu cũng cần giải thích quy ước đánh số trang, kích thước mặc định, giới hạn tối đa, cú pháp sort và cấu trúc response phân trang.

## 1. Vì sao API danh sách cần phân trang?

Một endpoint trả về toàn bộ dữ liệu có thể hoạt động tốt khi số bản ghi ít. Khi dữ liệu tăng lên, response lớn làm tăng thời gian truy vấn, dung lượng truyền tải và bộ nhớ cần dùng ở cả server lẫn client.

Phân trang giúp:

- Giới hạn số bản ghi trong mỗi response.
- Giảm lượng dữ liệu truyền qua mạng.
- Cho phép client tải dữ liệu theo nhu cầu.
- Kết hợp sắp xếp để kết quả có thứ tự xác định.
- Hỗ trợ giao diện bảng, danh sách và màn hình quản trị.

Ví dụ endpoint:

~~~http
GET /api/v1/products?page=0&size=20&sort=createdAt,desc
~~~

Request này yêu cầu trang đầu tiên, tối đa 20 sản phẩm, sắp xếp theo thời điểm tạo giảm dần. Spring Data chuyển các query parameter thành một đối tượng Pageable để service hoặc repository sử dụng.

## 2. Pageable là gì?

Pageable là interface của Spring Data mô tả thông tin phân trang. Nó cung cấp các thông tin chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| pageNumber | Số thứ tự trang |
| pageSize | Số phần tử tối đa trong một trang |
| offset | Vị trí bản ghi bắt đầu |
| sort | Tiêu chí sắp xếp |

Với cách đánh số trang mặc định, trang đầu tiên có chỉ số 0. Nếu page=2 và size=20, offset tương ứng là 40, nghĩa là truy vấn bắt đầu từ phần tử thứ 41 theo thứ tự đã sắp xếp.

Trong Spring MVC, controller có thể nhận Pageable trực tiếp:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    public Page<ProductResponse> list(Pageable pageable) {
        return productService.findAll(pageable);
    }
}
~~~

Spring Data Web hỗ trợ phân giải Pageable từ query parameter. Trong cấu hình mặc định thường gặp, các tham số là:

- page: chỉ số trang, bắt đầu từ 0.
- size: số phần tử yêu cầu trong một trang.
- sort: thuộc tính và hướng sắp xếp; có thể xuất hiện nhiều lần.

Pageable là tham số truy vấn của HTTP request. Client không cần gửi một JSON object có tên pageNumber, pageSize hay sort trong request body.

## 3. @ParameterObject giúp Springdoc hiển thị Pageable

Nếu để Pageable như một tham số phức hợp mà không có metadata phù hợp, tài liệu có thể không thể hiện các query parameter theo cách người tích hợp mong đợi. Springdoc cung cấp @ParameterObject để phân rã object thành các tham số riêng:

~~~java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;

@GetMapping
public Page<ProductResponse> list(
    @ParameterObject Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

Với cấu hình Spring Data Web thông thường, Swagger UI có thể hiển thị các tham số page, size và sort. Người dùng có thể nhập trực tiếp giá trị query thay vì phải tạo một object JSON.

Khi dùng Springdoc 2.x trong ứng dụng Spring Boot 3, package annotation thường là org.springdoc.core.annotations.ParameterObject. Nếu dự án dùng phiên bản khác, hãy kiểm tra package và API annotation tương ứng với dependency đang cài.

### 3.1. Ẩn Pageable khỏi danh sách tham số và khai báo thủ công

Trong một số trường hợp, dự án muốn kiểm soát hoàn toàn tên, mô tả, giá trị mặc định hoặc ví dụ của các tham số. Có thể ẩn tham số Pageable khỏi tài liệu và khai báo các query parameter công khai:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.data.domain.Pageable;

@GetMapping
@Parameters({
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        description = "Chỉ số trang, bắt đầu từ 0.",
        schema = @Schema(type = "integer", minimum = "0", defaultValue = "0")
    ),
    @Parameter(
        name = "size",
        in = ParameterIn.QUERY,
        description = "Số phần tử tối đa trong một trang.",
        schema = @Schema(type = "integer", minimum = "1", defaultValue = "20")
    ),
    @Parameter(
        name = "sort",
        in = ParameterIn.QUERY,
        description = "Thuộc tính và hướng sắp xếp, ví dụ createdAt,desc.",
        array = @ArraySchema(schema = @Schema(type = "string"))
    )
})
public Page<ProductResponse> list(
    @Parameter(hidden = true) Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

Đây là cách minh họa khi cần tùy biến tham số. Hãy xác minh tài liệu chỉ chứa một bộ page, size, sort, tránh trường hợp vừa phân rã Pageable vừa khai báo thủ công gây tham số trùng.

Với nhiều endpoint dùng chung một quy ước, có thể tái sử dụng annotation tổng hợp hoặc cấu hình OpenAPI customizer thay vì lặp lại metadata.

## 4. Các query parameter page và size

### 4.1. page

page xác định chỉ số trang cần lấy. Theo mặc định Spring Data, chỉ số bắt đầu từ 0:

~~~http
GET /api/v1/products?page=0
GET /api/v1/products?page=1
GET /api/v1/products?page=2
~~~

Nếu client gửi số âm, resolver có thể chuẩn hóa về giá trị hợp lệ theo cơ chế của Spring Data. Tuy nhiên, API vẫn nên công bố miền giá trị không âm và có thể chủ động xác thực nếu muốn trả lỗi rõ ràng thay vì âm thầm chuẩn hóa.

### 4.2. size

size xác định số phần tử tối đa trong một trang:

~~~http
GET /api/v1/products?size=10
GET /api/v1/products?size=50
~~~

Không nên cho phép client yêu cầu kích thước không giới hạn. Một size quá lớn có thể tạo truy vấn nặng và response lớn. Hãy thiết lập giá trị mặc định cùng giới hạn tối đa ở server, sau đó mô tả chúng trong tài liệu.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: page
        size-parameter: size
        default-page-size: 20
        max-page-size: 100
        one-indexed-parameters: false
~~~

Các thuộc tính trên điều chỉnh tên tham số, kích thước mặc định, kích thước tối đa và quy ước đánh số trang. Tên tham số và cách đánh số được thay đổi ở đây cần được phản ánh nhất quán trong OpenAPI, ví dụ và tài liệu tích hợp.

### 4.3. Đánh số trang từ 1

Một số API muốn trang đầu tiên là page=1 để phù hợp cách hiểu phổ biến ở giao diện người dùng. Có thể bật:

~~~yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
~~~

Khi đó resolver diễn giải query parameter theo quy ước một-based. Cần phân biệt chỉ số client gửi với chỉ số nội bộ mà Pageable sử dụng. Không nên chỉ đổi ví dụ trong Swagger UI mà quên thay đổi resolver ở runtime.

## 5. Sort và cú pháp query parameter

Sort là abstraction của Spring Data mô tả thứ tự sắp xếp. Một Sort có thể gồm nhiều Order; mỗi Order xác định thuộc tính, hướng tăng/giảm và một số tùy chọn khác.

Cú pháp query phổ biến:

~~~http
GET /api/v1/products?sort=name,asc
GET /api/v1/products?sort=createdAt,desc
GET /api/v1/products?sort=category,asc&sort=price,desc
~~~

Ý nghĩa:

- name,asc: sắp xếp theo tên tăng dần.
- createdAt,desc: sắp xếp theo thời điểm tạo giảm dần.
- Nhiều tham số sort: tạo thứ tự ưu tiên nhiều tiêu chí; tiêu chí đầu được áp dụng trước.

Nếu chỉ ghi thuộc tính mà không chỉ định hướng, Spring Data thường dùng ASC. Hãy mô tả rõ hành vi mặc định của API.

### 5.1. Sort mặc định bằng @PageableDefault

Có thể đặt page size và sort mặc định ngay trên tham số controller:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springdoc.core.annotations.ParameterObject;

@GetMapping
public Page<ProductResponse> list(
    @ParameterObject
    @PageableDefault(
        page = 0,
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

Khi client không truyền sort, Spring Data sử dụng tiêu chí mặc định được khai báo. Nếu client gửi sort, giá trị client cung cấp có thể thay thế thứ tự mặc định. Hãy xác minh hành vi trong resolver và mô tả rõ trong API.

### 5.2. Nhiều tiêu chí sort mặc định

Nếu cần nhiều tiêu chí mặc định, có thể dùng @SortDefault:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.web.SortDefault;

@GetMapping
public Page<ProductResponse> list(
    @ParameterObject
    @SortDefault.SortDefaults({
        @SortDefault(
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ),
        @SortDefault(
            sort = "name",
            direction = Sort.Direction.ASC
        )
    })
    Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

Trong ví dụ, bản ghi được sắp xếp theo createdAt giảm dần; nếu có nhiều bản ghi cùng thời điểm tạo, name tăng dần được dùng làm tiêu chí tiếp theo. Một tiêu chí phụ ổn định như ID có thể giúp giảm hiện tượng thứ tự thay đổi giữa các lần truy vấn khi nhiều bản ghi có cùng giá trị sort.

### 5.3. Chỉ nhận Sort khi không cần phân trang

Một endpoint có thể chỉ cần sắp xếp danh sách đã được giới hạn bởi nghiệp vụ mà không cần page và size. Spring Data Web hỗ trợ nhận Sort riêng:

~~~java
import java.util.List;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Sort;

@GetMapping("/featured")
public List<ProductResponse> featured(
    @ParameterObject Sort sort
) {
    return productService.findFeatured(sort);
}
~~~

Trong trường hợp này, query parameter sort vẫn có thể lặp lại để truyền nhiều tiêu chí. Không có page hoặc size vì controller không nhận Pageable. Hãy kiểm tra OpenAPI JSON để xác nhận Springdoc biểu diễn Sort thành query parameter đúng như resolver đang nhận.

## 6. Kiểm soát thuộc tính được phép sort

Không nên cho client sắp xếp tùy ý theo mọi thuộc tính của entity hoặc database. Một số thuộc tính có thể nhạy cảm, không được index hoặc gây truy vấn tốn kém. Ngoài ra, tên field trong API không nhất thiết trùng tên cột dữ liệu.

Hãy xác định danh sách sort field được hỗ trợ, ví dụ:

| Query sort field | Thuộc tính nghiệp vụ |
|---|---|
| name | Tên sản phẩm |
| price | Giá bán |
| createdAt | Thời điểm tạo |
| updatedAt | Thời điểm cập nhật |

Có thể kiểm tra danh sách sort trước khi gọi repository:

~~~java
private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
    "name",
    "price",
    "createdAt",
    "updatedAt"
);

private Pageable validateSort(Pageable pageable) {
    for (Sort.Order order : pageable.getSort()) {
        if (!ALLOWED_SORT_FIELDS.contains(order.getProperty())) {
            throw new InvalidSortFieldException(order.getProperty());
        }
    }
    return pageable;
}
~~~

Ví dụ cần import java.util.Set, Sort, Pageable và định nghĩa exception riêng. Cách xử lý lỗi có thể trả 400 Bad Request với mã INVALID_SORT_FIELD. Nếu dùng mapping giữa tên API và tên thuộc tính entity, hãy chuyển đổi qua allowlist thay vì nối trực tiếp chuỗi do client gửi vào câu SQL.

## 7. Mô tả Pageable trong OpenAPI

Với @ParameterObject, Springdoc có thể sinh các query parameter từ Pageable. Dù vậy, người viết API vẫn cần kiểm tra tài liệu được sinh ra:

~~~yaml
parameters:
  - name: page
    in: query
    description: Chỉ số trang, bắt đầu từ 0.
    required: false
    schema:
      type: integer
      minimum: 0
      default: 0
  - name: size
    in: query
    description: Số phần tử tối đa trong một trang; mặc định 20, tối đa 100.
    required: false
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
  - name: sort
    in: query
    description: Có thể lặp lại để chỉ định nhiều tiêu chí; ví dụ createdAt,desc.
    required: false
    schema:
      type: array
      items:
        type: string
~~~

OpenAPI cho phép khai báo sort là array khi query parameter có thể lặp lại. Cách serialize query cần khớp với Spring Data resolver và công cụ client. Nếu Swagger UI tạo sort theo dạng khác với server mong đợi, hãy tùy biến parameter style/explode hoặc cung cấp ví dụ chính xác.

Không mặc định rằng Springdoc luôn biết mọi cấu hình Pageable tùy biến của ứng dụng. Khi đổi tên page thành pageNumber, size thành limit, bật one-based hoặc dùng prefix/qualifier, hãy kiểm tra /v3/api-docs và sửa metadata tương ứng nếu cần.

## 8. Tùy chỉnh tên tham số và nhiều Pageable

Spring Data Web cho phép cấu hình tên query parameter và prefix cho các Pageable được phân biệt bằng qualifier. Ví dụ cấu hình:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: page
        size-parameter: limit
        prefix: ""
        qualifier-delimiter: _
~~~

Khi có nhiều tham số Pageable trong cùng một method, có thể dùng @Qualifier để tạo nhóm tên riêng:

~~~java
@GetMapping("/dashboard")
public DashboardResponse dashboard(
    @Qualifier("orders") Pageable ordersPageable,
    @Qualifier("customers") Pageable customersPageable
) {
    return dashboardService.load(ordersPageable, customersPageable);
}
~~~

Với delimiter _, nhóm tham số có thể có dạng orders_page, orders_limit, orders_sort và customers_page, customers_limit, customers_sort, tùy cấu hình resolver. Đây là trường hợp cần kiểm tra tài liệu OpenAPI kỹ hơn vì @ParameterObject và customizer có thể cần hỗ trợ prefix/qualifier để tên hiển thị khớp runtime.

Nếu endpoint cần nhiều tập dữ liệu phân trang, cân nhắc tách thành nhiều endpoint hoặc tạo request model riêng nếu cách dùng nhiều Pageable làm hợp đồng khó hiểu.

## 9. Page, Slice và List khác nhau thế nào?

Spring Data có nhiều kiểu kết quả cho truy vấn:

| Kiểu | Nội dung | Metadata | Chi phí thường gặp |
|---|---|---|---|
| List<T> | Danh sách bản ghi | Không có metadata trang | Không tự mô tả tổng số trang |
| Slice<T> | Một lát dữ liệu | Có thông tin có trang tiếp theo hay không | Có thể tránh truy vấn đếm tổng |
| Page<T> | Một trang dữ liệu | Có tổng phần tử và tổng số trang | Thường cần truy vấn count |

Page<T> phù hợp khi giao diện cần hiển thị tổng số kết quả hoặc tổng số trang. Slice<T> phù hợp khi client chỉ cần biết còn dữ liệu tiếp theo hay không, chẳng hạn nút “Tải thêm”. List<T> phù hợp khi API chủ động giới hạn dữ liệu hoặc không cần metadata phân trang.

Ví dụ repository và service:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {
    Page<Product> findByActiveTrue(Pageable pageable);
}

public Page<ProductResponse> findAll(Pageable pageable) {
    return productRepository.findByActiveTrue(pageable)
        .map(productMapper::toResponse);
}
~~~

Phương thức map giữ metadata trang và chuyển đổi từng phần tử từ entity sang DTO. Nên trả DTO công khai thay vì trực tiếp trả entity persistence.

## 10. Cấu trúc response phân trang

Một đối tượng Page chứa dữ liệu và metadata như:

- content: các phần tử của trang hiện tại.
- number: chỉ số trang.
- size: kích thước trang.
- numberOfElements: số phần tử thực tế trong trang.
- totalElements: tổng số phần tử phù hợp truy vấn.
- totalPages: tổng số trang.
- first, last, empty: trạng thái trang.
- sort: thông tin sắp xếp.

Ví dụ response minh họa:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Bàn phím cơ",
      "price": 1250000
    },
    {
      "id": 102,
      "name": "Chuột không dây",
      "price": 450000
    }
  ],
  "number": 0,
  "size": 20,
  "numberOfElements": 2,
  "totalElements": 42,
  "totalPages": 3,
  "first": true,
  "last": false,
  "empty": false
}
~~~

Đây là hình dạng response đơn giản hóa để giải thích metadata. JSON thực tế khi serialize trực tiếp PageImpl có thể chứa thêm thuộc tính như pageable và sort, đồng thời cấu trúc có thể khác theo phiên bản Spring Data. Không nên dựa vào thứ tự field hoặc cấu trúc nội bộ của PageImpl như một hợp đồng ổn định mà chưa kiểm tra.

## 11. Thiết kế DTO response phân trang ổn định

Nếu muốn kiểm soát hoàn toàn JSON response, có thể tạo DTO riêng:

~~~java
public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean empty
) {
    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.isFirst(),
            source.isLast(),
            source.isEmpty()
        );
    }
}
~~~

Controller có thể chuyển Page thành DTO:

~~~java
@GetMapping
public PageResponse<ProductResponse> list(
    @ParameterObject Pageable pageable
) {
    return PageResponse.from(productService.findAll(pageable));
}
~~~

Với DTO riêng, API có thể quyết định tên metadata như page thay vì number, giới hạn field công khai và giữ cấu trúc response ổn định khi nâng cấp Spring Data. Cần mô tả schema generic và ví dụ tương ứng trong OpenAPI.

Một lựa chọn khác là Spring HATEOAS PagedModel nếu API muốn trả thêm liên kết điều hướng như self, next, prev và metadata trang theo mô hình hypermedia. Hãy chọn một hình thức nhất quán với cách client tiêu thụ API.

## 12. Mô tả Page response trong Springdoc

Springdoc có thể suy ra schema response từ kiểu trả về Page<ProductResponse>, nhưng schema cuối cùng phụ thuộc phiên bản springdoc, Spring Data và cách serialize. Với DTO riêng, schema thường rõ ràng và dễ kiểm soát hơn.

Có thể mô tả response DTO bằng annotation:

~~~java
@Schema(name = "ProductPageResponse")
public record ProductPageResponse(
    @Schema(description = "Danh sách sản phẩm của trang hiện tại.")
    List<ProductResponse> content,

    @Schema(description = "Chỉ số trang, bắt đầu từ 0.", example = "0")
    int page,

    @Schema(description = "Kích thước trang.", example = "20")
    int size,

    @Schema(description = "Tổng số sản phẩm phù hợp truy vấn.", example = "42")
    long totalElements,

    @Schema(description = "Tổng số trang.", example = "3")
    int totalPages,

    boolean first,
    boolean last,
    boolean empty
) {
}
~~~

Trong dự án thật, ProductResponse cần được định nghĩa và import đúng package. Nếu dùng PageResponse<T> generic, có thể khai báo schema cụ thể cho từng operation bằng @Schema(implementation = ...) hoặc cấu hình schema tương ứng để client generator nhận được kiểu phần tử cụ thể.

## 13. Lọc dữ liệu kết hợp Pageable và Sort

Một API danh sách thường kết hợp nhiều query parameter lọc với Pageable:

~~~java
@GetMapping
public Page<ProductResponse> search(
    @RequestParam(required = false) String keyword,
    @RequestParam(required = false) BigDecimal minPrice,
    @RequestParam(required = false) BigDecimal maxPrice,
    @ParameterObject
    @PageableDefault(size = 20, sort = "createdAt",
                     direction = Sort.Direction.DESC)
    Pageable pageable
) {
    return productService.search(
        keyword, minPrice, maxPrice, pageable
    );
}
~~~

Request ví dụ:

~~~http
GET /api/v1/products?keyword=keyboard&minPrice=100000&maxPrice=2000000&page=0&size=20&sort=createdAt,desc
~~~

Tài liệu OpenAPI cần mô tả từng query parameter lọc và bộ tham số phân trang/sắp xếp. Nêu rõ quy tắc kết hợp min/max, xử lý giá trị không hợp lệ và cách sort mặc định.

Nếu query có nhiều điều kiện, có thể gom các tham số nghiệp vụ thành một request model riêng nhưng Pageable vẫn thường được truyền như query parameter. Không nên đặt Pageable trong request body JSON nếu endpoint sử dụng cơ chế phân trang chuẩn của Spring Data Web.

## 14. Giới hạn, hiệu năng và tính ổn định của phân trang

Phân trang offset/page-number dễ sử dụng, nhưng có một số đặc điểm:

- Khi dữ liệu thay đổi giữa các lần gọi, bản ghi có thể dịch chuyển giữa các trang.
- Page thường cần đếm tổng số bản ghi để tính totalElements và totalPages.
- Trang có offset rất lớn có thể khiến truy vấn database chậm.
- Sort không ổn định có thể làm bản ghi trùng hoặc bị bỏ qua giữa các trang.

Để tăng tính ổn định:

1. Giới hạn size tối đa ở server.
2. Dùng tiêu chí sort có tính xác định; thêm ID làm tiêu chí phụ khi cần.
3. Tạo index phù hợp với các trường lọc và sort thường dùng.
4. Cân nhắc Slice nếu không cần tổng số bản ghi.
5. Với dữ liệu rất lớn hoặc thay đổi liên tục, cân nhắc cursor/keyset pagination thay cho offset pagination.

Cursor pagination thường cần một token hoặc giá trị mốc để lấy phần dữ liệu tiếp theo. Đây là hợp đồng khác với Pageable thông thường; hãy mô tả riêng cursor, hướng duyệt, tính hết hạn và hành vi khi cursor không hợp lệ.

## 15. Ví dụ tài liệu OpenAPI hoàn chỉnh

Ví dụ rút gọn dưới đây mô tả endpoint danh sách sản phẩm:

~~~yaml
paths:
  /api/v1/products:
    get:
      summary: Tìm kiếm sản phẩm có phân trang
      description: |
        Trả về danh sách sản phẩm theo điều kiện lọc và thứ tự sắp xếp.
        page bắt đầu từ 0; size mặc định là 20 và tối đa là 100.
        Có thể lặp lại sort để khai báo nhiều tiêu chí.
      parameters:
        - name: keyword
          in: query
          required: false
          schema:
            type: string
        - name: page
          in: query
          required: false
          description: Chỉ số trang, bắt đầu từ 0.
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          required: false
          description: Số phần tử mỗi trang, tối đa 100.
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: sort
          in: query
          required: false
          description: Có thể lặp lại, ví dụ sort=createdAt,desc.
          style: form
          explode: true
          schema:
            type: array
            items:
              type: string
      responses:
        '200':
          description: Trang kết quả sản phẩm.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductPageResponse'
        '400':
          description: Tham số phân trang, lọc hoặc sort không hợp lệ.
components:
  schemas:
    ProductPageResponse:
      type: object
      properties:
        content:
          type: array
          items:
            $ref: '#/components/schemas/ProductResponse'
        page:
          type: integer
        size:
          type: integer
        totalElements:
          type: integer
          format: int64
        totalPages:
          type: integer
        first:
          type: boolean
        last:
          type: boolean
        empty:
          type: boolean
~~~

Trong đặc tả thực tế, hãy xác nhận cách serialize mảng query sort khớp với resolver của Spring Data. Nếu server nhận tham số lặp như sort=name,asc&sort=price,desc, OpenAPI nên mô tả serialization phù hợp để Swagger UI và client generator tạo request đúng.

## 16. Kiểm tra tài liệu được sinh ra

Sau khi chạy ứng dụng Spring Boot, mở endpoint OpenAPI mặc định:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Tìm operation danh sách và kiểm tra:

1. Có các query parameter page, size, sort hay không.
2. Kiểu dữ liệu và vị trí in: query có chính xác không.
3. Giá trị mặc định có khớp @PageableDefault và cấu hình resolver không.
4. size có thể hiện giới hạn tối đa mà server thực thi không.
5. sort có thể lặp lại và có mô tả cú pháp direction không.
6. Response schema có phản ánh đúng JSON runtime không.
7. Các tham số lọc khác có mô tả miền giá trị và hành vi lỗi không.

Thử trực tiếp trong Swagger UI với trang đầu, trang tiếp theo, size mặc định, size tối đa và nhiều tiêu chí sort. Nếu thay đổi cấu hình Pageable, hãy chạy lại kiểm tra vì tài liệu cũ có thể không còn khớp.

## 17. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Không dùng @ParameterObject cho Pageable | Swagger UI không thể hiện đúng page/size/sort | Thêm annotation hoặc khai báo query parameter thủ công |
| Ghi page bắt đầu từ 1 trong tài liệu nhưng resolver dùng 0 | Client lấy sai trang | Đồng bộ one-indexed-parameters và mô tả |
| Không giới hạn size | Client có thể yêu cầu response quá lớn | Cấu hình max-page-size và công bố giới hạn |
| Không mô tả sort lặp lại | Client khó tạo nhiều tiêu chí sắp xếp | Mô tả array/query parameter có thể lặp |
| Cho sort tùy ý theo mọi field | Truy vấn chậm hoặc lộ thuộc tính nội bộ | Dùng allowlist sort field |
| Sort không có tiêu chí phụ ổn định | Kết quả giữa các trang có thể thay đổi | Thêm tiêu chí phụ như ID |
| Trả trực tiếp PageImpl mà không kiểm tra JSON | Schema có thể phụ thuộc phiên bản Spring Data | Dùng DTO phân trang ổn định hoặc xác minh serialization |
| Nghĩ @ParameterObject tự giới hạn size | Server không thực thi giới hạn như tài liệu | Cấu hình resolver và validation thực tế |
| Tài liệu chỉ mô tả query mà không nói response metadata | Client không biết cách duyệt trang | Mô tả content, totalElements, totalPages hoặc next cursor |

## 18. Ghi nhớ

- Pageable chứa chỉ số trang, kích thước trang, offset và Sort.
- Spring Data Web thường nhận page, size, sort từ query parameter.
- @ParameterObject giúp Springdoc phân rã Pageable thành các tham số truy vấn riêng.
- page mặc định bắt đầu từ 0; có thể đổi quy ước nhưng phải đồng bộ resolver và tài liệu.
- @PageableDefault và @SortDefault đặt giá trị phân trang/sắp xếp mặc định.
- sort có thể lặp lại để mô tả nhiều tiêu chí; nên giới hạn field được phép sort.
- Page<T> cung cấp tổng số phần tử và tổng số trang; Slice<T> chỉ cần biết còn dữ liệu tiếp theo; List<T> không có metadata trang.
- DTO response phân trang giúp giữ JSON ổn định và kiểm soát schema.
- Luôn kiểm tra /v3/api-docs và response runtime để bảo đảm tài liệu khớp cấu hình Spring Data.

Khi xây dựng API danh sách bằng Spring Data, hãy xem Pageable và Sort là một phần hợp đồng HTTP. Mô tả rõ query parameter, mặc định, giới hạn và cú pháp sắp xếp bằng Springdoc; đồng thời chọn response phân trang có schema ổn định để client có thể điều hướng dữ liệu chính xác.
