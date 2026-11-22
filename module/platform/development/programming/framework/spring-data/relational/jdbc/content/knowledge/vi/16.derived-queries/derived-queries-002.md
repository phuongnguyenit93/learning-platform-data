# Truy vấn bằng thuộc tính trực tiếp của aggregate root

Spring Data JDBC hỗ trợ **derived query** (truy vấn suy diễn): framework phân tích tên phương thức repository, xác định property trong kiểu domain rồi tạo SQL phù hợp. Cách này hữu ích khi điều kiện lọc nằm ngay trên aggregate root, chẳng hạn `customerId`, `status`, `totalAmount` hoặc `createdAt` của `PurchaseOrder`.

Bài học tập trung vào việc đặt tên method theo property Java trực tiếp của root, kết hợp điều kiện, sắp xếp và giới hạn kết quả. Đồng thời, ta sẽ phân biệt truy vấn root với truy vấn qua collection con hoặc aggregate khác.

## 1. Mô hình đơn hàng

Giả sử `PurchaseOrder` là aggregate root:

```java
package com.example.orders.domain;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    Long customerId,
    String status,
    BigDecimal totalAmount,
    LocalDateTime createdAt,
    String note,
    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    List<OrderLine> lines
) {}
```

Các property trực tiếp:

| Property Java | Ý nghĩa | Cột SQL theo quy ước |
| --- | --- | --- |
| `id` | Mã đơn hàng. | `id` |
| `customerId` | ID khách hàng tham chiếu. | `customer_id` |
| `status` | Trạng thái đơn. | `status` |
| `totalAmount` | Tổng tiền. | `total_amount` |
| `createdAt` | Thời điểm tạo. | `created_at` |
| `note` | Ghi chú tùy chọn. | `note` |

`customerId` là ID scalar nằm trực tiếp trên `PurchaseOrder`, không phải một object `Customer` được tự động tải. Vì vậy, method `findByCustomerId(...)` nhắm vào property của root.

## 2. Cấu trúc tên derived query

Repository:

```java
package com.example.orders.repository;

import java.util.List;
import java.util.Optional;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByCustomerId(Long customerId);

    List<PurchaseOrder> findByStatus(String status);

    Optional<PurchaseOrder> findByIdAndCustomerId(
        Long id,
        Long customerId
    );
}
```

Spring Data tạo implementation của các method query khi khởi tạo repository. Một derived query thường có cấu trúc:

```text
findBy + Property + Operator + And/Or + Property + OrderBy + Sort
```

Ví dụ `findByStatusAndCustomerIdOrderByCreatedAtDesc` có nghĩa:

1. `findBy`: bắt đầu truy vấn.
2. `Status`: lọc theo property `status`.
3. `And`: kết hợp điều kiện tiếp theo bằng AND.
4. `CustomerId`: lọc theo `customerId`.
5. `OrderByCreatedAtDesc`: sắp xếp theo `createdAt` giảm dần.

Method name dựa trên **property Java**, không dựa trên tên cột SQL. Nếu naming strategy ánh xạ `customerId` thành `customer_id`, tên method vẫn là `findByCustomerId`.

## 3. Truy vấn theo một property

Một số method thường dùng:

```java
List<PurchaseOrder> findByCustomerId(Long customerId);

List<PurchaseOrder> findByStatus(String status);

List<PurchaseOrder> findByTotalAmount(BigDecimal totalAmount);

List<PurchaseOrder> findByCreatedAt(LocalDateTime createdAt);
```

Các method trên diễn đạt điều kiện bằng trên property tương ứng:

| Method | Điều kiện SQL về mặt ý nghĩa |
| --- | --- |
| `findByCustomerId(7L)` | `WHERE customer_id = ?` |
| `findByStatus("CREATED")` | `WHERE status = ?` |
| `findByTotalAmount(amount)` | `WHERE total_amount = ?` |
| `findByCreatedAt(time)` | `WHERE created_at = ?` |

Gọi repository:

```java
List<PurchaseOrder> orders =
    purchaseOrderRepository.findByCustomerId(7L);

List<PurchaseOrder> createdOrders =
    purchaseOrderRepository.findByStatus("CREATED");
```

Giá trị tham số được bind qua JDBC. Không nối input trực tiếp vào chuỗi SQL. Bind parameter giúp driver xử lý đúng kiểu dữ liệu và tránh SQL injection do ghép chuỗi tùy tiện.

## 4. Kết hợp điều kiện bằng And và Or

Dùng `And` khi mọi điều kiện đều phải đúng:

```java
List<PurchaseOrder> findByCustomerIdAndStatus(
    Long customerId,
    String status
);
```

Ý nghĩa SQL:

```sql
SELECT ...
FROM purchase_order
WHERE customer_id = ?
  AND status = ?;
```

Dùng `Or` khi một trong các điều kiện có thể đúng:

```java
List<PurchaseOrder> findByStatusOrNote(
    String status,
    String note
);
```

Ý nghĩa SQL:

```sql
SELECT ...
FROM purchase_order
WHERE status = ?
   OR note = ?;
```

Khi method có nhiều `And` và `Or`, cần đọc kỹ cách parser nhóm điều kiện. Nếu biểu thức có nhiều nhóm ngoặc hoặc logic khó diễn đạt, dùng `@Query` hay custom repository với SQL tường minh thường dễ hiểu và dễ review hơn.

## 5. Các toán tử lọc thường gặp

Tập từ khóa hỗ trợ có thể phụ thuộc loại repository và phiên bản Spring Data JDBC. Những ví dụ dưới đây là các dạng query derivation thường dùng; với từ khóa ít phổ biến, đối chiếu tài liệu đúng phiên bản dự án.

### So sánh và khoảng giá trị

```java
List<PurchaseOrder> findByTotalAmountGreaterThan(BigDecimal minimum);

List<PurchaseOrder> findByTotalAmountGreaterThanEqual(BigDecimal minimum);

List<PurchaseOrder> findByTotalAmountLessThan(BigDecimal maximum);

List<PurchaseOrder> findByTotalAmountBetween(
    BigDecimal minimum,
    BigDecimal maximum
);
```

Ý nghĩa SQL minh họa:

```sql
WHERE total_amount > ?
WHERE total_amount >= ?
WHERE total_amount < ?
WHERE total_amount BETWEEN ? AND ?
```

`Between` thường biểu diễn khoảng bao gồm hai biên theo semantics SQL. Nếu nghiệp vụ cần khoảng nửa mở như [from, to), kết hợp `GreaterThanEqual` và `LessThan` để thể hiện rõ.

### Kiểm tra null

```java
List<PurchaseOrder> findByNoteIsNull();

List<PurchaseOrder> findByNoteIsNotNull();
```

Tương ứng với `WHERE note IS NULL` và `WHERE note IS NOT NULL`. Dùng `IsNull`/`IsNotNull` để thể hiện rõ ý định thay vì truyền null vào method equality.

### Tìm chuỗi

Với property kiểu `String`, có thể dùng:

```java
List<PurchaseOrder> findByNoteContaining(String text);

List<PurchaseOrder> findByNoteStartingWith(String prefix);

List<PurchaseOrder> findByNoteEndingWith(String suffix);

List<PurchaseOrder> findByNoteLike(String pattern);
```

Các dạng này thường được chuyển thành điều kiện `LIKE` với wildcard tương ứng. Với `Like`, cần hiểu ký tự % và _. Case sensitivity phụ thuộc collation/dialect; không giả định mọi database đều tìm kiếm không phân biệt hoa thường.

### Tìm trong danh sách giá trị

```java
List<PurchaseOrder> findByStatusIn(Collection<String> statuses);

List<PurchaseOrder> findByStatusNotIn(Collection<String> statuses);
```

Ví dụ:

```java
var statuses = List.of("CREATED", "CONFIRMED");
List<PurchaseOrder> orders =
    purchaseOrderRepository.findByStatusIn(statuses);
```

Về ý nghĩa SQL, `IN` tạo một danh sách tham số. Xử lý collection rỗng ở service trước khi gọi repository vì `IN ()` không được hỗ trợ thống nhất; quyết định trả danh sách rỗng hay bỏ điều kiện phải theo hợp đồng nghiệp vụ.

## 6. Sắp xếp và giới hạn kết quả

Có thể khai báo thứ tự ngay trong tên method:

```java
List<PurchaseOrder> findByCustomerIdOrderByCreatedAtDesc(
    Long customerId
);

List<PurchaseOrder> findByStatusOrderByTotalAmountAscCreatedAtDesc(
    String status
);
```

- `Asc`: tăng dần.
- `Desc`: giảm dần.

Lấy đơn mới nhất của một khách:

```java
Optional<PurchaseOrder> findFirstByCustomerIdOrderByCreatedAtDesc(
    Long customerId
);
```

Lấy tối đa 10 đơn mới nhất có trạng thái:

```java
List<PurchaseOrder> findTop10ByStatusOrderByCreatedAtDesc(
    String status
);
```

`First` và `Top` giới hạn số kết quả. Nếu nhiều hàng có cùng thời điểm, thêm một thuộc tính phụ ổn định như ID:

```java
List<PurchaseOrder> findTop10ByStatusOrderByCreatedAtDescIdDesc(
    String status
);
```

Không tải toàn bộ đơn của một khách rồi cắt danh sách trong Java nếu database có thể lọc, sắp xếp và giới hạn ngay trong SQL. Khả năng phân trang và các kiểu tham số paging cần xác nhận với phiên bản Spring Data JDBC đang dùng; không mặc định mọi API của Spring Data JPA đều có ở JDBC.

## 7. Chọn kiểu trả về phù hợp

| Kiểu trả về | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `List<PurchaseOrder>` | Danh sách, có thể rỗng. | Có thể có nhiều đơn. |
| `Iterable<PurchaseOrder>` | Tập kết quả có thể duyệt. | Không cần API List cụ thể. |
| `Optional<PurchaseOrder>` | Không có hoặc một kết quả. | Điều kiện duy nhất hoặc method có First/Top. |
| `long` | Số hàng phù hợp. | `countBy...`. |
| `boolean` | Có tồn tại hay không. | `existsBy...`. |

Ví dụ:

```java
long countByCustomerId(Long customerId);

boolean existsByCustomerIdAndStatus(
    Long customerId,
    String status
);
```

`Optional` chỉ phù hợp khi query trả tối đa một kết quả. Nếu điều kiện không duy nhất mà có nhiều hàng, framework có thể báo lỗi kết quả không đơn nhất. Nếu chỉ cần một hàng theo thứ tự cụ thể, dùng `First`/`Top` cùng `OrderBy`.

Các method như `findById`, `existsById` và `deleteById` đã được cung cấp bởi `CrudRepository`. Không cần khai báo lại chỉ để truy vấn theo ID.

## 8. Tên property Java khác tên cột SQL

Giả sử property được ánh xạ bằng annotation:

```java
@Column("order_state")
String status
```

Dù tên cột thực tế là `order_state`, method vẫn dùng tên property:

```java
List<PurchaseOrder> findByStatus(String status);
```

Không dùng `findByOrderState(...)` trừ khi class thực sự có property `orderState`. `@Column` thay đổi mapping property-to-column, không đổi tên property trong mô hình domain.

Tương tự, naming strategy có thể chuyển `createdAt` thành `created_at`, nhưng method vẫn dùng `findByCreatedAt...`.

## 9. Ranh giới root và truy vấn qua child/aggregate khác

Một derived query theo property trực tiếp có thể nhắm đến:

- `PurchaseOrder.customerId`
- `PurchaseOrder.status`
- `PurchaseOrder.totalAmount`
- `PurchaseOrder.createdAt`

Trong khi đó `PurchaseOrder.lines` là collection con; mỗi `OrderLine` có `productId`. Truy vấn “tìm đơn có dòng hàng chứa productId = 11” liên quan đến bảng con, không phải property trực tiếp của root. Không mặc định parser có thể điều hướng mọi collection/object graph như JPA.

Khi cần truy vấn theo child row, có thể viết SQL join tường minh:

```sql
SELECT DISTINCT po.id,
       po.customer_id,
       po.status,
       po.total_amount,
       po.created_at,
       po.note
FROM purchase_order po
JOIN order_line ol ON ol.order_id = po.id
WHERE ol.product_id = :productId;
```

Đây là SQL minh họa điều kiện join. Nếu ánh xạ kết quả thành aggregate đầy đủ, cần bảo đảm query/mapping cung cấp đủ dữ liệu theo hợp đồng Spring Data JDBC. Với báo cáo hoặc màn hình tìm kiếm, DTO/projection thường phù hợp hơn.

Tương tự, `findByCustomerId(7L)` chỉ lọc theo cột `customer_id`; nó không tự join bảng customer và dựng object Customer. Nếu cần lọc theo tên khách hàng, dùng SQL join tường minh hoặc tìm customer trước rồi dùng ID, tùy yêu cầu và hiệu năng.

## 10. SQL được suy diễn và cách quan sát

Method:

```java
List<PurchaseOrder> findByCustomerIdAndStatusOrderByCreatedAtDesc(
    Long customerId,
    String status
);
```

Có thể hiểu về mặt SQL như sau:

```sql
SELECT id,
       customer_id,
       status,
       total_amount,
       created_at,
       note
FROM purchase_order
WHERE customer_id = ?
  AND status = ?
ORDER BY created_at DESC;
```

SQL runtime có thể thêm alias, quoting, xử lý mapping hoặc câu truy vấn tải child rows tùy phiên bản/dialect. Đoạn SQL trên chỉ mô tả ý nghĩa, không phải bản sao chính xác được cam kết.

Bật log trong môi trường phát triển để quan sát:

```yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
    org.springframework.data.jdbc.core: DEBUG
```

Khi đọc log, kiểm tra bảng root, cột WHERE, thứ tự và kiểu tham số, cũng như các truy vấn tải collection con. Không bật log chứa dữ liệu nhạy cảm trong production nếu chưa có chính sách bảo vệ.

## 11. Index và hiệu năng

Derived query không tự làm truy vấn nhanh. Database vẫn cần index phù hợp với điều kiện lọc và sắp xếp.

Nếu ứng dụng thường tìm đơn theo khách hàng, trạng thái và thời điểm mới nhất:

```sql
CREATE INDEX idx_order_customer_status_created
ON purchase_order (customer_id, status, created_at DESC);
```

Nếu thường lọc theo trạng thái và thời điểm:

```sql
CREATE INDEX idx_order_status_created
ON purchase_order (status, created_at DESC);
```

Không tạo index cho mọi property chỉ vì có method `findBy...`. Index làm tăng chi phí ghi và dung lượng. Hãy dựa trên workload, độ chọn lọc, execution plan và thống kê truy vấn.

Một derived query trả `List<PurchaseOrder>` có thể tải aggregate cùng các thành phần con theo mapping. Nếu khách hàng có hàng chục nghìn đơn, tránh trả tất cả một lần; dùng giới hạn kết quả hoặc query/projection thích hợp.

## 12. Khi nào dùng @Query hoặc custom repository?

Derived query phù hợp khi điều kiện nằm trên property trực tiếp và có thể diễn đạt gọn bằng tên method.

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Lọc theo `status` hoặc `customerId` | Derived query. |
| Kết hợp vài điều kiện AND/OR | Derived query nếu tên vẫn dễ hiểu. |
| Lọc khoảng ngày/giá | Derived query với toán tử phù hợp. |
| Join bảng con hoặc aggregate khác | `@Query` hoặc custom repository. |
| Tổng hợp `SUM/COUNT/GROUP BY` phức tạp | SQL tường minh và DTO/projection. |
| Vendor-specific function hoặc hint | Custom SQL phù hợp database. |
| Method name quá dài | `@Query` để diễn đạt rõ. |

Ví dụ SQL khai báo trên repository method (cú pháp annotation/bind parameter cần theo phiên bản Spring Data JDBC):

```java
@Query("""
    SELECT id, customer_id, status, total_amount, created_at, note
    FROM purchase_order
    WHERE customer_id = :customerId
      AND status = :status
    ORDER BY created_at DESC
    """)
List<PurchaseOrder> findRecentOrders(
    Long customerId,
    String status
);
```

Khi dùng `@Query`, ứng dụng chịu trách nhiệm SQL, tên cột, parameter binding và tương thích dialect. Với aggregate có collection con, xác minh cách query method ánh xạ kết quả và tải child collection. Không coi một query chỉ trả vài cột là aggregate đầy đủ.

## 13. Lỗi thường gặp khi đặt tên method

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Property không tìm thấy | Method dùng tên cột SQL hoặc sai tên Java property. | Dùng tên property thật trong class. |
| Method quá dài | Dồn quá nhiều điều kiện vào derived query. | Tách query hoặc dùng `@Query`. |
| Optional gây lỗi | Điều kiện trả nhiều hàng nhưng method chỉ nhận một. | Dùng List hoặc giới hạn First/Top. |
| Khác biệt case sensitivity | Kỳ vọng collation giống database khác. | Kiểm tra collation/dialect, chuẩn hóa dữ liệu. |
| Danh sách IN rỗng | SQL `IN ()` không portable. | Xử lý đầu vào rỗng ở service. |
| Query root quá nặng | Trả aggregate đầy đủ cùng child collection. | Giới hạn hoặc dùng DTO/projection. |
| Tìm field của bảng liên quan không hoạt động | Giả định derived query tự join aggregate khác. | Dùng ID scalar hoặc SQL join tường minh. |
| Keyword không được hỗ trợ | Khác biệt phiên bản/repository. | Đối chiếu reference docs và startup error. |

Tên method không hợp lệ có thể làm Spring khởi tạo repository thất bại ngay khi application context được tạo. Đọc lỗi property không tìm thấy và đối chiếu với kiểu domain trong `CrudRepository<PurchaseOrder, Long>`.

## 14. Bài thực hành

Dữ liệu mẫu:

```sql
INSERT INTO purchase_order
    (customer_id, status, total_amount, created_at, note)
VALUES
    (7, 'CREATED',   285000.00, '2026-11-01 09:00:00', NULL),
    (7, 'CONFIRMED', 450000.00, '2026-11-02 10:30:00', 'Giao buổi sáng'),
    (8, 'CREATED',   120000.00, '2026-11-03 11:00:00', NULL),
    (7, 'CANCELLED',  99000.00, '2026-11-04 14:00:00', 'Khách hủy');
```

Repository:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByCustomerId(Long customerId);

    List<PurchaseOrder> findByStatusAndCustomerIdOrderByCreatedAtDesc(
        String status,
        Long customerId
    );

    List<PurchaseOrder> findByTotalAmountBetween(
        BigDecimal min,
        BigDecimal max
    );

    List<PurchaseOrder> findByNoteIsNull();

    Optional<PurchaseOrder> findFirstByCustomerIdOrderByCreatedAtDesc(
        Long customerId
    );

    long countByStatus(String status);

    boolean existsByCustomerIdAndStatus(
        Long customerId,
        String status
    );
}
```

Thực hành:

1. Tìm tất cả đơn của customer 7 bằng `findByCustomerId`.
2. Tìm đơn `CREATED` của customer 7 và sắp xếp mới nhất trước.
3. Tìm đơn có tổng tiền trong khoảng bằng `Between`.
4. Tìm đơn chưa có ghi chú bằng `IsNull`.
5. Lấy đơn mới nhất của customer 7 bằng `First` và `OrderBy`.
6. Đếm đơn theo trạng thái và kiểm tra khách có đơn `CONFIRMED` hay không.
7. Bật SQL log, đối chiếu điều kiện và tham số với kết quả.
8. Thêm index phù hợp cho truy vấn thường dùng, so sánh execution plan trước/sau.
9. Viết integration test cho kết quả rỗng, một kết quả, nhiều kết quả và giá trị null.
10. Thử truy vấn theo `OrderLine.productId` bằng SQL join và so sánh với derived query trên root.

## 15. Câu hỏi tự kiểm tra

- Derived query là gì và Spring Data JDBC lấy tên property từ đâu?
- Vì sao `findByCustomerId` dùng `customerId` chứ không dùng tên cột `customer_id`?
- `And` và `Or` thể hiện logic nào?
- `Between`, `IsNull`, `In` và `Containing` dùng trong trường hợp nào?
- Khi nào nên trả `List` và khi nào dùng `Optional`?
- `Top10By...OrderBy...Desc` giải quyết vấn đề gì?
- Vì sao `findByCustomerId` không tự tải object Customer?
- Khi nào nên dùng `@Query` hoặc custom repository?
- Vì sao derived query không bảo đảm hiệu năng nếu thiếu index?
- Khi tìm theo `OrderLine.productId`, tại sao phải xem xét truy vấn bảng con?

Derived query phù hợp khi điều kiện lọc nằm trên property trực tiếp của aggregate root và có thể diễn đạt rõ bằng tên method. Hãy đặt tên theo **Java property**, chọn kiểu trả về theo số kết quả, kiểm tra SQL và bổ sung index theo workload. Khi truy vấn vượt ranh giới root hoặc cần join/tổng hợp phức tạp, chuyển sang SQL tường minh và DTO phù hợp thay vì kéo dài một method name khó hiểu.
