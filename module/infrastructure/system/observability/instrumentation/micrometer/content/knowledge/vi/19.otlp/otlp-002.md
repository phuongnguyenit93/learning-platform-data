# Cấu hình endpoint, chu kỳ gửi và thông tin xác thực

Micrometer có thể xuất metrics từ ứng dụng Java qua OpenTelemetry Protocol (OTLP) đến OpenTelemetry Collector hoặc một backend hỗ trợ OTLP. Khi cấu hình đường gửi, cần xác định đúng endpoint nhận metrics, giao thức truyền, chu kỳ publish và thông tin xác thực. Một cấu hình sai path hoặc nhầm cổng HTTP với gRPC có thể khiến ứng dụng vẫn chạy nhưng metrics không đến được collector.

Với registry OTLP của Micrometer, ứng dụng thường gửi metrics theo chu kỳ bằng OTLP/HTTP với Protobuf. Endpoint HTTP mặc định thường dùng cổng 4318 và path /v1/metrics. Cổng 4317 thường dành cho OTLP/gRPC; không thể chỉ đổi số cổng để biến một endpoint gRPC thành endpoint HTTP.

## 1. Luồng gửi metrics qua OTLP

Luồng cơ bản gồm các thành phần:

~~~mermaid
flowchart LR
    A["Ứng dụng Java"] --> B["Micrometer MeterRegistry"]
    B --> C["OTLP Registry"]
    C -->|"OTLP/HTTP Protobuf"| D["OpenTelemetry Collector"]
    D --> E["Backend metrics"]
    E --> F["Dashboard / Alert"]
~~~

Mã nghiệp vụ ghi nhận Counter, Gauge, Timer hoặc DistributionSummary vào MeterRegistry. OTLP registry thu thập các meter theo chu kỳ, chuyển đổi chúng sang OTLP metrics data model và gửi HTTP request đến receiver. Collector tiếp nhận, có thể xử lý hoặc enrich dữ liệu rồi chuyển đến backend qua exporter tương ứng.

Collector giúp tách ứng dụng khỏi backend cuối cùng. Ứng dụng chỉ cần biết endpoint OTLP của collector; collector chịu trách nhiệm định tuyến, batch, retry hoặc chuyển đổi theo cấu hình pipeline của nó.

## 2. Chọn đúng giao thức và endpoint

OpenTelemetry Collector thường có hai cổng mặc định:

| Giao thức | Cổng mặc định | Endpoint metrics |
| --- | ---: | --- |
| OTLP/gRPC | 4317 | Endpoint gRPC của receiver |
| OTLP/HTTP | 4318 | /v1/metrics |

Micrometer OTLP registry sử dụng OTLP/HTTP. Vì vậy, endpoint thường có dạng:

~~~text
http://otel-collector:4318/v1/metrics
~~~

Trong đó:

- Scheme http hoặc https xác định transport.
- Host là tên DNS hoặc địa chỉ của collector mà ứng dụng có thể truy cập.
- Port là cổng HTTP receiver.
- Path /v1/metrics là đường nhận metrics của OTLP/HTTP.

Không cấu hình URL gốc của collector nếu registry yêu cầu URL đầy đủ đến endpoint metrics. Ví dụ, http://otel-collector:4318 có thể thiếu path /v1/metrics. Hãy kiểm tra tài liệu của phiên bản Micrometer đang dùng để xác nhận cách property url được diễn giải.

### Cấu hình receiver trong OpenTelemetry Collector

Ví dụ cấu hình Collector bật receiver OTLP qua HTTP:

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [debug]
~~~

Receiver lắng nghe trên cổng 4318 và pipeline metrics chuyển dữ liệu nhận được sang exporter debug để kiểm tra. Trong production, thay hoặc bổ sung exporter phù hợp với backend, đồng thời cấu hình xác thực và TLS ở vị trí phù hợp với kiến trúc triển khai.

Nếu collector chạy trong container hoặc Kubernetes, host mà ứng dụng dùng phải là DNS/service name có thể phân giải từ network namespace của ứng dụng. localhost chỉ trỏ đến chính container hoặc pod hiện tại, không tự động trỏ đến collector ở container khác.

## 3. Thêm dependency OTLP registry

Với Spring Boot, thường thêm Actuator và OTLP registry:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-otlp")
}
~~~

Spring Boot BOM nên quản lý phiên bản Micrometer để các module có phiên bản tương thích. Không override riêng micrometer-registry-otlp mà không kiểm tra các module Micrometer còn lại.

Khi dependency có mặt và metrics export được bật, Spring Boot auto-configuration tạo registry phù hợp. Các service tiếp tục inject MeterRegistry như khi dùng registry khác:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderMetrics {

    private final MeterRegistry registry;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordCreated() {
        registry.counter(
            "orders.created",
            "channel", "web"
        ).increment();
    }
}
~~~

Mã nghiệp vụ không cần tự gửi HTTP request đến collector. Registry chịu trách nhiệm export metrics theo cấu hình.

## 4. Cấu hình endpoint và chu kỳ gửi trong Spring Boot

Có thể cấu hình OTLP metrics exporter trong application.yml:

~~~yaml
management:
  otlp:
    metrics:
      export:
        enabled: true
        url: http://otel-collector:4318/v1/metrics
        step: 30s
        connect-timeout: 5s
        read-timeout: 10s
        batch-size: 10000
~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Vai trò |
| --- | --- |
| enabled | Bật hoặc tắt export metrics OTLP |
| url | Endpoint OTLP/HTTP nhận metrics |
| step | Khoảng thời gian giữa các lần publish |
| connect-timeout | Thời gian tối đa chờ thiết lập kết nối |
| read-timeout | Thời gian tối đa chờ phản hồi |
| batch-size | Giới hạn số lượng meter được gom trong một batch theo cấu hình registry |

Tên property và giá trị mặc định có thể thay đổi theo phiên bản Spring Boot/Micrometer. Hãy đối chiếu metadata cấu hình của đúng phiên bản dependency mà dự án đang sử dụng trước khi triển khai.

### Chu kỳ step khác scrape interval

Với OTLP push, ứng dụng chủ động publish metrics theo step. Step 30 giây có nghĩa registry gửi theo chu kỳ xấp xỉ 30 giây; nó không phải chu kỳ Prometheus scrape.

| Step | Tác động thường gặp |
| --- | --- |
| Ngắn, ví dụ 10–15 giây | Dữ liệu đến backend nhanh hơn, số lần gửi và overhead mạng tăng |
| Trung bình, ví dụ 30–60 giây | Cân bằng giữa độ trễ cập nhật và chi phí export |
| Dài, ví dụ vài phút | Ít request hơn nhưng dashboard và cảnh báo cập nhật chậm hơn |

Chọn step dựa trên nhu cầu phát hiện sự cố, lưu lượng metrics, kích thước payload và năng lực collector. Step ngắn không tự làm dữ liệu chính xác hơn; nó chỉ thay đổi cách chia khoảng export và tần suất gửi.

Step của registry cũng khác cửa sổ truy vấn ở backend. Ví dụ, registry publish mỗi 30 giây nhưng dashboard có thể tính rate hoặc rolling window trong 5 phút.

## 5. Batch size và giới hạn payload

Registry có thể gom nhiều meter vào một lần gửi. Batch size ảnh hưởng số lượng meter trong một request và kích thước payload:

- Batch quá lớn có thể tạo request nặng, tăng bộ nhớ tạm và thời gian xử lý ở collector.
- Batch quá nhỏ có thể làm tăng số request, overhead HTTP và số lần xử lý ở collector.
- Số meter thực tế còn phụ thuộc tags, histogram buckets, resource attributes và số lượng series được export.

Không nên chọn batch size chỉ theo tổng số meter trong ứng dụng. Hãy quan sát kích thước request, thời gian phản hồi, số lỗi từ collector và tài nguyên của ứng dụng. Nếu registry/phiên bản đang dùng không cung cấp property batch-size, không tự thêm property ngoài hợp đồng cấu hình; hãy kiểm tra khả năng của exporter cụ thể.

## 6. Thông tin xác thực qua HTTP headers

Collector hoặc gateway có thể yêu cầu API key, bearer token hoặc một header tùy chỉnh. OTLP HTTP hỗ trợ gửi headers cùng request. Micrometer/Spring Boot có thể cấu hình map headers theo phiên bản đang sử dụng.

Ví dụ với bearer token:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: https://otel-gateway.example.com/v1/metrics
        headers:
          authorization: Bearer ${OTLP_METRICS_TOKEN}
~~~

Ví dụ với API key:

~~~yaml
management:
  otlp:
    metrics:
      export:
        headers:
          x-api-key: ${OTLP_METRICS_API_KEY}
~~~

Tên header, cách binding map và placeholder cần được kiểm tra theo phiên bản Spring Boot/Micrometer. Gateway có thể yêu cầu tên header khác hoặc token theo định dạng riêng. Không gửi cả bearer token và API key nếu server không yêu cầu.

### Quản lý secret an toàn

- Không ghi token thật vào application.yml, file build, Docker image hoặc repository.
- Đọc secret từ biến môi trường, secret manager hoặc cơ chế quản lý cấu hình an toàn của nền tảng.
- Giới hạn quyền của token chỉ cho phép gửi metrics đến đúng tenant hoặc endpoint.
- Có quy trình xoay vòng và thu hồi token.
- Không log header Authorization, API key hoặc toàn bộ cấu hình chứa secret.
- Không đưa secret vào resource attributes hoặc metric tags.

Placeholder ${OTLP_METRICS_TOKEN} chỉ là ví dụ. Môi trường triển khai phải cung cấp biến đó; nếu không, ứng dụng cần phát hiện cấu hình thiếu ngay khi khởi động thay vì gửi request không xác thực.

## 7. TLS và bảo vệ đường truyền

Khi metrics rời khỏi host hoặc cluster, nên dùng HTTPS để bảo vệ dữ liệu trên đường truyền. Ví dụ:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: https://otel-gateway.example.com/v1/metrics
        headers:
          authorization: Bearer ${OTLP_METRICS_TOKEN}
~~~

Ứng dụng cần tin cậy certificate chain của endpoint và kiểm tra hostname đúng. Không tắt xác minh certificate để xử lý lỗi TLS trong production. Nếu collector dùng CA nội bộ, cấu hình trust store hoặc cơ chế trust certificate phù hợp với runtime Java và HTTP client mà registry sử dụng.

Mutual TLS yêu cầu cả client certificate và private key. Khả năng cấu hình mTLS trực tiếp phụ thuộc phiên bản exporter và HTTP client tích hợp; không giả định các property url/headers đã đủ. Nếu cần mTLS, hãy dùng cơ chế TLS được registry hỗ trợ hoặc đặt OTLP gateway/service mesh ở vị trí có thể quản lý client certificate, đồng thời xác minh end-to-end.

## 8. Resource attributes và metric tags

Resource attributes mô tả nguồn phát telemetry, chẳng hạn service name, phiên bản và môi trường. Metric tags mô tả chiều phân tích của từng meter. Hai loại metadata có mục đích khác nhau.

Ví dụ resource attributes:

~~~yaml
management:
  otlp:
    metrics:
      export:
        resource-attributes:
          service.name: order-service
          service.version: 2.4.0
          deployment.environment: production
~~~

Resource attributes giúp backend phân biệt metrics đến từ service hoặc deployment nào. Tags như channel=web hoặc result=success dùng để phân nhóm một metric nghiệp vụ cụ thể.

Không đưa hostname, pod UID hoặc request ID vào resource attributes nếu mỗi lần triển khai tạo ra quá nhiều resource riêng mà không có nhu cầu truy vấn tương ứng. Tương tự, không đưa dữ liệu định danh cá nhân hoặc secret vào tags. Hãy kiểm soát cardinality ở cả resource và metric dimensions.

## 9. Xử lý lỗi kết nối và phản hồi

Khi không gửi được metrics, nguyên nhân có thể nằm ở nhiều lớp:

| Dấu hiệu | Khả năng cần kiểm tra |
| --- | --- |
| Connection refused | Collector chưa lắng nghe, sai host/port hoặc network policy chặn |
| Unknown host | DNS/service name không phân giải được từ ứng dụng |
| 404 Not Found | Sai path, thường thiếu /v1/metrics hoặc route gateway không đúng |
| 401 Unauthorized | Thiếu token hoặc token không hợp lệ |
| 403 Forbidden | Token không có quyền gửi vào tenant/endpoint |
| 415 Unsupported Media Type | Receiver/gateway không chấp nhận encoding hoặc content type |
| 429 Too Many Requests | Collector/gateway giới hạn tốc độ hoặc quota |
| 5xx | Collector hoặc backend trung gian đang gặp lỗi |
| Timeout | Kết nối, collector hoặc mạng xử lý chậm hơn timeout cấu hình |
| TLS handshake failure | Certificate, hostname, trust store hoặc giao thức TLS không khớp |

Quy trình điều tra:

1. Kiểm tra log của registry để tìm URL, mã phản hồi và lỗi transport; bảo đảm log không chứa secret.
2. Xác minh DNS và kết nối TCP từ đúng container/pod chạy ứng dụng.
3. Kiểm tra receiver OTLP/HTTP có lắng nghe đúng cổng và path không.
4. Kiểm tra token, quyền tenant và TLS trust chain.
5. Xem log hoặc internal telemetry của Collector để xác định request đã đến receiver chưa.
6. Kiểm tra pipeline metrics có receiver và exporter hoạt động không.
7. Kiểm tra backend có nhận dữ liệu và resource attributes đúng không.

Không kết luận chỉ từ việc ứng dụng khởi động thành công. Exporter có thể được tạo đúng nhưng các lần publish sau đó vẫn thất bại do endpoint, xác thực hoặc mạng.

## 10. Kiểm thử endpoint trước khi tích hợp

Trước khi chạy ứng dụng, có thể xác minh Collector đang lắng nghe cổng HTTP và route OTLP/HTTP đã được cấu hình. Một request không có payload metrics hợp lệ có thể nhận phản hồi lỗi; mục tiêu của bước kiểm tra này là xác nhận DNS, TCP, TLS và route, không phải chứng minh telemetry được ingest thành công.

Kiểm thử end-to-end nên dùng một metric có tên dễ nhận diện:

~~~java
Counter counter = registry.counter(
    "otlp.smoke.test",
    "environment", "test"
);
counter.increment();
~~~

Chờ ít nhất một chu kỳ step, sau đó kiểm tra:

- Registry đã thực hiện publish.
- Collector nhận request tại receiver OTLP/HTTP.
- Pipeline metrics đã xử lý dữ liệu.
- Backend xuất hiện metric và resource attributes dự kiến.
- Không có lỗi 401/403, timeout hoặc lỗi decode.

Nếu dùng Spring Boot, có thể tạo integration test với OTLP receiver thử nghiệm hoặc một collector test trong môi trường CI. SimpleMeterRegistry không kiểm tra được HTTP export, headers hoặc OTLP serialization.

## 11. Bảo vệ vận hành khi publish theo chu kỳ

Một số điểm cần theo dõi sau khi triển khai:

- Tỷ lệ publish thành công và số lỗi transport.
- Thời gian gửi request và kích thước payload.
- Số meter/series được export và mức tăng cardinality.
- Tài nguyên CPU, bộ nhớ và số thread liên quan đến exporter.
- Collector receiver accepted/refused records và exporter queue/backpressure nếu có.
- Độ trễ từ lúc ứng dụng ghi nhận đến lúc backend truy vấn được metric.

Step, batch size và timeout có liên quan với nhau. Nếu payload lớn nhưng read-timeout quá ngắn, request có thể thường xuyên timeout. Nếu step quá ngắn so với năng lực collector, lượng request và overhead có thể tăng. Hãy điều chỉnh dựa trên số liệu thực tế thay vì tăng timeout hoặc batch size một cách tùy tiện.

Nếu collector có cơ chế queue/retry, hãy cấu hình và giám sát ở Collector theo tài liệu của phiên bản đang chạy. Không mặc định mọi lỗi export từ ứng dụng đều được lưu bền vững hoặc retry vô hạn; cần xác định rõ nơi chịu trách nhiệm buffering và khả năng mất dữ liệu khi process dừng.

## 12. Cấu hình mẫu tổng hợp

Ví dụ application.yml cho một ứng dụng Spring Boot gửi metrics đến Collector qua HTTPS:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  otlp:
    metrics:
      export:
        enabled: true
        url: https://otel-gateway.example.com/v1/metrics
        step: 30s
        connect-timeout: 5s
        read-timeout: 10s
        batch-size: 10000
        headers:
          authorization: Bearer ${OTLP_METRICS_TOKEN}
        resource-attributes:
          service.name: order-service
          service.version: 2.4.0
          deployment.environment: production
~~~

Mẫu trên minh họa cấu trúc cấu hình; hãy xác minh property nào được hỗ trợ bởi phiên bản Spring Boot đang dùng. Biến OTLP_METRICS_TOKEN phải được cung cấp qua secret store hoặc môi trường triển khai. Endpoint phải hỗ trợ OTLP/HTTP metrics và certificate phải được runtime tin cậy.

Nếu muốn giữ cấu hình trong application.properties:

~~~properties
management.otlp.metrics.export.enabled=true
management.otlp.metrics.export.url=https://otel-gateway.example.com/v1/metrics
management.otlp.metrics.export.step=30s
management.otlp.metrics.export.connect-timeout=5s
management.otlp.metrics.export.read-timeout=10s
management.otlp.metrics.export.batch-size=10000
management.otlp.metrics.export.headers.authorization=Bearer ${OTLP_METRICS_TOKEN}
~~~

Không commit giá trị token thực vào file properties.

## 13. Checklist trước khi đưa OTLP vào production

- [ ] Đã thêm micrometer-registry-otlp đúng phiên bản được BOM quản lý.
- [ ] Endpoint là URL OTLP/HTTP metrics đầy đủ, gồm path /v1/metrics.
- [ ] Collector bật receiver OTLP/HTTP trên cổng phù hợp.
- [ ] Không nhầm cổng HTTP 4318 với gRPC 4317.
- [ ] Step phù hợp với yêu cầu độ mới dữ liệu và năng lực collector.
- [ ] Batch size và timeout được chọn dựa trên payload thực tế.
- [ ] Header xác thực được lấy từ secret store hoặc biến môi trường.
- [ ] HTTPS và certificate validation được bật khi truyền qua mạng cần bảo vệ.
- [ ] Resource attributes mô tả đúng service và deployment.
- [ ] Collector pipeline metrics có exporter đến backend.
- [ ] Đã kiểm thử publish end-to-end và xác minh metric tại backend.
- [ ] Có giám sát lỗi export, backpressure và khả năng mất dữ liệu.

Cấu hình OTLP thành công cần bảo đảm ba lớp cùng khớp: ứng dụng gửi đúng endpoint/giao thức, collector xác thực và nhận được payload, pipeline chuyển metrics đến backend. Step và batch size quyết định nhịp gửi; headers và TLS bảo vệ đường truyền. Kiểm tra end-to-end sau ít nhất một chu kỳ publish là cách xác nhận đáng tin cậy rằng metrics thực sự đi hết pipeline.
