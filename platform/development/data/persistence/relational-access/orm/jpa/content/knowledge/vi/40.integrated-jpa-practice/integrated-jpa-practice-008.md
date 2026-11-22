# Trả DTO có phân trang mà không tải thừa đồ thị entity

Một API danh sách đơn hàng thường chỉ cần hiển thị **mã đơn, khách hàng, trạng thái, thời điểm tạo và tổng tiền**. Nhưng nếu lấy danh sách `PurchaseOrder` entities rồi để JSON serializer hoặc một vòng lặp mapping tự truy cập `order.getCustomer()`, `order.getLines()` và `line.getProduct()`, ứng dụng rất dễ sinh **N+1 queries**, nạp hàng nghìn objects không cần thiết và làm hỏng phân trang khi dùng `JOIN FETCH` một collection.

Mục tiêu của bài thực hành này là xây dựng một endpoint **trả về DTO có phân trang thực sự ở database**, không kéo theo toàn bộ entity graph:

```http
GET /api/orders?status=SUBMITTED&page=0&size=20
Authorization: Bearer <token>
```

Response minh họa:

```json
{
  "items": [
    {
      "id": 801,
      "orderNumber": "SO-2026-0801",
      "customerName": "Công ty Minh An",
      "status": "SUBMITTED",
      "createdAt": "2026-11-10T08:30:00Z",
      "totalAmount": 1250000.00
    },
    {
      "id": 799,
      "orderNumber": "SO-2026-0799",
      "customerName": "Cửa hàng Hòa Bình",
      "status": "SUBMITTED",
      "createdAt": "2026-11-09T14:10:00Z",
      "totalAmount": 850000.00
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 137,
  "totalPages": 7,
  "hasNext": true
}
```

Đây là dữ liệu ví dụ; số lượng và giá trị không đến từ database thực tế.

Ta sẽ đi từ một triển khai sai đến JPQL constructor projection, Spring Data JPA `Page`/`Slice`, xử lý quan hệ một-nhiều bằng truy vấn hai bước, tổng hợp dữ liệu, phân trang bằng cursor, kiểm thử số SQL và các ràng buộc bảo mật.

> **Nguyên tắc cốt lõi:** Với endpoint đọc danh sách, hãy **chọn đúng cột, đúng số dòng và đúng quan hệ mà giao diện cần**, thay vì tải managed entities rồi cắt bớt dữ liệu trong Java. Phân trang phải áp dụng trên **bản ghi gốc (root rows)** trước khi mở rộng collection.

Bài thuộc chương **Thực hành tổng hợp** của module **Data Persistence Relational Access ORM JPA**. Các ví dụ sử dụng Jakarta Persistence, JPQL, Java records, Spring Data JPA và PostgreSQL khi cần kiểm thử; những phần provider-specific như cấu hình Hibernate được chỉ rõ.

---

## 1. Bài toán và tiêu chí hoàn thành

Giả sử hệ thống bán hàng có ba loại dữ liệu:

```text
Customer
  id, tenantId, name, email, phone, address, ...
      |
      | 1
      v
PurchaseOrder
  id, tenantId, orderNumber,
  status, createdAt, totalAmount, version, ...
      |
      | 1
      v
OrderLine (*)
  id, orderId, productId, quantity,
  unitPrice, discount, ...
      |
      v
Product
  id, sku, name, description, images, ...
```

Mỗi đơn hàng có một khách hàng và có thể có nhiều dòng hàng. Một customer có thể có rất nhiều orders. Một product có thể có nhiều thông tin mô tả, hình ảnh và thuộc tính.

**Màn hình danh sách** chỉ cần:

| Trường DTO | Nguồn dữ liệu | Cần tải toàn entity? |
| --- | --- | --- |
| `id` | `PurchaseOrder.id` | Không |
| `orderNumber` | `PurchaseOrder.orderNumber` | Không |
| `customerName` | `Customer.name` | Không |
| `status` | `PurchaseOrder.status` | Không |
| `createdAt` | `PurchaseOrder.createdAt` | Không |
| `totalAmount` | `PurchaseOrder.totalAmount` | Không |
| `totalElements` | `COUNT` query | Không |

Không cần tải `Customer.email`, `Customer.address`, `OrderLine` hay `Product` cho danh sách cơ bản.

### 1.1. Các tiêu chí kỹ thuật

1. Database giới hạn đúng `size` root orders mỗi trang.
2. Query không phát sinh N+1 khi page size tăng.
3. Trả DTO với tập fields ổn định; không serialize entity/proxy.
4. Lọc dữ liệu theo tenant đã được xác thực.
5. Sort có thứ tự ổn định, không chỉ dựa một cột có thể trùng.
6. `totalElements` và nội dung trang dùng cùng điều kiện lọc.
7. Không sử dụng collection fetch join trực tiếp trên pageable query.
8. Pagination không phụ thuộc việc giữ `EntityManager` mở tới lúc serialize JSON.
9. Với trang rỗng, xử lý kết quả đúng và tránh query `IN ()` bất hợp lệ.
10. Có tests xác nhận kết quả và số SQL không tăng tuyến tính theo số phần tử.

### 1.2. Cần phân biệt hai yêu cầu

**Danh sách đơn giản**: tổng tiền đã được lưu trong `PurchaseOrder.totalAmount`, nên chỉ cần query DTO và query COUNT.

**Danh sách cần dữ liệu tổng hợp từ lines**: ví dụ số dòng hàng hoặc số lượng sản phẩm; phải bổ sung aggregate query cho **chính những order IDs nằm trong trang**, không fetch tất cả lines của mọi đơn trước khi chia trang.

Ta sẽ giải quyết cả hai trường hợp.

## 2. Mapping entity minh họa

Các class sau trình bày những phần liên quan đến bài thực hành. Trong dự án thật còn cần constructors, domain methods, validation và migrations tương ứng.

### 2.1. Customer

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "name", nullable = false)
    private String name;

    protected Customer() {}

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

### 2.2. PurchaseOrder

```java
package com.example.shop.domain;

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
    private String tenantId;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(
        name = "total_amount",
        nullable = false,
        precision = 18,
        scale = 2
    )
    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private Long version;

    protected PurchaseOrder() {}

    // Domain constructors and methods belong here.
}
```

### 2.3. OrderLine

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(
        name = "unit_price",
        nullable = false,
        precision = 18,
        scale = 2
    )
    private BigDecimal unitPrice;

    protected OrderLine() {}
}
```

`OrderStatus` là enum nghiệp vụ, ví dụ:

```java
public enum OrderStatus {
    DRAFT,
    SUBMITTED,
    APPROVED,
    CANCELLED
}
```

### 2.4. Vì sao quan hệ nên để LAZY?

`@ManyToOne` mặc định thường là EAGER theo đặc tả JPA; ta chọn rõ `fetch = FetchType.LAZY` để không áp dụng eager fetching cho mọi use case. `@OneToMany` mặc định LAZY, nhưng ta cũng khai báo rõ để diễn đạt chủ đích.

**Lưu ý:** LAZY không phải cam kết provider luôn chỉ dùng proxy hay luôn tránh mọi secondary SQL. Query, enhancement, provider và cách truy cập entity vẫn quyết định SQL thực tế. LAZY là một cơ chế để không mặc định tải đồ thị lớn, không phải giải pháp cho mọi N+1.

### 2.5. Vì sao không đặt EAGER cho toàn bộ associations?

Nếu entity dùng chung cho màn hình danh sách, màn hình chi tiết, job báo cáo và transaction ghi, EAGER toàn cục có thể kéo thông tin không cần thiết tới mọi nơi, hoặc khiến provider sinh secondary selects.

**Fetch plan nên phụ thuộc use case**, không phụ thuộc mong muốn tránh một lazy-loading exception ở lớp API.

## 3. Thiết kế DTO là hợp đồng API

Ta dùng Java record:

```java
package com.example.shop.api;

import com.example.shop.domain.OrderStatus;
import java.math.BigDecimal;
import java.time.Instant;

public record OrderListItem(
    Long id,
    String orderNumber,
    String customerName,
    OrderStatus status,
    Instant createdAt,
    BigDecimal totalAmount
) {}
```

### 3.1. Vì sao DTO không chứa entity?

Sai:

```java
public record OrderListItem(
    Long id,
    Customer customer,
    List<OrderLine> lines
) {}
```

Dù tên class là DTO, nó vẫn có thể kéo theo JPA managed entities, lazy proxies và serialization side effects.

Đúng hơn là các trường scalar hoặc value objects được chọn có chủ đích.

### 3.2. Có thể dùng nested DTO không?

Có, ví dụ `CustomerSnippet(Long id, String name)`. Nhưng nếu yêu cầu chỉ hiển thị tên khách hàng, một scalar field thường đơn giản hơn.

### 3.3. Entity khác DTO về lifecycle

Entity managed có persistence identity, dirty checking, lazy loading, cascade, versioning. DTO chỉ mang dữ liệu cho use case. DTO trả từ một constructor projection **không phải managed PurchaseOrder hoặc Customer**.

Điều này giúp giảm chi phí materialization và loại bỏ rủi ro serializer vô tình kích hoạt LAZY loading.

### 3.4. Tổng tiền nên lấy từ đâu?

Ở ví dụ chính, `totalAmount` được lưu trên Order và được cập nhật nhất quán theo domain workflow. Đây là một **denormalized value có chủ đích**. Nếu business luôn phải tính từ OrderLines mới nhất, cần query aggregate hoặc consistency strategy khác — không mặc định tin tổng tiền lưu sẵn.

## 4. Anti-pattern: tải entity rồi map trong Java

Một triển khai ban đầu:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    PurchaseOrder.class
)
.setParameter("tenantId", trustedTenantId)
.setFirstResult(page * size)
.setMaxResults(size)
.getResultList();

List<OrderListItem> result = orders.stream()
    .map(o -> new OrderListItem(
        o.getId(),
        o.getOrderNumber(),
        o.getCustomer().getName(),
        o.getStatus(),
        o.getCreatedAt(),
        o.getTotalAmount()
    ))
    .toList();
```

Đoạn trên cần entity getters và một transaction/context còn hoạt động để đọc LAZY relationships.

### 4.1. Vì sao xuất hiện N+1?

Giả sử có 20 orders thuộc 20 khách hàng khác nhau và L1/L2 cache lạnh.

```text
1 SELECT purchase_orders (20 orders)
    +
20 SELECT customers WHERE id = ?
    =
21 SELECTs (minh họa)
```

Đây là một khả năng phổ biến, không phải số SQL cố định trong mọi provider. Nếu nhiều Orders dùng chung Customer, hoặc cache chứa Customer, số SELECT có thể thấp hơn. Nhưng pattern vẫn nguy hiểm khi số distinct target entities tăng.

### 4.2. Nếu mapper còn truy cập lines?

```java
o.getLines().size()
```

Có thể kích hoạt thêm collection SELECTs. Nếu còn lặp `line.getProduct()`, số SQL có thể tăng tiếp.

### 4.3. Bẫy Open Session in View

Nếu Spring Boot giữ persistence context mở tới serialization layer, việc trả entity trực tiếp có thể “chạy được” vì serializer nạp associations sau service. Đây không phải giải pháp hiệu năng; SQL trở nên khó kiểm soát và phụ thuộc JSON graph.

### 4.4. Bẫy `@Transactional(readOnly=true)`

Read-only transaction không biến entity query thành projection. Nó có thể điều chỉnh một số hành vi transaction/ORM tùy framework/provider, nhưng không tự bỏ các cột hay associations thừa.

### 4.5. Bẫy cắt trang trong Java

Sai:

```java
List<PurchaseOrder> all = repository.findAll();

List<PurchaseOrder> pageItems =
    all.subList(from, to);
```

Database vẫn trả tất cả rows và provider có thể hydrate rất nhiều managed entities trước khi Java cắt danh sách.

## 5. Hướng chính: JPQL constructor projection

JPQL hỗ trợ `SELECT NEW` để tạo DTO trực tiếp từ các expressions trong query.

```java
List<OrderListItem> rows = em.createQuery(
    """
    SELECT new com.example.shop.api.OrderListItem(
        o.id,
        o.orderNumber,
        c.name,
        o.status,
        o.createdAt,
        o.totalAmount
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.tenantId = :tenantId
      AND o.status = :status
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    OrderListItem.class
)
.setParameter("tenantId", trustedTenantId)
.setParameter("status", OrderStatus.SUBMITTED)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

### 5.1. Những gì được lấy?

Chỉ các expressions trong constructor projection: sáu cột logic dùng tạo DTO.

Trong đa số tình huống, provider không cần hydrate `PurchaseOrder`, `Customer` hoặc `OrderLine` thành managed entities chỉ để tạo các scalar DTO đó.

### 5.2. Vì sao dùng JOIN thay JOIN FETCH?

`JOIN o.customer c` cho phép lấy `c.name` như một scalar trong projection.

`JOIN FETCH` có mục tiêu nạp association của **entity owner** vào persistence context; khi chỉ trả DTO, không cần yêu cầu fetch cả Customer entity.

### 5.3. Tên class phải đầy đủ

JPQL constructor expression dùng tên class đầy đủ:

```jpql
new com.example.shop.api.OrderListItem(...)
```

Constructor (với record là canonical constructor) phải khớp số lượng/thứ tự/kiểu đối số.

### 5.4. Số SQL

Với danh sách cơ bản, query trên thường được provider chuyển thành một SELECT có JOIN và pagination. Điều này không bảo đảm mọi execution plan giống nhau giữa các DBMS, nhưng thiết kế không có đường truy cập Customer LAZY sau khi query đã trả DTO.

### 5.5. Một lỗi rất hay gặp

Không làm:

```java
SELECT o, c.name
FROM PurchaseOrder o
JOIN o.customer c
```

rồi gọi kết quả là “không tải entity”, vì `o` trong select list vẫn là một entity result. Nếu chỉ cần id và number, chọn `o.id` và `o.orderNumber`.

## 6. Phân trang phải có thứ tự ổn định

Một query phân trang không có `ORDER BY` thường không đảm bảo page boundaries ổn định.

### 6.1. Chỉ sort theo createdAt chưa đủ

Hai orders có thể được tạo trong cùng millisecond:

```text
Order#801 createdAt=2026-11-10T08:30:00Z
Order#802 createdAt=2026-11-10T08:30:00Z
```

Nếu query chỉ:

```jpql
ORDER BY o.createdAt DESC
```

thứ tự giữa các rows có cùng timestamp không được xác định hoàn toàn.

### 6.2. Dùng tie-breaker có tính duy nhất

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

`id` giúp xác định thứ tự cho hai Orders cùng `createdAt`.

### 6.3. Thứ tự ổn định không ngăn dữ liệu thay đổi đồng thời

Một row mới được INSERT trước khi client lấy page 2 có thể đẩy offset của các rows cũ sang trang khác. Tie-breaker giúp deterministic ordering trong cùng trạng thái dữ liệu, **không cung cấp snapshot xuyên nhiều HTTP requests**.

### 6.4. Sort phải phù hợp index và use case

Sort mặc định thường đặt theo `createdAt DESC, id DESC`; nếu business yêu cầu order khác, repository phải có strategy và index phù hợp, không thêm bất kỳ raw sort expression nào từ client.

## 7. Count query: phần bắt buộc khi trả Page có tổng

Một `Page` đầy đủ có thể cần `totalElements`, `totalPages` và `hasNext`.

Count:

```java
Long total = em.createQuery(
    """
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
      AND o.status = :status
    """,
    Long.class
)
.setParameter("tenantId", trustedTenantId)
.setParameter("status", OrderStatus.SUBMITTED)
.getSingleResult();
```

### 7.1. Không dùng FETCH JOIN trong count query

Sai về ý đồ:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN FETCH o.customer
```

Fetch join dùng để tải association của selected entity owner, không phải tính row count. Một provider có thể từ chối hoặc xử lý không đúng ý.

### 7.2. Count phải có cùng predicates

Nếu content query lọc:

```jpql
WHERE o.tenantId = :tenantId
  AND o.status = :status
```

mà count chỉ lọc `status`, response có thể tiết lộ tổng đơn của các tenants khác và pagination metadata bị sai.

### 7.3. COUNT khác số dòng sau JOIN to-many

Ví dụ:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.product.id = :productId
```

Nếu mỗi Order có nhiều matching lines, `COUNT(o)` có thể đếm một Order nhiều lần. Khi điều kiện cần số Orders duy nhất, cân nhắc `COUNT(DISTINCT o.id)` hoặc `EXISTS` theo semantics và JPQL provider support.

### 7.4. COUNT có thể đắt

Với bảng rất lớn và nhiều filters, COUNT đôi khi chiếm phần đáng kể latency. Nếu giao diện chỉ cần nút “Trang tiếp theo”, có thể trả **Slice** thay vì Page và bỏ query COUNT.

### 7.5. COUNT và content có thể không cùng snapshot

Ở isolation như `READ COMMITTED`, hai SELECT trong cùng transaction vẫn có thể quan sát trạng thái committed khác nhau nếu writers đồng thời thay đổi dữ liệu. Nếu nghiệp vụ cần snapshot consistency nghiêm ngặt, phải thiết kế transaction/isolation hoặc cursor snapshot policy tương ứng.

## 8. Triển khai repository JPA thuần: DTO và count

Một phiên bản đầy đủ của page result không phụ thuộc Spring Data:

```java
package com.example.shop.api;

import java.util.List;

public record OrderPageResponse(
    List<OrderListItem> items,
    int page,
    int size,
    long totalElements,
    long totalPages,
    boolean hasNext
) {
    public OrderPageResponse {
        items = List.copyOf(items);
    }
}
```

Repository:

```java
package com.example.shop.persistence;

import com.example.shop.api.OrderListItem;
import com.example.shop.api.OrderPageResponse;
import com.example.shop.domain.OrderStatus;
import jakarta.persistence.EntityManager;

import java.util.List;

public class OrderListQuery {

    private final EntityManager em;

    public OrderListQuery(EntityManager em) {
        this.em = em;
    }

    public OrderPageResponse findPage(
            String trustedTenantId,
            OrderStatus status,
            int page,
            int size) {

        if (trustedTenantId == null ||
            trustedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Trusted tenant is required"
            );
        }

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                "Invalid page or size"
            );
        }

        long offset = (long) page * size;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Page offset is too large"
            );
        }

        // Query structure is built from trusted code,
        // not from untrusted input.
        String statusPredicate =
            status == null ? "" : " AND o.status = :status";

        String contentJpql = """
            SELECT new com.example.shop.api.OrderListItem(
                o.id,
                o.orderNumber,
                c.name,
                o.status,
                o.createdAt,
                o.totalAmount
            )
            FROM PurchaseOrder o
            JOIN o.customer c
            WHERE o.tenantId = :tenantId
            """
            + statusPredicate
            + " ORDER BY o.createdAt DESC, o.id DESC";

        var contentQuery = em.createQuery(
            contentJpql,
            OrderListItem.class
        );

        contentQuery.setParameter(
            "tenantId",
            trustedTenantId
        );

        if (status != null) {
            contentQuery.setParameter("status", status);
        }

        List<OrderListItem> items = contentQuery
            .setFirstResult((int) offset)
            .setMaxResults(size)
            .getResultList();

        String countJpql = """
            SELECT COUNT(o)
            FROM PurchaseOrder o
            WHERE o.tenantId = :tenantId
            """
            + statusPredicate;

        var countQuery = em.createQuery(
            countJpql,
            Long.class
        );
        countQuery.setParameter(
            "tenantId",
            trustedTenantId
        );

        if (status != null) {
            countQuery.setParameter("status", status);
        }

        long total = countQuery.getSingleResult();

        long totalPages = total == 0
            ? 0
            : 1 + (total - 1) / size;

        boolean hasNext =
            offset + items.size() < total;

        return new OrderPageResponse(
            items,
            page,
            size,
            total,
            totalPages,
            hasNext
        );
    }
}
```

### 8.1. Những quyết định trong code

- `tenantId` đến từ nguồn tin cậy.
- `page` và `size` được chặn giới hạn.
- Offset dùng `long` để tính trước, sau đó mới cast sang `int` cho JPA `setFirstResult`.
- Query string chỉ nối một predicate cố định do code chọn; không nối raw input từ request.
- Constructor projection không trả entities.
- Page order có tie-breaker `id`.
- Count dùng cùng status predicate.
- Tổng số trang tính bằng số học nguyên, không cần chuyển sang floating point.
- DTO list được copy bất biến ở response boundary.

### 8.2. Vì sao không tính total bằng items.size()?

`items.size()` chỉ là số kết quả của **trang hiện tại**, không phải tổng rows thỏa filter.

### 8.3. Vì sao không truyền toàn bộ request sort vào JPQL?

Giá trị sort từ client là input không tin cậy; cần allowlist field names và directions. Bind parameter không thể thay cho một tên cột trong ORDER BY.

### 8.4. Khi page vượt quá cuối danh sách

Content query có thể trả `[]` nhưng count vẫn cho biết `totalElements`. Đây là một response hợp lệ; một API có thể chọn trả empty page hoặc một HTTP status khác theo contract.

### 8.5. Khi COUNT quá lớn

`COUNT` trả `Long` ở JPA. Trong API contract ta dùng `long` thay vì `int` để tránh tràn số với dataset lớn.

## 9. Đặt transaction và authorization đúng tầng

Một service:

```java
@Service
public class ListOrdersService {

    private final OrderListRepository repository;
    private final CurrentActor currentActor;

    public ListOrdersService(
            OrderListRepository repository,
            CurrentActor currentActor) {
        this.repository = repository;
        this.currentActor = currentActor;
    }

    @Transactional(readOnly = true)
    public OrderPageResponse list(
            OrderStatus status,
            int page,
            int size) {

        Actor actor = currentActor.requireAuthenticated();
        String tenantId = actor.trustedTenantId();

        return repository.findPage(
            tenantId, status, page, size
        );
    }
}
```

`OrderListRepository` và `CurrentActor` là các interfaces/ports minh họa; adapter có thể gọi `OrderListQuery` ở phần trước.

### 9.1. Tenant ID từ đâu?

Không dùng:

```java
repository.findPage(request.tenantId(), ...);
```

nếu client có thể thay tenant tùy ý. Tenant phải được xác định từ authentication/session/membership đã được kiểm tra theo security policy.

### 9.2. Tenant filter không thay mọi phân quyền

Một user thuộc tenant A chưa chắc được xem mọi Order của tenant A. Nếu quyền dựa trên owner/team/department, query cần thêm scope tương ứng.

### 9.3. readOnly không đồng nghĩa có một snapshot duy nhất

`@Transactional(readOnly = true)` của Spring thường là một hint đến transaction manager/provider. Nó không tự đảm bảo snapshot giống nhau qua COUNT và content ở mọi DB isolation.

### 9.4. Vì sao không return entity qua controller?

DTO đã được tạo trong transaction và không chứa LAZY proxies, nên serialization ngoài transaction không phát sinh SQL mới hoặc `LazyInitializationException` do đọc associations của entity.

## 10. Spring Data JPA: Page<DTO> từ repository

Nếu dự án dùng Spring Data JPA, có thể viết interface:

```java
package com.example.shop.persistence;

import com.example.shop.api.OrderListItem;
import com.example.shop.domain.OrderStatus;
import com.example.shop.domain.PurchaseOrder;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            SELECT new com.example.shop.api.OrderListItem(
                o.id,
                o.orderNumber,
                c.name,
                o.status,
                o.createdAt,
                o.totalAmount
            )
            FROM PurchaseOrder o
            JOIN o.customer c
            WHERE o.tenantId = :tenantId
              AND o.status = :status
            """,
        countQuery = """
            SELECT COUNT(o)
            FROM PurchaseOrder o
            WHERE o.tenantId = :tenantId
              AND o.status = :status
            """
    )
    Page<OrderListItem> findSummaries(
        @Param("tenantId") String trustedTenantId,
        @Param("status") OrderStatus status,
        Pageable pageable
    );
}
```

### 10.1. Vai trò của Pageable

`Pageable` mang page number, page size và sort. Spring Data có thể thêm pagination/sort vào query theo cơ chế của version đang chạy.

### 10.2. Dùng PageRequest có sort ổn định

```java
Pageable pageable = PageRequest.of(
    page,
    size,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<OrderListItem> result =
    repository.findSummaries(
        trustedTenantId,
        OrderStatus.SUBMITTED,
        pageable
    );
```

Các property names trong `Sort` phải là entity/query properties được hỗ trợ. Khi dùng projection/joins/phức tạp hơn, kiểm tra SQL/order expressions thực tế với Spring Data JPA version đích.

### 10.3. Vì sao khai báo countQuery riêng?

Vì count của một projection có JOIN, DISTINCT hoặc GROUP BY phức tạp không nên được giả định là có thể sinh đúng tự động. Count query riêng thể hiện rõ semantics và tránh fetch join trong count path.

### 10.4. Page có chắc luôn chạy đúng hai SQL không?

Không. Spring Data có thể áp dụng các tối ưu cho count query ở một số trường hợp. Số SQL còn phụ thuộc provider, transaction/cache và code ngoài query. Trong test, đừng hard-code “luôn đúng hai” khi framework có quyền bỏ count query nếu đã biết tổng từ một trang chưa đầy.

### 10.5. Không trả Page thẳng ra public API nếu cần contract ổn định

JSON serialization của `PageImpl` có thể thay đổi theo Spring Data version/cấu hình. Với public API cần ổn định, map `Page<OrderListItem>` sang một response DTO tự định nghĩa.

```java
OrderPageResponse response = new OrderPageResponse(
    result.getContent(),
    result.getNumber(),
    result.getSize(),
    result.getTotalElements(),
    result.getTotalPages(),
    result.hasNext()
);
```

`Page.getTotalPages()` trả `int`; khi dùng custom response với `long totalPages`, Java sẽ chuyển từ `int` lên `long`. Với datasets ngoài giới hạn tính toán framework, phải xác định API contract thích hợp.

## 11. Không để Sort từ client trở thành JPQL tùy ý

Một HTTP request có thể gửi:

```http
GET /api/orders?sort=customerName,desc
```

Nhưng không nên lấy string chưa kiểm soát rồi nối thẳng:

```java
String jpql =
    "SELECT ... ORDER BY " + rawSortFromRequest;
```

### 11.1. Allowlist

Ví dụ thiết kế input:

```java
public enum OrderSortKey {
    CREATED_AT,
    ORDER_NUMBER,
    TOTAL_AMOUNT
}
```

Mapping:

```java
String expression = switch (key) {
    case CREATED_AT -> "o.createdAt";
    case ORDER_NUMBER -> "o.orderNumber";
    case TOTAL_AMOUNT -> "o.totalAmount";
};
```

Dùng direction được parse thành enum `ASC`/`DESC` hoặc boolean, không đưa raw SQL fragment từ client vào query.

### 11.2. Query parameter không thay tên cột

```jpql
ORDER BY :sortField
```

`:sortField` đại diện một giá trị, không phải identifier. Đây không phải cách hợp lệ để dynamic sort theo một field.

### 11.3. Tie-breaker luôn được thêm

Nếu client sort theo `totalAmount DESC`, nên thêm `o.id DESC` (hoặc một unique tie-breaker phù hợp) để pagination deterministically ordered.

### 11.4. Sort qua relation có thể tạo JOIN

Sort theo `customer.name` có thể làm query phức tạp hơn và thay execution plan. Khi có optional relation, inner join/left join semantics cũng ảnh hưởng số root orders được giữ lại.

## 12. Quan hệ to-one: JOIN lấy scalar thay vì nạp Customer

Trong bài toán chính, `PurchaseOrder.customer` là `@ManyToOne`.

```jpql
SELECT new com.example.shop.api.OrderListItem(
    o.id, o.orderNumber, c.name,
    o.status, o.createdAt, o.totalAmount
)
FROM PurchaseOrder o
JOIN o.customer c
```

### 12.1. Vì sao JOIN thường không nhân số root rows ở to-one?

Mỗi Order trỏ một Customer; thông thường JOIN từ Order sang đúng một Customer không làm nhân bản Orders như to-many. Vì vậy nó tương đối phù hợp khi phân trang roots.

Tuy nhiên vẫn phải xét dữ liệu, join conditions, multi-tenancy và relationship cardinality thực.

### 12.2. LEFT JOIN khi Customer optional

Nếu business cho phép `customer` null:

```jpql
FROM PurchaseOrder o
LEFT JOIN o.customer c
```

thì `c.name` sẽ null khi không có Customer. Inner join sẽ loại Orders thiếu Customer khỏi result. Count query cũng phải có semantics phù hợp.

### 12.3. Không chọn toàn bộ Customer rồi chỉ dùng tên

`SELECT o, c` hoặc entity graph fetch Customer làm nhiều dữ liệu được hydrate hơn khi endpoint chỉ cần `c.name`.

### 12.4. JOIN không tự thay authorization

Nếu ứng dụng multi-tenant, vẫn cần predicates tenant/permission; FK tồn tại không đồng nghĩa mọi Customer được phép hiển thị.

## 13. Quan hệ to-many là vấn đề khó hơn

Giả sử một Order có 10 OrderLines. Nếu JOIN:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
ORDER BY o.id
```

root Order có thể xuất hiện thành nhiều result rows ở mức relational query.

### 13.1. Row multiplication

```text
Order A:  4 lines
Order B: 12 lines
Order C:  1 line

Relational JOIN:
  A A A A
  B B B B B B B B B B B B
  C

17 SQL rows
chỉ có 3 distinct Orders
```

Nếu áp LIMIT 10 trực tiếp vào SQL rows, ta không có 10 distinct Orders. Nó có thể cắt giữa các lines của Order B.

### 13.2. To-many JOIN FETCH với pagination

Một query rất dễ gây sự cố:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    PurchaseOrder.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

JPA không cung cấp bảo đảm portable rằng collection fetch join có thể được phân trang root entities đúng theo cách mong muốn. Provider có thể cảnh báo, phân trang trong memory, từ chối query hoặc dùng chiến lược khác.

### 13.3. Vì sao DISTINCT không đủ?

`DISTINCT` trên JPA result không tự loại chi phí nhân SQL rows do collection JOIN. SQL vẫn có thể trả một lượng dữ liệu lớn trước khi provider khử trùng entity results.

### 13.4. Nguy cơ về bộ nhớ

Nếu lấy 20 Orders nhưng mỗi Order có 500 Lines, physical result có thể rất lớn; khi provider phải áp pagination trong Java, nó có thể tải nhiều Orders/Lines hơn đáng kể so với số cần hiển thị.

### 13.5. Cấu hình fail-fast của Hibernate

Hibernate có setting:

```properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Những phiên bản Hibernate hỗ trợ setting này có thể ném lỗi khi phát hiện collection fetch join kết hợp limit/offset không phù hợp, thay vì âm thầm pagination trong memory.

Đây là **Hibernate-specific configuration**, không phải JPA standard. Nó giúp phát hiện anti-pattern, không làm query sai thành đúng.

## 14. Cách xử lý to-many: page roots trước, tải dữ liệu phụ sau

Khi DTO cần thêm thông tin từ OrderLines, dùng một chiến lược nhiều bước:

```text
Filter and order PurchaseOrders
              |
              v
Page root Order IDs (LIMIT/OFFSET)
              |
              v
Read page-level DTO basics by IDs
              |
              v
Aggregate only OrderLines of page IDs
              |
              v
Assemble DTOs in original page order
              |
              v
Return Page/Response
```

Ý tưởng: **không nhân root rows trước khi áp phân trang**.

### 14.1. Ba câu SQL logic

- Query A: lấy `20 Order IDs` theo filter và sort.
- Query B: lấy các fields của đúng 20 Orders.
- Query C: aggregate `OrderLines` có `order_id IN :pageIds`.
- Query COUNT nếu client thật sự cần tổng elements.

Số SQL thường là một hằng số nhỏ theo page, thay vì `1 + N`, nhưng thời gian còn phụ thuộc số lines/data/indexes.

### 14.2. Không nên dùng hai bước khi chưa cần

Nếu màn hình chỉ cần các cột sẵn trên Order và Customer, **một constructor projection trực tiếp** là đơn giản hơn. Dùng nhiều bước khi có nhu cầu tổng hợp/to-many/sort shape khiến query một bước không phù hợp.

## 15. Thực hành hai bước: page IDs

Query IDs:

```java
List<Long> pageIds = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
      AND o.status = :status
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    Long.class
)
.setParameter("tenantId", trustedTenantId)
.setParameter("status", OrderStatus.SUBMITTED)
.setFirstResult(page * size)
.setMaxResults(size)
.getResultList();
```

Trước khi nhân `page * size` trong code production cần validate range và tránh integer overflow như ở repository mẫu.

### 15.1. Trang rỗng

```java
if (pageIds.isEmpty()) {
    // Return empty content and count metadata
    // according to the pagination contract.
}
```

Đặc biệt không thực thi:

```jpql
WHERE o.id IN :ids
```

với list rỗng nếu provider/DBMS có thể tạo `IN ()` không hợp lệ. Return sớm và xác định COUNT có cần chạy hay không.

### 15.2. Query IDs chỉ phải làm một việc

Nó áp điều kiện lọc và sort để lấy root Orders. Đừng `JOIN FETCH o.lines` trong query ID page.

### 15.3. Index phù hợp

Với query lọc `tenant_id` và `status`, sắp `created_at DESC, id DESC`, một index phù hợp có thể giúp DB tìm nhanh page IDs. Không tạo index tùy tiện trước khi đo execution plan.

### 15.4. Tenant condition vẫn cần ở bước 2

Dù `pageIds` đến từ query đã lọc, lệnh đọc chi tiết nên giữ tenant predicate như defense in depth; không dùng `id` bất kỳ do client gửi mà bỏ scope.

## 16. Tải các fields của đúng những IDs trong trang

```java
List<OrderListItem> details = em.createQuery(
    """
    SELECT new com.example.shop.api.OrderListItem(
        o.id,
        o.orderNumber,
        c.name,
        o.status,
        o.createdAt,
        o.totalAmount
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.tenantId = :tenantId
      AND o.id IN :pageIds
    """,
    OrderListItem.class
)
.setParameter("tenantId", trustedTenantId)
.setParameter("pageIds", pageIds)
.getResultList();
```

### 16.1. IN không bảo đảm thứ tự

Một query `WHERE o.id IN :pageIds` **không tự trả rows theo thứ tự của list pageIds**. Nếu làm:

```java
return details;
```

có thể gây thứ tự DTO sai so với page query.

### 16.2. Khôi phục thứ tự từ pageIds

```java
Map<Long, OrderListItem> byId =
    details.stream().collect(
        Collectors.toMap(
            OrderListItem::id,
            Function.identity()
        )
    );

List<OrderListItem> ordered = pageIds.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
```

Đoạn code cần imports `Map`, `Collectors`, `Function` và `Objects`. Với application có policy nhất quán nghiêm ngặt, một ID biến mất giữa hai queries không nên bị lặng lẽ lọc; cần xử lý theo transaction/snapshot semantics, ví dụ phát hiện mismatch và retry/fail theo contract.

### 16.3. Nếu có hai DTO cho cùng ID?

Query to-one không nên tạo nhiều DTO cho cùng Order nếu mapping/cardinality đúng. Nếu duplicate xuất hiện, `toMap` mặc định sẽ ném lỗi — tín hiệu hữu ích cho thấy query shape có vấn đề. Không mặc định merge duplicates bằng cách chọn arbitrary record.

### 16.4. Tránh query IN quá lớn

Với page size tối đa 100, danh sách IDs thường tương đối nhỏ. Nếu page size lên hàng chục nghìn, DBMS có giới hạn parameter/IN expressions và plan considerations; giải pháp không phải cứ tăng size vô hạn.

## 17. Aggregate OrderLines của page mà không nạp entities

Giả sử DTO cần thêm:

- `lineCount`: số dòng hàng.
- `totalQuantity`: tổng số lượng.
- `calculatedSubtotal`: tổng `quantity × unitPrice`.

Tạo một projection:

```java
package com.example.shop.api;

import java.math.BigDecimal;

public record OrderLineAggregate(
    Long orderId,
    Long lineCount,
    Long totalQuantity,
    BigDecimal calculatedSubtotal
) {}
```

JPQL:

```java
List<OrderLineAggregate> aggregates = em.createQuery(
    """
    SELECT new com.example.shop.api.OrderLineAggregate(
        l.order.id,
        COUNT(l),
        SUM(l.quantity),
        SUM(l.quantity * l.unitPrice)
    )
    FROM OrderLine l
    WHERE l.order.id IN :pageIds
    GROUP BY l.order.id
    """,
    OrderLineAggregate.class
)
.setParameter("pageIds", pageIds)
.getResultList();
```

### 17.1. Giới hạn của ví dụ về numeric types

Theo quy tắc JPQL aggregate, kiểu của `COUNT` là `Long`; `SUM` có những quy tắc kiểu dựa trên kiểu numeric expression. Với `int quantity`, `SUM(quantity)` thường được định kiểu `Long` theo đặc tả; với biểu thức chứa `BigDecimal`, cần xác nhận projection constructor/SQL numeric result tương thích trên provider/DBMS mục tiêu.

Nếu nghiệp vụ liên quan tiền và thuế, phải kiểm tra **rounding, scale, currency, discounts** và semantics của aggregate. Không coi biểu thức `SUM(quantity * unitPrice)` là tổng tiền thanh toán trong mọi mô hình.

### 17.2. Không có lines thì sao?

Query `GROUP BY l.order.id` **không có row cho Order không có lines**. Cần mapping default hợp lệ ở assembly layer:

```java
OrderLineAggregate empty = new OrderLineAggregate(
    orderId,
    0L,
    0L,
    BigDecimal.ZERO
);
```

Không giả định aggregate query luôn trả một row có count zero cho mọi Order.

### 17.3. Không nạp OrderLine entities

Projection sử dụng các expressions `l.order.id`, `COUNT` và `SUM`. Provider/DB có thể tính aggregate mà không hydrate từng OrderLine thành managed entity trong JVM.

Đó là lợi ích lớn khi một page gồm 20 Orders nhưng mỗi Order có hàng trăm hoặc hàng nghìn lines.

### 17.4. Khi aggregate phải lọc tenant

Nếu order IDs là generated từ query trusted, vẫn có thể tăng defense in depth:

```jpql
FROM OrderLine l
JOIN l.order o
WHERE o.tenantId = :tenantId
  AND o.id IN :pageIds
```

Query này bảo đảm scope rõ, hỗ trợ review bảo mật và bảo vệ khi code thay nguồn page IDs về sau.

## 18. Ghép aggregate vào DTO trả về

DTO chi tiết thêm aggregate:

```java
public record OrderListWithStats(
    Long id,
    String orderNumber,
    String customerName,
    OrderStatus status,
    Instant createdAt,
    BigDecimal totalAmount,
    long lineCount,
    long totalQuantity,
    BigDecimal calculatedSubtotal
) {}
```

Sau khi đã có `details` và `aggregates`:

```java
Map<Long, OrderListItem> detailById =
    details.stream().collect(
        Collectors.toMap(
            OrderListItem::id,
            Function.identity()
        )
    );

Map<Long, OrderLineAggregate> aggregateById =
    aggregates.stream().collect(
        Collectors.toMap(
            OrderLineAggregate::orderId,
            Function.identity()
        )
    );

List<OrderListWithStats> items =
    pageIds.stream()
        .map(id -> {
            OrderListItem base = detailById.get(id);
            if (base == null) {
                throw new IllegalStateException(
                    "Page item changed during read"
                );
            }

            OrderLineAggregate stats =
                aggregateById.get(id);

            long lineCount =
                stats == null ? 0L : stats.lineCount();

            long quantity =
                stats == null ? 0L : stats.totalQuantity();

            BigDecimal subtotal =
                stats == null
                    ? BigDecimal.ZERO
                    : stats.calculatedSubtotal();

            return new OrderListWithStats(
                base.id(),
                base.orderNumber(),
                base.customerName(),
                base.status(),
                base.createdAt(),
                base.totalAmount(),
                lineCount,
                quantity,
                subtotal
            );
        })
        .toList();
```

### 18.1. Thứ tự được giữ nguyên

Duyệt `pageIds` là cách rõ nhất để giữ đúng thứ tự của query phân trang, bất kể thứ tự các rows trong `details` hoặc `aggregates`.

### 18.2. Chi phí Java

Với page size hợp lý, tạo hai maps và 20 DTOs là chi phí nhỏ so với tải hàng nghìn OrderLine managed entities, nhưng vẫn cần đo nếu có đặc điểm workload khác.

### 18.3. Tách tổng tiền lưu và subtotal tính lại

`totalAmount` có thể gồm thuế, shipping, discount, voucher. `calculatedSubtotal` chỉ là tổng đơn giá × số lượng. Đặt tên rõ và không dùng thay lẫn nhau.

### 18.4. Cùng snapshot chưa?

Các query IDs/details/aggregates chạy tuần tự có thể thấy dữ liệu thay đổi giữa chúng nếu isolation cho phép. Có yêu cầu nhất quán mạnh thì phải dùng transaction/snapshot hoặc mô hình tiền tính/cursor phù hợp.

## 19. Có thể lấy COUNT và aggregate trong một query không?

Đôi khi có thể dùng `GROUP BY` và projections phức tạp để tính số dòng trên từng Order:

```jpql
SELECT
    o.id,
    COUNT(l)
FROM PurchaseOrder o
LEFT JOIN o.lines l
WHERE o.tenantId = :tenantId
GROUP BY o.id
```

Nhưng câu hỏi quan trọng là **pagination áp lên tập Orders sau grouping hay áp lên SQL rows trước grouping?**

### 19.1. Grouping có thể tạo query phức tạp

Khi muốn cùng lúc chọn nhiều fields trên Order, Customer và aggregate lines, có thể phải GROUP BY nhiều expressions theo quy tắc JPQL và DBMS. Execution plan có thể tốn kém so với page root IDs trước.

### 19.2. COUNT cho Page khác COUNT(lines)

- `COUNT(o)`: tổng Orders phù hợp filter.
- `COUNT(l)`: số OrderLines.
- `COUNT(DISTINCT o.id)`: số root Orders distinct trong query có to-many join.

Nhầm các số đếm này gây phân trang sai.

### 19.3. Một SQL không luôn nhanh hơn nhiều SQL

Một query join/group khổng lồ có thể trả nhiều rows trung gian, tiêu thụ CPU/IO và memory hơn ba queries nhỏ với page IDs. Đo execution plan, rows scanned và end-to-end latency trước khi tối ưu chỉ theo số statement.

### 19.4. Khi nào query aggregation trực tiếp hợp lý?

Nếu DB có index tốt, root page nhỏ và aggregate được tối ưu tốt, một query có GROUP BY và pagination đúng semantics có thể hiệu quả. Nhưng cần chứng minh tính đúng của root paging dưới query plan/provider thay vì viết theo cảm tính.

## 20. Nếu cần vài OrderLines đại diện cho mỗi Order

Màn hình danh sách đôi khi cần “3 sản phẩm đầu tiên” cho mỗi Order.

### 20.1. Không tải toàn bộ lines chỉ để lấy 3

Sai:

```java
order.getLines().stream()
    .limit(3)
    .toList();
```

Nếu collection lazy được initialize đầy đủ, DB/ORM có thể tải tất cả lines rồi Java mới chọn 3.

### 20.2. Hai hướng thực tế

- **Denormalize preview** có chính sách cập nhật/consistency rõ.
- **Query per-page preview rows** bằng SQL có window function `ROW_NUMBER() OVER (PARTITION BY order_id ...)` hoặc một chiến lược chuyên biệt được DB/provider hỗ trợ.

### 20.3. Vì sao phải phân biệt portable và provider-specific?

JPQL tiêu chuẩn ở một phiên bản nhất định có thể không biểu đạt thuận tiện “top K child rows per parent”. Dùng native SQL/window function PostgreSQL hoặc Hibernate extension có thể phù hợp, nhưng phải cô lập ở read repository và kiểm thử trên DBMS thực tế.

### 20.4. Chọn đúng thứ tự child

“Ba dòng đầu” phải có thứ tự xác định, ví dụ `line.position ASC, line.id ASC`, không dùng thứ tự tự nhiên của bảng.

### 20.5. Không dùng pagination toàn cục thay top K mỗi parent

`setMaxResults(3)` trên query `WHERE order_id IN :pageIds` chỉ trả ba lines **cho tất cả Orders cộng lại**, không phải ba lines **cho mỗi Order**.

## 21. Page so với Slice: khi nào bỏ COUNT?

Spring Data cung cấp hai ý tưởng:

- **Page**: content và metadata tổng elements/pages.
- **Slice**: content và dấu hiệu có trang tiếp theo, không bắt buộc biết tổng số rows.

### 21.1. Khi UI chỉ cần Next/Previous

Một cursor/feed hoặc màn hình “Xem thêm” thường không cần `totalElements`.

Ta có thể lấy `size + 1` rows:

```java
List<OrderListItem> candidates = em.createQuery(
    """
    SELECT new com.example.shop.api.OrderListItem(
        o.id, o.orderNumber, c.name,
        o.status, o.createdAt, o.totalAmount
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.tenantId = :tenantId
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    OrderListItem.class
)
.setParameter("tenantId", trustedTenantId)
.setFirstResult(offset)
.setMaxResults(size + 1)
.getResultList();

boolean hasNext = candidates.size() > size;

List<OrderListItem> current =
    candidates.subList(
        0,
        Math.min(size, candidates.size())
    );
```

Ở production cần validate `size` để `size + 1` không overflow và kiểm tra offset range như phần trước.

### 21.2. Lợi ích

Có thể tránh COUNT query trong request nếu chỉ cần `hasNext`, đặc biệt với bảng/filters lớn.

### 21.3. Giới hạn

Không thể hiển thị “Trang 3 trên 142” nếu không biết total. Số `hasNext` chỉ có ý nghĩa tương ứng với trạng thái dữ liệu/query tại lúc đọc.

### 21.4. Có Slice là không cần pagination đúng?

Vẫn phải có sort ổn định, database limit, tenant filter và xử lý concurrency.

### 21.5. Spring Data Slice

Một repository có thể trả `Slice<OrderListItem>` với `Pageable` trong những trường hợp framework hỗ trợ. Cần kiểm tra SQL thực tế và count behavior theo Spring Data version; nếu query phức tạp, tự viết size+1 là một lựa chọn minh bạch.

## 22. Offset pagination và hạn chế ở trang sâu

```java
.setFirstResult(page * size)
.setMaxResults(size)
```

là API JPA chuẩn. Provider/dialect dịch sang SQL pagination phù hợp DBMS.

### 22.1. Deep offset

Ở page 100.000, database có thể phải quét/bỏ qua rất nhiều rows trước khi trả 20 rows. Dù không tải entities thừa trong JVM, database vẫn chịu chi phí.

### 22.2. Drift khi đồng thời INSERT/DELETE

Ví dụ:

```text
Page 0:
  [100, 99, 98]

A new Order 101 is inserted.

Page 1 with OFFSET 3:
  [98, 97, 96]
```

Order#98 bị lặp giữa hai pages. Đây là đặc điểm thường gặp của offset pagination trên tập dữ liệu thay đổi.

### 22.3. Khi nào offset đủ tốt?

- Backoffice có vài nghìn rows.
- Users thường chỉ xem vài trang đầu.
- Cần nhảy tới trang số cụ thể.
- Data volatility và consistency requirements không quá khắt khe.

### 22.4. Khi nào cân nhắc keyset/cursor?

- Feed hoạt động liên tục.
- Dữ liệu rất lớn.
- Deep paging chậm.
- UI thường chỉ Next/Previous.
- Muốn tránh một số hiện tượng drift do insert ở đầu danh sách.

## 23. Keyset pagination với createdAt + id

Với thứ tự:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

client có thể gửi cursor là pair của row cuối trang trước:

```text
lastCreatedAt = 2026-11-10T08:30:00Z
lastId        = 801
```

Query trang tiếp theo:

```java
List<OrderListItem> next = em.createQuery(
    """
    SELECT new com.example.shop.api.OrderListItem(
        o.id,
        o.orderNumber,
        c.name,
        o.status,
        o.createdAt,
        o.totalAmount
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.tenantId = :tenantId
      AND o.status = :status
      AND (
          o.createdAt < :cursorCreatedAt
          OR (
              o.createdAt = :cursorCreatedAt
              AND o.id < :cursorId
          )
      )
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    OrderListItem.class
)
.setParameter("tenantId", trustedTenantId)
.setParameter("status", status)
.setParameter("cursorCreatedAt", cursorCreatedAt)
.setParameter("cursorId", cursorId)
.setMaxResults(size + 1)
.getResultList();
```

### 23.1. Vì sao có hai thành phần cursor?

Nếu chỉ so sánh `createdAt`, những Orders có cùng timestamp có thể bị mất hoặc lặp. `id` làm tie-breaker.

### 23.2. Cursor có cần bảo vệ không?

Nếu cursor được đưa qua HTTP, nên dùng định dạng opaque/có xác thực theo security policy, tránh client sửa arbitrary values hoặc làm lộ internal metadata. Cursor có thể gắn tenant/filter/sort hoặc server phải xác minh chúng khi nhận.

### 23.3. Null và mutable sort keys

Ví dụ giả định `createdAt` không null và không thay đổi. Nếu sort field nullable hoặc thay đổi liên tục, predicate keyset và consistency phải được thiết kế thêm.

### 23.4. Keyset có giải quyết mọi concurrency không?

Không. Nếu giá trị sort của record đang xem thay đổi, hoặc authorization filter đổi giữa requests, vẫn có thể có biến động. Keyset chủ yếu tránh chi phí OFFSET sâu và một số trường hợp dịch chuyển trang do inserts trước cursor.

### 23.5. Index

Một composite index tương thích filter/sort giúp keyset hiệu quả. Cursor query trên dữ liệu lớn vẫn cần `EXPLAIN` và benchmark.

## 24. Tối ưu chỉ bắt đầu sau khi đo

Một query ít SQL không đồng nghĩa nhanh nhất. Cần đo:

| Metric | Giải thích |
| --- | --- |
| JDBC SQL executions/request | Phát hiện N+1, extra SQL |
| Query latency p50/p95/p99 | Trải nghiệm người dùng và tail latency |
| Rows returned từ DB | Phát hiện JOIN multiplication |
| Bytes transferred | Payload SQL lớn |
| Entity load/collection load counts | Hydration ORM không cần thiết |
| Heap allocation và GC | Tải graph quá lớn |
| Database CPU/IO/locks | Chi phí bị đẩy xuống DB |
| Connection acquisition wait | Pool contention |
| COUNT query duration | Có nên dùng Slice thay Page? |
| Cache hits/misses | Cold vs warm behavior |

### 24.1. Baseline minh họa

Một hệ thống có thể ghi:

```text
page size=20
orders returned=20

Old entity mapper:
  1 query for orders
  20 queries for customers
  20 queries for lines
  total 41 queries

New DTO projection:
  1 content query
  1 count query (when required)
  total ~2 queries
```

Đây là **mô hình minh họa**, không phải số đo có sẵn. Thực tế phụ thuộc provider, cache, filter và cách framework xử lý COUNT.

### 24.2. Đừng chỉ đo global Hibernate Statistics

`SessionFactory.getStatistics()` có counters, nhưng chúng thường toàn cục. Trong concurrent test/load, chúng có thể cộng hoạt động của nhiều requests và không ánh xạ chính xác từng request.

### 24.3. JDBC prepare count khác execute count

`getPrepareStatementCount()` không phải bằng chứng tuyệt đối về số lần `executeQuery/executeUpdate/executeBatch`, vì statement reuse và batching làm các metrics khác nhau.

### 24.4. Đo end-to-end

Nếu chỉ đo `getResultList()` mà quên JSON serialization hoặc mapping LAZY sau query, có thể bỏ sót phần lớn chi phí ở triển khai cũ.

## 25. Dùng index phù hợp filter + order

Với query:

```sql
SELECT ...
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.tenant_id = ?
  AND o.status = ?
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20 OFFSET 0;
```

Một candidate index PostgreSQL:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
ON purchase_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
```

### 25.1. Đây là candidate, không phải khẳng định tối ưu tuyệt đối

Index phụ thuộc selectivity, filter combinations, data distribution, DBMS và query plan. Nếu có nhiều queries không filter status, có thể cần chiến lược index khác.

### 25.2. COUNT cũng cần chú ý

COUNT theo tenant/status vẫn có thể tốn thời gian trên bảng lớn; index không biến mọi COUNT thành phép toán O(1).

### 25.3. Composite index và keyset

Index theo tenant/status/created_at/id có thể hỗ trợ cả offset nhỏ và keyset theo createdAt/id, nếu optimizer thấy phù hợp.

### 25.4. Đánh đổi write overhead

Index cần storage và làm INSERT/UPDATE/DELETE tốn thêm công. Đừng tạo nhiều index trùng lặp chỉ để chạy một test nhanh hơn.

### 25.5. Dùng plan thật

`EXPLAIN (ANALYZE, BUFFERS)` trên PostgreSQL hoặc công cụ tương ứng của DBMS giúp xác nhận rows scan, index usage, sort và I/O. Dataset test vài chục rows không thể đại diện kết quả production-scale.

## 26. Filter động và count consistency

API có thể cần:

```text
status
createdFrom
createdTo
customerName
minTotal
maxTotal
```

### 26.1. Không nối raw input vào JPQL

Sai:

```java
"WHERE o.status = '" + request.status() + "'"
```

Đúng: build query structure từ allowlisted fields và bind values bằng `setParameter()`.

### 26.2. Criteria API là lựa chọn chuẩn cho filter động

`CriteriaBuilder`, `CriteriaQuery` và `Predicate` giúp build conditions programmatically.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<OrderListItem> cq =
    cb.createQuery(OrderListItem.class);

Root<PurchaseOrder> o =
    cq.from(PurchaseOrder.class);

Join<PurchaseOrder, Customer> c =
    o.join("customer");

List<Predicate> filters = new ArrayList<>();

filters.add(
    cb.equal(o.get("tenantId"), trustedTenantId)
);

if (status != null) {
    filters.add(cb.equal(o.get("status"), status));
}

cq.select(
    cb.construct(
        OrderListItem.class,
        o.get("id"),
        o.get("orderNumber"),
        c.get("name"),
        o.get("status"),
        o.get("createdAt"),
        o.get("totalAmount")
    )
);

cq.where(filters.toArray(Predicate[]::new));

cq.orderBy(
    cb.desc(o.get("createdAt")),
    cb.desc(o.get("id"))
);
```

Đoạn này là fragment, cần tạo `TypedQuery`, thêm pagination và count query riêng. Nó dùng API chuẩn JPA; static metamodel có thể thay string property names để giảm lỗi rename.

### 26.3. Count dùng cùng predicates về mặt logic

Có thể dùng cùng filter model để tạo hai Criteria queries, nhưng không nên tái sử dụng các `Predicate`/`Root` objects gắn với một `CriteriaQuery` khác một cách tùy tiện. Xây predicates từ cùng filter specification cho từng query root.

### 26.4. COUNT và LEFT JOIN khi filter optional relation

Nếu content query cho phép Customer null bằng LEFT JOIN nhưng count query dùng INNER JOIN, tổng có thể lệch. Cần rà soát semantics joins.

### 26.5. Filter dữ liệu nhạy cảm

Tenant/authorization predicates phải áp cho mọi query, kể cả count, summary aggregation, search và export.

## 27. DTO projection so với EntityGraph

`EntityGraph` là cơ chế JPA chuẩn để xác định attributes cần nạp ở một entity query.

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

query.setHint(
    "jakarta.persistence.fetchgraph",
    graph
);
```

### 27.1. Khi nào EntityGraph hữu ích?

Khi use case thực sự cần managed `PurchaseOrder` và Customer entity để thực hiện domain operation hoặc return graph trong transaction có kiểm soát.

### 27.2. Khi nào DTO projection tốt hơn?

Khi endpoint chỉ cần vài scalar columns và không thay đổi entities. Không cần hydrate entire Order + Customer rồi map ngược về DTO.

### 27.3. EntityGraph không tự làm pagination collection an toàn

Nếu graph chứa `lines` to-many, provider có thể thực hiện collection fetching theo chiến lược gây row multiplication hoặc extra selects. EntityGraph **không phải magic fix** cho mọi pageable query.

### 27.4. Fetch join và projection giải quyết hai nhu cầu khác nhau

| Nhu cầu | Hướng chính |
| --- | --- |
| List UI chỉ cần scalar fields | DTO projection |
| Load Order aggregate để chỉnh sửa | Entity query với fetch plan thích hợp |
| N+1 to-one nhưng vẫn cần managed entities | `JOIN FETCH` / `EntityGraph` |
| Page roots và cần aggregate lines | Page IDs + aggregate query |
| Page roots và cần preview top-K lines | Chuyên biệt per-page child query/native SQL |
| Scrolling feed | Keyset/cursor + DTO |

## 28. Một endpoint REST hoàn chỉnh theo hướng DTO

Thiết kế controller đơn giản (Spring MVC):

```java
@RestController
@RequestMapping("/api/orders")
public class OrderListController {

    private final OrderListService service;

    public OrderListController(OrderListService service) {
        this.service = service;
    }

    @GetMapping
    public OrderPageResponse list(
            @RequestParam(required = false)
            OrderStatus status,

            @RequestParam(defaultValue = "0")
            int page,

            @RequestParam(defaultValue = "20")
            int size) {

        return service.list(status, page, size);
    }
}
```

`OrderListService` là application service được implement theo chiến lược ở phần trước, resolve trusted actor/tenant và gọi repository.

### 28.1. Controller không nhận tenantId trực tiếp

Nếu tenant dựa vào authentication, không để `tenantId` từ query/body thay source tin cậy.

### 28.2. Validate request trước DB

- Page không âm.
- Size trong khoảng cho phép (ví dụ 1–100).
- Status thuộc enum được hỗ trợ.
- Sort/filter là allowlisted.
- Deep offsets có policy rõ (có thể chuyển keyset).

### 28.3. Response DTO không chứa lazy proxies

Vì service trả `OrderPageResponse` từ scalar DTOs, serialization không cần mở persistence context.

### 28.4. Cần error handling theo API contract

Invalid page/size/sort nên trả 400 hoặc 422 theo API policy; không trả raw persistence exception hoặc SQL stacktrace cho client.

### 28.5. Kiểm soát kích thước JSON

Dù chỉ có scalar fields, page size lớn vẫn tăng response bytes và serializer CPU. Giới hạn size là một phần bảo vệ tài nguyên hệ thống.

## 29. Kiểm thử tích hợp: phát hiện N+1 thực sự

Một test đơn giản chỉ tạo 2 Orders có thể không phát hiện vấn đề. Dataset nên đủ nhiều và cố tình có **nhiều Customers khác nhau**.

### 29.1. Fixture đại diện

```text
Tenant A:
  100 Customers
  200 Orders
  5-50 Lines per Order
  Several Orders share createdAt timestamps

Tenant B:
  50 Customers
  100 Orders
  Orders with overlapping order numbers
```

Số fixtures là minh họa; điều quan trọng là có đủ distinct associations để lộ SQL pattern.

### 29.2. Test query result

Ví dụ với JUnit và transactional `EntityManager`:

```java
@Test
void returnsDtoWithoutEntityGraph() {
    // Arrange: fixtures already inserted and committed,
    // or created in this test transaction.
    em.flush();
    em.clear();

    OrderPageResponse result = query.findPage(
        "tenant-A",
        OrderStatus.SUBMITTED,
        0,
        20
    );

    assertEquals(20, result.items().size());

    assertTrue(
        result.items().stream().allMatch(
            item -> item.customerName() != null
        )
    );

    assertTrue(
        result.items().stream().allMatch(
            item -> item.totalAmount() != null
        )
    );
}
```

Test còn cần import và bootstrap fixtures phù hợp. Nếu test dùng L2 cache, làm rõ cache state; `clear` chỉ xóa L1.

### 29.3. SQL budget test

Dùng JDBC/DataSource proxy hoặc tracing per-test để đo executions ở phạm vi service call:

```text
start SQL counter
call listOrders(size=1)
record SQL executions

clear/cache-isolate
start SQL counter
call listOrders(size=50)
record SQL executions
```

**Mục tiêu:** số SQL không tăng tuyến tính theo số Orders chỉ vì mapper truy cập Customer hoặc Lines.

### 29.4. Không hard-code số statement khi framework tối ưu count

Với Spring Data Page, count query có thể được bỏ qua trong trường hợp suy được total từ content. Một test quá cứng nhắc “phải chính xác 2 SQL” dễ vỡ khi framework thay đổi dù code vẫn đúng.

### 29.5. Dùng công cụ đúng để đếm

Hibernate Statistics có counters về prepared statements/entity loads, nhưng để đo chính xác JDBC execute count, công cụ JDBC instrumentation thường phù hợp hơn. Global statistics có thể bị nhiễu nếu chạy test song song.

## 30. Kiểm thử phân trang đúng root rows

### 30.1. Không trùng IDs giữa trang ổn định

Với fixtures không thay đổi trong lúc test:

```java
OrderPageResponse page0 =
    query.findPage("tenant-A", null, 0, 20);

OrderPageResponse page1 =
    query.findPage("tenant-A", null, 1, 20);

Set<Long> firstIds = page0.items().stream()
    .map(OrderListItem::id)
    .collect(Collectors.toSet());

Set<Long> secondIds = page1.items().stream()
    .map(OrderListItem::id)
    .collect(Collectors.toSet());

assertTrue(
    Collections.disjoint(firstIds, secondIds)
);
```

Khi dữ liệu có concurrent inserts, offset paging có thể làm lặp; fixture test này phải **ổn định** để kiểm tra sort/pagination logic.

### 30.2. Tie-breaker test

Tạo nhiều Orders cùng createdAt nhưng ID khác nhau. Kỳ vọng mỗi page có thứ tự `id DESC` trong nhóm timestamp bằng nhau.

### 30.3. TotalElements test

Xác nhận:

- `totalElements` phản ánh toàn bộ rows phù hợp tenant/status.
- `items.size() <= size`.
- `totalPages` được tính đúng.
- Trang cuối có `hasNext=false`.
- Trang vượt cuối trả empty content.

### 30.4. Tenant isolation test

Actor tenant-A không được thấy Orders tenant-B, kể cả chúng có cùng status/orderNumber. Count cũng không được tính tenant-B.

### 30.5. Optional filter test

Test `status=null` trả nhiều statuses nhưng vẫn giới hạn tenant và sort đúng.

## 31. Kiểm thử kỹ thuật để chứng minh không hydrate thừa

Ngoài SQL count, có thể xem entity/collection load counters nếu dùng Hibernate:

```java
SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics statistics =
    sessionFactory.getStatistics();
```

Đây là Hibernate API, không phải JPA standard.

### 31.1. Điều gì cần quan sát?

Với scalar constructor projection, ta không muốn số `PurchaseOrder`/`OrderLine` managed entity loads tăng chỉ vì build list DTO.

Nhưng counters có phạm vi toàn cục; phải cô lập test và xem version/provider behavior.

### 31.2. Query trả DTO không bảo đảm zero DB work

DTO projection giảm hydration, không xóa chi phí JOIN, sorting, COUNT hoặc disk I/O. Một query vẫn có thể chậm nếu thiếu index hoặc filter kém.

### 31.3. Memory measurements

Nếu endpoint cũ hydrate 20 Orders × 500 Lines, application có thể tạo hàng nghìn entity/collection objects. Projection trả vài chục scalar DTOs thường giảm allocation đáng kể; đo heap/GC để xác nhận.

### 31.4. Serialization test

Sau khi service trả DTO, đóng transaction/context rồi serialize response. Không được có lazy loading SQL ngoài service, và JSON phải khớp API contract.

## 32. Test với PostgreSQL container và migrations thật

Khi production dùng PostgreSQL, JPA integration tests nên kiểm chứng trên PostgreSQL thật nếu query phụ thuộc SQL dialect, indexes, data types hoặc transaction semantics.

```text
JUnit 5 / Spring @DataJpaTest
      |
      v
PostgreSQL Testcontainers
      |
      v
Flyway/Liquibase migrations
      |
      v
JPA EntityManagerFactory
      |
      v
DTO pagination queries
      |
      v
SQL count + correctness assertions
```

### 32.1. Tránh H2 che khác biệt

H2 compatibility mode không đảm bảo hành vi pagination, sort/collation, index plan và locking giống PostgreSQL.

### 32.2. Migrations là schema owner

Nếu production dùng Flyway, test nên chạy migrations thật và không để Hibernate tự `drop-and-create` tables trước test.

### 32.3. Dữ liệu số và ngày giờ

Test `BigDecimal` precision/scale, `Instant` timestamps và order sorting với giá trị biên. Đừng chỉ dùng vài bản ghi có timestamps cách xa nhau.

### 32.4. Tách correctness và performance

Một PostgreSQL container với vài chục Orders xác nhận query hoạt động đúng; nó không chứng minh p95 production với hàng triệu rows.

## 33. Query COUNT và nội dung trong transaction thực

Một `Page` gồm content query và count query.

### 33.1. Khả năng inconsistent metadata

Giả sử:

```text
T1: SELECT content -> 20 rows
T2: INSERT Order and COMMIT
T1: SELECT COUNT -> total increased
```

Ở một số isolation levels, content và count có thể phản ánh hai committed states khác nhau.

### 33.2. Khi nào chấp nhận?

Danh sách backoffice thông thường có thể chấp nhận metadata hơi thay đổi trong khi có writes, miễn API không hứa snapshot mạnh.

### 33.3. Khi nào cần chính sách mạnh hơn?

- Báo cáo tài chính đối chiếu.
- Xuất dữ liệu cần snapshot nhất quán.
- Workflow phê duyệt dựa số lượng/tổng tuyệt đối.
- API cursor cần duy trì view nhất quán trong một đợt xử lý.

Khi đó có thể cần snapshot isolation, transaction design, query aggregates atomically hoặc materialized snapshot.

### 33.4. Read-only transaction không tự sửa mọi consistency issue

`@Transactional(readOnly=true)` không đồng nghĩa Serializable isolation. Phải định nghĩa requirement và test trên DBMS cụ thể.

## 34. Những lỗi phổ biến nhất

### Lỗi 1 — Trả Page<PurchaseOrder> rồi serialize

Có thể lộ fields không mong muốn, lazy proxies và N+1.

### Lỗi 2 — Chỉ thêm @JsonIgnore cho lines

Có thể giảm JSON field nhưng không bảo đảm provider không eager-fetch hoặc mapper không truy cập association ở nơi khác.

### Lỗi 3 — Dùng EAGER để tránh LazyInitializationException

Có thể làm nặng mọi use case và không đảm bảo tránh secondary selects.

### Lỗi 4 — `JOIN FETCH o.lines` kết hợp `Pageable`

Có nguy cơ pagination trong memory hoặc root-row limit sai.

### Lỗi 5 — Tin rằng DISTINCT luôn sửa pagination collection

Không loại chi phí SQL row multiplication hoặc behavior provider-specific.

### Lỗi 6 — Dùng `findAll()` rồi `subList()`

Đã tải mọi root rows vào JVM.

### Lỗi 7 — Map Customer.name qua LAZY getter trong vòng lặp

Có thể tạo N+1 queries.

### Lỗi 8 — Dùng DTO nhưng field DTO chứa entity

Vẫn có thể tải đồ thị object lớn.

### Lỗi 9 — Query constructor expression chọn `o` entity

Chưa tránh entity hydration.

### Lỗi 10 — Không ORDER BY khi phân trang

Page boundaries không xác định.

### Lỗi 11 — ORDER BY một cột không duy nhất

Có thể lặp/bỏ row giữa pages ngay cả khi dataset không thay đổi, do ties.

### Lỗi 12 — Query COUNT quên tenant predicate

Sai metadata và có thể lộ thông tin tenant khác.

### Lỗi 13 — Count trên to-many JOIN không DISTINCT

Một Order có thể bị đếm nhiều lần.

### Lỗi 14 — Thực thi `IN :ids` với list rỗng

Có thể sinh SQL không hợp lệ hoặc behavior provider-specific.

### Lỗi 15 — Giả định thứ tự `WHERE id IN :ids` theo thứ tự ids

Không được bảo đảm; phải reorder kết quả.

### Lỗi 16 — Tải toàn bộ OrderLines chỉ để tính COUNT/SUM

Có thể dùng database aggregate query.

### Lỗi 17 — Tính `getLines().size()` trước khi page root IDs

Dễ gây collection load cho rất nhiều Orders.

### Lỗi 18 — Dùng COUNT khi UI chỉ cần hasNext

Thêm query tốn kém không cần thiết; cân nhắc Slice.

### Lỗi 19 — Trang sâu bằng OFFSET mà không đo

DB có thể quét lượng lớn rows; cân nhắc keyset.

### Lỗi 20 — Cursor chỉ chứa createdAt mà không có ID tie-breaker

Có thể bỏ qua Orders có cùng timestamp.

### Lỗi 21 — Cho client gửi raw ORDER BY expression

Injection và query behavior ngoài kiểm soát.

### Lỗi 22 — Không giới hạn page size

Client có thể yêu cầu hàng trăm nghìn DTOs và làm quá tải DB/API.

### Lỗi 23 — Chỉ đo SQL count

Một query JOIN lớn có thể đắt hơn vài queries nhỏ.

### Lỗi 24 — Đếm `getPrepareStatementCount()` là exact JDBC executions

Prepared statements và execute calls khác nhau.

### Lỗi 25 — Query result đúng trên dataset quá nhỏ

N+1 có thể chưa lộ vì mọi orders dùng chung một Customer hoặc cache đã ấm.

### Lỗi 26 — Chỉ test trang đầu

Không thấy duplicate/order drift, trang cuối hoặc empty page.

### Lỗi 27 — Coi @Transactional(readOnly=true) là tối ưu projection

Read-only không tự chọn ít cột hơn.

### Lỗi 28 — Coi EntityGraph là cơ chế pagination to-many tự an toàn

Không có cam kết đó.

### Lỗi 29 — Tự tính `page * size` bằng int không kiểm tra

Có thể overflow thành offset âm/sai.

### Lỗi 30 — Trả PageImpl trực tiếp rồi coi JSON contract bất biến

Serialization shape có thể chịu ảnh hưởng Spring Data version/config.

## 35. Thực hành theo từng bước

### Bước 1 — Đặt hợp đồng response

```text
GET /api/orders
Query:
  status optional
  page >= 0
  1 <= size <= 100

Sort:
  createdAt DESC, id DESC

Response:
  items: scalar DTO[]
  page, size, totalElements, totalPages, hasNext
```

Không cho response chứa JPA entities.

### Bước 2 — Tạo entity mapping tối thiểu

- `@ManyToOne(fetch=LAZY)` đến Customer.
- `@OneToMany(fetch=LAZY)` đến OrderLine.
- Không thêm EAGER chỉ để phục vụ list.
- Giữ `totalAmount` theo domain consistency policy.

### Bước 3 — Viết JPQL constructor query

Chọn đúng sáu fields cần cho `OrderListItem`, JOIN Customer để lấy tên.

### Bước 4 — Viết count query riêng

Dùng cùng tenant/status filters và không có collection fetch join.

### Bước 5 — Giới hạn size và offset

Giới hạn page size, tính offset không overflow và luôn ORDER BY tie-breaker.

### Bước 6 — Tạo fixtures đặc biệt

- 100 Customers distinct.
- 200 Orders.
- Nhiều Orders cùng timestamp.
- Một số Orders không có lines.
- Một số Orders có hàng trăm lines.
- Tenant B có Orders khác.

### Bước 7 — Kiểm thử correctness

Assert DTO fields, order, page metadata, last page, empty page, tenant isolation.

### Bước 8 — Kiểm thử N+1

Đo SQL executions khi page size từ 1 lên 50. SQL count không được tăng tuyến tính vì Customer/Line loading.

### Bước 9 — Bổ sung nhu cầu tổng hợp

Nếu UI muốn line count/subtotal, thêm page-ID + aggregate query; không thay bằng `JOIN FETCH` collection + pageable.

### Bước 10 — Đo và xem DB plan

Ghi p95, COUNT duration, rows returned, entity loads và EXPLAIN theo dataset representative.

## 36. Bài tập thực hành

### Bài 1 — Nhận diện N+1

```java
orders.stream()
    .map(o -> o.getCustomer().getName())
    .toList();
```

**Câu hỏi:** Nếu Customer là LAZY và có 50 distinct Customers?

**Đáp án:** Có nguy cơ 1 query Orders + khoảng 50 secondary Customer selects khi cache lạnh. Dùng projection `JOIN o.customer c` lấy `c.name`.

### Bài 2 — DTO có entity ẩn

```java
record OrderDto(Long id, Customer customer) {}
```

**Đáp án:** Chưa loại entity graph. Trả `customerName`/`customerId` scalars hoặc nested DTO không chứa JPA entity.

### Bài 3 — JOIN FETCH lines

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

kèm `setMaxResults(20)`.

**Đáp án:** Không đảm bảo portable database-level paging cho 20 distinct roots; cần page IDs trước hoặc thiết kế projection/aggregate.

### Bài 4 — COUNT khác filter

Content lọc `tenant=A AND status=SUBMITTED` nhưng count chỉ `status=SUBMITTED`.

**Đáp án:** Count sai và có thể lộ dữ liệu. Dùng cùng predicates.

### Bài 5 — Trang trống

`pageIds=[]` rồi chạy query `WHERE id IN :pageIds`.

**Đáp án:** Return sớm theo contract; đừng phụ thuộc behavior của empty IN list.

### Bài 6 — Reorder

Query ID page trả `[9,7,4]`, query details trả `[4,9,7]`.

**Đáp án:** Build map by ID và duyệt page IDs để giữ thứ tự ban đầu.

### Bài 7 — COUNT lines

Order A có 4 lines, Order B có 2 lines. Query COUNT(o) với JOIN lines trả 6.

**Đáp án:** Đang đếm join rows; cần count distinct roots/EXISTS hoặc thay query shape.

### Bài 8 — Sum không có lines

Aggregate query không trả record cho Order C có 0 lines.

**Đáp án:** Dùng default count 0/subtotal 0 khi không có aggregate group.

### Bài 9 — Sort tie

Hai Orders cùng createdAt; query chỉ sort createdAt.

**Đáp án:** Thêm unique tie-breaker `id`.

### Bài 10 — Deep page

`page=100000`, `size=50` trên bảng rất lớn.

**Đáp án:** OFFSET có thể chậm. Đo và cân nhắc keyset pagination.

### Bài 11 — Cursor không đầy đủ

Cursor chỉ lưu timestamp, các records khác cùng timestamp bị bỏ.

**Đáp án:** Dùng composite cursor (createdAt, id) theo sort.

### Bài 12 — Count quá tốn

UI chỉ có “Xem thêm”, không hiển thị tổng pages.

**Đáp án:** Dùng size+1/Slice; bỏ count query nếu API contract cho phép.

### Bài 13 — Client sort SQL

`sort=createdAt DESC; DROP TABLE ...`.

**Đáp án:** Không nối raw string vào JPQL/SQL; allowlist property/direction.

### Bài 14 — Tenant từ request

Client gửi `tenantId=B` trong query param nhưng đang đăng nhập ở A.

**Đáp án:** Không dùng làm trusted tenant scope; xác định từ authenticated principal/membership.

### Bài 15 — Read-only transaction

Service dùng `@Transactional(readOnly=true)` nhưng trả `List<PurchaseOrder>`.

**Đáp án:** Vẫn trả managed entities; read-only không tự trở thành DTO projection.

### Bài 16 — L2 cache

Test SQL count tăng bất thường giữa hai lần chạy có cache khác nhau.

**Đáp án:** Cần kiểm soát cold/warm cache và đo executions đúng scope.

### Bài 17 — Trang cuối

Total=41, size=20.

**Đáp án:** Có 3 pages; page 2 chứa 1 row và `hasNext=false`.

### Bài 18 — Offset overflow

`page` và `size` đều lớn; `page * size` trong int thành số âm.

**Đáp án:** Tính bằng long, validate range rồi mới cast.

### Bài 19 — Row count vs SQL count

Một query trả 50.000 join rows để dựng 20 Orders; query khác dùng 3 SQL trả 1.000 rows.

**Đáp án:** Nhiều SQL hơn có thể nhanh hơn và tốn ít RAM; đo rows, bytes, latency, DB work.

### Bài 20 — Kiểm thử production-like

Test H2 pass nhưng PostgreSQL có khác biệt ORDER BY/collation.

**Đáp án:** Chạy integration test trên DBMS đích, migrations thật và dataset đủ đại diện.

## 37. Câu hỏi tự kiểm tra

**1. DTO projection là gì?**

Query trực tiếp chọn expressions cần thiết để tạo DTO, thay vì nạp managed entities rồi map.

**2. JPQL hỗ trợ constructor projection không?**

Có, qua `SELECT NEW fully.qualified.Dto(...)`.

**3. DTO từ constructor projection có được JPA dirty-check như entity không?**

Không như managed entity.

**4. Vì sao có thể xuất hiện N+1 khi map `getCustomer().getName()`?**

Vì association LAZY chưa load có thể phát một secondary query cho từng Customer chưa có trong cache/context.

**5. Khi list chỉ cần Customer.name, dùng JOIN hay JOIN FETCH?**

JOIN chọn scalar `c.name` trong DTO là hướng phù hợp; không cần fetch toàn Customer entity.

**6. @ManyToOne mặc định có thể EAGER không?**

Có; khai báo fetch plan rõ theo use case để tránh vô tình over-fetch.

**7. Vì sao không trả entity trực tiếp từ REST?**

Có thể lộ fields, lazy proxy/N+1, vòng quan hệ và phụ thuộc serialization vào persistence context.

**8. setFirstResult và setMaxResults thuộc API nào?**

Jakarta Persistence/JPA query API chuẩn.

**9. ORDER BY có cần thiết với pagination không?**

Có, nếu muốn thứ tự deterministic.

**10. Vì sao thêm id làm tie-breaker?**

Vì createdAt/totalAmount có thể trùng giữa nhiều records.

**11. Page khác Slice thế nào?**

Page có metadata tổng; Slice chỉ cần biết có trang tiếp theo.

**12. COUNT query có thể được bỏ qua khi nào?**

Khi UI/API không cần total và có thể dùng size+1/Slice; hoặc framework tối ưu theo ngữ cảnh.

**13. Count query có cần tenant filter không?**

Có, để đúng semantics và không lộ metadata ngoài scope.

**14. Collection fetch join với pagination nguy hiểm vì sao?**

To-many JOIN nhân SQL rows, có thể khiến paging sai hoặc provider paging trong memory.

**15. SELECT DISTINCT tự sửa mọi rủi ro collection fetch join pagination không?**

Không.

**16. Cách an toàn khi cần số lines trên một page Orders?**

Page root IDs trước rồi aggregate OrderLines cho `IN :pageIds`.

**17. Query `IN :ids` có bảo toàn thứ tự list ids không?**

Không; reorder ở Java hoặc áp order phù hợp.

**18. Khi page IDs rỗng, nên làm gì?**

Trả empty result theo contract, tránh empty IN query.

**19. COUNT(l) và COUNT(o) giống nhau không?**

Không; chúng đếm các đối tượng/query rows khác nhau.

**20. GROUP BY trả row cho Order không có Line không?**

Không trong query bắt đầu từ OrderLine; cần default khi assemble.

**21. Vì sao `SUM(quantity * unitPrice)` cần kiểm tra?**

Numeric typing, scale, rounding và business total semantics có thể khác.

**22. Có nên dùng `Page<Entity>` rồi Jackson bỏ field?**

Không nếu mục tiêu là tránh entity hydration và uncontrolled lazy loads.

**23. EntityGraph có luôn tốt hơn projection không?**

Không; nó dùng cho controlled entity fetch, projection phù hợp scalar list.

**24. @Transactional(readOnly=true) có tự tránh N+1 không?**

Không.

**25. Offset sâu có thể chậm vì sao?**

DB cần xử lý/bỏ qua nhiều rows trước khi trả page.

**26. Keyset cursor cần những trường nào với sort createdAt DESC, id DESC?**

Thường cần cả createdAt và id để tạo predicate tiếp theo.

**27. Keyset có đảm bảo snapshot bất biến giữa requests không?**

Không tự động.

**28. Dynamic sort từ client nên xử lý thế nào?**

Allowlist fields/directions, không nối raw identifiers.

**29. Index nào đáng thử cho tenant/status + createdAt/id sort?**

Một composite index theo các predicates và order keys, nhưng cần EXPLAIN/benchmark trước khi kết luận.

**30. SQL count ít có luôn là nhanh nhất không?**

Không; rows/bytes, DB plan, CPU/IO và memory cũng quan trọng.

**31. Vì sao SQL tests cần nhiều distinct Customers?**

Để N+1 không bị che bởi identity map hoặc nhiều Orders cùng tham chiếu một Customer.

**32. Vì sao cần kiểm soát L1/L2 cache trong performance test?**

Cache hits thay đổi SQL count và latency.

**33. Với Spring Data Page, có nên assert luôn đúng hai SQL không?**

Không nhất thiết; framework có thể tối ưu count, provider/caches cũng ảnh hưởng.

**34. Count và content trong cùng read-only transaction có chắc cùng snapshot không?**

Không ở mọi isolation level.

**35. Bài học quan trọng nhất khi làm pageable DTO?**

Page root records ở DB, chỉ chọn fields cần thiết, tách to-many aggregation/fetch khỏi root paging, bảo đảm scope/order/count và kiểm thử SQL behavior thực tế.

## 38. Kịch bản tổng hợp: từ API chậm đến API ổn định

Một hệ thống thương mại có:

```text
1,000,000 PurchaseOrders
300,000 Customers
~10 OrderLines/Order on average
PostgreSQL + Hibernate
Spring Boot REST API
```

Màn hình “Đơn đã nộp” hiển thị 20 Orders/trang và có bộ lọc status.

### 38.1. Triển khai ban đầu

```java
Page<PurchaseOrder> entities =
    repository.findAll(pageable);

return entities.map(order -> new OrderListItem(
    order.getId(),
    order.getOrderNumber(),
    order.getCustomer().getName(),
    order.getStatus(),
    order.getCreatedAt(),
    order.getTotalAmount()
));
```

Các vấn đề:

- Query không lọc tenant/status đúng use case nếu dùng `findAll`.
- Lazy Customer getters có thể tạo N+1.
- Entities chứa nhiều state không cần thiết.
- Serializer/mapping phụ thuộc transaction/context.
- Nếu thêm `getLines()` để tính tổng, collection loads tăng.

### 38.2. Bước sửa đầu tiên

Dùng JPQL constructor projection với `JOIN o.customer c`, tenant/status predicates, `ORDER BY createdAt DESC, id DESC`, `Pageable` và count query riêng.

### 38.3. Bước sửa thứ hai nếu UI muốn lineCount

Đừng chuyển sang `JOIN FETCH o.lines`. Dùng page IDs rồi aggregate lines theo IDs. Reorder và assemble DTO.

### 38.4. Bước sửa thứ ba khi user cuộn rất sâu

Kiểm tra p95 và execution plan của deep offset; nếu cần, chuyển endpoint dạng feed sang keyset/cursor.

### 38.5. Bộ kiểm thử hồi quy

- Đúng tenant/status.
- Không duplicate root IDs trên fixture ổn định.
- Tie-breakers và last page đúng.
- Số SQL không tăng theo N Customers/Lines.
- Count query không leak tenant-B.
- Aggregates đúng với Orders có 0 hoặc nhiều Lines.
- SQL trên PostgreSQL migrations thật.
- JSON serialize không đòi mở EntityManager.
- Optional relations/NULL/BigDecimal có test riêng.
- Trang lớn bị giới hạn.
- Concurrent inserts được mô tả rõ trong API semantics.

### 38.6. Quyết định tối ưu cần dựa dữ liệu

Có thể projection đã đáp ứng SLO. Nếu không, xem indexing, COUNT cost, filter selectivity, DB load và request concurrency. Đừng bật tất cả Hibernate fetch/batch/cache settings cùng lúc rồi không biết yếu tố nào giúp.

## 39. Tóm tắt quy trình lựa chọn

```text
Màn hình cần những field nào?
               |
               v
Chỉ scalar/to-one fields?
       /                     \
     Có                       Không
      |                         |
      v                         v
JPQL constructor DTO       Cần to-many data?
with JOIN to-one                |
      |                  +------+------+
      v                  |             |
Database LIMIT/OFFSET   Aggregate      Preview rows
+ stable ORDER BY          |             |
      |                    v             v
      |                Page IDs      Page IDs +
      |                 first        top-K child
      |                    |         query strategy
      |                    v             |
      |             GROUP BY page IDs    |
      +--------------------+-------------+
                           |
                           v
                  Assemble scalar DTOs
                           |
                           v
                 Need totalElements?
                      /         \
                    Yes          No
                     |            |
                     v            v
                 COUNT query     size+1 Slice
                      \           /
                       v         v
                   Observe SQL/count
                       |
                       v
             Test tenant, order, pages,
             rows, SQL budget and latency
```

## 40. Kết luận

Trả DTO có phân trang mà không tải thừa đồ thị entity là một **kỹ thuật thiết kế read path**, không chỉ là đổi kiểu trả về từ `List<Entity>` sang `List<Dto>`.

Một implementation tốt thường đáp ứng những nguyên tắc:

1. **Phân biệt use case danh sách với use case chỉnh sửa aggregate**; danh sách nên trả scalar DTOs khi chỉ cần dữ liệu hiển thị.
2. **Dùng JPQL constructor projection** hoặc một projection mechanism phù hợp để chọn đúng columns.
3. **JOIN to-one để lấy fields cần thiết**, không fetch toàn bộ Customer entity nếu chỉ cần tên.
4. **Page root rows ở database**, có `setFirstResult`/`setMaxResults` hoặc `Pageable` và thứ tự ổn định.
5. **Không dùng pageable collection fetch join như cách giải N+1**, vì row multiplication và in-memory pagination risks.
6. **Khi cần thông tin to-many, page IDs trước rồi aggregate/fetch đúng page IDs**, không load hàng nghìn children chỉ để tính vài chỉ số.
7. **Giữ thứ tự ban đầu** khi truy vấn details bằng `IN :ids`.
8. **Count query phải phản ánh cùng filters và authorization scope**; tránh fetch join và tránh đếm join rows thành root count.
9. **Dùng Slice hoặc keyset** khi không cần COUNT hoặc deep offsets quá đắt.
10. **Giới hạn page size, validate sort/filter, bind parameters và lấy tenant từ nguồn tin cậy**.
11. **Không dựa vào Open Session in View hoặc read-only annotation** để sửa over-fetching.
12. **Đo JDBC executions, rows, entity loads và latency**, không chỉ nhìn số SQL.
13. **Test trên database/migrations phù hợp** với production khi cần đúng SQL dialect/constraint.
14. **Kiểm thử các trường hợp âm**: trang trống, page vượt cuối, ties, null relation, 0 lines, duplicate child rows, tenant isolation và concurrency.
15. **Đặt DTO làm API contract rõ ràng**, không để entity proxy hoặc serialized `PageImpl` quyết định bất ngờ định dạng response.

Công thức dễ nhớ cho endpoint danh sách là:

```text
Filter safely
    -> Sort deterministically
    -> Page root data in DB
    -> Project only needed columns
    -> Aggregate children only for page IDs if required
    -> Count only when needed
    -> Return stable DTO response
    -> Measure and regression-test SQL
```

Kết quả mong đợi không chỉ là “trang có 20 dòng”, mà là **database chỉ xử lý phạm vi dữ liệu cần thiết, ORM không hydrate đồ thị không dùng tới, response không kích hoạt truy vấn ẩn và phân trang vẫn chính xác khi entity relationships trở nên phức tạp**.
