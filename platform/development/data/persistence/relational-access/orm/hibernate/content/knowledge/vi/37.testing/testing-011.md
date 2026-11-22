# Kiểm thử cache, filter và phân lập dữ liệu nhiều tổ chức

Một ứng dụng SaaS có thể lưu dữ liệu của nhiều tổ chức trong cùng một hệ thống. Người dùng thuộc tổ chức A chỉ được thấy đơn hàng, khách hàng và báo cáo của A; người dùng thuộc tổ chức B chỉ được thấy dữ liệu của B. Các truy vấn Hibernate có thể đã thêm điều kiện tenant đúng, nhưng một lỗi vẫn có thể xuất hiện khi bật **first-level cache, second-level cache, query cache, filters hoặc khi đổi tenant context giữa các request**.

Ví dụ: request của A load `Customer(id=42)` vào cache. Sau đó request của B tìm `Customer(id=42)`. Nếu cache key hoặc cách áp dụng filter không chứa đúng tenant context, ứng dụng có thể trả dữ liệu A cho B. Đây là lỗi cách ly dữ liệu nghiêm trọng, dù câu JPQL thông thường có `where tenant_id = :tenantId`.

Bài này tập trung vào cách **kiểm thử cache, filter và tenant isolation xuyên suốt các đường truy cập ORM**: query list, load theo ID, associations, collection, query cache, L2 cache, native SQL, transaction, pooled connections và async execution.

~~~text
Request A                         Request B
   |                                  |
tenant=A                           tenant=B
   |                                  |
Session A                           Session B
   |                                  |
L1-A / L2 / Query cache           L1-B / L2 / Query cache
   |                                  |
   +------------ Hibernate -----------+
                    |
              JDBC / Connection
                    |
                 Database
       tenant_id / schema / database / RLS
~~~

**Nguyên tắc cốt lõi:** Tenant là một phần của security context và transaction boundary. Mỗi Session/EntityManager phải hoạt động với đúng tenant; cache keys, query parameters, connection routing và database constraints phải giữ được cùng ranh giới đó. Một test chỉ kiểm tra query list của tenant A chưa chứng minh tenant B không thể đọc cùng ID qua `find()`, association hoặc cache.

> **Phạm vi:** Java 17+, Hibernate ORM 6.x, Jakarta Persistence, Spring/Spring Data JPA, JDBC, Micrometer và PostgreSQL là bối cảnh minh họa. `@TenantId`, `@FilterDef`, cache provider, multi-tenant connection provider và một số filter-loading options phụ thuộc Hibernate version. Cần kiểm tra đúng Hibernate minor version và DBMS của dự án; các ví dụ không phải cấu hình bảo mật hoàn chỉnh dùng trực tiếp cho production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt first-level cache, second-level cache và query cache.
2. Hiểu cache key, Session identity và tenant identifier ảnh hưởng thế nào tới isolation.
3. Kiểm thử Hibernate `@Filter` với tham số tenant, kể cả load-by-ID và association paths.
4. Phân biệt discriminator-based, schema-based và database-based multi-tenancy.
5. Sử dụng `@TenantId` khi phiên bản Hibernate hỗ trợ và kiểm tra tenant identifier được áp dụng đúng.
6. Phát hiện rủi ro khi filter parameter không nằm trong cache key hoặc khi Session được tái sử dụng sai.
7. Kiểm thử cache hits/misses, eviction và stale data sau update.
8. Kiểm tra query cache khi cùng một HQL được chạy dưới nhiều tenants.
9. Kiểm thử native SQL, bulk DML, JDBC và các đường truy cập có thể bypass ORM filters.
10. Kiểm soát tenant context qua thread pool, async tasks và message consumers.
11. Thiết kế Testcontainers/integration tests để xác minh isolation bằng database gần production.
12. Xây dựng negative tests chứng minh một tenant không thể đọc, sửa hoặc liên kết dữ liệu của tenant khác.

## 2. Vì sao cần test cả cache và tenant cùng lúc?

Một test đơn giản:

~~~java
List<Order> orders = entityManager.createQuery(
    "select o from Order o where o.tenantId = :tenantId",
    Order.class
)
.setParameter("tenantId", tenantId)
.getResultList();
~~~

có thể pass vì query đã lọc đúng. Nhưng ứng dụng còn các đường khác:

- `entityManager.find(Order.class, id)`.
- `getReference()` rồi initialize proxy.
- Load `Customer.orders`.
- `Order.customer` qua LAZY/EAGER.
- Query có cache.
- Entity đã nằm trong first-level cache.
- Native SQL do repository tự viết.
- Bulk update/delete.
- Một request khác chạy trên pooled connection vừa dùng tenant khác.

Mỗi đường truy cập có semantics khác. **Tenant isolation phải được xác minh trên toàn bộ graph truy cập dữ liệu**, không chỉ trên một repository method.

## 3. Ba lớp cache cần phân biệt

| Lớp | Phạm vi | Nội dung thường giữ | Rủi ro cần test |
|---|---|---|---|
| First-level cache (L1) | Một Session/EntityManager | Managed entity instances và collections | Session dùng sai tenant hoặc context giữ object cũ |
| Second-level cache (L2) | Nhiều Sessions trong SessionFactory | Entity/collection state theo cache region | Cache key, tenant key, invalidation |
| Query cache | Nhiều Sessions theo cấu hình | Query result/identifiers và metadata liên quan | Query parameters/filter/tenant dimension, stale result |

L1 cache luôn gắn với persistence context; nó không phải cache dùng chung toàn ứng dụng. L2/query cache là tùy chọn và cần cache provider phù hợp.

Không được gọi cả ba là “Hibernate cache” rồi giả định chúng có cùng key hoặc cùng lifecycle.

## 4. First-level cache và identity map

Trong một Session, Hibernate giữ một managed instance cho một entity identity. Ví dụ:

~~~java
Order first = session.find(Order.class, 100L);
Order second = session.find(Order.class, 100L);

assertSame(first, second);
~~~

Thông thường lần thứ hai có thể trả object đã quản lý mà không chạy SQL mới.

Lợi ích:

- Identity nhất quán trong một unit of work.
- Dirty checking.
- Giảm SELECT lặp trong cùng context.
- Theo dõi associations và collections.

Rủi ro cho tenant isolation xuất hiện khi ứng dụng **tự thay đổi tenant filter/context trong cùng Session**, hoặc dùng Session/EntityManager vượt quá request/tenant boundary. Một Session không nên được tái sử dụng cho hai tenants.

## 5. Một Session phải có tenant context ổn định

Một Session/EntityManager đại diện cho một persistence context. Với multi-tenancy, tenant identifier được chọn khi Session được mở hoặc được resolve bởi integration tương ứng.

Không làm:

~~~java
Session session = sessionFactory.openSession();

session.enableFilter("tenantFilter")
    .setParameter("tenantId", "tenant-A");

// Load entity A.

session.disableFilter("tenantFilter");
session.enableFilter("tenantFilter")
    .setParameter("tenantId", "tenant-B");

// Tiếp tục dùng cùng Session để load tenant B.
~~~

Ngay cả khi query mới có predicate B, L1 cache và các managed references đã có từ tenant A vẫn tồn tại. Thay filter parameter không biến các objects cũ thành tenant B objects.

**Tạo Session/EntityManager riêng cho mỗi tenant unit of work**, đóng/clear đúng lifecycle, và không chia sẻ managed entities giữa requests.

## 6. Test chứng minh L1 cache không bị trộn tenant

Nếu dùng manual filter, tạo hai Sessions riêng:

~~~java
try (Session sessionA = sessionFactory.openSession()) {
    sessionA.enableFilter("tenantFilter")
        .setParameter("tenantId", "tenant-A");

    Order orderA = sessionA.find(Order.class, orderId);
    assertEquals("tenant-A", orderA.getTenantId());
}

try (Session sessionB = sessionFactory.openSession()) {
    sessionB.enableFilter("tenantFilter")
        .setParameter("tenantId", "tenant-B");

    Order orderB = sessionB.find(Order.class, orderId);
    // Xác nhận không nhận được row của tenant-A.
}
~~~

Đoạn này chỉ minh họa lifecycle. Hành vi filter đối với load-by-key phụ thuộc mapping và Hibernate version; không giả định `find()` tự động áp dụng filter trong mọi cấu hình.

Một test tốt cần chạy cả hai chiều A→B và B→A, đóng Session giữa các lần, và kiểm tra query SQL/exception/result rõ ràng.

## 7. Second-level cache là cache xuyên Session

Một entity có thể bật L2 cache:

~~~java
@Entity
@Table(name = "product")
@Cacheable
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.products"
)
public class Product {
    @Id
    private Long id;

    private String name;
}
~~~

Cấu hình provider/cache region phải được thiết lập riêng. Annotation JPA `@Cacheable` và annotation Hibernate `@Cache` không tự tạo cache provider nếu project chưa cấu hình.

L2 cache có thể phục vụ một Session mới mà không cần SELECT database. Đây là nơi cần xác nhận tenant identity trong cache key và cách mapping/filter được áp dụng.

## 8. Query cache không phải bản sao của entity cache

Query cache được bật khi cấu hình Hibernate và query được đánh dấu cacheable:

~~~java
List<Product> products = session.createSelectionQuery(
    "from Product p where p.category = :category",
    Product.class
)
.setParameter("category", category)
.setCacheable(true)
.getResultList();
~~~

Query cache thường giữ kết quả query (thường là identifiers cho entity queries) cùng metadata/space invalidation. Entity state có thể được lấy từ L2 cache hoặc database tùy cấu hình.

Các điểm phải test:

- Cùng query với tenant A và tenant B.
- Cùng parameter nhưng filter values khác.
- Query cache hit sau lần chạy đầu.
- Data update làm query result invalidated đúng không.
- Cache region có chứa kết quả nhạy cảm không.
- Query cache và L2 cache cùng bật có behavior thế nào.

Không giả định query cache key chỉ có HQL text. Hibernate có thể xét parameters, enabled filters và tenant context theo implementation/version; **phải kiểm chứng bằng integration test trên version đang chạy**.

## 9. Cache key và tenant identifier

Với Hibernate multi-tenancy thực sự, tenant identifier là một phần của cache identity/key trong cơ chế multi-tenant của Hibernate. Điều này giúp cùng một entity ID ở hai tenants không bị coi là cùng cache entry khi tenant context được thiết lập đúng.

Tuy nhiên, đừng mở rộng kết luận đó cho mọi ứng dụng chỉ có cột `tenant_id` và tự viết `@Filter`.

Hai thiết kế khác nhau:

1. **Hibernate multi-tenancy:** Tenant identifier là một phần của Session/tenant-aware loading và cache key.
2. **Manual filter:** Entity được lọc bằng filter parameter, nhưng cache key của entity có thể chỉ dựa trên entity identity/tenant setup mà mapping thực sự cung cấp.

Nếu dùng manual filter, cần bảo đảm primary key/identity và cache strategy không cho phép cùng key được diễn giải khác nhau theo filter parameter. Nếu không chứng minh được, tắt L2 cache cho dữ liệu tenant-scoped hoặc dùng tenant-aware multi-tenancy/key design.

## 10. Kiểm thử L2 cache hit/miss đúng cách

Để xác nhận cache thực sự được sử dụng:

1. Bật L2 cache và một provider phù hợp.
2. Bật Hibernate statistics trong test.
3. Commit entity fixture.
4. Clear/đóng Session đầu.
5. Load entity trong Session mới để warm cache.
6. Đóng Session.
7. Load lại trong Session thứ hai.
8. Đọc hit/miss counts và SQL logs.
9. Lặp lại với tenant khác.

Ví dụ statistics:

~~~java
Statistics statistics =
    sessionFactory.getStatistics();

statistics.clear();

// Lần load đầu.
loadInNewSession(id);

// Lần load tiếp theo.
loadInAnotherSession(id);

long hits = statistics.getSecondLevelCacheHitCount();
long misses = statistics.getSecondLevelCacheMissCount();
long puts = statistics.getSecondLevelCachePutCount();
~~~

Statistics là cấp SessionFactory và test chạy song song có thể làm nhiễu. Dùng fixture/workload cô lập; không clear global statistics trong production request.

## 11. Cache test phải tách L1 khỏi L2

Nếu load cùng entity hai lần trong cùng Session:

~~~java
session.find(Product.class, id);
session.find(Product.class, id);
~~~

lần thứ hai có thể chỉ hit L1. Điều này **không chứng minh L2 cache hoạt động**.

Để test L2:

~~~text
Session 1: load Product -> close
Session 2: load Product -> inspect L2 hit
Session 3: load Product -> inspect L2 hit
~~~

Cần đảm bảo entity không bị evict giữa các lần, transaction đã commit, và cache provider không vô hiệu hóa entry vì concurrency strategy/locking.

## 12. Kiểm thử entity cache khi có filter parameter

Một filter thủ công:

~~~java
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(name = "tenantId", type = String.class)
)
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId"
)
@Entity
public class Customer {
    @Id
    private Long id;

    @Column(name = "tenant_id")
    private String tenantId;
}
~~~

Có thể lọc query theo tenant. Nhưng nếu entity cache lookup theo ID không đưa filter parameter vào cache key, entity đã cached có thể tạo đường bypass hoặc visibility behavior không như query SQL.

**Đừng bật L2 cache cho manual-filter tenant entities chỉ vì list query pass.** Hãy test `find`, `getReference`, associations, L2 warm-up từ tenant A rồi load dưới tenant B. Nếu không có bảo đảm version/provider rõ ràng, disable L2 cache cho entity đó hoặc dùng Hibernate tenant-aware identity.

## 13. Filter khi load-by-key và applyToLoadByKey

Hibernate có các phiên bản hỗ trợ tùy chọn `applyToLoadByKey` trong filter definition để áp dụng filter cho những load theo identifier/to-one paths tương ứng.

Ví dụ theo API version có hỗ trợ:

~~~java
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(name = "tenantId", type = String.class),
    applyToLoadByKey = true
)
~~~

Điểm quan trọng:

- Kiểm tra Javadoc đúng Hibernate minor version; không copy thuộc tính nếu version đang dùng không hỗ trợ.
- `find()`/`getReference()` và to-one association loading cần test riêng.
- L2 cache có thể làm thay đổi đường load; không kết luận chỉ từ SQL filter behavior.
- Filter không thay thế authorization/database enforcement.
- Không dùng cùng Session để thay tenant parameter sau khi đã load objects.

Nếu hệ thống cần isolation mạnh, discriminator multi-tenancy/DB-level controls thường rõ ràng hơn việc tự bật một filter trong từng repository.

## 14. @TenantId cho discriminator-based multi-tenancy

Hibernate hỗ trợ discriminator-style tenant mapping bằng `@TenantId` ở các phiên bản phù hợp:

~~~java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    private Long id;

    @TenantId
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    private String name;
}
~~~

Hibernate lấy tenant identifier từ Session/tenant resolver và áp dụng vào các SQL ORM tương ứng. Tenant column được quản lý bởi Hibernate theo mapping/version; không nên để API request tự tùy tiện gán tenant ID.

Cần xác nhận:

- Tenant identifier được resolve đúng cho Session.
- INSERT gắn tenant hiện tại.
- SELECT/UPDATE/DELETE có predicate phù hợp.
- Cache keys tách tenants.
- Associations không thể tham chiếu nhầm tenant.
- Native SQL và bulk operations có policy riêng.

`@TenantId` là Hibernate-specific, không phải Jakarta Persistence annotation.

## 15. Tenant resolver trong ứng dụng Spring

Với Hibernate multi-tenancy, `CurrentTenantIdentifierResolver` có thể lấy tenant identifier từ context ứng dụng:

~~~java
public class RequestTenantResolver
        implements CurrentTenantIdentifierResolver<String> {

    @Override
    public String resolveCurrentTenantIdentifier() {
        return TenantContext.requireTenantId();
    }

    @Override
    public boolean validateExistingCurrentSessions() {
        return true;
    }
}
~~~

Đây là skeleton; generic signatures và wiring cần khớp Hibernate version. `TenantContext` là abstraction do ứng dụng quản lý.

Resolver không tự xác thực người dùng. Trước khi đặt tenant context, application phải xác thực actor có quyền truy cập tenant đó. Không tin trực tiếp header `X-Tenant-Id` do client gửi mà không authorization.

## 16. Mở Session với tenant identifier tường minh

Hibernate SessionBuilder có thể nhận tenant identifier:

~~~java
try (Session session = sessionFactory
        .withOptions()
        .tenantIdentifier("tenant-A")
        .openSession()) {
    // Chỉ xử lý unit of work của tenant-A.
}
~~~

Cách này hữu ích trong integration tests, background jobs và tooling cần chỉ định tenant rõ.

Không dùng chung Session sau khi đã gán tenant. Đóng Session khi hoàn thành unit of work; tenant identifier không phải một setting đổi qua lại an toàn trong một persistence context.

## 17. Ba chiến lược multi-tenancy

| Chiến lược | Cách lưu | Thành phần cần test |
|---|---|---|
| Database per tenant | Mỗi tenant có database riêng | Connection routing, credentials, pool, migrations |
| Schema per tenant | Mỗi tenant có schema riêng | Schema selection, connection/session reset, SQL qualification |
| Discriminator column | Chung tables, có `tenant_id` | Tenant predicate, cache key, composite constraints |

Database/schema separation có thể tạo ranh giới vật lý mạnh hơn, nhưng connection routing sai vẫn có thể đưa request tới nhầm DB/schema. Discriminator dễ chia sẻ hạ tầng hơn nhưng mọi đường truy cập phải áp dụng tenant constraint đúng.

## 18. Test discriminator isolation

Fixture có thể có:

~~~sql
CREATE TABLE customer (
    id BIGINT NOT NULL,
    tenant_id VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
~~~

Dữ liệu:

~~~sql
INSERT INTO customer(tenant_id, id, name)
VALUES
    ('tenant-A', 1, 'Alice A'),
    ('tenant-B', 1, 'Bob B');
~~~

Hai tenants có cùng local ID nhưng dữ liệu khác nhau. Test mở hai Sessions với tenant identifier riêng, rồi load ID 1.

Kết quả kỳ vọng:

- Tenant A thấy Alice A.
- Tenant B thấy Bob B.
- Không Session nào nhận object của tenant kia.
- L2 cache không trộn hai entries.
- Query cache không trả kết quả của tenant khác.

Schema PK composite là ví dụ DB-level constraint; entity mapping/identifier strategy phải phù hợp Hibernate multi-tenancy setup đang dùng. Không copy DDL này nếu entity `@Id`/tenant mapping của dự án chưa hỗ trợ semantics tương ứng.

## 19. Test insert tenant ID

Với `@TenantId`, kiểm tra insert:

~~~java
try (Session session = openTenantSession("tenant-A")) {
    Transaction tx = session.beginTransaction();

    Customer customer = new Customer();
    customer.setName("Alice");

    session.persist(customer);
    tx.commit();
}
~~~

Sau đó query raw DB hoặc dùng session tenant A/B để xác nhận `tenant_id` được ghi đúng.

Không cho client gửi một `tenantId` tùy ý rồi bind vào entity. Nếu field tenant được Hibernate quản lý, application nên lấy tenant từ authenticated context và để ORM gán theo contract của phiên bản.

## 20. Test update/delete không vượt tenant boundary

Một negative test cần thử cả read và write:

- Tenant A load row A rồi update.
- Tenant B cố load cùng local ID.
- Tenant B cố update/delete ID của A.
- Kiểm tra DB row A không thay đổi bởi request B.
- Kiểm tra affected row count và transaction outcome.
- Kiểm tra bulk DML có predicate tenant hay không.

Không chỉ assert query trả empty. Một đường UPDATE không tenant predicate có thể sửa dữ liệu dù SELECT đã lọc đúng.

Với database discriminator, primary key/unique constraints nên bao gồm tenant khi ID chỉ unique trong tenant. Foreign keys cần bảo đảm association không thể trỏ cross-tenant.

## 21. Composite unique constraints và foreign keys

Nếu business key chỉ unique trong một tổ chức:

~~~sql
CREATE UNIQUE INDEX uq_customer_tenant_email
ON customer(tenant_id, lower(email));
~~~

Nếu Order tham chiếu Customer trong cùng tenant, một DB design có thể dùng composite FK:

~~~sql
ALTER TABLE customer
    ADD CONSTRAINT uq_customer_tenant_id
    UNIQUE (tenant_id, id);

ALTER TABLE orders
    ADD CONSTRAINT fk_order_customer_same_tenant
    FOREIGN KEY (tenant_id, customer_id)
    REFERENCES customer(tenant_id, id);
~~~

Như vậy DB có thể ngăn một Order tenant A tham chiếu Customer tenant B, kể cả application mapping có bug.

ORM association mapping cho composite foreign key cần được thiết kế phù hợp; nếu mapping chỉ dùng `customer_id`, DB composite constraint có thể cần thêm column mapping và migration. Đây là lớp defense-in-depth rất hữu ích.

## 22. Test association và collection isolation

Một entity có thể được lọc đúng khi query root nhưng lộ dữ liệu qua association nếu FK/tenant mapping sai.

Test các đường:

~~~java
Order order = session.find(Order.class, orderId);
Customer customer = order.getCustomer();

List<OrderLine> lines = order.getLines();
~~~

Với tenant A, xác nhận:

- Customer thuộc A.
- Lines thuộc A.
- Các child rows có `tenant_id` phù hợp.
- Không có foreign key tới tenant B.
- Lazy initialization vẫn dùng cùng tenant context.
- Fetch join/entity graph cho kết quả tương đương.

Thêm test cho `ManyToMany`, join tables và collection tables: tenant column cần nằm trong association key/constraint nếu quan hệ được partition theo tenant.

## 23. Query cache qua hai tenants

Chọn một HQL query cacheable:

~~~java
List<Customer> findActiveCustomers(Session session) {
    return session.createSelectionQuery(
        "from Customer c where c.active = true order by c.id",
        Customer.class
    )
    .setCacheable(true)
    .getResultList();
}
~~~

Chạy:

1. Session tenant A, gọi query lần đầu.
2. Session tenant B, gọi cùng query, cùng HQL/parameters.
3. Session tenant A lần nữa.
4. Kiểm tra kết quả theo tenant.
5. Kiểm tra query-cache hits/misses.
6. Lặp sau khi cập nhật dữ liệu của tenant A.

Hibernate có tenant context và query/cache-key logic riêng trong multi-tenancy; vẫn phải test đúng phiên bản, cache provider và query plan. Đừng suy luận rằng cùng HQL chắc chắn cùng cache entry, hoặc khác tenant chắc chắn tự tách đúng trong mọi cấu hình custom.

## 24. Query parameters và enabled filters trong cache

Query có thể phụ thuộc:

- HQL/SQL string.
- Query parameters.
- Pagination/sort options.
- Enabled filter names và parameter values.
- Tenant identifier.
- Query spaces/data invalidation.
- Cache region/provider behavior.

Với manual filters, kiểm tra rằng tenant parameter khác nhau không nhận cached result của nhau. Nếu không chứng minh được behavior, không cache query tenant-scoped cho đến khi có strategy an toàn.

Khi test, không dùng một Session đã warm query cache và L1 cache rồi kết luận query cache key đúng. Mỗi lần chạy nên dùng Session mới, nhưng vẫn cùng SessionFactory/cache provider.

## 25. Entity L2 cache và manual filter

Giả sử `Customer` có global numeric ID và manual filter `tenant_id=:tenantId`. Nếu entity cache key không chứa filter parameter, việc cache một entity theo ID có thể không biểu diễn tenant scope của filter.

Thiết kế an toàn cần một trong các điều kiện:

- Dùng Hibernate multi-tenancy để tenant identifier được đưa vào cache identity.
- Entity identifier thực sự chứa tenant discriminator theo mapping/DB identity.
- Không cache entity tenant-scoped bằng L2 nếu không thể chứng minh key isolation.
- Tách cache region/provider/key strategy theo tenant khi kiến trúc hỗ trợ và đã được kiểm thử.

Không dùng một kết quả query list để kết luận `find(Customer.class,id)` an toàn khi L2 cache bật.

## 26. Cache collection associations

Hibernate có thể cache collection state riêng nếu collection được đánh dấu cacheable và provider hỗ trợ.

~~~java
@OneToMany(mappedBy = "customer")
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "sales.customer-orders"
)
private Set<Order> orders;
~~~

Nếu collection được partition theo tenant, kiểm tra:

- Owner entity identity có tenant dimension không.
- Collection cache key có giữ tenant identity không.
- Association rows có tenant column/constraint phù hợp.
- Collection invalidation khi thêm/xóa child.
- Native/bulk DML có làm collection cache stale không.
- Request B không nhận collection đã warm bởi A.

Nếu không chắc, disable collection cache cho tenant-sensitive associations cho tới khi có test chứng minh an toàn.

## 27. Evict cache đúng phạm vi trong test

Hibernate Cache API có thể evict entity/collection/query regions theo nhiều cấp. Ví dụ:

~~~java
SessionFactory sessionFactory = ...;

sessionFactory.getCache()
    .evictEntityData(Customer.class);

sessionFactory.getCache()
    .evictCollectionData(Customer.class.getName() + ".orders");

sessionFactory.getCache()
    .evictQueryRegions();
~~~

Tên collection role là `entityName.collectionName` và cần khớp mapping thực tế. API có overload theo entity ID/region tùy version.

Dùng eviction để cô lập test hoặc xử lý cache invalidation có chủ đích; **không gọi evict-all sau mỗi request** để né lỗi isolation. Eviction có thể che một cache-key bug thay vì sửa nguyên nhân.

## 28. Cache invalidation sau update

Test chu trình:

1. Tenant A load Customer vào L2.
2. Transaction mới cập nhật Customer.
3. Commit.
4. Session thứ ba load lại.
5. Kiểm tra giá trị mới.
6. Tenant B load cùng key/local ID.
7. Kiểm tra không nhận dữ liệu A.

Concurrency strategy ảnh hưởng semantics:

- `READ_ONLY`: phù hợp dữ liệu bất biến/không update.
- `READ_WRITE`: phối hợp cache locking/soft locks theo provider.
- `NONSTRICT_READ_WRITE`: chấp nhận cửa sổ stale data.
- `TRANSACTIONAL`: phụ thuộc cache provider/transaction integration.

Chọn strategy theo consistency requirement và provider thực tế. Đừng dùng cache mode như biện pháp authorization.

## 29. Native SQL có thể bypass filter/tenant restriction

Ví dụ:

~~~java
entityManager.createNativeQuery(
    "select * from customer where id = :id"
)
.setParameter("id", id)
.getResultList();
~~~

Native SQL do ứng dụng viết không được giả định sẽ tự nhận mọi entity-level `@Filter` hoặc discriminator predicate như HQL do Hibernate sinh.

Nếu dùng native SQL:

- Thêm tenant predicate tường minh khi cần.
- Bind tenant ID từ authenticated server-side context.
- Không lấy tenant ID từ input chưa được xác thực.
- Kiểm tra SQL views/RLS/database permissions.
- Test cả read và mutation.
- Xem native query có map entity/cache state không.

Một native query chỉ thiếu `tenant_id` có thể trở thành đường rò dữ liệu dù tất cả JPQL repositories đều đúng.

## 30. Bulk HQL/JPQL DML và tenant isolation

Bulk mutation:

~~~java
int changed = entityManager.createQuery(
    """
    update Customer c
    set c.active = false
    where c.lastSeenAt < :cutoff
    """
)
.setParameter("cutoff", cutoff)
.executeUpdate();
~~~

Với multi-tenancy discriminator, Hibernate có thể bổ sung tenant restriction trong một số ORM-generated mutation paths theo mapping/version. Nhưng không tự giả định mọi HQL/native/bulk query được bảo vệ giống entity dirty checking.

Test SQL generated và row counts. Nếu business command chỉ được tác động tenant hiện tại, predicate/tenant strategy phải được xác nhận ở DB. Bulk DML cũng bypass per-entity callbacks/dirty checking và có thể làm L1/L2/query cache stale.

## 31. Schema-per-tenant isolation

Với schema-per-tenant:

~~~text
tenant_A.customer
tenant_A.orders

tenant_B.customer
tenant_B.orders
~~~

Tenant routing có thể được thực hiện qua `MultiTenantConnectionProvider` hoặc integration tương ứng. Khi lấy connection từ pool, hệ thống phải chọn schema đúng.

Test cần kiểm tra:

- Session A lấy connection/schema A.
- Session B lấy connection/schema B.
- Một connection được trả pool rồi tái sử dụng không giữ schema trước đó.
- `search_path`/schema state được reset khi release connection.
- Transaction rollback không để session setting rò sang borrower tiếp theo.
- Migration được chạy trên mọi tenant schema.
- Native SQL không hard-code schema khác.

Schema separation không tự an toàn nếu connection pool session state bị rò hoặc routing resolver trả tenant sai.

## 32. Database-per-tenant isolation

Với database-per-tenant:

- Tenant resolver chọn database/connection provider.
- Credentials/connection pools có thể riêng hoặc được quản lý theo strategy.
- Migrations phải đồng bộ.
- Failover/rotation/connection limits cần được quản lý.
- Background job phải mở Session bằng tenant identifier đúng.

Test một tenant không thể query nhầm DB của tenant khác. Dùng dữ liệu marker khác nhau trong từng database và assert cả connection metadata/schema/database identity khi phù hợp.

Không chỉ kiểm tra resolver trả chuỗi tenant đúng; phải xác minh **connection thực tế** trỏ tới database đúng.

## 33. Pooled connection và session state leakage

Database session có thể giữ state như:

- Current schema/search_path.
- Role.
- Session variables.
- Timezone.
- RLS context variables.
- Temporary tables.
- Isolation/session settings.

Nếu connection được trả pool mà không reset state, request tiếp theo có thể kế thừa tenant A settings trong request B.

Một integration test nên:

1. Mượn connection dưới tenant A.
2. Đặt schema/tenant session state theo cách ứng dụng dùng.
3. Trả connection.
4. Mượn lại connection (cố tình pool size nhỏ để dễ reuse).
5. Xác nhận tenant B nhận state đúng và không còn A.
6. Lặp cả khi exception/rollback xảy ra.

Ưu tiên transaction-local settings nếu DB hỗ trợ và đảm bảo cleanup ở mọi paths. Không dùng `SET` session-level mà thiếu reset.

## 34. Row-level security là lớp DB riêng

PostgreSQL Row-Level Security có thể enforce tenant predicate ở database:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_orders_policy
ON orders
USING (tenant_id = current_setting('app.tenant_id')::text)
WITH CHECK (tenant_id = current_setting('app.tenant_id')::text);
~~~

Đây là ví dụ minh họa; cần xử lý `missing_ok`, role bypass, connection/session variables, migration owner privileges và transaction context.

Test:

- Role ứng dụng có RLS thực sự được áp dụng không.
- Tenant A không SELECT/UPDATE/INSERT row B.
- Không dùng superuser/BYPASSRLS trong application tests.
- Tenant context được đặt trước query và reset đúng.
- Connection pool không mang session variable của request trước.
- Native SQL cũng chịu policy.
- Error/rollback paths không bỏ quên cleanup.

RLS là defense-in-depth hữu ích; Hibernate filter không thay thế nó.

## 35. Tenant context và thread-local

Nhiều ứng dụng dùng context holder:

~~~java
public final class TenantContext {

    private static final ThreadLocal<String> CURRENT =
        new ThreadLocal<>();

    public static void set(String tenantId) {
        CURRENT.set(tenantId);
    }

    public static String requireTenantId() {
        String tenantId = CURRENT.get();
        if (tenantId == null) {
            throw new IllegalStateException("Tenant context missing");
        }
        return tenantId;
    }

    public static void clear() {
        CURRENT.remove();
    }
}
~~~

HTTP filter/interceptor có thể set context sau authentication và clear trong `finally`.

~~~java
try {
    TenantContext.set(authenticatedTenantId);
    chain.doFilter(request, response);
} finally {
    TenantContext.clear();
}
~~~

Không lấy tenant context từ header thô mà chưa authorize. Dùng `remove()` để tránh thread pool reuse làm rò tenant ID sang request kế tiếp.

## 36. Async executor không tự mang tenant context

~~~java
TenantContext.set("tenant-A");

executor.execute(() -> {
    // Không giả định TenantContext ở đây là tenant-A.
});
~~~

Thread pool có threads riêng và có thể giữ context từ task trước nếu cleanup sai.

Cách an toàn:

- Truyền tenant ID tường minh vào command/task đã được authorize.
- Dùng context propagation mechanism phù hợp Spring/Micrometer.
- Set context ở đầu task và clear trong `finally`.
- Không truyền EntityManager/Session sang thread khác.
- Mở transaction và Session mới trong worker.
- Test exception/rejection/cancellation paths.

Trace context propagation và tenant context propagation là hai việc riêng; một cái được truyền đúng không chứng minh cái kia đúng.

## 37. Message consumer và scheduled jobs

Một message có thể chứa tenant identifier để định tuyến, nhưng consumer vẫn phải xác minh nguồn và hợp đồng message.

~~~java
public void handle(OrderEvent event) {
    String tenantId = tenantResolver.resolveAuthorizedTenant(event);

    try {
        TenantContext.set(tenantId);
        processInNewTransaction(event);
    } finally {
        TenantContext.clear();
    }
}
~~~

`resolveAuthorizedTenant` là logic ứng dụng cần triển khai. Không tin payload tenantId nếu producer/transport không được xác thực.

Với scheduled jobs, chạy loop theo tenants:

- Mở Session/transaction riêng từng tenant/chunk.
- Không giữ một Session xuyên tenants.
- Ghi checkpoint kèm tenant ID.
- Retry chỉ trong tenant scope tương ứng.
- Metrics/logs ghi tenant pseudonymous hoặc low-cardinality category, tránh cardinality explosion.

## 38. Test tenant isolation qua HTTP boundary

Integration test nên gọi API với credentials/token của từng tenant, không chỉ gọi repository trực tiếp.

Ví dụ:

~~~text
GET /api/customers/1
Authorization: Bearer token-A
-> customer của tenant A

GET /api/customers/1
Authorization: Bearer token-B
-> customer của tenant B hoặc 404/403 theo API contract
~~~

Test các trường hợp:

- Tenant A đọc resource A: thành công.
- Tenant B đọc resource A: bị từ chối/không tìm thấy theo policy.
- Tenant B sửa resource A: không thay đổi DB.
- Tenant A không thể gán association tới resource B.
- Missing/invalid tenant context: fail closed.
- Request lỗi vẫn clear context trước request kế tiếp.
- Cache warm bởi A không làm B thấy dữ liệu A.

404 hay 403 là quyết định API/security policy; điều quan trọng là không lộ data và không tạo side effect.

## 39. Test query cache bằng hai tenant và cùng parameters

Một kịch bản tối thiểu:

~~~java
@Test
void queryCacheDoesNotMixTenants() {
    List<Customer> a = runCachedQuery("tenant-A", "ACTIVE");
    List<Customer> b = runCachedQuery("tenant-B", "ACTIVE");

    assertThat(a).allMatch(c -> c.getTenantId().equals("tenant-A"));
    assertThat(b).allMatch(c -> c.getTenantId().equals("tenant-B"));
}
~~~

`runCachedQuery` phải mở Session/EntityManager tenant-specific, enable cacheable query và đóng context sau mỗi lần.

Để test tốt hơn:

1. Warm cache bằng A.
2. Chạy B lần đầu.
3. Chạy A lần nữa.
4. Chạy B lần nữa.
5. Kiểm tra identifiers, names và query-cache hit/miss counts.
6. Lặp với cùng local ID ở hai tenants.
7. Lặp sau update/eviction.

Không chỉ assert size; hai tenants có thể cùng số rows nhưng dữ liệu bị tráo.

## 40. Test L2 cache qua tenant switch

Kịch bản:

~~~text
1. Session tenant-A: load entity ID 1, warm L2.
2. Close Session A.
3. Session tenant-B: load entity ID 1.
4. Assert B nhận đúng row B hoặc not-found theo schema.
5. Inspect L2 hit/miss and SQL logs.
6. Reverse order: warm B, then load A.
~~~

Đây là test quan trọng nếu ID chỉ unique trong tenant hoặc manual filter được dùng.

Nếu dùng Hibernate `@TenantId`/native multi-tenancy, xác minh tenant identifier thực sự đi vào cache identity. Nếu dùng filter tự viết, đừng mặc định L2 cache hiểu filter parameter; cân nhắc disable L2 hoặc thiết kế key/identifier tenant-aware.

## 41. Test L1 cache và filter parameter thay đổi

Với manual filter, tạo test negative để minh họa tại sao không được đổi tenant trong cùng Session:

~~~java
try (Session session = sessionFactory.openSession()) {
    session.enableFilter("tenantFilter")
        .setParameter("tenantId", "tenant-A");

    Customer a = loadCustomer(session, idA);

    // Không đổi sang tenant-B và tiếp tục dùng Session này.
    // Đây là cách dùng sai cần bị loại khỏi production design.
}
~~~

Test đúng nên mở Session B riêng. Nếu muốn kiểm tra guard của ứng dụng, có thể thêm assertion rằng tenant context không thể đổi trong khi persistence context còn active.

Không viết test mong Hibernate tự detach hoặc lọc lại mọi object L1 khi filter parameter đổi; đó không phải contract an toàn.

## 42. Test filter trên association và load-by-key

Tạo graph:

~~~text
Tenant A Customer 1
    └── Order 10
          └── Lines ...

Tenant B Customer 1
    └── Order 10
          └── Lines ...
~~~

Với từng tenant Session, test:

- Query root entity.
- `find()` by ID.
- `getReference()` + initialize.
- Load to-one Customer.
- Load one-to-many Orders/Lines.
- Fetch join.
- EntityGraph.
- Collection cache nếu bật.

Đặc biệt với `@FilterDef(applyToLoadByKey=true)` nếu version hỗ trợ, kiểm tra option có hiệu lực đúng cho direct fetch paths. Test không nên dựa vào một association duy nhất để kết luận toàn bộ graph an toàn.

## 43. Test native SQL và JDBC bypass

Viết negative/control test:

~~~java
List<?> unsafe = entityManager.createNativeQuery(
    "select id, tenant_id, name from customer"
).getResultList();
~~~

Câu SQL này cố tình không có tenant predicate. Nếu database RLS không bật, nó có thể trả rows nhiều tenants. Đây là cách chứng minh ORM filter không phải DB security boundary.

Sau đó test query có bind predicate:

~~~java
List<?> safe = entityManager.createNativeQuery(
    """
    select id, tenant_id, name
    from customer
    where tenant_id = :tenantId
    """
)
.setParameter("tenantId", authenticatedTenantId)
.getResultList();
~~~

Trong production, ưu tiên database RLS/permissions khi cần enforce mọi SQL paths. Đừng lặp tenant ID từ request body; lấy từ trusted authenticated context.

## 44. Test bulk mutation và affected row count

Một bulk UPDATE không có tenant predicate có thể ảnh hưởng nhiều tổ chức:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE created_at < :cutoff;
~~~

Test cần kiểm tra:

- Tenant A chỉ update A.
- Tenant B không bị thay đổi.
- Row count bằng số records đúng tenant.
- Lỗi/rollback không để partial unintended writes.
- L1/L2/query cache được clear/evict khi bulk DML bypass ORM state.
- SQL generated có tenant condition theo strategy/version.

Đối với native DML, thêm tenant predicate rõ và DB policy. Đối với ORM-generated HQL, xác nhận SQL thực tế của Hibernate version đang dùng.

## 45. Test cache invalidation sau native/bulk DML

Native SQL và bulk DML có thể bypass managed entity lifecycle. Nếu cache được bật:

1. Warm L2 entity cache.
2. Warm query cache.
3. Update row bằng native SQL hoặc bulk HQL.
4. Mở Session mới.
5. Kiểm tra entity state.
6. Kiểm tra query results.
7. Thử evict entity/collection/query region theo policy.
8. Lặp ở tenant khác.

Không dùng eviction toàn cục như một cách che giấu invalidation bug. Xác định cache region nào bị ảnh hưởng và cơ chế invalidate phù hợp. Hibernate có thể biết một số query spaces của HQL nhưng không nhất thiết biết external SQL chạy từ một connection khác.

## 46. Cache invalidation và transaction commit

Không coi cache update/eviction hoàn tất trước khi transaction commit. Cache concurrency strategy/provider có transaction coordination riêng.

Test:

- Transaction A update nhưng chưa commit.
- Transaction B đọc.
- Transaction A commit/rollback.
- Session C đọc lại.
- Quan sát L2 state và DB state theo isolation/cache strategy.

Nếu dùng `READ_WRITE`, `NONSTRICT_READ_WRITE` hay `TRANSACTIONAL`, expected consistency khác nhau. Đừng viết test yêu cầu linearizable reads từ một strategy được cấu hình chỉ eventual/non-strict.

## 47. Test schema-per-tenant connection routing

Với schema A/B, tạo cùng table name nhưng data marker khác nhau:

~~~sql
CREATE SCHEMA tenant_a;
CREATE SCHEMA tenant_b;

CREATE TABLE tenant_a.marker (value VARCHAR(40));
CREATE TABLE tenant_b.marker (value VARCHAR(40));

INSERT INTO tenant_a.marker VALUES ('A');
INSERT INTO tenant_b.marker VALUES ('B');
~~~

Qua connection provider/session của tenant A/B, query marker và assert đúng kết quả.

Sau đó test reuse cùng pooled connection nếu có thể:

- A query.
- Release connection.
- B query.
- A query lại.
- Force exception/rollback giữa các lần.
- Kiểm tra schema/session state sau release.

Chỉ test resolver string là chưa đủ; cần test connection thật và schema thật.

## 48. Test database-per-tenant routing

Dùng hai DB/container hoặc hai database trong cùng PostgreSQL container:

- Tenant A database có marker `A`.
- Tenant B database có marker `B`.
- Tenant resolver map đúng tenant → datasource/provider.
- Mở Session từng tenant.
- Xác nhận connection metadata/marker.
- Thử tenant không tồn tại: fail closed.
- Thử provider error: không fallback sang default tenant một cách im lặng.

Không cấu hình default tenant tùy tiện trong production; fallback có thể biến lỗi missing context thành truy cập nhầm tổ chức.

## 49. Test connection pool state reset

Nếu dùng PostgreSQL `search_path` hoặc RLS session variables:

- Xác định state được đặt bằng `SET`, `SET LOCAL` hay connection init SQL.
- Xác nhận state có reset khi connection được trả pool.
- Test cả exception và transaction rollback.
- Cố tình cấu hình pool nhỏ để reuse connection.
- Chạy song song hai tenant và kiểm tra không cross-talk.
- Không để test chỉ chạy tuần tự nếu production concurrency là yếu tố chính.

Một lỗi session-state leak có thể hiếm khi xuất hiện ở unit test nhưng gây data leak dưới tải thật.

## 50. Test concurrency giữa tenants

Dùng barrier/latch để tạo interleaving:

~~~text
Thread A: set tenant-A -> open Session A -> wait
Thread B: set tenant-B -> open Session B -> query
Thread A: resume -> query
Thread B: finish -> clear context
Thread A: finish -> clear context
~~~

Assertions:

- Mỗi thread giữ tenant context riêng.
- Session được mở dưới đúng tenant.
- Không dùng shared EntityManager/Session.
- Không rò ThreadLocal sau khi task hoàn tất.
- Request B không đọc marker của A.
- Exception/cancellation không bỏ qua cleanup.

Test phải kiểm soát executor và cleanup; không dùng `Thread.sleep()` để hy vọng tạo race condition ổn định.

## 51. Test missing tenant context phải fail closed

Nếu `TenantContext` không có tenant:

~~~java
assertThrows(
    IllegalStateException.class,
    () -> tenantResolver.resolveCurrentTenantIdentifier()
);
~~~

Không tự chọn tenant mặc định trong ứng dụng multi-tenant nhạy cảm trừ khi đó là explicit system tenant có policy riêng.

Test:

- Request không có tenant claim.
- Token không có quyền tenant.
- Tenant ID không tồn tại.
- Background task thiếu context.
- Consumer nhận event không hợp lệ.
- Resolver ném exception.
- Không có connection/session nào được route sang tenant mặc định ngoài ý muốn.

## 52. Test tenant context không bị rò sau exception

~~~java
try {
    TenantContext.set("tenant-A");
    service.process();
} finally {
    TenantContext.clear();
}
~~~

Test giả lập `service.process()` ném exception, sau đó dùng cùng executor thread cho task B và xác nhận context B được set từ đầu, không còn A.

Có thể dùng executor đơn luồng để ép reuse cùng worker thread trong test. Đây là cách phát hiện ThreadLocal leak tốt hơn test tạo thread mới mỗi lần.

## 53. Test với Testcontainers và production-like database

H2 có thể phù hợp test JPA cơ bản, nhưng không đủ đại diện cho mọi multi-tenancy/cache semantics:

- Schema switching và `search_path`.
- RLS policies.
- Native SQL/dialect.
- Composite FKs/partial indexes.
- Session variables.
- Timestamp/locking behavior.
- JDBC connection pool state.
- Database-specific cache/query invalidation interactions.

Dùng Testcontainers với cùng DB engine/version gần production. Nếu production dùng PostgreSQL, test schema, RLS, native SQL và pool trên PostgreSQL thay vì chỉ H2.

Cache provider cũng phải giống hoặc gần production; test bằng provider in-memory đơn giản không chứng minh cluster/distributed cache behavior.

## 54. Ví dụ cấu trúc integration test Spring

Một test có thể dùng `@SpringBootTest` hoặc `@DataJpaTest` với Testcontainers:

~~~java
@Testcontainers
@SpringBootTest
class TenantIsolationIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // Configure datasource/container and run real migrations.
    // Open tenant-specific sessions or request contexts.
}
~~~

Spring Boot/Testcontainers wiring có thể dùng `@DynamicPropertySource` hoặc `@ServiceConnection` tùy version. Đảm bảo test chạy migrations thật và Hibernate schema validation đúng.

Nếu test transaction tự rollback cuối method, điều đó có thể che commit/cache behavior. Với L2/query cache, hãy tạo transaction fixture commit rõ ràng, sau đó mở Session mới cho assertions.

## 55. Test L2 cache bằng statistics

Hibernate Statistics có thể giúp quan sát:

~~~java
Statistics stats = sessionFactory.getStatistics();
stats.clear();

loadInTenant("tenant-A", customerId);
loadInTenant("tenant-A", customerId);

long hits = stats.getSecondLevelCacheHitCount();
long misses = stats.getSecondLevelCacheMissCount();
long queryHits = stats.getQueryCacheHitCount();
long queryMisses = stats.getQueryCacheMissCount();
~~~

Các methods/metrics và statistics APIs có thể khác giữa Hibernate versions. Bật statistics trong test profile; chúng có overhead và là SessionFactory-wide counters.

Kết hợp statistics với SQL logs và result assertions. Một cache hit không chứng minh đúng tenant; phải kiểm tra nội dung trả về.

## 56. Test invalidation theo từng cache region

Khi cập nhật Customer:

- Entity region `customers`.
- Collection region `customer-orders`.
- Query region `active-customers`.
- Natural ID cache nếu có.
- Cache region khác chứa dependent data.

Kiểm tra update qua ORM và update qua native SQL riêng. Một bulk/native path có thể cần explicit eviction; không assume Hibernate biết external writer đã thay đổi rows.

Tránh dùng một `evictAllRegions()` trong mọi test setup nếu bài test cần xác nhận cache hit hoặc invalidation. Chỉ evict đúng region ở fixture boundary khi có chủ đích.

## 57. Natural ID cache cũng cần tenant-aware tests

Nếu entity dùng `@NaturalId`:

~~~java
@NaturalId
@Column(name = "external_code")
private String externalCode;
~~~

và `external_code` chỉ unique trong từng tenant, schema constraint nên là:

~~~sql
UNIQUE (tenant_id, external_code)
~~~

Test `byNaturalId()` dưới tenant A/B với cùng external code, warm natural-ID cache từ A rồi load B.

Không khai báo một business key là globally unique nếu domain chỉ bảo đảm uniqueness per tenant. Cache và natural-ID lookup phải phù hợp identity model thật.

## 58. Cache region naming và operational isolation

Có thể đặt region names rõ:

~~~java
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "tenant-data.customers"
)
~~~

Region name tự nó không tách tenants. Nếu tất cả tenants dùng cùng region, cache key/provider phải có tenant dimension phù hợp.

Nếu chọn region riêng theo tenant, phải đánh giá số lượng regions, memory, eviction, cluster invalidation và lifecycle khi tenant mới/xóa. Không tạo region tùy ý theo request nếu cache provider không được thiết kế cho cardinality đó.

## 59. Negative tests là bằng chứng quan trọng

Bên cạnh happy path, tạo tests cố tình truy cập chéo:

| Thao tác | Tenant A | Tenant B thử truy cập A |
|---|---|---|
| Query list | Chỉ thấy A | Không thấy A |
| Find by ID | Load A | Not found/denied theo contract |
| To-one association | Target A | Không resolve target A |
| Collection | Children A | Không thấy children A |
| Query cache | Kết quả A | Không nhận kết quả A |
| L2 cache | Entity A | Không nhận state A |
| Native SQL | Có tenant predicate/RLS | Không bypass policy |
| Bulk update | Chỉ sửa A | Không sửa A |
| Insert FK | Liên kết A→A | Không thể liên kết A→B |
| Async task | Context A | Không rò context sang B |

Đừng chỉ assert exception. Hãy kiểm tra DB state sau test để chắc chắn thao tác thất bại không tạo side effects.

## 60. Đo và quan sát cache/filter behavior

Các tín hiệu hữu ích:

- Hibernate L2 cache hits/misses/puts.
- Query cache hits/misses/puts.
- Entity/collection load counts.
- SQL query counts và durations.
- Connection pool active/pending/acquire.
- Tenant routing/connection schema metadata.
- Filter enabled state ở boundary nếu có instrumentation.
- Error counts theo tenant category (low cardinality).
- Cross-tenant authorization denials.

Không đưa tenant ID không giới hạn vào metric labels. Dùng structured logs/traces có access controls và pseudonymous tenant key nếu cần điều tra.

## 61. SQL logging để xác nhận tenant predicate

Trong test:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Kiểm tra:

- SELECT có `tenant_id` predicate không.
- INSERT có tenant_id đúng không.
- UPDATE/DELETE có tenant restriction không.
- Lazy association load có tenant condition không.
- Schema/database routing có trỏ đúng không.
- Native SQL có tự thiếu tenant condition không.

Bind logs có thể lộ dữ liệu nhạy cảm; chỉ dùng dữ liệu giả hoặc redaction trong test/staging. SQL log không phải cơ chế bảo vệ và không thay negative tests.

## 62. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ test query list | Bỏ sót find/association/cache | Test toàn bộ load paths |
| Đổi filter tenant trong cùng Session | L1 vẫn giữ objects cũ | Session mới mỗi tenant |
| Nghĩ filter parameter luôn nằm trong entity cache key | Có thể cache cross-scope | Tenant-aware identity hoặc tắt L2 |
| Chỉ warm cache một tenant | Không phát hiện A/B collision | Test warm A rồi B và đảo chiều |
| Dùng H2 cho schema/RLS tests | Không tái hiện DB semantics | Testcontainers DB production-like |
| Native SQL không tenant predicate | Lộ dữ liệu | RLS/explicit trusted predicate |
| Bulk update không scope tenant | Sửa nhiều tổ chức | Test affected rows và DB policy |
| ThreadLocal không clear | Tenant context leak | try/finally + reuse-thread test |
| Async dùng Session của caller | Session không thread-safe | Session/transaction mới |
| Pooled connection giữ search_path cũ | Query tenant sai schema | Reset/transaction-local state |
| Cache eviction toàn cục để né lỗi | Che invalidation bug | Test đúng region/key lifecycle |
| Chỉ assert result count | Có thể trả nhầm tenant rows cùng số lượng | Assert tenant marker/business values |
| Missing tenant fallback default | Truy cập nhầm tổ chức | Fail closed |
| FK chỉ theo customer_id | Association cross-tenant | Composite FK tenant_id + id |
| Tin trace/tenant header từ client | Spoof tenant | Resolve từ authenticated principal |

## 63. Runbook điều tra nghi ngờ rò dữ liệu qua cache

1. Ghi nhận request, tenant context, resource ID và thời điểm.
2. Xác định tenant từ authenticated principal, không chỉ từ header/log.
3. Kiểm tra Session/EntityManager được mở với tenant nào.
4. Xác định dữ liệu đến từ L1, L2, query cache hay SQL.
5. Lấy SQL/bind values đã redact và kiểm tra tenant predicate.
6. Tạm evict đúng cache region trong môi trường kiểm soát để xác định cache có liên quan không; không xem đây là fix.
7. Chạy lại A→B và B→A bằng Sessions mới.
8. Kiểm tra direct find, proxy, to-one, collections và native/bulk paths.
9. Kiểm tra connection routing/schema/session state.
10. Kiểm tra DB constraints/RLS và raw rows.
11. Thêm regression test tái hiện đường truy cập gây lỗi.
12. Nếu có khả năng data exposure thật, thực hiện incident/security response theo quy trình của tổ chức.

## 64. Checklist trước khi bật cache trong multi-tenant system

**Tenant context**

- [ ] Tenant được xác thực từ identity/authorization context?
- [ ] Mỗi Session có một tenant cố định?
- [ ] Missing tenant fail closed?
- [ ] ThreadLocal được clear trong finally?
- [ ] Async/consumer/scheduled jobs mở Session riêng?
- [ ] Connection/schema state được reset?

**ORM filters và multi-tenancy**

- [ ] Đã chọn rõ `@TenantId`, filter hay schema/database strategy?
- [ ] Load-by-ID/to-one behavior đã test?
- [ ] `applyToLoadByKey` được kiểm tra theo đúng Hibernate version nếu dùng?
- [ ] Native SQL và bulk DML có tenant policy?
- [ ] Association/collection/join tables có tenant integrity?
- [ ] Composite unique/FK constraints phù hợp?

**Cache**

- [ ] L1 không chia sẻ giữa tenants?
- [ ] L2 entity key có tenant dimension nếu cần?
- [ ] Manual filter + L2 cache được chứng minh an toàn hoặc cache bị tắt?
- [ ] Query cache tách tenant/filter parameters?
- [ ] Collection/natural ID cache đã test?
- [ ] Update/native DML invalidation rõ?
- [ ] Cache provider/config giống production đủ mức cần thiết?

**Kiểm thử**

- [ ] A→B và B→A warm-cache tests?
- [ ] Same local ID ở hai tenants?
- [ ] Query list, find, proxy, association và collection?
- [ ] Native SQL và bulk update/delete?
- [ ] Concurrent requests/pooled connection reuse?
- [ ] RLS/connection routing trên DB thật nếu dùng?
- [ ] DB state assertions sau unauthorized write?

## 65. Bài tập thực hành

1. Tạo hai tenants có cùng local customer ID nhưng tên khác; kiểm tra query và find bằng Sessions riêng.
2. Bật L2 cache cho Customer; warm tenant A rồi load tenant B, kiểm tra entity cache hit/miss và dữ liệu.
3. Tạo manual `@Filter` theo tenantId; test load-by-ID với `applyToLoadByKey` nếu version hỗ trợ.
4. Bật query cache cho cùng HQL, chạy lần lượt A/B/A/B với cùng parameters và assert exact tenant values.
5. Cache một collection Customer.orders; thử load collection của tenant khác.
6. Tạo native SQL thiếu tenant predicate và chứng minh ORM filter không tự rewrite query text.
7. Viết bulk update rồi kiểm tra row count/DB state của cả hai tenants.
8. Tạo composite FK tenant_id/customer_id và thử insert cross-tenant association.
9. Cấu hình schema-per-tenant; test pooled connection reuse và reset search_path.
10. Dùng Testcontainers PostgreSQL để test RLS dưới application role không phải superuser.
11. Dùng executor đơn luồng, cố tình ném exception trong tenant A task, sau đó chạy tenant B task để phát hiện ThreadLocal leak.
12. Chạy hai tenants đồng thời bằng latches; xác nhận không có Session/tenant context sharing.
13. Test cache invalidation sau ORM update và native SQL update.
14. Thêm negative API test: token B đọc/sửa resource A phải không thành công và DB không thay đổi.
15. Mô phỏng cache region riêng theo tenant và đánh giá memory/cardinality trade-offs.

## 66. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Ứng dụng nhiều tổ chức cần bật cache"] --> B{"Tenant isolation được thực hiện ở đâu?"}
    B -- "Hibernate discriminator" --> C["@TenantId / tenant-aware Session"]
    B -- "Manual tenant filter" --> D["@Filter + trusted tenant parameter"]
    B -- "Schema/database" --> E["Connection routing + reset state"]
    C --> F{"L2/query cache bật?"}
    D --> F
    E --> F
    F -- "Không" --> G["Test L1, SQL, tenant boundaries"]
    F -- "Có" --> H["Test tenant-aware cache keys"]
    H --> I["Warm A -> load B -> warm B -> load A"]
    G --> J["Test find, associations, native, bulk"]
    I --> J
    J --> K["Test concurrency, pool reuse, RLS/constraints"]
    K --> L["Chỉ bật production khi negative tests pass"]
~~~

## 67. Tài liệu đối chiếu chính thức

- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — second-level cache, query cache, filters, multi-tenancy và tenant identifier.
- [Hibernate ORM Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/) — `@TenantId`, `@FilterDef`, `@Filter`, cache annotations và SessionBuilder APIs theo version.
- [Hibernate ORM Introduction](https://docs.hibernate.org/orm/current/introduction/html_single/) — persistence context, Session lifecycle và multi-tenancy concepts.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — EntityManager, persistence context, caching hints và mapping contracts.
- [Testcontainers Documentation](https://java.testcontainers.org/) — database containers cho integration testing.
- [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS policies, USING/WITH CHECK và role behavior.
- [PostgreSQL Connection Settings](https://www.postgresql.org/docs/current/runtime-config-client.html) — session settings/timezone và connection behavior.

Các trang `current` có thể mô tả Hibernate mới hơn ứng dụng. Kiểm tra Javadocs của đúng minor version, đặc biệt với `@TenantId`, `applyToLoadByKey`, cache provider và tenant connection APIs.

## 68. Tổng kết

**Kiểm thử cache, filter và tenant isolation phải xác minh dữ liệu không thể vượt qua ranh giới tổ chức trên mọi đường truy cập.**

- **L1 cache** gắn với một Session; không đổi tenant context hoặc chia sẻ Session giữa tenants.
- **L2 cache** xuyên Sessions; chỉ bật cho tenant data khi cache identity/key thực sự giữ tenant dimension hoặc có chiến lược an toàn đã được chứng minh.
- **Query cache** cần được test với cùng query/parameters nhưng tenant và filter values khác nhau.
- **Manual `@Filter`** có thể lọc ORM queries nhưng load-by-ID, associations và cache cần test riêng; không dùng filter làm security boundary.
- **`@TenantId` và Hibernate multi-tenancy** giúp tenant identifier tham gia ORM identity/loading/cache semantics theo version; vẫn cần kiểm soát native SQL và connection routing.
- **Schema/database-per-tenant** phải test pooled connection reuse, schema reset và routing thật.
- **Database constraints/RLS** có thể cung cấp lớp bảo vệ vượt ngoài ORM; test dưới đúng application role.
- **Async/message jobs** cần tenant context được truyền có chủ đích và Session/transaction mới.
- **Negative tests** A→B, B→A, same ID, cache warm-up, native/bulk writes và concurrency là bằng chứng quan trọng nhất.

Hãy kiểm tra theo thứ tự **tenant authentication → Session boundary → SQL/filter → cache key/hit → association/native paths → database constraints → pooled connection/async context**. Chỉ một query list trả đúng dữ liệu không chứng minh toàn bộ ứng dụng được phân lập an toàn.
