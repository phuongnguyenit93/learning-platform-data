# Truyền filter an toàn

## Mục tiêu

API tìm kiếm thường nhận các điều kiện lọc từ query string, ví dụ trạng thái đơn hàng, tên khách hàng hoặc khoảng tổng tiền. Những giá trị này đến từ client nên phải được xem là dữ liệu không đáng tin cậy. Nếu ghép trực tiếp chúng vào JPQL, SQL, tên thuộc tính hoặc biểu thức sắp xếp, ứng dụng có thể gặp injection, truy vấn ngoài dự kiến hoặc lộ dữ liệu không thuộc phạm vi người dùng.

Trong Spring HATEOAS, filter còn liên quan tới phân trang và điều hướng: các link next, prev và self cần giữ đúng điều kiện tìm kiếm để client tiếp tục duyệt cùng một tập kết quả.

Sau bài học, bạn có thể:

- Thiết kế filter DTO có kiểu dữ liệu và validation rõ ràng.
- Phân biệt giá trị filter với tên field, operator và sort property.
- Dùng Spring Data JPA Specification và Criteria API để tạo điều kiện có tham số.
- Allowlist các field, operator và thuộc tính sort mà API cho phép.
- Xử lý ký tự wildcard trong tìm kiếm LIKE.
- Kết hợp filter với Pageable, PagedResourcesAssembler và HAL links.
- Kiểm thử filter hợp lệ, filter không hợp lệ và các đầu vào có dấu hiệu injection.

## Vì sao phải truyền filter an toàn?

Giả sử client gọi:

~~~http
GET /api/orders?status=PAID&customerName=An&minTotal=100000
Accept: application/hal+json
~~~

Server cần tìm các đơn hàng đã thanh toán, có tên khách hàng chứa “An” và tổng tiền từ 100.000 trở lên. Các giá trị PAID, An và 100000 là dữ liệu đầu vào. Chúng không được phép quyết định tùy ý cấu trúc câu truy vấn.

Có hai loại đầu vào cần phân biệt:

| Loại đầu vào | Ví dụ | Cách kiểm soát |
|---|---|---|
| Giá trị dữ liệu | PAID, An, 100000 | Bind parameter, kiểm tra kiểu, độ dài và miền giá trị. |
| Cấu trúc truy vấn | status, totalAmount, contains, desc | Chọn từ allowlist do server định nghĩa. |

Prepared statement hoặc Criteria API bảo vệ giá trị dữ liệu khỏi bị diễn giải thành cú pháp SQL. Chúng không tự biến một tên thuộc tính hoặc toán tử tùy ý thành hợp lệ. Vì vậy, filter an toàn cần cả hai lớp: bind giá trị và giới hạn cấu trúc truy vấn.

Không nhận nguyên chuỗi where, tên cột SQL, JPQL fragment hoặc biểu thức Sort do client gửi rồi nối vào câu truy vấn. Hợp đồng API nên công bố một tập filter có ý nghĩa nghiệp vụ, không công bố ngôn ngữ truy vấn nội bộ của database.

## Dùng filter DTO có kiểu

Với một endpoint tìm kiếm đơn hàng, hãy định nghĩa các filter được hỗ trợ bằng một request model riêng:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Size;

public record OrderFilter(
        OrderStatus status,
        @Size(max = 80) String customerName,
        @DecimalMin("0.00") BigDecimal minTotal,
        @DecimalMin("0.00") BigDecimal maxTotal) {

    @AssertTrue(message = "minTotal phải nhỏ hơn hoặc bằng maxTotal")
    public boolean isTotalRangeValid() {
        return minTotal == null
                || maxTotal == null
                || minTotal.compareTo(maxTotal) <= 0;
    }
}
~~~

Các trường có ý nghĩa rõ ràng:

- status là enum, nên client chỉ có thể truyền một trạng thái được khai báo.
- customerName có giới hạn độ dài để tránh chuỗi tìm kiếm quá lớn.
- minTotal và maxTotal là BigDecimal, phù hợp với giá trị tiền tệ.
- isTotalRangeValid() kiểm tra quan hệ giữa hai giá trị, không chỉ kiểm tra từng trường độc lập.

Controller nhận filter qua @ModelAttribute:

~~~java
import jakarta.validation.Valid;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;

    @GetMapping("/api/orders")
    PagedModel<EntityModel<OrderResponse>> search(
            @Valid @ModelAttribute OrderFilter filter,
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = orderService.search(filter, pageable);
        return pagedAssembler.toModel(page, orderAssembler);
    }
}
~~~

Spring MVC bind query parameters vào các property của filter DTO và Pageable. Khi dùng @Valid, dữ liệu không hợp lệ được đưa vào luồng xử lý lỗi binding/validation của Spring MVC; API nên chuẩn hóa các lỗi này thành response 400 có thông báo phù hợp.

Filter DTO giới hạn bề mặt đầu vào. Client chỉ có thể gửi những điều kiện mà model công bố, còn server quyết định mỗi điều kiện được chuyển thành predicate như thế nào. Không dùng entity JPA làm filter object vì entity có thể chứa nhiều property nội bộ không thuộc hợp đồng tìm kiếm.

## Tạo predicate an toàn bằng Specification

Spring Data JPA cung cấp Specification<T> để xây điều kiện truy vấn bằng Criteria API. Các giá trị filter được truyền vào các hàm của CriteriaBuilder, thay vì nối chuỗi SQL:

~~~java
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.data.jpa.domain.Specification;

final class OrderSpecifications {

    private OrderSpecifications() {
    }

    static Specification<Order> hasStatus(OrderStatus status) {
        return (root, query, cb) -> status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }

    static Specification<Order> customerNameContains(String name) {
        if (name == null || name.isBlank()) {
            return (root, query, cb) -> cb.conjunction();
        }

        String pattern = "%"
                + escapeLike(name.trim().toLowerCase(Locale.ROOT))
                + "%";

        return (root, query, cb) -> cb.like(
                cb.lower(root.<String>get("customerName")),
                pattern,
                '\\');
    }

    static Specification<Order> totalAtLeast(BigDecimal minTotal) {
        return (root, query, cb) -> minTotal == null
                ? cb.conjunction()
                : cb.greaterThanOrEqualTo(
                        root.<BigDecimal>get("totalAmount"),
                        minTotal);
    }

    static Specification<Order> totalAtMost(BigDecimal maxTotal) {
        return (root, query, cb) -> maxTotal == null
                ? cb.conjunction()
                : cb.lessThanOrEqualTo(
                        root.<BigDecimal>get("totalAmount"),
                        maxTotal);
    }

    private static String escapeLike(String value) {
        return value
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_");
    }
}
~~~

Mỗi specification chỉ tạo một predicate. Khi tên khách hàng không được cung cấp, predicate cb.conjunction() tương đương điều kiện đúng và không lọc theo tên. Khi có tên, giá trị được chuyển thành pattern và truyền vào CriteriaBuilder.like(...) cùng ký tự escape.

Service kết hợp các điều kiện:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    Page<Order> search(OrderFilter filter, Pageable pageable) {
        OrderSortPolicy.validate(pageable);

        Specification<Order> specification =
                OrderSpecifications.hasStatus(filter.status())
                        .and(OrderSpecifications.customerNameContains(
                                filter.customerName()))
                        .and(OrderSpecifications.totalAtLeast(
                                filter.minTotal()))
                        .and(OrderSpecifications.totalAtMost(
                                filter.maxTotal()));

        return repository.findAll(specification, pageable);
    }
}
~~~

Repository cần hỗ trợ JpaSpecificationExecutor:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

interface OrderRepository
        extends JpaRepository<Order, UUID>,
                JpaSpecificationExecutor<Order> {
}
~~~

Specification sử dụng Criteria API để tạo truy vấn có tham số. Giá trị như tên khách hàng hoặc số tiền được xử lý như dữ liệu, không trở thành cú pháp truy vấn. Tên property trong ví dụ (status, customerName, totalAmount) là chuỗi do server viết cố định trong code; tuyệt đối không thay chúng bằng tên field nhận trực tiếp từ request.

## Xử lý wildcard trong LIKE

Bind parameter ngăn chuỗi tìm kiếm trở thành SQL syntax, nhưng ký tự % và _ vẫn có ý nghĩa wildcard trong biểu thức LIKE:

- % khớp với không hoặc nhiều ký tự.
- _ khớp với đúng một ký tự.

Nếu người dùng tìm tên An_, có thể họ muốn tìm đúng chuỗi chứa dấu gạch dưới, không phải dùng _ như wildcard. Hàm escapeLike(...) ở ví dụ trước escape các ký tự backslash, % và _, sau đó CriteriaBuilder nhận ký tự escape backslash.

Nếu sản phẩm chủ ý cung cấp wildcard search, hãy công bố rõ cú pháp và giới hạn độ phức tạp. Không vô tình để ký tự wildcard mở rộng phạm vi tìm kiếm, làm truy vấn tốn kém hoặc khiến kết quả khác điều người dùng mong đợi.

## Allowlist field và operator

Một API filter tổng quát đôi khi nhận dạng:

~~~http
GET /api/orders?field=totalAmount&operator=gte&value=100000
~~~

Thiết kế này linh hoạt hơn DTO cố định, nhưng field và operator là dữ liệu cấu trúc truy vấn. Không truyền trực tiếp chúng vào root.get(field), JpaSort.unsafe(...), JPQL hoặc SQL. Hãy chuyển chúng qua allowlist:

~~~java
enum OrderFilterField {
    STATUS,
    CREATED_AT,
    TOTAL_AMOUNT,
    CUSTOMER_NAME
}

enum FilterOperator {
    EQ,
    GTE,
    LTE,
    CONTAINS
}
~~~

Tiếp theo, định nghĩa các cặp field/operator được hỗ trợ. Ví dụ:

| Field | Operator được phép | Kiểu value |
|---|---|---|
| STATUS | EQ | OrderStatus |
| CREATED_AT | GTE, LTE | LocalDate hoặc Instant theo hợp đồng |
| TOTAL_AMOUNT | EQ, GTE, LTE | BigDecimal |
| CUSTOMER_NAME | CONTAINS | Chuỗi có giới hạn độ dài |

Server phải kiểm tra cả field, operator và kiểu value. Không phải operator nào cũng có nghĩa với mọi field; ví dụ CONTAINS không phù hợp với số tiền, còn GTE không phù hợp với trạng thái enum.

Nếu field hoặc operator không nằm trong allowlist, trả 400 Bad Request với lỗi đầu vào rõ ràng. Không âm thầm bỏ qua filter sai vì client có thể tưởng rằng điều kiện đã được áp dụng và nhận kết quả rộng hơn dự kiến.

Với phần lớn API nghiệp vụ, một filter DTO có kiểu như OrderFilter dễ kiểm tra và tài liệu hóa hơn một query language tự thiết kế. Chỉ xây filter tổng quát khi sản phẩm thực sự cần khả năng kết hợp điều kiện linh hoạt.

## Truyền sort an toàn cùng Pageable

Sort cũng là dữ liệu do client cung cấp. Ví dụ:

~~~http
GET /api/orders?sort=createdAt,desc
~~~

Không cho phép client sắp xếp theo mọi property của entity. Một số property có thể nhạy cảm, không có index, gây join tốn kém hoặc không thuộc hợp đồng công khai.

Hãy kiểm tra từng sort property bằng allowlist trước khi đưa Pageable xuống repository:

~~~java
import java.util.Set;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

final class OrderSortPolicy {

    private static final Set<String> ALLOWED_PROPERTIES =
            Set.of("createdAt", "status", "totalAmount");

    private OrderSortPolicy() {
    }

    static void validate(Pageable pageable) {
        for (Sort.Order order : pageable.getSort()) {
            if (!ALLOWED_PROPERTIES.contains(order.getProperty())) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Thuộc tính sort không được hỗ trợ");
            }
        }
    }
}
~~~

Service gọi OrderSortPolicy.validate(pageable) trước khi truy vấn. Sort.Direction được Spring phân giải thành ASC hoặc DESC; property vẫn cần allowlist. Nếu API muốn tên sort thân thiện hơn tên property persistence, dùng map từ alias công khai sang property cố định ở server.

Tránh JpaSort.unsafe(...) với dữ liệu request. API này cho phép biểu thức sort không được kiểm tra theo cách thông thường; chỉ dùng biểu thức cố định do server kiểm soát khi thực sự cần.

Ngoài sort allowlist, hãy giới hạn page size ở resolver:

~~~properties
spring.data.web.pageable.default-page-size=20
spring.data.web.pageable.max-page-size=100
~~~

Filter có giới hạn độ dài, sort có allowlist và page size có max giúp giới hạn chi phí của một request tìm kiếm.

## Kết hợp filter với PagedResourcesAssembler

Controller có thể nhận filter và Pageable cùng lúc. Service tạo Page<Order> từ predicate đã kiểm tra; PagedResourcesAssembler chuyển kết quả thành PagedModel:

~~~java
@GetMapping("/api/orders")
PagedModel<EntityModel<OrderResponse>> search(
        @Valid @ModelAttribute OrderFilter filter,
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.search(filter, pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
~~~

Response HAL chứa các item đã được assembler chuyển đổi, page metadata và các links điều hướng. Ví dụ request:

~~~http
GET /api/orders?status=PAID&customerName=An&minTotal=100000&page=0&size=20&sort=createdAt,desc
Accept: application/hal+json
~~~

Các links self, next, prev và last cần giữ các filter hiện tại cùng size và sort. PagedResourcesAssembler tạo links dựa trên request hiện tại và Pageable; hãy kiểm thử href thực tế để xác nhận các query parameters nghiệp vụ được giữ lại trong cấu hình ứng dụng.

Khi tự tạo link tìm kiếm hoặc link template, dùng URI builder và truyền từng query parameter đã được xác thực. Không nối chuỗi query bằng tay vì dấu cách, dấu &, dấu % hoặc ký tự Unicode có thể bị diễn giải sai khi tạo URI.

Client nên theo href trong relation next thay vì tự tăng page và ghép lại toàn bộ filter. Server là nơi quyết định cách duy trì các tham số tìm kiếm trong links hypermedia.

## Filter không thay thế authorization

Filter quyết định tập kết quả theo điều kiện tìm kiếm, nhưng không phải ranh giới bảo mật. Ví dụ, người dùng có thể gửi customerId của khách hàng khác hoặc bỏ hẳn filter tenant. Server phải giới hạn truy vấn theo danh tính và quyền của request:

~~~java
Specification<Order> specification =
        OrderSpecifications.hasStatus(filter.status())
                .and(OrderSpecifications.customerNameContains(
                        filter.customerName()))
                .and((root, query, cb) ->
                        cb.equal(root.get("tenantId"), currentTenantId));
~~~

currentTenantId phải được lấy từ security context hoặc thành phần đáng tin cậy phía server, không lấy nguyên giá trị tenant do client gửi. Nếu người dùng không có quyền truy cập một đơn hàng, không được để một filter khác làm lộ đơn hàng đó.

Chỉ đưa vào DTO những filter được phép công khai. Không cho client lọc theo các trường như internalNote, passwordHash, accessToken hoặc thông tin nội bộ khác. Thông báo lỗi cũng không nên tiết lộ tên bảng, cột, câu SQL hay stack trace.

## Kiểm thử filter an toàn

MockMvc có thể kiểm tra request hợp lệ được áp dụng đúng và response vẫn chứa links phân trang:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
                .param("status", "PAID")
                .param("customerName", "An")
                .param("minTotal", "100000")
                .param("page", "0")
                .param("size", "10")
                .param("sort", "createdAt,desc")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.page.size").value(10))
        .andExpect(jsonPath("$._links.self.href").exists());
~~~

Các trường hợp cần có:

- Status không thuộc enum hoặc số tiền không parse được trả 400.
- minTotal lớn hơn maxTotal bị từ chối.
- Chuỗi tìm kiếm dài hơn giới hạn bị từ chối.
- Sort property không nằm trong allowlist trả 400.
- Field/operator không được hỗ trợ trong filter tổng quát trả 400.
- Giá trị giống chuỗi SQL injection được xem như dữ liệu literal và không làm thay đổi cấu trúc truy vấn.
- %, _ và ký tự escape trong tìm kiếm được xử lý đúng với quy tắc LIKE đã công bố.
- Filter theo tenant không thể đọc dữ liệu của tenant khác.
- Link next giữ filter, sort và size; chỉ page thay đổi.
- Page size vượt giới hạn được xử lý theo chính sách resolver.

Đối với kiểm thử injection, đừng chỉ khẳng định request trả 200. Hãy xác minh kết quả chỉ chứa những bản ghi khớp literal, không có dữ liệu ngoài phạm vi và không làm thay đổi cấu trúc truy vấn. Có thể dùng integration test với database test để kiểm tra predicate thực tế.

## Những lỗi thường gặp

- **Nối chuỗi filter vào SQL/JPQL:** dùng bind parameter hoặc Criteria API; không ghép giá trị client vào query string.
- **Cho client gửi tên cột tùy ý:** allowlist field và ánh xạ alias sang property cố định.
- **Cho client gửi operator tùy ý:** kiểm tra cặp field/operator và kiểu value được phép.
- **Dùng sort property trực tiếp mà không kiểm tra:** giới hạn sort bằng allowlist; tránh JpaSort.unsafe với input client.
- **Quên wildcard LIKE:** %, _ vẫn có ngữ nghĩa wildcard dù value đã được bind. Escape nếu API tìm kiếm literal.
- **Không giới hạn kích thước filter:** giới hạn độ dài chuỗi, số lượng điều kiện, khoảng thời gian và page size.
- **Bỏ qua lỗi filter không hợp lệ:** trả 400 thay vì âm thầm bỏ điều kiện và trả tập dữ liệu rộng hơn.
- **Coi filter là authorization:** luôn thêm điều kiện tenant/quyền từ ngữ cảnh server đáng tin cậy.
- **Làm mất filter trong page links:** kiểm thử href next và prev với các query parameters thực tế.
- **Tự nối URL:** dùng URI builder để encode query values chính xác.

## Quy trình truyền filter an toàn

1. Xác định những điều kiện tìm kiếm thực sự thuộc hợp đồng API.
2. Tạo filter DTO có kiểu, giới hạn độ dài và validation liên trường.
3. Bind giá trị bằng repository parameters hoặc Criteria API; không nối chuỗi SQL/JPQL.
4. Allowlist field, operator và sort property; từ chối cấu trúc truy vấn không hỗ trợ.
5. Escape wildcard LIKE nếu tìm kiếm cần khớp literal.
6. Áp dụng tenant scope và authorization từ security context phía server.
7. Kết hợp filter với Pageable và PagedResourcesAssembler để tạo PagedModel.
8. Kiểm thử input không hợp lệ, injection-like values, tenant boundary và filter preservation trong HAL links.

Truyền filter an toàn nghĩa là client được chọn giá trị trong phạm vi hợp đồng mà server công bố, còn server giữ quyền kiểm soát cấu trúc truy vấn và phạm vi dữ liệu. Khi filter DTO, Criteria API, allowlist và HAL pagination links được thiết kế nhất quán, API vừa dễ khám phá vừa hạn chế injection, truy vấn tốn kém và rò rỉ dữ liệu.
