# Chờ điều kiện bất đồng bộ, cô lập destination và dọn dữ liệu kiểm thử

> **Chương:** Kiểm thử  
> **Phạm vi:** Integration test Java/JMS với ActiveMQ Classic và Apache Artemis, sử dụng JDK 17, JUnit 5 và Jakarta Messaging. Bài tập trung vào ba việc thường làm test broker chập chờn: chờ điều kiện có deadline, cô lập queue/topic theo từng test và dọn đúng tài nguyên sau khi test kết thúc.

## 1. Ba nguyên nhân khiến test JMS chập chờn

Một test gửi message rồi lập tức đọc database có thể thất bại dù hệ thống hoạt động đúng: producer chỉ vừa gửi, listener chưa được scheduler gọi, consumer còn đang ghi DB hoặc transaction chưa commit. Thêm một khoảng chờ cố định chỉ che race trong một số lần chạy; CI chậm hơn hoặc broker tải cao vẫn có thể làm test lỗi.

Test ổn định phải xác định **điều kiện cần chờ**, **thời hạn tối đa**, **event ID**, và **destination mà test sở hữu**.

```text
Test thread                  JMS broker / listener              Business store
    |                                  |                              |
    | provision unique queue           |                              |
    |--------------------------------->|                              |
    | register consumer/listener       |                              |
    |--------------------------------->|                              |
    | publish eventId=it-123            |                              |
    |--------------------------------->| dispatch                      |
    |                                  |----------------------------->|
    |                                  |                        persist result
    |                                  |<-----------------------------|
    | await(condition, deadline)       |                              |
    |<----------- result/timeout -------|                              |
    | assert eventId + state           |                              |
    | close consumer, delete own queue |                              |
```

| Điều cần chờ | Cách phù hợp | Không nên |
|---|---|---|
| Consumer nhận message | CompletableFuture hoặc CountDownLatch hoàn tất từ listener, có timeout | Chờ cố định rồi giả định listener đã chạy |
| Message xuất hiện trên queue | JMS receive(timeout) | Poll vô hạn hoặc đọc queue dùng chung |
| Side effect cuối cùng đã commit | Awaitility chờ trạng thái nghiệp vụ theo event ID | Chỉ assert send đã trả về |

send trả về phản ánh hợp đồng gửi và confirmation của provider; nó không chứng minh listener đã chạy hay DB đã commit. receive trả về cũng không chứng minh business side effect phía sau đã hoàn tất.

## 2. Chờ điều kiện bất đồng bộ bằng deadline

### 2.1. Dùng CompletableFuture cho callback JMS

Khi test cần xác minh broker dispatch message tới consumer, đăng ký listener **trước khi publish** và chuyển kết quả callback thành CompletableFuture. Test thread chờ future với deadline; callback chỉ trích xuất dữ liệu bất biến rồi hoàn tất future.

Dependency Awaitility cho test:

```xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <version>4.2.2</version>
    <scope>test</scope>
</dependency>
```

Trong Spring Boot project, JUnit Jupiter thường đã được quản lý bởi spring-boot-starter-test theo BOM; chỉ thêm Awaitility nếu chưa có.

Listener dùng một JMSContext riêng:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

record ReceivedEvent(String eventId, String body) {}

final class AsyncQueueListener implements AutoCloseable {
    private final JMSContext context;
    private final JMSConsumer consumer;
    private final CompletableFuture<ReceivedEvent> received =
        new CompletableFuture<>();

    AsyncQueueListener(ConnectionFactory factory, String user,
                       String password, String queueName) {
        context = factory.createContext(user, password);
        consumer = context.createConsumer(context.createQueue(queueName));
        consumer.setMessageListener(this::onMessage);
        context.start();
    }

    private void onMessage(Message message) {
        try {
            if (!(message instanceof TextMessage text)) {
                throw new IllegalStateException("Expected TextMessage");
            }
            received.complete(new ReceivedEvent(
                text.getStringProperty("eventId"), text.getText()));
        } catch (JMSException | RuntimeException failure) {
            received.completeExceptionally(failure);
        }
    }

    ReceivedEvent await(Duration timeout) throws Exception {
        return received.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    @Override
    public void close() {
        try {
            consumer.close();
        } finally {
            context.close();
        }
    }
}
```

Callback không chia sẻ JMSContext với test thread và không gọi thêm thao tác JMS; nó chỉ đọc message rồi hoàn tất future. Context mặc định dùng AUTO_ACKNOWLEDGE, nên message có thể được acknowledge khi callback kết thúc. Ví dụ này xác minh **dispatch trên queue lab riêng**, không chứng minh transaction nghiệp vụ.

Producer test:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

final class TestPublisher {
    static void publish(ConnectionFactory factory, String user, String password,
                        String queueName, String eventId, String body) {
        try (JMSContext context = factory.createContext(user, password)) {
            Queue queue = context.createQueue(queueName);
            TextMessage message = context.createTextMessage(body);
            message.setStringProperty("eventId", eventId);
            context.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .send(queue, message);
        }
    }
}
```

Một test dùng hai helper trên:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import jakarta.jms.ConnectionFactory;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AsyncJmsIntegrationTest {
    private final ConnectionFactory factory = TestBroker.connectionFactory();
    private final QueueAdmin admin = TestBroker.queueAdmin();
    private final String user = TestBroker.user();
    private final String password = TestBroker.password();

    @Test
    void receivesTheEventPublishedToItsOwnQueue() throws Exception {
        String suffix = UUID.randomUUID().toString().replace("-", "");
        String queue = "it.orders." + suffix;
        String eventId = "event-" + suffix;
        admin.createQueue(queue);
        try (AsyncQueueListener listener =
                 new AsyncQueueListener(factory, user, password, queue)) {
            TestPublisher.publish(factory, user, password,
                queue, eventId, "ORDER_CONFIRMED");
            ReceivedEvent actual = listener.await(Duration.ofSeconds(5));
            assertEquals(eventId, actual.eventId());
            assertEquals("ORDER_CONFIRMED", actual.body());
        } finally {
            admin.deleteQueue(queue);
        }
    }
}
```

TestBroker là fixture do dự án kiểm thử cung cấp, không phải class JMS có sẵn. QueueAdmin là adapter quản trị broker ở mục 5. Queue và event ID có UUID để test không nhận nhầm message cũ hoặc message của test song song. Listener đóng trước khi queue bị xóa.

### 2.2. Dùng receive(timeout) khi cần polling đồng bộ

```java
try (JMSContext context = factory.createContext(user, password);
     JMSConsumer consumer =
         context.createConsumer(context.createQueue(queueName))) {
    context.start();
    Message message = consumer.receive(Duration.ofSeconds(5).toMillis());
    assertNotNull(message, "No message before deadline");
}
```

Timeout tính bằng **mili giây**. Khi hết thời gian mà không có message, receive trả null; test cần báo lỗi kèm queue/event ID. Không lặp receive(100) vô hạn vì test có thể treo và che lỗi consumer không chạy.

### 2.3. Dùng Awaitility để chờ side effect ở DB

Khi listener nhận message rồi cập nhật database bất đồng bộ, assert trạng thái **được ghi bền vững** theo event ID:

```java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;

await()
    .alias("projection for event " + eventId)
    .pollInterval(Duration.ofMillis(100))
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertEquals("CONFIRMED",
            orderRepository.findStatusByEventId(eventId)));
```

Điều kiện phải gắn với dữ liệu của test, không phải một order bất kỳ đã tồn tại. Awaitility lặp assertion cho tới khi đạt hoặc quá hạn. 100 ms chỉ là polling interval ví dụ, không phải cam kết broker giao message trong 100 ms. Chọn deadline theo SLA test và thời gian khởi động CI; không kéo dài timeout vô hạn để che consumer bị treo.

### 2.4. Kiểm thử “không có message”

```java
Message unexpected = consumer.receive(500L);
assertNull(unexpected,
    "No message should arrive during the 500 ms observation window");
```

Kết quả chỉ chứng minh không nhận được message trong **500 ms đó**. Nó không chứng minh message sẽ không đến trong tương lai. Queue phải được cô lập và không có producer/test khác gửi vào.

## 3. Chờ broker sẵn sàng và tránh race lúc đăng ký consumer

### 3.1. Readiness không đồng nghĩa cổng TCP đã mở

Broker process có thể mở port trước khi hoàn tất recovery persistence, cấu hình security hoặc provisioning destination. Chờ điều kiện mà test thật sự cần:

- Có thể tạo JMS connection với credential test.
- Destination đã được provision.
- Consumer tạo được và start.
- Nếu test HA, backup đã đồng bộ theo điều kiện topology trước khi fault injection.

Ví dụ Awaitility kiểm tra consumer có thể đăng ký:

```java
import static org.awaitility.Awaitility.await;
import java.time.Duration;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;

static void awaitBrokerReady(ConnectionFactory factory,
                             String user, String password,
                             String healthQueue) {
    await()
        .alias("JMS broker accepts a consumer")
        .pollInterval(Duration.ofMillis(200))
        .atMost(Duration.ofSeconds(30))
        .until(() -> {
            try (JMSContext context = factory.createContext(user, password);
                 JMSConsumer consumer =
                     context.createConsumer(context.createQueue(healthQueue))) {
                context.start();
                return true;
            } catch (RuntimeException unavailable) {
                return false;
            }
        });
}
```

healthQueue phải được provision trước và chỉ dùng cho probe. Hàm này xác nhận khả năng mở consumer, **không** chứng minh persistence, mọi destination hoặc business flow đã sẵn sàng. Khi timeout, log exception cuối cùng để chẩn đoán auth, DNS, port hoặc broker startup.

### 3.2. Đăng ký consumer trước khi publish

Với queue, persistent message có thể nằm lại chờ consumer; nhưng tạo consumer trước giúp test tránh phụ thuộc auto-create policy và xác nhận listener đã start. Với **Topic non-durable**, thứ tự càng quan trọng: publish trước khi subscriber tồn tại có thể khiến message bị bỏ qua đúng theo pub/sub semantics.

Trình tự ổn định:

1. Provision destination riêng và đợi broker xác nhận.
2. Tạo consumer/listener, đăng ký callback rồi gọi JMSContext.start().
3. Publish event với eventId riêng.
4. Chờ callback hoặc business state bằng deadline.
5. Đóng consumer/context rồi mới xóa destination.

Không dùng khoảng sleep sau khi tạo consumer để “đảm bảo đã sẵn sàng”. Nếu cần readiness rõ ràng, expose signal từ fixture sau khi consumer được tạo/start hoặc dùng health probe có kiểm soát.

## 4. Cô lập destination cho từng test

### 4.1. Vì sao một queue cố định gây nhiễm chéo?

Nếu mọi test cùng dùng orders.test, test timeout có thể để lại persistent message; test sau nhận message cũ và pass sai. Khi chạy song song, test A có thể nhận message test B. Purge trước test chỉ che triệu chứng và có thể xóa dữ liệu test khác đang dùng.

Ưu tiên **unique destination per test**:

```text
it.orders.<build-id>.<test-run-id>.<uuid>
it.inventory.<build-id>.<test-run-id>.<uuid>
```

Tên destination nên có prefix it./test., dùng ký tự đơn giản, không chứa PII, có run ID/UUID để tránh trùng giữa parallel test và CI retry. Prefix giúp truy vết, nhưng không tự chứng minh quyền sở hữu.

```java
String runId = UUID.randomUUID().toString().replace("-", "");
String queueName = "it.billing." + runId;
String eventId = "evt-" + runId;
```

### 4.2. Selector không thay thế queue riêng

```java
String selector = "testRunId = '" + runId + "'";
JMSConsumer consumer = context.createConsumer(queue, selector);
```

Selector chỉ giới hạn message consumer nhìn thấy. Message cũ không khớp selector vẫn nằm trong queue, chiếm memory/store hoặc được consumer khác nhận. Selector không tự cô lập queue và không phải cơ chế cleanup. Nếu buộc dùng queue chung, cần owner, selector duy nhất, không có consumer rộng và quy trình dọn dữ liệu được khóa đồng bộ; tốt hơn vẫn là queue riêng.

### 4.3. Topic cần cô lập subscription identity

- Non-durable subscriber chỉ nhận event trong thời gian subscription tồn tại.
- Durable subscriber phải có identity duy nhất cho test, thường gồm clientID và subscription name; tái sử dụng identity có thể làm test nhận backlog cũ.
- Shared durable subscription cho test song song cần subscription riêng cho từng test run nếu mục tiêu là cô lập. Dùng chung một subscription sẽ khiến các test cạnh tranh message.
- Đóng consumer rồi unsubscribe durable subscription do test sở hữu; không unsubscribe subscription dùng chung.

Ví dụ JMS 1.1-style:

```java
String suffix = UUID.randomUUID().toString().replace("-", "");
String clientId = "it-billing-" + suffix;
String subscription = "orders-" + suffix;

connection.setClientID(clientId); // trước khi tạo Session/consumer
MessageConsumer consumer =
    session.createDurableSubscriber(topic, subscription);
```

Với JMS 2.x có thể dùng JMSContext.createDurableConsumer(topic, subscription). Unsubscribe đúng subscription sau khi consumer đã đóng; không xóa subscription do môi trường dùng chung sở hữu.

### 4.4. Provision queue là trách nhiệm của fixture

context.createQueue("it.billing.x") tạo destination object/handle phía client; nó **không phải lệnh portable** bảo đảm physical queue đã được tạo trên mọi broker.

| Broker | Provision | Cleanup |
|---|---|---|
| ActiveMQ Classic | Management/JMX BrokerViewMBean.addQueue(name) hoặc provisioning được phép của broker | Sau khi consumer đóng, BrokerViewMBean.removeQueue(name) |
| Artemis | Management API tạo address/queue với routing type phù hợp; ANYCAST cho competing consumers | Management API destroyQueue(name) hoặc admin adapter |
| JMS TemporaryQueue | Session.createTemporaryQueue() hoặc JMSContext.createTemporaryQueue() | TemporaryQueue.delete() hoặc đóng connection sở hữu |

Trong Artemis, queue gắn với address và routing type; test competing consumers thường dùng **ANYCAST**. Không tạo multicast queue nếu test chỉ muốn một message được một worker nhận. Nếu bật auto-create destination, vẫn cần kiểm tra tài nguyên thực sự tồn tại và có chính sách auto-delete phù hợp; không dựa vào default khác nhau giữa phiên bản.

## 5. Cleanup đúng thứ tự và đúng quyền sở hữu

### 5.1. Vòng đời teardown

```text
Create unique queue/subscription
              |
              v
       Publish and await
              |
              v
      Stop listener/producer
              |
              v
   Close consumer + JMSContext
              |
              v
 Verify consumerCount/inFlight = 0
              |
              v
 Delete only test-owned destination
              |
              v
       Record cleanup result
```

Đóng consumer trước khi xóa queue để tránh race giữa callback đang chạy và management operation. Nếu listener thực hiện side effect bất đồng bộ, chờ side effect đạt trạng thái terminal trước khi đóng. Khi test fail do timeout, vẫn đóng resource trong finally/@AfterEach; không để connection mở và consumer giữ message.

### 5.2. Queue vĩnh viễn và TemporaryQueue

TemporaryQueue phù hợp cho request/reply hoặc reply-to riêng. Nó được connection tạo và sở hữu; delete() hoặc đóng connection sẽ dọn destination tạm theo provider. Tuy nhiên:

- Không dùng TemporaryQueue để kiểm tra persistent backlog qua broker restart.
- Không dùng nó thay queue durable của ứng dụng.
- Queue vĩnh viễn phải được xóa qua management/admin API hoặc lifecycle của test broker.

### 5.3. Adapter quản trị riêng cho fixture

```java
interface QueueAdmin {
    void createQueue(String queueName) throws Exception;
    void deleteQueue(String queueName) throws Exception;
    QueueState inspect(String queueName) throws Exception;
}

record QueueState(long messageCount,
                  long deliveringCount,
                  long consumerCount) {}
```

ClassicQueueAdmin có thể dùng BrokerView MBean để add/remove queue và QueueView MBean để đọc trạng thái. ArtemisQueueAdmin dùng management API để tạo/xóa queue và đọc QueueControl. Hai adapter dùng **credential quản trị của broker test**, không cấp credential đó cho code nghiệp vụ.

Pseudo-flow:

```java
String queue = uniqueQueueName();
queueAdmin.createQueue(queue);
try {
    runJmsAssertions(queue);
} finally {
    closeAllJmsResources();
    QueueState state = queueAdmin.inspect(queue);
    if (state.consumerCount() != 0 || state.deliveringCount() != 0) {
        throw new IllegalStateException("Queue still active: " + state);
    }
    queueAdmin.deleteQueue(queue);
}
```

Đây là cấu trúc teardown; closeAllJmsResources() phải đóng mọi resource do test mở. Nếu test đã ném exception và cleanup cũng lỗi, giữ exception gốc và đính cleanup exception bằng addSuppressed() để không che nguyên nhân ban đầu.

**Không dùng purge() thay deleteQueue().** Purge xóa message nhưng để destination tồn tại; delete queue xóa cả tài nguyên test sở hữu. Chỉ xóa queue riêng khi chắc chắn nó thuộc run hiện tại.

### 5.4. Classic và Artemis quản lý queue

Classic BrokerView MBean thường có ObjectName:

```text
org.apache.activemq:type=Broker,brokerName=<broker-name>
```

BrokerViewMBean.addQueue(String) và removeQueue(String) là operation quản trị; removeQueue xóa destination cùng dữ liệu trong queue. QueueViewMBean cung cấp QueueSize, InFlightCount, ConsumerCount để kiểm tra trước cleanup. Chỉ gọi trên broker lab sau khi consumer/producer đã đóng.

Artemis dùng management API/JMX. Fixture admin có thể gọi operation destroyQueue(queueName) trên ActiveMQServerControl sau khi xác minh queue thuộc prefix test. Khi tạo queue, dùng routing type ANYCAST cho competing consumers; không xóa address dùng chung nếu queue khác còn gắn trên đó. Tên MBean và overload management API có thể phụ thuộc phiên bản/deployment, vì vậy adapter cần được kiểm tra với đúng Artemis version.

## 6. JUnit 5 fixture: tạo, kiểm thử và dọn queue riêng

Ví dụ cấu trúc test dùng helper ở trên:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import jakarta.jms.ConnectionFactory;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderQueueIT {
    private final ConnectionFactory factory = TestBroker.connectionFactory();
    private final QueueAdmin admin = TestBroker.queueAdmin();
    private final String user = TestBroker.user();
    private final String password = TestBroker.password();

    @Test
    void waitsForExpectedEventAndDeletesOnlyItsQueue() throws Exception {
        String runId = UUID.randomUUID().toString().replace("-", "");
        String queue = "it.orders." + runId;
        String eventId = "evt-" + runId;
        admin.createQueue(queue);

        Exception primaryFailure = null;
        try (AsyncQueueListener listener =
                 new AsyncQueueListener(factory, user, password, queue)) {
            TestPublisher.publish(factory, user, password,
                queue, eventId, "ORDER_CONFIRMED");
            ReceivedEvent received = listener.await(Duration.ofSeconds(5));
            assertEquals(eventId, received.eventId());
            assertEquals("ORDER_CONFIRMED", received.body());
        } catch (Exception failure) {
            primaryFailure = failure;
            throw failure;
        } finally {
            try {
                QueueState state = admin.inspect(queue);
                if (state.consumerCount() != 0 ||
                        state.deliveringCount() != 0) {
                    throw new IllegalStateException(
                        "Destination still active: " + state);
                }
                admin.deleteQueue(queue);
            } catch (Exception cleanupFailure) {
                if (primaryFailure != null) {
                    primaryFailure.addSuppressed(cleanupFailure);
                } else {
                    throw cleanupFailure;
                }
            }
        }
    }
}
```

TestBroker, QueueAdmin, QueueState, AsyncQueueListener và TestPublisher là helper của project test. Ví dụ nhấn mạnh thứ tự sở hữu resource; adapter admin cần xác định rõ hành vi khi queue không tồn tại (delete idempotent hoặc báo lỗi đã phân loại).

Trong Spring Boot có thể đóng gói fixture bằng JUnit extension hoặc BeforeEach/AfterEach, nhưng vẫn giữ nguyên tắc: mỗi test có run ID riêng, consumer đóng trước delete, chỉ xóa destination do fixture tạo và cleanup failure không che lỗi test gốc.

## 7. Chờ business side effect và kiểm tra idempotency

Nhận được JMS message chưa đủ nếu mục tiêu integration test là xác minh service xử lý message. Chờ trạng thái **được ghi bền vững**:

```java
@Test
void listenerUpdatesProjectionEventually() {
    String eventId = publishOrderEventToUniqueQueue();

    await()
        .alias("projection for " + eventId)
        .pollInterval(Duration.ofMillis(100))
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            OrderProjection projection =
                repository.findByEventId(eventId).orElseThrow();
            assertEquals("CONFIRMED", projection.status());
            assertEquals(eventId, projection.lastEventId());
        });
}
```

Repository phải đọc từ transaction/connection có thể nhìn thấy commit của listener; đừng giữ DB snapshot cũ từ transaction test mở trước đó.

Nếu listener cập nhật DB rồi ACK message:

- JMS local transaction không tự commit DB.
- @Transactional mặc định có thể trỏ tới DB transaction manager chứ không phải JMS transaction manager.
- Nếu không dùng XA/JTA, DB commit thành công nhưng JMS ACK thất bại có thể khiến message redeliver.
- Test nên xác minh idempotency theo event ID: cùng event giao lại không tạo hai business records/side effects.

Không assert callback count bằng 1 như bảo đảm exactly-once. Assert số business record duy nhất và trạng thái cuối theo event ID.

## 8. Chạy song song và chống dữ liệu tồn từ lần trước

| Tài nguyên | Quy tắc khi chạy song song |
|---|---|
| Queue | Unique theo test method/run; không dùng queue cố định |
| Topic durable subscription | Unique clientID + subscription name |
| Event | eventId duy nhất; property runId để truy vết |
| Database | Schema/tenant/partition hoặc khóa dữ liệu test riêng |
| Broker admin | Không wildcard delete; ownership rõ |
| ConnectionFactory | Có thể reuse theo provider contract; mỗi test dùng JMSContext/Session riêng |

JMSContext và Session không nên chia sẻ đồng thời giữa test threads. Có thể reuse factory được fixture quản lý, nhưng mỗi test tạo context/session riêng.

CI có thể retry trên cùng broker và persistence volume. Dùng buildId + retryId + UUID; nếu cần sweep resource cũ sau khi CI bị kill:

1. Chỉ chọn queue thuộc prefix test do pipeline sở hữu.
2. Kiểm tra tuổi, owner/run metadata và không có consumer hoạt động.
3. Ghi danh sách queue sắp xóa vào log artifact.
4. Xóa từng queue cụ thể qua admin API; lỗi cleanup phải được báo.

Không sweep wildcard it.> trên broker dùng chung bởi nhiều pipeline nếu không có lease/ownership. Prefix tên không tự chứng minh quyền sở hữu.

### Dọn message hay xóa destination?

| Mục đích | Hành động |
|---|---|
| Test sở hữu queue độc lập, kết thúc run | Đóng consumer rồi delete queue qua admin API |
| Test dùng TemporaryQueue | Gọi TemporaryQueue.delete() hoặc đóng connection sở hữu |
| Chỉ xóa message của run trong queue dùng chung | Consume/ACK theo selector hoặc operation lọc đã được phê duyệt |
| Queue shared có nhiều owner | Không purge; tách queue/namespace |
| Durable Topic subscription do test tạo | Đóng consumer rồi unsubscribe đúng identity |
| Broker test container bị hủy toàn bộ | Bỏ data directory cùng container; không tác động broker dùng chung |

Database rollback không tự rollback message trên broker trừ khi đã cấu hình distributed transaction. Ngược lại, xóa queue không rollback database side effect mà listener đã ghi.

## 9. Chẩn đoán timeout và cleanup lỗi

| Triệu chứng | Nguyên nhân thường gặp | Điều tra |
|---|---|---|
| Future timeout, queue vẫn có message | Consumer chưa start, selector sai, listener không kết nối | Destination, consumer count, auth và event ID |
| Future timeout, queue trống | Producer gửi nhầm broker/destination, message bị consumer khác nhận, TTL/expiry hoặc Topic không durable | Broker URL, message ID, expiry, subscriber identity |
| Chạy riêng pass, chạy parallel fail | Queue/subscription dùng chung hoặc event ID trùng | Unique queue/subscription và DB namespace |
| Nhận message cũ | Queue persistent được tái sử dụng sau CI retry | Unique destination/run ID |
| Cleanup báo queue vẫn có consumer | Listener chưa đóng hoặc callback còn chạy | Đóng resource, đợi callback terminal |
| Delete queue thất bại | Management policy, active consumer hoặc broker khác | Inspect consumer/in-flight; không force delete khi chưa rõ owner |
| Test mất message sau callback | AUTO_ACKNOWLEDGE đã ACK khi callback kết thúc | Queue riêng; chọn transacted/client-ack nếu test ACK semantics |
| Awaitility chờ quá lâu | Không có atMost, điều kiện thiếu deadline | Luôn đặt timeout, chỉ ignore lỗi tạm thời dự kiến |
| Broker ready nhưng test không nhận | Port mở trước khi security/destination sẵn sàng | Readiness đúng tầng và ACL/destination |
| CI cleanup xóa queue test khác | Sweep wildcard không có owner boundary | Run ID, lease, delete queue cụ thể |

Mỗi test nên log testRunId, broker product/version, destination/subscription, eventId, JMSMessageID nếu có, thời điểm publish/receive/commit/cleanup, exception cause và queue state trước teardown. Không log password hoặc toàn bộ payload nhạy cảm.

## 10. Checklist nghiệm thu

- [ ] Mọi điều kiện bất đồng bộ có deadline hữu hạn; không dùng sleep để đồng bộ.
- [ ] Listener đăng ký và JMSContext.start() trước khi publish; Topic test tạo subscription trước event.
- [ ] Test chờ đúng điều kiện: message nhận được hoặc business state commit, gắn với event ID.
- [ ] Queue/topic subscription có identity riêng cho test run; parallel tests không tranh message.
- [ ] Không hiểu createQueue() là lệnh portable provision physical queue.
- [ ] Mỗi test chỉ cleanup destination mà fixture sở hữu.
- [ ] Consumer/context đóng trước khi delete queue hoặc unsubscribe durable subscription.
- [ ] Queue permanent xóa qua management adapter; TemporaryQueue theo JMS lifecycle.
- [ ] Không purge wildcard, DLQ, queue shared hoặc destination production.
- [ ] CI retry dùng run ID mới; sweep resource cũ có owner, age và audit log.
- [ ] Timeout/cleanup failure có run ID, destination, event ID và broker state.
- [ ] Test xác minh side effect idempotent khi redelivery, không giả định exactly-once callback.

**Kết luận:** Test JMS ổn định cần **chờ điều kiện thật bằng deadline**, **cô lập queue/subscription theo từng test**, và **dọn tài nguyên theo đúng quyền sở hữu sau khi consumer đóng**. CompletableFuture, receive(timeout) và Awaitility giải quyết các loại chờ khác nhau; unique destination cùng admin adapter ngăn message cũ và test song song nhiễm chéo.

## Tài liệu chính thức

1. [Jakarta Messaging 3.1 — JMSContext](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext): tạo consumer, start context, close và session mode.
2. [Jakarta Messaging 3.1 — JMSConsumer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsconsumer): receive(timeout), setMessageListener và close.
3. [Jakarta Messaging 3.1 — TemporaryQueue](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/temporaryqueue): lifecycle và delete().
4. [Apache ActiveMQ Classic — JMX](https://activemq.apache.org/components/classic/documentation/jmx): BrokerView MBean, destination management và quyền quản trị.
5. [Apache ActiveMQ Classic — How Do I Find the Size of a Queue?](https://activemq.apache.org/components/classic/documentation/how-do-i-find-the-size-of-a-queue): QueueSize, InFlightCount, ConsumerCount và queue inspection.
6. [Apache Artemis — Management](https://artemis.apache.org/components/artemis/documentation/latest/management.html): ActiveMQServerControl, QueueControl, create/destroy queue và metrics.
7. [Apache Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): address, ANYCAST/MULTICAST, queue lifecycle và auto-create/delete settings.
8. [Awaitility — Usage](https://github.com/awaitility/awaitility/wiki/Usage): await(), atMost, polling interval và untilAsserted.
