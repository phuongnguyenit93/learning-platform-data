# Chọn dữ liệu vừa đủ cho từng màn hình

Trong ứng dụng Model–View–Controller (MVC), một màn hình không cần toàn bộ dữ liệu của một đối tượng nghiệp vụ. Trang danh sách đơn hàng có thể chỉ cần mã đơn, tên khách hàng, trạng thái và tổng tiền; trang chi tiết cần thêm địa chỉ, dòng hàng và lịch sử; trang tổng quan có thể chỉ cần số lượng đơn theo trạng thái và tổng doanh thu. Nếu mọi màn hình đều tải toàn bộ entity rồi để View tự chọn trường cần hiển thị, ứng dụng sẽ đọc dữ liệu dư thừa, tạo thêm truy vấn và làm tăng chi phí bộ nhớ, mạng cũng như thời gian phản hồi.

Chọn dữ liệu vừa đủ nghĩa là bắt đầu từ nhu cầu thực tế của View, xác định trường và phép tính cần thiết, sau đó thiết kế truy vấn và hợp đồng dữ liệu phù hợp. Controller điều phối request, query/application service lấy dữ liệu, presenter tạo ViewModel, còn View chỉ trình bày kết quả. Cách làm này giúp giữ ranh giới MVC rõ ràng và cải thiện hiệu năng mà không làm suy yếu quy tắc nghiệp vụ.

## 1. Vì sao không nên tải toàn bộ dữ liệu?

Giả sử entity Order có:

- Mã định danh, mã đơn và trạng thái.
- Khách hàng, địa chỉ giao hàng và thông tin liên hệ.
- Danh sách dòng hàng, sản phẩm và giá tại thời điểm đặt.
- Ghi chú nội bộ, lịch sử thay đổi và thông tin thanh toán.
- Dữ liệu phục vụ quy tắc nghiệp vụ và quan hệ ORM.

Trang danh sách chỉ cần sáu trường nhưng ứng dụng tải toàn bộ entity cùng các quan hệ. Hệ quả có thể gồm:

- **Đọc nhiều cột hơn cần thiết:** tăng dữ liệu từ database và chi phí ánh xạ.
- **Đọc nhiều bản ghi liên quan:** quan hệ không cần thiết có thể kích hoạt thêm truy vấn.
- **Tạo object graph lớn:** ORM phải tạo và quản lý nhiều object trong persistence context.
- **Tăng dữ liệu truyền đi:** ViewModel hoặc JSON có thể chứa trường không cần hiển thị.
- **Tăng nguy cơ lộ dữ liệu:** trường nội bộ có thể vô tình xuất hiện trong response.
- **Khó kiểm soát truy vấn:** template hoặc serializer truy cập thuộc tính lazy có thể tạo truy vấn ngoài dự kiến.

Chi phí không chỉ nằm ở số byte. Một truy vấn có thể trả ít dữ liệu nhưng thực hiện nhiều lần; một response nhỏ có thể được tạo sau hàng trăm truy vấn. Vì vậy, cần xem đồng thời số truy vấn, số hàng đọc, số cột, thời gian database, thời gian xử lý ứng dụng và kích thước response.

### Nguyên tắc thiết kế

1. Bắt đầu từ nội dung và hành động của từng màn hình.
2. Liệt kê trường, quan hệ và phép tổng hợp thực sự cần thiết.
3. Lấy dữ liệu gần với hình dạng mà View hoặc use case cần.
4. Giữ phép tính và quy tắc nghiệp vụ ở đúng lớp.
5. Giới hạn số bản ghi bằng filter, sort và pagination.
6. Đo truy vấn thực tế trước khi thêm cache hoặc tối ưu phức tạp.

## 2. Bắt đầu từ nhu cầu của từng màn hình

Không nên thiết kế một truy vấn dùng chung cho mọi màn hình chỉ vì chúng cùng hiển thị đơn hàng. Hãy phân tích từng View.

| Màn hình | Dữ liệu cần | Dữ liệu thường không cần |
|---|---|---|
| Danh sách đơn hàng | ID, mã đơn, tên khách, trạng thái, tổng tiền, ngày tạo | Ghi chú nội bộ, lịch sử đầy đủ, mọi dòng hàng |
| Chi tiết đơn hàng | Thông tin đơn, khách hàng, địa chỉ, dòng hàng, trạng thái và hành động phù hợp | Các quan hệ không liên quan như toàn bộ lịch sử thanh toán của khách |
| Biểu mẫu chỉnh sửa | ID, version, các trường được phép sửa và giá trị chọn | Entity graph đầy đủ hoặc thông tin chỉ dành cho quản trị |
| Dashboard | Số lượng, tổng tiền, xu hướng theo khoảng thời gian | Từng entity của tất cả đơn hàng |
| Ô autocomplete | ID, nhãn hiển thị, có thể thêm một thông tin phân biệt | Mô tả dài, lịch sử, quan hệ và metadata không cần thiết |

Ví dụ, trang danh sách có thể cần một kiểu dữ liệu riêng:

```java
public record OrderListItemData(
    UUID id,
    String orderNumber,
    String customerName,
    OrderStatus status,
    BigDecimal total,
    String currencyCode,
    Instant createdAt
) {}
```

Trang chi tiết có hợp đồng khác:

```java
public record OrderDetailsData(
    UUID id,
    String orderNumber,
    String customerName,
    String shippingAddress,
    OrderStatus status,
    BigDecimal total,
    String currencyCode,
    Instant createdAt,
    List<OrderLineData> lines
) {}
```

Hai kiểu dữ liệu khác nhau vì hai View có nhu cầu khác nhau. Việc tạo query DTO riêng không có nghĩa phải tạo một class cho mọi trường hợp nhỏ; chỉ tách khi nó làm rõ hợp đồng, quyền truy cập hoặc cách truy vấn.

### Hỏi đúng câu hỏi trước khi viết query

- View có hiển thị trường này thật không?
- Trường đó có cần để thực hiện hành động hay chỉ được tải “cho tiện”?
- Có thể tính tổng hợp trong database thay vì tải từng bản ghi không?
- Quan hệ này có thực sự cần trong request hiện tại không?
- Có thể giới hạn số hàng bằng phân trang hoặc top-N không?
- Người dùng hiện tại có quyền xem toàn bộ trường đó không?

## 3. Tách truy vấn dữ liệu khỏi entity đầy đủ

Entity phục vụ trạng thái và quy tắc nghiệp vụ. Query DTO hoặc projection phục vụ việc đọc dữ liệu theo nhu cầu của một màn hình. Không nhất thiết mọi truy vấn đọc đều phải tải entity đầy đủ.

### Projection trong Spring Data JPA

Spring Data JPA hỗ trợ interface projection để chỉ lấy những thuộc tính được khai báo:

```java
public interface OrderListRow {
    UUID getId();
    String getOrderNumber();
    String getCustomerName();
    OrderStatus getStatus();
    BigDecimal getTotal();
    String getCurrencyCode();
    Instant getCreatedAt();
}
```

Với projection có trường lấy từ quan hệ, có thể dùng truy vấn rõ ràng để đặt alias phù hợp:

```java
@Query("""
    select o.id as id,
           o.orderNumber as orderNumber,
           c.displayName as customerName,
           o.status as status,
           o.total as total,
           o.currencyCode as currencyCode,
           o.createdAt as createdAt
    from Order o
    join o.customer c
    where o.ownerId = :ownerId
    order by o.createdAt desc
    """)
Page<OrderListRow> findRowsByOwner(
    @Param("ownerId") UUID ownerId,
    Pageable pageable
);
```

Interface projection có thể giảm dữ liệu được lấy và tránh tải entity graph không cần thiết. Cần kiểm tra SQL thực tế được sinh ra, vì projection lồng nhau hoặc biểu thức phức tạp có thể khiến framework tạo join hoặc lấy thêm dữ liệu.

### DTO projection bằng constructor expression

Với DTO dạng record, có thể dùng constructor expression trong JPQL:

```java
public record OrderListItemData(
    UUID id,
    String orderNumber,
    String customerName,
    OrderStatus status,
    BigDecimal total,
    String currencyCode,
    Instant createdAt
) {}

@Query("""
    select new com.example.shop.orders.OrderListItemData(
        o.id,
        o.orderNumber,
        c.displayName,
        o.status,
        o.total,
        o.currencyCode,
        o.createdAt
    )
    from Order o
    join o.customer c
    where o.ownerId = :ownerId
    """)
Page<OrderListItemData> findListData(
    @Param("ownerId") UUID ownerId,
    Pageable pageable
);
```

Tên lớp trong constructor expression phải là tên đầy đủ của DTO. Thứ tự và kiểu tham số phải khớp constructor. Cách này làm hình dạng dữ liệu truy vấn rõ ràng và không buộc View phụ thuộc entity.

### Khi nào vẫn nên tải entity?

Khi thực hiện hành động thay đổi trạng thái, application service thường cần tải aggregate/entity để gọi hành vi và bảo vệ bất biến. Ví dụ, xác nhận đơn hàng cần kiểm tra trạng thái, dòng hàng và quy tắc hiện tại. Khi đó tải entity là hợp lý.

Đối với màn hình chỉ đọc, dashboard hoặc danh sách lớn, projection thường phù hợp hơn. Không nên biến mọi entity thành DTO bằng cách tải toàn bộ rồi map, nếu query có thể chỉ chọn các cột cần thiết ngay từ đầu.

## 4. Tránh N+1 và tải quan hệ không cần thiết

Lỗi N+1 xảy ra khi ứng dụng tải một danh sách cha bằng một truy vấn, sau đó phát sinh thêm một truy vấn cho mỗi bản ghi con khi truy cập quan hệ lazy.

Ví dụ:

```java
List<Order> orders = orderRepository.findByOwnerId(ownerId);

for (Order order : orders) {
    // Có thể kích hoạt một query riêng cho customer nếu quan hệ lazy.
    String customerName = order.getCustomer().getDisplayName();
    renderRow(order, customerName);
}
```

Nếu có 100 đơn hàng và mỗi lần truy cập customer tạo một query, tổng số có thể gần 101 query. Khi quan hệ sâu hơn, số truy vấn có thể tăng nhanh.

### Cách khắc phục

- Dùng projection hoặc DTO query lấy trực tiếp tên khách hàng cần hiển thị.
- Dùng join phù hợp để lấy quan hệ cần thiết trong một query.
- Dùng EntityGraph hoặc fetch strategy có chủ đích khi cần entity và quan hệ cụ thể.
- Dùng batch fetching khi tải nhiều quan hệ lazy là phù hợp với luồng xử lý.
- Dùng truy vấn tổng hợp hoặc truy vấn con để tránh tải từng bản ghi chỉ nhằm tính toán.

Không nên chuyển mọi quan hệ sang EAGER để “sửa” N+1. Quan hệ eager có thể làm mọi màn hình tải thêm dữ liệu ngay cả khi không cần, và vẫn không bảo đảm chỉ có một SQL query. Hãy chọn fetch plan theo use case.

### Thận trọng với fetch join và pagination

Fetch join một collection có thể nhân số hàng kết quả: một đơn có năm dòng hàng tạo ra năm hàng SQL cho cùng đơn. Khi kết hợp phân trang, kết quả có thể bị trùng, thiếu hoặc buộc ORM xử lý phân trang trong bộ nhớ tùy provider và cấu hình.

Với danh sách đơn hàng, thường nên phân trang trên query cha chỉ lấy trường danh sách. Với trang chi tiết, tải các dòng hàng của một đơn cụ thể bằng truy vấn riêng hoặc fetch plan có giới hạn. Nếu cần danh sách cha cùng một collection lớn, có thể:

1. Truy vấn trang ID hoặc DTO của các đơn hàng.
2. Truy vấn dữ liệu con cho tập ID của trang đó.
3. Gom dữ liệu con theo ID trong application/query service.
4. Tạo ViewModel cho từng hàng.

Đây là hai truy vấn có số lượng ổn định theo trang, thường dễ kiểm soát hơn một truy vấn fetch collection kết hợp pagination.

## 5. Dùng phép tổng hợp ở nơi dữ liệu đang nằm

Dashboard thường cần COUNT, SUM, AVG, min/max hoặc nhóm theo trạng thái. Không nên tải hàng trăm nghìn entity về Java chỉ để đếm hoặc cộng.

Ví dụ query tổng hợp:

```java
public record OrderSummaryData(
    OrderStatus status,
    long orderCount,
    BigDecimal totalAmount
) {}

@Query("""
    select new com.example.shop.orders.OrderSummaryData(
        o.status,
        count(o),
        sum(o.total)
    )
    from Order o
    where o.ownerId = :ownerId
      and o.createdAt >= :from
      and o.createdAt < :to
    group by o.status
    """)
List<OrderSummaryData> summarizeByStatus(
    @Param("ownerId") UUID ownerId,
    @Param("from") Instant from,
    @Param("to") Instant to
);
```

Database được tối ưu để lọc và tổng hợp gần nơi dữ liệu lưu trữ. Ứng dụng chỉ nhận số lượng kết quả nhỏ để tạo dashboard.

### Đặt đúng ranh giới cho phép tính

Không phải mọi phép tính đều nên đưa vào SQL:

- Tổng tiền theo dữ liệu đã lưu có thể được tổng hợp trong query nếu ý nghĩa nghiệp vụ đã được xác định.
- Giá cuối cùng, thuế hoặc chiết khấu cần quy tắc miền nhất quán có thể được tính bởi domain/application logic.
- Định dạng tiền, ngày giờ và nhãn trạng thái dành cho người dùng thuộc presentation layer.

Nếu phép tổng hợp phụ thuộc quy tắc phức tạp, hãy bảo đảm query và domain dùng cùng định nghĩa. Tránh tạo hai cách tính khác nhau cho cùng một khái niệm nghiệp vụ.

## 6. Lọc, sắp xếp và phân trang ở phía máy chủ

Một View danh sách không nên tải tất cả dữ liệu rồi dùng JavaScript hoặc template để lọc và phân trang. Khi dữ liệu tăng, chi phí mạng, bộ nhớ và render sẽ tăng theo toàn bộ tập dữ liệu.

### Pagination bằng Page và Pageable

Ví dụ Controller:

```java
@GetMapping
public String list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @AuthenticationPrincipal AppPrincipal principal,
        Model model) {

    int safePage = Math.max(page, 0);
    int safeSize = Math.min(Math.max(size, 1), 100);

    Pageable pageable = PageRequest.of(
        safePage,
        safeSize,
        Sort.by(Sort.Direction.DESC, "createdAt")
    );

    Page<OrderListItemData> result =
        orderQueryService.findPage(principal.userId(), pageable);

    model.addAttribute("orders", result);
    return "orders/list";
}
```

Giới hạn size giúp tránh request yêu cầu hàng chục nghìn bản ghi. Trong ứng dụng thực tế, sort field nên được ánh xạ từ allowlist, không chuyển trực tiếp chuỗi tùy ý từ client vào Sort.

Page thường cần truy vấn nội dung và truy vấn đếm tổng số bản ghi. Với màn hình chỉ cần biết còn trang tiếp theo hay không, Slice có thể tránh count query. Cần chọn theo nhu cầu giao diện:

| Kiểu | Dữ liệu cung cấp | Chi phí thường gặp |
|---|---|---|
| Page<T> | Nội dung, tổng số phần tử và tổng số trang | Thường có thêm count query |
| Slice<T> | Nội dung và thông tin còn phần tiếp theo | Không cần tổng số toàn bộ |
| List<T> giới hạn | Chỉ danh sách trong giới hạn đã đặt | Không tự cung cấp metadata phân trang |

### Offset pagination và keyset pagination

Offset pagination dễ hiểu và phù hợp với danh sách vừa phải:

```sql
SELECT id, order_number, status, created_at
FROM orders
WHERE owner_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 10000;
```

Ở offset lớn, database có thể phải duyệt và bỏ qua nhiều hàng trước khi trả kết quả. Keyset pagination dùng giá trị của hàng cuối trang trước để lấy trang tiếp:

```sql
SELECT id, order_number, status, created_at
FROM orders
WHERE owner_id = ?
  AND (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Ví dụ dùng tuple so sánh cần được điều chỉnh theo hệ quản trị cơ sở dữ liệu và hướng sắp xếp. Với database không hỗ trợ cú pháp tuple, có thể viết điều kiện tương đương bằng created_at < ? OR (created_at = ? AND id < ?). Cần có thứ tự ổn định với tie-breaker như ID để tránh bản ghi bị bỏ qua hoặc lặp khi nhiều hàng có cùng thời điểm.

Keyset phù hợp với feed hoặc danh sách lớn đi tuần tự. Nó không thuận tiện khi người dùng cần nhảy trực tiếp tới một trang bất kỳ hoặc xem tổng số trang.

## 7. Chọn cột và quan hệ theo mục đích

Không nên lấy SELECT * cho mọi truy vấn đọc. Việc chọn cột tường minh giúp người đọc thấy hợp đồng dữ liệu và giảm nguy cơ lấy trường lớn hoặc nhạy cảm không cần thiết.

Ví dụ:

```sql
-- Dùng cho hàng trong danh sách.
SELECT id, order_number, status, total, created_at
FROM orders
WHERE owner_id = ?
ORDER BY created_at DESC
LIMIT 20;
```

Tránh lấy các cột như nội dung ghi chú dài, file blob, audit payload hoặc thông tin nội bộ nếu màn hình không cần chúng. Với quan hệ, chỉ join những bảng cung cấp trường thực sự dùng trong View.

### Cẩn thận với quan hệ một-nhiều

Join collection có thể nhân số hàng. Nếu trang danh sách chỉ cần số lượng dòng hàng, có thể dùng phép tổng hợp hoặc subquery thay vì tải toàn bộ OrderLine:

```sql
SELECT o.id,
       o.order_number,
       COUNT(ol.id) AS line_count
FROM orders o
LEFT JOIN order_lines ol ON ol.order_id = o.id
WHERE o.owner_id = ?
GROUP BY o.id, o.order_number
ORDER BY o.order_number;
```

Khi query có nhiều collection, việc join tất cả có thể tạo tích số hàng rất lớn. Hãy cân nhắc truy vấn riêng theo trang ID hoặc tổng hợp từng collection rồi ghép kết quả trong query service.

## 8. Tạo chỉ mục theo truy vấn thực tế

Truy vấn chỉ chọn đúng dữ liệu vẫn có thể chậm nếu database phải quét quá nhiều hàng hoặc sắp xếp lượng dữ liệu lớn. Index cần hỗ trợ điều kiện lọc, join và thứ tự sắp xếp thực tế.

Ví dụ, truy vấn thường lọc theo owner_id rồi sắp xếp theo created_at và id:

```sql
CREATE INDEX idx_orders_owner_created_id
ON orders (owner_id, created_at DESC, id DESC);
```

Thứ tự cột trong index có ý nghĩa. Với index tổng hợp, cần xem các điều kiện equality, range và thứ tự sắp xếp cùng quy tắc leftmost-prefix của hệ quản trị; không có một thứ tự duy nhất tối ưu cho mọi query. Không chọn thứ tự chỉ dựa trên độ chọn lọc của một cột riêng lẻ.

### Một số lưu ý

- Index có thể tăng tốc đọc nhưng làm chậm insert/update/delete và tốn dung lượng.
- Không tạo index cho mọi cột theo cảm tính.
- Cột trong điều kiện WHERE, join và ORDER BY là ứng viên cần xem xét.
- Hàm áp dụng lên cột hoặc pattern tìm kiếm có thể khiến index thông thường khó được sử dụng.
- Index có thể không hiệu quả nếu điều kiện lọc trả về phần lớn bảng.
- Cần xem execution plan và thống kê dữ liệu thực tế.

Ví dụ, WHERE LOWER(email) = ? có thể không sử dụng index thường trên email tùy database. Có thể dùng functional index hoặc lưu một giá trị chuẩn hóa riêng nếu nhu cầu tìm kiếm yêu cầu; quyết định dựa trên hệ quản trị và kế hoạch truy vấn.

## 9. Đo truy vấn thay vì đoán

Trước khi tối ưu, cần có đường cơ sở:

- Thời gian response tổng thể và phân vị p50/p95/p99.
- Số query được thực thi trong một request.
- Thời gian database và số hàng được đọc/trả.
- Số byte response và kích thước ViewModel.
- Tỷ lệ cache hit/miss nếu có cache.
- CPU, bộ nhớ và số connection đang sử dụng.

Một màn hình có response chậm không nhất thiết do SQL. Thời gian có thể nằm ở network, serialization, template rendering, gọi dịch vụ bên ngoài hoặc lock contention. Hãy phân rã thời gian trước khi thay đổi.

### Dùng execution plan

EXPLAIN hoặc công cụ tương đương cho biết database dự kiến thực hiện truy vấn như thế nào; một số hệ quản trị có chế độ thực thi thực tế như EXPLAIN ANALYZE.

Hãy xem:

- Query có dùng index mong muốn không?
- Có full table scan hoặc sort lớn không?
- Số hàng ước tính có lệch nhiều so với số hàng thực tế không?
- Join có tạo ra nhiều hàng trung gian không?
- Count query có tốn kém hơn query nội dung không?
- Có thể đẩy filter hoặc aggregation xuống database không?

Chạy lệnh phân tích thực tế trên môi trường phù hợp, vì EXPLAIN ANALYZE có thể thực thi query và tạo tải. Dữ liệu mẫu nhỏ thường không phản ánh đúng hành vi khi bảng có hàng triệu bản ghi.

### Phát hiện N+1 bằng quan sát

Trong môi trường phát triển hoặc kiểm thử, bật thống kê SQL hoặc công cụ quan sát truy vấn để biết một request đã phát bao nhiêu query. Không nên bật log SQL chi tiết liên tục ở production nếu nó tạo overhead hoặc ghi lộ dữ liệu.

Một kiểm thử hữu ích là xác minh số truy vấn không tăng tuyến tính theo số hàng danh sách. Nếu danh sách 10 và 50 đơn tạo số query lần lượt 11 và 51, có dấu hiệu N+1. Mục tiêu không phải luôn chỉ có một query; mục tiêu là số truy vấn có chủ đích và tăng theo cách kiểm soát được.

## 10. Cache dữ liệu đọc khi có lý do

Sau khi query đã phù hợp và có index hợp lý, cache có thể giảm tải cho dữ liệu đọc lặp lại. Tuy nhiên, cache không sửa được query sai và tạo thêm vấn đề nhất quán.

Các loại cache thường gặp:

| Cache | Dữ liệu phù hợp | Lưu ý |
|---|---|---|
| Request-scope / persistence context | Dữ liệu được dùng lặp trong một request | Vòng đời ngắn, không chia sẻ giữa request |
| Application cache | Danh mục ít thay đổi, cấu hình, dữ liệu tham chiếu | Cần TTL và chiến lược invalidation |
| Distributed cache | Dữ liệu đọc nhiều giữa nhiều instance | Cần quản lý key, serialization và đồng bộ |
| HTTP/browser cache | Tài nguyên tĩnh hoặc response có chính sách phù hợp | Cần kiểm soát private/public và dữ liệu nhạy cảm |

Ví dụ key cache nên chứa đủ phạm vi ảnh hưởng kết quả:

```text
orders:summary:{ownerId}:{from}:{to}:{currency}
```

Nếu bỏ ownerId, dữ liệu của người dùng này có thể bị trả cho người khác. Nếu bỏ khoảng thời gian hoặc loại tiền, kết quả có thể không đúng. Cache key là một phần của ranh giới dữ liệu và quyền truy cập.

### TTL và invalidation

- TTL ngắn giảm thời gian dữ liệu cũ nhưng tăng số lần query.
- Invalidation khi ghi giúp dữ liệu mới xuất hiện nhanh hơn nhưng cần xử lý nhiều key liên quan.
- Cache-aside dễ triển khai nhưng có thể có cache stampede khi key hết hạn đồng loạt.
- Với dashboard tổng hợp, có thể dùng dữ liệu tổng hợp cập nhật định kỳ nếu độ trễ được chấp nhận.

Không cache dữ liệu theo người dùng hoặc quyền truy cập nếu key không thể phân biệt đúng phạm vi. Không đưa token hoặc secret vào cache key. Cần xác định rõ hành vi khi cache unavailable: fallback query, trả lỗi hay dùng dữ liệu cũ trong giới hạn được phép.

## 11. Giữ việc định dạng ở presentation layer

Query nên trả dữ liệu có kiểu phù hợp như BigDecimal, Instant, enum hoặc mã tiền tệ. Presenter chuyển chúng thành nhãn, chuỗi tiền và thời gian theo locale/múi giờ của người dùng.

Ví dụ:

```java
public record OrderListItemView(
    UUID id,
    String orderNumber,
    String customerName,
    String statusLabel,
    String totalText,
    String createdAtText
) {}

@Component
@RequiredArgsConstructor
public class OrderListPresenter {
    private final MessageSource messages;

    public OrderListItemView present(
            OrderListItemData data,
            Locale locale,
            ZoneId zoneId) {

        NumberFormat money = NumberFormat.getCurrencyInstance(locale);
        Currency currency = Currency.getInstance(data.currencyCode());
        money.setCurrency(currency);
        int fractionDigits = Math.max(currency.getDefaultFractionDigits(), 0);
        money.setMinimumFractionDigits(fractionDigits);
        money.setMaximumFractionDigits(fractionDigits);

        DateTimeFormatter dateTime = DateTimeFormatter
            .ofLocalizedDateTime(FormatStyle.SHORT)
            .withLocale(locale)
            .withZone(zoneId);

        return new OrderListItemView(
            data.id(),
            data.orderNumber(),
            data.customerName(),
            statusLabel(data.status(), locale),
            money.format(data.total()),
            dateTime.format(data.createdAt())
        );
    }

    private String statusLabel(OrderStatus status, Locale locale) {
        return messages.getMessage(
            "order.status." + status.name(), null, locale
        );
    }
}
```

Ví dụ rút gọn; trong ứng dụng thực tế, nhãn trạng thái nên lấy từ message bundle hoặc localization service. Query không nên lưu sẵn chuỗi định dạng theo một locale cố định nếu dữ liệu cần hiển thị cho nhiều ngôn ngữ.

Đừng đưa logic truy vấn hoặc gọi repository vào template. Khi template truy cập quan hệ lazy hoặc gọi helper có side effect, hiệu năng trở nên khó dự đoán và trách nhiệm MVC bị trộn lẫn.

## 12. Tránh overfetch và underfetch ở API

Nếu View là SPA hoặc client khác, response JSON cũng là một hợp đồng dữ liệu. Trả quá nhiều trường làm tăng băng thông và có thể lộ dữ liệu; trả quá ít khiến client phải gọi nhiều endpoint tuần tự.

Hãy cân bằng:

- **Overfetch:** một response chứa nhiều trường hoặc quan hệ client không dùng.
- **Underfetch:** client phải gọi nhiều request để dựng một màn hình dù dữ liệu có thể lấy cùng lúc.
- **Round-trip cost:** mỗi request thêm có độ trễ mạng, xác thực, routing và serialization.

Một endpoint tổng hợp theo màn hình có thể hữu ích khi các phần dữ liệu cần hiển thị luôn đi cùng nhau và có cùng ranh giới quyền. Tuy nhiên, không nên tạo endpoint khổng lồ cho mọi màn hình nếu nó kết hợp các miền nghiệp vụ không liên quan hoặc khó cache.

Với API, nên:

- Chọn response DTO theo use case.
- Giới hạn trường và kích thước collection.
- Dùng pagination cho danh sách.
- Cung cấp filter/sort có allowlist.
- Tránh serialize entity graph trực tiếp.
- Giữ status, error contract và authorization nhất quán.

## 13. Tối ưu dashboard và màn hình tổng hợp

Dashboard thường cần số liệu đã tổng hợp thay vì các entity riêng lẻ. Có thể dùng một query cho từng khối thống kê hoặc một query tổng hợp có kiểm soát.

Ví dụ một dashboard gồm:

- Tổng số đơn trong kỳ.
- Tổng doanh thu theo tiền tệ.
- Số đơn theo trạng thái.
- Top sản phẩm theo số lượng.

Nếu các chỉ số dùng cùng bộ lọc và quyền truy cập, có thể gom một số phép tổng hợp vào query để giảm round-trip. Nếu chúng có cách cập nhật hoặc độ trễ khác nhau, tách query hoặc dùng bảng tổng hợp/materialized view có thể phù hợp hơn.

### Khi nào cần read model riêng?

Khi màn hình báo cáo cần tổng hợp phức tạp trên nhiều aggregate, việc dựng dữ liệu bằng cách tải từng entity và duyệt trong Java sẽ tốn tài nguyên. Có thể tạo read model hoặc bảng tổng hợp được cập nhật theo sự kiện hoặc lịch định kỳ.

Read model cần nêu rõ:

- Nguồn dữ liệu và quy tắc tổng hợp.
- Tần suất cập nhật và độ trễ chấp nhận được.
- Cách xử lý sự kiện trùng hoặc đến sai thứ tự.
- Cách tái tạo dữ liệu khi read model sai.
- Quyền truy cập và phạm vi dữ liệu của từng người dùng/tổ chức.

Không cần triển khai CQRS hoặc materialized view cho một dashboard nhỏ nếu một truy vấn tổng hợp đơn giản đã đáp ứng yêu cầu.

## 14. Kiểm thử hiệu năng và hợp đồng dữ liệu

Kiểm thử không chỉ xác nhận View hiển thị đúng. Cần xác minh query chỉ lấy dữ liệu cần thiết, giới hạn số hàng và không tạo N+1.

| Loại kiểm thử | Nội dung |
|---|---|
| Unit test query service | Filter, sort, page và quyền người dùng được áp dụng đúng |
| Unit test presenter | Định dạng và ánh xạ dữ liệu đúng |
| Integration test repository | Projection trả đúng trường và join đúng |
| Query-count test | Số truy vấn ổn định, không tăng theo số phần tử |
| Pagination test | Trang cuối, trang rỗng, page size tối đa và thứ tự ổn định |
| Authorization test | Query không trả dữ liệu ngoài phạm vi người dùng |
| Performance test | p95/p99, throughput và tài nguyên dưới tải đại diện |

Ví dụ kiểm thử presenter:

```java
@Test
void mapsOnlyFieldsNeededByOrderList() {
    OrderListItemData data = new OrderListItemData(
        UUID.fromString("00000000-0000-0000-0000-000000000001"),
        "ORD-1001",
        "Nguyễn An",
        OrderStatus.CONFIRMED,
        new BigDecimal("1250000"),
        "VND",
        Instant.parse("2026-11-19T02:30:00Z")
    );

    OrderListItemView view = presenter.present(
        data, Locale.forLanguageTag("vi-VN"), ZoneId.of("Asia/Ho_Chi_Minh")
    );

    assertEquals("ORD-1001", view.orderNumber());
    assertEquals("Nguyễn An", view.customerName());
    assertEquals("Đã xác nhận", view.statusLabel());
    assertNotNull(view.totalText());
}
```

Ví dụ minh họa kiểm tra mapping; test thực tế nên cố định locale, timezone và message bundle. Kiểm thử hiệu năng cần dữ liệu đủ lớn và phân bố gần thực tế, đồng thời chạy trong môi trường có cấu hình gần với triển khai.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Mọi màn hình đều tải entity đầy đủ | Overfetch, object graph lớn và lộ trường không cần thiết | Query DTO/projection theo từng nhu cầu |
| Dùng một query chung cho list, detail và dashboard | Join và cột thừa; khó tối ưu từng màn hình | Tách read query theo use case |
| Truy cập lazy relation trong vòng lặp | N+1 query | Projection, join có chủ đích hoặc batch |
| Đặt mọi quan hệ thành EAGER | Tải quá nhiều dữ liệu ở các màn hình khác | Chọn fetch plan theo request |
| Fetch join collection rồi phân trang | Nhân hàng, phân trang sai hoặc xử lý trong bộ nhớ | Phân trang ID/DTO cha rồi lấy dữ liệu con riêng |
| Tải tất cả rồi lọc trong JavaScript | Tốn mạng và bộ nhớ | Filter và pagination ở database |
| Dùng Page dù không cần tổng số | Count query tốn kém | Cân nhắc Slice hoặc giới hạn List |
| Tính tổng bằng cách tải từng entity | Tốn CPU và băng thông | Aggregate query khi phù hợp |
| Tạo index không dựa trên query plan | Tốn dung lượng và chi phí ghi mà không cải thiện đọc | Đo và xem execution plan |
| Thêm cache để che query kém | Dữ liệu cũ và khó invalidation | Tối ưu query trước, cache theo nhu cầu |
| Cache key thiếu user hoặc tenant scope | Có thể trả dữ liệu sai người | Đưa đầy đủ phạm vi quyền vào key |
| Định dạng chuỗi ngay trong query | Khó localization và tái sử dụng | Presenter định dạng theo ngữ cảnh |

## 16. Quy trình thực hành tối ưu một màn hình

Giả sử trang danh sách đơn hàng tải chậm:

1. **Ghi lại yêu cầu màn hình.** Liệt kê cột, bộ lọc, thứ tự sắp xếp, thao tác và metadata phân trang.
2. **Đo hiện trạng.** Ghi response time, p95, số query, thời gian SQL, số hàng đọc và kích thước response.
3. **Kiểm tra truy vấn.** Tìm SELECT *, lazy loading, N+1, join collection và count query tốn kém.
4. **Thiết kế query DTO.** Chọn đúng trường cần hiển thị; áp dụng filter theo người dùng và pagination ở database.
5. **Tối ưu quan hệ.** Join hoặc projection cho quan hệ cần thiết; bỏ các quan hệ không dùng.
6. **Kiểm tra index.** Dùng execution plan để xác định index phù hợp với filter và order by.
7. **Đo lại.** So sánh cùng dữ liệu và tải; xác minh kết quả nghiệp vụ vẫn đúng.
8. **Chỉ thêm cache khi có bằng chứng.** Xác định TTL, key scope, invalidation và hành vi khi cache lỗi.

Quy trình này giúp mỗi thay đổi có mục tiêu và có thể đánh giá. Không nên thêm cache, tăng connection pool hoặc đổi fetch strategy chỉ dựa trên một lần quan sát mà chưa biết nút thắt nằm ở đâu.

## 17. Checklist chọn dữ liệu vừa đủ

- Đã liệt kê các trường thực sự được hiển thị hoặc cần cho hành động của màn hình chưa?
- Query có lấy đúng cột và quan hệ cần thiết không?
- Có thể dùng projection hoặc DTO thay cho entity đầy đủ không?
- Có truy cập lazy relation trong vòng lặp hoặc trong template không?
- Có N+1 hoặc join collection làm nhân hàng không?
- Danh sách đã lọc, sắp xếp và phân trang tại database chưa?
- Page, Slice hay keyset pagination phù hợp với trải nghiệm không?
- Phép tổng hợp có thể thực hiện ở database mà vẫn giữ đúng quy tắc nghiệp vụ không?
- Index có được chọn dựa trên query plan và dữ liệu thực tế không?
- ViewModel có tránh trường nhạy cảm và dữ liệu không cần thiết không?
- Cache key có chứa đầy đủ user/tenant và tham số ảnh hưởng kết quả không?
- Đã đo p95/p99, query count, response size và tài nguyên trước/sau chưa?

## Kết luận

Chọn dữ liệu vừa đủ cho từng màn hình là một quyết định đồng thời về thiết kế MVC, quyền dữ liệu và hiệu năng. Hãy bắt đầu từ nhu cầu của View, tạo query DTO hoặc projection phù hợp, tránh N+1 và join không cần thiết, phân trang và tổng hợp ở nơi dữ liệu được lưu, sau đó đo bằng truy vấn và tải thực tế. Entity vẫn cần thiết cho các hành động nghiệp vụ; projection và read model phù hợp cho nhiều luồng chỉ đọc. Khi truy vấn có mục tiêu và hợp đồng dữ liệu rõ ràng, ứng dụng giảm công việc không cần thiết mà vẫn giữ được tính đúng đắn và khả năng bảo trì.
