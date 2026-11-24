# Chọn tracer theo hệ thống

Trong chương **Tracer implementation** của mô-đun **SPRING_BOOT_OBSERVABILITY**, chọn tracer là quyết định chọn implementation đứng sau abstraction tracing mà ứng dụng Spring Boot sử dụng. Micrometer Tracing cung cấp API thống nhất cho ứng dụng; bridge kết nối API đó với một tracing implementation như **OpenTelemetry** hoặc **Brave**. Implementation, exporter và backend cần phù hợp với hạ tầng hiện có, cách truyền context, chính sách sampling, khả năng vận hành và chi phí telemetry.

Mô-đun này hướng dẫn thiết lập observability cho Spring Boot bằng **Micrometer Observation, metrics, logs và distributed tracing**; học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng thực tế. Chọn tracer ảnh hưởng tới khả năng nối request qua nhiều dịch vụ, đường xuất dữ liệu, quy tắc metadata, công cụ vận hành và kế hoạch chuyển đổi sau này.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Micrometer Observation**, **Micrometer Tracing**, tracing bridge, tracer implementation, exporter và backend.
2. Đánh giá khi nào nên dùng OpenTelemetry bridge, khi nào hệ thống hiện hữu có thể tiếp tục dùng Brave/Zipkin.
3. Chọn tracer dựa trên backend, dịch vụ trong hệ thống, instrumentation, propagation, sampling, bảo mật và năng lực vận hành.
4. Cấu hình Spring Boot ở mức dependency và property cho một implementation phù hợp.
5. Tránh cài nhiều bridge/tracer cạnh tranh hoặc tạo nhiều tracing pipeline không chủ đích.
6. Kiểm chứng trace ID, parent–child spans, resource attributes và đường xuất dữ liệu end-to-end.
7. Lập kế hoạch migration giữa các implementation mà vẫn giữ correlation trong giai đoạn chuyển tiếp.
8. Kết hợp tracing với metrics và logs, không dùng số lượng traces thay thế cho traffic/error metrics.

## 2. Phân biệt các lớp trong tracing stack

Các thành phần sau thường được gọi chung là “tracer”, nhưng vai trò của chúng khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Micrometer Observation** | Mô tả vòng đời một hoạt động ở mức ứng dụng: tên, key-values, scope, event, lỗi. | `order.lookup`, `payment.authorize`. |
| **Micrometer Tracing** | Abstraction cho span, tracer, current span, propagation và baggage. | API tracing được tích hợp với Spring Boot. |
| **Tracing bridge** | Nối abstraction Micrometer Tracing với implementation cụ thể. | OpenTelemetry bridge hoặc Brave bridge. |
| **Tracer implementation** | Quản lý span/context và hành vi tracing phía ứng dụng. | OpenTelemetry SDK hoặc Brave. |
| **Propagator** | Inject/extract trace context qua HTTP headers hoặc message carrier. | W3C Trace Context, B3. |
| **Exporter/reporter** | Gửi spans ra khỏi process theo giao thức hoặc định dạng được hỗ trợ. | OTLP exporter, Zipkin reporter. |
| **Collector/agent** | Nhận, batch, lọc, định tuyến hoặc chuyển tiếp telemetry. | OpenTelemetry Collector hoặc agent của nền tảng. |
| **Backend** | Lưu trữ, tìm kiếm, phân tích và hiển thị traces. | Jaeger, Tempo, Zipkin hoặc APM tương thích. |

Một luồng phổ biến:

~~~mermaid
flowchart LR
    App["Spring Boot application"] --> Obs["Micrometer Observation"]
    Obs --> MT["Micrometer Tracing"]
    MT --> Bridge["Một tracing bridge"]
    Bridge --> Impl["Tracer implementation"]
    Impl --> Prop["Propagator"]
    Impl --> Export["Exporter / reporter"]
    Export --> Collector["Collector / agent"]
    Collector --> Backend["Trace backend"]
    App --> Metrics["Metrics: MeterRegistry"]
    App --> Logs["Logs / MDC"]
    Backend --> Search["Trace search / waterfall"]
    Metrics --> Correlate["Điều tra kết hợp"]
    Logs --> Correlate
    Search --> Correlate
~~~

Micrometer Observation là điểm instrument nghiệp vụ; bridge/tracer tạo và quản lý spans; exporter chuyển dữ liệu; backend là nơi người vận hành tìm trace. **Backend nhận OTLP không tự quyết định ứng dụng phải dùng OpenTelemetry bridge**: còn có các đường tương thích khác. Ngược lại, tracer có thể tạo span đúng nhưng exporter/reporter sai thì backend vẫn không thấy dữ liệu.

Một trace gồm nhiều **span** có quan hệ. Mỗi span mô tả một công đoạn: server nhận HTTP request, gọi database, gửi HTTP client request hoặc xử lý bước nghiệp vụ.

~~~text
Trace ID: 4f17c38a927d4b55a90714b02f8e6d19
└── SERVER GET /orders/{id}                780 ms
    ├── INTERNAL order.lookup                45 ms
    └── CLIENT POST inventory-service       690 ms
        └── SERVER POST /inventory/reserve   650 ms
~~~

Trong ví dụ giả định, trace giúp định vị nhánh tốn thời gian. Không cộng duration lồng nhau tùy tiện: span cha bao hàm các span con, các nhánh cũng có thể chạy đồng thời. Trace ID định danh trace; span ID định danh span; parent span ID biểu diễn quan hệ; attributes/status/events mô tả hoạt động và lỗi; resource attributes mô tả service/process, chẳng hạn `service.name`.

## 3. Những lựa chọn thường gặp trong Spring Boot

Với hệ sinh thái Spring Boot 3.x, hai lựa chọn bridge thường được nhắc tới là **OpenTelemetry** và **Brave**.

| Tiêu chí | Micrometer Tracing với OpenTelemetry bridge | Micrometer Tracing với Brave bridge |
| --- | --- | --- |
| Implementation | OpenTelemetry SDK/API qua bridge của Micrometer. | Brave qua bridge của Micrometer. |
| Hệ sinh thái | Chuẩn mở, instrumentation/exporter rộng, hỗ trợ nhiều ngôn ngữ/nền tảng. | Hệ sinh thái Zipkin/Brave lâu đời, phù hợp hệ thống đang dùng Zipkin/B3. |
| Đường xuất phổ biến | OTLP tới Collector hoặc backend nhận OTLP; cũng có thể có exporter khác. | Zipkin reporter tới Zipkin endpoint; tùy cấu hình có thể dùng đường xuất tương thích khác. |
| Propagation | W3C Trace Context thường là lựa chọn phổ biến; hỗ trợ propagator được cấu hình. | B3 thường gặp trong hệ thống Zipkin; phải cấu hình đồng nhất với dịch vụ còn lại. |
| Phù hợp khi | Muốn chuẩn hóa telemetry đa ngôn ngữ, dùng OTLP/Collector hoặc nền tảng OTel. | Đã có hạ tầng Brave/Zipkin ổn định và nhu cầu hiện tại được đáp ứng. |
| Cần xác minh | Resource attributes, exporter, sampler, propagators, semantic conventions và SDK configuration. | Reporter endpoint, B3/W3C propagation, span model và exporter compatibility. |

Đây là so sánh định hướng. Cả hai hướng đều có thể hoạt động với Micrometer Tracing, nhưng **không phải cùng một bridge**. Hãy kiểm tra dependency tree và auto-configuration của phiên bản Spring Boot/Micrometer thực tế trước khi triển khai.

### OpenTelemetry bridge

Thường là lựa chọn phù hợp khi:

- Hệ thống có nhiều ngôn ngữ và muốn một chuẩn telemetry chung.
- Nền tảng giám sát đã nhận OTLP hoặc đang chuẩn hóa qua OpenTelemetry Collector.
- Cần tận dụng hệ sinh thái instrumentation, resource attributes và exporter của OpenTelemetry.
- Có kế hoạch đưa metrics/traces/logs về cùng một pipeline hoặc tiêu chuẩn metadata.
- Đang xây dựng tracing mới và chưa bị ràng buộc bởi Brave/Zipkin cụ thể.

### Brave bridge

Có thể là lựa chọn hợp lý khi:

- Hệ thống Spring Boot hiện tại đã vận hành với Brave/Zipkin và các service liên quan dùng B3.
- Dashboard, công cụ vận hành và runbook phụ thuộc Zipkin.
- Đội vận hành hiểu rõ sampling, reporter, dependency và giới hạn của pipeline hiện tại.
- Việc đổi implementation chưa tạo giá trị đủ lớn để bù chi phí migration và kiểm thử tương thích.

Không nên giữ Brave chỉ vì “hệ thống cũ đang chạy” nếu backend, tooling và yêu cầu tương lai đã chuyển sang chuẩn khác. Cũng không nên đổi sang OpenTelemetry chỉ vì tên gọi phổ biến mà chưa có kế hoạch chuyển đổi propagation, resource metadata và instrumentation.

## 4. Ma trận quyết định: chọn theo hệ thống

Bắt đầu bằng câu hỏi **hệ thống hiện tại cần giải quyết vấn đề nào?**

| Tình trạng hệ thống | Hướng nên đánh giá trước | Lý do |
| --- | --- | --- |
| Dịch vụ mới, đa ngôn ngữ, nền tảng nhận OTLP | OpenTelemetry bridge | Chuẩn hóa giao thức, metadata và pipeline ở nhiều service. |
| Đã dùng OpenTelemetry Collector và OTLP cho phần lớn workloads | OpenTelemetry bridge | Tái sử dụng pipeline, cấu hình và năng lực vận hành. |
| Java/Spring Boot cũ dùng Brave và Zipkin ổn định | Brave bridge hoặc migration theo giai đoạn | Hạn chế thay đổi đồng thời nhiều tầng đang hoạt động. |
| Backend chỉ nhận Zipkin format nhưng ứng dụng mới dùng OTel | Đánh giá OTel exporter tương thích hoặc Collector chuyển đổi | Không mặc định phải đổi backend cùng lúc với tracer. |
| Nền tảng APM cung cấp agent riêng | So sánh agent, bridge và khả năng ingest OTLP | Tránh instrument hai lần hoặc bỏ sót spans. |
| Upstream dùng B3, service mới dùng W3C | Chọn chiến lược propagation liên thông | Tracer cần nhận/gửi đúng header ở từng ranh giới. |
| Chi phí tracing cao, cần giảm ingest | Giữ implementation phù hợp và thiết kế sampling | Thay tracer không tự giải quyết chi phí dữ liệu. |
| Trace đứt qua async/thread/message | Kiểm tra context propagation và instrumentation | Đổi exporter không tự sửa context bị mất. |

Có thể dùng bảng chấm điểm nội bộ, gán trọng số 1–5:

| Yếu tố đánh giá | Trọng số gợi ý | Câu hỏi |
| --- | ---: | --- |
| Tương thích backend/pipeline | 5 | Backend có nhận giao thức và metadata của implementation không? |
| Propagation qua các service | 5 | Có kết nối được W3C/B3/headers đang sử dụng không? |
| Instrumentation framework/client | 4 | Có instrument Spring MVC/WebFlux, HTTP client, DB, messaging không? |
| Sampling và chi phí | 4 | Có head/tail sampling, giới hạn và quan sát dropped spans không? |
| Vận hành và bảo mật | 4 | Có TLS, auth, retention, access control và dashboard không? |
| Migration/duy trì | 3 | Đội có thể nâng cấp bridge/exporter và kiểm thử không? |
| Tính năng riêng của backend | 2 | Có phụ thuộc query, attributes hoặc UI riêng của vendor không? |

Đây là khung thảo luận, không phải điểm số chuẩn của Micrometer. Backend tương thích nhưng propagation không thống nhất thì tracing vẫn bị tách. Tracer phù hợp nhưng đội không vận hành được Collector/agent thì hệ thống vẫn có thể mất spans mà không phát hiện.

## 5. Cấu hình OpenTelemetry bridge trong Spring Boot

Ví dụ cho **Spring Boot 3.x**, Java 17+, Spring MVC và dependency versions do Spring Boot BOM quản lý:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Cấu hình OTLP/HTTP tới OpenTelemetry Collector:

~~~yaml
spring:
  application:
    name: order-api

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Ý nghĩa:

- `micrometer-tracing-bridge-otel` kết nối Micrometer Tracing với OpenTelemetry.
- `opentelemetry-exporter-otlp` cung cấp exporter OTLP phù hợp với auto-configuration.
- Endpoint ví dụ dùng OTLP/HTTP traces, thường là port 4318 và path `/v1/traces`.
- `sampling.probability: 0.1` là ví dụ giữ khoảng 10% head-sampled traces trong trường hợp cấu hình hỗ trợ; không phải khuyến nghị chung.
- `order-api` là tên service cần kiểm tra trong resource attributes ở Collector/backend.

Nếu ứng dụng và Collector chạy trong các container khác nhau, `otel-collector` phải phân giải được trong network của ứng dụng. Không dùng `localhost` trừ khi exporter và receiver thật sự chia sẻ network namespace phù hợp.

### OTLP/gRPC là lựa chọn vận chuyển khác

Nếu receiver chỉ bật gRPC, exporter phải sử dụng OTLP/gRPC tương ứng. Cổng mặc định thường dùng cho OTLP/gRPC là **4317**, trong khi OTLP/HTTP thường dùng **4318**. Không chỉ thay số port trong URL HTTP và kỳ vọng transport tự đổi sang gRPC.

Cũng cần xác minh TLS/auth khi đi qua mạng thật. Endpoint `http://` chỉ phù hợp với lab hoặc network đã được bảo vệ; production nên sử dụng TLS/mTLS và thông tin xác thực theo chính sách nền tảng.

## 6. Khi nào tiếp tục dùng Brave bridge?

Nếu hệ thống Spring Boot hiện tại đã dùng Brave và Zipkin, một cấu hình tham khảo cho Spring Boot 3.x có thể gồm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
~~~

Ví dụ cấu hình Zipkin endpoint:

~~~yaml
spring:
  application:
    name: order-api

management:
  tracing:
    sampling:
      probability: 0.1
  zipkin:
    tracing:
      endpoint: http://zipkin:9411/api/v2/spans
~~~

Ví dụ giả định hạ tầng nhận Zipkin spans tại endpoint tương ứng và phiên bản Spring Boot đang dùng hỗ trợ các property này. Cần xác minh package, dependency management và property names theo release cụ thể. Không thêm Brave bridge và OpenTelemetry bridge cùng lúc cho cùng một registry/pipeline chỉ để thử xem cái nào “tốt hơn”.

### Backend Zipkin và OTLP

Zipkin là backend và có định dạng/API ingest riêng; OTLP là giao thức OpenTelemetry. Có thể đặt Collector làm lớp trung gian để nhận OTLP và xuất sang backend/format được hỗ trợ. Cần xác minh khả năng exporter/conversion thực tế, bao gồm mapping attributes, resource, status, events và sampling.

Không giả định mọi span attribute trong OTLP sẽ được thể hiện giống hệt sau khi chuyển đổi sang Zipkin. Hãy kiểm tra payload và khả năng tìm kiếm của backend, nhất là khi dashboard dựa vào tên tag cụ thể.

## 7. Dùng Micrometer Observation trong code nghiệp vụ

Với Spring Boot đang sử dụng Micrometer Observation, nên ưu tiên instrument hoạt động nghiệp vụ qua **Observation API** khi abstraction đó đáp ứng nhu cầu:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ObservationRegistry registry;
    private final OrderRepository repository;

    public OrderService(ObservationRegistry registry,
                        OrderRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    public Order load(long id) {
        return Observation.createNotStarted("order.load", registry)
                .contextualName("load order")
                .lowCardinalityKeyValue("operation", "load")
                .lowCardinalityKeyValue("component", "order-service")
                .observe(() -> repository.findById(id)
                        .orElseThrow(() ->
                                new IllegalArgumentException("Order not found")));
    }

    public interface OrderRepository {
        java.util.Optional<Order> findById(long id);
    }

    public record Order(long id, String status) {}
}
~~~

Khi OpenTelemetry bridge, metrics handler và tracing handler phù hợp được cấu hình, cùng observation có thể góp phần tạo timing metric và span. Code nghiệp vụ không cần phụ thuộc trực tiếp OpenTelemetry SDK chỉ để dùng abstraction Micrometer.

Dùng trực tiếp OpenTelemetry API có thể hợp lý nếu một thư viện/platform đã chuẩn hóa trên OTel API, cần tracing feature chưa được abstraction Micrometer cung cấp trong phiên bản đang dùng, hoặc một thành phần đa ngôn ngữ yêu cầu API cụ thể. Nếu instrument qua cả Micrometer và OTel API, phải xác định rõ cách chia sẻ tracer/context. Không tạo hai span cho cùng thao tác chỉ vì cả hai API đều được gọi.

### Kiểm soát cardinality

`operation=load` và `component=order-service` có số giá trị hữu hạn. Không thêm order ID, email, token hoặc request ID làm low-cardinality key-value. Nếu cần mã tham chiếu trong trace, cân nhắc high-cardinality attribute với chính sách quyền riêng tư, retention và chi phí index; không đưa dữ liệu nhạy cảm vào telemetry theo mặc định.

## 8. Propagation phải khớp với phần còn lại của hệ thống

Một trace chỉ liên kết xuyên dịch vụ khi context được truyền đúng. W3C Trace Context thường biểu diễn thông tin bằng header `traceparent`:

~~~http
GET /inventory/42 HTTP/1.1
Host: inventory-service
traceparent: 00-4f17c38a927d4b55a90714b02f8e6d19-3a9c31cdb4dcbd74-01
~~~

Các hệ thống Brave/Zipkin lâu đời có thể sử dụng B3, ví dụ header `b3` hoặc các header B3 multi-header. Tên header và cách mã hóa cần được cấu hình thống nhất giữa caller và callee.

| Tình trạng upstream/downstream | Điều cần làm |
| --- | --- |
| Tất cả service dùng W3C Trace Context | Chuẩn hóa W3C và kiểm tra inject/extract ở HTTP/messaging. |
| Nhiều service cũ dùng B3 | Cấu hình propagator phù hợp hoặc giai đoạn chuyển tiếp hỗ trợ format cũ. |
| Gateway nhận W3C, service đích chỉ hiểu B3 | Dùng gateway/bridge có khả năng chuyển context và kiểm thử parent links. |
| Service dùng cả W3C và B3 | Xác định thứ tự ưu tiên, tránh hai trace contexts cạnh tranh trong một request. |
| Async thread hoặc Reactor mất parent | Kiểm tra context propagation của executor/reactive stack. |
| Messaging không có span liên kết | Kiểm tra message headers và instrumentation inject/extract. |

Không phải cứ đổi tracer implementation là hệ thống tự chuyển toàn bộ header. Nếu upstream gửi B3 nhưng downstream chỉ extract W3C, trace có thể bị tách thành hai root. Nếu hai định dạng cùng hiện diện nhưng có trace IDs khác nhau, cần quy định rõ propagator nào được ưu tiên.

### Context propagation qua HTTP client

Spring Boot thường có instrumentation phù hợp khi dùng client/builder được auto-configure. Ví dụ với `RestClient.Builder` do Spring quản lý trong phiên bản hỗ trợ:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {

    private final RestClient client;

    public InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service:8080")
                .build();
    }

    public InventoryResponse find(long id) {
        return client.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .body(InventoryResponse.class);
    }

    public record InventoryResponse(long id, int quantity) {}
}
~~~

Hostname và endpoint trong ví dụ cần tồn tại trong network ứng dụng. Nếu tự tạo HTTP client ngoài instrumentation, propagation có thể không tự động hoạt động. Kiểm tra request gửi ra có `traceparent` hoặc header theo quy ước hệ thống.

### Async và reactive

Scope observation/tracing trong một thread không tự đảm bảo được truyền sang mọi thread khác. Khi dùng `@Async`, `CompletableFuture`, executor tùy biến hoặc Reactor, sử dụng cơ chế context propagation phù hợp với phiên bản Spring Boot/Micrometer và stack thực tế. Không mang một `Observation.Scope` đang mở qua thread khác và đóng ở nơi không cùng execution context.

Với Reactor, công việc có thể chỉ thực thi khi subscribe; vòng đời observation phải theo terminal signal (complete/error/cancel), không kết thúc chỉ vì đã tạo `Mono`/`Flux`.

## 9. Sampling: không dùng đổi tracer để chữa chi phí

Một tracer phù hợp vẫn cần chính sách sampling. Head sampling quyết định sớm trace nào được ghi; parent-based sampling có thể tuân theo quyết định từ upstream. Tail sampling tại Collector có thể chọn trace sau khi nhận đủ spans theo policy, ví dụ ưu tiên trace lỗi hoặc chậm.

Ví dụ lab giữ mọi trace:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Ví dụ thử nghiệm với xác suất thấp hơn:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Các tỷ lệ này chỉ minh họa. Không có một con số sampling đúng cho mọi service. Quyết định cần dựa trên lưu lượng, tỷ lệ lỗi hiếm, chi phí ingest, giá trị điều tra và khả năng xử lý của backend.

| Câu hỏi | OpenTelemetry bridge | Brave bridge |
| --- | --- | --- |
| Có sampling ở ứng dụng? | Có, qua tracing SDK/configuration phù hợp. | Có, qua cấu hình sampling của Brave/Micrometer integration. |
| Có tail sampling ở Collector? | Có nếu spans được đưa tới OTel Collector và cấu hình processor tương ứng. | Có thể khi spans được chuyển qua pipeline hỗ trợ; cần xác minh cách ingest. |
| Đổi bridge có tự giảm chi phí? | Không. | Không. |
| Metrics bị sampling cùng tỷ lệ? | Không mặc định. | Không mặc định. |

Metrics thường tiếp tục tổng hợp traffic độc lập với số traces được lưu. Không dùng số traces để tính request rate, error rate hay SLO. Tail sampling chỉ quyết định trên spans Collector nhận được; nếu head sampler ở ứng dụng đã bỏ trace, Collector không thể tạo lại spans chưa từng được gửi.

## 10. Exporter và backend: kiểm tra khả năng tương thích

| Backend/hạ tầng | Câu hỏi phải xác minh |
| --- | --- |
| **Jaeger** | Phiên bản triển khai có nhận OTLP trực tiếp không? Nếu không, Collector cần exporter/protocol nào? |
| **Grafana Tempo** | Endpoint OTLP nhận traces ở đâu? Resource attributes và retention ra sao? |
| **Zipkin** | Nhận Zipkin spans qua API nào? Có cần Brave reporter hay Collector chuyển đổi? |
| **APM vendor** | API key, endpoint, region, TLS, sampling và quota ingest có gì đặc thù? |
| **OpenTelemetry Collector** | Receiver, processor, exporter, queue, retry và memory limiter đã được cấu hình/giám sát chưa? |

Không dựa vào tên backend để đoán endpoint. Địa chỉ, path, giao thức và auth phải lấy từ cấu hình nền tảng thực tế.

Một Collector ở giữa thường giúp tách địa chỉ backend khỏi cấu hình từng ứng dụng, tập trung authentication/TLS, routing, batching, sampling và quan sát dropped telemetry. Nhưng Collector trở thành thành phần vận hành mới: cần HA, capacity, memory, queue, retry và cảnh báo. Direct export có thể đơn giản cho hệ thống nhỏ; lựa chọn cần tính cả chi phí vận hành.

## 11. Resource metadata và semantic conventions

Khi chọn tracer, hãy xác minh **resource attributes** và **span attributes** mà backend dùng để lọc và tìm kiếm.

Một trace hữu ích thường cần:
- `service.name`: tên dịch vụ ổn định.
- Metadata môi trường/deployment như namespace hoặc environment khi cần.
- Operation/span name đủ rõ để phân tích.
- HTTP method, route template và status theo conventions phù hợp.
- Dependency/DB/messaging attributes theo instrumentation hỗ trợ.
- Error status/event khi operation thất bại.

Không gắn tên pod có vòng đời ngắn hoặc user/request IDs thành resource identity chung cho mọi span nếu sai ngữ nghĩa. Resource mô tả process/service instance; span attributes mô tả một hoạt động.

Semantic conventions và naming có thể thay đổi theo phiên bản instrumentation. Khi đổi bridge hoặc nâng cấp, hãy so sánh raw spans để phát hiện tên span đổi, service name đổi, route thành URL thô, error status/attributes bị mất hoặc mapping tags khác làm dashboard hỏng.

## 12. Liên kết metrics, logs và tracing

| Câu hỏi vận hành | Metrics | Logs | Traces |
| --- | --- | --- | --- |
| Có bao nhiêu request lỗi? | Tỉ lệ/count theo route và status. | Sự kiện lỗi cụ thể. | Một số trace lỗi được sampling/giữ. |
| P95 tăng ở đâu? | HTTP/dependency timer, histogram. | Timeout, retry, pool wait. | Waterfall và span durations. |
| Request nào bị ảnh hưởng? | Thường không có request ID riêng. | Request ID và trace ID nếu có. | Trace ID và span tree. |
| Service nào bị nghẽn? | Pool, JVM, queue, request metrics. | Log từng service. | Client/server spans xuyên dịch vụ. |

Micrometer Observation có thể tạo metrics và spans từ cùng hoạt động khi handlers phù hợp được cấu hình. Logs có thể mang trace ID/span ID qua MDC. Tuy nhiên, metric labels cần low cardinality; trace attributes vẫn phải kiểm soát privacy/chi phí; logs độc lập với tracing sampler; exporter của traces không thay metrics exporter; không phải mọi request đều có trace được lưu.

Một hệ thống chọn tracer tốt là hệ thống **giữ được khả năng điều tra end-to-end**, chứ không chỉ là hệ thống xuất được spans từ một service.

## 13. Migration giữa Brave và OpenTelemetry

Migration tracing là thay đổi giao thức/vận hành, không chỉ là thay dependency.

### Giai đoạn 1 — Kiểm kê

Ghi lại bridge/tracer đang dùng trong từng service; propagation formats (W3C, B3, baggage và header tự định nghĩa); backend, endpoint, reporter/exporter và Collector; sampling rules, resource attributes, span names, tags và log correlation; dashboard, alerts, saved queries và runbooks dựa vào fields nào.

### Giai đoạn 2 — Chọn một ranh giới

Không đổi mọi service, gateway, Collector và backend trong một lần nếu không cần. Chọn service có traffic và dependency đại diện; chạy trong môi trường được kiểm soát và ghi nhận trace trước/sau theo cùng kịch bản.

### Giai đoạn 3 — Kiểm thử propagation liên thông

Thử caller cũ → service mới; caller mới → service cũ; service mới → service mới; HTTP qua gateway và ít nhất hai service; messaging/async nếu hệ thống dùng. Xác minh trace ID, parent span ID, sampling flags và parentage. Nếu hỗ trợ W3C và B3 trong giai đoạn chuyển tiếp, cấu hình thứ tự ưu tiên và thử trường hợp hai headers có context không giống nhau.

### Giai đoạn 4 — So sánh dữ liệu

Đối chiếu tỉ lệ traces được thu nhận với sampling dự kiến; span names, attributes, resource identity và error status; latency từng dependency; logs correlation; exporter errors, Collector drops và backend ingestion; ingest volume, index size, retention và chi phí.

### Giai đoạn 5 — Rollout và rollback

Triển khai theo nhóm service hoặc vùng traffic. Giữ cấu hình/phiên bản trước trong thời gian rollback có kiểm soát. Không để hai tracing implementations cùng instrument một request tạo duplicate spans vô tình.

Nếu backend mới chưa đáp ứng, rollback cần khôi phục bridge, exporter và propagation policy đồng bộ; chỉ khôi phục dependency mà quên header strategy có thể tiếp tục làm trace bị tách.

## 14. Lỗi thường gặp khi chọn và triển khai tracer

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không có tracer bean hoặc startup lỗi | Thiếu bridge, dependency version xung đột hoặc auto-configuration không kích hoạt. | Kiểm tra dependency tree và conditions theo Spring Boot release. |
| Có hai span cho cùng thao tác | Operation bị instrument qua hai API/agent/bridge. | Chọn một nguồn instrumentation và xác định ranh giới. |
| Trace bị tách khi qua service khác | B3/W3C không tương thích, client/server thiếu instrumentation hoặc context mất. | Kiểm tra headers và propagator ở từng hop. |
| OTLP exporter không kết nối | Sai transport/port/path, DNS/network, TLS hoặc auth. | Xác minh receiver, exporter endpoint và Collector logs. |
| Collector nhận spans nhưng backend trống | Exporter backend/pipeline lỗi hoặc backend không ingest/index. | Kiểm tra Collector exporter errors và backend ingestion. |
| Service xuất hiện thành nhiều service names | Resource attributes hoặc naming không nhất quán. | Chuẩn hóa `service.name`, environment/namespace và mapping. |
| Dashboard mất dữ liệu sau migration | Span names/tags/semantic conventions thay đổi. | So sánh raw spans, cập nhật query/dashboard. |
| Traces ít hơn request metrics | Sampling hoặc lỗi export/ingest. | Xem sampling policy và pipeline; không dùng trace count làm traffic. |
| Backend quá tải sau đổi bridge | Sampling tăng, attributes nhiều, batching/limits chưa phù hợp. | Đo ingest, giảm cardinality, điều chỉnh sampling và Collector capacity. |
| Logs thiếu trace ID | MDC/correlation hoặc async propagation chưa đúng. | Kiểm tra log pattern, context và executor/reactive setup. |
| Async span không có parent | Observation đóng trước async work hoặc context không truyền. | Quản lý lifecycle theo completion và propagation đúng execution context. |

## 15. Runbook đánh giá tracer cho hệ thống đang chạy

1. **Xác định mục tiêu điều tra:** lỗi hiếm, độ trễ dependency, fan-out hay correlation đa ngôn ngữ? Ghi rõ trace cần trả lời câu hỏi nào.
2. **Lập bản đồ hệ thống:** service, framework, HTTP client, messaging, database, gateway, agent và backend hiện tại.
3. **Kiểm tra propagation:** W3C/B3 và baggage đang dùng ở ranh giới nào? Có context bị mất qua async không?
4. **So sánh backend/ingest:** OTLP trực tiếp, Collector, Zipkin API hay agent? Tính khả năng tương thích và vận hành.
5. **Chọn candidate bridge:** OpenTelemetry hoặc Brave theo điều kiện hiện có và mục tiêu dài hạn.
6. **Dựng luồng thử nghiệm:** một request HTTP qua ít nhất hai service, có custom observation và dependency span.
7. **Xác nhận end-to-end:** trace ID, parent–child, resource metadata, errors, logs correlation và backend search.
8. **Đo chi phí:** sampling rate, exported spans, dropped spans, storage/index và tải Collector.
9. **Thử lỗi có kiểm soát:** downstream chậm, trả lỗi, timeout, async hoặc message nếu có.
10. **Ra quyết định rollout:** chọn implementation, propagation policy, sampling, ownership và kế hoạch rollback; ghi lại bằng chứng.

Một tracer không nên được chọn chỉ vì demo local hiển thị được waterfall. Nó phải giữ được context qua đúng các đường giao tiếp mà hệ thống dùng, với metadata có ích và chi phí chấp nhận được.

## 16. Bài tập tự kiểm tra

### Bài 1 — Chọn bridge

Một hệ thống mới gồm Java/Spring Boot, Node.js và Go; nền tảng observability đã nhận OTLP qua Collector. Hướng nào nên được đánh giá đầu tiên?

**Đáp án:** OpenTelemetry bridge là ứng viên tự nhiên để chuẩn hóa qua OTLP và hệ sinh thái đa ngôn ngữ. Tuy nhiên vẫn phải kiểm tra instrumentation của từng service, propagation, resource attributes, sampling và backend.

### Bài 2 — Giữ Brave hay đổi?

Một hệ thống Java hiện tại dùng Brave/Zipkin, B3 propagation và dashboard ổn định. Không có yêu cầu mới về đa ngôn ngữ hoặc OTLP. Có bắt buộc đổi sang OpenTelemetry bridge không?

**Đáp án:** Không. Có thể tiếp tục dùng Brave nếu stack còn được hỗ trợ, vận hành đáp ứng nhu cầu và rủi ro/chi phí được chấp nhận. Nên lập kế hoạch migration khi có lợi ích cụ thể, không đổi chỉ vì xu hướng.

### Bài 3 — OTLP thành công nhưng trace bị tách

Collector nhận spans từ cả order-api và inventory-api, nhưng chúng có trace IDs khác nhau. Cần sửa exporter hay propagation?

**Đáp án:** Ưu tiên kiểm tra propagation: `traceparent`/B3 có được inject và extract không, HTTP client/server có được instrument không, async context có bị mất không. Exporter vận chuyển spans đã tạo; nó không tự ghép hai traces bằng tên service.

### Bài 4 — Chọn sampling

Một API có 20.000 request/giây và backend ingest vượt ngân sách. Có nên đổi từ OpenTelemetry sang Brave để giảm traces không?

**Đáp án:** Không có cơ sở. Chi phí cần giải quyết qua sampling policy, attributes/cardinality, exporter batching, Collector capacity và retention. Đổi implementation không tự giảm sampling hoặc lượng dữ liệu.

### Bài 5 — Hai bridge trong một ứng dụng

Một ứng dụng thêm cả `micrometer-tracing-bridge-otel` và `micrometer-tracing-bridge-brave` vì muốn gửi cùng span tới hai backend. Đây có phải thiết kế mặc định nên dùng không?

**Đáp án:** Không. Hai bridge có thể tạo auto-configuration cạnh tranh hoặc pipeline trùng tùy version/config. Nếu cần xuất tới hai nơi, đánh giá exporter/Collector fan-out từ một tracing implementation. Kiểm tra không có duplicate spans và context bị tách.

### Bài 6 — Metrics nhiều hơn traces

Dashboard metrics cho thấy 5.000 request, backend lưu 500 trace. Có thể kết luận 4.500 request không được instrument không?

**Đáp án:** Không. Tracing sampling có thể giữ 10%, trong khi metrics tổng hợp hầu hết request. Kiểm tra sampling và export pipeline; dùng metrics cho traffic/error rate, traces cho mẫu điều tra.

## 17. Checklist chọn và vận hành tracer

- [ ] Đã xác định backend, giao thức ingest và pipeline exporter/Collector hiện có.
- [ ] Chọn một tracing bridge phù hợp, tránh cấu hình nhiều implementation cạnh tranh.
- [ ] Dependency versions được quản lý tương thích với Spring Boot/Micrometer.
- [ ] Resource attributes, đặc biệt `service.name`, nhất quán giữa các service.
- [ ] W3C/B3 propagation được thống nhất và kiểm tra ở gateway, HTTP client/server và messaging.
- [ ] Context propagation qua `@Async`, executor, `CompletableFuture` và Reactor được kiểm chứng.
- [ ] Sampling phù hợp traffic, SLO, tỷ lệ lỗi hiếm và ngân sách backend.
- [ ] OTLP/Zipkin reporter dùng đúng transport, endpoint, TLS/auth và network boundary.
- [ ] Collector/agent có giám sát queue, exporter failures, dropped spans và resource usage.
- [ ] Span names/attributes có ngữ nghĩa, cardinality và privacy được kiểm soát.
- [ ] Logs tương quan được bằng trace ID khi context hiện hành có sẵn.
- [ ] Metrics vẫn là nguồn cho traffic, error rate và latency tổng hợp; không suy SLO từ trace count.
- [ ] Dashboard/alerts được kiểm thử sau thay đổi names, attributes hoặc semantic conventions.
- [ ] Migration có kế hoạch canary, so sánh dữ liệu và rollback propagation/bridge đồng bộ.

**Ghi nhớ:** Chọn tracer theo **backend, propagation, instrumentation, sampling và khả năng vận hành của toàn hệ thống**. Với Spring Boot, Micrometer Tracing giúp ứng dụng giữ abstraction; OpenTelemetry bridge phù hợp khi chuẩn hóa theo OTel/OTLP và đa ngôn ngữ, còn Brave bridge có thể tiếp tục phù hợp với hệ thống Zipkin/B3 đang vận hành tốt. Điều quyết định là trace phải được nối xuyên các dịch vụ, xuất đến đúng nơi, mang metadata có ích và phối hợp được với metrics/logs để điều tra sự cố bằng bằng chứng.
