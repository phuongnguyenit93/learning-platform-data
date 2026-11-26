# Correlation header của batch message trong Spring Batch Integration

## Mục tiêu bài học

Khi Spring Batch chạy theo mô hình **remote chunking** hoặc **remote partitioning**, một manager có thể gửi nhiều yêu cầu tới các worker thông qua Spring Integration và message broker. Các worker xử lý với thời gian khác nhau, phản hồi có thể đến không đúng thứ tự gửi, request có thể được giao lại và một số phản hồi có thể bị trễ hoặc thất lạc. Muốn biết **phản hồi này thuộc phần việc nào**, hệ thống cần một cơ chế liên kết request–reply đáng tin cậy.

**Correlation header** là một phần quan trọng của cơ chế đó. Tuy nhiên, correlation ID **không đồng nghĩa** với `messageId`, `JobExecutionId`, `StepExecutionId`, trace ID, message key hay idempotency key. Dùng sai một trong những định danh này có thể làm manager ghép nhầm reply, làm aggregator gộp sai message hoặc khiến một chunk được ghi nhiều lần sau retry.

Bài học thuộc chương **Spring Batch Integration** của module **SPRING_BATCH_SCALING_OPERATIONS**, với mục tiêu mở rộng workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các kiến trúc phân tán nhưng vẫn bảo đảm thread safety, retry/restart, đo bottleneck và khả năng vận hành.

Sau bài, bạn có thể:

- Giải thích correlation header ở cấp message, request–reply và nhóm message.
- Phân biệt correlation ID với message ID, job/step execution ID, sequence, trace ID và idempotency key.
- Thiết kế định danh liên kết request–reply khi nhiều chunk hoặc partition cùng chạy.
- Hiểu vai trò của `correlationId`, `sequenceNumber`, `sequenceSize` trong Spring Integration.
- Tổ chức việc truyền header qua AMQP/RabbitMQ, Kafka hoặc gateway mà không dựa vào giả định header luôn tự tồn tại.
- Xử lý duplicate reply, timeout, late reply, broker redelivery và restart an toàn.
- Xây test xác nhận không ghép nhầm message và không lặp side effect nghiệp vụ.
- Đo latency, inflight requests và correlation errors khi scale worker.

## 1. Vì sao phải tương quan request và reply?

Giả sử manager đã gửi ba chunk:

~~~text
09:00:00  Request A → Worker 1
09:00:01  Request B → Worker 2
09:00:02  Request C → Worker 3
~~~

Vì khối lượng xử lý khác nhau, thứ tự phản hồi có thể là:

~~~text
09:00:03  Reply B
09:00:04  Reply C
09:00:08  Reply A
~~~

Nếu manager chỉ lấy **reply đến đầu tiên** gắn với **request gửi đầu tiên**, kết quả sẽ sai. Phải có định danh hoặc protocol state liên kết phản hồi với đúng yêu cầu gốc.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant A as Worker A
    participant B as Worker B

    M->>Q: Request A, correlation=A
    M->>Q: Request B, correlation=B
    Q->>A: Request A
    Q->>B: Request B
    B-->>Q: Reply B, correlation=B
    Q-->>M: Reply B
    A-->>Q: Reply A, correlation=A
    Q-->>M: Reply A
    Note over M: Ghép B↔B, A↔A dù reply đảo thứ tự
~~~

**Correlation** giải đáp câu hỏi: *message này thuộc giao dịch hội thoại, phần việc logic hoặc nhóm message nào?* Tùy trường hợp, mục đích là:

1. Ghép một **reply** với **request** tương ứng.
2. Gom các message con thành **một group** do splitter tạo ra.
3. Liên kết log và metric giữa manager, broker và worker.
4. Phát hiện reply đến trễ, message trùng hoặc phản hồi không còn thuộc request đang chờ.

**Quan trọng:** correlation giúp **nhận dạng**, không tự đảm bảo message được xử lý đúng một lần, đúng thứ tự hoặc commit thành công.

## 2. Không có một “ID” giải quyết tất cả bài toán

Các định danh xuất hiện cùng lúc trong một hệ thống batch:

| Định danh | Trả lời câu hỏi | Vòng đời điển hình |
| --- | --- | --- |
| `MessageHeaders.ID` / message ID | Đây là message envelope nào? | Có thể thay đổi khi dựng/gửi lại message |
| **Correlation ID** request–reply | Reply thuộc request hoặc hội thoại nào? | Thường ổn định trong một lượt request–reply logic |
| **Correlation ID** của aggregator | Message thuộc group nào để ghép? | Chung cho các message con của một group |
| `sequenceNumber` | Message ở vị trí nào trong một chuỗi/group? | Theo group, không mặc nhiên là thứ tự commit nghiệp vụ |
| `sequenceSize` | Group dự kiến có bao nhiêu phần tử? | Theo splitter/aggregator nếu biết trước |
| **JobInstance identity** | Lần xử lý logic nào theo JobParameters? | Có thể xuyên qua các lần restart |
| **JobExecutionId** | Lần cố gắng thực thi job nào? | Thay đổi khi restart tạo JobExecution mới |
| **StepExecutionId** | Execution của một step/partition cụ thể? | Thuộc JobExecution, có thể thay ở lần thực thi lại |
| **Logical chunk ID** do ứng dụng định nghĩa | Đơn vị dữ liệu logic nào đang được xử lý? | Cần định nghĩa rõ để xử lý retry/replay |
| **Idempotency key** | Side effect này đã được áp dụng chưa? | Bền vững theo thao tác nghiệp vụ |
| **Trace ID / span ID** | Hoạt động này thuộc trace giám sát nào? | Theo trace/span, không thay thế business identity |
| **Broker key/routing key** | Message được định tuyến vào đâu? | Theo topology và partition/queue |

Các ID có thể được mang trong cùng message nhưng **không cùng ngữ nghĩa**. Ví dụ, dùng `messageId` làm khóa chống ghi trùng có thể thất bại khi broker hoặc ứng dụng tạo lại một message với ID mới cho cùng side effect.

Tương tự, dùng chỉ một `jobExecutionId` làm correlation ID cho **mọi chunk** trong job sẽ không đủ để ghép riêng reply của chunk A với request A: hàng nghìn chunk có cùng giá trị.

### Một nguyên tắc thiết kế

**Một ID phải có một hợp đồng rõ ràng về phạm vi duy nhất, cách tạo, thời gian sống và hành vi khi retry/restart.** Nếu không thể viết ra hợp đồng đó, đừng dùng ID ấy để điều khiển logic quan trọng.

## 3. Correlation header trong Spring Integration

Spring Integration dùng các message header để truyền metadata. Những header thường liên quan đến tương quan và nhóm message là:

- `correlationId`: định danh dùng để liên kết các message thuộc cùng conversation/group trong những component hỗ trợ.
- `sequenceNumber`: số thứ tự của message trong chuỗi do component tạo ra.
- `sequenceSize`: kích thước chuỗi hoặc nhóm kỳ vọng khi biết trước.
- `replyChannel`: kênh nhận reply trong message-driven request–reply ở những mô hình gateway/channel hỗ trợ.
- `errorChannel`: kênh xử lý lỗi trong flow tương ứng.
- `id` và `timestamp`: metadata envelope của Spring Message.

Tên và cách framework tự tạo/copy các header phụ thuộc **component**, **phiên bản** và **message mapper**. Ví dụ, một splitter có thể tạo correlation/sequence cho các message con, còn một messaging gateway có thể tự quản lý correlation để khớp reply. Không được giả định rằng mọi header sẽ đi qua broker dưới cùng tên, cùng kiểu dữ liệu hoặc được chuyển tiếp mặc định.

### Hai tình huống correlation dễ nhầm

**Request–reply correlation:**

~~~text
Request chunk-17 ─────→ worker
Reply chunk-17   ←───── worker

Correlation biểu thị cùng một request/chunk
~~~

**Splitter–aggregator correlation:**

~~~text
Input batch-X → split thành X-1, X-2, X-3
                       \      |      /
                       aggregator group X

Correlation biểu thị cùng một GROUP
~~~

Nếu sử dụng cùng một header cho cả hai ý nghĩa mà không thiết kế group identity riêng, aggregator có thể gom nhầm các reply hoặc gateway mất khả năng ghép chính xác.

**Khuyến nghị:** phân biệt rõ **correlation do framework/protocol sở hữu** với **application correlation** do bạn bổ sung. Khi chưa hiểu component nào đang đọc `correlationId`, ưu tiên đặt header riêng như `batchLogicalCorrelationId` và không tùy tiện ghi đè header dành cho framework.

## 4. Vị trí correlation trong remote chunking

Ở remote chunking, **manager** thường là nơi dùng ItemReader và tạo chunk; các **worker** nhận chunk, chạy ItemProcessor/ItemWriter theo cấu hình rồi gửi phản hồi. Manager vẫn quản lý trạng thái của manager step.

~~~mermaid
flowchart LR
    SRC[("Nguồn")] --> M["Manager Step<br/>read + chunk"]
    M --> OUT["Request outbound adapter"]
    OUT --> Q[["Broker requests"]]
    Q --> WA["Worker A"]
    Q --> WB["Worker B"]
    WA --> DEST[("Đích")]
    WB --> DEST
    WA --> REPLY[["Broker replies"]]
    WB --> REPLY
    REPLY --> IN["Reply inbound adapter"]
    IN --> M
~~~

Mỗi chunk đang được xử lý có thể liên quan đến:

- ID của manager JobExecution và manager StepExecution.
- Định danh/sequence của chunk do giao thức hoặc ứng dụng cung cấp.
- ID của request được gửi qua transport.
- Correlation protocol cần cho gateway/reply matching.
- Application correlation ID dùng cho logging/tracing/đối soát.
- Idempotency key của item hoặc side effect thực tế.

Spring Batch Integration có hợp đồng request/reply cho remote chunking; **đừng tự thay payload hoặc header cốt lõi của framework** mà chưa kiểm tra phiên bản, vì manager còn phải nhận đúng response và cập nhật trạng thái.

### Manager có thể nhận reply đảo thứ tự

Nếu A mất 30 giây và B chỉ mất 2 giây, B sẽ về trước. Đây không phải lỗi. Hệ thống phải khớp reply theo hợp đồng protocol, chứ không lấy **thứ tự nhận** làm định danh.

### Worker không nhất thiết có StepExecution riêng kiểu remote partitioning

Remote chunking và remote partitioning khác nhau. Với **remote partitioning**, worker thực thi worker StepExecution đã được manager phân công; với **remote chunking**, worker xử lý các chunk do manager đọc. Không nên thiết kế correlation trong remote chunking với giả định rằng mọi worker đều có một StepExecution phân vùng tương ứng với từng chunk.

## 5. Vị trí correlation trong remote partitioning

Remote partitioning dùng **StepExecutionRequest** hoặc hợp đồng yêu cầu thực thi partition tương ứng. Manager tạo các StepExecution theo partition, worker truy xuất metadata và chạy worker step.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant R as JobRepository
    participant Q as Broker
    participant W as Worker

    M->>R: Tạo StepExecution cho partition
    M->>Q: Request(partition, stepExecutionId)
    Q->>W: Chuyển yêu cầu
    W->>R: Truy xuất StepExecution/ExecutionContext
    W->>W: Chạy worker step
    W->>R: Lưu status/checkpoint
    W-->>Q: Reply/Execution status
    Q-->>M: Trả kết quả đúng partition
~~~

Ở đây `stepExecutionId` có vai trò mạnh hơn khi tìm worker StepExecution. Nhưng vẫn cần phân biệt:

- `stepExecutionId` là danh tính execution trong JobRepository.
- Correlation request–reply là cách ghép yêu cầu giao tiếp với phản hồi.
- Partition name/ExecutionContext xác định input nghiệp vụ.
- Idempotency key bảo vệ side effect khi phần việc bị chạy lại.

Nếu chỉ dùng partition name `partition-0` làm correlation giữa **hai JobExecution khác nhau**, các response trễ có thể bị nhầm. Cần giới hạn identity theo lần chạy, step hoặc một namespace phù hợp.

## 6. Quy tắc xây correlation ID không bị va chạm

Một application correlation key thực dụng cho **một request chunk trong một lần thực thi** có thể gồm:

~~~text
batch:jobExecution=901:stepExecution=945:chunk=000042
~~~

Ý nghĩa:

- JobExecution 901 xác định lần chạy.
- StepExecution 945 xác định manager step ở lần chạy đó.
- `chunk=000042` phân biệt request trong step.

Đây là **đề xuất đặt tên của ứng dụng**, không phải định dạng chuẩn bắt buộc của Spring Batch hoặc broker.

### Những điều cần tránh

- Chỉ dùng `chunk=42`: dễ trùng giữa job/step.
- Chỉ dùng `stepName=importStep`: cùng step name trong nhiều execution.
- Chỉ dùng `jobExecutionId`: nhiều request trong cùng job.
- Chỉ dùng timestamp millisecond: có thể trùng và không ổn định khi retry.
- Tạo UUID mới mỗi lần retry rồi dùng nó làm idempotency key: mỗi retry trở thành “đơn vị mới”.
- Mang toàn bộ dữ liệu cá nhân, token hoặc payload nhạy cảm vào correlation header.
- Dùng key quá dài làm tăng kích thước message và metric cardinality không cần thiết.

### Cách sử dụng ở nhiều vòng đời

| Tình huống | Hợp đồng ID mong muốn |
| --- | --- |
| Một request được phát đi lần đầu | ID duy nhất trong phạm vi request đang chờ |
| Broker redeliver đúng request | Correlation logic vẫn nhận ra cùng request |
| Manager gửi retry chủ đích | Gắn với cùng phần việc logic nhưng phân biệt attempt nếu cần |
| Job restart thành JobExecution khác | Correlation protocol mới có thể khác; idempotency nghiệp vụ vẫn phải bảo vệ replay |
| Một business event đi qua nhiều chunk/run | Idempotency dựa business key/event ID, không chỉ correlation ID |

**Đặc biệt:** các số thứ tự chunk tự tăng có thể phụ thuộc vào cách manager đọc và tạo chunk. Khi restart, bạn không được mặc định rằng chunk số 42 chứa đúng tập item trước đó. Nếu cần chống lặp xuyên restart, hãy gắn deduplication với **business key và nội dung/tác dụng nghiệp vụ**, hoặc một logical work ID đã được lưu bền vững.

## 7. Header correlation không phải idempotency key

Giả sử manager gửi một chunk, worker ghi DB thành công nhưng reply bị mất. Request có thể được gửi lại theo chính sách. Correlation ID giúp nhận biết đó là **cùng cuộc hội thoại/phần việc**, nhưng không ngăn câu SQL chạy lần hai.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant W as Worker
    participant D as Database

    M->>Q: Request corr=C42
    Q->>W: Request corr=C42
    W->>D: COMMIT dữ liệu
    W--xM: Reply thất lạc
    Q-->>W: Redelivery corr=C42 (tùy cấu hình)
    W->>D: Cần chống lặp side effect
    W-->>M: Reply corr=C42
~~~

Nếu writer làm `UPDATE counter = counter + 1` khi cùng event chạy lại, kết quả có thể tăng hai lần. Để tránh, cần **idempotent writer** hoặc một ledger/unique constraint trên khóa nghiệp vụ nằm trong transaction phù hợp.

### Phân biệt hai câu hỏi

- *“Reply này thuộc request nào?”* → correlation.
- *“Tác dụng nghiệp vụ của request này đã commit chưa?”* → idempotency/transaction/reconciliation.

Giải quyết đúng câu đầu tiên không tự giải quyết câu thứ hai.

## 8. Correlation ID và sequence header không bảo đảm thứ tự commit

Các header `sequenceNumber` và `sequenceSize` thường xuất hiện khi splitter đánh dấu message để aggregator phục hồi nhóm. Tuy nhiên:

1. Sequence number nói về **vị trí logic trong nhóm**, không phải thời gian commit.
2. Hai worker có thể nhận các sequence theo thứ tự rồi hoàn tất đảo thứ tự.
3. Retry làm một sequence xuất hiện lại.
4. Group size có thể không biết trước với luồng streaming hoặc group biến thiên.
5. Aggregate group đầy đủ không chứng minh mọi side effect đã commit theo đúng business order.

Ví dụ:

~~~text
sequenceNumber=1 → worker A: chậm 10 giây
sequenceNumber=2 → worker B: nhanh 1 giây
sequenceNumber=3 → worker C: nhanh 2 giây

Reply/commit: 2, 3, 1
~~~

Nếu nghiệp vụ cần sự kiện version 1 trước version 2, phải thiết kế **key affinity**, sequence guard ở DB hoặc mô hình xử lý tuần tự phù hợp. Header correlation chỉ giúp xác định group, không biến các worker thành một hàng đợi xử lý tuần tự.

## 9. Thiết kế application header riêng để không phá framework

Khi Spring Batch Integration hoặc messaging gateway quản lý request/reply correlation, ứng dụng có thể thêm các header phục vụ audit/tracing mà **không ghi đè header protocol**.

Một bộ header tự định nghĩa:

| Header của ứng dụng | Ý nghĩa |
| --- | --- |
| `batchLogicalCorrelationId` | Liên kết log/metric của một logical chunk request |
| `batchRunKey` | Danh tính business run/cutoff được xác định |
| `batchManagerStepExecutionId` | ID manager StepExecution phục vụ điều tra |
| `batchWorkKey` | ID phần việc logic có ranh giới bền vững nếu ứng dụng có |
| `batchAttempt` | Số lượt gửi lại ở **tầng ứng dụng**, nếu được theo dõi |
| `batchPayloadVersion` | Phiên bản hợp đồng message/payload |

Đây là **tên ứng dụng đề xuất**, không phải header Spring Batch tự cung cấp. Khi dùng thực tế, hai phía phải cùng thống nhất tên, kiểu và quyền sở hữu header.

**Bộ quy tắc:**

- Framework sở hữu header correlation/reply/sequence dùng cho protocol thì không thay đổi tùy tiện.
- Custom header được bảo toàn qua converter/adapter chỉ khi cấu hình mapper hỗ trợ.
- Dữ liệu cần thiết cho tính đúng phải được xác minh từ metadata hoặc payload có hợp đồng, **không tin một header chưa được xác thực**.
- Tên header và cách serialize cần đủ ổn định để manager/worker khác phiên bản đọc được.
- Không đặt các object Java có kiểu tùy biến khó serialize làm giá trị header qua broker nếu không có contract rõ.

## 10. Ví dụ Java: tạo application correlation header

Ví dụ dưới đây dùng **Spring Messaging** để đính kèm header vào một message có sẵn. Nó không thay thế giao thức remote chunking; đây là một lớp metadata có thể được dùng ở ranh giới flow đã được thiết kế.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class BatchCorrelationHeaders {

    public static final String LOGICAL_CORRELATION_ID =
            "batchLogicalCorrelationId";

    public static final String RUN_KEY = "batchRunKey";

    public static final String MANAGER_STEP_EXECUTION_ID =
            "batchManagerStepExecutionId";

    public static final String ATTEMPT = "batchAttempt";

    private BatchCorrelationHeaders() {
    }

    public static <T> Message<T> annotate(
            Message<T> original,
            String correlationId,
            String runKey,
            long managerStepExecutionId,
            int attempt) {

        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException(
                    "correlationId must not be blank");
        }
        if (runKey == null || runKey.isBlank()) {
            throw new IllegalArgumentException(
                    "runKey must not be blank");
        }
        if (attempt < 0) {
            throw new IllegalArgumentException(
                    "attempt must not be negative");
        }

        return MessageBuilder.fromMessage(original)
                .setHeader(LOGICAL_CORRELATION_ID, correlationId)
                .setHeader(RUN_KEY, runKey)
                .setHeader(
                        MANAGER_STEP_EXECUTION_ID,
                        managerStepExecutionId)
                .setHeader(ATTEMPT, attempt)
                .build();
    }
}
~~~

### Điểm cần chú ý

- `MessageBuilder.fromMessage` lấy message có sẵn làm cơ sở, tránh tự bỏ payload và các header hữu ích.
- Ví dụ **không** ghi đè `correlationId` hoặc `replyChannel` của framework.
- Một header `batchAttempt` phân biệt lượt thử về mặt quan sát; **không** tự biến attempt thành khóa duy nhất của side effect.
- Khi gửi qua broker, cần xác nhận converter và header mapper thực sự chuyển các custom header này.
- Nếu cùng một message được tái tạo, `MessageHeaders.ID` có thể khác; đừng dùng nó để so sánh logical chunk.

Ví dụ tạo correlation ID từ một phạm vi **thực sự ổn định trong một StepExecution**:

~~~java
public static String correlationForExecution(
        long jobExecutionId,
        long managerStepExecutionId,
        long logicalChunkSequence) {

    if (jobExecutionId <= 0
            || managerStepExecutionId <= 0
            || logicalChunkSequence < 0) {
        throw new IllegalArgumentException(
                "Invalid execution or sequence");
    }

    return "job-" + jobExecutionId
            + ":step-" + managerStepExecutionId
            + ":chunk-" + logicalChunkSequence;
}
~~~

**Giới hạn:** chỉ dùng `logicalChunkSequence` khi ứng dụng/giao thức đã xác định nó rõ và quản lý tính duy nhất. Không giả định mọi chunk luôn có cùng số sequence sau restart. Nếu chỉ cần logging, có thể dùng một request ID riêng nhưng phải phân biệt rõ với idempotency key.

## 11. Khi nào sử dụng header correlation chuẩn của Spring Integration?

Spring Integration cung cấp hằng số cho các header liên quan đến correlation/sequence thông qua `IntegrationMessageHeaderAccessor` ở các phiên bản tương ứng.

Ví dụ **message của một workflow application-defined**, không đụng vào giao thức remote chunking hiện có:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public static Message<String> groupedMessage(
        String payload,
        String groupId,
        int sequenceNumber,
        int sequenceSize) {

    if (sequenceNumber < 1 || sequenceSize < sequenceNumber) {
        throw new IllegalArgumentException("Invalid sequence");
    }

    return MessageBuilder.withPayload(payload)
            .setHeader(
                IntegrationMessageHeaderAccessor.CORRELATION_ID,
                groupId)
            .setHeader(
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                sequenceNumber)
            .setHeader(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                sequenceSize)
            .build();
}
~~~

Với group ba phần tử, cả ba message có cùng `groupId`, nhưng `sequenceNumber` lần lượt là 1, 2 và 3.

**Không áp dụng máy móc đoạn này lên remote chunking request:** nếu framework/gateway đang sử dụng header correlation của nó để ghép riêng từng chunk, ghi đè bằng một group ID chung có thể làm sai request/reply matching.

### Hướng dẫn chọn

- **Spring Integration splitter/aggregator do bạn thiết kế:** dùng correlation/sequence chuẩn theo hợp đồng component, xác nhận release strategy.
- **Gateway/remote chunking protocol do framework thiết lập:** để component sở hữu header protocol, thêm header riêng cho application correlation nếu cần.
- **Tracing/observability:** dùng trace context chuyên biệt và ứng dụng header ổn định, không tùy tiện biến trace ID thành group key.

## 12. Request–reply gateway và correlation lifecycle

Trong Spring Integration, messaging gateway là một trong các cách biểu diễn request–reply. Một gateway có thể dùng các header như reply channel, error channel hoặc metadata riêng để liên kết request với response.

Khi vượt qua ranh giới **process/broker**:

- Một `replyChannel` trong JVM có thể là đối tượng hoặc kênh tạm **không thể serialize nguyên dạng**.
- Inbound/outbound gateway của broker có thể dùng destination/reply-to và broker correlation property tương ứng.
- Có adapter chuyển đổi header từ Spring Message sang message property của broker.
- Timeout có thể làm caller không còn chờ, dù worker đang hoàn thành.
- Reply đến trễ cần được xử lý thay vì ghép nhầm sang request mới.

**Do đó, không tự copy toàn bộ Spring Message headers sang JSON rồi gửi qua broker.** Hãy sử dụng các adapter/gateway hỗ trợ, định nghĩa contract cho các header được phép qua transport, và kiểm tra behavior của version đang chạy.

### Một quy tắc an toàn

Nếu gateway tự tạo protocol correlation ID, **đừng sửa ID đó** ở middleware tùy biến. Có thể thêm `batchLogicalCorrelationId` để log, và giữ gateway correlation trong lớp transport.

## 13. AMQP/RabbitMQ: correlation ID và reply-to

Trong AMQP, message có thể có các property như **correlation ID** và **reply-to**. Spring Integration AMQP adapter/gateway có cơ chế map message và các property này, với chi tiết phụ thuộc phiên bản và cấu hình.

~~~mermaid
flowchart LR
    M["Manager Gateway"] --> REQ[["AMQP request queue"]]
    REQ --> W["Worker inbound gateway"]
    W --> REP[["AMQP reply queue / reply-to"]]
    REP --> M
~~~

### Những điều cần kiểm tra

1. Manager gửi request qua **đúng exchange/routing key/queue**.
2. Worker đọc request bằng message converter tương thích.
3. Correlation property từ AMQP hoặc header protocol được giữ nhất quán.
4. Worker reply về **đúng destination** mà manager đang chờ.
5. Khi nhiều request cùng outstanding, manager ghép reply theo correlation, không theo FIFO.
6. Nếu worker commit DB rồi mất reply, retry/redelivery được giải quyết bằng idempotency.
7. Nếu dùng một reply queue chung cho nhiều manager instances, không để instance này nhận và làm thất lạc reply của instance khác ngoài cơ chế gateway hỗ trợ.
8. Cấu hình acknowledgement, consumer concurrency, prefetch và timeout không tạo vòng retry vô hạn.

### Đừng nhầm các trường

| Trường/thông tin | Vai trò |
| --- | --- |
| AMQP correlation ID | Hỗ trợ liên kết request–reply ở tầng transport/gateway |
| AMQP reply-to | Cho biết reply cần được gửi tới đâu |
| Spring Integration `correlationId` | Header framework có thể dùng cho conversation/group |
| Application `batchLogicalCorrelationId` | Liên kết audit/trace theo định nghĩa ứng dụng |
| Job/StepExecution IDs | Xác định trạng thái thực thi trong Spring Batch |
| Business idempotency key | Ngăn side effect bị áp dụng lại |

Các giá trị này **không nhất thiết giống nhau**. Một gateway có thể xử lý correlation protocol mà ứng dụng chỉ cần quan sát qua header riêng.

## 14. Kafka: partition key không phải correlation ID

Với Kafka, **message key** thường dùng để xác định partition đích. Các record cùng key có thể được append vào cùng topic partition theo quy tắc producer/partitioner phù hợp, nhưng Kafka không tự tạo quan hệ request–reply chỉ từ key đó.

Một thiết kế request–reply qua Kafka cần làm rõ:

- Topic request và reply.
- Cách mang correlation ID qua Kafka headers hoặc payload theo converter.
- Consumer group, topic partition và worker ownership.
- Cách manager xác định reply thuộc request đang chờ.
- Offset commit, retry, duplicate delivery và message retention.
- Cách dùng key để giữ thứ tự theo aggregate nếu nghiệp vụ cần, **tách** khỏi request–reply correlation.

**Không dùng Kafka key làm idempotency key theo thói quen.** Nếu key chỉ là `customer-42`, nhiều giao dịch hợp lệ của khách hàng đó có cùng key; dedupe theo key sẽ bỏ mất công việc.

### Kafka header value

Kafka record headers thường là cặp tên và **byte array**. Nếu ứng dụng tự map `batchLogicalCorrelationId`, hãy thống nhất encoding, ví dụ UTF-8, và viết integration test để xác nhận header được phục hồi đúng kiểu.

Đừng suy đoán rằng `String` ở Spring Message sẽ trở thành `String` tương đương ở mọi consumer. Header mapper và message converter phải được kiểm chứng bằng round-trip test.

## 15. Splitter, aggregator và hai cấp correlation

Spring Integration có các pattern **Splitter** (tách một message thành nhiều phần) và **Aggregator** (gom lại thành một group). Đây là nơi `correlationId` cùng `sequenceNumber`, `sequenceSize` thường có ý nghĩa rõ.

~~~mermaid
flowchart TB
    IN["Input batch X"] --> SPLIT["Splitter"]
    SPLIT --> X1["X.1: correlation=X, seq=1/3"]
    SPLIT --> X2["X.2: correlation=X, seq=2/3"]
    SPLIT --> X3["X.3: correlation=X, seq=3/3"]
    X1 --> AGG["Aggregator group X"]
    X2 --> AGG
    X3 --> AGG
    AGG --> OUT["Kết quả đã gom"]
~~~

### Sự khác biệt then chốt

Nếu một job có 200 chunk requests cần 200 replies, **mọi reply không nên tự động có cùng correlation ID chỉ vì thuộc cùng job** nếu manager/gateway dựa trên correlation đó để ghép một request cụ thể.

Nếu cố ý tạo **một group gồm 200 replies** để chờ toàn bộ job, có thể dùng một *group ID* chung, nhưng phải bổ sung **request ID từng chunk** riêng. Đây là hai cấp:

~~~text
jobGroupId       = job-901-step-945
chunkRequestId   = job-901-step-945-chunk-000042
~~~

- `jobGroupId` để gộp 200 kết quả nếu thuật toán aggregator yêu cầu.
- `chunkRequestId` để định danh mỗi request/reply.
- `businessIdempotencyKey` cho side effect của từng item/chunk.

Không nhầm khái niệm “tương quan theo nhóm” với “tương quan request–reply”.

### Sequence size có thể không cố định

Với streaming, filter, retry hoặc tập dữ liệu chưa xác định trước, số thành viên group có thể không biết. Một aggregator dựa cứng vào `sequenceSize=200` có thể chờ mãi nếu group thật không có đủ phần tử.

Chọn **release strategy**, timeout, partial results và recovery theo yêu cầu nghiệp vụ, không mặc định mọi splitter group đều có kích thước biết trước.

## 16. Aggregator: correlation đúng nhưng release strategy sai vẫn nguy hiểm

Một aggregator thường cần:

1. **Correlation strategy** xác định message thuộc group nào.
2. **Message store** lưu các message trong group.
3. **Release strategy** quyết định khi nào group đủ điều kiện hoàn thành.
4. **Group timeout/expiry** để xử lý group còn thiếu.
5. **Duplicate handling** khi message cùng phần việc được gửi lại.
6. **Output processing** sau khi group được release.

Nếu correlation ID bị đặt thành chỉ một `jobName`:

~~~text
group = "nightly-import"
~~~

thì **hai JobExecution chạy đồng thời** có thể bị gom chung. Phải có namespace đủ phân biệt:

~~~text
group = "nightly-import:jobExecution=901:managerStep=945"
~~~

Nhưng nếu job restart thành JobExecution khác, nhóm cũ có thể còn tồn tại trong message store; cần chính sách expire/cleanup và phân biệt run mới.

### Message store và restart

Một aggregator chỉ dùng **in-memory message store** có thể mất các message đang chờ khi JVM chết. Nếu business yêu cầu phục hồi group state qua crash, cần một message store bền vững hoặc thiết kế đối soát/đọc lại rõ ràng, cùng transaction semantics phù hợp.

**Gom đủ reply không tự đồng nghĩa writer đúng dữ liệu.** Nếu worker ghi lỗi hoặc có side effect ngoài transaction, cần phản hồi trạng thái và đối soát nghiệp vụ, không chỉ đếm số message.

## 17. Timeout: correlation vẫn đúng nhưng request có thể hết hạn

Giả sử manager gửi `C42` và chờ 20 giây. Worker bị chậm vì DB, sau 30 giây mới trả reply:

~~~text
T+00s  Request C42
T+20s  Manager timeout, không còn caller chờ
T+30s  Reply C42 đến
~~~

Reply vẫn **đúng correlation** nhưng có thể không còn một request active để ghép. Hệ thống phải có chính sách:

- Ghi nhận reply muộn vào log và metric.
- Kiểm tra metadata nếu worker có thể đã commit.
- Không ghép reply C42 sang request C43.
- Không tự động tạo side effect mới chỉ vì reply không đến trước timeout.
- Có cách xử lý trạng thái “đã commit nhưng chưa được xác nhận” an toàn.

### Timeout không phải hủy transaction

Một request timeout ở manager **không đảm bảo** worker đã dừng. Trong hệ thống phân tán, caller ngừng chờ và worker tiếp tục chạy là trạng thái bình thường có thể xảy ra. Nếu gửi lại phần việc mà không kiểm tra worker cũ, có thể xuất hiện **hai worker xử lý cùng logical work**.

Correlation ID giúp phát hiện các thông điệp thuộc cùng phần việc, nhưng logic **ownership, fencing, idempotency và JobRepository status** mới là công cụ xử lý sự cố thực.

## 18. Duplicate reply và duplicate request

Không chỉ request có thể được giao lại; reply cũng có thể bị nhận lại do retry/offset/ack.

### Ví dụ trường hợp

~~~text
Manager outstanding: C42
Worker đã xử lý C42, gửi Reply C42
Manager nhận Reply C42 và đánh dấu xong
Broker hoặc adapter giao lại Reply C42
~~~

Nếu manager coi mỗi reply là một kết quả mới và tăng `completedCount` lần hai, aggregator có thể release sai group. Cần nhận diện reply trùng bằng **request identity + trạng thái đã xử lý**, tùy hợp đồng framework.

### State machine logic

~~~mermaid
flowchart TD
    A["Request C42: SENT"] --> B["WAITING_REPLY"]
    B -->|Reply hợp lệ lần đầu| C["COMPLETED"]
    B -->|Timeout| D["UNKNOWN / RECONCILE"]
    D -->|Metadata xác nhận hoàn thành| C
    D -->|Cần thực thi lại an toàn| E["RETRY_PENDING"]
    E --> B
    C -->|Duplicate reply| F["IGNORE + AUDIT"]
    F --> C
~~~

Đây là mô hình ứng dụng để suy luận, **không phải state machine nội bộ chuẩn của Spring Batch Integration**. Hệ thống thật phải theo giao thức và metadata cụ thể của framework.

Không dùng correlation ID một mình làm bằng chứng rằng request đã thành công; nó chỉ định danh phần việc. Cần kiểm tra response status và kết quả execution.

## 19. Restart: khi JobExecutionId thay đổi

Một điểm dễ bị bỏ qua là **JobInstance** và **JobExecution** không cùng vòng đời.

Ví dụ:

~~~text
JobInstance "daily-close" với businessDate=2026-11-25
    JobExecution 901: FAILED
    JobExecution 907: restart cùng JobInstance
~~~

Nếu correlation ID dùng `jobExecutionId` làm namespace, request cũ thuộc 901 và request mới thuộc 907, giúp tránh nhầm reply giữa hai execution. Nhưng nghiệp vụ của 907 có thể cần **xử lý lại dữ liệu mà 901 đã ghi một phần**.

Vì vậy:

- Correlation protocol có thể mới theo JobExecution.
- Partition/chunk identity cần được xác định theo hợp đồng restart.
- Idempotency key phải bảo vệ side effect nghiệp vụ qua các execution.
- Reader/checkpoint có thể thay đổi nhóm item đi trong một chunk sau rollback/restart.
- Reply từ execution cũ có thể tới muộn sau khi execution mới đã bắt đầu.
- Không tự đổi window/range input của cùng công việc logic khi restart nếu checkpoint còn phụ thuộc nó.

### Tránh “ID đúng nhưng dữ liệu khác”

Nếu correlation dựa `chunkSequence=42` và sau restart chunk 42 chứa **tập item khác**, dùng nó để dedupe sẽ bỏ mất dữ liệu. Định danh chỉ có ý nghĩa nếu cả hai phía thống nhất **nó định danh cái gì**.

**Thực hành tốt:** phục hồi ở cấp metadata/StepExecution của Spring Batch và idempotency theo business key; dùng correlation ID để điều tra và liên kết hội thoại, không dùng làm toàn bộ cơ chế restart.

## 20. Lưu trạng thái chống lặp ở database

Giả sử một chunk chứa nhiều thao tác ghi. Nếu các thao tác cần lặp lại an toàn xuyên job restart, có thể tạo ledger theo **business event ID**, thay vì dedupe theo message ID.

~~~sql
CREATE TABLE applied_business_event (
    event_id      VARCHAR(128) PRIMARY KEY,
    payload_hash  CHAR(64) NOT NULL,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Khi worker xử lý event:

1. Xác định `event_id` duy nhất theo nguồn nghiệp vụ.
2. Kiểm tra hoặc cố ghi `event_id` vào ledger theo transaction an toàn.
3. Nếu event đã có, xác nhận payload hash khớp; nếu khác là conflict.
4. Nếu chưa có, thực hiện update/insert nghiệp vụ trong **cùng transaction** với ledger.
5. Commit cả hai cùng nhau hoặc rollback cả hai.

### Vì sao chỉ `SELECT` rồi `INSERT` là chưa đủ?

Hai worker có thể cùng thấy chưa có event rồi cùng insert. Cần **unique constraint** và cách xử lý xung đột trong transaction, không dựa vào kiểm tra read-before-write không khóa.

### Với API ngoài

Nếu worker gửi payment/email/HTTP, ledger DB nội bộ **không tự atomically commit** với dịch vụ ngoài. Có thể cần idempotency key do API hỗ trợ, transactional outbox, inbox, retry có giới hạn và quy trình đối soát.

Correlation ID của chunk vẫn hữu ích trong log, nhưng side effect cần được bảo vệ ở cấp nghiệp vụ.

## 21. Logging và tracing: correlation phải đi qua nhiều process

Một log chỉ có dòng `worker processed chunk` rất khó điều tra khi có hàng nghìn worker messages. Cần liên kết **manager → broker → worker → reply**.

Một mẫu log dạng key-value:

~~~text
service=batch-manager
jobExecutionId=901
managerStepExecutionId=945
chunkCorrelationId=job-901:step-945:chunk-42
batchLogicalCorrelationId=job-901:step-945:chunk-42
messageDirection=OUTBOUND_REQUEST
worker=unassigned
status=SENT
~~~

Worker khi nhận:

~~~text
service=batch-worker
batchLogicalCorrelationId=job-901:step-945:chunk-42
messageDirection=INBOUND_REQUEST
worker=worker-jvm-3
chunkStatus=PROCESSING
elapsedMs=154
~~~

Manager nhận reply:

~~~text
service=batch-manager
batchLogicalCorrelationId=job-901:step-945:chunk-42
messageDirection=INBOUND_REPLY
worker=worker-jvm-3
status=COMPLETED
elapsedMs=297
~~~

Dữ liệu giả định. Nếu `traceparent`/tracing context được truyền qua messaging, có thể liên kết các span với cùng trace. Nhưng trace/span ID không nên dùng thay cho business key hoặc idempotency key.

### Cardinality và bảo mật

- Correlation ID thường có số giá trị rất lớn. **Không** đưa từng ID làm label của Prometheus histogram/counter.
- Nên dùng correlation ID trong **structured logs hoặc tracing**, với retention và sampling phù hợp.
- Không đưa tài khoản, email, token, password hoặc dữ liệu nhạy cảm dạng thô vào correlation header.
- Giới hạn chiều dài và charset của header, đặc biệt khi đi qua nhiều broker/middleware.
- Mỗi service cần tuân thủ xác thực/ủy quyền cho message; correlation ID **không phải chứng chỉ tin cậy**.

## 22. Metric cần đo khi số chunk/worker tăng

Correlation hữu ích cho quan sát chi tiết, nhưng metric tổng hợp cần tránh cardinality quá cao.

| Metric | Ý nghĩa |
| --- | --- |
| `requests_sent_total` | Số yêu cầu đã phát |
| `replies_received_total` | Số reply nhận được, kể cả duplicate nếu định nghĩa vậy |
| `replies_matched_total` | Reply ghép thành công với request active |
| `orphan_replies_total` | Reply không tìm được request active |
| `duplicate_replies_total` | Reply trùng phần việc đã hoàn tất |
| `request_timeout_total` | Request vượt thời gian chờ |
| `inflight_requests` | Số request chưa có kết quả xác định |
| `request_to_reply_latency` | Thời gian từ gửi tới reply |
| `broker_queue_age` | Thời gian message nằm chờ |
| `worker_processing_latency` | Thời gian xử lý worker |
| `business_dedupe_total` | Số side effect bị ngăn lặp bằng idempotency |
| `reconciliation_failures_total` | Số lần đối soát sai dữ liệu |

**Phải định nghĩa cách tính.** `replies_received_total` có thể lớn hơn `requests_sent_total` do reply trùng hoặc phạm vi cửa sổ đo; không được suy diễn là job có nhiều phần việc hơn. Kết quả cuối vẫn cần xem `readCount`, `writeCount`, rollback/skip, DB metrics và độ đúng dữ liệu.

### Công thức capacity đơn giản

Nếu manager phát 5.000 requests/s nhưng worker chỉ hoàn thành 4.000 requests/s, backlog có thể tăng khoảng 1.000 requests/s trong một hệ thống có queue trung gian và tốc độ ổn định. Tăng correlation fields không làm hệ thống xử lý nhanh hơn; nó giúp **nhìn thấy** phần việc đang nằm ở đâu.

Khi số inflight tăng, cần giới hạn concurrency, broker capacity, connection pool và timeout; đừng tạo vô hạn request chỉ vì manager đọc nhanh.

## 23. Lỗi header mapper: correlation biến mất qua broker

Một trong những lỗi thực tế khó phát hiện là header tồn tại trong message nội bộ của manager, nhưng sau khi chuyển qua broker thì worker không còn thấy.

Ví dụ:

~~~text
Manager Spring Message:
    batchLogicalCorrelationId = C42

Outbound mapper:
    chỉ copy một số header được cho phép

Broker message:
    không có batchLogicalCorrelationId

Worker:
    correlation missing
~~~

Nguyên nhân có thể gồm:

- Header mapper không cho phép custom header.
- Message converter không hỗ trợ kiểu dữ liệu của giá trị.
- Cấu hình producer/consumer dùng tên header khác nhau.
- Gateway thay/loại bỏ một số header protocol cho request–reply.
- Payload transform tạo message mới nhưng không copy metadata cần thiết.
- Adapter qua nhiều giao thức làm đổi encoding từ String sang bytes.
- Tên header bị chuẩn hóa theo quy tắc của broker/mapper.
- Một message retry được tạo mới nhưng code quên đính lại application headers.

### Hướng khắc phục

1. Định nghĩa **header contract** theo từng transport.
2. Dùng kiểu giá trị đơn giản và encoding được hỗ trợ.
3. Kiểm tra chiều outbound→broker→inbound bằng integration test.
4. Tránh chuyển nguyên các header **nội bộ không serialize được** qua wire.
5. Log sự thiếu header tại boundary, không âm thầm tự tạo một correlation ID mới rồi coi request cũ như request mới.
6. Tách logic correlation mà framework tạo khỏi custom correlation phục vụ audit.

## 24. Ví dụ Java: ghép reply bằng application correlation trong test

Đoạn mã sau minh họa một **reply do ứng dụng tự xây**, không can thiệp response nội bộ của Spring Batch Integration. Nó cho thấy cách giữ application correlation khi tạo reply message.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class ReplyFactory {

    public static Message<String> reply(
            Message<?> request,
            String result) {

        Object correlationId = request.getHeaders().get(
                BatchCorrelationHeaders.LOGICAL_CORRELATION_ID);

        if (!(correlationId instanceof String id)
                || id.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing application correlation header");
        }

        return MessageBuilder.withPayload(result)
                .setHeader(
                    BatchCorrelationHeaders.LOGICAL_CORRELATION_ID,
                    id)
                .build();
    }
}
~~~

**Không làm điều này thay cho framework remote chunking reply handler.** Nếu framework đang xử lý request/reply, hãy giữ nguyên hợp đồng response và chỉ thêm instrumentation/headers bằng cơ chế được hỗ trợ. Mã trên là ví dụ application-level request–reply để hiểu cách sử dụng header.

### Test với hai reply đảo thứ tự

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class ReplyFactoryTest {

    @Test
    void repliesPreserveTheirOwnCorrelation() {
        Message<String> requestA =
                MessageBuilder.withPayload("chunk-A")
                        .setHeader(
                            BatchCorrelationHeaders.LOGICAL_CORRELATION_ID,
                            "request-A")
                        .build();

        Message<String> requestB =
                MessageBuilder.withPayload("chunk-B")
                        .setHeader(
                            BatchCorrelationHeaders.LOGICAL_CORRELATION_ID,
                            "request-B")
                        .build();

        Message<String> replyB = ReplyFactory.reply(
                requestB, "result-B");
        Message<String> replyA = ReplyFactory.reply(
                requestA, "result-A");

        // Reply B đến trước Reply A vẫn nhận dạng đúng.
        assertEquals(
                "request-B",
                replyB.getHeaders().get(
                    BatchCorrelationHeaders.LOGICAL_CORRELATION_ID));
        assertEquals(
                "request-A",
                replyA.getHeaders().get(
                    BatchCorrelationHeaders.LOGICAL_CORRELATION_ID));
    }
}
~~~

Test JUnit 5 này kiểm tra **tính bảo toàn application header trong bộ nhớ**. Nó **không** kiểm tra broker, gateway protocol hoặc transaction side effect. Cần integration test thực mới chứng minh message converter và adapter hoạt động đúng.

## 25. Kiểm thử request/reply qua middleware thật

Một kế hoạch kiểm thử có giá trị nên có các nhóm sau:

### 25.1. Round-trip header mapping

- Manager gửi request có application header C42.
- Kiểm tra broker lưu property/header mong đợi.
- Worker nhận request và đọc lại C42 đúng kiểu/encoding.
- Worker trả reply và manager đọc lại correlation theo contract.
- Kiểm tra `replyChannel`/broker reply destination do gateway sử dụng không bị ghi đè sai.

### 25.2. Concurrency và reply đảo thứ tự

- Gửi ít nhất 100 request có correlation khác nhau.
- Dùng hai hoặc nhiều worker tạo delay ngẫu nhiên.
- Kiểm tra mỗi response ghép đúng request.
- Không group reply theo `jobName` hoặc `stepName` đơn lẻ.
- Không suy ra thứ tự commit từ reply arrival.

### 25.3. Lỗi và redelivery

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Worker chết trước commit | Work chưa commit được chạy lại an toàn |
| Worker chết sau commit trước reply | Correlation vẫn đúng và side effect không nhân đôi |
| Reply B đến trước A | B ghép B, A ghép A |
| Duplicate reply A | Không đánh dấu thêm một work item đã hoàn thành |
| Request timeout | Không gắn reply đến trễ sang request khác |
| Retry tạo message mới | Application correlation và business dedupe vẫn được xác định |
| Job restart | Request cũ không làm sai execution mới; output idempotent |
| Header custom bị lọc | Phát hiện thiếu header, không im lặng coi như hợp lệ |
| Manager/worker khác phiên bản | Converter và protocol vẫn tương thích hoặc fail rõ |
| Broker queue backlog tăng | Có giới hạn inflight và metric phù hợp |

### 25.4. Đối soát nghiệp vụ

Không chỉ kiểm tra số reply. Với cùng dataset và business cutoff:

1. So sánh số business key hợp lệ ở nguồn với đích.
2. Kiểm tra duplicate/thiếu record.
3. Kiểm tra checksum hoặc giá trị đầu ra theo business key.
4. Tạo retry/crash rồi so kết quả với lần chạy không lỗi.
5. Kiểm tra StepExecution/JobExecution metadata và các trạng thái kết thúc phù hợp.
6. Kiểm tra side effect ngoài transaction (HTTP/API) bằng idempotency hoặc ledger.

## 26. Tình huống thực tế: 20 triệu giao dịch, 16 worker

Một doanh nghiệp chạy job chuẩn hóa **20.000.000 giao dịch** mỗi đêm. Manager đọc dữ liệu nguồn và gửi chunk 500 item cho các worker JVM; processor gọi dịch vụ quy tắc và writer upsert vào DB đích.

Số chunk lý tưởng khi không filter/skip và mỗi chunk đủ 500 item:

\[
N_{\mathrm{chunks}}=
\frac{20.000.000}{500}=40.000
\]

Giả sử manager có thể có hàng trăm request đang inflight. Cần ghép **40.000 lượt kết quả logic** với đúng request, dù worker hoàn thành đảo thứ tự.

### Thiết kế định danh

Giả sử manager đang ở:

~~~text
jobExecutionId=901
managerStepExecutionId=945
businessRunKey=2026-11-25-normalization
~~~

Một request minh họa:

~~~json
{
  "applicationHeaders": {
    "batchLogicalCorrelationId":
      "job-901:step-945:chunk-42",
    "batchRunKey":
      "2026-11-25-normalization",
    "batchManagerStepExecutionId": 945,
    "batchAttempt": 0
  },
  "description": "Ví dụ minh họa, không phải protocol wire của Spring Batch"
}
~~~

Manager/gateway vẫn sử dụng correlation và payload **theo giao thức Spring Batch Integration thực tế**; các custom header trên phục vụ log/audit nếu adapter cho phép.

### Một sự cố mô phỏng

1. Worker 5 xử lý chunk 42 và commit thành công.
2. Reply 42 thất lạc vì broker disconnect.
3. Worker 8 hoàn thành chunk 43 trước; reply 43 tới manager.
4. Manager không được coi reply 43 là reply 42.
5. Sau timeout, chunk 42 được kiểm tra metadata và retry/redelivery nếu chính sách yêu cầu.
6. Writer dùng business transaction ID và unique/upsert đúng ngữ nghĩa để không ghi trùng.
7. Application correlation C42 nối log của các lượt thử; attempt cho biết vòng gửi lại, không phải khóa của giao dịch nghiệp vụ.

### Benchmark giả định

| Worker | Throughput output | p95 request–reply latency | Orphan/late replies | Nhận xét |
| ---: | ---: | ---: | ---: | --- |
| 1 | 3.000 item/s | 300 ms | Thấp | Baseline |
| 4 | 9.000 item/s | 430 ms | Thấp | Có ích |
| 8 | 13.500 item/s | 650 ms | Trung bình | Gần trần DB |
| 16 | 14.100 item/s | 1.600 ms | Cao | Contention/queue tăng |
| 24 | 13.800 item/s | 2.400 ms | Cao | Thêm worker phản tác dụng |

Tất cả số liệu trong bảng là **giả định**. Orphan/late reply có thể phản ánh timeout quá ngắn, network/broker, slow worker hoặc cấu hình gateway; không thể kết luận nguyên nhân chỉ từ một cột metric.

Ở 16 worker, latency tăng trong khi throughput chỉ cải thiện nhẹ so với 8 worker. Correlation/trace giúp phân biệt việc chờ broker với chờ worker/DB, nhưng **không tự tăng throughput**.

### Quyết định kiến trúc

Nếu processor là nút thắt và DB còn dư, thêm worker có thể phù hợp. Nếu manager reader hoặc DB đích đã đạt trần, cần tối ưu nguồn/đích hoặc xem lại kiến trúc. Với business data có thể chia thành các partition độc lập, remote partitioning có thể giảm nhu cầu manager gửi tất cả item qua broker.

**Điểm quan trọng:** không chọn số worker dựa trên số reply/s nếu kết quả nghiệp vụ có duplicate hoặc sai sau restart.

## 27. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “correlationId chính là messageId.” | Message ID xác định envelope; correlation liên kết conversation/group. |
| “Mọi chunk trong cùng job có thể dùng cùng correlationId.” | Nếu protocol cần request–reply riêng, dùng cùng ID có thể gây nhầm reply; group ID là mục đích khác. |
| “JobExecutionId là khóa chống lặp nghiệp vụ.” | Restart có JobExecution mới; dedupe nên dựa business event/work identity thích hợp. |
| “sequenceNumber quyết định thứ tự DB commit.” | Không. Nó chủ yếu biểu diễn vị trí logic; worker có thể hoàn tất đảo thứ tự. |
| “Kafka key là correlationId.” | Key định tuyến partition; không tự liên kết request/reply. |
| “RabbitMQ reply-to và correlation ID là một.” | Reply-to định tuyến reply; correlation ID nhận dạng hội thoại. |
| “Gateway luôn gửi mọi header qua broker.” | Header mapper/converter có thể loại hoặc chuyển đổi kiểu header. |
| “Có correlation đúng thì không thể ghi trùng.” | Correlation không thay idempotency/transaction. |
| “Có đủ số reply thì mọi side effect đúng.” | Cần kiểm tra status và đối soát dữ liệu nghiệp vụ. |
| “Reply đến trễ có thể khớp request mới nhất.” | Phải ghép theo ID/protocol, không theo thời gian đến. |
| “Timeout ở manager đã dừng worker.” | Worker có thể còn chạy hoặc đã commit. |
| “Trace ID có thể dùng làm khóa nghiệp vụ.” | Tracing có vòng đời khác business identity. |
| “Cứ copy toàn bộ Spring headers lên wire là được.” | Có header nội bộ không serializable hoặc do gateway quản lý. |
| “Aggregation group ID nên giống request ID của từng chunk.” | Hai mức tương quan có phạm vi khác nhau. |
| “Log từng correlationId thành metric label sẽ hữu ích.” | Cardinality rất lớn; nên ghi chi tiết vào logs/traces. |

## 28. Checklist thiết kế correlation header

- [ ] Đã xác định rõ đây là correlation cho **request–reply** hay **aggregator group**.
- [ ] Biết thành phần nào sở hữu `correlationId`, `replyChannel`, `sequenceNumber`, `sequenceSize`.
- [ ] Không tự ghi đè protocol header do Spring Batch Integration/gateway quản lý.
- [ ] Application correlation ID có namespace đủ duy nhất theo run/step/chunk cần thiết.
- [ ] Không dùng timestamp hay một JobExecutionId duy nhất làm ID cho mọi request.
- [ ] Có business idempotency key tách biệt để xử lý retry/restart.
- [ ] Header value đơn giản, bounded, không chứa dữ liệu nhạy cảm.
- [ ] Đã kiểm tra header mapper qua transport bằng integration test.
- [ ] Correlation ID được giữ/có thể truy xuất ở manager, worker và reply boundary.
- [ ] Reply đến đảo thứ tự vẫn khớp đúng request.
- [ ] Duplicate/late/orphan reply có policy và metric rõ.
- [ ] Timeout không được suy luận là worker chắc chắn dừng.
- [ ] Restart không ghép message cũ sang execution mới.
- [ ] Nếu dùng aggregator, group key đủ phân biệt các execution và group state có TTL/recovery.
- [ ] Có giới hạn inflight requests, timeout/retry và backpressure.
- [ ] Có structured log với correlation, StepExecution, worker và attempt.
- [ ] Không đưa correlationId động thành high-cardinality metric label.
- [ ] Đã thử worker crash sau commit, reply mất, redelivery, duplicate và broker reconnect.
- [ ] Có đối soát business key/side effect sau lỗi.
- [ ] Chỉ tăng worker khi throughput cùng correctness và khả năng vận hành được xác minh.

## 29. Câu hỏi tự kiểm tra

**1. Vì sao `correlationId` và `MessageHeaders.ID` không nên coi là một?**

Vì message ID thường là danh tính envelope; một request có thể được dựng/gửi lại với envelope khác. Correlation định nghĩa quan hệ giữa request, reply hoặc group và cần hợp đồng ổn định theo mục đích đó.

**2. Nếu manager gửi chunk A rồi B nhưng reply B về trước, điều gì phải xảy ra?**

Reply B phải được ghép đúng request B; A vẫn còn outstanding cho đến khi có kết quả hoặc timeout/reconciliation. Không gán reply dựa trên thứ tự nhận.

**3. Một job có 10.000 chunk, có nên dùng cùng `jobExecutionId` làm correlation ID của mọi chunk không?**

Không nếu cần phân biệt request/reply từng chunk. `jobExecutionId` có thể là một phần namespace, nhưng cần thêm step/chunk request identity riêng.

**4. `sequenceNumber` và `sequenceSize` có ý nghĩa gì?**

Chúng có thể mô tả vị trí và kích thước một group để splitter/aggregator quản lý. Chúng không tự bảo đảm worker commit theo thứ tự.

**5. Vì sao Kafka key không thay thế correlation header?**

Kafka key thường phục vụ định tuyến/partitioning. Request–reply cần một ID để ghép response với request, cùng reply topic/protocol phù hợp.

**6. Sau khi worker commit thành công nhưng reply mất, chỉ có correlation ID có chống ghi trùng được không?**

Không. Cần idempotent writer, unique constraint/ledger hoặc idempotency ở API và kiểm tra trạng thái execution.

**7. Vì sao application header có thể biến mất giữa manager và worker?**

Header mapper/converter có thể lọc header, đổi kiểu hoặc không serialize header đó; cần round-trip test với broker thật.

**8. Nếu gateway tự quản lý `correlationId`, ứng dụng muốn có ID để trace log nên làm gì?**

Dùng một custom header riêng như `batchLogicalCorrelationId` và xác nhận adapter truyền nó. Không ghi đè protocol correlation mà chưa hiểu giao thức.

**9. Khi job restart thành JobExecution mới, có thể dùng correlation cũ làm idempotency key không?**

Không mặc định. Cùng dữ liệu có thể được xử lý lại trong execution khác; idempotency phải dựa trên business operation identity đủ ổn định và được lưu bền vững.

**10. Aggregator đã nhận đủ số reply có bảo đảm dữ liệu đúng không?**

Không. Còn cần kiểm tra response status, transaction, retry/skip, business key và side effect ngoài DB.

**11. Vì sao không đưa mỗi correlation ID làm label metric?**

Vì số giá trị có thể bằng số message/chunk, tạo high cardinality rất lớn. Nên dùng logs/traces cho ID chi tiết, metric tổng hợp cho latency/counters.

**12. Trong remote partitioning, `StepExecutionId` có vai trò gì khác remote chunking?**

Worker remote partitioning thường truy xuất và thực thi một StepExecution được manager tạo sẵn; remote chunking thường truyền các chunk mà manager đã đọc. Vì vậy không nên giả định mỗi chunk có một worker StepExecution riêng kiểu partition.

---

**Ghi nhớ:** **Correlation header là cơ chế liên kết message**, không phải cơ chế đảm bảo exactly-once hoặc thứ tự xử lý. Trong Spring Batch Integration, phải phân biệt correlation của gateway/request–reply với group của splitter/aggregator; phân biệt chúng với JobExecution, StepExecution, message ID, trace ID và idempotency key. Thiết kế tốt giữ protocol header đúng chủ sở hữu, truyền application header nhất quán qua middleware, xử lý reply đảo thứ tự/đến trễ và bảo vệ dữ liệu bằng transaction, checkpoint, idempotency và đối soát sau restart. Mục tiêu là **scale worker mà không ghép nhầm phần việc và không làm sai dữ liệu**.
