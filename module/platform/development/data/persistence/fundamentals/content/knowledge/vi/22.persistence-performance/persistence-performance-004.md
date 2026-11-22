# Vấn đề N+1 và truy vấn lặp theo từng phần tử

## 1. Một màn hình danh sách có thể gây ra hàng trăm truy vấn thế nào?

Giả sử một ứng dụng Java hiển thị **50 đơn hàng gần nhất**, mỗi đơn có danh sách mặt hàng. Để dựng response, ứng dụng chạy một truy vấn lấy 50 đơn, rồi với **từng đơn** tiếp tục truy vấn các dòng hàng:

```text
SELECT ... FROM orders ... LIMIT 50;              -- 1 truy vấn
SELECT ... FROM order_lines WHERE order_id = ?;   -- đơn 1
SELECT ... FROM order_lines WHERE order_id = ?;   -- đơn 2
...
SELECT ... FROM order_lines WHERE order_id = ?;   -- đơn 50

Tổng cộng: 1 + 50 = 51 truy vấn.
```

Đây là **vấn đề N+1**: một truy vấn lấy **N đối tượng cha**, sau đó thêm một truy vấn **cho mỗi đối tượng** để lấy dữ liệu liên quan. Nếu thêm địa chỉ giao hàng và trạng thái thanh toán theo cách tương tự, đường đi có thể gần `1 + 3N` truy vấn. Khi N tăng, số lượt giao tiếp với database tăng theo từng phần tử.

N+1 không phải lỗi cú pháp SQL: từng truy vấn riêng lẻ có thể rất đúng và chạy rất nhanh. Vấn đề là **cách phối hợp nhiều truy vấn ở tầng ứng dụng**, đặc biệt khi ORM tự tải dữ liệu hoặc khi code lặp và gọi repository bên trong vòng `for`.

Bài học thuộc chương **Hiệu năng** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ nhận diện N+1 trong JPA/Hibernate, MyBatis và JDBC; lựa chọn query projection, fetch join, batch fetching hoặc truy vấn gom theo ID; đồng thời hiểu tác động tới transaction, isolation, chỉ mục, kết nối, bảo mật tenant và độ ổn định khi mở rộng dữ liệu.

> **Nguyên tắc:** Không tối ưu chỉ bằng cách “đổi LAZY thành EAGER” hoặc “join tất cả bảng”. Hãy xác định **màn hình cần dữ liệu nào, số câu SQL thực thi thực tế và kích thước kết quả**, rồi chọn chiến lược nạp dữ liệu phù hợp.

## 2. Định nghĩa chính xác và cách tính chi phí

Cho:

- `N`: số phần tử cha được lấy từ truy vấn đầu.
- `k`: số loại quan hệ được nạp riêng cho mỗi phần tử.
- `Q`: tổng số câu SQL được gửi tới database.

Trong trường hợp đơn giản, mỗi quan hệ bị truy vấn một lần cho từng phần tử:

\[
Q(N) = 1 + kN
\]

Với `N = 50` và `k = 1`, ta có `Q = 51`. Với hai quan hệ cùng kiểu nạp, `Q = 101`. Đây là **mô hình minh họa**, không phải công thức bắt buộc của mọi ORM: first-level cache, second-level cache, batch fetch và dữ liệu đã nạp có thể làm số SQL quan sát được khác đi.

| Số đơn N | 1 truy vấn cha + 1 truy vấn con/đơn | Một truy vấn cha + một truy vấn gom con |
| ---: | ---: | ---: |
| 1 | 2 | 2 |
| 10 | 11 | 2 |
| 50 | 51 | 2 |
| 100 | 101 | 2 |
| 500 | 501 | 2 hoặc nhiều batch |

Nếu mỗi lượt round-trip DB thêm một chi phí mạng, parse, lập lịch và lấy connection/statement, tổng chi phí dễ tăng mạnh ở p95/p99 khi tải thực. Tuy nhiên **51 truy vấn không tương đương 51 connection**: trong một transaction JDBC/JPA, nhiều câu SQL thường chạy trên cùng connection; vấn đề là số lần trao đổi và công việc tại DB.

Một truy vấn join trả hàng triệu dòng cũng có thể chậm hơn 51 truy vấn nhỏ. Vì vậy **mục tiêu là giảm công việc toàn hệ thống**, không chỉ giảm bộ đếm query bằng mọi giá.

## 3. Mô hình dữ liệu xuyên suốt cho ví dụ

Dùng PostgreSQL để minh họa một hệ thống đơn hàng đa tenant:

```sql
CREATE TABLE demo_orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    status TEXT NOT NULL,
    total NUMERIC(18, 2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE demo_order_lines (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES demo_orders(id),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0)
);

-- Hỗ trợ truy vấn danh sách đơn theo tenant và thời gian.
CREATE INDEX ix_demo_orders_tenant_recent
ON demo_orders(tenant_id, created_at DESC, id DESC);

-- Hỗ trợ lấy các dòng hàng theo ID đơn.
CREATE INDEX ix_demo_order_lines_order
ON demo_order_lines(order_id);
```

Để đơn giản, khóa ngoại của dòng hàng tham chiếu ID đơn duy nhất toàn bảng. Truy vấn đọc dòng hàng theo đơn vẫn phải bảo đảm quyền truy cập **qua đơn thuộc đúng tenant**. Nếu hệ thống có nhiều đường truy cập trực tiếp dòng hàng, có thể cần lưu/kiểm tra `tenant_id` tại bảng con, dùng khóa ngoại tổng hợp hoặc cơ chế bảo mật như RLS theo thiết kế tổng thể.

Màn hình cần hiển thị có hai dạng:

1. **Danh sách đơn:** ID, trạng thái, tổng tiền, thời gian tạo; không cần tất cả dòng hàng.
2. **Chi tiết đơn:** một đơn và các dòng hàng của nó.

Hai nhu cầu ấy **không nhất thiết nên dùng cùng một chiến lược fetch**. Việc cố nạp mọi quan hệ cho danh sách là một nguyên nhân phổ biến của over-fetching.

## 4. N+1 xuất hiện trong vòng lặp Java thuần như thế nào?

Không cần ORM mới có N+1. Giả sử repository dùng JDBC hoặc MyBatis:

```java
List<Order> orders = orderRepository.findRecent(tenantId, 50); // 1 SELECT

for (Order order : orders) {
    // Mỗi lần gọi lại gửi một SELECT xuống database.
    List<OrderLine> lines = lineRepository.findByOrderId(order.id());
    order.setLines(lines);
}
```

Nếu `findRecent` trả 50 đơn, vòng lặp thường gây ra thêm 50 lượt SQL. Mỗi lần `findByOrderId` có index tốt vẫn là một round-trip và một lần thực thi truy vấn.

Cách thay thế là **gom nhu cầu dữ liệu**:

```java
List<Order> orders = orderRepository.findRecent(tenantId, 50);
List<UUID> orderIds = orders.stream().map(Order::id).toList();

Map<UUID, List<OrderLine>> linesByOrder =
        lineRepository.findByOrderIds(tenantId, orderIds);

for (Order order : orders) {
    order.setLines(linesByOrder.getOrDefault(order.id(), List.of()));
}
```

Đoạn trên mô tả hợp đồng repository; `findByOrderIds` phải tự triển khai bằng **một truy vấn gom hoặc một số batch**. Nếu nó ngầm gọi lại `findByOrderId` trong vòng lặp, N+1 vẫn còn nguyên.

```sql
-- Truy vấn gom các dòng hàng từ danh sách ID đơn.
-- :order_ids là tập tham số có kiểu UUID đã được bind an toàn.
SELECT l.id, l.order_id, l.sku, l.quantity, l.unit_price
FROM demo_order_lines AS l
JOIN demo_orders AS o ON o.id = l.order_id
WHERE o.tenant_id = :tenant_id
  AND l.order_id IN (:order_ids)
ORDER BY l.order_id, l.id;
```

Danh sách ID rỗng phải được xử lý riêng ở tầng ứng dụng để tránh sinh SQL `IN ()` không hợp lệ. Với danh sách lớn, chia batch theo giới hạn và execution plan của DBMS; không ghép chuỗi ID trực tiếp từ người dùng vào SQL.

## 5. JPA/Hibernate: LAZY, persistence context và lúc nào SQL được gửi

Trong JPA, một quan hệ `@OneToMany` thường được khai báo `FetchType.LAZY`. Khi lấy danh sách `OrderEntity`, ORM có thể chưa truy vấn `order_lines` cho từng đơn. SQL bổ sung chỉ xuất hiện khi code **truy cập quan hệ**.

Ví dụ ánh xạ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "demo_orders")
public class OrderEntity {
    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    private String status;
    private BigDecimal total;

    @Column(name = "created_at")
    private Instant createdAt;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    protected OrderEntity() {}

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public BigDecimal getTotal() { return total; }
    public Instant getCreatedAt() { return createdAt; }
    public List<OrderLineEntity> getLines() { return lines; }
}

@Entity
@Table(name = "demo_order_lines")
public class OrderLineEntity {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id", nullable = false)
    private OrderEntity order;

    private String sku;
    private int quantity;

    @Column(name = "unit_price")
    private BigDecimal unitPrice;

    protected OrderLineEntity() {}

    public UUID getId() { return id; }
    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
    public BigDecimal getUnitPrice() { return unitPrice; }
}
```

Hai lớp này là **entity lưu trữ**, chưa phải request/response DTO. Bản ví dụ tập trung vào **đọc dữ liệu**: constructor tạo mới, setter quản lý aggregate, auditing và các invariant ghi chưa được triển khai.

### Một phép gọi `getLines()` có thể phát sinh SQL

```java
List<OrderEntity> orders = entityManager.createQuery(
        """
        SELECT o FROM OrderEntity o
        WHERE o.tenantId = :tenantId
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        OrderEntity.class)
    .setParameter("tenantId", tenantId)
    .setMaxResults(50)
    .getResultList();

for (OrderEntity order : orders) {
    // Nếu collection chưa được khởi tạo, Hibernate có thể SELECT riêng.
    System.out.println(order.getLines().size());
}
```

Trong một persistence context mới và không có batch/cache giúp đỡ, pattern thường là **1 + 50 câu SQL**. Nếu ở ngoài persistence context còn hoạt động, truy cập LAZY có thể ném `LazyInitializationException` thay vì nạp thêm. Đó là **hai biểu hiện của quyết định fetch không phù hợp với ranh giới sử dụng**, không có nghĩa nên mở transaction thật rộng chỉ để che lỗi.

### Vì sao `EAGER` không phải nút “sửa N+1”?

`FetchType.EAGER` nói rằng quan hệ phải được nạp trước khi entity được xem là đã tải đầy đủ theo hợp đồng fetch, **không bảo đảm chỉ có một truy vấn SQL**. Tùy loại truy vấn, provider và cấu hình, ORM vẫn có thể phát sinh **secondary selects cho từng entity**, tức vẫn gặp N+1.

Đổi tất cả quan hệ thành EAGER còn làm những màn hình **không cần** dữ liệu con phải nạp thêm dữ liệu, tăng tải và bộ nhớ. Chiến lược hợp lý là giữ mặc định thận trọng rồi **chọn fetch plan theo use case**.

## 6. Cách phát hiện N+1 từ SQL log và số liệu runtime

Đừng chỉ nhìn số dòng Java. Để xác định N+1, phải quan sát **các câu SQL thực sự gửi xuống DB** và xem chúng tăng như thế nào khi N tăng.

Ví dụ một trace đáng ngờ:

```text
1: SELECT ... FROM demo_orders WHERE tenant_id = ? LIMIT ?
2: SELECT ... FROM demo_order_lines WHERE order_id = ?
3: SELECT ... FROM demo_order_lines WHERE order_id = ?
4: SELECT ... FROM demo_order_lines WHERE order_id = ?
...
51: SELECT ... FROM demo_order_lines WHERE order_id = ?
```

Nếu các câu SQL lặp cùng cấu trúc với tham số khác nhau, đó là tín hiệu mạnh của pattern truy vấn theo phần tử. Một lần lặp duy nhất không đủ chẩn đoán; vấn đề xuất hiện khi số lần lặp tỷ lệ với số bản ghi cha.

| Công cụ/quan sát | Dùng để làm gì | Giới hạn |
| --- | --- | --- |
| Hibernate SQL logging | Xem truy vấn đã thực thi, thứ tự và mẫu lặp | Log có thể nhiều, chứa dữ liệu nhạy cảm nếu bật bind values |
| Hibernate statistics | Đếm statement/collection fetch, kiểm tra ảnh hưởng fetch plan | Một số counter ở cấp `SessionFactory`, bị nhiễu khi nhiều test/thread cùng chạy |
| DataSource proxy / JDBC interceptor | Đếm truy vấn theo request/transaction | Phải cấu hình instrumentation đúng mọi datasource |
| APM tracing | Gắn DB spans vào endpoint, thấy request có nhiều round-trip | Sampling và grouping có thể che một số câu |
| `EXPLAIN (ANALYZE, BUFFERS)` | Phân tích **một câu truy vấn** chậm hoặc query plan xấu | Không tự đếm N+1 ở tầng Java |
| `pg_stat_statements` (PostgreSQL, nếu bật) | Xem mẫu SQL tổng hợp, tần suất gọi và thời gian | Cần đối chiếu endpoint/trace để xác định vòng lặp gây gọi nhiều |

Trong môi trường thử nghiệm Hibernate, có thể bật thống kê theo cấu hình provider:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Các chi tiết tên property phụ thuộc stack/phiên bản Hibernate. Đừng bật toàn bộ logging tham số SQL ở production mà không kiểm soát thông tin cá nhân, mật khẩu, token và khối lượng log.

### Phải đo ở kích thước dữ liệu đủ khác nhau

Chạy cùng endpoint với N = 1, 10, 50, 100 trong môi trường dữ liệu và cache được kiểm soát. Nếu query count tăng gần tuyến tính theo N, nguyên nhân có thể là N+1. Nếu query count gần cố định nhưng latency tăng, hãy xem **kích thước dữ liệu trả về, sắp xếp, index, join fan-out hoặc serialization**.

Warm cache có thể che N+1. Khi kiểm thử, cần biết first-level/second-level cache có đang chứa entity/collection hay không; kết quả của một request chạy lần hai có thể khác lần đầu.

## 7. Giải pháp A: DTO projection khi màn hình chỉ cần vài trường

Một màn hình danh sách chỉ hiển thị `id`, `status` và `total` **không nên tự động tải toàn bộ `lines`**. Cách trực tiếp nhất là truy vấn vào DTO:

```java
package com.example.api;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderListItem(
        UUID id, String status, BigDecimal total) {}
```

```java
List<OrderListItem> items = entityManager.createQuery(
        """
        SELECT new com.example.api.OrderListItem(o.id, o.status, o.total)
        FROM OrderEntity o
        WHERE o.tenantId = :tenantId
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        OrderListItem.class)
    .setParameter("tenantId", tenantId)
    .setMaxResults(50)
    .getResultList();
```

Với JPQL constructor expression hợp lệ và mapping đúng, truy vấn chỉ lấy các trường cần thiết; nó không tạo collection để serializer vô tình truy cập. DTO read model giúp tránh nhiều trường hợp N+1 **ngay từ thiết kế hợp đồng dữ liệu**.

Ưu điểm:

- Giảm số cột, số object ORM managed và nguy cơ truy cập quan hệ ngoài ý muốn.
- Phân trang danh sách đơn giản hơn so với join fetch collection.
- Response API tách khỏi cấu trúc entity/schema, giảm rủi ro lộ thông tin nội bộ.

Giới hạn: nếu DTO cần **số dòng hàng, tổng tiền từ nhiều bảng hoặc trường tổng hợp**, vẫn phải viết SQL/JPQL phù hợp; projection **không tự động** giải quyết query con hoặc phép tính bị gọi riêng cho từng phần tử.

Ví dụ gộp tổng số lượng theo đơn trong PostgreSQL:

```sql
SELECT o.id,
       o.status,
       o.total,
       COALESCE(SUM(l.quantity), 0) AS total_quantity
FROM demo_orders AS o
LEFT JOIN demo_order_lines AS l ON l.order_id = o.id
WHERE o.tenant_id = :tenant_id
GROUP BY o.id, o.status, o.total
ORDER BY MAX(o.created_at) DESC, o.id DESC
LIMIT :limit;
```

Lệnh trên minh họa một cách tổng hợp dữ liệu, nhưng **không mặc định tốt hơn** chiến lược lấy page đơn rồi tính tổng cho đúng tập page. Query plan, lượng đơn của tenant, chỉ mục và bộ nhớ dành cho GROUP BY phải được đo. Với bảng lớn, **phân trang đơn trước rồi join/tổng hợp page nhỏ** thường là ứng viên đáng thử.

## 8. Giải pháp B: `JOIN FETCH` cho màn hình chi tiết

Khi client cần **một đơn và tất cả dòng hàng**, một fetch join thường hợp lý:

```java
OrderEntity order = entityManager.createQuery(
        """
        SELECT DISTINCT o
        FROM OrderEntity o
        LEFT JOIN FETCH o.lines
        WHERE o.id = :orderId
          AND o.tenantId = :tenantId
        """,
        OrderEntity.class)
    .setParameter("orderId", orderId)
    .setParameter("tenantId", tenantId)
    .getSingleResult();
```

Với kết quả **một đơn**, truy vấn có thể lấy đủ dữ liệu cha/con qua một lượt SQL thay vì tải cha trước rồi kích hoạt lazy collection. `LEFT JOIN` vẫn trả đơn **không có dòng hàng**; nếu dùng `INNER JOIN`, đơn không có con sẽ bị loại khỏi kết quả.

Hãy phân biệt **số object miền/entity** với **số hàng SQL thực tế**:

```text
Một đơn O1 với 3 dòng hàng:
O1, L1
O1, L2
O1, L3

SQL trả 3 hàng, ORM có thể dựng 1 OrderEntity và 3 OrderLineEntity.
```

`DISTINCT` trong JPQL giúp biểu đạt yêu cầu kết quả entity cha không trùng; chi tiết khử trùng lặp ở ORM/SQL có thể thay đổi theo JPA provider và phiên bản. Nó **không làm biến mất** các hàng join vật lý khi một cha có nhiều con.

### Khi JOIN FETCH trở nên tốn kém

Nếu một đơn có 10.000 dòng, truy vấn sẽ tải rất nhiều dữ liệu dù chỉ có một lệnh SQL. Nếu fetch cùng lúc hai collection độc lập, ví dụ 20 dòng hàng và 10 lịch sử trạng thái, join có thể tạo **20 × 10 = 200 hàng** cho một đơn do phép nhân kết hợp.

Hibernate còn có giới hạn đối với việc fetch đồng thời nhiều *bag* collection trong một số mapping, chẳng hạn lỗi `MultipleBagFetchException`. Không nên giải quyết N+1 bằng cách fetch join mọi collection theo phản xạ.

**Fetch join là công cụ của một fetch plan cụ thể**, không phải default tốt nhất cho mọi endpoint.

## 9. Giải pháp C: Entity graph theo use case

Trong JPA, có thể khai báo `EntityGraph` hoặc truyền fetch graph/hint để chỉ định quan hệ cần tải:

```java
import jakarta.persistence.EntityGraph;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import java.util.UUID;

EntityGraph<OrderEntity> graph =
        entityManager.createEntityGraph(OrderEntity.class);
graph.addAttributeNodes("lines");

TypedQuery<OrderEntity> query = entityManager.createQuery(
        """
        SELECT o FROM OrderEntity o
        WHERE o.id = :orderId AND o.tenantId = :tenantId
        """,
        OrderEntity.class);
query.setParameter("orderId", orderId);
query.setParameter("tenantId", tenantId);
query.setHint("jakarta.persistence.fetchgraph", graph);
OrderEntity detail = query.getSingleResult();
```

Ví dụ biểu đạt fetch graph đồng thời lọc `tenantId` **ngay tại database**. Trong hệ đa tenant, cần đặt điều kiện bảo mật ở truy vấn hoặc áp dụng cơ chế DB tương ứng như RLS, không chỉ tải entity theo ID rồi mới kiểm tra quyền sau đó.

**Entity graph không hứa chắc một câu SQL**: provider có thể dùng join hoặc các câu truy vấn bổ sung để thực hiện fetch plan. Cần đo query count và kích thước kết quả. Khi graph chứa collection, các cảnh báo về pagination và nhân hàng vẫn áp dụng.

## 10. Giải pháp D: batch fetching khi vẫn muốn lazy loading

Hibernate có thể gom nhiều lazy collection/proxy vào một hoặc vài truy vấn thay vì một truy vấn cho từng cha. Đây là một khả năng **đặc thù của provider**, không phải bảo đảm tự động của JPA.

Ví dụ cấu hình Hibernate:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Hoặc dùng annotation Hibernate trên quan hệ:

```java
@org.hibernate.annotations.BatchSize(size = 32)
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLineEntity> lines = new ArrayList<>();
```

Khi một lazy collection được truy cập, Hibernate có thể nạp thêm các collection chưa khởi tạo của những order khác trong persistence context bằng các truy vấn theo **nhiều ID**. Với 50 đơn và batch 32, số truy vấn lấy dòng hàng có thể giảm còn vài lượt thay vì 50, tùy provider, cách truy cập, cache và dữ liệu.

So sánh minh họa:

```text
Không batch:
  1 SELECT orders + 50 SELECT order_lines theo từng order

Có batch size 32 (giản lược):
  1 SELECT orders + 1 SELECT lines WHERE order_id IN (32 ID)
                  + 1 SELECT lines WHERE order_id IN (18 ID)
```

**Không mặc định** SQL chính xác luôn có hai danh sách 32 và 18 ID. Cách triển khai có thể padding tham số, nạp trước tập khác, sử dụng cache hoặc thay đổi theo phiên bản Hibernate.

Ưu điểm: ít phải thay đổi code gọi lazy collection, phù hợp nhiều luồng đọc và giảm query count. Nhược điểm: vẫn có hơn một round-trip, có thể nạp thêm quan hệ không dùng và phụ thuộc persistence context. Cần thử với N lớn, nhiều quan hệ và giới hạn số tham số của DBMS.

**SUBSELECT fetching** là một lựa chọn Hibernate khác cho một số collection: provider có thể dựa trên truy vấn lấy parent để nạp nhiều collection cùng lúc. Nó có trade-off về số hàng và phạm vi session; không nên bật chỉ vì nghe tên “một truy vấn”.

## 11. Giải pháp E: phân trang cha trước, nạp con sau

Đây thường là phương án hữu ích nhất cho danh sách có nhiều parent nhưng vẫn phải hiển thị con: **phân trang đơn hàng trước, sau đó chỉ lấy quan hệ cho tập ID trong trang**.

### Vì sao không fetch join collection trực tiếp với LIMIT/OFFSET?

Một truy vấn:

```java
entityManager.createQuery(
        """
        SELECT o FROM OrderEntity o
        LEFT JOIN FETCH o.lines
        WHERE o.tenantId = :tenantId
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        OrderEntity.class)
    .setParameter("tenantId", tenantId)
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
```

trông như “50 đơn với dòng hàng trong một câu SQL”, nhưng **LIMIT trên kết quả JOIN không giống LIMIT trên 50 đơn riêng biệt**. Nếu DB giới hạn 50 **hàng join**, một đơn có 50 dòng có thể chiếm hết trang. Một số phiên bản/cấu hình Hibernate chọn áp dụng phân trang collection fetch ở bộ nhớ sau khi tải nhiều hàng, khiến truy vấn cực kỳ tốn kém; có thể phát cảnh báo hoặc cấu hình để **fail fast**.

Hibernate có tùy chọn liên quan `hibernate.query.fail_on_pagination_over_collection_fetch` để biến một số trường hợp nguy hiểm thành lỗi khi phát triển. Tên và hành vi phải được kiểm chứng theo phiên bản đang dùng; không dùng thuộc tính này thay cho một fetch plan được thiết kế đúng.

### Hai bước: chọn ID trang rồi lấy dữ liệu đầy đủ

**Bước 1: Chọn ID đơn theo thứ tự ổn định.**

```java
List<UUID> pageIds = entityManager.createQuery(
        """
        SELECT o.id FROM OrderEntity o
        WHERE o.tenantId = :tenantId
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        UUID.class)
    .setParameter("tenantId", tenantId)
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
```

**Bước 2: Lấy các đơn và dòng hàng của chính tập ID đó**, không phân trang trên collection join:

```java
List<OrderEntity> loaded = pageIds.isEmpty()
    ? List.of()
    : entityManager.createQuery(
            """
            SELECT DISTINCT o FROM OrderEntity o
            LEFT JOIN FETCH o.lines
            WHERE o.tenantId = :tenantId
              AND o.id IN :ids
            """,
            OrderEntity.class)
        .setParameter("tenantId", tenantId)
        .setParameter("ids", pageIds)
        .getResultList();
```

**Bước 3: Khôi phục thứ tự trang.** `IN :ids` **không bảo đảm** DB trả dữ liệu theo thứ tự danh sách ID; sắp lại ở Java theo `pageIds` trước khi dựng response:

```java
Map<UUID, OrderEntity> byId = loaded.stream()
        .collect(java.util.stream.Collectors.toMap(
                OrderEntity::getId, java.util.function.Function.identity()));

List<OrderEntity> ordered = pageIds.stream()
        .map(byId::get)
        .filter(java.util.Objects::nonNull)
        .toList();
```

Với một trang không quá lớn, số lượt SQL thường là **hai** (chưa tính câu `COUNT` nếu UI cần tổng số trang). Nếu mỗi đơn có nhiều dòng hoặc cần thêm collection khác, hãy đánh giá số hàng join và cân nhắc **ba truy vấn**: trang parent, dữ liệu parent, dữ liệu children, rồi group/map thành DTO thay vì join nặng.

### Tính nhất quán giữa hai SELECT

Ở PostgreSQL `READ COMMITTED`, mỗi câu `SELECT` thông thường có snapshot riêng. Giữa bước 1 và 2, một order có thể bị xóa/chuyển tenant (nếu mô hình cho phép) hoặc có dòng hàng mới được commit. Hai bước không tự tạo **một ảnh chụp nguyên tử** chỉ vì chạy trong một phương thức Java.

Nếu báo cáo yêu cầu một snapshot ổn định, hãy chọn transaction/isolation phù hợp (ví dụ `REPEATABLE READ` của PostgreSQL) và cân nhắc độ dài transaction, MVCC retention cùng tải. Nếu màn hình chấp nhận biến động theo thời gian thực, ghi rõ semantics và xử lý trường hợp ID không còn tồn tại khi bước 2 chạy.

**Pagination theo OFFSET** còn có thể trùng/thiếu bản ghi giữa các trang khi có insert mới. Với feed lớn và yêu cầu paging ổn định hơn, xem xét **keyset pagination** theo khóa sắp xếp (`created_at`, `id`) với điều kiện tiếp nối phù hợp, cùng tenant scope và index.

## 12. Hai truy vấn không join: tổng hợp kết quả an toàn ở Java

Đôi khi chỉ cần DTO hiển thị các dòng hàng, không cần ORM dựng entity graph. Một lựa chọn là dùng **hai truy vấn SQL rõ ràng**:

```sql
-- 1. Lấy trang đơn trước; tham số tenant được xác thực.
SELECT id, status, total, created_at
FROM demo_orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;

-- 2. Dùng đúng tập id lấy từ bước 1:
SELECT l.order_id, l.id, l.sku, l.quantity, l.unit_price
FROM demo_order_lines AS l
JOIN demo_orders AS o ON o.id = l.order_id
WHERE o.tenant_id = :tenant_id
  AND l.order_id IN (:order_ids)
ORDER BY l.order_id, l.id;
```

Sau đó group theo `order_id`:

```java
Map<UUID, List<OrderLineDto>> linesByOrder = new HashMap<>();
for (OrderLineDto line : queriedLines) {
    linesByOrder.computeIfAbsent(
            line.orderId(), ignored -> new ArrayList<>()).add(line);
}

List<OrderDetailDto> result = ordersInPageOrder.stream()
        .map(o -> new OrderDetailDto(
                o.id(), o.status(), o.total(),
                linesByOrder.getOrDefault(o.id(), List.of())))
        .toList();
```

Các kiểu `OrderLineDto`, `OrderDetailDto` và `ordersInPageOrder` là thành phần minh họa của application read model; khi xây dựng thực tế phải định nghĩa record/mapper và đồng nhất tên trường. Cần xử lý đơn không có dòng hàng bằng danh sách rỗng, không bỏ đơn khỏi kết quả.

Đối với dữ liệu đa tenant, đừng chỉ kiểm tra tenant ở truy vấn cha rồi tin mọi ID con từ ngoài. Ví dụ trên vẫn join với `demo_orders` để scope tenant ở câu SQL thứ hai. Với hệ thống nhiều datasource/replica, cả hai truy vấn cũng cần đạt yêu cầu nhất quán đọc đã công bố.

Một chi tiết ORM: nếu tự truy vấn `OrderLineEntity` rồi group ở Java, **điều đó không nhất thiết đánh dấu collection `order.getLines()` của `OrderEntity` đã initialized**. Nếu sau đó lại gọi `getLines()` trên entity gốc, ORM có thể tiếp tục thực hiện N+1. Hãy dựng response từ read model đã group, hoặc dùng fetch plan đúng.

## 13. MyBatis và N+1 từ nested select

MyBatis không có dirty checking/persistence context kiểu JPA, nhưng vẫn có N+1 khi khai báo collection thông qua **nested select**. Ví dụ XML minh họa:

```xml
<resultMap id="orderMap" type="com.example.persistence.OrderRow">
  <id property="id" column="id"/>
  <result property="status" column="status"/>
  <collection property="lines"
              column="id"
              select="findLinesByOrderId"/>
</resultMap>

<select id="findRecentOrders" resultMap="orderMap">
  SELECT id, status
  FROM demo_orders
  WHERE tenant_id = #{tenantId}
  ORDER BY created_at DESC, id DESC
  LIMIT #{limit}
</select>

<select id="findLinesByOrderId"
        parameterType="java.util.UUID"
        resultType="com.example.persistence.OrderLineRow">
  SELECT id, order_id, sku, quantity, unit_price
  FROM demo_order_lines
  WHERE order_id = #{value}
</select>
```

Đây là các fragment để đặt trong mapper XML thực tế, với namespace/interface và các kiểu Java được định nghĩa tương ứng. MyBatis có thể nạp nested select ngay hoặc trì hoãn theo cấu hình; khi collection được lấy cho từng order, số truy vấn con vẫn có thể là N.

Các cách giải quyết:

- Viết một truy vấn `JOIN` và `resultMap` cho danh sách phù hợp, nhớ khai báo `<id>` đúng để không tạo object trùng.
- Dùng hai mapper query: lấy trang order, sau đó `SELECT ... WHERE order_id IN (...)` qua `<foreach>` với tham số được bind, group kết quả trong Java.
- Dùng DTO projection hoặc SQL tổng hợp nếu màn hình không cần toàn bộ dòng hàng.

MyBatis giúp **viết SQL chủ động**, nhưng không tự tránh việc mapper method bị gọi trong vòng lặp. Khi dùng dynamic SQL, `#{value}` bind giá trị; tránh đưa input không tin cậy vào cấu trúc SQL bằng text substitution.

## 14. JDBC thuần: gom nhiều ID không có nghĩa ghép chuỗi SQL tùy tiện

Nếu repository dùng JDBC trực tiếp, `PreparedStatement` vẫn hỗ trợ batching ID qua các placeholder:

```java
public static Map<UUID, List<String>> loadSkusByOrderIds(
        Connection connection, UUID tenantId, List<UUID> ids)
        throws SQLException {
    if (ids.isEmpty()) {
        return Map.of();
    }

    String placeholders = String.join(
            ",", java.util.Collections.nCopies(ids.size(), "?"));
    String sql = """
        SELECT l.order_id, l.sku
        FROM demo_order_lines l
        JOIN demo_orders o ON o.id = l.order_id
        WHERE o.tenant_id = ?
          AND l.order_id IN (""" + placeholders + ") ORDER BY l.order_id";

    Map<UUID, List<String>> result = new HashMap<>();
    try (PreparedStatement st = connection.prepareStatement(sql)) {
        st.setObject(1, tenantId);
        for (int i = 0; i < ids.size(); i++) {
            st.setObject(i + 2, ids.get(i));
        }
        try (ResultSet rows = st.executeQuery()) {
            while (rows.next()) {
                UUID id = (UUID) rows.getObject("order_id");
                result.computeIfAbsent(id, ignored -> new ArrayList<>())
                      .add(rows.getString("sku"));
            }
        }
    }
    return result;
}
```

Ví dụ là **phần thân phương thức**: cần import `java.sql.*`, `java.util.*` ở lớp chứa nó. Chuỗi SQL được tạo động **chỉ ở số lượng ký tự `?`**, còn mọi ID và tenant được bind bằng tham số JDBC; không ghép trực tiếp giá trị của client vào SQL.

Với `ids` rất lớn, giới hạn số bind parameters, độ dài SQL, parse cost và execution plan có thể làm một truy vấn gom quá lớn kém hiệu quả. Chia batch có giới hạn, dùng array parameter (ví dụ PostgreSQL `= ANY(?::uuid[])` với kiểu array phù hợp), bảng tạm hoặc phương án khác theo DBMS.

Batch fetching để **đọc nhiều ID** khác với `addBatch()/executeBatch()` của JDBC để **thực thi nhiều statement ghi**. Hai kỹ thuật đều giảm overhead theo cách khác nhau; không nhầm hai khái niệm này.

## 15. N+1 có thể xuất hiện ở đâu ngoài collection?

| Ngữ cảnh | Mẫu gây N+1 | Cách suy nghĩ về giải pháp |
| --- | --- | --- |
| Quan hệ `@ManyToOne` | Mỗi `OrderLine` gọi `getProduct()` để lấy tên hàng | Join hoặc batch fetch/product projection |
| Kiểm tra quyền | Mỗi đơn gọi permission repository riêng | Truy vấn quyền theo tập ID hoặc policy ở DB |
| Xây DTO | Mapper gọi truy vấn lấy discount/shipping cho từng item | Tổng hợp dữ liệu trước khi map |
| GraphQL resolver | Mỗi resolver field truy vấn DB từng parent | DataLoader/batching theo request, tenant scope |
| REST serializer | Serialize entity, chạm lazy property | DTO response rõ ràng và fetch plan trong use case |
| Template/view | View gọi `getLines().size()` cho từng order | Tránh I/O ẩn trong view |
| Kiểm tra tồn kho trong batch | Mỗi dòng CSV gọi `findSku(...)` | Lấy dữ liệu theo tập, giữ invariant tại bước ghi |
| Message consumer | Xử lý một batch event, mỗi event SELECT cùng loại | Gom tham chiếu hoặc tái dùng dữ liệu có kiểm soát |

Với GraphQL, `DataLoader` có thể gom các ID phát sinh từ resolver trong một đợt; nhưng batch loader phải thực sự thực hiện **truy vấn gom**, bảo đảm thứ tự kết quả gắn đúng ID và không gom dữ liệu của các tenant/quyền khác nhau.

Với permission và tồn kho, tối ưu truy vấn không được làm yếu đi **kiểm tra quyền hoặc tính đúng đắn cạnh tranh**. Batch đọc trạng thái cũ để hiển thị khác với ra quyết định ghi dựa trên dữ liệu có thể đã thay đổi.

## 16. N+1, index và query plan: tối ưu cả số câu lẫn nội dung SQL

Giảm từ 51 SQL xuống 2 SQL thường hữu ích, nhưng hai câu mới cũng phải được tối ưu:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT l.id, l.order_id, l.sku, l.quantity, l.unit_price
FROM demo_order_lines l
JOIN demo_orders o ON o.id = l.order_id
WHERE o.tenant_id = '00000000-0000-0000-0000-000000000001'::uuid
  AND l.order_id IN (
      '00000000-0000-0000-0000-000000000010'::uuid,
      '00000000-0000-0000-0000-000000000011'::uuid
  );
```

Các UUID trong ví dụ chỉ dùng khi chạy trên dữ liệu **thử nghiệm** tương ứng. `EXPLAIN ANALYZE` thực thi truy vấn; với SELECT là thao tác đọc, nhưng vẫn tốn tài nguyên, nên chọn thời điểm và môi trường thích hợp. Quan sát:

- **Index scan, bitmap scan hay sequential scan**: lựa chọn phụ thuộc độ chọn lọc, kích thước bảng và thống kê.
- **Actual rows so với estimated rows**: ước lượng sai có thể khiến planner chọn join không phù hợp.
- **Buffers/I/O**: dữ liệu có đang được đọc quá nhiều không.
- **Sort/hash memory và temp I/O**: join/aggregation lớn có đẩy dữ liệu ra đĩa tạm không.
- **Thời gian thực thi SQL**: so với latency phía Java và network để biết nút nghẽn nằm đâu.

Chỉ mục `demo_order_lines(order_id)` giúp truy vấn con theo từng order và truy vấn gom theo tập order ID. Chỉ mục `demo_orders(tenant_id, created_at DESC, id DESC)` phục vụ lọc tenant và sắp xếp trang. Nhưng index không tự giảm số lần ORM gọi SQL; N+1 vẫn là lỗi **cách nạp dữ liệu**.

Một `JOIN FETCH` trả rất nhiều cột và hàng lặp có thể gây **network transfer**, GC pressure và hydrate object chậm. Vì vậy đo cả `rows returned`, bytes, CPU, heap, GC, thời gian serialize và p95/p99 của endpoint.

## 17. Cache có thể che N+1 nhưng không sửa cấu trúc truy cập

First-level cache của JPA giúp tránh nạp lại **cùng entity** trong một persistence context. Second-level cache hoặc cache ứng dụng có thể giảm một số lượt DB. Tuy nhiên:

- Cache miss/cold start vẫn bộc lộ N+1.
- Dữ liệu nhiều tenant hoặc key mới có thể tạo mẫu miss đồng loạt.
- Cache tự nó cần chính sách invalidation, TTL và độ mới.
- Tăng cache hit rate không chứng minh một vòng lặp gọi repository theo từng phần tử đã được thiết kế tốt.
- Cùng một SQL pattern được gọi N lần nhưng tất cả cache hit ở lần benchmark thứ hai có thể làm thời gian đo rất đẹp và kết luận sai.

**Không dùng cache làm giải pháp đầu tiên** cho một vấn đề có thể được giải quyết bằng cách lấy đúng tập dữ liệu trong một hoặc vài truy vấn. Sau khi sửa fetch plan, cache có thể là lớp tối ưu bổ sung phù hợp với hợp đồng nhất quán.

## 18. Transaction, pool và hiệu năng dưới tải

N+1 tăng thời gian giữ tài nguyên:

```text
request -> lấy connection
        -> query parent
        -> N lượt query child
        -> map/serialize
        -> trả connection
```

Nếu transaction giữ connection trong toàn bộ đoạn này, thời gian giữ connection tăng có thể làm pool cạn khi có nhiều request đồng thời. Nếu các query child chạy ngoài transaction hoặc mở connection riêng, còn phát sinh chi phí lấy connection và khó bảo đảm cùng snapshot đọc.

**Không mở transaction ghi lâu chỉ để tránh LazyInitializationException.** Hãy tải và chuyển sang DTO bên trong một ranh giới đọc phù hợp, đóng tài nguyên đúng lúc. Trong Spring, `@Transactional(readOnly = true)` có thể giúp diễn đạt use case đọc, nhưng **không tự làm SQL chạy ít đi, không bảo đảm không có truy vấn và không thay thế lựa chọn isolation**.

Lưu ý một số lựa chọn Spring/Hibernate dùng **Open Session in View**: persistence context còn mở khi controller/view serialize response nên lazy loading vẫn chạy sau phần service. Điều này có thể che giấu N+1 ở tầng HTTP và làm chi phí I/O xuất hiện muộn. Tắt OSIV (nếu phù hợp kiến trúc) giúp lộ chỗ thiếu fetch plan sớm hơn, nhưng cần **sửa cách lấy dữ liệu** thay vì chỉ thay cấu hình rồi chấp nhận lỗi.

Nếu giải pháp dùng hai hoặc ba truy vấn để dựng một trang, hãy xác định snapshot consistency: `READ COMMITTED` có thể nhìn các trạng thái đã commit ở thời điểm khác nhau; `REPEATABLE READ` trên PostgreSQL có thể giữ một snapshot phù hợp với báo cáo nhưng cũng có chi phí giữ snapshot. Lựa chọn phải dựa trên yêu cầu nghiệp vụ, không chỉ hiệu năng.

## 19. Đo hiệu quả trước và sau một thay đổi fetch plan

Một thí nghiệm có thể chạy trong môi trường thử nghiệm:

1. Seed ít nhất 100 đơn của một tenant; phân bố số dòng hàng đa dạng: 0, 1, 10, 100, có vài đơn lớn.
2. Chạy endpoint với page size 10, 50, 100 và đặt giới hạn trả dữ liệu rõ ràng.
3. Ghi số SQL, số hàng, byte truyền, DB execution time, request latency p50/p95/p99, pool occupancy và heap.
4. Chạy lần đầu **cold cache**, lần sau warm cache; tách hai loại kết quả.
5. Giữ nguyên dữ liệu/traffic khi so sánh phiên bản cũ và phương án DTO projection, fetch join, batch hoặc hai truy vấn.
6. Xác nhận **kết quả trả về tương đương về nghiệp vụ**: đủ dòng hàng, thứ tự, đơn không có con, scope tenant, pagination không mất hàng.
7. Thử thêm đồng thời 10–50 request (tùy năng lực môi trường) để phát hiện pool wait và query contention, nhưng không mặc định một cấu hình tải là đại diện production.

Một bảng kết quả **giả định** để minh họa cách đánh giá, không phải số đo thực tế:

| Chiến lược | Page size | SQL/request | Đánh đổi cần đo |
| --- | ---: | ---: | --- |
| Vòng lặp tải dòng hàng | 50 | Khoảng 51 | Nhiều round-trip; ít hàng mỗi query |
| Batch fetch size 32 | 50 | Có thể khoảng 3 | Phụ thuộc provider/cache/persistence context |
| Hai bước page ID rồi fetch join | 50 | Thường khoảng 2 | Số hàng join, thứ tự map, hai snapshot |
| DTO chỉ lấy trường danh sách | 50 | Thường 1 | Không có dòng hàng chi tiết |
| Một fetch join cho tất cả dữ liệu | 50 | Có thể 1 nhưng pagination nguy hiểm | Row explosion và memory pagination |

Kết quả tối ưu là phương án thỏa **SLO latency, tính đúng đắn và tài nguyên**, không phải luôn là phương án có SQL count nhỏ nhất.

## 20. Thiết lập kiểm thử hồi quy N+1

Một integration test có thể thất bại khi một thay đổi mapping làm số SQL tăng theo N. Nếu dùng Hibernate statistics:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

// Chạy ở môi trường test riêng, Hibernate statistics đã được bật.
@Test
void listOrdersShouldNotExecuteOneQueryPerOrder() {
    Statistics statistics = sessionFactory.getStatistics();
    statistics.clear();

    List<OrderListItem> result =
            orderQueryService.listRecent(tenantId, 50);

    long prepared = statistics.getPrepareStatementCount();
    assertThat(result).hasSize(50);
    assertThat(prepared).isLessThanOrEqualTo(3);
}
```

Đây là **đoạn phương thức test minh họa**: `sessionFactory`, `orderQueryService`, `tenantId` và dữ liệu seed phải được fixture cung cấp. `getPrepareStatementCount()` thường là counter cấp `SessionFactory`; khi các test hoặc request khác chạy đồng thời, kết quả có thể bị nhiễu. Nếu cần số lượng **theo một request**, dùng datasource query counter gắn correlation ID/transaction hoặc công cụ proxy phù hợp.

Một test chỉ assert query count **chưa đủ**:

- Test trên N=1 không thể phát hiện số SQL tăng theo N.
- Dữ liệu quan hệ đã nằm trong cache có thể cho kết quả giả an toàn.
- Query count nhỏ nhưng một câu SQL trả khối lượng cực lớn vẫn thất bại về hiệu năng.
- Một mapper thay đổi thứ tự/scope tenant nhưng vẫn chỉ chạy hai truy vấn có thể sai dữ liệu.

Nên assert **cả số truy vấn, dữ liệu kết quả và những đặc tính quan trọng của phân trang**, đồng thời có benchmark định kỳ cho tải và kích thước gần production.

## 21. Quy trình xử lý một endpoint bị N+1

**Bước 1 — Mô tả dữ liệu API thực sự cần.** Màn hình danh sách cần chi tiết hay chỉ cần số lượng/tổng? Có quan hệ nào không được phép trả ra ngoài?

**Bước 2 — Ghi trace SQL theo request.** Đếm SELECT cha, SELECT con và nhận diện các query lặp theo một foreign key. Đo với nhiều page size.

**Bước 3 — Tìm chỗ kích hoạt I/O.** Có thể là vòng `for`, `getLines()`, mapper DTO, JSON serializer, GraphQL resolver, MyBatis nested select hoặc lazy loading trong view.

**Bước 4 — Chọn fetch plan.** DTO projection cho list; fetch join/entity graph cho detail; batch hoặc two-step fetch khi cần nạp con cho page. Không dùng fetch join collection với phân trang một cách tùy tiện.

**Bước 5 — Giữ bất biến.** Filter tenant ở từng truy vấn, xác định transaction/snapshot, xử lý quan hệ rỗng và không để output bị nhân/trùng.

**Bước 6 — Xem query plan.** Đảm bảo các truy vấn mới có index phù hợp, không tạo cartesian explosion và không chuyển hàng quá lớn.

**Bước 7 — Đo và kiểm thử hồi quy.** So latency, query count, row count, memory, pool và kết quả nghiệp vụ ở các kích thước N khác nhau.

**Bước 8 — Theo dõi sau triển khai.** Quan sát DB spans/request và cảnh báo endpoint bất ngờ phát nhiều SQL; kiểm tra p95/p99 và regression khi thêm trường quan hệ vào DTO.

## 22. Những sai lầm thường gặp

1. **“LAZY gây N+1 nên cứ dùng EAGER.”** EAGER có thể vẫn sinh secondary selects và tăng over-fetching.
2. **“Một câu JOIN luôn nhanh hơn nhiều SELECT.”** Join có thể nhân hàng, truyền nhiều bytes và tốn memory.
3. **“Có index thì N+1 hết ảnh hưởng.”** Index rút ngắn từng query, không giảm số round-trip.
4. **“Trả nguyên JPA entity cho API là tiện.”** Serializer có thể kích hoạt lazy query, lộ field và làm API phụ thuộc ORM.
5. **“Thêm JOIN FETCH cho collection trong query phân trang.”** Có thể paginate ở memory hoặc tạo kết quả không đúng kỳ vọng.
6. **“SELECT ... IN (...) luôn là một query dù N vô hạn.”** Danh sách ID lớn có giới hạn tham số, parse cost và plan; có thể cần batch.
7. **“Batch fetch size lớn nhất luôn tốt nhất.”** Có thể tăng số ID/bytes nạp thừa và làm cache/memory nặng.
8. **“Dùng entity graph thì chắc chắn chỉ một SQL.”** Cách fetch do provider thực hiện, phải đo.
9. **“Đọc danh sách parent rồi SELECT riêng child sẽ tự khởi tạo collection ORM.”** Không nhất thiết; có thể vô tình query lần nữa.
10. **“Lấy hai trang dữ liệu khác thời điểm không ảnh hưởng gì.”** Cần biết snapshot và yêu cầu nhất quán đọc.
11. **“N+1 chỉ xảy ra trong JPA.”** JDBC loop, MyBatis nested select và GraphQL resolver đều có thể gây N+1.
12. **“Warm-cache benchmark đã đủ.”** Cold cache, nhiều tenant và tải đột biến có thể bộc lộ chi phí.
13. **“Query count càng ít thì response càng đúng.”** Ít SQL nhưng thiếu dữ liệu, sai tenant hoặc phân trang sai vẫn không đạt.
14. **“Mở Open Session in View giải quyết triệt để N+1.”** Nó có thể chỉ cho phép query ẩn tiếp tục chạy trong serialization.

## 23. Bài tập tự kiểm tra

**Câu 1.** API trả 80 đơn. Một truy vấn lấy danh sách đơn, sau đó mỗi đơn tải `orderLines` bằng SELECT riêng. Có bao nhiêu truy vấn theo mô hình N+1 đơn giản? Nếu thêm hai quan hệ khác cũng tải mỗi đơn một lần thì sao?

**Câu 2.** Đổi `@OneToMany(fetch=LAZY)` sang EAGER có phải bảo đảm ORM chỉ dùng một SQL không? Vì sao?

**Câu 3.** Màn hình chỉ cần `id`, `status` và `total`. Chọn DTO projection hay fetch join toàn bộ dòng hàng sẽ hợp lý hơn, và vì sao?

**Câu 4.** Một query `LEFT JOIN FETCH o.lines` có thêm `setMaxResults(20)`. Vì sao giới hạn 20 hàng join không đồng nghĩa nhận đúng 20 đơn?

**Câu 5.** Dùng chiến lược page ID rồi fetch join theo `IN :ids`. Có được giả định kết quả thứ hai giữ thứ tự giống trang ID không?

**Câu 6.** Hibernate batch size 32 được bật. Một trang có 70 đơn và một collection lazy trên mỗi đơn. Query count có chắc bằng `1 + ceil(70/32)` không?

**Câu 7.** Hai truy vấn nạp parent và children chạy ở PostgreSQL READ COMMITTED. Một transaction khác thêm child giữa hai SELECT. Response có chắc cùng một snapshot không?

**Câu 8.** MyBatis dùng `<collection select="findLinesByOrderId">`. N+1 có thể xảy ra không dù ứng dụng không dùng JPA?

**Câu 9.** Thay N+1 bằng một câu join nhưng latency tăng và heap tăng mạnh. Nêu các nguyên nhân có thể và phép đo cần xem.

**Câu 10.** Một test kiểm tra N=1 và đếm đúng hai truy vấn. Có đủ kết luận endpoint không có N+1 không?

**Câu 11.** Dùng `JOIN FETCH` hai quan hệ collection: 15 dòng hàng và 8 sự kiện lịch sử mỗi đơn. Query join có thể tạo bao nhiêu hàng cho mỗi đơn trong trường hợp tích Descartes?

**Câu 12.** API Java đọc trang đơn theo tenant, nhưng truy vấn gom dòng hàng nhận một list ID bất kỳ từ client mà không kiểm tra tenant. Tại sao đây không chỉ là vấn đề hiệu năng?

**Gợi ý trả lời:**

1. Khoảng **81 truy vấn**; nếu có tổng ba quan hệ riêng cho mỗi đơn, khoảng `1 + 3×80 = 241`.
2. **Không.** EAGER yêu cầu nạp quan hệ nhưng provider vẫn có thể dùng secondary selects; cần đo SQL thực tế và chọn fetch plan theo use case.
3. **DTO projection** thường phù hợp: không tải dữ liệu con không cần thiết, ít object và dễ phân trang.
4. Một đơn có thể chiếm nhiều hàng join; ORM có thể paginate trong memory hoặc gặp cảnh báo/lỗi tùy provider.
5. **Không.** Phải reorder theo `pageIds` hoặc diễn đạt ORDER BY phù hợp; `IN` không tạo thứ tự.
6. **Không chắc.** Batch/cache/phiên bản provider và cách truy cập ảnh hưởng truy vấn; công thức chỉ để ước lượng.
7. **Không.** READ COMMITTED thường có snapshot theo statement; nếu cần cùng snapshot hãy xem isolation/transaction phù hợp.
8. **Có.** Nested select có thể gọi một SELECT cho mỗi phần tử cha.
9. Row explosion, truyền dữ liệu lặp, hydrate object và GC; đo actual rows, bytes, query plan, heap, p95/p99.
10. **Không.** Với N=1, N+1 cũng chỉ có hai query; phải thử N khác nhau và cold cache.
11. Có thể **15×8 = 120 hàng** cho một đơn, trước khi tính các yếu tố khác; fetch nhiều bag còn có thể bị ORM từ chối.
12. Có nguy cơ **truy cập dữ liệu chéo tenant**, không chỉ N+1. Truy vấn gom phải kiểm tra scope truy cập ở database/boundary có thẩm quyền.

## Kết luận

**N+1 là hệ quả của việc truy vấn dữ liệu liên quan theo từng phần tử**, dù code dùng JDBC, MyBatis hay JPA/Hibernate. Nó thường chỉ xuất hiện khi N tăng hoặc khi serializer/resolver chạm tới quan hệ được nạp muộn, khiến số lượt SQL, network và thời gian giữ connection tăng theo kích thước response.

Trong **DATA_PERSISTENCE_FUNDAMENTALS**, hãy chọn cách nạp dữ liệu theo mục đích: **DTO projection** cho danh sách đơn giản, **fetch join/entity graph** cho chi tiết có phạm vi nhỏ, **batch fetching** để giảm round-trip với lazy relationship, hoặc **phân trang parent trước rồi nạp children theo tập ID** khi cần hiển thị nhiều đơn và nhiều dòng hàng. Sau mỗi thay đổi, kiểm tra không chỉ SQL count mà còn **số hàng, query plan, bộ nhớ, phân trang, tenant scope, snapshot consistency và p95/p99**. Tối ưu persistence chỉ thực sự thành công khi hệ thống vừa nhanh hơn vừa giữ nguyên tính đúng đắn của dữ liệu.
