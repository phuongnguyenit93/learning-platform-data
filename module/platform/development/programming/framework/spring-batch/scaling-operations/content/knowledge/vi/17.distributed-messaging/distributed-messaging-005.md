# Correlation ID của request

Trong một hệ thống Spring Batch phân tán, **request** được gửi qua message broker có thể mất nhiều giây hoặc nhiều phút mới có **reply**. Một lúc có thể tồn tại hàng trăm yêu cầu từ các job, step, chunk hoặc partition khác nhau. Reply còn có thể đến **không đúng thứ tự**, bị **giao lại**, đến **sau timeout** hoặc xuất hiện khi manager đã restart. Vì vậy, bên gửi cần một cách xác định chính xác **reply này thuộc request nào**: đó là vai trò của **correlation ID**.

Bài học thuộc chương **Thông điệp phân tán** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module nghiên cứu mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán; đồng thời đo nút thắt, giữ thread safety, thiết kế retry/restart, vận hành job và chọn kiến trúc phù hợp tài nguyên. Nội dung tập trung vào **Correlation ID của request** khi manager và worker trao đổi thông điệp, đặc biệt trong **remote chunking**, **remote partitioning** và các request/reply integration flow.

**Nguyên tắc cốt lõi:** correlation ID giúp **ghép đúng yêu cầu với phản hồi**, nhưng **không tự bảo đảm** thông điệp được xử lý một lần, transaction đã commit, reply là đáng tin cậy hay dữ liệu nghiệp vụ không bị nhân đôi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả bài toán ghép request–reply khi nhiều worker xử lý đồng thời và reply trả về không theo thứ tự gửi.
2. Phân biệt **correlation ID**, **broker message ID**, **request ID**, **trace ID**, **business key/idempotency key**, **chunk sequence** và **StepExecution identity**.
3. Thiết kế hợp đồng request/reply với một định danh không nhập nhằng trong phạm vi job và lần thực thi.
4. Hiểu cách Spring Batch remote chunking/remote partitioning cần **bảo toàn correlation/protocol metadata** qua Spring Integration và broker.
5. Xử lý reply **trễ, lặp, sai nguồn, sai execution, mất header hoặc sai schema**.
6. Đặt timeout và quản lý danh sách request đang chờ phản hồi mà không rò bộ nhớ hoặc đánh dấu thành công giả.
7. Kết hợp correlation với **retry, redelivery, restart và idempotent business effects**.
8. Kiểm thử request/reply không đúng thứ tự, nhiều manager đồng thời, worker crash trước/sau commit và mất reply.
9. Đo message age, in-flight requests, correlation miss và reply latency để lựa chọn kiến trúc phân tán phù hợp.

**Tình huống xuyên suốt:** một Spring Batch manager gửi ba chunk tới queue, worker A xử lý chunk đầu chậm, worker B xử lý chunk thứ hai nhanh, worker C xử lý chunk thứ ba rồi phải retry. Nếu manager chỉ nhận một message có nội dung `SUCCESS`, nó không biết đó là kết quả của chunk nào. Correlation ID và các trường nhận diện execution/sequence giúp manager cập nhật đúng công việc và không nhầm reply của lần chạy trước sang lần chạy mới.

## 2. Vì sao không thể ghép reply bằng thứ tự đến?

Hãy xét một manager gửi ba yêu cầu:

~~~text
09:00:00 gửi request A -> worker 1, correlation = req-a
09:00:01 gửi request B -> worker 2, correlation = req-b
09:00:02 gửi request C -> worker 3, correlation = req-c

09:00:03 nhận reply B (SUCCESS, correlation = req-b)
09:00:07 nhận reply C (SUCCESS, correlation = req-c)
09:00:15 nhận reply A (SUCCESS, correlation = req-a)
~~~

Nếu manager ghép reply đầu tiên với request đầu tiên, trạng thái A và B sẽ bị đảo. Với dữ liệu hàng triệu bản ghi, nhầm lẫn như vậy có thể dẫn đến báo `COMPLETED` sai, đếm kết quả hai lần hoặc bỏ qua lỗi của chunk chưa hoàn tất.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker request
    participant A as Worker A
    participant B as Worker B
    participant R as Broker reply
    M->>Q: Request A / corr-A
    M->>Q: Request B / corr-B
    Q->>A: A / corr-A
    Q->>B: B / corr-B
    B->>R: Reply B / corr-B
    R->>M: Reply B / corr-B
    A->>R: Reply A / corr-A
    R->>M: Reply A / corr-A
~~~

**Correlation ID** là giá trị mà bên nhận reply dùng để liên kết kết quả với yêu cầu đã phát trước đó. Trong hệ thống request/reply, bên nhận request thường phải **giữ hoặc trả lại đúng giá trị correlation mà giao thức yêu cầu**.

Không nên dựa vào:

- Thứ tự publish của manager: broker/consumer không mặc định bảo đảm thứ tự xử lý và hoàn tất giữa nhiều worker.
- Thứ tự commit DB: chunk nhỏ có thể commit trước chunk lớn dù được gửi sau.
- Thread name hoặc hostname: một worker xử lý nhiều request, một request có thể được redeliver sang worker khác.
- Số lần nhận reply: một reply có thể lặp, một request có thể không có reply trong thời hạn đợi.

## 3. Phân biệt các định danh dễ nhầm

| Định danh | Trả lời câu hỏi | Vòng đời/phạm vi | Có dùng làm khóa dedup nghiệp vụ? |
| --- | --- | --- | --- |
| **Correlation ID** | Reply này thuộc **request nào**? | Theo request/reply exchange, hoặc theo hợp đồng protocol | **Không mặc định** |
| **Request ID** | Lần yêu cầu/gửi cụ thể này là gì? | Theo request; có thể dùng luôn làm correlation ID nếu quy ước nhất quán | Không đủ nếu một operation bị gửi lại bằng request mới |
| **Broker message ID** | Bản tin được broker/producer đánh dấu thế nào? | Theo message/delivery, tùy broker | Không: publish lại có thể có ID khác |
| **Reply ID** | Bản tin phản hồi cụ thể là gì? | Theo reply | Không: cùng phản hồi có thể được phát lại |
| **Trace ID** | Các span/log thuộc một luồng xử lý phân tán nào? | Có thể trải nhiều service, request, retry | Không: chủ yếu phục vụ quan sát |
| **Chunk sequence** | Đây là chunk thứ mấy theo protocol? | Thường trong phạm vi step/execution; kiểm tra framework | Không: một record có thể được replay ở chunk khác |
| **StepExecution ID** | Lần thực thi step nào đang được ghi nhận? | Một StepExecution, có thể khác sau restart | Không: không nhận diện duy nhất record |
| **JobInstance / JobExecution ID** | Job logic và lần chạy cụ thể nào? | JobInstance xuyên restart; JobExecution mỗi lần chạy | Không đủ để xác định một request |
| **Business key** | Record/operation nghiệp vụ nào đang được xử lý? | Theo miền nghiệp vụ, ví dụ `(batchKey, transactionId)` | **Có**, nếu được thiết kế đúng |
| **Idempotency key** | Tác động nghiệp vụ này đã được áp dụng chưa? | Ổn định qua retry/redelivery của cùng logical operation | **Có**, khi sink thực thi hợp đồng dedup |

Một hệ thống có thể **chọn cùng một chuỗi** làm request ID và correlation ID. Điều đó hợp lệ nếu cả hai phía thống nhất cách sử dụng, nhưng hai **vai trò** vẫn khác nhau. Ngược lại, trace ID nên bao trùm nhiều hoạt động nên thường **không** phù hợp để nhận diện duy nhất từng request.

### Ví dụ đầy đủ các cấp định danh

~~~text
jobName           = nightly-settlement
jobInstanceKey    = settlement-2026-11-26
jobExecutionId    = 845
stepExecutionId   = 1092
logicalChunkKey   = settlement-2026-11-26/chunk-0042
requestId         = 19744df7-718b-49db-a2f2-19ef23c0f93c
correlationId     = 19744df7-718b-49db-a2f2-19ef23c0f93c
brokerMessageId   = broker-generated-id-xyz
traceId           = trace-for-entire-workflow
businessKey       = settlement-2026-11-26/tx-1001
~~~

Nếu worker đã commit giao dịch `tx-1001` nhưng reply bị mất, manager có thể tạo **requestId/correlationId khác** khi phát lại. **Business key phải giữ nguyên**, vì đây là cùng tác động nghiệp vụ.

## 4. Correlation ID thuộc phạm vi nào?

Một correlation ID phải **không nhập nhằng trong phạm vi các request có thể cùng xuất hiện**. Các lựa chọn phổ biến:

1. **UUID ngẫu nhiên cho từng request**: dễ tạo, ít nguy cơ trùng; manager cần lưu ánh xạ tới công việc logic.
2. **ID có cấu trúc**: kết hợp execution ID, step và sequence, ví dụ `run-845/step-1092/request-42`; cần chuẩn hóa, kiểm tra tính duy nhất và bảo vệ thông tin nhạy cảm.
3. **ID từ hệ thống điều phối**: nếu framework đã có correlation/sequence protocol, phải **dùng nguyên hợp đồng ấy** thay vì phát minh một ID khác để thay thế.

Một thiết kế phù hợp với nhiều manager cùng dùng reply queue có thể coi khóa lookup là:

~~~text
(protocolVersion, managerInstanceScope, correlationId)
~~~

Hoặc dùng một correlation ID toàn cục duy nhất và **kiểm tra thêm** các metadata job/step trong reply. Không chỉ dựa vào `chunkSequence=42` vì hai job hoặc hai step có thể cùng có sequence 42.

### Khi restart, có nên dùng lại correlation ID cũ?

Không có một câu trả lời đúng cho mọi protocol:

- **Broker redelivery cùng message**: các headers/payload của message thường giữ cùng correlation ID theo hợp đồng transport; worker nên trả lại đúng correlation ấy.
- **Manager chủ động tạo một request mới** để thử lại logical operation: có thể chọn **correlation ID mới** cho lần trao đổi mới và giữ **business/idempotency key cũ**.
- **Framework remote chunking/partitioning** có thể tự quản lý sequence, execution context và trạng thái outstanding; phải tuân theo protocol của đúng phiên bản thư viện.

**Không tự ý đổi correlation ID của một request đang tồn tại** trong adapter, vì reply có thể không còn ghép được. Tương tự, không lấy một correlation ID cũ đã hết hạn rồi dùng cho request mới có ý nghĩa khác.

## 5. Remote chunking: correlation với request chứa nhiều item

Trong **Spring Batch remote chunking**, manager đọc các item, tạo `ChunkRequest` và gửi tới worker; worker thực hiện processing/writing rồi gửi `ChunkResponse`. Manager phải xác định **response nào tương ứng với yêu cầu chunk nào** để theo dõi số chunk còn đợi và tổng hợp trạng thái.

~~~mermaid
flowchart LR
    M["Manager reader + chunk writer"] --> O["Request outbound adapter"]
    O --> Q[("Request queue")]
    Q --> W["Worker processor + writer"]
    W --> R[("Reply queue")]
    R --> I["Manager inbound adapter"]
    I --> M
~~~

Trong Spring Batch Integration, việc ghép reply có thể dựa trên **metadata/protocol bên trong `ChunkRequest`/`ChunkResponse`** (chẳng hạn sequence/execution identity theo version) cùng các header liên quan đến transport. **Không mặc định một header tên `correlationId` là cơ chế duy nhất của Spring Batch**, và cũng không mặc định correlation ID bên ngoài có thể thay thế sequence do framework quản lý.

Một hệ thống dùng builder/flow chính thức cần:

- Giữ nguyên **payload class** và metadata mà remote chunking protocol cần.
- Đảm bảo serialization tương thích giữa manager và worker.
- Bảo toàn **headers dùng để route và correlate** qua outbound/inbound message converters.
- Không biến `ChunkResponse` thành chuỗi `"SUCCESS"` vì như vậy mất thông tin cần để manager đối chiếu.
- Có hợp đồng rõ về timeout, worker failure, reply bị lặp và manager restart.

**Một reply success không đủ để suy ra toàn bộ job đã hoàn tất.** Manager có thể còn nhiều chunk chưa nhận reply, reader chưa kết thúc, hoặc một response lỗi vẫn đang chờ được xử lý.

### Khung cấu hình manager/worker

Ví dụ định hướng Spring Batch Integration 5.x, tập trung vào đường trao đổi; cần ghép broker adapters phù hợp:

~~~java
@Bean
MessageChannel chunkRequests() {
    return new DirectChannel();
}

@Bean
MessageChannel chunkReplies() {
    return new DirectChannel();
}

// Các channel này là đầu nối nội bộ. Cần integration flow:
// chunkRequests -> broker request queue
// broker reply queue -> chunkReplies
//
// Worker app:
// broker request queue -> worker inbound channel
// worker outbound channel -> broker reply queue
//
// Không thay đổi/đánh rơi metadata của ChunkRequest/ChunkResponse
// và headers mà adapter/protocol cần để ghép đúng response.
~~~

Đây là **sơ đồ cấu hình kênh**, không phải job có thể chạy chỉ bằng hai bean `DirectChannel`. Phiên bản Spring Batch Integration, Spring Integration và adapter broker phải tương thích. Khi mở rộng sang Kafka/JMS/RabbitMQ, kiểm tra kiểu thông điệp và các header được mapper truyền qua thực tế.

## 6. Remote partitioning: correlation ở cấp worker StepExecution

Trong **remote partitioning**, manager gửi yêu cầu thực thi **partition**; worker đọc dữ liệu phần mình, chạy một **worker step** và phản hồi kết quả thực thi. Correlation ở đây gắn với **yêu cầu thực thi partition/StepExecution**, không phải từng chunk chứa items đã được manager đọc.

| Thuộc tính | Remote chunking | Remote partitioning |
| --- | --- | --- |
| Manager gửi gì? | `ChunkRequest` chứa tập items hoặc payload theo protocol | Yêu cầu worker xử lý một StepExecution/partition với context |
| Worker đọc dữ liệu? | Thông thường **không**; nhận item từ manager | **Có**; đọc vùng dữ liệu được giao |
| Granularity để đối chiếu | Request/reply của **chunk** | Request/reply hoặc kết quả của **partition execution** |
| Metadata quan trọng | Chunk sequence, execution identity, correlation headers | Job/StepExecution identity, partition name, status |
| Restart | Reader thường ở manager; output có thể đã commit trước reply | Worker step có state/checkpoint; partition có thể được restart |

**Không trộn lẫn `StepExecutionId` của remote partitioning với `chunkSequence` của remote chunking**. Một worker step có thể đọc hàng trăm chunk bên trong nhưng manager chỉ điều phối **một partition request**.

Nếu có hai partition cùng tên ở hai JobInstance khác nhau, chỉ `partitionName="partition0"` chưa đủ để ghép response. Phải kết hợp identity của execution hoặc sử dụng protocol định danh của framework và kiểm tra reply thuộc đúng lần chạy.

## 7. Đi từ Spring Integration message đến broker: header phải được map

Một Spring Integration `Message<T>` có **payload** và **headers**. Khi đưa qua broker, adapter thường phải chuyển headers hoặc metadata ứng dụng thành các thuộc tính transport, và khi nhận phải phục hồi đúng dạng mà handler chờ.

| Transport | Các trường thường liên quan | Điều cần kiểm tra |
| --- | --- | --- |
| AMQP/RabbitMQ | `correlationId`, `replyTo`, message properties/headers | Correlation/reply address được publish và restore đúng qua converter; queue/binding đúng |
| JMS | `JMSCorrelationID`, `JMSReplyTo`, `JMSMessageID` | Không nhầm correlation ID với broker-assigned message ID; kiểu reply destination đúng |
| Kafka | Record key, headers ứng dụng, topic reply | Record key **không mặc nhiên** là correlation ID; consumer reply cần header/contract riêng |
| Spring Integration | Message headers như `correlationId`, reply-channel routing theo flow | Header mapper không làm mất/đổi metadata, channel object không bị serialize sai |

Tên property cụ thể và mapper mặc định **tùy Spring Integration adapter và version**. Một số framework dùng correlation metadata nằm trong **payload**, một số adapter có property transport riêng; có thể tồn tại cả hai. Cần test request/reply end-to-end sau khi đi **qua broker thật**, không chỉ test `DirectChannel` trong cùng JVM.

### Cẩn thận với reply channel

`MessageHeaders.REPLY_CHANNEL` trong Spring Messaging có thể chứa tham chiếu `MessageChannel` hoặc một tên channel trong bối cảnh integration nội bộ. **Không tự serialize một Java `MessageChannel` object rồi gửi sang JVM khác**. Với broker, địa chỉ reply thường là tên destination/queue/topic hoặc metadata mà gateway/adapter có thể ánh xạ được. Bảo đảm worker biết reply phải quay về đâu, manager nào đang đợi, và tương quan request nào.

**Ví dụ dấu hiệu lỗi:** worker log `Processed chunk successfully`, reply queue tăng nhưng manager vẫn timeout. Một nguyên nhân có thể là correlation header bị converter loại bỏ. Nguyên nhân khác là reply route sai, payload không deserialize được hoặc response không thuộc execution mà manager đang theo dõi.

## 8. Hợp đồng request/reply minh họa

Nếu **tự xây một request/reply flow nghiệp vụ** bằng Spring Integration (không sử dụng trực tiếp wire protocol của Spring Batch Integration), nên định nghĩa envelope rõ:

~~~json
{
  "protocolVersion": 1,
  "correlationId": "9713a084-f0d7-4b4b-875f-7f30c033f970",
  "requestId": "9713a084-f0d7-4b4b-875f-7f30c033f970",
  "jobExecutionId": 845,
  "stepExecutionId": 1092,
  "logicalWorkId": "settlement/chunk-0042",
  "attempt": 1,
  "snapshotId": "snapshot-2026-11-26",
  "replyDestination": "batch-reply-v1",
  "payload": {
    "transactionIds": ["tx-1001", "tx-1002"]
  }
}
~~~

Reply:

~~~json
{
  "protocolVersion": 1,
  "correlationId": "9713a084-f0d7-4b4b-875f-7f30c033f970",
  "requestId": "9713a084-f0d7-4b4b-875f-7f30c033f970",
  "jobExecutionId": 845,
  "stepExecutionId": 1092,
  "logicalWorkId": "settlement/chunk-0042",
  "attempt": 1,
  "outcome": "SUCCEEDED",
  "processedItems": 2
}
~~~

**Đây không phải JSON protocol chính thức của `ChunkRequest`/`ChunkResponse` Spring Batch.** Nó minh họa những thông tin mà một giao thức request/reply tùy biến có thể cần. Nếu dùng remote chunking/partitioning builder của framework, **giữ protocol framework**, chỉ thêm metadata hỗ trợ khi adapter được thiết kế để giữ nguyên chúng.

### Validation ở phía nhận reply

Manager không nên chỉ làm:

~~~java
// SAI: chỉ dựa vào chuỗi correlation và một cờ boolean.
if (pending.containsKey(reply.correlationId())
        && reply.outcome().equals("SUCCEEDED")) {
    markChunkCompleted();
}
~~~

Một bước ghép có kiểm soát cần:

1. **Tìm request đang chờ** theo correlation ID (và namespace nếu giao thức yêu cầu).
2. Kiểm tra **protocol version** và loại reply.
3. Đối chiếu **job/step execution**, logical work và attempt với request đã gửi.
4. Xác thực nguồn/giao thức broker; không tin mù các header do client không được ủy quyền gửi.
5. Đánh dấu request hoàn tất **một lần** bằng transition nguyên tử hoặc cơ chế tương đương.
6. Chỉ sau đó đánh thức phía đang đợi, tổng hợp kết quả và cập nhật metadata phù hợp.

Nếu reply trùng, sai execution hoặc không tìm thấy request, **không** âm thầm dùng nó để hoàn tất một request khác.

## 9. Sinh correlation ID và đăng ký trước khi publish

Với một request/reply flow tùy biến, một cách phổ biến là sinh UUID và đăng ký trạng thái **trước khi gửi**:

~~~java
record WorkRequest(
        String correlationId,
        long jobExecutionId,
        long stepExecutionId,
        String logicalWorkId,
        String snapshotId) {}

record WorkReply(
        String correlationId,
        long jobExecutionId,
        long stepExecutionId,
        String logicalWorkId,
        boolean success) {}

String correlationId = UUID.randomUUID().toString();
WorkRequest request = new WorkRequest(
        correlationId,
        jobExecutionId,
        stepExecutionId,
        logicalWorkId,
        snapshotId);

// Trước khi publish:
// 1. Đăng ký correlationId -> expected execution/work.
// 2. Sau đó mới publish request.
// 3. Nếu publish thất bại, xử lý trạng thái pending theo hợp đồng.
~~~

**Vì sao phải đăng ký trước publish?** Một worker nhanh có thể phản hồi trước khi thread gửi kịp đăng ký mapping. Khi đó reply hợp lệ trở thành “không có request đang đợi”. Đây là một race condition thường xuất hiện ở test in-memory nhanh nhưng khó tái hiện trên production.

Nếu mapping chỉ lưu trong RAM, manager chết sẽ mất danh sách pending. Với giao thức yêu cầu khôi phục sau crash, cần **sổ cái request bền vững** hoặc tận dụng metadata/restart protocol của Spring Batch; một `ConcurrentHashMap` không đủ để giải quyết distributed recovery.

### Có nên dùng timestamp hoặc counter làm ID?

`System.currentTimeMillis()` đơn lẻ có thể trùng giữa hai request cùng millisecond; counter trong JVM có thể reset khi restart hoặc trùng giữa nhiều manager. UUID hoặc ID có namespace và cơ chế cấp phát duy nhất thường an toàn hơn. Đừng suy ra “ID có timestamp” là tự động tăng toàn cục, hoặc dùng index trong List làm correlation giữa nhiều manager.

## 10. Registry pending request: ví dụ Java có kiểm soát

Trong một **RPC tùy biến** (không phải Spring Batch remote chunking protocol), một registry in-memory có thể ghép reply bằng correlation ID. Ví dụ dưới đây có mục đích minh họa **thread-safe lookup và validation**, không giải quyết khôi phục qua JVM crash:

~~~java
final class PendingReplyRegistry {
    private final ConcurrentMap<String, Pending> pending =
            new ConcurrentHashMap<>();

    record Expected(long jobExecutionId,
                    long stepExecutionId,
                    String logicalWorkId) {}

    private record Pending(
            Expected expected,
            CompletableFuture<WorkReply> future) {}

    CompletableFuture<WorkReply> register(
            String correlationId, Expected expected) {
        var future = new CompletableFuture<WorkReply>();
        Pending created = new Pending(expected, future);
        if (pending.putIfAbsent(correlationId, created) != null) {
            throw new IllegalArgumentException(
                    "Duplicate pending correlation ID");
        }
        return future;
    }

    boolean acceptReply(WorkReply reply) {
        Pending entry = pending.get(reply.correlationId());
        if (entry == null) {
            // Trễ, lặp hoặc không thuộc manager/execution đang đợi.
            return false;
        }
        Expected x = entry.expected();
        boolean sameExecution =
                x.jobExecutionId() == reply.jobExecutionId()
                && x.stepExecutionId() == reply.stepExecutionId()
                && x.logicalWorkId().equals(reply.logicalWorkId());
        if (!sameExecution) {
            // Không cho reply mạo danh/nhầm execution hoàn tất pending.
            return false;
        }
        if (pending.remove(reply.correlationId(), entry)) {
            entry.future().complete(reply);
            return true;
        }
        // Một thread khác đã hoàn tất hoặc hủy pending này.
        return false;
    }

    void expire(String correlationId, Throwable reason) {
        Pending entry = pending.remove(correlationId);
        if (entry != null) {
            entry.future().completeExceptionally(reason);
        }
    }

    int outstanding() {
        return pending.size();
    }
}
~~~

**Điểm tốt:** `putIfAbsent` ngăn hai pending cùng ID, `remove(key, value)` là kiểm tra/xóa nguyên tử cho đúng entry, và `CompletableFuture` đánh thức bên đợi khi có reply phù hợp.

**Giới hạn nghiêm trọng:** đây chỉ là bản **minh họa trong một JVM**, không phải cơ chế production hoàn chỉnh:

- Chưa có **persistence** hoặc khả năng phục hồi pending sau manager crash.
- Chưa có scheduler/TTL tự động: caller phải **chủ động gọi `expire`** khi timeout, cancel hoặc job thất bại.
- Cần thiết kế rõ semantics khi reply và timeout tranh chấp, khi publish thất bại, khi Future bị hủy hoặc khi manager shutdown.
- Không xác thực signature/ACL của message; registry check field **không thay thế xác thực broker/worker**.
- Nếu broker redeliver reply sau khi entry bị remove, hàm trả `false`; cần log/metric và chính sách xử lý late/duplicate riêng.
- Kết quả `success=true` chưa chứng minh DB commit; vẫn cần hợp đồng worker, transaction và business reconciliation.

Không gắn lớp tùy biến này lên Spring Batch remote chunking chỉ để thay thế cơ chế response correlation sẵn có. Hãy áp dụng registry khi thật sự xây **một giao thức riêng** và có đầy đủ lý do thiết kế, test và persistence.

## 11. Timeout, phản hồi trễ và trạng thái không chắc chắn

Timeout nghĩa là **manager chưa nhận được reply phù hợp trong giới hạn chờ**, **không** có nghĩa worker chưa xử lý hay DB chưa commit.

~~~text
T0: manager gửi req-42
T1: worker nhận req-42
T2: worker commit business DB
T3: reply bị chậm do broker/network
T4: manager timeout req-42
T5: manager tạo req-43 cho cùng logicalWorkId (theo policy)
T6: reply req-42 mới đến
~~~

Ở T6, nếu manager dùng mỗi `logicalWorkId` để đánh thức request mới, reply cũ có thể bị nhận nhầm như reply req-43. Nếu dùng per-attempt correlation và execution validation, nó có thể phân loại reply req-42 là **late reply**. Tuy nhiên, worker của req-43 vẫn có thể đang chạy và tác động nghiệp vụ đã được áp dụng ở T2. Vì vậy cần **idempotency key ở sink**.

### Một state machine đơn giản cho RPC tùy biến

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> SENT: publish accepted
    CREATED --> FAILED: publish failed
    SENT --> SUCCEEDED: valid success reply
    SENT --> FAILED: valid error reply
    SENT --> TIMED_OUT: timeout
    TIMED_OUT --> RECONCILING: unknown outcome
    RECONCILING --> SUCCEEDED: evidence of completed effect
    RECONCILING --> RETRYING: replay permitted
    RETRYING --> SENT: new request/correlation
~~~

Đây là **state machine minh họa**, không phải trạng thái enum mặc định của Spring Batch. Khi timeout, không đơn giản chuyển `TIMED_OUT -> FAILED` rồi xóa output cũ; cần xác định policy và sự thật phía worker. Có thể quản lý TTL của reply cũ, nhưng xoá/bỏ reply phải đi kèm đối soát logical operation.

## 12. Retry, redelivery và correlation ID: ba trường hợp khác nhau

| Trường hợp | Điều gì được lặp? | Correlation ID nên được hiểu thế nào? | Tính đúng đắn nghiệp vụ |
| --- | --- | --- | --- |
| Broker redeliver **cùng request message** | Một delivery xảy ra lần nữa | Giữ metadata của request gốc theo transport contract | Worker idempotent, ACK/commit đúng |
| Manager chủ động **tạo request retry mới** | Một request mới cho cùng work | Có thể có correlation mới; liên kết với cùng logical work | Business key/idempotency key phải ổn định |
| Manager **restart JobInstance** | JobExecution mới có thể replay item/partition | Không nhận nhầm reply từ JobExecution cũ; tuân protocol framework | Snapshot ổn định, checkpoint và writer replay-safe |

Với remote chunking, một `ItemProcessor` có thể được gọi lại cho cùng item sau rollback hoặc redelivery. **Đừng dùng correlation ID của từng chunk làm idempotency key duy nhất** khi business operation có thể bị chuyển sang chunk khác.

Ví dụ SQL cho hiệu ứng idempotent từ cùng batch và transaction:

~~~sql
CREATE TABLE normalized_transaction (
    batch_key       VARCHAR(100) NOT NULL,
    transaction_id  VARCHAR(100) NOT NULL,
    net_amount      NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, transaction_id)
);

INSERT INTO normalized_transaction (
    batch_key, transaction_id, net_amount)
VALUES (:batchKey, :transactionId, :netAmount)
ON CONFLICT (batch_key, transaction_id)
DO UPDATE SET net_amount = EXCLUDED.net_amount;
~~~

UPSERT đảm bảo không tạo hai **dòng** cùng khóa; nếu dữ liệu nguồn hoặc rule có thể thay đổi, `DO UPDATE` có thể che giấu conflict nghiệp vụ. Với yêu cầu nghiêm ngặt, lưu checksum/rule version và **từ chối khi nội dung khác**. Với API thanh toán hoặc event ngoài DB transaction, cần idempotency key tại hệ thống nhận, dedup ledger hoặc transactional outbox.

## 13. ACK, commit, reply và correlation: bốn việc khác nhau

~~~text
Manager                       Broker                  Worker
   | publish request corr-X      |                       |
   |---------------------------->|                       |
   |                             | deliver corr-X        |
   |                             |---------------------->|
   |                             |                       | DB transaction
   |                             |                       | COMMIT
   |                             |  ACK request delivery  |
   |                             |<----------------------|
   |                             |  publish reply corr-X |
   |                             |<----------------------|
   |  reply corr-X               |                       |
   |<----------------------------|                       |
~~~

Sơ đồ là **một thứ tự minh họa**; trong thực tế, ACK và publish reply có thể xảy ra theo thứ tự khác tùy listener/adapter. Không có distributed ACID transaction mặc định bao trùm manager DB, broker và worker business DB.

| Sự kiện | Nó chứng minh gì? | Nó không chứng minh gì? |
| --- | --- | --- |
| Broker publisher confirm | Publish được broker xác nhận theo cấu hình | Worker đã xử lý/chốt DB |
| Consumer ACK | Delivery đã được acknowledge theo policy | Reply đến manager hoặc DB transaction chắc chắn commit |
| DB COMMIT | Tác động trong transaction DB đã được lưu | Broker biết kết quả hay manager đã nhận reply |
| Reply `SUCCEEDED` với đúng correlation | Worker/giao thức báo thành công cho request được chỉ định | Không tự chứng minh mọi side effect ngoài DB |
| StepExecution `COMPLETED` | Framework đánh giá step hoàn tất theo quy tắc batch | Dữ liệu cuối chắc chắn đúng khi có lỗi thiết kế SQL/idempotency |

### Trường hợp nguy hiểm: đã commit nhưng chưa reply

Nếu worker đã commit rồi chết trước ACK/reply, broker có thể giao lại request theo cấu hình. Correlation ID giúp nhận diện reply của **request**, nhưng **không khóa được giao dịch nghiệp vụ** ở hai worker khác nhau. Một `synchronized` Java lock cũng không đủ giữa hai JVM. Phải dùng unique constraint, idempotent operation hoặc một protocol dedup bền vững.

## 14. Nhiều manager dùng chung broker hoặc reply queue

Khi có nhiều manager instance/job chạy cùng lúc, rủi ro ghép nhầm tăng:

~~~text
Manager A: jobExecutionId=845, request sequence=12
Manager B: jobExecutionId=846, request sequence=12

Reply queue chung:
  reply sequence=12, của job 846
~~~

Nếu chỉ dùng sequence 12, manager A có thể hiểu nhầm. Cần **execution identity/namespace** và đường routing hoặc correlation contract được kiểm chứng. Những lựa chọn:

- Tạo correlation ID đủ duy nhất toàn cục và validate thêm execution/step.
- Dùng reply destination riêng theo manager/execution khi broker/adapter cho phép, đồng thời có lifecycle và cleanup.
- Dùng shared reply queue với consumer group/selector/routing bảo đảm chỉ đúng manager xử lý reply của mình.
- Nếu một reply nhầm tới manager khác, **không ACK bỏ một cách mù quáng** khi contract yêu cầu route lại; phân biệt lỗi routing với reply thật sự orphan.

**Lưu ý:** trong một queue có nhiều competing consumers, **chỉ gắn correlation ID không bảo đảm broker phân phối reply đến đúng manager**. Một consumer có thể lấy message của manager khác. Cần thiết kế routing/selector/handler theo semantics của broker; nếu consumer nhận nhầm rồi ACK, manager đúng sẽ không bao giờ thấy reply.

### Tránh lộ thông tin qua correlation ID

Một ID dạng `tenant-secret-123/customer-email@example.com/request-42` dễ gây lộ dữ liệu trong broker logs, tracing, dashboard và DLQ. Dùng ID opaque; tenant/business context chỉ nên có trong trường bảo vệ phù hợp và được che khi log. Không nhét access token, password hoặc credentials vào correlation header.

## 15. Bảo toàn header qua adapter và sự cố serialization

Một request có thể đi qua nhiều tầng:

~~~text
Spring Integration Message
   -> outbound adapter
   -> broker properties/headers
   -> inbound adapter
   -> worker integration flow
   -> reply outbound adapter
   -> broker
   -> manager reply inbound adapter
~~~

Mỗi lần convert là một điểm có thể **mất hoặc đổi** correlation/metadata.

**Kiểm tra theo thứ tự:**

1. Manager đã tạo/giữ ID đúng theo protocol chưa?
2. Sau outbound mapping, broker message có correlation property/header không?
3. Inbound adapter ở worker có khôi phục được property ấy không?
4. Worker có copy đúng correlation khi trả reply, hay tự sinh ID mới không?
5. Reply outbound có map đúng property của broker không?
6. Manager inbound có khôi phục correlation về đúng header/protocol không?
7. Reply payload có version/class mà manager hiểu được không?

Nếu một adapter chỉ map whitelist header, trường tùy biến có thể bị loại. Không sửa mã Spring Batch core để “né” vấn đề; hãy cấu hình mapper/converter tương thích và test round-trip.

**Khuyến nghị:** viết một integration test chạy qua **đúng broker** đang dùng (RabbitMQ, JMS hoặc Kafka với bridge/protocol thích hợp). Một bài unit test gửi `Message` qua `DirectChannel` chưa chứng minh header có thể qua network và trở lại.

## 16. Phản hồi trùng, sai execution hoặc không rõ nguồn

Khi nhận reply, có bốn nhóm kết quả cần phân biệt:

| Nhóm reply | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| **Matched** | Correlation hợp lệ, execution/sequence/type khớp, đang pending | Chuyển trạng thái đúng một lần, hoàn tất request |
| **Duplicate** | Cùng reply/request đã được xử lý trước đó | Không cộng trạng thái/lượt hoàn thành lần hai; ghi metric |
| **Late/orphan** | Không còn pending, có thể do timeout/restart | Tra ledger và chính sách đối soát; không gán cho request mới |
| **Invalid/mismatched** | Correlation sai, wrong job/step, payload lỗi, không được ủy quyền | Từ chối, cảnh báo và điều tra; không sửa metadata batch |

**Không** dùng một catch-all handler để trả success khi có lỗi deserialize hoặc không tìm thấy correlation. Điều đó có thể biến một partition/chunk chưa xử lý thành “đã xong” và làm mất dữ liệu.

### Khi reply bị lỗi thì ACK thế nào?

Phụ thuộc vào broker, listener container và trách nhiệm của ứng dụng. Nếu reply không khớp vì **routing sai**, ACK và bỏ có thể khiến manager chờ mãi. Nếu đó là **duplicate đã được xử lý**, việc giữ lại và redeliver vô hạn cũng sai. Phải có chính sách rõ cho từng loại: retry/route lại, dead-letter, lưu orphan để đối soát, hoặc ACK sau khi ghi nhận trạng thái bền vững. Không viết một `catch(Exception) { ack(); }` cho mọi trường hợp.

## 17. Tạo ledger bền vững cho giao thức tùy biến

Nếu hệ thống xây một request/reply protocol riêng ngoài Spring Batch Integration, có thể cần lưu tình trạng request để khôi phục sau manager crash. Ví dụ bảng PostgreSQL:

~~~sql
CREATE TABLE request_correlation (
    run_key          VARCHAR(120) NOT NULL,
    correlation_id   VARCHAR(120) NOT NULL,
    logical_work_id  VARCHAR(160) NOT NULL,
    attempt_no       INTEGER NOT NULL,
    state            VARCHAR(20) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_key, correlation_id),
    UNIQUE (run_key, logical_work_id, attempt_no)
);
~~~

`run_key` có thể là định danh execution/namespace do protocol của ứng dụng xác định; `logical_work_id` giữ mối liên hệ với operation cần hoàn tất. Ví dụ update trạng thái với compare-and-set:

~~~sql
UPDATE request_correlation
SET state = 'SUCCEEDED',
    updated_at = CURRENT_TIMESTAMP
WHERE run_key = :runKey
  AND correlation_id = :correlationId
  AND logical_work_id = :logicalWorkId
  AND state = 'PENDING';
~~~

Kiểm tra **số row được update**: 1 nghĩa là transition đã thắng; 0 nghĩa là state đã đổi, correlation không tồn tại hoặc không khớp. Nhưng transition trạng thái thành công **không thay thế xác thực payload, kết quả nghiệp vụ và transaction boundary**.

Đối với Spring Batch dùng protocol chính thức, **không tự thêm bảng này như một yêu cầu mặc định**. JobRepository và integration components đã có hợp đồng trạng thái riêng; xây ledger bổ sung chỉ khi cần ở lớp orchestration/side effect và phải tránh tạo hai nguồn sự thật mâu thuẫn.

## 18. Quan sát và tracing correlation ID

Correlation ID hữu ích khi nối log của manager, broker, worker và reply consumer:

~~~text
manager  SEND     corr=req-42 step=workerStep exec=845
broker   ROUTED   corr=req-42 queue=batch.requests
worker-2 RECEIVE  corr=req-42 attempt=1
worker-2 COMMIT   corr=req-42 items=200
worker-2 REPLY    corr=req-42 result=SUCCEEDED
manager  MATCHED  corr=req-42 result=SUCCEEDED
~~~

Đây là mẫu log diễn giải, không phải tên event mặc định của framework.

Nên đo:

| Metric | Ý nghĩa | Khi bất thường |
| --- | --- | --- |
| `requests_sent_total` | Số request đã publish theo hợp đồng | Tăng nhưng worker không nhận |
| `requests_in_flight` | Số request chưa có outcome rõ | Tăng liên tục, nguy cơ backlog |
| `reply_latency_seconds` | Từ lúc gửi đến lúc nhận reply hợp lệ | p95/p99 tăng, DB/broker nghẽn |
| `reply_correlation_miss_total` | Không tìm thấy request phù hợp | Header bị mất, reply trễ hoặc routing sai |
| `reply_duplicate_total` | Reply được phát/giao nhiều lần | Redelivery hoặc duplicate publish |
| `reply_mismatch_total` | Khác job/step/attempt/protocol | Sai execution, lỗi mapping hoặc nghi vấn bảo mật |
| `reply_timeout_total` | Request hết hạn chờ | Worker chậm, reply mất hoặc broker lỗi |
| `request_redelivery_total` | Broker giao lại request | ACK/DB failure hoặc consumer crash |
| `dead_letter_messages` | Message cần can thiệp | Poison/mismatch chưa được xử lý |
| DB commit/rollback/connection wait | Năng lực worker thực tế | Nút thắt ở sink |

**Không dùng mỗi correlation ID làm tag của metric time series**, vì tạo cardinality rất lớn. Dùng nó trong log/tracing với retention, sampling và hạn chế dữ liệu nhạy cảm; metric tổng hợp theo job/step/loại lỗi. Trace ID có thể giúp nối nhiều span và nhiều request; correlation ID giúp tìm **một trao đổi request/reply cụ thể**.

### Một nguyên tắc thực dụng về thời gian

`replyLatency = timeReceivedReply - timePublishedRequest` chỉ là một **quan sát phía manager**, bao gồm queue wait, worker processing, network và reply path. Đừng lấy nó bằng thời gian DB transaction. Nếu cần phân rã, instrument các mốc publish, dequeue, process, commit, reply và matched với đồng hồ/trace phù hợp.

## 19. Unit test: ghép reply trái thứ tự và không ghép nhầm

Với registry ví dụ ở phần 10, có thể kiểm thử không phụ thuộc broker. Giả định các `WorkReply` và `PendingReplyRegistry` đã được khai báo:

~~~java
@Test
void outOfOrderRepliesMatchOnlyTheirRequests() throws Exception {
    PendingReplyRegistry registry = new PendingReplyRegistry();
    var expectedA = new PendingReplyRegistry.Expected(
            845L, 1092L, "work-A");
    var expectedB = new PendingReplyRegistry.Expected(
            845L, 1092L, "work-B");

    CompletableFuture<WorkReply> a =
            registry.register("corr-A", expectedA);
    CompletableFuture<WorkReply> b =
            registry.register("corr-B", expectedB);

    WorkReply replyB =
            new WorkReply("corr-B", 845L, 1092L, "work-B", true);
    WorkReply replyA =
            new WorkReply("corr-A", 845L, 1092L, "work-A", true);

    assertTrue(registry.acceptReply(replyB)); // B đến trước A.
    assertSame(replyB, b.get(1, TimeUnit.SECONDS));
    assertFalse(a.isDone());

    assertTrue(registry.acceptReply(replyA));
    assertSame(replyA, a.get(1, TimeUnit.SECONDS));
    assertEquals(0, registry.outstanding());
}

@Test
void duplicateOrWrongExecutionCannotCompletePending() {
    PendingReplyRegistry registry = new PendingReplyRegistry();
    var expected = new PendingReplyRegistry.Expected(
            845L, 1092L, "work-A");
    var pending = registry.register("corr-A", expected);

    // Correlation đúng nhưng JobExecution sai.
    assertFalse(registry.acceptReply(
            new WorkReply("corr-A", 846L, 1092L, "work-A", true)));
    assertFalse(pending.isDone());

    WorkReply correct =
            new WorkReply("corr-A", 845L, 1092L, "work-A", true);
    assertTrue(registry.acceptReply(correct));
    assertFalse(registry.acceptReply(correct)); // Duplicate reply.
}
~~~

Test này chứng minh **correlation + execution validation** ở một JVM, không chứng minh worker đã commit hoặc broker bảo toàn header. Dùng `CountDownLatch`/barrier và executor test nếu cần tạo hai reply xử lý đồng thời, không dựa vào `Thread.sleep` để mong race xuất hiện.

## 20. Integration test với broker và Spring Batch thật

Cần test trên transport đúng môi trường (RabbitMQ/JMS/Kafka bridge tương ứng), manager, worker và JobRepository/DB test. Một bộ test có giá trị:

1. **Round-trip header:** gửi request, chụp thông điệp ở phía worker và reply phía manager; xác minh correlation/protocol metadata đi qua các adapter không đổi.
2. **Trái thứ tự:** giữ worker A bằng latch, cho B hoàn thành trước, xác minh manager chỉ đánh dấu đúng chunk/partition.
3. **Hai manager:** cùng chạy hai JobExecution có sequence giống nhau, dùng reply routing phù hợp; không có cross-manager match.
4. **Duplicate reply:** publish/giao lại reply đã xử lý; không cộng trạng thái hai lần hoặc báo COMPLETED giả.
5. **Mất correlation:** loại bỏ header/metadata trong môi trường test; hệ thống phải báo rõ mismatch/timeout, không tự gán reply ngẫu nhiên.
6. **Worker chết trước commit:** xác minh retry/redelivery theo broker ACK policy và output không sai.
7. **Worker chết sau commit trước reply:** cùng business operation được replay an toàn, correlation mới/cũ xử lý đúng contract.
8. **Manager restart:** khởi động lại cùng JobInstance và snapshot, xử lý stale reply/in-flight request mà không nhân đôi business effect.
9. **Poison reply/schema mismatch:** fail/route DLQ theo policy; không nuốt lỗi deserialize.
10. **Shutdown và backlog:** giới hạn outstanding, timeout, metrics và cleanup registry/ledger không làm mất công việc.

### Ma trận hành vi cần ghi nhận

| Tình huống | Kỳ vọng correlation | Kỳ vọng nghiệp vụ |
| --- | --- | --- |
| Reply đúng, đến muộn hơn reply khác | Ghép đúng request gốc | Mỗi work được tổng hợp đúng |
| Reply trùng | Không hoàn tất hai lần | Không nhân đôi side effect |
| Reply từ JobExecution cũ | Không ghép nhầm execution mới | Có đối soát/replay an toàn |
| Broker redeliver request | Giữ request protocol metadata | Writer idempotent |
| Manager gửi retry request mới | ID theo attempt contract, cùng logical work | Cùng idempotency key |
| Mất header correlation | Báo lỗi rõ, không ghép theo thứ tự | Không báo success giả |
| Wrong tenant/job/step | Reject/alert, bảo toàn quyền | Không ghi lẫn dữ liệu |

**Test với `DirectChannel` thuần là chưa đủ**: converter/mapper của broker có thể làm mất header chỉ khi vượt ranh giới JVM. Đồng thời, kill thật worker container sẽ bộc lộ ACK, reply và DB commit timing mà một unit test ném exception không thể mô phỏng đầy đủ.

## 21. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Worker báo thành công nhưng manager cứ chờ | Reply route sai, correlation header bị drop, schema không tương thích | Kiểm tra từng adapter/hop và payload protocol |
| Manager nhận reply nhưng ghép sai chunk | Dùng sequence không namespace, gán theo thứ tự | Dùng correlation/protocol identity đầy đủ |
| Chỉ lỗi khi nhiều manager đồng thời | Shared reply queue không route đúng owner | Selector/destination/routing theo manager hoặc execution |
| Reply đến sau timeout làm request mới thành success | Tái sử dụng correlation ID hoặc lookup theo logical work đơn giản | Per-attempt correlation + reconcile late reply |
| Counter completion tăng hai lần | Duplicate reply chưa được loại | Atomic transition, dedup reply theo request state |
| Trùng dữ liệu sau worker crash | Tưởng correlation ID thay thế idempotency | Unique business key, transactional outbox/dedup |
| Restart bỏ sót dữ liệu | Input snapshot đổi, checkpoint không tương thích | Giữ snapshot/JobInstance, đối soát |
| Bị memory leak khi job lớn | Pending registry không expire/cleanup | TTL, cancel và durable ledger nếu cần |
| Kafka key đúng nhưng reply vẫn miss | Record key không được map thành correlation header | Explicit header/protocol mapping, test round-trip |
| Worker nhận nhưng không deserialize được | DTO/schema/version hoặc converter sai | Tương thích manager–worker, DLQ và cảnh báo |
| Log có nhiều correlation ID trùng | Counter reset, ID tạo từ timestamp thấp độ phân giải | UUID/namespace và kiểm tra uniqueness |
| Phát hiện reply giả/cross-tenant | Tin header từ nguồn không xác thực | Broker auth/ACL, validation execution/tenant, tránh PII |

## 22. Runbook khi mất correlation

Khi manager có nhiều request pending hoặc timeout bất thường:

1. **Xác định phạm vi**: JobInstance/JobExecution, manager node, step, broker request/reply destination và thời điểm bắt đầu lỗi.
2. **Lấy một request mẫu** theo correlation hoặc protocol sequence, tra log publish và event nhận ở worker.
3. **Theo từng hop**: message trước outbound adapter, ở broker, sau worker inbound, trước worker reply outbound và sau manager reply inbound.
4. **Đối chiếu metadata**: correlation ID, job/step execution, logical work, schema, reply destination; không chỉ so sánh một chuỗi `SUCCESS`.
5. **Kiểm tra broker**: depth, oldest age, DLQ, unacked, redelivery, selector/consumer routing và quyền.
6. **Kiểm tra worker DB**: kết quả đã commit chưa, transaction rollback/timeout hay sink đang nghẽn?
7. **Phân loại outcome**: chưa xử lý, đã commit nhưng mất reply, reply trễ, reply sai job hoặc không thể xác nhận.
8. **Khôi phục có kiểm soát**: sửa mapper/route/cấu hình; nếu phải replay thì giữ snapshot, idempotency key và restart contract.
9. **Đối soát cuối**: tập business keys và giá trị, StepExecution status, orphan/stale replies; đừng chỉ dựa vào queue depth bằng 0.
10. **Ngăn tái diễn**: thêm round-trip integration test, alert correlation miss, timeout và duplicate; ghi lại runbook/incident.

**Không tự sửa JobRepository để đánh dấu `COMPLETED` cho chunk/step đang thiếu reply**, và cũng không xóa toàn bộ reply queue chỉ để metric trở về 0 khi chưa xác minh những kết quả nghiệp vụ đã commit.

## 23. Bài thực hành và checklist

**Bài thực hành:** tạo manager gửi tối thiểu 20 logical work request qua broker tới ba worker. Mỗi request có correlation ID duy nhất, execution identity, logical work ID, snapshot và business key. Với Spring Batch remote chunking thật, dùng protocol chính thức để gửi `ChunkRequest`/`ChunkResponse`; nếu tự xây RPC test riêng, dùng envelope/registry minh họa của bài.

Các lượt chạy:

1. **Normal path:** reply tới bất kỳ thứ tự nào nhưng đúng request; mọi business record được xuất đủ.
2. **Out-of-order:** dùng latch làm request đầu chậm hơn hai request sau; manager vẫn ghép đúng.
3. **Duplicate:** gửi reply trùng hoặc redeliver request; completion không tăng hai lần, sink không nhân đôi.
4. **Late reply:** timeout một request, tạo attempt mới, rồi thả reply cũ; không cho reply cũ hoàn tất nhầm attempt mới.
5. **Multi-manager:** hai JobExecution đồng thời có cùng chunk sequence; reply queue/routing không lẫn job.
6. **Header loss:** cố ý bỏ correlation ở một adapter trong test; phải fail/alert rõ, không fallback theo thứ tự.
7. **Crash:** kill worker trước commit và sau commit trước reply; xác minh retry/redelivery/ACK và DB output.
8. **Restart:** khởi chạy lại cùng JobInstance với snapshot bất biến; đối soát output và xử lý stale messages.
9. **Performance:** đo in-flight requests, reply latency p95/p99, broker backlog, redelivery và correlation misses.

### Checklist trước khi chạy production

- [ ] Đã phân biệt correlation ID, message ID, trace ID, chunk/StepExecution identity và idempotency key.
- [ ] Request/reply contract được version hóa; correlation có namespace/đủ duy nhất, không mang dữ liệu nhạy cảm.
- [ ] Nếu dùng Spring Batch Integration, giữ nguyên protocol metadata thay vì thay `ChunkRequest`/`ChunkResponse` bằng payload tùy ý.
- [ ] Adapter manager/worker bảo toàn correlation và reply route qua broker; đã có round-trip test.
- [ ] Reply được đối chiếu cả correlation và execution/work identity; completion transition chỉ xảy ra một lần.
- [ ] Có timeout, xử lý late/duplicate/orphan reply, registry cleanup và persistence nếu giao thức tùy biến đòi restart.
- [ ] Có retry hữu hạn/redelivery policy, ACK phù hợp transaction và writer idempotent.
- [ ] Có cơ chế định tuyến reply đúng manager khi nhiều job/manager dùng chung broker.
- [ ] Có xác thực broker/worker, quyền theo tenant và hạn chế PII trong headers, logs, DLQ.
- [ ] Có metric in-flight, reply latency, timeout, correlation miss, duplicate và đối soát dữ liệu thực.
- [ ] Đã kiểm thử worker/manager crash, missing header, mismatch execution, out-of-order, retry và restart.

**Ghi nhớ:** **Correlation ID trả lời “reply này dành cho request nào?”**, không trả lời “record nghiệp vụ đã được áp dụng đúng một lần chưa?”. Trong Spring Batch phân tán, cần **giữ nguyên metadata của protocol qua middleware, đối chiếu đúng execution, chấp nhận reply có thể trễ/lặp và dùng idempotency riêng cho tác động nghiệp vụ**. Khả năng mở rộng đáng tin cậy đến từ sự kết hợp giữa message routing, transaction, JobRepository, retry/restart và kiểm thử thực tế, chứ không chỉ từ một header chứa UUID.
