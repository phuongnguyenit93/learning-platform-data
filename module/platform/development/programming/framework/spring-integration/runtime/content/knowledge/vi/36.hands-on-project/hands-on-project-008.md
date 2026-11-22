# Kiểm thử graceful shutdown với message đang chờ trong Spring Integration Runtime

## 1. Bài toán thực hành và kết quả cần đạt

Trong module **SPRING_INTEGRATION_RUNTIME**, message đi qua **channel, endpoint, consumer, poller và executor**, có thể được lưu trong **MessageStore**, sau đó ghi DB hoặc gọi dịch vụ ngoài. Khi instance nhận SIGTERM vì rollout hoặc scale-down, không phải mọi message đều đã được xử lý. Một số message nằm trong **QueueChannel**, một số đã được consumer lấy ra nhưng handler còn chạy, một số đã commit DB nhưng broker chưa nhận acknowledgement.

Bài thực hành tổng hợp này tập trung vào một mục tiêu có thể **kiểm chứng bằng test**:

> Khi yêu cầu dừng, hệ thống ngừng nhận công việc mới, tiếp tục xử lý phần đã được chấp nhận trong một thời hạn hữu hạn, và **nói đúng sự thật** về những message chưa hoàn tất. Nếu buộc phải dừng khi backlog còn, kiến trúc phải phục hồi từ durable source/store; graceful shutdown một mình không thay thế durability.

Sau bài, bạn sẽ có:

- Một **fixture Spring Integration Java DSL** dùng DirectChannel → QueueChannel → polling consumer.
- Một **ingress gate** mô phỏng điểm ngừng nhận mới, có thao tác pause rõ ràng.
- Một **MessageHandler với CountDownLatch** để giữ một message in-flight và tạo backlog có thể đo.
- Các bài **JUnit 5** cho queue chưa drain, pause ingress, drain thành công, timeout khi handler bị chặn và stop consumer.
- Mô hình coordinator phân biệt **DRAINED** với **TIMED_OUT_WITH_PENDING** thay vì coi hết timeout là thành công.
- Bản thiết kế test nâng cao với **JDBC MessageStore, broker, transaction, retry, errorChannel, idempotency, crash/restart và Kubernetes grace period**.

**Phạm vi kỹ thuật:** Các ví dụ Java DSL dùng mô hình Spring Boot 3, Spring Integration 6.x, JDK 17+ và JUnit 5; API và cấu hình cần đối chiếu với BOM thực tế. Một số kịch bản dùng DB/broker/container thật được trình bày thành quy trình fault-injection vì test in-memory không thể tự chứng minh độ bền sau khi JVM chết.

## 2. Định nghĩa đúng “graceful” trước khi viết test

Giả sử một instance có topology:

~~~mermaid
flowchart LR
    SRC["Source / Broker"] --> IN["Ingress endpoint / gate"]
    IN --> C["DirectChannel"]
    C --> Q["pendingQueue - QueueChannel"]
    Q --> P["workConsumer - poller"]
    P --> H["Business handler"]
    H --> DB[("Business DB")]
    H --> EXT["External API"]
    H -. "Exception" .-> ERR["Retry / errorChannel"]
~~~

Khi ứng dụng được yêu cầu shutdown:

| Vùng công việc | Trạng thái cần quan sát | Ví dụ |
| --- | --- | --- |
| **Ingress** | Còn chấp nhận message mới không? | Broker listener, file adapter, gateway hoặc gate |
| **Queued** | Bao nhiêu message chưa bị consumer lấy? | QueueChannel, ChannelMessageStore |
| **In-flight** | Bao nhiêu handler đã bắt đầu nhưng chưa kết thúc? | Polling consumer, executor workers |
| **Unacked** | Nguồn đã giao nhưng chưa nhận ack/offset commit? | Kafka, JMS, AMQP |
| **Pending durable recovery** | Công việc lưu bền vững, chờ lần sau? | JDBC queue, inbox/outbox, retry journal |
| **Unknown external effects** | Remote effect đã thực hiện nhưng response mất? | HTTP payment, outbound messaging |

Một bài test chỉ gọi:

~~~java
consumer.stop();
assertFalse(consumer.isRunning());
~~~

**không đủ** để gọi là test graceful shutdown. Nó chỉ quan sát lifecycle state của consumer. Message có thể vẫn nằm trong queue, trong executor hoặc đang được xử lý bởi task đã bắt đầu.

### Các bất biến sẽ kiểm thử

1. **Sau pause:** ingress được kiểm soát không nhận thêm message.
2. **Trong drain:** consumer vẫn được phép xử lý queue đã có.
3. **Trước deadline:** nếu queued = 0 và in-flight = 0, có thể kết luận **đã drain phần việc trong phạm vi test**.
4. **Sau deadline:** nếu queued hoặc in-flight còn, kết quả là **TIMED_OUT_WITH_PENDING**, không phải **DRAINED**.
5. **Khi stop consumer:** không còn lượt poll mới theo hợp đồng endpoint; tác vụ đang chạy dở được quan sát riêng.
6. **Khi restart:** công việc bắt buộc không mất phải do **durable source/store** giữ, không chỉ QueueChannel in-memory.
7. **Khi redelivery:** hai delivery cùng eventId không được tạo hai **business side effects**.

**DRAINED, TIMED_OUT_WITH_PENDING và DATA_LOSS_RISK là nhãn do bài lab định nghĩa**, không phải enum Spring Integration tự cung cấp.

## 3. Vì sao dùng CountDownLatch thay vì Thread.sleep?

Muốn test queue còn message khi shutdown, trước hết cần **tạo được trạng thái đó một cách chắc chắn**.

Một test không ổn định:

~~~java
input.send(message);
Thread.sleep(100);
assertEquals(2, pendingQueue.getQueueSize());
~~~

Nó phụ thuộc vào tốc độ CI, lịch TaskScheduler, số thread rảnh và thời gian chạy handler.

Thay bằng hai tín hiệu:

- **firstStarted:** handler đã thực sự nhận message thứ nhất.
- **releaseFirst:** test quyết định khi nào handler được tiếp tục.

~~~mermaid
sequenceDiagram
    participant T as JUnit
    participant Q as QueueChannel
    participant P as Polling Consumer
    participant H as Blocking Handler
    T->>Q: Enqueue EV-1, EV-2, EV-3
    T->>P: start()
    P->>Q: receive EV-1
    Q-->>P: EV-1
    P->>H: handle EV-1
    H-->>T: firstStarted.countDown()
    Note over H: Wait on releaseFirst
    Note over Q: EV-2 và EV-3 còn queued
    T->>T: Assert queued=2, in-flight=1
    T->>H: releaseFirst.countDown()
    H-->>P: EV-1 completed
    P->>Q: receive EV-2, rồi EV-3
~~~

Với **một polling consumer xử lý đồng bộ**, khi EV-1 bị giữ trong handler, EV-2/EV-3 chưa được poll tiếp. Test quan sát snapshot này **không cần đoán thời gian xử lý**.

### Thread boundary trong lab

~~~text
JUnit thread:
    gate.submit(EV-1/EV-2/EV-3)
      → DirectChannel
      → QueueChannel enqueue
    returns

TaskScheduler / polling consumer thread:
    QueueChannel.receive()
    → BlockingOrderHandler.handleMessage()
    → success / failure
~~~

**send() thành công** nghĩa message được channel chấp nhận theo contract, **chưa** chứng minh business handler hoàn tất. Phải quan sát **queue depth, in-flight và kết quả cuối**.

## 4. Chuẩn bị project và dependencies

Một project Maven/Gradle Spring Boot cần:

| Dependency | Vai trò |
| --- | --- |
| **spring-boot-starter-integration** | Spring Integration core và Boot configuration |
| **spring-integration-test** | @SpringIntegrationTest, MockIntegrationContext và test utilities |
| **spring-boot-starter-test** | JUnit 5 và Spring Test |
| **spring-boot-starter-jdbc** | Cho test JDBC/transaction nâng cao |
| **spring-integration-jdbc** | Cho JdbcChannelMessageStore nếu cần persistent queue |
| **PostgreSQL driver / Testcontainers** | Cho test DB sống qua application restart |

Gradle minh họa cho lab in-memory:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<boot-version-from-project>'
    id 'io.spring.dependency-management' version '<compatible-version>'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.integration:spring-integration-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Các chuỗi dạng <...> trong Gradle là placeholder**, không phải version thật; chọn phiên bản theo BOM của project. Không trộn tùy ý Spring Integration 5.x với 6.x.

Các class Java dưới đây đặt trong cùng package:

~~~text
src/test/java/.../shutdown/
  ShutdownLabConfiguration.java
  IngressGate.java
  BlockingOrderHandler.java
  GracefulDrainTest.java
~~~

## 5. Tạo ingress gate mô phỏng ngừng nhận message

Lab không cần broker thật. **IngressGate** mô phỏng hợp đồng “sau pause, caller không thể enqueue message mới”.

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

final class IngressGate {
    private final MessageChannel input;
    private boolean accepting = true;

    IngressGate(MessageChannel input) {
        this.input = input;
    }

    synchronized boolean submit(String eventId) {
        if (!accepting) {
            return false;
        }
        return input.send(
                MessageBuilder.withPayload(eventId)
                        .setHeader("eventId", eventId)
                        .build());
    }

    synchronized void pause() {
        accepting = false;
    }

    synchronized void resume() {
        accepting = true;
    }

    synchronized boolean isAccepting() {
        return accepting;
    }
}
~~~

**Tại sao synchronized?** Đồng bộ hóa bảo đảm pause không chen vào giữa kiểm tra accepting và send của một request khác. Trong fixture, đường sau input là DirectChannel → QueueChannel nên enqueue hoàn tất đồng bộ.

**Giới hạn:** Gate là **API ứng dụng tự viết**, không phải SourcePollingChannelAdapter.stop() hoặc broker consumer stop. Trong production phải dừng **đúng inbound endpoint/container** và xác minh các delivery đang in-flight. Một caller gửi thẳng vào input bỏ qua gate thì gate không thể chặn.

## 6. Tạo handler có thể giữ message đang xử lý

Handler dùng các tín hiệu:

- **firstStarted**: đã bắt đầu EV-1.
- **releaseFirst**: test cho phép EV-1 tiếp tục.
- **inFlight**: số handler đang chạy.
- **allCompleted**: ba message đã được handler xử lý xong.

~~~java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

final class BlockingOrderHandler implements MessageHandler {
    final CountDownLatch firstStarted = new CountDownLatch(1);
    final CountDownLatch releaseFirst = new CountDownLatch(1);
    final CountDownLatch allCompleted = new CountDownLatch(3);

    private final AtomicInteger invocations = new AtomicInteger();
    private final AtomicInteger inFlight = new AtomicInteger();
    private final Queue<String> completed = new ConcurrentLinkedQueue<>();

    @Override
    public void handleMessage(Message<?> message) {
        inFlight.incrementAndGet();
        boolean success = false;
        try {
            int visit = invocations.incrementAndGet();
            if (visit == 1) {
                firstStarted.countDown();
                if (!releaseFirst.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Test did not release first message");
                }
            }

            completed.add((String) message.getPayload());
            success = true;
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Handler interrupted before completion", interrupted);
        } finally {
            inFlight.decrementAndGet();
            if (success) {
                allCompleted.countDown();
            }
        }
    }

    int activeCount() {
        return inFlight.get();
    }

    int completedCount() {
        return completed.size();
    }

    Queue<String> completedEvents() {
        return completed;
    }
}
~~~

**Giới hạn của bộ đo trong test:**

1. Handler chặn **lần gọi đầu tiên**, không phụ thuộc chuỗi eventId. Mỗi test cần fixture độc lập.
2. inFlight bao quanh **handleMessage**, không đo task đang chờ executor, ACK nguồn hoặc DB commit ở proxy tầng ngoài.
3. completed là kết quả **trong RAM**, không thay business state đã commit.
4. Test luôn phải thả latch trong nhánh cleanup, không chờ vô hạn.
5. Nếu thêm ExecutorChannel hoặc nhiều polling consumers, queue depth/ordering sẽ khác; phải sửa assertions theo topology.

## 7. Tạo IntegrationFlow có polling consumer thật

Hai flow: **ingressFlow** enqueue message, **processingFlow** poll và gọi BlockingOrderHandler. Endpoint được đặt ID **workConsumer** để test start/stop.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class ShutdownLabConfiguration {

    @Bean("ingressInput")
    MessageChannel ingressInput() {
        return new DirectChannel();
    }

    @Bean("pendingQueue")
    QueueChannel pendingQueue() {
        // In-memory queue: không durable qua JVM restart.
        return new QueueChannel();
    }

    @Bean
    IngressGate ingressGate(
            @Qualifier("ingressInput") MessageChannel ingressInput) {
        return new IngressGate(ingressInput);
    }

    @Bean
    BlockingOrderHandler blockingOrderHandler() {
        return new BlockingOrderHandler();
    }

    @Bean
    IntegrationFlow ingressFlow() {
        return IntegrationFlow.from("ingressInput")
                .channel("pendingQueue")
                .get();
    }

    @Bean
    IntegrationFlow processingFlow(BlockingOrderHandler handler) {
        return IntegrationFlow.from("pendingQueue")
                .handle(handler, endpoint -> endpoint
                        .id("workConsumer")
                        .poller(Pollers.fixedDelay(25)
                                .maxMessagesPerPoll(1)))
                .get();
    }
}
~~~

Trong fixture:

- **DirectChannel** không tạo thread boundary giữa ingress và enqueue.
- **QueueChannel** giữ message chờ và tạo ranh giới producer/consumer.
- **PollingConsumer** lấy message theo fixed-delay và gọi handler.
- **maxMessagesPerPoll(1)** giúp EV-2/EV-3 nằm chờ khi EV-1 bị chặn.
- **ID workConsumer** cho phép tìm đúng endpoint lifecycle, không đoán tên do DSL tạo tự động.

**Phạm vi:** fixedDelay(25) dùng giá trị milliseconds trong DSL thông dụng; khi đổi API/version nên kiểm tra overload và đơn vị. Đây là cấu hình cho lab, production còn cần transaction, capacity và error handling.

### Không tạo thêm subscriber “quan sát” vào DirectChannel

DirectChannel thường điều phối một message tới **một subscriber**. Gắn thêm handler debug có thể cạnh tranh với business flow. Khi cần quan sát mà không đổi dispatch, dùng **WireTap** hoặc channel kiểm thử riêng.

## 8. JUnit 5: tạo backlog, pause ingress và drain

Dùng **@SpringIntegrationTest(noAutoStartup = "workConsumer")** để polling endpoint không chạy ngay khi tạo context; test chủ động start. **@DirtiesContext** cách ly QueueChannel và CountDownLatch giữa các phương thức.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.Lifecycle;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ShutdownLabConfiguration.class)
@SpringIntegrationTest(noAutoStartup = "workConsumer")
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class GracefulDrainTest {

    @Autowired
    IngressGate gate;

    @Autowired
    @Qualifier("pendingQueue")
    QueueChannel pendingQueue;

    @Autowired
    BlockingOrderHandler handler;

    @Autowired
    @Qualifier("workConsumer")
    Lifecycle consumer;

    @AfterEach
    void cleanup() {
        // Không để worker bị giữ khi assertion thất bại.
        handler.releaseFirst.countDown();
        consumer.stop();
    }

    @Test
    void stoppedConsumerDoesNotDrainQueue() throws Exception {
        assertFalse(consumer.isRunning());
        assertTrue(gate.submit("EV-1"));
        assertTrue(gate.submit("EV-2"));
        assertTrue(gate.submit("EV-3"));

        assertEquals(3, pendingQueue.getQueueSize());
        assertEquals(0, handler.activeCount());
        gate.pause();
        assertFalse(gate.submit("EV-4"));
        assertEquals(3, pendingQueue.getQueueSize());
        assertEquals(0, handler.completedCount());
        assertFalse(handler.allCompleted.await(
                150, TimeUnit.MILLISECONDS));
    }

    @Test
    void pauseIngressAndDrainAllPendingMessages() throws Exception {
        assertTrue(gate.submit("EV-1"));
        assertTrue(gate.submit("EV-2"));
        assertTrue(gate.submit("EV-3"));
        assertEquals(3, pendingQueue.getQueueSize());

        gate.pause();
        assertFalse(gate.isAccepting());
        assertFalse(gate.submit("EV-4"));

        // Giữ consumer chạy trong pha drain.
        consumer.start();
        try {
            assertTrue(handler.firstStarted.await(
                    3, TimeUnit.SECONDS));
            assertEquals(2, pendingQueue.getQueueSize());
            assertEquals(1, handler.activeCount());
            assertEquals(0, handler.completedCount());

            handler.releaseFirst.countDown();
            assertTrue(handler.allCompleted.await(
                    5, TimeUnit.SECONDS));

            assertEquals(0, pendingQueue.getQueueSize());
            assertEquals(0, handler.activeCount());
            assertEquals(3, handler.completedCount());
            assertEquals(Set.of("EV-1", "EV-2", "EV-3"),
                    new HashSet<>(handler.completedEvents()));

            consumer.stop();
            assertFalse(consumer.isRunning());
        } finally {
            handler.releaseFirst.countDown();
        }
    }

    @Test
    void deadlineCanExpireWhileMessagesRemain() throws Exception {
        assertTrue(gate.submit("EV-1"));
        assertTrue(gate.submit("EV-2"));
        assertTrue(gate.submit("EV-3"));
        gate.pause();

        consumer.start();
        try {
            assertTrue(handler.firstStarted.await(
                    3, TimeUnit.SECONDS));
            assertEquals(2, pendingQueue.getQueueSize());
            assertEquals(1, handler.activeCount());

            boolean allDoneWithinBudget =
                    handler.allCompleted.await(
                            150, TimeUnit.MILLISECONDS);
            assertFalse(allDoneWithinBudget);
            assertEquals(2, pendingQueue.getQueueSize());
            assertEquals(1, handler.activeCount());

            // Cleanup: thả worker trước khi đóng context.
            handler.releaseFirst.countDown();
            assertTrue(handler.allCompleted.await(
                    5, TimeUnit.SECONDS));
        } finally {
            handler.releaseFirst.countDown();
        }
    }
}
~~~

### Cách đọc từng test

| Test | Trạng thái đã tạo | Kết luận thực sự |
| --- | --- | --- |
| stoppedConsumerDoesNotDrainQueue | Queue có 3; consumer chưa start | Queue không tự xử lý khi không có polling consumer |
| pauseIngressAndDrainAllPendingMessages | Ngừng nhận mới, giữ EV-1 in-flight và hai message queued, rồi thả worker | Với **fixture 3 message**, cả ba hoàn tất, queue trống, in-flight về 0 |
| deadlineCanExpireWhileMessagesRemain | Handler bị giữ trong khoảng deadline thử | Hết budget có thể xảy ra khi vẫn queued/in-flight; không được báo DRAINED |

**Điều test chưa chứng minh:** Không có broker, JDBC store, DB transaction hay external side effect. Consumer được start/stop bằng lifecycle; ingress là **gate mô phỏng**. Muốn chứng minh graceful shutdown trên một pod thật cần thêm integration test với transport và resource thực.

### Vì sao không gọi stop() ngay khi handler đang bị chặn?

Stop một polling consumer trong lúc handler chờ latch có thể làm kết quả phụ thuộc lifecycle callback, executor và TaskScheduler, thậm chí treo nếu test chưa giải phóng worker. Bài test tập trung vào **timeout khi pending**, nên thả worker trong finally. Hành vi stop khi có in-flight cần một test riêng với deadline, interrupt và cleanup được kiểm soát.

### Vì sao dùng context riêng?

Spring Test có thể cache ApplicationContext. Nếu không cách ly, CountDownLatch và QueueChannel từ một test có thể ảnh hưởng test tiếp theo. **@DirtiesContext** giúp test dễ hiểu nhưng có chi phí khởi tạo context; suite lớn có thể reset fixture nếu chứng minh không còn task in-flight.

## 9. Queued không đồng nghĩa in-flight, cũng không đồng nghĩa committed

Ở thời điểm EV-1 đã dequeue và chờ releaseFirst:

~~~text
ingress accepting = false
pendingQueue size = 2
handler in-flight = 1
completed count = 0
~~~

**Tổng số công việc chưa hoàn tất là 3**, không phải 2. Queue depth chỉ đếm message còn chờ, không đếm message đang nằm trong handler.

Khi đã thả handler và đợi đủ ba completion:

~~~text
ingress accepting = false
pendingQueue size = 0
handler in-flight = 0
completed count = 3
~~~

Đây là **DRAINED trong phạm vi lab**. Ở production còn cần xem executor queued, broker unacked, DB commit, outbox pending và external effect chưa xác nhận.

### Snapshot đơn lẻ có thể bị race

Giữa **QueueChannel.receive()** và thời điểm handler tăng inFlight có thể có một khoảng ngắn queue đã giảm nhưng handler chưa được đánh dấu active. Vì vậy điều kiện:

~~~java
boolean drained = pendingQueue.getQueueSize() == 0
        && handler.activeCount() == 0;
~~~

**không đủ làm điều kiện chính xác tuyệt đối** khi consumer vẫn có thể dequeue. Trong lab, CountDownLatch **allCompleted** biết có đúng ba message; ở production cần **ownership tracking bao cả dequeue→commit, ack/transaction state** hoặc một quiesce barrier được thiết kế.

Ngoài ra, nếu handler có AOP transaction, DB commit có thể xảy ra **sau khi method return**, nên inFlight trong method không mặc định đo tới thời điểm commit. Business completion cần dựa trên điểm **đã commit/ack** hoặc trạng thái bền vững.

## 10. Mô hình hóa kết quả shutdown thay vì trả một Boolean

Một shutdown coordinator phải phân biệt:

| Outcome do ứng dụng định nghĩa | Ý nghĩa | Hành động |
| --- | --- | --- |
| **DRAINED** | Công việc trong phạm vi phải hoàn tất đã có outcome xác nhận | Đóng downstream và resource |
| **TIMED_OUT_WITH_DURABLE_PENDING** | Hết thời gian; phần còn lại lưu bền vững, có đường replay | Đóng instance, chuyển ownership cho worker mới |
| **TIMED_OUT_WITH_UNACKED** | Nguồn còn delivery chưa ack theo contract | Theo dõi redelivery sau restart |
| **RECONCILIATION_REQUIRED** | External effect chưa biết thành công hay không | Truy vấn provider bằng operationId, không replay mù |
| **DATA_LOSS_RISK** | Có việc trong RAM và nguồn có thể đã ack | Không tuyên bố an toàn; sửa durable handoff |
| **FAILED_TO_QUIESCE** | Một producer/replica vẫn nhận message | Không kết luận drain từ một queueDepth snapshot |

Đây là **nhãn do bài lab định nghĩa**, không phải enum built-in của Spring Integration.

### Một snapshot cần chứa gì?

~~~java
record DrainSnapshot(
        boolean ingressPaused,
        long queuePending,
        long handlersInFlight,
        long executorQueued,
        long sourceUnacked,
        long unresolvedEffects) {

    boolean noKnownPendingWork() {
        return ingressPaused
                && queuePending == 0
                && handlersInFlight == 0
                && executorQueued == 0
                && sourceUnacked == 0
                && unresolvedEffects == 0;
    }
}
~~~

- **queuePending** phải được đo mà không tiêu thụ message; không gọi receive() để đếm.
- **handlersInFlight** phải bao đúng giai đoạn việc ứng dụng sở hữu, kể cả commit khi cần.
- **executorQueued** là hàng đợi task riêng, không nằm trong QueueChannel depth.
- **sourceUnacked** phụ thuộc broker/adapter; khi không đo được, ghi **UNKNOWN**, không tự điền 0.
- **unresolvedEffects** gồm external API outcome chưa biết hoặc công việc chưa có trạng thái bền vững.

**Một snapshot toàn số 0 chưa phải bằng chứng tuyệt đối**: có thể tồn tại khoảng hở giữa dequeue và tăng inFlight. Cần quiesce barrier, trạng thái sở hữu công việc và kiểm chứng durable outcome.

### Helper chờ deadline hữu hạn

Ví dụ chỉ minh họa quản lý thời hạn, không tự stop adapter hoặc làm snapshot atomic:

~~~java
import java.time.Duration;
import java.util.function.Supplier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

enum WaitOutcome {
    NO_KNOWN_PENDING,
    DEADLINE_EXCEEDED,
    INTERRUPTED
}

record WaitResult(WaitOutcome outcome, DrainSnapshot last) {}

final class DrainDeadline {
    static WaitResult await(Supplier<DrainSnapshot> sample,
                            Duration budget) {
        long start = System.nanoTime();
        long limit = Math.max(0, budget.toNanos());

        for (;;) {
            DrainSnapshot snapshot = sample.get();
            if (snapshot.noKnownPendingWork()) {
                return new WaitResult(
                        WaitOutcome.NO_KNOWN_PENDING, snapshot);
            }

            long remaining = limit - (System.nanoTime() - start);
            if (remaining <= 0) {
                return new WaitResult(
                        WaitOutcome.DEADLINE_EXCEEDED, snapshot);
            }

            LockSupport.parkNanos(Math.min(
                    remaining, TimeUnit.MILLISECONDS.toNanos(20)));
            if (Thread.currentThread().isInterrupted()) {
                return new WaitResult(
                        WaitOutcome.INTERRUPTED, snapshot);
            }
        }
    }
}
~~~

**Không chạy helper trên worker duy nhất cần xử lý backlog**: thread chờ có thể chiếm mất slot xử lý. Nếu dùng trong production, gọi trên management thread và kết hợp quiescence invariant. NO_KNOWN_PENDING vẫn phải xác nhận qua business/durable state trước khi gọi DRAINED.

### Test deadline helper

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class DrainDeadlineTest {

    @Test
    void returnsTimeoutWhenPending() {
        DrainSnapshot pending = new DrainSnapshot(
                true, 2, 1, 0, 0, 0);

        WaitResult result = DrainDeadline.await(
                () -> pending, Duration.ofMillis(50));

        assertEquals(
                WaitOutcome.DEADLINE_EXCEEDED, result.outcome());
        assertEquals(2, result.last().queuePending());
        assertEquals(1, result.last().handlersInFlight());
    }

    @Test
    void acceptsQuiescedSnapshot() {
        DrainSnapshot done = new DrainSnapshot(
                true, 0, 0, 0, 0, 0);

        WaitResult result = DrainDeadline.await(
                () -> done, Duration.ofMillis(50));

        assertEquals(
                WaitOutcome.NO_KNOWN_PENDING, result.outcome());
    }
}
~~~

Những test này xác minh **logic của helper**, không phải độ chính xác millisecond của scheduler hoặc thời hạn stop thực sự của Spring/Kubernetes.

## 11. Test lifecycle thực: stop ingress trước, stop consumer sau

Trong fixture, gate chỉ mô phỏng ingress. Ở ứng dụng thật, phải xác định **endpoint tạo message** và **endpoint tiêu thụ backlog**.

~~~mermaid
flowchart LR
    S["File / Broker source"] --> A["ordersInboundEndpoint"]
    A --> Q["ordersQueue"]
    Q --> P["ordersProcessingEndpoint"]
    P --> H["Business handler"]
    CMD["Admin / shutdown coordinator"] -. "stop ingress" .-> A
    CMD -. "stop sau drain" .-> P
~~~

### Trình tự cần kiểm thử

1. Chuyển instance sang **QUIESCING** để ngăn nhận công việc mới.
2. Stop **ordersInboundEndpoint** hoặc broker listener/container theo lifecycle của adapter.
3. Xác minh đúng **instance/endpoint** đã dừng ingress. Nếu có nhiều inbound producers đổ vào cùng queue, phải quiesce tất cả nguồn liên quan.
4. Giữ **ordersProcessingEndpoint** và DB/executor downstream hoạt động để drain.
5. Quan sát queue, in-flight, source unacked, transaction, retry và pending effects.
6. Khi đã drain hoặc đạt điểm durable handoff an toàn, mới stop consumer, executor và resource.

**Control Bus** có thể gửi biểu thức SpEL vào endpoint lifecycle:

~~~text
@ordersInboundEndpoint.stop()
@ordersInboundEndpoint.isRunning()
@ordersInboundEndpoint.start()
~~~

Nhưng **Control Bus không tự drain queue**. Đây là đường quản trị đặc quyền cao: không chuyển biểu thức do caller không tin cậy cung cấp trực tiếp tới controlBus, mà phải có authentication, authorization và allowlist.

### Spring Integration Orderly Shutdown

Spring Integration có cơ chế **Orderly Shutdown** thông qua management API như **IntegrationMBeanExporter.stopActiveComponents(long howLong)** trong các phiên bản phù hợp. Ý tưởng là dừng nguồn/producer trước và cho những message đang ở giữa flow thời gian hoàn tất.

~~~java
// Fragment trong ứng dụng đã cấu hình IntegrationMBeanExporter:
// howLong được tính bằng MILLISECONDS.
exporter.stopActiveComponents(30_000L);
~~~

**Không được giả định** mọi ứng dụng Spring Boot tự gọi đúng cơ chế này khi nhận SIGTERM. Test production phải xác minh ai gọi, ở phase nào, trước hay sau khi lifecycle processor stop downstream consumer, và thời gian còn lại trong termination budget.

### Trạng thái lifecycle khác trạng thái nghiệp vụ

~~~text
INGRESS_STOPPED
DRAINING
DRAINED
PENDING_DURABLE
STOPPED
~~~

Đây là **state machine ứng dụng**, không phải một chuỗi trạng thái do SmartLifecycle tự quản. Endpoint báo **isRunning=false** vẫn có thể còn handler in-flight hoặc transaction chờ commit.

## 12. Persistent QueueChannel: bài kiểm thử in-memory chưa đủ

QueueChannel mặc định dùng queue trong heap. Một lần stop và restart **ApplicationContext** trong cùng JVM với một bean QueueChannel mới **không bảo tồn message cũ**. Crash JVM còn làm mọi task pending RAM biến mất.

| Nơi message đang tồn tại | Khi JVM chết | Cần kiểm chứng |
| --- | --- | --- |
| **QueueChannel in-memory** | Queue state biến mất | Source có thể replay hay đã ack? |
| **Executor task queue in-memory** | Task chưa chạy có thể mất | Handoff đã durable chưa? |
| **JdbcChannelMessageStore** | Bản ghi đã commit có thể được đọc lại | Schema, query provider, group ID, transaction |
| **Broker còn unacked** | Có thể redeliver theo protocol/adapter | Ack mode, lease/offset, idempotency |
| **Transactional inbox/outbox** | State đã commit có thể sống qua restart | Có consumer/publisher mới tiếp tục? |
| **External provider** | Side effect có thể đã xảy ra | Operation ID và reconciliation |

### Fragment Java configuration với JdbcChannelMessageStore

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;

@Configuration
class DurableQueueLabConfiguration {

    @Bean
    JdbcChannelMessageStore channelMessageStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        return store;
    }

    @Bean("durablePendingQueue")
    QueueChannel durablePendingQueue(
            JdbcChannelMessageStore channelMessageStore) {
        return new QueueChannel(new MessageGroupQueue(
                channelMessageStore, "orders-shutdown-lab"));
    }
}
~~~

Đây là **fragment bổ sung**, không phải thay thế drop-in cho toàn bộ ShutdownLabConfiguration. Muốn chạy:

- Thêm **spring-integration-jdbc**, DataSource/PostgreSQL driver, transaction manager phù hợp và **schema Spring Integration JDBC** của version đang dùng.
- Dùng **groupId ổn định** (ví dụ orders-shutdown-lab) qua các lần start/restart. Nếu groupId hoặc region thay đổi, worker mới có thể không nhìn thấy message cũ.
- Chọn query provider theo database thật; ví dụ dùng PostgreSQL.
- Bảo đảm payload/headers có serializer tương thích qua restart/version change, đặc biệt không lưu object replyChannel chỉ có trong JVM nếu không có chiến lược resolver phù hợp.
- Tạo polling consumer cho **durablePendingQueue** và quyết định rõ transaction của receive/dequeue.

**Điểm học quan trọng:** Đổi in-memory QueueChannel thành persistent store giúp lưu **message chưa bị dequeue** nếu write đã commit, nhưng **không tự làm mọi handler và external API atomic**.

## 13. Test transaction: dequeue rồi handler lỗi có quay lại queue?

Với một queue backed by **JdbcChannelMessageStore**, test cần phân biệt **transaction được mở ở đâu**.

### Topology mong muốn

~~~text
JDBC QueueChannel (message đã commit)
    ↓
PollingConsumer mở transaction TX-A
    ↓
QueueChannel.receive() trong TX-A
    ↓
Business handler thực thi đồng bộ trong TX-A
    ↓
COMMIT nếu success / ROLLBACK nếu failure
~~~

Một fragment XML thể hiện transaction advice ở poller:

~~~xml
<int:service-activator
        input-channel="durablePendingQueue"
        ref="orderHandler"
        method="handle">
    <int:poller fixed-delay="50" max-messages-per-poll="1">
        <int:transactional
                transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

Đây là fragment; cần namespace, bean và transactionManager trong cấu hình đầy đủ. Với transaction/DB resource phù hợp, dequeue và handler đồng bộ có thể được commit/rollback cùng nhau.

### Kịch bản kiểm thử rollback

1. Bắt đầu PostgreSQL/test DB có schema Spring Integration JDBC.
2. Ghi EV-42 vào durablePendingQueue và **commit**.
3. Cấu hình handler lần đầu ném một exception đã định trước; không để recovery callback nuốt lỗi rồi báo success.
4. Cho polling consumer nhận EV-42 **trong transaction**.
5. Xác minh transaction rollback và message vẫn còn khả năng được poll lại.
6. Cho handler lần sau thành công; xác minh business DB commit, queue entry được remove đúng cách.
7. Đếm số handler attempts và số business effects riêng biệt: **hai attempts** vẫn có thể chỉ tạo **một logical completion**.

**Đừng dùng QueueChannel in-memory cho test này rồi kết luận JDBC rollback đúng.** Cơ chế remove/rollback phụ thuộc message store và transaction manager cụ thể.

### Một ranh giới nguy hiểm: poller → ExecutorChannel

~~~text
TX-A trên polling consumer:
  JDBC queue.receive(EV-42)
  ExecutorChannel.send(EV-42)
  COMMIT TX-A; queue row bị remove

Worker thread:
  task còn trong executor RAM
  JVM bị kill
~~~

Khi đó EV-42 **có thể mất** dù queue ban đầu persistent, vì durable dequeue đã commit **trước khi worker làm business effect**. Đó là lỗi thiết kế **handoff/transaction boundary**, không chữa được bằng tăng shutdown timeout.

**Giải pháp:** Đưa việc sang durable inbox/broker/work queue mới **trước khi commit dequeue**, hoặc giữ đoạn xử lý cần atomic trong cùng transaction phù hợp. Dùng idempotency và fault-injection test để xác nhận không có lỗ hổng giữa các mốc commit.

## 14. Broker ACK: message còn ở queue có được nguồn giao lại không?

Trong lab in-memory, input.send() được gọi trực tiếp từ JUnit. Ở production, phần lớn ứng dụng có **source adapter**: Kafka, JMS, AMQP, file, JDBC hoặc HTTP.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant A as Inbound Adapter
    participant Q as QueueChannel
    participant W as Worker
    B->>A: Deliver EV-42
    A->>Q: send EV-42
    Q-->>A: accepted
    opt Một cấu hình ack sớm
        A-->>B: ACK / commit offset
    end
    Note over Q: Message đang chờ trong queue
    Note over Q,W: Process bị kill trước khi worker xử lý
~~~

**Nguy cơ:** Nếu nguồn đã nhận ACK/offset commit, message chỉ còn trong **QueueChannel in-memory** rồi JVM chết, source có thể không giao lại EV-42. Từ góc nhìn producer, việc đã được chấp nhận, nhưng từ góc nhìn nghiệp vụ, công việc chưa hề được thực hiện.

### Không có một hợp đồng ACK chung cho mọi adapter

| Source | Test phải xác minh cụ thể |
| --- | --- |
| **Kafka** | Consumer poll, offset commit mode, listener transaction/error handling, rebalance và thời điểm handoff |
| **JMS** | Session transaction, ack mode, listener container stop và redelivery |
| **AMQP/RabbitMQ** | Manual/auto ack, requeue, prefetch, consumer cancel và connection close |
| **File/FTP/SFTP** | File filter, metadata/checkpoint, move/delete/staging, replay file |
| **JDBC polling source** | Row claim/status update, transaction commit, duplicate selection |
| **HTTP inbound gateway** | Khi nào trả 2xx, request đang mở, HTTP retry của client, durable acceptance |

**Không suy luận rằng handler ném exception luôn dẫn tới redelivery.** Nếu trước đó nguồn đã ack hoặc recovery handler đã xử lý lỗi, contract có thể khác. Ngược lại, broker at-least-once có thể redeliver dù side effect đã commit.

### Hai phép kiểm thử đối xứng

**Case A — ACK trước durable handoff:** Gửi EV-42, cho adapter ACK sau khi enqueue vào QueueChannel RAM, kill process trước khi worker xử lý. Sau restart, kiểm tra liệu EV-42 có còn ở nguồn hay store không. Nếu không, đây là **DATA_LOSS_RISK** cần sửa kiến trúc.

**Case B — Handoff durable trước ACK:** Gửi EV-43, commit durable inbox/JDBC queue trước khi ACK, kill process trước khi worker xử lý. Sau restart, worker mới phải thấy EV-43 từ store hoặc source replay, rồi hoàn tất business operation.

Đối chiếu **cả source metadata và database state**, không chỉ log từ consumer. Việc mất log hoặc chậm scrape metrics không đủ chứng minh mất message.

## 15. Crash/restart: test riêng process, không chỉ đóng ApplicationContext

Muốn xác nhận message sống qua restart, tốt nhất sử dụng **hai lần chạy process/container khác nhau** cùng kết nối tới một external store/broker vẫn tồn tại.

~~~mermaid
flowchart TD
    DB[("PostgreSQL + broker giữ nguyên")]
    A["Process A"] -->|commit pending EV-42| DB
    A -->|kill/crash| X["Process A biến mất"]
    DB -->|đọc pending| B["Process B"]
    B --> H["Business handler"]
    H --> Y[("Business state committed")]
~~~

### Test P1 — Pending JDBC queue sống qua restart

1. Dựng PostgreSQL với schema/message store phù hợp.
2. Khởi động Process A, tạo QueueChannel có groupId **orders-shutdown-lab** và **không cho polling consumer start**.
3. Gửi ba event EV-1, EV-2, EV-3; xác minh transaction enqueue đã commit.
4. Kill Process A; **không xóa database** và không reset group metadata.
5. Khởi động Process B dùng **cùng DataSource/schema/region/groupId và serializer**.
6. Start consumer, thu ba **business completion records** ở DB, không chỉ tin count trên QueueChannel.
7. Xác minh backlog còn lại đúng trạng thái đã xử lý và không có eventId bị bỏ sót.

**Expected:** Message pending đã commit trong store sống qua restart. **Chưa chứng minh:** message đang xử lý sau dequeue cũng an toàn trong mọi topology.

### Test P2 — Rollback sau dequeue nhưng trước business commit

1. Đưa EV-4 vào JDBC queue.
2. Start polling consumer với transaction bao **receive + handler đồng bộ**.
3. Đặt fault checkpoint ở handler, sau receive nhưng trước business DB commit.
4. Cho handler throw/rollback và xác minh message vẫn có thể được poll lại.
5. Tắt fault; lần sau handler commit thành công.
6. Đối chiếu **hai handler attempts nhưng một business result**.

**Expected:** Rollback của cùng transactional resource khiến dequeue không được commit vĩnh viễn. Không áp dụng test này cho một ExecutorChannel đã tách transaction trước handler.

### Test P3 — Crash sau side effect nhưng trước source ACK

1. Chọn một **stable operationId** (ví dụ PAYMENT-42) và source có redelivery được cấu hình đúng.
2. Cho handler commit một business update hoặc provider nhận idempotency request.
3. Dùng fault hook ngay sau commit/side effect nhưng **trước ACK**, sau đó kill process.
4. Start Process B; kiểm tra broker có thể redeliver cùng business eventId.
5. Xác minh unique inbox/idempotency state hoặc provider idempotency key làm **business effect chỉ xảy ra một lần**.
6. Nếu provider response bị mất, trạng thái là **UNKNOWN_OUTCOME**; dùng query/reconciliation trước khi gửi operation mới.

**Expected:** Hệ thống chịu được at-least-once delivery mà không tạo double side effect. **Không được giả định** mọi transport hỗ trợ một checkpoint ACK giống nhau.

### Test P4 — Executor RAM chứa task chưa chạy khi process bị kill

1. Tạo executor một worker và queue có dung lượng xác định.
2. Chặn worker thứ nhất bằng CountDownLatch; enqueue EV-5 vào executor queue.
3. Xác nhận nguồn đã ACK hay chưa, và EV-5 còn ở durable store không.
4. Kill Process A khi EV-5 chưa bắt đầu handler.
5. Start Process B với nguồn/store cũ, xác minh EV-5 có đường replay.

**Nếu EV-5 chỉ tồn tại trong executor RAM và source đã ACK**, test có thể phơi bày mất việc. Đây là kết quả giúp phát hiện lỗi kiến trúc; không được sửa test bằng cách bỏ assertion về EV-5.

### Tại sao không chỉ dùng @DirtiesContext hoặc context.close()?

Đóng ApplicationContext sạch sẽ thường gọi lifecycle callbacks; một task đang chạy có thể được cho thêm thời gian hoàn tất. **SIGKILL, OOM, node failure hoặc Kubernetes grace period hết** không bảo đảm chạy cleanup, transaction synchronization callback hay @PreDestroy. Muốn chứng minh durability, **phải có ít nhất một test bất ngờ mất process** với store bên ngoài còn nguyên.

## 16. Shutdown budget: ba đồng hồ không tự cộng lại thành một

Trong ứng dụng Spring Boot trên Kubernetes có thể đồng thời tồn tại:

| Thời hạn | Cấu hình hoặc chủ thể | Giới hạn |
| --- | --- | --- |
| **Spring Boot lifecycle phase** | spring.lifecycle.timeout-per-shutdown-phase | Thời gian chờ **mỗi phase** của SmartLifecycle |
| **Spring Integration orderly shutdown** | stopActiveComponents(howLong) | Khoảng thời gian theo thao tác orderly shutdown, đơn vị **milliseconds** |
| **Kubernetes pod termination** | terminationGracePeriodSeconds | Tổng khoảng cho pod dừng trước force kill |
| **preStop hook** | Pod lifecycle hook | **Tiêu tốn cùng Kubernetes grace period** |
| **Broker lease/ack deadline** | Broker/adapter | Khi message được coi là eligible cho redelivery |
| **HTTP/DB timeout** | Client/transaction manager | Không bảo đảm remote side effect bị thu hồi |

Ví dụ trong application.yml:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s

server:
  shutdown: graceful
~~~

Và fragment trong PodSpec:

~~~yaml
terminationGracePeriodSeconds: 90
containers:
  - name: order-worker
    image: example.com/order-worker:lab
~~~

**Các cấu hình chỉ là ví dụ.** Spring Boot graceful web shutdown không tự stop/drain mọi broker/file adapter. Timeout-per-shutdown-phase không được cộng thêm ngoài Kubernetes grace, còn preStop làm giảm phần thời gian còn lại dành cho Spring.

### Bài toán ngân sách

~~~text
Kubernetes grace:                 90 giây
preStop/quiesce + propagation:    10 giây
drain mục tiêu:                  55 giây
resource close + metrics:        15 giây
safety margin:                   10 giây
~~~

Đây là một ngân sách **tuần tự minh họa**. Một số giai đoạn có thể overlap; cần đo thời gian thật trong rollout. Không đặt drain=90 giây khi grace=90 giây rồi tiếp tục preStop=10 giây; pod có thể bị kill trước khi drain/cleanup hoàn tất.

### Kịch bản Kubernetes test

1. Triển khai hai replica với external broker + persistent DB.
2. Gửi backlog lớn hơn khả năng xử lý ngay trong 10 giây.
3. Kích hoạt rollout/scale down thật để pod cũ nhận termination.
4. Quan sát endpoint lifecycle, inbound rate, queued, executor tasks, handler in-flight, source unacked và pod termination timestamp.
5. Xác minh pod cũ **ngừng ingress** nhưng tiếp tục drain hoặc để lại durable pending.
6. Cho replica còn lại/replica mới tiếp tục; so sánh **event IDs đã nhận với business completion**.
7. Chạy hai biến thể: drain kịp grace và drain không kịp grace.

**Readiness=false không tự dừng Kafka/JMS/AMQP consumer.** Nó chủ yếu ảnh hưởng routing traffic được quản lý qua readiness; cần stop source adapters riêng. Tương tự, một shell entrypoint không forward SIGTERM có thể ngăn JVM thực hiện lifecycle shutdown.

## 17. Retry, errorChannel và transaction trong thời gian drain

Một message không thể xử lý ngay có thể đang:

- Retry trong handler với backoff.
- Chờ HTTP request có timeout dài.
- Chờ DB lock hoặc connection pool.
- Đang được gửi tới errorChannel.
- Được lưu vào DLQ/quarantine/outbox cho xử lý sau.

**Hết shutdown deadline không đồng nghĩa handler được phép nuốt exception rồi báo success.** Nếu một message chưa có kết quả nghiệp vụ cuối, phải có durable recovery hoặc source redelivery theo contract.

### Ví dụ error flow: không count mọi retry như một business failure

~~~text
EV-42 delivery #1
  handler attempt #1 → timeout
  handler attempt #2 → timeout
  handler attempt #3 → success

Output business completion = 1
Handler attempts = 3
ErrorMessage count: tùy advice/error flow được cấu hình
~~~

Không được mặc định sẽ có một ErrorMessage cho **mỗi attempt thất bại**; nhiều RetryAdvice chỉ publish lỗi cuối cùng sau khi retry cạn. Cần dùng handler spy/metrics để đếm attempts và error flow để kiểm chứng recovery cuối.

### Test poison message

1. Enqueue EV-BAD với payload không hợp lệ.
2. Cho handler ném **non-retryable validation exception**.
3. Xác nhận retry policy **không thử vô hạn**.
4. Xác minh message được đưa vào quarantine/DLQ **bền vững** theo hợp đồng.
5. Tiếp tục drain EV-GOOD sau EV-BAD; không để một message lỗi giữ toàn bộ queue tới khi hết deadline.

**Không dùng queue.clear() để khiến biểu đồ queueDepth về 0.** Điều đó xóa cơ hội phục hồi của những message chưa được xử lý.

## 18. Observability cho graceful shutdown: ghi bằng chứng, không đoán

Một shutdown test có tính thuyết phục nên phát cả **logs, metrics và trạng thái của source/store**. Nếu chỉ có một log “shutdown finished”, không biết thực sự đã drain hay chưa.

### Bảng metric/diagnostic tối thiểu

| Tín hiệu | Phải trả lời được | Cạm bẫy |
| --- | --- | --- |
| **ingress.accepting** | Endpoint/caller còn tạo message mới? | Một replica stopped không đại diện toàn cluster |
| **queue.depth** | Bao nhiêu message chưa dequeue? | Không tính handler/executor in-flight |
| **queue.oldest.age** | Message nào đang chờ quá lâu? | Đo bằng thời gian liên JVM cần clock sync |
| **poller.running** | Consumer còn chạy để drain không? | isRunning=false không có nghĩa không còn in-flight |
| **handler.active** | Bao nhiêu handler đang chạy? | Đếm trong method có thể chưa gồm DB commit |
| **executor.queued/active** | Có task đã được handoff nhưng chưa xử lý? | Executor queue RAM có thể mất khi crash |
| **source.unacked** | Có message có thể redeliver? | Phụ thuộc adapter/broker metadata |
| **transaction.committed/rolledBack** | Durable effect đã commit hay rollback? | Counter trong RAM không phải nguồn kiểm toán |
| **retry.pending / dlq.pending** | Có công việc đang chờ recovery? | Retry vô hạn có thể ngăn drain |
| **outbox.pending** | Event đã commit nhưng chưa publish? | Publish thành công trước mark-sent có thể lặp |
| **shutdown.result** | DRAINED / DURABLE_PENDING / RISK? | Không biến mọi timeout thành success |
| **budget.remaining** | Còn bao nhiêu thời gian cho cleanup? | Không chỉ tính timeout Spring Boot |

### Ví dụ log khi EV-1 bị chặn trong test

~~~text
event=shutdown_observation
instance=order-lab-1
phase=DRAINING
ingressAccepting=false
queued=2
handlerInFlight=1
executorQueued=0
allCompleted=false
result=IN_PROGRESS
~~~

Nếu 150 ms đã hết mà chưa thả latch:

~~~text
event=shutdown_decision
phase=DRAINING
queued=2
handlerInFlight=1
deadlineReached=true
result=TIMED_OUT_WITH_PENDING
~~~

Nếu đó là QueueChannel in-memory và nguồn đã ACK, phải tăng mức cảnh báo lên **DATA_LOSS_RISK**; bản thân lab không có broker nên **không được suy ra** nguồn sẽ replay.

### Sau khi thả worker

~~~text
event=shutdown_decision
phase=DRAINED
queued=0
handlerInFlight=0
completedEvents=3
result=DRAINED_IN_LAB_SCOPE
~~~

Các field trên là **format do ứng dụng tự thiết kế**, không phải metric/log mà Spring Integration luôn phát tự động. Không đưa payload, token hoặc thông tin khách hàng vào logs. Event IDs/correlation IDs dùng cho trace/log có kiểm soát; **không dùng mỗi eventId làm metric tag** vì cardinality cao.

### Dùng Micrometer ở đúng ranh giới

- **Timer** cho send/dispatch latency, queue wait, handler execution, shutdown elapsed.
- **Counter** cho handler attempts, errors, retry, duplicate suppressed, DLQ published, shutdown outcomes.
- **DistributionSummary** cho batch size hoặc serialized payload bytes.
- **Gauge** cho queue depth, executor queued/active, in-flight và pending groups.

Không đếm handler attempts là số **business operations duy nhất**. Một event có thể xử lý nhiều lần do retry và redelivery. Khi tạo SLO, dùng durable business state hoặc một completion event có định nghĩa rõ.

## 19. Ma trận kiểm thử để tránh “happy path only”

| Mã | Kịch bản | Công cụ | Assertion quyết định |
| --- | --- | --- | --- |
| **G01** | Queue có ba message, consumer chưa start | QueueChannel + @SpringIntegrationTest | Queue vẫn có 3; completed=0 |
| **G02** | Pause ingress trước khi drain | IngressGate | EV-4 bị từ chối; backlog không tăng do gate |
| **G03** | Một handler in-flight, hai message queued | CountDownLatch | queued=2, inFlight=1, completed=0 |
| **G04** | Thả handler rồi drain đủ ba message | CountDownLatch + polling endpoint | completed IDs đúng, queue=0, inFlight=0 |
| **G05** | Deadline hết khi EV-1 chưa được thả | Timed await | Không được báo DRAINED |
| **G06** | Stop consumer khi không có công việc in-flight | Lifecycle | isRunning=false; không poll thêm theo contract |
| **G07** | Stop một inbound adapter thật | Lifecycle/broker/file test | Không nhận mới tại đúng endpoint/instance |
| **G08** | Handler ném lỗi và transaction rollback | JDBC store + transaction | Message có thể retry, không mất durable work |
| **G09** | Handler ném lỗi rồi recovery sang DLQ | Error flow + durable DLQ | DLQ đã commit, không log success giả |
| **G10** | Persistent queue còn message khi process A chết | PostgreSQL + Process B | B đọc được đúng events đã commit |
| **G11** | Dequeue commit rồi task executor còn RAM | Executor + fault hook | Phát hiện nguy cơ mất việc/handoff gap |
| **G12** | Crash sau DB commit trước broker ACK | Broker + DB | Redelivery có thể xảy ra, effect chỉ một lần |
| **G13** | HTTP timeout sau external side effect | Fake provider với status lookup | Reconciliation, không double operation |
| **G14** | Rollout có preStop và grace ngắn | Kubernetes test | Không nói đã drain khi pod bị kill sớm |
| **G15** | Hai replicas cùng một source/store | Multi-instance test | Ownership, ack, per-instance state rõ |
| **G16** | Backlog còn nhưng shutdown bắt buộc kết thúc | Persistent store + restart | Durable pending được worker mới xử lý |
| **G17** | Correlation group thiếu một phần lúc shutdown | MessageGroupStore | Group incomplete giữ/expire theo policy |
| **G18** | Executor task bị reject khi shutdown/overload | Bounded executor | Lỗi handoff quan sát được, không ACK thành công giả |

**G01–G06** là các test logic/lifecycle nội JVM; **G07–G18** cần fixture adapter, DB, broker hoặc orchestrator tương ứng. Không đánh dấu các bài kiểm thử sau là PASS chỉ vì ba JUnit method của lab in-memory đã PASS.

## 20. Debug khi test graceful shutdown thất bại

### Trường hợp 1 — consumer tự chạy trước khi test enqueue

**Dấu hiệu:** Queue depth không bằng 3 dù test vừa gửi ba message.

**Nguyên nhân thường gặp:** Endpoint autoStartup đã chạy, một consumer khác đang poll, hoặc fixture bị dùng chung giữa các test. Kiểm tra **@SpringIntegrationTest(noAutoStartup)** có khớp ID endpoint thật không; verify không có subscriber/poller khác.

### Trường hợp 2 — firstStarted không được countDown

**Dấu hiệu:** Test timeout khi chờ handler bắt đầu.

Kiểm tra:

1. Endpoint **workConsumer** có start và isRunning đúng không?
2. Channel bean **pendingQueue** có được flow processingFlow đọc không?
3. Poller trigger/fixedDelay có hoạt động và TaskScheduler có thread rảnh không?
4. Handler có được đăng ký làm đúng MessageHandler không?
5. Có exception trước khi handler vào block đầu tiên, hoặc message bị flow khác consume không?

**Không chữa bằng sleep lâu hơn trước khi xác minh topology**.

### Trường hợp 3 — sau releaseFirst vẫn không đủ ba completed

**Dấu hiệu:** allCompleted.await trả false.

Xem errorChannel/log handler, transaction rollback, poller state, eventId và exception. Có thể test đã để consumer bị stop sớm, hoặc handler throw. Nếu đầu ra là QueueChannel khác, nhớ rằng **receive() sẽ tiêu thụ message**, đừng vô tình dùng một test observer làm business consumer.

### Trường hợp 4 — Queue depth về 0 nhưng outcome cuối sai

Một message có thể đã được dequeue nhưng còn chờ trong executor queue hoặc đang gọi external HTTP. Kiểm tra **in-flight, executor queued, transaction commit, source ack, provider status** thay vì sửa công thức queue depth.

### Trường hợp 5 — test restart mất message dù dùng JdbcChannelMessageStore

Kiểm tra:

- Có dùng đúng **DataSource/schema/table prefix/region/groupId** ở cả hai process?
- Enqueue đã commit trước khi process A chết chưa?
- Payload/headers có serialize/deserialize được qua phiên bản application mới?
- Poller B có đang chạy, có DB lock hoặc consumer khác đang sở hữu message không?
- Process A có dequeue và commit mất message trước khi kill không?
- Nếu handler đã tạo side effect nhưng chưa checkpoint, có replay/reconciliation chưa?

**Không xóa bảng message store để “dọn lỗi”** nếu đó là dữ liệu chưa xử lý.

### Trường hợp 6 — Kubernetes kill pod trước khi cleanup

Kubernetes tính preStop trong cùng termination grace. Nếu JVM được khởi chạy qua shell không forward SIGTERM, Spring có thể không nhận tín hiệu. Kiểm tra signal forwarding, deadline, preStop, lifecycle phase và trạng thái pod termination; **SIGKILL không chạy @PreDestroy hay shutdown hook**.

### Trường hợp 7 — hiện duplicate sau restart

At-least-once redelivery có thể là hành vi hợp lệ nếu ACK chưa hoàn tất. Kiểm tra **stable eventId/operationId, inbox unique constraint, outbox publish state và provider idempotency**. Không sửa bằng cách ack sớm trước durable commit, vì có thể đổi lỗi trùng thành **mất dữ liệu**.

## 21. Runbook một lần graceful shutdown có message đang chờ

Áp dụng cho dịch vụ có **inbound source → durable queue → polling consumer → DB/outbound**. Phải điều chỉnh với từng adapter và transaction model; đây là **thủ tục ứng dụng vận hành**, không phải API tự động của mọi IntegrationFlow.

### Pha 0 — Ghi baseline

Trước khi gửi shutdown command, ghi:

~~~text
operationId=rollout-42
instance=order-worker-b
flow=order-import
ingressAccepting=true
queued=500
inFlight=8
executorQueued=12
sourceUnacked=3
retryPending=4
outboxPending=7
unknownExternalEffects=0
deadline=...
~~~

Kiểm tra **nguồn replay nếu process chết**: broker còn retention/unacked, JDBC queue có transaction/serializer đúng, inbox/outbox đã được thử nghiệm qua restart. Nếu chỉ có QueueChannel RAM và nguồn đã ack, hãy ghi **DATA_LOSS_RISK** thay vì tự động tiếp tục rollout nguy hiểm.

### Pha 1 — Quiesce ingress

1. Ngừng nhận message mới tại **đúng inbound endpoint/consumer/container**.
2. Với HTTP service, giảm readiness hoặc ngừng chấp nhận request mới theo chính sách drain của gateway/load balancer.
3. Với broker/file adapter, stop lifecycle riêng; readiness của web server **không** tự stop Kafka/JMS/AMQP consumer.
4. Với nhiều replica, theo dõi **từng replica** và instance mới gia nhập trong lúc rollout.
5. Xác nhận ingress mới thực sự giảm hoặc dừng; ghi thời điểm barrier được thiết lập.

**Không stop consumer xử lý queue ở pha này.**

### Pha 2 — Drain với budget hữu hạn

Giữ polling consumer, executor, DB connection pool và external client còn hoạt động. Quan sát định kỳ nhưng **không đọc/receive message chỉ để đo queue depth**.

~~~text
remainingWork :=
    queued
    + executorQueued
    + handlerInFlight
    + claimedButNotCommitted
    + sourceUnacked
    + unresolvedExternalOutcomes
~~~

Đây là **mô hình khái niệm**, không phải phép cộng luôn chính xác trong mọi topology: một message có thể được ghi nhận ở nhiều metric cùng lúc. Mục đích là **không bỏ sót một nơi sở hữu công việc**, không dùng tổng này làm số business operations.

Nếu handler fail:

- Lỗi transient: retry hữu hạn với backoff, trong budget hoặc durable retry queue.
- Lỗi permanent: quarantine/DLQ được commit theo hợp đồng.
- External outcome chưa biết: lưu UNKNOWN và đối soát theo operationId.
- Không bắt exception rồi return success nếu nghiệp vụ chưa hoàn tất.

### Pha 3 — Quyết định tại deadline

| Bằng chứng | Kết quả vận hành |
| --- | --- |
| Ingress đã quiesced, không còn queued/claimed/in-flight/unacked, commit/ack xác nhận | **DRAINED** |
| Còn queue đã commit trong durable store, worker mới có thể đọc | **DURABLE_PENDING** |
| Còn broker delivery unacked và chắc chắn có redelivery theo adapter policy | **REPLAYABLE_PENDING** |
| Provider request đã gửi nhưng response không rõ | **RECONCILIATION_REQUIRED** |
| Có task chỉ trong RAM và source đã ACK | **DATA_LOSS_RISK** |
| Không chắc ingress còn nhận hay không, hoặc thiếu metrics quan trọng | **INCOMPLETE_EVIDENCE**; không công bố thành công |

### Pha 4 — Stop downstream và đóng resource

Khi phần bắt buộc đã hoàn tất hoặc được chuyển giao bền vững, dừng consumer/poller, executor và kết nối theo thứ tự phù hợp. Dành một **safety margin** cho transaction cleanup và process exit; không dùng toàn bộ Kubernetes grace để chờ retry.

### Pha 5 — Xác minh sau restart

1. Worker mới kết nối đúng broker/store/region/groupId.
2. Durable backlog/pending outbox được đọc lại và giảm theo processing rate.
3. Cùng eventId redeliver không tạo thêm side effect nghiệp vụ.
4. UNKNOWN_OUTCOME được reconciliation thay vì replay tùy tiện.
5. Không có orphan MessageGroup hoặc retry record quá SLA.
6. Desired state của flow được khôi phục; không bật ingress khi cluster còn đang maintenance.

### Kết quả bàn giao cho đội vận hành

~~~text
shutdownId=rollout-42
service=order-worker
oldInstance=order-worker-b
finalOutcome=TIMED_OUT_WITH_DURABLE_PENDING
queuedInJdbcStore=19
handlerInFlight=0
sourceUnacked=0
externalUnknown=1
newWorkerCanRecover=true
followUp=RECONCILE_EXTERNAL_OPERATION
~~~

Đây là một kết quả **hợp lệ có điều kiện** nếu 19 message đã commit trong store và worker mới thực sự tiếp tục được. Nó không phải **DRAINED**.

## 22. Bài tập mở rộng cho người học

### Bài A — Thay gate giả bằng inbound endpoint thật

Thay **IngressGate** bằng một inbound polling adapter có **ID lifecycle tường minh** và một MessageSource mock có thể điều khiển. Dùng **@SpringIntegrationTest(noAutoStartup = {...})** và **MockIntegrationContext** nếu phù hợp, tạo message rồi stop nguồn bằng Lifecycle hoặc control message.

**Đạt yêu cầu khi:** Sau stop không có lượt nhận mới theo hợp đồng endpoint; polling consumer đọc backlog vẫn chạy; sau start nguồn tiếp tục nhận message. Không dựa vào một Thread.sleep cố định.

### Bài B — Chuyển QueueChannel sang JDBC

Dùng cùng message store qua **hai application contexts** hoặc hai process. Gửi ba message khi consumer chưa chạy, đóng context A rồi tạo context B dùng cùng DB/groupId.

**Đạt yêu cầu khi:** Context B nhận đủ message đã commit, không mất ID và không để lại bản ghi chưa xử lý bất thường. Sau đó lặp lại bằng **kill process** để phân biệt graceful context close với crash recovery.

### Bài C — Thêm một ExecutorChannel trước handler

Chèn ExecutorChannel có pool một worker và queue hữu hạn sau consumer. Chặn worker bằng latch, theo dõi **QueueChannel depth** và **executor queued**.

**Đạt yêu cầu khi:** Test chứng minh queued trong QueueChannel có thể về 0 trong khi executor vẫn còn task, và ghi lại lỗ hổng khi dequeue đã commit nhưng task chỉ trong RAM.

### Bài D — Thêm transaction rollback và retry

Dùng JDBC queue transactional và handler fail lần đầu, success lần sau. Quan sát handler attempts, business DB commits, error flow và final queue state.

**Đạt yêu cầu khi:** Một event có thể được retry nhưng chỉ tạo **một business completion**. Nếu handler có external side effect, dùng idempotency key hoặc fake provider có khả năng đối soát.

### Bài E — Kiểm thử nhiều replica

Chạy hai worker với một shared durable source/queue phù hợp. Yêu cầu một instance drain/stop trong khi instance khác tiếp tục. Kiểm tra **ownership và idempotency** trên business store, không chỉ số log.

**Đạt yêu cầu khi:** Không bỏ sót event đã được accepted và không double business effect, kể cả khi một instance crash sau commit trước acknowledgement.

## 23. Câu hỏi tự kiểm tra và đáp án

**1. QueueChannel.getQueueSize() trả 0 thì graceful shutdown đã hoàn tất?**

**Chưa chắc.** Message có thể đã dequeue nhưng vẫn nằm trong handler, executor task queue hoặc transaction. Cần kiểm tra in-flight, nguồn unacked và durable business outcome.

**2. Stop polling consumer khi queue còn 500 message có khiến 500 message tự được xử lý không?**

**Không.** Consumer bị stop sẽ không tiếp tục poll theo hợp đồng, backlog có thể đứng yên. Nếu muốn drain, dừng ingress trước và giữ consumer chạy tới khi đạt tiêu chí hoặc hết budget.

**3. Handler đang chờ latch, test dùng await(timeout) trả false. Có phải test bị lỗi?**

**Không nhất thiết.** Đó là kết quả mong đợi khi mô phỏng deadline hết lúc còn in-flight. Bài test phải assert đúng trạng thái timeout và thả latch trong cleanup.

**4. Đổi QueueChannel in-memory sang JDBC có bảo đảm mọi message an toàn sau SIGKILL?**

**Không hoàn toàn.** Message đã commit trong store có thể sống qua restart; message đã dequeue và chỉ còn trong executor RAM có thể mất. Cần kiểm tra transaction/handoff và source ACK.

**5. Một broker redeliver event sau crash là framework bị lỗi?**

**Không tự động.** At-least-once redelivery có thể đúng protocol khi ACK chưa thành công. Nghiệp vụ phải idempotent; không được tạo double side effect.

**6. Hết Kubernetes grace có bảo đảm Spring chạy @PreDestroy xong?**

**Không.** Khi hết thời hạn, process có thể bị force kill. preStop dùng chung grace period; thiết kế phải phục hồi từ durable state mà không phụ thuộc callback cleanup.

**7. Vì sao không dùng @DirtiesContext thay cho crash test?**

Vì **context close** có thể chạy lifecycle cleanup, trong khi kill process bất ngờ không đảm bảo làm vậy. Chỉ test hai process/container độc lập với store giữ nguyên mới kiểm chứng đúng ranh giới restart/durability.

**8. HTTP payment đã xử lý nhưng worker mất response trong lúc shutdown. Có nên tạo payment operation mới?**

**Không.** Ghi UNKNOWN_OUTCOME, tra cứu bằng stable operationId/idempotency key và đối soát. Request timeout không chứng minh remote chưa thực hiện side effect.

## 24. Checklist trước khi đánh dấu lab hoàn thành

- Đã đọc đúng chủ đề **kiểm thử graceful shutdown với message đang chờ**, không chỉ test lifecycle stop()?
- Test tạo được message queued và một message in-flight bằng **CountDownLatch**, không dựa vào sleep may rủi?
- Ingress gate hoặc inbound endpoint được pause **trước khi** consumer bắt đầu drain?
- Test xác minh source không nhận thêm công việc mới trong phạm vi được kiểm soát?
- Test chứng minh queue **không tự drain** khi consumer bị stop?
- Test thấy **queued=2, inFlight=1**, rồi hoàn tất đúng ba business events khi thả latch?
- Test **timeout path** trả trạng thái pending, không gọi nhầm DRAINED?
- Có cleanup trong finally/@AfterEach để tránh thread/test context bị kẹt?
- Test đã cách ly context hoặc reset QueueChannel/latch an toàn giữa các cases?
- Đã phân biệt **in-memory QueueChannel, JDBC-backed QueueChannel và executor queue RAM**?
- Nếu dùng JDBC, có test restart với cùng DataSource/schema/region/groupId và dữ liệu đã commit?
- Poller transaction bao dequeue/handler đồng bộ khi yêu cầu rollback hợp lệ?
- Nếu có ExecutorChannel sau dequeue, đã kiểm tra durable handoff gap?
- Có biết chính xác **điểm ACK/offset commit** của broker adapter so với durable write?
- Có test crash **sau side effect trước ACK**, cùng eventId không double business effect?
- Có xử lý **UNKNOWN_OUTCOME, retry budget, DLQ và pending outbox**?
- Có tách Spring lifecycle timeout, Orderly Shutdown timeout và Kubernetes termination grace?
- Có test rollout thực khi **không đủ thời gian drain**?
- Observability có queue depth, in-flight, executor queued, unacked, pending durable và outcome rõ ràng?
- Không xóa MessageStore hoặc queue chỉ để làm trạng thái shutdown trông “xanh”?
- Có bằng chứng business DB/source/store thực sự nhất quán sau restart?

## Kết luận

Kiểm thử **graceful shutdown với message đang chờ** không phải chỉ gọi stop() rồi kiểm tra isRunning=false. Bài thực hành cho thấy cách tạo **backlog và in-flight một cách xác định** bằng QueueChannel, polling consumer và CountDownLatch; sau đó kiểm chứng **pause ingress → drain queue → hoàn tất handler → stop consumer**. Nó cũng tạo được **deadline hết khi vẫn còn message** mà không khiến test treo hoặc báo thành công giả.

Với hệ thống Spring Integration Runtime thực tế, tiêu chí an toàn còn bao gồm **transaction, broker ACK, persistent MessageStore, executor queued tasks, retry/recovery, correlation và external side effects**. Một queue persistent không bảo vệ task đã bị dequeue sang executor RAM; một HTTP timeout không chứng minh side effect chưa xảy ra; một broker redelivery không đồng nghĩa lỗi nếu handler idempotent.

Vì vậy, kết quả vận hành đúng phải trả lời được: **Còn việc gì? Nó nằm ở đâu? Có durable không? Ai sẽ xử lý sau restart? Có thể thực thi trùng tác dụng nghiệp vụ không?** Chỉ khi các câu hỏi này có bằng chứng qua **test in-JVM, fault injection và crash/restart với store thật**, hệ thống mới có graceful shutdown đủ tin cậy để triển khai.

## Tài liệu tham khảo

- [Spring Integration Reference — Orderly Shutdown](https://docs.spring.io/spring-integration/reference/shutdown.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html)
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Framework — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
