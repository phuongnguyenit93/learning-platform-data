# Correlation ID trong distributed flow

Khi một Spring Batch manager gửi hàng nghìn yêu cầu qua RabbitMQ, Kafka hoặc JMS cho nhiều worker JVM, các response hiếm khi trở về theo đúng thứ tự đã gửi. Worker xử lý nhanh có thể trả lời trước worker được dispatch sớm; broker có thể redeliver message sau khi ACK mất; manager có thể restart trong lúc một reply cũ còn nằm trong queue. Nếu lấy **vị trí response trong danh sách** làm vị trí của request, hoặc dùng một correlation ID quá mơ hồ như `chunk-17`, manager sẽ dễ đánh dấu sai chunk, chờ vô hạn một kết quả đã có, hoặc ghi nhận thành công cho **JobExecution khác**.

**Correlation ID trong distributed flow** là định danh được sử dụng để **nối một phản hồi/sự kiện với đúng yêu cầu hoặc đơn vị công việc logic** tại ranh giới bất đồng bộ. Nó không tự bảo đảm message được giao đúng một lần, không phải distributed lock và không xác nhận transaction nghiệp vụ đã commit. Giá trị thực sự xuất hiện khi correlation ID được đặt trong **một giao thức hoàn chỉnh**: identity đủ phân biệt, durable pending state khi cần, quy tắc duplicate/stale/timeout, bước đối soát business output và kết quả Spring Batch.

Bài thuộc chương **Observability** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng đến mở rộng Spring Batch trên workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán; đo nút thắt, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực. Bài này tập trung vào **correlation và quan sát distributed flow** trong **remote chunking, remote partitioning, Spring Integration và messaging middleware**; phân biệt điều phối đúng với việc chỉ gắn một ID vào log.

> **Thông điệp cốt lõi:** **correlation ID trả lời “reply này thuộc request nào?”**, không trả lời “business effect đã được áp dụng đúng một lần chưa?”. Hai câu hỏi cần hai cơ chế khác nhau nhưng phải đối soát được với nhau.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `correlationId` với `traceId`, `messageId`, `requestId`, `JobInstanceId`, `JobExecutionId`, `StepExecutionId`, `partitionName`, `chunkSequence` và `businessOperationId`.
2. Xác định **đơn vị cần correlate** trong remote chunking và remote partitioning, khác nhau ra sao với local partitioning.
3. Thiết kế một key đủ namespace để phân biệt các jobs, executions, steps, partitions, chunks và nguồn dữ liệu.
4. Truyền đúng correlation metadata qua Spring Messaging/Spring Integration, AMQP/RabbitMQ, JMS và Kafka, kể cả reply/error path.
5. Dựng manager-side pending registry; biết khi nào in-memory map đủ và khi nào cần **durable request/reply ledger**.
6. Xử lý **out-of-order, duplicate, late, unknown và conflicting replies** mà không làm thay đổi outcome sai.
7. Phân tích crash windows giữa broker publish, DB commit, ACK, worker reply, manager correlation và JobRepository update.
8. Kết hợp correlation với retry/redelivery/restart và **business idempotency/fencing**, tránh lẫn transport identity với logical operation identity.
9. Gắn correlation vào structured logs, distributed trace spans và metrics mà không tạo high-cardinality tags hoặc lộ dữ liệu.
10. Viết JUnit/SQL/broker integration tests và runbook để điều tra timeout, missing reply, manager restart hoặc hai managers tranh reply queue.

**Bối cảnh ví dụ:** Job `dailySettlement` có `JobInstanceId=819` và `JobExecutionId=845`. Manager gửi 400 `ChunkRequest`, mỗi chunk chứa 200 records, tới ba worker JVM. Chunk 18 hoàn tất trước chunk 17; worker xử lý chunk 19 commit DB rồi chết trước khi gửi reply; một reply của execution 844 còn trong broker được deliver trễ. Manager phải xác định **đúng response của execution 845**, không nhân đôi hiệu ứng khi chunk 19 được retry, đồng thời không để reply 844 đánh dấu chunk hiện hành thành công.

## 2. Correlation trong hệ thống bất đồng bộ

Trong lời gọi phương thức đồng bộ, caller thường có stack frame chờ return của chính phương thức đã gọi. Qua messaging, manager **gửi request rồi làm việc khác**; nhiều replies có thể về ở những thread, queue, node và thời điểm khác nhau. Cần một key liên kết **request gửi đi** với **reply nhận được**.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Request Queue
    participant A as Worker A
    participant B as Worker B
    participant R as Reply Queue
    M->>Q: Request R17 (chunk 17)
    M->>Q: Request R18 (chunk 18)
    Q->>A: R17
    Q->>B: R18
    B->>R: Reply R18
    R-->>M: Reply R18
    Note over M: Update pending R18, R17 vẫn chờ
    A->>R: Reply R17
    R-->>M: Reply R17
    Note over M: Update pending R17
~~~

**Không được giả định:** broker delivery FIFO nghĩa worker completion FIFO; một worker xử lý lâu hơn cũng làm reply đảo thứ tự. Ngay cả khi transport giữ thứ tự **trong một partition/session theo điều kiện riêng**, hệ thống nhiều worker và retry vẫn có thể hoàn tất lệch thứ tự.

## 3. Phân biệt các loại định danh

| Định danh | Phạm vi/nguồn | Vai trò | Không dùng thay |
| --- | --- | --- | --- |
| **Correlation ID** | Request/reply protocol | Ghép response với logical request/pending slot | Business dedup key nếu không có hợp đồng riêng |
| **Message ID** | Broker/provider hoặc app | Nhận diện một message envelope/delivery | Logical request bền qua retry/republish |
| **Request attempt ID** | App mỗi lần publish/dispatch | Audit một lần thử gửi | Logical request nếu attempt đổi mà work không đổi |
| **Trace ID** | Distributed tracing SDK | Xâu chuỗi spans để chẩn đoán latency | Request correlation hoặc authorization |
| **Span ID** | Tracing span | Nhận diện một thao tác | Chunk/partition identity |
| **JobInstance ID** | Spring Batch JobRepository | Nhận diện job instance theo identifying JobParameters | Execution attempt hoặc work item |
| **JobExecution ID** | JobRepository | Một lần chạy/restart JobInstance | ID ổn định xuyên các lần restart |
| **StepExecution ID** | JobRepository | Lần chạy một step/worker partition | Business operation key |
| **Partition name** | `Partitioner`/step mapping | Logical partition ổn định trong một snapshot | Uniqueness toàn hệ nếu thiếu namespace |
| **Chunk sequence** | Chunk protocol/step scope | Phân biệt chunk request trong một execution | Uniqueness toàn cluster |
| **Business operation ID** | Nghiệp vụ | Ngăn cùng effect bị áp dụng hai lần | Tracing hoặc routing metadata |

**Lý do phải tách:** một request logical có thể bị gửi lại dưới **message ID mới**, nhưng phải giữ key idempotency cũ. Ngược lại, một trace có thể bao trùm hàng trăm chunks, nên trace ID **không đủ phân biệt** một ChunkResponse cụ thể.

## 4. Ba lớp identity cần giữ nhất quán

Một giao thức vững cần:

1. **Logical work identity:** `batchKey`, `sourceVersion`, `partitionName` hoặc key của chunk theo business contract. Dùng để đối soát output qua retry/restart.
2. **Execution identity:** `jobExecutionId` và `stepExecutionId`; phân biệt lần chạy cũ/mới.
3. **Transport attempt identity:** message ID, request dispatch attempt, broker delivery tag/redelivery. Dùng để chẩn đoán retries nhưng không thay logical work key.

Ví dụ:

~~~text
Logical work:
  batchKey=2026-11-26/settlement, chunkLogicalKey=chunk-17, source=v3

Execution A:
  jobExecutionId=845, stepExecutionId=880, request=R-845-880-17
  broker messageId=M1, deliveryAttempt=1

Retry transport same logical request:
  jobExecutionId=845, stepExecutionId=880, request=R-845-880-17
  broker messageId=M2, deliveryAttempt=2

Restart execution B:
  jobExecutionId=846, stepExecutionId=901, request=R-846-901-17
  logical work vẫn phải đối soát với dữ liệu đã commit từ A
~~~

**Không mặc định chunk-17 của một JobExecution mới giống hệt chunk-17 cũ** nếu reader/snapshot/partition mapping đã thay. Khi cần idempotency xuyên restart, logical operation ID phải được thiết kế dựa trên **nguồn bất biến và business keys**, chứ không chỉ ghép những số đếm framework.

## 5. Hai kiểu “correlation ID” hay bị lẫn

Từ *correlation ID* thường được dùng cho hai khái niệm:

- **Application request/reply correlation:** ví dụ manager giữ `R-845-880-17` trong pending registry; reply chứa cùng key để manager lấy đúng request.
- **Logging/observability correlation:** ví dụ gắn `correlationId` vào MDC/logs để tìm tất cả events của một request.

Hai cơ chế có thể **dùng chung giá trị** nếu đã chọn rõ phạm vi và quyền truy cập, nhưng yêu cầu tin cậy khác nhau. Logging có thể sample/drop, còn manager **không được phụ thuộc log exporter** để quyết định reply hợp lệ. Không để giá trị người dùng tự truyền qua header kiểm soát state mà không validation.

## 6. Correlation không phải exactly-once

Kịch bản kinh điển:

~~~text
1. Worker nhận request R17.
2. Worker ghi business DB và COMMIT thành công.
3. Worker chết trước khi reply được publish / ACK được xác nhận.
4. Broker redeliver R17 hoặc manager retry.
5. Worker khác xử lý lại R17.
~~~

**Correlation ID** cho manager biết reply cuối thuộc `R17`; nó **không ngăn lần ghi DB ở bước 5**. Để bảo vệ correctness, cần **writer idempotent** theo logical business operation, durable ledger, unique constraint + payload verification hoặc transactional outbox tùy hiệu ứng. Có thể có **hai processing attempts nhưng một business effect**.

Một `ChunkResponse` “SUCCESS” cũng chưa phải chứng cứ đủ nếu worker gửi response trước khi transaction thực sự commit hoặc nếu reply đến từ một request stale. Hợp đồng phải phân biệt **commit evidence**, **reply status**, **manager correlation decision** và **Spring Batch StepExecution outcome**.

## 7. Remote chunking: correlation ở mức chunk

Trong **remote chunking**, manager thường có `ItemReader` và tạo một `ChunkRequest` chứa nhiều items; worker process/write rồi trả `ChunkResponse`. Identity cần phản ánh **chunk được manager dispatch**, không chỉ từng item.

~~~mermaid
flowchart LR
    M["Manager ItemReader / Chunker"] --> D["ChunkRequest + correlation"]
    D --> Q[("Request Broker")]
    Q --> W["Worker ChunkProcessor / Writer"]
    W --> B[("Business DB")]
    W --> R[("Reply Broker")]
    R --> C["Manager reply correlator"]
    C --> J[("JobRepository / outcome")]
~~~

Ví dụ một envelope ứng dụng:

~~~json
{
  "protocolVersion": 1,
  "kind": "CHUNK_REQUEST",
  "correlationId": "settlement/845/880/chunk/17",
  "jobExecutionId": 845,
  "stepExecutionId": 880,
  "chunkSequence": 17,
  "batchKey": "2026-11-26/settlement",
  "sourceVersion": "snapshot-v3",
  "logicalOperationKey": "settlement-v3/chunk-17",
  "attemptId": "dispatch-2"
}
~~~

Đây là **protocol ví dụ do ứng dụng định nghĩa**, không phải cấu trúc JSON mặc định của Spring Batch. Các phiên bản Spring Batch có thể cung cấp sequence/job identifiers khác nhau trong message classes; phải kiểm tra đúng API và integration adapter đang dùng thay vì copy một envelope tưởng tượng vào nội bộ framework.

**Điểm then chốt:** manager có thể gửi C17, C18, C19 rồi nhận C18 trước. Registry không được cập nhật bằng thứ tự `pending.removeFirst()`. Nó phải tìm đúng request key/sequence **trong execution scope**.

## 8. Remote partitioning: correlation ở mức StepExecution

Trong **remote partitioning**, manager chia work thành partitions; worker nhận `StepExecutionRequest` (hoặc message tương đương theo Spring Batch Integration version/topology), chạy worker step với `ExecutionContext` của partition rồi báo/kết luận kết quả qua reply hoặc shared `JobRepository`.

~~~text
Manager JobExecution=845
  Partition name=partition0, worker StepExecution=884
  Partition name=partition1, worker StepExecution=885
  Partition name=partition2, worker StepExecution=886

Worker partition2 hoàn tất trước partition0.
Status/response của StepExecution=886 không được
ghép vào pending slot của StepExecution=884.
~~~

**Khác với remote chunking:** worker partitioning thường giữ reader riêng và có **StepExecution** với checkpoint/transaction của chính nó. Manager correlation thường phải dựa vào **worker step execution identity và kết quả JobRepository**, không suy rằng mỗi partition đồng nghĩa một single chunk sequence.

**Không giả định tất cả remote partitioning deployments đều dùng cùng một reply queue.** Một số flow nhận explicit reply, một số handler tham chiếu repository/status; test và telemetry phải gắn vào topology cụ thể.

## 9. Local partitioning và parallel steps vẫn cần context đúng

Local `TaskExecutorPartitionHandler` chạy workers trên **threads cùng JVM**, nên không nhất thiết cần request/reply broker correlation. Tuy nhiên, để **observability và kiểm thử** vẫn cần định danh:

- `JobExecutionId`, `managerStepExecutionId`, `workerStepExecutionId`.
- `partitionName`, range/source version.
- Thread name/worker identity như thông tin phụ trợ, **không phải business key**.

Không dùng vị trí `StepExecution` trong collection hay completion timestamp để đoán partition nào. Trong parallel steps/flows, flow A có thể xong trước B mà không phải lỗi; logic phụ thuộc phải nằm trong job flow/barrier, không trong cơ chế “callback thứ nhất” của một listener.

## 10. State machine tối thiểu cho request/reply

Một durable request lifecycle có thể được mô tả:

~~~mermaid
stateDiagram-v2
    [*] --> PREPARED
    PREPARED --> DISPATCHING: manager publish attempt
    DISPATCHING --> IN_FLIGHT: broker accepted / recoverable publish outcome
    IN_FLIGHT --> REPLIED: valid reply received
    IN_FLIGHT --> TIMED_OUT: deadline exceeded
    IN_FLIGHT --> FAILED: explicit failure outcome
    TIMED_OUT --> RECONCILING: check worker/DB/broker
    DISPATCHING --> RECONCILING: publish outcome unknown
    RECONCILING --> IN_FLIGHT: safe retry same logical work
    RECONCILING --> REPLIED: verified durable outcome
    REPLIED --> CORRELATED: manager CAS accepted
    CORRELATED --> [*]
    FAILED --> [*]
~~~

**Đây là state machine ứng dụng**, không phải trạng thái mặc định của `ChunkRequest`. Các bước `REPLIED`, `CORRELATED` có thể gộp thành một transition transaction trong triển khai thực. Quan trọng hơn tên enum là **hợp đồng của mỗi transition**: nguồn bằng chứng, quyền update và điều kiện CAS.

### Những trạng thái không được gộp vô ý

- **DISPATCHED**: code đã gọi gửi hoặc broker đã xác nhận? Phải định nghĩa mốc.
- **IN_FLIGHT**: request đã publish nhưng manager chưa có outcome; worker có thể đã commit.
- **TIMED_OUT**: chưa nhận reply đúng hạn; **không chứng minh worker failed**.
- **FAILED**: outcome thực sự thất bại và phù hợp policy, không phải chỉ “trace bị thiếu”.
- **CORRELATED**: reply khớp request; chưa chắc toàn job/batch đã hoàn tất hay được publish.

## 11. Thiết kế correlation key có namespace rõ

Một ID kiểu `chunk-17` chỉ độc nhất trong một bước cụ thể, không độc nhất giữa các JobExecutions, tenants hoặc worker pools. Một key có cấu trúc phù hợp:

~~~text
namespace / jobExecutionId / stepExecutionId / kind / sequence
tenant-a/settlement / 845 / 880 / CHUNK / 17
~~~

Trong production, có thể lưu **opaque request UUID** làm khóa chính và lưu các fields trên thành metadata bất biến. Hai cách tương đương về chức năng nếu **đảm bảo uniqueness/validation trong kho trạng thái**:

| Kiểu ID | Ưu điểm | Rủi ro/cần lưu ý |
| --- | --- | --- |
| Composite key dễ đọc | Debug và đối chiếu JobRepository nhanh | Lộ metadata nội bộ; separator/escape; length |
| Opaque UUID/ULID | Độc lập định dạng các business fields | Phải tra durable ledger để biết request thuộc gì |
| Sequence trong step | Rẻ và thân thiện tracing | Trùng giữa JobExecutions/StepExecutions |
| Broker-generated message ID | Thuận tiện transport-level | Có thể thay khi retry/republish; provider-specific |
| Business key | Bền xuyên restart | Một operation có thể cần nhiều request attempts; không luôn là pending slot |

**Khuyến nghị:** giữ hai cột độc lập `request_id` và `logical_operation_key`. `request_id` phục vụ **một pending request trong một execution**, `logical_operation_key` phục vụ **đối soát/dedup nghiệp vụ xuyên retry/restart**. Nếu một logical request gửi lại trong cùng execution, giữ `request_id`; có thể sinh `dispatch_attempt_id` mới cho audit.

## 12. Mẫu request và reply envelope Java 17

~~~java
record WorkIdentity(
        String namespace,
        long jobExecutionId,
        long stepExecutionId,
        String workKind,
        long sequenceNo) {

    WorkIdentity {
        Objects.requireNonNull(namespace);
        Objects.requireNonNull(workKind);
        if (namespace.isBlank() || workKind.isBlank()
                || jobExecutionId <= 0 || stepExecutionId <= 0
                || sequenceNo < 0) {
            throw new IllegalArgumentException("Invalid work identity");
        }
    }
}

record WorkerRequest(
        String requestId,
        WorkIdentity identity,
        String sourceVersion,
        String logicalOperationKey,
        String dispatchAttemptId,
        byte[] payload) {}

record WorkerReply(
        String requestId,
        WorkIdentity identity,
        String logicalOperationKey,
        String resultStatus,
        String resultHash,
        String workerAttemptId) {}
~~~

**Bộ record chỉ là DTO minh họa**, không đại diện cho các constructor nội bộ của Spring Batch. Với Java `record` chứa `byte[]`, phép so sánh `equals` mặc định so **tham chiếu mảng**, không so nội dung. Trong hệ thống thật nên dùng immutable bytes wrapper, một message codec và validation/hash riêng; **không dùng `record.equals` trực tiếp làm xác minh payload**.

Yêu cầu:

1. `requestId` phải có uniqueness trong phạm vi request registry và không thể bị đoán/đổi để sửa trạng thái ngoài quyền.
2. `identity` khớp **pending slot** do manager tạo; không chỉ tin header do peer gửi.
3. `sourceVersion` và `logicalOperationKey` phải được lưu bền vững trước dispatch.
4. `dispatchAttemptId` có thể đổi khi republish, nhưng `requestId` của cùng logical request attempt được phép giữ nguyên theo protocol.
5. `resultStatus` chỉ là lời khai từ worker; cần validate enum, payload integrity và business outcome trước manager final success.

## 13. Đặt correlation ở payload hay header?

**Header** phù hợp để adapters/brokers/gateways biết message thuộc request nào mà chưa parse payload. **Payload** phù hợp cho domain protocol validation và versioning. Nhiều hệ thống dùng **cả hai**, nhưng phải kiểm chúng không mâu thuẫn.

~~~text
Spring Message Headers:
  correlationId = R-845-880-17
  requestId = R-845-880-17
  traceparent = ...      (observability only)

Payload:
  requestId = R-845-880-17
  jobExecutionId = 845
  stepExecutionId = 880
  sequence = 17
~~~

**Quy tắc kiểm:** inbound adapter map header; worker validator kiểm header request ID **trùng** payload ID và khớp authorization/source. Nếu không trùng, reject/quarantine và audit; **không lấy giá trị “có vẻ hợp lệ hơn”**.

Không assume message header `correlationId` sẽ luôn đi xuyên tất cả converter/adapters. Cần kiểm **wire-level** từng transport, không chỉ object `MessageHeaders` trước khi gửi.

## 14. Spring Messaging và Spring Integration: ví dụ gắn header

Một ví dụ tại tầng message nội bộ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.integration.IntegrationMessageHeaderAccessor;

Message<WorkerRequest> toSpringMessage(WorkerRequest request) {
    return MessageBuilder.withPayload(request)
            .setHeader(
                IntegrationMessageHeaderAccessor.CORRELATION_ID,
                request.requestId())
            .setHeader("batch.requestId", request.requestId())
            .setHeader("batch.jobExecutionId",
                       request.identity().jobExecutionId())
            .setHeader("batch.stepExecutionId",
                       request.identity().stepExecutionId())
            .build();
}
~~~

**Đây là đoạn code ứng dụng minh họa**, các tên hằng và mapping ở Spring Integration phải được kiểm trên phiên bản đang dùng. Spring Messaging có `MessageHeaders.ID` là **UUID của message object**, thường thay khi xây message mới; nó không phải request ID bền qua retry/restart. `replyChannel` và `errorChannel` là các routing headers/channels, **không phải correlation ID**.

Khi gửi message sang broker:

- Spring Integration outbound adapter phải map đúng custom `batch.*` và correlation header theo provider.
- Converter/serializer phải giữ payload request identity.
- Worker reply builder phải **copy đúng logical request ID**, không lấy ID của reply message mới làm request ID.
- Manager inbound reply flow phải validate requestId/execution identity **trước** khi cập nhật pending state.

**Không sao chép toàn bộ headers một cách mù quáng**: `replyChannel` có thể là channel object nội bộ JVM không serializable; tracing baggage có thể chứa dữ liệu nhạy cảm; broker có hạn chế header name/type/size.

## 15. RabbitMQ/AMQP: correlationId và replyTo

Trong AMQP, message properties có thể mang `correlationId` và `replyTo` cùng custom headers. `correlationId` thường là khóa để request/reply RPC ghép nhau; `replyTo` chỉ định nơi gửi response. Khi Spring AMQP/Spring Integration chuyển đổi message, phải xác minh cách các properties này được map vào/ra Spring Message headers theo adapter/mapper.

~~~text
Request:
  routingKey = batch.chunk.requests
  AMQP correlationId = R-845-880-17
  AMQP replyTo = batch.chunk.replies.manager-A
  app headers: jobExecutionId=845, stepExecutionId=880

Reply:
  AMQP correlationId = R-845-880-17
  delivery route = batch.chunk.replies.manager-A
  payload: requestId=R-845-880-17, outcome=...
~~~

**Không mặc định RabbitMQ tự đặt correlationId** cho mọi message. Producer/protocol và adapter configuration quyết định điều đó. Với **Direct Reply-to**, temporary reply queues hoặc shared reply queues, có những semantics và giới hạn khác nhau; cần test đúng topology thật.

Broker có thể redeliver request, worker publish reply hai lần, hoặc manager consume reply sau khi pending registry đã mất do restart. **AMQP property correlationId không tự bảo đảm reply được xử lý exactly-once**.

## 16. JMS: JMSCorrelationID, JMSMessageID và JMSReplyTo

Trong JMS:

- `JMSMessageID` thường do provider gán cho message; không nhất thiết ổn định khi republish.
- `JMSCorrelationID` dùng liên kết reply tới request theo protocol; có hệ RPC dùng request JMSMessageID làm correlation trong reply, **có hệ dùng application-generated ID**.
- `JMSReplyTo` chỉ định reply destination.

Không được trộn hai chính sách cùng một flow: nếu manager kỳ vọng response.`JMSCorrelationID` bằng `request.JMSMessageID` nhưng worker lại gửi `request.applicationRequestId`, manager có thể timeout dù worker đã commit.

**Test mapping cần xác nhận:** ID nào manager đăng ký trước khi gửi, ID nào worker nhìn thấy trên message được provider xác nhận, và ID nào worker đặt vào reply. Với request JMSMessageID chưa biết trước publish, manager-side pending registry phải xử lý đúng việc provider cấp ID sau send; một **application-generated requestId** có thể đơn giản hơn khi thiết kế theo chủ đích.

## 17. Kafka: record headers và reply topic

Kafka record không có một RPC reply-to/correlation property bắt buộc như một số AMQP/JMS patterns. Ứng dụng có thể định nghĩa:

~~~text
Request topic: batch.chunk.requests
  key = partition/batch routing key
  headers["batch.requestId"] = UTF-8 bytes of R-845-880-17
  payload = WorkerRequest(...)

Reply topic: batch.chunk.replies
  key = manager/response routing key
  headers["batch.requestId"] = same requestId
  payload = WorkerReply(...)
~~~

**Điểm phân biệt:** Kafka có **offset và ordering trong từng topic-partition** theo điều kiện producer/consumer; offset không phải request correlation ID. Với nhiều partitions/consumers, processing completion/replies vẫn có thể đến không theo thứ tự request.

Header values thường là bytes. Custom encoder/decoder phải thống nhất encoding, size và schema version. Consumer group/rebalance và broker retention ảnh hưởng đến việc pending replies có thể bị đọc lại; manager phải **dedup theo request ID và execution identity**, không theo offset của một lần receive.

## 18. Khi chuyển giữa nhiều transports

Một hệ thống có thể có flow `HTTP → Kafka → Worker → AMQP reply → Manager`. Nếu gửi `correlationId` dưới dạng JMS property ở một adapter nhưng đổi thành `x-request-id` qua HTTP và `batch.requestId` qua Kafka, cần **mapping contract** cho từng ranh giới:

| Boundary | Tên/representation | Validation |
| --- | --- | --- |
| HTTP ingress | `X-Batch-Request-Id` hoặc body field | Validate length, namespace, auth, provenance |
| Spring Message | `correlationId` và `batch.requestId` | Header/payload agree |
| AMQP request/reply | Basic properties `correlationId` | Header mapper giữ giá trị đúng |
| JMS request/reply | `JMSCorrelationID` | Không đổi policy giữa sender/receiver |
| Kafka record | UTF-8 bytes trong application header | Serializer/mapping nhất quán |
| Business DB | `logical_operation_key` | Unique constraint + payload verification |
| Trace/log | Correlation attribute/log context | Không dùng làm quyết định commit |

**Điểm có thể thất bại:** converter bỏ headers, adapter chỉ allowlist một số headers, header name JMS không hợp lệ theo provider, Kafka encoding khác, hoặc worker tạo reply mới nhưng lấy `MessageHeaders.ID` thay request ID gốc. Bài integration test cần inspect **message trên broker**.

## 19. Pending registry trong JVM: phù hợp khi nào?

Một test/demo có thể giữ:

~~~java
record RequestKey(String namespace,
                  long jobExecutionId,
                  long stepExecutionId,
                  long sequenceNo) {}

record PendingRequest(String requestId, RequestKey key) {}

final class InMemoryPendingRegistry {
    private final ConcurrentMap<String, PendingRequest> pending =
            new ConcurrentHashMap<>();

    void register(PendingRequest request) {
        PendingRequest previous = pending.putIfAbsent(
                request.requestId(), request);
        if (previous != null && !previous.equals(request)) {
            throw new IllegalStateException(
                    "Duplicate requestId with different identity");
        }
    }

    PendingRequest lookup(String requestId) {
        return pending.get(requestId);
    }
}
~~~

`ConcurrentHashMap` chống data race của **nhiều handler threads cùng một JVM**, nhưng không phải:

- Durable pending state qua manager restart.
- Distributed coordination giữa hai manager nodes.
- Transaction chung với broker publish hoặc business DB.
- Bảo đảm một reply chỉ được accepted một lần nếu update state không có CAS.

Khi manager mất process, map biến mất nhưng worker có thể vẫn commit và reply. **Với workload quan trọng và remote messaging**, cần durable ledger hoặc framework-provided recoverable state đã được chứng minh phù hợp.

## 20. Durable pending ledger bằng PostgreSQL

Một schema minh họa:

~~~sql
CREATE TABLE batch_request_ledger (
    request_id          VARCHAR(180) PRIMARY KEY,
    namespace           VARCHAR(120) NOT NULL,
    job_instance_id     BIGINT NOT NULL,
    job_execution_id    BIGINT NOT NULL,
    step_execution_id   BIGINT NOT NULL,
    work_kind           VARCHAR(20) NOT NULL
                        CHECK (work_kind IN ('CHUNK','PARTITION')),
    work_sequence       BIGINT NOT NULL,
    logical_operation_key VARCHAR(220) NOT NULL,
    source_version      VARCHAR(160) NOT NULL,
    state               VARCHAR(24) NOT NULL
                        CHECK (state IN (
                            'PREPARED','DISPATCHING','IN_FLIGHT',
                            'TIMED_OUT','RECONCILING','CORRELATED',
                            'FAILED','QUARANTINED')),
    expected_result_hash VARCHAR(128),
    correlated_result_hash VARCHAR(128),
    owner_epoch         BIGINT NOT NULL DEFAULT 0,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deadline_at         TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    UNIQUE (namespace, job_execution_id, step_execution_id,
            work_kind, work_sequence)
);

CREATE INDEX idx_batch_request_pending
    ON batch_request_ledger(state, deadline_at);
~~~

**Lưu ý schema là của ứng dụng**, không phải bảng Spring Batch tạo sẵn. `logical_operation_key` có thể lặp giữa JobExecutions do restart: nó nên được quản lý bằng một **business operation ledger** riêng và policy dedup phù hợp, không thêm unique constraint ở đây nếu restart hợp lệ cần request mới. Nếu cần audit nhiều attempts, tạo bảng `batch_request_attempt`; không ghi đè hết lịch sử khi tăng `attempt_count`.

### Nguồn chân lý nào được chọn?

`JobRepository` quản lý trạng thái JobExecution/StepExecution và checkpoint; `batch_request_ledger` quản lý **pending/correlation protocol**; business DB/ledger xác nhận **effect đã commit**. Nếu cả ba không cập nhật trong một transaction, cần reconciliation. Không dùng bảng request tự tạo để “fake” một StepExecution COMPLETED khi framework chưa có outcome phù hợp.

## 21. Durable reply inbox: lưu cả những phản hồi bất thường

Chỉ lưu reply được accepted sẽ khiến việc điều tra duplicate/stale khó khăn. Có thể tạo một **inbox/audit**:

~~~sql
CREATE TABLE batch_reply_inbox (
    reply_event_id     VARCHAR(180) PRIMARY KEY,
    request_id         VARCHAR(180) NOT NULL,
    job_execution_id   BIGINT NOT NULL,
    step_execution_id  BIGINT NOT NULL,
    payload_hash       VARCHAR(128),
    worker_attempt_id  VARCHAR(180),
    outcome            VARCHAR(24) NOT NULL,
    classification     VARCHAR(30) NOT NULL,
    received_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_batch_reply_request
    ON batch_reply_inbox(request_id, received_at);
~~~

**Một transport delivery có thể không có globally unique event ID**, nên ứng dụng phải sinh/duy trì `reply_event_id` theo protocol. Nếu broker redeliver cùng message, có thể cần dedup event ID; nếu worker **publish lại** logically same reply dưới new message ID, vẫn phải dedup **outcome** bằng `request_id + execution identity + payload hash`, chứ không chỉ bằng khóa chính của inbox.

Các `classification` minh họa:

~~~text
ACCEPTED
DUPLICATE_IDENTICAL
CONFLICTING_DUPLICATE
STALE_EXECUTION
UNKNOWN_REQUEST
MALFORMED
RECONCILE_REQUIRED
~~~

Nếu transport nhận reply không hợp lệ (không đúng schema/auth) thì không được parse vô hạn hoặc ghi nguyên payload nhạy cảm vào DB. Audit nên lưu reason code, request ID đã validate và payload digest khi phù hợp.

## 22. Quy tắc chấp nhận reply: validation trước state change

Một manager-side inbound handler nên thực hiện theo thứ tự:

1. **Xác thực nguồn/trust boundary** của message; kiểm authorization theo namespace/tenant nếu cần.
2. Kiểm schema/`protocolVersion`, field lengths và types; không để malformed input làm parser/DB query nổ không kiểm soát.
3. Đọc `requestId` ở header và payload; xác minh chúng trùng nếu protocol chứa cả hai.
4. Lấy **đúng pending row** theo requestId từ durable registry.
5. So `jobExecutionId`, `stepExecutionId`, `workKind`, `workSequence`, `sourceVersion` và `logicalOperationKey`.
6. Xác nhận execution/owner hiện hành hoặc phân loại **stale/late** theo policy restart.
7. Kiểm reply outcome và **business evidence** cần thiết; đặc biệt không coi worker báo `COMPLETED` là DB commit đã được đối soát.
8. Dùng **transaction/CAS** để ghi nhận accepted outcome đúng một lần.
9. Ghi audit/inbox trong cùng transaction nơi khả thi; nếu dùng broker khác DB, áp dụng outbox/reconciliation.
10. Chỉ thông báo cho manager StepExecution/JobRepository theo hợp đồng **sau khi correlation được xác nhận**.

Nếu một bước không đạt, phân loại và xử lý có audit. **Không dùng `Map.remove(requestId)` trước khi validate payload** rồi làm mất pending entry vĩnh viễn khi nhận reply sai.

## 23. Atomic compare-and-set cho transition CORRELATED

Một câu SQL minh họa dành cho request đã được xác minh:

~~~sql
UPDATE batch_request_ledger
SET state = 'CORRELATED',
    correlated_result_hash = :verifiedHash,
    completed_at = CURRENT_TIMESTAMP
WHERE request_id = :requestId
  AND namespace = :namespace
  AND job_execution_id = :jobExecutionId
  AND step_execution_id = :stepExecutionId
  AND work_kind = :workKind
  AND work_sequence = :workSequence
  AND source_version = :sourceVersion
  AND state IN ('IN_FLIGHT','RECONCILING')
RETURNING request_id, completed_at;
~~~

**Đây là bước transition sau validation**, không phải toàn bộ handler: giá trị `verifiedHash` phải tương ứng reply/business effect đã xác thực; **reply status failed** không được gọi SQL này như một outcome thành công. Nếu UPDATE trả **0 row**, có thể do duplicate reply, wrong execution, timeout chưa reconciliation, request chưa commit publish hoặc conflict — phải **truy vấn trạng thái hiện tại và phân loại**, không coi 0 row luôn là thành công.

### Khi timeout và reply cạnh tranh

~~~text
Thread A: timeout scanner đang muốn TIMED_OUT.
Thread B: inbound reply handler đang muốn CORRELATED.

Nếu cả hai dùng UPDATE CAS theo trạng thái hiện tại:
  Chỉ một transition thắng ở mỗi trạng thái.
  Loser phải đọc lại state và xử lý policy tiếp.
~~~

Ví dụ timeout:

~~~sql
UPDATE batch_request_ledger
SET state = 'TIMED_OUT'
WHERE request_id = :requestId
  AND state = 'IN_FLIGHT'
  AND deadline_at <= CURRENT_TIMESTAMP;
~~~

Một reply đến sau transition `TIMED_OUT` không được làm UPDATE `CORRELATED` trực tiếp từ mọi state tùy tiện; nó phải đi qua **RECONCILING**, kiểm commit evidence, execution liveness và restart policy. **Timeout không phải rollback**.

## 24. Một handler @Transactional để phân loại duplicate

Code dưới đây mô tả ý tưởng; các helper/DAO cần hiện thực dựa trên schema/transaction manager thực tế:

~~~java
enum CorrelationDecision {
    ACCEPTED, DUPLICATE_IDENTICAL, STALE,
    UNKNOWN, CONFLICT, RECONCILE_REQUIRED
}

final class DurableReplyCorrelator {
    private final RequestLedgerDao ledger;
    private final BusinessOutcomeVerifier verifier;
    private final ReplyAuditDao audit;

    DurableReplyCorrelator(RequestLedgerDao ledger,
                           BusinessOutcomeVerifier verifier,
                           ReplyAuditDao audit) {
        this.ledger = ledger;
        this.verifier = verifier;
        this.audit = audit;
    }

    @Transactional
    public CorrelationDecision correlate(WorkerReply reply) {
        // lockForUpdate locks one pending request row in current transaction.
        RequestState row = ledger.lockForUpdate(reply.requestId());
        if (row == null) {
            audit.recordUnknown(reply);
            return CorrelationDecision.UNKNOWN;
        }
        if (!row.sameExecutionAndWork(reply)) {
            audit.recordStale(reply);
            return CorrelationDecision.STALE;
        }
        if (row.isCorrelated()) {
            boolean identical = row.acceptedHash()
                    .equals(reply.resultHash());
            audit.recordDuplicate(reply, identical);
            return identical
                    ? CorrelationDecision.DUPLICATE_IDENTICAL
                    : CorrelationDecision.CONFLICT;
        }
        if (!row.canReconcileNow()) {
            audit.recordReconcileRequired(reply);
            return CorrelationDecision.RECONCILE_REQUIRED;
        }
        if (!verifier.isBusinessOutcomeValid(reply)) {
            audit.recordReconcileRequired(reply);
            return CorrelationDecision.RECONCILE_REQUIRED;
        }
        ledger.markCorrelated(row, reply.resultHash());
        audit.recordAccepted(reply);
        return CorrelationDecision.ACCEPTED;
    }
}
~~~

**Các interface `RequestLedgerDao`, `BusinessOutcomeVerifier`, `ReplyAuditDao` và `RequestState` là lớp ứng dụng giả định**; không phải API có sẵn của Spring Batch. Ví dụ giả định **cùng transactional datasource** cho ledger/audit, `lockForUpdate` thực sự lấy row lock, và business verifier có cách đọc outcome ổn định. Với tài nguyên khác DB, không có giao dịch nguyên tử chung; cần reconciliation/outbox. Trong triển khai thật còn phải xác thực header/payload, source version, worker authorization và kiểm **reply outcome enum** trước khi gọi method này.

**Điểm quan trọng:** code không gọi `ledger.markCorrelated` khi outcome chưa xác minh. Việc lưu audit ngay trong transaction có thể rollback nếu có exception; thiết kế poison reply/quarantine cần policy riêng để không bị lặp vô hạn.

## 25. Publisher outbox: pending request và việc gửi message không chung transaction

Nếu manager `INSERT batch_request_ledger` xong rồi crash trước broker publish, request bị kẹt `PREPARED`. Nếu publish xong nhưng crash trước cập nhật `IN_FLIGHT`, message có thể **đã được worker xử lý** dù ledger nhìn như chưa gửi.

Mẫu **transactional outbox**:

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant DB as Request DB + Outbox
    participant P as Outbox Publisher
    participant Q as Broker
    participant W as Worker
    M->>DB: TX: INSERT pending request + outbox event
    DB-->>M: COMMIT
    P->>DB: Claim unsent outbox row
    P->>Q: Publish request (same requestId)
    Q-->>P: Publish outcome/confirm
    P->>DB: Mark published (idempotent)
    Q->>W: Deliver request
~~~

Vì DB commit và broker publish không có transaction phân tán mặc định, publisher có thể gửi **lặp** sau khi publish thành công nhưng mất confirm/DB update. **Outbox đổi vấn đề “mất request” thành “có thể gửi lặp nhưng có idempotency”**, không mang exactly-once delivery tự động.

### SQL khái niệm

~~~sql
CREATE TABLE batch_request_outbox (
    event_id           VARCHAR(180) PRIMARY KEY,
    request_id         VARCHAR(180) NOT NULL,
    payload_ref        VARCHAR(400) NOT NULL,
    state              VARCHAR(20) NOT NULL
                       CHECK (state IN ('READY','SENDING','SENT')),
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    last_attempt_at    TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trong cùng transaction manager tạo pending request:
INSERT INTO batch_request_ledger (...);
INSERT INTO batch_request_outbox (
    event_id, request_id, payload_ref, state)
VALUES (:eventId, :requestId, :payloadRef, 'READY');
~~~

`INSERT INTO batch_request_ledger (...)` là ký hiệu rút gọn, không phải SQL chạy trực tiếp. Trong production, outbox claiming/leases/poison handling, publisher confirms, source version pinning và retry limits phải có thiết kế rõ.

## 26. Worker inbox và idempotent business effect

Một worker có thể nhận **cùng requestId** hai lần. Nếu writer làm:

~~~sql
UPDATE account_balance
SET balance = balance + :delta
WHERE account_id = :accountId;
~~~

thì redelivery có thể **cộng tiền hai lần**. Cần một **business idempotency key** ổn định, chẳng hạn `(batchKey, sourceRecordId, businessRuleVersion)` hoặc `operationId` do producer tạo theo semantics.

Ví dụ ledger:

~~~sql
CREATE TABLE applied_business_operation (
    operation_id   VARCHAR(220) PRIMARY KEY,
    payload_hash   VARCHAR(128) NOT NULL,
    applied_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong **cùng DB transaction**:

1. `INSERT` `operation_id` với payload hash theo unique constraint.
2. Nếu inserted mới, áp dụng business update và commit cùng transaction.
3. Nếu conflict, đọc/so payload hash; nếu giống, trả “already applied” theo protocol; nếu khác, **fail/quarantine**.
4. Chỉ trả worker outcome có căn cứ sau khi transaction bền vững theo setup.

**Không dùng `ON CONFLICT DO NOTHING` rồi coi mọi conflict là thành công**: cùng operation ID nhưng payload khác có thể là corruption/reused ID, phải bị phát hiện.

### Quan hệ giữa request ID và operation ID

~~~text
Attempt A:  request=R845-C17, businessOperation=settlement/record-9001
Attempt B:  request=R845-C17, businessOperation=settlement/record-9001
Restart C:  request=R846-C17, businessOperation=settlement/record-9001

Request ID có thể đổi giữa executions.
Business operation key vẫn ổn định khi cùng logical record/version.
~~~

**Không lấy `chunkSequence` đơn lẻ làm operation ID của mỗi record**: một chunk chứa nhiều records; partition/chunk mapping còn có thể khác khi cấu hình thay đổi. Chọn key theo **logical effect được phép áp dụng một lần**, không theo network packet.

## 27. Sự khác nhau giữa retry, redelivery và restart

| Cơ chế | Ai khởi xướng? | Correlation identity có thể thay? | Business idempotency cần? |
| --- | --- | --- | --- |
| **Spring Batch retry** | Fault-tolerant chunk/step | Cùng StepExecution/request hoặc xử lý lại item | Có với side effect có thể replay |
| **Broker redelivery** | Broker sau NACK/ACK uncertainty | Transport attempt/message ID có thể khác, logical request giữ | **Có** |
| **Manager republish** | Timeout/reconciliation/outbox | Dispatch attempt đổi, request ID có thể giữ theo protocol | **Có** |
| **Job restart** | JobOperator/launcher theo policy | JobExecution/StepExecution IDs thường mới | **Có**, key ổn định theo logical data |
| **Business correction** | Một batch/version mới có chủ đích | ID logical work có thể mới | Quy tắc correction khác dedup |

**Không cộng bốn loại attempt rồi gọi chúng là bốn business operations thành công**. Một logical record có thể được processor gọi nhiều lần, gửi qua broker nhiều lần và xuất hiện trong hai JobExecutions sau restart mà cuối cùng vẫn chỉ có **một effect hợp lệ**.

## 28. Reply trễ sau restart: phải kiểm execution hiện hành

~~~mermaid
sequenceDiagram
    participant M1 as Manager Execution 845
    participant A as Worker StepExecution 880
    participant M2 as Manager Execution 846
    participant B as Worker StepExecution 901
    M1->>A: R845-C17
    Note over A: Network pause / vẫn có thể commit
    M2->>B: R846-C17
    B-->>M2: Reply R846-C17
    A-->>M2: Reply R845-C17 (late)
    Note over M2: Reject stale correlation, reconcile old effects
~~~

Manager execution 846 phải **không** ghi kết quả của `R845-C17` vào pending slot `R846-C17`. Nhưng từ chối reply **không tự rollback** business DB commits của worker A. Cần:

- Kiểm trạng thái JobRepository và business ledger của logical work.
- Fencing/quiescence nếu worker A còn có thể ghi sau khi worker B nhận quyền.
- Idempotency theo source version/business key cho replay.
- Ghi audit `stale_reply`, không xóa mất bằng chứng.
- Chỉ update outcome của request hiện hành sau xác minh đúng scope.

**Một timeout không chứng minh worker chết**. GC pause hoặc network partition có thể khiến reply trễ nhiều phút. Không dùng “deadline expired” làm giấy phép để hai workers cùng áp dụng non-idempotent effects.

## 29. Fencing khác correlation

Correlation trả lời **reply thuộc ai**; fencing ngăn **worker cũ tiếp tục ghi sau khi ownership thay đổi**. Hai cơ chế độc lập:

~~~text
Owner epoch 7: Worker A nhận partition P0.
Lease A hết hạn, epoch tăng 8 cho Worker B.
A vẫn có thể thức dậy và gửi reply cũ.

Correlation từ chối reply A không có nghĩa
business sink tự từ chối ghi từ A.
~~~

Muốn bảo vệ mạnh, phải có **resource-side fencing** hoặc publish/commit serialized qua một coordinator đáng tin:

- Với cùng PostgreSQL DB, chunk transaction có thể khóa row owner/epoch và validate trong transaction trước business writes.
- Với external API hoặc filesystem, DB row lock không trực tiếp fencing tài nguyên kia; cần conditional writes/versioned immutable results/single publisher/compensating protocol.
- Các idempotency keys vẫn cần thiết dù fencing hoạt động, vì duplicate delivery khi **cùng owner** có thể xảy ra.

**Không gắn leaseEpoch vào correlation ID rồi tự kết luận stale worker không thể ghi**. Epoch chỉ có giá trị nếu nơi nhận write **kiểm và từ chối** token cũ.

## 30. Hai manager trên một reply queue

Khi manager A và manager B là **competing consumers** của cùng reply queue:

~~~text
Manager A đang chờ R-A-17.
Worker publish reply cho R-A-17.
Broker deliver reply ấy tới Manager B.
B không có pending R-A-17 -> UNKNOWN.
A tiếp tục đợi -> TIMEOUT.
~~~

**Correlation có thể phát hiện lỗi**, nhưng **không tự định tuyến lại reply**. Cần:

1. Reply destination riêng per manager/execution hoặc broker routing theo reply-to, tùy topology.
2. Nếu dùng shared reply stream, thiết kế **ownership/partitioning** sao cho đúng manager đọc result hoặc xử lý qua durable registry cho phép cooperative correlation.
3. Durable pending lookup và policy xử lý unknown/late responses; không ACK/drop bừa một reply có thể thuộc manager khác nếu đang dùng competing consumers.
4. Quản lý manager crash/restart và stale reply destinations.
5. Dùng flow/error channel với audit/alerts cho wrong route và missing correlation.

**Với Kafka**, consumer group assignment/partition key có ý nghĩa khác RabbitMQ shared queue; phải chọn và kiểm tra routing thật. Đừng giả định `replyTo` luôn có mặt hoặc có cùng semantics ở mọi provider.

## 31. Correlation ID trong structured logs và distributed tracing

**Correlation ID** phục vụ **request/reply correctness**. **Trace ID** phục vụ theo dõi đường đi của operation. Cùng một request có thể có nhiều delivery attempts/spans nhưng một pending key; đồng thời một trace có thể bao trùm nhiều requests.

~~~json
{
  "event": "worker_reply_received",
  "service": "settlement-manager",
  "requestId": "R-845-880-17",
  "jobInstanceId": 819,
  "jobExecutionId": 845,
  "stepExecutionId": 880,
  "chunkSequence": 17,
  "workerAttemptId": "worker-b/attempt-2",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "outcome": "RECONCILE_REQUIRED",
  "reasonCode": "DB_COMMIT_UNKNOWN"
}
~~~

`traceId` nên được lấy từ **actual tracing context** do instrumentation quản lý, không tự nối từ request ID. Với RabbitMQ/JMS/Kafka, W3C `traceparent` thường là carrier của distributed trace; nó **không phải** request correlation key. Nếu `traceparent` bị drop ở adapter, hệ thống có thể **mất liên kết trace nhưng vẫn correlate đúng reply**.

### Span milestones nên có

~~~mermaid
flowchart LR
    A["manager.request.prepare"] --> B["broker.publish"]
    B --> C["worker.message.receive"]
    C --> D["worker.business.process"]
    D --> E["db.commit outcome"]
    E --> F["worker.reply.publish"]
    F --> G["manager.reply.receive"]
    G --> H["manager.reply.correlate"]
~~~

**Không gắn span `COMMITTED` vào `ItemWriter.write` nếu transaction chưa commit**. Với Spring-managed DB transaction có thể instrument `TransactionSynchronization.afterCommit`; vẫn phải phân biệt DB commit với broker ACK, StepExecution status và JobRepository metadata.

## 32. Logging MDC phải được dọn ở thread pools

Khi các workers sử dụng `TaskExecutor`/message listener container, thread có thể được tái sử dụng cho request tiếp theo:

~~~java
void withCorrelationLogging(
        String requestId, Runnable work) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", requestId);
        work.run();
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

Ví dụ dùng SLF4J `MDC`; cần imports và policy log correlation phù hợp. Ở hệ có Micrometer Tracing/Context Propagation, ưu tiên framework-provided scope management để không giữ **hai nguồn context độc lập**. Một thread-local MDC **không tự truyền qua network**, và `MDC.put` trên manager thread **không đồng nghĩa** worker thread đã nhận giá trị.

### Cardinality budget

**Đặt `requestId` vào logs/traces có retention và quyền truy cập** là hợp lý. Nhưng nếu đặt request ID làm **metric label** cho mỗi ChunkRequest, hàng triệu time series có thể xuất hiện. Metrics nên dùng `batch.mode`, `worker.role`, `outcome`, `reasonCode` và queue category có tập giá trị nhỏ.

## 33. Security: correlation không chứng minh danh tính

Một inbound reply chứa `correlationId=R845-C17` **không chứng minh** nó đến từ worker được ủy quyền. Nếu attacker hoặc service lỗi có thể tự đặt ID và trả `COMPLETED`, manager có thể chấp nhận kết quả giả nếu chỉ so chuỗi.

**Cần kết hợp:**

1. Broker authentication/authorization, TLS/mTLS khi phù hợp; giới hạn producer nào được publish vào reply destination.
2. Validate `tenant/namespace` và execution/work identity từ durable registry, không chỉ từ untrusted payload.
3. Hạn chế độ dài, charset và cardinality request ID; không dùng trực tiếp ID làm filesystem path, SQL string concat hay metric tag.
4. Schema/version validation, checksum/content hash và business outcome verification.
5. Không đưa raw PII/credentials/full payload vào correlation ID, `baggage`, log hoặc span attributes.
6. Không cho upstream user chọn `replyTo` tùy ý nếu nó cho phép exfiltration hoặc reply routing ngoài namespace.
7. Audit mọi rejection `UNKNOWN, STALE, CONFLICT, MALFORMED`; giới hạn log volume và tránh log injection.
8. Phân biệt replay hợp lệ cùng request ID với request giả mạo: correlation **không** thay authorization, integrity và chống replay.

**Không dùng một UUID “khó đoán” như bằng chứng bảo mật duy nhất**. Request ID là key điều phối, không phải authentication token.

## 34. Metrics nên đo theo logical request và attempt

| Metric | Ý nghĩa | Điều không được đánh đồng |
| --- | --- | --- |
| `batch_requests_prepared_total` | Logical requests được tạo và lưu bền | Broker đã nhận |
| `batch_request_publish_attempts_total` | Những lần gọi publish | Logical work mới |
| `batch_request_published_total` | Broker nhận publish theo confirm semantics | Worker DB commit |
| `batch_requests_inflight` | Request chưa có outcome cuối | Đúng số worker đang chạy |
| `batch_reply_received_total` | Reply deliveries tới manager | Unique accepted completions |
| `batch_reply_correlated_total` | Replies match pending hợp lệ | Business DB đúng nếu chưa reconcile |
| `batch_reply_duplicate_total` | Duplicates giống nội dung | Duplicate effects |
| `batch_reply_conflict_total` | Same request, different outcome/hash | An toàn bỏ qua |
| `batch_reply_stale_total` | Replies từ execution hết hiệu lực | Worker cũ không còn ghi |
| `batch_reply_unknown_total` | Không tìm thấy pending request | Chắc chắn request chưa từng tồn tại |
| `batch_request_timeout_total` | Deadline bị vượt | Worker rollback |
| `batch_request_recovery_lag_seconds` | Thời gian khôi phục request | Chỉ network latency |
| `batch_worker_business_committed_total` | Logical effects mới được commit | Số message ACK |
| `batch_correlation_db_latency_seconds` | CAS/ledger DB có nghẽn? | Worker processing duration |

**Phân loại:** attempts/transport vs logical requests vs logical business effects phải là ba bộ đếm khác nhau. Một request bị redeliver ba lần có thể tạo `reply_received_total=2`, `publish_attempts_total=1` và `business_committed_total=1`; đây không nhất thiết là lỗi.

### Alert nên dựa ngưỡng vận hành

- Pending requests oldest age vượt deadline theo loại job/workload.
- `UNKNOWN/STALE/CONFLICT` replies tăng sau deploy/restart.
- Manager received replies nhưng correlated thấp kéo dài; kiểm routing và pending registry.
- Worker DB commit bình thường nhưng reply publish failures cao.
- Reply inbox/backlog tăng, manager reply consumers không healthy.
- Request timeout tăng đồng thời với broker queue age hoặc DB lock wait.

Chữ `STALE` dùng trong metric classification phải nhất quán, không tạo reason labels từ raw exception messages.

## 35. Test unit: reply đến sai thứ tự nhưng không ghép nhầm

Một model giả định cho test không cần broker:

~~~java
record ReplyKey(long jobExecutionId,
                long stepExecutionId,
                long chunkSequence) {}

record ReplyEnvelope(
        ReplyKey key, String requestId,
        String status, String payloadHash) {}

final class ReplyRegistry {
    private final Set<ReplyKey> expected;
    private final ConcurrentMap<ReplyKey, ReplyEnvelope> received =
            new ConcurrentHashMap<>();

    ReplyRegistry(Set<ReplyKey> expected) {
        this.expected = Set.copyOf(expected);
    }

    void accept(ReplyEnvelope reply) {
        if (!expected.contains(reply.key())) {
            throw new IllegalArgumentException("Unknown or stale reply");
        }
        ReplyEnvelope prior =
                received.putIfAbsent(reply.key(), reply);
        if (prior != null && !prior.equals(reply)) {
            throw new IllegalStateException(
                    "Conflicting reply for same work identity");
        }
    }

    boolean allReceived() {
        return received.keySet().containsAll(expected);
    }

    int uniqueReplyCount() {
        return received.size();
    }
}
~~~

Test:

~~~java
@Test
void outOfOrderAndDuplicateRepliesRemainCorrelated() {
    ReplyKey c17 = new ReplyKey(845, 880, 17);
    ReplyKey c18 = new ReplyKey(845, 880, 18);
    ReplyRegistry registry = new ReplyRegistry(Set.of(c17, c18));

    ReplyEnvelope r17 =
            new ReplyEnvelope(c17, "R17", "COMPLETED", "hash17");
    ReplyEnvelope r18 =
            new ReplyEnvelope(c18, "R18", "COMPLETED", "hash18");

    registry.accept(r18); // Delivered first.
    assertFalse(registry.allReceived());
    registry.accept(r17);
    registry.accept(r18); // Identical duplicate.

    assertTrue(registry.allReceived());
    assertEquals(2, registry.uniqueReplyCount());
    assertThrows(IllegalStateException.class,
            () -> registry.accept(new ReplyEnvelope(
                    c18, "R18", "COMPLETED", "DIFFERENT")));
}
~~~

**Lưu ý:** `allReceived()` chỉ có nghĩa đã nhận **một response cho mỗi expected key**; nó không chứng minh mọi response thành công hoặc business effects đã commit. `ReplyKey` ở ví dụ chỉ dùng trong một isolated test namespace; production còn cần `requestId/namespace/workKind/sourceVersion` và database transactions. Một registry in-memory **không** thay thế durable recovery.

## 36. Kiểm thử concurrency: hai replies cùng lúc

Một data race có thể làm cùng request được accepted hai lần nếu code tách `if (notReceived)` và `markReceived` thành hai operation:

~~~text
Thread A: check pending=true
Thread B: check pending=true
Thread A: mark completed
Thread B: mark completed lần nữa
~~~

**Dùng CAS/unique constraint**, không dùng `synchronized` cục bộ để bảo vệ hai manager JVMs. Với unit test in-memory, có thể ép hai inbound handlers tới gần đồng thời:

~~~java
@Test
void twoThreadsCannotCreateTwoLogicalCompletions() throws Exception {
    ReplyKey key = new ReplyKey(845, 880, 17);
    ReplyRegistry registry = new ReplyRegistry(Set.of(key));
    ReplyEnvelope reply = new ReplyEnvelope(
            key, "R17", "COMPLETED", "hash17");
    CountDownLatch start = new CountDownLatch(1);
    ExecutorService pool = Executors.newFixedThreadPool(2);

    try {
        Callable<Void> task = () -> {
            start.await();
            registry.accept(reply);
            return null;
        };
        Future<Void> one = pool.submit(task);
        Future<Void> two = pool.submit(task);
        start.countDown();
        one.get(10, TimeUnit.SECONDS);
        two.get(10, TimeUnit.SECONDS);
        assertEquals(1, registry.uniqueReplyCount());
    } finally {
        start.countDown();
        pool.shutdownNow();
    }
}
~~~

**Giới hạn của test:** nó chứng minh logic concurrent map ở **một JVM**, không chứng minh DB CAS giữa hai managers hoặc redelivery semantics của broker. Cần PostgreSQL integration test riêng với hai DB connections/threads và unique constraints; phải assert đúng **một accepted transition/event**, duplicate được phân loại.

## 37. Kiểm thử timeout và reply race một cách xác định

Mục tiêu: manager timeout scanner và reply handler tranh cùng một row. Cách kiểm:

~~~text
Setup: request R17 state=IN_FLIGHT, deadline đã quá.
Thread A: chờ barrier rồi UPDATE -> TIMED_OUT.
Thread B: chờ barrier rồi validate + UPDATE -> CORRELATED.

Assert:
  database có một trạng thái hợp lệ sau race,
  không double-count success/timeout as two final effects,
  nếu timeout thắng trước thì reply đi qua RECONCILING,
  nếu reply thắng trước thì timeout không ghi đè CORRELATED,
  business outcome vẫn được đối soát.
~~~

**Không dùng `Thread.sleep` để “tạo race” rồi chấp nhận test flaky**; dùng `CountDownLatch` để đồng bộ điểm bắt đầu, transaction hooks hoặc test-specific pause trong DAO để ép interleaving. Test **hai connection thật** trên PostgreSQL sẽ thể hiện row locking/CAS sát production hơn in-memory fake.

### Bằng chứng đủ để kết luận

Đọc cả **ledger row** và **audit inbox** sau transactions commit. Nếu DB status đúng nhưng metrics đã tăng success hai lần do callbacks chạy trước commit, bộ test vẫn cần fail hoặc cảnh báo **instrumentation semantics sai**.

## 38. Test wire-level với RabbitMQ/JMS/Kafka

Một kiểm thử toàn đường:

1. Khởi động broker thật trong môi trường test/containers và PostgreSQL cho JobRepository/business/ledger.
2. Chạy manager và ít nhất **hai worker JVM/process** nếu mục tiêu là remote interaction.
3. Đăng ký `requestId`/execution identity trong durable pending ledger **trước khi dispatch**.
4. Manager publish requests C17, C18 cùng header/payload chứa correlation ID.
5. Inspect **wire message headers** tại consumer/broker probe; kiểm header mapper không drop/đổi ID.
6. Chặn worker C17 ở failpoint; để worker C18 commit và reply trước.
7. Manager nhận C18 và chỉ cập nhật **C18**; C17 vẫn pending.
8. Release C17, nhận reply và đối soát JobRepository/business DB.
9. Lặp lại với duplicate reply, unknown reply, stale reply từ old execution và worker kill sau DB commit trước reply.
10. Tắt/khôi phục manager và xác minh pending ledger/outbox/reply inbox có thể reconcile; không bị mất request sau restart.

### Những negative tests không thể bỏ

| Case | Lỗi được tiêm | Kết quả mong đợi |
| --- | --- | --- |
| N01 | Reply header requestId khác payload ID | Reject/quarantine, không đổi pending |
| N02 | Reply không có correlation ID | MALFORMED/UNKNOWN, không match theo thứ tự |
| N03 | Reply có chunk sequence đúng nhưng JobExecution sai | STALE, không cập nhật execution mới |
| N04 | Reply bị duplicate với messageId khác | Một logical outcome, audit duplicate |
| N05 | Same requestId nhưng payload hash khác | CONFLICT, không last-write-wins |
| N06 | Broker redelivery sau ACK uncertainty | Business effect chỉ áp dụng một lần |
| N07 | Worker commit rồi chết trước reply | Recovery/replay-safe, không fake failure/success |
| N08 | Manager chết sau publish trước ledger update | Outbox recovery, không mất request |
| N09 | Manager khác nhận reply vào wrong queue | Routing/unknown correlation được phát hiện |
| N10 | Trace context mất nhưng correlation còn | Workflow đúng, chỉ distributed tracing bị đứt |
| N11 | Reply mới của execution 846 đến trước reply cũ 845 | Chỉ accept đúng current execution |
| N12 | Business outcome unknown sau network cut | RECONCILE_REQUIRED, không ghi COMPLETED mù quáng |

**Transport-specific:** RabbitMQ cần kiểm ACK/NACK, publisher confirms, replyTo; JMS kiểm `JMSCorrelationID`/provider mapping; Kafka kiểm record headers, consumer group, replay/offset semantics. Không suy từ test `DirectChannel` cùng JVM ra bảo đảm của broker.

## 39. Error channel và poison replies

Không phải mọi message gửi tới reply queue đều là reply parse được:

~~~text
Reply deserialize lỗi
  -> không tìm thấy requestId
  -> header mapper loại correlation field
  -> payload schema version không hỗ trợ
  -> jobExecutionId không khớp
  -> resultHash conflicts
~~~

Trong Spring Integration, các lỗi asynchronous flow có thể đi qua `errorChannel` hoặc adapter error handler tùy topology. **Error channel xử lý exception, không thay correlation protocol**. Một malformed reply có thể không được gắn request identity đầy đủ; cần:

- **Dead-letter/quarantine** theo loại lỗi, có policy retry hữu hạn; tránh poison reply bị redeliver vô hạn và chiếm hết consumer capacity.
- **Audit an toàn** với reason code/metadata đã validate, không log full payload nhạy cảm.
- **Không ACK/drop bừa** reply chưa được xử lý khi protocol còn cần recovery và transport ACK semantics cho phép xử lý lại.
- Không `catch(Exception.class)` rồi trả một `ChunkResponse` giả `COMPLETED`.
- Phân biệt lỗi observability (mất `traceparent`) với lỗi workflow (mất `correlationId`).

**Với unknown reply:** nó có thể thuộc manager khác, JobExecution đã nghỉ, hoặc pending ledger có lỗi. Chính sách DLQ/forward/reconcile phải xuất phát từ routing topology, không dùng một quy tắc “unknown thì luôn xóa” cho mọi kiến trúc.

## 40. Dòng thời gian phân tích một sự cố

Giả sử manager đang chờ `R-845-880-17`:

~~~text
02:00:00.010 MANAGER_REQUEST_PREPARED      request=R-845-880-17
02:00:00.025 BROKER_PUBLISH_CONFIRMED     request=R-845-880-17
02:00:02.310 WORKER_RECEIVED              request=R-845-880-17
02:00:03.500 BUSINESS_DB_COMMIT_CONFIRMED  logicalOperation=settlement-v3/record-9001
02:00:03.510 WORKER_CRASH_BEFORE_REPLY     request=R-845-880-17
02:00:10.000 MANAGER_TIMEOUT              request=R-845-880-17
02:00:11.000 BROKER_REDELIVERY            request=R-845-880-17
02:00:11.200 WORKER_DEDUP_VERIFIED         logicalOperation=settlement-v3/record-9001
02:00:11.240 REPLY_PUBLISHED              request=R-845-880-17
02:00:11.300 MANAGER_RECONCILING           request=R-845-880-17
02:00:11.350 CORRELATION_ACCEPTED          request=R-845-880-17
~~~

Các timestamps là **minh họa**; chỉ được log `BUSINESS_DB_COMMIT_CONFIRMED` sau commit outcome theo resource thực. Nếu dựa timestamps của các hosts để đo queue wait, phải tính clock skew hoặc dùng broker/trace durations theo đúng điều kiện đo.

**Kết luận điều tra:** timeout manager là dấu hiệu **không nhận được reply kịp**, không chứng minh chunk đã rollback; worker B đã xác minh operation tồn tại nên không áp dụng lần hai. Correlation cuối cùng được chấp nhận sau khi outcome được đối soát.

## 41. Runbook: manager không nhận được reply

1. **Định danh phạm vi:** `namespace`, `JobInstanceId/JobExecutionId`, manager/worker `StepExecutionId`, `chunkSequence/partitionName`, `requestId`, source version.
2. **Kiểm ledger:** request ở `PREPARED, IN_FLIGHT, TIMED_OUT, RECONCILING` hay `CORRELATED`? Deadline/attempt_count/owner epoch là gì?
3. **Kiểm outbox:** request đã được publish với broker confirm chưa? Có lần publish không chắc chắn sau crash không?
4. **Kiểm request queue:** message backlog/oldest age, route, replyTo, consumer count, DLQ và redelivery.
5. **Kiểm worker:** process nào nhận, parse headers đúng không, StepExecution đang làm gì, có lỗi serialization/transaction?
6. **Kiểm business DB:** operation đã commit hay rollback; payload/key đã bị dedup; output values và source version đúng không?
7. **Kiểm reply path:** worker publish response chưa, reply queue/topic nào, manager nào consume, reply có `correlationId`/execution fields không?
8. **Kiểm inbox/audit:** có `UNKNOWN/STALE/CONFLICTING_DUPLICATE`, hoặc reply đến manager khác không?
9. **Xác minh restart/ownership:** JobExecution mới xuất hiện chưa, worker cũ còn sống sau timeout không? Sink có fencing/idempotency không?
10. **Xử lý có điều kiện:** retry same logical work qua outbox, route lại reply theo protocol, reconcile và CAS pending state, hoặc fail/quarantine nếu identity/payload conflict.
11. **Xác nhận final outcome:** JobRepository phù hợp, business keys/values đúng, không còn pending bị bỏ quên, reply accepted đúng execution.
12. **Kết thúc incident:** lưu reason, lần dispatch/delivery, latency breakdown, dữ liệu đối soát và test phải bổ sung.

### Tình huống A — broker chưa gửi được

~~~text
Request ledger = PREPARED
Outbox = READY
Broker không có message
Business DB chưa có operation

=> Outbox publisher có thể dispatch lại cùng requestId
   khi không có conflicting owner; kiểm publisher liveness.
~~~

### Tình huống B — broker đã gửi, worker commit rồi chết

~~~text
Request ledger = TIMED_OUT
Outbox = SENT
Broker redelivered = true
Business ledger = COMMITTED, đúng payload hash
Reply chưa được manager chấp nhận

=> Reconcile business outcome; retry/reply theo protocol.
   Không xóa business data hoặc áp dụng operation lần hai.
~~~

### Tình huống C — reply tới nhưng không match

~~~text
Reply requestId = R-844-880-17
Manager pending = R-845-880-17
Payload chunkSequence = 17
TraceId có thể giống hoặc khác tùy span context

=> STALE_EXECUTION hoặc UNKNOWN theo registry.
   Không match dựa riêng chunkSequence hay traceId.
~~~

**Không sửa JobRepository bằng tay thành `COMPLETED`, xóa reply queue để dashboard hết pending, hoặc quay lại FIFO reply matching**. Các hành động ấy có thể che giấu một sự cố data correctness.

## 42. Những sai lầm dễ gây lỗi distributed correlation

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Correlation chỉ là `chunk-17` | Trùng giữa jobs/restarts | Scoped request key/execution identity |
| Dùng `MessageHeaders.ID` làm logical request ID | Thay khi rebuild message | Application-generated stable request ID |
| Lấy `traceId` làm correlation | Một trace chứa nhiều requests, sampling | Protocol ID độc lập tracing |
| Ghép reply theo thứ tự arrival | Out-of-order làm cập nhật sai chunk | Lookup bằng request ID/execution key |
| Dùng `replyTo` làm correlation | Chỉ biết đích trả lời, không biết request | Hai fields riêng |
| Rebuild reply không copy correlation | Manager timeout dù worker done | Header mapping + payload validation |
| Chỉ gửi correlation ở local Spring channel | Adapter drop ở broker | Wire-level tests |
| Pending map chỉ trong JVM | Mất sau manager restart | Durable ledger/JobRepository recovery |
| `SELECT` rồi `UPDATE` không CAS | Hai handlers cùng accept | DB transaction/row lock/CAS |
| TIMEOUT = FAILED/ROLLBACK | Có thể worker đã commit | RECONCILING + business evidence |
| “Duplicate reply” bằng broker message ID | Redelivery/reply republish có ID mới | Dedup logical request + content hash |
| `ON CONFLICT DO NOTHING` mọi trường hợp | Che duplicate khác payload | Conflict verify/alert |
| Reply execution cũ update execution mới | False success sau restart | Execution identity + stale reply policy |
| Không có fencing | Worker cũ vẫn ghi dù reply bị reject | Sink-side epoch enforcement/quiescence |
| Shared reply queue không routing | Manager khác consume reply | Reply ownership/topology integration |
| Đếm reply/s = DB commit/s | Có duplicates, failures, pending | Separate attempt/outcome metrics |
| Dùng `correlationId` làm auth token | Có thể bị giả mạo | Broker auth + validation |
| Lưu full headers/payload trong tracing | PII/secret leak, cardinality | Allowlist/retention |
| Test chỉ fake `DirectChannel` | Không thấy ACK/routing/redelivery lỗi | Broker + multi-JVM tests |
| Coi writer callback là commit | Rollback vẫn bị ghi success | Transaction outcome verification |

## 43. Bài thực hành tổng hợp

**Đề bài:** xây một Spring Batch 5.x/Java 17+ remote chunking pipeline giả lập nhập **80.000 records**, chunk size 200, dùng RabbitMQ (hoặc Kafka/JMS có contract tương đương), manager và hai worker JVMs, PostgreSQL cho business output và correlation ledger. Mỗi record có `batchKey`, `recordId`, `sourceVersion` và business operation key ổn định.

### Phần A — Identity và request ledger

1. Tạo hai JobExecutions với source snapshots riêng; đảm bảo requestId không trùng giữa chúng.
2. Đăng ký `requestId, jobExecutionId, stepExecutionId, chunkSequence, sourceVersion` trong DB trước publish.
3. Gắn request ID ở Spring Message header và trong payload; kiểm mapping qua broker thật.
4. Thực hiện transactional outbox; xác minh crash sau DB outbox commit trước broker publish không mất request.
5. Thực hiện duplicate publish cùng logical request; worker không áp dụng effect hai lần.

### Phần B — Correlation dưới concurrency

6. Cho worker xử lý chunk C18 nhanh hơn C17; manager nhận reply C18 trước nhưng chỉ C18 hoàn tất.
7. Dùng hai threads cùng nhận reply C17; DB CAS chấp nhận một logical transition.
8. Gửi reply C17 lần hai cùng hash và lần ba hash khác; phân loại duplicate/conflict.
9. Gửi header ID khác payload ID; xác minh rejection không xóa pending row.
10. Cho reply vào queue của manager khác; kiểm routing/unknown reply handler.

### Phần C — Retry, restart và crash

11. Kill worker sau DB commit nhưng trước reply/ACK; quan sát redelivery và idempotent ledger.
12. Cho manager timeout đồng thời với reply handler; test CAS race và reconciliation.
13. Restart cùng JobInstance (theo recovery policy) để có JobExecution mới; gửi reply của old execution đến muộn.
14. Bảo đảm old reply không cập nhật new pending; business effects old execution vẫn được đối soát.
15. Tắt tracing exporter; correlation protocol vẫn hoạt động đúng và logs/metrics còn đủ.

### Phần D — Observability và vận hành

16. Đo pending oldest age, reply correlation latency, duplicate/stale/unknown totals và broker queue wait.
17. Với một request lỗi, tìm đường đi bằng requestId → DB ledger → broker/worker log → JobRepository → business effect.
18. Viết runbook xử lý `TIMED_OUT + business COMMITTED` mà không replay non-idempotent.

**Tiêu chí đạt:** không có reply ghép sai, missing/duplicate logical business effects; request/reply vẫn tìm được sau process restart, wire headers đúng, status được CAS bảo vệ, và operator có đủ evidence để giải thích timeout/late/unknown replies.

## 44. Checklist trước production

- [ ] Đã xác định **đơn vị correlation** theo remote chunking/remote partitioning và topology thực tế.
- [ ] `requestId` đủ namespace/uniqueness; không dùng `chunkSequence` hoặc partition name trần trên toàn cluster.
- [ ] Tách `requestId`, `dispatchAttemptId`, `traceId`, `messageId` và `businessOperationId`.
- [ ] Header và payload ID được kiểm thống nhất; missing/mismatch không được match theo FIFO.
- [ ] Spring Integration adapter/header mapper giữ correlation ID trên request **và** reply path.
- [ ] AMQP `correlationId/replyTo`, JMS `JMSCorrelationID` hoặc Kafka headers được kiểm **trên broker thật**.
- [ ] Pending requests được ghi bền theo workload/recovery SLA; không phụ thuộc duy nhất in-memory map.
- [ ] Request+outbox được ghi trong cùng DB transaction; publisher retry có thể phát lại cùng request an toàn.
- [ ] Inbox/dedup phân biệt identical duplicate, conflicting duplicate, unknown và stale.
- [ ] Handler kiểm execution/work/source identity và business evidence trước final success transition.
- [ ] Có transaction/CAS để timeout scanner và reply handler không ghi đè trạng thái nhau.
- [ ] TIMEOUT không tự là business FAILED/ROLLBACK; có RECONCILING path.
- [ ] Worker business writer idempotent theo logical operation và xác minh payload conflicts.
- [ ] Sink có fencing/quiescence khi worker cũ có thể ghi sau ownership change.
- [ ] JobRepository/ExecutionContext vẫn là nguồn checkpoint/restart, không bị thay bằng correlation ledger.
- [ ] Restart với JobExecution mới không accept late reply của old execution vào pending slot mới.
- [ ] Multi-manager reply routing và unknown correlation được kiểm thử.
- [ ] Broker ACK, publish confirms, reply receive và DB commit có signals riêng.
- [ ] Tracing W3C context tách biệt protocol correlation, mất exporter không làm hỏng business flow.
- [ ] Logs/MDC có ID đúng và cleanup trên pooled threads; metrics tránh high-cardinality request IDs.
- [ ] Header/payload validation, tenant authorization, broker credentials/TLS và PII policies được áp dụng.
- [ ] Có unit tests out-of-order/duplicates, DB CAS concurrency tests, broker multi-JVM + crash tests.
- [ ] Có alert cho oldest pending, correlation conflicts, stale replies, publisher failures và unknown commit.
- [ ] Runbook kiểm đủ manager → outbox/broker → worker/DB → reply/inbox → JobRepository.
- [ ] Không sửa metadata JobRepository hay xóa queues để “giải quyết” missing reply chưa đối soát.

**Ghi nhớ:** **Correlation ID trong distributed flow** là chìa khóa để ghép **đúng response với đúng pending request** khi Spring Batch điều phối nhiều chunks/partitions song song qua middleware. Correlation phải **đủ namespace, đi xuyên được header/payload/transport, tồn tại qua recovery và được kiểm bằng identity/CAS**, vì out-of-order, duplicate, timeout và late replies là các tình huống thực tế. Nhưng correlation **không thay business idempotency, transaction outcome, fencing, JobRepository hoặc distributed tracing**; kiến trúc an toàn sử dụng các lớp này phối hợp để vừa **khôi phục đúng dữ liệu**, vừa **biết chính xác chuyện gì đã xảy ra**.
