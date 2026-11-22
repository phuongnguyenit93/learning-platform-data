# Shutdown timeout và message còn trong queue trong Spring Integration Runtime

## Mục tiêu bài học

Trong **SPRING_INTEGRATION_RUNTIME**, một IntegrationFlow thường nhận message từ HTTP, broker, file hoặc database, chuyển qua **channel, endpoint, consumer, poller, executor**, rồi cập nhật **MessageStore**, DB hoặc dịch vụ ngoài. Khi deploy một phiên bản mới, scale down pod hay đóng JVM, một số message có thể đang nằm trong **QueueChannel**, một số đã được poller lấy ra và một số đang chạy dở trong worker thread.

Nếu shutdown quá nhanh, dữ liệu chưa được lưu bền vững có thể mất. Nếu chờ vô hạn để drain backlog, ứng dụng có thể không dừng được, bị orchestrator kill cưỡng bức hoặc làm chậm việc thay thế phiên bản. **Shutdown timeout và message còn trong queue** là bài toán cân bằng giữa **ngừng nhận mới, hoàn tất những việc có thể hoàn tất, bảo tồn những việc chưa hoàn tất và khôi phục an toàn sau restart**.

Bài thuộc chương **Vận hành** và sử dụng ngữ cảnh của module: quản lý lifecycle IntegrationFlow, transaction, retry, message store, error handling, correlation, threading, hiệu năng và trạng thái runtime.

Sau bài này, bạn có thể:

- Phân biệt **pause ingress, stop consumer, drain queue, graceful shutdown, forced termination** và **restart recovery**.
- Giải thích khi nào message trong **QueueChannel in-memory** có nguy cơ mất và khi nào **persistent ChannelMessageStore** giúp bảo tồn chúng.
- Hiểu **poller transaction** ảnh hưởng đến việc một message đã bị lấy khỏi store có được đưa lại sau rollback hay không.
- Phân biệt **Spring Boot shutdown phase timeout**, **Spring Integration orderly-shutdown timeout**, **Kubernetes termination grace period**, **HTTP/broker deadline** và **thời gian xử lý nghiệp vụ**.
- Chọn thứ tự dừng endpoint để **ngừng tạo backlog mới nhưng không dừng ngay consumer đang drain**.
- Kiểm tra **in-flight task, acknowledgement, transaction, retry, outbox, correlation và idempotency** trước khi công bố an toàn.
- Viết test cho shutdown khi queue còn message, timeout, crash, restart và nhiều replica.

> **Nguyên tắc:** Một timeout hết hạn **không chứng minh queue đã rỗng**; một queue đã rỗng **không chứng minh tất cả side effect đã commit**. Cần nhìn đồng thời **queued + in-flight + unacked + pending retry/outbox** và chính sách durability của từng lớp.

## 1. Điều gì có thể còn tồn tại ngay lúc shutdown?

Xét luồng:

~~~mermaid
flowchart LR
    B["Broker / file source"] --> I["Inbound adapter"]
    I --> D["DirectChannel"]
    D --> Q[("ordersQueue<br/>QueueChannel")]
    Q --> P["Polling consumer"]
    P --> E["Executor / handler"]
    E --> DB[("Business DB")]
    E --> H["HTTP / broker outbound"]
    E -. "Failure" .-> R["Retry / errorChannel"]
~~~

Tại thời điểm SIGTERM, các phần việc có thể ở trạng thái khác nhau:

| Trạng thái | Vị trí điển hình | Rủi ro khi process dừng |
| --- | --- | --- |
| **Chưa nhận** | Broker/topic, thư mục file, DB source | Nguồn có thể giữ lại nếu chính sách retention/ack phù hợp |
| **Đã nhận nhưng chưa enqueue** | Inbound adapter, DirectChannel, transformer | Handoff và ack có thể chưa đồng bộ; kiểm tra nguồn và transaction |
| **Đang chờ trong queue** | QueueChannel/MessageStore | Mất khi in-memory và JVM chết; có thể phục hồi nếu persistent và đã commit |
| **Đã dequeue, đang xử lý** | Poller, handler, executor | Transaction có thể commit, rollback hoặc bị cắt dở; external effect có thể đã xảy ra |
| **Đã commit business DB, chưa ack nguồn** | Handler → inbound adapter | Có thể bị redeliver khi restart; cần idempotency |
| **Đã ghi outbox, chưa publish** | Outbox pending | Publisher phải tiếp tục sau restart |
| **Đã publish, chưa mark published** | Outbox publisher / broker | Có thể publish lại; downstream cần dedup |
| **Đang chờ retry/recovery** | Retry queue, DLQ, MessageStore | Cần retention/durability và trạng thái cuối rõ ràng |

**Queue depth chỉ đo một phần công việc.** Khi một consumer gọi receive() và đã lấy message ra khỏi QueueChannel, số queued có thể giảm, trong khi handler đang giữ message đó thêm 20 giây để gọi DB/HTTP. Khi queued=0 nhưng in-flight=5, chưa thể kết luận drain xong.

### Bốn hành động thường bị gọi chung là “stop”

- **Pause ingress:** Ngừng nhận hoặc phát sinh message mới ở một hoặc nhiều inbound endpoints. Không tự xử lý phần backlog có sẵn.
- **Stop consumer:** Dừng endpoint lấy message ra xử lý. Nếu làm trước khi drain, backlog có thể còn nguyên.
- **Graceful / orderly shutdown:** Theo trình tự, ngừng nhận mới và cho công việc đang tồn tại một khoảng thời gian hoàn tất; sau đó đóng resource.
- **Forced termination:** Hết ngân sách hoặc process bị kill; trạng thái còn lại phải được khôi phục từ nguồn bền vững.

Đừng dùng **stop() thành công** hoặc **isRunning=false** của một inbound endpoint để suy ra mọi worker đã idle hay mọi message đã được ack.

## 2. Một timeline shutdown có backlog

Giả sử ordersQueue có **100 message**, polling consumer có **4 worker** và một message mất trung bình 500 ms để xử lý. Thông lượng lý tưởng lúc không có bottleneck khoảng **8 message/giây**; drain 100 message mất ít nhất khoảng **12,5 giây** nếu không có thêm message, overhead hoặc skew.

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Application / ingress
    participant Q as QueueChannel
    participant W as Poller / workers
    participant D as Business DB
    O->>A: SIGTERM / yêu cầu drain
    A->>A: Ngừng ingress mới
    Note over Q: 100 message còn chờ
    loop Trong shutdown budget
        W->>Q: receive một message
        Q-->>W: Message
        W->>D: Xử lý + commit
        D-->>W: Commit thành công
    end
    alt Queue rỗng và in-flight = 0
        A-->>O: Drained, có thể dừng consumer
    else Timeout gần hết
        A-->>O: Undrained: để state bền vững cho restart
    end
~~~

**12,5 giây không phải bảo đảm**: thời gian thực phụ thuộc maxMessagesPerPoll, số executor threads, DB pool, lock contention, retry, HTTP timeout, batch distribution, commit và acknowledgement. Nếu có một message treo 30 giây và chỉ bốn worker, thời gian đuôi có thể dài hơn nhiều.

### Hai kết quả shutdown hợp lệ nhưng khác nhau

**A. Drain hoàn toàn:** Ingress đã dừng, queue empty, in-flight empty, tất cả effect/commit và các ack cần thiết đã đạt trạng thái xác định. Có thể đóng process với ít việc cần phục hồi.

**B. Hết budget nhưng giữ được durability:** Một số message **chưa xử lý** vẫn nằm ở persistent store/broker; một số đang xử lý phải rollback/reconcile; process dừng và worker mới khôi phục. Đây có thể là thiết kế hợp lệ khi backlog quá lớn để drain trong một pod termination grace.

Thiết kế sai là **coi B như A** trong log/monitoring hoặc dùng QueueChannel in-memory rồi giả định message chắc chắn sẽ xuất hiện lại khi restart.

## 3. Nhiều loại timeout: cùng tên nhưng khác hợp đồng

| Đồng hồ | Điều nó giới hạn | Điều nó **không** tự bảo đảm |
| --- | --- | --- |
| **Spring Boot lifecycle timeout** | Thời gian chờ khi dừng một phase của SmartLifecycle beans theo LifecycleProcessor | Không tự drain toàn bộ QueueChannel của Spring Integration |
| **Orderly Shutdown stopActiveComponents(howLong)** | Tổng khoảng chờ theo hoạt động orderly shutdown của Spring Integration; tham số **milliseconds** | Không bảo đảm tất cả worker hoàn thành trước deadline, không tự persist queue RAM |
| **Kubernetes terminationGracePeriodSeconds** | Khoảng cho phép pod/container dừng trước khi bị kill theo cơ chế termination | Không tự động mở rộng timeout nội bộ của Spring Boot hay broker |
| **preStop hook duration** | Thời gian chạy thao tác preStop | **Tiêu tốn cùng Kubernetes grace budget**, không phải thời gian bổ sung |
| **HTTP/gateway timeout** | Thời gian chờ client/server cho một request | Request phía đối tác có thể vẫn thực hiện side effect |
| **Broker ack/visibility/lease timeout** | Khi nguồn xem message đã hoàn tất hoặc đủ điều kiện giao lại | Không chứng minh DB transaction/HTTP effect atomic |
| **Transaction timeout** | Thời hạn giao dịch theo transaction manager | Không rollback external HTTP/broker side effect tùy ý |
| **Queue receive timeout** | Một lần consumer đợi message tối đa bao lâu | Không phải shutdown deadline tổng |
| **Executor awaitTermination** | Thời gian chờ task của executor hoàn tất sau yêu cầu stop/shutdown | Không lưu lại task in-memory chưa chạy |

**Quan trọng:** Property **spring.lifecycle.timeout-per-shutdown-phase** là thời hạn **cho mỗi lifecycle phase**, không phải một đồng hồ cho toàn bộ process shutdown. Tổng shutdown có thể gồm nhiều phase và cleanup khác. Kubernetes nhìn vào **toàn bộ thời gian thực**, bao gồm preStop và các hoạt động còn lại.

### Cấu hình Spring Boot tối giản

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s

# Tùy phiên bản Spring Boot, graceful HTTP shutdown
# có thể là mặc định hoặc cần bật rõ:
server:
  shutdown: graceful
~~~

Property này hữu ích cho **SmartLifecycle** và web server lifecycle. Nó **không** tương đương việc gọi **IntegrationMBeanExporter.stopActiveComponents(...)** và không tự tạo một transaction giữa nguồn, queue và downstream. Cần kiểm tra phiên bản Spring Boot đang dùng và lifecycle của từng endpoint.

### Ví dụ ngân sách shutdown cho pod

Giả sử dự kiến:

~~~text
Kubernetes termination grace             : 90 s
  - preStop / ngừng ingress / propagation :  5 s
  - orderly drain mục tiêu                : 60 s
  - Spring lifecycle / resource close     : 15 s
  - dự phòng                              : 10 s
~~~

Đây là **bảng ngân sách minh họa**, không phải phép cộng bắt buộc của các thời gian Spring vì có thể có giai đoạn **chồng lấn** hoặc nhiều lifecycle phases. Điểm cần bảo đảm trong thực tế: mọi hoạt động blocking trên đường terminate không được vượt quá **Kubernetes grace tổng**, và vẫn có một khoảng dự phòng cho DB/client cleanup.

Không đặt **orderly-drain=90s** đồng thời **terminationGracePeriodSeconds=90** rồi còn chạy preStop=10s: Kubernetes có thể kill trước khi orderly drain xong.

## 4. Spring Integration Orderly Shutdown: dừng nguồn trước, để flow hoàn tất

Spring Integration có cơ chế **Orderly Shutdown**, được tài liệu mô tả qua JMX operation:

~~~java
// API của IntegrationMBeanExporter khi component này được cấu hình:
public void stopActiveComponents(long howLong);
~~~

Tham số **howLong** có đơn vị **milliseconds** và là thời gian cho phép hoạt động shutdown theo cơ chế exporter. Trình tự được tài liệu Spring Integration mô tả về mặt khái niệm:

1. Gọi **beforeShutdown()** trên các bean **OrderlyShutdownCapable** để chúng chuẩn bị ngừng tiếp nhận, ví dụ listener JMS/AMQP, TCP hoặc HTTP inbound tùy implementation.
2. Dừng một số **active message channels** như channel backed by JMS/AMQP nếu có.
3. Dừng các **MessageSource** để ngăn phát sinh dữ liệu mới.
4. Dừng các inbound **MessageProducer** còn lại không triển khai OrderlyShutdownCapable.
5. Cho các **in-flight messages** một khoảng thời gian còn lại để hoàn tất.
6. Gọi **afterShutdown()** trên các OrderlyShutdownCapable components để hoàn thành cleanup cuối.

Điểm đặc biệt: tài liệu giải thích thuật toán được cải thiện từ Spring Integration 4.1 nhằm **không dừng sớm toàn bộ poller/executor**, để message nằm giữa flow trong QueueChannel vẫn có thể được xử lý trong thời gian chờ. <https://docs.spring.io/spring-integration/reference/shutdown.html>

**Đây là phương thức quản trị được gọi một cách có chủ đích**, không nên giả định mọi ứng dụng Spring Boot tự gọi nó chính xác như vậy khi nhận SIGTERM. Khi thiết kế integration với shutdown process, phải xác minh exporter được bật, trigger thật sự được gọi và thứ tự của nó với Spring context close.

### Gọi orderly shutdown theo đường quản trị

Nếu ứng dụng đã cấu hình **IntegrationMBeanExporter**, code quản trị nội bộ có thể được cấp bean tham chiếu:

~~~java
import org.springframework.integration.monitor.IntegrationMBeanExporter;

final class OrderlyShutdownCommand {
    private final IntegrationMBeanExporter exporter;

    OrderlyShutdownCommand(IntegrationMBeanExporter exporter) {
        this.exporter = exporter;
    }

    void requestDrainBeforeShutdown() {
        // 30 giây, không phải 30 milliseconds.
        exporter.stopActiveComponents(30_000L);
    }
}
~~~

Đây là **một mảnh logic quản trị**, chưa phải cấu hình application đầy đủ. Phải có exporter/JMX management phù hợp với phiên bản project; không tự mở JMX port ra Internet. Nếu gọi từ **Control Bus** hoặc management endpoint, đầu vào phải được allowlist và xác thực, không thực thi biểu thức SpEL do client không tin cậy gửi.

**Không gọi stopActiveComponents hai lần từ các lifecycle callback khác nhau** mà chưa có hợp đồng idempotency hoặc đồng bộ hóa: hai quá trình shutdown có thể tranh cùng resource và làm log/trạng thái khó phân tích.

## 5. Message còn trong QueueChannel: local memory khác persistent store

**QueueChannel** là một **PollableChannel**. Nó nhận message vào queue và cho consumer gọi receive() để lấy message ra xử lý. Khác biệt lớn nhất khi shutdown là **queue được backing bởi gì**:

| Loại queue | Message đã enqueue sống qua process restart? | Nhận định |
| --- | --- | --- |
| **QueueChannel mặc định in-memory** | **Không** khi JVM thực sự chết | Dùng được khi chấp nhận mất message, test hoặc source có thể replay đáng tin cậy |
| **QueueChannel bounded in-memory** | **Không** | Giới hạn memory/backpressure, không tự có durability |
| **QueueChannel + JdbcChannelMessageStore** | Có thể, đối với bản ghi đã commit đúng cách | Cần bảng/schema, transaction, cấu hình store, serializer và quyền DB |
| **QueueChannel + Redis/Mongo backed store** | Phụ thuộc implementation và độ bền của backend | Xem consistency, eviction/persistence, transaction/ack của store cụ thể |
| **Broker-backed channel/source** | Phụ thuộc broker retention/ack/commit | Không đồng nhất với QueueChannel in-memory |

~~~mermaid
flowchart TD
    I["Message gửi vào QueueChannel"] --> Q{"Backing store?"}
    Q -- "In-memory" --> RAM[("JVM heap")]
    Q -- "Persistent" --> DB[("DB / persistent store")]
    RAM --> K["Kill JVM → state local biến mất"]
    DB --> REC["Restart → có thể đọc lại bản ghi đã commit"]
    REC --> CON["Consumer processing + idempotency"]
~~~

**Một bounded QueueChannel cũng vẫn là in-memory queue** nếu không cấu hình persistent store. Capacity giảm nguy cơ OOM, nhưng không biến message thành durable. Ngược lại, khi QueueChannel dùng **message-store**, cấu hình capacity của XML queue không được dùng chung theo cách của bounded in-memory queue; phải kiểm soát capacity/backpressure tại nguồn hoặc policy của store.

### Không dùng receive() chỉ để “đếm backlog”

Một lời gọi **receive() thành công sẽ lấy message khỏi queue**. Nếu management/health checker nhận thử message để kiểm tra còn bao nhiêu rồi bỏ qua, nó có thể làm **mất một phần việc** hoặc thay đổi transaction boundary. Dùng **metrics/management API hoặc thống kê store được hỗ trợ** để quan sát queue depth/age, không dùng một consumer giả đọc rồi bỏ.

## 6. Cấu hình QueueChannel bền vững và poller transaction

Một pattern thường dùng khi queue phải sống qua JVM restart là **JdbcChannelMessageStore**. Spring Integration phân biệt **JdbcMessageStore** tổng quát và **JdbcChannelMessageStore** được tối ưu cho channel.

### Ví dụ Java Configuration với PostgreSQL

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;

@Configuration
class DurableQueueConfiguration {

    @Bean
    JdbcChannelMessageStore ordersChannelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);

        // SQL nhận message phù hợp với PostgreSQL.
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        return store;
    }

    @Bean
    QueueChannel ordersQueue(JdbcChannelMessageStore ordersChannelStore) {
        return new QueueChannel(
                new MessageGroupQueue(
                        ordersChannelStore, "ordersQueue"));
    }
}
~~~

**Điều kiện bắt buộc trước khi đưa ví dụ vào production:**

1. Cần dependency **spring-integration-jdbc**, DataSource và schema **INT_CHANNEL_MESSAGE** cùng bảng/liên quan theo hướng dẫn phiên bản đang dùng.
2. **MessageGroupQueue groupId="ordersQueue" phải ổn định qua restart** nếu muốn cùng logical queue. Thay groupId sau deploy có thể làm message cũ tồn tại nhưng không còn được queue mới đọc tới.
3. **JdbcChannelMessageStore cần ChannelMessageStoreQueryProvider** phù hợp RDBMS; ví dụ trên dùng PostgreSQL.
4. Cấu hình vùng **region**, bảng, schema, account database và index phù hợp khi chia sẻ store giữa nhiều flow hoặc instance.
5. Payload/headers phải serialize/deserialize được sau restart và nâng version; đặc biệt thận trọng với replyChannel/errorChannel chứa object chỉ tồn tại trong JVM.
6. Cần giới hạn luồng nhận, batch, backpressure và monitor backlog; persistent store không tự bảo vệ DB khỏi queue tăng vô hạn.

Ví dụ này tạo queue và store, **chưa cấu hình consumer/transaction**. Chỉ riêng việc đặt JdbcChannelMessageStore chưa đủ để bảo đảm một message đã được dequeue nhưng handler lỗi sẽ được đưa lại đúng cách.

### Ví dụ XML polling consumer có transaction

Một lựa chọn dễ đọc cho ranh giới transaction là:

~~~xml
<int:service-activator
        input-channel="ordersQueue"
        ref="orderProcessor"
        method="handle">
    <int:poller fixed-delay="500" max-messages-per-poll="5">
        <int:transactional
                transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

Đây là **mảnh cấu hình XML**; cần khai báo namespace integration, bean orderProcessor, ordersQueue và transactionManager tương thích với DataSource của JdbcChannelMessageStore trong file cấu hình đầy đủ.

**Vì sao transaction ở poller quan trọng?** Với transactional persistent store như JdbcChannelMessageStore, nếu **poller thực hiện receive() trong transaction** và xử lý downstream đồng bộ trong phạm vi transaction đó, việc remove message chỉ được commit vĩnh viễn khi transaction thành công. Nếu xử lý ném exception dẫn đến rollback, thao tác dequeue được rollback, để message có cơ hội được nhận lại. Đây là điểm được Spring Integration Reference nêu rõ. <https://docs.spring.io/spring-integration/reference/channel/configuration.html>

### So sánh hai timeline

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant Q as JDBC Queue Store
    participant H as Handler
    participant D as Business DB
    Note over P,D: Poller transaction bao cả receive và xử lý đồng bộ
    P->>Q: receive/remove trong transaction
    Q-->>P: Message EV-42
    P->>H: handle EV-42
    H->>D: update
    alt Handler thành công
        P->>D: COMMIT transaction
        Note over Q: Dequeue commit
    else Handler throw + rollback
        P->>D: ROLLBACK
        Note over Q: Message còn có thể được poll lại
    end
~~~

**Không được suy luận điều này cho tất cả topology.** Nếu poller nhận từ DB store rồi đưa message qua **ExecutorChannel** sang thread khác, transaction của poller **không tự chuyển sang worker**. Poller có thể commit dequeue trước khi worker thực hiện business effect. Message đã ra khỏi queue persistent nhưng còn là task trong executor memory; forced shutdown có thể khiến phần việc mất.

### Một lỗ hổng điển hình dù có JdbcChannelMessageStore

~~~text
JDBC QueueChannel.receive() (transaction A)
    → ExecutorChannel.submit(task)
    → transaction A COMMIT và xóa message khỏi JDBC queue

Worker B đang xếp hàng trong executor (in-memory)
    → process bị kill
    → task biến mất
    → JDBC QueueChannel không còn row để replay
~~~

Để bảo vệ đoạn async, cần thay đổi kiến trúc: giữ **handoff bền vững** tới durable work queue/broker, cấu hình transaction/ack hợp lệ hoặc đưa worker vào một điểm tiêu thụ bền vững riêng. Đừng chỉ tăng shutdown timeout để chữa rủi ro atomicity giữa dequeue và enqueue in-memory.

## 7. Tính đúng đắn khi message đã bị dequeue nhưng chưa commit

Đặt tên các mốc:

~~~text
T0  Message M ở JDBC QueueChannel (đã commit)
T1  Poller bắt đầu transaction
T2  QueueChannel.receive() loại M trong transaction
T3  Handler cập nhật business DB
T4  Handler gọi external HTTP API
T5  Transaction commit/rollback
T6  Adapter/broker ack hoặc outbound publish
~~~

### Nếu cùng một DataSource và cùng transaction

Khi **queue dequeue + business DB update** thuộc cùng transaction phù hợp, rollback có thể khôi phục cả hai. Tuy vậy, transaction manager, propagation và tài nguyên thực tế phải tương thích; một transaction khác dùng DataSource khác **không tự atomic**.

### Nếu side effect ở HTTP

Giả sử tại T4 provider đã xử lý thành công, rồi transaction DB rollback tại T5. Message quay lại queue; lần sau có thể gọi HTTP lần nữa.

~~~text
M vẫn còn để replay trong JDBC queue
  + provider đã charge một lần
  → redelivery cần stable idempotencyKey / reconciliation
~~~

Vì vậy một persistent queue và poller transaction **bảo vệ delivery state** trong DB tương thích, **không tạo exactly-once side effect** với dịch vụ ngoài.

### Nếu worker bị interrupt khi shutdown

Thread có thể bị interrupt trong lúc chờ lock, sleep hoặc network operation. Tùy adapter/client, interrupt có thể hủy thao tác hoặc để trạng thái remote **chưa biết**. Handler cần:

- Phục hồi interrupt flag khi bắt InterruptedException, hoặc truyền exception theo hợp đồng để outer transaction quyết định rollback.
- Không catch InterruptedException rồi **return success** nếu nghiệp vụ chưa hoàn tất.
- Phân biệt **cancelled before effect** và **unknown outcome after request**.
- Tránh giữ DB transaction mở trong một HTTP call không có deadline.

Ví dụ handler bị interrupt khi chờ một nguồn:

~~~java
try {
    boolean ready = latch.await(10, java.util.concurrent.TimeUnit.SECONDS);
    if (!ready) {
        throw new IllegalStateException("Operation deadline exceeded");
    }
    persistResult();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Interrupted during shutdown or cancellation", interrupted);
}
~~~

**Đây là fragment minh họa**, cần triển khai latch và persistResult ở môi trường test/ứng dụng cụ thể. Mục đích là **không báo xử lý thành công giả** khi thread bị ngắt trước khi hoàn tất.

## 8. Đừng dừng consumer trước khi drain queue

Một runbook sai:

~~~text
1. Stop poller nhận đơn mới.
2. Stop luôn polling consumer đọc QueueChannel.
3. Wait until ordersQueue depth == 0.
~~~

Nếu không còn consumer, queue **không thể tự drain**. Một runbook đúng theo hướng an toàn:

~~~mermaid
flowchart TD
    A["Bắt đầu shutdown / pause"] --> B["Ngừng inbound producers"]
    B --> C["Giữ downstream pollers/handlers chạy"]
    C --> D{"Queue còn message?<br/>In-flight còn task?"}
    D -- "Có và còn budget" --> E["Tiếp tục xử lý / retry có giới hạn"]
    E --> D
    D -- "Không" --> F["Đóng downstream & resources"]
    D -- "Có và hết budget" --> G["Chốt state pending, log/metric"]
    G --> H["Stop theo hợp đồng; chuẩn bị restart/replay"]
    F --> I["Process exit"]
    H --> I
~~~

### Một quy trình pause–drain–stop cụ thể

1. **Quiesce ingress:** dừng các inbound endpoints hoặc yêu cầu nguồn không gửi thêm. Cần tính tất cả replica và các producer khác.
2. **Xác minh:** Inbound rate giảm, các endpoint mục tiêu thực sự ngừng nhận mới và không bị auto-start lại.
3. **Tiếp tục consumer:** giữ các poller đọc QueueChannel và worker đủ tài nguyên để xử lý backlog.
4. **Theo dõi:** queue depth, **oldest queued message age**, in-flight, active DB transaction, retry/DLQ/outbox pending.
5. **Đạt tiêu chí drain:** không còn message chờ và in-flight đã có outcome rõ ràng, không còn side effect chưa xác nhận trong phạm vi phải hoàn tất.
6. **Dừng downstream:** đóng poller, executor và resource sau khi không còn công việc cần chạy trong JVM, theo thứ tự phù hợp.
7. **Nếu quá hạn:** không tuyên bố drain thành công; bảo toàn state persistent và đảm bảo lần khởi động sau có recovery path.

**Chú ý:** Quiesce ingress không phải đóng toàn bộ network connection ngay lập tức. Ví dụ một inbound adapter có request đang xử lý có thể cần hoàn tất hoặc trả response đúng theo lifecycle/transport contract. Các loại adapter có cách stop khác nhau.

### Điều kiện drain nên do ứng dụng định nghĩa

Một tiêu chí minh họa:

~~~text
ingressAcceptingNewMessages == false
AND queueBacklog == 0
AND activeHandlers == 0
AND sourceInFlightUnacked == 0
AND noUnresolvedEffectWithinShutdownScope == true
~~~

Những biến trên là **business/operational metrics do bạn định nghĩa**, không phải các method built-in giống nhau của mọi adapter. Nếu hệ thống cho phép durable outbox pending sống qua restart, điều kiện có thể coi **outbox pending đã được lưu bền vững** là đủ, không nhất thiết bắt publish hết trước process exit.

## 9. Đo in-flight: queue rỗng vẫn có thể chưa an toàn

Một tracker tối giản cho handler synchronous hoặc worker:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class InFlightTracker {
    private final AtomicInteger active = new AtomicInteger();

    void execute(Runnable work) {
        active.incrementAndGet();
        try {
            work.run();
        } finally {
            active.decrementAndGet();
        }
    }

    int activeCount() {
        return active.get();
    }
}
~~~

Sử dụng trong service activator:

~~~java
@ServiceActivator(inputChannel = "ordersProcessing")
public void handle(Message<OrderCommand> message) {
    inFlightTracker.execute(() -> orderService.process(
            message.getPayload()));
}
~~~

**Hai đoạn code này là fragment**, cần định nghĩa OrderCommand, orderService, bean wiring và import phù hợp. Chúng chỉ đo khoảng thời gian **method được gọi đến method return/throw**, không bao gồm:

- Message đang nằm trong **executor queue chưa được chạy**.
- DB transaction commit do proxy **sau khi method return** nếu tracker đặt bên trong method.
- Broker ack diễn ra sau handler.
- HTTP effect đang chạy ở một async callback khác.
- Event vẫn pending trong outbox/MessageStore.

Nếu metric in-flight phải biểu diễn việc **đã commit/đã ack**, hãy instrument tại ranh giới thật của transaction và nguồn, không chỉ dùng counter bao quanh method body.

### Chờ drain với deadline hữu hạn

Ví dụ một helper quan sát **tracker**, không tương đương full shutdown coordinator:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

final class DrainWaiter {
    static boolean awaitZero(InFlightTracker tracker, Duration limit) {
        long remaining = limit.toNanos();
        long deadline = System.nanoTime() + remaining;

        while (tracker.activeCount() != 0) {
            remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                return false;
            }
            LockSupport.parkNanos(
                    Math.min(remaining, TimeUnit.MILLISECONDS.toNanos(20)));
            if (Thread.currentThread().isInterrupted()) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return true;
    }
}
~~~

**Không gọi helper này trên executor duy nhất đang chạy các handler cần drain**: thread chờ có thể chiếm slot cần cho việc xử lý. Với shutdown thực, còn cần stop ingress, queue depth, ack status và persistence; dùng **CompletableFuture, latch, condition hoặc event-driven signal** phù hợp để tránh polling dày.

## 10. Nếu shutdown timeout hết nhưng queue vẫn còn message

Đến deadline, **không có một thao tác “ép tất cả message hoàn tất” an toàn cho mọi trường hợp**. Quyết định phải dựa trên loại queue và state:

| State còn lại | Chiến lược phù hợp | Điều tuyệt đối không suy diễn |
| --- | --- | --- |
| Message chưa lấy trong **in-memory QueueChannel** | Cần drain trước shutdown hoặc đã có nguồn replay bền vững | Không tự tồn tại sau JVM restart |
| Message chưa lấy trong **persistent QueueChannel** | Giữ record đã commit, consumer mới đọc tiếp | Không chắc message đã từng dequeue ngoài transaction vẫn còn |
| Task nằm trong **executor queue in-memory** | Hoàn thành trước deadline hoặc dùng durable handoff/replay trước đó | Stop executor có thể làm task biến mất |
| Message đang trong poller transaction DB | Rollback/commit theo transaction manager; kiểm tra connection và interrupt | Timeout không tự chứng minh rollback thành công |
| Broker delivery chưa ack | Dựa adapter/broker redelivery/offset semantics | Không mặc định “handler throw chắc chắn redeliver” |
| HTTP side effect có kết quả chưa biết | Lưu UNKNOWN, dùng idempotency/reconciliation | Timeout không chứng minh remote chưa xử lý |
| Outbox pending đã commit | Cho publisher mới gửi tiếp với eventId ổn định | Đừng xóa pending chỉ vì app dừng |
| Aggregator group incomplete | Giữ persistent MessageGroupStore/metadata và policy expiry | Group bị xóa không thể tái tạo nếu không còn nguồn replay |

### Hết budget không phải tín hiệu để gọi queue.clear()

Xóa QueueChannel, dọn bảng INT_CHANNEL_MESSAGE, reset MetadataStore hoặc force-ack broker chỉ để đạt một đồ thị queueDepth=0 có thể biến một tình huống **có thể khôi phục** thành mất dữ liệu. Cần có runbook riêng cho **poison messages, DLQ và retention**, không trộn vào shutdown cleanup.

### Thiết kế shutdown có quyền kết thúc mà không mất việc

Mục tiêu production không nhất thiết là “xử lý sạch mọi backlog trước khi pod chết”; khi backlog lớn, điều này có thể không khả thi trong termination grace. Mục tiêu mạnh hơn là:

1. Ngừng tạo thêm việc mới tại instance đang chết.
2. Hoàn tất phần đang chạy nếu còn thời gian.
3. Với phần chưa hoàn tất, giữ **durable state hoặc source replay guarantee**.
4. Khi restart/instance khác nhận lại, **idempotency** chặn side effect trùng.
5. Có observability và reconciliation cho outcome chưa chắc chắn.

## 11. Tác động của broker, file adapter và gateway khi stop

Một Flow có QueueChannel ở giữa có thể nhận message từ rất nhiều nguồn. Việc shutdown **adapter** quyết định một message còn được nguồn giữ, có thể redeliver, hay đã được coi là hoàn tất.

| Inbound source | Điều cần xác minh | Rủi ro nếu chỉ nhìn QueueChannel |
| --- | --- | --- |
| **JMS listener/adapter** | Session transaction, ack mode, listener container stop, redelivery | Message đã ack khi đưa vào QueueChannel in-memory, nhưng worker chưa xử lý |
| **AMQP/RabbitMQ inbound** | Auto/manual ack, requeue, publisher confirm, consumer cancel, prefetch/unacked | Broker có thể giao lại khi connection chết; idempotency phải chịu duplicate |
| **Kafka inbound** | Offset commit, poll/consumer lifecycle, record processing boundary, rebalance | Offset đã commit nhưng task còn trong executor memory có thể gây mất việc |
| **File inbound** | Accept-once filter, file rename/move, source metadata, checkpoint | File được đánh dấu đã thấy nhưng payload in-memory bị mất khi kill |
| **FTP/SFTP inbound** | Remote/local filter, download staging, file permission, remote retention | Download xong chưa chắc business effect đã commit |
| **JDBC polling source** | Câu SQL chọn row, update status/claim, transaction | Row đã đánh dấu consumed nhưng chưa giao vào durable processing queue |
| **HTTP inbound gateway** | Request đang mở, load balancer drain, timeout và response | HTTP response đã thành công không chứng minh asynchronous worker đã hoàn tất |

**Mỗi adapter có ack/commit riêng**, vì vậy không có công thức chung “dừng consumer rồi message chắc chắn sẽ quay lại”. Phải đọc contract của adapter, mode acknowledgement, transaction manager và cấu hình container/version đang dùng.

### Ví dụ: broker → QueueChannel in-memory

~~~text
Broker record EV-42
   → inbound adapter nhận
   → QueueChannel in-memory nhận thành công
   → broker offset/ack có thể được commit theo adapter contract
   → process bị kill trước khi downstream poll
~~~

Nếu nguồn **đã xem việc giao vào QueueChannel là hoàn tất**, broker không bắt buộc redeliver EV-42; message chỉ còn trong heap cũ và bị mất. Đây là lỗi **mối nối giữa acknowledgement của ingress và durability của handoff**, không chỉ là shutdown timeout nhỏ.

**Giải pháp kiến trúc:** Nếu cần giữ at-least-once, bảo đảm điểm ack của nguồn đến **sau một handoff bền vững được xác nhận** hoặc toàn bộ xử lý có transaction/ack phù hợp; dùng broker/durable queue đúng nghĩa, tránh để ack phụ thuộc một thao tác enqueue in-memory.

### Ví dụ: broker unacked → redelivery sau kill

~~~text
Broker record EV-43 (chưa ACK)
   → handler gọi HTTP thành công
   → JVM chết trước ACK
   → broker phát lại EV-43
~~~

Trong trường hợp này **không mất delivery**, nhưng có thể **lặp side effect**. Giữ **business eventId/idempotencyKey** qua redelivery, áp dụng inbox/outbox hoặc kiểm tra version/unique constraint tương thích với nghiệp vụ.

### File adapter: không xóa hoặc reset checkpoint tùy tiện

Một file đã được nhận có thể được một AcceptOnce filter ghi vào MetadataStore. Khi restart:

- Store in-memory có thể quên file và đọc lại; cần idempotency để tránh xử lý trùng.
- Store persistent có thể nhớ file và bỏ qua; nếu handoff sau filter chưa được lưu bền vững thì có thể **mất nghiệp vụ**.
- Một file có thể đã được **move/delete** theo workflow trước khi business transaction hoàn tất, gây khó replay.

Lựa chọn an toàn thường là **giữ file gốc hoặc staging/replay mechanism** cho tới khi có durable checkpoint, và xác định rõ lúc nào filter/metadata đại diện cho “đã thấy file” so với “đã xử lý xong”.

## 12. Kubernetes: preStop, SIGTERM và terminationGracePeriodSeconds

Khi pod bị xóa do rollout/scale down, Kubernetes bắt đầu quá trình termination. Nếu có **preStop hook**, hook chạy trong grace period. Sau đó container runtime yêu cầu process dừng; nếu hết hạn, container có thể bị kill cưỡng bức.

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant P as Pod / process
    participant I as Spring Integration
    K->>P: Pod Terminating, bắt đầu grace countdown
    opt preStop hook
        K->>P: Chạy preStop
        P->>I: Quiesce ingress nếu được thiết kế
    end
    K->>P: TERM (sau preStop)
    P->>I: Spring context shutdown/lifecycle
    I->>I: Hoàn tất in-flight trong budget còn lại
    alt Kết thúc trước deadline
        P-->>K: Normal exit
    else Grace period hết
        K->>P: Force kill
        Note over I: Chỉ durable/replay state còn có cơ hội phục hồi
    end
~~~

Một mảnh cấu hình cho pod:

~~~yaml
# Fragment thuộc PodSpec/Deployment.spec.template.spec
terminationGracePeriodSeconds: 90

containers:
  - name: order-worker
    image: example.com/order-worker:1.0
    # Các field container khác được cấu hình trong manifest thực.
~~~

**Đây là fragment minh họa**, không phải deployment manifest hoàn chỉnh. Nếu có preStop, nó **dùng chung thời gian trong 90 giây**. Đừng dùng preStop với một sleep quá dài mà không hiểu tình trạng drain: thời gian sleep đó giảm thời gian Spring còn lại sau TERM.

### Readiness, termination và broker consumer là những chuyện khác nhau

- Đưa **readiness=false** có thể giúp load balancer/service không gửi **HTTP traffic mới** tới pod, nhưng propagation và existing connections có độ trễ.
- Readiness HTTP **không tự dừng Kafka/JMS/AMQP consumer**; listener phải có lifecycle/stop logic tương ứng.
- Với consumer group, khi một replica rời group, broker có thể **rebalance** và cho replica khác nhận partition/record theo protocol. Cần chống duplicate nếu trước đó effect đã commit nhưng offset chưa.
- Nếu dùng một **preStop HTTP call** tới management API, endpoint đó cần hoạt động khi pod Terminating, được xác thực và không nhận biểu thức điều khiển tùy ý.

### Quản lý PID 1 và tín hiệu

Nếu Java được chạy thông qua một shell wrapper không chuyển tiếp tín hiệu đúng cách, SIGTERM có thể không tới JVM, khiến graceful shutdown không diễn ra như mong đợi. Kiểm tra entrypoint, init process, signal forwarding và cách container thực sự nhận TERM.

**Không dựa vào SIGKILL hoặc lỗi OOM để chạy cleanup:** Khi JVM bị kill cưỡng bức, **@PreDestroy, shutdown hook, transaction callback** có thể không được gọi. Chính vì vậy durable queue/replay và idempotency là một yêu cầu độc lập với cơ chế shutdown đẹp.

### Spring Boot graceful web shutdown không tự điều khiển poller

Spring Boot hỗ trợ graceful shutdown của embedded web server, với cơ chế đóng connection/request riêng và timeout-per-shutdown-phase. Với ứng dụng worker vừa có web Actuator vừa có JMS/Kafka/file poller:

- Web server không nhận HTTP request mới **không chứng minh** inbound broker/file đã ngừng.
- Đóng ApplicationContext có thể stop các SmartLifecycle beans theo phase, nhưng điều đó không tự đảm bảo backlog đã drain trước khi consumer bị stop.
- Nếu dùng **Spring Integration Orderly Shutdown** trong runbook, cần chủ động xác nhận khi nào nó chạy trong tiến trình tổng, tránh hai cơ chế cùng tranh deadline hoặc stop nhầm thứ tự.

## 13. Lifecycle, SmartLifecycle và thứ tự dừng

Spring Framework dùng **Lifecycle** và **SmartLifecycle** để khởi động/dừng các bean theo context. SmartLifecycle có **phase** và hỗ trợ dạng stop với callback; trong quá trình context stop, bean có phase cao thường dừng trước bean phase thấp theo cơ chế lifecycle processor.

Điều này quan trọng vì:

~~~text
ordersInboundAdapter  (source)
   → QueueChannel
   → ordersProcessingPoller (consumer)
   → outbound handler
~~~

Mục tiêu drain đòi hỏi **source dừng nhận mới trước**, còn **consumer tiếp tục** đủ lâu. Nhưng thứ tự SmartLifecycle không tự biết đây là quan hệ ingress→queue→consumer trong business flow của bạn.

**Cần kiểm tra:**

1. ID/bean/phase của từng endpoint có đúng với flow đang chạy không?
2. Một endpoint có **autoStartup=true** khi context khởi động lại không?
3. Stop có ngăn **lượt poll mới** hay còn có hoạt động đang chạy dở?
4. Có executor/scheduler nào bị stop sớm hơn worker cần drain?
5. Thời gian stop của một bean có callback async; timeout cho phase đó kết thúc ở đâu?
6. Một **IntegrationFlow dynamic** được đăng ký bằng IntegrationFlowContext cần lifecycle/registration management riêng không?

**Lưu ý:** Gọi Control Bus trực tiếp **@ordersInboundEndpoint.stop()** có thể dùng để pause, nhưng nó chỉ nhắm vào bean/instance đó. Nó **không** khiến các endpoint khác tự dừng đúng thứ tự, và một replica mới sau restart có thể auto-start nếu desired state không được lưu.

### Thủ tục quản trị nhiều instance

Nếu hệ thống có ba replica, cần:

~~~text
desiredState(order-import) = DRAINING

replica A: ingress stopped, queued=0, inFlight=0
replica B: ingress stopped, queued=12, inFlight=3
replica C: ingress running, queued=0, inFlight=0
~~~

Từ snapshot này không thể thông báo “toàn cluster đã pause”. Replica C vẫn nhận message; B chưa drain. Một **management coordinator** cần tập hợp trạng thái, stop đúng instance, xử lý node mới gia nhập và quyết định deadline cho từng pod.

Nếu dùng **shared persistent QueueChannel**, các replica cùng đọc phải dùng đúng cơ chế concurrency/locking của store; đừng nghĩ rằng một con số queueDepth của A nhất thiết đại diện cho toàn cluster.

## 14. Shutdown không phải transaction: duplicate, outbox và correlation

Kịch bản nguy hiểm:

~~~mermaid
sequenceDiagram
    participant Q as Persistent QueueChannel
    participant W as Worker
    participant D as DB
    participant H as External API
    Q->>W: Dequeue eventId=EV-42
    W->>D: Commit business update
    W->>H: POST external operation
    H-->>W: Thành công
    Note over W: SIGTERM / worker bị kill trước checkpoint cuối
    Q->>W: EV-42 có thể replay sau rollback/restart
    W->>H: Gọi lại nếu thiếu idempotency?
~~~

**Message được giao lại không nhất thiết là lỗi.** Nếu transaction nguồn chưa commit, replay là hành vi phù hợp at-least-once. Side effect ngoài transaction có thể đã xảy ra.

Để an toàn:

- Dùng **eventId/operationId ổn định**, không dùng attemptId hay Spring MessageHeaders.ID làm idempotency key.
- Với thay đổi DB, dùng **transactional inbox/unique constraint** kết hợp business update trong cùng transaction.
- Với event outbound, dùng **transactional outbox**, publisher có thể publish lại nhưng downstream idempotent.
- Với HTTP payment hoặc API có external effect, dùng **idempotency key phía đích** và đối soát khi timeout/connection reset.
- Giữ **correlationId** để debug nhiều attempt, nhưng correlationId không mặc định là khóa dedup của một business operation.
- Với aggregator/MessageGroupStore, kiểm tra release/expiry/late arrival sau restart; group complete không đồng nghĩa downstream effect đã được xác nhận.

### Trạng thái UNKNOWN phải được lưu bền vững

Nếu shutdown ngắt một external request sau khi đã gửi:

~~~text
REQUESTED → IN_FLIGHT → UNKNOWN_OUTCOME
                        ↓
                    RECONCILING
                        ↓
                  CONFIRMED / FAILED
~~~

Không tự chuyển UNKNOWN_OUTCOME thành FAILED chỉ vì JVM bị kill trước khi nhận response. Retry thiếu idempotency khi provider đã commit có thể tạo double charge, double email hoặc external event trùng.

### Kho nào là nguồn sự thật?

| Nguồn | Nó biết gì? | Không tự biết gì? |
| --- | --- | --- |
| QueueChannel/MessageStore | Message đang tồn tại trong queue/group | External side effect đã thực hiện chưa |
| Broker source | Delivery/ack/offset theo protocol | DB business commit ngoài phạm vi source |
| Business DB/inbox | Business update và eventId đã commit | HTTP provider outcome nếu không được đối soát |
| Outbox | Event đã ghi chờ publish hoặc đã mark sent | Downstream consumer đã áp dụng effect chưa |
| External provider | Trạng thái charge/request theo provider reference | Internal queue state của ứng dụng |

Do đó, **queue depth=0** là một tín hiệu vận hành, không phải sổ cái chứng minh mọi operation đều thành công.

## 15. Observability: biết thật sự đã drain hay chỉ hết thời gian

Khi vận hành, cần quan sát cả **trạng thái lifecycle** và **trạng thái công việc**. Một Dashboard chỉ có queue size có thể che khuất task đang chạy.

| Metric / tín hiệu | Định nghĩa quan trọng | Cách đọc khi shutdown |
| --- | --- | --- |
| **ingress.accepting** | Instance còn nhận message mới hay không | Phải chuyển sang false ở ingress cần quiesce |
| **inbound.delivery.rate** | Số lần nhận message theo adapter | Cần giảm sau pause; không đồng nghĩa broker đã ngừng publish |
| **queue.depth** | Số message đang chờ trong một queue cụ thể | Nên giảm khi drain; không gồm message đã dequeue |
| **queue.oldest.age** | Tuổi message chờ lâu nhất, khi đo được | Phân biệt backlog mới vs tồn đọng lâu |
| **poller.running / poll.count** | Poller còn hoạt động và thực hiện lượt poll không | Consumer cần tiếp tục khi đang drain |
| **handler.in_flight** | Số handler đang được thực thi | Cần chạm 0 trước khi coi xử lý trong process hoàn tất |
| **executor.active / executor.queued / rejected** | Task đang chạy, task chờ, task bị từ chối | Không bỏ qua queue nằm ngoài QueueChannel |
| **transaction.commit / rollback** | Outcome theo transaction resource | Kiểm tra message được remove bền vững hay rollback |
| **source.unacked** | Delivery đã cấp nhưng nguồn chưa ack, nếu adapter cung cấp | Có thể được redeliver khi instance dừng |
| **retry.pending / DLQ.pending** | Công việc đang chờ phục hồi | Có thể hợp lệ nếu đã lưu durable |
| **outbox.pending** | Event commit nhưng chưa publish thành công | Phải có publisher phục hồi sau restart |
| **shutdown.elapsed / budget.remaining** | Thời gian dùng và còn lại của lần shutdown | Phát hiện quá hạn và dành dự phòng cleanup |
| **shutdown.outcome** | drained, timed_out_with_durable_pending, aborted/error | Không dùng một Boolean success cho mọi trường hợp |

**Metric có định nghĩa:** Queue depth từ JdbcChannelMessageStore có thể là snapshot với transaction/replica khác đang thay đổi. Hãy đánh dấu **application, flow, queue, instance/region** phù hợp; không dùng **eventId/correlationId** làm Micrometer tag vì cardinality rất cao. Business IDs nên nằm trong log/trace đã được bảo vệ.

### Ví dụ log shutdown có cấu trúc

~~~text
operation=ORDERLY_SHUTDOWN
application=order-worker
instance=order-worker-2
phase=DRAINING
ingressAccepting=false
queueName=ordersQueue
queued=31
inFlight=4
executorQueued=0
retryPending=2
outboxPending=7
budgetRemainingMs=18000
result=IN_PROGRESS
~~~

Khi hết deadline:

~~~text
operation=ORDERLY_SHUTDOWN
instance=order-worker-2
phase=FINALIZING
queued=19
inFlight=2
remainingWorkDurable=true
result=TIMED_OUT_WITH_DURABLE_PENDING
recoveryMode=RESTART_REPLAY
~~~

Đây là **format ứng dụng tự định nghĩa**. Không gán remainingWorkDurable=true chỉ từ việc JdbcChannelMessageStore được cấu hình: cần kiểm chứng còn work nào đã dequeue sang executor, external side effect chưa xác nhận hoặc broker đã ack sớm.

### Những alert đáng có

- Shutdown phase vượt deadline, process bị kill trước khi cleanup xong.
- Số message queued **không giảm** dù ingress đã pause và poller được cho chạy.
- Queue depth=0 nhưng **in-flight không về 0** sau deadline.
- Message store không thể ghi/đọc, backlog không phục hồi sau restart.
- Executor queue tăng và rejected tasks xuất hiện trong lúc drain.
- Outbox/retry pending **age** vượt SLA dù pod mới đã chạy.
- Duplicate **business side effect** xuất hiện sau rollout, không chỉ duplicate delivery.
- Một replica mới auto-start ingress trong khi desired state vẫn PAUSED/DRAINING.

## 16. Ước lượng thời gian drain và chọn shutdown budget

Một phép ước lượng sơ bộ:

\[
T_{drain} \approx \frac{Q}{\min(\lambda_{consumer}, \lambda_{DB}, \lambda_{external})} + T_{tail}
\]

Trong đó:

- **Q**: số message đang chờ, không gồm in-flight.
- **lambda_consumer**: thông lượng xử lý hữu hiệu của consumer/poller.
- **lambda_DB, lambda_external**: giới hạn throughput do resource downstream.
- **T_tail**: thời gian đuôi của công việc còn đang chạy, retry, commit và final acknowledgment.

Đây chỉ là **ước lượng capacity** khi ingress đã ngừng. Nếu dữ liệu vẫn tiếp tục được đưa vào, cần dùng **net drain rate = processing rate – ingress rate**; khi net rate gần 0, drain có thể không bao giờ kết thúc.

Ví dụ:

~~~text
Queued = 1200
Processing capacity ổn định = 40 message/s
Không có ingress mới
→ Ước lượng phần queue khoảng 30 s

Nhưng:
P99 external call = 15 s
Retry backlog đáng kể
→ Deadline 30 s có thể không đủ.
~~~

**Không lấy thông lượng trung bình lúc ít tải** làm bảo đảm shutdown. Trong lúc rollout, DB có thể đang được bảo trì, broker rebalance và nhiều replica cùng drain; tốc độ thường khác normal operation.

### Cách chọn ngân sách thực tế

1. Đo **p95/p99 handler duration**, queue wait, throughput, retry backoff và DB commit latency.
2. Xác định cần drain **toàn bộ queue** hay chỉ **in-flight work**, phần còn lại được phép replay.
3. Tính budget cho **preStop, ingress quiescence, drain, lifecycle close và safety margin**.
4. Đảm bảo orchestrator cho phép ít nhất khoảng đủ theo **tổng thời gian thực**, không cộng nhầm các timeout độc lập thành một cơ chế tự động.
5. Chạy chaos/drain test với backlog và external latency xấu hơn bình thường.
6. Đo tỷ lệ **drained** so với **timed_out_with_durable_pending** trong nhiều lần rollout, không chỉ dựa trên một case thành công.

## 17. Unit test: dừng consumer không làm queue tự rỗng

Đây là một bài test nhỏ với QueueChannel in-memory. Nó **không mô phỏng JVM restart**, chỉ chứng minh message được giữ trong queue **khi chưa có consumer nào lấy ra**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class QueuePendingTest {

    @Test
    void queuedMessagesRemainUntilAConsumerReceivesThem() {
        QueueChannel queue = new QueueChannel(2);

        assertTrue(queue.send(
                MessageBuilder.withPayload("EV-1").build()));
        assertTrue(queue.send(
                MessageBuilder.withPayload("EV-2").build()));

        // Khi consumer đang stop hoặc không tồn tại, queue không tự drain.
        Message<?> first = queue.receive(0);
        Message<?> second = queue.receive(0);

        assertNotNull(first);
        assertNotNull(second);
        assertEquals("EV-1", first.getPayload());
        assertEquals("EV-2", second.getPayload());
        assertNull(queue.receive(0));
    }
}
~~~

**Giới hạn:** Test dùng QueueChannel in-memory nên không chứng minh durability. Nó không kết luận gì về transaction, broker ack, executor task hoặc SIGTERM. Muốn xác minh state sau JVM restart, phải dùng **store persistent thật**, đóng process rồi khởi động process mới.

### Test chờ in-flight có timeout

Sử dụng helper InFlightTracker và DrainWaiter ở phần 9, cùng CountDownLatch để không phụ thuộc Thread.sleep:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class InFlightDrainTest {

    @Test
    void returnsFalseWhenWorkStillRunsAtDeadline()
            throws Exception {
        InFlightTracker tracker = new InFlightTracker();
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Future<?> task = executor.submit(() ->
                tracker.execute(() -> {
                    started.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                    }
                }));

        try {
            assertTrue(started.await(2, TimeUnit.SECONDS));
            assertEquals(1, tracker.activeCount());
            assertFalse(DrainWaiter.awaitZero(
                    tracker, Duration.ofMillis(100)));
        } finally {
            release.countDown();
            task.get(2, TimeUnit.SECONDS);
            executor.shutdownNow();
        }

        assertEquals(0, tracker.activeCount());
    }
}
~~~

Test này chứng minh **timed wait không báo drained khi handler còn chạy**. Nó **không** chứng minh queue đã rỗng hoặc side effect đã commit, vì tracker mới chỉ đếm các method đang thực thi.

## 18. Integration test: kill process sau dequeue hoặc sau business commit

Đối với các hệ thống cần độ tin cậy cao, test nên dùng **PostgreSQL + broker/test transport** và hai lần chạy application trong **hai process/container khác nhau**, giữ nguyên dữ liệu trong store.

### Kịch bản A — QueueChannel persistent còn 20 message

1. Tạo schema và JdbcChannelMessageStore với **groupId ổn định**.
2. Gửi 20 message, xác minh chúng đã được commit trong store.
3. **Không start polling consumer**; đóng hoặc kill application process.
4. Khởi động lại một process khác dùng **cùng DB, region/groupId và serializer**.
5. Start poller, đợi 20 message được xử lý, assert mỗi **eventId** hoàn tất đúng một kết quả nghiệp vụ.
6. Kiểm tra không còn pending row khi các transaction xử lý hoàn tất.

**Giá trị chứng minh:** Message đã nằm bền vững trong queue có thể sống qua restart. Không chứng minh những task đã được dequeue nhưng vẫn trong executor memory.

### Kịch bản B — Poller transaction rollback khi handler lỗi

1. Cấu hình poller transaction bao cả receive từ JdbcChannelMessageStore và xử lý đồng bộ.
2. Đưa một message EV-42 vào queue, cho handler ném exception có kiểm soát.
3. Xác minh transaction rollback.
4. Để poller thử lại theo retry policy phù hợp; lần sau cho handler thành công.
5. Assert business DB chỉ có một kết quả cuối, queue message được xóa khi commit thành công.

**Giá trị chứng minh:** Dequeue gắn với transaction cho phép replay sau rollback trong topology đã cấu hình. Không áp dụng cho mọi loại MessageStore hoặc async handoff.

### Kịch bản C — Crash sau DB commit nhưng trước ack

1. Sử dụng broker source có ack/offset chưa được commit trước thời điểm kiểm thử.
2. Cho handler commit một business side effect và ghi inbox/outbox nếu có.
3. Chèn fault checkpoint trước ack; **kill worker process**, không graceful shutdown.
4. Khởi động lại worker hoặc replica khác, quan sát redelivery.
5. Assert **business side effect không bị áp dụng thêm lần nào** dù delivery/handler attempt có thể tăng.

**Giá trị chứng minh:** Idempotency và recovery hoạt động khi commit/ack không atomic.

### Kịch bản D — Deadline hết khi executor còn task

1. Dùng executor nhỏ, CountDownLatch giữ một worker và tạo hàng chờ.
2. Yêu cầu shutdown với deadline hữu hạn; xác minh trạng thái **TIMED_OUT_WITH_PENDING** thay vì DRAINED giả.
3. Mở latch hoặc kill process ở điểm đã định.
4. Nếu hệ thống yêu cầu replay, kiểm tra task có được lưu **durable trước khi handoff**; nếu không, test phải phơi bày nguy cơ mất việc.

**Không thể biến một task queue trong JVM thành durable chỉ bằng test**. Nếu kiến trúc đang thiếu durable handoff, phải sửa thiết kế chứ không sửa assertion.

### Kịch bản E — Kubernetes rollout với nhiều replica

1. Triển khai hai hoặc nhiều replica, tạo backlog và message đang in-flight.
2. Thực hiện rollout/scale down để kích hoạt termination thật.
3. Xác minh pod nhận TERM, preStop nếu có và application đi qua trạng thái DRAINING.
4. Quan sát queue depth, in-flight, source unacked và shutdown budget trên từng replica.
5. Khi một pod chết, replica khác xử lý tiếp từ **broker/store bền vững** mà không double side effect.
6. Tái diễn với backlog lớn hơn khả năng drain để kiểm thử **timeout path**, không chỉ happy path.

**Test với Ctrl+C trong IDE không đủ**: IDE có thể terminate process theo cơ chế khác với container SIGTERM, và restart graceful không mô phỏng kill cưỡng bức.

## 19. Tình huống chẩn đoán thường gặp

### Tình huống A — Graceful shutdown báo xong, nhưng 300 message mất

**Dấu hiệu:**

~~~text
ordersQueue (in-memory): 300 messages
Inbound adapter: stopped
Polling consumer: stopped
ApplicationContext: closed normally
After restart: ordersQueue empty
~~~

**Nguyên nhân có khả năng:** QueueChannel chỉ sống trong JVM; context đóng sạch không có nghĩa framework tự persist message đang chờ. Nếu nguồn đã ack trước khi đưa vào queue, nó cũng có thể không redeliver.

**Cách xử lý:** Dùng persistent ChannelMessageStore hoặc một durable transport, kiểm chứng điểm ack/handoff và thêm shutdown state check. Nếu tiếp tục chấp nhận in-memory queue, phải có hợp đồng replay từ nguồn và đo được queue pending khi quá hạn.

### Tình huống B — JdbcChannelMessageStore có data nhưng sau restart poller không thấy

**Dấu hiệu:** Bảng INT_CHANNEL_MESSAGE vẫn có row, nhưng flow mới không nhận được.

**Cần kiểm tra:**

1. **groupId/queue name, region và table prefix** có thay đổi sau deploy không?
2. Ứng dụng mới có kết nối **đúng database/schema** và quyền đọc không?
3. Poller endpoint có **isRunning=true** và scheduler hoạt động không?
4. QueryProvider có tương thích PostgreSQL/DB đang dùng không?
5. Payload/header serializer có decode được dữ liệu đã ghi bằng bản cũ không?
6. Những row đó có thực sự thuộc **logical queue** mà instance mới đọc không?
7. Transaction hoặc DB lock từ consumer khác có làm hàng chờ không?

**Không tự xóa bảng** để “hết backlog”: việc đó có thể xóa toàn bộ message chưa xử lý.

### Tình huống C — ordersQueue depth=0 nhưng shutdown mãi không xong

Có thể có:

- Handler in-flight đang chờ HTTP response.
- Executor queue đã lấy việc khỏi QueueChannel nhưng chưa chạy.
- DB transaction đang block trên row/lock.
- RetryAdvice đang backoff hoặc poller còn xử lý batch.
- Kafka/JMS container đang đợi commit/ack hoặc rebalance.

**Đo thêm:** handler.inFlight, executor active/queued, transaction age, external call latency và source unacked. Đừng kết luận “framework không stop đúng” chỉ vì queued=0.

### Tình huống D — Hết 60 giây rồi Kubernetes vẫn kill trước khi drain

**Timeline ví dụ:**

~~~text
Kubernetes grace = 60 s
preStop consumes 15 s
Spring lifecycle may need 35 s
Extra cleanup needs 15 s
Total sequential demand = 65 s > grace
~~~

Kubernetes bắt đầu grace countdown **trước preStop**. Vì vậy việc set **spring.lifecycle.timeout-per-shutdown-phase=45s** không tạo thêm 45 giây bên ngoài grace. Cần đo thời gian thực, rút ngắn preStop nếu phù hợp, ưu tiên durable pending và điều chỉnh budget có dự phòng.

### Tình huống E — Message bị xử lý hai lần sau deploy nhưng không mất

Đây có thể là **hành vi redelivery hợp lệ** của broker hoặc rollback queue transaction khi worker bị ngắt. Nếu external effect đã thành công trước đó, handler mới có nguy cơ lặp.

**Cách sửa:** Giữ eventId/idempotency key qua restart, dùng inbox/unique constraint, optimistic version, outbox và đối soát outcome. Không cố “chữa duplicate” bằng ack thật sớm khi nghiệp vụ chưa hoàn tất, vì như vậy có thể chuyển lỗi từ trùng thành **mất message**.

### Tình huống F — Vừa stop ingress vừa stop consumer nên backlog đứng yên

**Nguyên nhân:** Không còn consumer đọc queue. **Cách sửa:** Phân biệt trạng thái STOP_INGRESS với DRAINING. Để downstream polling consumer/worker tiếp tục chạy đến khi đạt tiêu chí hoặc budget cạn; chỉ sau đó mới stop downstream.

### Tình huống G — Queue nhỏ đi nhưng DB bị duplicate

Queue depth giảm có thể chỉ là kết quả **dequeue**, không có nghĩa xử lý business thành công. Nếu handler retry sau HTTP timeout, một số message có thể tạo side effect trùng dù mỗi message chỉ bị lấy một lần từ queue.

**Kiểm tra:** eventId, MessageHeaders.ID, transaction commit, retry owner, provider request ID và idempotency; phân biệt **delivery count**, **handler attempts** và **business operation completion**.

## 20. Runbook vận hành một lần shutdown có queue pending

Đây là một quy trình tham khảo cho service có **broker inbound → persistent QueueChannel → polling consumer → DB/outbound**. Điều chỉnh theo phiên bản Spring Integration, loại adapter và điều kiện cluster.

### Pha 0 — Trước khi rollout

Ghi baseline: queue depth/oldest age, in-flight count, throughput, transaction latency, unacked deliveries, retry/outbox pending, number of replicas, shutdown deadline, source ack semantics. Kiểm tra đường recovery và business idempotency đã được test.

**Quyết định quan trọng trước khi bắt đầu:** Khi hết deadline mà còn message, có **nguồn replay/durable store được xác minh** không? Nếu câu trả lời là **không** và không được phép mất message, không tiếp tục rollout theo cơ chế stop bình thường; cần sửa kiến trúc hoặc xử lý backlog trước.

### Pha 1 — Quiesce nguồn vào

Phát trạng thái **DRAINING** hoặc PAUSED cho đúng instance/flow. Stop những inbound endpoints cần ngừng, giảm readiness HTTP nếu phù hợp và xác minh adapter đã ngừng nhận mới. Với multi-replica, thu thập trạng thái toàn bộ node liên quan.

**Không stop consumer đọc queue ở pha này.** Giữ thread pool, scheduler và DB connections phục vụ xử lý backlog.

### Pha 2 — Drain trong budget

Giữ poller/handler chạy, theo dõi các meter mỗi chu kỳ với deadline hữu hạn. Tính **queued + executorQueued + inFlight + sourceUnacked + unresolved external outcomes** thay vì chỉ nhìn QueueChannel.

Nếu lỗi transient xảy ra, để retry có giới hạn và backoff phù hợp; nếu dữ liệu invalid, chuyển recovery/quarantine theo contract. Đừng tạo retry vô hạn khiến drain không bao giờ kết thúc.

### Pha 3 — Quyết định tại deadline

| Điều kiện | Quyết định |
| --- | --- |
| Queue empty, in-flight empty, các commit/ack quan trọng xác định | **DRAINED**, đóng downstream/resource |
| Queue còn nhưng **đã commit ở store bền vững** và có consumer mới đọc | **DURABLE_PENDING**, đóng theo kế hoạch phục hồi |
| In-flight có thể rollback an toàn, source sẽ redeliver và handler idempotent | **REPLAYABLE_PENDING**, tiếp tục shutdown kèm audit |
| External side effect UNKNOWN | **RECONCILE_REQUIRED**, ghi state bền vững và chạy đối soát |
| Chỉ còn task/queue **in-memory không có replay** | **DATA_LOSS_RISK**, không tuyên bố shutdown an toàn |

### Pha 4 — Dừng downstream, giải phóng resource

Dừng downstream endpoints phù hợp, kết thúc executor/scheduler và DB/connection pools **sau khi những phần cần drain đã hoàn tất hoặc được bảo tồn**. Giữ một khoảng thời gian cho logging, metrics flush và resource cleanup, nhưng không coi logs/metrics flush là bằng chứng durability của business data.

### Pha 5 — Sau restart

1. Xác minh instance mới thực sự kết nối **đúng source/store/region/groupId**.
2. Kiểm tra pending queue, MessageGroupStore, retry journal và outbox từ trạng thái đã commit.
3. Cho consumer mới tiếp tục **có giới hạn tải**, không làm DB/remote quá tải.
4. Đối soát eventId/operationId: số business completion và duplicate suppressed có hợp đồng rõ.
5. Kiểm tra UNKNOWN_OUTCOME với provider thay vì phát lệnh mới tùy ý.
6. Đưa desired state từ DRAINING/PAUSED về RUNNING khi toàn bộ điều kiện sức khỏe đạt.

### Bảng log tối thiểu khi bàn giao ca trực

~~~text
shutdownId=rollout-2026-11-22-001
service=order-worker
oldPod=order-worker-b
stopIngressAt=...
drainDeadline=...
finalQueued=19
finalInFlight=0
finalUnacked=0
pendingStore=JDBC
durablePendingVerified=true
outboxPending=7
externalUnknownCount=1
recoveryOwner=order-worker-new-replica
outcome=DURABLE_PENDING_RECONCILIATION_REQUIRED
~~~

Các field là **mẫu runbook**, không phải log do Spring Integration tự phát. Dữ liệu phải được bảo vệ và không chứa payload/PII không cần thiết.

## 21. Bài thực hành: chọn timeout và chiến lược queue khi scale down

**Đề bài:** Hệ thống chạy ba replica. Mỗi replica có một inbound broker adapter; các message đi qua QueueChannel rồi tới polling consumer gọi PostgreSQL và dịch vụ thanh toán. Khi scale down, một replica có queue depth=500, in-flight=8. Kubernetes cho pod 70 giây để kết thúc, nhưng HTTP outbound có P99 tới 12 giây; một số request timeout có thể đã tạo side effect.

### Nhiệm vụ

1. Vẽ state diagram của một message: broker-delivered, queued, dequeued, in-flight, business-committed, acked, unknown.
2. Xác định **QueueChannel in-memory hay JDBC-backed** và vị trí broker ack.
3. Đánh giá liệu 70 giây có đủ để drain tất cả 500 message **dựa trên throughput đo được**; nếu không, thiết kế durable pending/replay.
4. Chọn thứ tự stop: broker ingress, QueueChannel consumers, executor và DB/HTTP resources.
5. Giải thích vì sao queue depth=0 nhưng inFlight=8 chưa đủ để đóng ngay.
6. Đề xuất các **test crash/rollback/redelivery** kiểm chứng business effect không trùng.
7. Viết runbook cho trường hợp một provider charge đã thành công nhưng response bị mất khi pod chết.

### Hướng giải

**Bước 1:** Quiesce broker inbound trên replica sắp dừng, nhưng giữ consumer chạy. Xác nhận còn hai replica khác có thể nhận việc sau rebalance.

**Bước 2:** Nếu queue là RAM và broker đã ack khi enqueue, **không thể tin cậy vào replay**. Chuyển sang durable handoff hoặc sửa ack boundary trước khi vận hành scale down với dữ liệu quan trọng.

**Bước 3:** Nếu queue là JDBC-backed, kiểm tra message đã commit, groupId/region ổn định, poller transaction bao receive và xử lý đồng bộ. Nếu có ExecutorChannel trung gian, phải đánh giá lỗ hổng handoff.

**Bước 4:** Chọn drain budget sau khi trừ preStop/cleanup và safety margin. Đừng mặc định 70 giây đều dành cho handler.

**Bước 5:** Nếu timeout, phân loại từng phần: queued trong DB có thể replay; in-flight có transaction rollback; external UNKNOWN phải reconcile; outbox chờ publish có thể được publisher khác khôi phục.

**Bước 6:** Khi replica mới hoạt động, assert đủ business results, cùng eventId không tạo duplicate effect, retry hữu hạn và backlog giảm.

### Câu hỏi tự kiểm tra

**1. Spring Boot graceful shutdown 30 giây có bảo đảm QueueChannel rỗng không?**

**Không.** Nó điều phối lifecycle theo thời hạn cấu hình. Queue có thể còn message; phải thiết kế drain/recovery, đặc biệt khi consumer đã bị stop.

**2. Persistent QueueChannel có bảo đảm message đang chạy trên ExecutorChannel sống qua kill không?**

**Không tự động.** Nếu dequeue đã commit và task chỉ tồn tại trong executor memory, task có thể mất. Cần durable handoff hoặc transaction/ack boundary phù hợp.

**3. Tại sao không stop cả ingress và consumer ngay khi nhận SIGTERM?**

**Vì** consumer còn cần đọc backlog để drain. Stop consumer quá sớm có thể để queue còn nguyên cho đến lúc process chết.

**4. terminationGracePeriodSeconds=90 và preStop mất 20 giây có cho Spring thêm 90 giây sau TERM không?**

**Không.** preStop **tiêu tốn cùng grace period**. Phần còn lại cho Spring và cleanup phải nằm trong ngân sách tổng.

**5. Nếu queue persistent còn message và shutdown timeout, đó có luôn là lỗi nghiêm trọng?**

**Không.** Có thể là **DURABLE_PENDING** hợp lệ nếu message đã commit, consumer mới có thể replay và nghiệp vụ idempotent. Cần ghi trạng thái chính xác, không báo drained giả.

**6. Queue depth=0, nhưng handler vừa POST payment và mất response; có nên báo hoàn tất không?**

**Chưa đủ.** Cần trạng thái UNKNOWN_OUTCOME và reconciliation/idempotency. Queue trống không nói lên kết quả phía provider.

**7. Vì sao persistent queue có thể thấy duplicate sau restart dù đã có transaction?**

**Vì** rollback/replay hoặc broker redelivery có thể xảy ra sau side effect bên ngoài đã thành công. Transaction queue/DB không tự bao trùm tất cả hệ thống.

## 22. Checklist production

- Đã phân biệt rõ **stop ingress, stop consumer, drain queue, graceful shutdown và forced termination**?
- Đã xác định **QueueChannel in-memory hay persistent**, không chỉ nhìn bean type QueueChannel?
- Với persistent queue, DataSource, query provider, schema, region/groupId và serializer có ổn định qua restart?
- Có **poller transaction bao receive()** nếu cần rollback dequeue khi handler thất bại?
- Có biết **điểm chuyển qua ExecutorChannel** khiến transaction sender không tự tiếp tục?
- Có tránh tình huống broker ack **trước durable handoff**?
- Có đo queue depth, oldest age, executor queued, in-flight, unacked, retry/outbox pending và unresolved side effects?
- Có stop **inbound producer trước** nhưng giữ **consumer xử lý backlog** đến tiêu chí/drain budget?
- Có phân biệt timeout **Spring Boot phase**, **stopActiveComponents(milliseconds)** và **Kubernetes grace seconds**?
- Nếu có preStop, đã tính thời gian hook vào **cùng termination budget**?
- SIGTERM có thật sự đến Java process hay bị shell wrapper nuốt?
- Có tránh dựa vào @PreDestroy/shutdown hook cho tình huống SIGKILL/OOM?
- Có timeout HTTP/DB/lock và retry budget đủ chặt để không giữ in-flight vô hạn?
- Có stable eventId/idempotencyKey, transactional inbox/outbox hoặc provider reconciliation khi redelivery?
- Có ngăn việc xóa QueueChannel/MessageStore/MetadataStore chỉ để giảm backlog?
- Nếu multi-replica, có kiểm tra desired vs actual state, consumer rebalance và store sharing?
- Có phân biệt **DRAINED**, **DURABLE_PENDING**, **REPLAYABLE_PENDING**, **UNKNOWN_OUTCOME** và **DATA_LOSS_RISK**?
- Có integration test **kill process với queue pending**, dequeue transaction rollback, async handoff và restart thật?
- Có test shutdown **hết budget** chứ không chỉ thành công khi queue nhỏ?
- Có runbook rõ ai sở hữu recovery và thời điểm mở lại ingress?

## Kết luận

**Shutdown timeout và message còn trong queue** không chỉ là vấn đề chờ thêm vài giây. Đó là câu hỏi **message đang ở đâu, ai sở hữu nó, trạng thái đã bền vững hay chưa, transaction/ack kết thúc vào lúc nào và ai sẽ tiếp tục sau khi JVM biến mất**.

Trong Spring Integration Runtime, một thứ tự vận hành có chủ đích là **quiesce ingress → giữ consumer/poller chạy để drain → xác minh queued và in-flight → đóng resource hoặc bảo tồn durable pending khi hết hạn → replay/idempotent recovery**. Cơ chế **Orderly Shutdown** hỗ trợ stop nguồn và cho message in-flight thời gian hoàn tất, nhưng không thay thế một chiến lược bền vững cho QueueChannel, ExecutorChannel, broker hay external API.

Thiết kế đáng tin cậy phải cho phép **hết shutdown budget mà không mất việc** khi backlog không thể drain, và cho phép **redelivery mà không tạo duplicate business side effect** sau restart. Điều đó cần MessageStore phù hợp, transaction đúng ranh giới, outbox/inbox, correlation, observability và các bài kiểm thử kill/restart thật sự.

## Tài liệu tham khảo

- [Spring Integration Reference — Orderly Shutdown](https://docs.spring.io/spring-integration/reference/shutdown.html)
- [Spring Integration Reference — Configuring Message Channels và Persistent QueueChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Framework API — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
