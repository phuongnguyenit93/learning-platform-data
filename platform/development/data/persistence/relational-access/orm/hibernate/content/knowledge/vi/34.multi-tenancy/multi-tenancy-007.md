# Phân tách Session, giao dịch và bộ nhớ đệm

## 1. Bối cảnh: nhiều tổ chức cùng sử dụng một ứng dụng

Trong hệ thống *multi-tenancy*, một ứng dụng phục vụ nhiều tổ chức (*tenant*), chẳng hạn các công ty, trường học hoặc cửa hàng. Mỗi tổ chức sở hữu tập dữ liệu riêng. Người dùng thuộc tổ chức A không được vô tình thấy đơn hàng, hóa đơn hay thông tin nhân sự của tổ chức B.

Ví dụ:

```text
Một ứng dụng quản lý đơn hàng
  Tenant A: Công ty Alpha
    Order #17 -> khách hàng Alpha
    Order #18 -> khách hàng Alpha

  Tenant B: Công ty Beta
    Order #17 -> khách hàng Beta
    Order #21 -> khách hàng Beta
```

Hai tổ chức thậm chí có thể sử dụng **cùng một giá trị ID số 17** nếu thiết kế khóa chính cho phép. Vì vậy, một thao tác “đọc Order #17” chưa xác định đầy đủ thực thể cần đọc nếu thiếu bối cảnh tổ chức.

Hibernate có nhiều cơ chế giúp triển khai multi-tenancy. Nhưng bảo vệ dữ liệu không chỉ là thêm cột `tenant_id`. Cần xác định và kiểm thử rõ ba ranh giới:

1. **Session/persistence context:** Một Hibernate Session thuộc tenant nào, quản lý những entity instances nào, và tenant context có được cố định trong suốt unit of work không?
2. **Transaction:** Những thay đổi thuộc tenant nào được commit/rollback cùng nhau? Một transaction có vô tình chạy SQL ở nhiều nguồn dữ liệu hoặc tenant khác nhau không?
3. **Cache:** Một cache entry của tenant A có thể bị lấy nhầm cho tenant B khi hai tenant dùng cùng entity ID hoặc query parameters không?

**Mục tiêu:** mỗi đường đọc và ghi phải có tenant identity đáng tin cậy, được giữ nhất quán từ request đến Session, transaction, JDBC connection, cache key và database.

## 2. Tenant là gì, và ranh giới dữ liệu nào đang cần bảo vệ?

Trong tài liệu này, `tenantId` là mã định danh tổ chức có quyền sở hữu dữ liệu nghiệp vụ. Ví dụ `alpha` và `beta`.

Phân biệt:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| User identity | Ai đang thực hiện request? | User 812 |
| Tenant identity | Dữ liệu của tổ chức nào? | alpha |
| Authorization | User có quyền trên tenant và tài nguyên này không? | User 812 thuộc alpha |
| Persistence unit | Bộ entity mappings nào đang được quản lý? | Orders EMF |
| JDBC resource | Kết nối đến database/schema nào? | orders_db / schema alpha |
| Transaction scope | Những thao tác nào cùng commit? | Tạo Order + Outbox row cho alpha |

Tenant ID là **đầu vào bảo mật**. Chỉ vì client gửi header `X-Tenant-Id: alpha` không có nghĩa người dùng được phép xem dữ liệu Alpha. Phía server phải xác thực session/token và kiểm tra user có quyền chọn tenant đó.

Một user có thể là thành viên của nhiều tổ chức, nhưng **mỗi unit of work** vẫn nên có tenant context rõ ràng. Chuyển tenant trong UI thường là một request hoặc một unit of work mới, không phải đổi một biến toàn cục giữa lúc transaction đang chạy.

## 3. Ba mô hình phân vùng dữ liệu phổ biến

Trong ứng dụng Hibernate, ba mô hình vật lý thường được xem xét:

| Mô hình | Dữ liệu được chia thế nào? | Lợi ích | Rủi ro chính |
|---|---|---|---|
| **Shared schema / discriminator** | Các tenant cùng bảng, mỗi row có `tenant_id` | Dễ vận hành schema, dùng chung pool | Rủi ro thiếu predicate tenant, uniqueness/FK |
| **Schema-per-tenant** | Mỗi tenant có schema/tables riêng trong một DBMS | Phân tách namespace, migration theo schema | Schema switching, migrations, pool/reset |
| **Database-per-tenant** | Mỗi tenant có database hoặc cluster riêng | Cô lập vận hành/backup/quyền tốt hơn | Số pools/connections, chi phí, provisioning |

Ví dụ:

```text
SHARED SCHEMA
  one database
    orders(tenant_id, id, ...)
    customers(tenant_id, id, ...)

SCHEMA PER TENANT
  one database
    alpha.orders / alpha.customers
    beta.orders  / beta.customers

DATABASE PER TENANT
  Alpha DB -> orders, customers
  Beta  DB -> orders, customers
```

Các mô hình này không tự quyết định service nào có quyền xem tenant nào, và không tự tạo một transaction xuyên nhiều databases. Tầng authentication/authorization và Hibernate tenant context vẫn phải được thiết kế.

## 4. Tại sao phải tách Session theo tenant?

Hibernate `Session` (hoặc JPA `EntityManager` do Hibernate triển khai) là một **unit of work** có persistence context. Persistence context là identity map và nơi theo dõi entity state để dirty checking.

Khi xử lý tenant A:

```text
Request A (authorized tenant = alpha)
                |
                v
          Session for alpha
                |
                +-- Order(alpha, 17)
                +-- Customer(alpha, 8)
                |
                v
          Transaction A
```

Xử lý tenant B:

```text
Request B (authorized tenant = beta)
                |
                v
           Session for beta
                |
                +-- Order(beta, 17)
                +-- Customer(beta, 9)
                |
                v
           Transaction B
```

Không được dùng cùng một Session rồi đổi biến `currentTenant` từ alpha sang beta và kỳ vọng Hibernate sẽ tự xóa toàn bộ managed state, thay JDBC resource và tái định nghĩa mọi entity key.

**Một Session được mở cho tenant nào thì tenant identity của Session đó phải được coi là cố định suốt vòng đời.**

## 5. Session identity và entity identity không chỉ có ID số

Trong một persistence context thông thường, một entity được xác định bằng mapping type và identifier; khi multi-tenancy được cấu hình đúng, Hibernate còn phải bảo đảm tenant context là một phần của cơ chế định danh/đọc dữ liệu thích hợp.

Ví dụ:

```text
Tenant alpha: Customer(id=5, name="An")
Tenant beta:  Customer(id=5, name="Binh")
```

Nếu ứng dụng lưu một `Map<Long, Customer>` dùng chung toàn ứng dụng:

```java
Map<Long, Customer> customerCache = new ConcurrentHashMap<>();
customerCache.put(5L, alphaCustomer);
```

rồi dùng `customerCache.get(5L)` khi xử lý Beta thì đã có nguy cơ lộ dữ liệu, dù Hibernate multi-tenancy có thể đang được cấu hình đúng.

Một key cấp ứng dụng phải chứa tenant scope:

```java
public record TenantEntityKey(String tenantId, Long entityId) {}

Map<TenantEntityKey, CustomerView> cache =
    new ConcurrentHashMap<>();

cache.put(
    new TenantEntityKey("alpha", 5L),
    alphaView);
```

Hibernate L2 cache có cơ chế tenant-aware key riêng khi multi-tenancy được thiết lập, nhưng mọi cache do ứng dụng tự viết hoặc Spring Cache đều cần tự kiểm soát tenant key.

## 6. Không truyền Session qua các requests hoặc threads

Hibernate Session concrete không phải một đối tượng chia sẻ tự do giữa nhiều threads.

Anti-pattern:

```java
public final class UnsafeSessionHolder {
    static Session sharedSession; // Không làm vậy.
}
```

Nguy cơ:

- Hai requests thay đổi cùng persistence context.
- Tenant context bị lẫn.
- Entity instances từ request trước được giữ lại.
- Dirty checking/flush ghi thay đổi không mong đợi.
- JDBC connection và transaction lifecycle khó kiểm soát.

Trong Spring, `@PersistenceContext` thường inject một **shared EntityManager proxy**. Proxy có thể là dependency của singleton service, nhưng nó định tuyến lời gọi đến EntityManager gắn với transaction hiện tại; không có nghĩa concrete EntityManager được dùng chung xuyên requests.

Nguyên tắc an toàn:

```text
Mỗi request/command
      -> xác định tenant đáng tin
      -> mở/nhận EntityManager đúng tenant
      -> thực thi transaction
      -> commit/rollback
      -> đóng/giải phóng tài nguyên
```

## 7. Xác định tenant trước khi mở Session

Điểm quan trọng về thời điểm:

```text
1. Authenticate user
2. Authorize user for requested tenant
3. Establish tenant context
4. Start transaction / open Hibernate Session
5. Execute repository operations
6. Commit or rollback
7. Close Session / clear tenant context
```

Nếu đến bước 4 Session đã mở cho alpha rồi code mới đổi tenant context sang beta ở bước 5, việc đổi context không làm Session tự trở thành Session của beta.

Không dùng một default tenant như `public` hoặc `master` để xử lý mọi trường hợp thiếu context trong request cần truy cập dữ liệu tenant. Thiếu tenant identity đáng tin nên bị từ chối sớm, trừ khi đây là một luồng system/admin được mô hình hóa riêng với quyền cụ thể.

## 8. Tenant resolution trong Hibernate

Hibernate có API `CurrentTenantIdentifierResolver` nhằm xác định tenant identifier hiện tại khi Hibernate cần tạo Session trong các cấu hình hỗ trợ.

Ví dụ khái niệm cho phiên bản Hibernate có API generic:

```java
import org.hibernate.context.spi.CurrentTenantIdentifierResolver;

public final class TenantIdentifierResolver
        implements CurrentTenantIdentifierResolver<String> {

    @Override
    public String resolveCurrentTenantIdentifier() {
        String tenant = TenantContext.currentOrNull();
        if (tenant == null || tenant.isBlank()) {
            throw new IllegalStateException(
                "No tenant selected for persistence");
        }
        return tenant;
    }

    @Override
    public boolean validateExistingCurrentSessions() {
        return true;
    }
}
```

`TenantContext` là abstraction của ứng dụng, không phải class có sẵn của Hibernate. Generic signature và cách đăng ký resolver có thể khác giữa các nhánh Hibernate; kiểm tra Javadoc/API đúng major version trước khi sử dụng.

### 8.1. validateExistingCurrentSessions()

Ý nghĩa của `validateExistingCurrentSessions()` là yêu cầu Hibernate kiểm tra tenant identity khi sử dụng một “current Session” đã tồn tại trong những cơ chế tương ứng.

Đây là một lớp phát hiện mismatch hữu ích, **không thay thế authorization**. Nó cũng không biến Session alpha thành Session beta và không nên được xem là giải pháp cho vấn đề thay tenant giữa transaction.

### 8.2. System jobs cần tenant scope tường minh

Một scheduled job không có HTTP request:

```text
Nightly job
    |
    +-- tenant alpha -> riêng Session/transaction
    +-- tenant beta  -> riêng Session/transaction
    +-- tenant gamma -> riêng Session/transaction
```

Job nên lấy danh sách tenant từ nguồn cấu hình/registry đáng tin rồi xử lý từng tenant theo policy; không sử dụng tenant còn sót trong ThreadLocal của thread pool.

## 9. Mở Session với tenant ID rõ ràng

Trong Hibernate native API, có thể yêu cầu Session gắn tenant ID khi mở:

```java
SessionFactory sessionFactory = ...;
String tenantId = "alpha";

try (Session session = sessionFactory
        .withOptions()
        .tenantIdentifier(tenantId)
        .openSession()) {

    Transaction tx = session.beginTransaction();
    try {
        Order order = session.find(Order.class, 17L);
        // Chỉ xử lý trong tenant alpha.
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
```

Mã trên minh họa Hibernate Session API và transaction management thuần Hibernate; trong Spring Boot thông thường không nên tạo Session/commit thủ công trong một service đã được `@Transactional` quản lý. Khi dùng Spring, hãy để tenant resolver/integration mở đúng tenant-scoped EntityManager ở transaction boundary.

Không cho controller chọn tùy ý `tenantIdentifier(request.getParameter("tenant"))` mà không có authorization.

## 10. Một Session gắn với tenant, không phải một tenant gắn với thread vĩnh viễn

Một số hệ thống lưu tenant context trong ThreadLocal:

```java
public final class TenantContext {
    private static final ThreadLocal<String> CURRENT =
        new ThreadLocal<>();

    private TenantContext() {}

    public static void set(String tenant) {
        CURRENT.set(tenant);
    }

    public static String currentOrNull() {
        return CURRENT.get();
    }

    public static void clear() {
        CURRENT.remove();
    }
}
```

ThreadLocal có thể thích hợp cho mô hình synchronous servlet/thread-per-request nếu **được thiết lập trước transaction và luôn clear trong finally**:

```java
try {
    TenantContext.set(authorizedTenantId);
    chain.doFilter(request, response);
} finally {
    TenantContext.clear();
}
```

Đoạn code là phần lõi minh họa của một filter sau authentication/authorization; chưa phải filter hoàn chỉnh hay cơ chế security đầy đủ.

Nguy cơ lớn khi quên `clear()`: servlet container tái sử dụng thread cho request của tenant khác. ThreadLocal cũ có thể khiến Hibernate resolver chọn sai tenant.

### 10.1. Async và reactive không giống synchronous servlet

Khi công việc chuyển sang thread khác qua `@Async`, `CompletableFuture`, executor hoặc mô hình reactive:

- ThreadLocal không tự propagate đúng cách.
- Một thread có thể phục vụ nhiều logical requests theo thời gian.
- Copy context mù có thể giữ tenant đã hết hạn hoặc người dùng không còn quyền.

Phải dùng context propagation phù hợp framework/runtime, thiết kế explicit tenant parameter ở job boundary và xác nhận transaction/EntityManager sử dụng đúng tenant. Không dùng một ThreadLocal đơn giản như giải pháp tổng quát cho mọi reactive pipeline.

## 11. Tenant resolver không phải cơ chế chọn quyền truy cập

Một resolver trả `alpha` chỉ nói Hibernate nên làm việc trong tenant alpha; nó không chứng minh user có quyền trên alpha.

Anti-pattern:

```java
String tenantId = request.getHeader("X-Tenant-Id");
TenantContext.set(tenantId);
```

Nếu thiếu xác thực, user Beta có thể tự đặt header Alpha. Một luồng đúng:

```text
JWT/session principal -> user ID
Requested tenant ID   -> input cần kiểm tra
Membership/role check -> user có quyền trên tenant?
                       /           \
                     NO            YES
                     |              |
                   403             TenantContext.set(...)
```

Với token mang active tenant claim, cần xác minh chữ ký, expiry, audience và nguồn phát hành. Không lấy tenant identity từ raw decoded JWT chưa được xác thực.

## 12. Shared schema với cột tenant_id

Mô hình một bảng chung:

```sql
CREATE TABLE purchase_orders (
    tenant_id VARCHAR(80) NOT NULL,
    id BIGINT NOT NULL,
    order_number VARCHAR(80) NOT NULL,
    total_amount NUMERIC(19, 2) NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
```

Dữ liệu:

```text
tenant_id   id   order_number
alpha       17   AL-0017
beta        17   BE-0017
alpha       18   AL-0018
```

Khi chạy:

```sql
SELECT *
FROM purchase_orders
WHERE id = 17;
```

database có thể trả **hai hàng**. Điều kiện đúng khi xử lý Alpha là:

```sql
SELECT *
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND id = :id;
```

`tenantId` phải xuất phát từ context đã được ủy quyền. Predicate này là yếu tố cốt lõi của phân vùng shared schema.

## 13. @TenantId trong các phiên bản hỗ trợ

Trong Hibernate 6.x có hỗ trợ discriminator-based multi-tenancy, annotation `org.hibernate.annotations.TenantId` giúp đánh dấu thuộc tính đại diện cho tenant identifier của entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.TenantId;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @TenantId
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    protected PurchaseOrder() {}
}
```

Với mapping và Session tenant-aware được cấu hình đúng, Hibernate có thể tự gắn tenant ID khi persist và áp dụng tenant restriction cho đường truy cập ORM tương ứng.

**Cần lưu ý về phiên bản:** `@TenantId` và các API/giới hạn multi-tenancy thuộc Hibernate-specific extensions; không có trong Jakarta Persistence chuẩn. Không copy vào Hibernate version cũ hoặc dự án provider khác mà không kiểm tra hỗ trợ.

### 13.1. @TenantId không phải field để user tự chỉnh

Không để API nhận JSON:

```json
{"tenantId": "beta", "orderNumber": "BE-0017"}
```

rồi tin rằng object sẽ an toàn khi thực thi dưới Session Alpha. Tenant ID phải do hạ tầng persistence đã xác thực quản lý; thay đổi giá trị tenant của entity đã persist là hành động có rủi ro cao và có thể không được Hibernate hỗ trợ.

Một command tạo Order nên chỉ cung cấp dữ liệu nghiệp vụ:

```java
public record CreateOrderRequest(
    String orderNumber,
    BigDecimal totalAmount) {}
```

Tenant context đến từ authentication + authorization, không phải từ editable field của client.

## 14. Cột tenant_id cần tham gia thiết kế khóa và index

Khi IDs chỉ unique trong từng tenant:

```sql
PRIMARY KEY (tenant_id, id)
```

giúp database ngăn duplicate trong cùng tenant nhưng cho phép alpha và beta cùng có `id=17`.

Tuy nhiên Hibernate/JPA entity identifier mapping phải phù hợp với khóa thật. Ví dụ chỉ đặt `@Id` trên `id` và `@TenantId` trên `tenantId` không có nghĩa **mọi cơ chế JPA composite ID** tự động ánh xạ đúng một primary key composite trong mọi version. Cần thiết kế mapping, ID generation và DDL nhất quán; khi cần composite identifier theo JPA, xem `@EmbeddedId`/`@IdClass` và tương thích với `@TenantId` của Hibernate version đang dùng.

Một lựa chọn khác là dùng ID toàn cục duy nhất và giữ tenant_id cho isolation:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    order_number VARCHAR(80) NOT NULL
);
```

Dù ID toàn cục duy nhất, SQL nghiệp vụ và quyền truy cập vẫn phải hạn chế tenant. Sự duy nhất của ID không thay thế tenant isolation.

## 15. Unique constraint phải tính tenant scope

Ví dụ hai tổ chức đều muốn có order number `ORD-001`. Nếu uniqueness chỉ tính trong từng tenant:

```sql
CREATE UNIQUE INDEX uq_orders_tenant_number
ON purchase_orders (tenant_id, order_number);
```

Không sử dụng:

```sql
UNIQUE (order_number)
```

nếu nghiệp vụ cho phép các tổ chức khác nhau dùng cùng số đơn.

Ngược lại, những trường thực sự global như một external registry identifier có thể phải unique toàn hệ thống. Đừng máy móc thêm `tenant_id` vào mọi unique key; cần xác định invariant của từng entity.

Nếu dùng soft delete, có thể cần phối hợp `tenant_id` với active-only unique index theo DBMS:

```sql
-- Ví dụ PostgreSQL:
CREATE UNIQUE INDEX uq_active_tenant_order_number
ON purchase_orders (tenant_id, order_number)
WHERE deleted = FALSE;
```

SQL trên giả định bảng đã có cột `deleted`. Đây là một ví dụ của PostgreSQL, không portable nguyên vẹn sang mọi DBMS.

## 16. Foreign key phải ngăn tham chiếu chéo tenant

Giả sử:

```text
alpha: Customer #9
beta:  Customer #9
```

Order của Alpha không được tham chiếu Customer của Beta chỉ vì hai ID trùng nhau.

Ở mức relational schema có composite tenant-scoped key:

```sql
CREATE TABLE customers (
    tenant_id VARCHAR(80) NOT NULL,
    id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE purchase_orders (
    tenant_id VARCHAR(80) NOT NULL,
    id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, id)
);
```

Foreign key gồm tenant_id giúp database bảo vệ referential integrity ngay cả khi một câu SQL thủ công sai. Nếu chỉ có `FOREIGN KEY (customer_id) REFERENCES customers(id)` trong mô hình ID-per-tenant, constraint không thể xác định tenant đúng.

Mapping JPA/association của ứng dụng cũng phải tương thích composite keys/joins. Một annotation `@TenantId` trên hai entities không tự chứng minh tất cả database foreign keys đã tenant-aware.

## 17. Schema-per-tenant và tenant-scoped Session

Ở mô hình schema-per-tenant:

```text
PostgreSQL server
  schema alpha
    purchase_orders
    customers

  schema beta
    purchase_orders
    customers
```

Entity mapping Java có thể cùng tên bảng:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Nhưng khi Hibernate mở Session cho tenant Alpha, JDBC connection cần truy cập đúng schema Alpha; với Beta, đúng schema Beta. Hibernate có cơ chế multi-tenant connection provider để phục vụ việc này.

Không hard-code:

```java
@Table(schema = "alpha", name = "purchase_orders")
```

nếu kỳ vọng cùng mapping được dùng động cho tất cả schemas. Hard-code schema thường ràng buộc entity vào một schema cố định.

## 18. MultiTenantConnectionProvider làm gì?

Hibernate hỗ trợ SPI `MultiTenantConnectionProvider` cho những cách triển khai nhiều database/schema cần chọn JDBC resource theo tenant.

Về ý tưởng, provider cần:

- Cung cấp connection không gắn tenant khi Hibernate cần đọc metadata ban đầu trong những tình huống hỗ trợ.
- Cung cấp connection cho một tenant ID cụ thể.
- Giải phóng connection và khôi phục trạng thái trước khi trả pool.
- Quyết định có hỗ trợ aggressive release phù hợp transaction/connection handling mode không.

Sơ đồ:

```text
Hibernate Session(tenant=alpha)
              |
              v
MultiTenantConnectionProvider
              |
        tenant lookup
            /    \
           /      \
          v        v
      schema A   schema B
          |        |
          +--- JDBC connection / pool
                         |
                         v
                      Database
```

Đây là SPI cấp Hibernate. Spring Boot DataSource routing và `AbstractRoutingDataSource` là các công cụ khác; có thể kết hợp nhưng không thay thế việc đảm bảo tenant context, transaction và connection lifecycle đúng.

## 19. Ví dụ ý tưởng chọn schema

Một cách triển khai schema-per-tenant là lấy connection từ pool chung rồi thiết lập schema trước khi Hibernate dùng:

```java
Connection connection = sharedDataSource.getConnection();
connection.setSchema(authorizedSchemaName);
// Sử dụng connection cho Session tenant tương ứng.
```

Khi xong:

```java
try {
    connection.setSchema(defaultSchemaName);
} finally {
    connection.close(); // Trả connection về pool.
}
```

Đây là **mã giải thích cơ chế**, chưa phải implementation hoàn chỉnh của `MultiTenantConnectionProvider`. Một provider thật phải xử lý:

- Tenant ID → schema mapping qua whitelist/registry đáng tin.
- `getAnyConnection()/releaseAnyConnection()` và tenant-specific get/release theo SPI.
- Exceptions khi set schema thất bại.
- Không trả connection mang schema Alpha cho request Beta.
- Reset transaction/session settings khác nếu có.
- SQL metadata/DDL của database đích.

**Cực kỳ quan trọng:** không ghép trực tiếp một tên schema chưa kiểm soát từ HTTP request vào chuỗi SQL `SET search_path = ...`. Identifier không bind như value parameter thông thường; phải có whitelist và quoting theo DBMS.

## 20. Schema switching là trạng thái nằm trên connection

Hình dung:

```text
Pool has physical connection C1

Request alpha:
  borrow C1
  set schema = alpha
  query alpha.orders
  release C1

Request beta:
  borrow C1
  must set schema = beta
  query beta.orders
  release C1
```

Nếu provider quên thiết lập schema Beta hoặc quên reset/validate state, một connection được tái sử dụng có thể tiếp tục chạy dưới schema Alpha.

Trong mô hình PostgreSQL dùng `search_path` hoặc session variables cho Row-Level Security, trạng thái trên connection cần được hiểu rõ:

- Session-scoped settings có thể tồn tại qua transactions.
- Transaction-local settings chỉ có hiệu lực trong transaction hiện tại.
- Connection pool có thể tái sử dụng physical connections.
- Một lỗi exception không được bỏ qua trong bước cleanup.

Đây là nơi cần integration test **hai tenants xen kẽ trên cùng pool**, không chỉ test một tenant đơn lẻ.

## 21. Database-per-tenant và routing tới pool đúng

Ở mô hình database-per-tenant:

```text
tenant alpha -> DataSource A -> Alpha database
tenant beta  -> DataSource B -> Beta database
tenant gamma -> DataSource C -> Gamma database
```

`MultiTenantConnectionProvider` có thể chọn connection pool theo tenant ID. Mỗi database có thể có credentials, backup, migration và pool settings riêng.

Ưu điểm:

- Tenant có thể được cô lập tốt hơn ở tầng DB permissions và storage.
- Có thể scale/migrate tenant lớn độc lập.
- Backup/restore theo tenant dễ hơn trong một số kiến trúc.

Chi phí:

- N tenant có thể kéo theo nhiều pools/connections và metadata overhead.
- Cần provisioning tự động và lifecycle quản lý pool.
- Phải quản lý migrations cho mọi database.
- Có thể có tenant DB tạm thời không sẵn sàng.
- Việc điều chuyển tenant sang DB khác đòi hỏi bảo toàn routing consistency.

Tạo một pool vĩnh viễn cho mỗi tenant khi có hàng chục nghìn tenant có thể vượt giới hạn connection và memory. Cần chiến lược bounded pool, lazy initialization hoặc resource management phù hợp quy mô.

## 22. @TenantId và connection provider giải quyết các bài toán khác nhau

| Cơ chế | Vị trí phân tách | Ý nghĩa |
|---|---|---|
| `@TenantId` discriminator | Trong rows của một bảng chung | Tenant được nhận diện bằng mapped property/SQL predicate |
| Schema-per-tenant provider | JDBC connection/schema | Cùng mapping, schema physical khác |
| Database-per-tenant provider | JDBC connection/database | Connection chọn database theo tenant |
| `CurrentTenantIdentifierResolver` | Bước quyết định tenant context | Cho Hibernate biết tenant hiện tại |

Không nên gắn `@TenantId` vào entity rồi nghĩ Hibernate đã tự tạo schemas/databases riêng. Cũng không nên cấu hình schema provider rồi bỏ qua authorization tenant.

Đối với hỗn hợp mô hình (ví dụ nhiều clusters, mỗi cluster có shared-schema tenants), phải xác định rõ hai tầng routing và discriminator, đồng thời kiểm tra khả năng hỗ trợ trong Hibernate version thực tế.

## 23. Một transaction của tenant A không phải transaction của tenant B

Giả sử:

```java
@Transactional
public void createOrder(...) {
    // Hibernate tenant context = alpha
}
```

Transaction này được bắt đầu thông qua transaction manager và EntityManager gắn với Alpha. Không đổi sang Beta giữa method rồi dùng cùng transaction để ghi Beta:

```java
TenantContext.set("alpha");
Order a = em.find(Order.class, 17L);

TenantContext.set("beta"); // Anti-pattern.
Order b = em.find(Order.class, 17L);
```

EntityManager có thể vẫn là Session Alpha và trả `Order alpha#17` từ first-level cache. Thao tác này không an toàn và không thuộc contract để đổi tenant của Session.

Nếu cần thao tác hai tenants, xem đó là **hai unit of work riêng**, có authorization và transaction policy rõ; nếu dữ liệu nằm ở hai databases, không có một local transaction tự bảo đảm atomic commit cả hai.

## 24. Mối quan hệ giữa Spring @Transactional và tenant context

Trong Spring Boot dùng `JpaTransactionManager`, một luồng phổ biến:

```text
HTTP filter resolves and authorizes tenant
                 |
                 v
TenantContext.set("alpha")
                 |
                 v
Spring AOP intercepts @Transactional method
                 |
                 v
Transaction manager acquires/associates EntityManager
                 |
                 v
Hibernate resolves tenant / opens Session
                 |
                 v
Repository calls + flush + commit
                 |
                 v
Filter finally clears TenantContext
```

Vì transaction manager có thể tạo/bind EntityManager **ngay khi transaction bắt đầu**, tenant context phải được đặt trước khi gọi method `@Transactional` qua Spring proxy.

Nếu tenant context chỉ được set bên trong method sau một repository query đầu tiên, đã quá muộn để bảo đảm Session chọn đúng tenant.

### 24.1. OSIV làm ranh giới phức tạp hơn

Nếu bật Open EntityManager in View, EntityManager có thể được mở/bind ở web request scope trước khi service transaction bắt đầu. Khi đó tenant resolution phải sẵn sàng **trước khi OSIV tạo EntityManager**, không chỉ trước service method.

Với REST API nhiều tenant, nên cân nhắc tắt OSIV và chuyển entity sang DTO trong transaction:

```properties
spring.jpa.open-in-view=false
```

Đây là một lựa chọn kiến trúc thường hữu ích; không tự động giải quyết mọi lỗi tenant. Vẫn phải có filter/security ordering đúng và test request thực.

## 25. Một transaction chỉ an toàn khi các thao tác cùng tenant

Ví dụ một command tạo Order và OutboxEvent:

```text
Tenant alpha transaction
   |
   +-- INSERT orders(alpha, ...)
   +-- INSERT outbox_events(alpha, ...)
   |
   v
COMMIT cùng local database transaction
```

Nếu `OutboxEvent` vô tình dùng DataSource của tenant Beta, ý nghĩa transactional outbox bị phá vỡ. Outbox chỉ bảo đảm thay đổi nghiệp vụ và durable event được commit cùng nhau khi cả hai thuộc **cùng local transaction resource**.

Trong shared-schema model, mỗi outbox row thường cần tenant identity hoặc một envelope xác định tenant an toàn. Consumer phải kiểm tra tenant trước khi cập nhật read model.

## 26. Cross-tenant operations không tự có tính nguyên tử

Một admin job có thể cần chuyển dữ liệu từ Alpha sang Beta:

```text
Transaction A:
  đọc/đánh dấu Source record của alpha

Transaction B:
  tạo Target record của beta
```

Nếu A commit nhưng B lỗi, hệ thống rơi vào trạng thái dở dang. Nếu B commit trước A, còn trạng thái ngược lại.

Không sửa bằng cách đổi ThreadLocal tenant giữa hai repository calls trong cùng một `@Transactional`.

Các lựa chọn:

1. Thiết kế workflow idempotent, có source/target states và retry.
2. Dùng outbox/event-driven integration khi chấp nhận eventual consistency.
3. Dùng Saga với compensation nếu có nhiều business steps.
4. Cân nhắc JTA/XA/2PC khi thực sự cần atomic commit nhiều XA resources và hạ tầng hỗ trợ.
5. Khi dữ liệu nằm ở cùng database/connection và nghiệp vụ cho phép, thiết kế một thao tác DB có tính nguyên tử nhưng vẫn enforce authorization rõ.

Ngay cả khi cả hai tenants nằm trong shared schema, không nên tự cho phép service thường làm cross-tenant mutation. Đó là một capability quản trị riêng, cần audit và kiểm soát quyền chặt chẽ.

## 27. Chuyển tenant trong cùng request: nên làm thế nào?

Giả sử UI cho phép người dùng chuyển từ Alpha sang Beta. Cách an toàn nhất là tạo một request mới có tenant đã được xác thực/ủy quyền, để Hibernate mở một Session phù hợp.

```text
GET /alpha/orders
  authenticated alpha membership
  Session(alpha) -> commit/close

Switch organization in UI

GET /beta/orders
  authenticated beta membership
  Session(beta) -> commit/close
```

Nếu cần một màn hình admin hiển thị dữ liệu tổng hợp hai tenants, nên thiết kế aggregator chỉ đọc với **hai session/transactions tách biệt**, trả DTO và dán nhãn nguồn tenant cho từng record, thay vì gộp managed entities của hai tenants vào một persistence context.

## 28. First-level cache luôn có phạm vi Session

Hibernate first-level cache (L1) là persistence context:

```java
Order first = em.find(Order.class, 17L);
Order second = em.find(Order.class, 17L);
```

Trong cùng một Session tenant Alpha, `first` và `second` có thể là cùng managed object và lần đọc thứ hai không tạo SQL.

Điểm quan trọng:

- L1 **không** phải shared cache giữa requests.
- L1 **không** phải một bảng dữ liệu chung cho mọi tenant.
- L1 giữ managed state của tenant gắn với Session.
- L1 có thể stale nếu một writer khác sửa DB ngoài persistence context.

Nếu benchmark gọi `find()` 100 lần cùng Session rồi kết luận “tenant B được hưởng cache hit của Alpha”, phép đo đó đang hiểu sai L1. Để kiểm tra phân tách tenants, cần mở **hai Sessions độc lập** và dùng cùng entity ID ở hai tenants.

## 29. Vì sao không được đổi tenant khi L1 còn entity?

Giả sử:

```text
Session opened for alpha
  L1 contains Order(id=17, customer="Alpha Co")

Application changes ThreadLocal to beta
  L1 still contains Order(id=17, customer="Alpha Co")
```

Nếu code gọi `find(Order.class,17)` lần nữa, Hibernate có thể trả ngay entity managed của Alpha. Tenant resolver không được thiết kế như một công tắc “đổi dữ liệu trong cùng Session”.

Giải pháp:

1. Kết thúc transaction Alpha.
2. Đóng/giải phóng Session Alpha.
3. Xác thực và ủy quyền Beta.
4. Mở Session Beta mới.
5. Chỉ thao tác entities thuộc Beta trong Session đó.

Không coi `entityManager.clear()` là giải pháp đầy đủ để “chuyển tenant” trên cùng Session. Clear loại managed entities khỏi L1 nhưng không thay đổi tenant identity đã gắn với Session/JDBC resource.

## 30. Second-level cache chia sẻ factory nhưng phải phân biệt tenant

L2 cache của Hibernate thường có phạm vi `SessionFactory`. Nếu nhiều tenant sử dụng cùng factory, các Sessions khác tenants có thể cùng dùng cache backend/regions.

```text
SessionFactory
   |
   +-- Session(alpha) -> L2 Product(alpha, id=17)
   |
   +-- Session(beta)  -> L2 Product(beta, id=17)
   |
   v
Shared cache provider / regions
```

Trong Hibernate multi-tenancy được cấu hình đúng, domain-data cache keys cần phân biệt tenant identifier cùng với entity type/ID. Nhờ đó `Product(alpha,17)` và `Product(beta,17)` không va nhau dù cùng ID.

Nhưng cần phân biệt hai điều:

- Hibernate có cơ chế tenant-aware L2 key khi sử dụng multi-tenancy thông qua các API mà nó hỗ trợ.
- **Cache tự xây ở application, Spring `@Cacheable` và cache provider custom key implementation không tự an toàn chỉ vì có Hibernate**.

Nếu thay `CacheKeysFactory` hoặc implement cache provider tùy chỉnh, phải bảo toàn tenant identity trong key và kiểm thử cross-tenant collisions.

## 31. Một ví dụ L2 cache key khái niệm

Giả sử:

```text
Entity class: Product
Entity ID:    100

Tenant alpha -> name="Product Alpha"
Tenant beta  -> name="Product Beta"
```

Một cache key không an toàn:

```text
Product:100
```

Một key có tenant scope:

```text
alpha:Product:100
beta:Product:100
```

Đây là **mô hình key giải thích**, không phải biểu diễn serialized key bắt buộc của Hibernate. Hibernate có thể dùng object/key implementation riêng, bao gồm metadata như entity type, ID, tenant và cache factory configuration.

Nếu một developer quan sát Redis/Ehcache keys thấy không có chuỗi `alpha:` hiển thị, điều đó **không tự chứng minh cache không tenant-aware**; key có thể được serialize hoặc đóng gói. Phải kiểm chứng bằng hành vi đọc Alpha/Beta cùng ID trong các Sessions riêng.

## 32. Cấu hình L2 cache cho entity

Ví dụ khi cache provider phù hợp được cấu hình:

```java
@Entity
@Table(name = "products")
@Cacheable
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE)
public class Product {
    @Id
    private Long id;

    @TenantId
    private String tenantId;

    private String displayName;
}
```

Cấu hình Hibernate:

```properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.generate_statistics=true
```

Hai property này **chưa đủ** để có L2 cache hoạt động: vẫn cần cache provider/region factory, mappings và concurrency strategy tương thích Hibernate version.

Đừng bật cache cho tất cả entities. Một region chứa dữ liệu rất nhiều tenants ít sử dụng có thể tiêu tốn RAM, tăng eviction và giảm hiệu quả locality.

## 33. L2 cache hit của tenant A không phải quyền của tenant B

Một bài test:

```text
Step 1:
  Tenant alpha Session
  find(Product, 100) -> Product Alpha
  L2 put/hit tùy trạng thái warm

Step 2:
  Tenant beta Session
  find(Product, 100) -> Product Beta

Expected:
  Không bao giờ nhận Product Alpha trong Session Beta.
```

Có thể cả hai Sessions dùng chung region L2. Tách region theo tenant không nhất thiết là yêu cầu của Hibernate khi key đã chứa tenant ID, nhưng tách region/capacity có thể hữu ích cho performance hoặc isolation theo policy.

Quan trọng là **logic tenancy của cache key và access path**, không chỉ tên region.

## 34. Query cache cũng cần xét tenant identity

Hibernate query cache có thể lưu kết quả của những query được đánh dấu cacheable.

Ví dụ:

```java
List<Product> products = session
    .createSelectionQuery("""
        select p
        from Product p
        where p.categoryCode = :category
        order by p.id
        """, Product.class)
    .setParameter("category", "BOOKS")
    .setCacheable(true)
    .getResultList();
```

Tenant Alpha và Beta đều truy vấn `category=BOOKS`. Nếu query result cache dùng key chỉ gồm query string + parameter `BOOKS` mà không tách tenant, có nguy cơ trả IDs/results sai tenant.

Hibernate multi-tenancy/query-cache implementation phải bảo toàn tenant scope theo phiên bản và mapping hỗ trợ. Không tự tạo một cross-tenant query cache ngoài Hibernate chỉ từ SQL + parameters.

### 34.1. Test query cache bằng dữ liệu trùng keys

```text
Alpha BOOKS:
  Product(id=1, name="Alpha Book")

Beta BOOKS:
  Product(id=1, name="Beta Book")

Same HQL + same category parameter

Run Alpha query -> warm cache
Run Beta query  -> must return Beta Book
Run Alpha again -> must return Alpha Book
```

Test này cần xác nhận kết quả, không chỉ xem một counter hit.

## 35. Tại sao query cache hit không bảo đảm query an toàn?

Một query có thể có:

- Tenant discriminator mapping đúng.
- Entity L2 cache key đúng.
- Query cache strategy phù hợp.

Nhưng nếu query đi qua **native SQL tự viết** và thiếu predicate `tenant_id`, logic vẫn có thể trả dữ liệu ngoài quyền. Caching chỉ làm dữ liệu sai được tái sử dụng nhanh hơn.

Ngoài ra, query cache hit có thể cần hydrate entities từ L2 hoặc DB tùy Hibernate version/result layout. Vì vậy:

1. Kiểm tra tenant isolation bằng giá trị thực của kết quả.
2. Kiểm tra SQL generated hoặc native statement.
3. Kiểm tra cache keys/regions theo implementation.
4. Kiểm tra L2/query hit/miss/put.
5. Kiểm tra correctness dưới data update và tenant switching.

Một hệ thống “99% cache hits” có thể vẫn có lỗ hổng isolation nếu authorization sai.

## 36. Spring @Cacheable rất dễ thiếu tenant ID

Ví dụ nguy hiểm:

```java
@Cacheable(cacheNames = "productView", key = "#productId")
public ProductView getProduct(Long productId) {
    return repository.getRequired(productId);
}
```

Với cùng product ID 17:

```text
Request alpha -> cache[17] = Alpha Product
Request beta  -> cache[17] -> Alpha Product!
```

Spring Cache không tự biết tenant của Hibernate Session nếu cache key chỉ có `productId`.

Một thiết kế rõ hơn:

```java
@Cacheable(
    cacheNames = "productView",
    key = "#tenantId + ':' + #productId")
public ProductView getProduct(
        String tenantId, Long productId) {
    authorizeTenant(tenantId);
    return repository.getRequired(productId);
}
```

Đây là ví dụ khái niệm; `authorizeTenant` phải thật sự kiểm tra quyền và service phải đảm bảo Hibernate Session đang chạy trong cùng tenantId. Tham số tenantId được đưa vào cache key **không được là input tùy ý chưa xác thực**.

Tốt hơn, tạo một immutable `TenantEntityKey` có tenantId và entityId, dùng key generator nhất quán và tránh cache objects chứa dữ liệu nhạy cảm dùng chung giữa các security scopes.

## 37. Invalidation phải có tenant scope

Khi Alpha cập nhật Product #17:

```text
cache key: alpha:product:17
```

Nếu application chỉ evict:

```text
product:17
```

trong khi mọi entries thực dùng tenant-qualified keys, Alpha entry có thể không bị xóa.

Ngược lại, nếu application xóa cả cache region cho mọi tenant mỗi khi một tenant thay đổi, correctness có thể vẫn đảm bảo nhưng gây cache churn và hiệu năng kém.

Vì vậy:

- Cache writes/evictions phải dùng cùng key scheme tenant-aware.
- Event từ message broker phải mang tenant identity được xác minh.
- Không để event Beta evict dữ liệu Alpha do ID trùng.
- Cần test cập nhật một tenant không thay đổi kết quả tenant khác.
- Với cross-tenant maintenance, evict rõ ràng tất cả affected tenant keys/regions theo policy.

## 38. Một region chứa nhiều tenant có thể tạo noisy neighbor

Giả sử L2 cache có capacity 10.000 entries:

```text
Tenant alpha: 100 hot products được đọc liên tục
Tenant beta: import/report quét 500.000 products một lần
```

Nếu cùng region và eviction policy không có tenant-aware quotas, Beta scan có thể đẩy hot entries của Alpha khỏi cache, làm latency Alpha tăng.

Đây là vấn đề **performance isolation**, khác với security isolation:

- Cache key có thể vẫn phân biệt đúng tenant.
- Nhưng capacity/evictions có thể không công bằng giữa tenants.

Các phương án:

- Chỉ cache read-mostly/hot data có reuse.
- Điều chỉnh region capacity và expiry.
- Tách workloads hoặc cache regions khi cần.
- Hạn chế scan làm cache warming vô ích.
- Dùng metrics per tenant ở tầng application với cardinality kiểm soát.

Không thêm metric label cho từng tenant nếu có hàng trăm nghìn tenants; điều đó có thể gây cardinality explosion. Có thể theo dõi top tenants, tier hoặc phân nhóm phù hợp.

## 39. First-level, L2 và query cache khác nhau ở phạm vi tenant

| Tầng | Phạm vi | Phân tách tenant bằng gì? | Rủi ro |
|---|---|---|---|
| L1/persistence context | Một Session | Session thuộc tenant cố định | Đổi tenant context khi Session còn sống |
| Hibernate L2 | Nhiều Sessions trong một SessionFactory | Hibernate tenant-aware cache keys trong multi-tenancy hỗ trợ | Custom key/provider hoặc cấu hình sai |
| Hibernate query cache | Cacheable query results trong factory/provider | Tenant-aware query context/key theo integration | Native/custom query cache bypass, mismatched mappings |
| Spring Cache | Method result cache | Application key generator phải bao gồm tenant | Key chỉ có entityId |
| Redis/custom cache | Phụ thuộc application | Tên key/namespace + tenant/authorization | Dữ liệu chéo tenant, eviction sai |

Không nên gọi chung tất cả là “Hibernate cache”. Mỗi tầng có lifecycle, isolation và invalidation khác nhau.

## 40. Native SQL là đường dễ vượt qua tenant isolation

Ví dụ trong shared schema:

```java
List<?> rows = em.createNativeQuery("""
    SELECT id, order_number
    FROM purchase_orders
    WHERE status = :status
    """)
    .setParameter("status", "PAID")
    .getResultList();
```

Không có `tenant_id` trong SQL. Nếu database không có RLS hoặc view policy khác, query có thể trả orders từ mọi tenant.

Sửa:

```java
List<?> rows = em.createNativeQuery("""
    SELECT id, order_number
    FROM purchase_orders
    WHERE tenant_id = :tenantId
      AND status = :status
    """)
    .setParameter("tenantId", authorizedTenantId)
    .setParameter("status", "PAID")
    .getResultList();
```

**Bind tenantId như data parameter**; đừng nối user input thành SQL string. Native SQL không tự nhận tất cả các bảo đảm predicate của ORM discriminator mapping.

Với schema-per-tenant, native SQL còn phải đảm bảo connection đang ở đúng schema và không dùng identifier/schema từ client chưa được whitelist.

## 41. HQL/Criteria và bulk mutations

HQL thông thường trên entity tenant-aware:

```hql
select o
from PurchaseOrder o
where o.status = :status
```

có thể được Hibernate bổ sung tenant restriction theo mapping multi-tenancy hỗ trợ.

Nhưng bulk HQL:

```hql
update PurchaseOrder o
set o.status = :cancelled
where o.createdAt < :cutoff
```

và:

```hql
delete from PurchaseOrder o
where o.expiredAt < :now
```

có semantics khác entity-by-entity operations. Hibernate version, tenant strategy, inheritance mapping, filters và query translator quyết định SQL thực tế.

Không phỏng đoán rằng mọi bulk operation tự thêm predicate tenant trong mọi version. Thực hiện integration test:

1. Insert cùng loại dữ liệu vào tenant A và B.
2. Chạy bulk mutation trong Session tenant A.
3. Xem SQL generated.
4. Assert chỉ A thay đổi và B giữ nguyên.
5. Kiểm tra L1/L2/cache invalidation.

Nếu dùng native bulk SQL, tenant predicate và authorization phải được xử lý tường minh.

## 42. Database Row-Level Security (RLS) là một lớp bảo vệ khác

Trong shared-schema PostgreSQL, RLS có thể bắt database giới hạn rows theo session context được thiết lập đáng tin cậy:

```sql
ALTER TABLE purchase_orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_orders_policy
ON purchase_orders
USING (
    tenant_id = current_setting('app.tenant_id', true)
);
```

Đây là ví dụ định hướng PostgreSQL. Một hệ thống production còn cần kiểm soát quyền owner/BYPASSRLS, chính sách cho INSERT/UPDATE/DELETE, cách set/reset session setting và policy đối với giá trị NULL.

RLS có thể bảo vệ cả native SQL nếu được cấu hình đúng và connection không có quyền bypass. Nhưng:

- Hibernate `@TenantId` và RLS là hai lớp độc lập.
- Phải set tenant context ở database connection đúng thời điểm.
- Pooled connection phải reset context hoặc dùng transaction-local setting phù hợp.
- DB account với quyền đặc biệt có thể bypass policy.
- App vẫn cần authorization; RLS không tự xác thực user cuối.

Không tuyên bố “có RLS nên không cần unit tests cho cross-tenant leaks”.

## 43. Connection pool và tenant-specific session variables

Khi connection từ pool được tái sử dụng:

```text
Connection C1 reused:
  alpha request -> SET app.tenant_id='alpha'
  release C1
  beta request  -> must set app.tenant_id='beta'
```

Nếu không reset context, Beta request có thể gặp RLS policy của Alpha. Tùy SQL/driver:

- Session-scoped `SET` có thể giữ giá trị ngoài transaction.
- Transaction-scoped `SET LOCAL` cần transaction active.
- Connection pool có thể reset một số attributes nhưng không phải mọi custom session variable.

Provider/routing infrastructure phải quản lý từ lúc borrow đến lúc release, kể cả exception paths và rollback.

Trường hợp thiếu tenant context cần fail closed, không “tạm query với superuser” vì ứng dụng vẫn cần khởi động.

## 44. Một transaction có thể chứa nhiều SQL nhưng cùng tenant

```java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = PurchaseOrder.create(command);
    orders.persist(order);

    reservationService.reserve(order);

    outboxRepository.persist(
        OutboxEvent.orderCreated(order.getId()));
}
```

Mẫu này chỉ an toàn về tenant scope khi:

- Các repositories dùng cùng đúng persistence unit/connection tenant.
- Mọi entities/association references thuộc tenant được chọn.
- Outbox row mang đúng tenant ID.
- Các services không tự đổi TenantContext.
- Transaction manager và security scope rõ ràng.

Nếu reservationService dùng một database của hệ thống khác, nó không tự tham gia local transaction chỉ vì cùng call stack.

## 45. @Transactional(readOnly = true) không phải bảo vệ tenant

Ví dụ:

```java
@Transactional(readOnly = true)
public OrderView getOrder(long id) {
    return repository.readView(id);
}
```

`readOnly=true` có thể ảnh hưởng flush mode/hints và transaction configuration, nhưng không chọn tenant, không xác thực membership và không bảo đảm dữ liệu B không lọt vào response.

Muốn read-only tenant scope đúng, cần:

1. Authenticated principal.
2. Authorized tenant ID.
3. Session resolver/routing đúng tenant.
4. SQL tenant restriction hoặc database isolation.
5. Cache key tenant-aware.
6. Test kết quả với duplicate IDs và nhiều tenants.

Đừng dùng annotation transaction như thay thế security design.

## 46. Cross-tenant foreign keys trong shared-schema

Mô hình sai:

```text
Order(tenant_id=alpha, customer_id=9)
Customer(tenant_id=beta, id=9)
```

Nếu DB chỉ kiểm tra customer_id và customer ID không global unique, có thể vô tình gắn Order Alpha vào Customer Beta.

Một constraint tenant-scoped:

```sql
FOREIGN KEY (tenant_id, customer_id)
REFERENCES customers (tenant_id, id)
```

giúp ngăn tham chiếu xuyên tenant. Nhưng khi JPA association dùng `@ManyToOne`, cần khai báo join columns và constraints phù hợp. Không chỉ dựa vào filter ở SELECT để bù cho dữ liệu quan hệ đã sai.

Với schema-per-tenant/database-per-tenant, DB foreign keys thường chỉ có ý nghĩa **bên trong cùng tenant schema/database**. Cross-database references phải được mô hình hóa bằng IDs và integration policies riêng.

## 47. Entity associations khi một target bị chuyển tenant

Giả sử Order #10 của Alpha tham chiếu Customer #5 của Alpha. Việc đổi `customer.tenantId` sang Beta không phải một phép cập nhật property bình thường:

- Có thể làm sai foreign keys của Order.
- Có thể làm sai Hibernate identity/cache key.
- Có thể vi phạm authorization.
- Có thể làm lộ history/data của Alpha cho Beta.

Một thao tác “chuyển ownership giữa tổ chức” nên được thiết kế như **business workflow** có audit:

1. Xác minh quyền của nguồn và đích.
2. Xác định những bản ghi được di chuyển/sao chép.
3. Lập mapping ID đích.
4. Ghi dữ liệu trong transaction đích.
5. Đồng bộ/xóa/đánh dấu dữ liệu nguồn theo policy.
6. Reconcile khi partial failure.

Không tùy tiện sửa `tenant_id` của managed entity rồi gọi `save()`.

## 48. Một request chứa nhiều org IDs: yêu cầu đặc biệt

Giả sử endpoint admin:

```text
GET /reports?tenantIds=alpha,beta,gamma
```

Không nên đưa ba tenant IDs vào một Session đơn và mong Hibernate tự combine multi-tenant model.

Thay vào đó:

- Xác thực quyền truy cập từng tenant.
- Đọc từng tenant qua riêng Session/transaction hoặc read model tổng hợp được phép.
- Chuyển kết quả sang DTO có tenant labels.
- Đặt limit/pagination cho từng tenant để tránh memory explosion.
- Xác định consistency/freshness của báo cáo liên tenant.
- Không tái sử dụng managed objects giữa Sessions.

Một service chuyên trách “global reporting” có thể chạy trên một data warehouse với chính sách truy cập khác, thay vì lách `@TenantId` trong transactional application.

## 49. Multiple DataSources không đồng nghĩa multiple tenants

Một ứng dụng có hai DataSources:

```text
ordersDataSource
billingDataSource
```

chưa chắc đó là tenant isolation: có thể hai DB phục vụ hai bounded contexts của **cùng một tenant**.

Ngược lại, một shared-schema DataSource có thể chứa dữ liệu của hàng nghìn tenants. Vì vậy:

- Tenant boundary là **business ownership/security boundary**.
- DataSource boundary là **database connection/resource boundary**.
- Transaction boundary là **atomic commit/rollback boundary**.
- Persistence unit boundary là **mapping/SessionFactory boundary**.

Chúng có thể trùng nhau nhưng không phải cùng một khái niệm.

## 50. Hai EntityManagerFactory riêng có giúp cache isolation?

Nếu mỗi tenant có một `EntityManagerFactory` riêng, mỗi factory có persistence context và cache infrastructure riêng. Điều này có thể tạo sự cô lập mạnh hơn theo factory boundary, nhưng đổi lại:

- Metadata và connection resources nhân lên.
- Một factory-per-tenant có thể tốn RAM khi số tenant lớn.
- Schema migration/provisioning trở nên phức tạp.
- Factory lifecycle và restart phải được quản lý.

Một SessionFactory chung với Hibernate multi-tenancy hỗ trợ là lựa chọn khác, thường tiết kiệm metadata hơn. Không có một giải pháp luôn tối ưu; cần cân bằng isolation requirements, số tenants, DB layout và resources.

**Không tạo một EntityManagerFactory cho mỗi request**. Factory là tài nguyên lâu dài; Session mới là unit of work ngắn hạn.

## 51. Schema migration trong multi-tenancy

### 51.1. Shared schema

Một schema chung có migration chung:

```text
Migrate orders table
  add column / index / constraint
  validate mapping
```

Nhưng migration vẫn phải:

- Backfill tenant_id cho dữ liệu legacy.
- Đặt NOT NULL/foreign keys phù hợp.
- Chuyển unique indexes sang tenant-scoped nếu nghiệp vụ yêu cầu.
- Kiểm tra query plans theo dữ liệu từng tenant.
- Không để hàng không có tenant trở thành “dùng chung cho tất cả” ngoài policy.

### 51.2. Schema-per-tenant

```text
for each tenant schema:
  acquire migration lock
  apply versioned migrations
  record schema version
  validate
```

Nếu tenant Alpha đã ở schema version 12 nhưng Beta ở 11, application code phải biết có thể phục vụ cả hai không. Một rollout cần tương thích ngược hoặc migration orchestration để không có hàng nghìn tenants ở trạng thái hỗn hợp không được kiểm soát.

### 51.3. Database-per-tenant

Migrations cần chạy trên database của từng tenant, với retries, metrics và kiểm soát concurrency. Không giả định Spring Boot `spring.flyway.*` mặc định tự migrate mọi DataSource động.

## 52. Monitoring: không chỉ đo một hit ratio tổng

Các signals hữu ích:

| Nhóm | Metric/tín hiệu |
|---|---|
| Session | Tenant mismatch errors, Session creation/close, open contexts |
| Transaction | Commit/rollback counts, duration, failed transactions |
| JDBC | Pool active/idle/pending, schema reset failures, connection errors |
| SQL | Queries/request, DB time, rows scanned, missing tenant predicate incidents |
| L2 | Hit/miss/put, evictions, working set, region memory |
| Query cache | Hit/miss/put, invalidation, query reuse |
| Security | Cross-tenant access denials, unauthorized tenant switch attempts |
| Jobs | Per-tenant processing backlog, retries, partial failure |
| Migrations | Tenant schema version, failed migration count |

Để tránh rò dữ liệu hoặc metric cardinality quá lớn:

- Không gắn raw user ID/tenant ID lên mọi metrics nếu có số lượng tenants lớn.
- Dùng top-N tenants, plan tier hoặc cohort.
- Đặt correlation ID trong trace/log có kiểm soát và thực hiện redaction.
- Không log nhạy cảm JDBC credentials hoặc full SQL bind parameters trong production.

## 53. Vì sao cache hit ratio tổng có thể đánh lừa?

Giả sử:

```text
Tenant Alpha:
  L2 hits   = 90.000
  L2 misses = 10.000

Tenant Beta:
  L2 hits   = 100
  L2 misses = 9.900
```

Tổng hit ratio là:

```text
(90,000 + 100) /
(90,000 + 10,000 + 100 + 9,900)
≈ 81.9%
```

Nhưng Beta có tỷ lệ hit khoảng 1%, rất khác Alpha 90%. Nếu Beta là tenant lớn theo doanh thu hoặc chịu latency nghiêm ngặt, nhìn hit ratio tổng có thể che vấn đề.

Cần đo theo traffic class/tenant cohort hoặc sampling thích hợp; Hibernate `Statistics` theo SessionFactory không tự cung cấp metric tuyệt đối chính xác theo từng tenant trong mọi API/version. Không suy ra tenant-specific cache statistics khi nguồn chỉ có aggregate counters.

## 54. Phân tách dữ liệu và phân tách tài nguyên là hai mục tiêu

Có hai loại isolation:

1. **Data isolation:** Beta không bao giờ đọc/ghi dữ liệu Alpha nếu không có quyền.
2. **Resource isolation:** Workload nặng của Beta không khiến Alpha bị cạn pool/cache/CPU và phá SLO.

Một shared DB và L2 cache với tenant-aware keys có thể giải quyết data isolation nhưng vẫn có noisy neighbor.

Công cụ resource isolation có thể gồm:

- Database-per-tenant cho khách hàng lớn.
- Pool quotas hoặc routing theo tenant tier.
- Read replica/reporting database tách khỏi OLTP.
- Rate limits/concurrency limits cho batch jobs.
- Cache capacity/eviction policies theo workload.
- Query timeouts và statement cost guardrails.

Không kết luận bảo mật đã tốt chỉ từ việc performance ổn, hoặc performance đã cô lập chỉ vì tenant data không bị lẫn.

## 55. Không sử dụng tenantId như tùy chọn nullable

Ví dụ nguy hiểm:

```java
String tenant = TenantContext.currentOrNull();
if (tenant == null) {
    return allOrders(); // Anti-pattern.
}
return ordersFor(tenant);
```

Một request không có tenant context không được tự động trở thành admin request xem tất cả.

Thiết kế đúng:

- Endpoint tenant-scoped: không có tenant → từ chối.
- Endpoint admin: xác thực role/capability riêng, service/repository riêng, audit.
- Background job: được cấu hình explicit tenant/system scope.
- Public/reference data: tách mapping/endpoint khỏi business tenant data.

Một “root tenant” hoặc special tenant identifier nếu được Hibernate version hỗ trợ phải được xem là capability đặc biệt và bảo vệ như quyền quản trị, không phải default fallback.

## 56. Public/shared reference data và tenant data

Ứng dụng có thể có:

```text
Global Country table:
  VN, US, JP

Tenant-scoped Customer table:
  alpha customers
  beta customers
```

Không phải mọi entity đều cần `tenant_id`. Nhưng phải phân loại rõ:

- Entity global, read-only/shared.
- Entity tenant-scoped.
- Entity tenant-customized kế thừa giá trị mặc định.
- Entity quản trị chỉ system role được phép sửa.

Association giữa tenant entity và global entity có thể hợp lệ theo model. Association giữa tenant Alpha entity và tenant Beta entity thường không hợp lệ.

Nếu dùng một SessionFactory có tenant context, hãy kiểm tra mapping của entities shared và tenant-scoped; đừng tự thêm `@TenantId` vào mọi bảng mà không xem business ownership.

## 57. Tenant identity trong events và background workers

Một outbox event:

```json
{
  "eventId": "e-123",
  "tenantId": "alpha",
  "aggregateType": "Order",
  "aggregateId": "17",
  "eventType": "OrderCreated"
}
```

Consumer phải:

1. Xác minh nguồn event/broker credentials.
2. Kiểm tra tenant registry/quyền xử lý.
3. Thiết lập tenant context **trước khi mở transaction**.
4. Xử lý idempotently theo key chứa tenant scope.
5. Commit transaction đúng tenant.
6. Clear context trong finally.

Ví dụ idempotency key:

```java
public record ProcessedEventKey(
    String tenantId, UUID eventId) {}
```

Nếu inbox dùng `eventId` một mình và các nguồn có thể phát trùng ID giữa tenants, có thể chặn nhầm event hợp lệ. Dùng unique constraints/ID policy đúng hệ thống.

## 58. Tenant context khi retry

Một batch job:

```text
Attempt 1:
  tenant alpha
  transaction fails, retry scheduled

Attempt 2:
  worker thread reused from tenant beta job
```

Nếu retry task không mang explicit tenant identity và tin ThreadLocal cũ, có thể ghi sai database.

Một retry command nên lưu:

```java
public record RetryableTenantCommand(
    String tenantId,
    String operationId,
    long aggregateId) {}
```

Worker nhận command và xác thực quyền hệ thống, thiết lập tenant context, bắt đầu transaction mới rồi clear trong finally.

Không mang một Hibernate Session/EntityManager qua retries. Một failed transaction/persistence context không phải state sạch để tái sử dụng.

## 59. Consistency khi đổi tenant database routing

Với database-per-tenant, cấu hình có thể đổi:

```text
Before migration:
  tenant alpha -> Cluster 1

After migration:
  tenant alpha -> Cluster 3
```

Nếu routing registry đổi khi Session Alpha đang hoạt động:

- Session hiện tại có thể vẫn giữ connection cũ.
- Một request mới có thể lấy connection mới.
- Ghi đồng thời vào hai clusters có thể tạo split-brain.

Tenant move cần quy trình:

1. Chặn/giới hạn writes hoặc đảm bảo replication cutover nhất quán.
2. Copy và đối chiếu dữ liệu.
3. Cập nhật routing registry atomically theo policy.
4. Drain/close old Sessions và connection pools khi cần.
5. Reset/invalidate caches phù hợp.
6. Kiểm chứng read-after-write và rollback strategy.

Không chỉ đổi một key trong `Map<tenantId, DataSource>` giữa production traffic mà tin mọi transaction sẽ tự chuyển nhất quán.

## 60. Kịch bản tấn công và lỗi dễ bị bỏ qua

### 60.1. IDOR xuyên tenant

User Beta biết Order ID 17 của Alpha, gọi:

```text
GET /orders/17
```

Nếu Hibernate Session/authorization đang ở Beta đúng, nó không được trả Alpha order dù entity ID trùng hoặc trông giống nhau. Test IDOR phải thử cả shared-schema và cache-warmed scenarios.

### 60.2. Tenant context bị rò qua thread pool

Request Alpha bỏ quên ThreadLocal; request Beta tiếp theo trên cùng thread dùng Alpha context. Ngăn bằng `finally remove()`, filter ordering và test sequential alternating tenants.

### 60.3. Connection pool giữ schema trước

Connection Alpha được trả pool mà không reset. Beta borrow lại và truy cập Alpha schema. Ngăn bằng trusted schema routing, setup/cleanup đúng và connection reuse tests.

### 60.4. Cache entry thiếu tenant

`@Cacheable(key="#id")` trả Alpha DTO cho Beta. Ngăn bằng tenant-qualified keys và tests với cùng entity IDs.

### 60.5. Native SQL thiếu tenant predicate

Một report dùng `SELECT * FROM orders` trả mọi tenants. Ngăn bằng code review, query abstraction, DB RLS khi phù hợp và integration tests.

### 60.6. Cross-tenant association

Order Alpha tham chiếu Customer Beta nếu foreign key chỉ theo ID hoặc authorization thiếu. Ngăn bằng composite tenant-aware FKs và validation.

## 61. Test case 1: cùng ID nhưng dữ liệu khác tenant

Fixture:

```text
Alpha:
  Product #17, name="Alpha Product"

Beta:
  Product #17, name="Beta Product"
```

Pseudo-test:

```java
String alphaName = inTenant("alpha", session ->
    session.find(Product.class, 17L).getDisplayName());

String betaName = inTenant("beta", session ->
    session.find(Product.class, 17L).getDisplayName());

assertEquals("Alpha Product", alphaName);
assertEquals("Beta Product", betaName);
```

`inTenant(...)` là test helper do ứng dụng tạo, phải mở Session/transaction mới đúng tenant và đóng tài nguyên. Cần thực thi theo hai thứ tự Alpha→Beta và Beta→Alpha, có L2/query cache bật và tắt.

## 62. Test case 2: Session không đổi tenant khi ThreadLocal đổi

Kịch bản:

```text
1. Set tenant alpha.
2. Begin transaction / open Session alpha.
3. Find Product #17 -> Alpha Product.
4. Change ThreadLocal tenant to beta (test only).
5. Attempt another find in same Session.
6. Assert implementation không tự trở thành beta.
7. Ensure mismatch is rejected/detected where configured.
```

Test này làm rõ contract. Không đưa thao tác đổi tenant trong Session vào business code thật; nó là trường hợp kiểm tra phòng vệ và mô hình mental.

Nếu `CurrentTenantIdentifierResolver.validateExistingCurrentSessions()` được bật, kiểm chứng behavior cụ thể theo Hibernate version/session context. Test không được giả định một message exception duy nhất cho mọi integration.

## 63. Test case 3: two-tenant transaction separation

Ví dụ schema-per-tenant hoặc database-per-tenant:

```text
Transaction Alpha:
  INSERT Order A
  COMMIT

Transaction Beta:
  INSERT Order B
  ROLLBACK

Expected:
  Alpha Order persists
  Beta Order absent
```

Nếu application có một “orchestration method” gọi cả hai services, test cố tình gây failure ở thời điểm giữa hai commits để chứng minh không có transaction chung và đảm bảo recovery workflow xử lý.

Không đặt `@Transactional` trên toàn test rồi để test framework rollback mặc định; như vậy có thể che commit boundaries. Dùng transactions thật và reads từ Sessions/Connections độc lập.

## 64. Test case 4: query cache và native SQL

Bật query cache, cùng HQL và parameters:

```text
1. Alpha query(category="BOOKS") -> result A.
2. Beta  query(category="BOOKS") -> result B.
3. Alpha query again -> still A.
4. Update Beta Product -> Alpha cache/result unchanged.
5. Run native SQL without tenant predicate in test-only path:
   verify it demonstrates why direct SQL must be guarded.
```

Khi test native SQL không an toàn, chỉ chạy trên dữ liệu giả trong môi trường cô lập; mục tiêu là phát hiện/sửa lỗi, không đưa query thiếu bảo vệ vào production.

Kiểm tra cả cache invalidation khi một tenant thay đổi state: không được trả stale data vượt quá policy và không làm lẫn dữ liệu giữa tenants.

## 65. Test case 5: connection reuse và schema reset

Với connection pool size 1:

```text
1. Open alpha Session -> read alpha.orders.
2. Commit/close -> return connection to pool.
3. Open beta Session  -> read beta.orders.
4. Commit/close.
5. Open alpha Session -> read alpha.orders.
```

Pool size nhỏ giúp tăng xác suất tái sử dụng cùng physical connection, làm lộ lỗi không reset schema/session variables. Test nên assert database-level schema/tenant context ở mỗi lượt nếu DBMS cho phép.

Thử thêm tình huống query Alpha ném exception ngay sau khi schema được set, rồi Beta tiếp tục, để kiểm tra cleanup trong failure path.

## 66. Test case 6: background job xen kẽ tenants

Một executor một thread:

```text
Job Alpha -> success
Job Beta  -> exception
Job Alpha -> retry
Job Gamma -> success
```

Mỗi job cần explicit tenant ID và `finally clear()`; thất bại Beta không được làm Gamma chạy trong Beta tenant context.

Nếu dùng `@Async`, hãy test context propagation đúng theo thread model; đừng dựa vào ThreadLocal của request thread tồn tại trên worker thread.

## 67. Test case 7: shared-schema FK và unique

Database tests:

```text
Alpha Customer #9 exists.
Beta  Customer #9 exists.

Alpha Order references Alpha Customer #9 -> allowed.
Alpha Order attempts to reference Beta Customer #9 -> rejected
  by schema/domain policy.

Alpha order_number "A-001" -> allowed.
Beta  order_number "A-001" -> allowed if scoped per tenant.
Alpha duplicate "A-001" -> rejected.
```

Đây là ranh giới mà Hibernate tenant predicate không đủ nếu các câu native SQL hoặc migrations vô tình ghi FK sai. Database constraints tenant-aware làm giảm phụ thuộc vào hành vi của một application code path.

## 68. Test case 8: quản trị cross-tenant được ủy quyền

Một admin endpoint cần tổng hợp hai tenants:

- Regular user Beta không thể yêu cầu danh sách Alpha.
- Admin được phép mới tạo các Sessions riêng.
- Kết quả DTO mang tenant label để không nhầm ID.
- Audit log ghi ai đọc dữ liệu cross-tenant.
- Không giữ managed entities từ Alpha trong Session Beta.
- Không áp dụng cùng local transaction lên hai databases rồi tuyên bố atomic.

Nếu test chỉ xác nhận người dùng bị từ chối qua controller nhưng service nội bộ vẫn cho đọc mọi tenant, cần bổ sung authorization ở service boundary hoặc cơ chế phù hợp hơn.

## 69. Một Spring service pattern có tenant scope rõ

Ví dụ:

```java
@Service
public class ProductReadService {

    private final ProductRepository products;
    private final TenantAuthorization authorization;

    public ProductReadService(
            ProductRepository products,
            TenantAuthorization authorization) {
        this.products = products;
        this.authorization = authorization;
    }

    @Transactional(readOnly = true)
    public ProductView getProduct(long productId) {
        String tenantId = TenantContext.currentOrNull();
        if (tenantId == null) {
            throw new IllegalStateException("Missing tenant");
        }

        authorization.requireAccess(tenantId);

        Product product = products.findById(productId)
            .orElseThrow();

        return new ProductView(
            product.getId(),
            product.getDisplayName());
    }
}
```

Ví dụ giả định request filter đã authenticate/authorize và set tenant **trước khi transaction bắt đầu**. Kiểm tra lại trong service là defense in depth; nếu context bị set muộn sau Session creation, việc kiểm tra này không tự sửa Session đang thuộc tenant khác.

Các classes `ProductView`, `ProductRepository` và `TenantAuthorization` do ứng dụng định nghĩa. Đừng lấy đoạn này như cấu hình multi-tenancy hoàn chỉnh khi chưa có resolver/provider/schema/DB policy.

## 70. Các lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tenant Beta thấy dữ liệu Alpha | Context hoặc SQL/cache key sai | Test duplicate IDs, auth, Session binding |
| Đổi tenant context nhưng query vẫn đọc Alpha | Session Alpha đã mở và L1 còn entity | Đóng Session, mở Session mới |
| Sau request lỗi, tenant kế tiếp bị sai | ThreadLocal không clear | `finally remove()`; test thread reuse |
| Connection Beta đọc schema Alpha | Schema/session settings không reset | Provider setup/cleanup và pool reuse test |
| `@TenantId` không được nhận diện | Hibernate version/provider không hỗ trợ | Kiểm tra runtime Hibernate version và mapping |
| Unique constraint chặn key của tenant khác | Unique index không có tenant_id | Migrate tenant-scoped uniqueness |
| Order liên kết nhầm Customer tenant khác | FK không chứa tenant_id | Composite tenant-aware FK |
| Native report trả mọi tenants | SQL thiếu tenant restriction | Bind trusted tenantId / DB RLS |
| Spring `@Cacheable` lộ dữ liệu | Key chỉ dùng entity ID | Tenant-qualified key và invalidation |
| Query cache trả sai tenant | Query/cache integration thiếu tenant scope | Kiểm tra provider/version, test same params |
| L2 hit ratio cao nhưng tenant lớn chậm | Aggregate metrics che noisy neighbor | Theo dõi region/workload cohorts |
| Tạo pool cho mỗi tenant gây cạn kết nối | Resource growth không giới hạn | Pool lifecycle/quotas hoặc kiến trúc khác |
| `@Transactional` không áp dụng | Self-invocation hoặc proxy boundary sai | Gọi qua Spring proxy, test transactions |
| Cross-tenant write chỉ một bên commit | Hai local DB transactions độc lập | Outbox/Saga/XA hoặc đổi workflow |
| Job chạy sai tenant khi retry | Context không được truyền rõ | Explicit tenant command, retry scope mới |
| OSIV mở Session trước tenant resolution | Filter/order sai | Resolve trước OSIV hoặc tắt OSIV |
| Hibernate cache đúng nhưng Redis sai | Cache app không tenant-aware | Key/namespace và security policy riêng |
| Migration mới chỉ áp dụng cho một schema | Tenant migration orchestration thiếu | Per-tenant schema version và monitoring |

## 71. Quy trình triển khai phân tách dữ liệu nhiều tổ chức

**Bước 1 — Xác định business tenant boundary.** Mỗi tài nguyên thuộc tenant nào? Có global data không? Ai có quyền cross-tenant?

**Bước 2 — Chọn mô hình database.** Shared schema, schema-per-tenant hay database-per-tenant theo yêu cầu isolation, scale và vận hành.

**Bước 3 — Cấu hình tenant-aware Hibernate.** Dùng `@TenantId` hoặc tenant connection provider/resolver phù hợp với mapping và phiên bản Hibernate.

**Bước 4 — Thiết lập tenant context đáng tin.** Authenticate/authorize trước khi mở Session; fail closed nếu không có tenant.

**Bước 5 — Chốt Session lifecycle.** Một Session/EntityManager cho một tenant, không đổi context giữa unit of work.

**Bước 6 — Chốt transaction boundary.** Một tenant transaction không mặc nhiên commit tài nguyên của tenant khác; thiết kế workflow/compensation khi cần.

**Bước 7 — Bảo vệ database schema.** Tenant-scoped unique keys, FKs, indexes, RLS và pool/schema reset khi phù hợp.

**Bước 8 — Bảo vệ cache.** Kiểm tra L1, Hibernate L2, query cache và Spring/custom cache keys khi IDs trùng giữa tenants.

**Bước 9 — Kiểm tra mọi SQL paths.** HQL, Criteria, bulk mutations, native SQL, JDBC, ETL, background jobs và read models.

**Bước 10 — Thử lỗi thực.** Threads reused, pool size 1, exception during cleanup, cache warm, cross-tenant IDs, admin permissions, partial commits.

**Bước 11 — Vận hành.** Monitoring tenant-related failures, pool, DB latency, L2/query cache churn, migrations và reconciliation.

## 72. Sơ đồ ranh giới Tenant → Session → Transaction → Cache

```text
                    Authenticated request
                             |
                             v
                 Authorized tenant identity
                             |
                             v
                     Tenant context
                             |
                             v
                  Open Session for tenant T
                             |
          +------------------+------------------+
          |                  |                  |
          v                  v                  v
   Persistence Context  Transaction       JDBC routing
    L1: tenant T        for tenant T      tenant T schema/DB
          |                  |                  |
          +------------------+------------------+
                             |
                             v
                    Hibernate ORM SQL
                             |
                  +----------+-----------+
                  |                      |
                  v                      v
             L2 entity cache        Query cache
            tenant-aware key      tenant-aware context
                  |                      |
                  +----------+-----------+
                             |
                             v
                        DB query
                             |
                             v
                   Commit or rollback T
                             |
                             v
                Close Session, clear context
```

Các nhánh L1/L2/query cache được vẽ để thể hiện ranh giới; thứ tự lookup thực tế khác theo loại thao tác, query và Hibernate version. Không dùng sơ đồ như thứ tự xử lý SQL bắt buộc.

## 73. Checklist ngắn cho code review nhiều tenant

Khi review một repository/service, hãy hỏi:

1. Tenant ID đến từ nguồn nào, ai xác minh user có quyền?
2. Tenant ID được thiết lập **trước** khi transaction/Session được mở chưa?
3. Code có đổi TenantContext giữa transaction hoặc dùng Session qua threads không?
4. Native SQL/bulk statements có tenant restrictions đúng không?
5. Mọi association/FK có cho phép cross-tenant ID collision không?
6. Unique constraints có thực hiện đúng uniqueness scope không?
7. Cache key có bao gồm tenant cho mọi custom/Spring caches không?
8. Cache invalidation có cùng tenant scope với cache put/read không?
9. Connection pool có reset schema/session variables kể cả khi exception không?
10. Các job, retry, outbox consumers có explicit tenant context không?
11. Có test dữ liệu trùng ID, trùng query parameters giữa hai tenants không?
12. Có kế hoạch xử lý cross-tenant admin workflow, partial commit và migrations không?

Nếu không trả lời được các câu hỏi này, một test CRUD thành công cho một tenant chưa đủ bằng chứng về multi-tenancy isolation.

## 74. Tổng kết

Trong ứng dụng Hibernate phục vụ **nhiều tổ chức**, ranh giới dữ liệu phải xuyên suốt từ authorization đến persistence:

- **Session/persistence context:** mỗi Session được mở cho một tenant đã xác thực và tenant identity phải giữ ổn định trong suốt unit of work. Không đổi ThreadLocal để “chuyển tenant” khi Session còn sống. L1 cache là identity map của Session và có thể giữ entity của tenant cũ.
- **Transaction:** `@Transactional` chỉ điều khiển resources của transaction manager đã chọn. Hai tenant dùng hai databases/connections không mặc nhiên chia sẻ một atomic transaction; cross-tenant workflows cần idempotency, retry, outbox/Saga hoặc distributed transaction thật khi phù hợp.
- **Cache:** Hibernate L2/query cache trong multi-tenancy được hỗ trợ phải dùng tenant-aware context/keys; nhưng Spring Cache và caches tự xây cần tenant-qualified keys và invalidation riêng. Một entity ID hoặc query parameter trùng không được khiến Alpha nhận dữ liệu của Beta.

Shared schema cần tenant discriminator, composite constraints và SQL predicates phù hợp. Schema-per-tenant/database-per-tenant cần routing connection đúng và cleanup trạng thái của pooled connections. Với cả ba mô hình, native SQL, bulk mutations, background jobs và admin access là các đường phải kiểm thử riêng.

**Nguyên tắc cốt lõi:** tenant là một phần của ngữ cảnh định danh và quyền truy cập, không phải một biến tùy chọn để thay đổi giữa chừng. Phân tách Session, transaction và cache được coi là thành công khi **cùng ID, cùng query, cùng pool và cùng cache backend vẫn không thể làm dữ liệu của hai tổ chức bị lẫn**, kể cả khi xảy ra lỗi, retry hoặc thay đổi tenant liên tiếp.
