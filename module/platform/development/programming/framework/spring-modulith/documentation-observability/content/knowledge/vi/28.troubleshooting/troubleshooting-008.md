# Exporter không gửi dữ liệu

> **Chương:** Chẩn đoán lỗi
> **Phạm vi:** Spring Modulith Documentation & Observability trên Spring Boot. Trọng tâm là chẩn đoán khi module event metrics, module-entry spans hoặc các tín hiệu telemetry khác không xuất hiện tại OpenTelemetry Collector hay hệ thống quan sát, dù ứng dụng vẫn xử lý nghiệp vụ.

## 1. Hiểu đúng hiện tượng “exporter không gửi dữ liệu”

Ứng dụng `shop` chia thành các application module `orders`, `inventory` và `payments`. Đội phát triển đã tạo module graph bằng Spring Modulith, mở endpoint Actuator `/actuator/modulith`, phát `OrderPlaced` từ module `orders` và cấu hình xuất trace/metric sang OpenTelemetry Collector. Tuy nhiên, dashboard không có dữ liệu `module.events.published`, không tìm thấy span mô-đun, trong khi REST API trả HTTP 200.

Lỗi có thể xảy ra **trước exporter, tại exporter, trong Collector hoặc sau Collector**. Một log có `traceId` không chứng minh trace đã được xuất; HTTP 200 ở `/actuator/modulith` cũng chỉ chứng minh API kiến trúc đang hoạt động. Để tìm nguyên nhân, phải xác định **tín hiệu nào mất và mất ở chặng nào**.

Sau bài học, bạn sẽ:

1. Phân biệt module graph, Micrometer metrics, tracing và cơ chế xuất dữ liệu.
2. Kiểm tra dependency runtime, effective configuration, sampling, endpoint, protocol và credentials.
3. Theo dấu đường đi qua OpenTelemetry Collector và backend bằng bằng chứng có thể quan sát.
4. Dùng probe có kiểm soát để tách lỗi tạo dữ liệu khỏi lỗi vận chuyển.
5. Xác nhận việc sửa lỗi bằng kiểm thử hồi quy, kể cả context propagation giữa các module.

**Nguyên tắc ưu tiên:** kiểm tra từng tầng, ghi nhận kết quả và chuyển sang tầng tiếp theo. Đừng tăng sampling, bật debug toàn bộ hoặc tăng hàng loạt timeout/queue trước khi biết dữ liệu bị mất ở đâu.

## 2. Bản đồ đường đi của telemetry

~~~mermaid
flowchart LR
    A["Nghiệp vụ: orders, payments"] --> B["Spring Modulith instrumentation"]
    B --> C["Micrometer Observation / MeterRegistry"]
    C --> D["Tracing bridge + span exporter"]
    C --> E["Metrics registry / meter exporter"]
    D --> F["OTLP receiver của Collector"]
    E --> F
    F --> G["Processors / routing / filter"]
    G --> H["Collector exporter"]
    H --> I["Trace/metrics backend"]
    I --> J["Query / dashboard"]
    K["ApplicationModules / Documenter"] --> L["Module graph / tài liệu"]
    L -. "Dữ liệu kiến trúc tĩnh" .-> J
~~~

Sơ đồ gộp hai luồng push để dễ chẩn đoán. `Prometheus` theo mô hình thông dụng **kéo (scrape)** từ `/actuator/prometheus`; trong trường hợp đó không có việc ứng dụng tự push metric theo luồng `E → F`. `Documenter` tạo tài liệu module ở thời điểm build, còn `/actuator/modulith` công bố cấu trúc module qua Actuator; **cả hai không phải bằng chứng trace đã tới backend**.

| Bằng chứng | Điều thực sự chứng minh | Điều chưa chứng minh |
| --- | --- | --- |
| `/actuator/modulith` có graph | Bộ phận phát hiện application module và Actuator đang hoạt động. | Có trace/metric, tracer hoặc exporter. |
| `/actuator/metrics/module.events.published` có giá trị | Micrometer đã đăng ký/thu thập metric phát domain event. | Metric được xuất tới Collector/backend. |
| Log có `traceId` / `spanId` | Có trace context trong luồng ghi log. | Span đã được sample/export hoặc backend đã nhận. |
| Exporter log cho thấy HTTP/gRPC thành công | Một request xuất dữ liệu đã được đích tiếp nhận ở lớp giao thức. | Backend lưu trữ và giao diện truy vấn hiển thị đúng signal. |
| Collector có `receiver accepted` | Collector đã tiếp nhận dữ liệu tương ứng. | Processor không drop và downstream exporter đã gửi thành công. |
| Backend query có metric/trace mới | Dữ liệu đến nơi có thể truy vấn. | Mọi nhánh nghiệp vụ/module đều có instrumentation đầy đủ. |

Spring Modulith cung cấp module-entry spans cho các lời gọi được instrument qua API module. Nó cũng tạo metric:

- `module.events.published`: counter chung cho domain event đã phát.
- `module.events.published.$moduleIdentifier.$simpleEventTypeName`: counter theo module và loại sự kiện.

Các module spans thường có thuộc tính `module.identifier`, `module.name`, `module.method` và `module.invocation-type`. **Không thấy những tín hiệu này** có thể là do chưa phát sự kiện, lời gọi không đi qua điểm được instrument, sai scope component hoặc thiếu runtime instrumentation; không mặc nhiên là lỗi mạng của exporter.

## 3. Quy trình khoanh vùng trong 10 phút đầu

Để tránh chẩn đoán theo cảm giác, ghi một phiếu sự cố nhỏ:

| Trường | Ví dụ cần ghi |
| --- | --- |
| Artifact đang chạy | SHA-256 của JAR/image digest, Git revision nếu có |
| Phiên bản | Spring Boot, Spring Modulith, Micrometer, OpenTelemetry SDK/Collector |
| Môi trường | Profile, pod/host/namespace, cổng quản trị, tên service |
| Signal mất | Traces, metrics hay cả hai; riêng module spans hay toàn bộ HTTP spans |
| Thời điểm phát hiện | Mốc thời gian tuyệt đối và múi giờ |
| Giao thức | OTLP HTTP 4318, gRPC 4317, Zipkin hoặc Prometheus scrape |
| Destination thực tế | DNS/host/port/path đã được giải quyết sau khi áp dụng override |
| Bằng chứng | Request ID kiểm thử, giá trị counter, exporter errors, receiver/collector counters |

Sau đó chạy theo cây quyết định:

~~~mermaid
flowchart TD
    A["Không thấy dữ liệu ở dashboard"] --> B{"App có tạo signal?"}
    B -->|"Không"| C["Kiểm tra event, instrumentation, sampling"]
    B -->|"Có"| D{"Có registry / tracer và exporter đúng?"}
    D -->|"Không"| E["Kiểm tra runtime dependencies, profile, properties"]
    D -->|"Có"| F{"App gửi đến receiver được?"}
    F -->|"Không"| G["DNS, port, protocol, TLS, auth, timeout"]
    F -->|"Có"| H{"Collector nhận được signal?"}
    H -->|"Không"| I["Receiver/pipeline/route/firewall"]
    H -->|"Có"| J{"Collector chuyển tiếp đến backend?"}
    J -->|"Không"| K["Processor/filter/queue/retry/exporter"]
    J -->|"Có"| L["Query theo service, timeframe, tenant, labels"]
~~~

**Gợi ý đọc nhanh:** nếu metric có trong `/actuator/metrics` nhưng không có trong OTLP receiver, hãy tập trung vào registry/exporter hoặc transport. Nếu Collector báo accepted mà backend không có dữ liệu, hãy chuyển sang pipeline Collector và backend. Nếu ngay `/actuator/metrics` đã không có metric cần tìm, tiếp tục kiểm tra cách sinh metric trước.

## 4. Kiểm tra dependency trong bản đóng gói

Spring Modulith **Insight starter** bao gồm hỗ trợ Actuator và module observability, nhưng cần dependency bổ sung để xuất telemetry tới hệ thống nhận như OTLP/Zipkin. Các module docs sinh graph cũng không tự cung cấp trace exporter.

Ví dụ Gradle Groovy DSL cho **Spring Boot 4.x tương thích với Spring Modulith 2.2.x**, giả sử ứng dụng đã có Spring Boot plugin và các starter nghiệp vụ:

~~~groovy
dependencies {
    implementation platform('org.springframework.modulith:spring-modulith-bom:2.2.0')
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Tracer/OTLP exporter: sử dụng BOM của Spring Boot.
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'

    // Chỉ cần nếu muốn push metrics qua OTLP.
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
~~~

Ví dụ cho **Spring Boot 3.5.x** với Spring Modulith ở nhánh hỗ trợ Boot 3.5 (chọn đúng BOM cho dự án):

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
~~~

**Điểm dễ nhầm:** Boot 3.5 dùng `management.otlp.tracing.*`; Boot 4.x sử dụng các thuộc tính exporter theo `management.opentelemetry.tracing.export.otlp.*`. Tài liệu Boot 4.x cũng có tùy chọn cấu hình OTLP chung cho nhiều signal. Trước khi sửa YAML, xác nhận phiên bản framework và tên property đã được binder nhận. Hai snippet trên là **lựa chọn theo phiên bản**, không được gộp thành một dependency set duy nhất.

Kiểm tra bản JAR đã phát hành:

~~~bash
# Chỉ áp dụng cho executable JAR kiểu Spring Boot.
jar tf shop.jar | grep 'BOOT-INF/lib/spring-modulith'
jar tf shop.jar | grep 'BOOT-INF/lib/micrometer'
jar tf shop.jar | grep 'BOOT-INF/lib/opentelemetry'
~~~

Trên PowerShell có thể dùng `jar tf shop.jar | Select-String 'BOOT-INF/lib'`. Nếu Gradle/Maven có dependency ở test classpath nhưng JAR thiếu runtime exporter, mọi phép thử trong IDE có thể thành công trong khi deployment im lặng. Khi đã có các dependency, vẫn cần xem **auto-configuration condition**: exporter hoặc registry có thể đã bị tắt bởi property, bean thay thế hoặc starter không phù hợp với nhánh Spring Boot.

**Kiểm chứng tốt hơn:** xuất dependency tree của chính build được dùng cho JAR, đối chiếu hash của artifact đang chạy và các profile/overrides; không dựa vào `build.gradle` ở một commit khác.

## 5. Kiểm tra nguồn dữ liệu ở trong ứng dụng

### 5.1. Bắt đầu từ signal cơ bản nhất

Khi Actuator metrics có sẵn và endpoint được expose trên cổng quản trị, thử:

~~~bash
curl -i http://localhost:19090/actuator/health
curl -sS http://localhost:19090/actuator/metrics
curl -sS http://localhost:19090/actuator/metrics/jvm.memory.used
curl -sS http://localhost:19090/actuator/metrics/module.events.published
~~~

Cổng `19090` chỉ là ví dụ. Nếu không có cổng quản trị riêng, đường dẫn mặc định thường là `/actuator` trên cổng ứng dụng. Nếu endpoint bị giới hạn quyền, phải sử dụng danh tính hợp lệ trong môi trường thử; không bỏ xác thực để “xác minh nhanh”.

Diễn giải kết quả:

- `/actuator/metrics` 404/403: trước tiên xác minh endpoint availability, `management.endpoints.web.exposure.include`, security và cổng đang gọi.
- `jvm.memory.used` có dữ liệu, `module.events.published` chưa có: MeterRegistry đang hoạt động; kiểm tra **có domain event thực sự được phát** và Modulith instrumentation.
- Cả các metric JVM không xuất hiện: kiểm tra Actuator, `MeterRegistry`, custom registry/filter và cơ chế expose.
- Đã có `module.events.published` nhưng dashboard trống: khoanh vùng ở bước **xuất metric hoặc backend** thay vì thay đổi logic phát event.

**Một metric có thể được đăng ký lười (lazy registration).** Hãy thực thi một nghiệp vụ thử nghiệm có phát event, lấy counter trước/sau và so sánh cùng bộ tag. Khi thử với nhiều replica, gửi request và đọc metrics trên **cùng một instance**, nếu không số đếm có thể khác do load balancing.

### 5.2. Phân biệt trace lỗi với context lỗi

Với module `orders` gọi `inventory`:

1. Có HTTP server span nhưng **không có module-entry span**: xem interceptor của Spring Modulith, bean thuộc API module, proxy invocation, version và component scanning.
2. Có module spans ở các trace khác nhau: xem `@Async`, task executor, Reactor, message broker và context propagation. Exporter vẫn có thể đang hoạt động.
3. Có spans trong process/log nhưng Collector chưa nhận: chuyển sang exporter, sampling và mạng.
4. Toàn bộ trace không tồn tại: kiểm tra tracer bridge, SDK/no-op, sampling và exporter, đồng thời bảo đảm đã thực thi một request được instrument.

Việc gọi method trong **cùng bean bằng `this.someMethod()`** có thể không đi qua Spring proxy, vì vậy không nên kỳ vọng mọi method nội bộ đều tạo module span. Khi gọi HTTP sang service khác bằng `RestClient`/`WebClient`, dùng builder đã được Spring Boot cấu hình để truyền tracing context; khi qua executor hoặc reactive pipeline cần cơ chế context propagation phù hợp.

### 5.3. Dùng một probe không phụ thuộc nghiệp vụ

Nếu ứng dụng chạy được nhưng chưa chắc có telemetry, trong môi trường thử có thể tạo một probe nhỏ có chủ ý. Ví dụ chỉ bật controller sau khi kích hoạt profile `telemetry-smoke`:

~~~java
package com.example.shop.diagnostics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("telemetry-smoke")
class TelemetryProbeController {

    private final MeterRegistry meters;
    private final ObservationRegistry observations;

    TelemetryProbeController(MeterRegistry meters,
                             ObservationRegistry observations) {
        this.meters = meters;
        this.observations = observations;
    }

    @PostMapping("/internal/telemetry-probe")
    String probe() {
        this.meters.counter("lesson.export.probe").increment();
        return Observation.createNotStarted("lesson.export.probe", observations)
                .observe(() -> "ok");
    }
}
~~~

Đây là **đoạn kiểm thử ứng dụng mẫu**, không yêu cầu thêm vào hệ thống production. Bảo vệ endpoint bằng network policy và authentication trong môi trường thử, gỡ profile/probe sau chẩn đoán. Metric `lesson.export.probe` giúp kiểm tra pipeline metric ngay cả khi nghiệp vụ chưa phát event; `Observation` giúp quan sát span khi tracing bridge đã được cấu hình. Nếu probe tới backend nhưng không thấy `module.events.published`, vấn đề nằm ở **nguồn dữ liệu hoặc instrumentation của Modulith**, không phải kênh OTLP chung.

## 6. Kiểm tra cấu hình exporter theo đúng phiên bản

### 6.1. Ví dụ Boot 4.x: đẩy traces và metrics qua OTLP/HTTP

Ví dụ môi trường staging, Collector nội bộ có receiver OTLP HTTP tại `otel-collector:4318`:

~~~yaml
spring:
  application:
    name: shop

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,modulith"
  tracing:
    sampling:
      probability: 1.0  # Chỉ dùng cho phép thử ngắn có kiểm soát.
  opentelemetry:
    tracing:
      export:
        otlp:
          transport: http
          endpoint: "http://otel-collector:4318/v1/traces"
  otlp:
    metrics:
      export:
        url: "http://otel-collector:4318/v1/metrics"
        step: 10s
~~~

Trên Boot 4, dependency `spring-boot-starter-opentelemetry` hỗ trợ đường tracing OpenTelemetry/OTLP. Metric push OTLP là đường riêng của `micrometer-registry-otlp`. Việc dùng chung Collector **không đồng nghĩa** chỉ cần một exporter hoặc một endpoint cho mọi loại dữ liệu.

### 6.2. Ví dụ Boot 3.5.x: cách đặt tên property tracing cũ

~~~yaml
spring:
  application:
    name: shop

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: "http://otel-collector:4318/v1/traces"
    metrics:
      export:
        url: "http://otel-collector:4318/v1/metrics"
        step: 10s
~~~

Mẫu Boot 3.5 cần `micrometer-tracing-bridge-otel` và `opentelemetry-exporter-otlp` cùng Actuator; xem `management.otlp.tracing.*` cho cấu hình tracing. **Dùng đúng Javadoc/configuration metadata của phiên bản đang triển khai**, vì nâng Boot 3 → 4 có thể khiến property cũ không còn tạo hiệu quả mong muốn.

Trong thực tế nên cấu hình URL/token bằng nguồn cấu hình ngoài hoặc secret manager. Không đưa bearer token trực tiếp vào tài liệu, mã nguồn, lệnh debug có thể bị ghi lịch sử shell hay dashboard.

### 6.3. OTLP/HTTP và OTLP/gRPC: đúng host chưa đủ

| Thành phần | OTLP qua HTTP/protobuf | OTLP qua gRPC |
| --- | --- | --- |
| Cổng quy ước thường gặp | `4318` | `4317` |
| Đường dẫn signal | `/v1/traces`, `/v1/metrics`, `/v1/logs` | Sử dụng gRPC service/method, không phải path HTTP tương ứng |
| Kiểu request | HTTP POST có payload Protobuf, content type thích hợp | HTTP/2 gRPC và Protobuf |
| Lỗi cấu hình điển hình | Trỏ vào root `/` hoặc sai `/v1/...`, proxy chặn POST. | Dùng HTTP client vào gRPC receiver, TLS/h2c không phù hợp. |

Giá trị cổng trên là **quy ước**, không bảo đảm Collector/ingress đang nghe ở đó. Môi trường có TLS, port mapping hoặc gateway riêng phải dùng giá trị triển khai thực tế.

**Không dùng `curl GET http://host:4318/v1/traces` để kết luận exporter hỏng.** Endpoint ingest OTLP chờ POST với payload hợp lệ; phản hồi 404/405/415 từ GET hoặc POST rỗng chỉ cho biết nhiều nhất rằng đã đi tới một HTTP handler nào đó, không xác minh có một lô span hợp lệ được nhận. Cách chắc chắn hơn là gửi signal thật từ ứng dụng và quan sát receiver counters hoặc debug exporter của Collector.

## 7. Kiểm tra effective configuration và trạng thái bật/tắt

Khi exporter im lặng, hãy kiểm tra **giá trị runtime đã bind**:

- Profile thực tế (`spring.profiles.active`), `application-{profile}.yaml` trong/ngoài JAR và `spring.config.import`.
- Biến môi trường, system properties, command-line arguments và cấu hình do nền tảng triển khai thêm.
- Cờ tắt exporter, registry hoặc SDK; dấu hiệu exporter auto-configuration không được tạo bean.
- URL signal-specific ghi đè URL chung, đặc biệt trong các nhánh Boot hỗ trợ `OTEL_EXPORTER_OTLP_ENDPOINT` và `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`.
- Mức sampling, các filter Observation/Meter, tên service, resource attributes, và tenant/namespace của backend.

Ở Boot 4.x, các property đáng kiểm tra gồm `management.tracing.sampling.probability`, `management.opentelemetry.tracing.export.otlp.endpoint`, `management.otlp.metrics.export.url` và cờ enable tương ứng. Với OpenTelemetry SDK, `OTEL_SDK_DISABLED=true` hoặc `management.opentelemetry.enabled=false` có thể làm SDK không hoạt động. Một registry metrics Micrometer vẫn có thể hoạt động độc lập, nên không thể suy trạng thái trace từ metrics.

Khi đã được phân quyền ở môi trường nội bộ, `/actuator/env` và `/actuator/configprops` có thể hỗ trợ xem nguồn cấu hình/binding; Spring Boot thường che các giá trị nhạy cảm. **Không mở `show-values=always` hoặc xuất toàn bộ `env` vào ticket**, vì endpoint có thể chứa secret. Nếu có thể, in bản “effective config fingerprint” đã loại token: Boot/Modulith version, active profile, exporter type, host/port/path, sampling và cờ enable.

### Lỗi do cấu hình giao thoa

Ví dụ ứng dụng chạy trong Kubernetes, `application-staging.yaml` đặt Collector là `otel-collector:4318`; một Helm value lại đặt `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` sang một service khác. Kết quả có thể là metric đến Collector A, trace gửi Collector B và dashboard chỉ truy vấn A.

Trên Boot 4.x, tham số **signal-specific** có thể ưu tiên hơn endpoint chung `management.opentelemetry.otlp.endpoint`. Khi dùng biến môi trường OTel, endpoint chung thường được bổ sung hậu tố `/v1/traces`, `/v1/metrics` nếu cần theo giao thức HTTP; endpoint signal-specific lại được hiểu đúng như giá trị cung cấp. Vì vậy cần xác nhận URL **sau khi bind**, không tự nối đường dẫn bằng cách đoán.

## 8. Kiểm tra mạng, TLS và mã lỗi xuất dữ liệu

Chỉ kiểm tra **từ nơi tiến trình ứng dụng thực sự chạy**. `localhost` trong container là chính container ứng dụng, không phải máy host hay Collector ở pod khác.

Các lệnh kiểm tra kết nối cơ bản:

~~~bash
# Thực thi trong pod/container app hoặc môi trường cùng network.
getent hosts otel-collector
nc -vz otel-collector 4318

# Kiểm tra đường HTTP/TLS được sử dụng (không gửi dữ liệu OTLP hợp lệ).
curl -v --connect-timeout 3 http://otel-collector:4318/
~~~

Trên PowerShell:

~~~powershell
Resolve-DnsName otel-collector
Test-NetConnection -ComputerName otel-collector -Port 4318
~~~

Các công cụ có thể không được cài sẵn trong container tối giản; thay bằng công cụ chẩn đoán nội bộ đã được phê duyệt. **DNS resolve và TCP connect thành công không chứng minh receiver chấp nhận OTLP**.

| Dấu hiệu | Nhóm lỗi có thể | Hướng khoanh vùng |
| --- | --- | --- |
| `UnknownHostException` / DNS thất bại | Tên service sai, DNS hoặc network namespace. | Kiểm tra service discovery từ pod/host ứng dụng. |
| `Connection refused` | Không có listener đúng cổng, service targetPort sai, Collector tắt. | Kiểm tra địa chỉ, receiver binding, container/service port. |
| Connect timeout | Firewall, NetworkPolicy, route, proxy hoặc đích không đáp ứng. | Kiểm tra traffic theo chiều app → collector, không chỉ chiều ngược lại. |
| `SSLHandshakeException` / certificate verify failed | CA/truststore, hostname/SNI, mTLS hoặc thời hạn chứng chỉ. | Kiểm tra chuỗi chứng chỉ và TLS config, không tắt xác minh TLS. |
| HTTP 401/403 | Thiếu/sai token, header auth, tenant hoặc quyền. | Kiểm tra secret injection, header và policy phía receiver/backend. |
| HTTP 404/405/415 | Sai path `/v1/traces`/`/v1/metrics`, sai phương thức/media type hoặc ingress route. | Xác định OTLP/HTTP receiver và cấu hình exporter; tránh kết luận từ GET thử nghiệm. |
| gRPC `UNIMPLEMENTED` hoặc HTTP/2 lỗi | Gửi sai giao thức/cổng, proxy không hỗ trợ gRPC, receiver thiếu service. | Đối chiếu OTLP/gRPC với OTLP/HTTP, TLS/h2c, ingress rules. |
| HTTP 429/503, `RESOURCE_EXHAUSTED`, timeout | Quá tải hoặc downstream backpressure. | So accepted/failed, queue, rate limits, tài nguyên Collector/backend. |
| HTTP 400 / `INVALID_ARGUMENT` | Payload không hợp lệ, attributes quá giới hạn, encoding/protocol sai. | Xem lỗi chi tiết và cấu hình processor/receiver; tránh retry vô hạn. |

**Quy tắc với lỗi xác thực:** kiểm tra token có được nạp và gửi đến đúng đích, nhưng chỉ ghi nhận sự hiện diện của header/token đã che, không log secret hoặc chạy `curl -v` chứa token thật vào kênh lưu trữ công khai.

## 9. Kiểm tra Collector theo từng chặng

OpenTelemetry Collector chỉ xử lý signal khi **receiver được cấu hình và được gắn vào pipeline của signal đó**. Định nghĩa `receivers.otlp` mà quên gắn `otlp` vào `service.pipelines.traces.receivers` sẽ khiến luồng traces không được xử lý như mong đợi.

Ví dụ cấu hình Collector phục vụ **chẩn đoán trong môi trường cô lập**, dùng debug exporter để nhìn thấy dữ liệu đã qua pipeline:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

Mẫu này giúp xác minh **app → collector**, không gửi tới backend production. Không thay cấu hình Collector đang phục vụ nhiều ứng dụng chỉ để bật debug; hãy chạy một Collector kiểm thử độc lập hoặc cấu hình route chẩn đoán riêng nếu môi trường cho phép. Debug exporter có thể in dữ liệu telemetry chứa thuộc tính nhạy cảm, nên giới hạn quyền và thời gian ghi log.

Các câu hỏi khi kiểm tra Collector:

1. Collector có lắng nghe `4318` và/hoặc `4317` trên interface đúng không, service/pod có map đúng cổng không?
2. `service.pipelines.traces` và `service.pipelines.metrics` có receiver OTLP, processor và exporter không?
3. Receiver counter có tăng sau probe? Các metric nội bộ thường có nhóm `otelcol_receiver_accepted_*` hoặc `otelcol_receiver_refused_*`.
4. Exporter counter và log downstream ra sao? Thường có `otelcol_exporter_sent_*` hoặc `otelcol_exporter_send_failed_*` (kiểm tra tên chính xác theo bản Collector).
5. Processor có drop/sửa tên resource hoặc route theo tenant khác không? Tail sampling có thể cố ý loại trace.
6. Queue/retry có backlog, dữ liệu bị bỏ do hết giới hạn đợi, đầy bộ nhớ hoặc restart không?

Nếu `receiver accepted > 0` nhưng `exporter sent = 0`, hãy tập trung vào **processor, routing, queue và exporter**. Nếu `exporter sent` tăng nhưng dashboard không thấy, hãy kiểm tra tenant, quyền, retention, ingestion delay và query filters tại backend. Các metric nội bộ chỉ là chỉ dẫn: tùy phiên bản và cấu hình có thể bị đổi tên hoặc không bật.

### Khi Collector quá tải hoặc không gửi được

Collector có thể xếp hàng, retry theo backoff và cuối cùng **drop data** nếu downstream ngắt lâu, queue đầy hoặc hết thời gian retry. Giảm sampling/lượng tag, kiểm tra CPU/memory, giới hạn queue/batch và khôi phục downstream trước khi tăng tài nguyên. Không tăng queue vô hạn vì có thể gây OOM. Khi yêu cầu chống mất dữ liệu qua restart, xem xét persistent queue/storage theo tài liệu Collector và hạ tầng của dự án; không giả định queue mặc định bảo đảm không mất dữ liệu.

## 10. Phân biệt sự cố của ba kiểu exporter phổ biến

| Kiểu cung cấp dữ liệu | Cách hoạt động | Điểm kiểm tra đầu tiên |
| --- | --- | --- |
| **OTLP traces** | Ứng dụng/SDK gửi span đã sample/batch tới receiver, sau đó Collector chuyển tiếp. | Tracer/bridge, sampling, endpoint `/v1/traces` hoặc gRPC, receiver accepted spans. |
| **OTLP metrics** | `OtlpMeterRegistry` đẩy theo chu kỳ `step` tới `/v1/metrics`. | Meter có trong app, registry OTLP, `management.otlp.metrics.export.url`, receiver accepted metric points. |
| **Prometheus scrape** | Prometheus gọi `/actuator/prometheus` theo scrape interval. | Registry Prometheus, endpoint exposure/access, target trạng thái `UP`, relabeling. |

Với **Prometheus**, ứng dụng không chủ động push metric qua OTLP. Chẩn đoán bằng `curl` từ **Prometheus target network**, HTTP status của `/actuator/prometheus`, cấu hình `scrape_configs`, `metrics_path`, `scheme`, TLS, auth và target labels. Nếu `/actuator/metrics` có meter nhưng `/actuator/prometheus` không có, xem việc đăng ký registry, lọc meter, thời điểm scrape và cách tên metric được chuyển sang định dạng Prometheus. Tên `module.events.published` trên Micrometer không nhất thiết giống tên hiển thị trong Prometheus.

Với **OTLP metrics**, thường có độ trễ bằng ít nhất một chu kỳ `step` cộng thời gian vận chuyển/ingest. Chờ qua vài chu kỳ khi đánh giá và kiểm tra timestamp. Với traces, sampling và batch processing là hai bước riêng: sampling có thể ngăn span được export; batching có thể khiến export diễn ra sau khi request đã trả về.

## 11. Trường hợp dữ liệu đã tới backend nhưng không nhìn thấy

Một số sự cố được báo là “exporter không gửi” dù exporter hoạt động bình thường:

- Dashboard đang lọc sai `service.name`, `deployment.environment`, tenant, namespace hoặc application/module tag.
- Time range/timezone không bao gồm thời điểm gửi hoặc có độ lệch đồng hồ giữa ứng dụng và backend.
- Trace được sample nhưng query đang tìm theo một span name khác; các module spans không phải mọi method call.
- Metric được đổi tên theo convention của backend, gộp nhãn, lọc tag hoặc bị giới hạn cardinality.
- Collector exporter trả accepted nhưng backend ingestion pipeline còn chờ xử lý, retention đã hết hoặc người dùng không có quyền xem.
- Backend chỉ hiển thị một loại signal (traces hoặc metrics), trong khi ứng dụng đã gửi signal còn lại.

Kiểm chứng bằng dữ liệu dễ tìm: một request thử với thời gian chính xác, `service.name` cố định, một counter probe tăng có kiểm soát, và trace ID từ log (không dùng ID chứa bí mật). Nếu dùng trace ID để tìm trực tiếp, xác nhận nó đã được sample; log có trace ID nhưng trace không được sample vẫn là tình huống hợp lệ.

### Context propagation không phải lỗi exporter

Nếu `orders` phát event và listener `inventory` chạy `@Async`, có thể xuất hiện **hai trace rời nhau**. Kiểm tra executor, `ContextPropagatingTaskDecorator`/Micrometer Context Propagation, Reactor context và propagation qua message broker tùy công nghệ. Sau khi khôi phục context, xác minh span linkage; **đừng chỉ nhìn số lượng span** rồi kết luận exporter đã sửa được. Nội dung trace và parent/child/span links phụ thuộc cơ chế truyền context thực tế.

## 12. Checklist khắc phục và tiêu chí xác nhận

Nên tiến hành theo thứ tự, lưu bằng chứng ở mỗi bước:

| Cổng kiểm tra | Hành động | Điều kiện đạt |
| --- | --- | --- |
| **A. Artifact** | Kiểm tra JAR/image, dependency và phiên bản thực. | Modulith Insight/observability và tracer/exporter/registry phù hợp có trong runtime. |
| **B. Generation** | Gửi HTTP request và event nghiệp vụ kiểm thử; truy vấn Actuator metrics. | Thấy meter và ít nhất một observation/span của luồng được instrument. |
| **C. Configuration** | So active profiles, effective endpoint, cờ enable, sampling, exporter type. | Runtime dùng đúng URL, path, protocol và registry/tracer mong muốn. |
| **D. Transport** | Kiểm tra DNS/TCP/TLS/auth từ chính process namespace. | Không còn lỗi kết nối, chứng chỉ hoặc quyền. |
| **E. Collector ingest** | Đọc receiver metrics/log hoặc debug exporter cô lập. | Collector nhận signal mới sau probe. |
| **F. Collector egress** | Kiểm tra processors, filters, queue, retry, backend exporter. | Dữ liệu tương ứng được chuyển tới backend; không có drop bất thường. |
| **G. Query** | Tìm theo time range, tenant, service và trace ID. | Signal xuất hiện với đúng service/module tags. |
| **H. Regression** | Chạy nghiệp vụ domain event, cross-module API và async listener. | Event metric tăng, module spans phù hợp, context được truyền theo thiết kế. |

### Tình huống thực hành: trace không có, metric cũng không có

**Dữ kiện:** `/actuator/modulith` trả JSON đúng, `/actuator/health` thành công. `/actuator/metrics/module.events.published` có số đếm, nhưng Collector không ghi nhận metric points. Không có trace ở dashboard.

**Cách điều tra hợp lý:**

1. Khẳng định runtime có `OtlpMeterRegistry`, tracing bridge/exporter và đúng dependency theo Boot 3.x/4.x. Nếu thiếu registry OTLP, Actuator metrics vẫn có thể hiển thị từ một registry khác, nên “có local metrics” chưa chứng minh đã bật push.
2. Kiểm tra `management.otlp.metrics.export.url` và tracing endpoint theo đúng phiên bản. Nếu cả hai đều chỉ về `localhost:4318` trong pod ứng dụng nhưng Collector nằm ở pod khác, xác định đây là sai destination.
3. Chỉnh destination bằng cấu hình môi trường, khởi động lại với artifact như cũ và gửi probe. Dùng receiver metrics để xem accepted của traces/metrics.
4. Nếu metric tới Collector nhưng trace không có, kiểm tra tracer bridge, exporter và sampling; với `management.tracing.sampling.probability=1.0` chỉ trên staging, gửi request mới rồi đợi qua chu kỳ xuất.
5. Nếu Collector accepted nhưng backend query trống, kiểm tra pipeline exporter và tenant/time filter. Xác nhận đúng dịch vụ bằng `service.name`.
6. Kết thúc khi probe metric và trace xuất hiện, `module.events.published` tăng sau event thật, module-entry spans được ghi nhận cho đường gọi được instrument và không có lỗi exporter lặp lại.

**Không đạt** nếu chỉ đổi một property mà chưa có bằng chứng dữ liệu xuất hiện ở Collector/backend. **Đạt** khi chỉ ra được chặng lỗi, sửa đúng chặng, có phép thử lặp lại và xác nhận không làm hỏng tracing/metrics ở luồng nghiệp vụ khác.

## 13. Các thực hành vận hành nên giữ

1. **Không xuất bí mật:** tránh đưa token, cookie, chứng chỉ riêng, payload nhạy cảm hay dữ liệu khách hàng vào span attributes, event tags và log debug.
2. **Giới hạn sampling khi thử:** `1.0` hữu ích cho chẩn đoán ngắn, nhưng có thể gây quá tải trong production. Sau kiểm chứng phải trả về chính sách sampling phù hợp.
3. **Báo động theo nhiều chặng:** ứng dụng còn xử lý event, Collector receiver accepted, exporter failed/dropped và backend ingest/query cần được theo dõi độc lập.
4. **Ghi nhận phiên bản/config fingerprint:** đặc biệt khi nâng Spring Boot/Modulith, thay collector image hoặc đổi giao thức OTLP.
5. **Bảo vệ Actuator:** `/actuator/env`, `/actuator/configprops`, `/actuator/modulith` và `/actuator/prometheus` nên được giới hạn mạng và quyền theo nhu cầu vận hành.
6. **Không dùng test slice làm bằng chứng exporter thực:** Spring Boot có thể không auto-configure exporter trong `@SpringBootTest`; phép thử tích hợp phải chạy cấu hình phù hợp hoặc artifact triển khai thực.

## 14. Ghi nhớ và tài liệu tham khảo

**Cách xác định nguyên nhân gốc:** luôn đi từ **signal được tạo → registry/tracer → exporter → receiver → collector pipeline → backend → dashboard**. Mỗi bước phải có bằng chứng riêng. Spring Modulith cho biết hoạt động ở ranh giới module; Micrometer và Spring Boot chịu trách nhiệm bridge/registry/exporter; Collector và backend quyết định chặng nhận, xử lý và truy vấn.

Tài liệu gốc (chọn đúng nhánh đang chạy):

1. [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module-entry spans, event metrics, Insight starter và Actuator.
2. [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): bridge/exporter và `management.otlp.tracing.*`.
3. [Spring Boot 4.0 — Tracing](https://docs.spring.io/spring-boot/4.0/reference/actuator/tracing.html): OpenTelemetry starter và `management.opentelemetry.tracing.export.otlp.*`.
4. [Spring Boot 4.0 — Observability](https://docs.spring.io/spring-boot/4.0/reference/actuator/observability.html): exporter OTLP, environment variables, disabled SDK và context.
5. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): registry, OTLP metrics, Prometheus và endpoint metrics.
6. [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure và bảo vệ endpoint.
7. [OpenTelemetry Collector — Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): lỗi receiver/pipeline/exporter và dấu hiệu cần quan sát.
8. [OpenTelemetry Collector — Resiliency](https://opentelemetry.io/docs/collector/resiliency/): retry, sending queue và những điều kiện có thể mất dữ liệu.

**Lưu ý phiên bản:** Spring Boot 3.5 và 4.x có những tên dependency/config property khác nhau. Trong mọi tình huống, đối chiếu documentation/configuration metadata của **đúng phiên bản đã khóa trong build** trước khi sửa cấu hình hoặc viết script triển khai.
