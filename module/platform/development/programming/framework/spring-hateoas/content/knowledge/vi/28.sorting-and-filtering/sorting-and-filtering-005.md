# Bộ lọc tùy chọn

Bộ lọc tùy chọn cho phép client truy vấn một tập hợp tài nguyên bằng một hoặc nhiều tiêu chí mà không phải cung cấp tất cả tiêu chí trong mọi request. Ví dụ, endpoint đơn hàng có thể lọc theo trạng thái, khách hàng, khoảng ngày tạo hoặc tổng tiền. Client có thể chỉ gửi trạng thái, kết hợp trạng thái với khách hàng, hoặc bỏ toàn bộ bộ lọc để lấy danh sách mặc định.

Trong Spring HATEOAS, việc lọc được thực hiện bởi controller, tầng truy vấn và repository; HATEOAS đảm nhiệm việc công bố đường dẫn tìm kiếm và các liên kết điều hướng. Một API tốt cần giữ các tiêu chí lọc nhất quán giữa request hiện tại, link search và link phân trang. Khi client theo link next, nó phải tiếp tục xem cùng tập kết quả đã lọc, thay vì vô tình quay về danh sách không có bộ lọc.

Bài học này trình bày cách nhận tham số tùy chọn trong Spring MVC, phân biệt tham số vắng mặt với giá trị rỗng, chuẩn hóa và xác thực tiêu chí, ghép điều kiện truy vấn bằng Spring Data JPA Specification, công bố URI template tìm kiếm, giữ bộ lọc trong link phân trang và kiểm thử hợp đồng hypermedia.

## 1. Bộ lọc tùy chọn là gì?

Một bộ lọc tùy chọn là tiêu chí truy vấn mà client có thể cung cấp hoặc bỏ qua. Ví dụ:

~~~http
GET /orders
GET /orders?status=PROCESSING
GET /orders?customerId=8f6b2c1a-4d6e-4a11-9b55-1c3a9d77e021
GET /orders?status=PROCESSING&customerId=8f6b2c1a-4d6e-4a11-9b55-1c3a9d77e021
GET /orders?createdFrom=2026-01-01&createdTo=2026-01-31
~~~

Tất cả request đều truy cập cùng endpoint collection, nhưng mỗi request xác định một tập con khác nhau.

Ví dụ hợp đồng cho endpoint đơn hàng:

| Tham số | Kiểu | Ý nghĩa |
|---|---|---|
| status | OrderStatus | Lọc theo trạng thái đơn |
| customerId | UUID | Lọc theo khách hàng |
| createdFrom | LocalDate | Ngày tạo bắt đầu, tính cả ngày này |
| createdTo | LocalDate | Ngày tạo kết thúc, tính cả ngày này |
| minTotal | BigDecimal | Tổng tiền tối thiểu |
| maxTotal | BigDecimal | Tổng tiền tối đa |
| page | Integer | Trang kết quả |
| size | Integer | Số phần tử mỗi trang |
| sort | String | Trường và hướng sắp xếp |

Client chỉ gửi những tham số cần thiết. Server áp dụng các điều kiện đã nhận và trả về collection tương ứng.

Bộ lọc tùy chọn khác với việc tạo nhiều endpoint cho từng tổ hợp điều kiện. Thay vì có endpoint riêng cho đơn hàng đang xử lý, đơn hàng của khách hàng, đơn hàng trong tháng và đơn hàng đang xử lý của một khách hàng, API có thể dùng một endpoint tìm kiếm với các tham số có thể kết hợp.

## 2. Phân biệt tham số vắng mặt, rỗng và không hợp lệ

Một trong những quyết định quan trọng nhất là quy định ý nghĩa của các giá trị đầu vào.

| Request | Cách hiểu nên quy định |
|---|---|
| Không có status | Không áp dụng điều kiện trạng thái |
| status=PROCESSING | Chỉ lấy đơn đang xử lý |
| status= | Giá trị rỗng; có thể từ chối hoặc chuẩn hóa thành không lọc theo hợp đồng |
| status=UNKNOWN | Giá trị enum không hợp lệ, thường trả 400 |
| customerId không có | Không lọc theo khách hàng |
| customerId=abc | UUID sai định dạng, trả 400 |
| minTotal=100 và maxTotal=50 | Khoảng không hợp lệ, trả 400 |

Không nên để hành vi với chuỗi rỗng phụ thuộc ngẫu nhiên vào bộ chuyển đổi tham số. Hãy quy định rõ:

- Tham số không xuất hiện có nghĩa là bỏ qua điều kiện.
- Tham số có giá trị hợp lệ sẽ tạo predicate tương ứng.
- Tham số rỗng được chuẩn hóa hoặc từ chối theo một quy tắc thống nhất.
- Tham số sai định dạng hoặc mâu thuẫn được trả về như lỗi request, thường là 400 Bad Request.

Nếu API xem chuỗi rỗng tương đương với không cung cấp bộ lọc, cần chuẩn hóa trước khi xây dựng truy vấn. Nếu chuỗi rỗng là đầu vào không hợp lệ, hãy trả lỗi rõ ràng thay vì âm thầm bỏ qua.

### 2.1. Muốn lọc những bản ghi có giá trị null

Tham số bị bỏ qua thường có nghĩa là không áp dụng predicate. Vì vậy, không nên dùng một giá trị rỗng để đồng thời diễn đạt cả “không lọc” và “chỉ lấy bản ghi không có customer”. Nếu cần lọc quan hệ null, hãy công bố một tiêu chí riêng, chẳng hạn **customerAssigned=false** hoặc **customerIdIsNull=true**.

Ví dụ:

~~~java
if (Boolean.TRUE.equals(filter.customerAssigned())) {
    predicates.add(cb.isNotNull(root.get("customer")));
} else if (Boolean.FALSE.equals(filter.customerAssigned())) {
    predicates.add(cb.isNull(root.get("customer")));
}
~~~

Thêm thuộc tính **Boolean customerAssigned** vào filter object. Nhờ vậy, ba trạng thái được phân biệt rõ: null nghĩa là không lọc customer; true chỉ lấy bản ghi có customer; false chỉ lấy bản ghi không có customer.

## 3. Nhận tham số tùy chọn trong Spring MVC

Với Spring MVC, dùng **@RequestParam(required = false)** để khai báo tham số không bắt buộc.

~~~java
@GetMapping("/orders")
public CollectionModel<EntityModel<OrderRepresentation>> search(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(required = false) UUID customerId) {

    // Tạo bộ lọc và truy vấn
}
~~~

Nếu client không gửi status hoặc customerId, Spring MVC cung cấp giá trị null cho tham số tương ứng. Controller có thể dùng các giá trị đó để quyết định điều kiện nào cần áp dụng.

Có thể đặt tên tham số tường minh:

~~~java
@RequestParam(name = "createdFrom", required = false)
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
LocalDate createdFrom
~~~

Tên công khai của query parameter khi đó không phụ thuộc tên biến Java. Điều này hữu ích khi API cần giữ tên tham số ổn định qua các lần refactor.

### 3.3. Bộ lọc có nhiều giá trị

Spring MVC có thể bind nhiều giá trị cùng tên vào List hoặc Collection:

~~~java
@RequestParam(name = "status", required = false)
List<OrderStatus> statuses
~~~

Client có thể gửi theo dạng lặp tham số:

~~~http
GET /orders?status=NEW&status=PROCESSING
~~~

Đây là cách composite mặc định. Spring HATEOAS cũng hỗ trợ cách non-composite, trong đó các giá trị được phân tách bằng dấu phẩy. Dùng **@NonComposite** nếu API chọn cách biểu diễn đó:

~~~java
import org.springframework.hateoas.NonComposite;

@RequestParam(name = "status", required = false)
@NonComposite
List<OrderStatus> statuses
~~~

Request khi đó có thể có dạng **?status=NEW,PROCESSING**. Hãy chọn một quy ước và dùng nhất quán trong controller, URI template, client và kiểm thử. Với giá trị có chứa dấu phẩy, cần kiểm tra encoding và quy tắc parse thực tế.

Đây là biến thể của hợp đồng filter dùng một status đơn lẻ ở các ví dụ trước. Nếu API hỗ trợ nhiều trạng thái, đổi trường status trong filter object thành Collection<OrderStatus> và dùng predicate IN:

~~~java
if (filter.statuses() != null && !filter.statuses().isEmpty()) {
    predicates.add(root.get("status").in(filter.statuses()));
}
~~~

### 3.1. Dùng Optional<T>

Có thể dùng java.util.Optional để thể hiện rõ tham số có thể vắng mặt:

~~~java
@GetMapping("/orders")
public CollectionModel<EntityModel<OrderRepresentation>> search(
        @RequestParam Optional<OrderStatus> status,
        @RequestParam Optional<UUID> customerId,
        @RequestParam Optional<Boolean> customerAssigned) {

    OrderFilter filter = new OrderFilter(
        status.orElse(null),
        customerId.orElse(null),
        customerAssigned.orElse(null),
        null,
        null,
        null,
        null
    );

    // Truy vấn theo filter
}
~~~

Với Spring MVC, tham số Optional được xem là không bắt buộc. Tuy nhiên, khi có nhiều tiêu chí và cần chuẩn hóa dữ liệu, một DTO bộ lọc thường dễ quản lý hơn việc truyền một danh sách dài tham số vào nhiều tầng.

Không nên dùng Optional như một cách thay thế validation. Giá trị được gửi lên vẫn phải được kiểm tra về định dạng, miền giá trị và quan hệ giữa các tiêu chí.

### 3.2. Dùng defaultValue khi có mặc định thật sự

Có thể dùng defaultValue khi API định nghĩa một giá trị mặc định:

~~~java
@RequestParam(defaultValue = "20") int size
~~~

Nếu client không gửi size, server dùng 20. Khi có defaultValue, tham số được xem là không bắt buộc.

Không nên dùng defaultValue để che giấu sự khác biệt giữa “không lọc” và “lọc theo một giá trị cụ thể”. Ví dụ, tự gán status mặc định là PROCESSING sẽ khiến request không có status chỉ trả đơn đang xử lý, dù client có thể kỳ vọng lấy mọi trạng thái.

## 4. Gom tiêu chí vào một filter object

Khi endpoint có nhiều tham số, nên gom chúng thành một đối tượng để truyền qua các tầng ứng dụng.

~~~java
public record OrderFilter(
    OrderStatus status,
    UUID customerId,
    Boolean customerAssigned,
    LocalDate createdFrom,
    LocalDate createdTo,
    BigDecimal minTotal,
    BigDecimal maxTotal
) {}
~~~

Controller nhận tham số HTTP rồi tạo filter object:

~~~java
@GetMapping("/orders")
public PagedModel<EntityModel<OrderRepresentation>> search(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(required = false) UUID customerId,
        @RequestParam(required = false) Boolean customerAssigned,
        @RequestParam(required = false)
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate createdFrom,
        @RequestParam(required = false)
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate createdTo,
        @RequestParam(required = false) BigDecimal minTotal,
        @RequestParam(required = false) BigDecimal maxTotal,
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    OrderFilter filter = new OrderFilter(
        status,
        customerId,
        customerAssigned,
        createdFrom,
        createdTo,
        minTotal,
        maxTotal
    );

    // Xác thực filter, truy vấn và tạo PagedModel
}
~~~

Filter object mang ý nghĩa ứng dụng, không phải đối tượng persistence. Nó có thể được dùng bởi service, query component và test mà không phụ thuộc trực tiếp vào HTTP request.

Nếu ứng dụng cần nhiều endpoint dùng chung một bộ lọc, hãy đặt filter object ở package phù hợp với tầng ứng dụng. Tránh để service nhận HttpServletRequest hoặc đọc query parameter trực tiếp từ web context.

## 5. Chuẩn hóa và xác thực bộ lọc

Trước khi truy vấn, hãy kiểm tra các điều kiện có thể gây ra kết quả vô nghĩa hoặc tốn tài nguyên.

Ví dụ:

~~~java
import org.springframework.stereotype.Component;

@Component
public class OrderFilterValidator {

    public void validate(OrderFilter filter) {
        if (filter.customerId() != null
                && Boolean.FALSE.equals(filter.customerAssigned())) {
            throw new InvalidOrderFilterException(
                "Không thể chỉ định customerId khi customerAssigned=false"
            );
        }

        if (filter.createdFrom() != null
                && filter.createdTo() != null
                && filter.createdFrom().isAfter(filter.createdTo())) {
            throw new InvalidOrderFilterException(
                "createdFrom phải nhỏ hơn hoặc bằng createdTo"
            );
        }

        if (filter.minTotal() != null
            && filter.maxTotal() != null
            && filter.minTotal().compareTo(filter.maxTotal()) > 0) {
            throw new InvalidOrderFilterException(
                "minTotal không được lớn hơn maxTotal"
            );
        }

        if (filter.minTotal() != null
            && filter.minTotal().signum() < 0) {
            throw new InvalidOrderFilterException(
                "minTotal không được âm"
            );
        }

        if (filter.maxTotal() != null
                && filter.maxTotal().signum() < 0) {
            throw new InvalidOrderFilterException(
                "maxTotal không được âm"
            );
        }
    }
}
~~~

Các quy tắc xác thực nên bao gồm:

- Khoảng ngày có thứ tự hợp lệ.
- customerId không mâu thuẫn với customerAssigned.
- Giá trị min không lớn hơn max.
- Số tiền nằm trong miền nghiệp vụ cho phép.
- Tập giá trị enum hợp lệ.
- Kích thước trang không vượt giới hạn.
- Các chuỗi tìm kiếm có độ dài hợp lý.
- Danh sách ID không vượt số lượng tối đa.

Nếu tham số là chuỗi tự do, có thể trim khoảng trắng và chuẩn hóa chữ hoa/chữ thường theo semantics của trường. Không tự động chuyển đổi dữ liệu theo cách làm thay đổi ý nghĩa tìm kiếm, ví dụ loại bỏ dấu hoặc wildcard mà API chưa công bố.

Lỗi đầu vào nên được ánh xạ nhất quán thành 400 Bad Request với thông tin chỉ rõ tham số sai. Không trả collection rỗng cho một request sai định dạng, vì điều đó khiến client nhầm lẫn giữa “không có kết quả” và “bộ lọc không hợp lệ”.

## 6. Ghép điều kiện truy vấn bằng Spring Data JPA Specification

Khi số tiêu chí tăng, việc tạo một repository method cho từng tổ hợp bộ lọc sẽ khó duy trì. Spring Data JPA Specification cho phép ghép các predicate theo những tiêu chí thực sự được cung cấp.

Specification phù hợp khi bộ lọc cần được kết hợp động. Với một hoặc hai tiêu chí cố định, derived query method hoặc JPQL có thể đơn giản hơn. Chọn cách truy vấn theo độ phức tạp thực tế thay vì đưa mọi endpoint vào một query builder tổng quát.

Repository cần mở rộng JpaSpecificationExecutor:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID>,
                JpaSpecificationExecutor<Order> {
}
~~~

Tạo specification từ filter object:

~~~java
public final class OrderSpecifications {

    private OrderSpecifications() {
    }

    public static Specification<Order> from(OrderFilter filter) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (filter.status() != null) {
                predicates.add(
                    cb.equal(root.get("status"), filter.status())
                );
            }

            if (filter.customerId() != null) {
                predicates.add(
                    cb.equal(
                        root.get("customer").get("id"),
                        filter.customerId()
                    )
                );
            }

            if (Boolean.TRUE.equals(filter.customerAssigned())) {
                predicates.add(cb.isNotNull(root.get("customer")));
            } else if (Boolean.FALSE.equals(filter.customerAssigned())) {
                predicates.add(cb.isNull(root.get("customer")));
            }

            if (filter.createdFrom() != null) {
                LocalDateTime from =
                    filter.createdFrom().atStartOfDay();

                predicates.add(
                    cb.greaterThanOrEqualTo(
                        root.get("createdAt"),
                        from
                    )
                );
            }

            if (filter.createdTo() != null) {
                LocalDateTime until =
                    filter.createdTo().plusDays(1).atStartOfDay();

                predicates.add(
                    cb.lessThan(
                        root.get("createdAt"),
                        until
                    )
                );
            }

            if (filter.minTotal() != null) {
                predicates.add(
                    cb.greaterThanOrEqualTo(
                        root.get("total"),
                        filter.minTotal()
                    )
                );
            }

            if (filter.maxTotal() != null) {
                predicates.add(
                    cb.lessThanOrEqualTo(
                        root.get("total"),
                        filter.maxTotal()
                    )
                );
            }

            return cb.and(predicates.toArray(Predicate[]::new));
        };
    }
}
~~~

Các import chính:

~~~java
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

import jakarta.persistence.criteria.Predicate;
import org.springframework.data.jpa.domain.Specification;
~~~

Mỗi predicate chỉ được thêm khi tiêu chí tương ứng có giá trị. Khi filter không chứa tiêu chí nào, danh sách predicate rỗng và cb.and(...) tạo điều kiện không giới hạn, nên truy vấn trả tập hợp theo mặc định.

Với createdTo, ví dụ dùng mốc đầu ngày kế tiếp và toán tử nhỏ hơn. Cách này bao gồm toàn bộ thời điểm trong ngày kết thúc mà không phải đoán độ chính xác của timestamp, chẳng hạn 23:59:59.999.

Ví dụ giả định createdAt là LocalDateTime theo cùng quy ước múi giờ của ứng dụng. Nếu hệ thống lưu Instant hoặc timestamp UTC, hãy chuyển ngày biên sang múi giờ nghiệp vụ được xác định rõ trước khi tạo predicate.

Tên thuộc tính trong root.get(...) phải khớp với mô hình JPA thực tế. Với dự án lớn, có thể dùng JPA static metamodel để giảm lỗi chính tả khi đổi tên field.

## 7. Thực thi truy vấn có bộ lọc và phân trang

Service nhận filter và Pageable, sau đó gọi repository:

~~~java
@Service
public class OrderQueryService {

    private final OrderRepository repository;
    private final OrderFilterValidator filterValidator;

    public OrderQueryService(
            OrderRepository repository,
            OrderFilterValidator filterValidator) {
        this.repository = repository;
        this.filterValidator = filterValidator;
    }

    public Page<Order> search(
            OrderFilter filter,
            Pageable pageable) {

        filterValidator.validate(filter);

        Specification<Order> specification =
            OrderSpecifications.from(filter);

        return repository.findAll(specification, pageable);
    }
}
~~~

Controller chuyển Page thành PagedModel:

~~~java
Page<Order> page = queryService.search(filter, pageable);

return pagedAssembler.toModel(page, orderModelAssembler);
~~~

PagedResourcesAssembler tạo representation phân trang và các link điều hướng dựa trên request hiện tại. Khi dùng query parameter tùy chỉnh, hãy xác nhận các tham số lọc vẫn xuất hiện trong link next, prev, first và last. Nếu ứng dụng cung cấp link base tùy chỉnh cho assembler, link đó cần chứa đầy đủ filter đang áp dụng.

Bộ lọc và phân trang giải quyết hai việc khác nhau:

- Bộ lọc xác định tập kết quả.
- Pageable xác định phần nào của tập kết quả được trả về và thứ tự hiển thị.

Ngay cả khi không có filter nào, endpoint collection vẫn nên giới hạn kích thước trang và có thứ tự mặc định ổn định. Không để request GET /orders không tham số vô tình tải toàn bộ bảng.

Khi client theo link next, server phải áp dụng cùng tiêu chí lọc với trang trước. Nếu bỏ mất filter, client sẽ chuyển sang một tập kết quả khác giữa chừng.

## 8. Công bố link tìm kiếm với URI template

Một API hypermedia nên công bố khả năng tìm kiếm qua relation, thay vì yêu cầu client tự đoán tên endpoint và query parameter.

Ví dụ HAL:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders?status=PROCESSING&page=0&size=20"
    },
    "search": {
      "href": "/orders{?status,customerId,customerAssigned,createdFrom,createdTo,minTotal,maxTotal,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Relation search cho client biết link này hỗ trợ truy vấn. URI template liệt kê các biến mà client có thể cung cấp. Client không cần biết query string được ghép theo thứ tự nào hoặc server đang dùng page/size hay một cơ chế khác, miễn là template được công bố đúng.

Có thể tạo template tường minh:

~~~java
Link search = Link.of(
    "/orders{?status,customerId,customerAssigned,createdFrom,createdTo,minTotal,maxTotal,page,size,sort}",
    IanaLinkRelations.SEARCH
);
~~~

Trong ứng dụng thực tế, tránh lặp đường dẫn bằng chuỗi nếu mapping có thể thay đổi. Có thể tạo base URI từ controller mapping bằng WebMvcLinkBuilder rồi bổ sung template variables phù hợp. Cần kiểm thử link cuối cùng để xác nhận các biến được công bố đúng.

Nếu endpoint dùng tên tham số khác với tên field Java, template phải dùng tên query parameter công khai. Ví dụ annotation @RequestParam(name = "createdFrom") thì URI template cũng cần biến createdFrom.

## 9. Tạo search link từ controller mapping

Với Spring MVC, WebMvcLinkBuilder có thể tạo link dựa trên mapping của controller. Ví dụ controller có method search:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping
    public PagedModel<EntityModel<OrderRepresentation>> search(
            @RequestParam(required = false) OrderStatus status,
            @RequestParam(required = false) UUID customerId,
            @RequestParam(required = false) Boolean customerAssigned,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate createdFrom,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate createdTo,
            @RequestParam(required = false) BigDecimal minTotal,
            @RequestParam(required = false) BigDecimal maxTotal,
            Pageable pageable) {
        // Tìm kiếm
    }
}
~~~

Có thể tham chiếu handler method để tạo search link:

~~~java
Link search = linkTo(
    methodOn(OrderController.class).search(
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null
    )
).withRel(IanaLinkRelations.SEARCH);
~~~

Các giá trị null trong lời gọi giả lập thể hiện những query parameter tùy chọn chưa được cung cấp. Spring HATEOAS có thể biểu diễn chúng thành URI template dựa trên metadata của handler mapping và parameter annotations.

Hãy xác minh các biến thực tế qua Link.getVariableNames() hoặc response HAL. Đặc biệt, Pageable có thể được xử lý bởi Spring Data web integration; tên page, size và sort phụ thuộc cấu hình PageableHandlerMethodArgumentResolver. Không giả định cấu hình mặc định nếu ứng dụng đã đổi tên hoặc đổi định dạng tham số phân trang.

Ví dụ kiểm tra link trong unit test:

~~~java
assertThat(search.isTemplated()).isTrue();
assertThat(search.getVariableNames())
    .contains(
        "status",
        "customerId",
        "customerAssigned",
        "createdFrom",
        "createdTo",
        "minTotal",
        "maxTotal"
    );
~~~

Nếu API dùng URI template được tạo thủ công, test cần xác nhận đầy đủ cả filter variables lẫn pagination variables.

### 9.1. Khai báo query parameter tùy chọn trong affordance

Nếu API công bố thao tác tìm kiếm qua một media type có hỗ trợ affordance, chẳng hạn HAL-FORMS, có thể mô tả từng query parameter bằng **QueryParameter.optional(...)**. Cách này thể hiện rõ tham số nào client có thể bỏ qua.

~~~java
import org.springframework.hateoas.Affordances;
import org.springframework.hateoas.QueryParameter;
import org.springframework.http.HttpMethod;

Link collection = linkTo(OrderController.class).withSelfRel();

Link search = Affordances.of(collection)
    .afford(HttpMethod.GET)
    .withOutput(OrderRepresentation.class)
    .addParameters(
        QueryParameter.optional("status"),
        QueryParameter.optional("customerId"),
        QueryParameter.optional("customerAssigned"),
        QueryParameter.optional("createdFrom"),
        QueryParameter.optional("createdTo"),
        QueryParameter.optional("minTotal"),
        QueryParameter.optional("maxTotal"),
        QueryParameter.optional("page"),
        QueryParameter.optional("size"),
        QueryParameter.optional("sort")
    )
    .withName("search")
    .toLink();
~~~

Ở đây, affordance mô tả một thao tác GET trên collection và khai báo các tiêu chí tìm kiếm là tùy chọn. Media type hỗ trợ affordance có thể chuyển metadata này thành mô tả thao tác mà client đọc được. Với HAL JSON cơ bản, hãy công bố URI template trong link search như mục trước; không giả định HAL tự biểu diễn đầy đủ metadata affordance.

Hai cách phục vụ hai phần bổ sung cho nhau: URI template cho biết tên biến mà client có thể điền vào href; affordance mô tả thao tác HTTP và các tham số của thao tác cho media type có hỗ trợ.

## 10. Giữ bộ lọc trong link phân trang

Giả sử client gọi:

~~~http
GET /orders?status=PROCESSING&customerId=CUS-7&page=0&size=20
~~~

Link next cần tiếp tục chứa status và customerId:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders?status=PROCESSING&customerId=CUS-7&page=0&size=20"
    },
    "next": {
      "href": "/orders?status=PROCESSING&customerId=CUS-7&page=1&size=20"
    }
  }
}
~~~

Nếu link next chỉ chứa page=1&size=20, client sẽ mất ngữ cảnh tìm kiếm. Điều này tạo ra lỗi khó nhận ra vì response vẫn hợp lệ nhưng dữ liệu không còn thuộc cùng tập kết quả.

PagedResourcesAssembler thường xây dựng pagination links dựa trên URI request hiện tại và cập nhật tham số trang. Nếu cần custom base link, hãy truyền link đã giữ lại filter. Khi dùng custom resolver hoặc đổi tên query parameter, cần kiểm thử cách assembler tạo URL theo cấu hình đó.

Một nguyên tắc quan trọng: tất cả link điều hướng trong một trang kết quả phải mô tả cùng một truy vấn, chỉ khác phần điều hướng trang hoặc sắp xếp nếu client chủ động thay đổi.

## 11. Bộ lọc kết hợp với sorting

Filtering và sorting thường xuất hiện cùng nhau. Bộ lọc xác định tập kết quả, còn sort xác định thứ tự của tập đó.

Ví dụ:

~~~http
GET /orders?status=PROCESSING&sort=createdAt,desc&sort=total,asc
~~~

Spring Data Pageable có thể nhận nhiều tham số sort. Nếu dùng Sort riêng, controller có thể nhận:

~~~java
@RequestParam(required = false) OrderStatus status,
Sort sort
~~~

Khi trả PagedModel, thứ tự sắp xếp phải được giữ trong link next và prev. Nếu link pagination bỏ mất sort, các trang có thể không còn ổn định hoặc client nhận dữ liệu theo thứ tự khác.

Nên định nghĩa whitelist các trường được phép sort. Không cho client tùy ý yêu cầu sắp xếp theo mọi thuộc tính entity, nhất là field nội bộ hoặc association có chi phí truy vấn cao. Nếu API công bố sort=createdAt,desc thì cần bảo đảm createdAt là tên thuộc tính được hỗ trợ ổn định.

Với dữ liệu có nhiều bản ghi trùng giá trị sort, nên bổ sung một khóa phụ ổn định, ví dụ ID, để giảm việc phần tử nhảy giữa các trang khi dữ liệu thay đổi.

## 12. Giới hạn và bảo vệ bộ lọc

Bộ lọc tùy chọn không có nghĩa client được phép truy vấn mọi field theo cách tùy ý.

Các giới hạn thường cần thiết:

- Whitelist trường có thể lọc và sort.
- Giới hạn độ dài chuỗi tìm kiếm.
- Giới hạn số giá trị trong filter dạng danh sách.
- Giới hạn page size.
- Từ chối khoảng ngày quá rộng nếu truy vấn gây tải lớn.
- Không công bố filter trên dữ liệu mà người dùng không được phép xem.
- Dùng parameter binding và Criteria API thay vì nối chuỗi SQL từ input.
- Kiểm tra quyền ở tầng truy vấn để không tải dữ liệu ngoài phạm vi người dùng.

Ví dụ, nếu endpoint chỉ hỗ trợ lọc theo status và customerId, client không thể tự thêm query parameter internalFlag rồi kỳ vọng server phải áp dụng. API chỉ hỗ trợ những filter đã được định nghĩa và tài liệu hóa.

Không dùng query parameter để thay thế authorization. Một client có thể gửi customerId của người khác; service hoặc repository phải áp dụng phạm vi dữ liệu theo quyền người gọi.

## 13. Kiểm thử bộ lọc tùy chọn

Kiểm thử nên bao gồm từng tiêu chí riêng lẻ, tổ hợp nhiều tiêu chí, request không có filter và dữ liệu đầu vào không hợp lệ.

Ví dụ với MockMvc:

~~~java
mockMvc.perform(get("/orders")
        .param("status", "PROCESSING")
        .param("customerId", customerId.toString())
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.search.href").exists())
    .andExpect(jsonPath("$._embedded.orders").isArray());
~~~

Kiểm tra request không có filter:

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Kiểm tra đầu vào sai:

~~~java
mockMvc.perform(get("/orders")
        .param("customerId", "not-a-uuid"))
    .andExpect(status().isBadRequest());
~~~

Kiểm tra khoảng ngày không hợp lệ:

~~~java
mockMvc.perform(get("/orders")
        .param("createdFrom", "2026-02-01")
        .param("createdTo", "2026-01-01"))
    .andExpect(status().isBadRequest());
~~~

Test cần xác nhận nội dung collection thực sự khớp tiêu chí, không chỉ xác nhận status 200. Dùng fixture có nhiều trạng thái và khách hàng khác nhau để phát hiện trường hợp server bỏ qua một predicate.

## 14. Kiểm thử link phân trang có giữ filter

Đây là một test quan trọng đối với API có cả filter và pagination:

~~~java
mockMvc.perform(get("/orders")
        .param("status", "PROCESSING")
        .param("customerId", customerId.toString())
        .param("customerAssigned", "true")
        .param("page", "0")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.next.href")
        .value(org.hamcrest.Matchers.containsString("status=PROCESSING")))
    .andExpect(jsonPath("$._links.next.href")
        .value(org.hamcrest.Matchers.containsString(
            "customerId=" + customerId
        )))
    .andExpect(jsonPath("$._links.next.href")
        .value(org.hamcrest.Matchers.containsString("customerAssigned=true")));
~~~

Test chỉ kiểm tra next link khi fixture có đủ kết quả để tạo trang tiếp theo. Nếu chỉ có một trang, relation next có thể không xuất hiện và đó là hành vi đúng.

Nên gửi request tiếp theo bằng href của link next thay vì tự ghép page=1. Sau đó xác nhận các phần tử vẫn thỏa status và customerId. Đây là cách kiểm tra cả hợp đồng hypermedia lẫn hành vi thực tế của endpoint.

## 15. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng tham số bắt buộc cho filter không bắt buộc | Client phải gửi tiêu chí không cần thiết | Dùng required=false hoặc Optional |
| Không phân biệt vắng mặt và chuỗi rỗng | Bộ lọc có hành vi khó đoán | Chuẩn hóa hoặc từ chối giá trị rỗng rõ ràng |
| Gán default filter không được công bố | Request không filter lại bị thu hẹp kết quả | Chỉ đặt default khi đó là hợp đồng thật |
| Tạo repository method cho mọi tổ hợp | Số method tăng nhanh | Ghép Specification hoặc query builder |
| Nối chuỗi SQL từ input | Rủi ro injection và lỗi truy vấn | Dùng Criteria API/parameter binding |
| Không xác thực quan hệ giữa min và max | Truy vấn trả kết quả vô nghĩa | Kiểm tra filter trước khi truy vấn |
| Link next làm mất filter | Client chuyển sang tập kết quả khác | Giữ query parameters trong pagination links |
| Search template thiếu tên biến | Client không biết filter được hỗ trợ | Kiểm tra variable names và HAL response |
| Cho phép sort tùy ý | Lộ field hoặc tạo truy vấn đắt | Whitelist sort properties |
| Chỉ test status HTTP | Không phát hiện predicate bị bỏ qua | Kiểm tra nội dung và link điều hướng |
| Dùng filter để thay authorization | Client có thể truy vấn dữ liệu ngoài phạm vi | Áp dụng quyền ở server/service/query layer |

## 16. Quy trình triển khai bộ lọc tùy chọn

Khi thêm filter cho một collection endpoint, hãy thực hiện theo thứ tự:

1. Xác định các tiêu chí được hỗ trợ và tên query parameter công khai.
2. Quy định ý nghĩa của tham số vắng mặt, rỗng và không hợp lệ.
3. Nhận tham số bằng @RequestParam(required = false) hoặc filter object.
4. Chuẩn hóa và xác thực các tiêu chí, bao gồm quan hệ giữa min/max và from/to.
5. Ghép predicate trong service hoặc query layer bằng Specification hay cơ chế truy vấn phù hợp.
6. Áp dụng Pageable và whitelist các trường sort.
7. Chuyển kết quả thành PagedModel bằng PagedResourcesAssembler.
8. Công bố relation search với URI template liệt kê các filter được hỗ trợ.
9. Bảo đảm link phân trang giữ nguyên các filter đang áp dụng.
10. Kiểm thử request không filter, từng filter, tổ hợp filter, đầu vào sai và next/prev link.

Bộ lọc tùy chọn giúp một endpoint collection phục vụ nhiều nhu cầu truy vấn mà không làm client phụ thuộc vào các route riêng cho từng tổ hợp điều kiện. Khi tham số được chuẩn hóa rõ, truy vấn được ghép có kiểm soát và link hypermedia giữ nguyên ngữ cảnh lọc, client có thể khám phá và điều hướng qua các kết quả nhất quán. Spring HATEOAS công bố search relation và pagination links; Spring MVC cùng tầng truy vấn chịu trách nhiệm diễn giải và thực thi các tiêu chí lọc.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – URI templates and WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [WebMvcLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [Spring Data JPA Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA JpaSpecificationExecutor API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaSpecificationExecutor.html)
- [Spring Data Web Support and Pagination](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html)
- [Spring Framework @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring HATEOAS QueryParameter API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/QueryParameter.html)
- [Spring HATEOAS Affordances API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Affordances.html)

