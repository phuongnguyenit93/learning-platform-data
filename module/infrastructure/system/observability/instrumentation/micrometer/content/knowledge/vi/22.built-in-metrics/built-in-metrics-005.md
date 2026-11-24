# Giám sát cache: tỷ lệ truy cập, dung lượng và loại bỏ phần tử

Cache giảm độ trễ và tải cho database hoặc dịch vụ phía sau bằng cách giữ lại kết quả để tái sử dụng. Hiệu quả của cache phụ thuộc vào workload, chính sách lưu trữ và cách ứng dụng truy cập key. Một cache có hit ratio thấp có thể làm tăng số lần truy vấn nguồn; cache tăng kích thước liên tục có thể vượt ngân sách bộ nhớ; eviction tăng nhanh có thể cho thấy working set lớn hơn sức chứa hoặc chính sách hết hạn chưa phù hợp.

Micrometer cung cấp các binder để quan sát hành vi cache. Bộ metric cơ bản thường gồm số lần hit/miss, số entry hiện tại và số entry bị eviction. Từ hit và miss, có thể tính hit ratio theo một khoảng thời gian. Size cho biết số entry hiện tại nếu provider hỗ trợ; eviction count cho biết số entry đã bị loại bỏ theo cơ chế của cache. Cần đọc những số đo này cùng nhau và hiểu giới hạn của từng cache provider.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích các metric cache phổ biến do Micrometer binder tạo ra.
- Bật thống kê của cache provider và đăng ký cache với MeterRegistry.
- Tính hit ratio và miss ratio từ số lần hit/miss trong một khoảng thời gian.
- Theo dõi số entry hiện tại và tốc độ eviction.
- Phân biệt eviction, expiration, invalidation và thao tác remove.
- Hiểu vì sao một số provider không cung cấp đủ size, miss hoặc eviction statistics.
- Tích hợp cache metrics với Spring Boot Actuator.
- Dùng metrics để đánh giá hiệu quả cache mà không tạo tag cardinality cao.

## Cache metrics trả lời những câu hỏi nào?

Một cache thường cần được quan sát theo ba nhóm:

1. **Hiệu quả truy cập:** bao nhiêu lần lookup trả về entry có sẵn (hit), bao nhiêu lần phải tải hoặc tính lại giá trị (miss)?
2. **Dung lượng hiện tại:** cache đang giữ bao nhiêu entry? Con số này có tiến gần giới hạn cấu hình không?
3. **Loại bỏ entry:** cache đã eviction bao nhiêu entry và tốc độ eviction có tăng bất thường không?

Micrometer cung cấp một bộ metric cơ bản dùng chung cho nhiều cache implementation. Một số provider còn có metric riêng về load duration, eviction weight, transaction hoặc storage.

| Meter canonical | Loại thường gặp | Ý nghĩa |
|---|---|---|
| `cache.gets` | Function-tracking counter | Số lần lookup, có tag `result=hit` hoặc `result=miss` |
| `cache.puts` | Function-tracking counter | Số entry được thêm theo thống kê mà provider cung cấp |
| `cache.evictions` | Function-tracking counter | Số entry bị eviction |
| `cache.size` | Gauge | Số entry hiện tại hoặc ước lượng |
| Metric riêng của provider | Tùy provider | Load duration, eviction weight, dung lượng storage hoặc thống kê bổ sung |

Các meter được gắn tag nhận diện cache, thường gồm tên cache và có thể có tên CacheManager. Tên và tập tag thực tế phụ thuộc binder, Spring Boot và provider. Hãy kiểm tra registry hoặc endpoint Actuator để biết các tag đang có.

### Hiểu đúng hit và miss

- **Hit:** thao tác lookup tìm thấy entry có thể sử dụng trong cache.
- **Miss:** thao tác lookup không tìm thấy entry; ứng dụng thường phải tải dữ liệu từ nguồn hoặc tính toán lại.
- **Hit ratio:** tỷ lệ lookup thành công trên tổng lookup trong một khoảng.
- **Miss ratio:** tỷ lệ lookup thất bại trên tổng lookup trong một khoảng.

Công thức:

\[
\text{hit ratio} = \frac{\text{hits}}{\text{hits}+\text{misses}}
\]

\[
\text{miss ratio} = \frac{\text{misses}}{\text{hits}+\text{misses}}
\]

Nếu có 900 hit và 100 miss trong cùng khoảng thời gian, hit ratio là 90% và miss ratio là 10%.

Hit ratio nên được tính theo một cửa sổ thời gian, chẳng hạn 5 phút, để phản ánh hành vi gần đây. Dùng tổng hit/miss từ lúc process khởi động có thể che khuất sự suy giảm vừa xảy ra. Micrometer dùng function-tracking counter cho các thống kê tích lũy; backend có thể tính tốc độ tăng của chúng trong từng cửa sổ.

## Binder cache của Micrometer

Micrometer có các binder cho nhiều cache phổ biến như Caffeine, Ehcache, Guava, Hazelcast và JCache. Spring Boot cũng có auto-configuration để đăng ký metrics cho các cache tương thích với phiên bản Boot đang dùng. Danh sách hỗ trợ và mức chi tiết thay đổi theo provider, phiên bản Micrometer và phiên bản Spring Boot.

Tài liệu Spring Boot hiện hành liệt kê Cache2k, Caffeine, Hazelcast, JCache và Redis cho auto-configuration cache metrics. Danh sách binder trực tiếp của Micrometer có thể khác, chẳng hạn có Ehcache và Guava. Vì vậy, hãy đối chiếu đúng danh sách của integration mà dự án đang sử dụng; việc một provider xuất hiện trong danh sách Micrometer không tự động có nghĩa Spring Boot sẽ auto-bind nó trong mọi phiên bản.

Các binder kế thừa mô hình chung từ `CacheMeterBinder`. Binder đọc thống kê từ cache provider và đưa các giá trị tích lũy vào registry. Một số giá trị có thể không được provider hỗ trợ; khi đó meter tương ứng có thể không được tạo hoặc không có số liệu hữu ích.

### Ví dụ với Caffeine

Caffeine cần bật thống kê trước khi tạo cache. Nếu bỏ `recordStats()`, các số liệu hit/miss có thể không được ghi nhận và Micrometer không thể cung cấp thống kê đúng:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.cache.CaffeineCacheMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class CacheMetricsDemo {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();

        Cache<String, String> cache = Caffeine.newBuilder()
            .maximumSize(10_000)
            .recordStats()
            .build();

        try {
            CaffeineCacheMetrics.monitor(
                registry,
                cache,
                "products"
            );

            cache.getIfPresent("p-100"); // miss
            cache.put("p-100", "Keyboard");
            cache.getIfPresent("p-100"); // hit
            cache.getIfPresent("p-404"); // miss

            System.out.println(
                "Hit count: "
                    + registry.get("cache.gets")
                        .tag("cache", "products")
                        .tag("result", "hit")
                        .functionCounter()
                        .count()
            );

            System.out.println(
                "Miss count: "
                    + registry.get("cache.gets")
                        .tag("cache", "products")
                        .tag("result", "miss")
                        .functionCounter()
                        .count()
            );

            System.out.println(
                "Size: "
                    + registry.get("cache.size")
                        .tag("cache", "products")
                        .gauge()
                        .value()
            );
        } finally {
            registry.close();
        }
    }
}
~~~

`CaffeineCacheMetrics.monitor(...)` đăng ký meter cho cache hiện có và trả lại chính cache đó. Phương thức không bọc cache bằng proxy và không thay đổi cách ứng dụng gọi cache. Binder đọc thống kê do Caffeine cung cấp.

Trong ví dụ, hai lần lookup đầu tiên là miss và lần lookup sau khi put là hit. Caffeine thống kê thao tác dựa trên API được gọi; nếu ứng dụng sử dụng loading cache, async cache hoặc các phương thức khác, hãy xác nhận chính xác cách provider phân loại một lần lookup.

Nếu muốn tạo binder riêng rồi gọi `bindTo(registry)`, có thể dùng constructor của `CaffeineCacheMetrics`. Phương thức tĩnh `monitor` thường ngắn gọn hơn khi chỉ cần đăng ký một cache.

### CaffeineStatsCounter

Micrometer còn cung cấp `CaffeineStatsCounter` như một lựa chọn để gắn thống kê trực tiếp vào Caffeine `StatsCounter`. Cách này hữu ích khi muốn dùng cơ chế thống kê của Caffeine với registry ngay từ lúc xây cache. Chọn một cách instrumentation rõ ràng để tránh cùng một cache bị đăng ký meter hai lần.

## Dung lượng cache: size không đồng nghĩa với bộ nhớ byte

`cache.size` thường biểu diễn số entry đang có trong cache. Nó không mặc định cho biết số byte heap mà cache chiếm dụng.

Ví dụ, hai cache cùng có 10.000 entry nhưng kích thước value có thể rất khác nhau. Cache chứa mã quốc gia và cache chứa object kết quả tìm kiếm lớn không thể so sánh mức tiêu thụ bộ nhớ chỉ bằng số entry.

| Số đo | Ý nghĩa |
|---|---|
| Entry count | Số phần tử đang được cache giữ |
| Maximum size | Giới hạn số entry theo cấu hình, nếu provider dùng giới hạn này |
| Weighted size | Tổng trọng số entry theo chính sách provider, nếu có |
| Heap/storage bytes | Dung lượng bộ nhớ hoặc storage thực tế; cần provider metric riêng hoặc công cụ khác |

Với Caffeine, `estimatedSize()` trả về số entry ước lượng. Việc lấy size có thể có tính chất gần đúng tùy implementation và thời điểm cập nhật. Với một số distributed cache hoặc JCache implementation, size có thể không được hỗ trợ hoặc không có ý nghĩa tương đương giữa các provider.

Không diễn giải gauge không tồn tại hoặc luôn bằng 0 là cache chắc chắn rỗng. Hãy kiểm tra tài liệu provider và dữ liệu thực tế trước khi dùng size làm alert.

### So sánh size với capacity

Nếu cache có giới hạn `maximumSize=10_000` và `cache.size` hiện khoảng 9.500, cache đang gần giới hạn entry. Tuy nhiên, chỉ có thể tính phần trăm sử dụng khi biết capacity thực tế và size có cùng ngữ nghĩa:

\[
\text{capacity utilization} =
\frac{\text{current entries}}{\text{maximum entries}}\times 100\%
\]

Không áp dụng công thức này cho cache giới hạn theo weight nếu gauge size chỉ đếm entry. Cũng không áp dụng cho cache không có giới hạn cứng.

## Eviction và các kiểu loại bỏ entry

Eviction xảy ra khi cache tự loại bỏ entry theo chính sách quản lý dung lượng hoặc thuật toán của provider. Ví dụ, Caffeine có thể loại bỏ entry khi vượt maximum size/weight hoặc khi chính sách expiration yêu cầu loại bỏ entry hết hạn trong quá trình bảo trì.

Cần phân biệt các hoạt động:

- **Eviction:** cache tự loại bỏ entry theo chính sách quản lý.
- **Expiration:** entry hết thời hạn cấu hình; provider có thể loại bỏ ngay hoặc loại bỏ khi hoạt động bảo trì diễn ra.
- **Invalidation:** ứng dụng chủ động vô hiệu hóa một key hoặc một nhóm key.
- **Removal:** thao tác xóa do ứng dụng hoặc API cache yêu cầu.

Không phải provider nào cũng tính các hoạt động này vào cùng một thống kê. `cache.evictions` không nhất thiết bằng tổng số entry bị xóa vì mọi nguyên nhân. Nếu cần phân biệt expiration, invalidation và removal, hãy dùng metric riêng của provider hoặc instrumentation nghiệp vụ phù hợp.

Eviction count thường là bộ đếm tích lũy. Tốc độ eviction trong một khoảng giúp nhận diện thay đổi hành vi:

- Eviction tăng cùng size chạm capacity và miss ratio tăng: working set có thể lớn hơn cache.
- Eviction tăng nhưng hit ratio vẫn cao: cache có thể đang luân chuyển entry ít được dùng mà không ảnh hưởng nhiều đến workload.
- Eviction tăng cùng load duration hoặc backend latency: nhiều request có thể phải tải lại dữ liệu.
- Eviction tăng đột ngột sau deploy: kiểm tra thay đổi maximum size, expiration, key distribution hoặc lưu lượng.

Eviction cao không tự động có nghĩa cấu hình sai. Một cache bounded cần eviction để giữ giới hạn dung lượng. Hãy đánh giá eviction cùng hit/miss, size, load latency và chi phí truy vấn nguồn.

## Đọc các metric trong Spring Boot

Khi dùng Spring Boot Actuator với cache provider được hỗ trợ, auto-configuration có thể tự đăng ký metrics cho các cache đã tồn tại lúc ứng dụng khởi động. Các metric được chuẩn hóa ở mức cơ bản và có thể bổ sung thống kê riêng theo provider.

Ví dụ cấu hình Spring Cache dùng Caffeine:

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names: products, product-details
    caffeine:
      spec: maximumSize=10000,expireAfterWrite=10m,recordStats
~~~

`recordStats` trong Caffeine spec bật thống kê để binder có thể đọc hit/miss. `cache-names` khai báo các cache được tạo sẵn; auto-configuration có thể phát hiện và bind chúng trong quá trình khởi động.

Một service có thể sử dụng Spring Cache abstraction:

~~~java
@Service
public class ProductService {

    @Cacheable(cacheNames = "products", key = "#productId")
    public Product findProduct(String productId) {
        return productRepository.findById(productId)
            .orElseThrow();
    }
}
~~~

Khi phương thức được gọi với cùng key, Spring Cache sẽ kiểm tra cache theo cấu hình. Binder quan sát thống kê của cache provider; nó không cần sửa từng phương thức có annotation.

### Cache tạo động sau khi khởi động

Spring Boot thường bind các cache có thể phát hiện khi ứng dụng khởi động. Cache được tạo động hoặc tạo bằng code sau giai đoạn auto-configuration có thể cần đăng ký tường minh.

Spring Boot cung cấp `CacheMetricsRegistrar` để bind cache tương thích vào registry. API vẫn là `bindCacheToRegistry(cache, tags...)`, nhưng package có thể thay đổi theo major version của Spring Boot. Ví dụ:

~~~java
boolean bound = cacheMetricsRegistrar.bindCacheToRegistry(
    cache,
    Tag.of("tier", "runtime")
);
~~~

Giá trị trả về cho biết cache có được hỗ trợ và bind thành công hay không. Hãy dùng đúng package import theo phiên bản Spring Boot của dự án. Với cache provider không có binder tương ứng, cần tích hợp binder của Micrometer hoặc viết instrumentation riêng.

## Kiểm tra cache metrics qua Actuator

Endpoint metrics của Spring Boot hữu ích để chẩn đoán meter đang được đăng ký. Ví dụ:

~~~bash
curl -s http://localhost:8080/actuator/metrics/cache.gets
~~~

Response cung cấp tên metric, mô tả, measurement và các tag có thể dùng để drill down. Kiểm tra danh sách tag trước khi truy vấn một cache cụ thể; tag key có thể là `cache`, `name`, `cacheManager` hoặc khác tùy cấu hình/provider.

Ví dụ truy vấn theo tag sau khi xác nhận key thực tế:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/cache.gets?tag=result:hit"
~~~

Có thể dùng endpoint caches để xem cache manager và tên cache:

~~~bash
curl -s http://localhost:8080/actuator/caches
~~~

Endpoint metrics và caches phục vụ chẩn đoán ứng dụng. Trong production, hệ thống giám sát nên thu thập từ registry export như Prometheus hoặc OTLP thay vì scrape endpoint chẩn đoán này làm backend metrics.

## Tính hit ratio và miss ratio trong Prometheus

Giả sử cache binder export meter `cache.gets` thành counter `cache_gets_total`, với tag `result=hit` hoặc `result=miss`. Hit ratio trong năm phút:

~~~promql
sum by (cache) (
  rate(cache_gets_total{result="hit"}[5m])
)
/
sum by (cache) (
  rate(cache_gets_total{result=~"hit|miss"}[5m])
)
~~~

Miss ratio:

~~~promql
sum by (cache) (
  rate(cache_gets_total{result="miss"}[5m])
)
/
sum by (cache) (
  rate(cache_gets_total{result=~"hit|miss"}[5m])
)
~~~

Tên label `cache` chỉ là ví dụ. Với Spring Boot hoặc provider khác, label có thể mang tên khác; hãy thay theo output thực tế của endpoint và backend.

Dùng `rate` để tính tốc độ tăng của counter trong cửa sổ, sau đó chia tốc độ hit cho tổng tốc độ lookup. Điều này cho hit ratio của khoảng gần đây, thay vì tỷ lệ tích lũy từ lúc ứng dụng khởi động.

Khi không có lookup trong cửa sổ, mẫu số bằng 0 và biểu thức có thể không tạo giá trị hữu ích. Không nên diễn giải no traffic là hit ratio 0% hoặc 100%. Dashboard có thể hiển thị no data; alert cần xử lý trường hợp không có hoạt động riêng với trường hợp miss ratio cao.

### Đếm tốc độ eviction

Tốc độ eviction theo cache:

~~~promql
sum by (cache) (
  rate(cache_evictions_total[5m])
)
~~~

Kết quả biểu thị số entry bị eviction mỗi giây. Có thể so sánh với tốc độ lookup hoặc put, nhưng cần xem xét semantics của provider và chính sách cache.

### Theo dõi size

Nếu provider export `cache.size` thành gauge `cache_size`:

~~~promql
cache_size
~~~

Khi muốn so sánh với capacity cố định 10.000 entry:

~~~promql
cache_size / 10000
~~~

Biểu thức chỉ phù hợp khi size thực sự là số entry và capacity được cấu hình là 10.000 cho cache tương ứng. Nếu có nhiều cache với capacity khác nhau, hãy dùng metric/configuration riêng để tránh áp một hằng số sai cho tất cả.

## Dashboard và cảnh báo có ý nghĩa

Một dashboard cache nên hiển thị các đại lượng có thể giải thích cùng nhau:

| Panel | Metric hoặc phép tính | Câu hỏi |
|---|---|---|
| Hit ratio | Hit rate / total lookup rate | Cache có phục vụ lại dữ liệu hiệu quả không? |
| Miss rate | Miss rate / total lookup rate | Tần suất phải tải dữ liệu từ nguồn là bao nhiêu? |
| Lookup throughput | Rate của cache.gets | Cache đang nhận bao nhiêu lookup? |
| Current size | cache.size | Cache đang giữ bao nhiêu entry? |
| Eviction rate | Rate của cache.evictions | Entry đang bị loại bỏ nhanh đến mức nào? |
| Load duration/failure | Metric riêng provider | Miss có làm request chậm hoặc load thất bại không? |

Không có một ngưỡng hit ratio phù hợp cho mọi cache. Cache chứa dữ liệu tham chiếu ổn định có thể kỳ vọng hit ratio cao; cache lưu kết quả truy vấn theo key duy nhất hoặc dữ liệu ngắn hạn có thể có hit ratio thấp mà vẫn đúng thiết kế.

Có thể cân nhắc cảnh báo khi:

- Miss ratio tăng vượt ngưỡng trong một khoảng có đủ traffic.
- Eviction rate tăng đột biến đồng thời với miss rate hoặc load latency.
- Size liên tục ở sát capacity trong khi workload vẫn tăng.
- Load failure tăng hoặc load duration vượt mục tiêu.
- Metrics cache biến mất khỏi backend, cho thấy binder/provider hoặc pipeline thu thập có vấn đề.

Nên ưu tiên cảnh báo miss ratio cao hơn hit ratio thấp khi muốn phát hiện cache làm tăng tải nguồn. Tuy nhiên, cả hai cần xử lý trường hợp không có traffic. Một cache ít được dùng không nên phát cảnh báo hiệu quả chỉ vì hit ratio không xác định.

## Cardinality và tag của cache

Tên cache là chiều phân tích hữu ích và thường có số lượng hữu hạn. Các tag bổ sung nên mô tả vai trò hoặc loại cache, chẳng hạn `tier=local` hoặc `purpose=product-catalog`, nếu các giá trị được kiểm soát.

Không gắn các dữ liệu sau vào tag:

- Cache key.
- User ID hoặc session ID.
- Request ID.
- Product ID hoặc order ID.
- URL hoặc chuỗi truy vấn động.

Mỗi giá trị tag mới có thể tạo một meter ID/time series mới. Cache key thường có số lượng rất lớn; đưa key vào tag sẽ làm cardinality tăng nhanh và có thể làm lộ dữ liệu nghiệp vụ.

Khi có nhiều CacheManager, giữ tag nhận diện manager để phân biệt cache cùng tên. Trước khi thêm tag mới, xác định câu hỏi dashboard cần trả lời và ước lượng số tổ hợp.

## Giới hạn và khác biệt giữa cache provider

Không nên giả định mọi provider đều cung cấp cùng một bộ thống kê:

| Thống kê | Khả năng hỗ trợ |
|---|---|
| Hit count | Nhiều provider hỗ trợ; semantics phụ thuộc thao tác lookup |
| Miss count | Có thể không có ở một số distributed cache |
| Put count | Một số provider chỉ đếm entry được thêm qua loading mechanism; manual put có thể không được tính |
| Eviction count | Có thể không được provider hỗ trợ hoặc không phân biệt mọi nguyên nhân loại bỏ |
| Size | Có thể là ước lượng, không hỗ trợ hoặc mang semantics riêng |
| Load duration | Thường là metric riêng của provider có loading statistics |
| Eviction weight | Chỉ có ý nghĩa với provider/chính sách dùng trọng số |

Ví dụ, tài liệu `CacheMeterBinder` ghi nhận `missCount`, `evictionCount` và `size` có thể không có nếu implementation không cung cấp. Với Guava và Caffeine, put count không nhất thiết đếm các lệnh manual put; nó phản ánh entry được thêm qua cơ chế load theo semantics của binder/provider.

Một số distributed cache không thể biết chính xác mọi miss hoặc size trên toàn cụm mà không tạo thêm chi phí. Nếu metric bị thiếu, hãy xác định provider có hỗ trợ hay không trước khi coi đó là lỗi instrumentation.

## Kiểm thử instrumentation với SimpleMeterRegistry

Có thể kiểm thử cache binder mà không cần backend:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.cache.CaffeineCacheMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class CacheMetricsTest {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();

        Cache<String, String> cache = Caffeine.newBuilder()
            .maximumSize(10)
            .recordStats()
            .build();

        try {
            CaffeineCacheMetrics.monitor(registry, cache, "products");

            cache.getIfPresent("p-1"); // miss
            cache.put("p-1", "Keyboard");
            cache.getIfPresent("p-1"); // hit
            cache.getIfPresent("p-2"); // miss

            double hits = registry.get("cache.gets")
                .tag("cache", "products")
                .tag("result", "hit")
                .functionCounter()
                .count();

            double misses = registry.get("cache.gets")
                .tag("cache", "products")
                .tag("result", "miss")
                .functionCounter()
                .count();

            if (hits != 1.0) {
                throw new AssertionError("Expected one hit but got " + hits);
            }
            if (misses != 2.0) {
                throw new AssertionError("Expected two misses but got " + misses);
            }
        } finally {
            registry.close();
        }
    }
}
~~~

Kiểm thử này xác nhận binder đọc được hit/miss statistics từ Caffeine sau khi bật `recordStats()`. Nếu dùng JUnit, chuyển các điều kiện assert sang assertion của framework để test runner quản lý kết quả.

Để kiểm tra eviction, tạo cache có maximum size nhỏ, chèn nhiều key và gọi thao tác maintenance phù hợp với provider trước khi đọc eviction count. Eviction có thể xảy ra bất đồng bộ hoặc theo maintenance cycle; không nên giả định count thay đổi đồng bộ ngay tại câu lệnh put.

`SimpleMeterRegistry` kiểm tra logic instrumentation tại process. Cần kiểm thử tích hợp riêng để xác nhận tên metric, tag, đơn vị và dữ liệu export trên Prometheus hoặc OTLP.

## Quy trình điều tra khi cache hoạt động kém

Khi hit ratio giảm hoặc eviction tăng, điều tra theo thứ tự:

1. **Xác minh dữ liệu:** cache.gets, size và eviction metrics có hiện diện, cập nhật và mang đúng tag không?
2. **Kiểm tra lưu lượng:** lookup rate có tăng hoặc thay đổi phân bố theo cache không?
3. **Kiểm tra miss:** miss tăng ở cache nào, vào thời điểm nào và có làm backend/database tăng tải không?
4. **Kiểm tra size/capacity:** cache có chạm maximum size/weight không? Size gauge có đúng semantics không?
5. **Kiểm tra eviction:** eviction do giới hạn dung lượng, expiration hay thao tác khác theo provider?
6. **Kiểm tra load:** load duration và failure có tăng không?
7. **Đối chiếu cấu hình:** TTL, maximum size, maximum weight, refresh policy và key distribution có thay đổi không?
8. **Đánh giá tính đúng đắn:** invalidation có đảm bảo dữ liệu mới không? Hit ratio cao không chứng minh dữ liệu luôn fresh.

Không tăng cache capacity chỉ vì eviction tăng. Nếu working set quá lớn, tăng capacity có thể tiêu tốn bộ nhớ mà không cải thiện đáng kể hit ratio. Hãy đo tác động lên backend load, latency, heap và độ mới dữ liệu trước khi điều chỉnh.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hit/miss luôn bằng 0 | Caffeine chưa bật `recordStats()` hoặc provider không cung cấp statistics | Bật thống kê trước khi tạo cache; kiểm tra hỗ trợ provider |
| Không thấy cache metrics | Cache không được bind, tạo sau startup hoặc provider không tương thích | Kiểm tra auto-configuration và đăng ký tường minh |
| Size bằng 0 nhưng cache có dữ liệu | Provider không hỗ trợ size hoặc metric có semantics khác | Kiểm tra tài liệu provider và API native |
| Put count thấp hơn số lệnh put | Binder chỉ đếm entry theo loading mechanism | Đối chiếu semantics của provider |
| Eviction tăng nhưng hit ratio ổn định | Cache đang luân chuyển entry không còn hữu ích | Đọc cùng miss rate, load latency và capacity |
| Hit ratio không có dữ liệu | Không có lookup trong cửa sổ hoặc thiếu hit/miss meter | Phân biệt no traffic với lỗi thu thập |
| Dashboard có nhiều series | Tag động hoặc nhiều tên cache không kiểm soát | Dùng cache name và tag hữu hạn |
| Hit ratio cao nhưng dữ liệu cũ | Invalidation/expiration chưa đúng | Theo dõi freshness và kiểm thử tính đúng đắn riêng |

## Ghi nhớ

- Cache metrics giúp quan sát hiệu quả lookup, số entry hiện tại và tốc độ eviction.
- `cache.gets` thường có tag `result=hit` hoặc `result=miss`; tính ratio bằng rate trong cùng cửa sổ.
- `cache.size` là số entry hoặc ước lượng, không mặc định là số byte bộ nhớ.
- `cache.evictions` là thống kê eviction theo provider, không nhất thiết gồm mọi expiration, invalidation hoặc remove.
- Với Caffeine, bật `recordStats()` trước khi tạo cache.
- `CaffeineCacheMetrics.monitor(...)` đăng ký meter cho cache hiện có mà không bọc cache.
- Spring Boot tự bind các cache tương thích được phát hiện khi startup; cache tạo động có thể cần `CacheMetricsRegistrar`.
- Put, miss, size và eviction statistics có thể khác nhau hoặc không được hỗ trợ giữa provider.
- Không dùng cache key, user ID hoặc request ID làm tag.
- Đọc hit/miss, size, eviction, load latency và backend load cùng nhau trước khi thay đổi capacity hoặc TTL.

Khi kết hợp hit ratio, size và eviction với lưu lượng lookup cùng thời gian tải dữ liệu, nhóm có thể đánh giá cache đang giảm tải cho hệ thống phía sau hay chỉ chuyển chi phí sang bộ nhớ và quá trình làm mới entry. Những số đo này giúp đưa ra quyết định cấu hình dựa trên hành vi thực tế của cache provider.

## Tài liệu tham khảo

- [Micrometer: Cache Instrumentations](https://docs.micrometer.io/micrometer/reference/reference/cache.html) — binder cho Caffeine, Ehcache, Guava, Hazelcast và JCache; cách tính hit ratio theo khoảng thời gian.
- [Micrometer Core: CacheMeterBinder API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/binder/cache/CacheMeterBinder.html) — thống kê chung, khả năng không hỗ trợ size/miss/eviction và semantics của put count.
- [Micrometer Core: CaffeineCacheMetrics API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/binder/cache/CaffeineCacheMetrics.html) — đăng ký metrics cho Caffeine và yêu cầu recordStats().
- [Spring Boot: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — cache auto-configuration, provider được hỗ trợ, cache manager tags và đăng ký cache động.
- [Spring Boot: Metrics endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html) — xem tên meter, measurement, base unit và các tag khả dụng.

