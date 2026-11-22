# Sampling cho lưu lượng lớn

Một ứng dụng Spring Kafka có thể xử lý hàng nghìn đến hàng trăm nghìn message mỗi giây. Nếu tạo và xuất toàn bộ distributed traces của mọi record, mỗi lần gửi Kafka, mỗi lần nhận, mỗi truy vấn database và mọi lời gọi HTTP, hệ thống observability có thể phải tiếp nhận một lượng span khổng lồ. Kết quả là chi phí lưu trữ tăng, collector hoặc exporter quá tải, và chính telemetry trở thành nguồn gây áp lực cho dịch vụ nghiệp vụ.

**Sampling cho lưu lượng lớn** là chính sách chọn một phần trace để ghi nhận, truyền đi hoặc lưu trữ mà vẫn giữ khả năng điều tra sự cố. Trong Spring Kafka Reliability Operations, sampling cần được đặt trong ngữ cảnh **Micrometer Observation, distributed tracing, Kafka header propagation, retry/DLT và các tín hiệu vận hành không được phép mất**.

Nguyên tắc quan trọng nhất: **giảm số trace được lưu không có nghĩa giảm độ chính xác của các metric vận hành cốt lõi**. Consumer lag, số record đã xử lý, số lỗi, tốc độ DLT, latency và tình trạng rebalance cần được giám sát riêng, không được chỉ tính bằng cách đếm một tập trace đã sampling.

## 1. Vì sao Kafka workload cần chính sách sampling?

Xét một pipeline điển hình:

```text
HTTP request / batch job
          |
          v
Spring service + KafkaTemplate.send()
          |
          v
Kafka topic orders
          |
          v
Spring @KafkaListener
          |
          +--> PostgreSQL
          +--> Inventory HTTP API
          +--> KafkaTemplate.send("orders-result")
          |
          v
Downstream listeners
```

Một sự kiện đơn hàng có thể sinh nhiều span: span nhận HTTP request, span gửi Kafka, span xử lý listener, các span client DB/HTTP và span phát Kafka downstream. Một record **không tương đương một span**; một sự kiện còn có thể được xử lý lại khi retry, rebalance, restart hoặc replay DLT.

Nếu pipeline nhận 5.000 event/giây, mỗi event tạo trung bình bốn span và tất cả spans được xuất, lượng phát sinh sơ bộ là 20.000 spans/giây. Một ngày có khoảng **1,728 tỷ span**, chưa kể lỗi/retry. Chính sách giữ lại 1% trace có thể giảm đáng kể lượng span được lưu, nhưng lượng giảm thực tế phụ thuộc nơi sampling diễn ra, kích thước trace và việc trace có được kế thừa sampling decision xuyên service hay không.

Không chọn sampling rate theo cảm tính. Hãy bắt đầu bằng throughput, số span trung bình của một trace, dung lượng/chi phí mỗi span, thời gian retention, mức độ quan trọng của các luồng nghiệp vụ và yêu cầu điều tra lỗi hiếm.

## 2. Phân biệt Observation, span, trace và metrics

**Micrometer Observation** là một abstraction cho phép đo một operation và thông báo cho các observation handlers. Tùy cấu hình, cùng một observation có thể đóng góp vào metrics và tracing:

| Thành phần | Nhiệm vụ | Cách liên quan tới sampling |
|---|---|---|
| Observation | Biểu diễn thao tác đã quan sát, ví dụ listener xử lý record | Vẫn có thể được tạo và đo dù trace không được xuất |
| Span | Đơn vị công việc trong distributed trace | Có thể được record hoặc bỏ qua theo tracing sampler |
| Trace | Tập span liên kết bằng trace context | Thường là đơn vị hợp lý để quyết định sampling |
| Micrometer timer/counter | Đo số lần, duration, kết quả xử lý | Không nên bị suy giảm chỉ vì trace sampling |
| Kafka client/broker metrics | Đo fetch, poll, lag, rebalance, bytes, request | Là nguồn monitoring riêng, không dựa vào trace sample |
| Log / audit | Diễn giải sự kiện và trạng thái nghiệp vụ | Có chính sách lọc/retention riêng; không phải cứ trace bị drop thì mọi log bị drop |

Một `@KafkaListener` xử lý thành công 100.000 record vẫn phải được phản ánh bằng metrics và committed offsets tương ứng, kể cả khi sampling chỉ giữ lại trace của khoảng 1.000 record. Nếu dashboard lấy tổng số trace làm tổng số record, số liệu sẽ bị lệch vì một trace có thể bao phủ nhiều record hoặc một event có thể có nhiều lần xử lý.

**Trace sampling khác metric tag cardinality.** Giảm tracing từ 100% xuống 1% không giải quyết được việc gắn `orderId` hoặc `eventId` vào metric tags. Hai loại chi phí phải được quản lý bằng hai chính sách độc lập.

## 3. Các chiến lược sampling chính

| Chiến lược | Thời điểm quyết định | Ưu điểm | Điểm đánh đổi |
|---|---|---|---|
| Head-based probabilistic | Khi trace bắt đầu hoặc span root được tạo | Giảm overhead sớm, tiết kiệm CPU/network/exporter | Có thể bỏ lỡ lỗi hiếm phát sinh sau đó |
| Parent-based | Khi một span con nhận trace context từ upstream | Giữ quyết định sampling nhất quán theo trace | Phụ thuộc propagation và chính sách của upstream |
| Rules-based / priority | Theo thuộc tính hoặc loại workload có sẵn tại thời điểm quyết định | Giữ nhiều hơn cho luồng quan trọng | Dễ thiên lệch; high-cardinality và chính sách phức tạp |
| Tail-based | Khi collector đã nhận đủ hoặc chờ một phần trace | Có thể ưu tiên lỗi, latency cao, DLT path | Collector phải nhận và giữ nhiều spans trước khi quyết định |
| Adaptive / rate-limited | Điều chỉnh theo tải, ngân sách hoặc throughput | Duy trì chi phí dưới giới hạn khi traffic tăng | Khó diễn giải tỷ lệ đại diện; cần metrics và audit rõ |

Trong một hệ thống lớn, có thể kết hợp nhiều tầng: head sampling tỷ lệ phù hợp để giảm tải SDK, policy theo service ở collector và giới hạn lưu trữ backend. Nhưng nếu head sampler **đã bỏ một trace**, tail sampler ở collector **không thể khôi phục các spans chưa từng được export**. Đặc biệt, đừng quảng cáo “giữ 100% lỗi” ở collector khi SDK đã bỏ phần lớn trace lỗi trước khi nhìn thấy trạng thái cuối.

## 4. Head-based probabilistic sampling hoạt động thế nào?

Với xác suất lấy mẫu `p = 0.01`, khoảng 1% những **trace mới** có thể được chọn để record/export. Quyết định thường được tính lúc bắt đầu trace, có thể dựa trên trace ID hoặc thuật toán sampler của SDK để tránh random lại ở từng span.

```text
100.000 Kafka records
       |
       v
Tracing SDK áp dụng sampling probability ~1%
       |
       +--> phần lớn trace không được xuất
       |
       +--> các trace được chọn
                    |
                    v
             span producer / consumer / DB / HTTP
                    |
                    v
              Collector + trace backend
```

Đây là sơ đồ khái niệm: con số record được chọn **không luôn đúng bằng 1% số record** vì một trace có thể chứa nhiều record, các trace có độ dài khác nhau, và upstream có thể quyết định sampling trước consumer. Sampling ngẫu nhiên là một phép ước lượng phân phối; trong một cửa sổ ngắn, tỷ lệ thực tế có thể khác 1%.

Ưu điểm là giảm lưu lượng telemetry rất sớm. Nhược điểm là tại thời điểm bắt đầu một trace, hệ thống chưa biết record sẽ thất bại, latency có vượt SLO hay không hoặc DLT có được publish hay không.

## 5. Parent-based sampling và bối cảnh Kafka bất đồng bộ

Trong distributed tracing, span thường kế thừa **trace context** từ hoạt động upstream. Với HTTP, context có thể đi qua headers. Với Kafka, framework/bridge có thể truyền context qua **record headers** khi producer và consumer Observation/tracing được cấu hình phù hợp.

```text
Service A: HTTP POST /orders
   traceId = T1, sampled = true
        |
        v
KafkaTemplate gửi orders (tracing headers)
        |
        v
Kafka broker lưu record + headers
        |
        v
Service B: @KafkaListener nhận record
   đọc trace context upstream
   áp dụng parent-based sampling
        |
        v
Service C / database spans có thể cùng trace T1
```

Nếu parent context được propagate đúng và sampler có policy parent-based, các span con thường tôn trọng quyết định đã có. Một trace được chọn ở upstream có cơ hội giữ liên tục qua producer, Kafka consumer và downstream. Một trace đã được đánh dấu không sampled cũng thường không tự “bật lại” ở mỗi service.

Với Kafka, cần thận trọng: record có thể được xử lý lâu sau khi producer span kết thúc, có thể được retry ở topic khác, và một batch listener có thể chứa **nhiều records với nhiều trace contexts**. Cách Spring Kafka tạo/tiếp nối observation và parent/span links phải được xác minh theo phiên bản và instrumentation. Không tự giả định toàn bộ batch thuộc một trace duy nhất.

Nếu một service không truyền hoặc không đọc tracing headers, consumer có thể bắt đầu một trace root mới rồi ra quyết định sampling khác. Điều này làm trace xuyên service bị đứt hoặc rời rạc, ngay cả khi mỗi service đều báo “đã bật tracing”.

## 6. Bật Observation cho Spring Kafka listener

Với Spring Kafka dùng Micrometer Observation, có thể bật bằng `ContainerProperties` trên đúng listener container factory:

```java
@Configuration
public class OrdersKafkaObservabilityConfig {

    @Bean("ordersKafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties().setObservationEnabled(true);

        return factory;
    }
}
```

Listener dùng factory này:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
```

`OrderEvent` và `orderService` là thành phần minh họa. ConsumerFactory cần deserializer, broker properties và security tương ứng. Cấu hình `observationEnabled=true` bật cơ chế Observation ở container phiên bản hỗ trợ; **nó không mặc nhiên đặt tỷ lệ sampling** và cũng không tự cung cấp exporter/collector.

Nếu cùng ứng dụng có nhiều container factories, phải bật Observation trên **factory được listener thực tế sử dụng**. Bật trên một bean khác không tạo tracing cho listener đang chạy. Khi chạy batch listener, cần kiểm tra behavior của Observation trong phiên bản Spring Kafka cụ thể; không mặc định nhận một span độc lập cho mỗi record trong batch.

## 7. Bật Observation cho Kafka producer

Để context tracing đi từ producer qua Kafka tới consumer, phía gửi cũng cần instrumentation tương ứng. `KafkaTemplate` hỗ trợ Observation trong các phiên bản Spring Kafka có tính năng này:

```java
@Bean
KafkaTemplate<String, OrderEvent> observedKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);
    return template;
}
```

Khi có `ObservationRegistry`, tracing handlers và propagator phù hợp, Spring Kafka có thể tạo producer observations và truyền trace context qua Kafka record headers. Đường truyền thực tế phụ thuộc các thư viện Micrometer Tracing/OpenTelemetry/Brave, cấu hình propagation và framework version.

Không tự sao chép nguyên bộ Kafka headers mà không hiểu nguồn dữ liệu. Khi replay từ DLT hoặc transform record, cần quyết định chính sách giữ trace context, business correlation ID và provenance. Header `traceparent` hoặc định dạng propagation khác **không phải khóa idempotency nghiệp vụ**; nó chỉ là dữ liệu hỗ trợ liên kết telemetry.

Nếu pipeline dùng Kafka transaction, một producer span ghi nhận `send()` thành công không nhất thiết chứng minh transaction đã commit. Hãy kết hợp telemetry với transaction outcome và `read_committed` consumer khi cần đảm bảo chỉ quan sát dữ liệu committed về mặt xử lý nghiệp vụ.

## 8. Cấu hình sampling probability trong Spring Boot

Với các phiên bản Spring Boot hỗ trợ Micrometer Tracing và thuộc tính sampling này, có thể cấu hình một tỷ lệ lấy mẫu chung:

```yaml
management:
  tracing:
    sampling:
      probability: 0.01
```

Giá trị `0.01` tương ứng **khoảng 1% trace roots mới**, không phải 1% Kafka partitions hay 1% số bản ghi được commit. Một số môi trường dùng property tương đương trong `.properties`:

```properties
management.tracing.sampling.probability=0.01
```

Tính năng này cần stack tracing phù hợp với phiên bản Spring Boot: Micrometer Observation/Tracing, bridge đến Brave hoặc OpenTelemetry và exporter backend được cấu hình. **Không nhầm property này với `management.metrics.*`**, vì metrics và traces là hai kênh telemetry khác nhau.

`management.tracing.sampling.probability` chủ yếu điều khiển việc lấy mẫu tại tracing layer được Boot tự cấu hình. Nếu đã cung cấp custom tracer, sampler, OpenTelemetry SDK hoặc agent riêng, cấu hình ấy có thể được xử lý khác hoặc không còn là nguồn duy nhất. Cần xác minh **effective sampler** ở runtime, nhất là khi có Java agent và SDK auto-configuration đồng thời.

Các service downstream nhận parent context có thể kế thừa quyết định upstream. Do đó đặt `0.01` trên service B không có nghĩa service B luôn giảm đúng 99% traces nếu nhiều parent đã được chọn từ service A với tỷ lệ khác.

## 9. Ví dụ cấu hình OpenTelemetry SDK sampler

Nếu ứng dụng chủ động cấu hình OpenTelemetry SDK thay vì dựa hoàn toàn vào Spring Boot auto-configuration, một chiến lược thường gặp là **parent-based trace ID ratio sampling**:

```java
import io.opentelemetry.sdk.trace.samplers.Sampler;

Sampler sampler = Sampler.parentBased(
        Sampler.traceIdRatioBased(0.01));
```

Ý nghĩa: nếu span có parent context, sampler tham chiếu quyết định của parent; nếu là root mới, lấy mẫu theo tỷ lệ khoảng 1%. Đây là **đoạn xây một đối tượng sampler**, không phải bean tự động áp dụng cho Spring Kafka bằng cách copy vào bất kỳ class nào. Để có hiệu lực, sampler phải được gắn vào chính `SdkTracerProvider`/SDK đang được ứng dụng và instrumentation sử dụng.

Một cấu hình SDK thay thế hoàn toàn auto-config có thể ảnh hưởng exporter, propagation, resource attributes, shutdown và OpenTelemetry bridge. Trong production, ưu tiên một nguồn cấu hình tracing nhất quán, tránh để Spring Boot và Java agent tạo hai SDK hoặc hai bộ exporter trùng nhau.

Không nên gắn sampler với business ID mà không cân nhắc quyền riêng tư và tính ổn định. Sampling theo trace ID đã được phân phối đồng đều thường phù hợp hơn việc lấy hash của `customerId` rồi khiến một nhóm khách hàng luôn được trace còn nhóm khác không bao giờ được quan sát.

## 10. Tính ngân sách sampling từ throughput thực tế

Ước lượng sơ bộ có thể bắt đầu từ:

```text
spans/giây xuất ≈ traces root mới/giây
                 × sampling probability
                 × spans trung bình / trace được chọn

spans/ngày ≈ spans/giây xuất × 86.400
```

Ví dụ minh họa, giả sử ứng dụng tạo khoảng 5.000 trace roots mới/giây, mỗi trace có trung bình 4 span:

| Sampling probability | Trace roots được lấy mẫu/giây (kỳ vọng) | Spans/giây (ước lượng) | Spans/ngày (ước lượng) |
|---:|---:|---:|---:|
| 100% | 5.000 | 20.000 | 1.728.000.000 |
| 10% | 500 | 2.000 | 172.800.000 |
| 1% | 50 | 200 | 17.280.000 |
| 0,1% | 5 | 20 | 1.728.000 |

Đây chỉ là phép tính năng lực giả định, không phải số liệu từ một cluster thật. Kafka record có thể không ánh xạ 1:1 với trace root, spans/trace thay đổi theo fan-out và lỗi, và các trace được kế thừa parent có thể được chọn ở upstream. Muốn lập budget chính xác cần đo **actual exported spans per second**, kích thước span và retention của backend.

Tỷ lệ 1% vẫn có thể tạo **17,28 triệu span/ngày** theo giả định trên. Vì vậy, “chỉ lấy 1%” chưa hẳn rẻ với lưu lượng lớn. Ngược lại, giảm xuống 0,1% có thể khiến việc tìm lỗi hiếm trở nên rất khó. Hãy dựa vào SLO, chi phí và khả năng điều tra để chọn chính sách hợp lý.

## 11. Đừng dùng trace sampling để tính số lỗi thực

Giả sử hệ thống có 1.000.000 record, trong đó 100 record bị lỗi nghiệp vụ. Nếu sampling ngẫu nhiên 1%, số trace lỗi được giữ **kỳ vọng** chỉ khoảng một; hoàn toàn có khả năng không thấy trace lỗi nào dù lỗi thực sự tồn tại.

```text
1.000.000 records
     |
     +--> 999.900 thành công
     |
     +--> 100 thất bại

Trace sampling 1%:
  số trace lỗi được giữ có thể là 0, 1, 2, ...
```

Do đó, **error rate, retry count, DLT publish success/failure, consumer lag và latency SLO phải dùng metrics có độ bao phủ đầy đủ**. Trace cung cấp chi tiết nguyên nhân cho một **mẫu** giao dịch, không phải hệ thống kế toán số lượng record chính xác.

Các counters hữu ích có thể là:

- `app.kafka.records.processed` theo pipeline, outcome và reason có số giá trị hữu hạn.
- `app.kafka.retry.attempts` theo listener/error category.
- `app.kafka.dlt.published` và `app.kafka.dlt.publish_failed`.
- Kafka consumer group lag, rebalance count, poll/commit errors.
- Listener processing duration histogram để tính p95/p99 theo pipeline.

Không đưa `record.key`, Kafka offset, request ID, exception message hoặc payload JSON vào metrics tags. Sampling rate thấp **không giảm** cardinality của các metric được gắn nhãn theo từng message.

## 12. Ưu tiên lỗi và latency cao: head sampling có giới hạn

Một sampling policy theo lỗi có vẻ hấp dẫn: “giữ toàn bộ trace thất bại, bỏ phần lớn trace thành công”. Nhưng tại thời điểm **head sampling**, listener chưa chạy xong và chưa biết kết quả. Không thể yêu cầu head sampler dự đoán tương lai dựa trên exception xảy ra vài giây sau.

Có thể tăng sampling cho các luồng **đã biết trước là quan trọng**, ví dụ service xử lý thanh toán, workflow settlement hoặc một topic recovery. Nhưng sampling theo nghiệp vụ ở mức SDK cần khả năng nhận biết thuộc tính cần thiết **trước** quyết định sampling và kiểm soát số chính sách. Với Kafka, topic name hoặc headers có thể được biết ở consumer boundary; root trace có thể đã được tạo tại producer upstream nên chính sách consumer không nhất thiết được quyền quyết định lại.

Nếu yêu cầu là giữ trace khi **status=ERROR** hoặc khi **latency vượt ngưỡng**, tail-based sampling tại collector thường phù hợp hơn về mặt chức năng. Đổi lại, toàn bộ dữ liệu span đầu vào phải đến được điểm ra quyết định tail sampling; không thể có độ đầy đủ 100% lỗi nếu upstream đã drop phần lớn trace.

## 13. Tail-based sampling tại OpenTelemetry Collector

**Tail sampling** hoãn quyết định đến khi collector đã nhận span của một trace trong một khoảng chờ. Nó có thể chọn trace theo điều kiện như có span lỗi, latency cao hoặc một tỷ lệ baseline ngẫu nhiên.

```text
Spring Kafka services (đủ span được export)
                 |
                 v
       OpenTelemetry Collector
                 |
          gom theo trace ID
                 |
        chờ/quan sát trace
                 |
        +--------+---------+
        |                  |
     trace ERROR       trace bình thường
        |                  |
      giữ lại       giữ tỷ lệ nhỏ (ví dụ 2%)
                 |
                 v
              Trace backend
```

Một ví dụ cấu hình **minh họa** cho `tail_sampling` processor của OpenTelemetry Collector phiên bản có hỗ trợ tính năng này:

```yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 2048
    spike_limit_mib: 512

  tail_sampling:
    decision_wait: 15s
    num_traces: 50000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 2

  batch: {}
```

Đây là **trích đoạn processor**, không phải file Collector đầy đủ. Một cấu hình chạy được còn cần `receivers`, `exporters`, `service.pipelines.traces` và security/network settings. Hỗ trợ processor và policy cần được xác nhận theo bản OpenTelemetry Collector/Collector Contrib đang triển khai. Các tham số `decision_wait` và `num_traces` phải được sizing theo số trace root/giây, fan-out, memory và thời gian trace thực tế.

Nếu một số spans đến muộn hơn quyết định tail sampling, trace có thể bị thiếu đoạn hoặc phát sinh xử lý late spans tùy phiên bản. Nếu một hệ thống có nhiều collector replicas, các spans của cùng trace ID cần được định tuyến nhất quán tới nơi ra quyết định hoặc dùng kiến trúc load balancing phù hợp; nếu spans bị chia tản mát, policy có thể không thấy toàn bộ dấu hiệu lỗi của trace.

**Chú ý:** chính sách `status_code=ERROR` chỉ hoạt động khi instrumentation thực sự đánh dấu span status là ERROR. Một business error được bắt rồi xử lý thành kết quả hợp lệ có thể không được đánh dấu ERROR. DLT publishing thành công cũng không đồng nghĩa span listener được đánh dấu thất bại. Muốn policy đúng, cần xác định semantics của error status trong instrumentation.

## 14. Head và tail sampling: chọn phương án theo chi phí

| Yêu cầu | Head-based | Tail-based |
|---|---|---|
| Giảm CPU/network telemetry ngay tại ứng dụng | Tốt | Không; ứng dụng thường vẫn xuất spans đầu vào collector |
| Giữ trace khi kết quả cuối cùng là lỗi | Không bảo đảm | Khả thi nếu toàn bộ spans liên quan đến collector |
| Giữ trace latency cao | Hạn chế khi chưa biết latency lúc bắt đầu | Khả thi với policy và decision window phù hợp |
| Collector memory requirements | Tương đối thấp | Có thể cao do giữ trace tạm thời |
| Vận hành multi-replica collector | Đơn giản hơn | Cần route/aggregate theo trace ID |
| Tính nhất quán giữa các service | Cần propagation + parent-based | Cần trace ID và spans đến đủ để quyết định |
| Tính đầy đủ khi upstream đã sample drop | Không thể phục hồi traces đã drop | Cũng không thể phục hồi traces không đến collector |

Một kiến trúc thực tế có thể dùng head-based sampling trên luồng bình thường để tiết kiệm telemetry ngay từ đầu, còn các luồng quan trọng hoặc môi trường điều tra chuyên dụng xuất đủ spans để tail sampling chọn lỗi và latency cao. Khi phối hợp, phải nêu rõ **lớp nào có khả năng nhìn thấy trace nào**; đừng khẳng định hệ thống giữ mọi lỗi nếu thực tế có một sampler upstream loại bỏ trước đó.

## 15. Kafka retry, DLT và sampling decision

Spring Kafka có thể xử lý record nhiều lần: retry trong `DefaultErrorHandler`, chuyển sang retry topic qua `@RetryableTopic`, rồi publish sang Dead Letter Topic (DLT). Một sự kiện nghiệp vụ có thể trải qua nhiều lần delivery và nhiều listener spans.

```text
orders
   |
   v
@KafkaListener (attempt 1) -> lỗi
   |
   v
orders-retry (attempt 2) -> lỗi
   |
   v
orders.DLT
   |
   v
Replay có kiểm soát -> orders (lần xử lý khác)
```

Khi record được publish sang retry/DLT topic, metadata tracing có thể được sao chép, bổ sung hoặc thay đổi tùy recoverer, serializer/header mapper và Spring Kafka version. Không giả định context sẽ tự được giữ nguyên ở mọi topology. Nếu header tracing được bảo toàn và Observation đang bật đúng cách, các lần xử lý có thể liên kết với trace gốc hoặc tạo trace/span quan hệ mới theo semantics instrumentation.

Về mặt vận hành cần **hai loại định danh**:

- **Trace/correlation identity:** phục vụ quan sát một đường xử lý, có thể thay đổi khi replay hoặc khi context không được propagate.
- **Stable business event ID:** phục vụ idempotency, audit, phân biệt record gốc và các lần retry/replay; không dùng trace ID làm khóa xử lý đúng một lần.

Nếu chính sách sampling bỏ trace của event gốc, có thể chỉ còn logs/metrics khi sự kiện đến DLT. Vì vậy, DLT cần giữ original topic/partition/offset, exception class, business event ID và retry metadata đủ để điều tra **ngay cả khi không có trace**. Tracing là công cụ chẩn đoán bổ sung, không phải nguồn bằng chứng duy nhất.

## 16. Khi một lỗi hiếm xảy ra nhưng trace bị sampling bỏ

Một sự cố chỉ xảy ra một lần trong hàng triệu record vẫn phải có khả năng điều tra tối thiểu qua:

1. **Structured log** chứa event ID, topic, partition, offset, listener ID, error category, correlation ID theo chính sách bảo mật.
2. **DLT/quarantine** giữ record thất bại cùng provenance và chính sách retention phù hợp.
3. **Metrics có độ bao phủ đầy đủ** cho failure count, timeout, retry attempts và DLT publish results.
4. **Audit nghiệp vụ** hoặc inbox/outbox records khi side effect quan trọng.
5. **On-demand diagnostic sampling** hoặc môi trường replay có kiểm soát để tái hiện trace ở tỷ lệ cao hơn khi cần.

Đừng tăng sampling lên 100% toàn hệ thống ngay khi thấy một lỗi lẻ nếu traffic cực lớn. Một thay đổi global có thể làm exporter/collector quá tải đúng lúc incident. Tốt hơn nên có chế độ điều tra theo service, tenant đã được phép hoặc một tập event đã xác định, với **thời hạn và rate limit rõ ràng**.

Nếu muốn sampling 100% cho các lần replay có kiểm soát, tránh copy nguyên payload nhạy cảm vào span attributes. Sampled trace vẫn phải tuân thủ data minimization và access control.

## 17. Cardinality: sampling không sửa tags sai thiết kế

Một sai lầm thường gặp là thêm `order.id` vào span/metric attributes rồi dựa vào sampling để giảm chi phí. Với spans, high-cardinality attributes có thể tăng kích thước event và tạo nguy cơ rò rỉ dữ liệu; với metrics, `orderId` có thể tạo một time series cho mỗi đơn hàng **ngay cả khi không trace record đó**.

| Dữ liệu | Metrics tags | Trace attributes / log fields |
|---|---|---|
| Service, environment, pipeline | Phù hợp nếu giá trị hữu hạn | Phù hợp |
| Topic và listener ID | Có điều kiện theo cardinality | Phù hợp trong ngữ cảnh Kafka |
| Partition | Cân nhắc số lượng partition × labels | Hữu ích cho điều tra |
| Retry attempt | Có thể chuẩn hóa thành các bucket nhỏ | Hữu ích cho một trace được lấy mẫu |
| Event ID, order ID | Không nên | Chỉ khi cần, áp dụng masking/access/retention |
| Kafka offset | Không nên | Có thể lưu trong logs/trace khi cần điều tra |
| Payload, token, exception message có PII | Không nên | Tránh hoặc redact; cần quy trình bảo mật riêng |

Micrometer phân biệt **low-cardinality key values** thường dùng cho metrics và **high-cardinality key values** có thể dành cho tracing trong Observation conventions. Việc dùng high-cardinality trong trace không tự làm dữ liệu an toàn; vẫn cần giới hạn số lượng, kích thước và thông tin nhạy cảm được phép ghi nhận.

## 18. Sampling ảnh hưởng tới phân tích latency như thế nào?

Nếu lấy mẫu ngẫu nhiên theo trace ID với một tỷ lệ cố định, sampled traces có thể giúp khám phá hình dạng request và chuỗi phụ thuộc. Tuy nhiên, không nên dựa hoàn toàn vào tập sampled traces để tính chính xác p95/p99 latency SLO trên toàn traffic, đặc biệt khi sampling rate thấp hoặc sampling policy thiên về lỗi/chậm.

Ví dụ tail sampling cố tình giữ toàn bộ trace có latency trên 5 giây và chỉ 2% trace bình thường. Trung bình latency của **traces được lưu** sẽ cao hơn trung bình toàn bộ traffic vì mẫu được chọn có chủ đích. Nếu dùng data đó làm latency SLO mà không áp dụng trọng số đúng, dashboard sẽ bị thiên lệch.

Để giám sát SLO, hãy dùng Micrometer timers và histogram có cardinality kiểm soát, tính tỷ lệ request/record vượt ngưỡng và phân vị ở backend phù hợp. Dùng traces để điều tra **vì sao** các record trong đuôi latency chậm, không thay thế nền tảng metric chính xác.

Sampling rate thay đổi theo thời gian cũng khiến số trace lỗi lưu lại tăng/giảm không đồng nghĩa error rate thực tế tăng/giảm. Dashboard trace volume nên hiển thị cấu hình sampling và effective sample rate để tránh nhầm lẫn.

## 19. Tải hệ thống quan sát: exporter, queue và collector

Ngay cả khi sampling giảm dữ liệu gửi ra, telemetry pipeline vẫn có giới hạn tài nguyên cần quản lý:

```text
Spring Kafka Observation/Tracing
          |
          v
Tracing SDK sampling + span processor
          |
          v
Exporter queue / batch
          |
          v
OTLP / Collector
          |
          v
Batch / tail sampling / routing
          |
          v
Trace backend
```

Theo dõi `spans created`, `spans sampled`, `spans exported`, dropped spans, queue size, exporter failures, collector memory và backend ingestion throttling. Một trace được sampler chọn nhưng bị exporter drop vì queue đầy vẫn không thể điều tra trên backend.

Với tail sampling, collector phải giữ trace data trong bộ nhớ đến khi ra quyết định. Nếu throughput tăng 10 lần trong peak load, memory footprint có thể tăng theo và gây eviction/drop. `decision_wait`, `num_traces`, tail policies và collector replica count cần được sizing theo peak traffic, không chỉ throughput bình thường.

Mất trace do exporter/collector không được phép kéo theo mất Kafka record hoặc làm sai offset commit. Tránh thiết kế exporter đồng bộ chặn consumer thread vô thời hạn; cấu hình timeout, bounded queue, graceful degradation và kiểm soát telemetry overhead theo thư viện thực tế. Khi sự cố observability backend xảy ra, hệ thống nghiệp vụ vẫn cần hoạt động và metrics/alert tối thiểu phải có đường dự phòng phù hợp.

## 20. Monitoring tỷ lệ sampling thực tế

Một sampling probability được khai báo là 1% không chứng minh backend thực sự nhận 1% **traces đầy đủ**. Có thể có parent-based decisions, mất context, collector drops, exporter failures, service traffic skew hoặc tail policies làm tỷ lệ khác đi.

Các nhóm chỉ số nên quan sát:

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Incoming Kafka record rate | Có bao nhiêu record thực sự được nhận? |
| Observation invocation count | Có bao nhiêu operation được instrument? |
| Tracing sampled spans/traces | SDK đang chọn bao nhiêu dữ liệu? |
| Exporter queue/dropped spans | Có span được chọn nhưng không ra khỏi process? |
| Collector received/exported spans | Collector có drop do memory, policy hoặc network? |
| Backend ingested traces | Lượng trace thực tế được lưu có phù hợp budget? |
| Trace completeness | Span producer/consumer/downstream có bị đứt context? |
| Sampling policy version | Tỷ lệ thay đổi lúc nào và do ai thay đổi? |

Nên ghi lại sampling policy như một cấu hình vận hành có version và changelog. Khi giảm từ 10% xuống 1%, trace count giảm là điều dự kiến; error rate và business throughput **không nên** tự giảm tương ứng.

Một số chính sách tail-based giữ gần như mọi trace lỗi. Khi có outage làm error rate tăng từ 0,1% lên 50%, ingestion có thể tăng đột ngột dù lượng traffic không đổi. Cần giới hạn budget cho chính sách ưu tiên lỗi hoặc có chiến lược graceful degradation được xác định trước.

## 21. Kịch bản multi-replica và consistency xuyên dịch vụ

Một pipeline có thể chạy 20 pod producer, 30 pod consumer và nhiều downstream services. Nếu mỗi pod tạo trace root mới với random sampling độc lập khi context bị mất, backend có thể có các mảnh trace không nối được với nhau. Để giữ correlation, cần:

1. Một quy ước propagation thống nhất, ví dụ W3C Trace Context khi stack hỗ trợ.
2. Instrumentation producer và consumer đều bật Observation/tracing trên đúng factory/template.
3. Sampling policy parent-based hoặc quy ước tương đương giữa các service tham gia.
4. Không làm mất tracing headers khi dùng message converter, bridge Kafka, retry/DLT hoặc replay.
5. Dùng business correlation ID ổn định ngoài tracing để liên kết khi trace bị bỏ hoặc cần điều tra nhiều lần replay.

Tại collector nhiều replica dùng tail sampling, spans của cùng trace ID phải đi tới cùng điểm ra quyết định hoặc qua tầng aggregation/load-balancer theo trace ID phù hợp. Chỉ tăng số collector mà không quan tâm trace affinity có thể làm tail policies nhìn thấy mỗi nơi một phần trace.

Không nhầm `consumer group.id` với `trace ID`. Một consumer group xác định cách Kafka phân phối partition và committed offset, còn trace ID liên kết các operation được quan sát. Một record được giao lại sau rebalance có thể tạo một processing span mới và business ID cần giữ nguyên; không được dùng trace ID để deduplicate xử lý tài chính.

## 22. Kiểm thử end-to-end sampling cho Spring Kafka

Để xác minh cấu hình, có thể dùng Kafka test broker hoặc Testcontainers và một OpenTelemetry/Micrometer test exporter. Không chỉ kiểm tra một property tồn tại trong YAML; cần nhìn thấy traces và metrics ở đúng chỗ.

Các kịch bản quan trọng:

1. **Observation listener và producer:** cả `KafkaTemplate` lẫn container đều tạo telemetry khi được bật và có tracing setup.
2. **Head sampling 100% trong test:** gửi một event, xác nhận trace context đi qua Kafka headers và spans producer/consumer liên kết theo instrumentation của version hiện hành.
3. **Head sampling 0% trong test:** không xuất sampled trace tương ứng, nhưng metrics listener và kết quả nghiệp vụ vẫn được ghi nhận.
4. **Sampling 1% với lượng event đủ lớn:** kiểm tra tỷ lệ thống kê theo trace roots, không assert mỗi 100 records phải có đúng một trace.
5. **Parent sampled/unsampled:** xác nhận downstream tôn trọng context upstream hoặc ghi nhận rõ nơi bắt đầu trace root mới.
6. **Retry/DLT:** lỗi được recover, DLT metadata còn đủ ngay cả khi trace không sampled; kiểm tra propagation qua retry topic theo cấu hình thực tế.
7. **Exporter outage:** quan sát telemetry drops nhưng không làm listener bỏ record hoặc commit offset sai.
8. **Tail sampling lỗi:** khi SDK xuất đầy đủ spans tới collector, error trace được chọn nếu span status/attributes khớp policy.
9. **Collector multi-replica:** kiểm tra trace routing và completeness; không nhận span producer ở replica A rồi consumer ở replica B mà policy ra quyết định riêng.
10. **PII/cardinality:** đảm bảo trace/span attributes không chứa payload nhạy cảm, metrics không có event ID/order ID làm tags.
11. **Batch listener:** xác nhận cách framework tạo Observation theo batch/record, không giả định một batch có cùng trace context.
12. **Sampling policy đổi lúc runtime/deploy:** kiểm tra dashboards nêu rõ thời điểm thay đổi và không diễn giải trace volume là số message thực.

Không nên dùng test chờ “chính xác một trace được sample” với tỷ lệ 1% và 100 event; xác suất dẫn đến test flaky. Với test propagation, chọn sampler 100% để quan sát cấu trúc trace; với test xác suất, dùng số lượng lớn và một khoảng sai số thống kê hợp lý.

## 23. Troubleshooting sampling và tracing

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Metrics vẫn có nhưng không thấy traces | Sampling thấp/0%, exporter/collector lỗi hoặc Observation/tracing bridge chưa được bật | Kiểm tra effective sampler, instrumentation, export queue và backend |
| Consumer có span nhưng không nối với producer | Không propagate/extract Kafka tracing headers hoặc tracing SDK khác định dạng | Xác minh producer/consumer Observation, propagator và message headers |
| Trace lỗi hiếm không xuất hiện | Head sampling đã drop trước khi biết outcome | Dùng metrics/logs/DLT; cân nhắc tail sampling cho luồng có nhu cầu |
| Backend quá tải dù sampling 1% | Lưu lượng rất lớn, nhiều span/trace, retry storm, tail policy giữ errors | Đo spans/s thực tế, exporter queue và collector capacity |
| Tail sampling chỉ giữ đoạn cuối trace | Span đến chậm hoặc spans cùng trace phân tán giữa collector replicas | Điều chỉnh decision wait và trace-ID-aware routing |
| `status_code=ERROR` không giữ lỗi nghiệp vụ | Span không được đánh dấu ERROR theo instrumentation | Xác nhận error handling và observation conventions |
| Trace volume giảm sau deploy, hệ thống vẫn khỏe | Sampling probability thay đổi | Đối chiếu change log, kiểm tra metrics nghiệp vụ đầy đủ |
| Có hai tracing pipelines khác nhau | Java agent và SDK tự cấu hình song song | Chọn một nguồn instrumentation/exporter và kiểm tra duplicate spans |
| Tìm record DLT không có trace | Record không sampled, context bị mất hoặc exporter drop | Tra cứu DLT provenance, business event ID và structured logs |
| Số series Prometheus vẫn tăng vô hạn | Metric tags high-cardinality, không liên quan tracing sampler | Chuẩn hóa tags, loại bỏ event ID/order ID khỏi metric labels |

Khi chẩn đoán, đi từ **business processing/metrics**, qua **Observation và SDK sampler**, tiếp đến **exporter/Collector**, cuối cùng mới tới **trace backend**. Mỗi tầng có một kiểu mất dữ liệu khác nhau. Không quy kết `sampling.probability` khi thực tế span đã được chọn nhưng bị drop ở exporter.

## 24. Runbook khi cần tăng sampling trong sự cố

Một chiến lược vận hành thực tế không giữ 100% trace toàn hệ thống suốt thời gian dài, nhưng có thể tăng khả năng điều tra tạm thời cho phạm vi hẹp:

1. **Xác định mục tiêu:** lỗi ở topic, consumer group, listener, service hoặc workflow nào; cần điều tra latency, exception hay dữ liệu bất nhất?
2. **Kiểm tra tín hiệu nền:** Kafka lag, DLT, retry, consumer non-responsive, error rate và downstream latency xác nhận sự cố thực tế.
3. **Đo budget hiện tại:** spans/s, collector memory, exporter drop, ingest throttling và retention còn khả dụng.
4. **Chọn phạm vi:** service/pipeline có vấn đề hoặc một workflow replay được duyệt; không bật 100% cho toàn cluster theo phản xạ.
5. **Chọn loại sampling:** tăng head rate nếu cần nhiều trace thông thường; dùng tail sampling khi cần ưu tiên lỗi/chậm và có năng lực collector.
6. **Bảo đảm propagation:** kiểm tra Kafka headers, parent-based sampling, retry/DLT và trace affinity giữa collectors.
7. **Giới hạn thời gian và tốc độ:** cấu hình có expiry, rate budget và người chịu trách nhiệm rollback sampling policy.
8. **Theo dõi overhead:** exporter drops, collector queue, CPU/heap của ứng dụng, Kafka listener latency và độ trễ của tracing backend.
9. **Thu thập bằng chứng:** lưu trace links, business event ID và DLT provenance với phân quyền đúng; không đưa payload nhạy cảm vào span.
10. **Hoàn nguyên:** khôi phục sampling về baseline sau incident và ghi lại kết quả/giới hạn của đợt điều tra.

Nếu sampler không hỗ trợ thay đổi động, thay đổi policy có thể đòi hỏi rolling deployment; cần cân nhắc tác động rebalance của các Kafka consumers. Trong lúc triển khai, các pods dùng sampling policy khác nhau có thể cùng tồn tại; ghi nhận version/config để diễn giải số liệu trong giai đoạn chuyển tiếp.

## 25. Nguyên tắc production

1. **Sampling là lựa chọn dữ liệu tracing**, không thay đổi delivery semantics, commit offset hay idempotency của Spring Kafka.
2. Tính budget từ trace roots/s, spans/trace, kích thước span, retention và tải peak; 1% vẫn có thể tạo hàng triệu span/ngày.
3. Ưu tiên parent-based sampling và propagation nhất quán qua Kafka record headers để giữ mối liên kết producer/consumer.
4. Head sampling giảm overhead sớm nhưng có thể bỏ lỡ lỗi hiếm; tail sampling giữ lỗi/chậm tốt hơn khi collector nhận đủ spans.
5. **Tail sampling không phục hồi spans đã bị SDK drop**; không hứa giữ 100% lỗi nếu upstream head sampling đã bỏ dữ liệu.
6. Bật Observation trên đúng listener container factory và `KafkaTemplate`; kiểm tra tracing bridge/exporter trước khi diễn giải kết quả.
7. Metrics về throughput, error rate, consumer lag, retry và DLT phải có độ bao phủ độc lập với trace sampling.
8. Không dùng trace ID làm business idempotency key; giữ stable event ID cho retry, replay và audit.
9. Giới hạn metric tag cardinality, redact PII trong spans/logs và không export payload thô chỉ vì trace được sampled.
10. Giám sát SDK/exporter/collector drops, tail memory, trace completeness và effective sampling rate trên backend.
11. Kiểm thử head/parent/tail semantics, Kafka header propagation, batch listeners, retry/DLT và collector outage trước rollout.
12. Có quy trình tăng sampling tạm thời theo phạm vi, budget và thời hạn rõ ràng khi điều tra production.

**Kết luận:** sampling cho lưu lượng lớn giúp Spring Kafka duy trì giá trị của distributed tracing mà không biến hệ thống observability thành nút thắt. Chiến lược bền vững kết hợp **metrics đầy đủ**, **traces được lấy mẫu có chủ đích**, **context propagation nhất quán** và **DLT/audit có provenance**. Hiểu rõ khác biệt giữa head và tail sampling, cùng giới hạn của mỗi tầng trong pipeline telemetry, giúp đội vận hành kiểm soát chi phí mà vẫn đủ bằng chứng để điều tra lỗi hiếm, latency cao và sự cố retry/recovery.
