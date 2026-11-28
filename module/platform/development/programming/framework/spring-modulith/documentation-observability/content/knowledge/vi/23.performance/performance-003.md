# Chi phí export metrics và traces

Trong ứng dụng Spring Boot dùng Spring Modulith, metrics và traces giúp quan sát ranh giới application module, thời gian xử lý, event publication và lỗi giữa các thành phần. Tuy nhiên, mỗi tín hiệu được tạo ra đều tiêu thụ tài nguyên: CPU để đo và serialize, bộ nhớ để giữ meter/span và hàng đợi, băng thông để gửi dữ liệu, dung lượng lưu trữ ở backend và chi phí truy vấn.

Chi phí có thể tăng nhanh khi thêm module instrumentation, histogram buckets, tag có nhiều giá trị, span attributes lớn hoặc sampling quá cao. Một dashboard đơn giản vẫn có thể tạo hàng triệu time series; một request qua nhiều module có thể tạo nhiều span records hơn dự kiến.

Bài học thuộc chương **Hiệu năng** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Nội dung tập trung vào cách ước lượng, đo và tối ưu chi phí export metrics/traces trong Spring Boot, Micrometer, Spring Modulith và OpenTelemetry mà vẫn giữ tín hiệu cần thiết cho vận hành.

> **Nguyên tắc:** đo workload thực tế trước khi thay đổi sampling, scrape interval, histogram hoặc batch size. Các công thức dưới đây là mô hình ước lượng; payload, compression, backend pricing và overhead thay đổi theo exporter, protocol, instrumentation và môi trường.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt chi phí tạo telemetry, export, truyền tải, ingest, lưu trữ và truy vấn.
2. Ước lượng metric samples/day từ active series và scrape interval.
3. Ước lượng spans/day từ request rate, spans/request và sampling ratio.
4. Giải thích vì sao cardinality, histogram buckets và span payload size ảnh hưởng chi phí.
5. Phân biệt Prometheus pull metrics với OTLP push metrics.
6. Hiểu batch, queue, timeout, retry và data loss ở SDK/Collector.
7. Cấu hình export phù hợp với Spring Boot/Micrometer/OpenTelemetry.
8. Dùng dashboard và benchmark để tìm điểm cân bằng giữa chi phí và khả năng điều tra.

## 2. Các lớp chi phí của telemetry

Một pipeline điển hình:

~~~mermaid
flowchart LR
    App["Spring Boot + Modulith
    Observations / meters / spans"] --> SDK["Micrometer registry
    Tracing SDK / exporter queues"]
    SDK --> Net["Network
    OTLP or scrape"]
    Net --> Collector["OpenTelemetry Collector
    processors / queues / exporters"]
    Collector --> Metrics["Metrics backend"]
    Collector --> Traces["Tracing backend"]
    Metrics --> Dash["Dashboards / alerts / SLO"]
    Traces --> Search["Trace search / investigations"]
~~~

| Lớp | Tài nguyên tiêu thụ | Dấu hiệu cần đo |
| --- | --- | --- |
| Instrumentation trong ứng dụng | CPU, allocation, lock contention, meter/span objects | CPU profile, allocation rate, request latency |
| Registry và SDK | Bộ nhớ cho meters, active series, span buffers | Meter count, queue size, heap, GC |
| Serialization và compression | CPU, temporary buffers | Export duration, CPU, payload bytes |
| Network | Băng thông, connection, TLS handshake | Bytes/s, request count, retry |
| Collector | CPU, memory, queue, disk nếu persistent queue | Queue utilization, refused data, exporter failures |
| Backend ingest | Ingest quota, write throughput, index/compaction | Samples/s, spans/s, ingest bytes/s |
| Storage | Retention, replication, indexes, object/block storage | GiB/day, retention days |
| Query | CPU/RAM backend, query samples scanned | Query latency, dashboard load, query cost |

Không nên chỉ nhìn hóa đơn backend. Cardinality cao có thể làm heap của ứng dụng tăng trước khi backend nhận dữ liệu. Ngược lại, tăng batch size có thể giảm số request mạng nhưng tăng bộ nhớ và thời gian chờ export.

### Metrics và traces tạo chi phí theo cách khác nhau

- **Metrics:** chi phí thường bị chi phối bởi số active time series, tần suất thu thập/export, số histogram buckets, số target và retention.
- **Traces:** chi phí thường bị chi phối bởi request rate, số spans trong mỗi trace, sampling ratio, kích thước span, event/link/attribute và thời gian giữ trace.

Metrics phù hợp để đo toàn bộ traffic với nhãn có cardinality được kiểm soát. Traces thường được sampling để giới hạn chi phí nhưng vẫn giữ được những request đại diện hoặc bất thường.

## 3. Chi phí metrics: active series và scrape interval

Một time series được xác định bởi tên metric và tổ hợp label/tag. Cùng một meter có thể tạo nhiều series khi các tag có nhiều giá trị.

Ví dụ:

~~~text
http.server.requests{
  method="GET",
  status="200",
  uri="/orders"
}
~~~

Nếu metric có 4 HTTP methods, 6 nhóm status, 12 URI templates và 3 application instances, nó có thể có tối đa:

\[
4 \times 6 \times 12 \times 3 = 864
\]

series. Đây là số tổ hợp tối đa theo các dimension giả định, không phải số series chắc chắn sẽ xuất hiện.

### Công thức ước lượng samples

Với Prometheus scrape:

\[
\text{samples/day} \approx
\text{active series} \times
\frac{86\,400}{\text{scrape interval (seconds)}}
\]

Ví dụ một service có 8.000 active series:

| Scrape interval | Samples/series/day | Tổng samples/day |
| --- | ---: | ---: |
| 15 giây | 5.760 | 46.080.000 |
| 30 giây | 2.880 | 23.040.000 |
| 60 giây | 1.440 | 11.520.000 |

Tăng scrape interval từ 15 lên 60 giây làm số samples giảm khoảng 75% nếu số active series không đổi. Đổi lại, dashboard có độ phân giải thấp hơn và các spike ngắn có thể khó quan sát.

Đối với Prometheus local storage, có thể ước lượng sơ bộ:

\[
\text{disk bytes} \approx
\text{retention seconds} \times
\text{ingested samples/second} \times
\text{bytes/sample}
\]

Tài liệu Prometheus đưa ra mức trung bình khoảng 1–2 bytes/sample cho dữ liệu time series đã lưu. Đây chỉ là ước lượng planning cho TSDB, không phải kích thước payload mạng hay cam kết cho remote backend; WAL, head chunks, labels, compaction, replication và phiên bản có thể làm dung lượng thực tế khác đi.

Với push registry như Micrometer OTLP, thay scrape interval bằng export step. Số data points được gửi phụ thuộc loại meter, temporality, aggregation và registry implementation. Không mặc định một push point tương đương một Prometheus scrape sample.

### Histogram làm tăng số series

Histogram thường tạo nhiều bucket series cùng với count/sum. Nếu có 20 bucket boundaries và 500 tổ hợp tag, metric histogram có thể tạo khoảng 11.000 series (20 bucket + count + sum, nhân với 500) trong một exposition dạng Prometheus classic histogram. Số chính xác phụ thuộc registry, bucket boundaries, cumulative buckets và cách backend biểu diễn histogram.

Trước khi bật histogram cho một meter:

1. Xác định dashboard thật sự cần phân vị/latency distribution hay chỉ cần average/max.
2. Chọn bucket boundaries phù hợp với SLA và latency thực tế.
3. Giới hạn tag combinations.
4. Đo series count trước và sau.
5. Kiểm tra backend có hỗ trợ native histogram hoặc aggregation khác giúp giảm số series không.

Không bật percentile histogram cho mọi meter chỉ vì cấu hình có sẵn. Histogram hữu ích cho latency SLO nhưng có thể tạo lượng series lớn khi kết hợp với nhiều tag.

## 4. Cardinality là nguồn chi phí dễ bị bỏ sót

Micrometer tạo meter riêng cho từng tổ hợp tag values. Nếu tag có giá trị không giới hạn như user ID, request ID, trace ID, session ID, email hoặc full URL, số meter/time series có thể tăng theo traffic và dữ liệu người dùng.

Ví dụ sai:

~~~java
Counter.builder("order.completed")
        .tag("order_id", order.getId().toString())
        .register(registry)
        .increment();
~~~

Mỗi order ID có thể tạo một meter riêng. Hàng triệu đơn hàng có thể tạo hàng triệu meter và series.

Ví dụ phù hợp hơn:

~~~java
Counter.builder("order.completed")
        .tag("channel", order.getChannel())
        .tag("outcome", "success")
        .register(registry)
        .increment();
~~~

Các tag như channel/outcome chỉ phù hợp nếu tập giá trị được giới hạn và validate.

### Phân loại metadata

Spring Boot/Micrometer Observation phân biệt low-cardinality và high-cardinality key-values:

| Loại | Ví dụ | Nơi sử dụng |
| --- | --- | --- |
| Low cardinality | module, event type, HTTP method, status group, outcome | Metrics và traces |
| High cardinality | order ID, user ID, request ID, trace ID, session ID | Traces/logs; không dùng làm metric tags |

Một ID có thể rất hữu ích khi điều tra một request nhưng không phù hợp làm metric tag. Có thể đặt metadata định danh vào trace/log, còn metric chỉ dùng nhóm giá trị hữu hạn.

### Ước lượng cardinality tổng

Với metric có n tag keys:

\[
\text{possible series} \leq
\prod_{i=1}^{n} |\text{distinct values of tag}_i|
\]

Ví dụ:

| Tag | Số giá trị |
| --- | ---: |
| module | 6 |
| event_type | 10 |
| outcome | 4 |
| instance | 3 |
| Tổng tổ hợp tối đa | 720 |

Nếu thêm order ID có 500.000 giá trị, số tổ hợp lý thuyết tăng lên 360 tỷ. Thực tế có thể không đạt tới con số đó nhưng chỉ một phần nhỏ cũng đủ làm registry và backend quá tải.

### Giới hạn cardinality bằng MeterFilter

Khi instrumentation bên thứ ba tạo tag khó kiểm soát, MeterFilter có thể làm hàng rào bảo vệ:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricsConfiguration {

    @Bean
    MeterFilter limitUriCardinality() {
        return MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny()
        );
    }
}
~~~

Spring Boot tự đăng ký các MeterFilter bean trên registry do Spring quản lý. Giới hạn là biện pháp bảo vệ cuối cùng; ưu tiên sửa instrumentation để dùng URI template như /orders/{id} thay vì URL chứa ID thật. Kiểm tra meter name và tag key trong exposition thực tế của phiên bản dự án.

Micrometer cũng có High Cardinality Tags Detector ở các version hỗ trợ. Detector giúp phát hiện nhiều meters cùng tên có thể do tag cardinality cao; nó là cảnh báo heuristic, không thay thế việc thiết kế tag có giới hạn.

## 5. Metrics export: Prometheus pull và OTLP push

Spring Boot auto-configures Micrometer và thêm registry tương ứng khi dependency registry có trong runtime classpath. Vì vậy, cần biết ứng dụng đang export metrics tới bao nhiêu đích.

| Mô hình | Cách hoạt động | Chi phí cần quan sát |
| --- | --- | --- |
| Prometheus pull | Prometheus scrape endpoint của ứng dụng theo interval | Số target, scrape interval, series/target, scrape duration |
| Micrometer OTLP push | OtlpMeterRegistry export theo step | Data points/step, export duration, retries, payload bytes |
| Vendor registry push | Registry gửi dữ liệu theo chu kỳ của backend | Export interval, request quota, payload size, retry |
| Nhiều registry cùng lúc | Composite registry fan-out tới nhiều backend | Serialization/network có thể lặp, ingest bị tính nhiều lần |

### Tránh export trùng không chủ đích

Nếu dependency có nhiều registry, Spring Boot có thể thêm tất cả vào composite MeterRegistry. Một meter được ghi một lần nhưng được export tới nhiều registry. Điều này hữu ích khi chủ ý dual-publish, nhưng làm tăng network và backend ingestion.

Trong cấu hình Spring Boot hiện hành, Micrometer là lựa chọn metrics chính của Spring portfolio. OpenTelemetry SDK MeterProvider không tự động thay thế Micrometer registry; nếu dependency riêng dùng OTel MeterProvider, phải cấu hình export/wiring riêng. Tắt OpenTelemetry SDK cũng không nhất thiết tắt Micrometer metrics. Vì vậy, inventory cả MeterRegistry và OTel SDK trước khi tính chi phí để tránh bỏ sót hoặc export trùng.

Kiểm tra:

- Có cả Prometheus registry và OTLP registry cùng hoạt động không?
- Có exporter thứ hai hoặc agent đang gửi cùng metrics không?
- Có cả Spring Boot Micrometer metrics và một OpenTelemetry MeterProvider riêng cùng ghi cùng tín hiệu không?
- Có registry nào chỉ cần ở staging/debug nhưng lại bật trong production không?

Tắt registry không cần dùng bằng property tương ứng; không xóa instrumentation quan trọng để giảm chi phí trước khi hiểu registry nào đang export.

## 6. Spring Modulith metrics và chi phí theo module

Spring Modulith Insight cung cấp observability cho application module và event interactions. Các meter như module.events.published giúp theo dõi số event được publish, còn module spans giúp lần theo lời gọi qua ranh giới module.

Đối với event metrics:

- Dùng event type và module identifier có tập giá trị hữu hạn.
- Không gắn publication UUID, aggregate ID hoặc event payload vào metric tags.
- Giữ riêng metric publication và metric listener completion.
- Chỉ thêm meter riêng cho event types thực sự cần dashboard/alert.

Nếu ứng dụng có 40 event types và 8 module, hãy tính trước số meter/tag combinations. Đừng tạo meter name động từ tên lớp hoặc payload không được kiểm soát.

Module spans cũng có chi phí. Một request qua 6 module có thể tạo thêm nhiều spans so với request chỉ đi qua một module. Hãy instrument những ranh giới giúp trả lời câu hỏi vận hành, và tránh tạo span cho từng method nhỏ nếu không mang lại giá trị chẩn đoán.

**Lưu ý:** module.events.published đo publication, không đo listener completion. Nếu cần đo chi phí consumer, thêm success/failure counters hoặc theo dõi Event Publication Registry và backlog metrics.

## 7. Chi phí traces: request rate, spans/request và sampling

Trace thường bao gồm root span và các child spans. Với Spring Modulith, một request có thể tạo HTTP server span, module invocation spans, database/client spans, event publication/listener spans và external HTTP/RPC spans.

Ước lượng:

\[
\text{spans/day} \approx
\text{requests/second} \times
\text{spans/request} \times
\text{sampling ratio} \times 86\,400
\]

Payload thô:

\[
\text{raw trace bytes/day} \approx
\text{spans/day} \times
\text{average bytes/span}
\]

Payload thực gửi phụ thuộc protobuf encoding, compression, batch, attributes, events, links và protocol. Hãy đo byte thực tế thay vì coi raw estimate là hóa đơn.

### Ví dụ ước lượng

Giả sử ứng dụng có 150 requests/second, trung bình 5 spans/request và average span payload 1,2 KB trước compression:

| Sampling ratio | Spans/second | Spans/day | Raw payload/day |
| --- | ---: | ---: | ---: |
| 100% | 750 | 64.800.000 | khoảng 77,8 GB |
| 10% | 75 | 6.480.000 | khoảng 7,8 GB |
| 5% | 37,5 | 3.240.000 | khoảng 3,9 GB |

Các số liệu là ví dụ để lập ngân sách. Payload thực tế có thể nhỏ hơn sau compression hoặc lớn hơn khi span có nhiều attributes/events.

### Sampling không đồng nghĩa với metrics sampling

Giảm trace sampling giúp giảm số trace gửi tới tracing backend. Nó không tự động giảm Prometheus metrics hoặc Micrometer metrics. Nếu dashboard cần request count/error rate/SLO toàn traffic, hãy dùng metrics phù hợp thay vì đếm sampled traces.

Spring Boot hiện đặt sampling probability mặc định là 10% trong cấu hình tracing thông thường. Có thể thay đổi bằng management.tracing.sampling.probability. Hãy xác nhận sampler implementation và parent-based behavior trong version đang dùng.

## 8. Kích thước span và attribute budget

Mỗi span có metadata như trace ID, span ID, name, timestamps, status, resource attributes, span attributes, events và links. Số lượng và độ dài các trường này ảnh hưởng CPU để tạo/serialize span, heap khi span được giữ trong exporter queue, payload bytes gửi qua network và indexing/storage ở backend.

Tránh:

- Ghi toàn bộ request/response body vào span.
- Ghi SQL statement có literal values hoặc query parameter nhạy cảm.
- Đưa JWT, cookie, authorization header hoặc dữ liệu cá nhân vào attributes.
- Thêm danh sách item không giới hạn vào span event.
- Ghi stack trace rất dài lặp lại ở nhiều span nếu log đã lưu đầy đủ exception.

Nên ưu tiên module.name, operation name và outcome, stable error type/status, downstream system name, low-cardinality business category và ID cần điều tra trong traces/logs khi policy bảo mật cho phép.

Đặt giới hạn attribute count, value length, event count và link count theo SDK/version. Giới hạn giúp bảo vệ memory/payload, nhưng cắt dữ liệu quá mạnh có thể làm mất bằng chứng cần thiết.

## 9. Batching: giảm overhead nhưng không miễn phí

Batching gom nhiều records vào một lần export:

- Giảm số HTTP/gRPC requests.
- Tăng hiệu quả compression.
- Giảm overhead per-request và TLS/network round trips.
- Có thể cải thiện throughput.

Nhưng batch lớn cũng giữ nhiều span/metric points trong memory hơn, tăng thời gian chờ trước khi gửi batch đủ lớn, tăng payload size và nguy cơ vượt giới hạn receiver, đồng thời làm retry tốn kém hơn nếu batch thất bại.

### BatchSpanProcessor trong SDK

OpenTelemetry BatchSpanProcessor có các tham số phổ biến:

| Tham số | Giá trị mặc định thường gặp | Tác động |
| --- | ---: | --- |
| max queue size | 2.048 spans | Số span tối đa giữ trong queue |
| max export batch size | 512 spans | Số span tối đa trong một batch |
| schedule delay | 5 giây | Thời gian chờ tối đa giữa các lần export |
| export timeout | 30 giây | Thời gian tối đa cho một lần export |

Đây là default của SDK specification/configuration, không phải sizing phù hợp cho mọi workload. Queue đầy có thể làm span mới bị drop; batch size phải nhỏ hơn hoặc bằng queue size.

### Cấu hình Spring Boot tracing exporter

Ví dụ dưới đây minh họa cấu hình Spring Boot hiện hành với OpenTelemetry/OTLP. Kiểm tra property metadata của minor version trong BOM trước khi áp dụng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  opentelemetry:
    tracing:
      export:
        schedule-delay: 5s
        timeout: 10s
        max-queue-size: 4096
        max-batch-size: 512
        otlp:
          endpoint: http://otel-collector:4318/v1/traces
          compression: gzip
          timeout: 10s
~~~

Ví dụ tăng queue lên 4.096 để hấp thụ burst; đây không phải lời khuyên tăng queue mặc định. Đo heap, queue occupancy, export latency và dropped spans trước khi chọn giá trị. Nếu backend chậm kéo dài, queue lớn chỉ trì hoãn thời điểm đầy và tăng memory usage.

## 10. Queue, retry và backpressure

Có nhiều hàng đợi trong pipeline:

1. SDK/BatchSpanProcessor queue trong ứng dụng.
2. Collector exporter sending queue.
3. Backend ingestion buffers/queues.

Các queue này có giới hạn và chính sách retry riêng. Khi backend chậm, queue tăng; khi queue đầy, telemetry có thể bị drop hoặc request export bị block/reject tùy cấu hình.

### Ước lượng thời gian chịu outage

Nếu queue chứa được Q records và pipeline nhận R records/second:

\[
\text{buffer time (seconds)} \approx \frac{Q}{R}
\]

Ví dụ queue chứa 60.000 spans, ứng dụng gửi 1.000 spans/second thì queue chỉ hấp thụ được khoảng 60 giây khi không export được. Với batch queue, phải xác định Q tính theo requests, items hay bytes.

### Collector queue và retry

Collector exporter thường có sending queue và retry-on-failure. Queue đầy hoặc retry hết thời gian có thể làm mất telemetry. Persistent queue/WAL có thể bảo vệ dữ liệu qua restart nhưng tạo thêm disk I/O, disk capacity và vận hành storage.

Theo dõi các tín hiệu:

- otelcol_exporter_queue_size
- otelcol_exporter_queue_capacity
- otelcol_exporter_enqueue_failed_spans
- otelcol_exporter_send_failed_spans
- otelcol_processor_refused_spans
- otelcol_receiver_refused_spans
- Các metric tương đương cho metric points và log records

Không chỉ tăng queue hoặc worker khi thấy backlog. Nếu backend đã quá tải, tăng worker có thể làm backend chịu thêm áp lực. Trước tiên xác định nút thắt là network, Collector CPU/memory, exporter, hay backend ingest.

## 11. Collector batching và thay đổi phiên bản

Collector có thể batch telemetry ở processor hoặc exporter. Cách cấu hình phụ thuộc distribution và version.

**Lưu ý cập nhật:** OpenTelemetry chính thức deprecate Batch Processor truyền thống vào tháng 11/2026, hướng tới exporter-level batching và processor mới queue_batch. Theo kế hoạch được công bố, exporter batching dự kiến bật mặc định ở Collector 0.171.0 (tháng 2/2027), còn Batch Processor dự kiến bị gỡ khỏi core distributions ở 0.177.0 (tháng 5/2027). Vì vậy, không copy cấu hình processors: batch từ bài viết cũ mà không kiểm tra release notes và component availability của Collector đang triển khai.

Khi chọn batch configuration, document batch trigger theo số records hay timeout, batch maximum size và giới hạn receiver, queue sizer đo requests/items/bytes, retry duration và backoff, queue in-memory hay persistent, thứ tự memory limiter/sampling/batching và hành vi khi queue đầy.

Batching nên được đặt sau những processor có thể loại dữ liệu như sampling, nếu thứ tự pipeline/version quy định như vậy. Đọc tài liệu của component đang dùng vì thứ tự và semantics có thể thay đổi giữa các bản.

## 12. Metrics export với Spring Boot

Spring Boot dùng Micrometer làm metrics facade. Khi registry tương ứng có trong classpath, Boot có thể auto-configure registry và thêm vào composite registry.

### Prometheus scrape

Ví dụ cấu hình endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: shop-application
      environment: production
~~~

Prometheus scrape interval được cấu hình phía Prometheus/agent, không phải bằng property export step của Micrometer.

### OTLP push qua Micrometer

Ví dụ cấu hình Micrometer OTLP registry:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://otel-collector:4318/v1/metrics
        step: 30s
        connect-timeout: 5s
        read-timeout: 10s
        compression-mode: gzip
~~~

Property names và exporter behavior phụ thuộc Spring Boot version. Với Boot hiện hành, metric-specific URL có thể được cấu hình riêng; common OTLP properties cho traces/logs/metrics có precedence và path fallback riêng. Kiểm tra đúng reference guide trước khi chuyển từ registry này sang registry khác.

Đừng bật cả Prometheus scrape và OTLP push tới cùng backend nếu không có mục đích dual-ingest. Khi chủ động dual-export, hãy đo số samples nhận ở từng backend và tính chi phí trùng lặp.

## 13. Tối ưu sampling theo mục tiêu vận hành

| Chiến lược | Cách làm | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Head sampling | Quyết định ở đầu trace | Giảm dữ liệu sớm, giảm tải SDK/network/Collector | Có thể bỏ lỡ lỗi xảy ra ở trace không được chọn |
| Parent-based ratio | Root trace chọn theo tỷ lệ; child theo parent | Giữ tính nhất quán trace phân tán | Vẫn có thể bỏ lỡ lỗi trong trace bị loại từ root |
| Tail sampling | Collector/backend quyết định sau khi thấy trace | Có thể ưu tiên lỗi/latency cao | Phải gửi candidate traces tới Collector; tăng state, memory và routing complexity |

Nếu muốn tail sampling giữ trace lỗi, head sampling ở SDK không được loại trace đó trước khi đến Collector. Tail sampling giảm ingest vào backend cuối nhưng không loại bỏ chi phí tạo span và truyền candidate traces tới Collector.

### Chọn tỷ lệ theo môi trường

- Development: có thể lấy mẫu cao để debug.
- Staging: đủ cao cho kiểm thử luồng và lỗi, nhưng gần workload thực tế.
- Production: bắt đầu từ baseline có kiểm soát, sau đó điều chỉnh theo spans/s, bytes/s, lỗi và chi phí backend.

Không chọn sampling probability chỉ theo cảm giác. Tính trace volume dự kiến, thử tải và kiểm tra rằng tỷ lệ thấp vẫn giữ đủ traces để điều tra các luồng quan trọng.

### Giữ metrics cho SLO, dùng traces để chẩn đoán

Không giảm metrics collection chỉ vì trace ingest cao. Metrics có cardinality thấp có thể cung cấp request rate, error rate và latency cho toàn traffic. Traces cung cấp chi tiết call path cho một phần traffic được lấy mẫu.

## 14. Giảm chi phí span payload

1. Không tạo span cho mọi method nội bộ nếu không tạo giá trị điều tra.
2. Giữ attributes ổn định, ngắn và có giới hạn.
3. Không ghi request/response body hoặc toàn bộ payload event.
4. Tránh lặp cùng một thông tin ở resource, span và event.
5. Ghi exception ở nơi có giá trị nhất; tránh nhân bản stack trace trên mọi span.
6. Đặt giới hạn số attributes/events/links theo SDK.
7. Dùng sampling phù hợp, không drop errors một cách mù quáng.
8. Dùng compression/batching khi pipeline hỗ trợ và đo CPU/network tradeoff.

Với Spring Modulith, module spans nên giúp nhận diện module boundary và latency contribution. Nếu một module gọi hàng chục method nội bộ, không nhất thiết tạo span cho từng method. Hãy giữ mức chi tiết vừa đủ để biết module nào chậm và operation nào thất bại.

## 15. Đo chi phí thực tế

Trước và sau mỗi thay đổi, ghi lại:

| Chỉ số | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| Active metric series | series | Quy mô metrics đang ingest |
| Samples ingested | samples/s hoặc samples/day | Tải metrics |
| Metric export duration | ms | Thời gian export mỗi batch/step |
| Span creation rate | spans/s | Tải instrumentation |
| Sampled trace rate | traces/s | Tỷ lệ trace được giữ |
| Span payload size | bytes/span | Kích thước trung bình |
| Export queue utilization | % | Mức sử dụng queue |
| Dropped/refused telemetry | records/s | Dữ liệu mất hoặc bị từ chối |
| Collector CPU/memory | % / MiB | Tải Collector |
| Backend ingest bytes | MiB/s hoặc GiB/day | Chi phí ingest |
| Storage growth | GiB/day | Tốc độ tăng dung lượng |
| Query latency | ms | Chi phí và hiệu năng truy vấn |

### Dashboard chi phí tối thiểu

Tạo dashboard gồm active series theo service/module/metric family; samples/s và ingest bytes/s; spans/s, traces/s và sampled ratio; export latency và batch size; SDK queue size/drop counter nếu được expose; Collector queue size/capacity; Collector refused/enqueue failed/send failed; backend ingestion quota và storage growth; CPU/heap/GC của application và Collector.

Không dùng high-cardinality labels để tạo dashboard chi phí. Group theo service, environment, signal, exporter và component có tập giá trị hữu hạn.

## 16. Benchmark: tìm cấu hình có chi phí phù hợp

Một benchmark tốt phải giữ workload ổn định và thay đổi từng tham số:

1. Chọn kịch bản đại diện: HTTP request đơn giản, request qua nhiều module, event listener async và lỗi downstream.
2. Chạy baseline không thay đổi telemetry.
3. Bật metrics và traces với cấu hình hiện tại.
4. Ghi CPU, heap, GC, request latency, throughput, active series, spans/s và bytes/s.
5. Thay đổi một tham số: scrape interval, export step, sampling, batch size hoặc attribute set.
6. Chạy cùng workload và thời lượng.
7. So sánh p50/p95/p99 latency, CPU, heap, export failures, queue utilization và backend ingest.
8. Kiểm tra chất lượng điều tra: có tìm được trace lỗi, module chậm và event listener không?
9. Lặp lại ở mức tải bình thường, peak và burst.
10. Chọn cấu hình đáp ứng SLO và ngân sách, sau đó kiểm chứng trên staging/canary.

### Bảng benchmark mẫu

| Kịch bản | Sampling | Active series | Spans/s | App CPU | Heap delta | Backend ingest | Dropped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 0% | … | 0 | … | … | … | … |
| Metrics only | 0% | … | 0 | … | … | … | … |
| Traces 10% | 10% | … | … | … | … | … | … |
| Traces 25% | 25% | … | … | … | … | … | … |
| Traces 100% | 100% | … | … | … | … | … | … |

Không dùng baseline 0% tracing để kết luận tracing luôn có overhead cố định; overhead phụ thuộc số spans/request, attributes, exporter và batch behavior.

## 17. Tối ưu theo thứ tự ưu tiên

Khi chi phí vượt ngân sách, xử lý theo thứ tự:

1. **Cardinality:** loại tag không giới hạn, chuẩn hóa URI, giới hạn event/module labels.
2. **Meter scope:** bỏ meter trùng lặp hoặc instrumentation không có consumer.
3. **Histogram:** giảm buckets hoặc chỉ bật cho latency metrics quan trọng.
4. **Scrape/export interval:** tăng interval nếu độ phân giải hiện tại vượt nhu cầu.
5. **Trace sampling:** giảm head sampling hoặc dùng tail sampling theo mục tiêu.
6. **Span payload:** bỏ attributes/events dư thừa và giới hạn kích thước.
7. **Batch/compression:** đo batch size, flush timeout và compression.
8. **Collector topology:** tách workload, scale đúng tier hoặc dùng persistent queue khi cần.
9. **Backend retention/query:** điều chỉnh retention và dashboard queries theo yêu cầu.

Đừng tăng Collector replicas trước khi xác định backend có đang là bottleneck hay không. Nếu queue tăng vì backend ingest chậm, thêm Collector có thể chỉ đẩy nhiều dữ liệu hơn vào backend đã quá tải.

## 18. Theo dõi Collector và backpressure

Collector scaling guide khuyến nghị quan sát queue size/capacity, refused telemetry và thời gian scrape. Queue thường được xem là cần chú ý khi tiến gần 60–70% capacity trong workload ổn định; đây là ngưỡng tham khảo, không phải SLA chung cho mọi pipeline.

Ví dụ PromQL:

~~~promql
100 *
otelcol_exporter_queue_size
/
otelcol_exporter_queue_capacity
~~~

Theo dõi số spans bị từ chối:

~~~promql
rate(otelcol_processor_refused_spans[5m])
~~~

Theo dõi số spans export thất bại:

~~~promql
rate(otelcol_exporter_send_failed_spans[5m])
~~~

Metric names và stability level có thể thay đổi theo Collector version/distribution. Xác nhận exposition của Collector trước khi dùng rule. Nếu metric không được expose ở mức telemetry hiện tại, bật internal telemetry phù hợp.

## 19. Những đánh đổi không nên bỏ qua

| Tối ưu | Lợi ích | Rủi ro |
| --- | --- | --- |
| Tăng scrape interval | Giảm samples và scrape load | Mất độ phân giải, bỏ lỡ spike ngắn |
| Giảm histogram buckets | Giảm series | Phân vị/latency distribution kém chính xác |
| Giảm trace sampling | Giảm spans và ingest | Có thể bỏ lỡ trace lỗi |
| Giảm span attributes | Giảm payload và indexing | Thiếu context khi điều tra |
| Tăng batch size | Giảm request overhead, tăng compression | Tăng memory và export delay |
| Tăng queue size | Chịu burst/outage lâu hơn | Tăng memory/disk, chỉ trì hoãn drop |
| Giảm retention | Giảm storage | Mất lịch sử điều tra dài hạn |
| Drop telemetry tại Collector | Giảm backend ingest | Mất dữ liệu trước khi đến backend |

Khi drop dữ liệu, ghi rõ signal nào bị loại, ở processor nào, theo điều kiện nào và ai phê duyệt. Không drop error spans hoặc event failure metrics một cách vô tình chỉ để giảm chi phí.

## 20. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Heap ứng dụng tăng theo traffic | High-cardinality tags tạo nhiều Meter | Chuẩn hóa tags, dùng MeterFilter và detector |
| Backend metrics ingest tăng nhanh | Series count hoặc scrape frequency tăng | Đếm active series, xem tag combinations và interval |
| Một histogram tạo nhiều series | Quá nhiều buckets × tag combinations | Chỉ bật histogram cho meter cần thiết |
| Traces ingest cao | Sampling cao, nhiều spans/request hoặc span payload lớn | Đo spans/request và giảm payload/sampling có kiểm soát |
| Exporter queue liên tục đầy | Backend/network chậm hoặc queue nhỏ hơn burst | Tìm bottleneck, đo send failures, điều chỉnh queue theo memory |
| Tăng Collector replicas nhưng backlog không giảm | Backend ingest là bottleneck | Scale backend hoặc giảm ingest có kiểm soát |
| Traces mất khi Collector restart | Chỉ dùng in-memory queue | Xem xét persistent queue/WAL và disk budget |
| Dashboard latency thiếu dữ liệu | Sampling trace bị dùng làm metric nguồn | Dùng metrics toàn traffic cho SLO |
| Metrics bị gửi hai lần | Nhiều registry/exporter cùng hoạt động | Inventory registry và disable exporter không cần |
| Batch lớn nhưng latency export tăng | Flush timeout/size quá cao | Đo batch size và thời gian chờ |
| Queue lớn nhưng vẫn drop khi outage dài | Retry duration hoặc outage vượt buffer window | Tính buffer time, retry policy và persistence |
| Collector CPU tăng sau sampling | Sampling đặt sai thứ tự hoặc xử lý trước drop | Đặt processor theo pipeline/version và đo lại |

## 21. Bài thực hành

Chuẩn bị ứng dụng Spring Modulith có module order, inventory và billing, Actuator, Micrometer và OpenTelemetry exporter.

1. Export danh sách meter và Prometheus scrape baseline.
2. Đếm active series theo metric family và tag combinations.
3. Chọn một histogram, ghi số bucket và series count trước/sau.
4. Gửi workload cố định và đo samples/day theo scrape interval 15 giây.
5. Chuyển interval sang 30 hoặc 60 giây, đo mức giảm và tác động dashboard.
6. Đo requests/s, spans/request và average span payload.
7. Tính spans/day ở sampling 100%, 25%, 10% và 5%.
8. Bật module spans và so sánh chi phí với trace chỉ có HTTP/database spans.
9. Tăng batch size hoặc schedule delay trong staging; ghi CPU, heap, export latency và queue.
10. Tạo một tình huống Collector/backend chậm trong môi trường test; quan sát queue, retry và dropped/refused telemetry.
11. Thử thêm tag có nhiều giá trị trong test; xác nhận detector/MeterFilter phát hiện hoặc giới hạn.
12. Chọn cấu hình phù hợp với SLO và ghi lại lý do giữ/bỏ từng signal.

Mẫu ghi kết quả:

| Cấu hình | Samples/day | Spans/day | Export bytes/day | App CPU | Collector memory | Dropped telemetry | Đạt SLO? |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Baseline | … | … | … | … | … | … | … |
| Interval 30s | … | … | … | … | … | … | … |
| Sampling 10% | … | … | … | … | … | … | … |
| Reduced attributes | … | … | … | … | … | … | … |
| Tuned batch/queue | … | … | … | … | … | … | … |

### Câu hỏi tự kiểm tra

1. Vì sao số meter không bằng số time series được backend lưu?
2. Scrape interval ảnh hưởng samples/day như thế nào?
3. Histogram buckets nhân với tag combinations làm tăng cardinality ra sao?
4. Vì sao order ID và trace ID không phù hợp làm metric tags?
5. Khác biệt giữa Prometheus pull và Micrometer OTLP push là gì?
6. Vì sao giảm trace sampling không tự động giảm metrics?
7. Batch size lớn có thể giảm network overhead nhưng làm tăng chi phí nào?
8. Queue đầy ở SDK khác queue đầy ở Collector như thế nào?
9. Khi nào tăng Collector replicas không giải quyết được backlog?
10. Vì sao tail sampling cần nhận candidate traces trước khi quyết định giữ/bỏ?

## 22. Tổng kết

Chi phí export metrics và traces phụ thuộc vào toàn bộ đường đi từ instrumentation trong ứng dụng tới backend. Metrics thường chịu ảnh hưởng lớn bởi active series, cardinality, histogram buckets và scrape/export interval. Traces chịu ảnh hưởng bởi request rate, spans/request, sampling ratio và kích thước span. Cả hai còn tiêu thụ CPU, memory, network, Collector capacity, backend ingestion và storage.

Hãy đo active series, samples/s, spans/s, payload bytes, queue utilization và dropped telemetry trước khi tối ưu. Giảm cardinality và meter không cần thiết trước; sau đó điều chỉnh histogram, interval, sampling, span payload, batch và queue. Đảm bảo metrics vẫn phản ánh toàn traffic cho SLO, traces vẫn đủ để điều tra lỗi, và mọi thay đổi có benchmark chứng minh chi phí giảm mà chất lượng vận hành vẫn đạt yêu cầu.

## Tài liệu tham khảo

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html).
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).
- [OpenTelemetry — SDK Configuration Types](https://opentelemetry.io/docs/specs/otel/configuration/types/).
- [OpenTelemetry — Collector Resiliency](https://opentelemetry.io/docs/collector/resiliency/).
- [OpenTelemetry — Scaling the Collector](https://opentelemetry.io/docs/collector/scaling/).
- [OpenTelemetry — Deprecating the Collector Batch Processor (November 2026)](https://opentelemetry.io/blog/2026/collector-batching-migration/).
- [Prometheus — Storage](https://prometheus.io/docs/prometheus/latest/storage/).
