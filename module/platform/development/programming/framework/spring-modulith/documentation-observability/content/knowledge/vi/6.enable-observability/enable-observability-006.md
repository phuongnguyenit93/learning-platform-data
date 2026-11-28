# Phân biệt bật metrics với bật tracing

Trong một ứng dụng Spring Boot tổ chức bằng **Spring Modulith**, câu “đã bật observability” thường chưa đủ chính xác. Người vận hành có thể cần biết **bao nhiêu sự kiện được phát trong một khoảng thời gian**, trong khi người điều tra lỗi lại cần biết **một yêu cầu cụ thể đi qua những application module nào và chậm ở đâu**. Trường hợp đầu dùng **metrics**; trường hợp sau dùng **tracing**. Chúng có thể cùng xuất phát từ Micrometer Observation nhưng có **đường thu thập, cấu hình xuất dữ liệu và cách sử dụng khác nhau**.

Bài thuộc chương **Bật quan sát**, trong phạm vi **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**: dùng Spring Modulith để sinh tài liệu về ranh giới application module, đọc module graph/Actuator và quan sát tương tác module thông qua event metrics, tracing và context propagation. Chủ đề trực tiếp ở đây là **phân biệt bật metrics với bật tracing**, tự cấu hình từng loại và kiểm tra chúng độc lập.

> Ví dụ dependency và thuộc tính cấu hình trong bài dùng **Spring Boot 4.2 + Spring Modulith 2.2**. Với Spring Boot 3.x hoặc các nhánh Spring Modulith 1.x/2.0, một số tên artifact, starter và thuộc tính exporter có thể khác. Luôn đối chiếu tài liệu của đúng cặp phiên bản đang dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt câu hỏi mà metrics và tracing giải đáp, đơn vị dữ liệu và cách lưu trữ của chúng.
2. Giải thích quan hệ giữa **Micrometer Observation**, **MeterRegistry**, **Micrometer Tracing**, tracer/bridge và exporter.
3. Mô tả hai nhóm tín hiệu Spring Modulith công bố: metric **domain event publication** và **module entry spans**.
4. Bật metrics và kiểm tra `/actuator/metrics` hoặc `/actuator/prometheus` mà chưa cần tracing backend.
5. Bật tracing qua OpenTelemetry/OTLP và xem các span trên backend, không nhầm với thao tác expose Actuator.
6. Giải thích tại sao **sampling** và **context propagation** chủ yếu ảnh hưởng đến trace, trong khi event counter có hành vi khác.
7. Chẩn đoán khi một tín hiệu có dữ liệu nhưng tín hiệu còn lại chưa xuất hiện.

## 2. Metrics và tracing trả lời hai nhóm câu hỏi khác nhau

| Tiêu chí | **Metrics** | **Tracing** |
| --- | --- | --- |
| Đơn vị | Meter: counter, gauge, timer, histogram... | Trace gồm các span biểu diễn các công việc đã được quan sát |
| Cách quan sát | **Tổng hợp** số liệu theo tên và bộ nhãn | **Theo từng lần thực thi** khi có span được ghi lại |
| Câu hỏi tốt nhất | “Mỗi phút công bố bao nhiêu `OrderPlaced`?”, “Tỷ lệ lỗi đang tăng không?” | “Đơn này qua module nào?”, “Bước nào chậm?”, “Span nào là cha/con?” |
| Định danh | Metric name + tag có số lượng giá trị hữu hạn (low cardinality) | Trace ID, span ID, parent, start/end time, attributes |
| Nguồn dữ liệu | Micrometer `MeterRegistry` và registry/exporter phù hợp | Micrometer Tracing, tracer/bridge, trace exporter và backend |
| Ví dụ công cụ | Spring Boot `/actuator/metrics`, Prometheus, Grafana dashboard | Jaeger, Zipkin, Grafana Tempo/trace UI |
| Lấy mẫu | Counter thường cập nhật mỗi lần sự kiện được ghi nhận; hệ thống thu thập có thể scrape/aggregate theo chu kỳ | Sampler quyết định trace/span nào được ghi và xuất |
| Hạn chế | Không chứng minh một request cụ thể đã đi qua những bước nào | Không phải bộ đếm đầy đủ nếu sampling bỏ bớt trace |

Ví dụ:

- Metrics có thể cho biết số lần ứng dụng công bố `OrderPlaced` tăng từ 20 lên 200 mỗi phút. Từ đó, bạn biết tải đã tăng nhưng **không xác định được yêu cầu cụ thể nào chậm** chỉ từ counter.
- Tracing có thể cho biết trace của một request `POST /orders` đi qua module `orders` rồi `payments`, bước thanh toán mất phần lớn thời gian. Nó **không đại diện đầy đủ cho mọi request** nếu chỉ lấy mẫu một phần.

Không thể kết luận “bật metrics = bật tracing” hay “bật tracing = đã có metrics của domain event”. Mỗi đường phải có **instrumentation** và **nơi nhận dữ liệu** tương ứng.

## 3. Những thành phần tham gia khi “bật”

Một luồng khái niệm:

~~~mermaid
flowchart TB
    A["Nghiệp vụ Spring Boot<br/>orders / payments / inventory"]
    B["Spring Modulith observability<br/>event publication + module entry"]
    O["Micrometer Observation<br/>ObservationRegistry"]
    M["Micrometer Metrics<br/>MeterRegistry"]
    T["Micrometer Tracing<br/>Tracer / OpenTelemetry"]
    R["Prometheus registry<br/>/actuator/prometheus"]
    E["OTLP trace exporter"]
    P["Prometheus / Grafana<br/>metric dashboard"]
    J["Collector / Tempo / Jaeger<br/>trace search"]
    A --> B
    B --> O
    B -->|"domain event counters"| M
    O -->|"metrics observation handler (nếu có)"| M
    O -->|"tracing observation handler (nếu có)"| T
    M --> R
    R --> P
    T --> E
    E --> J
~~~

Sơ đồ thể hiện **các đường dữ liệu có thể kích hoạt**, không có nghĩa mỗi observation đều phải tạo đồng thời cả counter và span. Đặc biệt, Spring Modulith công bố **event-publication metrics** của riêng nó; việc một method trong module sinh ra module entry span không mặc nhiên tạo ra một metric tên `module.events.published`.

### 3.1. Các lớp cần phân biệt

- **Instrumentation**: code/framework đánh dấu một sự kiện hay đoạn công việc cần quan sát; Spring Modulith instrument các điểm vào module và việc công bố domain event.
- **ObservationRegistry**: đầu mối của Micrometer Observation; handler thích hợp có thể biến observation thành dữ liệu metrics/tracing.
- **MeterRegistry**: lưu và xuất metric qua Simple, Prometheus, OTLP, Datadog... Khi dùng Prometheus, HTTP endpoint là nơi để server ngoài đến scrape.
- **Tracer/bridge**: tạo span/trace context và chuyển sang OpenTelemetry hoặc Brave.
- **Exporter/backend**: chuyển/lưu dữ liệu để truy vấn và hiển thị. Một OTLP collector có thể nhận cả metrics và traces nhưng là **hai signal**, với các endpoint/luồng và cấu hình có thể riêng.

Bởi vậy, một ứng dụng có thể có `MeterRegistry` và truy vấn được metric nhưng **chưa có tracer/exporter**, hoặc có tracer nhưng **chưa cấu hình Prometheus scrape**.

## 4. Spring Modulith tự cung cấp những tín hiệu nào?

Khi bật hỗ trợ observability của Spring Modulith, có hai nhóm được tài liệu chính thức mô tả.

### 4.1. Event publication metrics

Spring Modulith công bố các counter cho domain event được phát trong ứng dụng:

| Meter name trong Micrometer | Ý nghĩa |
| --- | --- |
| `module.events.published` | Counter tổng hợp số lần **công bố domain event** được ghi nhận |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter cho một loại event cụ thể thuộc module được nhận diện |

Các **low-cardinality tags** của counter tổng hợp theo tài liệu gồm:

- `module.event.type`: loại domain event được phát.
- `module.identifier`: technical ID của application module liên quan.
- `module.name`: tên module dễ đọc.

Metric cho event cụ thể có các tag như `module.identifier` và `module.name`, và có thể được tùy chỉnh nếu triển khai `ModulithEventMetricsCustomizer`.

Ví dụ `module.events.published` tăng thêm một khi có một `OrderPlaced` được công bố và instrumentation ghi nhận publication. **Nó đo publication**, không trực tiếp đo listener đã xử lý thành công, số lần retry, tốc độ xử lý hay trạng thái giao dịch cuối cùng.

Cũng cần phân biệt **tên trong Micrometer** với **tên khi export**: ở Prometheus, dấu chấm có thể đổi thành gạch dưới và counter có thể thêm hậu tố như `_total`. Vì thế, khi thao tác, hãy tìm theo **tiền tố metric được chuẩn hóa**, không dùng một tên Prometheus suy đoán làm tiêu chí kiểm thử duy nhất.

### 4.2. Module entry spans

Spring Modulith có thể instrument các Spring component nằm ở **entry point/API của application module** để tạo observation/span khi có lời gọi qua ranh giới module. Module entry span được tài liệu mô tả bằng các thuộc tính:

| Span attribute | Ý nghĩa |
| --- | --- |
| `module.identifier` | Định danh kỹ thuật của module được đi vào |
| `module.name` | Tên module |
| `module.invocation-type` | Hình thức đi vào, ví dụ `bean` hoặc `event listener` |
| `module.method` | Phương thức tại điểm truy cập module |

Một trace có thể chứa HTTP server span và các module entry span lồng nhau:

~~~text
Trace ID: <giá trị minh họa>
HTTP POST /orders                     (server span)
└── orders.placeOrder                 (module entry span)
    └── payments.charge               (module entry span)
~~~

Tên span chỉ là ví dụ trình bày. Khi truy vấn trên backend, nên dựa thêm vào thuộc tính `module.*` thực tế và trace/span ID.

**Điều quan trọng:** module entry span chỉ thể hiện **lần vào module được instrument và được lấy mẫu/xuất thành công**; không phải mọi method nội bộ đều sinh ra một entry span. Nó cũng không nhất thiết là root span của toàn trace.

## 5. Bật metrics: điều kiện và cấu hình mẫu

Để có **metrics xuất sang Prometheus**, tối thiểu cần:

1. Instrumentation tạo metric cần quan sát; trong bài là Spring Modulith observability.
2. Micrometer `MeterRegistry`/Prometheus registry được Spring Boot cấu hình.
3. Actuator cho phép expose `prometheus` nếu chọn giao thức scrape.
4. Một Prometheus server có thể truy cập và scrape endpoint nếu muốn lưu lịch sử/dashboard.

Ví dụ **Gradle** trong ứng dụng đã quản lý phiên bản Spring Boot 4.2 / Spring Modulith 2.2 (qua BOM/dependency management phù hợp):

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Đã bao gồm Modulith Actuator và Modulith observability.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Cần registry này nếu muốn Prometheus scrape metrics.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Nếu dự án chỉ cần instrumentation metrics/module, có thể thay `spring-modulith-starter-insight` bằng `spring-modulith-observability-core` và thêm Spring Boot Actuator starter phù hợp để có HTTP endpoints. Cần kiểm tra phiên bản thư viện của dự án trước khi đổi dependency.

`application.yml` tối thiểu cho lab metrics:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Sau khi khởi động ứng dụng và thực sự phát domain event, kiểm tra:

~~~bash
# Liệt kê metric names đang được Micrometer ghi nhận.
curl -fsS http://localhost:8080/actuator/metrics

# Xem counter tổng hợp domain event (nếu đã được instrument và có dữ liệu).
curl -fsS http://localhost:8080/actuator/metrics/module.events.published

# Tìm các metric Spring Modulith trong Prometheus scrape output.
curl -fsS http://localhost:8080/actuator/prometheus | grep 'module_events_published'
~~~

`/actuator/metrics` trả JSON cho mục đích chẩn đoán và khám phá meter. `/actuator/prometheus` trả định dạng scrape do Prometheus hiểu; đây **không phải endpoint để tìm một trace**.

Lưu ý:

- Tên metric có thể chưa có trong `/actuator/metrics` trước khi code có sự kiện tương ứng và meter được đăng ký.
- Nếu thiếu Prometheus registry hoặc endpoint chưa được expose, `/actuator/prometheus` có thể trả 404/không khả dụng dù `/actuator/metrics` vẫn hoạt động.
- Chỉ thấy một counter tăng cho biết publication được ghi nhận; nếu cần biết listener hoàn tất, phải kiểm tra sự kiện, publication registry/logs hoặc metric trạng thái xử lý riêng.

### 5.1. Có thể bật metrics mà chưa bật tracing không?

**Có.** `MeterRegistry` và Prometheus registry có thể hoạt động khi ứng dụng không khai báo tracer/exporter. Khi đó bạn vẫn có event counters và các metric khác từ Spring Boot/Micrometer, nhưng không có bảo đảm xuất hiện **module entry traces** trong một tracing backend.

Trong trường hợp dùng **Simple in-memory registry** của Micrometer, có thể đọc `/actuator/metrics` ngay cả khi chưa cài Prometheus; nhưng Simple registry phù hợp để kiểm tra cục bộ, không thay thế hệ thống lưu lịch sử và cảnh báo.

### 5.2. Nếu muốn export metrics bằng OTLP

Prometheus pull/scrape chỉ là một lựa chọn. Có thể dùng `io.micrometer:micrometer-registry-otlp` và cấu hình:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
~~~

Khi đó metric được **đẩy (push)** tới OTLP collector/backend theo lịch của registry, không thông qua `/actuator/prometheus`. URL trên giả định collector chấp nhận OTLP/HTTP tại cổng 4318; cần có collector thật mới quan sát được dữ liệu.

## 6. Bật tracing: điều kiện và cấu hình mẫu

Để có **module entry spans trong trace backend**, cần:

1. Instrumentation của Spring Modulith để tạo observation ở điểm vào module.
2. Micrometer Tracing và tracer implementation phù hợp.
3. Exporter được bật và cấu hình tới trace collector/backend.
4. Một lần thực thi đi qua entry point được instrument và **được sampling**.
5. Trace context được truyền đúng nếu muốn nối các span qua thread, HTTP/messaging hoặc listener bất đồng bộ.

Ví dụ **Gradle** cho OpenTelemetry + OTLP:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Spring Modulith instrument các điểm vào module.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Spring Boot 4: tracer + OpenTelemetry SDK và OTLP export.
    runtimeOnly 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Ví dụ `application.yml` để thực hành:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces

  # Dùng cấu hình này nếu lab muốn chỉ export traces, không export
  # thêm metrics qua OTLP do starter OpenTelemetry kéo vào.
  otlp:
    metrics:
      export:
        enabled: false
~~~

**Giải thích từng phần:**

- `spring-boot-starter-opentelemetry` cung cấp đường đi tracing + OTLP theo Spring Boot 4.2. Đây là lựa chọn cho ví dụ, không phải lựa chọn duy nhất: Spring Boot cũng hỗ trợ Brave/Zipkin qua `spring-boot-starter-zipkin`.
- `management.tracing.sampling.probability: 1.0` yêu cầu lấy mẫu 100% trong lab để dễ kiểm chứng. Theo tài liệu Spring Boot 4.2, mặc định xác suất chỉ khoảng **0.1**; trong production cần điều chỉnh theo lưu lượng/chi phí.
- `management.opentelemetry.tracing.export.otlp.endpoint` chỉ **đích nhận traces**. Với OTLP/HTTP, collector phải mở `/v1/traces`.
- Trong Spring Boot 4, starter OpenTelemetry còn có thể kéo theo registry xuất **OTLP metrics**; `management.otlp.metrics.export.enabled: false` tránh việc lab tracing-only gửi thêm metrics qua OTLP. Thuộc tính này **không có nghĩa tắt toàn bộ metric instrumentation nội bộ của Spring Boot**.
- Dù có `spring-modulith-starter-insight`, thiếu backend/collector hoặc exporter bị cấu hình sai thì **không tìm thấy traces trên UI**.

### 6.1. Tracing có cần expose HTTP endpoint `/actuator/tracing` không?

**Không có endpoint HTTP chuẩn `/actuator/tracing` để đọc toàn bộ traces theo cách `/actuator/metrics` trả metrics.** Traces thường được gửi từ exporter đến Zipkin, Tempo, Jaeger hoặc OpenTelemetry Collector rồi truy vấn bằng công cụ tracing tương ứng.

`/actuator/modulith` xuất **module architecture JSON**, cũng không phải lịch sử module entry spans. Mở `/actuator/modulith` được chỉ xác nhận khả năng đọc mô hình module, không xác nhận exporter tracing đã hoạt động.

### 6.2. Khi nào span xuất hiện?

Giả sử ứng dụng có các module `orders` và `payments`; một bean API trong `orders` gọi bean API `payments`. Nếu instrumentation bao phủ các điểm truy cập, sampling giữ trace và collector hoạt động, backend có thể ghi nhận:

~~~text
traceId=abc...             (minh họa)
└── HTTP POST /orders
    └── module.identifier=orders
        └── module.identifier=payments
~~~

Nên kiểm tra các tag `module.identifier`, `module.invocation-type` và `module.method` thay vì chỉ tìm tên span cố định. Tên span thực tế phụ thuộc conventions và phiên bản.

Trường hợp chỉ có traces HTTP mà không thấy module entry spans, hãy kiểm tra dependency Modulith observability, điểm vào bean có được instrument không, cách code gọi bean, sampler và exporter; không vội kết luận hệ thống không đi qua module khác.

## 7. Ba chế độ cấu hình đặt cạnh nhau

| Chế độ | Dependency/đường dữ liệu | Cách kiểm tra | Điều không nên kỳ vọng |
| --- | --- | --- | --- |
| **Chỉ metrics** | Modulith instrumentation + Micrometer MeterRegistry + registry phù hợp (Prometheus/OTLP) | `/actuator/metrics`, `/actuator/prometheus` hoặc metric backend | Không mặc nhiên có traces ở Jaeger/Tempo |
| **Chỉ tracing export** | Modulith instrumentation + tracer bridge + OTLP/Zipkin exporter; có thể tắt OTLP metrics export | Truy vấn trace ID/span/tag module trong tracing backend | Không mặc nhiên có Prometheus endpoint |
| **Metrics + tracing** | Cả hai đường dữ liệu được cấu hình; có thể chọn Prometheus cho metric và OTLP cho trace | Metric tăng khi event publish; trace hiện khi request được sampling | Event counter và số trace không nhất thiết khớp nhau |

**Ví dụ bật cả hai:** sử dụng Spring Modulith insight starter, Prometheus registry và Spring Boot OpenTelemetry starter.

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    runtimeOnly 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,modulith
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
  # Ví dụ này chỉ dùng Prometheus cho metrics, OTLP cho traces:
  otlp:
    metrics:
      export:
        enabled: false
~~~

**Điều cần nhớ:** `include: ...` điều khiển HTTP Actuator exposure. Nó **không bật tracer** và cũng **không thay thế dependency registry/exporter**. Khả năng truy cập các endpoint còn phụ thuộc cấu hình management access, Spring Security và network.

### 7.1. Ví dụ domain event phát sinh dữ liệu metrics

Một application module công bố domain event:

~~~java
// com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

~~~java
// com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void placeOrder(UUID orderId) {
        // Code nghiệp vụ lưu đơn hàng được lược bỏ cho ví dụ.
        events.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

Khi method được gọi qua API bean ở một luồng đã instrument, **hai kiểu dữ liệu có thể xuất hiện với ý nghĩa khác nhau**:

- **Metric:** publication của `OrderPlaced` làm thay đổi số liệu domain event được ghi nhận bởi `module.events.published`.
- **Trace:** lời gọi vào `orders` có thể tạo một module entry span để biết thời gian và vị trí trong trace, nếu tracer và sampling cho phép.

Không suy từ “metric tăng 1” thành “tracing có đúng 1 span”, bởi **một request có thể tạo nhiều span hoặc nhiều event** và trace có thể bị bỏ do sampling.

## 8. Sampling: khác biệt quan trọng

**Tracing sampling** kiểm soát lượng traces được giữ lại/xuất. Với Spring Boot 4.2:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Nghĩa là xác suất lấy mẫu mục tiêu khoảng 10% cho các root traces theo sampler mặc định và parent sampling policy. Con số là xác suất lấy mẫu, không đảm bảo cứ 10 request sẽ có chính xác 1 trace. Trường hợp đã nhận trace context từ upstream, parent-based sampler còn tôn trọng trạng thái sampling của parent.

**Event counters** là số liệu tổng hợp được ghi khi publication được instrument; chúng không bị chuyển thành “10% số lần publish” chỉ vì cấu hình `management.tracing.sampling.probability: 0.1`. Chu kỳ scrape, aggregation và cách export metric vẫn có thể làm độ phân giải trên dashboard khác với thao tác phát event tức thời.

Ví dụ định tính:

| Hiện tượng | Metrics | Tracing |
| --- | --- | --- |
| Có 1000 lần publish `OrderPlaced` trong khoảng thời gian đo | Counter ghi nhận số publication đã instrument (có thể quan sát mức tăng khoảng 1000 nếu không mất dữ liệu metric) | Không thể suy phải có 1000 traces/span liên quan |
| Giảm sampling từ 1.0 xuống 0.1 | Không tự làm domain event counter giảm xuống 10% | Ít traces được lưu hơn, khó bắt một request cụ thể |
| Backend trace tạm mất kết nối | Metric backend độc lập có thể vẫn hoạt động | Traces có thể không được export/hiển thị |
| Prometheus ngừng scrape | Số liệu trên Prometheus có thể gián đoạn dù code vẫn tăng meter trong ứng dụng | Trace exporter/backend có thể vẫn hoạt động |

**Không lấy số lượng trace từ UI để làm tổng số request chính xác khi sampling đang bật**. Muốn biết lưu lượng toàn hệ thống, sử dụng request counters/timers phù hợp.

## 9. Context propagation có liên quan thế nào?

Một trace có ý nghĩa khi các span liên quan được nối bằng **trace context**. Trong lời gọi đồng bộ trên cùng thread, context thường được tiếp tục. Khi xử lý `@Async`, application event listener bất đồng bộ, hàng đợi hoặc HTTP call sang service khác, cần bảo đảm context được truyền qua điểm chuyển giao.

Ví dụ với Spring Boot 4.2, nếu ứng dụng dùng `@Async` với `AsyncTaskExecutor` do framework tự cấu hình:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Nếu dùng custom executor, cần cấu hình `ContextPropagatingTaskDecorator` cho executor tương ứng theo tài liệu Spring Boot. Đối với HTTP, dùng `RestClient.Builder` hoặc `WebClient.Builder` được Spring Boot auto-configure để hỗ trợ propagation, thay vì tự tạo client bỏ qua cấu hình.

~~~mermaid
sequenceDiagram
    autonumber
    participant R as HTTP request
    participant O as Orders
    participant B as Async executor
    participant I as Inventory listener
    R->>O: placeOrder()
    Note over O: Trace context đang active
    O->>B: publish / schedule
    B-->>I: handle(OrderPlaced)
    Note over I: Quan hệ trace phụ thuộc<br/>context propagation thực tế
~~~

Nếu thiếu propagation, span listener **có thể nằm ở trace khác**, bị tách thành root mới hoặc không có context mong muốn. Điều này chủ yếu gây khó đọc **trace của một giao dịch**, trong khi **event publication counter** vẫn có thể tăng do event đã được publish.

Không nên khẳng định mọi listener bất đồng bộ sẽ tự động là span con của publisher chỉ vì bật property trên. Cần kiểm tra executor được dùng, cơ chế listener/transaction, thời điểm commit và instrumentation thực tế.

## 10. Quy trình kiểm chứng độc lập từng tín hiệu

### Bước A — Kiểm tra metrics trước

1. Xác nhận có Modulith observability dependency và `MeterRegistry`/Prometheus registry.
2. Khởi động ứng dụng và xác nhận Actuator có expose `metrics`/`prometheus`.
3. Kích hoạt một luồng nghiệp vụ **công bố domain event** (ví dụ tạo đơn hàng).
4. Truy vấn `GET /actuator/metrics/module.events.published` và so sánh counter trước/sau.
5. Nếu dùng Prometheus, xác nhận dữ liệu scrape và target `UP`, rồi đọc chart theo nhãn/tên meter được chuẩn hóa.

Nếu metrics có dữ liệu, điều đó **chưa kiểm chứng tracing**. Sang bước B độc lập.

### Bước B — Kiểm tra tracing

1. Xác nhận có Micrometer Tracing và tracer/exporter (ví dụ `spring-boot-starter-opentelemetry`).
2. Kiểm tra collector/backend đang chạy và địa chỉ exporter đúng.
3. Trong lab, đặt `management.tracing.sampling.probability: 1.0`.
4. Gọi luồng đi qua API của ít nhất một application module.
5. Tìm trace theo service name, thời gian và các thuộc tính `module.identifier` hoặc `module.method`.
6. Nếu chỉ thấy HTTP span, kiểm tra Modulith instrumentation, đường gọi qua Spring bean, sampling và phương thức được nhận diện.
7. Nếu listener async bị tách trace, kiểm tra context propagation.

Nếu trace hiển thị bình thường, điều đó **chưa chứng minh metric domain event cũng đang được export**. Chỉ đo được điều đã instrument và có đường thu thập phù hợp.

### Bước C — Đối chiếu với module graph và Actuator

Nếu có `GET /actuator/modulith`, endpoint này trả mô hình ứng dụng, ví dụ module names, base packages và dependencies. Dùng nó để biết **ràng buộc cấu trúc** và chọn luồng cần kiểm chứng. Đừng nhầm module graph với event counter hoặc lịch sử traces.

## 11. Những lỗi thường gặp khi “đã bật mà không thấy”

| Triệu chứng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Có `/actuator/metrics` nhưng không có `module.events.published` | Chưa có domain event được publish, instrumentation chưa hiện diện, metric chưa đăng ký | Gọi đúng nhánh publish event, kiểm tra Modulith observability |
| `/actuator/prometheus` trả 404 | Chưa thêm Prometheus registry hoặc endpoint chưa được expose/khả dụng | Kiểm tra dependency `micrometer-registry-prometheus` và `management.endpoints.web.exposure.include` |
| Prometheus thấy metric nhưng Jaeger/Tempo không có trace | Chưa có tracer/exporter, collector unreachable hoặc trace bị sampling | Kiểm tra tracing starter, OTLP endpoint, backend, sampling |
| Jaeger/Tempo thấy HTTP spans nhưng không có module entry spans | Thiếu Modulith instrumentation hoặc lời gọi không đi qua entry point được instrument | Kiểm tra `spring-modulith-observability-core` / `starter-insight` và luồng gọi Spring bean |
| Có trace nhưng thiếu event metrics | Chưa phát domain event, metrics registry/export pipeline chưa cấu hình, counter chưa xuất hiện | Kiểm tra event publish và meter/registry độc lập |
| Event counter tăng nhưng inventory chưa cập nhật | Metric chỉ đo publication, listener có thể lỗi/chưa chạy | Xem event publication registry, logs, listener tracing |
| Span của async listener không chung trace ID | Context không được truyền qua executor/transport | Kiểm tra `spring.task.execution.propagate-context`, decorator, client builder |
| Đặt sampling 1.0 nhưng vẫn không thấy trace | Sampling không giải quyết exporter sai hoặc điểm instrument không chạy | Kiểm tra network/backend/exporter và thời điểm thực thi |
| Bật starter OpenTelemetry nhưng thấy thêm OTLP metrics export ngoài ý muốn | Starter kéo theo registry metrics OTLP | Nếu không cần, cấu hình `management.otlp.metrics.export.enabled: false` |

### 11.1. Hai loại “bật” thường bị nhầm

**Bật instrumentation** có nghĩa ứng dụng có khả năng ghi nhận sự kiện/operation. **Bật export/exposure** có nghĩa dữ liệu được đưa tới nơi mà người dùng truy vấn được. Có thể thiếu một trong hai:

~~~text
Có instrumentation + thiếu exporter  -> Backend không nhận dữ liệu.
Có exporter + không có sự kiện phù hợp -> Không có metric/span mong đợi.
Có cả hai + sampling trace thấp      -> Metric có thể tăng nhưng trace khó tìm.
~~~

Điều này giải thích phần lớn trường hợp “đã thêm dependency mà dashboard vẫn trống”.

### 11.2. Lưu ý về tags và chi phí

Metrics nên dùng nhãn **low cardinality** như module ID, event type hoặc outcome; tránh gắn `orderId`, email, token, URL động hay giá trị người dùng không giới hạn vào metric tags. Mỗi tổ hợp nhãn mới có thể sinh thêm time series và tăng chi phí lưu trữ.

Trong tracing, attributes có thể mang thông tin chi tiết hơn để điều tra từng request, nhưng vẫn phải loại bỏ dữ liệu nhạy cảm, giới hạn kích thước và áp dụng sampling/retention hợp lý. Việc trace cho phép high-cardinality tags **không có nghĩa nên ghi PII hoặc secrets**.

### 11.3. Phân quyền endpoint

`/actuator/metrics`, `/actuator/prometheus` và `/actuator/modulith` có thể tiết lộ hoạt động hoặc cấu trúc nội bộ. Trên production, cần expose theo nhu cầu, giới hạn mạng và bảo vệ bằng Spring Security/quyền quản trị phù hợp. Với Prometheus, cấp quyền scrape cho hệ thống thu thập, không mở các actuator endpoints không cần thiết cho công chúng.

## 12. Bài thực hành có đáp án định hướng

### Bài 1 — Chọn tín hiệu đúng

Với các câu hỏi sau, hãy chọn **metrics** hay **tracing**:

1. “Trong 15 phút vừa qua, có bao nhiêu `OrderPlaced` được publish?”
2. “Tại sao riêng request mang trace ID X mất 2 giây?”
3. “Một loại event có được công bố thường xuyên hơn hôm qua không?”
4. “Một lần vào `payments` có quan hệ parent–child với `orders` không?”
5. “Lần publish event Y có chắc chắn khiến listener thành công không?”

**Gợi ý:** (1) metrics; (2) tracing; (3) metrics; (4) tracing; (5) không thể kết luận chỉ từ publication counter hoặc dependency graph, cần quan sát trạng thái listener/registry tương ứng.

### Bài 2 — Bật metrics nhưng không yêu cầu tracer

Từ skeleton Spring Boot + Spring Modulith, thêm Prometheus registry và Modulith instrumentation, expose `metrics,prometheus`, phát một domain event và tìm counter `module.events.published`. Ghi lại tên metric thực tế ở `/actuator/metrics` và tên đã chuẩn hóa ở Prometheus. Giải thích vì sao chưa thấy traces ở Zipkin/Tempo là điều có thể bình thường.

### Bài 3 — Bật tracing và so sánh sampling

Thêm OpenTelemetry starter và chạy OTLP collector/backend. Gọi cùng một nghiệp vụ với sampling `1.0` và `0.1` trong hai lượt thực hành đủ dài; tìm các module entry spans và ghi nhận sự khác biệt. **Không khẳng định sẽ có tỷ lệ đúng 1/10** vì sampling là xác suất và có thể chịu parent context.

Sau đó kiểm tra counter event publication. Giải thích vì sao giảm sampling không làm nó tự động giảm 90%.

### Bài 4 — Luồng bất đồng bộ

Tạo event listener chạy trên một executor riêng. So sánh trace ID/parent ID ở publisher và listener khi cấu hình truyền context phù hợp và khi thiếu cấu hình. Kết luận dựa trên **dữ liệu trace quan sát được**; đồng thời kiểm tra publication counter để nhận ra hai tín hiệu đang nói về hai chuyện khác nhau.

### Bài 5 — Chẩn đoán dashboard

Giả sử nhóm vận hành báo: “`/actuator/prometheus` có `module_events_published`, nhưng module `payments` không xuất hiện trong tracing UI”. Viết quy trình kiểm tra tối đa 6 bước: có tracer, exporter, backend, sampling, Modulith module entry instrumentation và lời gọi thực sự đến `payments` hay chưa.

## 13. Câu hỏi ôn tập

1. `MeterRegistry` và `Tracer` giải quyết hai loại dữ liệu khác nhau thế nào?
2. Metrics `module.events.published` đo **publication** hay **listener completion**?
3. `module.identifier` có thể xuất hiện cả ở metric tag và span attribute không? Khi đó mục đích của từng tín hiệu khác nhau thế nào?
4. Chỉ thêm `spring-modulith-starter-insight` đã đủ để có trace trong Tempo chưa?
5. Vì sao `management.endpoints.web.exposure.include=metrics,prometheus` không tự bật tracing?
6. Vì sao một metric có thể tăng mà trace liên quan không được tìm thấy?
7. Sampling `0.1` có ý nghĩa gì; có làm event counter giảm 90% không?
8. Nếu trace bị đứt ở `@Async`, loại cấu hình nào cần kiểm tra?
9. Vì sao cấu hình OTLP metrics khác cấu hình OTLP traces?
10. Có thể dùng `/actuator/modulith` để liệt kê lịch sử request không?

## 14. Ghi nhớ

**Metrics cho biết xu hướng/tổng hợp; tracing cho biết hành trình của một lần thực thi.** Trong Spring Modulith, event publication counters và module entry spans là hai dữ liệu bổ sung cho nhau: counters giúp phát hiện biến động về phát sự kiện, spans giúp phân tích các lần đi vào ranh giới module.

Để **bật metrics**, cần instrumentation, `MeterRegistry` và đường export/scrape của metric. Để **bật tracing**, cần instrumentation, tracer/bridge, sampling phù hợp, exporter/backend và context propagation khi vượt thread hoặc transport. **Actuator/module graph** bổ sung bức tranh cấu trúc, không thay thế hai loại dữ liệu vận hành này.

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features: Observing Application Modules, Module Entry Span, Observability Metrics](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Boot — Actuator Metrics: MeterRegistry, Prometheus và OTLP](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Spring Boot — Actuator Tracing: Micrometer Tracing, exporters, sampling](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot — Observability: ObservationRegistry và context propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Boot — Common Application Properties: OTLP tracing/metrics endpoints](https://docs.spring.io/spring-boot/appendix/application-properties/index.html).
