# Thiết kế tra cứu đơn hàng với lọc, phân trang và DTO riêng

Bài học này thuộc chương **Thực hành hệ thống đơn hàng** của module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, trong chương trình **học tổ chức phần mềm theo kiến trúc phân tầng**. Một màn hình quản trị đơn hàng thường cần lọc theo khách hàng, trạng thái hoặc khoảng thời gian; sắp xếp theo ngày tạo, tổng tiền hay mã đơn; và chỉ tải một phần kết quả cho mỗi lần xem. Thiết kế truy vấn cần phối hợp tầng trình bày, application và data access, đồng thời giữ entity ORM ở phía persistence và trả dữ liệu qua DTO phù hợp với nhu cầu của caller.

Bài học xây dựng một luồng tra cứu bằng Java/Spring: HTTP nhận tiêu chí tìm kiếm, application kiểm tra và điều phối use case, adapter JPA thực hiện truy vấn có lọc và phân trang, rồi kết quả được chuyển thành DTO riêng. Bên cạnh cách triển khai, cần hiểu các giới hạn về chi phí `COUNT`, thứ tự sắp xếp ổn định, dữ liệu thay đổi đồng thời và cách tránh N+1 query.

Sau bài học, bạn có thể thiết kế API tra cứu có hợp đồng rõ ràng, chọn kiểu phân trang phù hợp, giới hạn trường sắp xếp, trả DTO thay vì entity JPA, và giải thích mức nhất quán của kết quả khi dữ liệu thay đổi trong lúc người dùng chuyển trang.

## 1. Xác định hợp đồng tra cứu trước khi viết query

Giả sử màn hình đơn hàng cần các tiêu chí sau:

- Khách hàng (nếu người dùng chọn).
- Trạng thái đơn hàng (nếu có).
- Thời điểm tạo từ và đến.
- Trang hiện tại và số dòng mỗi trang.
- Trường và chiều sắp xếp.

Kết quả mỗi dòng chỉ cần mã đơn, tên khách hàng, trạng thái, tổng tiền và thời điểm tạo. Không cần trả toàn bộ aggregate `Order` hoặc entity `OrderEntity` nếu màn hình chỉ hiển thị các trường đó.

Trước khi triển khai, hãy xác định hợp đồng:

| Thành phần | Quyết định |
|---|---|
| Bộ lọc | Các trường nào là tùy chọn, cách chuẩn hóa và ý nghĩa khoảng thời gian |
| Phạm vi dữ liệu | Tenant/đơn vị nào được phép truy vấn; phạm vi này lấy từ danh tính đã xác thực |
| Phân trang | Page index bắt đầu từ 0 hay 1, kích thước mặc định và giới hạn tối đa |
| Sắp xếp | Chỉ cho phép những trường nào, chiều nào và thứ tự phụ ổn định |
| DTO | Các trường thực sự cần hiển thị, không để lộ entity/persistence relation |
| Tổng số | API có cần tổng số bản ghi và tổng số trang chính xác hay chỉ cần biết còn trang tiếp theo |

Đừng để framework quyết định ngầm những điều này. Một API có hợp đồng rõ giúp frontend, application và adapter hiểu cùng một ý nghĩa của bộ lọc, trang và kết quả.

## 2. Thiết kế DTO riêng cho request, use case và response

DTO (Data Transfer Object) biểu diễn dữ liệu đi qua một ranh giới. Có thể dùng các DTO khác nhau cho HTTP, application và response nếu chúng có trách nhiệm khác nhau. Không nên dùng `OrderEntity` làm DTO chỉ vì JPA đã có sẵn class đó.

### HTTP request DTO

Một request có thể nhận query parameter như sau:

```http
GET /api/orders?status=PAID&customerId=2e9...&createdFrom=2026-01-01T00:00:00Z&createdTo=2026-02-01T00:00:00Z&page=0&size=20&sort=CREATED_DESC
```

Các trường do client cung cấp là tiêu chí tìm kiếm. `tenantId` hoặc phạm vi truy cập không nên được tin cậy nếu client tự gửi; server cần lấy nó từ principal/security context đã xác thực.

Controller có thể nhận tham số đã được Spring bind và validate:

```java
@RestController
@RequestMapping("/api/orders")
@Validated
public class OrderQueryController {
    private final SearchOrdersUseCase searchOrders;

    public OrderQueryController(SearchOrdersUseCase searchOrders) {
        this.searchOrders = searchOrders;
    }

    @GetMapping
    public OrderPageResponse search(
            @RequestParam(required = false) UUID customerId,
            @RequestParam(required = false) OrderStatus status,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant createdFrom,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            Instant createdTo,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            @RequestParam(defaultValue = "CREATED_DESC") OrderSort sort,
            @AuthenticationPrincipal AppPrincipal principal) {

        var query = new SearchOrdersQuery(
                principal.tenantId(), customerId, status,
                createdFrom, createdTo, page, size, sort);

        return OrderPageResponse.from(searchOrders.execute(query));
    }
}
```

Đây là ví dụ minh họa; `AppPrincipal` là principal do ứng dụng ánh xạ từ danh tính đã xác thực, còn `OrderStatus` và `OrderSort` là enum của hợp đồng. Cần cấu hình method/parameter validation tương ứng với phiên bản Spring đang dùng. Nếu `createdFrom` lớn hơn hoặc bằng `createdTo`, application phải từ chối tiêu chí không hợp lệ theo hợp đồng đã chọn. Controller không lấy `tenantId` từ query parameter vì như vậy caller có thể thử đổi tenant để đọc dữ liệu ngoài phạm vi.

### Application query và result

Application dùng kiểu của chính nó, không để `Pageable`, `Page`, `Sort` hoặc `OrderEntity` lan vào use case:

```java
public record SearchOrdersQuery(
        UUID tenantId,
        UUID customerId,
        OrderStatus status,
        Instant createdFromInclusive,
        Instant createdToExclusive,
        int page,
        int size,
        OrderSort sort) {}

public enum OrderSort {
    CREATED_DESC,
    CREATED_ASC,
    TOTAL_DESC,
    ORDER_NUMBER_ASC
}

public record OrderListItem(
        UUID id,
        String orderNumber,
        String customerName,
        OrderStatus status,
        BigDecimal total,
        Instant createdAt) {}

public record PageResult<T>(
        List<T> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext) {}
```

`tenantId` được tạo từ principal đã xác thực ở adapter HTTP; một message handler hoặc CLI nếu được phép gọi use case cũng phải cung cấp phạm vi đã xác minh theo chính sách của nó. Application result chỉ chứa dữ liệu mà caller cần, không mang proxy, lazy collection hoặc annotation JPA.

### HTTP response DTO

Response có thể dùng một kiểu riêng với tên field phù hợp API:

```java
public record OrderItemResponse(
        UUID id,
        String orderNumber,
        String customerName,
        String status,
        BigDecimal total,
        Instant createdAt) {}

public record OrderPageResponse(
        List<OrderItemResponse> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext) {

    static OrderPageResponse from(PageResult<OrderListItem> result) {
        var items = result.items().stream()
                .map(item -> new OrderItemResponse(
                        item.id(), item.orderNumber(), item.customerName(),
                        item.status().name(), item.total(), item.createdAt()))
                .toList();
        return new OrderPageResponse(
                items, result.page(), result.size(),
                result.totalElements(), result.totalPages(), result.hasNext());
    }
}
```

Application DTO và HTTP response DTO có thể giống nhau ở ứng dụng nhỏ; tách riêng khi API cần versioning, tên field/format khác với use case hoặc có nhiều adapter tiêu thụ cùng kết quả. Mục tiêu là giữ hợp đồng ổn định và tránh để thay đổi schema persistence tự động thay đổi API.

## 3. Xác định đúng ngữ nghĩa của bộ lọc

### Bộ lọc tùy chọn

Một tiêu chí không được gửi thường có nghĩa là “không giới hạn theo tiêu chí đó”. Ví dụ, không có `status` thì tìm mọi trạng thái trong phạm vi caller được phép xem. Không nên biến giá trị thiếu thành một trạng thái mặc định mà client không yêu cầu.

Trước khi query, cần chuẩn hóa đầu vào:

- Chuỗi tìm kiếm: trim khoảng trắng, giới hạn độ dài và xác định quy tắc phân biệt hoa/thường.
- Enum: chỉ nhận giá trị được định nghĩa; giá trị lạ trả lỗi validation rõ ràng.
- ID: parse thành kiểu ID, không dùng chuỗi tùy ý làm điều kiện ghép SQL.
- Danh sách lọc: giới hạn số phần tử để tránh query quá lớn.
- Khoảng thời gian: quy định timezone và biên bao gồm/không bao gồm.

### Khoảng thời gian nửa mở

Một cách ổn định để lọc ngày giờ là dùng khoảng nửa mở `[fromInclusive, toExclusive)`: lấy bản ghi có `createdAt >= from` và `createdAt < to`. Ví dụ muốn lấy đơn trong tháng 1 theo UTC, dùng từ `2026-01-01T00:00:00Z` đến trước `2026-02-01T00:00:00Z`.

Khoảng nửa mở tránh phải tạo “23:59:59.999999999” ở cuối ngày, vốn phụ thuộc độ chính xác timestamp của database. Nếu UI nhận ngày theo múi giờ địa phương, hãy chuyển đầu ngày và đầu ngày kế tiếp trong múi giờ nghiệp vụ thành `Instant` trước khi gọi use case; không mặc định mọi ngày đều là UTC nếu quy tắc kinh doanh dùng múi giờ khác.

### Phạm vi truy cập luôn là một điều kiện bắt buộc

Tra cứu phải giới hạn theo tenant/đơn vị hoặc phạm vi mà principal được phép xem. Điều kiện này khác bộ lọc tùy chọn: client không được bỏ qua nó. Hãy áp dụng `tenantId` trong query ở mọi đường gọi, và kiểm thử trường hợp người dùng tenant A không nhìn thấy đơn tenant B dù biết ID khách hàng hoặc mã đơn.

## 4. Phân trang offset với Page và Pageable

### Page index và size

Spring Data dùng page index bắt đầu từ `0`. Với `page=0&size=20`, query lấy 20 phần tử đầu tiên; `page=1&size=20` lấy phần tử tiếp theo theo thứ tự đã sắp xếp. API cần ghi rõ quy ước này vì một số UI hiển thị số trang từ 1.

Offset pagination thường được tạo bằng `PageRequest.of(page, size, sort)`. Không cho client gửi `size` tùy ý không giới hạn; page quá lớn hoặc size rất lớn có thể gây truy vấn tốn tài nguyên và response nặng. Đặt mặc định hợp lý, giới hạn tối đa và cân nhắc giới hạn page sâu.

### Sắp xếp ổn định với khóa phụ duy nhất

Phân trang cần thứ tự xác định. Nếu chỉ sort theo `createdAt`, nhiều đơn có thể cùng timestamp. Database không đảm bảo thứ tự tương đối giữa các hàng có giá trị sort bằng nhau nếu không có tiêu chí phụ. Vì vậy, luôn thêm khóa duy nhất làm tie-breaker, ví dụ `id`:

```java
private static Sort toSpringSort(OrderSort sort) {
    return switch (sort) {
        case CREATED_ASC -> Sort.by(
                Sort.Order.asc("createdAt"), Sort.Order.asc("id"));
        case TOTAL_DESC -> Sort.by(
                Sort.Order.desc("total"), Sort.Order.desc("id"));
        case ORDER_NUMBER_ASC -> Sort.by(
                Sort.Order.asc("orderNumber"), Sort.Order.asc("id"));
        case CREATED_DESC -> Sort.by(
                Sort.Order.desc("createdAt"), Sort.Order.desc("id"));
    };
}
```

Không chuyển trực tiếp chuỗi `sort` tùy ý từ client thành tên property hoặc SQL fragment. Dùng enum/allowlist để chỉ cho phép các trường đã hỗ trợ. `Sort` của Spring Data thường dùng property path của entity, không phải tên cột SQL; vẫn cần giới hạn property được phép và không nhận biểu thức SQL tự do.

### Page và Slice khác nhau

- `Page<T>` thường cung cấp `totalElements` và `totalPages`, nên Spring Data thường cần chạy thêm count query.
- `Slice<T>` tập trung vào `hasNext`/`hasPrevious`; adapter có thể lấy thêm một phần tử để biết còn dữ liệu hay không mà không cần tổng số chính xác.
- Một danh sách đơn giản với `limit` có thể đủ nếu UI không cần điều hướng trang.

Count query có thể đắt với bộ lọc phức tạp, join nhiều bảng hoặc dữ liệu lớn. Chỉ trả tổng số chính xác khi sản phẩm thực sự cần. Nếu giao diện chỉ có nút “Xem thêm”, `Slice` hoặc cursor pagination có thể phù hợp hơn.

## 5. Triển khai query ở tầng data access

### Projection thay vì trả entity

Với danh sách đơn hàng, chỉ cần một số cột. Spring Data JPA có thể ánh xạ kết quả sang interface projection:

```java
public interface OrderListProjection {
    UUID getId();
    String getOrderNumber();
    String getCustomerName();
    OrderStatus getStatus();
    BigDecimal getTotal();
    Instant getCreatedAt();
}
```

Projection này thuộc adapter persistence, không phải HTTP response. Repository Spring Data có thể khai báo query trả projection và count query tương ứng:

```java
public interface SpringDataOrderSearchRepository
        extends Repository<OrderEntity, UUID> {

    @Query(
        value = """
            select o.id as id,
                   o.orderNumber as orderNumber,
                   c.name as customerName,
                   o.status as status,
                   o.total as total,
                   o.createdAt as createdAt
              from OrderEntity o
              join o.customer c
             where o.tenantId = :tenantId
               and (:customerId is null or c.id = :customerId)
               and (:status is null or o.status = :status)
               and (:fromInclusive is null or o.createdAt >= :fromInclusive)
               and (:toExclusive is null or o.createdAt < :toExclusive)
            """,
        countQuery = """
            select count(o.id)
              from OrderEntity o
              join o.customer c
             where o.tenantId = :tenantId
               and (:customerId is null or c.id = :customerId)
               and (:status is null or o.status = :status)
               and (:fromInclusive is null or o.createdAt >= :fromInclusive)
               and (:toExclusive is null or o.createdAt < :toExclusive)
            """
    )
    Page<OrderListProjection> search(
            @Param("tenantId") UUID tenantId,
            @Param("customerId") UUID customerId,
            @Param("status") OrderStatus status,
            @Param("fromInclusive") Instant fromInclusive,
            @Param("toExclusive") Instant toExclusive,
            Pageable pageable);
}
```

Đây là JPQL minh họa với giả định entity `OrderEntity` có `tenantId`, `customer`, `orderNumber`, `status`, `total` và `createdAt`; quan hệ `customer` có `id` và `name`. Tên property phải khớp entity thực tế. Alias trong `select` cần khớp tên getter của projection. Các `@Param` làm rõ ánh xạ tên tham số; `Pageable` được dùng bên trong adapter và không xuất hiện trong application contract. Các import được lược bớt.

Biểu thức `(:parameter is null or field = :parameter)` dễ minh họa bộ lọc tùy chọn, nhưng với nhiều điều kiện hoặc database lớn, nó có thể làm optimizer khó chọn index tối ưu. Khi cần query động, cân nhắc Spring Data `Specification`, Criteria API, Querydsl hoặc custom repository để chỉ thêm predicate có giá trị. Tránh ghép chuỗi SQL/JPQL từ input không tin cậy.

### Adapter chuyển Page projection thành application result

```java
@Repository
class JpaOrderSearchAdapter implements OrderSearchPort {
    private final SpringDataOrderSearchRepository repository;

    JpaOrderSearchAdapter(SpringDataOrderSearchRepository repository) {
        this.repository = repository;
    }

    @Override
    public PageResult<OrderListItem> search(SearchOrdersQuery query) {
        var pageable = PageRequest.of(
                query.page(), query.size(), toSpringSort(query.sort()));

        var page = repository.search(
                query.tenantId(), query.customerId(), query.status(),
                query.createdFromInclusive(), query.createdToExclusive(),
                pageable);

        var items = page.getContent().stream()
                .map(row -> new OrderListItem(
                        row.getId(), row.getOrderNumber(), row.getCustomerName(),
                        row.getStatus(), row.getTotal(), row.getCreatedAt()))
                .toList();

        return new PageResult<>(items, page.getNumber(), page.getSize(),
                page.getTotalElements(), page.getTotalPages(), page.hasNext());
    }

    // toSpringSort như ví dụ allowlist ở phần trên.
}
```

`OrderSearchPort` là interface do application sở hữu, có phương thức nhận `SearchOrdersQuery` và trả `PageResult<OrderListItem>`. Adapter biết `Pageable`, `Page`, projection và entity; application không cần biết những kiểu đó. Projection giúp database chỉ trả các cột cần cho màn hình và tránh serialize entity/proxy ra ngoài.

Nếu query join collection one-to-many, một đơn có thể xuất hiện nhiều hàng. Khi đó cần xử lý `distinct`, grouping hoặc query riêng phù hợp; count query có thể phải dùng `count(distinct o.id)`. Không áp dụng `join fetch` một collection lớn cùng phân trang một cách tùy tiện: Hibernate có thể cảnh báo hoặc phải phân trang trong bộ nhớ, dẫn đến tải quá nhiều dữ liệu. Với danh sách, projection hoặc query hai bước thường dễ kiểm soát hơn.

## 6. Application service kiểm tra và điều phối

Application service giữ quy tắc use case và gọi port:

```java
public interface OrderSearchPort {
    PageResult<OrderListItem> search(SearchOrdersQuery query);
}

public interface SearchOrdersUseCase {
    PageResult<OrderListItem> execute(SearchOrdersQuery query);
}

@Service
public class SearchOrdersService implements SearchOrdersUseCase {
    private final OrderSearchPort orders;

    public SearchOrdersService(OrderSearchPort orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public PageResult<OrderListItem> execute(SearchOrdersQuery query) {
        if (query.page() < 0) {
            throw new InvalidOrderSearch("page phải lớn hơn hoặc bằng 0");
        }
        if (query.size() < 1 || query.size() > 100) {
            throw new InvalidOrderSearch("size phải nằm trong khoảng 1..100");
        }
        if (query.createdFromInclusive() != null
                && query.createdToExclusive() != null
                && !query.createdFromInclusive()
                        .isBefore(query.createdToExclusive())) {
            throw new InvalidOrderSearch("Khoảng thời gian không hợp lệ");
        }
        return orders.search(query);
    }
}
```

Validation ở controller giúp phản hồi sớm với lỗi cú pháp/giá trị request; application vẫn bảo vệ các điều kiện của use case vì nó có thể được gọi từ CLI, job hoặc message handler. `tenantId` cần được xác thực ở ranh giới tin cậy và không được thay bằng giá trị tùy ý từ client. Nếu ứng dụng có policy phân quyền chi tiết, use case cần kiểm tra quyền trên phạm vi dữ liệu trước khi truy vấn.

### Transaction đọc và giới hạn của `readOnly`

`@Transactional(readOnly = true)` thể hiện ý định của use case là đọc dữ liệu và có thể giúp transaction manager/provider tối ưu phù hợp. Đây thường là một hint/configuration; không nên xem nó như bảo đảm phổ quát rằng mọi lệnh ghi đều bị database chặn. Adapter tham gia transaction của application nếu cùng transaction manager và resource.

Một truy vấn `Page` luôn cần query lấy nội dung; Spring Data thường chạy thêm count query để tính tổng số, nhưng trong một số trường hợp có thể suy ra tổng số từ nội dung trang và bỏ qua câu count. Khi cả hai câu lệnh được chạy dưới isolation `READ_COMMITTED`, chúng có thể quan sát hai snapshot khác nhau nếu có transaction khác commit ở giữa. Vì vậy, `totalElements` và nội dung trang có thể không phản ánh đúng cùng một thời điểm tuyệt đối. Một transaction read-only không tự động đồng nghĩa với snapshot nhất quán; semantics phụ thuộc database, isolation level và transaction manager.

Nếu nghiệp vụ cần snapshot nhất quán giữa nội dung trang và count, cần chọn isolation/transaction semantics phù hợp với database cụ thể và đánh giá chi phí khóa/phiên bản. Nếu màn hình chấp nhận tổng số gần đúng hoặc thay đổi theo thời gian, có thể dùng `Slice` để tránh count query. Hãy ghi rõ hợp đồng thay vì hứa một mức nhất quán mà implementation không bảo đảm.

## 7. DTO, projection và tránh N+1 query

### Chọn đúng dữ liệu cần trả

Một DTO danh sách nên chứa các trường UI cần, ví dụ mã đơn, tên khách hàng, trạng thái, tổng tiền và ngày tạo. Không trả:

- Entity có lazy collection hoặc proxy ORM.
- Quan hệ nội bộ như danh sách payment/log nếu màn hình không dùng.
- Field nhạy cảm như thông tin thanh toán hoặc địa chỉ riêng nếu caller không có quyền và không cần hiển thị.
- Toàn bộ entity graph chỉ để lấy vài thuộc tính.

Projection ở query có thể giảm lượng cột và object phải tạo. Nếu cần domain model đầy đủ để thực hiện hành vi nghiệp vụ, dùng repository/aggregate phù hợp; với màn hình đọc, read model/DTO thường tiết kiệm hơn.

### Nhận diện N+1

Nếu query lấy 20 đơn hàng, sau đó code gọi `order.getCustomer().getName()` cho từng entity và quan hệ customer chưa được tải, ORM có thể phát sinh một truy vấn cho danh sách và thêm nhiều truy vấn cho từng customer. Đây là mẫu N+1.

Với trang danh sách, có thể giải quyết bằng:

- Projection query join đúng quan hệ many-to-one cần hiển thị.
- DTO constructor projection hoặc interface projection.
- Entity graph/fetch plan cho quan hệ cần thiết, nếu vẫn trả entity nội bộ.
- Batch fetching khi phù hợp và đã đo hiệu quả.

Không dùng fetch join collection tùy tiện với `Pageable`. Join collection làm nhân số hàng, gây trùng root entity và làm count/phân trang phức tạp. Nếu cần dữ liệu con, cân nhắc query trang ID trước rồi query dữ liệu con cho tập ID đó, hoặc trả projection được thiết kế phù hợp.

## 8. Offset pagination, keyset pagination và dữ liệu thay đổi đồng thời

### Offset pagination dễ dùng nhưng trang sâu có thể đắt

Offset pagination thường dịch thành `OFFSET` và `LIMIT`. Với trang đầu, database có thể lấy nhanh một lượng nhỏ hàng; với offset rất lớn, database vẫn có thể phải duyệt/bỏ qua nhiều hàng trước khi trả kết quả. Index phù hợp với bộ lọc và thứ tự sắp xếp có thể cải thiện, nhưng không xóa mọi chi phí của offset sâu.

Một index có thể cân nhắc là tổ hợp các trường lọc phổ biến và sort, ví dụ `(tenant_id, created_at, id)`; index thực tế phải dựa trên query plan, selectivity và workload. Không tạo index cho mọi tổ hợp bộ lọc vì index tăng chi phí ghi, dung lượng và bảo trì.

### Thứ tự ổn định không tạo snapshot

Thêm `id` làm tie-breaker bảo đảm thứ tự xác định tại một thời điểm. Nhưng nếu đơn mới được chèn hoặc trạng thái/thời gian sắp xếp thay đổi giữa hai request, offset của các hàng có thể dịch chuyển. Người dùng có thể thấy một đơn lặp lại ở trang kế tiếp hoặc bỏ qua một đơn.

Đây không nhất thiết là bug nếu màn hình là danh sách vận hành theo dữ liệu mới nhất và chấp nhận kết quả thay đổi. Nếu nghiệp vụ cần duyệt một tập kết quả ổn định, cần xác định thêm semantics: snapshot/version, thời điểm chụp, hoặc cursor dựa trên khóa sắp xếp.

### Keyset/cursor pagination

Keyset pagination dùng giá trị của hàng cuối trang trước làm cursor, thay vì bỏ qua một số lượng lớn hàng. Ví dụ sắp xếp theo `(createdAt DESC, id DESC)`, trang kế tiếp tìm hàng có cặp khóa nhỏ hơn cặp cuối cùng:

```sql
select id, order_number, status, created_at
from orders
where tenant_id = :tenantId
  and (
       created_at < :lastCreatedAt
       or (created_at = :lastCreatedAt and id < :lastId)
  )
order by created_at desc, id desc
fetch first :size rows only
```

Đây là SQL minh họa; cú pháp giới hạn số hàng tùy database. Keyset thường hiệu quả hơn ở trang sâu khi có index phù hợp và giảm hiện tượng dịch chuyển do bản ghi mới chèn trước cursor. Tuy nhiên, nó không tự tạo snapshot tuyệt đối: nếu trường sort của một bản ghi thay đổi, bản ghi vẫn có thể di chuyển qua cursor. Cursor cần mã hóa hoặc ký nếu được đưa ra API công khai, và cần gắn với filter/sort để không bị tái sử dụng sai truy vấn.

Offset phù hợp khi người dùng cần nhảy đến trang bất kỳ và dữ liệu không quá lớn; keyset phù hợp khi duyệt tuần tự, dữ liệu lớn hoặc trang sâu. Chọn theo trải nghiệm và semantics cần thiết, không chỉ theo thói quen.

## 9. Kiểm thử chức năng và tính nhất quán

Một bộ test tốt cần xác nhận cả filter, paging, DTO và các trường hợp dữ liệu thay đổi:

| Loại kiểm thử | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Unit test application | Validation và điều phối đúng | Từ chối page âm, size vượt giới hạn, from không trước to; gọi port với tenant từ actor |
| Integration test repository | Predicate và mapping đúng với database | Kết hợp status/customer/date; projection trả đủ trường; count khớp trong fixture ổn định |
| Pagination test | Thứ tự ổn định và page metadata đúng | Nhiều đơn cùng `createdAt` vẫn có thứ tự theo `id`; trang 0/1 không trùng khi dữ liệu không đổi |
| Sort allowlist test | Chỉ trường sắp xếp được hỗ trợ mới được dùng | `CREATED_DESC` hợp lệ; tên property tùy ý bị từ chối |
| Tenant/security test | Không đọc dữ liệu ngoài phạm vi | Tenant A không nhận đơn của tenant B khi bỏ filter customer/status |
| DTO/API test | Response không lộ entity hoặc field ngoài hợp đồng | JSON chỉ có trường được công bố; không có lazy proxy/quan hệ persistence |
| Concurrency/consistency test | Hành vi khi có insert/update giữa các lần đọc được hiểu rõ | Xác nhận offset có thể dịch; keyset theo cursor hoạt động theo hợp đồng |

Integration test nên dùng database gần với production, đặc biệt khi dựa vào JPQL, collation, index, isolation hoặc query plan cụ thể. H2 có thể hữu ích cho một số test nhanh nhưng không đảm bảo tái hiện mọi semantics của PostgreSQL/MySQL. Test concurrency cần điều khiển thời điểm commit giữa các truy vấn; chỉ gọi API hai lần tuần tự không chứng minh snapshot behavior.

## 10. Hiệu năng và khả năng vận hành

### Đọc query plan và đo đúng workload

Với query tra cứu thường dùng, hãy kiểm tra `EXPLAIN`/query plan trên dữ liệu đủ đại diện. Xem database có dùng index cho tenant, status, customer và sort hay không; số hàng ước tính so với thực tế; chi phí join; và count query có tốn hơn query nội dung không.

Theo dõi ít nhất:

- Latency p50/p95/p99 của endpoint tra cứu.
- Số request và tỷ lệ lỗi.
- Thời gian query nội dung và count query nếu instrument riêng.
- Kích thước trang và tỷ lệ truy vấn trang sâu.
- Connection pool wait, database CPU, lock wait và số hàng đọc.
- Số query phát sinh trên mỗi request để nhận diện N+1.

Đừng chỉ đo thời gian của method repository nếu method đó còn chờ connection pool hoặc gọi nhiều query bên trong. Trace và query log có kiểm soát giúp phân biệt thời gian adapter, database và serialization.

### Giới hạn tài nguyên đầu vào

Một endpoint tìm kiếm nên giới hạn `size`, page sâu hoặc khoảng thời gian quá rộng nếu workload cần. Có thể đặt timeout phù hợp, giới hạn số filter, và từ chối sort không hỗ trợ. Các giới hạn này cần được thể hiện trong API contract để client biết cách sử dụng.

## 11. Những sai lầm thường gặp

1. **Trả `Page<OrderEntity>` trực tiếp.** API bị gắn với entity, lazy relation và schema. Trả DTO/read model riêng.
2. **Cho client chọn mọi property để sort.** Điều này làm query khó kiểm soát và có thể gây lỗi khi property không hợp lệ. Dùng enum/allowlist.
3. **Không có tie-breaker trong sort.** Các hàng có cùng giá trị sort có thể đổi thứ tự giữa các request. Thêm khóa duy nhất.
4. **Cho `size` không giới hạn.** Một request có thể kéo quá nhiều hàng và làm cạn bộ nhớ/connection. Đặt max size và kiểm soát trang sâu.
5. **Dùng `Page` dù UI không cần tổng số.** Count query có thể tốn kém. Dùng `Slice` hoặc cursor nếu chỉ cần biết còn dữ liệu.
6. **Dùng fetch join collection với phân trang mà không kiểm tra.** Kết quả có thể nhân hàng hoặc buộc phân trang trong bộ nhớ. Dùng projection hoặc query hai bước.
7. **Tin rằng `readOnly = true` bảo đảm snapshot.** Isolation thực tế phụ thuộc database và transaction manager; READ_COMMITTED có thể cho hai câu query thấy hai trạng thái khác nhau.
8. **Cho rằng sort ổn định đồng nghĩa dữ liệu bất biến giữa các trang.** Tie-breaker chỉ ổn định thứ tự cho tập dữ liệu tại thời điểm query; insert/update vẫn có thể làm offset dịch chuyển.
9. **Lấy tenant từ query parameter.** Caller có thể sửa tenant ID. Phạm vi truy cập phải đến từ principal đã xác thực và policy server-side.
10. **Dùng một DTO khổng lồ cho mọi use case.** DTO nên phản ánh nhu cầu của endpoint/màn hình; query khác có thể cần projection khác.

## 12. Checklist thiết kế một API tra cứu đơn hàng

Trước khi phát hành endpoint, hãy xác nhận:

- Bộ lọc tùy chọn và khoảng thời gian có semantics rõ; timezone được quy định.
- Tenant/ownership scope được lấy từ danh tính đã xác thực, không tin giá trị client gửi.
- Page index, size mặc định, size tối đa và sort allowlist được validate.
- Thứ tự có tie-breaker duy nhất để kết quả phân trang xác định.
- Application contract không phụ thuộc `Page`, `Pageable`, `Sort` hoặc entity JPA nếu mục tiêu là độc lập persistence.
- Adapter query chỉ lấy trường cần thiết và trả projection/DTO phù hợp.
- Count query được đánh giá; dùng `Slice`/cursor nếu không cần tổng số chính xác.
- Không phát sinh N+1 hoặc fetch collection không phù hợp với pagination.
- Transaction/isolation semantics và ảnh hưởng của ghi đồng thời được hiểu và mô tả đúng.
- Unit, integration, API contract, security và consistency tests bao phủ các trường hợp quan trọng.

Thiết kế tra cứu đơn hàng tốt không chỉ là thêm `WHERE`, `LIMIT` và `OFFSET`. Nó là một hợp đồng xuyên tầng: presentation nhận tiêu chí hợp lệ, application áp dụng phạm vi use case, adapter thực hiện query hiệu quả và DTO trả đúng dữ liệu cần thiết. Khi chọn rõ semantics của lọc, phân trang, sắp xếp và nhất quán, hệ thống có thể mở rộng màn hình tra cứu mà không làm lộ entity ORM hoặc tạo ra những cam kết dữ liệu mà database không bảo đảm.
