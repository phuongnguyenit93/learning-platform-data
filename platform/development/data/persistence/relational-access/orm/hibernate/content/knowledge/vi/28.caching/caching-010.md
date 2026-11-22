# Đo hit, miss, put và chi phí truy vấn sau khi bật bộ nhớ đệm

## 1. Bật cache không đồng nghĩa ứng dụng đã nhanh hơn

Hibernate có nhiều cơ chế bộ nhớ đệm giúp giảm số lần đọc database, nhưng **mức độ sử dụng cache và hiệu quả thực tế là hai câu hỏi khác nhau**. Một hệ thống có hit ratio cao vẫn có thể phản hồi chậm vì truy vấn không được cache, N+1, khóa database, hoặc dữ liệu phải được serialize nhiều lần. Ngược lại, một cache ít hit có thể vẫn hữu ích nếu những lần hit tránh được truy vấn rất đắt đỏ.

Khi bật cache, cần trả lời bốn nhóm câu hỏi:

1. **Hit:** Bao nhiêu lần ứng dụng tìm thấy dữ liệu hợp lệ trong cache?
2. **Miss:** Bao nhiêu lần có yêu cầu đọc cache nhưng không tìm thấy dữ liệu dùng được?
3. **Put:** Bao nhiêu lần dữ liệu được đưa vào cache?
4. **Chi phí thực tế:** Sau khi bật cache, số SQL statements, database round trips, thời gian truy vấn, heap, GC, CPU và độ trễ ứng dụng thay đổi như thế nào?

Trong Hibernate, các chỉ số hit/miss/put có thể đến từ **second-level cache** và **query cache**. Cần đo riêng hai loại; không gộp các counter khác bản chất thành một “hit rate” duy nhất.

Ví dụ hai kết quả:

```text
Thử nghiệm A:
  Second-level cache hit ratio = 95%
  Thời gian API p95 không thay đổi
  90% thời gian request nằm ở một SQL aggregate không cache

Thử nghiệm B:
  Second-level cache hit ratio = 55%
  Số lần load Product bằng ID giảm mạnh
  Thời gian API p95 tốt hơn đáng kể
```

Ví dụ chỉ minh họa khả năng diễn giải. Kết luận triển khai phải dựa vào số đo trên workload của dự án, không suy ra hiệu năng từ tỷ lệ hit đơn lẻ.

## 2. Ba tầng cache trong một ứng dụng Hibernate

Trước khi đọc thống kê, phải phân biệt các tầng:

| Tầng | Phạm vi | Nội dung điển hình | Chỉ số cần quan sát |
|---|---|---|---|
| First-level cache | Một `Session`/`EntityManager` | Managed entity theo identity | Số SELECT, entity loads, phạm vi persistence context |
| Second-level cache (L2) | Nhiều session trong cùng `SessionFactory`, hoặc cluster theo provider | Entity state, collection state, natural-id data theo region | L2 hit/miss/put, region memory/evictions |
| Query cache | Vùng cache cho kết quả của query được đánh dấu cacheable | Query result theo query key/parameters, tùy Hibernate version và result layout | Query cache hit/miss/put, SQL tránh được và chi phí hydrate |

Sơ đồ tổng quan:

```text
Application
    |
    v
Session / EntityManager
    |
    +--> First-level cache (persistence context)
    |        |
    |        +-- hit --> managed entity có sẵn
    |        |
    |        +-- miss --> Hibernate load path
    |                        |
    |                        v
    |                 Second-level cache?
    |                    /        \
    |                 hit         miss
    |                  |            |
    |                  v            v
    |            cached state     SELECT DB
    |                  |            |
    |                  +------------+
    |                        |
    |                        v
    |                  managed entity
    |
    +--> Cacheable query
               |
               +-- Query cache hit --> cached result handling
               |
               +-- Query cache miss --> execute SQL
                                            |
                                            v
                                        cache result
```

Sơ đồ là mô hình giải thích, không phải thứ tự tuyệt đối cho mọi loại query/fetch plan. Truy vấn có thể dùng query cache rồi truy cập L2 để dựng entity, và cache hit không bảo đảm không còn SQL nào trong cả request.

## 3. First-level cache thường che khuất việc đo L2

First-level cache là một phần của persistence context và không cần bật riêng. Nếu cùng một session gọi:

```java
Product a = entityManager.find(Product.class, 10L);
Product b = entityManager.find(Product.class, 10L);
```

lần thứ hai thường lấy cùng managed instance từ persistence context mà không cần truy vấn database hay hỏi second-level cache. Kết quả:

```text
Lần 1: Session chưa có Product #10
        -> L2 lookup hoặc SELECT database

Lần 2: Session đã có Product #10
        -> trả instance managed ngay trong Session
        -> không nhất thiết phát sinh L2 hit
```

Nếu benchmark lặp `find()` 100 lần trong cùng một `EntityManager` rồi quan sát không có SQL, đó **không chứng minh L2 hoạt động**.

Để đo L2, cần tạo các session/persistence context độc lập giữa những lần đọc, hoặc clear persistence context có kiểm soát. Trong production, đừng clear session đang phục vụ nghiệp vụ chỉ để tăng counter hit.

## 4. Second-level cache lưu những loại dữ liệu nào?

Second-level cache của Hibernate được cấu hình theo cache provider và region. Các loại dữ liệu thường gặp:

- State của một entity được đánh dấu cacheable.
- State của collection association nếu collection được cấu hình cache.
- Thông tin natural ID trong các cấu hình phù hợp.
- Dữ liệu phục vụ cache strategy và invalidation.

Điều quan trọng: **entity cache và collection cache là hai thứ khác nhau**.

Ví dụ:

```java
@Entity
@Cacheable
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE)
public class Product {
    @Id
    private Long id;

    private String sku;
    private String name;
}
```

L2 entity cache giúp giảm việc đọc state của Product theo identity. Nếu có:

```java
@OneToMany(mappedBy = "product", fetch = FetchType.LAZY)
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE)
private Set<ProductImage> images = new HashSet<>();
```

collection cache có thể giữ thông tin các phần tử/identifier thuộc collection. Nếu phần tử là entity mà bản thân không được cache, Hibernate có thể vẫn cần SQL để tải entity state của từng phần tử. Do đó hit ở collection region không đảm bảo mọi entity bên trong đều có cache hit.

## 5. Cấu hình bật cache chỉ là bước đầu

Ví dụ property trong một ứng dụng dùng Hibernate:

```properties
hibernate.cache.use_second_level_cache=true
hibernate.cache.use_query_cache=true
hibernate.generate_statistics=true
```

Trong Spring Boot:

```properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.use_query_cache=true
spring.jpa.properties.hibernate.generate_statistics=true
```

Đây mới là **các công tắc chức năng/thống kê**, chưa phải cấu hình cache backend hoàn chỉnh. Cần:

1. Có cache provider tương thích Hibernate version, ví dụ provider dựa trên JCache khi phù hợp.
2. Cấu hình region factory theo provider và thư viện đi kèm.
3. Cấu hình region capacity, TTL/expiry, eviction policy và concurrency strategy.
4. Đánh dấu các entity/collection được phép cache.
5. Đánh dấu từng query cần query cache khi sử dụng query cache.

Không nên cấu hình mọi entity là cacheable chỉ vì đã bật L2. Entity biến động mạnh hoặc có kích thước lớn có thể gây churn, inconsistency và memory pressure.

### 5.1. Cẩn trọng với thống kê trong production

`hibernate.generate_statistics=true` hữu ích khi đo và test. Thu thập thống kê có chi phí; quyết định bật liên tục trong production nên dựa trên quan sát thực tế và công cụ metrics đang dùng. Có thể bật thống kê trong thời gian giới hạn để điều tra, hoặc xuất metric đã chọn qua hệ thống quan sát phù hợp.

Không để logging SQL, bind parameters hay statistic dump quá chi tiết làm thay đổi kết quả benchmark hoặc lộ thông tin nhạy cảm.

## 6. CacheConcurrencyStrategy ảnh hưởng semantics và chi phí

Hibernate có các cache concurrency strategies, ví dụ:

| Strategy | Ý nghĩa khái quát | Cân nhắc |
|---|---|---|
| `READ_ONLY` | Dữ liệu về cơ bản không thay đổi qua Hibernate | Thích hợp reference data bất biến; ghi thay đổi không phù hợp |
| `READ_WRITE` | Có cơ chế phối hợp cache với ghi nhằm tránh nhiều kiểu stale read | Phổ biến cho entity có thay đổi, tốn chi phí coordination |
| `NONSTRICT_READ_WRITE` | Chấp nhận cửa sổ không nhất quán trong một số tình huống | Chỉ dùng khi nghiệp vụ cho phép dữ liệu hơi cũ |
| `TRANSACTIONAL` | Dựa vào provider có hỗ trợ transactional cache | Phụ thuộc provider và nền tảng transaction |

Strategy không phải nút “bật tốc độ cao”. Một chiến lược cho tỷ lệ hit tốt nhưng tạo stale read có thể sai về nghiệp vụ. Benchmark phải giữ nguyên yêu cầu consistency và kiểm thử read-write concurrency.

Ví dụ danh mục quốc gia ít thay đổi có thể hợp với READ_ONLY; tồn kho đang giao dịch liên tục thường không phải đối tượng cache đơn giản. Không dùng cache để thay thế optimistic locking hoặc database constraints.

## 7. Ý nghĩa chính xác của hit, miss và put

### 7.1. Hit

Một **cache hit** được ghi nhận khi một cache lookup tìm được entry đủ điều kiện phục vụ lookup ở tầng đó.

Ví dụ L2:

```text
Session A -> find(Product #10)
             -> DB load -> L2 put

Session B -> find(Product #10)
             -> L2 hit -> không cần DB load state Product
```

L2 hit ở đây không bao gồm mọi lần Product #10 được lấy từ first-level cache. Nó cũng không bảo đảm request không phát sinh SQL cho association khác.

### 7.2. Miss

Một **cache miss** được ghi nhận khi có lookup nhưng không có entry dùng được. Cache miss có thể dẫn tới DB read, nhưng không nên xem **mỗi miss tương ứng chính xác một SELECT**:

- Một SQL có thể tải nhiều entities.
- Batch fetching hoặc join fetching có thể gộp nhiều load.
- Cache lookup có thể diễn ra sau những quyết định load khác.
- Query cache miss có thể kéo theo nhiều entity loads.
- Một số lookup loại dữ liệu không được cache không đi vào counter tương ứng.

### 7.3. Put

Một **cache put** là thao tác đưa entry vào cache/region theo logic của provider và Hibernate. Nó không nhất thiết là một INSERT/UPDATE vào database.

Các nguồn put:

- Đọc từ DB rồi đưa entity state vào L2.
- Ghi entity rồi cập nhật/đặt entry theo strategy phù hợp.
- Thực thi query cacheable rồi đưa kết quả vào query cache.
- Nạp lại sau eviction/expiry.

Không yêu cầu `puts = misses`. Có thể có cache misses không dẫn tới put, nhiều puts do write path hoặc entry đã được làm mới, và điều kiện put phụ thuộc concurrency strategy/provider.

## 8. Hai nhóm statistics không được trộn lẫn

| Counter | Loại cache | Điều đo |
|---|---|---|
| `secondLevelCacheHitCount` | L2 | Lookup L2 thành công |
| `secondLevelCacheMissCount` | L2 | Lookup L2 không có dữ liệu dùng được |
| `secondLevelCachePutCount` | L2 | Entry được đưa vào L2 |
| `queryCacheHitCount` | Query cache | Cacheable query tìm thấy cached result |
| `queryCacheMissCount` | Query cache | Cacheable query không có cached result hợp lệ |
| `queryCachePutCount` | Query cache | Kết quả được đưa vào query cache |

Không cộng L2 hit với query cache hit để tạo một tỷ lệ chung rồi gọi nó là “cache hiệu quả 95%”. Query cache có thể hit trong khi entity state cần hydrate vẫn miss ở L2, hoặc ngược lại.

Ngoài ra, không suy ra `queryCacheMissCount` phản ánh tất cả các query không sử dụng cache. Những query **không được đánh dấu cacheable** thường đi thẳng database và không phải là miss của query cache.

## 9. Đọc Hibernate Statistics bằng Java

Hibernate cung cấp `org.hibernate.stat.Statistics` ở phạm vi SessionFactory:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = sessionFactory.getStatistics();

long l2Hits = stats.getSecondLevelCacheHitCount();
long l2Misses = stats.getSecondLevelCacheMissCount();
long l2Puts = stats.getSecondLevelCachePutCount();

long queryHits = stats.getQueryCacheHitCount();
long queryMisses = stats.getQueryCacheMissCount();
long queryPuts = stats.getQueryCachePutCount();
```

Các phương thức tổng hợp trên có trong những Hibernate versions hỗ trợ Statistics tương ứng. Khi nâng cấp Hibernate, cần kiểm tra API và định nghĩa counter của phiên bản được dùng, đặc biệt với thông tin region hoặc query cache layout.

### 9.1. Statistics có phạm vi SessionFactory

Counter tổng thường tích lũy trên một SessionFactory. Nếu một server phục vụ 1.000 requests song song, không thể coi delta trong một request là chính xác riêng request đó khi những request khác cũng thay đổi counters.

Trong integration test đơn luồng có fixture riêng, đo trước/sau một workload là khả thi. Trong production, nên đo **theo thời gian và instance**, xuất metrics tới monitoring và dùng traffic segmentation/tracing để liên hệ với endpoint.

## 10. Tạo snapshot chỉ số trước và sau workload

Để không xóa thống kê toàn cục, có thể tạo snapshot:

```java
public record CacheCounters(
    long l2Hit,
    long l2Miss,
    long l2Put,
    long queryHit,
    long queryMiss,
    long queryPut
) {
    public static CacheCounters from(Statistics s) {
        return new CacheCounters(
            s.getSecondLevelCacheHitCount(),
            s.getSecondLevelCacheMissCount(),
            s.getSecondLevelCachePutCount(),
            s.getQueryCacheHitCount(),
            s.getQueryCacheMissCount(),
            s.getQueryCachePutCount());
    }

    public CacheCounters minus(CacheCounters prior) {
        return new CacheCounters(
            l2Hit - prior.l2Hit,
            l2Miss - prior.l2Miss,
            l2Put - prior.l2Put,
            queryHit - prior.queryHit,
            queryMiss - prior.queryMiss,
            queryPut - prior.queryPut);
    }
}
```

Sử dụng:

```java
Statistics stats = sessionFactory.getStatistics();
CacheCounters before = CacheCounters.from(stats);

runReadWorkload();

CacheCounters delta =
    CacheCounters.from(stats).minus(before);

System.out.println(delta);
```

Ưu điểm: không phải gọi `stats.clear()` trong hệ thống có traffic. Hạn chế: khi nhiều threads dùng cùng SessionFactory, delta vẫn gộp hoạt động của các threads đó.

Trong integration test cô lập, có thể gọi `Statistics.clear()` trước mỗi kịch bản để tiện so sánh; **không reset Statistics toàn cục trên production chỉ để đo một request**.

## 11. Tính hit ratio và miss ratio đúng cách

Với một loại cache trong một khoảng quan sát:

```text
lookups = hits + misses

hitRatio = hits / lookups
missRatio = misses / lookups
```

Nếu không có lookup (hits + misses = 0), hit ratio **không được xác định**; không tự động báo 100% hay 0% như thể đã có bằng chứng.

Trong Java:

```java
static OptionalDouble hitRatio(long hits, long misses) {
    long lookups = hits + misses;
    return lookups == 0
        ? OptionalDouble.empty()
        : OptionalDouble.of((double) hits / lookups);
}
```

Ví dụ:

```text
Khoảng đo:
  L2 hits   = 800
  L2 misses = 200
  L2 puts   = 180

L2 hit ratio = 800 / (800 + 200) = 80%
L2 miss ratio = 20%
```

Puts không tham gia mẫu số của hit ratio. Nếu có 10.000 puts do dữ liệu luôn thay đổi nhưng chỉ 800 hits, cần đánh giá cache churn và overhead, không chỉ nhìn tỷ lệ hit.

### 11.1. Đo theo khoảng thời gian

Trong production, counters tích lũy từ thời điểm khởi động có thể che mất thay đổi mới. Nên đo delta theo cửa sổ:

- 1 phút hoặc 5 phút để quan sát biến động ngắn.
- 1 giờ để đánh giá traffic ổn định hơn.
- So sánh peak hour và off-peak.
- Tách instance khi ứng dụng scale horizontally.

Một tỷ lệ hit tích lũy cao từ tuần trước không nói nhiều về hành vi cache sau khi deployment hoặc data update hôm nay.

## 12. Hit ratio cao không chứng minh hiệu năng cao

Giả sử:

```text
Endpoint A:
  1.000 L2 hits cho một bảng lookup nhỏ
  1 query aggregate mất 300 ms

Endpoint B:
  200 L2 hits cho entity đắt đỏ
  100 SQL joins được tránh
```

A có thể có hit ratio cao hơn nhưng latency tệ hơn. Cần xem:

- **Số SQL được tránh:** có giảm không?
- **Thời gian SQL được tránh:** query tránh được đắt hay rẻ?
- **Thời gian lookup cache:** đọc cache có rẻ hơn DB read bao nhiêu?
- **Chi phí ghi/invalidate:** cache có bị put/evict liên tục không?
- **Chi phí bộ nhớ:** heap/off-heap, GC, serialization.
- **Độ trễ end-to-end:** p50/p95/p99 của API/batch.

Chỉ số hit/miss/put là **giải thích về hành vi cache**, không phải kết quả kinh doanh cuối cùng của tối ưu.

## 13. Query cache khác L2 entity cache như thế nào?

Một query:

```hql
select p
from Product p
where p.category.id = :categoryId
order by p.id
```

không được tự động cache kết quả chỉ vì entity Product đã được L2 cache. Hibernate vẫn phải tìm danh sách Product IDs phù hợp qua SQL, trừ khi kết quả query được cache bằng cơ chế riêng.

Query cache dùng cho các query được đánh dấu cacheable và khi query cache đã bật:

```java
List<Product> products = session.createSelectionQuery("""
    select p
    from Product p
    where p.category.id = :categoryId
    order by p.id
    """, Product.class)
    .setParameter("categoryId", categoryId)
    .setCacheable(true)
    .getResultList();
```

Lần đầu có thể là query cache miss, SQL được thực thi, kết quả được put. Lần sau với cùng query key và data còn hợp lệ có thể hit. Chi tiết dữ liệu lưu trong query cache, cách hydrate entity và phụ thuộc L2 khác nhau theo Hibernate version/result layout; **query cache hit không bảo đảm zero SQL cho toàn request**.

### 13.1. Query key phụ thuộc nhiều yếu tố

Một kết quả cached query thường được phân biệt bởi:

- Nội dung query và các query options liên quan.
- Bound parameter values.
- Pagination/limits và các tham số ảnh hưởng kết quả.
- Các điều kiện/filter/tenant được provider đưa vào key.

Nếu mỗi request có filter, timestamp hoặc page cursor khác nhau, số lần lặp lại đúng query key có thể thấp. Query cache sẽ tạo nhiều misses/puts và ít hits.

Do đó query cache hợp hơn với tập truy vấn lặp lại có nhiều reuse, ít biến động; không phải mặc định tốt cho mọi search API.

## 14. Query cache hit chưa chắc đồng nghĩa không phát SQL

Ví dụ query cache giữ một kết quả liệt kê Product, nhưng các entity Product chưa có state trong L2 hoặc bị evict:

```text
Cacheable query: category=15
      |
      v
Query cache hit
      |
      v
Cần dựng Product entities
      |
      +-- L2 available? --> cache hits
      |
      +-- L2 unavailable --> có thể cần SELECT entity state
```

Phần này phụ thuộc result cache layout của Hibernate version và loại projection. Đối với một số query projection scalar/DTO, kết quả query cache có thể chứa trực tiếp giá trị cần thiết. Không lấy một mô tả cố định cho mọi phiên bản.

Khi đo query cache:

1. Xem `queryCacheHitCount`.
2. Xem tổng SQL và thời gian database.
3. Xem L2 hit/miss nếu kết quả chứa entity.
4. Xem thời gian hydrate/transform kết quả.
5. Xem memory và chi phí invalidation.

Một query cache hit tốt là hit giúp giảm **chi phí toàn luồng**, không chỉ tăng một counter.

## 15. Cấu hình một query cacheable có chủ đích

Ví dụ:

```java
List<CategoryView> rows = session.createSelectionQuery("""
    select new com.example.read.CategoryView(
        c.id, c.name)
    from Category c
    where c.enabled = true
    order by c.name, c.id
    """, CategoryView.class)
    .setCacheable(true)
    .setCacheRegion("reference-category-query")
    .getResultList();
```

Đây là HQL constructor projection, giả định DTO `CategoryView` có constructor tương thích. Query có ít biến thể và dữ liệu category ít thay đổi là ứng viên đáng thử.

Một query search với tham số biến thiên nhanh:

```java
session.createSelectionQuery("""
    select p
    from Product p
    where lower(p.name) like :pattern
    order by p.updatedAt desc, p.id desc
    """, Product.class)
    .setParameter("pattern", pattern)
    .setCacheable(true)
    .getResultList();
```

có thể có reuse thấp và invalidation thường xuyên. Việc bật cacheable ở query này cần đo, không nên làm theo phản xạ.

### 15.1. Đặt tên region theo use case

Region có tên rõ như `reference-category-query` giúp phân biệt cache thường xuyên truy cập với cache cho search. Dù API cung cấp region-level statistics khác nhau giữa Hibernate versions, cache provider thường có metrics về size, eviction, expiration và memory.

Không đặt tất cả query vào một region không có phân tách rồi khó xác định truy vấn nào gây churn.

## 16. Đo theo region quan trọng hơn một tổng số

Ví dụ hệ thống có ba entity regions:

```text
ReferenceCountry:
  hits   = 900, misses = 10, puts = 10

Product:
  hits   = 100, misses = 300, puts = 290

ShoppingCart:
  hits   = 5,   misses = 80, puts = 75
```

Tổng L2 hit ratio có thể trông không quá xấu nhờ ReferenceCountry, nhưng ShoppingCart đang có churn và có thể không đáng cache.

Khi đo, cần lập bảng theo region:

| Region | Hits | Misses | Puts | Hit ratio | Evictions | Memory | Ghi chú |
|---|---:|---:|---:|---:|---:|---:|---|
| Product | Đo | Đo | Đo | Tính | Provider metric | Provider metric | Đọc theo ID |
| Category | Đo | Đo | Đo | Tính | Provider metric | Provider metric | Dữ liệu ít thay đổi |
| OrderLine collection | Đo | Đo | Đo | Tính | Provider metric | Provider metric | Collection lớn |
| Query region | Đo | Đo | Đo | Tính | Provider metric | Provider metric | Query reuse |

Tên API Hibernate để lấy region statistics có thể khác theo major version; ví dụ Hibernate 6 có các dạng thống kê domain-data/query region, còn tài liệu Hibernate cũ có class/method khác. Hãy dùng API của version đang triển khai. Không áp dụng nguyên mã từ Hibernate 5 lên Hibernate 6 mà không kiểm tra compile.

## 17. Puts nhiều và ít hits: dấu hiệu cache churn

**Cache churn** xảy ra khi dữ liệu liên tục được đưa vào cache nhưng ít được tái sử dụng trước khi bị thay/evict/expire.

Ví dụ:

```text
Trong 5 phút:
  puts   = 10.000
  hits   = 100
  misses = 9.900
```

Không thể chỉ dựa vào các con số này kết luận lỗi, vì put/miss có semantics khác nhau; nhưng chúng là tín hiệu nên điều tra:

- Data có read-after-write reuse thực sự không?
- Entries bị eviction vì region quá nhỏ?
- TTL quá ngắn?
- Có nhiều khóa chỉ được truy cập một lần?
- Query cache keys quá phân mảnh do filters/pagination?
- Mỗi update có làm invalidation một vùng rộng?
- Nhiều application nodes có cache cục bộ riêng, giảm locality?

Một put tốn CPU, serialization và bộ nhớ mà không có hit sau đó có thể là overhead ròng. Nếu cache data có chi phí nạp rất thấp và reuse hiếm, bỏ cache region đó có thể tốt hơn.

## 18. Miss nhiều: chưa chắc phải tăng TTL hoặc dung lượng

Nếu tỷ lệ miss cao, trước hết cần phân loại:

| Nguyên nhân | Dấu hiệu | Can thiệp có thể thử |
|---|---|---|
| Cold start | Miss cao sau deploy/start | Warm-up có giới hạn hoặc chấp nhận giai đoạn lạnh |
| Working set lớn hơn capacity | Eviction liên tục | Tăng capacity có đo memory hoặc đổi caching policy |
| TTL quá ngắn | Entry expire trước lần đọc lại | Điều chỉnh TTL theo freshness SLO |
| Khóa có tính duy nhất cao | Mỗi key chỉ truy cập một lần | Không cache workload đó |
| Nhiều writers | Entry thường bị invalidated | Tách read models hoặc bỏ L2 cho entity quá biến động |
| Query parameters quá đa dạng | Query cache miss/put lớn | Chỉ cache subset query ổn định |
| Nhiều nodes với local cache | Mỗi node tự warm | Chọn topology phù hợp, đo coherence cost |
| Query không được cacheable | SQL chạy nhưng query miss counter thấp | Phân biệt query cache off/bypass với miss |

Không sửa configuration theo một tỷ lệ aggregate. Cần xem region, time window, working set, eviction, request pattern và consistency requirements.

## 19. Thiết kế thí nghiệm cache có baseline

Một thí nghiệm tin cậy thường có ít nhất ba giai đoạn:

1. **Baseline, cache disabled:** đo truy vấn/latency khi chưa bật L2/query cache.
2. **Cold cache:** bật cache nhưng region chưa chứa dữ liệu; đo chi phí lookup, miss và put.
3. **Warm cache:** lặp lại workload có cùng key/query distribution khi entries còn hợp lệ; đo hits và SQL giảm được.

```text
Thử nghiệm A                Thử nghiệm B
Cache disabled              Cache enabled
      |                           |
      v                           v
Same dataset                Cold pass
Same DBMS/version                 |
Same input                        v
Same concurrency            Warm pass
      |                           |
      +-------------+-------------+
                    |
                    v
            Compare end-to-end:
            SQL, latency, CPU,
            memory, hits/misses/puts,
            DB load, correctness
```

Nếu baseline không bật cache nhưng warm test lại dùng số request/tenant khác, so sánh không công bằng.

### 19.1. Không gộp cold và warm vô tình

Một benchmark chạy 100 vòng lặp với cùng 10 IDs trong cùng một Session thực chất có thể chỉ đo first-level cache. Một benchmark dùng Session khác nhưng dữ liệu luôn thay đổi có thể chỉ đo cold miss.

Phải định nghĩa workload:

- Tỷ lệ hot keys vs long-tail keys.
- Có write/invalidation xen kẽ không?
- Có bao nhiêu Session/requests?
- Query parameters được lặp lại bao nhiêu lần?
- Có cache warm-up trước khi bắt đầu timer không?

Không có một cấu hình cache lý tưởng tách rời traffic thực.

## 20. Thí nghiệm L2 với hai Session độc lập

Giả sử Product được đánh dấu cacheable và có cache backend được cấu hình:

```java
SessionFactory sf = entityManagerFactory
        .unwrap(SessionFactory.class);
Statistics stats = sf.getStatistics();

// Đây là test cô lập, không chạy clear stats trên production.
stats.clear();

try (Session s1 = sf.openSession()) {
    Product first = s1.find(Product.class, 10L);
    assert first != null;
}

CacheCounters afterFirst = CacheCounters.from(stats);

try (Session s2 = sf.openSession()) {
    Product second = s2.find(Product.class, 10L);
    assert second != null;
}

CacheCounters afterSecond = CacheCounters.from(stats);
CacheCounters secondRead =
        afterSecond.minus(afterFirst);
```

Nếu L2 đã có entry Product #10 từ trước, lần đọc đầu cũng có thể hit. Để đo cold rõ ràng, dùng environment test cô lập hoặc evict entry trước test theo API Cache của phiên bản đang dùng.

Ví dụ JPA Cache:

```java
entityManagerFactory.getCache()
    .evict(Product.class, 10L);
```

Thao tác evict ở đây dành cho **test cô lập**; không evict cache production dùng chung chỉ để đo một request.

Điều mong đợi khi Product được cache đúng và không có thay đổi:

```text
First independent Session:
    L2 miss hoặc bypass do trạng thái test
    DB SELECT
    L2 put nếu cache provider chấp nhận

Second independent Session:
    L2 hit
    không cần SELECT để đọc state Product #10
```

Kết quả cụ thể còn phụ thuộc cache mode, transaction/strategy, provider và cách dữ liệu được nạp.

## 21. Thí nghiệm query cache trong các Session riêng

Một query cacheable:

```java
List<Long> findActiveCategoryIds(Session session) {
    return session.createSelectionQuery("""
        select c.id
        from Category c
        where c.active = true
        order by c.id
        """, Long.class)
        .setCacheable(true)
        .setCacheRegion("active-category-ids")
        .getResultList();
}
```

Trong integration test:

```java
Statistics stats = sessionFactory.getStatistics();
stats.clear();

try (Session first = sessionFactory.openSession()) {
    findActiveCategoryIds(first);
}
CacheCounters afterFirst = CacheCounters.from(stats);

try (Session second = sessionFactory.openSession()) {
    findActiveCategoryIds(second);
}
CacheCounters delta =
    CacheCounters.from(stats).minus(afterFirst);
```

Nếu kết quả query được cache và còn hợp lệ, lần thứ hai có thể tăng query cache hit. Đây là scalar projection giúp cô lập query result caching với entity state loading; nếu query trả entity, cần đo thêm L2 và số SQL hydrate entities.

Không dựa vào thời gian riêng hai lượt rất nhỏ để khẳng định hiệu năng production. Cần lặp nhiều lần, có warm-up, không có logs/bind tracing nặng và so sánh trên workload đại diện.

## 22. Đo SQL statements và round trips bên cạnh cache counters

Các chỉ số Hibernate khác có thể hữu ích:

```java
long preparedStatements =
    stats.getPrepareStatementCount();

long entityLoads =
    stats.getEntityLoadCount();

long entityFetches =
    stats.getEntityFetchCount();

long queryExecutions =
    stats.getQueryExecutionCount();

long collectionFetches =
    stats.getCollectionFetchCount();
```

Ý nghĩa các counter phụ thuộc Hibernate version, loại query và đường load; đừng coi prepared statement count là số network round trips chính xác. JDBC batching, statement reuse và provider behavior có thể làm quan hệ khác nhau.

Để đo chính xác hơn:

- JDBC/data-source instrumentation đếm `executeQuery`, `executeUpdate` và `executeBatch`.
- Database metrics đo statements thực thi, rows scanned, buffer hits, I/O.
- Distributed tracing đo khoảng thời gian JDBC và call graph.
- SQL logs có kiểm soát giúp tìm query N+1, nhưng không nên là metric duy nhất.

Một L2 hit có thể giảm entity fetch SELECT nhưng endpoint vẫn có 20 SQL statements khác. Số SQL tránh được mới giúp giải thích latency.

## 23. Query ExecutionCount không đồng nghĩa query cache miss

Hibernate có các counter cho query execution và query cache. Chúng không nên bị diễn giải như hai mặt của một tổng:

```text
Query A: không bật cacheable
    -> SQL chạy
    -> không có nghĩa tăng query cache miss

Query B: cacheable, chưa có result
    -> query cache miss
    -> có thể chạy SQL, sau đó put

Query C: cacheable, result hợp lệ
    -> query cache hit
    -> có thể tránh query SQL chính
```

Vì vậy, muốn tính **cache coverage**, cần đo bao nhiêu request/query types được cacheable, không chỉ đọc hit/miss counters. Một hệ thống có query cache hit ratio 99% nhưng chỉ 1% query types dùng cache có thể vẫn không giảm DB load đáng kể.

## 24. Chuẩn hóa chi phí truy vấn theo đơn vị công việc

Chỉ số tổng như “giảm từ 10.000 SQL xuống 8.000 SQL” thiếu ngữ cảnh nếu traffic cũng giảm. Nên chuẩn hóa:

```text
SQL statements per request
Database time per request
Cache lookups per request
Cache puts per 1,000 requests
Cache memory bytes per active key
Latency p50/p95/p99 per endpoint
```

Ví dụ:

```text
Trước cache:
  5 SQL statements / product-detail request
  p95 response = 180 ms

Sau cache:
  2 SQL statements / product-detail request
  p95 response = 110 ms
  L2 hit ratio = 75%
```

Các số trên là minh họa cách trình bày, không phải cam kết cải thiện. Trong báo cáo thực, cần kèm khoảng đo, traffic, sample size và môi trường; chỉ khi cùng workload mới có thể quy cải thiện cho cache.

## 25. Đo latency theo phân phối, không chỉ trung bình

Cache có thể cải thiện median nhưng làm tail latency xấu hơn:

- Cold miss cần thêm cache lookup trước DB read.
- Cache backend remote có network timeout.
- Eviction và cache serialization gây GC pause.
- Query cache invalidation đồng thời tạo stampede.
- Mỗi request tải graph lớn sau query cache hit.

Nên đo:

| Chỉ số | Dùng để đánh giá |
|---|---|
| p50 | Trải nghiệm request điển hình |
| p95 | Tác động tới phần chậm của người dùng |
| p99 | Tail latency, timeout và rare cache misses |
| Max/timeout rate | Tính ổn định khi provider/cache backend gặp sự cố |
| DB p95 | Cache có thực sự giảm tải cho DB không? |
| JVM GC pause | Memory overhead có làm tail latency xấu không? |

Một cache có p50 tốt hơn nhưng p99 tăng vượt SLO có thể không đạt yêu cầu sản phẩm.

## 26. Hit ratio phải được hiểu theo tần suất truy cập dữ liệu

Giả sử Product thuộc hai nhóm:

```text
Top 100 products:
    70% tổng số lần đọc

Long-tail 900.000 products:
    30% tổng số lần đọc
```

Nếu cache đủ sức giữ hot keys, hit ratio có thể cao dù phần lớn Product IDs chưa bao giờ được cache. Điều đó có thể rất hiệu quả vì đa số traffic nằm ở hot keys.

Ngược lại, nếu một batch job quét tuần tự từng Product một lần, L2 có thể chỉ ghi hàng loạt puts rồi không tái sử dụng. Một báo cáo hit ratio theo toàn ứng dụng có thể bị batch job làm thấp dù endpoint chính có cache rất tốt.

Nên phân tách:

- Online request vs background batch.
- Read-heavy vs write-heavy features.
- Reference data vs transactional data.
- Tenant lớn vs tenant nhỏ khi hợp lệ.
- Hot key vs scan workload.

Không cố tối ưu hit ratio toàn cục bằng cách cache dữ liệu chỉ được đọc một lần.

## 27. Entity update và cache invalidation

Khi một Product được cập nhật qua Hibernate:

```java
@Transactional
public void renameProduct(long id, String name) {
    Product product = em.find(Product.class, id);
    product.rename(name);
}
```

Hibernate có thể phối hợp L2 state theo concurrency strategy. Tuy nhiên:

- Cùng session vẫn có managed state.
- L2 update/invalidation phụ thuộc provider/strategy.
- Query cache có thể cần vô hiệu hóa cached results liên quan đến table/query spaces bị thay đổi.
- Các writer bên ngoài Hibernate không nhất thiết được Hibernate nhìn thấy.

Do đó cần đo **đọc xen kẽ ghi**, không chỉ benchmark 100% read. Cache có thể cho hit cao khi không có writes, rồi giảm mạnh khi dữ liệu thay đổi thường xuyên.

### 27.1. Bulk HQL và native SQL

```java
em.createQuery("""
    update Product p
    set p.active = false
    where p.discontinued = true
    """).executeUpdate();
```

Bulk mutation không cập nhật từng managed instance đang có trong persistence context. Hibernate có cơ chế xử lý cache/query spaces liên quan, nhưng first-level cache vẫn có thể stale; nên flush/clear hoặc refresh phù hợp.

Với JDBC trực tiếp, SQL ngoài Hibernate hoặc job database khác, các L2/query cache regions có thể không được invalidated theo mong đợi. Cần có chiến lược synchronization, evict, TTL hoặc cơ chế provider/cluster thích hợp.

### 27.2. Dữ liệu cache hit nhưng đã cũ không phải chiến thắng

Nếu cache trả trạng thái Account chưa bị khóa sau khi DB đã khóa, hit cao lại gây lỗi bảo mật/nghiệp vụ. Khi đo, phải xác nhận:

1. Dữ liệu cache còn hợp lệ theo yêu cầu freshness.
2. Update/delete được phản ánh đúng thời điểm.
3. Concurrency strategy tương thích use case.
4. Có xử lý writer ngoài Hibernate.

**Correctness là điều kiện tiên quyết trước performance.**

## 28. Query cache invalidation làm thay đổi lợi ích

Query cache cần biết kết quả có còn hợp lệ sau những thay đổi liên quan. Hibernate dùng thông tin query spaces/timestamps và cơ chế invalidation theo phiên bản để đánh giá cached result.

Một vấn đề thường gặp:

```text
Query: select products where active=true

Timeline:
    T0: query miss -> SQL -> put result
    T1: query hit
    T2: nhiều Product được update
    T3: result có thể bị invalidated
    T4: query miss -> SQL -> put lại
```

Nếu bảng Product thay đổi rất thường xuyên, một query cacheable trên bảng đó có thể bị invalidation nhiều đến mức ít khi tái sử dụng được kết quả.

Khi xem query cache hit/miss/put, nên đặt cạnh:

- Write rate theo tables/entity.
- Query invalidation/region eviction metrics.
- Thời gian giữa các lần put và lần hit tiếp theo.
- Số lượng query keys khác nhau.
- Tỷ lệ parameter reuse.

Không chỉ tăng TTL query cache để tránh miss nếu cách đó làm kết quả stale ngoài policy.

## 29. Query cache và collection N+1

Giả sử endpoint lấy Order rồi truy cập Customer và OrderLines:

```java
List<Order> orders = session.createSelectionQuery("""
    select o
    from Order o
    order by o.id
    """, Order.class)
    .setCacheable(true)
    .getResultList();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
    System.out.println(order.getLines().size());
}
```

Ngay cả khi query Order hit cache, việc truy cập association lazy có thể kích hoạt nhiều SQL. Query cache không tự sửa N+1.

Trước khi bật cache cho màn hình danh sách, xem fetch plan:

- Query chỉ cần vài fields? Dùng DTO projection.
- Luôn cần Customer? Cân nhắc join fetch/entity graph cho to-one.
- OrderLines lớn? Query riêng có phân trang/count, không tải toàn bộ collection.
- Nhiều lazy entities cùng loại? Cân nhắc batch fetching.
- Có thể giải quyết chỉ bằng join/index tốt không?

Một fetch plan đúng thường đem lại lợi ích bền vững hơn cache cố che các truy vấn thừa.

## 30. Phân biệt database buffer cache với Hibernate cache

Một SQL không hit Hibernate L2 vẫn có thể nhanh vì database đã có index/data pages trong buffer cache. Ngược lại, một Hibernate cache hit có thể tiết kiệm network round trip nhưng không làm giảm nhiều DB CPU nếu query ban đầu rất rẻ.

```text
Hibernate L2 / Query cache   <-- bên application
           |
           v
       JDBC / Network
           |
           v
Database buffer/page cache  <-- bên database
           |
           v
      Disk / storage
```

Không nhầm:

- “Hibernate cache miss” với “database đọc từ đĩa”.
- “Database buffer cache hit” với “Hibernate second-level cache hit”.
- “Query SQL chạy” với “query phải I/O vật lý”.

Khi phân tích hiệu năng, xem cả Hibernate cache statistics và DB buffer/IO metrics. Câu hỏi là cache ở tầng ứng dụng có giảm tổng chi phí đủ nhiều để bù độ phức tạp consistency/memory không.

## 31. Chi phí bộ nhớ và serialization

Một L2 entry không miễn phí:

- Object hoặc serialized bytes chiếm RAM/on-heap/off-heap.
- Provider có metadata cho expiry/eviction/version.
- Clustered cache có network/serialization overhead.
- Query cache entries có thể chứa tập kết quả lớn.
- Garbage collection có thể tăng nếu cache dùng heap.

Nếu cache 100.000 entities có average serialized payload lớn, memory pressure có thể vượt lợi ích giảm SELECT. Cần đo cache size/entries, heap usage, GC pause và eviction.

Một chiến lược:

1. Chỉ cache read-mostly entities có reuse.
2. Tránh cache graph/collection rất lớn chỉ vì mapping cho phép.
3. Chọn region capacity theo working set thực.
4. Đo hit ratio sau khi đổi capacity.
5. Theo dõi eviction/expiration để xác định vì sao miss.

Tăng dung lượng cache đến khi hit ratio 100% có thể làm app mất ổn định vì thiếu heap.

## 32. Multi-node và cache topology

Trong ứng dụng có nhiều instances:

```text
Node A                     Node B
SessionFactory A           SessionFactory B
L2 cache A                 L2 cache B
       \                      /
        \                    /
         \-- Shared Database-/
```

Nếu mỗi node có cache local:

- Warm cache của Node A không làm Node B tự warm.
- Update trên Node A cần chiến lược invalidation/consistency đối với Node B.
- Scale-out có thể giảm cache locality và khiến tỷ lệ hit thay đổi.
- Deployment/restart có thể gây cold start đồng loạt.

Với distributed/clustered cache, cần đo thêm network latency, replication/invalidation traffic, serialization và failure modes.

Hai systems cùng hit ratio 90% có thể có latency hoàn toàn khác nhau nếu một cache nằm trong process còn một cache remote qua mạng.

## 33. Cache stampede và thời điểm hết hạn

Một key phổ biến hết hạn, sau đó hàng trăm requests cùng đọc:

```text
Time T: hot cache key expires
        |
        +-- Request 1 -> miss -> DB
        +-- Request 2 -> miss -> DB
        +-- Request 3 -> miss -> DB
        +-- ...
        +-- Request N -> miss -> DB
```

Tình trạng này gọi là *cache stampede*. Các counter có thể cho thấy spike miss/put, nhưng nếu chỉ xem hit ratio trung bình 1 giờ có thể không thấy p99 latency tại thời điểm đó.

Tùy cache provider/architecture, có thể cân nhắc:

- Per-key load coordination/single-flight ở tầng phù hợp.
- Warm-up cho dữ liệu rất nóng trước khi mở traffic.
- Staggered expiry/jitter ở những cache mà ứng dụng quản lý TTL.
- Đảm bảo database vẫn chịu được miss burst.
- Rate limit hoặc graceful degradation cho những read paths không quan trọng.

Không giả định Hibernate L2 hoặc query cache mặc định tự giải quyết mọi dạng stampede. Các cơ chế phụ thuộc provider và topology.

## 34. Stale data, TTL và freshness SLO

Hit ratio cao có thể đi kèm dữ liệu cũ. Vì vậy khi bật cache, cần trả lời:

| Loại dữ liệu | Mức độ chấp nhận stale | Gợi ý cân nhắc |
|---|---|---|
| Danh mục quốc gia ít thay đổi | Có thể dài | READ_ONLY hoặc cache dài với quy trình cập nhật rõ |
| Thông tin mô tả sản phẩm | Có thể chịu delay ngắn tùy nghiệp vụ | L2 READ_WRITE hoặc TTL phù hợp |
| Giá bán đang thay đổi | Thường cần rất chính xác | Quy tắc invalidation/transaction rõ ràng |
| Tồn kho | Thường cần chính xác ở ghi/đặt hàng | Không lấy cache làm nguồn quyết định cuối |
| Quyền truy cập, khóa tài khoản | Nhạy cảm với stale state | Cơ chế đồng bộ nghiêm ngặt hoặc tránh cache không phù hợp |

TTL không thay thế transaction isolation hay version checks. Cache strategy phải phù hợp business correctness; nếu không thể đảm bảo, nên không cache loại dữ liệu đó.

## 35. Đo cache trong môi trường production

Nếu hệ thống dùng Micrometer/Prometheus hoặc một hệ metrics khác, có thể xuất counters:

```text
hibernate_l2_hits_total
hibernate_l2_misses_total
hibernate_l2_puts_total

hibernate_query_cache_hits_total
hibernate_query_cache_misses_total
hibernate_query_cache_puts_total
```

Đây là **tên metric minh họa**, không phải tên mặc định được mọi phiên bản Hibernate/Micrometer cung cấp. Khi triển khai, dùng tên metric thật từ instrumentation và tránh đăng ký trùng counters.

Nên gắn labels có cardinality thấp:

- Service/instance.
- Cache type.
- Region nếu số region hữu hạn.
- Environment.

Không tạo label theo entity ID, user ID hoặc raw query parameter: sẽ gây cardinality explosion và có thể lộ dữ liệu nhạy cảm.

### 35.1. Alert theo chi phí, không chỉ hit ratio

Ví dụ các tín hiệu phối hợp:

- L2 hit ratio tụt đột ngột **và** DB SELECT QPS tăng.
- Query cache miss/put tăng **và** p95 latency tăng.
- Evictions tăng **và** heap/GC pressure cao.
- Cache backend timeout **và** DB read latency tăng.
- Cache hit tốt nhưng API p99 xấu do một query không cache.

Đây là hướng thiết kế alert, không có threshold chung áp dụng cho mọi ứng dụng.

## 36. Một mẫu báo cáo trước/sau khi bật cache

| Metric | Trước cache | Sau cache (cold) | Sau cache (warm) | Kết luận |
|---|---:|---:|---:|---|
| Requests/giây | Đo | Đo | Đo | Cùng mức tải? |
| L2 hits/misses/puts | Không áp dụng | Đo | Đo | Cache lookup pattern |
| Query hits/misses/puts | Không áp dụng | Đo | Đo | Query reuse |
| JDBC SQL/request | Đo | Đo | Đo | SQL giảm bao nhiêu? |
| DB time/request | Đo | Đo | Đo | Giảm chi phí DB? |
| API p50/p95/p99 | Đo | Đo | Đo | Người dùng được lợi? |
| DB CPU/IO | Đo | Đo | Đo | DB load giảm? |
| JVM heap/GC | Đo | Đo | Đo | Cache tốn memory bao nhiêu? |
| Cache evictions | Không áp dụng | Đo | Đo | Capacity phù hợp? |
| Correctness/freshness | Xác nhận | Xác nhận | Xác nhận | Không chấp nhận stale ngoài policy |

Không nên chỉ báo cáo hit ratio. Một kết quả tốt cần có SQL giảm, latency cải thiện hoặc DB cost giảm **trong khi correctness vẫn đạt**.

## 37. Test trường hợp cache bị cập nhật

Một integration test nên:

1. Tạo Product và commit.
2. Từ Session A, đọc Product #10 để warm L2.
3. Từ Session B, đọc lại và quan sát hit.
4. Trong transaction khác, cập nhật Product #10 và commit.
5. Từ Session C mới, đọc lại và assert state mới theo concurrency strategy.
6. Ghi thống kê SQL/L2 hit/miss/put để hiểu invalidation path.

Đừng giữ Session A từ đầu đến cuối rồi expect thấy state mới: first-level cache vẫn có identity map và có thể giữ state cũ theo transaction isolation.

Ví dụ khung test:

```java
@Test
void cacheDoesNotHideCommittedProductUpdate() {
    // prepareProductAndCommit(productId, "Old");
    //
    // inNewSession(() -> load(productId));
    // inNewSession(() -> load(productId)); // warm L2
    //
    // inNewTransaction(() -> rename(productId, "New"));
    //
    // String observed = inNewSession(
    //     () -> load(productId).getName());
    // assertEquals("New", observed);
}
```

Đây là skeleton thiết kế test; các helper và transaction boundary phải được hiện thực thực tế. Với distributed cache, cần test đọc/ghi giữa các nodes.

## 38. Test query cache invalidation

Giả sử cacheable query:

```hql
select p.id
from Product p
where p.active = true
order by p.id
```

Kịch bản:

1. Query từ Session A để cache danh sách.
2. Query từ Session B để xác nhận reuse.
3. Update một Product `active=true` thành `active=false` và commit.
4. Query từ Session C với cùng parameters.
5. Assert Product đã tắt không còn xuất hiện trong kết quả.

Thử cả:

- Update qua Hibernate managed entity.
- Bulk HQL mutation.
- Native SQL/JDBC/out-of-band writer nếu kiến trúc có sử dụng.

Các đường ghi ngoài Hibernate có thể cần explicit invalidation hoặc không được phép sửa dữ liệu mà cache đang phụ thuộc. Nếu hệ thống có out-of-band writes, đó là một phần của cache consistency design.

## 39. Test region capacity và eviction

Một cache provider có giới hạn entries/memory. Khi working set vượt giới hạn:

```text
Read key 1 --> put
Read key 2 --> put
...
Read key N --> cache full
Read key N+1 --> eviction một hoặc nhiều entries
Read key 1 again --> có thể miss
```

Để đánh giá:

- Chạy workload với working set nhỏ hơn, gần bằng và lớn hơn capacity.
- Đo hit/miss/put và eviction metrics.
- Đo heap/off-heap và GC.
- Đo latency ở cold/warm và khi cache pressure.
- Xác nhận provider eviction policy đang hoạt động như cấu hình.

Không tự động tăng cache capacity khi eviction tăng: nếu keys ít reuse, tăng RAM cũng có thể không cải thiện nhiều.

## 40. Thử nghiệm A/B hoặc canary khi bật cache

Trong hệ thống có lưu lượng lớn, bật L2/query cache cho toàn bộ nodes một lúc có thể gây:

- Cold start spike.
- Memory pressure.
- Thay đổi p99 latency.
- Cache consistency issue ở multi-node.
- Invalidation load bất ngờ.

Có thể dùng canary:

```text
Baseline group: cache configuration hiện tại
Canary group:   cache configuration mới
               cùng workload tương đương
                     |
                     v
        Compare request latency, DB QPS,
        error rate, cache metrics, memory
                     |
                     v
            Rollout / rollback decision
```

Canary chỉ có ý nghĩa nếu traffic allocation và data locality tương đương. Một node canary ít request hoặc có tỷ lệ hot keys khác baseline có thể tạo kết luận sai.

## 41. Những lỗi đo cache thường gặp

| Hiện tượng | Vì sao sai hoặc chưa đủ | Cách xử lý |
|---|---|---|
| Gọi find lặp trong cùng Session rồi coi là L2 hit | First-level cache phục vụ dữ liệu | Dùng sessions độc lập khi đo L2 |
| Cache hit ratio = 100% vì hits=0, misses=0 | Không có lookup | Báo N/A, kiểm tra cache thực sự được dùng |
| Cộng query hits và L2 hits | Hai loại lookup khác nhau | Báo metric riêng |
| Dùng puts làm mẫu số hit ratio | Put không phải lookup | Hits/(hits+misses) |
| SQL giảm nhưng API không nhanh | Bottleneck ở nơi khác | Đo latency end-to-end và DB time |
| Query cache hit mà vẫn còn SQL | Entity hydrate/lazy associations hoặc query khác | Xem SQL trace, L2 và fetch plan |
| Query cache miss thấp nhưng DB QPS cao | Query không cacheable vẫn chạy DB | Đo cache coverage |
| Cache có nhiều puts, ít hits | Churn hoặc cold scan | Xem reuse, TTL, capacity |
| Hit cao nhưng trả dữ liệu sai | Stale cache/invalidation | Kiểm thử read-after-write correctness |
| Statistics reset giữa traffic production | Counter bị xóa, nhiễu báo cáo | Snapshot delta theo thời gian |
| Có Hibernate stats nhưng không thấy evictions | Eviction ở cache provider | Thu thêm provider metrics |
| Dùng H2 benchmark thay DB đích | SQL/optimizer khác | Đo trên DBMS/version mục tiêu |
| Benchmark chỉ một lần | JIT/cache/warm-up bias | Nhiều lượt, phân phối latency |
| Query cache mọi search query | Key cardinality cao, invalidation | Cache use case có reuse thật |
| Tăng TTL để có hit cao | Có thể vi phạm freshness | Tôn trọng correctness policy |
| Cache đối tượng rất lớn | Memory/GC/serialization overhead | Giới hạn region và chỉ cache dữ liệu hot |
| Thiếu tenant isolation | Cached result có thể lộ dữ liệu | Kiểm thử tenant keys/filter/RLS |

## 42. Quy trình tối ưu dựa trên bằng chứng

**Bước 1 — Chọn use case rõ ràng.** Ví dụ Product detail, category lookup hoặc top-selling products; tránh bắt đầu từ “bật cache toàn bộ”.

**Bước 2 — Xác định access pattern.** Đọc theo ID hay query? Có repeated keys? Read/write ratio? Dữ liệu lớn? Freshness yêu cầu bao nhiêu?

**Bước 3 — Chọn đúng loại cache.** L2 entity/collection cho access theo identity; query cache khi query keys lặp lại và invalidation có thể kiểm soát.

**Bước 4 — Cấu hình provider/region.** Concurrency strategy, TTL, capacity, eviction, topology multi-node và monitoring.

**Bước 5 — Đo baseline.** SQL/request, DB time, API p50/p95/p99, heap/GC, CPU, error rate.

**Bước 6 — Đo cold và warm.** Dùng Sessions độc lập để không nhầm first-level với L2; query cache có riêng hit/miss/put.

**Bước 7 — Phân tích region.** Đọc hit/miss/put theo thời gian, puts/evictions và chi phí reload. Phân biệt cache coverage với miss ratio.

**Bước 8 — Đo tác động hệ thống.** Số SQL/round trips tránh được, DB CPU/IO, JVM memory/GC, lock và tail latency.

**Bước 9 — Kiểm chứng consistency.** Test update/delete, bulk mutation, out-of-band writes, tenant isolation và distributed-cache behavior.

**Bước 10 — Ra quyết định.** Giữ cache nếu lợi ích latency/DB cost đáng kể và correctness/overhead đạt SLO; nếu không, thu hẹp region, chỉnh policy hoặc tắt cache.

## 43. Sơ đồ lựa chọn và diễn giải

```text
                Request chậm / DB load cao
                           |
                           v
             Có query hoặc entity read lặp lại?
                    /              \
                  KHÔNG             CÓ
                   |                 |
                   v                 v
             Tối ưu SQL/fetch    Truy cập theo ID?
             /index trước         /          \
                                CÓ           KHÔNG
                                |              |
                                v              v
                           Thử L2 cache    Query keys lặp?
                                               /      \
                                             CÓ      KHÔNG
                                              |         |
                                              v         v
                                      Thử query cache  Tối ưu query
                                              |         /fetch plan
                                              |
                         +--------------------+
                         |
                         v
                  Đo hit / miss / put
                         |
                         v
                Đo SQL + latency + memory
                         |
                         v
                Kiểm tra stale/read-after-write
                         |
                         v
                 Lợi ích > chi phí và rủi ro?
                    /              \
                  CÓ               KHÔNG
                   |                 |
                   v                 v
                Rollout       Sửa policy / bỏ cache
```

## 44. Tổng kết

Đo bộ nhớ đệm trong Hibernate cần bắt đầu từ **đúng tầng cache**. First-level cache thuộc một Session và có thể khiến test tưởng L2 đã hit. Second-level cache giúp tái sử dụng state entity/collection giữa các Sessions. Query cache chỉ áp dụng cho các query được đánh dấu cacheable và có cơ chế query key/invalidation riêng.

Ba counter chính là **hit**, **miss**, **put**. Hit và miss cho phép tính hit ratio của một loại cache trong một khoảng quan sát; put cho biết hoạt động đưa dữ liệu vào cache và không phải thành phần của mẫu số hit ratio. Đọc riêng L2 và query cache, sau đó phân tích theo region và theo traffic pattern. Hit ratio cao không đồng nghĩa latency thấp, cũng không đảm bảo dữ liệu còn đúng.

Một đánh giá có giá trị phải so sánh **baseline, cold cache và warm cache** trên cùng DBMS/workload, dùng nhiều Sessions để loại trừ first-level effects, đo SQL/request, DB time, p50/p95/p99, CPU, heap/GC và cache-provider evictions. Sau đó kiểm tra update, delete, bulk HQL/JDBC, multi-node consistency và tenant isolation.

**Mục tiêu không phải đạt 100% hit ratio, mà là giảm chi phí truy vấn và cải thiện trải nghiệm người dùng mà vẫn bảo toàn tính đúng đắn của dữ liệu.** Chỉ giữ cache khi có bằng chứng rõ rằng lợi ích lớn hơn chi phí về bộ nhớ, invalidation, độ phức tạp và rủi ro vận hành.
