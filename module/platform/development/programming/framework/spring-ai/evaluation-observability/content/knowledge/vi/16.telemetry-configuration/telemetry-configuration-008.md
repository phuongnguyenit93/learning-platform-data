# Phân biệt telemetry chưa được tạo với telemetry chưa được chuyển đi

## 1. Đặt đúng câu hỏi khi dashboard không có dữ liệu

Khi một dashboard trống hoặc không tìm thấy trace của request vừa chạy, có ít nhất hai nhóm nguyên nhân khác nhau:

- **Telemetry chưa được tạo:** operation chưa chạy, component chưa được instrument, Observation không được phát sinh, handler không ghi meter/span, hoặc dữ liệu bị sampling/filter loại ngay tại nguồn.
- **Telemetry đã được tạo nhưng chưa được chuyển đi hoặc chưa truy vấn được:** meter/span tồn tại trong ứng dụng nhưng endpoint scrape/export, network, authentication, Collector, backend, retention hoặc query có vấn đề.

Không thể chẩn đoán hai nhóm này bằng cách chỉ mở Grafana. Cần kiểm tra theo chuỗi từ operation trong ứng dụng đến nơi lưu dữ liệu.

Trong module SPRING_AI_EVALUATION_OBSERVABILITY, việc phân biệt này giúp nhóm xác định đúng nguyên nhân khi chất lượng RAG, tool calling, factual correctness, latency hoặc chi phí thay đổi giữa các phiên bản prompt/model/pipeline.

Một quy trình chẩn đoán hữu ích là:

1. Xác nhận operation có thực sự chạy.
2. Xác nhận instrumentation tạo Observation.
3. Xác nhận Observation được handler chuyển thành meter/span.
4. Xác nhận meter/span còn tồn tại sau sampling/filter.
5. Xác nhận ứng dụng expose hoặc export được dữ liệu.
6. Xác nhận Prometheus/Collector nhận được dữ liệu.
7. Xác nhận backend lưu dữ liệu và query đúng.

Mỗi bước có bằng chứng riêng. Nếu bỏ qua các bước giữa, nhóm dễ sửa sai tầng: ví dụ tăng sampling khi vấn đề thật là request chưa đi qua VectorStore, hoặc sửa Collector trong khi ứng dụng chưa hề tạo span.

## 2. Chuỗi tạo và chuyển telemetry

~~~mermaid
flowchart TD
    A["Business operation chạy"] --> B["Instrumentation / Observation"]
    B --> C{"Observation có được phát sinh?"}
    C -->|Không| N1["Chưa tạo: kiểm tra code path, instrument và registry"]
    C -->|Có| D{"Có handler phù hợp?"}
    D -->|Không| N2["Observation có nhưng chưa có meter/span"]
    D -->|Có| E["Meter và/hoặc span được ghi"]
    E --> F{"Có sampling hoặc filter?"}
    F -->|Bị loại| N3["Đã quan sát nhưng bị sampling/filter loại"]
    F -->|Được giữ| G{"Signal path"}
    G --> H["Metrics: MeterRegistry / Actuator"]
    G --> I["Traces: Span processor / exporter"]
    H --> J["Prometheus scrape"]
    I --> K["OTLP / Collector"]
    J --> L["Metrics backend"]
    K --> M["Trace backend"]
    L --> Q["Dashboard / query"]
    M --> Q
    N1 --> Z["Bằng chứng và bước kiểm tra tiếp"]
    N2 --> Z
    N3 --> Z
~~~

| Giai đoạn | Metrics | Traces |
|---|---|---|
| Operation | HTTP request, model call, vector query, tool execution | Cùng operation đó |
| Instrumentation | Micrometer meter/Observation | Observation/Tracing bridge |
| Ghi nhận | MeterRegistry nhận Counter/Timer/Gauge | Tracer tạo Span |
| Loại bỏ tại nguồn | MeterFilter/Observation predicate hoặc không đăng ký meter | Sampler, span processor/filter |
| Rời ứng dụng | Expose qua Actuator để scrape; hoặc exporter nếu dùng push metrics | Span processor/exporter gửi OTLP/Zipkin |
| Receiver | Prometheus scrape target hoặc metrics receiver | Collector OTLP receiver |
| Lưu trữ | Prometheus/metrics backend | Tempo/Jaeger/trace backend |
| Truy vấn | PromQL, Grafana | TraceQL/search, Jaeger query, Grafana |

**Metrics và traces có đường đi khác nhau.** Với Prometheus, ứng dụng thường expose metrics và Prometheus chủ động scrape. Với OTLP tracing, ứng dụng thường export spans đến Collector. Vì vậy, việc Collector không nhận spans không nói gì về việc Prometheus scrape metrics; ngược lại, up=1 không chứng minh trace exporter đang hoạt động.

## 3. Phân biệt ba trạng thái: chưa tạo, đã tạo nhưng bị loại, và chưa chuyển đi

Không phải mọi trường hợp không thấy dữ liệu đều thuộc đúng hai nhóm đầu bài. Có một trạng thái trung gian quan trọng: telemetry đã được tạo nhưng bị sampling hoặc filter loại trước khi gửi.

| Trạng thái | Dấu hiệu | Ví dụ |
|---|---|---|
| Chưa tạo | Không có Observation/meter/span tại nguồn | Request không gọi ChatModel; client bypass instrumented ChatClient |
| Có Observation nhưng không ghi tín hiệu | Observation chạy nhưng thiếu meter/tracing handler | Registry chỉ có một loại handler hoặc wiring sai |
| Đã tạo rồi bị loại | Có operation nhưng sampler/filter quyết định drop | Head sampler loại trace; MeterFilter deny meter |
| Đã tạo và đang giữ ở ứng dụng | Actuator có meter hoặc exporter có queue | Prometheus chưa scrape; exporter chưa gửi thành công |
| Đã rời ứng dụng nhưng receiver không nhận | Lỗi network/auth/protocol/endpoint | OTLP 401, TLS failure, connection refused |
| Receiver nhận nhưng không lưu | Collector pipeline/exporter/backend lỗi | Receiver accepted spans nhưng exporter send failed |
| Đã lưu nhưng không tìm thấy | Query sai, time range, tenant, retention | Trace có trong backend nhưng Grafana dùng sai datasource |

Khi báo cáo, hãy mô tả trạng thái bằng bằng chứng. Câu “không có trace” chỉ là triệu chứng; “app không tạo span”, “head sampler drop”, “Collector không nhận” và “backend query không tìm thấy” là các chẩn đoán khác nhau.

## 4. Bằng chứng đầu tiên: operation có thực sự chạy không?

Trước khi kiểm tra telemetry pipeline, hãy xác nhận operation nghiệp vụ đã xảy ra.

Ví dụ một request Spring AI:

~~~text
POST /api/answers
  -> ChatClient.call()
  -> QuestionAnswerAdvisor
  -> VectorStore.query()
  -> ChatModel.call()
  -> Tool execution (chỉ khi model yêu cầu)
  -> HTTP response
~~~

Luồng thực tế có thể khác. Một endpoint có thể dùng ChatModel trực tiếp, không gọi ChatClient; có thể không bật RAG; model có thể trả lời mà không gọi tool; hoặc retry/advisor có thể làm model được gọi nhiều lần.

Hãy ghi expected path trước khi chạy:

| Operation | Bằng chứng nghiệp vụ |
|---|---|
| HTTP endpoint | HTTP status, access log đã lọc, request counter |
| ChatClient | Call/stream hoàn tất, response hoặc test stub được xác nhận |
| ChatModel | Provider request thực sự được gửi và nhận response |
| VectorStore | Query thực sự chạy, có fixture/source IDs |
| Tool | Tool event được ghi bởi fixture hoặc mock service |
| Evaluation | Runner lưu result theo run/case/attempt |

Nếu tool không chạy vì model không yêu cầu, thiếu tool span là đúng. Nếu request không đi qua RAG, thiếu vector-store metric là đúng. Đừng xem một component không được gọi là lỗi export.

### Tách operation nghiệp vụ khỏi việc gọi model

Một request có thể trả lời từ cache, từ rule hoặc từ dữ liệu có sẵn mà không gọi model. Khi đó HTTP metric có thể tăng nhưng GenAI model metric không tăng. Điều này phản ánh code path thực tế, không nhất thiết là instrumentation hỏng.

Tương tự, nếu unit test mock ChatModel, test có thể tạo HTTP/ChatClient observation nhưng không tạo provider call hoặc token usage thật. Ghi rõ test dùng mock hay model thật trong kết quả.

## 5. Kiểm tra instrumentation của từng component

Spring AI dùng Micrometer Observation để đo các operation ở ChatClient, ChatModel, advisor, EmbeddingModel và VectorStore. Tool execution cũng có observation khi tool được thực thi. Spring MVC/WebFlux và HTTP client có instrumentation riêng.

| Component | Câu hỏi kiểm tra | Điều kiện để có tín hiệu |
|---|---|---|
| HTTP server | Request đi qua Spring MVC/WebFlux không? | Web instrumentation và registry đang hoạt động |
| ChatClient | Code gọi builder/client có instrumentation không? | Dùng Spring-managed/instrumented client phù hợp version |
| ChatModel | Model operation thực sự được gọi không? | Client/provider path có observation support |
| Advisor | Advisor có chạy trong ChatClient chain không? | Advisor observation được hỗ trợ và bật |
| VectorStore | Query/add/delete có thực thi không? | VectorStore implementation được instrument |
| Tool | Tool có được gọi thật không? | Tool callback thực thi qua Spring AI tool mechanism |
| HTTP client | Request provider đi qua client nào? | Client/SDK có Micrometer/OTel instrumentation |

Nếu một implementation tùy chỉnh tự gọi SDK hoặc HTTP client trực tiếp, instrumentation của Spring AI có thể không bao phủ operation đó. Hãy kiểm tra đúng adapter và version; nếu cần, thêm Observation ở ranh giới business/service do ứng dụng sở hữu.

### Phiên bản là một phần của bằng chứng

Ghi lại Spring Boot, Spring AI, Micrometer, OpenTelemetry SDK/exporter, Collector và provider SDK. Với dòng ví dụ Boot 3.5 dùng Spring AI 1.1.x; dòng Boot 4.x dùng Spring AI 2.x. Luôn đối chiếu compatibility matrix của release thực tế trước khi kết luận một metric/span “phải có”.

Tên meter, span convention, property và tags có thể thay đổi theo version. Tìm đúng release docs hoặc dependency metadata đã khóa trong build của ứng dụng.

## 6. Observation có được phát sinh và có handler nhận không?

Micrometer Observation là lớp trung gian để một operation có thể được xử lý thành nhiều tín hiệu. Observation không tự động bảo đảm rằng cả meter và span đều được tạo. Kết quả phụ thuộc các handler đã đăng ký trong ObservationRegistry.

Ví dụ:

- DefaultMeterObservationHandler ghi metrics từ Observation.
- Tracing observation handlers tạo và kết thúc spans.
- Observation predicate có thể quyết định không bắt đầu một Observation.
- Observation filter có thể bổ sung hoặc chuẩn hóa context trước khi handler xử lý.

Một registry có meter handler nhưng không có tracing handler có thể tạo metrics mà không tạo spans. Một registry có tracing handler nhưng không có meter handler có thể tạo spans mà không có meter tương ứng.

### Tạo một custom Observation để kiểm tra đường instrumentation

Ví dụ minh họa một business operation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class AnswerWorkflow {

    private final ObservationRegistry observationRegistry;

    AnswerWorkflow(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    String execute() {
        Observation observation = Observation
                .createNotStarted("app.answer.workflow", observationRegistry)
                .lowCardinalityKeyValue("operation", "answer");

        observation.start();
        try (Observation.Scope scope = observation.openScope()) {
            return performAnswer();
        } catch (RuntimeException exception) {
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }

    private String performAnswer() {
        return "synthetic answer";
    }
}
~~~

Đây là ví dụ để hiểu cơ chế, không phải yêu cầu tạo custom meter trùng với meter Spring AI. Nếu meter handler được đăng ký, Observation có thể tạo Timer tương ứng; nếu tracing handler được đăng ký và sampler giữ trace, nó có thể tạo span. Dữ liệu cụ thể phụ thuộc cấu hình registry.

### Dùng custom Observation để khoanh vùng

Nếu app.answer.workflow có meter nhưng không có span, operation và meter path đã chạy; tập trung kiểm tra tracing handler, sampler và exporter. Nếu cả meter lẫn span đều vắng mặt, kiểm tra code path, registry được inject, predicate và lifecycle start/stop.

Nếu không muốn tạo custom Observation trong production chỉ để debug, dùng một test nhỏ trong profile local hoặc kiểm tra operation hiện có qua Actuator.

## 7. Registry NOOP, registry sai và handler bị thiếu

Một nguyên nhân thường gặp của “không có telemetry” là code dùng registry không hoạt động hoặc không phải registry mà Spring Boot đã cấu hình.

Kiểm tra:

- Service nhận ObservationRegistry từ Spring container hay tự tạo một registry mới?
- ObservationRegistry.NOOP có bị truyền vào client/custom component không?
- MeterRegistry được inject có phải registry mà Actuator expose không?
- Spring AI client có dùng ObservationRegistry được cấu hình bởi framework không?
- Các ObservationHandler có được đăng ký ở registry đang thực sự được dùng không?
- Có nhiều ApplicationContext hoặc nhiều MeterRegistry khiến dữ liệu nằm ở registry khác không?

Tránh tự tạo một SimpleMeterRegistry trong bean production chỉ để test rồi kỳ vọng /actuator/prometheus hiển thị meter đó. Registry được Actuator expose phải là registry được cấu hình trong application context và được nối với endpoint.

### Kiểm tra custom code

Nếu một service tự tạo client bằng constructor hoặc builder không được Spring quản lý, client có thể không nhận cùng ObservationRegistry/configuration với client do auto-configuration tạo ra. So sánh bean thực tế và cách khởi tạo; xác nhận client sử dụng trong request là client đã được instrument.

## 8. Telemetry bị loại tại nguồn: predicate, filter và sampling

Ngay cả khi operation chạy và Observation được tạo, meter/span có thể không được ghi hoặc không được giữ.

| Cơ chế | Áp dụng | Hệ quả |
|---|---|---|
| ObservationPredicate | Observation | Có thể ngăn Observation bắt đầu |
| MeterFilter | Meter registration/ID | Có thể deny, rename hoặc giới hạn meter |
| Tracing sampler | Root/child trace | Có thể loại span/trace trước khi export |
| Span processor/filter | Span đã tạo | Có thể drop hoặc sửa attributes trước export |
| Collector filter/tail sampler | Dữ liệu đã tới Collector | Có thể loại trace sau khi nhận |
| Prometheus metric relabeling | Samples khi scrape | Có thể drop/đổi labels hoặc series |
| Log filter/level | Logs | Có thể bỏ log event dù operation vẫn chạy |

Phải xác định filter nằm ở đâu. Nếu trace bị head-sampled out trong SDK, Collector không thể khôi phục trace đó. Nếu trace tới Collector rồi bị tail sampler drop, receiver vẫn có thể ghi nhận spans đã nhận dù backend không có trace.

### Kiểm tra sampling

Trong local test, đặt sampling đủ cao (thường 100%) để xác minh đường tracing, sau đó thử tỷ lệ thấp hơn. Nếu dùng parent-based sampler, sampled flag trong traceparent từ upstream có thể chi phối quyết định của child. Một request con nhận parent không sampled có thể không xuất trace dù local probability lớn hơn 0.

Để kiểm tra root sampling, tạo request không có remote parent hoặc đặt trace context phù hợp với test. Không suy luận sampler hỏng chỉ từ một request có parent context bị loại.

### Sampling metrics và traces không giống nhau

Sampling trace không làm Prometheus counter/timer tự giảm theo cùng tỷ lệ. MeterFilter hoặc metric relabeling mới có thể ảnh hưởng series metrics. Đánh giá dataset sampling cũng là một quyết định riêng, không liên quan đến trace sampling.
## 9. Xác minh meter đã được tạo trong ứng dụng

Với Spring Boot Actuator, hai endpoint thường hữu ích:

- GET /actuator/metrics: liệt kê meter names mà registry expose.
- GET /actuator/metrics/{name}: đọc measurement và available tags của một meter.

Ví dụ:

~~~text
GET http://localhost:8080/actuator/metrics
GET http://localhost:8080/actuator/metrics/http.server.requests
GET http://localhost:8080/actuator/metrics/gen_ai.client.operation
GET http://localhost:8080/actuator/metrics/db.vector.client.operation
~~~

Tên meter ví dụ phải đối chiếu với version Spring AI/Micrometer thực tế. Nếu /actuator/metrics không liệt kê meter, kiểm tra instrumentation/registry/filter trước khi xem Prometheus.

Nếu meter có trong /actuator/metrics/{name} nhưng không có ở /actuator/prometheus, kiểm tra Prometheus registry dependency, exporter endpoint, meter naming/filters và cấu hình exposure.

Endpoint Actuator có thể bị bảo vệ bởi Spring Security. Hãy dùng credential có quyền phù hợp; 401/403 là lỗi truy cập endpoint, không phải bằng chứng meter chưa được tạo.

## 10. Xác minh metrics đã được expose hay chưa

Prometheus thường dùng pull model: ứng dụng expose exposition endpoint, Prometheus scrape theo scrape_interval.

Ví dụ cấu hình local cho Spring Boot 3.5:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: spring-ai-quality-service
      environment: local
~~~

Cần dependency runtime micrometer-registry-prometheus tương thích với BOM. Chỉ expose endpoint chưa bảo đảm Prometheus đã scrape; đây là hai bước riêng.

### So sánh ba endpoint

| Endpoint | Câu hỏi trả lời |
|---|---|
| /actuator/metrics | Registry có meter name nào? |
| /actuator/metrics/{name} | Meter cụ thể có measurement/tag nào? |
| /actuator/prometheus | Registry có render series theo Prometheus exposition không? |

Ví dụ kiểm tra:

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/gen_ai.client.operation
curl -s http://localhost:8080/actuator/prometheus | grep -E 'gen_ai|http_server|db_vector'
~~~

Nếu metrics endpoint có meter nhưng Prometheus exposition không có, kiểm tra registry/exporter và meter filter. Nếu exposition có series nhưng Prometheus không có, chuyển sang kiểm tra scrape target.

## 11. Phân biệt metrics chưa tạo với metrics chưa được scrape

| Quan sát | Kết luận có thể rút ra | Bước tiếp theo |
|---|---|---|
| Meter không có ở Actuator metrics | Chưa có meter trong registry được expose | Kiểm tra operation, instrumentation, registry, handler, filter |
| Meter có ở Actuator metrics, không có ở Prometheus exposition | Meter có trong registry nhưng chưa render/đăng ký đúng registry hoặc bị filter | Kiểm tra Prometheus registry, naming và filter |
| Series có ở /actuator/prometheus, up=0 | Ứng dụng expose series nhưng Prometheus scrape thất bại | Kiểm tra DNS, port, path, TLS, auth, network |
| Series có ở exposition, up=1, không có series trong query | Có thể scrape relabel/drop, sai job/labels/time range hoặc query | Kiểm tra target, metric relabeling, raw series và thời gian |
| Series có trong Prometheus nhưng dashboard trống | Query/dashboard/variable/tenant/time range sai | Chạy PromQL trực tiếp |

up=1 chỉ nói rằng Prometheus scrape target thành công. Nó không chứng minh mọi meter mong đợi đã được tạo. Tương tự, up=0 cho biết scrape không thành công; không kết luận app không tạo metric.

### Kiểm tra target và scrape samples

PromQL:

~~~promql
up{job="spring-ai"}
~~~

~~~promql
scrape_samples_scraped{job="spring-ai"}
~~~

~~~promql
scrape_samples_post_metric_relabeling{job="spring-ai"}
~~~

Nếu số samples sau metric relabeling thấp hơn đáng kể số samples scrape, xem các rule relabeling có drop series hay không. Metric nội bộ và tên series có thể thay đổi theo phiên bản Prometheus; xác nhận với phiên bản đang chạy.

## 12. Phân biệt trace chưa tạo với trace chưa export

Với tracing, phải kiểm tra nhiều điểm hơn vì span có thể bị loại trước khi rời ứng dụng.

| Bằng chứng | Diễn giải |
|---|---|
| Không có Observation cho operation | Instrumentation/code path chưa phát sinh observation |
| Observation có nhưng không có meter/span | Handler hoặc registry wiring chưa đầy đủ |
| Meter có nhưng không có span | Metrics handler hoạt động; tracing handler/sampler/config cần kiểm tra |
| Span được tạo nhưng sampled out | Quyết định sampler không giữ trace |
| App exporter báo send failure | Span có thể đã được tạo nhưng không chuyển thành công |
| Collector accepted spans tăng | Collector đã nhận dữ liệu; chưa chứng minh backend lưu thành công |
| Collector exporter send failed tăng | Receiver nhận được nhưng downstream exporter gặp lỗi |
| Backend có trace nhưng query không thấy | Query, tenant, time range hoặc retention có vấn đề |

Nếu SDK có diagnostic logging, exporter metrics hoặc in-memory test exporter, dùng chúng để xác định span có được tạo và exporter có cố gửi hay không. Không bật log payload/secret trong production chỉ để chẩn đoán.

## 13. Kiểm tra tracing sampler và parent context

Ví dụ cấu hình local Spring Boot 3.5:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Đây là cấu hình kiểm thử local. Xác suất 1.0 chỉ giúp sampler không loại trace ở bước head sampling theo tỷ lệ; exporter vẫn có thể thất bại, Collector vẫn có thể drop, và backend vẫn có thể không lưu.

Khi chẩn đoán, kiểm tra:

- Có remote parent không?
- traceparent có sampled flag 01 hay 00?
- Sampler là parent-based, ratio hay always-on/off?
- Có SDK-level sampler khác ghi đè cấu hình không?
- Trace có bị drop ở span processor hoặc Collector filter không?

Đừng nhầm việc span không được export với việc span không bao giờ được tạo. Với head sampler, quyết định thường xảy ra trước khi trace được giữ để export; với tail sampler, dữ liệu đã tới Collector rồi mới được quyết định giữ/drop.

## 14. Xác minh OTLP exporter có thực sự gửi đi

Khi app có span được giữ, exporter phải gửi đúng protocol, host, port và path.

| Protocol | Port thường gặp | Endpoint traces |
|---|---:|---|
| OTLP/HTTP | 4318 | http://collector:4318/v1/traces |
| OTLP/gRPC | 4317 | collector:4317 qua gRPC exporter |

Không dùng HTTP path /v1/traces cho gRPC channel. Không nối path hai lần nếu framework tự thêm signal path vào common endpoint. Endpoint thực tế phụ thuộc property và SDK version.

Với Spring Boot 3.5, ví dụ:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
      transport: http
      timeout: 10s
~~~

Kiểm tra:

- DNS hostname resolve được từ container/network namespace của ứng dụng.
- Port đang listen và receiver đúng protocol đã bật.
- Path signal đúng.
- Timeout hữu hạn.
- TLS trust, hostname và mTLS đúng nếu dùng HTTPS.
- Bearer token/header hợp lệ nếu receiver yêu cầu.
- Exporter không bị disable hoặc thay thế bởi cấu hình khác.

HTTP 401/403 là vấn đề auth/authorization. 404 thường gợi ý path hoặc receiver route. 415/400 có thể là protocol/content type/payload mismatch. Connection refused hoặc timeout thường liên quan listener, DNS, network hoặc backend quá tải.

## 15. Kiểm tra Collector: nhận được chưa và chuyển tiếp được chưa?

Collector chia thành receiver, processor và exporter. Phải kiểm tra cả ba.

| Collector stage | Bằng chứng | Cách diễn giải |
|---|---|---|
| Receiver | Accepted spans/metrics/logs | Dữ liệu đã tới receiver |
| Receiver | Refused spans hoặc auth failures | Receiver từ chối hoặc không xử lý được |
| Processor | Pipeline được cấu hình và không có lỗi/drop bất thường | Dữ liệu đi qua processor |
| Exporter | Sent spans | Exporter chuyển tiếp thành công theo metric nội bộ |
| Exporter | Send failures/retries | Downstream backend/network/auth lỗi |
| Queue | Queue size/capacity | Phát hiện backpressure và nguy cơ drop |

Một số tên metric nội bộ thường gặp ở Collector gồm otelcol_receiver_accepted_spans, otelcol_receiver_refused_spans, otelcol_exporter_sent_spans, otelcol_exporter_send_failed_spans và các queue metrics. Tên, labels và trạng thái deprecated phụ thuộc Collector version/distribution; xác minh qua telemetry endpoint của binary đang chạy.

### Ví dụ cấu hình pipeline traces

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  batch: {}

exporters:
  otlp_http/backend:
    endpoint: https://trace-backend.internal

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp_http/backend]
~~~

Đây là skeleton minh họa. Backend có thể yêu cầu path, auth, TLS, tenant header hoặc exporter type riêng. Receiver chỉ listen trên interface phù hợp network topology; không mở receiver không xác thực ra public network.

### Accepted không đồng nghĩa stored

Nếu otelcol_receiver_accepted_spans tăng nhưng backend không có trace, kiểm tra exporter pipeline, backend endpoint, auth, queue, retry và storage. Nếu otelcol_exporter_send_failed_spans tăng, dữ liệu đã tới Collector nhưng downstream export đang thất bại.

Nếu receiver accepted không tăng, quay lại app exporter: sampler, endpoint, protocol, network, TLS và auth.

## 16. Backend đã lưu nhưng truy vấn không thấy

Khi exporter gửi thành công, vẫn còn các nguyên nhân khiến trace/metric không xuất hiện trong giao diện:

- Query sai datasource hoặc sai endpoint query.
- Sai tenant/project/namespace.
- Sai service name hoặc resource attributes.
- Chọn khoảng thời gian không chứa request.
- Clock của app/Collector/backend lệch.
- Retention đã xóa dữ liệu.
- Dashboard variable hoặc filter loại hết series.
- Backend indexing/compaction chưa hoàn tất.
- Người dùng không có quyền đọc trace/metric.

Đối với trace, tìm theo trace ID trước; nếu không có, tìm theo service và khoảng thời gian chính xác. Với metrics, chạy PromQL trực tiếp trước khi mở dashboard. Đừng dùng Grafana dashboard như công cụ duy nhất để xác định telemetry có tồn tại hay không.
## 17. Phân biệt metric chưa ghi với metric chưa export khi dùng OTLP metrics

Một số hệ thống dùng OTLP metrics push thay vì Prometheus scrape. Khi đó cần kiểm tra MeterRegistry/OTLP registry, export schedule, endpoint và Collector metrics receiver. Quy trình gần giống tracing nhưng signal type là metrics:

1. Xác nhận meter được tạo trong registry.
2. Xác nhận registry có OTLP exporter/reader phù hợp.
3. Xác nhận export interval đã đến.
4. Kiểm tra exporter errors/queue.
5. Kiểm tra Collector metrics receiver accepted/refused.
6. Kiểm tra metrics pipeline/exporter và backend.
7. Query đúng metric name/resource attributes.

Không áp dụng giả định Prometheus scrape cho OTLP push. Một ứng dụng có thể đồng thời expose Prometheus endpoint và push OTLP metrics; đây là hai pipeline độc lập, cần kiểm tra từng pipeline.

## 18. Logs: phân biệt không phát sinh với không thu thập

Logs cũng có hai điểm khác nhau:

- Log event không được phát sinh vì code path không ghi log, log level cao hơn event hoặc logger bị tắt.
- Log event được ghi ở process stdout/file nhưng agent/collector không đọc, parse, enrich hoặc export.

Kiểm tra theo thứ tự:

1. Có log event tại process console/file không?
2. Logger level và appender có cho phép event không?
3. Container runtime có giữ stdout/stderr không?
4. Agent/Collector có đọc đúng file/stream và parser không?
5. Exporter có gửi đến log backend không?
6. Backend query đúng service, labels, tenant và time range không?

Không dùng raw prompt, completion, tool arguments hoặc secret để chứng minh logging hoạt động. Log một event tổng hợp với correlation ID không nhạy cảm và trạng thái operation.

## 19. Bảng chẩn đoán nhanh theo bằng chứng

| Bằng chứng đầu tiên bị thiếu | Nhóm nguyên nhân ưu tiên | Kiểm tra tiếp |
|---|---|---|
| Business event/request | Request không tới app hoặc code path khác | Client, ingress, routing, app logs |
| Observation | Instrumentation không chạy, predicate skip, registry sai | Client wiring, ObservationRegistry, version |
| Meter tại Actuator | Meter handler/registry/filter | /actuator/metrics, MeterFilter, context |
| Span tại SDK/test exporter | Tracing handler/sampler/SDK | Observation handlers, parent context, sampler |
| Series tại Prometheus exposition | Prometheus registry/Actuator | Dependency, endpoint, exposure |
| Series trong Prometheus | Scrape config/network/relabel | up, targets, samples, relabeling |
| Span tại Collector receiver | App exporter/network/auth | OTLP endpoint, protocol, TLS, token |
| Span ở trace backend | Collector pipeline/exporter/backend | Accepted/sent/failed, queue, auth |
| Dữ liệu trong backend query | Query/dashboard/time range/tenant/RBAC | Raw query, datasource, retention |

## 20. Ví dụ điều tra 1: HTTP metric có nhưng ChatModel metric không có

Giả sử http_server_requests_seconds_count tăng sau request nhưng không thấy gen_ai_client_operation_seconds_count.

Điều này chứng minh HTTP request đã được instrument và ghi meter. Nó chưa chứng minh ChatModel được gọi.

Kiểm tra theo thứ tự:

1. Endpoint có trả từ cache/rule hoặc short-circuit trước ChatModel không?
2. Code có gọi ChatClient/ChatModel thật hay chỉ dùng mock?
3. Có exception xảy ra trước khi model call bắt đầu không?
4. Client/provider path đang dùng có instrumentation support không?
5. Có custom ObservationPredicate hoặc MeterFilter loại meter không?
6. Actuator đang expose đúng MeterRegistry không?

Nếu model call chưa xảy ra, đây là vấn đề code path. Nếu model call xảy ra nhưng meter không có ở Actuator, xem instrumentation/handler/registry. Nếu meter có ở Actuator nhưng không có ở Prometheus, xem scrape/export.

## 21. Ví dụ điều tra 2: metrics có nhưng trace không có

Giả sử ChatClient và ChatModel metrics tăng, nhưng trace backend không tìm thấy request.

Có thể rút ra rằng metrics path có ít nhất một handler đang hoạt động. Tracing path cần được kiểm tra riêng:

1. Có tracing bridge/SDK và tracing handler phù hợp không?
2. ObservationRegistry đang dùng có tracing handler không?
3. Sampler có giữ root/child trace không?
4. Remote parent trong traceparent có sampled flag 00 không?
5. Span processor/exporter có được cấu hình không?
6. App exporter có gửi đúng OTLP endpoint/protocol/path không?
7. Collector receiver có accepted spans không?
8. Collector exporter có sent spans hay send failures?
9. Backend có lưu trace nhưng query sai tenant/time range không?

Không tăng sampling khi chưa biết trace bị drop ở đâu. Nếu exporter endpoint sai, tăng sampling chỉ làm nhiều span thất bại hơn.

## 22. Ví dụ điều tra 3: Collector nhận span nhưng Tempo không thấy

Giả sử Collector receiver accepted spans tăng, nhưng query Tempo không tìm thấy trace.

Đã có bằng chứng span rời ứng dụng và tới Collector. Chuyển sang kiểm tra:

- Traces pipeline có exporter đến Tempo hay không?
- Exporter endpoint là ingest endpoint đúng chưa?
- Có auth token/tenant header/TLS phù hợp không?
- otelcol_exporter_send_failed_spans có tăng không?
- Queue có đầy hoặc retry quá lâu không?
- Tempo receiver/ingester có nhận dữ liệu không?
- Query datasource có trỏ đến Tempo query API không?
- Trace ID, service name, time range và tenant có chính xác không?

Nếu exporter send failures tăng, tập trung vào Collector → backend. Nếu sent spans tăng nhưng query không thấy, kiểm tra backend ingestion, tenant và truy vấn. sent_spans là bằng chứng exporter đã gửi thành công theo định nghĩa của exporter; nó không thay thế kiểm tra dữ liệu đã được index và truy vấn ở backend.

## 23. Thiết kế smoke test để phân biệt hai nhóm lỗi

Một smoke test nên thu thập bằng chứng ở nhiều tầng cho cùng một request:

| Mốc | Dữ liệu cần lưu |
|---|---|
| Trước request | Meter baseline, app version, sampling config |
| Request | HTTP status, test trace ID, fixture/case ID |
| Sau request | Meter delta, Actuator metric snapshot |
| Prometheus | Target up, raw series, scrape timestamp |
| Collector | Accepted/refused/sent/failed counters và queue |
| Trace backend | Trace lookup result và span count |
| Evaluation | Quality score, tool events, dataset/rubric version |

### Pseudocode

~~~java
// Pseudocode: thay helper bằng client/test harness của dự án.
long modelBefore = actuatorCounter("gen_ai.client.operation");
long vectorBefore = actuatorCounter("db.vector.client.operation");

String traceId = "4bf92f3577b34da6a3ce929d0e0e4736";
Response response = sendSyntheticRequest(traceId);

assertThat(response.status()).isEqualTo(200);

long modelAfter = actuatorCounter("gen_ai.client.operation");
long vectorAfter = actuatorCounter("db.vector.client.operation");

assertThat(modelAfter).isGreaterThan(modelBefore);
assertThat(vectorAfter).isGreaterThan(vectorBefore); // chỉ khi request có RAG

boolean traceFound = traceBackendContains(traceId);
boolean metricsScraped = prometheusHasExpectedSeries();

recordDiagnosticResult(
    traceId,
    modelAfter - modelBefore,
    vectorAfter - vectorBefore,
    traceFound,
    metricsScraped
);
~~~

Đây là pseudocode, không phải test class biên dịch nguyên trạng. Nếu request không có RAG, bỏ assertion VectorStore. Nếu provider không trả usage metadata, không bắt buộc token metric tăng. Đợi scrape interval và export schedule trước khi kiểm tra backend.

### Bốn kết quả chẩn đoán mẫu

| Actuator meter | Prometheus | Collector/backend trace | Chẩn đoán ưu tiên |
|---|---|---|---|
| Không có | Không có | Không có | Operation/instrumentation/registry chưa tạo |
| Có | Không có | Không có | Metrics scrape/export lỗi; tracing cần chẩn đoán riêng |
| Có | Có | Không có | Metrics path tốt; tracing path chưa tạo, bị sampling hoặc export lỗi |
| Có | Có | Có ở Collector nhưng không ở backend | Collector downstream/backend/query lỗi |

Bảng này là điểm khởi đầu. Hãy bổ sung bằng chứng trung gian như span processor diagnostics, exporter failures và backend query để thu hẹp chính xác hơn.

## 24. Những sai lầm thường gặp khi chẩn đoán

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| Grafana trống nghĩa là app không tạo telemetry | Dashboard là cuối pipeline | Kiểm tra Actuator, exporter, receiver và backend |
| up=1 nghĩa là mọi metric đã tạo | up chỉ phản ánh scrape target | Kiểm tra series cụ thể và meter registry |
| Không có trace nghĩa là chưa tạo span | Có thể bị sampling/filter hoặc export fail | Kiểm tra sampler, SDK diagnostics và Collector |
| Collector accepted nghĩa là backend lưu thành công | Accepted chỉ chứng minh receiver nhận | Kiểm tra exporter sent/failed và query backend |
| Tăng sampling sẽ sửa mọi lỗi trace | Sampling không sửa endpoint/auth/SDK | Xác định điểm drop trước |
| Không có vector span nghĩa là instrumentation hỏng | Request có thể không chạy RAG | Xác nhận expected path |
| Không có tool span nghĩa là tool integration lỗi | Model có thể không gọi tool | Xác minh tool event |
| Token metric thiếu nghĩa là model call không chạy | Provider có thể không trả usage | Kiểm tra response metadata |
| HTTP 401/403 nghĩa là telemetry chưa tạo | Đây là lỗi truy cập receiver/endpoint | Kiểm tra identity/authorization |
| Thấy meter ở một registry nghĩa là Actuator cũng thấy | Có thể là registry khác | Xác nhận đúng application context/registry |

## 25. Bài thực hành: phân loại telemetry bị thiếu

Chuẩn bị một dịch vụ Spring AI dùng dữ liệu tổng hợp:

- Endpoint POST /api/answers.
- ChatClient và ChatModel có instrumentation.
- RAG dùng VectorStore fixture.
- Tool đọc trạng thái giả, chỉ được gọi khi model yêu cầu.
- Actuator expose metrics; Prometheus scrape.
- OTLP exporter gửi traces đến Collector, Collector export đến Tempo.

Thực hiện các tình huống:

1. Gửi request baseline và xác nhận HTTP, ChatClient, ChatModel meter.
2. Gửi request có RAG; xác nhận VectorStore operation và span.
3. Gửi request buộc gọi tool fixture; xác nhận tool event/span.
4. Bỏ qua ChatModel bằng cache/rule; xác nhận HTTP meter có thể tăng mà model meter không tăng.
5. Dùng mock ChatModel; ghi rõ các tín hiệu provider/usage không xuất hiện.
6. Tạm thời loại Observation bằng predicate trong test; xác nhận operation vẫn chạy nhưng meter/span tương ứng không được tạo.
7. Dùng MeterFilter deny một meter trong profile test; quan sát khác biệt giữa observation và meter registry.
8. Đặt trace sampling về 0 trong test; xác nhận metrics vẫn tăng nhưng trace không được export.
9. Đặt sai OTLP endpoint; xác nhận span có thể được tạo nhưng exporter không gửi thành công.
10. Dừng Collector; quan sát export retry/failure và queue.
11. Để Collector nhận span nhưng làm sai downstream exporter; xác nhận accepted tăng và backend không có trace.
12. Sửa pipeline, xác nhận trace được lưu và query theo trace ID.
13. Chụp bằng chứng ở từng tầng, ghi rõ trạng thái “chưa tạo”, “bị loại” hay “chưa chuyển đi”.

### Câu hỏi tự kiểm

**Câu 1:** Actuator không có meter của ChatModel. Có nên kiểm tra Tempo trước không?

Không. Trước tiên xác nhận operation, instrumentation, registry/handler và filter tại ứng dụng.

**Câu 2:** Actuator có meter, nhưng Prometheus không có series. Meter đã được tạo chưa?

Có bằng chứng meter tồn tại trong registry được Actuator expose. Kiểm tra Prometheus registry/exposition và scrape pipeline.

**Câu 3:** Prometheus up=1 nhưng một meter mong đợi không xuất hiện. Điều đó có chứng minh meter đã tạo không?

Không. up=1 chỉ chứng minh scrape thành công; phải kiểm tra meter cụ thể ở Actuator và series cụ thể trong Prometheus.

**Câu 4:** Collector accepted spans tăng, nhưng Tempo query trống. Span có rời app không?

Có bằng chứng Collector đã nhận span. Tiếp tục kiểm tra Collector processor/exporter, backend ingest, tenant và query.

**Câu 5:** Trace không có tool span. Có kết luận tool instrumentation lỗi được không?

Chưa. Xác minh tool có thực sự được gọi qua tool event/fixture trước.

## 26. Checklist chẩn đoán trước khi thay đổi cấu hình

- [ ] Ghi rõ operation và expected path của request.
- [ ] Xác nhận HTTP/model/RAG/tool operation thực sự đã chạy.
- [ ] Ghi lại Spring Boot, Spring AI, Micrometer, OTel SDK, Collector và backend version.
- [ ] Xác nhận client dùng đúng ObservationRegistry/MeterRegistry của application context.
- [ ] Kiểm tra ObservationPredicate, ObservationHandler, MeterFilter và tracing handler.
- [ ] Kiểm tra meter cụ thể tại /actuator/metrics/{name}.
- [ ] Kiểm tra series render tại /actuator/prometheus nếu dùng Prometheus registry.
- [ ] Phân biệt Prometheus scrape với OTLP metrics push.
- [ ] Kiểm tra trace sampling, remote parent và sampled flag.
- [ ] Xác nhận exporter đúng protocol, endpoint, path, TLS và authentication.
- [ ] Kiểm tra Collector receiver accepted/refused và pipeline traces.
- [ ] Kiểm tra exporter sent/failed, retry và queue pressure.
- [ ] Query trực tiếp backend theo trace ID, service, tenant và time range.
- [ ] Phân biệt telemetry bị sampling/filter loại với telemetry export thất bại.
- [ ] Không tăng sampling hoặc expose endpoint rộng hơn trước khi xác định tầng lỗi.
- [ ] Không bật raw prompt/completion/tool payload để thay cho kiểm tra instrumentation.
- [ ] Lưu bằng chứng và kết luận theo từng tầng để lần sau tái hiện được.

### Tài liệu chính thức

- Spring AI Observability: https://docs.spring.io/spring-ai/reference/observability/
- Spring Boot 3.5 Metrics: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Spring Boot 3.5 Tracing: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- Micrometer Observation: https://docs.micrometer.io/micrometer/reference/observation.html
- OpenTelemetry Collector troubleshooting: https://opentelemetry.io/docs/collector/troubleshooting/

**Kết luận:** hãy tìm điểm cuối cùng còn bằng chứng telemetry và điểm đầu tiên bị thiếu. Nếu meter/span chưa tồn tại tại nguồn, xử lý operation, instrumentation, registry, handler hoặc filter. Nếu dữ liệu đã có tại nguồn, lần theo scrape/export, network, Collector, backend và query. Cách phân tầng này giúp xử lý đúng nguyên nhân và tránh làm tăng tải, chi phí hoặc rủi ro dữ liệu khi thay đổi sampling hay cấu hình telemetry.
