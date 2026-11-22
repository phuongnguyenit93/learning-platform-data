# Đo hit, miss và kiểm thử tính đúng đắn khi bật cache

Khi bật cache cho ứng dụng Spring Data JPA, chỉ thấy response nhanh hơn ở một vài lần gọi chưa đủ để kết luận cache hoạt động đúng. Cần đo số lần cache hit và miss, xác định phần truy vấn database được tránh, theo dõi eviction/expiration và kiểm thử dữ liệu vẫn chính xác sau khi tạo, sửa, xóa hoặc rollback.

Spring có nhiều lớp cache khác nhau. Spring Cache thường cache kết quả của một phương thức ở tầng ứng dụng; JPA persistence context, JPA second-level cache và Hibernate query cache lại có vòng đời và phạm vi khác. Trước khi đo, hãy xác định đang đo cache nào và thao tác nào thực sự đi qua cache đó.

## 1. Phân biệt các lớp cache trong ứng dụng JPA

Một ứng dụng Spring Data JPA có thể có nhiều lớp cache:

| Loại cache | Phạm vi | Dữ liệu thường giữ | Cách quan sát |
|---|---|---|---|
| Persistence context (first-level cache) | Một EntityManager/transaction context | Entity đã được load hoặc quản lý | Theo dõi SQL và trạng thái EntityManager |
| JPA second-level cache | Chia sẻ giữa các EntityManager trong persistence unit | Entity/collection được provider cache | Hibernate/JPA provider statistics |
| Hibernate query cache | Theo cấu hình Hibernate | Kết quả truy vấn và thông tin đồng bộ vùng cache | Hibernate statistics/metrics |
| Spring Cache abstraction | Theo CacheManager và cache name | Kết quả method, DTO hoặc giá trị ứng dụng | Micrometer/provider cache statistics |

Một lần đọc Entity lần thứ hai trong cùng persistence context có thể không phát SQL dù Spring Cache không có hit. Ngược lại, một lần gọi method được cache có thể hit Spring Cache và bỏ qua hoàn toàn Repository method.

Vì vậy, không dùng một con số hit/miss để đại diện cho tất cả các lớp cache. Hãy đặt tên metric và dashboard theo đúng cache layer.

## 2. Hit và miss có nghĩa gì?

Với Spring Cache, một lần truy cập cache thường có hai kết quả:

- **Hit:** cache tìm thấy entry hợp lệ cho key; phương thức được đánh dấu cacheable không cần chạy phần thân.
- **Miss:** cache không có entry cho key; phương thức chạy, lấy dữ liệu nguồn và kết quả có thể được lưu vào cache.

Ví dụ:

~~~java
@Service
public class ProductQueryService {

    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#id")
    public Optional<ProductDto> findById(Long id) {
        return repository.findById(id)
                .map(ProductDto::from);
    }
}
~~~

Với cùng một ID và entry chưa hết hạn:

1. Lần gọi đầu: cache miss, method chạy và đọc Repository.
2. Lần gọi sau: cache hit, method body được bỏ qua.
3. Khi entry bị evict hoặc expire: lần gọi kế tiếp miss và đọc lại dữ liệu nguồn.

Đây là cache-aside ở mức method. Cache không tự biết dữ liệu trong database đã thay đổi bởi batch job, SQL trực tiếp hoặc một ứng dụng khác. Ứng dụng cần chiến lược invalidation/expiration phù hợp.

## 3. Tính hit ratio và miss ratio

Nếu cache provider cung cấp số lần hit và miss trong cùng một khoảng đo:

~~~text
totalGets = hits + misses
hitRatio  = hits / totalGets
missRatio = misses / totalGets
~~~

Ví dụ:

| Chỉ số | Giá trị |
|---|---:|
| Hits | 8.000 |
| Misses | 2.000 |
| Total gets | 10.000 |
| Hit ratio | 80% |
| Miss ratio | 20% |

Hit ratio 80% nghĩa là 8 trên 10 lần lấy cache tìm được entry. Nó không có nghĩa 80% request được phục vụ nhanh hơn, vì một request có thể gọi cache nhiều lần hoặc không gọi cache.

Nếu totalGets bằng 0, hit ratio không xác định; không chia cho 0 hoặc hiển thị 0% như thể đã có traffic. Hãy hiển thị “no samples” hoặc bỏ qua khoảng đo đó.

Đo theo cửa sổ thời gian cũng cần cẩn thận. Bộ đếm provider thường là cumulative từ lúc cache được tạo hoặc statistics được reset. Để tính tỷ lệ trong một khoảng, lấy delta hits và delta misses trong chính khoảng đó, không trộn tổng số tích lũy của những khoảng khác nhau.

## 4. Những metric nên theo dõi

Hit/miss chỉ là một phần của chất lượng cache. Nên theo dõi thêm:

| Metric | Câu hỏi cần trả lời |
|---|---|
| Gets / lookups | Cache được truy cập bao nhiêu lần? |
| Hits | Bao nhiêu lần tìm thấy entry? |
| Misses | Bao nhiêu lần phải chạy nguồn dữ liệu? |
| Hit ratio | Tỷ lệ truy cập được cache đáp ứng là bao nhiêu? |
| Puts / loads | Có bao nhiêu entry được thêm hoặc nạp? |
| Evictions | Bao nhiêu entry bị loại do chính sách dung lượng? |
| Expirations | Bao nhiêu entry hết TTL? |
| Size / estimated size | Cache đang giữ khoảng bao nhiêu entry? |
| Load duration | Khi miss, lấy dữ liệu nguồn mất bao lâu? |
| DB query count/latency | Cache có giảm tải database thực tế không? |
| Memory/heap | Cache tiêu thụ bao nhiêu bộ nhớ? |
| Error rate | Cache backend có lỗi hoặc timeout không? |

Tên metric và khả năng cung cấp phụ thuộc cache implementation. Không phải mọi provider đều có counter eviction, expiration, load time hoặc size.

Hit ratio cao nhưng database vẫn chậm có thể do cache chỉ bao phủ một phần query tốn kém, miss rất đắt, cache hit không tránh các truy vấn khác trong request, serialization/network cache tốn thời gian hoặc cache làm tăng GC và memory pressure.

Đánh giá hiệu quả bằng cả latency, database load, memory và tính đúng đắn.

## 5. Đo cache bằng Micrometer và Spring Boot Actuator

Spring Boot Actuator tích hợp Micrometer để xuất metric của những cache mà implementation/registry hỗ trợ. Với cache được instrument, các metric Spring/Micrometer thường gặp gồm:

- cache.gets: số lần lấy cache, thường có tag result để phân biệt hit và miss.
- cache.puts: số lần ghi entry.
- cache.evictions: số lần eviction.
- cache.size: kích thước ước tính nếu provider hỗ trợ.

Metric thực tế phụ thuộc CacheManager, cache implementation, binder và phiên bản thư viện. Một số cache chỉ hỗ trợ một phần thống kê; cache không expose native statistics có thể không có hit/miss hoặc size. Hãy kiểm tra meter thực tế thay vì giả định mọi cache đều xuất đủ metric.

Ví dụ dependency Maven cho Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Cấu hình expose endpoint cần thiết trong môi trường phù hợp:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Không expose endpoint quản trị/metrics ra Internet công khai nếu chưa có xác thực và giới hạn quyền. Cấu hình endpoint phải theo chính sách vận hành của ứng dụng.

Khi Actuator metrics endpoint được bật, có thể kiểm tra metric cache qua endpoint metrics, ví dụ:

~~~text
/actuator/metrics/cache.gets
~~~

Kết quả có thể chứa các tag như cache name và result. Cú pháp query/tag cụ thể phụ thuộc phiên bản Boot/Micrometer. Nếu dùng Prometheus registry, tên metric được chuyển đổi theo quy tắc Prometheus; hãy kiểm tra endpoint Prometheus để xem tên và label thực tế.

## 6. Bật statistics của cache provider

Spring Cache là abstraction; bản thân annotation cacheable không bảo đảm mọi provider tự ghi hit/miss. Cần bật statistics theo cách của provider.

### Caffeine

Với Caffeine, bật thống kê bằng recordStats():

~~~java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("products");

    manager.setCaffeine(
            Caffeine.newBuilder()
                    .maximumSize(10_000)
                    .expireAfterWrite(Duration.ofMinutes(10))
                    .recordStats()
    );

    return manager;
}
~~~

Sau khi bật, native cache có thể cung cấp CacheStats:

~~~java
CaffeineCache springCache =
        (CaffeineCache) cacheManager.getCache("products");

com.github.benmanes.caffeine.cache.Cache<Object, Object> nativeCache =
        springCache.getNativeCache();

CacheStats stats = nativeCache.stats();

long hits = stats.hitCount();
long misses = stats.missCount();
double hitRate = stats.hitRate();
~~~

Đoạn code dùng Caffeine và Spring's CaffeineCache; cần có dependency tương ứng. Nếu không bật recordStats(), các số liệu hit/miss native có thể không được ghi nhận như mong đợi.

### ConcurrentMapCache

ConcurrentMapCache phù hợp cho demo hoặc ứng dụng đơn giản, nhưng không phải cache production có đầy đủ chính sách TTL/size và thống kê. Đừng giả định nó cung cấp native hit/miss counters giống Caffeine.

### JCache, Ehcache và provider khác

JCache có API quản lý statistics nhưng cần bật statistics trên cache configuration theo provider. Ehcache, Hazelcast, Redis và các implementation khác có cách expose metric riêng. Một số metric cần binder hoặc integration bổ sung.

Quy trình chung:
1. Xác định CacheManager và loại cache đang chạy.
2. Bật stats theo tài liệu provider.
3. Kiểm tra cache instance có native stats hay không.
4. Đăng ký/bật Micrometer binder nếu cần.
5. Tạo hit và miss có kiểm soát.
6. Đọc metric và xác nhận counter thay đổi đúng.

## 7. Phân biệt hit/miss của Spring Cache với Hibernate L2 cache

Nếu ứng dụng bật Hibernate second-level cache, cần đo riêng các chỉ số như:
- Second-level cache hit count.
- Second-level cache miss count.
- Second-level cache put count.
- Query cache hit/miss/put count nếu query cache được bật.

Hibernate statistics có thể được bật qua cấu hình provider, ví dụ:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Sau đó có thể truy cập SessionFactory statistics trong cấu hình Hibernate phù hợp:

~~~java
Statistics statistics = sessionFactory.getStatistics();

long hits = statistics.getSecondLevelCacheHitCount();
long misses = statistics.getSecondLevelCacheMissCount();
long puts = statistics.getSecondLevelCachePutCount();
~~~

Tên API và package có thể khác theo phiên bản Hibernate. Bật statistics có thể tạo thêm overhead; chỉ bật ở môi trường cần quan sát và kiểm tra chi phí.

Một lần Spring Cache hit có thể khiến Repository không được gọi, nên Hibernate L2 cache không ghi nhận lần lookup đó. Ngược lại, một lần Repository chạy có thể được Hibernate L2 cache đáp ứng mà không đọc database. Hãy dashboard riêng cho từng layer.

## 8. Kiểm thử cơ bản: lần đầu miss, lần sau hit

Một kiểm thử tốt cần chứng minh hành vi quan sát được, không chỉ kiểm tra annotation tồn tại.

Có thể kiểm tra bằng một dependency mock hoặc spy:
- Gọi method với key chưa có.
- Xác nhận Repository được gọi một lần.
- Gọi lại cùng key.
- Xác nhận Repository không bị gọi thêm.
- Gọi với key khác.
- Xác nhận nguồn dữ liệu được gọi cho key mới.

Ví dụ minh họa với Mockito và Spring test context:

~~~java
@SpringBootTest
class ProductQueryCacheTest {

    @Autowired
    private ProductQueryService service;

    @Autowired
    private CacheManager cacheManager;

    @MockBean
    private ProductRepository repository;

    @BeforeEach
    void clearCache() {
        cacheManager.getCache("products").clear();
    }

    @Test
    void secondCallForSameKeyUsesCache() {
        Product product = new Product(10L, "Keyboard");

        when(repository.findById(10L))
                .thenReturn(Optional.of(product));

        Optional<ProductDto> first = service.findById(10L);
        Optional<ProductDto> second = service.findById(10L);

        assertEquals(first, second);
        verify(repository, times(1)).findById(10L);
    }
}
~~~

Ví dụ cần cấu hình EnableCaching, bean ProductQueryService, ProductRepository và cache tên products. Annotation MockBean có thể được thay bằng cơ chế mock bean tương ứng của phiên bản Spring Boot đang dùng. Nếu method trả DTO, DTO cần equals/hashCode phù hợp để so sánh trong test.

Test này xác nhận cùng key chỉ gọi Repository một lần trong phạm vi cache hiện tại. Nó chưa chứng minh invalidation, TTL, concurrency hoặc metrics được instrument đúng.

## 9. Kiểm thử eviction sau khi cập nhật

Cache chỉ đúng nếu dữ liệu cũ được loại bỏ hoặc cập nhật khi nguồn thay đổi.

Ví dụ:

~~~java
@Service
public class ProductCommandService {

    private final ProductRepository repository;

    public ProductCommandService(ProductRepository repository) {
        this.repository = repository;
    }

    @CacheEvict(cacheNames = "products", key = "#id")
    public void rename(Long id, String newName) {
        Product product = repository.findById(id)
                .orElseThrow();

        product.rename(newName);
    }
}
~~~

Sau khi gọi rename(), lần đọc tiếp theo cùng ID phải lấy dữ liệu mới từ nguồn và cache lại kết quả mới.

Một test cần:
1. Đọc product lần đầu để tạo cache entry.
2. Gọi command cập nhật.
3. Gọi query lại cùng key.
4. Xác nhận Repository trả dữ liệu mới.
5. Xác nhận không còn giá trị cũ trong cache.

Mặc định CacheEvict xóa entry sau khi method invocation thành công; beforeInvocation = true xóa trước khi method chạy. Nếu cập nhật database thất bại và transaction rollback, việc eviction trước khi transaction kết thúc có thể gây cache miss thừa hoặc tạo race. Hãy chọn thời điểm eviction theo transaction semantics và yêu cầu nhất quán.

## 10. CachePut và CacheEvict khác nhau

| Annotation | Hành vi |
|---|---|
| Cacheable | Kiểm tra cache trước; hit thì bỏ qua method, miss thì chạy và lưu kết quả |
| CachePut | Luôn chạy method rồi ghi kết quả vào cache |
| CacheEvict | Xóa một entry hoặc toàn bộ cache |
| Caching | Kết hợp nhiều thao tác cache trên cùng method |

Ví dụ dùng CachePut:

~~~java
@CachePut(cacheNames = "products", key = "#result.id")
public ProductDto update(ProductCommand command) {
    Product saved = repository.update(command);
    return ProductDto.from(saved);
}
~~~

CachePut phù hợp khi method luôn phải chạy và kết quả mới được đưa vào cache. Không đặt Cacheable và CachePut trên cùng method một cách tùy tiện vì semantics có thể xung đột; hãy dùng các method riêng và kiểm thử rõ.

Với xóa toàn bộ cache:

~~~java
@CacheEvict(cacheNames = "products", allEntries = true)
public void rebuildProductCatalog() {
    // Rebuild catalog.
}
~~~

Evict toàn bộ có thể tạo nhiều miss đồng thời sau đó. Nếu cache lớn hoặc traffic cao, hãy cân nhắc chiến lược refresh/warm-up và tránh tạo thundering herd.

## 11. Kiểm thử đúng đắn khi transaction rollback

Một tình huống quan trọng: method cập nhật cache chạy bên trong transaction database nhưng transaction sau đó rollback.

Nếu cache đã bị cập nhật/xóa trước khi database commit, cache có thể không còn phản ánh dữ liệu thực tế. Một cách xử lý là dùng transaction-aware cache để trì hoãn các thao tác put/evict/clear cho đến khi transaction commit thành công.

Ví dụ bọc CacheManager:

~~~java
@Bean
CacheManager transactionAwareCacheManager(CacheManager delegate) {
    return new TransactionAwareCacheManagerProxy(delegate);
}
~~~

Transaction-aware decorator có thể trì hoãn các thao tác ghi cache được hỗ trợ cho đến sau commit. Khi transaction rollback, các thao tác cache đang chờ không được thực hiện.

Điều này không biến database và Redis/Caffeine thành một distributed transaction. Cache vẫn là hệ thống riêng và vẫn có thể gặp lỗi sau commit, eviction không thành công hoặc race giữa các node. Hãy thiết kế TTL, retry và cơ chế đồng bộ phù hợp.

Để kiểm thử:
1. Tạo entry cache ban đầu.
2. Bắt đầu transaction cập nhật dữ liệu và cache.
3. Cố ý ném exception làm rollback.
4. Đọc lại database và cache.
5. Xác nhận cache không chứa giá trị chưa commit.

Không dùng Transactional trên chính test theo cách khiến transaction ngoài của test che khuất ranh giới transaction cần kiểm tra. Có thể gọi service transactional từ test không có transaction bao ngoài rồi đọc lại bằng transaction mới.

## 12. Kiểm thử TTL và eviction theo dung lượng

Cache entry có thể hết hạn theo TTL hoặc bị loại khi vượt giới hạn dung lượng.

Ví dụ Caffeine:

~~~java
Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(Duration.ofMinutes(5))
        .recordStats()
        .build();
~~~

Kiểm thử TTL bằng cách chờ đúng thời gian thực thường làm test chậm và không ổn định. Caffeine hỗ trợ ticker có thể điều khiển trong test để tăng thời gian logic mà không phải sleep. Với provider khác, dùng clock/timer test hook nếu có.

Nên kiểm tra:
- Entry tồn tại trước TTL.
- Entry không còn được trả sau khi TTL hết.
- Eviction theo maximumSize khi cache vượt dung lượng.
- Metric eviction/expiration tăng đúng theo provider.
- Cache không giữ dữ liệu vô hạn khi key cardinality tăng liên tục.

Không assert rằng eviction xảy ra ngay lập tức nếu provider dùng maintenance hoặc eviction policy bất đồng bộ. Hãy dùng API test/maintenance phù hợp với provider.

## 13. Cache key phải đại diện đầy đủ cho kết quả

Một cache key sai có thể làm dữ liệu của request này được trả cho request khác.

Ví dụ kết quả phụ thuộc cả product ID và tenant ID:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#tenantId + ':' + #productId"
)
public ProductDto findForTenant(Long tenantId, Long productId) {
    return repository.findForTenant(tenantId, productId)
            .map(ProductDto::from)
            .orElseThrow();
}
~~~

Nếu chỉ dùng productId trong khi cùng ID có thể tồn tại ở nhiều tenant, cache có thể trả dữ liệu sai tenant.

Key cũng có thể cần chứa:
- Locale nếu kết quả đã được dịch.
- Currency nếu giá được chuyển đổi.
- Role/permission nếu kết quả đã lọc theo quyền.
- Version hoặc filter parameters nếu kết quả phụ thuộc chúng.
- Các tham số phân trang/sắp xếp nếu cache cả trang kết quả.

Không đưa dữ liệu nhạy cảm vào key nếu key có thể bị lộ trong metrics/log. Dùng key ổn định, có giới hạn cardinality và tránh chuỗi tùy ý rất dài.

## 14. Cache null, Optional và kết quả không tìm thấy

Cache behavior với null/Optional phụ thuộc Spring Cache version và provider. Cần xác định rõ có cache kết quả không tìm thấy hay không.

Nếu cache cả negative lookup:
- Giảm truy vấn lặp cho ID không tồn tại.
- Nhưng một Entity vừa được tạo có thể vẫn bị che bởi negative entry cũ cho đến khi eviction/TTL.
- TTL cho negative result thường nên ngắn hơn dữ liệu ổn định nếu nghiệp vụ yêu cầu.

Có thể dùng điều kiện unless để ngăn cache kết quả không mong muốn. Với Optional, Spring Cache có cơ chế unwrap trong các phiên bản hiện hành; hãy xác minh chính xác giá trị được đưa vào biểu thức unless theo phiên bản dự án. Một điều kiện thường dùng để tránh cache kết quả null là:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#id",
    unless = "#result == null"
)
public ProductDto findById(Long id) {
    return repository.findDtoById(id).orElse(null);
}
~~~

Ví dụ trên dùng kiểu trả về ProductDto có thể null để làm rõ semantics. Nếu method trả Optional, hãy viết test cho trường hợp Optional.empty() và kiểm tra cache provider lưu hay bỏ qua kết quả đó như mong muốn.

Nếu không muốn cache kết quả vắng mặt, cấu hình điều kiện rõ ràng. Nếu muốn cache negative result, đặt TTL và invalidation phù hợp khi Entity mới được tạo.

## 15. Cache stampede và tải đồng thời

Khi một key hết hạn hoặc bị evict, nhiều request đồng thời có thể cùng miss và cùng truy vấn database. Hiện tượng này thường gọi là cache stampede hoặc thundering herd.

Một số cách giảm rủi ro:
- Dùng cơ chế đồng bộ load theo key nếu provider hỗ trợ.
- Dùng Cacheable(sync = true) khi semantics và provider phù hợp.
- Warm-up các key quan trọng có kiểm soát.
- Dùng TTL có jitter để tránh nhiều key hết hạn cùng thời điểm.
- Giới hạn concurrency của các tác vụ load nặng.
- Dùng stale-while-revalidate nếu nghiệp vụ cho phép trả dữ liệu cũ trong thời gian refresh.
- Bảo vệ database bằng timeout, rate limit và bulkhead.

sync = true có giới hạn theo cache provider và không phải distributed lock toàn hệ thống. Với nhiều application instance, cần hiểu cơ chế đồng bộ của backend cache.

Kiểm thử concurrency bằng nhiều thread cùng truy cập một key chưa có; đếm số lần nguồn dữ liệu được gọi và xác nhận kết quả không bị ghi sai. Không chỉ test tuần tự rồi suy luận concurrency an toàn.

## 16. Cache nhiều instance và invalidation

Với một ứng dụng chạy nhiều instance:
- Local Caffeine cache của mỗi instance là độc lập.
- Một instance evict không tự động xóa entry trên instance khác.
- Hai instance có thể trả dữ liệu khác nhau trong khoảng thời gian khác nhau.
- Restart một instance có thể làm cache local mất toàn bộ entry.

Redis hoặc distributed cache có thể chia sẻ entry giữa các instance, nhưng invalidation và consistency vẫn cần thiết kế. Nếu nhiều ứng dụng cùng ghi database, mọi writer phải phát tín hiệu invalidation hoặc dùng TTL/freshness policy đủ phù hợp.

Một chiến lược phổ biến là phát domain event/outbox sau khi commit, để các instance hoặc cache service evict key liên quan. Message có thể bị giao trùng hoặc trễ; consumer nên idempotent.

Không giả định CacheEvict trên local cache đồng bộ toàn cluster. Hãy xác định CacheManager đang dùng và cơ chế broadcast thực tế.

## 17. Kiểm thử không phụ thuộc thứ tự test

Cache là trạng thái chia sẻ giữa các test trong cùng ApplicationContext. Nếu test không xóa cache, kết quả có thể phụ thuộc thứ tự chạy.

Thực hành:
- Xóa đúng cache trước mỗi test bằng CacheManager.
- Dùng key riêng cho từng test.
- Không phụ thuộc vào cache còn sót từ test trước.
- Không dùng Thread.sleep() dài để chờ TTL nếu provider có test clock.
- Kiểm tra nguồn dữ liệu được gọi bao nhiêu lần.
- Tắt hoặc cấu hình cache rõ ràng cho test cần đo hành vi không cache.
- Với integration test transaction, hiểu rõ test transaction và transaction service.

Ví dụ helper:

~~~java
@BeforeEach
void clearProductCache() {
    Cache cache = cacheManager.getCache("products");
    if (cache != null) {
        cache.clear();
    }
}
~~~

Không dùng CacheManager.getCacheNames() rồi xóa mọi cache nếu test chỉ sở hữu một cache; xóa đúng cache giúp tránh tác động đến test fixture khác trong context dùng chung.

## 18. Đo cache bằng log và dashboard

Một dashboard hữu ích nên có:
- Hits và misses theo cache name.
- Hit ratio theo thời gian.
- Puts, evictions, expirations.
- Cache size và memory usage nếu provider cung cấp.
- Latency của method được cache.
- Số query database và thời gian query tương ứng.
- Error rate của cache backend.
- Tỷ lệ timeout/retry khi dùng distributed cache.

Nên tách label theo cache name ổn định, ví dụ products, customer-summary, pricing. Không dùng user ID hoặc key động làm metric tag vì cardinality có thể tăng không giới hạn và làm hệ thống metrics quá tải.

Khi so sánh trước/sau khi bật cache:
1. Dùng workload và dữ liệu tương đương.
2. Ghi nhận baseline database query count/latency.
3. Warm cache theo kịch bản thực tế.
4. Đo hit/miss và latency trong cùng cửa sổ.
5. Quan sát heap, eviction và GC.
6. Kiểm tra write workload và độ trễ invalidation.
7. Chạy cả kịch bản cache lạnh, cache ấm và cache bị restart.

Không chỉ nhìn hit ratio trung bình. P95/P99 latency và database load thường cho thấy rõ hơn cache có cải thiện trải nghiệm thực tế hay không.

## 19. Kiểm thử correctness khi bật cache: ma trận tình huống

| Tình huống | Điều cần xác nhận |
|---|---|
| Đọc lần đầu | Miss, gọi nguồn dữ liệu và lưu kết quả |
| Đọc lại cùng key | Hit, không gọi nguồn lần nữa |
| Đọc key khác | Miss độc lập cho key mới |
| Cập nhật Entity | Entry cũ bị evict hoặc thay bằng kết quả mới |
| Xóa Entity | Không trả lại Entity đã xóa từ cache |
| Transaction rollback | Không cache dữ liệu chưa commit |
| TTL hết hạn | Lần đọc sau tải lại nguồn |
| Cache backend lỗi | Fallback/error behavior đúng thiết kế |
| Nhiều instance | Invalidation truyền tới các instance theo thiết kế |
| Hai tenant cùng ID | Không dùng chung key sai phạm vi |
| Nhiều request cùng miss | Không tạo tải nguồn vượt kiểm soát |
| Bulk/native update | Có cơ chế invalidation riêng vì callback không tự chạy |

Ma trận này nên được chuyển thành test case cho các cache quan trọng, đặc biệt là dữ liệu giá, quyền truy cập, trạng thái đơn hàng và thông tin có thể thay đổi thường xuyên.

## 20. Lỗi thường gặp khi đo và kiểm thử cache

**Nhầm first-level cache với Spring Cache hit**

EntityManager có thể trả Entity từ persistence context mà không chạy SQL. Điều đó không chứng minh cacheable hit. Đo từng layer riêng.

**Không bật provider statistics**

Annotation hoạt động nhưng counter hit/miss không tăng hoặc không được xuất. Bật stats và kiểm tra native cache/binder.

**Đọc cumulative counter như tỷ lệ theo phút**

Counter thường tích lũy từ lúc khởi tạo/reset. Tính delta trong cùng cửa sổ thời gian.

**Hit ratio cao nhưng database vẫn quá tải**

Có thể cache không bao phủ query nặng, miss quá đắt hoặc request còn nhiều query khác. Theo dõi DB query count và latency.

**Không evict sau update/delete**

Cache tiếp tục trả dữ liệu cũ. Gắn invalidation với mọi đường ghi, bao gồm batch, native SQL và writer ngoài ứng dụng.

**Evict trước khi transaction commit**

Nếu transaction rollback hoặc concurrent reader nạp lại giá trị cũ trước commit, cache có thể sai. Xem xét transaction-aware cache và test race.

**Cache key thiếu tenant hoặc tham số nghiệp vụ**

Kết quả của một phạm vi người dùng có thể bị trả cho phạm vi khác. Thiết kế key chứa đủ mọi yếu tố quyết định kết quả.

**Cache Entity có lazy proxy**

Entity detached hoặc quan hệ lazy có thể gây lỗi ngoài transaction. Thường cache DTO/immutable read model dễ kiểm soát hơn.

**Test phụ thuộc thứ tự chạy**

Cache còn dữ liệu từ test trước. Clear cache và dùng key riêng trước mỗi test.

**Cho rằng local eviction áp dụng toàn cluster**

Mỗi instance có thể có cache riêng. Cần distributed cache hoặc invalidation broadcast.

**Dùng metric tag có cardinality cao**

Tag theo user ID/cache key làm số lượng time series tăng mạnh. Chỉ dùng label có tập giá trị hữu hạn và ổn định.

## 21. Quy trình bật cache an toàn

Khi bật cache cho một use case Spring Data JPA:

1. Xác định dữ liệu có thể cache và thời gian stale tối đa nghiệp vụ chấp nhận.
2. Chọn cache layer: Spring Cache, Hibernate L2 hoặc query cache; tránh bật nhiều lớp không cần thiết.
3. Chọn key chứa đầy đủ tham số, tenant và ngữ cảnh ảnh hưởng kết quả.
4. Chọn provider và cấu hình TTL, maximum size, serialization và statistics.
5. Đặt Cacheable trên method đọc phù hợp và bảo đảm lời gọi đi qua Spring proxy.
6. Đặt CacheEvict hoặc CachePut trên mọi đường ghi liên quan.
7. Xác định hành vi với transaction commit/rollback, bulk DML và writer ngoài ứng dụng.
8. Bật Micrometer/provider metrics và kiểm tra hit/miss thực tế.
9. Viết test miss/hit, key khác, update, delete, rollback, TTL và concurrency.
10. Kiểm tra multi-instance invalidation nếu ứng dụng chạy nhiều node.
11. So sánh latency, database load, memory và eviction trước/sau khi bật.
12. Triển khai dần, theo dõi stale data/error rate và có khả năng tắt cache khi phát hiện sai lệch.

## 22. Kết luận

Đo hit/miss cần bắt đầu từ việc xác định cache layer. Spring Cache, persistence context và Hibernate second-level/query cache có phạm vi và thống kê riêng. Với Spring Boot/Micrometer, các cache có hỗ trợ có thể xuất cache.gets cùng tag hit/miss, puts, evictions và size; khả năng thực tế phụ thuộc provider và binder. Hit ratio được tính từ hits/(hits + misses), nhưng phải đo delta trong cùng khoảng thời gian và xem cùng database latency, memory và eviction.

Kiểm thử tính đúng đắn phải chứng minh lần đầu miss, lần sau hit, key độc lập, update/delete invalidation, rollback, TTL, concurrency và nhiều instance. Cache key phải đại diện đầy đủ cho dữ liệu, transaction cần được phối hợp với cache mutation và mọi đường ghi database phải có chiến lược invalidation. Cache chỉ đáng bật khi đo được lợi ích và chứng minh dữ liệu vẫn đúng theo freshness requirement của nghiệp vụ.
