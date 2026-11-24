# Ánh xạ mục đích timeout, isolation và fallback khi rời Hystrix

## Mục tiêu

Khi chuyển một ứng dụng Spring Cloud cũ khỏi Netflix Hystrix sang Spring Cloud CircuitBreaker với Resilience4j, không nên chỉ đổi tên thuộc tính cấu hình. Hystrix gộp nhiều khả năng vào một command: timeout, thread/semaphore isolation, circuit breaker và fallback. Ở kiến trúc mới, các trách nhiệm này thường được cấu hình thành những cơ chế riêng như Circuit Breaker, TimeLimiter, Bulkhead và timeout của HTTP client.

Sau bài học, bạn có thể:

- Xác định mục đích của Hystrix timeout, thread isolation và semaphore isolation.
- Ánh xạ các mục đích đó sang TimeLimiter, Bulkhead và timeout ở tầng HTTP client.
- Chuyển fallback từ `getFallback()` sang callback của Spring Cloud CircuitBreaker hoặc fallback method.
- Phân biệt cấu hình tương đương về ý định với thuộc tính không có ánh xạ một-một.
- Lập kế hoạch chuyển đổi, kiểm thử hành vi và theo dõi tải sau khi rời Hystrix.

## Tư duy chuyển đổi: giữ mục đích, thiết kế lại cơ chế

Hystrix command thường kết hợp các việc sau:

- Thực thi thao tác phụ thuộc.
- Áp dụng timeout.
- Cách ly bằng thread pool hoặc semaphore.
- Theo dõi lỗi để mở/đóng circuit.
- Gọi fallback khi thao tác thất bại hoặc bị từ chối.

Spring Cloud CircuitBreaker cung cấp abstraction cho lời gọi được bảo vệ. Khi dùng Resilience4j, từng khả năng được biểu diễn bằng cấu hình riêng. Vì vậy, một thuộc tính Hystrix thường cần được phân tích thành một hoặc nhiều yêu cầu mới.

| Mục đích trong Hystrix | Cơ chế thường dùng sau chuyển đổi | Điều cần xác minh |
|---|---|---|
| `execution.isolation.thread.timeoutInMilliseconds` | TimeLimiter và timeout của HTTP client. | Caller ngừng chờ đúng hạn; I/O thực tế có được hủy hay không. |
| `execution.isolation.strategy=THREAD` | ThreadPoolBulkhead hoặc executor riêng có giới hạn. | Pool, queue, rejection và truyền context. |
| `execution.isolation.strategy=SEMAPHORE` | SemaphoreBulkhead. | Số lời gọi đồng thời và thời gian chờ lấy permit. |
| `execution.isolation.semaphore.maxConcurrentRequests` | `bulkhead.maxConcurrentCalls`. | Đây là giới hạn concurrency ở caller, không phải số thread. |
| `execution.isolation.thread.*` pool/queue | `thread-pool-bulkhead` hoặc executor riêng. | `queueCapacity` không có cùng semantics với mọi giới hạn queue của Hystrix. |
| `getFallback()` | Fallback function của `CircuitBreaker.run` hoặc `fallbackMethod`. | Exception nào kích hoạt fallback và kiểu response được trả về. |
| `circuitBreaker.requestVolumeThreshold` | `minimumNumberOfCalls`. | Cửa sổ thống kê và cách đếm mẫu. |
| `circuitBreaker.errorThresholdPercentage` | `failureRateThreshold`. | Các exception bị ignore và ngưỡng áp dụng. |
| `circuitBreaker.sleepWindowInMilliseconds` | `waitDurationInOpenState`. | Thời gian trước khi cho phép probe `HALF_OPEN`. |

Đây là ánh xạ theo ý định. Không phải mọi thuộc tính Hystrix đều có thuộc tính Resilience4j tương đương. Hãy xác định hành vi mà ứng dụng cần bảo toàn rồi chọn cơ chế mới, thay vì sao chép nguyên tên và giá trị.

## Timeout: tách giới hạn chờ khỏi giới hạn I/O

Trong Hystrix, `execution.isolation.thread.timeoutInMilliseconds` thường giới hạn thời gian command chạy trong thread isolation. Khi chuyển sang Spring Cloud CircuitBreaker, có thể cấu hình TimeLimiter theo instance:

```yaml
resilience4j:
  timelimiter:
    instances:
      catalog:
        timeoutDuration: 800ms
        cancelRunningFuture: true
```

Với Spring Cloud CircuitBreaker Resilience4j, TimeLimiter được tích hợp vào factory theo cấu hình của integration. Có thể tắt TimeLimiter toàn cục bằng `spring.cloud.circuitbreaker.resilience4j.disable-time-limiter: true`, hoặc chọn phạm vi theo instance/group bằng `disable-time-limiter-map` nếu phiên bản đang dùng hỗ trợ. Tắt TimeLimiter không tắt Circuit Breaker.

TimeLimiter giới hạn thời gian chờ theo cơ chế thực thi mà integration cung cấp. Nó không bảo đảm socket, JDBC statement hoặc tác vụ blocking bên dưới dừng ngay khi timeout. Do đó, phải cấu hình timeout ở client thực hiện I/O:

- HTTP connect timeout giới hạn thời gian thiết lập kết nối.
- HTTP response/read timeout giới hạn thời gian chờ dữ liệu phản hồi.
- JDBC connection acquisition timeout giới hạn thời gian chờ lấy connection từ pool.
- Query/statement timeout giới hạn thời gian thực thi truy vấn ở database driver hoặc ORM.
- Deadline của request giới hạn tổng thời gian qua nhiều tầng.

Ví dụ cấu hình một WebClient dùng Reactor Netty:

```java
import java.time.Duration;

import reactor.netty.http.client.HttpClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class CatalogClientConfiguration {
    @Bean
    WebClient catalogWebClient() {
        HttpClient httpClient = HttpClient.create()
                .responseTimeout(Duration.ofMillis(700));

        return WebClient.builder()
                .baseUrl("http://catalog-service")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Ví dụ trên đặt response timeout; trong production cần cấu hình cả connect timeout và pool acquire timeout theo client/version đang dùng. Nếu dùng `RestClient` hoặc `RestTemplate`, cấu hình timeout trong HTTP request factory tương ứng.

### Deadline tổng

Không nên đặt cùng một timeout dài ở mọi tầng. Nếu Gateway chờ 2 giây, order-service không nên bắt đầu một lời gọi inventory mới với timeout 2 giây khi request đã tiêu tốn 1,5 giây. Hãy truyền hoặc tính deadline còn lại và chỉ bắt đầu thao tác khi còn đủ ngân sách.

Ví dụ, một request có deadline 1.500 ms có thể phân bổ 200 ms cho xử lý Gateway, tối đa 900 ms cho order-service gọi dependency và phần còn lại cho xử lý/serialize response. Các giá trị phải dựa trên SLA và latency đo được. TimeLimiter của từng lời gọi không thay thế deadline tổng.

## Isolation: thread pool và semaphore không giống nhau

Hystrix cung cấp hai chiến lược isolation chính:

- **THREAD:** command chạy trên thread pool riêng. Mục đích là cách ly một dependency blocking khỏi thread xử lý request và giới hạn lượng công việc chạy đồng thời.
- **SEMAPHORE:** command chạy trên thread của caller nhưng phải lấy permit. Mục đích là giới hạn concurrency mà không tạo pool thread riêng.

Trong Resilience4j, hai mục đích này thường được ánh xạ như sau:

| Hystrix | Resilience4j | Hành vi |
|---|---|---|
| Thread isolation | ThreadPoolBulkhead | Có pool và queue riêng; task có thể được xếp hàng rồi chạy trên worker. |
| Semaphore isolation | SemaphoreBulkhead | Giới hạn permit; không tạo thread pool mới. |

Ví dụ SemaphoreBulkhead:

```yaml
resilience4j:
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0
```

Ví dụ ThreadPoolBulkhead:

```yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      legacy-catalog:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
```

SemaphoreBulkhead tương ứng với giới hạn số lời gọi đồng thời. ThreadPoolBulkhead phù hợp khi cần cách ly một thao tác blocking trên executor riêng. Không nên chuyển mọi lời gọi sang ThreadPoolBulkhead theo thói quen: một ứng dụng reactive cần giữ I/O non-blocking và tránh chạy blocking code trên event loop.

### Giới hạn queue không phải lúc nào cũng tương đương

Hystrix thread pool có các thuộc tính như `coreSize`, `maxQueueSize` và `queueSizeRejectionThreshold`. Resilience4j ThreadPoolBulkhead có `coreThreadPoolSize`, `maxThreadPoolSize` và `queueCapacity`. Các giá trị này phục vụ mục đích gần nhau nhưng cách áp dụng queue, rejection và thay đổi ngưỡng không hoàn toàn giống nhau.

Một queue lớn chỉ giữ request chờ lâu hơn; nó không làm dependency nhanh hơn. Hãy chọn queue nhỏ dựa trên deadline, giới hạn concurrency và thời gian xử lý. Nếu request hết deadline khi còn nằm trong queue, công việc có thể vẫn chạy sau khi caller không còn cần kết quả.

Hystrix có thể cấu hình giới hạn riêng cho semaphore của fallback bằng `fallback.isolation.semaphore.maxConcurrentRequests`. Resilience4j không nên được xem là tự động tạo cùng một quota fallback. Nếu fallback có thể gây tải đáng kể, hãy giới hạn riêng nó bằng semaphore, executor hoặc rate limit phù hợp.

## Circuit Breaker: ánh xạ cửa sổ và ngưỡng

Một số thuộc tính Circuit Breaker Hystrix có mục đích gần với Resilience4j:

| Hystrix | Resilience4j | Ghi chú |
|---|---|---|
| `requestVolumeThreshold` | `minimumNumberOfCalls` | Số mẫu tối thiểu trước khi đánh giá ngưỡng. |
| `errorThresholdPercentage` | `failureRateThreshold` | Tỷ lệ lỗi để mở mạch. |
| `sleepWindowInMilliseconds` | `waitDurationInOpenState` | Thời gian chờ ở `OPEN` trước khi cho phép probe. |
| `metrics.rollingStats.timeInMilliseconds` | `slidingWindowType: TIME_BASED` và `slidingWindowSize` | Cần chuyển đổi đơn vị và kiểm tra cách chia bucket/cửa sổ. |
| `forceOpen` / `forceClosed` | Trạng thái cưỡng bức tương ứng nếu integration/version hỗ trợ | Không giả định cách vận hành và quyền ghi đè giống nhau. |

Ví dụ cấu hình Resilience4j:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 700ms
        waitDurationInOpenState: 8s
        permittedNumberOfCallsInHalfOpenState: 3
```

Hystrix và Resilience4j không nhất thiết tính rolling statistics theo cùng cách. Đừng chuyển `rollingStats.timeInMilliseconds` thành một số `slidingWindowSize` tùy ý rồi kỳ vọng tỷ lệ chuyển trạng thái giống hệt. Hãy chọn loại cửa sổ, kích thước, số mẫu tối thiểu và ngưỡng dựa trên lưu lượng thực tế, sau đó chạy cùng kịch bản lỗi để hiệu chỉnh.

## Fallback: chuyển từ getFallback() sang callback rõ ràng

Trong Hystrix, fallback thường được triển khai bằng `getFallback()` trong command hoặc một phương thức fallback gắn với command. Khi chuyển sang Spring Cloud CircuitBreaker, callback fallback được truyền tại nơi tạo lời gọi:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogGateway {
    private final RestClient restClient;
    private final CircuitBreaker catalogBreaker;

    public CatalogGateway(
            RestClient.Builder builder,
            CircuitBreakerFactory<?, ?> factory) {
        this.restClient = builder.baseUrl("http://catalog-service").build();
        this.catalogBreaker = factory.create("catalog");
    }

    public Product findById(String id) {
        return catalogBreaker.run(
                () -> restClient.get()
                        .uri("/products/{id}", id)
                        .retrieve()
                        .body(Product.class),
                error -> Product.unavailable(id));
    }
}
```

`Product` và `Product.unavailable` là kiểu dữ liệu ví dụ. Fallback callback nhận nguyên nhân dưới dạng `Throwable`; ứng dụng có thể phân loại nguyên nhân để trả cache, response không khả dụng hoặc truyền lỗi về caller. Với annotation Resilience4j, có thể dùng `@CircuitBreaker(name = "catalog", fallbackMethod = "findFallback")`, nhưng đây là annotation của Resilience4j và vẫn phụ thuộc Spring AOP proxy.

Không nên coi mọi lỗi đều có cùng fallback:

- Circuit Breaker đang `OPEN`: có thể trả dữ liệu cache hoặc lỗi dependency không khả dụng.
- Timeout/kết nối: có thể trả dữ liệu suy giảm nếu nghiệp vụ cho phép.
- Lỗi validation hoặc HTTP 4xx nghiệp vụ: giữ đúng ý nghĩa lỗi, không biến thành dữ liệu mặc định.
- Lỗi lập trình hoặc cấu hình: thường cần truyền lỗi và sửa nguyên nhân thay vì che giấu.

Hystrix có khái niệm lỗi bị loại khỏi thống kê như `HystrixBadRequestException`. Khi chuyển sang Resilience4j, xác định exception nào không nên làm tăng failure rate bằng `ignoreExceptions` hoặc predicate phù hợp. Lưu ý exception bị ignore khỏi thống kê không đồng nghĩa fallback chắc chắn không chạy; hành vi fallback còn phụ thuộc đường gọi và API đang sử dụng.

### Giới hạn fallback riêng

Fallback cũng có thể quá tải. Nếu mỗi request thất bại đều gọi một cache, database dự phòng hoặc service khác, nguồn dự phòng có thể trở thành điểm nghẽn mới. Hãy:

- Giới hạn concurrency của fallback riêng với dependency chính.
- Đặt timeout ngắn và queue hữu hạn cho nguồn dự phòng.
- Không gọi lại dependency đang lỗi qua một route khác.
- Trả lỗi có cấu trúc nếu không có dữ liệu an toàn để trả.
- Theo dõi tỷ lệ fallback và lỗi của chính fallback.

## Ánh xạ cấu hình thực tế

Bảng dưới đây là checklist để chuyển các mục đích phổ biến. Tên thuộc tính Resilience4j cần được đặt theo instance ID dùng trong Spring Cloud CircuitBreaker factory.

| Cấu hình Hystrix | Cấu hình/thiết kế mới | Việc cần làm |
|---|---|---|
| `execution.timeout.enabled` | Bật/tắt TimeLimiter của integration | Dùng `disable-time-limiter` khi thật sự cần tắt TimeLimiter; vẫn cấu hình timeout HTTP client. |
| `execution.isolation.thread.timeoutInMilliseconds` | `resilience4j.timelimiter.instances.<id>.timeoutDuration` | Chuyển thời lượng, sau đó kiểm tra cancellation và timeout I/O. |
| `execution.isolation.strategy=THREAD` | `resilience4j.thread-pool-bulkhead.instances.<id>` | Chọn pool, queue, rejection và context propagation. |
| `execution.isolation.strategy=SEMAPHORE` | `resilience4j.bulkhead.instances.<id>` | Chọn `maxConcurrentCalls` và `maxWaitDuration`. |
| `execution.isolation.semaphore.maxConcurrentRequests` | `bulkhead.maxConcurrentCalls` | Giữ giới hạn concurrency theo capacity upstream. |
| `fallback.isolation.semaphore.maxConcurrentRequests` | Bulkhead riêng cho fallback | Không dùng chung quota với lời gọi chính nếu tải khác nhau. |
| `fallback.enabled` | Fallback callback/method có chủ đích | Quyết định rõ lỗi nào được fallback và lỗi nào truyền về caller. |
| `circuitBreaker.requestVolumeThreshold` | `minimumNumberOfCalls` | Chọn cửa sổ và số mẫu tối thiểu. |
| `circuitBreaker.errorThresholdPercentage` | `failureRateThreshold` | Kiểm thử tỷ lệ lỗi thực tế sau khi chuyển đổi. |
| `circuitBreaker.sleepWindowInMilliseconds` | `waitDurationInOpenState` | Chọn thời gian mở theo tốc độ phục hồi dependency. |
| `threadpool.<key>.coreSize` | `coreThreadPoolSize` | Không sao chép nguyên số nếu mô hình queue và tải đã đổi. |
| `threadpool.<key>.maxQueueSize` | `queueCapacity` | Chọn queue hữu hạn theo deadline và latency. |

Không có một thuộc tính đơn lẻ thay thế toàn bộ Hystrix command. Một command dùng THREAD isolation có thể cần cả ThreadPoolBulkhead, TimeLimiter, HTTP client timeout, Circuit Breaker và fallback. Việc chuyển đổi hoàn tất khi hành vi và giới hạn tài nguyên tương đương với mục tiêu vận hành, không phải khi mọi con số cấu hình đã được sao chép.

## Ví dụ cấu hình sau chuyển đổi

Một cấu hình minh họa cho dependency `catalog`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 8s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      catalog:
        timeoutDuration: 800ms
        cancelRunningFuture: true
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0
  thread-pool-bulkhead:
    instances:
      legacy-catalog:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
```

Ví dụ trên minh họa hai kiểu Bulkhead cho hai trường hợp khác nhau. Không nhất thiết bật cả SemaphoreBulkhead và ThreadPoolBulkhead cho cùng một lời gọi. Chọn một cơ chế cách ly phù hợp với loại thực thi và kiểm tra thứ tự decorator trong integration. Nếu cần bảo vệ một HTTP client blocking, ThreadPoolBulkhead có thể cách ly thread; nếu cần giới hạn concurrency trên caller thread, SemaphoreBulkhead thường phù hợp hơn.

## Lộ trình chuyển đổi theo từng command

Không nên thay toàn bộ Hystrix cùng lúc nếu hệ thống có nhiều dependency và fallback phức tạp. Chuyển đổi theo từng command hoặc nhóm dependency:

1. **Lập danh mục command:** ghi lại command key, group key, thread pool key, downstream, timeout, isolation strategy, fallback và exception bị bỏ qua.
2. **Phân loại I/O:** xác định command blocking, non-blocking, CPU-bound hay fan-out nhiều dependency.
3. **Chọn ranh giới mới:** tạo một Circuit Breaker ID cho dependency hoặc nhóm thao tác có cùng đặc tính lỗi.
4. **Ánh xạ timeout:** đặt timeout ở HTTP/database client, TimeLimiter và deadline tổng.
5. **Ánh xạ isolation:** chọn SemaphoreBulkhead hoặc ThreadPoolBulkhead; đặt queue và concurrency theo capacity.
6. **Chuyển fallback:** giữ đúng kiểu dữ liệu, status và ngữ nghĩa nghiệp vụ; giới hạn tải nguồn fallback.
7. **Chuyển circuit policy:** chọn sliding window, minimum calls, failure/slow-call threshold và thời gian `OPEN`.
8. **Kiểm thử lỗi:** success, timeout, connection reset, 5xx, rejection, fallback failure và phục hồi `HALF_OPEN`.
9. **So sánh telemetry:** request rate, latency, thread/queue/connection saturation, retry, fallback và trạng thái Circuit Breaker.
10. **Triển khai theo đợt:** quan sát một dependency trước, sau đó mở rộng khi hành vi ổn định.

## Kiểm thử hành vi sau chuyển đổi

Một bộ kiểm thử tích hợp nên chứng minh mục đích cũ được đáp ứng bằng cơ chế mới:

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Dependency phản hồi nhanh | Caller nhận kết quả thật; Circuit Breaker ghi nhận success. |
| Dependency phản hồi quá thời hạn | Caller kết thúc trong timeout/deadline; HTTP client không giữ tài nguyên vô hạn. |
| Dependency liên tục trả lỗi | Circuit Breaker mở sau khi đủ mẫu và đạt threshold. |
| Circuit Breaker `OPEN` | Supplier không gọi upstream; fallback hoặc lỗi từ chối được xử lý đúng. |
| Semaphore hết permit | Request mới bị từ chối/chờ trong giới hạn; không tạo thread mới. |
| ThreadPoolBulkhead đầy queue | Task mới bị từ chối; queue không vượt capacity. |
| Fallback chậm hoặc lỗi | Fallback có timeout/concurrency riêng; không làm cạn tài nguyên caller. |
| Dependency phục hồi | Probe `HALF_OPEN` được giới hạn và mạch đóng lại khi đủ kết quả tốt. |

Kiểm tra cả số request thật tới upstream. Nếu timeout xảy ra nhưng request vẫn tiếp tục chạy ở thread hoặc socket, chỉ assert rằng caller nhận fallback là chưa đủ. Quan sát connection pool, active thread và task đang chạy để xác nhận tài nguyên được giải phóng.

## Những tính năng Hystrix không được thay thế tự động

Một số khả năng của Hystrix không có ánh xạ trực tiếp chỉ bằng cách dùng Spring Cloud CircuitBreaker:

- **Request cache:** cần xác định cache key, phạm vi request và cơ chế cache mới; không tự xuất hiện khi chuyển Circuit Breaker.
- **Request collapsing:** cần thiết kế batching hoặc coalescing riêng nếu downstream có hỗ trợ.
- **Hystrix dashboard/event stream:** chuyển sang Micrometer, Actuator và hệ thống quan sát tương ứng; dashboard cũ không tự hiểu metric Resilience4j.
- **Thread context propagation:** kiểm tra SecurityContext, MDC, tracing và transaction context khi chuyển sang executor/ThreadPoolBulkhead.
- **Fallback semaphore:** cần giới hạn fallback rõ ràng; không giả định Bulkhead của lời gọi chính tự giới hạn fallback.
- **Command grouping và thread pool key:** cần thiết kế lại ID Circuit Breaker, Bulkhead và tên executor theo ranh giới dependency mới.

Nếu ứng dụng dùng `HystrixObservableCommand` hoặc RxJava, hãy chuyển sang `Mono`/`Flux` hoặc `CompletableFuture` theo mô hình ứng dụng. Không gọi blocking API trên Reactor event loop và không tự subscribe trong service chỉ để kích hoạt fallback.

## Theo dõi sau khi chuyển đổi

Các chỉ số nên được đối chiếu trước và sau migration:

- Tỷ lệ success, failure, timeout và lời gọi bị từ chối theo dependency.
- Latency p50/p95/p99 và thời gian request tổng.
- Số thread active, queue depth, queue wait và task rejection.
- Số Bulkhead permit còn trống và số lần từ chối.
- HTTP connection pool active/idle/pending acquire và acquire timeout.
- Số fallback, tỷ lệ fallback thành công và độ trễ fallback.
- Số probe `HALF_OPEN`, thời gian ở `OPEN` và thời gian phục hồi.
- Số request logic so với số request vật lý tới upstream.

Resilience4j có thể xuất metric qua Micrometer khi binder phù hợp được bật. Tên metric và tag có thể khác Hystrix; hãy cập nhật dashboard, alert và runbook. Tránh giữ dashboard cũ nhưng chỉ thay nguồn dữ liệu một phần, vì điều đó dễ làm người vận hành hiểu sai trạng thái hệ thống.

## Lỗi thường gặp

- **Chỉ thay Hystrix command bằng `CircuitBreaker.run`:** bỏ sót timeout, isolation và giới hạn concurrency.
- **Cho rằng TimeLimiter thay thế HTTP timeout:** caller có thể ngừng chờ trong khi I/O vẫn chạy.
- **Dùng ThreadPoolBulkhead cho mọi lời gọi:** có thể tạo thêm queue và thread không cần thiết, đặc biệt với reactive I/O.
- **Dùng SemaphoreBulkhead nhưng quên giới hạn connection pool:** permit còn trống không có nghĩa HTTP client còn connection.
- **Sao chép nguyên queue size:** semantics queue và rejection giữa hai thư viện không giống nhau.
- **Dùng một Bulkhead cho cả dependency và fallback:** nguồn dự phòng có thể không còn capacity khi dependency chính lỗi.
- **Fallback mọi exception thành dữ liệu mặc định:** che giấu lỗi validation, lỗi lập trình hoặc trạng thái nghiệp vụ chưa xác định.
- **Retry `CallNotPermittedException`:** Circuit Breaker đã từ chối lời gọi; retry ngay chỉ tạo thêm công việc vô ích.
- **Giữ nguyên dashboard Hystrix:** metric name, event và trạng thái không tự tương thích với Resilience4j.
- **Không kiểm tra context propagation:** log, trace hoặc security context có thể mất khi chuyển sang executor riêng.
- **Chỉ so sánh tỷ lệ lỗi:** bỏ qua latency, saturation, số request vật lý và hành vi hủy tác vụ.

Rời Hystrix là cơ hội tách rõ timeout, isolation, Circuit Breaker và fallback thành những chính sách có thể cấu hình và quan sát độc lập. Hãy chuyển theo mục đích của từng command, kiểm tra giới hạn tài nguyên ở cả caller và upstream, rồi xác nhận bằng test lỗi và telemetry trước khi mở rộng sang các dependency khác.
