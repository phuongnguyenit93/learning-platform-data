# Chi phí log sự kiện và metrics trên đường xử lý chính

Circuit breaker cần ghi nhận kết quả lời gọi, cập nhật sliding window và phát sự kiện khi có thay đổi. Trong ứng dụng Spring Cloud dùng Resilience4j, Micrometer và event publisher giúp quan sát hành vi đó. Tuy nhiên, mọi thao tác bổ sung trên đường xử lý chính đều có chi phí: đọc đồng hồ, cập nhật meter, tạo tag, định dạng log, ghi stack trace, cấp phát object và chuyển dữ liệu sang hệ thống thu thập.

Mục tiêu không phải bỏ quan sát để giảm độ trễ. Cần chọn loại thông tin phù hợp với tần suất phát sinh, giữ thao tác đồng bộ trên hot path thật ngắn và đưa công việc I/O hoặc xử lý nặng sang một đường riêng có giới hạn. Một state transition hiếm gặp có thể được ghi log đầy đủ; một sự kiện thành công xuất hiện hàng chục nghìn lần mỗi giây nên được tổng hợp thành metric thay vì ghi một dòng log cho mỗi request.

## 1. Hot path gồm những gì?

Hot path là phần mã được thực thi cho mỗi request hoặc mỗi lời gọi dependency. Khi circuit breaker bọc một lời gọi, đường xử lý có thể gồm:

```text
Request nghiệp vụ
      |
      v
Circuit breaker kiểm tra state
      |
      v
Supplier gọi HTTP/RPC client
      |
      v
Ghi nhận success / failure / duration
      |
      v
Cập nhật sliding window và metrics
      |
      v
Phát event nếu có sự kiện tương ứng
      |
      v
Trả kết quả hoặc xử lý fallback
```

Các bước kiểm tra state và cập nhật thống kê là một phần cần thiết của circuit breaker. Chi phí quan sát bổ sung thường đến từ việc ứng dụng đăng ký event listener, ghi log, tạo metric tùy chỉnh, gắn tag động hoặc xuất dữ liệu ra ngoài.

Hãy phân biệt hai loại công việc:

- **Cập nhật tại chỗ:** tăng counter, cập nhật timer/gauge hoặc ghi một giá trị vào bộ đệm trong bộ nhớ. Các thao tác này thường nhanh nhưng vẫn tiêu thụ CPU, bộ nhớ và có thể tạo tranh chấp khi nhiều thread cập nhật cùng meter.
- **I/O hoặc xử lý mở rộng:** ghi file, gửi log qua mạng, gọi telemetry backend, serialize payload lớn, truy vấn database hoặc tính toán phân tích. Không nên thực hiện các công việc này trực tiếp trong callback của mỗi lời gọi.

Micrometer thường cập nhật meter trong bộ nhớ; Prometheus scrape endpoint theo chu kỳ riêng. Việc scrape không diễn ra đồng bộ trong từng request, nhưng mỗi lần cập nhật meter vẫn có chi phí và số lượng time series lớn làm tăng bộ nhớ, CPU, dung lượng scrape và chi phí lưu trữ.

## 2. Chi phí của từng loại quan sát

| Hoạt động | Chi phí thường gặp | Khi nào phù hợp |
| --- | --- | --- |
| Counter tăng một đơn vị | Tìm meter, cập nhật bộ đếm, đồng bộ nội bộ | Đếm sự kiện có tần suất cao với số tag hữu hạn |
| Timer ghi duration | Đọc đồng hồ, cập nhật count/sum và histogram nếu bật | Đo thời gian lời gọi hoặc thao tác quan trọng |
| Gauge đọc trạng thái | Lưu callback và đọc giá trị khi scrape | Quan sát state hoặc số lượng tài nguyên hiện tại |
| Log một state transition | Định dạng thông điệp và ghi log; thường hiếm | Ghi lại thay đổi `CLOSED`/`OPEN`/`HALF_OPEN` để điều tra |
| Log từng success/failure | Định dạng và xuất một dòng cho mỗi lần gọi; có thể tạo I/O lớn | Chỉ khi lưu lượng thấp hoặc đã lấy mẫu có chủ đích |
| Stack trace cho exception | Thu thập và định dạng stack trace, tăng kích thước log | Lỗi cần chẩn đoán, có kiểm soát tần suất |
| Trace/span | Tạo context, timestamp, propagation và export | Theo dõi luồng xuyên nhiều service; cần sampling phù hợp |
| Gửi event tới dịch vụ từ xa | Serialize, network, retry và quản lý lỗi truyền tải | Thực hiện bất đồng bộ qua queue/buffer có giới hạn |

Không có một con số overhead đúng cho mọi ứng dụng. Chi phí phụ thuộc JDK, phiên bản Micrometer/Resilience4j, registry, logging backend, số thread, cấu hình histogram, lượng tag và tải thực tế. Cần đo trong môi trường gần production thay vì giả định một meter hoặc một dòng log luôn rẻ.

## 3. Event listener có thể nằm ngay trên thread phát event

Resilience4j cung cấp event publisher cho các sự kiện như state transition, call success, call error và call not permitted. Consumer đăng ký trực tiếp thường được gọi trong quá trình event được phát. Vì vậy, hãy xem callback là một phần của đường xử lý có thể đang chạy trên thread thực hiện lời gọi, trừ khi integration hoặc phiên bản cụ thể bảo đảm cơ chế bất đồng bộ.

Ví dụ listener chỉ ghi nhận state transition:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryCircuitBreakerEvents {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryCircuitBreakerEvents.class);

    public InventoryCircuitBreakerEvents(CircuitBreakerRegistry registry) {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");

        breaker.getEventPublisher()
            .onStateTransition(event ->
                log.warn("inventory circuit breaker state transition: {}", event));
    }
}
```

State transition thường ít xuất hiện hơn call success, nên ghi log cho mỗi lần chuyển trạng thái có thể hợp lý. Tuy vậy, logging backend đồng bộ vẫn có thể làm thread phát event chờ ghi dữ liệu. Dùng log appender bất đồng bộ nếu cần, đồng thời cấu hình queue hữu hạn và chính sách khi queue đầy.

Không nên thêm `onSuccess` rồi ghi `INFO` cho mọi lời gọi thành công. Với lưu lượng lớn, cách đó tạo log volume tỷ lệ thuận với request rate, tăng chi phí format, I/O, truyền tải và lưu trữ. Dùng timer/counter tổng hợp để trả lời câu hỏi về xu hướng; chỉ ghi log chi tiết khi có lý do điều tra.

## 4. Chọn event nào cần log?

Mỗi loại event có tần suất và giá trị chẩn đoán khác nhau:

| Event | Tần suất có thể gặp | Cách xử lý gợi ý |
| --- | --- | --- |
| State transition | Thấp hơn nhiều so với số lời gọi | Ghi log có cấu trúc với breaker ID và trạng thái trước/sau |
| Call success | Có thể bằng gần như toàn bộ request | Không log từng lần; dùng timer/counter |
| Call error | Tăng mạnh trong outage | Metric tổng hợp, log mẫu hoặc log theo nhóm lỗi có giới hạn |
| Call not permitted | Có thể rất cao khi breaker `OPEN` | Dùng metric để đếm; tránh ghi một warning cho mỗi request bị chặn |
| Slow call | Tùy latency và threshold | Dùng slow-call rate và histogram; log mẫu nếu cần điều tra |
| Reset hoặc thao tác quản trị | Hiếm và có ý nghĩa vận hành | Ghi audit có người thực hiện, lý do và thời điểm |

Khi breaker `OPEN`, một lượng lớn request có thể bị từ chối rất nhanh. Nếu mỗi `CallNotPermittedException` tạo một stack trace và một dòng log `ERROR`, chính lúc hệ thống đang chịu sự cố lại có thể tạo thêm tải cho CPU, disk, log collector và mạng. Hãy đếm số lần bị từ chối bằng metric và log state transition; chỉ log mẫu của các lần từ chối nếu cần thêm ngữ cảnh.

## 5. Metrics: rẻ hơn log từng request nhưng vẫn có giới hạn

Micrometer và Resilience4j cung cấp metric tổng hợp cho circuit breaker. Một timer có thể ghi nhận số lượng và thời gian thực thi theo các nhóm kết quả; gauge có thể biểu diễn state, failure rate, slow-call rate hoặc số mẫu trong cửa sổ. Các meter này giúp quan sát xu hướng mà không cần tạo một dòng log cho mọi request.

Tuy nhiên, mỗi tổ hợp tên meter và tag tạo một hoặc nhiều time series. Ví dụ, metric có các tag `dependency`, `environment`, `region` và `pod` sẽ có số series tăng theo số tổ hợp giá trị. Nếu thêm `userId`, `orderId`, `sku` hoặc request ID, cardinality có thể tăng gần như theo số request.

Quy tắc tag an toàn:

- Dùng giá trị có tập hữu hạn như `dependency=inventory`, `result=success|failure`, `environment=prod`.
- Chỉ thêm `pod` hoặc `instance` khi cần phân tích theo replica và backend có thể chịu số series tương ứng.
- Không dùng user ID, order ID, request ID, URL chứa tham số hoặc exception message làm tag.
- Phân loại exception thành nhóm hữu hạn như `timeout`, `connection`, `rejected`, `other` nếu cần phân tách lỗi.
- Đưa ID cụ thể và nguyên nhân chi tiết vào log hoặc trace có kiểm soát, không đưa vào label metric.

Ví dụ đăng ký counter một lần trong constructor thay vì tạo tên và tag động trong từng request:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class InventoryFallbackMetrics {

    private final Counter fallbackCounter;

    public InventoryFallbackMetrics(MeterRegistry registry) {
        this.fallbackCounter = Counter.builder("application.fallback.calls")
            .description("Number of inventory fallback responses")
            .tag("dependency", "inventory")
            .register(registry);
    }

    public void recordFallback() {
        fallbackCounter.increment();
    }
}
```

Meter được tạo một lần và tái sử dụng. Nếu cần phân loại theo nguyên nhân, tạo trước một số counter có tag hữu hạn hoặc dùng meter provider theo enum cố định; tránh truyền chuỗi tùy ý từ exception vào tag.

## 6. Timer và histogram làm tăng chi phí theo dõi

Timer đo count và tổng thời gian. Khi bật histogram, registry còn duy trì hoặc xuất các bucket để tính phân vị ở backend. Histogram hữu ích khi cần p95/p99, nhưng số bucket và số tag làm tăng số time series.

Ví dụ cấu hình bật histogram cho timer circuit breaker:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        resilience4j.circuitbreaker.calls: true
```

Không bật histogram cho mọi meter chỉ vì có thể. Hãy chọn các timer phục vụ SLO hoặc điều tra tail latency, cân nhắc bucket phù hợp với thời gian phản hồi mục tiêu và kiểm tra cardinality sau khi triển khai. Nếu backend hỗ trợ percentile tổng hợp theo cách khác, đánh giá chi phí và độ chính xác của từng lựa chọn.

Timer đo duration của supplier không nhất thiết bao gồm fallback hoặc toàn bộ request nghiệp vụ. Nếu cần phân biệt thời gian dependency với thời gian end-to-end, tạo hai timer ở hai ranh giới rõ ràng thay vì gộp vào một metric. Không ghi thêm một timer tùy chỉnh trùng hoàn toàn với timer Resilience4j nếu không có câu hỏi quan sát cụ thể cần trả lời.

## 7. Đo thời gian dependency bằng Timer có tái sử dụng

Khi cần metric nghiệp vụ riêng cho lời gọi inventory, khởi tạo timer một lần và ghi thời lượng quanh client call:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Service
public class InventoryClientMetrics {

    private final InventoryClient client;
    private final Timer dependencyTimer;

    public InventoryClientMetrics(
            InventoryClient client,
            MeterRegistry registry) {
        this.client = client;
        this.dependencyTimer = Timer.builder("dependency.client.duration")
            .description("Time spent waiting for the inventory dependency")
            .tag("dependency", "inventory")
            .register(registry);
    }

    public InventoryResult fetch(String sku) {
        long started = System.nanoTime();
        try {
            return client.fetch(sku);
        } finally {
            dependencyTimer.record(
                System.nanoTime() - started,
                TimeUnit.NANOSECONDS
            );
        }
    }
}
```

`finally` bảo đảm timer vẫn ghi nhận thời lượng khi client ném exception. Ví dụ chỉ đo thời gian đồng bộ của client call; với API reactive hoặc `CompletionStage`, phải ghi nhận khi publisher/stage kết thúc, không dừng timer ngay lúc trả về đối tượng bất đồng bộ. Nếu Resilience4j đã xuất timer phù hợp với đúng ranh giới này, hãy dùng meter sẵn có thay vì đo trùng.

Không gắn `sku` vào tag timer. Nếu cần biết SKU nào gây lỗi, ghi giá trị đó vào trace/log có kiểm soát và tuân thủ chính sách dữ liệu của ứng dụng.

## 8. Logging bất đồng bộ vẫn cần queue hữu hạn

Async appender chuyển phần ghi log hoặc truyền log ra khỏi thread request, nhưng không làm chi phí bằng 0. Thread phát event vẫn phải tạo log event, format hoặc chuẩn bị message và enqueue. Khi queue đầy, logging framework có thể block, bỏ log hoặc áp dụng chính sách khác tùy cấu hình.

Nếu cần đưa event sang một worker riêng, dùng queue hữu hạn và quy định rõ hành vi khi quá tải:

```text
Resilience4j event callback
          |
          v
Tạo event summary nhỏ
          |
          v
Bounded queue
    |          |
    | còn chỗ  | đầy
    v          v
Enqueue     Drop/sample low-priority event
    |
    v
Background worker
    |
    v
Log collector / telemetry backend
```

Không tạo một `CompletableFuture.runAsync(...)` mới cho mỗi event rồi đẩy vào common pool mà không có giới hạn. Cách đó có thể tích lũy task không giới hạn khi log backend chậm, khiến bộ nhớ và thread pool cạn. Một queue hữu hạn buộc hệ thống có quyết định rõ: bỏ bớt event tần suất cao, lấy mẫu hoặc áp dụng backpressure có giới hạn.

State transition thường có giá trị chẩn đoán cao và tần suất thấp; có thể xử lý theo một kênh ưu tiên hơn call success. Nếu queue chung đầy, cân nhắc ghi state transition bằng một log ngắn hoặc dùng queue riêng có giới hạn. Không được để telemetry làm treo request nghiệp vụ.

## 9. Lấy mẫu log và trace theo mục tiêu

Các cách giảm log volume thường dùng:

- Ghi đầy đủ state transition vì chúng ít xảy ra và có ý nghĩa vận hành.
- Không log từng success; dùng timer và counter tổng hợp.
- Lấy mẫu call error hoặc slow call theo tỷ lệ, theo chu kỳ hoặc theo một số mẫu đầu tiên của mỗi giai đoạn lỗi.
- Giới hạn stack trace lặp lại; giữ một số ví dụ đủ để xác định loại lỗi và ghi tổng số lần qua metric.
- Dùng trace sampling cho lưu lượng bình thường và chính sách giữ trace lỗi/tail latency theo khả năng của tracing backend.
- Tách log audit của thao tác quản trị khỏi log chẩn đoán có thể lấy mẫu.

Lấy mẫu phải giữ được thông tin cần điều tra. Nếu chỉ ghi một lỗi ngẫu nhiên trong một giờ, có thể bỏ lỡ thời điểm bắt đầu sự cố. Có thể ưu tiên mẫu đầu tiên sau khi breaker chuyển `OPEN`, một số mẫu theo chu kỳ khi lỗi còn tiếp diễn và một mẫu khi breaker phục hồi. Tổng số lỗi vẫn được phản ánh bằng metric.

Không dùng sampling để bỏ qua audit bắt buộc hoặc sự kiện nghiệp vụ cần lưu bền vững. Event publisher của circuit breaker phục vụ quan sát và chẩn đoán; nếu cần audit giao dịch, hãy ghi vào hệ thống audit/domain event có độ bền và semantics riêng.

## 10. Tránh các thao tác nặng trong callback

Callback của event không nên:

- Gọi HTTP, RPC hoặc database để gửi event ngay lập tức.
- Đọc cấu hình từ remote store hoặc truy vấn service discovery.
- Serialize toàn bộ request/response hoặc dump object lớn.
- Ghi stack trace đầy đủ cho mọi call error khi outage.
- Tạo metric với tag chứa giá trị mới cho mỗi request.
- Chờ lock, semaphore hoặc queue không giới hạn thời gian.
- Chạy phép tính thống kê hoặc phân tích đồng bộ trên thread phát event.

Callback nên lấy những trường nhỏ, ổn định như breaker ID, state transition, nhóm lỗi và timestamp. Sau đó cập nhật metric cục bộ hoặc enqueue một event summary vào buffer có giới hạn. Nếu worker không theo kịp, có thể bỏ event chẩn đoán tần suất cao và tăng một counter nội bộ cho số event bị drop.

Ví dụ listener tối giản chỉ ghi state transition:

```java
breaker.getEventPublisher()
    .onStateTransition(event -> {
        log.warn("Circuit breaker transition: {}", event);
    });
```

Không cần đăng ký listener ở mỗi request. Đăng ký một lần trong vòng đời bean và xác minh breaker lấy từ registry chính là instance đang bảo vệ lời gọi. Nếu có nhiều breaker, gắn listener theo từng instance hoặc dùng cơ chế customizer phù hợp với integration.

## 11. Tránh metric và log trùng lặp

Resilience4j/Micrometer đã cung cấp các meter cho call result, state và duration. Nếu ứng dụng lại tạo counter cho mọi success/failure/not-permitted mà không có mục tiêu riêng, dữ liệu sẽ bị nhân đôi và dashboard dễ diễn giải sai.

Chỉ tạo metric tùy chỉnh khi nó trả lời một câu hỏi khác, ví dụ:

- Bao nhiêu request nghiệp vụ đã dùng fallback?
- Bao nhiêu command bị từ chối do dependency không khả dụng?
- Bao nhiêu lần fallback cũng thất bại?
- Bao nhiêu thao tác quản trị đã force-open hoặc reset breaker?

Metric custom nên có tên và đơn vị rõ ràng. Không cộng số fallback thành công vào số lời gọi dependency thành công: đó là hai sự kiện ở hai ranh giới khác nhau. Tương tự, không tính call-not-permitted là lỗi mới của dependency vì supplier không được chạy.

## 12. Benchmark chi phí quan sát

Để biết cấu hình quan sát có làm chậm hot path hay không, đo trong điều kiện tải gần với production. So sánh các lần chạy với cùng dữ liệu và cùng cấu hình nghiệp vụ:

1. Baseline: circuit breaker hoạt động với metric tích hợp tối thiểu, không có log per-call.
2. Metrics: bật các timer/gauge/counter cần thiết.
3. Logging: bật state-transition log và chính sách log lỗi đã lấy mẫu.
4. Histogram/tracing: bật histogram hoặc tracing sampling theo cấu hình dự kiến.
5. Stress telemetry: làm log collector chậm hoặc queue gần đầy để kiểm tra hệ thống khi backend quan sát suy giảm.

Ghi lại throughput, CPU, allocation/GC, p50/p95/p99 của request, độ trễ dependency, số log/giây, số time series và mức sử dụng queue. Đánh giá cả lúc bình thường lẫn lúc breaker `OPEN`, vì call-not-permitted và exception có thể phát sinh theo đợt lớn.

Khi so sánh, giữ nguyên số replica, thread pool, request mix và thời gian warm-up. Không kết luận từ một lần chạy ngắn hoặc chỉ dựa vào latency trung bình. Mục tiêu là xác định phần quan sát nào tạo overhead đáng kể và mức overhead đó có chấp nhận được so với lợi ích chẩn đoán.

## 13. Ví dụ cấu hình quan sát có giới hạn

Một cấu hình cơ bản có thể bật các endpoint cần thiết, gắn tag ứng dụng có cardinality thấp và bật histogram cho timer circuit breaker:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: order-service
      environment: production
    distribution:
      percentiles-histogram:
        resilience4j.circuitbreaker.calls: true
```

Không thêm các tag như user ID, request ID hoặc order ID. Nếu số dependency hoặc pod lớn, tính trước số time series dự kiến trước khi bật histogram cho tất cả tổ hợp. Endpoint Actuator/Prometheus cần được giới hạn truy cập qua mạng giám sát và quyền phù hợp.

Với log, ưu tiên state transition ở mức `WARN` hoặc `INFO` tùy quy ước vận hành; call error lặp lại nên được tổng hợp hoặc lấy mẫu. Đặt log level theo môi trường và tránh bật `DEBUG` cho mọi request trong production trong thời gian dài.

## 14. Checklist thiết kế hot path

- Dùng meter Resilience4j có sẵn trước khi tạo metric trùng lặp.
- Khởi tạo Counter/Timer một lần và tái sử dụng; không đăng ký meter mới theo giá trị request.
- Giữ tag có cardinality thấp và hữu hạn.
- Dùng timer/histogram để tổng hợp độ trễ thay cho log từng lần gọi.
- Ghi log đầy đủ cho state transition; lấy mẫu call error, slow call và call-not-permitted khi lưu lượng cao.
- Không thực hiện I/O mạng, database hoặc xử lý nặng trong event callback.
- Nếu chuyển event sang worker, dùng queue hữu hạn, chính sách drop/backpressure rõ ràng và metric theo dõi queue/drop.
- Không tạo task bất đồng bộ không giới hạn cho mỗi event.
- Tách metric dependency, fallback và request end-to-end; không gộp các loại kết quả khác ranh giới.
- Benchmark p95/p99, CPU, allocation, log volume và cardinality khi bật instrumentation.
- Bảo vệ endpoint telemetry và không ghi dữ liệu nhạy cảm vào tag hoặc log.

Quan sát tốt giúp phát hiện dependency suy giảm, giải thích vì sao circuit breaker mở và đo tác động lên người dùng. Khi chọn đúng mức chi tiết cho từng loại event, dùng metric tổng hợp cho lưu lượng cao và giữ callback ngắn, ứng dụng có thể duy trì khả năng chẩn đoán mà không biến logging hoặc telemetry thành một nguồn nghẽn mới trên đường xử lý chính.
