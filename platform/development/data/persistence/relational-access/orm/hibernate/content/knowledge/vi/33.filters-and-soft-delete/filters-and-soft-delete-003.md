# Bật, tắt bộ lọc và giới hạn khi context đã có sẵn thực thể trong Hibernate ORM

## 1. Bộ lọc được bật, nhưng vì sao vẫn nhìn thấy đơn hàng đã xóa?

Giả sử hệ thống bán hàng sử dụng Hibernate ORM. Bảng `purchase_orders` có cột `deleted_at`; một hàng có `deleted_at IS NOT NULL` được xem là đã xóa mềm. Ứng dụng muốn:

- Người dùng thông thường chỉ thấy các đơn chưa xóa.
- Nhân viên quản trị có quyền được xem cả đơn đã xóa.
- Mọi truy vấn trong một nghiệp vụ phải được giới hạn theo `tenant_id`.

Hibernate hỗ trợ **bộ lọc động** bằng `@FilterDef`, `@Filter` và `Session.enableFilter()`. Một cách triển khai sơ bộ là bật filter khi truy vấn danh sách và tắt nó khi cần chế độ quản trị.

Nhưng hãy tưởng tượng chuỗi thao tác sau trong **cùng một persistence context**:

~~~java
PurchaseOrder order = entityManager.find(
    PurchaseOrder.class, 101L);

Session session = entityManager.unwrap(Session.class);
session.enableFilter("visibleOrders")
    .setParameter("tenantId", 7L);

PurchaseOrder again = entityManager.find(
    PurchaseOrder.class, 101L);
~~~

Nếu `order` đã managed, lệnh `find()` thứ hai có thể trả lại **chính instance đang có trong first-level cache**, bất kể filter vừa được bật. Không có SQL mới để filter can thiệp.

Một tình huống khác:

~~~java
List<OrderItem> items = order.getItems();
items.size(); // Collection đã được khởi tạo.

session.enableFilter("activeItems");

items.size(); // Vẫn là collection đã khởi tạo trước đó.
~~~

Filter mới không tự áp dụng lại lên những phần tử đã nằm trong collection.

**Đây là chủ đề chính của bài:** Hibernate Filter tác động đến **SQL/load plan khi ORM quyết định tải dữ liệu**; nó không phải cơ chế chuyển đổi ngay lập tức toàn bộ object graph đã tồn tại trong một `EntityManager` hay `Session`.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Khai báo và sử dụng Hibernate `@FilterDef`, `@Filter`, `enableFilter()`, `disableFilter()`.
2. Phân biệt điều kiện filter động với soft-delete restriction cố định.
3. Hiểu filter có phạm vi **Session**, trong khi entity managed có phạm vi **persistence context**.
4. Giải thích vì sao entity và collection đã tải trước khi bật filter không tự được lọc lại.
5. Nhận biết những giới hạn của load-by-key, `find()`, `getReference()` và association to-one.
6. Thiết kế ranh giới bật/tắt filter trong service Spring `@Transactional`, tránh rò rỉ filter giữa các nghiệp vụ.
7. Không dùng Hibernate Filter làm lớp bảo mật duy nhất trong hệ thống đa tenant.
8. Nhận ra các thao tác native SQL, bulk DML, cache hoặc external writer không tự tuân theo mọi filter.
9. Viết integration tests kiểm chứng cả dữ liệu đã managed và dữ liệu chưa tải.
10. Chọn đúng giải pháp giữa filter, `@SQLRestriction`, `@SoftDelete`, điều kiện repository và row-level security.

Ví dụ dùng Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA và PostgreSQL. Hibernate Filter là API **đặc thù Hibernate**, không phải một tính năng portable của toàn bộ Jakarta Persistence. Một số tùy chọn, đặc biệt liên quan đến tải theo khóa và soft delete, thay đổi theo phiên bản Hibernate; cần kiểm thử trên phiên bản thực tế.

## 2. Phân biệt các lớp chịu trách nhiệm lọc dữ liệu

Trước khi viết annotation, cần xác định lớp nào đang kiểm soát tập dữ liệu.

| Cơ chế | Phạm vi | Có thay đổi động? | Tự loại instance đã managed khỏi L1? |
|---|---|---|---|
| `WHERE` trong HQL/JPQL | Một truy vấn cụ thể | Có, qua parameter/query builder | Không |
| Hibernate `@Filter` | Các thao tác load/query phù hợp trong Session đang bật filter | Có | Không |
| `@SQLRestriction` | Restriction mapping tĩnh do Hibernate áp dụng ở các load path được hỗ trợ | Không bật/tắt bằng Session | Không |
| Hibernate `@SoftDelete` | Soft-delete semantics theo mapping, ở phiên bản hỗ trợ | Không phải công tắc filter tùy ý | Không |
| Persistence context/L1 cache | Một EntityManager/Session | Managed instances tồn tại đến detach/clear/close | Là nơi giữ instance |
| Second-level cache | SessionFactory/provider/cache region | Phụ thuộc cache configuration | Không thay đổi L1 đã có |
| PostgreSQL row-level security | Database session/role/policy | Theo database policy/context | Không tự tái kiểm tra trên L1 hit |
| Application authorization | Service/API/business boundary | Theo principal, tenant, quyền | Phải được kiểm tra độc lập |

Một filter không biến thành điều kiện bảo mật có hiệu lực trên mọi đường đọc Java. Nếu entity đã nằm trong context, nhiều thao tác chỉ tra cứu identity map. Nếu ứng dụng dùng native SQL, filter Hibernate không mặc nhiên sửa câu SQL ấy. Nếu dữ liệu được trả từ một cache application riêng, filter ORM cũng không kiểm soát việc đọc cache đó.

### 2.1. Luồng đọc theo ID

~~~mermaid
flowchart TD
    A[entityManager.find ID] --> B{Entity đã managed trong L1?}
    B -->|Có| C[Trả lại instance managed]
    B -->|Không| D[ORM quyết định cách load]
    D --> E{Load path có áp dụng filter đang bật?}
    E -->|Có| F[SQL với predicate filter]
    E -->|Không| G[SQL không chứa predicate đó]
    F --> H[Hydrate hoặc trả null theo kết quả]
    G --> H
~~~

Nhánh từ L1 tới managed object **không chạy qua SQL**. Vì vậy không thể bảo đảm `enableFilter()` làm một object đã managed “biến mất”.

### 2.2. Luồng truy vấn danh sách

Một HQL:

~~~hql
select o
from PurchaseOrder o
order by o.createdAt desc
~~~

khi filter phù hợp đang bật, Hibernate có thể thêm predicate tenant/soft-delete vào SQL sinh ra. Tuy nhiên nếu một hàng trả về trỏ tới entity có cùng khóa đã managed trong context, Hibernate thường tái sử dụng instance đang managed thay vì tạo một object mới và thay toàn bộ state.

**Lọc tập khóa từ database** và **state của object đã managed** là hai vấn đề tách biệt.

## 3. Mô hình dữ liệu cho ví dụ

Giả sử schema PostgreSQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    order_number VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uk_order_number_per_tenant
        UNIQUE (tenant_id, order_number)
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES purchase_orders(id),
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT ck_order_items_quantity
        CHECK (quantity > 0)
);

CREATE INDEX idx_orders_tenant_active_created
ON purchase_orders(tenant_id, created_at DESC, id DESC)
WHERE deleted_at IS NULL;

CREATE INDEX idx_items_order_active
ON order_items(order_id)
WHERE deleted_at IS NULL;
~~~

Một tập dữ liệu minh họa:

| ID đơn | Tenant | Trạng thái xóa | Ý nghĩa |
|---:|---:|---|---|
| 101 | 7 | `NULL` | Đang hoạt động của tenant 7 |
| 102 | 7 | `2026-01-10...` | Đã xóa mềm của tenant 7 |
| 103 | 8 | `NULL` | Đang hoạt động của tenant 8 |
| 104 | 8 | `2026-02-01...` | Đã xóa mềm của tenant 8 |

Khi filter “tenant 7 và chưa xóa” được bật, một query danh sách phù hợp chỉ nên nhận ID 101. Khi filter đó bị tắt, kết quả phụ thuộc các điều kiện khác trong HQL và quyền ứng dụng; **tắt filter không tương đương tự động được phép đọc toàn bộ tenant**.

### 3.1. Entity tối giản

~~~java
import jakarta.persistence.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Version
    private long version;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public Instant getDeletedAt() { return deletedAt; }
    public List<OrderItem> getItems() { return items; }
}
~~~

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    protected OrderItem() {}
}
~~~

Các public classes thực tế cần nằm ở source file riêng và bổ sung constructors/domain methods phù hợp. Code chưa bật filter; phần sau sẽ thêm metadata Hibernate có chủ đích.

## 4. Khai báo một filter động với @FilterDef và @Filter

Hibernate hỗ trợ định nghĩa tên filter và các parameter:

~~~java
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@Table(name = "purchase_orders")
@FilterDef(
    name = "visibleOrders",
    parameters = @ParamDef(
        name = "tenantId",
        type = Long.class
    )
)
@Filter(
    name = "visibleOrders",
    condition = "tenant_id = :tenantId and deleted_at is null"
)
public class PurchaseOrder {
    @Id
    private Long id;
    // Những trường persistent khác.
}
~~~

Đây là phiên bản rút gọn để minh họa **annotation bổ sung vào entity PurchaseOrder đã có**, không phải yêu cầu tạo hai entity cùng tên trong project.

### 4.1. Vai trò của @FilterDef

`@FilterDef` công bố:

- **name**: tên filter, ví dụ `visibleOrders`.
- **parameters**: tham số có kiểu, ở đây `tenantId` là `Long`.
- Có thể có các tùy chọn/default condition/auto-enable khác theo phiên bản Hibernate.

Filter definition thường nằm trong metadata của persistence unit/SessionFactory. Nó không tự bảo đảm filter đang bật ở mọi Session.

### 4.2. Vai trò của @Filter

`@Filter` gắn điều kiện SQL với entity hoặc association. Điều kiện `tenant_id = :tenantId and deleted_at is null` dùng **tên cột vật lý trong database**, không phải Java property `tenantId` hoặc `deletedAt`.

Khi Hibernate tạo SQL cho một load path có hỗ trợ filter và filter đó đang bật, nó có thể ghép điều kiện tương ứng vào SQL:

~~~sql
SELECT o.*
FROM purchase_orders o
WHERE o.tenant_id = ?
  AND o.deleted_at IS NULL
ORDER BY o.created_at DESC;
~~~

SQL thực có thể sử dụng alias, join và cú pháp khác; đây là minh họa ngữ nghĩa.

### 4.3. Định nghĩa filter không đồng nghĩa bật filter

Mặc định, filter động thông thường cần được bật trên `Session`. Chỉ viết:

~~~java
@Filter(name = "visibleOrders", condition = "...")
~~~

không đủ để bảo đảm mọi truy vấn tự áp dụng nó. Một số Hibernate version có tùy chọn auto-enabled, nhưng bạn phải xác định chính xác cấu hình và cơ chế set parameter; không được đoán rằng ứng dụng tự nhận tenant ID từ Spring Security.

### 4.4. Tránh trộn hai mục đích nếu cần bật/tắt riêng

Nếu filter vừa kiểm tra tenant vừa loại soft-delete:

~~~sql
tenant_id = :tenantId AND deleted_at IS NULL
~~~

thì tắt nó để xem đơn đã xóa **cũng tắt điều kiện tenant**. Đây là rủi ro lớn. Thiết kế tốt hơn thường là:

- Ràng buộc tenant không được bỏ qua một cách tùy tiện.
- Điều kiện soft-delete có thể được bật/tắt theo quyền và use case.

Ví dụ tách hai filter có tên rõ ở phần tiếp theo.

## 5. Tách filter tenant và filter xóa mềm

Metadata minh họa:

~~~java
@Entity
@Table(name = "purchase_orders")
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(
        name = "tenantId",
        type = Long.class
    )
)
@FilterDef(name = "activeOrders")
@Filter(
    name = "tenantScope",
    condition = "tenant_id = :tenantId"
)
@Filter(
    name = "activeOrders",
    condition = "deleted_at is null"
)
public class PurchaseOrder {
    @Id
    private Long id;
    // Các mapping fields khác.
}
~~~

Các `@FilterDef` là repeatable ở các phiên bản hỗ trợ; nếu project/phiên bản yêu cầu container annotation, dùng dạng metadata tương ứng. Ý chính không đổi: **tenantScope** và **activeOrders** là hai điều kiện có thể được quản lý riêng.

Khi cả hai được bật trong một Session, các điều kiện áp dụng cùng nhau (về bản chất là giao của hai tập):

~~~sql
WHERE tenant_id = ?
  AND deleted_at IS NULL
~~~

Khi chỉ tắt `activeOrders` mà vẫn giữ `tenantScope`, một query phù hợp có thể trả cả đơn đang hoạt động và đã xóa của tenant hiện tại.

### 5.1. Bảng các chế độ

| tenantScope | activeOrders | Kết quả mong muốn trên truy vấn phù hợp | Cần quyền? |
|---|---|---|---|
| Bật tenant 7 | Bật | Chỉ đơn đang hoạt động tenant 7 | Quyền đọc bình thường |
| Bật tenant 7 | Tắt | Cả đơn đã xóa của tenant 7 | Quyền xem deleted |
| Bật tenant 8 | Bật | Chỉ đơn đang hoạt động tenant 8 | Quyền tenant 8 |
| Tắt | Bật | Đơn đang hoạt động của nhiều tenant | Chỉ dành cho workflow đặc biệt đã kiểm soát |
| Tắt | Tắt | Toàn bộ các đơn mà query có thể thấy | **Không cho phép chỉ vì đã tắt filter** |

Trong ứng dụng nhiều tenant, việc một Session có thể tắt tenantScope là khả năng kỹ thuật, **không phải chính sách phân quyền**. Phải đặt authorization trong tầng tin cậy hoặc DB policy.

### 5.2. Các filter không tự áp dụng lên mọi association

Entity `PurchaseOrder` có `@Filter` không nhất thiết làm mọi truy vấn độc lập trên `OrderItem` tự động tuân theo cùng tenant restriction. Với child entity, query trực tiếp hoặc association-specific load phải được thiết kế rõ.

Ví dụ một repository `OrderItemRepository.findAll()` có thể tạo SQL trên `order_items` mà không đi qua query Order. Vì vậy filter ở parent **không thay thế** filter/query policy trên các entity child cần bảo vệ.

## 6. Bật, đặt tham số và tắt filter bằng Session

API đặc trưng của Hibernate:

~~~java
import org.hibernate.Filter;
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);

Filter tenantFilter = session.enableFilter("tenantScope");
tenantFilter.setParameter("tenantId", trustedTenantId);

session.enableFilter("activeOrders");

// Thực hiện các query chịu ảnh hưởng của filter.

session.disableFilter("activeOrders");
session.disableFilter("tenantScope");
~~~

### 6.1. Session, không phải SessionFactory

`SessionFactory` là factory chia sẻ giữa các requests. `Session` là persistence context riêng cho một đơn vị làm việc. **Enabled filter state thuộc Session**, không phải biến toàn cục được bật cho mọi request.

Điều này tốt cho việc ràng buộc theo tenant/request, nhưng cũng có nghĩa bạn phải quản lý scope đúng: cùng một Session có thể phục vụ nhiều thao tác theo lifecycle Spring/OSIV và filter state có thể tồn tại lâu hơn một method nếu không tắt.

### 6.2. Luôn đặt parameter trước khi chạy query

~~~java
Filter f = session.enableFilter("tenantScope");
f.setParameter("tenantId", trustedTenantId);
~~~

Không mở query trước khi đã cung cấp các parameter bắt buộc rồi trông đợi Hibernate suy luận tenant. Nếu filter thiếu parameter, provider có thể báo lỗi khi thực thi query.

`trustedTenantId` phải lấy từ ngữ cảnh bảo mật được xác minh; không lấy nguyên từ query parameter `?tenantId=...` rồi coi client có quyền chọn tenant.

### 6.3. Parameter binding thay vì nối chuỗi SQL

Nên:

~~~java
session.enableFilter("tenantScope")
    .setParameter("tenantId", trustedTenantId);
~~~

Không nên tạo condition string từ dữ liệu người dùng:

~~~java
String condition = "tenant_id = " + rawClientTenantId;
// Không dùng chuỗi do client kiểm soát làm điều kiện SQL.
~~~

Điều kiện của `@Filter` là metadata tĩnh do developer định nghĩa; giá trị động được bind qua Filter API. Với danh sách tham số, Hibernate có `setParameterList()` trong các use case/phiên bản hỗ trợ, nhưng vẫn cần giới hạn kích thước, kiểu và tránh danh sách rỗng có semantics khó hiểu.

### 6.4. disableFilter ảnh hưởng các lần tải về sau

~~~java
session.disableFilter("activeOrders");
~~~

Lệnh này không tự:

- Xóa những entity đã managed.
- Làm một collection initialized tải lại.
- Refresh thuộc tính entity đang có.
- Commit transaction.
- Phục hồi một snapshot dữ liệu cũ.

Nó thay đổi **cấu hình filter cho các thao tác load/query phù hợp tiếp theo** trong Session.

## 7. Phạm vi filter trong Spring @Transactional

Trong ứng dụng Spring Data JPA, EntityManager thường được Spring gắn với transaction hiện tại. Có thể dùng một service chuyên trách:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.hibernate.Session;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VisibleOrderReader {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public List<PurchaseOrder> findCurrentOrders(Long trustedTenantId) {
        Session session = entityManager.unwrap(Session.class);

        session.enableFilter("tenantScope")
            .setParameter("tenantId", trustedTenantId);
        session.enableFilter("activeOrders");

        try {
            return entityManager.createQuery("""
                select o
                from PurchaseOrder o
                order by o.createdAt desc, o.id desc
                """, PurchaseOrder.class)
                .getResultList();
        } finally {
            session.disableFilter("activeOrders");
            session.disableFilter("tenantScope");
        }
    }
}
~~~

Code trên minh họa lifecycle bật → query → tắt. Trong project thật, **không trả entity có lazy associations trực tiếp tới web serializer**; nên map DTO trong transaction trước khi tắt filter/đóng context và kiểm soát association nào cần load.

### 7.1. try/finally quan trọng

Nếu query ném exception mà code không tắt filter, một Session sống tiếp có thể mang filter của nghiệp vụ trước:

~~~text
Lượt 1: bật tenant 7
  -> query lỗi
  -> quên disableFilter
Lượt 2: thao tác khác dùng cùng Session
  -> vẫn còn tenant 7, kết quả sai hoặc thiếu
~~~

`try/finally` giúp khôi phục state ngay cả khi query lỗi. Tuy nhiên nếu một transaction đã thất bại, không nên cố tiếp tục sử dụng EntityManager như chưa có lỗi; để transaction boundary rollback đúng.

### 7.2. Không tắt filter sớm khi còn lazy access

Sai về timing:

~~~java
List<PurchaseOrder> orders;
session.enableFilter("activeOrders");
try {
    orders = queryOrders();
} finally {
    session.disableFilter("activeOrders");
}

for (PurchaseOrder o : orders) {
    o.getItems().size(); // Lazy load sau khi filter bị tắt.
}
~~~

Nếu `items` có filter riêng cần giữ và chưa được initialized, lazy load xảy ra **sau khi disableFilter** có thể nạp dữ liệu ngoài tập mong muốn.

Nên thực hiện toàn bộ việc load cần thiết và map DTO **trong phạm vi đã bật filter**:

~~~java
session.enableFilter("activeItems");
try {
    List<PurchaseOrder> orders = loadOrders();
    return orders.stream()
        .map(o -> new OrderRow(
            o.getId(),
            o.getItems().stream()
                .map(OrderItem::getSku)
                .toList()
        ))
        .toList();
} finally {
    session.disableFilter("activeItems");
}
~~~

Đoạn này vẫn có thể tạo N+1 nếu thiếu fetch plan; để sản xuất cần tối ưu query/batch. Ý chính là **thời điểm khởi tạo lazy association phải nằm trong filter scope** nếu bạn muốn filter tham gia vào query load của association đó.

### 7.3. Không bật tắt trong controller rồi hy vọng service dùng cùng Session

Một controller có thể gọi nhiều service có transaction propagation khác nhau. Nếu bật filter ở controller, chưa chắc đó là cùng Hibernate Session với query trong service, nhất là khi outer transaction chưa bắt đầu hoặc có `REQUIRES_NEW`.

Đặt cấu hình filter trong transaction-boundary/service **nơi query được thực thi**, và kiểm thử đúng Session được sử dụng. Nếu cần policy áp dụng cho mọi repository query, thiết kế một cơ chế scope chung có kiểm soát thay vì dựa vào thứ tự gọi controller.

## 8. First-level cache: điểm quan trọng nhất của bài

Persistence context của Hibernate có **identity map**. Khi entity với cùng entity type và identifier đã managed, Hibernate thường trả lại cùng Java object cho các lần truy cập tương ứng trong cùng context.

Ví dụ:

~~~java
PurchaseOrder first = entityManager.find(
    PurchaseOrder.class, 102L);

// Giả sử first được load khi chưa bật activeOrders,
// và đơn #102 có deleted_at != NULL.

Session session = entityManager.unwrap(Session.class);
session.enableFilter("activeOrders");

PurchaseOrder second = entityManager.find(
    PurchaseOrder.class, 102L);

assert first == second; // Cùng managed instance nếu first còn trong context.
~~~

Nếu đối tượng đã managed, không nhất thiết có SELECT mới. Filter chưa có cơ hội loại bỏ nó khỏi identity map.

### 8.1. Filter không sửa tập entity đang managed

Một số người nghĩ:

~~~text
Session bật activeOrders
  -> Hibernate duyệt tất cả managed entities
  -> Loại bỏ những entity có deleted_at != NULL
~~~

**Hibernate không thực hiện bước này như hệ quả của enableFilter.**

L1 là cơ chế quản lý identity/dirty checking; filter được dùng khi sinh truy vấn hoặc tải association theo path hỗ trợ. Tự động detach mọi object không khớp filter sẽ ảnh hưởng state changes, cascade và references đang tồn tại, vì thế không thể coi filter như “dọn lại persistence context”.

### 8.2. Query trả ID đã managed vẫn dùng instance managed

Giả sử:

1. Session đã load Order 101.
2. Một transaction khác update một số cột của Order 101.
3. Session hiện tại chạy query có filter và SQL trả ID 101.
4. Hibernate có thể trả instance Order 101 đang managed với state cũ.

Do vậy filter quyết định **hàng SQL nào phù hợp**, không có nghĩa mọi thuộc tính của entity đang managed luôn mới nhất từ DB.

### 8.3. Query HQL khác truy cập theo ID

Một HQL:

~~~hql
select o
from PurchaseOrder o
where o.id = :id
~~~

về hình dạng có thể phát SELECT áp dụng `@Filter` đang bật. Còn:

~~~java
entityManager.find(PurchaseOrder.class, id);
~~~

có đường load-by-key và first-level cache riêng. **Không giả định hai API luôn có cùng hành vi filter.** Đây là điểm quan trọng với yêu cầu giới hạn tenant hoặc soft-delete.

## 9. Ví dụ thời gian: bật filter sau khi đã tải thực thể

Giả sử Order 102 đã bị xóa mềm:

~~~sql
UPDATE purchase_orders
SET deleted_at = CURRENT_TIMESTAMP
WHERE id = 102;
~~~

Test transaction/persistence context:

~~~text
T0  Session S mới, activeOrders đang tắt
T1  S.find(Order, 102) -> Order 102 được managed
T2  S.enableFilter("activeOrders")
T3  S.find(Order, 102) -> có thể trả lại Order 102 ở L1
T4  S chạy HQL list với filter -> SQL có deleted_at IS NULL
T5  HQL list không bao gồm Order 102 nếu DB state đã deleted
T6  S vẫn có managed Order 102 trong L1
~~~

Hai quan sát T3 và T5 có thể xảy ra **trong cùng Session**:

- `find(102)` trả entity đã managed.
- Query danh sách theo filter không trả row đã xóa.

Điều này không có nghĩa Hibernate tự mâu thuẫn về SQL; nó phản ánh hai đường truy cập có semantics khác nhau.

### 9.1. Khi filter bị tắt sau một query

~~~text
T0  Session S bật activeOrders
T1  Query list trả Orders 101, 103
T2  S tắt activeOrders
T3  Query list không filter có thể thêm Order 102
T4  Những Orders đã managed từ T1 vẫn managed
~~~

Tắt filter làm mở rộng kết quả của các truy vấn phù hợp về sau, **không tạo lại entity mới cho những khóa đã nằm trong L1**.

### 9.2. Không dùng cùng Session để đo độ an toàn của hai chế độ

Nếu một test đọc admin mode, sau đó bật user filter rồi kiểm tra `em.find()`, test dễ bị L1 che sự thật. Test điều kiện filter phải có các case **context mới** và **context đã chứa entity**, thay vì chỉ so sánh một danh sách trong một transaction.

## 10. Collection đã khởi tạo không được lọc lại

Quan hệ to-many còn dễ gây nhầm lẫn hơn entity root.

~~~java
PurchaseOrder order = entityManager.find(
    PurchaseOrder.class, 101L);

List<OrderItem> items = order.getItems();
items.size(); // Hibernate initialize collection.

session.enableFilter("activeItems");

int after = items.size();
~~~

Nếu `items` đã được initialized ở thời điểm filter chưa bật, `after` vẫn là số phần tử có trong collection object đó. Hibernate không chạy lại SELECT để loại các OrderItem đã soft-delete.

### 10.1. @Filter ở collection

Một mapping minh họa:

~~~java
@OneToMany(
    mappedBy = "order",
    fetch = FetchType.LAZY
)
@Filter(
    name = "activeItems",
    condition = "deleted_at is null"
)
private List<OrderItem> items = new ArrayList<>();
~~~

`@FilterDef(name="activeItems")` cần được đăng ký trong persistence unit. Khi filter `activeItems` bật **trước lần khởi tạo collection phù hợp**, Hibernate có thể thêm điều kiện `deleted_at IS NULL` vào SQL load collection.

Nếu collection đã initialized trước, bật filter không thay đổi các phần tử đã có.

### 10.2. Sơ đồ hai trường hợp

~~~mermaid
flowchart TD
    A[Order có lazy items] --> B{Items đã initialized?}
    B -->|Chưa| C[Bật activeItems]
    C --> D[Truy cập items]
    D --> E[SQL load collection có filter phù hợp]
    B -->|Rồi| F[Bật activeItems]
    F --> G[Đọc collection có sẵn]
    G --> H[Không có SQL reload; dữ liệu cũ còn nguyên]
~~~

### 10.3. Tắt filter không nạp lại các phần tử đã bị ẩn

Tình huống ngược:

~~~java
session.enableFilter("activeItems");
order.getItems().size(); // Chỉ load những item đang active.

session.disableFilter("activeItems");
order.getItems().size(); // Vẫn là collection đã initialized.
~~~

Collection này không tự mở rộng để gồm item đã xóa mềm. Một UI admin đọc cùng managed Order và mong sau khi tắt filter sẽ thấy toàn bộ items có thể nhận danh sách thiếu.

### 10.4. Tại sao không nên sửa collection đã initialized bằng tay để “áp dụng filter”?

~~~java
order.getItems().removeIf(
    item -> item.getDeletedAt() != null);
~~~

Nếu quan hệ có `orphanRemoval=true` hoặc cascade, thao tác remove khỏi managed collection có thể được Hibernate hiểu là thay đổi quan hệ cần DELETE/UPDATE. **Lọc phần tử để hiển thị không phải thao tác mutation của aggregate**.

Nên tạo DTO/list mới với predicate Java nếu chỉ cần lọc view:

~~~java
List<OrderItem> visible = order.getItems().stream()
    .filter(item -> item.getDeletedAt() == null)
    .toList();
~~~

Nhưng phải nhớ: cách lọc trong Java không giảm dữ liệu đã đọc từ DB và không thay thế giới hạn dữ liệu bảo mật; nó chỉ tạo một view in-memory khi dữ liệu đã được tải hợp lệ.

## 11. Truy cập trực tiếp bằng khóa và giới hạn của @Filter

Đây là bẫy quan trọng nhất nếu dùng Filter làm điều kiện bảo mật.

~~~java
entityManager.find(PurchaseOrder.class, 102L);
session.byId(PurchaseOrder.class).load(102L);
entityManager.getReference(PurchaseOrder.class, 102L);
~~~

Các API này dùng đường tải hoặc reference theo khóa định danh. Trong nhiều phiên bản Hibernate, filter thông thường **không tự động được áp dụng cho load-by-key** theo cùng cách với HQL query. Một số phiên bản có tùy chọn như `applyToLoadByKey` trong `@FilterDef`, nhưng tính năng và hệ quả với association phải được kiểm tra trên phiên bản cụ thể.

### 11.1. Load-by-key còn có first-level cache

Kể cả provider hỗ trợ áp dụng filter khi SQL load-by-key, một object đã managed trong L1 vẫn có thể được trả mà không chạy SQL. Do đó bật `applyToLoadByKey` **không sửa bài toán object đã có trong persistence context**.

### 11.2. getReference chưa chắc truy vấn ngay

`getReference()` có thể trả proxy/reference và trì hoãn truy vấn cho tới khi truy cập thuộc tính, tùy provider/mapping. Filter state tại thời điểm tạo reference chưa hẳn tương đương filter state tại thời điểm proxy khởi tạo.

Không viết business rule:

~~~java
session.enableFilter("tenantScope")
    .setParameter("tenantId", tenantId);
PurchaseOrder order = em.getReference(
    PurchaseOrder.class, orderId);
session.disableFilter("tenantScope");
return order; // Có thể lazy load ở thời điểm khác.
~~~

Nếu cần xác minh quyền, dùng query explicit có tenant predicate và map DTO trong transaction hoặc một cơ chế authorization độc lập.

### 11.3. To-one association cũng thường tải theo key

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

Khi code truy cập `order.getCustomer()`, Hibernate có thể load Customer theo FK/ID, không nhất thiết qua query root có filter giống PurchaseOrder. Nếu filter của Customer cấm đọc đối tượng đó, provider có thể gặp tình huống association tham chiếu tới row không được phép nhìn thấy.

Các tùy chọn lọc load-by-key có thể tạo `EntityFilterException` hoặc hành vi tương tự ở trường hợp to-one reference theo Hibernate version; không giả định chúng làm association biến thành `null` một cách an toàn.

### 11.4. Filter không thể biến một FK hợp lệ thành “không tồn tại” trên mọi đường

Database vẫn có FK `purchase_orders.customer_id` trỏ tới Customer. Filter là quy tắc chọn hàng khi đọc; nó không thay đổi referential integrity. Nếu logic UI có customer ẩn/soft-deleted, cần xác định:

- Cho phép đơn tham chiếu customer đã soft-deleted hay không?
- Hiển thị thông tin snapshot thay vì load Customer?
- Service trả `null`/placeholder nếu user không có quyền?
- To-one association nào bắt buộc tồn tại theo mô hình domain?

Không trông đợi một `@Filter` tự giải quyết mọi semantics của quan hệ.

## 12. clear(), detach(), refresh() có giúp áp dụng filter mới không?

Khi cần đọc lại dữ liệu dưới filter khác, một số API JPA/Hibernate liên quan:

| API | Tác dụng chính | Lưu ý |
|---|---|---|
| `entityManager.clear()` | Detach toàn bộ entities trong context | Có thể làm mất các thay đổi pending chưa flush |
| `entityManager.detach(entity)` | Detach một entity | Association/collection đã giữ reference Java còn tồn tại ở caller |
| `entityManager.refresh(entity)` | Reload state của managed entity từ persistence store | Không phải cơ chế đổi security scope cho cả graph |
| `entityManager.close()` | Đóng persistence context | Chỉ dùng trực tiếp nếu bạn sở hữu lifecycle EM |
| Tạo EntityManager/Session mới | Có một persistence context mới | Phù hợp nhất khi cần đổi hẳn visibility scope |

### 12.1. clear không phải một nút “làm mới filter”

~~~java
entityManager.clear();
session.enableFilter("activeOrders");
~~~

`clear()` khiến lần tải sau không dùng managed instance cũ, nhưng nó **không bảo đảm mọi load path áp dụng filter**, không tự cấp quyền và không sửa vấn đề direct find theo key ở những phiên bản không áp dụng filter cho cách tải đó.

Ngoài ra, nếu trước `clear()` có các thay đổi chưa flush, chúng có thể không được đồng bộ vì entity đã bị detach.

### 12.2. refresh không phải giải pháp tổng quát

Gọi:

~~~java
entityManager.refresh(order);
~~~

có thể làm ORM reload field values, nhưng không biến một collection đã initialized thành “collection khác theo filter mới” với semantics bảo đảm trên mọi version. Nó cũng có thể ghi đè in-memory modifications chưa flush.

Không dùng refresh để kiểm tra quyền truy cập; validation/authorization phải được thực hiện ở service/database policy.

### 12.3. Cách đơn giản nhất khi đổi visibility mode

Với nghiệp vụ **đổi chế độ dữ liệu**, nên dùng **persistence context mới**, bật đúng filter trước truy vấn đầu tiên và map DTO rồi đóng transaction/context.

Điều này đặc biệt quan trọng với:

- Chuyển từ user mode sang admin mode.
- Chuyển tenant ID.
- Chuyển từ “chỉ active” sang “bao gồm deleted”.
- Truy cập lại entity/collection đã được load dưới scope cũ.

Một transaction mới không luôn đồng nghĩa một EntityManager hoàn toàn mới nếu cấu hình OSIV/custom context giữ EntityManager theo request; hãy xác nhận lifecycle thực tế.

## 13. Persistence context có thể sống lâu hơn bạn tưởng

Trong Spring, persistence context thường gắn với transaction. Nhưng có những cấu hình làm nó sống lâu hơn một service method:

- Open EntityManager/Session in View (OSIV).
- Extended persistence context trong ứng dụng có stateful workflow.
- Session được ứng dụng quản lý thủ công.
- Batch jobs dùng một Session cho nhiều bước.
- Transaction propagation/EntityManager binding khác mặc định.

### 13.1. Open Session in View và filter rò rỉ scope

Khi OSIV giữ EntityManager mở suốt HTTP request:

~~~text
HTTP request
  -> Controller
      -> Service A bật activeOrders, query
      -> Service A quên tắt filter
      -> Service B đọc Orders trong cùng request
      -> JSON serializer truy cập lazy items
  -> EntityManager đóng cuối request
~~~

Service B hoặc serializer có thể chịu filter state còn sót lại. Ngược lại, nếu Service A tắt filter trước khi serializer lazy-load, một collection có thể được tải **không có filter**.

Vì vậy tránh trả entity trực tiếp qua JSON boundary; nên map DTO đầy đủ trong transaction/service có filter scope được quản lý rõ. Cân nhắc vô hiệu OSIV khi kiến trúc cho phép.

### 13.2. Extended persistence context

Trong một ứng dụng giữ EM qua nhiều bước user workflow, có thể đã managed cả những entity từ trước khi filter được bật. Thay đổi filter giữa các bước không loại các object đang được giữ. Khi cần thay visibility mode, phải thiết kế context boundaries, không chỉ set flag.

### 13.3. Session không an toàn để chia sẻ giữa các thread

Không giữ một Hibernate Session chung cho nhiều HTTP requests hoặc parallel tasks rồi bật/tắt filter theo ThreadLocal/tenant:

~~~text
Thread A bật tenant 7
Thread B bật tenant 8 trên cùng Session
Thread A query...
~~~

Hibernate Session/EntityManager thông thường không thread-safe. Filter là session state nên mô hình chia sẻ này vừa sai isolation vừa sai concurrency.

### 13.4. Async task không tự dùng đúng Session

`@Async`, background worker hoặc một executor thread khác không mặc nhiên kế thừa transaction-bound EntityManager/filter state từ request thread. Hãy truyền tenant/actor dưới dạng dữ liệu có kiểm soát và tạo transaction/Session riêng cho worker.

## 14. Bật/tắt filter có thể tạo sai lệch ngay trong cùng transaction

Trong một transaction:

~~~text
T0  activeOrders = enabled
T1  Load Order 101 và items active
T2  activeOrders = disabled
T3  Query lấy thêm các Order deleted
T4  activeOrders = enabled lại
T5  Dùng những references đã load ở T3
~~~

Ở T5, những entity đã managed trong T3 vẫn là object Java hợp lệ và vẫn có thể được service sử dụng. Bật filter lại không thu hồi reference.

### 14.1. Visibility không phải trạng thái của entity

Entity không mang một nhãn “được load khi filter đang bật” để Hibernate tự cấm truy cập khi filter đổi. Visibility là quy tắc truy vấn, còn managed entity là object trong context.

### 14.2. Đừng chuyển chế độ bằng filter trong một request dài

Nếu cùng một workflow phải lần lượt đọc dữ liệu admin và user, nên cân nhắc:

1. Các service riêng có authorization rõ.
2. DTO được dựng trong mỗi transaction/scope.
3. Persistence contexts độc lập nếu tập visibility khác nhau.
4. Không chuyển entity managed từ admin context sang user context như dữ liệu “đã an toàn”.

### 14.3. Ranh giới service rõ hơn thao tác đổi filter giữa chừng

Ví dụ một phương thức `findDeletedForAdmin()` có quyền đặc biệt nên sử dụng query explicit:

~~~hql
select o
from PurchaseOrder o
where o.tenantId = :tenantId
  and o.deletedAt is not null
order by o.id
~~~

và DTO riêng. Nếu việc bật/tắt filter tạo quá nhiều state transitions, một query có `WHERE` rõ ràng dễ kiểm soát và kiểm thử hơn.

## 15. Không nên xem Hibernate Filter là lớp an ninh tenant duy nhất

Filter rất hữu ích để giảm lặp predicate, nhưng nó có những đường bypass hoặc giới hạn:

- Session có thể không bật filter nếu service quên.
- Một số load-by-key API có thể không áp dụng filter theo version.
- Entity đã managed vẫn có thể được trả từ L1.
- Native SQL không tự được chèn filter.
- Bulk writes có semantics khác với entity query.
- DTO từ JDBC/jOOQ/reports không đi qua Hibernate entity filter.
- Cache application hoặc event payload không chịu filter ORM.
- Admin code có thể tắt filter rồi đưa object cho code thường.

**Authorization tenant phải được thực thi như một quy tắc bảo mật độc lập.** Nếu phải bảo đảm không bao giờ đọc cross-tenant từ database, cần thiết kế repository predicates, schema isolation hoặc database row-level security (RLS) phù hợp, cộng với kiểm tra quyền ở tầng service.

### 15.1. Hạn chế khi chỉ dùng `@Filter` cho multi-tenancy

~~~java
session.enableFilter("tenantScope")
    .setParameter("tenantId", tenantId);
~~~

đây là opt-in mutable state. Nếu một method quên bật hoặc gọi native SQL, điều kiện có thể không được bảo đảm.

Nếu ứng dụng dùng tenant riêng theo Hibernate multi-tenancy support (tenant identifier của Session và connection/schema resolution), hãy dùng cơ chế đó đúng mục tiêu thay vì mô phỏng tất cả bằng một filter tùy ý. Dù vậy cơ chế multi-tenancy cũng phải được cấu hình/test cho mọi access path.

### 15.2. Xác định quyền ở service

~~~java
@Transactional(readOnly = true)
public OrderRow findForTenant(
        Long orderId,
        Long authenticatedTenantId) {

    PurchaseOrder order = em.createQuery("""
        select o
        from PurchaseOrder o
        where o.id = :orderId
          and o.tenantId = :tenantId
          and o.deletedAt is null
        """, PurchaseOrder.class)
        .setParameter("orderId", orderId)
        .setParameter("tenantId", authenticatedTenantId)
        .getResultStream()
        .findFirst()
        .orElseThrow(OrderNotFoundException::new);

    return OrderRow.from(order);
}
~~~

Lệnh query đặt predicate tenant rõ ràng cho việc **chọn hàng từ DB**; tuy nhiên một entity đã managed cùng ID có thể được ORM trả lại dưới state cũ. Nếu quyền hoặc soft-delete thay đổi trong lúc transaction chạy, cần transaction isolation/snapshot/business checks thích hợp. Query này vẫn không thay thế mọi authorization policy.

### 15.3. Database RLS

PostgreSQL RLS có thể giới hạn hàng ở tầng database nếu role, policy và session context được cấu hình đúng. Tuy nhiên nếu Hibernate trả entity từ L1 hoặc một provider cache mà không chạy SQL, RLS **không có cơ hội kiểm tra lại trên lần đọc ấy**.

Khi phối hợp RLS + ORM cache:

- Tách persistence context theo tenant/principal scope.
- Không truyền managed entity giữa các scope có quyền khác nhau.
- Xác định RLS role/context của connection và tránh rò rỉ qua connection pool.
- Cân nhắc hạn chế L2 cache cho dữ liệu chịu permission policy thay đổi nhanh.
- Có integration tests gồm RLS thật và các access paths qua cache.

## 16. Soft delete: filter động hay restriction tĩnh?

Một bảng có `deleted_at` có hai nhóm yêu cầu:

1. **Mặc định chỉ xem bản ghi active** ở hầu hết use cases.
2. **Một số use cases quản trị xem cả deleted** hoặc chỉ deleted.

Cần chọn mapping sao cho đường đọc bình thường được bảo vệ và đường đọc quản trị vẫn có semantics rõ.

### 16.1. @Filter cho điều kiện có thể bật/tắt

~~~java
@FilterDef(name = "activeOrders")
@Filter(
    name = "activeOrders",
    condition = "deleted_at is null"
)
@Entity
class PurchaseOrder {
    // ...
}
~~~

Ưu điểm:

- Có thể bật ở user workflow, tắt ở admin workflow.
- Có thể kết hợp với `tenantScope`.
- Phù hợp khi một Session được kiểm soát rõ và query paths đã được kiểm thử.

Rủi ro:

- Mặc định thường không bật.
- Quên bật hoặc tắt sai scope có thể trả deleted rows.
- Direct key loads và entities đã managed có các giới hạn đã nêu.
- Không phù hợp làm bảo mật duy nhất.

### 16.2. @SQLRestriction cho điều kiện tĩnh

Ở những phiên bản Hibernate 6 có hỗ trợ `@SQLRestriction`:

~~~java
@Entity
@SQLRestriction("deleted_at is null")
public class PurchaseOrder {
    // ...
}
~~~

Annotation này mô tả restriction SQL tĩnh, không có công tắc `Session.disableFilter()` để bỏ điều kiện theo ý muốn. Nó phù hợp hơn nếu **đơn đã xóa không bao giờ được truy vấn bằng entity mapping này** trong normal workflows.

Giới hạn:

- Không thể tắt dễ dàng để tạo admin view cùng entity mapping.
- Điều kiện không nhận dynamic tenant parameter như `@Filter`.
- Vẫn cần hiểu L1, native SQL và bulk DML behavior.
- Với quyền admin xem deleted, có thể cần repository/native query hoặc model/read path riêng.

Annotation `@Where` xuất hiện nhiều trong tài liệu cũ và bị deprecated trong một số Hibernate 6 versions; không sao chép hướng dẫn cũ mà bỏ qua version.

### 16.3. @SoftDelete của Hibernate

Các phiên bản Hibernate 6.4+ có `@SoftDelete` với semantics chính thức cho soft deletion, thường sử dụng cột chỉ báo thay vì viết tay mọi thao tác. Ví dụ minh họa:

~~~java
@Entity
@SoftDelete
public class CatalogItem {
    @Id
    private Long id;
}
~~~

Cách đặt column, strategy/indicator, converter và khả năng áp dụng lên entity/collection phụ thuộc Hibernate version. Không cho rằng `@SoftDelete` tự thích ứng với schema `deleted_at TIMESTAMPTZ` mà không cấu hình/chuyển đổi tương thích.

`@SoftDelete` không đơn thuần là một filter session có thể tắt. Nếu yêu cầu truy vấn deleted records, cần thiết kế query path thích hợp thay vì mặc định `disableFilter` sẽ bật chế độ xem deleted cho `@SoftDelete`.

### 16.4. @SQLDelete và mô hình cũ

Trong một số hệ thống cũ, soft delete được triển khai bằng:

~~~java
@SQLDelete(sql =
    "UPDATE purchase_orders SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?")
~~~

kết hợp `@Where`/restriction. SQL custom DELETE phụ thuộc mapping, optimistic version, tham số và dialect. Đừng copy đoạn minh họa một cách trực tiếp vào entity có `@Version` mà chưa xử lý SQL placeholders/version check đúng.

`@SQLDelete` quyết định thao tác xóa khi ORM gọi `remove`, **không phải** cơ chế lọc dữ liệu sau khi xóa. Phải xác định cả write path lẫn read visibility.

### 16.5. Chọn theo hợp đồng nghiệp vụ

| Nhu cầu | Hướng cân nhắc |
|---|---|
| Chỉ đọc active, deleted không thuộc normal entity view | `@SoftDelete` hoặc static restriction nếu phù hợp version |
| Cần bật/tắt soft delete theo transaction/use case | Dynamic `@Filter` với scope kiểm soát |
| Admin cần xem deleted trong read model riêng | Explicit SQL/DTO/repository được phân quyền |
| Chính sách tenant phải có hiệu lực trên mọi SQL | App auth + query policy, DB isolation/RLS, không chỉ filter |
| Nhiều external writers | DB constraints/triggers hoặc policy chung, không tin callback/filter đơn lẻ |

## 17. @Filter trên to-many collection và join table

Ngoài entity filter, Hibernate có thể gắn filter lên collection mapping.

### 17.1. One-to-many theo cột child

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Filter(
    name = "activeItems",
    condition = "deleted_at is null"
)
private List<OrderItem> items = new ArrayList<>();
~~~

Condition thường tham chiếu cột của bảng đích phù hợp với collection mapping. Khi collection được load trong filter scope, Hibernate có thể chèn predicate vào SQL.

### 17.2. Many-to-many và @FilterJoinTable

Một association:

~~~text
users
  <- user_roles(user_id, role_id, revoked_at) ->
roles
~~~

Nếu muốn lọc theo **cột trên join table** `revoked_at`, Hibernate cung cấp hướng `@FilterJoinTable` ở mapping phù hợp:

~~~java
@ManyToMany(fetch = FetchType.LAZY)
@JoinTable(
    name = "user_roles",
    joinColumns = @JoinColumn(name = "user_id"),
    inverseJoinColumns = @JoinColumn(name = "role_id")
)
@FilterJoinTable(
    name = "activeMembership",
    condition = "revoked_at is null"
)
private Set<Role> roles = new HashSet<>();
~~~

`@FilterDef(name = "activeMembership")` cần được khai báo. `@Filter` trên target entity và `@FilterJoinTable` trên association table không phải cùng điều kiện.

### 17.3. Không chỉ nhìn kết quả một lần

Test phải chứng minh:

- Collection **chưa initialized**, filter bật trước load.
- Collection initialized trước filter.
- Tắt filter sau initialized.
- Tải cùng dữ liệu trong Session khác.
- Thêm/xóa membership có đúng behavior write không.

### 17.4. Cảnh giác bag, fetch join và pagination

Filter chỉ giới hạn những hàng child phù hợp; nó không sửa bản chất to-many join nhân bản parent rows. `JOIN FETCH` collection kết hợp `Pageable` vẫn có thể gây pagination in memory hoặc warning của Hibernate. Nếu page root rồi fetch child, dùng kỹ thuật phân trang ID trước và fetch collection theo ID, đảm bảo filter được bật trong cả thời điểm load cần thiết.

## 18. Filter trên collection không phải một collection model mới

Một collection `order.getItems()` dưới filter activeItems có thể chứa ít phần tử hơn toàn bộ rows trên DB. Tuy nhiên đối với Hibernate, nó vẫn là persistent collection gắn với cùng owner/entity mapping.

### 18.1. Không chỉnh collection với ý định chỉ ẩn bớt UI

Nếu collection được khởi tạo với filter khiến một số rows bị ẩn, sau đó user code thêm/xóa phần tử, ORM cần quản lý snapshot/dirty actions theo semantics collection mapping. Đặc biệt với `orphanRemoval`, join table hoặc ordered collection, **không nên dùng một partially visible collection làm nền để thay thế toàn bộ membership**.

Khi cần chỉnh sửa tập con, hãy tải/kiểm tra đúng aggregate state hoặc thao tác child repository có điều kiện và transaction/locking rõ.

### 18.2. Dùng DTO cho filtered view

Một query:

~~~hql
select new com.example.app.dto.OrderItemRow(
    i.id, i.sku, i.quantity
)
from OrderItem i
where i.order.id = :orderId
  and i.deletedAt is null
order by i.id
~~~

có thể phù hợp hơn khi API chỉ cần danh sách active items mà không cần initialized collection của managed Order.

DTO read model tránh nhầm lẫn giữa “collection của entity” và “view đã lọc”, nhưng điều kiện tenant/authorization vẫn phải có khi cần.

### 18.3. Tránh phân trang một filtered collection đã initialized

Đừng load toàn bộ items rồi `.stream().skip(offset).limit(size)` nếu một Order có hàng trăm nghìn child. Filter ở SQL giúp giảm tập rows theo điều kiện, nhưng pagination child cần query riêng với `ORDER BY`, `LIMIT` và `OFFSET`/keyset.

## 19. Kết hợp nhiều filter: phép AND và sự khác biệt điều kiện

Giả sử:

- tenantScope: `tenant_id = :tenantId`
- activeOrders: `deleted_at is null`
- paidOrders: `status = 'PAID'`

Khi bật cả ba trên PurchaseOrder, về ngữ nghĩa các predicate cần cùng thỏa:

~~~sql
WHERE tenant_id = ?
  AND deleted_at IS NULL
  AND status = 'PAID'
~~~

### 19.1. Không dùng enableFilter để thay thế mọi filter input động

Nếu người dùng chọn từ ngày đến ngày, số tiền tối thiểu, trạng thái đơn, mã sản phẩm và pagination, một Criteria query/Specification có các parameter tường minh thường dễ kiểm soát hơn việc tạo hàng loạt Session filters cho mỗi input.

Filter phù hợp cho **cross-cutting visibility policy** được tái sử dụng trên nhiều query. Điều kiện đặc thù từng endpoint nên sống trong query/repository có hợp đồng rõ.

### 19.2. OR khác AND

Một yêu cầu:

~~~text
Đơn đang active hoặc đơn đã deleted trong 7 ngày gần nhất
~~~

không thể biểu diễn đơn giản bằng cách bật hai filter độc lập với điều kiện `deleted_at IS NULL` và `deleted_at >= :cutoff`, vì hai filter thường cộng lại theo AND và có thể cho tập rỗng.

Viết một predicate có OR đúng:

~~~sql
(deleted_at IS NULL OR deleted_at >= :cutoff)
~~~

trong filter cụ thể hoặc query riêng, tùy use case. Không xem nhiều filter như một hệ thống boolean expression tự động cấu hình OR giữa các filter.

### 19.3. Thứ tự bật filter không thay ngữ nghĩa cơ bản

Bật activeOrders trước tenantScope hay ngược lại thường không đổi điều kiện logic AND của SQL. Tuy nhiên **thời điểm load** vẫn quan trọng: nếu query hoặc lazy load chạy giữa hai lần bật, dữ liệu đã tải có thể không chịu đủ các điều kiện.

Vì thế nên bật và set **toàn bộ filters cần thiết trước lần query đầu tiên** trong scope.

## 20. Filter parameter và những rủi ro kiểu dữ liệu

Ví dụ parameter `tenantId`:

~~~java
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(
        name = "tenantId",
        type = Long.class
    )
)
~~~

Nó cho Hibernate biết kiểu Java/SQL binding thích hợp theo mapping/provider. Không truyền `"7"` dạng String nếu filter mong `Long`, rồi tự tin driver sẽ convert.

### 20.1. Date/time filter

~~~java
@FilterDef(
    name = "recentOrders",
    parameters = @ParamDef(
        name = "fromTime",
        type = Instant.class
    )
)
@Filter(
    name = "recentOrders",
    condition = "created_at >= :fromTime"
)
~~~

Với `TIMESTAMPTZ`, cần đảm bảo Java Instant, JDBC timezone và Hibernate dialect được cấu hình nhất quán. Dùng giá trị `fromTime` đã parse/validate trong service; không nối raw timestamp string vào condition.

### 20.2. Danh sách ID có thể rỗng

Nếu filter dùng `region_id in (:allowedRegions)`, semantics khi `allowedRegions` rỗng cần rõ: không có region được phép, hay bỏ filter? Không tự tắt filter khi danh sách rỗng nếu rỗng có nghĩa **không được xem gì**.

Nên xử lý ở service:

~~~java
if (allowedRegions.isEmpty()) {
    return List.of(); // Nếu policy là không có quyền vùng nào.
}

session.enableFilter("regionScope")
    .setParameterList("allowedRegions", allowedRegions);
~~~

Nếu dùng query không có filter cho danh sách rỗng, đó có thể là lỗi lộ dữ liệu nghiêm trọng. Cần validation kích thước danh sách và test với database/dialect mục tiêu.

### 20.3. Alias SQL trong điều kiện phức tạp

Với filter trên entity có JOIN/subquery, Hibernate có cơ chế alias injection và các tùy chọn cho SQL fragment aliases ở một số annotation/versions. Một condition không rõ cột thuộc bảng nào có thể gây ambiguous column.

Ví dụ hai bảng đều có `deleted_at`; condition `deleted_at is null` được đưa vào một SQL join phức tạp có thể cần alias đúng. Khi cần điều kiện phức tạp, kiểm tra SQL Hibernate sinh ra, dùng cơ chế alias được hỗ trợ hoặc viết repository query rõ ràng. Đừng nối trực tiếp một alias SQL do bạn đoán như `o.deleted_at` vào annotation nếu provider không bảo đảm alias `o`.

## 21. Bulk HQL/native DML không giống entity filtering

Hibernate Filter thường được bàn đến ở đường **SELECT/load**. Nhưng ghi dữ liệu có những đường khác:

~~~java
entityManager.createQuery("""
    update PurchaseOrder o
    set o.status = :status
    where o.createdAt < :cutoff
    """)
    .setParameter("status", "ARCHIVED")
    .setParameter("cutoff", cutoff)
    .executeUpdate();
~~~

Hoặc:

~~~sql
UPDATE purchase_orders
SET status = 'ARCHIVED'
WHERE created_at < :cutoff;
~~~

Không được mặc định filter đang bật trong Session sẽ chèn tenant/deleted predicates vào **mọi** bulk HQL/SQL UPDATE hoặc DELETE. Hành vi cụ thể có thể khác nhau theo Hibernate version và loại DML; SQL native được bạn cung cấp là một câu SQL riêng.

### 21.1. Ghi điều kiện tenant trực tiếp vào bulk DML

Nên:

~~~hql
update PurchaseOrder o
set o.status = :status
where o.tenantId = :trustedTenantId
  and o.deletedAt is null
  and o.createdAt < :cutoff
~~~

với trustedTenantId từ auth context. Đối với bulk operations, phải kiểm tra số rows affected và business preconditions/authorization.

### 21.2. Native SQL là đường bypass rõ ràng

~~~java
entityManager.createNativeQuery("""
    select *
    from purchase_orders
    where id = :id
    """)
    .setParameter("id", id)
    .getResultList();
~~~

SQL này **không tự thêm** `tenant_id = :tenantId` chỉ vì bạn đã bật `tenantScope` trên Hibernate Session. Nếu source of truth là native SQL, mọi predicate cần được thiết kế trong SQL hoặc DB policy tương ứng.

### 21.3. Bulk DML có thể làm L1 stale

Sau bulk UPDATE:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
// Entity managed với status cũ.

em.createQuery("""
    update PurchaseOrder o
    set o.status = 'ARCHIVED'
    where o.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();

// order object có thể vẫn giữ status cũ trong L1.
~~~

Filter bật/tắt không sửa state cũ này. Cần chọn refresh/clear/new context với hiểu biết về pending changes và authorization. Đồng thời bulk DML có thể bypass entity callbacks và optimistic version semantics nếu câu lệnh không xử lý rõ.

## 22. Xóa mềm là thay đổi dữ liệu, không chỉ là filter

Một thao tác xóa mềm có thể là:

~~~java
@Transactional
public void softDelete(
        Long id,
        Long authenticatedTenantId) {

    PurchaseOrder order = repository
        .findVisibleForTenant(id, authenticatedTenantId)
        .orElseThrow();

    order.markDeleted(Instant.now());
}
~~~

`findVisibleForTenant` phải có predicate tenant/visibility rõ; `markDeleted` là domain method cập nhật `deletedAt` và các invariants. Với entity managed, dirty checking phát UPDATE khi flush.

### 22.1. Filter không tự cập nhật deleted_at

Bật `activeOrders` chỉ định cách **đọc**; nó không làm `entityManager.remove(order)` biến thành UPDATE trừ khi mapping soft-delete behavior (ví dụ `@SoftDelete`, custom SQL DELETE hoặc application service) được cấu hình.

### 22.2. Xóa mềm đã update DB nhưng entity vẫn managed

Sau:

~~~java
order.markDeleted(now);
em.flush();
~~~

object `order` vẫn có thể nằm trong L1 với `deletedAt != null`. Bật `activeOrders` sau đó không detach object; đây là trường hợp rất phổ biến ngay sau khi xóa mềm trong cùng service.

Nếu tiếp tục truy cập/order.getItems() trong cùng transaction, cần hiểu authorization và filter scope riêng, không mặc định đối tượng đã bị xóa mềm “không thể truy cập nữa”.

### 22.3. Soft delete và unique constraints

Nếu business cho phép tạo lại `order_number` sau khi đơn cũ đã bị xóa mềm, UNIQUE(tenant_id, order_number) trên toàn bảng có thể chặn INSERT. PostgreSQL có thể dùng partial unique index:

~~~sql
CREATE UNIQUE INDEX uk_active_order_number_per_tenant
ON purchase_orders(tenant_id, order_number)
WHERE deleted_at IS NULL;
~~~

Đây là quyết định DDL/migration, không phải đặc tính của filter. Nếu constraint UNIQUE toàn bảng cũ vẫn tồn tại, phải xử lý migration/cleanup trước khi thêm partial index để đạt business semantics mới.

### 22.4. Không dùng filter để che dữ liệu vi phạm constraint

Một bản ghi bị xóa mềm vẫn tồn tại trên database. FK, CHECK, UNIQUE và transaction rules vẫn có hiệu lực theo DDL. Filter không làm hàng bị xóa vật lý hoặc giải quyết xung đột dữ liệu đã tồn tại.

## 23. Second-level cache và query cache: thêm một lớp cần hiểu

L1 đã đủ gây bất ngờ, nhưng L2/query cache cũng đáng chú ý.

### 23.1. L2 không phải filter theo user

Second-level cache của Hibernate có thể lưu entity state qua nhiều Sessions. Filter được áp dụng trên những load paths phù hợp; không nên giả định một entry trong L2 được “gắn quyền của user đang đọc”.

Trong ứng dụng multi-tenant, phải xác minh cache keys, session tenant identifier và isolation phù hợp. Nếu bạn tự mô phỏng tenant bằng mutable `@Filter` thay vì Hibernate multi-tenancy strategy, **không dùng L2 cache làm lập luận rằng cross-tenant object access đã được bảo vệ**.

### 23.2. L1 có thể thắng trước khi đến L2

Nếu Order 102 đang managed trong Session, không có lợi ích gì từ việc kiểm tra L2 hoặc SQL filter khi `find(102)` trả object từ L1. Vì vậy evict L2 không giải quyết object đã managed.

### 23.3. Query cache cần test filter parameters

Khi Hibernate query cache được bật và một query được đánh dấu cacheable, filter state/parameters có thể ảnh hưởng cache key hoặc tính hợp lệ của cached results theo version/implementation. Không giả định mọi query cache region tự tách user/tenant đúng kỳ vọng.

Test cụ thể:

- Cùng HQL với tenant 7 và tenant 8 phải cho kết quả tách biệt.
- Bật/tắt activeOrders không được dùng nhầm cached result set.
- Data changes phải được invalidation phù hợp.
- Kết quả loaded qua cache vẫn phải tuân thủ authorization business.

Khi tính đúng đắn bảo mật quan trọng hơn hiệu năng, cân nhắc tắt query cache cho truy vấn nhạy cảm hoặc dùng cơ chế tenant isolation được provider hỗ trợ và kiểm thử kỹ.

### 23.4. Cache ứng dụng còn nằm ngoài Hibernate

Nếu service `@Cacheable` (Spring Cache) trả `OrderRow` theo key chỉ gồm `orderId`, user tenant 8 có thể nhận DTO đã cache từ tenant 7 nếu method/authorization/key sai. Hibernate Filter không thể sửa lỗi này. Cache key và authorization scope phải được thiết kế ở tầng cache application riêng.

## 24. Transaction isolation và tính nhất quán của filter

Filter chỉ quyết định predicate tại thời điểm query/load. Nó không tạo snapshot bất biến hoặc chống concurrent writes.

Ví dụ:

~~~text
T1 bật activeOrders và query Order 101 (deleted_at NULL).
T2 soft-delete Order 101 rồi commit.
T1 vẫn có managed Order 101.
T1 bật lại activeOrders, đọc Order 101 từ L1.
~~~

Ngay cả khi database đã đổi, entity đang managed trong T1 không tự refresh.

### 24.1. READ COMMITTED

Trong PostgreSQL READ COMMITTED, các SELECT khác nhau có thể nhìn thấy committed snapshots khác nhau; một query list sau khi T2 commit có thể không còn trả Order 101, nhưng T1 vẫn có managed Order 101.

### 24.2. REPEATABLE READ

Trong REPEATABLE READ của PostgreSQL, cùng transaction thường nhìn snapshot ổn định hơn cho database reads, nhưng L1 vẫn là identity map riêng. Filter không thay thế isolation, còn transaction dài có thể gây pressure tài nguyên/MVCC.

### 24.3. Không dùng filter để “khóa” quyền đọc

Nếu quyền truy cập bị thu hồi khi transaction đang xử lý, filter đã bật với parameter cũ không tự nhận policy mới. Với các tác vụ nhạy cảm, cần authorization checks theo contract, transaction boundary phù hợp và không chia sẻ managed object giữa các user scopes.

## 25. Đăng ký filter ở nhiều entity và consistency theo graph

Hệ thống lớn có:

~~~text
Tenant
  -> Customer
      -> PurchaseOrder
          -> OrderItem
          -> Shipment
~~~

Nếu `tenantScope` chỉ gắn trên PurchaseOrder, một query độc lập `select c from Customer c` có thể không chịu điều kiện đó.

### 25.1. Xác định mọi entry point

Liệt kê các đường truy cập:

1. Root HQL/Criteria query.
2. Repository `findById`.
3. Lazy `@ManyToOne` và `@OneToMany`.
4. Named queries và native queries.
5. Batch/subselect loads.
6. DTO projections.
7. Bulk UPDATE/DELETE.
8. Cache và external integrations.

Mỗi đường có thể cần predicate/authorization riêng. Không suy luận “đã gắn filter trên Order là toàn bộ object graph an toàn”.

### 25.2. FK tham chiếu chéo tenant là lỗi dữ liệu

Nếu Order tenant 7 có customer_id trỏ tới Customer tenant 8, một filter có thể làm query hiển thị thiếu Customer nhưng không sửa ràng buộc nghiệp vụ sai. Cần enforce consistency ở service và nếu khả thi ở database bằng composite FK/unique keys hoặc schema isolation thích hợp.

### 25.3. Đừng để filter ẩn lỗi thiết kế dữ liệu

Một query trả ít rows hơn khi bật active filter có thể do dữ liệu soft-deleted hợp lệ; cũng có thể do join, FK sai, alias condition hoặc association missing. Debug bằng SQL, database query và domain invariants, không tắt filter rồi tự mặc định mọi dữ liệu ẩn đều không quan trọng.

## 26. Thiết kế repository query rõ ràng khi quyền cần chắc chắn

Đối với các endpoint quan trọng, explicit predicate thường dễ audit hơn Session filter mutable state.

~~~java
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where o.id = :id
          and o.tenantId = :tenantId
          and o.deletedAt is null
        """)
    Optional<PurchaseOrder> findActiveForTenant(
        @Param("id") Long id,
        @Param("tenantId") Long tenantId
    );

    @Query("""
        select o
        from PurchaseOrder o
        where o.tenantId = :tenantId
          and o.deletedAt is not null
        order by o.deletedAt desc, o.id desc
        """)
    List<PurchaseOrder> findDeletedForAdmin(
        @Param("tenantId") Long tenantId
    );
}
~~~

### 26.1. Khi nào vẫn dùng @Filter?

- Có nhiều HQL/Criteria queries dùng cùng một visibility rule.
- Service có transaction scope rõ và luôn set parameter trước tải dữ liệu.
- Các load paths cần filter đã được integration-test trên Hibernate version thực tế.
- Filter không bị xem là nguồn authorization duy nhất.
- Có cơ chế tách context cho admin/user và tenant changes.

### 26.2. Khi nào explicit query phù hợp hơn?

- Một endpoint cần quyền truy cập theo tenant chính xác.
- Chỉ có vài truy vấn và visibility rule đơn giản.
- Có nhiều chế độ admin/restore/soft delete khác nhau.
- Query phải chạy native SQL hoặc bulk DML.
- Cần kiểm tra rõ query có predicate tenant hay không.

### 26.3. DTO tốt hơn trả entity ở API boundary

DTO có thể giữ một snapshot giá trị cụ thể trong thời điểm được tạo. Nó không kéo theo lazy association sau khi filter bị disable hoặc EntityManager đóng.

Điều này giảm nguy cơ serializer làm query ngoài scope. Tuy vậy DTO đã được tạo cũng không tự hủy khi quyền thay đổi: API vẫn cần authorization tại thời điểm phục vụ request và chính sách cache/retention phù hợp.

## 27. Spring service quản lý filter scope có chủ đích

Một pattern thực tế là **chỉ sử dụng Session trong một transaction ngắn**, tạo DTO trước khi thoát scope:

~~~java
@Service
public class OrderQueryService {
    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public List<OrderRow> listActive(
            Long trustedTenantId) {

        Session session = em.unwrap(Session.class);
        session.enableFilter("tenantScope")
            .setParameter("tenantId", trustedTenantId);
        session.enableFilter("activeOrders");

        try {
            List<PurchaseOrder> orders =
                em.createQuery("""
                    select o
                    from PurchaseOrder o
                    order by o.createdAt desc, o.id desc
                    """, PurchaseOrder.class)
                    .setMaxResults(100)
                    .getResultList();

            return orders.stream()
                .map(o -> new OrderRow(
                    o.getId(), o.getTenantId()
                ))
                .toList();
        } finally {
            session.disableFilter("activeOrders");
            session.disableFilter("tenantScope");
        }
    }
}

public record OrderRow(Long id, Long tenantId) {}
~~~

Ví dụ chỉ map scalar không đụng lazy associations. Nếu cần items, phải quyết định fetch plan/child query và filter scope tương ứng.

### 27.1. Không lạm dụng enable/disable nhiều lần

Nếu một service tự bật tenantScope nhưng được gọi bên trong một service khác cũng đã bật tenantScope với parameter khác, `finally` của method con có thể **tắt filter của method cha**. Filter state thuộc chung Session, nên nested scopes không tự có stack push/pop.

Ví dụ nguy hiểm:

~~~text
Outer: enable tenantScope(tenant 7)
  Inner: enable tenantScope(tenant 8)
  Inner: finally disable tenantScope
Outer: query tiếp -> không còn filter
~~~

**try/finally không tự giải quyết reentrant/nested filter scope** nếu nhiều layer cùng sở hữu filter. Thường nên có **một owner duy nhất** cho filter config ở transaction boundary.

### 27.2. Nested filter scope cần policy

Nếu framework nội bộ cung cấp helper `withTenantFilter`, helper phải:

- Biết filter đã bật trước đó hay chưa.
- Không ghi đè tenant parameter ngoài ý muốn.
- Chỉ tắt filter nếu nó là bên bật filter.
- Cấm chuyển tenant trong cùng persistence context nếu có entity managed.
- Có tests cho nested calls/exceptions.

API `Session.getEnabledFilter(name)` có thể giúp kiểm tra trạng thái filter tùy phiên bản; không có cơ chế “push old filter state” hoàn chỉnh tự động ở mọi phiên bản. Một chính sách đơn giản hơn là **không cho nested override**; tenant scope immutable trong toàn use case.

### 27.3. Tránh self-invocation và transaction scope sai

Với Spring proxy-based `@Transactional`, gọi một annotated method từ `this.method()` có thể bypass proxy nên không tạo transaction như mong muốn. Nếu helper filter chạy trước khi transaction-bound EntityManager được thiết lập, code có thể cấu hình sai Session.

Đặt `@Transactional` trên service method được gọi qua Spring bean/proxy và test integration rằng Session filter được bật trên chính Session thực thi query.

## 28. Admin xem dữ liệu đã xóa: lựa chọn an toàn hơn tắt tất cả filter

Admin có thể cần:

~~~text
GET /admin/tenants/7/orders/deleted
~~~

Yêu cầu này khác hoàn toàn:

~~~text
GET /orders?includeDeleted=true&tenantId=7
~~~

Nếu chỉ có query parameter `includeDeleted` và service tắt filter theo input chưa kiểm tra quyền, một user có thể tự bật chế độ admin.

### 28.1. Kiểm tra quyền trước khi chọn view

~~~java
@PreAuthorize("hasAuthority('ORDERS_VIEW_DELETED')")
@Transactional(readOnly = true)
public List<DeletedOrderRow> listDeleted(
        Long trustedTenantId) {

    return repository.findDeletedForAdmin(trustedTenantId)
        .stream()
        .map(DeletedOrderRow::from)
        .toList();
}
~~~

Đoạn code yêu cầu Spring Security/method security config và DTO implementation tương ứng. Nó thể hiện ý tưởng **quyền được xác minh trước khi query deleted**.

### 28.2. Không trả managed objects của admin context tới user context

Nếu một admin method đã load Order 102 (deleted), rồi truyền entity Java đó cho một service user được bật activeOrders, service user có thể đọc fields trực tiếp mà không đi qua SQL filter. Đừng dùng entity reference như một capability token chứng minh quyền.

Tốt hơn là truyền ID hoặc DTO đã được authorization rõ, và nếu cần load lại ở user context thì làm trong context/transaction độc lập với predicate bắt buộc.

### 28.3. Restore soft-deleted entity

Khôi phục một Order bị xóa mềm là **write workflow**. Một query admin riêng có thể tìm deleted row theo tenant, kiểm tra quyền, rồi update `deletedAt = null` với optimistic locking/constraints.

Không chỉ:

~~~java
session.disableFilter("activeOrders");
PurchaseOrder order = em.find(PurchaseOrder.class, id);
order.setDeletedAt(null);
~~~

nếu bạn chưa xác minh direct find, tenant, trạng thái managed và uniqueness constraints. Restore cần kiểm tra business rules: ví dụ order number có thể đã được tái sử dụng sau soft-delete và việc restore sẽ vi phạm partial unique index.

## 29. SQL logging và cách xác nhận filter thực sự áp dụng

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

Không bật TRACE bind parameters mặc định trong production vì log có thể chứa tenant IDs, dữ liệu khách hàng và thông tin nhạy cảm.

### 29.1. Các dấu hiệu đúng

Khi query list chạy dưới tenantScope/activeOrders, SQL mong đợi có predicate:

~~~sql
... WHERE ... tenant_id = ? AND ... deleted_at IS NULL
~~~

Khi filter tắt trong một Session mới, SQL list có thể không còn predicate này.

### 29.2. Những điều SQL log không nói đủ

Nếu `em.find()` trả từ L1, không có SQL để kiểm tra predicate. Nếu một collection đã initialized, việc đọc lại `size()` cũng không tạo SQL. Đây là bằng chứng của **cache/context reuse**, không phải bằng chứng filter được áp dụng.

### 29.3. Hibernate Statistics

~~~java
SessionFactory sf =
    entityManagerFactory.unwrap(SessionFactory.class);
Statistics stats = sf.getStatistics();

long before = stats.getPrepareStatementCount();
// Chạy một use case trong test cô lập.
long delta = stats.getPrepareStatementCount() - before;
~~~

Statistics là bộ đếm cấp SessionFactory, có thể chịu ảnh hưởng bởi thread khác. Dùng SQL capture khi cần assert một predicate cụ thể trong generated SQL; counter delta chỉ hỗ trợ đo số statements.

### 29.4. Cẩn thận với plan cache và SQL aliases

Hibernate filter parameter có thể làm SQL thay đổi theo filter state. PostgreSQL query planner có thể sử dụng plan khác cho query có predicate tenant/soft-delete. Việc bật filter không bảo đảm query nhanh hơn nếu index/cardinality không phù hợp. Đo plan bằng `EXPLAIN (ANALYZE, BUFFERS)` trên database test với dữ liệu đại diện.

## 30. Index cho tenant và soft delete

Một query:

~~~sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE tenant_id = 7
  AND deleted_at IS NULL
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

có thể được hỗ trợ bằng partial index:

~~~sql
CREATE INDEX idx_orders_active_per_tenant
ON purchase_orders(
    tenant_id,
    created_at DESC,
    id DESC
)
WHERE deleted_at IS NULL;
~~~

### 30.1. Filter quyết định điều kiện, index quyết định chi phí

`@Filter` không tự tạo index hoặc chọn plan tốt. Với hàng triệu orders, thiếu index có thể làm SELECT chậm dù filter đúng.

### 30.2. Query admin đọc deleted dùng index khác

~~~sql
SELECT id, deleted_at
FROM purchase_orders
WHERE tenant_id = 7
  AND deleted_at IS NOT NULL
ORDER BY deleted_at DESC, id DESC
LIMIT 50;
~~~

Với workload admin thường xuyên, có thể cân nhắc index riêng:

~~~sql
CREATE INDEX idx_orders_deleted_per_tenant
ON purchase_orders(
    tenant_id,
    deleted_at DESC,
    id DESC
)
WHERE deleted_at IS NOT NULL;
~~~

Không tạo mọi index minh họa một cách máy móc: index có chi phí write/storage. Dùng `EXPLAIN ANALYZE`, thống kê dữ liệu và business SLA để quyết định.

### 30.3. Không quên index cho child filtering

Nếu `order_items` load theo `order_id` và `deleted_at IS NULL`, một partial index trên `order_id` của active child có thể hữu ích. Nhưng nếu query cần sort theo lineNumber, có thể cần index hỗ trợ cả sort; chọn theo SQL thực.

## 31. Integration test cần có hai trục: filter state và persistence context state

Test đơn giản “bật filter rồi findAll thấy ít hàng” **chưa đủ**. Cần ít nhất hai biến:

1. Filter đang bật hay tắt.
2. Entity/collection đã được load trước đó hay chưa.

### 31.1. Ma trận chính

| Trường hợp | Bối cảnh | Điều cần quan sát |
|---|---|---|
| A | Session mới, bật filter trước query list | SQL có predicate, kết quả đúng |
| B | Session mới, filter tắt | Query list theo hợp đồng không filter |
| C | Entity deleted đã managed, rồi bật filter | `find` có thể trả managed object từ L1 |
| D | Collection initialized trước filter | Bật filter không thay đổi collection đã có |
| E | Collection initialized dưới filter, rồi tắt | Tắt không tự nạp những item bị ẩn |
| F | HQL list dưới filter, entity ID trước đó đã managed | Query lọc keys; instance managed có thể tái sử dụng |
| G | Direct load-by-key trong Session mới | Xác định behavior theo Hibernate version |
| H | Lazy to-one reference với filter | Kiểm tra load-by-key và exception/null semantics |
| I | Native SQL trong Session có filter | Native SQL không tự chèn Hibernate filter |
| J | Bulk DML và managed entity | Không mặc định DML chịu filter; L1 có thể stale |
| K | Hai tenants cùng query shape | Không lộ dữ liệu qua filters/caches |
| L | Nested service enable/disable | Không tắt scope của outer service |
| M | OSIV hoặc extended context | Không làm lazy load ngoài filter scope |
| N | Transaction rollback/soft-delete | State sau rollback và Session mới đúng |

### 31.2. Dữ liệu fixture

Tạo:

~~~text
Order 101 tenant=7 deleted_at=NULL
Order 102 tenant=7 deleted_at=2026-01-10
Order 103 tenant=8 deleted_at=NULL
Order 104 tenant=8 deleted_at=2026-02-01

Order 101:
  Item 201 active
  Item 202 deleted
~~~

Fixture nên được commit, sau đó test dùng EntityManager/transaction **mới**. Nếu test tạo fixture và query trong cùng persistence context, L1 có thể che hành vi filter.

### 31.3. Test SQL query list trong Session mới

~~~java
@Test
void filtersListForTenantAndActiveState() {
    try (Session session = sessionFactory.openSession()) {
        session.enableFilter("tenantScope")
            .setParameter("tenantId", 7L);
        session.enableFilter("activeOrders");

        List<Long> ids = session.createQuery("""
            select o.id
            from PurchaseOrder o
            order by o.id
            """, Long.class).getResultList();

        assertEquals(List.of(101L), ids);
    }
}
~~~

Đây là test skeleton giả định fixture IDs được định trước. Khi dùng generated identity, test nên lấy ID thực từ fixture hoặc seed SQL có ID cố định để không phụ thuộc sequence value. Session đọc đơn giản có thể không cần explicit transaction với một số setup, nhưng integration test production nên quản lý transaction/isolation rõ.

### 31.4. Test L1 không tự bị lọc lại

~~~java
@Test
void enablingFilterDoesNotEvictManagedOrder() {
    try (Session session = sessionFactory.openSession()) {
        PurchaseOrder loaded = session.find(
            PurchaseOrder.class, deletedOrderId);
        assertNotNull(loaded);

        session.enableFilter("activeOrders");

        PurchaseOrder again = session.find(
            PurchaseOrder.class, deletedOrderId);
        assertSame(loaded, again);
    }
}
~~~

Kết quả test dựa trên việc `loaded` đã được managed, không phải lời bảo đảm về filter on load-by-key ở Session mới. Đây là case cốt lõi của bài.

### 31.5. Test collection đã initialized

~~~java
@Test
void initializedCollectionIsNotRefiltered() {
    try (Session session = sessionFactory.openSession()) {
        PurchaseOrder order = session.find(
            PurchaseOrder.class, orderId);

        int allCount = order.getItems().size();
        // Load collection khi activeItems chưa bật.

        session.enableFilter("activeItems");
        int afterEnable = order.getItems().size();

        assertEquals(allCount, afterEnable);
    }
}
~~~

Nếu collection có cache, association mapping hoặc default filter khác, cần làm test cô lập. Điều quan trọng là xác minh **không có reload tự động**.

### 31.6. Test context mới khi đổi mode

~~~java
List<Long> activeIds;
try (Session active = sessionFactory.openSession()) {
    active.enableFilter("activeOrders");
    activeIds = active.createQuery("""
        select o.id from PurchaseOrder o
        order by o.id
        """, Long.class).getResultList();
}

List<Long> allIds;
try (Session admin = sessionFactory.openSession()) {
    allIds = admin.createQuery("""
        select o.id from PurchaseOrder o
        order by o.id
        """, Long.class).getResultList();
}
~~~

Trong project thật phải thêm tenant predicate/filter và authorization policy trước khi cho admin query; skeleton chỉ minh họa **hai Session độc lập** có state riêng.

## 32. Test security không chỉ bằng Hibernate Filter

Một test bảo mật tốt cần thử mọi access path:

- `findById` hoặc `getReference` cho ID của tenant khác.
- Query list, Criteria/Specification, pagination.
- Lazy to-one/to-many associations.
- Native SQL, JDBC/jOOQ adapters.
- Bulk UPDATE/DELETE theo ID.
- Query result cache và application cache.
- Service nhận entity detached từ tầng khác.
- Admin mode sau user mode và ngược lại.
- Async worker có tenant context riêng.

### 32.1. Assertion theo chính sách

Ví dụ tenant 7 không được nhận Order 103 của tenant 8:

~~~java
assertThrows(AccessDeniedException.class, () ->
    orderService.getForTenant(103L, 7L));
~~~

Nhưng không nên chỉ assert exception từ Hibernate `@Filter`. Service có thể trả not-found/forbidden theo policy; quan trọng là không lộ dữ liệu khác tenant qua bất kỳ API path nào.

### 32.2. Nếu dùng RLS, test bằng DB role/context thật

Các test chạy với owner/superuser có thể bypass chính sách RLS trong PostgreSQL tùy cấu hình. Phải test role giống runtime app và cơ chế thiết lập tenant context thực tế. Không suy luận từ test Hibernate filter rằng RLS đã hoạt động.

## 33. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Bật filter rồi find vẫn trả deleted entity | Entity đã managed ở L1 | Dùng context mới, không coi filter là access-control check |
| Tắt activeItems nhưng collection vẫn thiếu deleted item | Collection initialized dưới filter | Tải lại qua context mới hoặc query riêng |
| Bật activeItems mà collection vẫn chứa item deleted | Collection initialized trước filter | Không mong refilter; dùng DTO/query phù hợp |
| Query list không có tenant predicate | Filter chưa được enable/set parameter hoặc không gắn mapping | Kiểm tra Session, annotation, SQL log |
| Native query đọc được deleted rows | Hibernate filter không tự sửa SQL native | Ghi predicate trực tiếp hoặc DB policy |
| Direct find bỏ qua filter | Load-by-key khác HQL/filter behavior | Test version, chọn explicit query/authorization |
| To-one association lỗi khi filter theo key | FK trỏ tới entity bị filter che | Thiết kế association/visibility hợp lệ |
| Sau admin query, user thấy dữ liệu admin | Same persistence context hoặc filter tắt sai scope | Separate context, không truyền managed entity |
| Service B bị filter tenant của Service A | Quên disable hoặc nested scopes | Có owner duy nhất, try/finally và test |
| Inner service tắt filter của outer | Filter state không có push/pop tự động | Cấm nested overrides/restore state có kiểm soát |
| Lazy association load khi filter đã tắt | DTO mapping/serialization quá muộn | Map DTO trong filter scope |
| Row filter làm user tưởng đã được phân quyền | Filter chỉ là ORM load policy | Authorization + query predicates/RLS |
| @Filter trên Order nhưng Item query lộ data | Filter không tự trải qua mọi entity | Thiết kế mọi entry point |
| @Filter bị xung đột alias | Condition không resolve column/alias | Kiểm tra generated SQL/alias options |
| `IN` filter với danh sách rỗng lộ rows | Code tắt filter khi list rỗng | Fail closed/return empty theo policy |
| Bật filter tenant nhưng cache vẫn có dữ liệu sai | Cache/context scope không được thiết kế | Isolate tenant/context/cache và test |
| Soft-delete rồi find lại vẫn thấy Order | Order vẫn managed sau UPDATE | Hiểu L1; query/transaction mới |
| Bulk UPDATE ảnh hưởng nhiều tenant | Tin filter sẽ áp dụng cho mọi DML | Predicate tenant explicit ở DML |
| Filter đúng nhưng query chậm | Thiếu index/cardinality không tốt | EXPLAIN ANALYZE và index |
| Admin không restore được record | Static restriction hoặc @SoftDelete cấm normal load | Admin write path riêng được phân quyền |
| @SQLRestriction không tắt được | Restriction tĩnh, không phải @Filter | Chọn dynamic filter hoặc query admin riêng |
| Query cache gây kết quả sai kỳ vọng | Cache key/invalidation/filter state chưa được test | Cô lập cache, kiểm tra parameters và regions |

## 34. Bài thực hành từng bước

### Bài A — Bật/tắt filter cơ bản

1. Tạo bảng `purchase_orders` có `tenant_id` và `deleted_at`.
2. Seed hai tenants, mỗi tenant có active/deleted orders.
3. Khai báo `tenantScope` và `activeOrders`.
4. Bật cả hai trong Session mới và truy vấn danh sách.
5. Tắt riêng activeOrders, giữ tenantScope, so sánh kết quả.
6. Tắt tenantScope và giải thích tại sao đây không phải quyền của user thường.

### Bài B — Persistence context đã có entity

1. Tạo một deleted Order và commit fixture.
2. Mở Session không filter, gọi `find` để entity được managed.
3. Bật activeOrders và gọi `find` cùng ID.
4. Kiểm tra cùng Java reference và số SQL.
5. Đóng Session, mở Session mới bật filter trước query.
6. So sánh HQL query và direct key load theo Hibernate version.

### Bài C — Collection initialized trước/sau filter

1. Một Order có hai Items, một active, một deleted.
2. Session A đọc `order.items.size()` trước khi bật activeItems.
3. Bật filter và đọc lại: không có reload.
4. Session B bật filter trước khi khởi tạo items.
5. Đọc items, xác nhận chỉ những row phù hợp.
6. Tắt filter, đọc lại same collection, giải thích vì sao không có thêm item.

### Bài D — Spring transaction scope

1. Viết service @Transactional đọc orders sau enableFilter.
2. Tạo try/finally để disableFilter.
3. Cố ý cho query ném exception, xác nhận filter state được cleanup.
4. Viết nested service cố override cùng tenant filter.
5. Giải thích vì sao inner disable có thể phá outer scope.
6. Refactor để chỉ một lớp sở hữu filter configuration.

### Bài E — OSIV và lazy load

1. Tạo endpoint trả entity Order với lazy items.
2. Bật filter trong service rồi tắt trước serialization.
3. Quan sát SQL/lazy load trong web layer khi OSIV bật.
4. Refactor service trả DTO đã map dưới filter scope.
5. Kiểm tra SQL không xảy ra trong serializer.
6. Đánh giá tắt OSIV theo kiến trúc.

### Bài F — Native SQL và bulk DML

1. Bật tenantScope trong Session.
2. Chạy HQL SELECT và xem SQL.
3. Chạy native SELECT không có tenant predicate, xem sự khác biệt.
4. Chạy bulk HQL UPDATE trên DB test và đo số rows affected.
5. Thêm tenant predicate tường minh vào DML.
6. Kiểm tra entity managed có thể stale sau bulk DML.

### Bài G — Soft-delete strategy

1. Dùng dynamic activeOrders filter.
2. Thử admin query xem deleted records trong Session khác.
3. Thay thử bằng `@SQLRestriction` ở branch test, quan sát không disable được.
4. Nếu Hibernate version hỗ trợ, thử `@SoftDelete` trên entity riêng.
5. So sánh cách thực hiện DELETE và read visibility của từng strategy.
6. Viết kế hoạch restore một soft-deleted Order có conflict unique index.

### Bài H — Multi-tenant security

1. Seed tenant 7 và tenant 8 với cùng loại dữ liệu.
2. Test mọi repository entry point chỉ trả tenant được phép.
3. Test direct ID loading và lazy association.
4. Test read path native SQL/JDBC.
5. Test entity/cached DTO không được truyền từ admin scope sang user scope.
6. Nếu dùng RLS, chạy test với database role không bypass policy.

### Bài I — Hiệu năng

1. Tạo 100.000 Orders với tỷ lệ active/deleted đại diện.
2. Chạy query tenant/active có và không có partial index.
3. Dùng `EXPLAIN (ANALYZE, BUFFERS)`.
4. Theo dõi SQL count, memory và latency khi collection lazy load.
5. Thử pagination hai bước ID-first khi fetch collection.
6. Xác định trade-off giữa filter, explicit predicate và DTO projection.

## 35. Checklist trước khi đưa filter vào production

1. **Filter có mục đích gì?** Soft delete hiển thị hay ràng buộc truy cập dữ liệu?
2. Nếu liên quan tenant/authorization, đã có lớp bảo mật không phụ thuộc `@Filter` chưa?
3. `@FilterDef` và `@Filter` đã gắn đúng entities/collections chưa?
4. Filter có cần bật mặc định không? Ai chịu trách nhiệm enable và set parameter?
5. Parameter tenant có đến từ context được xác minh không?
6. Có bật tất cả filters **trước lần query/lazy load đầu tiên** không?
7. Có một owner duy nhất quản lý filter trong transaction không?
8. Nested calls có thể override/tắt filter của outer scope không?
9. Mọi lỗi đều cleanup state bằng `finally` thích hợp không?
10. Có entity đã managed trước khi bật filter không?
11. Có collection đã initialized trước khi bật hoặc tắt filter không?
12. Direct `find`/`getReference`/to-one association đã được test theo Hibernate version không?
13. Có dùng OSIV/extended context/async làm thay đổi Session lifecycle không?
14. Mọi DTO có được map khi filter còn áp dụng cho lazy loads không?
15. Có native SQL/bulk DML/JDBC làm bypass filter không?
16. Tenant/soft-delete predicates có được đưa vào write operations phù hợp không?
17. Soft-delete strategy (`@Filter`, `@SQLRestriction`, `@SoftDelete`) có đúng nhu cầu admin/restore không?
18. Entity/collection/query/application caches có tách scope và invalidation đúng không?
19. Có cần PostgreSQL RLS hoặc database-level isolation không?
20. Dữ liệu khác tenant có thể bị lộ qua detached references/API cache không?
21. Query filter có index và plan phù hợp không?
22. Đã có integration tests với context mới **và** context đã có entity/collection chưa?
23. Đã kiểm thử rollback, concurrent soft delete và transaction isolation chưa?
24. Đã kiểm tra SQL log không phát sinh query ngoài filter scope chưa?

## 36. Tổng kết: filter thay đổi câu truy vấn, không thay đổi quá khứ của context

~~~mermaid
flowchart TD
    A[Cần đổi bộ lọc truy vấn] --> B{Context đã có entity/collection liên quan?}
    B -->|Chưa| C[Bật filter trước load]
    C --> D[Query/lazy load phù hợp có predicate filter]
    B -->|Có| E[Filter không tự refilter managed state]
    E --> F{Cần đổi visibility mode?}
    F -->|Có| G[Ưu tiên Session/EntityManager mới và auth rõ]
    F -->|Không| H[Dùng managed state đúng scope, không suy ra filter sẽ reload]
    G --> I[Map DTO và đóng scope]
    D --> I
~~~

Những nguyên tắc quan trọng nhất:

1. **`@FilterDef` khai báo filter; `@Filter` gắn điều kiện; `Session.enableFilter`/ `disableFilter` điều khiển state trên Session.**
2. **Filter áp dụng khi Hibernate tạo SQL hoặc tải dữ liệu qua các path được hỗ trợ**, không phải một phép biến đổi trực tiếp trên mọi Java object trong persistence context.
3. **Entity đã managed trong first-level cache vẫn có thể được truy cập sau khi bật filter**. Một `find()` có thể trả lại cùng instance mà không chạy SQL.
4. **Collection đã initialized không được lọc lại khi bật filter và không được mở rộng lại khi tắt filter.**
5. **Direct load-by-key, `getReference` và association to-one cần kiểm thử riêng**, vì không thể giả định semantics giống query list; một số Hibernate versions hỗ trợ cấu hình bổ sung nhưng không giải quyết L1.
6. **Filter state thuộc Session, không phải transaction toàn cục hay principal.** Đặt scope rõ trong service, bật trước load và cleanup đúng; tránh nested override.
7. **Một Session cũ không phù hợp để đổi hoàn toàn quyền visibility giữa user/admin/tenant**. Dùng persistence context mới và DTO boundary khi cần.
8. **Dynamic filter khác static soft-delete restriction**: `@SQLRestriction` và `@SoftDelete` không đơn thuần có thể disable như `@Filter`.
9. **Native SQL, bulk DML, caches và external writers không tự tuân theo mọi filter.** Điều kiện bảo mật quan trọng phải được thực thi ở các đường truy cập tương ứng.
10. **Không sử dụng Hibernate Filter làm lớp phân quyền tenant duy nhất.** Kết hợp authorization ở service, query predicates, tenant isolation hoặc DB RLS khi cần.
11. **Kiểm thử phải bao phủ cả filter state lẫn persistence context state**: context mới, managed object cũ, collection initialized, lazy loads, key loads và cache.

Kết luận cốt lõi: **bật hoặc tắt filter làm thay đổi điều kiện cho những lần tải dữ liệu thích hợp trong tương lai; nó không xóa, chỉnh sửa hoặc tải lại những thực thể mà Hibernate đã quản lý từ trước**. Khi nhận ra giới hạn này và thiết kế ranh giới Session/transaction/authorization rõ ràng, bạn có thể dùng Hibernate Filter cho xóa mềm và truy vấn có điều kiện mà không đánh đồng nó với cơ chế bảo mật hoặc trạng thái dữ liệu nhất quán tuyệt đối.
