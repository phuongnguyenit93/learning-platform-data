# Đo lỗi đăng ký, lỗi truy vấn và độ trễ kết nối sổ đăng ký

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt lỗi đăng ký service, lỗi truy vấn discovery và kết quả truy vấn không có instance.
- Đo số lần thành công/thất bại và độ trễ của thao tác register, deregister, lookup.
- Tách thời gian thiết lập kết nối đến registry khỏi thời gian thực hiện request HTTP hoặc truy vấn discovery.
- Dùng Micrometer để tạo counter, timer và gauge với nhãn có cardinality được kiểm soát.
- Xuất metric qua Spring Boot Actuator, Prometheus và xây dựng dashboard/alert.
- Dùng metric để khoanh vùng lỗi cấu hình, mạng, xác thực, registry server và cache phía client.

## 1. Vì sao cần đo riêng từng loại hoạt động?

Service registry là thành phần hạ tầng quan trọng. Nếu provider không đăng ký được, consumer có thể không tìm thấy instance. Nếu lookup chậm, request nghiệp vụ có thể tăng latency dù các service vẫn hoạt động. Nếu kết nối đến registry chập chờn, client có thể dùng dữ liệu cache cũ hoặc không cập nhật được danh sách instance.

Không nên gộp mọi vấn đề thành một metric tên discovery.errors. Cần phân biệt ít nhất ba nhóm:

1. **Registration:** provider đăng ký hoặc hủy đăng ký instance.
2. **Discovery lookup:** consumer tìm service ID và lấy danh sách instance.
3. **Registry connectivity/request:** client thiết lập kết nối và gửi request đến registry.

| Nhóm | Câu hỏi cần trả lời | Metric quan trọng |
| --- | --- | --- |
| Registration | Bao nhiêu lần đăng ký thất bại? Thời gian đăng ký có tăng không? | Operation count, failure count/rate, operation duration, retry count. |
| Lookup | Bao nhiêu truy vấn có instance, rỗng hoặc lỗi? Lookup mất bao lâu? | Lookup count theo outcome, empty result count, lookup duration, instance count. |
| Connectivity | Client có kết nối được registry không? Kết nối hoặc request mất bao lâu? | Connection state, connect attempt/result, connect duration, registry request duration. |

Ba nhóm có liên quan nhưng không đồng nghĩa. Một lần lookup trả danh sách rỗng có thể là kết quả hợp lệ. Một lần lookup phát sinh timeout là lỗi truy vấn. Một HTTP request đến registry có thể chậm dù kết nối TCP đã được tái sử dụng từ connection pool.

## 2. Phân biệt operation, request và kết nối

Cần xác định chính xác metric đang đo thời gian nào:

- **Registration duration:** thời gian từ lúc ứng dụng bắt đầu thao tác đăng ký đến khi client API hoàn tất hoặc phát sinh lỗi.
- **Lookup duration:** thời gian từ lúc gọi DiscoveryClient.getInstances() đến khi có kết quả hoặc exception. Thời gian này có thể bao gồm đọc cache, xử lý local và/hoặc truy vấn registry tùy implementation.
- **Registry request duration:** thời gian thực hiện một request HTTP/gRPC hoặc một thao tác protocol đến registry, tính ở phía client.
- **Connection establishment duration:** thời gian từ lúc bắt đầu thiết lập kết nối mới đến lúc kết nối sẵn sàng. Tùy transport, khoảng này có thể gồm DNS resolution, TCP handshake và TLS handshake.
- **Connection state:** trạng thái kết nối hiện tại hoặc sự kiện chuyển trạng thái, ví dụ CONNECTED, SUSPENDED, RECONNECTED, LOST với Curator.

Một Timer bọc quanh getInstances() đo lookup duration, không tự động đo thời gian bắt tay TCP. Khi HTTP client tái sử dụng connection pool, nhiều request không thiết lập kết nối mới. Vì vậy, không được gọi request duration là connect latency.

Đối với Eureka, cần đo HTTP request ở transport mà phiên bản đang sử dụng thực sự khởi tạo. Đối với ZooKeeper/Curator, có thể theo dõi ConnectionStateListener và thời gian từ lúc bắt đầu kết nối đến khi nhận trạng thái CONNECTED/RECONNECTED. Với Consul hoặc client HTTP khác, dùng hook/observation của HTTP client tương ứng.

## 3. Thiết kế metric cho registration

Nên đo riêng các operation:

- register: đăng ký instance mới hoặc đăng ký lại.
- deregister: hủy đăng ký khi shutdown hoặc khi instance bị loại.
- renew/heartbeat: gia hạn lease nếu registry/client có operation tương ứng.
- registration_retry: số lần retry thao tác đăng ký.

Các metric gợi ý:

| Metric logic | Loại | Ý nghĩa |
| --- | --- | --- |
| service.registry.operations | Counter | Tổng số operation register/deregister, phân loại theo outcome. |
| service.registry.operation | Timer | Thời gian hoàn thành operation đăng ký hoặc hủy đăng ký. |
| service.registry.retries | Counter | Số lần retry đăng ký hoặc cập nhật registration. |
| service.registry.registration.active | Gauge | Số instance registration mà ứng dụng cho là đang hoạt động, nếu có nguồn trạng thái đáng tin cậy. |

Nhãn nên giới hạn ở những giá trị ổn định:

- registry: eureka, consul, zookeeper, kubernetes.
- operation: register, deregister, renew.
- outcome: success, failure, timeout, rejected nếu phân loại được.
- service: tên service từ tập cấu hình đã biết, không lấy tùy tiện từ request đầu vào.

### Định nghĩa thế nào là registration thành công?

Với API đồng bộ, operation được xem là thành công khi client hoàn tất mà không phát sinh lỗi theo hợp đồng của implementation. Với API bất đồng bộ, cần đo kết quả cuối cùng của callback/future thay vì chỉ đo thời gian enqueue tác vụ.

Không phải mọi phương thức ServiceRegistry.register() đều trả về response xác nhận registry đã lưu và mọi peer đã nhìn thấy instance. Ví dụ, một phương thức có kiểu trả về void có thể chỉ báo lỗi bằng exception. Counter success trong trường hợp đó có nghĩa thao tác client hoàn tất theo hợp đồng API, không phải bằng chứng toàn bộ consumer đã thấy instance.

Nếu cần xác nhận visibility, đo riêng một tín hiệu như registration.visibility.delay: thời gian từ lúc provider đăng ký đến lúc một lần kiểm tra độc lập nhìn thấy instance. Không trộn visibility delay với registration duration.

## 4. Thiết kế metric cho discovery lookup

Mỗi lần lookup cần được phân loại thành các outcome riêng:

- found: có ít nhất một instance.
- empty: truy vấn thành công nhưng danh sách instance rỗng.
- error: lookup phát sinh exception.
- Có thể bổ sung timeout nếu nhận diện được timeout riêng mà vẫn giữ tổng outcome nhất quán.

Metric gợi ý:

| Metric logic | Loại | Ý nghĩa |
| --- | --- | --- |
| service.discovery.lookups | Counter | Tổng lookup theo service và outcome. |
| service.discovery.lookup | Timer | Độ trễ lookup. |
| service.discovery.instances | Distribution summary/Gauge | Số instance trả về trong mỗi lookup hoặc số instance hiện được cache. |
| service.discovery.empty | Counter | Số lookup không tìm thấy instance. |
| service.discovery.errors | Counter | Số lookup thất bại do exception. |

Không gộp empty vào error. Danh sách rỗng có thể do service chưa đăng ký, service ID sai, namespace/filter không khớp hoặc cache chưa cập nhật. Exception thường phản ánh lỗi kết nối, xác thực, timeout hoặc lỗi implementation.

Khi đếm số instance, cần ghi rõ đây là số lượng tại thời điểm lookup, số lượng trong cache hay số lượng ở registry server. Ba nguồn này có thể khác nhau do cache và độ trễ đồng bộ.

## 5. Đo độ trễ kết nối và request đến registry

Độ trễ kết nối giúp phát hiện các vấn đề trước khi thao tác register/lookup thất bại:

- DNS resolution chậm hoặc không ổn định.
- TCP connect timeout, packet loss hoặc firewall reset.
- TLS handshake chậm, chứng thư hoặc trust chain có vấn đề.
- Connection pool cạn, request phải chờ lấy connection.
- Registry server phản hồi chậm hoặc bị quá tải.

Nên tách các metric sau nếu transport cho phép:

| Metric | Đo khoảng thời gian nào? | Dùng để chẩn đoán |
| --- | --- | --- |
| service.registry.connect | Bắt đầu tạo kết nối mới đến khi kết nối sẵn sàng. | DNS/TCP/TLS hoặc đường mạng. |
| service.registry.connection.acquire | Chờ lấy connection từ pool. | Pool quá nhỏ hoặc connection bị giữ quá lâu. |
| service.registry.request | Gửi request đến khi nhận response. | Registry server, network round-trip và xử lý request. |
| service.registry.connection.events | Số lần chuyển trạng thái kết nối. | Kết nối chập chờn hoặc reconnect liên tục. |
| service.registry.connected | Trạng thái kết nối hiện tại, thường là 0 hoặc 1. | Tình trạng kết nối tại thời điểm scrape. |

Nếu thư viện chỉ cung cấp tổng request duration, hãy ghi đúng tên là request latency. Đừng suy diễn ra connect latency khi không có instrumentation ở tầng connection.

### Đo connection state với Curator

Với ZooKeeper, ConnectionStateListener cung cấp các sự kiện như CONNECTED, SUSPENDED, RECONNECTED và LOST. Có thể dùng chúng để cập nhật gauge và tăng counter sự kiện. Thời gian kết nối ban đầu hoặc reconnect cần được đo từ lúc bắt đầu attempt đến khi nhận sự kiện thành công; không đo từ thời điểm bất kỳ.

Ví dụ khung xử lý sự kiện:

~~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.curator.framework.state.ConnectionState;

public class RegistryConnectionMetrics {

    private final AtomicInteger connected = new AtomicInteger(0);

    public RegistryConnectionMetrics(MeterRegistry meters) {
        Gauge.builder("service.registry.connected", connected, AtomicInteger::get)
                .tag("registry", "zookeeper")
                .register(meters);
    }

    public void onState(ConnectionState state, MeterRegistry meters) {
        switch (state) {
            case CONNECTED:
            case RECONNECTED:
                connected.set(1);
                break;
            case SUSPENDED:
            case LOST:
                connected.set(0);
                break;
            default:
                break;
        }

        Counter.builder("service.registry.connection.events")
                .tag("registry", "zookeeper")
                .tag("state", state.name().toLowerCase())
                .register(meters)
                .increment();
    }
}
~~~~

Đây là phần minh họa instrumentation, không phải bean tự động có sẵn trong mọi Spring Cloud Zookeeper version. Hãy gắn listener vào đúng CuratorFramework do Spring quản lý, theo lifecycle của ứng dụng. Không tạo một Curator client thứ hai chỉ để thu thập metric.

Gauge connected phản ánh trạng thái mà client đang báo. Nó không chứng minh rằng mọi request registry đều thành công hoặc mọi service instance đều khỏe mạnh. SUSPENDED là trạng thái mất kết nối; LOST có ý nghĩa session đã mất theo semantics của phiên bản Curator.

## 6. Instrument DiscoveryClient bằng Micrometer

Spring Boot Actuator sử dụng Micrometer làm facade metrics. Có thể đo lookup ở lớp gọi DiscoveryClient, nơi ứng dụng biết service ID và phân biệt found/empty/error.

Ví dụ helper:

~~~~java
import java.util.List;
import java.util.function.Supplier;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.cloud.client.ServiceInstance;

public class DiscoveryMetrics {

    private final MeterRegistry meters;

    public DiscoveryMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    public List<ServiceInstance> recordLookup(
            String registry,
            String boundedService,
            Supplier<List<ServiceInstance>> lookup) {

        Timer.Sample sample = Timer.start(meters);
        String outcome = "error";

        try {
            List<ServiceInstance> instances = lookup.get();
            outcome = instances.isEmpty() ? "empty" : "found";
            return instances;
        } finally {
            sample.stop(Timer.builder("service.discovery.lookup")
                    .tag("registry", registry)
                    .tag("service", boundedService)
                    .tag("outcome", outcome)
                    .register(meters));

            meters.counter("service.discovery.lookups",
                    "registry", registry,
                    "service", boundedService,
                    "outcome", outcome).increment();
        }
    }
}
~~~~

Cách dùng:

~~~~java
List<ServiceInstance> instances = metrics.recordLookup(
        "eureka",
        "inventory-service",
        () -> discoveryClient.getInstances("inventory-service")
);
~~~~

Nếu getInstances() trả list rỗng, outcome là empty. Nếu phát sinh RuntimeException, outcome giữ giá trị error, timer và counter vẫn được ghi trong finally, còn exception tiếp tục được truyền lên tầng gọi.

Trong ví dụ, boundedService phải đến từ danh sách service ID đã biết hoặc một allowlist. Không dùng giá trị tùy ý do người dùng gửi lên làm metric tag.

## 7. Instrument registration operation

Có thể bọc thao tác register/deregister bằng Timer.Sample và counter. Ví dụ helper nhận một Runnable để không phụ thuộc vào implementation registry:

~~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class RegistrationMetrics {

    private final MeterRegistry meters;

    public RegistrationMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    public void record(
            String registry,
            String boundedService,
            String operation,
            Runnable action) {

        Timer.Sample sample = Timer.start(meters);
        String outcome = "failure";

        try {
            action.run();
            outcome = "success";
        } finally {
            sample.stop(Timer.builder("service.registry.operation")
                    .tag("registry", registry)
                    .tag("service", boundedService)
                    .tag("operation", operation)
                    .tag("outcome", outcome)
                    .register(meters));

            meters.counter("service.registry.operations",
                    "registry", registry,
                    "service", boundedService,
                    "operation", operation,
                    "outcome", outcome).increment();
        }
    }
}
~~~~

Ví dụ gọi:

~~~~java
registrationMetrics.record(
        "eureka",
        "inventory-service",
        "register",
        () -> serviceRegistry.register(registration)
);
~~~~

Trong thực tế, cần đặt wrapper ở đúng ranh giới operation để không đếm trùng khi framework tự retry. Nếu đo từng lần thử, dùng operation/tag riêng như attempt; nếu đo kết quả cuối cùng, chỉ tăng counter một lần cho toàn bộ operation. Ghi rõ semantics trong tên metric và dashboard.

Không bắt exception rồi bỏ qua chỉ để metric outcome thành success. Ví dụ trên giữ nguyên exception để caller xử lý theo chính sách retry/failure.

## 8. Xuất metric bằng Spring Boot Actuator

Thêm Actuator và registry phù hợp. Với Prometheus:

~~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~~

Cấu hình endpoint:

~~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: never
  metrics:
    distribution:
      percentiles-histogram:
        service.registry.operation: true
        service.registry.request: true
        service.registry.connect: true
        service.discovery.lookup: true
~~~~

Endpoint /actuator/metrics hỗ trợ kiểm tra metric trong môi trường phát triển. Endpoint /actuator/prometheus xuất dữ liệu theo định dạng Prometheus khi registry tương ứng đã được cấu hình.

Trong production, giới hạn truy cập management endpoints bằng authentication, network policy hoặc management port riêng. Không công khai endpoint metrics chứa thông tin nội bộ ra Internet.

### Histogram và percentile

Timer mặc định có thể cung cấp count, total time và max. Để tính p95/p99 trong Prometheus, cần bật histogram phù hợp cho các timer. Histogram tạo thêm chuỗi thời gian theo bucket, vì vậy hãy chỉ bật cho metric thực sự cần theo dõi và thiết kế bucket/SLO phù hợp.

Percentile tính tại client và histogram bucket có đặc tính khác nhau. Histogram bucket có thể tổng hợp giữa nhiều instance; percentile client-side thường không thể cộng gộp chính xác thành percentile toàn cụm.

## 9. Metric naming và cardinality

Metric phải có tên và tag ổn định. Ví dụ:

| Metric Micrometer | Prometheus thường thấy | Ý nghĩa |
| --- | --- | --- |
| service.registry.operations Counter | service_registry_operations_total | Tổng register/deregister theo outcome. |
| service.registry.operation Timer | service_registry_operation_seconds_count, _sum, _bucket | Số lần và phân bố thời gian operation. |
| service.discovery.lookups Counter | service_discovery_lookups_total | Tổng lookup theo outcome. |
| service.discovery.lookup Timer | service_discovery_lookup_seconds_count, _sum, _bucket | Phân bố độ trễ lookup. |
| service.registry.connected Gauge | service_registry_connected | Trạng thái kết nối hiện tại. |
| service.registry.connection.events Counter | service_registry_connection_events_total | Số lần phát sinh sự kiện connection state. |

Tên chính xác có thể thay đổi theo naming convention của registry/exporter. Hãy kiểm tra /actuator/prometheus để xác nhận tên thực tế trước khi viết PromQL.

### Tránh cardinality cao

Không dùng các giá trị sau làm tag:

- Instance ID sinh ngẫu nhiên.
- IP/hostname của từng Pod nếu số Pod thay đổi liên tục.
- Request ID, trace ID, correlation ID.
- User ID, tenant ID, order ID.
- URL đầy đủ có query string hoặc exception message.
- Tên service do caller truyền tùy ý.

Nên dùng tag có tập giá trị nhỏ: registry, operation, outcome, environment, service từ allowlist. Exception class có thể dùng nếu tập loại exception được giới hạn và không chứa tên động; nếu không, phân loại thành timeout, connection, authentication, other.

Cardinality cao làm tăng bộ nhớ, chi phí scrape, lưu trữ và truy vấn Prometheus. Thông tin chi tiết như instance ID hoặc trace ID phù hợp hơn với log/tracing, không phải metric label.

## 10. Dashboard và PromQL

Một dashboard quan sát registry nên có ít nhất bốn khu vực:

1. **Registration:** success/failure rate, retry count, p95/p99 registration duration.
2. **Lookup:** found/empty/error rate, số instance trả về, p95/p99 lookup duration.
3. **Connectivity:** connection state, reconnect count, connect duration và registry request duration.
4. **Impact:** request lỗi do không chọn được instance, tỷ lệ 5xx và latency của service caller.

Ví dụ PromQL cho tỷ lệ registration failure:

~~~~promql
sum(rate(service_registry_operations_total{
  operation="register",
  outcome="failure"
}[5m]))
/
clamp_min(
  sum(rate(service_registry_operations_total{
    operation="register"
  }[5m])),
  1
)
~~~~

Tỷ lệ lookup error:

~~~~promql
sum(rate(service_discovery_lookups_total{
  outcome="error"
}[5m]))
/
clamp_min(
  sum(rate(service_discovery_lookups_total[5m])),
  1
)
~~~~

Tỷ lệ lookup empty:

~~~~promql
sum(rate(service_discovery_lookups_total{
  outcome="empty"
}[5m]))
/
clamp_min(
  sum(rate(service_discovery_lookups_total[5m])),
  1
)
~~~~

p95 của registry request duration:

~~~~promql
histogram_quantile(
  0.95,
  sum by (le, registry) (
    rate(service_registry_request_seconds_bucket[5m])
  )
)
~~~~

p99 của discovery lookup:

~~~~promql
histogram_quantile(
  0.99,
  sum by (le, registry, service) (
    rate(service_discovery_lookup_seconds_bucket[5m])
  )
)
~~~~

Các truy vấn trên giả định metric đã được export thành tên Prometheus tương ứng và histogram đã được bật. Điều chỉnh tên metric/tag theo kết quả thực tế của exporter.

Không chỉ xem tỷ lệ. Khi volume thấp, một lỗi có thể làm tỷ lệ tăng mạnh nhưng không ảnh hưởng lớn; khi volume cao, một tỷ lệ lỗi nhỏ cũng có thể gây nhiều request thất bại. Dashboard nên hiển thị cả rate, count tuyệt đối, latency và số instance.

## 11. Alert có ý nghĩa vận hành

Một alert tốt nên gắn với tác động và tồn tại đủ lâu để loại bỏ nhiễu. Ví dụ:

| Alert | Điều kiện gợi ý | Phản ứng |
| --- | --- | --- |
| Registration failure spike | Tỷ lệ registration failure vượt ngưỡng trong vài phút và có đủ số lần thử. | Kiểm tra credential, URL, registry health, network và rollout. |
| Lookup error spike | Lookup error tăng liên tục, không tính outcome empty. | Kiểm tra kết nối registry, timeout, TLS và API server. |
| Lookup empty spike | Tỷ lệ empty tăng bất thường với service quan trọng. | Kiểm tra provider registration, service ID, namespace, label và cache. |
| Registry latency high | p95/p99 request hoặc lookup vượt SLO trong một cửa sổ ổn định. | Kiểm tra server load, connection pool, DNS/TLS và network. |
| Registry disconnected | Gauge connected bằng 0 hoặc connection state lỗi kéo dài. | Kiểm tra ensemble/server, route, DNS và credential. |
| Reconnect storm | Số lần reconnect tăng liên tục. | Kiểm tra network flapping, GC pause, timeout và server saturation. |

Không alert chỉ vì một lần lookup empty. Có service chỉ được deploy theo lịch hoặc không cần instance trong một số môi trường. Alert nên dựa vào service criticality, thời gian kéo dài, traffic thực tế và baseline.

Có thể dùng for trong Prometheus alert rule để yêu cầu điều kiện tồn tại liên tục trước khi gửi cảnh báo. Đặt ngưỡng theo SLO và dữ liệu vận hành thực tế, không sao chép một con số cố định cho mọi registry.

## 12. Quy trình chẩn đoán từ metric

Khi phát hiện consumer không tìm thấy instance, đi theo thứ tự:

1. **Kiểm tra lookup outcome:** là empty hay error? Nếu error, đọc exception category và timeout.
2. **Kiểm tra registration:** provider có tăng registration failure hoặc retry không? Thời điểm lỗi có trùng với deploy không?
3. **Kiểm tra visibility:** operation registration thành công nhưng instance đã xuất hiện trong registry view chưa? Có độ trễ replication/cache không?
4. **Kiểm tra connectivity:** gauge connected, connect attempt, reconnect event và registry request latency có bất thường không?
5. **Kiểm tra server:** registry CPU/memory, request queue, peer/leader state và server-side latency.
6. **Kiểm tra cấu hình:** service ID, namespace, label, URL, TLS, authentication, timeout và proxy.
7. **Đối chiếu log/trace:** dùng timestamp, trace ID trong log/tracing để tìm một lần operation cụ thể; không đưa trace ID thành metric tag.
8. **Xác minh phục hồi:** registration và lookup có trở lại bình thường sau khi sửa lỗi không; dữ liệu cache có được làm mới không?

Ví dụ: lookup empty tăng nhưng lookup error không tăng, trong khi registration failure tăng ở một provider. Khả năng cao consumer truy vấn thành công nhưng provider không đăng ký được. Nếu lookup error và registry request latency cùng tăng, cần điều tra registry/network trước khi kết luận service chưa tồn tại.

## 13. Các lỗi instrumentation thường gặp

- **Đếm retry như operation mới:** làm registration failure rate bị phóng đại. Cần phân biệt logical operation và attempt.
- **Đếm empty là error:** làm dashboard sai ngữ nghĩa và alert nhiễu.
- **Chỉ đo tổng latency:** không biết chậm ở DNS/TCP/TLS, pool acquire, registry server hay local cache.
- **Đo getInstances() rồi gọi đó là network latency:** lookup có thể trả từ cache.
- **Đo enqueue thay vì completion:** metric async báo thành công quá sớm.
- **Gắn instance ID làm tag:** cardinality tăng theo số lần deploy.
- **Bắt exception và trả list rỗng:** lỗi kết nối bị che thành kết quả empty, làm metric sai.
- **Chỉ xem trung bình:** p95/p99 có thể xấu dù average vẫn thấp.
- **Không phân biệt registration accepted với visibility:** provider nghĩ đã đăng ký trong khi consumer chưa nhìn thấy instance.
- **Không kiểm thử khi registry unavailable:** instrumentation chỉ được xác nhận ở happy path.

## 14. Checklist triển khai

- [ ] Có counter cho register/deregister và lookup.
- [ ] Có outcome riêng success, failure, found, empty, error.
- [ ] Có timer cho operation, lookup và registry request.
- [ ] Đo connection establishment riêng nếu transport hỗ trợ.
- [ ] Theo dõi connection state và reconnect event.
- [ ] Định nghĩa rõ registration success có nghĩa gì theo API implementation.
- [ ] Đo visibility delay nếu cần biết consumer nhìn thấy instance khi nào.
- [ ] Dùng Micrometer và export qua Actuator/Prometheus.
- [ ] Bật histogram cho timer cần tính p95/p99.
- [ ] Giới hạn tag vào tập giá trị ổn định; không dùng ID động hoặc dữ liệu cá nhân.
- [ ] Không chuyển exception thành empty result.
- [ ] Dashboard có count, rate, latency và số instance.
- [ ] Alert phân biệt registration failure, lookup error, lookup empty và connectivity.
- [ ] Kiểm thử timeout, DNS/TLS, auth, registry restart, cache stale và retry.
- [ ] Bảo vệ management endpoint và không export dữ liệu nhạy cảm.

## Ghi nhớ

- Registration failure, lookup error và lookup empty là ba outcome khác nhau.
- Timer bọc getInstances() đo lookup duration, không mặc định là TCP/TLS connection latency.
- Request duration, connection-pool acquire time và connection establishment time cần được đặt tên riêng.
- Dùng Micrometer Counter để đếm, Timer để đo thời gian và Gauge để phản ánh trạng thái hiện tại.
- Định nghĩa rõ registration success; API hoàn tất không luôn có nghĩa mọi consumer đã nhìn thấy instance.
- Tách logical operation và retry attempt để tránh đếm trùng.
- Dùng histogram để tổng hợp p95/p99 và giới hạn cardinality của metric tag.
- Kết hợp metric với log, trace và trạng thái registry để tìm nguyên nhân gốc.

## Tài liệu tham khảo chính thức

- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot – Prometheus Endpoint](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus)
- [Micrometer – Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Micrometer – Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html)
- [Prometheus – Histograms and Summaries](https://prometheus.io/docs/practices/histograms/)
- [Spring Cloud Commons – DiscoveryClient and ServiceRegistry](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
