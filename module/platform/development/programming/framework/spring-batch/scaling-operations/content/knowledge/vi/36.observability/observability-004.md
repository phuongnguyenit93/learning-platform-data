# Trace manager worker interaction

Trong Spring Batch xử lý khối lượng dữ liệu lớn, một job có thể điều phối hàng chục worker threads, nhiều JVM hoặc nhiều pod thông qua middleware. Khi dashboard cho thấy manager chờ lâu nhưng CPU của worker thấp, người vận hành cần trả lời: **manager đã gửi request chưa, broker giữ message bao lâu, worker nào nhận, chunk/partition nào đang chạy, transaction đã commit chưa, và reply có về đúng manager execution không?** Log cục bộ từng process thường không đủ trả lời. **Trace manager worker interaction** là việc quan sát xuyên suốt các chặng điều phối, truyền message, thực thi và phản hồi bằng **distributed tracing**, kết hợp với metrics, structured logs và metadata Spring Batch.

Bài học thuộc chương **Observability** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch qua multi-threaded step, parallel steps, partitioning và xử lý phân tán, đồng thời đo nút thắt, giữ thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế. Ở đây, trọng tâm là **theo dấu tương tác manager ↔ worker** trong **remote partitioning**, **remote chunking** và đối chiếu với **local partitioning**, không chỉ thêm một trace ID vào log.

**Nguyên tắc:** trace là **bằng chứng quan sát một đường thực thi**, không phải cơ chế giao hàng exactly-once, không thay thế `JobRepository`, `ExecutionContext`, correlation protocol, transaction ledger hay business reconciliation. Một span ghi `SUCCESS` có thể chỉ nói rằng một phương thức gửi message đã chạy xong; **không** chứng minh worker đã commit dữ liệu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **trace ID**, **span ID**, **parent/child**, **span link**, **correlation ID**, **request ID**, **JobExecution ID**, **StepExecution ID** và **business idempotency key**.
2. Vẽ đường đi manager → outbound gateway/channel → broker → worker → business transaction → reply → manager trong remote partitioning và remote chunking.
3. Xác định **điểm bắt đầu/kết thúc span đúng với loại operation**: dispatch, broker publish, worker consume, processing, chunk commit, reply và reply correlation.
4. Truyền trace context qua Spring Integration và AMQP/JMS/Kafka bằng cơ chế **W3C Trace Context** và header mapping đã xác minh.
5. Dùng Micrometer Observation/Tracing hoặc OpenTelemetry phù hợp Spring Boot 3/Spring Batch 5, phân biệt auto-instrumentation với span tự bổ sung.
6. Giữ trace liên tục qua **thread pools**, batch listeners, multi-worker processing, asynchronous callbacks và broker redelivery.
7. Chẩn đoán missing reply, delayed/duplicate message, worker failure, job restart, broker backlog và manager timeout bằng trace + JobRepository + business DB.
8. Thiết kế tên span/attributes có cardinality vừa phải; không đưa payload, token hay dữ liệu khách hàng vào trace.
9. Kiểm thử end-to-end với **hai JVM/process và broker thật**, không chỉ một channel trong cùng JVM.
10. Xây runbook và dashboard để lựa chọn giữa tăng worker, chỉnh queue/pool, tối ưu DB hoặc khắc phục routing.

**Tình huống xuyên suốt:** một manager chạy job `nightlySettlement` gồm 10 triệu transactions, gửi `ChunkRequest` qua RabbitMQ tới ba worker pod. Một chunk được gửi lúc 01:00:00 nhưng manager chỉ nhận response lúc 01:00:25. Cần xác định 25 giây nằm ở **queue wait**, **deserialize**, **ItemProcessor**, **DB lock/commit**, **reply publish**, **reply routing** hay **manager correlation wait**. Trong job partitioning khác, manager gửi `StepExecutionRequest` để worker chạy một partition; ta cũng cần biết node nào xử lý step và metadata nào xác nhận kết quả.

## 2. Tracing giải quyết câu hỏi gì, không giải quyết câu hỏi gì?

| Câu hỏi | Bằng chứng phù hợp | Trace đơn lẻ có đủ? |
| --- | --- | --- |
| Manager gửi request lúc nào? | Producer/send span, message metadata | Có, nếu đã instrument |
| Broker giữ message bao lâu? | Publish/consume timestamps, broker metrics | Chỉ khi có đủ mốc đáng tin |
| Worker nào bắt đầu xử lý? | Consumer/worker span + worker identity | Có khi sampled/propagation đúng |
| Worker đã commit chunk chưa? | DB transaction outcome, StepExecution, ledger | **Không** nếu chỉ thấy processor span |
| Reply có đúng execution không? | Correlation ID + protocol metadata + receive span | Cần correlation protocol |
| Message có bị redeliver không? | Broker redelivery headers, attempts, logs | Không chắc nếu chỉ một trace |
| Một business effect có bị áp dụng hai lần? | Unique operation ID/ledger/reconciliation | **Không** |
| Worker được scale bao nhiêu? | Executor/pod metrics, queue depth | Trace chỉ bổ sung |
| Job có thể restart từ đâu? | JobRepository và ExecutionContext | **Không** |

Một hệ thống quan sát tốt dùng **ba tín hiệu gắn cùng ngữ cảnh**: **traces** cho đường đi/latency, **metrics** cho tổng lượng và ngưỡng cảnh báo, **logs** cho lỗi/bằng chứng chi tiết có thể truy cứu. Spring Batch **metadata** là nguồn dữ liệu độc lập về kết quả thực thi.

## 3. Khác biệt giữa các kiểu interaction

| Kiến trúc | Manager làm gì? | Worker làm gì? | Đơn vị giao việc qua ranh giới |
| --- | --- | --- | --- |
| **Local partitioning** | Tạo partitions và dispatch qua TaskExecutor trong một JVM | Chạy worker StepExecution trên thread | `ExecutionContext`/worker StepExecution; **không có broker** |
| **Remote partitioning** | Tạo partition, gửi yêu cầu thực thi qua middleware | Chạy worker StepExecution, cập nhật/trả kết quả | `StepExecutionRequest` cùng metadata worker step |
| **Remote chunking** | Đọc items, đóng chunks, gửi request | Process/write chunk rồi trả response | `ChunkRequest` / `ChunkResponse` |
| **Parallel steps/flows** | Điều phối luồng trong một JobExecution | Steps/branches thực thi đồng thời | Không nhất thiết có message |

**Điểm phải giữ chính xác:**

- Với **remote partitioning**, `ItemReader` thường ở **worker**; mỗi partition có reader/checkpoint và StepExecution riêng. Tracing phải gắn với **worker StepExecution**, không giả định manager đọc từng record.
- Với **remote chunking**, `ItemReader` thường ở **manager**; message chứa một chunk nhiều items. Trace cho một request **không tương đương trace của mỗi item**.
- Với **local partitioning**, context đi qua executor threads; instrument đúng thread boundaries là trọng tâm, không tạo giả broker spans.
- Trong cả hai mô hình phân tán, completion về mặt **Spring Batch** và broker ACK/reply là các sự kiện khác nhau.

## 4. Trace, span, parent, link và correlation

~~~text
Trace ID:    định danh một cây/đồ thị quan sát xuyên service
Span ID:     định danh một operation được đo
Parent ID:   quan hệ nhân quả trực tiếp giữa hai spans
Span link:   liên kết với context khác, hữu ích cho async/redelivery
Correlation: định danh request/reply ở protocol ứng dụng
~~~

Một trace có nhiều spans; mỗi span có thời điểm start/end, name, attributes, events và status. **Trace ID không phải correlation ID**, vì hai mục đích có khác biệt lớn:

| Định danh | Phạm vi | Dùng vào việc gì | Nên làm idempotency key? |
| --- | --- | --- | --- |
| `traceId` | Một distributed trace | Điều hướng đường thực thi | **Không** |
| `spanId` | Một span | Thể hiện operation cha/con | **Không** |
| `requestCorrelationId` | Một request/reply logic | Ghép đúng response với request pending | **Không mặc định** |
| `requestId` | Một dispatch attempt hoặc logical request | Dedup/correlation theo protocol | Tùy thiết kế, không đánh đồng |
| `JobInstanceId` | Identifying JobParameters | Phân biệt một batch logic | Không phải message identity |
| `JobExecutionId` | Một lần chạy/restart của JobInstance | Xác định attempt chạy job | Không phải record identity |
| `StepExecutionId` | Lần chạy một step/partition | Liên hệ worker metadata | Không phải trace ID |
| `partitionName` | Logical partition | Stable partition mapping/restart | Không phải request ID |
| `chunkSequence` | Thứ tự trong một protocol/scope | Xác định chunk/reply | Không đủ nếu thiếu execution context |
| `businessOperationId` | Một business effect | Chống áp dụng cùng operation hai lần | **Có nếu sink thực thi** |

**Đừng dùng trace ID để match reply**: exporter có thể drop spans vì sampling, trace context có thể thay đổi giữa attempts hoặc bị mất qua adapter, trong khi Spring Batch request/reply vẫn phải hoạt động đúng. Correlation protocol phải độc lập với hệ thống telemetry.

## 5. Sơ đồ remote chunking đầy đủ

~~~mermaid
sequenceDiagram
    participant M as Batch Manager
    participant Out as Outbound Integration
    participant MQ as Middleware
    participant W as Worker
    participant DB as Business DB
    participant Reply as Reply Queue
    M->>M: Reader tạo items/chunk
    M->>Out: ChunkRequest + trace context
    Out->>MQ: Publish request
    Note over MQ: Queue wait / redelivery có thể xảy ra
    MQ->>W: Deliver request
    W->>W: Deserialize + process items
    W->>DB: Writer + transaction COMMIT/ROLLBACK
    W->>Reply: ChunkResponse + correlation
    Reply->>M: Deliver reply
    M->>M: Correlate reply + update chunk outcome
~~~

**Mốc cần đo riêng:** manager build chunk, outbound adapter publish, broker queue wait, inbound adapter receive, worker processing, DB writer/commit, reply publish, inbound reply receive và manager wait/correlation. Thứ tự trên là mô hình logic; **ACK**, **transaction commit**, **reply** và **JobRepository update** có thể không chung một transaction.

~~~text
manager.job
 └─ manager.chunk.dispatch              (build + send intent)
     ├─ messaging.publish               (broker accept/send)
     └─ worker.messaging.receive        (extracted remote trace context)
          ├─ worker.chunk.process
          │   ├─ processor.batch
          │   └─ db.write / db.commit outcome
          └─ worker.reply.publish
              └─ manager.reply.receive / correlate
~~~

Sơ đồ span tree trên là **minh họa**. Trong mô hình hoàn toàn bất đồng bộ, consumer và reply spans có thể là **span mới liên kết bằng span link** thay vì luôn là quan hệ parent-child kéo dài nhiều giờ. Không giữ một span/scope mở vô hạn chỉ để “có một đường thẳng đẹp” trên tracing UI.

## 6. Sơ đồ remote partitioning đầy đủ

~~~mermaid
sequenceDiagram
    participant M as Manager PartitionStep
    participant MQ as Request Middleware
    participant W as Remote Worker JVM
    participant JR as JobRepository
    participant DB as Business DB
    participant R as Reply/Status
    M->>JR: Tạo/điều phối worker StepExecutions
    M->>MQ: StepExecutionRequest + traceparent
    MQ->>W: Deliver partition request
    W->>JR: Read/update StepExecution metadata
    W->>W: Reader/Processor/Writer theo ExecutionContext
    W->>DB: Chunk transactions COMMIT
    W->>JR: Worker StepExecution final outcome
    W->>R: Reply / completion signal nếu protocol dùng
    R->>M: Correlate worker status
    M->>JR: Aggregate partition results
~~~

Trong cấu hình cụ thể, manager có thể nhận kết quả qua reply flow hoặc đọc trạng thái `JobRepository` theo mô hình handler/integration được dùng. **Không giả định bắt buộc mỗi remote partition deployment có cùng kiểu reply message**. Trace instrumentation phải đặt tại **đúng topology thực tế**.

**Với remote partitioning, chỉ gửi xong `StepExecutionRequest` không nghĩa partition đã chạy.** Manager còn cần quan sát nhận request, worker step start/end, trạng thái JobRepository và kết quả tổng hợp.

## 7. W3C Trace Context là gì?

Chuẩn thường gặp để lan truyền distributed trace qua HTTP và message headers là **W3C Trace Context**, với:

- `traceparent`: định danh trace, parent span và sampled flags.
- `tracestate`: dữ liệu vendor-specific theo contract.
- `baggage`: các giá trị bổ sung nếu triển khai W3C Baggage; **có thể chứa dữ liệu nhạy cảm**, cần policy nghiêm ngặt.

Ví dụ hình thức `traceparent`:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

**Không tự nối string traceparent bằng `UUID.randomUUID()`.** Để SDK instrumentation/tracing propagator tạo và extract/inject các headers, bảo đảm ID format/flags hợp lệ, baggage sanitization và khả năng tương thích.

Mỗi message cần giữ **đúng context** từ producer sang consumer nếu muốn nối trace. Một event có thể đi qua HTTP → Spring Integration → RabbitMQ → worker JVM → JMS reply; **mỗi adapter** có header mapping và transport semantics riêng. Context có trên channel nội bộ chưa chứng minh nó đã lên broker.

## 8. Truyền context xuyên message khác truyền qua method call

Trong cùng thread, tracing SDK có thể giữ current span trong thread-local scope. Khi chuyển sang broker:

~~~text
Manager thread (active producer span)
    ↓ Inject trace context vào message headers
AMQP/Kafka/JMS message
    ↓ Receive + extract context từ headers
Worker thread (start consumer/processing span)
~~~

Nếu **không inject/extract**, worker có thể tạo **trace mới**: job vẫn chạy đúng nhưng UI observability hiển thị hai cây không liên kết. Nếu worker chỉ copy giá trị `traceId` vào log mà không tạo span với parent/link context đúng, tracing backend cũng không tự ghép các spans thành quan hệ có ý nghĩa.

**Không cố giữ `ThreadLocal` hoặc `MDC` xuyên network**: chúng chỉ sống trong process/thread. Propagation phải dùng **message headers/carrier** hoặc context propagation mechanism được instrumentation hỗ trợ.

## 9. Header mapping qua Spring Integration và broker

| Transport | Header/carrier điển hình | Điều cần xác nhận |
| --- | --- | --- |
| **RabbitMQ/AMQP** | Message properties headers và adapter mappings | `traceparent/tracestate` có thật trong AMQP headers? reply path có giữ context? |
| **Kafka** | Record headers, giá trị thường là byte arrays | Producer/consumer instrumentation có inject/extract đúng encoding? |
| **JMS** | JMS properties/user properties theo provider | Tên property, kiểu giá trị, restrictions và adapter mapping có tương thích? |
| **Spring Integration channel nội bộ** | `MessageHeaders` của Spring Messaging | Context có giữ qua async channel/executor? |
| **HTTP gateway** | HTTP request headers | Tracing filter/interceptor và upstream trust boundary có hoạt động? |

**Các điểm dễ mất header:**

1. Custom `HeaderMapper` chỉ copy allowlist mà quên `traceparent`.
2. Custom message converter tạo message mới nhưng bỏ headers.
3. Workflow request/reply map request header sang broker nhưng reply dùng map riêng.
4. Bridge qua Kafka/JMS thay tên hoặc encoding header mà không extract lại.
5. Manual `MessageBuilder.withPayload(...)` tạo một message mới và không truyền context phù hợp.
6. Một async handler được chạy trên executor không mang current context.

**Đừng cho rằng mọi adapter tự động propagate trace context trên mọi Spring Integration/Spring Boot version.** Hãy test header **ở wire/broker thực**, không chỉ đọc `MessageHeaders` trước khi publish.

## 10. Từ trace context tới worker span

~~~mermaid
flowchart LR
    R["Producer có active Observation"] --> I["Propagator inject headers"]
    I --> Q[("Broker message")]
    Q --> X["Worker adapter extract headers"]
    X --> C["Consumer span / Observation"]
    C --> B["Batch worker logic"]
    B --> D[("DB transaction")]
    B --> P["Reply span + headers"]
~~~

**Nếu instrument bằng Micrometer Tracing**, tracing bridge/exporter và instrumentation của Spring messaging phải được cấu hình đúng; `ObservationRegistry` một mình chỉ tạo observation/timing, **không tự bảo đảm cross-JVM trace**. Ở những nơi Spring Integration không có instrumentation theo phiên bản/topology, phải thêm observation/span và propagator tại **đúng ranh giới**.

Một cách kiểm tra nhanh:

~~~text
1. Manager inject traceparent vào request message.
2. Worker nhận message, log có traceId trùng với request.
3. Tracing backend có worker consumer span parent/link đến producer context.
4. Worker gửi reply; manager nhận reply với correlation ID đúng.
5. Retry/redelivery tạo attempt spans có thể truy cứu,
   không làm mất logical request identity.
~~~

Nếu bước 2 đúng nhưng bước 3 sai, có thể code chỉ copy `traceId` string vào log, hoặc parent context đã bị mất. Nếu bước 3 đúng nhưng bước 4 sai, tracing vẫn hoạt động nhưng **protocol reply correlation đang lỗi**; không được coi một span nối được là kết quả job thành công.

## 11. Micrometer Observation, Tracing và OpenTelemetry

Trong hệ Spring Boot 3.x/Spring Batch 5.x, ba khái niệm thường xuất hiện cùng nhau:

- **Micrometer Observation**: API biểu diễn operation, context, low/high-cardinality key-values và observation lifecycle. Có thể cung cấp metrics và tracing qua registered handlers.
- **Micrometer Tracing**: API abstraction cho spans/tracer/baggage, có thể bridge sang OpenTelemetry hoặc tracer backend khác.
- **OpenTelemetry SDK/Collector/backend**: tạo/xuất spans và nhận dữ liệu telemetry qua OTLP hoặc transport khác theo stack đã chọn.

**Đừng đánh đồng các tầng:** gọi `Observation.createNotStarted(...)` không đủ nếu không có ObservationRegistry được cấu hình handler/tracing bridge và exporter. Một span được tạo trong JVM nhưng exporter không kết nối cũng sẽ không xuất hiện trong tracing backend.

### Cấu hình minh họa

~~~yaml
# Ví dụ Spring Boot 3.x; kiểm tra property/dependency
# theo đúng minor version và tracing/exporter đang dùng.
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

**Đây không phải cam kết mọi bản Boot đều có cùng dependency/property**. Cần chọn bridge (`micrometer-tracing-bridge-otel` hoặc tương đương), exporter OTLP và instrumentation Spring Integration/messaging phù hợp đúng version; xem effective configuration qua diagnostics/test, không suy đoán chỉ dựa YAML.

**Chọn sampling 10% không đồng nghĩa 90% request biến mất khỏi JobRepository**: tracing sampling chỉ tác động vào telemetry. Error counters, commit outcomes và dữ liệu job phải giữ đủ độc lập để vận hành.

## 12. Thêm span nghiệp vụ bằng Micrometer Observation

Đây là đoạn Java minh họa **đo một đoạn xử lý đồng bộ**. Nó không phải cấu hình đầy đủ manager/worker integration, và **không tự tạo trace context qua broker**.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

final class BatchWorkerObservation {
    private final ObservationRegistry registry;

    BatchWorkerObservation(ObservationRegistry registry) {
        this.registry = registry;
    }

    void traceChunkProcessing(
            String mode,
            String logicalStepName,
            long stepExecutionId,
            Runnable process) {

        Observation observation = Observation.createNotStarted(
                        "batch.worker.chunk.process", registry)
                .lowCardinalityKeyValue("batch.mode", mode)
                .lowCardinalityKeyValue("batch.role", "worker")
                .lowCardinalityKeyValue(
                        "batch.step.name", logicalStepName)
                .highCardinalityKeyValue(
                        "batch.step.execution.id",
                        Long.toString(stepExecutionId));

        observation.observe(process);
    }
}
~~~

**Giải thích:**

1. `batch.worker.chunk.process` là tên **ổn định**; không nhét chunk sequence hay UUID vào tên observation.
2. `batch.mode` dùng một tập giá trị nhỏ (`remote-chunking`, `remote-partitioning`, `local-partitioning`), phù hợp low-cardinality.
3. `stepExecutionId` thường tăng liên tục nên được đặt **high-cardinality** và chỉ thêm khi hệ thống tracing/retention cho phép; **không** đưa nó vào mọi time-series metric tag.
4. `observe(process)` đo thời gian thực thi `Runnable`. Nếu callback kết thúc trước DB transaction commit, span này **không** khẳng định commit đã thành công.
5. Nếu operation thực sự là **async future** hoặc gửi message rồi trả về, scope đóng khi callback trả về; muốn đo completion phải instrument callback và remote boundary riêng.

**Tránh tạo span trùng:** nếu Spring/Micrometer/OpenTelemetry auto-instrumentation đã tạo span consumer/producer, custom span ở đây nên đo **business processor/Batch chunk** bên dưới thay vì tạo thêm một consumer span y hệt.

## 13. Khi nào cần Micrometer Tracer trực tiếp?

Khi cần điều khiển rõ vòng đời span trong một operation đồng bộ, có thể dùng `io.micrometer.tracing.Tracer`:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

final class WorkerSpanRunner {
    private final Tracer tracer;

    WorkerSpanRunner(Tracer tracer) {
        this.tracer = tracer;
    }

    void runWorkerLogic(Runnable logic) {
        Span span = tracer.nextSpan()
                .name("batch.worker.business")
                .start();
        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            logic.run();
        } catch (RuntimeException error) {
            span.error(error);
            throw error;
        } finally {
            span.end();
        }
    }
}
~~~

`nextSpan()` thường lấy current trace context theo tracer scope đang active. Nếu **không có extracted remote context trước đó**, một span mới có thể bắt đầu trace khác. Đây là lý do phải instrument **inbound message carrier** và đảm bảo context extraction trước khi gọi worker logic.

**Không giữ SpanInScope qua async scheduling rồi để worker khác dùng scope ấy**. Span scope thường thread-local; nếu `logic.run()` chỉ gọi `executor.submit(...)` rồi return, span kết thúc trước khi task xử lý xong. Dùng context-aware executor/wrapper hoặc tạo span ở task thực thi, liên kết parent/link đúng.

## 14. Chọn điểm đo span theo lifecycle Spring Batch

Một hệ thống có thể thêm instrumentation ở các lớp:

| Điểm đo | Tín hiệu thật sự có | Không nên gọi là |
| --- | --- | --- |
| Manager `beforeStep` | Manager step bắt đầu | Worker partition đã nhận work |
| `Partitioner.partition(...)` | Tạo map partition contexts | Workers đã chạy |
| Outbound adapter send | Gọi publish hoặc broker accept theo API | Business commit |
| Broker consumer receive | Message được deliver tới worker | Message đã xử lý thành công |
| Worker `beforeStep` | Worker StepExecution bắt đầu | All chunks committed |
| `ItemProcessor.process` | Một item được process | Exactly-once effect |
| `ItemWriter.write` | Writer method thực thi | DB transaction đã commit |
| Chunk commit hook/outcome | Chunk transaction committed trong nguồn phù hợp | Broker reply đã về |
| Worker `afterStep` | Worker step logic kết thúc và status đang được tổng hợp | JobRepository đã persist mọi trạng thái và manager đã biết |
| Worker reply publish | Worker gửi response | Manager đã correlate/aggregate |
| Manager reply receive | Reply được nhận | Reply đúng execution nếu chưa validate |
| Manager `afterStep` | Manager step kết thúc theo flow | Toàn business output đúng nếu chưa reconcile |

**Một lỗi phổ biến** là thêm span `batch.chunk.committed` vào `ItemWriteListener.afterWrite`. Listener này có thể chạy **trước khi transaction commit**, sau đó một exception khiến rollback; tên span như vậy là misleading. Gọi span đó là `batch.writer.invoke`, và lấy **commit outcome thực** từ transaction synchronization/connection/StepExecution events đã xác minh.

### Span granularity nên vừa đủ

10 triệu items × một span/item tạo quá nhiều telemetry. Thường bắt đầu bằng **span per request/chunk/partition** và các spans dài cho nguồn I/O, processor batch và writer commit. Bật per-item debug trace **có điều kiện**, lấy mẫu theo source file/record test, không mặc định production.

## 15. Commit, rollback, ACK và reply là những sự kiện khác nhau

~~~text
T1  worker nhận ChunkRequest
T2  processor xử lý item
T3  writer thực thi SQL
T4  transaction COMMIT thành công
T5  worker publish ChunkResponse
T6  broker ACK inbound request
T7  manager nhận reply và xác nhận correlation
~~~

Thứ tự T5/T6 có thể khác nhau tùy container, middleware và transaction configuration; trong trường hợp lỗi, một vài bước có thể không xảy ra hoặc outcome chưa rõ.

Nếu worker đã **commit DB tại T4** nhưng chết trước khi reply/ACK được xác nhận, broker có thể **redeliver request** hoặc manager retry. Trace sẽ có **nhiều attempts**, nhưng business side effect phải được dedup/đối soát. Không dùng số span `worker.chunk.process` bằng một để kết luận chunk được áp dụng đúng một lần.

**Phân biệt tên telemetry:**

- `messaging.publish.attempt`: ứng dụng thử gửi message.
- `messaging.publish.acknowledged`: broker xác nhận publish theo publisher confirm/producer callback semantics đang dùng.
- `worker.chunk.processed`: code xử lý chunk trả về.
- `db.transaction.committed`: transaction commit outcome đã được xác minh.
- `worker.reply.published`: response đã được broker nhận theo contract.
- `manager.reply.correlated`: manager xác nhận reply khớp request còn hiệu lực.
- `step.execution.completed`: trạng thái framework tương ứng sau khi persist/confirm theo định nghĩa metric.

**Không đếm chúng như cùng một “success counter”.** Mỗi event báo một milestone khác nhau.

## 16. Gắn transaction outcome vào telemetry

Trong Spring-managed JDBC transaction, muốn ghi nhận chính xác commit/rollback có thể dùng một `TransactionSynchronization` ở trong transaction đang hoạt động:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

final class ChunkTransactionAudit {
    void registerOutcomeCallback(
            Runnable onCommit,
            Runnable onRollbackOrUnknown) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException(
                    "No active transaction synchronization");
        }
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        onCommit.run();
                    }

                    @Override
                    public void afterCompletion(int status) {
                        if (status != STATUS_COMMITTED) {
                            onRollbackOrUnknown.run();
                        }
                    }
                });
    }
}
~~~

**Ràng buộc của ví dụ:**

- `afterCommit` là **sau khi transaction manager thông báo commit**, không phải broker ACK hoặc producer reply; resource bên ngoài có thể vẫn chưa đồng bộ.
- Callback có thể chạy với transaction context/scope tracing đã thay đổi; muốn tạo span `commit outcome` liên kết đúng trace phải **capture/restore tracing context hợp lệ**, không giữ một `ThreadLocal` sống vô thời hạn.
- Không thực hiện network blocking/side effect quan trọng bên trong callback chỉ để xuất telemetry; lỗi exporter **không được đổi quyết định business commit**.
- `STATUS_UNKNOWN`/rollback cần được gắn trạng thái riêng, **không** tự giải thích cả hai là input record lỗi.
- Với non-Spring-managed transactions hoặc DB khác, cách instrument có thể khác; kiểm thử trên transaction manager thực tế.

**Nếu worker dùng một business DB và JobRepository ở resource khác**, commit audit của một transaction không đủ xác nhận cả hai stores nhất quán. Trace giúp nhìn chỗ lệch nhưng recovery cần idempotency và reconciliation.

## 17. Liên kết spans với JobRepository metadata

Một `JobExecution` chứa các `StepExecution`, và partitioned step có **manager** cùng **worker StepExecutions**. Việc instrument nên luôn biết **loại step** đang quan sát:

~~~text
jobName = nightlySettlement
jobInstanceId = 819
jobExecutionId = 845

manager:
  stepName = settlementManager
  stepExecutionId = 880

worker:
  stepName = settlementWorker:partition3
  stepExecutionId = 884
  partitionName = partition3
  executionContext = {rangeStart:..., rangeEnd:...}
~~~

Các số là ví dụ. `StepExecutionId` **là ID metadata của execution**, không tạo từ trace ID. Trong restart cùng JobInstance, `JobExecutionId` và worker `StepExecutionId` có thể thay đổi, trong khi **logical partition name/snapshot** vẫn cần ổn định.

**Thực hành đặt tags:**

| Metadata | Đặt ở đâu? | Lý do |
| --- | --- | --- |
| `batch.role=manager/worker` | Span attribute/low-cardinality | Phân biệt topology |
| `batch.mode=remote-chunking` | Low-cardinality | So các mô hình |
| `batch.job.name` | Low-cardinality nếu tập job names kiểm soát | Dashboard |
| `batch.step.logical.name` | Low-cardinality nếu đã chuẩn hóa | Phân tích latency theo step |
| `batch.job.execution.id` | Span attribute/log, **không** metric tag | High-cardinality |
| `batch.step.execution.id` | Span attribute/log, **không** metric tag | Join JobRepository |
| `batch.partition.name` | Span attribute/log tùy policy | Có thể high-cardinality nếu per file |
| `batch.chunk.sequence` | Span attribute/log | Rất nhiều giá trị |
| `messaging.destination.name` | Low-cardinality nếu tập tên queue nhỏ | Tìm queue bottleneck |
| `worker.instance.id` | Resource attribute/span/log có ngân sách | Theo dõi node/pod |
| `source.record.id` | Chỉ debug/audit được bảo vệ | Cardinality/PII risk |

**Không đưa toàn bộ `ExecutionContext` vào span**: nó có thể chứa file paths, tenants, tokens, SQL params hoặc những giá trị có kích thước lớn. Chọn allowlist metadata và chuẩn hóa trước khi ghi.

## 18. Span name và attributes nên tuân theo cardinality budget

**Nên:**

~~~text
batch.manager.partition.dispatch
messaging.publish
messaging.receive
batch.worker.partition.process
batch.manager.reply.correlate
batch.worker.chunk.process
batch.worker.chunk.transaction
~~~

**Không nên:**

~~~text
batch.worker.chunk.90442
process-order-customer@example.com
stepExecutionId=884
worker-account-123456789
~~~

Tên operation phải **ổn định**, còn định danh thực thi nằm ở attributes/logs với chính sách sampling/retention. Với một triệu chunks, nếu đặt `chunkSequence` trong metric tag, time-series có thể tăng rất nhanh và gây chi phí exporter/backends.

### Sampling có chọn lọc

Một phương án:

- Tổng hợp **metrics cho mọi request/chunk**, mức cardinality thấp.
- Lấy mẫu traces cho một phần traffic; nâng mẫu khi lỗi/timeout theo khả năng sampler/backend.
- Dùng **tail sampling** ở collector nếu cần giữ các traces lỗi/độ trễ cao, đồng thời đánh giá chi phí bộ nhớ và mất dữ liệu khi collector lỗi.
- Lưu JobRepository/business audit bền vững cho kết quả, không phụ thuộc việc trace được sample hay không.

**Một request không có trace trên UI không đủ kết luận nó chưa được gửi.** Có thể nó bị sampling drop, exporter lỗi hoặc propagation đứt.

## 19. Log correlation qua MDC

Structured logs hỗ trợ tìm sự kiện khi trace sample không được giữ. Một log record hữu ích:

~~~json
{
  "event": "worker_chunk_committed",
  "service": "settlement-worker",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "jobExecutionId": 845,
  "stepExecutionId": 884,
  "chunkSequence": 42,
  "requestCorrelationId": "manager-845/chunk-42",
  "durationMs": 126,
  "outcome": "COMMITTED"
}
~~~

`traceId` và `spanId` nên đến từ **tracing context thực**, không tự suy ra từ `requestCorrelationId`. Spring/Micrometer có thể tự gắn chúng vào MDC khi instrumentation active. Nếu custom thread pool không propagate scope, log trong worker có thể thiếu hoặc mang context của task trước.

**Không đưa item payload/raw SQL/PII vào MDC**. Thread pool tái sử dụng threads nên mỗi context bổ sung phải được restore/clear đúng cách. `MDC.put()` mà không `remove()` trong `finally` có thể gây **rò ngữ cảnh giữa hai JobExecutions**.

## 20. Correlation ID ở request/reply phải độc lập trace

Remote chunking/partitioning thường có request/reply protocol. Manager phải trả lời:

~~~text
Reply này thuộc:
  jobExecutionId nào?
  worker StepExecution hoặc chunk sequence nào?
  request attempt/logical request nào?
  manager instance/route nào?

Trạng thái đó còn hợp lệ hay đã restart/timeout?
~~~

Không lấy trace ID làm khóa duy nhất để match reply. Một trace có thể chứa **nhiều chunk requests**, còn một chunk có thể bị **redeliver** và tạo thêm spans. Không phụ thuộc thứ tự message reply: worker processing time khác nhau khiến replies **đảo thứ tự**.

~~~text
Manager gửi C17, C18, C19
Worker xử lý:
  C18: 100 ms
  C19: 400 ms
  C17: 3.2 s

Reply đến: C18, C19, C17
=> Ghép bằng protocol ID, không ghép theo FIFO hoặc traceId.
~~~

Trace giúp biết **tại sao C17 chậm**; correlation protocol giúp manager **xác định response C17 và cập nhật đúng outcome**. Hai chức năng bổ sung cho nhau, nhưng không thay thế.

## 21. Asynchronous processing: parent-child hay span link?

Trong request/response đồng bộ, một child span thường nằm gọn bên trong thời gian của parent. Nhưng với broker:

~~~text
01:00:00 Manager gửi message; producer span kết thúc.
01:00:10 Message được worker nhận sau 10 giây trong queue.
01:00:25 Worker xử lý và publish reply.
01:00:30 Manager nhận reply.
~~~

Có hai chiến lược tracing phù hợp tùy semantic instrumentation:

1. **Propagate remote parent**: consumer span được tạo trên extracted context, giữ quan hệ nhân quả với producer. Đơn giản khi mỗi message là một work request cụ thể.
2. **Span link**: consumer hoặc background worker span thuộc một trace/lifecycle mới nhưng có link tới producer/message context. Hữu ích với xử lý rất muộn, batch gom nhiều messages, redelivery và fan-in/fan-out.

**Không ép mọi event thành parent-child bằng cách giữ manager span mở hàng giờ**. Một batch job dài nhiều tiếng có thể vượt retention/timeout hoặc làm trace khổng lồ. Nên dùng **nhiều traces có liên kết**, attributes `jobExecutionId/partition` và logs/correlation để tìm lại.

### Khi một worker nhận message gom nhiều nguồn

Nếu một batch operation được tạo từ nhiều input messages, không thể chọn một parent duy nhất đại diện mọi nguồn. **Span links tới các input contexts** diễn tả quan hệ nhiều-đến-một tốt hơn. Khi gửi một message ra nhiều workers, mỗi worker có thể là consumer span cùng linked producer context.

## 22. Thread pools và context propagation trong JVM

Ngay cả **local partitioning**, trace có thể đứt khi manager tạo các tasks rồi giao cho `TaskExecutor`:

~~~text
Manager thread: active trace T
    executor.submit(workerTask)

Thread pool worker-3:
    Không có current trace context nếu executor không được wrap.
    Tạo root span T2 thay vì span liên quan T.
~~~

Với **Micrometer Context Propagation** hoặc context-aware executor, có thể capture/restore tracing context tại lúc submit và scope lại khi task chạy. Cách cấu hình tùy Spring Framework/Boot/Integration version, cần kiểm tra trên executor được `TaskExecutorPartitionHandler` thật sự sử dụng.

**Kiểm thử bắt buộc:** bên trong worker `beforeStep` hoặc handler, đọc current trace context, so với context manager kỳ vọng hoặc xác nhận span link thích hợp. Không chỉ log một tên thread và giả định trace ID tự nối.

### Vì sao MDC đơn thuần chưa đủ?

~~~java
MDC.put("jobExecutionId", Long.toString(jobExecutionId));
executor.execute(workerTask);
~~~

`MDC.put` trên manager thread không bắt buộc lan sang worker thread. Nếu task decorator capture MDC mà quên restore giá trị cũ/clear cuối task, thread pool có thể in **JobExecution ID của request trước**.

**Ưu tiên propagation đồng bộ giữa tracing context và MDC** qua framework/instrumentation; không xây hai hệ copy thủ công có nguy cơ lệch. Nếu cần một custom `TaskDecorator`, kiểm tra chính xác cả **đường throw exception**, thread reuse và nested tasks.

## 23. Retry/redelivery phải tạo quan sát cho từng attempt

Một request có thể được broker gửi hai lần vì ACK bị mất:

~~~text
attempt 1:
  requestId=R42
  worker=A, trace/span consumer A
  business DB COMMIT
  worker chết trước ACK/reply

attempt 2:
  requestId=R42
  worker=B, trace/span consumer B
  business effect đã tồn tại -> idempotent no-op/verified
  reply được gửi lại theo protocol
~~~

Một trace UI đúng có thể hiển thị hai consumer attempts, nhưng **không có nghĩa hai business commits cùng tạo tác động**. Cần:

- Giữ **logical request identity** trong cả hai attempts.
- Ghi nhận `deliveryAttempt` hoặc redelivered flag nếu broker cung cấp đáng tin; không tự phỏng đoán từ trace.
- Tách metrics `messages_received_total`, `business_operations_applied_total` và `idempotency_duplicates_total`.
- Nếu worker B xử lý request mà đã commit ở A, trả outcome hợp lệ sau khi kiểm idempotency/protocol; không phát sinh output lần hai.
- Không phụ thuộc vào span của attempt 1 còn tồn tại vì sampling hoặc exporter có thể drop.

**Quan sát quan trọng:** redelivery là đặc tính transport; **retry Spring Batch** của processor/writer là đặc tính job; **restart JobInstance** là đặc tính framework; ba cơ chế có thể cùng tồn tại nhưng không được coi như một loại attempt duy nhất.

## 24. Reply trễ và out-of-order sau restart

Giả sử manager JobExecution 845 đợi reply partition 3. Worker A bị pause; manager timeout, job bị restart sang JobExecution 846, worker B được điều phối xử lý logical partition theo protocol. Sau đó reply của worker A mới đến.

~~~text
Request A:
  jobExecutionId=845
  workerStepExecutionId=884
  partition=partition3

Request B (restart):
  jobExecutionId=846
  workerStepExecutionId=901
  partition=partition3

Reply A đến sau Reply B.
~~~

**Không để tracing correlation “nối được trace” dẫn đến việc manager chấp nhận reply A vào 846.** Protocol phải kiểm execution identity/partition/chunk và trạng thái hiện tại; reply stale phải được ghi metric/log và xử lý theo contract.

Các mốc nên trace:

1. `manager.request.dispatched`: execution/partition IDs.
2. `manager.request.timed_out`: timeout và pending request state.
3. `manager.job.restarted`: JobInstance ID giữ nguyên, JobExecution ID mới.
4. `worker.reply.published`: worker execution nào gửi response.
5. `manager.reply.rejected_stale` hoặc `manager.reply.correlated`: quyết định cuối.

**Một reply bị đánh dấu stale không chứng minh DB worker A rollback.** Có thể business effects đã commit trước khi reply bị từ chối. Reconciliation và idempotency/fencing vẫn cần.

## 25. Nhiều manager dùng chung broker và reply routing

Khi hai manager instances cùng consume reply queue, có thể xảy ra **manager M2 nhận reply thuộc pending request của M1**. Nếu routing/correlation không được thiết kế, M1 tiếp tục timeout mặc dù worker đã phản hồi.

~~~mermaid
flowchart LR
    M1["Manager M1: request R1"] --> MQ[("Work broker")]
    M2["Manager M2: request R2"] --> MQ
    MQ --> W["Worker"]
    W --> RQ[("Reply broker")]
    RQ --> M1
    RQ --> M2
~~~

**Một trace giúp thấy reply đã được gửi và process nào nhận**; nó **không tự sửa routing**. Cần request/reply protocol có `replyTo`, partition/channel routing, correlation registry hoặc setup consumer topology đảm bảo replies đến đúng owner, tùy broker và Spring Batch Integration configuration.

### Câu hỏi khi gặp lỗi

- Reply queue có nhiều competing consumers không?
- Message có `replyTo` và correlation metadata đầy đủ khi lên broker không?
- Consumer M2 có log `unknown correlation` mà M1 lại timeout không?
- Manager bị restart đã mất pending registry in-memory chưa?
- `ChunkResponse/StepExecution` nào đã commit trạng thái nhưng reply vẫn in-flight?

**Không gửi cùng reply cho mọi manager rồi mong trace ID giúp họ tự hiểu** nếu protocol chưa quy định dedup/fencing. Tracing chỉ là quan sát, không thay routing hay durable pending state.

## 26. Spring Integration gateway và middleware error flow

Một request có thể không đến worker vì:

~~~text
Manager integration gateway
  -> output channel
  -> header mapper/converter
  -> broker publish
  -> queue/routing key
  -> inbound adapter
  -> worker handler
~~~

**Mỗi đoạn cần phân biệt “đã gọi API” và “đã được nhận”:**

| Mốc | Bằng chứng nên lưu | Khi không có worker span |
| --- | --- | --- |
| Channel send | Observation/event từ manager | Xem adapter/subscriber |
| Broker publisher confirm | Broker xác nhận publish theo API | Xem routing/queue/mandatory return |
| Queue depth/age | Broker metrics | Xem backlog/consumer availability |
| Consumer delivery | Inbound adapter/span/log | Xem filters/deserialize errors |
| Worker handler invocation | Worker process span | Xem channel thread/errorChannel |
| Worker business commit | DB transaction/ledger | Nếu thiếu, không suy ra success từ delivery |
| Reply producer confirm | Reply broker metrics/producer instrumentation | Nếu không có, xem worker error flow |
| Manager reply consume | Inbound reply adapter/correlation log | Nếu có, xem wrong registry/stale reply |

Spring Integration `errorChannel` và error handler có thể nhận exception của asynchronous flow; lỗi ở đó phải có **trace context hoặc link hợp lệ**, không chỉ một log stack trace không có request ID. Nhưng không được catch/log rồi trả `COMPLETED` giả; error path vẫn cần cập nhật Spring Batch outcome theo protocol.

## 27. Khi nào một trace bị “đứt” giữa manager và worker?

| Triệu chứng | Nguyên nhân thường gặp | Kiểm chứng |
| --- | --- | --- |
| Manager trace có producer span, worker có root trace mới | Thiếu trace context injection/extraction | Quan sát raw message headers và worker extractor |
| `traceparent` có trên Spring `MessageHeaders` nhưng không có trên broker | HeaderMapper/converter làm mất header | Test wire-level AMQP/Kafka/JMS |
| Worker logs có đúng trace ID nhưng backend không nối spans | Chỉ copy string/MDC, không activate parent/link | Kiểm SDK/propagator/consumer span |
| Worker có trace nhưng reply là root trace mới | Không inject context ở reply publish | Kiểm reply adapter/callback |
| Local worker thread bị thiếu trace ID | Executor không propagate thread-local scope | Test TaskExecutor context |
| Trace không xuất hiện ở backend | Sampling/exporter/collector lỗi | Telemetry pipeline metrics/logs |
| Spans đúng nhưng manager vẫn timeout | Reply routing/correlation sai | So request IDs, replyTo, pending registry |
| Traces lặp cùng request ID | Broker redelivery/retry hoặc duplicate send | Kiểm delivery attempts + business ledger |
| Span “SUCCESS” nhưng DB rollback | Gắn success tại writer invocation | Instrument transaction outcome thực |
| Một trace chứa hàng triệu spans và bị cắt | Quá granular hoặc trace sống quá lâu | Span per chunk/partition, sampling/links |

**Các bước kiểm tra theo thứ tự:** (1) có producer span? (2) request thực sự tới broker? (3) wire headers? (4) worker extraction? (5) worker business outcome? (6) reply publication? (7) manager correlation? (8) exporter/sampler? Làm theo chuỗi giúp tránh kết luận sai “mất trace nên message không đến”.

## 28. Metrics phục vụ cùng một câu chuyện

Tracing có thể bị sampled; metrics tổng hợp nên bao phủ mọi operation theo kiến trúc:

| Metric | Phân biệt điều gì? | Ngưỡng/cảnh báo ví dụ |
| --- | --- | --- |
| `batch_manager_requests_dispatched_total` | Manager tạo/gửi request | Đột biến/trễ theo throughput kỳ vọng |
| `batch_manager_requests_pending` | Request chưa có outcome | Tăng kéo dài, chạm deadline |
| `messaging_publish_failures_total` | Lỗi gửi lên broker | Any sustained non-zero |
| `messaging_queue_age_seconds` | Thời gian chờ trong queue | P95/P99 vượt SLA |
| `worker_requests_received_total` | Consumer đã nhận message | Không tương ứng dispatch trong cửa sổ đủ dài |
| `worker_processing_duration_seconds` | Worker compute/DB | P95/P99 tăng |
| `worker_db_commit_duration_seconds` | Commit/lock contention | Tăng dù queue age thấp |
| `worker_transaction_rollbacks_total` | DB rollback/retry | Spike sau deploy/load |
| `worker_replies_published_total` | Worker đã publish reply | Thấp hơn committed operations cần điều tra |
| `manager_replies_correlated_total` | Reply khớp request hợp lệ | Thấp hơn replies received |
| `manager_replies_stale_total` | Reply trễ/sai execution | Tăng khi restart/timeout |
| `broker_redelivery_total` | Transport retry/ACK uncertainty | Spike khi worker crash |
| `job_step_execution_failed_total` | Step metadata thất bại | Nhìn theo role/logical step |
| `worker_outcome_unknown_total` | Commit/ACK không xác định | Cần reconciliation |
| `telemetry_export_failures_total` | Trace exporter/collector lỗi | Traces có thể mất dù job chạy |

**Lưu ý tính toán:** đừng đòi `requests dispatched == replies correlated` tại mọi thời điểm vì in-flight, timeouts, skips, failed messages và retries; cần biết **cửa sổ thời gian, logical ID và transport semantics**. Cũng không dùng retry-attempt counts như logical business operation counts.

### Các breakdown hữu ích

~~~text
manager send latency
  + broker queue/transport wait
  + worker receive/deserialize
  + worker business processing
  + DB transaction/commit
  + reply publish/transport
  + manager receive/correlation delay

  ~= end-to-end observed request duration
~~~

Dấu `~=` nhấn mạnh clocks/overlap và các phép đo có thể **không cộng chính xác**. Đặc biệt timestamps từ các hosts khác nhau có clock skew; nên dùng span durations/monotonic clocks cho thời gian trong process và đồng bộ thời gian để so các mốc giữa hosts.

## 29. Tách performance problem khỏi correctness problem

Một worker chậm có thể do nhiều nguyên nhân có hành động xử lý khác nhau:

| Trace/metric pattern | Giải thích khả dĩ | Hành động kiểm chứng |
| --- | --- | --- |
| Queue wait cao, worker process thấp | Thiếu consumers, broker backlog | Kiểm worker count, prefetch/consumer concurrency |
| Worker process cao, CPU cao | CPU-bound processor | Profile/scale workers, kiểm GC |
| Worker process cao, DB wait cao | DB bottleneck/index/locking | Query plan, pool/lock metrics |
| Manager build chunk chậm, worker rảnh | Reader/serialization manager bottleneck | Profile manager reader, size/prefetch |
| Request publish nhanh, reply lâu | Worker/reply routing hoặc timeout | Xem worker span + reply queue |
| Duplicates/redeliveries tăng | ACK uncertainty, worker crash | Kiểm broker/config và idempotency |
| StepExecution COMPLETED nhưng output thiếu | Data correctness/skip/filter/commit config | Reconcile, không tăng worker vội |
| Exporter lỗi, trace không hiện | Observability pipeline hỏng | Kiểm collector/exporter, không suy ra job hỏng |

**Tăng số worker không luôn cải thiện throughput**: nếu DB là nút thắt, thêm worker có thể tăng lock contention/pool wait, kéo dài P99. Dùng trace để tìm **chặng chiếm latency lớn nhất**, rồi chạy benchmark có đối soát business output.

## 30. Bảo mật và bảo vệ trace context

Headers như `traceparent`/`tracestate`/`baggage` đi qua biên dịch vụ, vì vậy:

- **Không cho phép upstream bất kỳ nhét arbitrary baggage** chứa PII/credentials vào hệ thống nội bộ. Baggage có thể lan sang nhiều services/exporters.
- Dùng allowlist/size limit cho custom baggage, không copy toàn bộ `JobParameters` hoặc `ExecutionContext` vào headers.
- Không gắn raw item payload, account number, email, full file path chứa thông tin nhạy cảm, SQL bind values hay token vào span attributes.
- Trên boundary không tin cậy, có thể quyết định **không tin/khởi tạo trace context mới** và dùng link/log reference theo threat model; không để dữ liệu trace ảnh hưởng authorization.
- Không dùng trace ID, correlation ID hay header `replyTo` làm bằng chứng người gửi đã được xác thực hoặc có quyền xử lý một tenant.
- Giới hạn quyền truy cập tracing backend/logs, retention và audit ai xem trace chứa metadata vận hành.
- Không echo/broadcast headers không được phép qua middleware reply; kiểm outbound mapper.
- Tránh **span names/tags chứa unbounded cardinality** có thể bị người gửi bên ngoài lợi dụng tạo chi phí telemetry.
- Theo dõi exporter buffer/sampling và rate limits, để telemetry không gây backpressure trực tiếp lên xử lý nghiệp vụ.

**Telemetry phải hỗ trợ production, không làm job thất bại chỉ vì collector tạm unavailable** trừ khi tổ chức có một compliance contract đặc biệt được thiết kế và kiểm thử riêng.

## 31. Test local partitioning: context không đứt khi đổi thread

Trước khi test broker, nên có một bài test đơn giản cho **manager → TaskExecutor → worker StepExecution** trong cùng JVM:

~~~text
Manager start Observation/Span với traceId=T.
Partitioner tạo 4 ExecutionContexts.
TaskExecutorPartitionHandler dispatch các workers.
Worker:partition0 và worker:partition1 ghi log traceId.
Assert:
  ít nhất hai worker thực sự chạy đồng thời,
  worker trace context được propagate hoặc link hợp lệ,
  mỗi worker có StepExecutionId/partitionName riêng,
  business output đúng tập expected.
~~~

**Không dùng `InheritableThreadLocal` như lời giải chung**: pool threads được tạo/reuse khác lúc submit task; context của request mới có thể không được truyền và context cũ có thể rò sang task kế tiếp.

### Chọn Test-only probe phù hợp

Gắn `StepExecutionListener` vào **worker step** để log/thu các metadata:

~~~java
final class WorkerTraceProbe implements StepExecutionListener {
    private final ConcurrentMap<Long, String> observedTraceIds =
            new ConcurrentHashMap<>();
    private final Tracer tracer;

    WorkerTraceProbe(Tracer tracer) {
        this.tracer = tracer;
    }

    @Override
    public void beforeStep(StepExecution execution) {
        Span active = tracer.currentSpan();
        observedTraceIds.put(
                execution.getId(),
                active == null ? "MISSING" : active.context().traceId());
    }

    Map<Long, String> snapshot() {
        return Map.copyOf(observedTraceIds);
    }
}
~~~

**Giới hạn:** listener chỉ ghi current span tại thời điểm `beforeStep`; nếu tracing instrumentation cố tình bắt đầu span **sau** callback này, `MISSING` chưa tự chứng minh cả worker không có trace. Đặt probe vào **đúng thời điểm** sau extraction/wrapping mà hệ thống cam kết. Tracer bean phải được cấu hình; tên `Span` trong ví dụ là `io.micrometer.tracing.Span`.

**Assertion phải phù hợp propagation policy:** nếu local TaskExecutor giữ cùng trace, trace IDs nên tương ứng trace manager; nếu thiết kế dùng new trace + span links, hãy kiểm link thay vì ép equality. Đừng ghép tất cả worker steps vào một span duy nhất rồi che mất concurrency.

## 32. Test wire-level: traceparent phải qua broker thật

Một integration test tối thiểu cho remote chunking:

1. Khởi động broker thật bằng Testcontainers hoặc môi trường tích hợp kiểm soát, cùng manager JVM và worker JVM tách biệt.
2. Cài tracing bridge/exporter test và một collector/in-memory exporter **phù hợp SDK**.
3. Manager tạo request với `requestCorrelationId` ổn định, instrumentation inject W3C `traceparent`.
4. Test intercept/inspect **message headers ở broker hoặc consumer adapter**, không chỉ Spring `MessageHeaders` tại sender.
5. Worker extract context, ghi span consumer và worker processing.
6. Worker ghi business output idempotent, commit, publish reply có correlation đúng.
7. Manager nhận reply, cập nhật request outcome; query JobRepository/DB để xác minh logic.
8. Lấy spans đã export, kiểm producer/consumer relationship **parent hoặc link theo policy**.

### Contract assertions

~~~text
assert request.messageHeaders contains valid W3C traceparent
assert worker extracted trace context (not randomly generated context)
assert producer/consumer spans are related by parent/link
assert requestCorrelationId is identical across logical request/reply
assert manager's reply correlation accepts correct execution/chunk
assert business ledger has exactly one logical effect
assert JobRepository outcome matches committed worker result
~~~

**Không giả định span export là đồng bộ**: SDK có thể buffer trước khi gửi; integration test phải flush/await exporter với timeout và cleanup để tránh flaky tests. Test một broker riêng/quarantine queues sau test; không dùng production topic/queue.

### Một pseudo-test có chủ đích tách helpers

~~~java
@Test
void remoteChunkingCarriesTraceAndCorrelatesReply() throws Exception {
    String batchKey = "it-trace-remote-chunk-001";
    long chunkSequence = 17L;

    var send = testManager.dispatchChunk(batchKey, chunkSequence);
    var requestOnWire =
            testBrokerProbe.awaitRequest(send.requestId());

    assertNotNull(requestOnWire.header("traceparent"));
    assertEquals(send.requestId(),
            requestOnWire.header("requestCorrelationId"));

    var reply = testManager.awaitCorrelatedReply(send.requestId());
    assertEquals(send.requestId(), reply.correlationId());
    assertTrue(reply.matchedExpectedExecution());

    testTraceExporter.awaitRelatedProducerConsumerSpans(
            send.requestId());
    testBusinessRepository.assertLogicalChunkEffectsCorrect(
            batchKey, chunkSequence);
}
~~~

**Các lớp `testManager`, `testBrokerProbe`, `testTraceExporter` và `testBusinessRepository` là fixtures cần tự triển khai**; code này minh họa **hợp đồng assertions**, không phải bộ API do Spring Batch cung cấp. Test phải có deadline rõ và xử lý sampling (thường chọn sampler always-on trong test).

## 33. Test mất header, converter và reply path

Tạo các negative cases sau:

| Case | Lỗi cố ý | Test cần phát hiện |
| --- | --- | --- |
| N01 | Outbound mapper loại `traceparent` | Broker request thiếu header; worker root trace mới |
| N02 | Tracestate/baggage bị drop | Propagation còn trace nhưng vendor/baggage policy thay đổi có kiểm soát |
| N03 | Kafka header encoding sai | Worker không extract được context |
| N04 | JMS property mapper reject tên header | Missing context, error rõ |
| N05 | Worker custom converter tạo new message không copy headers | Worker span tách khỏi producer |
| N06 | Reply mapper bỏ correlation header | Manager timeout/unknown reply dù trace còn |
| N07 | Reply mapper bỏ trace context | Reply trace bị tách; correlation vẫn phải đúng |
| N08 | TaskExecutor không propagate context | Local worker span trở thành root |
| N09 | Exporter tắt | Job vẫn đúng; tracing backend không nhận spans |
| N10 | Sampling xác suất thấp | Metrics và JobRepository vẫn phản ánh đầy đủ |

**N06 đặc biệt quan trọng:** mất correlation có thể làm **sai workflow**, không chỉ mất telemetry. N01/N07 thường chủ yếu gây đứt trace, trừ khi custom logic có coupling sai với tracing. Test phải thể hiện sự khác nhau đó.

### Kiểm tra header size

Nếu baggage phát triển thành một tập hàng trăm trường, broker hoặc downstream adapter có thể từ chối header quá lớn. Test boundary với limit của broker và allowlist; không đưa raw JobParameters/payload vào baggage chỉ để debug.

## 34. Test lỗi worker, rollback và redelivery

Một ma trận failure injection:

| Kịch bản | Điểm gây lỗi | Evidence cần đối chiếu |
| --- | --- | --- |
| F01. Worker crash trước read | Sau broker delivery | Consumer started, no business effect, message requeue theo policy |
| F02. Crash trước DB commit | Writer chạy nhưng transaction chưa commit | Processing span có thể tồn tại, business DB không có effect |
| F03. Crash sau commit trước reply | Business DB bền vững, reply vắng | Redelivery attempt mới; writer idempotent, manager không fake success |
| F04. Reply broker unreachable | Worker đã xử lý xong | Reply publish failure, pending manager request tăng |
| F05. Reply trễ sau restart | Execution ID đã đổi | Manager từ chối stale reply; trace có link/reference cũ |
| F06. Duplicate reply | Cùng request reply hai lần | Một logical completion, duplicate metric |
| F07. Out-of-order replies | C17 chậm hơn C18 | Match đúng chunk sequence/execution, không FIFO |
| F08. Consumer deserialize failure | Message sai schema | Error flow/DLQ khác business skip, không có worker commit |
| F09. Broker redelivery | Inbound ACK không được xác nhận | Nhiều attempt spans, một logical business effect |
| F10. DB lock timeout | Worker xử lý nhưng DB chậm | DB wait span/metrics, bounded retry/fail |
| F11. Quarantine insert fail | Record skip không lưu được bằng chứng | Không COMPLETED giả; worker failure policy |
| F12. Telemetry collector down | Traces không xuất được | Business job vẫn chạy theo policy, export failure metric |

**Một test “crash” bằng cách throw `RuntimeException` trong worker không tương đương kill process**. Khi process bị kill sau DB commit nhưng trước reply, transaction/ACK/StepExecution metadata có thể còn ở trạng thái khác. Tối thiểu nên có **một test end-to-end kill worker JVM** đúng mốc và xác minh recovery qua database/broker.

## 35. Test span timing: không dùng đồng hồ các máy như nhau tuyệt đối

Trong multi-JVM, mỗi host/pod có clock riêng. Nếu lấy manager send timestamp trừ worker receive timestamp trong ứng dụng, kết quả có thể **âm hoặc sai lệch lớn** khi clocks không đồng bộ.

**Nên:**

- Dùng `Duration` đo bằng monotonic clock trong **một process** cho đoạn local.
- Dùng broker queue age/lag metrics khi broker cung cấp mốc đáng tin.
- Đồng bộ NTP/clock và kiểm tolerance khi kết hợp wall-clock timestamps nhiều hosts.
- Khi xem distributed trace, nhận biết backend có thể vẽ spans lệch do clock skew.
- Không trừ tùy tiện span start timestamps của hai hosts để kết luận 20 giây queue wait nếu clock chưa được kiểm chứng.

Một trace chặng:

~~~text
manager.publish attempt:       5 ms (local)
broker queue age:             19 s  (broker metric)
worker process:               70 ms (worker local)
worker DB commit:            300 ms (worker local)
reply publish:                10 ms (worker/broker instrumentation)
manager reply handling:        4 ms (manager local)
~~~

Nếu end-to-end latency là 20 giây, broker wait có thể là nút thắt chính. Nhưng phải so cùng request ID và timeframe, không dùng p99 của các request khác nhau như một phép cộng chính xác.

## 36. Dashboard theo vai trò manager và worker

Dashboard hữu ích nên đặt cạnh nhau:

**Manager pane**

- JobExecution/StepExecution status hiện tại và số partitions/chunks đã dispatch.
- Pending request count, oldest pending age và request timeout rate.
- Reply received/correlated/stale/unknown counts.
- Manager reader/serialization/publish durations, outbound errors.
- Trace links cho những requests chậm nhất theo correlation ID **trong logs** (không dùng ID làm metric labels).

**Broker pane**

- Request/reply queues: backlog, oldest message age, consumers, delivery/redelivery.
- Publisher confirms, connection/channel errors, dead-letter queue depth.
- Kafka lag/rebalance/partition metrics hoặc JMS provider metrics tương ứng.
- Có đủ capacity và permissions theo transport.

**Worker pane**

- Active workers, executor/consumer concurrency và request handling latency.
- Processor/writer/DB commit duration, transaction rollback/retry.
- Business effect applied/dedup/unknown.
- Worker StepExecution states và failures.
- Trace exemplars/samples cho slow/error outcomes.

**Quality pane**

- Input/output record counts **và** key/value reconciliation status.
- Skip/retry/quarantine theo policy; output idempotency conflicts.
- Job restart age, outcome unknown, publication gate.

**Không dùng một dashboard đẹp để thay `JobRepository` hay business validation**. Metrics/traces có thể mất hoặc sample; metadata/ledger giữ evidence cuối cùng.

## 37. Runbook: manager chờ worker nhưng không thấy reply

1. **Khoanh vùng** `JobInstanceId`, `JobExecutionId`, manager `StepExecutionId`, `partitionName/chunkSequence`, request correlation ID và thời điểm dispatch.
2. **Kiểm manager trace/log**: request build/send span đã chạy? publish API báo lỗi hay broker đã confirm?
3. **Kiểm broker**: queue depth, oldest age, consumer count, DLQ/deserialize failures, routing key và `replyTo`.
4. **Kiểm wire trace headers**: `traceparent` có qua outbound adapter/mapper không? Nếu không, là lỗi observability nhưng message có thể vẫn đang được xử lý.
5. **Kiểm worker**: worker JVM/pod nào nhận, consumer span bắt đầu chưa, step/chunk nào đang active, errorChannel có exception không?
6. **Kiểm transaction**: DB effect đã commit, rollback, hay outcome chưa chắc chắn? Query business ledger và StepExecution, không suy từ một `writer.write` span.
7. **Kiểm reply**: worker đã publish chưa, broker có reply message không, inbound reply adapter của manager có nhận không?
8. **Kiểm correlation**: request/reply IDs, job/step/chunk execution identity và pending registry; có unknown/stale reply ở manager khác không?
9. **Kiểm retry/restart**: có broker redelivery, manager timeout, JobExecution mới hoặc worker cũ vẫn chạy không?
10. **Chọn xử lý an toàn**: retry theo protocol có idempotency, reconcile metadata, quiesce/fence stale worker trước khi dispatch lại, hoặc fail/alert nếu outcome không rõ.
11. **Xác nhận hoàn tất**: JobRepository và business output có trạng thái đúng; reply đến đúng logical request; không duplicate effects.
12. **Đóng incident**: ghi root cause, latency breakdown, idempotency conflicts, exporter/header mapping issues và test cần bổ sung.

### Ví dụ A — worker commit xong, reply mất

~~~text
manager request R42: DISPATCHED, pending 120 s
broker request: delivered, ACK status uncertain
worker trace: process done, db.commit verified
reply queue: publish failed
business ledger: operation R42 already applied

=> Không replay mù quáng để “đẩy lại dữ liệu”.
   Retry/reconcile theo request protocol, writer idempotent,
   manager chỉ complete khi có outcome hợp lệ.
~~~

### Ví dụ B — không thấy worker trace

~~~text
manager producer span: OK
broker request: còn trong queue 30 s
consumer count: 0
worker traces: không có

=> Nhiều khả năng worker chưa nhận message, xem consumer
   availability/routing/permissions. Không kết luận
   "worker process chậm" chỉ từ manager timeout.
~~~

**Không xóa queue, sửa JobRepository thành COMPLETED hoặc tăng timeout vô hạn** khi chưa đối soát trạng thái commit và source of truth.

## 38. Anti-patterns khi trace manager worker

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `traceId` làm request correlation ID | Nhiều requests cùng trace, reply bị match sai | Correlation protocol độc lập |
| Chỉ thêm `traceId` vào log | Không có producer/consumer links trên backend | Instrument/extract/inject context thực |
| Gắn span `SUCCESS` trong `ItemWriter.write` | Rollback sau writer vẫn hiện success | Đo commit outcome riêng |
| Giữ span manager mở hàng giờ cho mọi chunks | Trace khổng lồ, timeout/retention | Span per request/partition, links cho async |
| Một span cho mỗi item ở job 10 triệu records | Telemetry overload/high cost | Span per chunk/partition và sampling |
| Cho mọi JobParameters vào baggage | PII/secret leak, header quá lớn | Allowlist, bounded baggage |
| Chỉ kiểm message headers trước adapter | Broker mapper có thể đã drop context | Wire-level tests |
| Giả định mọi Spring Integration adapter auto-trace | Mất parent context khi đổi transport | Kiểm instrumentation theo version/topology |
| Tin `reply ACK == DB COMMIT` | Success giả hoặc duplicate retries | Phân biệt milestones và business ledger |
| Không giữ JobExecution/StepExecution metadata | Khó phân biệt restart/late reply | Gắn IDs vào logs/span attributes |
| Dùng IDs mỗi chunk làm metric tags | Cardinality bùng nổ | Low-cardinality labels |
| Không propagate qua executor | Worker root trace/missing MDC | Context-aware executor/test |
| Không clear MDC sau task | Logs lẫn JobExecution khác | Scope restore/cleanup |
| Chỉ test `DirectChannel` cùng JVM | Không phát hiện broker header/ACK/reply lỗi | Multi-process broker integration |
| Traces sampled mất nên nói request không gửi | Kết luận sai | Broker metrics + JobRepository/ledger |
| Retry request không idempotent | Double business effect | Stable logical operation key + sink dedup |

## 39. Bài thực hành cuối bài

Thiết kế hai jobs Spring Batch trên **Java 17+/Spring Batch 5.x**, dùng **hai manager/worker JVMs** và RabbitMQ (hoặc Kafka/JMS được cấu hình tương đương), mỗi job có dataset bất biến và business output replay-safe.

**Phần A — remote chunking**

1. Manager đọc 10.000 items, chia chunks 200, gửi request với `requestCorrelationId` và W3C context.
2. Worker extract context, tạo consumer/process spans, commit DB và publish reply.
3. Instrument manager dispatch, worker receive, worker processing/commit, reply publish, manager correlate.
4. Xác minh producer và worker spans có parent/link đúng; correlation ID độc lập trace ID.
5. Tạo ba chunks có processing times khác nhau để replies đảo thứ tự; manager vẫn match đúng.
6. Kill worker sau DB commit trước ACK/reply và để broker redeliver; business effects không nhân đôi.

**Phần B — remote partitioning**

7. Manager tạo bốn stable partitions, mỗi worker nhận `StepExecutionRequest` với context metadata phù hợp.
8. Trace worker `StepExecution` begin/end và các chunk commits; đối chiếu JobRepository.
9. Tạo failure ở partition3; kiểm manager aggregate đúng failure và worker khác có thể đã commit.
10. Restart JobInstance, phân biệt JobExecution IDs/StepExecution IDs cũ và mới; reject stale reply.

**Phần C — observability**

11. Cố tình drop `traceparent` ở một adapter; detect missing context bằng test wire-level.
12. Cố tình drop reply correlation header; chứng minh trace đúng **không** cứu được protocol.
13. Thử exporter/collector không sẵn sàng; business job vẫn giữ kết quả đúng, metric export failure báo lỗi.
14. Lặp với sampling 10% và always-on trong test; quan sát khác biệt cost và dữ liệu JobRepository.
15. Đo queue wait, worker CPU/DB commit, reply latency và xác định bottleneck có căn cứ.

**Tiêu chí đạt:** có bằng chứng end-to-end qua **process/broker boundary**, request/reply correlation đúng, spans mô tả trung thực các mốc, worker retry/restart không tạo side effect trùng, dashboard có metrics đủ cho unsampled requests và logs không rò rỉ dữ liệu nhạy cảm.

## 40. Checklist trước production

- [ ] Xác định topology chính xác: local partitioning, remote partitioning hay remote chunking.
- [ ] Có trace/observation ở manager dispatch, broker publish/receive, worker processing, reply và manager correlation.
- [ ] Phân biệt trace/span ID với correlation ID, JobExecution/StepExecution, partition/chunk và business idempotency key.
- [ ] Spring Boot/Batch/Integration/Micrometer instrumentation và exporter đã được xác minh **theo version đang chạy**.
- [ ] W3C `traceparent/tracestate` được inject/extract qua **wire headers**; baggage có policy.
- [ ] Context được propagate khi `TaskExecutor` chuyển thread; MDC không lẫn dữ liệu giữa tasks.
- [ ] Span operation được đặt tên ổn định, low-cardinality và có span links phù hợp asynchronous/redelivery.
- [ ] Không gắn status business COMMITTED từ reader/processor/writer invocation trước transaction commit.
- [ ] ACK, reply publish, reply receive, manager correlate và StepExecution final outcome có signals riêng.
- [ ] Late/duplicate/out-of-order replies được nhận biết theo protocol ID; restart không match sai execution.
- [ ] Multi-manager reply routing được kiểm thử; unknown correlation được báo.
- [ ] Có idempotent sink và business reconciliation cho retry/redelivery/commit-unknown.
- [ ] Metrics không phụ thuộc trace sampling, tách request attempts và logical business effects.
- [ ] Tracing exporter failure không làm mất business correctness.
- [ ] Không đưa raw payload, secrets, PII, unbounded IDs vào span name/metric labels/baggage.
- [ ] Có test hai JVM/process và broker thật, wire-level header mapping, reply path và worker kill.
- [ ] Có test lost context, stale reply, redelivery, rollback sau writer và exporter outage.
- [ ] Có dashboard manager/broker/worker/quality; dùng JobRepository/ledger làm nguồn outcome.
- [ ] Có runbook điều tra theo dispatch → broker → worker → transaction → reply → correlation.
- [ ] Đo latency, queue backlog, DB wait và throughput trước khi quyết định tăng workers.

**Ghi nhớ:** **Trace manager worker interaction** không chỉ là hiển thị một `traceId` trên log. Trong Spring Batch scaling, phải nhìn được **đường đi request/chunk/partition từ manager qua middleware đến worker rồi trở lại**, phân biệt từng mốc **send–receive–process–commit–reply–correlate** và giữ trace context đúng qua network/thread boundaries. Correlation ID, JobRepository, business idempotency và reconciliation vẫn quyết định tính đúng; tracing, metrics và logs giúp **tìm nơi chậm, nơi lỗi và nơi thiếu bằng chứng** để vận hành batch song song/phân tán an toàn.
