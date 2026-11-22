# Phân biệt kiểm thử logic xử lý với kiểm thử ngữ nghĩa của broker

> **Chương:** Kiểm thử  
> **Phạm vi:** Test cho producer/consumer Java dùng ActiveMQ Classic hoặc Artemis. Bài phân biệt **logic nghiệp vụ** (validation, mapping, idempotency, side effect) với **ngữ nghĩa broker** (delivery, ACK/transaction, redelivery, persistence, selector, ordering, TTL, DLQ, durable subscription, failover). Ví dụ dùng JUnit 5; Artemis minh họa Jakarta JMS, Classic có client/API riêng theo phiên bản.

## 1. Hai câu hỏi khác nhau, hai loại bằng chứng

Giả sử ứng dụng nhận lệnh tạo hóa đơn từ queue `billing.commands`. Consumer phải kiểm tra payload, xác thực `orderId`, tính tổng tiền, ghi hóa đơn vào database và chỉ xác nhận message khi xử lý an toàn.

Có hai nhóm câu hỏi kiểm thử.

**A. Logic ứng dụng có đúng không?**

- Payload hợp lệ được chuyển thành command đúng?
- Payload sai bị từ chối theo quy tắc nghiệp vụ?
- Một `jobId` đã xử lý không tạo hóa đơn lần hai?
- Lỗi validation không gọi repository?
- Repository lỗi thì handler không giả vờ thành công?

**B. Broker có thực thi messaging contract đúng không?**

- Message persistent còn sau broker restart theo failure model đã cấu hình?
- JMS transaction rollback có khiến message được giao lại?
- ACK/commit chỉ loại message khỏi queue sau đúng ranh giới?
- Selector có lọc đúng message?
- TTL/expiration có hoạt động?
- Poison message có vào DLQ theo policy Classic/Artemis?
- Durable topic subscription giữ message khi subscriber offline?
- Cluster/failover có reconnect và xử lý delivery theo kỳ vọng?

Unit test dùng Mockito có thể chứng minh handler gọi repository đúng. Nó **không thể chứng minh** Artemis redeliver sau rollback, vì mock không thực thi journal, dispatch, transaction hay DLQ của broker.

**Nguyên tắc:** đặt assertion ở tầng có khả năng thực thi chính hành vi mà assertion đang tuyên bố.

## 2. Bản đồ test: logic, adapter, broker và hệ thống

~~~mermaid
flowchart TD
    U["Unit tests\nLogic thuần, không broker"] --> A["Adapter tests\nJMS mapping, headers, converter"]
    A --> B["Broker integration tests\nBroker thật + config thật"]
    B --> S["System tests\nNhiều service, DB, HA, network"]
    U -. "không chứng minh" .-> B
~~~

| Tầng | Thành phần thật | Thành phần có thể giả lập | Câu hỏi chính |
|---|---|---|---|
| Unit test | Domain logic, handler, validator | Repository, clock, external API | Logic đúng với input/output và lỗi? |
| Adapter test | JMS adapter/serializer hoặc Spring integration nhỏ | Broker có thể chưa cần | Mapping body/header/property và exception đúng? |
| Broker integration test | **Broker thật**, JMS client thật, destination/policy thật | Downstream business service có thể stub | Broker thực thi ACK, rollback, selector, TTL, DLQ…? |
| System test | Broker, DB, nhiều service/worker và network | Dependency ngoài phạm vi test | Toàn luồng đúng khi retry, restart, failover? |

Embedded broker vẫn là broker thật ở một mức, nhưng chỉ kiểm chứng cấu hình embedded đã dựng. Nó **không tự chứng minh** production có cùng persistence, TLS, authorization, cluster topology hoặc store.

Tên test nên chỉ rõ tầng:

- `shouldRejectInvalidInvoiceCommand_unit`
- `shouldMapJmsPropertiesToCommand_adapter`
- `shouldRedeliverAfterSessionRollback_artemisIT`
- `shouldRecoverAfterBrokerRestart_systemIT`

Tên test không làm nó đúng, nhưng giúp reviewer không nhầm unit behavior với provider semantics.

## 3. Unit test logic xử lý: không cần khởi động broker

Đặt logic nghiệp vụ vào class độc lập với JMS. Listener chỉ chuyển đổi message thành command và gọi handler; handler không biết broker dùng Classic hay Artemis.

### 3.1. Ví dụ cấu trúc ứng dụng

~~~java
package example.billing;

public record InvoiceCommand(
        String jobId,
        String orderId,
        long amountCents) {
}

public interface InvoiceRepository {
    void createIfAbsent(String jobId, String orderId, long amountCents);
}

public final class InvoiceHandler {
    private final InvoiceRepository repository;

    public InvoiceHandler(InvoiceRepository repository) {
        this.repository = repository;
    }

    public void handle(InvoiceCommand command) {
        if (command == null) {
            throw new IllegalArgumentException("command is required");
        }
        if (command.jobId() == null || command.jobId().isBlank()) {
            throw new IllegalArgumentException("jobId is required");
        }
        if (command.orderId() == null || command.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (command.amountCents() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        repository.createIfAbsent(
                command.jobId(),
                command.orderId(),
                command.amountCents());
    }
}
~~~

`createIfAbsent` là contract repository: cùng `jobId` không tạo side effect trùng. Unit test kiểm tra handler truyền đúng dữ liệu; **tính unique của database** cần test với DB thật hoặc DB test tương thích nếu đó là cam kết SQL.

### 3.2. JUnit 5 + Mockito kiểm tra logic

~~~java
package example.billing;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class InvoiceHandlerTest {
    @Mock
    InvoiceRepository repository;

    InvoiceHandler handler;

    @BeforeEach
    void setUp() {
        handler = new InvoiceHandler(repository);
    }

    @Test
    void createsInvoiceForValidCommand() {
        InvoiceCommand command =
                new InvoiceCommand("job-100", "order-9", 12500);

        handler.handle(command);

        verify(repository).createIfAbsent(
                "job-100", "order-9", 12500);
        verifyNoMoreInteractions(repository);
    }

    @Test
    void rejectsInvalidAmountBeforeCallingRepository() {
        InvoiceCommand command =
                new InvoiceCommand("job-101", "order-9", 0);

        assertThrows(
                IllegalArgumentException.class,
                () -> handler.handle(command));

        verifyNoInteractions(repository);
    }

    @Test
    void propagatesRepositoryFailure() {
        InvoiceCommand command =
                new InvoiceCommand("job-102", "order-9", 12500);

        doThrow(new IllegalStateException("database unavailable"))
                .when(repository)
                .createIfAbsent("job-102", "order-9", 12500);

        assertThrows(
                IllegalStateException.class,
                () -> handler.handle(command));
    }
}
~~~

Những test này không mở socket, không tạo ConnectionFactory và không cần broker. Chúng nhanh, lặp lại tốt, phù hợp kiểm tra nhiều nhánh nghiệp vụ.

### 3.3. Điều unit test không thể kết luận

Từ việc `InvoiceHandlerTest` PASS, không được kết luận:

- JMS message rollback khi handler ném exception.
- Message redeliver sau khi consumer crash.
- Persistent message sống qua broker restart.
- Queue selector, priority hoặc DLQ hoạt động.
- Consumer ở node khác nhận message.
- `@JmsListener` tự động ACK sau DB commit.

Những kết luận đó cần **integration test chạy JMS client với broker** và cấu hình tương ứng.

## 4. Adapter test: kiểm tra ranh giới JMS với logic

Adapter là nơi ánh xạ `TextMessage`/`BytesMessage`, JMS properties và schema thành command. Có thể unit test adapter với mock `Message` để kiểm tra mapping, nhưng đây vẫn **không phải broker integration test**.

~~~java
package example.billing;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

public final class InvoiceMessageAdapter {
    public InvoiceCommand toCommand(Message message)
            throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException("TextMessage required");
        }

        String jobId = message.getStringProperty("jobId");
        String orderId = message.getStringProperty("orderId");
        long amountCents = Long.parseLong(textMessage.getText());

        return new InvoiceCommand(jobId, orderId, amountCents);
    }
}
~~~

Test adapter có thể mock `TextMessage` để trả property/body cụ thể, rồi kiểm tra command. Tuy nhiên mock không chứng minh:

- Artemis/Classic truyền property đúng kiểu thực tế.
- Converter Spring tạo đúng `TextMessage`/`BytesMessage`.
- Selector expression trên broker lọc đúng.
- Provider gán `JMSRedelivered`, `JMSMessageID`, `JMSExpiration` như mong đợi.

Vì vậy adapter test nên có một số **contract test với provider thật** cho mapping quan trọng: property types, body encoding, correlation ID và timestamp.

## 5. Broker integration test cần broker thật

Một integration test ngữ nghĩa broker phải khởi tạo hoặc kết nối đúng loại broker:

- ActiveMQ Classic nếu production dùng Classic.
- Artemis nếu production dùng Artemis.
- Cùng version/client/protocol và broker policy quan trọng với production càng tốt.
- Queue/address, persistence, redelivery, expiry, security phải được cấu hình đúng phạm vi đang test.

Có thể dùng Docker Compose hoặc Testcontainers để chạy broker ephemeral. **Image tag, biến môi trường, port, entrypoint và health check phải được khóa theo image thực tế**; không coi tên image chung là API ổn định.

### 5.1. Fixture Artemis

Ví dụ fragment address/queue và policy trong `broker.xml`:

~~~xml
<addresses>
  <address name="test.jobs">
    <anycast>
      <queue name="test.jobs" durable="true"/>
    </anycast>
  </address>

  <address name="DLQ">
    <anycast>
      <queue name="DLQ" durable="true"/>
    </anycast>
  </address>
</addresses>

<address-settings>
  <address-setting match="test.jobs">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>3</max-delivery-attempts>
    <redelivery-delay>100</redelivery-delay>
  </address-setting>
</address-settings>
~~~

Đây là fragment minh họa; ghép vào `<core>` theo XSD version. Cần user test có quyền send/consume `test.jobs` và quyền cần thiết với DLQ. Nếu broker dùng auto-create/auto-delete, cố định fixture để test không phụ thuộc tài nguyên tồn tại ngẫu nhiên.

### 5.2. Fixture Classic là cấu hình khác

Classic có destination policy/dead-letter strategy riêng. Fragment `activemq.xml`:

~~~xml
<destinationPolicy>
  <policyMap>
    <policyEntries>
      <policyEntry queue="test.jobs">
        <deadLetterStrategy>
          <individualDeadLetterStrategy
              queuePrefix="DLQ."
              useQueueForQueueMessages="true"/>
        </deadLetterStrategy>
      </policyEntry>
    </policyEntries>
  </policyMap>
</destinationPolicy>
~~~

Classic client cũng có thể cấu hình redelivery policy; Artemis broker dùng address settings. **Không dùng cùng XML để test cả hai provider.**

### 5.3. Broker fixture phải cô lập

- Broker khởi động trước test và báo ready sau khi acceptor thật sự listen.
- Broker URL được inject qua property/env, không hard-code vào business logic.
- Queue test được provision rõ ràng và có quyền phù hợp.
- Test dùng unique `testRunId` để không đọc nhầm message từ lượt trước.
- Mỗi test đóng consumer/session/context/factory và dọn destination theo lifecycle.
- Test broker restart phải giữ **persistent volume/data directory**; container mới với data rỗng không kiểm chứng persistence.
- Không dùng một broker dùng chung giữa các test song song nếu chúng cùng purge/consume một queue.

## 6. Artemis Jakarta JMS integration test: rollback phải tạo redelivery

Test sau kiểm tra ngữ nghĩa broker: message commit vào queue, consumer nhận trong transacted session, rollback, rồi consumer mới nhận lại message.

Ví dụ dependency test với Artemis Jakarta client:

~~~xml
<dependency>
  <groupId>org.apache.activemq</groupId>
  <artifactId>artemis-jakarta-client</artifactId>
  <version>2.37.0</version>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.junit.jupiter</groupId>
  <artifactId>junit-jupiter</artifactId>
  <scope>test</scope>
</dependency>
~~~

Version chỉ là ví dụ; dự án thực tế nên quản lý bằng BOM/lockfile và chọn bản tương thích broker/JDK.

### 6.1. Test rollback/redelivery

~~~java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class ArtemisRedeliveryIT {
    private final String brokerUrl =
            System.getProperty("broker.url", "tcp://localhost:61616");
    private final String user =
            System.getProperty("broker.user", "test");
    private final String password =
            System.getProperty("broker.password", "test-only");

    @Test
    void rollsBackAndRedeliversUnacknowledgedMessage() throws Exception {
        String testId = UUID.randomUUID().toString();
        String queueName = "test.jobs";
        String selector = "testId = '" + testId + "'";

        try (ActiveMQConnectionFactory factory =
                     new ActiveMQConnectionFactory(brokerUrl)) {

            try (JMSContext producer = factory.createContext(
                    user, password, JMSContext.SESSION_TRANSACTED)) {
                Queue queue = producer.createQueue(queueName);
                TextMessage message =
                        producer.createTextMessage("payload-" + testId);
                message.setStringProperty("testId", testId);

                producer.createProducer().send(queue, message);
                producer.commit();
            }

            try (JMSContext first = factory.createContext(
                    user, password, JMSContext.SESSION_TRANSACTED)) {
                Queue queue = first.createQueue(queueName);
                JMSConsumer consumer = first.createConsumer(queue, selector);
                first.start();

                Message received = consumer.receive(5_000);
                assertNotNull(received, "message should be delivered");
                assertEquals(testId,
                        received.getStringProperty("testId"));
                first.rollback();
            }

            try (JMSContext second = factory.createContext(
                    user, password, JMSContext.SESSION_TRANSACTED)) {
                Queue queue = second.createQueue(queueName);
                JMSConsumer consumer = second.createConsumer(queue, selector);
                second.start();

                Message redelivered = consumer.receive(5_000);
                assertNotNull(redelivered, "message should be redelivered");
                assertEquals(testId,
                        redelivered.getStringProperty("testId"));
                assertTrue(redelivered.getJMSRedelivered(),
                        "provider should mark redelivery");
                second.commit();
            }
        }
    }
}
~~~

Điều test chứng minh:

- Producer transaction commit làm message sẵn sàng cho delivery.
- Consumer rollback không ACK message.
- Broker/client giao lại message cho consumer tiếp theo.
- Header `JMSRedelivered` được kiểm tra trên provider đang chạy.

Điều test **không** chứng minh: database side effect được rollback; consumer xử lý exactly-once; broker restart giữ message; hoặc Classic có cùng behavior. Đó là test khác.

**Fixture:** queue `test.jobs` phải tồn tại hoặc auto-create được cho phép; broker test user có quyền. Selector `testId` cô lập message của mỗi lượt. Dùng queue fixture riêng và dọn message/queue theo lifecycle suite.
## 7. Kiểm tra ACK và transaction ở đúng ranh giới

| Kiểu xử lý | ACK/hoàn tất khi nào? | Điều cần test |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | Theo semantics provider/API sau receive/listener xử lý tương ứng | Thời điểm ACK và behavior khi listener ném exception |
| `CLIENT_ACKNOWLEDGE` | Client gọi `message.acknowledge()`; phạm vi ACK của session phải hiểu đúng | Message nào được ACK khi acknowledge; rollback/reconnect |
| `SESSION_TRANSACTED` | `session.commit()` xác nhận receive; `rollback()` không xác nhận và có thể redeliver | Commit/rollback thực sự ảnh hưởng queue và delivery count |

Trong JMS, Session quản lý transaction/acknowledgment; không chia sẻ một session cho nhiều thread. Với Spring listener container, `sessionTransacted`, transaction manager và acknowledge mode ảnh hưởng behavior; phải test **container thực** thay vì chỉ gọi handler method.

### 7.1. Message chưa commit ở producer

Một integration test có thể:

1. Producer gửi message trong transacted session nhưng **chưa commit**.
2. Consumer ở connection/session độc lập thử nhận với timeout hữu hạn.
3. Producer commit.
4. Consumer nhận message.

Test này chứng minh message chưa commit chưa sẵn sàng cho delivery theo semantics provider. Tránh chờ vô hạn hoặc dùng chung một session giữa producer/consumer.

### 7.2. Consumer crash khác rollback có chủ ý

Để test crash:

- Consumer nhận message nhưng không commit.
- Dừng process/đóng socket cưỡng bức trong broker lab.
- Đợi broker phát hiện connection mất và giải phóng delivery chưa ACK.
- Mở consumer mới, xác minh cùng `testId` được giao lại.

Không assert redelivery ngay trong mili giây đầu sau kill; phát hiện transport failure và cleanup session có độ trễ. Dùng timeout tổng có giới hạn, log connection close và không lấy `Thread.sleep()` cố định làm bằng chứng.

## 8. Test redelivery limit và DLQ theo provider

DLQ là ngữ nghĩa broker/policy. Unit test chỉ có thể kiểm tra ứng dụng phân loại exception; nó không chứng minh broker chuyển poison message.

### 8.1. Artemis: max-delivery-attempts

Trong fixture Artemis:

~~~xml
<address-setting match="test.jobs">
  <dead-letter-address>DLQ</dead-letter-address>
  <max-delivery-attempts>3</max-delivery-attempts>
  <redelivery-delay>100</redelivery-delay>
</address-setting>
~~~

Test thực tế:

1. Gửi message có `testId` riêng.
2. Consumer nhận message trong transacted context và rollback có chủ ý.
3. Lặp lại theo số delivery attempts mà broker version định nghĩa.
4. Khi vượt giới hạn, xác minh message không còn ở queue nguồn và xuất hiện ở DLQ.
5. Đọc message DLQ, kiểm tra `testId`, body, properties và delivery metadata theo provider.
6. Xác minh message khác trong queue nguồn vẫn xử lý được.

`max-delivery-attempts` là cấu hình Artemis broker. Không so trực tiếp con số này với `maximumRedeliveries` của Classic client mà không tính lần giao đầu và cách provider đếm attempts.

### 8.2. Classic: redelivery policy và dead-letter strategy

Classic client có thể cấu hình redelivery:

~~~java
factory.getRedeliveryPolicy().setInitialRedeliveryDelay(100);
factory.getRedeliveryPolicy().setRedeliveryDelay(250);
factory.getRedeliveryPolicy().setUseExponentialBackOff(true);
factory.getRedeliveryPolicy().setBackOffMultiplier(2.0);
factory.getRedeliveryPolicy().setMaximumRedeliveries(2);
~~~

Broker Classic có dead-letter strategy riêng:

~~~xml
<policyEntry queue="test.jobs">
  <deadLetterStrategy>
    <individualDeadLetterStrategy
        queuePrefix="DLQ."
        useQueueForQueueMessages="true"/>
  </deadLetterStrategy>
</policyEntry>
~~~

Khi client hết số lần redelivery, poison acknowledgment/behavior provider có thể khiến broker chuyển message vào DLQ. Test phải chạy với **Classic client + Classic broker + policy thật**, không dùng Artemis để kết luận Classic.

### 8.3. Tránh test DLQ dễ sai

- Không chỉ kiểm tra `JMSRedelivered=true` một lần rồi kết luận DLQ hoạt động.
- Không giả định `maximumRedeliveries=2` đồng nghĩa `max-delivery-attempts=2`.
- Không dùng DLQ chung mà thiếu `testId`.
- Không purge DLQ dùng chung trong suite chạy song song.
- Không chỉ test chuyển DLQ; cần test operator đọc, phân tích và redrive an toàn.
- Kiểm tra body/properties còn nguyên; expiry/delivery metadata có thể khác theo broker/version.

## 9. Test selector, ordering, TTL và durable subscription

Đây đều là semantics do provider/broker tham gia thực thi, không thể chứng minh bằng mock `JMSConsumer`.

### 9.1. Message selector

Ví dụ gửi hai message:

~~~java
producer.setProperty("kind", "pdf").send(queue, "report-A");
producer.setProperty("kind", "csv").send(queue, "report-B");
~~~

Consumer:

~~~java
JMSConsumer pdfConsumer =
        context.createConsumer(queue, "kind = 'pdf'");
~~~

Test nên xác nhận:

- Consumer selector `kind='pdf'` nhận đúng `report-A`.
- `report-B` vẫn còn để consumer không selector nhận sau.
- Property có kiểu đúng; JMS selector không tương đương truy vấn tùy ý trên body JSON.
- Message không có property hoặc có type sai không match ngoài ý muốn.

### 9.2. Ordering

Để test queue order, kiểm soát topology:

- Một producer/session.
- Một queue.
- Một consumer.
- Cùng priority và delivery mode.
- Không selector, message grouping, scheduled delivery, retry/redelivery hoặc nhiều consumer.
- Không có message cũ từ test trước.

Trong điều kiện đơn giản đó có thể kiểm tra sequence theo contract ứng dụng/provider. Nhưng **nhiều consumers không có thứ tự hoàn thành toàn cục**: J1 có thể được giao cho worker chậm, J2 cho worker nhanh và commit trước.

Không viết assertion “hai consumer phải luân phiên A-B-A-B” vì đó không phải JMS contract portable.

### 9.3. TTL/expiration

Test TTL cần kiểm tra `JMSExpiration` và không giao message sau thời điểm hết hạn, nhưng tránh dùng khoảng ngủ quá sát ngưỡng:

1. Gửi message TTL đủ ngắn nhưng vẫn có margin, ví dụ 1 giây.
2. Đảm bảo không có consumer nhận ngay.
3. Đợi qua expiration bằng cơ chế chờ có timeout; không dựa clock máy khác nhau.
4. Tạo consumer mới, xác minh message hết hạn không được giao.
5. Nếu cấu hình expiry address/queue, xác minh message tới đó theo broker policy.

Test này phụ thuộc scheduler/expiry scan và cấu hình broker; CI quá tải có thể cần timeout hợp lý.

### 9.4. Durable topic subscription

Test durable subscription phải xác minh **cùng client ID + subscription name** và subscriber offline trong lúc publish:

1. Tạo durable subscriber trên topic.
2. Đóng subscriber nhưng giữ subscription.
3. Producer publish persistent message.
4. Mở lại durable subscriber với đúng identity/subscription.
5. Xác minh nhận message offline-period.
6. Hủy subscription theo API và kiểm tra resource được dọn.

Non-durable subscriber không có backlog khi offline. Queue competing consumers và durable topic subscription là hai contract khác nhau; không dùng test queue để tuyên bố topic durable hoạt động.

## 10. Test persistence qua broker restart khác test embedded/in-memory

Để chứng minh persistent message tồn tại qua **broker process restart**:

- Broker bật persistence và dùng data directory bền.
- Message gửi với delivery mode persistent (hoặc tương đương provider).
- Queue durable.
- Producer transaction commit.
- Dừng broker theo failure scenario đã định nghĩa; giữ nguyên volume/data directory.
- Khởi động lại cùng broker instance/config/store.
- Mở consumer mới và kiểm tra message nhận được.
- Xác minh message count/ACK và không mất/trùng theo business ID.

**In-memory embedded broker** có thể test delivery/transaction trong process nhưng không chứng minh persistent store. **Container bị xóa cùng volume** rồi tạo container rỗng cũng không phải restart persistence test.

### 10.1. Test crash/recovery phải nêu failure model

| Failure được mô phỏng | Có thể kết luận | Không thể kết luận |
|---|---|---|
| Java consumer crash | Unacked delivery phục hồi theo broker/client semantics | Broker persistence qua restart |
| Broker process restart, giữ data directory | Store phục hồi sau process restart trong môi trường đó | Disk failure/HA takeover |
| Container restart, giữ persistent volume | Broker/container phục hồi cùng volume | Multi-node HA nếu chưa test topology |
| Primary failover sang backup | Behavior của HA policy và backup node đã thử | DR ở region khác |
| Xóa volume hoặc làm hỏng journal | Recovery từ backup/replica nếu đã cấu hình và test | Rediscovery tự tái tạo message bị mất |

Không dùng từ “durable” để gộp mọi failure model. Test report cần ghi broker version, persistence mode, volume, thao tác dừng và topology.

## 11. Test failover/cluster là system test

Nếu production dùng Classic Failover Transport, Artemis HA, cluster redistribution hoặc bridge, chạy test riêng:

- **Classic Failover Transport:** client reconnect endpoint khác; kiểm tra send/commit unknown và consumer redelivery.
- **Artemis HA:** primary/backup theo shared-store hoặc replication; kiểm tra backup takeover và state.
- **Artemis redistribution:** backlog ở B chuyển sang A khi consumer thay đổi vị trí và policy cho phép; chứng minh message pending ở B trước khi A có demand.
- **Cluster load balancing:** phân biệt routing message mới với redistribution backlog cũ.
- **Network partition:** kiểm tra timeout, retry, fencing/quorum và duplicate; không chỉ tắt một socket rồi suy ra HA đúng.

Một test chỉ tạo `ActiveMQConnectionFactory` với URL chứa hai endpoint **không chứng minh** broker HA topology hoạt động. Phải khởi chạy topology tương ứng và inject failure vào đúng node/network path.

## 12. Test Spring JMS listener: gọi method trực tiếp chưa đủ

Ví dụ:

~~~java
listener.onMessage(payload);
~~~

Đây là test logic handler, không kiểm tra:

- Spring tạo listener container chưa.
- `@JmsListener` đăng ký đúng destination chưa.
- Converter ánh xạ `TextMessage`/JSON đúng chưa.
- Listener factory dùng transaction/ack mode nào.
- Exception có rollback và broker redeliver không.
- Concurrency có tạo đúng số session/consumer không.

Một **Spring JMS integration test** phải khởi tạo ApplicationContext với đúng provider `ConnectionFactory`, enable listener container, gửi message qua broker thật và chờ kết quả handler quan sát được (DB row, test latch hoặc event). Sau đó cố ý ném exception để kiểm tra rollback/redelivery với broker policy thực.

Nếu listener ghi DB, dùng database test thật hoặc DB container cho integration test; mock repository chỉ chứng minh adapter gọi repository, không chứng minh transaction DB/JMS atomic.

### 12.1. Không dùng Thread.sleep() để đồng bộ test

Thay vì:

~~~java
Thread.sleep(2000);
assertEquals(1, repository.count());
~~~

Dùng bounded wait/polling hoặc latch:

~~~java
boolean completed = latch.await(
        5, java.util.concurrent.TimeUnit.SECONDS);
assertTrue(completed, "listener did not complete within 5 seconds");
~~~

Trong integration test, latch chỉ báo handler đã chạy; **assert dữ liệu bền** từ repository/DB sau đó mới chứng minh side effect. Đặt timeout hữu hạn và log test ID để chẩn đoán khi CI chậm.
## 13. Cô lập test: tránh message cũ, test song song và trạng thái rò rỉ

Broker integration test thường flaky vì dùng chung destination hoặc không dọn state:

- Test A để lại message pending; test B vô tình nhận.
- DLQ dùng chung chứa poison message từ lượt chạy trước.
- Một listener Spring context còn sống nhận message của test khác.
- Queue purge giữa test làm mất message suite khác đang cần.
- Client prefetch khiến count ở management không phản ánh ngay queue pending.
- Test chạy song song đụng cùng client ID/durable subscription name.

Nguyên tắc thực hành:

1. Mỗi test dùng UUID/`testRunId` riêng trong property, body và log.
2. Dùng queue/namespace riêng theo suite nếu broker cho phép; nếu không, selector cô lập message và fixture đảm bảo cleanup.
3. Không purge destination dùng chung khi suite chạy song song.
4. Đóng `JMSContext`, consumer, connection factory, listener container và broker container theo lifecycle.
5. Durable subscription có tên riêng; hủy đúng lúc.
6. Timeout đủ cho broker/CI nhưng hữu hạn; tránh retry vô hạn.
7. Khi assertion fail, in test ID, broker URL đã che secret, queue count, delivering count và correlation ID.
8. Test cần message rỗng phải kiểm tra queue thực sự rỗng hoặc dùng selector cho test ID; không chỉ dựa `receiveNoWait()` trong lúc provider chưa ổn định.

### 13.1. Không chạy song song các test cùng state

Nếu hai test cùng consume `test.jobs`, một test có thể lấy message của test kia dù selector khác. Selector giúp lọc message, nhưng queue state, DLQ và management counter vẫn được chia sẻ.

Có ba lựa chọn:

- Một broker riêng cho mỗi test class/suite.
- Một queue được provision riêng theo test ID và xóa sau khi hoàn tất.
- Một queue fixture dùng chung nhưng suite **không chạy song song**, mỗi message có selector và cleanup rõ.

Không tạo queue theo mỗi test trong production chỉ để test dễ hơn; test fixture có thể provision resource động nếu broker permissions và cleanup được quản lý.

## 14. Ma trận: hành vi nào test ở tầng nào?

| Behavior | Unit | Adapter | Broker integration | System |
|---|---:|---:|---:|---:|
| Validate payload/tính toán nghiệp vụ | **Chính** | | | |
| Mapping JMS property/body | | **Chính** | Xác nhận provider mapping | |
| Gọi send đúng destination | Mock boundary | Có thể | **Cần** nếu route thật quan trọng | |
| Transaction send commit/rollback | | | **Chính** | Khi tích hợp nhiều resource |
| Consumer ACK/rollback/redelivery | | | **Chính** | Crash/network thật |
| Persistent message qua broker restart | | | **Chính** (giữ store) | HA/DR mở rộng |
| Selector/priority/ordering | | | **Chính** | Nếu nhiều broker/consumer |
| TTL/expiry queue | | | **Chính** | Tải cao/time drift |
| DLQ/max attempts | | | **Chính** | Operator redrive workflow |
| Durable topic subscription | | Adapter config | **Chính** | Subscriber deploy/scale |
| TLS/auth/authorization | Không | Config mapping | Broker integration | Rotation/PKI/HA |
| Cluster redistribution/failover | Không | URL/client config | Cluster integration | **Chính** khi topology production |
| DB inbox/idempotency | Logic có thể unit | | DB + broker integration | **Chính** khi crash window |
| Throughput/latency capacity | Không | Không | Benchmark component | **Chính** end-to-end |

Không cần viết mọi hành vi thành system test đắt đỏ. Nhưng **không thay broker integration test bằng mock** khi acceptance criterion nói về broker semantics.

## 15. Cấu trúc test suite có thể duy trì

~~~text
src/
  main/java/
    example/billing/
      InvoiceHandler.java
      InvoiceMessageAdapter.java
      BillingListener.java
  test/java/
    example/billing/
      InvoiceHandlerTest.java             # JUnit + Mockito, không broker
      InvoiceMessageAdapterTest.java      # Mapping test
  integrationTest/java/
    example/billing/
      ArtemisRedeliveryIT.java             # Broker thật
      ArtemisDlqIT.java                    # Address settings + DLQ
      ArtemisPersistenceIT.java            # Giữ data volume khi restart
      ClassicRedeliveryIT.java             # Classic client + broker thật
  test-resources/
    artemis/
      broker.xml
    classic/
      activemq.xml
~~~

Tên folder `integrationTest` tùy build tool; không có yêu cầu Gradle source set cụ thể. Quan trọng là phân tách **lệnh chạy**, dependency và tài nguyên môi trường. Unit tests nên chạy nhanh ở mọi commit; broker tests có thể chạy ở CI stage chuyên biệt nhưng phải chạy đủ thường xuyên.

### 15.1. Tiêu chí hoàn tất của một broker integration test

Một test đáng tin cậy phải ghi:

- Broker name/version và client artifact/version.
- Protocol/URL, queue/address, routing type và policy được test.
- Persistence mode và data directory nếu liên quan.
- Producer delivery mode và transaction mode.
- Consumer acknowledge/transaction mode.
- Số lần nhận/rollback/redelivery mong đợi.
- Assertion dựa trên business test ID, không dựa duy nhất timestamp/log text.
- Timeout và cleanup behavior.
- Những failure model **chưa** được kiểm tra.

## 16. Lỗi test thường gặp và cách sửa

| Test sai | Vì sao không chứng minh behavior | Cách sửa |
|---|---|---|
| Mock `JmsTemplate.convertAndSend()` rồi tuyên bố broker nhận message | Không có network/broker | Broker integration test gửi message thật |
| Gọi listener method trực tiếp rồi tuyên bố ACK đúng | Không chạy listener container/session | Khởi tạo container + broker thật |
| Dùng in-memory broker để kết luận persistence | Không có store bền như production | Broker thật với persistent volume và restart |
| Chỉ assert `JMSRedelivered` sau một rollback mock | Không có provider delivery | JMS transaction thật, rollback thật |
| Test DLQ chỉ kiểm tra exception được ném | Broker chưa chuyển message | Broker policy + đọc queue DLQ |
| Dùng hai consumer và assert FIFO completion | Consumer chạy song song | Một consumer nếu kiểm tra thứ tự nhận; ordering per key test riêng |
| Test TTL với sleep sát expiry | Clock/scheduler/CI variance | TTL có margin, bounded receive, expiry policy |
| Dùng queue chung trong test song song | Nhận nhầm message hoặc purge chéo | Queue/test ID cô lập |
| Chỉ kiểm tra queue depth sau redistribution | Consumer có thể nhận và ACK ngay | Log jobId + delivery/ACK metrics |
| Broker test chạy trên version khác production | Semantics/config có thể khác | Pin image/client/version và cấu hình |
| Test chỉ chạy embedded broker | Không có TLS/HA/cluster/production persistence | Bổ sung broker integration/system suite |
| Retry test không có idempotency assertion | Duplicate side effect bị bỏ qua | Unique jobId/inbox và crash-window test |

## 17. Checklist thiết kế kiểm thử

- [ ] Logic nghiệp vụ có unit test độc lập với JMS/provider?
- [ ] Adapter test kiểm tra mapping body, headers, properties và exception?
- [ ] Test tuyên bố ACK/rollback/redelivery có chạy trên broker thật?
- [ ] Broker integration dùng đúng provider (Classic hoặc Artemis), client namespace và version phù hợp?
- [ ] Queue/address/routing type/permissions được provision tường minh?
- [ ] Test producer transaction commit và rollback ở boundary cần thiết?
- [ ] Test consumer transacted ACK/rollback và delivery lại sau crash?
- [ ] DLQ test xác minh message thực sự được chuyển, body/property còn đọc được?
- [ ] TTL, selector, ordering, priority và durable subscription có test riêng theo semantics?
- [ ] Persistence test giữ nguyên broker data directory qua restart?
- [ ] HA/cluster/redistribution test dựng topology thật và ghi failure model?
- [ ] Test cô lập destination/testRunId, không purge queue dùng chung?
- [ ] Async assertions dùng timeout/latch/polling, không dựa sleep cố định?
- [ ] Consumer side effect có idempotency khi broker redeliver?
- [ ] Test report ghi rõ điều gì **đã** và **chưa** được chứng minh?

## 18. Kết luận

**Kiểm thử logic xử lý** trả lời ứng dụng tính toán, validation, mapping nghiệp vụ và side effect có đúng hay không. **Kiểm thử ngữ nghĩa của broker** trả lời broker thật có thực thi delivery, transaction, ACK, redelivery, persistence, selector, TTL, DLQ, durable subscription và failover đúng theo cấu hình hay không.

Mockito và unit test rất hữu ích, nhưng chỉ chứng minh các tương tác mà mock được lập trình để trả về. Khi tuyên bố “rollback sẽ redeliver”, “message sống qua restart” hoặc “poison message vào DLQ”, cần một **broker integration test** chạy đúng provider/version/configuration. Khi tuyên bố HA/cluster hoạt động, cần **system test trên topology và failure model tương ứng**.

Thiết kế test tốt không cố đưa mọi thứ vào một loại test. Nó đặt **mỗi assertion ở tầng có thể thực thi và chứng minh hành vi đó**, dùng test ID để cô lập, giữ timeout hữu hạn và kiểm tra idempotency tại ranh giới database/JMS. Nhờ vậy test suite vừa nhanh khi sửa logic, vừa đủ tin cậy khi thay broker, đổi policy hoặc nâng phiên bản ActiveMQ.
