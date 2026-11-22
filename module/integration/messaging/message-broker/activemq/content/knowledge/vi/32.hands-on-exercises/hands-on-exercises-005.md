# Thực hành retry, DLQ và phát lại thông điệp lỗi có kiểm soát

> **Chương:** Bài tập tổng hợp  
> **Mục tiêu:** Hoàn thành một lab đầu-cuối cho luồng `orders`: gửi message persistent, cố tình tạo lỗi xử lý, quan sát rollback và redelivery có backoff, xác nhận poison message được chuyển vào Dead Letter Queue (DLQ), điều tra nguồn gốc, rồi replay có giới hạn và có audit. Lab dùng **Java 17, Jakarta JMS và ActiveMQ Artemis**; cuối bài đối chiếu cơ chế tương ứng trong ActiveMQ Classic.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

1. Phân biệt một lần delivery lại do rollback với một lần replay nghiệp vụ được tạo thành message mới.
2. Cấu hình delivery-attempt limit, redelivery delay và DLQ cho đúng address/queue.
3. Dùng JMS transacted session để ACK/rollback rõ ràng; không nuốt exception rồi vô tình ACK message.
4. Đọc `JMSRedelivered`, `JMSXDeliveryCount`, `eventId` và metadata nguồn của message DLQ.
5. Replay một message sau khi đã xử lý nguyên nhân, giữ nguyên logical `eventId`, ghi nhận replay batch và giới hạn số lần replay.
6. Chứng minh message không bị mất hoặc replay vô hạn bằng queue metrics, inbox/idempotency và test tình huống lỗi.

Lab giả lập một order event có property `failUntil`. Consumer rollback khi delivery count chưa vượt giá trị này. Message thường sẽ thành công sau vài lần retry; message poison dùng `failUntil=99` sẽ vượt delivery budget và được broker chuyển vào DLQ. Đây là công tắc lỗi dành riêng cho lab, không phải một field nghiệp vụ nên đưa vào contract production.

## 2. Chuẩn bị broker và project

### 2.1. Tạo Artemis instance riêng cho lab

Chọn một bản Artemis và client cùng dòng phiên bản, chạy trên máy local hoặc môi trường test cô lập. Ví dụ trên Linux:

```bash
export ARTEMIS_HOME=/opt/apache-artemis
"$ARTEMIS_HOME/bin/artemis" create /var/lib/artemis-lab --user lab --password lab-password --role lab
/var/lib/artemis-lab/bin/artemis run
```

Broker lab lắng nghe ở `tcp://localhost:61616` theo cấu hình mặc định. Nếu môi trường đã có broker test, dùng endpoint và user riêng của bạn; không tạo instance mới trên thư mục data đang được broker khác sử dụng.

### 2.2. Khai báo queue và DLQ

Trong `broker.xml`, thêm các fragment sau vào phần `<core>` hiện có. Lab dùng một ANYCAST queue cho đơn hàng, một queue DLQ và một queue quarantine để giữ message đã hết replay budget:

```xml
<addresses>
    <address name="orders">
        <anycast><queue name="orders"/></anycast>
    </address>
    <address name="DLQ">
        <anycast><queue name="DLQ"/></anycast>
    </address>
    <address name="orders.quarantine">
        <anycast><queue name="orders.quarantine"/></anycast>
    </address>
</addresses>
<address-settings>
    <address-setting match="orders">
        <dead-letter-address>DLQ</dead-letter-address>
        <max-delivery-attempts>3</max-delivery-attempts>
        <redelivery-delay>1000</redelivery-delay>
        <redelivery-delay-multiplier>2.0</redelivery-delay-multiplier>
        <max-redelivery-delay>5000</max-redelivery-delay>
    </address-setting>
</address-settings>
```

Đây là fragment cấu hình, không thay toàn bộ `broker.xml`. Giữ nguyên các address/binding đang có; bảo đảm mỗi address/queue chỉ được khai báo một lần. Nếu security được bật, user `lab` cần quyền send/consume trên `orders`, `DLQ`, `orders.quarantine` và quyền cần thiết để tạo/nhận destination theo policy của broker.

| Thuộc tính | Giá trị lab | Tác dụng |
|---|---:|---|
| `dead-letter-address` | `DLQ` | Chuyển message vượt delivery attempts sang address DLQ |
| `max-delivery-attempts` | `3` | Giới hạn số lần broker giao message trước khi dead-letter |
| `redelivery-delay` | `1000` ms | Chờ trước lần giao lại |
| `redelivery-delay-multiplier` | `2.0` | Tăng delay theo cấp số nhân |
| `max-redelivery-delay` | `5000` ms | Chặn delay tăng vượt quá 5 giây |

Với delay mẫu, các lần retry tăng dần xấp xỉ 1 giây, 2 giây rồi tối đa 5 giây. Thời điểm thực tế còn phụ thuộc broker scheduling, load và phiên bản. `max-delivery-attempts` là delivery budget của Artemis; đừng mặc định nó đếm giống `maximumRedeliveries` của Classic.

### 2.3. Maven project

Tạo project Java 17 với dependency Jakarta client của Artemis. Version client nên khớp broker release đang chạy:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>2.37.0</version>
    </dependency>
</dependencies>
<build>
    <plugins>
        <plugin>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>exec-maven-plugin</artifactId>
            <version>3.5.0</version>
        </plugin>
    </plugins>
</build>
```

`2.37.0` là version ví dụ pin dependency cho lab; nếu broker dùng release khác, thay client version bằng bản tương thích cùng release train. Nếu dự án quản lý version qua BOM, đưa dependency vào `dependencyManagement` theo quy ước dự án.

Đặt thông tin kết nối trong biến môi trường:

```bash
export ARTEMIS_URL=tcp://localhost:61616
export ARTEMIS_USER=lab
export ARTEMIS_PASSWORD=lab-password
```

Không commit password thật vào repository. Tạo các class lab ở package `lab.retry` và giữ mỗi public class trong file Java cùng tên.

## 3. Producer: gửi message persistent có event ID ổn định

Producer dùng transacted session. `eventId` là UUID của sự kiện logic; nếu producer retry gửi lại cùng một order event do timeout không rõ kết quả, ứng dụng cần giữ cùng event ID qua lần gửi lại.

Tạo `OrderProducer.java`:

```java
package lab.retry;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import java.util.UUID;

public final class OrderProducer {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "ARTEMIS_URL", "tcp://localhost:61616");
        String user = System.getenv("ARTEMIS_USER");
        String password = System.getenv("ARTEMIS_PASSWORD");
        String eventId = args.length > 0
                ? args[0] : UUID.randomUUID().toString();
        int failUntil = args.length > 1
                ? Integer.parseInt(args[1]) : 2;

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);
        Connection connection = factory.createConnection(user, password);
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue orders = session.createQueue("orders");
                MessageProducer producer = session.createProducer(orders);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                    TextMessage message = session.createTextMessage(
                            "{\"orderId\":\"O-1001\",\"amountMinor\":129900}");
                    message.setStringProperty("eventId", eventId);
                    message.setStringProperty("eventType", "OrderCreated");
                    message.setStringProperty("orderId", "O-1001");
                    message.setIntProperty("schemaVersion", 1);
                    message.setIntProperty("failUntil", failUntil);
                    producer.send(message);
                    session.commit();
                    System.out.printf(
                            "SENT eventId=%s failUntil=%d%n",
                            eventId, failUntil);
                } catch (Exception e) {
                    session.rollback();
                    throw e;
                } finally {
                    producer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
            factory.close();
        }
    }
}
```

Gửi hai loại message:

```bash
# Message lỗi hai lần rồi xử lý thành công ở lần giao kế tiếp
mvn -q exec:java -Dexec.mainClass=lab.retry.OrderProducer -Dexec.args="evt-retry-001 2"

# Message lỗi liên tục để kiểm tra chuyển DLQ
mvn -q exec:java -Dexec.mainClass=lab.retry.OrderProducer -Dexec.args="evt-poison-001 99"
```

`exec-maven-plugin` đã được khai báo trong fragment `pom.xml` ở trên. Hai event ID mẫu phải khác nhau; khi lặp lại bài test, tạo ID mới để tránh nhầm message tồn từ lần chạy trước.

## 4. Consumer: rollback, redelivery và commit

### 4.1. Dùng transacted session

Tạo `OrderConsumer.java`:

```java
package lab.retry;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class OrderConsumer {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "ARTEMIS_URL", "tcp://localhost:61616");
        String user = System.getenv("ARTEMIS_USER");
        String password = System.getenv("ARTEMIS_PASSWORD");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);
        Connection connection = factory.createConnection(user, password);
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue orders = session.createQueue("orders");
                MessageConsumer consumer = session.createConsumer(orders);
                try {
                    connection.start();
                    for (int poll = 0; poll < 8; poll++) {
                        Message received = consumer.receive(10_000L);
                        if (received == null) {
                            System.out.println("No more messages in this window.");
                            break;
                        }
                        if (!(received instanceof TextMessage message)) {
                            System.out.println("Unsupported message type; rollback.");
                            session.rollback();
                            continue;
                        }

                        String eventId =
                                message.getStringProperty("eventId");
                        int deliveryCount =
                                message.propertyExists("JMSXDeliveryCount")
                                ? message.getIntProperty("JMSXDeliveryCount")
                                : 1;
                        int failUntil =
                                message.getIntProperty("failUntil");
                        boolean redelivered = message.getJMSRedelivered();

                        System.out.printf(
                                "RECEIVED eventId=%s deliveryCount=%d " +
                                "redelivered=%s failUntil=%d%n",
                                eventId, deliveryCount,
                                redelivered, failUntil);

                        if (deliveryCount <= failUntil) {
                            session.rollback();
                            System.out.printf(
                                    "ROLLBACK eventId=%s attempt=%d%n",
                                    eventId, deliveryCount);
                            continue;
                        }

                        try {
                            processOrder(message);
                            session.commit();
                            System.out.printf(
                                    "COMMITTED eventId=%s attempt=%d%n",
                                    eventId, deliveryCount);
                        } catch (Exception processingFailure) {
                            session.rollback();
                            System.err.printf(
                                    "PROCESSING_FAILED eventId=%s type=%s%n",
                                    eventId,
                                    processingFailure.getClass().getSimpleName());
                        }
                    }
                } finally {
                    consumer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
            factory.close();
        }
    }

    private static void processOrder(TextMessage message) throws Exception {
        String eventId = message.getStringProperty("eventId");
        String orderId = message.getStringProperty("orderId");
        if (eventId == null || eventId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing event identity");
        }
        // Thay bằng xử lý nghiệp vụ idempotent trong lab mở rộng.
        System.out.printf("PROCESS orderId=%s eventId=%s body=%s%n",
                orderId, eventId, message.getText());
    }
}
```

`Session.SESSION_TRANSACTED` khiến ACK của message chỉ có hiệu lực khi `commit()` thành công. `rollback()` trả delivery chưa commit về broker để áp dụng redelivery policy. `JMSRedelivered` là cờ cho biết message đã được giao trước đó; `JMSXDeliveryCount` giúp quan sát số lần delivery mà provider báo cáo. Đọc cả hai để chẩn đoán, nhưng dùng semantics và giới hạn của broker làm nguồn quyết định cuối.

Nếu handler ném exception, phải rollback. Nếu catch exception rồi return mà không rollback, container/session có thể commit hoặc ACK message theo cách cấu hình; poison message sẽ không được retry như mong muốn. Trong production, chỉ commit sau khi business transaction và inbox/idempotency record đã hoàn tất theo thiết kế nhất quán.

### 4.2. Chạy lab và đọc log

Sau khi broker sẵn sàng, chạy producer hai lần rồi chạy consumer:

```bash
mvn -q exec:java -Dexec.mainClass=lab.retry.OrderProducer -Dexec.args="evt-retry-001 2"
mvn -q exec:java -Dexec.mainClass=lab.retry.OrderProducer -Dexec.args="evt-poison-001 99"
mvn -q exec:java -Dexec.mainClass=lab.retry.OrderConsumer
```

Kết quả mong đợi:

| Event | Delivery attempts | Hành vi | Trạng thái cuối |
|---|---:|---|---|
| `evt-retry-001` | 1, 2 | Rollback theo `failUntil=2` | — |
| `evt-retry-001` | 3 | Xử lý và commit | Queue `orders` không còn message này |
| `evt-poison-001` | Tới delivery budget 3 | Rollback liên tục | Broker chuyển message sang queue `DLQ` |

`JMSXDeliveryCount` thường bắt đầu từ 1 cho delivery đầu tiên; broker có thể có khác biệt nhỏ theo protocol/version. Đối chiếu log của consumer với queue counters và DLQ thực tế. Nếu count vượt dự kiến, xác minh address-setting match đúng address, client có thật sự dùng transacted session và không có consumer khác cùng nhận queue.

Không dùng `Thread.sleep()` để tạo redelivery. Delay thuộc broker policy; consumer chờ bằng `receive(timeout)` để tránh biến lab thành một vòng polling không kiểm soát.

## 5. Điều tra DLQ trước khi replay

### 5.1. DLQ là nơi cách ly, không phải queue retry tự động

Khi message đã vào DLQ, broker đã kết thúc retry budget của destination nguồn. Consumer của queue `orders` không tự động đọc DLQ; phải có thao tác triage/replay riêng. Giữ DLQ message cho tới khi có quyết định xử lý, retention và owner rõ ràng.

Kiểm tra trên management console hoặc JMX:

| Queue | Chỉ số cần xem | Kết quả mong đợi sau lab |
|---|---|---|
| `orders` | `MessageCount`, `DeliveringCount`, `ConsumerCount` | Poison message đã rời source queue |
| `DLQ` | `MessageCount`, `MessagesAdded`, oldest age | Tăng một message poison |
| `orders.quarantine` | `MessageCount` | Ban đầu bằng 0 |

### 5.2. Đọc metadata nguồn và event identity

Artemis thường bổ sung metadata nguồn khi dead-letter, trong đó có:

- `_AMQ_ORIG_ADDRESS`: address ban đầu.
- `_AMQ_ORIG_QUEUE`: queue ban đầu.

Đây là property phục vụ điều tra của Artemis, không phải tên header portable giữa mọi JMS provider. Luôn kiểm tra property có tồn tại trước khi đọc; không dùng nó làm logical event ID. `eventId` do ứng dụng tạo mới là khóa tương quan để tìm producer log, consumer log và business record.

Ví dụ browse DLQ mà không remove message:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.QueueBrowser;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import java.util.Enumeration;

public final class DlqInspector {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "ARTEMIS_URL", "tcp://localhost:61616");
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);
        Connection connection = factory.createConnection(
                System.getenv("ARTEMIS_USER"),
                System.getenv("ARTEMIS_PASSWORD"));
        try {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            try {
        Queue dlq = session.createQueue("DLQ");
                QueueBrowser browser = session.createBrowser(dlq);
                try {
                    connection.start();
                    Enumeration<?> messages = browser.getEnumeration();
                    while (messages.hasMoreElements()) {
                        Message message = (Message) messages.nextElement();
                        String eventId =
                                message.getStringProperty("eventId");
                        String sourceAddress = message.propertyExists(
                                "_AMQ_ORIG_ADDRESS")
                                ? message.getStringProperty("_AMQ_ORIG_ADDRESS")
                                : "unknown";
                        String sourceQueue = message.propertyExists(
                                "_AMQ_ORIG_QUEUE")
                                ? message.getStringProperty("_AMQ_ORIG_QUEUE")
                                : "unknown";
                        System.out.printf(
                                "DLQ eventId=%s sourceAddress=%s sourceQueue=%s " +
                                "redelivered=%s%n",
                                eventId, sourceAddress, sourceQueue,
                                message.getJMSRedelivered());
                        if (message instanceof TextMessage text) {
                            System.out.println(text.getText());
                        }
                    }
                } finally {
                    browser.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
            factory.close();
        }
    }
}
```

`QueueBrowser` chỉ browse, không ACK/remove message. Tránh in payload nhạy cảm ra terminal/log; trong production chỉ log event ID, source, failure class/reason code và trace/correlation ID đã sanitize.

### 5.3. Triage record trước khi quyết định replay

Với mỗi DLQ message, ghi lại:

1. `eventId`, message ID provider, source address/queue và thời điểm vào DLQ.
2. `JMSXDeliveryCount` cuối cùng nếu provider còn cung cấp, `JMSRedelivered`, schema version và event type.
3. Exception/log tương ứng từ consumer; DLQ không tự lưu đầy đủ stack trace của ứng dụng.
4. Business state: order còn hợp lệ không, side effect đã xảy ra chưa, inbox/dedup record có tồn tại không.
5. Nguyên nhân đã được khắc phục chưa: code, dependency, credential, schema, queue policy hoặc dữ liệu.

Chỉ replay sau khi đã phân loại. Message hết hạn, event không còn hợp lệ hoặc đã áp dụng side effect không nên được phát lại một cách máy móc. Nếu không thể sửa an toàn, giữ trong DLQ/quarantine và giao owner nghiệp vụ quyết định.

## 6. Replay có kiểm soát và atomic ACK + send

### 6.1. Quy tắc replay

Replay là thao tác tạo một message mới từ message DLQ đã được duyệt. Cần giữ `eventId` để consumer idempotent nhận ra cùng một sự kiện logic, đồng thời tạo `replayBatchId` và tăng `replayCount` để audit và giới hạn vòng lặp.

| Thuộc tính | Replay |
|---|---|
| `eventId` | Giữ nguyên; đại diện cùng logical event |
| `JMSMessageID` | Provider tạo ID mới cho message mới |
| `JMSXDeliveryCount` | Không copy; broker quản lý lại từ delivery mới |
| `replayCount` | Tăng một đơn vị |
| `replayBatchId` | Tạo ID cho lần replay được duyệt |
| `_AMQ_ORIG_ADDRESS`, `_AMQ_ORIG_QUEUE` | Metadata Artemis không tự coi là contract ứng dụng |
| Body | Giữ nguyên, trừ khi có migration/repair được phê duyệt |

Replay tool nhận một `eventId` cụ thể đã được duyệt và dùng selector để lấy đúng message đó từ DLQ. Không replay “message đầu tiên trong DLQ” một cách mù quáng khi queue có nhiều source/event khác nhau.

Trong lab, `failUntil` là công tắc lỗi giả lập. Replay tool sẽ đặt nó về 0 để mô phỏng tình huống nguyên nhân đã được sửa. Đây chỉ là thao tác mô phỏng. Production không được tự ý sửa payload/property nghiệp vụ; hãy sửa consumer/dependency hoặc chạy một transformation có version, audit và approval rõ ràng.

### 6.2. ReplayTool dùng cùng transacted JMS session

Tạo `DlqReplay.java`. Consumer đọc DLQ, producer gửi message mới vào `orders` hoặc `orders.quarantine`, rồi commit cả hai thao tác trong cùng JMS transaction:

```java
package lab.retry;

import jakarta.jms.Connection;
import jakarta.jms.DeliveryMode;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import java.util.UUID;

public final class DlqReplay {
    private static final int MAX_REPLAY_COUNT = 1;

    public static void main(String[] args) throws Exception {
        if (args.length != 1 || args[0].isBlank()) {
            throw new IllegalArgumentException(
                    "Pass the eventId that has been approved for replay");
        }
        String targetEventId = args[0];
        String selectorValue = targetEventId.replace("'", "''");
        String url = System.getenv().getOrDefault(
                "ARTEMIS_URL", "tcp://localhost:61616");
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);
        Connection connection = factory.createConnection(
                System.getenv("ARTEMIS_USER"),
                System.getenv("ARTEMIS_PASSWORD"));
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue dlq = session.createQueue("DLQ");
                Queue orders = session.createQueue("orders");
                Queue quarantine = session.createQueue("orders.quarantine");
                MessageConsumer consumer = session.createConsumer(
                        dlq, "eventId = '" + selectorValue + "'");
                MessageProducer orderProducer = session.createProducer(orders);
                MessageProducer quarantineProducer =
                        session.createProducer(quarantine);
                try {
                    orderProducer.setDeliveryMode(DeliveryMode.PERSISTENT);
                    quarantineProducer.setDeliveryMode(
                            DeliveryMode.PERSISTENT);
                    connection.start();

                    if (!(consumer.receive(5000L) instanceof TextMessage dead)) {
                        System.out.println("DLQ is empty in this window.");
                        session.rollback();
                        return;
                    }

                    String eventId = dead.getStringProperty("eventId");
                    int previousReplayCount =
                            dead.propertyExists("replayCount")
                            ? dead.getIntProperty("replayCount") : 0;
                    String replayBatchId = UUID.randomUUID().toString();

                    TextMessage copy = session.createTextMessage(dead.getText());
                    copy.setStringProperty("eventId", eventId);
                    copy.setStringProperty(
                            "eventType", dead.getStringProperty("eventType"));
                    copy.setStringProperty(
                            "orderId", dead.getStringProperty("orderId"));
                    copy.setIntProperty(
                            "schemaVersion", dead.getIntProperty("schemaVersion"));
                    copy.setIntProperty(
                            "replayCount", previousReplayCount + 1);
                    copy.setStringProperty("replayBatchId", replayBatchId);
                    if (dead.getJMSCorrelationID() != null) {
                        copy.setJMSCorrelationID(dead.getJMSCorrelationID());
                    }
                    if (dead.getJMSType() != null) {
                        copy.setJMSType(dead.getJMSType());
                    }

                    if (previousReplayCount >= MAX_REPLAY_COUNT) {
                        copy.setStringProperty(
                                "quarantineReason", "replay_limit_exceeded");
                        quarantineProducer.send(
                                copy, DeliveryMode.PERSISTENT, 4, 0);
                        session.commit();
                        System.out.printf(
                                "QUARANTINED eventId=%s batch=%s%n",
                                eventId, replayBatchId);
                    } else {
                        // Lab-only repair: mô phỏng lỗi tạm thời đã được sửa.
                        copy.setIntProperty("failUntil", 0);
                        orderProducer.send(
                                copy, DeliveryMode.PERSISTENT, 4, 0);
                        session.commit();
                        System.out.printf(
                                "REPLAY_COMMITTED eventId=%s batch=%s " +
                                "replayCount=%d%n",
                                eventId, replayBatchId, previousReplayCount + 1);
                    }
                } catch (Exception e) {
                    session.rollback();
                    throw e;
                } finally {
                    consumer.close();
                    orderProducer.close();
                    quarantineProducer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
            factory.close();
        }
    }
}
```

Trong cùng một JMS transacted session, việc nhận message DLQ và gửi message mới tới source/quarantine được commit như một transaction của broker. Nếu send thất bại trước commit, `rollback()` giữ lại DLQ message. Nếu commit thành công, DLQ message được acknowledge và message mới được gửi. Nếu client mất kết nối đúng lúc commit, kết quả phía client có thể không xác định; `eventId` ổn định và inbox dedup vẫn cần thiết để bảo vệ side effect.

Đoạn code copy **allowlist** các application properties thuộc contract; không copy `JMSXDeliveryCount`, `JMSMessageID` hoặc metadata broker. Nếu contract có thêm property, thêm nó có chủ đích và kiểm tra kiểu dữ liệu. `replayCount` giới hạn một lần replay; nếu message tiếp tục lỗi sau replay, lần DLQ kế tiếp sẽ được chuyển sang `orders.quarantine`.

### 6.3. Audit replay trong môi trường thực tế

Log từ tool giúp điều tra, nhưng hệ thống vận hành nên lưu một replay request bền vững:

```sql
CREATE TABLE replay_request (
    replay_batch_id UUID PRIMARY KEY,
    event_id        VARCHAR(64) NOT NULL,
    source_address  VARCHAR(255),
    source_queue    VARCHAR(255),
    requested_by    VARCHAR(160) NOT NULL,
    approval_ref    VARCHAR(160) NOT NULL,
    status          VARCHAR(24) NOT NULL,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);
```

Quy trình thực tế:

1. Operator tạo request với event ID, lý do, người yêu cầu và approval reference; status là `REQUESTED`.
2. Replay tool claim request, kiểm tra event ID vẫn còn trong DLQ và tạo `replayBatchId`.
3. Tool gửi message mới có cùng event ID và batch ID, rồi commit JMS transaction ACK + send.
4. Sau commit, cập nhật audit row thành `COMMITTED`; nếu chuyển quarantine thì dùng status tương ứng.
5. Nếu process chết sau JMS commit nhưng trước khi cập nhật DB, audit row còn `REQUESTED`. Reconciler tìm `replayBatchId` trong message đã replay hoặc đối chiếu DLQ/source để xác định kết quả rồi cập nhật status.

DB audit và JMS transaction không tự atomic với nhau. Nếu cần atomicity giữa hai resource, đánh giá XA/JTA; nếu không, dùng trạng thái request, batch ID và reconciliation như trên để xử lý cửa sổ commit không rõ kết quả. Không đánh dấu `COMMITTED` trước khi JMS commit thành công.

### 6.4. Chạy replay và xác nhận

Sau khi `evt-poison-001` đã xuất hiện trong DLQ và đã điều tra:

```bash
mvn -q exec:java -Dexec.mainClass=lab.retry.DlqInspector
mvn -q exec:java -Dexec.mainClass=lab.retry.DlqReplay -Dexec.args="evt-poison-001"
mvn -q exec:java -Dexec.mainClass=lab.retry.OrderConsumer
```

Kết quả mong đợi:

- DLQ giảm một message sau replay commit.
- Queue `orders` nhận message mới có cùng `eventId`, `replayCount=1` và `replayBatchId`.
- Consumer xử lý và commit message sau khi lỗi giả lập đã được sửa.
- Nếu replayed message vẫn lỗi, message quay về DLQ với `replayCount=1`; lần replay tiếp theo sẽ đi `orders.quarantine`, không tiếp tục vòng lặp.

Không chạy nhiều ReplayTool song song trong lab. Production replay cần batch size, rate limit, lock/claim hoặc cơ chế phân công để hai operator không phát lại cùng message đồng thời.

## 7. Bảo vệ side effect bằng idempotency

### 7.1. Delivery retry và replay đều có thể tạo duplicate

Có hai loại lặp:

- **Redelivery:** broker giao lại cùng message sau rollback hoặc session/connection failure. Broker giữ delivery state và tăng delivery count.
- **Replay:** operator/tool tạo một message mới từ DLQ. Provider cấp `JMSMessageID` mới và delivery count bắt đầu lại; logical `eventId` vẫn phải giữ nguyên.

Vì vậy không dùng `JMSMessageID` hoặc `JMSXDeliveryCount` làm khóa chống duplicate nghiệp vụ. Dùng `eventId` ổn định và unique constraint trong inbox.

### 7.2. Inbox table mẫu

Ví dụ PostgreSQL:

```sql
CREATE TABLE consumed_event (
    event_id       VARCHAR(64) PRIMARY KEY,
    event_type     VARCHAR(120) NOT NULL,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at   TIMESTAMPTZ
);
```

Consumer mở DB transaction, insert event ID rồi mới áp dụng business update:

```sql
INSERT INTO consumed_event(event_id, event_type)
VALUES (:eventId, :eventType)
ON CONFLICT (event_id) DO NOTHING;
```

- Nếu insert tạo một row mới, thực hiện business side effect trong cùng DB transaction rồi commit DB.
- Nếu row đã tồn tại, đây là duplicate delivery/replay; bỏ qua side effect và hoàn tất JMS transaction.
- Nếu DB transaction lỗi, rollback DB và JMS session để broker có thể redeliver theo policy.

DB transaction và JMS transaction trong ví dụ là hai resource khác nhau. Commit DB rồi JMS commit thất bại có thể làm message được giao lại; unique key `event_id` giúp lần giao lại không thực hiện side effect lần nữa. Nếu yêu cầu atomic commit giữa DB và broker, cần đánh giá XA/JTA, recovery log và chi phí vận hành; inbox idempotency vẫn hữu ích để xử lý duplicate ngoài dự kiến.

### 7.3. Thứ tự commit quan trọng

| Thứ tự | Sự cố có thể xảy ra | Hậu quả |
|---|---|---|
| JMS commit trước, DB commit sau | Process chết sau ACK nhưng trước DB commit | Message đã mất khỏi queue nhưng side effect chưa được lưu |
| DB commit trước, JMS commit sau | Process chết hoặc commit JMS không rõ kết quả | Message có thể redeliver; inbox nhận ra duplicate |
| DB + JMS XA transaction | Coordinator/recovery phải xử lý cả hai resource | Atomicity tốt hơn nhưng cấu hình và vận hành phức tạp |

Với consumer thông thường, hoàn tất DB transaction idempotent trước rồi mới commit JMS session. Đừng tuyên bố “exactly once” chỉ vì đã bật transacted session; delivery vẫn có thể lặp, còn idempotency bảo vệ kết quả nghiệp vụ.

## 8. Đo lường và kiểm chứng kết quả lab

### 8.1. Metrics cần quan sát

| Metric | Dùng để trả lời |
|---|---|
| `orders.MessageCount` | Còn bao nhiêu message ready ở source queue? |
| `orders.DeliveringCount` | Có bao nhiêu message đang in-flight? |
| `orders.MessagesAdded` | Producer đã thêm bao nhiêu message? |
| `orders.MessagesAcknowledged` | Consumer đã commit/ACK bao nhiêu message? |
| `DLQ.MessageCount` | Bao nhiêu message đang cách ly? |
| `orders.quarantine.MessageCount` | Bao nhiêu message vượt replay budget? |
| Redelivery ratio | Bao nhiêu delivery attempts là redelivery? |
| Oldest message age | Message chờ lâu nhất đã vượt SLA chưa? |
| Replay committed/quarantined | Operator replay bao nhiêu, thành công hay bị quarantine? |

Artemis QueueControl/JMX và management console có thể cung cấp queue counters. Tên attribute/API cụ thể tùy broker version; dùng cùng một nguồn cho các snapshot trước/sau. Với Classic, đọc destination MBeans và BrokerView usage. Không cộng metric active và backup thành hai lần traffic.

### 8.2. Log có thể đối soát

Một log line hữu ích nên có:

```text
timestamp
broker
sourceAddress
sourceQueue
eventId
JMSMessageID
JMSXDeliveryCount
JMSRedelivered
replayCount
replayBatchId
outcome = committed | rolled_back | dead_lettered | replayed | quarantined
failureClass
```

Không log password, token, toàn bộ payload hoặc PII không cần thiết. `JMSMessageID` giúp truy vết một message vật lý; `eventId` liên kết cùng một event qua producer retry, redelivery và replay.

### 8.3. Kết quả mong đợi sau toàn bộ lab

| Thời điểm | `orders` | `DLQ` | `orders.quarantine` |
|---|---:|---:|---:|
| Trước khi gửi | 0 | 0 | 0 |
| Sau producer | 2 | 0 | 0 |
| Sau consumer | 0 | 1 | 0 |
| Sau replay commit và consumer xử lý | 0 | 0 | 0 |

Đây là kết quả kỳ vọng khi chỉ gửi hai message trong lab và không có message cũ. Nếu có queue auto-create, test chạy song song hoặc message tồn từ lần trước, số đếm có thể khác; dùng event ID để đối chiếu thay vì chỉ nhìn tổng count.

## 9. Đối chiếu ActiveMQ Classic

Classic dùng redelivery policy phía client và dead-letter strategy phía broker. Không áp dụng các thuộc tính Artemis `max-delivery-attempts`, `dead-letter-address` hoặc address-settings cho Classic.

Đoạn code Classic bên dưới cần client Jakarta tương ứng với Classic 6.x (artifact `org.apache.activemq:activemq-client-jakarta`) trong một Maven profile riêng. Không đưa client Classic vào cùng ví dụ Artemis rồi trộn các factory; các dòng Classic cũ dùng `javax.jms` cần source/import tương ứng, không tương thích trực tiếp với ứng dụng Spring Boot 3/Jakarta.

### 9.1. RedeliveryPolicy của Classic client

Ví dụ với ActiveMQ Classic Jakarta client tương thích ứng dụng:

```java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.RedeliveryPolicy;

ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://localhost:61616");
RedeliveryPolicy policy = factory.getRedeliveryPolicy();
policy.setInitialRedeliveryDelay(1000L);
policy.setUseExponentialBackOff(true);
policy.setBackOffMultiplier(2.0);
policy.setMaximumRedeliveryDelay(5000L);
policy.setMaximumRedeliveries(3);
```

Trong Classic, `maximumRedeliveries` là số lần redelivery sau lần delivery đầu tiên theo client policy. Khi vượt budget, client gửi poison acknowledgment để broker áp dụng dead-letter strategy. Vì cách đếm khác Artemis, phải xem `JMSXDeliveryCount` và test trên đúng version thay vì copy nguyên con số cấu hình.

### 9.2. Individual Dead Letter Strategy

Fragment trong `activemq.xml`:

```xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue=">">
                <deadLetterStrategy>
                    <individualDeadLetterStrategy
                        queuePrefix="DLQ."
                        useQueueForQueueMessages="true"/>
                </deadLetterStrategy>
            </policyEntry>
        </policyEntries>
    </policyMap>
</destinationPolicy>
```

Với source queue `orders`, individual strategy tạo DLQ tương ứng có prefix, thường là `DLQ.orders`. Provision destination và ACL theo cấu hình broker; không mặc định mọi message luôn vào `ActiveMQ.DLQ` khi đã chọn individual strategy.

Classic replay vẫn cần cùng nguyên tắc: consume DLQ và send message mới trong cùng transacted session khi provider/broker hỗ trợ cùng transaction; giữ logical event ID, giới hạn replay, ghi audit và idempotency ở consumer. Tên DLQ, client API và management metrics phải được xác minh theo Classic version đang chạy.

## 10. Bài tập mở rộng

**Bài 1 — Backoff:** đổi `redelivery-delay` thành 500 ms, multiplier 3 và max 4 giây. Ghi timestamp từng delivery; so sánh delay thực tế với delay cấu hình.

**Bài 2 — Budget:** gửi ba message có `failUntil=0`, `2`, `99`. Dự đoán số lần rollback và trạng thái cuối trước khi chạy; đối chiếu `JMSXDeliveryCount`, source queue và DLQ.

**Bài 3 — Replay cap:** replay poison message một lần sau đó cố ý để nó fail tiếp. Chứng minh lần tiếp theo đi quarantine và không tạo replay loop.

**Bài 4 — Duplicate event:** gửi hai message vật lý có cùng `eventId`, khác `JMSMessageID`. Dùng inbox unique key để chứng minh business side effect chỉ xảy ra một lần.

**Bài 5 — Crash window:** mô phỏng exception sau khi replay tool send message nhưng trước `session.commit()`. Xác nhận rollback giữ message ở DLQ và không để message mới ở source queue. Sau đó bỏ exception và chạy lại.

**Bài 6 — Nguồn gốc:** gửi poison message từ hai source queue có address settings khác nhau. Browse DLQ, phân loại bằng `_AMQ_ORIG_ADDRESS`/`_AMQ_ORIG_QUEUE` và ghi nhận khác biệt với Classic.

**Bài 7 — Replay có phê duyệt:** xây một bảng audit gồm eventId, source, reason, operator, approval, replayBatchId, replayCount, timestamp và kết quả. Không replay nếu chưa có reason và owner.

## 11. Checklist nghiệm thu

- [ ] Broker Artemis lab có source queue, DLQ và quarantine queue được provision đúng.
- [ ] Producer gửi persistent message với eventId ổn định và properties đúng kiểu.
- [ ] Consumer dùng transacted session; lỗi xử lý dẫn tới rollback.
- [ ] Redelivery delay/backoff có hiệu lực và delivery attempts bị giới hạn.
- [ ] Poison message được chuyển vào DLQ; source queue không giữ message đó vô hạn.
- [ ] Có thể browse DLQ mà không remove message và xác định source/event ID.
- [ ] Replay giữ eventId, tạo replayBatchId, tăng replayCount và không copy provider delivery metadata.
- [ ] ACK DLQ và send source/quarantine nằm trong cùng JMS transaction.
- [ ] Message vượt replay cap đi quarantine thay vì tạo vòng lặp.
- [ ] Inbox/idempotency bảo vệ business side effect khi delivery/replay trùng.
- [ ] Dashboard/log đối soát được source, DLQ, quarantine, redelivery và replay outcomes.
- [ ] Hiểu khác biệt giữa Artemis address settings và Classic RedeliveryPolicy/DeadLetterStrategy.

**Kết luận:** retry là cơ hội xử lý lại lỗi tạm thời trong delivery budget; DLQ là điểm cách ly khi message không thể tiếp tục retry; replay là quyết định vận hành tạo một message mới sau khi đã điều tra và sửa nguyên nhân. Kết hợp transacted session, backoff, DLQ metadata, replay cap, audit và inbox idempotency giúp luồng xử lý phục hồi được mà không biến lỗi đơn lẻ thành retry storm hoặc side effect trùng lặp.
