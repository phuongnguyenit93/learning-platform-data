# ConsumerStoppedEvent

`ConsumerStoppedEvent` là application event do **Spring Kafka** phát ra khi một Kafka consumer thuộc listener container **đã dừng hoạt động**. Sự kiện này giúp ứng dụng quan sát vòng đời consumer, xác định nguyên nhân dừng và đưa ra cảnh báo hoặc quyết định khôi phục có kiểm soát.

Trong hệ thống chạy nhiều consumer thread, một consumer dừng không đồng nghĩa toàn bộ listener container đã dừng. `ConcurrentMessageListenerContainer` có thể quản lý nhiều consumer con và từng consumer có thể kết thúc với nguyên nhân riêng. Do đó, khi xử lý `ConsumerStoppedEvent`, cần phân biệt **consumer-level event**, **container-level event**, **consumer group rebalance** và **tiến độ offset**.

Tài liệu giải thích ý nghĩa của event, các giá trị `Reason`, cách đăng ký listener bằng Spring, mối liên hệ với Kafka transaction, graceful shutdown, restart policy, observability và runbook xử lý sự cố.

## 1. ConsumerStoppedEvent xuất hiện ở đâu trong lifecycle?

Spring Kafka listener container quản lý vòng `poll()`, gửi record cho phương thức `@KafkaListener` và điều phối acknowledgement/commit. Một vòng đời tiêu biểu gồm:

1. Container khởi tạo Kafka consumer và consumer thread.
2. Consumer tham gia group, nhận assignment và bắt đầu `poll()`.
3. Container gọi listener xử lý record, retry hoặc recovery khi có lỗi.
4. Offset được commit theo `AckMode` hoặc transaction policy khi đủ điều kiện.
5. Container được yêu cầu stop, hoặc consumer gặp một lỗi khiến nó phải ngừng.
6. Consumer dọn tài nguyên, đóng client và kết thúc vòng xử lý.
7. Spring Kafka phát lifecycle event, trong đó có `ConsumerStoppedEvent`.

~~~mermaid
sequenceDiagram
    participant A as Application / orchestration
    participant C as Listener container
    participant K as Kafka consumer thread
    participant E as Spring event observer
    A->>C: start()
    C->>K: Tạo consumer và bắt đầu poll
    K->>K: Subscribe, poll, xử lý records
    alt Dừng bình thường
        A->>C: stop()
        C->>K: Yêu cầu kết thúc
    else Lỗi khiến consumer phải dừng
        K->>K: Exception hoặc điều kiện dừng
    end
    K->>K: Cleanup và đóng consumer
    C->>E: ConsumerStoppedEvent(reason)
    E-->>C: Ghi nhận event, metric hoặc tín hiệu khôi phục
~~~

Sơ đồ mô tả luồng logic. Thứ tự chính xác giữa cleanup, các event phụ trợ và callback bất đồng bộ tùy phiên bản Spring Kafka và cấu hình application event multicaster.

### Điều gì KHÔNG được suy ra từ event?

Một `ConsumerStoppedEvent` không tự chứng minh:

- Mọi child consumer của container cha đều đã ngừng.
- Toàn bộ Spring Boot application đang shutdown.
- Consumer group đã hoàn tất rebalance.
- Record cuối cùng đã xử lý thành công.
- Offset cuối cùng chắc chắn được commit.
- Kafka transaction hoặc database transaction đã commit.
- Không còn worker nền xử lý dữ liệu đã nhận trước đó.
- Record chưa hoàn tất sẽ không được giao lại.

Đây là **tín hiệu lifecycle**, không phải chứng nhận thành công nghiệp vụ.

## 2. Phân biệt các event gần nhau

Spring Kafka cung cấp nhiều application event; chúng mô tả các thời điểm và phạm vi khác nhau.

| Event | Phạm vi | Mục đích |
|---|---|---|
| `ConsumerStartingEvent` | Consumer | Quan sát thời điểm bắt đầu khởi tạo consumer. |
| `ConsumerStartedEvent` | Consumer | Ghi nhận consumer đã bắt đầu hoạt động. |
| `ConsumerStoppingEvent` | Consumer | Quan sát bước consumer chuẩn bị ngừng. |
| **`ConsumerStoppedEvent`** | **Consumer** | **Ghi nhận consumer đã dừng và nguyên nhân dừng.** |
| `ContainerStoppedEvent` | Container | Biết listener container đã đạt trạng thái stopped. |
| `ConsumerFailedToStartEvent` | Consumer/container | Phát hiện consumer không khởi chạy được theo điều kiện thời gian. |
| `NonResponsiveConsumerEvent` | Polling health | Phát hiện consumer không phản hồi/poll như mong đợi. |
| `ListenerContainerIdleEvent` | Listener/container | Phát hiện consumer idle, không phải consumer đã dừng. |
| Rebalance callback | Topic/partition | Biết partition được giao, thu hồi hoặc đã mất ownership. |

Các class, constructor và giá trị event cụ thể phụ thuộc phiên bản Spring Kafka. Khi triển khai code phụ thuộc API, cần sử dụng đúng version mà dự án đang chạy.

### ConsumerStoppedEvent và ContainerStoppedEvent

Ví dụ một listener có `concurrency=3`:

~~~text
Container cha: ordersListener
    Child consumer 0: thread A
    Child consumer 1: thread B
    Child consumer 2: thread C

Stop cả container:
    A dừng -> ConsumerStoppedEvent
    B dừng -> ConsumerStoppedEvent
    C dừng -> ConsumerStoppedEvent
    Container kết thúc -> ContainerStoppedEvent
~~~

Vì vậy, có thể có nhiều `ConsumerStoppedEvent` trong một lần shutdown hợp lệ. Tránh gửi cảnh báo sự cố riêng cho từng event `NORMAL` khi ứng dụng đang rolling deploy.

Ngược lại, chỉ nhận một `ConsumerStoppedEvent` chưa đủ để khẳng định toàn container đã dừng. Hãy kiểm tra `ContainerStoppedEvent` hoặc trạng thái thực của container nếu mục tiêu là điều phối lifecycle ở cấp cha.

## 3. Reason: tại sao consumer dừng?

`ConsumerStoppedEvent` có phương thức `getReason()` biểu diễn nguyên nhân dừng do Spring Kafka phân loại. Các giá trị thường gặp trong những dòng Spring Kafka hỗ trợ cơ chế này gồm:

| Reason | Ý nghĩa | Hướng điều tra đầu tiên |
|---|---|---|
| `NORMAL` | Consumer dừng theo nhánh bình thường | Đối chiếu lệnh stop, shutdown, rolling deployment. |
| `ERROR` | Consumer dừng do một lỗi không thể tiếp tục xử lý bình thường | Xem exception gốc, container và broker logs. |
| `FENCED` | Dừng liên quan transactional producer bị fence | Kiểm tra `transactional.id`, producer epoch và deployment overlap. |
| `AUTH` | Dừng do authentication/authorization failure | Kiểm tra credential, TLS/SASL và ACL. |
| `NO_OFFSET` | Không tìm thấy vị trí offset hợp lệ khi policy không cho phép reset tự động | Kiểm tra group committed offset, retention và `auto.offset.reset`. |

Cần kiểm tra enum trong phiên bản Spring Kafka thực tế vì danh sách và cách phân loại có thể thay đổi. Không phải mọi exception từ `@KafkaListener` đều tạo `ERROR`. Một lỗi listener được `DefaultErrorHandler` xử lý bằng retry/DLT có thể không làm consumer dừng.

**Reason chỉ là phân loại ở mức lifecycle**, không thay thế exception stack trace. Đặc biệt, `FENCED` không nói chắc rằng ID trùng giữa hai pod; `AUTH` không cho biết ngay credential sai hay ACL thiếu; `ERROR` cũng không cho biết chính xác record nào khiến consumer dừng.

## 4. Đăng ký @EventListener cho ConsumerStoppedEvent

Spring application context có thể tiếp nhận event qua `@EventListener`:

~~~java
@Component
public class KafkaLifecycleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaLifecycleObserver.class);

    @EventListener
    public void handleStopped(ConsumerStoppedEvent event) {
        log.warn(
                "Kafka consumer stopped: reason={}, sourceType={}",
                event.getReason(),
                event.getSource().getClass().getSimpleName());
    }
}
~~~

Các import gồm `org.springframework.kafka.event.ConsumerStoppedEvent`, `org.springframework.context.event.EventListener`, `org.springframework.stereotype.Component` và SLF4J logger.

Handler chỉ ghi log nên ít rủi ro can thiệp vòng đời. Trong production, nên liên kết thêm instance ID, listener ID, group ID và timestamp theo những API/metadata thực tế mà phiên bản Spring Kafka cung cấp.

### Phân loại theo Reason

~~~java
@EventListener
public void handleStopped(ConsumerStoppedEvent event) {
    ConsumerStoppedEvent.Reason reason = event.getReason();

    switch (reason) {
        case NORMAL:
            log.info("Kafka consumer stopped normally");
            break;
        case FENCED:
            log.error("Transactional producer fenced");
            break;
        case AUTH:
            log.error("Kafka authentication/authorization problem");
            break;
        case NO_OFFSET:
            log.error("No valid starting offset");
            break;
        case ERROR:
            log.error("Kafka consumer stopped due to error");
            break;
        default:
            log.warn("Kafka consumer stopped, reason={}", reason);
    }
}
~~~

Code minh họa ngữ nghĩa xử lý, không phải một restart controller hoàn chỉnh. Với enum thay đổi giữa phiên bản, kiểm tra lại giá trị được hỗ trợ. Không nên chỉ dựa vào `reason` để tự động reset offset hoặc xoay credentials.

### Đếm stop event bằng Micrometer

~~~java
@Component
public class ConsumerStopMetrics {

    private final MeterRegistry registry;

    public ConsumerStopMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void record(ConsumerStoppedEvent event) {
        registry.counter(
                "kafka.consumer.stopped.total",
                "reason",
                event.getReason().name()
        ).increment();
    }
}
~~~

Ví dụ giả định Micrometer `MeterRegistry` đã được cấu hình. Counter này đếm **lần event được phát**, không phải số consumer đang stopped tại thời điểm hiện tại. Để đo current health, cần kết hợp trạng thái container/group và tín hiệu started/assigned.

## 5. Event handler có thể chạy trên consumer thread

Spring `ApplicationEventMulticaster` thường phát event đồng bộ theo mặc định. Vì vậy, `@EventListener` có thể chạy trên chính thread đang phát event, trong trường hợp Kafka lifecycle thường gần consumer/container thread.

Những hệ quả vận hành:

- Handler chặn lâu có thể kéo dài thời gian consumer dừng/cleanup.
- Một exception phát sinh từ handler có thể làm phức tạp luồng application events.
- Gọi lại thao tác lifecycle đồng bộ khi container còn stopping có thể gặp race hoặc deadlock.
- Handler không nên gọi database/network I/O không timeout.
- Không được dùng event như nơi xử lý lại record hoặc tự commit offset.

Nếu ứng dụng cấu hình multicaster bất đồng bộ, event handler có thể chạy trên executor khác. Khi đó càng không được giả định reference đến Kafka `Consumer` có thể được thao tác trên thread của handler.

### Nguyên tắc xử lý event an toàn

1. Ghi log, metric hoặc cập nhật trạng thái nội bộ nhẹ.
2. Trích xuất metadata cần thiết rồi gửi tín hiệu đến remediation service nếu cần.
3. Không giữ lâu reference tới container/consumer chỉ để dùng từ worker nền.
4. Không gọi `Thread.sleep` để chờ Kafka hồi phục.
5. Không trực tiếp restart mọi consumer từ callback.
6. Nếu phải điều khiển container, để một controller có kiểm tra trạng thái và backoff đảm nhiệm.

`ConsumerStoppedEvent` là nơi **phát hiện và thông báo** trạng thái, không phải nơi thực hiện mọi thao tác phục hồi.

## 6. NORMAL: consumer dừng có chủ đích

`NORMAL` thường tương ứng với việc application/container dừng theo kế hoạch:

- Spring Boot đang shutdown.
- Orchestrator yêu cầu pod kết thúc trong rolling deployment.
- Application gọi `stop()` cho listener container.
- Đội vận hành scale down workload.
- Một quy trình bảo trì dừng consumer có chủ đích.

Một event `NORMAL` phù hợp thời điểm deployment thường không cần paging. Tuy nhiên, nó vẫn cần được đối chiếu với số consumer còn lại và lag; nếu workload bị dừng nhưng không có instance thay thế, backlog có thể tăng.

### Graceful shutdown cần nhiều tín hiệu hơn

Khi dừng theo kế hoạch, cần kiểm soát:

- Record đang xử lý có được hoàn tất không?
- Các acknowledgements đã được commit đúng policy chưa?
- Kafka transaction đang mở có được commit/abort không?
- Worker nền có còn thao tác dữ liệu sau khi container dừng không?
- Consumer group có phân phối lại partition cho member còn hoạt động không?

`ConsumerStoppedEvent(NORMAL)` không trả lời tất cả các câu hỏi đó. Nó chỉ ghi nhận consumer dừng theo luồng mà Spring Kafka phân loại là bình thường.

## 7. FENCED: transactional producer đã mất quyền

Kafka producer transactional có `transactional.id` và producer epoch. Khi producer mới khởi tạo cùng ID hợp lệ, Kafka coordinator có thể fence producer đời cũ. Producer cũ gặp `ProducerFencedException` hoặc lỗi producer epoch ở thao tác transactional tiếp theo.

Trong Spring Kafka transactional listener, tình huống này có thể dẫn đến `ConsumerStoppedEvent` với reason `FENCED`.

~~~mermaid
sequenceDiagram
    participant A as Pod A - producer cũ
    participant K as Transaction coordinator
    participant B as Pod B - producer mới
    participant E as ConsumerStoppedEvent observer
    A->>K: transactional.id=X, epoch E1
    Note over A: A pause hoặc mất kết nối
    B->>K: initTransactions ID=X
    K-->>B: epoch E2
    A->>K: commit transaction với E1
    K-->>A: Producer fenced
    A->>E: ConsumerStoppedEvent(FENCED)
    E->>E: Ghi log và chuyển tín hiệu remediation
~~~

Một lần fencing producer cũ trong quá trình thay thế có thể là bảo vệ hợp lệ. Nhưng fencing lặp lại giữa các replica hợp lệ thường cho thấy collision `transactionIdPrefix` hoặc producer lifecycle có vấn đề.

### Hướng xử lý FENCED

1. Ghi nhận instance, `transactional.id`/prefix và thời điểm exception.
2. Kiểm tra tất cả replica/factory có thể tạo cùng ID.
3. Đối chiếu rollout overlap và process cũ chưa dừng.
4. Không tái sử dụng producer đã bị fence.
5. Đọc transaction outcome và committed offsets để xác định record cần xử lý lại.
6. Sửa mapping ID trước khi khởi động lại hàng loạt.
7. Theo dõi producer fencing, transaction abort và group lag sau remediation.

Đừng restart ngay lập tức trong vòng lặp nếu hai pod liên tục fence nhau. Restart sẽ không sửa được cấu hình identity trùng nhau.

## 8. AUTH: lỗi authentication hoặc authorization

Consumer có thể dừng do Kafka từ chối xác thực hoặc phân quyền. Nguyên nhân cụ thể có thể là:

- SASL username/password sai hoặc không đồng bộ.
- OAuth token hết hạn/chưa được làm mới.
- TLS certificate hết hạn hoặc cấu hình truststore sai.
- ACL không cho phép đọc topic hoặc join consumer group.
- Principal thay đổi sau rollout.
- Broker policy hoặc secret rotation thay đổi.

Trong các phiên bản Spring Kafka hỗ trợ, thuộc tính như `authExceptionRetryInterval` trên container properties có thể cho phép chờ và thử lại một số authentication exception thay vì dừng ngay. Nếu consumer dừng vì lỗi loại này, reason `AUTH` giúp observer phân loại.

Không nên chỉ đặt restart loop nhanh. Cần xác minh exception gốc, credential source, ACL và broker logs. Nếu credential chưa được sửa, restart chỉ gây thêm log, tải và rebalance.

### Hướng xử lý AUTH

1. Đối chiếu thời điểm lỗi với thay đổi secret/ACL/certificate.
2. Kiểm tra exception class cụ thể.
3. Kiểm tra consumer group/topic ACL, không chỉ bootstrap connectivity.
4. Xác minh pod đã mount đúng secret, certificate và env variables.
5. Nếu retry được, dùng interval/backoff hữu hạn theo policy.
6. Sau khi sửa, xác nhận consumer join group, poll và offset tiến.

## 9. NO_OFFSET: không có vị trí offset hợp lệ

Kafka lưu committed offset theo consumer group, topic và partition. Khi group chưa có committed offset hợp lệ, `auto.offset.reset` thường quyết định bắt đầu ở `earliest` hoặc `latest` nếu chính sách cho phép.

Nếu cấu hình `auto.offset.reset=none`, Kafka client có thể ném `NoOffsetForPartitionException` khi không có offset. Spring Kafka có thể dừng consumer và phát reason `NO_OFFSET`.

~~~yaml
spring:
  kafka:
    consumer:
      group-id: finance-reconciler
      enable-auto-commit: false
      auto-offset-reset: none
~~~

Cấu hình này phù hợp khi nghiệp vụ **bắt buộc** owner xác nhận điểm bắt đầu, nhưng có thể gây dừng consumer khi group mới hoặc partition mới chưa có committed offset.

### Hướng xử lý NO_OFFSET

1. Xác định group ID, topic, partition bị ảnh hưởng.
2. Kiểm tra committed offset và earliest/latest offsets còn trong log.
3. Xem group ID có đổi, partition count tăng hoặc retention xóa dữ liệu cũ không.
4. Xin quyết định nghiệp vụ về bắt đầu earliest/latest hay seed offset cụ thể.
5. Dừng consumer phù hợp trước khi thay đổi offset để tránh đụng commit đang chạy.
6. Đánh giá nguy cơ replay/duplicate hoặc bỏ qua dữ liệu trước khi áp dụng.
7. Khởi động lại, xác minh assignment và tiến độ.

Không đổi tự động mọi `NO_OFFSET` thành `latest`, vì có thể bỏ qua các record quan trọng chưa xử lý.

## 10. ERROR: consumer dừng bất thường

`ERROR` là nhóm lỗi tổng quát. Nó có thể xuất hiện khi vòng consumer kết thúc vì exception mà container không tiếp tục xử lý được. Nhưng **listener ném exception không nhất thiết khiến consumer dừng**.

Ví dụ listener lỗi tạm thời:
- `DefaultErrorHandler` có thể retry trong cùng partition.
- Sau khi hết retry, recoverer có thể publish DLT.
- Nếu recovery thành công, listener container có thể tiếp tục poll.
- Trong trường hợp đó có thể không có `ConsumerStoppedEvent(ERROR)`.

Khi có `ERROR`, cần xác định nguyên nhân gốc bằng stack trace, thread logs và trạng thái Kafka client. Kiểm tra serializer, deserializer, transaction manager, recoverer, broker connectivity và các exception ngoài retry policy.

### Đừng xây dựng auto-restart cho mọi ERROR

Một lỗi dữ liệu vĩnh viễn hoặc lỗi cấu hình không thay đổi qua restart. Restart liên tục tạo rebalance, thêm lag và làm che dấu nguyên nhân gốc. Hãy giới hạn số lần thử, backoff và chuyển sang cảnh báo khi vượt ngưỡng.

## 11. Rebalance không đồng nghĩa consumer stopped

Rebalance mô tả **phân phối partition** giữa các member, còn stop event mô tả **vòng đời consumer**.

Ví dụ nhóm có hai consumer A/B, bốn partition. Khi consumer C tham gia, một phần partition chuyển từ A/B sang C. A và B có thể vẫn chạy; chúng nhận các callback partition revoked/assigned nhưng **không nhất thiết** phát `ConsumerStoppedEvent`.

~~~text
Trước scale:
  Consumer A -> P0, P1
  Consumer B -> P2, P3

Sau scale:
  Consumer A -> P0, P1
  Consumer B -> P2
  Consumer C -> P3

Có rebalance, nhưng A và B chưa dừng.
~~~

`onPartitionsAssigned`, `onPartitionsRevoked` và `onPartitionsLost` quản lý ownership partition; không được dùng chúng như sự thay thế cho `ConsumerStoppedEvent`.

Với cooperative rebalance, các partition có thể được chuyển từng phần; số callback revoke/assign cũng không bằng số stop events.

## 12. Container concurrent: gom event theo scope

Spring Kafka `ConcurrentMessageListenerContainer` tạo nhiều child containers theo `concurrency`. Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: inventory-service
      enable-auto-commit: false
    listener:
      concurrency: 4
      ack-mode: record
~~~

Khi toàn bộ container dừng, có thể nhận bốn `ConsumerStoppedEvent` từ bốn child consumers. Event handler cần phân biệt theo listener/container và application instance.

Không dùng mỗi bộ đếm số stop event làm bằng chứng mọi consumer đã kết thúc, vì:
- Event có thể phát nhiều lần qua các lần restart.
- Application event multicaster bất đồng bộ không bảo đảm thứ tự callback.
- Một child consumer lỗi khi parent còn chạy.
- Listener ID hoặc concurrency có thể thay đổi qua deployment.

Dùng `ContainerStoppedEvent` và trạng thái container nếu cần xác nhận stop ở cấp parent; dùng consumer group membership nếu cần biết member Kafka đang hoạt động thực tế.

## 13. Lập chiến lược restart có kiểm soát

Một stop event bất thường thường cần remediation nhưng **không phải lúc nào cũng cần restart ngay**.

~~~mermaid
flowchart TD
    A[ConsumerStoppedEvent] --> B[Phân loại reason]
    B --> C{Shutdown có chủ đích?}
    C -->|Có| D[Ghi nhận expected stop]
    C -->|Không| E{Có thể tự phục hồi?}
    E -->|Không| F[Alert / sửa cấu hình hoặc offset]
    E -->|Có| G[Kiểm tra lifecycle container]
    G --> H[Áp dụng backoff và retry budget]
    H --> I[Controller thực hiện restart]
    I --> J[Kiểm tra started, assignment và poll]
    J --> K{Ổn định?}
    K -->|Có| L[Kết thúc remediation]
    K -->|Không| M[Escalation / ngăn restart loop]
~~~

Một restart controller nên:
1. Lưu **intentional shutdown flag** để không restart khi ứng dụng đang đóng.
2. Xác định đúng container/listener cần khôi phục.
3. Phân loại reason; `AUTH`/`NO_OFFSET` thường cần can thiệp trước.
4. Chỉ restart khi container ở trạng thái hợp lệ, không còn đang stopping.
5. Bảo đảm một controller duy nhất điều phối restart cùng listener.
6. Giới hạn số lần thử và dùng backoff có biên.
7. Xác nhận startup, assignment, poll và offset tiến sau restart.
8. Phối hợp với Kubernetes/systemd nếu orchestrator cũng quản lý liveness/restart.

### Anti-pattern

~~~java
@EventListener
public void handleStopped(ConsumerStoppedEvent event) {
    // Không khởi động lại container ngay cho mọi event:
    // registry.getListenerContainer("ordersListener").start();
}
~~~

Một handler đồng bộ gọi `start()` khi container còn trong shutdown có thể tạo race hoặc vòng lặp stop/start. Nếu cần restart, chuyển tín hiệu sang controller ngoài consumer thread và xác nhận lifecycle trước khi thao tác.

## 14. Offset, acknowledgement và redelivery khi consumer dừng

`ConsumerStoppedEvent` không phải offset commit barrier. Một record có thể đã cập nhật database thành công nhưng offset chưa kịp commit.

~~~text
Partition P0:
  offset 80: xử lý xong, committed offset 81
  offset 81: DB commit thành công
  consumer dừng trước khi commit offset 82
  member mới bắt đầu lại từ committed offset 81

Hệ quả: offset 81 có thể được xử lý lại.
~~~

Đó là hành vi at-least-once bình thường. Consumer cần idempotency, ví dụ `eventId` cùng unique constraint/inbox trong transaction database.

| Tình huống | Rủi ro | Cách giảm thiểu |
|---|---|---|
| DB update xong nhưng offset chưa commit | Record được giao lại, duplicate side effect | Inbox/idempotency. |
| Ack sớm rồi listener thất bại | Offset có thể tiến khi nghiệp vụ chưa hoàn tất | Ack sau xử lý. |
| Kafka transaction abort khi consumer dừng | Output và offset không được commit như transaction thành công | Transactional listener đúng wiring, `read_committed`. |
| Worker nền còn xử lý khi consumer stop | Tác động cũ có thể chạy sau rebalance | Ownership token, cancellation và idempotency. |
| DLT publish thất bại | Recovery chưa bền vững | Theo dõi send result, không commit recovery sai. |

Không tự reset offset, `seekToEnd` hoặc commit một offset mới chỉ vì thấy stop event. Offset cần được quyết định theo kết quả nghiệp vụ và policy đã phê duyệt.

## 15. Graceful shutdown với record đang xử lý

Để shutdown an toàn khi rolling deployment:

1. Orchestrator yêu cầu pod kết thúc.
2. Ứng dụng đánh dấu trạng thái đang shutdown có chủ đích.
3. Container dừng nhận thêm công việc theo lifecycle.
4. Listener hoàn tất hoặc rollback record đang xử lý.
5. Offset/transaction được commit hoặc abort theo policy.
6. Consumer đóng và phát `ConsumerStoppedEvent`.
7. Parent container đạt trạng thái stopped; có thể có `ContainerStoppedEvent`.
8. Application context đóng các tài nguyên còn lại.

Thời gian shutdown cần đủ cho công việc thông thường, nhưng không vô hạn. Nếu listener offload sang thread pool, container stop không tự bảo đảm worker đã dừng. Cần shutdown protocol và quản lý in-flight work riêng.

Không dùng `@EventListener` của stop event để cố xử lý nốt batch hoặc commit offset cuối; thiết kế đó dễ chạy sai thread và đụng lifecycle.

## 16. Transactional listener và producer fencing

Trong luồng Kafka consume–transform–produce, Spring Kafka có thể phối hợp output records và input offset trong cùng transaction. Nếu producer bị fence, transaction cũ không được phép commit hợp lệ; consumer có thể dừng và phát reason `FENCED`.

Cần kiểm tra:
- `transactionIdPrefix` của từng replica/factory có duy nhất không.
- Listener container có Kafka transaction manager đúng không.
- `KafkaTemplate` có tham gia cùng transaction của container không.
- Consumer downstream có `isolation.level=read_committed` khi cần không.
- Transaction và `max.poll.interval.ms` có phù hợp thời gian xử lý không.
- Database/HTTP có idempotency riêng không.
- Recovery sau rollback dùng `AfterRollbackProcessor` theo policy phù hợp.

Producer fencing, consumer group zombie fencing và `FencedInstanceIdException` của static member là các cơ chế khác nhau. Không suy ra từ một reason `FENCED` rằng mọi guarantee của pipeline đã được kiểm chứng.

## 17. Kiểm thử ConsumerStoppedEvent trong Spring test

Một test observer có thể thu event vào queue:

~~~java
@Component
public class ConsumerStopEventRecorder {

    private final BlockingQueue<ConsumerStoppedEvent> queue =
            new LinkedBlockingQueue<>();

    @EventListener
    public void record(ConsumerStoppedEvent event) {
        queue.offer(event);
    }

    public ConsumerStoppedEvent await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return queue.poll(timeout, unit);
    }
}
~~~

Các import có thể gồm `BlockingQueue`, `LinkedBlockingQueue` và `TimeUnit`. Đây là ví dụ test; production không nên giữ vô hạn event object chứa reference tới source/container trong queue.

### Các kịch bản test

- **Normal stop:** start listener container, đợi consumer chạy, gọi stop, xác nhận event và trạng thái container.
- **Concurrency:** cấu hình nhiều child consumers, quan sát stop events theo child nhưng không giả định thứ tự tuyệt đối.
- **NO_OFFSET:** group mới cùng `auto.offset.reset=none` và partition thiếu committed offset; xác minh behavior theo version.
- **AUTH:** cố ý dùng credential/ACL test bị từ chối; xác minh lỗi phân loại đúng và policy retry/stop.
- **FENCED:** dùng môi trường Kafka test để tạo producer collision có kiểm soát; không thử trên cluster production.
- **ERROR:** tạo lỗi thực sự khiến consumer dừng theo version; không giả định mỗi listener exception đều làm stop.
- **Shutdown intent:** chắc chắn observer không tự restart container đang dừng theo kế hoạch.

Kiểm tra cả container state và group assignment sau event; chỉ xác nhận queue nhận event chưa đủ chứng minh recovery thành công.

## 18. Monitoring và alerting

| Tín hiệu | Công dụng | Cách đọc đúng |
|---|---|---|
| Stop event count theo reason | Phân loại số lần consumer dừng | Là số sự kiện, không phải current down count. |
| Start event count | Phát hiện consumer khởi động lại | Dùng cùng stop count để nhận diện loop. |
| Container running/stopped | Trạng thái container cha | Không suy ra từ một child event. |
| Consumer group member count | Member Kafka hiện có | Phát hiện thiếu capacity sau stop. |
| Rebalance count/duration | Sự ổn định assignment | Không đồng nhất với stop count. |
| Lag theo partition | Backlog tăng khi member ngừng | Phân biệt source traffic và processing rate. |
| Committed offset | Điểm bắt đầu sau restart | Liên hệ với in-flight work và retry. |
| Transaction abort/fencing | Chẩn đoán reason `FENCED` | Đối chiếu prefix và rollout. |
| Authentication failures | Chẩn đoán `AUTH` | Credential, ACL, certificate. |
| No-offset errors | Chẩn đoán `NO_OFFSET` | Reset policy, retention, group ID. |

Đặt cảnh báo theo mức độ: `NORMAL` trong rollout thường chỉ cần ghi nhận; `AUTH` ảnh hưởng toàn group có thể cần cảnh báo; `NO_OFFSET` ở luồng nghiệp vụ quan trọng cần owner xem xét; `FENCED` lặp trên các replica hợp lệ cần điều tra transactional ID; `ERROR` kèm lag tăng/member count giảm cần được xử lý theo SLA.

Log nên có instance ID, listener ID, group ID, timestamp, reason, topic/partition liên quan khi có dữ liệu và exception class. Không đưa event ID/offset hoặc pod UID biến thiên lớn làm metric label; dùng chúng trong log/trace.

## 19. Runbook: Consumer dừng ngoài ý muốn

1. Ghi nhận reason, timestamp, instance, listener/container ID và group ID.
2. Xác định một child consumer hay toàn container đã dừng.
3. Tìm exception gốc trước event trong logs.
4. Kiểm tra group assignment, rebalance, broker health và consumer lag.
5. Đối chiếu committed offset, in-flight work và transaction outcome.
6. Phân loại: `AUTH`, `NO_OFFSET`, `FENCED`, `ERROR` hay stop có chủ đích.
7. Khắc phục nguyên nhân hoặc khởi động lại bằng controller có backoff.
8. Xác nhận consumer started, được assigned và tiếp tục poll.
9. Kiểm tra duplicate/recovery và side effect ngoài Kafka.

Không reset offset trong khi chưa rõ record cuối đã xử lý đến đâu.

## 20. Runbook: Consumer liên tục stop/start

1. Dựng timeline started/stopped events theo instance/listener.
2. Kiểm tra reason lặp lại và exception class.
3. Đối chiếu lịch deploy, autoscaling và liveness probe.
4. Kiểm tra nhiều restart controllers có cùng điều khiển container không.
5. Với `FENCED`: sửa identity collision, không chỉ tăng retry.
6. Với `AUTH`: sửa credentials/ACL.
7. Với `NO_OFFSET`: chốt offset policy có chủ đích.
8. Với `ERROR`: kiểm tra exception và policy stop/error handler.
9. Bật backoff, retry budget và escalation để ngăn rebalance storm.
10. Theo dõi lag và membership sau khi stabilise.

## 21. Runbook: NORMAL nhưng consumer group thiếu member

1. Đối chiếu expected shutdown/deployment với `ConsumerStoppedEvent(NORMAL)`.
2. Kiểm tra `ContainerStoppedEvent` và trạng thái container cha.
3. Đếm replica/consumer thực tế so với expected concurrency.
4. Kiểm tra pod thay thế đã started và join group chưa.
5. Xem partition đang bị giữ hoặc chờ session timeout không.
6. Kiểm tra readiness, scheduler, deployment rollout và ứng dụng khởi động thất bại.
7. Theo dõi lag theo partition để biết workload nào không còn owner xử lý.

`NORMAL` không phải cam kết high availability; nó chỉ cho biết nhánh stop của consumer bình thường.

## 22. Runbook: FENCED trong rolling deployment

1. Xác định process cũ/mới và khoảng thời gian overlap.
2. Kiểm tra `transactionIdPrefix` và `transactional.id` thực tế.
3. Phân biệt fencing producer cũ hợp lệ với hai pod độc lập dùng ID trùng.
4. Không tái sử dụng producer đã bị fence.
5. Kiểm tra Kafka transaction abort và committed offsets nguồn.
6. Kiểm tra output với consumer `read_committed` và idempotency DB/API.
7. Sửa identity/lifecycle trước khi restart hàng loạt.
8. Theo dõi lỗi fencing sau khi rollout hoàn tất.

## 23. Runbook: NO_OFFSET sau khi tăng partition

1. Xác định partition mới và group đang subscribe.
2. Kiểm tra `auto.offset.reset` có là `none` không.
3. Kiểm tra committed offset và log start/end offsets.
4. Xin quyết định nghiệp vụ về earliest/latest hoặc seed offset.
5. Xác định replay/bỏ qua backlog có được phép không.
6. Áp dụng thay đổi theo quy trình, tránh consumer commit song song khi reset.
7. Khởi động lại và xác minh assignment, poll, lag và offset.

## 24. Bảng kiểm soát ConsumerStoppedEvent

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng vận hành |
|---|---|---|
| Registration | `@EventListener` có nằm trong đúng Spring context? | Bean wiring và event logs. |
| Reason | Consumer dừng vì lý do gì? | `getReason()`, stack trace. |
| Scope | Một child hay toàn parent container đã stop? | Concurrency, `ContainerStoppedEvent`. |
| Intent | Stop có trùng shutdown/deploy theo kế hoạch? | Rollout timeline, lifecycle flag. |
| Threading | Handler có giữ consumer thread hoặc gọi KafkaConsumer sai thread? | Callback duration, executor policy. |
| Restart | Có backoff, retry budget, single controller? | Restart state, attempts. |
| Membership | Partition đã được giao lại, group có đủ member? | Consumer group assignment. |
| Offset | Record cuối cùng có commit đúng không? | Committed offsets, AckMode. |
| Transaction | `FENCED` có do producer collision hay replacement hợp lệ? | Prefix, epoch, transaction logs. |
| Idempotency | Redelivery có gây duplicate nghiệp vụ? | Event ID, inbox/unique constraint. |
| Observability | Stop/start, lag và lỗi được giám sát đúng mức? | Dashboards, alerts, runbooks. |

**Kết luận:** `ConsumerStoppedEvent` giúp quan sát khi một Spring Kafka consumer dừng và cung cấp `Reason` để phân loại shutdown bình thường, lỗi, producer fencing, authentication hoặc thiếu offset. Nó không tự khẳng định toàn container đã dừng, offset đã commit hay nghiệp vụ đã hoàn tất. Một giải pháp production cần liên kết event với container/group state, transaction/offset, exception logs và idempotency; giữ event handler nhẹ và điều phối restart có kiểm soát để tránh biến một sự cố thành vòng lặp rebalance.
