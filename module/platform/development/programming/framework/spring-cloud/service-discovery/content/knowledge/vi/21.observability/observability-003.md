# Theo dõi số instance và biến động đăng ký theo dịch vụ

Trong hệ thống microservice, một service có thể có nhiều instance và số lượng đó thay đổi liên tục theo deploy, scale, health check, restart hoặc sự cố mạng. Chỉ nhìn dashboard registry tại một thời điểm không đủ để biết hệ thống đang ổn định hay đang liên tục thêm, xóa và thay đổi trạng thái instance.

Cần theo dõi đồng thời hai nhóm dữ liệu:

- **Số instance hiện tại:** bao nhiêu instance đã đăng ký, bao nhiêu instance khỏe, warning, critical hoặc đang ở trạng thái không phục vụ.
- **Biến động đăng ký:** trong một khoảng thời gian có bao nhiêu lần register, deregister, đổi trạng thái, đăng ký thất bại hoặc mất đồng bộ.

Hai nhóm này trả lời hai câu hỏi khác nhau. Gauge cho biết snapshot hiện tại; counter cho biết số sự kiện đã xảy ra. Một service có thể luôn có 5 instance nhưng liên tục thay instance cũ bằng instance mới. Nếu chỉ xem gauge, hiện tượng churn này không xuất hiện.

Bài này trình bày cách thiết kế metric theo service và trạng thái, khai thác metric có sẵn của Eureka và Consul, bổ sung instrumentation bằng Micrometer, truy vấn Prometheus, xây dựng dashboard và cảnh báo biến động đăng ký.

## 1. Cần phân biệt registered, healthy và eligible

Trước khi đếm instance, cần xác định đang đếm tập nào. Registry có thể còn lưu registration của một instance nhưng health check đã báo lỗi. Consumer cũng có thể áp dụng thêm filter để chỉ chọn một phần instance.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Registered instances | Instance còn entry trong registry/catalog | 5 |
| Healthy instances | Instance có trạng thái sức khỏe đạt yêu cầu | 4 |
| Eligible instances | Instance còn lại sau filter của consumer/load balancer | 3 |
| Reachable instances | Instance mà network path từ consumer thực sự kết nối được | Có thể chỉ còn 2 |

Ví dụ service `inventory-service` có 5 registration:

- 3 instance đang UP hoặc passing.
- 1 instance warning.
- 1 instance critical.
- Consumer chỉ lấy instance UP/passing và chỉ chọn zone nội bộ của mình, nên có thể chỉ còn 2 ứng viên.

Không nên đặt một metric tên `service_instance_count` rồi dùng nó cho cả bốn ý nghĩa. Tên và label phải thể hiện rõ tập instance đang được đo.

### 1.1. Đếm theo service và trạng thái

Một snapshot hữu ích có dạng:

| Service | UP / passing | Warning | Critical / DOWN | Tổng đăng ký |
|---|---:|---:|---:|---:|
| inventory-service | 3 | 1 | 1 | 5 |
| order-service | 4 | 0 | 0 | 4 |
| payment-service | 2 | 0 | 1 | 3 |

Tổng đăng ký có thể lớn hơn số instance khỏe. Nếu chỉ hiển thị tổng, operator có thể tưởng service đủ capacity dù nhiều instance đã không nhận traffic.

Trạng thái của các registry khác nhau:

- Eureka thường dùng `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE` và `UNKNOWN`.
- Consul health check dùng `passing`, `warning` và `critical`.
- Một ứng dụng có thể chuẩn hóa các trạng thái này thành `healthy`, `degraded`, `unhealthy` và `unknown` cho dashboard liên registry, nhưng phải giữ lại trạng thái gốc để chẩn đoán.

## 2. Gauge và counter phục vụ hai mục đích khác nhau

Prometheus phân biệt rõ metric phản ánh trạng thái với metric tích lũy sự kiện.

**Gauge** có thể tăng hoặc giảm. Dùng gauge để biểu diễn số instance đang được đăng ký tại thời điểm scrape:

~~~text
service_registry_instances{
  registry="eureka",
  service="inventory-service",
  status="UP"
} 3
~~~

**Counter** chỉ tăng trong vòng đời tiến trình, ngoại trừ reset khi process restart. Dùng counter để đếm sự kiện đăng ký:

~~~text
service_registry_registration_events_total{
  registry="eureka",
  service="inventory-service",
  action="register",
  result="success"
} 42
~~~

Một ví dụ:

- Lúc 10:00 có 5 instance.
- Trong 10 phút tiếp theo, một instance bị deregister và một instance mới đăng ký.
- Lúc 10:10 vẫn có 5 instance.

Gauge vẫn là 5. Counter register tăng 1 và counter deregister tăng 1. Hai metric cùng cần thiết để hiểu biến động.

Quy tắc:

- Số lượng hiện tại, số instance theo status, số lần scrape thành công gần nhất: gauge.
- Tổng register, deregister, status transition và lỗi đăng ký: counter.
- Thời gian thao tác register/deregister hoặc thời gian đồng bộ snapshot: histogram hoặc summary.
- Không dùng `rate()` cho gauge. Dùng `rate()` hoặc `increase()` cho counter.

## 3. Bộ metric đề xuất

Có thể chuẩn hóa một bộ metric độc lập với registry backend. Ví dụ dưới đây là tên metric do đội ứng dụng hoặc exporter tự định nghĩa, không phải tất cả đều được Spring Cloud tự tạo.

| Metric | Type | Label chính | Ý nghĩa |
|---|---|---|---|
| `service_registry_instances` | Gauge | registry, service, status, datacenter | Số registration hiện tại theo trạng thái |
| `service_registry_registration_events_total` | Counter | registry, service, action, result, reason | Số lần register, deregister hoặc đổi status |
| `service_registry_registration_duration_seconds` | Histogram | registry, operation, result | Thời gian register/deregister |
| `service_registry_last_snapshot_timestamp_seconds` | Gauge | registry, datacenter | Unix timestamp lần đọc snapshot thành công gần nhất |
| `service_registry_snapshot_duration_seconds` | Gauge hoặc Histogram | registry, datacenter | Thời gian lấy và tổng hợp snapshot |
| `service_registry_snapshot_errors_total` | Counter | registry, datacenter, reason | Số lần collector không lấy được snapshot |

### 3.1. Chọn label có giới hạn

Các label hữu ích:

- `registry`: eureka, consul, zookeeper hoặc kubernetes.
- `service`: service ID/name.
- `status`: trạng thái gốc hoặc trạng thái đã chuẩn hóa.
- `datacenter` hoặc `cluster`: phạm vi registry.
- `action`: register, deregister, status_change.
- `result`: success hoặc failure.
- `reason`: một tập lý do hữu hạn như startup, graceful_shutdown, health_transition, lease_expired, operator.

Không nên đưa các giá trị có thể thay đổi liên tục vào label:

- Instance ID, pod UID hoặc container ID.
- IP address, hostname động hoặc request ID.
- User ID, trace ID hoặc exception message.
- Timestamp hoặc nội dung log.

Mỗi tổ hợp label tạo một time series. Nếu thêm instance ID và IP cho mọi instance vào mọi metric, cardinality sẽ tăng nhanh khi scale hoặc deploy. Dùng log, event store hoặc registry API để điều tra từng instance; giữ metric ở cấp service và trạng thái.

## 4. Nguồn dữ liệu để đếm instance

Không có một nguồn duy nhất phù hợp cho mọi câu hỏi. Hãy chọn theo mục tiêu:

| Nguồn | Đếm được gì? | Giới hạn |
|---|---|---|
| Registry API / Catalog API | Registration hiện có | Có thể không cho biết trạng thái health chi tiết |
| Health API | Registration cùng check và trạng thái | Cần tổng hợp nhiều check theo chính sách |
| Eureka server metrics | Gauge theo application và instance status | Phải bật; không phải lịch sử event |
| Consul agent telemetry | Hoạt động và hiệu năng của agent/API/catalog | Không phải gauge số instance hiện tại theo service |
| Consumer DiscoveryClient | Tập instance consumer thực sự nhìn thấy | Có thể khác registry do cache và filter |
| LoadBalancer supplier | Tập instance sau các filter của LoadBalancer | Chỉ phản ánh góc nhìn của consumer đó |

Dashboard vận hành nên phân biệt metric phía registry và metric phía consumer. Nếu registry báo 5 instance UP nhưng consumer chỉ nhìn thấy 3, cần điều tra cache, datacenter, ACL, filter, zone hoặc thời gian đồng bộ.

## 5. Theo dõi số instance với Eureka

Eureka nhận registration metadata và heartbeat từ từng instance. Server giữ trạng thái registry; khi heartbeat không được gia hạn theo cơ chế lease, instance có thể bị loại khỏi registry theo chính sách và thời gian cấu hình.

Spring Cloud Netflix có sẵn tính năng Micrometer tên `EurekaInstanceMonitor`. Tính năng này lắng nghe sự kiện registration của Eureka và tạo/cập nhật gauge trong `MeterRegistry`.

Để bật:

~~~yaml
eureka:
  server:
    metrics:
      enabled: true
~~~

Tính năng này mặc định tắt theo tài liệu Spring Cloud Netflix hiện hành.

Gauge mặc định có tên Micrometer `eureka.server.instances` và hai tag:

- `application`: tên application/service.
- `status`: trạng thái instance như UP, DOWN, STARTING, OUT_OF_SERVICE hoặc UNKNOWN.

Khi xuất qua Prometheus, tên metric có thể được chuẩn hóa theo quy ước đặt tên của registry, ví dụ thành `eureka_server_instances`. Tên dùng ở endpoint Actuator metrics và tên đã chuẩn hóa trong Prometheus có thể khác nhau.

Có thể bổ sung tag qua implementation riêng của `EurekaInstanceTagsProvider`. Chỉ thêm tag có tập giá trị giới hạn, chẳng hạn region hoặc environment.

### 5.1. Gauge Eureka cho biết gì?

Ví dụ metric sau khi scrape:

~~~text
eureka_server_instances{
  application="INVENTORY-SERVICE",
  status="UP"
} 3

eureka_server_instances{
  application="INVENTORY-SERVICE",
  status="OUT_OF_SERVICE"
} 1
~~~

Có thể truy vấn tổng số instance theo application và status:

~~~promql
sum by (application, status) (eureka_server_instances)
~~~

Đếm riêng instance UP:

~~~promql
sum by (application) (
  eureka_server_instances{status="UP"}
)
~~~

Đây là gauge về số lượng instance theo trạng thái. Nó giúp nhìn snapshot và xu hướng số lượng, nhưng không cho biết trong khoảng thời gian vừa rồi có bao nhiêu lần đăng ký mới hoặc deregister.

### 5.2. Theo dõi churn của Eureka

Nếu cần biết số lần đăng ký/deregister theo thời gian, cần thêm event instrumentation. Có thể ghi nhận sự kiện tại server-side listener hoặc tầng xử lý registry để phản ánh các thay đổi mà Eureka thực sự chấp nhận.

Phân biệt:

- Register: một registration mới được tạo hoặc được chấp nhận.
- Renew/heartbeat: instance gia hạn lease; đây không phải registration mới.
- Status change: trạng thái instance đổi, ví dụ UP sang OUT_OF_SERVICE.
- Cancel/deregister: registration bị hủy.
- Expiration: registration bị loại do lease hết hạn.

Không đếm mọi heartbeat thành register event. Một instance có thể gửi heartbeat định kỳ rất thường xuyên; nếu tính heartbeat vào churn, biểu đồ sẽ phản ánh nhịp heartbeat thay vì vòng đời instance.

Nếu cần đếm chính xác event, hãy instrument ở nguồn phát sinh sự kiện phía server. Counter đặt ở provider chỉ cho biết client đã cố gắng gọi register hoặc deregister; nó có thể bỏ lỡ abrupt crash hoặc event bị mất khi process kết thúc trước lần scrape.

## 6. Theo dõi số instance với Consul

Consul tách Catalog và Health:

- Catalog lưu service registration, node, address, port, tag và metadata.
- Health API trả registration cùng các check liên quan, cho biết instance đang passing, warning hay critical.

Để đếm tổng registration của một service, có thể truy vấn:

~~~bash
curl http://127.0.0.1:8500/v1/catalog/service/inventory-service
~~~

Mỗi phần tử là một service registration trong catalog. Đếm phần tử để có số registration hiện tại, theo đúng datacenter, namespace và partition mà query sử dụng.

Để đọc health:

~~~bash
curl http://127.0.0.1:8500/v1/health/service/inventory-service
~~~

Để chỉ lấy các node mà mọi health check đều passing:

~~~bash
curl "http://127.0.0.1:8500/v1/health/service/inventory-service?passing"
~~~

Khi xây dựng gauge theo trạng thái, collector có thể phân loại kết quả từ các check theo chính sách thống nhất:

- Có ít nhất một check critical: instance được phân loại critical.
- Không có critical nhưng có check warning: instance được phân loại warning.
- Tất cả check liên quan đều passing: instance được phân loại passing.

Cần ghi rõ collector có tính check cấp node cùng check cấp service hay không. Health API có thể trả các check ở cả hai phạm vi; nếu chỉ đọc check HTTP của service mà bỏ qua node check, số healthy có thể cao hơn góc nhìn của Consul.

### 6.1. Consul agent telemetry không phải instance inventory

Consul agent có các metric liên quan đến Catalog và API:

- `consul.catalog.register` và `consul.catalog.deregister` đo thời gian thao tác catalog, được công bố dạng summary.
- `consul.client.api.catalog_register` đếm request register mà agent nhận.
- `consul.client.api.catalog_deregister` đếm request deregister mà agent nhận.
- `consul.catalog.service.query` đếm truy vấn catalog service.
- `consul.catalog.service.not_found` đếm truy vấn service không tìm thấy.

Các metric này hữu ích để theo dõi tải, lỗi và hiệu năng của Consul. Chúng không phải số instance hiện đang tồn tại theo từng service. Đặc biệt, số API request không nhất thiết bằng số registration thực sự thay đổi vì một request có thể cập nhật entry đã có, được retry hoặc thất bại.

Muốn có gauge số instance theo service và health state, hãy lấy snapshot từ Catalog/Health API hoặc dùng exporter chuyên biệt. Muốn có lịch sử biến động, hãy thu thập event từ nguồn registry hoặc instrument các thao tác register/deregister với kết quả rõ ràng.

### 6.2. Scrape Consul agent metrics

Consul có thể xuất telemetry ở định dạng Prometheus qua endpoint agent. Ví dụ cấu hình scrape:

~~~yaml
scrape_configs:
  - job_name: consul-agent
    metrics_path: /v1/agent/metrics
    params:
      format: ["prometheus"]
    static_configs:
      - targets:
          - consul-agent-1:8500
          - consul-agent-2:8500
~~~

Consul dùng path và query parameter này thay cho endpoint mặc định `/metrics`. Cần bảo vệ endpoint agent, cấu hình ACL/TLS theo môi trường và xác minh retention telemetry phù hợp với phiên bản Consul.

## 7. Tạo snapshot exporter cho số lượng hiện tại

Nếu registry không cung cấp gauge theo service, có thể xây dựng collector chạy định kỳ:

1. Lấy danh sách service cần theo dõi.
2. Truy vấn Catalog hoặc Health API.
3. Tổng hợp số registration theo service và status.
4. Cập nhật gauge.
5. Cập nhật timestamp snapshot thành công.
6. Nếu truy vấn lỗi, tăng error counter và giữ timestamp thành công trước đó để cảnh báo dữ liệu đã cũ.

Ví dụ output:

~~~text
service_registry_instances{
  registry="consul",
  service="inventory-service",
  status="passing",
  datacenter="dc1"
} 3

service_registry_instances{
  registry="consul",
  service="inventory-service",
  status="warning",
  datacenter="dc1"
} 1

service_registry_instances{
  registry="consul",
  service="inventory-service",
  status="critical",
  datacenter="dc1"
} 1

service_registry_last_snapshot_timestamp_seconds{
  registry="consul",
  datacenter="dc1"
} 1795500000
~~~

Timestamp là Unix time của lần snapshot thành công gần nhất. Có thể tính độ cũ bằng PromQL:

~~~promql
time() - service_registry_last_snapshot_timestamp_seconds
~~~

Nếu collector không truy vấn được registry, không được đặt tất cả gauge về 0. Giá trị 0 có nghĩa là snapshot thành công và không có instance; dữ liệu không lấy được phải thể hiện bằng error counter hoặc snapshot age. Nếu đặt 0 khi truy vấn lỗi, dashboard sẽ báo nhầm rằng service đã mất toàn bộ instance.

### 7.1. Collector polling có thể bỏ lỡ biến động nhanh

Giả sử collector đọc snapshot mỗi 30 giây. Một instance được đăng ký và deregister trong khoảng giữa hai lần scrape. Cả hai snapshot có thể đều là 5 instance; gauge không bao giờ thể hiện instance tạm thời đó.

Snapshot trả lời trạng thái tại thời điểm đọc, không phải nhật ký sự kiện. Nếu cần ghi nhận mọi biến động:

- Dùng event listener ở registry server nếu backend hỗ trợ.
- Dùng watch/blocking query để nhận biết thay đổi, sau đó đọc lại snapshot.
- Instrument register/deregister tại điểm thực hiện thao tác.
- Ghi event vào log/event store bền vững nếu cần audit chính xác.

Watch hoặc blocking query thường báo dữ liệu đã thay đổi, không nhất thiết là một bản ghi lịch sử cho từng thao tác. Nếu có nhiều thay đổi giữa hai lần đọc, collector vẫn cần so sánh snapshot hoặc đọc event log có độ bền phù hợp.

## 8. Instrumentation bằng Micrometer

Spring Boot Actuator cung cấp Micrometer và tự cấu hình MeterRegistry khi dependency registry tương ứng có trên classpath. Với Prometheus, thêm các dependency phù hợp với Spring Boot/Spring Cloud BOM của dự án:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Expose endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: never
~~~

Endpoint Prometheus là `/actuator/prometheus`. Endpoint này không được expose mặc định trong mọi cấu hình; cần expose rõ và bảo vệ bằng network policy hoặc Spring Security.

### 8.1. Gauge số instance

Ví dụ một component giữ số lượng theo service và status:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.stereotype.Component;

@Component
public class RegistryInstanceMetrics {

    private final MeterRegistry meterRegistry;

    private final ConcurrentMap<String, AtomicInteger> counts =
            new ConcurrentHashMap<>();

    public RegistryInstanceMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void setCount(
            String registry,
            String service,
            String status,
            int count
    ) {
        String key = registry + "|" + service + "|" + status;

        AtomicInteger value = counts.computeIfAbsent(key, ignored -> {
            AtomicInteger holder = new AtomicInteger();

            Gauge.builder(
                    "service.registry.instances",
                    holder,
                    AtomicInteger::get
            )
            .tag("registry", registry)
            .tag("service", service)
            .tag("status", status)
            .register(meterRegistry);

            return holder;
        });

        value.set(count);
    }
}
~~~

Collector gọi `setCount` sau mỗi snapshot thành công. Đối tượng `AtomicInteger` được giữ trong map để backing object của gauge còn sống; không tạo gauge từ một object tạm thời rồi để nó bị garbage collection.

Ví dụ này minh họa một collector đơn giản. Trong production, cần xử lý entry của service/status đã biến mất, quy tắc chuẩn hóa trạng thái và đồng bộ khi nhiều collector cùng cập nhật.

### 8.2. Counter cho register và deregister

Có thể ghi sự kiện tại nơi ứng dụng hoặc registry server xác nhận thao tác:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.stereotype.Component;

@Component
public class RegistryEventMetrics {

    private final MeterRegistry meterRegistry;

    public RegistryEventMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void record(
            String registry,
            String service,
            String action,
            String result,
            String reason
    ) {
        Counter.builder("service.registry.registration.events")
                .tag("registry", registry)
                .tag("service", service)
                .tag("action", action)
                .tag("result", result)
                .tag("reason", reason)
                .register(meterRegistry)
                .increment();
    }
}
~~~

Các giá trị label nên lấy từ enum hoặc tập hữu hạn, ví dụ:

- action: `register`, `deregister`, `status_change`.
- result: `success`, `failure`.
- reason: `startup`, `graceful_shutdown`, `health_transition`, `lease_expired`, `operator`.

Hãy ghi counter sau khi biết kết quả thao tác. Nếu muốn theo dõi cả request thử và kết quả cuối, dùng metric riêng cho attempt và success/failure; đừng gộp hai ý nghĩa vào cùng một counter.

Không ghi heartbeat renew vào counter registration. Nếu cần quan sát heartbeat, tạo metric riêng cho renew request, renew failure hoặc lease expiration.

### 8.3. Đo thời gian thao tác

Có thể dùng Timer/DistributionSummary hoặc Histogram để theo dõi thời gian thao tác register/deregister. Ví dụ:

~~~java
import io.micrometer.core.instrument.Timer;

Timer.Sample sample = Timer.start(meterRegistry);

try {
    registryClient.register(instance);
    sample.stop(Timer.builder("service.registry.registration.duration")
            .tag("registry", "consul")
            .tag("operation", "register")
            .tag("result", "success")
            .register(meterRegistry));
} catch (RuntimeException ex) {
    sample.stop(Timer.builder("service.registry.registration.duration")
            .tag("registry", "consul")
            .tag("operation", "register")
            .tag("result", "failure")
            .register(meterRegistry));
    throw ex;
}
~~~

Ví dụ cần đặt tại adapter thực hiện thao tác registry. Nếu instrumentation đặt ở một tầng gọi bên ngoài, timer có thể bao gồm retry, queue hoặc network delay; hãy xác định rõ latency đang đo là thời gian client call hay thời gian registry commit.

## 9. Cấu hình Prometheus scrape

Ví dụ Prometheus scrape ứng dụng Spring Boot:

~~~yaml
scrape_configs:
  - job_name: spring-services
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - order-service-1:8080
          - inventory-service-1:8080
          - payment-service-1:8080
~~~

Trong môi trường động, có thể dùng Kubernetes service discovery, Consul service discovery hoặc file-based service discovery thay cho danh sách tĩnh. Mỗi target nên được scrape độc lập để phân biệt metric của từng process.

Không nên scrape một endpoint gateway chung nếu mục tiêu là đếm metric per-instance của ứng dụng. Gateway có thể chỉ xuất metric của chính gateway và che khuất instance backend.

## 10. PromQL cho số lượng và biến động

Các truy vấn sau giả định metric custom đã được xuất theo tên Prometheus tương ứng. Micrometer có thể chuẩn hóa dấu chấm thành dấu gạch dưới khi xuất; hãy kiểm tra tên thực tế tại `/actuator/prometheus`.

### 10.1. Số instance theo service và status

~~~promql
sum by (service, status) (
  service_registry_instances
)
~~~

### 10.2. Số instance khỏe theo service

Nếu status gốc là Eureka:

~~~promql
sum by (service) (
  service_registry_instances{status="UP"}
)
~~~

Nếu status gốc là Consul:

~~~promql
sum by (service) (
  service_registry_instances{status="passing"}
)
~~~

Nếu đã chuẩn hóa về health_state:

~~~promql
sum by (service) (
  service_registry_instances{health_state="healthy"}
)
~~~

Chỉ dùng một quy ước trạng thái nhất quán trong cùng dashboard. Không cộng trực tiếp UP với passing nếu metric không chuẩn hóa hoặc label registry không được tách.

### 10.3. Số lần register và deregister trong 15 phút

~~~promql
sum by (service, action) (
  increase(
    service_registry_registration_events_total{
      action=~"register|deregister",
      result="success"
    }[15m]
  )
)
~~~

### 10.4. Tốc độ biến động registration

~~~promql
sum by (service) (
  rate(
    service_registry_registration_events_total{
      action=~"register|deregister",
      result="success"
    }[5m]
  )
)
~~~

Đây là tốc độ sự kiện mỗi giây. Nếu muốn tổng số sự kiện trong cửa sổ thời gian, dùng `increase()`.

### 10.5. Lỗi đăng ký

~~~promql
sum by (service, operation) (
  increase(
    service_registry_registration_failures_total[5m]
  )
)
~~~

### 10.6. Tuổi snapshot

~~~promql
time() - service_registry_last_snapshot_timestamp_seconds
~~~

Nếu giá trị tăng liên tục, collector không cập nhật snapshot thành công. Phân biệt trường hợp này với gauge instance bằng 0.

## 11. Thiết kế dashboard

Một dashboard theo dõi service discovery nên có các panel sau:

| Panel | Kiểu hiển thị | Câu hỏi trả lời |
|---|---|---|
| Instance hiện tại theo service/status | Stacked bar hoặc stacked area | Service đang có bao nhiêu instance UP, warning, critical? |
| Register/deregister theo thời gian | Time series | Có deploy, scale hoặc churn bất thường không? |
| Status transition | Time series | Instance có liên tục chuyển UP/DOWN không? |
| Registration failure | Time series | Registry có từ chối hoặc không nhận thao tác không? |
| Registration latency | Histogram/quantile | Thao tác đăng ký có chậm bất thường không? |
| Snapshot age | Stat/time series | Collector có đang đọc được registry không? |
| Healthy vs desired capacity | Gauge/bar | Số instance khỏe có thấp hơn nhu cầu không? |

Nên cho phép lọc theo registry, service, environment, cluster và datacenter. Nếu có nhiều vùng, cần so sánh tổng số instance với số instance tại từng vùng để phát hiện lệch phân bố.

Một dashboard chỉ có panel tổng instance sẽ khó nhận ra các trường hợp:

- Tổng số không đổi nhưng instance bị thay liên tục.
- Tổng registration cao nhưng healthy thấp.
- Collector không đọc được registry và đang hiển thị snapshot cũ.
- Consumer nhìn thấy ít instance hơn registry.
- Một datacenter mất registration trong khi các datacenter khác vẫn bình thường.

## 12. Cảnh báo nên tập trung vào hành vi có ý nghĩa

Không phải mọi lần register/deregister đều là sự cố. Rolling deployment có thể tạo churn bình thường. Cảnh báo nên xét service criticality, capacity mong muốn, thời gian kéo dài và tỷ lệ thay đổi.

### 12.1. Không còn instance khỏe

~~~yaml
groups:
  - name: service-discovery
    rules:
      - alert: ServiceHasNoHealthyInstances
        expr: |
          sum by (service) (
            service_registry_instances{status=~"UP|passing"}
          ) == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.service }} không còn instance khỏe"
~~~

Metric gauge cần xuất giá trị 0 cho service đã biết ngay cả khi không có instance. Nếu time series biến mất hoàn toàn, biểu thức trên có thể không trả về series; khi đó cần dùng `absent()` hoặc recording rule dựa trên inventory service đã biết.

### 12.2. Churn tăng đột biến

~~~yaml
- alert: ServiceRegistrationChurnHigh
  expr: |
    sum by (service) (
      increase(
        service_registry_registration_events_total{
          action=~"register|deregister"
        }[10m]
      )
    ) > 20
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Service {{ $labels.service }} có nhiều biến động đăng ký"
~~~

Ngưỡng 20 chỉ là ví dụ. Hãy đặt baseline theo quy mô service và lịch deploy. Một service có hàng trăm instance có mức biến động bình thường khác một service chỉ có hai instance.

### 12.3. Lỗi đăng ký tăng

~~~yaml
- alert: ServiceRegistrationFailures
  expr: |
    sum by (service) (
      increase(
        service_registry_registration_events_total{result="failure"}[5m]
      )
    ) > 0
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "Có lỗi đăng ký service {{ $labels.service }}"
~~~

### 12.4. Snapshot đã cũ

~~~yaml
- alert: ServiceRegistrySnapshotStale
  expr: |
    time() - service_registry_last_snapshot_timestamp_seconds > 120
  for: 1m
  labels:
    severity: warning
  annotations:
    summary: "Snapshot registry đã cũ"
~~~

Cần đặt ngưỡng theo chu kỳ polling và thời gian timeout. Nếu collector chạy mỗi 30 giây, ngưỡng 120 giây có thể hợp lý để bắt lỗi kéo dài, nhưng phải hiệu chỉnh theo môi trường.

## 13. Registration churn và các nguyên nhân thường gặp

Churn là hiện tượng instance liên tục xuất hiện, biến mất hoặc thay đổi trạng thái trong một khoảng thời gian. Một mức churn nhỏ là bình thường khi deploy hoặc scale. Churn cao kéo dài có thể gây tăng tải registry, cache refresh, DNS update và load balancer re-selection.

| Dấu hiệu | Nguyên nhân có thể | Dữ liệu cần đối chiếu |
|---|---|---|
| Register/deregister tăng theo chu kỳ | Rolling deployment, autoscaling hoặc restart loop | Deployment event, pod restart, desired replicas |
| Instance chuyển UP/DOWN liên tục | Health check chập chờn, timeout quá ngắn | Health check latency, dependency health, log |
| Instance biến mất sau network interruption | Lease/session hết hạn | Heartbeat, session event, network error |
| Register thất bại | ACL, auth, sai service name hoặc registry unavailable | Registry logs, ACL metrics, client errors |
| Registry count cao nhưng UP thấp | Nhiều registration còn tồn tại nhưng health không đạt | Eureka status hoặc Consul checks |
| Consumer thấy ít instance hơn registry | Cache cũ, filter, zone, datacenter hoặc namespace | DiscoveryClient và LoadBalancer supplier |
| Chỉ một datacenter thiếu instance | Replication, federation hoặc cấu hình region | Datacenter/region metrics và registry state |

### 13.1. Phân biệt churn thật và heartbeat

Eureka dùng heartbeat để gia hạn lease. Heartbeat tăng không đồng nghĩa registration churn tăng. Nếu chỉ số heartbeat tăng cùng lúc với số instance không đổi, đó có thể chỉ là hoạt động bình thường của client.

Consul có health check và agent telemetry. Một check chuyển passing sang critical rồi trở lại passing là status transition, không nhất thiết registration bị deregister và register lại.

Hãy tách ba loại event:

1. **Registration lifecycle:** tạo hoặc xóa registration.
2. **Health/status transition:** instance vẫn tồn tại nhưng trạng thái thay đổi.
3. **Liveness/heartbeat:** client hoặc agent đang gia hạn lease/session hoặc thực hiện check định kỳ.

## 14. Độ mới dữ liệu và độ lệch giữa registry với consumer

Registry snapshot, discovery cache và LoadBalancer cache có thể cập nhật ở thời điểm khác nhau. Vì vậy, dashboard cần chỉ ra nguồn metric và thời điểm snapshot.

Ví dụ:

- Eureka Server có 5 instance UP.
- Eureka Client của consumer đã fetch registry trước lần deregister gần nhất nên vẫn thấy 5.
- LoadBalancer cache còn giữ danh sách 5 instance.
- Một request tiếp theo vẫn có thể chọn endpoint vừa bị xóa.

Để điều tra, hãy lấy số lượng ở ba góc nhìn:

| Góc nhìn | Metric hoặc phép kiểm tra |
|---|---|
| Registry server | Số registration và status trong registry |
| DiscoveryClient | Danh sách instance consumer đã nhận |
| LoadBalancer | Danh sách ứng viên sau supplier/filter |

Đừng so sánh hai snapshot được lấy ở thời điểm khác nhau mà không ghi timestamp. Với Consul, hãy giữ datacenter, namespace, partition và filter nhất quán giữa các truy vấn. Với Eureka, kiểm tra trạng thái peer replication và client fetch interval nếu số liệu giữa server và consumer lệch nhau.

## 15. Bảo mật và quyền truy cập metric

Metrics có thể tiết lộ tên service nội bộ, topology, datacenter, trạng thái triển khai và số lượng instance. Cần:

- Chỉ cho Prometheus hoặc monitoring agent được truy cập endpoint metrics.
- Không expose Actuator metrics/prometheus ra Internet công khai.
- Bảo vệ Consul agent metrics và API bằng network policy, ACL và TLS phù hợp.
- Không đưa token, secret, hostname nhạy cảm hoặc dữ liệu cá nhân vào label.
- Giới hạn quyền truy cập dashboard theo vai trò.
- Không coi metric registration là bằng chứng xác thực service identity.

Nếu metric được scrape từ registry server, exporter cần quyền đọc phù hợp. Không dùng token có quyền ghi registration chỉ để lấy số liệu.

## 16. Quy trình triển khai theo từng bước

1. Chọn nguồn sự thật cho registration: Eureka server, Consul Catalog/Health API hoặc registry khác.
2. Xác định rõ số registered, healthy, eligible và reachable.
3. Bật metric có sẵn của backend nếu phù hợp, ví dụ Eureka instance gauge.
4. Thêm collector snapshot nếu cần count theo service/status mà backend chưa cung cấp.
5. Instrument register, deregister, status change và failure tại nguồn sự kiện.
6. Không tính heartbeat thành registration event.
7. Xuất metric qua Micrometer/Prometheus hoặc telemetry exporter.
8. Xây dashboard theo service, status, datacenter và registry.
9. Thiết lập cảnh báo zero healthy, high churn, registration failure và stale snapshot.
10. Kiểm thử deploy, scale, graceful shutdown, abrupt crash, health failure và registry outage.
11. Đối chiếu registry server với DiscoveryClient và LoadBalancer của consumer.
12. Đánh giá cardinality và retention trước khi mở rộng số label.

## 17. Ghi nhớ

- Số registration hiện tại là gauge; số lần register/deregister là counter.
- Registered, healthy, eligible và reachable là bốn tập khác nhau.
- Eureka có gauge `eureka.server.instances` theo application/status; tính năng cần bật bằng `eureka.server.metrics.enabled=true` và mặc định tắt.
- Consul có metric cho catalog operation và API request; chúng không thay thế gauge inventory theo service.
- Consul Catalog đếm registration; Health API cung cấp check và trạng thái instance.
- Muốn có số lượng theo service/status, dùng registry snapshot hoặc exporter; muốn có lịch sử mọi biến động, thu thập event tại nguồn.
- Không đếm heartbeat như register; status transition cũng không phải deregistration.
- Giữ label cardinality thấp, tránh instance ID, IP, trace ID và exception message.
- Theo dõi timestamp snapshot để phân biệt service không có instance với collector không đọc được registry.
- So sánh registry, DiscoveryClient và LoadBalancer để tìm nguyên nhân lệch số liệu.

Theo dõi số instance cùng với biến động đăng ký giúp phân biệt thiếu capacity, health degradation và churn do triển khai hoặc lỗi mạng. Khi gauge phản ánh snapshot có nguồn rõ ràng và counter phản ánh event thực tế, dashboard có thể cho biết service đang có bao nhiêu instance, trạng thái của chúng ra sao và vì sao số lượng thay đổi.

## Tài liệu tham khảo

- [Spring Cloud Netflix — Eureka Server Metrics](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Consul — Agent Telemetry Metrics](https://developer.hashicorp.com/consul/docs/reference/agent/telemetry)
- [Consul — Catalog HTTP API](https://developer.hashicorp.com/consul/api-docs/catalog)
- [Consul — Health HTTP API](https://developer.hashicorp.com/consul/api-docs/health)
- [Spring Boot — Actuator Metrics and Prometheus](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Prometheus — Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus — Metric Types](https://prometheus.io/docs/concepts/metric_types/)
