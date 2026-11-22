# Quản lý cache khi triển khai hoặc thay đổi dữ liệu ngoài ứng dụng

Trong ứng dụng dùng Java Persistence API (JPA), cache giúp giảm truy vấn, giảm độ trễ và tiết kiệm tài nguyên cơ sở dữ liệu. Tuy nhiên, cache có thể trở thành nguồn **dữ liệu cũ (stale data)** khi bản ghi được cập nhật không thông qua luồng JPA thông thường: script SQL chạy trong lúc triển khai, Flyway/Liquibase data migration, công cụ quản trị database, ETL/CDC, job JDBC, microservice khác, bulk UPDATE hoặc một quá trình nhập dữ liệu định kỳ.

Xét ví dụ vận hành:

```text
10:00  Node A đọc Product#42, price=100000 VND.
       Product#42 có thể được lưu trong L2 cache.
10:05  Nhóm vận hành chạy SQL:
       UPDATE products SET price=120000 WHERE id=42;
10:06  Node B đọc Product#42 qua JPA.
       Nếu cache chưa được invalidated, node B
       có thể vẫn thấy price=100000.
10:07  Người dùng đặt hàng theo giá cũ.
```

Câu SQL đúng và đã `COMMIT` không bảo đảm mọi lớp cache trong ứng dụng đã được làm mới. Ngược lại, gọi `clear()` trên một `EntityManager` cũng không nhất thiết xóa shared cache của toàn hệ thống. Muốn vận hành an toàn, ta phải nhận diện **loại cache**, **ai sở hữu cache**, **đường ghi dữ liệu nào được quan sát**, **những nút ứng dụng nào còn chạy** và **mức nhất quán mà nghiệp vụ cần**.

Bài **“Quản lý cache khi triển khai hoặc thay đổi dữ liệu ngoài ứng dụng”** thuộc chương **“Vận hành và di trú”** của module **Data Persistence Relational Access ORM JPA**. Bài tập trung vào chiến lược cache invalidation, triển khai nhiều node và rolling deployments, migrations/backfills, dữ liệu thay đổi bằng SQL/JDBC/ETL, phối hợp sự kiện sau commit, optimistic locking, bảo mật multi-tenant, kiểm thử thực tế và runbook xử lý sự cố.

> **Nguyên tắc trọng tâm:** Cache không phải nguồn dữ liệu có thẩm quyền. Đọc nhanh nhưng sai có thể nguy hiểm hơn đọc chậm mà đúng, đặc biệt đối với số dư, quyền truy cập, giá, trạng thái đơn hàng hoặc tồn kho.

## 1. Mục tiêu học tập

Sau bài học, bạn cần có khả năng:

1. Giải thích sự khác nhau giữa **L1 persistence context**, **JPA L2 shared cache**, **Hibernate query cache**, **Spring Cache/Redis** và **cache phía client/CDN**.
2. Xác định một thay đổi từ SQL, JDBC, migration hoặc service khác có thể khiến cache nào lỗi thời.
3. Phân biệt **evict**, **refresh**, **clear**, **invalidate**, **expire**, **namespace/version** và **bypass cache**.
4. Dùng `EntityManager.refresh()`, `EntityManager.clear()` và `EntityManagerFactory.getCache()` đúng phạm vi.
5. Hiểu tại sao `@Version` không tự invalidate cache khi external SQL không cập nhật đúng version.
6. Đưa ra chiến lược cho **data migration, rolling deploy, batch import, CDC pipeline và sửa dữ liệu khẩn cấp**.
7. Thiết kế invalidate **sau commit** và đánh giá điểm yếu của cơ chế chỉ phát sự kiện best-effort.
8. Giữ tenant/authorization boundaries trong các cache keys, evictions và messages.
9. Xử lý race giữa reader/writer/invalidation và giữa node cũ/node mới khi triển khai.
10. Kiểm thử cache bằng database thực, nhiều EntityManager và nhiều application instances, có observability và fallback.

## 2. Mô hình dữ liệu xuyên suốt

Giả sử có một hệ thống bán hàng nhiều tenant, lưu sản phẩm, giá và trạng thái kinh doanh.

```java
package example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_product_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
public class Product {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private String tenantId;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false)
    private String displayName;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ProductStatus status;

    @Version
    @Column(nullable = false)
    private Long version;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Product() {}

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public Long getVersion() { return version; }
    public Instant getUpdatedAt() { return updatedAt; }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        price = newPrice;
    }
}

enum ProductStatus {
    DRAFT, ACTIVE, DISCONTINUED
}
```

Ứng dụng có thể dùng entity này trong:

- Trang danh mục: đọc `displayName`, `price`, `status`.
- Checkout: xác định price snapshot và kiểm tra trạng thái bán.
- Admin panel: cập nhật giá qua `@Transactional` service.
- External ERP: nhập bảng giá qua JDBC/staging tables.
- Flyway migration: sửa tên trạng thái hoặc chuẩn hóa giá.

Các đường ghi đó **không mặc nhiên thông báo cho cùng một hệ thống cache**.

### 2.1. Một thay đổi được “nhìn thấy” hay chưa?

Đối với mỗi read, cần phân biệt:

1. Database transaction đã commit thay đổi chưa?
2. Read query đến **primary hay read replica**?
3. Có persistence context đang giữ entity đã đọc trước đó không?
4. Có shared L2 cache đang giữ state cũ không?
5. Có Hibernate query results cache hoặc framework/application cache giữ response cũ không?
6. HTTP/CDN/browser cache có giữ response cũ không?

Chỉ kiểm tra một tầng không đủ chứng minh toàn hệ thống đã thấy dữ liệu mới.

## 3. Sơ đồ các lớp dữ liệu và cache

```text
Browser / Mobile App
      |
      | HTTP cache / CDN / client state
      v
API Gateway / Application Node A, B, C
      |
      | @Cacheable / Redis / Caffeine
      v
Business Service
      |
      | EntityManager (L1 persistence context)
      v
JPA Provider / Hibernate
      |
      | L2 entity/collection cache
      | optional query-result cache
      v
JDBC Connection / Transaction
      |
      +----> Primary Database
      |
      +----> Read Replica (potential replication lag)

External writers:
  SQL migration / DBA
  JDBC batch / ERP
  ETL / CDC sink
  other service
          |
          v
       Database
          |
          ?    Cache invalidation không tự xảy ra
          v    trên mọi tầng / mọi node
     Application caches
```

### 3.1. Bảng phân loại

| Tầng | Phạm vi thông thường | Cơ chế làm mới | Đặc điểm cần nhớ |
|---|---|---|---|
| JPA L1 | Một `EntityManager` | `refresh`, `detach`, `clear`, đóng EM | Identity map luôn có cho managed entities; không phải tùy chọn tắt như shared cache |
| JPA L2 | Chia sẻ trong một persistence unit/EMF, tùy provider/cache config | `Cache.evict(...)`, `evictAll()`, provider API | Không mặc định đồng bộ với writer ngoài ứng dụng |
| Hibernate query cache | Query results/IDs/scalar values theo provider | Provider-specific invalidation/region eviction | Không nằm trong API portable `jakarta.persistence.Cache` |
| Spring Cache/Redis | Method results/read-model objects, có thể nhiều nodes | `@CacheEvict`, key/version, TTL, explicit delete | Không tự mất khi JPA L2 evict |
| HTTP/CDN/browser | Response theo URL/headers/keys | Cache-Control, ETag, surrogate purge | Không phụ thuộc trực tiếp persistence context |
| Read replica | Bản sao DB, không phải Java cache | Replication catches up / route primary | Dữ liệu cũ dù tất cả JPA caches đã clear |

### 3.2. Không nhầm “L1 cache” với Redis

L1 ở đây là persistence context của JPA, bảo đảm identity nhất quán cho cùng persistent identity trong một EntityManager. Redis là store độc lập, có thể cache DTO/method responses. Cách invalidation của hai lớp **khác nhau hoàn toàn**.

### 3.3. Không có “một lệnh clear mọi cache”

`em.clear()` không xóa Redis, query cache hoặc mọi L2 entries. `emf.getCache().evictAll()` không xóa managed objects trong EntityManagers đang mở, không mặc nhiên xóa Hibernate query regions, Spring Cache hay CDN. Một runbook phải liệt kê từng tier có khả năng trả dữ liệu cũ.

## 4. L1 persistence context: cache của một EntityManager

Một EntityManager giữ managed entity instances trong identity map.

```java
EntityManager em = emf.createEntityManager();
try {
    Product first = em.find(Product.class, 42L);
    Product second = em.find(Product.class, 42L);
    assertSame(first, second);
} finally {
    em.close();
}
```

Lần `find` thứ hai có thể trả cùng object mà không phát SQL. Nếu một DBA cập nhật row trong DB giữa hai lần `find`, object đang managed **không tự thay field**.

### 4.1. Kịch bản stale state

```text
EntityManager A:
  find Product#42 -> price=100000

SQL bên ngoài:
  UPDATE products SET price=120000 WHERE id=42;
  COMMIT;

EntityManager A:
  find Product#42 -> vẫn cùng instance, price=100000
```

Đây là hành vi identity map, không nhất thiết là bug của provider.

### 4.2. `refresh()`

Nếu cần cập nhật state từ database:

```java
Product product = em.find(Product.class, 42L);
em.refresh(product);
BigDecimal refreshedPrice = product.getPrice();
```

`refresh` yêu cầu nạp lại persistent state cho managed entity. Cần thực hiện trong context/lifecycle/transaction và DB isolation phù hợp; **không có nghĩa vượt qua snapshot isolation**. Nếu transaction giữ snapshot REPEATABLE READ, refresh có thể không nhìn thấy commit mới từ transaction khác theo semantics DB.

### 4.3. `refresh` có thể làm mất local edits chưa flush

```java
Product product = em.find(Product.class, 42L);
product.changePrice(new BigDecimal("150000"));
em.refresh(product); // Local pending change có thể bị ghi đè!
```

Không dùng `refresh` vô điều kiện ở giữa command đang sửa entity. Chỉ refresh khi chấp nhận hủy/đồng bộ state theo policy rõ.

### 4.4. `clear()`

```java
em.clear();
Product reloaded = em.find(Product.class, 42L);
```

`clear` detach **tất cả** managed entities của EM hiện tại. Lần `find` tiếp theo sẽ không dùng identity map cũ, nhưng **vẫn có thể đọc L2 cache** nếu shared cache cho phép.

### 4.5. `clear` không phải phép “discard an toàn”

Nếu EM đang có pending entity changes chưa flush, `clear` có thể bỏ những thay đổi chưa đồng bộ. Đừng gọi trong active transaction chỉ để “xóa cache” mà không xem tác động lên unit of work. Có thể dùng transaction boundary mới hoặc xử lý flush trước khi clear **chỉ nếu business commit semantics cho phép**.

### 4.6. `detach(entity)`

`em.detach(product)` chỉ detach entity cụ thể khỏi context. Khi cần làm mới đúng một entity mà muốn tránh detach toàn context, cân nhắc refresh hoặc detach rồi load lại; lưu ý cascade DETACH, pending changes và L2 cache.

### 4.7. EntityManager vòng đời dài tăng rủi ro stale

Extended persistence contexts hoặc tự giữ EntityManager lâu qua nhiều tác vụ khiến cached state tồn tại lâu. Với request-per-transaction setup, một EM thường ngắn đời hơn, nhưng vẫn có stale reads **ngay trong cùng request/transaction** nếu external write xảy ra giữa các reads.

### 4.8. Spring `@PersistenceContext` proxy

Một Spring-managed injected EntityManager thường là proxy được bind vào transaction/current context; gọi `clear` trên proxy có thể ảnh hưởng tất cả managed entities trong transaction hiện tại. Không nghĩ nó chỉ clear một repository method hoặc một Product.

## 5. JPA shared second-level cache

Shared L2 cache giúp nhiều EntityManagers giảm số lần đọc database cho entity data đủ điều kiện. Nó là **tính năng tùy cấu hình/provider**, không nên giả định mọi ứng dụng JPA đều bật.

### 5.1. Các chế độ shared cache

Jakarta Persistence định nghĩa `SharedCacheMode` với các giá trị phổ biến:

| Mode | Ý nghĩa |
|---|---|
| `ALL` | Cho cache tất cả entity types theo policy |
| `NONE` | Không dùng shared entity cache |
| `ENABLE_SELECTIVE` | Chỉ cache các entity types được đánh dấu cacheable |
| `DISABLE_SELECTIVE` | Cache theo mặc định, trừ entity types được tắt |
| `UNSPECIFIED` | Provider quyết định |

Chi tiết và mức hỗ trợ thực tế phụ thuộc provider. Các annotations `@Cacheable(true)`/`@Cacheable(false)` tương tác với mode đang dùng.

### 5.2. Ví dụ cấu hình

```xml
<persistence-unit name="catalogPU">
    <shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
    <!-- classes and provider properties -->
</persistence-unit>
```

```java
@Entity
@Cacheable(true)
public class ProductCategory {
    // Reference data ít thay đổi.
}
```

Trong Hibernate, để L2 cache thực sự hoạt động còn cần cache region factory/provider phù hợp và các cấu hình cụ thể. Chỉ có `@Cacheable(true)` chưa bảo đảm node đã có một shared clustered cache.

### 5.3. L2 cache scope không đương nhiên là cluster-wide

Một node có thể giữ cache trong RAM cục bộ, trong khi node khác có cache riêng. Nếu muốn cluster coherence, cần một cache provider/configuration hỗ trợ invalidation/replication phù hợp hoặc cơ chế event/broadcast. `EntityManagerFactory.getCache()` được gọi trên node A không mặc nhiên xóa L2 cache của node B.

### 5.4. Phân biệt entity cache và collection cache

Cache state của `Product` không đồng nghĩa cache mọi `@OneToMany` associations. Hibernate có collection cache regions riêng tùy mapping/config. Khi SQL bên ngoài thêm một child row, cần xét **collection membership/query results**, không chỉ entity data.

### 5.5. Cache cho dữ liệu ít thay đổi

Danh sách quốc gia, loại sản phẩm hoặc metadata immutable thường phù hợp cache hơn số dư tài khoản, inventory hoặc quyền truy cập cần strong freshness. Quyết định dựa trên business staleness tolerance, không chỉ query frequency.

### 5.6. Hình thức eviction portable

```java
Cache cache = emf.getCache();
cache.evict(Product.class, 42L);
```

`evict` yêu cầu loại **một entity instance** với primary key khỏi shared cache theo JPA. Cần xác nhận physical cache backend/provider thực sự nhận lệnh, và nhớ rằng nó không clear L1 của EMs đang active.

## 6. Các thao tác `jakarta.persistence.Cache` chuẩn

Jakarta Persistence cung cấp interface `Cache` thông qua `EntityManagerFactory.getCache()`.

```java
import jakarta.persistence.Cache;
import jakarta.persistence.EntityManagerFactory;

public class CatalogCacheAdmin {

    private final EntityManagerFactory emf;

    public CatalogCacheAdmin(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public void evictOneProduct(Long productId) {
        emf.getCache().evict(Product.class, productId);
    }

    public void evictAllProducts() {
        emf.getCache().evict(Product.class);
    }

    public void evictAllEntities() {
        emf.getCache().evictAll();
    }

    public boolean mightContainProduct(Long id) {
        return emf.getCache().contains(Product.class, id);
    }
}
```

### 6.1. `evict(Class, primaryKey)`

Phù hợp khi một script hoặc service ngoài JPA đã thay đúng Product#42 và ta biết ID. Scope hẹp giúp giảm cache miss sau invalidation. Nhưng nếu thay child collection hoặc query result, chỉ evict Product entity có thể chưa đủ.

### 6.2. `evict(Class)`

Loại shared-cache instances của một entity type. Hữu ích khi data migration đổi hàng nghìn rows và không thể liệt kê IDs một cách đáng tin. Đổi lại có thể tạo thác cache misses vào DB; cần tính traffic và kế hoạch warmup nếu phù hợp.

### 6.3. `evictAll()`

Loại shared cache data trên persistence unit tương ứng. Đây là **biện pháp tương đối mạnh**, thường dùng cho runbook triển khai toàn cục nếu vùng cache không thể xác định. Nó không tự invalidates application DTO caches, query regions, L1 contexts, replicas hay các EMFs/node khác nếu cache chưa được chia sẻ/coordinated.

### 6.4. `contains(Class, id)` không phải kiểm tra data freshness

`contains` có thể cho biết cache provider đang chứa entity instance theo API semantics, nhưng:

- Có entry không có nghĩa entry **mới**.
- Không có entry không đảm bảo read sẽ từ primary DB (có thể L1/query cache/replica).
- Không phải công cụ validate dữ liệu giữa node A và B.

### 6.5. `evict` không phải một database transaction

Lệnh cache eviction thường không tham gia cùng atomic transaction như SQL UPDATE một cách mặc định. Trong khoảng giữa DB commit và cache invalidate, reads có thể thấy dữ liệu cũ. Phần điều phối phía sau sẽ xử lý trade-off này.

### 6.6. Evict đúng persistence unit

Ứng dụng có nhiều `EntityManagerFactory` cho nhiều datasources/persistence units cần gọi đúng factory. Evict ở PU cho catalog không làm mới cache của PU cho billing nếu đó là các cache khác nhau.

## 7. Cache retrieve/store modes theo từng thao tác

JPA chuẩn có cache modes để yêu cầu provider tương tác với shared cache như thế nào.

### 7.1. `CacheRetrieveMode.BYPASS`

```java
Product product = em.find(
    Product.class,
    42L,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
```

Ý định là **bỏ qua L2 cache** khi retrieve theo mode. Tuy nhiên nếu `Product#42` đã managed trong L1 của **chính EM**, `find` vẫn có thể trả managed instance đó. Muốn một DB read mới, dùng EM mới hoặc xử lý `refresh`/detach/clear phù hợp, và xét isolation.

### 7.2. `CacheStoreMode.BYPASS`

```java
Product product = em.find(
    Product.class,
    42L,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.BYPASS
    )
);
```

Mục tiêu là tránh đọc và tránh populate/update shared L2 cache cho thao tác đó theo JPA cache-mode contract; behavior/provider support cần được kiểm chứng trên stack thực.

### 7.3. `CacheStoreMode.REFRESH`

`CacheStoreMode.REFRESH` yêu cầu refresh shared cache state cho result theo contract của JPA, nhưng không thay thế database isolation semantics và không tự invalidate mọi related query/application caches. Chỉ sử dụng sau khi hiểu provider hiện hành.

### 7.4. Không dùng bypass làm “global cure”

Một endpoint cực kỳ nhạy cảm có thể cần read-from-primary, bypass L2 và dùng transaction phù hợp. Nhưng bật bypass trên mọi query sẽ giảm lợi ích cache, tăng DB load và vẫn không sửa L1 stale state ở nơi khác.

### 7.5. Đọc có tính nhất quán mạnh

Với kiểm tra quyền/tồn kho/số dư, có thể chọn query trực tiếp primary, transaction/locking/optimistic protocol phù hợp thay vì tin vào cache eventual-consistent. **Bypass cache không tự khóa row** và không ngăn writer khác cập nhật ngay sau đọc.

## 8. Hibernate cache regions và query cache

Hibernate là một JPA provider phổ biến, bổ sung API và khái niệm cache riêng. Không coi toàn bộ API Hibernate là portable Jakarta Persistence.

### 8.1. Entity cache region

Entity type có thể được lưu trong một region và chịu concurrency strategy như read-only, read-write hoặc nonstrict-read-write tùy provider/cache configuration. Chọn strategy theo tính thay đổi dữ liệu và consistency requirements.

Một entity mutable nhưng có external writers nên được xem xét rất cẩn thận trước khi bật L2 cache: Hibernate có thể quản lý những thay đổi **đi qua Hibernate**, trong khi writer SQL khác không thông báo cache.

### 8.2. Collection region

Ví dụ `Category.products` có collection caching. SQL import thêm Product#99 vào category:

```sql
INSERT INTO products (id, category_id, ...)
VALUES (99, 5, ...);
```

Ngay cả khi evict Product#99, collection cache của Category#5 có thể vẫn giữ danh sách membership cũ. Cần invalidation vùng/collection phù hợp theo Hibernate API/configuration, hoặc tắt collection cache cho dữ liệu được sửa liên tục từ bên ngoài.

### 8.3. Query cache là cache **kết quả truy vấn**

Ví dụ query:

```java
List<Product> products = em.createQuery(
        "select p from Product p " +
        "where p.tenantId = :tenant " +
        "and p.status = :active",
        Product.class)
    .setParameter("tenant", tenantId)
    .setParameter("active", ProductStatus.ACTIVE)
    .setHint("org.hibernate.cacheable", true)
    .getResultList();
```

HQL/JPQL query caching qua Hibernate không được kích hoạt chỉ vì có L2 cache; nó cần provider configuration và opt-in thích hợp. Kết quả query có thể lưu identifiers/scalars và dựa vào invalidation timestamps/spaces, tùy Hibernate version/query type. **Không phải cứ evict Product#42 là mọi cached query results có Product#42 tự hết stale**.

### 8.4. Thay đổi ngoài Hibernate gây “unknown change”

Hibernate có thể biết query spaces/tables bị ảnh hưởng khi chính nó chạy DML và invalidation mechanism được cấu hình. Nhưng SQL bên ngoài process hoặc external JDBC connection không phát thông tin đó vào Hibernate. Query cache có thể tiếp tục trả list IDs/aggregate results cũ cho đến khi bị invalidate/expire.

### 8.5. Native SQL và synchronized query spaces

Với Hibernate, một số native queries có API khai báo synchronized query spaces/entities để phối hợp flush/query invalidation khi chạy **qua Hibernate**. Cách hỗ trợ khác theo version/query API. Nó **không** biến SQL script chạy từ DBA tool thành một sự kiện mà Hibernate tự thấy.

### 8.6. Evict Hibernate-specific regions

Tùy Hibernate version, `SessionFactory.getCache()` có các phương thức quản lý entity/collection/query regions như `evictEntityData`, `evictCollectionData`, `evictQueryRegions`. Ví dụ khái niệm:

```java
SessionFactory sf =
    emf.unwrap(SessionFactory.class);

sf.getCache().evictEntityData(Product.class);
sf.getCache().evictQueryRegions();
```

**Kiểm tra chính xác method names/signatures/version** trên Hibernate đang dùng, nhất là collection region management. API này provider-specific, không thay vì `EntityManagerFactory.getCache()` trong code portable.

### 8.7. Không xóa query cache timestamps lung tung

Trong một số cấu hình Hibernate, cập nhật thời gian invalidation cho query spaces là cơ chế giúp nhận diện stale result sets. Clear một phần regions không đúng thứ tự hoặc giữ query results lâu hơn metadata invalidation có thể gây incoherence. Dùng provider-supported eviction/region lifecycle thay vì trực tiếp sửa backend keys không hiểu cấu trúc.

### 8.8. Query cache cho aggregate reports

Một query `select count(p)` hoặc `sum(...)` có thể lưu scalar result. External INSERT/UPDATE/DELETE có thể khiến aggregate **sai** dù không có một entity cache entry cụ thể cần evict. Phải invalidate **result sets / report cache** theo query dependencies hoặc dùng TTL/refresh/read model phù hợp.

## 9. Spring Cache, Caffeine và Redis là một lớp riêng

Một service có thể có:

```java
@Cacheable(
    cacheNames = "productDetails",
    key = "#tenantId + ':' + #productId"
)
public ProductView getProduct(
        String tenantId, Long productId) {
    Product product = repository
        .findByIdAndTenantId(productId, tenantId)
        .orElseThrow();
    return ProductView.from(product);
}
```

Nếu Redis/Caffeine còn giữ `ProductView(price=100000)`, gọi `emf.getCache().evict(Product.class,42L)` **không xóa ProductView đó**.

### 9.1. Cache key là một phần data security

Key ví dụ:

```text
productDetails:TENANT_A:42
productDetails:TENANT_B:42
```

Nếu bỏ tenant khi ID chỉ unique theo tenant, app có thể trả dữ liệu tenant A cho tenant B. Với per-user permissions, key hoặc cache boundary còn có thể cần permission scope/role/version hoặc tránh cache response nhạy cảm.

### 9.2. @CacheEvict

```java
@CacheEvict(
    cacheNames = "productDetails",
    key = "#tenantId + ':' + #productId"
)
public void invalidateProductView(
        String tenantId, Long productId) {
    // Cache advice performs eviction.
}
```

Lưu ý Spring Cache annotations được áp qua proxy trong cấu hình thông thường; self-invocation có thể bypass advice. Phải xác minh cache manager và phạm vi Redis/Caffeine đang dùng.

### 9.3. TTL không phải strong consistency

TTL 5 phút giới hạn thời gian stale **nếu cache và backend hoạt động như dự kiến**, nhưng không bảo đảm user đọc ngay sau commit thấy state mới. Với thay đổi quyền/giá thanh toán/lock trạng thái, 5 phút stale có thể không chấp nhận được.

### 9.4. Per-node Caffeine khác shared Redis

Evict key trong local cache ở node A không tự clear node B. Redis là store dùng chung có thể đơn giản hóa eviction giữa nodes, nhưng còn near-cache/local-cache, replica lag và race khi writers repopulate. Hãy xác định topology thật.

### 9.5. TTL stampede

Evict hàng loạt keys ngay sau deploy có thể khiến hàng nghìn requests đồng thời đánh DB. Có thể dùng staggered TTL, request coalescing/single-flight, bounded warmup và traffic throttling. Không hy sinh correctness chỉ vì muốn giữ cache hit cao.

### 9.6. Cache của HTML/API/gateway

Ngay cả khi service trả DTO mới, CDN/browser có thể giữ ETag/Cache-Control response cũ. Điều này đòi hỏi HTTP cache policies và surrogate key purge hoặc versioned URLs cho nội dung tương ứng; không thuộc `jakarta.persistence.Cache`.

## 10. Những đường ghi dữ liệu ngoài ứng dụng

| Nguồn thay đổi | Ví dụ | Loại cache có thể không được biết |
|---|---|---|
| DBA chạy SQL | UPDATE Product.price | L1/L2/query/application/CDN |
| Flyway/Liquibase data migration | Backfill status, đổi enum values | Các caches có state/serialized schema cũ |
| JDBC batch job | Cập nhật 500.000 stock rows | L2/query/DTO caches |
| Stored procedure | Cập nhật discount, status | Các vùng không được ORM theo dõi đầy đủ |
| Microservice khác dùng chung DB | Giá từ ERP service | Cache của service hiện tại |
| ETL/CDC sink | Apply dữ liệu đã transform | Cache consumers chưa nhận invalidation |
| Manual repair | Sửa record bị lỗi | Cache + audit/reconciliation |
| Bulk JPQL UPDATE/DELETE | `executeUpdate` | L1 và có thể những cache layers khác |
| Native SQL qua JPA | UPDATE tùy ý | Tùy provider synchronization/regions |
| DB trigger | Tự cập nhật field liên quan | Cache entries của các rows/bảng phát sinh |
| Restore từ backup | Thay cả tập dữ liệu | Toàn bộ cache namespace có thể sai |

### 10.1. “Không đi qua JPA” là dấu hiệu cần review

Không phải external change nào cũng bắt buộc flush toàn cache. Nhưng **bất kỳ writer không tham gia invalidation protocol** đều có thể phá giả định rằng cache phản ánh DB mới nhất.

### 10.2. Bulk JPQL không đồng nghĩa ordinary entity update

Ví dụ:

```java
int changed = em.createQuery(
    "update Product p " +
    "set p.status = :inactive " +
    "where p.tenantId = :tenant " +
    "and p.status = :active")
  .setParameter("inactive", ProductStatus.DISCONTINUED)
  .setParameter("active", ProductStatus.ACTIVE)
  .setParameter("tenant", tenantId)
  .executeUpdate();
```

Bulk DML bypass per-entity dirty checking/lifecycle callbacks, và managed entities đang ở L1 có thể stale. Provider có thể invalidate một số shared regions khi chính nó chạy bulk operation, nhưng không tự xử lý mọi Spring Cache/Redis/CDN cache. Không dựa vào hành vi không kiểm chứng.

### 10.3. DB trigger tạo dữ liệu mới ngoài ORM expectation

Một update Price có thể kích hoạt trigger ghi `price_history` hoặc thay `price_effective_at`. Ngay cả nếu Product#42 được evict, các báo cáo/collections cache liên quan cũng cần xem xét. Hãy lập bảng dependencies từ **source tables → cache keys/regions**.

## 11. Vì sao `@Version` không tự giải quyết cache stale?

`@Version` phục vụ **optimistic concurrency** cho những đường ghi tuân thủ JPA/provider protocol. Nó không phải một cơ chế pub/sub invalidation tới mọi node.

### 11.1. External SQL không tăng version

```sql
UPDATE products
SET price = 120000
WHERE id = 42;
```

Giả sử trước đó DB `version=7`. Sau SQL trên, version vẫn 7 nếu không có trigger hoặc explicit update. Một EM khác giữ entity version=7 có thể tạo write mới với version predicate vẫn khớp và ghi đè một số giá trị từ state cũ tùy mapping/provider SQL.

### 11.2. External writer tăng version

Với numeric version và một update phù hợp:

```sql
UPDATE products
SET price = 120000,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 42
  AND tenant_id = 'TENANT_A';
```

Điều này giúp **các stale managed writers** phát hiện version mismatch khi update cùng entity. Nhưng một L2 cache đã lưu price=100000/version=7 vẫn có thể được trả cho một reader nếu không có cache invalidation/coherence mechanism; `@Version` không tự query DB để so version mỗi lần cache hit.

### 11.3. DB trigger bảo vệ version nhưng cần phù hợp mapping

Có thể dùng trigger để bump version khi có writers ngoài JPA, nhưng phải phối hợp với Hibernate/JPA version increment để tránh double increment, bất đồng timing/result version và optimistic conflicts giả. Không áp trigger máy móc khi ứng dụng cũng tự tăng version.

### 11.4. Business data và concurrency guard là hai việc khác nhau

- **Version check**: chống ghi stale state trong cạnh tranh.
- **Cache invalidation**: giúp reads tránh dữ liệu cũ.
- **Authorization**: xác định caller có quyền đổi Price/status.
- **DB constraints**: đảm bảo state hợp lệ.

Một cơ chế không thay thế ba cơ chế còn lại.

### 11.5. External writers cần tham gia protocol

Viết **data modification contract** cho mọi source:

```text
Modify source rows using approved SQL/transaction
Validate tenant/scope/constraints
Maintain version/audit protocol if required
Commit
Publish durable invalidation/change event
Evict related caches
Verify freshness/functional result
```

Với hệ thống đòi strong consistency, một event eventual-consistent có thể vẫn chưa đủ; phần sau trình bày những lựa chọn nghiêm ngặt hơn.

## 12. Khi nào nên invalidate: trước, trong hay sau commit?

Giả sử app sử dụng Redis cache `productDetails:TENANT_A:42` và muốn đổi giá:

```text
BEGIN;
UPDATE products SET price = 120000 WHERE id = 42;
COMMIT;
DELETE cache key;
```

Ngay cả quy trình có thứ tự này vẫn có một **cửa sổ stale** sau COMMIT trước DELETE. Việc chạy DELETE trước COMMIT cũng có race khác.

### 12.1. Evict trước commit

```text
Writer W: DELETE cache(key)
Reader R: cache miss
Reader R: SELECT DB -> old price=100000 (W chưa commit)
Reader R: populate cache(old)
Writer W: COMMIT new price=120000

=> Cache giữ old price.
```

**Evict trước commit không phải luôn an toàn** vì reader khác có thể repopulate dữ liệu cũ trong lúc transaction chưa commit.

### 12.2. Evict sau commit

```text
Writer W: COMMIT new price
Reader R: cache hit old price trong vài milliseconds
Writer W: DELETE cache(key)
Reader tiếp: miss -> DB new price
```

Sau commit hợp lý hơn với eventual consistency, nhưng vẫn có một khoảng trễ và một race nếu reader có DB query cũ đang chạy rồi populate cache **sau eviction**.

### 12.3. Invalidation sau rollback

Nếu SQL UPDATE rollback nhưng cache bị evict, hệ thống không sai dữ liệu nếu đọc DB source tiếp, nhưng có unnecessary cache miss và có thể gây cache stampede. Với side effects khác (query region purge, materialized summary refresh), thời điểm rollback có thể gây hệ quả khó hiểu. Chọn policy rõ.

### 12.4. Giao thức đơn giản không mang nghĩa linearizability

Không được tuyên bố:

> “Có `@TransactionalEventListener(AFTER_COMMIT)` nên mọi read sau commit đều thấy dữ liệu mới.”

Event listener có thể chạy sau commit nhưng trên node khác vẫn có delivery latency; reader có thể đang giữ L1 state hoặc cache old result; replica cũng có thể chưa catch up.

### 12.5. Chọn consistency contract

| Requirement | Ví dụ | Hướng tiếp cận |
|---|---|---|
| Eventual, stale tối đa 1 phút | Catalog preview | TTL + after-commit invalidation, monitoring |
| Read-your-writes | Admin sửa giá rồi refresh ngay | Bypass/refresh/read primary và version-aware response cho chính user |
| Strict checkout price | Tính tiền phải đúng giá tại thời điểm xác nhận | Transaction/snapshot/revalidation, giá khóa theo order policy, không tin DTO cache |
| Strong permission revocation | Thu hồi quyền truy cập | Không chỉ cache TTL; kiểm tra authoritative permission/version hoặc invalidate đồng bộ có fence |
| Auditable billing | Ledger report | Committed immutable source/snapshot, query/database consistency |

Điểm quan trọng: “Làm mới cache” và “bảo đảm đúng lúc nào” không cùng một bài toán. Chọn cách dựa trên SLO/consistency requirements.

## 13. Spring event listener sau commit

Một pattern đơn giản cho **cập nhật qua ứng dụng**:

```java
public record ProductChanged(
    String tenantId,
    Long productId
) {}
```

Service:

```java
@Service
public class ProductCommandService {

    private final ProductRepository products;
    private final ApplicationEventPublisher events;

    @Transactional
    public void changePrice(
            String tenantId,
            Long id,
            BigDecimal newPrice) {

        Product product = products
            .findByIdAndTenantId(id, tenantId)
            .orElseThrow();

        product.changePrice(newPrice);

        events.publishEvent(
            new ProductChanged(
                tenantId, product.getId()));
    }
}
```

Listener:

```java
@Component
public class ProductCacheListener {

    private final CacheManager cacheManager;

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterCommit(ProductChanged event) {
        org.springframework.cache.Cache cache =
            cacheManager.getCache("productDetails");
        if (cache != null) {
            String key =
                event.tenantId() + ":" + event.productId();
            cache.evict(key);
        }
    }
}
```

### 13.1. Đây là pattern minh họa, không phải production solution hoàn chỉnh

Trong ví dụ, event chỉ chứa entity ID vì phục vụ eviction đơn thuần. Nếu version là một phần cache consistency protocol, phải lấy **committed correct version** (hoặc ghi outbox với version được xác định chính xác), không gửi version placeholder: version mới có thể chưa được biết khi event được phát trước flush.

### 13.2. Tại sao `AFTER_COMMIT`?

Listener chỉ tiến hành eviction khi transaction được đánh dấu đã commit, tránh invalidate vì update đã rollback. Tuy nhiên không nên giả định listener delivery durable.

### 13.3. Process crash giữa commit và listener

```text
DB commit successful
JVM process crashes
AFTER_COMMIT listener did not evict Redis
```

Cache có thể stale cho đến TTL/manual purge. Event cùng process là tiện lợi nhưng **không thay một durable change feed/outbox** khi consistency yêu cầu cao.

### 13.4. Listener error không rollback committed transaction

Nếu eviction Redis lỗi sau DB commit, rollback DB **không còn khả thi** chỉ vì after-commit action fail. Cần retry/alert/repair flow. Đừng trả lời user “đã rollback update” nếu dữ liệu đã committed.

### 13.5. Node-local cache

`@TransactionalEventListener` chạy ở process hiện tại. Nếu node B có Caffeine local cache riêng, nó không được evict trừ khi có broadcast/durable event hoặc topology shared cache phù hợp.

### 13.6. Version event và transaction timing

Nếu cần version trong event, một cách là flush để provider assign new numeric version trước khi ghi durable outbox record, nhưng flush có thể ném constraint errors và vẫn chưa commit. Cần write model/outbox schema chính xác, không giả định setter đã tăng version.

## 14. Transactional outbox: invalidation bền vững hơn

Một integration pattern là ghi một row outbox **trong cùng database transaction** với thay đổi business data, rồi relay worker gửi event sau commit.

### 14.1. Schema minh họa

```sql
CREATE TABLE cache_invalidation_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    change_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
```

Nếu identifier type không phải BIGINT, chọn kiểu phù hợp. `aggregate_type`/`change_type` cần vocabulary được version hóa; các hệ thống có thể dùng JSON payload kèm version và event trace ID.

### 14.2. Trong một transaction

```text
BEGIN
  update Product#42 price
  insert cache_invalidation_outbox(
      eventId, productId=42, tenant=A)
COMMIT
```

Nếu transaction rollback, cả Product update và outbox row rollback. Nếu commit thành công nhưng process chết, outbox row **vẫn tồn tại** để relay xử lý sau.

### 14.3. Relay

```text
outbox polling / CDC
    |
    v
publish ProductChanged event
    |
    v
subscribers by application/cache domain
    |
    v
evict Product entity/query/DTO regions or keys
    |
    v
record delivery / ack / retry
```

### 14.4. At-least-once delivery

Outbox relays có thể publish event hơn một lần (crash sau publish trước marking). Eviction là hành động thường idempotent khi xóa cùng key nhiều lần, nhưng nếu event làm **rebuild/prewarm** hoặc cập nhật version counters, phải thiết kế idempotency/ordering.

### 14.5. Event-ordering

```text
Product#42 version 7 -> version 8
Product#42 version 8 -> version 9
```

Nếu subscriber nhận event version 9 trước version 8, một “write cache payload” ngây thơ có thể ghi lại state cũ. Ưu tiên **invalidation thay payload** hoặc compare-and-set theo monotonic version/source commit sequence. Event version phải có nghĩa thống nhất và đáng tin.

### 14.6. Lost messages và replay

Outbox giúp khôi phục từ relay downtime nếu retention/ack protocol đúng. Theo dõi event age, retry count, dead-letter queue và thời gian chậm nhất giữa DB commit và cache invalidation. Có runbook replay theo sequence/event ID.

### 14.7. Outbox không tự giải quyết cửa sổ stale

Relay có thể trễ vài giây; trong khoảng đó cache cũ vẫn tồn tại. Nếu requirement đòi “sau commit, mọi node luôn thấy state mới”, cần giao thức mạnh hơn hoặc bypass cache cho operations nhạy cảm. Outbox là **durability/invalidation propagation mechanism**, không tự là distributed transaction với cache.

### 14.8. External writers phải ghi outbox hoặc CDC source

Script SQL ngoài application nếu chỉ UPDATE products mà không ghi outbox và không có CDC coverage thì relay không biết có change. Quy ước migration/ETL phải ghi sự kiện thích hợp hoặc thực hiện invalidation theo runbook.

## 15. CDC: phát hiện thay đổi database không đi qua JPA

Change Data Capture có thể trích thay đổi từ database log (ví dụ PostgreSQL WAL logical decoding hoặc hệ tương đương) và phát events tới subscribers.

### 15.1. Khi CDC hữu ích

- ERP hoặc legacy service ghi cùng database.
- DBA sửa dữ liệu trực tiếp.
- Batch import/ETL không gọi application API.
- Nhiều services cần đồng bộ read models/cache.
- Muốn rebuild state dựa trên committed row changes.

### 15.2. CDC có biết toàn bộ business meaning không?

Một row update `price=120000` nói có thay đổi cột Price, nhưng không nhất thiết biết:

- Tenant permissions của caller.
- Có cần invalidate product list pages, price filters hay recommendations không?
- Có tính lại product search index không?
- Có business event nào như `PriceApproved` không?

CDC là **nguồn tín hiệu dữ liệu thay đổi**, còn dependency mapping/invalidation decisions thuộc hệ thống.

### 15.3. CDC lag

Lưu ý:

```text
DB commit at T0
CDC reads log at T0+500ms
Kafka/event bus delivers at T0+1s
Subscriber invalidates at T0+2s
```

Trong 2 giây đó, cached reads có thể stale. Đặt freshness budget và monitor end-to-end lag.

### 15.4. Thứ tự và duplicate events

Partition/consumer nhóm theo entity key nếu cần ordering. Một số pipelines có at-least-once delivery, replay hoặc reorder; eviction thường dễ xử lý hơn cache-put event payload nhưng vẫn cần version/fencing nếu có concurrent fills.

### 15.5. CDC và migration lớn

Một backfill cập nhật 50 triệu rows có thể phát 50 triệu CDC events, quá tải cache invalidation workers. Có thể chọn invalidation theo region/namespace ở cấp migration, điều tiết CDC hoặc chiến lược bulk snapshot; phải giữ continuity/offset và không âm thầm mất các change events quan trọng.

### 15.6. Không nhầm CDC với database backup

CDC không tự thay backup, PITR/reconciliation và idempotent recovery. Một cached read-model có thể được rebuild từ primary source nếu changelog đầy đủ và consistency policy cho phép.

## 16. Race giữa read miss và invalidate: stale repopulation

Ngay cả khi eviction xảy ra **sau commit**, một reader query kéo dài có thể repopulate cache bằng old data sau eviction.

### 16.1. Timeline

```text
T1 Reader R: cache miss
T2 Reader R: SELECT old Product.price=100000
              (transaction/snapshot started before write)
T3 Writer W: COMMIT price=120000
T4 Writer W: EVICT cache key
T5 Reader R: PUT price=100000 into cache
T6 Reader S: cache hit price=100000
```

**Delete-after-commit chưa loại bỏ mọi race** khi cache-aside writers/populators không có coordination.

### 16.2. Phiên bản cache key (generation/epoch)

Một cách giảm race là namespace theo generation:

```text
catalog:v12:TENANT_A:42
catalog:v13:TENANT_A:42
```

Sau cutover, readers dùng `v13`; một reader cũ populate `v12` không làm bẩn `v13`. Tuy nhiên phải bảo đảm consumers chỉ đọc generation mới sau switch và old node không còn phục vụ requests trên namespace cũ khi correctness yêu cầu.

### 16.3. Version-aware cache write

Nếu cache entry mang `sourceVersion`, có thể dùng atomic compare-and-set:

```text
put(newEntry) only when
    newEntry.version >= cachedEntry.version
```

Cần atomicity ở cache backend. Nhưng với **external writes không tăng version**, so version không phát hiện old data. Versioning protocol phải được thực thi bởi mọi writers.

### 16.4. Invalidate with generation token

Một key có generation counter:

```text
generation(TENANT_A:42) = 20
reader captures generation 20
writer commits then increments generation to 21
reader finishes old DB query
reader sees generation != 20 -> discards old fill
```

Đây là mô hình fencing; triển khai thực phải bảo đảm đọc/ghi generation và cache value tương ứng một cách atomic hoặc có guard/check lặp cần thiết, nếu không vẫn tồn tại race giữa kiểm tra generation và write.

### 16.5. Cache-aside không tự cung cấp strict consistency

Nếu dữ liệu là giá checkout hay quyền mới thu hồi, cân nhắc transaction-primary reads/locking/version checks thay vì cố biến mọi application cache thành linearizable store. Không dùng stale cache như authoritative decision source.

### 16.6. Nếu dùng TTL, ghi rõ giới hạn

TTL giới hạn tuổi từ lần cache fill theo policy, không thể bảo đảm **mọi read sau một DB commit** mới ngay. Nếu cache entry bị repopulate cũ sau eviction, nó có thể sống thêm cả một TTL.

## 17. Cache key và invalidation dependency graph

Một Product có thể xuất hiện trong nhiều cache keys:

```text
productDetails:tenantA:42
productList:tenantA:ACTIVE:page1
productList:tenantA:ACTIVE:page2
productsByCategory:tenantA:5
productSearch:tenantA:keyword=sua
productPriceAggregate:tenantA
promotionEligibleProducts:tenantA
```

Thay `price` có thể ảnh hưởng:

- Product detail cache.
- Các trang list sort theo price.
- Search/filter results theo price.
- Discount eligibility.
- Promotion aggregate.
- Report totals.

### 17.1. Evict một entity không đủ

`emf.getCache().evict(Product.class,42L)` chỉ nhắm shared entity cache. Nếu productList là Spring Cache/Redis một serialized DTO list, list vẫn giữ price cũ. Nếu query filter theo price, item mới có thể phải xuất hiện/biến mất ở cached result set.

### 17.2. Lập dependency map

| Source table/field | L2 entity | Collection | Query regions | Application cache |
|---|---|---|---|---|
| `products.price` | Product#id | Có thể category/product list nếu contains embedded projection | Price/filter/sort queries | Details, search, reports |
| `products.status` | Product#id | Category active memberships | Active product queries | Menus, listing |
| `products.category_id` | Product#id | Old và new category collections | Category queries | Category pages |
| `inventory.quantity` | Inventory#id | Có thể không | Availability queries | Stock badges |
| `user_roles` links | User/Role tùy mapping | User.roles membership | Permission lookup queries | Authorization cache |

### 17.3. Granularity

- **ID eviction** khi biết chính xác ID và dependent keys.
- **Region/type eviction** khi thay số lượng lớn hoặc dependency khó liệt kê.
- **Namespace version bump** khi release thay cách giải nghĩa dữ liệu/cache schema.
- **Disable/bypass** khi không thể bảo đảm correctness trong maintenance window.

### 17.4. Không dùng wildcard key scan bừa bãi

Redis `KEYS prefix*` trên dataset lớn có thể block/đắt và tạo load. Chọn keyed indexes/set membership, `SCAN` có kiểm soát, prefix generation hoặc direct cache region operations; xem version/backend semantics. Dùng TTL để tự dọn old generations theo retention plan.

### 17.5. Caching paginated/sorted lists

Evict chỉ `page=1` không đủ khi đổi price/status làm thứ tự hoặc membership thay đổi; một item có thể dịch từ page 2 sang page 1. Những list results có invalidation dependency rộng thường phù hợp TTL ngắn, key theo catalog generation hoặc summary/read model rõ.

## 18. Triển khai nhiều instance: local cache và distributed cache

Một hệ thống có ba pods:

```text
Pod A: L2 local Product#42 price=100000
Pod B: L2 local Product#42 price=100000
Pod C: L2 local Product#42 price=100000

DB: Product#42 price=120000 after migration
```

Gọi `evict` trên pod A chỉ bảo đảm theo scope của cache provider trên pod A. Nếu B/C có local caches độc lập, users đi vào B/C vẫn có thể thấy old price.

### 18.1. Kiểm tra topology

Hỏi:

1. Cache dùng shared Redis/Infinispan/Hazelcast hay local Ehcache/Caffeine?
2. L2 có clustering/invalidation protocol hay mỗi JVM tự giữ region?
3. Query result caches có dùng same backing store không?
4. Spring Cache và Hibernate L2 dùng **cùng Redis cluster** hay là hai logical caches khác?
5. Có near-cache ở từng pod không?
6. Có pods cũ, scheduled jobs, background consumers đang giữ cùng vùng cache không?

### 18.2. Broadcast invalidation

Một pattern:

```text
Change committed -> event bus
                  -> Pod A evict relevant L2 / local cache
                  -> Pod B evict relevant L2 / local cache
                  -> Pod C evict relevant L2 / local cache
                  -> Redis delete/epoch bump if applicable
```

Nếu event chỉ đến “một subscriber trong consumer group”, **không phải tất cả pods** sẽ nhận. Phải thiết kế semantics broadcast hay dùng shared central generation/expiration sao cho mọi readers đều bị ảnh hưởng.

### 18.3. Một node tạm offline

Node B không nhận event vì restart. Khi trở lại, nó có thể giữ local cache cũ nếu restart không clear state hoặc cache được persisted. Cần replay theo offset/epoch, TTL/namespace version hoặc node startup validation trước khi phục vụ requests.

### 18.4. Không phụ thuộc ephemeral process lifecycle nếu cache persistent

Khởi động lại JVM có thể xóa L1/local memory cache, nhưng **không** xóa Redis/distributed store hay persisted cache files. “Restart app để clear cache” chỉ đúng cho một số layers/topologies.

### 18.5. Instance identity và rolling deployments

Khi deploy từng pod, một số pods đang chạy release cũ, số khác chạy release mới. Nếu chung cache namespace nhưng serialization/entity shape thay đổi, cả hai có thể đọc/ghi incompatible cache entries. Điều này cần kế hoạch riêng ở các phần tiếp theo.

## 19. Rolling deployment: khi phiên bản cũ và mới cùng chạy

Một rolling deployment:

```text
Time T0: Node A/B/C đều chạy release v1.
Time T1: Node A chạy release v2; B/C vẫn v1.
Time T2: Node B chạy v2; C vẫn v1.
Time T3: Node C chạy v2.
```

Trong lúc chuyển đổi, cả v1 và v2 có thể đồng thời đọc/ghi chung DB/cache.

### 19.1. Thay đổi Java entity shape

Giả sử v1 cache `ProductView`:

```json
{
  "id": 42,
  "price": 100000,
  "status": "ACTIVE"
}
```

v2 thêm:

```json
{
  "id": 42,
  "price": 100000,
  "currency": "VND",
  "availability": "IN_STOCK",
  "status": "ACTIVE"
}
```

Nếu v2 deserialize dữ liệu Redis v1 vào new DTO mà không có backward-compatible schema, có thể thiếu currency/availability, lỗi deserialize hoặc sử dụng default sai. Ngược lại v1 có thể đọc v2 payload rồi fail vì unknown fields.

### 19.2. Cache schema versioning

Một phương án:

```text
catalog:productView:schema-v1:TENANT_A:42
catalog:productView:schema-v2:TENANT_A:42
```

Các releases có cache representation khác nhau không chia sẻ key. Điều này giảm rủi ro serialization compatibility, nhưng **vẫn cần xử lý invalidation/freshness** cho cả hai namespaces trong giai đoạn coexistence.

### 19.3. Cache schema version khác source-data version

- **Schema version**: format của cached value.
- **Data version**: committed version của một Product row.
- **Release version**: application build/deployment artifact.
- **Generation/epoch**: namespace mà readers đang dùng.

Không nên lấy một số `v2` chung cho tất cả mà không biết nó đại diện cái gì.

### 19.4. Old node có thể repopulate cache cũ

Nếu chạy lệnh evict trong lúc node v1 còn phục vụ, node đó có thể nạp lại old-format key hoặc old-data snapshot. Sau khi evict, phải bảo đảm:

- Old readers không còn được route nếu migration cần cutover.
- Hoặc old/new reader protocols đều tương thích và invalidation áp đủ hai phiên bản.
- Hoặc mỗi release dùng namespace riêng và có kế hoạch draining.

### 19.5. Blue-green deployment

Blue-green giúp tách traffic giữa hai fleets, nhưng nếu dùng chung DB và cache thì không tự bảo đảm data consistency. Cần xem cache namespace, data migrations, in-flight requests và rollback behavior trước khi chuyển traffic.

### 19.6. Traffic draining

Khi release có thay đổi cache semantics, một sequence khả thi:

```text
Deploy compatible new version
Warm/test new cache generation if safe
Quiesce or drain old writers/readers when required
Finish data migration and commit
Invalidate/switch generation with coordination
Route traffic to compatible readers
Observe and retire old generation
```

Đây là phương án tham khảo; thứ tự cụ thể phụ thuộc việc old version có đọc/ghi được cả old/new schema trong window hay không.

## 20. Expand–migrate–contract và cache compatibility

Một deployment an toàn thường tách việc thay schema thành các pha:

1. **Expand:** bổ sung schema mà code cũ vẫn chạy được.
2. **Migrate/backfill:** chuyển dữ liệu hoặc điền dữ liệu mới.
3. **Switch reads/writes:** ứng dụng bắt đầu dùng representation mới khi dữ liệu đủ.
4. **Contract:** chỉ xóa schema cũ khi không còn code cũ phụ thuộc.

Cache cũng cần theo từng pha.

### 20.1. Ví dụ đổi `price` thành `base_price` + `currency_code`

Schema cũ:

```text
products.price
```

Schema mới:

```text
products.base_price
products.currency_code
```

Nếu lập tức drop `price` và deploy v2 trước khi mọi node v1 ngừng, v1 có thể fail. Nếu chỉ đổi cache key mà DB values chưa backfill, v2 có thể cache null/incorrect representation.

### 20.2. Expand

Migration tạo columns mới nullable/compatible, chưa bỏ price. Code mới có thể dual-read hoặc fallback theo strategy. Tránh vô tình chuyển old cached value thiếu currency thành “0 VND” không có căn cứ.

### 20.3. Backfill

Script SQL điền `base_price`/`currency_code` theo domain mapping. Nếu v2 cache values trong lúc backfill mới làm một phần, có thể lưu mixed snapshots; chọn generation cutover, maintenance read-mode hoặc dual-read logic có validation.

### 20.4. Switch

Khi dữ liệu mới đầy đủ và code mới được triển khai, route read path sang new fields. Invalidate entity/query/application cache entries liên quan hoặc dùng new generation được populating từ committed new state.

### 20.5. Contract

Sau khi xác nhận không còn node/consumer cũ, bỏ old column và old cache namespace theo retention. Không xóa old data/cache trước khi đã quyết định rollback plan.

### 20.6. Câu hỏi quan trọng

Nếu rollback code v2 về v1 sau khi DB/data đã được thay đổi, v1 có còn hiểu representation/database mới không? Một cache flush không sửa được schema incompatibility hoặc mất dữ liệu. Rollback phải được xem là phần của migration design.

## 21. Data migration thay hàng loạt rows

Một migration có thể đổi 200.000 sản phẩm:

```sql
UPDATE products
SET status = 'DISCONTINUED'
WHERE status = 'LEGACY';
```

Sau commit, mọi Product entries có status cũ đều có nguy cơ stale.

### 21.1. Đếm và xác nhận scope trước thay đổi

```sql
SELECT COUNT(*)
FROM products
WHERE status = 'LEGACY';
```

Ghi tenant filters/cutoff/affected IDs, preview số lượng và rollback/recovery plan. Những bước này bảo vệ dữ liệu gốc; cache invalidation chỉ là một bước sau migration.

### 21.2. Nếu ít rows

Ghi danh sách IDs affected trong migration/log an toàn, rồi:

```java
for (Long id : changedIds) {
    emf.getCache().evict(Product.class, id);
}
```

Cùng lúc invalidate dependent Spring/Redis query/list keys. Nếu chạy trong một node với local caches, phải truyền event đến các nodes khác.

### 21.3. Nếu nhiều rows

Evict từng ID có thể tốn nhiều request tới distributed backend. Có thể:

- Evict toàn entity region.
- Bump logical catalog generation.
- Đóng cửa read cache trong maintenance window.
- Tạo build/read-model snapshot mới rồi cutover.

Chọn theo mức chấp nhận stale data và chi phí cache stampede.

### 21.4. Không evict trước khi data migration commit toàn bộ

Nếu migration dùng nhiều transactions/batches, có thể chưa có một “toàn bộ đã commit” duy nhất. Cần định nghĩa whether read path được chấp nhận thấy trạng thái mixed, hoặc tạm vô hiệu hóa caching/traffic trong khi backfill.

### 21.5. Batches và watermark

Với 10 triệu rows:

```text
Batch 1 (ids 1..10000)   COMMIT
Batch 2 (ids 10001..20000) COMMIT
...
Final validation and cutover
```

Nếu dashboard vẫn phục vụ live reads, phải biết một request có thể thấy một số rows migrated và số khác chưa. Dùng migration state/watermark hoặc dual-read compatible schema nếu mixed state có thể tồn tại.

### 21.6. Data backfill không bảo đảm query cache chính xác

Nếu query cache lưu `count(status='LEGACY')`, việc evict Product entity region có thể chưa loại cached aggregate result. Phải tính query-result invalidation trong runbook.

### 21.7. DB trigger ảnh hưởng các bảng khác

Migration cập nhật Products có thể kích hoạt trigger làm update CategorySummary. Cache dependencies phải bao gồm các side-effect tables.

### 21.8. Throttling sau invalidate

Một full-region eviction khi traffic cao có thể gây:

- Cache hit rate giảm đột ngột.
- DB CPU/I/O tăng.
- Throttled connection pool.
- Tail latency tăng.
- Request timeouts.

Có thể dùng rate limits, staggered warmup và cache generation prepopulation, nhưng không prewarm dữ liệu chưa commit.

## 22. Thay đổi reference data và enum values

Reference tables thường được cache lâu vì ít thay đổi. Nhưng migration thay enum/lookup data có thể tác động **business semantics** sâu hơn giá trị cũ.

### 22.1. Ví dụ thay status

v1:

```java
enum ProductStatus {
    DRAFT, ACTIVE, LEGACY
}
```

v2:

```java
enum ProductStatus {
    DRAFT, ACTIVE, DISCONTINUED
}
```

Nếu DB được migrate `LEGACY -> DISCONTINUED` trong lúc node v1 còn đọc, v1 có thể throw khi map enum string mà nó không biết.

### 22.2. Evict cache không giải quyết incompatibility

Khi node v1 không hiểu `DISCONTINUED`, đọc trực tiếp DB sau eviction **cũng sẽ lỗi**. Cần release compatibility strategy:

- Deploy readers chấp nhận cả old/new values trước khi đổi DB.
- Hoặc tạm không route old nodes trong migration.
- Hoặc dùng converter/dual-field compatibility phù hợp.

### 22.3. Cached reference data có thể bị stale lâu

Một lookup list `shippingMethods` cached “vĩnh viễn” có thể không thấy method mới. Ngay cả khi không có JPA L2, application cache/CDN có thể giữ list. Đặt explicit invalidation theo lifecycle của reference data.

### 22.4. Đổi ý nghĩa của cùng một mã

Nếu `status='ACTIVE'` giữ nguyên string nhưng behavior nghiệp vụ đổi từ “visible” sang “sellable”, old cache entries vẫn map được nhưng cho quyết định sai. Dùng semantic version của rules/read model, không chỉ schema/JSON version.

## 23. Thay đổi bên ngoài khi ứng dụng vẫn phục vụ lưu lượng

Có ba hướng vận hành:

### 23.1. Online, eventual consistency

Cho external writer commit, phát change events, subscriber evict và chấp nhận stale trong freshness budget. Phù hợp catalog preview hoặc analytics có as-of watermark, **không** tự phù hợp với checkout/security decisions.

### 23.2. Online nhưng bảo vệ đường quyết định quan trọng

Cho catalogs cache stale trong một thời gian ngắn, nhưng checkout đọc/revalidate authoritative Product/Price/Inventory trong transaction ở primary DB và lưu price snapshot đúng domain policy.

### 23.3. Maintenance/cutover window

Nếu data transformation không backward compatible hoặc không chấp nhận mixed states:

1. Ngừng/giảm traffic của những endpoints liên quan.
2. Drain in-flight writes.
3. Commit migration và validate data.
4. Invalidate/switch cache generation.
5. Khởi động compatible readers/writers.
6. Mở traffic và monitor.

### 23.4. Không dựa vào read-only banner để chặn mọi writes

Một banner frontend không ngăn direct API calls, background jobs, consumers hoặc service-to-service writers. Maintenance gate phải enforce ở server/routing/DB permissions phù hợp.

### 23.5. Đóng cache không có nghĩa đóng mọi traffic

Có thể tạm bypass cache cho riêng Product reads trong thời gian backfill, nhưng nếu DB không chịu được traffic gốc, lại cần rate limits hoặc maintenance mode. Tính capacity trước.

## 24. Runbook khi DBA sửa dữ liệu khẩn cấp

Giả sử phải sửa giá sai Product#42 mà không có thời gian triển khai code.

### 24.1. Trước khi sửa

- Xác định tenant, business key, PK và tất cả cached representations liên quan.
- Đọc row hiện tại, version, updated_at, status và các FK/reference cần thiết.
- Xác nhận người phê duyệt, ticket/correlation ID, mức ảnh hưởng và lịch thao tác.
- Xác nhận các app nodes, cache backends, read replicas và maintenance restrictions.
- Chọn cách rollback/reverse operation và cách đo success.

### 24.2. Mẫu SQL sửa có guard

```sql
BEGIN;

UPDATE products
SET price = 120000,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 42
  AND tenant_id = 'TENANT_A'
  AND version = 7;

-- Kiểm tra affected rows == 1 theo client/DB tooling.
-- Nếu không đúng, ROLLBACK và điều tra; không COMMIT bừa.

COMMIT;
```

SQL minh họa cho một **numeric @Version** protocol. Nếu production có DB triggers/version management khác, phải theo thiết kế thực tế; không tự increment trùng. Không dùng raw ad-hoc SQL mà thiếu scope/approval trên production.

### 24.3. Sau commit

1. Ghi committed version/price và affected row count.
2. Phát/ghi durable invalidation cho Product#42 và dependent caches.
3. Xác nhận tất cả nodes/cache regions được bao phủ hoặc chuyển generation.
4. Chờ replica/source watermark nếu read path dùng replica.
5. Truy vấn bằng DB primary và qua read API với các node routes đại diện.
6. Monitor cache hit rate, stale-read metrics, DB load và errors.
7. Ghi audit operation/correction result, không đóng ticket chỉ vì SQL commit.

### 24.4. Nếu invalidate thất bại

Không rollback DB một cách tùy tiện chỉ vì Redis lỗi **sau** commit. Chọn:

- Retry durable invalidation.
- Temporarily bypass affected cache/read path.
- Evict broader region/generation với thông báo vận hành.
- Giới hạn hoặc disable affected endpoint nếu consistency bắt buộc.

### 24.5. Không gọi `evictAll()` như phản xạ đầu tiên

Một Product#42 thay đổi mà xóa toàn L2 của 100 triệu objects có thể làm hệ thống quá tải. Ưu tiên targeted invalidation khi biết dependencies; dùng broader flush khi impact không xác định hoặc cần force clean toàn hệ.

### 24.6. Runbook có tiêu chí hoàn thành

Ví dụ:

```text
DB row Product#42 price=120000, version=8
API read via all traffic-serving nodes returns compatible price
Product detail/list/report caches invalidated or generation advanced
Replica watermark >= correction commit watermark (if applicable)
No stale error alarms after configured propagation deadline
No unexpected DB overload
Audit ticket captures correction and verification
```

Nếu một tiêu chí chưa đạt, chưa thể tuyên bố sửa dữ liệu đã được phản ánh trên mọi read path.

## 25. Restore backup và thay đổi tập dữ liệu trên diện rộng

Database restore/PITR/clone có thể làm **toàn bộ cache generation không còn phù hợp**, thậm chí khi row IDs/version trùng với trước restore.

### 25.1. Trường hợp nguy hiểm

```text
Before restore:
 Product#42 price=120000 version=9
 Cache holds price=120000 version=9

Restore DB to older snapshot:
 Product#42 price=100000 version=7

Cache still holds post-restore state.
```

Nếu cache có persisted keys/Redis namespace cũ, application sau restart có thể tiếp tục đọc dữ liệu không tồn tại trong DB restored.

### 25.2. Release/generation không được suy duy nhất từ numeric row version

Sau restore, version có thể **quay lùi**. Một cache compare-and-set “chỉ nhận version lớn hơn” có thể bác đúng restored state. Cần **database incarnation/restore epoch** hoặc toàn namespace invalidation khi point-in-time restore.

### 25.3. Quy trình

- Không route traffic tới DB restored cho tới khi data/cache topology được đồng bộ.
- Bump global cache generation/database incarnation ID.
- Evict/bypass old cache namespaces; purge incompatible query/application cache results.
- Kiểm tra node startup không còn dùng stale persisted local cache.
- Verify sample business IDs và aggregate row counts.
- Mở traffic có giám sát và rollback plan.

### 25.4. Không quên search index và derived stores

Elasticsearch/OpenSearch, materialized views, analytics warehouse và application cache có thể phản ánh trạng thái **trước restore**. Đó là derived state cần rebuild/reconcile, không chỉ một key Redis.

## 26. Cache và read replica: hai nguồn stale khác nhau

Một report có thể đọc dữ liệu cũ dù ứng dụng đã invalidate mọi cache.

```text
T0: DBA commit price=120000 on primary.
T1: All local/L2/Redis caches evicted.
T2: API cache miss, SELECT from read replica.
T3: Replica still at price=100000.
T4: API repopulates cache price=100000.
T5: Replication catches up to price=120000.
```

Khi cache fill từ replica đang trễ, stale state có thể sống tiếp sau khi replica bắt kịp.

### 26.1. Ngăn repopulation từ stale replica

Một số lựa chọn:

- Khi đổi dữ liệu nhạy cảm, route read/refresh tới **primary** cho đến khi replica đạt commit watermark.
- Không populate shared cache từ replica nếu source freshness chưa đạt yêu cầu.
- Dùng replica lag monitoring, LSN/GTID/watermark protocol tùy DB, không tự đoán từ thời gian system clock.
- Sau catch-up, invalidate lần nữa các derived keys có thể đã bị fill bằng old state.

### 26.2. Primary read chưa đủ nếu L1 giữ object cũ

EntityManager đang có Product#42 ở L1 có thể trả cached state ngay cả khi connection đã route primary. Cần transaction/context strategy phù hợp.

### 26.3. Replica freshness contract

Cho dashboard chấp nhận 30 giây lag, expose `dataAsOf`/watermark có căn cứ từ replica/pipeline. Với checkout hoặc permission revocation, route critical decision queries tới authoritative source theo policy.

### 26.4. TTL không cần bằng replica lag

TTL 5 giây với replica trễ 10 giây có thể khiến cache liên tục lấy dữ liệu cũ. Freshness policy phải xét **source freshness**, không chỉ cache item age.

### 26.5. Cross-node consistency

Node A route primary, node B route replica và cùng ghi Redis cache sẽ có incoherence nếu B stale repopulates value. Chỉ các readers có nguồn đủ mới được phép fill shared authoritative read cache, hoặc dùng version fencing.

## 27. Multi-tenancy và cache isolation

Trong multi-tenant systems, stale cache không chỉ là lỗi hiển thị mà còn có thể là **rò dữ liệu**.

### 27.1. Shared-table tenancy

Nếu products có `tenant_id`, một service query phải scope:

```java
Optional<Product> findByIdAndTenantId(
    Long productId, String tenantId);
```

Application cache key phải phản ánh tenant:

```text
productDetails:{tenantId}:{productId}
```

### 27.2. Tenant không chỉ là tham số từ client

Lấy tenant scope từ authenticated principal/authorized delegation. Nếu client được tự cung cấp `tenantId` bất kỳ vào cache key, có thể dẫn tới cross-tenant cache probing hoặc insecure direct object reference.

### 27.3. JPA L2 tenant handling

Một provider có multitenancy support có thể encode tenant identifier trong cache key; không tự kết luận L2 cache luôn trộn tenant chỉ vì PK trùng. Tuy nhiên phải test provider version/config và custom cache integration để đảm bảo không có cross-tenant entry collision.

### 27.4. Eviction tenant-specific

`emf.getCache().evict(Product.class, 42L)` dùng entity type+ID API tiêu chuẩn, không nhận tenant argument. Trong một persistence unit multi-tenant với composite keys hoặc provider-specific tenant-aware cache, phạm vi hành vi eviction cần kiểm tra rõ. Khi eviction phải chính xác theo tenant, cân nhắc provider-supported API, proper tenant context hoặc region-level invalidation nếu không thể định tuyến an toàn; không tự dựng bare ID key cho internal Hibernate cache.

### 27.5. Authorization cache nguy hiểm hơn catalog cache

Ví dụ user bị thu hồi quyền ADMIN nhưng local role cache vẫn giữ permission:

```text
Database: user role=USER
Cache: user role=ADMIN
API: authorization based on cached role -> accepts forbidden action
```

Với permission revocation, cần consistency protocol mạnh: authoritative decision path, centralized session/token versioning, synchronous revocation or short-lived credentials theo threat model; không coi TTL dài như policy đủ an toàn.

### 27.6. Row-level security và bypass writers

Database RLS, Hibernate filters hoặc @TenantId có thể hạn chế một số queries/writers, nhưng cache application tự dựng có thể bypass scope nếu key sai. Test read/write/eviction trên toàn bộ data boundaries.

### 27.7. Cache poisoning từ negative lookup

Nếu `productDetails:TENANT_A:42` bị cache `NOT_FOUND` trong khi Product#42 được tạo từ external writer, API có thể tiếp tục trả 404. Negative caching cần TTL phù hợp và invalidation trên INSERT, không chỉ UPDATE/DELETE.

## 28. Negative caching và dữ liệu mới

Không có Product#99 tại T0:

```text
T0 API GET Product#99 -> DB no row -> cache NOT_FOUND.
T1 ERP creates Product#99 -> COMMIT.
T2 API GET Product#99 -> cached NOT_FOUND -> 404.
```

### 28.1. Cache negative results có lý do

Nó giảm tải DB cho IDs không tồn tại hoặc abuse traffic. Nhưng external INSERT/RESTORE phải invalidates negative entry.

### 28.2. Cache key cần chứa permissions

Không cache một response “not found” do caller A thiếu quyền dưới key dùng chung cho caller B có quyền. Có thể tách 403/404-hiding semantics khỏi raw entity existence cache.

### 28.3. Không giữ NOT_FOUND vĩnh viễn

Nếu IDs có thể được tạo sau đó hoặc nghiệp vụ cho phép restore, đặt TTL ngắn và invalidation khi create/restore event.

### 28.4. Tombstones

Soft-deleted product có thể được cache như tombstone. Khi restore, invalidates tombstone và list/search results. Nếu id reuse xảy ra, cache generation/DB incarnation cũng cần xét.

### 28.5. Deletes và stale references

Khi external SQL xóa Product#42, cache entity/detail/list/collection có thể giữ bản ghi “ma”. Với FK cascades, xóa một parent có thể ảnh hưởng hàng nghìn children, cần invalidate **các entity types liên quan**, không chỉ một ID.

## 29. Collection và relationship caches sau external SQL

Không phải mọi thay đổi là update một scalar column.

### 29.1. Chuyển sản phẩm sang category khác

```sql
UPDATE products
SET category_id = 7,
    version = version + 1
WHERE id = 42
  AND category_id = 5;
```

Sau commit, cần xem:

- Product#42 entity data.
- Category#5 products collection (mất một item).
- Category#7 products collection (thêm item).
- Cached category listing/count/search results.
- Any derived materialized views.

### 29.2. Không chỉ evict category 7

Cache old category 5 vẫn có thể hiển thị Product#42; new category 7 có thể thiếu. Invalidation dependency graph phải xét **old parent và new parent**, nên change event có thể cần old/new category IDs.

### 29.3. Join-table changes

Ví dụ SQL:

```sql
INSERT INTO product_tags (product_id, tag_id)
VALUES (42, 9);
```

Nếu Hibernate cache `Product.tags` collection, entity Product#42 data region eviction có thể chưa clear cached association membership. Cần provider collection eviction hoặc broader region action.

### 29.4. `@ElementCollection`

External SQL sửa `product_attributes` collection table: entity root field data có thể không đủ thể hiện changes; kiểm tra collection cache regions và projection/results caches.

### 29.5. Database ON DELETE CASCADE

External DELETE parent có thể xóa child rows do FK. JPA không chạy per-entity callbacks và cache provider không có cơ sở biết danh sách child IDs qua SQL ngoài process. Có thể cần region-wide eviction hoặc change capture đầy đủ trên child table.

### 29.6. Read models theo relationship count

Nếu cached `productCountByCategory`, chuyển một product phải giảm count old category và tăng count new category. Evict Product entity đơn lẻ không sửa hai cached aggregates.

## 30. Query cache và pagination sau data migration

Một API list active products:

```java
Page<ProductListRow> findActiveProducts(
    String tenantId, Pageable pageable);
```

List result phụ thuộc vào:

- Row membership theo status/tenant.
- Sort by name/price/updatedAt.
- Pagination offsets/cursors.
- Total count.

Nếu migration đổi status của 20.000 products, cached pages/counts có thể sai theo nhiều cách.

### 30.1. Page membership thay đổi

Product#42 từ ACTIVE thành DISCONTINUED phải biến mất khỏi mọi list active. Nếu cache chỉ evict Product#42 nhưng page chứa ID 42 vẫn được cached, API có thể vẫn trả nó hoặc trả thiếu một item ở trang phù hợp.

### 30.2. Sorting thay đổi

Giá Product#42 từ 100000 thành 120000 có thể chuyển vị trí giữa page 1 và page 2 nếu sort theo price. Invalidate một page không đủ khi item dịch qua page boundaries.

### 30.3. Count query cache

`COUNT(status='ACTIVE')` cần refresh khi UPDATE/INSERT/DELETE thay status; không có entity nào để identify cho scalar query result. Invalidate query/report region hoặc cache key phụ thuộc toàn dataset.

### 30.4. Cursor vs snapshot

Nếu user đang phân trang list trong lúc backfill, cả offset và keyset có thể có biến động do data thay đổi. Khi report cần tái lập/consistency, dùng snapshot/version/watermark; không kỳ vọng cache invalidate tạo snapshot coherence.

### 30.5. Cache definitions là một phần của API contract

List cache key cần bao gồm tenant, filters, sort, page/size, permissions, currency, locale và schema/version nếu chúng ảnh hưởng output. Thiếu một dimension có thể cho ra dữ liệu không tương ứng request.

## 31. Cache stampede sau triển khai

Full cache eviction có thể tạo một lượng lớn cache misses cùng lúc.

### 31.1. Kịch bản

```text
Before: 99% requests hit Redis
Deploy: FLUSH all Product caches
Next second: 5,000 requests miss simultaneously
DB: 5,000 expensive SELECTs/joins
Pool: saturated
Latency: p99 increases
```

### 31.2. Biện pháp

- Chỉ evict changed IDs/regions cần thiết.
- Bump namespace và warm một tập keys phổ biến từ **committed correct source** trước traffic cutover.
- Request coalescing/single-flight cho cùng key.
- Stagger cache expiration và dùng jitter TTL.
- Rate-limit expensive report/rebuild queries.
- Autoscale reads hoặc tạm tăng DB capacity có kế hoạch.
- Theo dõi pool, DB CPU, cache hit/miss, error rates.

### 31.3. Không “stale-while-revalidate” cho mọi dữ liệu

Stale-while-revalidate phù hợp với nội dung ít rủi ro như product preview, nhưng có thể không phù hợp với permission revocation, active bank balance hoặc checkout price. Mọi lớp stale-serving phải dựa trên business consistency contract.

### 31.4. Prewarm có thể tạo dữ liệu sai

Warmup từ replica chưa catch up hoặc từ DB khi migration chưa xong có thể chứa old/mixed state. Kiểm tra source watermark/data version trước khi populate generation mới.

### 31.5. Cache không phải giải pháp chữa SQL chậm

Nếu cache flush gây DB collapse, cần đo query/index/pagination/capacity và giảm read cost, không chỉ kéo TTL vô hạn để che performance issue.

## 32. Metrics và observability

Một cache invalidation protocol cần **quan sát được**.

### 32.1. Metrics nên có

| Metric | Câu hỏi trả lời |
|---|---|
| L1/L2 cache hit/miss | Request thực sự được cache phục vụ bao nhiêu? |
| Region size/eviction count | Có đúng region được evict không? |
| Query-cache hit/miss/stale signals | Query result còn dùng cache không? |
| Redis key eviction/error/latency | Delete/bump generation có thành công không? |
| Event delivery lag | Sau DB commit bao lâu invalidation được áp? |
| Outbox oldest pending age | Có event bị kẹt/replay chưa? |
| CDC consumer lag | Có change outside app chưa được xử lý? |
| Replica apply lag/watermark | Reader nguồn có mới chưa? |
| Cache generation mismatch | Node nào đang phục vụ namespace cũ? |
| DB QPS/pool wait/CPU | Cache purge có gây thác misses không? |
| Stale-read audit sampling | Dữ liệu API khác authoritative DB bao nhiêu? |
| Error rate/p95/p99 | Người dùng có bị ảnh hưởng khi invalidation không? |

### 32.2. Hibernate Statistics

Hibernate có metrics/statistics cho second-level cache/query cache khi được bật; tên counter/API và overhead phụ thuộc version/provider. Trong production nên thiết lập sampling/configuration phù hợp, không log toàn bộ dữ liệu chi tiết gây overhead.

### 32.3. Correlation ID

Mỗi change event nên có:

```text
eventId
tenantId
entityType/entityId
sourceCommitTime or watermark
cacheGeneration
sourceService/migrationId
traceId
```

Thông tin cần tối thiểu đủ truy vết; tránh đưa full PII/secrets vào log/event.

### 32.4. Alert theo freshness budget

Nếu quy định “Catalog cache stale tối đa 30 giây”, alert khi outbox/CDC invalidation lag hoặc stale-read sampling vượt giới hạn. Không chỉ cảnh báo khi Redis down; cache có thể online nhưng stale.

### 32.5. Không suy cache freshness chỉ từ hit rate

99% hit rate có thể là 99% câu trả lời **cũ** sau migration. Hit rate là performance metric, không phải correctness metric.

### 32.6. Đo business discrepancy

Đối chiếu một tập sample IDs hoặc aggregates giữa authoritative DB và API/read models, có tenant/category/version dimensions, vừa phát hiện stale data vừa phát hiện transform/migration logic sai.

## 33. Test môi trường: database, EMF, L2 và Redis thật

Một unit test mock cache không chứng minh provider invalidation semantics hoặc race với external SQL. Cần integration tests theo lớp.

### 33.1. Test L1

1. Tạo Product price=100000 và commit.
2. EM A `find` Product#42.
3. External JDBC connection UPDATE price=120000 + COMMIT.
4. EM A `find` lại, quan sát managed state cũ.
5. `refresh` hoặc tạo EM mới/bypass L2 phù hợp; assert read phản ánh DB theo isolation.

### 33.2. Test L2

1. Bật L2 với provider/cache region thực.
2. EM A load Product, close.
3. External JDBC UPDATE + COMMIT.
4. EM B load Product; xác nhận setup có cache hit (nếu test nhằm chứng minh stale).
5. Evict Product ID trong correct EMF/cache region.
6. EM C load Product và xác nhận fresh value.

Không ép test phải thấy stale khi L2/provider không bật hoặc query không cacheable; mục tiêu là kiểm tra **cấu hình đang dùng**.

### 33.3. Test query cache

1. Cache một query count/list có provider support.
2. External SQL thay status/insert/delete.
3. Kiểm tra query result old (nếu cache hit theo config).
4. Invalidate query region/query-dependent cache.
5. Chạy lại và assert result đúng.

### 33.4. Test Spring Cache/Redis

1. Gọi API để populate `productDetails:tenant:id`.
2. Thay row bằng external JDBC.
3. Trigger invalidation event.
4. Assert key bị xóa/generation tăng và API trả new value.
5. Chạy test với hai app instances hoặc hai local cache managers nếu topology cần.

### 33.5. Test source replica

Nếu production reads qua replica, integration test cần kiểm tra phản ứng khi replication lag: không populate shared cache từ stale replica khi policy cấm, hoặc as-of/TTL minh bạch nếu eventual consistency cho phép.

### 33.6. Test rollback

External writer UPDATE rồi ROLLBACK; cache không được claim có new committed value. Nếu có event, nó không được trở thành durable committed change event. Assert DB and cache/response outcomes.

### 33.7. Test transaction liveness

Nếu EM A vẫn đang trong REPEATABLE READ transaction, sau external COMMIT, `refresh` có thể không thấy change như application kỳ vọng. Test riêng snapshot isolation so với L1/L2 stale behavior.

### 33.8. Test teardown

Reset DB/cache namespace được cô lập cho test, không xóa Redis production keys. Chờ worker events complete và close EM/DataSource resources; tránh asynchronous invalidation từ test trước ảnh hưởng test sau.

## 34. Ví dụ integration test: thay đổi bằng JDBC bên ngoài JPA

Đây là cách minh họa sự khác nhau giữa state trong EM và dữ liệu committed trong DB.

### 34.1. Setup

Giả định:

- JUnit Jupiter và Spring Test hoặc bootstrap JPA thủ công.
- Một PostgreSQL test instance được cấu hình cùng migrations như deployment.
- Product#42 đã được seed và commit với price=100000.
- `EntityManagerFactory`/`DataSource` đã được thiết lập.
- Test method không bị bọc một transaction rollback vô tình giữ fixture chưa commit.

### 34.2. Dùng một JDBC connection độc lập

```java
void externalSqlPriceChange(
        DataSource dataSource,
        long productId,
        BigDecimal newPrice) throws SQLException {

    try (Connection c = dataSource.getConnection()) {
        c.setAutoCommit(false);

        try (PreparedStatement ps = c.prepareStatement(
                """
                UPDATE products
                   SET price = ?,
                       version = version + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                """)) {
            ps.setBigDecimal(1, newPrice);
            ps.setLong(2, productId);
            int changed = ps.executeUpdate();

            if (changed != 1) {
                throw new IllegalStateException(
                    "Expected exactly one product");
            }
            c.commit();
        } catch (SQLException | RuntimeException failure) {
            c.rollback();
            throw failure;
        }
    }
}
```

Đây là **test helper** cho direct JDBC; production writer phải thêm tenant/authorization predicate, version protocol, affected-row safeguards, audit/outbox theo requirement. Code đặt catch kiểu `Exception` với method khai báo `throws SQLException` cần điều chỉnh exception contract khi triển khai (ví dụ catch SQLException và RuntimeException riêng); mục đích ở đây là minh họa một JDBC connection/commit tách khỏi JPA.

### 34.3. Kiểm tra L1 stale

```java
@Test
void managedEntityDoesNotAutoRefreshAfterExternalSql()
        throws Exception {

    EntityManager em = emf.createEntityManager();
    try {
        Product first = em.find(Product.class, 42L);
        BigDecimal oldPrice = first.getPrice();

        externalSqlPriceChange(
            dataSource, 42L,
            new BigDecimal("120000.00"));

        Product again = em.find(Product.class, 42L);

        assertSame(first, again);
        assertEquals(
            0, oldPrice.compareTo(again.getPrice()));

        // To observe new DB state, choose an operation
        // appropriate for this transaction isolation:
        em.refresh(first);
        assertEquals(
            0,
            new BigDecimal("120000.00")
                .compareTo(first.getPrice()));
    } finally {
        em.close();
    }
}
```

Test này giả định không có enclosing repeatable-read snapshot ngăn fresh visibility và không có trigger/transaction side effect khác. Nếu có, phải điều chỉnh transaction/context setup và ghi rõ expected result. Đây là **test-case minh họa**, không phải lời hứa rằng `refresh` luôn xuyên mọi DB snapshot.

### 34.4. Kiểm tra L2 với fresh EM

Nếu L2 bật:

```java
EntityManager a = emf.createEntityManager();
Product loaded = a.find(Product.class, 42L);
a.close();

externalSqlPriceChange(dataSource, 42L, nextPrice);

// No guarantee this is a DB read if L2 is still populated.
EntityManager b = emf.createEntityManager();
try {
    Product maybeStale =
        b.find(Product.class, 42L);
} finally {
    b.close();
}

emf.getCache().evict(Product.class, 42L);

EntityManager c = emf.createEntityManager();
try {
    Product fresh = c.find(Product.class, 42L);
    // Assert price after ensuring source is primary/current.
} finally {
    c.close();
}
```

Không nên dùng `emf.getCache().contains()` làm bằng chứng query đã thật sự hit L2; kiểm tra Hibernate cache statistics/SQL logs trong test có mục đích đó.

### 34.5. Vì sao test không phải một unit test?

Nó cần database/connection/transaction thật, cache provider behavior thật và second-level cache config tương ứng. Mock `Cache.evict` chỉ chứng minh method được gọi, không chứng minh stale state biến mất.

## 35. Kiểm thử transaction và invalidation race

Một test có hai transactions:

```text
Reader R: begin, SELECT old price, block before cache PUT
Writer W: begin, UPDATE price, COMMIT
Writer W: invalidate Product cache
Reader R: complete cache PUT of old price
Reader S: GET cached Product -> ?
```

### 35.1. Kịch bản deterministic

Dùng `CountDownLatch`:

```java
CountDownLatch readerFetchedOld =
    new CountDownLatch(1);
CountDownLatch allowReaderToPopulate =
    new CountDownLatch(1);
```

Reader:

```java
ProductView oldView = loadFromDatabaseSnapshot();
readerFetchedOld.countDown();
if (!allowReaderToPopulate.await(
        10, TimeUnit.SECONDS)) {
    throw new TimeoutException(
        "Reader not released");
}
cache.put(key, oldView);
```

Coordinator:

```java
assertTrue(readerFetchedOld.await(
    10, TimeUnit.SECONDS));
writerUpdateCommitAndEvict();
allowReaderToPopulate.countDown();
```

Cuối cùng assert source DB mới nhưng naive cache có thể giữ old; sau đó bật generation/version-fence strategy và assert old fill bị bỏ qua.

### 35.2. Đặt event markers đúng chỗ

`readerFetchedOld.countDown()` phải phát **sau khi reader có dữ liệu cũ**, không trước SQL. `writerUpdateCommitAndEvict()` chỉ return sau DB commit và thực hiện invalidate theo designed protocol.

### 35.3. Không dùng `Thread.sleep`

Sleep 100ms không bảo đảm reader đã query old snapshot hay writer đã commit. Timed latches giúp test chứng minh đúng ordering thay vì hy vọng scheduler.

### 35.4. Test race nhiều node

Nếu có pod local caches, thử:

- Node A old local cache, node B old local cache.
- External DB change commits.
- Invalidation delivered to A nhưng B chưa nhận.
- B request phải đi vào safe path hoặc chấp nhận stale theo contract.
- Khi B replay event/epoch check, phải thấy new data.

### 35.5. Test event lost/delayed

Simulate event bus outage sau committed change. Với outbox durable, relay có thể resume và invalidate; nếu consistency bắt buộc, endpoint có thể bypass affected cache trong outage. Test recovery và lag alert, không chỉ happy-path publish.

## 36. Kiểm thử rolling deployment cache compatibility

Khi cache payload format đổi:

```text
Release v1 -> Redis key schema-v1
Release v2 -> Redis key schema-v2
```

Test:

1. v1 app instance tạo cached data v1.
2. v2 app instance đọc cùng DB, không deserialize nhầm v1 object nếu không compatible.
3. v2 tạo v2 cached data.
4. Cả v1 và v2 vẫn chạy trong coexistence window.
5. External writer đổi Product#42; invalidation protocol áp đúng cả generations hoặc cutover strategy.
6. Sau route switch, v2 trả state mới.
7. Rollback simulation không đòi đọc cache payload mà v1 không hiểu.

### 36.1. Vì sao không kiểm thử chỉ trên một process?

Trong một process, class definitions không dễ mô phỏng hai different deployed releases chạy đồng thời. Dùng integration environment với hai app builds/containers hoặc dedicated compatibility contract tests cho serializer/cache key formats.

### 36.2. Chữ “version” có bốn nghĩa

Test cần phân biệt release version, schema version, entity `@Version` và cache namespace epoch. Một mismatch có thể xảy ra dù entity version không đổi.

### 36.3. Rollback

Đánh giá rollback v2→v1 sau khi đã migrate DB. Nếu DB có enum mới mà v1 không parse được, cache purge không giải quyết; cần compatible readers hoặc formal rollback migration plan.

### 36.4. Deploy validation

Release gate có thể kiểm tra:

```text
All active nodes understand new DB values
All active nodes use intended cache schema generation
Outbox/CDC lag within budget
Representative read API values match primary DB
No abnormal cache miss storm/DB overload
Rollback/read compatibility documented
```

## 37. Không phải dữ liệu nào cũng nên cache

Cache có chi phí consistency. Trước khi bật L2/Redis, cần cân nhắc:

| Dữ liệu | Có nên cache? | Lưu ý |
|---|---|---|
| Quốc gia, đơn vị đo ít đổi | Thường có thể | Invalidate khi metadata migration |
| Product category name | Có thể | TTL/evict khi admin hoặc import sửa |
| Product price cho browsing | Có thể, có freshness budget | Checkout cần price source/revalidation policy riêng |
| Inventory availability | Rất thận trọng | Cache chỉ để hiển thị, không làm source quyết định trừ tồn kho |
| User role/permissions | Cực kỳ thận trọng | Revocation consistency, scope và authorization |
| Account balance | Cực kỳ thận trọng | Không dùng stale cache cho transfer authorization |
| Audit ledger | Có thể cache immutable views nếu phù hợp | Không bỏ qua append/adjustment read requirements |
| Long-running report | Snapshot/materialized view thường hợp lý | As-of/version và reconciliation |

### 37.1. Đừng bật L2 chỉ vì query nhiều

Một entity frequently updated bởi nhiều external writers có invalidation cost cao. Khi invalidation không đáng tin, tắt L2 cho entity ấy có thể **an toàn và đơn giản hơn** so với nỗ lực sửa stale cache bằng TTL dài.

### 37.2. Đừng cài cache ở mọi tầng

Nếu Spring Cache, Hibernate L2, query cache và CDN đều giữ cùng một dữ liệu nhưng không có dependency map, mọi migration phải invalidate bốn lần. Chọn một tầng cache có semantics rõ có thể tốt hơn nhiều tiers khó kiểm soát.

### 37.3. Cache immutable data

Data versioned theo immutable IDs/content hashes có thể dễ cache lâu hơn vì version mới tạo key mới, không sửa key cũ. Nhưng nếu tham chiếu “current version” cũng được cache, key current pointer vẫn phải invalidate khi release đổi.

### 37.4. Security-critical paths

Với permission/financial decisions, ưu tiên authoritative reads hoặc cache protocol có chứng minh consistency. Nếu không thể chứng minh, **bypass hoặc disable cache** trên đường quyết định quan trọng.

## 38. Incident: giá đã sửa nhưng API vẫn trả giá cũ

### 38.1. Triệu chứng

DB primary:

```text
Product#42 price = 120000, version=8
```

API node A:

```json
{"id":42,"price":120000}
```

API node B:

```json
{"id":42,"price":100000}
```

### 38.2. Điều tra theo tầng

1. Kiểm tra node B response thực đến từ local application cache hay repository.
2. Kiểm tra Redis key/namespace/version (không log sensitive values).
3. Kiểm tra Hibernate L2/query-cache hit counters trên node B.
4. Xác nhận EM mới/transaction mới hay extended L1 context.
5. Xác nhận B route primary hay replica.
6. Kiểm tra outbox/CDC event cho Product#42 và delivery tới B.
7. Kiểm tra rolling deployment, schema/cache generation mismatch.

### 38.3. Khắc phục tạm thời

Nếu sự cố ảnh hưởng price checkout:

- Chặn hoặc bypass stale cache trong authoritative checkout path.
- Ép DB primary/current transaction validation.
- Targeted invalidate key + entity/query regions trên các nodes, theo provider topology.
- Nếu không xác định dependency, dùng broader cache generation reset có capacity plan.

### 38.4. Khắc phục lâu dài

Lập dependency map, bắt external writers đi qua outbox/CDC hoặc runbook, monitor propagation lag, thêm integration test hai nodes và data migration rehearsal.

### 38.5. Hậu kiểm

Không ghi kết luận “cache đã được clear” mà không chỉ rõ:

```text
Cache tier
Node(s)
Region/key/namespace
Eviction time/event ID
Data source/watermark
Verification query
User-visible recovery time
```

## 39. Incident: rollback release không đọc được cached values

### 39.1. Triệu chứng

v2 serializer ghi một DTO field enum mới vào Redis. Sau rollback ứng dụng v1:

```text
IllegalArgumentException: Unknown enum value
JsonMappingException: Cannot deserialize ...
ClassCastException / serialVersionUID mismatch
```

### 39.2. Không giải quyết bằng JPA `clear`

Lỗi ở Redis serialized payload và Java application DTO schema; xóa L1 context không liên quan.

### 39.3. Cách xử lý

- Đưa v1 vào read path chỉ với compatible cache namespace, hoặc bypass incompatible cache.
- Purge version-specific DTO keys, không tùy tiện flush Redis toàn tổ chức.
- Đảm bảo DB schema/data vẫn tương thích với v1; nếu không, khôi phục compatible reader/deploy strategy.
- Monitor cache misses/DB load khi fallback.

### 39.4. Phòng ngừa

Serialization contract tests, versioned cache keys, expand–migrate–contract, backwards compatibility hoặc zero-downtime release protocol.

## 40. Incident: CDC backlog sau migration lớn

### 40.1. Triệu chứng

Data backfill update 10 triệu products, CDC queue tăng mạnh:

```text
Commit completed
CDC backlog: 10 million events
Redis invalidation delayed: hours
API still serving cached status values
```

### 40.2. Phân loại rủi ro

Nếu cached status chỉ hiển thị ít quan trọng, có thể chấp nhận lag với banner/as-of watermark. Nếu status quyết định quyền bán hoặc chính sách compliance, phải bypass/block affected read path, không chờ queue tự đuổi kịp trong im lặng.

### 40.3. Khắc phục

- Tạm chuyển read path sang authoritative source hoặc new generation.
- Nếu change scope rộng, invalidate region/namespace theo migration checkpoint thay vì gửi delete cho từng ID.
- Giữ CDC offsets đúng, không bỏ sự kiện mà các consumers khác cần.
- Throttle backfill/worker concurrency theo DB/queue capacity.
- Xác minh các events đến trễ không làm ghi stale payload vào cache generation mới.

### 40.4. Hậu kiểm

Mỗi data migration lớn cần **cache impact estimate** và **event-volume estimate** cùng data/DB risk plan.

## 41. Các anti-pattern thường gặp

### 41.1. “SQL đã COMMIT nên mọi client thấy dữ liệu mới”

Sai vì L1, L2, query/application caches, CDN và replica đều có thể giữ state cũ. Chứng minh từng read path theo freshness contract.

### 41.2. Gọi `EntityManager.clear()` để xóa toàn hệ thống

`clear` chỉ detach managed state của **một EntityManager**. Nó không purge L2/Redis/query regions và có thể bỏ pending changes chưa flush.

### 41.3. Gọi `getCache().evictAll()` rồi tuyên bố Redis đã mới

JPA shared `Cache` không phải Spring CacheManager. Phải invalidates DTO/application cache độc lập.

### 41.4. Evict trên một pod khi còn nhiều local caches

Node B/C có thể giữ L2/Caffeine data cũ. Phải dùng cluster cache coherence, broadcast hoặc generation mechanism phù hợp.

### 41.5. Dùng TTL để thay quyền cập nhật ngay

TTL 5 phút không phù hợp nếu user vừa bị thu hồi quyền phải mất hiệu lực ngay. Dùng authoritative/security revocation protocol.

### 41.6. Evict trước transaction commit

Reader khác có thể miss cache, đọc DB old state và repopulate cache cũ trước commit. Chọn after-commit với awareness về residual race.

### 41.7. Tin rằng after-commit listener là durable event

JVM có thể chết sau DB commit nhưng trước eviction. Dùng durable outbox/CDC khi yêu cầu recoverable invalidation.

### 41.8. Tin rằng outbox bằng strong consistency

Outbox có delivery latency và không chặn stale reads trong window trước subscriber invalidation. Chọn consistency contract trung thực.

### 41.9. Cho cached reader populate từ replica chưa bắt kịp

Cache có thể bị nạp lại state cũ **sau khi đã evict**. Bảo vệ bằng source watermark/primary reads/fencing.

### 41.10. Bỏ tenant khỏi key

`productDetails:42` không đủ nếu ID chỉ unique trong tenant hoặc response phụ thuộc tenant. Dùng scoping đúng cả cache read và invalidation.

### 41.11. Không invalidate negative cache khi INSERT/RESTORE

API tiếp tục trả 404 dù row đã tồn tại. Negative cache là cache cần maintenance như positive entries.

### 41.12. Chỉ evict entity khi parent-child relationship thay đổi

Collection/query caches có thể giữ old membership. Invalidate old/new parent collection regions và derived lists khi cần.

### 41.13. Chỉ evict product detail khi đổi status

Active list/search pages, counts và reports vẫn stale. Lập dependency map cho cache keys và source tables.

### 41.14. Bỏ qua `@Version` trên external SQL

Stale managed writers có thể ghi đè external change nếu version protocol không được giữ. Nếu tăng version, vẫn phải invalidate readers.

### 41.15. DB trigger tăng version mà không kiểm tra tương thích JPA

Có thể double increment hoặc ORM nhận version không như kỳ vọng. Version management phải có single documented protocol và integration tests.

### 41.16. Coi `@Cacheable(true)` là đủ để cache chạy cluster-wide

Còn cache provider/region configuration, backend topology và invalidation consistency. Annotation không tự dựng distributed cache.

### 41.17. Xóa Redis `KEYS *` trong production vì một Product

Rủi ro block/load, xóa dữ liệu của các domains khác và cache stampede. Dùng exact keys, provider APIs, SCAN có kiểm soát hoặc generation key.

### 41.18. Cache entire JPA entity qua JSON serialization

Có thể kéo lazy proxies/association graphs, lộ fields và sinh incompatible cached payload giữa releases. Với application cache, ưu tiên stable DTO/read model và schema-versioned serializer.

### 41.19. Dùng một namespace cho incompatible DTO releases

Rolling deployment có thể gây deserialize exceptions hoặc dữ liệu thiếu fields. Version hóa cache representation hoặc giữ backward compatibility.

### 41.20. Invalidate trước khi old nodes ngừng repopulate

Old app có thể ghi old cache state/format sau purge. Cần drain/fence/namespace cutover.

### 41.21. Prewarm từ source chưa commit hoặc replica stale

Generation mới sẽ chứa dữ liệu cũ/mixed. Check committed state và source watermark trước warmup.

### 41.22. Cho migration update 10 triệu rows mà không dự đoán CDC volume

Event consumers/cache invalidation có thể lag hàng giờ. Lập batch/lag/region-invalidation plan.

### 41.23. Bỏ qua rollback compatibility

DB schema/enum đã đổi có thể khiến old release fail, dù cache được xóa hoàn toàn. Expand–migrate–contract và release rollbacks phải tính cả source data.

### 41.24. Nghĩ restart JVM đồng nghĩa flush mọi cache

Persistent Redis, distributed regions, browser cache và search index vẫn có thể giữ old state.

### 41.25. Đọc lại bằng cùng EM rồi coi là verification

L1 có thể trả cùng managed instance. Dùng fresh transaction/context, bypass shared cache hoặc direct JDBC khi xác minh authoritative DB state.

### 41.26. Không ghi nhận dữ liệu trước/sau khi thao tác khẩn cấp

Không có baseline, version, affected rows, event ID hay audit, rất khó chứng minh migration thành công và rollback thế nào.

### 41.27. Dùng full cache flush ngay giờ cao điểm

Có thể gây DB miss storm. Lên capacity/throttling/warmup plan, targeted eviction nếu có thể.

### 41.28. Chỉ đo hit rate

Cache hit cao có thể đang phục vụ stale state. Cần freshness/reconciliation metrics.

### 41.29. Giữ stale search indexes sau restore DB

Cache generation có thể mới, nhưng Elasticsearch/materialized views vẫn phản ánh snapshot trước restore. Derived stores phải được rebuild/reconciled.

### 41.30. Dùng test H2/mock Cache rồi suy production PostgreSQL/Redis đúng

L1/L2/driver/cluster/replica/race semantics phụ thuộc môi trường. Có integration tests với stack đủ gần production.

## 42. Bảng quyết định chiến lược cache

| Tình huống | Điểm khởi đầu hợp lý | Phạm vi cần kiểm tra |
|---|---|---|
| Một Product thay đổi qua JPA service | After-commit targeted eviction | L2, product DTO, list/query deps, nodes |
| DBA sửa một Product bằng SQL | Guarded SQL + version protocol + explicit invalidation | All caches, replica, audit |
| JDBC import vài nghìn products | Durable change events/batch invalidation | IDs, query/list caches, throughput |
| Backfill hàng triệu rows | Region/epoch cutover, maintenance or compatible live migration | CDC lag, mixed state, stampede |
| Enum/status migration | Compatible code rollout trước data change | Old nodes, serializers, cache schema |
| New DTO fields trong rolling deploy | Versioned cache schema keys | v1/v2 coexistence, rollback |
| Local L2 cache nhiều pods | Broadcast/cluster coherence/disable cache | Message delivery to all nodes |
| Redis product DTO cache | Targeted key eviction/namespace bump | Tenant-scoped keys, list pages |
| Critical stock/permission query | Primary authoritative read + lock/version protocol | L1, L2 bypass, transactional decisions |
| Long-running analytics | Snapshot/read model with as-of | Refresh watermark, reconciliation |
| Read replica lag | Wait for commit watermark or route primary | Stale repopulation, source freshness |
| External restore/PITR | New database incarnation/cache epoch | Full derived state, backward compatibility |
| Query cache aggregate stale | Provider query-region eviction/recompute | Scalar/list results, source tables |
| Negative cache stale 404 | Invalidate on insert/restore, short TTL | Existence and authorization scopes |
| Redis outage during invalidation | Durable retry + temporary bypass/disable | Cache downtime behavior, alerts |
| High cache miss after eviction | Controlled prewarm, load shedding | DB capacity, p95 latency |

### 42.1. Câu hỏi dẫn đường

Trước khi bật/giữ cache cho dữ liệu có external writers:

1. Ai là source of truth?
2. Những writers nào thay source đó?
3. Writer nào có gửi invalidation signal?
4. Cache nằm ở tier nào, node nào và region nào?
5. Cache key có tenant/permissions/schema/generation không?
6. Tối đa cho phép dữ liệu stale bao lâu?
7. Có thể có reader đã query old state rồi fill cache sau eviction không?
8. External changes có bump version và giữ optimistic locking contract không?
9. Mỗi backfill/release cần invalidate theo ID, region hay toàn namespace?
10. Có kiểm chứng DB/source watermark và sample API results không?
11. Event có durable/replay/idempotent không?
12. Nếu invalidation không hoạt động, hệ thống degrade an toàn bằng cách nào?

### 42.2. Không có một giải pháp cache tốt nhất cho mọi thứ

Catalog page có thể chấp nhận TTL 30 giây; checkout price cần revalidation; role revocation đòi security-specific protocol; restore database cần whole-generation invalidation. Thiết kế theo **ngữ nghĩa dữ liệu**, không chỉ theo cache engine.

## 43. Kế hoạch triển khai migration có cache: mẫu làm việc

### 43.1. Trước triển khai

1. Ghi rõ schema/data change, impacted tables/fields, estimated affected rows.
2. Liệt kê JPA entities/collections/query regions và application/cache keys phụ thuộc.
3. Đánh giá migrations có backward-compatible với old nodes không.
4. Xác định cache serialization format đổi hay chỉ value đổi.
5. Chọn generation/eviction/durable event strategy.
6. Đặt consistency SLA cho từng read path.
7. Đo event volume, backfill duration, Redis/DB capacity.
8. Chuẩn bị rollback/restore và cache incarnation plan.
9. Rehearse trên test/staging DB với traffic và cached entries đại diện.
10. Thống nhất owner/approval/runbook/observability.

### 43.2. Trong triển khai

1. Deploy compatible readers/writers hoặc đưa system vào maintenance gate phù hợp.
2. Xác nhận tất cả nodes đang chạy được phép đọc format/data states sắp xuất hiện.
3. Chạy migration theo batches/transaction checkpoints.
4. Theo dõi affected rows, DB locks, replica lag, outbox/CDC lag.
5. Giữ nguồn event/invalidation không bị mất.
6. Không switch new cache generation khi source còn chưa đủ/committed.
7. Quiesce old nodes nếu cần tránh old-format repopulation.
8. Commit final data version và verify authoritative source.
9. Invalidate region/keys hoặc switch generation đúng scope.
10. Route traffic/canary và kiểm tra production-like API responses.

### 43.3. Sau triển khai

1. So source DB values với results qua từng read path.
2. Xác nhận cache event lag đã nằm trong SLA.
3. Theo dõi cache misses, DB CPU/QPS/pool wait, p95/p99 latency.
4. Kiểm tra tenant isolation và authorization-critical endpoints.
5. Xác nhận negative caches, list pages, aggregates, collections đã được cập nhật.
6. Quét sample stale records và ghi metrics.
7. Chỉ contract old schema/cache generation sau khi old consumers đã ngừng.
8. Ghi audit/report release version, migration ID, event/epoch IDs.
9. Tạo follow-up cho các lệch dữ liệu hoặc cache keys chưa hết TTL.
10. Test hoặc chứng minh rollback route nếu còn yêu cầu.

### 43.4. Nếu không xác định được cache dependencies

Không chọn evict ngẫu nhiên một entity class và hi vọng đủ. Tạm bypass affected cache, giới hạn traffic nếu cần, hoặc dùng scoped region/global epoch reset theo runbook và đo DB capacity. Sau sự cố, bổ sung dependency map và automation invalidation.

## 44. An toàn vận hành, quyền và audit

### 44.1. Cache clear là thao tác vận hành nhạy cảm

`evictAll()` hoặc Redis namespace bump trên production có thể ảnh hưởng nhiều tenants và gây tải lớn. Endpoint admin thực hiện flush cache cần authentication, authorization, change approval, rate limit, audit và cấm raw arbitrary cache commands từ public API.

### 44.2. Không expose internal cache keys

Cache keys có thể chứa tenant/user/resource IDs hoặc pattern internal. Không trả toàn bộ key listing cho client không được phép; tránh tạo primitive cho cache enumeration hoặc invalidation DoS.

### 44.3. Sensitive data trong cached values

Product preview cache ít nhạy cảm hơn user session/role/payment DTOs. Dữ liệu nhạy cảm cần encryption/access control/retention policy của backend cache, không chỉ TTL.

### 44.4. Invalidation events phải trusted

Nếu client có thể gửi fake `ProductChanged(tenant=B,id=42)` vào event bus, họ có thể gây cache eviction storm hoặc kích hoạt logic sai. Authenticate event producers, validate event schema/scope và giới hạn consumer actions.

### 44.5. Audit

Ghi:

```text
who/what triggered invalidation
tenant and affected entity/region
source transaction/migration ID
time/commit watermark
nodes or cache generation updated
outcome/error/retry
verification evidence
```

Không log full financial/PII payload hoặc credentials.

### 44.6. Operational dry run

Với migration thay nhiều rows, có thể chạy dry-run query để đếm affected IDs/regions và ước lượng invalidation load. Tránh chạy DML rồi ROLLBACK như “dry run” trên production nếu triggers/external effects hoặc locks gây tác động; dùng controlled staging/query-plan paths.

### 44.7. Cảnh báo runbook

Nếu script database commit thành công nhưng invalidate thất bại, báo **PARTIAL_OPERATIONAL_COMPLETION** chứ không nói source change rollback. Tiếp tục retry/disable read cache và cập nhật incident status.

## 45. Bài tập thực hành

### Bài 1 — Phân loại cache

Ứng dụng có:

```text
EntityManager request scope
Hibernate L2 Product region
Hibernate query cache active products
Spring @Cacheable ProductView in Redis
Browser cached GET /products/42
```

DB Product#42 đổi giá. Hãy lập bảng loại cache nào có thể stale và thao tác làm mới tương ứng. Giải thích vì sao không có một `em.clear()` duy nhất giải quyết tất cả.

### Bài 2 — L1 stale state

Tạo `EntityManager` A, đọc Product#42. Bằng JDBC connection B update/commit price. A `find` lại. Giải thích identity map, sau đó dùng `refresh` trong transaction/isolation phù hợp để đọc giá mới.

### Bài 3 — Pending changes và clear

Trong một EM đang có `product.changePrice(...)` chưa flush, gọi `em.clear()`. Điều gì có thể xảy ra với local change? Đề xuất cách xác nhận application không mất dữ liệu khi clear.

### Bài 4 — L2 eviction đúng một entity

Viết hàm Java gọi:

```java
emf.getCache().evict(Product.class, productId);
```

Sau đó dùng EM khác đọc Product. Giải thích vì sao cùng EM đã load trước có thể vẫn stale.

### Bài 5 — Region-level eviction

Migration cập nhật 500.000 Product rows mà không lưu chính xác IDs. So sánh `evict(Product.class)`, `evictAll()` và catalog cache generation bump. Chọn phương án giảm tác động các cache domain khác.

### Bài 6 — `contains` không chứng minh dữ liệu mới

`Cache.contains(Product.class,42L)` trả true. Nó cho biết điều gì, và những kết luận nào **không** thể rút ra về price freshness?

### Bài 7 — Bypass L2

Viết JPA `find` với `jakarta.persistence.cache.retrieveMode=BYPASS`. Nếu entity đã managed trong L1 của cùng EM, có chắc query DB xảy ra không? Thiết kế test phân biệt.

### Bài 8 — Query cache aggregate

Một query cached `count(Product where status=ACTIVE)` trả 200. SQL bên ngoài đổi 30 rows sang DISCONTINUED và commit. Thiết kế invalidation cho query region, không chỉ Product entity instances.

### Bài 9 — Collection membership

SQL chuyển Product#42 từ Category#5 sang Category#7. Liệt kê entity, old/new collection và query/DTO caches phải xem xét. Viết một test hai categories sau commit.

### Bài 10 — Application cache không bị JPA evict

`@Cacheable(productDetails)` lưu `ProductView` vào Redis. Gọi JPA `evict(Product.class,42L)` rồi request vẫn trả old price. Viết invalidation bằng Spring CacheManager với tenant-scoped key.

### Bài 11 — Tenant key

Hai tenants có cùng `productId=42`. Thiết kế cache keys tránh trộn và test request tenant A không đọc cache của tenant B, ngay cả sau invalidate/reload.

### Bài 12 — Evict trước commit

Viết timeline có writer evict trước commit và reader repopulate old data. Giải thích vì sao cách này không bảo đảm consistency sau commit.

### Bài 13 — Evict sau commit

Viết timeline cache hit old data trong cửa sổ DB commit→evict. Định nghĩa freshness SLA của product browsing, và nêu khi nào cần authoritative read.

### Bài 14 — Stale repopulation race

Dùng `CountDownLatch` ép:

```text
Reader fetch old DB state
Writer commit + evict
Reader cache-put old state
```

Viết test chứng minh naive cache-aside sai, sau đó thêm generation token hoặc version-aware fencing.

### Bài 15 — L2 local nhiều pods

Có pods A, B, C với local L2 caches. Một DBA UPDATE Product#42. Gọi `evict` trên A. Vì sao B/C vẫn có thể stale? Đề xuất broadcast/event replay/region approach.

### Bài 16 — Event không đến node offline

Node B offline khi nhận ProductChanged event, sau đó khởi động lại với persisted local cache. Thiết kế startup epoch check, replay hoặc TTL/namespace strategy.

### Bài 17 — Transactional event listener

Viết `@TransactionalEventListener(AFTER_COMMIT)` xóa Redis ProductView. Test rollback transaction không xóa cache theo event success path. Giải thích hạn chế process crash giữa DB commit và listener.

### Bài 18 — Transactional outbox

Thiết kế schema outbox, ghi ProductChanged event trong cùng transaction với UPDATE, relay sau commit và retry khi Redis down. Test event không mất khi process crash sau commit.

### Bài 19 — Out-of-order events

Product version 8 và 9 phát events nhưng subscriber nhận v9 trước v8. Nếu subscriber cache-put payload thay vì evict, có thể xảy ra gì? Thiết kế CAS/sourceVersion protocol.

### Bài 20 — CDC external writer

ERP dùng JDBC UPDATE Products mỗi giờ. Thiết kế pipeline CDC/consumer invalidate caches, xử lý duplicate delivery, lag, tenant scoping và metrics.

### Bài 21 — Backfill 10 triệu rows

Một migration cần UPDATE 10 triệu rows. Dự báo CDC event volume, DB load, cache misses. So sánh per-ID invalidation với bulk generation cutover, có runbook rollback.

### Bài 22 — Rolling deploy payload schema

v1 `ProductView(id,price,status)`; v2 thêm `currency`. Thiết kế cache schema keys để v1/v2 cùng chạy mà không deserialize sai và cách invalidation trong coexistence window.

### Bài 23 — Expand–migrate–contract

Đổi `products.price` thành `base_price` và `currency_code`. Viết bốn pha schema/data/reader cutover cùng kế hoạch cache generation/old node draining.

### Bài 24 — Enum migration

v1 Java enum có LEGACY, v2 có DISCONTINUED. SQL đổi DB values. Vì sao evict cache không làm v1 đọc được new value? Đề xuất release ordering.

### Bài 25 — Read replica stale fill

Primary đã commit price mới, replica trễ 3 giây, cache được evict sau commit. Reader tải old price từ replica và repopulate Redis. Thiết kế routing/watermark để tránh stale fill.

### Bài 26 — Negative cache

API cache NOT_FOUND cho Product#99. External INSERT tạo Product#99. Thiết kế invalidation trên create/restore và test GET từ 404 thành 200 đúng SLA.

### Bài 27 — Soft delete và list cache

Product#42 được soft delete qua JDBC. Những cached pages/counts/negative entries nào cần thay đổi? Nếu restore, cách xử lý cache khác gì DELETE vật lý?

### Bài 28 — DB restore

DB được restore từ snapshot cũ, Product version quay từ 9 về 7. Tại sao version-aware cache write chỉ nhận version lớn hơn có thể sai? Thiết kế database incarnation/epoch reset.

### Bài 29 — Runbook sửa giá

Viết thao tác có scope `tenantId+id+expectedVersion`, kiểm tra affected rows, commit, publish durable invalidation, verify qua DB primary/API nodes và audit ticket.

### Bài 30 — Permission revocation

User bị thu hồi ADMIN role nhưng cache quyền còn giữ 5 phút. Nêu vì sao TTL không đủ với strict revocation và thiết kế authoritative permission/session-version protocol.

### Bài 31 — Lock/counter cache trên critical path

Checkout đọc Product price từ Redis và stock từ local cache. Hãy quyết định fields nào chỉ dùng để hiển thị, fields nào phải validate bằng transaction primary/locking hoặc conditional UPDATE.

### Bài 32 — Cache stampede

`evictAll()` khiến 5.000 requests đồng thời miss, DB pool cạn. Thiết kế targeted purge, prewarm, jitter TTL, request coalescing và load shedding; xác định metrics cần monitor.

### Bài 33 — Query cache pagination

User xem list ACTIVE sort by price với 20 products/page. Migration đổi giá/status của Product#42. Vì sao chỉ evict page chứa Product#42 có thể sai? Thiết kế query/list namespace generation.

### Bài 34 — Tạo test multi-instance

Hai app instances dùng Redis chung nhưng Caffeine/L2 local riêng. Seed DB, warm cache ở cả A/B, external SQL UPDATE, phát event, kiểm tra cả hai nodes trả price mới. Thêm case event delivery delayed.

### Bài 35 — Đo freshness

Đặt SLO “99.9% catalog changes reflected trong 30s”. Chọn metrics outbox age, CDC lag, cache generation, primary/API sample diff, replica watermark và incident alerts.

### Bài 36 — Audit cache maintenance

Một endpoint admin có quyền reset catalog cache. Thiết kế authentication/authorization, rate limit, scoped key/region whitelist, audit trail và cách giảm cache stampede.

### Bài 37 — Release rollback

Release v2 đã migrate DB values và viết cache schema-v2, nhưng cần rollback về v1. Thiết kế compatibility check và chỉ ra trường hợp không thể rollback code đơn thuần.

### Bài 38 — Sửa dữ liệu qua stored procedure

Stored procedure update Product, CategorySummary và PriceHistory trong cùng DB transaction. Lập dependency map và event payload, tránh chỉ invalidate Product entity.

### Bài 39 — Test integrity khi event bus lỗi

Product update commit thành công nhưng relay Redis eviction fail. Assert event còn pending, retry/replay thành công, DB không bị rollback sai và endpoint nhạy cảm có safe fallback.

### Bài 40 — Thiết kế toàn hệ thống

Cho dự án có Product/Inventory/UserRole, PostgreSQL primary + replica, Hibernate L2 local, Spring Redis cache, Flyway và ERP JDBC import. Thiết kế cache policy theo data criticality, invalidation dependencies, external writers protocol, rolling deploy/backfill/restore runbooks và integration tests chứng minh correctness.

## 46. Câu hỏi tự kiểm tra

**1. Cache có phải nguồn dữ liệu có thẩm quyền không?**

Không. Database/committed source-of-truth là nơi xác định state theo domain; cache là bản sao/derived state phục vụ reads.

**2. Vì sao external SQL UPDATE có thể làm JPA đọc dữ liệu cũ?**

SQL ngoài process không tự invalidate L1, L2, query cache và application caches đang giữ state cũ.

**3. JPA L1 cache nằm ở đâu?**

Trong persistence context của từng EntityManager.

**4. Hai `em.find` trên cùng PK trong một EM có thể trả cùng object không?**

Có. Identity map của persistence context bảo đảm quản lý một persistent identity theo JPA semantics.

**5. `EntityManager.clear()` có xóa L2 cache không?**

Không. Nó detach managed entities trong một EM; shared cache là lớp khác.

**6. `em.clear()` có thể làm mất gì?**

Pending managed changes chưa flush có thể bị bỏ, nên không gọi tùy tiện giữa transaction.

**7. `em.refresh(entity)` làm gì?**

Yêu cầu reload persistent state cho managed entity theo DB transaction/isolation; có thể ghi đè local unflushed edits.

**8. `refresh` có vượt mọi isolation snapshot không?**

Không. Database isolation/snapshot visibility vẫn áp dụng.

**9. `em.detach(entity)` khác `clear` thế nào?**

Detach nhắm entity (có cascade implications) còn clear detach toàn bộ managed state của EM.

**10. EntityManagerFactory L2 cache có luôn bật không?**

Không. Phụ thuộc `SharedCacheMode`, entity cacheability và provider/cache backend configuration.

**11. `@Cacheable(true)` có tự tạo Redis distributed cache không?**

Không. Đây là JPA cache metadata; cache provider/topology phải được cấu hình.

**12. `SharedCacheMode.ENABLE_SELECTIVE` có ý nghĩa gì?**

Shared caching được chọn cho entity types đánh dấu cacheable theo JPA/provider rules.

**13. `emf.getCache().evict(Product.class,42L)` có mục đích gì?**

Yêu cầu loại entry của Product#42 khỏi shared JPA cache trong scope persistence unit/provider.

**14. `emf.getCache().evict(Product.class)` khác evict một ID thế nào?**

Nó loại các instances của entity type đó trong shared cache, phạm vi rộng hơn.

**15. `evictAll()` có xóa Redis, browser cache và mọi active L1 không?**

Không. Nó chỉ thao tác trên JPA shared cache theo contract.

**16. `Cache.contains` có chứng minh cache entry mới không?**

Không. Nó không kiểm chứng dữ liệu so với database hiện tại.

**17. JPA `CacheRetrieveMode.BYPASS` có bỏ qua L1 managed entity không?**

Không nên giả định; bypass chủ yếu nhắm shared cache, còn L1 identity map có thể trả entity đã managed.

**18. Hibernate query cache có là API portable JPA không?**

Không. Đây là tính năng provider-specific.

**19. Hibernate query cache có chỉ cache entities giống L2 không?**

Không. Nó có thể cache query results/IDs/scalars theo provider/version.

**20. Vì sao external SQL có thể làm `COUNT` query cache sai?**

Aggregate result không được recompute/invalidate khi source tables đổi ngoài invalidation protocol.

**21. Collection cache có giống entity cache không?**

Không hoàn toàn. Associations/collection memberships có thể ở regions riêng và cần invalidation độc lập.

**22. Đổi Category của Product cần xem caches nào?**

Product entity, old/new category collection memberships, queries/lists và DTO read models liên quan.

**23. Spring `@Cacheable` thuộc JPA L2 không?**

Không. Đó là application cache abstraction, có thể dùng Redis/Caffeine tùy CacheManager.

**24. Xóa JPA L2 Product#42 có xóa Spring Redis ProductView không?**

Không mặc định; cần invalidate cache riêng.

**25. Local Caffeine cache ở pod A có tự xóa cache pod B không?**

Không, trừ khi có coherence/broadcast protocol riêng.

**26. Redis shared cache có giải quyết mọi stale data không?**

Không. L1/L2 local caches, query cache, read replicas, stale repopulation và serialization compatibility vẫn có thể gây lỗi.

**27. Vì sao cache key thường cần tenant ID?**

Để tách data scope, tránh collisions/cross-tenant data leakage và match authorization context.

**28. Tenant ID từ request có được tin ngay để tạo cache key không?**

Không; phải xác minh authorized tenant scope.

**29. Negative caching là gì?**

Cache kết quả “không tồn tại/không tìm thấy” để giảm repeated misses.

**30. External INSERT có thể làm negative cache sai thế nào?**

Key còn `NOT_FOUND` khiến API trả 404 dù database đã có row mới.

**31. `@Version` có tự invalidates L2 trên mọi external SQL UPDATE không?**

Không. Nó chủ yếu bảo vệ optimistic writes khi external writer tuân version protocol; invalidation là việc riêng.

**32. Nếu external writer không bump version có rủi ro gì?**

Một stale managed writer có thể không phát hiện thay đổi ngoài ứng dụng và ghi đè state cũ tùy mapping/update strategy.

**33. Tăng version bằng SQL có đủ bảo đảm mọi cached reads mới không?**

Không. Cache vẫn có thể trả version/price cũ cho đến khi invalidated/bypassed.

**34. Vì sao trigger bump version cần thiết kế cẩn thận?**

Có thể xung đột với JPA provider version management, gây double increment hoặc incorrect optimistic checks.

**35. Vì sao không evict trước commit?**

Reader khác có thể miss cache, đọc DB old state và repopulate nó trước khi writer commit.

**36. Evict sau commit có hoàn toàn loại cửa sổ stale không?**

Không. Còn latency và race reader đã fetch old state rồi populate cache sau eviction.

**37. `@TransactionalEventListener(AFTER_COMMIT)` giúp gì?**

Chạy handler sau transaction commit phase theo Spring semantics, thích hợp cho best-effort post-commit invalidation.

**38. AFTER_COMMIT listener có durable qua process crash không?**

Không; nếu process chết sau DB commit trước listener, eviction có thể bị bỏ sót.

**39. Transactional outbox giải quyết điểm yếu nào?**

Ghi change event trong cùng DB transaction với business update để relay có thể retry sau crash.

**40. Outbox có tự bảo đảm strong consistency giữa DB và Redis không?**

Không. Delivery/invalidation có thể trễ dù event durable.

**41. Vì sao outbox events có thể bị gửi trùng?**

At-least-once delivery, crash sau publish nhưng trước ack/mark-published; consumers cần idempotency.

**42. Vì sao event ordering quan trọng khi cache-put payload?**

Event cũ đến sau event mới có thể overwrite fresh entry nếu không có version/fencing guard.

**43. CDC là gì?**

Change Data Capture thu committed database changes qua log hoặc cơ chế tương tự để phát tới downstream systems.

**44. CDC có tự hiểu business dependencies của cache không?**

Không. It reports source changes; application phải map tới affected keys/regions/read models.

**45. CDC lag tác động cache ra sao?**

Cache invalidation xảy ra trễ so với DB commit, làm kéo dài stale window.

**46. Versioned namespace giúp gì trong rolling deploy?**

Tách cached payload formats/generations để old/new release không đọc nhầm incompatible representations.

**47. Schema version và entity version có phải một không?**

Không. Một cái định nghĩa format cached object, cái kia định nghĩa row concurrency state.

**48. Vì sao cần drain old nodes trước một cache cutover nghiêm ngặt?**

Old readers/writers có thể repopulate cache cũ hoặc dùng format/source semantics không còn đúng.

**49. Expand–migrate–contract giúp gì?**

Giữ compatibility trong zero-downtime schema/data migrations và tránh release cũ bị hỏng khi new schema xuất hiện.

**50. Evict cache có giải quyết old code không biết new enum value không?**

Không. Code/schema compatibility phải được xử lý ở application/deployment.

**51. Vì sao prewarm cache sau migration cần kiểm tra source watermark?**

Nếu nạp từ replica trễ hoặc dữ liệu migration chưa commit đầy đủ, new cache generation có thể chứa old/mixed state.

**52. Vì sao read replica có thể repopulate old cache sau eviction?**

Replica chưa apply DB change, cache-miss reader lấy old row từ replica rồi ghi lại vào cache.

**53. Cache entry TTL 30 giây có bảo đảm đọc sau commit mới ngay không?**

Không. TTL chỉ giới hạn tuổi cache theo policy, không tạo read-after-write linearizability.

**54. Restore DB có thể làm `@Version` giảm không?**

Có. Restored snapshot có thể có version nhỏ hơn state cache từng biết.

**55. Vì sao cần database incarnation/cache epoch sau restore?**

Để nhận diện cache keys thuộc DB snapshot cũ và tránh giữ state từ một lịch sử dữ liệu đã bị thay thế.

**56. Redis `KEYS *` có nên là thao tác purge mặc định không?**

Không. Nó có thể gây load và phạm vi xóa quá rộng; dùng targeted eviction/namespace strategies.

**57. Cache hit rate cao có chứng minh correctness không?**

Không. Cache có thể hit dữ liệu cũ rất nhanh.

**58. Metric nào giúp đo độ trễ invalidation?**

Khoảng thời gian từ DB commit/source watermark tới lúc cache key/region/generation được cập nhật trên read paths.

**59. Vì sao query list phân trang khó invalidate hơn entity detail?**

Status/price/sort changes làm thay membership, thứ tự, page boundaries và total count của nhiều pages.

**60. Data migration lớn có thể gây cache stampede không?**

Có. Evict diện rộng làm miss rate tăng và DB/pool quá tải nếu không có traffic/warmup plan.

**61. Có nên cache inventory value để quyết định checkout trừ hàng không?**

Không nếu cache stale có thể gây oversell; cần authoritative concurrency protocol trên DB hoặc một cơ chế nhất quán đã được chứng minh.

**62. Cache quyền ADMIN bị stale sau thu hồi quyền có rủi ro gì?**

Privilege remains effective ngoài ý muốn; cần revocation consistency policy mạnh hơn TTL dài.

**63. Test external SQL thay entity cần kiểm tra gì?**

DB committed state, L1/L2/query/application cache responses và targeted eviction/bypass path, không chỉ SQL rowcount.

**64. Test multi-node khác single-node ở điểm nào?**

Nó kiểm tra invalidation distribution/cluster coherence, local near-caches, node downtime/replay và release coexistence.

**65. Khi cache invalidation thất bại sau DB commit, có rollback DB được không?**

Không chỉ vì cache thất bại; transaction DB đã commit. Cần retry/repair/bypass và ghi operational incident.

**66. Khi nào tắt cache là quyết định hợp lý?**

Khi data đổi thường xuyên bởi uncontrolled external writers, business cần strong freshness hoặc chi phí coherence vượt lợi ích.

**67. Có phải mọi data cache cần cùng SLA không?**

Không. Product preview, permissions, financial decisions và analytics có consistency/freshness requirements khác nhau.

**68. Vì sao event consumer cần authenticate producer?**

Ngăn fake invalidation events/cache DoS hoặc thay đổi scope của tenants khác.

**69. Một migration được coi hoàn tất khi SQL COMMIT thành công chưa?**

Chưa chắc. Cần kiểm tra data correctness, cache propagation, replica/derived state, app compatibility và SLO.

**70. Nguyên tắc vận hành quan trọng nhất?**

**Mỗi thay đổi ngoài ứng dụng cần có kế hoạch làm mới đúng cache layers, đúng nodes, sau commit, có kiểm chứng freshness và fallback an toàn nếu invalidation trễ hoặc thất bại.**

## 47. Checklist vận hành JPA cache khi thay đổi dữ liệu

### 47.1. Xác định dữ liệu và nguồn thay đổi

1. Dữ liệu nào được thay? Entity/ID, table/column, associations, aggregate dependencies?
2. Source of truth là primary database, ledger hay một hệ thống khác?
3. Writer là JPA service, bulk JPQL, JDBC, ETL, DBA SQL, CDC sink hay DB trigger?
4. Thao tác có tenant/owner/authorization scope đúng không?
5. Có bao nhiêu rows và những IDs nào affected?
6. Transaction đã commit chưa? Có deferred constraints/rollback risk không?
7. `@Version`/audit/updatedAt protocol có được external writer tuân thủ không?
8. Trigger/FK cascades có thay các bảng/relationships khác không?
9. Data change có tương thích code/schema/cache format đang chạy không?
10. Có rollback, restore và snapshot incarnation strategy không?

### 47.2. Lập bản đồ cache

11. Có active EntityManagers/extended contexts giữ L1 stale state không?
12. JPA L2 có được bật không, entity types nào cacheable?
13. Có collection regions/relationships bị ảnh hưởng không?
14. Có Hibernate query cache hoặc cached scalar aggregates không?
15. Có Spring Redis/Caffeine/Guava cache chứa DTO/method result không?
16. Có negative cache (NOT_FOUND), list page, search/filter/sort caches không?
17. HTTP/CDN/browser cache có giữ response cũ không?
18. Node nào có local cache, node nào dùng shared backend?
19. Key/region có tenant, permissions, currency, locale, schema/epoch dimensions đúng không?
20. Có read replica hoặc derived store có lag khác cache không?

### 47.3. Chọn protocol invalidation

21. Có thể evict theo chính xác entity ID không?
22. Có cần invalidate old/new parent collections hoặc child entity regions không?
23. Có cần clear query/report regions hoặc application list keys không?
24. Nếu nhiều rows, region eviction hay namespace epoch hợp lý hơn per-ID events không?
25. Eviction có xảy ra sau committed change theo policy không?
26. Có durable outbox/CDC nếu external writers/after-commit crashes là rủi ro không?
27. Các events có được gửi tới **mọi** local cache nodes cần nhận không?
28. Event consumer có idempotency, ordering hoặc version fencing khi cần không?
29. Có stale repopulation race giữa old reader và eviction không?
30. Nếu Redis/event bus lỗi, read path sẽ bypass, degrade hay chấp nhận stale theo SLA?

### 47.4. Triển khai và di trú

31. Old/new releases có đọc được cả old/new DB values trong overlap window không?
32. Cache serializers/DTO formats có backward/forward compatibility không?
33. Có dùng schema-versioned keys hay release namespaces khi cần không?
34. Old nodes đã drain hoặc được fence khỏi new generation chưa?
35. Backfill có thể tạo mixed states và dữ liệu partial-commit không?
36. CDC/outbox có đủ capacity cho migration event volume không?
37. Cache warmup source đã commit và replica đạt watermark chưa?
38. Sau full eviction, DB/pool chịu được cache stampede không?
39. Read-critical endpoints có authoritative source/transactional revalidation không?
40. Restore/PITR có bump database incarnation/cache epoch không?

### 47.5. Kiểm thử và xác nhận

41. L1 stale/read-after-refresh test đã chạy với transaction isolation rõ chưa?
42. L2 eviction test có cache provider thật, EM mới và correct region không?
43. Query cache aggregate/list test có external INSERT/UPDATE/DELETE không?
44. Redis/local cache multi-node test có event loss/delay case không?
45. Stale repopulation race và generation fencing đã được kiểm tra chưa?
46. Tenant authorization/negative cache correctness tests có đủ không?
47. Migration compatibility và code rollback simulation đã có chưa?
48. Primary DB versus API response diff đã được kiểm tra qua nhiều nodes chưa?
49. Replica/outbox/CDC lag và cache invalidation completion nằm trong freshness SLO chưa?
50. Error rates, cache misses, DB CPU/pool wait, p95/p99 latency có bất thường không?

### 47.6. Kết thúc và audit

51. Migration/runbook ghi actor, ticket, affected IDs, version, commit marker chưa?
52. Invalidation sự kiện/key/region/generation có log/ack/retry evidence chưa?
53. Có proof rằng old cache payloads không còn được đọc qua active traffic paths không?
54. Có xác nhận không còn old nodes dùng cache format incompatible không?
55. Có alert nếu event lag hoặc stale-read sample vượt ngưỡng không?
56. Có kế hoạch xóa old generations/keys sau retention không?
57. Có tách success của DB modification khỏi success của cache invalidation không?
58. Nếu mới hoàn tất một phần, incident status có phản ánh đúng không?
59. Có follow-up sửa dependency graph/invalidation automation nếu runbook thủ công gây lỗi không?
60. Có tài liệu hóa consistency/freshness contract cho những người vận hành và phát triển không?

## 48. Tài liệu tham khảo khi áp dụng vào dự án

Cần đối chiếu cách triển khai cụ thể với phiên bản của JPA provider và hạ tầng:

- [Jakarta Persistence specifications](https://jakarta.ee/specifications/persistence/): persistence context, `Cache`, `SharedCacheMode`, `CacheRetrieveMode`, `CacheStoreMode` và locking semantics.
- [Jakarta Persistence API documentation](https://jakarta.ee/specifications/persistence/): `EntityManager.refresh`, `clear`, `detach`, `EntityManagerFactory.getCache`.
- [Hibernate ORM User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): L2 cache, collection/query cache regions, cache concurrency strategies, provider-specific eviction và statistics.
- [Spring Framework Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CacheEvict`, CacheManager, proxy behavior.
- [Spring Framework Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và transaction phases.
- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/): transactions, snapshots, replication, WAL, maintenance SQL và monitoring.
- [Redis Documentation](https://redis.io/docs/latest/): key expiry, eviction, operational commands, distributed cache concerns.

Các đường dẫn là điểm tra cứu chính thức; cần sử dụng tài liệu đúng major versions đang chạy. Đặc biệt, **Hibernate APIs và cache implementation details có thể thay đổi giữa các versions**, còn Jakarta Persistence API chuẩn không quy định toàn bộ cluster eviction/query-region semantics.

## 49. Tổng kết

Khi triển khai hoặc thay đổi dữ liệu bên ngoài ứng dụng, vấn đề thực sự không chỉ là “xóa cache” mà là **đảm bảo mọi nơi đọc dữ liệu đều hiểu đúng một trạng thái committed, tương thích với phiên bản ứng dụng và phù hợp độ mới cần thiết**.

Những nguyên tắc cần ghi nhớ:

1. **Phân biệt từng cache tier:** L1 nằm trong mỗi EntityManager; shared L2 có phạm vi persistence unit/cache provider; Hibernate query cache, Spring Cache/Redis, HTTP/CDN và replica là các hệ riêng.
2. **Không dùng `clear()` thay `evictAll()` hoặc ngược lại.** Mỗi API chỉ tác động một scope; clear còn có thể làm mất pending changes chưa flush.
3. **`@Version` không tự invalidate cache.** External writers phải giữ optimistic concurrency protocol nếu cần, đồng thời cache layers phải được cập nhật/bỏ qua.
4. **Cache invalidation cần dependency map.** Đổi giá/trạng thái/association có thể ảnh hưởng entity, collection membership, query results, sorted pages, counts và DTO caches.
5. **Evict sau commit vẫn có cửa sổ stale và stale repopulation race.** Giao thức eventual-consistent phải ghi rõ SLA; dữ liệu critical có thể cần authoritative reads, locking, version fences hoặc generation protocol.
6. **After-commit listener không durable qua crash.** Transactional outbox/CDC giúp recover/replay, nhưng không tự cung cấp strong consistency nếu delivery còn asynchronous.
7. **Multi-node cache cần broadcast hoặc shared coherence.** Evict trên một JVM không tự xóa caches của mọi pods.
8. **Rolling deployment cần compatibility:** data/schema values, cache payload format, old/new nodes, rollback, epoch namespacing và out-of-order events.
9. **Migration lớn cần kế hoạch cache impact:** batch windows, mixed state, query-region invalidation, CDC lag, stampede, warmup và verified source watermark.
10. **Read replica có thể làm cache mới lại trở thành cũ.** Không populate shared cache từ source replica chưa đạt freshness yêu cầu của nghiệp vụ.
11. **Restore database cần reset data incarnation.** Không chỉ dựa vào monotonic per-row version nếu version có thể quay lùi sau PITR.
12. **Bảo vệ tenant và permissions trong cache key/invalidation.** Cache stale hoặc trộn keys có thể dẫn đến data leak và privilege escalation.
13. **Đo cả correctness lẫn performance:** cache hit rate, lag, stale-sampling, DB primary/API diff, error rates, DB load và latency.
14. **Với dữ liệu quá nhạy cảm, không cache vẫn có thể là thiết kế tốt.** Một cache không có invalidation protocol đáng tin có thể gây rủi ro cao hơn lợi ích độ trễ.
15. **Runbook chỉ hoàn tất sau khi verified state đã xuất hiện trên read paths phù hợp**, không phải ngay sau câu SQL COMMIT hoặc một lệnh Redis DEL.

### 49.1. Quy trình thực hành có thể áp dụng

```text
Data change request / deployment
               |
               v
       Identify source of truth
               |
               v
     Map affected tables / entities
               |
               v
   Map L1/L2/query/DTO/client caches
               |
               v
  Select consistency & freshness budget
               |
               v
   Choose ID / region / epoch strategy
               |
               v
   Plan old/new code + schema versions
               |
               v
       Run authorized DB change
               |
               v
        COMMIT + source watermark
               |
               v
     Durable invalidation / CDC relay
               |
               v
      All cache readers catch up
               |
               v
   Verify primary / replica / API output
               |
               v
    Monitor lag / misses / DB pressure
               |
               v
     Audit and close operational change
```

### 49.2. Ba câu hỏi quyết định

**Câu 1 — Cache nào có thể còn giữ dữ liệu cũ?** Đừng chỉ nghĩ đến một EntityManager; hãy liệt kê shared cache, query results, Redis, node-local state, browser và replicas.

**Câu 2 — Khi nào các reader được phép thấy dữ liệu cũ?** Nếu không có câu trả lời rõ, chưa có consistency contract. Với giá checkout, quyền và số dư, thường phải kiểm tra authoritative state ngay trong quyết định nghiệp vụ.

**Câu 3 — Nếu một invalidation event bị trễ hoặc mất thì hệ thống làm gì?** Cần durability/retry/epoch/fallback và quan sát được mức stale, không dựa vào hi vọng message sẽ luôn đến đúng lúc.

> **Quy tắc vận hành:** *Mỗi thay đổi dữ liệu bên ngoài JPA cần một phương án đồng bộ read paths, không chỉ một câu SQL. Một cache entry chỉ đáng tin khi nguồn, phiên bản, phạm vi và độ mới của nó phù hợp với quyết định nghiệp vụ đang được thực hiện.*
