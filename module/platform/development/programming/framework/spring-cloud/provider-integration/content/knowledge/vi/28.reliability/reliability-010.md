# Dừng ứng dụng an toàn khi còn thông điệp hoặc yêu cầu đang xử lý

Một tiến trình Spring Boot không chỉ cần dừng nhanh; nó cần dừng ở một ranh giới mà trạng thái nghiệp vụ vẫn nhất quán. Khi nhận tín hiệu dừng, ứng dụng có thể còn HTTP request đang chạy, message đã nhận từ broker, transaction database chưa commit, event đang publish từ outbox hoặc tác vụ nền đang ghi file. Nếu đóng connection và thread pool ngay lập tức, request có thể bị cắt giữa chừng, message có thể được giao lại hoặc bị mất tùy settlement mode, và event có thể được publish nhưng chưa cập nhật trạng thái outbox.

**Graceful shutdown** là quy trình ngừng nhận công việc mới, cho phép công việc đang chạy hoàn tất trong một khoảng thời gian có giới hạn, lưu trạng thái cần thiết, settle message đúng thời điểm và đóng tài nguyên theo thứ tự. Khi hết deadline, ứng dụng phải có cách dừng cưỡng bức an toàn: công việc chưa commit được để broker giao lại, còn side effect đã commit phải được bảo vệ bằng idempotency.

Bài thuộc chương **Độ tin cậy** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích các failure window khi process dừng giữa request, transaction, message settlement và publish.
2. Phân biệt graceful shutdown, immediate shutdown và crash recovery.
3. Thiết kế trình tự readiness drain, ngừng nhận việc mới, drain in-flight work và đóng tài nguyên.
4. Cấu hình graceful shutdown của embedded web server trong Spring Boot.
5. Dừng message listener/poller mà vẫn xử lý đúng ACK, Complete, Delete hoặc checkpoint.
6. Phối hợp visibility timeout, message lock, ack deadline và checkpoint với thời gian drain.
7. Dừng outbox publisher mà không đánh dấu nhầm event là đã publish.
8. Đóng executor, scheduler, HTTP client, cloud SDK và database theo thứ tự.
9. Tính termination deadline phù hợp với Kubernetes hoặc môi trường chạy khác.
10. Kiểm thử SIGTERM, timeout hết hạn, redelivery, duplicate và phục hồi sau restart.

## 2. Graceful shutdown bảo vệ điều gì?

Một ứng dụng có thể đang thực hiện nhiều loại công việc:

- HTTP request đang đọc/ghi database.
- Message handler đã nhận message và đang chạy nghiệp vụ.
- Outbox publisher đã claim event và đang gửi tới broker.
- Scheduler đang chạy batch hoặc cleanup.
- Executor đang xử lý tác vụ bất đồng bộ.
- Upload/download đang truyền dữ liệu với Blob/S3/Cloud Storage.
- Stream processor đang xử lý record nhưng chưa checkpoint.
- Saga đang cập nhật state và phát command tiếp theo.

Mục tiêu của graceful shutdown:

- Ngừng nhận công việc mới trước khi đóng tài nguyên.
- Cho phép công việc đang chạy hoàn tất trong giới hạn thời gian.
- Commit trạng thái nghiệp vụ trước ACK/Complete/Delete/checkpoint.
- Không đánh dấu publish thành công nếu chưa có confirmation theo contract.
- Để broker redeliver công việc chưa hoàn tất khi process bị buộc dừng.
- Đóng client, connection pool và database sau khi worker đã dừng.

Graceful shutdown không thể bảo đảm mọi tác vụ luôn hoàn thành. Một request có thể chạy lâu hơn termination deadline; dependency có thể mất kết nối; lock có thể hết hạn. Thiết kế cần một đường phục hồi khi drain không hoàn tất.

## 3. Các failure window khi process dừng

### HTTP request bị cắt giữa transaction

~~~mermaid
sequenceDiagram
    participant LB as Load balancer
    participant A as Spring Boot
    participant DB as Database
    LB->>A: Request tạo order
    A->>DB: BEGIN + ghi order
    Note over A,DB: SIGTERM tới process
    A--xDB: Process bị kill trước COMMIT
    Note over DB: Transaction rollback khi connection đóng
    LB-->>LB: Client có thể retry
~~~

Nếu transaction chưa commit, database thường rollback khi connection bị đóng. Nhưng client có thể không biết kết quả và gửi lại request. API cần idempotency key để tránh tạo order trùng khi response bị mất sau commit.

### Message đã xử lý nhưng chưa ACK

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Database
    B->>C: Deliver message M1
    C->>DB: BEGIN + update business
    DB-->>C: COMMIT
    Note over C: SIGTERM trước ACK
    C--xB: Process dừng, ACK chưa gửi
    B->>C: Redelivery sau restart
    C->>DB: Inbox kiểm tra M1
    Note over DB: Duplicate được nhận diện
    C->>B: ACK / Complete
~~~

Đây là tình huống có thể xảy ra dù ứng dụng dừng theo quy trình. Commit trước ACK và inbox/idempotency làm redelivery an toàn.

### ACK trước commit gây mất nghiệp vụ

Nếu consumer ACK message rồi process bị dừng trước khi database commit, broker có thể coi message đã hoàn tất và không giao lại. Vì vậy không ACK chỉ vì handler đã bắt đầu hoặc đã đưa công việc vào executor nội bộ.

### Outbox publish thành công nhưng chưa mark SENT

~~~mermaid
sequenceDiagram
    participant P as Outbox publisher
    participant B as Broker
    participant DB as Database
    P->>B: Publish event E1
    B-->>P: Accepted
    Note over P: SIGTERM trước update outbox
    P--xDB: Chưa mark SENT
    Note over DB: Outbox vẫn PENDING/IN_FLIGHT
    P->>B: Publish lại E1 sau restart
    Note over B: Có thể nhận duplicate
~~~

Giữ event ID ổn định và dùng consumer inbox để tránh lặp business effect. Không tạo event ID mới khi publisher retry cùng outbox record.

## 4. Shutdown lifecycle: ngừng nhận trước, đóng tài nguyên sau

Một trình tự tổng quát:

~~~mermaid
flowchart TD
    A[SIGTERM / stop request] --> B[Đánh dấu instance NOT_READY]
    B --> C[Ngừng nhận HTTP request mới]
    B --> D[Ngừng poll/receive message mới]
    B --> E[Ngừng scheduler claim công việc mới]
    C --> F[Drain HTTP in-flight]
    D --> G[Drain message handlers]
    E --> H[Drain background jobs / outbox publish]
    F --> I[Đợi transaction và response hoàn tất]
    G --> J[Commit rồi ACK/Complete hoặc để redelivery]
    H --> K[Persist state và publish confirmation]
    I --> L[Đóng executors và clients]
    J --> L
    K --> L
    L --> M[Đóng database / context]
    M --> N[Process exit]
~~~

Các hoạt động có thể chạy song song sau khi đã ngừng nhận việc mới, nhưng thứ tự phụ thuộc tài nguyên:

1. Đánh dấu NOT_READY và bắt đầu drain ingress.
2. Dừng nhận HTTP request mới và message mới.
3. Dừng scheduler/outbox poller claim công việc mới.
4. Chờ request/handler/publisher đang chạy hoàn tất.
5. Commit transaction và settle message theo đúng contract.
6. Dừng executor/background worker sau khi queue đã drain hoặc deadline đã hết.
7. Đóng broker clients, storage clients và HTTP clients.
8. Đóng database connection pool và application context.

Không đóng database trước khi message handler và outbox publisher hoàn tất cập nhật trạng thái. Không đóng broker client trước khi listener đã dừng và các settlement cần thiết đã được gửi.

## 5. Readiness drain và ngừng nhận công việc mới

Trước khi process đóng, hệ thống điều phối cần ngừng gửi traffic mới tới instance đó.

### Readiness khác liveness

- **Readiness:** instance có nên nhận traffic mới không.
- **Liveness:** tiến trình còn sống và có khả năng tiếp tục chạy không.
- **Startup probe:** ứng dụng đã khởi động đủ để được kiểm tra readiness/liveness chưa.

Khi shutdown bắt đầu, readiness nên chuyển NOT_READY. Load balancer/orchestrator cần thời gian cập nhật endpoint và ngừng định tuyến traffic mới. Readiness fail không tự động dừng message listener; consumer cần được pause/stop riêng.

Không làm liveness fail chỉ để bắt đầu shutdown. Liveness failure có thể kích hoạt restart cưỡng bức và cắt ngang drain.

### Readiness propagation delay

Việc cập nhật readiness và endpoint routing không nhất thiết xảy ra tức thì. Một số request có thể đã được load balancer gửi tới instance trong thời gian propagation. Embedded web server graceful shutdown và ứng dụng vẫn cần xử lý các request đang tới trong khoảng chuyển tiếp.

Có thể dùng một khoảng drain delay ngắn sau khi readiness đổi trạng thái, nhưng phải tính nó vào termination budget. Không dựa vào sleep cố định mà bỏ qua trạng thái thực tế nếu nền tảng có lifecycle hook phù hợp.

### Message ingress cần điều khiển riêng

Readiness của HTTP endpoint không có nghĩa broker ngừng giao message. Với message-driven application:

- Dừng listener container hoặc subscriber pull loop.
- Dừng long polling/prefetch nhận message mới.
- Không nhận thêm batch nếu không đủ thời gian xử lý trước deadline.
- Đợi các callback đang chạy.
- Với stream processor, dừng fetch/assignment theo lifecycle của client và giữ checkpoint an toàn.

## 6. Graceful shutdown của Spring Boot web server

Spring Boot hỗ trợ graceful shutdown cho embedded web server. Cấu hình thường dùng:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Khi application context đóng, web server ngừng nhận request mới theo khả năng của server và chờ các request đang xử lý hoàn tất trong khoảng timeout được cấu hình cho shutdown phase.

Các lưu ý:

- Cấu hình chỉ tác động tới embedded web server do Spring Boot quản lý.
- Nó không tự drain mọi message listener, scheduler, custom executor hoặc cloud SDK.
- Timeout là giới hạn chờ; request kéo dài hơn vẫn có thể bị cắt khi process bị dừng cưỡng bức.
- Cần kiểm tra behavior với phiên bản Spring Boot và web server thực tế.
- Client retry sau khi mất response cần idempotency key.
- Với WebFlux, cần kiểm thử request reactive và cancellation của downstream publisher.

### Application lifecycle

Spring quản lý bean lifecycle và các component triển khai Lifecycle/SmartLifecycle. Có thể dùng lifecycle phase để điều phối thứ tự start/stop. Các phase được start theo thứ tự tăng dần và stop theo thứ tự ngược lại; component có phase cao hơn sẽ được yêu cầu stop sớm hơn.

Điều này hữu ích khi listener cần dừng trước resource mà listener sử dụng. Tuy nhiên, không phải mọi binder/client đều dùng cùng lifecycle phase. Kiểm tra phase và stop semantics của từng component trước khi dựa vào thứ tự tự động.

### Không phụ thuộc riêng vào @PreDestroy

**@PreDestroy** phù hợp để đóng một resource hoặc giải phóng tài nguyên đơn giản. Một phương thức cleanup không nên tự mình điều phối toàn bộ hệ thống nếu còn listener, request và background task cần drain. Dùng lifecycle contract rõ ràng, có deadline và trạng thái.

## 7. Quản lý HTTP request đang chạy

Graceful web server shutdown xử lý phần lớn vòng đời request của embedded server, nhưng ứng dụng vẫn cần quan tâm tới các tác vụ được tách khỏi request.

Ví dụ controller gửi tác vụ vào executor rồi trả response:

~~~java
@PostMapping("/reports")
public ResponseEntity<ReportAccepted> createReport(
        @RequestBody ReportCommand command) {
    reportExecutor.submit(() -> reportService.generate(command));
    return ResponseEntity.accepted()
            .body(new ReportAccepted(command.operationId()));
}
~~~

Nếu response đã trả 202 nhưng tác vụ chỉ nằm trong queue RAM, process dừng có thể làm mất công việc. Có hai lựa chọn:

- Ghi command/outbox vào storage bền vững trước khi trả 202; worker có thể tiếp tục sau restart.
- Nếu tác vụ chỉ là best-effort, định nghĩa rõ rằng nó có thể bị bỏ khi shutdown và không hứa đã được tiếp nhận bền vững.

Không coi việc submit vào executor là durable acceptance.

### Idempotency của request

Client có thể timeout và retry khi server đã commit nhưng chưa gửi response. Với thao tác tạo order/payment:

- Nhận idempotency key từ client hoặc tạo operation ID ở bước tiếp nhận bền vững.
- Lưu key và kết quả trong transaction.
- Retry cùng key trả lại kết quả đã biết hoặc trạng thái đang xử lý.
- Không tạo operation mới cho cùng một ý định chỉ vì connection bị đóng.

### Request có side effect ngoài database

Nếu request gọi payment provider rồi process dừng trước khi lưu kết quả, cần provider idempotency key và reconciliation. Graceful shutdown giảm xác suất bị cắt ngang nhưng không thay thế recovery cho unknown outcome.

## 8. Dừng message consumer an toàn

Một consumer cần thực hiện các bước:

1. Ngừng nhận message mới.
2. Không claim thêm batch hoặc prefetch thêm công việc.
3. Chờ handler đang chạy trong thời gian drain.
4. Đợi transaction database commit/rollback.
5. Chỉ ACK/Complete/Delete sau commit.
6. Nếu không thể hoàn tất trước deadline, không ACK message chưa commit; để broker redeliver theo semantics.
7. Đóng receiver/subscriber sau khi dừng settlement cần thiết.

### Handler đang chạy khi shutdown

Không nên kill thread ngay khi nhận SIGTERM. Cho handler hoàn tất trong giới hạn thời gian nếu:

- Nó có thể commit trong deadline.
- Message lock/visibility/ack deadline còn hiệu lực hoặc có thể gia hạn.
- Dependency còn khả dụng.
- Không vi phạm overall shutdown budget.

Nếu handler không thể hoàn tất, cần rollback transaction và để message được giao lại. Nếu handler đã tạo external side effect, phải có idempotency/reconciliation khi redelivery.

### Prefetch và batch size

Prefetch/batch lớn làm tăng số message đã nhận nhưng chưa xử lý khi shutdown bắt đầu. Điều này kéo dài drain và có thể khiến lock/visibility timeout hết hạn.

Chọn prefetch/concurrency theo:

- Thời gian xử lý p95/p99.
- Message lock/visibility/ack deadline.
- Số worker.
- Shutdown grace period.
- Khả năng gia hạn lock/ack deadline.
- Chi phí redelivery và duplicate.

Không prefetch nhiều hơn khả năng hoàn tất trong thời gian xử lý và drain dự kiến.

## 9. Message settlement phải theo business commit

Với queue hỗ trợ ACK/Complete/Delete:

~~~text
Receive message
  → Execute handler
  → Begin database transaction
  → Inbox + business update
  → Commit
  → ACK / Complete / Delete
~~~

Nếu process dừng trước commit, message không được settle và có thể redeliver. Nếu commit xong nhưng dừng trước ACK, redelivery được inbox nhận diện.

Với stream có checkpoint:

~~~text
Read record at sequence N
  → Persist business state / inbox
  → Commit database
  → Checkpoint only through contiguous completed sequence
~~~

Không checkpoint vượt qua record chưa commit. Nếu record lỗi đã được lưu bền vững vào failure store theo policy, checkpoint có thể tiến qua record đó sau khi việc lưu failure đã hoàn tất và được audit.

### ACK không đồng nghĩa handler đã chạy xong

## 10. Azure Service Bus: lock và processor shutdown

Azure Service Bus thường dùng Peek-Lock để consumer nhận message dưới một lock rồi Complete sau khi xử lý. Khi shutdown:

- Ngừng processor/receiver nhận message mới.
- Chờ callback đang chạy hoàn tất nếu thời gian drain cho phép.
- Commit database trước khi Complete.
- Đảm bảo lock không hết hạn trước khi handler hoàn tất; dùng lock renewal trong lúc xử lý khi cần.
- Nếu process dừng hoặc lock hết hạn trước Complete, message có thể được giao lại.
- Không Complete trước khi business state đã bền vững.

### Lock expiry trong lúc drain

Giả sử handler cần 45 giây nhưng lock còn 20 giây. Nếu không thể gia hạn lock, message có thể được giao lại trong khi handler cũ vẫn đang chạy. Hai consumer có thể cùng tạo side effect nếu không có idempotency/concurrency control.

Vì vậy:

- Chọn lock duration/renewal theo thời gian xử lý.
- Giới hạn drain time để còn thời gian Complete.
- Dùng inbox/unique constraint để bảo vệ transaction.
- Không giả định stop processor tự gia hạn lock vô hạn.
- Kiểm tra API stop/close và callback behavior của Azure SDK/binder version đang dùng.

### Receive-and-Delete

Với Receive-and-Delete, message có thể bị loại khỏi broker ngay khi giao. Nếu process dừng trước khi handler hoàn tất, broker không thể redeliver message đó. Không dùng mode này cho công việc cần bảo đảm xử lý bền vững trừ khi có cơ chế lưu durable acceptance/recovery khác.

## 11. Azure Event Hubs: dừng processor và checkpoint

Event Hubs consumer xử lý stream theo partition. Khi shutdown:

1. Dừng nhận event mới hoặc dừng processor theo API lifecycle.
2. Chờ handler đang chạy hoàn tất trong giới hạn.
3. Commit business state trước checkpoint.
4. Chỉ checkpoint tới event cuối cùng đã hoàn tất liên tục trong partition.
5. Đóng processor/client sau khi checkpoint cần thiết đã được ghi.

Nếu process dừng sau database commit nhưng trước checkpoint, event có thể được đọc lại từ checkpoint cũ. Inbox/idempotency bảo vệ business effect.

Nếu checkpoint trước business commit, event có thể bị bỏ qua sau restart. Với consumer xử lý song song, không checkpoint vượt qua event cũ hơn còn đang chạy.

Checkpoint là tiến độ đọc, không phải transaction chung với database. Dùng checkpoint store và consumer group phù hợp; kiểm tra behavior khi partition ownership/rebalance thay đổi.

## 12. AWS SQS: visibility timeout và dừng polling

SQS consumer nhận message và message trở nên invisible trong visibility timeout. Consumer xóa message sau khi xử lý thành công.

Khi shutdown:

- Dừng long polling/nhận message mới.
- Không nhận thêm batch khi không đủ thời gian xử lý.
- Chờ handler đang chạy commit.
- Gọi DeleteMessage sau khi commit.
- Nếu không hoàn tất, không delete; visibility timeout hết thì message có thể được giao lại.
- Đảm bảo visibility timeout đủ cho xử lý và drain hoặc gia hạn trong lúc xử lý.

### Visibility timeout và redelivery

Nếu visibility timeout ngắn hơn thời gian handler, message có thể xuất hiện lại trước khi handler cũ kết thúc. Nếu shutdown kéo dài, visibility timeout có thể hết và một consumer khác nhận message.

Cần:

- Sizing visibility timeout theo p99 processing duration và shutdown margin.
- Dùng ChangeMessageVisibility khi cần kéo dài thời gian xử lý theo policy.
- Không kéo dài vô hạn; có deadline và max processing time.
- Dùng inbox/idempotency để bảo vệ duplicate.
- Với FIFO, lưu ý message group có thể bị chặn cho tới khi message được delete hoặc visibility timeout kết thúc.

### Không xóa message trong finally

Không gọi DeleteMessage vô điều kiện trong finally. Nếu handler ném exception hoặc transaction rollback, xóa message sẽ làm mất cơ hội retry. Chỉ delete sau khi business commit hoặc sau khi lỗi đã được ghi bền vững vào failure store theo policy.

## 13. AWS Kinesis Data Streams: checkpoint và shard ownership

Kinesis consumer thường checkpoint sequence number theo shard. Với Kinesis Client Library, worker/lease lifecycle và shard shutdown cần được xử lý theo API/version đang dùng.

Khi dừng:

- Ngừng nhận record mới cho shard hoặc dừng worker theo lifecycle của library.
- Hoàn tất record đang xử lý nếu còn thời gian.
- Commit business state trước checkpoint.
- Chỉ checkpoint qua dãy record đã hoàn tất liên tục.
- Để record chưa checkpoint được đọc lại khi shard được xử lý tiếp.
- Khi lease chuyển, worker mới có thể đọc lại từ checkpoint gần nhất.

Không checkpoint record mới hơn khi record cũ hơn chưa hoàn tất. Nếu xử lý song song, cần quản lý contiguous completion. Dùng event ID/inbox để chống duplicate sau restart hoặc lease handoff.

## 14. Google Cloud Pub/Sub: ack deadline và subscriber shutdown

Pub/Sub subscriber nhận message với ack deadline. Client library có thể tự gia hạn deadline trong thời gian xử lý theo cấu hình lease management.

Khi shutdown:

- Ngừng nhận message mới bằng lifecycle của Subscriber/client.
- Cho callback đang chạy hoàn tất trong giới hạn.
- Commit business state trước ACK.
- Nếu không ACK trước khi deadline hết, message có thể được giao lại.
- Đóng subscriber sau khi các callback/settlement cần thiết hoàn tất hoặc khi hết deadline.
- Dùng inbox/idempotency vì redelivery vẫn có thể xảy ra theo delivery semantics.

### Exactly-once delivery

Nếu subscription bật exactly-once delivery và client/API đáp ứng điều kiện hỗ trợ, ACK confirmation có semantics mạnh hơn trong phạm vi feature. Điều đó không tạo transaction chung với database. Process có thể commit database rồi dừng trước ACK confirmation; ứng dụng vẫn cần idempotent business effect và recovery.

### Flow control

Flow control giới hạn số message/byte outstanding. Giảm outstanding count có thể làm drain nhanh và giảm lượng message đang giữ lease khi shutdown. Tuy nhiên giới hạn quá thấp làm giảm throughput bình thường; chọn theo latency và capacity.

## 15. Spring Cloud Stream binder và listener lifecycle

Spring Cloud Stream cung cấp abstraction function/consumer, nhưng lifecycle, pause/resume, acknowledgment và stop behavior phụ thuộc binder.

Cần xác minh:

- Binding/listener container được tạo và quản lý bởi bean nào?
- Có thể pause/stop nhận message mới mà vẫn đợi in-flight callback không?
- Khi stop, binder có settle message đang xử lý không?
- Handler return bình thường thì ACK/Complete diễn ra khi nào?
- Handler ném exception trong lúc shutdown thì retry/DLQ thế nào?
- Batch listener có dừng giữa batch không?
- Manual acknowledgment có được hỗ trợ và API nào dùng?
- Consumer concurrency/prefetch có giảm được trước shutdown không?
- Binder close có đóng client dùng chung với producer không?

Không giả định một lệnh stop chung hoạt động giống nhau trên Service Bus, SQS, Pub/Sub, Event Hubs và Kinesis. Viết integration test với binder và phiên bản thực tế.

### Listener container và SmartLifecycle

Một số listener container triển khai Spring Lifecycle/SmartLifecycle. Spring có thể yêu cầu container dừng theo phase. Với custom component, có thể dùng SmartLifecycle để điều phối stop bất đồng bộ, nhưng phải gọi callback khi drain thực sự hoàn tất hoặc khi deadline đã hết.

Không gọi callback ngay khi mới gửi tín hiệu stop nếu handler vẫn đang chạy. Nếu lifecycle callback bị giữ vô hạn, application context có thể không đóng đúng hạn.

## 16. Dừng outbox publisher và producer an toàn

Outbox publisher cũng cần graceful shutdown:

1. Ngừng scheduler/poller claim record mới.
2. Giữ các record đã claim trong trạng thái có lease.
3. Chờ publish đang chạy hoàn tất trong deadline.
4. Chỉ mark SENT sau broker confirmation.
5. Nếu kết quả unknown, giữ record ở trạng thái retry/lease expiry; lần chạy sau publish cùng event ID.
6. Đóng producer/client sau khi publish task dừng.
7. Không xóa outbox record chỉ vì process đang shutdown.

### Nếu publish đã accepted nhưng chưa mark SENT

Sau restart, publisher có thể gửi lại event. Đây là duplicate hợp lệ theo failure model. Consumer inbox và stable event ID ngăn side effect lặp.

### Dừng producer trước hay consumer trước?

Không có một thứ tự duy nhất cho mọi topology. Với một instance vừa nhận command vừa phát event:

- Ngừng nhận ingress trước.
- Chờ các handler hiện tại commit và ghi outbox.
- Dừng outbox poller claim event mới sau khi không còn handler tạo thêm outbox.
- Drain các publish đang chạy.
- Đóng broker clients.

Nếu outbox poller bị dừng quá sớm trong khi HTTP/message handler vẫn có thể ghi outbox, event mới sẽ chờ đến instance/worker sau. Điều đó có thể chấp nhận nếu outbox bền vững và worker khác sẽ tiếp tục; nếu không, cần điều phối đúng thứ tự.

## 17. Dừng scheduler, executor và background jobs

Một executor có hai loại công việc:

- Đã bắt đầu chạy.
- Đang nằm trong queue nhưng chưa chạy.

Khi shutdown:

- Ngừng submit công việc mới.
- Gọi shutdown để từ chối submission mới và cho task đã nhận hoàn tất.
- Chờ trong khoảng thời gian hữu hạn.
- Nếu hết deadline, yêu cầu hủy tác vụ có thể hủy và ghi nhận task chưa hoàn tất.
- Không giả định interrupt sẽ dừng được blocking network I/O.
- Công việc chưa chạy trong queue RAM phải được lưu bền vững hoặc được phép bỏ theo policy.

### Java ExecutorService minh họa

~~~java
public void stopExecutor(ExecutorService executor, Duration timeout) {
    executor.shutdown();

    try {
        if (!executor.awaitTermination(
                timeout.toMillis(), TimeUnit.MILLISECONDS)) {
            List<Runnable> neverStarted = executor.shutdownNow();
            recordUnstartedTasks(neverStarted);
            executor.awaitTermination(
                    Math.min(1000, timeout.toMillis()),
                    TimeUnit.MILLISECONDS);
        }
    } catch (InterruptedException ex) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Đoạn code là mẫu khái niệm. Trong ứng dụng thật, cần tránh dùng hết timeout còn lại cho từng executor liên tiếp. Chia sẻ một shutdown deadline và truyền remaining time cho từng phase.

### Scheduled task

Scheduler cần ngừng tạo lần chạy mới. Một task định kỳ có thể đang chạy khi shutdown bắt đầu; chờ nó hoàn tất nếu có thể. Không để scheduler khởi tạo batch mới sau khi readiness đã chuyển NOT_READY.

## 18. Thứ tự đóng tài nguyên

Một quy tắc thực dụng:

| Tài nguyên | Thời điểm dừng/đóng |
| --- | --- |
| Readiness/ingress | Đầu tiên |
| HTTP server nhận request mới | Đầu drain |
| Message listener/subscriber | Đầu drain |
| Scheduler/poller claim việc mới | Sau khi chặn ingress tạo việc mới |
| In-flight handler/request | Chờ hoàn tất |
| Outbox publisher đang gửi | Chờ confirmation hoặc để retry sau restart |
| Executor/background worker | Sau khi không còn submission mới |
| Broker producer/consumer client | Sau khi listener/publisher dừng |
| Storage/HTTP clients | Sau khi tác vụ dùng chúng kết thúc |
| Database connection pool | Gần cuối |
| Application context/process | Cuối cùng |

Tài nguyên có quan hệ phụ thuộc phải đóng sau component sử dụng nó. Ví dụ database pool phải còn mở khi handler đang commit; broker producer phải còn mở khi outbox publisher chờ confirmation.

Không đóng database hoặc broker client chỉ vì một bean cleanup được gọi sớm. Dùng lifecycle phase/dependency để bảo đảm thứ tự và test với shutdown thực tế.

## 19. Shutdown deadline và termination budget

Môi trường điều phối thường chỉ cho process một khoảng thời gian trước khi gửi SIGKILL hoặc force terminate. Tất cả phase phải nằm trong budget đó.

Một cách lập ngân sách:

~~~text
Termination grace period
  >= readiness propagation
   + stop accepting new work
   + in-flight drain
   + message settlement / checkpoint
   + resource cleanup
   + safety margin
~~~

Các phần có thể chạy song song nên không nhất thiết cộng toàn bộ thời gian tối đa, nhưng phải đo thời gian thực tế và tránh vượt deadline tổng.

### Ví dụ budget minh họa

| Phase | Ngân sách |
| --- | ---: |
| Readiness/endpoint propagation | 5 giây |
| Ngừng nhận HTTP/message mới | 3 giây |
| Drain request/handler | 20 giây |
| Commit/ACK/checkpoint | 5 giây |
| Đóng clients/executors/database | 5 giây |
| Safety margin | 7 giây |
| **Tổng tham khảo** | **45 giây** |

Các con số chỉ minh họa. Dùng p95/p99 processing time, max handler duration, lock/visibility deadline và orchestrator configuration để chọn giá trị.

### Hết deadline thì sao?

Nếu drain không hoàn tất:

- Không ACK message chưa commit.
- Không checkpoint qua record chưa hoàn tất.
- Không mark outbox SENT khi confirmation chưa rõ.
- Persist tiến độ hoặc operation state nếu có thể.
- Hủy tác vụ có thể hủy một cách an toàn.
- Để broker redeliver message chưa settle.
- Dựa vào inbox/idempotency để xử lý lại.
- Đóng resource và thoát trước khi orchestrator force kill nếu còn thời gian.

Không cố giữ process sống vô hạn để chờ một dependency đang outage.
## 20. Kubernetes: SIGTERM, preStop và terminationGracePeriodSeconds

Khi Kubernetes terminate Pod, kubelet thực hiện lifecycle shutdown, có thể chạy preStop hook rồi gửi SIGTERM tới process theo container stop behavior. Pod có thời gian termination grace period; khi hết, process có thể bị SIGKILL.

Ví dụ manifest:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: provider-integration
      image: example/provider-integration:1.0
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
~~~

Đây chỉ là ví dụ minh họa. preStop có thể dùng để bắt đầu drain hoặc chờ endpoint propagation, nhưng thời gian hook cũng tiêu thụ termination grace period. Không đặt sleep dài tùy tiện và quên phần thời gian còn lại cho Spring Boot.

### Readiness probe

Readiness probe nên phản ánh instance đang nhận traffic được hay không. Khi shutdown bắt đầu, ứng dụng có thể chuyển readiness state sang REFUSING_TRAFFIC nếu dùng Spring Boot Actuator availability support.

Ví dụ cấu hình probe trong Kubernetes:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 2
  failureThreshold: 1
~~~

Path/port cần khớp Actuator và deployment. Readiness probe không thay thế việc dừng message listener.

### Budget phải tính cả preStop

Termination grace period bắt đầu trước hoặc trong quá trình lifecycle hook theo semantics của Kubernetes. Hãy tính preStop vào tổng thời gian và kiểm tra behavior của phiên bản cluster/runtime. Cấu hình grace period phải lớn hơn tổng drain + cleanup, có margin.

### Pod disruption và rolling update

Trong rolling update hoặc node drain:

- Readiness giúp ngừng gửi request mới.
- PodDisruptionBudget hạn chế số Pod bị gián đoạn đồng thời nhưng không tự làm từng process drain đúng.
- maxUnavailable/maxSurge ảnh hưởng capacity trong rollout.
- Ứng dụng phải xử lý SIGTERM và restart idempotently.
- Worker consumer cần phối hợp replica còn lại để nhận message sau khi Pod rời đi.

## 21. Docker, systemd và môi trường không dùng Kubernetes

Graceful shutdown không chỉ áp dụng cho Kubernetes.

### Docker

Docker stop thường gửi SIGTERM rồi chờ timeout trước khi SIGKILL. Cấu hình stop timeout phải dài hơn shutdown budget của ứng dụng. Đảm bảo Java process nhận tín hiệu trực tiếp; entrypoint script cần dùng exec để không giữ tín hiệu ở shell cha.

### systemd

Service có thể dùng TimeoutStopSec để giới hạn thời gian stop. Cấu hình này cần lớn hơn thời gian drain/cleanup đã thiết kế. Kiểm tra KillSignal và process tree để child worker không bị bỏ lại.

### VM/container platform khác

Tìm hiểu chính xác tín hiệu stop, thời gian grace, health routing và cách nền tảng thay instance. Không giả định mọi nền tảng đều gửi SIGTERM theo cùng thứ tự.

## 22. Shutdown khi có upload/download hoặc stream dài

Các operation streaming có thể kéo dài hơn HTTP request thông thường:

- Upload Blob/S3/Cloud Storage.
- Download file lớn.
- Stream response qua WebFlux.
- Đọc/ghi Event Hubs hoặc Kinesis batch.
- Chuyển dữ liệu giữa hai provider.

Cần quy định:

- Maximum operation duration.
- Chunk/part checkpoint.
- Multipart upload cleanup/abort.
- Resume token hoặc offset nếu hỗ trợ.
- Temporary file cleanup.
- Idempotent object key và conditional write.
- Hành vi khi process dừng giữa các chunk.

Với multipart upload, một phần dữ liệu có thể đã được gửi nhưng object chưa hoàn tất. Recovery cần tiếp tục hoặc abort upload theo API/provider semantics; không coi HTTP request đã bắt đầu là upload thành công.

Với stream response, graceful web server shutdown có thể chờ request đang mở trong giới hạn. Nếu stream kéo dài vô hạn, cần maximum duration hoặc reconnect/resume protocol.

## 23. Shutdown và scheduled maintenance

Các tác vụ nền như outbox polling, reconciliation, cleanup và scheduled export cần lifecycle riêng.

- Ngừng trigger lần chạy mới.
- Không claim batch mới sau khi shutdown bắt đầu.
- Đợi batch hiện tại commit checkpoint/trạng thái.
- Nếu batch chưa hoàn tất, lưu cursor và retry sau restart.
- Không xóa file/record đang được consumer sử dụng.
- Đảm bảo job có lease/lock và fencing token nếu nhiều replica.
- Không chạy cleanup outbox/inbox khi còn publisher/consumer cần record.

Scheduled job chạy theo cron có thể trùng thời điểm shutdown. Dùng distributed lock/lease và durable checkpoint để tránh hai instance cùng thực hiện side effect.

## 24. Readiness, liveness và dependency health trong shutdown

Không nên biến mọi dependency outage thành readiness failure ngay từ đầu, cũng không nên để instance nhận traffic khi nó đã bắt đầu đóng.

Một số nguyên tắc:

- Readiness chuyển NOT_READY khi bắt đầu drain.
- Liveness tiếp tục phản ánh process có bị deadlock/hỏng không.
- Dependency health hiển thị tình trạng từng provider nhưng không nhất thiết loại instance khỏi load balancer.
- Khi shutdown, readiness không quay lại ACCEPTING_TRAFFIC.
- Health check không tạo request nặng tới dependency đang drain.
- Không để liveness restart process đang thực hiện một shutdown có kiểm soát.

Nếu dùng Spring Boot Actuator availability state, có thể tích hợp readiness state với orchestration. Kiểm tra endpoint health group và probe configuration thực tế.

## 25. Observability cho shutdown

Cần biết process đang ở phase nào và còn bao nhiêu công việc chưa hoàn tất.

| Metric | Ý nghĩa |
| --- | --- |
| shutdown_started_total | Số lần bắt đầu shutdown |
| shutdown_duration_seconds | Tổng thời gian shutdown |
| shutdown_phase_duration_seconds | Thời gian từng phase |
| shutdown_deadline_exceeded_total | Số lần vượt deadline |
| readiness_drain_seconds | Thời gian từ NOT_READY tới ngừng ingress |
| http_inflight_requests | Request HTTP đang chạy |
| message_inflight_count | Message handler đang chạy |
| message_settlement_pending | Message đã xử lý nhưng chưa ACK/Complete |
| outbox_inflight_publish_count | Event publisher đang gửi |
| outbox_pending_count | Event chưa được publish |
| executor_active_count | Task đang chạy |
| executor_queue_depth | Task đang chờ |
| checkpoint_lag | Khoảng cách tới vị trí đã commit |
| shutdown_forced_task_count | Task bị dừng khi hết deadline |

Log shutdown nên có:

- Shutdown reason/signal.
- Instance/pod ID và application version.
- Phase bắt đầu/kết thúc.
- In-flight count đầu/cuối phase.
- Số message đã Complete/Delete/ACK.
- Số message chưa settle và dự kiến redelivery.
- Outbox publish confirmation/unknown outcome.
- Checkpoint cuối cùng đã commit.
- Deadline còn lại và lý do force stop.

Không log payload nhạy cảm hoặc token. Dùng correlation ID trong log nhưng tránh đưa ID có cardinality cao vào metric label.

## 26. Kiểm thử graceful shutdown

Một unit test gọi close bean không đủ để chứng minh process xử lý SIGTERM đúng. Cần integration test và test trên runtime gần production.

### Test matrix

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không có request/message đang chạy | Dừng nhanh và sạch |
| HTTP request đang chạy, transaction commit trước deadline | Response hoàn tất hoặc client nhận kết quả có thể tra cứu |
| HTTP request chưa commit khi bị force stop | Transaction rollback; client retry không tạo duplicate |
| Message handler commit rồi shutdown trước ACK | Redelivery; inbox chặn side effect trùng |
| Message handler chưa commit khi hết deadline | Không ACK; broker giao lại |
| Outbox publish accepted nhưng chưa mark SENT | Có thể publish duplicate sau restart; consumer dedupe |
| Outbox publisher chưa gửi | Record còn pending và được worker sau xử lý |
| Stream record đã commit nhưng chưa checkpoint | Replay được dedupe |
| Checkpoint trước business commit | Test phải phát hiện nguy cơ mất tác động |
| Visibility/lock/ack deadline hết trong drain | Redelivery không gây duplicate business effect |
| Executor có task trong queue | Task durable được phục hồi; task best-effort được ghi nhận |
| Dependency unavailable trong shutdown | Process thoát trong budget, operation unknown được reconcile |
| Kubernetes gửi SIGTERM rồi hết grace | App dừng trước force kill hoặc để broker phục hồi |
| Rolling update nhiều replica | Traffic và message được tiếp nhận bởi replica còn lại |

### Failure injection

1. Gửi SIGTERM khi HTTP transaction đang chạy.
2. Gửi SIGTERM sau database commit nhưng trước response.
3. Gửi SIGTERM sau message commit nhưng trước ACK.
4. Làm broker lock/visibility/ack deadline hết hạn trong khi handler chạy.
5. Dừng outbox publisher ngay sau broker confirmation.
6. Dừng stream consumer sau business commit nhưng trước checkpoint.
7. Làm database chậm để drain vượt p99 dự kiến.
8. Làm dependency timeout và xác minh deadline tổng.
9. Để executor queue còn task khi hết shutdown grace.
10. Restart Pod và xác minh redelivery/replay không tạo side effect trùng.

### Kiểm thử trên managed service

- Dùng queue/topic/stream test riêng.
- Chạy đúng binder và cloud SDK version production.
- Đo thời gian stop listener và số in-flight handler.
- Kiểm tra message lock/visibility/ack deadline và delivery count.
- Đối chiếu inbox, business state, outbox và checkpoint sau restart.
- Chạy rolling update với nhiều replica để kiểm tra capacity còn lại.
- Không cố ý force kill production consumer đang xử lý giao dịch quan trọng.

## 27. Runbook khi instance phải dừng hoặc rollout

### Trước rollout

1. Xác nhận replica còn lại đủ capacity nhận traffic/message.
2. Kiểm tra queue backlog, processing lag và outbox pending age.
3. Kiểm tra handler p95/p99 và termination grace period.
4. Xác nhận readiness, SIGTERM và lifecycle config đã được triển khai.
5. Kiểm tra broker lock/visibility/ack deadline có phù hợp.
6. Tạm dừng batch/replay lớn nếu chúng tranh chấp capacity.

### Khi shutdown bắt đầu

1. Đánh dấu NOT_READY.
2. Ngừng nhận HTTP request mới.
3. Dừng listener/poller nhận message mới.
4. Dừng scheduler claim batch mới.
5. Chờ in-flight request/handler/publisher.
6. Commit rồi settle message; không settle công việc chưa commit.
7. Ghi nhận công việc chưa hoàn tất và deadline còn lại.

### Sau restart

1. Kiểm tra message redelivery và delivery count.
2. Xác minh inbox dedupe.
3. Kiểm tra outbox record còn PENDING/IN_FLIGHT đã được claim lại.
4. Kiểm tra checkpoint và replay từ offset an toàn.
5. Đối soát business operation có unknown outcome.
6. Theo dõi duplicate, backlog và error rate.

### Khi drain không hoàn tất

- Không kéo dài process vô hạn ngoài grace period.
- Để message chưa settle được redeliver.
- Giữ outbox record chưa xác nhận để publisher retry.
- Giữ checkpoint ở vị trí an toàn.
- Dùng idempotency/reconciliation để xử lý operation không rõ kết quả.
- Ghi lại phase và resource khiến shutdown bị chậm.

## 28. Bài thực hành: dừng Order consumer an toàn khi rollout

**Bối cảnh:** Spring Boot Order service chạy ba replica trên Kubernetes. Mỗi replica nhận HTTP request, consume OrderPaid từ một broker managed, cập nhật database và ghi ReceiptRequested vào outbox. Khi rolling update, một Pod có thể nhận SIGTERM trong lúc đang xử lý order hoặc publish event.

### Phần A — HTTP graceful shutdown

1. Bật graceful shutdown cho embedded server.
2. Cấu hình lifecycle timeout.
3. Khi shutdown bắt đầu, readiness chuyển NOT_READY.
4. Xác minh load balancer ngừng gửi request mới.
5. Gửi request đang chạy và SIGTERM; kiểm tra transaction/response.
6. Retry client với cùng idempotency key và xác minh không tạo order trùng.

### Phần B — Message consumer

1. Dừng receive/polling trước khi đóng database.
2. Đợi handler hiện tại commit inbox và business state.
3. ACK/Complete/Delete sau commit.
4. Nếu deadline hết, để message chưa commit được redeliver.
5. Restart Pod và xác minh duplicate được inbox xử lý.

### Phần C — Outbox publisher

1. Dừng poller claim record mới.
2. Đợi publish đang chạy nhận confirmation.
3. Chỉ mark SENT sau confirmation.
4. Kill publisher giữa broker acceptance và mark SENT.
5. Restart và xác minh cùng event ID được publish lại an toàn.

### Phần D — Kubernetes budget

1. Chọn terminationGracePeriodSeconds dựa trên drain và cleanup.
2. Nếu dùng preStop, tính thời gian hook vào grace period.
3. Kiểm tra readiness propagation.
4. Chạy rolling update khi còn ba replica.
5. Đo shutdown phase duration và số message chưa settle.

### Sản phẩm cần nộp

- Sơ đồ lifecycle shutdown của HTTP, listener, outbox và resource.
- Cấu hình Spring Boot graceful shutdown.
- Cấu hình Kubernetes readiness/termination grace period.
- Bảng timeout/lock/visibility/ack deadline theo broker.
- Bằng chứng test SIGTERM trong request và message handler.
- Bằng chứng outbox publish duplicate được deduplicate.
- Dashboard shutdown duration, in-flight count, pending settlement và checkpoint lag.
- Runbook rollout và recovery sau forced termination.

### Câu hỏi tự kiểm tra

1. Vì sao readiness drain không tự dừng message listener?
2. Spring Boot graceful web server shutdown bảo vệ phần nào?
3. Vì sao phải dừng nhận message mới trước khi đóng database?
4. Khi message đã commit nhưng chưa ACK, điều gì có thể xảy ra?
5. Vì sao ACK trước commit có thể làm mất nghiệp vụ?
6. Azure Service Bus lock, SQS visibility timeout và Pub/Sub ack deadline ảnh hưởng drain thế nào?
7. Vì sao Event Hubs/Kinesis checkpoint phải theo contiguous completed records?
8. Outbox publisher nên làm gì khi broker đã nhận event nhưng mark SENT chưa chạy?
9. Vì sao submit task vào executor không phải durable acceptance?
10. Spring Lifecycle phase ảnh hưởng thứ tự stop như thế nào?
11. Kubernetes preStop có tiêu thụ termination grace period không?
12. Khi hết shutdown deadline, message chưa commit nên được xử lý ra sao?
13. Vì sao client retry sau khi HTTP response bị mất cần idempotency key?
14. Làm sao kiểm tra shutdown thực sự graceful trong rolling update?
15. Những metric nào cho biết process bị buộc dừng khi còn công việc?

## 29. Ghi nhớ

- Graceful shutdown bắt đầu bằng việc ngừng nhận công việc mới, sau đó drain request/handler/publisher đang chạy và cuối cùng đóng tài nguyên.
- Readiness drain ngừng traffic HTTP; message listener/poller cần được pause/stop riêng.
- Spring Boot web server graceful shutdown không tự drain mọi binder, scheduler, executor hoặc cloud SDK.
- Commit business state trước ACK/Complete/Delete/checkpoint; nếu dừng trước ACK, redelivery được xử lý bằng inbox/idempotency.
- Event Hubs/Kinesis chỉ checkpoint qua các record đã hoàn tất liên tục; không vượt qua record chưa commit.
- Outbox publisher dừng claim mới, chờ publish đang chạy và chỉ mark SENT sau broker confirmation.
- Executor queue trong RAM không phải durable queue; chỉ ACK khi công việc hoặc ý định tiếp tục đã được lưu bền vững.
- Đóng listener/worker trước broker client và đóng database gần cuối để transaction còn hoàn tất.
- Termination budget phải tính readiness propagation, drain, settlement, cleanup và safety margin; preStop cũng tiêu thụ thời gian.
- Khi hết deadline, để message chưa settle được redeliver, giữ checkpoint an toàn và dùng idempotency/reconciliation để phục hồi.
- Kiểm thử SIGTERM trong HTTP request, message handler, outbox publish và stream checkpoint trên môi trường gần production.

## Tài liệu tham khảo

- [Spring Boot graceful shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Framework lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Kubernetes Pod termination lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Kubernetes probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Event Hubs checkpoints and processor](https://learn.microsoft.com/azure/event-hubs/event-processor-balance-partition-load)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Amazon Kinesis Data Streams consumers](https://docs.aws.amazon.com/streams/latest/dev/building-consumers.html)
- [Google Cloud Pub/Sub lease management](https://cloud.google.com/pubsub/docs/lease-management)
- [Google Cloud Pub/Sub flow control](https://cloud.google.com/pubsub/docs/flow-control)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Java ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
