# Giới hạn kích thước trang và kiểm soát thuộc tính được phép sắp xếp

Spring Data JPA hỗ trợ nhận `Pageable` và `Sort` để phân trang, sắp xếp kết quả. Khi các giá trị này đến từ HTTP request, ứng dụng cần kiểm soát hai điều: **mỗi request được phép lấy tối đa bao nhiêu bản ghi** và **client được phép sắp xếp theo những thuộc tính nào**.

Nếu không giới hạn page size, client có thể yêu cầu một trang rất lớn làm tăng bộ nhớ, thời gian truy vấn, số entity được hydrate và chi phí serialization. Nếu nhận tùy ý thuộc tính sort, client có thể kích hoạt các đường dẫn quan hệ đắt tiền, truy vấn lỗi hoặc làm lộ những trường nội bộ mà API không muốn công khai. Hãy cấu hình giới hạn ở tầng web và kiểm tra lại chính sách trước khi repository thực thi query.

Bài này sử dụng Spring Boot 3.x, Spring Data JPA 3.x, Jakarta Persistence và Java 17+. Các package/cấu hình resolver cần được đối chiếu với release train đang dùng.

## 1. Pageable và Sort từ HTTP request

Một controller có thể nhận `Pageable` trực tiếp:

```java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService customerService;

    public CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @GetMapping
    public Page<CustomerSummary> search(
            @PageableDefault(
                size = 20,
                sort = {"createdAt", "id"},
                direction = Sort.Direction.DESC
            )
            Pageable pageable
    ) {
        return customerService.search(pageable);
    }
}
```

Một request điển hình:

```http
GET /api/customers?page=0&size=20&sort=createdAt,desc&sort=id,desc
```

Spring Data Web phân tích các tham số:

- `page`: chỉ số trang, mặc định bắt đầu từ 0.
- `size`: số bản ghi tối đa trong một trang.
- `sort`: thuộc tính và hướng sắp xếp; có thể truyền nhiều lần để tạo sort nhiều cột.

Ví dụ `sort=createdAt,desc&sort=id,desc` nghĩa là sắp xếp theo createdAt giảm dần, sau đó id giảm dần.

`Pageable` chứa page number, page size và Sort. Repository dùng thông tin này để tạo truy vấn có giới hạn và thứ tự tương ứng. Controller không cần tự ghép chuỗi SQL.

## 2. Page size mặc định không phải giới hạn tối đa

Có hai khái niệm riêng:

- **Fallback/default page size**: kích thước được dùng khi request không truyền size.
- **Maximum page size**: giới hạn trên mà resolver chấp nhận khi client yêu cầu size lớn.

Ví dụ, đặt mặc định 20 không có nghĩa client không thể gửi `size=50000`. Nếu không cấu hình giới hạn tối đa, request vẫn có thể yêu cầu một trang lớn tùy cấu hình resolver.

Annotation `@PageableDefault(size = 20)` chỉ cung cấp giá trị mặc định cho tham số Pageable của method. Nó không phải cơ chế giới hạn request size.

Nên quyết định rõ các chính sách:

| Chính sách | Ví dụ |
|---|---|
| Page size mặc định | 20 |
| Page size tối đa | 100 |
| Trang bắt đầu | 0 |
| Sort mặc định | createdAt DESC, id DESC |
| Số thuộc tính sort tối đa | 2 thuộc tính client yêu cầu |
| Không truyền sort | Dùng sort mặc định |
| Sort không được phép | Trả HTTP 400 |

Các con số chỉ là ví dụ. Hãy chọn theo kích thước DTO, chi phí query, tải thực tế và nhu cầu giao diện.

## 3. Cấu hình resolver để giới hạn page size

Trong Spring Boot, có thể khai báo bean `PageableHandlerMethodArgumentResolverCustomizer` để cấu hình resolver tự động chuyển request parameter thành Pageable.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
public class PaginationWebConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> {
            resolver.setMaxPageSize(100);
            resolver.setFallbackPageable(
                PageRequest.of(
                    0,
                    20,
                    Sort.by(
                        Sort.Order.desc("createdAt"),
                        Sort.Order.desc("id")
                    )
                )
            );
            resolver.setOneIndexedParameters(false);
        };
    }
}
```

Ý nghĩa:

- `setMaxPageSize(100)`: giới hạn kích thước trang ở resolver. Với request yêu cầu lớn hơn mức này, resolver chuẩn hóa/cap size về mức tối đa.
- `setFallbackPageable(...)`: đặt Pageable mặc định khi request không cung cấp page/size phù hợp.
- `setOneIndexedParameters(false)`: API sử dụng page index bắt đầu từ 0.

Package của customizer là `org.springframework.data.web.config`. Bean được Spring Boot nhận diện khi cấu hình Spring Data web pagination. Nếu dự án tự đăng ký argument resolver hoặc không dùng cấu hình web mặc định của Boot, cần cấu hình resolver thực tế đang được MVC sử dụng.

Không nên dựa vào giá trị mặc định của framework. Hãy đặt max page size tường minh để API có hợp đồng ổn định khi nâng cấp Spring Data.

### 3.1. @PageableDefault và cấu hình toàn cục

Có thể đặt default riêng cho endpoint:

```java
@GetMapping
public Page<CustomerSummary> search(
    @PageableDefault(
        page = 0,
        size = 25,
        sort = {"createdAt", "id"},
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return customerService.search(pageable);
}
```

Nếu client không truyền tham số, endpoint dùng page 0, size 25 và sort đã khai báo. Nếu client gửi page, size hoặc sort, các giá trị request có thể thay thế default tương ứng.

`@PageableDefault` không ghi đè `setMaxPageSize` và không tạo allowlist cho sort. Cần cấu hình max ở resolver và kiểm tra sort riêng.

Nếu muốn mỗi cột có hướng mặc định khác nhau, có thể dùng `@SortDefault.SortDefaults`:

```java
@SortDefault.SortDefaults({
    @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
    @SortDefault(sort = "id", direction = Sort.Direction.DESC)
})
Pageable pageable
```

Chỉ dùng một nguồn default rõ ràng cho mỗi endpoint để tránh cấu hình khó hiểu giữa fallback toàn cục và annotation tại method.

## 4. Cap page size hay từ chối request vượt giới hạn?

Resolver chuẩn thường cap kích thước yêu cầu về mức tối đa đã cấu hình. Ví dụ client gửi `size=10000`, ứng dụng có thể xử lý như size 100 thay vì trả lỗi.

Đây là một chính sách hợp lệ, nhưng cần nhất quán trong API:

- **Cap**: dễ bảo vệ tài nguyên; client vẫn nhận kết quả với page size nhỏ hơn yêu cầu.
- **Reject**: hợp đồng rõ ràng hơn nếu client phải biết request vượt giới hạn; cần kiểm tra giá trị thô trước hoặc trong custom argument resolver.

Không nên nghĩ rằng thêm `@Max(100)` lên tham số Pageable sẽ tự kiểm tra page size bên trong object. Bean Validation không tự suy diễn constraint cho thuộc tính lồng bên trong Pageable nếu không có cơ chế validation phù hợp.

Nếu muốn reject, có thể nhận tham số size riêng và validate trước khi tạo Pageable, hoặc viết resolver/validator chuyên biệt. Ví dụ đơn giản với request DTO hoặc tham số riêng:

```java
@GetMapping("/strict")
public Page<CustomerSummary> searchStrict(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size
) {
    Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
    );

    return customerService.search(pageable);
}
```

Ví dụ này cố định sort để minh họa validate page/size. Nếu endpoint cũng nhận sort động, hãy parse sort qua allowlist trước khi tạo PageRequest. Với `@RequestParam`, cần bật method validation theo cấu hình Spring MVC/Spring Framework của dự án để các constraint được thực thi.

## 5. Giới hạn phải được bảo vệ cả ở tầng service

Resolver chỉ kiểm soát request đi qua MVC argument resolution. Một service có thể được gọi từ scheduled job, message consumer, test hoặc một service khác bằng Pageable tự tạo. Các đường gọi đó không nhất thiết đi qua resolver.

Vì vậy, nếu giới hạn là quy tắc tài nguyên của use case, nên kiểm tra lại ở service hoặc một policy dùng chung:

```java
@Component
public class CustomerPagePolicy {

    private static final int MAX_PAGE_SIZE = 100;

    public Pageable validate(Pageable requested) {
        if (requested == null || requested.isUnpaged()) {
            throw new IllegalArgumentException(
                "A paged request is required"
            );
        }

        int page = requested.getPageNumber();
        int size = requested.getPageSize();

        if (page < 0) {
            throw new IllegalArgumentException("Page must be non-negative");
        }

        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "Page size must be between 1 and " + MAX_PAGE_SIZE
            );
        }

        return requested;
    }
}
```

Service gọi policy trước repository:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;
    private final CustomerPagePolicy pagePolicy;

    public CustomerService(
            CustomerRepository repository,
            CustomerPagePolicy pagePolicy
    ) {
        this.repository = repository;
        this.pagePolicy = pagePolicy;
    }

    @Transactional(readOnly = true)
    public Page<CustomerSummary> search(Pageable requested) {
        Pageable pageable = pagePolicy.validate(requested);
        return repository.findAllProjectedBy(pageable);
    }
}
```

Resolver giúp bảo vệ HTTP boundary; service policy bảo vệ use case khi được gọi từ các đường khác. Dùng cùng một hằng số/cấu hình cho hai nơi để tránh một nơi cho phép 100 nhưng nơi khác lại cho phép 500.

Nếu resolver đã cap size, service sẽ nhận giá trị sau khi cap. Nếu muốn reject đúng giá trị request ban đầu, phải validate trước khi resolver làm mất thông tin size gốc hoặc dùng custom resolver.

## 6. Sort từ request là dữ liệu cần kiểm soát

Spring Data hỗ trợ sort động qua tham số:

```http
GET /api/customers?sort=name,asc
GET /api/customers?sort=createdAt,desc&sort=id,desc
```

Một `Sort` chứa một hoặc nhiều `Sort.Order`. Mỗi order có property và direction; có thể thêm ignoreCase hoặc null handling tùy API.

Không nên chuyển mọi chuỗi sort client gửi thẳng vào repository mà không có chính sách. Các rủi ro gồm:

- Client yêu cầu sắp xếp theo thuộc tính nội bộ hoặc không nên công khai.
- Sort theo đường dẫn quan hệ gây join hoặc query tốn kém.
- Sort theo property không tồn tại làm query lỗi.
- Nhiều cột sort làm query và index phức tạp.
- Sort không ổn định khiến bản ghi lặp hoặc mất giữa các trang khi dữ liệu thay đổi.

Spring Data JPA kiểm tra/diễn giải sort property theo mapping và query, nhưng điều đó không thay thế allowlist nghiệp vụ. Một thuộc tính hợp lệ về mặt JPA vẫn có thể không được phép dùng trong API.

## 7. Tạo allowlist thuộc tính sort

Một cách an toàn là ánh xạ tên sort công khai của API sang property Java được phép:

| Tên client gửi | Property nội bộ |
|---|---|
| created | createdAt |
| name | name |
| status | status |

Không đưa mọi property của entity vào allowlist. Ví dụ email, internalNote, passwordHash hoặc quan hệ lớn có thể không được phép sort qua API dù chúng tồn tại trong entity.

Policy có thể xác thực từng order và giới hạn số cột:

```java
@Component
public class CustomerSortPolicy {

    private static final Map<String, String> ALLOWED = Map.of(
        "created", "createdAt",
        "name", "name",
        "status", "status"
    );

    private static final int MAX_SORT_FIELDS = 2;

    public Sort validate(Sort requested) {
        List<Sort.Order> accepted = new ArrayList<>();

        for (Sort.Order order : requested) {
            String property = ALLOWED.get(order.getProperty());

            if (property == null) {
                throw new IllegalArgumentException(
                    "Unsupported sort field: " + order.getProperty()
                );
            }

            if (accepted.size() >= MAX_SORT_FIELDS) {
                throw new IllegalArgumentException(
                    "Too many sort fields"
                );
            }

            accepted.add(
                new Sort.Order(order.getDirection(), property)
            );
        }

        if (accepted.isEmpty()) {
            accepted.add(Sort.Order.desc("createdAt"));
        }

        boolean hasId = accepted.stream()
            .anyMatch(order -> order.getProperty().equals("id"));

        if (!hasId) {
            accepted.add(Sort.Order.asc("id"));
        }

        return Sort.by(accepted);
    }
}
```

Ví dụ trên dùng tên công khai `created`, sau đó ánh xạ thành property Java `createdAt`. Client không được tự chọn property tùy ý. Policy chỉ giữ direction ASC/DESC và bỏ các option khác để API có hành vi rõ ràng.

Lưu ý: ví dụ giới hạn hai order do client yêu cầu rồi thêm `id` làm tie-breaker nội bộ. Nếu muốn cho client sort id trực tiếp, hãy thêm id vào allowlist và điều chỉnh giới hạn tương ứng.

## 8. Kết hợp PagePolicy và SortPolicy

Có thể kết hợp hai policy để tạo Pageable an toàn:

```java
@Component
public class CustomerPagePolicy {

    private static final int MAX_PAGE_SIZE = 100;

    private final CustomerSortPolicy sortPolicy;

    public CustomerPagePolicy(CustomerSortPolicy sortPolicy) {
        this.sortPolicy = sortPolicy;
    }

    public Pageable validate(Pageable requested) {
        if (requested == null || requested.isUnpaged()) {
            throw new IllegalArgumentException(
                "A paged request is required"
            );
        }

        int page = requested.getPageNumber();
        int size = requested.getPageSize();

        if (page < 0) {
            throw new IllegalArgumentException("Invalid page number");
        }

        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Invalid page size");
        }

        Sort safeSort = sortPolicy.validate(requested.getSort());

        return PageRequest.of(page, size, safeSort);
    }
}
```

Service chỉ dùng Pageable đã qua policy:

```java
@Transactional(readOnly = true)
public Page<CustomerSummary> search(Pageable requested) {
    return repository.findAllProjectedBy(
        pagePolicy.validate(requested)
    );
}
```

Nếu client gửi `sort=created,desc&sort=name,asc`, policy đổi thành sort theo `createdAt DESC`, rồi `name ASC`, sau đó thêm `id ASC` để kết quả ổn định. Nếu client gửi `sort=passwordHash,asc`, policy từ chối trước khi repository tạo query.

Ở tầng web, nên chuyển lỗi validation thành HTTP 400 bằng exception handler nhất quán. Không trả lỗi SQL hoặc stack trace nội bộ cho client.

## 9. Vì sao cần sort ổn định?

Giả sử nhiều Customer có cùng createdAt. Nếu chỉ sort theo createdAt, thứ tự giữa các bản ghi cùng thời điểm không được xác định duy nhất. Khi client lấy trang 0 rồi trang 1, dữ liệu mới có thể được thêm hoặc cập nhật; bản ghi có thể xuất hiện lặp hoặc bị bỏ qua giữa hai lần request.

Thêm khóa duy nhất làm tiêu chí cuối:

```java
Sort stableSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);
```

Khi createdAt bằng nhau, id xác định thứ tự. Đây là tie-breaker giúp thứ tự có tính xác định hơn.

Sort ổn định không tạo snapshot nhất quán xuyên suốt nhiều HTTP request. Nếu dữ liệu thay đổi liên tục, offset pagination vẫn có thể dịch chuyển. Với luồng duyệt sâu hoặc dữ liệu biến động, cân nhắc keyset/seek pagination và cursor dựa trên các trường sort cùng khóa duy nhất.

## 10. Sort nhiều cột và cú pháp request

Spring Data Web thường nhận nhiều tham số sort:

```http
GET /api/customers?page=0&size=25&sort=created,desc&sort=id,asc
```

Thứ tự các tham số sort thể hiện thứ tự ưu tiên:

1. created DESC.
2. id ASC.

Có thể truyền một sort parameter gồm property và direction; cú pháp direction mặc định có thể là ASC nếu không chỉ rõ. Hãy công bố cú pháp API rõ trong OpenAPI và kiểm thử cách resolver phân tích dấu phẩy, dấu chấm và tên property.

Không nhận biểu thức SQL như `LOWER(name)` từ client. Nếu API cần sort không phân biệt hoa/thường hoặc theo biểu thức, hãy tạo một lựa chọn sort có tên cố định và ánh xạ sang biểu thức được developer kiểm soát.

## 11. Cẩn thận với JpaSort.unsafe

Spring Data JPA cung cấp `JpaSort.unsafe(...)` cho các trường hợp cần sort theo biểu thức mà sort property thông thường không cho phép. Đây là API nâng cao, cho phép đưa expression vào phần ORDER BY mà không qua kiểm tra property path thông thường.

Ví dụ minh họa cho code do developer kiểm soát:

```java
Sort expressionSort = JpaSort.unsafe("LENGTH(name)");
```

Không bao giờ truyền trực tiếp chuỗi sort do người dùng gửi vào `JpaSort.unsafe`. Điều đó phá vỡ ranh giới giữa lựa chọn sort được phép và biểu thức query. Nếu cần expression sort, hãy ánh xạ một enum/alias cố định như `nameLength` sang expression được viết sẵn trong code, không nhận raw expression từ HTTP.

Với query native SQL, cách Spring Data áp dụng Sort động phụ thuộc loại query và phiên bản. Không giả định mọi native query đều hỗ trợ sort động an toàn. Với native SQL phức tạp, nên khai báo query/ORDER BY rõ ràng hoặc xây dựng query từ whitelist identifier đã kiểm soát.

## 12. Giới hạn số thuộc tính sort và kiểu sort

Ngoài allowlist, API có thể giới hạn:

- Số cột sort tối đa, ví dụ 2.
- Direction chỉ ASC hoặc DESC.
- Không cho phép sort theo nested association nếu không có use case rõ.
- Không cho phép sort theo LOB, JSON, trường bí mật hoặc biểu thức tính toán nặng.
- Không cho phép client điều khiển null precedence nếu database/provider chưa được kiểm thử.
- Chỉ chấp nhận một số tổ hợp sort đã định nghĩa trước nếu query có yêu cầu index cụ thể.

Một thuộc tính có trong allowlist chưa chắc mọi tổ hợp đều hiệu quả. Ví dụ sort theo status rồi createdAt có thể cần composite index khác với sort theo createdAt rồi status.

Nếu API cần nhiều chế độ sắp xếp, có thể dùng enum:

```java
public enum CustomerOrder {
    NEWEST,
    NAME_ASC,
    STATUS_ASC
}
```

Service ánh xạ từng lựa chọn sang Sort cố định:

```java
private Sort toSort(CustomerOrder order) {
    return switch (order) {
        case NEWEST -> Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("id")
        );
        case NAME_ASC -> Sort.by(
            Sort.Order.asc("name"),
            Sort.Order.asc("id")
        );
        case STATUS_ASC -> Sort.by(
            Sort.Order.asc("status"),
            Sort.Order.asc("id")
        );
    };
}
```

Enum thường dễ công bố và kiểm thử hơn việc để client gửi property path tự do.

## 13. Page, Slice và giới hạn tài nguyên

Pageable kiểm soát số hàng của một trang, nhưng kiểu kết quả ảnh hưởng số query và chi phí:

| Kiểu kết quả | Nội dung | Chi phí cần chú ý |
|---|---|---|
| Page<T> | Content, page metadata và tổng số bản ghi/trang | Thường cần count query |
| Slice<T> | Content và thông tin còn trang tiếp theo | Thường không cần count toàn bộ |
| List<T> với Pageable | Chỉ content đã giới hạn | Không có total metadata |
| Window<T> | Một cửa sổ kết quả dùng Scroll API | Phù hợp với scrolling/keyset khi provider/query hỗ trợ |

Nếu giao diện cần tổng số trang, dùng Page. Nếu chỉ cần nút "Tải thêm", Slice thường tránh được count query. Nếu xử lý tuần tự dữ liệu lớn, cân nhắc Scroll API/keyset thay vì offset page sâu.

Page size 100 không có nghĩa query luôn nhẹ: entity có nhiều eager association, fetch join hoặc DTO lớn vẫn có thể trả payload nặng. Hãy kết hợp page limit với projection/DTO, fetch plan rõ và index phù hợp.

## 14. Offset lớn và giới hạn page number

PageRequest sử dụng page number và page size để tính offset. Trang càng sâu, database có thể phải bỏ qua càng nhiều hàng trước khi trả kết quả.

Ví dụ:

```java
PageRequest.of(
    10000,
    100,
    Sort.by("id").ascending()
);
```

Offset tương ứng là một triệu hàng. Với bảng lớn, việc dùng OFFSET lớn có thể chậm dù page size đã được giới hạn.

Có thể áp dụng thêm giới hạn page index hoặc offset tối đa cho endpoint nếu nghiệp vụ không cần truy cập trang rất sâu. Nếu cần duyệt toàn bộ dữ liệu, dùng keyset pagination/Scroll API với cursor thay vì tăng page number mãi.

Page size cap bảo vệ số hàng trả về mỗi lần; nó không tự giới hạn offset. Hai giới hạn này giải quyết hai vấn đề khác nhau.

## 15. Index và sort

Database có thể phải sort nhiều hàng nếu không có index phù hợp. Với truy vấn:

```sql
SELECT id, name, status, created_at
FROM customers
WHERE status = ?
ORDER BY created_at DESC, id ASC
LIMIT ? OFFSET ?;
```

Một composite index có thể hữu ích tùy database và selectivity:

```sql
CREATE INDEX idx_customers_status_created_id
    ON customers (status, created_at DESC, id ASC);
```

Đây là ví dụ định hướng, không phải index mặc định cho mọi schema. Hãy dùng execution plan và workload để quyết định thứ tự cột, chiều sort và việc có cần covering index hay không. Database khác nhau có khả năng khai thác mixed-direction index khác nhau.

Không tạo index cho mọi thuộc tính được allowlist. Mỗi index làm tăng chi phí insert/update/delete và dung lượng lưu trữ. Chọn một tập sort phổ biến có giá trị nghiệp vụ cao.

## 16. Xử lý lỗi đầu vào thành HTTP response rõ ràng

Nếu policy từ chối page size hoặc sort field, API nên trả lỗi 400 với thông báo ổn định:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ProblemDetail> handleInvalidQuery(
            IllegalArgumentException exception
    ) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.BAD_REQUEST
        );
        problem.setTitle("Invalid pagination or sort parameter");
        problem.setDetail(exception.getMessage());

        return ResponseEntity.badRequest().body(problem);
    }
}
```

Trong ứng dụng lớn, nên dùng exception riêng như `InvalidPageRequestException` thay vì bắt mọi IllegalArgumentException, vì loại exception chung có thể xuất phát từ lỗi lập trình khác. Chỉ trả các thông tin đầu vào cần thiết; không trả SQL, entity mapping nội bộ hoặc stack trace.

Nếu resolver cap size, response có thể cần công bố page size thực tế trong metadata để client biết server đã áp dụng giới hạn. Với Spring Data Page, `getSize()` phản ánh kích thước Pageable của trang; hãy kiểm thử response serializer đang dùng.

## 17. Kiểm thử cấu hình phân trang và allowlist

Nên có test cho cả MVC resolver và policy:

- Không truyền size: dùng fallback size.
- Truyền size hợp lệ: giữ size được yêu cầu.
- Truyền size vượt max: resolver cap hoặc endpoint reject đúng hợp đồng đã chọn.
- Truyền size 0/âm: xử lý theo chính sách và phiên bản resolver.
- Truyền page âm: bị chuẩn hóa hoặc từ chối theo hợp đồng API.
- Truyền sort được phép: ánh xạ đúng property Java.
- Truyền sort không được phép: trả HTTP 400 trước repository.
- Truyền quá nhiều sort order: bị từ chối.
- Không truyền sort: dùng default sort.
- Sort có giá trị trùng: id tie-breaker làm kết quả ổn định.
- Pageable.unpaged(): service policy từ chối nếu use case yêu cầu giới hạn.
- Service được gọi trực tiếp với Pageable lớn: policy vẫn bảo vệ giới hạn.

Ví dụ unit test cho sort policy:

```java
class CustomerSortPolicyTest {

    private final CustomerSortPolicy policy =
        new CustomerSortPolicy();

    @Test
    void mapsPublicSortAliasToEntityProperty() {
        Sort result = policy.validate(
            Sort.by(Sort.Order.desc("created"))
        );

        List<Sort.Order> orders =
            StreamSupport.stream(result.spliterator(), false).toList();

        assertThat(orders)
            .extracting(Sort.Order::getProperty)
            .containsExactly("createdAt", "id");
    }

    @Test
    void rejectsUnsupportedProperty() {
        assertThatThrownBy(() ->
            policy.validate(Sort.by("passwordHash"))
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
```

Đây là khung test; bổ sung import và test MVC cho resolver theo phiên bản Spring Boot đang dùng. Với test tích hợp, kiểm tra cả SQL và thứ tự kết quả trên database cùng loại production.

## 18. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Client yêu cầu size rất lớn | Chỉ cấu hình default size, không cấu hình max | Dùng setMaxPageSize |
| @PageableDefault không giới hạn size | Annotation chỉ đặt giá trị mặc định | Cấu hình resolver max |
| Scheduled job bỏ qua max size | Gọi service trực tiếp, không đi qua MVC resolver | Kiểm tra Pageable trong service policy |
| Sort theo property lạ làm query lỗi | Không validate tên sort | Dùng allowlist |
| Sort theo quan hệ gây query chậm | Cho phép nested property tùy ý | Chỉ cho phép field đã đánh giá chi phí |
| Sort không ổn định giữa các trang | Thiếu tie-breaker duy nhất | Thêm id hoặc khóa duy nhất vào cuối |
| Page sâu rất chậm | Offset lớn | Giới hạn offset hoặc dùng keyset/Scroll API |
| Page query chậm dù content nhỏ | Count query tốn kém | Dùng Slice nếu không cần total |
| Native query không áp dụng sort như dự kiến | Hỗ trợ dynamic sort phụ thuộc query/provider | Khai báo ORDER BY hoặc whitelist query riêng |
| Sort expression gây rủi ro | Truyền raw input vào JpaSort.unsafe | Chỉ dùng expression cố định trong code |
| Quá nhiều sort field | Không giới hạn số order | Giới hạn số cột và tổ hợp được hỗ trợ |
| Page size hợp lệ nhưng response vẫn nặng | Entity graph/association/payload lớn | Dùng projection, DTO và fetch plan |
| API trả lỗi SQL cho client | Không chuẩn hóa validation error | Exception handler trả HTTP 400 an toàn |

## 19. Bài tập thực hành

1. Tạo endpoint GET /api/customers nhận Pageable và quan sát query parameter page, size, sort.
2. Đặt fallback page size 20 và max page size 100 bằng resolver customizer.
3. Gửi request size=10000 và xác nhận resolver cap đúng theo hợp đồng.
4. Dùng @PageableDefault để đặt sort mặc định createdAt DESC, id DESC.
5. Viết CustomerSortPolicy chỉ cho phép created, name và status.
6. Thử gửi sort=passwordHash,asc và xác nhận API trả HTTP 400 trước repository.
7. Giới hạn tối đa hai sort order client yêu cầu và tự thêm id tie-breaker.
8. So sánh Page và Slice để quan sát count query.
9. Thử page number lớn và đo thời gian offset query.
10. Tạo index phù hợp cho filter + sort phổ biến và so sánh execution plan.
11. Gọi service trực tiếp bằng Pageable lớn/unpaged để xác nhận service policy vẫn bảo vệ.
12. Viết MVC test xác nhận default, max size, sort allowlist và thông báo lỗi.

**Nguyên tắc xuyên suốt:** page size mặc định và page size tối đa là hai cấu hình khác nhau. Dùng resolver để bảo vệ request HTTP, kiểm tra lại Pageable ở service khi có đường gọi khác, và chỉ ánh xạ sort alias qua allowlist property được phép. Thêm khóa duy nhất làm tie-breaker, chọn Page/Slice/keyset theo nhu cầu và đo query/index trên database thật.
