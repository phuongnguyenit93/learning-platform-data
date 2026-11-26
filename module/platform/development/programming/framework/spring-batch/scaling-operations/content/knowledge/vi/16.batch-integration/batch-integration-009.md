# Retry message delivery trong Spring Batch Integration

## Mục tiêu bài học

Khi Spring Batch chạy **remote chunking** hoặc **remote partitioning** qua Spring Integration, manager và worker trao đổi thông điệp qua middleware. Mạng có thể ngắt, broker có thể khởi động lại, worker có thể chết giữa giao dịch, reply có thể đến trễ và một message có thể được giao cho consumer nhiều lần. Không thể thiết kế scaling an toàn nếu chỉ xét đường đi thành công của một message.

**Retry message delivery** là cơ chế thử lại việc **đưa thông điệp đến đúng nơi và xử lý những trường hợp giao nhận thất bại**. Nó khác với **retry nghiệp vụ trong một chunk** và cũng khác với **restart một JobExecution**. Nếu trộn các tầng retry mà không xác định rõ ranh giới commit, hệ thống có thể xử lý cùng dữ liệu nhiều lần, tạo retry storm hoặc tuyên bố job hoàn thành dù một số phần việc chưa có kết quả chắc chắn.

Bài thuộc chương **Spring Batch Integration** của module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu là mở rộng Spring Batch với multi-threaded step, parallel steps, partitioning và xử lý phân tán, đồng thời đo bottleneck, bảo đảm thread safety, retry/restart và lựa chọn kiến trúc theo tài nguyên thực tế.

Sau khi học, bạn có thể:

- Phân biệt **publish retry**, **consumer retry**, **broker redelivery**, **request timeout** và **Spring Batch retry/restart**.
- Hiểu vì sao delivery thường phải được thiết kế để chịu **at-least-once** thay vì mặc định exactly-once.
- Xác định điểm an toàn để ACK/reject một message khi worker có giao dịch dữ liệu.
- Áp dụng backoff, giới hạn số lần retry, phân loại lỗi và dead-letter queue (DLQ).
- Giải thích khác biệt cơ bản giữa RabbitMQ/AMQP và Kafka trong xử lý giao lại.
- Sử dụng Spring Integration retry advice/error handling có chủ đích và không retry sai ranh giới bất đồng bộ.
- Thiết kế writer idempotent, correlation ID và cách đối soát khi worker đã commit nhưng reply bị mất.
- Thử kill worker, mất kết nối, duplicate delivery, poison message và restart để kiểm chứng tính đúng.

## 1. Bối cảnh: message trong một hệ thống batch phân tán

Trong **remote chunking**, manager thường đọc item, tạo chunk và gửi phần việc qua middleware đến worker để process/write; worker trả kết quả theo giao thức Spring Batch Integration.

~~~mermaid
flowchart LR
    SRC[("Nguồn")] --> M["Manager JVM<br/>read + tạo chunk"]
    M --> OUT["Outbound messaging"]
    OUT --> Q[["Request broker"]]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    W1 --> D[("Dữ liệu đích")]
    W2 --> D
    W1 --> REP[["Reply broker"]]
    W2 --> REP
    REP --> IN["Reply inbound"]
    IN --> M
~~~

Trong **remote partitioning**, manager tạo các worker StepExecution cùng ExecutionContext, gửi yêu cầu thực thi phần việc; worker tự đọc phần dữ liệu được phân công và cập nhật metadata qua cơ chế Spring Batch.

~~~mermaid
flowchart TB
    M["Manager<br/>Partitioner + handler"] --> Q[["Request channel"]]
    Q --> A["Worker A: StepExecution A"]
    Q --> B["Worker B: StepExecution B"]
    A --> J[("JobRepository")]
    B --> J
    M --> J
    A --> DB[("Nguồn / đích")]
    B --> DB
~~~

Hai mô hình đều phải xử lý mất message, retry và worker crash, nhưng **đơn vị phần việc khác nhau**:

| Tiêu chí | Remote chunking | Remote partitioning |
| --- | --- | --- |
| Request đại diện | Chunk item do manager đọc | Yêu cầu chạy một worker StepExecution |
| Worker tự đọc dữ liệu nguồn | Thông thường không | Có, theo ExecutionContext |
| Trạng thái liên quan | Manager step và giao thức chunk request/reply | Worker StepExecution, ExecutionContext và JobRepository |
| Khi request lặp | Có thể lặp xử lý/ghi chunk | Có nguy cơ hai worker cố thực thi cùng phần việc |
| Bảo vệ quan trọng | Idempotency dữ liệu, chunk status và correlation | Metadata/ownership StepExecution, input ổn định, writer idempotent |
| Retry transport | Theo broker/adapter/handler | Theo broker/adapter/handler |

Không thể dùng một cơ chế ACK của broker thay cho mọi loại trạng thái trong Spring Batch. Cần xác định tầng nào đang quản lý **work completion** và tầng nào chỉ quản lý **message transfer**.

## 2. Retry là từ chung cho nhiều hành vi khác nhau

Một request có thể được “thử lại” ở nhiều tầng.

| Tầng | Điều được thử lại | Ví dụ | Rủi ro |
| --- | --- | --- | --- |
| **Producer publish** | Gửi message từ manager đến broker | Kết nối bị mất trước khi có publish confirm | Broker có thể đã nhận message dù producer tưởng thất bại |
| **Broker redelivery** | Giao lại message chưa ACK/offset chưa commit | Worker crash sau khi nhận | Một request có thể được xử lý hai lần |
| **Consumer/handler retry** | Gọi lại logic xử lý khi handler throw exception | DB timeout lúc worker thực thi | Có thể lặp side effect đã xảy ra trước lỗi |
| **Spring Batch item retry** | Gọi lại reader/processor/writer theo chính sách fault tolerant | Một item gây lỗi tạm thời | Chunk có thể rollback và xử lý lại |
| **Request–reply timeout/retry** | Manager chưa thấy phản hồi nên kiểm tra hoặc gửi lại | Reply bị mất sau worker commit | Work thực có thể xong nhưng không được xác nhận |
| **Job restart** | Phục hồi job/step bị thất bại | Chạy lại cùng JobInstance | Input và checkpoint phải ổn định |

Các tầng có thể **lồng nhau**. Nếu producer retry ba lần, broker redeliver hai lần, handler retry bốn lần, số lượt gọi logic nghiệp vụ có thể vượt xa mong đợi. Không lấy tích các giới hạn làm số chắc chắn, nhưng phải phân tích **worst-case amplification** để tránh lũ request khi hệ thống đang lỗi.

**Câu hỏi quan trọng:** retry này lặp lại **lệnh gửi**, **toàn message**, **giao dịch chunk**, hay **phần việc logic sau restart**?

## 3. Delivery semantics: at-most-once, at-least-once và exactly-once

Có ba khái niệm thường dùng:

**At-most-once delivery**: cố gắng không giao message lặp lại, nhưng có thể mất message khi lỗi. Ví dụ ACK sớm trước khi xử lý rồi worker chết.

**At-least-once delivery**: message được giao lại khi chưa xác nhận thành công; tăng khả năng hoàn thành nhưng có thể phát sinh duplicate. Consumer phải xử lý được việc nhận lại.

**Exactly-once effect**: side effect nghiệp vụ được áp dụng đúng một lần theo định nghĩa. Đây **không tự xuất hiện** chỉ vì broker hoặc SDK có một tính năng mang tên “exactly once”.

Giả sử message được worker nhận một lần, nhưng worker commit DB rồi reply bị mất. Manager không biết chắc kết quả, nên việc giao lại có thể xảy ra. Khi ấy *delivery* có thể lặp nhưng *business effect* vẫn cần lặp lại an toàn.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant W as Worker
    participant D as Database
    participant M as Manager

    M->>B: Chunk request R42
    B->>W: Giao R42
    W->>D: COMMIT chunk R42
    D-->>W: Thành công
    W--xM: Reply bị mất
    B-->>W: Có thể redeliver R42 theo ack policy
    W->>D: Kiểm tra và ghi lặp an toàn
~~~

**Định hướng thực dụng:** thiết kế phần việc sao cho **có thể nhận/giao lại** và side effect không sai, sau đó cấu hình giao nhận có xác nhận, backoff và theo dõi phù hợp. Đừng cam kết exactly-once qua DB, broker và HTTP khi chưa có giao dịch hoặc chiến lược idempotency trên toàn hệ thống.

## 4. Các cửa sổ lỗi phải được phân tích riêng

Một request đi qua nhiều điểm có thể thất bại:

~~~text
T0  Manager tạo request
T1  Producer gửi tới broker
T2  Broker nhận và lưu theo cấu hình
T3  Worker nhận message
T4  Worker bắt đầu transaction
T5  Worker commit dữ liệu nghiệp vụ
T6  Worker phát reply
T7  Manager nhận reply và đối chiếu trạng thái
~~~

| Vị trí lỗi | Trạng thái có thể xảy ra | Hành động cần cân nhắc |
| --- | --- | --- |
| Trước T1 | Chưa chắc đã gửi | Retry publish có giới hạn |
| T1–T2 | Producer không biết broker có nhận chưa | Dùng confirm, message identity, chịu duplicate |
| T2–T3 | Broker có request nhưng consumer chưa lấy | Quan sát backlog/retention; giao theo broker |
| T3–T4 | Message đã tới worker, chưa xử lý | Nếu chưa ACK, broker có thể redeliver |
| T4–T5 | Transaction chưa commit | Rollback; retry theo loại lỗi và context |
| Sau T5 trước T6 | Business DB đã commit nhưng chưa reply | Idempotency và đối chiếu kết quả |
| T6–T7 | Reply có thể tới trễ hoặc mất | Correlation, timeout, reconciliation |
| Sau T7 | Reply trùng/đến thêm | Không cộng kết quả hoàn thành hai lần |

**Không thể suy ra dữ liệu chưa commit chỉ từ việc manager chưa nhận reply.** Đây là nguyên nhân phổ biến của duplicate write và cần được đưa thành tình huống thử nghiệm bắt buộc.

## 5. Broker ACK khác với transaction commit

ACK là sự xác nhận ở **tầng transport/consumer**; commit của writer là sự xác nhận ở **tầng dữ liệu nghiệp vụ**. Hai thao tác không mặc nhiên là một transaction nguyên tử.

### ACK quá sớm

~~~text
Worker nhận R42
  → ACK broker
  → bắt đầu ghi DB
  → JVM chết trước commit
~~~

Broker có thể coi request đã hoàn tất và **không redeliver** theo cơ chế ACK thông thường, dù DB chưa ghi dữ liệu.

### ACK sau khi xử lý

~~~text
Worker nhận R42
  → xử lý chunk / commit DB
  → ACK broker
~~~

Nếu JVM chết **sau commit, trước ACK**, broker có thể giao lại R42. Đây là cửa sổ duplicate thường phải chấp nhận để không mất work.

**Lưu ý:** một inbound adapter, gateway hoặc listener container cụ thể có thể tự điều khiển ACK khi handler return hoặc dựa vào transaction/ack mode. Không được giả định ACK xảy ra ở thời điểm nào chỉ từ tên Spring Integration channel. Phải đọc và kiểm thử cấu hình thực tế của adapter/consumer.

### Bốn câu hỏi cần trả lời

1. ACK được gửi lúc **nhận**, **handler return**, **DB commit** hay ở một callback khác?
2. Nếu handler throw exception, container sẽ retry tại chỗ, reject, requeue hay chuyển DLQ?
3. Nếu worker process thành công nhưng **publish reply thất bại**, ACK của request ra sao?
4. Nếu message bị redeliver, worker sẽ xác định trạng thái nghiệp vụ đã commit bằng cách nào?

Khi không thể có transaction chung giữa broker và business DB, **idempotency** hoặc một inbox/outbox bền vững thường đóng vai trò bảo vệ cuối cùng.

## 6. RabbitMQ/AMQP: ACK, requeue và dead-letter

Với RabbitMQ, các khái niệm thường gặp là **consumer acknowledgement**, **publisher confirm**, **basic.reject/basic.nack**, **requeue** và **dead-letter exchange (DLX)**. Chúng không thay thế nhau.

- **Publisher confirm** hỗ trợ producer biết broker đã xác nhận publish theo cấu hình. Nó không chứng minh worker đã xử lý hay DB đã commit.
- **Consumer ACK** cho broker biết message đã được xử lý ở mức mà listener/container coi là thành công.
- **Reject/NACK + requeue** có thể khiến request được giao lại.
- **Reject/NACK không requeue** có thể đưa request sang DLX nếu queue được cấu hình dead-letter phù hợp; nếu không, message có thể bị loại bỏ.
- **TTL + dead-letter routing** có thể tạo delayed retry queue, nhưng phải có giới hạn số lần và chống vòng lặp vô hạn.

~~~mermaid
flowchart TD
    Q[["Request queue"]] --> W["Worker consumer"]
    W --> O{"Kết quả xử lý"}
    O -->|Thành công| ACK["ACK theo adapter policy"]
    O -->|Lỗi tạm thời| RETRY[["Retry / delay queue"]]
    O -->|Lỗi không phục hồi| DLQ[["Dead-letter queue"]]
    RETRY --> Q
~~~

### Requeue tức thì có thể tạo vòng lặp nóng

Nếu DB đang không truy cập được, worker nhận message rồi lập tức NACK requeue. Broker có thể giao lại gần như ngay lập tức, khiến consumer chiếm CPU, flood log và làm DB càng quá tải.

**Biện pháp:** bounded retry, backoff/delay, circuit breaker hoặc pause consumer ở mức phù hợp. Nếu cần giữ thứ tự theo key, việc đưa một message lỗi sang queue trễ còn có thể khiến message sau vượt lên; phải thiết kế ordering riêng.

### Cần kiểm tra theo adapter cụ thể

Trong Spring Integration AMQP, hành vi có thể khác giữa inbound channel adapter, inbound gateway và cấu hình listener container. Một số adapter hỗ trợ error channel, listener retry hoặc ACK mode tùy chọn; **không lấy ví dụ của adapter này làm bảo đảm cho adapter khác**.

## 7. Kafka: offset commit, retry topic và ordering

Trong Kafka, consumer đọc record từ topic partition và **commit offset** để thể hiện vị trí tiêu thụ. Offset commit không mặc nhiên nằm trong cùng transaction với DB writer của Spring Batch.

Tình huống:

~~~text
Consumer đọc offset=150
Worker commit dữ liệu
JVM chết trước khi offset=151 được commit
Consumer mới đọc lại offset=150
~~~

Record có thể được xử lý lại. Nếu commit offset quá sớm rồi worker chết trước khi ghi, record có nguy cơ bị bỏ qua ở lần tiêu thụ tiếp theo theo vị trí đã commit.

### Hai cách xử lý lỗi thường gặp

**Seek/retry trong partition:** tạm giữ việc xử lý record lỗi và retry theo chính sách, giúp duy trì một số dạng thứ tự nhưng có thể gây head-of-line blocking.

**Retry topic:** chuyển record lỗi sang topic xử lý lại sau backoff; main consumer có thể tiếp tục, tăng throughput nhưng record sau **có thể vượt record trước**. Với event/state machine cần thứ tự theo business key, phải có sequence guard hoặc cơ chế chặn thích hợp.

Kafka có thứ tự log **trong mỗi topic partition**, không có thứ tự commit nghiệp vụ toàn cục khi nhiều consumer/handler xử lý bất đồng bộ. Kafka key để định tuyến partition **không phải** correlation ID request–reply hoặc idempotency key.

### Thận trọng với lời hứa exactly-once

Một cơ chế transaction/offset của Kafka có thể bảo đảm các thao tác cụ thể trong hệ sinh thái Kafka theo điều kiện riêng, nhưng **không tự đưa business DB/HTTP side effect vào cùng atomic transaction**. Cần idempotency hoặc thiết kế giao dịch phù hợp khi worker ghi ra hệ thống ngoài Kafka.

## 8. So sánh transport để chọn chính sách retry

| Khía cạnh | RabbitMQ/AMQP | Kafka |
| --- | --- | --- |
| Đơn vị giao nhận | Message trong queue/consumer | Record trong topic partition |
| Vị trí xác nhận | Consumer ACK/NACK theo chế độ và adapter | Offset commit/transaction theo consumer framework |
| Giao lại | Requeue/redelivery, queue/DLX policy | Re-consume sau seek/rebalance, retry topic hoặc cơ chế ứng dụng |
| Bản chất thứ tự | Phụ thuộc queue, consumer, prefetch, requeue | Thứ tự log trong một partition |
| Delay/backoff | Retry queue, TTL/DLX, delayed scheduling hoặc advice/container | Backoff trong consumer, retry topic và scheduling |
| Dead letter | DLX/DLQ theo binding | DLT/topic lỗi theo producer và consumer policy |
| Request–reply | Reply-to, correlation property hoặc gateway | Cần reply topic, correlation và quy tắc định tuyến |
| Điểm kiểm tra | ACK mode, requeue default, publisher confirms, redelivery | Offset commit, retry policy, ordering và topic retention |

Không có một câu trả lời “broker nào retry tốt hơn” cho mọi hệ thống. Quan trọng là **hợp đồng thực thi của adapter + yêu cầu tính đúng nghiệp vụ + năng lực vận hành**.

## 9. Spring Integration: retry advice hoạt động ở đâu?

Spring Integration có các cơ chế xử lý lỗi như **error channel**, **service activator**, **RequestHandlerRetryAdvice** và tích hợp với **Spring Retry**. Chúng hữu ích nhưng phạm vi phải được hiểu chính xác.

**RequestHandlerRetryAdvice** thường bao quanh việc gọi **một MessageHandler** và retry khi handler báo lỗi qua exception. Nó không tự theo dõi mọi công việc bất đồng bộ phát sinh sau khi handler return.

~~~mermaid
flowchart LR
    IN["Input message"] --> H["MessageHandler"]
    A["Retry advice"] --> H
    H --> S["Business service"]
    S --> DB[("DB / API")]
    H --> OUT["Output/reply"]
~~~

Nếu handler chuyển công việc vào một executor rồi trả về thành công, retry advice ở handler ấy có thể **không thấy lỗi phát sinh trên thread bất đồng bộ**. Muốn retry đúng, phải đặt cơ chế ở nơi có thể quan sát lỗi và ranh giới commit thật.

### Chọn đúng vị trí đặt retry

| Nơi áp dụng | Phù hợp khi | Rủi ro |
| --- | --- | --- |
| Retry quanh synchronous handler | Lỗi tạm thời xảy ra trước khi handler return | Gọi lại side effect nếu không idempotent |
| Listener/container retry | Cần kiểm soát ACK/requeue sau nhiều lần thử | Có thể lặp toàn message thay vì một item |
| Broker redelivery | Consumer không xác nhận thành công | Không biết side effect trước khi crash đã commit chưa |
| Fault-tolerant Spring Batch step | Item/chunk có lỗi retryable được framework quản lý | Không thay thế retry publish/reply của middleware |
| Job restart | Phục hồi execution thất bại bằng metadata | Không tự điều khiển retry message đang inflight |

**Không chồng nhiều lớp retry chỉ vì mỗi thư viện đều có annotation `@Retryable` hoặc một thuộc tính `retryLimit`.** Mỗi lớp cần có mục đích và giới hạn độc lập.

## 10. Ví dụ Java: retry advice cho MessageHandler đồng bộ

Ví dụ sau minh họa cấu hình **Spring Integration + Spring Retry** cho một handler đồng bộ, với số lần thử hữu hạn và exponential backoff. Đây là ví dụ cấu trúc để học; trong remote chunking thật, phải xác định handler/adapter nào do Spring Batch Integration sở hữu trước khi gắn advice.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.support.RetryTemplate;

@Bean
public RequestHandlerRetryAdvice transientHandlerRetryAdvice() {
    RetryTemplate retryTemplate = new RetryTemplate();

    // maxAttempts bao gồm lần thử đầu tiên.
    SimpleRetryPolicy retryPolicy = new SimpleRetryPolicy();
    retryPolicy.setMaxAttempts(3);
    retryTemplate.setRetryPolicy(retryPolicy);

    ExponentialBackOffPolicy backOff =
            new ExponentialBackOffPolicy();
    backOff.setInitialInterval(200L); // ms
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(2_000L);    // ms
    retryTemplate.setBackOffPolicy(backOff);

    RequestHandlerRetryAdvice advice =
            new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(retryTemplate);
    return advice;
}
~~~

**Lưu ý quan trọng về ví dụ:**

- `SimpleRetryPolicy` như trên tập trung minh họa số lần thử; **chưa phân loại đầy đủ exception retryable và non-retryable**. Production nên định nghĩa policy theo loại lỗi cụ thể.
- Backoff trên handler đồng bộ giữ thread đang xử lý trong thời gian chờ; nếu có nhiều message lỗi, các consumer threads có thể bị chiếm hết.
- `RequestHandlerRetryAdvice` không tự ACK broker hay gửi request vào DLQ; việc đó phụ thuộc adapter, error flow và recovery logic.
- Nếu một lần gọi handler đã commit external side effect trước khi exception, advice có thể gọi lại toàn handler. Chỉ dùng khi thao tác được bảo vệ bằng transaction hoặc idempotency phù hợp.
- Đoạn mã dành cho API thường gặp trong Spring Integration/Spring Retry tương ứng; phải đối chiếu phiên bản dự án trước khi áp dụng.

### Vì sao cần phân loại exception?

Nếu payload thiếu `stepExecutionId` hoặc business key sai kiểu, retry ba lần không giúp dữ liệu hợp lệ hơn. Ngược lại, DB connection timeout tạm thời có thể phục hồi sau vài giây.

**Retry chỉ nên áp dụng khi nguyên nhân có khả năng biến mất mà không cần thay dữ liệu hoặc mã.**

## 11. Error channel và recovery phải có đích xử lý rõ

Spring Integration có thể chuyển lỗi đến **error channel** dưới dạng message chứa exception và metadata liên quan. Nhưng “có error channel” **không đồng nghĩa** message đã được retry hoặc đưa sang DLQ.

Một chiến lược recovery nên xác định:

1. Lỗi thuộc loại tạm thời hay cố định?
2. Message còn được retry tại chỗ không?
3. Khi hết retry, adapter sẽ throw, reject/NACK, publish DLQ hay đánh dấu FAILED?
4. Nếu đã có DB commit, trạng thái đó được kiểm tra thế nào?
5. Nếu cần trả reply lỗi, protocol manager có nhận và xử lý được không?
6. Nếu lưu ở DLQ, ai chịu trách nhiệm reprocess và đối soát?

~~~mermaid
flowchart TB
    I["Worker xử lý request"] --> D{"Lỗi?"}
    D -->|Không| OK["Commit / reply theo hợp đồng"]
    D -->|Có| C{"Retryable?"}
    C -->|Có| R["Bounded retry + backoff"]
    R --> X{"Thành công?"}
    X -->|Có| OK
    X -->|Không| F["Fail request + recovery policy"]
    C -->|Không| F
    F --> Q[["DLQ / alert / reconciliation"]]
~~~

Sơ đồ mang tính khái niệm: **không** hàm ý Spring Batch Integration tự tạo những channel này. Đặc biệt, một worker đã trả reply thành công cho manager nhưng sau đó error flow mới xảy ra là thiết kế cần xem lại nếu job yêu cầu side effect hoàn tất trước khi báo thành công.

### Không nuốt exception tùy tiện

Một error handler chỉ log lỗi rồi return “thành công” có thể khiến inbound listener ACK message. Khi ấy manager có thể không biết một phần việc đã thất bại.

Cần quyết định rõ khi nào một lỗi được **xử lý và hoàn tất**, khi nào phải **propagate** để listener áp dụng retry/rejection policy phù hợp.

## 12. Phân loại lỗi: retryable và non-retryable

| Loại lỗi | Ví dụ | Hành động khuyến nghị |
| --- | --- | --- |
| Network tạm thời | TCP reset, broker disconnect, timeout ngắn | Retry có giới hạn, backoff và quan sát |
| DB quá tải ngắn hạn | Connection timeout, deadlock có thể retry | Retry có giới hạn; giảm concurrency nếu lặp |
| Quota/rate limit | HTTP 429 có Retry-After | Tôn trọng thời gian được yêu cầu, giới hạn lưu lượng |
| HTTP server lỗi tạm | 502/503/504 trong điều kiện phù hợp | Retry an toàn nếu idempotent hoặc có key |
| Payload sai schema | Thiếu trường, sai kiểu, không deserialize | Thường fail fast, DLQ/quarantine |
| Vi phạm nghiệp vụ | Trạng thái không hợp lệ, key không tồn tại | Fail hoặc xử lý theo chính sách nghiệp vụ, không retry vô hạn |
| Authentication/authorization | 401/403 do credentials/config | Sửa cấu hình/quyền; retry liên tục hiếm khi có ích |
| Unique conflict | Dữ liệu trùng hoặc cạnh tranh | Phân biệt duplicate hợp lệ với conflict thực |
| Worker JVM bị kill | Không có exception xử lý ở worker cũ | Broker redelivery/manager reconciliation và restart |
| Reply thất lạc | Business work có thể đã xong | Đối chiếu trạng thái, không vội chạy lại |

Không chỉ dựa vào **tên exception**; một `TimeoutException` có thể xuất hiện sau khi dịch vụ đích đã nhận lệnh và commit. Với tác dụng không idempotent, retry tự động có thể nguy hiểm dù nguyên nhân trông tạm thời.

### Retry theo ngữ nghĩa HTTP

- GET không có side effect có thể dễ thử lại hơn, nhưng vẫn phải giới hạn tải.
- POST thanh toán/tạo tài nguyên thường cần **idempotency key** do API hỗ trợ.
- 429 có thể mang thông tin `Retry-After`; không dùng backoff ngắn hơn quota cho phép.
- Nếu API trả về kết quả không rõ (timeout sau gửi), ưu tiên **tra cứu trạng thái theo business operation ID** trước khi lặp thao tác.

## 13. Exponential backoff, jitter và retry budget

Một công thức backoff đơn giản:

\[
d_n = \min(d_{\max}, d_0 \times \alpha^{n-1})
\]

Trong đó `d_0` là delay ban đầu, `\alpha` là hệ số tăng, `d_max` là trần. Ví dụ `d_0=200ms`, hệ số `2`, trần `2s`:

| Lượt thử lại | Delay trước lượt retry |
| ---: | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 2.000 ms (đạt trần) |

Đây là bảng minh họa chính sách có **năm lần retry sau lần gửi/ xử lý đầu**; cần phân biệt `maxAttempts` thường **bao gồm** lần đầu trong nhiều API retry, còn tên biến `maxRetries` có thể chỉ đếm các lượt bổ sung.

### Jitter để tránh retry storm

Nếu 1.000 worker đều gặp DB outage cùng lúc, cùng backoff cố định có thể khiến chúng retry đồng loạt sau đúng 1 giây, làm DB vừa phục hồi bị quá tải trở lại.

Thêm một khoảng **jitter** ngẫu nhiên trong giới hạn, ví dụ full jitter cho delay cap, giúp phân tán thời điểm retry. Thiết kế cần:

- Trần delay.
- Tổng thời gian retry tối đa (*retry budget/deadline*).
- Số attempts hữu hạn.
- Cơ chế dừng hoặc pause khi downstream đang quá tải.
- Khả năng hủy công việc khi job đã thất bại/đã bị stop.
- Metric cho số lượt thử, thời gian chờ và số request đang inflight.

**Không phải mọi thao tác cần retry ngay ở cùng thread.** Với chờ dài, delayed queue/scheduler có thể tiết kiệm worker threads hơn, nhưng tăng độ phức tạp ordering, state và recovery.

## 14. Cấu hình retry budget để không bùng nổ công việc

Giả sử một worker JVM có 16 consumer, mỗi message được xử lý tối đa bốn attempts và manager cũng có thể gửi lại cùng request do timeout. Nếu DB đang lỗi, toàn cluster có thể tạo nhiều transaction thất bại trong thời gian ngắn.

Hãy định nghĩa một **ngân sách retry toàn tuyến**:

| Giới hạn | Ví dụ chính sách | Mục đích |
| --- | --- | --- |
| Handler attempts | Tối đa 3 lần tính cả lần đầu | Không lặp mãi trên worker |
| Message redelivery | Tối đa 3 lần theo retry count bền vững | Giới hạn lặp qua broker |
| Retry deadline | Không quá 2 phút cho lỗi tạm | Chặn request hết ý nghĩa |
| Concurrency | Tối đa 4 request/worker JVM | Giới hạn tải DB |
| Manager outstanding | Giới hạn N chunk chưa rõ kết quả | Tạo backpressure |
| Circuit breaker | Tạm ngừng khi DB/API lỗi rộng | Tránh lũ retry đồng bộ |
| DLQ threshold | Vượt budget → quarantine/alert | Cho phép điều tra thủ công |

Các con số là **minh họa**, không phải mặc định tốt nhất. Quan trọng là budget các tầng **không vô tình nhân lên vô hạn** và đủ thời gian cho SLA/restart.

### Đếm retry thế nào?

Nếu custom header `attempt` được tăng khi ứng dụng gửi lại, **broker redelivery có thể không tăng header ấy**. Nếu muốn giới hạn redelivery dựa trên dữ liệu bền vững, phải chọn cơ chế đúng broker/adapter và lưu attempt state khi cần.

Không tin vào một bộ đếm trong bộ nhớ của worker JVM để giới hạn tổng retry sau khi JVM chết; nó có thể reset về 0 khi process khởi động lại.

## 15. Dead-letter queue: giữ bằng chứng, không phải “xử lý xong”

Một **dead-letter queue (DLQ)** hoặc dead-letter topic lưu các message không thể xử lý theo chính sách hiện tại. Đây là khu vực cách ly và điều tra, **không mặc nhiên là nơi công việc đã hoàn thành**.

DLQ cần có:

- Payload gốc ở định dạng có thể truy xuất an toàn.
- Lý do lỗi và loại exception được chuẩn hóa.
- Correlation/request ID, job/step execution ID khi có.
- Số attempts hoặc dấu hiệu redelivery đáng tin cậy.
- Timestamp nhận và thời điểm lỗi.
- Version của application và message schema.
- Quy định retention, ACL và bảo vệ dữ liệu nhạy cảm.
- Runbook quyết định sửa payload, replay, bỏ qua có phê duyệt hoặc fail job.

### Cẩn trọng khi replay

Nếu message DLQ được gửi lại sau khi một phần side effect đã commit, writer cần chống lặp. Nếu manager đã kết thúc JobExecution FAILED và JobInstance được restart, việc tự replay DLQ **song song** có thể tạo hai cơ chế phục hồi tranh cùng dữ liệu.

**Một nguồn điều phối phục hồi phải có quyền sở hữu rõ ràng.** Replay DLQ không được tách khỏi trạng thái Spring Batch khi nó có thể gây xử lý lại cùng phần việc.

### Không coi mọi DLQ event là skip hợp lệ

Spring Batch có chính sách skip cho item lỗi tùy nghiệp vụ, nhưng đưa một **chunk request/partition request** sang DLQ rồi coi step thành công không tương đương với skip hợp lệ từng item. Manager cần biết liệu work unit đã bị bỏ qua, đã fail hay còn đợi xử lý.

## 16. Poison message và lỗi không thể khôi phục bằng chờ đợi

**Poison message** là thông điệp luôn thất bại với code/cấu hình và dữ liệu hiện tại, chẳng hạn schema không hợp lệ, step name sai hoặc business rule vĩnh viễn không thỏa.

Nếu không giới hạn retry, một poison message có thể:

- Giữ consumer bận vô thời hạn.
- Làm queue không tiến triển.
- Tạo hàng triệu log lỗi giống nhau.
- Chặn các message sau nếu strict order.
- Làm manager timeout rồi tự gửi lại thêm bản sao.
- Phát sinh nhiều DLQ/redelivery loops không có điểm dừng.

### Hướng xử lý

1. Validate schema và các field bắt buộc ngay khi nhận.
2. Phân loại lỗi không thể phục hồi và không retry lặp.
3. Gửi tới quarantine/DLQ nếu hợp đồng và hạ tầng cho phép.
4. Báo cho manager/workflow biết phần việc đã thất bại.
5. Bảo toàn thông tin đối soát.
6. Có quy trình sửa dữ liệu và replay có kiểm soát.

Không nên **ACK thành công** một request chỉ để queue thông thoáng trong khi nghiệp vụ chưa được xử lý. Nếu deliberately skip theo chính sách, phải ghi rõ skip là hợp lệ và ảnh hưởng tới kết quả cuối.

## 17. Idempotency ở cấp item và business operation

Khi delivery có thể lặp, writer nên được thiết kế để cùng business operation được gọi lại không làm sai kết quả.

### Upsert cho bản ghi snapshot

Ví dụ PostgreSQL:

~~~sql
INSERT INTO normalized_transaction (
    transaction_id, normalized_amount_cents, source_version
)
VALUES (:transactionId, :amountCents, :sourceVersion)
ON CONFLICT (transaction_id)
DO UPDATE SET
    normalized_amount_cents =
        EXCLUDED.normalized_amount_cents,
    source_version = EXCLUDED.source_version
WHERE normalized_transaction.source_version
      <= EXCLUDED.source_version;
~~~

Mẫu chỉ thích hợp khi bản ghi nguồn là **snapshot hoặc phép ghi đè theo version** và có ràng buộc `UNIQUE` trên `transaction_id`. Trong tình huống hai bản ghi cùng version nhưng payload khác nhau, cần thêm kiểm tra conflict; `<=` có thể chấp nhận ghi đè cùng version nếu nghiệp vụ cho phép, nhưng không tự phân biệt payload không nhất quán.

### Ledger cho side effect dạng cộng dồn

Giả sử event chứa delta cần cộng vào balance **một lần**. Không dùng một `UPDATE balance = balance + delta` đơn lẻ khi request có thể đến lại.

Schema minh họa:

~~~sql
CREATE TABLE applied_transaction (
    transaction_id UUID PRIMARY KEY,
    account_id BIGINT NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong một transaction DB:

1. Cố xác lập ownership của `transaction_id` qua unique constraint.
2. Nếu đã có, đối chiếu payload hash; đúng duplicate thì không cập nhật lại, sai hash thì fail.
3. Nếu chưa có, cập nhật balance theo quy tắc nghiệp vụ.
4. Commit **ledger và business update cùng nhau**.
5. Nếu rollback, cả hai phải được hoàn tác theo transaction manager/resource.

Phải thiết kế concurrency/locking hợp lý; chỉ `SELECT` kiểm tra trước rồi `INSERT` sau **không đủ** vì hai worker có thể cùng thấy chưa tồn tại. Ràng buộc unique ở DB là một lớp bảo vệ quan trọng.

**Đặc biệt:** ledger này bảo vệ DB nằm trong transaction. Gửi email, gọi thanh toán hoặc đẩy message ra broker khác cần thêm idempotency key, outbox hoặc quy trình đối soát riêng.

## 18. Idempotency của chunk không giống idempotency của message ID

Một chunk có thể chứa 500 item; sau rollback/restart, ranh giới chunk có thể thay đổi vì filter, skip hoặc đầu vào thay đổi. Do đó:

- `MessageHeaders.ID`: thường định danh envelope.
- `correlationId`: giúp ghép request–reply.
- `chunkSequence`: định danh thứ tự chunk theo giao thức/luồng chạy nếu có.
- `business event ID`: định danh bản ghi/side effect cần chống lặp.

**Không mặc định rằng chunk 42 của lần restart chứa đúng cùng 500 item với chunk 42 của lần chạy trước.** Dedupe xuyên restart theo `chunkSequence` có thể bỏ sót hoặc làm sai dữ liệu.

Một thiết kế an toàn thường **đối soát và idempotent ở cấp business key/event ID**, đồng thời tôn trọng checkpoint và protocol state của Spring Batch Integration.

### Message redelivery ≠ chunk rollback

Message cũ có thể được giao lại dù chunk lần đầu đã commit. Ngược lại, một chunk có thể rollback khi worker còn sống mà broker chưa redeliver. Hai cơ chế cần được test riêng.

## 19. Reply bị mất: một trường hợp cần reconciliation hơn là retry mù

Giả sử remote chunking manager gửi request `C42`. Worker ghi thành công, nhưng kết nối reply broker lỗi.

~~~text
Manager: SENT C42
Worker:  COMMITTED C42
Reply:   LOST / NOT OBSERVED
Manager: TIMEOUT C42
~~~

Timeout chỉ cho biết manager **chưa quan sát được reply hợp lệ**, không xác nhận worker đã dừng hay chưa commit.

Có thể cần:

- Correlation ID gắn với request/chunk theo giao thức.
- Job/Step execution metadata hoặc trạng thái ứng dụng để đối chiếu.
- Ledger/idempotency theo business key để biết side effect đã xảy ra.
- Một chính sách retry và timeout không cho hai worker cùng chạy thiếu kiểm soát.
- Khả năng xử lý reply muộn hoặc duplicate reply.

### Tình huống ba reply

~~~text
Request A, B, C gửi theo thứ tự A→B→C
Reply B đến trước, C đến tiếp, A đến cuối
~~~

Manager phải ghép **B với B, C với C, A với A**. Retry hoặc redelivery có thể làm cùng correlation xuất hiện hơn một lần; không được tăng completed count hai lần.

**Correlation trả lời “thuộc request nào”; idempotency trả lời “đã tạo side effect chưa”.** Cả hai đều cần thiết, nhưng không thay thế nhau.

## 20. Remote partitioning: không chạy cùng StepExecution thiếu kiểm soát

Với remote partitioning, worker nhận yêu cầu thực thi một **StepExecution đã tồn tại**. Nếu worker A nhận request và đang xử lý, nhưng manager timeout rồi giao lại cho worker B, có nguy cơ **cả hai cùng thực thi một StepExecution**.

Điều cần làm:

- Xác minh StepExecution status và trạng thái worker cũ.
- Tuân theo cách quản lý dispatch/restart của `PartitionHandler` và framework đang dùng.
- Không tự tạo StepExecution mới chỉ bằng cách copy request ID.
- Không tự quyết định “retry ở worker khác” khi chưa chắc worker cũ đã ngừng.
- Giữ partition name và ExecutionContext input ổn định qua restart.
- Có ràng buộc business key/idempotency chống ghi trùng ngay cả khi gặp trường hợp bất thường.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant A as Worker A
    participant J as JobRepository
    participant B as Worker B

    M->>A: StepExecutionRequest P7
    A->>J: Bắt đầu StepExecution P7
    M--xA: Mất kết nối / không thấy reply
    Note over M: Không có nghĩa Worker A đã dừng
    M->>J: Kiểm tra trạng thái P7
    M->>B: Chỉ giao lại theo recovery policy an toàn
~~~

Sơ đồ nhấn mạnh **reconciliation trước khi thực thi lại**. Cách chính xác để phát hiện stale execution hoặc dọn trạng thái phụ thuộc phiên bản Spring Batch, repository và kiến trúc giám sát worker; không có một thao tác broker ACK duy nhất giải quyết được.

## 21. Retry message và Spring Batch fault tolerance khác nhau

Spring Batch hỗ trợ cấu hình **retry/skip** cho chunk-oriented step theo chính sách item/chunk. Spring Integration và broker lại có retry ở cấp message.

Ví dụ cấu hình fault-tolerant worker step:

~~~java
@Bean
public Step retryableWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRow> reader,
        ItemProcessor<InputRow, OutputRow> processor,
        ItemWriter<OutputRow> writer) {

    return new StepBuilder("retryableWorkerStep", jobRepository)
            .<InputRow, OutputRow>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

Đây là mã minh họa API thường gặp ở **Spring Batch 5.x**, giả định các import, DTO và bean hạ tầng đã được khai báo. `TransientDataAccessException` thuộc Spring DAO; trong dự án thật phải chọn đúng exception có thể retry và kiểm thử transaction.

**Không suy ra** rằng `.retryLimit(3)` ở worker step đồng nghĩa broker sẽ chỉ giao request tối đa ba lần. Đây là chính sách **của Spring Batch step**, còn broker redelivery phụ thuộc lớp messaging.

### Tổng số lượt thử

Nếu step retry ba lần ở một transaction, nhưng message bị giao lại hai lần, cùng business operation có thể được gọi nhiều lần. Với HTTP side effect không idempotent, vấn đề có thể phát sinh trước khi code chạm tới DB.

Cần một bảng cấu hình có chủ đích ghi rõ **tầng retry nào là chủ sở hữu chính** cho mỗi loại lỗi.

## 22. Concurrency, ordering và backpressure khi retry

Retry tăng tải lên hệ thống đang gặp sự cố. Nếu manager tạo 10.000 chunk requests nhưng worker chỉ xử lý được 2.000, queue backlog và latency sẽ tăng.

Đặc biệt, **message lỗi có thể bị đưa lại phía sau queue**, khiến request mới vượt qua request cũ. Với nghiệp vụ yêu cầu thứ tự theo account/order, phải bảo vệ bằng sequence guard hoặc routing theo key, không tin rằng retry queue giữ đúng thứ tự commit.

### Ba giới hạn nên phối hợp

1. **Manager outstanding chunks/partitions:** không cấp việc vô hạn khi worker chưa hoàn tất.
2. **Worker consumer concurrency:** số request thực thi đồng thời tương ứng CPU và connection budget.
3. **Downstream capacity:** DB, HTTP quota, broker throughput, transaction log và index lock.

Một mô hình đơn giản:

\[
R_{\mathrm{job}}
\leq \min(R_{\mathrm{read}},R_{\mathrm{worker}},
         R_{\mathrm{write}},R_{\mathrm{transport}})
\]

Các tốc độ phải quy đổi về cùng đơn vị item; nếu processor filter, phải tính tỷ lệ đầu vào/đầu ra. Retry làm lượng **work attempted** tăng nhưng không tương đương lượng **business work committed**.

### Queue dài không có nghĩa throughput tăng

Nếu producer gửi 3.000 chunk/s và worker chỉ hoàn thành 2.500 chunk/s, backlog có thể tăng xấp xỉ 500 chunk/s khi tải ổn định. Retry thêm 300 chunk/s có thể làm tình trạng tệ hơn. Cần backpressure, giảm concurrency hoặc pause khi downstream quá tải.

## 23. Test retry với fault injection thực tế

Một test happy path chỉ chứng minh message đi đúng đường. Muốn xác nhận recovery, phải tạo lỗi **trước và sau commit**.

| Thử nghiệm | Điều cần chứng minh |
| --- | --- |
| Kill worker trước DB commit | Chunk/partition chưa commit được xử lý lại an toàn |
| Kill worker sau commit trước ACK | Redelivery không nhân đôi business effect |
| Broker disconnect lúc producer publish | Không mất phần việc, duplicate được nhận diện |
| Broker disconnect lúc worker gửi reply | Manager reconcile, không gửi lại mù |
| DB timeout trong worker | Retry có giới hạn/backoff; không tạo retry storm |
| Invalid schema/step name | Fail fast, DLQ/error flow phù hợp |
| Một poison message | Không chặn queue mãi; không ACK thành công giả |
| Duplicate request | Không có hai side effect cho cùng business key |
| Duplicate reply | Manager không đánh dấu hoàn thành hai lần |
| Reply B về trước A | Correlation đúng; không ghép nhầm |
| Retry qua delayed queue | Không phá ordering nghiệp vụ ngoài policy |
| Restart JobInstance | Reader checkpoint và writer idempotent bảo đảm đúng dữ liệu |
| Worker cũ còn chạy khi manager timeout | Không khởi thêm cùng StepExecution thiếu kiểm soát |
| DLQ replay | Không chạy song song với một cơ chế restart tranh cùng work |

### Trình tự test đề xuất

1. Tạo snapshot/dataset nhỏ có business key rõ và expected output.
2. Chạy một worker với broker thật hoặc containerized broker có cùng loại với production.
3. Bật log/correlation ID để quan sát request/reply.
4. Thêm worker, thay đổi độ trễ nhằm tạo hoàn thành đảo thứ tự.
5. Inject lỗi ở từng mốc publish, receive, commit, ACK và reply.
6. Tạo duplicate message, non-retryable exception và timeout.
7. Kiểm tra broker state, JobRepository và ledger business.
8. Đối soát đầu ra với baseline tuần tự đã được chấp nhận.
9. Kiểm tra không rò connection/thread và retry đã dừng đúng budget.

## 24. Ví dụ integration-test mô phỏng duplicate delivery

Mã dưới đây là ví dụ **mức dịch vụ** để chứng minh idempotency khi cùng event được gọi nhiều lần. Nó không thay thế test RabbitMQ/Kafka hay Spring Batch JobRepository.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class IdempotentEventServiceTest {

    @Test
    void sameEventMayBeDeliveredTwiceButAppliedOnce() {
        UUID eventId = UUID.fromString(
                "00000000-0000-0000-0000-000000000042");

        FakeLedgerAndBalanceStore store =
                new FakeLedgerAndBalanceStore();
        IdempotentEventService service =
                new IdempotentEventService(store);

        service.apply(eventId, 42L, 150L);
        service.apply(eventId, 42L, 150L); // redelivery

        assertEquals(150L, store.balance(42L));
        assertEquals(1, store.appliedEventCount());
    }
}
~~~

Các lớp `FakeLedgerAndBalanceStore` và `IdempotentEventService` là **kiểu giả định**, không phải thư viện Spring Batch. Để kiểm tra concurrency thật, dùng DB có unique constraint và cho hai consumer gọi cùng event đồng thời; một fake store trong bộ nhớ không phát hiện đầy đủ race/transaction isolation.

### Biến thể test bắt buộc

- Gửi cùng eventId nhưng payload khác: phải báo conflict.
- Đưa hai event cùng account vào worker song song: xác minh atomicity/order theo yêu cầu nghiệp vụ.
- Dùng API ngoài với idempotency key và timeout sau khi API đã nhận yêu cầu.
- Kill JVM giữa việc ghi ledger và business update: nếu hai thao tác cùng transaction, không có trạng thái nửa vời.
- Chạy lại cùng business operation ở JobExecution khác: kết quả vẫn đúng.

## 25. Observability: metric nào chứng minh retry an toàn?

Khi vận hành phân tán, không chỉ đếm tổng số message. Cần phân biệt **số lượt xử lý** và **số công việc nghiệp vụ hoàn tất**.

| Metric/log | Ý nghĩa |
| --- | --- |
| `message_publish_attempts_total` | Producer đã cố gửi bao nhiêu lần |
| `message_publish_confirm_failures_total` | Publish confirm gặp vấn đề |
| `message_redeliveries_total` | Broker/consumer quan sát message giao lại |
| `handler_retry_attempts_total` | Số lượt gọi handler do retry |
| `retry_exhausted_total` | Số request hết retry budget |
| `dead_letter_messages_total` | Số message đưa vào DLQ/DLT |
| `dead_letter_oldest_age` | Work lỗi bị tồn đọng bao lâu |
| `duplicate_business_events_total` | Số duplicate được writer chặn |
| `message_request_timeout_total` | Manager/gateway quá hạn chờ |
| `late_reply_total` | Số reply đến sau timeout |
| `inflight_request_count` | Số request chưa có kết quả cuối |
| `queue_age` | Broker backlog thực |
| `worker_chunk_duration` | Latency xử lý và commit worker |
| `db_lock_wait` / `connection_wait` | Có nghẽn DB do retry/concurrency không |
| `reconciliation_failures_total` | Kết quả dữ liệu sai, thiếu hoặc trùng |

### Correlation log minh họa

~~~text
jobExecutionId=19001
managerStepExecutionId=19042
logicalWorkId=chunk-000452
correlationId=run-19001-step-19042-request-452
workerInstance=worker-jvm-03
attempt=2
redelivered=true
failureClass=TransientDatabaseTimeout
businessCommitStatus=UNKNOWN
recoveryAction=RECONCILE
~~~

Đây là ví dụ định danh của ứng dụng; **không** phải định dạng header tiêu chuẩn bắt buộc của Spring Batch Integration. Nên thống nhất field naming qua manager, broker và worker.

**Cardinality:** các ID động thuộc logs/traces; đừng dùng mỗi correlationId, eventId hay StepExecutionId làm label của metric vì có thể tạo hàng triệu time series.

### Đo hiệu quả retry

Một hệ thống báo “100.000 message processed/s” nhưng 30% là duplicate hoặc retry có thể chỉ hoàn thành ít công việc hơn nhiều. Nên đo:

\[
R_{\mathrm{useful}} =
\frac{\text{số business item được commit hợp lệ}}
{\text{elapsed time}}
\]

Khi có item filtered/skip, cần định nghĩa rõ `business item` để so sánh nhất quán. Tăng retry attempts mà không tăng `R_useful` là tín hiệu cần tối ưu, không phải thành công về throughput.

## 26. Tình huống minh họa: 15 triệu bản ghi và DB timeout

Một hệ thống nhập **15.000.000 giao dịch** trong cửa sổ **30 phút**. Manager gửi chunk 500 item qua broker cho worker; writer lưu vào database với khóa `transaction_id` duy nhất.

Mức thông lượng input tối thiểu theo phép chia lý tưởng:

\[
R_{\mathrm{required}} =
\frac{15.000.000}{30\times60}
\approx 8.333\ \mathrm{items/s}
\]

Giả định khi không có lỗi, 8 worker đạt 10.500 item/s đầu ra. Nhưng trong thời điểm cao tải, DB xuất hiện connection timeout và worker bắt đầu retry.

### Phiên bản A — retry tức thì vô hạn

- Broker requeue ngay khi handler fail.
- Worker có nhiều consumer liên tục nhận lại message cũ.
- Manager cũng timeout và gửi yêu cầu mới.
- DB chưa phục hồi đã phải nhận thêm kết nối và giao dịch.
- Queue age tăng, CPU worker dùng nhiều cho lỗi, số item commit giảm.

Giả sử throughput hữu ích giảm xuống **4.800 item/s**. Đây là số **giả định** để giải thích retry amplification, không phải tính chất mặc định của Spring Batch.

### Phiên bản B — retry có ngân sách và idempotency

Thiết kế lại:

1. Bounded handler retry cho lỗi DB ngắn.
2. Backoff có jitter hoặc delayed retry phù hợp.
3. Consumer concurrency giới hạn theo connection pool.
4. Không retry lỗi schema/validation.
5. DLQ/alert khi vượt budget, không âm thầm coi job hoàn thành.
6. Writer idempotent theo `transaction_id` và source version.
7. Manager đối chiếu timeout/reply trễ; không chạy lại mù.
8. Có đối soát business key sau restart.

Bảng benchmark giả định:

| Cấu hình | Worker | Retry behavior | Throughput hữu ích | Kết quả |
| --- | ---: | --- | ---: | --- |
| Không lỗi, baseline | 8 | Ít retry | 10.500 item/s | PASS |
| DB timeout + requeue nóng | 8 | Vòng lặp tức thì | 4.800 item/s | Chậm, nhiều tải thừa |
| Bounded retry + backoff | 8 | Có giới hạn | 8.900 item/s | PASS sau thử lỗi |
| Bounded retry + tăng worker | 16 | Có giới hạn nhưng DB wait cao | 8.600 item/s | Không tăng ích lợi |
| Bounded retry + 6 worker | 6 | Ít contention hơn | 8.700 item/s | Có thể đủ SLA |

**Diễn giải:** với 15 triệu item, 8.700 item/s cho thời gian lý tưởng `15.000.000/8.700 ≈ 28,7 phút`. Thời gian này **chưa** bao gồm khởi tạo, nghỉ backoff, bước cuối và dự phòng restart. Vì vậy nếu SLA đúng 30 phút, chỉ dựa vào thông lượng trung bình là chưa đủ; phải đo toàn job trong tình huống lỗi thực tế.

### Kế hoạch xác nhận

- Ghi đủ request/reply correlation và timeline ACK/commit.
- Tắt DB trong một khoảng ngắn, xem retry có tràn queue không.
- Kill worker ngay sau commit một chunk.
- Khởi động lại và đối soát mọi transaction_id.
- Kiểm tra đúng số bản ghi được commit và không có side effect trùng.
- Kiểm tra DLQ không chứa phần việc bị bỏ quên ngoài chính sách.
- Chọn số worker theo SLA **và** connection/CPU/DB budget.

Bài học là **retry tốt phải giúp hoàn thành công việc đúng, không làm downstream quá tải thêm**.

## 27. Khi nào cần circuit breaker hoặc tạm dừng tiêu thụ?

Retry từng message có thể hợp lý khi một vài request lỗi. Nhưng nếu toàn bộ database, HTTP API hoặc broker downstream đang outage, việc 20 JVM cùng retry sẽ tốn tài nguyên mà không tăng xác suất thành công đáng kể.

Có thể cân nhắc:

- **Circuit breaker:** mở khi tỷ lệ lỗi cao, thử lại theo nhịp thăm dò.
- **Pause/resume consumer:** tạm dừng lấy thêm message khi DB không sẵn sàng.
- **Backpressure:** giới hạn request mới do manager gửi.
- **Bulkhead:** cô lập những loại phần việc gây lỗi để phần việc khác vẫn tiến triển.
- **Rate limiter:** bảo vệ quota của API/DB đích.
- **Admission control:** từ chối hoặc trì hoãn phần việc mới khi capacity đang cạn.

Những cơ chế này phải được phối hợp với **JobExecution status, stop/restart và SLA**. Pause consumer không có nghĩa message đã hoàn thành; job cần biết đang chờ, thất bại hay được phép phục hồi sau.

**Không nên cắt bỏ cơ chế retry/restart của Spring Batch bằng một circuit breaker tự viết mà không hiểu metadata của framework.** Thiết kế phải giữ được quyền sở hữu phần việc và khả năng đối soát.

## 28. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| “Retry message có nghĩa Spring Batch tự retry item.” | Broker/handler và fault-tolerant step là các tầng khác nhau. |
| “ACK broker là DB đã commit.” | ACK không mặc nhiên atomic với transaction nghiệp vụ. |
| “At-least-once nghĩa là exactly-once.” | At-least-once cho phép duplicate; writer phải lặp lại an toàn. |
| “Publisher confirm nghĩa là worker đã xử lý.” | Confirm là sự kiện ở phía broker/producer theo policy, không phải business completion. |
| “Timeout manager nghĩa là worker đã dừng.” | Worker có thể vẫn chạy hoặc đã commit. |
| “Requeue ngay là retry nhanh nhất và tốt nhất.” | Có thể tạo hot loop và retry storm. |
| “Có error channel là tự động đưa lỗi vào DLQ.” | Error handling cần recovery flow/adapter policy cụ thể. |
| “DLQ nghĩa là work đã được xử lý.” | DLQ là quarantine; cần xử lý/replay/đối soát. |
| “RetryLimit(3) của worker step giới hạn broker redelivery.” | Hai cấu hình không tự đồng bộ. |
| “Chỉ retry timeout luôn an toàn.” | Timeout có thể xảy ra sau khi side effect đã commit. |
| “Message ID là idempotency key tốt nhất.” | Envelope có thể thay đổi khi phát lại; cần business key bền vững. |
| “Retry topic không ảnh hưởng thứ tự.” | Event đến sau có thể vượt event đang retry. |
| “Nhiều worker giảm latency trong outage.” | Có thể tăng lock wait, queue và số lỗi. |
| “COMPLETED nghĩa là không có duplicate side effect.” | Cần đối soát business key và resource ngoài DB. |
| “Thêm retry là thay thế được restart.” | Restart cần JobRepository/checkpoint và input ổn định. |

## 29. Checklist thiết kế retry message delivery

- [ ] Đã xác định đơn vị retry: publish, message, handler, chunk hay JobExecution.
- [ ] Có timeline rõ cho send → broker → receive → DB commit → ACK → reply.
- [ ] Biết ACK/offset commit chính xác xảy ra ở đâu theo adapter/container.
- [ ] Producer có publish confirm/exception handling và cơ chế chịu duplicate.
- [ ] Có correlation ID request–reply không bị nhầm khi reply đảo thứ tự.
- [ ] Không dùng correlation/message ID thay business idempotency key.
- [ ] Writer xử lý lại an toàn; với DB có unique constraint/ledger khi cần.
- [ ] Có phân loại lỗi retryable và non-retryable, không retry schema lỗi vô hạn.
- [ ] Mỗi tầng retry có max attempts, backoff, deadline và quan sát rõ.
- [ ] Có jitter/circuit breaker/backpressure để tránh retry storm.
- [ ] Có chính sách DLQ/DLT, retention, ACL, alert và runbook replay.
- [ ] DLQ không được coi như business completion nếu hợp đồng không cho phép.
- [ ] Manager xử lý timeout, late reply và duplicate reply đúng protocol.
- [ ] Remote partitioning không giao lại cùng StepExecution thiếu kiểm soát.
- [ ] Restart giữ input/checkpoint ổn định và xử lý lại side effect an toàn.
- [ ] Kiểm tra nguồn/đích vẫn chịu được tổng concurrency/connection pool.
- [ ] Nếu yêu cầu thứ tự, retry topic/requeue không làm sai sequence nghiệp vụ.
- [ ] Có fault injection kill worker trước/sau commit và mất reply.
- [ ] Có metric retry attempts, redelivery, DLQ age, inflight, hữu ích throughput.
- [ ] Đã đối soát dữ liệu và tính chi phí retry trong SLA trước khi tăng worker.

## 30. Câu hỏi tự kiểm tra

**1. Worker commit DB xong nhưng chưa ACK broker thì JVM chết. Điều gì có thể xảy ra?**

Broker có thể giao lại message vì chưa nhận ACK. Nếu writer không idempotent, dữ liệu đã commit có thể bị ghi thêm một lần nữa. Cần bảo vệ side effect bằng khóa nghiệp vụ/transaction hoặc idempotency thích hợp.

**2. Phân biệt retry item của Spring Batch với broker redelivery.**

Retry item/chunk được cấu hình trong step để xử lý lỗi nghiệp vụ hoặc giao dịch theo policy của Spring Batch. Broker redelivery giao lại message chưa xác nhận, có thể khiến toàn request/chunk/partition được xử lý lại. Chúng không dùng chung một giới hạn attempts mặc định.

**3. Vì sao `maxAttempts=3` không nhất thiết nghĩa ba lần retry?**

Trong nhiều RetryPolicy, con số này bao gồm **lần thử đầu tiên**, nên tối đa hai lượt thử bổ sung. Phải đọc hợp đồng của API đang dùng.

**4. Vì sao cần backoff có jitter?**

Khi nhiều worker cùng lỗi do downstream outage, jitter phân tán thời điểm retry, tránh việc tất cả retry đồng loạt tạo quá tải mới.

**5. RabbitMQ publish confirm có chứng minh writer đã commit không?**

Không. Confirm chỉ nói producer/broker đã xác nhận publish theo cơ chế cấu hình; việc worker nhận, xử lý và commit dữ liệu là bước khác.

**6. Kafka offset đã commit có tương đương side effect ở DB đã commit không?**

Không mặc nhiên. Nếu offset commit trước DB, có thể mất work; nếu DB commit trước offset, có thể xử lý lại. Cần idempotency hoặc cơ chế giao dịch phối hợp phù hợp.

**7. Khi nào message nên tới DLQ?**

Khi lỗi không thể retry bằng cách chờ hoặc đã vượt retry budget theo chính sách. DLQ cần cảnh báo, giữ dữ liệu điều tra và quy trình replay an toàn; không mặc nhiên có nghĩa phần việc được hoàn thành.

**8. Manager timeout một partition, có nên gửi cùng StepExecution cho worker khác ngay?**

Không nên nếu chưa chắc worker cũ đã dừng. Cần xác minh StepExecution/ownership, chính sách recovery của PartitionHandler và tính an toàn của writer.

**9. Vì sao messageId/correlationId chưa đủ cho idempotency xuyên restart?**

Chúng thường định danh envelope hoặc hội thoại. Sau restart, cùng business operation có thể nằm trong message/chunk khác; idempotency cần khóa nghiệp vụ ổn định qua các lần thực thi.

**10. Spring Integration error channel có tự bảo đảm request được retry tối đa ba lần không?**

Không. Error channel là một đường xử lý lỗi; phải cấu hình retry advice/container/recovery rõ ràng và kiểm chứng hành vi của adapter.

**11. Khi DB quá tải, vì sao tăng worker có thể khiến job chậm hơn?**

Nhiều worker tạo thêm transaction, lock wait, connection wait và retry. Throughput hữu ích có thể giảm dù số lượt xử lý thử tăng.

**12. Để kiểm chứng hệ thống at-least-once an toàn, cần thử lỗi nào quan trọng nhất?**

Tối thiểu kill worker **sau DB commit nhưng trước ACK/reply**, rồi để message được giao lại và xác nhận không có side effect trùng, metadata đúng và job có thể phục hồi.

---

**Ghi nhớ:** **Retry message delivery là bài toán giao nhận có trạng thái không chắc chắn**, không chỉ là gọi lại một hàm khi có exception. Trong Spring Batch Integration, phải phân biệt retry ở producer, broker, handler, chunk và JobRepository/restart; xác định đúng điểm ACK/commit và xử lý tình huống worker đã ghi dữ liệu nhưng manager chưa biết. Phương án bền vững kết hợp **bounded retry, backoff có jitter, phân loại lỗi, DLQ, correlation, idempotency và reconciliation**, sau đó đo throughput hữu ích và kiểm thử lỗi thật trước khi tăng worker. Mục tiêu là **hoàn thành đúng dữ liệu trong SLA**, chứ không phải gửi lại message càng nhiều càng tốt.
