# Kết hợp bộ lọc có hoặc không có giá trị đầu vào trong Criteria API và Hibernate

## 1. Bài toán: một màn hình tìm kiếm, rất nhiều tổ hợp điều kiện

Một trang quản trị đơn hàng cho phép người dùng tìm kiếm theo nhiều tiêu chí:

- Từ khóa trong tên hoặc email khách hàng.
- Trạng thái đơn hàng: DRAFT, PAID, CANCELLED.
- Khách hàng cụ thể.
- Tổng tiền tối thiểu và tối đa.
- Ngày tạo bắt đầu và kết thúc.
- Danh sách sản phẩm xuất hiện trong đơn.
- Chỉ xem đơn có dòng hàng, hoặc chỉ xem đơn chưa có dòng hàng.
- Sắp xếp và phân trang.

Người dùng không nhất thiết điền mọi tiêu chí. Một yêu cầu có thể chỉ chứa trạng thái PAID; yêu cầu khác chỉ có khoảng tiền; yêu cầu thứ ba có từ khóa, trạng thái và thời gian cùng lúc.

Viết một câu HQL riêng cho từng tổ hợp nhanh chóng trở nên khó quản lý. Với 8 điều kiện có hoặc không xuất hiện, về lý thuyết có tới 2^8 = 256 tổ hợp bật/tắt. **Criteria API** của Jakarta Persistence cho phép xây dựng câu query theo từng điều kiện đang thực sự được cung cấp.

Ví dụ ý tưởng:

~~~java
List<Predicate> conditions = new ArrayList<>();

if (filter.status() != null) {
    conditions.add(cb.equal(root.get("status"), filter.status()));
}
if (filter.minAmount() != null) {
    conditions.add(cb.greaterThanOrEqualTo(
        root.get("totalAmount"), filter.minAmount()));
}

query.where(cb.and(conditions.toArray(Predicate[]::new)));
~~~

Nếu chỉ có status, SQL chỉ cần điều kiện status. Nếu có cả status và minAmount, hai điều kiện được ghép bằng AND. Nếu không có cả hai, query có thể vẫn chứa các ràng buộc bắt buộc như tenant và soft delete.

**Trọng tâm của bài:** không chỉ biết gọi CriteriaBuilder, mà còn xác định chính xác khi nào một bộ lọc được xem là **vắng mặt**, khi nào nó có giá trị hợp lệ, và khi nào một giá trị rỗng phải cho **không kết quả** thay vì vô tình lấy toàn bộ dữ liệu.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt điều kiện bắt buộc với bộ lọc tùy chọn.
2. Thiết kế request/filter object biểu diễn rõ null, chuỗi trắng, collection rỗng, số 0 và Boolean false.
3. Tạo danh sách Predicate động bằng CriteriaBuilder và kết hợp AND/OR có ngoặc đúng.
4. Chỉ tạo JOIN hoặc EXISTS khi bộ lọc tương ứng xuất hiện.
5. Xử lý an toàn LIKE, IN, BETWEEN, enum, BigDecimal và Instant.
6. Xây query lấy dữ liệu và count query có cùng ngữ nghĩa lọc.
7. Dùng Spring Data JPA Specification để tái sử dụng bộ lọc.
8. Kiểm soát phân trang, sắp xếp, distinct và collection join.
9. Tránh vô tình bỏ qua tenant, quyền truy cập hoặc soft-deleted rows.
10. Kiểm thử tổ hợp bộ lọc và đọc SQL Hibernate sinh ra.

Ví dụ sử dụng Java 17+, Jakarta Persistence 3.x, Hibernate ORM 6.x, Spring Boot 3.x và PostgreSQL. Criteria API là API chuẩn Jakarta Persistence; các chi tiết SQL, cách tối ưu query và kết quả của một số function vẫn phụ thuộc Hibernate version/dialect.

## 2. Mô hình entity cho ví dụ

Giả sử hệ thống có PurchaseOrder, Customer, OrderItem và Product.

~~~mermaid
erDiagram
    CUSTOMER ||--o{ PURCHASE_ORDER : places
    PURCHASE_ORDER ||--o{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    CUSTOMER {
        bigint id PK
        string full_name
        string email
    }
    PURCHASE_ORDER {
        bigint id PK
        bigint tenant_id
        bigint customer_id FK
        string status
        numeric total_amount
        timestamp created_at
        timestamp deleted_at
    }
    ORDER_ITEM {
        bigint id PK
        bigint order_id FK
        bigint product_id FK
    }
    PRODUCT {
        bigint id PK
        string sku
    }
~~~

Một mapping rút gọn:

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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Column(name = "total_amount", precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at")
    private Instant createdAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Instant getCreatedAt() { return createdAt; }
}

enum OrderStatus { DRAFT, PAID, CANCELLED }
~~~

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    @Column(name = "full_name")
    private String fullName;

    private String email;
}

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY)
    private Product product;
}

@Entity
@Table(name = "products")
public class Product {
    @Id
    private Long id;

    private String sku;
}
~~~

Trong project thật, mỗi public top-level class nằm trong file riêng; các getter, constructor và quy tắc domain được bổ sung theo thiết kế. Mã minh họa tập trung vào tên persistent attribute dùng trong Criteria, không phải toàn bộ entity lifecycle.

HQL/Criteria sử dụng **tenantId, totalAmount, createdAt và customer** theo tên thuộc tính Java đã được mapping; SQL do Hibernate sinh mới dùng tenant_id, total_amount, created_at và customer_id.

## 3. Thiết kế object biểu diễn bộ lọc

Không nên truyền chín tham số rời rạc qua nhiều lớp service. Một record mô tả yêu cầu tìm kiếm rõ hơn:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Set;

public record OrderSearchFilter(
    String keyword,
    Long customerId,
    Set<OrderStatus> statuses,
    BigDecimal minAmount,
    BigDecimal maxAmount,
    Instant createdFrom,
    Instant createdBefore,
    Set<Long> productIds,
    Boolean hasItems
) {
    public static OrderSearchFilter empty() {
        return new OrderSearchFilter(
            null, null, null, null, null,
            null, null, null, null
        );
    }
}
~~~

Mỗi field có một ý nghĩa rõ:

| Field | Giá trị không có filter | Khi có giá trị |
|---|---|---|
| keyword | null hoặc chuỗi trắng theo policy chuẩn hóa | Tìm tên/email Customer |
| customerId | null | Chỉ đơn của Customer cụ thể |
| statuses | null | Lọc theo tập enum |
| minAmount | null | Tổng tiền lớn hơn hoặc bằng ngưỡng |
| maxAmount | null | Tổng tiền nhỏ hơn hoặc bằng ngưỡng |
| createdFrom | null | Ngày tạo từ thời điểm này, bao gồm đầu mút |
| createdBefore | null | Ngày tạo trước thời điểm này, không gồm cuối |
| productIds | null | Chỉ đơn chứa ít nhất một Product trong tập |
| hasItems | null | true: có dòng hàng; false: không có dòng hàng |

Không dùng primitive boolean cho một tiêu chí có ba trạng thái **không cung cấp / true / false**, vì boolean primitive chỉ có hai giá trị. Dùng Boolean để giữ ý nghĩa null = không lọc.

### 3.1. Giá trị vắng mặt khác giá trị hợp lệ

Những kiểm tra sau rất dễ sai:

~~~java
if (filter.minAmount() != null
        && filter.minAmount().signum() > 0) {
    // Sai nếu 0 là ngưỡng hợp lệ cần lọc.
}
~~~

~~~java
if (Boolean.TRUE.equals(filter.hasItems())) {
    // Chỉ xử lý true, bỏ qua false dù client đã yêu cầu.
}
~~~

Quy tắc đúng:

~~~java
if (filter.minAmount() != null) {
    // 0 vẫn là giá trị hợp lệ.
}

if (filter.hasItems() != null) {
    // Xử lý cả true và false.
}
~~~

### 3.2. Chuỗi null, rỗng và chỉ chứa khoảng trắng

Ví dụ:

~~~text
keyword = null
keyword = ""
keyword = "   "
keyword = "Linh"
~~~

Một policy tìm kiếm thường hợp lý là coi ba giá trị đầu như **không cung cấp từ khóa**, và coi "Linh" là giá trị lọc. Cần chuẩn hóa trước khi xây Criteria:

~~~java
String keyword = filter.keyword() == null
    ? null
    : filter.keyword().strip();

if (keyword != null && !keyword.isBlank()) {
    // Bổ sung predicate tìm kiếm.
}
~~~

Đừng đồng nhất mọi chuỗi rỗng với không cung cấp cho mọi domain. Một bộ lọc “tên trường thật sự bằng chuỗi rỗng” hoặc “giá trị bị thiếu” có thể cần một operator riêng. Đây là quyết định API contract, không phải mặc định của Hibernate.

### 3.3. Danh sách null khác danh sách rỗng

Với statuses:

~~~text
statuses = null             -> client không yêu cầu lọc theo status
statuses = [PAID]           -> chỉ PAID
statuses = [PAID, DRAFT]    -> PAID hoặc DRAFT
statuses = []               -> tùy contract: không kết quả hoặc request không hợp lệ
~~~

Trong bài này chọn chính sách **null = không lọc; tập rỗng được cung cấp = không khớp bản ghi nào**. Cách này phù hợp với toán tử IN: không có status hợp lệ nào được cho phép trong tập rỗng.

Một API khác có thể quyết định [] = không lọc hoặc HTTP 400. Điều quan trọng là policy được định nghĩa và thực thi **trước khi** Hibernate tạo query. Nếu web framework tự gộp “không truyền parameter” với “truyền parameter rỗng” thành cùng một giá trị, DTO/argument resolver cần được thiết kế để không làm mất ngữ nghĩa.

## 4. Điều kiện bắt buộc không được phụ thuộc dữ liệu form

Giả sử hệ thống multi-tenant và dùng soft delete. Mọi query bình thường phải giới hạn:

~~~hql
where o.tenantId = :currentTenant
  and o.deletedAt is null
~~~

Ngay cả khi người dùng không chọn filter nào, hai điều kiện này vẫn phải tồn tại. Không được đưa tenantId do client tùy ý cung cấp vào cùng nhóm optional rồi bỏ qua khi null.

~~~java
predicates.add(cb.equal(
    root.get("tenantId"), authenticatedTenantId));
predicates.add(cb.isNull(root.get("deletedAt")));
~~~

**Tenant ID phải đến từ ngữ cảnh xác thực/ủy quyền đáng tin cậy**, không phải tham số request mà bất kỳ client nào cũng sửa được. Nếu cần tìm đơn của nhiều tenant với quyền admin, đó là use case khác phải được cấp quyền rõ ràng.

Một query builder an toàn có hai lớp:

1. **Ràng buộc luôn đúng:** tenant, phạm vi quyền truy cập, soft delete, trạng thái bảo mật.
2. **Bộ lọc tùy chọn:** keyword, status, tiền, thời gian, product, hasItems.

Kết quả cuối là AND của các ràng buộc bắt buộc với các nhóm predicate tùy chọn.

## 5. Cấu trúc Criteria API cơ bản

Jakarta Persistence cung cấp những kiểu chính:

| API | Vai trò |
|---|---|
| EntityManager | Tạo và thực thi CriteriaQuery trong persistence context |
| CriteriaBuilder | Xây phép so sánh, AND/OR, LIKE, EXISTS, COUNT, ORDER |
| CriteriaQuery<T> | Mô tả truy vấn SELECT trả kiểu T |
| Root<T> | Entity gốc của FROM |
| Path<T> | Đường dẫn một thuộc tính đã mapping |
| Predicate | Điều kiện logic |
| Join<Z,X> | Association join |
| Subquery<T> | Truy vấn con |
| TypedQuery<T> | Bind tham số/giới hạn và thực thi truy vấn |

Ví dụ điều kiện cố định:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Predicate paid = cb.equal(
    order.get("status"), OrderStatus.PAID);
Predicate notDeleted = cb.isNull(
    order.get("deletedAt"));

cq.select(order);
cq.where(cb.and(paid, notDeleted));
cq.orderBy(cb.desc(order.get("createdAt")),
           cb.desc(order.get("id")));

List<PurchaseOrder> result =
    entityManager.createQuery(cq).getResultList();
~~~

Query trên dùng **tên thuộc tính entity**, không phải tên cột. Nếu mapping đổi tên cột từ created_at sang placed_at nhưng thuộc tính Java vẫn là createdAt, Criteria không cần sửa.

### 5.1. AND/OR có ngữ nghĩa nhóm

Giả sử yêu cầu:

~~~text
tenant = 7
AND deletedAt IS NULL
AND status IN (PAID, DRAFT)
AND (customer.fullName LIKE keyword OR customer.email LIKE keyword)
~~~

Ta cần xây hai tầng:

~~~java
Predicate nameMatches = cb.like(
    cb.lower(customer.get("fullName")), pattern, '~');
Predicate emailMatches = cb.like(
    cb.lower(customer.get("email")), pattern, '~');

Predicate keywordGroup = cb.or(nameMatches, emailMatches);
predicates.add(keywordGroup);

cq.where(cb.and(predicates.toArray(Predicate[]::new)));
~~~

Nếu thay toàn bộ AND bằng OR:

~~~java
cq.where(cb.or(predicates.toArray(Predicate[]::new)));
~~~

thì bất kỳ bản ghi nào khớp keyword, hoặc chỉ khớp status, hoặc chỉ có deletedAt null đều có thể xuất hiện. Nghiêm trọng hơn, OR với tenant predicate có thể khiến dữ liệu tenant khác bị trả về. **Điều kiện bảo mật không bao giờ bị nới rộng bởi một OR do form tìm kiếm điều khiển**.

### 5.2. conjunction và disjunction

~~~java
Predicate alwaysTrue = cb.conjunction();
Predicate alwaysFalse = cb.disjunction();
~~~

- conjunction biểu thị TRUE khi chưa gắn điều kiện con.
- disjunction biểu thị FALSE khi chưa gắn điều kiện con.

Có thể dùng conjunction làm giá trị mặc định của một filter không được cung cấp; dùng disjunction cho yêu cầu tập giá trị được cung cấp nhưng rỗng và có nghĩa “không khớp gì”.

Tuy nhiên đừng chỉ thêm cb.conjunction() cho mọi filter không có dữ liệu nếu việc bỏ qua filter đơn giản, dễ đọc hơn. Một danh sách Predicate chỉ thêm khi có input hợp lệ thường là cách diễn đạt rõ ràng nhất.

## 6. Bộ lọc bằng nhau: enum và ID

### 6.1. Một trạng thái

~~~java
if (status != null) {
    predicates.add(
        cb.equal(root.get("status"), status));
}
~~~

### 6.2. Nhiều trạng thái

~~~java
if (filter.statuses() != null) {
    if (filter.statuses().isEmpty()) {
        predicates.add(cb.disjunction());
    } else {
        predicates.add(
            root.get("status").in(filter.statuses()));
    }
}
~~~

Predicate IN tương đương status = PAID OR status = DRAFT về ý nghĩa lọc tập giá trị. Đừng tạo một chuỗi HQL bằng cách nối trực tiếp các enum/string client truyền vào.

### 6.3. Tìm theo Customer ID

~~~java
if (filter.customerId() != null) {
    predicates.add(cb.equal(
        root.get("customer").get("id"),
        filter.customerId()
    ));
}
~~~

Đường dẫn root.get("customer").get("id") dựa trên association Java. Hibernate quyết định SQL có thể so sánh cột FK trực tiếp hay cần JOIN theo mapping và query. Không viết customer_id trong Criteria nếu đó không phải tên persistent attribute.

### 6.4. Lỗi dữ liệu đầu vào phải báo sớm

Một status không thuộc enum hợp lệ hoặc customer ID không thể parse phải được báo HTTP 400 (hoặc lỗi validation tương ứng), **không phải âm thầm bỏ filter**. Nếu client gửi status=PAIDDD mà server bỏ qua, một truy vấn tưởng hẹp có thể trả về rất nhiều dữ liệu.

## 7. Khoảng tiền và thời gian

### 7.1. Khoảng tiền bao gồm hai đầu

~~~java
if (filter.minAmount() != null) {
    predicates.add(cb.greaterThanOrEqualTo(
        root.<BigDecimal>get("totalAmount"),
        filter.minAmount()));
}

if (filter.maxAmount() != null) {
    predicates.add(cb.lessThanOrEqualTo(
        root.<BigDecimal>get("totalAmount"),
        filter.maxAmount()));
}
~~~

Nếu chỉ có minAmount, query có điều kiện >=. Nếu chỉ có maxAmount, query có điều kiện <=. Nếu có cả hai, kết quả là khoảng đóng.

Có thể dùng cb.between khi đủ hai đầu:

~~~java
cb.between(
    root.<BigDecimal>get("totalAmount"),
    filter.minAmount(),
    filter.maxAmount()
);
~~~

Nhưng hai predicate độc lập tiện hơn cho bộ lọc **mỗi đầu có thể vắng mặt**.

### 7.2. Không biến 0 thành thiếu giá trị

Giá trị minAmount=0 có nghĩa lọc totalAmount >= 0. Có thể nó không làm giảm nhiều dữ liệu, nhưng vẫn là yêu cầu hợp lệ và có thể có ý nghĩa nếu dữ liệu chứa tiền âm cho refund. Chỉ bỏ filter khi null, không khi equals(BigDecimal.ZERO).

### 7.3. Kiểm tra khoảng trước khi query

~~~java
if (filter.minAmount() != null
        && filter.maxAmount() != null
        && filter.minAmount().compareTo(
            filter.maxAmount()) > 0) {
    throw new IllegalArgumentException(
        "minAmount không được lớn hơn maxAmount");
}
~~~

Không phụ thuộc vào việc SQL tự trả tập rỗng khi min > max. Validation rõ ràng giúp client biết lỗi yêu cầu.

### 7.4. Khoảng thời gian nửa mở

~~~java
if (filter.createdFrom() != null) {
    predicates.add(cb.greaterThanOrEqualTo(
        root.<Instant>get("createdAt"),
        filter.createdFrom()));
}

if (filter.createdBefore() != null) {
    predicates.add(cb.lessThan(
        root.<Instant>get("createdAt"),
        filter.createdBefore()));
}
~~~

Khoảng [createdFrom, createdBefore) có đầu trái bao gồm, đầu phải loại trừ. Điều này phù hợp với việc lọc theo ngày:

~~~text
Từ 2026-11-01T00:00:00Z
Trước 2026-12-01T00:00:00Z
~~~

Nó tránh phải tự tạo “23:59:59.999999” vốn có thể sai theo precision của database.

Nếu người dùng chọn ngày theo múi giờ Việt Nam, tầng API nên chuyển đầu ngày theo Asia/Ho_Chi_Minh sang Instant với ZonedDateTime/ZoneId, rồi dùng Instant nhất quán. Không giả định một chuỗi ngày không có timezone luôn tương đương UTC.

## 8. Tìm kiếm từ khóa có hoặc không có giá trị

Một thanh tìm kiếm tên/email có thể dùng LIKE và OR:

~~~java
String text = filter.keyword() == null
    ? null
    : filter.keyword().strip();

if (text != null && !text.isBlank()) {
    Join<PurchaseOrder, Customer> customer =
        root.join("customer", JoinType.INNER);

    String pattern = "%" + escapeLike(
        text.toLowerCase(Locale.ROOT)) + "%";

    Predicate byName = cb.like(
        cb.lower(customer.<String>get("fullName")),
        pattern,
        '~');

    Predicate byEmail = cb.like(
        cb.lower(customer.<String>get("email")),
        pattern,
        '~');

    predicates.add(cb.or(byName, byEmail));
}
~~~

Giá trị text chỉ được đưa vào predicate nếu có nội dung. Nếu keyword null/blank, không tạo JOIN Customer chỉ để phục vụ keyword, và không thêm điều kiện LIKE %%.

### 8.1. Vì sao cần escape %, _ và ký tự escape?

Trong SQL LIKE:

- % khớp một chuỗi ký tự bất kỳ.
- _ khớp một ký tự bất kỳ.

Nếu người dùng tìm đúng chuỗi "50%" mà code đặt pattern "%50%%", ký tự % của người dùng bị hiểu là wildcard. Có thể tránh bằng cách chọn ký tự escape ~:

~~~java
private static String escapeLike(String value) {
    return value
        .replace("~", "~~")
        .replace("%", "~%")
        .replace("_", "~_");
}
~~~

Khi gọi cb.like(expression, pattern, '~'), CriteriaBuilder tạo LIKE với escape character phù hợp. Ví dụ input "50%" trở thành pattern chứa "~%" cho phần dấu phần trăm literal.

Việc dùng bound value của CriteriaBuilder giúp tránh nối trực tiếp SQL và giảm nguy cơ injection. Escape wildcard là yêu cầu khác: **bind parameter không tự biến % và _ thành ký tự literal**.

### 8.2. Case insensitive có phụ thuộc database

cb.lower(column) kết hợp text.toLowerCase(Locale.ROOT) là cách tìm không phân biệt chữ hoa/thường đơn giản. Nhưng lower-casing, collation và các ký tự Unicode đặc biệt có thể khác giữa Java và database. Với tìm kiếm văn bản phức tạp, cân nhắc collation, case-folding, unaccent, full-text search hoặc search index được thiết kế riêng.

LOWER(column) cũng có thể làm database khó dùng index B-tree thông thường cho điều kiện LIKE bắt đầu bằng %. PostgreSQL có thể cần functional index/trigram index tùy workload. Đừng kết luận query động tự động tối ưu chỉ vì sử dụng Criteria API.

## 9. Bộ lọc theo collection: EXISTS thay vì JOIN làm nhân bản parent

Yêu cầu: “Chỉ hiển thị đơn chứa ít nhất một sản phẩm có ID trong tập productIds”.

Một cách dễ viết:

~~~java
Join<PurchaseOrder, OrderItem> item =
    root.join("items", JoinType.INNER);
predicates.add(
    item.get("product").get("id").in(productIds));
~~~

Tuy nhiên, một PurchaseOrder có nhiều OrderItem khớp điều kiện sẽ xuất hiện **nhiều hàng SQL**. Điều này ảnh hưởng phân trang parent và count query.

Nếu chỉ cần kiểm tra **tồn tại ít nhất một child**, correlated EXISTS diễn đạt rõ hơn:

~~~java
Subquery<Long> sq = query.subquery(Long.class);
Root<OrderItem> item = sq.from(OrderItem.class);

sq.select(cb.literal(1L));
sq.where(
    cb.equal(item.get("order"), root),
    item.get("product").get("id").in(productIds)
);

predicates.add(cb.exists(sq));
~~~

EXISTS không làm nhân bản PurchaseOrder ở kết quả ngoài. Hibernate dịch câu Criteria này thành SQL EXISTS với điều kiện liên kết order ID tương ứng.

### 9.1. Collection rỗng cần policy rõ ràng

~~~java
if (filter.productIds() != null) {
    if (filter.productIds().isEmpty()) {
        predicates.add(cb.disjunction());
    } else {
        // Bổ sung correlated EXISTS.
    }
}
~~~

Theo policy đang chọn, productIds được cung cấp nhưng rỗng nghĩa là không có sản phẩm nào có thể khớp, nên trả tập rỗng. Nếu API muốn xem [] là “không áp dụng filter”, hãy thay quy tắc ngay ở input boundary và viết test tương ứng.

### 9.2. Bộ lọc hasItems có ba trạng thái

~~~java
if (filter.hasItems() != null) {
    Subquery<Long> sq = query.subquery(Long.class);
    Root<OrderItem> item = sq.from(OrderItem.class);

    sq.select(cb.literal(1L));
    sq.where(cb.equal(item.get("order"), root));

    Predicate hasAtLeastOne = cb.exists(sq);
    predicates.add(filter.hasItems()
        ? hasAtLeastOne
        : cb.not(hasAtLeastOne));
}
~~~

- hasItems=null: không lọc theo số item.
- hasItems=true: chỉ đơn có ít nhất một OrderItem.
- hasItems=false: chỉ đơn không có OrderItem.

Đây là ví dụ rõ nhất về lý do không dùng Boolean primitive hoặc chỉ kiểm tra Boolean.TRUE.

### 9.3. Có nhiều bộ lọc collection độc lập?

Giả sử cần:

~~~text
Order có Product ID thuộc tập A
AND Order có ít nhất một item thuộc category B
~~~

Hai EXISTS độc lập có nghĩa có thể là **hai item khác nhau** cùng thỏa mỗi vế. Nếu yêu cầu là **cùng một item** vừa thuộc Product A vừa thuộc category B, phải đặt cả hai điều kiện trong **cùng một subquery EXISTS**.

Ví dụ:

~~~java
sq.where(
    cb.equal(item.get("order"), root),
    item.get("product").get("id").in(productIds),
    cb.equal(item.get("product").get("category"), category)
);
~~~

Đây là khác biệt nghiệp vụ quan trọng khi kết hợp bộ lọc trên collection.

## 10. Ghép các nhóm Predicate đúng ngữ nghĩa

Giả sử API nhận:

~~~text
tenant = 7 (bắt buộc)
statuses = [PAID, DRAFT]
minAmount = 100
keyword = "linh"
hasItems = false
~~~

Điều kiện cần là:

~~~text
tenant = 7
AND deletedAt IS NULL
AND status IN (PAID, DRAFT)
AND totalAmount >= 100
AND (
  lower(customer.fullName) LIKE '%linh%'
  OR lower(customer.email) LIKE '%linh%'
)
AND NOT EXISTS (order items)
~~~

Trong Criteria, mỗi filter đóng góp **một predicate hoặc một nhóm predicate** vào danh sách chung; cuối cùng dùng AND:

~~~java
List<Predicate> conditions = new ArrayList<>();

conditions.add(mandatoryTenant);
conditions.add(notDeleted);

if (hasStatuses) {
    conditions.add(statusGroup);
}
if (hasKeyword) {
    conditions.add(cb.or(nameMatches, emailMatches));
}
if (hasMinimum) {
    conditions.add(minimumAmount);
}
if (hasItemsChoice) {
    conditions.add(itemPresence);
}

query.where(cb.and(
    conditions.toArray(Predicate[]::new)));
~~~

Sơ đồ:

~~~mermaid
flowchart TD
    A[Input filters] --> B[Normalize + validate]
    B --> C[Luôn thêm tenant và deletedAt]
    C --> D{Keyword hợp lệ?}
    D -->|Có| E[Thêm nhóm OR: name hoặc email]
    D -->|Không| F[Bỏ nhóm keyword]
    E --> G[Thêm status, amount, date nếu có]
    F --> G
    G --> H{productIds / hasItems?}
    H -->|Có| I[Thêm EXISTS / NOT EXISTS]
    H -->|Không| J[Không có predicate collection]
    I --> K[AND tất cả các nhóm]
    J --> K
    K --> L[Thực thi query và count cùng ngữ nghĩa]
~~~

### 10.1. Phân biệt AND của các nhóm và OR trong một nhóm

Cần:

~~~text
status=PAID AND (emailContains="a" OR nameContains="a")
~~~

Không phải:

~~~text
(status=PAID AND emailContains="a") OR nameContains="a"
~~~

Hai biểu thức khác nhau. Biểu thức thứ hai trả cả những Customer có tên khớp từ khóa dù status không phải PAID. Khi một filter có nhiều cách match, tạo OR trước, rồi thêm predicate OR đó vào AND toàn cục.

### 10.2. Nếu người dùng muốn “bất kỳ điều kiện nào”

Đó là một query mode khác, ví dụ:

~~~text
(status=PAID OR totalAmount>=1000)
AND tenant=7
AND deletedAt IS NULL
~~~

Đừng thay AND toàn query thành OR. Hãy tạo nhóm userCriteria bằng cb.or(...), rồi kết hợp với ràng buộc bắt buộc bằng cb.and(tenantPredicate, activePredicate, userCriteria).

## 11. Xây một bộ lọc Criteria tái sử dụng giữa content query và count query

Một sai lầm phổ biến là query lấy dữ liệu áp dụng 7 bộ lọc nhưng query COUNT chỉ áp dụng 5 bộ lọc. Kết quả là UI báo 500 đơn trong khi danh sách thực sự chỉ khớp 18 đơn.

Giải pháp: tái sử dụng **logic tạo Predicate** trên từng Root/CriteriaQuery mới, không tái sử dụng chính các instance Predicate của query trước.

### 11.1. Bộ dựng Predicate đầy đủ

~~~java
import jakarta.persistence.criteria.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class OrderPredicates {
    private OrderPredicates() {}

    public static List<Predicate> build(
            CriteriaBuilder cb,
            AbstractQuery<?> query,
            Root<PurchaseOrder> root,
            OrderSearchFilter filter,
            Long tenantId) {

        List<Predicate> predicates = new ArrayList<>();

        // Bắt buộc và không điều khiển bởi filter từ client.
        predicates.add(cb.equal(root.get("tenantId"), tenantId));
        predicates.add(cb.isNull(root.get("deletedAt")));

        if (filter.customerId() != null) {
            predicates.add(cb.equal(
                root.get("customer").get("id"),
                filter.customerId()));
        }

        if (filter.statuses() != null) {
            if (filter.statuses().isEmpty()) {
                predicates.add(cb.disjunction());
            } else {
                predicates.add(
                    root.get("status").in(filter.statuses()));
            }
        }

        if (filter.minAmount() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                root.<BigDecimal>get("totalAmount"),
                filter.minAmount()));
        }
        if (filter.maxAmount() != null) {
            predicates.add(cb.lessThanOrEqualTo(
                root.<BigDecimal>get("totalAmount"),
                filter.maxAmount()));
        }

        if (filter.createdFrom() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                root.<Instant>get("createdAt"),
                filter.createdFrom()));
        }
        if (filter.createdBefore() != null) {
            predicates.add(cb.lessThan(
                root.<Instant>get("createdAt"),
                filter.createdBefore()));
        }

        String keyword = filter.keyword() == null
            ? null : filter.keyword().strip();
        if (keyword != null && !keyword.isBlank()) {
            Join<PurchaseOrder, Customer> customer =
                root.join("customer", JoinType.INNER);

            String pattern = "%" + escapeLike(
                keyword.toLowerCase(Locale.ROOT)) + "%";

            Predicate byName = cb.like(
                cb.lower(customer.<String>get("fullName")),
                pattern, '~');
            Predicate byEmail = cb.like(
                cb.lower(customer.<String>get("email")),
                pattern, '~');
            predicates.add(cb.or(byName, byEmail));
        }

        if (filter.productIds() != null) {
            if (filter.productIds().isEmpty()) {
                predicates.add(cb.disjunction());
            } else {
                Subquery<Long> byProduct =
                    query.subquery(Long.class);
                Root<OrderItem> item =
                    byProduct.from(OrderItem.class);
                byProduct.select(cb.literal(1L));
                byProduct.where(
                    cb.equal(item.get("order"), root),
                    item.get("product").get("id")
                        .in(filter.productIds()));
                predicates.add(cb.exists(byProduct));
            }
        }

        if (filter.hasItems() != null) {
            Subquery<Long> withItems =
                query.subquery(Long.class);
            Root<OrderItem> item =
                withItems.from(OrderItem.class);
            withItems.select(cb.literal(1L));
            withItems.where(
                cb.equal(item.get("order"), root));

            Predicate exists = cb.exists(withItems);
            predicates.add(filter.hasItems()
                ? exists
                : cb.not(exists));
        }

        return predicates;
    }

    private static String escapeLike(String value) {
        return value
            .replace("~", "~~")
            .replace("%", "~%")
            .replace("_", "~_");
    }
}
~~~

Điểm quan trọng:

- Các field tùy chọn được kiểm tra null **độc lập**.
- keyword chỉ sinh JOIN khi có từ khóa thực sự.
- statuses/productIds rỗng sinh FALSE theo policy đã chọn.
- minAmount=0 và hasItems=false vẫn được áp dụng.
- EXISTS trên OrderItem giúp parent không bị nhân bản bởi collection join.
- Tenant và soft delete được thêm bất kể filter nào có mặt.
- Phương thức nhận AbstractQuery<?> để có thể tạo subquery cho cả query dữ liệu và query COUNT.

Một số hệ quản trị hoặc mapping có thể sinh SQL join khác nhau cho customer ID/path expression. Chạy SQL log trên Hibernate version mục tiêu để quan sát chứ không dựa vào hình dạng SQL giả định.

### 11.2. Tại sao truyền cả query vào bộ dựng?

Subquery gắn với query cha:

~~~java
Subquery<Long> sq = query.subquery(Long.class);
~~~

Một predicate EXISTS phải tham chiếu đúng Root của query cha. Không thể xây sẵn một Predicate, rồi tái sử dụng nó nguyên vẹn cho một CriteriaQuery khác có Root khác mà mong provider tự sửa quan hệ.

**Tái sử dụng mã xây điều kiện, không tái sử dụng object Predicate/Path/Root giữa các CriteriaQuery độc lập.**

## 12. Content query, count query, sorting và paging

Ta tạo search service dùng chung OrderPredicates:

~~~java
import jakarta.persistence.*;
import jakarta.persistence.criteria.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderRow(
    Long id,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt
) {}

public record SearchPage<T>(
    List<T> content,
    long totalElements,
    int page,
    int size
) {}
~~~

Trong project Java, hai public record ở trên nằm trong hai source file riêng. Tiếp theo là service:

~~~java
@Service
public class OrderCriteriaSearch {
    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public SearchPage<OrderRow> search(
            Long authenticatedTenantId,
            OrderSearchFilter request,
            int page,
            int size,
            String sortField) {

        OrderSearchFilter f = request == null
            ? OrderSearchFilter.empty()
            : request;
        validate(f, page, size, authenticatedTenantId);

        CriteriaBuilder cb = em.getCriteriaBuilder();

        // Query nội dung.
        CriteriaQuery<PurchaseOrder> cq =
            cb.createQuery(PurchaseOrder.class);
        Root<PurchaseOrder> root =
            cq.from(PurchaseOrder.class);

        List<Predicate> conditions = OrderPredicates.build(
            cb, cq, root, f, authenticatedTenantId);

        cq.select(root);
        cq.where(cb.and(
            conditions.toArray(Predicate[]::new)));
        cq.orderBy(sortOrders(cb, root, sortField));

        int first = Math.toIntExact((long) page * size);
        List<PurchaseOrder> entities = em.createQuery(cq)
            .setFirstResult(first)
            .setMaxResults(size)
            .getResultList();

        // Query COUNT có Root/Predicate riêng.
        CriteriaQuery<Long> countQuery =
            cb.createQuery(Long.class);
        Root<PurchaseOrder> countRoot =
            countQuery.from(PurchaseOrder.class);

        List<Predicate> countConditions =
            OrderPredicates.build(
                cb, countQuery, countRoot,
                f, authenticatedTenantId);

        countQuery.select(cb.count(countRoot));
        countQuery.where(cb.and(
            countConditions.toArray(Predicate[]::new)));

        long total = em.createQuery(countQuery)
            .getSingleResult();

        List<OrderRow> content = entities.stream()
            .map(o -> new OrderRow(
                o.getId(),
                o.getStatus(),
                o.getTotalAmount(),
                o.getCreatedAt()))
            .toList();

        return new SearchPage<>(content, total, page, size);
    }

    private static List<Order> sortOrders(
            CriteriaBuilder cb,
            Root<PurchaseOrder> root,
            String sortField) {

        return switch (sortField == null
                ? "newest" : sortField) {
            case "amountHigh" -> List.of(
                cb.desc(root.get("totalAmount")),
                cb.desc(root.get("id")));
            case "amountLow" -> List.of(
                cb.asc(root.get("totalAmount")),
                cb.asc(root.get("id")));
            case "oldest" -> List.of(
                cb.asc(root.get("createdAt")),
                cb.asc(root.get("id")));
            case "newest" -> List.of(
                cb.desc(root.get("createdAt")),
                cb.desc(root.get("id")));
            default -> throw new IllegalArgumentException(
                "sortField không được hỗ trợ");
        };
    }

    private static void validate(
            OrderSearchFilter f,
            int page,
            int size,
            Long tenantId) {

        if (tenantId == null) {
            throw new IllegalArgumentException(
                "Không xác định được tenant hiện tại");
        }
        if (page < 0 || size < 1 || size > 100
                || (long) page * size > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Phân trang không hợp lệ");
        }
        if (f.minAmount() != null && f.maxAmount() != null
                && f.minAmount().compareTo(f.maxAmount()) > 0) {
            throw new IllegalArgumentException(
                "minAmount phải nhỏ hơn hoặc bằng maxAmount");
        }
        if (f.createdFrom() != null
                && f.createdBefore() != null
                && !f.createdFrom().isBefore(
                    f.createdBefore())) {
            throw new IllegalArgumentException(
                "createdFrom phải trước createdBefore");
        }
    }
}
~~~

Các import cho OrderStatus, PurchaseOrder, OrderSearchFilter, SearchPage và OrderRow phụ thuộc package của dự án.

### 12.1. Vì sao sorting phải có whitelist?

Request có thể gửi "newest", "amountHigh", "amountLow" hoặc "oldest"; service ánh xạ thành **persistent attributes đã được cho phép**. Không lấy chuỗi user input rồi đưa trực tiếp vào root.get(sortField) hoặc nối thành ORDER BY tùy ý. Chuỗi sai có thể gây lỗi lúc chạy; một số API cho phép truy cập thuộc tính mà sản phẩm không muốn công khai.

Mỗi sort thêm ID làm tie-breaker để các hàng có cùng createdAt/totalAmount vẫn có thứ tự ổn định.

### 12.2. Count query dùng cùng logic lọc

Nếu query dữ liệu áp dụng một EXISTS để lọc productIds, count query phải áp dụng cùng EXISTS đó. Ngược lại, tổng số trang sẽ sai.

Vì bộ dựng dùng hai Root riêng nhưng cùng filter:

~~~java
OrderPredicates.build(cb, cq, root, f, tenantId);
OrderPredicates.build(cb, countQuery, countRoot, f, tenantId);
~~~

ta giảm nguy cơ lệch điều kiện. **Đừng copy object Predicate** từ cq sang countQuery; hãy dựng mới.

### 12.3. Vì sao COUNT không cần DISTINCT trong ví dụ?

Query ngoài không JOIN collection OrderItem; bộ lọc productIds/hasItems dùng EXISTS. Join Customer là quan hệ ManyToOne, mỗi Order chỉ có một Customer. Vì vậy các hàng PurchaseOrder không bị nhân bản trong query ngoài, nên cb.count(countRoot) đếm số đơn đúng.

Nếu sau này bổ sung JOIN collection ở query ngoài, phải xét lại root duplicates, DISTINCT, countDistinct và pagination. Không thêm cb.distinct(true) như một miếng vá chung mà chưa hiểu cardinality.

### 12.4. Count có thể là câu query đắt

Page<T> thường cần totalElements và totalPages; COUNT trên nhiều EXISTS hoặc filter phức tạp có thể tốn đáng kể chi phí. Nếu UI chỉ cần “còn trang tiếp theo không”, có thể sử dụng Slice hoặc lấy size+1 hàng thay vì luôn COUNT. Nhưng không được dùng Slice để bỏ qua những ràng buộc lọc hoặc đổi semantics.

### 12.5. Hai query không mặc nhiên cùng snapshot

Ở PostgreSQL READ COMMITTED, content query và count query trong cùng transaction có thể thấy dữ liệu khác nhau nếu transaction khác commit giữa hai statement. Ví dụ một đơn vừa được tạo có thể xuất hiện trong count nhưng không có trong content.

Với màn hình danh sách thông thường, chênh lệch nhỏ có thể chấp nhận; với báo cáo tài chính yêu cầu snapshot nhất quán, phải xác định isolation hoặc read model phù hợp. @Transactional(readOnly=true) không tự tạo snapshot giống nhau cho mọi statement trong READ COMMITTED.

## 13. Khi nào dùng Criteria API, khi nào dùng HQL điều kiện tĩnh?

Có một phương án thường gặp:

~~~hql
select o
from PurchaseOrder o
where (:status is null or o.status = :status)
  and (:minAmount is null or o.totalAmount >= :minAmount)
~~~

Ý tưởng là một câu HQL cố định chứa mọi bộ lọc. Nó có thể phù hợp với màn hình nhỏ, ít điều kiện. Nhưng:

- Query luôn có những OR liên quan parameter, kể cả khi filter không xuất hiện.
- Optimizer/database có thể tạo plan khác so với một predicate được bỏ hoàn toàn, tùy prepared statement và parameter selectivity.
- Nhiều bộ lọc phức tạp như EXISTS/keyword OR dễ làm câu HQL dài khó đọc.
- Enum, null và collection parameters vẫn cần policy cụ thể.
- Điều kiện bảo mật phải luôn được giữ độc lập với OR tùy chọn.

Criteria xây query động sẽ **chỉ thêm các predicate đã có input hợp lệ**, giúp SQL được diễn đạt gần với mục tiêu thực tế của từng request. Tuy nhiên nhiều dạng query khác nhau cũng có trade-off về plan cache/compilation; không thể khẳng định Criteria luôn nhanh hơn HQL tĩnh.

### 13.1. Criteria API và native SQL

Criteria dùng entity/attribute model và giúp truyền giá trị được bind, giảm phụ thuộc tên bảng/cột. Native SQL phù hợp khi cần tính năng PostgreSQL phức tạp hoặc query reporting được tối ưu đặc biệt. Nhưng native SQL vẫn phải kiểm soát optional inputs, parameter binding, tenant predicate và quyền truy cập như nhau.

### 13.2. Không dùng string concatenation cho giá trị người dùng

Không viết:

~~~java
String hql = "from PurchaseOrder o where o.status = '"
    + inputStatus + "'";
~~~

Ghép giá trị trực tiếp vào query tăng rủi ro injection và lỗi escaping. CriteriaBuilder nhận giá trị làm biểu thức được Hibernate xử lý an toàn theo mapping. Đối với các phần identifier như sort field, vẫn phải dùng whitelist vì không thể bind một tên thuộc tính như bind value.

## 14. Spring Data JPA Specification: đóng gói mỗi bộ lọc thành một thành phần

Nếu dự án dùng Spring Data JPA, có thể tái sử dụng Criteria API qua Specification.

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface PurchaseOrderRepository
    extends JpaRepository<PurchaseOrder, Long>,
            JpaSpecificationExecutor<PurchaseOrder> {
}
~~~

Mỗi Specification là một hàm tạo Predicate:

~~~java
import org.springframework.data.jpa.domain.Specification;
import java.math.BigDecimal;
import java.time.Instant;

public final class OrderSpecs {
    private OrderSpecs() {}

    public static Specification<PurchaseOrder> inTenant(
            Long tenantId) {
        return (root, query, cb) ->
            cb.equal(root.get("tenantId"), tenantId);
    }

    public static Specification<PurchaseOrder> notDeleted() {
        return (root, query, cb) ->
            cb.isNull(root.get("deletedAt"));
    }

    public static Specification<PurchaseOrder> withStatus(
            OrderStatus status) {
        return (root, query, cb) -> status == null
            ? null
            : cb.equal(root.get("status"), status);
    }

    public static Specification<PurchaseOrder> atLeast(
            BigDecimal minimum) {
        return (root, query, cb) -> minimum == null
            ? null
            : cb.greaterThanOrEqualTo(
                root.<BigDecimal>get("totalAmount"),
                minimum);
    }

    public static Specification<PurchaseOrder> before(
            Instant upperExclusive) {
        return (root, query, cb) -> upperExclusive == null
            ? null
            : cb.lessThan(
                root.<Instant>get("createdAt"),
                upperExclusive);
    }
}
~~~

Trong Spring Data JPA, Specification có thể trả null Predicate để đại diện “không đóng góp điều kiện” khi ghép các Specification cho truy vấn SELECT. Tùy version, API có thể có helper như unrestricted(); hãy theo tài liệu phiên bản Spring Data sử dụng.

### 14.1. Kết hợp Specification bằng AND

~~~java
Specification<PurchaseOrder> spec =
    Specification.allOf(
        OrderSpecs.inTenant(authenticatedTenantId),
        OrderSpecs.notDeleted(),
        OrderSpecs.withStatus(status),
        OrderSpecs.atLeast(minAmount),
        OrderSpecs.before(createdBefore)
    );

Page<PurchaseOrder> page =
    repository.findAll(spec, pageable);
~~~

Đây là cách diễn đạt:

~~~text
tenantId = currentTenant
AND deletedAt IS NULL
AND (status nếu có)
AND (minAmount nếu có)
AND (createdBefore nếu có)
~~~

Nếu Spring Data version của dự án không có overload allOf dạng varargs, có thể dùng allOf(Collection) hoặc kết hợp bằng and() theo API version. Các method nhận null vẫn phải giữ đúng ngữ nghĩa vắng mặt.

### 14.2. Kết hợp Specification bằng OR có ngoặc

~~~java
Specification<PurchaseOrder> optionalAny =
    Specification.anyOf(
        OrderSpecs.withStatus(status),
        OrderSpecs.atLeast(minAmount)
    );

Specification<PurchaseOrder> secured =
    Specification.allOf(
        OrderSpecs.inTenant(authenticatedTenantId),
        OrderSpecs.notDeleted(),
        optionalAny
    );
~~~

Ý định là (status match OR amount match) **trong phạm vi tenant + notDeleted**. Nếu cả hai filter tùy chọn đều vắng mặt, phải xác định policy query: trả dữ liệu trong tenant, trả tập rỗng, hay yêu cầu ít nhất một điều kiện. Việc Specification trả null hay unrestricted có thể ảnh hưởng kết quả kết hợp allOf/anyOf theo phiên bản; kiểm thử riêng kịch bản “không có filter” thay vì giả định.

Trong ví dụ API của bài, tìm kiếm mặc định dùng AND giữa các tiêu chí được cung cấp. OR chỉ dùng để ghép những cách match trong cùng một nhóm như keyword name/email.

### 14.3. Specification có bộ lọc collection

~~~java
public static Specification<PurchaseOrder> hasAnyProduct(
        Set<Long> productIds) {
    return (root, query, cb) -> {
        if (productIds == null) {
            return null;
        }
        if (productIds.isEmpty()) {
            return cb.disjunction();
        }

        Subquery<Long> sq = query.subquery(Long.class);
        Root<OrderItem> item = sq.from(OrderItem.class);
        sq.select(cb.literal(1L));
        sq.where(
            cb.equal(item.get("order"), root),
            item.get("product").get("id").in(productIds)
        );
        return cb.exists(sq);
    };
}
~~~

Chúng ta vẫn chọn EXISTS để không làm nhân bản PurchaseOrder trong câu query ngoài.

### 14.4. Cẩn thận với fetch join trong Specification

Một số ví dụ trên Internet thêm:

~~~java
root.fetch("items", JoinType.LEFT);
~~~

vào Specification rồi gọi repository.findAll(spec, pageable). Với quan hệ collection:

- Fetch join có thể khiến Hibernate phải phân trang trong bộ nhớ hoặc báo lỗi tùy cấu hình.
- Count query do Spring Data tạo không thể áp dụng fetch collection như query entity; fetch owner có thể không hiện diện trong SELECT của COUNT.
- Query content và count có thể có shape khác nhau, khiến code “chỉ thêm fetch” gây exception.

**Không dùng fetch collection trong Specification phân trang một cách mặc định.** Nếu cần items, phân trang Order ID trước rồi fetch đúng các Order theo ID, dùng batch fetch, hoặc trả DTO chỉ chứa các trường cần hiển thị. Đừng đổi sang EAGER cho toàn bộ collection chỉ để tránh lazy query.

## 15. Tìm kiếm OR giữa nhiều trường và join cho optional filter

Keyword có thể khớp:

~~~text
customer.fullName chứa "an"
OR customer.email chứa "an"
OR order.externalReference chứa "an"
~~~

Một Specification:

~~~java
public static Specification<PurchaseOrder> keyword(
        String rawKeyword) {
    return (root, query, cb) -> {
        String text = rawKeyword == null
            ? null : rawKeyword.strip();
        if (text == null || text.isBlank()) {
            return null;
        }

        String pattern = "%" + text
            .toLowerCase(Locale.ROOT) + "%";
        Join<PurchaseOrder, Customer> customer =
            root.join("customer", JoinType.INNER);

        return cb.or(
            cb.like(
                cb.lower(customer.<String>get("fullName")),
                pattern),
            cb.like(
                cb.lower(customer.<String>get("email")),
                pattern)
        );
    };
}
~~~

Đây là phiên bản đơn giản để giải thích cách nhóm OR. Trong production, dùng hàm escapeLike cùng escape character như phần trước nếu muốn tìm literal %, _; không để chuỗi người dùng vô tình thay đổi semantics wildcard.

Nếu customer là quan hệ optional và muốn cho phép tìm theo externalReference ngay cả khi đơn không có customer, một INNER JOIN sẽ loại những đơn không có customer trước khi OR được đánh giá. Khi đó nên dùng LEFT JOIN và nhóm OR đúng cách.

**Chọn loại JOIN dựa trên yêu cầu toàn bộ predicate**, không chỉ dựa vào một field đang được kiểm tra.

## 16. Bộ lọc “không có giá trị” khác bộ lọc “có giá trị NULL trong DB”

Một trường ngày xóa có thể dùng hai nhu cầu:

1. Không lọc deletedAt.
2. Chỉ lấy entity có deletedAt IS NULL.
3. Chỉ lấy entity có deletedAt IS NOT NULL.

Nếu chỉ dùng Instant deletedAtFilter với null = “không lọc”, ta **không thể** dùng null đó để biểu diễn “tìm những bản ghi có deletedAt NULL”.

Một thiết kế rõ hơn là operator enum:

~~~java
public enum PresenceFilter {
    ANY, PRESENT, MISSING
}
~~~

~~~java
static Predicate byPresence(
        CriteriaBuilder cb,
        Path<?> path,
        PresenceFilter mode) {

    if (mode == null || mode == PresenceFilter.ANY) {
        return cb.conjunction();
    }
    return mode == PresenceFilter.PRESENT
        ? cb.isNotNull(path)
        : cb.isNull(path);
}
~~~

Với optional association, có thể dùng PRESENT/MISSING để tìm có hoặc không có liên kết, nếu mapping cho phép FK nullable và business requirement có ý nghĩa.

Đừng vô tình bỏ qua yêu cầu “tìm các hàng chưa có giá trị” chỉ vì code kiểm tra input null để bỏ filter. Trong API, **vắng mặt của bộ lọc** và **toán tử IS NULL** phải là hai khái niệm khác nhau.

## 17. Từ dữ liệu form tới filter object: nên chuẩn hóa ở ranh giới API

Không nên để database query builder chịu trách nhiệm phân biệt mọi cách client biểu diễn input. Một lớp request mapper/validator nên:

1. Parse enum từ giá trị hợp lệ, không silently ignore invalid value.
2. Trim/normalize keyword theo contract.
3. Phân biệt không truyền statuses và truyền tập rỗng nếu API yêu cầu.
4. Parse BigDecimal không dùng double cho tiền.
5. Parse ngày cùng timezone rõ ràng, chuyển thành Instant.
6. Kiểm tra min <= max và from < before.
7. Giới hạn kích thước page, số phần tử trong productIds và độ dài keyword.
8. Không nhận tenantId từ request làm authority.
9. Chuẩn hóa sort key thành một enum hoặc whitelist.

Ví dụ endpoint:

~~~text
GET /api/orders?statuses=PAID,DRAFT&minAmount=100
GET /api/orders?keyword=linh&hasItems=false
GET /api/orders?createdFrom=2026-11-01T00:00:00Z
GET /api/orders?page=2&size=20&sortField=amountHigh
~~~

Đây là contract minh họa; cách bind query params thành Set<Enum> hay Boolean phụ thuộc Spring MVC/controller. Controller nên trả lỗi validation rõ ràng khi giá trị không hợp lệ trước khi gọi repository.

### 17.1. Filter không được tự “thả lỏng” khi parse lỗi

Sai:

~~~java
try {
    status = OrderStatus.valueOf(rawStatus);
} catch (Exception ignored) {
    status = null;
}
~~~

Một lỗi chính tả trong status làm filter biến mất và query trở nên rộng hơn mong đợi. Hãy trả thông báo “status không hợp lệ” thay vì bỏ điều kiện.

### 17.2. Giới hạn keyword và tập ID

Ngay cả khi parameter binding an toàn, người dùng có thể gửi keyword rất dài hoặc IN chứa hàng chục nghìn ID để làm tăng chi phí. Giới hạn có thể gồm:

- keyword tối đa số ký tự hợp lý theo UX.
- productIds tối đa số phần tử theo SLA.
- page size tối đa 100 hoặc ngưỡng đã đo.
- số tổ hợp OR/AND phức tạp được cho phép.
- timeout/rate-limit cho báo cáo tốn kém.

Giới hạn phải phù hợp domain và tải thực tế; con số minh họa không phải yêu cầu chung của Hibernate.

## 18. Kết quả query khi mọi bộ lọc tùy chọn đều vắng mặt

Giả sử request không có keyword, customerId, statuses, amount, time, productIds và hasItems. Với policy trong bài, kết quả là:

~~~hql
select o
from PurchaseOrder o
where o.tenantId = :currentTenant
  and o.deletedAt is null
order by o.createdAt desc, o.id desc
~~~

Không phải:

~~~hql
select o
from PurchaseOrder o
~~~

Vì tenant và soft delete là ràng buộc bắt buộc. Một API cũng có thể đặt policy “phải có ít nhất một tiêu chí” để bảo vệ hệ thống khỏi truy vấn quá rộng; khi đó validate và trả lỗi trước khi query, chứ không tự động biến mọi filter rỗng thành một predicate ngẫu nhiên.

### 18.1. Ví dụ các tổ hợp

| Input | Predicate bổ sung |
|---|---|
| Không có filter tùy chọn | Không bổ sung; vẫn giữ tenant/soft delete |
| status=PAID | status = PAID |
| minAmount=0 | totalAmount >= 0 |
| keyword="   " | Không bổ sung keyword |
| keyword="linh" | lower(name) LIKE ... OR lower(email) LIKE ... |
| statuses=[] | FALSE theo policy |
| productIds=[] | FALSE theo policy |
| hasItems=true | EXISTS OrderItem |
| hasItems=false | NOT EXISTS OrderItem |
| createdFrom có, createdBefore null | createdAt >= from |
| createdFrom null, createdBefore có | createdAt < before |
| statuses=[PAID,DRAFT], minAmount=100 | status IN (...) AND totalAmount >= 100 |

Đây là ma trận quan trọng để tránh phụ thuộc ngẫu nhiên vào truthiness hay cách framework deserialize query parameter.

## 19. Một số lỗi thường gặp với Criteria động

### 19.1. Luôn JOIN to-many dù filter không dùng

Sai:

~~~java
Join<PurchaseOrder, OrderItem> items =
    root.join("items", JoinType.INNER);

if (filter.productIds() != null) {
    predicates.add(
        items.get("product").get("id")
            .in(filter.productIds()));
}
~~~

Khi productIds=null, INNER JOIN vẫn loại mọi đơn không có item và có thể nhân bản đơn có nhiều item. Nghĩa là một filter “vắng mặt” đã âm thầm thay đổi tập kết quả.

Đúng hơn: chỉ tạo JOIN khi cần, hoặc dùng EXISTS khi muốn lọc theo sự tồn tại của child.

### 19.2. Gọi root.get với tên cột database

Sai:

~~~java
root.get("total_amount")
~~~

nếu persistent attribute là totalAmount. Criteria sử dụng model Java:

~~~java
root.get("totalAmount")
~~~

### 19.3. Nhầm Predicate OR và AND

Sai:

~~~java
cb.or(tenantPredicate, statusPredicate)
~~~

vì status có thể khớp đơn của tenant khác. Đúng là AND(tenantPredicate, các nhóm optional), OR chỉ được đặt bên trong nhóm do nghiệp vụ định nghĩa.

### 19.4. So sánh bằng equal với null

~~~java
cb.equal(root.get("deletedAt"), null)
~~~

không phải cách rõ ràng để kiểm tra NULL. Dùng:

~~~java
cb.isNull(root.get("deletedAt"))
~~~

### 19.5. Dùng list rỗng mà không xác định semantics

IN rỗng có hành vi khác nhau tùy provider/dialect hoặc được framework xử lý riêng. Xử lý rỗng ở filter builder bằng cb.disjunction() hoặc validation theo contract; không dựa vào SQL do Hibernate tự chọn khi IN không có phần tử.

### 19.6. Tạo Predicate cho query khác rồi tái sử dụng

Root của content query không giống Root của count query. Cần chạy lại cùng logic builder trên từng query, không copy Predicate giữa chúng.

### 19.7. Đọc entity LAZY sau khi transaction đã đóng

Content query có thể trả PurchaseOrder nhưng controller JSON serializer truy cập order.customer hoặc order.items ngoài transaction, gây LazyInitializationException hoặc N+1. Map DTO ngay trong transaction hoặc định nghĩa fetch/projection phù hợp, không bật EAGER mọi collection chỉ để tránh lỗi.

### 19.8. Không có tie-breaker khi phân trang

~~~java
cq.orderBy(cb.desc(root.get("createdAt")));
~~~

Nếu nhiều đơn cùng createdAt, trang có thể không ổn định. Thêm id làm thứ tự thứ hai.

## 20. SQL thực tế khi các bộ lọc thay đổi

Không có filter tùy chọn, Hibernate có thể sinh:

~~~sql
SELECT o.id, o.status, o.total_amount, o.created_at
FROM purchase_orders o
WHERE o.tenant_id = ?
  AND o.deleted_at IS NULL
ORDER BY o.created_at DESC, o.id DESC
LIMIT ? OFFSET ?;
~~~

Nếu có statuses và khoảng tiền:

~~~sql
SELECT o.id, o.status, o.total_amount, o.created_at
FROM purchase_orders o
WHERE o.tenant_id = ?
  AND o.deleted_at IS NULL
  AND o.status IN (?, ?)
  AND o.total_amount >= ?
  AND o.total_amount <= ?
ORDER BY o.created_at DESC, o.id DESC
LIMIT ? OFFSET ?;
~~~

Nếu có keyword:

~~~sql
SELECT o.id, o.status, o.total_amount, o.created_at
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.tenant_id = ?
  AND o.deleted_at IS NULL
  AND (
    LOWER(c.full_name) LIKE ? ESCAPE '~'
    OR LOWER(c.email) LIKE ? ESCAPE '~'
  )
ORDER BY o.created_at DESC, o.id DESC
LIMIT ? OFFSET ?;
~~~

Nếu có productIds:

~~~sql
SELECT o.id, o.status, o.total_amount, o.created_at
FROM purchase_orders o
WHERE o.tenant_id = ?
  AND o.deleted_at IS NULL
  AND EXISTS (
    SELECT 1
    FROM order_items i
    WHERE i.order_id = o.id
      AND i.product_id IN (?, ?)
  )
ORDER BY o.created_at DESC, o.id DESC
LIMIT ? OFFSET ?;
~~~

Đây là SQL **minh họa**, không phải cam kết Hibernate luôn sinh đúng danh sách cột/alias/join như vậy. SQL thật phụ thuộc mapping, fetch plan, dialect và version. Điều quan trọng là quan sát sự khác nhau: **khi không có keyword, không cần JOIN Customer chỉ để tìm từ khóa; khi không có productIds, không có EXISTS đó**.

## 21. Hiệu năng và index cho tìm kiếm nhiều tiêu chí

Criteria API thay đổi cách xây query, không tự tạo index hay bảo đảm SQL tối ưu. Các tổ hợp filter phổ biến có thể cần index khác nhau.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_orders_tenant_created_id
ON purchase_orders(tenant_id, created_at DESC, id DESC);

CREATE INDEX idx_orders_tenant_status_created
ON purchase_orders(tenant_id, status, created_at DESC, id DESC);

CREATE INDEX idx_items_order_id
ON order_items(order_id);

CREATE INDEX idx_items_product_order
ON order_items(product_id, order_id);
~~~

Những index này chỉ là ứng viên. Lựa chọn thực tế phải xem cardinality, tần suất query, số lượng bản ghi, chi phí ghi và EXPLAIN plan. Index quá nhiều làm INSERT/UPDATE chậm hơn và tăng storage.

### 21.1. LIKE chứa wildcard đầu chuỗi

Query LIKE '%linh%' thường không tận dụng hiệu quả index B-tree chuẩn. Với PostgreSQL, có thể cân nhắc extension pg_trgm và trigram index hoặc full-text search, nhưng cần triển khai theo policy migration/schema của dự án và kiểm chứng bằng plan. Không tự động thay mọi tìm kiếm bằng ILIKE hoặc lower() mà không đo chi phí.

### 21.2. Tổ hợp filter khác nhau có thể có plan khác

Status PAID rất phổ biến có thể cần plan khác status CANCELLED rất hiếm. Date range rất hẹp và rất rộng có selectivity khác nhau. Database optimizer quyết định join order, index scan hoặc sequential scan theo thống kê và parameter. Đừng giả định một SQL template cố định với nhiều điều kiện OR :param IS NULL luôn tối ưu hoặc Criteria động luôn tối ưu.

### 21.3. Phân trang sâu

OFFSET 100000 có thể tốn kém dù query chỉ chọn 20 đơn. Nếu user cần duyệt dữ liệu lớn theo thứ tự ngày/ID, cân nhắc **keyset/cursor pagination**:

~~~java
Predicate afterCursor = cb.or(
    cb.lessThan(
        root.<Instant>get("createdAt"),
        lastCreatedAt),
    cb.and(
        cb.equal(
            root.get("createdAt"), lastCreatedAt),
        cb.lessThan(
            root.<Long>get("id"), lastId)
    )
);
~~~

Predicate này dành cho thứ tự createdAt DESC, id DESC. Thêm vào cùng AND với các filter còn lại và dùng setMaxResults(size), không dùng OFFSET. Keyset cursor phải được xây từ hàng cuối trang trước; filter/sort cần giữ nhất quán giữa các request.

## 22. Quan sát SQL và query plan

Trong development/test:

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

Chỉ bật logging bind parameter ở môi trường phù hợp vì có thể lộ email, số tiền hoặc dữ liệu cá nhân. Không để TRACE trong production mặc định.

Checklist quan sát kỹ thuật của một query:

1. Tenant và deletedAt có xuất hiện ở mọi tổ hợp không?
2. Filter nào vắng mặt thì SQL có bỏ đúng predicate đó không?
3. Keyword có JOIN Customer khi cần; không JOIN chỉ vì filter khác không?
4. ProductIds dùng EXISTS và tránh duplicate parent không?
5. COUNT áp dụng đúng cùng tập điều kiện không?
6. Query phân trang có LIMIT/OFFSET tại database không?
7. Có N+1 do lazy association bị truy cập khi map DTO không?
8. Giá trị bind được gửi đúng kiểu enum, BigDecimal và Instant không?

Ví dụ EXPLAIN trên PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id
FROM purchase_orders o
WHERE o.tenant_id = 7
  AND o.deleted_at IS NULL
  AND o.status IN ('PAID', 'DRAFT')
  AND o.total_amount >= 100
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20;
~~~

Quan sát actual rows, index scan, filter, sort, buffers và execution time. EXPLAIN ANALYZE thực thi câu SELECT trên dữ liệu thật của môi trường đang chạy; chỉ sử dụng với dữ liệu/môi trường thích hợp.

### 22.1. Query cache và plan cache

Các tổ hợp Criteria khác nhau có thể sinh các SQL shape khác nhau và có những kế hoạch thực thi khác. Đây là một trade-off của truy vấn động so với query template cố định. Không bật Hibernate query cache hoặc cố chuẩn hóa mọi predicate chỉ để “ít SQL string hơn” khi chưa có số liệu thực tế.

### 22.2. Đo số hàng, không chỉ số câu SQL

Một query join to-many có thể chỉ là một statement nhưng trả hàng chục nghìn SQL rows cho 20 parent. EXISTS thường phù hợp khi chỉ cần tìm order có child khớp. Đo số hàng thực, entity loads, query time và heap thay vì kết luận số statement thấp đồng nghĩa hiệu năng tốt.

## 23. Kiểm thử các trường hợp có hoặc không có filter

Một integration test nên tạo dữ liệu có chủ đích:

| Order | Tenant | Status | Amount | Created | Items | Customer |
|---:|---:|---|---:|---|---:|---|
| 101 | 7 | PAID | 0 | 2026-11-01 | 0 | Linh |
| 102 | 7 | PAID | 120 | 2026-11-02 | 2 | Linh |
| 103 | 7 | DRAFT | 80 | 2026-11-03 | 1 | An |
| 104 | 7 | CANCELLED | 300 | 2026-11-04 | 0 | Bình |
| 105 | 8 | PAID | 500 | 2026-11-05 | 1 | Khách tenant khác |
| 106 | 7 | PAID | 600 | 2026-11-06 | 1 | Đã soft delete |

Test với authenticatedTenantId=7, chỉ đơn chưa xóa.

### 23.1. Ma trận test đầu vào

| Case | Điều kiện | Điều cần khẳng định |
|---|---|---|
| Không chọn filter | Tất cả optional null | Chỉ các Order active thuộc tenant 7 |
| Status đơn | statuses=[PAID] | Chỉ đơn PAID |
| Nhiều status | statuses=[PAID,DRAFT] | Bao gồm cả hai trạng thái |
| Status rỗng | statuses=[] | Không có kết quả theo policy |
| Min tiền bằng 0 | minAmount=0 | Ngưỡng 0 được áp dụng, không tự bỏ |
| Khoảng tiền | min=50, max=150 | Chỉ các đơn nằm trong khoảng |
| Khoảng đảo | min=150, max=50 | Validation từ chối |
| Keyword trống | keyword="   " | Bỏ keyword, giữ mandatory predicates |
| Keyword có nội dung | keyword="linh" | Match tên/email Customer |
| Keyword có % hoặc _ | keyword="50%" | Ký tự được escape theo literal policy |
| hasItems=true | true | Chỉ đơn có ít nhất một item |
| hasItems=false | false | Chỉ đơn không có item |
| hasItems=null | null | Không lọc số item |
| productIds=[x] | Có tập Product ID | Chỉ đơn chứa product phù hợp |
| productIds=[] | Tập rỗng | Không có kết quả |
| Date start only | createdFrom có, before null | Chỉ áp dụng >= |
| Date end only | from null, createdBefore có | Chỉ áp dụng < |
| Multi-tenant | Request cố thao túng filter | Không bao giờ nhận Order tenant 8 |
| Soft delete | Mọi tổ hợp | Không nhận Order đã xóa |
| Paging/sorting | Nhiều Order cùng createdAt | Thứ tự ổn định theo id |
| Count | Kết hợp 3–4 filter | totalElements khớp số parent từ SQL |

### 23.2. Test một filter vắng mặt không tạo join sai

Thiết lập một Order không có item. Khi productIds=null và hasItems=null, Order đó **vẫn phải xuất hiện** nếu các điều kiện khác phù hợp. Nếu builder luôn INNER JOIN items, test này sẽ thất bại. Đây là phép thử tốt để phát hiện một optional filter “vắng mặt nhưng vẫn ảnh hưởng kết quả”.

### 23.3. Test một Order có nhiều child cùng match

Cho Order 102 có hai OrderItem cùng thuộc productIds được tìm. Query danh sách và COUNT vẫn phải coi Order 102 là **một đơn**, không phải hai. EXISTS giúp giữ đúng cardinality.

### 23.4. Test false và zero

Hai test đặc biệt quan trọng:

~~~java
assertThat(search(filterWithHasItemsFalse).content())
    .allMatch(order -> /* không có OrderItem */ true);

assertThat(search(filterWithMinAmountZero).content())
    .isNotNull();
~~~

Đây là skeleton minh họa ý định assertion, không phải test hoàn chỉnh có fixture/method đã định nghĩa. Với kiểm thử thật, kiểm tra ID kỳ vọng và số item bằng truy vấn DB hoặc DTO tương ứng. Mục tiêu là không nhầm **false = không cung cấp** hoặc **0 = không cung cấp**.

### 23.5. Test count query riêng

So sánh totalElements mà API trả với số Order khớp điều kiện kiểm tra độc lập. Chú ý cả keyword JOIN to-one và productIds EXISTS, vì đây là chỗ COUNT dễ bị khác content query khi code được tách riêng.

### 23.6. Test trên database mục tiêu

PostgreSQL Testcontainers giúp kiểm tra LIKE escape, kiểu thời gian, truy vấn EXISTS, enum mapping và SQL pagination gần production hơn H2. H2 có thể khác về function, collation và cú pháp escape; test chỉ trên H2 không đảm bảo behavior giống PostgreSQL.

## 24. Bài thực hành tổng hợp

### Bài A — Filter object và chuẩn hóa

1. Tạo OrderSearchFilter với keyword, statuses, min/max amount, from/before và hasItems.
2. Định nghĩa policy null/blank/empty set/false/zero bằng bảng.
3. Viết validation min/max, thời gian và page size.
4. Dùng một enum sort key thay chuỗi tự do nếu thích.
5. Kiểm tra parse invalid enum phải trả lỗi, không bỏ filter.

### Bài B — Ghép AND và OR

1. Viết Criteria lấy các đơn PAID.
2. Thêm minAmount nếu có.
3. Thêm nhóm OR tìm Customer theo name/email nếu keyword không blank.
4. Thêm tenantId bắt buộc và deletedAt IS NULL.
5. Chứng minh một điều kiện OR của keyword không thể nới rộng tenant.

### Bài C — Kiểm tra collection

1. Tạo đơn có nhiều OrderItem và đơn không có OrderItem.
2. Thêm filter productIds bằng JOIN, quan sát duplicate parent.
3. Thay bằng correlated EXISTS.
4. Viết hasItems=true/false bằng EXISTS/NOT EXISTS.
5. So sánh COUNT và kết quả phân trang của hai cách.

### Bài D — Reusable builder và count

1. Tách builder vào OrderPredicates.build.
2. Dựng content CriteriaQuery<PurchaseOrder>.
3. Dựng count CriteriaQuery<Long> mới.
4. Bảo đảm cả hai gọi cùng builder nhưng dùng Root/Predicate riêng.
5. So sánh totalElements với dữ liệu thật.

### Bài E — Specification

1. Cho PurchaseOrderRepository mở rộng JpaSpecificationExecutor.
2. Viết inTenant, notDeleted, withStatus, atLeast và hasAnyProduct.
3. Ghép bằng Specification.allOf.
4. Tạo một nhóm OR bằng anyOf.
5. Thử các filter null; xác nhận mandatory predicates vẫn còn.

### Bài F — Hiệu năng và bảo mật

1. Bật Hibernate SQL logging ở môi trường test.
2. So sánh SQL khi có keyword và khi keyword null.
3. Dùng EXPLAIN ANALYZE cho status/date range và productIds.
4. Thử tenant khác và deleted row trong mọi trường hợp.
5. Thử LIKE chứa %, _; xác nhận literal search đúng policy.
6. Giới hạn page size và danh sách IDs dài.
7. Kiểm tra kết quả ổn định khi nhiều Order cùng createdAt.

## 25. Những nguyên tắc cần nhớ

1. **Bộ lọc vắng mặt không có nghĩa giống mọi giá trị rỗng.** Null, blank, empty set, false và zero có thể biểu diễn các yêu cầu khác nhau.
2. **Ràng buộc bắt buộc luôn được thêm.** Tenant, authorization và soft delete không phụ thuộc form tìm kiếm.
3. **Một filter chỉ thêm predicate khi thật sự có mặt.** Không tạo JOIN hoặc WHERE vô tình thay đổi dữ liệu khi input vắng mặt.
4. **Các bộ lọc độc lập thường kết hợp bằng AND.** Những cách match trong một filter (name hoặc email) được nhóm bằng OR.
5. **Collection filter thường dùng EXISTS** nếu chỉ cần kiểm tra tồn tại; JOIN to-many có thể nhân bản parent và làm sai COUNT/paging.
6. **Khoảng độc lập mỗi đầu** dùng >= và <= hoặc < nửa mở; validate min/max trước khi gửi SQL.
7. **Boolean false phải được giữ nguyên** và **minAmount=0 phải được coi là giá trị hợp lệ**.
8. **LIKE cần xử lý wildcard** theo policy; parameter binding chống injection nhưng không tự escape % và _.
9. **Tái sử dụng logic xây Predicate, không tái sử dụng Predicate/Root giữa content và count query.**
10. **Phân trang và sorting phải có giới hạn/whitelist và thứ tự ổn định.** Tránh fetch join collection khi phân trang root.
11. **Specification là cách đóng gói Criteria theo thành phần** trong Spring Data JPA, nhưng vẫn phải hiểu JOIN, EXISTS và count.
12. **Criteria API không tự tối ưu SQL**; cần quan sát generated SQL, actual rows, index, execution plan và kiểm thử tổ hợp dữ liệu.

Khi thiết kế truy vấn động, đừng bắt đầu bằng câu hỏi “viết if như thế nào?”. Hãy bắt đầu bằng **mô tả ngữ nghĩa của từng trạng thái đầu vào**, phân biệt điều kiện bắt buộc với tùy chọn, xác định cách nhóm AND/OR, rồi mới chuyển các quy tắc ấy thành Criteria Predicate. Khi làm đúng, cùng một query builder có thể phục vụ hàng trăm tổ hợp tìm kiếm mà vẫn rõ ràng, an toàn, dễ kiểm thử và không vô tình lấy thêm dữ liệu ngoài yêu cầu.
