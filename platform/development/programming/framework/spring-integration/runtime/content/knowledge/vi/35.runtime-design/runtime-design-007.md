# Đảm bảo lifecycle start, stop và cleanup trong Spring Integration runtime

Một message flow có thể chạy đúng khi ứng dụng đang ổn định nhưng vẫn đánh rơi message trong vài giây **khởi động**, ngừng xử lý đột ngột khi **shutdown**, hoặc giữ connection/thread/poller sau khi **gỡ một IntegrationFlow động**. Những lỗi này khó tái hiện vì chúng xảy ra ở ranh giới của <code>ApplicationContext</code>, <code>MessageChannel</code>, consumer endpoint, task executor, transaction và message store, chứ không nhất thiết trong phương thức nghiệp vụ.

Bài học **“Đảm bảo lifecycle start, stop và cleanup”** thuộc chương **Thiết kế runtime** của module **SPRING_INTEGRATION_RUNTIME**. Ta sẽ thiết kế vòng đời từ lúc tạo flow, start theo phụ thuộc, chặn ingress, xử lý phần việc đang chạy, stop endpoint, cleanup resource và khôi phục sau restart; đồng thời xem tác động của retry, correlation, error handling, poller, threading và hiệu năng.

> **Nguyên tắc:** <code>start()</code> không đồng nghĩa **ready để nhận mọi message**; <code>stop()</code> không đồng nghĩa **đã drain in-flight**; và <code>destroy()</code> không đồng nghĩa **đã xóa persistent state hoặc hủy mọi side effect từ bên ngoài**. Ứng dụng phải xác định và kiểm thử riêng từng hậu điều kiện.

## 1. Lifecycle là một hợp đồng, không chỉ là ba phương thức

Vòng đời của Spring Integration liên quan đến **nhiều đối tượng khác nhau**:

| Đối tượng | Vai trò | Điều cần bảo đảm |
|---|---|---|
| <code>IntegrationFlow</code> | Mô tả kết nối message source, channel, endpoint và handler | Flow được register đúng một lần, dependency sẵn sàng trước khi nhận traffic |
| <code>MessageChannel</code> | Chuyển message đồng bộ, bất đồng bộ hoặc lưu queue | Producer biết accepted nghĩa là gì; queue có giới hạn và recovery policy |
| <code>EventDrivenConsumer</code> | Subscribe handler vào <code>SubscribableChannel</code> | Đăng ký khi start, ngừng nhận message mới khi stop theo semantics endpoint |
| <code>PollingConsumer</code> | Poll <code>PollableChannel</code> theo trigger | Trigger/start state, số message/poll, in-flight execution và transaction |
| <code>SourcePollingChannelAdapter</code> | Chủ động poll <code>MessageSource</code> | Không poll trước khi phụ thuộc/downstream sẵn sàng |
| <code>TaskExecutor</code>/<code>TaskScheduler</code> | Điều phối worker hoặc task theo lịch | Không shutdown trước khi producer dừng, không nhận task sau cutoff |
| <code>MessageStore</code> | Lưu message, group, delay hoặc metadata | Restart không làm mất dữ liệu bắt buộc giữ; cleanup theo retention |
| Adapter của broker/HTTP/TCP | Nối nguồn/đích bên ngoài | ACK, retry, redelivery, đóng session và drain theo đúng API adapter |
| <code>IntegrationFlowContext</code> | Đăng ký/gỡ flow ở runtime | Registration có ID ổn định và ownership rõ ràng |

Một phương thức <code>stop()</code> chỉ dừng phần lifecycle của đối tượng được gọi. Nếu handler đã gửi HTTP request, DB transaction đang commit hoặc executor đã nhận <code>Runnable</code>, cần một cơ chế **theo dõi completion riêng**. Ngược lại, một <code>QueueChannel</code> có thể vẫn chứa message sau khi polling consumer dừng; việc dừng polling không xóa queue.

### Từ góc nhìn nghiệp vụ: năm mốc cần đo

1. **Accepted:** nguồn hoặc channel đã chấp nhận message/task.
2. **Started:** handler hoặc consumer bắt đầu xử lý.
3. **Completed:** tác vụ đạt hậu điều kiện nghiệp vụ (có thể gồm commit/ACK).
4. **Recovered:** lỗi đã được retry/DLQ/quarantine theo chính sách.
5. **Released:** runtime đã bỏ registration và resource mà flow sở hữu.

Không được coi bước 1 tương đương bước 3. Với <code>DirectChannel</code>, handler đồng bộ thường nằm trên call stack của <code>send()</code>. Với <code>ExecutorChannel</code>, <code>send()</code> có thể trả về ngay khi task được giao cho executor. Với <code>QueueChannel</code>, thành công có thể chỉ là message đã được enqueue.

## 2. State machine đề xuất cho runtime flow

Spring Integration không cung cấp sẵn toàn bộ state machine dưới đây. Đây là **hợp đồng điều phối do ứng dụng tự thiết kế** để nhiều endpoint và nguồn ngoài tuân thủ cùng quy trình.

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> REGISTERED: khai báo bean / register dynamic flow
    REGISTERED --> STARTING: khởi động dependency và endpoint
    STARTING --> READY: health/consumer/route đạt điều kiện
    READY --> QUIESCING: đóng admission
    QUIESCING --> DRAINING: không còn nhận công việc mới
    DRAINING --> STOPPING: in-flight = 0 hoặc chuyển recovery bền vững
    STOPPING --> STOPPED: stop endpoint, adapter, scheduler theo ownership
    STOPPED --> CLEANING: destroy riêng flow / đóng resource riêng
    CLEANING --> DESTROYED: hậu điều kiện đạt
    STARTING --> FAILED: lỗi start
    DRAINING --> FAILED: timeout / dữ liệu chưa được bảo toàn
    STOPPING --> FAILED: stop lỗi
    CLEANING --> FAILED: cleanup lỗi
    FAILED --> QUIESCING: retry có checkpoint
    STOPPED --> STARTING: resume nếu còn được phép
~~~

Ba điểm cần nhấn mạnh:

- <code>READY</code> chỉ được công bố **sau** khi tuyến xử lý và dependency đã sẵn sàng; tạo bean không đủ.
- <code>DRAINING</code> cần một **điểm cắt ingress** được bảo đảm. Nếu producer còn gửi mãi, việc đợi pending về 0 có thể không bao giờ kết thúc.
- <code>DESTROYED</code> không phải trạng thái có sẵn của <code>IntegrationFlowRegistration</code> để đọc bằng một getter; ứng dụng có thể cần ghi checkpoint riêng.

### Quy trình start và stop là hai hướng bất đối xứng

~~~mermaid
flowchart LR
    A["START"] --> B["Tạo/kiểm tra dependency"]
    B --> C["Register + start consumer/handler"]
    C --> D["Ready checks"]
    D --> E["Mở admission / ingress"]
    E --> F["RUNNING"]
    F --> G["Đóng admission / ingress"]
    G --> H["Drain / settle pending"]
    H --> I["Stop endpoint / adapter"]
    I --> J["Destroy owned flow/resources"]
    J --> K["STOPPED / CLEAN"]
~~~

Không đảo thứ tự **mở ingress trước khi consumer ready** hoặc **shutdown executor trước khi consumer ngừng submit task**. Từng hệ thống có thể khác chi tiết, nhưng hai invariant trên cần được kiểm chứng.

## 3. Spring Lifecycle, SmartLifecycle và phase

Spring Framework có <code>Lifecycle</code> và <code>SmartLifecycle</code>. Nhiều endpoint của Spring Integration triển khai cơ chế tương ứng để tự start/stop theo <code>ApplicationContext</code>.

| API | Nghĩa vận hành |
|---|---|
| <code>start()</code> | Bắt đầu hoạt động của thành phần; có thể subscribe hoặc lên lịch poll |
| <code>stop()</code> | Yêu cầu ngừng hoạt động, theo hợp đồng lớp triển khai |
| <code>isRunning()</code> | Snapshot trạng thái lifecycle, **không phải số in-flight** |
| <code>SmartLifecycle.isAutoStartup()</code> | Có tham gia tự start khi context khởi tạo hay không |
| <code>SmartLifecycle.getPhase()</code> | Thứ tự tương đối khi start/stop |
| <code>SmartLifecycle.stop(Runnable callback)</code> | API hỗ trợ dừng bất đồng bộ; component phải gọi callback sau khi stop hoàn tất |

Với các <code>SmartLifecycle</code> **trong cùng lifecycle processor**, phase **thấp hơn khởi động trước và dừng sau**; phase cao hơn khởi động sau và dừng trước. Ý tưởng thường dùng:

~~~text
START:
  downstream/resources ready → worker consumer → inbound producer

STOP:
  inbound producer → worker consumer → downstream/resources
~~~

Tuy nhiên, một cấu hình phase không có nghĩa tất cả adapter đều tôn trọng thứ tự đó theo đúng cách bạn tưởng; có thể có dependency <code>depends-on</code>, bean không implement <code>SmartLifecycle</code>, dynamic registration hoặc công việc ngoài Spring context. Phải kiểm tra **bean thật**, phase thật và log lifecycle.

Ví dụ truy vấn endpoint:

~~~java
SmartLifecycle worker =
    context.getBean("orders.worker", SmartLifecycle.class);

log.info("endpoint={}, autoStartup={}, running={}, phase={}",
    "orders.worker",
    worker.isAutoStartup(),
    worker.isRunning(),
    worker.getPhase());
~~~

<code>SmartLifecycle</code> thuộc <code>org.springframework.context</code>. Tên <code>orders.worker</code> phải là **endpoint bean ID**, không phải tên tùy ý của <code>OrderService</code>.

**Phản ví dụ:** Handler có <code>isRunning() == false</code> trong lúc một task đã submit vào executor vẫn đang xử lý. Đó không nhất thiết là framework “báo sai”, vì lifecycle state và in-flight task không đo cùng một thứ.

## 4. Chuẩn hóa tiêu chí READY trước khi nhận traffic

Một ứng dụng không nên công bố ready ngay khi HTTP server mở socket. Với flow quan trọng, readiness nên đòi hỏi:

- cấu hình/secret đã nạp và bean flow được đăng ký;
- message channel và consumer endpoint đã start theo thiết kế;
- poller hoặc listener container đủ khả năng nhận, không bị stop do bảo trì;
- DB/broker/downstream quan trọng đủ điều kiện theo health contract;
- error channel, DLQ/recovery hoặc outbox cần thiết đã sẵn sàng;
- trạng thái nghiệp vụ không phải <code>DELETING</code>, <code>MAINTENANCE</code> hoặc shutdown;
- chưa mở admission ở nguồn bên ngoài trước thời điểm các điều kiện trên đạt.

Readiness không nên chờ “tất cả dependency trên thế giới đều hoàn hảo” nếu hệ thống có degraded mode hợp lệ. Nhưng phải phản ánh **đúng khả năng xử lý công việc mà readiness hứa hẹn**.

### Ingress khác consumer

| Thành phần | Có thể start trước? | Vì sao? |
|---|---|---|
| Output channel, handler, recovery sink | Thường có | Chuẩn bị đích nhận và đường lỗi |
| Polling consumer của queue nội bộ | Thường có, sau khi dependency ready | Giúp drain backlog nếu cần |
| Inbound adapter ngoài, HTTP admission, broker listener | Chỉ mở khi ready | Tránh nhận message khi không có consumer/đường lưu bền vững |
| Metrics/tracing | Nên có từ sớm | Quan sát lỗi startup và stop |

Nếu nguồn là một broker có retry/redelivery, **pause hoặc chưa start listener** có thể giúp giữ message phía broker cho tới khi ứng dụng ready. Nhưng chi tiết ACK, offset và khả năng pause phụ thuộc adapter cụ thể, không suy ra từ <code>MessageChannel</code>.

## 5. Ví dụ Java DSL: queue, poller và endpoint chưa auto-start

Ví dụ tự chứa bên dưới minh họa một luồng trong một JVM với <code>QueueChannel</code> bounded. Input là channel nội bộ; thành phần nhận từ HTTP/broker sẽ gọi một admission gate được trình bày ở mục tiếp theo.

~~~java
public record OrderCommand(String eventId, String orderId, int quantity) {}

public class OrderProcessor {
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        // Ví dụ: ghi DB theo eventId với unique constraint/idempotency.
        // Đây là code nghiệp vụ minh họa; không giả định có DB ở test này.
    }
}
~~~

~~~java
@Configuration
@EnableIntegration
public class OrderRuntimeConfig {

    @Bean(name = "orders.pending")
    QueueChannel ordersPending() {
        return new QueueChannel(256);
    }

    @Bean
    OrderProcessor orderProcessor() {
        return new OrderProcessor();
    }

    @Bean
    IntegrationFlow orderWorkerFlow(OrderProcessor processor) {
        return IntegrationFlow.from("orders.pending")
            .handle(processor, "process", endpoint -> endpoint
                .id("orders.worker")
                .autoStartup(false)
                .poller(Pollers.fixedDelay(200)
                    .maxMessagesPerPoll(10)
                    .receiveTimeout(0)))
            .get();
    }
}
~~~

Các kiểu chính: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.dsl.Pollers</code>, <code>org.springframework.integration.channel.QueueChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>, cùng <code>@Configuration</code>/<code>@Bean</code> của Spring.

Ở đây:

- <code>orders.pending</code> có capacity 256 **message**, không tự xử lý nghiệp vụ chỉ vì enqueue thành công.
- Input là <code>PollableChannel</code>, nên endpoint cần poller để gọi <code>receive()</code>.
- <code>autoStartup(false)</code> là cấu hình cho **endpoint** <code>orders.worker</code>, giữ consumer chưa chạy cho tới khi ứng dụng gọi <code>start()</code>.
- <code>maxMessagesPerPoll(10)</code> giúp mỗi lần poll có giới hạn; nó không bảo đảm luôn xử lý 10 message mỗi 200 ms.
- Khi endpoint chưa start, queue vẫn có thể nhận message từ sender. Vì vậy cần **admission gate** nếu không muốn traffic đi vào trước readiness.

Ví dụ không dùng persistent store: khi JVM crash, message còn trong in-memory queue có thể mất. Không đưa ví dụ này lên production với giả định “shutdown sẽ giữ lại queue” nếu không có hợp đồng replay từ upstream hoặc persistent channel store.

## 6. Admission gate: chặn message mới mà không mất cuộc đua với stop

Một đoạn code như:

~~~java
if (ready.get()) {
    inputChannel.send(message);
}
~~~

**không đủ** để bảo đảm “không còn send sau cutoff”: thread A có thể đọc <code>ready=true</code>, thread B đóng gate rồi stop consumer, thread A mới gọi <code>send()</code>.

Ví dụ sau dùng <code>ReentrantReadWriteLock</code> để **serialize cutoff với mọi lời gọi submit đi qua gate**:

~~~java
public final class OrderAdmissionGate {
    private final MessageChannel input;
    private final ReadWriteLock lock = new ReentrantReadWriteLock(true);
    private boolean accepting;

    public OrderAdmissionGate(MessageChannel input) {
        this.input = input;
    }

    public boolean submit(OrderCommand command) {
        lock.readLock().lock();
        try {
            if (!accepting) {
                return false;
            }
            Message<OrderCommand> request = MessageBuilder
                .withPayload(command)
                .setHeader("businessEventId", command.eventId())
                .build();
            return input.send(request, 200);
        } finally {
            lock.readLock().unlock();
        }
    }

    public void open() {
        lock.writeLock().lock();
        try {
            accepting = true;
        } finally {
            lock.writeLock().unlock();
        }
    }

    public void close() {
        lock.writeLock().lock();
        try {
            accepting = false;
        } finally {
            lock.writeLock().unlock();
        }
    }
}
~~~

Các kiểu: <code>org.springframework.messaging.MessageChannel</code>, <code>org.springframework.integration.support.MessageBuilder</code>, <code>java.util.concurrent.locks.ReadWriteLock</code> và <code>ReentrantReadWriteLock</code>. Có thể đăng ký gate:

~~~java
@Bean
OrderAdmissionGate orderAdmissionGate(
        @Qualifier("orders.pending") MessageChannel pending) {
    return new OrderAdmissionGate(pending);
}
~~~

Hợp đồng quan trọng:

1. Sau khi <code>close()</code> **trả về**, mọi lần <code>submit()</code> *bắt đầu sau thời điểm đó* đều bị từ chối; những send đã vào gate trước cutoff đã kết thúc hoặc timeout trước khi write lock được lấy.
2. Chỉ code đi **qua gate** được bảo vệ. Không expose channel trực tiếp cho một producer khác rồi giả định gate chặn được nó.
3. <code>submit() == false</code> là **chưa nhận thành công theo giao diện này**. HTTP gateway, broker adapter hoặc outbox cần chính sách retry/NACK/persistence đúng; không ACK source như đã hoàn tất.
4. Trong nhiều JVM, lock trên **một tiến trình** không chặn producer từ pod khác. Cần trạng thái bền vững, version/CAS, broker pause/partition ownership hoặc distributed admission phù hợp.
5. Giữ read lock trong <code>send(timeout)</code> có thể khiến <code>close()</code> chờ tới timeout; nên dùng timeout hữu hạn và đo thời gian cutoff.

Gate không phải cơ chế xử lý message đang chạy. Nó chỉ xác định thời điểm **không còn tiếp nhận mới** để quá trình drain có thể kết thúc.

## 7. Drain: thế nào mới là không còn công việc chưa hoàn tất?

Sau khi đóng ingress, cách kiểm tra phổ biến là:

~~~java
if (queue.getQueueSize() == 0) {
    worker.stop();
}
~~~

**Cách này không an toàn.** Poller có thể vừa lấy message cuối ra khỏi queue nhưng handler chưa chạy xong. Một message cũng có thể đang nằm trong executor queue hoặc chờ retry/backoff; <code>getQueueSize()</code> lúc đó bằng 0 mà công việc chưa hoàn tất.

### Định nghĩa một đơn vị outstanding

Với một logical message đã được chấp nhận:

~~~text
ACCEPTED
   │
   ├──> PENDING_QUEUE
   │          │
   │          └──> IN_FLIGHT
   │                    ├──> COMMITTED / ACKED      ──> SETTLED
   │                    ├──> DURABLY_QUARANTINED   ──> SETTLED theo policy
   │                    └──> RETRY_SCHEDULED       ──> vẫn OUTSTANDING
   │
   └──> REJECTED_BEFORE_ACCEPTANCE ──> không tính outstanding
~~~

Đối với drain, cần đếm **accepted nhưng chưa terminal-settled**, chứ không chỉ message còn trong channel. Hậu điều kiện có thể là:

\[
\text{Outstanding} = \text{Accepted} - \text{Committed/ACKed} - \text{QuarantinedByPolicy} = 0
\]

**Giới hạn của công thức:** Một message có thể tạo nhiều fragment/side effect, nên đơn vị <code>Accepted</code> và <code>Settled</code> phải được định nghĩa theo **logical event**. Nếu một message chỉ được ACK sau khi outbound hoàn tất, đừng giảm outstanding ngay sau <code>handleMessage()</code>. Với hệ thống nhiều node, cần lưu progress bền vững hoặc suy từ broker/DB/outbox, không dựa vào <code>AtomicInteger</code> cục bộ.

### Ngăn race khi ghi accepted và completed

Trong cùng một JVM, nếu muốn dùng counter, hãy đăng ký một message là outstanding **trước** khi nó có thể được consumer xử lý; nếu <code>send()</code> thất bại chắc chắn trước khi được chấp nhận, thì hoàn tác counter. Nếu tăng counter **sau** <code>send()</code>, worker có thể hoàn tất trước lúc counter tăng, tạo số âm hoặc kết luận drain sai.

Ngoài ra, cần quyết định rõ:

- Khi retry sẽ làm lại đúng logical event hay tạo một event mới?
- Thành công có nghĩa handler trả về hay transaction đã commit?
- Khi chuyển sang DLQ/quarantine, ai chịu trách nhiệm replay và khi nào mới coi settled?
- Khi producer/broker không xác định được ACK thành công hay thất bại, có thể cần đối soát thay vì đơn giản decrement counter.

Trong production, một sổ ghi nhận <code>admitted/settled</code> tại durable inbox/outbox hoặc broker offset thường đáng tin cậy hơn counter chỉ tồn tại trong bộ nhớ.

### Một probe làm hợp đồng giữa flow và orchestrator

~~~java
public interface WorkDrainProbe {
    // Phải bao gồm queue, in-flight, retry và công việc chưa có terminal outcome.
    boolean allAcceptedWorkSettled();

    // Dùng cho log/metrics, không tự đủ làm điều kiện kết thúc.
    long inFlight();
    long pending();
}
~~~

Đây là **interface ứng dụng tự triển khai**, không phải API của Spring Integration. Với một flow đơn giản, probe có thể ghép queue depth và tracker in-flight được bảo vệ đúng race. Với persistent queue và broker, probe phải tích hợp DB/adapter state. Không thể dùng một implementation “chung cho mọi channel” mà không biết transaction boundary.

## 8. Coordinator start → quiesce → drain → stop

Ví dụ dưới đây sử dụng gate mục 6, <code>SmartLifecycle</code> của endpoint và <code>WorkDrainProbe</code> do ứng dụng triển khai. Đây là bộ khung điều phối **cho một tiến trình**, không phải controller phân tán.

~~~java
public final class OrderRuntimeCoordinator {
    private final OrderAdmissionGate gate;
    private final SmartLifecycle workerEndpoint;
    private final WorkDrainProbe probe;

    public OrderRuntimeCoordinator(
            OrderAdmissionGate gate,
            SmartLifecycle workerEndpoint,
            WorkDrainProbe probe) {
        this.gate = gate;
        this.workerEndpoint = workerEndpoint;
        this.probe = probe;
    }

    public synchronized void startAfterRecovery() {
        // Đường gọi phải xác minh DB/broker/recovery sink đã sẵn sàng trước.
        if (!workerEndpoint.isRunning()) {
            workerEndpoint.start();
        }
        if (!workerEndpoint.isRunning()) {
            throw new IllegalStateException("orders.worker chưa running");
        }
        gate.open(); // Bước cuối: chỉ mở nhận mới sau khi consumer ready.
    }

    public synchronized void quiesceDrainAndStop(Duration budget)
            throws InterruptedException {
        gate.close(); // Không cho thêm công việc mới qua gate.
        long deadline = System.nanoTime() + budget.toNanos();

        while (!probe.allAcceptedWorkSettled()) {
            if (System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                    "Drain timeout; vẫn giữ gate đóng và worker chạy");
            }
            Thread.sleep(25);
        }

        workerEndpoint.stop();
        if (workerEndpoint.isRunning()) {
            throw new IllegalStateException(
                "Endpoint chưa dừng; cần kiểm tra lifecycle");
        }
    }
}
~~~

<code>Duration</code> thuộc <code>java.time</code>; <code>SmartLifecycle</code> thuộc <code>org.springframework.context</code>. Để wire vào ví dụ:

~~~java
@Bean
OrderRuntimeCoordinator orderRuntimeCoordinator(
        OrderAdmissionGate gate,
        @Qualifier("orders.worker") SmartLifecycle endpoint,
        WorkDrainProbe probe) {
    return new OrderRuntimeCoordinator(gate, endpoint, probe);
}
~~~

**Các giới hạn cần nêu rõ:**

1. <code>Thread.sleep(25)</code> chỉ minh họa vòng chờ có deadline trên **management/control thread**, không được chạy trên thread poller hay trong handler cần được drain. Trong hệ thống lớn nên dùng completion signals, condition hoặc event-driven coordinator.
2. Nếu timeout, code **không** destroy flow hay dừng consumer. Gate vẫn đóng để operator khắc phục nguyên nhân và tiếp tục drain. Đây là hành vi cố ý nhằm tránh bỏ message đang chạy.
3. <code>isRunning()</code> là trạng thái lifecycle. Một số implementation dừng bất đồng bộ qua <code>stop(Runnable)</code>; việc trả về từ <code>stop()</code> không phải bằng chứng tự động rằng mọi task đã kết thúc. Phải kiểm tra đúng hợp đồng triển khai và <code>WorkDrainProbe</code>.
4. <code>synchronized</code> chỉ serialize các lệnh coordinator trên **một instance**. Multi-pod cần leader/lock/CAS hoặc partition ownership để tránh hai coordinator start/stop cùng flow.
5. <code>startAfterRecovery()</code> chưa kiểm chứng mọi dependency bên ngoài; kiểm tra readiness thực tế phải nằm trước khi gọi.
6. Trong Spring context, <code>@Bean</code> <code>WorkDrainProbe</code> cần implementation thực sự; ví dụ không tuyên bố probe tự được framework cấp.

### Khi không thể drain trong thời hạn shutdown

Nếu orchestrator chỉ cấp một khoảng dừng hữu hạn, đừng tự đặt <code>outstanding = 0</code> rồi destroy:

| Nhóm message | Phương án an toàn |
|---|---|
| Vẫn ở broker, chưa ACK | Giữ ở broker/NACK/requeue theo hợp đồng adapter |
| Đã ghi durable inbox/queue | Dừng consumer sau khi commit đúng, cho instance mới resume |
| Đang chạy handler và không thể cancel an toàn | Cấp đủ grace period, hoặc fencing để ngăn stale worker ghi sau restart |
| Chỉ ở in-memory queue | Ưu tiên drain hoặc chuyển sang store bền vững trước khi process thoát |
| Đã gửi side effect ngoài nhưng ACK chưa chắc chắn | Dùng idempotency key và đối soát sau restart |
| Delayer/aggregator còn pending group | Giữ store/region, khôi phục hoặc quarantine theo policy; không xóa bừa |

Một shutdown có thể coi là **safe stop** nếu công việc chưa hoàn tất vẫn có recovery path có thể kiểm chứng, chứ không nhất thiết mọi nghiệp vụ đã hoàn thành ngay tại thời điểm pod dừng.

## 9. Stop theo kiểu channel và endpoint

Không thể viết một lệnh stop dùng chung rồi suy ra một hành vi cho mọi channel.

| Cấu trúc | Khi stop consumer/source | Rủi ro còn lại |
|---|---|---|
| <code>DirectChannel</code> + <code>EventDrivenConsumer</code> | Endpoint có thể unsubscribe handler; channel vẫn tồn tại nếu là bean riêng | Sender tiếp tục gửi có thể gặp <code>MessageDispatchingException</code> |
| <code>PublishSubscribeChannel</code> | Số subscriber giảm khi các endpoint stop | Mặc định cho phép không subscriber có thể làm send “thành công” mà không delivery |
| <code>ExecutorChannel</code> | Không còn subscriber mới sau stop, nhưng worker task đã submit có thể tiếp tục | Lỗi worker sau stop, shutdown executor quá sớm, side effect muộn |
| <code>QueueChannel</code> + <code>PollingConsumer</code> | Poller ngừng gọi <code>receive()</code> mới theo lifecycle | Message vẫn ở queue; in-flight đang chạy có thể chưa hoàn tất |
| <code>SourcePollingChannelAdapter</code> | Ngừng kích hoạt poll theo trigger | Source đã nhận nhưng chưa dispatch/commit có thể vẫn chịu rollback/redelivery |
| <code>FluxMessageChannel</code> + reactive consumer | Cần quản lý subscription/cancellation theo reactive lifecycle | Cancel không đồng nghĩa remote side effect đã rollback |
| Inbound Kafka/JMS/AMQP adapter | Container/listener được stop theo API riêng | ACK, offset, redelivery, rebalance và in-flight callback khác nhau |

### Trường hợp khó: DirectChannel báo thiếu subscriber khi shutdown

~~~text
Thread A: producer kiểm tra endpoint vẫn ACTIVE
Thread B: stop EventDrivenConsumer, unsubscribe handler
Thread A: send(M) vào DirectChannel
→ MessageDispatchingException: Dispatcher has no subscribers
~~~

Đây là một **race tại ranh giới lifecycle**. Cách sửa là đóng admission/stop ingress **trước** khi stop consumer, không tăng <code>sendTimeout</code> hoặc đăng ký handler giả để nuốt message.

Với <code>PublishSubscribeChannel</code> có <code>minSubscribers=0</code>, lỗi còn khó nhìn hơn: gửi có thể thành công khi tất cả subscriber đã dừng. Khi delivery là bắt buộc, cấu hình <code>requireSubscribers</code> hoặc giao sự kiện vào store/broker có hợp đồng đáng tin cậy; đừng coi publish–subscribe mặc định là durable queue.

## 10. Stop đúng thứ tự với executor và scheduler

Spring Framework phân biệt <code>TaskExecutor</code> (chạy task) và <code>TaskScheduler</code> (kích hoạt task theo lịch). <code>ExecutorChannel</code> hoặc poller có thể dùng những bean **dùng chung** này.

Một trình tự thường an toàn:

~~~text
1. Đóng ingress/admission, pause broker listener nếu phù hợp
2. Không tạo poll mới; để các poll/handler đã nhận được quản lý theo policy
3. Đợi accepted-but-unsettled về 0 hoặc bảo toàn phục hồi
4. Stop endpoint/adapter và unregister subscriber
5. Shutdown executor/scheduler riêng flow sau khi hết task
6. Destroy flow và đóng resource được flow sở hữu
7. Xác minh không còn timer/subscription/connection/task mồ côi
~~~

Tùy nguồn, bạn có thể cần **giữ polling consumer đang chạy cho đến khi drain queue xong**; vì vậy mục 2 và 3 phải được phân biệt rõ. “Dừng poll mới” ở trên chỉ áp dụng khi không còn queue cần drain hoặc đã chuyển phần việc sang recovery; nếu còn backlog và poller là consumer duy nhất, phải để nó chạy trong quá trình drain.

### ThreadPoolTaskExecutor không tự giải bài toán delivery

Một executor riêng dành cho flow có thể khai báo:

~~~java
@Bean(name = "orders.executor")
ThreadPoolTaskExecutor ordersExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(4);
    pool.setMaxPoolSize(8);
    pool.setQueueCapacity(64);
    pool.setThreadNamePrefix("orders-worker-");
    pool.setWaitForTasksToCompleteOnShutdown(true);
    pool.setAwaitTerminationSeconds(20);
    return pool;
}
~~~

<code>ThreadPoolTaskExecutor</code> thuộc <code>org.springframework.scheduling.concurrent</code>. Chờ hoàn tất task lúc shutdown là một **lựa chọn có trade-off**, không bảo đảm side effect từ HTTP/DB đã được commit đúng hoặc mọi task bất hợp tác sẽ bị kết thúc. Theo phiên bản Spring Framework, tùy chọn shutdown và cơ chế <code>SmartLifecycle</code> có thể tương tác; cần kiểm tra cấu hình <code>acceptTasksAfterContextClose</code>, early shutdown và thực nghiệm với bean thật.

Không cấu hình <code>setAwaitTerminationSeconds(20)</code> rồi kết luận không còn task sau đúng 20 giây. Hết thời gian chờ có thể để lại tác vụ chưa hoàn tất hoặc bị interrupt; công việc không chịu interrupt (ví dụ blocking I/O) có thể kéo dài hơn.

### Vì sao không tăng pool vô hạn để drain nhanh?

Tăng worker có thể làm cạn JDBC connection pool, tăng lock contention hoặc vượt rate limit downstream. Nếu bottleneck là DB/HTTP, điều đúng thường là **giảm ingress**, giữ concurrency trong ngưỡng dependency chịu được và dùng durable buffering; không tăng <code>maxPoolSize</code> một cách mù quáng.

## 11. Transaction, ACK và retry ở ranh giới stop

Để dừng an toàn, phải định nghĩa transaction bảo vệ đoạn nào:

| Flow | Transaction thường nằm ở đâu? | Điều không được giả định |
|---|---|---|
| <code>DirectChannel</code> cùng thread | Transaction bên ngoài có thể bao handler | <code>send()</code> trả về nghĩa là mọi outbound effect đã commit |
| <code>ExecutorChannel</code> | Worker có transaction riêng nếu được cấu hình | JDBC transaction của sender được truyền tự động |
| <code>QueueChannel</code> với persistent store | Receive/handler trong poller transaction tùy advice/store | Lấy message khỏi queue nghĩa là đã ACK broker |
| Kafka/JMS/AMQP inbound | Container transaction/acknowledgment và handler tùy adapter | ACK sẽ luôn rollback khi handler async fail |
| Reactive flow | Reactive transaction manager trong Reactor Context | ThreadLocal JDBC tự đi qua <code>publishOn</code> |

**Retry ở handler khác retry ở sender.** Nếu sender bị reject trước khi handler chạy, <code>RequestHandlerRetryAdvice</code> bên trong handler chưa có cơ hội retry. Nếu retry xảy ra sau khi một remote side effect đã thành công nhưng ACK thất bại, replay có thể tạo duplicate. Vì vậy:

- mỗi logical event cần business idempotency key ổn định;
- commit/ACK terminal được ghi nhận trong cùng hợp đồng nhất quán hoặc có đối soát;
- retry có hạn, backoff/jitter và dead-letter/quarantine cho poison message;
- stop/cancel không tự bỏ retry job đã lưu bền vững;
- stop phải chặn **new attempts** của event không còn hợp lệ (ví dụ tenant đã DELETING), nhưng không hủy audit/recovery record trái chính sách.

### MessageStore là trách nhiệm dữ liệu, không phải chỉ một bean

<code>JdbcMessageStore</code>, <code>JdbcChannelMessageStore</code>, <code>MessageGroupStore</code> hoặc kho Redis có thể giữ queue, group aggregator, delayer và claim-check. Khi stop/destroy flow:

1. Xác định message nào vẫn pending và ai là consumer hợp pháp sau restart.
2. Giữ nguyên namespace/region và serializer cần để recovery, hoặc migrate/quarantine có kiểm toán.
3. Chỉ xóa group/message đã đủ điều kiện theo policy; không DELETE raw rows khi worker còn đang nhận.
4. Khi có nhiều instance, quản lý lock/correlation/claim để hai node không xử lý cùng một event ngoài ý muốn.
5. Phân biệt cleanup resource (đóng connection/thread) với cleanup dữ liệu (retention/purge).

Destroy một bean store **không** mặc định xóa nội dung database. Ngược lại, xóa dữ liệu store có thể khiến flow không resume được sau restart.

## 12. Lifecycle của IntegrationFlow được đăng ký động

Với flow khai báo sẵn bằng <code>@Bean</code>, Spring context quản lý nhiều khía cạnh lifecycle. Với flow được tạo ở runtime, <code>IntegrationFlowContext</code> cung cấp cơ chế đăng ký, start/stop và gỡ.

Ví dụ ứng dụng có một flow xử lý riêng cho từng tenant. Mỗi tenant được cấp **flow ID ổn định** và <code>DirectChannel</code> riêng để tránh routing lẫn nhau:

~~~java
@Component
public class TenantFlowRegistry {
    private final IntegrationFlowContext flowContext;
    private final TenantEventService service;

    public TenantFlowRegistry(
            IntegrationFlowContext flowContext,
            TenantEventService service) {
        this.flowContext = flowContext;
        this.service = service;
    }

    private String id(UUID tenantId, long generation) {
        return "tenant.flow." + tenantId + "." + generation;
    }

    public IntegrationFlowContext.IntegrationFlowRegistration register(
            UUID tenantId, long generation) {
        String flowId = id(tenantId, generation);
        if (flowContext.getRegistrationById(flowId) != null) {
            throw new IllegalStateException("Flow đã đăng ký: " + flowId);
        }

        MessageHandler handler = message -> service.process(
            tenantId, generation, (TenantEvent) message.getPayload());

        IntegrationFlow flow = IntegrationFlow.from(new DirectChannel())
            .handle(handler)
            .get();

        return flowContext.registration(flow)
            .id(flowId)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();
    }

    public void start(UUID tenantId, long generation) {
        var registration =
            flowContext.getRegistrationById(id(tenantId, generation));
        if (registration == null) {
            throw new IllegalStateException("Flow chưa đăng ký");
        }
        registration.start();
    }

    public void unregisterAfterDrain(UUID tenantId, long generation) {
        var registration =
            flowContext.getRegistrationById(id(tenantId, generation));
        if (registration != null) {
            registration.stop();
            registration.destroy();
        }
    }
}
~~~

<code>TenantEventService</code> và <code>TenantEvent</code> là kiểu **do ứng dụng tự định nghĩa**, ví dụ:

~~~java
public record TenantEvent(String eventId, String content) {}

public interface TenantEventService {
    void process(UUID tenantId, long generation, TenantEvent event);
}
~~~

Các kiểu framework: <code>org.springframework.integration.dsl.context.IntegrationFlowContext</code>, <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.channel.DirectChannel</code> và <code>org.springframework.messaging.MessageHandler</code>.

**Ý nghĩa thiết kế:**

1. <code>registration(...).autoStartup(false)</code> đăng ký topology nhưng chưa mở xử lý, phù hợp bước khởi tạo chưa hoàn tất.
2. <code>registration.start()</code> chỉ được gọi sau khi tenant còn ACTIVE, credentials/route sẵn sàng và admission gate tương ứng cho phép.
3. <code>registration.stop()</code> dùng để dừng thành phần lifecycle của flow, **không thay** drain.
4. <code>registration.destroy()</code> gỡ registration/bean phụ thuộc thuộc flow. Có thể dùng <code>flowContext.remove(flowId)</code> như đường gỡ theo ID; không cần gọi **cả hai** cho cùng registration.
5. <code>useFlowIdAsPrefix()</code> giúp tránh trùng bean IDs khi nhiều flow có cấu trúc tương tự; nó yêu cầu đã chỉ định <code>.id(...)</code>.
6. <code>TenantEventService</code> có thể là shared bean; flow chỉ **tham chiếu** service, không được tự destroy service dùng chung khi một tenant bị xóa.

Đoạn kiểm tra <code>getRegistrationById() != null</code> rồi register không nguyên tử trên nhiều thread hoặc node. Production phải serialize provision/delete theo tenant bằng CAS/version, single owner hoặc coordination phù hợp. Dùng generation giúp cleanup cũ không hủy nhầm flow mới nếu cùng tenant được tạo lại.

### Registry không phải persistent configuration

Dynamic registration là trạng thái runtime của <code>ApplicationContext</code>. Sau restart JVM, ứng dụng cần **tự rebuild** từ nguồn cấu hình bền vững; đừng kỳ vọng một flow được đăng ký bằng Java object sẽ tự xuất hiện ở process mới chỉ vì message store còn dữ liệu.

## 13. Ownership: resource nào được phép đóng?

Lifecycle cleanup phải bắt đầu từ **ownership map**. Hãy phân biệt resource do flow tạo và resource toàn ứng dụng dùng chung:

| Resource | Thường là per-flow/per-tenant? | Cleanup |
|---|---|---|
| <code>IntegrationFlowRegistration</code> | Có | Stop/destroy sau khi đã drain |
| Endpoint và channel được dynamic registration tạo riêng | Có | Registration quản lý phụ thuộc; xác minh bean/handle biến mất |
| Shared <code>DirectChannel</code>, router và error channel | Không | Chỉ gỡ subscriber/route tenant; không đóng channel chung |
| <code>ThreadPoolTaskExecutor</code> riêng tenant | Có thể | Không submit mới; drain rồi shutdown theo deadline |
| Shared executor hoặc <code>TaskScheduler</code> | Không | Không shutdown chỉ vì một tenant stop |
| Broker listener container riêng flow | Có thể | Stop/unsubscribe đúng container và xác nhận ACK/offset |
| Shared connection factory/HTTP client | Không | Không close nếu tenant khác còn dùng |
| Custom <code>ScheduledFuture</code>, Reactor <code>Disposable</code> | Có thể | Cancel/dispose đúng handle, xác nhận không còn callback |
| Per-tenant secret/credentials/cache | Có thể | Thu hồi sau khi không còn in-flight/recovery hợp lệ cần nó |
| <code>JdbcMessageStore</code>/Redis data | Dữ liệu có thể riêng nhưng backend thường chung | Retention/purge theo namespace và generation, không xóa backend |
| Error/DLQ/outbox records | Dữ liệu có thể thuộc tenant | Dọn theo policy và audit, không mặc định khi destroy flow |

**Không đưa singleton dùng chung vào <code>IntegrationFlowRegistrationBuilder.addBean(...)</code> chỉ để tiện truy cập** nếu không muốn nó nằm trong phạm vi bean phụ thuộc bị destroy. Một connection factory hoặc scheduler chỉ được đóng khi **owner thực sự** của nó kết thúc và không còn consumer nào sử dụng.

### Cleanup hook có kiểm soát

Ứng dụng có thể biểu diễn resource riêng dưới dạng lease:

~~~java
public interface RuntimeResourceLease extends AutoCloseable {
    String ownerFlowId();
    String resourceName();

    @Override
    void close() throws Exception;
}
~~~

Một registry ứng dụng lưu <code>ownerFlowId → leases</code> có thể làm cleanup idempotent, kiểm tra owner trước khi close và giữ kết quả cho retry. Đây không phải interface mặc định của Spring Integration.

**Tránh double-close:** Nếu một object đã được registration đăng ký là dependent bean và framework gọi destroy hook của nó, đừng đồng thời để resource registry đóng object đó lần nữa nếu implementation không chịu được.

### Một quy trình cleanup phân tầng

~~~mermaid
flowchart TD
    A["Ingress đã chặn, pending đã settled"] --> B["Stop endpoint thuộc flow"]
    B --> C["Destroy registration/owned bean"]
    C --> D["Cancel timer, custom subscription, lease riêng"]
    D --> E["Kiểm tra executor/connection/thread còn owner?"]
    E --> F["Purge dữ liệu đúng policy, theo namespace/generation"]
    F --> G["Ghi cleanup checkpoint + xác minh hậu điều kiện"]
    D -. "Không chạm" .-> H["Shared executor/channel/connection factory"]
~~~

Cleanup có thể thất bại giữa các bước. Mỗi bước nên chạy **idempotent**, có checkpoint và phân biệt trạng thái “resource đã vắng mặt” với “chưa thể xác định resource có vắng mặt hay không”.

## 14. Restart và reconciliation sau crash

Một quy trình chỉ hoạt động khi shutdown graceful là chưa đủ. Process có thể bị <code>kill -9</code>, mất điện, OOM hoặc pod bị cưỡng bức dừng trước deadline. Khi đó callback <code>stop()</code>/<code>destroy()</code> **không được bảo đảm chạy**.

Ứng dụng cần một **reconciler** ở startup, dựa trên dữ liệu bền vững:

| Trạng thái lưu bền vững | Hành vi khi startup |
|---|---|
| <code>ACTIVE</code> | Rebuild flow theo config, giữ chưa nhận traffic đến khi mọi dependency/route ready |
| <code>STARTING</code> từ process đã chết | Kiểm tra checkpoint, ownership và idempotency trước khi resume |
| <code>QUIESCING</code>/<code>DRAINING</code> | Không mở ingress mới; phục hồi/drain/quarantine pending theo policy |
| <code>STOPPING</code> | Xác minh đã ngừng consumer và outstanding còn gì; hoàn thành stop có kiểm soát |
| <code>CLEANUP_FAILED</code> | Retry cleanup với generation fencing; không tự provision flow mới |
| <code>DELETED</code> | Không rebuild; kiểm tra leak/retention bằng job riêng nếu cần |

Ví dụ trình tự startup của instance mới:

~~~text
1. Đọc config + trạng thái operation/job từ DB
2. Khởi tạo message store, connection/transaction manager và recovery sink
3. Rebuild các flow đủ điều kiện nhưng chưa tự start inbound
4. Khôi phục pending group/delayed message/queue theo từng loại endpoint
5. Xác định owner duy nhất cho partition hoặc tenant
6. Start consumer, kiểm tra health và nghiệp vụ readiness
7. Mở admission / broker listener / HTTP readiness
8. Bật giám sát lag, duplicate event, error rate và startup duration
~~~

Các bước trên là thiết kế ứng dụng, không phải transaction nguyên tử trên toàn bộ Spring context, broker và DB. Nên lưu checkpoint ở nơi bền vững; một <code>AtomicBoolean</code> trong singleton sẽ mất sau crash.

### Quản lý idempotency khi old/new instance trùng thời điểm

Trong rolling deploy, instance cũ có thể vẫn đang hoàn tất side effect trong khi instance mới đã nhận redelivery. Cần kết hợp:

- business event ID duy nhất, unique constraint hoặc durable inbox để tránh double commit;
- lease/partition ownership để ngăn hai consumer cùng xử lý khi không được phép;
- generation/version fencing trước khi ghi resource dễ bị cleanup cũ xóa;
- timeout và transaction boundary đủ rõ để xác định attempt nào terminal;
- recovery workflow cho những trường hợp remote side effect thành công nhưng ACK/DB marker chưa xác nhận.

Spring Integration giúp điều phối message, nhưng **không mặc nhiên cung cấp exactly-once end-to-end** giữa broker, DB và remote HTTP.

## 15. Shutdown trong container/Kubernetes và rolling deployment

Một môi trường container thường gửi tín hiệu chấm dứt và cấp một khoảng thời gian hữu hạn trước khi kill process. Vì vậy cần thiết kế:

1. **Readiness off:** stop quảng bá instance là nơi nhận traffic mới. Readiness của HTTP/load balancer và việc pause broker listener là **hai con đường riêng**, phải cấu hình cả hai nếu sử dụng.
2. **Close admission:** chặn việc submit mới ngay trong process, kể cả những request đã đến trước thời điểm readiness thay đổi.
3. **Allow drain:** cho handler/poller cần thiết tiếp tục xử lý phần đã accepted; không shutdown executor sớm.
4. **Cut over safely:** nếu hết ngân sách drain, chuyển pending sang durable recovery, không chỉ interrupt và giả định message sẽ tự quay lại.
5. **Stop/destroy:** ngừng các endpoint rồi đóng resource theo ownership.
6. **Exit:** đối soát và phát metric/trace cuối trong giới hạn thời gian; không giữ process treo vô hạn.

Một hook <code>@PreDestroy</code> có thể hữu ích để ghi checkpoint hoặc cleanup nhanh, nhưng không nên xem đó là giải pháp duy nhất cho nhiều giây drain. Tại thời điểm destroy beans, lifecycle processor có thể đã stop một số thành phần cần cho công việc. Một coordinator quản lý quiesce/drain **trước khi context close** thường dễ điều khiển hơn.

### SmartLifecycle phase và readiness cần được phối hợp

Phase thấp start trước/stop sau là một cơ chế **thứ tự tương đối**, không thay cho:

- chặn request từ load balancer hoặc gateway;
- pause/stop broker listener theo ACK/offset đúng;
- xác minh message đã persist hoặc handler completion;
- ngăn dynamic registration mới trong lúc app đang shutdown;
- đợi async error publisher, trace exporter và resource cleanup hoàn tất.

Nếu dùng <code>SmartLifecycle.stop(Runnable callback)</code> trong một component custom, callback phải được gọi **một lần sau khi stop thực sự kết thúc**. Gọi callback ngay khi vừa *yêu cầu* shutdown executor có thể khiến lifecycle processor tiến tới đóng connection trong lúc task còn dùng nó.

### Ví dụ sai phổ biến

~~~text
preStop: shutdown executor trước
    ↓
HTTP/broker ingress vẫn phát message
    ↓
ExecutorChannel reject toàn bộ task mới
    ↓
Error handler chưa kịp publish hoặc recovery sink cũng bị đóng
    ↓
Message bị ACK sai / request timeout / retry storm
~~~

Phương án đúng phải đổi **thứ tự sự kiện** và điều kiện nhận, không chỉ tăng shutdown timeout.

## 16. Quan sát lifecycle và hậu điều kiện cleanup

Khi kiểm tra production, nên có **metric tương ứng với từng phase** thay vì chỉ log “Application started”.

| Dữ liệu quan sát | Ý nghĩa | Cách dùng khi incident |
|---|---|---|
| <code>flow.state</code> theo nhóm trạng thái | <code>STARTING/READY/QUIESCING/DRAINING/STOPPED</code> | Phát hiện flow kẹt ở phase bất thường |
| <code>ingress.accepting</code> | Gate đang mở hay đóng | Giải thích 429/503/NACK hoặc message bị reject |
| <code>accepted_not_settled</code> | Số logical event chưa terminal | Phán đoán có thể stop an toàn |
| <code>queue.depth</code> và oldest age | Message đang chờ consumer | Phát hiện thiếu poller, backlog hoặc slow consumer |
| <code>endpoint.isRunning</code> | Lifecycle của poller/subscriber | So sánh với state READY/STOPPED |
| Executor active/queued/rejected | Worker đã hết khả năng chạy hoặc shutdown | Tìm task chưa hoàn tất |
| Pending group/delayed message | Correlation chưa release, delay chưa đến hạn | Quyết định giữ store hoặc quarantine |
| Error/retry/DLQ counts | Recovery có đang tạo backlog không | Tránh đóng flow khi lỗi chưa settled |
| Cleanup step duration/failure | Resource/bean nào cleanup chậm hoặc bị leak | Retry checkpoint và đánh giá grace period |

Các tên <code>flow.state</code>, <code>ingress.accepting</code> và <code>accepted_not_settled</code> là **metric do ứng dụng đề xuất**, không phải meter mặc định được Spring Integration tự tạo. Spring Integration hỗ trợ Micrometer/Observation cho các channel, handler, source phù hợp khi được cấu hình, nhưng metric nghiệp vụ “terminal-settled” phải do ứng dụng định nghĩa.

### Correlation và quản lý độ lớn nhãn metric

Nên gắn trong log/trace được phép:

~~~text
timestamp, service, instance, flowId, endpointId
phase, action, reason, elapsedMs, threadName
messageId, correlationId, businessEventId
accepted, settled, inFlight, queueDepth
errorType, retryAttempt, cleanupCheckpoint
~~~

Không gắn raw business event ID, request ID hoặc tenant UUID có cardinality cao vào **mọi metric label**. Dynamic flow có thể tạo rất nhiều series nếu mỗi flow ID sinh ra một tag khác nhau. Chọn tag ổn định như <code>flowType</code>, <code>endpointType</code> và <code>outcome</code>; giữ correlation ID ở trace/log có chính sách bảo mật phù hợp.

### Integration graph và lifecycle snapshot

Nếu có <code>IntegrationGraphServer</code>, một snapshot graph giúp xác minh topology đã được thêm/gỡ:

~~~java
IntegrationGraphServer graphServer =
    applicationContext.getBean(IntegrationGraphServer.class);

var current = graphServer.rebuild();
log.info("Current integration graph: {}", current);
~~~

Các kiểu thuộc <code>org.springframework.integration.graph</code>. <code>rebuild()</code> có ý nghĩa sau dynamic registration/remove vì graph có thể được cache, nhưng **graph không phải bằng chứng message cụ thể đã được xử lý**. Khi shutdown, vẫn phải đối chiếu ingress, ACK, in-flight, queue/store và lifecycle.

## 17. Kiểm thử lifecycle bằng JUnit 5

Test lifecycle phải bắt được race và hoàn tất **có kiểm soát**, không dựa vào <code>Thread.sleep(1000)</code> rồi hy vọng worker đã xong. Với <code>QueueChannel</code>, test gửi/nhận nên dùng timeout hữu hạn. Với executor/in-flight, sử dụng latch hoặc future.

### 17.1. Test gate mở/đóng và giữ message trong queue

~~~java
@Test
void closedGateRejectsNewMessagesWithoutClearingBacklog() {
    QueueChannel queue = new QueueChannel(1);
    OrderAdmissionGate gate = new OrderAdmissionGate(queue);
    OrderCommand order = new OrderCommand("E-1", "O-1", 2);

    assertFalse(gate.submit(order)); // Ban đầu gate đóng.
    gate.open();
    assertTrue(gate.submit(order));
    assertEquals(1, queue.getQueueSize());

    gate.close();
    assertFalse(gate.submit(new OrderCommand("E-2", "O-2", 1)));
    assertEquals(1, queue.getQueueSize()); // Không bị xóa khi gate đóng.
    assertEquals(order, queue.receive(0).getPayload());
}
~~~

Test này chỉ chứng minh logic admission và queue trong một JVM. Nó không mô phỏng producer bypass gate hoặc crash trước khi message được persist.

### 17.2. Test race giữa submit và close()

Đây là test quan trọng để bảo đảm <code>close()</code> không báo hoàn tất khi một sender đang giữ read lock:

~~~java
@Test
void closeWaitsForAnAlreadyAcceptedSend() throws Exception {
    DirectChannel channel = new DirectChannel();
    CountDownLatch handlerEntered = new CountDownLatch(1);
    CountDownLatch releaseHandler = new CountDownLatch(1);
    CountDownLatch closeAttempted = new CountDownLatch(1);

    channel.subscribe(message -> {
        handlerEntered.countDown();
        try {
            if (!releaseHandler.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test handler timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    });

    OrderAdmissionGate gate = new OrderAdmissionGate(channel);
    gate.open();
    ExecutorService threads = Executors.newFixedThreadPool(2);
    try {
        Future<Boolean> sending = threads.submit(() ->
            gate.submit(new OrderCommand("E-1", "O-1", 2)));

        assertTrue(handlerEntered.await(2, TimeUnit.SECONDS));
        Future<?> closing = threads.submit(() -> {
            closeAttempted.countDown();
            gate.close();
        });

        assertTrue(closeAttempted.await(2, TimeUnit.SECONDS));
        assertFalse(closing.isDone()); // Send đang giữ read lock.

        releaseHandler.countDown();
        assertTrue(sending.get(2, TimeUnit.SECONDS));
        closing.get(2, TimeUnit.SECONDS);
        assertFalse(gate.submit(new OrderCommand("E-2", "O-2", 2)));
    } finally {
        releaseHandler.countDown();
        threads.shutdownNow();
    }
}
~~~

<code>CountDownLatch</code>, <code>ExecutorService</code>, <code>Executors</code>, <code>Future</code> và <code>TimeUnit</code> thuộc <code>java.util.concurrent</code>. Test này cố ý dùng <code>DirectChannel</code> để handler đồng bộ giữ read lock trong <code>send()</code>. Với <code>ExecutorChannel</code>, handler chạy sau submit nên lock chỉ bảo vệ **thời điểm accepted**, không bảo vệ completion của worker; cần <code>WorkDrainProbe</code> để drain.

### 17.3. Test endpoint không auto-start

Sử dụng <code>OrderRuntimeConfig</code> ở mục 5:

~~~java
@SpringJUnitConfig(OrderRuntimeConfig.class)
@SpringIntegrationTest(noAutoStartup = "orders.worker")
class OrderWorkerLifecycleTest {

    @Autowired
    @Qualifier("orders.worker")
    SmartLifecycle worker;

    @Autowired
    @Qualifier("orders.pending")
    QueueChannel pending;

    @Test
    void pendingMessageDoesNotRequireWorkerToBeRunning() {
        assertFalse(worker.isRunning());

        Message<OrderCommand> event = MessageBuilder
            .withPayload(new OrderCommand("E-10", "O-10", 1))
            .build();

        assertTrue(pending.send(event, 0));
        assertEquals(1, pending.getQueueSize());

        // Cleanup fixture vì test này cố ý không start poller.
        assertEquals(event, pending.receive(0));
    }

    @Test
    void workerCanBeStartedThenStopped() {
        assertFalse(worker.isRunning());
        worker.start();
        try {
            assertTrue(worker.isRunning());
        } finally {
            worker.stop();
        }
    }
}
~~~

<code>@SpringJUnitConfig</code> thuộc <code>org.springframework.test.context.junit.jupiter</code>; <code>@SpringIntegrationTest</code> thuộc <code>org.springframework.integration.test.context</code>. Với Spring TestContext cache, phải đảm bảo endpoint và queue được khôi phục về trạng thái fixture cần cho test sau, ví dụ qua cleanup sau mỗi test hoặc cô lập context. Từ góc nhìn vận hành, test này chứng minh queue vẫn nhận message khi consumer chưa start; nó **không** xác nhận message được xử lý nếu bạn không start worker.

### 17.4. Test dynamic registration được gỡ đúng

~~~java
@Test
void registeredFlowCanStartStopAndBeDestroyed() {
    String id = "test.flow.orders";
    AtomicInteger processed = new AtomicInteger();
    MessageHandler handler = msg -> processed.incrementAndGet();
    IntegrationFlow flow = IntegrationFlow.from(new DirectChannel())
        .handle(handler)
        .get();

    var registration = flowContext.registration(flow)
        .id(id)
        .useFlowIdAsPrefix()
        .autoStartup(false)
        .register();
    try {
        registration.start();
        assertTrue(registration.getInputChannel().send(
            MessageBuilder.withPayload("item").build()));
        assertEquals(1, processed.get());
        registration.stop();
    } finally {
        registration.destroy();
    }

    assertNull(flowContext.getRegistrationById(id));
}
~~~

<code>flowContext</code> là bean <code>IntegrationFlowContext</code> được inject vào test có Spring context; cần ID test duy nhất nếu các test chạy song song. Test chứng minh registration lifecycle và dispatch. Nó không chứng minh tài nguyên ngoại vi đã đóng hoặc pending message store đã được purge đúng.

## 18. Ma trận failure injection cho start, stop và cleanup

| Thời điểm lỗi | Hậu quả có thể xảy ra | Bằng chứng cần kiểm thử |
|---|---|---|
| Register flow trước khi dependency ready | Adapter/handler nhận message rồi fail | Admission vẫn đóng; không ACK ngoài ý muốn |
| Start handler thất bại | Endpoint còn stop, channel có thể không subscriber | Health/exception/log và recovery policy |
| Producer gửi đúng lúc gate đóng | Send thành công hoặc bị từ chối theo thứ tự cutoff | Không có send mới hoàn tất sau <code>close()</code> nếu phải qua gate |
| Stop <code>EventDrivenConsumer</code> khi sender còn chạy | <code>MessageDispatchingException</code> | Ngăn race bằng quiesce trước stop |
| Poller đã dequeue nhưng handler chưa xong | Queue rỗng nhưng chưa committed | Outstanding chưa về 0, không destroy |
| Executor có task chờ lúc shutdown | Task reject/interrupt hoặc side effect muộn | Task accepted/settled và shutdown policy |
| Reactive subscription bị cancel | Publisher terminal/cancel nhưng remote operation còn chạy | Cơ chế cancellation và external idempotency |
| DB commit thành công, broker ACK thất bại | Message được redeliver, có thể side effect trùng | Unique business event key chặn duplicate |
| Broker đã ACK nhưng queue chỉ in-memory | Crash mất message chưa xử lý | Thiết kế durable handoff, không ACK trước độ bền cần thiết |
| Error flow đóng trước producer/worker | <code>ErrorMessage</code> không có subscriber | Lỗi gốc vẫn được ghi nhận và có recovery |
| Delayer/aggregator còn group khi destroy | Message/group còn trong persistent store | Recovery/retention đúng, không xóa raw rows |
| Cleanup resource thất bại một phần | Leak socket, timer, bean phụ thuộc | Checkpoint + retry idempotent |
| Dynamic flow bị xóa và tạo lại cùng tenant | Cleanup cũ có thể đụng resource mới | Generation/owner fencing |
| Pod chết không chạy shutdown hook | In-memory state mất, dynamic registry biến mất | Rebuild/reconcile từ durable state |

### Định nghĩa tiêu chí PASS của game day

Một diễn tập “graceful shutdown thành công” cần xác nhận:

- Không có message được nhận **sau cutoff** mà thiếu recovery path;
- Những event đã accepted hoặc được **settled theo policy** hoặc có bằng chứng durable replay;
- Không có worker cũ tiếp tục ghi side effect trái quyền sau khi owner chuyển;
- Endpoint, timer, connection và custom resource được đóng theo ownership;
- Instance mới rebuild đúng flow được phép chạy, không revive tenant đang cleanup;
- Business event không tạo side effect trùng dù có redelivery;
- Metrics/trace/audit đủ để chứng minh các điều trên.

Việc process thoát với exit code 0 **không đủ** để đạt PASS nếu còn message đã ACK nhưng mất trong queue in-memory.

## 19. Runbook khi flow không chịu start, stop hoặc cleanup

| Triệu chứng | Nguyên nhân khả dĩ | Hành động điều tra |
|---|---|---|
| Đã khai báo flow nhưng không xử lý message | <code>autoStartup=false</code>, endpoint chưa start, input channel sai | Đọc <code>SmartLifecycle</code>, endpoint ID, subscriber count |
| Start rồi vẫn không ready | DB/broker/credentials không sẵn sàng, error sink thiếu | Readiness dependency và lỗi startup |
| <code>DirectChannel</code> không có subscriber | Endpoint stop/chưa start hoặc dynamic flow đã destroy | Admission, wiring và lifecycle timeline |
| Queue vẫn nhận nhưng không có output | Poller stop, handler chậm, queue backlog | Poller state, oldest age, worker/DB metrics |
| Stop rất lâu | In-flight blocking I/O, retry vô hạn, executor deadlock | Thread dump, outstanding, deadline và dependency |
| Stop báo xong nhưng task vẫn chạy | Async task đã submit trước stop, lifecycle khác completion | Worker active/queue và task completion metric |
| Restart làm mất message | Queue in-memory hoặc ACK quá sớm | Kiểm tra durable store/offset, recovery contract |
| Restart xử lý trùng | Side effect commit nhưng ACK thất bại | Business idempotency key, outbox/inbox |
| Flow đã destroy nhưng JDBC group còn | Persistent data không thuộc lifecycle bean | Region/group policy, retention job |
| Tenant khác bị gián đoạn sau cleanup | Shared executor/channel/connection bị đóng | Ownership map và bean destroy logs |
| Dynamic flow tạo lại rồi lỗi tên bean | ID/prefix trùng hoặc registration cũ chưa gỡ | <code>getRegistrationById()</code>, flow ID/generation |
| Metrics cho thấy 0 traffic sau rolling deploy | Admission chưa mở, source pause hoặc component ID đổi | Readiness, broker listener, graph rebuild |

### Runbook theo thứ tự

1. Xác định <code>flowId</code>, endpoint ID, channel type, instance/pod và thời điểm chuyển trạng thái.
2. Kiểm tra <code>SmartLifecycle.isRunning()</code>, autoStartup, phase và trạng thái gate.
3. Dựng timeline từ ingress accepted, worker started, handler completed, DB commit/ACK và error/retry.
4. Nếu start lỗi, không mở admission cho tới khi resource/consumer đạt readiness.
5. Nếu stop kẹt, phân biệt queue pending với in-flight và durable recovery; thu thread dump khi cần.
6. Nếu cleanup lỗi, xác minh resource nào thuộc riêng flow; không đóng singleton shared.
7. Nếu restart, đọc durable state và generation trước khi rebuild hoặc phát lại.
8. Tái hiện sự cố bằng test có latch, timeout và failure injection thay vì restart ngẫu nhiên.
9. Ghi checkpoint/hậu điều kiện, chuyển owner của DLQ/replay còn lại và chỉ đóng incident khi không có công việc mồ côi.

## 20. Checklist thiết kế production

- [ ] Có state machine rõ cho register, start, ready, quiesce, drain, stop và destroy.
- [ ] Readiness được bật **sau** khi consumer/dependency/recovery sink sẵn sàng; admission mặc định đóng.
- [ ] Mọi ingress quan trọng đi qua gate/routing có chính sách chặn khi shutdown/tenant deletion.
- [ ] Thứ tự <code>SmartLifecycle</code> phase được kiểm tra trên bean thật; không dựa duy nhất vào phase.
- [ ] Có accepted-but-unsettled tracker đúng completion boundary, không coi queue rỗng hoặc <code>send()==true</code> là commit.
- [ ] Poller không bị stop trước khi queue cần drain được xử lý hoặc chuyển sang durable recovery.
- [ ] Executor/scheduler có ownership, capacity, shutdown policy và deadline hữu hạn; không đóng resource shared từ một flow.
- [ ] Transaction/ACK/retry/idempotency được kiểm thử với broker/store đúng adapter.
- [ ] Pending message/group/delayer/outbox có retention và restart plan, không bị xóa cùng bean theo mặc định.
- [ ] Dynamic <code>IntegrationFlow</code> có ID ổn định, generation và cleanup idempotent; không double-destroy registration.
- [ ] Có reconciler sau crash, fencing giữa instance cũ và mới, startup không nhận traffic quá sớm.
- [ ] Graceful shutdown trong container có readiness-off, ingress quiesce, drain, stop và cleanup theo thứ tự.
- [ ] Có metrics/log/trace cho lifecycle state, queue, in-flight, error, cleanup time và resource leak.
- [ ] Có JUnit/integration test cho start/stop, admission race, queue pending, dynamic registration, restart và failure injection.
- [ ] Đã diễn tập timeout, poison message, loss of ACK, rolling deploy và cleanup thất bại giữa chừng.

**Kết luận:** Đảm bảo lifecycle của Spring Integration runtime nghĩa là thiết kế một **giao thức vận hành có hậu điều kiện kiểm chứng**, chứ không chỉ gọi <code>start()</code>, <code>stop()</code> rồi <code>destroy()</code>. Thứ tự bền vững là **chuẩn bị dependency và recovery → start consumer → công bố READY/mở admission → đóng ingress → drain hoặc bảo toàn pending → stop endpoint → dọn resource thuộc sở hữu → xác minh/reconcile**. Khi hiểu rõ channel, poller, executor, transaction và message store, ứng dụng có thể khởi động, dừng và nâng cấp mà không làm mất hoặc xử lý trùng message ngoài chính sách đã định.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Endpoints, Pollers và lifecycle](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference — Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Reference — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
