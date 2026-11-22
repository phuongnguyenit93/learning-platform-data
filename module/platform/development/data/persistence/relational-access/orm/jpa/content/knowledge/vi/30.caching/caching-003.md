# Đánh giá hỗ trợ cache chia sẻ theo provider trong JPA

Trong một ứng dụng sử dụng Java Persistence API (JPA), nhiều request có thể liên tục đọc cùng danh mục, cấu hình, sản phẩm hoặc thông tin tham chiếu. Nếu mỗi lần đều phải truy vấn database, các thao tác đọc lặp lại có thể làm tăng độ trễ và chi phí I/O. **Shared cache**, thường được gọi là **second-level cache (L2)**, là một cơ chế cho phép các persistence contexts khác nhau tái sử dụng trạng thái entity đã được provider lưu lại.

Tuy nhiên, việc code có annotation `@Cacheable` hoặc gọi `EntityManagerFactory.getCache()` **không chứng minh** L2 đã được bật, hoạt động hiệu quả hay có mức độ nhất quán đáp ứng nghiệp vụ. Những khía cạnh như cache backend, TTL, region, query cache, distributed invalidation và statistics thường phụ thuộc vào provider, phiên bản và cấu hình deployment.

~~~text
HTTP Request A                    HTTP Request B
      |                                 |
EntityManager A                    EntityManager B
      |                                 |
Persistence Context A              Persistence Context B
   (L1 cache)                         (L1 cache)
      |                                 |
      +---------------+-----------------+
                      |
                      v
                Shared / L2 cache
                 tùy provider
                      |
                Cache miss/bypass
                      |
                      v
                   Database
~~~

Bài học tập trung vào cách **đánh giá hỗ trợ cache chia sẻ theo provider** một cách có thể kiểm chứng: phân biệt L1 và L2, đọc hiểu `SharedCacheMode` và `@Cacheable`, sử dụng JPA `Cache` API, làm rõ khác biệt Hibernate/EclipseLink, đo cache hit giữa hai EntityManagers, xử lý stale data, external SQL, multi-node, multi-tenant và thực hiện kiểm thử/benchmark trước khi bật production.

## 1. Phân biệt L1 và L2

### 1.1. First-level cache

Mỗi persistence context quản lý các entity instances theo identity. Ví dụ:

~~~java
EntityManager em = emf.createEntityManager();

try {
    CatalogCategory a =
        em.find(CatalogCategory.class, 10L);

    CatalogCategory b =
        em.find(CatalogCategory.class, 10L);

    System.out.println(a == b);
} finally {
    em.close();
}
~~~

Hai lần `find` cùng type/ID trong một persistence context thường trả cùng managed instance. Lần thứ hai có thể không cần SQL. Đây là **first-level cache/identity map**, một phần cốt lõi của JPA persistence context, không phải bằng chứng L2.

L1 gắn với managed/detached state, dirty checking, flush và identity consistency. `SharedCacheMode.NONE` hoặc `@Cacheable(false)` **không tắt L1**.

### 1.2. Shared cache

L2 có thể được chia sẻ giữa những persistence contexts độc lập thuộc cùng provider/cache configuration.

~~~java
EntityManager first = emf.createEntityManager();
CatalogCategory categoryA;
try {
    categoryA =
        first.find(CatalogCategory.class, 10L);
} finally {
    first.close();
}

EntityManager second = emf.createEntityManager();
CatalogCategory categoryB;
try {
    categoryB =
        second.find(CatalogCategory.class, 10L);
} finally {
    second.close();
}
~~~

Nếu L2 đã được cấu hình đúng và entry cache hợp lệ, lượt đọc ở `second` có thể tránh SELECT để tải chính entity đó. Hai Java objects không nhất thiết là cùng instance vì mỗi persistence context quản lý identity riêng.

### 1.3. So sánh nhanh

| Tiêu chí | L1 | L2 |
|---|---|---|
| Phạm vi | Một persistence context | Provider/cache backend |
| Quản lý managed identity | Có | Không thay L1 |
| Bắt buộc có semantics JPA | Có | Có API/chính sách nhưng implementation tùy provider |
| Dùng giữa hai EntityManagers | Không trực tiếp | Có thể |
| Evict bằng `EntityManagerFactory.getCache()` | Không | Có |
| Tự chia sẻ giữa JVMs | Không | Không mặc định |
| Bảo đảm mọi truy vấn không phát SQL | Không | Không |

## 2. Mô hình minh họa

Giả sử có hai entity:

- `CatalogCategory`: danh mục ít thay đổi, thường được đọc lại.
- `ProductOffer`: giá hiện tại thay đổi nhiều và có writers từ hệ thống khuyến mãi.

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "catalog_category")
@Cacheable(true)
public class CatalogCategory {

    @Id
    private Long id;

    @Column(nullable = false)
    private String code;

    @Column(nullable = false)
    private String displayName;

    @Version
    private long version;

    protected CatalogCategory() {}

    public Long getId() { return id; }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "product_offer")
@Cacheable(false)
public class ProductOffer {

    @Id
    private Long id;

    @Column(nullable = false)
    private BigDecimal currentPrice;

    @Version
    private long version;

    protected ProductOffer() {}

    public Long getId() { return id; }

    public BigDecimal getCurrentPrice() {
        return currentPrice;
    }
}
~~~

Danh mục có thể là ứng viên cache tốt do read/write ratio cao. Giá bán cần freshness nghiêm ngặt hơn nếu nó tham gia quyết định thu tiền. Không có quy tắc cấm tuyệt đối cache giá; cần thiết kế đường đọc authoritative trong command transaction nếu cache có thể stale.

## 3. JPA chuẩn hóa đến đâu?

Jakarta Persistence cung cấp các khái niệm portable:

- `SharedCacheMode` ở persistence unit.
- `@Cacheable` trên entity.
- `EntityManagerFactory.getCache()`.
- `Cache.contains` và các thao tác eviction.
- `CacheRetrieveMode` và `CacheStoreMode` qua hints.

Những thành phần không được JPA chuẩn hóa toàn diện:

- Region factory và cache backend.
- TTL, TTI, capacity và thuật toán eviction.
- Cache concurrency strategy của từng vendor.
- Query-result cache, collection cache, natural-ID cache.
- Cache distribution/replication/invalidation giữa nodes.
- Cache hit/miss statistics API.
- Khả năng atomic commit DB cùng cache update.
- Chính sách vận hành khi cache backend gặp sự cố.

**JPA chuẩn hóa ý định và một số API điều khiển; provider quyết định rất nhiều chi tiết thực thi.**

## 4. Năm giá trị SharedCacheMode

~~~java
SharedCacheMode.ALL
SharedCacheMode.NONE
SharedCacheMode.ENABLE_SELECTIVE
SharedCacheMode.DISABLE_SELECTIVE
SharedCacheMode.UNSPECIFIED
~~~

### 4.1. ALL

Yêu cầu chính sách shared cache áp dụng cho tất cả entity types của persistence unit theo semantics ALL. Không nên dùng rộng nếu có những entities thay đổi liên tục hoặc có consistency requirements khó bảo đảm.

### 4.2. NONE

Yêu cầu không sử dụng shared entity cache. Persistence context L1 vẫn hoạt động. Đây là baseline quan trọng để so sánh performance/correctness.

### 4.3. ENABLE_SELECTIVE

Chỉ cache các entities được đánh dấu `@Cacheable(true)` theo policy. Thường phù hợp để bắt đầu với những reference entities đã được chọn.

### 4.4. DISABLE_SELECTIVE

Mặc định cho phép cache những entity không được đánh dấu `@Cacheable(false)`. Dễ vô tình mở rộng cache khi thêm entity mới, vì thế cần convention của team.

### 4.5. UNSPECIFIED

Provider định nghĩa behavior. Cùng code có thể có SQL/cache behavior khác khi chuyển Hibernate sang EclipseLink hoặc đổi version/config.

### 4.6. Ma trận cache eligibility

| SharedCacheMode | `@Cacheable(true)` | `@Cacheable(false)` | Không annotation |
|---|---|---|---|
| ALL | Theo ALL | Theo ALL | Theo ALL |
| NONE | Không L2 | Không L2 | Không L2 |
| ENABLE_SELECTIVE | Có thể L2 | Không L2 | Không L2 |
| DISABLE_SELECTIVE | Có thể L2 | Không L2 | Có thể L2 |
| UNSPECIFIED | Tùy provider | Tùy provider | Tùy provider |

**Có thể L2** chỉ nói về eligibility theo chính sách chuẩn. Nó không bảo đảm provider đã được cấu hình với cache backend hoạt động hoặc entry có sẵn.

## 5. Khai báo trong persistence.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="shopPU"
        transaction-type="RESOURCE_LOCAL">

        <class>com.example.shop.domain.CatalogCategory</class>
        <class>com.example.shop.domain.ProductOffer</class>

        <shared-cache-mode>
            ENABLE_SELECTIVE
        </shared-cache-mode>

        <properties>
            <!-- DB và provider properties -->
        </properties>

    </persistence-unit>
</persistence>
~~~

Ví dụ dùng Jakarta Persistence 3.1 XML. Trong ứng dụng Spring có thể cấu hình `EntityManagerFactory` bằng Spring Boot properties thay vì file này. Điều quan trọng là **config nguồn nào thực sự được runtime sử dụng**, không chỉ có một file XML trong repository.

Với JPA 2.x, namespace APIs/hints có thể mang tiền tố `javax.persistence`; với Jakarta Persistence 3.x dùng `jakarta.persistence`. Không trộn các thế hệ mà chưa kiểm chứng dependency/provider.

## 6. @Cacheable khác Spring @Cacheable

Annotation JPA:

~~~java
import jakarta.persistence.Cacheable;

@Cacheable(true)
@Entity
public class CatalogCategory {
    // ...
}
~~~

khác Spring method result caching:

~~~java
import org.springframework.cache.annotation.Cacheable;
~~~

Spring annotation có thể cache return value của một method; JPA annotation diễn đạt shared entity cache eligibility. Hai cache layers có thể đồng thời tồn tại nhưng có **hai bài toán invalidation khác nhau**.

### 6.1. @Cacheable(true) không đủ

Một entity vẫn có thể miss L2 do backend không bật, entry hết hạn, eviction, bypass hint, update invalidation hoặc provider-specific execution path.

### 6.2. @Cacheable(false) không làm mọi lần find chạy SQL

Với entity đã managed trong L1, gọi find lại vẫn có thể không phát SQL.

### 6.3. Annotation cho root không tự cache tất cả children

Collection memberships, child entity state và lazy associations có cache policies riêng. Cần kiểm tra từng loại.

## 7. EntityManagerFactory.getCache()

~~~java
EntityManagerFactory emf = ...;

Cache cache = emf.getCache();
~~~

API `jakarta.persistence.Cache` hỗ trợ:

~~~java
boolean present =
    cache.contains(CatalogCategory.class, categoryId);

cache.evict(CatalogCategory.class, categoryId);

cache.evict(CatalogCategory.class);

cache.evictAll();
~~~

### 7.1. contains

Kiểm tra cache báo có entry theo type/ID hay không. Không được dùng kết quả này làm bảo đảm rằng query tiếp theo không có SQL: provider có thể cần association, query result IDs, version check hoặc entry có thể bị eviction.

### 7.2. evict(type,id)

Loại bỏ một entity entry khỏi shared cache theo semantics JPA. Không xóa database row, không phải `em.remove`, không tự refresh những managed objects hiện có.

### 7.3. evict(type)

Yêu cầu eviction theo entity class; có thể làm nhiều entries cold. Dùng chủ đích thay vì sau mọi update một record.

### 7.4. evictAll()

Evict toàn shared entity cache. Hữu ích trong isolated benchmark baseline; gọi thường xuyên ở production có thể làm DB tăng load đột ngột.

### 7.5. Cache API không có statistics chuẩn

JPA `Cache` không cung cấp hit/miss/put metrics, cache bytes hay TTL. Dùng extension của Hibernate/EclipseLink/cache backend để quan sát.

## 8. L1 và L2 eviction không giống nhau

~~~java
CatalogCategory category =
    em.find(CatalogCategory.class, categoryId);

emf.getCache().evict(
    CatalogCategory.class, categoryId
);

String name = category.getDisplayName();
~~~

`category` vẫn là managed instance trong current EntityManager, nên `name` có thể vẫn là giá trị đã đọc trước. Evict L2 không làm L1 tự refresh.

| Thao tác | Mục tiêu |
|---|---|
| `em.clear()` | Detach mọi managed entities khỏi current context |
| `em.detach(entity)` | Detach một entity |
| `em.refresh(entity)` | Tải lại state của managed entity |
| `cache.evict(type,id)` | Loại shared cache entry |
| `cache.evictAll()` | Loại shared entity cache |

Cẩn trọng: `em.clear()` có thể làm pending dirty changes chưa flush không được tiếp tục quản lý. `em.refresh()` có thể ghi đè pending values. Không dùng chúng tùy tiện trong business transaction chỉ để “thử cache”.

## 9. CacheRetrieveMode: Đọc từ L2 hay không?

~~~java
CacheRetrieveMode.USE
CacheRetrieveMode.BYPASS
~~~

- `USE`: Cho phép provider retrieve từ shared cache theo policy.
- `BYPASS`: Yêu cầu bỏ qua shared cache khi lấy dữ liệu cho operation.

~~~java
CatalogCategory category = em.find(
    CatalogCategory.class,
    categoryId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
~~~

### 9.1. BYPASS không bỏ qua L1

Nếu EntityManager đã managed Category cùng ID, find có thể trả current instance. Muốn xác minh BYPASS thực sự đọc DB, dùng một EntityManager **mới không giữ entity đó**.

### 9.2. Hint trên query

~~~java
List<CatalogCategory> categories =
    em.createQuery(
        """
        SELECT c FROM CatalogCategory c
        WHERE c.code LIKE :prefix
        """,
        CatalogCategory.class
    )
    .setParameter("prefix", "E%")
    .setHint(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
    .getResultList();
~~~

Hint tác động shared entity cache retrieval theo provider semantics, không tắt database buffer cache, Spring method cache hoặc mọi query-result cache vendor-specific.

## 10. CacheStoreMode: Lưu hoặc làm mới L2

~~~java
CacheStoreMode.USE
CacheStoreMode.BYPASS
CacheStoreMode.REFRESH
~~~

- `USE` cho phép store theo cache policy.
- `BYPASS` yêu cầu không store dữ liệu vào L2 cho operation.
- `REFRESH` yêu cầu làm mới shared cache bằng state lấy từ DB theo semantics store mode.

### 10.1. Đọc DB và refresh cache

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);

CatalogCategory category = em.find(
    CatalogCategory.class,
    categoryId,
    hints
);
~~~

Nên thử trong context mới, vì entity đang managed trong L1 có thể làm find trả object cũ mà không thực hiện data retrieval như mong muốn.

### 10.2. Bảng tổ hợp

| Retrieve | Store | Ý định |
|---|---|---|
| USE | USE | Dùng shared cache bình thường |
| BYPASS | USE | Không lấy từ L2 nhưng có thể store |
| USE | BYPASS | Có thể đọc L2, không store |
| BYPASS | BYPASS | Bỏ qua retrieve/store L2 |
| BYPASS | REFRESH | Lấy DB state rồi yêu cầu cập nhật L2 |

Không biến bảng thành một cam kết SQL count tuyệt đối: query path, L1 và provider implementation vẫn quyết định cách thực thi.

## 11. Hibernate: Hỗ trợ không đồng nghĩa đã cấu hình

Hibernate có các second-level cache integrations và region strategies, nhưng một application chỉ dùng Hibernate ORM **chưa chắc có cache backend L2 hữu dụng đang hoạt động**.

Những mục phải kiểm tra:

- Hibernate version, module integration và JPA API generation.
- `hibernate.cache.use_second_level_cache`, region factory.
- Cache backend/provider thật.
- Entity cacheability, region names và concurrency strategy.
- TTL/capacity và eviction policy.
- Statistics APIs để đo hit/miss/put.
- Query cache có được bật riêng không nếu cần.
- Cluster consistency và transactions.

### 11.1. JCache

Một số phiên bản Hibernate dùng Hibernate JCache module cùng một JCache provider. Ý định cấu hình có thể là:

~~~properties
hibernate.cache.use_second_level_cache=true
hibernate.cache.region.factory_class=jcache
~~~

Đây không phải cấu hình đầy đủ dùng được với mọi version. Phải chọn đúng module, region factory identifier, JCache backend, cache regions và expiry/size.

### 11.2. Annotation riêng Hibernate

Trong những version hỗ trợ:

~~~java
@Cacheable(true)
@org.hibernate.annotations.Cache(
    usage = org.hibernate.annotations.CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog-category"
)
@Entity
public class CatalogCategory {
    // ...
}
~~~

Annotation `org.hibernate.annotations.Cache` không portable sang mọi JPA provider. Nó có thể giúp khai báo region/strategy riêng Hibernate khi cấu hình phù hợp.

### 11.3. Hibernate statistics

Provider có thể cho số L2 hits, misses, puts và per-region counters. Dùng chúng trong integration test, nhưng không coi chúng là method của JPA `Cache`.

## 12. EclipseLink: Shared object caching có đặc thù riêng

EclipseLink có cơ chế shared identity maps/caches và chính sách caching riêng. Default shared caching có thể khác Hibernate tùy phiên bản.

Cần kiểm tra:

- Shared cache có bật mặc định trên entity types không.
- `SharedCacheMode`, `@Cacheable` được áp dụng ra sao.
- Cache size/type/expiry và invalidation.
- Identity map/shared object cache behavior.
- Cache coordination giữa nhiều nodes.
- External DB changes có được nhận biết không.
- Query result cache nếu sử dụng.
- Cách đo cache hits/SQL.

Một thuộc tính riêng EclipseLink trong những cấu hình phù hợp:

~~~properties
eclipselink.cache.shared.default=true
~~~

Đây **không phải property JPA portable**. Không chuyển thuộc tính này sang Hibernate hay tin rằng một setting đã cấu hình xong distributed cache.

### 12.1. Không so sánh providers bằng defaults tình cờ

Nếu Hibernate chạy cache-off và EclipseLink cache-on, một benchmark nhỏ không thể kết luận EclipseLink có query engine tốt hơn. Cần so sánh cùng read/write workload và correctness SLA dưới các policies tương đương.

## 13. Ma trận khả năng theo provider

| Khả năng | JPA chuẩn | Hibernate | EclipseLink |
|---|---|---|---|
| Persistence context/L1 | Có | Có | Có |
| `SharedCacheMode` | Có | Implementation tương ứng | Implementation tương ứng |
| `@Cacheable` | Có | Theo cấu hình | Theo cấu hình |
| `Cache.contains/evict` | Có | Có implementation | Có implementation |
| Retrieve/store hints | Có | Kiểm thử query path/version | Kiểm thử query path/version |
| Region/cache backend | Không | Vendor/backend-specific | Vendor-specific |
| TTL/capacity | Không | Cache backend/provider | Cache backend/provider |
| Query-result cache | Không portable | Extension | Extension |
| Collection cache | Không portable | Extension | Extension |
| Distributed coordination | Không | Backend/deployment-specific | Coordination/deployment-specific |
| Hit/miss statistics | Không trong JPA Cache | Provider-specific | Provider-specific |
| External SQL invalidation | Không có blanket guarantee | Cần test | Cần test |

Không kết luận “provider X hỗ trợ mọi loại cache tốt hơn” chỉ từ ma trận. Nó xác định phạm vi chuẩn và những mục phải xác nhận trên stack thực.

## 14. Cách kiểm tra cache thật bằng hai EntityManagers

Đây là test then chốt:

~~~java
Cache cache = emf.getCache();

cache.evict(CatalogCategory.class, categoryId);

// First persistence context.
EntityManager emA = emf.createEntityManager();
CatalogCategory a;

try {
    a = emA.find(
        CatalogCategory.class, categoryId
    );
} finally {
    emA.close();
}

// Second persistence context.
EntityManager emB = emf.createEntityManager();
CatalogCategory b;

try {
    b = emB.find(
        CatalogCategory.class, categoryId
    );
} finally {
    emB.close();
}

assertNotNull(a);
assertNotNull(b);
assertEquals(a.getId(), b.getId());
~~~

Những assertions này chỉ kiểm tra object/data. Muốn xác nhận **L2 hit**, phải ghi SQL count hoặc provider L2 statistics giữa hai lượt.

### 14.1. Kế hoạch đo

~~~text
1. Evict Category ID khỏi cache
2. Reset counters trong test harness
3. EM A find -> close -> đo SELECT/L2 put
4. EM B find -> close -> đo SELECT/L2 hit
5. So sánh với SharedCacheMode.NONE
6. Kiểm tra giá trị category vẫn đúng
~~~

Không coi zero SQL trong cùng một EM là bằng chứng L2. Không mặc định một cache hit làm tất cả EAGER/LAZY associations cũng không phát SQL.

### 14.2. Cache.contains là dấu hiệu phụ

`cache.contains(type,id)` hữu ích để quan sát entry presence, nhưng nó không bảo đảm không phát SQL ở query tiếp theo; entry có thể bị evict bất kỳ lúc nào hoặc query cần data khác.

## 15. Bộ test BYPASS và REFRESH

Một acceptance suite:

- Warm Category entry trong L2.
- Cập nhật Category bằng một transaction độc lập.
- Commit.
- Đọc bằng EM mới với default cache policy.
- Đọc bằng EM mới khác với retrieve BYPASS.
- Đọc bằng EM mới với retrieve BYPASS + store REFRESH.
- Kiểm tra value, SQL count và L2 state sau refresh.

Ví dụ:

~~~java
EntityManager em = emf.createEntityManager();

try {
    CatalogCategory c = em.find(
        CatalogCategory.class,
        categoryId,
        Map.of(
            "jakarta.persistence.cache.retrieveMode",
            CacheRetrieveMode.BYPASS,
            "jakarta.persistence.cache.storeMode",
            CacheStoreMode.REFRESH
        )
    );

    assertNotNull(c);
} finally {
    em.close();
}
~~~

Không dùng cùng EM đã managed Category từ trước; L1 có thể che kết quả test.

## 16. Entity cache khác query-result cache

Một query:

~~~java
List<CatalogCategory> categories =
    em.createQuery(
        """
        SELECT c FROM CatalogCategory c
        WHERE c.code LIKE :prefix
        ORDER BY c.code
        """,
        CatalogCategory.class
    )
    .setParameter("prefix", "A%")
    .getResultList();
~~~

có thể vẫn chạy SQL để tìm IDs khớp filter, ngay cả khi các Category entities đã được cache theo ID.

### 16.1. Query cache là vendor extension

Query-result cache có thể lưu danh sách kết quả/IDs cho query + parameters. JPA `Cache.contains(Entity.class,id)` không phải API kiểm tra query-result entries.

### 16.2. Query cache invalidation khác entity cache

Nếu Category đổi `code`, tập kết quả `LIKE 'A%'` có thể đổi. Invalidate một entity entry chưa đủ chứng minh query-result cache được cập nhật.

### 16.3. Phân biệt các layers

| Cache | Nội dung | Chuẩn JPA? |
|---|---|---|
| L1 | Managed entity state | Có |
| L2 | Shared entity state | Có API/policy |
| Query cache | Query results/IDs | Không portable |
| Collection cache | Collection membership/state | Không portable |
| Natural-ID cache | Natural key lookup | Không portable |
| Spring cache | Method return values | Không phải JPA |
| HTTP cache | Response representation | Không phải JPA |
| DB buffer cache | Data/index pages | Không phải JPA |

## 17. L2 không tự sửa lazy loading hay N+1

Một Order có:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
~~~

L2 hit của Order root không bảo đảm `lines` đã được initialized. Nếu Order detached và lines chưa tải, vẫn có thể gặp Hibernate `LazyInitializationException`.

Nếu một loop đọc 100 Orders và gọi lazy Customer getter, cache warm có thể giảm SQL. Nhưng cache cold vẫn có thể gây N+1. Giải pháp đúng ở tầng query là fetch plan/DTO projection/batch fetch, không dựa vào cache “may mắn” để che thiết kế chưa tốt.

### 17.1. Collection cache riêng

Cần kiểm tra collection membership caching, child entity cache, invalidation khi thêm/xóa Line, nested associations và native SQL child updates. Không suy từ entity L2 hit ra collection cache hit.

### 17.2. JOIN FETCH và L2

Một JPQL JOIN FETCH có thể chủ động lấy association qua DB, dù một số entity state có cache. Query plan, association cardinality và pagination vẫn cần được tối ưu độc lập.

## 18. Cache consistency khi ghi dữ liệu

Các đường ghi thường gặp:

1. Managed entity update qua JPA.
2. JPQL bulk UPDATE/DELETE.
3. Native SQL.
4. JDBC service bên ngoài.
5. Database triggers.
6. ETL hoặc admin scripts.
7. Application instance khác cùng provider.
8. Application khác dùng provider/backend khác.

Một shared cache đúng phải có chính sách rõ cho từng đường ghi. `@Version` hỗ trợ optimistic locking với managed updates nhưng **không tự làm mọi external SQL update phát invalidation**.

### 18.1. Managed update và rollback

Test:

~~~text
Warm L2
BEGIN transaction
Modify managed Category
FLUSH
ROLLBACK
Read Category bằng EM mới
~~~

Kết quả không được coi thay đổi đã rollback là committed state.

### 18.2. Bulk JPQL DML

~~~java
int changed = em.createQuery(
        """
        UPDATE CatalogCategory c
        SET c.displayName = :newName
        WHERE c.code = :code
        """
    )
    .setParameter("newName", "Đồ điện")
    .setParameter("code", "ELECTRICAL")
    .executeUpdate();
~~~

Bulk DML bỏ qua per-entity managed lifecycle/dirty checking như update entity thông thường. Provider có thể có cơ chế invalidation vùng cache liên quan, nhưng behavior phụ thuộc provider/version. Không mặc định mọi bulk update tự giữ L1 và L2 đồng bộ.

### 18.3. External SQL

~~~sql
UPDATE catalog_category
SET display_name = 'Điện tử'
WHERE code = 'ELECTRICAL';
~~~

Nếu script không đi qua provider, L2 có thể không được thông báo. Cần eviction events, TTL, cache coordination hoặc bypass cache cho critical reads.

## 19. Thứ tự commit và invalidation

### 19.1. Evict trước commit

Nếu application evict L2 trước khi DB commit, request khác có thể miss và nạp lại committed state cũ, rồi ghi entry cũ vào L2.

### 19.2. Evict sau commit

Có khoảng thời gian DB đã commit nhưng cache chưa bị invalidated. Nếu process crash trước event eviction, stale entry có thể tồn tại thêm.

### 19.3. Điều này có ý nghĩa gì?

JPA không chuẩn hóa `Cache.evict` thành một phần atomic của DB commit. Nếu domain cần read-after-write consistency nghiêm ngặt trên nhiều nodes, phải có protocol/provider integration đáp ứng, hoặc bypass cache trên read path đó. TTL ngắn chỉ giảm stale window chứ không bảo đảm tức thời.

## 20. Local L2 cache và cluster cache

~~~text
App Node A -> EntityManagerFactory A -> L2 A
                                         |
                                         v
                                      Database
                                         ^
                                         |
App Node B -> EntityManagerFactory B -> L2 B
~~~

Hai L2 caches có thể độc lập. Nếu A cập nhật DB, B có thể giữ entry cũ.

### 20.1. Các mô hình triển khai

- Local caches riêng.
- Local caches với invalidation messages.
- Shared distributed backing cache.
- Near-cache + distributed backend.

### 20.2. Những câu hỏi quan trọng

- Cache data có thực sự được chia sẻ hay chỉ nhận eviction?
- Invalidation message có thể bị mất không?
- Có replication lag không?
- Khi node offline rồi reconnect, cache được rebuild thế nào?
- DB commit và cache update có tính nguyên tử không?
- Cache backend down thì fallback DB hay fail?
- Namespace/keys có phân biệt tenant không?

JPA standard không cung cấp toàn bộ answers này; phải đọc cấu hình backend và test trong topology thực.

## 21. Provider-specific concurrency strategy

Một số Hibernate integrations hỗ trợ những thuật ngữ như:

- `READ_ONLY`.
- `NONSTRICT_READ_WRITE`.
- `READ_WRITE`.
- `TRANSACTIONAL`.

### 21.1. READ_ONLY

Thích hợp với immutable/read-only entity. Nếu nightly job vẫn sửa DB mà cache không invalidated, có nguy cơ stale.

### 21.2. NONSTRICT_READ_WRITE

Cho phép policy nhất quán ít chặt hơn trong một số trường hợp; cần SLA rõ về stale window.

### 21.3. READ_WRITE

Có cơ chế phối hợp cache updates của provider/backend nhưng không bảo đảm đồng bộ tự động với mọi external raw SQL writer.

### 21.4. TRANSACTIONAL

Cần backend/transaction manager integration phù hợp, không mặc định khả dụng chỉ vì JPA chạy trong transaction.

**Không chuyển máy móc strategy names giữa Hibernate và EclipseLink**. So sánh bằng correctness tests, không chỉ tên cấu hình.

## 22. Cache capacity và hiệu năng

Một cache có memory giới hạn, entry size, TTL/TTI và eviction policy riêng backend.

### 22.1. Working set

Nếu 10 triệu entities được đọc phân tán nhưng chỉ 20.000 hot IDs xuất hiện thường xuyên, cần phân tích working set và capacity, không cache hết theo mặc định.

### 22.2. Memory và garbage collection

L2 có thể tăng heap/off-heap, metadata, serialization và GC pressure. Query count giảm nhưng P99 latency có thể tăng nếu cache overhead lớn.

### 22.3. Warm và cold cache

Benchmark phải có cold start, warm state và mixed reads/writes. Nếu chỉ đo 100% hits, kết quả không phản ánh auto-scaling/restart/eviction trong production.

### 22.4. Thundering herd

Sau mass eviction hoặc cache outage, nhiều requests cùng miss hot keys và đánh DB. Cần capacity planning, warm-up, load protection hoặc rate limiting thích hợp.

### 22.5. Hit ratio

\[ \text{Hit ratio} = \frac{\text{L2 hits}}{\text{L2 hits} + \text{L2 misses}} \]

Phải lấy cùng một provider metric definition. Một hit ratio cao không bảo đảm endpoint nhanh nếu remote cache network, deserialize hoặc GC tốn chi phí.

## 23. Multi-tenant data isolation

Giả sử:

~~~text
Tenant A: Category local ID 10 = Electronics
Tenant B: Category local ID 10 = Books
~~~

Nếu cache key chỉ theo local ID và provider/application không phân biệt tenant đúng, có nguy cơ cross-tenant data leak.

### 23.1. Multi-tenancy policy

Kiểm tra tenant ID nằm trong cache identity/namespace theo provider multi-tenancy integration hoặc data model có globally unique keys. Không suy rằng một `WHERE tenantId` ở query sẽ luôn sửa được một cache key collision sai.

### 23.2. Cache không thay authorization

Một `em.find(Class,id)` có cache hit vẫn cần security/tenant validation trước khi dữ liệu được trả. Cache chỉ tối ưu retrieval, không quyết định quyền truy cập.

### 23.3. Sensitive state

Permission, entitlement, token, payment và personal data cần retention/expiry/eviction/encryption/access policy riêng. Nếu cần revoke ngay, không dùng cache stale mà chưa có coherence mechanism.

## 24. Bộ tiêu chí đánh giá provider

| Nhóm | Câu hỏi chính |
|---|---|
| Portability | SharedCacheMode và hints có hoạt động như mong đợi? |
| Configuration | Backend/region factory có được bật? |
| Entity coverage | Những mappings nào cacheable? |
| Correctness | Có trả stale vượt SLA không? |
| Invalidation | JPA/native/external update xử lý thế nào? |
| Transaction | Commit/rollback có được phản ánh đúng? |
| Query behavior | Query/collection cache có riêng không? |
| Cluster | Invalidation giữa 2+ JVMs có ổn? |
| Tenant isolation | Cache identity có phân biệt tenant? |
| Performance | SQL count, P95/P99 có cải thiện? |
| Resources | RAM/GC/cache network có chấp nhận? |
| Failure | Backend down/partition có policy rõ? |
| Operations | Có metrics, alerts và rollback config? |

### 24.1. Không chỉ hỏi “có hỗ trợ cache không?”

Phải hỏi hỗ trợ cache trong **điều kiện nào**: provider/version, backend, region strategy, entity type, query path, single-node hay cluster, DB dialect và transaction manager.

### 24.2. Không lấy tốc độ làm tiêu chuẩn duy nhất

Một provider nhanh nhưng trả data stale ngoài SLA không đáp ứng yêu cầu. Correctness và tenant isolation là điều kiện tiên quyết.

## 25. Một mẫu báo cáo benchmark

| Profile | Data correctness | L2 hit ratio | SELECT/request | P95 latency | RAM | Ghi chú |
|---|---|---|---|---|---|---|
| Hibernate L2 off | Chưa đo | — | Chưa đo | Chưa đo | Chưa đo | Baseline |
| Hibernate selective | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Backend/region |
| EclipseLink cache off | Chưa đo | — | Chưa đo | Chưa đo | Chưa đo | Baseline |
| EclipseLink selective | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Cache policy |
| Tuned provider backend | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | TTL/strategy |

Không điền số liệu không có thật. Khi so sánh, giữ tương đương schema, database, connection pool, heap, workload, hit distribution, read/write ratio và consistency contract.

### 25.1. Metadata phải ghi

~~~text
JPA API version:
Provider and version:
Cache backend and version:
Java runtime:
Database and dialect:
Transaction manager:
SharedCacheMode:
Cacheable entity list:
Region/TTL/capacity:
Instance count:
External writers:
Stale-data SLA:
Observed SQL/hit/miss/latency:
~~~

## 26. Bộ test nghiệm thu tối thiểu

### Test A — L1 không bị nhầm L2

Trong cùng EntityManager, find hai lần cùng ID rồi đo identity/SQL.

### Test B — Hai persistence contexts

EM A load, close; EM B load; quan sát L2 hit và SELECT count.

### Test C — Cache off baseline

`SharedCacheMode.NONE`, đo SQL và latency.

### Test D — Selective policy

Với `ENABLE_SELECTIVE`, Category cacheable, Offer không cacheable theo policy.

### Test E — Evict

Warm một entry, evict theo ID, mở EM mới và xem miss/SQL.

### Test F — Retrieve BYPASS

Đọc trong EM mới, kiểm tra BYPASS thực sự tránh L2 retrieval.

### Test G — Store REFRESH

Đọc DB sau external update với BYPASS + REFRESH, rồi kiểm tra entry mới.

### Test H — Transaction commit

Managed update commit; EM khác đọc đúng state.

### Test I — Transaction rollback

Update rồi rollback; cache không trả uncommitted state như đã thành công.

### Test J — Bulk/native SQL

Warm cache rồi update qua bulk JPQL hoặc external SQL; xác nhận policy stale/evict.

### Test K — Cluster

Node A commit update, node B đọc theo SLA.

### Test L — Tenant isolation

Hai tenants dùng cùng local ID không được đọc nhầm cached data.

### Test M — Backend outage

Cache down; ứng dụng fallback/fail theo policy, không trả dữ liệu sai.

### Test N — Query/collection cache

Nếu bật provider extensions, test riêng query-result membership, collection mutations và invalidation.

## 27. Một phép thử external writer

~~~text
EM A:
  find Category#10, warm L2
  close

JDBC transaction:
  UPDATE catalog_category
  SET display_name = 'Tên mới'
  WHERE id = 10
  COMMIT

EM B:
  find Category#10 với cache policy mặc định
  close

EM C:
  find Category#10 với retrieve BYPASS
  close

Compare:
  Giá trị trả về
  SQL/statistics
  Stale window được chấp nhận hay không
~~~

Không mặc định EM B chắc chắn stale hoặc chắc chắn fresh; đó chính là điều **bài đánh giá provider phải xác minh**. Dùng EM mới giúp tránh L1 che kết quả. Đảm bảo external update commit trước khi đọc và cleanup fixture sau test.

## 28. Những lỗi tư duy phổ biến

| Nhận định | Vì sao sai |
|---|---|
| `@Cacheable(true)` nghĩa đã bật L2 | Thiếu backend/config |
| Find hai lần một EM không SQL là L2 hit | Có thể là L1 |
| Evict làm managed entity tự refresh | L2 và L1 khác nhau |
| BYPASS đọc DB dù L1 đã có entity | BYPASS chỉ liên quan shared cache |
| Cache.contains true bảo đảm zero SQL | Query/associations/race vẫn có thể phát SQL |
| L2 tự cache kết quả mọi JPQL | Query cache là tính năng khác |
| Root cached nghĩa Lines cached | Collection cache riêng |
| L2 sửa N+1 | Fetch plan cần tối ưu |
| Shared nghĩa tất cả pods cùng dữ liệu | Cần distributed coordination |
| @Version tự invalidate raw SQL | External writers có thể không thông báo |
| TTL bảo đảm tức thời nhất quán | TTL cho phép stale window |
| READ_WRITE xử lý mọi external writer | Không có blanket guarantee |
| Cache mọi entity sẽ nhanh hơn | Có memory/write/eviction overhead |
| Query cache là API JPA portable | Không |
| Đổi Hibernate sang EclipseLink không cần đổi gì | Vendor extensions và defaults khác |
| Cache hit tự xác nhận permission | Authorization vẫn bắt buộc |

## 29. Bài tập thực hành

### Bài 1. L1 hay L2?

Hai lần `find` cùng ID trong một EntityManager chỉ phát một SELECT.

**Đáp án:** Chưa chứng minh L2; có thể do L1.

### Bài 2. ENABLE_SELECTIVE

Category có `@Cacheable(true)`, Offer không annotation.

**Đáp án:** Category được chọn, Offer không được chọn theo shared mode này.

### Bài 3. DISABLE_SELECTIVE

Offer có `@Cacheable(false)`.

**Đáp án:** Offer bị loại khỏi shared cache; entity không annotation thường được phép cache.

### Bài 4. NONE

**Câu hỏi:** Có tắt identity map không?

**Đáp án:** Không. L1 vẫn hoạt động.

### Bài 5. UNSPECIFIED

Hai providers cùng dùng mode này cho SQL counts khác nhau.

**Đáp án:** Default phụ thuộc provider; phải ghi config/version và dùng explicit policy nếu cần so sánh.

### Bài 6. Evict

Evict Category#10 nhưng current EM còn giữ object cũ.

**Đáp án:** Evict L2 không xóa managed instance L1.

### Bài 7. BYPASS

Một EM đã managed Category, find cùng ID với BYPASS vẫn có data cũ.

**Đáp án:** BYPASS shared cache không buộc L1 reload. Test bằng EM mới.

### Bài 8. Refresh cache

Muốn đọc DB và cập nhật L2 entry.

**Đáp án:** Thử retrieve BYPASS + store REFRESH trong context mới; kiểm chứng provider.

### Bài 9. Query cache

SELECT Categories theo LIKE vẫn chạy SQL khi entity L2 warmed.

**Đáp án:** Entity cache không tự lưu query-result membership.

### Bài 10. @Version

External SQL sửa Category nhưng không thông báo L2.

**Đáp án:** @Version không tự bảo vệ cache khỏi mọi external writes.

### Bài 11. Hai JVMs

Node A update, node B có local cached entry.

**Đáp án:** Cần invalidation/coordination phù hợp để đảm bảo freshness.

### Bài 12. Cross-tenant key

Hai tenants có ID=10, dữ liệu khác nhau.

**Đáp án:** Cache key/namespace phải phân biệt tenant; kiểm thử isolation.

### Bài 13. High hit, slow API

L2 hit rate 95%, P99 lại tăng.

**Đáp án:** Đo network cache, CPU/GC, serialization và memory; hit ratio không phải mục tiêu cuối.

### Bài 14. Spring @Cacheable

Có Spring cache ở service và JPA @Cacheable ở entity.

**Đáp án:** Hai lớp cache khác nhau, cần invalidation policies độc lập.

### Bài 15. Provider migration

Chuyển Hibernate sang EclipseLink và giữ Hibernate-specific region properties.

**Đáp án:** Không có portability guarantee; cấu hình lại và chạy acceptance tests.

### Bài 16. Cache backend down

**Đáp án:** Cần fallback/timeout/error policy, dự tính DB capacity và kiểm tra correctness.

### Bài 17. Bulk UPDATE

JPQL bulk UPDATE thay field nhưng EM đang quản lý entity cũ.

**Đáp án:** L1 có thể stale; kiểm thử thêm L2 invalidation theo provider.

### Bài 18. Cache all

Ứng dụng có triệu Orders thay đổi thường xuyên và bật ALL.

**Đáp án:** Có thể không hiệu quả, nhiều invalidations và stale risk; bắt đầu selective với read-mostly data.

### Bài 19. Collection cache

Order root có L2 hit nhưng `order.getLines()` vẫn phát SQL.

**Đáp án:** Root cache không tự đồng nghĩa collection membership cached.

### Bài 20. TTL

TTL 30 giây, requirement là thấy mọi committed update trong một giây.

**Đáp án:** TTL đơn thuần không đủ để bảo đảm; cần invalidation/consistency protocol hoặc bypass authoritative reads.

## 30. Checklist khi đánh giá provider

1. JPA provider và version đã được ghi?
2. Cache backend/module thực sự được cài?
3. SharedCacheMode có explicit hay UNSPECIFIED?
4. `@Cacheable` áp dụng đúng entities?
5. Có test hai EntityManagers riêng?
6. Có phân biệt L1, L2 và query cache?
7. Có SQL instrumentation và cache hit/miss metrics?
8. Có test `Cache.contains`, `evict`, `evictAll`?
9. Có test L1 vẫn giữ instance sau L2 eviction?
10. Retrieve BYPASS có được kiểm chứng trong EM mới?
11. Store REFRESH có làm mới entry như mong muốn?
12. Có test managed update, commit, rollback?
13. Có test JPQL bulk và external SQL?
14. Có SLA độ mới dữ liệu?
15. Có test query/collection cache riêng nếu sử dụng?
16. Có test multi-node cache coordination?
17. Cache keys có phân biệt tenant không?
18. Có authentication/authorization trước khi trả cached data?
19. Có TTL, capacity và eviction policy?
20. Working set có vừa memory?
21. Có test cold/warm/mixed read/write workload?
22. Có quan sát DB CPU, heap/GC, P95/P99?
23. Có test backend outage và fallback?
24. Có tránh dùng stale cache cho critical write decisions?
25. Có tài liệu hóa provider-specific extensions?
26. Có contract tests khi upgrade/chuyển provider?
27. Có kế hoạch targeted eviction và rollback config?
28. Có người chịu trách nhiệm vận hành và xử lý stale incidents?

## 31. Quy trình quyết định

~~~text
              Có nên bật shared cache cho entity?
                            |
                            v
                    Đọc nhiều, ghi ít?
                      /           \
                    Không         Có
                     |             |
                     v             v
                Cân nhắc       Định nghĩa SLA
                không cache    stale/invalidation
                                   |
                                   v
                         SharedCacheMode +
                         @Cacheable
                                   |
                                   v
                       Cấu hình provider/backend
                                   |
                                   v
                        Test hai EntityManagers
                                   |
                                   v
                       Test commit/rollback/
                       bulk SQL/external writers
                                   |
                                   v
                        Test multi-node/tenant
                                   |
                                   v
                         Correctness đạt SLA?
                            /           \
                          Không         Có
                           |             |
                           v             v
                       Tắt/rework     Đo P95, SQL,
                       coherence      hit ratio, RAM
                                        |
                                        v
                                Lợi ích đo được?
                                  /         \
                                Không        Có
                                  |           |
                                  v           v
                               Tắt/tối ưu  Bật chọn lọc
                                          + monitor
~~~

## 32. Tổng kết

**Shared cache của JPA là một công cụ tối ưu đọc giữa nhiều persistence contexts, nhưng không phải bảo đảm mọi provider đã bật hoặc phối hợp cache giống nhau.** JPA chuẩn hóa `SharedCacheMode`, `@Cacheable`, `EntityManagerFactory.getCache()` và các retrieve/store hints. Còn backend, region policies, query/collection cache, TTL, metrics và cluster consistency là những quyết định phụ thuộc provider/version.

Các nguyên tắc quan trọng:

1. **L1 luôn gắn với persistence context; L2 là tầng chia sẻ tùy provider và cấu hình.**
2. **Hai lần find trong cùng EM không chứng minh L2.** Hãy đo qua hai EMs độc lập.
3. **ENABLE_SELECTIVE thường dễ kiểm soát khi bắt đầu**, nhất là với reference data đọc nhiều và ghi ít.
4. **@Cacheable(true) chỉ diễn đạt eligibility**; phải xác minh cache backend, region và SQL behavior.
5. **Cache API evict L2 chứ không tự refresh L1**; BYPASS shared cache cũng không làm biến mất managed instance.
6. **Entity cache, query-result cache và collection cache là những cơ chế khác nhau**; không suy rộng từ một L2 hit.
7. **Hibernate và EclipseLink có defaults/extensions khác nhau**, cần báo cáo chính xác provider version/cache integration.
8. **Bulk DML, native SQL, external writers và multi-node deployments là các trường hợp quan trọng để test invalidation.**
9. **@Version, TTL và cache hit ratio không thay một consistency SLA rõ ràng.**
10. **Tenant isolation, security và tính đúng nghiệp vụ luôn ưu tiên hơn lợi ích giảm SQL.**
11. **Benchmark bằng data/workload thực**, gồm cold/warm cache, read/write mix, SQL count, P95/P99 và memory.
12. **Bật shared cache có kiểm soát**, với observability, fallback và regression tests khi nâng cấp/chuyển provider.

Đánh giá cache chia sẻ không dừng ở câu hỏi “provider có hỗ trợ hay không?”, mà phải xác định **hỗ trợ với cấu hình nào, trong phạm vi nào, đúng dữ liệu đến mức nào, khi cập nhật ai chịu trách nhiệm invalidation và hiệu năng cải thiện được bao nhiêu**. Khi đã chứng minh được các điều đó, shared cache mới là một tối ưu đáng tin cậy trong ứng dụng JPA.
