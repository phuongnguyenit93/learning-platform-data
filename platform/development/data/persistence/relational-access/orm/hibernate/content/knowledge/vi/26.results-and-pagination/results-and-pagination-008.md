# Phân trang hai bước theo định danh khi cần tải thêm tập hợp

## 1. Một trang 20 đơn hàng có thật sự chỉ đọc 20 hàng SQL?

Một màn hình quản trị bán hàng cần hiển thị 20 đơn hàng mới nhất. Mỗi đơn có thể gồm nhiều dòng hàng và giao diện cần hiển thị tên sản phẩm, số lượng hoặc giá tiền ngay bên dưới đơn. Với Hibernate ORM, cách viết đầu tiên thường là:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.items
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """, PurchaseOrder.class)
    .setParameter("status", OrderStatus.PAID)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Nhìn vào mã Java, có vẻ query chỉ tải 20 đơn. Nhưng một đơn có 5 dòng hàng tạo ra 5 hàng SQL sau khi JOIN với bảng dòng hàng. Nếu 10.000 đơn đều có dòng hàng, việc giới hạn 20 **hàng SQL** không bảo đảm trả về 20 **đơn đầy đủ**. Hibernate có thể chọn tải tập dữ liệu join rất lớn rồi áp dụng phân trang trong bộ nhớ để tránh làm collection bị cắt cụt.

Kỹ thuật **phân trang hai bước theo định danh** giải quyết sự nhầm lẫn này bằng cách tách hai trách nhiệm:

1. **Bước 1 — chọn đúng trang định danh (ID) của entity gốc:** database giới hạn số PurchaseOrder cần hiển thị.
2. **Bước 2 — tải entity và collection của đúng những ID đó:** Hibernate nạp toàn bộ association cần thiết cho những parent đã chọn, nhưng không đặt LIMIT/OFFSET lên hàng join.

Kết quả là ứng dụng giữ được cả **độ chính xác của trang parent** lẫn **tính đầy đủ của collection**. Đây là một chiến lược quan trọng trong chương **Kết quả và phân trang** của Hibernate ORM.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao collection fetch join và LIMIT/OFFSET không nên được kết hợp trực tiếp.
- Hiểu row multiplication, cảnh báo Hibernate về pagination in memory và cơ chế fail fast.
- Viết truy vấn ID-first, truy vấn fetch theo tập ID và khôi phục đúng thứ tự ban đầu.
- Kết hợp COUNT, Page, Slice và keyset pagination với hai bước tải dữ liệu.
- Xử lý bộ lọc theo child bằng EXISTS thay vì JOIN nhân bản parent.
- Biết giới hạn khi tải nhiều collection, collection rất lớn, kết quả DTO và N+1.
- Hiểu khoảng thời gian giữa hai SELECT, transaction isolation và dữ liệu thay đổi đồng thời.
- Thiết kế kiểm thử SQL/ORM để bảo đảm page size, thứ tự và collection đầy đủ.
- Đo chi phí thật bằng SQL logging, số hàng trả về và EXPLAIN ANALYZE.

Ví dụ dùng Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA và PostgreSQL. Những ví dụ về hành vi cảnh báo, câu SQL và API provider-specific cần được xác nhận theo phiên bản Hibernate thực tế. Nguyên lý cardinality của JOIN và LIMIT vẫn đúng bất kể framework nào.

## 2. Parent, child và đơn vị phân trang

Giả sử PurchaseOrder là entity gốc, OrderItem là tập hợp con:

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ PURCHASE_ORDERS : places
    PURCHASE_ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : referenced
    PURCHASE_ORDERS {
        bigint id PK
        bigint customer_id FK
        bigint tenant_id
        varchar status
        numeric total_amount
        timestamp created_at
        timestamp deleted_at
    }
    ORDER_ITEMS {
        bigint id PK
        bigint order_id FK
        bigint product_id FK
        integer line_number
        integer quantity
    }
~~~

Với trang danh sách đơn hàng, **đơn vị được phân trang là PurchaseOrder**. Mỗi đơn có thể có 0, 1, 3, 100 hoặc hàng nghìn OrderItem.

Ví dụ:

| Order ID | Số OrderItem | Số hàng khi LEFT JOIN |
|---:|---:|---:|
| 101 | 3 | 3 |
| 102 | 0 | 1 |
| 103 | 5 | 5 |
| 104 | 1 | 1 |
| 105 | 20 | 20 |

LEFT JOIN tạo ít nhất một hàng cho đơn không có item: các cột bên child là NULL. Nếu join một collection, tổng số hàng là xấp xỉ:

~~~text
joinedRows = sum(max(1, childCount(order))) trên các order
~~~

Với bảng trên, 5 PurchaseOrder tạo 30 hàng SQL. Một trang 5 parent không có nghĩa một query join chỉ trả 5 rows.

### 2.1. SQL LIMIT cắt hàng sau JOIN

~~~sql
SELECT
    o.id AS order_id,
    i.id AS item_id
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
ORDER BY o.id
LIMIT 4;
~~~

Kết quả có thể là:

| order_id | item_id |
|---:|---:|
| 101 | 1001 |
| 101 | 1002 |
| 101 | 1003 |
| 102 | NULL |

Database mới chỉ trả về **2 parent**, dù LIMIT 4. Tăng LIMIT tới 6 cũng không bảo đảm 6 parent: giới hạn vẫn nằm ở cấp hàng join. Nếu một Order có 100 items, một page SQL LIMIT 20 có thể chỉ chứa phần đầu collection của một Order.

### 2.2. Vì sao cắt collection là sai về ngữ nghĩa?

Nếu Hibernate coi collection đã được khởi tạo sau fetch join, ứng dụng có thể hiểu:

~~~java
order.getItems().size()
~~~

là tổng số item của đơn. Nếu kết quả SQL bị LIMIT cắt giữa collection, giá trị trên sẽ không phải toàn bộ item trong database. Vì vậy Hibernate thường không áp dụng pagination trực tiếp xuống SQL trong tình huống collection fetch join có limit/offset; thay vào đó có thể tải tất cả hàng join phù hợp, khử lặp root và cắt trang trong memory.

Điều này ưu tiên tính đầy đủ của object graph nhưng có thể tạo vấn đề nghiêm trọng về memory, network và độ trễ.

## 3. Dấu hiệu Hibernate đang phân trang trong bộ nhớ

Một truy vấn có collection fetch join kết hợp setFirstResult/setMaxResults:

~~~java
select distinct o
from PurchaseOrder o
left join fetch o.items
order by o.createdAt desc, o.id desc
~~~

thường dẫn tới cảnh báo:

~~~text
HHH90003004: firstResult/maxResults specified with collection fetch;
applying in memory
~~~

Trong Hibernate 6, cơ chế này giúp tránh cắt collection khi ORM không thể áp dụng LIMIT lên parent mà vẫn fetch đủ child theo cách thông thường.

### 3.1. Vì sao page có vẻ đúng vẫn có thể chậm?

Giả sử có:

- 50.000 đơn thỏa filter.
- Trung bình 8 dòng hàng/đơn.
- Page size = 20.

Một query join toàn bộ đơn có thể tạo khoảng **400.000 hàng SQL** trước khi Hibernate lấy 20 root entity cần hiển thị. DTO cuối cùng chỉ có 20 đơn nên kiểm thử chỉ kiểm tra size có thể không phát hiện vấn đề. Database, driver, network và JVM đã thực hiện lượng công việc lớn hơn rất nhiều.

Các biểu hiện:

- Endpoint chậm dần khi tổng số đơn tăng, dù page size cố định.
- Heap tăng mạnh hoặc GC nhiều.
- Chỉ thấy một câu SQL nhưng câu đó trả quá nhiều rows.
- Trong log không có LIMIT/OFFSET ở query join, mặc dù đã gọi Pageable.
- Hibernate phát cảnh báo pagination over collection fetch.

### 3.2. Bật cấu hình fail fast

Spring Boot:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        query:
          fail_on_pagination_over_collection_fetch: true
~~~

Hoặc Hibernate property trực tiếp:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Khi bật và Hibernate phát hiện trường hợp tương ứng, nó ném exception thay vì lặng lẽ phân trang kết quả collection fetch trong bộ nhớ. Đây là một guardrail hữu ích cho development/test; với production, nên cân nhắc bật để tránh một truy vấn mới âm thầm gây quá tải.

**Cấu hình chỉ phát hiện sai lầm, không tự tối ưu query.** Phải thiết kế lại truy vấn để database phân trang đúng tập root trước khi fetch collection.

### 3.3. DISTINCT không giải quyết gốc rễ

~~~hql
select distinct o
from PurchaseOrder o
left join fetch o.items
~~~

DISTINCT có ý nghĩa khử duplicate entity result, nhưng các hàng SQL khác item_id vẫn khác nhau. Kể cả Hibernate 6 tự khử lặp root sau fetch join, số hàng SQL cần đọc và số OrderItem cần dựng không tự giảm chỉ vì thêm DISTINCT. Không dùng DISTINCT như cách sửa pagination in memory.

## 4. Hai bước đúng: ID page trước, fetch graph sau

Một hình dung đầy đủ:

~~~mermaid
flowchart TD
    A[Request: page 0 size 20 + filter] --> B[Query 1: chọn ID của 20 Order]
    B --> C[Database LIMIT/OFFSET ở parent ID]
    C --> D{Có ID?}
    D -->|Không| E[Trả trang rỗng và tổng count phù hợp]
    D -->|Có| F[Query 2: SELECT Order LEFT JOIN FETCH items WHERE ID IN danh sách]
    F --> G[Hibernate hydrate các entity và collection hoàn chỉnh]
    G --> H[Tạo Map theo Order ID]
    H --> I[Khôi phục thứ tự từ danh sách ID bước 1]
    I --> J[Map DTO và trả trang]
~~~

### 4.1. Bước 1 — chỉ chọn ID của parent

PostgreSQL:

~~~sql
SELECT o.id
FROM purchase_orders o
WHERE o.tenant_id = :tenant_id
  AND o.status = 'PAID'
  AND o.deleted_at IS NULL
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20 OFFSET 0;
~~~

Mỗi hàng trong kết quả là một ID đơn hàng. Chưa có JOIN to-many nên LIMIT 20 tương ứng tối đa 20 PurchaseOrder.

HQL:

~~~hql
select o.id
from PurchaseOrder o
where o.tenantId = :tenantId
  and o.status = :status
  and o.deletedAt is null
order by o.createdAt desc, o.id desc
~~~

Code phân trang dùng setFirstResult/setMaxResults trên query ID; database có thể áp dụng LIMIT/OFFSET theo dialect.

### 4.2. Bước 2 — lấy đúng những parent đó cùng collection

HQL:

~~~hql
select distinct o
from PurchaseOrder o
left join fetch o.items
where o.id in :ids
  and o.tenantId = :tenantId
  and o.deletedAt is null
~~~

Truy vấn thứ hai **không có Pageable, setFirstResult hay setMaxResults**. Vì chỉ có tối đa 20 ID, Hibernate lấy toàn bộ collection cho đúng tập parent của trang mà không phải quét mọi đơn trong hệ thống.

SQL minh họa:

~~~sql
SELECT o.*, i.*
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id IN (?, ?, ?, ...)
  AND o.tenant_id = ?
  AND o.deleted_at IS NULL;
~~~

Một Order trong page có 30 items sẽ tạo 30 hàng SQL, nhưng tất cả 30 là dữ liệu thực sự được yêu cầu để tải đầy đủ collection. Độ lớn truy vấn thứ hai phụ thuộc tổng items của **những parent được chọn**, không còn phụ thuộc toàn bộ số đơn thỏa filter.

### 4.3. Tại sao dùng LEFT JOIN FETCH?

Nếu dùng INNER JOIN FETCH, các Order không có item bị loại khỏi kết quả bước 2, dù ID bước 1 đã chọn chúng. Khi cần giữ cả Order có collection rỗng, LEFT JOIN FETCH thích hợp hơn.

### 4.4. Không cần ORDER BY ở bước 2 để giữ page order

SQL IN không bảo đảm thứ tự kết quả bằng thứ tự danh sách ID đầu vào. Ví dụ:

~~~text
IDs bước 1 = [105, 101, 104, 102]
Fetch kết quả = [101, 102, 104, 105]
~~~

Nếu trả trực tiếp thứ tự của query fetch, UI hiển thị sai thứ tự đã phân trang. Ta phải **sắp lại theo danh sách ID từ bước 1** trong Java.

### 4.5. Bước 2 không được tự phân trang

Sai:

~~~java
fetchQuery.setMaxResults(pageSize);
~~~

Khi query thứ hai có collection fetch join, limit ở đây lại đưa ứng dụng về bài toán cũ. Phân trang đã hoàn tất ở query ID; query fetch phải tải đủ items của các parent được chọn.

## 5. Cấu trúc entity Java dùng trong ví dụ

Ta có thể dùng hai entity sau (rút gọn nhưng thống nhất các thuộc tính được dùng trong truy vấn):

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    @OrderBy("lineNumber ASC, id ASC")
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Instant getCreatedAt() { return createdAt; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public List<OrderItem> getItems() { return items; }
}

enum OrderStatus { DRAFT, PAID, CANCELLED }
~~~

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "line_number", nullable = false)
    private int lineNumber;

    @Column(name = "sku_snapshot", nullable = false)
    private String skuSnapshot;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected OrderItem() {}

    public Long getId() { return id; }
    public int getLineNumber() { return lineNumber; }
    public String getSkuSnapshot() { return skuSnapshot; }
    public int getQuantity() { return quantity; }
    public BigDecimal getUnitPrice() { return unitPrice; }
}
~~~

Mỗi public class/enum thực tế nằm trong file Java riêng; các đoạn trên minh họa mapping, không bao gồm đầy đủ constructor, setter nghiệp vụ và migration. Dùng skuSnapshot để màn hình có SKU đã được chốt khi tạo đơn mà không vô tình kích hoạt lazy-loading tới Product ở bước map DTO.

### 5.1. Thứ tự của collection và thứ tự của page là hai thứ khác

Annotation @OrderBy trên items sắp các item trong **từng đơn** theo lineNumber/id. Nó không bảo đảm thứ tự danh sách PurchaseOrder trong một Page. Thứ tự parent được quyết định bởi query ID ở bước 1 và phải được bảo toàn độc lập.

Ngoài ra @OrderBy không tương đương @OrderColumn: một annotation sắp dựa trên thuộc tính, annotation kia lưu vị trí collection trong database với semantics khác. Chọn theo domain model của ứng dụng.

## 6. Repository Spring Data JPA: hai query chuyên trách

Repository:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.Collection;
import java.util.List;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    // Query 1: chỉ phân trang ID của parent.
    @Query("""
        select o.id
        from PurchaseOrder o
        where o.tenantId = :tenantId
          and o.status = :status
          and o.deletedAt is null
        order by o.createdAt desc, o.id desc
        """)
    List<Long> findPageIds(
        @Param("tenantId") Long tenantId,
        @Param("status") OrderStatus status,
        Pageable pageable
    );

    // Query 2: fetch đầy đủ items cho một tập ID đã chọn.
    @Query("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.items
        where o.id in :ids
          and o.tenantId = :tenantId
          and o.deletedAt is null
        """)
    List<PurchaseOrder> fetchWithItems(
        @Param("ids") Collection<Long> ids,
        @Param("tenantId") Long tenantId
    );

    // Query 3 (tùy nhu cầu): tổng số parent của bộ lọc.
    @Query("""
        select count(o)
        from PurchaseOrder o
        where o.tenantId = :tenantId
          and o.status = :status
          and o.deletedAt is null
        """)
    long countVisibleOrders(
        @Param("tenantId") Long tenantId,
        @Param("status") OrderStatus status
    );
}
~~~

Phân biệt:

- **findPageIds**: trả List<Long>, có Pageable, không fetch collection.
- **fetchWithItems**: trả entity graph, nhận tập IDs nhỏ, **không có Pageable**.
- **countVisibleOrders**: đếm số PurchaseOrder, không đếm OrderItem.

Tổng cộng một request Page đầy đủ có thể thực thi **ba SQL SELECT**: lấy ID trang, fetch entity/items và đếm tổng. Tên gọi **phân trang hai bước** chỉ hai bước tải nội dung; count là tác vụ metadata của Page, không phải một lần tải tập hợp thứ ba.

### 6.1. Hạn chế Pageable.sort trong query ID

Query findPageIds đã định nghĩa thứ tự cố định createdAt DESC, id DESC. Nếu truyền vào Pageable có Sort do client điều khiển, Spring Data có thể bổ sung hoặc xử lý sorting theo API/version, làm thay đổi thứ tự mong muốn.

Một phương án đơn giản là service nhận page/size và tạo:

~~~java
Pageable idPage = PageRequest.of(pageNumber, pageSize);
~~~

Đây là Pageable không mang Sort động. Nếu UI cần nhiều kiểu sắp xếp, thiết kế từng lựa chọn sort hợp lệ với tie-breaker cố định, đồng thời đảm bảo bước 1 và cursor/page contract tương ứng.

### 6.2. Vì sao không trả Page<PurchaseOrder> trực tiếp từ fetchWithItems?

Nếu thêm Pageable vào fetchWithItems, Hibernate sẽ gặp lại collection fetch join + pagination. Count query không sửa được vấn đề này. Truy vấn bước 2 được giới hạn theo **ID**, không theo LIMIT/OFFSET.

### 6.3. Đừng đưa tập IDs rỗng vào IN

SQL IN () có cú pháp/hành vi khác nhau theo provider/dialect. Nếu bước 1 trả List rỗng, service nên bỏ qua bước fetch hoàn toàn. Khi page vượt trang cuối, vẫn có thể cần count để báo totalElements chính xác.

## 7. Service hoàn chỉnh: chọn ID, fetch, khôi phục thứ tự, tạo DTO

Trả entity trực tiếp ra HTTP có thể kéo theo lazy-loading, JSON cyclic references và rò rỉ trường dữ liệu. Ta tạo DTO cho use case:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderItemRow(
    Long id,
    int lineNumber,
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderPageRow(
    Long id,
    Instant createdAt,
    OrderStatus status,
    BigDecimal totalAmount,
    List<OrderItemRow> items
) {}
~~~

Trong project thực tế, đặt hai public record vào các source file riêng.

Service:

~~~java
import org.springframework.data.domain.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class OrderPageService {
    private final PurchaseOrderRepository repository;

    public OrderPageService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<OrderPageRow> findPaidOrders(
            Long trustedTenantId,
            int pageNumber,
            int pageSize) {

        if (trustedTenantId == null) {
            throw new IllegalArgumentException("Tenant bắt buộc");
        }
        if (pageNumber < 0 || pageSize < 1 || pageSize > 100
                || (long) pageNumber * pageSize > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Thông số phân trang không hợp lệ");
        }

        Pageable pageable = PageRequest.of(pageNumber, pageSize);
        OrderStatus status = OrderStatus.PAID;

        // 1. Chỉ chọn ID ở database.
        List<Long> ids = repository.findPageIds(
            trustedTenantId, status, pageable);

        // 2. Metadata count, độc lập với phép fetch join.
        long total = repository.countVisibleOrders(
            trustedTenantId, status);

        if (ids.isEmpty()) {
            return new PageImpl<>(List.of(), pageable, total);
        }

        // 3. Fetch toàn bộ collection cho đúng tập ID.
        List<PurchaseOrder> fetched = repository.fetchWithItems(
            ids, trustedTenantId);

        Map<Long, PurchaseOrder> byId = fetched.stream()
            .collect(Collectors.toMap(
                PurchaseOrder::getId,
                Function.identity()
            ));

        // 4. IN không giữ thứ tự: tái dựng theo danh sách bước 1.
        List<OrderPageRow> content = ids.stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .map(OrderPageService::toRow)
            .toList();

        return new PageImpl<>(content, pageable, total);
    }

    private static OrderPageRow toRow(PurchaseOrder order) {
        List<OrderItemRow> items = order.getItems().stream()
            .map(i -> new OrderItemRow(
                i.getId(),
                i.getLineNumber(),
                i.getSkuSnapshot(),
                i.getQuantity(),
                i.getUnitPrice()
            ))
            .toList();

        return new OrderPageRow(
            order.getId(),
            order.getCreatedAt(),
            order.getStatus(),
            order.getTotalAmount(),
            items
        );
    }
}
~~~

Điểm quan trọng:

1. **Pageable chỉ áp dụng cho query ID**.
2. **fetchWithItems không nhận Pageable**.
3. Query ID và count dùng cùng điều kiện tenant, status, deletedAt.
4. Query fetch vẫn ràng buộc tenant/deletedAt vì đây là dữ liệu cần kiểm soát quyền truy cập.
5. Map<Long, PurchaseOrder> cho phép phục hồi thứ tự root từ IDs.
6. DTO được tạo trong transaction, khi collection đã được fetch.
7. Không cần gán vị trí của item dựa theo vị trí parent.

### 7.1. Vì sao dùng Map thay cho sorted() trực tiếp?

Có thể sắp kết quả fetch bằng comparator theo createdAt/id, nhưng thuật toán đó lặp lại logic ORDER BY tại Java, dễ lệch khi query ID có nhiều tiêu chí động, collation khác hoặc nullable sort values.

Map + đi theo danh sách ID đầu vào:

~~~java
Map<Long, PurchaseOrder> byId = fetched.stream()
    .collect(Collectors.toMap(
        PurchaseOrder::getId,
        Function.identity()
    ));

List<PurchaseOrder> ordered = ids.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
~~~

đảm bảo **đúng thứ tự của query ID** mà không cần tái triển khai so sánh.

### 7.2. Vì sao filter null ở bước map?

Nếu một Order bị xóa hoặc trở nên không còn hợp lệ giữa hai SELECT, fetchWithItems có thể không trả ID đó. Đoạn code filter(Objects::nonNull) tránh NullPointerException, nhưng **không tự giải quyết mâu thuẫn snapshot**: nội dung page có thể ngắn hơn pageSize. Trong ứng dụng cần tính nhất quán mạnh, phải quyết định transaction isolation/snapshot hoặc chiến lược retry theo nghiệp vụ.

Không âm thầm lấy thêm một ID “bù” mà không đánh giá lại sort/cursor và các điều kiện filter; điều đó có thể làm trang bị trùng hoặc bỏ sót entity.

### 7.3. Không lạm dụng read-only transaction

@Transactional(readOnly=true) có thể giúp một số tối ưu trong Spring/Hibernate và giữ persistence context hoạt động lúc map DTO. Tuy nhiên nó **không bảo đảm** các câu SELECT nhìn thấy cùng một snapshot ở mọi isolation level, cũng không phải kiểm soát quyền đọc dữ liệu.

## 8. Các trường hợp không có item, item trùng và thứ tự collection

Hai bước phải giữ nguyên kết quả hợp lệ của các parent đặc biệt.

### 8.1. Parent có collection rỗng

Giả sử query ID trả [102, 103], trong đó Order 102 không có OrderItem. LEFT JOIN FETCH vẫn trả Order 102 với collection rỗng. INNER JOIN FETCH sẽ làm Order 102 biến mất trong bước 2, phá vỡ ngữ nghĩa trang.

### 8.2. Hibernate 6 xử lý root duplicate

Khi JOIN FETCH một collection, cùng Order xuất hiện trên nhiều hàng SQL; Hibernate 6 có cơ chế loại root entity trùng trong result list cho fetch join. Dùng select distinct o trong JPQL/HQL vẫn có thể biểu thị ngữ nghĩa rõ ràng, nhưng **không loại bỏ chi phí nhận các hàng child**.

Không dùng result list size của một join không được thiết kế rõ để suy ra số hàng SQL thực tế. Kiểm tra count, Statistics và execution plan riêng.

### 8.3. List/BAG, Set và duplicate child

@OneToMany kiểu List không có @OrderColumn thường được Hibernate xem là bag theo semantics. Một phép fetch join một collection có thể phù hợp, nhưng fetch nhiều bag cùng lúc có thể ném MultipleBagFetchException.

Đổi List thành Set chỉ để né exception không chữa được Cartesian multiplication; nó còn thay đổi semantics của collection, equals/hashCode và khả năng giữ phần tử trùng/thứ tự.

### 8.4. Không lọc child ngay trong FETCH JOIN nếu muốn collection đầy đủ

Một query dễ gây hiểu nhầm:

~~~hql
select distinct o
from PurchaseOrder o
join fetch o.items i
where i.quantity >= :minimumQty
~~~

Ý định có thể là “chỉ chọn Order chứa item có quantity đủ lớn”, nhưng fetch join này có thể khởi tạo collection **chỉ với các item thỏa điều kiện**, không phải toàn bộ items của Order. Cách đúng khi cần chọn parent theo child và sau đó tải toàn bộ children:

1. Bước 1 dùng EXISTS để lọc Order ID.
2. Bước 2 fetch o.items theo IDs, **không thêm điều kiện lọc i.quantity vào fetch join**.

Chỉ lọc child trong query riêng nếu mục tiêu thật sự là trả một danh sách child đã lọc, không phải thay đổi trạng thái một collection đầy đủ.

## 9. Bộ lọc tùy chọn và JOIN to-many trong bước ID

Giả sử màn hình yêu cầu:

~~~text
Các đơn PAID của tenant hiện tại
được tạo sau thời điểm A
và có ít nhất một OrderItem thuộc productId = 900.
~~~

Cách dễ viết nhưng cần cẩn thận:

~~~hql
select o.id
from PurchaseOrder o
join o.items i
where i.product.id = :productId
order by o.createdAt desc, o.id desc
~~~

Nếu một đơn có 3 OrderItem cùng productId, query ID có thể trả cùng ID 3 lần. Khi LIMIT/OFFSET, các vị trí phân trang bị chiếm bởi duplicate ID, khiến số parent thực tế trong trang thấp hơn dự kiến.

### 9.1. Dùng EXISTS để chọn parent

~~~hql
select o.id
from PurchaseOrder o
where o.tenantId = :tenantId
  and o.status = :status
  and o.deletedAt is null
  and exists (
      select 1
      from OrderItem i
      where i.order = o
        and i.product.id = :productId
  )
order by o.createdAt desc, o.id desc
~~~

EXISTS chỉ xác định parent có ít nhất một child thỏa điều kiện, không tạo hàng lặp trong SELECT ID ngoài. Vì vậy LIMIT/OFFSET tiếp tục áp dụng đúng đơn vị Order.

### 9.2. Query COUNT phải cùng điều kiện EXISTS

~~~hql
select count(o)
from PurchaseOrder o
where o.tenantId = :tenantId
  and o.status = :status
  and o.deletedAt is null
  and exists (
      select 1
      from OrderItem i
      where i.order = o
        and i.product.id = :productId
  )
~~~

Nếu content query có EXISTS nhưng count query thiếu EXISTS, totalElements sẽ sai. Với query động, nên tái sử dụng **logic dựng điều kiện** (Criteria/Specification) trên từng query độc lập, không sao chép Predicate có Root thuộc query khác.

### 9.3. Hai điều kiện child khác nhau có cần cùng một item?

Ví dụ:

~~~text
Order chứa một item có productId = 900
AND Order chứa một item quantity >= 10.
~~~

Hai EXISTS độc lập cho phép **hai item khác nhau** thỏa hai điều kiện. Nếu business yêu cầu **cùng một OrderItem** phải có productId=900 và quantity>=10, đặt cả hai điều kiện trong **một EXISTS**. Việc tách hai bước pagination không thay thế phân tích đúng ngữ nghĩa predicate.

### 9.4. Khi nào dùng DISTINCT ở query ID?

Nếu buộc phải JOIN to-many để sắp xếp/aggregate, có thể dùng SELECT DISTINCT o.id hoặc GROUP BY root tùy query, nhưng phải bảo đảm ORDER BY hợp lệ theo database/dialect và số parent không bị nhân bản.

Không dùng DISTINCT như phản xạ chung: với ORDER BY child column không nằm trong SELECT DISTINCT, một số database có thể từ chối query hoặc định nghĩa kết quả không rõ. Khi cần xếp hạng theo child, thường phải tính metric aggregate theo parent rồi phân trang các metric đó.

## 10. Khi sort dựa vào dữ liệu child

Giả sử user muốn “đơn có số dòng hàng nhiều nhất” đứng đầu. Không thể chỉ JOIN OrderItem rồi ORDER BY i.id để lấy page parent — một parent có thể xuất hiện nhiều lần và thứ tự không phản ánh itemCount.

Đầu tiên tạo **một hàng cho mỗi parent**:

~~~sql
SELECT
    o.id,
    COUNT(i.id) AS item_count
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.tenant_id = :tenantId
  AND o.deleted_at IS NULL
GROUP BY o.id
ORDER BY item_count DESC, o.id DESC
LIMIT 20 OFFSET 0;
~~~

Query này trả ID và metric item_count ở cấp parent. Bước 2 vẫn dùng tập ID đó để fetch toàn bộ items. Khi reconstruct order, lấy thứ tự từ kết quả bước 1 (hoặc danh sách ID đã trích) chứ không để query fetch quyết định.

### 10.1. HQL projection cho ID và metric

Trong Hibernate/JPA, có thể dùng constructor projection:

~~~java
public record OrderRankKey(Long id, Long itemCount) {}
~~~

~~~hql
select new com.example.shop.dto.OrderRankKey(
    o.id,
    count(i.id)
)
from PurchaseOrder o
left join o.items i
where o.tenantId = :tenantId
  and o.deletedAt is null
group by o.id
order by count(i.id) desc, o.id desc
~~~

Sau đó setFirstResult/setMaxResults trên query projection có một row per Order. Khóa tie-breaker o.id làm thứ tự ổn định.

### 10.2. Nếu filter theo child và sort theo child khác

Định nghĩa rõ việc COUNT tính tất cả item hay chỉ item đã match filter. Trong SQL, đặt điều kiện ở WHERE, ON hoặc một correlated subquery có thể cho kết quả khác nhau. Bước ID phải thực thi **đúng semantics của trang**; bước fetch chỉ giải quyết việc tải dữ liệu liên quan.

## 11. Count query: số entity gốc, không phải số hàng JOIN

Một API kiểu Page cần tổng số phần tử và tổng số trang.

Không nên đếm:

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id;
~~~

nếu đơn vị trang là PurchaseOrder, vì Order có 5 items bị tính 5 lần.

Những cách đếm parent hợp lệ tùy bài toán:

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
WHERE o.status = 'PAID';
~~~

Hoặc khi cần lọc theo child:

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
WHERE o.status = 'PAID'
  AND EXISTS (
      SELECT 1
      FROM order_items i
      WHERE i.order_id = o.id
        AND i.quantity >= 10
  );
~~~

Hoặc nếu join thật sự bắt buộc:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id
WHERE i.quantity >= 10;
~~~

EXISTS thường diễn đạt rõ yêu cầu “parent có ít nhất một child” và tránh tạo tập kết quả ngoài bị nhân bản. Tuy nhiên hiệu năng phụ thuộc optimizer/index; không khẳng định EXISTS nhanh hơn mọi JOIN trong mọi trường hợp.

### 11.1. Page, Slice và List khác nhau

| Kết quả API | Cần COUNT tổng? | Đặc điểm |
|---|---|---|
| Page<T> | Thường cần, có thể tối ưu ở trường hợp đặc biệt | Biết totalElements/totalPages |
| Slice<T> | Không bắt buộc | Biết có trang kế tiếp bằng cách đọc thêm một phần tử |
| List<T> | Không tự count | Chỉ trả dữ liệu của một lượt truy vấn |

Nếu UI không cần tổng số trang, Slice giúp tránh count query đắt. Nhưng ngay cả khi dùng Slice, **bước ID vẫn phải phân trang root**, không áp dụng LIMIT trực tiếp lên collection fetch join.

### 11.2. Bước 2 không dùng COUNT để chọn IDs

COUNT là metadata. Nó không xác định những Order nào nằm trong page. Thứ tự và giới hạn của ID query mới xác định tập entity phải fetch. Đừng trộn count query với fetch join để cố giải quyết cùng lúc cả hai việc.

### 11.3. Trang ngoài phạm vi

Nếu pageNumber vượt trang cuối, danh sách ID rỗng. Một Page có thể vẫn báo totalElements lớn hơn 0, vì database có dữ liệu nhưng không có dữ liệu ở offset yêu cầu. Không mặc định totalElements=0 chỉ vì IDs của trang đó rỗng.

## 12. Tối ưu không cần count: Slice bằng cách lấy size + 1 ID

Nếu UI chỉ có nút “Tải thêm”, ta có thể chọn **pageSize+1 ID** ở bước 1:

~~~java
int pageSize = 20;
int offset = Math.toIntExact((long) pageNumber * pageSize);

List<Long> candidateIds = entityManager.createQuery("""
    select o.id
    from PurchaseOrder o
    where o.tenantId = :tenantId
      and o.deletedAt is null
    order by o.createdAt desc, o.id desc
    """, Long.class)
    .setParameter("tenantId", tenantId)
    .setFirstResult(offset)
    .setMaxResults(pageSize + 1)
    .getResultList();

boolean hasNext = candidateIds.size() > pageSize;
List<Long> visibleIds = candidateIds.stream()
    .limit(pageSize)
    .toList();
~~~

Chỉ visibleIds được đưa vào query fetch thứ hai. ID thứ pageSize+1 được dùng để xác định hasNext, **không được fetch rồi vô tình trả thêm vào page**.

### 12.1. Bẫy khi dùng PageRequest với size + 1

Không đơn giản gọi:

~~~java
PageRequest.of(pageNumber, pageSize + 1)
~~~

nếu muốn offset bằng pageNumber * pageSize. PageRequest tính offset dựa vào kích thước mới (pageSize+1), khiến trang thứ hai, thứ ba... bị lệch. Cần kiểm soát offset riêng hoặc dùng abstraction Slice của Spring Data có semantics đúng.

### 12.2. Trả Slice sau khi fetch

~~~java
return new SliceImpl<>(
    content,
    PageRequest.of(pageNumber, pageSize),
    hasNext
);
~~~

Tương tự Page, content được tạo từ các IDs đã lấy, khôi phục thứ tự sau fetch. Vẫn phải xử lý khả năng parent biến mất giữa hai truy vấn.

### 12.3. Tại sao Slice không phải cách sửa collection fetch pagination?

Slice chỉ tránh count và cho biết còn dữ liệu không. Nếu truy vấn chính vẫn dùng fetch join collection kèm limit, Hibernate vẫn đối mặt row multiplication và nguy cơ in-memory pagination. Tách ID-first là kỹ thuật giải quyết nguyên nhân gốc.

## 13. Offset pagination so với keyset pagination

Với OFFSET:

~~~sql
SELECT id
FROM purchase_orders
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
~~~

Database có thể phải bỏ qua nhiều hàng trước khi trả trang sâu. OFFSET còn có thể gây lặp/mất bản ghi giữa hai request khi có insert/delete phía trước offset.

### 13.1. Keyset chọn các ID sau cursor

Giả sử sort theo createdAt DESC, id DESC. Trang đầu:

~~~sql
SELECT id, created_at
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND deleted_at IS NULL
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Trang tiếp theo dùng sort key của hàng cuối trang trước:

~~~sql
SELECT id, created_at
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND deleted_at IS NULL
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

PostgreSQL có thể biểu diễn điều kiện tương đương bằng row-value comparison:

~~~sql
AND (created_at, id) < (:lastCreatedAt, :lastId)
~~~

HQL:

~~~hql
select o.id, o.createdAt
from PurchaseOrder o
where o.tenantId = :tenantId
  and o.deletedAt is null
  and (
      o.createdAt < :lastCreatedAt
      or (
          o.createdAt = :lastCreatedAt
          and o.id < :lastId
      )
  )
order by o.createdAt desc, o.id desc
~~~

### 13.2. Vẫn fetch bước 2 theo ID

Keyset chỉ thay **cách chọn page IDs**. Bước 2 vẫn:

~~~hql
select distinct o
from PurchaseOrder o
left join fetch o.items
where o.id in :ids
~~~

Không thêm limit vào bước 2. Cursor được xây từ thứ tự/keys của **bước chọn ID**, không từ thứ tự bất kỳ của kết quả fetch.

### 13.3. Cursor phải có semantics nhất quán

Nếu user thay status, tenant, keyword hoặc sort, cursor cũ có thể không còn hợp lệ. API nên encode hoặc ràng buộc cursor với filter/sort đã dùng. Với cột sort nullable, cần định nghĩa thứ tự NULL và điều kiện keyset phù hợp; biểu thức so sánh đơn giản ở trên giả định createdAt non-null.

### 13.4. Keyset không bảo đảm snapshot bất biến

Nếu order được update sort key từ cũ sang mới giữa hai request, keyset cũng có thể trả kết quả khác với một snapshot bất biến. Nếu nghiệp vụ cần xuất dữ liệu nhất quán qua nhiều trang, cân nhắc snapshot token, immutable sort key, transaction/replica snapshot hoặc export job phù hợp.

## 14. Một transaction có bảo đảm hai truy vấn đọc cùng dữ liệu?

Tách thành hai SELECT tạo ra một khoảng thời gian giữa:

~~~text
T1: chọn Order IDs [105, 104, 103]
T2: transaction khác xóa Order 104 hoặc cập nhật status
T3: fetch các Order theo IDs [105, 104, 103]
~~~

Ở PostgreSQL với isolation READ COMMITTED, mỗi statement có thể dùng snapshot tại thời điểm bắt đầu statement, kể cả hai statement chạy trong cùng một transaction Spring. Query fetch có thể thiếu 104; count chạy sau đó có thể cũng đã thay đổi.

### 14.1. Mức nhất quán chấp nhận được

| Use case | Lựa chọn có thể phù hợp |
|---|---|
| Danh sách quản trị thông thường | READ COMMITTED, chấp nhận dữ liệu thay đổi nhẹ |
| Báo cáo cần một snapshot trong transaction | Cân nhắc REPEATABLE READ, đặc biệt trên PostgreSQL |
| Quy trình cần đảm bảo một Order không đổi trong lúc thao tác | Khóa/optimistic version theo nghiệp vụ, không chỉ readOnly |
| Export nhiều trang trong thời gian dài | Snapshot/point-in-time read model hoặc cơ chế export nhất quán |

REPEATABLE READ có chi phí và hành vi MVCC khác; không áp dụng mọi nơi chỉ vì query có hai bước. Một transaction dài có thể giữ snapshot lâu và tăng áp lực tài nguyên ở database.

### 14.2. Trạng thái managed entity

Nếu persistence context đã chứa một PurchaseOrder trước query fetch, Hibernate thường dùng cùng entity instance theo identity map. Khi đó trạng thái đang managed có thể ảnh hưởng việc bạn quan sát dữ liệu; native/bulk updates trong transaction khác hoặc cùng context có thể khiến entity state stale.

Để kiểm thử query thật, đừng dùng một persistence context đã chứa sẵn toàn bộ Order và items; dùng transaction/context mới hoặc clear sau fixture khi phù hợp.

### 14.3. Khi parent mất giữa hai bước

Một số chính sách:

- Chấp nhận trang thiếu một Order vừa bị xóa và trả các Order còn lại.
- Thử lại toàn bộ ID page + fetch một số lần giới hạn nếu màn hình cần page đủ.
- Dùng transaction isolation nhất quán hơn nếu báo cáo cần snapshot chính xác.

Không coi việc thiếu Order là bằng chứng tự động cho lỗi thuật toán; nó có thể là một thay đổi đồng thời hợp lệ. Tuy nhiên nếu thiếu thường xuyên ngay cả khi không có ghi concurrent, cần kiểm tra JOIN type, tenant filter, soft delete và mapping.

## 15. Tenant, soft delete và filter bảo mật trong hai bước

Nếu hệ thống multi-tenant, ID query phải có tenant filter:

~~~hql
where o.tenantId = :trustedTenantId
  and o.deletedAt is null
~~~

Query fetch thứ hai cũng nên áp dụng những ràng buộc bảo mật còn phù hợp:

~~~hql
where o.id in :ids
  and o.tenantId = :trustedTenantId
  and o.deletedAt is null
~~~

**ID trong một danh sách không tự chứng minh quyền truy cập.** Đừng tin tưởng một danh sách IDs do client tự gửi để gọi query fetch rồi trả về object graph thuộc tenant khác.

### 15.1. IDs phải lấy từ query đã được ủy quyền

Trong pattern chuẩn, bước 1 tạo IDs nội bộ theo tenant/role. Bước 2 nhận đúng IDs đó, không nhận arbitrary IDs từ request để tải dữ liệu nhạy cảm. Nếu API cần endpoint GET /orders/{id}, quyền truy cập của ID đó vẫn phải được kiểm tra riêng.

### 15.2. Database row-level security

Nếu database có RLS, nó có thể bổ sung một lớp bảo vệ. Nhưng ứng dụng vẫn phải cấu hình connection/session role đúng và viết filter có ý nghĩa nghiệp vụ. Đừng coi RLS hoặc ORM filter tự động sửa mọi query native/custom query; kiểm tra riêng từng execution path.

### 15.3. Soft delete thay đổi giữa hai câu SELECT

Order có thể được soft delete sau ID query nhưng trước fetch; query thứ hai với deletedAt is null sẽ loại nó, tạo trang thiếu phần tử. Điều này phản ánh thay đổi đồng thời. Bỏ điều kiện deletedAt ở bước 2 có thể khiến một Order vừa bị xóa mềm vẫn xuất hiện. Chọn theo contract và isolation, không bỏ qua ràng buộc chỉ để ép page size đủ.

## 16. Khi collection quá lớn: hai bước vẫn chưa đủ

Kỹ thuật ID-first giới hạn số **parent**, không giới hạn số **child** của mỗi parent.

Ví dụ:

- Page size = 20.
- 19 Order có 2 items.
- 1 Order có 100.000 items.

Query thứ hai vẫn có thể tải khoảng 100.038 OrderItem rows, tạo rất nhiều Java objects. Nó tốt hơn tải mọi Order trong database, nhưng không làm một collection khổng lồ trở nên nhẹ.

### 16.1. Phân trang collection riêng

Có thể thiết kế API:

~~~text
GET /orders?page=0&size=20
GET /orders/105/items?page=0&size=50
~~~

Query danh sách Order trả thông tin tóm tắt/số lượng item; query chi tiết OrderItem được phân trang độc lập:

~~~java
public interface OrderItemRepository
        extends JpaRepository<OrderItem, Long> {

    Page<OrderItem> findByOrderId(
        Long orderId, Pageable pageable);
}
~~~

Như vậy ứng dụng đặt giới hạn cho cả hai loại entity. Cần kiểm tra authorization với Order trước khi cho phép đọc items; một Order ID hợp lệ không có nghĩa mọi user được xem items.

### 16.2. Nếu chỉ cần số lượng item, đừng fetch tất cả

Một projection thay thế:

~~~hql
select o.id, count(i.id)
from PurchaseOrder o
left join o.items i
where o.id in :ids
group by o.id
~~~

Hoặc một SQL aggregate nhóm theo order_id. Nó trả tối đa một hàng tổng hợp cho mỗi parent, tránh hydrate toàn bộ OrderItem chỉ để lấy size.

Với UI hiển thị tối đa ba item đầu của mỗi Order, đừng tự động fetch cả 100.000 rồi cắt List trong Java. Cần thiết kế query lấy top-N child theo parent (ví dụ window function SQL), hoặc API expand riêng khi người dùng mở Order.

### 16.3. Chọn DTO theo nhu cầu hiển thị

Nếu màn hình chỉ cần ID, status, createdAt, totalAmount và itemCount, dùng projection/aggregate thường rẻ hơn two-phase fetch toàn collection. Hai bước là một lựa chọn khi **thực sự phải tải các collection đầy đủ** cho trang parent.

## 17. Hai bước tải nhiều collection: tránh Cartesian multiplication

Giả sử PurchaseOrder có:

- items: 5 phần tử.
- payments: 2 phần tử.
- shipments: 3 phần tử.

Một query fetch cùng lúc:

~~~hql
select distinct o
from PurchaseOrder o
left join fetch o.items
left join fetch o.payments
left join fetch o.shipments
where o.id in :ids
~~~

có thể tạo tới 5 × 2 × 3 = **30 hàng SQL cho một Order**, chưa tính các trường hợp child nhiều hơn. Đây là Cartesian multiplication ở cấp các collection. Một số mapping bag còn có thể gây MultipleBagFetchException.

### 17.1. Chia bước fetch thành nhiều query

Một cách tổ chức:

1. Bước ID: chọn 20 Order IDs.
2. Query A: fetch Order + items theo IDs.
3. Query B: fetch payments cho các Order IDs đã chọn.
4. Query C: fetch shipments nếu UI thật sự cần.
5. Map DTO trong cùng transaction/context, giữ thứ tự parent theo IDs đầu tiên.

Khi query B trả Payment entity theo order association, có thể ánh xạ vào DTO độc lập hoặc cho Hibernate khởi tạo association phù hợp theo mapping; không giả định mọi câu SELECT Payment tự động đánh dấu PurchaseOrder.payments collection đã initialized. Tùy API, có thể query fetch riêng từng collection trên tập Order đã managed và kiểm tra SQL thực tế.

### 17.2. Nhiều SQL không nhất thiết chậm hơn một SQL

Một câu JOIN ba collections có thể truyền hàng trăm nghìn dòng lặp của parent, payment và shipment. Ba câu SELECT nhỏ không nhân chéo đôi khi tiết kiệm bandwidth, heap và thời gian tổng thể. Đo actual rows, bytes truyền và query time; không tối ưu theo số câu SQL đơn thuần.

## 18. So sánh hai bước với batch fetching

Một lựa chọn khác là lấy trang Order bình thường rồi Hibernate batch-load collections khi cần:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 25)
private List<OrderItem> items = new ArrayList<>();
~~~

Hoặc cấu hình:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 25
~~~

Truy vấn parent:

~~~sql
SELECT *
FROM purchase_orders
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Sau đó Hibernate có thể phát một hoặc một vài câu SELECT tải items của nhóm owner:

~~~sql
SELECT *
FROM order_items
WHERE order_id IN (?, ?, ?, ...);
~~~

### 18.1. Khi nào hai bước ID + fetch phù hợp?

- Cần định nghĩa rõ trang parent theo filter/sort phức tạp.
- Cần tải đầy đủ một collection bounded để map DTO.
- Muốn kiểm soát chính xác truy vấn nào fetch association.
- Có thể chịu thêm round-trip so với một query đơn giản nhưng tránh pagination in memory.

### 18.2. Khi nào batch fetching phù hợp?

- Đã có query parent phân trang an toàn.
- Nhiều use case truy cập collection LAZY theo pattern tương tự.
- Không muốn viết query fetch thứ hai chuyên biệt cho từng màn hình.
- Có nhiều association cùng được truy cập ở các thời điểm khác nhau.

### 18.3. Subselect fetching có thể phù hợp nhưng cần đo

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderItem> items = new ArrayList<>();
~~~

Hibernate có thể dùng subselect dựa trên nhóm parent đã được tải để khởi tạo nhiều collection. Hình dạng SQL và tập owner chịu ảnh hưởng của query và context. Nó không thay thế việc phân trang root ở database và không tự giới hạn số items của parent. Với dữ liệu có cardinality lớn, cần quan sát query thực tế.

### 18.4. Bảng quyết định

| Use case | Cách thường phù hợp |
|---|---|
| Danh sách Order, không hiển thị items | Page entity/DTO root, không fetch collection |
| Danh sách cần itemCount | Aggregate/DTO projection |
| Danh sách cần tất cả items của 20 Order, collection vừa | Page IDs rồi fetch collection theo IDs |
| Danh sách root rồi lazy access nhiều collections | Batch fetch hoặc fetch query theo association |
| Chi tiết một Order có ít items | Fetch join không pagination |
| Một Order có rất nhiều items | Page child riêng |
| Nhiều collections độc lập | Chia fetch hoặc aggregate thành nhiều query |
| Duyệt trang sâu theo thời gian | Keyset IDs rồi fetch theo IDs |

## 19. Vì sao EntityGraph không mặc nhiên sửa được pagination?

Spring Data JPA có thể dùng:

~~~java
@EntityGraph(attributePaths = "items")
Page<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable
);
~~~

EntityGraph mô tả fetch plan, không thay đổi cardinality của quan hệ. Nếu Hibernate thực thi collection attribute qua JOIN FETCH, pagination có thể vẫn xảy ra trong memory hoặc bị chặn bởi cấu hình fail fast.

Ngược lại, fetch join quan hệ to-one như PurchaseOrder.customer thường không nhân số hàng root nếu mapping/constraint đúng. Page Order kèm customer to-one có thể được database phân trang an toàn trong nhiều trường hợp. Nhưng chỉ cần thêm một collection to-many join là bài toán cũ quay lại.

**Đừng xem EntityGraph hay EAGER mapping là một cách né giới hạn của collection pagination.**

## 20. SQL index hỗ trợ query ID và fetch collection

Với query IDs:

~~~sql
SELECT o.id
FROM purchase_orders o
WHERE o.tenant_id = :tenantId
  AND o.status = 'PAID'
  AND o.deleted_at IS NULL
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20;
~~~

Một index có thể phù hợp trên PostgreSQL:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON purchase_orders(
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
~~~

Với query fetch:

~~~sql
SELECT *
FROM order_items
WHERE order_id IN (...);
~~~

Một index hỗ trợ:

~~~sql
CREATE INDEX idx_order_items_order_id
ON order_items(order_id);
~~~

### 20.1. Index không thay thế thiết kế page

Một index tốt có thể giúp lấy IDs nhanh, nhưng không thể biến JOIN LIMIT theo rows thành pagination parent đúng. Ngược lại, ID-first đúng nhưng thiếu index khiến database phải sort/filter tập lớn ở bước 1. Cần cả **semantics query đúng** lẫn **kế hoạch thực thi tốt**.

### 20.2. Partial index cho soft delete

Nếu đa phần truy vấn chỉ xem Order chưa xóa, PostgreSQL có thể cân nhắc partial index:

~~~sql
CREATE INDEX idx_active_orders_tenant_status_created
ON purchase_orders(
    tenant_id, status, created_at DESC, id DESC
)
WHERE deleted_at IS NULL;
~~~

Index này chỉ thích hợp nếu filter/schema và workload phù hợp; nó tăng chi phí ghi và dùng storage. Không tạo tất cả index minh họa một cách máy móc.

### 20.3. Quá nhiều IDs trong IN

Với page size 20 hoặc 100, IN thường có số tham số hợp lý. Nếu page size bị cho phép lên tới hàng chục nghìn, có thể chạm giới hạn bind parameter hoặc plan kém. Giới hạn pageSize theo UX/SLA, hoặc dùng temporary table/array/table-valued mechanism phù hợp database trong các job lớn. Query report/export nhiều bản ghi nên có kiến trúc riêng thay vì tăng pageSize vô hạn.

## 21. Đo đúng hiệu năng, không chỉ đếm số câu SQL

Bật SQL logging trong development:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Logger bind parameter có thể chứa ID, email hoặc dữ liệu nhạy cảm. Không bật TRACE mặc định trong production.

### 21.1. Dấu hiệu hai bước hoạt động đúng

Trong log, mong đợi:

1. Query chọn ID có LIMIT/OFFSET hoặc pagination dialect ở database.
2. Query fetch theo IN có đúng tập ID của page, **không có LIMIT/OFFSET**.
3. Không có warning HHH90003004 cho query bước 2.
4. Không có hàng loạt query lazy N+1 khi map DTO.
5. Query COUNT (nếu Page) đếm parent với cùng bộ lọc.

### 21.2. Hibernate Statistics

~~~java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);
Statistics statistics = sessionFactory.getStatistics();

long statementsBefore = statistics.getPrepareStatementCount();
long loadedBefore = statistics.getEntityLoadCount();

// Gọi service lấy một page đã được cô lập trong test.

long statementDelta =
    statistics.getPrepareStatementCount() - statementsBefore;
long entityLoadDelta =
    statistics.getEntityLoadCount() - loadedBefore;
~~~

Statistics là bộ đếm cấp SessionFactory, có thể thay đổi do các thread khác. Chỉ dùng delta để suy luận rõ trong test cô lập; nó không phải số rows SQL thực tế. Query 1 + Query 2 + count có thể chỉ 3 statements nhưng vẫn nạp nhiều OrderItem nếu một Order có collection khổng lồ.

### 21.3. EXPLAIN ANALYZE cho bước 1

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id
FROM purchase_orders o
WHERE o.tenant_id = 7
  AND o.status = 'PAID'
  AND o.deleted_at IS NULL
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20;
~~~

Theo dõi Index Scan/Seq Scan, Sort, actual rows, buffers và execution time. Database có thể sử dụng index để trả ID theo thứ tự mà không cần sort toàn bộ tập.

### 21.4. EXPLAIN ANALYZE cho bước 2

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.created_at, i.id, i.line_number
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id IN (105, 104, 103)
  AND o.tenant_id = 7
  AND o.deleted_at IS NULL;
~~~

Đánh giá:

- Có bao nhiêu parent IDs?
- Database trả bao nhiêu joined rows?
- Mỗi parent có bao nhiêu child?
- Có dùng index order_items(order_id) không?
- Phần lớn thời gian nằm ở bước 1, bước 2 hay map DTO?

Đừng so sánh “một SQL vs ba SQL” mà không tính actual rows, bytes truyền, hydrate count và heap. EXPLAIN ANALYZE thực sự chạy câu SELECT; chỉ thực hiện trong môi trường/dữ liệu được phép.

## 22. Kiểm thử đúng bản chất phân trang parent

Tạo fixture có số items rất không đều:

| Order | createdAt | Items | Status |
|---:|---|---:|---|
| 105 | Ngày mới nhất | 3 | PAID |
| 104 | Mới hơn | 0 | PAID |
| 103 | Trung bình | 50 | PAID |
| 102 | Cũ hơn | 1 | PAID |
| 101 | Cũ nhất | 5 | PAID |

Với pageSize=2, pageNumber=0:

~~~text
IDs bước 1 = [105, 104]
Page content IDs = [105, 104]
Order 105: đầy đủ 3 items
Order 104: collection rỗng
totalElements = 5
~~~

Trang tiếp theo:

~~~text
IDs bước 1 = [103, 102]
Page content IDs = [103, 102]
Order 103: đầy đủ 50 items
Order 102: đầy đủ 1 item
totalElements = 5
~~~

### 22.1. Đừng chỉ assert số lượng parent

Một query phân trang trong memory vẫn có thể trả 2 parent đúng và 3/0 items đầy đủ. Test chỉ kiểm tra content.size()==2 không chứng minh database đã phân trang ở bước 1. Cần kết hợp assert nội dung với SQL logging/fail fast/counter hay công cụ capture SQL.

### 22.2. Ma trận test

| Case | Điều cần kiểm tra |
|---|---|
| Page đầu, page giữa, page cuối | IDs đúng thứ tự, không trùng, đúng size nếu có đủ dữ liệu |
| Page vượt quá cuối | Content rỗng nhưng totalElements vẫn phản ánh toàn tập |
| Parent không có items | Vẫn xuất hiện, items rỗng |
| Parent có rất nhiều items | Items đầy đủ, không bị cắt theo pageSize |
| Nhiều parent cùng createdAt | Tie-breaker ID ổn định |
| Query fetch trả thứ tự khác query IDs | Service khôi phục đúng thứ tự ban đầu |
| IDs rỗng | Không gọi fetch IN rỗng |
| Child filter có nhiều item match một Order | Parent chỉ chiếm một vị trí trong page |
| Count filter theo child | COUNT đúng số parent, không phải số item |
| Tenant khác | Không trả Order ngoài phạm vi |
| Soft-deleted Order | Không xuất hiện theo contract |
| Collection lớn | Đo heap và actual rows, không chỉ số SELECT |
| Hibernate fail fast bật | Không có pagination over collection fetch ở query hợp lệ |
| Dữ liệu đổi giữa hai SELECT | Behavior được xác định và test concurrency khi cần |

### 22.3. Skeleton integration test

~~~java
@SpringBootTest
class OrderTwoPhasePageTest {
    @Autowired OrderPageService orderPageService;

    @Test
    void pageParentsThenLoadCompleteItemCollections() {
        // Arrange:
        // Persist Order 105 với 3 items,
        // Order 104 với 0 items,
        // Order 103 với 50 items,
        // cùng các Order khác.
        // Flush/commit fixture và dùng persistence context mới.

        Page<OrderPageRow> page =
            orderPageService.findPaidOrders(
                trustedTenantId, 0, 2);

        // Assert:
        // page.content IDs là [105, 104].
        // Order 105 có đủ 3 items.
        // Order 104 vẫn xuất hiện với list rỗng.
        // totalElements phản ánh đúng số Order PAID của tenant.
        // SQL query IDs có pagination tại database.
    }
}
~~~

Đây là skeleton mô tả fixture và assertion, không phải test hoàn chỉnh có data setup/import/trustedTenantId. Nên dùng PostgreSQL Testcontainers hoặc một database tương ứng production để kiểm tra chính xác dialect/pagination/logging; H2 có thể khác SQL syntax và execution plan.

### 22.4. Kiểm thử N+1 và mapping DTO

Sau query fetch, mapper chỉ truy cập các thuộc tính đã được tải của Order/OrderItem. Nếu thêm i.getProduct().getName() mà product là LAZY, mapper có thể phát query riêng cho từng Product và tạo N+1. Test cần ghi số statements khi map DTO; có thể bổ sung fetch to-one Product trong query thứ hai khi cardinality phù hợp hoặc dùng projection/batch fetching.

## 23. Lỗi thực tế và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Page 20 nhưng database gửi hàng chục nghìn rows | Collection fetch join + Pageable trên toàn tập | Page IDs trước, fetch theo IN sau |
| Cảnh báo HHH90003004 | Hibernate đang pagination in memory | Bật fail fast và sửa query |
| DISTINCT vẫn chậm | SQL vẫn trả nhiều hàng child | Đổi fetch strategy, không dựa vào DISTINCT |
| Page có ít Order dù LIMIT 20 | LIMIT áp dụng cho joined rows/duplicate IDs | Chỉ page parent ID không nhân bản |
| Collection của Order cuối bị thiếu | SQL LIMIT cắt fetch child | Query fetch thứ hai không có LIMIT |
| Order không có items biến mất | Dùng INNER JOIN FETCH | Dùng LEFT JOIN FETCH |
| Trang sort sai sau khi fetch | IN không bảo toàn thứ tự ID | Map theo ID rồi duyệt IDs bước 1 |
| COUNT lớn hơn số đơn | JOIN to-many nhân rows | COUNT parent/EXISTS/count distinct đúng semantics |
| Product filter làm duplicate Order IDs | JOIN items ở query ID | Dùng EXISTS hoặc GROUP BY parent |
| Không thể fetch hai bag | MultipleBagFetchException | Chia fetch collection thành nhiều query |
| Query 2 quá lớn dù pageSize nhỏ | Một parent có collection cực lớn | Child page riêng/DTO aggregate |
| Có query N+1 khi serialize JSON | Map DTO truy cập association LAZY chưa tải | Fetch cần thiết trong transaction hoặc projection |
| Hai SELECT thấy dữ liệu khác nhau | Concurrent write + READ COMMITTED | Chấp nhận/retry/isolation phù hợp |
| Trang thiếu Order sau fetch | Parent bị xóa/soft delete hoặc JOIN/filter sai | Xác định snapshot semantics, kiểm tra filter |
| Cross-tenant IDs bị trả | Thiếu ràng buộc tenant | Dùng auth tenant ở cả hai bước |
| PageRequest size+1 làm lệch offset | Offset tính theo size mới | Giữ offset theo pageSize thật hoặc dùng Slice đúng |
| Trang sâu chậm | OFFSET lớn | Keyset ID pagination |
| Thêm EntityGraph collection vẫn warning | Fetch plan có to-many join | Không dùng collection graph trên query có limit |

## 24. Bài thực hành tổng hợp

### Bài A — Tái hiện pagination in memory

1. Tạo 100 Order với số items từ 0 đến 100.
2. Viết query SELECT DISTINCT Order LEFT JOIN FETCH items có Pageable.
3. Quan sát SQL và cảnh báo HHH90003004.
4. Bật hibernate.query.fail_on_pagination_over_collection_fetch=true.
5. Ghi nhận exception để xác nhận vấn đề có thể được phát hiện sớm.

### Bài B — Chuyển sang hai bước

1. Viết query lấy Order IDs theo createdAt DESC, id DESC.
2. Gọi setFirstResult/setMaxResults hoặc Pageable **chỉ trên query ID**.
3. Viết query fetch items theo danh sách IDs.
4. Không đặt limit ở query fetch.
5. Map Order theo ID rồi tái dựng thứ tự theo query đầu.
6. Assert mỗi Order có đầy đủ items.

### Bài C — Thêm bộ lọc collection

1. Thêm OrderItem.productId hoặc association Product.
2. Tìm Order chứa ít nhất một item của Product 900.
3. Cho một Order có nhiều item Product 900.
4. So sánh ID query dùng JOIN và ID query dùng EXISTS.
5. Đảm bảo mỗi Order chỉ chiếm một vị trí trong page.
6. Viết count query dùng cùng predicate EXISTS.

### Bài D — Page và Slice

1. Tạo Page đầy đủ totalElements bằng count query.
2. Thử page vượt trang cuối.
3. Tạo Slice đọc pageSize+1 IDs để xác định hasNext.
4. Chứng minh offset vẫn phải tính theo pageSize hiển thị.
5. Đo thời gian count khi số Order lớn.

### Bài E — Keyset pagination

1. Tạo nhiều Order có createdAt trùng nhau.
2. Viết cursor (lastCreatedAt, lastId).
3. Query ID trang kế tiếp bằng điều kiện keyset.
4. Fetch graph theo IDs như cũ.
5. Khi filter/sort đổi, vô hiệu hóa cursor cũ.
6. Quan sát tác động insert mới giữa hai request.

### Bài F — Đo hiệu năng

1. Log SQL của query join+pagination cũ.
2. Log SQL của query ID và fetch mới.
3. Ghi số rows, entity loads, heap và thời gian.
4. EXPLAIN ANALYZE query ID với/không có index.
5. Tạo một Order có 50.000 items, xác định giới hạn còn lại của two-step.
6. Thay fetch collection bằng child pagination hoặc aggregate trong trường hợp đó.

### Bài G — Concurrency và bảo mật

1. Thử soft delete Order giữa query ID và query fetch.
2. So sánh behavior trong READ COMMITTED và REPEATABLE READ khi phù hợp.
3. Thử tenant khác và đảm bảo không đọc được Order.
4. Đảm bảo query fetch luôn nhận IDs từ query đã kiểm soát quyền.
5. Ghi rõ contract API khi một Order biến mất giữa hai bước.

## 25. Checklist trước khi triển khai

1. **Đơn vị phân trang** là parent hay child? Có thật sự cần tải toàn bộ collection không?
2. Query đầu chỉ trả **một hàng cho mỗi parent ID** không?
3. Query ID có **ORDER BY ổn định với tie-breaker** không?
4. Filter theo child có dùng EXISTS hoặc cách tránh duplicate root không?
5. LIMIT/OFFSET có thật sự được database áp dụng ở **query ID** không?
6. Query fetch theo IDs có **không dùng Pageable/limit** không?
7. Query fetch dùng LEFT JOIN để giữ parent có collection rỗng không?
8. Đã xử lý **danh sách ID rỗng** trước khi gọi IN chưa?
9. Thứ tự kết quả có được phục hồi từ danh sách IDs không?
10. Count query có đúng cùng bộ lọc và đếm **parent**, không đếm child không?
11. Nếu dùng Slice, đã lấy thêm một ID mà không làm sai offset chưa?
12. Nếu có nhiều collections, đã tránh join nhân chéo và MultipleBagFetchException chưa?
13. Nếu một collection rất lớn, đã cân nhắc child page/aggregate/DTO chưa?
14. Tenant/authorization/soft delete có được giữ ở cả các bước cần thiết không?
15. Đồng thời ghi dữ liệu giữa hai SELECT có được xử lý theo contract không?
16. Đã đo SQL rows, ORM entity loads, heap và latency chứ không chỉ đếm SELECT chưa?
17. Đã bật fail fast trong môi trường phù hợp để ngăn regression không?
18. Đã viết integration test với parent 0 items, nhiều items, IDs trùng filter và sort tie chưa?

## 26. Nguyên tắc ghi nhớ

**Phân trang hai bước theo định danh** nghĩa là **phân trang entity gốc trước, tải tập hợp sau**.

- Collection fetch join làm một parent có thể tương ứng nhiều hàng SQL.
- LIMIT/OFFSET trực tiếp trên hàng join không bảo đảm page parent đầy đủ và có thể cắt child.
- Hibernate có thể phân trang trong bộ nhớ để tránh collection bị cắt, dẫn tới việc tải quá nhiều dữ liệu.
- Bước 1 chỉ lấy page IDs theo filter/sort ổn định, để database giới hạn đúng parent.
- Bước 2 fetch toàn bộ collection cho tập ID đó bằng IN, **không pagination**.
- IN không bảo toàn thứ tự, nên phải dựng thứ tự page theo IDs của bước 1.
- COUNT nếu cần là query riêng và phải đếm đúng parent với cùng bộ lọc.
- EXISTS phù hợp khi lọc parent theo điều kiện tồn tại child vì tránh duplicate IDs.
- Hai bước không giải quyết mọi vấn đề: một collection cực lớn hoặc nhiều collections join cùng lúc vẫn có thể tốn rất nhiều rows.
- Transaction read-only không tự tạo cùng snapshot ở mọi isolation; cần chọn semantics nhất quán phù hợp.
- SQL log, fail fast, execution plan và kiểm thử có cardinality lệch là các công cụ cần thiết để xác nhận.

Một trang 20 Order chỉ thật sự là một trang nhỏ khi **database quyết định đúng 20 Order nào thuộc trang trước**, rồi Hibernate mới tải phần dữ liệu con của chính 20 Order đó. Tách hai công việc theo định danh giúp giữ collection đầy đủ, duy trì thứ tự phân trang và tránh chi phí tăng theo toàn bộ số parent của hệ thống.
