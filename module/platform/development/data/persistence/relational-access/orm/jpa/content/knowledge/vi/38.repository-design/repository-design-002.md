# Thiết kế phương thức truy vấn theo nhu cầu sử dụng trong JPA

Repository là nơi ứng dụng diễn đạt nhu cầu truy cập dữ liệu bằng một **hợp đồng có ý nghĩa**, không đơn thuần là tập hợp các câu lệnh SELECT. Một phương thức `findAll()` có thể hoàn toàn hợp lý cho bảng cấu hình vài chục bản ghi, nhưng dễ trở thành nguồn lỗi khi được dùng cho API danh sách hàng triệu đơn hàng, báo cáo, màn hình chi tiết và thao tác sửa trạng thái cùng lúc.

Xem hai cách thiết kế sau:

```java
// Mơ hồ về mục đích, quy mô và dữ liệu được trả.
List<SalesOrder> findAll();

// Nêu rõ bài toán nghiệp vụ, ranh giới và kiểu dữ liệu.
Page<OrderListRow> searchVisibleOrders(
    String authorizedTenant,
    OrderStatus status,
    Pageable pageable
);
```

Cách thứ hai khiến người đọc đặt những câu hỏi thiết yếu: danh sách này của tenant nào, có lọc đơn bị xóa không, kết quả là managed entity hay DTO, có cần tổng số phần tử không, sắp xếp ra sao, và có tải `customer` hay `lines` không? Việc **định nghĩa rõ câu trả lời ngay trong repository contract** giúp tránh code tải thiếu dữ liệu, tải quá nhiều dữ liệu, N+1, sai phân trang hoặc trả ra tài nguyên không được phép.

Bài học thuộc chương **Thiết kế Repository** trong module *Data Persistence Relational Access ORM JPA*. Trọng tâm là **thiết kế các phương thức truy vấn bắt đầu từ trường hợp sử dụng (use case)** và biến chúng thành API bền vững, chính xác và hiệu quả. Các ví dụ dùng Jakarta Persistence/JPQL, Spring Data JPA và một số kỹ thuật tùy provider được đánh dấu rõ; không giả định mọi framework có cùng tính năng.

> **Tư duy cốt lõi:** Mỗi repository method nên trả lời được: “Ai cần dữ liệu này, để làm gì, trong phạm vi nào, với hình dạng nào, giới hạn bao nhiêu, thứ tự thế nào và kỳ vọng nhất quán ra sao?”

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chuyển yêu cầu giao diện hoặc nghiệp vụ thành hợp đồng truy vấn rõ ràng.
2. Phân biệt nhu cầu **đọc danh sách, đọc chi tiết, tìm kiếm, kiểm tra tồn tại, đếm, tổng hợp, đọc để sửa**.
3. Chọn kết quả `Optional<T>`, `List<T>`, `Page<T>`, `Slice<T>`, `Stream<T>` hoặc DTO phù hợp.
4. Đặt tên phương thức gắn với ý định nghiệp vụ thay vì chi tiết UI hoặc SQL vụn vặt.
5. Chọn Spring Data **derived queries**, `@Query`, `Specification`/Criteria API hoặc custom repository đúng thời điểm.
6. Thiết kế projection DTO/record và entity fetch plan không gây over-fetch/N+1.
7. Thiết kế phân trang, tổng số bản ghi, sorting ổn định và cursor pagination.
8. Ràng buộc tenant, quyền truy cập, soft delete và trạng thái theo use case.
9. Xử lý optional filters, text search, các mốc thời gian và input `null` một cách nhất quán.
10. Tránh SQL injection khi có sort/search động và tránh user enumeration qua truy vấn.
11. Phân biệt query dùng để hiển thị với query tải managed entity để thay đổi.
12. Thiết kế repository API hỗ trợ concurrency/locking đúng nhu cầu.
13. Dùng bulk update có ý thức về persistence context và lifecycle.
14. Viết tests cho kết quả, phạm vi quyền, thứ tự, phân trang, query count và DB constraints.
15. Nhận ra khi nào cần tách read model/custom query service thay vì mở rộng một repository thành “siêu interface”.

## 2. Repository không phải chỉ là DAO đổi tên

Data Access Object truyền thống có thể phơi bày thao tác CRUD gần với bảng: `insert`, `update`, `delete`, `selectById`. Repository thường biểu diễn **tập hợp các aggregate/entities hoặc một cổng truy cập dữ liệu mà domain/application cần**.

Trong một ứng dụng:

```text
HTTP Controller
   |
   v
Application Service / Use case
   |
   v
Repository interface (hợp đồng)
   |
   +-- Spring Data generated implementation
   +-- JPQL @Query
   +-- Criteria / Specification
   +-- Custom EntityManager implementation
   |
   v
JPA provider -> JDBC -> Database
```

### 2.1. Repository có trách nhiệm gì?

- Biểu diễn cách chọn dữ liệu có ý nghĩa với application.
- Giữ quy tắc truy cập dữ liệu ổn định: scope, filters, sorts.
- Chọn entity hoặc read projection theo contract.
- Giới hạn số rows và rõ ràng hóa result cardinality.
- Phối hợp với transaction/context theo architecture.
- Không che giấu các assumptions có thể làm sai dữ liệu.

### 2.2. Repository không nên làm gì?

- Tự trả HTTP status, xây JSON, đọc request headers.
- Quyết định người dùng hiện tại có quyền gì mà không nhận/được cung cấp thông tin authorization đáng tin.
- Gọi hệ thống thanh toán, gửi email hoặc thực hiện workflow nhiều bước.
- Chứa business orchestration dài, transaction distributed logic.
- Trả toàn bộ entity graph cho mọi use case “vì tiện”.

### 2.3. Repository domain-oriented hay persistence-oriented?

Một hệ thống có thể khai interface domain port `OrderRepository` trong domain/application layer và adapter Spring Data `JpaOrderRepository` trong infrastructure layer. Hệ thống đơn giản hơn có thể dùng thẳng `JpaRepository` ở application service. Điều quan trọng là **contract được thể hiện rõ**, không phải ép tất cả dự án vào một kiểu layering.

---

## 3. Bắt đầu bằng use-case inventory

Giả sử một hệ thống bán hàng có các chức năng:

| Use case | Câu hỏi nghiệp vụ | Dữ liệu cần | Kiểu truy vấn thích hợp |
|---|---|---|---|
| Danh sách đơn | “50 đơn mới nhất mà nhân viên được xem?” | ID, status, customer name, amount, createdAt | Page/Slice DTO |
| Chi tiết đơn | “Đơn X có thông tin gì?” | Order, Customer, Lines, Products | Detail DTO hoặc graph giới hạn |
| Tìm kiếm | “Các đơn PAID trong khoảng ngày?” | Filters động, sort và paging | Specification/Criteria/JPQL |
| Kiểm tra tồn tại | “Đơn còn hoạt động hay không?” | Boolean | EXISTS |
| Tổng số đơn | “Có bao nhiêu đơn theo trạng thái?” | Scalar/aggregate | COUNT/GROUP BY |
| Cập nhật đơn | “Tải trạng thái để chuyển sang SHIPPED” | Managed Order, version, rule state | Entity query trong transaction |
| Duyệt batch | “100 đơn đang chờ xử lý tiếp theo?” | IDs/status có thứ tự, có thể lock | Bounded query/claim |
| Xuất báo cáo | “Xuất 100.000 dòng báo cáo” | Flat fields, chunks | DTO streaming/keyset |
| Giỏ hàng theo user | “Giỏ hàng active của một owner?” | 0 hoặc 1 Cart | Optional entity |
| Top sản phẩm | “10 sản phẩm bán nhiều nhất tuần này?” | Aggregate product summary | Custom DTO aggregate |

Nếu mọi use case gọi `findAll` rồi filter/map trong Java, backend đang chuyển công việc lọc, đếm và sắp xếp từ database sang memory, đồng thời làm contract mơ hồ.

### 3.1. Tài liệu hóa từng query contract

Một mô tả ngắn:

```text
Operation: searchVisibleOrders
Consumer: OrderAdminList
Required scope: authorizedTenant, deletedAt IS NULL
Optional filters: status, dateFromInclusive, dateToExclusive
Result: Page<OrderListRow>
Default sort: createdAt DESC, id DESC
Maximum size: 100
Count required: yes (UI hiển thị total)
Consistency: read-only, không phải snapshot giữa requests
Security: không truy vấn tenant khác
```

### 3.2. “Mọi field của entity” thường không phải yêu cầu thật

Danh sách hiển thị 5 cột không cần tải toàn bộ Customer, địa chỉ, Lines và Payment. Phần lớn read use cases có thể mô tả bằng projection.

### 3.3. Ghi cả những trường hợp không cần dữ liệu

Để biết “đơn có tồn tại không”, `exists` có thể tốt hơn `find` + map. Để biết “có đơn tiếp theo không”, `Slice` có thể tránh một count query.

---

## 4. Mô hình JPA ví dụ xuyên suốt

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Version
    @Column(name = "version")
    private Long version;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected SalesOrder() {}

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public Customer getCustomer() { return customer; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getDeletedAt() { return deletedAt; }
    public List<OrderLine> getLines() { return lines; }

    public void markShipped() {
        if (status != OrderStatus.PAID) {
            throw new IllegalStateException(
                "Only paid orders can be shipped"
            );
        }
        status = OrderStatus.SHIPPED;
    }
}
```

Customer và Line:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {}

    public String getDisplayName() {
        return displayName;
    }
}

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private SalesOrder order;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "product_id")
    private Product product;

    @Column(name = "quantity")
    private int quantity;

    protected OrderLine() {}

    public Long getId() { return id; }
    public Product getProduct() { return product; }
    public int getQuantity() { return quantity; }
}

public enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
```

`Product` là một mapped entity được giả định có `id`, `sku` và `name`. Các snippets minh họa tập trung thiết kế query; constructors, validation, sequence definitions và migrations hoàn chỉnh tùy dự án.

### 4.1. Quan hệ LAZY là lựa chọn thiết kế fetch plan, không phải bảo mật

`LAZY` cho phép tải quan hệ theo use case nhưng không kiểm soát authorization hoặc JSON serialization. Repository phải yêu cầu đúng graph/projection.

### 4.2. Soft delete phải có semantics rõ

`deletedAt == null` được dùng minh họa active orders. Nếu một service có quyền xem cả deleted records, phải dùng method riêng có quyền tương ứng; đừng để caller vô tình bỏ lọc.

### 4.3. Tenant scope là điều kiện cốt lõi

Query theo `id` một mình có thể không đủ ở shared-schema multitenancy. Dùng authorized tenant từ trusted context và repository query có predicate rõ.

---

## 5. Thiết kế tên phương thức theo ý định

Đọc:

```java
List<SalesOrder> findByStatus(OrderStatus status);
```

Khó biết: danh sách bao nhiêu? Có tenant filter không? Có gồm deleted? Có sắp xếp không? Có fetch Customer/Lines không?

Một tên giàu ngữ nghĩa:

```java
List<SalesOrder> findActiveOrdersForCustomer(
    String authorizedTenant,
    Long customerId,
    int limit
);
```

Hợp đồng vẫn cần mô tả status nào được coi là active và thứ tự. Không phải cứ tên dài là tốt: nếu method có nhiều flags/filters, dùng query criteria object.

### 5.1. Đặt tên theo nghiệp vụ, không theo màn hình cụ thể

`findAdminTableData()` gắn với UI và khó reuse. `findOrderListRows(...)` mô tả data shape; `findReadyToShipOrders(...)` mô tả trạng thái nghiệp vụ.

### 5.2. Tên phản ánh cardinality

`findActiveCartByOwner` gợi ý 0–1 result. `listActiveOrdersByCustomer` gợi ý nhiều result. `countPaidOrders` trả số lượng.

### 5.3. Tên không giấu hiệu ứng ghi

`findAndMarkProcessed()` là một operation có mutation; nên nằm trong service với transaction rõ hoặc method claim được đặt tên và document side effect cụ thể.

### 5.4. Không dùng `get`/`find` như một guarantee tùy ý

Trong Spring Data, tiền tố tên method có semantics framework. Trong interface custom, team tự quy ước. Đừng trộn semantics “get = throw if missing” với “get = nullable” giữa repositories.

---

## 6. Chọn đúng kiểu kết quả

| Nhu cầu | Kiểu kết quả phù hợp | Lưu ý |
|---|---|---|
| Một entity có thể vắng | `Optional<SalesOrder>` | Không dùng null như một signal mập mờ |
| Danh sách hữu hạn, không cần total | `List<OrderListRow>` | Phải có giới hạn từ query/contract |
| Kết quả có total count | `Page<OrderListRow>` | Có thể chạy count query |
| Chỉ cần có trang sau | `Slice<OrderListRow>` | Tránh tổng count khi không cần |
| Duyệt rows lớn | `Stream<OrderExportRow>` | Cần đóng stream/transaction/connection |
| Kiểm tra tồn tại | `boolean` | Không load entity khi không cần |
| Đếm/tổng hợp | `long`, `BigDecimal`, DTO | Chú ý null của SUM và units |
| Top một kết quả | `Optional<T>` + sort rõ | Không dựa vào row order ngầm |
| Entity để sửa | `SalesOrder`/`Optional<SalesOrder>` | Managed trong transaction |
| Nhiều groups | `List<StatusCountRow>` | COUNT/GROUP BY trong DB |

### 6.1. Không trả List không giới hạn

`List<Order> findAllByTenantId(...)` có thể tạo OOM nếu tenant có hàng triệu records. Với API public, giới hạn page/chunk nên ở boundary.

### 6.2. Optional không có nghĩa luôn duy nhất

Nếu query được viết dựa trên field không unique nhưng method trả `Optional`, nhiều rows có thể gây exception. Test schema UNIQUE hoặc predicate đủ chặt.

### 6.3. Page không miễn phí

`Page` thường cần count để biết total. Nếu UX chỉ cần nút “Xem thêm”, `Slice` hoặc cursor contract có thể phù hợp.

### 6.4. Stream phải có lifecycle

Spring Data JPA stream results có thể giữ JDBC resources; cần transaction thích hợp và close:

```java
try (Stream<OrderExportRow> rows =
         repository.streamExportRows(tenant)) {
    rows.forEach(this::writeRow);
}
```

`writeRow` là output handler giả định. Không giữ transaction/connection mở khi ghi file rất lớn ra remote service nếu không có thiết kế streaming, backpressure và recovery phù hợp.

---

## 7. Trả entity hay DTO?

**Entity result** hợp lý khi use case cần domain behavior, dirty checking hoặc thao tác trên managed aggregate.

**DTO projection** hợp lý khi read-only endpoint cần dữ liệu phẳng/hạn chế:

```java
package com.example.shop.api;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderListRow(
    Long id,
    String customerName,
    OrderStatus status,
    BigDecimal total,
    Instant createdAt
) {}
```

### 7.1. Danh sách nên chọn đúng fields

Nếu UI chỉ dùng `customerName`, query không cần hydrate toàn Customer object hoặc Lines collection.

### 7.2. Detail có thể khác list

`OrderDetailResponse` có `List<OrderLineRow>`, trong khi `OrderListRow` không. Không cố cho một DTO có hàng chục nullable fields phục vụ mọi use case.

### 7.3. Projection không được dirty-check

Sửa `OrderListRow` không làm JPA update entity. Với update use case, load managed Order hoặc dùng atomic update query theo yêu cầu.

### 7.4. Trả entity trực tiếp qua REST dễ bị mở rộng graph

Serializer có thể gọi lazy getters, gây N+1, circular references và lộ fields. Dùng response DTO ở API boundary.

---

## 8. Spring Data JPA derived queries

Với trường hợp đơn giản, method name có thể đủ:

```java
public interface SalesOrderJpaRepository
        extends JpaRepository<SalesOrder, Long> {

    Optional<SalesOrder>
    findByIdAndTenantIdAndDeletedAtIsNull(
        Long id,
        String tenantId
    );

    boolean existsByIdAndTenantIdAndDeletedAtIsNull(
        Long id,
        String tenantId
    );

    long countByTenantIdAndStatusAndDeletedAtIsNull(
        String tenantId,
        OrderStatus status
    );

    List<SalesOrder>
    findTop20ByTenantIdAndStatusAndDeletedAtIsNullOrderByCreatedAtDescIdDesc(
        String tenantId,
        OrderStatus status
    );
}
```

### 8.1. Ưu điểm

- Ít boilerplate.
- Method name làm rõ field predicates cho query đơn giản.
- Spring Data tự tạo query từ entity property paths.
- Phù hợp simple lookup, exists, count, top-N.

### 8.2. Nhược điểm khi tên quá dài

Một method chứa 8 điều kiện cùng nhiều `Or` và `OrderBy` có thể khó hiểu precedence và khó bảo trì. Nên chuyển sang `@Query`/Specification/custom query.

### 8.3. Kiểm tra property names

Derived query parser dựa trên tên Java attributes của entity, không dựa vào SQL column names. Đổi tên field trên entity có thể ảnh hưởng method definitions.

### 8.4. `findById` từ JpaRepository không tự tenant-aware

`repository.findById(id)` là API CRUD chung, không tự thêm `tenantId` từ security context. Với shared-tenant data, cần contract/scoping đầy đủ hoặc security control ở tầng khác đã được kiểm chứng.

### 8.5. Top/First vẫn cần sort

“Đơn đầu tiên” chỉ có ý nghĩa khi có `ORDER BY` quyết định thứ tự. `findFirstByStatus` không có sort không bảo đảm là bản ghi mới nhất.

---

## 9. Khi nào chuyển từ derived query sang @Query?

Dùng `@Query` khi cần:

- JPQL constructor expression cho DTO.
- JOIN/filter/sort có chủ đích.
- EXISTS/subquery/aggregation.
- Điều kiện OR có nhóm rõ ràng.
- Fetch join/entity query với association cần thiết.
- Count query tùy chỉnh cho pagination.
- Query dựa trên các predicate phức tạp nhưng shape ổn định.

Ví dụ:

```java
public interface OrderReadRepository
        extends Repository<SalesOrder, Long> {

    @Query(
        """
        select new com.example.shop.api.OrderListRow(
            o.id, c.displayName, o.status,
            o.totalAmount, o.createdAt
        )
        from SalesOrder o
        join o.customer c
        where o.tenantId = :tenant
          and o.deletedAt is null
          and o.status = :status
        order by o.createdAt desc, o.id desc
        """
    )
    List<OrderListRow> findLatestRows(
        @Param("tenant") String authorizedTenant,
        @Param("status") OrderStatus status,
        Pageable pageable
    );
}
```

`Pageable` có thể áp pagination cho một List-returning query, nhưng metadata tổng số không được trả như `Page`. Nếu static `ORDER BY` đã có, tránh trộn thêm dynamic sorting trái contract.

### 9.1. Đọc query dễ hiểu hơn tên dài

Một JPQL multiline với predicates explicit có thể dễ review hơn tên derived 150 ký tự.

### 9.2. Không phải mọi query có join đều cần fetch join

`join o.customer c` đủ để lấy `c.displayName` cho DTO. `join fetch` phục vụ entity association fetching, không phải constructor projection.

### 9.3. `@Query` thuộc Spring Data, JPQL thuộc JPA

Spring Data `@Query` annotation không phải annotation core `jakarta.persistence`. Ứng dụng JPA thuần có thể dùng `EntityManager.createQuery`/`@NamedQuery`.

---

## 10. Ví dụ Page DTO với countQuery riêng

```java
@Query(
    value = """
        select new com.example.shop.api.OrderListRow(
            o.id, c.displayName, o.status,
            o.totalAmount, o.createdAt
        )
        from SalesOrder o
        join o.customer c
        where o.tenantId = :tenant
          and o.deletedAt is null
          and (:status is null or o.status = :status)
        order by o.createdAt desc, o.id desc
        """,
    countQuery = """
        select count(o)
        from SalesOrder o
        where o.tenantId = :tenant
          and o.deletedAt is null
          and (:status is null or o.status = :status)
        """
)
Page<OrderListRow> searchOrderRows(
    @Param("tenant") String authorizedTenant,
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

### 10.1. Vì sao count query riêng?

Count không cần SELECT columns của Customer hay ORDER BY. Nếu query chính có join/projection phức tạp, explicit count giúp đảm bảo đúng semantics và dễ kiểm soát SQL.

### 10.2. Filter logic phải tương đương

Nếu main query lọc một điều kiện mà count bỏ sót, `Page.getTotalElements()` sai. Với optional filters càng nhiều, cần test chéo từng tổ hợp.

### 10.3. Optional filter `:status is null` không phải luôn tối ưu nhất

Một query gộp optional predicates có thể khiến optimizer chọn plan kém hoặc có vấn đề type inference ở một số DB/dialects. Với search phức tạp, dynamic predicates bằng Criteria/Specification có thể tốt hơn. Kiểm tra SQL/plan thật.

### 10.4. Sort phải do repository/service kiểm soát

Query trên có static sort `createdAt desc,id desc`. Khi gọi, nên dùng `PageRequest.of(page,size,Sort.unsorted())` hoặc một contract rõ không thêm sort trái với query.

### 10.5. Page và Slice

Nếu không cần total, có thể thiết kế một query trả `Slice<OrderListRow>` để giảm nhu cầu count. Việc Spring Data áp thêm row để xác định `hasNext` phụ thuộc implementation/return type; test đúng behavior trên framework version.

---

## 11. Một hợp đồng search có criteria object

Khi có nhiều filters, tránh method 12 tham số:

```java
Page<OrderListRow> search(
    String tenant,
    OrderStatus status,
    Instant start,
    Instant end,
    Long customerId,
    String keyword,
    BigDecimal minAmount,
    BigDecimal maxAmount,
    boolean includeDeleted,
    int page,
    int size,
    Sort sort
);
```

Thiết kế một type rõ:

```java
public record OrderSearchCriteria(
    OrderStatus status,
    Long customerId,
    Instant createdFromInclusive,
    Instant createdToExclusive,
    BigDecimal minimumTotal,
    BigDecimal maximumTotal
) {}
```

Và API:

```java
Page<OrderListRow> searchVisibleOrders(
    String authorizedTenant,
    OrderSearchCriteria criteria,
    Pageable pageable
);
```

### 11.1. Đừng đưa tenant vào criteria nếu có thể bị caller tự ý sửa

Nếu `tenant` là security boundary, nên tách khỏi user-controlled search fields. App service lấy tenant từ trusted security context, rồi truyền xuống repository.

### 11.2. Criteria là dữ liệu, không phải câu SQL

Không cho client gửi raw JPQL/SQL fragment, tên bảng hoặc WHERE string vào criteria.

### 11.3. Validate ngay khi tạo

`createdFromInclusive <= createdToExclusive`, `min <= max`, bounded page size, statuses hợp lệ. Đừng để các giá trị bất hợp lệ biến thành truy vấn khó hiểu.

### 11.4. Record có thể chứa dữ liệu nhạy cảm

Không log nguyên criteria nếu nó có keyword/email/user identifiers. Dùng structured event summary không chứa raw input.

---

## 12. Chọn Specification/Criteria khi predicates động

Spring Data JPA `JpaSpecificationExecutor` hỗ trợ `Specification<T>`. Ví dụ:

```java
import org.springframework.data.jpa.domain.Specification;
import jakarta.persistence.criteria.Predicate;
import java.util.ArrayList;
import java.util.List;

public final class OrderSpecifications {

    private OrderSpecifications() {}

    public static Specification<SalesOrder> visibleOrders(
            String authorizedTenant,
            OrderSearchCriteria criteria
    ) {
        return (root, query, cb) -> {
            List<Predicate> p = new ArrayList<>();

            p.add(
                cb.equal(
                    root.get("tenantId"),
                    authorizedTenant
                )
            );
            p.add(cb.isNull(root.get("deletedAt")));

            if (criteria.status() != null) {
                p.add(
                    cb.equal(
                        root.get("status"),
                        criteria.status()
                    )
                );
            }

            if (criteria.createdFromInclusive() != null) {
                p.add(
                    cb.greaterThanOrEqualTo(
                        root.get("createdAt"),
                        criteria.createdFromInclusive()
                    )
                );
            }

            if (criteria.createdToExclusive() != null) {
                p.add(
                    cb.lessThan(
                        root.get("createdAt"),
                        criteria.createdToExclusive()
                    )
                );
            }

            return cb.and(p.toArray(Predicate[]::new));
        };
    }
}
```

### 12.1. Predicate composition

Có thể tạo từng `Specification` rồi `and`/`or` rõ ràng, tránh một method khổng lồ. Security predicates phải được compose theo cách không bị “OR” vô tình làm rơi tenant filter.

### 12.2. Query type nằm ở entity root

`Specification<SalesOrder>` thường chọn entities. Nếu cần projection DTO tối ưu, có thể dùng custom repository/CriteriaQuery<DTO> hoặc framework hỗ trợ projection phù hợp; đừng assume mọi version có sẵn dynamic specification-to-DTO behavior giống nhau.

### 12.3. Avoid fetch joins trong count phase

Một Specification thực hiện `root.fetch("lines")` có thể gây count query invalid hoặc collection pagination issues. Tách fetch plan khỏi reusable predicate specifications khi có Page.

### 12.4. Criteria API type-safety

`root.get("createdAt")` dùng string field names; có thể dùng JPA static metamodel `SalesOrder_.createdAt` nếu project generate metamodel. Test và compiler giúp bắt lỗi sớm hơn.

---

## 13. JPQL cố định hay Criteria động?

| Tình huống | Giải pháp thường phù hợp |
|---|---|
| Tìm một Order theo ID+tenant | Derived query |
| List theo status với static sort | Derived query hoặc @Query |
| DTO với Customer name | @Query constructor expression |
| Search nhiều filters optional | Specification/Criteria |
| Complex analytics/grouping | @Query/native SQL/custom read repo |
| Dynamic projection và keyset | Custom EntityManager/Criteria/SQL |
| Query có vendor-specific syntax | Native SQL có kiểm soát |
| Mỗi filter có business semantics riêng | Named specification/predicate methods |

### 13.1. Tránh áp một kỹ thuật cho mọi trường hợp

Chỉ vì team thích Specification không có nghĩa một `findByIdAndTenantId` phải dùng Criteria. Ngược lại, 20 optional filters nhét vào một `@Query` có thể khó hiểu và khó tối ưu.

### 13.2. Query By Example (QBE)

Spring Data QBE hữu ích cho một số tìm kiếm đơn giản dựa vào mẫu đối tượng nhưng có giới hạn khi cần ranges, nested OR, subqueries, groups hoặc authorization phức tạp. Không dùng QBE để thay một access-control predicate bắt buộc nếu nó có thể bị bỏ qua.

### 13.3. Querydsl hoặc jOOQ?

Đây là các công cụ bổ sung với DSL/type safety mạnh cho dynamic queries. jOOQ gần SQL hơn JPA; nếu dùng chúng, đặt implementation trong adapter và giữ repository contract rõ. Không nói chúng thuộc chuẩn JPA.

---

## 14. Tách predicate nghiệp vụ khỏi phần hiển thị

Một use case “Order đang chờ ship” có thể có quy tắc:

```text
tenant_id = authorizedTenant
status = PAID
deleted_at IS NULL
shipping_method IS NOT NULL
created_at <= cutoff
```

Một method tốt biểu diễn predicate nhất quán:

```java
List<SalesOrder> findReadyToShip(
    String authorizedTenant,
    Instant cutoff,
    int limit
);
```

### 14.1. Business status không tự bằng một enum

“ReadyToShip” có thể cần nhiều predicates. Không gọi `findByStatus(PAID)` rồi để 5 services tự áp những điều kiện khác nhau trong Java.

### 14.2. Method name không phải đủ thay thế documentation

Ghi rõ định nghĩa “ready”, sort, limit và lock semantics. Khi rule đổi, có một implementation tập trung.

### 14.3. Không đưa orchestration vào repository

Repository có thể chọn Orders đủ điều kiện, còn service xử lý shipment transitions, inventory, external calls và transaction boundaries.

---

## 15. Search theo khoảng thời gian: ranh giới nửa mở

Một bộ lọc ngày trong UI có thể là “từ 01/11 tới hết 07/11” theo timezone của người dùng.

Đừng biến nó thành `23:59:59.999` tuỳ ý. Chuyển sang khoảng:

```text
[createdFromInclusive, createdToExclusive)
```

JPQL:

```jpql
select o
from SalesOrder o
where o.tenantId = :tenant
  and o.createdAt >= :from
  and o.createdAt < :to
```

### 15.1. Ví dụ chuyển LocalDate sang Instant

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = LocalDate.of(2026, 11, 1)
    .atStartOfDay(zone)
    .toInstant();

Instant toExclusive = LocalDate.of(2026, 11, 8)
    .atStartOfDay(zone)
    .toInstant();
```

Đây là phép tính minh họa. Ứng dụng thực phải dùng business timezone hoặc user-authorized timezone đúng contract; không gắn cố định múi giờ chỉ vì server chạy tại một địa điểm.

### 15.2. Tại sao không dùng BETWEEN cho end-of-day tùy ý?

`BETWEEN` bao gồm cả hai đầu mút, dễ gây trùng/thiếu ở boundary khi độ chính xác timestamp khác nhau (milliseconds/microseconds). Half-open interval dễ ghép các ngày không chồng nhau.

### 15.3. Test DST/time zone

Với zones có daylight saving time, “một ngày” không nhất thiết luôn 24 giờ. Dùng calendar start-of-day theo zone thay vì cộng cố định 86.400 giây.

### 15.4. DB type và Java type

`Instant`/`TIMESTAMP WITH TIME ZONE`/`TIMESTAMP` có mapping phụ thuộc DB/provider. Test round-trip và predicate boundary trên target DB.

---

## 16. Tìm kiếm chuỗi với LIKE: escaping và collation

Ví dụ tìm Customer display name chứa keyword:

```jpql
select c
from Customer c
where lower(c.displayName) like :pattern escape '!'
```

Code chuẩn bị pattern với escape character `!`:

```java
static String likeContainsPattern(String raw) {
    String normalized =
        raw.strip().toLowerCase(Locale.ROOT);

    String escaped = normalized
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");

    return "%" + escaped + "%";
}
```

### 16.1. Escape wildcard, không nối SQL string

Pattern được truyền qua `setParameter("pattern",...)`. Không tự nối user input thành JPQL/SQL literal.

### 16.2. Có cần lower() không?

Nếu muốn case-insensitive search, `lower(...)` có thể được dùng nhưng có thể ảnh hưởng index usage và Unicode/collation behavior. Cân nhắc function index, DB collation hoặc full-text search trên DB mục tiêu.

### 16.3. Phân biệt substring search và prefix search

`%abc%` thường khó tận dụng B-tree index truyền thống hơn `abc%`. Nếu business chỉ cần “bắt đầu bằng”, dùng prefix predicate và index thích hợp.

### 16.4. Đặt giới hạn keyword

Một chuỗi quá dài hoặc chứa toàn wildcards có thể tốn tài nguyên. Validate length, normalize policy, rate-limit nếu cần; không coi escaping là đủ để chống mọi expensive queries.

### 16.5. Native/full-text tùy database

PostgreSQL trigram/full-text, Elasticsearch hay các hệ tìm kiếm riêng có use cases khác nhau. Đừng nhét truy vấn full-text phức tạp vào một derived `ContainingIgnoreCase` rồi mặc định nó scale tốt.

---

## 17. Ý nghĩa của null, empty string và empty collection

Với `OrderSearchCriteria.status() == null`, chọn một semantics duy nhất:

- `null` = không lọc theo status.
- Status enum = lọc đúng giá trị.
- Empty string từ HTTP = validation failure hoặc normalize thành absent theo policy.

### 17.1. Đừng nhầm null với tìm rows có NULL column

Với input `customerId=null`, có use case cần “không lọc Customer”; use case khác cần “Orders không có Customer”. Hai semantics không giống nhau.

### 17.2. Không tạo `IN ()` rỗng tuỳ tiện

Một danh sách IDs rỗng có thể dẫn tới SQL invalid trên một số dialects. Với API `findByIds(empty)`, nhiều khi trả `List.of()` ngay là hợp lý; nếu caller yêu cầu “không filter”, cần một kiểu input khác rõ ràng.

### 17.3. Validate ID list sizes

`IN (:ids)` với 20 IDs khác 100.000 IDs. Giới hạn batch/chunk theo DB parameter limits và memory.

### 17.4. Không coi absence trong Java là evidence của quyền

Một `Optional.empty()` có thể nghĩa là không tồn tại **hoặc** không nằm trong authorized scope. Service/API chọn 404/403 theo security policy, không đưa chi tiết thừa.

---

## 18. Sắp xếp ổn định là một phần hợp đồng

Nếu query:

```jpql
order by o.createdAt desc
```

và nhiều Orders có cùng timestamp, thứ tự giữa các rows có thể thay đổi. Với pagination, điều này dễ tạo duplicate/missing items giữa pages.

Dùng tie-breaker duy nhất:

```jpql
order by o.createdAt desc, o.id desc
```

### 18.1. Default sort phải được xác định

Không để “database trả theo insertion order” trở thành hợp đồng ngầm.

### 18.2. Sort động phải có allowlist

Ví dụ client gửi `sortField=createdAt`, `direction=desc`. Service chỉ cho các fields đã được duyệt: createdAt, totalAmount, status. Không truyền nguyên string làm SQL identifier.

### 18.3. Null sort semantics

DBs khác nhau ở `NULLS FIRST/LAST` defaults và support. Nếu sort field nullable, định nghĩa thứ tự rõ và test target dialect.

### 18.4. Sort theo collection không rõ nghĩa

“Order by line.product.name” với một Order có nhiều Lines phải định nghĩa MIN/MAX/first/aggregate. Nếu không, join nhân root rows và pagination bị sai.

---

## 19. Phân trang: Page, Slice, List và cursor

Cần chọn dựa trên UX:

| UX | Contract gợi ý |
|---|---|
| Bảng có số trang và total | `Page<OrderListRow>` |
| Nút “Load more” | `Slice<OrderListRow>` |
| Feed cuộn vô hạn | Cursor/keyset + slice DTO |
| Top 10 mới nhất | Bounded `List` với sort |
| Export lớn | Chunked cursor/stream |
| Chi tiết một item | `Optional<Detail>` |

### 19.1. Limit page size ở boundary

```java
int safeSize = Math.min(
    Math.max(requestedSize, 1),
    100
);
Pageable page = PageRequest.of(
    Math.max(requestedPage, 0),
    safeSize,
    Sort.unsorted()
);
```

### 19.2. Validate thay vì âm thầm sửa tùy API

Clamp size giúp giới hạn tài nguyên, nhưng contract public có thể cần trả 400 nếu input không hợp lệ. Chọn chính sách và test, không để hai endpoints xử lý khác nhau bất ngờ.

### 19.3. OFFSET sâu có chi phí

Với nhiều rows, OFFSET lớn có thể scan/sort nhiều dữ liệu. Khi UX chỉ cần tuần tự “next”, keyset pagination có thể hiệu quả hơn.

### 19.4. Page count có thể rất đắt

Nếu count toàn dataset tốn, cân nhắc Slice/estimated count/read model theo business contract; không tự trả một total giả như thể exact.

---

## 20. Cursor/keyset pagination: hợp đồng nên diễn tả gì?

Một cursor có thể mang sort key cuối cùng:

```text
lastCreatedAt = 2026-11-15T08:00:00Z
lastId = 98765
```

JPQL (sort giảm dần):

```jpql
select o.id
from SalesOrder o
where o.tenantId = :tenant
  and o.deletedAt is null
  and (
      o.createdAt < :lastCreatedAt
      or (
          o.createdAt = :lastCreatedAt
          and o.id < :lastId
      )
  )
order by o.createdAt desc, o.id desc
```

### 20.1. Page đầu không có cursor

Dùng query variant không có cursor predicate hoặc dynamic Criteria. Không truyền những giá trị sentinel như timestamp min nếu logic có thể sinh edge cases.

### 20.2. Cursor không phải security token nếu chưa thiết kế như vậy

Cursor encode dữ liệu sort không có nghĩa có quyền truy cập. Query vẫn cần tenant/authorization predicates; nếu cursor chứa thông tin nhạy cảm, bảo vệ/encode/sign theo contract.

### 20.3. Sort key có thể thay đổi

Nếu `createdAt` immutable, keyset đơn giản hơn. Nếu sort theo field mutable như status/updatedAt, items có thể di chuyển giữa pages do concurrent updates. Cần policy consistency.

### 20.4. Không bắt một cursor API hỗ trợ random page jumps

Cursor thường tốt cho sequential navigation, còn “nhảy trang 100” đòi thiết kế khác. Không giả rằng Page và Cursor thay nhau mà không đổi UX.

---

## 21. Phân trang root entities có to-many collection

Một anti-pattern:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
where o.tenantId = :tenant
order by o.createdAt desc
```

kết hợp `setMaxResults(50)`.

### 21.1. Một Order có nhiều Lines sẽ sinh nhiều SQL rows

LIMIT trên joined rows khác “50 Orders đầy đủ”. Provider có thể paginate in memory, báo warning hoặc fail theo version/config.

### 21.2. Giải pháp theo use case

- List chỉ cần totals/counts → DTO/aggregate query, không load Lines.
- Page Orders kèm Lines → **page IDs trước, fetch children theo page IDs**.
- Một Order detail có collection nhỏ → collection fetch join/EntityGraph có thể hợp lý.
- Order có 50.000 Lines → page riêng Lines.

### 21.3. Two-step contract

```text
Step 1: SELECT Order IDs with filter/sort/page
Step 2: SELECT Lines / graph WHERE order_id IN (:pageIds)
Step 3: Map DTOs and restore original order
```

### 21.4. Đo rows chứ không chỉ query count

Một giant join có một SQL nhưng có thể truyền hàng chục nghìn duplicated rows. Một few-query plan thường rõ và hiệu quả hơn.

---

## 22. JOIN FETCH, EntityGraph và projection là quyết định per method

Ví dụ đọc entity để xử lý state:

```java
@Query(
    """
    select o
    from SalesOrder o
    join fetch o.customer
    where o.id = :id
      and o.tenantId = :tenant
      and o.deletedAt is null
    """
)
Optional<SalesOrder> findActiveWithCustomer(
    @Param("id") Long orderId,
    @Param("tenant") String authorizedTenant
);
```

### 22.1. Không thêm `join fetch o.customer` ở mọi query

Nếu use case không dùng Customer, fetch join tải dữ liệu thừa. Fetch plan nên phù hợp response/domain logic.

### 22.2. EntityGraph có thể diễn đạt cùng ý định

Spring Data `@EntityGraph(attributePaths={"customer"})` trên query method là lựa chọn khác. EntityGraph mô tả fetch graph, không hứa chính xác một SQL statement.

### 22.3. Tránh fetch nhiều to-many collections

Join Lines+Payments+Notes có thể tạo Cartesian row explosion và rủi ro Hibernate multiple-bag limitations. Tách read methods/query sections.

### 22.4. Không dùng EAGER mapping để thay query design

`@ManyToOne(fetch=EAGER)` có thể khiến mọi use case phải tải Customer, đôi khi bằng secondary selects. Tối ưu phải xuất phát từ consumer.

---

## 23. Phân biệt load-for-update với load-for-display

Hai consumer cần cùng Order ID nhưng mục đích khác:

**Display:**

```java
Optional<OrderDetailResponse> findDetail(
    String authorizedTenant,
    Long orderId
);
```

**Change status:**

```java
Optional<SalesOrder> findActiveForTransition(
    String authorizedTenant,
    Long orderId
);
```

### 23.1. Khi cần sửa, managed entity có ích

Application service thực hiện:

```java
@Transactional
public void shipOrder(
        String authorizedTenant,
        Long id
) {
    SalesOrder order =
        orderRepository.findActiveForTransition(
            authorizedTenant,
            id
        ).orElseThrow(OrderNotFoundException::new);

    order.markShipped();
    // Dirty checking/flush at transaction boundary.
}
```

### 23.2. Không tải collection không liên quan

Nếu `markShipped` chỉ kiểm tra status, không cần fetch Lines/Products. Nếu rule đòi inventory/lines, load đúng relations/queries cần để giữ invariant.

### 23.3. DTO không được theo dõi thay đổi

Chỉ đọc `OrderDetailResponse` rồi sửa field trên DTO không cập nhật database.

### 23.4. Tách mục đích không có nghĩa tách mọi query thành repository khác

Có thể dùng cùng domain repository với methods khác nhau. Tách interface khi read model/traffic/complexity đủ khác để lợi ích rõ.

---

## 24. Đặt ranh giới transaction ở đâu?

JPA repository methods thường là thành phần của transaction do application service điều phối.

```text
Controller
  -> Service @Transactional
       -> repository.findActiveForTransition(...)
       -> domain invariant checks
       -> entity state mutation
       -> transaction flush/commit
```

### 24.1. Read-only không tự xử lý N+1

`@Transactional(readOnly=true)` có thể là hint/optimization theo transaction manager, không thay query shape. Mapper gọi lazy getters trong loop vẫn tạo N+1.

### 24.2. Read consistency giữa nhiều queries

Detail load Order+Customer rồi Lines+Product bằng hai queries có thể thấy dữ liệu ở hai thời điểm dưới READ COMMITTED. Nếu cần snapshot, cân nhắc isolation/versions/read model.

### 24.3. Không mở transaction cho việc gọi external HTTP lâu

Giữ DB locks/connections khi gọi remote service có thể gây pool exhaustion. Repo contract và service orchestration cần ranh giới rõ.

### 24.4. Không đặt @Transactional tuỳ tiện trên private method

Trong proxy-based Spring transactions, self-invocation có thể không đi qua advice. Test behavior thật với configuration của dự án.

---

## 25. Repository và soft delete

Nếu dùng `deletedAt`, cần định nghĩa:

- Method public list có loại deleted rows không?
- Admin restore có được thấy deleted không?
- Count active có bỏ deleted không?
- Exists lookup theo ID có phân biệt deleted không?
- Update/delete thao tác có kiểm tra current state không?

### 25.1. Một cặp methods rõ

```java
Optional<SalesOrder> findByIdAndTenantIdAndDeletedAtIsNull(
    Long id,
    String tenantId
);

Optional<SalesOrder> findByIdAndTenantId(
    Long id,
    String tenantId
);
```

Method thứ hai cần giới hạn caller/use case (ví dụ admin recovery), không để ai cũng dùng và vô tình bypass soft-delete visibility.

### 25.2. Khóa “duy nhất trong active rows”

Nếu business cho phép dùng lại externalRef của một Order đã soft-deleted, có thể cần partial UNIQUE index theo `deleted_at is null` (database-specific). Repo `existsByExternalRef` không thay DB constraint.

### 25.3. Static provider filters cần test

Hibernate filters/`@Where`-like settings/soft delete annotations có behavior theo version. Đừng assume chúng được áp vào mọi native SQL, bulk DML, count query và related collections.

### 25.4. Không trộn recover query vào normal list

Một method `findAllIncludingDeleted` rất dễ bị gọi nhầm. Tên và adapter/authorization boundary phải phản ánh đặc quyền.

---

## 26. Tenant và authorization là hợp đồng xuyên suốt

Một service:

```java
public Optional<SalesOrder> findOrder(
        Long orderId,
        AuthenticatedPrincipal principal
) {
    String tenant = principal.authorizedTenantId();

    return repository
        .findByIdAndTenantIdAndDeletedAtIsNull(
            orderId, tenant
        );
}
```

### 26.1. Không tin tenant header tùy ý

Nếu client có thể truyền `tenantId`, phải xác minh nó thuộc phạm vi quyền của authenticated principal. Repository nhận **authorized scope**, không nhất thiết nhận raw request input.

### 26.2. Search, count, exists phải cùng scope

Không có ý nghĩa khi list áp tenant còn count bỏ tenant, hoặc exists cho phép dò sự tồn tại của Order tenant khác.

### 26.3. Query theo nhiều tenant hợp lệ

Admin có quyền xem nhiều tenants có thể dùng `tenantId IN (:authorizedTenantIds)`, nhưng phải giới hạn số IDs và đảm bảo tập đó đến từ policy, không từ client tự chọn.

### 26.4. ID không thay authorization

Một Long ID khó đoán không phải là access control. Không gọi unscoped `findById` trong controller chỉ vì ID là UUID/long.

### 26.5. Query caching cần scoped keys

Nếu cache DTO theo `orderId` nhưng data IDs chỉ unique trong tenant, key phải bao gồm tenant; kể cả globally unique IDs vẫn cần authorization check.

---

## 27. Kiểm tra tồn tại: exists không thay ràng buộc database

Ví dụ trước khi tạo Order với externalReference:

```java
boolean alreadyUsed = repository
    .existsByTenantIdAndExternalRefAndDeletedAtIsNull(
        tenant,
        externalRef
    );
```

Nhưng:

```text
Tx A: exists -> false
Tx B: exists -> false
Tx A: INSERT -> success
Tx B: INSERT -> ?
```

### 27.1. Race condition vẫn tồn tại

`existsBy` chỉ là kiểm tra ở một thời điểm. Dùng DB UNIQUE constraint đúng scope làm hàng rào cuối cùng.

### 27.2. Tránh TOCTOU assumptions

Không coi `if (!exists) save` là atomic. Nếu nghiệp vụ cần idempotency, khóa/request-key và retry behavior phải được thiết kế riêng.

### 27.3. Exists để trả lời câu hỏi, không để serialize entity

Nếu chỉ cần boolean, tránh `findBy...().isPresent()` có thể tạo entity hydration không cần thiết. Tuy nhiên actual query do framework sinh ra cần đo nếu hot path.

### 27.4. Không lộ user enumeration

`existsByEmail` ở public API có thể cho người lạ biết email đăng ký. Khi security policy yêu cầu, trả generic response.

---

## 28. Count và aggregate methods

Tổng tiền đã thanh toán trong một khoảng:

```java
public record RevenueSummary(
    long orderCount,
    BigDecimal totalAmount
) {}
```

JPQL constructor:

```java
@Query(
    """
    select new com.example.shop.api.RevenueSummary(
        count(o),
        coalesce(sum(o.totalAmount), 0)
    )
    from SalesOrder o
    where o.tenantId = :tenant
      and o.deletedAt is null
      and o.status = :status
      and o.createdAt >= :from
      and o.createdAt < :to
    """
)
RevenueSummary summarizeRevenue(
    @Param("tenant") String tenant,
    @Param("status") OrderStatus status,
    @Param("from") Instant from,
    @Param("to") Instant to
);
```

### 28.1. Aggregate trả scalar không cần hydrate Orders

Đừng load một triệu Orders vào Java chỉ để tính SUM. Database có aggregate operations; query chỉ chọn kết quả cần.

### 28.2. Kiểu dữ liệu aggregate

`count` thường trả `Long` ở JPQL, `sum` trên BigDecimal trả BigDecimal; constructor của DTO/record phải khớp. `COALESCE` literal type inference có thể khác theo provider; kiểm tra JPQL parse/runtime, hoặc xử lý null result trong Java nếu cần portability.

### 28.3. COUNT khác COUNT DISTINCT

Nếu join Lines, một Order có 3 Lines có thể bị đếm 3 lần. Dùng `count(distinct o)` hoặc thiết kế predicate EXISTS theo bài toán.

### 28.4. Aggregate cần tính định nghĩa nghiệp vụ

“Doanh thu” là gross, net, paid, refunded, tax included, currency nào? Repository nên có tên và filter phản ánh định nghĩa, không dùng `sumAllTotals()` mơ hồ.

### 28.5. Multi-currency không cộng như cùng đơn vị

Nếu Orders có nhiều currencies, phải group theo currency hoặc chuyển đổi theo rate policy; không cộng BigDecimal khác đơn vị thành một số vô nghĩa.

---

## 29. Filter parents theo child predicate: EXISTS thường rõ nghĩa

“Các Order có ít nhất một Line thuộc Product SKU X”:

```jpql
select o
from SalesOrder o
where o.tenantId = :tenant
  and o.deletedAt is null
  and exists (
      select l.id
      from OrderLine l
      where l.order = o
        and l.product.sku = :sku
  )
```

### 29.1. Vì sao không `join o.lines l` rồi DISTINCT luôn?

Join to-many tạo nhiều SQL rows cho cùng root. `EXISTS` diễn đạt chính xác predicate “có ít nhất một” và có thể giữ query cardinality theo Orders, tùy DB optimizer.

### 29.2. Count query đơn giản hơn

Root `count(o)` kết hợp EXISTS thường tránh nhân rows, nhưng performance vẫn cần plan/index trên target DB.

### 29.3. Không fetch filtered children rồi coi collection đầy đủ

Lọc Lines trong join không có nghĩa một partial collection có thể được xem như toàn bộ Order.lines đã initialized. Tách root filtering và child loading.

### 29.4. Authorization cho subquery

Nếu hệ thống multi-tenant và FKs/row filters không đủ bảo vệ, cần bảo đảm child predicate không thể đi ra ngoài authorized tenant scope.

---

## 30. Thiết kế top-N per group không giống top-N toàn bộ

“Mỗi Order hiển thị tối đa 3 Lines gần nhất” là **top 3 Lines trên mỗi Order**, không phải:

```jpql
select l
from OrderLine l
where l.order.id in :ids
order by l.id desc
```

với `setMaxResults(3)`, vì query đó trả tối đa 3 Lines cho **toàn bộ tập Orders**, không phải 3 cho từng Order.

### 30.1. Hướng giải quyết

- Page Order IDs, rồi dùng native SQL/window function `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY ...)` trên DB hỗ trợ.
- Dùng materialized/read model chứa preview.
- Nếu số Orders rất nhỏ, query riêng có kiểm soát đôi khi chấp nhận được, nhưng phải đo N+1.

### 30.2. Native SQL cần type-safe mapping

Không nối input trực tiếp vào SQL, trả DTO/`@SqlResultSetMapping`/mapping cụ thể theo provider. Window functions không portable JPQL truyền thống theo mọi version.

### 30.3. Method name

`findRecentLinePreviewsForOrders(ids,limitPerOrder)` diễn đạt rõ cardinality. `findTop3Lines(ids)` dễ gây hiểu lầm.

---

## 31. Query dữ liệu cần sửa và locking

Một batch worker chọn Orders để ship có thể cần tránh hai workers xử lý cùng một Order.

### 31.1. Pessimistic lock cho query theo scope

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query(
    """
    select o
    from SalesOrder o
    where o.id = :id
      and o.tenantId = :tenant
      and o.deletedAt is null
    """
)
Optional<SalesOrder> findActiveForExclusiveUpdate(
    @Param("id") Long id,
    @Param("tenant") String tenant
);
```

`@Lock` là Spring Data JPA annotation; `LockModeType` thuộc Jakarta Persistence.

### 31.2. Lock không được áp bừa lên mọi read query

Lock làm tăng contention/deadlock risk, đặc biệt khi transaction kéo dài. Chỉ dùng nếu business invariant thật sự đòi.

### 31.3. “Skip locked” không portable theo một method annotation chung

Các kiểu claim queue sử dụng `FOR UPDATE SKIP LOCKED` là database/dialect-specific hoặc cần query hints/provider extension. Test với DB target và transaction boundaries.

### 31.4. Optimistic locking thường đủ cho CRUD thông thường

`@Version` giúp phát hiện concurrent stale updates khi flushing entity changes. Repo không cần pessimistic lock nếu retry/conflict semantics chấp nhận được.

### 31.5. Không giữ lock khi gọi external service

Claim task state/commit trước rồi xử lý external call bằng workflow/idempotency phù hợp, thay vì giữ DB transaction mở trong suốt network request.

---

## 32. Bulk update methods: thật sự là một contract khác

Nếu muốn chuyển nhiều Order từ PAID sang SHIPPED:

```java
@Modifying
@Query(
    """
    update SalesOrder o
    set o.status = :next
    where o.tenantId = :tenant
      and o.deletedAt is null
      and o.status = :current
    """
)
int transitionStatus(
    @Param("tenant") String tenant,
    @Param("current") OrderStatus current,
    @Param("next") OrderStatus next
);
```

### 32.1. Bulk JPQL DML bypass normal managed-entity semantics

Bulk UPDATE không gọi từng entity domain method, không mặc định xử lý entity callbacks/dirty checking/automatic optimistic-version increment như cách update managed entities. Nếu business cần những semantics đó, hãy cân nhắc phương án khác hoặc explicit conditions/version handling.

### 32.2. Persistence context có thể stale

Managed SalesOrder đã được load trước bulk update có thể vẫn giữ status cũ. Cần `flush`/`clear`/reload theo workflow; Spring Data `@Modifying(flushAutomatically=...,clearAutomatically=...)` có options nhưng việc clear sẽ detach các entities khác.

### 32.3. Return count là số row affected, không phải domain success count

`executeUpdate`/Spring `@Modifying` có thể trả số rows bị ảnh hưởng. Nó không tự chứng minh external side effect đã xong hoặc các business transitions được authorized.

### 32.4. Không gọi transitionStatus trong transaction chưa có ranh giới

Bulk DML cần transaction. Service nên làm rõ scope, authorization và rollback policy.

### 32.5. Tên phương thức phải nêu mutation

`transitionStatus`/`markExpiredOrders` rõ hơn `findAndUpdateSomething`. Các methods ghi không thuộc nhóm read queries dù cùng repository infrastructure.

---

## 33. Các kết quả “không tìm thấy” cần chính sách nhất quán

```java
Optional<SalesOrder> order =
    repository.findByIdAndTenantIdAndDeletedAtIsNull(
        id, tenant
    );
```

Không tồn tại có thể vì:

- ID chưa từng được tạo.
- ID thuộc tenant khác.
- Record đã soft-deleted.
- Caller thiếu permission.
- Data đã bị xóa đồng thời.

### 33.1. Repository nên biểu diễn sự vắng mặt

`Optional.empty()` thích hợp cho 0–1. Service quyết định business exception/API response.

### 33.2. GetSingleResult và NoResultException

JPA `getSingleResult` có thể ném `NoResultException` và `NonUniqueResultException`; `getResultList` cho 0 rows là empty list. Một adapter có thể wrap thành Optional nhưng phải tôn trọng cardinality.

### 33.3. Đừng bỏ các nguyên nhân lỗi vào cùng một “null”

Đối với use case internal quan trọng, kết quả phân biệt unauthorized/soft-deleted có thể cần ở service theo quyền. Tránh gửi chi tiết phân biệt này cho caller không được phép.

### 33.4. Không biến DB unavailable thành Optional.empty

Lỗi kết nối hay timeout không phải “không có Order”. Catch-all rồi trả Optional.empty che hệ thống đang hỏng.

---

## 34. Error contract của repository

Repository có thể gặp:

- Query syntax/mapping error.
- Database connection/timeout.
- Unique/FK constraint violation.
- Deadlock/lock timeout.
- Optimistic lock conflict.
- Non-unique result.
- Stale object/persistence context issue.

### 34.1. Phân loại lỗi tại application boundary

Spring `DataAccessException` hierarchy có thể hỗ trợ phân loại, nhưng không đổi thành business error không phù hợp. Một `DataIntegrityViolationException` không luôn là duplicate ID.

### 34.2. Không log entity/SQL bind payload

Exception có thể chứa SQL, constraint names, rejected values. Log safe error codes, operation name, request ID; raw stack trace chỉ trong restricted diagnostic setting.

### 34.3. Không catch rồi tiếp tục dùng transaction failed

Sau JPA/JDBC flush exception, transaction có thể rollback-only/aborted. Rollback và mở transaction mới theo recovery policy.

### 34.4. Timeout cũng là một phần contract vận hành

Query search có thể chạy rất lâu nếu filters quá rộng. Đặt timeout/query limits và UX phù hợp; không chỉ tăng HTTP timeout vô hạn.

---

## 35. Thiết kế custom repository khi @Query không còn phù hợp

Khi requirements phức tạp:

- Query composition nhiều joins/optional filters.
- DTO shape có nested sections.
- Keyset pagination.
- Window functions/native SQL.
- User-visible report dynamic groupings.
- Multi-step query under one transaction.
- Vendor-specific search/locking.
- Batched reads theo IDs với order restoration.

Có thể tạo một **custom repository fragment** hoặc read adapter.

Interface:

```java
public interface OrderSearchQueries {

    Slice<OrderListRow> searchAfter(
        String authorizedTenant,
        OrderSearchCriteria criteria,
        OrderCursor cursor,
        int limit
    );
}
```

Implementation minh họa:

```java
@Repository
public class OrderSearchQueriesImpl
        implements OrderSearchQueries {

    @PersistenceContext
    private EntityManager em;

    @Override
    public Slice<OrderListRow> searchAfter(
            String authorizedTenant,
            OrderSearchCriteria criteria,
            OrderCursor cursor,
            int limit
    ) {
        // CriteriaBuilder/query implementation.
        // Apply mandatory tenant/soft-delete filters.
        // Apply cursor predicate and stable ordering.
        // Fetch limit+1, return bounded Slice.
        throw new UnsupportedOperationException(
            "Illustrative contract"
        );
    }
}
```

### 35.1. Đây là interface design, không phải completed implementation

`throw UnsupportedOperationException` là placeholder minh họa; không đem vào production. Khi triển khai, cần build actual query, bind parameters, map DTO, kiểm tra hasNext và transaction boundaries.

### 35.2. Kết hợp với JpaRepository

Trong Spring Data, repository interface có thể kế thừa custom fragment `OrderSearchQueries`; convention tên implementation/configuration có thay đổi theo Spring Data versions. Chạy integration test để chắc custom fragment được kết nối.

### 35.3. Hạn chế “siêu repository”

Một interface 120 methods có thể bị chia theo query responsibility: `OrderReadQueries`, `OrderWriteRepository`, `OrderAnalyticsQueries`, nhưng tránh phân tách máy móc tới mức mỗi method một class.

### 35.4. Tách interface không thay transaction model

Một use case nhiều repositories vẫn cần transaction/service orchestration rõ.

---

## 36. Tách read side khi nhu cầu hiển thị khác domain aggregate

Trong hệ thống nhỏ:

```text
SalesOrderRepository
  -> find for update
  -> find display rows
  -> count
```

Có thể là đủ. Trong hệ thống lớn:

```text
OrderCommandRepository
  -> load managed aggregate / persist

OrderListQueries
  -> search DTO rows / count

OrderDetailQueries
  -> detail DTO graph

OrderReportingQueries
  -> aggregates / exports
```

### 36.1. Không nhất thiết triển khai full CQRS

Tách read/write interfaces không đòi hai databases hoặc event sourcing. Mục tiêu là rõ contract và tránh entity graph không phù hợp.

### 36.2. Chọn read model tùy workload

Một dashboard cần pre-aggregated revenue có thể dùng materialized view/read table. Nhưng phải thiết kế refresh/consistency và không giả dữ liệu always-current.

### 36.3. Tránh duplicate business predicates

Nếu active/tenant filters xuất hiện ở 10 queries, nên có conventions/shared specification/port-level tests để bảo đảm chúng không lệch. Cẩn thận khi abstract quá sâu làm SQL khó kiểm soát.

---

## 37. Làm việc với nhiều IDs mà vẫn giữ thứ tự

Một query:

```jpql
select o
from SalesOrder o
where o.id in :ids
  and o.tenantId = :tenant
```

**Không đảm bảo giữ thứ tự của `ids`**.

### 37.1. Khi cần output theo thứ tự input

```java
Map<Long, SalesOrder> byId = fetched.stream()
    .collect(Collectors.toMap(
        SalesOrder::getId,
        Function.identity()
    ));

List<SalesOrder> ordered = ids.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
```

### 37.2. Thận trọng với missing IDs

Nếu một ID không thuộc tenant, đã soft delete hoặc bị xóa đồng thời, lọc null có thể làm output ngắn hơn. Contract phải nêu: bỏ qua, báo thiếu, hay trả per-ID statuses.

### 37.3. Đừng query 10.000 IDs bằng một IN unbounded

Chunk theo size hợp lý, đo SQL plans và parameter limits. Với batch lớn, temporary table/array parameter/native join có thể phù hợp hơn tùy database.

### 37.4. IDs trùng trong input

Xác định có giữ duplicate hay unique. Một `Map` sẽ hợp nhất results theo ID; nếu caller muốn từng input item, reconstruction cần tính cả duplicates.

---

## 38. Fetch nhiều quan hệ bằng nhiều truy vấn có kiểm soát

Một Order detail có Customer, Lines, Product, Payments:

```text
Query 1: Order + Customer
Query 2: OrderLines + Products where order_id=:id
Query 3: Payments where order_id=:id
Map: OrderDetailResponse
```

### 38.1. Ba queries không phải “xấu”

Nhiều khi ít rows và dễ dự đoán hơn một join gộp Lines × Payments tạo Cartesian multiplication.

### 38.2. Không chạy query mới trong vòng lặp theo từng Line

Nếu Line.product LAZY và mapper gọi tên cho 100 Lines, có thể thành N+1. Query 2 nên fetch to-one Product hoặc DTO projection.

### 38.3. Service đọc nhiều queries có thể cần transaction read-only

Đảm bảo consistent authorization/filter semantics, và hiểu isolation nếu concurrent updates giữa queries.

### 38.4. Tránh trả managed graph cho serializer

Map DTO trong service/repository read adapter; không để Jackson tự duyệt relation sau khi transaction kết thúc.

---

## 39. Dữ liệu cập nhật theo thời gian: latest, active, historical

Các phương thức:

```java
Optional<OrderSnapshot> findLatestSnapshotForOrder(
    String tenant,
    Long orderId
);

List<OrderStatusEventRow> listStatusHistory(
    String tenant,
    Long orderId,
    int limit
);
```

### 39.1. “Latest” cần sort key bất biến hoặc tie-breaker

Nếu nhiều events có cùng timestamp, sort by `timestamp desc,id desc`. Không lấy “row cuối cùng trong List” khi query không ORDER BY.

### 39.2. Historical record khác current state

Một domain entity Order.status biểu diễn current state; history có thể ở audit/event table. Đừng tái tạo lịch sử từ current row.

### 39.3. Temporal data có version/cutoff semantics

Nếu cần “trạng thái tại thời điểm T”, query khác `findById`. Có thể dùng snapshot table/temporal DB/system-versioned tables tùy kiến trúc.

### 39.4. Quyền đọc lịch sử có thể khác hiện tại

Historical data có thể chứa fields/actor details nhạy cảm hơn list hiện tại. Cần authorization và retention riêng.

---

## 40. GraphQL và batch queries

Một GraphQL endpoint trả danh sách Orders, rồi resolver tải Customer cho từng Order:

```text
Orders query: 1 SELECT
Customer resolver: N SELECTs
```

### 40.1. Repository cung cấp batch-by-IDs

```java
Map<Long, CustomerSummary> findCustomerSummaries(
    String authorizedTenant,
    Set<Long> customerIds
);
```

Implementation có thể dùng bounded `IN`/DTO projection rồi map theo ID.

### 40.2. Không đặt tenant scope chỉ ở outer resolver

Nested lookups vẫn phải tôn trọng authorized tenant/owner relationship; data loaders/caches nên scoped per request và permission context.

### 40.3. Contract có thể trả Map thay vì List

Nếu caller cần match theo IDs, Map thể hiện việc lookup. Tuy nhiên duplicate/missing IDs và ordering phải được document.

### 40.4. Batch query không phải global cache vô hạn

DataLoader có thể cache within request; không được chia sẻ một map không scope giữa users/tenants.

---

## 41. Dữ liệu lớn và export queries

Sai:

```java
List<SalesOrder> orders = repository.findAll();
for (SalesOrder order : orders) {
    writer.write(order.getCustomer().getDisplayName());
}
```

Vấn đề: load toàn bảng, N+1 Customer, persistence context phình to, khó retry sau thất bại.

### 41.1. Repository dành riêng export

```java
List<OrderExportRow> readExportChunk(
    String authorizedTenant,
    Instant snapshotCutoff,
    OrderCursor after,
    int chunkSize
);
```

### 41.2. DTO projection và chunks

Chọn đúng columns, giới hạn rows, dùng keyset/cursor. Không hydrate toàn entities nếu không cập nhật chúng.

### 41.3. Không giữ transaction quá lâu

Đọc theo chunks/stream cần thiết kế snapshot consistency, connection handling, retry/resume và output backpressure.

### 41.4. Export là job có trạng thái

Application service quản lý progress, checkpoint, file storage, retries và idempotency; repository chỉ trả dữ liệu từng bước.

---

## 42. Index là kết quả của query contract

Khi method có predicate:

```text
WHERE tenant_id = ?
  AND deleted_at IS NULL
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT 50
```

Database có thể hưởng lợi từ composite/partial index phù hợp.

Ví dụ PostgreSQL-specific:

```sql
CREATE INDEX idx_active_order_search
ON sales_order(
    tenant_id,
    status,
    created_at DESC,
    id DESC
)
WHERE deleted_at IS NULL;
```

### 42.1. Không tạo index mù quáng

Index có cost write/storage. Đo `EXPLAIN (ANALYZE,BUFFERS)` trên dataset/DB representative trước khi kết luận.

### 42.2. Query contract phải ổn định để index có ích

Nếu một method có 12 optional predicates nhưng UX thực tế thường chỉ lọc 2 fields, phân tích query frequency/parameter distribution rồi chọn indexes.

### 42.3. Không dùng index để che một method không giới hạn

Thêm index không sửa lỗi API trả hàng triệu rows. Giới hạn data volume và pagination vẫn bắt buộc.

### 42.4. Security filter cũng cần performance support

Nếu tenant predicate làm query chậm, thiết kế index/partition phù hợp thay vì bỏ tenant filter.

---

## 43. Đo hiệu năng của từng repository method

Những metrics quan trọng:

- Number of SQL SELECT statements.
- JDBC round-trips.
- Rows returned/processed.
- Query execution plan.
- p50/p95/p99 latency per use case.
- DB CPU/IO, connection wait.
- Java entity hydration/allocation.
- Memory và GC.
- Count query cost.
- Data accuracy và access scope.

### 43.1. N+1 thường ẩn ở mapper

Repository method phát 1 SQL nhưng mapping response sau đó lặp `o.getCustomer()` và phát N selects. Đo **toàn use case**, không chỉ phần repository method.

### 43.2. Fewer SQL không luôn better

Một fetch join nhiều to-many collections có thể xử lý rất nhiều rows. So sánh full latency/memory/resource consumption.

### 43.3. Dữ liệu test phải đại diện

List 50 Orders toàn cùng Customer có thể không lộ N+1 do persistence context cache. Test 50 distinct Customers, nhiều Lines và hot tenants.

### 43.4. Hibernate Statistics không phải JPA chuẩn

Có thể đo `SessionFactory.getStatistics()`/JDBC proxy trong môi trường Hibernate; provider khác cần instrumentation tương ứng. Khi test parallel, factory-level counters có thể lẫn workloads khác.

---

## 44. Testing repository contracts: không chỉ “query chạy được”

Một test tốt cần assert:

1. Đúng rows/fields.
2. Không vượt tenant/authorization scope.
3. Soft-deleted records được xử lý đúng.
4. Optional filters đúng cho từng tổ hợp.
5. Sort ổn định, tie-breaker đúng.
6. Page size/total/hasNext đúng.
7. Không nhân duplicate root rows khi join.
8. Null/empty inputs đúng contract.
9. Boundary times/precision/timezone đúng.
10. SQL count không tăng gần N+1 theo số roots.
11. Mapping projections/enum/BigDecimal đúng.
12. Transaction/concurrency semantics đúng cho write use case.

### 44.1. Tại sao flush/clear khi setup?

JPA L1 cache có thể che mapping/fetch behavior. Khi muốn test dữ liệu đọc từ DB, sau fixture persist có thể `flush` và `clear` rồi gọi repository method.

### 44.2. DataJpaTest rollback

Spring `@DataJpaTest` thường rollback transaction cuối test. Nó phù hợp mapping/read tests nhưng không chứng minh commit durability hoặc two-independent-transaction race. Dùng riêng transactional boundaries khi cần.

### 44.3. Testcontainers cho target DB

Nếu production là PostgreSQL, dùng PostgreSQL Testcontainers cho SQL/constraint behavior nhạy cảm với dialect. H2 in-memory không tái hiện toàn bộ optimizer/collation/isolation.

### 44.4. Test exact query semantics, không exact SQL aliases

ORM version có thể đổi alias format. Assert behavior và SQL budget/traces phù hợp hơn phụ thuộc raw SQL text format.

---

## 45. Ví dụ repository integration test cho query scoped DTO

Fixture:

```text
Tenant A:
  Order #1 PAID, active, Customer A
  Order #2 SHIPPED, active, Customer B
  Order #3 PAID, deleted

Tenant B:
  Order #4 PAID, active, Customer C
```

Test:

```java
@Test
void listShowsOnlyActiveOrdersOfAuthorizedTenant() {
    // Insert fixtures into test DB, flush/clear.

    Page<OrderListRow> page =
        repository.searchOrderRows(
            "tenant-a",
            OrderStatus.PAID,
            PageRequest.of(
                0, 20, Sort.unsorted()
            )
        );

    assertEquals(1, page.getTotalElements());
    assertEquals(1, page.getContent().size());
    assertEquals(1L, page.getContent().get(0).id());
    assertEquals("Customer A",
                 page.getContent().get(0).customerName());
}
```

### 45.1. Không chỉ test một tenant

Nếu data chỉ có tenant A, thiếu predicate `tenantId` trong query vẫn pass. Seed tenant B với status tương tự.

### 45.2. Deleted row cùng status

Nên có một deleted Order PAID để phát hiện bỏ sót `deletedAt is null`.

### 45.3. Page count và content phải cùng filters

Test cả metadata total và content. Count query có thể sai dù danh sách đúng.

### 45.4. Test sort với timestamp bằng nhau

Tạo hai Orders cùng createdAt, assert `id desc` theo contract.

---

## 46. Kiểm thử N+1 khi DTO thay đổi

Ban đầu DTO:

```java
record OrderListRow(
    Long id, String customerName
) {}
```

Sau đó thêm customer country:

```text
Order -> Customer -> Country
```

Nếu mapper dùng `o.getCustomer().getCountry().getName()`, có thể tạo secondary SELECTs per country.

### 46.1. Regression dataset

- 50 Orders.
- 50 distinct Customers.
- 50 distinct Countries hoặc ít cache reuse.
- New EntityManager/cold L1 khi đo.
- Assert field values, query budget.

### 46.2. Sửa bằng query shape

Có thể đổi constructor projection để join đến Country và chọn name, hoặc graph phù hợp nếu consumer cần entities.

### 46.3. Không bật EAGER trên toàn model để sửa một DTO

Nó ảnh hưởng các methods khác. Query plan phải theo use case.

---

## 47. Testing search filters theo ma trận

Với `OrderSearchCriteria`, xây các test cases:

| Case | status | customer | date | Expected |
|---|---|---|---|---|
| F1 | null | null | null | All visible active orders |
| F2 | PAID | null | null | Only PAID |
| F3 | null | Customer A | null | Only owner A |
| F4 | PAID | Customer B | range | Intersection |
| F5 | null | null | empty range | Empty or validation error theo contract |
| F6 | null | null | boundary timestamp | Correct half-open semantics |
| F7 | null | null | null | Tenant B rows excluded |
| F8 | null | null | null | Deleted rows excluded |

### 47.1. Include contradictory filters

`minAmount > maxAmount` phải bị reject (hoặc cho empty theo documented contract), không chạy query mập mờ.

### 47.2. Test Unicode/search wildcard

`%`, `_`, dấu tiếng Việt, whitespace, upper/lower case. Bảo đảm escaping/normalization/collation đúng policy.

### 47.3. Test sort whitelist

Input field `"DROP TABLE..."` không được đưa vào query. Nên bị reject như unsupported sort, không execute dynamic SQL.

### 47.4. Test huge page size

Input `size=1000000` không được khiến service trả một triệu entities. Validate hoặc clamp theo API policy.

---

## 48. Repository contract với concurrency

Một write service có flow:

```text
Load Order#42 status=PAID version=7
Check can ship
Set status=SHIPPED
Flush/commit with optimistic version check
```

### 48.1. Repository cần trả managed state

DTO-only query có thể không phù hợp nếu phải rely on dirty checking/version.

### 48.2. Test hai transactions độc lập

Tx A và B cùng đọc version 7; A commit, B commit cần conflict nếu update cùng version-controlled entity theo model.

### 48.3. Đừng dùng một EntityManager cho hai threads

EntityManager không thread-safe. Test concurrency phải dùng contexts/connections riêng.

### 48.4. Không retry toàn business operation vô điều kiện

Nếu operation có external side effect, retry sau optimistic conflict có thể lặp hành động. Dùng idempotency/outbox/workflow phù hợp.

### 48.5. Locking phải được nêu trong method contract

`findForExclusiveUpdate` khác `findForDisplay`. Caller cần biết transaction must be active và lock lifetime.

---

## 49. Cấu trúc một repository API dễ đọc

Một đề xuất cho hệ thống cỡ vừa:

```java
public interface OrderCommandRepository {
    Optional<SalesOrder> findActiveForChange(
        String authorizedTenant, Long orderId
    );

    void saveNew(SalesOrder order);
}

public interface OrderListQueries {
    Page<OrderListRow> searchVisibleOrders(
        String authorizedTenant,
        OrderSearchCriteria criteria,
        Pageable page
    );
}

public interface OrderDetailQueries {
    Optional<OrderDetailResponse> findVisibleDetail(
        String authorizedTenant, Long orderId
    );
}

public interface OrderStatisticsQueries {
    long countVisibleByStatus(
        String authorizedTenant, OrderStatus status
    );

    RevenueSummary summarizePaidOrders(
        String authorizedTenant,
        Instant fromInclusive,
        Instant toExclusive
    );
}
```

### 49.1. Đây là contract, không phải yêu cầu 4 concrete classes

Implement bằng Spring Data fragments, adapters hoặc EntityManager theo quy mô ứng dụng. Không tự động tạo một lớp cho mỗi method chỉ vì interface ở trên.

### 49.2. Tên “visible” phải có định nghĩa

Nó có thể bao gồm tenant, soft delete, ownership và authorization. Test behavior; documentation phải ghi rõ policy.

### 49.3. Write method saveNew cần semantics rõ

Spring Data `save` có persist/merge detection, nhất là assigned IDs. Nếu service cần create-only, adapter phải implement không vô tình overwrite existing row.

### 49.4. Read contracts có thể không trả JPA entities

DTO giúp tách schema/domain model khỏi API display shape.

---

## 50. Bảng quyết định phương pháp truy vấn

| Câu hỏi | Trường hợp sử dụng | Lựa chọn thường tốt |
|---|---|---|
| Tìm theo khóa có tenant? | 0–1 entity | Derived query/JPQL + Optional |
| Check đã tồn tại? | Boolean | exists query |
| Đếm status? | Scalar | COUNT |
| Trang danh sách 5 fields? | Read-only list | DTO constructor/interface projection |
| Detail có một to-one cần dùng? | Managed entity | JOIN FETCH/EntityGraph |
| Detail có 2 collections? | Aggregate view | Split bounded queries/DTO |
| Search 12 filters? | Flexible search | Criteria/Specification |
| Page root + children? | Nested list | Page IDs + fetch children |
| Cuộn vô hạn nhiều rows? | Feed | Keyset/cursor |
| Xuất CSV lớn? | Batch reporting | Chunked DTO query |
| Sort do client chọn? | Search UI | Allowlisted sorting |
| Chọn job để claim? | Concurrent worker | Lock/claim query + transaction |
| Bulk chuyển trạng thái? | Database mass update | @Modifying/JPQL DML, explicit semantics |
| Top 3 Lines cho mỗi Order? | Preview | Window function/native/read model |
| Tổng doanh thu? | Analytics | Aggregate DTO/query theo currency |
| Count có join children? | Parent count | EXISTS/count distinct đúng ngữ nghĩa |

Không có một “best query method” chung. Điều đúng nhất là **query phục vụ đúng use case với contract có thể được kiểm thử**.

---

## 51. Những sai lầm thường gặp

### 51.1. Dùng findAll cho endpoint phân trang

Chuyển tất cả rows vào Java rồi `subList` gây over-fetch và nguy cơ OOM.

### 51.2. Trả List không giới hạn từ repository method công khai

Không có max size, dễ quá tải khi dữ liệu tăng.

### 51.3. Trả Page khi không cần total

Count query có thể tốn DB resources.

### 51.4. Dùng Optional cho query không unique

Một query có thể trả nhiều rows và ném exception; cần unique predicate/DB constraint.

### 51.5. Lấy entity khi chỉ cần boolean

Có thể hydrate đối tượng không cần thiết, thay bằng exists query.

### 51.6. Đếm bằng cách load toàn collection

`order.getLines().size()` có thể gây lazy-load nguyên collection; dùng aggregate query nếu chỉ cần count.

### 51.7. Đặt tên method quá dài rồi tưởng đã rõ

Một derived method với 9 `And/Or` không thay thế documentation/filter grouping.

### 51.8. Để user truyền JPQL/SQL fragments vào repository

Dễ SQL injection và khó kiểm soát authorization.

### 51.9. Query theo ID nhưng quên tenant

Có thể lộ dữ liệu cross-tenant.

### 51.10. List filter deleted nhưng count quên deleted

Page metadata sai và có thể lộ sự tồn tại data ẩn.

### 51.11. Sorting thiếu tie-breaker

Pages có thể không ổn định khi timestamp bằng nhau.

### 51.12. Dynamic sort không allowlist

Có thể bị injection hoặc tiết lộ internal model fields; không tin raw input.

### 51.13. Dùng to-many fetch join trong Page không kiểm soát

Có thể paginate in memory hoặc sai root cardinality.

### 51.14. Dùng JOIN FETCH cho DTO projection

Không đúng mục tiêu của entity fetch join; dùng joins chọn scalar fields.

### 51.15. Fetch mọi collection để “đỡ N+1”

Có thể gây Cartesian explosion và OOM.

### 51.16. Dùng EAGER toàn cục để sửa một read endpoint

Tạo over-fetch ở endpoints khác.

### 51.17. Mapper DTO chạm lazy relations trong loop

Vẫn tạo N+1 dù API trả DTO.

### 51.18. Phân trang với ORDER BY field mutable mà không định nghĩa consistency

Rows có thể chuyển trang khi có concurrent writes.

### 51.19. Dùng offset sâu trên bảng lớn không đo

Có thể chậm dù trang đầu nhanh.

### 51.20. IN list không giới hạn

Có thể vượt bind limit và tạo query plans kém.

### 51.21. Tin IN giữ thứ tự IDs

Không có bảo đảm SQL ORDER BY; cần reorder.

### 51.22. Tìm kiếm LIKE không escape `%`/`_`

User input có thể trở thành wildcard ngoài ý định.

### 51.23. Cộng tiền nhiều currency không group

Aggregate business result sai.

### 51.24. Gọi exists rồi insert và tin không race

DB unique constraints vẫn bắt buộc.

### 51.25. Bật pessimistic lock trên mọi query

Tăng contention và deadlock risk.

### 51.26. Dùng bulk UPDATE như entity update bình thường

Bypass callbacks/version handling, persistence context có thể stale.

### 51.27. Đưa HTTP status handling vào JPA repository

Trộn application boundary với persistence layer.

### 51.28. Repository gọi external API trong transaction

Có thể giữ connection/locks lâu, khó rollback external action.

### 51.29. Dùng một custom repository “universal search” trả Object[]

Mất type safety, business semantics và dễ lỗi index/casts.

### 51.30. Đổi property names entity mà không test derived queries

Parser có thể lỗi ở bootstrap/runtime.

### 51.31. Không test nhiều tenants/soft-deleted rows

Query thiếu authorization filter vẫn có thể pass trên fixture đơn giản.

### 51.32. Chỉ test một SQL count, không kiểm tra kết quả

Query trả thiếu children vẫn có vẻ “hiệu quả”.

### 51.33. Quên time zone/day boundary

Kết quả ngày có thể lệch ở các khu vực/precision khác.

### 51.34. Bắt exception và trả Optional.empty cho cả DB outage

Che sự cố hệ thống như resource not found.

### 51.35. Dựa vào H2 để chứng minh planner/locking của production DB

Behavior, collation, isolation và SQL plans có thể khác.

---

## 52. Quy trình thiết kế phương thức truy vấn từ đầu

### Bước 1 — Mô tả use case bằng câu hỏi nghiệp vụ

“Nhân viên xem 50 Order mới nhất mà tenant A được phép xem” cụ thể hơn “cần find orders”.

### Bước 2 — Xác định security scope

Tenant, ownership, role, soft delete và data retention visibility.

### Bước 3 — Liệt kê fields và associations cần dùng

Chỉ 5 scalar fields? Cần nested Lines? Cần managed entity để thay đổi?

### Bước 4 — Xác định cardinality

0–1, bounded many, unbounded export, aggregate scalar hoặc groups.

### Bước 5 — Xác định result shape

Optional, DTO List/Page/Slice, Stream, Map, aggregate DTO, managed entity.

### Bước 6 — Xác định filters

Required vs optional, null semantics, date boundaries, text search normalization.

### Bước 7 — Xác định ordering và paging

Sort keys, tie-breaker, page size cap, total count, cursor/offset.

### Bước 8 — Chọn query technique

Derived, JPQL @Query, Specification/Criteria, custom EntityManager hoặc native SQL theo độ phức tạp.

### Bước 9 — Chọn fetch plan

To-one join, EntityGraph, DTO joins, two-step paging/explicit children queries; tránh N+1 và collection explosions.

### Bước 10 — Xác định transaction/consistency

Read-only snapshot expectation, managed update, optimistic/pessimistic lock, bulk DML semantics.

### Bước 11 — Review database support

Indexes, constraints, query plan, count cost, data distribution.

### Bước 12 — Viết tests

Fixtures nhiều tenants/status/NULL/timestamp trùng; correctness, page, query count, concurrency.

### Bước 13 — Đo và điều chỉnh

Đo trên DB/schema/data representative; không tối ưu chỉ theo số statements.

### Bước 14 — Document method contract

Caller biết input validation, outputs, ordering, missing values, authorization, query cost assumptions.

---

## 53. Thực hành: chọn query contract cho tám tình huống

### Tình huống A — Trang admin 50 Orders

**Nhu cầu:** ID, createdAt, status, Customer displayName, total; filter tenant/status; page+total.

**Đề xuất:** `Page<OrderListRow> searchVisibleOrders(tenant,criteria,pageable)` với JPQL constructor projection, countQuery riêng và sort ổn định.

### Tình huống B — Detail Order có 8 Lines

**Nhu cầu:** Thông tin Order, Lines và Product names.

**Đề xuất:** `Optional<OrderDetailResponse> findVisibleDetail(tenant,id)`; một query Order+Customer, một query Lines+Products hoặc bounded EntityGraph. Không bắt mọi list query tải Lines.

### Tình huống C — Khách hàng có giỏ hàng đang mở

**Nhu cầu:** 0 hoặc 1 Cart active theo owner và tenant.

**Đề xuất:** `Optional<Cart> findActiveByOwnerAndTenant(owner,tenant)`; DB uniqueness policy phù hợp.

### Tình huống D — Badge số đơn đang chờ

**Nhu cầu:** Số lượng NEW.

**Đề xuất:** `long countVisibleByStatus(tenant,NEW)`, không load List<Order> rồi `size`.

### Tình huống E — “Load more” History

**Nhu cầu:** 30 Events tiếp theo, không cần total.

**Đề xuất:** `Slice<OrderEventRow> findAfter(tenant,cursor,limit)`, cursor với stable tie-breaker.

### Tình huống F — Export 200.000 rows

**Nhu cầu:** CSV flat rows, resume khi fail.

**Đề xuất:** `List<OrderExportRow> readExportChunk(tenant,cutoff,cursor,chunkSize)`; DTO/keyset và service quản lý checkpoint.

### Tình huống G — Hai workers cùng xử lý PAID Orders

**Nhu cầu:** Không xử lý trùng, transaction boundaries rõ.

**Đề xuất:** Repository claim/lock query theo DB/dialect hoặc state transition atomic + idempotency, không chỉ `findTop100ByStatus` rồi gọi service song song.

### Tình huống H — Báo cáo tổng doanh thu

**Nhu cầu:** Group theo currency, ngày và trạng thái finalized.

**Đề xuất:** Aggregate DTO query hoặc read model; không load Orders rồi sum trong JVM.

---

## 54. Bài tập thực hành có gợi ý

### Bài 1 — Từ findAll đến use case

Một bảng đơn hàng có 5 triệu rows. Vì sao `repository.findAll()` không phù hợp cho API list?

**Gợi ý:** Không có page/size bound, over-fetch và memory.

### Bài 2 — Đặt tên method

Đặt tên cho query “một active Order theo ID và authorized tenant”.

**Gợi ý:** `findByIdAndTenantIdAndDeletedAtIsNull`.

### Bài 3 — Result type

Một Order có thể không tồn tại. Kiểu nào phù hợp?

**Đáp án:** `Optional<SalesOrder>` hoặc một result type biểu diễn absence theo contract.

### Bài 4 — Kiểm tra tồn tại

Chỉ cần biết active Order có tồn tại. Có nên hydrate entity không?

**Gợi ý:** `existsBy...`.

### Bài 5 — Uniqueness

Method trả Optional nhưng query bằng customer.displayName không unique.

**Gợi ý:** Dùng List hoặc bổ sung unique predicate/constraint.

### Bài 6 — Page vs Slice

UI chỉ có “Load more”, không hiển thị tổng. Nên cân nhắc gì?

**Gợi ý:** Slice/cursor để tránh count.

### Bài 7 — Sort ổn định

Hai Orders có cùng createdAt.

**Gợi ý:** Thêm `id desc` tie-breaker.

### Bài 8 — Default order

Không có `ORDER BY`. Có đảm bảo rows theo ID tăng dần không?

**Đáp án:** Không.

### Bài 9 — DTO

List chỉ cần customerName. Dùng entity/DTO?

**Gợi ý:** DTO projection join to-one Customer.

### Bài 10 — JOIN vs JOIN FETCH

Trong JPQL constructor DTO, có cần `join fetch o.customer` không?

**Đáp án:** Không, dùng join để chọn scalar field.

### Bài 11 — EAGER

Bật EAGER trên mọi Customer để sửa một endpoint list có hợp lý không?

**Gợi ý:** Không, có thể over-fetch trên use cases khác.

### Bài 12 — Search động

15 optional filters, nhiều ranges. Derived name hay Specification?

**Gợi ý:** Specification/Criteria/custom query rõ predicates.

### Bài 13 — Required scope

User có thể truyền tenantId trong request. Repository nên tin trực tiếp?

**Đáp án:** Không, phải truyền authorized scope từ trusted context.

### Bài 14 — Soft delete

Main query có `deletedAt is null` nhưng countQuery quên.

**Gợi ý:** Page totals sai và lộ counts không được phép.

### Bài 15 — NULL criteria

`criteria.status() == null` có nghĩa gì?

**Gợi ý:** Phải document: thường là không lọc status.

### Bài 16 — Empty IN

`findByIds(List.of())` có nên sinh `IN ()` không?

**Gợi ý:** Trả empty result/handle riêng theo contract.

### Bài 17 — SQL injection

Client gửi `sort="createdAt; DROP TABLE ..."`.

**Gợi ý:** Allowlist fields và query APIs parameterized.

### Bài 18 — LIKE wildcard

User tìm literal `100%` nhưng query dùng `LIKE '%100%%'`.

**Gợi ý:** Escape %/_ và bind pattern.

### Bài 19 — Unicode casefolding

Lower() có luôn giống nhau giữa Java và DB không?

**Đáp án:** Không; collation/locale/Unicode khác.

### Bài 20 — Date range

Tìm “từ 01/11 đến hết 07/11” nên dùng interval nào?

**Gợi ý:** [start-of-01/11, start-of-08/11) theo business timezone.

### Bài 21 — OFFSET sâu

Trang 1 nhanh, trang 100000 chậm.

**Gợi ý:** Đo keyset/cursor + index.

### Bài 22 — Cursor security

Một cursor chứa ID của Order tenant khác có cấp quyền truy cập không?

**Đáp án:** Không; query vẫn scope theo authorized tenant.

### Bài 23 — Collection fetch pagination

Page<Order> cùng fetch join Lines có thể gặp gì?

**Gợi ý:** Root row multiplication, memory pagination/exception.

### Bài 24 — Two-step IDs

Bước đầu của two-step pagination lấy gì?

**Đáp án:** Root IDs theo filter/sort/page.

### Bài 25 — IN ordering

Query `where id in :ids` giữ thứ tự input IDs?

**Đáp án:** Không, reorder.

### Bài 26 — Nested Lines

Mỗi Order preview 3 Lines. `setMaxResults(3)` trên query WHERE order_id IN(:ids) có đúng per Order không?

**Đáp án:** Không; đó là top 3 toàn tập.

### Bài 27 — Aggregate

Muốn tổng doanh thu theo currency. Có nên cộng toàn bộ amounts trực tiếp không?

**Gợi ý:** Group by currency hoặc dùng policy conversion.

### Bài 28 — COUNT join

Order có 5 Lines, `count(o)` sau join Lines có thể đếm mấy lần?

**Gợi ý:** Có thể 5 rows cho Order đó; xem count distinct/EXISTS.

### Bài 29 — Exists race

Hai transactions cùng `exists=false` rồi insert. Có chắc không duplicate?

**Đáp án:** Không; cần DB UNIQUE constraint.

### Bài 30 — Write workflow

Ship Order cần dirty checking. DTO projection có phù hợp?

**Gợi ý:** Load managed entity trong transaction.

### Bài 31 — @Version

Một stale update của Order nên được phát hiện ra sao?

**Gợi ý:** Optimistic locking/version tại flush/commit.

### Bài 32 — @Lock

Có nên `PESSIMISTIC_WRITE` cho tất cả GET endpoints không?

**Đáp án:** Không; contention và locks.

### Bài 33 — Bulk update

JPQL bulk UPDATE có tự gọi `order.markShipped()`/entity callbacks cho từng row không?

**Đáp án:** Không.

### Bài 34 — Persistence context stale

Bulk UPDATE đã xong nhưng một managed Order vẫn có status cũ.

**Gợi ý:** Flush/clear/reload theo workflow.

### Bài 35 — Transaction

`@Transactional(readOnly=true)` có tự ngăn N+1 không?

**Đáp án:** Không.

### Bài 36 — Error handling

DB unavailable nhưng adapter trả Optional.empty.

**Gợi ý:** Sai; connection error khác not found.

### Bài 37 — N+1 regression

50 Orders và 50 distinct Customers, mapper gọi `getCustomer()`.

**Gợi ý:** Đếm SQL trên whole use case, thử projection/join.

### Bài 38 — Query index

Query lọc tenant+status+active, sort createdAt desc/id desc. Index nào đáng cân nhắc?

**Gợi ý:** Composite/partial index đúng predicates, xác nhận EXPLAIN.

### Bài 39 — Test tenant leakage

Fixture chỉ có một tenant; query thiếu tenant filter có bị phát hiện không?

**Gợi ý:** Không chắc; seed tenant B với dữ liệu cùng status/ID space thích hợp.

### Bài 40 — Test boundary

Hai Orders đúng thời điểm `createdToExclusive`. Có được chọn không?

**Đáp án:** Không, với predicate `createdAt < toExclusive`.

### Bài 41 — Query result order

`getResultList()` có thứ tự insert khi không ORDER BY không?

**Đáp án:** Không đảm bảo.

### Bài 42 — Sorting client

UI yêu cầu sort theo collection.productName. Vấn đề gì?

**Gợi ý:** Một Order có nhiều Lines; định nghĩa aggregate sort key trước.

### Bài 43 — Export lớn

Tại sao không dùng `List<SalesOrder> findAll` để export 500.000 rows?

**Gợi ý:** Memory, persistence context, N+1, transaction long-lived.

### Bài 44 — GraphQL resolver

N resolvers gọi repository.findById(Customer). Cách giảm N+1?

**Gợi ý:** Batch-by-IDs/DataLoader scoped theo tenant/request.

### Bài 45 — Custom repository

Khi nào cần custom EntityManager implementation?

**Gợi ý:** Dynamic projection, keyset, complex SQL/window functions, multi-step queries.

### Bài 46 — Method contract

`findReadyToShip` phải document những gì?

**Gợi ý:** Status rules, tenant, deleted, sort, max rows, lock/transaction expectation.

### Bài 47 — Soft-delete security

Method `findByIdAndTenantId` không lọc deleted; ai được gọi?

**Gợi ý:** Chỉ use case privileged/recovery theo authorization.

### Bài 48 — Query plan

Một query 1 SELECT nhưng trả 100.000 duplicated joined rows; query 3 SELECT trả 2.000 rows. Chọn theo metric gì?

**Gợi ý:** End-to-end latency, bytes, memory, correctness, DB CPU.

### Bài 49 — Query contract test

Một Page query trả content đúng nhưng totalElements sai. Cần kiểm gì?

**Gợi ý:** countQuery không cùng filters, joins/count distinct.

### Bài 50 — Tổng hợp

Thiết kế API repository cho list, detail, update, count, export Orders.

**Gợi ý:** Dùng 5 query contracts khác nhau về DTO/entity, cardinality, sorting, transaction/locks, pagination và authorization; không ép tất cả vào một `findAll`.

---

## 55. Checklist review trước khi merge repository method

- [ ] Tên method nói rõ nghiệp vụ hoặc data shape.
- [ ] Consumer/use case được xác định.
- [ ] Required scope (tenant/owner/permission) luôn được áp dụng.
- [ ] Soft-delete/archived visibility được định nghĩa.
- [ ] Result type phản ánh cardinality: Optional/List/Page/Slice/scalar.
- [ ] Query có giới hạn rows/page size phù hợp.
- [ ] Result shape chỉ chứa fields cần thiết.
- [ ] Không trả entity trực tiếp ra API mà không có DTO boundary.
- [ ] Với managed updates, query trả entity đúng transaction context.
- [ ] Optional filter/null/empty-list semantics được document.
- [ ] Date range có timezone và boundary chính xác.
- [ ] Search user input được bind và escape đúng.
- [ ] Dynamic sort field có allowlist.
- [ ] Có ORDER BY ổn định và tie-breaker cho pagination.
- [ ] Có countQuery tương đương filters nếu trả Page.
- [ ] Có tránh collection fetch join + pagination không kiểm soát.
- [ ] Mapper có tạo lazy-load N+1 không.
- [ ] Fetch plan theo đúng use case, không EAGER toàn cục.
- [ ] Query theo children dùng EXISTS/aggregate khi thích hợp.
- [ ] IN queries có limit và ordering reconstruction khi cần.
- [ ] Aggregate COUNT/SUM có xử lý duplicate/currency/null đúng.
- [ ] EXISTS không thay database uniqueness.
- [ ] Locking/optimistic version được cân nhắc cho write use case.
- [ ] Bulk DML không bị nhầm với managed entity changes.
- [ ] Transaction boundary/isolation rõ.
- [ ] Missing data khác DB failure.
- [ ] Exception/log không lộ SQL bind/user payload.
- [ ] DB indexes/constraints phù hợp query predicates.
- [ ] Có test dữ liệu nhiều tenants và soft-deleted records.
- [ ] Có test timestamp ties, boundaries và pagination ordering.
- [ ] Có test query output và count metadata đúng.
- [ ] Có test query count/N+1 trên dataset đủ lớn.
- [ ] Có test concurrency khi method phục vụ state transition.
- [ ] Query chạy trên provider/DB mục tiêu nếu dùng dialect-specific behavior.
- [ ] Có mô tả method contract cho future maintainers.

## 56. Bảng tra cứu nhanh

| Nếu yêu cầu là... | Hãy nghĩ tới... |
|---|---|
| “Tìm đúng một Order” | Optional + unique predicate + tenant |
| “Tìm Order đã xóa” | Privileged query rõ ràng |
| “Danh sách có tổng số” | Page DTO + countQuery |
| “Xem thêm” | Slice/cursor |
| “Top 20 mới nhất” | Bounded List + stable ORDER BY |
| “Tìm kiếm nhiều filters” | Specification/Criteria + typed criteria object |
| “Chỉ kiểm tra có/không” | exists query |
| “Chỉ đếm” | COUNT query |
| “Tổng hợp doanh thu” | Aggregate DTO/group theo currency |
| “Dùng Customer.name trên list” | DTO JOIN projection |
| “Sửa status Order” | Managed entity + transaction/version |
| “Trang Order kèm Lines” | Page IDs rồi fetch children |
| “Một Order detail có vài Lines” | Bounded fetch plan/explicit queries |
| “Hai to-many collections” | Split queries, tránh Cartesian explosion |
| “Sort động” | Allowlist + tie-breaker |
| “Sort theo field collection” | Aggregate business sort key |
| “Date from/to” | Half-open interval + business timezone |
| “Text search LIKE” | Bind + escape + normalize + index plan |
| “IN list rỗng” | Handle theo contract |
| “IN list rất lớn” | Chunk/alternative DB join strategy |
| “Lấy job để xử lý” | Lock/claim + transaction/idempotency |
| “Bulk update nhiều rows” | JPQL DML + persistence-context policy |
| “Export lớn” | Chunked DTO/keyset/stream |
| “GraphQL N+1” | Batch-by-IDs/DataLoader |
| “Query chạy chậm” | SQL count/plan/latency/data distribution |
| “Repository interface quá dài” | Tách read/write/analytics theo use case |
| “Query tests pass H2” | Kiểm tra dialect target/constraints |
| “Page total sai” | CountQuery filters/joins |
| “Người dùng thấy Order tenant khác” | Mandatory scope + security tests |

## 57. Tổng kết

1. **Repository method tốt bắt đầu từ use case**, không bắt đầu từ danh sách API CRUD sẵn có.
2. **Contract cần rõ dữ liệu trả về, cardinality, authorization scope, filters, sort, page và consistency**.
3. **Derived query** phù hợp simple lookups; **`@Query`** hữu ích với projection/joins/aggregates; **Criteria/Specification** phù hợp dynamic predicates; **custom repositories** cho query plans phức tạp.
4. **Optional, Page, Slice, List, Stream và scalar results** không hoán đổi nhau tùy ý; mỗi kiểu có cost/lifecycle/semantics riêng.
5. **DTO projection** phù hợp read-only lists; **managed entity** cần thiết khi domain write dùng dirty checking và optimistic locking.
6. **Tenancy, soft-delete và authorization phải xuyên suốt** list, detail, count, exists, export và related lookups.
7. **Pagination phải có stable sort/tie-breaker**; count query phải cùng filter semantics; to-many fetch join không phải mặc định an toàn cho Page.
8. **Search input phải có semantics rõ**: optional filters, null, dates, Unicode, LIKE wildcards, sort allowlist và giới hạn kích thước.
9. **N+1/over-fetch được giải quyết theo từng method** bằng DTO, fetch plans, batch hoặc bounded multi-query reads.
10. **Aggregate/EXISTS thuộc database**, không nên load hàng nghìn entities để tính counts hoặc kiểm tra điều kiện đơn giản.
11. **Bulk DML, locking và concurrency** cần contract riêng, không trộn lẫn với phương thức đọc dữ liệu.
12. **Repository không thay application service**, nơi điều phối transaction, business rules, authorization và external side effects.
13. **Tests phải xác minh data correctness và security**, bên cạnh SQL query count, page metadata, DB constraints, ordering và concurrent behavior.
14. **Giới hạn truy vấn và kiểm soát nguồn dữ liệu là một phần bảo vệ hệ thống**, không chỉ tối ưu performance.
15. **Thiết kế Repository tốt giúp thay SQL/provider mà không thay đổi ý định nghiệp vụ**, miễn adapter giữ nguyên hợp đồng và tests.

**Kết luận:** Thay vì gom mọi thao tác vào một `findAll()` hoặc viết repository methods chỉ theo tên cột, hãy đặt câu hỏi về mục tiêu của từng người dùng và workflow: *cần những bản ghi nào, thuộc phạm vi quyền nào, trả về hình dạng gì, với bao nhiêu dữ liệu và thứ tự nào?* Từ đó chọn derived query, JPQL, Criteria, projection, paging và transaction phù hợp. Những hợp đồng nhỏ, rõ nghĩa và được kiểm thử theo use case giúp repository vừa dễ bảo trì, vừa hạn chế N+1, lỗi phân trang, sự cố bảo mật và các thay đổi dữ liệu ngoài ý muốn.
