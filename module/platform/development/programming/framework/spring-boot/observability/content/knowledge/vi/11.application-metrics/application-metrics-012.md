# Cache metrics trong Spring Boot: đo hit, miss, eviction và hiệu quả cache

Một ứng dụng Spring Boot có thể dùng cache để giảm số lần truy cập cơ sở dữ liệu hoặc gọi dịch vụ bên ngoài. Tuy nhiên, việc thêm `@Cacheable` chưa đủ để kết luận cache đang hiệu quả: tỷ lệ cache hit có thể thấp, cache bị đẩy dữ liệu quá thường xuyên, hoặc dữ liệu cũ khiến người dùng nhìn thấy kết quả sai. **Cache metrics** giúp phát hiện những hiện tượng đó bằng dữ liệu thay vì phỏng đoán.

Trong chương **Application metrics** của module **SPRING_BOOT_OBSERVABILITY**, bài học này tập trung vào cách thu thập và diễn giải chỉ số cache trong Spring Boot thông qua Micrometer và Actuator; sau đó liên kết kết quả với **Micrometer Observation, metrics, logs và distributed tracing** để điều tra lỗi, độ trễ và hành vi ứng dụng. Những vấn đề như tag/cardinality, exporter, sampling và propagation cũng có tác động trực tiếp đến cách xác minh kết luận trong production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cache hit, miss, put, eviction, size và các giới hạn khi diễn giải từng chỉ số.
2. Kích hoạt cache metrics cho Spring Boot với một provider cụ thể, ví dụ **Caffeine**.
3. Xác minh metrics qua `/actuator/metrics` và `/actuator/prometheus`.
4. Viết PromQL tính hit ratio, miss ratio, tốc độ eviction và quan sát dung lượng cache.
5. Phân biệt cache metrics với thời gian xử lý nghiệp vụ, lỗi HTTP và số liệu tracing.
6. Kiểm soát tên cache, labels/cardinality, dữ liệu nhạy cảm và tính nhất quán của cache.
7. Thiết kế kiểm thử và quy trình điều tra khi cache có metrics bất thường hoặc chưa xuất dữ liệu.

## 1. Cache giải quyết bài toán gì?

Giả sử một endpoint `GET /products/{sku}` lấy thông tin sản phẩm. Nếu mỗi request đều truy vấn database hoặc gọi `catalog-service`, hệ thống có thể tốn thời gian và tài nguyên ngay cả khi nhiều người cùng yêu cầu một sản phẩm.

Một cache cho phép lưu một kết quả tạm thời:

~~~mermaid
flowchart TD
    Request["GET /products/{sku}"] --> Lookup{"Có dữ liệu hợp lệ trong cache?"}
    Lookup -- "Hit" --> Cached["Trả kết quả từ cache"]
    Lookup -- "Miss" --> Backend["Đọc DB / catalog-service"]
    Backend --> Store["Lưu vào cache nếu chính sách cho phép"]
    Store --> Result["Trả kết quả"]
    Cached --> Result
    Lookup -. "Metrics hit/miss" .-> Meter["Micrometer cache.gets"]
    Backend -. "Quan sát dependency" .-> Observe["Observation / trace / logs"]
~~~

**Cache hit** là lần tra cứu tìm thấy giá trị dùng được tại cache. **Cache miss** là lần tra cứu không có dữ liệu dùng được, khiến hệ thống phải tìm hoặc tính từ nguồn khác. Nhưng định nghĩa chi tiết của hit/miss phụ thuộc provider và API tra cứu: một lần gọi `put` trực tiếp không nhất thiết đồng nghĩa một lần miss; nhiều request đồng thời có thể có hành vi nạp dữ liệu khác nhau.

Cache luôn có các đánh đổi:

- **Hiệu năng:** tiết kiệm thời gian đọc nguồn gốc, nhưng có chi phí bộ nhớ, lookup và quản lý.
- **Tính mới của dữ liệu:** cache có thể trả kết quả đã lỗi thời nếu TTL và invalidation không đúng.
- **Tài nguyên:** cache quá lớn có thể tăng áp lực heap/GC hoặc chi phí dịch vụ cache ngoài.
- **Độ tin cậy:** cache miss hàng loạt có thể làm quá tải database hoặc downstream.

Vì thế cần dùng metrics để **đo hiệu quả và chi phí**, không chỉ theo dõi một phần trăm hit.

## 2. Những chỉ số cache cốt lõi

Micrometer chuẩn hóa một số tên meter cho các provider được hỗ trợ. Các tên thường gặp gồm `cache.gets`, `cache.puts`, `cache.evictions` và `cache.size`. Số liệu nào khả dụng còn phụ thuộc thư viện cache, cấu hình thống kê và phiên bản tích hợp.

| Meter / khái niệm | Loại dữ liệu | Câu hỏi trả lời | Điều cần chú ý |
| --- | --- | --- | --- |
| `cache.gets` với `result=hit` | Counter/tổng số lần tra cứu hit | Cache phục vụ bao nhiêu lần đọc? | Số lần tích lũy, không phải tốc độ hiện tại |
| `cache.gets` với `result=miss` | Counter/tổng số lần tra cứu miss | Có bao nhiêu lần phải đọc nguồn khác? | Không đồng nghĩa số lần truy cập DB trong mọi provider |
| `cache.puts` | Counter nếu provider hỗ trợ | Có bao nhiêu thao tác ghi vào cache? | Ý nghĩa put có thể khác theo provider |
| `cache.evictions` | Counter nếu provider hỗ trợ | Có bao nhiêu entry bị loại theo cơ chế eviction? | Không mặc nhiên bao gồm mọi lần invalidation thủ công |
| `cache.size` | Gauge nếu provider hỗ trợ | Hiện tại khoảng bao nhiêu entry? | Có thể là ước lượng/chụp thời điểm, không phải tổng lượt truy cập |
| Hit ratio | Chỉ số suy ra từ hits và misses | Tỷ lệ tra cứu được phục vụ từ cache? | Phải dùng cùng khoảng thời gian và phạm vi |
| Miss ratio | Chỉ số suy ra | Tỷ lệ tra cứu không có dữ liệu ở cache? | Phải đọc cùng traffic, cache, instance |

### 2.1. Hit ratio và miss ratio

Trong một cửa sổ đo, gọi số lần hit là `H` và miss là `M`, với `H + M > 0`:

\[
\text{Hit ratio} = \frac{H}{H + M}
\qquad
\text{Miss ratio} = \frac{M}{H + M}
\]

Ví dụ trong 5 phút:

| Kết quả | Số lần |
| --- | ---: |
| Hit | 900 |
| Miss | 100 |
| Tổng lookup | 1.000 |
| Hit ratio | 90% |
| Miss ratio | 10% |

Trong ví dụ, **90% là tỷ lệ các lần tra cứu cache tìm thấy dữ liệu**, không phải tỷ lệ request HTTP thành công. Một request có thể tra cache nhiều lần hoặc hoàn toàn không tra cache; một cache hit cũng không bảo đảm response đúng về mặt nghiệp vụ.

### 2.2. Eviction khác explicit invalidation

**Eviction** thường nói đến entry bị loại vì giới hạn dung lượng, chính sách hết hạn hay quy tắc quản lý cụ thể của provider. **Invalidation** là hành động xóa/cập nhật dữ liệu vì ứng dụng biết dữ liệu đã thay đổi, ví dụ `@CacheEvict` sau khi sửa sản phẩm.

Không được mặc nhiên hiểu rằng mọi `@CacheEvict` đều tăng `cache.evictions`. Provider có thể phân biệt eviction theo dung lượng với removal do gọi API xóa, thay thế giá trị hoặc expiry. Trước khi viết alert dựa trên eviction, hãy kiểm tra chính xác semantics của provider đang dùng.

### 2.3. Cache size không phải số bytes bộ nhớ

`cache.size` thường là **số entry**, không phải kích thước heap tính bằng byte. Với Caffeine, kích thước có thể được báo bằng phép ước lượng. Một cache có 10.000 entry nhỏ và một cache có 10.000 entry chứa object lớn không có chi phí bộ nhớ bằng nhau.

Nếu lo heap và GC, hãy kết hợp cache size với `jvm.memory.used`, `jvm.gc.pause`, giới hạn cache và dữ liệu profiling phù hợp.

## 3. Spring Boot thu thập cache metrics bằng cách nào?

Spring Boot Actuator tích hợp Micrometer và có thể tự động instrument các cache khả dụng từ `CacheManager` khi provider được hỗ trợ. Với một cache cụ thể, quá trình thường gồm:

1. Ứng dụng khởi tạo `CacheManager` và những cache đã khai báo.
2. Spring Boot metrics auto-configuration nhận diện các cache mà nó hỗ trợ.
3. Một binder/provider phù hợp gắn meter cache vào `MeterRegistry`.
4. Cache provider cập nhật thống kê trong lúc ứng dụng thực thi.
5. Registry thể hiện meter tại endpoint Actuator hoặc xuất sang backend metrics.

~~~mermaid
flowchart LR
    App["@Cacheable / CacheManager"] --> Provider["Caffeine, JCache, ..."]
    Provider --> Stats["Provider statistics"]
    Stats --> Binder["Cache meter binder"]
    Binder --> Registry["MeterRegistry"]
    Registry --> Actuator["/actuator/metrics"]
    Registry --> Prom["/actuator/prometheus"]
    Prom --> Backend["Prometheus / Grafana"]
    App --> Observation["Micrometer Observation"]
    Observation --> Trace["Tracing / logs correlation"]
~~~

**Phụ thuộc provider:** không phải mọi triển khai `Cache` đều cung cấp thống kê hit/miss/eviction giống nhau. Có provider phải bật statistics, có provider chỉ hỗ trợ một phần meter, và cache đặt ở hệ thống phân tán có thể có thống kê local khác với thống kê toàn cụm. Do đó, không chỉ thêm Actuator rồi giả định toàn bộ số liệu đều tồn tại.

### 3.1. Cache khởi tạo sau startup

Spring Boot thường tự bind các cache **đã có tại thời điểm khởi động**. Với cache được tạo động sau đó (ví dụ tên cache phát sinh trong runtime), nó có thể **không tự có metrics**. Nếu cần quan sát cache mới, xem cơ chế đăng ký thông qua `CacheMetricsRegistrar` của Spring Boot hoặc binder provider tương ứng, và xác minh đúng API của phiên bản dự án.

Tốt hơn, **khai báo danh sách tên cache ổn định từ đầu** khi thiết kế nghiệp vụ. Tạo một cache riêng cho mỗi tenant, người dùng hoặc request có thể gây bùng nổ tên meter/label và rất khó quản lý.

### 3.2. Nhãn thường đi kèm

Cache metrics có thể có nhãn như tên cache và tên `CacheManager`. Thường gặp các nhãn liên quan đến `cache`, `cacheManager` và `result` (hit/miss). Những nhãn này giúp xác định cache nào có vấn đề, nhưng **tên và cách chuyển đổi nhãn khi xuất ra backend phụ thuộc phiên bản và registry**.

Ví dụ, nếu `catalogBySku` và `permissionsByRole` cùng dùng một `CacheManager`, việc tổng hợp tất cả hit/miss của hai cache thành một tỷ lệ chung có thể che giấu sự cố của từng cache. Khi cần điều tra, hãy lọc theo **cache và cache manager** trước.

## 4. Ví dụ Spring Boot với Caffeine

Caffeine là một provider cache in-process thường được dùng cùng Spring Cache abstraction. Trong ví dụ này, ứng dụng có cache tên `catalogBySku` để lưu thông tin sản phẩm theo SKU. Mỗi entry có TTL 10 phút và cache giới hạn 10.000 entry.

### 4.1. Dependencies

Ví dụ Gradle với Spring Boot 3.x và dependency management tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'com.github.ben-manes.caffeine:caffeine'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-cache` cung cấp cơ chế cache abstraction và thành phần cần thiết để dùng các annotation như `@Cacheable`; Caffeine là cache provider. Actuator kết hợp Micrometer làm nhiệm vụ thu thập metrics, còn Prometheus registry làm dữ liệu có thể được scrape.

### 4.2. Khai báo cache với recordStats()

Trong `CacheConfiguration.java`:

~~~java
package com.example.catalog;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("catalogBySku");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(10))
                .recordStats());
        return manager;
    }
}
~~~

**Điểm then chốt là `recordStats()`.** Với Caffeine, statistics recording phải được kích hoạt để các thống kê như hit/miss có ý nghĩa. Nếu bỏ `recordStats()`, cache vẫn có thể hoạt động và trả dữ liệu, nhưng một số thống kê có thể không cập nhật như kỳ vọng.

`new CaffeineCacheManager("catalogBySku")` khai báo một tên cache từ đầu để được khởi tạo và có cơ hội được Actuator bind ở startup. `maximumSize` giới hạn số entry; `expireAfterWrite` quy định thời gian hết hạn tính từ khi ghi, **không tự bảo đảm dữ liệu nghiệp vụ luôn nhất quán** sau khi nguồn gốc thay đổi.

### 4.3. Dùng @Cacheable trong một service

Trong `CatalogService.java`:

~~~java
package com.example.catalog;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final CatalogBackend backend;

    public CatalogService(CatalogBackend backend) {
        this.backend = backend;
    }

    @Cacheable(cacheNames = "catalogBySku", key = "#p0")
    public ProductView findProduct(String sku) {
        return backend.fetch(sku);
    }
}

interface CatalogBackend {
    ProductView fetch(String sku);
}

record ProductView(String sku, String name) {}
~~~

`CatalogBackend` là một adapter do ứng dụng triển khai để đọc dữ liệu từ database hoặc `catalog-service`; `ProductView` là record minh họa. Tham số `#p0` tham chiếu tham số đầu tiên của method, tránh phụ thuộc tên biến đầu vào có được giữ trong bytecode hay không.

Một request gọi `findProduct("SKU-1")` lần đầu thường phải lấy từ backend (**miss**) và ghi vào cache; lần gọi tiếp theo với cùng key, trong lúc entry còn hợp lệ, có thể được phục vụ từ cache (**hit**).

**Lưu ý proxy:** annotation caching của Spring thường thực thi qua AOP proxy. Nếu một method trong cùng object gọi trực tiếp `this.findProduct(...)`, lời gọi đó có thể **bỏ qua proxy** và không đi qua cơ chế `@Cacheable`. Điều này làm test hoặc metrics không như kỳ vọng dù annotation đã được thêm.

### 4.4. Invalidation và dữ liệu cũ

Nếu thông tin sản phẩm thay đổi, có thể cần invalidation rõ ràng:

~~~java
import org.springframework.cache.annotation.CacheEvict;

@CacheEvict(cacheNames = "catalogBySku", key = "#p0")
public void invalidateProduct(String sku) {
    // Khi được gọi qua Spring proxy, cache entry cho sku sẽ bị xóa.
}
~~~

Đây là ví dụ một method riêng trong bean Spring phù hợp; không nên chép nguyên đoạn có annotation này ra ngoài class. Một thiết kế thật phải quyết định **khi nào** invalidation xảy ra, đặc biệt nếu cập nhật dữ liệu trong transaction hoặc qua nhiều service. Cache hit cao nhưng trả dữ liệu cũ là thất bại về **tính đúng đắn**, không phải thành công.

## 5. Kích hoạt và xem cache metrics trong Actuator

Trong `application.yml`, cấu hình các endpoint phục vụ môi trường thử nghiệm:

~~~yaml
spring:
  application:
    name: catalog-service

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
  metrics:
    tags:
      application: catalog-service
~~~

Khởi động ứng dụng, tạo các lần tra cứu hit/miss rồi kiểm tra:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/cache.gets
curl -s http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics/cache.gets` thường cung cấp thông tin meter theo định dạng Actuator, gồm tên meter, measurements và available tags. Ở `/actuator/prometheus`, tên metric có thể được chuyển sang snake_case và thêm hậu tố `_total` đối với counter.

Ví dụ **đầu ra giả định, giản lược** sau khi có traffic:

~~~text
cache_gets_total{application="catalog-service",cache="catalogBySku",result="hit"} 900
cache_gets_total{application="catalog-service",cache="catalogBySku",result="miss"} 100
cache_puts_total{application="catalog-service",cache="catalogBySku"} 100
cache_evictions_total{application="catalog-service",cache="catalogBySku"} 5
cache_size{application="catalog-service",cache="catalogBySku"} 95
~~~

**Không coi các dòng trên là tên/nhãn bắt buộc của mọi phiên bản**. Một registry có thể bổ sung `cacheManager`, chuyển đổi tên hoặc không có một số meter nếu provider chưa hỗ trợ. Quan sát output thật rồi mới viết query và alerts.

### 5.1. Tại sao có meter nhưng giá trị bằng 0?

- Cache chưa nhận lookup hoặc chưa có hit/miss theo cách provider tính.
- `recordStats()` chưa được bật.
- Lời gọi `@Cacheable` bị self-invocation, cache không được kích hoạt hoặc dùng nhầm bean.
- Cache khác với tên mà bạn lọc đang được sử dụng.
- Dữ liệu được nạp trực tiếp bằng `put` nhưng chưa có lần `get`.
- Cấu hình runtime hoặc provider không hỗ trợ thống kê cụ thể đó.

Một giá trị 0 là tín hiệu cần điều tra, **không đủ để kết luận cache không có tác dụng** trước khi xác minh đường đi nghiệp vụ.

### 5.2. Bảo vệ endpoint

Metrics có thể để lộ tên cache, tên service, số entry, nhãn môi trường và cấu trúc ứng dụng. Trong production, giới hạn truy cập endpoint Actuator theo mạng quản trị, cơ chế xác thực/ủy quyền hoặc cách triển khai scrape phù hợp. Không bật công khai `/actuator/prometheus` chỉ để dễ xem khi debug.

## 6. Phân tích cache bằng PromQL

Các ví dụ sau giả định Prometheus nhận các **classic counter/gauge series** với tên `cache_gets_total`, `cache_evictions_total` và `cache_size`, có label `cache="catalogBySku"` và `application="catalog-service"`. Cần sửa query theo series thực.

**Quan trọng:** vì `cache.gets` là counter tích lũy, dùng `rate(...[5m])` hoặc `increase(...[5m])` để tính tỷ lệ trong cửa sổ, không chia đơn giản hai giá trị tích lũy từ đầu process nếu muốn biết hiệu quả vừa xảy ra.

### 6.1. Hit ratio trong 5 phút

~~~promql
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result="hit"
}[5m]))
/
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result=~"hit|miss"
}[5m]))
~~~

Kết quả `0.90` có nghĩa khoảng 90% **cache lookup được quan sát** trong khoảng thời gian đó là hit. Nếu tổng số lookup gần 0 hoặc bằng 0, phép chia có thể không có kết quả hoặc không có ý nghĩa thống kê. Dashboard nên hiển thị **lookup rate** bên cạnh hit ratio để tránh diễn giải sai.

Không gộp những cache có mục đích rất khác nhau rồi kết luận “hệ thống có hit ratio 90%”. Một cache có 10 triệu hit có thể che khuất một cache quan trọng chỉ có miss.

### 6.2. Miss ratio và lookup rate

~~~promql
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result="miss"
}[5m]))
/
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result=~"hit|miss"
}[5m]))
~~~

Tốc độ lookup:

~~~promql
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result=~"hit|miss"
}[5m]))
~~~

Miss ratio cao trong thời gian **cache khởi động lạnh** có thể bình thường; miss ratio tăng đột ngột sau nhiều giờ ổn định có thể chỉ ra expiration, eviction, invalidation hoặc thay đổi phân bố key.

### 6.3. Eviction rate

~~~promql
sum(rate(cache_evictions_total{
  application="catalog-service",
  cache="catalogBySku"
}[5m]))
~~~

Đây là số sự kiện eviction trung bình mỗi giây theo cách provider đếm. Nếu đột nhiên tăng, đối chiếu với `cache.size`, hit/miss và giới hạn `maximumSize`; không kết luận nguyên nhân là thiếu bộ nhớ nếu eviction còn có thể do expiry hoặc cách ghi đè tùy provider.

### 6.4. Cache size theo instance

~~~promql
cache_size{
  application="catalog-service",
  cache="catalogBySku"
}
~~~

Với Caffeine in-process, mỗi JVM có cache riêng, nên `cache_size` theo `instance` cho biết kích thước từng bản sao. Có thể cộng các instance để ước lượng tổng số entry *được lưu trên mọi bản sao*, nhưng **không phải số key duy nhất của toàn hệ thống** vì một SKU có thể được lưu lặp trên nhiều JVM.

Nếu nhiều instance cùng đo **một cache phân tán chung**, phép cộng size có thể đếm trùng; cần hiểu phạm vi metric của provider trước khi aggregate.

### 6.5. Xem hit ratio theo từng cache

Khi có nhiều cache cùng tên label `cache` trong cùng ứng dụng, có thể phân nhóm:

~~~promql
sum by (cache) (
  rate(cache_gets_total{
    application="catalog-service", result="hit"
  }[5m])
)
/
sum by (cache) (
  rate(cache_gets_total{
    application="catalog-service", result=~"hit|miss"
  }[5m])
)
~~~

Nếu nhiều `CacheManager` có thể chứa cache trùng tên, nên giữ cả nhãn cache manager thực tế trong phép `sum by (...)` để tránh gộp nhầm. Đừng suy ra nhãn `cacheManager` tồn tại ở mọi backend: hãy kiểm tra series trước.

## 7. Hit ratio cao chưa chắc là cache tốt

Hit ratio là chỉ số hữu ích nhưng **không phải SLO toàn diện**. Những trường hợp dễ gây hiểu sai:

| Tình huống | Metrics có thể trông như thế nào | Vấn đề thật |
| --- | --- | --- |
| Cache trả dữ liệu đã cũ | Hit ratio rất cao | Tính đúng đắn hoặc invalidation sai |
| Cache hit nhưng deserialize chậm | Hit ratio cao, HTTP p95 vẫn tăng | Chi phí xử lý trong app hoặc payload lớn |
| Dữ liệu ít được dùng nhưng rất nhiều key | Hit ratio thấp | Có thể workload không phù hợp với cache |
| Khởi động lại nhiều pod | Miss ratio tăng đột ngột | Cache lạnh (cold start) |
| TTL quá ngắn | Miss/put tăng | Entry hết hạn trước khi được tái sử dụng |
| `maximumSize` quá nhỏ | Eviction và miss cùng tăng | Capacity không đủ cho working set |
| Cache phân tán chậm hoặc lỗi mạng | Hit có thể cao, latency vẫn kém | Network/serialization/backend cache |
| Cache stampede khi key hot hết hạn | Nhiều miss cùng lúc và tải DB tăng | Cần load coalescing hoặc chính sách làm mới phù hợp |

Khi đánh giá cache, hãy nhìn cả **lưu lượng, hit/miss, eviction, size, latency của request, latency nguồn dữ liệu và tỷ lệ lỗi**. Với cache có yêu cầu tính mới, cần thêm kiểm chứng freshness hoặc correctness ở tầng nghiệp vụ, không thể suy từ hit ratio.

### 7.1. Cache hit có thể giảm tải bao nhiêu?

Giả sử trong 5 phút có 10.000 lần lookup, 9.000 hit và 1.000 miss. Nếu không có cache, mỗi lookup có thể phải gọi nguồn gốc; với cache, số lần cần đọc nguồn có thể giảm đáng kể.

Tuy nhiên, **không được khẳng định đã tiết kiệm đúng 9.000 truy vấn DB** chỉ từ hit/miss. Một số request có thể gọi nhiều cache; miss có thể được gộp cùng một lần load nhờ cơ chế đồng bộ; có thao tác prefetch/refresh hoặc backend batch; và không phải mọi cache lookup đều tương ứng một truy vấn DB.

Để chứng minh tác động, đo thêm **DB query rate / downstream request rate / connection pool usage** và so sánh trước/sau theo cùng traffic.

## 8. Metrics và Micrometer Observation bổ trợ nhau ra sao?

**Cache metrics** mô tả hành vi tổng hợp của cache, còn **Micrometer Observation** có thể theo dõi thời gian một thao tác nghiệp vụ, phát sinh metrics và span khi được instrument phù hợp. Hai cơ chế có mục tiêu khác nhau.

~~~mermaid
sequenceDiagram
    participant Client
    participant Catalog as CatalogService
    participant Cache as Caffeine cache
    participant Backend as CatalogBackend
    participant Metrics as Metrics backend
    participant Trace as Trace backend
    Client->>Catalog: GET /products/SKU-1
    Catalog->>Cache: lookup SKU-1
    alt Cache hit
        Cache-->>Catalog: ProductView
    else Cache miss
        Cache->>Backend: fetch SKU-1
        Backend-->>Cache: ProductView
        Cache-->>Catalog: ProductView
    end
    Catalog-->>Client: HTTP response
    Cache-->>Metrics: hit/miss/size/eviction metrics
    Catalog-->>Trace: Observed HTTP/backend spans nếu được cấu hình
~~~

Trong một ứng dụng Spring Boot điển hình:

- **Metrics của cache provider:** giúp phân tích hiệu quả cache theo cache name và instance.
- **HTTP server metrics:** cho request rate, lỗi 4xx/5xx, thời gian xử lý và p95/p99.
- **Metrics của downstream:** cho số lần gọi DB/HTTP, thời gian chờ connection và timeout nếu được instrument.
- **Distributed tracing:** cho một đường đi cụ thể, ví dụ request miss cache rồi mất 800 ms ở database.
- **Logs:** cung cấp sự kiện lỗi hoặc việc invalidation đáng chú ý, có thể liên kết bằng trace ID/span ID.

**Không giả định** chỉ vì cache có hit/miss metrics mà mỗi cache lookup sẽ xuất hiện dưới dạng span. Provider binder chủ yếu ghi metrics; muốn xem chi tiết trong tracing cần instrumentation phù hợp, và phải cân nhắc chi phí span rất lớn nếu ghi mọi lookup nhỏ.

### 8.1. Tag và cardinality: cache key không phải metric label

Một cache nội bộ đương nhiên có thể dùng hàng nghìn SKU làm key. Điều đó **không có nghĩa** nên đưa SKU vào nhãn của `cache.gets`. Key động là dữ liệu nghiệp vụ; metric label cần tập giá trị nhỏ như `cache=catalogBySku` hoặc `result=hit|miss`.

Tránh các label như `sku`, `userId`, `sessionId`, `orderId`, `traceId` hoặc raw URL. Mỗi giá trị mới có thể tạo time series mới, tăng bộ nhớ, chi phí và khả năng lộ dữ liệu. Nếu cần điều tra một request cụ thể, ưu tiên trace ID cùng logs an toàn thay vì gắn request ID vào metrics.

### 8.2. Context propagation và sampling

Khi cache miss dẫn đến một lời gọi qua HTTP sang `catalog-service`, Spring Boot cần HTTP client/tracing instrumentation và propagation thích hợp (ví dụ W3C `traceparent`) để span hai dịch vụ nằm trong cùng trace. Với `@Async` hoặc executor, phải có cơ chế truyền ngữ cảnh tương ứng.

Sampling có thể loại bỏ phần lớn traces, nhưng **không làm mọi counter cache biến mất**: cache metrics có thể tiếp tục được thu thập độc lập. Nếu một trace không được giữ, không thể kết luận request không tra cache hoặc cache không hoạt động.

### 8.3. Exporter metrics khác exporter tracing

`/actuator/prometheus` là endpoint để Prometheus thu thập metrics theo cơ chế scrape. Một pipeline OTLP tracing riêng có thể gửi spans tới Collector và trace backend. Nếu metrics xuất được mà traces không có, cần phân biệt lỗi sampling/propagation/tracing exporter với lỗi binder cache.

Với cache nằm ở Redis hoặc hệ thống phân tán khác, thống kê từ **server metrics** có thể khác số liệu ở **client/cache abstraction**. Hãy định nghĩa rõ mỗi metric đo ở đâu và dùng nguồn server-side phù hợp khi cần đánh giá tài nguyên hoặc toàn cụm.

## 9. Kiểm thử cache metrics

Một kiểm thử có ích nên chứng minh ba điều độc lập:

1. **Hành vi cache:** lần gọi thứ hai cùng key không gọi backend thêm lần nữa khi entry còn hợp lệ.
2. **Thống kê provider:** hit/miss được cập nhật khi thực hiện lookup.
3. **Tích hợp Micrometer/Spring Boot:** metrics thực sự được bind và xuất bởi registry đang dùng.

### 9.1. Unit test statistics của Caffeine

Có thể xác minh bản thân provider mà không cần khởi động ứng dụng:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CaffeineStatisticsTest {
    @Test
    void countsOneMissAndOneHit() {
        Cache<String, String> cache = Caffeine.newBuilder()
                .recordStats()
                .build();

        String first = cache.get("SKU-1", key -> "Product A"); // Miss + load.
        String second = cache.getIfPresent("SKU-1");          // Hit.

        assertEquals("Product A", first);
        assertEquals("Product A", second);
        assertEquals(1L, cache.stats().missCount());
        assertEquals(1L, cache.stats().hitCount());
    }
}
~~~

Test này **chỉ kiểm tra thống kê Caffeine**, chưa chứng minh Spring Boot đã tạo cache đúng tên hay Micrometer đã bind meter. Hãy giữ phân biệt giữa unit test của provider và integration test với Actuator.

### 9.2. Unit test binder với SimpleMeterRegistry

Khi cần xác minh cầu nối từ Caffeine sang Micrometer, có thể dùng binder `CaffeineCacheMetrics` trên cache native:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import io.micrometer.core.instrument.binder.cache.CaffeineCacheMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CaffeineMeterBindingTest {
    @Test
    void bindsCacheGetMetrics() {
        Cache<String, String> cache = Caffeine.newBuilder()
                .recordStats()
                .build();

        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            CaffeineCacheMetrics.monitor(registry, cache, "catalogBySku");

            cache.get("SKU-1", key -> "Product A");
            cache.getIfPresent("SKU-1");

            assertThat(registry.find("cache.gets")
                    .tag("cache", "catalogBySku")
                    .tag("result", "hit")
                    .meters()).isNotEmpty();
            assertThat(registry.find("cache.gets")
                    .tag("cache", "catalogBySku")
                    .tag("result", "miss")
                    .meters()).isNotEmpty();
        }
    }
}
~~~

Điểm chính của test là xác minh **meter được đăng ký với tags mong đợi**. Nếu cần kiểm tra giá trị đếm, hãy đọc meter cụ thể của Micrometer (ví dụ function counter ở binder provider) bằng API tương ứng với phiên bản đang dùng. Không khẳng định `SimpleMeterRegistry` sẽ có tên series Prometheus đã được đổi thành `cache_gets_total`.

### 9.3. Integration test Spring Boot

Với `@SpringBootTest` hoặc một test context phù hợp:

1. Bảo đảm `@EnableCaching` và bean `CaffeineCacheManager` có mặt.
2. Gọi **Spring bean** `CatalogService` từ bên ngoài proxy, không tự tạo instance bằng `new`.
3. Gọi `findProduct("SKU-1")` hai lần, xác minh backend chỉ được gọi một lần trong trường hợp cache có hiệu lực.
4. Kiểm tra `MeterRegistry` được inject có meter `cache.gets` với tag đúng tên cache, và quan sát hit/miss khi có traffic.
5. Nếu dùng Prometheus registry, kiểm tra output endpoint `/actuator/prometheus` và tên series thực tế.
6. Kiểm tra một case invalidation, TTL hoặc eviction theo chính sách cache; đừng giả định mọi lần `@CacheEvict` sẽ làm tăng `cache.evictions`.

Nên cách ly cache giữa các test để lần chạy trước không biến miss dự kiến thành hit bất ngờ. Với dữ liệu test nhỏ, dùng tập key cố định và tránh assertions dựa vào thứ tự kích hoạt các test khác.

## 10. Điều tra sự cố cache trong môi trường thực

### 10.1. Hit ratio giảm mạnh sau triển khai

Ví dụ hit ratio của `catalogBySku` giảm từ 92% xuống 35% sau rollout, trong khi p95 HTTP tăng từ 180 ms lên 700 ms.

Quy trình đề xuất:

1. **Xác minh phạm vi:** cache nào, service nào, instance nào, bản phát hành nào, khoảng đo nào có thay đổi.
2. **Xem traffic:** request rate và lookup rate có đổi không? Có đột biến request key mới không?
3. **Kiểm tra cache warm-up:** rollout mới, restart pod, tăng số instance hoặc thay đổi routing có làm cache in-process trở nên lạnh không?
4. **Đối chiếu eviction và size:** cache có chạm giới hạn capacity? TTL có giảm? Entry có bị invalidation hàng loạt?
5. **Xem backend:** database/call downstream có tăng tải tương ứng với số miss không?
6. **Dùng tracing và logs:** tìm request chậm đã được sampling giữ, xem thời gian ở backend hoặc connection pool, đối chiếu log timeout.
7. **Xác nhận nguyên nhân:** thử điều chỉnh TTL/capacity/logic key hoặc rollback có kiểm soát, rồi đo lại hit ratio, backend load và p95.

Một **trace chậm** cho thấy điều gì xảy ra trong một request; metrics cho thấy có bao nhiêu request bị ảnh hưởng. Cần cả hai loại bằng chứng, không chỉ mở một trace rồi khái quát.

### 10.2. Hit ratio rất cao nhưng người dùng nhìn thấy dữ liệu cũ

Đây có thể là vấn đề **cache invalidation hoặc freshness**, không phải vấn đề hit ratio. Kiểm tra:

- TTL có phù hợp với tốc độ thay đổi dữ liệu không?
- Có `@CacheEvict` hoặc cơ chế làm mới đúng sau update không?
- Update thành công ở nguồn dữ liệu nhưng sự kiện invalidation thất lạc?
- Cache in-process có nhiều bản sao và chỉ một instance được xóa?
- Có yêu cầu consistency khiến cách cache hiện tại không phù hợp?

Giải pháp là sửa hợp đồng nhất quán dữ liệu và kiểm thử cập nhật/xóa, không phải cố tăng hit ratio.

### 10.3. Evictions tăng và JVM GC pause tăng

Nếu cache `catalogBySku` gần chạm `maximumSize` và eviction tăng, hãy kiểm tra working set, kích thước entry, TTL và memory pressure. Nhưng việc eviction tăng không tự chứng minh rằng GC pause đến từ cache: phải đối chiếu heap, allocation rate, CPU và profiling nếu cần.

### 10.4. Không thấy cache metrics dù @Cacheable hoạt động

Kiểm tra lần lượt:

| Câu hỏi | Hướng kiểm tra |
| --- | --- |
| Caching đã bật chưa? | Có `@EnableCaching`, bean/proxy đúng và đường gọi đi qua proxy? |
| Provider có được hỗ trợ không? | Caffeine, JCache hoặc provider cụ thể có binder phù hợp? |
| Có statistics không? | Với Caffeine, `recordStats()` đã bật? |
| Cache đã tồn tại lúc startup chưa? | Nếu tạo động, cần cơ chế bind riêng |
| Tên cache có đúng không? | Kiểm tra `cacheNames` và các nhãn ở Actuator |
| Actuator có meter không? | Xem `/actuator/metrics/cache.gets` |
| Registry Prometheus đã sẵn sàng chưa? | Dependency, exposure, đường dẫn, network |
| Backend có scrape thành công không? | Kiểm tra Prometheus target, series thực tế và thời điểm |
| Có MeterFilter chặn không? | Kiểm tra chính sách đổi tên/từ chối meters |

Đừng sửa tracing exporter để chữa lỗi cache metrics chưa được bind; chúng là hai nhánh pipeline khác nhau.

## 11. Cardinality, chi phí và bảo mật

Với cache metrics, **tên cache** là một phần của hợp đồng quan sát. Một số hệ thống sai lầm khi đặt tên cache theo người dùng:

~~~text
Không nên:
  cache=products-for-user-123
  cache=products-for-user-124
  cache=products-for-user-125

Nên:
  cache=catalogBySku
  cache=permissionsByRole
~~~

Giữ tên cache hữu hạn, đặt nghĩa theo nghiệp vụ và dùng cache key bên trong provider để phân biệt item. **Không đưa cache key vào tag metrics**, đặc biệt với email, user ID, SKU có số lượng lớn hoặc URL thô.

Giả sử có 10 tên cache, 4 cache manager, 3 vùng và 30 instance. Nếu các tổ hợp đều xuất hiện, một meter có thể có tối đa **10 × 4 × 3 × 30 = 3.600** series trước khi tính tag `result=hit|miss` và các nhãn khác. Một cache name mới cho từng request làm cardinality mất kiểm soát.

Với thống kê hit/miss, chi phí không chỉ đến từ số series mà còn từ tần suất scrape, retention và số backend. Bảo vệ endpoint metrics và tránh đưa thông tin bí mật hoặc dữ liệu cá nhân vào tag, logs hoặc span attributes.

### 11.1. Đổi schema metrics an toàn

Nếu đổi tên `catalogBySku` hoặc đổi tag `cache`, dashboard/alert cũ có thể mất dữ liệu dù ứng dụng vẫn chạy. Trước khi thay:

1. Tìm các query, dashboard và alert đang dùng tên/cache label.
2. Kiểm tra khả năng hỗ trợ song song schema cũ/mới trong giai đoạn chuyển tiếp.
3. Cập nhật tài liệu và test contract.
4. Triển khai và so sánh count/rate trên các instance.
5. Thống nhất thời điểm loại bỏ query cũ sau khi dữ liệu lịch sử không còn cần.

## 12. Thiết kế dashboard và cảnh báo cache

Một dashboard cache nên giúp trả lời không chỉ “hit ratio bao nhiêu?” mà cả “**có ảnh hưởng đến người dùng hay không?**”.

| Nhóm panel | Giá trị nên quan sát | Gợi ý hành động khi bất thường |
| --- | --- | --- |
| Lookup throughput | Hit, miss và tổng lookup rate | Xác định workload có thay đổi không |
| Hit ratio | % hit trong 5–30 phút theo cache | Kiểm tra warm-up, TTL, key và capacity |
| Eviction rate | Evictions/giây | Kiểm tra memory budget, maximumSize |
| Cache size | Số entry theo instance/manager | Phát hiện instance lệch hoặc cache không tăng |
| User latency | HTTP p95/p99 của endpoint đọc sản phẩm | Xác minh có tác động người dùng |
| Downstream load | DB query/HTTP dependency rate, timeout | Biết miss có gây quá tải nguồn không |
| JVM health | Heap, GC pause, CPU | Cân bằng chi phí cache với hiệu năng |
| Errors | Tỷ lệ lỗi HTTP và backend | Phân biệt cache miss với sự cố nguồn |

Một cảnh báo hit ratio đơn giản như “dưới 70% trong 10 phút” dễ báo động giả khi traffic thấp hoặc cache lạnh. Nên kết hợp điều kiện **lookup rate tối thiểu**, mức độ duy trì qua nhiều cửa sổ và tác động đến downstream latency/error rate.

Ngoài ra, cache là cơ chế tối ưu hiệu năng. Trong hệ thống có SLO chính thức, **latency và error rate của người dùng** thường phù hợp hơn làm mục tiêu chính, còn cache metrics là tín hiệu chẩn đoán/điều khiển.

## 13. Bài thực hành: đo hiệu quả cache danh mục

**Bối cảnh:** một ứng dụng Spring Boot xử lý `GET /products/{sku}`. Số lượt truy cập sản phẩm tăng sau chiến dịch marketing. Bạn cần chứng minh cache giúp giảm truy cập `catalog-service` và phát hiện khi cache bắt đầu không hiệu quả.

**Nhiệm vụ:**

1. Thêm `spring-boot-starter-cache`, Caffeine, Actuator và registry Prometheus.
2. Khai báo cache `catalogBySku` có `maximumSize(10_000)`, TTL 10 phút và `recordStats()`.
3. Tạo `CatalogService.findProduct(sku)` dùng `@Cacheable`, gọi backend giả lập có bộ đếm số lần fetch.
4. Tạo bốn lookup theo thứ tự: `SKU-1`, `SKU-1`, `SKU-2`, `SKU-1`. Tính hit/miss trên giấy, rồi đối chiếu statistics provider. Trong giả định cache ban đầu trống và không có expiration: **2 miss, 2 hit, hit ratio 50%**.
5. Kiểm tra `cache.gets`, `cache.puts`, `cache.size` và các series mà Prometheus registry thực sự xuất.
6. Viết PromQL tính hit ratio 5 phút, miss rate và eviction rate; hiển thị lookup rate để tránh giải thích sai khi ít traffic.
7. Giảm `maximumSize` trong môi trường thử nghiệm rồi tạo nhiều key, xem eviction/miss và độ trễ backend thay đổi thế nào.
8. Thử cập nhật một sản phẩm: xác minh dữ liệu cũ còn tồn tại khi chưa invalidation, sau đó thiết kế và kiểm thử `@CacheEvict` đúng.
9. Khi miss rate tăng, mở một trace HTTP chậm được lấy mẫu, đối chiếu span của lời gọi backend và log theo trace ID nếu có.
10. Viết một đề xuất cảnh báo liên kết hit ratio với backend latency/5xx và một quy tắc cấm cache key hoặc dữ liệu cá nhân trong metric tags.

**Kết quả mong đợi:** cấu hình Caffeine phù hợp, unit/integration tests cho cache và meter binding, dashboard có hit/miss/eviction/size, giải thích được giới hạn của từng số đo, cùng một báo cáo điều tra ngắn có bằng chứng từ metrics, logs và traces.

## 14. Ghi nhớ

**Cache metrics** giúp nhìn thấy hit/miss, put, eviction và size của các cache được hỗ trợ. Trong Spring Boot, Actuator/Micrometer có thể tự bind cache đã được khởi tạo và provider có statistics; với **Caffeine**, `recordStats()` là cấu hình quan trọng khi cần thống kê hit/miss.

Một hit ratio cao không tự chứng minh cache có dữ liệu đúng hay request nhanh; một miss rate cao không tự chứng minh hệ thống lỗi. Phải đọc metrics theo **cache, traffic, instance, thời gian và hành vi provider**, sau đó đối chiếu với HTTP latency, downstream load, logs và distributed traces. Thiết kế tags/cardinality an toàn, exporter đáng tin cậy và hiểu rõ sampling/context propagation là điều kiện để việc điều tra sự cố có cơ sở.

**Tài liệu tham khảo:**

- [Spring Boot — Metrics và Cache Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Micrometer — Cache Metrics](https://docs.micrometer.io/micrometer/reference/reference/cache.html)
- [Micrometer — Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Caffeine — Statistics](https://github.com/ben-manes/caffeine/wiki/Statistics)
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
