# Tránh nhân dữ liệu khi tải nhiều quan hệ tập hợp

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Hiệu năng

Một ứng dụng JPA có thể giảm số câu SQL từ hàng trăm xuống chỉ còn một câu bằng cách sử dụng `JOIN FETCH`. Tuy nhiên, **ít SQL hơn không đồng nghĩa ít dữ liệu truyền hơn hoặc nhanh hơn**. Khi một entity cha có nhiều quan hệ tập hợp độc lập — chẳng hạn `PurchaseOrder.lines` và `PurchaseOrder.shipments` — việc fetch join đồng thời hai tập hợp có thể tạo ra **phép nhân số hàng kết quả** (*row multiplication*, thường được gọi là *Cartesian product* giữa các collection con theo mỗi cha).

Ví dụ một đơn hàng chứa **10 dòng hàng** và **8 kiện giao**, query nối cả hai tập hợp có thể tạo **80 hàng SQL** cho đúng **1 đơn hàng**, **10 dòng hàng** và **8 kiện giao**. Nếu tải 100 đơn hàng có cấu trúc tương tự, database có thể phải xử lý/truyền khoảng **8.000 hàng**, thay vì lượng dữ liệu logic chỉ gồm 100 đơn hàng + 1.000 dòng hàng + 800 kiện giao.

Ở Hibernate, còn một lỗi quan trọng: fetch đồng thời nhiều collection được ánh xạ theo **bag semantics** có thể gây `MultipleBagFetchException`. Dù tránh được lỗi bằng mapping kiểu Set hoặc indexed List, **phép nhân số hàng vẫn tồn tại**; việc đổi kiểu collection không tự chữa vấn đề hiệu năng.

Bài này hướng dẫn cách nhận diện, đo lường và giải quyết các vấn đề ấy trong JPA/Hibernate, đặc biệt khi kết hợp với **phân trang, DTO projection, batch fetching, subselect fetching và việc tải nhiều query trong cùng persistence context**.

Các ví dụ dựa trên Jakarta Persistence (`jakarta.persistence.*`), JPQL và một số extension của Hibernate ORM. Khi hành vi phụ thuộc Hibernate version, bài sẽ ghi rõ thay vì khẳng định đó là bảo đảm portable của JPA.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **N+1 query problem** với **row multiplication khi JOIN FETCH nhiều collections**.
2. Giải thích vì sao hai quan hệ `@OneToMany` độc lập tạo số hàng gần bằng tích số phần tử.
3. Ước lượng số SQL rows trước khi chọn fetch plan.
4. Phân biệt số **hàng SQL** với số **Java entity instances** và số phần tử collection.
5. Hiểu vì sao `DISTINCT` có thể khử entity references trùng trong result list nhưng không xóa chi phí SQL JOIN.
6. Phân biệt Hibernate `MultipleBagFetchException` với bản thân row explosion.
7. Hiểu bag, Set, List có order column và giới hạn của từng lựa chọn.
8. Biết tại sao không nên đổi `List` sang `Set` chỉ để “làm biến mất exception”.
9. Sử dụng `JOIN FETCH` một collection kết hợp với secondary queries cho collection còn lại.
10. Tận dụng first-level cache/persistence context để kết hợp những lần tải của cùng entity cha.
11. Thiết kế phương án **lấy trang ID trước rồi tải đồ thị sau**.
12. Giữ thứ tự phân trang đúng khi query thứ hai dùng `WHERE id IN :ids`.
13. Tránh fetch-join collection trực tiếp với `setFirstResult`/`setMaxResults` mà không hiểu giới hạn.
14. Hiểu cấu hình Hibernate `hibernate.query.fail_on_pagination_over_collection_fetch`.
15. Giải thích `@BatchSize`, `hibernate.default_batch_fetch_size` và trade-off của batch fetching.
16. Hiểu Hibernate `@Fetch(FetchMode.SUBSELECT)` và giới hạn memory/session scope.
17. Phân biệt `@EntityGraph` và `JOIN FETCH` về mục tiêu fetch plan so với số SQL rows.
18. Sử dụng DTO projections và nhiều truy vấn phẳng để tránh nhân dữ liệu.
19. Tránh N+1 khi dựng response DTO chứa nhiều collection.
20. Dùng `EXISTS` để lọc parent theo child mà không làm nở parent rows không cần thiết.
21. Hiểu tác động của `@ManyToOne`, các quan hệ đơn trị và chuỗi quan hệ lồng nhau.
22. Đo số SQL statements, số rows, bytes transferred, entity loads và latency thay vì chỉ đo thời gian.
23. Viết integration test có fixture kiểm tra số child records sau khi tải.
24. Nhận diện rủi ro do dirty collection, duplicate objects và `equals/hashCode` khi dùng `Set`.
25. Thiết kế fetch plan phù hợp với endpoint list, endpoint detail, report và export.
26. Nhận biết khi nào dùng aggregate queries, pagination hoặc mô hình đọc chuyên dụng thay vì tải cả object graph.
27. Đánh giá mức độ nhất quán giữa nhiều queries trong một transaction.
28. Phân biệt entity graph loading với nhu cầu lấy toàn bộ dữ liệu thật sự của API.

---

## 2. Mô hình ví dụ: một đơn hàng, hai tập hợp độc lập

Giả sử domain:

```text
                  PurchaseOrder
                  id, code, status
                     /      \
                    /        \
                   v          v
              OrderLine     Shipment
              id, sku       id, trackingNo
              quantity      carrier
```

Quan hệ:

- Một `PurchaseOrder` có nhiều `OrderLine`.
- Một `PurchaseOrder` có nhiều `Shipment`.
- Mỗi `OrderLine` thuộc đúng một `PurchaseOrder`.
- Mỗi `Shipment` thuộc đúng một `PurchaseOrder`.
- `OrderLine` và `Shipment` **không có tương ứng một-một theo vị trí**. Ví dụ line #1 không gắn độc quyền với shipment #1.

Điều cuối là trọng tâm. Hai tập hợp này là **hai chiều độc lập**, nên một JOIN trên cả hai buộc SQL tạo từng kết hợp `(line, shipment)` cho mỗi order.

### 2.1. Một bộ dữ liệu nhỏ

```text
PurchaseOrder #42: PO-2026-042

OrderLine:
  L1: SKU-A, qty=2
  L2: SKU-B, qty=1
  L3: SKU-C, qty=4

Shipment:
  S1: DHL, tracking=DH-001
  S2: UPS, tracking=UP-002
  S3: DHL, tracking=DH-003
  S4: VNPOST, tracking=VN-004
```

Dữ liệu nghiệp vụ có **1 Order + 3 Lines + 4 Shipments = 8 đối tượng logic**.

Nếu SQL JOIN đồng thời hai tập hợp, số hàng kết quả không phải 8.

---

## 3. Phép nhân hàng SQL xuất hiện thế nào?

Một phép nối minh họa:

```sql
SELECT
    o.id AS order_id,
    o.code,
    l.id AS line_id,
    l.sku,
    s.id AS shipment_id,
    s.tracking_no
FROM purchase_orders AS o
LEFT JOIN order_lines AS l
       ON l.order_id = o.id
LEFT JOIN shipments AS s
       ON s.order_id = o.id
WHERE o.id = 42
ORDER BY l.id, s.id;
```

Các hàng:

| Order | Line | Shipment |
|---|---|---|
| #42 | L1 | S1 |
| #42 | L1 | S2 |
| #42 | L1 | S3 |
| #42 | L1 | S4 |
| #42 | L2 | S1 |
| #42 | L2 | S2 |
| #42 | L2 | S3 |
| #42 | L2 | S4 |
| #42 | L3 | S1 |
| #42 | L3 | S2 |
| #42 | L3 | S3 |
| #42 | L3 | S4 |

**12 hàng SQL**, vì:

\[
3\ \text{lines} \times 4\ \text{shipments} = 12\ \text{rows}
\]

Các cột của Order được lặp 12 lần; mỗi Line xuất hiện 4 lần; mỗi Shipment xuất hiện 3 lần.

### 3.1. Vì sao gọi là Cartesian product?

Với mỗi order, `order_lines` và `shipments` được nối độc lập qua `order_id`. Về mặt tổ hợp, mỗi Line kết hợp với mỗi Shipment thuộc order đó. Đây không phải lỗi SQL optimizer; SQL làm đúng quan hệ JOIN đã yêu cầu.

### 3.2. Không có child nào thì sao?

Với `LEFT JOIN`, nếu một collection rỗng thì vẫn có một nhóm NULL được dùng để giữ parent. Với một parent có:

- 0 Lines, 4 Shipments: thường 4 rows.
- 3 Lines, 0 Shipments: thường 3 rows.
- 0 Lines, 0 Shipments: thường 1 row.
- 3 Lines, 4 Shipments: 12 rows.

Có thể ước lượng:

\[
R_{\text{parent}} \approx
\max(1,\lvert Lines\rvert)
\cdot
\max(1,\lvert Shipments\rvert)
\]

Công thức này xét hai **LEFT JOINs đơn giản, độc lập**, không thêm bộ lọc, DISTINCT, aggregation hay quan hệ phức tạp khác.

### 3.3. Cùng tổng số child entities nhưng chi phí khác nhau

| Lines | Shipments | Hai LEFT JOINs | Tổng child objects |
|---:|---:|---:|---:|
| 1 | 1 | 1 row | 2 |
| 3 | 4 | 12 rows | 7 |
| 10 | 8 | 80 rows | 18 |
| 100 | 100 | 10.000 rows | 200 |
| 1.000 | 50 | 50.000 rows | 1.050 |

**Tăng tuyến tính trong từng collection nhưng tăng theo tích khi JOIN cả hai.**

---

## 4. Chi phí không chỉ nằm ở số Java objects

Một Hibernate persistence context có identity map, vì vậy một entity có ID #42 được materialize thành một managed instance phù hợp trong context. Điều này không khiến database khỏi tạo/truyền các JOIN rows.

### 4.1. Tách ba đại lượng

1. **SQL result rows:** số dòng trả ra trên JDBC result set.
2. **Entity instances:** số entities thực tế được quản lý bởi persistence context.
3. **Collection members:** số phần tử logic trong `lines` và `shipments`.

Khi JOIN hai tập hợp:

```text
SQL result rows:    12
Unique Order:        1
Unique OrderLines:   3
Unique Shipments:    4
```

Nếu provider xử lý trùng lặp phù hợp mapping, result graph có thể đúng về số entities nhưng vẫn chịu toàn bộ chi phí xử lý 12 rows.

### 4.2. Các nguồn chi phí

- Database phải đọc/join/sắp xếp/hash rows theo execution plan.
- JDBC driver nhận thêm rows và bytes.
- Giá trị của parent bị lặp, kể cả các cột dài.
- ORM phải đọc từng row, so sánh entity keys và dựng association state.
- Bộ nhớ tạm chứa row buffers, collection loading state và kết quả.
- Network/serialization cost tăng.
- GC pressure và CPU xử lý hydration có thể tăng.
- Khi nhiều orders được xử lý, độ trễ request có thể tăng khó lường.

### 4.3. Vì sao SQL statement count có thể đánh lừa?

Một request với **1 SQL SELECT tải 100.000 rows** có thể nặng hơn một request với **3 SQL SELECT tổng cộng 2.000 rows**.

Mục tiêu không phải **ít câu SQL nhất**, mà là **đúng dữ liệu, đúng mức consistency, với tổng chi phí chấp nhận được**.

---

## 5. N+1 và row multiplication là hai đầu của bài toán fetch

### 5.1. N+1

Một query lấy N orders:

```jpql
SELECT o FROM PurchaseOrder o
ORDER BY o.id
```

Sau đó:

```java
for (PurchaseOrder order : orders) {
    order.getLines().size();
}
```

Nếu các collections LAZY và không có batch/cache optimization, có thể phát thêm N SELECT tải Lines.

```text
1 SELECT orders
N SELECT order_lines by order_id
--------------------------------
N+1 statements
```

### 5.2. Join-fetch nhiều tập hợp

Người phát triển phản ứng bằng cách fetch tất cả:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
LEFT JOIN FETCH o.shipments
```

Số SELECT có thể giảm, nhưng:

- SQL rows tăng theo tích của collection sizes.
- Hibernate có thể từ chối khi cả hai là bags.
- Phân trang collection fetch có thể trở nên sai/chạy trong memory.

### 5.3. Cần tìm phương án giữa hai cực

Giải pháp thường tốt hơn:

```text
1 SELECT page orders
1 SELECT lines for those order IDs
1 SELECT shipments for those order IDs
--------------------------------------
3 SQL queries, không tạo phép nhân lines × shipments
```

Hoặc batch/subselect fetching giảm số SELECT mà không cần JOIN tất cả.

---

## 6. Entity mẫu: PurchaseOrder

Các ví dụ tiếp theo dùng một entity mapping đơn giản.

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String code;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "status", nullable = false)
    private String status;

    @Version
    private long version;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<Shipment> shipments = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getCode() { return code; }
    public Instant getCreatedAt() { return createdAt; }
    public String getStatus() { return status; }
    public List<OrderLine> getLines() { return lines; }
    public List<Shipment> getShipments() { return shipments; }
    public long getVersion() { return version; }
}
```

Với Hibernate và mapping `List` không có persistent order index, các collections có thể có **bag semantics**. Tên Java type `List` không tự bảo đảm Hibernate lưu thứ tự trong database.

### 6.1. OrderLine

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}

    public Long getId() { return id; }
    public PurchaseOrder getOrder() { return order; }
    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
}
```

### 6.2. Shipment

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "shipments")
public class Shipment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "tracking_no", nullable = false)
    private String trackingNumber;

    protected Shipment() {}

    public Long getId() { return id; }
    public PurchaseOrder getOrder() { return order; }
    public String getTrackingNumber() { return trackingNumber; }
}
```

### 6.3. Ai sở hữu quan hệ?

Ở cả hai collections, `mappedBy = "order"` chỉ ra phía child có `@ManyToOne order` và foreign key. Trong demo, chúng ta tập trung vào đọc; nếu xây đầy đủ API tạo order/line/shipment, cần helper methods để giữ hai chiều in-memory nhất quán và transaction/`cascade` phù hợp.

### 6.4. Những ví dụ cần dữ liệu fixture

Mẫu code entity không có constructor public để tự thêm child trong từng snippet; fixture có thể tạo bằng repository factory, test builders, SQL setup hoặc constructor domain thích hợp trong dự án thật. Phần performance không phụ thuộc vào cách seed dữ liệu cụ thể.

---

## 7. DDL logic và index nền

Một schema minh họa:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_code VARCHAR(80) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    status VARCHAR(40) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);

CREATE TABLE shipments (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    tracking_no VARCHAR(120) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);

CREATE INDEX idx_order_lines_order_id
    ON order_lines(order_id);

CREATE INDEX idx_shipments_order_id
    ON shipments(order_id);

CREATE INDEX idx_orders_status_created_id
    ON purchase_orders(status, created_at, id);
```

DDL không bao gồm cách sinh ID cụ thể; provider/DBMS có thể sử dụng IDENTITY/sequence theo dialect. Index trên FK giúp các query `WHERE order_id IN (...)` và JOIN theo parent ID, nhưng **không làm phép nhân kết quả biến mất**.

### 7.1. Index có thể cải thiện I/O, không thay số kết hợp logic

Ngay cả khi mỗi bảng con có index tốt, với 3 Lines × 4 Shipments query vẫn có 12 combinations. Optimizer có thể thực thi nhanh hơn nhưng không thể biến một kết quả gồm 12 tuples khác nhau thành 7 rows mà vẫn giữ đầy đủ projection gốc.

---

## 8. JOIN FETCH một collection: khi nào hợp lý?

JPQL:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :id
```

Nếu Order #42 có 3 Lines, SQL result thường có khoảng 3 rows đối với parent này.

Đây là cách hữu ích để tải một aggregate phần cần thiết khi số child nhỏ và một query detail fetch có giới hạn.

### 8.1. Vì sao SELECT DISTINCT o?

JPQL `DISTINCT` yêu cầu khử duplicate entity results theo query semantics. Một `LEFT JOIN FETCH o.lines` có thể khiến mỗi parent xuất hiện trên nhiều SQL rows. `DISTINCT` giúp thể hiện rõ mong muốn mỗi Order chỉ xuất hiện một lần trong result list.

Các Hibernate versions khác nhau xử lý duplicate root entity references theo những chi tiết khác nhau. Với Hibernate 6, duplicate root entity references do join fetching có thể được loại tự động trong memory; `DISTINCT` không phải luôn cần chỉ để giải quyết duplicate roots. Tuy nhiên, **không phiên bản nào tự loại chi phí SQL rows đã được JOIN**.

### 8.2. Một-to-one hoặc many-to-one thường an toàn hơn

`LEFT JOIN FETCH o.customer` với mỗi Order chỉ có tối đa một Customer không nhân số rows Order lên theo chiều Customer. Fetch join nhiều **to-one** associations thường ít nguy cơ bùng nổ số rows hơn nhiều **to-many** collections, dù vẫn tăng kích thước mỗi SQL row.

### 8.3. Không phải mọi to-many JOIN FETCH đều xấu

Một Order có tối đa 3 Lines và endpoint chỉ tải 1 Order có thể rất hợp lý để join fetch. Vấn đề nằm ở **cardinality**, số tập hợp độc lập, số parent và row width.

---

## 9. JOIN FETCH hai collections: lỗi thiết kế hiệu năng

Một query hấp dẫn:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
LEFT JOIN FETCH o.shipments
WHERE o.id = :id
```

Có hai vấn đề tách biệt:

1. **Row multiplication**: dữ liệu quan hệ SQL phình theo tích.
2. **Bag semantics**: với Hibernate, nhiều bag fetches trong cùng query có thể bị từ chối.

### 9.1. Hai vấn đề không phải một

Nếu đổi mapping để Hibernate chấp nhận query, SQL có thể vẫn trả 12 rows cho 3 × 4. Nếu query bị `MultipleBagFetchException`, bạn chưa quan sát row multiplication vì Hibernate có thể từ chối từ giai đoạn xây query plan; nhưng nguy cơ về cardinality vẫn là lý do quan trọng để đổi fetch plan.

### 9.2. Vì sao `DISTINCT` chưa đủ?

Ngay cả với SQL:

```sql
SELECT DISTINCT
    o.id,
    o.code,
    l.id,
    l.sku,
    s.id,
    s.tracking_no
...
```

các tuples `(o,L1,S1)` và `(o,L1,S2)` **khác nhau ở s.id**, nên DISTINCT không loại chúng.

### 9.3. Bảng tổng hợp cho 100 orders

Giả sử mỗi order có 10 Lines và 8 Shipments:

| Cách tải | Số SQL queries | Rows quan hệ ước lượng |
|---|---:|---:|
| JOIN FETCH hai collections | 1 | ~8.000 |
| Query Orders, query Lines, query Shipments | 3 | ~100 + 1.000 + 800 = 1.900 |
| Join Orders–Lines, query Shipments riêng | 2 | ~1.000 + 800 = 1.800 |
| LAZY từng order không batch | ~201 | ~1.900, nhưng nhiều round trips |

Các con số là ví dụ đơn giản, bỏ qua các JOIN của to-one relations, filtering và provider-specific extra loads. Chúng minh họa rằng **2–3 queries có thể vận chuyển ít dữ liệu hơn 1 query**.

---

## 10. MultipleBagFetchException trong Hibernate

Khi hai `List` được Hibernate ánh xạ như bags, query fetch cả hai có thể dẫn tới:

```text
org.hibernate.loader.MultipleBagFetchException:
cannot simultaneously fetch multiple bags
```

Cách wrap thành exception ở JPA/Spring và stack trace khác nhau theo Hibernate version.

### 10.1. “Bag” là gì?

Bag là collection có thể có phần tử trùng và **không có persistent collection index đủ để phân biệt vị trí**. Một Java `List` không khai báo `@OrderColumn` trong nhiều cấu hình Hibernate thường là bag.

`@OrderBy` chỉ chỉ định thứ tự SQL khi load, **không nhất thiết biến bag thành indexed List có position key**. Đừng coi `@OrderBy` là cách sửa mọi MultipleBagFetchException.

### 10.2. Vì sao ORM gặp khó?

Khi SQL rows bị nhân chéo, mỗi Line và mỗi Shipment lặp lại nhiều lần. Với bags không có index/identity semantics phù hợp cho từng phần tử theo collection model, việc khôi phục đúng contents mà không vô tình chèn duplicates không đơn giản.

### 10.3. Hai phương án đúng về ý nghĩa

- **Tối ưu fetch plan**: tải mỗi to-many collection bằng query riêng hoặc batching; đây thường là phương án ưu tiên.
- **Thay collection semantics có lý do nghiệp vụ**: nếu quan hệ thực sự là Set hoặc indexed List, map như vậy. Tuy nhiên phải vẫn kiểm soát row multiplication.

Không chuyển `List` thành `Set` chỉ để Hibernate “hết báo lỗi” mà không xét equality, ordering và side effects.

---

## 11. Vì sao đổi List thành Set không phải thuốc chữa?

Có thể thấy một đề xuất:

```java
@OneToMany(mappedBy = "order")
private Set<OrderLine> lines = new HashSet<>();

@OneToMany(mappedBy = "order")
private Set<Shipment> shipments = new HashSet<>();
```

Nếu semantics hợp lệ, Hibernate có thể xử lý multiple set fetch joins khác multiple bags. Nhưng:

- JOIN vẫn có tối đa `lines × shipments` rows.
- Set không giữ thứ tự List theo hợp đồng thông thường.
- `equals/hashCode` của entity phải được thiết kế cẩn trọng.
- Với generated IDs, equality/hashCode sai có thể làm Set mất phần tử hoặc thay đổi behavior sau persist.
- Memory/hash computation có chi phí.
- Nếu domain cần duplicate elements hoặc thứ tự cố định, Set thay đổi ý nghĩa.
- Hibernate/provider vẫn có thể phát SQL lớn dù Java collections không có duplicates.

### 11.1. Khi Set là đúng

Một relationship thể hiện tập các memberships duy nhất, không có vị trí và domain logic dựa trên uniqueness có thể phù hợp Set.

### 11.2. Khi List là đúng

Một collection có thứ tự nghiệp vụ (ví dụ lines theo vị trí hiển thị) có thể cần indexed List với `@OrderColumn` hoặc field `lineNumber`. Tuy nhiên order column có thể thêm chi phí UPDATE khi reorder và đòi hỏi mapping ownership đúng.

### 11.3. Khi không cần đổi collection

Nếu chỉ cần chặn fetch explosion, **tách query** hiệu quả hơn và ít thay đổi domain semantics hơn.

---

## 12. @OrderColumn không đồng nghĩa tối ưu fetch

Một List có thể được ánh xạ với persistent index:

```java
@OneToMany
@OrderColumn(name = "line_position")
private List<OrderLine> lines;
```

Đây là ví dụ cấu trúc ý tưởng, cần ánh xạ owner/join column/join table cụ thể. Không nhất thiết dùng nguyên annotation này với quan hệ `mappedBy` trong ví dụ ở phần 6 mà không kiểm tra mapping.

### 12.1. Vai trò @OrderColumn

Nó cho provider biết vị trí phần tử trong List ở persistent storage. Đây là semantics khác bag không thứ tự.

### 12.2. Các trade-offs

- Reorder có thể cập nhật nhiều row positions.
- Database cần lưu thêm index column.
- SQL JOIN hai indexed Lists vẫn có multiplication.
- Cần nhất quán với business sorting/pagination của child entities.

### 12.3. @OrderBy khác @OrderColumn

`@OrderBy("lineNumber ASC")` dùng thứ tự theo attribute; `@OrderColumn` lưu thứ tự vị trí của List như persistent index. Hai khái niệm không đồng nghĩa và không phải đều sửa được MultipleBagFetchException.

---

## 13. DISTINCT ở JPQL và DISTINCT ở SQL

Xét một query:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
LEFT JOIN FETCH o.shipments
WHERE o.id = :id
```

### 13.1. DISTINCT trong kết quả entity

JPA `DISTINCT` diễn đạt không muốn duplicate root entities trong query result. Khi result graph đã được materialize, cùng Order identity có thể xuất hiện qua nhiều rows.

### 13.2. DISTINCT không làm thay đổi JOIN multiplicity

Ngay cả nếu provider pass DISTINCT xuống SQL, các rows có child columns khác nhau vẫn không giống nhau. Không thể kỳ vọng `DISTINCT` giảm 80 rows về 1 mà vẫn fetch đủ 10 Lines và 8 Shipments từ cùng query.

### 13.3. Hibernate 5 và Hibernate 6 khác nhau về duplicate root handling

Ở Hibernate 6, duplicate root entity references do JOIN FETCH được tự động loại trong memory theo cơ chế query processing. Ở các versions trước có các thực hành `SELECT DISTINCT` và hints liên quan việc pass-through DISTINCT. Không copy các hints/version-specific workarounds cũ vào Hibernate mới mà chưa kiểm tra tài liệu của version đang dùng.

### 13.4. Đừng đo hiệu quả bằng `result.size()`

`result.size() == 1` không nói gì về số JDBC rows database đã trả. Đo rows/bytes/CPU/SQL execution plan để nhìn thấy vấn đề thật.

---

## 14. Giải pháp 1: JOIN FETCH một collection, tải collection còn lại riêng

Với Order detail, một chiến lược thực tế:

1. Query Order + Lines.
2. Trong cùng EntityManager, query Order + Shipments.
3. Trả về cùng managed Order instance với cả hai collections được initialized.

JPQL:

```java
PurchaseOrder order = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    WHERE o.id = :id
    """,
    PurchaseOrder.class
).setParameter("id", orderId)
 .getSingleResult();

em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.shipments
    WHERE o.id = :id
    """,
    PurchaseOrder.class
).setParameter("id", orderId)
 .getResultList();
```

### 14.1. Vì sao query thứ hai có thể bổ sung vào cùng object?

JPA persistence context quản lý entity identity. Nếu Order#42 đã managed, việc provider materialize lại cùng entity identity theo query thứ hai dùng cùng persistence context sẽ tham chiếu cùng managed entity; fetch join có thể initialize `shipments` của instance đó.

### 14.2. Không clear giữa hai queries

Nếu gọi `em.clear()` sau query thứ nhất, Order trở thành detached và query thứ hai có thể trả một instance managed khác; code không còn đơn giản ghép hai collections vào cùng object như dự kiến.

### 14.3. Chỉ dùng một persistence context/transaction phù hợp

Code ví dụ phải chạy trong cùng persistence context. Với Spring, thường đặt tại service method `@Transactional(readOnly=true)` hoặc một transaction boundary tương ứng; không tự động chia mỗi repository call sang một EntityManager khác khi logic dựa trên identity map.

### 14.4. Chi phí số rows

Với 3 Lines và 4 Shipments:

```text
Query 1: ~3 rows
Query 2: ~4 rows
Total:   ~7 rows
```

Thay vì một query ~12 rows. Cùng dùng 2 SQL, nhưng rows không bị nhân.

### 14.5. Có cần query thứ hai trả result list?

Ở phương án này, query được thực thi để fetch collection; nếu Order#42 tồn tại, its managed state được bổ sung. Dù code không giữ danh sách kết quả thứ hai, phải bảo đảm query chạy hoàn tất trong context trước khi sử dụng/serialize graph.

---

## 15. Giải pháp 2: lấy parent IDs của trang trước, rồi fetch collections

Đây là phương án quan trọng cho endpoint list với pagination.

Ví dụ yêu cầu:

```http
GET /orders?status=PAID&page=2&size=20
```

### 15.1. Bước 1: query chỉ IDs để phân trang

```java
List<Long> orderIds = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.status = :status
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    Long.class
)
.setParameter("status", "PAID")
.setFirstResult(page * pageSize)
.setMaxResults(pageSize)
.getResultList();
```

Phân trang lúc này hoạt động ở **parent rows**, không phải rows đã bị nhân bởi collection JOIN.

### 15.2. Bước 2: kiểm tra trang rỗng

```java
if (orderIds.isEmpty()) {
    return List.of();
}
```

Đừng thực hiện `WHERE o.id IN :ids` khi danh sách rỗng rồi giả định mọi provider/DBMS chấp nhận `IN ()`.

### 15.3. Bước 3: fetch Lines cho đúng parents

```java
List<PurchaseOrder> ordersWithLines =
    em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        LEFT JOIN FETCH o.lines
        WHERE o.id IN :ids
        """,
        PurchaseOrder.class
    )
    .setParameter("ids", orderIds)
    .getResultList();
```

### 15.4. Bước 4: fetch Shipments riêng

```java
em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.shipments
    WHERE o.id IN :ids
    """,
    PurchaseOrder.class
)
.setParameter("ids", orderIds)
.getResultList();
```

### 15.5. Bước 5: phục hồi thứ tự trang

SQL `WHERE id IN (...)` không bảo đảm trả đúng thứ tự của `orderIds`. Giữ order bằng Java:

```java
Map<Long, PurchaseOrder> byId =
    ordersWithLines.stream()
        .collect(Collectors.toMap(
            PurchaseOrder::getId,
            Function.identity()
        ));

List<PurchaseOrder> ordered =
    orderIds.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();
```

Imports:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;
```

Nếu dữ liệu không đổi và không có filters khác giữa hai phases, mọi ID từ bước 1 phải có parent tương ứng. `filter(Objects::nonNull)` chỉ là defensive behavior cho trường hợp concurrent deletion; trong production cần quyết định **retry, trả thiếu, snapshot consistency hay error** thay vì âm thầm trả thiếu trang nếu contract yêu cầu stable page.

### 15.6. Phức tạp thêm nhưng an toàn cho pagination

Phương án cần khoảng ba queries theo page (IDs, Lines fetch, Shipments fetch) nhưng không nhân rows giữa tập hợp con. Đây là đánh đổi tốt cho nhiều workloads.

---

## 16. Vì sao query fetch thứ hai không được quyết định pagination?

Không đặt:

```java
.setFirstResult(20)
.setMaxResults(20)
```

trên query `LEFT JOIN FETCH o.lines` và mong “20 đơn hàng”. Limit SQL rows có thể cắt giữa collection của một Order.

### 16.1. Ví dụ

Một Order đầu có 100 Lines. SQL `LIMIT 20` trên join rows có thể chỉ chứa 20/100 Lines. Nếu provider coi collection đã initialized từ phần này, có nguy cơ một graph không đầy đủ; vì thế các ORMs thường không áp SQL row pagination đơn giản khi fetch collections.

### 16.2. Hibernate có thể phân trang trong memory

Trong một số trường hợp Hibernate nhận ra pagination kết hợp collection fetch và phải tải toàn bộ matching result rows rồi áp pagination ở memory. Điều này có thể rất tốn bộ nhớ/độ trễ, dù API chỉ xin `size=20`.

### 16.3. Fail fast thay vì trả về performance bất ngờ

Có thể cấu hình Hibernate:

```properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Khi query cố phân trang trên collection fetch không hỗ trợ như mong muốn, Hibernate có thể báo lỗi thay vì silently thực thi pagination trong memory. Đây là property của Hibernate, kiểm tra tên/behavior theo version đang dùng.

### 16.4. Cách đúng thường là parent IDs trước

Phân trang parent IDs (hoặc keyset) rồi fetch graph của đúng IDs, như phần 15. Không cố chữa bằng việc thêm `DISTINCT` vào paginated fetch join.

---

## 17. Lọc parent theo child mà không làm nhân rows vô ích

Ví dụ tìm các Order có ít nhất một Line SKU `"JAVA-BOOK"`.

Một query dùng JOIN:

```jpql
SELECT DISTINCT o.id
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku = :sku
ORDER BY o.id
```

Nếu một Order có nhiều Lines cùng SKU, JOIN có thể trả cùng Order ID nhiều lần trước DISTINCT.

### 17.1. Dùng EXISTS khi chỉ cần xét điều kiện

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku = :sku
)
ORDER BY o.id
```

`EXISTS` diễn đạt đúng câu hỏi “có ít nhất một child khớp không?” mà không yêu cầu join all matching child rows vào top-level result.

### 17.2. Kết hợp pagination

```java
List<Long> ids = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.status = :status
      AND EXISTS (
          SELECT l.id
          FROM OrderLine l
          WHERE l.order = o
            AND l.sku = :sku
      )
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    Long.class
)
.setParameter("status", "PAID")
.setParameter("sku", "JAVA-BOOK")
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

Sau đó fetch collections cho IDs như phần trước.

### 17.3. Khi cần lọc child collection được fetch

Đừng mặc định rằng `JOIN FETCH` với điều kiện ở WHERE trên child sẽ trả **đầy đủ collection**. Nó có thể chỉ giữ child rows thỏa điều kiện trong kết quả, gây hiểu nhầm collection đã được initialized với tập con.

Nếu nghiệp vụ cần vừa lọc parent theo một child predicate **vừa lấy toàn bộ children**, dùng `EXISTS` để lọc parent rồi fetch collection độc lập.

---

## 18. Tách query nhưng giữ đúng ranh giới transaction

Với nhiều queries, dữ liệu có thể thay đổi giữa các bước.

```text
T1: Query parent IDs [42, 43]
T2: Transaction khác thêm một Shipment cho Order#42, commit
T3: Query Lines
T4: Query Shipments
```

Dưới một số isolation levels, response có thể phản ánh trạng thái ở các thời điểm khác nhau.

### 18.1. Đừng hứa snapshot consistency từ @Transactional(readOnly=true)

Spring `@Transactional(readOnly=true)` chủ yếu là hint/cấu hình transaction phù hợp stack; không tự nâng isolation thành REPEATABLE READ hoặc SERIALIZABLE. Consistency phụ thuộc DBMS, transaction settings và concurrency.

### 18.2. Chọn freshness contract theo endpoint

- Dashboard gần thời gian thực có thể chấp nhận một snapshot không tuyệt đối.
- Trang chi tiết đơn hàng dùng để thực hiện thanh toán có thể cần version/lock hoặc transaction-level consistency.
- Export tài chính có thể cần stable snapshot hoặc một reporting job.
- API pagination nhiều trang chịu concurrent inserts/updates cần keyset/snapshot strategy.

### 18.3. Một query lớn cũng không tự là giải pháp mọi consistency issue

JOIN FETCH một query không đảm bảo toàn bộ workflow nhiều requests có cùng snapshot. Đúng consistency cần thiết kế transaction và concurrency policy, không chỉ chọn một câu SQL.

---

## 19. Giải pháp 3: LAZY collections kết hợp batch fetching

Khi số Orders mỗi trang vừa phải và không muốn viết explicit fetch queries cho mọi associations, Hibernate hỗ trợ **batch fetching**.

Ví dụ:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@org.hibernate.annotations.BatchSize(size = 32)
private List<OrderLine> lines;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@org.hibernate.annotations.BatchSize(size = 32)
private List<Shipment> shipments;
```

### 19.1. Cơ chế khái niệm

Thay vì:

```text
SELECT lines WHERE order_id=1
SELECT lines WHERE order_id=2
...
SELECT lines WHERE order_id=20
```

Hibernate có thể batch collection loads:

```sql
SELECT *
FROM order_lines
WHERE order_id IN (1,2,...,20);
```

Nhờ đó, truy cập LAZY collections của nhiều Orders trong cùng persistence context có thể cần ít SELECT hơn.

### 19.2. BatchSize không biến collections thành EAGER

Nó chỉ thay **cách tối ưu loading khi collection được truy cập** theo mechanism Hibernate. Không cần fetch mọi collection ở mọi endpoint.

### 19.3. Có thể cấu hình toàn cục

```properties
hibernate.default_batch_fetch_size=32
```

Đây là property Hibernate, không thuộc JPA standard. Config có thể được áp vào proxies/collections theo mapping/version. Nên đo SQL thật và điều chỉnh batch size theo workload.

### 19.4. Chi phí và giới hạn

- Batch size lớn tạo `IN` lists dài; có giới hạn placeholders/bind parameters theo DBMS.
- Nếu persistence context có rất nhiều entities, batch fetch target có thể khác trực giác.
- Số SQL statements vẫn phụ thuộc số owners/size/batch strategy.
- Nếu ứng dụng truy cập collections ngoài transaction/persistence context, LAZY loading có thể fail; batch size không chữa `LazyInitializationException`.

### 19.5. Khi nào phù hợp?

Endpoint page 20–100 parents, cần đọc một vài collections tùy điều kiện và không muốn JOIN fetch nhiều tập hợp có thể rất phù hợp để benchmark.

---

## 20. Batch fetching và N+1: cách đo

Giả sử 50 Orders, mỗi Order có Lines/Shipments.

Không batch:

```text
1 SELECT orders
50 SELECT lines
50 SELECT shipments
-------------------
~101 SQL statements
```

Batch size 25, access trong cùng context:

```text
1 SELECT orders
~2 SELECT batched lines
~2 SELECT batched shipments
---------------------------
~5 SQL statements (illustrative)
```

Đây chỉ là **ước lượng lý tưởng**; Hibernate version, session state, loading patterns, filters và cache có thể tạo số SELECT khác. Test phải dựa vào SQL/metrics quan sát được.

### 20.1. Batching giảm round trips, không nhân các collections

Mỗi query Lines trả Lines; mỗi query Shipments trả Shipments, không tạo `Lines × Shipments` trên cùng row set.

### 20.2. Đọc thứ tự truy cập ảnh hưởng behavior

Nếu code truy cập `order.getLines()` sau khi session đã đóng, không có batch fetching. Nếu dùng nhiều EntityManagers riêng cho từng Order, cơ hội batch giảm.

### 20.3. Batch size không phải càng lớn càng tốt

Thử 16/32/64/128 với dữ liệu và DB mục tiêu. Đo bytes, query latency, parameters count và memory. Chọn theo workload, không dựa vào một con số “magic”.

---

## 21. Giải pháp 4: Hibernate SUBSELECT fetching

Một extension Hibernate:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@org.hibernate.annotations.Fetch(
    org.hibernate.annotations.FetchMode.SUBSELECT
)
private List<OrderLine> lines;
```

### 21.1. Ý tưởng

Khi một collection trên một Order được truy cập, Hibernate có thể tải collections cùng role của nhiều parent entities đã được lựa chọn trong cùng context, bằng SQL chứa subselect tương ứng với cách cha đã được lấy.

```text
SELECT orders WHERE status='PAID'
          |
          v
Access order#42.lines
          |
          v
SUBSELECT-based load lines for selected parents
          |
          v
Several orders' lines initialized
```

### 21.2. Lợi ích

Giảm N+1 của collection loading mà không JOIN đồng thời nhiều collections. Hữu ích khi cần đọc cùng một collection role trên phần lớn parents vừa được query.

### 21.3. Giới hạn

- Hibernate-specific, không portable JPA.
- Có thể tải nhiều collections hơn application thực sự cần.
- Kết quả phụ thuộc parent selection/subselect scope và persistence context.
- Không mặc định phù hợp với session chứa rất nhiều parent entities.
- Với pagination, phải kiểm tra SQL thật để biết subselect bao gồm parents nào và có ảnh hưởng đến memory/IO.
- Filter/tenant/session state có thể ảnh hưởng.

### 21.4. Batch fetch vs SUBSELECT

Batch dùng group parent IDs; subselect liên hệ selection query của parents theo cơ chế provider. Cả hai giảm số queries cho LAZY collections nhưng profile chi phí khác nhau. Chọn dựa trên SQL thực tế, không chỉ annotation.

---

## 22. Giải pháp 5: DTO projection và nhiều truy vấn phẳng

Nhiều API chỉ cần JSON summary, không cần managed entities với lifecycle/cascades/dirty checking.

Ví dụ response:

```json
{
  "id": 42,
  "code": "PO-2026-042",
  "lines": [
    {"sku": "JAVA-A", "quantity": 2},
    {"sku": "JAVA-B", "quantity": 1}
  ],
  "shipments": [
    {"trackingNumber": "TRK-001"},
    {"trackingNumber": "TRK-002"}
  ]
}
```

Thay vì tải cả entity graph, có thể query **ba tập dữ liệu phẳng** rồi group trong service.

### 22.1. DTO records

```java
package demo.dto;

public record OrderRow(
    Long id,
    String code
) {}

public record LineRow(
    Long orderId,
    Long lineId,
    String sku,
    int quantity
) {}

public record ShipmentRow(
    Long orderId,
    Long shipmentId,
    String trackingNumber
) {}
```

Các record trên là ba declarations minh họa; trong Java thật thường đặt mỗi public record ở file riêng tương ứng tên.

### 22.2. Query trang Orders

```jpql
SELECT NEW demo.dto.OrderRow(o.id, o.code)
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
```

### 22.3. Query Lines theo Order IDs

```jpql
SELECT NEW demo.dto.LineRow(
    l.order.id,
    l.id,
    l.sku,
    l.quantity
)
FROM OrderLine l
WHERE l.order.id IN :ids
ORDER BY l.order.id, l.id
```

### 22.4. Query Shipments theo Order IDs

```jpql
SELECT NEW demo.dto.ShipmentRow(
    s.order.id,
    s.id,
    s.trackingNumber
)
FROM Shipment s
WHERE s.order.id IN :ids
ORDER BY s.order.id, s.id
```

### 22.5. Ưu điểm

- Không cần Hibernate materialize entire managed graph.
- Không cần fetch join hai bags.
- Không sinh tích Line × Shipment.
- Tránh serialize lazy proxies.
- Chỉ lấy columns cần thiết.
- Dễ kiểm soát shape/size response.
- Có thể kiểm soát thứ tự child rows.

### 22.6. Lưu ý JPQL constructor expression

Tên class DTO phải đầy đủ package và constructor/record canonical constructor có types khớp query results. Nếu project dùng JPQL/JPA version có hạn chế với một kiểu expression, kiểm tra compatibility provider/version.

---

## 23. Dựng DTO graph từ ba result lists

Ví dụ:

```java
Map<Long, List<LineRow>> linesByOrder =
    lineRows.stream()
        .collect(Collectors.groupingBy(
            LineRow::orderId));

Map<Long, List<ShipmentRow>> shipmentsByOrder =
    shipmentRows.stream()
        .collect(Collectors.groupingBy(
            ShipmentRow::orderId));

List<OrderResponse> response =
    orderRows.stream()
        .map(order -> new OrderResponse(
            order.id(),
            order.code(),
            linesByOrder.getOrDefault(
                order.id(), List.of()),
            shipmentsByOrder.getOrDefault(
                order.id(), List.of())
        ))
        .toList();
```

Response type:

```java
public record OrderResponse(
    Long id,
    String code,
    List<LineRow> lines,
    List<ShipmentRow> shipments
) {}
```

### 23.1. Độ phức tạp nhóm dữ liệu

Dùng hash maps theo parent ID giúp nối các child result lists trong memory mà **không tạo SQL Cartesian product**. Chi phí phụ thuộc tổng child rows, không phụ thuộc tích của hai collection sizes.

### 23.2. Tránh nested loop không cần thiết

Không viết:

```java
for (OrderRow order : orderRows) {
    for (LineRow line : allLines) {
        // find matching order
    }
    for (ShipmentRow shipment : allShipments) {
        // find matching order
    }
}
```

nếu có thể group theo ID một lần. Cách nested loop có thể tạo chi phí CPU `O(orders × children)` không cần thiết.

### 23.3. Response DTO và authorization

Đừng vì có DTO projection mà bỏ kiểm tra quyền theo tenant/user. Query Orders phải được lọc hợp lệ; child queries dùng IDs từ tập đã được cho phép. Với dữ liệu nhạy cảm, có thể thêm tenant predicate ở mỗi query như defense-in-depth.

---

## 24. Đếm child counts mà không tải toàn bộ child objects

Nếu endpoint danh sách chỉ hiển thị:

```text
PO-042
  10 items
  8 shipments
```

thì không cần nạp `lines` và `shipments` để gọi `.size()` cho mỗi Order.

### 24.1. Một query GROUP BY riêng cho Lines

```jpql
SELECT l.order.id, COUNT(l.id)
FROM OrderLine l
WHERE l.order.id IN :ids
GROUP BY l.order.id
```

### 24.2. Một query GROUP BY riêng cho Shipments

```jpql
SELECT s.order.id, COUNT(s.id)
FROM Shipment s
WHERE s.order.id IN :ids
GROUP BY s.order.id
```

Sau đó map `orderId -> count`, mặc định 0 nếu không có row aggregate cho ID đó.

### 24.3. Không cần fetch collection để lấy count

Nạp 10.000 OrderLines chỉ để hiển thị số 10.000 là rất tốn. Aggregate query giảm dữ liệu được truyền.

### 24.4. COUNT(DISTINCT child.id) với hai joins vẫn có chi phí

Một query:

```jpql
SELECT o.id,
       COUNT(DISTINCT l.id),
       COUNT(DISTINCT s.id)
FROM PurchaseOrder o
LEFT JOIN o.lines l
LEFT JOIN o.shipments s
GROUP BY o.id
```

có thể trả đúng counts, nhưng database **vẫn phải xử lý join multiplication** trước aggregation tùy plan. Với collections lớn, hai independent aggregate queries có thể hiệu quả hơn; phải đo trên database mục tiêu.

---

## 25. EntityGraph: có thể thuận tiện nhưng vẫn làm nở rows

JPA EntityGraph cho phép chỉ định các attributes cần load trong use case:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("lines");
graph.addAttributeNodes("shipments");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
```

### 25.1. EntityGraph diễn đạt fetch plan, không cam kết SQL shape

Provider có thể dùng joins hoặc secondary selects tùy mapping/provider/version. Không khẳng định một graph có hai collections luôn tạo một SQL query hay luôn tránh cartesian multiplication.

### 25.2. Graph fetch cả hai collections vẫn có rủi ro

Nếu Hibernate triển khai graph bằng fetch joins của hai bags, có thể gặp MultipleBagFetchException hoặc row explosion. Chuyển JPQL `JOIN FETCH` thành graph không tự chữa vấn đề.

### 25.3. Graph phù hợp để mô tả tập attributes cần dùng

Ví dụ detail view cần Customer và Payment (to-one) có thể là candidate tốt. Nếu graph có nhiều to-many, kiểm tra SQL thực tế và cân nhắc split graph/secondary loads.

### 25.4. @EntityGraph trong Spring Data JPA

`@EntityGraph(attributePaths={"lines","shipments"})` trên repository method là cách tiện để yêu cầu fetching, nhưng vấn đề cardinality vẫn y như trên. Không coi annotation là performance guarantee.

---

## 26. FetchType.EAGER không phải giải pháp

Một phản ứng với `LazyInitializationException` là chuyển mọi collection sang EAGER:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.EAGER)
private List<OrderLine> lines;
```

### 26.1. Vấn đề

EAGER biểu thị dữ liệu cần được tải theo mapping contract, nhưng provider có thể thực hiện bằng joins hoặc secondary selects. Nó có thể khiến **mọi endpoint** tải Lines dù chỉ cần Order code.

### 26.2. N+1 vẫn có thể xuất hiện

EAGER không đồng nghĩa “tự động đúng một SQL”. Một JPQL query không fetch join association EAGER có thể cần thêm selects để đáp ứng eager loading semantics, tùy provider.

### 26.3. Chiến lược thường tốt hơn

Đặt collection LAZY theo use case và thiết kế fetch plan cụ thể cho service/endpoint. Với các to-one relations cũng nên quyết định theo access pattern, tránh mặc định EAGER khi không cần.

### 26.4. Đừng dùng Open Session in View thay thiết kế

Giữ persistence context mở xuyên qua web serialization có thể che lazy loading trong controller nhưng tạo queries bất ngờ/N+1 khi render JSON. Nên load hoặc project dữ liệu cần thiết **trước khi trả response**, với transaction boundaries và fetch plan rõ ràng.

---

## 27. Một-to-many độc lập khác nested one-to-many

Xét hai mô hình:

**Hai sibling collections:**

```text
Order
  +-- Lines
  +-- Shipments
```

Số row JOIN gần:

\[
\lvert Lines\rvert \cdot \lvert Shipments\rvert
\]

**Một chuỗi lồng nhau:**

```text
Order
  +-- Lines
          +-- Discounts
```

Khi JOIN fetch `order.lines` và `line.discounts`, rows gần tổng số discounts trên từng Line (với LEFT JOIN giữ Line không có Discount):

\[
R \approx
\sum_{\text{line}}
\max(1,\lvert Discounts(line)\rvert)
\]

### 27.1. Không phải mọi JOIN hai to-many đều nhân theo hai tổng độc lập

Một chuỗi parent→child→grandchild có cardinality khác hai collections cùng thuộc parent. Tuy nhiên graph quá sâu vẫn có thể bùng dữ liệu nếu mỗi bước có fan-out lớn.

### 27.2. Khi thêm Shipments vào chuỗi

Nếu vừa fetch Lines→Discounts vừa fetch Shipments của Order, các rows cho nhánh Lines/Discounts lại có thể nhân với số Shipments.

### 27.3. Ước lượng theo đồ thị

Trước mỗi fetch plan, vẽ association graph và đánh dấu:

- To-one: 0 hoặc 1.
- To-many: số lượng trung bình/tối đa.
- Các nhánh to-many độc lập.
- Depth của nested collections.
- Bảng có cột lớn/LOB.
- Pagination/filters.

---

## 28. LOB và cột lớn làm tác hại nặng hơn

Một parent có column `description TEXT` lớn:

```text
Order.description ~ 20 KB
Lines = 10
Shipments = 8
JOIN rows = 80
```

Nếu description bị lặp trong mỗi row, riêng parent description có thể được truyền nhiều lần theo SQL projection/driver behavior. Đây là ví dụ về **row width amplification**.

### 28.1. Đừng fetch LOB không cần

Một endpoint list chỉ cần Order ID/code/status thì projection nên chỉ chọn các fields đó. Không load `@Lob` content để đưa vào query result mà UI không dùng.

### 28.2. @Basic(fetch=LAZY) với LOB không bảo đảm luôn lazy

Lazy basic attribute loading có thể cần bytecode enhancement/provider support. Hãy kiểm tra SQL thực tế; projection là cách chắc chắn để chỉ chọn columns cần dùng cho read-only API.

### 28.3. Kết hợp row count với bytes

Khi đo, đừng chỉ đếm rows. 1.000 rows × 5 KB có thể tốn hơn 5.000 rows × 50 bytes. Network/heap/cpu phải được xem cùng nhau.

---

## 29. Pagination còn liên quan thứ tự ổn định

Bước query IDs:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
```

### 29.1. Vì sao thêm id vào ORDER BY?

Nếu nhiều Orders có cùng `createdAt`, chỉ sort theo thời gian không cho thứ tự ổn định khi chia trang. ID làm tie-breaker.

### 29.2. Offset pagination dưới concurrent writes

Nếu một Order mới được thêm vào đầu danh sách giữa page 1 và page 2, offset-based pages có thể lặp/bỏ sót records. Đây là vấn đề pagination semantics độc lập với fetch strategy.

### 29.3. Keyset pagination

Có thể dùng last seen `(createdAt,id)` làm cursor:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :status
  AND (
       o.createdAt < :lastCreated
       OR (
           o.createdAt = :lastCreated
           AND o.id < :lastId
       )
  )
ORDER BY o.createdAt DESC, o.id DESC
```

Sau đó fetch child graph theo page IDs. Query minh họa cho sort DESC và cursor hợp lệ; xử lý page đầu, nulls và input validation trong code production.

### 29.4. Keyset không tự tránh join multiplication

Dù dùng cursor, vẫn nên tách bước parent IDs khỏi các to-many fetches. Keyset giải quyết traversal/offset issues, không phải cartesian product.

---

## 30. Khi cần sort parent theo thông tin child

Ví dụ: “Orders có shipment gần nhất trước”.

Nếu query JOIN nhiều Shipments rồi ORDER BY `s.createdAt`, một Order có nhiều shipment timestamps. Thế nào là vị trí **của Order** trong danh sách?

### 30.1. Phải định nghĩa aggregate sort key

Ví dụ:

- Max shipment timestamp.
- Min shipment timestamp.
- Count shipments.
- Tổng quantity.
- Một trạng thái đã được tính sẵn.

### 30.2. Tách query chọn parent IDs

Dùng aggregate/grouping hoặc một view/reporting table phù hợp để chọn IDs theo aggregate sort key. Sau đó fetch các collections cho IDs đã chọn.

### 30.3. Tránh paginate thẳng trên joined child rows

Nếu SQL có 20 rows nhưng chỉ 5 Orders unique sau khử trùng lặp, `LIMIT 20` không nghĩa “20 Orders”. Cần query parent-level selection đúng.

---

## 31. Query chunking với WHERE IN

Một trang 20–50 IDs thường đơn giản. Nhưng nếu export 50.000 Orders rồi dùng:

```jpql
WHERE o.id IN :ids
```

với 50.000 bind values, có thể gặp:

- DB parameter limit.
- SQL length/preparation overhead.
- Execution plan không ổn định.
- Network/driver memory.
- Provider parameter expansion limits.

### 31.1. Chia IDs thành chunks

```text
IDs [1..50000]
  -> chunk 1: 500 IDs
  -> chunk 2: 500 IDs
  ...
```

Mỗi chunk tải Lines và Shipments theo fetch plan tương ứng.

### 31.2. Không dùng chunk size vô hạn

Chọn theo DBMS/driver, connection pool, memory, latency, query plan. Có thể bắt đầu benchmark với 100–1000 IDs nhưng không xem đó là rule cố định.

### 31.3. Giữ original parent order

Sau nhiều chunk queries, gom kết quả vào Map theo ID rồi sắp lại theo thứ tự parent IDs ban đầu. `IN` không bảo đảm thứ tự.

### 31.4. Export lớn có thể cần streaming

Thay vì nạp tất cả Orders và collections vào persistence context rồi giữ đến cuối, đọc theo pages/chunks, chuyển sang DTO, giải phóng memory theo transaction boundaries phù hợp. Nếu dùng `em.clear()`, phải đảm bảo không cần các managed instances đã bị detach; xử lý từng chunk độc lập.

---

## 32. Count query riêng cho Page

Một UI phân trang có thể cần:

```text
content: 20 Orders
totalElements: 6.420 Orders
```

### 32.1. Đếm trên parent

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :status
```

Nếu lọc theo child:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :status
  AND EXISTS (
      SELECT l.id
      FROM OrderLine l
      WHERE l.order = o
        AND l.sku = :sku
  )
```

### 32.2. Không COUNT trên fetch join

JPQL fetch join nhằm load association của entity được chọn; sử dụng fetch join trong count query không phù hợp và có thể gây lỗi. Count query nên độc lập với fetch graph.

### 32.3. Pageable của Spring Data JPA

Với custom `@Query` có join/filter phức tạp, cần xác nhận count query đúng parent-level semantics. Không để framework tự suy count query sai từ một content query có fetch join/multiple joins.

### 32.4. Khi không cần total count

Một `Slice` hoặc logic lấy `pageSize+1` IDs có thể tránh count query lớn, nếu API chỉ cần biết `hasNext`.

---

## 33. Projection phẳng bằng SQL: khi nào cần JDBC?

JPA/JPQL có thể đủ cho phần lớn read flows. Nhưng báo cáo phức tạp có thể dùng:

- Native SQL projections.
- JDBC/JdbcTemplate.
- jOOQ hoặc SQL query builder tương ứng.
- Database views/materialized views.
- Reporting read model.

### 33.1. Lợi ích

Cho phép dùng SQL aggregation/window functions, JSON aggregation và strategies đặc thù DBMS để giảm round trips hoặc trả đúng shape cần thiết.

### 33.2. JSON aggregation cần đo

Một PostgreSQL query dùng `json_agg` để gom Lines và Shipments độc lập có thể trả một row per Order, nhưng nếu JOIN trực tiếp hai collections rồi `json_agg`, JSON arrays có thể vẫn bị duplicate elements vì nhân rows.

Thường cần aggregate **mỗi collection trong subquery/lateral query độc lập** rồi join aggregates vào Order.

### 33.3. Database-side aggregation không miễn phí

Nó chuyển công việc assembly sang DB, có thể tăng DB CPU/memory. So sánh với ba flat queries và Java grouping; không mặc định native JSON aggregation luôn nhanh hơn.

### 33.4. Khi JPA entity management không cần thiết

Với read-only report, DTO/SQL projection có thể rõ và rẻ hơn managed entity graph, đặc biệt nếu response rất rộng.

---

## 34. Không lạm dụng serialization trực tiếp entity graph

Một controller:

```java
@GetMapping("/orders")
public List<PurchaseOrder> listOrders() {
    return repository.findAll();
}
```

có thể khiến JSON serializer truy cập nhiều LAZY collections. Tùy persistence context/OSIV, kết quả là:

- `LazyInitializationException` nếu context đã đóng.
- N+1 queries nếu context còn mở.
- Dữ liệu graph quá rộng.
- Cyclic associations gây recursion.
- Payload lớn hơn yêu cầu.
- Exposure các fields không nên public.

### 34.1. Tách read model

Dùng `OrderCardResponse` cho danh sách, `OrderDetailResponse` cho chi tiết, `OrderExportRow` cho export. Mỗi use case có fetch plan phù hợp.

### 34.2. Không giải quyết bằng EAGER tất cả associations

EAGER default có thể làm mọi request tải graph quá lớn.

### 34.3. Định nghĩa giới hạn response

Ví dụ một Order có 100.000 Lines, detail endpoint có thể cần child pagination riêng:

```http
GET /orders/42
GET /orders/42/lines?page=0&size=100
GET /orders/42/shipments?page=0&size=50
```

Tránh mong một response detail duy nhất chứa dữ liệu vô hạn.

---

## 35. Một bảng so sánh các chiến lược

| Chiến lược | Số queries | Row multiplication | Pagination parent | Tính portable |
|---|---|---|---|---|
| JOIN FETCH một to-many | Ít | Theo một collection | Cẩn thận với paging | JPQL/JPA |
| JOIN FETCH hai to-many | Rất ít | **Cao: tích các sizes** | Dễ gặp vấn đề | JPQL hợp lệ tùy mapping; Hibernate có multiple-bag limitation |
| Tách fetch từng collection | Thường 2–3 | Tránh tích giữa các sibling collections | Tốt khi IDs selected trước | JPA |
| LAZY + batch fetching | Giảm N+1 | Không JOIN các sibling collections | Tốt | Hibernate-specific config |
| SUBSELECT fetching | Ít hơn N+1 trong use case phù hợp | Không JOIN sibling collections | Cần đo scope | Hibernate-specific |
| EntityGraph nhiều collections | Phụ thuộc provider | **Có thể cao** | Cần kiểm tra | JPA graph API, execution provider-dependent |
| DTO flat queries | Thường 2–3 | Không có sibling cross product | Tốt | JPQL/JPA |
| Aggregated counts | Ít | Tránh tải children | Tốt | JPQL/JPA |
| JSON aggregation độc lập | Có thể 1 | Không nếu SQL đúng | Phụ thuộc design | DBMS-specific |
| Secondary child pagination | Theo endpoint | Không bắt buộc | Parent và child paging tách | JPA/SQL |

**Lựa chọn ưu tiên thường phụ thuộc cardinality, query frequency, loại response, transaction consistency và database workload**, không phụ thuộc số queries thuần túy.

---

## 36. Case study: endpoint Order detail

### Yêu cầu

```text
GET /orders/42
Hiển thị:
  code, status, customerName
  3 Lines
  4 Shipments
```

### 36.1. Cách kém hiệu quả

Fetch `customer` (to-one), `lines` (to-many), `shipments` (to-many) cùng một query. Nếu Hibernate cho phép, rows có thể 12; nếu bags, có thể exception.

### 36.2. Phương án đề xuất

- Query Order + Customer + Lines.
- Query Order + Shipments.
- Map sang DTO trong service transaction.

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.customer
LEFT JOIN FETCH o.lines
WHERE o.id = :id
```

Lưu ý `customer` là một association to-one **giả định thêm vào model Order**; ví dụ phần 6 chưa khai báo property ấy. Query chỉ dùng được sau khi có mapping tương ứng.

Query thứ hai:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.shipments
WHERE o.id = :id
```

### 36.3. Khi nào không cần fetch Lines?

Nếu endpoint chỉ hiển thị order header/status, đừng fetch Lines/Shipments chỉ vì có mapping. Một DTO projection của Order headers có thể rẻ nhất.

---

## 37. Case study: trang 50 Orders

### Yêu cầu

```text
GET /orders?status=PAID&page=0&size=50

Mỗi row hiển thị:
  id, code, createdAt, totalLines, totalShipments
```

### 37.1. Phương án tệ

Fetch 50 Orders cùng toàn bộ Lines và Shipments để gọi `.size()`.

Với trung bình 20 Lines và 5 Shipments:

```text
Join rows ≈ 50 × 20 × 5 = 5.000
Logical children ≈ 50 × (20 + 5) = 1.250
```

### 37.2. Phương án phù hợp hơn

1. Query 50 Order IDs + headers.
2. Query `COUNT(lines) GROUP BY orderId`.
3. Query `COUNT(shipments) GROUP BY orderId`.
4. Ghép counts theo ID.
5. Không load collection entities.

### 37.3. Đo điểm hòa vốn

Nếu payload chỉ vài columns và số Orders nhỏ, nhiều approaches có thể đủ nhanh. Benchmark vẫn cần thiết; không nâng complexity quá mức khi chưa có bottleneck.

---

## 38. Case study: export 10.000 Orders

### Yêu cầu

Xuất file report chứa Order, Lines và Shipments.

### 38.1. Không JOIN tất cả và hold managed graph

Một join rows với trung bình 10 × 8 có thể tạo ~800.000 result rows. Nếu thêm một association to-many nữa, kích thước có thể tăng theo cấp số nhân.

### 38.2. Một pipeline khả thi

```text
Get next 200 Order IDs by keyset
        |
        v
Fetch flat Order data
        |
        v
Fetch Lines WHERE order_id IN chunk
        |
        v
Fetch Shipments WHERE order_id IN chunk
        |
        v
Write output for chunk
        |
        v
Release chunk memory
        |
        v
Next cursor / chunk
```

### 38.3. Memory và transaction boundaries

Với export dài, cần thiết kế snapshot/freshness policy, streaming output, chunk boundaries và retryability. Không giữ một EntityManager với hàng chục nghìn managed entities vô thời hạn nếu không cần.

### 38.4. Không tự clear khi vẫn cần lazy fields

Sau khi detach entities, lazy associations chưa loaded có thể không truy cập được. Với DTO flat projections, giảm phụ thuộc vào persistence context giúp xử lý chunk dễ hơn.

---

## 39. Query plan và optimizer khi JOIN nhiều collections

Một query nhiều JOIN có thể dùng:

- Nested loop joins.
- Hash joins.
- Merge joins.
- Index scans.
- Sequential scans.
- Sort/aggregate.

Cách thực thi phụ thuộc DBMS, statistics, indexes và cardinality estimates.

### 39.1. EXPLAIN giúp xác định điều gì?

- Cardinality ước tính và thực tế của từng bước.
- JOIN algorithm.
- Số rows trước/ sau JOIN.
- Filter selectivity.
- Sort/hash memory.
- Table/index access.
- Timing/IO nếu dùng explain analyze theo DBMS.

### 39.2. Ví dụ PostgreSQL

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, l.id, s.id
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
LEFT JOIN shipments s ON s.order_id = o.id
WHERE o.status = 'PAID';
```

Chỉ chạy `EXPLAIN ANALYZE` trên môi trường/khối lượng được phép vì nó **thực thi query**. Đối với SELECT thường an toàn về dữ liệu, nhưng vẫn có thể tiêu tốn đáng kể tài nguyên trên production.

### 39.3. DBA thống kê sai có thể làm nặng hơn

Nếu optimizer đánh giá thấp kích thước JOIN result, nó có thể chọn kế hoạch kém. Indexes/stats có thể cải thiện plan, nhưng phải giải quyết **fetch shape** khi cardinality logic quá cao.

---

## 40. Đo đúng: query count và row count

Các metrics nên thu:

1. Số SQL statements phát ra.
2. Số rows thực tế được JDBC đọc hoặc DB trả.
3. Kích thước payload SQL/bytes.
4. Latency p50/p95/p99 ở endpoint.
5. DB execution time và plans.
6. Database CPU/IO.
7. Entity load/collection fetch counts.
8. JVM heap/GC/hydration cost.
9. Result entity IDs và collection sizes.
10. Độ đúng của pagination/order.
11. Tần suất cache hits và ảnh hưởng cold/warm.
12. Concurrent load/connection pool behavior.

### 40.1. Hibernate statistics

Hibernate có `SessionFactory.getStatistics()` và các counters như query execution count, entity load count, collection fetch/load counts theo version.

```java
org.hibernate.SessionFactory sf =
    emf.unwrap(org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics stats =
    sf.getStatistics();

stats.setStatisticsEnabled(true);
stats.clear();

// Execute the test workload here.

System.out.println(
    "Statements prepared: "
        + stats.getPrepareStatementCount());

System.out.println(
    "Entity loads: "
        + stats.getEntityLoadCount());

System.out.println(
    "Collection loads: "
        + stats.getCollectionLoadCount());
```

Các APIs/counters là Hibernate-specific. Cần đối chiếu version và hiểu rằng chúng **không luôn cung cấp trực tiếp số JDBC rows** cho mọi SQL query.

### 40.2. Muốn đo SQL rows cần công cụ phù hợp

Sử dụng JDBC proxy/instrumentation, SQL logging kết hợp DB profiler, execution statistics, driver instrumentation hoặc query plan với actual rows. Chỉ bật `hibernate.show_sql=true` chưa chắc cho biết mỗi query trả bao nhiêu rows.

### 40.3. Không chỉ nhìn Java result list

Một query nhiều JOIN có thể trả List chỉ 20 Orders unique nhưng JDBC đã xử lý 10.000 rows.

### 40.4. So sánh công bằng

Giữ cố định dataset, DB statistics, transaction isolation, fetch columns, page size, cache warm state và concurrency. Nếu phương án A trả toàn bộ children còn B chỉ trả counts, chúng **không tương đương về requirements**, không so sánh như hai cách hoàn thành cùng một chức năng.

---

## 41. Thí nghiệm A: tái hiện row multiplication bằng SQL

Fixture:

```text
Order #42
  3 OrderLines
  4 Shipments
```

Chạy:

```sql
SELECT COUNT(*) AS joined_rows
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
LEFT JOIN shipments s ON s.order_id = o.id
WHERE o.id = 42;
```

Expected `joined_rows = 12` nếu dữ liệu đúng và không có filter khác.

### 41.1. So sánh với các truy vấn tách

```sql
SELECT COUNT(*)
FROM order_lines
WHERE order_id = 42;

SELECT COUNT(*)
FROM shipments
WHERE order_id = 42;
```

Expected 3 và 4.

### 41.2. Thử các trường hợp rỗng

- 0 Lines / 4 Shipments.
- 3 Lines / 0 Shipments.
- 0 Lines / 0 Shipments.
- 1 Line / 1 Shipment.

Xác nhận công thức `max(1, lines) × max(1, shipments)` trong tình huống LEFT JOIN đơn giản.

### 41.3. Không dùng COUNT(*) của JOIN để đếm Lines

Nếu query có cả Shipments join, `COUNT(l.id)` sẽ đếm lặp Lines theo số Shipments. Dùng aggregation strategy phù hợp hoặc query Lines riêng.

---

## 42. Thí nghiệm B: MultipleBagFetchException

Dùng Hibernate với hai collections theo bag semantics.

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
LEFT JOIN FETCH o.shipments
WHERE o.id = :id
```

### 42.1. Điều cần ghi

- Hibernate ORM version.
- Mapping `List` có `@OrderColumn` hay không.
- Exception type/root cause.
- Exception xảy ra trước SQL hay sau SQL.
- Đã có một query fetch join khác không.
- Graph `@EntityGraph` có thay đổi behavior không.

### 42.2. Điều cần kết luận

Exception phản ánh giới hạn Hibernate khi đồng thời fetch nhiều bag collections, không phải JPA portable exception bắt buộc mọi provider ném cùng class.

### 42.3. Không dùng Set conversion làm “đáp án tối ưu” duy nhất

Có thể thử Set mapping trong một mô hình riêng **với equality đúng**, rồi đo SQL row count. Nếu query chạy được nhưng vẫn trả 12 rows, chứng minh hai vấn đề khác nhau.

---

## 43. Thí nghiệm C: DISTINCT không xóa chi phí JOIN

Chuẩn bị một mapping/query hợp lệ cho provider để JOIN hai collections, ví dụ hai Set associations trong sandbox có test `equals/hashCode` phù hợp.

1. Chạy query không `DISTINCT`.
2. Ghi SQL và rows.
3. Chạy query có `DISTINCT`.
4. Ghi SQL và rows.
5. So sánh số Order IDs unique.
6. So sánh collection sizes thực tế.
7. Ghi Hibernate version.
8. Đo latency/memory.

### 43.1. Kỳ vọng khái niệm

`DISTINCT` có thể làm result list root entities unique theo semantics, nhưng khi child columns khác nhau, SQL join rows vẫn có thể bằng phép nhân.

### 43.2. Không suy SQL DISTINCT được đẩy xuống DB ở mọi version

Provider/version có thể xử lý duplicate root references theo cơ chế khác nhau. Quan sát actual SQL và kế hoạch thay vì đoán từ JPQL text.

---

## 44. Thí nghiệm D: tải hai collections bằng hai queries

1. Dùng cùng EntityManager.
2. Query `LEFT JOIN FETCH o.lines`.
3. Query `LEFT JOIN FETCH o.shipments`.
4. Kiểm tra cả hai collections initialized.
5. Assert mỗi collection có đúng số phần tử.
6. Ghi SQL statement count.
7. Ghi tổng SQL rows.
8. Thử gọi `em.clear()` giữa queries và giải thích behavior khác.
9. Thử đổi thứ tự hai fetch queries.
10. So sánh với single multi-collection JOIN query.

### 44.1. Kết quả logic

Một Order 3 Lines + 4 Shipments nên có đúng các child IDs:

```text
lines: [L1, L2, L3]
shipments: [S1, S2, S3, S4]
```

Không chấp nhận list duplicates do join explosion.

### 44.2. Độ đúng trước hiệu năng

Một test thành công khi data graph đúng, sau đó mới so SQL rows. Không đánh đổi graph incomplete lấy response nhanh.

---

## 45. Thí nghiệm E: page IDs rồi fetch graph

Dataset:

```text
100 Orders
mỗi Order 10 Lines
mỗi Order 8 Shipments
```

Thực hiện:

1. Chọn page size 20.
2. Query 20 Order IDs theo createdAt DESC, id DESC.
3. Fetch Lines cho IDs.
4. Fetch Shipments cho IDs.
5. Phục hồi thứ tự Java result.
6. Assert result có đúng 20 unique Orders.
7. Assert mỗi Order có 10 Lines và 8 Shipments.
8. Ghi statement count/row count/memory.
9. Thử trang 2.
10. So sánh với pagination trên collection fetch join (sandbox only).

### 45.1. Số rows mong đợi

Multi-join fetch 20 Orders:

```text
20 × 10 × 8 = 1.600 joined rows
```

Split fetch:

```text
20 parent ID rows
200 line-join rows
160 shipment-join rows
total ~380 rows
```

Nếu query fetch Lines và Shipments theo JOIN với parent, mỗi collection query có số rows tương ứng (với empty collections có thêm preserved-parent rows), không nhân chéo.

---

## 46. Thí nghiệm F: fail-on-pagination guard

1. Bật `hibernate.query.fail_on_pagination_over_collection_fetch=true`.
2. Viết JPQL query `LEFT JOIN FETCH o.lines`.
3. Gọi `setFirstResult(0)` và `setMaxResults(20)`.
4. Thực thi trong test DB có nhiều Orders/Lines.
5. Ghi Hibernate exception/warning behavior.
6. Thay bằng two-step parent IDs.
7. Đảm bảo guard không còn bị kích hoạt.
8. Assert đúng số unique parents.

### 46.1. Vì sao fail fast quan trọng?

Nó giúp biến một lỗi hiệu năng âm thầm (pagination trong memory) thành lỗi test dễ phát hiện sớm.

### 46.2. Không bắt buộc dùng guard ở mọi JPA provider

Property là Hibernate-specific. Với provider khác, tìm cơ chế tương đương hoặc viết integration tests để bảo đảm pagination semantics.

---

## 47. Thí nghiệm G: batch fetching

Fixture 60 Orders và hai LAZY collections.

1. Tắt batch fetching.
2. Load 60 Orders.
3. Truy cập `lines` và `shipments` trong cùng context.
4. Ghi SQL count.
5. Bật `hibernate.default_batch_fetch_size=16`.
6. Lặp lại với EntityManager/cache state tương đương.
7. Ghi số batched SELECTs.
8. Thử batch size 32, 64.
9. Kiểm tra SQL `IN` clauses.
10. Đo latency/DB plan/parameter count.
11. So sánh với explicit split query.

### 47.1. Không dùng sleep để đo “nhanh hơn”

Dùng warm-up và nhiều repetitions với profiler/benchmark harness phù hợp, không một phép đo wall-clock duy nhất rồi khẳng định performance.

---

## 48. Thí nghiệm H: SUBSELECT fetching

1. Map Lines bằng Hibernate `@Fetch(SUBSELECT)`.
2. Load 50 Orders qua một query.
3. Truy cập Lines của một Order.
4. Quan sát có những collections nào được tải cùng.
5. Truy cập Lines của các Orders còn lại.
6. Ghi SQL statements.
7. Lặp với page size nhỏ.
8. Lặp với persistence context chứa thêm nhiều Orders.
9. Đánh giá overfetch và memory.
10. So sánh với batch fetching.

### 48.1. Điều quan trọng

SUBSELECT có thể giảm N+1 nhưng không đảm bảo nó luôn tải đúng chỉ các Orders bạn dự định serialize. Hãy quan sát SQL/role/session scope thực tế.

---

## 49. Thí nghiệm I: DTO projection với ba flat queries

1. Tạo OrderRow, LineRow và ShipmentRow.
2. Query page OrderRows.
3. Query LineRows theo IDs.
4. Query ShipmentRows theo IDs.
5. Group theo orderId.
6. Dựng OrderResponse.
7. Assert đúng số Orders/Lines/Shipments.
8. Kiểm tra response không chứa JPA proxies.
9. Đo memory và JDBC rows.
10. So sánh với managed graph approach.
11. Thử dữ liệu child lớn và chỉ chọn columns cần.
12. Thử no children để bảo đảm arrays rỗng.

### 49.1. Lưu ý thứ tự

`Collectors.groupingBy` không tự diễn đạt business sorting của Lines/Shipments. Query ORDER BY theo `lineNumber` hoặc `id` và giữ insertion order trong lists, hoặc sort riêng sau grouping theo business rule.

---

## 50. Thí nghiệm J: counts-only dashboard

1. Tạo 1.000 Orders.
2. Mỗi Order có 100 Lines, 5 Shipments.
3. Dựng trang chỉ cần `lineCount` và `shipmentCount`.
4. Thử fetch graph rồi `getLines().size()`.
5. Thử hai `COUNT GROUP BY` queries.
6. So sánh SQL rows/bytes/latency.
7. Assert counts giống nhau.
8. Thử parent không có children.
9. Thử filter theo child bằng EXISTS.
10. So sánh EXPLAIN plans.

---

## 51. Thí nghiệm K: nested to-many vs sibling to-many

Tạo:

```text
Order
  Lines
     Discounts
  Shipments
```

1. Với 3 Lines, mỗi Line 2 Discounts, JOIN Order→Lines→Discounts.
2. Đếm rows: khoảng 6 cho branch này.
3. Thêm JOIN Order→Shipments với 4 Shipments.
4. Đếm rows: có thể khoảng 24.
5. Giải thích vì sao nhánh sibling nhân kết quả của nhánh nested.
6. Thiết kế fetch split: một query Lines/Discounts, một query Shipments.
7. Thử mức fan-out lớn và quan sát cardinality.
8. So sánh các chiến lược batch/subselect.

### 51.1. Không biến mọi graph thành công thức duy nhất

Các JOIN types, filters, conditions và optionality làm số rows thực tế thay đổi. Công thức là công cụ ước lượng, không thay SQL EXPLAIN/test.

---

## 52. Thí nghiệm L: kiểm tra tính nhất quán giữa hai queries

1. Query page IDs trong Transaction A.
2. Trước khi fetch Shipments, cho Transaction B insert một Shipment và commit.
3. Query Shipments trong A.
4. Quan sát kết quả dưới READ COMMITTED.
5. Lặp với REPEATABLE READ theo DBMS.
6. So sánh MVCC/locking semantics.
7. Xác định freshness requirement cho endpoint.
8. Nếu cần, sử dụng snapshot/transaction isolation/optimistic version policy phù hợp.
9. Không chỉ dùng readOnly=true rồi mặc định cùng snapshot.

---

## 53. Thí nghiệm M: giới hạn của Set workaround

1. Tạo mapping với `Set<OrderLine>` và `Set<Shipment>`.
2. Chọn equality/hashCode strategy phù hợp entity lifecycle.
3. Fetch join hai Sets.
4. Assert số phần tử collection.
5. Đo SQL row count.
6. Dùng 10×8 children, kiểm tra khoảng 80 rows.
7. Thử refactor sang hai queries mà vẫn giữ Set semantics.
8. So sánh SQL rows/memory.
9. Đánh giá có cần sort order hay không.
10. Ghi kết luận “không ném exception” không đồng nghĩa “tối ưu”.

---

## 54. Thí nghiệm N: truy vấn lọc parent bằng EXISTS

1. Tạo Orders có nhiều Lines cùng SKU.
2. Query parent IDs bằng JOIN + DISTINCT.
3. Query parent IDs bằng EXISTS.
4. Assert tập IDs giống nhau.
5. Đo SQL plans/row counts.
6. Phân trang 20 IDs.
7. Fetch full Lines/Shipments riêng.
8. Đảm bảo parent filter không khiến collection chỉ chứa Lines matching SKU.
9. Ghi behavior khi không có matching child.

---

## 55. Thí nghiệm O: export theo chunks

1. Tạo 10.000 Orders trong test database.
2. Dùng keyset pagination 200 IDs/chunk.
3. Query flat OrderRows, LineRows, ShipmentRows.
4. Dựng output từng chunk.
5. Giải phóng chunk buffers.
6. Đo peak memory.
7. Thử failure giữa chunks và resume cursor policy.
8. Kiểm tra không duplicate/skip IDs khi dataset ổn định.
9. Đánh giá isolation/freshness khi có concurrent writes.
10. So sánh với một multi-join fetch toàn bộ dữ liệu.

---

## 56. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Một query rất chậm dù SQL count=1 | JOIN nhiều to-many sinh quá nhiều rows | Split fetch, DTO, đo rows |
| `MultipleBagFetchException` | Fetch nhiều bags cùng lúc trong Hibernate | Tách queries, xét mapping semantics |
| `DISTINCT` không giảm network | Child tuples khác nhau nên SQL rows vẫn nhiều | Tránh sibling joins |
| Page size=20 nhưng Hibernate nạp hàng nghìn Orders/Lines | Collection fetch + pagination trong memory | Page IDs trước, bật fail-on-pagination guard |
| Trang trả ít hơn 20 Orders | Paginate JOIN rows rồi dedup parents | Paginate parent IDs |
| `Set` làm query chạy nhưng vẫn chậm | Không chữa row multiplication | Split queries |
| Dữ liệu List mất thứ tự sau đổi Set | Thay semantics domain | Dùng đúng collection type |
| Set bỏ sót child sau persist | equals/hashCode với generated ID sai | Thiết kế equality ổn định |
| @OrderBy không sửa bag exception | Không có persistent list index | Không dựa vào @OrderBy như @OrderColumn |
| @EntityGraph vẫn tạo SQL lớn | Provider JOIN nhiều collections | Quan sát SQL; split fetch |
| EAGER tạo SELECTs bất ngờ | Mapping yêu cầu fetch rộng | LAZY + use-case fetch plans |
| Controller ném LazyInitializationException | DTO/entity đọc LAZY ngoài context | Load trong service transaction, DTO |
| N+1 khi serialize JSON | Serializer truy cập LAZY | DTO + batch/split fetching |
| Query thứ hai không bổ sung collections trên object cũ | Khác EM hoặc clear/detach giữa queries | Giữ cùng persistence context |
| Order trả sai thứ tự sau query IN | SQL IN không bảo đảm order | Reorder theo original page IDs |
| IN có quá nhiều params | Page/export chunk quá lớn | Chunk IDs, benchmark |
| Parent lọc theo child nhưng collection thiếu rows | Dùng fetch join + child filter sai semantics | EXISTS lọc parent, fetch collection riêng |
| Count query nhân giá trị | COUNT trên multi-join | Aggregate riêng hoặc DISTINCT thích hợp |
| Cache hit nhưng SQL query vẫn nặng | Query plan/fetch shape tạo nhiều rows | Đo JDBC rows, không dựa cache |
| SUBSELECT load quá nhiều collections | Parent selection/session scope rộng | Benchmark, dùng batch/explicit queries |
| READ COMMITTED trả snapshot khác giữa queries | Concurrent write | Xác định isolation/freshness contract |
| Hibernate stats không cho SQL row count | Counter không phải row count | JDBC proxy/DB profiler |
| Có index nhưng SQL vẫn phình | Index không đổi join cardinality | Sửa fetch strategy |
| Không nhận diện multiple bag trong test H2 | Mapping/Provider/config khác | Integration test stack mục tiêu |
| Query DTO báo constructor error | Types/FQCN không khớp | Kiểm tra JPQL constructor projection |
| Page sort theo createdAt không ổn định | Nhiều parent cùng timestamp | Thêm unique ID tie-breaker |
| CountQuery từ Spring Data sai | Content query có joins/fetch khác count semantics | Viết countQuery riêng |

---

## 57. Checklist thiết kế fetch plan trước khi merge

| Câu hỏi | Cần xác nhận |
|---|---|
| Endpoint cần parent fields nào? | Chỉ select fields cần |
| Endpoint cần bao nhiêu child collections? | Có thể tách/cắt pagination? |
| Collections là siblings độc lập? | Có nguy cơ tích cardinality |
| Số child trung bình/tối đa? | Dùng real data distribution |
| Một parent có thể có collection cực lớn? | Pagination/chunking riêng |
| List mapping có bag semantics không? | Test với Hibernate version |
| Có MultipleBagFetchException? | Tách fetch/đánh giá mapping |
| Dùng Set chỉ vì exception? | Không đổi semantics vô cớ |
| Có @OrderColumn/@OrderBy? | Hiểu khác biệt |
| Query có DISTINCT? | Không coi là chữa row explosion |
| Query phân trang parent? | IDs trước, không join row LIMIT |
| Hibernate pagination guard bật? | Khuyến khích kiểm tra |
| Thứ tự parent sau IN được phục hồi? | Sort/map theo IDs |
| Query lọc theo child? | EXISTS hoặc parent-level selection |
| Có cần full children hay chỉ count? | Aggregate nếu chỉ cần count |
| To-one associations có fetch được cùng parent? | Cân nhắc single-valued joins |
| @EntityGraph có nhiều collections? | Kiểm SQL thực tế |
| BatchSize/default batch fetch size đo chưa? | Compare SQL count/rows |
| SUBSELECT scope rõ chưa? | Test parent selection |
| DTO projection có phù hợp không? | Tránh managed graph nếu read-only |
| Collection loaded cùng persistence context? | Không clear giữa queries |
| Có thể gặp LazyInitializationException? | DTO trong transaction |
| Có cache layers không? | Tách cache effects khi đo |
| SQL row count được đo? | JDBC/DB execution metrics |
| Chỉ số p95/p99 latency? | Đo dưới realistic load |
| Database JOIN plan đã xem? | EXPLAIN |
| Index foreign keys có phù hợp? | Có thể hỗ trợ split queries |
| LOB columns bị lặp? | Projection hạn chế row width |
| Page count query đúng? | Count parents |
| Concurrency giữa queries có chấp nhận? | Isolation/freshness |
| Tenant authorization có đúng ở các child queries? | Không rò dữ liệu |
| Export có chia chunks? | Memory bounded |
| Integration test với DB mục tiêu? | Tránh chỉ dùng H2 |
| Có regression test cardinality lớn? | Fixture 10×8, 100×100 |
| Có test empty collections? | LEFT JOIN behavior |
| Kết quả có duplicate child IDs? | Assert set/sequence theo business |
| Có test sort/order deterministic? | Có |
| Code chỉ trả đúng dữ liệu business cần? | Không overfetch |

---

## 58. Những hiểu lầm cần tránh

### 58.1. “Một SQL luôn nhanh hơn ba SQL”

Không. Một SQL JOIN có thể vận chuyển và hydrate hàng chục nghìn rows trùng lặp trong khi ba queries vận chuyển tổng dữ liệu tuyến tính.

### 58.2. “JOIN FETCH mọi collection là cách dứt điểm N+1”

Nó có thể đổi N+1 thành row explosion và multiple bag problems. Tối ưu fetching cần kiểm soát cả statement count lẫn cardinality.

### 58.3. “DISTINCT xóa hết duplicated JOIN rows”

Không. Khi Line/Shipment columns khác nhau, SQL rows là những tuples khác nhau. Root entity dedup không loại network/DB work.

### 58.4. “Result list có một Order nghĩa SQL chỉ trả một row”

Không. Entity identity map có thể materialize một Order từ nhiều JDBC rows.

### 58.5. “Hibernate MultipleBagFetchException là lỗi của mọi JPA provider”

Không. Đó là một giới hạn/exception của Hibernate. JPA không buộc mọi provider phát cùng class lỗi.

### 58.6. “Đổi List thành Set là sửa hết hiệu năng”

Không. Nó thay collection semantics và có thể tránh exception nhưng SQL rows vẫn nhân.

### 58.7. “@OrderBy và @OrderColumn là một”

Không. `@OrderBy` sắp theo attribute; `@OrderColumn` duy trì index/position của List.

### 58.8. “@EntityGraph luôn tránh Cartesian product”

Không. EntityGraph mô tả attributes cần fetch; provider vẫn quyết định SQL shapes.

### 58.9. “FetchType.EAGER luôn làm một SQL”

Không. EAGER có thể dùng secondary selects và overfetch dữ liệu trên mọi use cases.

### 58.10. “Pagination JOIN FETCH collection luôn LIMIT đúng số parent ở DB”

Không. Hibernate có thể paginate in memory hoặc báo lỗi; một SQL LIMIT trên JOIN rows không tương đương LIMIT parent count.

### 58.11. “Thêm DISTINCT vào paginated fetch join sẽ sửa paging”

Không. Phải thiết kế parent-level pagination (IDs/keyset) trước khi fetch collections.

### 58.12. “WHERE IN :ids bảo đảm thứ tự IDs”

Không. SQL không bảo đảm order nếu không có ORDER BY. Phục hồi thứ tự theo ID page hoặc dùng CASE ordering phù hợp DBMS.

### 58.13. “Tách hai queries sẽ tạo hai Order objects khác nhau”

Không nếu cùng persistence context quản lý cùng entity identity. `em.clear()`/transaction boundaries có thể thay đổi điều đó.

### 58.14. “Batch fetching làm collection EAGER”

Không. Nó tối ưu cách LAZY collection loads được gom nhóm khi truy cập.

### 58.15. “SUBSELECT chỉ tải đúng một collection đang cần”

Không mặc nhiên. Nó có thể tải cùng collection role cho nhiều parents trong context/subselect selection.

### 58.16. “DTO projection luôn phải qua entity graph trước”

Không. JPQL constructor queries có thể trả scalar fields từ DB trực tiếp, không cần hydrate managed entity graph.

### 58.17. “Muốn count Lines phải nạp toàn bộ Lines”

Không. Dùng COUNT/GROUP BY query.

### 58.18. “COUNT(DISTINCT) luôn làm database bỏ qua row multiplication”

Không. Database có thể vẫn phải xử lý join combinations trước aggregation. Đo plans.

### 58.19. “Index trên FK xóa được phép nhân rows”

Không. Index cải thiện truy cập, không đổi số combinations trong SQL JOIN.

### 58.20. “readOnly transaction tự tạo snapshot nhất quán giữa các queries”

Không. Isolation semantics thuộc DBMS/transaction config, không do readOnly hint một mình quyết định.

### 58.21. “LazyInitializationException nên sửa bằng OSIV hoặc EAGER tất cả”

Không phải giải pháp hiệu năng bền vững. Dùng DTO/service-level fetch kế hoạch rõ.

### 58.22. “JOIN parent→child→grandchild luôn giống JOIN hai sibling collections”

Không. Chuỗi nested có cardinality theo child grandchildren; sibling branches độc lập nhân lẫn nhau.

### 58.23. “Một phép đo latency là đủ chọn fetch strategy”

Không. Warm/cold cache, dataset cardinality, DB plan, concurrency và GC đều ảnh hưởng.

### 58.24. “Có 20 Orders trong JSON thì chi phí JOIN nhỏ”

Không. Một Order có hàng nghìn child records có thể nhân khổng lồ ngay cả khi page nhỏ.

---

## 59. Câu hỏi ôn tập

1. N+1 problem là gì?
2. Row multiplication khác N+1 ở đâu?
3. Hai collections độc lập mỗi tập 3 và 4 phần tử sinh khoảng bao nhiêu LEFT JOIN rows?
4. Vì sao 3 Lines và 4 Shipments không cho 7 JOIN rows?
5. Công thức ước lượng cho hai sibling LEFT JOIN collections là gì?
6. Trường hợp collection rỗng ảnh hưởng LEFT JOIN result ra sao?
7. Vì sao số Java entities unique có thể ít hơn SQL rows rất nhiều?
8. Những loại overhead nào tăng khi JDBC rows tăng?
9. Vì sao số SQL statements không phải thước đo hiệu năng duy nhất?
10. `JOIN FETCH` một collection phù hợp khi nào?
11. `JOIN FETCH` hai collections có hai rủi ro gì?
12. MultipleBagFetchException có phải JPA standard exception không?
13. Bag semantics là gì?
14. Java `List` có luôn là indexed persistent List không?
15. @OrderColumn khác @OrderBy thế nào?
16. Vì sao đổi List sang Set không xóa phép nhân SQL?
17. Set entity equality/hashCode cần lưu ý điều gì?
18. SELECT DISTINCT root làm gì ở JPQL?
19. Vì sao SQL DISTINCT không loại các rows có khác Line/Shipment ID?
20. Hibernate 6 khác các versions cũ thế nào trong root duplicate handling?
21. Làm sao tải Lines rồi Shipments trong cùng EntityManager?
22. Vì sao không em.clear giữa hai fetch queries?
23. Khi tách hai queries, số rows thay đổi thế nào với 3×4 collections?
24. Vì sao phân trang trực tiếp trên JOIN FETCH collection nguy hiểm?
25. Property Hibernate nào giúp fail sớm với pagination over collection fetch?
26. Bước đầu của two-phase page fetching là gì?
27. Vì sao cần sort theo createdAt và ID?
28. `IN :ids` có bảo đảm thứ tự không?
29. Làm sao phục hồi thứ tự parent page IDs?
30. Vì sao phải xử lý list IDs rỗng trước query IN?
31. Khi nào cần chia IN list thành chunks?
32. BatchSize giải quyết vấn đề gì?
33. Hibernate.default_batch_fetch_size dùng cho mục đích gì?
34. Batch fetching có làm fetch type thành EAGER không?
35. SUBSELECT fetching là gì?
36. SUBSELECT có thể overfetch ra sao?
37. EntityGraph có bảo đảm join strategy không?
38. EAGER có loại trừ N+1 hoàn toàn không?
39. Vì sao DTO flat queries thường phù hợp read-only response?
40. Cách group LineRow và ShipmentRow theo orderId?
41. Vì sao không cần fetch Lines để hiển thị lineCount?
42. Dùng COUNT DISTINCT với hai joins có thể vẫn tốn chi phí gì?
43. Khi lọc parent theo một matching child, EXISTS có lợi gì?
44. Vì sao filter child ngay trên fetch join có thể làm collection incomplete?
45. Parent-to-child-to-grandchild khác hai sibling branches thế nào?
46. Nếu thêm third sibling collection, row explosion tăng thế nào?
47. Tại sao LOB columns làm chi phí duplicate rows nặng hơn?
48. EXPLAIN ANALYZE giúp quan sát thông tin gì?
49. Hibernate Statistics có trực tiếp cho chính xác JDBC rows của mọi query không?
50. Có những công cụ nào đo rows/bytes thực tế?
51. Trình tự benchmark hai fetch plans công bằng là gì?
52. Vì sao trả entity trực tiếp từ controller có rủi ro?
53. Khi nào nên dùng child pagination riêng?
54. Khi nào DTO counts-only là lựa chọn phù hợp?
55. Một export lớn nên tổ chức memory và page/chunk thế nào?
56. Có thể có inconsistent response giữa hai SELECT dưới READ COMMITTED không?
57. @Transactional(readOnly=true) có bảo đảm REPEATABLE READ không?
58. Vì sao keyset pagination vẫn cần split child fetches?
59. Làm sao kiểm thử đúng child counts sau multi-query loads?
60. Với 50 Orders, mỗi Order 20 Lines và 5 Shipments, hãy ước lượng JOIN rows và split-fetch rows.
61. Vì sao một query không ném exception vẫn có thể rất chậm?
62. Một query COUNT(parent) có nên chứa FETCH JOIN không?
63. Vì sao cache hit không tự chữa query shape gây nhân dữ liệu?
64. Khi nào phương án JOIN một collection + secondary select phù hợp hơn DTO projection?
65. Làm sao xác định fetch plan tốt nhất cho endpoint của bạn?

---

## 60. Bảng ghi nhớ cuối bài

| Tình huống | Nguyên tắc | Hướng đi |
|---|---|---|
| 1 parent, 1 collection nhỏ | JOIN FETCH có thể hợp lý | Đo rows |
| 1 parent, 2 sibling collections | Rows ≈ tích số child | Split fetch |
| Hibernate hai bags | MultipleBagFetchException | Không multi-join bags |
| Đổi List sang Set | Không chữa row explosion | Chỉ đổi khi domain semantics đúng |
| Dùng DISTINCT | Khử duplicate roots, không giảm JOIN work | Tối ưu query shape |
| Page parents + collections | Không paginate SQL join rows | Page IDs trước |
| `WHERE id IN :ids` | Không giữ order | Reorder theo original IDs |
| N+1 ở nhiều LAZY collections | Batch/Subselect/explicit fetch | Benchmark |
| JPA EntityGraph nhiều to-many | Không bảo đảm tránh multiplication | Inspect SQL |
| Endpoint summary chỉ cần counts | Không tải full collections | COUNT GROUP BY |
| API chỉ cần vài fields | Không hydrate managed graph | DTO projection |
| Lọc parent theo child | Tránh nhân top-level rows | EXISTS |
| Một chain to-many | Cardinality theo nested branch | Tính theo graph |
| LOB lớn ở parent | Row width amplification | Projection |
| Export nhiều Orders | Không giữ huge managed graph | Chunk + DTO |
| Need consistent snapshot | Nhiều queries có thể thấy data khác | Isolation/transaction policy |
| Phân tích thực tế | SQL count chưa đủ | Rows, bytes, plan, heap, latency |
| Hibernate pagination warning | Có thể paginate in memory | Fail-on-pagination guard |
| Nghi ngờ child duplicates | Kiểm IDs/size trong test | Xác minh mapping/queries |

### Sơ đồ quyết định

```text
                  CẦN TẢI ORDER VÀ QUAN HỆ
                              |
                              v
                     Chỉ cần vài columns?
                         /          \
                       CÓ           KHÔNG
                        |              |
                        v              v
                 DTO projection    Cần mấy to-many?
                        |          /           \
                        |       0 hoặc 1      2 trở lên
                        |          |             |
                        |          v             v
                        |       Consider     Có sibling sets?
                        |       JOIN FETCH       |
                        |                        v
                        |                 Tránh JOIN cùng lúc
                        |                        |
                        |                        v
                        |              Có pagination parent?
                        |                 /             \
                        |               CÓ             KHÔNG
                        |                |                |
                        |                v                v
                        |          Query page IDs      Split fetch
                        |                |             / batch
                        |                v
                        |        Fetch collections
                        |        bằng query riêng
                        |                |
                        +----------------+
                              |
                              v
                 Kiểm tra dữ liệu đầy đủ/đúng
                              |
                              v
                  Đo SQL rows, query count,
                    network, heap, latency
                              |
                              v
                   Chọn fetch plan theo
                      workload thực tế
```

**Nguyên tắc cuối bài:** Mục tiêu của JPA performance không phải đưa mọi quan hệ vào **một câu SELECT**, mà là **trả đúng dữ liệu với tổng số hàng, round trips và bộ nhớ hợp lý**. Khi nhiều to-many collections độc lập được JOIN FETCH cùng lúc, số SQL rows có thể tăng theo tích, dù Java chỉ có một managed parent và dù `DISTINCT` đã khử duplicates trong result list. Hibernate `MultipleBagFetchException` là một dấu hiệu khác của cùng fetch-plan risk, nhưng đổi `List` thành `Set` không loại chi phí JOIN. Với endpoint phân trang, hãy **chọn trang parent IDs trước**, rồi **fetch từng collection độc lập trong cùng persistence context** hoặc dùng batch/subselect; với read-only API, cân nhắc **DTO/aggregate projections** và chỉ tải fields thực sự cần. Cuối cùng, chứng minh lựa chọn bằng **SQL row count, query plans, cache-aware benchmark và integration tests có cardinality lớn**, thay vì tối ưu theo số SQL statements đơn lẻ.

