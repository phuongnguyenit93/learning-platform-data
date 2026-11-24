# Commit sau khi xử lý outbound thành công trong Spring Integration Adapters

> **Chương:** Transactions  
> **Bài học:** Commit sau khi xử lý outbound thành công  
> **Phạm vi:** SPRING_INTEGRATION_ADAPTERS — kết nối hệ thống ngoài với Spring Integration qua inbound/outbound adapter, gateway, poller và MessageChannel; triển khai File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; quản lý hợp đồng message, lỗi, giao dịch và vòng đời kết nối.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa chính xác **commit sau outbound thành công** và biết “thành công” ở lớp nào: dispatch, handler, remote acceptance, durable write, hay kết quả nghiệp vụ cuối cùng.
2. Phân biệt **database transaction commit, JMS session commit, AMQP acknowledgement, Kafka offset commit và producer broker acknowledgement**: chúng không phải một giao dịch thống nhất.
3. Vẽ ranh giới **source receive → outbound operation → confirm → commit/ack source**, nhận diện điều gì xảy ra nếu process chết tại từng thời điểm.
4. Giải thích vì sao đặt outbound call trong một phương thức có **@Transactional** không đồng nghĩa HTTP/SFTP/broker trở thành thành viên của transaction DB.
5. Chọn mô hình thích hợp cho **DirectChannel, ExecutorChannel, QueueChannel, polling consumer, inbound gateway và outbound adapter/gateway**.
6. Dùng **transactional outbox/inbox, idempotency key, reconciliation, state machine, retry bounded, DLQ/parking** để đạt độ tin cậy khi không thể commit nguyên tử qua hệ thống.
7. Thiết kế chính sách commit/ack phù hợp cho **File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC**, tránh mất message hoặc gửi trùng tác dụng phụ.
8. Cấu hình ví dụ Java/Spring Integration ở ranh giới đồng bộ và database/outbox, hiểu điểm phải tích hợp API/container riêng.
9. Đo **outbound success, source ack, uncertain outcome, retry, backlog** riêng biệt; thiết kế kiểm thử có fault injection trước/sau mọi ranh giới commit.

## 2. Vì sao đây là một bài toán giao dịch?

Một luồng phổ biến:

~~~text
Inbound JMS message
    -> validate/transform
    -> HTTP outbound gateway gọi ERP
    -> JDBC cập nhật trạng thái xử lý
    -> xác nhận JMS message
~~~

Nghiệp vụ yêu cầu: chỉ xác nhận message nguồn khi thao tác bắt buộc đã được xử lý hoặc được **bảo toàn bền vững để tiếp tục xử lý**. Nhưng từ “thành công” có thể chỉ các sự kiện khác nhau:

- Handler được gọi mà không ném exception.
- HTTP client đã gửi đủ bytes.
- HTTP server trả 200/201/202.
- Message được một broker tiếp nhận hoặc ghi bền theo cấu hình.
- File đã được tạo ở local/remote nhưng chưa có ready marker.
- Dữ liệu đích đã commit transaction.
- Consumer downstream đã xử lý toàn bộ nghiệp vụ.
- Một outbox record đã được commit và bảo đảm có worker phát sau.

**Không được dùng một tín hiệu thành công ở lớp thấp thay cho cam kết ở lớp cao mà hợp đồng nghiệp vụ yêu cầu.**

### Kịch bản mất message

~~~text
1. JMS consumer nhận order-882
2. Spring Integration dispatch tới ExecutorChannel
3. Sender nhận kết quả send-to-channel thành công
4. Container ack nguồn
5. Process chết trước khi outbound HTTP handler chạy
6. Không còn bản copy bền vững của order-882
~~~

Dispatch thành công trong memory **không có nghĩa outbound thành công**. Nếu source đã ack, message có thể mất.

### Kịch bản xử lý trùng

~~~text
1. JMS consumer nhận order-883
2. HTTP outbound POST tạo order ở ERP thành công
3. Process chết trước JMS commit/ack
4. Broker giao lại order-883
5. HTTP POST được gửi lần nữa
~~~

Nếu ERP không có idempotency/reconciliation, có thể tạo hai đơn hàng. Việc **commit sau outbound thành công** giảm nguy cơ mất message nhưng **không loại bỏ duplicate**.

## 3. Định nghĩa theo nhiều mức “outbound thành công”

| Mức | Tín hiệu | Điều chứng minh | Điều KHÔNG chứng minh |
|---|---|---|---|
| L0 — Dispatch | MessageChannel.send trả về thành công | Message được channel chấp nhận theo semantics của channel | Remote đã nhận hoặc xử lý |
| L1 — Handler | MessageHandler return bình thường | Code handler kết thúc không ném lỗi | Side effect từ hệ thống ngoài đã commit |
| L2 — Transport ack | HTTP response, SFTP command result, broker producer ack/confirm | Một mức tiếp nhận của đích theo giao thức | Consumer cuối cùng hoàn thành nghiệp vụ |
| L3 — Durable acceptance | Outbox/inbox record commit, broker persist theo guarantee | Đã có nơi lưu bền theo hợp đồng | Business effect phía sau hoàn tất |
| L4 — Business completion | ERP order state confirmed, downstream operation committed | Nghiệp vụ đích được xác nhận ở phạm vi contract | Source và đích cùng commit atomically |
| L5 — End-to-end closure | Business completion và source state được ghi/ack đúng | Luồng đạt trạng thái đóng theo tiêu chí | Không thể có delivery lại trong tương lai |

### Ba điều cần phân định trong thiết kế

1. **Commit điều gì?** DB transaction, JMS session, Kafka offset, AMQP ack, file archive, row claim, hay outbox event state.
2. **Đợi xác nhận gì?** Outbound handler return, broker confirm, remote business state hoặc durable outbox.
3. **Lúc process chết, còn bản ghi ở đâu?** Source broker, input file, database inbox, outbox, retry queue, parking hoặc không ở đâu cả.

**Mục tiêu thực dụng:** một message bắt buộc phải luôn ở ít nhất một trạng thái có thể phục hồi cho tới khi đạt completion theo business contract; nếu có delivery trùng, xử lý phải idempotent.

## 4. Vòng đời nguồn → outbound → commit/ack

~~~mermaid
sequenceDiagram
    participant S as Inbound source/container
    participant F as Integration Flow
    participant O as Outbound dependency
    participant C as Commit / acknowledgement
    S->>F: Message eventId=order-882
    F->>F: Validate and resolve operation
    F->>O: Outbound request
    O-->>F: Success theo contract
    F->>F: Persist outcome if required
    F->>C: Commit/ack source theo semantics
    C-->>S: Progress recorded
~~~

Sơ đồ thể hiện **ý định thứ tự**, không khẳng định Spring Integration tự động tạo transaction xuyên hệ thống.

### Một thứ tự an toàn có điều kiện

~~~text
RECEIVED
 -> VALIDATED
 -> OUTBOUND_ATTEMPTED
 -> OUTBOUND_CONFIRMED
 -> LOCAL_STATE_RECORDED
 -> SOURCE_ACKNOWLEDGED
 -> DONE
~~~

Điều kiện: **OUTBOUND_CONFIRMED phải được định nghĩa theo nhu cầu nghiệp vụ** và các bước trung gian có cơ chế idempotency/recovery. Nếu outbound là enqueue vào một **outbox bền**, điều kiện commit source có thể là **DURABLY_ACCEPTED_FOR_PROCESSING**, thay vì đợi hệ thống cuối thực hiện.

### Khác nhau giữa commit source và commit đích

JMS source có thể commit session sau khi outbound HTTP trả success. Nhưng nếu HTTP server đã commit rồi JMS session commit thất bại, hai hệ thống vẫn không đồng bộ về trạng thái. Không có một atomic commit chung trừ khi có cơ chế giao dịch phân tán thực sự bao phủ các tài nguyên liên quan; HTTP API/SFTP thường không tham gia transaction manager của DB/JMS theo cách mặc định.

## 5. “Commit sau thành công” không đồng nghĩa exactly-once

**At-least-once**: message có thể được giao lại để tránh mất; consumer cần chấp nhận duplicate.

**At-most-once**: một số quyết định ack sớm giúp tránh lặp nhưng có thể mất message.

**Effectively-once business effect**: nhiều deliveries/attempts vẫn tạo **một hiệu ứng nghiệp vụ** thông qua idempotency, unique constraint, inbox, dedupe hoặc reconciliation.

### Ma trận crash tối thiểu

| Crash point | Source đã ack? | Outbound đã hoàn tất? | Nguy cơ | Bảo vệ |
|---|---|---|---|---|
| Trước xử lý | Chưa | Chưa | Redelivery | Idempotency/source persistence |
| Sau validate | Chưa | Chưa | Parse/validation lặp lại | Deterministic validation |
| Sau outbound request, chưa nhận response | Chưa | **Không rõ** | Remote có thể commit | Idempotency/reconciliation |
| Sau remote commit, trước ack | Chưa | Có | Duplicate khi redelivery | Stable business key |
| Sau ack, trước outbound completion | Có | Chưa | **Mất tác vụ** | Không ack sớm; durable handoff |
| Sau outbox commit, trước publish | Có thể có | Chưa publish | Outbox backlog | Publisher retry |
| Sau broker confirm, trước outbox mark DONE | Có thể có | Broker đã nhận | Publish trùng | Event ID + dedupe |
| Sau hoàn tất toàn bộ | Có | Có | Audit/metric lỗi phụ | Không chạy lại side effect vì telemetry |

**Không thể giải cả “mất” và “trùng” chỉ bằng việc đổi thứ tự hai lệnh.** Cần durable state và idempotency.

## 6. Transaction boundary trong Spring Integration

Spring Integration kết hợp **MessageChannel, endpoint, handler và transaction manager**. Một transaction có thể gắn vào polling consumer, message-driven adapter hoặc business service, nhưng phạm vi thực tế phụ thuộc:

- **PlatformTransactionManager** và tài nguyên được quản lý;
- Thread đang giữ transaction context;
- Channel đồng bộ hay bất đồng bộ;
- Transaction interceptor/advice chain;
- Container/listener mode;
- Poller and message store semantics;
- Outbound operation có tham gia transaction hay không.

### Transaction không tự “đi theo message”

Trong Spring, transaction thông thường gắn vào **execution context/thread** của transaction manager. Khi đi qua ExecutorChannel hoặc một ranh giới async khác, context không mặc nhiên truyền như một transaction duy nhất.

~~~text
Thread A:
  BEGIN JDBC tx
  -> DirectChannel
     -> JDBC handler cùng datasource/transaction manager
  COMMIT/ROLLBACK

Thread A:
  BEGIN JDBC tx
  -> ExecutorChannel.send(message)
  COMMIT tx A

Thread B:
  -> outbound HTTP/SFTP/JDBC handler chạy sau
  (không mặc nhiên ở trong tx A)
~~~

**DirectChannel** giúp giữ call stack đồng bộ, nhưng không khiến HTTP/SFTP tham gia JDBC transaction. **ExecutorChannel** khiến khoảng hở ack/commit sớm trở nên đặc biệt cần chú ý.

### TransactionScope và “success” trong flow

Một handler return bình thường không tự có nghĩa:

- Transaction manager đã commit thành công.
- Publisher confirm nhận được.
- Remote transaction đã thực hiện.
- ErrorMessage không bị nuốt.
- Message đã lưu bền.
- Request–reply gateway đã nhận response.

Muốn commit source theo outcome, phải kiểm tra **thời điểm hoàn tất thực tế** và đường exception của endpoint/container.

## 7. DirectChannel, ExecutorChannel, QueueChannel: chọn ranh giới cho đúng

| Channel | Khi send thành công | Khi handler lỗi | Độ bền |
|---|---|---|---|
| **DirectChannel** | Handler có thể đã chạy trong caller thread | Exception có thể propagate trực tiếp | Không mặc định |
| **ExecutorChannel** | Work được dispatch vào executor | Lỗi ở worker thread/error flow | Không mặc định |
| **QueueChannel** | Message được enqueue theo cấu hình | Consumer/poller cần failure handling | Phụ thuộc MessageStore/transaction |
| **PublishSubscribeChannel** | Dispatch theo subscribers/config | Lỗi và thành công từng subscriber cần quản lý | Không mặc định |

### DirectChannel phù hợp khi nào?

Khi cần **source consumer chờ outbound handler** trước khi quyết định ack, một flow đồng bộ giúp dễ suy luận thứ tự. Nhưng vẫn cần:

- Timeout per outbound attempt và deadline tổng;
- Chính sách retry/backoff không giữ thread mãi;
- Rõ ngoại lệ nào được ném về container;
- Idempotency khi outbound đã commit nhưng source commit chưa;
- Transaction manager phù hợp với tài nguyên local.

### ExecutorChannel: làm gì nếu buộc phải async?

Không ack nguồn dựa chỉ trên **enqueue in-memory** nếu yêu cầu at-least-once. Thay bằng:

- **Durable handoff**: ghi message/outbox/job store vào transaction có thể xác nhận, rồi ack nguồn theo protocol;
- Hoặc giữ source acknowledgement cho đến khi worker báo **business/durable completion** qua cơ chế coordination được hỗ trợ;
- Dùng error channel và retry record bền;
- Kiểm tra ứng dụng crash, executor rejection, shutdown và backpressure.

### QueueChannel

QueueChannel chỉ bền khi được cấu hình **MessageStore** và transaction/consumer phù hợp. Một QueueChannel in-memory không bảo vệ message qua restart. Nếu consumer đã lấy message khỏi queue rồi lỗi, phải biết message được requeued/rollback hay chuyển parking.

## 8. Outbound adapter và outbound gateway: mức thành công khác nhau

### Outbound adapter: thường one-way

Ví dụ File/SFTP/Kafka/AMQP outbound adapter có thể gửi message mà không tạo một **reply nghiệp vụ**.

Điều handler return có thể chỉ là:

- Đã hoàn thành lời gọi API của client;
- Message đã được submit để gửi async;
- Stream đã được write locally;
- Broker/remote đã ack ở một mức nào đó, **tùy cấu hình**.

**Không mặc nhiên coi return của outbound adapter là final consumer business completion.**

### Outbound gateway: request–reply

HTTP outbound gateway thường gửi request, chờ response và chuyển reply về flow. Nhưng:

- HTTP 202 có thể nghĩa là **Accepted**, chưa hoàn tất job.
- HTTP 200 có thể chỉ xác nhận request theo contract, không phải downstream toàn bộ.
- HTTP timeout không chứng minh đích chưa xử lý.
- Error response có thể đến **sau khi một side effect đã xảy ra**.

Nếu business contract yêu cầu **hoàn tất nghiệp vụ**, gateway có thể cần query trạng thái/final callback chứ không chỉ check status code.

## 9. Tách success của outbound khỏi ack của nguồn

Một thiết kế dễ kiểm thử nên định nghĩa hai quyết định độc lập:

~~~text
isOutboundAcceptedForBusinessContract(result)
canAcknowledgeSource(sourceContext, durableOutcome)
~~~

Ví dụ:

| Outbound operation | Success theo hợp đồng | Có thể ack nguồn ngay? |
|---|---|---|
| JDBC update trong transaction đúng | Transaction commit đã xác nhận | Có khi source ack phối hợp đúng, durable outcome đã đủ |
| HTTP POST tạo order | Kết quả đã đối soát theo order ID | Có nếu business state đã ghi hoặc nguồn được bảo toàn |
| HTTP 202 async job | Job ID đã lưu bền, workflow theo dõi | Có nếu contract cho phép accept-for-processing |
| Kafka publish | Future/producer ack thành công ở mức cấu hình | Tùy yêu cầu: broker acceptance hay consumer completion |
| AMQP publish | Publisher confirm theo chính sách | Tùy yêu cầu; confirm không phải consumer DONE |
| JMS outbound send | Send/commit JMS session theo transaction | Tùy transaction boundaries và broker semantics |
| SFTP upload | File remote được xác nhận/publish theo protocol | Có nếu trạng thái nghiệp vụ yêu cầu đúng mức này |
| File outbound write | File đã publish an toàn theo filesystem | Có nếu file delivery là terminal goal |
| Async ExecutorChannel send | Chỉ enqueue in-memory | **Không**, nếu cần durable outcome |

Câu trả lời “có thể ack” luôn phải gắn với **nguồn cụ thể**, nguồn giữ message ra sao và định nghĩa kết quả nghiệp vụ.

## 10. Poller: transaction và commit khi lấy message định kỳ

Polling consumer nhận message từ MessageSource theo trigger rồi gửi tới handler/channel. Một transaction advice đặt đúng quanh poll operation có thể giúp **transaction của tài nguyên local** quản lý hoạt động lấy/đánh dấu message.

Nhưng:

- Poller schedule **không phải** retry scheduler bền vững.
- Transaction advice chỉ có hiệu lực với tài nguyên transaction manager hỗ trợ.
- Một **File/SFTP poller** không có broker ack giống JMS/Kafka.
- Metadata filter/remote file list/rename có thể nằm ngoài transaction DB.
- Nếu handler downstream async, poll operation có thể kết thúc trước outbound.

### Ví dụ về thứ tự

~~~text
T0 poll row state NEW
T1 claim row -> PROCESSING
T2 route tới HTTP outbound handler
T3 HTTP success (hoặc durable job state)
T4 update row DONE
T5 commit JDBC transaction

Nếu HTTP fail:
    rollback transaction khi cùng đúng transaction boundary
    hoặc cập nhật RETRY_WAIT/PARKED bền theo business policy
~~~

**Không nên giữ transaction DB mở suốt HTTP call chậm nếu tránh được**: tăng lock duration, giảm throughput, khó cân bằng SLA. Thường ưu tiên claim/lease + durable state + outbound worker riêng.

### Transaction synchronization và resource lifecycle

Spring Integration cung cấp cơ chế **transaction synchronization** trong bối cảnh polling/adapters phù hợp, có thể hỗ trợ hành động gắn với trạng thái transaction như xử lý/di chuyển resource khi commit/rollback. Nhưng cần nhớ:

- Callback sau commit chạy theo lifecycle local transaction, không khiến SFTP rename hoặc HTTP call **trở thành atomic participant**.
- Nếu hành động hậu commit thất bại, DB commit trước **không bị rollback theo cách thông thường**.
- Phải có recovery, retry/idempotency, audit cho hành động sau commit.
- Tên API và config phụ thuộc phiên bản Spring Integration; cần kiểm tra module/reference tương ứng khi triển khai.

Không dùng transaction synchronization như một phép màu biến file move và JDBC commit thành một giao dịch phân tán duy nhất.

## 11. Tại sao @Transactional không đủ cho HTTP/SFTP?

Ví dụ minh họa một phương thức:

~~~java
@Transactional
public void process(OrderMessage order) {
    orderRepository.save(order);
    httpClient.createErpOrder(order);
}
~~~

Nếu HTTP đã tạo order rồi database transaction rollback, remote order **không tự bị xóa**. Nếu database commit trước HTTP hoặc HTTP timeout sau remote commit, hệ thống vẫn có những trạng thái không đồng bộ.

### Hai thứ tự, hai loại lỗi

~~~text
A. DB first:
    BEGIN DB
    INSERT order
    COMMIT DB
    HTTP POST ERP   <-- có thể fail
    => local DONE nhưng remote chưa có order

B. HTTP first:
    HTTP POST ERP success
    BEGIN DB
    INSERT status
    COMMIT DB       <-- có thể fail
    => remote có order, local chưa ghi kết quả
~~~

Không chỉ thay thứ tự rồi gọi là “atomic”. Cần:

- State machine theo bước;
- Inbox/outbox tùy hướng;
- Stable idempotency key;
- Remote query/reconciliation;
- Retry đúng bước;
- Compensation nếu nghiệp vụ cho phép và thực sự thực hiện được.

**SAGA/compensation** không đồng nghĩa rollback ACID. Compensation có thể thất bại, không thể đảo ngược mọi tác dụng phụ như email hoặc chuyển tiền đã settlement.

## 12. Commit sau outbound thành công: hai chiến lược thực tế

### Chiến lược A — synchronous completion trước source ack

~~~text
Receive source message
    -> outbound handler đồng bộ
    -> nhận thành công theo contract
    -> ghi local state
    -> ack/commit source
~~~

Phù hợp khi:

- Outbound latency dự đoán được và còn deadline;
- Source container cho phép giữ delivery trong processing;
- Thread/prefetch/consumer concurrency đủ;
- Có idempotency khi source redelivery;
- Không đòi atomic transaction xuyên remote;
- Exception propagate đúng cho source khi thất bại.

Giới hạn: giữ source worker lâu, HTTP response mất tạo outcome unknown, source commit có thể lỗi sau remote success.

### Chiến lược B — durable acceptance trước source ack

~~~text
Receive source message
    -> validate
    -> persist inbox/job/outbox in local durable store
    -> confirm durable commit
    -> ack/commit source
    -> async outbound worker sends
    -> persist success / retry / unknown state
~~~

Phù hợp khi:

- Outbound chậm/bất ổn;
- Cần survive restart;
- Có nhiều đích/broker;
- Source có timeout/consumer limits;
- Muốn kiểm soát retry qua phút/giờ;
- Có đủ storage, worker và monitoring.

**Quan trọng:** Chiến lược B không “ack sau outbound remote thành công”. Nó ack **sau khi cam kết lưu bền tác vụ phải thực hiện**. Đây có thể là một thiết kế đáp ứng yêu cầu độ tin cậy tốt hơn, nếu business contract cho phép.

## 13. Tổng quan trạng thái xử lý và kết quả terminal

~~~mermaid
flowchart TD
    A["RECEIVED"] --> V["VALIDATED"]
    V -->|"Invalid"| Q["INVALID / QUARANTINED"]
    V --> J["DURABLE_PENDING"]
    J --> O["OUTBOUND_ATTEMPT"]
    O -->|"Confirmed"| C["OUTBOUND_CONFIRMED"]
    O -->|"Retryable"| R["RETRY_WAIT"]
    R --> O
    O -->|"Outcome unknown"| U["OUTCOME_UNKNOWN"]
    U --> X["RECONCILE"]
    X -->|"Confirmed"| C
    X -->|"Not processed, safe retry"| R
    X -->|"Unresolved"| P["PARKED"]
    O -->|"Permanent"| Q
    C --> D["DONE"]
    D --> S["ACK / COMMIT source per contract"]
    J -.->|"Durable handoff policy"| S
~~~

Các trạng thái là **domain state** do ứng dụng định nghĩa, không phải enum mặc định của Spring Integration. Thời điểm ack/commit tùy chiến lược A/B và khả năng nguồn, không bắt buộc sau DONE trong mọi flow.

| Trạng thái | Ý nghĩa | Có thể xóa bản sao nguồn? |
|---|---|---|
| RECEIVED | Mới nhận, chưa bảo toàn | Không |
| VALIDATED | Dữ liệu hợp lệ | Chưa đủ |
| DURABLE_PENDING | Công việc được lưu bền và có worker phục hồi | Có thể theo chiến lược B và source contract |
| OUTBOUND_ATTEMPT | Đang gọi đích | Không suy ra thành công |
| OUTBOUND_CONFIRMED | Mức thành công đã kiểm chứng | Cần lưu state/ack chính xác |
| RETRY_WAIT | Cần thử lại theo lịch bền | Có thể nếu message đã lưu bền |
| OUTCOME_UNKNOWN | Không rõ đích đã commit | Không bỏ; phải reconcile |
| PARKED | Lưu để điều tra, còn khả năng replay | Có thể khi parking bền và được phê duyệt |
| DONE | Nghiệp vụ terminal hoàn tất | Có thể ack/cleanup theo hợp đồng |
| INVALID/QUARANTINED | Không thể xử lý dữ liệu hiện tại | Chỉ cleanup nguồn khi quarantine bền và hợp đồng cho phép |

## 14. HTTP outbound: response không nhất thiết là business commit

HTTP là giao thức request–response, không tham gia trực tiếp transaction của database nội bộ theo cách thông thường.

| Tín hiệu | Ý nghĩa có thể có | Quyết định xử lý |
|---|---|---|
| 200 OK | API trả thành công theo contract | Kiểm response/business state |
| 201 Created | Resource được tạo theo semantics API | Lưu remote ID và idempotency key |
| 202 Accepted | Request được nhận để xử lý sau | Lưu job ID, theo dõi completion |
| 204 No Content | Thành công không có body | Chỉ coi là DONE khi contract cho phép |
| 409 Conflict | Có thể duplicate hoặc conflict | Đối soát business key/version |
| 429/503 | Giới hạn tốc độ hoặc đang lỗi | Backoff/rate limit/durable retry |
| 400/401/403 | Invalid input/auth/permission | Sửa dữ liệu hoặc quyền, không retry mù |
| Connect timeout | Kết nối có thể chưa được thiết lập | Retry có điều kiện |
| Read timeout sau POST | Server có thể đã commit | OUTCOME_UNKNOWN, query/idempotency |

**HTTP 200 không tự chứng minh** mọi workflow async ở đích đã hoàn tất; contract API quyết định nghĩa của response.

### POST timeout sau remote commit

~~~mermaid
sequenceDiagram
    participant S as Inbound source
    participant I as Integration handler
    participant E as ERP
    participant D as ERP DB
    S->>I: Order event-882
    I->>E: POST + Idempotency-Key=event-882
    E->>D: Commit order
    D-->>E: OK
    Note over E,I: Response lost
    I-->>S: Handler uncertain or failed
    S->>I: Redelivery event-882
    I->>E: Query status / retry same key if supported
    E-->>I: Existing confirmed result
    I->>S: Ack after local business contract met
~~~

Nếu ERP không hỗ trợ idempotency/query, cần trạng thái OUTCOME_UNKNOWN và đối soát trước khi gửi lại một POST có side effect. **Không tăng số lần retry mù để giải quyết unknown outcome.**

### Khi nào commit nguồn sau HTTP?

Chỉ khi đã xác minh:

1. HTTP response theo **business contract**, không đơn giản là client return.
2. Event ID/remote ID và state được lưu hoặc có cơ chế phục hồi.
3. Không có nghĩa vụ xử lý bắt buộc chưa được bảo toàn.
4. Source container hỗ trợ ack/commit tại thời điểm ấy.
5. Nếu crash trước source commit, idempotency ngăn duplicate.

Với HTTP inbound gateway, commit nguồn không phải broker ack; ứng dụng thường trả reply hoặc 202 acceptance với **job ID + durable job record** khi xử lý sau.

## 15. JMS inbound → outbound: session commit sau handler

JMS listener có thể dùng transacted session hoặc acknowledgement mode khác. Khi container nhận message, nó có thể gọi flow đồng bộ rồi commit session sau khi handler hoàn tất thành công; nếu handler ném lỗi với cấu hình transaction phù hợp, container rollback và broker redeliver.

~~~text
JMS broker
  -> transacted listener/container
  -> Spring Integration message
  -> DirectChannel
  -> outbound handler
       success -> container commit JMS session
       failure -> exception propagated -> rollback/redelivery
~~~

**Đây là topology tham chiếu.** Kết quả phụ thuộc container factory, transaction manager, session mode, message-driven adapter, error flow và cách handler kết thúc. Không phải mọi JMS inbound có rollback/redelivery như nhau.

### Các loại transaction

- **JMS local transaction** quản lý nhận/gửi trong JMS session theo cấu hình hỗ trợ.
- **JDBC local transaction** quản lý database của transaction manager tương ứng.
- Nếu chỉ là hai local transactions riêng, commit không atomic.
- **JTA/XA** có thể phối hợp những resource managers thực sự hỗ trợ giao dịch phân tán khi môi trường được cấu hình đúng; cần cân nhắc recovery và vận hành. **HTTP/SFTP không tự trở thành XA participants.**
- Error flow hoặc RecoveryCallback **nuốt exception** có thể khiến container coi message đã xử lý, dù outbound chưa hoàn tất.

### Điểm kiểm tra

| Tình huống | Cần xác minh |
|---|---|
| Handler return bình thường | Container ack/commit theo mode nào? |
| Handler ném MessagingException | Exception có tới container hay bị chặn? |
| JMS rollback | Broker redeliver/DLQ theo policy nào? |
| Commit JMS thất bại sau HTTP success | Idempotency remote có ngăn duplicate? |
| Gửi JMS outbound cùng session | Có cùng transaction manager/session thực không? |
| DB commit rồi JMS commit lỗi | Có inbox/outbox hoặc reconciliation? |

Với HTTP call chậm, lựa chọn **JMS → durable inbox/outbox → ack JMS → outbound worker** thường giúp không giữ source transaction lâu. Tuy nhiên ack sau DB commit vẫn có crash window; inbox dedupe giúp redelivery an toàn.

## 16. AMQP inbound: consumer ack khác publisher confirm

Với AMQP/RabbitMQ:

- **Consumer ack:** xác nhận một delivery đầu vào theo container mode.
- **Consumer nack/reject/requeue:** từ chối, có thể broker redeliver hoặc dead-letter tùy cấu hình.
- **Publisher confirm:** broker xác nhận một publish theo guarantee/config.
- **Business completion:** consumer cuối đã áp dụng side effect và commit nghiệp vụ.

**Publisher confirm không đồng nghĩa business completion.**

### Mô hình publish

~~~text
AMQP source delivery
  -> validate + normalize
  -> outbound publish
  -> observe broker confirm as required
  -> durable local outcome
  -> ack source
~~~

Nếu client dùng async callback/future, một lời gọi gửi không ném lỗi **chưa chắc** publisher confirm đã đến. Không ack nguồn dựa trên assumption nếu contract đòi broker acceptance.

### Crash window

~~~text
1. Outbound publish đã tới broker đích.
2. Process chết trước ack nguồn AMQP.
3. Broker nguồn redeliver.
4. Publish lại cùng event.
~~~

Giải pháp: stable event ID, outbox/inbox và consumer dedupe. Gửi broker B và ack broker A **không tự là giao dịch nguyên tử**.

### Phân loại lỗi

- Transient: bounded retry/backoff hoặc delayed queue.
- Invalid: quarantine/DLQ; tránh requeue nóng vô hạn.
- Unknown outcome: reconciliation/parking.
- Duplicate đã xác minh DONE: no-op/ack có chủ đích.

Nếu handler có bốn attempts mỗi delivery và broker redeliver tổng ba lần, có thể có **12 handler invocations**. Retry count của một invocation không phải tổng delivery count.

## 17. Kafka inbound: offset commit sau mốc bảo đảm thích hợp

**Kafka offset commit** chỉ ghi tiến độ đọc của consumer group. Nó không phải commit của outbound HTTP/JDBC và không chứng minh remote đã xử lý xong.

| Tầng | Vai trò |
|---|---|
| Kafka consumer/client | Poll, heartbeat, partitions, offsets |
| Kafka listener container | Ack mode, error handler, seek/retry/DLT |
| Spring Integration inbound adapter | Chuyển record thành Spring Message |
| MessageChannel + handler | Route/transform/process |
| Producer/outbound adapter | Publish hoặc gọi hệ thống ngoài |
| Business database | Lưu trạng thái nghiệp vụ |
| Inbox/outbox | Durable handoff/dedupe |

### Offset và outbound

~~~text
offset 100: invoice.created
offset 101: invoice.updated
offset 102: invoice.cancelled
~~~

Nếu offset 100 được gửi vào ExecutorChannel rồi listener/offset commit trước khi handler thực sự gọi HTTP, crash có thể làm mất tác vụ. Cách xử lý:

- **Synchronous processing** nếu latency và poll constraints cho phép; ack theo success.
- **Durable handoff** vào inbox/outbox/job store rồi commit offset.
- **Container error handler/retry topology/DLT** theo config khi outbound fail.

### Kafka transaction không bao trùm mọi adapter

Kafka transactional producer/consumer có thể hỗ trợ read-process-write trong phạm vi Kafka transaction được quản lý. Điều đó **không tự bao gồm** HTTP POST, SFTP upload, AMQP hoặc DB transaction riêng.

### Ordering

Nếu offset 100 đang retry HTTP còn 101 được xử lý nhanh ở nhánh khác, ordering nghiệp vụ có thể bị đảo. Cần partition/key strategy, xử lý tuần tự, aggregate-version guard hoặc orchestration. Retry topic/DLT cũng có thể đổi ordering.

### Producer async

Khi handler chỉ submit send cho producer rồi return, offset commit có thể sớm hơn broker acknowledgement. Phải theo dõi **future/callback completion** theo API/version và contract, hoặc chọn outbox để ack nguồn tại mốc **durable acceptance**.

## 18. JDBC inbound/outbound: database commit và worker lease

### JDBC outbound trong cùng database transaction

Nếu toàn bộ side effects bắt buộc nằm trong **một database và được quản lý bởi cùng transaction manager**, chúng có thể được commit atomically:

~~~text
BEGIN JDBC transaction
  validate rows
  UPDATE order_state
  INSERT processed_events(eventId)
  INSERT outbox_events(eventId, target, state=PENDING)
COMMIT JDBC transaction
~~~

Nếu transaction rollback, các cập nhật DB đó chưa commit. Nhưng một HTTP/SFTP call được đặt trong block **không tự rollback**.

### JDBC inbound polling

Một poller có thể lấy row trạng thái NEW và claim:

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  +-> RETRY_WAIT -> PROCESSING
                  |
                  +-> OUTCOME_UNKNOWN
                  |
                  +-> PARKED
~~~

Cần:

- Atomic claim với transaction/row lock/lease theo DB;
- Worker owner, lease expiry;
- Durable attemptCount và nextAttemptAt;
- Stable businessEventId và unique constraint;
- Business deadline;
- Manual reconciliation;
- Không mark DONE trước business outcome được bảo đảm.

### Vì sao không giữ DB transaction mở quanh HTTP call chậm?

Lock duration dài, throughput giảm và dễ timeout/deadlock. Nếu HTTP đã commit nhưng JDBC commit fail, vẫn cần reconciliation. Thường nên **tách transaction lưu ý định** khỏi worker thực hiện HTTP, dùng outbox/job state.

### Retry deadlock

Transaction bị deadlock hoặc rollback-only phải được rollback rồi mở transaction mới cho retry. Không retry cả workflow khiến HTTP đã thành công được gọi lại.

## 19. File inbound: commit khác broker acknowledgement

File inbound adapter và poller **không có cùng cơ chế consumer ack** như JMS/Kafka. “Xác nhận” thường là file metadata, rename/move/archive/delete hoặc business state store do ứng dụng định nghĩa.

### Rủi ro archive quá sớm

~~~text
1. Poller thấy invoice-882.ready.
2. Ứng dụng move file sang /processed.
3. HTTP outbound gửi ERP rồi thất bại.
4. File không còn trong inbound directory.
5. Không có durable retry record.
~~~

Dù file vẫn có thể ở archive, **lần poll sau không tự nhận lại**. Nếu archive được xem là DONE, nhiệm vụ có thể bị bỏ sót.

### Quy trình tham khảo

1. Chỉ lấy file đã publish hoàn chỉnh (.ready/manifest).
2. Kiểm checksum, schema, kích thước; tạo stable event ID.
3. Stage file ở nơi có thể phục hồi và tạo inbox/job record.
4. Thực hiện outbound đồng bộ hoặc qua worker.
5. Nếu DONE thì archive; nếu fail thì RETRY_WAIT/PARKED/quarantine.
6. Nếu file move sau DB commit lỗi, cần reconciliation/retry riêng.
7. Không xóa nguồn trước khi biết đã có ít nhất một bản lưu đảm bảo xử lý tiếp.

### Transaction synchronization với File

Spring Integration có các cơ chế **transaction synchronization** cho những flow/polling situations phù hợp, có thể thực thi hành động liên quan commit/rollback. Nhưng file rename/move **không là atomic participant của database transaction**.

Nếu DB commit rồi action hậu commit lỗi, không thể rollback DB commit theo cách thông thường. Cần persistent state, retry, idempotency và operational runbook.

### Accept-once filter

Accept-once/metadata filter giúp hạn chế chọn file trùng theo trạng thái adapter; nó không phải cờ business DONE. Nếu filter đã ghi nhận trước outbound failure, cần reset/recovery có kiểm soát hoặc replay từ job store.

## 20. SFTP inbound/outbound: remote outcome có thể mơ hồ

### SFTP inbound

Một SFTP poller có thể list/download rồi tạo message. Những điều **không** được suy ra:

- Download về local = downstream business DONE.
- Remote accept-once filter = giao dịch đã commit.
- Remote rename/delete = đã commit chung với DB/broker.
- Session reconnect = source broker sẽ redeliver như JMS.

Cần staging, stable file/record keys, checksum, metadata store và job state.

### SFTP outbound upload

~~~text
Render file
  -> upload remote temp name
  -> verify size/checksum/manifest if available
  -> remote rename/publish final name
  -> record OUTBOUND_CONFIRMED
  -> source ack/archive according to contract
~~~

Nếu remote rename/upload đã thành công nhưng response mất, outcome chưa rõ. Trước retry, **query remote file status** theo stable filename/checksum, không overwrite vô điều kiện.

Remote rename có thể atomic theo filesystem/protocol cụ thể, nhưng **rename SFTP và commit nguồn DB/JMS không tự là một giao dịch nguyên tử**.

### Khi không thể xác minh remote

- Đưa event vào OUTCOME_UNKNOWN/PARKED;
- Giữ source hoặc durable job;
- Không tự xóa file khi còn obligation;
- Manual reconciliation hoặc retry với idempotency guard nếu contract cho phép;
- Ghi correlation ID thay vì credential;
- Không bỏ qua host-key verification để tránh lỗi.

## 21. Một outbound event có nhiều recipients: commit điều gì?

Một hóa đơn phải tới:

1. HTTP ERP;
2. Kafka analytics;
3. SFTP audit export.

Nếu HTTP/Kafka thành công nhưng SFTP thất bại, có thể ack source không?

**Không có câu trả lời chung.** Completion policy quyết định:

- **All required recipients confirmed:** chỉ DONE khi tất cả recipients bắt buộc đạt mức success đã định nghĩa.
- **Durable fan-out accepted:** ack nguồn sau khi mọi recipient jobs được lưu bền; các worker xử lý sau.
- **Optional best-effort:** bỏ nhánh không bắt buộc chỉ khi business policy cho phép và có audit.
- **Any-one success:** chỉ nếu các đích thay thế nhau theo hợp đồng thật.

### Per-recipient state

~~~json
{
  "businessEventId": "tenant-A:invoice-882:v3",
  "requiredDestinations": [
    "ERP_HTTP",
    "ANALYTICS_KAFKA",
    "AUDIT_SFTP"
  ],
  "recipients": {
    "ERP_HTTP": "DONE",
    "ANALYTICS_KAFKA": "DONE",
    "AUDIT_SFTP": "RETRY_WAIT"
  },
  "overallState": "PARTIALLY_DELIVERED"
}
~~~

Retry toàn fan-out có thể gửi lại HTTP/Kafka và tạo duplicate. Lưu **per-recipient status**; chỉ retry recipient chưa DONE với stable event ID và pinned route policy.

**Không dùng một boolean outboundSuccessful cho workflow nhiều đích.** Nó không diễn đạt PARTIALLY_DELIVERED, OUTCOME_UNKNOWN, OPTIONAL_FAILED hoặc RETRY_WAIT.

## 22. Transactional outbox: commit durable handoff trước khi ack nguồn

**Transactional outbox** giải quyết bài toán: phải thay đổi dữ liệu local và bảo đảm một message cuối cùng sẽ được phát, nhưng không có transaction atomic giữa database và HTTP/SFTP/broker.

~~~mermaid
sequenceDiagram
    participant C as Inbound consumer
    participant DB as Local DB
    participant W as Outbox worker
    participant O as Outbound destination
    C->>DB: BEGIN transaction
    C->>DB: Write inbox, business state, outbox(PENDING)
    DB-->>C: COMMIT successful
    C->>C: Ack source per container contract
    W->>DB: Claim outbox job with lease
    W->>O: Send + stable idempotency key
    O-->>W: Confirm per protocol/contract
    W->>DB: Mark outbox DONE
~~~

### Điều được bảo đảm và điều chưa được bảo đảm

- **Ack nguồn xảy ra sau database commit** của durable inbox/outbox, không nhất thiết sau remote business completion.
- Outbox worker có thể khôi phục sau restart.
- Nếu remote đã làm xong nhưng worker chết trước khi mark DONE, job có thể được gửi lại → cần idempotency/reconciliation.
- Nếu nguồn commit thất bại sau DB commit, broker có thể redeliver; inbox unique key bảo vệ duplicate.
- Database transaction chỉ atomic với các tài nguyên **tham gia cùng transaction**.

### Ví dụ schema cho PostgreSQL

~~~sql
CREATE TABLE inbox (
    event_id VARCHAR(180) PRIMARY KEY,
    payload_hash VARCHAR(128) NOT NULL,
    state VARCHAR(32) NOT NULL,
    accepted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(180) NOT NULL,
    destination_alias VARCHAR(120) NOT NULL,
    payload_bytes BYTEA NOT NULL,
    state VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    lease_owner VARCHAR(120),
    lease_until TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (event_id, destination_alias)
);
~~~

BIGSERIAL/BYTEA và cú pháp UPSERT dưới đây **phụ thuộc PostgreSQL**. Nếu một event cần nhiều operations đến cùng destination, unique key phải bổ sung operation/version/recipient identity; không dùng constraint quá rộng làm mất event hợp lệ.

### Trách nhiệm của database state

- **Inbox** giúp dedupe nguồn redelivery.
- **Outbox** bảo toàn ý định gửi.
- **Lease/nextAttemptAt** giúp workers phục hồi job sau crash.
- **Unique business/recipient key** tránh sinh duplicate jobs.
- **Retention** không xóa pending/retry chưa hoàn tất.
- **Encryption/ACL** bảo vệ payload hoặc payload reference.

## 23. Java: cùng transaction ghi inbox và outbox

Ví dụ dùng Spring Framework JdbcTemplate với @Transactional:

~~~java
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InboundAcceptanceService {

    private final JdbcTemplate jdbc;

    public InboundAcceptanceService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void accept(CanonicalEvent event) {
        int inserted = jdbc.update(
            """
            INSERT INTO inbox(event_id, payload_hash, state)
            VALUES (?, ?, 'ACCEPTED')
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId(), event.payloadHash()
        );

        if (inserted == 0) {
            String previousHash = jdbc.queryForObject(
                "SELECT payload_hash FROM inbox WHERE event_id = ?",
                String.class,
                event.eventId()
            );
            if (!Objects.equals(previousHash, event.payloadHash())) {
                throw new IllegalStateException(
                    "Same eventId but conflicting content");
            }
            return; // duplicate đã được nhận trước đó
        }

        jdbc.update(
            """
            INSERT INTO outbox(
                event_id, destination_alias, payload_bytes, state)
            VALUES (?, ?, ?, 'PENDING')
            """,
            event.eventId(),
            event.destinationAlias(),
            event.payloadBytes()
        );
    }

    public record CanonicalEvent(
            String eventId,
            String payloadHash,
            String destinationAlias,
            byte[] payloadBytes) {
    }
}
~~~

### Diễn giải commit boundary

- Nếu @Transactional được gọi qua Spring proxy và transaction manager đúng với DataSource, cả hai INSERT cùng một JDBC transaction.
- Nếu INSERT outbox thất bại, transaction rollback bao gồm INSERT inbox.
- Duplicate eventId/hash có thể được coi là đã accepted, **nhưng** production cần xác nhận record cũ có state/outbox hợp lệ và có thể repair tình huống không nhất quán.
- Cùng eventId nhưng khác payload hash là conflict phải điều tra, không dedupe như bản sao hợp lệ.
- Trước phương thức này phải validate tenant, schema, destinationAlias và payload.
- Nhiều recipients cần ghi các outbox records tương ứng trong một transaction, không chỉ một như mẫu.
- Mẫu sử dụng Java text blocks và PostgreSQL syntax; cần Java/dependency versions phù hợp.

### Gắn vào Spring Integration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class DurableIngressFlow {

    @Bean
    IntegrationFlow acceptIngress(InboundAcceptanceService acceptance) {
        return IntegrationFlow.from("validatedInboundEvents")
            .handle(acceptance, "accept")
            .get();
    }
}
~~~

Flow này không tự quản lý **JMS/AMQP acknowledgement hoặc Kafka offset commit**. Consumer/container phải được cấu hình sao cho chỉ khi **local database transaction commit thành công** mới xác nhận nguồn theo durable-acceptance contract.

### Cảnh báo thực tế

- Self-invocation không đi qua @Transactional proxy khi dùng proxy-based transactions thông thường.
- ExecutorChannel không tự mang transaction context qua worker thread.
- Transaction manager dùng nhầm datasource có thể làm DB write ngoài transaction mong muốn.
- Nếu bắt exception DB rồi return bình thường, container có thể ack dù không có outbox.
- Không lưu plaintext credentials/secret trong payloadBytes.

## 24. Outbox worker: send rồi mới đánh dấu DONE

Publisher chạy tách khỏi inbound listener, lấy outbox rows PENDING/RETRY_WAIT đã đến lịch.

~~~text
Transaction 1 — Claim:
    select eligible jobs
    -> lease job / state IN_PROGRESS
    -> COMMIT DB

Outside DB transaction — Outbound:
    send HTTP/SFTP/JMS/AMQP/Kafka
    -> wait/observe confirmation required by business contract

Transaction 2 — Finalize:
    if confirmed -> mark DONE and remote reference
    if retryable -> increment attempts, RETRY_WAIT, nextAttemptAt
    if unknown -> OUTCOME_UNKNOWN, schedule reconciliation
    if permanent -> INVALID/PARKED with reason and owner
    -> COMMIT DB
~~~

### Vì sao claim phải ngắn?

Không nên giữ database transaction/row locks suốt một HTTP call chậm. Điều đó có thể giảm throughput, tăng contention và làm transaction timeout. **Claim bằng lease trong một transaction ngắn**, sau đó xử lý network độc lập, là mô hình có thể khôi phục qua restart.

### Nhiều workers cùng poll

Dùng row locks/atomic UPDATE/lease theo khả năng database (ví dụ SELECT FOR UPDATE SKIP LOCKED ở DB hỗ trợ) để tránh hai worker cùng xử lý một job. Không chỉ SELECT PENDING rồi gửi ngay mà không claim.

### Crash window

| Crash point | Durable state | Recovery |
|---|---|---|
| Trước claim | PENDING | Worker khác claim |
| Sau claim trước send | IN_PROGRESS + lease | Lease expires → re-drive |
| Sau remote success trước DONE | Vẫn IN_PROGRESS hoặc UNKNOWN | Query/idempotency, có thể duplicate attempt |
| Sau DONE commit | DONE | Không gửi lại recipient đã hoàn tất |
| Trong cập nhật retry state | Tùy DB commit | Re-evaluate theo durable state |

**Outbox không bảo đảm exactly-once HTTP/SFTP delivery**. Nó bảo toàn ý định gửi và cho phép at-least-once attempts; cần idempotency/reconciliation để có một business effect.

## 25. Outcome unknown: có thể đã thành công dù không có ACK

Những lỗi mơ hồ thường gặp:

- HTTP POST đã commit nhưng client read timeout.
- SFTP rename hoàn tất nhưng connection mất trước response.
- AMQP publish broker đã nhận nhưng publisher confirm mất.
- Kafka record đã tới broker nhưng process chết trước callback.
- JDBC commit server đã ghi bền nhưng client mất connection khi chờ result.
- JMS send/commit bị gián đoạn mạng.

### Quy trình phân loại

~~~text
OUTBOUND_ATTEMPT
    |
    +-- confirmed failure before side effect -> RETRY_WAIT
    |
    +-- confirmed success per contract -> OUTBOUND_CONFIRMED
    |
    +-- uncertain outcome -> OUTCOME_UNKNOWN
                                |
                                +-> query remote status
                                +-> confirmed -> DONE
                                +-> confirmed not processed -> safe retry
                                +-> still unknown -> PARKED/triage
~~~

Không phân loại mọi timeout là chưa có tác dụng phụ. Mỗi protocol và business operation phải có **outcome reconciliation contract**.

### Event identity

~~~json
{
  "businessEventId": "tenant-17:order-882:v3",
  "destinationAlias": "billing-erp",
  "idempotencyKey": "tenant-17:order-882:v3",
  "operation": "order.upsert",
  "lastAttempt": 4,
  "lastOutcome": "UNKNOWN",
  "reconciliationState": "QUERY_REMOTE",
  "deadlineAt": "2026-11-24T00:00:00Z"
}
~~~

Idempotency key chỉ có tác dụng nếu **partner hỗ trợ** theo contract. Đặt header tên Idempotency-Key không thể tự ép một API không hỗ trợ trở nên idempotent.

## 26. Retry, BackOffPolicy và RequestHandlerRetryAdvice

| Cơ chế | Chức năng | Cẩn trọng |
|---|---|---|
| RetryTemplate/RetryPolicy | Chọn exception và maxAttempts | Không retry invalid/auth mù |
| BackOffPolicy | Chọn khoảng chờ giữa attempts | Không thay timeout/deadline |
| RequestHandlerRetryAdvice | Retry invocation của handler được gắn | Không retry cả flow trừ khi handler quá rộng |
| Broker redelivery | Source giao message lại | Nhân attempts lồng nhau |
| Durable delayed retry | Retry qua DB/queue sau một khoảng | Cần lease, idempotency |
| RecoveryCallback | Xử lý khi exhausted | Return success có thể khiến ack |
| Circuit breaker/bulkhead | Cô lập dependency down | Không thay durable recovery |

### Anti-pattern nuốt exception

~~~java
// Ví dụ mô tả; không phải code đầy đủ độc lập.
advice.setRecoveryCallback(context -> {
    log.error("Remote failed", context.getLastThrowable());
    return null; // Có thể bị coi handler thành công.
});
~~~

Nếu container chỉ nhìn thấy handler return bình thường, có thể ack/commit nguồn **trước khi message được bảo toàn**.

Nên propagate terminal failure tới container khi source cần rollback/redelivery, hoặc **ghi PARKED/DLQ/durable retry thành công** trước khi cho source hoàn tất theo contract.

### Nhiều tầng retry

~~~text
Broker deliveries: 5
  -> handler advice attempts: 4
      -> HTTP client attempts: 2
~~~

Có thể tới **5 × 4 × 2 = 40 HTTP requests** cho một business event trong tình huống xấu nhất. Đặt retry budget tổng, timeout từng attempt, business deadline và stable event ID. Không xem maxAttempts của một handler là tổng số attempts xuyên mọi tầng.

## 27. Transaction synchronization không thay distributed commit

Spring Integration có transaction-aware polling/advice và transaction synchronization trong những bối cảnh phù hợp. Có thể dùng để phối hợp:

- Move/rename file khi local DB transaction thành công;
- Đánh thức outbox publisher sau commit;
- Ghi telemetry hậu commit;
- Xử lý resource riêng khi rollback.

### Thứ tự minh họa

~~~text
BEGIN DB transaction
   INSERT inbox and outbox
COMMIT DB transaction
   afterCommit callback: trigger publisher or move file
~~~

**After-commit callback thất bại không làm local DB đã commit tự rollback.** Nếu chỉ dựa vào callback để publish, process crash sau DB commit nhưng trước callback có thể bỏ mất outbound event.

### Thiết kế vững hơn

1. Ghi **durable outbox row trước commit**.
2. After-commit có thể đánh thức worker cho nhanh.
3. Polling outbox/recovery phải hoạt động ngay cả khi callback không chạy.
4. File move/rename có retry/reconciliation riêng.
5. Không xem afterCommit là giao dịch nguyên tử giữa JDBC và HTTP/SFTP.

### XA/JTA và 2PC

Khi các resource managers có khả năng tham gia JTA/XA và hệ thống cấu hình transaction coordinator đúng, một số giao dịch JMS/DB có thể commit atomically trong **phạm vi resource tham gia**. Nhưng:

- Vận hành recovery/heuristic outcomes phức tạp;
- Timeout, hiệu năng và provider support cần được kiểm chứng;
- HTTP/SFTP và nhiều external APIs **không phải XA participants**;
- Business completion ở bên ngoài vẫn có thể cần reconciliation.

**Outbox/inbox thường thực dụng hơn cho đa protocol**, nhưng phải chấp nhận at-least-once và chống duplicate.

## 28. Bảo mật, privacy và độ tin cậy của thông điệp giao dịch

- Không log bearer token, password, SFTP private key hoặc broker credentials.
- Nếu inbox/outbox giữ payload có PII, cần encryption, ACL và retention.
- Dùng payload reference và metadata đã redact trong error logs.
- Idempotency keys phải ổn định, không làm rò secret.
- Kiểm tenant và destinationAlias trước outbound operation.
- Reconciliation endpoint cần quyền tối thiểu và rate limiting.
- Lọc headers khi bridge HTTP/JMS/Kafka, không phát tán Authorization/cookies.
- DLQ/parking phải có quyền truy cập và chính sách lưu trữ giống dữ liệu nghiệp vụ quan trọng.
- Không cleanup bản sao nguồn trước khi completion hoặc durable recovery bảo đảm đủ.
- OUTCOME_UNKNOWN phải có owner, deadline, alert và cách đóng/cancel hợp lệ; không chờ vô hạn.

### Quy trình quản trị

Với các operation tài chính hoặc compliance-critical, thay đổi điều kiện DONE/source ack phải có review và regression test. Không sửa error handler để nuốt exception nhằm làm dashboard 0 lỗi; đó có thể tạo silent data loss.

## 29. Observability: đo commit, ack và outbound riêng biệt

Một dashboard chỉ đếm “handler không ném exception” chưa thể chứng minh commit đúng. Cần phân biệt **nhận nguồn**, **chấp nhận bền**, **gửi outbound**, **xác nhận broker/remote**, **commit nguồn** và **business DONE**.

| Metric | Định nghĩa | Mục đích |
|---|---|---|
| **inbound_received_total** | Tổng source deliveries theo adapter | So với business events |
| **durable_acceptance_total** | Số events/jobs đã commit vào inbox/outbox | Kiểm durable handoff |
| **source_ack_total** | Số source acks/commits đã xác nhận | Phát hiện ack sớm |
| **source_ack_failures_total** | Số lần ack/commit lỗi | Dự đoán redelivery |
| **outbound_attempts_total** | Tổng operation invocations | Đo retry load |
| **outbound_transport_success_total** | Số transport confirms theo contract | Không nhầm với business success |
| **outbound_business_confirmed_total** | Số business effects confirmed | Completion metric |
| **outbox_pending_count** | Số jobs PENDING/RETRY_WAIT | Backlog |
| **outbox_oldest_age_seconds** | Tuổi job pending lớn nhất | SLO aging |
| **outcome_unknown_total** | Số remote outcomes chưa xác minh | Reconciliation queue |
| **reconciled_total** | Số unknown đã kết luận | Khả năng phục hồi |
| **dead_letter_or_parked_total** | Số terminal failures lưu bền | Vận hành triage |
| **duplicate_delivery_total** | Số redeliveries từ nguồn | Đếm message lặp |
| **idempotency_dedupe_hits_total** | Số duplicate operations bị ngăn | Độ an toàn replay |
| **duplicate_business_effect_total** | Số tác dụng phụ bị nhân đôi đã xác minh | Chỉ số chất lượng nghiêm trọng |
| **commit_latency_seconds** | Thời gian chờ local transaction commit | Tìm DB bottleneck |
| **destination_ack_latency_seconds** | Độ trễ publisher/remote ack | Tìm dependency issues |
| **delivery_to_done_latency_seconds** | Độ trễ nguồn nhận → business DONE | Đo SLO |
| **ack_without_durable_outcome_total** | Ack khi không tìm thấy DONE hoặc durable obligation hợp lệ | Cảnh báo silent loss |

### Correlation và structured logs

Mỗi event nên có:

- businessEventId ổn định;
- correlationId/traceId;
- source protocol/topic/queue/file alias (không lộ secret);
- destinationAlias/operation;
- attemptIndex, brokerDeliveryCount nếu biết;
- sourceAckState và outboundState khác nhau;
- transactionId hoặc logical processing ID phù hợp;
- routePolicyVersion/idempotencyKeyRef;
- terminalOutcome và reasonCode;
- timestamp của COMMIT, ACK, CONFIRM và DONE.

### Cardinality

Không đặt eventId/orderId/traceId làm metric labels. Dùng chúng ở log/traces. Metric labels nên theo adapter, destination alias có cardinality quản lý, errorCategory và finalOutcome.

### Cảnh báo quan trọng

**Outbound attempts tăng** nhưng **business DONE không tăng** cho thấy retries đang che lỗi. **Source ack tăng** nhưng **durable acceptance + business DONE không tương ứng** có thể là source ack sớm. **Unknown outcome backlog tăng tuổi** nghĩa là reconciliation không theo kịp.

## 30. Error handling: không được ack vì error flow đã chạy

Spring Integration có **ErrorMessage**, **errorChannel**, endpoint advice và cách truyền exception khác nhau giữa synchronous/async boundaries.

### Những nhầm lẫn phổ biến

- Một ErrorMessage được gửi tới errorChannel **không có nghĩa** đã ghi lỗi bền.
- Một error flow ghi log thành công **không có nghĩa** message nguồn có thể ack.
- Một RecoveryCallback trả null **không có nghĩa** outbound đã hoàn tất.
- NullChannel chỉ hủy message; không phải DLQ hoặc business recovery.
- Một message đã được enqueue vào QueueChannel in-memory **không bảo đảm** survive restart.
- Một HTTP callback async báo accepted **không chứng minh** remote business DONE.

### Error classification trước commit

~~~mermaid
flowchart TD
    A["Outbound attempt"] --> D{"Result category?"}
    D -->|"Confirmed success"| S["Persist DONE or confirmed reference"]
    D -->|"Transient fail"| R["Bounded retry or durable RETRY_WAIT"]
    D -->|"Permanent invalid"| Q["Quarantine / manual repair"]
    D -->|"Outcome unknown"| U["Reconciliation state"]
    D -->|"Security/config"| X["Escalation, pause destination"]
    S --> C{"Source completion contract met?"}
    R --> C
    Q --> C
    U --> C
    X --> C
    C -->|"Durable obligation or DONE"| K["Ack/commit per protocol"]
    C -->|"Not safely preserved"| E["Propagate/rollback; source recovery"]
~~~

**Chú ý:** Sơ đồ không khuyến khích ack khi chỉ tạo một trạng thái RETRY_WAIT/UNKNOWN trong memory. Phải có **durable record được commit** trước khi chuyển sang nhánh ack theo contract.

### Lỗi khi ghi parking/DLQ

Nếu durable parking write thất bại, đừng nuốt exception rồi ack nguồn. Cần propagate để source redelivery hoặc dùng một nơi giữ message đã được xác minh. Một ErrorMessage trong một channel in-memory **không đủ**.

## 31. Ma trận kiểm thử commit/ack end-to-end

Mỗi test phải biết **thời điểm source commit, outbound effect, durable state và crash point**. Dưới đây là bộ thử bao phủ nhiều adapter.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| T01 | DirectChannel handler outbound thành công | Source ack đúng sau business/durable outcome |
| T02 | DirectChannel handler ném exception | Không ack sai; rollback/recovery theo source |
| T03 | ExecutorChannel gửi vào memory rồi process chết | Test phát hiện nguy cơ mất message |
| T04 | Durable inbox/outbox commit trước source ack | Outbound job còn sau restart |
| T05 | Database commit inbox thành công, source ack thất bại | Redelivery được dedupe |
| T06 | Database INSERT outbox thất bại | Inbox transaction rollback, source chưa ack |
| T07 | Duplicate eventId cùng hash | Không tạo outbox job trùng |
| T08 | Duplicate eventId khác payload/hash | Conflict/investigation |
| T09 | Outbox worker claim rồi crash trước send | Lease expiry cho retry |
| T10 | Outbox worker gửi remote xong rồi crash trước DONE | Idempotency/reconcile, không nhân business effect |
| T11 | Hai workers cùng poll một job | Atomic claim ngăn double-send ngoài ý muốn |
| T12 | Outbox record DONE rồi restart | Không tự gửi lại |
| T13 | HTTP 200 theo contract đồng bộ | Persist completion rồi source ack |
| T14 | HTTP 202 async job | Lưu job ID, không coi final business DONE |
| T15 | HTTP POST commit rồi response timeout | OUTCOME_UNKNOWN, query/idempotency |
| T16 | HTTP 503/429 | Backoff/rate limit, retry có budget |
| T17 | HTTP 401/403 | Không retry vô hạn, owner triage |
| T18 | JMS transacted listener success | Session commit theo mode đã kiểm chứng |
| T19 | JMS handler failure | Rollback/redelivery theo container contract |
| T20 | JMS commit failure sau HTTP success | Duplicate được bảo vệ |
| T21 | JMS + DB hai local tx riêng | Test crash window giữa 2 commits |
| T22 | AMQP inbound handler success | Ack đúng mode/time |
| T23 | AMQP error flow nuốt exception | Negative test phát hiện ack thiếu outcome |
| T24 | AMQP publisher confirm delayed | Không coi send return là confirm nếu contract cần |
| T25 | AMQP publish success, confirm mất | Outcome reconciliation và dedupe |
| T26 | AMQP requeue lỗi invalid liên tục | Không hot loop vô hạn |
| T27 | Kafka offset commit trước async outbound completion | Negative test phát hiện silent loss |
| T28 | Kafka offset commit sau durable handoff | Replay an toàn qua restart |
| T29 | Kafka producer async callback fail | Outbox trạng thái RETRY_WAIT/ERROR |
| T30 | Kafka partition ordering | Version/order guard khi nhiều nhánh |
| T31 | Kafka transaction xử lý Kafka→Kafka | Không suy rộng sang HTTP/JDBC |
| T32 | JDBC deadlock | Retry transaction mới đúng phạm vi |
| T33 | JDBC transaction marked rollback-only | Không mark DONE sai |
| T34 | JDBC poller claim row rồi crash | Lease expiry/recovery |
| T35 | JDBC commit xong nhưng HTTP chưa gửi | Outbox publisher tiếp tục |
| T36 | File inbound đã accept-once trước outbound failure | Source metadata không làm mất job |
| T37 | File archive/move lỗi sau DB commit | Reconciliation riêng, không rollback DB giả |
| T38 | File chưa publish hoàn chỉnh | Không xử lý .part như ready |
| T39 | SFTP download bị cắt | Partial staging/transfer retry |
| T40 | SFTP upload xong nhưng rename response mất | Remote state reconciliation |
| T41 | SFTP host key mismatch | Security fail, không ack/mất dữ liệu |
| T42 | Nhiều recipients: hai DONE, một RETRY_WAIT | Chỉ retry recipient chưa DONE |
| T43 | RecoveryCallback return null khi chưa lưu parking | Negative test phải fail |
| T44 | Ghi DLQ/parking thất bại | Không ack mất source |
| T45 | Nested retries broker/handler/client | Đếm và giới hạn đúng tổng attempts |
| T46 | Business deadline hết trước lần retry | CANCELLED/PARKED theo contract |
| T47 | Unknown outcome tồn lâu | Có alert/owner/runbook |
| T48 | Outbox payload chứa PII | Encryption, ACL, retention |
| T49 | Error logs chứa token | Redaction, không lộ credential |
| T50 | Source ack và business DONE metric không khớp | Alert phát hiện sai boundary |
| T51 | Recovery sau một deploy lỗi | Jobs không bị xóa và route policy được pin |
| T52 | Outbound destination disabled | Không bỏ event; durable pause/parking |
| T53 | Partner idempotency key hết TTL | Không retry mù sau TTL, reconciliation |
| T54 | TransactionSynchronization afterCommit callback không chạy | Outbox poller vẫn publish |
| T55 | Local DB commit thành công nhưng JVM crash tức thì | Outbox bền; source replay dedupe |
| T56 | Consumer concurrency tăng gấp 10 | Không duplicate do race/claim |
| T57 | Broker redelivery bất ngờ | Một business effect nhờ inbox/idempotency |
| T58 | Nguồn đã ack nhưng audit metric chưa ghi | Không chạy lại side effect chỉ vì telemetry |
| T59 | Schema migration outbox trong deploy | Backward-compatible job processing |
| T60 | Manual redrive từ PARKED | Có approval, audit, idempotent result |

### Crash-point testing chi tiết

Tạo fault injection tại:

1. Sau source receive, trước inbox acceptance;
2. Sau inbox insert, trước outbox insert;
3. Sau outbox DB commit, trước source ack;
4. Sau source ack, trước outbox worker claim;
5. Sau worker claim, trước remote call;
6. Sau remote commit, trước response;
7. Sau response success, trước outbox mark DONE;
8. Sau outbox DONE, trước cleanup source/metrics;
9. Sau DLQ write, trước source ack;
10. Sau nguồn redelivery, trước inbox dedupe decision.

Mỗi điểm cần trả lời: **message còn ở đâu, có thể được giao lại không, có thể tạo duplicate effect không và terminal state nào phải xuất hiện?**

### Test harness phù hợp

- Unit test RetryPolicy, state transitions và idempotency classification.
- Integration test database transaction với rollback/unique constraints.
- Integration test JMS/AMQP/Kafka container ack modes và failure handlers.
- Fake HTTP server cho timeout sau commit/202/429/503.
- SFTP test server cho partial upload/rename outcome unknown.
- Fault injection/chaos test cho crash ở commit boundaries.
- Contract test với đối tác về idempotency key/response/confirm semantics.
- Load test với backpressure, long-running retries và worker leases.

Không chỉ assert số lần mock được gọi; phải kiểm tra **durable database state, source redelivery/offset và remote business effect**.

## 32. Case study: JMS → HTTP ERP → JDBC → AMQP

### Bối cảnh

Một ứng dụng Spring Integration nhận đơn hàng qua JMS broker, gọi ERP HTTP, cập nhật PostgreSQL và phát notification bằng AMQP.

~~~text
JMS inbound (transacted listener)
    -> validate/normalize
    -> HTTP outbound gateway ERP
    -> JDBC update status
    -> AMQP notification
    -> JMS source commit/ack
~~~

Doanh nghiệp yêu cầu:

- Một business event tạo tối đa **một** đơn hàng ERP.
- Không mất message khi ERP, DB hoặc AMQP down.
- Không giữ JMS consumer thread hàng giờ.
- AMQP fail không được khiến ERP bị gọi lại.
- Có thể truy vết source event đến trạng thái DONE/PARKED.
- Ack nguồn theo đúng contract, không chỉ dựa trên send-to-channel in-memory.
- Restart/deploy không xóa công việc pending.

### Dòng thời gian sự cố

| Mốc | Sự kiện | Điều phải phân tích |
|---|---|---|
| 09:00 | JMS nhận order-882 | Source session/ack boundary |
| 09:01 | ERP POST đã commit | Remote business state |
| 09:02 | HTTP response mất | OUTCOME_UNKNOWN/idempotency |
| 09:03 | JMS handler ném exception | Rollback/redelivery |
| 09:04 | JMS redeliver eventId cũ | Dedupe |
| 09:05 | JDBC update deadlock | Retry transaction mới |
| 09:06 | AMQP broker unavailable | Outbox RETRY_WAIT |
| 09:07 | App restart khi outbox IN_PROGRESS | Lease/recovery |
| 09:10 | Publisher confirm về muộn | Không mark DONE sớm |
| 09:11 | Publisher thành công nhưng process chết trước DONE | Duplicate publish |
| 09:12 | Manual replay | Approval/idempotency/route policy |

### Bài tập 1: tìm lỗi của flow đồng bộ

Một phương án được đề xuất:

~~~text
JMS message
  -> HTTP POST ERP
  -> JDBC UPDATE order_status
  -> AMQP publish
  -> return success
~~~

Hãy liệt kê ít nhất sáu crash windows hoặc hành vi ngoài dự kiến: HTTP timeout sau commit, JMS ack thất bại, AMQP confirm mất, database deadlock, error handler nuốt exception và publisher xử lý bất đồng bộ.

**Gợi ý:** không có một transaction atomic bao trùm HTTP + JDBC + AMQP + JMS. Khi bước sau lỗi, retry toàn flow có thể lặp bước trước. Handler return không chắc broker confirm đã được nhận.

### Bài tập 2: thiết kế durable acceptance

~~~mermaid
flowchart TD
    J["JMS inbound"] --> V["Validate + normalize eventId"]
    V --> I["DB transaction: inbox + outbox"]
    I -->|"Commit success"| ACK["JMS ack per container contract"]
    I -->|"Commit fail"| RB["Exception propagated / rollback"]
    I --> W["Outbox worker claim"]
    W --> E["ERP HTTP step"]
    E --> C{"Outcome?"}
    C -->|"Confirmed"| S["ERP_CONFIRMED"]
    C -->|"Transient"| R["RETRY_WAIT"]
    C -->|"Unknown"| U["RECONCILE / PARKED"]
    S --> O["DB transaction: status + AMQP outbox"]
    O --> A["AMQP publisher"]
    A -->|"Confirm"| D["AMQP_DONE"]
    A -->|"Fail"| P["Delayed retry"]
    P --> A
    D --> F["Business DONE"]
~~~

Sơ đồ khái niệm, không có nghĩa mọi bước trong một JDBC transaction. Nếu JMS source ack thất bại sau DB commit, inbox dedupe phải nhận ra redelivery.

### Bài tập 3: so sánh hai chính sách commit

**Policy A — JMS commit sau ERP và AMQP thành công:** gần với synchronous-completion contract nhưng giữ delivery lâu; AMQP outage có thể kéo rollback và redelivery khiến HTTP đã thành công bị gọi lại. Cần idempotency và per-step state.

**Policy B — JMS commit sau durable inbox/outbox DB commit:** source được xác nhận sau khi obligation xử lý đã lưu bền; worker thực hiện outbound sau. Cần leases, monitoring, retry limits, retention và manual replay controls.

**Câu hỏi:** nên chọn policy nào nếu ERP thường mất 8–15 giây còn AMQP đôi khi down 30 phút? Nêu business contract và operational controls làm cho Policy B có thể được chấp nhận.

**Gợi ý:** Policy B thường phù hợp khi durable job store và runbook có độ tin cậy được phê duyệt; đây không phải ack sau remote completion, mà ack sau **durable acceptance**.

### Bài tập 4: timeout sau ERP commit

1. Giữ stable businessEventId xuyên qua retries/redeliveries.
2. Dùng cùng idempotency key nếu ERP hỗ trợ.
3. Khi read timeout, chuyển OUTCOME_UNKNOWN.
4. Worker tra cứu ERP theo idempotency key/order ID.
5. Nếu confirmed, ghi remote order ID và ERP_CONFIRMED.
6. Nếu confirmed not processed, retry POST theo contract.
7. Nếu vẫn unknown, PARKED với owner/deadline, không gửi lệnh tạo order mù.

### Bài tập 5: AMQP outage không kéo ERP retry

Sau ERP_CONFIRMED, tạo một **notification outbox** trong DB. AMQP publisher có stable eventId và theo dõi publisher confirms. Khi broker down, record RETRY_WAIT, không gọi ERP lại.

Nếu publish tới broker thành công mà confirm bị mất, publisher có thể gửi lại; consumer downstream phải dedupe. Broker confirm chỉ xác nhận theo contract broker, không tự là consumer business completion.

### Bài tập 6: mười phép thử ưu tiên

1. ERP 503 rồi thành công.
2. ERP commit rồi response mất.
3. JMS redelivery sau ack failure.
4. Inbox duplicate cùng hash.
5. Inbox duplicate khác hash.
6. JDBC deadlock.
7. AMQP down 30 phút.
8. Publisher confirm bị mất.
9. Process chết giữa outbox claim và send.
10. Process chết sau remote success trước DONE.

Bổ sung manual redrive, cross-tenant access control, schema invalid, retention policy và concurrency.

### Kết quả mong đợi

Không phải chứng minh tuyệt đối không có duplicate deliveries; phải chứng minh:

- Mọi source event có bản lưu durable hoặc vẫn còn ở nguồn tới khi obligation được bảo đảm.
- Một business effect không bị nhân đôi nhờ idempotency/reconciliation.
- Jobs không bị mất khi restart.
- Có owner và cơ chế đóng OUTCOME_UNKNOWN.
- Source ack/commit tương thích durable acceptance.
- Không nuốt exception trước khi lưu recovery.

## 33. Các anti-pattern của “commit sau outbound”

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Ack source sau send vào ExecutorChannel | Message mất khi crash | Durable handoff/đợi completion |
| Đồng nhất handler return với remote commit | Success giả | Kiểm protocol/contract |
| HTTP 202 được coi business DONE | Async job chưa xong | Lưu job ID, theo dõi |
| HTTP POST timeout → retry mù | Tạo trùng đơn hàng | Idempotency/reconcile |
| Giữ JDBC transaction suốt HTTP call dài | Lock/timeout, vẫn không atomic | Outbox và worker |
| Retry toàn flow vì AMQP fail | ERP bị gọi lại | Per-recipient/per-step states |
| RecoveryCallback return null trước parking | Ack sai | Rethrow hoặc durable recovery |
| ErrorMessage vào NullChannel coi là DLQ | Không thể replay | Durable DLQ/parking |
| Kafka offset commit trước send future completion | Mất tác vụ | Await ack hoặc durable handoff |
| Kafka exactly-once = HTTP exactly-once | Nhầm phạm vi transaction | Remote idempotency |
| AMQP publisher confirm = consumer DONE | Completion metric sai | Contract nhiều mức |
| JMS session commit = JDBC commit | Hai local tx không atomic | XA phù hợp hoặc inbox/outbox |
| File move processed trước outbound | Không poll lại nguồn | Staging/state/late archive |
| Accept-once metadata xem là cờ DONE | Mất record khi downstream lỗi | Inbox/business state |
| SFTP rename timeout coi chắc chắn thất bại | Remote có thể đã publish | Reconcile remote |
| Outbox ghi bằng afterCommit callback duy nhất | Crash window mất event | Insert outbox trước commit |
| Outbox không lease/atomic claim | Hai workers cùng xử lý | Claim trong transaction |
| Xóa outbox khi đã thử gửi nhưng chưa confirm | Mất khả năng đối soát | UNKNOWN/RETRY_WAIT |
| Dedupe theo MessageHeaders.ID | UUID có thể đổi khi replay | Stable business event ID |
| EventId trùng nhưng payload khác vẫn bỏ | Dữ liệu sai bị che | Hash/version check |
| Infinite retry trong source transaction | Nghẽn thread/partition | Bounded + delayed retry |
| Không có deadline | Backlog chạy vô hạn | Expiry/cancel policy |
| Log full ErrorMessage headers | Lộ credentials/PII | Redact và secure logging |
| Không test crash sau remote commit | Duplicate effects production | Fault-injection |
| Đếm broker ack là DONE khi cần consumer processing | Báo SLO sai | Completion metric theo contract |
| Bật nhiều lớp retry không budget | Retry amplification | Budget end-to-end |
| Manual redrive không approval | Gửi trùng hoặc sai đích | Audit/permissions/idempotency |

### Một tiêu chí review thiết kế

Trước mỗi thay đổi ack/commit semantics, yêu cầu sơ đồ **source → handler → outbound → durable state → source ack** kèm ít nhất một crash test giữa mỗi cặp bước. Nếu không thể chỉ ra bản copy còn tồn tại khi crash, thiết kế chưa đủ độ tin cậy.

## 34. Runbook: outbound đã thành công, source commit thất bại

### Dấu hiệu

- Remote ERP đã tạo order.
- JMS/AMQP delivery chưa ack hoặc Kafka offset chưa commit.
- Broker redeliver cùng businessEventId.
- Log exception ở commit/ack.
- Remote order tồn tại nhưng local state hoặc source progress không khớp.

### Các bước xử lý

1. **Giữ bằng chứng:** eventId, correlationId, destinationAlias, source metadata, timestamp, remote ID.
2. **Dừng retry mù:** không tạo POST mới chỉ vì nguồn giao lại.
3. **Tra remote state:** theo stable order ID/idempotency key; lưu confirmed outcome.
4. **Kiểm inbox/outbox:** record đúng eventId/version/hash và job trạng thái nào.
5. **Phân loại:** source redelivery, remote duplicate, local DB commit uncertain, source ack failure.
6. **Khôi phục:** nếu DONE đã xác minh → dedupe/no-op; nếu thiếu bước → retry đúng bước; nếu unknown → PARKED.
7. **Đối chiếu source:** acknowledgement/offset/lease theo giao thức, không reset offset mù.
8. **Xác minh end-to-end:** một business effect, không orphan jobs.
9. **Audit:** owner, reason, decision, remote reference, approval nếu manual redrive.
10. **Hậu kiểm:** bổ sung negative/crash-point test, chỉnh transaction boundary nếu cần.

Không xóa broker message để dashboard đẹp, không xem log error là recovery và không đánh dấu DONE chỉ vì handler đã thử một lần.

## 35. Checklist triển khai commit/ack an toàn

- [ ] Định nghĩa rõ **outbound success level** theo business contract, không chỉ handler return.
- [ ] Biết **commit tài nguyên nào**: JDBC, JMS session, Kafka offset, AMQP consumer ack, File/SFTP lifecycle, outbox state.
- [ ] Có sơ đồ nguồn → xử lý → outbound → durable state → source acknowledgement.
- [ ] Xác định DirectChannel/ExecutorChannel/QueueChannel và transaction thread boundaries.
- [ ] Nếu dùng async, source không ack dựa trên enqueue in-memory khi cần at-least-once.
- [ ] Nếu dùng sync, timeout/deadline và source consumer concurrency đủ.
- [ ] JDBC local transaction không bị nhầm là distributed HTTP/SFTP transaction.
- [ ] JMS transaction/ack/rollback được test theo container mode.
- [ ] AMQP ack/nack/requeue/DLX và publisher confirm được phân biệt.
- [ ] Kafka offset/error handler/retry topic/DLT và producer ack semantics được test.
- [ ] File/SFTP có staging, ready marker, accept-once metadata, stable name và reconcile.
- [ ] JDBC polling có atomic claim, lease expiry, nextAttemptAt và state bền.
- [ ] @Transactional sử dụng đúng transaction manager/proxy và rollback policy.
- [ ] Có transactional outbox/inbox nếu source ack theo durable-acceptance model.
- [ ] Có unique business/recipient ID để dedupe.
- [ ] Có idempotency key hoặc query/reconciliation khi outbound outcome không rõ.
- [ ] Outbox publisher dùng atomic claim, lease, retry có deadline, mark DONE sau confirmation.
- [ ] Có xử lý crash ở tất cả ranh giới commit và source ack.
- [ ] Error flow/RecoveryCallback không nuốt lỗi khi chưa có durable recovery.
- [ ] DLQ/parking bền, có owner, retention, audit và controlled replay.
- [ ] Fan-out nhiều recipients có per-recipient statuses và required/optional policy.
- [ ] Source redelivery, client retry, handler retry và durable redrive có budget tổng.
- [ ] Metrics tách source ack, durable acceptance, outbound transport ack, business DONE.
- [ ] Không log secrets/PII; storage inbox/outbox có ACL/encryption và retention.
- [ ] Test hậu commit callback không chạy vẫn có outbox poller phục hồi.
- [ ] Test remote commit rồi response mất không tạo duplicate effect.
- [ ] Test deadlock/rollback-only không commit sai.
- [ ] Có runbook cho OUTCOME_UNKNOWN, stuck lease, expired jobs và source-ack failure.
- [ ] Review giao dịch có tài liệu rõ về giới hạn XA/JTA nếu dùng.
- [ ] Chưa có bằng chứng durable/business success thì không kết luận DONE chỉ vì outbound channel.send thành công.

## 36. Thuật ngữ và tài liệu đọc sâu

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Commit** | Xác nhận thành công của transaction theo phạm vi tài nguyên được quản lý |
| **Source acknowledgement (ack)** | Xác nhận một delivery đã xử lý hoặc được chấp nhận theo giao thức nguồn |
| **Kafka offset commit** | Ghi nhận tiến độ consumer group, không tự chứng minh external operation DONE |
| **AMQP publisher confirm** | Broker xác nhận mức tiếp nhận của outbound publish theo cấu hình |
| **JMS session commit** | Commit một transaction thuộc session JMS nếu dùng transacted session |
| **JDBC transaction commit** | Ghi bền các thay đổi DB tham gia cùng transaction |
| **Transport acceptance** | Đích đã nhận/giao thức phản hồi theo mức contract |
| **Business completion** | Tác vụ nghiệp vụ đạt trạng thái cuối được xác nhận |
| **Durable acceptance** | Tác vụ được lưu bền để hệ thống có thể xử lý sau |
| **Transactional outbox** | Ghi ý định gửi message cùng database transaction với dữ liệu nguồn |
| **Inbox / deduplication** | Lưu business event ID và kết quả để xử lý redelivery an toàn |
| **Idempotency key** | Khóa ổn định để gửi lại cùng operation không tạo hiệu ứng trùng |
| **Unknown outcome** | Không chắc remote đã commit side effect hay chưa |
| **Retry / backoff** | Thử lại lỗi có thể phục hồi / khoảng chờ giữa attempts |
| **Redelivery** | Source/broker giao lại một message chưa có acknowledgement phù hợp |
| **DLQ/DLT/PARKED** | Nơi giữ lỗi có thể điều tra hoặc replay |
| **Lease** | Quyền xử lý tạm thời của worker; hết hạn cho phép recovery |
| **Transaction synchronization** | Callback gắn với vòng đời local transaction, không mặc định atomic bên ngoài |
| **XA/JTA** | Cơ chế phối hợp một số tài nguyên hỗ trợ distributed transactions |
| **DirectChannel** | Channel dispatch đồng bộ trong caller thread theo topology |
| **ExecutorChannel** | Channel dùng executor, tạo ranh giới async |
| **QueueChannel** | Channel xếp message, độ bền phụ thuộc MessageStore/config |
| **At-least-once** | Delivery có thể lặp để tránh mất message |
| **Effectively-once effect** | Duplicate deliveries nhưng một hiệu ứng nghiệp vụ hợp lệ nhờ idempotency |
| **Compensation** | Thao tác nghiệp vụ bù, không đồng nghĩa rollback ACID |

### Tài liệu tham khảo khái niệm

- **Spring Integration Reference — Transactions:** transaction boundaries, polling consumers, transaction synchronization và advice.
- **Spring Integration Reference — Message Channels:** DirectChannel, ExecutorChannel, QueueChannel và implications của asynchronous handoff.
- **Spring Integration Reference — Error Handling:** errorChannel, ErrorMessage, lỗi đồng bộ/bất đồng bộ.
- **Spring Integration Reference — JMS, AMQP, Kafka, JDBC, HTTP, File, SFTP adapters/gateways:** hành vi từng protocol và endpoint.
- **Spring Framework Reference — Transaction Management:** PlatformTransactionManager, propagation, rollback và synchronization.
- **Spring Retry Reference:** RetryTemplate, RetryPolicy, BackOffPolicy và RecoveryCallback.
- **Spring for Apache Kafka Reference:** consumer ack mode, Kafka transactions, error handlers, offsets và DLT.
- **Spring AMQP Reference:** listener acknowledgement, nack/requeue, publisher confirms và dead-lettering.
- **Enterprise Integration Patterns:** Transactional Client, Idempotent Receiver, Guaranteed Delivery, Dead Letter Channel và Message Store.

Các tài liệu này là nguồn tham khảo theo chủ đề; cần đối chiếu **phiên bản Spring Integration/Spring Framework/client** của dự án trước khi sao chép API cấu hình cụ thể.

## 37. Câu hỏi tự đánh giá

1. Vì sao handler HTTP outbound trả về bình thường chưa chắc có nghĩa ERP business operation đã hoàn tất?
2. Kafka offset commit khác JDBC transaction commit ở đâu?
3. Vì sao việc ack nguồn **sau** outbound success vẫn có thể tạo duplicate?
4. Một ExecutorChannel trả kết quả send thành công có đủ điều kiện ack source chưa? Khi nào?
5. Trong chiến lược durable handoff, nguồn được ack trước hay sau remote outbound business completion?
6. Vì sao transactional outbox phải được ghi **trong** database transaction thay vì chỉ gửi message từ callback sau commit?
7. Vì sao outbox vẫn cần idempotency dù có unique eventId?
8. HTTP 202 Accepted có thể cho phép ack source khi nào?
9. Vì sao publisher confirm AMQP không chứng minh consumer downstream đã DONE?
10. Nếu Kafka consumer gửi một record sang HTTP rồi process crash trước offset commit, vấn đề nào xuất hiện?
11. File accept-once filter và archive có thể tạo rủi ro gì khi outbound fail?
12. Khi SFTP rename đã thực hiện nhưng response mất, xử lý thế nào?
13. Vì sao @Transactional trên phương thức có HTTP call không làm remote POST rollback?
14. Khi nào JTA/XA có ích, và tại sao nó không giải quyết trực tiếp HTTP/SFTP?
15. Nếu JMS handler retry bốn attempts và broker redeliver ba lần, tổng handler invocations có thể tới bao nhiêu?
16. Với fan-out ba recipients, hai DONE và một RETRY_WAIT, có nên gửi lại toàn fan-out không?
17. Lúc nào ErrorMessage/RecoveryCallback return bình thường có thể làm source ack sai?
18. Metric nào giúp phát hiện source ack tăng nhưng business events không hoàn tất?
19. Khi một job outbox bị stuck IN_PROGRESS vì worker chết, cần cơ chế gì?
20. Bằng chứng tối thiểu nào cần có trước khi mark business DONE?

### Đáp án ngắn và giải thích

1. Handler return chỉ là một tín hiệu; HTTP 202 hoặc remote workflow async có thể chưa DONE; phải kiểm response/business contract.
2. Kafka offset ghi tiến độ consumer group; JDBC commit ghi thay đổi DB trong transaction; không cùng phạm vi.
3. Remote có thể commit rồi source ack fail/crash; broker redeliver khiến operation chạy lại.
4. Không nếu chỉ enqueue in-memory. Có thể ack khi đã commit durable job state hoặc đã xác minh completion theo contract.
5. **Sau durable local acceptance**, có thể **trước remote business completion**, khi thiết kế và SLA cho phép.
6. Callback sau commit có thể không chạy nếu process crash; outbox phải tồn tại bền sau commit và được poll/recover.
7. Worker có thể gửi remote thành công rồi chết trước mark DONE; retry sẽ gửi lại, cần remote idempotency/reconcile.
8. Khi có durable job ID/state và business contract cho phép accepted-for-processing; không được gọi là final DONE.
9. Confirm phản ánh broker publish, không phải consumer side effect.
10. Consumer redelivery record; HTTP có thể đã xử lý → duplicate nếu thiếu idempotency.
11. File có thể bị đánh dấu/di chuyển và không được poll lại; cần staging/metadata và durable replay.
12. Kiểm remote state/checksum/filename, phân loại OUTCOME_UNKNOWN nếu chưa biết; không ghi đè mù.
13. JDBC transaction không bao phủ HTTP API; remote side effect không tự tham gia rollback.
14. XA hữu ích khi resource managers thực sự hỗ trợ coordination; HTTP/SFTP không mặc định tham gia.
15. **4 × 3 = 12** invocations, chưa kể client retries.
16. Không; retry recipient còn pending với state và idempotency riêng.
17. Khi exception được nuốt trước durable recovery; container có thể xem message thành công.
18. Ack-without-durable-outcome và tương quan sourceAck vs durableAcceptance/businessDONE.
19. Lease/expiry, atomic reclaim, attempt count bền, idempotent resume.
20. Business result theo contract, remote reference/outcome hoặc durable accepted-for-processing state, và source ack/transaction được xác minh.

---

**Kết luận:** “**Commit sau khi xử lý outbound thành công**” trong Spring Integration không phải một dòng cấu hình dùng chung cho mọi adapter. Điều đúng phải được phát biểu bằng **tài nguyên nào commit, mức outbound success cần chờ, source ack xảy ra lúc nào, và event còn có thể phục hồi ở đâu nếu process chết**. Với xử lý đồng bộ, có thể đợi outbound completion rồi ack nguồn nếu container/timeout cho phép; với tích hợp đa protocol và lỗi kéo dài, thường nên commit **durable inbox/outbox** trước source ack, sau đó hoàn tất outbound bằng worker có idempotency và reconciliation. Dù lựa chọn nào, hãy kiểm chứng **ack/commit boundary, unknown outcome, duplicate side effects và crash recovery** bằng integration/fault-injection tests thay vì chỉ dựa vào việc handler không ném exception.









