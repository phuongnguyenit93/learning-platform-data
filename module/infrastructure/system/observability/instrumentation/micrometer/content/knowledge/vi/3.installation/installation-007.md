# Khởi tạo registry dùng thật và cung cấp cấu hình kết nối

Micrometer cung cấp API thống nhất để ứng dụng Java ghi nhận metrics, còn một registry cụ thể quyết định cách những số đo đó được xuất đến hệ giám sát. Khi chuyển từ ví dụ học tập sang môi trường chạy thật, ứng dụng cần có registry phù hợp với backend, cấu hình endpoint hoặc cơ chế scrape, thông tin định danh dịch vụ và các thiết lập vận hành cần thiết.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, registry là cầu nối giữa Counter, Gauge, Timer, Distribution Summary trong ứng dụng với hệ thống giám sát. Việc khởi tạo đúng registry giúp ứng dụng Spring Boot xuất metrics ổn định, kiểm soát cardinality, kiểm thử instrumentation và diễn giải được số đo vận hành.

## 1. Chọn registry theo cách hệ giám sát nhận dữ liệu

MeterRegistry là abstraction của Micrometer. PrometheusMeterRegistry, OtlpMeterRegistry và các registry dành cho những backend khác là các triển khai cụ thể. Mỗi triển khai có giao thức và cách cấu hình kết nối riêng.

| Registry | Cách xuất dữ liệu | Cấu hình kết nối nằm ở đâu? | Trường hợp sử dụng |
|---|---|---|---|
| PrometheusMeterRegistry | Pull: ứng dụng phơi bày endpoint metrics | Ứng dụng bật endpoint; Prometheus cấu hình địa chỉ target và chu kỳ scrape | Hệ thống có Prometheus scrape ứng dụng |
| OtlpMeterRegistry | Push: ứng dụng gửi metrics theo OTLP | Ứng dụng cấu hình URL nhận OTLP, chu kỳ export và thông tin xác thực nếu cần | Hệ thống có OpenTelemetry Collector hoặc backend nhận OTLP |
| Registry của nhà cung cấp khác | Tùy backend, thường là push hoặc agent/exporter riêng | Theo endpoint, credential và thuộc tính do registry đó hỗ trợ | Khi tổ chức đã chọn dịch vụ giám sát cụ thể |

Không có một URL kết nối chung cho mọi registry. Với Prometheus, ứng dụng cung cấp endpoint để Prometheus chủ động đọc. Với OTLP, ứng dụng chủ động gửi dữ liệu đến endpoint nhận. Cần xác định mô hình này trước khi viết cấu hình.

Trong môi trường local, SimpleMeterRegistry hữu ích để kiểm tra meter trong bộ nhớ. Nó không xuất dữ liệu đến hệ thống giám sát và dữ liệu mất khi tiến trình dừng, vì vậy không nên dùng làm registry đích duy nhất trong production.

## 2. Thêm dependency của registry

Trong dự án Spring Boot, Actuator cung cấp các endpoint quản trị và tích hợp metrics; dependency registry bổ sung exporter cụ thể. Ví dụ với Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Chọn registry phù hợp với backend đang sử dụng.
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
    // runtimeOnly("io.micrometer:micrometer-registry-otlp")
}
~~~

Hai dòng registry trong ví dụ là hai lựa chọn. Hãy bật đúng dependency cho kiến trúc đang triển khai. Nếu chủ động xuất cùng một bộ metrics đến nhiều backend, có thể cấu hình nhiều registry và xác minh rõ việc fan-out đó là có chủ đích.

Khi dự án dùng Spring Boot dependency management hoặc Spring Boot Gradle plugin, hãy để BOM của Spring Boot quản lý phiên bản Micrometer tương thích. Nếu quản lý dependency thủ công, cần giữ phiên bản registry đồng bộ với micrometer-core và phiên bản Spring Boot đang dùng. Tránh nâng riêng một module registry lên phiên bản không tương thích với các thành phần còn lại.

## 3. Để Spring Boot khởi tạo registry và inject vào ứng dụng

Khi registry dependency có mặt trên classpath, Spring Boot có thể tự cấu hình registry tương ứng và cung cấp MeterRegistry qua dependency injection. Đây là cách phù hợp cho ứng dụng Spring Boot vì framework quản lý vòng đời registry và kết nối nó với các meter được đăng ký trong ứng dụng.

Một component có thể nhận MeterRegistry qua constructor rồi đăng ký meter:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {
    private final Counter completedOrders;
    private final Timer checkoutDuration;

    public CheckoutMetrics(MeterRegistry registry) {
        this.completedOrders = Counter.builder("checkout.orders.completed")
                .description("Number of completed checkout orders")
                .tag("channel", "web")
                .register(registry);

        this.checkoutDuration = Timer.builder("checkout.process")
                .description("Time spent processing a checkout")
                .register(registry);
    }

    public void recordCompletedOrder(Runnable operation) {
        checkoutDuration.record(operation);
        completedOrders.increment();
    }
}
~~~

Trong ví dụ, component chỉ phụ thuộc vào MeterRegistry. Khi đổi từ Prometheus sang OTLP, phần instrumentation vẫn giữ nguyên; thay đổi chính nằm ở dependency và cấu hình registry.

Không nên tự tạo SimpleMeterRegistry trong một component production rồi đăng ký meter vào đó, vì các meter ấy có thể không được registry mà Spring Boot đang xuất quản lý. Với ứng dụng Spring Boot, hãy inject MeterRegistry đã được cấu hình. Chỉ tự khởi tạo một registry cụ thể khi ứng dụng không dùng cơ chế auto-configuration và bạn chủ động quản lý cả vòng đời lẫn endpoint hoặc tác vụ export của nó.

## 4. Cấu hình Prometheus registry theo mô hình pull

Với Prometheus, ứng dụng không cần biết địa chỉ Prometheus server. Ứng dụng cung cấp endpoint metrics; Prometheus server mới là nơi cấu hình địa chỉ ứng dụng cần scrape.

### Cấu hình phía ứng dụng

Ví dụ application.yml:

~~~yaml
spring:
  application:
    name: checkout-service

management:
  endpoints:
    web:
      exposure:
        include: health,prometheus

  metrics:
    tags:
      application: ${spring.application.name}
      environment: ${APP_ENV:dev}
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Cấu hình này thực hiện các việc sau:

- Bật exposure cho endpoint Prometheus của Spring Boot Actuator.
- Thêm tag application và environment để phân biệt dịch vụ và môi trường.
- Bật histogram cho metric thời gian xử lý HTTP để có thể tính percentile từ bucket ở backend hỗ trợ truy vấn histogram.

Với cấu hình mặc định của Actuator, endpoint metrics thường nằm tại /actuator/prometheus. Nếu ứng dụng đổi management base path, dùng cổng quản trị riêng hoặc cấu hình bảo mật, địa chỉ scrape phải khớp với cấu hình thực tế. Chỉ expose endpoint trong mạng giám sát được kiểm soát; không mở endpoint quản trị ra Internet công cộng.

### Cấu hình phía Prometheus server

Trong prometheus.yml, khai báo target mà Prometheus có thể truy cập:

~~~yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: checkout-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - checkout-service:8080
~~~

Tên checkout-service ở đây phải phân giải được từ môi trường chạy Prometheus. Trong Docker Compose, đó có thể là tên service; trong Kubernetes, thường dùng DNS service hoặc cơ chế service discovery. Nếu Actuator chạy trên cổng hoặc đường dẫn khác, cập nhật target và metrics_path tương ứng.

Luồng dữ liệu:

~~~mermaid
flowchart LR
    A["Ứng dụng Spring Boot"] --> B["Micrometer Prometheus registry"]
    B --> C["/actuator/prometheus"]
    D["Prometheus server"] -->|"Scrape theo chu kỳ"| C
    D --> E[("Prometheus TSDB")]
    F["Grafana"] -->|"PromQL"| D
    D -->|"Kết quả truy vấn"| F
~~~

Prometheus scrape endpoint và lưu mẫu vào TSDB của nó. Grafana kết nối đến Prometheus data source và gửi truy vấn PromQL. Nếu Prometheus không scrape được ứng dụng, cần kiểm tra target, DNS, port, đường dẫn, firewall, TLS và xác thực mạng.

## 5. Cấu hình OTLP registry theo mô hình push

Nếu hệ thống dùng OpenTelemetry Collector hoặc backend nhận OTLP, ứng dụng có thể gửi metrics trực tiếp đến endpoint OTLP. Với Micrometer OTLP registry, cần thêm dependency:

~~~kotlin
runtimeOnly("io.micrometer:micrometer-registry-otlp")
~~~

Ví dụ cấu hình Spring Boot gửi metrics bằng OTLP/HTTP:

~~~yaml
spring:
  application:
    name: checkout-service

management:
  metrics:
    tags:
      application: ${spring.application.name}
      environment: ${APP_ENV:prod}

  otlp:
    metrics:
      export:
        url: ${OTLP_METRICS_URL:http://otel-collector:4318/v1/metrics}
        step: 30s
~~~

Trong cấu hình trên:

- OTLP_METRICS_URL là endpoint nhận metrics do môi trường triển khai cung cấp.
- Địa chỉ ví dụ dùng OTLP/HTTP trên cổng 4318 và đường dẫn /v1/metrics. Collector hoặc backend phải bật receiver đúng giao thức và địa chỉ này.
- step là khoảng thời gian registry gom và export số liệu. Chọn giá trị phù hợp với độ trễ chấp nhận được, tải mạng và khả năng tiếp nhận của backend.

Nếu endpoint yêu cầu xác thực, cấu hình header theo cơ chế mà backend hỗ trợ và lấy token từ secret manager hoặc biến môi trường. Ví dụ về cấu trúc header trong application.yml:

~~~yaml
management:
  otlp:
    metrics:
      export:
        headers:
          Authorization: "Bearer ${OTLP_TOKEN}"
~~~

Không ghi token thật vào file cấu hình được commit lên Git. Mỗi môi trường nên cấp URL, credential và chứng thư TLS qua cấu hình triển khai hoặc hệ thống quản lý bí mật. Với HTTPS, kiểm tra trust chain và hostname certificate; không tắt xác minh TLS để né lỗi kết nối.

Ở phía OpenTelemetry Collector, cần bật OTLP receiver đúng giao thức, địa chỉ và cổng; pipeline metrics phải nối receiver đó với processor và exporter đến backend đích. Collector chỉ nhận được dữ liệu khi endpoint mà ứng dụng gọi khớp với receiver đang lắng nghe.

~~~mermaid
flowchart LR
    A["Ứng dụng Java"] --> B["Micrometer OTLP registry"]
    B -->|"OTLP/HTTP export"| C["OpenTelemetry Collector"]
    C --> D["Metrics backend"]
    D --> E["Grafana"]
~~~

Khác với Prometheus pull, ở mô hình này ứng dụng chủ động gửi dữ liệu. Do đó, cần theo dõi lỗi export, timeout, xác thực và khả năng truy cập endpoint từ chính mạng chạy ứng dụng.

## 6. Cấu hình tag và phân phối để metrics có ích

Một registry kết nối thành công vẫn có thể xuất ra dữ liệu khó sử dụng nếu metric thiếu ngữ cảnh hoặc tag có cardinality quá cao. Hãy thiết lập các tag chung có tập giá trị hữu hạn, chẳng hạn:

- application: tên dịch vụ.
- environment: dev, staging hoặc production.
- region: vùng triển khai đã xác định.

Không dùng userId, orderId, sessionId, email hoặc requestId làm tag metric. Mỗi giá trị tag mới có thể tạo thêm một time series; những giá trị gần như duy nhất trên từng request có thể khiến số time series tăng mạnh, làm tăng bộ nhớ, dung lượng lưu trữ và chi phí truy vấn.

Với Timer hoặc Distribution Summary, chỉ bật histogram khi có nhu cầu truy vấn phân phối và percentile. Histogram tạo thêm bucket series nên cần cân nhắc số lượng metric, tag và bucket. Nếu backend cần p95 hoặc p99, xác nhận rằng registry thực sự xuất histogram phù hợp và backend giữ được bucket cần thiết.

Không gắn đơn vị vào tên tag để thay thế cho việc định nghĩa đơn vị đo. Chọn tên metric và đơn vị nhất quán, ghi description dễ hiểu, và giữ cách đặt tên ổn định qua các lần phát hành.

## 7. Kiểm tra registry đã kết nối và export thành công

Sau khi triển khai cấu hình, xác minh từ ứng dụng đến backend theo thứ tự:

1. **Kiểm tra ứng dụng khởi động.** Xem log để phát hiện lỗi tạo registry, thiếu dependency, cấu hình không hợp lệ hoặc không thể tạo kết nối.
2. **Kiểm tra phía Prometheus registry.** Gọi endpoint /actuator/prometheus từ một máy có quyền truy cập. Tìm các metric nền như JVM hoặc HTTP và metric tùy chỉnh như checkout_orders_completed_total. Tên cuối cùng có thể được chuẩn hóa theo quy tắc của registry.
3. **Kiểm tra Prometheus scrape.** Mở trang Targets của Prometheus hoặc truy vấn up{job="checkout-service"}. Giá trị 1 cho biết lần scrape gần nhất thành công; giá trị 0 hoặc target DOWN yêu cầu kiểm tra lỗi scrape.
4. **Kiểm tra phía OTLP.** Xem log của ứng dụng và Collector để tìm lỗi export, timeout, HTTP status, xác thực hoặc sai đường dẫn. Sau đó truy vấn metric ở backend nhận dữ liệu.
5. **Kiểm tra dashboard.** Xác nhận Grafana dùng đúng data source, khoảng thời gian và truy vấn. Nếu backend có dữ liệu nhưng panel trống, kiểm tra truy vấn và bộ lọc của panel.

Một số nguyên nhân phổ biến:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Không có endpoint /actuator/prometheus | Thiếu Prometheus registry hoặc Actuator, endpoint chưa được expose, sai management path/port |
| Prometheus target DOWN | DNS hoặc hostname không phân giải, sai port/path, firewall, TLS hoặc xác thực |
| Ứng dụng không gửi được OTLP | URL sai, receiver chưa bật, lệch HTTP/gRPC, timeout, token hoặc certificate |
| Có metrics nhưng thiếu percentile | Chưa bật histogram, sai cấu hình distribution hoặc backend không giữ bucket |
| Dữ liệu tăng số lượng chuỗi thời gian bất thường | Tag có cardinality cao hoặc metric được đăng ký lặp với nhiều tổ hợp tag |
| Dashboard không có dữ liệu dù backend có metric | Data source, truy vấn, time range hoặc biến lọc không đúng |

Có thể kiểm tra instrumentation bằng SimpleMeterRegistry trong unit test vì registry này cho phép đọc giá trị ngay trong bộ nhớ. Tuy nhiên, kiểm thử đó chỉ xác nhận code ghi nhận meter; nó không chứng minh Prometheus scrape hoặc OTLP export hoạt động. Kết nối thật cần được xác minh trong môi trường tích hợp với backend tương ứng.

## 8. Quy trình triển khai registry cho một dịch vụ Java

Khi đưa registry vào một dịch vụ mới, thực hiện lần lượt:

1. Chọn backend và giao thức: Prometheus pull hoặc OTLP push.
2. Thêm đúng registry dependency và để Spring Boot quản lý phiên bản tương thích.
3. Inject MeterRegistry do Spring Boot cấu hình vào các component instrumentation.
4. Cung cấp endpoint, scrape target hoặc OTLP URL theo đúng mô hình; đưa credential vào secret management.
5. Đặt tag chung có cardinality hữu hạn và cấu hình histogram cho những metric cần phân tích phân phối.
6. Kiểm tra endpoint hoặc export, xác nhận dữ liệu có mặt ở backend, rồi tạo truy vấn và dashboard.

Registry chỉ là một mắt xích trong đường đi của metrics. Một cấu hình dùng thật cần bảo đảm ứng dụng ghi nhận đúng số đo, registry xuất đúng định dạng, kết nối đến đúng đích, backend nhận và lưu được dữ liệu, còn dashboard truy vấn đúng nguồn. Khi từng điểm được xác minh, metrics mới đủ tin cậy để hỗ trợ theo dõi và ra quyết định vận hành.
