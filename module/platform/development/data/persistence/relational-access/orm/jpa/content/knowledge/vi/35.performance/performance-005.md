# Lựa chọn projection và truy vấn tổng hợp cho nhu cầu báo cáo

Một API quản lý đơn hàng thường có hai kiểu công việc rất khác nhau. Trong luồng chỉnh sửa, service cần tải **entity** để kiểm tra trạng thái, sửa dữ liệu rồi để JPA thực hiện dirty checking. Nhưng trong màn hình báo cáo, người dùng chỉ muốn biết tổng doanh thu theo ngày, số đơn theo trạng thái, top sản phẩm, hoặc thống kê theo khách hàng. Nếu dùng cùng cách tải toàn bộ entity graph cho mọi tình huống, ứng dụng sẽ phải hydrate rất nhiều object, tốn bộ nhớ, truy vấn thừa và thậm chí làm sai kết quả khi join các bảng một-nhiều.

Ví dụ báo cáo:

> Trong tháng này, theo từng khách hàng, hiển thị số đơn đã thanh toán, tổng doanh thu, giá trị trung bình mỗi đơn và thời điểm có đơn gần nhất, giới hạn trong tenant đang đăng nhập.

Đây không phải nhu cầu lấy danh sách `SalesOrder` rồi cộng bằng Java:

```java
List<SalesOrder> orders = orderRepository.findAll();
// Lặp qua hàng trăm nghìn entities rồi tổng hợp trong bộ nhớ.
```

Thay vào đó, ta có thể yêu cầu database tổng hợp trực tiếp:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue,
    AVG(total_amount) AS average_order,
    MAX(created_at) AS latest_order
FROM sales_orders
WHERE tenant_id = ?
  AND status = 'PAID'
  AND created_at >= ?
  AND created_at < ?
GROUP BY customer_id;
```

Database trả **một hàng cho mỗi khách hàng**, không trả từng entity. Nếu chỉ cần vài trường của một đơn hàng, **DTO projection** cũng cho phép chọn đúng dữ liệu cần thiết thay vì tải mọi cột và associations.

Bài **“Lựa chọn projection và truy vấn tổng hợp cho nhu cầu báo cáo”** thuộc chương **“Hiệu năng”** của module **Data Persistence Relational Access ORM JPA**. Mục tiêu là thiết kế truy vấn báo cáo **đúng nghĩa nghiệp vụ, chính xác số liệu, có phạm vi dữ liệu an toàn và hiệu quả**, từ JPQL/Criteria API đến Spring Data JPA và native SQL khi cần tính năng nâng cao.

## 1. Ba câu hỏi trước khi viết query báo cáo

Trước khi chọn kỹ thuật, xác định:

1. **Báo cáo cần hình dạng dữ liệu nào?** Một danh sách dòng, một giá trị tổng, một bảng nhóm theo chiều, hay một time series?
2. **Số liệu được định nghĩa ra sao?** Doanh thu là tổng giá trị đơn hay tổng dòng hàng? Đơn PAID hay SHIPPED? Có tính refund, tax, shipping, currency conversion không?
3. **Quy mô và cách sử dụng?** Cần online dưới vài trăm milliseconds, dashboard cập nhật theo phút hay batch xuất hàng triệu dòng?

Chỉ khi có đáp án mới quyết định giữa entity, scalar, DTO, interface projection, tuple, grouped aggregate, native SQL hay bảng tổng hợp trước.

### 1.1. Quy tắc trực giác

| Nhu cầu | Dạng truy vấn thường phù hợp |
|---|---|
| Chỉnh sửa một đơn hàng theo aggregate root | Load managed entity với fetch plan phù hợp |
| Danh sách đơn hàng chỉ hiển thị mã, khách, tổng tiền | DTO/record projection |
| Chỉ đếm số đơn | `COUNT` scalar query |
| Doanh thu theo khách hàng | `GROUP BY` + DTO projection |
| Top sản phẩm theo số lượng bán | Aggregate trên order items + `ORDER BY`/limit |
| Tỷ lệ đơn theo status | Conditional aggregation hoặc grouped count |
| Báo cáo theo tháng và rolling average | Native SQL/window functions hoặc read model chuyên dụng |
| Báo cáo rất lớn, tính nhiều lần mỗi ngày | Materialized view/summary table/analytical store, tùy freshness |

**“Projection”** trả lời câu hỏi *chọn những trường nào và trả về kiểu gì*. **“Aggregation”** trả lời câu hỏi *gộp những bản ghi nào và tính toán gì trên chúng*. Một truy vấn có thể sử dụng cả hai.

## 2. Mô hình dữ liệu xuyên suốt

Giả sử hệ thống có đơn hàng và các dòng hàng.

### 2.1. `SalesOrder`

```java
package example.sales;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "sales_orders")
public class SalesOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "order_code", nullable = false)
    private String orderCode;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false,
            precision = 15, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "currency_code", nullable = false, length = 3)
    private String currencyCode;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "order")
    private List<OrderItem> items = new ArrayList<>();

    protected SalesOrder() {}

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOrderCode() { return orderCode; }
    public Customer getCustomer() { return customer; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public String getCurrencyCode() { return currencyCode; }
    public Instant getCreatedAt() { return createdAt; }
}

enum OrderStatus {
    DRAFT, PAID, SHIPPED, CANCELLED, REFUNDED
}
```

### 2.2. `Customer`

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {}

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }
}
```

### 2.3. `OrderItem`

```java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false,
            precision = 15, scale = 2)
    private BigDecimal unitPrice;

    protected OrderItem() {}
}
```

### 2.4. Những giả định cần nói rõ

Trong các ví dụ ban đầu:

- `SalesOrder.totalAmount` là **tổng giá trị đơn theo currency của đơn**, đã được ứng dụng xác định.
- Chỉ `PAID` và `SHIPPED` được tính là doanh thu ghi nhận trong một số báo cáo minh họa, **không mặc nhiên là chuẩn kế toán**.
- `REFUNDED` cần policy riêng về gross/net revenue.
- Các ví dụ về tổng doanh thu **lọc theo một currency**. Không cộng trực tiếp 100 USD với 200 VND.
- Tenant đang truy cập được lấy từ security context của server, không lấy quyền tùy ý từ query parameter của client.
- Thời gian lọc dùng khoảng nửa mở `[from, to)` theo một timezone/business reporting calendar đã chọn.

Mô hình cố tình đơn giản; báo cáo sản xuất có thể cần transaction ledger, payment events, discounts, tax, shipping, refunds và exchange-rate snapshots.

## 3. Một tập dữ liệu nhỏ để hiểu kết quả

Giả định các đơn dưới đây thuộc `TENANT_A`, currency `VND`:

| id | customer | status | total_amount | created_at (UTC) |
|---:|---|---|---:|---|
| 1 | A | PAID | 200.000 | 2026-10-01 02:00 |
| 2 | A | PAID | 300.000 | 2026-10-02 02:00 |
| 3 | A | CANCELLED | 150.000 | 2026-10-02 08:00 |
| 4 | B | PAID | 400.000 | 2026-10-03 02:00 |
| 5 | B | DRAFT | 100.000 | 2026-10-03 10:00 |

Nếu báo cáo chỉ tính `PAID`:

| Customer | Số đơn | Tổng tiền | Trung bình/đơn |
|---|---:|---:|---:|
| A | 2 | 500.000 | 250.000 |
| B | 1 | 400.000 | 400.000 |

Nếu không lọc status, báo cáo sẽ cho kết quả khác và có thể sai định nghĩa doanh thu. **Query có thể chạy nhanh và SQL đúng cú pháp nhưng vẫn sai business metric.**

## 4. Tải entity toàn phần: phù hợp với command, không mặc định với report

Đoạn JPQL:

```java
List<SalesOrder> orders = em.createQuery(
        "select o from SalesOrder o " +
        "where o.tenantId = :tenant",
        SalesOrder.class)
    .setParameter("tenant", tenantId)
    .getResultList();
```

trả các **managed entities** trong persistence context nếu query là managed entity query bình thường.

### 4.1. Giá phải trả

Một managed entity có thể phát sinh:

- Hydration đầy đủ các persistent scalar fields được fetch.
- Identity-map bookkeeping và dirty-checking state.
- Khả năng phát sinh lazy loads khi code truy cập association.
- Bộ nhớ cho object graph, persistence context và có thể secondary cache.
- Trùng hoạt động đọc nếu service chỉ cần 3 trong 15 columns.

### 4.2. Vì sao không tổng hợp bằng Java khi DB làm được?

```java
BigDecimal revenue = orders.stream()
    .filter(o -> o.getStatus() == OrderStatus.PAID)
    .map(SalesOrder::getTotalAmount)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Đoạn này có thể hợp lý với **một tập nhỏ đã load vì lý do khác**. Nhưng nếu cần doanh thu trên hàng triệu rows, nó:

- Chuyển lượng lớn dữ liệu qua network.
- Tạo nhiều Java objects.
- Tốn heap/GC.
- Gây fetch phụ nếu truy cập associations.
- Làm sai dữ liệu khi chỉ load một page nhưng lại coi đó là toàn bộ tập.

Database đã được thiết kế để scan/filter/group/aggregate bằng SQL. Hãy đẩy phép toán phù hợp xuống database thay vì mặc định tải entity.

### 4.3. `JOIN FETCH` không phải giải pháp projection

`JOIN FETCH` thường dùng để load entity cùng associations cho một **use case cần entity graph**. Nó không thu hẹp số field cần đọc như DTO projection, và với to-many join có thể nhân hàng, tăng memory và gây vấn đề pagination.

### 4.4. `@EntityGraph` cũng không thay DTO

Entity graph điều khiển fetch plan. Nó giúp tránh N+1 trong một số luồng entity-oriented; không phải một cách portable để trả duy nhất hai scalar columns hay làm `SUM`/`GROUP BY`.

## 5. Scalar projection: truy vấn trả một giá trị

Khi chỉ cần tổng số đơn:

```java
Long count = em.createQuery(
        "select count(o) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "and o.status = :status",
        Long.class)
    .setParameter("tenant", tenantId)
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();
```

### 5.1. Ưu điểm

Trả một `Long`, không tạo từng `SalesOrder`. SQL backend thường chọn execution plan phù hợp với filter và aggregate.

### 5.2. Kiểu trả về quan trọng

`COUNT` trong JPQL trả `Long`. Không giả định `Integer` chỉ vì tập dữ liệu có ít rows.

### 5.3. Không dùng `getResultList().size()`

Anti-pattern:

```java
int count = em.createQuery(
        "select o from SalesOrder o",
        SalesOrder.class)
    .getResultList()
    .size();
```

Nó tải toàn bộ entities để đếm. `COUNT` đẩy việc đếm xuống DB. Lưu ý `COUNT(*)` cũng có chi phí trên bảng lớn; aggregate có thể cần scan hoặc dùng index tùy DB, không phải phép toán miễn phí.

### 5.4. Query `COUNT` không có group luôn trả một row

Khi không có `GROUP BY`, `COUNT` trả `0L` nếu không có bản ghi khớp. Ngược lại một query `GROUP BY` có thể trả **không có rows** nếu không có group nào.

## 6. Scalar projection: nhiều cột với `Object[]`

```java
List<Object[]> rows = em.createQuery(
        "select o.status, count(o) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "group by o.status",
        Object[].class)
    .setParameter("tenant", tenantId)
    .getResultList();

for (Object[] row : rows) {
    OrderStatus status = (OrderStatus) row[0];
    Long count = (Long) row[1];
}
```

Mỗi row là mảng với thứ tự tương ứng select list.

### 6.1. Khi `Object[]` phù hợp

- Query ngắn, test hoặc internal utility nhỏ.
- Prototype/profiling nhanh.
- Số columns ít, mapping được ghi rõ.

### 6.2. Khi không nên dùng rộng rãi

Nếu report có 12 fields và nhiều phiên bản API, các phép cast `row[7]` hoặc `row[11]` dễ sai sau refactor. Không có compile-time contract về tên/ý nghĩa field; thường nên dùng DTO/record.

## 7. `Tuple` projection: truy cập theo alias

Jakarta Persistence hỗ trợ `Tuple` để biểu diễn row có nhiều lựa chọn.

```java
List<Tuple> rows = em.createQuery(
        "select o.status as orderStatus, " +
        "       count(o) as orderCount " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "group by o.status",
        Tuple.class)
    .setParameter("tenant", tenantId)
    .getResultList();

for (Tuple row : rows) {
    OrderStatus status =
        row.get("orderStatus", OrderStatus.class);
    Long count =
        row.get("orderCount", Long.class);
}
```

### 7.1. Ưu điểm

Alias `orderStatus` và `orderCount` dễ đọc hơn index [0]/[1]. Tuple hữu ích khi kết quả có hình dạng động hoặc cần xử lý query construction linh hoạt.

### 7.2. Hạn chế

- Alias vẫn là string; đổi alias có thể chỉ lỗi lúc runtime.
- Tuple là kiểu persistence-oriented, không nên phơi nguyên ra public REST API.
- Không thay validation/casting sang DTO công khai.
- Query có dialect/provider-specific expression có thể trả JDBC/Java type khác mong đợi; cần mapping rõ.

### 7.3. Khi chọn Tuple hay DTO?

Nếu report fields cố định, DTO/record thường dễ bảo trì hơn. Nếu select list thay đổi theo cấu hình người dùng và không thể biết compile-time, Tuple hoặc cấu trúc report row động có thể phù hợp.

## 8. JPQL constructor expression: DTO projection

Đây là lựa chọn phổ biến cho báo cáo có schema output ổn định.

### 8.1. Định nghĩa DTO record

```java
package example.sales.reporting;

import example.sales.OrderStatus;

public record StatusCountRow(
    OrderStatus status,
    Long orderCount
) {}
```

### 8.2. JPQL `select new ...`

```java
List<StatusCountRow> rows = em.createQuery(
        "select new example.sales.reporting.StatusCountRow(" +
        "    o.status, count(o)) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "group by o.status",
        StatusCountRow.class)
    .setParameter("tenant", tenantId)
    .getResultList();
```

### 8.3. Điều kiện

- JPQL constructor expression cần class name đủ điều kiện theo syntax chuẩn (`package.ClassName`).
- DTO phải có **constructor tương thích về số lượng/thứ tự/kiểu** tham số. Java record có canonical constructor tự sinh phù hợp.
- DTO class không cần `@Entity`.
- Các giá trị là projection results, không phải managed entity instances.
- Không giả định một constructor expression tự ánh xạ theo parameter names như Jackson JSON mapping.

### 8.4. Ví dụ DTO danh sách đơn

```java
public record OrderListRow(
    Long id,
    String code,
    String customerName,
    BigDecimal totalAmount,
    String currency,
    Instant createdAt
) {}
```

```java
List<OrderListRow> page = em.createQuery(
        "select new example.sales.reporting.OrderListRow(" +
        "    o.id, o.orderCode, c.displayName, " +
        "    o.totalAmount, o.currencyCode, o.createdAt) " +
        "from SalesOrder o " +
        "join o.customer c " +
        "where o.tenantId = :tenant " +
        "order by o.createdAt desc, o.id desc",
        OrderListRow.class)
    .setParameter("tenant", tenantId)
    .setMaxResults(50)
    .getResultList();
```

Chỉ chọn những cột cần để render danh sách; không hydrate toàn bộ `SalesOrder`/`Customer`. Thứ tự `createdAt,id` giúp sorting ổn định khi nhiều orders cùng timestamp.

### 8.5. Constructor expression không làm query tự nhiên tối ưu

DTO thu hẹp columns nhưng DB vẫn phải filter, sort, join, aggregate. Nếu thiếu index hoặc join gây nhân hàng, DTO không giải quyết hết. Tối ưu **hình dạng dữ liệu trả về** và **execution plan** là hai việc liên quan nhưng khác nhau.

## 9. Spring Data JPA projections

Nếu dự án dùng Spring Data JPA, có thêm các lựa chọn repository-specific. Đây **không phải** một phần của Jakarta Persistence chuẩn.

### 9.1. Interface-based projection

```java
public interface OrderSummaryView {
    Long getId();
    String getOrderCode();
    BigDecimal getTotalAmount();
}
```

Ví dụ repository:

```java
public interface OrderRepository
        extends JpaRepository<SalesOrder, Long> {

    List<OrderSummaryView> findByTenantIdAndStatus(
        String tenantId, OrderStatus status);
}
```

Với **closed projections** gồm các getters khớp entity properties, Spring Data JPA có thể tối ưu selected fields bằng Tuple-based proxy mapping; hành vi cụ thể phụ thuộc loại query, nested properties và phiên bản Spring Data.

### 9.2. Nested projection có thể kéo theo joins lớn

Nếu interface khai báo:

```java
CustomerView getCustomer();
```

việc truy cập nested projection có thể tạo joins và materialize nhiều fields hơn mong đợi. Không coi nested projection là bảo đảm “chỉ lấy đúng 2 SQL columns” trong mọi phiên bản.

### 9.3. Class/record-based projection

```java
public record OrderCard(
    Long id,
    String orderCode,
    BigDecimal totalAmount
) {}
```

Spring Data có cơ chế constructor-based DTO projection khi đủ điều kiện, nhưng query derivation, explicit `@Query`, constructor names và JPQL rewriting chịu quy tắc framework. Với query aggregate phức tạp, **viết constructor expression tường minh** thường dễ kiểm soát hơn.

### 9.4. Interface projection cho aggregate

```java
public interface StatusCountView {
    OrderStatus getStatus();
    Long getOrderCount();
}
```

```java
@Query("""
    select o.status as status,
           count(o) as orderCount
    from SalesOrder o
    where o.tenantId = :tenantId
    group by o.status
    """)
List<StatusCountView> countByStatus(
    @Param("tenantId") String tenantId);
```

Aliases trong `SELECT` phải phù hợp getter/property names để projection binding hoạt động; khác DTO constructor projection vốn ánh xạ theo thứ tự arguments.

### 9.5. Dynamic projections

Một số Spring Data repository methods có thể nhận `Class<T>` để chọn projection type tại call site:

```java
<T> List<T> findByStatus(OrderStatus status, Class<T> type);
```

Chỉ dùng nếu nhiều projections thực sự phục vụ cùng use case; không biến một query public thành API trả arbitrary user-controlled class. Query plans/association loading và generated SQL vẫn phải được kiểm tra.

### 9.6. Entity vs interface vs record

| Phương án | Ưu điểm | Điểm cần cảnh giác |
|---|---|---|
| Entity | Có identity/lifecycle, dễ mutation | Dư dữ liệu, context/memory, N+1 |
| Scalar | Gọn cho một metric | Ít metadata/khó mở rộng |
| `Object[]` | Đơn giản, query tùy ý | Cast theo index, dễ vỡ |
| `Tuple` | Alias/type access | String aliases, persistence-centric |
| DTO/record | Kiểu dữ liệu rõ, immutable, REST-friendly | Constructor/type compatibility |
| Spring interface | Ngắn gọn cho projection đơn giản | Proxy/alias/nested joins, framework-specific |
| Native SQL mapped DTO | Đầy đủ SQL dialect features | Khó portable, cần result mapping |

## 10. Các hàm tổng hợp trong JPQL

JPQL cung cấp những aggregate functions phổ biến:

| Hàm | Ý nghĩa | Kiểu trả về cần chú ý |
|---|---|---|
| `COUNT(x)` | Đếm các giá trị không NULL của biểu thức | `Long` |
| `COUNT(DISTINCT x)` | Đếm số giá trị phân biệt, không NULL | `Long` |
| `SUM(x)` | Tổng numeric expression | Phụ thuộc numeric Java type |
| `AVG(x)` | Trung bình numeric expression | `Double` theo JPQL |
| `MIN(x)` | Giá trị nhỏ nhất | Kiểu biểu thức đầu vào |
| `MAX(x)` | Giá trị lớn nhất | Kiểu biểu thức đầu vào |

### 10.1. `COUNT`

```java
Long paidOrders = em.createQuery(
        "select count(o) from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "and o.status = :status",
        Long.class)
    .setParameter("tenant", tenantId)
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();
```

Đếm **orders**; không đếm rows của bảng order_items.

### 10.2. `SUM`

```java
BigDecimal revenue = em.createQuery(
        "select sum(o.totalAmount) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "and o.currencyCode = :currency " +
        "and o.status = :status",
        BigDecimal.class)
    .setParameter("tenant", tenantId)
    .setParameter("currency", "VND")
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();
```

Với `BigDecimal` attribute, `SUM` có kiểu `BigDecimal` theo JPQL aggregate type rules.

### 10.3. `SUM` có thể trả NULL khi không có dữ liệu

Nếu không có order thỏa điều kiện, `SUM` (khác `COUNT`) thường trả `null`. Đừng viết:

```java
revenue.add(extraAmount); // NPE nếu revenue null
```

Thay:

```java
BigDecimal total =
    revenue == null ? BigDecimal.ZERO : revenue;
```

hoặc dùng `COALESCE` trong query với type phù hợp:

```java
BigDecimal total = em.createQuery(
        "select coalesce(sum(o.totalAmount), :zero) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant",
        BigDecimal.class)
    .setParameter("zero", BigDecimal.ZERO)
    .setParameter("tenant", tenantId)
    .getSingleResult();
```

Provider/driver type mapping của aggregate và `COALESCE` cần được kiểm thử khi dùng native SQL/custom numeric types.

### 10.4. `AVG` và độ chính xác tiền

JPQL `AVG` trả `Double`, kể cả khi input numeric là `BigDecimal`. Nếu báo cáo yêu cầu **average money chính xác theo quy tắc decimal**, cân nhắc lấy `SUM` và `COUNT` rồi chia bằng `BigDecimal` có `RoundingMode` rõ.

Ví dụ:

```java
BigDecimal average = count == 0L
    ? BigDecimal.ZERO
    : sum.divide(
        BigDecimal.valueOf(count),
        2,
        RoundingMode.HALF_UP);
```

Không lấy `new BigDecimal(doubleValue)` bừa bãi vì có thể mang lỗi biểu diễn binary floating-point. `RoundingMode` phải tuân theo quy tắc tính tiền của sản phẩm, không tự chọn một mode cho mọi domain.

### 10.5. `MIN` và `MAX`

Ví dụ lấy thời điểm đơn đầu/đơn cuối:

```java
List<Object[]> result = em.createQuery(
        "select min(o.createdAt), max(o.createdAt) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant",
        Object[].class)
    .setParameter("tenant", tenantId)
    .getResultList();
```

Nếu không có data, các biểu thức `MIN`/`MAX` có thể trả NULL. Nên dùng DTO/tuple khi report cần thêm columns và mapping lâu dài.

### 10.6. `COUNT(DISTINCT ...)`

```java
Long customerCount = em.createQuery(
        "select count(distinct o.customer.id) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant",
        Long.class)
    .setParameter("tenant", tenantId)
    .getSingleResult();
```

Đếm distinct customers có ít nhất một order, không phải distinct orders. Khi chọn metric cần nói rõ unit đếm.

## 11. `GROUP BY`: mỗi nhóm tương ứng một dòng báo cáo

`GROUP BY` gộp các rows có cùng group key rồi tính aggregates trên từng nhóm.

### 11.1. Tổng doanh thu theo khách hàng

DTO:

```java
package example.sales.reporting;

public record CustomerRevenueRow(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal revenue
) {}
```

JPQL:

```java
List<CustomerRevenueRow> report = em.createQuery(
        "select new example.sales.reporting.CustomerRevenueRow(" +
        "    c.id, c.displayName, count(o), sum(o.totalAmount)) " +
        "from SalesOrder o " +
        "join o.customer c " +
        "where o.tenantId = :tenant " +
        "and o.currencyCode = :currency " +
        "and o.status = :paid " +
        "and o.createdAt >= :from " +
        "and o.createdAt < :to " +
        "group by c.id, c.displayName " +
        "order by sum(o.totalAmount) desc, c.id asc",
        CustomerRevenueRow.class)
    .setParameter("tenant", tenantId)
    .setParameter("currency", "VND")
    .setParameter("paid", OrderStatus.PAID)
    .setParameter("from", fromInclusive)
    .setParameter("to", toExclusive)
    .getResultList();
```

### 11.2. Vì sao group theo `c.id, c.displayName`?

Hai customers khác nhau có thể cùng `displayName`. Nếu chỉ group theo display name, report có thể gộp sai hai người. Group theo stable ID giữ đúng identity, tên là thông tin hiển thị bổ sung.

### 11.3. Các biểu thức ngoài aggregate phải hợp lệ với `GROUP BY`

Trong một grouped query, những trường không được bao trong aggregate mà xuất hiện trong select/order expressions cần phù hợp quy tắc GROUP BY của JPQL/SQL. Đừng chọn tùy ý:

```sql
SELECT customer_id, order_code, SUM(total_amount)
FROM sales_orders
GROUP BY customer_id;
```

`order_code` không xác định duy nhất trong mỗi nhóm customer. Một số database từ chối query hoặc có extensions chọn giá trị không rõ nghĩa. Nếu cần “mã đơn mới nhất”, hãy định nghĩa rõ bằng subquery/window hoặc query riêng, không lấy một column bất kỳ.

### 11.4. Group key là entity hay scalar?

Một số JPQL forms cho group theo entity path như `group by o.customer`, nhưng có portability/performance considerations khi provider mở rộng entity columns, đặc biệt với serialized/LOB/eager fields. Cho report lâu dài thường rõ ràng hơn khi group theo `customer.id` và các scalar attributes cần hiển thị.

### 11.5. `GROUP BY` không tự sắp xếp

Rows grouped không có guaranteed presentation order trừ khi query ghi `ORDER BY`. Nếu UI muốn top revenue, thêm `order by sum(...) desc` và tie-breaker ổn định.

## 12. `WHERE` và `HAVING`: lọc trước và sau tổng hợp

`WHERE` lọc **rows đầu vào** trước nhóm; `HAVING` lọc **groups sau khi đã aggregate**.

Ví dụ: khách có ít nhất 5 đơn PAID trong tháng.

```java
List<CustomerRevenueRow> report = em.createQuery(
        "select new example.sales.reporting.CustomerRevenueRow(" +
        "    c.id, c.displayName, count(o), sum(o.totalAmount)) " +
        "from SalesOrder o join o.customer c " +
        "where o.tenantId = :tenant " +
        "and o.status = :paid " +
        "and o.currencyCode = :currency " +
        "and o.createdAt >= :from " +
        "and o.createdAt < :to " +
        "group by c.id, c.displayName " +
        "having count(o) >= :minimum " +
        "order by sum(o.totalAmount) desc",
        CustomerRevenueRow.class)
    .setParameter("tenant", tenantId)
    .setParameter("paid", OrderStatus.PAID)
    .setParameter("currency", "VND")
    .setParameter("from", fromInclusive)
    .setParameter("to", toExclusive)
    .setParameter("minimum", 5L)
    .getResultList();
```

### 12.1. Không đặt aggregate predicate trong `WHERE`

Sai:

```sql
WHERE COUNT(*) >= 5
```

Đúng:

```sql
HAVING COUNT(*) >= 5
```

### 12.2. Lọc status ở WHERE làm thay đổi số đo

Nếu `where status = PAID`, `COUNT(o)` đếm **chỉ paid orders**. Nếu muốn một group row chứa cả paid count và canceled count, đừng filter cả hai ở WHERE; dùng conditional aggregation.

### 12.3. `HAVING` không thay điều kiện tenant

Tenant scoping và date range thuộc `WHERE`/join restrictions để giới hạn rows ngay từ đầu. Đừng tải dữ liệu cross-tenant vào aggregate rồi mới định bỏ bớt groups ở application layer.

### 12.4. Performance

WHERE predicates có thể giảm số rows trước grouping, cho phép optimizer dùng indexes. HAVING thường phải có aggregate state rồi mới lọc groups. Đừng dùng HAVING thay WHERE cho filter có thể áp sớm.

## 13. Conditional aggregation bằng `CASE WHEN`

Dashboard muốn tất cả trạng thái trên cùng một dòng:

```text
tenant=A, paid=120, shipped=90, cancelled=8, total=250
```

Một cách portable thường dùng `SUM(CASE WHEN ... THEN ... ELSE ... END)`.

### 13.1. Ví dụ theo tenant

DTO:

```java
public record OrderStatusCounters(
    String tenantId,
    Long totalOrders,
    Long paidOrders,
    Long shippedOrders,
    Long cancelledOrders
) {}
```

JPQL:

```java
List<OrderStatusCounters> counters = em.createQuery(
        "select new example.sales.reporting.OrderStatusCounters(" +
        "    o.tenantId, " +
        "    count(o), " +
        "    sum(case when o.status = :paid " +
        "        then 1L else 0L end), " +
        "    sum(case when o.status = :shipped " +
        "        then 1L else 0L end), " +
        "    sum(case when o.status = :cancelled " +
        "        then 1L else 0L end)) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "group by o.tenantId",
        OrderStatusCounters.class)
    .setParameter("tenant", tenantId)
    .setParameter("paid", OrderStatus.PAID)
    .setParameter("shipped", OrderStatus.SHIPPED)
    .setParameter("cancelled", OrderStatus.CANCELLED)
    .getResultList();
```

JPQL `CASE` và numeric `SUM` có tính hỗ trợ theo spec/provider; nếu dùng dialect cụ thể hoặc provider cũ, kiểm tra generated SQL và constructor types bằng integration tests. Với input type Long, `SUM` thường trả Long theo JPQL numeric aggregation rules.

### 13.2. Không có order có thể không có group row

Nếu tenant chưa có đơn, query group by tenantId trên `SalesOrder` có thể trả danh sách rỗng, không phải một row toàn zeros. Service nên tạo default metrics row hoặc bắt đầu từ `Tenant` entity rồi LEFT JOIN khi cần liệt kê tenants không có orders.

### 13.3. Tính tỷ lệ

Khi `totalOrders` là 0, tránh phép chia cho 0:

```java
double paidRate = totalOrders == 0L
    ? 0.0
    : (double) paidOrders / totalOrders;
```

Nếu API hiển thị phần trăm, định nghĩa rounding/scale rõ, không mix tỷ lệ 0–1 với tỷ lệ 0–100.

### 13.4. Một aggregate query vẫn có thể nặng

Conditional aggregation có thể cần scan tất cả orders khớp tenant/time. Một round trip không đồng nghĩa chi phí DB thấp; cần index/filter và đánh giá số lượng rows thực tế.

## 14. `COALESCE`, NULL và semantics của aggregate

SQL aggregate có NULL semantics ảnh hưởng trực tiếp dashboard.

### 14.1. `COUNT(*)` khác `COUNT(column)`

Trong SQL:

```sql
COUNT(*)              -- đếm rows
COUNT(discount_amount) -- đếm rows có discount_amount NOT NULL
```

Nếu 100 orders nhưng 30 không có discount, `COUNT(discount_amount)` có thể là 70.

Trong JPQL, `count(o)` đếm entity rows của query; `count(o.optionalField)` loại NULL của field. Không hoán đổi các cách đếm nếu metric là “số đơn”.

### 14.2. `SUM` và `AVG` bỏ qua NULL inputs

`SUM(discount_amount)` không xem NULL là một discount amount, nhưng với một business rule cụ thể có thể muốn coi NULL là zero. `coalesce(o.discountAmount, :zero)` làm rõ ý định khi property tồn tại.

### 14.3. Không có rows

`COUNT` = 0, `SUM`/`AVG`/`MIN`/`MAX` = NULL trong kết quả aggregate không nhóm khi không có input phù hợp. Grouped queries có thể không có result rows.

### 14.4. Không mặc định NULL và zero đồng nghĩa

- **Zero revenue**: đã có số liệu xác nhận giá trị tổng bằng 0.
- **NULL**: metric không có dữ liệu, không áp dụng hoặc chưa được tính, tùy nguồn.

Trong dashboard kế toán, phân biệt hai trạng thái có thể quan trọng. `COALESCE` làm API gọn nhưng cần chọn theo nghiệp vụ, không phải cứ gặp NULL là thay 0.

## 15. `JOIN` trong aggregate: nguồn sai số dễ bị bỏ qua

Giả sử:

```text
Order #1 total=100, items: A, B, C (3 dòng)
Order #2 total=200, items: D (1 dòng)
```

Nếu chạy:

```sql
SELECT SUM(o.total_amount)
FROM sales_orders o
JOIN order_items i
  ON i.order_id = o.id;
```

kết quả là **500** chứ không phải 300:

```text
Order #1 total 100 xuất hiện 3 lần
Order #2 total 200 xuất hiện 1 lần
SUM = 100 + 100 + 100 + 200 = 500
```

### 15.1. Sai lầm tương đương trong JPQL

```java
BigDecimal revenue = em.createQuery(
        "select sum(o.totalAmount) " +
        "from SalesOrder o join o.items i",
        BigDecimal.class)
    .getSingleResult();
```

Khi `o.totalAmount` là amount ở **mức order**, join items làm nhân rows ở **mức item**. Aggregate tính trên kết quả join, không tự hiểu một order phải đếm đúng một lần.

### 15.2. Không “sửa” bằng `SUM(DISTINCT totalAmount)`

Nếu hai orders khác nhau cùng `totalAmount=100`, `SUM(DISTINCT o.totalAmount)` chỉ cộng 100 một lần. `DISTINCT` áp dụng vào **giá trị amount**, không vào order identity. Đây là lỗi rất dễ lọt qua tests nhỏ.

### 15.3. Ba giải pháp tùy metric

**Giải pháp A — Tính doanh thu từ bảng order, không join items:**

```java
"select sum(o.totalAmount) from SalesOrder o " +
"where o.tenantId = :tenant and o.status = :paid"
```

**Giải pháp B — Nếu cần điều kiện “có item SKU X”, dùng `EXISTS` để không nhân order rows:**

```java
BigDecimal revenue = em.createQuery(
        "select sum(o.totalAmount) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "and exists (" +
        "    select i.id from OrderItem i " +
        "    where i.order = o and i.sku = :sku" +
        ")",
        BigDecimal.class)
    .setParameter("tenant", tenantId)
    .setParameter("sku", sku)
    .getSingleResult();
```

**Giải pháp C — Nếu metric là item revenue, tính trên items:**

```java
BigDecimal itemRevenue = em.createQuery(
        "select sum(i.unitPrice * i.quantity) " +
        "from OrderItem i " +
        "join i.order o " +
        "where o.tenantId = :tenant " +
        "and o.status = :paid",
        BigDecimal.class)
    .setParameter("tenant", tenantId)
    .setParameter("paid", OrderStatus.PAID)
    .getSingleResult();
```

Arithmetic trong JPQL và result numeric typing cần kiểm tra với provider/driver, nhất là khi kết hợp `BigDecimal` và integral fields. Đồng thời `itemRevenue` có thể không bằng `order.totalAmount` nếu tổng đơn gồm shipping, tax, discount hoặc rounding.

### 15.4. Phân biệt grain

- **Order grain**: mỗi row là một đơn.
- **Item grain**: mỗi row là một dòng hàng.
- **Customer grain**: một row kết quả cho một khách.
- **Daily grain**: một row kết quả cho một ngày.

Trước khi viết `JOIN` và `SUM`, ghi rõ **grain của metric**. Đừng cộng một số đo ở cấp order sau khi chuyển sang item grain mà không điều chỉnh.

## 16. `COUNT` sau join: đếm đơn hay đếm dòng hàng?

Giả sử `Order#1` có 3 items và `Order#2` có 1 item.

```java
Long joinedCount = em.createQuery(
        "select count(o) " +
        "from SalesOrder o join o.items i",
        Long.class)
    .getSingleResult();
```

Kết quả có thể là 4 vì đếm các rows sau join, **không phải 2 orders**.

### 16.1. Đếm distinct orders

```java
Long distinctOrders = em.createQuery(
        "select count(distinct o.id) " +
        "from SalesOrder o join o.items i",
        Long.class)
    .getSingleResult();
```

Kết quả 2 trong ví dụ.

### 16.2. Tại sao đôi khi `COUNT(DISTINCT)` vẫn không đủ?

Nó giải quyết **đếm order IDs**, nhưng không giải quyết `SUM(o.totalAmount)` bị nhân. Cần thiết kế riêng từng metric theo grain.

### 16.3. Đếm items

Nếu metric là số dòng hàng:

```java
Long itemCount = em.createQuery(
        "select count(i) from OrderItem i " +
        "join i.order o " +
        "where o.tenantId = :tenant",
        Long.class)
    .setParameter("tenant", tenantId)
    .getSingleResult();
```

### 16.4. Tổng số lượng khác số item rows

`COUNT(i)` đếm số dòng hàng; `SUM(i.quantity)` đếm tổng số lượng sản phẩm theo quantity. Một dòng hàng quantity 7 chỉ là một item row nhưng bảy đơn vị bán. Phải chọn metric đúng.

## 17. `LEFT JOIN` và nhóm không có dữ liệu

Một báo cáo có thể cần **cả những khách chưa có đơn**. Nếu bắt đầu từ SalesOrder và inner join Customer, những khách không có orders sẽ biến mất.

### 17.1. Bắt đầu từ Customer

Giả định `Customer` có reverse collection:

```java
@OneToMany(mappedBy = "customer")
private List<SalesOrder> orders;
```

JPQL:

```java
List<Tuple> rows = em.createQuery(
        "select c.id as customerId, " +
        "       c.displayName as customerName, " +
        "       count(o.id) as orderCount " +
        "from Customer c " +
        "left join c.orders o " +
        "group by c.id, c.displayName",
        Tuple.class)
    .getResultList();
```

Khách chưa có order nhận `orderCount=0` vì `COUNT(o.id)` bỏ qua NULL. Nếu dùng `COUNT(c)`, outer row vẫn chứa c nên khách đó có thể bị đếm là 1 — sai metric orders.

### 17.2. Điều kiện trên joined entity trong `WHERE`

```java
"from Customer c left join c.orders o " +
"where o.status = :paid"
```

Điều kiện `o.status=:paid` trong WHERE loại rows có `o=NULL`, thường làm mất khách không có orders và phá ý định của LEFT JOIN.

### 17.3. Đưa filter vào `ON`

Với JPQL hỗ trợ join condition:

```java
List<Tuple> rows = em.createQuery(
        "select c.id as customerId, " +
        "       count(o.id) as paidOrderCount " +
        "from Customer c " +
        "left join c.orders o on o.status = :paid " +
        "group by c.id",
        Tuple.class)
    .setParameter("paid", OrderStatus.PAID)
    .getResultList();
```

Điều kiện trong ON giới hạn **những matched orders** nhưng vẫn giữ khách không có matches.

### 17.4. Tenant boundary vẫn bắt buộc

Ở multi-tenant model, `Customer` cũng cần tenant scoping thích hợp. Nếu một khách có orders đa tenant hoặc reverse collection bao phủ dữ liệu ngoài tenant, filter trên ON phải có tenant restriction cho orders, còn root Customer cũng phải được scope theo authorized tenant. Không chỉ thêm tenant filter vào WHERE một cách tùy tiện vì có thể thay đổi LEFT JOIN semantics.

### 17.5. Zero rows khi không có root Customer

LEFT JOIN chỉ giữ rows của **root side**. Nếu root Customer không có bản ghi nào, query vẫn trả 0 rows, không tự sinh một “grand total zero” row.

## 18. Join nhiều collection: phép nhân hàng ngoài ý muốn

Giả sử mỗi `SalesOrder` có:

```text
3 OrderItem
2 PaymentAttempt
```

Nếu query:

```sql
FROM sales_orders o
JOIN order_items i ON i.order_id = o.id
JOIN payment_attempts p ON p.order_id = o.id
```

thì mỗi order có thể tạo **3 × 2 = 6 rows**. Khi `SUM(i.quantity)`, quantity của mỗi item bị cộng lặp **hai lần**; khi `SUM(p.amount)`, mỗi payment attempt bị cộng **ba lần**.

### 18.1. Hai quan hệ 1:N không có nghĩa hai dimensions độc lập

Join bảng child A và child B cùng theo parent chỉ kết nối bằng `parent_id`; database tạo các cặp combinations của children. Nếu muốn item totals và payment totals, không cộng cả hai trực tiếp trên một flat joined dataset.

### 18.2. Giải pháp dùng pre-aggregation

Trong native SQL:

```sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity) AS item_quantity
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_amount
    FROM payment_attempts
    WHERE state = 'CAPTURED'
    GROUP BY order_id
)
SELECT
    o.id,
    COALESCE(i.item_quantity, 0) AS item_quantity,
    COALESCE(p.paid_amount, 0) AS paid_amount
FROM sales_orders o
LEFT JOIN item_totals i ON i.order_id = o.id
LEFT JOIN payment_totals p ON p.order_id = o.id
WHERE o.tenant_id = :tenant_id;
```

Ở đây mỗi child table được tổng hợp **về một row trên order_id trước khi join**, tránh tích Descartes giữa hai sets. Đây là PostgreSQL/native SQL ví dụ; cần điều chỉnh syntax/parameter binding theo DB/provider.

### 18.3. Giải pháp query riêng

Với dashboard nhỏ, chạy hai grouped queries độc lập rồi merge results theo `orderId`/`customerId` trong ứng dụng có thể rõ ràng và hiệu quả hơn một query rất phức tạp. Cần hiểu transaction isolation/snapshot khi muốn số liệu giữa hai queries nhất quán.

### 18.4. Giải pháp aggregate ledger

Với tài chính, có thể chọn một nguồn dữ liệu canonical như payment ledger để tính `capturedAmount` thay vì suy từ nhiều bảng quan hệ không trực tiếp phản ánh doanh thu. Đây là quyết định domain model trước khi tối ưu query.

### 18.5. Checklist grain

Trước mỗi `SUM`/`COUNT` sau join, hỏi:

- Source metric nằm ở grain nào?
- Join có thể nhân source row lên mấy lần?
- `DISTINCT` trên identifier có cứu đúng loại metric không?
- Có thể `EXISTS` thay join khi chỉ cần kiểm tra tồn tại?
- Có thể pre-aggregate child trước?
- Có cần `COUNT DISTINCT` trên entity identity thay vì count joined rows?

## 19. Projection có `DISTINCT`: khi nào hữu ích?

`DISTINCT` loại kết quả duplicate theo **selected values**; nó không giải quyết mọi duplication về nghĩa dữ liệu.

### 19.1. Distinct customer IDs

```java
List<Long> customerIds = em.createQuery(
        "select distinct o.customer.id " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant",
        Long.class)
    .setParameter("tenant", tenantId)
    .getResultList();
```

Một customer có 20 orders chỉ xuất hiện một lần.

### 19.2. Distinct display names là sai identity

```java
"select distinct c.displayName from Customer c"
```

chỉ cho tập tên khác nhau, không phải tập customers. Hai người trùng tên có thể bị gộp. Chọn `c.id` nếu nhu cầu là distinct customer entities.

### 19.3. `DISTINCT` sau join có chi phí

Database có thể phải sort/hash để loại duplicates. Nếu chỉ muốn kiểm tra tồn tại child, `EXISTS` thường diễn tả rõ hơn. Không “rắc DISTINCT” để che mọi join design lỗi.

### 19.4. Constructor DTO và DISTINCT

JPQL có thể đặt `distinct` trước constructor expression phù hợp với provider:

```java
"select distinct new example.sales.reporting.OrderListRow(" +
"o.id, o.orderCode, c.displayName, " +
"o.totalAmount, o.currencyCode, o.createdAt) " +
"from SalesOrder o join o.customer c"
```

Nhưng nếu join to-many rồi chỉ chọn order-level fields, việc loại duplicate muộn có thể tăng chi phí và gây vấn đề pagination. Ưu tiên sửa join hoặc dùng `EXISTS` theo business predicate.

## 20. Báo cáo theo ngày, tuần, tháng: time bucket có timezone

Một dashboard “doanh thu mỗi ngày” tưởng chừng chỉ là `GROUP BY DATE(created_at)`. Nhưng một **ngày nghiệp vụ** phụ thuộc timezone.

### 20.1. Vì sao timezone quan trọng?

`2026-10-01T18:30:00Z` ở Việt Nam (UTC+7) là `2026-10-02 01:30`. Nếu group theo UTC date, order thuộc ngày 1/10; nếu group theo giờ Việt Nam, order thuộc ngày 2/10.

**Định nghĩa ngày báo cáo trước khi viết SQL**:

- Timezone nào: UTC, tenant's configured zone, chi nhánh, hay customer local zone?
- Khoảng thời gian gồm ranh giới nào?
- Có daylight saving time ở timezone đó không?
- Tính payment timestamp hay order creation timestamp?
- Dữ liệu late-arriving/backdated tính thế nào?

### 20.2. Khoảng nửa mở `[from, to)`

Trong Java:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate fromDay = LocalDate.of(2026, 10, 1);
LocalDate toDayExclusive = LocalDate.of(2026, 11, 1);

Instant from = fromDay.atStartOfDay(zone).toInstant();
Instant to = toDayExclusive.atStartOfDay(zone).toInstant();
```

JPQL filter:

```java
"where o.createdAt >= :from " +
"and o.createdAt < :to"
```

Không dùng `BETWEEN` với “23:59:59.999” tự tính vì có các mức precision khác nhau và lỗi ranh giới. Với timezone có DST, độ dài một ngày có thể khác 24 giờ; chuyển ngày local sang instant đúng cách.

### 20.3. Date bucketing trong PostgreSQL

Nếu `created_at` là `timestamptz`:

```sql
SELECT
    (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM sales_orders
WHERE tenant_id = :tenant_id
  AND currency_code = :currency
  AND status = 'PAID'
  AND created_at >= :from_utc
  AND created_at < :to_utc
GROUP BY local_day
ORDER BY local_day;
```

Đây là PostgreSQL-specific SQL. Các DB khác có date/time functions và timezone conversion syntax khác. Query condition dùng UTC instants đã tính từ local boundaries để index trên `created_at` có cơ hội được dùng; không wrap cột bằng function trong mọi WHERE predicate nếu tránh được.

### 20.4. JPQL chuẩn có hạn chế về time buckets tùy version/provider

Một số JPQL versions hỗ trợ datetime extraction functions, và provider có thể cho gọi `FUNCTION('date_trunc', ...)`. Tuy nhiên khi cần calendar weeks, fiscal quarters, timezone conversions hoặc date series, **native SQL/reporting view** thường minh bạch hơn. Không viết một query `function('date_trunc', ...)` rồi tuyên bố portable cho mọi RDBMS.

### 20.5. Ngày không có giao dịch

`GROUP BY date` chỉ tạo rows cho ngày **có data**. Dashboard thường muốn bảy ngày liên tục với cả những ngày zero. Cần:

- Calendar/date dimension rồi LEFT JOIN aggregate.
- Native SQL `generate_series` trên PostgreSQL.
- Hoặc application tạo danh sách ngày mong đợi và điền zeros vào missing buckets theo đúng metric semantics.

Không thêm zero rows một cách thiếu thông tin khi metric là unknown/unavailable thay vì confirmed zero.

### 20.6. Tuần ISO, tháng và fiscal calendar

“Week 1” phụ thuộc ISO week/year semantics; một tuần cuối tháng 12 có thể thuộc ISO week-year của năm sau. Fiscal quarter có thể không bắt đầu vào tháng 1. Calendar dimension hoặc domain calendar library sẽ giúp tránh query logic mơ hồ.

### 20.7. Timezone conversion có thể thay khi tenant đổi timezone

Nếu tenant thay timezone cấu hình, báo cáo lịch sử có cần giữ cách tính ngày cũ không? Một số hệ thống cần lưu reporting timezone/cutoff như versioned business configuration. Đây là requirement riêng, không được giải quyết chỉ bằng `created_at`.

## 21. Báo cáo tiền: currency, rounding, refunds và snapshot

Những query `SUM(totalAmount)` chỉ chính xác nếu `totalAmount` mang cùng ý nghĩa và cùng đơn vị.

### 21.1. Không cộng tiền khác currency

Sai:

```sql
SELECT SUM(total_amount)
FROM sales_orders;
```

khi có VND, USD, EUR trong cùng bảng.

Tối thiểu group/filter theo currency:

```java
public record RevenueByCurrency(
    String currencyCode,
    BigDecimal revenue
) {}
```

```java
List<RevenueByCurrency> rows = em.createQuery(
        "select new example.sales.reporting.RevenueByCurrency(" +
        "    o.currencyCode, sum(o.totalAmount)) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "and o.status = :paid " +
        "group by o.currencyCode",
        RevenueByCurrency.class)
    .setParameter("tenant", tenantId)
    .setParameter("paid", OrderStatus.PAID)
    .getResultList();
```

### 21.2. Chuyển đổi currency cần exchange rate policy

Một báo cáo gộp về VND phải xác định:

- Rate tại thời điểm tạo đơn, thanh toán hay kết toán?
- Rate source và version.
- Cách rounding theo currency.
- Số tiền converted được lưu snapshot hay tính động?
- Refund tính theo rate nào?

Không dùng exchange rate hôm nay để tính lại lịch sử nếu domain cần booked amount.

### 21.3. Gross revenue vs net revenue

`status = PAID` không đủ phân biệt:

- Paid amount đã capture.
- Refund đã hoàn tất.
- Partial refund.
- Chargeback.
- Discount/tax/shipping.
- Gift cards hoặc store credits.

Nếu nghiệp vụ là kế toán, một `payment_ledger` hoặc revenue-recognition read model thường đúng nghĩa hơn order status đơn giản.

### 21.4. Số lượng và đơn vị

`SUM(i.quantity)` chỉ cộng đúng nếu units tương thích; một item tính theo “kg” và item khác tính theo “piece” không thể cộng thành một “units sold” metric hữu nghĩa mà không group theo UOM hoặc convert.

### 21.5. Average order value

Nếu `AOV = total revenue / paid order count`, cần tránh đếm item rows thay order count. Với money, chia dùng `BigDecimal`/rounding policy. Nên định nghĩa denominator: orders PAID, unique completed checkouts hay payment events?

### 21.6. Tính theo snapshot để không bị sửa lịch sử

Nếu giá sản phẩm hiện tại thay đổi, báo cáo doanh thu lịch sử phải dùng `OrderItem.unitPriceAtPurchase` hoặc một captured amount immutable, không join `Product.currentPrice` rồi nhân quantity.

**Hiệu năng không cứu được số liệu sai nguồn**. Chọn grain và source-of-truth đúng trước khi tối ưu projection.

## 22. Phân trang báo cáo thường và báo cáo GROUP BY

Một danh sách đơn hàng có thể dùng:

```java
query.setFirstResult(100);
query.setMaxResults(50);
```

Nhưng với grouped report, đối tượng phân trang là **các groups**, không phải raw input orders.

### 22.1. Pagination trên aggregate results

Ví dụ:

```java
TypedQuery<CustomerRevenueRow> query =
    em.createQuery(
        "select new example.sales.reporting.CustomerRevenueRow(" +
        "c.id, c.displayName, count(o), sum(o.totalAmount)) " +
        "from SalesOrder o join o.customer c " +
        "where o.tenantId = :tenant " +
        "and o.status = :paid " +
        "group by c.id, c.displayName " +
        "order by sum(o.totalAmount) desc, c.id asc",
        CustomerRevenueRow.class);

query.setParameter("tenant", tenantId);
query.setParameter("paid", OrderStatus.PAID);
query.setFirstResult(0);
query.setMaxResults(20);

List<CustomerRevenueRow> firstPage = query.getResultList();
```

### 22.2. Không dùng `COUNT(o)` làm total pages của grouped report

Query nhóm theo customer trả 1 row/customer. `COUNT(o)` đếm orders, không đếm group rows. Nếu cần tổng số groups (customers có paid orders):

```java
Long totalCustomers = em.createQuery(
        "select count(distinct o.customer.id) " +
        "from SalesOrder o " +
        "where o.tenantId = :tenant " +
        "and o.status = :paid",
        Long.class)
    .setParameter("tenant", tenantId)
    .setParameter("paid", OrderStatus.PAID)
    .getSingleResult();
```

Đây là count phù hợp nếu query chính group theo **customer identity** và có cùng filters. Nếu `HAVING sum(...) >= threshold` thì `count(distinct customer.id)` **không đủ**: phải đếm groups thỏa HAVING, thường bằng native subquery/CTE hoặc một counting strategy khác.

### 22.3. Pagination ổn định cần tie-breaker

Nếu hai customers có cùng revenue:

```sql
ORDER BY revenue DESC
```

không bảo đảm ổn định thứ tự giữa hai groups. Thêm `customer_id ASC` để kết quả dễ dự đoán:

```sql
ORDER BY revenue DESC, customer_id ASC
```

### 22.4. OFFSET trên kết quả aggregate vẫn có thể đắt

Database có thể phải tính tổng hợp/sắp xếp cho rất nhiều groups trước khi bỏ qua `OFFSET`. Với hàng triệu customers, cân nhắc batch export, keyset/seek theo metric+ID (khi có thể) hoặc precomputed summary tables.

### 22.5. Tổng số nhóm thay đổi trong lúc phân trang

Báo cáo realtime có thể thay đổi giữa page 1 và page 2. Không hứa snapshot consistency nếu mỗi HTTP request chạy một transaction mới dưới isolation thông thường. Với report cần tái lập, dùng report run/snapshot token/cutoff.

## 23. Keyset pagination cho danh sách lớn

Đối với danh sách orders đã sort:

```text
ORDER BY created_at DESC, id DESC
```

thay vì `OFFSET 100000`, có thể dùng seek condition:

```java
List<OrderListRow> next = em.createQuery(
        "select new example.sales.reporting.OrderListRow(" +
        "o.id, o.orderCode, c.displayName, " +
        "o.totalAmount, o.currencyCode, o.createdAt) " +
        "from SalesOrder o join o.customer c " +
        "where o.tenantId = :tenant " +
        "and (o.createdAt < :lastTime " +
        "     or (o.createdAt = :lastTime and o.id < :lastId)) " +
        "order by o.createdAt desc, o.id desc",
        OrderListRow.class)
    .setParameter("tenant", tenantId)
    .setParameter("lastTime", lastCreatedAt)
    .setParameter("lastId", lastId)
    .setMaxResults(50)
    .getResultList();
```

### 23.1. Điều kiện

- Sort keys phải xác định và stable nếu muốn trải nghiệm pagination dễ tái lập.
- `createdAt`/`id` không nên bị thay trong lúc duyệt.
- Cursor phải chứa fields dùng trong ORDER BY và filter snapshot nếu có.
- Index candidate: `(tenant_id, created_at DESC, id DESC)`.
- Client không nên tự sửa tenant/cursor; validate/encode cursor theo security policy.

### 23.2. Keyset cho top aggregate khó hơn

Nếu sort theo `SUM(revenue) DESC`, tổng có thể thay đổi giữa requests. Keyset trên aggregate có thể cần snapshot/materialized result để tránh trùng/mất groups khi doanh thu biến động.

### 23.3. Không nhầm keyset với “không tính aggregate”

Seek giúp bỏ qua rows/groups hiệu quả trong một số query shapes; nếu report vẫn cần tính SUM trên hàng trăm triệu orders để biết thứ tự, database vẫn có chi phí aggregation lớn. Đó là lúc cần summary tables hoặc analytical store.

## 24. Criteria API: projection động có type information

Khi người dùng bật/tắt filters tùy ý, xây JPQL string nối thủ công dễ sai. Criteria API cho phép cấu thành AST query.

### 24.1. Criteria DTO projection

Giả sử DTO:

```java
public record CustomerTotal(
    Long customerId,
    BigDecimal revenue
) {}
```

Criteria query:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<CustomerTotal> cq =
    cb.createQuery(CustomerTotal.class);

Root<SalesOrder> order = cq.from(SalesOrder.class);
Path<Long> customerId =
    order.get("customer").get("id");
Path<BigDecimal> amount = order.get("totalAmount");

cq.select(
    cb.construct(
        CustomerTotal.class,
        customerId,
        cb.sum(amount)
    )
);

cq.where(
    cb.equal(order.get("tenantId"), tenantId),
    cb.equal(order.get("status"), OrderStatus.PAID)
);

cq.groupBy(customerId);
cq.orderBy(cb.desc(cb.sum(amount)));

List<CustomerTotal> results =
    em.createQuery(cq).getResultList();
```

### 24.2. `cb.construct` là constructor projection

Nó xây DTO bằng constructor arguments theo thứ tự, tương tự JPQL `select new`; không làm DTO thành managed entity.

### 24.3. `groupBy`/`having`

```java
Expression<Long> orderCount = cb.count(order);
cq.having(cb.ge(orderCount, 5L));
```

Đảm bảo `cq.groupBy(customerId)` đã phù hợp với select expressions. Aggregation semantics vẫn như SQL, Criteria API không tự tránh duplicated join rows.

### 24.4. Criteria Tuple

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<SalesOrder> root = cq.from(SalesOrder.class);

cq.multiselect(
    root.get("status").alias("status"),
    cb.count(root).alias("count")
);
cq.groupBy(root.get("status"));
```

Hữu ích cho report builder với dimensions được chọn động. Với public API, nên chuyển Tuple sang application-defined column descriptors/rows thay vì trả trực tiếp JPA types.

### 24.5. Static metamodel

`root.get("tenantId")` vẫn là chuỗi property name. Nếu dự án bật JPA static metamodel generation, dùng `SalesOrder_.tenantId` giúp giảm lỗi khi rename fields, nhưng cần annotation processor/configuration tương ứng.

### 24.6. Criteria không giải quyết mọi SQL analytics

Window functions, recursive CTEs, `generate_series`, percentile distributions và vendor-specific aggregates thường dễ diễn tả bằng native SQL hoặc reporting read model hơn Criteria thuần Jakarta Persistence.

## 25. Chọn JPQL hay native SQL?

Đây là quyết định về **khả năng biểu diễn, tính portable, khả năng tối ưu và chi phí bảo trì**.

| Tiêu chí | JPQL/Criteria | Native SQL |
|---|---|---|
| Tham chiếu entity/attribute mapping | Trực tiếp | Phải dùng physical tables/columns |
| Basic projection, joins, GROUP BY/HAVING | Tốt | Tốt |
| Đa database, ít SQL-specific syntax | Thường thuận lợi | Cần SQL dialect strategy |
| Window functions/CTE phức tạp | Phụ thuộc version/provider extensions | Mạnh trong DB hỗ trợ |
| `date_trunc`/`generate_series`/timezone bucket | Thường provider-specific | Diễn đạt trực tiếp theo DB |
| Complex pre-aggregation | Có thể qua nhiều JPQL queries/subqueries phù hợp | CTE/subquery dễ diễn đạt |
| Query plan tuning | Thấy SQL do provider tạo | Kiểm soát SQL trực tiếp |
| Mapping kết quả | DTO/record/tuple thuận tiện | Cần result mapping/alias/type conversion |
| SQL DB-specific optimizations | Hạn chế | Chủ động dùng optimizer features |

### 25.1. Đừng chọn native SQL chỉ để “nhanh hơn”

Một JPQL grouped query đơn giản có thể được dịch thành SQL tương đương native query và dùng cùng execution plan. **Chênh lệch hiệu năng cần đo**, không được giả định “native luôn nhanh”.

### 25.2. Khi native SQL đáng dùng

- CTE nhiều bước pre-aggregation.
- Window functions để rank/top-N per group.
- Conditional aggregation dùng cú pháp DB-specific.
- Timezone-aware date buckets, generate_series/calendar dimension.
- Recursive hierarchy report.
- Percentiles/median/histograms đặc thù DB.
- Materialized views hoặc DB table functions.
- SQL hints/index-only plans khi đã đo cần thiết.

### 25.3. Khi JPQL thường tốt hơn

- Truy vấn dữ liệu từ 1–3 entities đơn giản.
- DTO projections và aggregate count/sum theo một chiều.
- Filters tự nhiên theo entity attributes.
- Ứng dụng cần portability giữa database vendors.
- Giữ nhất quán với mapping tên field/relations.

### 25.4. Đọc nhiều dữ liệu bằng native query vẫn có chi phí

`SELECT *` native trên một triệu orders không tự tốt hơn `SELECT o` JPQL. Cần chọn columns, filters, aggregation, pagination và data access strategy đúng.

## 26. Native SQL trả DTO: cách ánh xạ kết quả

Với Jakarta Persistence:

```java
List<?> raw = em.createNativeQuery(
        "select status, count(*) from sales_orders " +
        "where tenant_id = ? " +
        "group by status")
    .setParameter(1, tenantId)
    .getResultList();
```

Kết quả nhiều cột thường được trả qua `Object[]` với JDBC/provider-specific numeric types. Ví dụ `COUNT(*)` đôi khi được map thành `BigInteger` hoặc `Long`, tùy stack; không ép cast tùy tiện khi muốn code portable.

### 26.1. `@SqlResultSetMapping`

Để map dữ liệu thành DTO, JPA có `@SqlResultSetMapping` và `@ConstructorResult`.

```java
@SqlResultSetMapping(
    name = "CustomerRevenueMapping",
    classes = @ConstructorResult(
        targetClass =
            example.sales.reporting.CustomerRevenueRow.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "customer_name", type = String.class),
            @ColumnResult(name = "order_count", type = Long.class),
            @ColumnResult(name = "revenue", type = BigDecimal.class)
        }
    )
)
@Entity
public class SalesOrder {
    // Entity mapping...
}
```

Query:

```java
@SuppressWarnings("unchecked")
List<CustomerRevenueRow> rows =
    em.createNativeQuery(
        """
        SELECT
            c.id AS customer_id,
            c.display_name AS customer_name,
            COUNT(o.id) AS order_count,
            SUM(o.total_amount) AS revenue
        FROM sales_orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.tenant_id = ?
          AND o.status = 'PAID'
        GROUP BY c.id, c.display_name
        """,
        "CustomerRevenueMapping")
    .setParameter(1, tenantId)
    .getResultList();
```

Mã là các fragments minh họa cần đặt mapping annotation trên một managed class được persistence unit nhận diện; các aliases, JDBC types và constructor signatures phải khớp. Tùy provider/driver, casting/conversion cần được kiểm chứng.

### 26.2. Native SQL parameters

Bind parameters cho **giá trị** như tenant, dates, statuses. Không nối input:

```java
String sql =
    "where tenant_id = '" + userInput + "'";
```

vì tạo rủi ro SQL injection. JPA native SQL support cho named parameters không hoàn toàn giống JPQL qua mọi providers; dùng positional parameters khi cần portability và kiểm chứng cú pháp trên stack hiện tại.

### 26.3. Dynamic ORDER BY không bind column names

Không thể đặt tên cột tùy ý vào một bind parameter để database coi đó là SQL identifier:

```sql
ORDER BY ?
```

Nếu UI chọn sort field, application map từ một **allowlist enum → trusted SQL fragment**, không nối raw user strings:

```java
String sortExpression = switch (sortKey) {
    case REVENUE -> "revenue DESC";
    case ORDER_COUNT -> "order_count DESC";
    case CUSTOMER_NAME -> "customer_name ASC";
};
```

Thêm stable tie-breaker, validate direction và không cho clients gửi arbitrary SQL expressions.

### 26.4. DTO tốt cho read model, không dùng entity mapping giả

Không nên map mỗi aggregate row thành `@Entity` giả có `@Id` trùng lặp tùy tiện chỉ để JPA trả kiểu object. Entity có identity/lifecycle semantics, có thể gây identity-map collisions khi group IDs không unique. Chọn DTO/constructor mapping cho report rows.

## 27. CTE: chia báo cáo phức tạp thành các bước rõ ràng

Common Table Expression (`WITH`) giúp biểu diễn **pre-aggregation, filtering, reconciliation**.

Ví dụ khách hàng có doanh thu, quantity và số đơn nhưng tránh nhân hàng:

```sql
WITH order_summary AS (
    SELECT
        o.id,
        o.customer_id,
        o.total_amount
    FROM sales_orders o
    WHERE o.tenant_id = :tenant_id
      AND o.status = 'PAID'
      AND o.currency_code = 'VND'
      AND o.created_at >= :from_utc
      AND o.created_at < :to_utc
),
item_summary AS (
    SELECT
        i.order_id,
        SUM(i.quantity) AS total_quantity
    FROM order_items i
    JOIN order_summary o ON o.id = i.order_id
    GROUP BY i.order_id
)
SELECT
    o.customer_id,
    COUNT(*) AS order_count,
    SUM(o.total_amount) AS revenue,
    COALESCE(SUM(i.total_quantity), 0) AS quantity
FROM order_summary o
LEFT JOIN item_summary i ON i.order_id = o.id
GROUP BY o.customer_id;
```

### 27.1. Vì sao CTE hữu ích?

`order_summary` giữ đúng grain **mỗi order một row**, `item_summary` giữ đúng grain **mỗi order một quantity row**. Kết quả cuối join một-một theo order ID, không bị nhân từng item row.

### 27.2. Không mặc định CTE nhanh hơn subquery

PostgreSQL và DB khác có optimizer behavior cho CTE/materialization/inlining khác nhau theo version. CTE thường giúp **đúng và dễ đọc**; hiệu năng phải đo bằng execution plan.

### 27.3. Sử dụng filter pushdown

Đặt tenant/status/date filter ở `order_summary` có thể giảm số order IDs phải join items. Tuy nhiên optimizer có thể rewrite query; hãy xem actual plan và rows scanned.

### 27.4. Khi nào tách nhiều queries?

Nếu dashboard có nhiều cards không chia sẻ same aggregation grain, 2–4 query độc lập đôi khi dễ cache/index và tối ưu hơn một CTE khổng lồ. Cần lưu ý snapshot consistency và transaction isolation nếu số liệu các cards phải khớp ở cùng một thời điểm.

## 28. Window functions: top-N, ranking và running total

Một số báo cáo không chỉ group mà còn cần **so sánh rows trong cùng partition**.

### 28.1. Top 3 khách hàng theo doanh thu trong mỗi tenant

SQL minh họa:

```sql
WITH revenue_per_customer AS (
    SELECT
        tenant_id,
        customer_id,
        SUM(total_amount) AS revenue
    FROM sales_orders
    WHERE status = 'PAID'
      AND currency_code = 'VND'
    GROUP BY tenant_id, customer_id
),
ranked AS (
    SELECT
        tenant_id,
        customer_id,
        revenue,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id
            ORDER BY revenue DESC, customer_id ASC
        ) AS position
    FROM revenue_per_customer
)
SELECT tenant_id, customer_id, revenue, position
FROM ranked
WHERE position <= 3
ORDER BY tenant_id, position;
```

### 28.2. `ROW_NUMBER` vs `RANK` vs `DENSE_RANK`

- `ROW_NUMBER()`: vị trí duy nhất, phân biệt ties theo ordering.
- `RANK()`: ties cùng rank, có thể nhảy số sau tie.
- `DENSE_RANK()`: ties cùng rank, không nhảy số.

Nếu business muốn “top 3 positions”, dùng ROW_NUMBER với stable tie-breaker. Nếu muốn “mọi khách trong top 3 mức doanh thu, kể cả ties”, DENSE_RANK/RANK có semantics khác. Không chọn tùy ý.

### 28.3. Running total theo ngày

```sql
WITH daily AS (
    SELECT
        created_at::date AS day,
        SUM(total_amount) AS revenue
    FROM sales_orders
    WHERE tenant_id = :tenant_id
      AND status = 'PAID'
      AND currency_code = 'VND'
    GROUP BY created_at::date
)
SELECT
    day,
    revenue,
    SUM(revenue) OVER (
        ORDER BY day
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS cumulative_revenue
FROM daily
ORDER BY day;
```

Lưu ý: `created_at::date` ở PostgreSQL phụ thuộc kiểu dữ liệu/session timezone; với `timestamptz` nên thực hiện bucket theo **business timezone** như mục 20 thay vì mặc định UTC/session.

### 28.4. Moving average

```sql
AVG(revenue) OVER (
    ORDER BY day
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
)
```

đây là trung bình của **bảy rows daily gần nhất**, không nhất thiết bảy **calendar days** nếu thiếu các ngày zero revenue. Muốn moving 7-day average thật, tạo date series đầy đủ hoặc áp dụng frame semantics phù hợp.

### 28.5. JPQL/Criteria support tùy version/provider

Hibernate HQL có extensions window functions trong những phiên bản nhất định; Jakarta Persistence portable JPQL không nên được giả định hỗ trợ mọi `OVER (PARTITION BY ...)`/CTE forms. Nếu project phụ thuộc portability, tách SQL analytics qua repository adapter và integration tests.

### 28.6. Query plan

Window function thường cần sorting/partitioning, tiêu tốn memory và có thể spill ra disk khi dataset lớn. Pre-aggregate trước khi window và cân nhắc indexes nếu phù hợp.

## 29. Date dimension và ngày không có giao dịch

Một báo cáo ngày thường cần đủ ngày, kể cả zero.

### 29.1. PostgreSQL `generate_series`

```sql
WITH days AS (
    SELECT d::date AS day
    FROM generate_series(
        DATE '2026-10-01',
        DATE '2026-10-07',
        INTERVAL '1 day'
    ) AS d
),
daily AS (
    SELECT
        (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS day,
        SUM(total_amount) AS revenue
    FROM sales_orders
    WHERE tenant_id = :tenant_id
      AND status = 'PAID'
      AND currency_code = 'VND'
    GROUP BY 1
)
SELECT
    days.day,
    COALESCE(daily.revenue, 0) AS revenue
FROM days
LEFT JOIN daily ON daily.day = days.day
ORDER BY days.day;
```

Ví dụ nhằm minh họa date series; production nên thêm **UTC range filter** phù hợp khoảng ngày yêu cầu vào CTE daily để tránh quét toàn bộ lịch sử, xử lý date/time parameters động an toàn, và kiểm soát timezone/boundary.

### 29.2. Calendar table

Với fiscal calendars, ngày nghỉ, business weeks, holiday/weekend flags, một bảng `dim_date` có thể tốt hơn tự sinh dates bằng SQL cho mọi report:

```text
date_key
calendar_date
iso_week
iso_week_year
fiscal_period
is_business_day
```

### 29.3. Zero fill trong application

Nếu chỉ 7–30 buckets và query trả sparse rows, Java có thể map by date rồi điền những ngày thiếu. Cách này hợp lý nếu đã thống nhất zero vs missing, currency và timezone; cần kiểm soát data volume và output order.

### 29.4. Report theo tháng cần deterministic boundaries

Đừng lấy “30 ngày gần nhất” thay cho “tháng trước”; đây là hai định nghĩa khác nhau. Tạo local calendar boundaries rồi chuyển sang instant theo reporting zone, filter bằng nửa mở `[from,to)`.

## 30. Thiết kế Spring Data repository cho báo cáo

Tách **command repository** và **reporting query services** giúp trách nhiệm rõ:

```text
OrderCommandService
    -> EntityManager / managed SalesOrder

OrderReportingService
    -> DTO projections / aggregate queries
    -> native SQL read models when needed
```

### 30.1. Một reporting query repository

```java
public interface OrderReportingRepository
        extends Repository<SalesOrder, Long> {

    @Query("""
        select new example.sales.reporting.RevenueByCurrency(
            o.currencyCode, sum(o.totalAmount))
        from SalesOrder o
        where o.tenantId = :tenantId
          and o.status = :paid
          and o.createdAt >= :from
          and o.createdAt < :to
        group by o.currencyCode
        """)
    List<RevenueByCurrency> revenues(
        @Param("tenantId") String tenantId,
        @Param("paid") OrderStatus status,
        @Param("from") Instant from,
        @Param("to") Instant to);
}
```

### 30.2. Không chuyển mọi report thành method name dài

`findByTenantIdAndStatusAndCreatedAtBetween...` hợp lý cho query đơn giản, nhưng aggregate/grouping nhiều dimensions thường dễ đọc hơn với explicit `@Query`/Criteria/custom reporting repository.

### 30.3. Spring Data Page với grouped query

Khi dùng `Page<T>` cho aggregate JPQL, Spring Data có thể không suy ra đúng **count of groups**, nhất là khi có `GROUP BY`/`HAVING`. Cần xác định `countQuery` phản ánh số groups, hoặc xây custom pagination result gồm content + totalGroups.

Ví dụ:

```java
@Query(
    value = """
        select new example.sales.reporting.CustomerTotal(
            o.customer.id, sum(o.totalAmount))
        from SalesOrder o
        where o.tenantId = :tenantId
          and o.status = :paid
        group by o.customer.id
        """,
    countQuery = """
        select count(distinct o.customer.id)
        from SalesOrder o
        where o.tenantId = :tenantId
          and o.status = :paid
        """
)
Page<CustomerTotal> groupByCustomer(
    @Param("tenantId") String tenantId,
    @Param("paid") OrderStatus paid,
    Pageable pageable);
```

Count query này phù hợp **khi không có HAVING trên aggregates** và cùng root filters. Với HAVING, count phải tính sau điều kiện nhóm; giải pháp cần thay đổi.

### 30.4. `Slice<T>` khi không cần total groups

Nếu UI chỉ có “load more”, không cần tổng số trang, Slice hoặc keyset cursor có thể tránh một grouped count query đắt. Nhưng phải bảo đảm stable ordering và xử lý dấu hiệu còn page tiếp theo.

### 30.5. Projection + filter authorization

Repository không nhận arbitrary tenant ID từ client rồi tin đó là quyền. Reporting service cần authorized tenant context, xác minh user permissions và áp đủ tenant predicates cho root, joined tables, native queries.

## 31. Báo cáo lớn: streaming, batching và exports

Một số report cần xuất hàng triệu rows sang CSV/Parquet hoặc downstream analytics. Khi ấy trả `List<DTO>` chứa tất cả rows vẫn có nguy cơ OutOfMemory.

### 31.1. JPA `getResultStream()`

```java
try (Stream<OrderListRow> stream =
        em.createQuery(
            "select new example.sales.reporting.OrderListRow(" +
            "o.id, o.orderCode, c.displayName, " +
            "o.totalAmount, o.currencyCode, o.createdAt) " +
            "from SalesOrder o join o.customer c " +
            "where o.tenantId = :tenant " +
            "order by o.id",
            OrderListRow.class)
        .setParameter("tenant", tenantId)
        .getResultStream()) {
    stream.forEach(csvWriter::writeRow);
}
```

### 31.2. `Stream` không bảo đảm server-side cursor

JPA/provider có thể triển khai `getResultStream()` bằng in-memory results hoặc driver cursor tùy version/configuration. Nếu muốn bounded-memory streaming thật, phải kiểm tra:

- JDBC fetch size.
- Driver autocommit/transaction rules.
- Provider stream implementation.
- Persistence context/connection lifetime.
- Timeout/cancelation.
- Writer backpressure và stream closure.

Không dùng Stream như chứng cứ rằng query chỉ chiếm O(1) memory.

### 31.3. Batch/keyset export

Một lựa chọn dễ kiểm soát:

```text
while more:
  select 1000 DTO rows WHERE id > lastId ORDER BY id
  write batch to export sink
  lastId = max id processed
```

Cần snapshot/cutoff, stable ordering và semantics cho concurrent inserts/updates nếu export phải tái lập.

### 31.4. Read-only transactions

Một transaction `readOnly=true` của Spring có thể cho provider/hints tối ưu dirty checking trong vài cấu hình, nhưng **không có nghĩa database sẽ không chạy SQL hoặc có thể bỏ security/authorization**; behavior phụ thuộc transaction manager/provider. DTO projection là read model nên càng ít cần persistence context state.

### 31.5. Connection lifetime và backpressure

Streaming lâu có thể giữ DB connection/transaction mở, gây connection pool exhaustion hoặc ảnh hưởng vacuum/locks tùy DB isolation. Với export rất lớn, cân nhắc asynchronous job, chunking, analytics store hoặc object storage output.

### 31.6. Không giữ HTTP request mở vô hạn

Một báo cáo 10 GB nên được tạo bởi job có trạng thái, progress, idempotency và access controls, rồi người dùng tải từ storage phù hợp. Đây là kiến trúc phục vụ report, không chỉ tối ưu Java list.

## 32. Indexes cho truy vấn projection và aggregate

Một query tốt ở JPA vẫn có thể chậm nếu database phải đọc quá nhiều rows hoặc sort quá lớn.

### 32.1. Candidate index cho danh sách orders

Query:

```sql
SELECT id, order_code, total_amount, created_at
FROM sales_orders
WHERE tenant_id = ?
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Một candidate B-tree:

```sql
CREATE INDEX idx_orders_tenant_status_time_id
ON sales_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
```

Nó phản ánh equality filters trước, sau đó sort columns. Không có nghĩa index luôn được chọn; phải xem query plan và data distribution.

### 32.2. Candidate cho report tổng hợp

Query:

```sql
SELECT customer_id, SUM(total_amount)
FROM sales_orders
WHERE tenant_id = ?
  AND currency_code = 'VND'
  AND status = 'PAID'
  AND created_at >= ?
  AND created_at < ?
GROUP BY customer_id;
```

Không có một index luôn tối ưu. Có thể cân nhắc `(tenant_id, status, currency_code, created_at, customer_id)` hoặc biến thể theo data selectivity, group key và khả năng index-only scan. Nhưng query vẫn cần aggregate rows khớp filter.

### 32.3. Covering index/INCLUDE

PostgreSQL cho phép:

```sql
CREATE INDEX idx_orders_paid_report
ON sales_orders (
    tenant_id,
    status,
    currency_code,
    created_at
)
INCLUDE (customer_id, total_amount);
```

Included columns có thể hỗ trợ index-only scan khi database visibility/optimizer cho phép; đổi lại tăng kích thước index và write overhead. `@Index` chuẩn JPA không biểu diễn toàn bộ INCLUDE options; cần migration vendor-specific.

### 32.4. Partial index

Nếu 95% queries chỉ lọc PAID:

```sql
CREATE INDEX idx_orders_paid_by_tenant_time
ON sales_orders (tenant_id, created_at)
WHERE status = 'PAID';
```

Một partial index có thể nhỏ hơn toàn bảng, nhưng query predicate/parameterization phải tương thích để optimizer sử dụng được. Đừng tự khẳng định chỉ vì `status=:status` được bind PAID thì mọi planner luôn nhận ra partial predicate.

### 32.5. Index child foreign keys

Khi report từ `OrderItem` join `SalesOrder` theo `order_id`, index trên child FK `order_items(order_id)` có thể giúp theo access plan, nhưng nhiều DB/indexes hiện hữu có thể đã bao phủ. Đừng thêm duplicate index khi chưa xem catalog và plan.

### 32.6. Index cho low-cardinality status

Status có năm giá trị, nếu đại đa số rows là PAID, index chỉ trên `status` có thể ít lợi ích. Composite theo tenant/time/currency hay partial index phù hợp workload hơn, nhưng cần đo.

### 32.7. Index là trade-off

Mỗi index có chi phí:

- Storage và cache footprint.
- INSERT/UPDATE/DELETE maintenance.
- WAL/redo, vacuum/rebuild/statistics.
- Migration locking và thời gian triển khai.

Không tạo một index cho mọi cột tham gia WHERE. Đọc index usage và bỏ duplicate/unused indexes theo quy trình an toàn.

## 33. Đọc `EXPLAIN`: tìm chỗ tốn thời gian thật

JPQL tốt nhất cũng không thay database optimizer. Đo SQL **thực sự được phát**.

### 33.1. PostgreSQL example

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    SUM(total_amount)
FROM sales_orders
WHERE tenant_id = 'TENANT_A'
  AND status = 'PAID'
  AND currency_code = 'VND'
  AND created_at >= TIMESTAMPTZ '2026-10-01T00:00:00Z'
  AND created_at < TIMESTAMPTZ '2026-11-01T00:00:00Z'
GROUP BY customer_id;
```

### 33.2. Những dấu hiệu cần đọc

| Node/metric | Có thể gợi ý |
|---|---|
| `Seq Scan` | Full scan có thể hợp lý hoặc filter/index chưa tốt |
| `Index Scan` | Index giúp tìm rows nhưng có thể nhiều heap reads |
| `Index Only Scan` | Có thể giảm heap reads nếu visibility cho phép |
| `HashAggregate` | Grouping bằng hash table; memory/spill quan trọng |
| `GroupAggregate` | Thường liên quan sorted input/order |
| `Sort` | Có thể tốn RAM/disk nếu nhiều groups |
| `Nested Loop` | Có thể tốt với ít rows, xấu với fan-out lớn |
| `Hash Join` | Có thể hữu ích với sets lớn; memory matters |
| Estimated vs actual rows | Statistics/cardinality estimation có chính xác không |
| Buffers read/hit | I/O pressure, cache behavior |
| Sort spill/temp files | Working memory và query structure |
| Execution time | Chi phí thực trong điều kiện test |

### 33.3. So sánh JPQL và SQL

Nên xem:

1. JPQL/source repository method.
2. Generated SQL và bound parameter **types**.
3. Execution plan với đại diện tenant/date range.
4. SQL row counts trước/sau joins.
5. Thời gian DB so với serialization/network/Java mapping.

Một report chậm có thể do DB scan, nhưng cũng có thể do N+1, per-row service calls, JSON response quá lớn hoặc client rendering.

### 33.4. `EXPLAIN ANALYZE` chạy query thật

Nó tiêu tốn resources. Với DML, nó có thể thực thi write. Chỉ dùng trên môi trường thích hợp, hoặc trong transaction/test protocol được kiểm soát; không chạy tùy tiện câu UPDATE/DELETE trên production.

### 33.5. Test tenants có phân phối dữ liệu khác nhau

`TENANT_A` có 100 orders, `TENANT_B` có 10 triệu. Query plan tốt với A không chứng minh performance với B. Dùng representative cardinality/skew và đo p95/p99 latency.

### 33.6. Query plan thay đổi theo thời gian

Statistics, VACUUM/ANALYZE, DB version, histogram, table growth, data skew, parameter choices đều có thể thay plan. Một benchmark một lần không bảo đảm vô thời hạn.

## 34. Query performance budget và giới hạn kết quả

Một reporting endpoint thường cần các giới hạn:

### 34.1. Giới hạn date range

Không cho user vô tình truy vấn dữ liệu 10 năm nếu màn hình cần tối đa 90 ngày. Hạn mức phải tuân domain/security policy, không chỉ tiện UI.

### 34.2. Giới hạn group cardinality

`GROUP BY customerId` trên 10 triệu customers có thể tạo kết quả rất lớn. Đặt paging/top-N, async export hoặc summary store.

### 34.3. Timeout và cancellation

JPA `Query` có standard hint về query timeout trong một số environments:

```java
query.setHint("jakarta.persistence.query.timeout", 3000);
```

Giá trị được hiểu theo **milliseconds** trong Jakarta Persistence query timeout hint; hỗ trợ/hành vi timeout phụ thuộc provider/driver/database. Timeout không tự kill mọi DB execution một cách hoàn hảo và không thay giới hạn công việc.

### 34.4. Giới hạn output

DTO projection giảm selected columns nhưng một triệu DTOs vẫn rất lớn. Dùng paging, streaming có kiểm chứng, batch export và response size limits.

### 34.5. Giới hạn concurrency

Dashboard tự refresh mỗi 2 giây cho 10.000 users có thể gây load DB cực lớn dù mỗi query 100ms. Cân nhắc caching, refresh cadence, rate limits, shared materialized results và một analytic read model.

### 34.6. Không biến SQL report thành user-defined SQL editor không kiểm soát

Dynamic dimensions, filters và sorts phải được allowlist; bind values; giới hạn complexity, query cost, output size và permissions. Một API báo cáo cho phép arbitrary SQL fragments có rủi ro injection và resource exhaustion.

## 35. Read replica và độ mới dữ liệu

Read replicas thường giảm tải primary DB cho reports, nhưng có **replication lag**.

### 35.1. Ví dụ

```text
12:00:00 Order PAID commit trên primary
12:00:01 UI gọi report qua replica
12:00:01 Replica chưa apply change
12:00:03 Replica bắt kịp
```

Report tại 12:00:01 có thể thiếu order vừa commit. Đây không nhất thiết là SQL sai.

### 35.2. Chọn consistency contract

- **Read-your-writes**: sau khi user thanh toán, số liệu phải thấy ngay.
- **Eventual consistency**: dashboard cập nhật trễ vài giây/phút chấp nhận được.
- **Snapshot consistency**: mọi cards/pages trong một report đại diện cùng một cutoff/version.
- **Auditable report**: phải tái lập được từ dữ liệu/events đã chốt.

Không dùng một read replica eventual-consistent cho yêu cầu read-your-writes mạnh mà không có routing/LSN/synchronization strategy phù hợp.

### 35.3. Báo độ mới cho người dùng

UI có thể hiển thị:

```text
Data as of: 2026-10-03 10:45 UTC
Source: reporting snapshot
```

Chỉ hiển thị timestamp có căn cứ từ data pipeline/snapshot; không dùng thời gian HTTP response làm “data as of” nếu replica/summary đang trễ.

### 35.4. Multi-query dashboard consistency

Nếu card “Tổng doanh thu” và “Doanh thu theo ngày” chạy hai queries ở snapshots khác nhau, tổng có thể lệch. Có thể dùng cùng transaction snapshot ở isolation phù hợp, hoặc cùng materialized snapshot version. Chi phí consistency phải được cân nhắc cùng SLA.

### 35.5. Replicas có thể có different execution plans

Index/schema phải tương thích, nhưng statistics/cache/hardware của replica có thể khác. Benchmark reporting SQL trên nơi nó thực sự chạy, không chỉ primary.

## 36. Cache báo cáo: nhanh hơn nhưng khó invalidation

Các câu tổng hợp giống nhau thường được gọi nhiều lần; cache có thể giảm DB load.

### 36.1. Cache key cần chứa đủ dimensions

Ví dụ:

```text
tenantId
fromUtc
toUtc
statuses
currency
reportVersion
timezone
filters
```

Nếu bỏ `tenantId` khỏi cache key, có nguy cơ **rò dữ liệu giữa tenants**. Nếu bỏ currency/timezone, số liệu có thể bị nhầm nghĩa.

### 36.2. TTL và invalidation

Một dashboard daily revenue có thể chấp nhận cache 1 phút; một màn hình cần số tiền sau giao dịch vừa commit có thể không. Cache invalidation phải gắn với business events hoặc TTL/freshness SLA.

### 36.3. Hibernate second-level/query cache không tự thay report cache

JPA L1 persistence context cache không cache tùy ý GROUP BY report results giữa requests. Hibernate query cache (khi có cấu hình) cũng có invalidation/space usage/tenant correctness considerations; không mặc định đủ cho high-cardinality analytical reports.

### 36.4. Response caching phải tôn trọng authorization

Một cache đã tính cho authorized user với role A có thể chứa fields mà role B không được phép xem. Key hoặc cache boundary cần phản ánh data-scope/permission policy; tránh cache nguyên response nhạy cảm rồi dùng lại cross-user.

### 36.5. Cache không sửa metric sai

Nếu query làm revenue bị nhân vì join, cache chỉ lưu **số sai nhanh hơn**. Correctness tests phải đến trước performance caching.

## 37. Materialized views và bảng tổng hợp trước

Khi dashboard phải aggregate hàng trăm triệu transactions lặp đi lặp lại, một query chạy trực tiếp trên OLTP DB có thể không đáp ứng latency/SLO.

### 37.1. Summary table

Ví dụ:

```sql
CREATE TABLE daily_revenue_summary (
    tenant_id VARCHAR(64) NOT NULL,
    business_day DATE NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    paid_order_count BIGINT NOT NULL,
    revenue NUMERIC(20, 2) NOT NULL,
    calculated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, business_day, currency_code)
);
```

Một row đại diện:

```text
(tenant A, 2026-10-01, VND)
    -> paid_order_count=1024
    -> revenue=502300000.00
```

Đây là read model riêng có **grain ngày × tenant × currency**, giúp dashboard query vài chục summary rows thay vì hàng triệu orders.

### 37.2. Materialized view

PostgreSQL:

```sql
CREATE MATERIALIZED VIEW mv_daily_revenue AS
SELECT
    tenant_id,
    currency_code,
    created_at::date AS business_day,
    COUNT(*) AS paid_order_count,
    SUM(total_amount) AS revenue
FROM sales_orders
WHERE status = 'PAID'
GROUP BY tenant_id, currency_code, created_at::date;
```

Ví dụ dùng `created_at::date` để minh họa; production cần timezone/calendar semantics như phần 20. Materialized view data có thể **stale** cho tới lần refresh. Cách refresh/concurrent refresh/index requirements phụ thuộc database.

### 37.3. Incremental summary updates

Có thể cập nhật daily summary theo các events như `OrderPaid`, `RefundCompleted`. Nhưng cần xử lý:

- At-least-once event delivery và idempotency.
- Events đến trễ/khác thứ tự.
- Refund/chargeback đảo ngược metric.
- Sửa ngày/currency/status sau khi ghi.
- Khả năng rebuild từ source of truth.
- Đối soát với transactional data.

### 37.4. Reconciliation

Định kỳ so:

```text
SUM(source orders/ledger for day)
vs
daily_revenue_summary.revenue
```

Nếu lệch, tìm missing/duplicated events, timezone boundaries, refunds hoặc conversion policies. Không dùng summary table mà không có cách kiểm chứng/rebuild.

### 37.5. Snapshot/cutoff version

Một report cần tái lập có thể ghi:

```text
reportId
tenantId
from/to
currency
reportDefinitionVersion
sourceWatermark
generatedAt
```

Khi gọi lại cùng reportId, người dùng xem cùng snapshot thay vì nhận số liệu thay đổi mỗi lần. Cách này quan trọng với báo cáo kiểm toán hoặc số liệu đã duyệt.

### 37.6. Không nhầm summary table với cache thuần

Summary table có schema, grain, update pipeline, reconciliation và data retention; nó là **một read model có lifecycle**, không chỉ Map trong Java.

## 38. OLTP, OLAP và phân luồng báo cáo

JPA thường chạy trên cơ sở dữ liệu **OLTP**, tối ưu transaction reads/writes từng aggregate. Báo cáo phức tạp có workload khác:

| Đặc tính | OLTP query | Analytical query |
|---|---|---|
| Số rows truy cập | Ít, theo PK/tenant | Nhiều, theo thời gian/dimensions |
| Kết quả | Entity/command state | Grouped metrics/time series |
| Latency | Thấp, predictable | Có thể dài/batch |
| Index | Point/range lookup | Scans, aggregates, columnar structures |
| Consistency | Current transaction state | Snapshot/freshness SLA |
| Dữ liệu | Normalized transactional | Views/denormalized/star schema |

### 38.1. Khi nào chuyển khỏi JPA query trực tiếp?

Một vài dấu hiệu:

- Dashboard aggregate quá nhiều data và gọi liên tục.
- P95 latency cao dù index/filter đã hợp lý.
- Queries cần CTE/window/percentiles nhiều bước.
- Export lớn gây áp lực connection pool/DB I/O.
- Cần retention dài hoặc historical snapshots khác transactional tables.
- OLTP writes bị ảnh hưởng bởi reporting scans.

### 38.2. Các lựa chọn

- Read replica cho query nặng nhưng freshness cho phép.
- Summary tables và materialized views.
- CDC pipeline sang analytical DB/warehouse.
- Reporting service riêng với API DTO.
- Async export với snapshot và object storage.

Không phải bài toán nào cũng cần data warehouse; chọn dựa trên SLA, volume, complexity và chi phí vận hành.

### 38.3. Giữ một nguồn dữ liệu đáng tin

Dù có OLAP read model, cần xác định source of truth và reconciliation path. Projection/aggregate query chỉ là **cách nhìn dữ liệu**, không thay transaction business rules.

## 39. Security, tenant scope và dữ liệu tổng hợp

Báo cáo có thể lộ thông tin nhạy cảm ngay cả khi chỉ có counts:

```text
Số đơn của một khách hàng đặc biệt
Doanh thu của một tổ chức khác
Số nhân viên thuộc bộ phận nhỏ
Tần suất giao dịch theo giờ
```

### 39.1. Tenant scoping

Áp `tenant_id` ở **source rows** trước aggregation. Một query không có tenant filter có thể trả tổng doanh thu cross-tenant dù không lộ từng order.

### 39.2. Không tin tenant ID từ client

Client gửi `tenant=A` không chứng minh có quyền xem A. Reporting service phải lấy authorized scope từ security principal/permissions và xác minh requested filters.

### 39.3. Joined tables

Nếu bảng customer/order/item có tenant IDs, review join predicates để không vô tình join cross-tenant rows khi IDs không global unique. Composite keys/tenant scoping cần được bảo toàn trong SQL.

### 39.4. Data suppression

Trong một số report, group có một người/khách duy nhất có thể tiết lộ dữ liệu cá nhân. Có thể cần minimum group size, suppression, permission-based fields hoặc delayed aggregation theo privacy/compliance policy.

### 39.5. Native SQL và ORM-level filters

Một số Hibernate filters, `@Where`/`@SQLRestriction` hoặc soft-delete/tenant mechanisms là provider-specific và có thể **không tự áp dụng** với native SQL tùy cấu hình. Đối chiếu every native report query với authorization, tenant isolation và soft delete semantics.

### 39.6. SQL injection

Bind filter values, allowlist dimension names/aggregates/order fields, giới hạn report query complexity và audit quyền truy cập. Projection không làm SQL injection biến mất.

### 39.7. Logging

Không log nguyên report rows chứa PII/financials; dùng traceId, tenant scope đã được phép, report definition ID, query duration, row counts và safe diagnostic metadata.

## 40. Kiểm thử báo cáo: kiểm tra số đúng trước khi đo nhanh

Một report có thể trả dưới 100ms nhưng sai doanh thu do join hoặc status filter. Test cần bảo vệ **metric semantics** độc lập với performance.

### 40.1. Chọn fixture nhỏ có đủ edge cases

Ví dụ:

```text
Tenant A:
    Customer X:
        Order 1 PAID, 100 VND, items=3
        Order 2 PAID, 200 VND, items=1
        Order 3 CANCELLED, 900 VND, items=2
    Customer Y:
        Order 4 PAID, 100 VND, items=0
    Customer Z:
        no orders

Tenant B:
    Customer Q:
        Order 5 PAID, 999 VND
```

Với paid-only tenant A:

```text
Revenue = 400 VND
Paid orders = 3
Distinct paying customers = 2
Customer X revenue = 300 VND
Customer Y revenue = 100 VND
Customer Z paid orders = 0 (nếu report bắt đầu từ Customer + LEFT JOIN)
Tenant B's 999 VND must not leak into A's report
```

Fixture tạo ít rows nhưng bao trùm:

- One-to-many fanout.
- Status exclusion.
- Same amount across distinct orders.
- Customer without orders.
- Tenant isolation.

Nếu viết test chỉ với mỗi order một item và không có same amounts, một query sai `SUM(DISTINCT amount)` vẫn có thể pass.

### 40.2. Test DTO projection field mapping

Ví dụ skeleton:

```java
@Test
void projectionContainsOnlyExpectedFields() {
    List<OrderListRow> rows =
        reportingService.listOrders("TENANT_A", 50);

    assertFalse(rows.isEmpty());
    OrderListRow row = rows.get(0);
    assertNotNull(row.id());
    assertNotNull(row.code());
    assertNotNull(row.totalAmount());
}
```

Điểm quan trọng không chỉ tồn tại fields mà còn đúng **order và type** của constructor; việc đổi JPQL SELECT argument order có thể âm thầm làm DTO sai nếu hai arguments cùng Java type.

### 40.3. Test aggregate values

```java
@Test
void customerRevenueHasCorrectOrderGrain() {
    Map<Long, CustomerRevenueRow> byId =
        reportingService.revenueByCustomer("TENANT_A")
            .stream()
            .collect(Collectors.toMap(
                CustomerRevenueRow::customerId,
                Function.identity()));

    assertEquals(
        new BigDecimal("300"),
        byId.get(customerXId).revenue());
    assertEquals(
        2L,
        byId.get(customerXId).orderCount());
}
```

Đây là test skeleton: `reportingService`, fixture IDs và imports do ứng dụng cung cấp. Query cần bảo đảm một currency/grain đã định nghĩa; với `BigDecimal`, test có thể dùng `compareTo` nếu scale không phải một phần của output contract.

### 40.4. Test duplicate join rows

Tạo một order với 3 items, amount=100; một order với 1 item, amount=200. Assert report order revenue là 300, không phải 500; đồng thời distinct order count=2, item row count=4.

### 40.5. Test no-data

Chọn date range không có orders:

- `COUNT` returns 0.
- `SUM` returns null hoặc application-defined zero.
- Grouped query returns empty list.
- Daily chart fills missing days nếu contract yêu cầu.

Không để NullPointerException chỉ vì một tenant mới tạo chưa có đơn.

### 40.6. Test DATE boundary

Tạo orders tại:

```text
2026-10-01T16:59:59.999Z
2026-10-01T17:00:00.000Z
```

Với Asia/Ho_Chi_Minh, chúng thuộc hai local calendar dates khác nhau. Test mapping theo `[from,to)` và conversion/aggregation; tránh dùng timezone mặc định của test runner.

### 40.7. Test tiền và currency

Tạo 100 VND và 10 USD; assert không có query nào trả 110 với nhãn revenue chung nếu chưa có conversion policy. Kiểm tra reporting DTO có currency dimension hoặc conversion snapshot.

### 40.8. Test HAVING/pagination counts

Tạo customers có 0/1/5/10 PAID orders. Với `HAVING COUNT >= 5`, group count phải là 2, không phải số paid orders cộng lại. Assert totalGroups và content page size phản ánh đúng filters/HAVING.

### 40.9. Test status transitions và refunds

Nếu order đổi PAID → REFUNDED, revenue report phải theo explicit domain policy. Với payment ledger, test partial refunds; không suy ra mọi refund luôn đảo toàn bộ order amount.

### 40.10. Test consistency giữa report cards

Nếu dashboard có total revenue và daily revenues, assert:

```text
SUM(daily revenue over selected days)
    == total revenue
```

trong cùng snapshot và cùng timezone/currency/status scope. Nếu dữ liệu có late arrivals hoặc asynchronous summary, test cần biết expected lag/cutoff.

### 40.11. Test privacy/tenant scope

Tạo tenant B có revenue lớn và những tên khách trùng với tenant A. Assert cả DTO projection và native SQL reports chỉ trả dữ liệu authorized tenant. Không chỉ kiểm tra controllers; trực tiếp test reporting repository/service khi cần.

### 40.12. Integration test với RDBMS mục tiêu

Test H2 hay mock `EntityManager` có thể không mô phỏng:

- Native functions, timezone conversions.
- Window/CTE semantics.
- Numeric `SUM`/`AVG` result types.
- Index/query plan behavior.
- Partial unique indexes.
- PostgreSQL `generate_series`/collation.

Nếu production dùng PostgreSQL, kiểm thử SQL analytics quan trọng trên PostgreSQL thật hoặc testcontainer với migrations thực.

## 41. Performance tests: tách chi phí DB và Java

Một bài benchmark có ích phải trả lời “thắt cổ chai ở đâu?”.

### 41.1. Thu thập phép đo

| Metric | Ý nghĩa |
|---|---|
| Query execution time | Chi phí DB SQL |
| Rows scanned/rows returned | Data reduction hiệu quả không |
| Sort/hash aggregate spill | Memory/disk pressure |
| Network bytes | Dữ liệu chuyển từ DB sang app |
| JPA hydration time | Chi phí tạo entity/DTO |
| Heap/GC pressure | Memory từ object materialization |
| Connection wait time | Pool saturation |
| p50/p95/p99 endpoint latency | Trải nghiệm thực tế |
| Concurrent requests/sec | Khả năng chịu tải dashboard |
| Index maintenance overhead | Tác động đến ghi OLTP |

### 41.2. So sánh hai phương án đúng nghĩa

Để so entity vs DTO:

1. Dùng cùng tenant/date/status filters.
2. Trả cùng business fields cho UI.
3. Dùng dataset đại diện.
4. Warmup đủ để tránh kết luận do cold start.
5. Quan sát SQL/N+1 trước khi quy hiệu năng cho projection.
6. Đo memory và network bytes ngoài response latency.

### 41.3. Không benchmark query sai

Một query `SUM(DISTINCT totalAmount)` có thể nhanh hơn query đúng nhưng business result sai. Correctness fixture phải pass trước khi so tốc độ.

### 41.4. Count query có thể là nút thắt

Một grouped result page 20 rows có thể trả nhanh nhưng count distinct toàn bộ 10 triệu customers chậm. Nếu UI không cần tổng số trang, dùng Slice/load-more hoặc snapshot-based pagination.

### 41.5. Test data distribution

Đừng đo với 10.000 orders evenly distributed nếu production có một tenant với 90% data, status skew và thời gian cao điểm. Index optimization cần hiểu distributions.

## 42. Những anti-pattern phổ biến

### 42.1. `findAll()` rồi stream để tính SUM

Database có thể tổng hợp hiệu quả hơn rất nhiều; Java chỉ cần nhận một aggregate row.

### 42.2. Dùng entity để trả dashboard cards

Hydrate managed entities, dirty-checking và lazy loads trong khi chỉ cần vài numbers. Dùng scalar/DTO/report query.

### 42.3. Trả `Object[]` xuyên nhiều tầng ứng dụng

Cast theo index dễ sai khi thêm field hoặc thay SELECT order. DTO/record có contract ổn định hơn.

### 42.4. Dùng interface projection và giả định chắc chắn chỉ chọn một số cột

Nested properties và open SpEL projections có thể kéo thêm associations/full entity loading. Kiểm tra generated SQL và Spring Data version.

### 42.5. Dùng `JOIN FETCH` để “tối ưu aggregate”

Fetch join phục vụ entity graph, không phải công thức tổng hợp. Nó có thể nhân rows và phá pagination.

### 42.6. Sum order amount sau join order items

Nhân order total theo số items, báo doanh thu cao giả.

### 42.7. `SUM(DISTINCT amount)` để “sửa” duplicated join rows

Nếu hai orders thật cùng amount, nó gộp mất một order. Cần sửa grain/join.

### 42.8. `COUNT(o)` sau to-many join để đếm orders

Đếm joined rows. Sử dụng `COUNT(DISTINCT o.id)` cho distinct order IDs hoặc loại join không cần thiết.

### 42.9. `COUNT(*)` trên LEFT JOIN khi muốn đếm children

Parent có 0 children vẫn có một null-extended row, `COUNT(*)` = 1. Dùng `COUNT(child.id)`.

### 42.10. Đặt filter của left-joined child ở WHERE

Có thể làm mất parent không có matching children. Cân nhắc `ON` với scope/tenant filter đúng.

### 42.11. Group theo display name

Hai customers trùng tên bị merge. Group theo stable identifier và các attributes hiển thị cần thiết.

### 42.12. Lấy column không aggregate từ một grouped row tùy ý

Ví dụ chọn `order_code` trong `GROUP BY customer_id` khi khách có nhiều orders. Metric “mã đơn mới nhất” cần query có nghĩa chính xác.

### 42.13. Group theo UTC date nhưng UI hiển thị local date

Orders gần nửa đêm bị xếp sai ngày nghiệp vụ. Phải định nghĩa timezone/calendar và dùng nửa mở boundaries.

### 42.14. Không điền ngày không có giao dịch

Chart có thể bỏ ngày zero và moving average tính theo 7 rows thay vì 7 calendar days.

### 42.15. Cộng tiền khác currency

`SUM(amount)` không có nghĩa nếu units khác nhau. Filter/group/convert theo rate policy.

### 42.16. Dùng giá product hiện tại cho doanh thu quá khứ

Historical revenue nên dùng captured order/item amount hoặc ledger, không join current price.

### 42.17. Count groups bằng count source rows

`GROUP BY customerId` trả số customers; `COUNT(order)` là số orders. `Page` total có thể sai hoàn toàn.

### 42.18. `HAVING` report nhưng countQuery bỏ qua HAVING

Total pages không khớp content. Cần count grouped results sau HAVING hoặc dùng khác pagination contract.

### 42.19. Không có stable tie-breaker

Hai groups cùng revenue có thể đổi thứ tự giữa pages. Thêm stable identifier vào ORDER BY.

### 42.20. Dùng OFFSET lớn rồi ngạc nhiên vì query chậm

DB có thể vẫn tính/sắp xếp và bỏ rất nhiều rows/groups. Cân nhắc keyset/snapshot/async export.

### 42.21. Ghép raw user input vào native SQL

Nguy cơ SQL injection và tùy ý chạy queries nặng. Bind values, allowlist dimensions/sorts.

### 42.22. Bật cache mà không có tenant trong key

Nguy cơ cross-tenant data leak. Cache key phải chứa toàn bộ data scope và metric dimensions.

### 42.23. Coi read replica là dữ liệu realtime tuyệt đối

Replica lag làm số liệu trễ. Xác định freshness SLA và hiển thị as-of timestamp có nguồn.

### 42.24. Coi materialized view luôn cập nhật sau một transaction

Snapshot refresh/CDC pipeline có thể trễ. Xây watermark/reconciliation.

### 42.25. Dùng `getResultStream` rồi giả định bounded memory

Provider/driver có thể materialize all rows; kiểm tra cursor/fetch size/transaction lifecycle hoặc dùng batch export.

### 42.26. Dùng index để giải quyết tất cả

Index không sửa wrong joins, wrong grain, N+1, large JSON output, missing WHERE, bad aggregate semantics hay lack of snapshots.

### 42.27. Không kiểm tra generated SQL

JPQL/Criteria/Spring projections có thể tạo joins/casts khác dự kiến. Xem SQL thực tế và execution plan trên DB mục tiêu.

### 42.28. Chỉ test happy path mỗi order một item

Không phát hiện multiplication. Test nhiều items, nhiều payment attempts, same amounts, no orders, mixed currencies.

### 42.29. Dùng `AVG` Double cho yêu cầu tiền chính xác mà không rounding policy

Định nghĩa decimal computation khi metric là money; cân nhắc sum/count với BigDecimal.

### 42.30. Bỏ qua transaction snapshot khi tính nhiều cards

Hai queries có thể đọc data ở hai thời điểm khác nhau và tạo dashboard internal inconsistency. Chọn consistency contract.

### 42.31. Không xét dữ liệu về muộn/hoàn tiền

Một báo cáo cuối ngày có thể thay đổi sau khi giao dịch được điều chỉnh. Cần định nghĩa cutoff, restatement policy và reconciliation.

### 42.32. Chạy báo cáo dài trực tiếp trên OLTP primary giờ cao điểm

Có thể làm chậm ghi, giữ connection và gây resource contention. Giới hạn query, async jobs/read replica/read model phù hợp.

### 42.33. Trả metric nhạy cảm chỉ vì đã GROUP BY

Aggregated data có thể vẫn reveal thông tin khách/tenant. Authorization/row-level scope và privacy rules vẫn bắt buộc.

## 43. Bài tập thực hành

### Bài 1 — Chọn kỹ thuật projection

Cho bốn chức năng:

1. Đổi trạng thái đơn hàng.
2. Danh sách 50 orders gồm ID, code, customer name, amount.
3. Đếm orders PAID trong tháng.
4. Doanh thu theo customer.

**Yêu cầu:** chọn entity, DTO, scalar, aggregate hoặc native query phù hợp từng trường hợp; nêu vì sao không nên dùng `findAll()` cho tất cả.

### Bài 2 — Scalar `COUNT`

Viết JPQL đếm số `SalesOrder` của authorized tenant với status PAID trong `[from,to)`. Xác định kiểu `getSingleResult()` và kết quả khi không có đơn.

### Bài 3 — `SUM` và NULL

Viết JPQL `SUM(o.totalAmount)` cho một currency/status. Giải thích vì sao không có orders thì kết quả có thể NULL; chọn dùng `COALESCE` hay application default theo metric contract.

### Bài 4 — DTO record

Tạo `OrderListRow(id,orderCode,customerName,totalAmount,currencyCode,createdAt)` và JPQL constructor expression. Không tải managed `SalesOrder` khi UI chỉ hiển thị những fields này.

### Bài 5 — `Object[]` vs `Tuple`

Viết một status-count query trả `Object[]` và phiên bản `Tuple` có aliases. So sánh khả năng refactor và lý do DTO thích hợp hơn cho public API.

### Bài 6 — Spring Data interface projection

Tạo interface `OrderSummaryView` với getters cho `id`, `orderCode` và `totalAmount`. Viết repository method; giải thích vì sao cần kiểm tra generated SQL nếu projection chứa nested customer.

### Bài 7 — GROUP BY theo customer

Viết query trả `CustomerRevenueRow` có `customer.id`, `displayName`, `count`, `sum`. Nếu hai customers có cùng display name, kết quả phải có hai groups độc lập.

### Bài 8 — HAVING

Chỉ lấy customers có ít nhất 5 orders PAID. Đặt điều kiện status và date ở WHERE, điều kiện count ở HAVING, và sắp xếp theo revenue giảm dần.

### Bài 9 — Top-N

Lấy top 10 customers theo doanh thu trong một tenant. Thêm `customerId` tie-breaker để ổn định sort; giới hạn kết quả. Nêu vì sao OFFSET lớn có thể đắt.

### Bài 10 — Conditional aggregation

Viết query trả một row theo tenant gồm total, paid, shipped, canceled counts bằng `CASE WHEN`. Xử lý khi tenant chưa có orders (không có group row).

### Bài 11 — Lỗi đếm trùng sau join

Có hai orders: Order A có 3 items, Order B có 1 item. Viết query:

```java
select count(o) from SalesOrder o join o.items i
```

Giải thích vì sao count có thể là 4 thay vì 2. Viết hai cách đếm orders đúng: bỏ join nếu không cần và `count(distinct o.id)` nếu cần join filter.

### Bài 12 — Lỗi tổng doanh thu sau join

Order A amount 100 có 3 items; Order B amount 200 có 1 item. Tính kết quả của:

```sql
SELECT SUM(o.total_amount)
FROM sales_orders o
JOIN order_items i ON i.order_id = o.id;
```

Sửa SQL để trả 300. Chứng minh vì sao `SUM(DISTINCT o.total_amount)` không an toàn nếu có hai orders khác nhau amount 100.

### Bài 13 — Join hai collections

Một order có 4 items và 3 payment attempts. Query join cả hai collections tạo bao nhiêu rows? Tại sao `SUM(quantity)` và `SUM(payment_amount)` bị nhân? Thiết kế pre-aggregation CTE theo order_id.

### Bài 14 — `EXISTS` thay join

Viết JPQL tính doanh thu của orders **có ít nhất một item SKU X** mà không làm nhân `totalAmount` nếu order có nhiều items SKU X.

### Bài 15 — LEFT JOIN zero-count

Báo cáo liệt kê cả customers không có orders. So sánh `COUNT(*)` với `COUNT(o.id)` sau LEFT JOIN. Giải thích vì sao filter status ở WHERE có thể khiến customer zero-orders biến mất.

### Bài 16 — Group by stable key

Hai customers cùng tên “Nguyễn Văn A” nhưng IDs khác nhau. Viết grouped query bảo đảm hai khách không bị nhập thành một row.

### Bài 17 — Group by ngày địa phương

Cho `2026-10-01T18:30:00Z` và timezone Asia/Ho_Chi_Minh. Xác định local date. Viết Java tạo `[from,to)` instants cho ngày 02/10 và SQL PostgreSQL group theo local date.

### Bài 18 — Ngày không có data

Report một tuần chỉ có orders vào thứ Hai, Tư, Sáu. Tạo output đủ bảy ngày bằng date dimension hoặc generate_series/zero filling. Giải thích khác biệt giữa zero và unknown.

### Bài 19 — AOV và BigDecimal

`SUM` paid amount là 1001.00 và order count là 3. Tính average với `BigDecimal.divide(..., scale=2, roundingMode=...)`. Nêu vì sao `AVG` Double có thể không phù hợp với financial accuracy policy.

### Bài 20 — Mixed currencies

Có VND, USD và EUR orders. Viết JPQL `GROUP BY currencyCode`; định nghĩa thêm dữ liệu cần có để tổng hợp tất cả về VND một cách auditable.

### Bài 21 — Refund semantics

Order PAID 1.000.000 VND được refund 300.000 VND. Định nghĩa gross revenue, net revenue và nguồn dữ liệu cần dùng; giải thích vì sao chỉ group theo status có thể không đủ.

### Bài 22 — Total groups vs total orders

Một grouped query trả doanh thu theo customer, có 20.000 orders nhưng 700 customers. Dùng count query nào cho số trang? Thêm HAVING `SUM > threshold` và giải thích vì sao `count(distinct customerId)` đơn giản không còn đúng.

### Bài 23 — Criteria API

Viết Criteria query dùng `cb.construct(CustomerTotal.class, customerId, cb.sum(amount))`, thêm tenant/status predicates và `groupBy`. Sau đó thêm optional date range filter chỉ khi parameter được cung cấp.

### Bài 24 — Native CTE

Một report cần order revenue, item quantity và payment amount. Viết CTE tổng hợp items/payments về một row/order rồi join kết quả mà không làm nhân số đo.

### Bài 25 — Window function ranking

Viết native SQL top 3 customers mỗi tenant bằng `ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY revenue DESC, customer_id)`. Nếu business muốn giữ mọi ties, so sánh `RANK`/`DENSE_RANK`.

### Bài 26 — Running 7-day average

Report daily revenue thiếu ngày không có orders. Đặt một moving window `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW`. Vì sao phép tính này không phải 7 calendar days nếu thiếu buckets? Thiết kế calendar series.

### Bài 27 — Keyset paging

Danh sách orders sort `createdAt DESC,id DESC`. Viết seek predicate cho page tiếp theo; nêu index candidate và cách bảo vệ cursor khỏi cross-tenant access.

### Bài 28 — DTO vs entity benchmark

So sánh report list 50.000 orders dùng entities và DTO records. Thu thập SQL selected columns, network bytes, hydration time, memory allocation và end-to-end p95 latency. Đừng kết luận chỉ dựa trên thời gian của một request.

### Bài 29 — EXPLAIN

Query tổng hợp theo customer đang dùng full table scan trên 10 triệu rows. Thiết kế thử nghiệm với tenant/status/date index, đọc `HashAggregate`/`Sort`/buffer metrics và quyết định có nên tạo index.

### Bài 30 — Materialized view

Dashboard có 10.000 users refresh doanh thu ngày mỗi phút. So sánh direct GROUP BY, cache TTL, read replica, materialized view và daily summary table. Thiết kế freshness SLA và reconciliation.

### Bài 31 — Partial success trong pipeline

Một CDC job cập nhật daily summary nhưng nhận cùng event hai lần. Thiết kế event-id idempotency và cách rebuild summary từ source of truth.

### Bài 32 — Read replica

User vừa thanh toán xong nhưng dashboard không tăng doanh thu trong 3 giây. Giải thích replica lag và đưa ra hai UX/consistency designs: read-your-writes và eventual reporting.

### Bài 33 — CSV export

Export 5 triệu rows. So sánh `getResultStream()`, cursor/fetch-size có kiểm chứng, keyset batches và async job. Xem xét connection lifetime, memory và retries.

### Bài 34 — Native SQL an toàn

User được chọn sort theo revenue, orderCount hoặc customerName. Viết allowlist mapping sang SQL fragments, bind tenant/date filters bằng parameters. Nêu nguy cơ raw sort string.

### Bài 35 — Tenant isolation

Tạo fixtures tenant A/B với cùng customer display names. Viết integration test chứng minh grouped report và native SQL chỉ trả rows trong authorized tenant.

### Bài 36 — Cache key

Report có dimensions tenant, currency, timezone, date range, status filter và definition version. Thiết kế cache key; giải thích hậu quả khi bỏ tenant hoặc currency.

### Bài 37 — Báo cáo tái lập

Một báo cáo tháng phải có thể xuất lại sau 6 tháng với cùng số liệu dù có late refunds/updates. Đề xuất snapshot cutoff, reporting version, immutable ledger hoặc report-run storage phù hợp.

### Bài 38 — Test fan-out và same amounts

Tạo hai orders cùng amount 100, mỗi order 2 items. Viết test phát hiện cả hai lỗi `SUM(o.amount)` sau join và `SUM(DISTINCT o.amount)`.

### Bài 39 — Test đối chiếu tổng và breakdown

Tạo fixtures rồi so `total revenue` với tổng của `revenue by customer` và `revenue by day` trong cùng snapshot/filter/currency. Giải thích vì sao số liệu có thể lệch khi report cards được chạy ở hai thời điểm.

### Bài 40 — Thiết kế report service hoàn chỉnh

Xây một thiết kế cho dashboard gồm:

- Tổng paid orders và revenue trong tháng.
- Breakdown theo currency và customer.
- Top 10 products theo quantity.
- Daily revenue đủ ngày.
- Tải CSV chi tiết.

Với từng nhu cầu, chọn entity/DTO/aggregate/native/summary, query grain, filters, index candidates, pagination, cache/freshness, authorization và integration tests.

## 44. Câu hỏi tự kiểm tra

**1. Projection là gì?**

Là cách chọn trường/biểu thức và kiểu kết quả của query, thay vì mặc định trả managed entity đầy đủ.

**2. Aggregation là gì?**

Là tính toán trên một tập rows hoặc mỗi group, ví dụ COUNT/SUM/AVG.

**3. Entity projection phù hợp nhất cho việc nào?**

Các command cần managed entity state, lifecycle và dirty checking.

**4. DTO projection có đưa result vào persistence context như managed entity không?**

Không; DTO/record không tự là managed JPA entity.

**5. `Object[]` có điểm yếu gì?**

Mapping theo index/casts, dễ sai khi query SELECT order thay đổi.

**6. `Tuple` tốt hơn `Object[]` ở điểm nào?**

Có thể truy cập alias và typed values thay vì chỉ numeric indices.

**7. JPQL constructor expression dùng cú pháp nào?**

`select new full.package.Dto(args...)` với constructor phù hợp.

**8. Java record có dùng làm JPQL DTO không?**

Có, nếu canonical constructor và selected argument types/order phù hợp provider/JPA query.

**9. Spring interface-based projection có phải JPA chuẩn không?**

Không, là tính năng Spring Data JPA.

**10. Interface nested projection có luôn chỉ fetch đúng hai columns không?**

Không; joins/nested attributes có thể làm nhiều dữ liệu hơn được đọc.

**11. Muốn đếm orders có nên dùng `findAll().size()` không?**

Không với tập lớn; dùng `COUNT` query.

**12. Kiểu JPQL `COUNT` là gì?**

`Long`.

**13. `SUM(BigDecimal)` thường trả gì theo JPQL?**

`BigDecimal`.

**14. `AVG` trong JPQL thường trả gì?**

`Double`, nên cân nhắc độ chính xác khi tính tiền.

**15. `SUM` không có input rows trả gì?**

NULL trong aggregate không nhóm; có thể dùng COALESCE/app fallback theo contract.

**16. `COUNT` không có input rows trả gì?**

`0L` nếu là aggregate không GROUP BY.

**17. Grouped query không có matches trả gì?**

Thông thường danh sách groups rỗng, không phải một row default.

**18. `COUNT(*)` và `COUNT(optionalColumn)` có giống nhau không?**

Không; COUNT(column) bỏ NULL values.

**19. Tại sao GROUP BY customerName có thể sai?**

Hai customers khác nhau có thể trùng display name; cần stable ID.

**20. `HAVING` khác `WHERE` thế nào?**

WHERE lọc rows trước grouping; HAVING lọc groups sau aggregate.

**21. Muốn khách có ít nhất 5 đơn đặt điều kiện ở đâu?**

`HAVING COUNT(order) >= 5`.

**22. `GROUP BY` có tự sắp kết quả không?**

Không; cần ORDER BY.

**23. `CASE WHEN` dùng để làm gì trong aggregate?**

Đếm/tính có điều kiện các nhóm trạng thái trong cùng query.

**24. Vì sao SUM order total sau join items có thể sai?**

Order-level amount lặp lại theo số item rows.

**25. `SUM(DISTINCT amount)` có giải quyết đúng không?**

Không; hai orders khác nhau cùng amount sẽ bị gộp mất.

**26. Muốn đếm distinct orders sau join dùng gì?**

`COUNT(DISTINCT order.id)` hoặc bỏ join nếu không cần.

**27. `COUNT(items)` có phải tổng số lượng sản phẩm không?**

Không; nó đếm item rows. Muốn số đơn vị bán thường dùng `SUM(quantity)`.

**28. Join hai to-many collections có vấn đề gì?**

Có thể tạo phép nhân số lượng rows (fan-out) và làm tổng hợp sai.

**29. Khi nào `EXISTS` hữu ích?**

Khi chỉ cần kiểm tra có related rows mà không muốn nhân parent rows qua join.

**30. Khi nào pre-aggregation CTE hữu ích?**

Khi cần tổng hợp nhiều child sources về cùng parent grain trước khi join.

**31. LEFT JOIN khách không có order, dùng `COUNT(*)` hay `COUNT(o.id)`?**

`COUNT(o.id)` để trả 0 cho khách không có matched orders.

**32. Vì sao WHERE trên left-joined child có thể mất các parent rows?**

Nó loại null-extended rows, làm LEFT JOIN hoạt động như INNER JOIN với filter đó.

**33. Đếm total pages của grouped report bằng count orders có đúng không?**

Không; cần count groups sau filters/HAVING.

**34. `COUNT(DISTINCT customerId)` có luôn đủ khi query có HAVING không?**

Không; nó không tự áp HAVING aggregate predicate lên groups.

**35. Stable pagination cần gì?**

ORDER BY với tie-breaker xác định và consistency/snapshot policy phù hợp.

**36. Keyset giúp gì?**

Giảm chi phí bỏ qua OFFSET lớn cho những queries có ordering và seek predicates phù hợp.

**37. Keyset trên top revenue realtime có khó khăn gì?**

Aggregate sort key có thể đổi giữa pages; cần snapshot/read model nếu muốn ổn định.

**38. Báo cáo theo ngày dùng UTC hay tenant local time?**

Phải định nghĩa theo business contract; không tự chọn UTC nếu UI kỳ vọng local date.

**39. Vì sao `[from,to)` thường tốt hơn inclusive end-of-day?**

Tránh lỗi precision/ranh giới và dễ ghép khoảng liên tiếp.

**40. `GROUP BY date` có tạo ngày zero revenue không?**

Không; cần calendar/date series hoặc application zero-fill.

**41. Có được cộng 100 USD và 200 VND trực tiếp không?**

Không, trừ khi đã quy đổi theo tỷ giá/policy xác định.

**42. Tại sao current product price không dùng để tính historical revenue?**

Vì giá thay đổi; phải dùng captured order/item price hoặc immutable ledger.

**43. Native SQL có luôn nhanh hơn JPQL không?**

Không; phải so generated SQL và execution plans.

**44. Khi nào nên dùng native SQL?**

Khi cần CTE/window/time bucket/DB-specific analytic features hoặc query plan control vượt portable JPQL.

**45. `@SqlResultSetMapping` dùng để làm gì?**

Định nghĩa cách map native query result columns sang objects/constructors/entities theo JPA.

**46. Window `ROW_NUMBER` khác `DENSE_RANK` thế nào?**

ROW_NUMBER gán vị trí riêng; DENSE_RANK giữ ties cùng rank và không nhảy số.

**47. `ROWS 6 PRECEDING` có luôn là 7 calendar days không?**

Không nếu daily series thiếu zero days; đó là 7 rows gần nhất.

**48. Criteria `cb.construct` tạo ra gì?**

DTO constructor projection.

**49. Criteria API có tự tránh join multiplication không?**

Không. Vẫn phải thiết kế grain/join đúng.

**50. `getResultStream` có bảo đảm server-side cursor không?**

Không; cần kiểm tra provider/driver/fetch size.

**51. Có index nghĩa là optimizer chắc chắn dùng không?**

Không; planner quyết định dựa trên cost/statistics.

**52. Covering index có miễn phí không?**

Không, tăng storage và write maintenance.

**53. Report trên read replica có luôn realtime không?**

Không, có replication lag.

**54. Cache key báo cáo bắt buộc chứa gì?**

Các dimensions/filter/security scope như tenant, currency, timezone, range, version theo contract.

**55. Materialized view có luôn thấy update mới không?**

Không; phụ thuộc refresh/incremental pipeline.

**56. Daily summary table cần gì để đáng tin?**

Grain rõ, update logic, idempotency, watermark và reconciliation.

**57. Vì sao dashboard hai cards có thể lệch nhau?**

Khác filters, snapshot times, currency/timezone, cache freshness hoặc query logic.

**58. Báo cáo có cần authorization không nếu chỉ trả tổng số?**

Có. Aggregated metrics vẫn có thể nhạy cảm.

**59. Muốn chứng minh query report đúng cần test gì?**

Known fixtures, expected aggregates, edge cases join fan-out, no-data, currencies, tenant scope và time boundaries.

**60. Muốn chứng minh query report nhanh cần kiểm tra gì?**

Generated SQL, EXPLAIN/ANALYZE, representative data, p95 latency, memory/network, concurrency và index costs.

## 45. Bảng quyết định: chọn kỹ thuật theo bài toán

| Bài toán | Kỹ thuật xuất phát | Khi cần chuyển hướng |
|---|---|---|
| Đổi trạng thái một đơn | Load managed entity | Fetch plan/batch association khi cần |
| List 50 orders | JPQL DTO/record projection | Keyset khi OFFSET sâu, read model nếu UI nhiều dimensions |
| Đếm đơn theo tenant/status | Scalar COUNT | Cached summary nếu gọi dày và source cực lớn |
| Tổng tiền một currency | Scalar SUM + NULL handling | Ledger/summary nếu financial semantics phức tạp |
| Count theo status | GROUP BY + DTO/record | Conditional aggregate nếu cần một row nhiều trạng thái |
| Doanh thu theo khách | JOIN many-to-one + GROUP BY stable ID | Native CTE nếu thêm các child metrics khác grain |
| Có khách không có đơn | Customer root + LEFT JOIN | Calendar/dimension table khi thiếu master rows |
| Đếm unique orders sau join items | COUNT(DISTINCT order.id) hoặc EXISTS | Bỏ join nếu có thể |
| Tổng tiền order sau join items | Tổng hợp từ Orders trước | Pre-aggregate hoặc EXISTS, không SUM(DISTINCT amount) |
| Top products theo units | SUM(item.quantity) GROUP BY SKU | Snapshot product name/UOM; native/summary theo scale |
| Doanh thu theo ngày local | Timezone-safe date bucket + nửa mở boundaries | Calendar table, native SQL, summary table |
| Top 3 mỗi tenant | Native CTE + ROW_NUMBER | Summary/warehouse nếu data lớn |
| Rolling average | Daily series + window function | Precomputed time-series |
| Báo cáo có filters động | Criteria/typed query builder | Query DSL/report definition engine có allowlists |
| Grouped report có pagination | DTO + count groups đúng | Slice/keyset/snapshot nếu count đắt |
| Xuất 5 triệu rows | Keyset batches hoặc verified cursor stream | Async job + object storage |
| Dashboard refresh dày | Cache với tenant/freshness scope | Materialized view/summary/OLAP |
| Báo cáo kế toán audit | Ledger + snapshot/report version | Dedicated reconciled analytical pipeline |

### 45.1. Quy tắc chọn bắt đầu đơn giản

Không cần mở đầu bằng warehouse, event pipeline và một hệ thống tổng hợp riêng cho báo cáo có 2.000 orders. Có thể bắt đầu bằng JPQL DTO và một index phù hợp. Khi volume, traffic hoặc metric complexity tăng, đo rồi nâng cấp kiến trúc.

### 45.2. Không bắt đầu bằng kỹ thuật trước định nghĩa metric

Nếu “doanh thu” chưa rõ có tính refunded orders không, dù JPQL hay CTE/window/materialized view đều có thể trả số sai. Business metric definition phải được viết rõ và thống nhất với owners.

### 45.3. Không dùng một data model cho mọi use case

Command model phục vụ invariants và transactions. Reporting read model phục vụ dimensions, aggregates và latency. Hai mô hình có thể dùng chung DB/JPA ban đầu; khi cần, có thể tách read model mà không ép entities thành DTO reports.

## 46. Checklist xây truy vấn báo cáo an toàn, chính xác và nhanh

### 46.1. Metric definition

1. **Mục đích:** màn hình đang cần metric hay details?
2. **Grain:** mỗi source row là order, item, payment, customer hay ngày?
3. **Danh sách dimensions:** tenant, customer, date bucket, status, currency, product, channel.
4. **Measure:** count orders, sum amount, sum quantity, average, distinct customers?
5. **Status policy:** paid, shipped, canceled, refunded được tính thế nào?
6. **Money policy:** currency grouping, FX rates, rounding, taxes, discounts và refunds?
7. **Time policy:** timezone, UTC boundaries, fiscal calendar và late data?
8. **Freshness:** realtime, eventual, daily cutoff hay audited snapshot?
9. **Data scope:** user/tenant authorization và minimum group-size privacy requirements?

### 46.2. Projection design

10. Report có thực sự cần managed entities không?
11. Nếu chỉ hiển thị vài fields, đã chọn DTO/record/interface/scalar projection phù hợp?
12. Constructor expression arguments có đúng thứ tự/types?
13. Numeric `COUNT`/`SUM`/`AVG` types và NULL cases được xử lý?
14. API DTO có tránh lộ persistence `Tuple`/`Object[]`/lazy proxies?
15. Nested projections có gây joins/phát sinh loading không?
16. Nếu dynamic fields, aliases/types có stable contract không?

### 46.3. Query semantics

17. WHERE lọc đúng tenant/status/currency/date trước aggregation?
18. GROUP BY dùng stable identity, không chỉ display name?
19. HAVING áp sau aggregate đúng định nghĩa?
20. Mọi non-aggregate selected expressions có hợp lệ trong GROUP BY?
21. JOIN cardinality có nhân metric source rows?
22. Nếu count orders qua items, có dùng DISTINCT ID/EXISTS?
23. Nếu SUM order total, đã tránh to-many join duplication?
24. LEFT JOIN có giữ zero-data groups khi cần, và filter nằm đúng ON/WHERE?
25. No-data: scalar NULL/zero và group empty list có đúng API contract?
26. Có ORDER BY và stable tie-breaker trước pagination?
27. Total groups/countQuery có cùng filters và HAVING không?
28. Date series đủ ngày hay thiếu zero buckets?
29. Currency/units có đồng nhất trước phép cộng?
30. Source số liệu lịch sử có immutable captured values hay không?

### 46.4. Performance

31. Query đã chọn ít columns/rows nhất phù hợp?
32. SQL generated bởi JPQL/Criteria/Spring Data đã được xem?
33. Có N+1 hoặc join fetch không cần thiết không?
34. Index candidates có phù hợp WHERE/JOIN/ORDER BY thực tế?
35. EXPLAIN/ANALYZE với data đại diện có chỉ ra scan/sort/hash bottleneck?
36. Có redundant indexes làm tăng write overhead không?
37. Pagination có dùng OFFSET quá sâu hoặc count distinct rất đắt?
38. Report có giới hạn date range, group count, timeout và output bytes?
39. Streaming có thực sự bounded memory trên provider/driver hiện tại?
40. Cache/read replica/materialized view có phù hợp traffic/freshness requirement?

### 46.5. Operational correctness

41. Native SQL có parameter binding/allowlist sorts?
42. Cache keys và report snapshots có tenant/currency/timezone/filter/version không?
43. Query giữa nhiều report cards có cùng snapshot/cutoff khi cần?
44. Materialized summaries có idempotency/rebuild/reconciliation?
45. Read replica có lag monitoring và as-of timestamp thực?
46. Async exports có restartability, access control và retention?
47. Tests có fan-out, duplicate equal amounts, zero groups và mixed currencies?
48. Test timezone boundary/partial refund/late-arriving events?
49. Integration tests dùng database/dialect và migrations đủ gần production?
50. Metrics gồm query plan, p95 latency, DB reads, memory và reporting error rate?

## 47. Tài liệu và hướng đọc tiếp

Khi áp dụng vào project thực tế, hãy ưu tiên đặc tả/provider version đúng với ứng dụng:

- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): JPQL SELECT, constructor expressions, GROUP BY/HAVING, aggregate functions, Criteria API, typed queries.
- [Jakarta Persistence 3.2 API](https://jakarta.ee/specifications/persistence/3.2/apidocs/): `Tuple`, `CriteriaBuilder`, `Query` và các kiểu API liên quan.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/): interface/class-based projections, repository queries, pagination, countQuery.
- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/): aggregate functions, window functions, `EXPLAIN`, indexes, materialized views, date/time functions.
- [Hibernate ORM User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): JPQL/HQL, DTO projections, query execution, fetch plans và provider-specific behavior.

Các đường dẫn là tài liệu tham khảo để đối chiếu API/version khi triển khai; không nên suy ra mọi HQL extension hay mọi cú pháp PostgreSQL là JPQL portable.

## 48. Tổng kết

**Lựa chọn projection và truy vấn tổng hợp cho nhu cầu báo cáo** đòi hỏi phân biệt hai việc: *trả về dữ liệu ở hình dạng nào* và *tính toán số liệu ở grain nào*. Tối ưu tốt nhất là **đúng metric trước, giảm dữ liệu không cần thiết, rồi mới đo execution plan và scale kiến trúc**.

### 48.1. Các quy tắc cốt lõi

1. **Đừng tải entity graph chỉ để hiển thị số liệu.** Với list/report ổn định, DTO/record projection giúp chọn đúng fields và giảm object hydration/persistence context overhead.
2. **Dùng scalar aggregates cho một metric** như `COUNT`/`SUM`, nhớ kiểu `COUNT=Long`, `AVG=Double` và NULL semantics của `SUM`.
3. **Dùng `GROUP BY` + DTO cho các breakdown** theo customer/status/currency; `HAVING` áp điều kiện sau nhóm, `WHERE` lọc source rows trước nhóm.
4. **Group theo identity ổn định**, không chỉ display name có thể trùng.
5. **Biết grain trước khi join.** To-many joins có thể nhân order rows, làm cả COUNT và SUM sai. `COUNT(DISTINCT order.id)` giải quyết distinct count, nhưng `SUM(DISTINCT amount)` không thay một metric đúng grain.
6. **Dùng `EXISTS` hoặc pre-aggregation** khi chỉ cần kiểm tra child tồn tại hoặc muốn ghép nhiều child aggregates mà không nhân hàng.
7. **LEFT JOIN cần hiểu ON/WHERE và NULL**, đặc biệt khi phải hiển thị khách/ngày không có dữ liệu.
8. **Money và time cần business policy.** Không cộng khác currency, không dùng current price thay giá lịch sử, không group UTC days nếu báo cáo tính theo timezone địa phương.
9. **Grouped pagination đếm số groups**, không dùng total source rows; thêm stable tie-breaker và cân nhắc keyset/snapshot nếu số liệu thay đổi.
10. **JPQL/Criteria tốt cho report vừa phải**, native SQL thích hợp khi cần CTE, window functions, time buckets và DB-specific analytical features.
11. **Đọc SQL thực tế và đo EXPLAIN**, indexes, sorting, memory, network, p95 latency, concurrency. Một DTO query vẫn có thể chậm nếu scan/aggregate quá lớn.
12. **Dùng cache/replica/materialized views/summary tables khi workload đòi hỏi**, nhưng phải định nghĩa freshness, security scope, snapshot và reconciliation.
13. **Kiểm thử số học và dữ liệu cạnh tranh**, đặc biệt fan-out, same amounts, zero results, timezone boundaries, refunds, mixed currencies và cross-tenant isolation.

### 48.2. Quy trình đơn giản có thể nhớ

```text
Business report requirement
        |
        v
Define metric / grain / filters
        |
        v
Choose projection output contract
        |
        v
Choose JPQL / Criteria / native SQL
        |
        v
Check GROUP BY + JOIN correctness
        |
        v
Verify known fixture results
        |
        v
Inspect SQL + EXPLAIN + indexes
        |
        v
Measure memory / latency / concurrency
        |
        v
Scale with cache, replica, summary or OLAP
        |
        v
Monitor freshness, reconcile, retest
```

> **Nguyên tắc thực hành:** *Báo cáo hiệu quả không phải là query trả ít object nhất bằng mọi giá, mà là query trả đúng số liệu, đúng phạm vi và đúng thời điểm với chi phí hợp lý. Projection giải quyết hình dạng dữ liệu; aggregation giải quyết phép tính; execution plan và read-model architecture giải quyết quy mô.*
