# Tìm kiếm theo định danh, điều kiện lọc, phân trang và sắp xếp

Tầng truy cập dữ liệu không chỉ đọc một bản ghi theo khóa chính hoặc lưu một đối tượng. Trong ứng dụng thực tế, nó còn phải phục vụ các màn hình danh sách và chức năng tìm kiếm: tìm đơn hàng theo mã, lọc theo trạng thái và khoảng thời gian, sắp xếp theo ngày tạo hoặc tổng tiền, rồi chia kết quả thành từng trang.

Thiết kế tốt cho các truy vấn này giúp ứng dụng trả đúng dữ liệu, tránh tải quá nhiều bản ghi, giữ kết quả ổn định khi người dùng chuyển trang và bảo vệ hệ thống trước những tham số truy vấn không hợp lệ. Bài học này tập trung vào cách tầng truy cập dữ liệu thực hiện các nhu cầu đó trong ứng dụng Java/Spring. Đây là một phần của việc tổ chức phần mềm theo kiến trúc phân tầng: tầng trình bày nhận tham số, tầng ứng dụng diễn đạt nhu cầu của use case, còn repository và adapter dữ liệu chuyển nhu cầu thành truy vấn phù hợp với kho lưu trữ.

## 1. Tìm kiếm theo định danh

Mỗi bản ghi thường có một định danh ổn định, chẳng hạn UUID hoặc số nguyên tăng dần. Tìm theo định danh thường là truy vấn đơn giản và có thể tận dụng chỉ mục khóa chính của cơ sở dữ liệu.

Với Spring Data JPA, repository kế thừa `JpaRepository` đã có sẵn `findById`, `existsById` và `deleteById`:

```java
public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
}
```

Application service có thể dùng `findById` để lấy bản ghi và chuyển trường hợp không tồn tại thành kết quả nghiệp vụ phù hợp:

```java
@Service
class GetOrderService {
    private final OrderRepository orders;

    GetOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderDetails get(UUID orderId) {
        var order = orders.findById(orderId)
                .orElseThrow(OrderNotFoundException::new);
        return OrderDetails.from(order);
    }
}
```

`findById` trả về `Optional` vì bản ghi có thể không tồn tại. Tầng ứng dụng quyết định ý nghĩa của trường hợp đó đối với use case; tầng trình bày có thể ánh xạ `OrderNotFoundException` thành HTTP `404 Not Found`. Không nên trả một đối tượng rỗng hoặc `null` khiến tầng gọi phải đoán ý nghĩa.

Định danh trong URL cũng không mặc nhiên chứng minh người gọi được phép xem bản ghi. Với dữ liệu nhiều khách hàng hoặc nhiều tổ chức, cần áp dụng điều kiện sở hữu hoặc tenant trong truy vấn, hay kiểm tra quyền truy cập trước khi trả kết quả. Tránh để một người dùng đoán UUID hoặc ID tuần tự rồi đọc dữ liệu của người khác. Chính sách bảo mật phải được thực thi ở phía máy chủ.

Đôi khi người dùng tìm theo mã nghiệp vụ như `ORD-2026-00125`, không phải khóa chính của bảng. Khi đó nên đặt tên phương thức thể hiện rõ trường tìm kiếm:

```java
public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
    Optional<OrderEntity> findByOrderNumber(String orderNumber);
}
```

Nếu mã đơn hàng chỉ duy nhất trong phạm vi một tenant, chữ ký truy vấn cần mang cả tenant hoặc phạm vi tương ứng, ví dụ `findByTenantIdAndOrderNumber(...)`. Ràng buộc duy nhất ở cơ sở dữ liệu cũng cần phản ánh cùng phạm vi đó. Không nên giả định mã hiển thị luôn duy nhất toàn hệ thống.

## 2. Lọc theo nhiều điều kiện

Một màn hình danh sách đơn hàng có thể cho phép lọc theo khách hàng, trạng thái, ngày tạo và khoảng tổng tiền. Các điều kiện có thể được kết hợp tùy lựa chọn của người dùng. Ví dụ:

```text
GET /api/orders?status=PAID&from=2026-10-01T00:00:00Z&before=2026-11-01T00:00:00Z&minTotal=100000
```

Tầng trình bày đọc query parameter và chuyển chúng thành một đối tượng tiêu chí tìm kiếm. Đối tượng này mô tả nhu cầu của use case, không phải một câu SQL hoặc cấu trúc bảng:

```java
public record OrderSearchCriteria(
        OrderStatus status,
        Instant createdFrom,
        Instant createdBefore,
        BigDecimal minTotal,
        BigDecimal maxTotal,
        UUID customerId) {
}
```

Trong ví dụ, `createdFrom` là mốc bao gồm và `createdBefore` là mốc kết thúc không bao gồm. Dùng khoảng thời gian nửa mở `[from, before)` giúp tránh lỗi ở ranh giới ngày do độ chính xác timestamp khác nhau. Nếu API nhận ngày lịch, cần quy định múi giờ áp dụng (thường là múi giờ nghiệp vụ hoặc UTC) và chuyển ngày bắt đầu/kết thúc thành `Instant` nhất quán.

Với điều kiện đơn giản, Spring Data có thể suy ra truy vấn từ tên phương thức:

```java
Page<OrderEntity> findByCustomerIdAndStatus(
        UUID customerId,
        OrderStatus status,
        Pageable pageable);
```

Cách này dễ đọc khi số điều kiện ít và cấu trúc truy vấn ổn định. Nếu có nhiều bộ lọc tùy chọn, tên phương thức sẽ dài và sinh ra nhiều tổ hợp. Khi đó có thể dùng `JpaSpecificationExecutor` để xây dựng điều kiện động:

```java
public interface OrderRepository extends
        JpaRepository<OrderEntity, UUID>,
        JpaSpecificationExecutor<OrderEntity> {
}
```

Mỗi tiêu chí có thể tạo một `Specification` nhỏ:

```java
final class OrderSpecifications {
    private OrderSpecifications() {}

    static Specification<OrderEntity> hasStatus(OrderStatus status) {
        return (root, query, cb) -> cb.equal(root.get("status"), status);
    }

    static Specification<OrderEntity> createdAtOrAfter(Instant from) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.get("createdAt"), from);
    }

    static Specification<OrderEntity> createdBefore(Instant before) {
        return (root, query, cb) ->
                cb.lessThan(root.get("createdAt"), before);
    }

    static Specification<OrderEntity> belongsToCustomer(UUID customerId) {
        return (root, query, cb) ->
                cb.equal(root.get("customerId"), customerId);
    }
}
```

Application service kết hợp những điều kiện thực sự được cung cấp:

```java
@Service
class SearchOrdersService {
    private final OrderRepository orders;

    SearchOrdersService(OrderRepository orders) {
        this.orders = orders;
    }

    Page<OrderEntity> search(OrderSearchCriteria criteria, Pageable pageable) {
        Specification<OrderEntity> spec =
                (root, query, cb) -> cb.conjunction();

        if (criteria.status() != null) {
            spec = spec.and(OrderSpecifications.hasStatus(criteria.status()));
        }
        if (criteria.createdFrom() != null) {
            spec = spec.and(
                    OrderSpecifications.createdAtOrAfter(criteria.createdFrom()));
        }
        if (criteria.createdBefore() != null) {
            spec = spec.and(
                    OrderSpecifications.createdBefore(criteria.createdBefore()));
        }
        if (criteria.customerId() != null) {
            spec = spec.and(
                    OrderSpecifications.belongsToCustomer(criteria.customerId()));
        }

        return orders.findAll(spec, pageable);
    }
}
```

Đây là ví dụ rút gọn: một ứng dụng thực tế cần xác thực các giá trị trước khi tạo criteria, kiểm tra `createdFrom` nhỏ hơn `createdBefore`, `minTotal` không vượt `maxTotal`, và bổ sung điều kiện khoảng tiền nếu API cung cấp các trường đó. Nếu tổng tiền được lưu ở bảng khác hoặc phải tính từ dòng hàng, cần chọn cách truy vấn phù hợp với mô hình dữ liệu và hiệu năng; không nên mặc định rằng có thể lọc trên một thuộc tính không tồn tại trong entity.

Với truy vấn phức tạp hơn, có thể dùng Criteria API, QueryDSL, JPQL hoặc native SQL. Chọn công cụ theo độ phức tạp, khả năng bảo trì và hiệu năng; không cần đưa mọi truy vấn vào `Specification`.

## 3. Phân trang: chỉ lấy phần dữ liệu cần thiết

Một bảng danh sách có thể chứa hàng trăm nghìn đơn hàng. Nếu mỗi lần mở trang đều tải tất cả bản ghi về bộ nhớ rồi mới cắt thành 20 phần tử, ứng dụng sẽ tốn tài nguyên và truyền dữ liệu không cần thiết. Phân trang nên được thực hiện tại tầng truy cập dữ liệu để cơ sở dữ liệu chỉ trả phần kết quả được yêu cầu.

Spring Data dùng `Pageable` để mô tả số trang, kích thước trang và thứ tự sắp xếp:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.DESC, "createdAt"));

Page<OrderEntity> result = orders.findAll(pageable);
```

`PageRequest.of(0, 20, ...)` yêu cầu trang đầu tiên, tối đa 20 phần tử. Spring Data mặc định đánh số trang từ 0. Nếu API công khai dùng số trang bắt đầu từ 1 cho thuận tiện người dùng, tầng trình bày cần chuyển đổi một cách nhất quán trước khi tạo `PageRequest`.

Một `Page<T>` thường cung cấp:

- `getContent()`: danh sách phần tử trong trang hiện tại.
- `getNumber()` và `getSize()`: số trang và kích thước trang.
- `getTotalElements()` và `getTotalPages()`: tổng số phần tử và tổng số trang.
- `hasNext()` và `hasPrevious()`: thông tin điều hướng.

Để tính tổng số phần tử, Spring Data thường thực hiện thêm một truy vấn `COUNT` ngoài truy vấn lấy nội dung. Với truy vấn join hoặc bộ lọc phức tạp, truy vấn đếm có thể tốn kém. Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, `Slice<T>` có thể phù hợp hơn vì không cần cung cấp tổng số trang; framework thường lấy thêm một bản ghi để xác định có trang tiếp theo.

Repository có thể khai báo:

```java
Page<OrderEntity> findByStatus(OrderStatus status, Pageable pageable);

Slice<OrderEntity> findByCustomerId(UUID customerId, Pageable pageable);
```

Không nên nhận kích thước trang tùy ý mà không giới hạn. Một client gửi `size=1000000` có thể gây truy vấn nặng và tạo áp lực bộ nhớ. API nên đặt kích thước mặc định và mức tối đa, chẳng hạn mặc định 20 và tối đa 100, theo nhu cầu sản phẩm và khả năng hệ thống.

## 4. Sắp xếp có kiểm soát và ổn định

Sắp xếp xác định thứ tự bản ghi trước khi chia trang. Ví dụ người dùng muốn đơn hàng mới nhất xuất hiện trước:

```java
Sort sort = Sort.by(Sort.Order.desc("createdAt"));
Pageable pageable = PageRequest.of(0, 20, sort);
```

Một điểm quan trọng: thứ tự cần có tính ổn định. Nếu nhiều đơn hàng có cùng `createdAt`, cơ sở dữ liệu có thể trả chúng theo thứ tự khác nhau giữa các lần truy vấn. Khi người dùng chuyển trang, một bản ghi có thể lặp lại hoặc bị bỏ qua. Hãy thêm một khóa phân biệt làm tiêu chí phụ:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));
Pageable pageable = PageRequest.of(0, 20, sort);
```

Trong Spring Data, thuộc tính dùng trong `Sort` thường là tên thuộc tính entity, không phải tên cột SQL. Không truyền trực tiếp một chuỗi sắp xếp tùy ý từ client vào truy vấn. Hãy ánh xạ các lựa chọn công khai như `createdAt`, `total` hoặc `status` sang danh sách thuộc tính được phép. Cách này ngăn client yêu cầu sắp xếp theo trường nội bộ hoặc đường dẫn quan hệ không được công khai, đồng thời giúp kiểm soát chi phí truy vấn.

Ví dụ tầng trình bày tạo `Pageable` với allowlist:

```java
private static final Map<String, String> SORT_FIELDS = Map.of(
        "created", "createdAt",
        "total", "totalAmount",
        "status", "status");

Pageable toPageable(int page, int size, String sortKey, String direction) {
    if (page < 0 || page > 10_000) {
        throw new IllegalArgumentException("page không hợp lệ");
    }
    int safeSize = Math.min(Math.max(size, 1), 100);

    String property = SORT_FIELDS.get(sortKey);
    if (property == null) {
        throw new IllegalArgumentException("sortKey không hợp lệ");
    }
    if (!"asc".equalsIgnoreCase(direction) && !"desc".equalsIgnoreCase(direction)) {
        throw new IllegalArgumentException("direction không hợp lệ");
    }
    Sort.Direction order = "asc".equalsIgnoreCase(direction)
            ? Sort.Direction.ASC : Sort.Direction.DESC;

    Sort sort = Sort.by(order, property);
    if (!"id".equals(property)) {
        sort = sort.and(Sort.by(Sort.Direction.DESC, "id"));
    }
    return PageRequest.of(page, safeSize, sort);
}
```

Đây là mã minh họa; trong ứng dụng thật, giới hạn trang và kích thước cần được chọn theo khả năng hệ thống và hợp đồng API. Ví dụ từ chối `page` vượt giới hạn, `size` được chặn trong khoảng 1–100, còn `sortKey` và `direction` phải thuộc tập giá trị được hỗ trợ. Allowlist phải được duy trì cùng với các thuộc tính được công khai của API.

Hãy quy định rõ cách xử lý giá trị `null`, thứ tự chữ hoa/chữ thường và collation nếu các trường đó được sắp xếp. Hành vi có thể khác nhau giữa các hệ quản trị cơ sở dữ liệu. Với trường hợp nghiệp vụ yêu cầu thứ tự cụ thể, hãy cấu hình hoặc biểu diễn quy tắc đó rõ ràng trong truy vấn.

## 5. Offset pagination và keyset pagination

`PageRequest` thường được triển khai bằng phân trang offset/limit. Ví dụ trang 3 với 20 phần tử có thể tương đương `LIMIT 20 OFFSET 60`. Cách này dễ hiểu, cho phép nhảy tới một trang bất kỳ và phù hợp với nhiều màn hình quản trị có quy mô vừa phải.

Tuy nhiên, offset lớn có thể tốn kém: cơ sở dữ liệu vẫn phải tìm hoặc bỏ qua nhiều hàng trước khi trả phần cần thiết. Ngoài ra, khi dữ liệu mới được chèn hoặc bản ghi bị xóa giữa hai lần người dùng chuyển trang, vị trí offset dịch chuyển và kết quả có thể lặp hoặc thiếu dù đã sắp xếp ổn định.

Với danh sách rất lớn hoặc luồng cuộn liên tục, có thể dùng **keyset pagination** (còn gọi là seek pagination). Thay vì gửi số trang, client gửi cursor chứa giá trị sắp xếp của phần tử cuối trang trước. Nếu sắp xếp theo `createdAt DESC, id DESC`, trang tiếp theo lấy các bản ghi thỏa điều kiện:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize
```

Cursor gồm cả `createdAt` và `id` vì `createdAt` có thể trùng. Với thứ tự tăng dần, điều kiện so sánh đổi tương ứng. Khi có nhiều trường sắp xếp hoặc có giá trị null, logic cursor phải phản ánh chính xác thứ tự đó.

| Tiêu chí | Offset pagination | Keyset pagination |
|---|---|---|
| Cách yêu cầu trang | Số trang hoặc offset | Cursor từ phần tử cuối trang trước |
| Nhảy tới trang tùy ý | Dễ hỗ trợ | Không thuận tiện; thường phải đi tuần tự |
| Trang rất sâu | Có thể chậm do offset lớn | Thường hiệu quả hơn nếu có chỉ mục phù hợp |
| Dữ liệu thay đổi giữa các lần tải | Có thể lặp hoặc bỏ sót do dịch chuyển offset | Ổn định hơn theo khóa cursor, nhưng vẫn cần hiểu dữ liệu mới và thay đổi khóa sắp xếp |
| Phù hợp | Bảng quản trị, danh sách vừa, cần tổng số trang | Feed lớn, cuộn vô hạn, dữ liệu lớn và thứ tự có chỉ mục |

Keyset không tự tạo ra một snapshot nhất quán tuyệt đối. Nếu một bản ghi thay đổi giá trị sắp xếp trong lúc người dùng đang duyệt, nó vẫn có thể chuyển vị trí. Nếu cần tính nhất quán theo snapshot, phải thiết kế thêm theo khả năng transaction hoặc snapshot của hệ quản trị dữ liệu. Cursor cũng nên được mã hóa hoặc ký nếu chứa thông tin nội bộ và cần chống sửa đổi.

## 6. Chọn Page, Slice hay projection

Không phải màn hình nào cũng cần tải toàn bộ entity. Một danh sách chỉ hiển thị mã đơn, ngày tạo, trạng thái và tổng tiền có thể dùng projection để lấy đúng các cột cần thiết:

```java
public interface OrderListItem {
    UUID getId();
    String getOrderNumber();
    OrderStatus getStatus();
    Instant getCreatedAt();
    BigDecimal getTotalAmount();
}

public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
    Page<OrderListItem> findByCustomerId(
            UUID customerId,
            Pageable pageable);
}
```

Projection có thể giảm lượng dữ liệu đọc và tránh tải quan hệ không cần thiết. Với truy vấn tùy chỉnh, có thể dùng DTO projection qua JPQL constructor expression hoặc native query nếu cần. Hãy cân nhắc fetch strategy và N+1 query: truy vấn danh sách entity rồi truy cập lazy relationship từng dòng có thể tạo ra nhiều truy vấn phụ. Không nên giải quyết N+1 bằng cách fetch join tùy tiện trên collection khi phân trang, vì join có thể nhân số dòng và làm sai phân trang hoặc buộc framework xử lý rất tốn kém. Projection hoặc truy vấn hai bước có thể phù hợp hơn.

Nếu cần tổng số kết quả, dùng `Page`; nếu chỉ cần biết có trang tiếp theo, dùng `Slice`; nếu API theo cursor, trả cursor kế tiếp cùng danh sách. Hợp đồng API nên chỉ đưa metadata mà client thực sự cần.

## 7. Hiệu năng truy vấn và chỉ mục

Các bộ lọc và cách sắp xếp thường quyết định chỉ mục cần thiết. Nếu truy vấn thường xuyên lọc theo `customer_id` và `status`, sau đó sắp xếp theo `created_at`, một chỉ mục ghép như `(customer_id, status, created_at, id)` có thể hữu ích. Tuy nhiên, thứ tự cột trong chỉ mục phụ thuộc mẫu truy vấn, độ chọn lọc và hệ quản trị dữ liệu; không có một chỉ mục tối ưu cho mọi tổ hợp.

Hãy xem execution plan bằng công cụ của hệ quản trị cơ sở dữ liệu trên dữ liệu gần với quy mô thực tế. Chú ý full table scan, sort lớn, join tốn kém, truy vấn count và chỉ mục không được sử dụng. Tránh tạo chỉ mục cho mọi trường lọc vì mỗi chỉ mục tăng dung lượng và chi phí ghi/cập nhật.

Một số lưu ý khác:

- Tránh truy vấn `LIKE '%keyword%'` trên bảng lớn nếu chưa đánh giá hiệu năng; wildcard đầu chuỗi thường khó tận dụng B-tree index. Có thể cần full-text search, trigram hoặc công cụ tìm kiếm chuyên dụng.
- Nếu hỗ trợ tìm kiếm không phân biệt hoa thường, thống nhất cách chuẩn hóa dữ liệu hoặc dùng chức năng/collation phù hợp; cách gọi `LOWER(column)` có thể ảnh hưởng khả năng dùng chỉ mục thông thường.
- Escape ký tự wildcard `%` và `_` nếu người dùng kỳ vọng tìm chuỗi literal, hoặc quy định rõ chúng được hiểu là ký tự đại diện.
- Giới hạn độ dài từ khóa, số điều kiện và kích thước trang để tránh truy vấn quá rộng.
- Chỉ chọn các cột cần thiết và tránh tải toàn bộ quan hệ khi danh sách chỉ cần vài trường.

## 8. Xác thực tham số và bảo vệ truy vấn

Tham số tìm kiếm là đầu vào không đáng tin cậy. Tầng trình bày cần xác thực kiểu dữ liệu, enum, ngày tháng, khoảng số, số trang, kích thước trang và lựa chọn sort. Tầng ứng dụng có thể kiểm tra tính hợp lệ theo use case, chẳng hạn khoảng ngày tối đa hoặc phạm vi dữ liệu người dùng được phép tìm. Tầng truy cập dữ liệu phải dùng tham số bind hoặc API truy vấn an toàn; không ghép chuỗi SQL từ đầu vào client.

Các tên thuộc tính hoặc hướng sắp xếp thường không thể bind như giá trị SQL thông thường. Vì vậy, phải ánh xạ sort key qua allowlist như ví dụ trên. Với tenant hoặc quyền sở hữu, điều kiện phạm vi phải được thêm vào truy vấn từ ngữ cảnh xác thực phía máy chủ, không nhận tenant ID tùy ý từ client rồi tin tưởng.

Ví dụ controller có thể nhận tham số rồi chuyển thành criteria và pageable:

```java
@RestController
@RequestMapping("/api/orders")
class OrderSearchController {
    private final SearchOrdersUseCase searchOrders;

    OrderSearchController(SearchOrdersUseCase searchOrders) {
        this.searchOrders = searchOrders;
    }

    @GetMapping
    Page<OrderListResponse> search(
            @RequestParam(required = false) OrderStatus status,
            @RequestParam(required = false) Instant from,
            @RequestParam(required = false) Instant before,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        var criteria = new OrderSearchCriteria(
                status, from, before, null, null, null);
        var pageable = PageRequest.of(
                Math.max(page, 0), Math.min(Math.max(size, 1), 100),
                Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));

        return searchOrders.search(criteria, pageable)
                .map(OrderListResponse::from);
    }
}
```

Ví dụ này lược bỏ xử lý lỗi tham số, xác thực người dùng và allowlist sort tùy chọn. Một ứng dụng hoàn chỉnh nên gom việc tạo `Pageable` vào thành phần có trách nhiệm rõ ràng, trả `400 Bad Request` khi tham số sai theo hợp đồng API, đồng thời áp dụng phạm vi tenant/authorization trong use case hoặc truy vấn. Controller không nên tự xây dựng SQL hay chứa quy tắc nghiệp vụ.

## 9. Kiểm thử tìm kiếm, lọc và phân trang

Kiểm thử cần xác nhận cả nội dung và metadata của kết quả:

| Loại kiểm thử | Nội dung cần xác nhận | Ví dụ |
|---|---|---|
| Unit test criteria/use case | Kết hợp điều kiện tùy chọn và từ chối khoảng không hợp lệ | Chỉ lọc trạng thái khi status được cung cấp |
| Repository integration test | Truy vấn đúng với cơ sở dữ liệu thực tế hoặc tương thích | Lọc theo trạng thái và khoảng thời gian trả đúng bản ghi |
| Pagination test | Số phần tử mỗi trang, tổng phần tử, trang kế tiếp | 45 kết quả với size 20 tạo ba trang |
| Sorting test | Thứ tự tăng/giảm và tie-breaker | Hai đơn cùng ngày được sắp theo ID ổn định |
| Security test | Người dùng không đọc dữ liệu ngoài phạm vi | Tenant A không nhận đơn hàng của tenant B |
| Validation test | Tham số sai bị từ chối rõ ràng | `size` vượt giới hạn hoặc `from` sau `before` trả lỗi |

Nên dùng database test gần với hệ quản trị đang chạy trong production khi truy vấn phụ thuộc collation, kiểu dữ liệu, hàm SQL hoặc execution plan đặc thù. Test bằng H2 có thể hữu ích cho một số trường hợp, nhưng không bảo đảm hành vi giống PostgreSQL, MySQL hay SQL Server ở mọi chi tiết.

## 10. Chọn cách truy vấn theo nhu cầu thực tế

| Nhu cầu | Cách tiếp cận phù hợp |
|---|---|
| Tìm một bản ghi theo khóa chính | `findById` |
| Tìm theo một vài trường cố định | Derived query như `findByOrderNumber` hoặc `findByCustomerIdAndStatus` |
| Bộ lọc tùy chọn kết hợp động | `Specification`, Criteria API hoặc QueryDSL |
| Danh sách cần tổng số trang | `Page<T>` và `Pageable` |
| Danh sách chỉ cần biết còn dữ liệu | `Slice<T>` |
| Danh sách rất lớn, duyệt tuần tự | Keyset/cursor pagination |
| Màn hình chỉ cần một vài trường | Projection hoặc DTO query |
| Truy vấn đặc thù, cần tối ưu SQL rõ ràng | JPQL hoặc native SQL có tham số an toàn |

Không có một cơ chế duy nhất phù hợp với mọi truy vấn. Bắt đầu từ hợp đồng mà use case và giao diện thực sự cần, sau đó chọn cách triển khai dễ hiểu và đo được hiệu năng. Tìm theo định danh cần rõ ràng về quyền truy cập; lọc cần có ngữ nghĩa ổn định; phân trang cần giới hạn và thứ tự xác định; sắp xếp cần allowlist; truy vấn lớn cần xem xét chỉ mục và kiểu cursor.

Khi các trách nhiệm này được đặt đúng tầng, giao diện có thể cung cấp chức năng tìm kiếm linh hoạt mà application service vẫn diễn đạt nhu cầu rõ ràng, còn tầng truy cập dữ liệu tối ưu cách lấy dữ liệu theo khả năng của cơ sở dữ liệu. Đây là cách xây dựng chức năng tìm kiếm có thể mở rộng và bảo trì trong kiến trúc phân tầng.
