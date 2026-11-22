# Xác minh SQL, lược đồ và dữ liệu sau thay đổi hạ tầng

Khi nâng cấp database, thay JDBC driver, đổi JPA provider, chuyển từ máy chủ vật lý lên managed database, thay connection pool hoặc triển khai một migration lớn, ứng dụng có thể **khởi động thành công nhưng đọc sai dữ liệu, gửi SQL khác trước, hoặc chỉ lỗi khi gặp tải thực tế**.

Ví dụ: dịch vụ Order chuyển từ PostgreSQL phiên bản cũ sang một cụm mới. Health check trả HTTP 200; `EntityManagerFactory` khởi tạo được; một câu `SELECT 1` chạy thành công. Nhưng sau khi đưa traffic vào:

- Truy vấn JPQL danh sách Orders chậm vì optimizer dùng execution plan khác.
- Migration thiếu unique constraint `(tenant_id, order_no)`.
- Cột `created_at` được xử lý timezone khác, làm mất Orders ở biên ngày.
- Dữ liệu backfill có một số `NULL` hoặc orphan records.
- Một connection vẫn trỏ sang database cũ do routing/proxy hoặc cấu hình sai.
- Tính năng insert gặp lỗi sequence không đồng bộ sau khi import.
- Lazy associations xuất hiện N+1 do provider/fetch-plan behavior khác.
- Read replica có lag khiến API đọc lại ngay sau ghi mà chưa thấy kết quả.
- Schema test có mặt đủ cột nhưng thiếu partial index, CHECK constraint hoặc trigger.
- API trả đúng số rows tổng nhưng sai tenant hoặc sai giá trị tiền.

Những sự cố này không thể phát hiện đầy đủ bằng `SELECT 1`, chỉ đếm rows hoặc một test `repository.save()` rồi `findById()` trong cùng persistence context.

Bài **“Xác minh SQL, lược đồ và dữ liệu sau thay đổi hạ tầng”**, thuộc chương **Vận hành và di trú** trong chủ đề **Data Persistence Relational Access ORM JPA**, trình bày cách xây dựng **quy trình xác minh đa lớp** trước, trong và sau thay đổi:

1. Xác định phạm vi thay đổi, nguồn sự thật và điều kiện chấp nhận.
2. Xác minh endpoint JDBC, database/schema thực, quyền truy cập và phiên bản.
3. Xác minh lịch sử migration, cấu trúc schema, constraints, indexes và mappings JPA.
4. Thu và so sánh SQL thật do JPQL/Criteria/Spring Data sinh ra.
5. Xác minh truy vấn, transaction, locking, optimistic version và lỗi dữ liệu.
6. Đối soát dữ liệu đã chuyển bằng khóa nghiệp vụ, counts, aggregates, checksums và mẫu sai lệch.
7. Kiểm tra hiệu năng, execution plans, connection pools, cache và replication.
8. Kiểm thử quá trình expand–migrate–contract, cutover, rollback/forward-fix và quan sát hậu triển khai.

Ví dụ dùng **Java 17+, Jakarta Persistence 3.x, Hibernate ORM, PostgreSQL, JUnit 5, Flyway và Testcontainers**. Các lệnh SQL catalog, `EXPLAIN (ANALYZE, BUFFERS)`, `pg_indexes`, `pg_stat_replication` là **PostgreSQL-specific**; MySQL, SQL Server, Oracle hoặc database khác có các truy vấn catalog và khả năng vận hành khác. Chúng là ví dụ cho một phương pháp kiểm chứng, không phải script chạy đại trà không cần điều chỉnh.

**Nguyên tắc trung tâm:** một thay đổi hạ tầng chỉ được coi là an toàn khi chứng minh được **đúng nơi kết nối, đúng lược đồ, đúng SQL, đúng dữ liệu, đúng transaction semantics và mức hiệu năng chấp nhận được**.

---

## 1. “Thay đổi hạ tầng” bao gồm những gì?

Trong hệ thống ORM/JPA, hạ tầng không chỉ là máy chủ database.

| Nhóm thay đổi | Ví dụ | Nguy cơ riêng |
| --- | --- | --- |
| Database engine/version | PostgreSQL 14 → 16 | Planner, collation, extension, behavior |
| Database topology | Primary → cluster, failover, replica | Routing, lag, consistency |
| Database location | On-premise → cloud | Network, TLS, timeouts, permissions |
| JDBC driver | PostgreSQL JDBC bản cũ → mới | Binding, timestamp, batching, metadata |
| ORM provider | Hibernate version upgrade | Generated SQL, schema validation, fetch/dirty checking |
| JPA mappings | Đổi column/type/relationship | Data loss, column mismatch, cascade |
| Schema migration | Add column/index/constraint, rename | Lock, backfill, compatibility |
| Pool/proxy | HikariCP, PgBouncer, managed proxy | Prepared statements, session state, transaction mode |
| Security | TLS, credentials rotation, RLS | Query authorization, schema/search_path |
| Cache | L2/query cache, distributed cache | Stale reads, invalidation |
| Application deployment | Rolling upgrade nhiều versions | Old/new schema compatibility |

Một release có thể chứa **nhiều nhóm thay đổi cùng lúc**. Khi đó khó xác định nguyên nhân regression; nên tách các bước và cổng xác minh khi có thể.

## 2. “Xác minh” không giống “migration chạy không báo lỗi”

Một migration báo success chỉ chứng minh công cụ đã hoàn tất công việc theo chính cơ chế của nó. Nó **không tự chứng minh**:

- Dữ liệu đã được backfill đúng.
- Ứng dụng đang đọc đúng schema vừa migrate.
- Tất cả instances đã chuyển sang database mới.
- Index thực sự được dùng.
- SQL/JPA behavior không đổi.
- Không phát sinh N+1.
- Các constraints cần thiết đã được tạo đúng.
- Không có dữ liệu bỏ sót hoặc duplicate theo tenant.
- Không có latency/tail-error regression.
- Rollback path còn khả thi.

Vì vậy dùng nhiều tầng kiểm chứng và các bằng chứng độc lập.

## 3. Sáu tầng xác minh tối thiểu

```text
┌─────────────────────────────────────────────────┐
│ 1. KẾT NỐI / ĐỊNH DANH                         │
│ Host, DB name, schema, role, server version     │
├─────────────────────────────────────────────────┤
│ 2. LƯỢC ĐỒ / MIGRATION                         │
│ Tables, columns, constraints, indexes, history  │
├─────────────────────────────────────────────────┤
│ 3. SQL / JPA                                   │
│ Generated SQL, params, query results, fetch     │
├─────────────────────────────────────────────────┤
│ 4. DỮ LIỆU / TÍNH NHẤT QUÁN                    │
│ Counts, keys, totals, hashes, FK/orphans        │
├─────────────────────────────────────────────────┤
│ 5. GIAO DỊCH / CẠNH TRANH                      │
│ Commit, rollback, locks, isolation, version     │
├─────────────────────────────────────────────────┤
│ 6. VẬN HÀNH / HIỆU NĂNG                        │
│ Latency, plans, pool, replication, errors       │
└─────────────────────────────────────────────────┘
```

Cần thêm một lớp xuyên suốt: **an toàn triển khai và rollback**. Nếu chỉ có metric và câu SQL nhưng không biết điều kiện dừng rollout, rủi ro vận hành vẫn cao.

## 4. Bắt đầu bằng change contract

Trước khi đụng database, lập một bảng ngắn:

| Thành phần | Trước thay đổi | Sau thay đổi | Điều kiện chấp nhận |
| --- | --- | --- | --- |
| JDBC endpoint | Old primary | New cluster | Không còn app instance trỏ nhầm |
| DB version | Version hiện tại | Version mục tiêu | Đã kiểm chứng driver/ORM |
| Schema version | Flyway V12 | Flyway V13 | History đúng, checksum hợp lệ |
| Order data | Nguồn chuẩn | Backfilled/cutover | Không thiếu/trùng keys, amounts đúng |
| API list | SQL pattern cũ | Pattern mới | Output đúng, không N+1 |
| Write path | Single DB | New primary | Commit/rollback/unique đúng |
| Latency | Baseline P95 | Sau rollout | Trong SLO đã xác định |
| Rollback | Deployment trước | Forward fix/revert plan | Biết điểm không thể quay lại |

Không điền các giá trị ngẫu nhiên nếu chưa đo. Một change contract nên ghi **owner**, thời điểm cutover, vị trí log/metrics, người phê duyệt và trigger dừng.

---

## 5. Mô hình Order và schema để minh họa

Các ví dụ theo dịch vụ nhiều tenant:

```text
Tenant
   └── PurchaseOrder (aggregate root)
         ├── OrderLine × N
         └── Customer reference
```

Entity:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_no", nullable = false)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private Long version;

    protected PurchaseOrder() {}

    // Domain methods, constructors, getters.
}
```

Các bảng quan trọng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    order_no VARCHAR(50) NOT NULL,
    customer_id BIGINT,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uq_orders_tenant_no
        UNIQUE (tenant_id, order_no),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id),
    CONSTRAINT ck_orders_total_nonnegative
        CHECK (total_amount >= 0)
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT ck_line_quantity
        CHECK (quantity > 0)
);
```

Đây là PostgreSQL DDL minh họa. Không giả định schema production y hệt; những lệnh query/catalog về sau phải chỉnh theo schema thật. Đặc biệt cần xác định kiểu `TIMESTAMP`/`TIMESTAMPTZ` và quy tắc timezone trước khi di trú.

## 6. Ví dụ thay đổi cụ thể: bổ sung trạng thái vận hành

Giả sử cần thêm cột `fulfillment_state` cho mỗi Order. Yêu cầu:

- Code cũ vẫn chạy khi schema mới được triển khai.
- Orders cũ phải có giá trị hợp lệ sau backfill.
- Code mới không được đọc `NULL` ngoài khoảng chuyển đổi được chấp nhận.
- Khi hoàn thành, database bắt buộc NOT NULL và có CHECK/enum policy.
- Không làm gián đoạn rolling deployment.

Một phương án expand–migrate–contract:

```text
Phase A: EXPAND
  ADD nullable column
  deploy code đọc null an toàn và ghi giá trị mới

Phase B: MIGRATE
  backfill dữ liệu cũ theo chunks
  verify null=0, mapping đúng, không miss rows

Phase C: CONTRACT
  enforce NOT NULL/constraint
  bỏ compatibility code sau khi old instances hết hoạt động
```

Đây là ví dụ về **compatibility discipline**, không phải một script bất biến cho mọi DB hoặc mọi SLA.

---

## 7. Xác minh đúng JDBC endpoint trước tiên

Một ứng dụng có thể khởi động bình thường khi trỏ sang **nhầm database**.

Đặc biệt nguy hiểm khi:

- Secret/config từ environment cũ còn hiệu lực.
- Một instance rolling deployment chưa nhận config mới.
- Connection pool đang giữ sessions cũ.
- Primary/replica routing sai.
- JDBC URL không chỉ định database name.
- Default schema/search_path khác.
- Proxy/sidecar đổi backend theo route.
- TLS verification bị vô hiệu hóa khi chuyển môi trường.

Việc đầu tiên không phải đọc table counts mà là **xác minh identity của backend thực đang phục vụ connection**.

## 8. SQL xác minh connection identity trên PostgreSQL

Một truy vấn read-only mẫu:

```sql
SELECT
    current_database()              AS database_name,
    current_schema()                AS default_schema,
    current_user                    AS database_user,
    session_user                    AS login_user,
    current_setting('server_version') AS server_version,
    inet_server_addr()              AS server_ip,
    inet_server_port()              AS server_port;
```

Giới hạn:

- `inet_server_addr()` có thể trả NULL trên Unix-domain socket.
- Qua proxy, thông tin server địa chỉ không phải lúc nào đại diện đầy đủ cho topology/routing.
- Database/schema/user vẫn cần đối chiếu môi trường mong đợi.
- Không hiển thị credentials trong diagnostics.
- `SELECT 1` không chứng minh schema/role chính xác.

Khi dùng connection pool, có thể sampling nhiều connections hoặc kiểm tra log/metrics theo pool/instance; **một connection đúng không chứng minh 100% instances/pool connections đã chuyển**.

## 9. Xác minh JDBC identity trong ứng dụng

Một diagnostic được phép chỉ trong môi trường test/health nội bộ:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    String databaseName = meta.getDatabaseProductName();
    String databaseVersion = meta.getDatabaseProductVersion();
    String driverName = meta.getDriverName();
    String driverVersion = meta.getDriverVersion();
    String catalog = connection.getCatalog();
    String schema = connection.getSchema();

    // So sánh với allowlist environment mong đợi.
    // Không log URL kèm credentials hoặc secrets.
}
```

Nên bổ sung PostgreSQL query `current_database/current_schema/current_user` vì JDBC metadata có thể không thể hiện search_path/role thực theo cách mong muốn.

**Không phơi diagnostic endpoint này ra public API** nếu thông tin DB/version/topology là nội bộ nhạy cảm.

## 10. Mọi app instance phải thống nhất connection target

Trong rollout:

```text
App A → old primary
App B → new primary
App C → old primary
App D → new primary
```

Có thể gây split-brain ở tầng application dù mỗi instance đều “healthy”. Cần:

- Kiểm tra configuration rollout per pod/VM.
- Quan sát active connections ở old/new DB.
- Đảm bảo secret rotation và pool restarts có hiệu lực.
- Có cơ chế cutover viết rõ primary owner.
- Kiểm tra connection proxy routing.
- Xác định liệu old DB còn writable hay đã bị khóa writers.
- Theo dõi replication/CDC catch-up nếu đang đồng bộ.

Không coi DNS change là bằng chứng mọi connection pool đã đóng connections cũ. Long-lived connections có thể tồn tại cho tới khi được recycle theo chính sách pool/proxy.

## 11. Search path và default schema

Đổi managed database có thể làm `search_path` khác:

```sql
SHOW search_path;
SELECT current_schema();
```

Nếu Flyway tạo `business.purchase_orders` còn JPA dùng unqualified `purchase_orders` trên `public`, có thể:

- Báo missing relation.
- Đọc một table khác trùng tên.
- Tạo schema drift.
- Gặp permission errors.
- Lỗi chỉ trên một số connections có session state khác.

Cần thống nhất:

- Flyway schemas/defaultSchema.
- Hibernate default schema hoặc `@Table(schema=...)` nếu cần.
- JDBC connection/session initialization.
- Database role search_path.
- RLS/tenant policy và schema routing.

Không sửa bằng cách cố tạo duplicate table ở nhiều schemas cho “đỡ lỗi”.

---

## 12. Xác minh migration history

Nếu dùng Flyway, thông tin cơ bản nằm trong `flyway_schema_history` ở schema được cấu hình.

Một truy vấn PostgreSQL ví dụ:

```sql
SELECT
    installed_rank,
    version,
    description,
    type,
    checksum,
    installed_on,
    success
FROM flyway_schema_history
ORDER BY installed_rank;
```

Tên và vị trí schema history table có thể được tùy chỉnh; với Flyway phiên bản khác có thêm/bớt fields. Điều cần xác minh:

- Không có failed migration.
- Version hiện tại khớp manifest release.
- Không có migrations ngoài ý định.
- Checksum khớp source migration code.
- Migration chạy trên **đúng database/schema**.
- Không có pending migration được bỏ qua bất ngờ.
- Application instances mới không cùng lúc chạy migration destructive khi chưa có coordination.

`Flyway.validate()` giúp kiểm tra tương ứng migrations đã áp và files nguồn theo policy công cụ. Nó **không chứng minh dữ liệu nghiệp vụ đã backfill đúng**.

## 13. Migrations phải là nguồn cấu trúc có phiên bản

Một workflow tương đối an toàn:

```text
Source-controlled migrations
        │
        ▼
Disposable DB migration test
        │
        ▼
Staging migration + data checks
        │
        ▼
Production migration với runbook
        │
        ▼
Schema catalog + Flyway validate
        │
        ▼
Application compatibility smoke tests
```

Không chỉnh một migration đã áp production chỉ để “sửa SQL cho đẹp” rồi bỏ qua checksum. Thông thường cần migration mới, hoặc quy trình repair được kiểm soát khi có lý do và audit trail rõ.

Migration success không được đánh đồng với dữ liệu migrated được so sánh nguồn/đích.

## 14. Hibernate schema `validate` chỉ là một lớp

Với Hibernate ORM:

```properties
hibernate.hbm2ddl.auto=validate
```

hoặc config Spring Boot:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

cho phép provider kiểm tra một số đặc điểm mapping/schema khi bootstrap.

Nhưng `validate` **không phải kiểm toán database toàn diện**, và thường không đảm bảo phát hiện mọi khác biệt trong:

- CHECK constraints.
- UNIQUE constraints.
- Foreign-key actions.
- Triggers/functions.
- Partial/expression indexes.
- Row-level security.
- Collations.
- Generated columns.
- Partitioning.
- Schema defaults.
- Sequence drift.
- Grants/roles.

Do đó cần schema-catalog checks và những integration tests thực sự vi phạm constraints quan trọng.

## 15. Catalog: kiểm tra columns và data types

PostgreSQL dùng `information_schema.columns`:

```sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    character_maximum_length,
    numeric_precision,
    numeric_scale
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'purchase_orders'
ORDER BY ordinal_position;
```

So sánh với manifest mong đợi:

- `tenant_id BIGINT NOT NULL`.
- `order_no` đủ chiều dài.
- `total_amount NUMERIC(14,2)`.
- `created_at` dùng kiểu thời gian chính xác.
- `version` không null.
- Cột mới hiện hữu, nullable/default policy đúng giai đoạn expand/contract.
- Không còn cột cũ sau khi đã kết thúc compatibility phase.

`information_schema` có thể không mô tả hết mọi PostgreSQL-specific metadata; dùng `pg_catalog` khi cần.

## 16. Kiểm tra constraints trực tiếp

Một cách đọc constraints:

```sql
SELECT
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid) AS definition,
    c.convalidated AS validated
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND t.relname = 'purchase_orders'
ORDER BY c.conname;
```

Các loại `contype` thường gặp:

- `p`: primary key.
- `u`: unique.
- `f`: foreign key.
- `c`: check.

Xác minh:

- Unique composite key đúng các cột và thứ tự/semantics.
- FK trỏ bảng/cột đúng.
- CHECK expression đúng nghiệp vụ.
- Constraint có được validate không.
- Deferrability/validation state khi liên quan.
- Rule về NULL có trùng production assumptions không.

**Tên constraint tồn tại không đủ:** cần xem định nghĩa thực. Một UNIQUE trên `order_no` đơn lẻ không tương đương UNIQUE `(tenant_id, order_no)`.

## 17. Kiểm tra indexes

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
      'purchase_orders',
      'order_lines'
  )
ORDER BY tablename, indexname;
```

Với PostgreSQL, `indexdef` cho thấy key order, partial predicate, INCLUDE và unique declaration. Kiểm tra thêm index validity trong catalog khi vừa tạo index concurrent/failed:

```sql
SELECT
    n.nspname,
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisvalid,
    x.indisready
FROM pg_index x
JOIN pg_class i ON i.oid = x.indexrelid
JOIN pg_class t ON t.oid = x.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND t.relname = 'purchase_orders';
```

Một index có tên xuất hiện nhưng `indisvalid = false` không nên được coi là index đã triển khai thành công cho query plans.

## 18. Vì sao constraint/index tồn tại chưa đủ?

Một index có thể:

- Không được optimizer chọn.
- Có predicate không khớp query.
- Có key order sai.
- Bị invalid/đang build.
- Quá rộng và tăng write latency.
- Không cover query columns.
- Không giải quyết N+1 hoặc Cartesian row multiplication.

Một CHECK constraint có thể:

- Chỉ áp trên rows mới, chưa validate existing data theo policy.
- Có expression thiếu trường hợp NULL.
- Không đúng rounding/domain semantics.
- Khác giữa source/target DB khi di trú.

Do đó cần **kiểm thử hành vi thực tế**, không dừng ở catalog.

---

## 19. Xác minh SQL được JPA provider tạo ra

JPQL:

```java
List<PurchaseOrder> page = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenant " +
    "AND o.status = :status " +
    "ORDER BY o.createdAt DESC, o.id DESC",
    PurchaseOrder.class
)
.setParameter("tenant", tenantId)
.setParameter("status", OrderStatus.PAID)
.setMaxResults(20)
.getResultList();
```

Sau khi đổi provider/dialect/driver, generated SQL có thể thay đổi:

- Pagination syntax.
- Join strategy và cột được SELECT.
- Cast/bind types.
- EAGER associations hoặc secondary selects.
- Discriminator/filter predicates.
- Quoting reserved identifiers.
- Optimistic version updates.
- Lock clauses.
- Batch insert/update shape.
- NULL ordering.
- Timestamp/enum representations.

**Không so sánh mỗi JPQL source string**, vì DB thực thi SQL được provider sinh ra.

## 20. Thu SQL như thế nào?

Có thể dùng:

- JDBC datasource-proxy/P6Spy trong test.
- Hibernate SQL logging với bind details được masking.
- OpenTelemetry/APM JDBC spans.
- Database slow query logs.
- PostgreSQL `pg_stat_statements` hoặc equivalent.
- Hibernate Statistics cho số entity loads/fetches/statements.
- Query plan capture từ database.

Khi so sánh trước/sau, ghi:

```text
Use case:
  GET /orders?status=PAID&page=0&size=20

SQL patterns:
  Pattern A: SELECT orders...
  Pattern B: SELECT customers by id...
  Pattern C: COUNT orders...

Per request:
  statement count
  bind parameter types
  SQL durations
  rows/bytes returned
  DB execution plans
  cache state
  latency P50/P95/P99
```

Không bật unmasked bind logs vô thời hạn trên production: có nguy cơ lộ personal data/secrets và tạo logging overhead.

## 21. SQL snapshots nên so sánh theo semantics

Một test “generated SQL phải bằng byte-for-byte cùng string” dễ bị vỡ chỉ vì provider đổi alias/whitespace hoặc dialect format.

Thay vào đó, kiểm tra invariants:

- Predicate tenant hiện diện.
- Soft-delete filter còn đúng.
- ORDER BY có tie-breaker.
- `LIMIT`/pagination áp ở SQL khi cần.
- Không có new unwanted joins.
- SQL count không tăng tuyến tính theo số results.
- Lock mode đúng với operation.
- Bound parameters đúng kiểu.
- Không có cast khiến index không dùng.
- Queries trả dữ liệu đúng.

Có thể lưu normalized SQL fingerprints và diff trong performance regression, nhưng **đừng coi thay đổi alias là lỗi nghiệp vụ**.

## 22. Query correctness phải kiểm tra bằng dữ liệu có chủ ý

Dataset nên có:

- Tenant A và Tenant B với cùng orderNo nếu schema cho phép theo tenant.
- Orders ở nhiều statuses.
- CreatedAt trùng nhau để kiểm tra ordering.
- Giá trị NULL/optional associations.
- Những Order có 0, 1, nhiều Lines.
- Numeric amounts có phần thập phân.
- Ngày sát ranh giới timezone.
- Dữ liệu UTF-8/Unicode, dấu tiếng Việt.
- Soft-deleted and active records.
- Các Customer được nhiều Orders tham chiếu.

Sau hạ tầng thay đổi, không chỉ kiểm tra số rows mà phải biết **những rows được trả** và thứ tự của chúng có đúng với API contract hay không.

## 23. Pagination có thể regress dù SQL vẫn chạy

Các thay đổi thường gây sai pagination:

- Null sort order đổi.
- Collation/sort khác.
- ORDER BY thiếu tie-breaker.
- Deep OFFSET chậm trên DB mới.
- Fetch join to-many kết hợp pagination.
- SQL dialect đổi LIMIT/OFFSET generation.
- JDBC parameter type của `setFirstResult`/`setMaxResults` khác.
- Count query khác fetch query.

Một test mạnh:

1. Seed ít nhất 30 Orders, gồm createdAt trùng.
2. Lấy page size 10 qua 4 pages.
3. Không mất/trùng IDs giữa pages khi dataset cố định.
4. ORDER BY ổn định (ví dụ `createdAt DESC, id DESC`).
5. Tenant/status filter đúng.
6. DB query không đọc toàn bảng khi request chỉ cần 10 rows (kiểm tra plan/rows khi performance-critical).

Một test chỉ assert “list.size()==10” không chứng minh pagination đúng.

## 24. N+1 xuất hiện sau provider upgrade

Một JPA mapping có thể giữ nguyên nhưng SQL count thay đổi theo provider version/fetch plans.

Ví dụ:

```java
List<PurchaseOrder> orders = repository.findRecent(...);

for (PurchaseOrder order : orders) {
    dto.add(new Summary(
        order.getId(),
        order.getCustomer().getDisplayName()
    ));
}
```

Nếu Customer lazy-loaded, 20 Orders với 20 distinct Customers có thể gây 1 + 20 SQL.

Một regression test nên:

- Seed các Orders có Customers khác nhau.
- Đóng seed EntityManager để loại L1 cache.
- Đo cả repository call và DTO mapper/serializer.
- So SQL count khi N=1,10,30.
- Cân nhắc DTO projection hoặc to-one JOIN FETCH/EntityGraph nếu cần.
- Không dùng một index mới để “chữa” bản chất số roundtrips.

## 25. Over-fetch sau thay đổi EntityGraph

Một query trước chỉ tải Orders, sau upgrade config tự tải Lines:

```java
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.status = :status
```

Có thể làm:

- SQL row count tăng vì Order có nhiều Lines.
- JDBC bytes tăng.
- Entity hydration tăng.
- Pagination bị phân trang trong memory.
- Heap/GC xấu đi.
- Nhiều to-many joins dẫn tới Cartesian explosion.

Không kết luận “SQL count giảm còn một là cải thiện”. Cần đo **rows, result width, CPU/heap và P95 end-to-end**.

---

## 26. Execution plan trước/sau thay đổi

PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = 7
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Cần ghi:

- Scan type: Seq Scan, Index Scan, Index Only Scan, Bitmap Heap Scan.
- Index Cond và Filter.
- Estimated rows vs actual rows.
- Rows removed by filter.
- Planning/execution time.
- Sort method, memory/disk spill.
- Buffers hit/read.
- Join algorithms, loops.
- Heap fetches.
- Parallel workers.
- Tác động data skew/parameter values.

`EXPLAIN ANALYZE` trên PostgreSQL **thực sự thực thi statement**. Không chạy tùy tiện với UPDATE/DELETE/INSERT trên production. Với SELECT trên bảng lớn cũng cần giới hạn tải và dùng chính sách diagnostic đã phê duyệt.

## 27. Index hiện hữu không có nghĩa planner sẽ dùng

Giả sử:

```sql
CREATE INDEX idx_orders_tenant_status_date
ON purchase_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
```

Nếu query còn:

```sql
WHERE DATE(created_at) = :day
```

thì index trên timestamp gốc có thể kém hữu ích hơn query range:

```sql
WHERE created_at >= :start
  AND created_at < :end
```

Hoặc nếu 90% rows mang status PAID, planner có thể chọn scan.

Xác minh dựa trên **actual plan, distribution và timing**, không ép index name. Index Scan đọc hàng triệu entries vẫn có thể chậm.

## 28. Thống kê optimizer sau import/backfill

Sau khi import hàng triệu rows, thống kê cũ có thể không phản ánh:

- Tỷ lệ status.
- Tenant sizes.
- Customer cardinality.
- Phân bố created_at.
- Mức độ NULL.
- Tương quan các cột.
- Kích thước bảng/index.

Nếu PostgreSQL estimates sai lệch lớn, có thể cần đảm bảo autovacuum/analyze hoặc chạy `ANALYZE` theo vận hành được phê duyệt:

```sql
ANALYZE purchase_orders;
```

`ANALYZE` là thao tác cập nhật planner statistics, không sửa data nghiệp vụ, nhưng có tải/ảnh hưởng planning và cần chính sách vận hành. Sau đó đo lại actual plan. Không mặc định mọi performance regression sau upgrade đều giải quyết bằng `ANALYZE`; còn cần xem indexes, SQL shape, locks và driver changes.

## 29. Parameterized SQL và plan caching

Hai tenants:

```text
Tenant A: 100 Orders
Tenant B: 8,000,000 Orders
```

Cùng JPQL nhưng bind parameter khác có thể tạo plans khác. JDBC prepared statements và database có cơ chế generic/custom plans hoặc parameter sniffing tùy engine.

Để xác minh:

- Test tenant nhỏ, vừa, lớn.
- Test status phổ biến và hiếm.
- Test date ranges hẹp/rộng.
- Kiểm tra JDBC driver/server-side prepare settings nếu thay đổi.
- Đo kế hoạch thực tế thay vì nối params trực tiếp vào SQL.

**Không bỏ parameter binding để “cứu planner” bằng SQL concatenation**, vì tạo injection risk và mất plan cache stability.

---

## 30. Data reconciliation là gì?

Sau migration/cutover, cần chứng minh **dữ liệu quan trọng tương đương theo một contract có thể kiểm tra**, không chỉ “source có 2 triệu rows, target cũng có 2 triệu rows”.

Các nhóm kiểm tra:

1. Row counts theo bảng.
2. Counts theo tenant/status/date.
3. Distinct business keys, duplicates và NULLs.
4. Referential integrity/orphans.
5. Aggregates: SUM/COUNT/MIN/MAX.
6. Field-level sample comparison.
7. Deterministic hashes/checksums của nội dung chuẩn hóa.
8. Record-level source-vs-target differences.
9. Sequence/identity next values.
10. Số lượng changes trong CDC backlog nếu có.
11. Timestamp/currency/enum/JSON/Unicode semantics.
12. Late-arriving writes trong quá trình snapshot/cutover.

Mỗi phép có giới hạn, vì vậy nên dùng **nhiều phép độc lập**.

## 31. Baseline phải được đo tại một thời điểm nhất quán

Nếu source database tiếp tục nhận writes trong khi target được import, việc so sánh counts “ngay lúc này” có thể khác nhau hợp lệ vì:

- Snapshot khác thời điểm.
- CDC chưa apply hết.
- In-flight transactions.
- Background jobs đang cập nhật.
- Read replica lag.
- Bảng được backfill theo chunks.

Một reconciliation đáng tin cần một **watermark**:

```text
Snapshot source at LSN/transaction position W
           │
           ▼
Copy all data covered by W
           │
           ▼
Apply CDC changes through W2
           │
           ▼
Pause/fence writes or ensure catch-up to W2
           │
           ▼
Compare source and target at consistent boundary
```

Cách lấy LSN/replication position cụ thể phụ thuộc replication technology. Không bịa ra một “timestamp cutover” rồi coi mọi late writes đã được bao phủ. Nếu dùng timestamp, phải chứng minh nó phản ánh order/coverage của writes theo hệ thống thực.

## 32. Row counts tổng chỉ là bước đầu

```sql
SELECT COUNT(*) AS order_count
FROM purchase_orders;
```

Counts có thể bằng nhau dù:

- Mất 1 row và trùng 1 row.
- Giá trị của 1000 rows bị sai.
- Tenant_id bị remap nhầm.
- created_at lệch timezone.
- Total amount bị làm tròn.
- OrderLine mất liên kết.
- Dữ liệu bên ngoài snapshot watermark.

Đừng tuyên bố migration data success chỉ vì `COUNT(*)` khớp.

## 33. Đếm theo tenant/status và ngày

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count
FROM purchase_orders
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Theo ngày nghiệp vụ (ví dụ xử lý timezone phải được định nghĩa rõ):

```sql
SELECT
    tenant_id,
    (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS business_day,
    COUNT(*) AS order_count
FROM purchase_orders
GROUP BY
    tenant_id,
    (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY tenant_id, business_day;
```

Cú pháp trên là PostgreSQL-specific. Nếu source/target có timezone conversion khác, so sánh bằng cùng quy tắc canonicalization hoặc chuyển về UTC instants trước.

**Counts theo chiều nghiệp vụ giúp phát hiện khác biệt mà total count che giấu.**

## 34. Tổng tiền phải so sánh bằng decimal, không dùng float bừa bãi

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    COALESCE(SUM(total_amount), 0) AS total_amount_sum
FROM purchase_orders
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Với `NUMERIC(14,2)`, database dùng decimal arithmetic theo semantics của nó, phù hợp tiền tệ hơn so với việc chuyển `DOUBLE PRECISION` rồi so sánh xấp xỉ.

Khi so sánh Java:

```java
BigDecimal expected = new BigDecimal("12345.67");
BigDecimal actual = ...;

assertEquals(0, expected.compareTo(actual));
```

Nếu nghiệp vụ yêu cầu scale cố định và currency riêng, còn cần kiểm tra scale/rounding/currency code. Hai tổng bằng nhau **không chứng minh từng Order đúng**: sai +100 ở A và -100 ở B có thể triệt tiêu. Cần thêm row-level comparisons.

## 35. Kiểm tra duplicate business keys

Ví dụ UNIQUE scope theo tenant:

```sql
SELECT
    tenant_id,
    order_no,
    COUNT(*) AS duplicates
FROM purchase_orders
GROUP BY tenant_id, order_no
HAVING COUNT(*) > 1;
```

Expected result: **không có rows** nếu business contract cấm duplicates.

Không chỉ tin rằng constraint có tên tồn tại: target import đôi khi chạy trên staging table chưa có constraint, hoặc migration tạo unique sau backfill nhưng thất bại/không validate.

Đối với dữ liệu lớn, query này có thể tiêu tốn tài nguyên; chạy trên replica/snapshot/staging hoặc theo lịch có kiểm soát.

## 36. Kiểm tra các giá trị NULL không hợp lệ

```sql
SELECT COUNT(*) AS invalid_count
FROM purchase_orders
WHERE tenant_id IS NULL
   OR order_no IS NULL
   OR status IS NULL
   OR total_amount IS NULL
   OR version IS NULL;
```

Trong expand–contract, một cột mới có thể tạm nullable; lúc đó ngưỡng hợp lệ theo phase:

```text
Expand phase:
  NULL fulfillment_state có thể tồn tại với old rows

Before contract phase:
  NULL fulfillment_state phải bằng 0

After contract phase:
  column NOT NULL + targeted behavior test
```

Không deploy `ALTER COLUMN ... SET NOT NULL` trước khi backfill và xác minh all rows nếu việc đó làm migration fail/lock lâu. Với bảng lớn, cần đánh giá thủ tục constraint validation theo engine.

## 37. Kiểm tra orphan foreign keys

Ví dụ OrderLine tham chiếu một Order không tồn tại:

```sql
SELECT
    l.id,
    l.order_id
FROM order_lines l
LEFT JOIN purchase_orders o
    ON o.id = l.order_id
WHERE o.id IS NULL;
```

Expected result: không có rows.

Một FK đã tạo và validated thường bảo vệ các writes mới, nhưng reconciliation vẫn hữu ích khi:

- Dữ liệu được import khi tạm vô hiệu constraints.
- Có staging tables chưa enforce FK.
- Legacy data không clean.
- Constraints được tạo NOT VALID.
- Referential integrity check chưa hoàn tất.

Đừng tắt FK trên target để import cho nhanh mà không có phase kiểm tra/validate lại.

## 38. So sánh source-vs-target bằng business key

Nếu source/target có stable IDs:

```text
Source Orders keyed by (tenant_id, order_no)
Target Orders keyed by (tenant_id, order_no)
```

Có thể xuất một manifest chỉ gồm:

```text
tenant_id | order_no | status | created_at_utc | total_amount
```

Sau đó so:

- Keys thiếu ở target.
- Keys dư ở target ngoài phạm vi snapshot.
- Duplicate keys.
- Khác field values.
- Khác timestamps.
- Khác numbers/rounding.
- Khác JSON normalization.

Nếu source/target không cùng database hoặc IDs được remap, **đừng join theo ID vật lý một cách mù quáng**; dùng stable business key hoặc mapping table được kiểm chứng.

Khi DB có thể query cả hai snapshots qua một môi trường được phê duyệt, một full outer join comparison sẽ dễ dùng, nhưng với hai hệ thống ở hai mạng cần export/chunk/ETL reconciliation an toàn.

## 39. Row-level mismatch query trong staging

Giả sử đã import source/target vào hai bảng reconciliation trong một **database test**:

```sql
SELECT
    COALESCE(s.tenant_id, t.tenant_id) AS tenant_id,
    COALESCE(s.order_no, t.order_no) AS order_no,
    s.status AS source_status,
    t.status AS target_status,
    s.total_amount AS source_amount,
    t.total_amount AS target_amount
FROM source_orders_snapshot s
FULL OUTER JOIN target_orders_snapshot t
    ON t.tenant_id = s.tenant_id
   AND t.order_no = s.order_no
WHERE s.order_no IS NULL
   OR t.order_no IS NULL
   OR s.status IS DISTINCT FROM t.status
   OR s.total_amount IS DISTINCT FROM t.total_amount;
```

`IS DISTINCT FROM` cho phép so sánh null-safe trên PostgreSQL. Câu SQL này chỉ minh họa khi **hai snapshot cùng ở một staging DB**; không tự động chạy cross-environment connection.

Nếu source/target có duplicate keys, FULL JOIN có thể nhân rows và gây kết luận sai. Phải kiểm tra uniqueness trước.

## 40. Dùng checksum/hash đúng cách

Checksum hữu ích khi có hàng triệu rows, nhưng phải định nghĩa rõ normalization:

- Chọn những fields nào.
- Thứ tự rows theo key duy nhất.
- Thứ tự fields.
- NULL representation.
- Ký tự phân cách/escaping.
- Encoding UTF-8.
- Unicode normalization.
- Timestamp format/timezone.
- Numeric scale/currency.
- JSON canonicalization.
- Hash algorithm và chunk boundaries.

Ví dụ logic:

```text
For each tenant and key range:
   canonicalize rows
   sort by stable key
   serialize with unambiguous encoding
   compute SHA-256 per row or chunk
   compare source/target digests
   drill down mismatched chunks
```

Không dùng `string_agg` toàn bảng khổng lồ mà không xét memory/time. Không dùng `SUM(hash(row))` đơn giản để suy tất cả rows bằng nhau: collisions và cancellation có thể che lỗi. Hash chỉ là **một tín hiệu**, không thay targeted field comparisons.

Một SHA-256 chunk checksum tốt cần canonicalization **giống nhau ở cả hai phía**, nếu không có thể báo lệch dù giá trị nghiệp vụ tương đương.

## 41. Sample checks không thay full reconciliation

Lấy ngẫu nhiên 100 Orders có thể bỏ sót 10 lỗi trong 10 triệu rows. Nên kết hợp:

- Full row-key coverage hoặc full chunk digests cho critical tables.
- Aggregates per tenant/status/day.
- Stratified samples: nhiều tenants, statuses, null/non-null, edge dates.
- Random samples có deterministic seed.
- Targeted edge cases: Unicode, long strings, max numeric precision.
- Verification after CDC catch-up.

Sampling là chiến lược giảm chi phí, không phải cam kết 100% correctness nếu không có coverage bảo đảm.

---

## 42. Sequence/identity sau import

Một lỗi điển hình khi copy rows với IDs đã gán:

```text
MAX(id) trong table = 2,000,000
Sequence nextval tiếp theo = 1,500
INSERT mới → duplicate primary key
```

Phải xác minh generated ID mechanism theo engine và migration tool. Với PostgreSQL, identity/sequence có thể liên kết column hoặc quản lý riêng; truy vấn tìm sequence liên quan:

```sql
SELECT pg_get_serial_sequence(
    'public.purchase_orders',
    'id'
);
```

Nếu trả NULL, column có thể dùng assigned IDs hoặc sequence không được liên kết theo cách hàm nhận diện. Không tự gọi `setval` trên production chỉ từ max ID khi các writers đang hoạt động; có race và sequence ownership/identity semantics cần xem xét.

Quy trình an toàn thường là:

1. Xác định sequence/identity thật.
2. Quiesce writes hoặc bảo đảm coordinated cutover.
3. So max ID trên target và sequence state.
4. Cập nhật sequence theo cách đúng với DB, role và concurrency.
5. Thực hiện một insert smoke test trong môi trường/cửa sổ được phép.
6. Xác minh rollback/cleanup dữ liệu test mà không làm sai counter.

Sequence gaps sau rollback **không phải lỗi**; điều quan trọng là không tái cấp key đang tồn tại.

## 43. Timezone và timestamp: một lỗi có thể phá báo cáo

Các câu hỏi:

- DB source lưu `timestamp without time zone` hay `timestamptz`?
- Data source có quy ước UTC hay local?
- JDBC driver dùng timezone nào khi bind/mapping?
- JPA mapping dùng `Instant`, `OffsetDateTime` hay `LocalDateTime`?
- App/DB session timezone có thay đổi?
- Day boundaries theo timezone nghiệp vụ nào?
- Index/filter có dùng `DATE(created_at)` làm thay semantics?
- DST của các vùng khác có cần xử lý?

Một test tốt seed:

```text
2026-11-14T16:59:59Z
2026-11-14T17:00:00Z
2026-11-15T16:59:59Z
2026-11-15T17:00:00Z
```

Với ngày 2026-11-15 ở `Asia/Ho_Chi_Minh` (UTC+7), khoảng ngày nghiệp vụ là từ `2026-11-14T17:00:00Z` tới trước `2026-11-15T17:00:00Z`. Test boundaries giúp phát hiện lỗi dùng timezone mặc định của server/JVM. Đối với zone có DST, tính hai midnight local qua ZoneId thay vì cộng cố định 24 giờ một cách máy móc.

## 44. Decimal và enum mappings

Các rủi ro khi di trú:

- `DECIMAL/NUMERIC` thành floating point.
- Scale/precision bị thu hẹp.
- Rounding mode khác.
- Hibernate enum `ORDINAL` được chuyển sang `STRING` không có data migration đúng.
- Enum value mới chưa được hỗ trợ bởi code cũ khi rolling deploy.
- DB CHECK allowed statuses chưa cập nhật.
- NULL/default semantics khác.

Kiểm chứng:

```sql
SELECT
    status,
    COUNT(*) AS count,
    COALESCE(SUM(total_amount), 0) AS amount
FROM purchase_orders
GROUP BY status
ORDER BY status;
```

Trong Java, dùng `BigDecimal` cho tiền tệ và test numeric values chính xác theo business contract. **Không đổi enum storage strategy chỉ bằng annotation** khi rows cũ còn dùng biểu diễn khác.

## 45. Collation, case sensitivity và Unicode

Đổi DB có thể thay:

- Thứ tự `ORDER BY name`.
- Case-sensitive/insensitive equality.
- Unique index behavior.
- `LOWER(...)`/`LIKE` matching.
- Accent handling.
- Unicode normalization.
- Locale-dependent comparisons.

Test những giá trị đại diện:

```text
An
an
Án
Ân
Đà Nẵng
đa năng
é
e + combining acute
```

Không tự cho rằng `LOWER` hoặc collation mới tương đương chính xác với quy tắc nghiệp vụ. Nếu dùng email/username normalized keys, định nghĩa canonicalization rõ, migrate data và kiểm chứng uniqueness. Với text search, index expression/operator class có thể khác theo DB.

---

## 46. Kiểm tra transaction commit/rollback sau nâng cấp

Một database mới vẫn cần bảo đảm nguyên tử của một use case.

Test tối thiểu:

```text
Test A:
   begin
   INSERT Order + two Lines
   commit
   read using new EntityManager
   expect all committed

Test B:
   begin
   INSERT Order + first Line
   throw exception
   rollback
   read using new EntityManager
   expect none of those new rows

Test C:
   begin
   UPDATE existing Order
   flush
   rollback
   fresh read returns old value
```

Đừng chỉ `save()` rồi `findById()` trong cùng EntityManager, vì L1 identity map có thể trả Java object chưa committed.

### JPA transaction example

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();
    em.persist(order);
    em.flush();
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
} finally {
    em.close();
}
```

Ví dụ dùng RESOURCE_LOCAL. Với Spring/JTA, transaction manager sở hữu commit/rollback; không gọi `em.getTransaction()` trên managed context trái contract.

## 47. Đọc lại bằng EntityManager mới

Sau commit:

```java
EntityManager reader = emf.createEntityManager();
try {
    PurchaseOrder persisted = reader.find(
        PurchaseOrder.class,
        orderId
    );
    assertNotNull(persisted);
} finally {
    reader.close();
}
```

Nếu test có L2 cache, một EntityManager mới không luôn đảm bảo query thẳng database; khi mục tiêu là xác minh DB committed row thật, cân nhắc JDBC readback hoặc kiểm soát cache trong môi trường cô lập.

Chỉ số `entity.getId() != null` **không chứng minh commit thành công**, đặc biệt với generated IDs được cấp trước transaction completion.

## 48. Test UNIQUE/FK/CHECK sau migration

Để xác minh database thật sự bảo vệ data:

- Insert hai Orders có cùng `tenant_id, order_no` → phải reject duplicate.
- Insert OrderLine với nonexistent order_id → phải reject FK.
- Insert OrderLine quantity=0 → phải reject CHECK.
- Insert Order total_amount âm → phải reject CHECK.
- Insert cùng order_no ở **hai tenants khác nhau** → phải hợp lệ nếu rule là unique theo tenant.

Nếu Bean Validation ở Java chặn trước SQL, phép thử đó chưa chứng minh DB constraint; dùng JDBC/native SQL trong test cô lập khi cần.

PostgreSQL SQLStates thường gặp:

| SQLState | Ý nghĩa |
| --- | --- |
| `23505` | unique_violation |
| `23503` | foreign_key_violation |
| `23514` | check_violation |
| `23502` | not_null_violation |

Phân loại cause/SQLState cụ thể thay vì chỉ `assertThrows(RuntimeException.class)`, vì một connection failure cũng tạo exception nhưng không chứng minh constraint đúng.

## 49. Optimistic locking và version correctness

Nếu entity có `@Version`:

```text
EM A reads Order version 5
EM B reads Order version 5
A updates, commits → version 6
B updates stale entity → OptimisticLockException/rollback
```

Test bằng **hai EntityManagers và transactions độc lập**, không dùng chung EntityManager giữa threads. Sau failure, đọc fresh context xác minh committed winner không bị ghi đè.

Các điểm cần kiểm tra sau provider/driver/schema upgrade:

- Version column type đúng.
- ORM update có điều kiện version.
- A commit làm version tăng theo contract.
- B stale update bị từ chối.
- Exception có thể xuất hiện ở flush hoặc commit và được bọc khác nhau.
- Bulk JPQL/native UPDATE không tự có same optimistic version behavior như managed dirty checking.

Một schema vẫn có cột version nhưng provider config/mapping sai có thể tạo lost update; cần test hành vi, không chỉ introspect cột.

## 50. Locking và isolation sau failover/migration

Một số use cases dùng:

```java
em.find(
    PurchaseOrder.class,
    orderId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Cần kiểm tra:

- Lock SQL/clauses thực tế.
- Transaction active.
- Lock timeout behavior.
- Deadlock detection/retry.
- Row-level vs table-level contention.
- Transaction isolation setting.
- Pool/proxy có giữ session/transaction state đúng không.
- Read replica có cho lock writes không.
- Lock release sau commit/rollback.

Không viết test với `Thread.sleep()` rồi coi thứ tự concurrency luôn được bảo đảm. Dùng `CountDownLatch`/barriers và hai connections độc lập khi cần kiểm tra blocking behavior.

## 51. Read replica và read-after-write consistency

Giả sử:

```text
Write → Primary commit
              │
              └── Replication async → Replica
                                     │
                              Read API (replica)
```

Read API có thể không thấy row vừa commit vì replica lag. Đây không nhất thiết là JPA commit bug.

Cần định nghĩa:

- Endpoint nào cần read-your-writes?
- Có route read-critical requests tới primary không?
- Có consistency token/LSN wait mechanism không?
- Replica lag SLO là gì?
- Failover promotion có mất writes được acknowledged không theo replication mode?
- Connection pools sau failover có nối đúng primary mới không?
- Cache invalidation có theo kịp hay không?

Một integration test “commit xong đọc replica ngay phải thấy” là flaky nếu kiến trúc chỉ cam kết eventual consistency. Test phải phản ánh consistency contract đã chọn.

---

## 52. Xác minh pool/proxy khi đổi database

HikariCP/PgBouncer/proxy hoặc managed connection pool có thể làm thay đổi:

- Max active connections.
- Connection acquisition latency.
- Session reset behavior.
- Autocommit.
- Isolation level.
- Read-only flag.
- Prepared statement handling.
- Temporary tables/session variables.
- Server-side cursors.
- Search path.
- Lock/statement timeout.
- TLS negotiation.

Một test `SELECT 1` dùng một connection không phát hiện được pool saturation và session-state leakage.

Metrics nên có:

```text
pool_active
pool_idle
pool_pending
connection_acquire_p95
connection_timeout_count
database_active_sessions
transaction_duration_p95
lock_wait_duration
prepared_statement_errors
```

Không tăng pool size vô hạn để “giải quyết” SQL chậm hoặc contention; pool lớn hơn có thể đẩy bottleneck xuống database.

## 53. Transaction pooling có thể phá giả định session state

Nếu chuyển sang một proxy có transaction pooling (ví dụ mode phù hợp của PgBouncer), application không nên mặc định session-local settings, temporary tables hoặc prepared statement lifecycle luôn bền qua transaction theo cùng cách với direct session pooling.

Các vấn đề có thể gặp:

- `SET search_path` cho session không theo connection ứng dụng như kỳ vọng.
- Server-side prepared statements cần compatibility settings.
- Advisory locks/session features không an toàn nếu connection vật lý thay đổi.
- Temporary tables/session variables khác.
- Cursor/streaming cần đúng lifecycle.

Phải kiểm thử những feature có sử dụng, kiểm tra proxy version/config, không đưa một cấu hình proxy vào production chỉ vì simple JPQL SELECT chạy được.

## 54. TLS và permission smoke tests

Sau credential rotation hay cloud migration:

- TLS certificate chain/hostname validation đúng.
- Application role có đúng quyền SELECT/INSERT/UPDATE/DELETE cần.
- Không có superuser privilege vô cớ.
- Migration user và runtime app user có roles khác nhau.
- Default schema/search_path/grants đúng.
- Audit logging có chạy.
- Không log passwords.
- Không để health diagnostics công khai DB details.

Một role có quyền đọc nhưng không INSERT có thể khiến read-only health check xanh và write API lỗi. Cần **read/write smoke tests** trên target an toàn và có cleanup, tránh test destructive trên dữ liệu production thật.

---

## 55. Runbook tổng quát cho một migration

### Giai đoạn A — Trước thay đổi

1. Xác định change contract và affected services.
2. Chụp baseline SQL patterns, latency, error rates.
3. Export schema metadata và Flyway history.
4. Kiểm tra DB backup/restore thực tế, không chỉ thấy backup job success.
5. Chuẩn bị dữ liệu reconciliation baseline.
6. Xác định business keys và cutover watermark.
7. Kiểm tra versions driver/provider/DB compatibility.
8. Chạy migrations trên disposable production-like DB.
9. Tập dượt trên staging với workload gần production.
10. Gắn owner/go-no-go/rollback thresholds.

### Giai đoạn B — Trong thay đổi

1. Áp expand migration trước code đòi schema mới.
2. Theo dõi locks/connection errors.
3. Backfill theo chunks có checkpoint.
4. Kiểm tra counts/aggregates/chunk digests theo tiến độ.
5. Bảo đảm CDC/dual-write coverage nếu có.
6. Đợi lag đạt ngưỡng hợp đồng.
7. Cutover writers có fencing rõ.
8. Rollout app instances có controlled ramp.
9. Thu SQL/plan metrics sau từng bước.
10. Dừng hoặc revert/forward-fix theo trigger đã định.

### Giai đoạn C — Sau thay đổi

1. Xác minh app instances dùng đúng target.
2. Flyway validate + schema/catalog checks.
3. Đối soát dữ liệu ở cutover watermark.
4. Run JPA smoke/integration operations.
5. Kiểm tra tenant isolation và integrity negative cases.
6. Kiểm tra SQL fingerprints/count/plan của hot paths.
7. So sánh P95/P99/throughput/DB resource.
8. Theo dõi replication/cache lag.
9. Giữ compatibility code đến khi old version hết chạy.
10. Sau observation window, mới contract cleanup theo policy.

Các bước này là **runbook mẫu**, cần tùy biến theo database topology, SLO, data volume và mức độ an toàn của môi trường.

## 56. Một thay đổi an toàn thường cần hai chiều tương thích

Trong rolling deployment, có thể tồn tại đồng thời:

```text
App v1 ↔ Schema v2
App v2 ↔ Schema v2
```

Nếu schema v2 đổi tên cột và drop cột v1 trước khi app v1 biến mất, traffic vào app cũ sẽ fail.

Dùng expand–contract:

```text
1. ADD new_column nullable / new table
2. Deploy code đọc cả cũ/mới hoặc fallback an toàn
3. Start writing new representation
4. Backfill old rows
5. Verify consistency
6. Route all traffic to new code
7. Disable old writers
8. Enforce constraints / drop legacy column later
```

Có thể có dual-write trong giai đoạn chuyển, nhưng dual-write không tự đảm bảo atomic consistency nếu hai destinations khác transactional boundary; cần CDC, outbox, idempotency hoặc reconciliation policy rõ.

## 57. Ví dụ migration expand: thêm column nullable

PostgreSQL/Flyway migration minh họa:

```sql
ALTER TABLE purchase_orders
ADD COLUMN fulfillment_state VARCHAR(30);
```

Đây là bước **expand**, chưa ép NOT NULL.

Code phiên bản mới có thể đọc null như một giá trị “chưa migrated”, nhưng cần document fallback semantics. Không thể tự gán null thành `FULFILLED` chỉ để tránh lỗi nếu dữ liệu lịch sử có trạng thái khác.

## 58. Backfill theo chunk thay vì UPDATE toàn bảng

Một ví dụ khái niệm:

```sql
UPDATE purchase_orders
SET fulfillment_state = CASE
    WHEN status = 'SHIPPED' THEN 'FULFILLED'
    WHEN status = 'CANCELLED' THEN 'CANCELLED'
    ELSE 'PENDING'
END
WHERE fulfillment_state IS NULL
  AND id >= :from_id
  AND id < :to_id;
```

Chạy với ranges bounded, checkpoint theo IDs/keys và transaction boundaries hợp lý.

Các điều kiện:

- Mapping theo domain rule phải được kiểm chứng.
- Workload concurrent writes có thể thay status trong lúc backfill.
- Dùng điều kiện `WHERE fulfillment_state IS NULL` giúp rerun có kiểm soát, nhưng chưa chứng minh mapping luôn đúng nếu source status đổi.
- Ghi log counts by batch, failed batches, retry count.
- Đặt giới hạn lock/transaction duration.
- Không quên tombstone/deleted/archived rows nếu chúng nằm trong scope.
- Test ở data skew/large tenants.

Một backfill idempotent không có nghĩa nó tự bảo đảm consistency dưới concurrent writes. Cần thiết kế sequencing, CDC hoặc write compatibility.

## 59. Xác minh trước contract

Trước khi thêm NOT NULL:

```sql
SELECT COUNT(*) AS missing
FROM purchase_orders
WHERE fulfillment_state IS NULL;
```

Các checks khác:

```sql
SELECT
    status,
    fulfillment_state,
    COUNT(*) AS row_count
FROM purchase_orders
GROUP BY status, fulfillment_state
ORDER BY status, fulfillment_state;
```

Nếu mapping rule yêu cầu:

```text
status SHIPPED → FULFILLED
status CANCELLED → CANCELLED
others → PENDING
```

cần kiểm tra các mismatches:

```sql
SELECT COUNT(*) AS mismatches
FROM purchase_orders
WHERE fulfillment_state IS DISTINCT FROM
    CASE
        WHEN status = 'SHIPPED' THEN 'FULFILLED'
        WHEN status = 'CANCELLED' THEN 'CANCELLED'
        ELSE 'PENDING'
    END;
```

Câu này là PostgreSQL-specific `IS DISTINCT FROM`. Trong thực tế, business rules có thể phức tạp hơn và trạng thái mới không được suy thuần từ status; khi đó phải dùng bảng mapping/business event history.

## 60. Contract migration chỉ sau khi đạt điều kiện

Sau khi old writers không còn và checks pass:

```sql
ALTER TABLE purchase_orders
ALTER COLUMN fulfillment_state SET NOT NULL;
```

Với bảng lớn, bước này có thể cần scan/lock đáng kể, tùy version/constraints/engine. Không triển khai bất chấp SLO. Một số engine có cách thêm/validate constraints từng giai đoạn, tạo index concurrent, hoặc metadata-only operations trong các trường hợp cụ thể; cần tìm đúng chiến lược cho DB/version thật.

Sau contract, test:

- Schema column NOT NULL.
- API old versions không còn dùng cột cũ.
- New inserts luôn có fulfillment_state.
- Data mismatch/null counts bằng 0.
- Migration history đúng.
- No unexpected locks/errors.
- Rollback policy đã chuyển từ revert schema sang forward fix nếu thao tác mất tính đảo ngược.

---

## 61. Rollback code không đồng nghĩa rollback dữ liệu

Một sai lầm phổ biến:

```text
Deploy App v2
Run migration V13 + backfill
Observe issue
Redeploy App v1
Assume system completely rolled back
```

Nếu migration đã:

- Drop/rename column.
- Chuyển đổi kiểu không đảo ngược.
- Backfill/transformed values.
- Ghi event data mới.
- Tạo rows mà v1 không hiểu.
- Gọi external services.
- Chuyển primary cutover.

thì revert application binary **không tự khôi phục dữ liệu/schema**.

Mỗi phase cần biết:

- Có thể rollback code không?
- Schema còn backward-compatible không?
- Data có cần restore hay forward fix không?
- Có snapshot/backup đủ mới không?
- Có cần fence writes trước restore không?
- Loss window/RPO chấp nhận là gì?
- Có data writes mới không thể merge ngược không?

**Không hứa “rollback trong một lệnh” khi state đã chuyển đổi không thể đảo ngược.**

## 62. Forward-fix thường hợp lý hơn schema rollback sau data migration

Một khi production đã ghi dữ liệu theo schema mới, nhiều hệ thống chọn **forward-fix**:

- Tạm dừng feature flag.
- Roll out hotfix tương thích schema hiện tại.
- Chạy correction migration có kiểm soát.
- Reconcile mismatched rows.
- Tiếp tục quan sát.

Nhưng không phải lúc nào cũng đúng. Với corruption diện rộng, restore từ backup hoặc failback có thể cần thiết; phải cân nhắc data loss window và khả năng reconcile writes mới. Runbook phải đưa ra decision criteria thay vì một lựa chọn mặc định tuyệt đối.

## 63. Cutover writes cần ownership/fencing

Nếu old và new DB đều nhận ghi trong thời gian chuyển:

```text
Writer A → Old DB
Writer B → New DB
```

có thể tạo divergent versions.

Một cutover có thể cần:

1. Chọn một writer owner duy nhất.
2. Chặn writes ở old DB hoặc thay routing được kiểm soát.
3. Đợi transactions in-flight hoàn tất.
4. Đồng bộ/verify CDC tới watermark.
5. Chuyển writer endpoint.
6. Thực hiện write smoke test có idempotency.
7. Theo dõi old DB xem còn writes ngoài ý định không.
8. Ghi nhận cutover ID/time/LSN/version.
9. Nếu failback, biết dữ liệu mới tạo sau cutover sẽ được chuyển lại ra sao.

Không trông chờ config của app “thường đúng” nếu một old worker/cron vẫn còn connection có quyền ghi.

---

## 64. Observability sau triển khai

Một dashboard tối thiểu cho JPA/database:

| Metric | Câu hỏi |
| --- | --- |
| HTTP P50/P95/P99 | Người dùng có chậm hơn không? |
| API error/5xx/4xx conflict | Tỷ lệ lỗi có tăng không? |
| JDBC query count/request | Có N+1 hoặc extra query không? |
| Slow SQL patterns | SQL nào góp phần latency? |
| DB CPU/IO/buffers | Database có chịu tải hơn không? |
| Connection pool active/pending | Có chờ connection không? |
| Transaction duration | Có transaction mới quá dài không? |
| Lock wait/deadlocks | Có contention không? |
| Replica lag | Data consistency có bị trễ không? |
| CDC backlog/last offset | Target có catch up không? |
| Cache hit/miss | Có stale/cache storm không? |
| GC/allocations | ORM hydration có tăng không? |
| Migration/backfill progress | Có batches stuck/fail không? |
| Reconciliation mismatch count | Data correctness có đúng không? |

Định nghĩa thresholds theo baseline/SLO thực; không tự áp một ngưỡng tuyệt đối như “mọi SQL phải dưới 10ms”.

## 65. So sánh performance công bằng

Một benchmark đáng tin:

1. Dataset và distributions đủ gần production.
2. Same queries và bind values.
3. Same functional result.
4. Cùng mức concurrency.
5. Cache cold/warm state được ghi nhận.
6. Connection pool và driver versions rõ.
7. JIT warm-up nếu benchmark Java.
8. DB statistics cập nhật tương đương.
9. Logging overhead tương đương.
10. Multiple runs, không chỉ một lần.
11. P95/P99, throughput và CPU/IO/heap cùng được xem.
12. Lock contention và background jobs được ghi nhận.

Một query có P50 tốt hơn nhưng P99 xấu đi khi replica lag hoặc lock waits tăng vẫn có thể là regression nghiêm trọng.

## 66. Chia release bằng canary hoặc progressive rollout

Một phương án:

```text
Migration expand
      │
      ▼
1% app instances / traffic
      │ compare SQL/data/latency/error
      ▼
10%
      │ compare
      ▼
50%
      │ compare
      ▼
100%
      │ observe
      ▼
Contract migration ở release sau
```

Cần nhớ: **canary ứng dụng không canary được một schema migration toàn cục** nếu schema đã áp trên database chung. Vì vậy expand changes phải backward-compatible với app cũ trước khi bắt đầu canary.

Khi canary đọc/ghi vào DB chung, không được làm một user được xử lý bằng hai schema semantics không tương thích. Feature flags và dual-read strategies cần tính toán consistency.

---

## 67. JPA integration test trên PostgreSQL thật

Có thể dùng JUnit 5 và Testcontainers để kiểm tra migrations, ORM mappings và SQL behavior.

Test setup:

```java
@Testcontainers
class OrderInfrastructureMigrationIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    private static EntityManagerFactory emf;

    @BeforeAll
    static void setup() {
        Flyway.configure()
            .dataSource(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword()
            )
            .locations("classpath:db/migration")
            .load()
            .migrate();

        Map<String, Object> overrides = Map.of(
            "jakarta.persistence.jdbc.url",
            postgres.getJdbcUrl(),
            "jakarta.persistence.jdbc.user",
            postgres.getUsername(),
            "jakarta.persistence.jdbc.password",
            postgres.getPassword(),
            "jakarta.persistence.jdbc.driver",
            "org.postgresql.Driver",
            "hibernate.hbm2ddl.auto",
            "validate"
        );

        emf = Persistence.createEntityManagerFactory(
            "orders-test",
            overrides
        );
    }

    @AfterAll
    static void cleanup() {
        if (emf != null) {
            emf.close();
        }
    }
}
```

Đây là skeleton: cần test `persistence.xml` với unit `orders-test` và các entity classes, production migrations trên classpath, dependencies tương thích. Cần mở/đóng EntityManagers riêng cho từng test/transaction. Không chạy Gradle hay Docker ở phần viết bài; đây là ví dụ để người học triển khai.

## 68. Test data sau migration bằng SQL/JDBC

Ví dụ skeleton helper:

```java
static long countRows(
        DataSource ds,
        String sql) throws SQLException {

    try (Connection connection = ds.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql);
         ResultSet rows = statement.executeQuery()) {

        if (!rows.next()) {
            throw new IllegalStateException(
                "COUNT query returned no row"
            );
        }
        return rows.getLong(1);
    }
}
```

Chỉ dùng SQL string cố định được code sở hữu, không nhận raw SQL input từ người dùng. Đối với parameterized business queries, dùng `PreparedStatement` và bind parameters.

Một test:

```java
assertEquals(
    expectedCount,
    countRows(ds,
        "SELECT COUNT(*) FROM purchase_orders")
);
```

nhưng như đã nêu, count đơn lẻ không đủ. Bổ sung phân nhóm/key coverage/cross-table invariants.

## 69. Test schema qua database metadata

JDBC `DatabaseMetaData`:

```java
try (Connection conn = dataSource.getConnection()) {
    DatabaseMetaData meta = conn.getMetaData();

    try (ResultSet cols = meta.getColumns(
            conn.getCatalog(),
            "public",
            "purchase_orders",
            "total_amount")) {

        assertTrue(cols.next());
        int jdbcType = cols.getInt("DATA_TYPE");

        assertEquals(
            java.sql.Types.NUMERIC,
            jdbcType
        );
    }
}
```

Cần tùy chỉnh expectations theo JDBC driver/type representation. Đừng chỉ test column exists rồi kết luận CHECK/UNIQUE/INDEX đúng.

Với những thuộc tính DB-specific, dùng catalog SQL khi metadata API không đủ.

## 70. Một JPA regression test cho tenant isolation

```java
@Test
void orderQueryMustNotLeakOtherTenant() {
    seedOrder(tenantA, "ORD-SHARED");
    seedOrder(tenantB, "ORD-SHARED");

    List<PurchaseOrder> result =
        repository.findRecentByTenant(tenantA, 20);

    assertFalse(result.isEmpty());
    assertTrue(
        result.stream()
            .allMatch(o -> o.getTenantId()
                .equals(tenantA))
    );
}
```

Methods `seedOrder` và repository là fixture/API giả định, cần triển khai theo codebase thật. Dùng hai tenants có cùng business key để bắt bug quên tenant predicate. Test cũng cần xác minh order IDs/rows chứ không chỉ allMatch trên empty list (vì empty stream luôn allMatch true).

Sau thay đổi schema/RLS/routing, test tenant isolation quan trọng ngang với SQL latency.

## 71. Test commit/rollback bằng context mới

Một transaction test:

```java
EntityManager writer = emf.createEntityManager();
EntityTransaction tx = writer.getTransaction();

try {
    tx.begin();
    writer.persist(order);
    writer.flush();
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
} finally {
    writer.close();
}

EntityManager reader = emf.createEntityManager();
try {
    assertNotNull(
        reader.find(PurchaseOrder.class, orderId)
    );
} finally {
    reader.close();
}
```

Đây là RESOURCE_LOCAL. Nếu bạn cần kiểm tra rollback, seed committed state rồi thực hiện invalid write/rollback và đọc lại context mới. Tránh chỉ assert object fields sau setter: Java memory không tự rollback.

## 72. Test version conflict sau thay đổi infrastructure

Một scenario:

```text
Seed Order version 0 and commit

EM1 + transaction A: load version 0
EM2 + transaction B: load version 0

A: change status and commit → version 1
B: change status and try flush/commit
Expected: optimistic conflict, B rollback

Fresh EM: DB has A's committed state
```

Nếu SQL update từ provider mới không có version predicate hoặc bulk DML code path đã thay đổi, test sẽ phát hiện trạng thái bị ghi đè.

Với databases/isolation khác, exact exception type/time có thể đổi, nên assert appropriate cause chain và state semantics, không hardcode một timing không portable.

---

## 73. CI pipeline: các cổng kiểm chứng

Một pipeline điển hình:

```text
Build application
   │
   ▼
Unit tests
   │
   ▼
Start disposable production-like DB
   │
   ▼
Apply migrations from empty schema
   │
   ▼
Hibernate mapping validate
   │
   ▼
DB constraint/index/schema tests
   │
   ▼
JPA integration tests
   │
   ▼
Migration upgrade tests (old schema + data)
   │
   ▼
Performance smoke/baseline comparison
   │
   ▼
Deployment candidate
```

Ngoài fresh migration test, có thể cần test **upgrade path**:

```text
Apply V1..V12
Seed realistic old data
Apply V13
Verify backfill/constraints
Bootstrap new app version
```

Fresh database không có legacy data có thể không bắt được lỗi add NOT NULL/rename/backfill trên những rows cũ.

## 74. Không để test tự động trỏ nhầm production

Đặc biệt khi test dùng `DROP`, `TRUNCATE`, `DELETE` hoặc Flyway `clean`:

- Dùng database disposable do Testcontainers tạo.
- Không lấy production JDBC URL từ environment fallback.
- Dùng test-specific DB credentials/role.
- Có guard ownership nếu có destructive operations.
- Không chạy `hibernate.hbm2ddl.auto=create-drop` trên shared DB.
- Không gọi `flyway.clean()` trên DB đang sử dụng.
- Không in passwords vào logs.
- Không tự động retry destructive migration trên production khi chưa có runbook.

Một test “nhanh” nhưng có khả năng xóa dữ liệu shared là thiết kế không chấp nhận được.

## 75. Có thể cần kiểm chứng trực tiếp trên staging/prod-readonly

Một integration test trong Testcontainers chứng minh code + migrations chạy với database engine tương tự, nhưng không chứng minh:

- Production role grants đúng.
- Production data distribution đúng.
- Production row count/data consistency đúng.
- Production hardware/load giống.
- CDN/proxy/network path tương đương.
- Replica lag.
- Actual connection routing.
- Data skew của một tenant lớn.
- Parameter plans trên 100 triệu rows.

Do đó kết hợp **CI disposable tests**, **staging rehearsal**, **read-only production diagnostics** và **post-cutover monitoring**. Các production data checks phải tuân thủ quyền truy cập, chi phí truy vấn và bảo vệ PII.

---

## 76. Chọn bằng chứng đủ mạnh cho mỗi kết luận

| Kết luận muốn chứng minh | Bằng chứng yếu | Bằng chứng mạnh hơn |
| --- | --- | --- |
| App trỏ đúng DB | `SELECT 1` | DB identity + role/schema + per-instance routing |
| Migration hoàn thành | Startup OK | Flyway validate/history + catalog |
| Constraints đúng | Entity annotations tồn tại | DB catalog + negative integrity tests |
| Data copy đầy đủ | COUNT tổng bằng nhau | Snapshot-aligned key coverage + aggregates/hash |
| Values đúng | 100 random samples | Deterministic chunk comparisons + edge samples |
| Queries đúng | JPQL compile | Integration tests trên migrated DB |
| SQL performance ổn | SQL có Index Scan | Actual plan, rows, buffers, latency under load |
| Commit thật | ID được sinh | Transaction complete + fresh DB readback |
| Tenant isolation | Một test tenant duy nhất | Cross-tenant fixtures + negative authorization cases |
| Rollback có thể thực hiện | Revert app image | Schema/data rollback or forward-fix rehearsed |

Không một bằng chứng đơn lẻ thay thế được tất cả; chọn evidence theo risk và business criticality.

## 77. Chứng cứ nên lưu sau rollout

Một release record có thể bao gồm:

```text
Change ID:
Release versions:
DB source/target identity:
Cutover timestamp and logical watermark:
Flyway schema version + validation:
Schema catalog diff:
Row/key counts by business dimension:
Reconciliation mismatches:
Hot SQL fingerprints + before/after plan:
API latency P50/P95/P99:
Error/lock/pool/replication metrics:
Feature flag and canary stages:
Rollback/forward-fix decision:
Owner and sign-off:
```

Không lưu bản dump PII/bind values không cần thiết vào ticket. Chỉ giữ metadata, aggregate metrics và link tới evidence được kiểm soát quyền truy cập.

## 78. Kiểm tra drift theo thời gian

Sau di trú, schema/data có thể drift do:

- Một DBA chỉnh DDL thủ công.
- Một app instance cũ dùng config update schema.
- Một migration áp sai environment.
- Một job ghi code/value legacy.
- Cache/proxy trả dữ liệu từ nguồn cũ.
- Một pipeline CDC silently failed.
- Có thêm service không đi qua migration policy.

Có thể lập scheduled drift checks:

- Flyway validate định kỳ.
- Schema catalog fingerprint.
- DB grants/roles diff.
- Critical uniqueness/orphan checks.
- CDC lag/mismatch metrics.
- Slow query plan changes.
- Data reconciliation theo tenant/chunks.
- Replication/backup restore drills.

Không chạy full-table checks quá nặng ở peak traffic; chọn incremental/checkpoint scans và observation schedule phù hợp.

---

## 79. Các bẫy vận hành thường gặp

### Bẫy 1: `SELECT 1` thành công nên migration đã đúng

Sai. Nó không biết tables/constraints/data/JPA behavior.

### Bẫy 2: EntityManagerFactory bootstrap thành công nghĩa schema hoàn toàn khớp

Không. Provider validation có phạm vi hữu hạn.

### Bẫy 3: Flyway history cho thấy V13 success nên backfill đúng

Không. Data reconciliation là bước riêng.

### Bẫy 4: Source và target cùng COUNT nên data giống

Không. Có thể mất/trùng keys hoặc sai values.

### Bẫy 5: Query dùng index nên chắc nhanh

Không. Có thể scan rất nhiều entries hoặc chậm do lock waits.

### Bẫy 6: Một SQL thay vì 100 SQL chắc tốt hơn

Không nếu JOIN FETCH tạo hàng triệu duplicate rows.

### Bẫy 7: Test dùng cùng EntityManager đã đọc đúng DB

L1 cache có thể che actual committed state.

### Bẫy 8: Bật Hibernate create-drop để “sửa” missing table ở production

Nguy hiểm, có thể xóa data/schema và che lỗi migration.

### Bẫy 9: App old/new cùng writable sau cutover

Có thể split-brain/divergent data.

### Bẫy 10: Code rollback cũng rollback database changes

Không nếu schema/data đã chuyển không đảo ngược.

### Bẫy 11: Read replica chưa thấy row nên commit thất bại

Có thể chỉ là replication lag.

### Bẫy 12: DB import xong không cần kiểm tra sequence

Có thể generated IDs đụng primary keys cũ.

### Bẫy 13: Nullable column mới sẽ hết NULL tự động

Không. Backfill và validation phải được thiết kế.

### Bẫy 14: DDL luôn rollback được

Khác theo database/operation; không giả định portable.

### Bẫy 15: SQLState một engine áp được cho engine khác

Không. Exception translation cần theo driver/provider/DB.

### Bẫy 16: Cùng JDBC URL nghĩa mọi instance kết nối cùng backend

Pool/proxy/DNS/session state có thể khiến khác nhau trong rollout.

### Bẫy 17: Data copy và live writes có thể so tại bất kỳ thời điểm nào

Không. Cần snapshot/CDC watermark nhất quán.

### Bẫy 18: Trigram/partial/expression index portable qua mọi DB

Không. Đây là features theo engine/dialect.

### Bẫy 19: Startup check quyền SELECT đủ cho write path

Không. Cần write smoke tests/permissions phù hợp.

### Bẫy 20: Benchmark bảng 100 rows đại diện production 100 triệu rows

Không. Query plan và costs thay đổi theo data size/distribution.

### Bẫy 21: Bỏ tenant filter để query nhanh hơn

Không chấp nhận; phá isolation/security.

### Bẫy 22: `EXPLAIN ANALYZE DELETE` chỉ xem plan

Sai. Nó thực thi DML trên PostgreSQL.

### Bẫy 23: Hash toàn dữ liệu nhưng normalization khác nhau

Báo mismatch giả hoặc che mismatch; cần canonicalization.

### Bẫy 24: Query có no duplicates nên UNIQUE constraint chắc tồn tại

Chưa chắc; cần catalog và negative test.

### Bẫy 25: Test được chạy trên H2 nên PostgreSQL nâng cấp chắc an toàn

Không. Driver/dialect/locking/constraint behavior khác.

---

## 80. Bài tập 1: Endpoint identity

Sau cutover, health check xanh nhưng một số app instances vẫn ghi DB cũ.

**Đáp án:** Kiểm tra per-instance JDBC endpoint, pool connections, proxy routing và fencing writers. `SELECT 1` không chứng minh tất cả đã chuyển.

## 81. Bài tập 2: Flyway history

Migration V13 báo success, nhưng `fulfillment_state` còn NULL ở 3% Orders.

**Đáp án:** Schema migration khác backfill verification. Không contract NOT NULL trước khi reconciliation xong.

## 82. Bài tập 3: Counts trùng

Source 1.000 Orders, target 1.000 Orders nhưng mất một orderNo và có duplicate khác.

**Đáp án:** Count tổng không đủ; đối soát business key coverage/duplicates.

## 83. Bài tập 4: Aggregate bằng nhưng rows sai

Source hai Orders 100 và 200; target hai Orders 150 và 150.

**Đáp án:** SUM bằng 300 nhưng values sai; cần row-level comparison/digests.

## 84. Bài tập 5: N+1 sau Hibernate upgrade

Page 20 Orders giờ phát 21 SQL thay vì một.

**Đáp án:** Phân tích fetch plan/mapper/provider SQL patterns, không chỉ thêm index.

## 85. Bài tập 6: Enum ORDINAL → STRING

Đổi `@Enumerated` nhưng rows cũ vẫn chứa số.

**Đáp án:** Cần data migration tương ứng, compatibility plan và tests đọc dữ liệu cũ.

## 86. Bài tập 7: Timezone biên ngày

Order lúc `2026-11-14T17:00:00Z` bị xếp sang ngày 14 theo local DB setting.

**Đáp án:** Theo Asia/Ho_Chi_Minh đó là midnight ngày 15; chuẩn hóa timezone và test boundaries.

## 87. Bài tập 8: Sequence drift

Target đã import ID tới 2 triệu nhưng sequence vẫn ở 100.

**Đáp án:** Xác minh sequence/identity ownership và điều chỉnh có kiểm soát khi writers được coordinated.

## 88. Bài tập 9: FK orphan

Target còn 20 OrderLines trỏ Order không tồn tại.

**Đáp án:** Reconciliation cần truy vấn orphan, sửa data và validate FK; count Orders riêng không phát hiện.

## 89. Bài tập 10: Index tạo rồi nhưng invalid

`pg_indexes` thấy tên index, `pg_index.indisvalid=false`.

**Đáp án:** Không coi index sẵn sàng. Điều tra failed/concurrent index creation và khôi phục theo runbook.

## 90. Bài tập 11: SQL chậm sau upgrade

Một SQL dùng index nhưng mất 800ms và đọc hàng triệu rows.

**Đáp án:** Xem actual plan, Index Cond/Filter, statistics, buffer reads và data skew; index existence không đồng nghĩa optimality.

## 91. Bài tập 12: H2 passes

JPA tests trên H2 pass, production PostgreSQL partial index/locking fail.

**Đáp án:** Thêm Testcontainers PostgreSQL integration/schema tests cho DB-specific behavior.

## 92. Bài tập 13: Hibernate validate pass

`CHECK(total_amount >= 0)` không tồn tại nhưng startup vẫn pass.

**Đáp án:** Validation mapping không kiểm tra mọi constraint. Dùng DB catalog và negative write test.

## 93. Bài tập 14: Read replica lag

Sau commit, read API trả Not Found trong 100ms đầu.

**Đáp án:** Kiểm tra replica consistency contract/lag/routing; không suy write rollback ngay.

## 94. Bài tập 15: Rollback App v1

App v2 đã drop column mà v1 vẫn cần.

**Đáp án:** Revert code không đủ. Cần expand-contract compatibility hoặc forward-fix/restore plan.

## 95. Bài tập 16: Old writer hoạt động

Một cron job cũ ghi DB cũ sau cutover.

**Đáp án:** Fencing và old-DB write monitoring là điều kiện cutover. Cần reconcile những writes đã đi sai nơi.

## 96. Bài tập 17: Backfill không idempotent

Chạy lại script làm totalAmount tăng gấp đôi.

**Đáp án:** Không đạt retry safety; thiết kế deterministic updates với checkpoint và kiểm chứng.

## 97. Bài tập 18: Prepared statement behavior

Ứng dụng chuyển qua transaction-pooling proxy, prepared statements lỗi ngẫu nhiên.

**Đáp án:** Kiểm tra proxy mode và JDBC/server-side prepare compatibility, không mặc định session state bền.

## 98. Bài tập 19: Two-phase ID paging

Tải 20 Order IDs rồi JOIN FETCH Lines bằng `IN :ids`, results bị đổi thứ tự.

**Đáp án:** `IN` không đảm bảo order. Khôi phục thứ tự IDs và kiểm tra consistency giữa hai queries.

## 99. Bài tập 20: Unique theo tenant

Sau migration, constraint là `UNIQUE(order_no)` thay vì `UNIQUE(tenant_id,order_no)`.

**Đáp án:** Sai business rule; kiểm tra catalog definition và negative tests cross-tenant.

## 100. Bài tập 21: Test rollback

`persist` rồi `flush`, `find` trong cùng EntityManager trả entity, sau đó rollback.

**Đáp án:** Không chứng minh committed state. Đọc lại bằng context mới sau rollback.

## 101. Bài tập 22: Constraint deferred

`flush` success nhưng commit fail.

**Đáp án:** Constraint có thể kiểm tra ở commit. Test cả completion boundary.

## 102. Bài tập 23: Performance baseline

Chỉ đo thời gian chạy một query trên cache nóng.

**Đáp án:** Cần nhiều runs, representative parameters, concurrency, P95/P99 và DB/JVM/pool metrics.

## 103. Bài tập 24: Cutover watermark

Source tiếp tục writes trong khi so counts với target.

**Đáp án:** Counts không thể so trực tiếp khi snapshots khác. Dùng consistent watermark/CDC catch-up.

## 104. Bài tập 25: Runbook hoàn chỉnh

**Yêu cầu:** Nâng cấp PostgreSQL + Hibernate và thêm `fulfillment_state` cho Order không downtime.

**Hướng giải:**

1. Ghi baseline versions, SQL, latency và source data invariants.
2. Test provider/driver/DB compatibility.
3. Chạy production migrations trên Testcontainers/staging.
4. Expand nullable column và deploy read-compatible code.
5. Backfill theo chunks/checkpoints.
6. Bảo đảm concurrent writes luôn cập nhật representation mới.
7. Đối soát null/mismatch/keys/aggregates/tenant.
8. Xác minh JPA generated SQL, enum/timestamp mappings.
9. Chạy constraints, commit/rollback/optimistic concurrency tests.
10. Capture hot query plans và index validity.
11. Cutover với writer fencing và CDC watermark nếu đổi DB.
12. Progressive rollout/monitor P95, errors, locks, pool và replica lag.
13. Chỉ contract NOT NULL/loại legacy code khi đủ điều kiện.
14. Chuẩn bị forward-fix/restore plan và ghi release evidence.

---

## 105. Checklist xác minh sau thay đổi hạ tầng

### A. Kết nối và cấu hình

- [ ] Mọi app instance đang dùng đúng JDBC endpoint/database.
- [ ] Database engine và server version được ghi nhận.
- [ ] JDBC driver, ORM/JPA provider và dialect tương thích.
- [ ] Database name, schema, search_path và current role đúng.
- [ ] Migration user và runtime user có quyền phù hợp.
- [ ] TLS/hostname verification và secrets được bảo vệ.
- [ ] Connection proxy/pool không làm lệch transaction/session semantics.
- [ ] Old writers đã được fence hoặc xử lý có kiểm soát.

### B. Lược đồ và migration

- [ ] Flyway/Liquibase history khớp release.
- [ ] Migration validation/checksum pass.
- [ ] Schema có tables, columns, types, NULL/default chính xác.
- [ ] PK, UNIQUE, FK, CHECK definitions đúng.
- [ ] Indexes có đúng keys, predicate, validity và đủ cho hot queries.
- [ ] JPA mapping validation chạy trên schema đã migrate.
- [ ] Không còn obsolete DDL automatic create/update trái policy.
- [ ] Expand–contract phases theo đúng compatibility window.

### C. SQL và JPA

- [ ] SQL generated thực tế đã được capture cho hot use cases.
- [ ] Tenant/authorization/soft-delete filters còn đúng.
- [ ] Parameter types, enum/timezone mappings không sai.
- [ ] Pagination, ORDER BY và tie-breakers đúng.
- [ ] SQL count không N+1 bất ngờ.
- [ ] JOIN FETCH không gây Cartesian explosion.
- [ ] Query plans và actual rows/buffers được kiểm tra.
- [ ] DTO projection/serialization không tạo overhead ngoài dự kiến.
- [ ] Bulk DML có được kiểm tra version/callback semantics không.

### D. Dữ liệu và consistency

- [ ] Source/target được so tại watermark nhất quán.
- [ ] Counts theo table/tenant/status/day phù hợp.
- [ ] Không có keys thiếu/dư/duplicate ngoài policy.
- [ ] Money totals và row-level amounts đúng.
- [ ] Không có orphan foreign keys.
- [ ] Những NULL/invalid statuses sau backfill đạt ngưỡng 0 nếu yêu cầu.
- [ ] Hash/chunk comparison dùng canonicalization thống nhất.
- [ ] Timestamp/timezone, Unicode/collation và numeric precision đúng.
- [ ] Sequences/identity không cấp trùng IDs đã import.
- [ ] CDC/replication catch-up đạt điều kiện cutover.

### E. Giao dịch và vận hành

- [ ] Commit/rollback integration tests pass với fresh-context readback.
- [ ] UNIQUE/FK/CHECK negative tests xác nhận DB behavior.
- [ ] Optimistic version conflict được phát hiện.
- [ ] Pessimistic locks, timeout và isolation behavior phù hợp.
- [ ] Pool pending/active, connection timeouts bình thường.
- [ ] API P95/P99 và error rates nằm trong SLO.
- [ ] DB CPU/I/O, lock waits và replication lag được theo dõi.
- [ ] Backup restore/forward-fix/rollback plan đã được tập dượt.
- [ ] Có go/no-go owner và release evidence.
- [ ] Không chạy destructive verification trên shared/prod data.

Checklist này không yêu cầu mọi bài test chạy trong production. Nó giúp phân chia công việc: phần nào kiểm tra được trong CI/Testcontainers, phần nào phải rehearsal trên staging, và phần nào chỉ có thể quan sát sau cutover thực.

## Kết luận

**Xác minh SQL, lược đồ và dữ liệu sau thay đổi hạ tầng** không thể thu gọn thành “ứng dụng khởi động được” hoặc “migration không lỗi”.

Một quy trình đáng tin cần chứng minh đồng thời:

- **Đúng nơi:** mỗi app instance kết nối đúng database/schema/role và writer owner.
- **Đúng cấu trúc:** migration history, columns, data types, constraints, indexes và JPA mappings phù hợp nhau.
- **Đúng truy vấn:** SQL generated và parameter/fetch/pagination semantics vẫn đúng, không phát sinh N+1, over-fetch hay plan regression lớn.
- **Đúng dữ liệu:** row/key coverage, aggregates, field-level values, NULL/duplicates/orphans, timestamps và sequences được đối soát theo watermark nhất quán.
- **Đúng giao dịch:** commit, rollback, version/locking và read visibility hoạt động theo consistency contract.
- **Đúng vận hành:** latency, pool, locks, replication/cache lag và error rates nằm trong giới hạn có thể chấp nhận.
- **Có khả năng phục hồi:** biết bước nào backward-compatible, khi nào phải forward-fix, và có evidence/owner để quyết định go/no-go.

Đặc biệt với JPA, đừng đánh đồng entity đang managed với dữ liệu đã commit, đừng lấy `hibernate.hbm2ddl.auto=validate` làm bằng chứng mọi ràng buộc database đều đúng, và đừng nhìn JPQL mà bỏ qua SQL thực thi.

Quy trình nên nhớ là: **định nghĩa hợp đồng thay đổi → thu baseline → xác minh kết nối/schema → kiểm tra SQL thật → đối soát dữ liệu nhất quán → test transaction và performance → rollout có cổng kiểm soát → theo dõi hậu triển khai và chuẩn bị recovery**.

Khi mỗi lớp có bằng chứng riêng, nhóm vận hành có thể phát hiện sai lệch có ý nghĩa trước khi nó trở thành dữ liệu hỏng hoặc sự cố production kéo dài.
