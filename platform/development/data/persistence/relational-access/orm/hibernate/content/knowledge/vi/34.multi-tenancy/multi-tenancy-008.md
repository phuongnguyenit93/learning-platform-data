# Truy vấn HQL, native SQL và thao tác ngoài Hibernate cần kiểm soát phạm vi

Trong hệ thống **nhiều tổ chức (multi-tenancy)**, một ứng dụng có thể phục vụ nhiều khách hàng hoặc tổ chức độc lập, mỗi tổ chức gọi là một **tenant**. Điều quan trọng không chỉ là đăng nhập thành công mà là **mọi đường đọc, ghi, truy vấn tổng hợp, xuất dữ liệu và xử lý nền phải bị giới hạn trong phạm vi tenant được phép**.

Một lỗi điển hình: ứng dụng dùng Hibernate để đọc entity nên các truy vấn HQL có tenant isolation, nhưng một báo cáo mới dùng native SQL hoặc một phương thức Spring Data `@Modifying` được thêm vào mà quên điều kiện tenant. SQL có thể đọc hoặc thay đổi nhiều tổ chức cùng lúc. Đôi khi không trả về từng dòng nhạy cảm, nhưng một truy vấn `COUNT(*)` hoặc `SUM(total_amount)` chưa lọc cũng làm lộ thông tin kinh doanh của tenant khác.

Ví dụ một bảng dùng chung:

~~~text
orders
+----+-----------+------------+---------+
| id | tenant_id | order_code | status  |
+----+-----------+------------+---------+
| 10 | alpha     | A-001      | NEW     |
| 20 | beta      | B-001      | NEW     |
| 30 | alpha     | A-002      | PAID    |
+----+-----------+------------+---------+
~~~

Tenant `alpha` chỉ được nhìn các rows 10 và 30. Với shared-table strategy, điều kiện:

~~~sql
select id, tenant_id, order_code
from orders
where tenant_id = :authorizedTenantId;
~~~

là một phần của **ranh giới bảo mật**, không chỉ là một filter tiện dụng.

Bài học thuộc chương **Nhiều tổ chức**, module *Data Persistence Relational Access ORM Hibernate*. Chúng ta sẽ phân biệt database-per-tenant, schema-per-tenant và shared-table tenancy; HQL/JPQL/Criteria được Hibernate quản lý; native SQL, bulk DML, JDBC và các hệ thống ngoài Hibernate; cùng những lớp bảo vệ bổ sung như Row-Level Security (RLS), tenant-aware foreign keys, cache keys, transaction context và integration tests. Các ví dụ hướng tới Hibernate ORM 6.x, Jakarta Persistence và Spring Boot; phần RLS dùng PostgreSQL và không phải SQL portable.

## 1. Tenant scope là gì?

**Tenant scope** là tập dữ liệu mà một request, transaction, Session hoặc background job được phép xem hay sửa. Dữ liệu có thể là:

- **Tenant-scoped:** đơn hàng, khách hàng, hợp đồng, hóa đơn, tồn kho, thành viên tổ chức.
- **Global/shared:** quốc gia, tiền tệ hoặc các mã tham chiếu toàn hệ thống.
- **Cross-tenant administrative:** dữ liệu chỉ một vai trò quản trị đã được cấp quyền riêng được phép xem.
- **Shared-by-policy:** tài nguyên có ownership rõ và danh sách tenants được phép cộng tác.

Không phải mọi bảng đều cần cột `tenant_id`, nhưng mọi truy vấn phải biết các bảng nào là tenant-scoped và giới hạn phạm vi tương ứng.

### 1.1. Tenant ID khác user ID

Một tenant có nhiều users; một user có thể là thành viên nhiều tenants. Tenant hiện hành phải được lựa chọn **sau khi xác thực principal và kiểm tra quyền thành viên**, không chỉ lấy từ header/request body.

~~~mermaid
flowchart TD
    A["HTTP request / background job"] --> B["Xác thực principal / service"]
    B --> C["Xác thực quyền chọn tenant"]
    C --> D["Trusted tenant scope"]
    D --> E["Hibernate Session / EntityManager"]
    D --> F["JDBC / SQL / external services"]
    E --> DB[("Database")]
    F --> DB
~~~

Ví dụ header `X-Tenant-Id: beta` chỉ thể hiện tenant muốn chọn, không chứng minh user được phép truy cập beta.

### 1.2. Tenant isolation và authorization là hai lớp

Một user alpha có thể chỉ được xem đơn hàng của bộ phận mình. Điều kiện `tenant_id = 'alpha'` chỉ chặn dữ liệu ngoài alpha; nó không tự kiểm tra vai trò hoặc quyền với từng resource.

Một authorization decision đầy đủ thường là:

~~~text
Principal có quyền với tenant này?
    AND
Principal có quyền làm action X trên resource Y trong tenant ấy?
~~~

Không nên đọc row ngoài tenant rồi mới vô tình trả tên/status của nó trong thông báo lỗi.

## 2. Ba chiến lược lưu trữ dữ liệu nhiều tenant

### 2.1. Database-per-tenant

Mỗi tenant có database riêng:

~~~text
alpha -> alpha_db -> orders, customers
beta  -> beta_db  -> orders, customers
~~~

Tenant isolation phụ thuộc **chọn đúng connection tới đúng database**. Nếu database được phân tách thực sự và role không có quyền đọc database khác, SQL không cần cột `tenant_id` để phân biệt rows.

Rủi ro chính: connection routing sai, datasource fallback, batch job chạy nhầm database, migrations/backup sai target, connection provider giữ sai tenant mapping.

### 2.2. Schema-per-tenant

Các tenants dùng một database nhưng có schemas riêng:

~~~text
Database
  alpha.orders
  alpha.customers
  beta.orders
  beta.customers
  shared.countries
~~~

Các SQL tên bảng không fully-qualified thường dùng current schema/search path. Phạm vi đúng phụ thuộc Hibernate connection provider, schema selection và DB grants.

Rủi ro chính: connection đã dùng schema alpha được trả pool nhưng không reset, request beta tái sử dụng; câu native SQL trỏ trực tiếp `beta.orders` bất chấp current schema; database role có quyền cross-schema quá rộng.

### 2.3. Shared-table/discriminator

Các tenants dùng chung bảng, mỗi row mang khóa tenant:

~~~text
orders
  id | tenant_id | order_code | status | customer_id
~~~

Tenant isolation có thể được Hibernate thực hiện qua `@TenantId`, qua một filter được áp nhất quán, hoặc trực tiếp tại database bằng RLS. Nếu ứng dụng chỉ thêm field `tenantId` thường mà không có cơ chế scope, HQL không tự an toàn.

### 2.4. Bảng trách nhiệm

| Mô hình | Boundary chính | HQL/ORM | Native SQL/JDBC |
| --- | --- | --- | --- |
| Database-per-tenant | Database connection | Session được route đúng database | Phải chọn đúng datasource/connection |
| Schema-per-tenant | Current schema và grants | Session được route đúng schema | Cần đúng schema; tránh qualified SQL sai |
| Shared table + `@TenantId` | ORM tenant discriminator | ORM paths được hỗ trợ có tenant scope | SQL phải tự giới hạn hoặc có RLS |
| Shared table chỉ có `tenant_id` | Predicate/authorization tự viết | Không có auto-scope mặc định | Mỗi statement phải kiểm tenant |

Không thể đánh giá query an toàn bằng cách chỉ nhìn nó có chữ `WHERE tenant_id` hay không: phải biết strategy, route, mapping và quyền DB. Ngược lại, cũng không thể kết luận câu HQL nào cũng an toàn chỉ vì ứng dụng dùng Hibernate.

## 3. Xác định tenant bằng trusted context

Giả sử request:

~~~http
GET /api/orders
Authorization: Bearer ...
X-Tenant-Id: alpha
~~~

Service nên:

1. Xác thực principal/service identity.
2. Lấy memberships và grants từ nguồn đáng tin.
3. Kiểm tra tenant được yêu cầu nằm trong tập được phép.
4. Gắn immutable tenant scope cho request/use case.
5. Mở Session/DB connection với scope đó.
6. Lưu audit actor và operation ID.
7. Dọn context khi kết thúc.

Một abstraction:

~~~java
public interface TrustedTenantContext {
    String requireAuthorizedTenantId();
}
~~~

Đây là interface minh họa do ứng dụng thiết kế, không phải Hibernate API. Method phải **fail closed** khi thiếu tenant, thay vì rơi về một tenant mặc định có dữ liệu.

### 3.1. Không lấy ownership từ request body

Sai:

~~~java
public record CreateOrderRequest(
        String tenantId,
        String orderCode
) {}
~~~

nếu service copy trực tiếp `request.tenantId()` vào entity. Caller có thể khai báo tenant bất kỳ.

Nên lấy ownership từ server:

~~~java
@Transactional
public Long createOrder(CreateOrderRequest request) {
    String tenantId =
            tenantContext.requireAuthorizedTenantId();

    // tenantId từ trusted context/authorized principal.
    // Dùng Hibernate tenant Session hoặc mapping đúng.
    return saveForCurrentTenant(tenantId, request);
}
~~~

`saveForCurrentTenant` là method minh họa. Nếu dùng `@TenantId`, Hibernate thường quản lý giá trị tenant của entity dựa trên Session; không tự gán bằng một setter từ client.

### 3.2. Entity ID không phải authorization token

ID tăng dần có thể đoán; UUID dù khó đoán vẫn có thể lộ qua logs, URLs hoặc email. Biết ID không đồng nghĩa có quyền truy cập resource của tenant khác.

## 4. Hibernate Session gắn với tenant identifier

Một cách mở Session với tenant ID trong Hibernate:

~~~java
try (Session session = sessionFactory
        .withOptions()
        .tenantIdentifier(authorizedTenantId)
        .openSession()) {

    // ORM operations trong scope tenant của Session.
}
~~~

Tenant identifier là một đặc tính Session, không nên được đổi tùy tiện trong vòng đời Session bằng cách thay một ThreadLocal.

### 4.1. Một Session không được sử dụng luân phiên tenants

Persistence Context giữ managed entities, snapshots, proxies và identity map. Nếu Session đã tải Product alpha, đổi ThreadLocal thành beta không có nghĩa các managed objects biến thành dữ liệu beta.

Quy tắc: **tạo Session/EntityManager riêng cho scope tenant thích hợp**, không chia sẻ giữa requests hoặc threads.

### 4.2. CurrentTenantIdentifierResolver

Ví dụ khái niệm:

~~~java
public final class AppTenantResolver
        implements CurrentTenantIdentifierResolver<String> {

    private final TrustedTenantContext context;

    public AppTenantResolver(TrustedTenantContext context) {
        this.context = context;
    }

    @Override
    public String resolveCurrentTenantIdentifier() {
        return context.requireAuthorizedTenantId();
    }

    @Override
    public boolean validateExistingCurrentSessions() {
        return true;
    }
}
~~~

Cần đăng ký resolver trong Hibernate/bootstrap configuration thật. `validateExistingCurrentSessions()` có thể kiểm tra mismatch khi lấy current Session theo cơ chế hỗ trợ, nhưng không tự quyết định quyền của principal.

Spring transaction có thể mở EntityManager trước khi một service method chạy. Do đó trusted tenant context phải được thiết lập **trước** khi Session được tạo; nếu set sau, tenant identifier có thể đã sai.

### 4.3. Transaction propagation

Một inner method `@Transactional(REQUIRED)` thường tham gia transaction của outer; không thể chọn lại tenant tùy ý. `REQUIRES_NEW` có transaction riêng nhưng vẫn phải được gắn tenant identity đã được xác thực. Không dùng propagation để giả vờ một Session có thể chuyển tenant.

## 5. Shared-table strategy với @TenantId

Hibernate ORM 6.x có `org.hibernate.annotations.TenantId` dành cho tenant discriminator:

~~~java
package com.example.sales;

import jakarta.persistence.*;
import org.hibernate.annotations.TenantId;

@Entity
@Table(name = "orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @TenantId
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "order_code", nullable = false)
    private String orderCode;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected PurchaseOrder() {}
}
~~~

Khi Hibernate đã được cấu hình đúng và Session gắn tenant identifier, ORM có thể áp discriminator cho các entity operations mà nó hỗ trợ. Điều này khác một field tên `tenantId` thông thường.

### 5.1. @Column không tương đương @TenantId

~~~java
@Column(name = "tenant_id")
private String tenantId;
~~~

một mình nó **không khiến Hibernate tự biết mọi query phải bị tenant-scoped**. Nếu không có filter, RLS, DB routing hoặc manual predicate, một HQL `from PurchaseOrder` có thể trả rows mọi tenants.

### 5.2. Không tự gán @TenantId từ user input

Trong mô hình discriminator, tenant value nên được gắn theo trusted Session tenant identifier. Không gọi:

~~~java
order.setTenantId(request.tenantId());
em.persist(order);
~~~

rồi coi đó là bảo mật. Nếu ứng dụng có manual tenant field, service phải dùng trusted server context và database constraints.

### 5.3. @TenantId có giới hạn

Annotation không tự sửa mọi native SQL string, JDBC statement, stored procedure hoặc external writer. HQL bulk mutations cũng có semantics khác managed updates; khi destructive, phải kiểm SQL sinh ra theo Hibernate version/mapping hoặc dùng explicit guards/RLS. Không khẳng định một bulk DELETE đã an toàn chỉ vì SELECT trên entity có `@TenantId`.

## 6. HQL/JPQL và Criteria

Ví dụ HQL:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        select o from PurchaseOrder o
        where o.status = :status
        order by o.id
        """,
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.NEW)
    .getResultList();
~~~

Câu query có thể an toàn nếu multi-tenancy strategy được áp đúng vào Session/mapping:

- Database-per-tenant: đã chọn đúng database.
- Schema-per-tenant: current schema đúng và permissions phù hợp.
- Shared-table `@TenantId`: Hibernate áp ORM tenant restriction theo cơ chế hỗ trợ.
- Shared-table manual field: **không an toàn nếu không có predicate/filter/RLS**.

### 6.1. Manual tenant predicate

~~~java
String tenantId =
        tenantContext.requireAuthorizedTenantId();

List<PurchaseOrder> orders = em.createQuery(
        """
        select o from PurchaseOrder o
        where o.tenantId = :tenantId
          and o.status = :status
        order by o.id
        """,
        PurchaseOrder.class
    )
    .setParameter("tenantId", tenantId)
    .setParameter("status", OrderStatus.NEW)
    .getResultList();
~~~

Predicate phải xuất hiện ở mọi query path có phạm vi liên quan. Không dùng tenant ID tùy ý từ request.

### 6.2. Criteria có kiểu nhưng không tự cấp quyền

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
        cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> o = cq.from(PurchaseOrder.class);

cq.select(o).where(
    cb.equal(o.get("status"), OrderStatus.NEW),
    cb.equal(
        o.get("tenantId"),
        tenantContext.requireAuthorizedTenantId()
    )
);

List<PurchaseOrder> rows =
        em.createQuery(cq).getResultList();
~~~

Trong shared-table manual strategy, mỗi Criteria tree phải có tenant predicate phù hợp. Với Hibernate `@TenantId`/DB routing, có thể dựa vào cơ chế đã cấu hình nhưng vẫn phải kiểm nghiệp vụ và query shape thực tế.

### 6.3. Spring Data derived queries

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Tên method `findByStatus` không tự mang authorization. Nếu ORM không tự scope:

~~~java
List<PurchaseOrder> findByTenantIdAndStatus(
        String tenantId,
        OrderStatus status
);
~~~

nhưng caller vẫn phải truyền tenant đã được xác minh. Cẩn trọng với generic repository methods `findAll`, `findById` và custom JPQL.

### 6.4. Specification có thể bị quên

~~~java
static Specification<PurchaseOrder> forTenant(
        String authorizedTenantId
) {
    return (root, query, cb) ->
        cb.equal(root.get("tenantId"), authorizedTenantId);
}
~~~

Nếu một method repository bỏ Specification này, restriction mất. Một quy ước “nhớ gắn filter” không mạnh bằng boundary mặc định fail-closed ở ORM/DB và integration tests.

## 7. JOIN và subquery cần cùng phạm vi

Giả sử customers của alpha và beta đều có local ID 10:

~~~text
customers
tenant_id | id | name
alpha     | 10 | Alice
beta      | 10 | Bob

orders
tenant_id | id | customer_id
alpha     | 50 | 10
~~~

Query sai:

~~~sql
select o.id, c.name
from orders o
join customers c
  on c.id = o.customer_id
where o.tenant_id = :tenantId;
~~~

Nó có thể ghép Alice và Bob. Query scoped:

~~~sql
select o.id, c.name
from orders o
join customers c
  on c.id = o.customer_id
 and c.tenant_id = o.tenant_id
where o.tenant_id = :tenantId;
~~~

### 7.1. LEFT JOIN và vị trí predicate

~~~sql
select o.id, c.name
from orders o
left join customers c
  on c.id = o.customer_id
where o.tenant_id = :tenantId
  and c.tenant_id = :tenantId;
~~~

Predicate của c ở WHERE có thể loại các orders thiếu customer (NULL), biến ý nghĩa của LEFT JOIN. Nếu association optional:

~~~sql
select o.id, c.name
from orders o
left join customers c
  on c.id = o.customer_id
 and c.tenant_id = o.tenant_id
where o.tenant_id = :tenantId;
~~~

Vừa bảo vệ tenant vừa giữ rows owner không có relation.

### 7.2. Subquery có thể lộ số liệu dù outer SELECT scoped

Sai:

~~~sql
select o.id,
       (select avg(total_amount) from orders) as average_amount
from orders o
where o.tenant_id = :tenantId;
~~~

Mỗi outer order thuộc tenant hiện hành, nhưng average tính trên **tất cả tenants**. Đúng:

~~~sql
select o.id,
       (
           select avg(i.total_amount)
           from orders i
           where i.tenant_id = o.tenant_id
       ) as tenant_average
from orders o
where o.tenant_id = :tenantId;
~~~

Các `EXISTS`, CTE, grouped queries và window functions cũng cần xem source relations của riêng chúng. Outer WHERE không tự scope một uncorrelated subquery.

## 8. Native SQL: ranh giới phải viết rõ

Native SQL được thực thi trực tiếp và **không mặc nhiên được Hibernate viết lại để thêm mọi tenant predicates**.

Không an toàn với shared table:

~~~java
List<?> rows = em.createNativeQuery(
        "select id, order_code from orders"
    )
    .getResultList();
~~~

### 8.1. Native SELECT tenant-scoped

~~~java
String tenantId =
        tenantContext.requireAuthorizedTenantId();

@SuppressWarnings("unchecked")
List<Object[]> rows = em.createNativeQuery(
        """
        select id, order_code, status
        from orders
        where tenant_id = :tenantId
        order by id
        """
    )
    .setParameter("tenantId", tenantId)
    .getResultList();
~~~

Bind parameter thay vì nối raw user input.

### 8.2. Mapping native results thành entity không tạo bộ lọc

~~~java
List<PurchaseOrder> orders = em.createNativeQuery(
        """
        select o.*
        from orders o
        where o.tenant_id = :tenantId
        """,
        PurchaseOrder.class
    )
    .setParameter("tenantId", tenantId)
    .getResultList();
~~~

`PurchaseOrder.class` chỉ mô tả result mapping; nó không chứng minh SQL `SELECT * FROM orders` thiếu WHERE sẽ tự được lọc. Không dùng khả năng Hibernate hydrate entity của tenant khác làm security guard; chặn từ SQL/DB layer.

### 8.3. Native UPDATE cần cả tenant và entity ID

Sai:

~~~sql
update orders
set status = 'CANCELLED'
where id = :id;
~~~

Nếu ID scoped theo tenant, lệnh có thể sửa nhiều rows; nếu ID globally unique, caller vẫn có thể sửa row tenant khác nếu biết ID.

Đúng:

~~~sql
update orders
set status = :nextStatus
where tenant_id = :tenantId
  and id = :id;
~~~

Service minh họa:

~~~java
@Transactional
public void cancelOrder(Long orderId) {
    String tenantId =
            tenantContext.requireAuthorizedTenantId();

    int affected = em.createNativeQuery(
            """
            update orders
            set status = :status
            where tenant_id = :tenantId
              and id = :id
            """
        )
        .setParameter("status", "CANCELLED")
        .setParameter("tenantId", tenantId)
        .setParameter("id", orderId)
        .executeUpdate();

    if (affected != 1) {
        throw new EntityNotFoundException(
                "Order unavailable in current tenant"
        );
    }
}
~~~

Với native bulk SQL, Hibernate L1 đang giữ Orders có thể stale. Thiết kế flush/clear/refresh có chủ đích, không tiếp tục dùng managed objects cũ rồi mặc định state đã cập nhật.

### 8.4. Native DELETE phải kiểm soát kỹ

~~~sql
delete from orders
where tenant_id = :tenantId
  and status = 'ARCHIVED';
~~~

Một câu DELETE thiếu tenant predicate có thể xóa dữ liệu mọi tổ chức. DB cascades có thể tiếp tục ảnh hưởng child rows; vì thế cần tenant-aware relationships và constraints.

## 9. Bulk HQL/JPQL và Spring Data @Modifying

Bulk UPDATE/DELETE không đồng nghĩa load managed entities rồi thay đổi từng object.

~~~java
int changed = em.createQuery(
        """
        update PurchaseOrder o
        set o.status = :next
        where o.status = :previous
        """
    )
    .setParameter("next", OrderStatus.ARCHIVED)
    .setParameter("previous", OrderStatus.CANCELLED)
    .executeUpdate();
~~~

Với manual tenant field, câu này có thể ảnh hưởng mọi tenants. Với `@TenantId`, cần kiểm behavior đối với mutation query theo Hibernate version/SQL sinh ra; destructive operations không nên được tin theo suy đoán.

Thêm guard:

~~~java
String tenantId =
        tenantContext.requireAuthorizedTenantId();

int changed = em.createQuery(
        """
        update PurchaseOrder o
        set o.status = :next
        where o.tenantId = :tenantId
          and o.status = :previous
        """
    )
    .setParameter("next", OrderStatus.ARCHIVED)
    .setParameter("previous", OrderStatus.CANCELLED)
    .setParameter("tenantId", tenantId)
    .executeUpdate();
~~~

### 9.1. @Modifying không tự scope

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update PurchaseOrder o
        set o.status = :status
        where o.tenantId = :tenantId
        """)
    int updateForTenant(
            @Param("tenantId") String tenantId,
            @Param("status") OrderStatus status
    );
}
~~~

- `flushAutomatically` giúp flush pending changes trước bulk.
- `clearAutomatically` giúp tránh managed state stale sau bulk.
- **Không thuộc tính nào tự kiểm quyền tenant**; caller phải truyền trusted tenant và query phải đúng predicate.

### 9.2. Ngoài tenant scope, bulk có những giới hạn riêng

Bulk DML thường không thực thi per-entity `@PreUpdate`/`@PreRemove`, Bean Validation, JPA cascades, Envers revisions hoặc optimistic locking như managed operations. Nó cũng có thể làm Persistence Context stale.

Một pattern khi cần bulk:

~~~java
em.flush(); // Pending managed changes trước bulk.

int affected = em.createQuery(
        """
        update PurchaseOrder o
        set o.status = :next
        where o.tenantId = :tenantId
        """
    )
    .setParameter("next", OrderStatus.ARCHIVED)
    .setParameter("tenantId", tenantId)
    .executeUpdate();

em.clear(); // Detach managed entities cũ.
~~~

Pattern này giải quyết một phần L1 synchronization, **không tạo tenant predicates cho những query khác** và không phục hồi per-entity events bị bulk DML bypass.

## 10. Ràng buộc database cần bảo vệ quan hệ cùng tenant

Một schema shared-table có thể dùng composite keys:

~~~sql
create table customers (
    tenant_id varchar(80) not null,
    id bigint not null,
    name varchar(150) not null,
    primary key (tenant_id, id)
);

create table orders (
    tenant_id varchar(80) not null,
    id bigint not null,
    customer_id bigint not null,
    order_code varchar(80) not null,
    primary key (tenant_id, id),
    constraint fk_orders_customer_tenant
        foreign key (tenant_id, customer_id)
        references customers (tenant_id, id),
    constraint uk_orders_tenant_code
        unique (tenant_id, order_code)
);
~~~

Composite FK chặn một Order alpha trỏ tới Customer chỉ tồn tại ở beta, kể cả khi row được ghi bằng SQL ngoài Hibernate. Composite UNIQUE cho phép cùng `order_code` tồn tại ở các tenants khác nhau nếu nghiệp vụ cho phép.

Với JPA, composite IDs cần mapping `@EmbeddedId`/`@IdClass` và `@JoinColumns` phù hợp. Một thiết kế khác dùng global UUID/sequence ID nhưng vẫn có tenant-aware FK/unique constraints. Global ID đơn giản hóa uniqueness, **không thay authorization**.

### 10.1. Không chỉ dựa vào kiểm tra ở service

Một service có thể check `customer.tenantId == order.tenantId` trước insert, nhưng một ETL script khác không đi qua service. Nếu invariant “order và customer phải cùng tenant” bắt buộc đúng cho mọi writer, DB composite FK là lớp bảo vệ mạnh hơn.

## 11. Count, pagination và aggregate cũng phải scoped

Sai:

~~~sql
select count(*), sum(total_amount)
from orders;
~~~

Đúng theo shared-table model:

~~~sql
select count(*), sum(total_amount)
from orders
where tenant_id = :tenantId;
~~~

Ngay cả khi một query không trả order details, tổng số và doanh thu vẫn là dữ liệu nhạy cảm.

### 11.1. Data query và count query cần cùng tenant boundary

~~~java
List<PurchaseOrder> page = em.createQuery(
        """
        select o from PurchaseOrder o
        where o.tenantId = :tenantId
          and o.status = :status
        order by o.id desc
        """,
        PurchaseOrder.class
    )
    .setParameter("tenantId", tenantId)
    .setParameter("status", OrderStatus.NEW)
    .setFirstResult(offset)
    .setMaxResults(size)
    .getResultList();

Long total = em.createQuery(
        """
        select count(o) from PurchaseOrder o
        where o.tenantId = :tenantId
          and o.status = :status
        """,
        Long.class
    )
    .setParameter("tenantId", tenantId)
    .setParameter("status", OrderStatus.NEW)
    .getSingleResult();
~~~

Nếu content chỉ chứa alpha nhưng total đếm toàn hệ thống, UI vẫn lộ số lượng orders của các tenants khác. Hai query có thể khác JOIN shape nhưng phải có cùng business filter và tenant scope.

### 11.2. Application cache phải tenant-aware

Nguy hiểm:

~~~java
@Cacheable("recentOrders")
public List<OrderDto> recentOrders() {
    return repository.findRecent();
}
~~~

Nếu key mặc định không phản ánh tenant context, beta có thể nhận cached result của alpha.

Ví dụ tốt hơn:

~~~java
@Cacheable(
    cacheNames = "recentOrders",
    key = "#tenantId"
)
public List<OrderDto> recentOrdersForTenant(
        String tenantId
) {
    // tenantId phải được ủy quyền ở service boundary.
}
~~~

Nếu kết quả còn phụ thuộc role/user permissions, key chỉ có tenant vẫn có thể không đủ. Hibernate multi-tenant caching và custom application caching là hai cơ chế khác nhau.

## 12. Hibernate @Filter: cần hiểu giới hạn

Một số ứng dụng dùng dynamic filter:

~~~java
@Entity
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId"
)
public class PurchaseOrder {
    // ...
}
~~~

Khi mở Session:

~~~java
Session session = em.unwrap(Session.class);

session.enableFilter("tenantFilter")
       .setParameter(
           "tenantId",
           tenantContext.requireAuthorizedTenantId()
       );
~~~

Filter có thể hữu ích, nhưng cần cân nhắc:

- Một Session quên bật filter có thể trả mọi tenant rows.
- Một entity/association không gắn filter có thể bypass ý định.
- Direct ID lookup, lazy association và bulk operations có behavior phụ thuộc mapping/version.
- Native SQL không tự được thêm điều kiện filter.
- Code có thể gọi `session.disableFilter("tenantFilter")` nếu được phép.
- Một filter bị disabled để phục vụ admin report không nên biến public request thành cross-tenant query.

Vì vậy **không dùng @Filter thủ công như một biên bảo mật duy nhất** nếu có thể sử dụng Hibernate multi-tenancy được tích hợp đúng và DB policy phù hợp.

## 13. PostgreSQL Row-Level Security (RLS)

Shared-table multi-tenancy có thể được tăng cường bằng RLS để database áp row policy cho SELECT, INSERT, UPDATE và DELETE của những roles chịu policy.

Ví dụ PostgreSQL:

~~~sql
create table orders (
    id bigint primary key,
    tenant_id text not null,
    order_code text not null,
    status text not null
);

alter table orders enable row level security;

create policy orders_tenant_isolation
on orders
for all
using (
    tenant_id = current_setting('app.tenant_id', true)
)
with check (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

`current_setting('app.tenant_id', true)` có thể trả NULL nếu setting chưa tồn tại, khi đó điều kiện `tenant_id = NULL` không thỏa, tạo khả năng fail-closed cho policy này.

### 13.1. USING và WITH CHECK khác nhau

- `USING` quyết định các existing rows có thể được nhìn/thao tác theo policy/operation.
- `WITH CHECK` kiểm tra giá trị row mới khi INSERT hoặc UPDATE.

Một policy chỉ bảo vệ việc đọc mà không kiểm ownership khi ghi vẫn có thể cho phép INSERT/UPDATE row sai tenant theo quyền DB.

### 13.2. Transaction-local tenant setting

Trên connection của chính transaction:

~~~sql
select set_config('app.tenant_id', :tenantId, true);
~~~

Tham số `true` đặt setting ở phạm vi transaction-local.

~~~text
BEGIN trên connection C
  -> set_config('app.tenant_id', authorizedTenant, true)
  -> SQL trên connection C
COMMIT / ROLLBACK
  -> transaction-local setting kết thúc
  -> connection có thể trở về pool
~~~

Nếu setting chạy trên một connection khác, SQL sau đó trên connection C sẽ không có tenant context mong muốn. Phải kiểm tra transaction manager, datasource và connection handling mode, nhất là với JDBC helper nằm ngoài JPA.

### 13.3. RLS có thể bị bypass bởi roles

Trong PostgreSQL, superusers và roles có `BYPASSRLS` có thể vượt policy. Table owners có hành vi đặc biệt; `FORCE ROW LEVEL SECURITY` có thể cần được cấu hình tùy threat model.

Nguyên tắc:

- Runtime application không dùng superuser.
- Không cấp BYPASSRLS cho app role.
- Kiểm grants và table ownership.
- Test bằng role tương đương production, không chỉ DBA account.
- Policy phải bao phủ tất cả tenant-scoped tables.
- Không cho client set arbitrary tenant context trái quyền đã xác thực.

RLS giúp giảm rủi ro native SQL quên WHERE, **nhưng không thay thế authorization theo role và không bảo vệ khi DB credentials bị lạm dụng để bypass policy**.

## 14. Schema-per-tenant và connection pool

Một tenant-aware connection provider có thể đặt schema khi mượn connection:

~~~java
Connection acquireFor(String tenantId)
        throws SQLException {

    String schema =
            trustedRegistry.requireAllowedSchema(tenantId);

    Connection connection = dataSource.getConnection();

    try {
        connection.setSchema(schema);
        return connection;
    } catch (SQLException | RuntimeException ex) {
        connection.close();
        throw ex;
    }
}

void release(Connection connection) throws SQLException {
    try {
        connection.setSchema(defaultSchema);
    } finally {
        connection.close(); // Trả connection về pool.
    }
}
~~~

Đây chỉ là **pseudo-skeleton**, không phải implementation đầy đủ của `MultiTenantConnectionProvider`. Provider thật còn phải tuân thủ các methods để lấy/release metadata connections, exception semantics và khả năng của JDBC driver.

### 14.1. Không lấy raw schema từ client

Sai:

~~~java
statement.execute("set search_path to " + requestTenant);
~~~

SQL identifier không được bind như ordinary value ở mọi DBMS, và phép nối chuỗi raw gây rủi ro injection/sai schema. Dùng tenant registry/whitelist map trusted tenant ID sang schema name hợp lệ, driver API phù hợp và DB grants giới hạn.

### 14.2. Pool reuse có thể rò schema

Nếu alpha connection được trả pool mà vẫn mang schema alpha, beta request dùng lại có thể thấy alpha. Vì vậy:

1. Luôn set schema trên mỗi lần acquire.
2. Reset schema/session state trong `finally` khi release.
3. Xử lý lỗi khi set/reset.
4. Hạn chế cross-schema permissions.
5. Test alpha → beta → alpha trên cùng pool.

### 14.3. Qualified SQL vượt current schema

~~~sql
select * from beta.orders;
~~~

vẫn có thể chạy khi current schema alpha nếu DB role được cấp quyền. Search path không phải security guard đầy đủ nếu credential có quyền đọc cross-schema.

## 15. Database-per-tenant và datasource routing

Một routing component có thể chọn datasource theo tenant đã được xác thực:

~~~java
DataSource forTenant(String tenantId) {
    DatabaseConfig cfg =
            trustedRegistry.requireTenantDatabase(tenantId);

    return dataSourceRegistry.get(cfg.databaseKey());
}
~~~

Đây là architecture pseudocode.

Phải bảo đảm:

- Không nhận JDBC URL từ client.
- Không có fallback vào shared database khi thiếu tenant.
- Connections không bị gán nhầm tenant.
- Migrations và backup chạy đúng database.
- Role của từng DB bị giới hạn phù hợp.
- Analytics toàn hệ thống được thực hiện qua privileged path riêng.
- Connection pool capacity và lifecycle được vận hành đúng khi số tenants tăng.

Một native SQL không có `tenant_id` có thể an toàn khi DB thực sự riêng, nhưng **routing sai biến sự an toàn ấy thành lỗi nghiêm trọng**.

## 16. Spring JDBC và những đường ghi ngoài Hibernate

Một service dùng Hibernate cho CRUD nhưng dùng `JdbcTemplate` để báo cáo:

~~~java
public long countOrders() {
    String tenantId =
            tenantContext.requireAuthorizedTenantId();

    return jdbcTemplate.queryForObject(
        """
        select count(*)
        from orders
        where tenant_id = ?
        """,
        Long.class,
        tenantId
    );
}
~~~

Với shared table, tenant predicate là bắt buộc nếu DB không có RLS. Với schema/database strategy, JdbcTemplate phải dùng **đúng tenant-aware datasource/connection**, không mặc nhiên inherit Session tenant chỉ vì cùng method có JPA.

### 16.1. @Transactional không làm mọi resource cùng tenant

Spring `@Transactional` do transaction manager điều phối. Nếu EntityManager dùng tenant-aware provider nhưng JDBC helper mở connection từ datasource khác, chúng có thể khác:

- Physical database.
- Selected schema.
- Transaction boundary.
- Connection-local RLS settings.
- Authentication/role.

Phải xác định chính xác resource ownership; không dùng việc cùng có annotation như bằng chứng mọi external connector đều cùng scope.

### 16.2. External writers

Các đường sau không tự áp Hibernate tenant isolation:

- SQL scripts của DBA.
- ETL/import jobs.
- Stored procedures.
- JDBC batch loaders.
- Flyway/Liquibase data migrations.
- Legacy applications.
- Các microservices cùng database.
- Scheduled jobs ngoài Spring/JPA.

Chúng cần tenant-aware DB permissions/RLS, predicates/connection selection, audit operation IDs và kiểm affected rows. Không cấp đặc quyền bypass để “script chạy cho dễ” rồi quên khôi phục.

## 17. Scheduled jobs và batch processing

Một scheduled task:

~~~java
@Scheduled(cron = "0 0 * * * *")
public void archiveOldOrders() {
    repository.archiveOldOrders();
}
~~~

không mặc nhiên có HTTP security context. Nếu không có trusted tenant, hãy **báo lỗi hoặc chạy một privileged workflow rõ ràng**, không chọn tenant mặc định.

### 17.1. Job cho một tenant

~~~java
public void archiveForTenant(String tenantId) {
    tenantJobRunner.runForAuthorizedTenant(
        tenantId,
        () -> archiveService.archiveOldOrders()
    );
}
~~~

`tenantJobRunner` là abstraction giả định: nó kiểm service identity, gắn context, mở transaction/Session riêng và cleanup.

### 17.2. Job quét tất cả tenants

~~~text
for each tenantId from trusted registry:
    1. Tạo tenant scope riêng.
    2. Mở transaction và Session tương ứng.
    3. Chạy job chỉ trong tenant đó.
    4. Commit hoặc rollback.
    5. Đóng Session và dọn tenant context.
    6. Tiếp tục tenant kế tiếp.
~~~

Không đổi ThreadLocal giữa các vòng mà vẫn giữ cùng một EntityManager. Nếu nhiều database tenants và yêu cầu all-or-nothing toàn hệ thống, một local JDBC transaction không đủ; cần thiết kế orchestration/compensation riêng.

### 17.3. Cross-tenant admin là capability đặc biệt

Một report hoặc migration toàn tenants phải có:

- Service principal/role đặc quyền riêng.
- Tenant registry và scope explicit.
- Quy trình review/audit.
- Resource/batch limits.
- DB permissions phù hợp.
- Tests ngăn user thường gọi privileged endpoint.

Đừng chỉ `disableFilter("tenantFilter")` rồi chạy public repository API như thể đó là authorization.

## 18. Async, thread pools và tenant context leakage

`@Async` hoặc Executor tasks không tự được bảo đảm kế thừa ThreadLocal/transaction context của request ban đầu.

~~~java
@Async
public void generateReport(Long reportId) {
    // Không được giả định tenant ThreadLocal có giá trị đúng.
}
~~~

Nguy cơ:

- Worker thiếu tenant ID.
- Thread pool tái sử dụng thread còn tenant của job trước.
- Tenant context đổi nhưng Hibernate Session đã mở với tenant cũ.
- Một EntityManager được truyền qua threads dù không thread-safe.

### 18.1. Dùng explicit context propagation

~~~java
public void generate(
        AuthorizedTenantScope scope,
        Long reportId
) {
    tenantRunner.run(scope, () -> {
        reportService.generate(reportId);
    });
}
~~~

`AuthorizedTenantScope` và `tenantRunner` là abstractions do ứng dụng xây dựng. Nếu dùng ThreadLocal, thiết lập và dọn trong `try/finally`. Truyền immutable IDs/DTOs, không truyền Session hoặc managed entity graph giữa threads.

Reactive context có cơ chế propagation khác ThreadLocal imperative; không tự áp các giả định của blocking Hibernate/JPA vào một reactive pipeline.

## 19. Search, storage, cache và message brokers

Hibernate không điều khiển toàn bộ data plane của ứng dụng.

### 19.1. Search index

Document:

~~~json
{
  "tenantId": "alpha",
  "orderId": 120,
  "text": "customer note"
}
~~~

phải được search theo tenant filter hoặc index/role isolation tương đương. Elasticsearch/OpenSearch không tự nhận `@TenantId` annotation của Hibernate.

### 19.2. Object storage

Keys có thể dùng namespace:

~~~text
tenants/alpha/orders/120/invoice.pdf
tenants/beta/orders/120/invoice.pdf
~~~

Nhưng prefix không thay authorization. API phát presigned URL/tải file phải kiểm principal và ownership, không nhận arbitrary object key rồi trả blob.

### 19.3. Message payload và idempotency

~~~json
{
  "tenantId": "alpha",
  "orderId": 120,
  "eventType": "ORDER_CONFIRMED"
}
~~~

Consumer phải xác nhận nguồn message, quyền/ownership và dedupe key có tenant nếu IDs scoped. Client hoặc producer không tin cậy có thể giả tenantId.

### 19.4. CSV/PDF exports

Export jobs đôi khi dùng JDBC/native SQL hoặc analytics connector. Tenant scope cần nằm ở query, report renderer và file download authorization. File đã được gửi nhầm tenant không thể rollback như một DB transaction.

## 20. Bảo vệ nhiều lớp (defense in depth)

~~~mermaid
flowchart TD
    A["Authenticated request / approved job"] --> B["Authorize tenant membership"]
    B --> C["Trusted TenantContext"]
    C --> D["Hibernate ORM-scoped queries"]
    C --> E["Native/JDBC tenant predicates"]
    C --> F["DB transaction-local tenant setting"]
    D --> G["DB roles / RLS / tenant-aware constraints"]
    E --> G
    F --> G
    G --> H[("Tenant-scoped data")]
~~~

| Lớp | Vai trò |
| --- | --- |
| Authentication | Xác định principal/service |
| Membership/role checks | Tenant được phép chọn và hành động được phép |
| Trusted tenant context | Truyền identity đã xác minh |
| Hibernate `@TenantId`/routing | Scope những ORM operations được hỗ trợ |
| Scoped native/bulk SQL | Chặn query paths ngoài entity lifecycle |
| RLS và DB grants | Chặn truy cập row sai ngay tại database |
| Tenant-aware PK/FK/UNIQUE | Ngăn quan hệ chéo tenant |
| Cache/search/storage scoping | Ngăn rò dữ liệu ngoài ORM |
| Audit/monitoring | Truy dấu admin/cross-tenant access |
| Integration tests | Chứng minh không đọc/ghi chéo tenant |

Không lớp nào miễn cho lớp khác trách nhiệm của nó. Ví dụ RLS không có tác dụng như mong đợi khi app dùng superuser, và `@TenantId` không tự bảo vệ một CSV export dùng JDBC không scoped.

## 21. Kiểm thử với ít nhất hai tenants

Test một tenant không chứng minh isolation. Tạo fixtures:

~~~text
Tenant alpha:
  customer externalCode C-001
  order id=100, code=SHARED-001, amount=100

Tenant beta:
  customer externalCode C-001
  order id=200, code=SHARED-001, amount=900
~~~

Nếu composite-key/schema model cho phép, dùng cùng local IDs để kiểm JOIN. Nếu global IDs, cố truy cập beta ID từ alpha context.

### 21.1. Test đọc entity ngoài tenant

~~~java
@Test
void alphaCannotReadBetaOrder() {
    tenantTestScope.runAs("alpha", () -> {
        Optional<OrderDto> result =
                orderService.findById(betaOrderId);

        assertTrue(result.isEmpty());
    });
}
~~~

`tenantTestScope` là fixture giả định mở đúng Session/transaction. Dùng ORM/database thật thay vì chỉ mock repository.

### 21.2. Test ghi ngoài tenant

- Gọi native/JPQL UPDATE/DELETE với betaOrderId trong alpha context.
- Mong đợi không có beta row bị thay đổi.
- Đọc beta row từ một tenant beta Session/connection **mới**.
- Kiểm affected row count và error semantics.
- Không xác nhận bằng cùng L1 entity stale.

### 21.3. Test aggregates

Alpha total=100, beta total=900. Alpha `SUM` phải trả 100, không phải 1000. Test `COUNT`, `AVG`, joins, CTEs và subqueries.

### 21.4. Test thiếu tenant context

Gọi tenant-scoped API mà không có context. Phải fail closed: exception hoặc DB policy không cho thấy/ghi rows, không fallback tenant thực.

### 21.5. Test connection/thread reuse

Chạy alpha → beta → alpha trong cùng pool. Kiểm schema reset, transaction-local RLS setting và ThreadLocal cleanup. Với database-per-tenant, kiểm datasource routing không nhầm target.

### 21.6. Test RLS bằng app role

Superuser hoặc table owner có thể bypass policy. Kiểm bằng role tương đương production, không phải account quản trị DB.

### 21.7. Test những đường ngoài Hibernate

Ngoài `findById`/HQL, cần test JdbcTemplate, native SQL, Spring Data `@Modifying`, scheduled jobs, report exports, search, storage, caches và queue consumers nếu chúng chạm tenant data.

## 22. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| HQL đúng nhưng native SQL rò rows | Native statement thiếu tenant WHERE | Bind trusted tenant hoặc DB RLS |
| `findById` thấy beta dưới alpha | Không có ORM/DB isolation | Kiểm mapping, Session tenant, filter, RLS |
| Một job sửa mọi tenants | Không có trusted tenant context | Explicit per-tenant job scope |
| `@Modifying` ảnh hưởng quá nhiều rows | Bulk UPDATE thiếu tenant predicate | Scope DML, kiểm row count, test |
| COUNT lộ số lượng toàn hệ thống | Count query quên tenant | Giữ same tenant/business scope |
| JOIN trả customer beta | Join thiếu tenant key | Tenant-aware JOIN và composite FK |
| Schema alpha rò sang beta | Pool không reset schema | Set/reset connection state |
| RLS không chặn | App role có bypass hoặc policy sai | Giới hạn grants, FORCE RLS khi phù hợp |
| @Async thấy tenant cũ | ThreadLocal leak | Explicit propagation + cleanup |
| Cache beta nhận alpha content | Cache key thiếu tenant | Key gồm tenant/security context |
| Native INSERT tạo row tenant khác | Lấy ownership từ client | Trusted server context + WITH CHECK |
| @Filter bị quên bật | Convention yếu | Session boundary mạnh + DB guard |
| Migration sửa dữ liệu nhiều tenants | Script chạy ngoài ORM không scope | Review SQL, audit, test DB |
| Export file lộ dữ liệu | Query/storage permission ngoài ORM | Scope toàn bộ export pipeline |

## 23. Checklist review mỗi truy vấn mới

1. Các bảng tham gia là global hay tenant-scoped?
2. Tenant identity đến từ trusted principal/service hay raw request?
3. Strategy là database, schema, @TenantId, @Filter hay RLS?
4. HQL/Criteria query shape này có thực sự bị scope không?
5. Native SQL/JDBC có tenant predicate/DB guard không?
6. JOIN có giữ cùng tenant ownership không?
7. Subqueries/CTEs/aggregates có filter tenant không?
8. Data query và count query có cùng tenant scope không?
9. UPDATE/DELETE có hạn chế affected rows đúng tenant không?
10. Có kiểm affected count và xử lý “không tìm thấy” không?
11. INSERT có thể bị client gán tenant_id sai không?
12. DB PK/FK/UNIQUE có ngăn cross-tenant references không?
13. Bulk DML có bypass callbacks/versioning/audit không?
14. Cache keys có chứa tenant và permission dimensions không?
15. Session/EntityManager có bị tái sử dụng giữa tenants không?
16. Connection pool có reset schema/tenant session state không?
17. Async/scheduled paths có context explicit không?
18. External search/storage/queue/report exports có scoped không?
19. Admin cross-tenant có privileged boundary và audit không?
20. Tests có ít nhất hai tenants với negative read/write cases không?

## 24. Bài tập thực hành

### Bài 1 — HQL

Entity có `tenantId` field nhưng không dùng `@TenantId`, @Filter hay RLS:

~~~java
em.createQuery(
    "from PurchaseOrder o where o.status = :status",
    PurchaseOrder.class
);
~~~

Query có an toàn không? Viết lại với trusted tenant predicate.

### Bài 2 — Native result mapping

~~~java
em.createNativeQuery(
    "select * from orders",
    PurchaseOrder.class
);
~~~

Vì sao truyền entity class không tự áp tenant WHERE?

### Bài 3 — Bulk DELETE

~~~sql
delete from orders where status='CANCELLED';
~~~

Nếu bảng chung nhiều tenants, chuyện gì xảy ra? Viết lại scoped DELETE và đề xuất integration test kiểm beta không thay đổi.

### Bài 4 — Aggregate leak

Một outer SELECT lọc alpha nhưng subquery tính AVG trên toàn bộ orders. Nó có làm lộ dữ liệu beta không? Sửa subquery.

### Bài 5 — JOIN

Customers alpha và beta có local ID 10, Order alpha tham chiếu customer_id 10. JOIN chỉ theo ID có thể trả gì? Hãy thêm tenant predicate và composite FK.

### Bài 6 — Schema và pool

Connection còn current schema alpha được beta request mượn. Nêu rủi ro và cách set/reset an toàn.

### Bài 7 — PostgreSQL RLS

Viết RLS policy dùng `current_setting('app.tenant_id', true)`; phân biệt `USING` và `WITH CHECK`; giải thích vì sao test bằng superuser không đáng tin.

### Bài 8 — Spring Data @Modifying

`clearAutomatically=true` có bảo đảm chỉ cập nhật tenant hiện hành không? Vì sao?

### Bài 9 — Cache

Một `@Cacheable` trả recent orders nhưng cache key thiếu tenant. Alpha gọi trước, beta gọi sau. Điều gì có thể xảy ra?

### Bài 10 — Async

Vì sao `@Async` có thể mất tenant context? Thiết kế cách truyền scope đã được xác minh và cleanup ThreadLocal.

### Bài 11 — Admin cross-tenant

Vì sao không nên disable tenant filter trong public service? Đề xuất privileged reporting path có audit riêng.

### Bài 12 — Database-per-tenant

Nếu schema không có cột tenant_id, native SQL an toàn phụ thuộc yếu tố nào? Nêu ba lỗi connection routing đáng test.

### Bài 13 — Client giả tenant

Principal thuộc alpha nhưng HTTP body có `tenantId=beta`. Service nên xử lý thế nào? DB RLS `WITH CHECK` hỗ trợ điều gì?

### Bài 14 — Backfill nhiều tenants

Một job chạy trên 100 tenants. Hãy mô tả loop với mỗi tenant một Session/transaction riêng, tenant registry và affected row logging.

### Bài 15 — Negative tests

Hãy thiết kế integration tests chứng minh alpha không thể đọc, sửa hoặc xóa betaOrderId. Vì sao chỉ test SELECT không đủ?

**Gợi ý:** (1) không nếu thiếu scope; (2) result mapping không sửa SQL; (3) phải thêm tenant WHERE; (4) có, cần correlated aggregate; (5) composite tenant/id; (6) schema state leak; (7) dùng restricted app role; (8) chỉ clear L1; (9) cache key tenant-aware; (10) explicit worker scope; (11) privileged boundary; (12) datasource routing; (13) không tin input; (14) độc lập từng tenant; (15) test cả reads và writes.

## 25. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): multi-tenancy, `@TenantId`, Hibernate filters, Session và query handling.
- [Hibernate ORM 6.6 HQL Reference](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/Hibernate_Query_Language.html): JOIN, subqueries, aggregates và bulk DML.
- [Hibernate ORM 6.6 Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/): `CurrentTenantIdentifierResolver`, `MultiTenantConnectionProvider` và Session builder APIs.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): JPQL/Criteria, bulk queries và persistence context.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): repository queries, native SQL và `@Modifying`.
- [Spring Framework Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries và resource coordination.
- [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS `USING`/`WITH CHECK` và quyền bypass.
- [PostgreSQL Configuration Functions](https://www.postgresql.org/docs/current/functions-admin.html): `current_setting` và `set_config`.
- [OWASP API Security](https://owasp.org/API-Security/): broken object-level authorization.

**Kết luận:** tenant isolation không thể chỉ dựa vào lời nhắc “nhớ thêm WHERE”. HQL/JPQL/Criteria có thể được scoped đúng khi Hibernate multi-tenancy được cấu hình phù hợp, nhưng **native SQL, bulk DML, JDBC, background jobs và external services không tự kế thừa mọi entity restriction**. Với shared tables, hãy dùng trusted tenant context, scoped predicates/joins/subqueries, tenant-aware database constraints và cân nhắc RLS. Với schema/database-per-tenant, bảo vệ connection routing, permissions và pool cleanup. Quan trọng nhất, kiểm thử ít nhất hai tenants trên mọi đường đọc, ghi, aggregate và export; truy cập thiếu tenant context phải **thất bại an toàn** thay vì vô tình mở toàn bộ dữ liệu.
