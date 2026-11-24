# OpenTelemetry với OTLP

Trong chương **Tracer implementation** của mô-đun **SPRING_BOOT_OBSERVABILITY**, **OpenTelemetry** là một lựa chọn triển khai distributed tracing cho Spring Boot, còn **OTLP (OpenTelemetry Protocol)** là giao thức đưa telemetry từ ứng dụng đến Collector hoặc hệ thống quan sát. Khi kết hợp **Micrometer Observation**, **Micrometer Tracing bridge cho OpenTelemetry** và **OTLP exporter**, ta có thể đi từ một request HTTP trong ứng dụng tới trace gồm nhiều span ở backend, rồi sử dụng thông tin đó để điều tra lỗi, độ trễ và quan hệ giữa các dịch vụ.

Điều quan trọng là không đánh đồng các thành phần: `ObservationRegistry` không phải Collector, OpenTelemetry không phải một backend lưu trữ, và cấu hình OTLP **tracing** không tự động xuất toàn bộ **metrics** hoặc **logs**. Bài này giải thích rõ các ranh giới, cách cấu hình, kiểm tra dữ liệu đầu cuối, sampling, context propagation, tags/cardinality và những lỗi thường gặp khi triển khai trên môi trường thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Micrometer Observation**, **Micrometer Tracing**, **OpenTelemetry**, **OTLP**, **Collector** và **trace backend**.
2. Cấu hình một ứng dụng Spring Boot 3.x xuất tracing spans bằng OTLP qua HTTP tới OpenTelemetry Collector.
3. Hiểu khác biệt giữa OTLP/HTTP cổng thường dùng **4318** và OTLP/gRPC cổng thường dùng **4317**.
4. Tạo custom observation, ghi lỗi và các thuộc tính trace phù hợp, kiểm tra quan hệ parent–child spans.
5. Giải thích vai trò của `traceparent`, `traceId`, `spanId`, propagation qua HTTP, thread và reactive pipelines.
6. Lựa chọn sampling ở ứng dụng và hiểu khi nào Collector có thể áp dụng chính sách xử lý khác.
7. Kiểm tra từng chặng: ứng dụng → exporter → Collector → backend, không suy đoán từ một cấu hình YAML.
8. Kiểm soát metadata, cardinality, dữ liệu nhạy cảm, TLS/xác thực và chi phí lưu trữ trace.
9. Kết hợp traces với metrics và logs để điều tra một request chậm hoặc lỗi.

## 2. Bản đồ các thành phần

Các tên gọi thường xuất hiện cạnh nhau nhưng giải quyết các bài toán khác nhau:

| Thành phần | Trách nhiệm | Không phải |
| --- | --- | --- |
| **Micrometer Observation** | Mô tả vòng đời một hoạt động; cung cấp tên, key-values, event, error, scope. | Một hệ thống lưu trace hoặc exporter. |
| **Micrometer Tracing** | Abstraction tạo span, truy cập tracer/context và liên kết instrumentation với tracing implementation. | Giao thức truyền telemetry trên mạng. |
| **OpenTelemetry** | Hệ sinh thái API, SDK và semantic conventions để tạo/xử lý telemetry. | Mặc định là nơi lưu trữ dữ liệu lâu dài. |
| **Micrometer Tracing OpenTelemetry bridge** | Kết nối abstraction của Micrometer Tracing với OpenTelemetry SDK/tracing implementation. | Tự động là một Collector. |
| **OTLP** | Giao thức truyền spans, metrics hoặc logs dưới dạng tín hiệu riêng tới receiver hỗ trợ. | Một database hoặc dashboard. |
| **OpenTelemetry Collector** | Nhận, xử lý, batch, định tuyến và xuất telemetry tới backend. | Bắt buộc phải có trong mọi topology OTLP. |
| **Trace backend** | Lưu và cho phép truy vấn trace, ví dụ Jaeger, Tempo hoặc hệ thống tương thích. | Chính thư viện Micrometer trong ứng dụng. |

Trong cách triển khai phổ biến của Spring Boot:

~~~mermaid
flowchart LR
    User["Client HTTP"]
    Svc["Spring Boot service"]
    Observation["Micrometer Observation"]
    Bridge["Micrometer Tracing OTel bridge"]
    SDK["OpenTelemetry SDK / Span exporter"]
    Collector["OTLP receiver của Collector"]
    Backend["Trace backend"]
    Logs["Logs có traceId/spanId"]
    Metrics["MeterRegistry / metrics backend"]

    User -->|"Request + traceparent nếu có"| Svc
    Svc --> Observation
    Observation --> Bridge --> SDK
    SDK -->|"OTLP/HTTP hoặc gRPC"| Collector --> Backend
    Svc --> Logs
    Observation -->|"Metrics handler nếu bật"| Metrics
~~~

Sơ đồ thể hiện các luồng **độc lập nhưng có thể liên kết**. Tracing span có thể được tạo từ observation; metrics handler có thể đo cùng hoạt động; logs có thể mang trace context qua MDC. Không phải mọi observation đều trở thành span được lưu: điều đó còn phụ thuộc **tracing bridge, sampler, exporter và backend**.

### Tracing là mô hình dữ liệu nào?

Một **trace** gồm các **span** có quan hệ. Mỗi span mô tả một công đoạn: server nhận HTTP request, gọi database, gửi HTTP client request hoặc xử lý một bước nghiệp vụ.

~~~text
Trace ID: 4f17c38a927d4b55a90714b02f8e6d19
└── SERVER GET /orders/{id}                780 ms
    ├── INTERNAL order.lookup                45 ms
    └── CLIENT POST inventory-service       690 ms
        └── SERVER POST /inventory/reserve   650 ms
~~~

Trong ví dụ giả định này, trace giúp định vị nhánh tốn thời gian. Tuy nhiên, các duration lồng nhau **không được cộng tùy ý**: một span cha bao hàm thời gian của các span con, và các nhánh có thể chạy đồng thời.

- **Trace ID** dùng để liên kết toàn bộ trace.
- **Span ID** định danh một span.
- **Parent span ID** cho biết quan hệ cha–con.
- **Attributes** mô tả thông tin như HTTP method, route, dependency hoặc outcome.
- **Status/events** có thể diễn giải lỗi hoặc những mốc đáng chú ý.
- **Resource attributes** mô tả tiến trình/dịch vụ, ví dụ `service.name`.

## 3. Chuẩn bị Spring Boot và dependency

Ví dụ ở bài này giả định **Spring Boot 3.x** với Java 17 trở lên, ứng dụng Spring MVC, dependency versions do **Spring Boot BOM** quản lý. Cấu hình chính xác có thể khác giữa các minor release, vì vậy cần đối chiếu behavior trong dự án đang chạy.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Chức năng từng dependency:

1. `spring-boot-starter-actuator` cung cấp hạ tầng Micrometer Observation và tích hợp quản trị/metrics thường dùng.
2. `micrometer-tracing-bridge-otel` là bridge giữa Micrometer Tracing và OpenTelemetry.
3. `opentelemetry-exporter-otlp` cung cấp khả năng gửi dữ liệu tới OTLP receiver phù hợp; khi auto-configuration của Spring Boot hoạt động, ứng dụng có thể xuất spans tới endpoint đã cấu hình.
4. `spring-boot-starter-web` chỉ cần cho ví dụ HTTP server trong bài; các ứng dụng WebFlux, messaging hoặc batch có integration tương ứng.

Không cần thêm đồng thời cả bridge OpenTelemetry và bridge Brave cho cùng pipeline chỉ vì muốn “nhiều tracing hơn”. Hãy chọn một tracing implementation, quản lý version đồng bộ và kiểm tra các bean thực tế. Việc tự cấu hình thêm một OpenTelemetry SDK độc lập cạnh SDK do Spring Boot auto-configure có thể tạo các pipelines trùng hoặc cạnh tranh.

### Cấu hình OTLP/HTTP cho môi trường thử nghiệm

~~~yaml
spring:
  application:
    name: order-api

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Ở đây:

- `spring.application.name` cung cấp tên ứng dụng; kiểm tra resource attribute `service.name` trong trace backend để xác nhận tên service thực tế.
- `management.tracing.sampling.probability: 1.0` được dùng cho **lab có tải thấp**, giúp giữ nhiều spans phục vụ kiểm tra. Không xem đây là cấu hình mặc định an toàn về chi phí cho production.
- `management.otlp.tracing.endpoint` trỏ tới một **OTLP/HTTP traces receiver**, thường dùng path `/v1/traces`.
- `localhost` nghĩa là **máy hoặc network namespace của ứng dụng**. Nếu Spring Boot chạy trong container còn Collector chạy trong container khác, `localhost:4318` thường trỏ nhầm chính container ứng dụng.

Ứng dụng phải được khởi động với cấu hình tương thích và Collector/backend phải đang chạy ở địa chỉ đó. Một file YAML hợp lệ **không đủ chứng minh** exporter đã gửi được dữ liệu.

## 4. OTLP là giao thức, không phải một URL bất kỳ

OTLP có những cách vận chuyển khác nhau. Phân biệt chúng trước khi cấu hình:

| Thuộc tính | OTLP/HTTP | OTLP/gRPC |
| --- | --- | --- |
| Transport | HTTP, thường là protobuf payload. | gRPC, thường dùng HTTP/2 và protobuf. |
| Cổng thường dùng | **4318** | **4317** |
| Địa chỉ ví dụ | `http://localhost:4318/v1/traces` | `http://localhost:4317` đối với cấu hình gRPC phù hợp. |
| Định tuyến tín hiệu | Thường dùng path `/v1/traces`, `/v1/metrics`, `/v1/logs`. | Dùng các RPC services/protocol của OTLP. |
| Kiểm tra | Theo response HTTP, receiver logs và công cụ hỗ trợ OTLP/HTTP. | Theo gRPC status, receiver logs và công cụ hỗ trợ OTLP/gRPC. |

**Cổng không phải định nghĩa tuyệt đối của giao thức.** Collector có thể được cấu hình lắng nghe ở cổng khác. Tuy nhiên, phải bảo đảm exporter và receiver **dùng cùng transport**. Không chỉ đổi `4318` thành `4317` trong một URL HTTP và kỳ vọng gRPC hoạt động.

Thường gặp ba lỗi cấu hình:

1. **Sai cổng/transport:** exporter dùng HTTP nhưng receiver chỉ bật gRPC.
2. **Sai path:** cấu hình HTTP traces endpoint ở root `/` thay vì `/v1/traces`, tùy exporter API.
3. **Sai host:** ứng dụng container gọi `localhost` thay vì DNS tên service Collector.

Khi môi trường dùng HTTPS/TLS hoặc mTLS, cần cấu hình exporter/Collector phù hợp, không đơn thuần thay `http` thành `https` mà bỏ qua chứng chỉ và danh tính.

## 5. Collector thử nghiệm để nhìn thấy spans

Một cách dễ kiểm tra đường xuất là dùng **OpenTelemetry Collector** với OTLP receiver và `debug` exporter. Đây là cấu hình **chỉ dành cho lab**, cho phép đọc dữ liệu spans từ output của Collector; nó chưa lưu trace vào một backend có giao diện tìm kiếm.

Ví dụ `otel-collector.yaml` (minh họa, không yêu cầu ghi file này trong bài):

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

processors:
  batch: {}

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

Nếu Spring Boot và Collector chạy cùng máy/network namespace, địa chỉ loopback trong ví dụ là phù hợp. Nếu chạy trong **hai container** khác nhau, Collector cần lắng nghe trên giao diện mạng container thích hợp và ứng dụng gửi tới tên dịch vụ Collector, ví dụ:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Trong tình huống container, receiver thường cần bind `0.0.0.0:4318` **bên trong mạng container được kiểm soát** và phải có network policy thích hợp. Không expose receiver không xác thực ra Internet chỉ để tiện thử.

Khi đã có binary Collector tương ứng, một lệnh chạy minh họa là:

~~~bash
otelcol-contrib --config=otel-collector.yaml
~~~

Tên binary tùy distribution được cài đặt. Trên một số bản cài đặt, binary mang tên `otelcol`; các component và version Collector cũng cần tương thích với file cấu hình.

**Cách xác minh:** phát sinh request trong ứng dụng, sau đó xem output của Collector có các spans/resource attributes từ `order-api` hay không. Output debug có thể chứa dữ liệu nhạy cảm trong attributes; chỉ bật chi tiết trong môi trường thử nghiệm, kiểm soát quyền xem và không sử dụng nó làm pipeline production lâu dài.

### Muốn lưu trace thì làm gì?

Một Collector production thường xuất tiếp tới **Jaeger, Tempo hoặc một backend phù hợp** qua exporter mà backend hỗ trợ. Cần cấu hình receiver/exporter, authentication, TLS, retry, batching, giới hạn tài nguyên và retention phù hợp. Collector **không tự động là nơi lưu trace lâu dài**; nếu chỉ có `debug` exporter, bạn mới xác minh được Collector nhận spans, chưa có giao diện điều tra lịch sử trong backend.

Collector cũng **không bắt buộc về mặt giao thức** nếu exporter gửi trực tiếp tới một backend nhận OTLP. Tuy nhiên, Collector thường hữu ích để tập trung chính sách xử lý, routing, bảo mật và quan sát pipeline.

## 6. Tạo custom observation để thử tracing

Ta có thể dùng Micrometer Observation mà không gọi trực tiếp OpenTelemetry SDK. Khi bridge và tracing handler đã được auto-configure, một observation có vòng đời đầy đủ có thể trở thành tracing span.

Ví dụ service nghiệp vụ minh họa:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderValidationService {

    private final ObservationRegistry registry;
    private final FraudGateway fraudGateway;

    public OrderValidationService(ObservationRegistry registry,
                                  FraudGateway fraudGateway) {
        this.registry = registry;
        this.fraudGateway = fraudGateway;
    }

    public Decision validate(OrderInput input) {
        return Observation.createNotStarted("order.validate", registry)
                .contextualName("validate order")
                .lowCardinalityKeyValue("operation", "validate")
                .lowCardinalityKeyValue("dependency", "fraud-gateway")
                .observe(() -> fraudGateway.evaluate(input));
    }

    public interface FraudGateway {
        Decision evaluate(OrderInput input);
    }

    public record OrderInput(String category, long amountMinorUnits) {}
    public record Decision(boolean accepted) {}
}
~~~

Đây là ví dụ có thể đưa vào một dự án Spring Boot có các dependency tương ứng. Phần thực hiện `FraudGateway` do ứng dụng định nghĩa. Những điểm quan trọng:

- `order.validate` là **tên ổn định**, không gắn mã đơn hàng hoặc request ID vào tên.
- `operation` và `dependency` có tập giá trị hữu hạn, phù hợp cho low-cardinality tags của metrics và metadata cơ bản.
- `observe(...)` quản lý `start`, scope, `stop` và lỗi trong một lambda đồng bộ theo Micrometer.
- Nếu tracer handler được cấu hình, span tương ứng có thể nằm trong trace của request HTTP cha.
- Nếu metrics handler cũng hoạt động, operation còn có thể xuất timing metrics; không được nhầm metric timer với một span duy nhất.

Khi cần kiểm soát vòng đời rõ ràng hơn, đặc biệt nếu phải thêm outcome theo kết quả:

~~~java
Observation observation = Observation
        .createNotStarted("order.validate", registry)
        .lowCardinalityKeyValue("operation", "validate");

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    Decision decision = fraudGateway.evaluate(input);
    observation.lowCardinalityKeyValue(
            "outcome", decision.accepted() ? "accepted" : "rejected");
    return decision;
} catch (RuntimeException exception) {
    observation.lowCardinalityKeyValue("outcome", "error");
    observation.error(exception);
    throw exception;
} finally {
    observation.stop();
}
~~~

Đoạn này minh họa thân một phương thức có biến `registry`, `fraudGateway` và `input` đã được định nghĩa. `openScope()` giữ observation hiện hành trong luồng đồng bộ, giúp tracing và logs correlation có ngữ cảnh; `stop()` hoàn tất vòng đời. **Đóng scope và dừng observation là hai thao tác khác nhau**.

Không gọi `start()` rồi lại dùng `observe(...)` một lần nữa trên cùng observation chỉ để “bảo đảm có span”. Hãy dùng **một** cách quản lý vòng đời nhất quán.

## 7. Trace đi qua các service như thế nào?

Một trace phân tán được liên kết nhờ **context propagation**, chứ không phải nhờ việc Collector nhận được hai span có tên giống nhau.

Với HTTP, W3C Trace Context thường dùng `traceparent`. Ví dụ:

~~~http
GET /api/orders/42 HTTP/1.1
Host: order-api
traceparent: 00-4f17c38a927d4b55a90714b02f8e6d19-3a9c31cdb4dcbd74-01
~~~

Trong đó:

- `00` là version của định dạng header.
- `4f17...` là trace ID 32 ký tự hex.
- `3a9...` là parent span ID 16 ký tự hex.
- `01` là tracing flags, thường liên quan quyết định sampling.

Một HTTP client có instrumentation thích hợp có thể **inject** `traceparent` vào request đi ra; HTTP server phía sau **extract** context để tạo server span thuộc cùng trace. Khi nhiều service làm đúng điều này, backend có thể hiển thị quan hệ client/server spans.

### Dùng HTTP client do Spring Boot cấu hình

Trong Spring Boot 3.2+ với Spring Framework có `RestClient`, cách thông dụng là inject `RestClient.Builder` do Spring Boot quản lý thay vì tạo client hoàn toàn thủ công:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PricingClient {

    private final RestClient restClient;

    public PricingClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://pricing-service:8080")
                .build();
    }

    public Price fetchPrice(String sku) {
        return restClient.get()
                .uri("/api/prices/{sku}", sku)
                .retrieve()
                .body(Price.class);
    }

    public record Price(long minorUnits, String currency) {}
}
~~~

`pricing-service` chỉ là hostname minh họa; muốn chạy cần dịch vụ thật và hệ thống tên phù hợp. Spring Boot instrument builder được quản lý khi tracing/observability phù hợp được bật. Nếu code tạo một `RestClient`, `RestTemplate` hay client HTTP tùy biến bên ngoài cơ chế instrumentation, propagation **có thể không xảy ra**.

Để kiểm tra end-to-end:

1. Gọi HTTP endpoint của `order-api`.
2. Xem trace ID ở logs hoặc Collector/backend.
3. Xác minh request của `order-api` sang `pricing-service` có context được truyền đúng.
4. Kiểm tra backend có **CLIENT span** và **SERVER span** liên quan, cùng trace ID và parent links đúng.
5. Nếu hai dịch vụ tạo hai trace riêng, kiểm tra instrumentation/propagator, không chỉnh OTLP exporter trước khi kiểm tra header.

Một Collector có thể nhận spans từ nhiều dịch vụ nhưng **không tự sửa parent–child relationship** nếu propagation bị mất trước đó.

## 8. Async, Reactor và MDC: những ranh giới dễ mất context

Trong xử lý đồng bộ, observation scope thường cho phép code chạy bên trong truy cập tracing context hiện hành. Nhưng qua thread pool, `CompletableFuture`, `@Async` hoặc Reactor, context có thể cần cơ chế propagation bổ sung.

Ví dụ gây hiểu nhầm:

~~~java
Observation.createNotStarted("fraud.async", registry)
        .observe(() -> CompletableFuture.supplyAsync(
                () -> fraudGateway.evaluate(input)));
~~~

Lambda trên có thể chỉ đo **thời gian tạo và lên lịch task**, vì `CompletableFuture` hoàn thành sau khi `observe(...)` đã đóng observation. Nếu code ở thread phụ không mang context, span của nó có thể mất parent hoặc logs thiếu trace ID.

Với async/reactive:

- Đặt vòng đời observation đúng theo **thời điểm công việc thực sự thực thi và kết thúc**.
- Dùng công cụ context propagation của stack đang sử dụng, không giữ một `Observation.Scope` mở rồi truyền thẳng qua thread tùy tiện.
- Với Reactor, nhớ publisher có thể là lazy; tạo `Mono` chưa đồng nghĩa công việc đã xảy ra.
- Xác minh context trong logs ở thread thực thi, không chỉ thread gọi ban đầu.
- Khi operation bị cancel, error hoặc timeout, cần thiết kế completion/error cleanup phù hợp để tránh span kéo dài hoặc mất dữ liệu.

**MDC không phải trace context chuẩn.** MDC thường là nơi logging framework đọc `traceId` và `spanId`; propagation giữa service dựa vào các carrier như HTTP headers hoặc message metadata. Sao chép một chuỗi `traceId` vào log không tự tạo quan hệ span cha–con.

## 9. Liên kết traces với logs

Khi Micrometer Tracing và logging integration hoạt động, logs có thể mang `traceId` và `spanId` trong MDC. Ví dụ log (minh họa):

~~~text
2026-11-22T10:30:12Z WARN order-api traceId=4f17c38a927d4b55a90714b02f8e6d19 spanId=3a9c31cdb4dcbd74 Validation dependency slow
~~~

Trong một số cấu hình Spring Boot, log correlation được hỗ trợ qua cấu hình sẵn. Nếu cần tự đặt pattern, một ví dụ cho môi trường thử nghiệm:

~~~yaml
logging:
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-}]"
~~~

Khi thay log pattern, hãy kiểm tra cấu hình logging/version để không vô tình làm mất các trường correlation đã được cung cấp mặc định. Trong production, structured JSON logs thường giúp truy vấn theo trace ID tốt hơn so với parser đọc một đoạn text tự do.

Cách điều tra phổ biến:

1. Tìm logs lỗi theo service và thời gian.
2. Lấy trace ID từ log nếu có.
3. Tìm trace ID ở backend tracing để xem đường đi request.
4. Đọc span durations/events/errors để xác định nơi cần điều tra.
5. Dùng metrics để kiểm tra ảnh hưởng lên toàn bộ traffic thay vì chỉ một trace.

**Nếu trace bị sample out**, log vẫn có thể chứa trace ID hoặc request ID theo context hiện có, nhưng không nhất thiết tìm được trace hoàn chỉnh ở backend. Logs không tự bị xóa vì tracing sampler bỏ một trace.

## 10. Sampling thay đổi dữ liệu bạn nhìn thấy ra sao?

Traces có thể rất lớn khi dịch vụ nhiều request/giây. **Sampling** là cơ chế chọn trace nào được thu thập/ghi nhận, giúp cân bằng chi phí và độ bao phủ.

Trong một lab tải thấp:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Trong production, có thể chọn một tỉ lệ nhỏ hơn, ví dụ:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Đây chỉ là **ví dụ chính sách 10%**, không phải khuyến nghị mặc định cho mọi hệ thống. Tỉ lệ phù hợp phụ thuộc lưu lượng, SLO, giá trị phân tích, chi phí backend và đặc tính sự cố hiếm.

### Head sampling ở ứng dụng

Một tracing SDK có thể quyết định **lấy mẫu gần đầu trace**. Với parent-based sampling, một quyết định sampling đã được upstream truyền xuống có thể ảnh hưởng lựa chọn ở service con. Vì thế, đặt `probability: 1.0` tại một downstream service **không nhất thiết** tạo span được lưu cho mọi request từ upstream đã unsampled.

### Tail sampling ở Collector

Collector có thể được cấu hình xử lý trace theo quyết định ở cuối trace, ví dụ ưu tiên traces có lỗi hoặc độ trễ cao. Nhưng muốn có dữ liệu để ra quyết định tail sampling, các span liên quan phải **được gửi tới Collector**. Nếu head sampler trong ứng dụng đã bỏ span, Collector không thể tạo lại phần chưa bao giờ được xuất.

Tail sampling còn cần quản lý memory, thời gian chờ các span, load balancing và các thành phần của pipeline phù hợp. Không đơn giản coi thêm một processor là đã có đầy đủ trace lỗi.

### Metrics có bị sampling tương ứng không?

Không. Các metric như HTTP request count và latency qua `MeterRegistry` có thể tiếp tục tổng hợp các lần chạy, ngay cả khi chỉ một phần traces được giữ. Vì vậy:

- Không lấy số traces được lưu làm số request chính xác cho SLO.
- Dùng metrics để tìm **tần suất, tỉ lệ và xu hướng**.
- Dùng một số traces đại diện để hiểu **đường thực thi và dependency**.
- Dùng logs để xem sự kiện cụ thể khi trace không còn.

## 11. Attributes, tags và cardinality

Trong Micrometer Observation, có sự phân biệt hữu ích:

- `lowCardinalityKeyValue(...)`: thường phù hợp cho các chiều hữu hạn như `operation=validate`, `outcome=success/error`, `dependency=fraud-gateway`. Metrics handler có thể dùng chúng để tạo metric labels.
- `highCardinalityKeyValue(...)`: dành cho metadata chi tiết hơn trong tracing khi handler hỗ trợ; không phù hợp đưa trực tiếp vào metric labels.

Ví dụ:

~~~java
Observation.createNotStarted("order.validate", registry)
        .lowCardinalityKeyValue("operation", "validate")
        .lowCardinalityKeyValue("outcome", "accepted")
        .highCardinalityKeyValue("business.reference", safeReference);
~~~

`safeReference` ở đây là giá trị **đã được đánh giá quyền riêng tư** chứ không phải cứ có ID là được phép đưa vào trace. High-cardinality trace attributes vẫn gây chi phí index/storage, có thể bị exporter/backend truncate hoặc loại theo chính sách. Đừng đưa email, token truy cập, số thẻ, request body hoặc dữ liệu cá nhân vào spans theo mặc định.

### Đặt tên span an toàn

Tránh:

~~~java
// Không nên: tên observation biến đổi theo từng order.
Observation.createNotStarted("order.validate." + orderId, registry);
~~~

Nên dùng tên ổn định:

~~~java
Observation.createNotStarted("order.validate", registry);
~~~

Giữ tên và attributes nhất quán giữa các dịch vụ giúp backend dễ tìm kiếm và tránh cardinality/chi phí cao. Tracing cũng có semantic conventions (ví dụ các thuộc tính HTTP/DB) thay đổi theo phiên bản instrumentation; kiểm tra tên thực tế trước khi tạo dashboard hay span search cố định.

### Một OTLP exporter có tự giải quyết privacy không?

Không. Nó vận chuyển telemetry theo cấu hình, không tự đảm bảo dữ liệu đã được khử nhạy cảm. Nên kiểm soát **tại nguồn**; nếu cần, thêm chính sách lọc/xóa attributes có chủ đích ở Collector và backend. Không xem một pipeline là an toàn chỉ vì dùng OpenTelemetry.

## 12. Bảo mật OTLP và Collector

Với local lab, `http://localhost:4318/v1/traces` không mã hóa có thể được chấp nhận khi tất cả thành phần chạy trong môi trường phát triển cô lập. Trong production, cần thiết kế đường truyền và quyền truy cập rõ ràng:

| Rủi ro | Biện pháp |
| --- | --- |
| OTLP receiver lộ ra Internet | Chỉ bind vào network nội bộ, dùng firewall/network policy. |
| Spans đi trên đường mạng không mã hóa | Dùng TLS/mTLS hoặc bảo vệ đường truyền theo kiến trúc. |
| Client không có danh tính phù hợp | Dùng authentication/authorization tại receiver, gateway hoặc proxy. |
| Token/certificate rò rỉ | Lưu bằng secret manager, xoay vòng và phân quyền chặt. |
| Attributes chứa dữ liệu nhạy cảm | Giới hạn ở instrumentation và Collector; kiểm tra payload/sample. |
| Collector quá tải | Batching, memory limits, retry/queue và giám sát dropped spans. |
| Backend có retention quá dài | Thiết kế retention, sampling và phân quyền truy vấn hợp lý. |

Không hard-code API key hoặc credential thật vào `application.yml` commit trong repository. Cần chọn cấu hình exporter headers, certificate trust, proxy hoặc environment variables theo phiên bản Spring Boot/OpenTelemetry SDK đang dùng. **Không tắt TLS verification** như một giải pháp lâu dài khi gặp lỗi chứng chỉ.

Bản thân Collector cũng cần observability: đo dữ liệu nhận/đã gửi/bị loại, lỗi exporter, queue, CPU/memory. Nếu ứng dụng vẫn gửi spans nhưng pipeline Collector mất dữ liệu, chỉ nhìn logs của ứng dụng sẽ không đủ.

## 13. Xác minh trace end-to-end

Một quy trình thử nghiệm ít rủi ro:

### Bước 1 — xác minh cấu hình

Kiểm tra trong ứng dụng chạy thử:

- Actuator và `micrometer-tracing-bridge-otel` có mặt.
- OTLP tracing exporter được auto-configure.
- `management.otlp.tracing.endpoint` trỏ tới đúng OTLP/HTTP receiver.
- Sampling đang phù hợp với lab.
- Collector có receiver traces và pipeline có exporter phù hợp.

### Bước 2 — tạo traffic thật

Gọi một HTTP endpoint được instrument:

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Địa chỉ là ví dụ; endpoint phải thật sự tồn tại trong ứng dụng thử. Có thể gọi lặp lại vài lần vì một số request bị sampling hoặc chưa đến collector/backend.

### Bước 3 — xem ứng dụng và Collector

Tìm các dấu hiệu:

- HTTP request đã thực thi và có log phù hợp.
- Log có trace ID/span ID khi logging correlation đang hoạt động.
- Collector debug output nhận `ResourceSpans`, `Span` hoặc thông tin tương đương với `service.name=order-api`.
- Các attributes/operation names hợp lý, không chứa dữ liệu nhạy cảm.

**Collector có dữ liệu là bằng chứng vượt qua chặng exporter/receiver**, chưa chứng minh backend lưu hoặc index thành công.

### Bước 4 — kiểm tra backend trace

Nếu Collector đã được nối tới backend:

1. Tìm service `order-api` và thời gian của request thử.
2. Tìm trace theo ID từ log hoặc từ danh sách traces.
3. Xác minh server span và custom span `order.validate`, nếu code path đã chạy.
4. Nếu có dependency được instrument, kiểm tra client/server spans có cùng trace ID và quan hệ parent/child hợp lý.
5. Xem duration, status, error/event, attributes và resource metadata.

### Bước 5 — đối chiếu với metrics

Nếu ứng dụng có metrics observation handler và `MeterRegistry` phù hợp, tìm timing metrics cho HTTP và custom operation. Đừng đòi số traces bằng request count; sampling/tracing pipeline khiến chúng khác nhau.

Để xem metrics qua Prometheus, cần thêm **registry/exporter metrics** và endpoint/scraper tương ứng. **OTLP tracing exporter không phải Prometheus registry**.

## 14. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Có HTTP metrics, không có trace | Chưa có tracing bridge/exporter, sampler bỏ traces hoặc Collector/backend sai. | Kiểm tra dependencies, sampling và tracing pipeline riêng. |
| Không thấy span trên Collector | Sai endpoint, port/transport/path, DNS/network, TLS/auth hoặc exporter chưa khởi tạo. | Xác minh app→receiver, Collector listener/logs. |
| Gửi HTTP tới cổng 4317 bị lỗi | Receiver 4317 thường là OTLP/gRPC, không phải OTLP/HTTP. | Dùng transport đúng; HTTP thường tới 4318/v1/traces. |
| Collector nhận spans nhưng backend trống | Pipeline chưa có exporter backend, exporter lỗi hoặc backend lọc/index chậm. | Xem pipeline config, Collector exporter errors và backend ingestion. |
| Service name không đúng | Resource attributes/config không như mong đợi. | Xem `service.name` trong payload Collector/backend. |
| Hai service tạo hai trace riêng | Thiếu `traceparent`, client/server không instrument hoặc context mất qua async. | Kiểm tra HTTP headers, tracing scopes, executor/Reactor context. |
| Logs không có trace ID | Logging pattern/MDC, tracing integration hoặc scope chưa active. | Kiểm tra log config và request instrumented thực. |
| Custom span thiếu hoặc rời parent | Observation chưa chạy đúng vòng đời, không mở scope hoặc code thực thi ngoài context. | Kiểm tra `observe`/`start/openScope/stop` và context propagation. |
| Traces xuất hiện không ổn định | Sampling, batching, network/exporter retries hoặc traffic quá thấp. | Lab với sampling phù hợp; kiểm tra Collector/backend theo thời gian. |
| Trace có dữ liệu nhạy cảm | Instrumentation thêm PII/credentials vào attributes, logs hoặc headers. | Rà soát instrumentation, lọc Collector và quyền truy cập. |
| Collector quá tải, mất spans | Lưu lượng cao, queue/backpressure hoặc giới hạn bộ nhớ. | Kiểm tra dropped spans, retry, batching và resource usage. |
| Tăng sampling lên 1.0 vẫn thiếu một số trace | Upstream parent sampling, exporter/backend lỗi hoặc request không được instrument. | Kiểm tra trace flags, toàn tuyến instrumentation và Collector. |

### Đừng sửa nhầm tầng

Nếu **không có span được tạo** thì thay OTLP endpoint chưa chắc giúp. Nếu **span có tại Collector nhưng không ở backend** thì thêm custom `Observation` cũng không giải quyết phần export backend. Nếu **span có nhưng parent–child sai** thì chỉnh sampler không thay thế context propagation.

Hãy tìm **ranh giới đầu tiên không có bằng chứng**, rồi sửa ở ranh giới đó.

## 15. Tình huống điều tra: checkout chậm sau một deploy

Giả sử sau khi triển khai, P95 của `POST /checkout` tăng từ 250 ms lên 1,4 giây. Ứng dụng gồm gateway, order service và inventory service, cùng xuất traces qua OTLP Collector.

Một cách điều tra có cấu trúc:

1. **Metrics xác nhận phạm vi:** xem request rate, 5xx rate, P95 theo route/service/instance. Không chỉ nhìn một request.
2. **Logs tìm sự kiện:** timeout, retry, “connection pool exhausted”, trace ID và thời điểm deploy.
3. **Tracing backend theo trace ID:** chọn một vài request chậm, đối chiếu request bình thường và kiểm tra critical path.
4. **Đọc waterfall:** nếu span client tới inventory kéo dài, so sánh với server span ở inventory. Nếu thời lượng chỉ tăng ở client, kiểm tra network, queue, connection pool và retries trước khi kết luận server chậm.
5. **Kiểm tra sự đầy đủ của trace:** nếu thiếu inventory server span, xem propagation và exporter ở inventory, không tự suy rằng inventory chưa xử lý request.
6. **Kiểm tra sampling:** một request báo lỗi có thể không có trace được giữ. Dùng metrics/logs và Collector telemetry để xác định nguồn thiếu.
7. **Đặt giả thuyết và xác minh:** bổ sung số liệu pool/DB/service latency, sau đó đo lại sau thay đổi.

Trong ví dụ này, **OTLP chỉ vận chuyển spans**. Giá trị điều tra đến từ instrumentation đúng, metadata có ngữ nghĩa, propagation nguyên vẹn, sampling phù hợp và backend lưu được những spans quan trọng.

## 16. Bài tập tự kiểm tra

### Bài 1 — OTLP/HTTP hay gRPC?

Ứng dụng dùng endpoint `http://localhost:4317/v1/traces`, còn Collector chỉ bật gRPC ở cổng 4317 và HTTP ở 4318. Vì sao trace không xuất hiện?

**Đáp án:** Ứng dụng đang gửi theo kiểu URL OTLP/HTTP tới cổng gRPC. Cần cấu hình exporter dùng transport gRPC phù hợp hoặc đổi sang receiver HTTP và endpoint `http://localhost:4318/v1/traces`.

### Bài 2 — Collector có span, backend không có

Collector debug exporter in spans của `order-api`, nhưng trace backend không tìm thấy service này. Nên sửa Micrometer Observation trước không?

**Đáp án:** Không. Span đã vượt qua ứng dụng và receiver. Kiểm tra Collector pipeline/exporter tới backend, TLS/auth, data dropping, index/retention và quyền truy vấn ở backend.

### Bài 3 — Hai trace ID khác nhau

Service A gọi service B, cả hai đều xuất spans tới cùng Collector, nhưng trace ID của B khác A. Có phải Collector chưa nối traces?

**Đáp án:** Collector thường không thể tự nối hai traces khi upstream không truyền parent context. Kiểm tra `traceparent` trên lời gọi HTTP, instrumentation của client/server và context propagation qua async.

### Bài 4 — Metrics và sampling

Hệ thống ghi metrics cho 10.000 HTTP requests nhưng trace backend có khoảng 1.000 trace. Có thể kết luận 9.000 request bị mất không?

**Đáp án:** Không. Tỉ lệ tracing sampling và exporter/collector có thể khiến số traces nhỏ hơn request count. Metrics vẫn tổng hợp nhiều request; cần đối chiếu các pipeline trước khi kết luận.

### Bài 5 — Attribute nào phù hợp?

Một nhóm muốn thêm `customerEmail`, `requestId`, `operation=validate`, `dependency=fraud-gateway` vào mọi span và timer metric. Nên xử lý thế nào?

**Đáp án:** `operation` và `dependency` có thể là low-cardinality key-values nếu tập giá trị hữu hạn. Email là dữ liệu nhạy cảm, không ghi tùy tiện vào telemetry. Request ID có cardinality cao, không đưa vào metric labels; chỉ cân nhắc logs hoặc trace attribute theo chính sách. Không bắt buộc mọi span phải mang toàn bộ metadata.

### Bài 6 — Vì sao async span không đúng?

Một observation bao lời gọi `CompletableFuture.supplyAsync(...)` và kết thúc trước khi công việc thật chạy xong. Điều gì sai?

**Đáp án:** Đoạn observation đang đo phần lên lịch, không đo toàn bộ công việc bất đồng bộ. Cần quản lý vòng đời theo completion của async task, kèm context propagation và cleanup đúng execution context.

## 17. Checklist triển khai OpenTelemetry với OTLP

- [ ] Chọn **một** tracing implementation phù hợp với Spring Boot/Micrometer, không phối bridge vô tình.
- [ ] Có Actuator, Micrometer Tracing OTel bridge và OTLP exporter tương thích.
- [ ] Endpoint OTLP đúng **transport, host, port, path và TLS/auth**.
- [ ] `localhost` chỉ được dùng khi ứng dụng và receiver cùng network namespace phù hợp.
- [ ] Collector có traces receiver và pipeline exporter tới đích mong muốn; debug exporter chỉ dùng cho lab.
- [ ] `service.name`, operation names và attributes hiển thị rõ ràng trong backend.
- [ ] Custom observation có vòng đời hoàn chỉnh, outcome/error được xử lý phù hợp.
- [ ] HTTP/messaging context propagation giữ trace ID và parent links xuyên service.
- [ ] Async/Reactor context propagation được kiểm chứng, không đo nhầm việc tạo task.
- [ ] Sampling phù hợp traffic/chi phí; hiểu ảnh hưởng của parent-based và tail sampling.
- [ ] Không dùng high-cardinality/sensitive fields làm metric labels; traces cũng có chính sách dữ liệu.
- [ ] Logs có correlation field khi tracing context đang active; pipeline logs độc lập vẫn hoạt động.
- [ ] Collector và trace backend có observability cho lỗi export, dropped spans và resource usage.
- [ ] Có phép kiểm thử end-to-end từ request thật tới Collector và backend, không chỉ kiểm tra cấu hình YAML.
- [ ] Khi điều tra sự cố, kết hợp metrics để tìm phạm vi, logs để lấy sự kiện và traces để xem đường thực thi.

**Ghi nhớ:** **OpenTelemetry** cung cấp hệ sinh thái tracing, **OTLP** vận chuyển spans, **Collector** xử lý/định tuyến telemetry, còn **Micrometer Observation** là cách Spring Boot mô tả các hoạt động trong ứng dụng. Chỉ khi instrumentation, context propagation, sampling, exporter và backend cùng hoạt động, distributed tracing mới giúp bạn liên kết request xuyên dịch vụ và tìm nguyên nhân lỗi hoặc độ trễ một cách có bằng chứng.
