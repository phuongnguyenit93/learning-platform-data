# Caching processor

Trong Spring Batch, ItemProcessor thường thực hiện validation, enrichment, mapping hoặc gọi dịch vụ để lấy dữ liệu bổ sung cho từng item. Nếu nhiều item cần cùng một dữ liệu tham chiếu, việc truy vấn database hoặc gọi service lặp lại có thể làm Step chậm và tăng tải hệ thống. Caching processor giúp giữ lại kết quả có thể tái sử dụng để những lần xử lý sau không phải thực hiện lại công việc tốn kém.

Caching cần được thiết kế theo semantics của dữ liệu. Cache đúng có thể giảm latency và tải backend; cache sai có thể trả dữ liệu cũ, trộn dữ liệu giữa tenant, làm sai kết quả sau restart hoặc che giấu lỗi nguồn. Đặc biệt, cache không thay thế transaction, checkpoint hay idempotency của Spring Batch. Một kết quả được cache trong bộ nhớ vẫn có thể tồn tại sau khi chunk rollback.

## 1. Vì sao cần cache trong ItemProcessor?

Giả sử Job nhập 100.000 đơn hàng. Mỗi đơn hàng cần lấy thông tin khách hàng để kiểm tra trạng thái và hạn mức:

~~~text
Order item
   |
   v
ItemProcessor
   |
   +--> Customer service / database
   |
   v
Enriched order
~~~

Nếu 100.000 đơn hàng chỉ thuộc 5.000 khách hàng, processor có thể gọi dịch vụ khách hàng nhiều lần cho cùng một customer ID. Cache giúp lưu profile đã đọc:

~~~text
Order 1, customer C-001 ----+
Order 2, customer C-001 ----+----> Cache hit
Order 3, customer C-002 ---------> Cache miss -> Load profile -> Cache
Order 4, customer C-001 ---------> Cache hit
~~~

Lợi ích thường gặp:

- Giảm số truy vấn lặp lại tới database.
- Giảm số request tới REST service hoặc hệ thống ngoài.
- Giảm latency của processor.
- Giảm tải cho hệ thống nguồn khi một batch xử lý nhiều item có khóa trùng nhau.
- Giữ snapshot dữ liệu tham chiếu trong một khoảng thời gian đã xác định.

Cache đặc biệt hữu ích với dữ liệu đọc nhiều, ít thay đổi và có thể tái sử dụng giữa nhiều item. Nó ít phù hợp với dữ liệu thay đổi liên tục hoặc kết quả phụ thuộc vào trạng thái riêng của từng lần xử lý.

## 2. Nên cache dữ liệu nào?

Không phải mọi kết quả trong processor đều nên được cache. Trước khi thêm cache, xác định dữ liệu có tính lặp lại và quy tắc thay đổi của nó.

| Dữ liệu | Khả năng phù hợp | Lý do |
|---|---|---|
| Mã quốc gia, danh mục, loại tiền | Cao | Ít thay đổi, nhiều item dùng chung |
| Customer profile | Tùy nghiệp vụ | Có thể được đọc nhiều lần nhưng cần freshness |
| Product metadata | Tùy nghiệp vụ | Giá và tồn kho có thể thay đổi nhanh |
| Tax rule theo version | Cao nếu pin version | Cần cùng một quy tắc trong cả batch |
| Kết quả validation thuần túy | Có điều kiện | Chỉ cache khi input và context đầy đủ, kết quả xác định |
| Kết quả gọi API tạo giao dịch | Không phù hợp | Có side effect và không được lặp tùy tiện |
| Kết quả phụ thuộc thời điểm hiện tại | Thường không | Cùng input có thể cho kết quả khác ở thời điểm khác |
| Dữ liệu nhạy cảm theo tenant | Có điều kiện nghiêm ngặt | Key và cache isolation phải ngăn rò dữ liệu |

Một quy tắc hữu ích là chỉ cache kết quả có thể tính lại hoặc đọc lại an toàn, với key đại diện đầy đủ cho mọi yếu tố ảnh hưởng tới kết quả.

Không cache side effect như gửi tiền, tạo invoice, gửi email hoặc phát lệnh giao dịch chỉ vì method thực hiện chúng nằm trong ItemProcessor. Những thao tác này cần idempotency key, transaction/outbox hoặc cơ chế chống thực hiện trùng riêng.

## 3. Cache dữ liệu tham chiếu thay vì cache toàn bộ item

Thông thường, cách an toàn và dễ kiểm soát hơn là cache dữ liệu tham chiếu mà processor cần, sau đó vẫn thực hiện logic xử lý cho từng item:

~~~java
@Component
public class OrderProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private final CustomerProfileService customerProfiles;

    public OrderProcessor(CustomerProfileService customerProfiles) {
        this.customerProfiles = customerProfiles;
    }

    @Override
    public EnrichedOrder process(OrderInput order) {
        CustomerProfile profile =
                customerProfiles.findByCustomerId(order.customerId());

        validateOrder(order, profile);
        return new EnrichedOrder(order, profile.customerTier());
    }
}
~~~

Processor vẫn xử lý từng order. Service chịu trách nhiệm lấy profile và có thể dùng cache. Cách tách này giúp cache policy nằm ở đúng tầng dữ liệu, đồng thời tránh vô tình tái sử dụng toàn bộ output của một item khác.

Nếu cache cả EnrichedOrder, key phải bao gồm tất cả input và context ảnh hưởng tới output, chẳng hạn order version, customer profile version, currency, locale, policy version và ngày nghiệp vụ. Điều này thường phức tạp hơn cache profile theo customer ID.

## 4. Dùng Spring Cache abstraction

Spring cung cấp Cache abstraction để ứng dụng dùng annotation hoặc API mà không phụ thuộc trực tiếp vào một cache provider cụ thể. Các provider có thể là Caffeine, JCache, Redis hoặc implementation khác được cấu hình trong ứng dụng.

Để dùng annotation caching, bật caching:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
~~~

Đánh dấu method đọc dữ liệu tham chiếu:

~~~java
@Service
public class CustomerProfileService {

    private final CustomerRepository repository;

    public CustomerProfileService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
            cacheNames = "customerProfiles",
            key = "#customerId",
            unless = "#result == null")
    public CustomerProfile findByCustomerId(String customerId) {
        return repository.findByCustomerId(customerId)
                .orElse(null);
    }
}
~~~

Khi method được gọi với customerId đã có trong cache, Spring trả về giá trị cache mà không thực thi method body. Khi chưa có entry, method truy vấn repository rồi lưu kết quả theo cấu hình cache.

Các thuộc tính thường dùng:

- cacheNames/value: tên cache.
- key: biểu thức xác định cache key.
- keyGenerator: component tự tạo key.
- condition: điều kiện để thực hiện caching.
- unless: điều kiện loại kết quả khỏi cache sau khi method chạy.
- cacheManager/cacheResolver: chọn nơi quản lý cache.
- sync: yêu cầu cache provider phối hợp việc nạp một key khi có nhiều lời gọi đồng thời, tùy hỗ trợ provider.

## 5. Spring Cache hoạt động qua proxy

Annotation như Cacheable thường được thực thi qua Spring AOP proxy. Vì vậy, method cần được gọi qua Spring bean proxy thì caching advice mới có cơ hội chạy.

Một lỗi phổ biến là self-invocation:

~~~java
@Service
public class CustomerProfileService {

    public CustomerProfile load(String id) {
        return findCached(id);
    }

    @Cacheable(cacheNames = "customerProfiles", key = "#id")
    public CustomerProfile findCached(String id) {
        return repository.findByCustomerId(id).orElse(null);
    }
}
~~~

Nếu load() gọi findCached() trực tiếp trên cùng instance, lời gọi nội bộ thường không đi qua proxy, nên annotation Cacheable trên findCached() có thể không được áp dụng. Hãy gọi method cacheable từ một bean khác hoặc tách method sang service riêng.

Không tự tạo service bằng new nếu muốn dùng proxy và các dependency do Spring quản lý. Inject bean qua constructor.

## 6. Cấu hình cache provider bằng Caffeine

Caffeine là một cache in-memory phổ biến trên JVM. Nó hỗ trợ giới hạn dung lượng, expiration và các chính sách eviction hiệu quả.

Ví dụ cấu hình Spring Cache:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("customerProfiles");

        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(100_000)
                .expireAfterWrite(Duration.ofMinutes(10)));

        return manager;
    }
}
~~~

Ví dụ này cần dependency Caffeine trong build. maximumSize giới hạn số entry và expireAfterWrite đặt thời gian sống tính từ lúc ghi. Giá trị thực tế phải dựa trên kích thước object, số key duy nhất, heap budget và tốc độ thay đổi dữ liệu.

Cache in-memory thuộc một JVM. Nếu chạy nhiều application instance hoặc nhiều worker process, mỗi process có cache riêng. Một process có thể thấy dữ liệu mới trong khi process khác vẫn giữ giá trị cũ cho đến khi entry hết hạn hoặc được invalidated.

## 7. TTL, eviction và giới hạn bộ nhớ

Cache cần có chính sách vòng đời. Nếu không giới hạn số entry, một Job xử lý nhiều triệu business key có thể giữ quá nhiều object trong heap và gây tăng garbage collection hoặc OutOfMemoryError.

Các cơ chế thường dùng:

- **TTL/expiration:** tự hết hạn sau một khoảng thời gian.
- **Maximum size:** giới hạn số entry.
- **Maximum weight:** giới hạn theo trọng lượng ước tính của entry.
- **Eviction policy:** loại entry khi cần chỗ trống.
- **Explicit invalidation:** xóa entry khi dữ liệu nguồn thay đổi.
- **Versioned key:** tạo key mới khi version dữ liệu thay đổi.

TTL dài giúp tăng hit rate nhưng có thể trả dữ liệu cũ lâu hơn. TTL ngắn cải thiện freshness nhưng giảm hit rate và tăng tải nguồn. Hãy chọn theo SLA của dữ liệu, không chỉ theo mục tiêu giảm số lần gọi service.

Maximum size là giới hạn số entry, không phải giới hạn byte chính xác. Một entry có thể chứa object lớn hơn nhiều entry khác. Nếu giá trị có kích thước biến động mạnh, cần ước tính memory footprint hoặc dùng cache provider hỗ trợ maximum weight.

## 8. Chọn cache key chính xác

Cache key phải đại diện đầy đủ cho mọi yếu tố quyết định kết quả. Nếu key thiếu một chiều context, cache có thể trả kết quả của một item cho item khác.

Ví dụ, profile phụ thuộc tenant:

~~~java
@Cacheable(
        cacheNames = "customerProfiles",
        key = "#tenantId + ':' + #customerId")
public CustomerProfile find(
        String tenantId,
        String customerId) {
    return repository.find(tenantId, customerId).orElse(null);
}
~~~

Nếu chỉ dùng customerId trong hệ thống multi-tenant, hai tenant có thể vô tình dùng chung entry. Đây vừa là lỗi dữ liệu vừa có thể là rò rỉ thông tin giữa tenant.

Những yếu tố có thể cần đưa vào key:

- Tenant hoặc security domain.
- Entity ID.
- Locale hoặc currency.
- Policy/schema version.
- Ngày nghiệp vụ hoặc effective date.
- Loại yêu cầu hoặc channel.
- Version của dữ liệu nguồn.

Không đưa toàn bộ object mutable làm key nếu equals/hashCode có thể thay đổi sau khi object được đưa vào cache. Nên dùng record/key object bất biến hoặc chuỗi canonical được chuẩn hóa.

## 9. Key object bất biến

Khi key có nhiều thành phần, dùng record giúp thể hiện contract:

~~~java
public record CustomerCacheKey(
        String tenantId,
        String customerId,
        String policyVersion) {
}
~~~

Tạo key:

~~~java
CustomerCacheKey key = new CustomerCacheKey(
        tenantId,
        customerId,
        policyVersion);
~~~

Key phải được chuẩn hóa nhất quán. Ví dụ, nếu tenant ID không phân biệt chữ hoa/chữ thường, hãy canonicalize ở một tầng duy nhất trước khi tạo key. Không tùy tiện trim hoặc đổi chữ hoa/thường nếu contract cho phép các giá trị phân biệt nhau.

Tránh dùng key có giá trị nhạy cảm trực tiếp trong log hoặc metrics. Có thể log loại cache và kết quả hit/miss mà không ghi raw key.

## 10. Cache output của ItemProcessor bằng decorator

Trong một số trường hợp, muốn bọc một ItemProcessor hiện có bằng một processor có cache. Có thể tạo decorator:

~~~java
public class CachingItemProcessor<I, O>
        implements ItemProcessor<I, O> {

    private final ItemProcessor<I, O> delegate;
    private final Cache cache;
    private final Function<I, Object> keyGenerator;

    public CachingItemProcessor(
            ItemProcessor<I, O> delegate,
            Cache cache,
            Function<I, Object> keyGenerator) {
        this.delegate = delegate;
        this.cache = cache;
        this.keyGenerator = keyGenerator;
    }

    @Override
    @SuppressWarnings("unchecked")
    public O process(I item) throws Exception {
        Object key = keyGenerator.apply(item);
        Cache.ValueWrapper cached = cache.get(key);

        if (cached != null) {
            return (O) cached.get();
        }

        O result = delegate.process(item);
        if (result != null) {
            cache.put(key, result);
        }
        return result;
    }
}
~~~

Decorator này chỉ cache output khác null. Điều đó tránh phụ thuộc vào việc cache provider có hỗ trợ lưu null hay không, và không giữ quyết định filter vô thời hạn. Cache miss đồng thời từ nhiều thread vẫn có thể gọi delegate nhiều lần vì đoạn get rồi process rồi put không phải một thao tác atomic. Nếu cần single-flight loading, dùng API đồng bộ của provider hoặc một cache loader phù hợp.

Ví dụ decorator chỉ an toàn khi delegate là hàm xác định theo key, không có side effect và output có thể dùng lại. Nếu delegate cập nhật database, gửi message hoặc phụ thuộc vào trạng thái mutable, cache toàn bộ output có thể làm bỏ qua công việc cần thiết.

## 11. Caching null và negative caching

Một lần tra cứu không tìm thấy dữ liệu có thể được cache để tránh truy vấn lặp lại. Đây thường được gọi là negative caching.

Ví dụ customer ID không tồn tại được tra đi tra lại trong file. Nếu mỗi lần đều truy vấn database, hệ thống có thể tốn tải cho cùng một kết quả không có dữ liệu.

Negative caching cần thận trọng:

- Dữ liệu chưa tồn tại hôm nay có thể được tạo sau đó.
- Cache null quá lâu có thể làm record mới không được nhìn thấy.
- Một số cache provider không cho lưu null hoặc cần cấu hình cho phép.
- Null có thể có nghĩa khác nhau: không tìm thấy, không được phép truy cập hoặc lỗi nguồn.

Với Spring Cache, unless có thể loại null khỏi cache:

~~~java
@Cacheable(
        cacheNames = "customerProfiles",
        key = "#customerId",
        unless = "#result == null")
public CustomerProfile find(String customerId) {
    return repository.findByCustomerId(customerId).orElse(null);
}
~~~

Nếu muốn negative caching, nên biểu diễn kết quả rõ ràng bằng Optional hoặc một wrapper có trạng thái FOUND/NOT_FOUND, rồi đặt TTL ngắn hơn cho NOT_FOUND. Không cache lỗi timeout hoặc lỗi kết nối như thể dữ liệu chắc chắn không tồn tại.

## 12. Cache hit, cache miss và cache stampede

Cache miss đồng thời có thể khiến nhiều thread cùng gọi backend cho một key trước khi entry được ghi. Hiện tượng này thường gọi là cache stampede hoặc thundering herd.

~~~text
Thread A ---- cache miss ----+
Thread B ---- cache miss ----+----> Backend load nhiều lần
Thread C ---- cache miss ----+
~~~

Với dữ liệu đắt tiền, cần phối hợp việc nạp:

- Dùng cache API có cơ chế atomic loading/single-flight.
- Dùng Caffeine Cache.get(key, mappingFunction) khi dùng trực tiếp Caffeine.
- Dùng Spring Cache sync=true nếu provider và Cache implementation hỗ trợ semantics phù hợp.
- Preload dữ liệu tham chiếu trước Step nếu tập dữ liệu nhỏ và biết trước.
- Dùng distributed lock chỉ khi cần và cân nhắc chi phí/khả năng phục hồi.

Ví dụ Spring Cache:

~~~java
@Cacheable(
        cacheNames = "customerProfiles",
        key = "#customerId",
        sync = true)
public CustomerProfile find(String customerId) {
    return repository.findByCustomerId(customerId).orElse(null);
}
~~~

sync=true yêu cầu đồng bộ việc tải cùng một key qua cache provider. Đây không phải bảo đảm phân tán giống nhau cho mọi provider; kiểm tra giới hạn của Cache implementation đang dùng. Không dựa vào nó để khóa nghiệp vụ xuyên nhiều application instance nếu provider không cung cấp distributed coordination.

## 13. Cache local và distributed cache

Có hai hướng triển khai phổ biến:

| Tiêu chí | Local cache | Distributed cache |
|---|---|---|
| Nơi lưu | Heap của một JVM | Hệ thống cache dùng chung như Redis hoặc provider phân tán |
| Latency | Thường rất thấp | Có network round-trip |
| Chia sẻ giữa instance | Không tự chia sẻ | Có thể chia sẻ |
| Invalidation | Từng JVM hoặc qua event | Có thể tập trung hơn nhưng cần thiết kế |
| Failure mode | Ảnh hưởng process hiện tại | Có thêm dependency mạng/cache server |
| Phù hợp | Reference data nhỏ, ít thay đổi | Nhiều instance cần chia sẻ cache |

Local cache đơn giản và nhanh nhưng có thể tạo nhiều bản copy trên các worker process. Distributed cache giảm sự phân tán dữ liệu cache nhưng thêm latency, network failure, serialization và vận hành.

Không nên chuyển sang distributed cache chỉ vì Job chạy nhiều thread trong một JVM. Caffeine local cache có thể đáp ứng tốt. Chỉ cần distributed cache khi nhiều process cần chia sẻ entry hoặc có yêu cầu tập trung về invalidation/visibility.

## 14. Cache scope và vòng đời trong Spring Batch

Cache và bean processor có thể có vòng đời khác nhau:

- Processor singleton: một instance có thể được nhiều JobExecution hoặc thread dùng chung.
- Processor @StepScope: target bean riêng cho mỗi StepExecution.
- CacheManager singleton: thường được chia sẻ trong application context.
- Cache local nằm trong processor: có vòng đời của bean processor.
- Distributed cache: có vòng đời ngoài JVM và có thể tồn tại qua restart.

@StepScope không tự tạo một cache dùng riêng cho từng thread. Nếu processor có field cache mutable, nhiều thread trong cùng StepExecution vẫn có thể truy cập cùng instance. Nếu muốn cache riêng cho từng worker partition, có thể tạo cache theo StepExecution hoặc dùng key có partition ID; cần cân nhắc memory và việc dữ liệu có thể dùng chung giữa partition hay không.

Nếu cache nằm trong singleton service, hai JobExecution có thể dùng chung entry. Điều này chỉ đúng khi dữ liệu cache không phụ thuộc vào state riêng của từng Job. Nếu phụ thuộc batch ID, policy version hoặc security context, đưa các yếu tố đó vào key hoặc cô lập cache.

## 15. Thread safety của cache

Trong multi-threaded Step, nhiều thread có thể gọi cùng processor hoặc service cache. Cần dùng cache provider có concurrency semantics phù hợp.

Các điểm cần chú ý:

- Không dùng HashMap mutable làm cache chung nếu nhiều thread đọc/ghi.
- Caffeine và ConcurrentMapCache hỗ trợ concurrent access theo implementation của chúng.
- Cache value nên bất biến hoặc được copy trước khi trả về.
- Cache loader không nên có side effect không idempotent.
- Invalidation đồng thời với load cần có semantics rõ.
- Không sửa trực tiếp object đang nằm trong cache.

Một cache thread-safe không đồng nghĩa toàn bộ dữ liệu bên trong tự thread-safe. Nếu cache lưu một ArrayList mutable và nhiều processor sửa list đó, vẫn có race condition.

## 16. Không sửa trực tiếp cache value

Giả sử cache lưu CustomerProfile:

~~~java
CustomerProfile profile = cache.get(customerId);
profile.setRiskLevel("HIGH");
~~~

Nếu profile là object mutable được chia sẻ, thay đổi của một item có thể ảnh hưởng item khác hoặc làm thay đổi kết quả mà không có invalidation. Điều này đặc biệt nguy hiểm khi cache value được tái sử dụng giữa tenant hoặc JobExecution.

Ưu tiên immutable DTO:

~~~java
public record CustomerProfile(
        String customerId,
        String tier,
        String riskLevel) {
}
~~~

Nếu cần thay đổi, tạo object mới:

~~~java
CustomerProfile enriched = new CustomerProfile(
        profile.customerId(),
        profile.tier(),
        calculateRisk(order, profile));
~~~

Không ghi state của từng item vào object tham chiếu lấy từ cache. Cache nên chứa dữ liệu tham chiếu ổn định; item output nên là object riêng.

## 17. Cache và transaction của chunk

Cache in-memory thường không tham gia transaction của database. Ví dụ:

1. Processor đọc dữ liệu từ repository.
2. Kết quả được đưa vào cache.
3. Writer ghi dữ liệu nhưng chunk rollback.
4. Cache vẫn giữ kết quả vừa đọc.

Đây không nhất thiết là lỗi nếu cache chỉ chứa dữ liệu tham chiếu đã commit và có thể đọc lại an toàn. Nhưng nếu cache lưu kết quả phụ thuộc vào thay đổi chưa commit, cache có thể giữ giá trị không tồn tại trong database sau rollback.

Không giả định cache put sẽ rollback cùng transaction. Spring Cache không mặc định cung cấp transaction semantics giống database. Một số provider/integration có transaction-aware behavior riêng, nhưng cần cấu hình và xác minh cụ thể.

Với dữ liệu có thể thay đổi trong cùng chunk, tránh cache kết quả chưa commit hoặc dùng version/snapshot để phân biệt. Nếu cần invalidation sau commit, dùng transaction synchronization hoặc event/outbox sau commit thay vì xóa cache trước khi transaction hoàn tất.

## 18. Cache và retry

Spring Batch có thể gọi lại processor khi retry một item hoặc chunk. Cache làm thay đổi số lần delegate được gọi:

- Lần đầu cache miss, delegate chạy và kết quả được cache.
- Writer sau đó thất bại.
- Chunk rollback và processor được gọi lại.
- Lần retry cache hit, delegate không chạy lần nữa.

Điều này đúng nếu delegate là phép tính thuần túy và kết quả vẫn hợp lệ. Nó sai nếu delegate có side effect cần được thực hiện trong mỗi lần thử hoặc output phụ thuộc vào trạng thái transaction đã rollback.

Vì vậy:

- Không dùng cache để chống duplicate side effect.
- Không cache exception tạm thời như kết quả cuối.
- Không cache kết quả phụ thuộc vào state chưa commit.
- Dùng idempotency key cho side effect.
- Đặt cache key có version nếu dữ liệu thay đổi theo transaction.

Nếu retry cần gọi lại delegate để xác nhận trạng thái nguồn, không nên cache output của toàn bộ processor. Có thể chỉ cache dữ liệu tham chiếu ít thay đổi và để bước kiểm tra trạng thái thực hiện lại.

## 19. Cache và restart

Cache local trong JVM thường mất khi process restart. Điều này không phải vấn đề nếu cache chỉ là tối ưu hiệu năng: lần restart đầu tiên có thể có nhiều cache miss hơn, sau đó cache được làm nóng lại.

Không nên lưu toàn bộ cache vào ExecutionContext. ExecutionContext phục vụ checkpoint và state cần khôi phục, không phải kho cache lớn. Lưu hàng nghìn hoặc hàng triệu entry có thể làm metadata phình to, tăng chi phí serialization và ảnh hưởng JobRepository.

Nếu kết quả cache cần tồn tại qua restart, có thể dùng:

- Distributed cache có TTL và version.
- Bảng reference snapshot gắn với batch ID.
- File snapshot bất biến.
- JobParameters chứa policy/version để nạp lại đúng dữ liệu.

Đối với batch cần tái lập kết quả, cách quan trọng nhất là pin version của dữ liệu/quy tắc. Cache chỉ là lớp tăng tốc truy cập tới snapshot đó.

## 20. Cache invalidation khi dữ liệu nguồn thay đổi

Cache có thể trở nên stale khi dữ liệu nguồn được cập nhật. Cần chọn chính sách invalidation:

### TTL

Entry tự hết hạn sau một khoảng thời gian. Dễ triển khai nhưng chấp nhận một khoảng stale window.

### Explicit eviction

Khi service cập nhật customer, nó xóa entry tương ứng:

~~~java
@CacheEvict(
        cacheNames = "customerProfiles",
        key = "#customerId")
public void updateProfile(
        String customerId,
        CustomerProfileUpdate update) {
    repository.update(customerId, update);
}
~~~

Nếu update database thành công nhưng eviction thất bại, cache có thể giữ dữ liệu cũ. Cần cân nhắc transaction ordering, retry invalidation hoặc event sau commit.

### Versioned key

Key chứa profile version hoặc policy version. Khi version tăng, request mới dùng key mới và không đọc entry cũ. Entry cũ có thể được dọn theo TTL.

### Event-driven invalidation

Service phát event sau khi dữ liệu thay đổi; các cache instance nhận event và evict entry. Cần xử lý event bị trễ, mất hoặc gửi lặp. Với nhiều JVM, invalidation event phải được broadcast tới mọi instance dùng local cache.

Không có một chiến lược phù hợp cho mọi dữ liệu. Với reference data cần consistency trong một batch, snapshot/version pin thường dễ kiểm soát hơn invalidation tức thời.

## 21. Cache policy version theo batch

Giả sử processor tính thuế dựa trên tax rule. Nếu rule thay đổi giữa Job, hai item trong cùng batch có thể được tính theo hai phiên bản khác nhau nếu cache refresh trong lúc chạy.

Có thể pin policy version trong JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", batchId, true)
        .addString("taxPolicyVersion", policyVersion, true)
        .toJobParameters();
~~~

Cache key:

~~~java
@Cacheable(
        cacheNames = "taxRules",
        key = "#policyVersion + ':' + #countryCode")
public TaxRule findRule(
        String policyVersion,
        String countryCode) {
    return repository.findRule(policyVersion, countryCode);
}
~~~

Khi restart cùng JobInstance, policyVersion vẫn giữ nguyên. Nếu cần dùng policy mới, tạo một JobInstance mới hoặc có quy trình reprocessing rõ ràng. Không silently đổi version trong một execution đã có checkpoint.

## 22. Cache error và fallback policy

Cache provider hoặc backend có thể lỗi:

- Cache server không kết nối được.
- Serialization/deserialization thất bại.
- Entry hết hạn hoặc bị evict.
- Cache loader timeout.
- Cache hết dung lượng hoặc bị từ chối ghi.

Cần quyết định cache là dependency bắt buộc hay chỉ là tối ưu:

| Tình huống | Chính sách có thể phù hợp |
|---|---|
| Cache miss | Load từ source |
| Cache read lỗi, dữ liệu nguồn sẵn sàng | Fail-open: đọc source trực tiếp |
| Cache write lỗi sau khi load thành công | Có thể trả kết quả source nếu cache chỉ là tối ưu |
| Policy/security lookup không xác định | Fail-closed nếu không thể xác minh an toàn |
| Source timeout | Retry có giới hạn hoặc fail Step |
| Dữ liệu không tồn tại | Negative cache có TTL ngắn nếu nghiệp vụ cho phép |

Không biến mọi cache exception thành cache miss một cách mù quáng. Nếu cache là nơi duy nhất giữ policy hoặc dữ liệu bắt buộc, bỏ qua lỗi có thể tạo kết quả sai. Log và metrics cần phân biệt cache failure với source failure.

## 23. Cache warming và preload

Nếu Job biết trước tập dữ liệu tham chiếu cần dùng, có thể preload cache trước khi xử lý item:

~~~text
Step 1: Load reference data
          |
          v
      Cache warm-up
          |
          v
Step 2: Process business items
          |
          v
      Cache lookups
~~~

Preload phù hợp khi:

- Tập reference data có kích thước hữu hạn.
- Dữ liệu cần nhất quán trong một batch.
- Có thể tải snapshot theo version.
- Thời gian preload thấp hơn chi phí truy vấn lặp lại.

Không preload toàn bộ bảng lớn vào heap nếu Job chỉ dùng một phần nhỏ. Có thể preload theo key set, theo partition hoặc dùng cache on-demand.

Nếu warm-up là một Step riêng, hãy lưu policy/version hoặc snapshot ID để các Step sau dùng cùng dữ liệu. Nếu Step warm-up thành công nhưng Step xử lý restart, không nên mặc định cache local vẫn còn trong memory; có thể cần preload lại hoặc dùng snapshot bền vững.

## 24. Cache và multi-threaded Step/partitioning

Trong multi-threaded Step, nhiều thread có thể gọi cùng processor. Cache provider cần hỗ trợ concurrent get/put/load. Nếu processor là singleton, mọi thread có thể dùng chung cache field hoặc service cache.

Trong partitioning, mỗi worker có thể chạy ở process hoặc JVM khác nhau:

- Local cache trên từng worker không chia sẻ entry.
- Một tenant/key có thể được load lặp lại ở nhiều partition.
- Cache distributed có thể chia sẻ entry nhưng thêm network dependency.
- Policy version phải giống nhau nếu các partition cần cùng kết quả.

Không giả định cache hit ở partition A sẽ làm partition B có hit nếu chúng chạy trên JVM khác. Nếu cần giảm duplicate load giữa các worker, dùng distributed cache hoặc preload snapshot chung.

Đồng thời, tránh một key nóng làm tất cả worker tranh chấp cùng một backend entry. Có thể dùng local near-cache kết hợp distributed cache nếu provider hỗ trợ và consistency requirements cho phép.

## 25. Cache trong processor chain

Một pipeline có thể gồm nhiều processor:

~~~text
Input
  |
  v
NormalizeProcessor
  |
  v
CachedReferenceLookupProcessor
  |
  v
ValidateProcessor
  |
  v
EnrichProcessor
  |
  v
Output
~~~

Cache nên được đặt gần bước có dữ liệu lặp lại. Không nhất thiết cache toàn bộ pipeline. Ví dụ:

- Normalize: thường là phép biến đổi nhanh, không cần cache.
- Reference lookup: có thể cache theo reference key.
- Validation: chỉ cache nếu kết quả thuần và phụ thuộc đầy đủ input/context.
- Enrichment: cache nếu dữ liệu có thể tái sử dụng và freshness rõ.

Nếu dùng CompositeItemProcessor, các delegate cần có kiểu input/output tương thích. Cache wrapper phải giữ đúng contract của ItemProcessor: trả output hoặc null để filter, và ném exception theo semantics đã định.

## 26. Cache và classifier

Classifier có thể chọn processor dựa trên metadata hoặc policy đã cache. Tuy nhiên, không nên dùng cache để che giấu route configuration thiếu hoặc làm route thay đổi không xác định.

Nếu route phụ thuộc tenant policy, key cache cần có tenant và policy version. Khi classifier chọn delegate, kết quả cần ổn định qua retry/restart của cùng item.

Nếu cache lookup trong classifier thất bại, hãy phân biệt lỗi tạm thời với unknown route. Không trả null delegate chỉ vì cache miss; cache miss là cơ hội load từ source, còn no-match là trường hợp không có route hợp lệ sau khi đã xác định policy.

## 27. Quan sát hiệu quả cache

Không nên chỉ thêm cache rồi giả định hiệu năng đã tốt hơn. Cần đo:

- Hit count và miss count.
- Hit ratio.
- Load count và load failure.
- Load latency.
- Eviction count.
- Cache size/estimated weight.
- Backend query/request count.
- Processor duration trước và sau caching.
- Tỷ lệ stale hoặc invalidation nếu hệ thống đo được.

Hit ratio cao chưa chắc có lợi nếu cache load rất rẻ hoặc object giữ trong heap quá lớn. Ngược lại, hit ratio vừa phải vẫn có ích nếu mỗi miss gọi một service chậm.

Dùng Micrometer hoặc metrics của cache provider để quan sát. Tránh gắn business key hoặc customer ID làm metric tag vì cardinality cao có thể làm hệ thống metrics quá tải và lộ dữ liệu. Tag theo cache name, outcome hoặc operation type thường phù hợp hơn.

## 28. Kiểm thử caching processor

Unit test nên xác nhận delegate được gọi đúng số lần:

~~~java
@Test
void reusesCachedCustomerProfile() {
    CustomerRepository repository = mock(CustomerRepository.class);
    CustomerProfile profile =
            new CustomerProfile("C-001", "GOLD", "LOW");

    when(repository.findByCustomerId("C-001"))
            .thenReturn(Optional.of(profile));

    CustomerProfileService service =
            new CustomerProfileService(repository);

    CustomerProfile first = service.findByCustomerId("C-001");
    CustomerProfile second = service.findByCustomerId("C-001");

    assertSame(first, second);
    verify(repository, times(1)).findByCustomerId("C-001");
}
~~~

Đoạn test trên chỉ kiểm tra service thuần; nếu dùng @Cacheable, cần gọi qua Spring proxy trong test context để annotation có hiệu lực. Một unit test tạo object bằng new sẽ không kiểm tra Spring AOP caching.

Các tình huống cần test:

- Cache hit không gọi source lần nữa.
- Cache miss gọi source và lưu kết quả.
- Key khác nhau không dùng nhầm entry.
- Tenant khác nhau không chia sẻ dữ liệu.
- Null/negative result theo đúng TTL và policy.
- Entry hết hạn hoặc bị evict được nạp lại.
- Cache failure theo đúng fail-open/fail-closed policy.
- Nhiều thread cùng miss một key không tạo tải ngoài dự kiến.
- Output mutable không bị thay đổi qua các item.

## 29. Kiểm thử Spring Batch integration

Một integration test nên chạy Step với nhiều item có reference key lặp lại và xác nhận cả kết quả lẫn số lần load:

~~~text
Input:
  Order 1 -> customer C-001
  Order 2 -> customer C-001
  Order 3 -> customer C-002
  Order 4 -> customer C-001

Expected reference loads:
  C-001 -> 1 lần trong cache lifetime
  C-002 -> 1 lần trong cache lifetime
~~~

Kiểm tra:

- Output của từng item vẫn đúng.
- Số lần truy vấn backend giảm như dự kiến.
- Cache key không trộn tenant/policy.
- Retry không làm lặp side effect.
- Rollback không làm cache giữ dữ liệu chưa commit.
- Restart hoạt động khi cache cold.
- Partition hoặc nhiều JobExecution không chia sẻ state sai phạm vi.

Nếu dùng local cache, test restart nên tạo lại application context hoặc cache instance để xác nhận Job không phụ thuộc cache cũ. Nếu dùng distributed cache, test invalidation, TTL và lỗi kết nối với provider test phù hợp.

## 30. Các lỗi thường gặp

**Cache toàn bộ processor có side effect:** cache hit bỏ qua delegate và có thể bỏ qua thao tác nghiệp vụ cần thực hiện. Chỉ cache phép đọc hoặc phép tính xác định.

**Cache key thiếu tenant hoặc policy version:** có thể trả dữ liệu của context khác. Đưa mọi yếu tố ảnh hưởng kết quả vào key.

**Không giới hạn cache:** batch có nhiều key duy nhất có thể làm heap tăng liên tục. Đặt maximum size/weight và TTL.

**Cache output mutable:** item sau có thể thấy object đã bị item trước sửa. Dùng immutable value hoặc copy.

**Dùng @Cacheable trong self-invocation:** lời gọi nội bộ không qua proxy nên caching advice không chạy như mong đợi. Tách bean hoặc gọi qua proxy.

**Giả định cache put rollback cùng database:** cache thường không tham gia chunk transaction. Không cache state phụ thuộc vào thay đổi chưa commit.

**Dùng cache để chống duplicate:** cache eviction, restart hoặc nhiều instance có thể làm side effect chạy lại. Dùng idempotency key và unique constraint.

**Cache null quá lâu:** record mới được tạo vẫn bị xem là không tồn tại. Negative cache cần TTL ngắn và semantics rõ.

**Không xử lý cache stampede:** nhiều thread cùng miss làm backend nhận nhiều request. Dùng atomic loading/single-flight khi cần.

**Coi local cache là dùng chung giữa partition:** mỗi JVM có cache riêng. Đánh giá cache scope và worker topology.

**Cache policy thay đổi mà không version:** cùng Job có thể dùng nhiều rule khác nhau. Pin policy version hoặc snapshot theo batch.

**Đưa business ID vào metric tag:** tạo cardinality cao và có thể lộ dữ liệu. Dùng tag có phạm vi thấp.

**Không kiểm thử cache cold khi restart:** Job có thể chỉ chạy đúng khi cache còn nóng. Đảm bảo cache là tối ưu hiệu năng, không phải nguồn state bắt buộc.

## Kết luận

Caching processor giúp giảm truy vấn và lời gọi dịch vụ lặp lại khi nhiều item dùng chung dữ liệu hoặc kết quả có thể tái sử dụng. Ưu tiên cache dữ liệu tham chiếu ở service được processor gọi; chỉ cache toàn bộ output khi phép xử lý xác định, key đầy đủ và không có side effect. Chọn provider, TTL, eviction và invalidation theo yêu cầu freshness, memory và topology worker. Đảm bảo cache key bao gồm tenant/context/version, value bất biến, cache thread-safe và cache failure có policy rõ. Cache thường không tham gia transaction của chunk và local cache mất khi restart, vì vậy không dùng nó thay checkpoint, idempotency hay business state. Đo hit/miss và backend load, đồng thời kiểm thử cache hit, cache cold, concurrency, rollback và restart trong Step integration để chứng minh cache chỉ tăng tốc mà không thay đổi kết quả nghiệp vụ.
