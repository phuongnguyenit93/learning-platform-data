# Observability xuyên Federation với Spring for GraphQL

Trong một hệ thống GraphQL Federation, một request từ client có thể đi qua router/supergraph, query planner và nhiều subgraph trước khi response được trả về. Nếu chỉ đo thời gian ở router hoặc chỉ xem log của một subgraph, rất khó xác định độ trễ phát sinh ở bước lập query plan, gọi mạng, resolver, DataLoader hay database.

Observability xuyên federation cần nối được các tín hiệu ở nhiều tầng: router, từng subgraph Spring for GraphQL và các dependency phía sau subgraph. Distributed tracing cho biết các bước thuộc cùng một request; metrics cho thấy xu hướng và tỷ lệ lỗi; logs cung cấp chi tiết để điều tra một trace cụ thể.

Trong bài này, ta dùng Micrometer Observation của Spring for GraphQL ở subgraph và OpenTelemetry (OTel) ở ranh giới dịch vụ. Ví dụ router dùng Apollo Router, nhưng các nguyên tắc trace context, service identity, cardinality và correlation cũng áp dụng cho gateway/router khác.

## 1. Kiến trúc quan sát của một federated graph

Giả sử một supergraph có hai subgraph:

- `catalog-subgraph` cung cấp Product và thông tin sản phẩm.
- `review-subgraph` cung cấp Reviews của Product.
- Apollo Router nhận một operation từ client, lập query plan và gọi một hoặc cả hai subgraph.

Một request có thể đi theo luồng:

~~~mermaid
flowchart TD
    C[GraphQL Client] -->|HTTP + traceparent| R[Apollo Router / Supergraph]
    R -->|HTTP + trace context| P[Catalog Subgraph - Spring GraphQL]
    R -->|HTTP + trace context| V[Review Subgraph - Spring GraphQL]
    P --> PS[Product Service]
    V --> VS[Review Service]
    PS --> DB1[(Catalog DB)]
    VS --> DB2[(Review DB)]
    R -. OTLP traces and metrics .-> O[OpenTelemetry Collector / APM]
    P -. OTLP traces and metrics .-> O
    V -. OTLP traces and metrics .-> O
~~~

Mục tiêu là mở một trace và nhìn thấy request xuyên qua các service, ví dụ:

1. HTTP request đến router.
2. Router parse, validate và lập query plan.
3. Router gọi `catalog-subgraph` và `review-subgraph`.
4. Mỗi subgraph chạy GraphQL execution.
5. Resolver và DataLoader gọi service/database.
6. Router tổng hợp kết quả và trả response.

Mỗi service vẫn có metrics riêng để theo dõi throughput, latency và lỗi. Trace ID giúp liên kết các span của cùng một request; `service.name` giúp phân biệt span thuộc router hay subgraph nào.

## 2. Ba tầng cần quan sát

| Tầng | Cần đo | Câu hỏi vận hành |
| --- | --- | --- |
| Router / Supergraph | HTTP request, query planning, subgraph fetch, response aggregation, GraphQL errors | Router có chậm không? Subgraph nào làm request chậm? Query plan có fan-out lớn không? |
| Spring GraphQL subgraph | `graphql.request`, `graphql.datafetcher`, `graphql.dataloader`, HTTP server | Request vào subgraph nào thất bại? Field hoặc batch loader nào chậm? |
| Dependency | Database, cache, REST/gRPC downstream, message broker | Resolver chậm do code, connection pool hay dependency? |

Không dùng một metric duy nhất để kết luận nguyên nhân. Ví dụ router request duration tăng có thể do query plan, thời gian chờ subgraph, mạng hoặc tổng hợp response. Cần mở trace và xem span con để tách từng phần.

## 3. Phân biệt OpenTelemetry trace và Apollo Federated Trace (FTV1)

Trong hệ sinh thái Apollo có hai khái niệm dễ nhầm:

| Cơ chế | Mục đích | Đường đi |
| --- | --- | --- |
| OpenTelemetry distributed tracing | Nối các span qua HTTP/service boundary, quan sát router, subgraph và dependency trong APM | W3C Trace Context / OTLP đến Collector hoặc APM |
| Apollo Federated Trace (FTV1) | Gửi thông tin timing/error ở cấp field từ subgraph về router để router tổng hợp và báo cáo GraphOS | Router yêu cầu `apollo-federation-include-trace: ftv1`; subgraph trả trace trong `extensions.ftv1` |

Hai cơ chế có thể bổ sung cho nhau nhưng không phải cùng một định dạng. Micrometer Observation của Spring for GraphQL tạo observations có thể xuất thành metrics/traces qua Micrometer Tracing; điều đó không tự động chứng minh subgraph tương thích FTV1. Nếu muốn GraphOS hiển thị field-level federated traces, phải xác nhận thư viện/runtime federation đang dùng có hỗ trợ FTV1 và cấu hình đúng theo hướng dẫn của thư viện đó.

Với Spring for GraphQL, phần thực hành chính của bài là nối trace context qua HTTP và xuất GraphQL observations sang OTel-compatible backend. Không giả định rằng chỉ bật `GraphQlObservationInstrumentation` là router sẽ nhận được `extensions.ftv1`.

## 4. Spring for GraphQL tạo những observations nào?

Spring for GraphQL tích hợp Micrometer Observation. Khi `ObservationRegistry` được cấu hình và `GraphQlObservationInstrumentation` được đăng ký, framework tạo ba loại observation chính:

| Observation | Phạm vi | Một số low-cardinality key |
| --- | --- | --- |
| `graphql.request` | Một GraphQL execution request | `graphql.operation.type`, `graphql.outcome` |
| `graphql.datafetcher` | Một data fetcher không tầm thường | `graphql.field.name`, `graphql.outcome`, `graphql.error.type` |
| `graphql.dataloader` | Một lần chạy batch loader | `graphql.loader.name`, `graphql.outcome`, `graphql.error.type` |

`graphql.request` có thể có outcome `SUCCESS`, `REQUEST_ERROR` hoặc `INTERNAL_ERROR`. Data fetcher và DataLoader có outcome `SUCCESS` hoặc `ERROR`. Field property được đọc trực tiếp từ Java object thường là trivial fetch và không tạo observation riêng.

Các key có cardinality cao như `graphql.operation.name`, `graphql.execution.id`, `graphql.field.path` hoặc `graphql.loader.size` phù hợp để xem trong trace, nhưng không nên đưa tất cả thành metric tags.

## 5. Bật Micrometer Observation trong từng Spring GraphQL subgraph

Nếu dùng Spring Boot, thêm Actuator và Micrometer Tracing bridge cho OpenTelemetry. Ứng dụng đã có Spring for GraphQL starter thì giữ dependency GraphQL hiện có.

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")

    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Spring Boot dependency management nên quản lý phiên bản tương thích. Nếu không dùng Spring Boot, cần cấu hình `ObservationRegistry`, `MeterRegistry`, tracing bridge/exporter và GraphQL instrumentation thủ công.

Đặt tên service khác nhau cho từng subgraph. Có thể dùng biến môi trường tiêu chuẩn:

~~~yaml
spring:
  application:
    name: catalog-subgraph
~~~

Ở subgraph khác:

~~~yaml
spring:
  application:
    name: review-subgraph
~~~

`service.name` là resource attribute nhận diện service trong trace/metrics. Đừng gắn một giá trị `service.name` chung cho tất cả subgraph, nếu không APM sẽ khó phân biệt service nào phát sinh span.

Spring Boot có thể tự cấu hình GraphQL observation instrumentation khi có `ObservationRegistry` và các điều kiện auto-configuration phù hợp với phiên bản đang dùng. Nếu ứng dụng tự tạo `GraphQlSource` hoặc không dùng Boot auto-configuration, cần đăng ký `GraphQlObservationInstrumentation`:

~~~java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.GraphQlObservationInstrumentation;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
class GraphQlObservationConfiguration {

    @Bean
    GraphQlObservationInstrumentation graphQlObservationInstrumentation(
            ObservationRegistry observationRegistry
    ) {
        return new GraphQlObservationInstrumentation(observationRegistry);
    }
}
~~~

Với Spring Boot GraphQL starter, các bean `Instrumentation` được phát hiện khi tạo `GraphQlSource`. Nếu tự tạo `GraphQlSource` mà không dùng cơ chế auto-configuration, truyền instrumentation trực tiếp vào builder:

~~~java
import java.util.List;

import io.micrometer.observation.ObservationRegistry;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .instrumentation(List.of(
                new GraphQlObservationInstrumentation(observationRegistry)
        ))
        .build();
~~~

Chọn một cách cấu hình phù hợp với cách ứng dụng tạo `GraphQlSource`; tránh đăng ký trùng instrumentation nếu Boot đã tự cấu hình nó. Kiểm tra startup condition và observations thực tế để xác nhận instrumentation được chạy.

## 6. Cấu hình sampling và export trace ở subgraph

Một cấu hình Boot thường cần đặt sampling probability và endpoint exporter theo môi trường:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Ví dụ dùng 10% sampling trong production để giới hạn chi phí. Môi trường development có thể dùng sampling cao hơn để dễ debug. Cấu hình trên minh họa property OTLP tracing của Spring Boot 3.x; tên property có thể thay đổi giữa các dòng Boot, vì vậy hãy đối chiếu tài liệu đúng phiên bản của dự án. `spring.application.name` đặt service identity; có thể dùng `OTEL_SERVICE_NAME` hoặc `management.opentelemetry.resource-attributes` khi cấu hình OpenTelemetry Resource trực tiếp theo phiên bản Boot.

Với tracing phân tán, sampler ở subgraph nên tôn trọng parent sampled flag. Nếu router đã chọn trace request, subgraph nên tiếp tục cùng trace theo parent context; không tự tạo một trace độc lập cho mỗi HTTP request nếu mục tiêu là xem toàn bộ call tree.

Metrics và traces là hai loại tín hiệu khác nhau. Prometheus registry xuất metrics; Micrometer Tracing bridge và OTLP exporter xuất traces. Có Actuator `/actuator/metrics` không đồng nghĩa trace đã được gửi đến Collector.

## 7. Truyền trace context từ router đến subgraph

W3C Trace Context dùng các HTTP headers phổ biến:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

`traceparent` mang trace ID, parent span ID và trace flags. Khi router gọi subgraph qua HTTP, router cần tiếp tục hoặc tạo trace context rồi truyền header tương ứng. HTTP server instrumentation ở Spring Framework nhận context này và tạo server observation/span con.

Spring for GraphQL đặt request observation bên trong transport layer. Tài liệu Spring GraphQL quy định parent observation phải được đặt vào GraphQL context bằng key `micrometer.observation`; với HTTP, Spring Framework có instrumentation riêng đảm nhiệm việc truyền trace context qua network boundary.

Nếu subgraph nhận request qua HTTP nhưng trace không nối với router, kiểm tra theo thứ tự:

1. Router có nhận `traceparent` từ client hoặc tạo trace mới không?
2. Router có gửi `traceparent` đến endpoint subgraph không?
3. Spring Boot HTTP server observation/tracing có được bật không?
4. Subgraph có dùng cùng trace backend và exporter không?
5. Subgraph có nhận parent context hay bắt đầu trace mới?
6. Có proxy/load balancer nào xóa hoặc thay đổi tracing headers không?

Khi subgraph gọi tiếp một REST service hoặc GraphQL service khác, dùng `RestClient.Builder`, `WebClient.Builder` hoặc `RestTemplateBuilder` do Spring Boot auto-configure để trace context được truyền tự động. Tạo client thủ công mà bỏ qua các builder này có thể làm đứt trace ở chiều outbound.

Với transport không phải HTTP hoặc custom transport, cần cơ chế truyền parent observation/context tương ứng. Không mặc định rằng HTTP propagation tự áp dụng cho WebSocket, RSocket hoặc message broker.

## 8. Bật telemetry ở Apollo Router

Apollo Router có telemetry riêng cho request lifecycle. Các span tiêu biểu gồm:

| Span | Phạm vi |
| --- | --- |
| `router` | HTTP request từ góc nhìn router |
| `supergraph` | GraphQL operation sau khi parse/validate và xử lý query plan |
| `subgraph` | HTTP call đến một subgraph |

Router hỗ trợ xuất telemetry qua OTLP. Ví dụ cấu hình dưới đây bật span cho các giai đoạn và exporter tracing OTLP. Endpoint phải trỏ tới Collector hỗ trợ giao thức exporter mà Router đang cấu hình.

~~~yaml
telemetry:
  instrumentation:
    spans:
      mode: spec_compliant
      router:
        attributes:
          otel.name: router
          operation.name: "router"
      supergraph:
        attributes:
          otel.name: supergraph
          operation.name: "supergraph"
      subgraph:
        attributes:
          otel.name: subgraph
          operation.name: "subgraph"
  exporters:
    tracing:
      otlp:
        enabled: true
        endpoint: "${env.OTEL_GRPC_ENDPOINT}"
~~~

Ví dụ, `OTEL_GRPC_ENDPOINT` có thể được đặt thành `otel-collector:4317` khi Collector nhận OTLP qua gRPC. Dùng endpoint/port đúng với exporter protocol mà Router đang cấu hình; HTTP OTLP thường dùng port `4318` và path signal-specific.

Có thể bật Prometheus exporter cho Router:

~~~yaml
telemetry:
  exporters:
    metrics:
      prometheus:
        enabled: true
        listen: "127.0.0.1:9090"
        path: "/metrics"
~~~

Đây là hai phần cấu hình có thể hợp nhất vào cùng root `telemetry` trong file router. Giới hạn endpoint metrics ở network nội bộ hoặc bảo vệ bằng hạ tầng triển khai; không expose metrics endpoint ra Internet một cách tùy tiện.

Router cũng có thể xuất log JSON:

~~~yaml
telemetry:
  exporters:
    logging:
      stdout:
        enabled: true
        format: json
~~~

Chỉ bật log chi tiết ở môi trường cần thiết. Instrumentation quá nhiều event hoặc attribute có thể làm tăng CPU, dung lượng telemetry và latency của router.

## 9. Phân biệt latency của router và latency của subgraph

Ví dụ một trace có các span:

~~~text
HTTP POST /graphql                         420 ms
  router                                    420 ms
    supergraph                              410 ms
      subgraph catalog                      120 ms
        HTTP server catalog                 105 ms
          graphql.request                    92 ms
            graphql.datafetcher Product.id    2 ms
            graphql.datafetcher Product.price 35 ms
              JDBC query                     30 ms
      subgraph review                       250 ms
        HTTP server review                  235 ms
          graphql.request                   220 ms
            graphql.dataloader reviews      180 ms
              SQL query                     170 ms
~~~

Trong ví dụ, review subgraph có batch query chậm và là nhánh có thời gian lớn hơn. Tối ưu catalog trước có thể không làm giảm đáng kể latency end-to-end. Cần mở span con của `graphql.dataloader` hoặc database để tìm nguyên nhân.

Khi các subgraph được gọi song song, không cộng tất cả thời lượng subgraph để suy ra request duration. End-to-end latency thường bị chi phối bởi nhánh chậm nhất cộng với phần planning, network và response aggregation. Trace timeline giúp nhìn thấy quan hệ song song này.

## 10. Dùng GraphQL observations để tìm field chậm

Trong Spring GraphQL, `graphql.datafetcher` đo các resolver không tầm thường. Các key mặc định hữu ích:

| Key | Cardinality | Dùng để |
| --- | --- | --- |
| `graphql.field.name` | Low | Nhóm thời gian/lỗi theo field name |
| `graphql.outcome` | Low | Phân biệt `SUCCESS` và `ERROR` |
| `graphql.error.type` | Low | Phân nhóm loại exception |
| `graphql.field.path` | High | Xác định vị trí field cụ thể trong trace |

Nếu `Product.price` thường chậm, mở trace để kiểm tra service hoặc database span bên dưới. Nếu field property đơn giản không có observation riêng, xem request span hoặc instrument service/repository tương ứng.

Đối với DataLoader:

| Key | Cardinality | Dùng để |
| --- | --- | --- |
| `graphql.loader.name` | Low | Xác định loader đang chạy |
| `graphql.outcome` | Low | Phân biệt batch thành công/thất bại |
| `graphql.error.type` | Low | Nhóm lỗi batch |
| `graphql.loader.size` | High | Điều tra kích thước batch trong trace |

Kết hợp batch duration và batch size để phát hiện batch quá nhỏ, quá lớn hoặc service bị chậm. Nếu cần metric tổng hợp theo size range, tạo bucket có số lượng hữu hạn thay vì đưa giá trị size bất kỳ thành tag metric.

## 11. Đặt service identity và metadata nhất quán

Mỗi process nên có resource attributes rõ ràng:

~~~text
service.name = catalog-subgraph
service.namespace = commerce
deployment.environment = production
service.version = 1.8.0
~~~

Router có `service.name` riêng, ví dụ `apollo-router`. Review subgraph có `service.name=review-subgraph`. Có thể thêm `service.namespace`, `deployment.environment`, `service.version` để so sánh theo môi trường và phiên bản release.

Không gắn subgraph name thành tag động ở mọi metric nếu mỗi subgraph đã chạy thành service riêng và `service.name` đã thể hiện điều đó. Trong router span, subgraph name là attribute có ích để biết call nào đang được thực hiện.

Không đưa các giá trị sau vào low-cardinality metrics:

- Trace ID, span ID hoặc request ID.
- User ID, email, customer ID hoặc tenant ID không giới hạn.
- Raw GraphQL query hoặc toàn bộ variables.
- Field path chứa index của list hoặc dữ liệu đầu vào.
- Error message có nội dung động.

Các giá trị này làm tăng cardinality hoặc có thể chứa dữ liệu nhạy cảm. Nếu cần dùng chúng để điều tra, cân nhắc trace attributes có kiểm soát, redaction và chính sách retention.

## 12. Correlate logs với traces

Log của router và subgraph cần có trace ID/span ID để chuyển từ log sang trace. Khi Micrometer Tracing tích hợp với logging framework, MDC correlation có thể được thêm vào log pattern hoặc structured logging.

Spring Boot mặc định thêm correlation ID dựa trên MDC `traceId` và `spanId` khi Micrometer Tracing hoạt động. Có thể tùy chỉnh `logging.pattern.correlation` nếu muốn log thể hiện thêm `spring.application.name` hoặc định dạng khác.

Ví dụ log dạng JSON:

~~~json
{
    "timestamp": "2026-11-20T06:30:00Z",
    "level": "ERROR",
    "service": "review-subgraph",
    "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
    "spanId": "00f067aa0ba902b7",
    "message": "Review batch lookup failed",
    "loader": "reviewsByProductId"
}
~~~

Không tự log toàn bộ GraphQL request body để lấy operation name hoặc variables. Có thể dùng operation name đã được chuẩn hóa, field name và trace ID. Nếu log error details, loại bỏ token, password, personal data và nội dung truy vấn có thông tin nhạy cảm.

Khi điều tra một request:

1. Tìm trace bằng trace ID từ log hoặc response correlation.
2. Xem router span để biết subgraph nào bị gọi và thời gian chờ.
3. Mở server span của subgraph tương ứng.
4. Tìm `graphql.request`, `graphql.datafetcher` hoặc `graphql.dataloader` có latency/error bất thường.
5. Đi tiếp xuống JDBC, Redis hoặc HTTP client span.
6. Dùng log có cùng trace ID để xem thông tin lỗi đã được redacted.

## 13. GraphQL outcome không đồng nghĩa HTTP status

GraphQL có thể trả HTTP `200 OK` cùng response `data` một phần và `errors`. Do đó cần quan sát cả transport và GraphQL execution.

| Tín hiệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| HTTP server status | `200`, `400`, `500` | Kết quả ở tầng HTTP transport |
| `graphql.outcome` | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` | Kết quả GraphQL request trong Spring GraphQL |
| `graphql.datafetcher` outcome | `SUCCESS`, `ERROR` | Một resolver có thành công không |
| `graphql.dataloader` outcome | `SUCCESS`, `ERROR` | Một batch load có thành công không |

Nếu HTTP 200 nhưng `graphql.outcome=REQUEST_ERROR`, request đã tới GraphQL server và có GraphQL errors không thuộc internal error. Nếu HTTP request lỗi trước khi GraphQL execution bắt đầu, có thể không có `graphql.request` observation tương ứng. Khi dashboard chỉ dựa trên HTTP 5xx, các lỗi GraphQL có thể bị bỏ sót.

## 14. Apollo Federated Trace Data và GraphOS

Nếu dùng GraphOS Insights, router có thể tổng hợp field-level trace data từ các subgraph hỗ trợ FTV1. Luồng khái quát:

1. Router nhận operation và tạo query plan.
2. Router gửi sub-query tới từng subgraph.
3. Khi cần thu thập FTV1, router gửi header `apollo-federation-include-trace: ftv1`.
4. Subgraph tương thích trả trace data trong response `extensions.ftv1`.
5. Router ghép các trace con theo query plan và báo cáo federated trace tới GraphOS.

Đây là cách GraphOS hiển thị timing/error ở cấp field qua toàn supergraph. Khả năng FTV1 phụ thuộc thư viện subgraph và cấu hình của nó. Với subgraph Spring GraphQL, cần kiểm tra adapter Federation/runtime đang dùng có hỗ trợ format này hay không; không tự thêm `extensions.ftv1` bằng một observation Micrometer thông thường.

Apollo Router cũng có thể xuất OpenTelemetry traces trực tiếp tới OTLP backend. Nếu mục tiêu là Jaeger, Tempo, Zipkin hoặc Datadog, dùng Router OTEL exporter và subgraph Micrometer/OTel exporter để nối trace context. Nếu mục tiêu là GraphOS field-level trace, kiểm tra FTV1 support và cấu hình reporting riêng.

Hai luồng có thể cùng được triển khai, nhưng sampling và privacy policy phải được thiết kế nhất quán. Federated trace payload có thể làm tăng kích thước response subgraph và latency; chỉ bật mức chi tiết cần thiết.

## 15. Sampling xuyên router và subgraph

Sampling giảm chi phí lưu trữ và xử lý trace. Một chiến lược đơn giản:

- Development: sampling cao để quan sát mọi nhánh khi debug.
- Staging: sampling đủ cao để kiểm tra query plan và field behavior.
- Production: parent-based sampling với tỷ lệ phù hợp tải và ngân sách telemetry.
- Error/high-latency tail: cân nhắc tail-based sampling ở Collector để giữ lại trace lỗi hoặc chậm nếu hạ tầng hỗ trợ.

Nếu mỗi subgraph tự random sampling độc lập, trace có thể thiếu span con dù router đã ghi span cha. Dùng parent-based sampler để tôn trọng sampled flag trong trace context. Nếu dùng tail sampling, Collector phải nhận đủ spans của trace trước khi quyết định giữ/bỏ; cấu hình exporter và batching cần phù hợp.

Không tăng sampling lên 100% trong production mà không đánh giá lưu lượng, kích thước span, overhead và retention. Có thể tăng tạm thời khi điều tra một incident rồi trả về mức bình thường.

## 16. Dashboard và alert cho federated graph

Một dashboard vận hành nên chia thành các nhóm:

| Dashboard section | Metrics/attributes gợi ý | Câu hỏi |
| --- | --- | --- |
| Supergraph traffic | Router request rate, active requests, HTTP status | Traffic tăng hay router đang bị bão hòa? |
| End-to-end latency | p50/p95/p99 router request duration | Client đang cảm nhận độ trễ thế nào? |
| Subgraph latency | Subgraph span duration theo subgraph name | Subgraph nào chi phối critical path? |
| GraphQL errors | `graphql.outcome`, field/DataLoader error rate | Lỗi xuất hiện ở request, resolver hay batch? |
| Query planning | Supergraph/query planning span duration | Operation có query plan phức tạp không? |
| Dependency | JDBC, Redis, HTTP client spans | Resolver đang chờ dependency nào? |
| Saturation | CPU, memory, connection pool, thread/worker utilization | Service có gần chạm giới hạn tài nguyên không? |

Alert nên dùng SLO và baseline thực tế. Ví dụ:

- p95 latency của supergraph vượt SLO trong một cửa sổ đủ dài.
- Tỷ lệ `graphql.outcome=INTERNAL_ERROR` tăng đột biến.
- Một subgraph có p95 cao hơn các subgraph khác hoặc vượt budget riêng.
- DataLoader error rate tăng hoặc batch duration tăng kéo dài.
- Router active requests tăng trong khi subgraph throughput không tăng tương ứng.

Không đặt alert trên từng trace ID hoặc operation name tùy ý. Dùng các dimension có tập giá trị được kiểm soát như service, environment, operation type và outcome.

## 17. Phân bổ latency budget cho subgraph

Giả sử SLO end-to-end của một operation là 500 ms. Có thể chia budget tham khảo:

| Thành phần | Budget minh họa |
| --- | ---: |
| Router parse/validate/query plan | 40 ms |
| Network + subgraph fetch overhead | 40 ms |
| Catalog subgraph critical path | 150 ms |
| Review subgraph critical path | 200 ms |
| Response aggregation/serialization | 40 ms |
| Headroom | 30 ms |

Đây chỉ là ví dụ để lập ngân sách, không phải giá trị mặc định. Nếu router gọi hai subgraph song song, tổng thời gian không phải tổng budget của hai subgraph; nhánh chậm nhất thường quyết định phần lớn thời gian chờ. Nếu các subgraph được gọi theo dependency tuần tự, thời gian có thể cộng dồn.

Khi một operation vượt SLO, dùng trace để xác định nhánh critical path, sau đó đặt SLO/alert riêng cho subgraph hoặc dependency liên quan.

## 18. Kiểm thử trace propagation xuyên federation

Không nên chỉ kiểm tra endpoint metrics có trả dữ liệu. Cần kiểm tra trace context thực sự được nối:

1. Gửi request có `traceparent` hợp lệ tới router.
2. Xác nhận router tạo/tiếp tục trace có trace ID mong đợi.
3. Xác nhận request đến subgraph có parent trace context tương ứng.
4. Xác nhận subgraph tạo server span con và GraphQL request observation.
5. Xác nhận data fetcher/DataLoader observations nằm trong trace của request đó.
6. Xác nhận spans được export đến cùng Collector/backend.

Ở integration test, có thể dùng in-memory exporter hoặc test observation handler để kiểm tra parent/child span relationships. Ở môi trường chạy thật, gửi một operation qua router và kiểm tra trace trong backend. Test phải dùng một trace ID cố định chỉ trong môi trường test; không hardcode trace ID trong production request.

Một kiểm tra quan trọng là gửi request qua router rồi gọi trực tiếp subgraph. Request trực tiếp nên tạo trace mới nếu không có parent context; request qua router phải có parent span liên kết. Điều này giúp phân biệt instrumentation ở subgraph có hoạt động nhưng propagation từ router bị đứt.

## 19. Kiểm thử GraphQL observations ở subgraph

`GraphQlTester` có thể xác minh GraphQL response, trong khi Micrometer `MeterRegistry`/Observation test handler xác minh observation đã được ghi.

Các scenario cần kiểm tra:

| Scenario | Request observation | Field/DataLoader observation |
| --- | --- | --- |
| Query thành công | `SUCCESS` | Field/batch thành công |
| Resolver trả lỗi nghiệp vụ | Thường `REQUEST_ERROR` nếu error không phải internal | Data fetcher `ERROR` |
| Resolver phát sinh internal error | `INTERNAL_ERROR` | Data fetcher `ERROR` |
| Batch loader thất bại | Request outcome theo ErrorType trong response | DataLoader `ERROR` |

Test metrics nên cô lập `MeterRegistry` hoặc so sánh count trước/sau request để tránh phụ thuộc test chạy trước. Đừng dùng `GraphQlTester` response assertion thay cho trace propagation test; hai test kiểm tra hai hợp đồng khác nhau.

## 20. Troubleshooting observability xuyên federation

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Router có trace nhưng subgraph không xuất hiện | Router không propagate `traceparent`, subgraph thiếu HTTP tracing hoặc exporter không hoạt động | Kiểm tra outbound headers, server instrumentation và OTLP exporter |
| Subgraph có trace riêng nhưng không cùng trace ID với router | Parent context không được nhận hoặc bị thay thế | Kiểm tra W3C Trace Context và proxy/load balancer |
| Có HTTP metrics nhưng không có `graphql.request` | GraphQL instrumentation chưa được cấu hình hoặc `ObservationRegistry` không có | Kiểm tra GraphQlObservationInstrumentation/Boot auto-configuration |
| Có `graphql.request` nhưng không có data fetcher spans | Field chỉ là property access trivial hoặc instrumentation không ghi nhận resolver | Kiểm tra field mapping và GraphQL instrumentation |
| Router span cho thấy subgraph chậm nhưng subgraph request nhanh | Độ trễ nằm ở network, queue, connection hoặc thời gian router chờ/đọc response | So sánh router subgraph span, HTTP server span và network metrics |
| GraphQL trả HTTP 200 nhưng dashboard không báo lỗi | Dashboard chỉ lọc HTTP 5xx | Theo dõi `graphql.outcome` và field/DataLoader error |
| Metrics có quá nhiều time series | Operation name, path, ID hoặc user data được dùng làm metric tags | Giảm low-cardinality tags; chuyển dữ liệu chi tiết sang trace khi phù hợp |
| GraphOS không có field-level federated trace | Subgraph không hỗ trợ FTV1 hoặc chưa cấu hình trả trace | Kiểm tra hỗ trợ FTV1 và header/request flow |
| OTLP trace có nhưng GraphOS Studio không hiển thị | OTLP APM trace và GraphOS federated trace reporting là hai pipeline | Cấu hình GraphOS reporting/FTV1 riêng nếu cần Studio Insights |
| Trace bị thiếu span con không ổn định | Sampling độc lập hoặc context bị mất khi async | Dùng parent-based sampling và kiểm tra context propagation |
| Trace/log chứa dữ liệu nhạy cảm | Raw query, variables hoặc exception message bị ghi | Redact payload, giới hạn attributes và kiểm tra retention |
| Router chậm sau khi bật telemetry | Thu thập quá nhiều spans/events hoặc sampling quá cao | Giảm sampling, bỏ attributes thừa và đo overhead |

## 21. Checklist triển khai

Khi bật observability cho một federated graph có Spring GraphQL subgraphs:

1. Đặt `service.name` riêng cho router và từng subgraph.
2. Bật Micrometer Observation trong từng Spring GraphQL service.
3. Cấu hình Micrometer Tracing bridge và OTLP exporter cho subgraph.
4. Bật Router telemetry và export traces/metrics tới Collector.
5. Bảo đảm W3C `traceparent` được truyền từ router tới HTTP subgraph.
6. Kiểm tra GraphQL observations nằm dưới đúng HTTP server span.
7. Theo dõi `graphql.request`, `graphql.datafetcher` và `graphql.dataloader`.
8. Dùng resource attributes để phân biệt environment, service và version.
9. Giữ metrics tags low-cardinality; tránh ID, raw query và variables.
10. Correlate structured logs với trace ID/span ID.
11. Đặt sampling phù hợp và ưu tiên parent-based propagation.
12. Phân biệt OTEL traces với Apollo FTV1 federated trace data.
13. Chỉ bật FTV1 khi federation runtime/subgraph adapter hỗ trợ và cần GraphOS field traces.
14. Tạo dashboard theo router, subgraph, GraphQL outcome và dependency latency.
15. Kiểm thử trace propagation và GraphQL observations qua một operation thật.
16. Đánh giá privacy, retention và telemetry overhead trước khi triển khai production.

Observability xuyên federation hiệu quả khi một request có thể được theo dõi từ router tới đúng subgraph, field resolver và dependency. Spring for GraphQL cung cấp các GraphQL observations ở từng subgraph; OpenTelemetry nối chúng qua ranh giới dịch vụ; router telemetry cho biết query plan và subgraph fetch. Khi phân biệt đúng các lớp này và kiểm soát cardinality/sampling, đội vận hành có thể tìm ra nhánh gây lỗi hoặc chậm mà không phải bật log payload quá mức.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Apollo Router — Router Telemetry](https://www.apollographql.com/docs/graphos/routing/observability/router-telemetry-otel)
- [Apollo Router — OpenTelemetry in Apollo Federation](https://www.apollographql.com/docs/graphos/routing/observability/router-telemetry-otel/enabling-telemetry/usage-guides/subgraph-instrumentation)
- [Apollo GraphOS — Federated Trace Data](https://www.apollographql.com/docs/graphos/routing/observability/graphos/federated-trace-data)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
