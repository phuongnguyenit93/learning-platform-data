# Tích hợp Actuator, resilience4j-micrometer và hệ thống thu thập số liệu

Circuit Breaker chỉ giúp bảo vệ dịch vụ khi đội phát triển và vận hành hiểu được nó đang ở trạng thái nào, bao nhiêu lời gọi thành công hoặc thất bại, tỷ lệ lời gọi chậm có tăng hay không và fallback được sử dụng thường xuyên đến mức nào. Nếu chỉ cấu hình ngưỡng trong application.yml mà không thu thập số liệu, rất khó biết ngưỡng đó có phù hợp với lưu lượng thực tế hay Circuit Breaker đang mở mạch quá thường xuyên.

Spring Boot Actuator cung cấp các endpoint quản trị và quan sát ứng dụng. Micrometer chuẩn hóa cách ghi nhận metrics và chuyển dữ liệu đến hệ thống giám sát. Resilience4j cung cấp module resilience4j-micrometer để xuất các chỉ số của Circuit Breaker, Retry, Bulkhead và những cơ chế phục hồi khác. Prometheus có thể định kỳ thu thập các metrics này, còn Grafana dùng dữ liệu để xây dựng dashboard và cảnh báo.

Bài học trình bày cách kết nối các thành phần đó trong ứng dụng Spring Cloud CircuitBreaker dùng Resilience4j, cách đọc metrics, cách theo dõi trạng thái và cách bảo vệ endpoint Actuator khi đưa ứng dụng lên môi trường thật.

## 1. Kiến trúc thu thập và hiển thị metrics

Trong một ứng dụng Order gọi Inventory qua Circuit Breaker, luồng quan sát có thể được tổ chức như sau:

~~~text
Order Service
  |
  +--> CircuitBreaker "inventory"
  |       |
  |       +--> state, calls, failure rate, slow-call rate
  |
  +--> Spring Boot Actuator
          |
          +--> Micrometer MeterRegistry
                    |
                    +--> Prometheus registry
                              |
                              v
                         /actuator/prometheus
                              |
                              v
                         Prometheus server
                              |
                              v
                         Grafana dashboard
                         Alerts / notifications
~~~

Mỗi thành phần có trách nhiệm riêng:

- **Resilience4j** ghi nhận kết quả và trạng thái của các cơ chế bảo vệ.
- **resilience4j-micrometer** chuyển các dữ liệu đó thành meter có tên và tag thống nhất.
- **Micrometer** cung cấp API chung để ứng dụng không phải phụ thuộc trực tiếp vào định dạng của một hệ thống giám sát.
- **Spring Boot Actuator** quản lý endpoint metrics, health và endpoint Prometheus.
- **Prometheus** scrape metrics từ các instance ứng dụng theo chu kỳ.
- **Grafana** truy vấn dữ liệu từ Prometheus để hiển thị xu hướng, dashboard và cảnh báo.

Metrics khác với log và trace. Metrics phù hợp để tổng hợp xu hướng theo thời gian; log giúp điều tra một sự kiện cụ thể; trace thể hiện đường đi và thời gian của một request qua nhiều dịch vụ. Nên kết hợp cả ba khi vận hành hệ thống phân tán.

## 2. Chuẩn bị dependency

Trong ứng dụng Spring Boot dùng Spring Cloud CircuitBreaker với Resilience4j, cần có Actuator và module metrics của Resilience4j. Nếu muốn Prometheus scrape trực tiếp endpoint của ứng dụng, thêm Prometheus registry của Micrometer.

Ví dụ dependency Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-micrometer</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Các phiên bản nên được quản lý bằng Spring Boot dependency management và Spring Cloud BOM tương thích. Không nên tự chọn phiên bản Spring Cloud, Resilience4j và Micrometer riêng lẻ mà không kiểm tra ma trận tương thích của dự án.

Spring Boot Actuator đã đưa Micrometer core vào dependency graph, vì vậy thông thường không cần khai báo micrometer-core trực tiếp. Module resilience4j-micrometer cung cấp bộ chuyển đổi metrics của Resilience4j sang Micrometer. Prometheus registry cung cấp định dạng scrape mà Prometheus hiểu được.

Nếu ứng dụng chỉ cần xem metrics cục bộ qua Actuator, không nhất thiết phải thêm Prometheus registry. Nếu hệ thống giám sát dùng backend khác như OTLP, Datadog hoặc một registry được Micrometer hỗ trợ, hãy thêm registry tương ứng và cấu hình exporter theo môi trường.

## 3. Cấu hình Circuit Breaker và Actuator

Ví dụ application.yml cho một Circuit Breaker tên inventory:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus

  endpoint:
    health:
      show-details: when_authorized

  health:
    circuitbreakers:
      enabled: true

  metrics:
    tags:
      application: order-service
~~~

Cấu hình Circuit Breaker tạo cửa sổ 20 lời gọi gần nhất và cần ít nhất 10 mẫu trước khi đánh giá tỷ lệ. Failure rate hoặc slow-call rate đạt 50% có thể làm mạch chuyển sang OPEN. Các ngưỡng này chỉ là giá trị minh họa, cần được điều chỉnh theo độ trễ bình thường, lưu lượng và mục tiêu độ tin cậy của dependency.

Trong phần Actuator:

- health cung cấp trạng thái sức khỏe ứng dụng.
- info cung cấp thông tin ứng dụng đã được cấu hình.
- metrics cho phép kiểm tra meter và tag đang có.
- prometheus xuất dữ liệu theo định dạng Prometheus scrape.

Endpoint Prometheus chỉ xuất hiện khi micrometer-registry-prometheus có trên classpath. Endpoint metrics và Prometheus không nhất thiết có cùng tên hiển thị: Micrometer dùng tên meter chuẩn hóa theo quy ước của registry đích.

Chỉ expose những endpoint thực sự cần thiết. Mặc định Spring Boot chỉ expose health qua HTTP. Không nên mở tất cả endpoint bằng dấu * trên mạng công khai.

## 4. Resilience4j tự động đưa metrics vào Micrometer như thế nào?

Khi dùng Spring Cloud CircuitBreaker Resilience4j với đúng dependency, phần auto-configuration có thể thiết lập việc thu thập metrics. Các dependency quan trọng là:

- spring-boot-starter-actuator
- resilience4j-micrometer

Spring Cloud CircuitBreaker Resilience4j có auto-configuration cho metrics khi các dependency cần thiết có mặt. Không cần tự tạo một MeterRegistry thứ hai hoặc tự bind lại cùng registry nếu auto-configuration đã thực hiện việc đó.

Với ứng dụng dùng Resilience4j trực tiếp, không dùng auto-configuration tương ứng, có thể bind registry bằng API của Resilience4j:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.micrometer.tagged.TaggedCircuitBreakerMetrics;
import io.micrometer.core.instrument.MeterRegistry;

public class CircuitBreakerMetricsConfiguration {

    public void bindMetrics(
            CircuitBreakerRegistry circuitBreakerRegistry,
            MeterRegistry meterRegistry) {

        TaggedCircuitBreakerMetrics
            .ofCircuitBreakerRegistry(circuitBreakerRegistry)
            .bindTo(meterRegistry);
    }
}
~~~

TaggedCircuitBreakerMetrics đăng ký metrics cho các instance trong registry và có thể theo dõi các instance được tạo thêm sau đó thông qua cơ chế event của registry. Chỉ dùng cách bind thủ công khi ứng dụng chưa có cơ chế auto-configuration tương đương. Bind lặp cùng một registry có thể gây meter trùng hoặc lỗi đăng ký tên meter.

Khi ứng dụng dùng CircuitBreakerFactory của Spring Cloud, hãy giữ đúng registry và provider do cấu hình Spring quản lý. Không tự tạo một CircuitBreakerRegistry độc lập chỉ để lấy metrics, vì registry đó có thể không chứa instance đang bảo vệ lời gọi nghiệp vụ.

## 5. Những metrics quan trọng của Circuit Breaker

Resilience4j cung cấp nhiều meter. Tên và tag cụ thể có thể khác theo phiên bản module, nhưng các nhóm chỉ số phổ biến gồm:

| Metric | Loại dữ liệu | Ý nghĩa |
| --- | --- | --- |
| resilience4j.circuitbreaker.calls | Timer | Số lượng và thời gian của các lời gọi thành công, thất bại hoặc bị bỏ qua |
| resilience4j.circuitbreaker.state | Gauge | Trạng thái hiện tại của Circuit Breaker |
| resilience4j.circuitbreaker.failure.rate | Gauge | Tỷ lệ lời gọi thất bại trong cửa sổ đánh giá |
| resilience4j.circuitbreaker.slow.call.rate | Gauge | Tỷ lệ lời gọi chậm trong cửa sổ đánh giá |
| resilience4j.circuitbreaker.buffered.calls | Gauge | Số lời gọi thành công và thất bại đang được lưu trong cửa sổ |
| resilience4j.circuitbreaker.max.buffered.calls | Gauge | Số mẫu tối đa của cửa sổ hiện tại |
| resilience4j.circuitbreaker.not.permitted.calls | Counter | Số lời gọi bị từ chối vì Circuit Breaker không cho phép thực thi |

Các meter thường có tag name để xác định instance. Metric calls còn có tag kind để phân biệt successful, failed và ignored. Metric state có tag state để phân biệt closed, open, half_open và các trạng thái đặc biệt được phiên bản hỗ trợ.

Ví dụ, inventory là tên instance được khai báo trong application.yml. Khi xem metrics, hãy lọc theo tag name=inventory để không cộng nhầm số liệu của Payment hoặc Shipping.

Không nên tự suy luận trạng thái từ một counter đơn lẻ. Ví dụ, số lời gọi thất bại tăng có thể là dấu hiệu dependency gặp lỗi, nhưng cần xem thêm failure rate, tổng số mẫu, slow-call rate và trạng thái hiện tại để hiểu tình huống.

## 6. Đọc metrics qua Actuator

Khi đã bật Actuator và expose endpoint metrics, có thể liệt kê các meter hiện có:

~~~bash
curl http://localhost:8080/actuator/metrics
~~~

Tìm meter của Circuit Breaker:

~~~bash
curl http://localhost:8080/actuator/metrics/resilience4j.circuitbreaker.calls
~~~

Endpoint trả về các measurement và tag có thể lọc. Ví dụ truy vấn riêng instance inventory và các lời gọi thất bại:

~~~bash
curl "http://localhost:8080/actuator/metrics/resilience4j.circuitbreaker.calls?tag=name:inventory&tag=kind:failed"
~~~

Có thể kiểm tra state:

~~~bash
curl "http://localhost:8080/actuator/metrics/resilience4j.circuitbreaker.state?tag=name:inventory&tag=state:open"
~~~

Nếu meter không tồn tại, hãy kiểm tra lần lượt:

1. Actuator có trong classpath hay chưa.
2. resilience4j-micrometer có trong classpath hay chưa.
3. Spring Cloud CircuitBreaker có đang dùng Resilience4j provider hay không.
4. Instance inventory đã được tạo và có lời gọi đi qua hay chưa.
5. Endpoint metrics đã được expose hay chưa.
6. Có cấu hình tắt metrics của Spring Cloud CircuitBreaker Resilience4j hay không.
7. Có đang xem nhầm registry hoặc nhầm tên instance hay không.

Tên meter trong endpoint Actuator dùng dạng tên Micrometer. Tên hiển thị trong Prometheus có thể được chuẩn hóa thành chữ thường và dấu gạch dưới. Khi truy vấn Actuator, hãy dùng tên meter được trả về từ endpoint /actuator/metrics.

## 7. Xuất metrics cho Prometheus

Prometheus hoạt động theo mô hình scrape: server Prometheus định kỳ gọi endpoint của từng instance ứng dụng để lấy số liệu. Thêm dependency micrometer-registry-prometheus và expose endpoint prometheus:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Kiểm tra endpoint từ máy có quyền truy cập:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Nếu cấu hình đúng, response chứa các dòng metrics theo định dạng Prometheus. Tên meter Micrometer như resilience4j.circuitbreaker.calls có thể được chuyển thành dạng resilience4j_circuitbreaker_calls_seconds_count và các series liên quan theo quy tắc Prometheus.

Ví dụ cấu hình scrape trong prometheus.yml:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: order-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - order-service:8080
~~~

Trong môi trường Docker hoặc Kubernetes, target cần dùng hostname và port mà Prometheus thực sự truy cập được. Không dùng localhost trong cấu hình Prometheus nếu ứng dụng chạy ở container khác, vì localhost khi đó trỏ về chính container Prometheus.

Nếu Actuator endpoint nằm ở management port riêng, metrics_path và target phải dùng đúng port quản trị. Nếu endpoint yêu cầu xác thực, cấu hình Prometheus để gửi thông tin xác thực qua secret hoặc cơ chế bảo mật phù hợp; không ghi credential trực tiếp vào file cấu hình được commit vào repository.

## 8. Xây dựng dashboard theo câu hỏi vận hành

Dashboard tốt giúp trả lời câu hỏi cụ thể thay vì chỉ hiển thị thật nhiều biểu đồ. Với Circuit Breaker, nên có các khu vực sau:

| Khu vực dashboard | Chỉ số cần hiển thị | Câu hỏi vận hành |
| --- | --- | --- |
| Trạng thái | State theo từng instance | Dependency nào đang OPEN hoặc HALF_OPEN? |
| Lưu lượng | Calls theo kind và instance | Có bao nhiêu lời gọi thành công hoặc thất bại? |
| Tỷ lệ lỗi | Failure rate và slow-call rate | Chất lượng dependency đang xấu đi đến mức nào? |
| Từ chối | Not permitted calls | Có bao nhiêu request bị Circuit Breaker chặn? |
| Độ trễ | Thời gian lời gọi và HTTP client latency | Request chậm ở Circuit Breaker hay ở tầng HTTP? |
| Fallback | Số lần fallback theo dependency | Người dùng đang nhận kết quả suy giảm thường xuyên đến đâu? |
| Tài nguyên | Thread, connection pool, bulkhead rejection | Sự cố dependency có làm cạn tài nguyên caller không? |

Không nên chỉ theo dõi trạng thái OPEN. Một Circuit Breaker có thể chuyển OPEN trong thời gian ngắn rồi phục hồi, nhưng failure rate hoặc slow-call rate vẫn tăng cao. Dashboard nên hiển thị xu hướng theo thời gian và cho phép drill-down theo tên instance.

Nên có một bảng tổng hợp cho từng dependency, gồm trạng thái, failure rate, slow-call rate, số lời gọi bị từ chối và số fallback. Khi nhiều instance cùng được bảo vệ, tên instance cần ổn định để dashboard và alert không tạo ra một chuỗi series mới sau mỗi lần triển khai.

## 9. Ví dụ truy vấn và cảnh báo Prometheus

Sau khi scrape thành công, Prometheus lưu các time series. Các tên dưới đây minh họa dạng tên đã được chuẩn hóa từ Micrometer; hãy xác nhận tên và tag thực tế tại endpoint Prometheus của ứng dụng.

Trạng thái OPEN của Inventory:

~~~promql
resilience4j_circuitbreaker_state{
  name="inventory",
  state="open"
} == 1
~~~

Tốc độ lời gọi thất bại trong 5 phút:

~~~promql
rate(
  resilience4j_circuitbreaker_calls_seconds_count{
    name="inventory",
    kind="failed"
  }[5m]
)
~~~

Failure rate hiện tại:

~~~promql
resilience4j_circuitbreaker_failure_rate{
  name="inventory"
}
~~~

Có thể tạo alert khi Circuit Breaker ở OPEN liên tục:

~~~yaml
groups:
  - name: circuit-breaker-alerts
    rules:
      - alert: InventoryCircuitBreakerOpen
        expr: resilience4j_circuitbreaker_state{name="inventory",state="open"} == 1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: Inventory Circuit Breaker is OPEN
          description: Requests to Inventory are being rejected by the circuit breaker.
~~~

Alert cần gắn với hành động vận hành rõ ràng. Ví dụ, khi Inventory OPEN liên tục, người trực có thể kiểm tra health của Inventory, tỷ lệ lỗi HTTP, latency, kết nối mạng và số request bị từ chối. Không nên cảnh báo chỉ vì một lần chuyển trạng thái rất ngắn nếu hệ thống có thể tự phục hồi nhanh và không ảnh hưởng người dùng.

Khi đặt alert theo failure rate, cần thêm điều kiện số mẫu tối thiểu hoặc dựa trên metric của Circuit Breaker đã thực hiện minimumNumberOfCalls. Một tỷ lệ 100% từ một mẫu duy nhất có thể gây cảnh báo nhiễu nếu không xét lượng request.

## 10. Health indicator và trạng thái ứng dụng

Actuator health và Circuit Breaker metrics phục vụ các mục tiêu khác nhau:

- Health endpoint trả trạng thái sức khỏe theo các HealthIndicator và nhóm health được cấu hình.
- Metrics cung cấp số liệu liên tục về lời gọi, tỷ lệ lỗi và trạng thái.
- Readiness cho biết instance có nên nhận traffic mới hay không.
- Liveness cho biết tiến trình có còn sống và có thể tiếp tục chạy hay không.

Resilience4j có thể đăng ký health indicator cho Circuit Breaker bằng registerHealthIndicator. Khi bật health indicator, trạng thái OPEN có thể làm thành phần Circuit Breaker báo DOWN và ảnh hưởng trạng thái tổng hợp của /actuator/health.

Điều này cần được cân nhắc trước khi bật trong production. Một dependency Inventory đang OPEN không nhất thiết có nghĩa tiến trình Order đã chết. Nếu Order vẫn phục vụ được các chức năng khác hoặc trả fallback có kiểm soát, đánh dấu toàn bộ ứng dụng DOWN có thể khiến nền tảng loại instance khỏi traffic, tạo thêm sự cố.

Không nên đưa trạng thái dependency vào liveness probe. Nếu cần dùng cho readiness, hãy quyết định theo khả năng phục vụ nghiệp vụ của instance và thiết kế health group riêng. Có thể giữ liveness độc lập với Circuit Breaker, đồng thời dùng metrics và alert để đội vận hành theo dõi dependency.

Ví dụ cấu hình health indicator là lựa chọn có chủ đích:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true

management:
  health:
    circuitbreakers:
      enabled: true
~~~

Hãy kiểm tra mapping trạng thái theo phiên bản Resilience4j Spring Boot integration đang dùng và xác nhận ảnh hưởng trên health endpoint trước khi đưa cấu hình vào readiness probe.

## 11. Theo dõi thêm Retry, Bulkhead, TimeLimiter và HTTP client

Circuit Breaker không hoạt động một mình. Nếu ứng dụng kết hợp nhiều chính sách, dashboard cần thể hiện được ranh giới của từng cơ chế.

| Cơ chế | Metrics cần theo dõi |
| --- | --- |
| Retry | Số lần gọi thành công ở attempt đầu, thành công sau retry, thất bại sau khi hết lượt |
| Bulkhead | Số lời gọi đang dùng permit, số lời gọi bị từ chối, thread pool và queue |
| TimeLimiter | Số timeout, thời gian hoàn tất và số tác vụ bị hủy nếu có |
| HTTP client | Request count, response status, latency, connection timeout và response timeout |
| Circuit Breaker | State, calls, failure rate, slow-call rate và not-permitted calls |

Khi số lần retry tăng, failure rate của Circuit Breaker có thể được diễn giải khác nhau tùy thứ tự bao chính sách. Nếu Circuit Breaker nằm trong Retry, mỗi attempt có thể tạo một mẫu. Nếu Circuit Breaker bao ngoài Retry, nó thường nhận kết quả cuối cùng của chuỗi retry. Dashboard nên thể hiện cả attempt count và request count để tránh hiểu nhầm.

Nếu Bulkhead thường xuyên từ chối lời gọi nhưng Circuit Breaker vẫn CLOSED, có thể caller đã hết ngân sách concurrency mà dependency chưa được đánh giá là lỗi. Nếu TimeLimiter timeout tăng đồng thời với slow-call rate, cần kiểm tra response time và timeout budget. Quan sát nhiều chỉ số cùng lúc giúp xác định đúng tầng gây nghẽn.

## 12. Kết hợp metrics, log và distributed tracing

Metrics cho biết có bao nhiêu lỗi và xu hướng thay đổi; log và trace giúp tìm nguyên nhân của một request cụ thể.

Một log hữu ích có thể gồm:

- Tên Circuit Breaker instance.
- Trạng thái trước và sau khi chuyển.
- Loại sự kiện: success, error, call not permitted hoặc state transition.
- Correlation ID hoặc trace ID nếu có.
- Tên dependency và route nghiệp vụ.
- Exception class đã được lọc thông tin nhạy cảm.

Có thể đăng ký event listener trên Circuit Breaker để ghi nhận chuyển trạng thái:

~~~java
CircuitBreaker inventory = circuitBreakerRegistry
    .circuitBreaker("inventory");

inventory.getEventPublisher()
    .onStateTransition(event ->
        log.warn(
            "CircuitBreaker inventory state changed: {}",
            event.getStateTransition()
        )
    )
    .onCallNotPermitted(event ->
        log.warn("CircuitBreaker inventory rejected a call")
    )
    .onError(event ->
        log.debug(
            "CircuitBreaker inventory recorded an error",
            event.getThrowable()
        )
    );
~~~

Không nên ghi log mọi lời gọi thành công ở mức WARN hoặc ERROR. Với lưu lượng lớn, log từng event có thể tạo ra tải và chi phí lưu trữ đáng kể. Dùng metrics để tổng hợp thành công; log các sự kiện quan trọng như chuyển trạng thái, từ chối hàng loạt hoặc lỗi bất thường.

Trace nên được tạo ở ranh giới request và truyền qua HTTP client được instrument. Khi có trace ID trong log, người vận hành có thể tìm span tương ứng để biết thời gian nằm ở gateway, HTTP client hay service đích. Không đưa access token, cookie hoặc dữ liệu bí mật vào tag, log hay trace attribute.

## 13. Tránh cardinality cao và dữ liệu nhạy cảm

Micrometer sử dụng tag để phân nhóm metrics. Tag có số lượng giá trị không giới hạn có thể tạo ra hàng trăm nghìn hoặc hàng triệu time series, làm tăng bộ nhớ và chi phí của Prometheus.

Các tag phù hợp thường là:

- application hoặc service name.
- dependency hoặc Circuit Breaker instance name.
- operation name có tập giá trị hữu hạn.
- outcome hoặc kind.
- environment hoặc region có danh sách giới hạn.

Không nên dùng các giá trị sau làm tag metrics:

- User ID hoặc customer ID.
- Order ID hoặc transaction ID.
- Correlation ID hoặc trace ID.
- URL đầy đủ chứa path variable.
- Exception message hoặc dữ liệu request tùy ý.

Các giá trị có cardinality cao phù hợp hơn với log hoặc trace có chính sách lưu trữ và truy vấn phù hợp. Cũng không được ghi access token, refresh token, mật khẩu, cookie phiên hoặc bí mật vào log hay metrics.

Tag application trong ví dụ application.yml có giá trị cố định:

~~~yaml
management:
  metrics:
    tags:
      application: order-service
      environment: production
~~~

Không nên đặt tên instance theo request hoặc người dùng. Một instance như inventory là hợp lý; inventory-user-123 hoặc inventory-order-456 sẽ tạo quá nhiều meter và làm mất ý nghĩa quản lý theo dependency.

## 14. Bảo mật endpoint Actuator

Actuator endpoint có thể tiết lộ thông tin về ứng dụng, tài nguyên, cấu hình và lưu lượng. Endpoint metrics thường không chứa access token, nhưng vẫn có thể cho thấy tên dependency, lỗi nội bộ, trạng thái và mô hình tải. Endpoint env, configprops, heapdump hoặc threaddump còn có thể chứa dữ liệu nhạy cảm hoặc thông tin vận hành sâu hơn.

Một số nguyên tắc bảo vệ:

1. Chỉ expose các endpoint cần thiết như health, info, metrics và prometheus.
2. Đặt endpoint quản trị trên mạng nội bộ hoặc management port riêng khi phù hợp.
3. Bảo vệ endpoint bằng Spring Security, gateway nội bộ, network policy hoặc xác thực của nền tảng.
4. Giới hạn quyền đọc metrics và quyền xem chi tiết health theo vai trò.
5. Không expose toàn bộ endpoint bằng dấu * trên internet.
6. Dùng secret management cho thông tin xác thực của Prometheus hoặc hệ thống thu thập.
7. Kiểm tra endpoint sau mỗi lần triển khai để chắc chắn không vô tình mở thêm endpoint.

Có thể cấu hình management server trên port riêng:

~~~yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
~~~

Cấu hình bind vào loopback chỉ phù hợp khi Prometheus hoặc agent thu thập chạy trên cùng host. Trong Kubernetes hoặc môi trường container, cần dùng network và service riêng để chỉ cho phép hệ thống giám sát truy cập.

Nếu endpoint được truy cập từ mạng khác, không nên chỉ dựa vào việc đổi port để bảo mật. Hãy dùng TLS, xác thực và kiểm soát truy cập mạng phù hợp với hạ tầng.

## 15. Quy trình kiểm tra từ ứng dụng đến dashboard

Sau khi cấu hình xong, kiểm tra theo trình tự để tìm lỗi ở đúng tầng:

1. Xác nhận ứng dụng khởi động với dependency Actuator, resilience4j-micrometer và Prometheus registry.
2. Gửi request thành công qua Circuit Breaker inventory.
3. Tạo một số request thất bại hoặc chậm để Circuit Breaker ghi nhận mẫu.
4. Gọi /actuator/metrics và xác nhận meter resilience4j.circuitbreaker.calls có mặt.
5. Truy vấn meter theo tag name=inventory và kind phù hợp.
6. Gọi /actuator/prometheus và xác nhận các series của Circuit Breaker được xuất.
7. Kiểm tra Prometheus target đang UP và có dữ liệu mới.
8. Tạo dashboard Grafana theo state, failure rate, slow-call rate, calls và not-permitted calls.
9. Thử mở mạch có kiểm soát và xác nhận dashboard, alert phản ánh trạng thái.
10. Khôi phục dependency, quan sát HALF_OPEN rồi CLOSED.
11. Kiểm tra endpoint Actuator chỉ được truy cập bởi thành phần có quyền.
12. Kiểm tra tag không chứa ID request, người dùng hoặc dữ liệu nhạy cảm.

Nếu Prometheus target UP nhưng không có metric Circuit Breaker, có thể registry đang scrape đúng endpoint nhưng Resilience4j metrics chưa được bind. Nếu Actuator metrics có dữ liệu nhưng Prometheus không có, kiểm tra endpoint prometheus, registry dependency, scrape path, port và quyền truy cập. Nếu dashboard hiển thị nhiều series bất thường, kiểm tra tag cardinality.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có endpoint /actuator/prometheus | Thiếu micrometer-registry-prometheus hoặc chưa expose endpoint | Thêm registry và expose prometheus |
| Endpoint metrics không có meter Resilience4j | Thiếu resilience4j-micrometer hoặc auto-configuration không hoạt động | Kiểm tra dependency và Resilience4j provider |
| Không thấy metric calls của inventory | Instance chưa được tạo hoặc không có lời gọi đi qua | Kiểm tra tên instance và luồng request |
| Meter được đăng ký trùng | Auto-configuration và code thủ công cùng bind một registry | Chỉ giữ một cơ chế đăng ký metrics |
| Prometheus target DOWN | Sai host, port, path, TLS hoặc xác thực | Kiểm tra scrape target và truy cập endpoint từ Prometheus |
| Dashboard hiển thị tên metric khác | Registry chuẩn hóa tên theo quy ước Prometheus | Kiểm tra raw exposition tại /actuator/prometheus |
| Health chuyển DOWN khi Circuit Breaker OPEN | Circuit Breaker health indicator tham gia health tổng hợp | Xem lại việc bật indicator và health group |
| Alert tăng đột biến | Ngưỡng thấp hoặc số mẫu quá ít | Kết hợp failure rate với lưu lượng và thời gian duy trì |
| Prometheus có quá nhiều time series | Tag chứa user ID, request ID hoặc dữ liệu thay đổi liên tục | Dùng tag có tập giá trị hữu hạn |
| Metrics endpoint bị truy cập công khai | Exposure hoặc network policy quá rộng | Giới hạn endpoint, xác thực và phân đoạn mạng |

## 17. Nguyên tắc vận hành

- Dùng Actuator để công bố các endpoint quan sát cần thiết.
- Dùng resilience4j-micrometer để xuất metrics của đúng registry Circuit Breaker đang bảo vệ lời gọi.
- Dùng một cơ chế bind metrics; tránh đăng ký trùng.
- Dùng Prometheus hoặc backend Micrometer phù hợp để lưu dữ liệu theo thời gian.
- Dùng Grafana để theo dõi trạng thái, failure rate, slow-call rate, rejection và fallback.
- Kết hợp metrics với log và trace để điều tra request cụ thể.
- Đặt alert theo thời gian duy trì và số mẫu đủ lớn, tránh cảnh báo nhiễu.
- Không để Circuit Breaker OPEN tự động làm liveness của cả ứng dụng thất bại nếu ứng dụng vẫn có thể phục vụ chức năng khác.
- Tránh tag cardinality cao và tuyệt đối không đưa bí mật vào metrics.
- Bảo vệ endpoint Actuator bằng xác thực và kiểm soát mạng.

Actuator, Micrometer và resilience4j-micrometer tạo thành đường thu thập dữ liệu từ Circuit Breaker đến hệ thống giám sát. Khi các meter được gắn đúng instance, Prometheus scrape thành công và dashboard hiển thị cả trạng thái lẫn tỷ lệ lỗi, đội vận hành có thể nhận biết dependency đang suy giảm, đánh giá hiệu quả của ngưỡng bảo vệ và xử lý sự cố dựa trên dữ liệu. Việc giới hạn endpoint, kiểm soát tag và kết hợp metrics với log cùng tracing giúp quá trình quan sát hữu ích mà vẫn an toàn trong môi trường production.

## Tài liệu tham khảo

- [Spring Cloud CircuitBreaker — Collecting Metrics](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/collecting-metrics.html)
- [Resilience4j Micrometer](https://resilience4j.readme.io/docs/micrometer)
- [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Actuator Endpoints and Exposure](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)

