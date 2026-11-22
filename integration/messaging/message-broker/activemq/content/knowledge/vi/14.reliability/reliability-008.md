# Xử lý kết quả commit không xác định khi kết nối đứt

## 1. Lỗi mạng có thể làm mất phản hồi, dù transaction đã commit

Trong hệ thống JMS dùng Apache ActiveMQ Classic hoặc Artemis, một producer gọi **Session.commit()** để kết thúc transaction gửi **OrderPaid**. Broker có thể đã nhận và commit message nhưng kết nối đứt trước khi phản hồi thành công tới client. Client thấy exception hoặc timeout và **không biết commit đã xảy ra hay chưa**.

Đó là **ambiguous commit outcome**, tức **kết quả commit không xác định** tại phía gọi. Hai trạng thái thật của broker có thể là **COMMITTED** hoặc **NOT COMMITTED**, nhưng client chỉ quan sát **UNKNOWN**. Không được đồng nhất exception với rollback.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as JMS producer
    participant B as ActiveMQ broker
    participant J as Broker journal
    P->>B: send(OrderPaid) trong Session transacted
    P->>B: commit()
    B->>J: Ghi nhận commit
    J-->>B: Commit hoàn tất
    B--xP: Phản hồi commit thất lạc
    Note over P: Exception/timeout: outcome UNKNOWN
    Note over B: Message có thể đã có trong queue
~~~

Nếu **retry bằng message mới**, cùng sự kiện nghiệp vụ có thể xuất hiện hai lần. Nếu bỏ event vì cho rằng nó đã gửi, có thể mất event vĩnh viễn khi broker thực tế chưa commit. Bài này thuộc chương **Độ tin cậy** của module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**, tập trung vào cách xử lý kết quả commit không rõ ràng ở **producer**, **consumer**, database và đường khôi phục sau đứt kết nối.

### Các mốc cần phân biệt

~~~text
T0  Nghiệp vụ phát sinh, eventId được lưu
T1  Tạo JMS Session transacted
T2  Gọi send()
T3  Gọi commit()
T4  Broker quyết định/ghi nhận kết quả transaction
T5  Client nhận phản hồi commit thành công
~~~

| Mốc đứt kết nối | Kiến thức client thực sự có | Hành động đúng |
| --- | --- | --- |
| Trước khi gửi | Chưa có kết quả gửi | Giữ event ở nguồn bền vững để thử lại |
| Đang gửi hoặc sau send, trước commit | Chưa có commit được xác nhận | Đóng phiên lỗi; thử lại bằng cùng eventId |
| Trong commit, trước phản hồi | **UNKNOWN**: có thể đã commit | Retry idempotent; không đánh dấu chắc chắn thất bại |
| Broker commit nhưng response thất lạc | Broker đã commit, client vẫn UNKNOWN | Phải chịu được gửi lặp nếu retry |
| Commit trả về thành công | JMS provider đã xác nhận transaction theo hợp đồng | Có thể đánh dấu phát thành công; vẫn chưa chứng minh consumer xử lý |

Trong sự cố thực, không thể xác định T4 chỉ bằng exception. **Connection tự reconnect thành công** không trả lời được transaction trước đã commit hay chưa. **Queue depth = 0** cũng không chứng minh message chưa được gửi: message có thể đã ACK, in-flight, expired, chuyển DLQ hoặc route sang subscription.

Vì vậy, khi **commit() ném lỗi do đường truyền**, không gọi **rollback()** rồi tuyên bố transaction đã được hoàn tác. Rollback không đảo ngược một commit broker đã hoàn tất. Session/Connection lỗi nên được đóng hoặc bỏ theo contract client; việc thử lại phải dựa trên **bản ghi nghiệp vụ bền vững**.

## 2. Phân biệt kết quả kỹ thuật và kết quả nghiệp vụ

Có ba điều khác nhau:

| Kết quả | Ý nghĩa |
| --- | --- |
| **JMS send/commit thành công** | Broker/provider xác nhận transaction gửi |
| **Consumer JMS ACK/commit thành công** | Broker/provider xác nhận transaction nhận |
| **Business effect đã commit** | Database hoặc dịch vụ ngoài đã thực hiện nghiệp vụ |

JMS local transaction không bao trùm JDBC transaction hay HTTP API. Producer có thể thấy commit UNKNOWN dù broker đã nhận message; consumer có thể commit database thành công nhưng JMS commit UNKNOWN; cả hai đều tạo rủi ro phát/nhận trùng.

**JMSMessageID** do provider cấp cho một JMS message; producer retry bằng một JMS message mới có thể nhận JMSMessageID khác. **JMSRedelivered** chỉ mô tả trạng thái delivery của provider; lần gửi trùng từ producer có thể có JMSRedelivered=false. Vì thế phải có **eventId nghiệp vụ ổn định** được giữ nguyên ở mọi lần thử.

Ví dụ:

~~~json
{
  "eventId": "payment-ORD-932-v1",
  "eventType": "OrderPaid",
  "orderId": "ORD-932",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T10:15:00Z"
}
~~~

| Khóa | Sinh ở đâu | Vai trò |
| --- | --- | --- |
| eventId | Producer trước lần gửi đầu | Nhận diện cùng một sự kiện qua retry, inbox, reconciliation |
| JMSMessageID | JMS provider khi gửi | Theo dõi từng JMS message; không phải business id |
| JMSCorrelationID | Ứng dụng | Liên kết workflow/request nếu cần |
| Artemis duplicate ID | Producer gắn property riêng của Artemis | Giảm gửi trùng trong phạm vi cache broker |

**Không sinh UUID mới khi retry cùng event**. Định danh mới sẽ khiến downstream tưởng đó là nghiệp vụ mới.

## 3. Transactional outbox giúp producer retry mà không mất sự kiện

Nếu Order Service ghi đơn hàng vào database rồi gửi JMS, hai commit thuộc hai hệ thống độc lập. Đặt **order update và outbox event vào cùng một DB transaction**, sau đó có relay phát JMS theo eventId của outbox.

~~~mermaid
flowchart LR
    O[Order Service] --> TX[DB transaction]
    TX --> ORD[(orders)]
    TX --> OUT[(outbox_events)]
    OUT --> R[Relay đọc và retry]
    R -->|send + JMS commit| MQ[(ActiveMQ)]
    MQ --> C[Consumer idempotent]
~~~

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(120) PRIMARY KEY,
    destination VARCHAR(120) NOT NULL,
    payload TEXT NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Giao dịch nghiệp vụ:

~~~text
BEGIN DB TRANSACTION
  UPDATE orders SET status = 'PAID' WHERE order_id = :orderId
  INSERT INTO outbox_events(event_id, destination, payload, state)
  VALUES (:stableEventId, 'orders.in', :payload, 'PENDING')
COMMIT DB TRANSACTION
~~~

Relay dùng trạng thái **PENDING**, **IN_FLIGHT** và **SENT**; có thể thêm **UNCERTAIN** để theo dõi một commit lỗi. Quan trọng nhất: **chỉ đánh dấu SENT sau khi JMS commit được xác nhận**. Khi không rõ kết quả, vẫn giữ event trong outbox để retry cùng eventId.

~~~text
claim outbox row với lease/lock
  tạo Session transacted
  send message với eventId ổn định
  commit JMS
  nếu commit được xác nhận:
      mark outbox SENT
  nếu kết quả commit UNKNOWN:
      giữ outbox chờ retry/đối soát
release lease
~~~

| Điểm relay chết | Outbox | Broker | Phục hồi |
| --- | --- | --- | --- |
| Trước send | Chưa SENT | Có thể chưa nhận | Retry |
| Trong JMS commit | Chưa SENT | **UNKNOWN** | Retry cùng eventId |
| JMS commit xong, chưa update outbox | Chưa SENT | Message có thể đang ở broker/đã được consume | Retry cùng eventId; consumer dedup |
| Update SENT thành công | SENT | JMS provider đã xác nhận gửi | Dừng retry outbox trong đường chuẩn |

**Outbox không làm DB và JMS thành một transaction nguyên tử.** Nó biến khoảng hở thành tình huống có thể retry an toàn. Cần thêm **consumer inbox/idempotency** vì relay có thể gửi trùng, dù triển khai outbox đúng.

Để tránh relay chết giữ hàng vĩnh viễn, dùng lease hết hạn và batch claim như **SELECT ... FOR UPDATE SKIP LOCKED** nếu phù hợp; retry có **backoff với jitter**, giới hạn đồng thời và cảnh báo tuổi outbox. Không tạo vòng lặp gửi nóng.

## 4. Artemis duplicate detection là lớp giảm trùng có giới hạn

Artemis cho phép producer gắn property provider-specific **_AMQ_DUPL_ID**, dùng một ID cố định cho cùng bản phát lại. Broker có thể sử dụng cache để nhận ra duplicate message cùng phạm vi address theo quy tắc của nó:

~~~java
TextMessage msg = context.createTextMessage(payload);
msg.setStringProperty("eventId", stableEventId);
msg.setStringProperty("_AMQ_DUPL_ID", stableEventId);
~~~

Ví dụ các tùy chọn cache ở cấu hình **broker.xml** Artemis (ghép đúng vào cấu trúc broker đang chạy):

~~~xml
<id-cache-size>20000</id-cache-size>
<persist-id-cache>true</persist-id-cache>
~~~

Cache có giới hạn dung lượng, cấu hình persistence và phạm vi address/topology. Một event phát lại sau khi ID bị loại khỏi cache **có thể không được broker nhận ra là trùng**. Duplicate detection cũng không chứng minh consumer đã commit nghiệp vụ.

Property **_AMQ_DUPL_ID** là extension của Artemis, không phải JMS portable; không giả định ActiveMQ Classic dùng y hệt. Với Classic, các cơ chế audit/producer sequence riêng cũng không thay thế **eventId + idempotent consumer**.

## 5. Java producer: không đánh đồng JMS commit exception với rollback

Ví dụ này dùng **Jakarta Messaging** với **org.apache.activemq:artemis-jakarta-client** phù hợp phiên bản broker. Trên Maven, một dependency tham chiếu có dạng:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.42.0</version>
</dependency>
~~~

Đặt **eventId** từ bản ghi outbox bền vững; code chỉ minh họa **một lần phát** và trả về trạng thái. Chỗ quản lý outbox DB do relay thực hiện.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class CommitAwarePublisher {
    enum Outcome { CONFIRMED, UNKNOWN }

    public static Outcome publish(
            ActiveMQConnectionFactory factory,
            String user, String password,
            String stableEventId, String orderId) {

        try (JMSContext jms = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = jms.createQueue("orders.in");
            TextMessage msg =
                    jms.createTextMessage("OrderPaid:" + orderId);
            msg.setStringProperty("eventId", stableEventId);
            msg.setStringProperty("orderId", orderId);
            msg.setStringProperty("eventType", "OrderPaid");

            // Artemis-only, optional broker duplicate detection.
            msg.setStringProperty("_AMQ_DUPL_ID", stableEventId);

            jms.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(queue, msg);

            jms.commit(); // Có thể đã commit dù client nhận exception.
            return Outcome.CONFIRMED;
        } catch (Exception failure) {
            System.err.println("JMS outcome UNKNOWN eventId="
                    + stableEventId + ": " + failure.getMessage());
            return Outcome.UNKNOWN;
        }
    }
}
~~~

Gọi hàm với một **stableEventId lấy lại từ outbox mỗi lần retry**:

~~~java
ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61617");

CommitAwarePublisher.Outcome result =
        CommitAwarePublisher.publish(
                factory, brokerUser, brokerPassword,
                "payment-ORD-932-v1", "ORD-932");
~~~

- **CONFIRMED**: lời gọi commit trả về thành công; relay có thể cập nhật outbox SENT.
- **UNKNOWN**: không tự mark SENT. Retry bằng cùng eventId trong ngữ cảnh JMS mới, có backoff và theo dõi.
- Một số lỗi ở bước trước commit chắc chắn chưa gửi; ví dụ cố ý trả UNKNOWN cho mọi exception để **không đánh dấu SENT sai**. Hệ thống production có thể phân loại lỗi chi tiết hơn, nhưng không được đoán khi có lỗi đường truyền ở commit.
- **Không dùng rollback trên session đã lỗi để kết luận transaction không tồn tại ở broker**.

Với ActiveMQ Classic, vẫn dùng **Session transacted + commit()**, nhưng chọn client và package JMS phù hợp (Classic 5.x thường dùng **javax.jms**) và bỏ phần property riêng Artemis. Giải pháp outbox/inbox không phụ thuộc broker nào.


## 6. Consumer: database đã commit nhưng JMS ACK còn UNKNOWN

Consumer cũng có cửa sổ lỗi tương tự. Nó nhận OrderPaid, cập nhật database, rồi **commit JMS Session** để ACK. Nếu DB commit xong nhưng kết nối broker đứt khi JMS commit, có thể xảy ra hai trường hợp:

1. Broker **đã nhận ACK và commit**, nên message không được giao lại.
2. Broker **chưa commit ACK**, nên message có thể được phát lại khi phiên consumer phục hồi.

Ứng dụng **không được undo business effect đã commit** chỉ vì không nhận phản hồi từ JMS. Nếu được giao lại, nó cần nhận diện event đã xử lý và ACK mà không tạo side effect lần nữa.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as ActiveMQ broker
    participant C as Inventory consumer
    participant D as PostgreSQL
    B-->>C: Deliver E1
    C->>D: BEGIN + INSERT inbox + business effect
    D-->>C: DB COMMIT thành công
    C->>B: JMS Session.commit() / ACK
    B--xC: Phản hồi commit bị mất
    Note over C: DB đã commit, kết quả ACK UNKNOWN
    Note over B,C: E1 có thể redeliver hoặc không
~~~

| DB commit | JMS commit | Hành động |
| --- | --- | --- |
| DB rollback chắc chắn | Chưa gọi JMS commit | Rollback JMS nếu Session còn hợp lệ, cho phép redelivery |
| DB commit thành công | JMS commit thành công | Message và nghiệp vụ hoàn tất |
| DB commit thành công | **JMS commit UNKNOWN** | Giữ DB effect; khi redelivery thì dedup và ACK |
| **DB commit UNKNOWN** | Chưa gọi JMS commit | Khôi phục/đối soát DB bằng khóa duy nhất; retry idempotent |
| DB commit thành công | Consumer chết trước JMS commit | Redelivery có thể xảy ra; inbox xử lý an toàn |

Lưu ý: **auto-ack sớm** trước khi commit nghiệp vụ cũng gây lỗi ngược lại: broker xem message đã xử lý trong khi DB chưa có kết quả. Với tác vụ quan trọng cần điều khiển ranh giới, dùng Session transacted hoặc acknowledge mode/frame­work phù hợp và kiểm tra chính xác thứ tự.

## 7. Inbox: bảo vệ side effect ngay cả khi gửi/nhận trùng

Consumer lưu dấu event đã xử lý trong **cùng transaction database** với thay đổi nghiệp vụ. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE inventory_reservations (
    event_id VARCHAR(120) PRIMARY KEY,
    order_id VARCHAR(120) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Mô hình xử lý:

~~~text
BEGIN DB TRANSACTION
  inserted = INSERT processed_events(consumer_name, event_id)
             VALUES ('inventory-service', :eventId)
             ON CONFLICT DO NOTHING

  IF inserted == 1:
      INSERT inventory_reservations(event_id, order_id)
      VALUES (:eventId, :orderId)
      -- Cập nhật tồn kho (nếu có) trong CÙNG DB transaction.
  ELSE:
      bỏ qua side effect vì event đã xử lý
COMMIT DB TRANSACTION

COMMIT JMS SESSION
~~~

Dùng khóa **(consumer_name, event_id)** vì cùng event có thể được xử lý độc lập ở Inventory, Notification và Audit. Nếu một nhóm tiêu thụ thấy bản ghi inbox đã tồn tại, nó chỉ cần xác nhận message mà không chạy lại side effect.

**Bảng processed_events không được commit trước side effect**: nếu side effect thất bại, bản ghi inbox bị lưu trước sẽ làm lần retry bỏ qua nghiệp vụ chưa hoàn tất. Nếu cần gọi API ngoài DB như gửi email hoặc charge payment, một transaction PostgreSQL không thể tự đảm bảo API đó idempotent; dùng **idempotency key tại dịch vụ đích**, outbox tiếp theo hoặc reconciliation riêng.

### Nếu chính DB commit mất phản hồi

DB cũng có kết quả UNKNOWN khi connection đứt sát COMMIT. Khi transaction DB tạo **inbox record và side effect nguyên tử**, retry lại theo **eventId** trên một connection DB mới:

- Transaction cũ đã commit: unique key tồn tại; không tạo side effect thêm.
- Transaction cũ chưa commit: insert có thể thành công và side effect được tạo lần đầu.
- Transaction cũ còn đang xử lý chưa rõ: quản lý timeout/lock và đối soát theo cơ chế DB; không tự suy rằng đã rollback chỉ từ IOException.

Kỹ thuật đúng là làm thao tác **idempotent**, không cố đoán kết quả dựa trên exception.

## 8. Java/JMS + JDBC: đặt DB commit trước JMS commit

Đoạn sau dùng **Artemis Jakarta JMS client**, **PostgreSQL JDBC**, và các bảng ở mục 7. Mục đích là thể hiện rõ lỗi **JMS commit không xác định** sau khi DB đã bền vững; code không chứa framework reconnect, scheduler hoặc logic quản lý DLQ hoàn chỉnh.

Dependency tham chiếu (chọn lại phiên bản tương thích môi trường):

~~~xml
<dependencies>
  <dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.42.0</version>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>42.7.4</version>
  </dependency>
</dependencies>
~~~

**ReliableInventoryConsumer.java**:

~~~java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSRuntimeException;
import jakarta.jms.Message;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;

public final class ReliableInventoryConsumer {
    public static void main(String[] args) throws Exception {
        String brokerUrl = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String brokerUser = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String brokerPassword = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");
        String dbUrl = Objects.requireNonNull(
                System.getenv("DB_URL"), "Missing DB_URL");
        String dbUser = Objects.requireNonNull(
                System.getenv("DB_USER"), "Missing DB_USER");
        String dbPassword = Objects.requireNonNull(
                System.getenv("DB_PASSWORD"), "Missing DB_PASSWORD");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);

        try (JMSContext jms = factory.createContext(
                brokerUser, brokerPassword,
                JMSContext.SESSION_TRANSACTED)) {
            JMSConsumer consumer = jms.createConsumer(
                    jms.createQueue("orders.in"));

            while (!Thread.currentThread().isInterrupted()) {
                Message message = consumer.receive(5000L);
                if (message == null) {
                    continue;
                }

                String eventId;
                try {
                    eventId = required(message, "eventId");
                    String orderId = required(message, "orderId");
                    applyDbOnce(
                            dbUrl, dbUser, dbPassword, eventId, orderId);
                } catch (Exception dbOrBusinessFailure) {
                    System.err.println("DB/business failure: "
                            + dbOrBusinessFailure.getMessage());
                    try {
                        jms.rollback();
                    } catch (JMSRuntimeException rollbackFailure) {
                        System.err.println(
                                "JMS rollback failed; recreate session");
                        break;
                    }
                    continue;
                }

                try {
                    jms.commit(); // ACK sau khi DB bền vững.
                    System.out.println("JMS ACK confirmed " + eventId);
                } catch (JMSRuntimeException commitFailure) {
                    System.err.println("UNKNOWN JMS commit " + eventId
                            + ": " + commitFailure.getMessage());
                    // Không kết luận đã rollback và không thực thi DB lại.
                    break; // Session lỗi; tầng quản lý kết nối khởi tạo lại.
                }
            }
        }
    }

    private static String required(Message msg, String key)
            throws Exception {
        String value = msg.getStringProperty(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing JMS property: " + key);
        }
        return value;
    }

    private static void applyDbOnce(
            String url, String user, String password,
            String eventId, String orderId) throws SQLException {
        try (Connection db = DriverManager.getConnection(
                url, user, password)) {
            db.setAutoCommit(false);
            try {
                int inserted;
                try (PreparedStatement dedup = db.prepareStatement(
                        "INSERT INTO processed_events "
                        + "(consumer_name, event_id) "
                        + "VALUES ('inventory-service', ?) "
                        + "ON CONFLICT DO NOTHING")) {
                    dedup.setString(1, eventId);
                    inserted = dedup.executeUpdate();
                }

                if (inserted == 1) {
                    try (PreparedStatement effect = db.prepareStatement(
                            "INSERT INTO inventory_reservations "
                            + "(event_id, order_id) VALUES (?, ?)")) {
                        effect.setString(1, eventId);
                        effect.setString(2, orderId);
                        effect.executeUpdate();
                    }
                    System.out.println("New business effect " + eventId);
                } else {
                    System.out.println("Already processed " + eventId);
                }
                db.commit();
            } catch (SQLException dbFailure) {
                try {
                    db.rollback();
                } catch (SQLException rollbackFailure) {
                    dbFailure.addSuppressed(rollbackFailure);
                }
                // DB commit có thể vẫn là UNKNOWN, nhưng unique key
                // cho phép lần retry tiếp theo không lặp side effect.
                throw dbFailure;
            }
        }
    }
}
~~~

Producer cần gắn **orderId** như một JMS property:

~~~java
message.setStringProperty("orderId", orderId);
~~~

Trong môi trường lab, tạo hai bảng PostgreSQL, cấu hình **BROKER_URL/BROKER_USER/BROKER_PASSWORD** và **DB_URL/DB_USER/DB_PASSWORD**, rồi chạy consumer cùng producer đã cấu hình đúng. Để demo thực sự giữ hàng, cần bổ sung cập nhật stock có kiểm tra số lượng trong **cùng DB transaction**; bảng reservation ở đây chỉ mô phỏng một side effect có khóa duy nhất.

**Những ranh giới đã được thể hiện:**

- Transaction DB bao gồm **inbox marker** và **reservation**, vì vậy không thể commit marker mà bỏ sót reservation.
- **jms.commit()** chỉ chạy sau khi DB commit thành công hoặc phát hiện duplicate.
- Khi **jms.commit()** ném lỗi, chương trình không gọi rollback như bằng chứng undo ACK; ngắt phiên JMS không rõ trạng thái và để điều phối khởi động session mới.
- Nếu message được giao lại, bản ghi inbox khiến nó chỉ được ACK, không tạo reservation thứ hai.
- Nếu payload hỏng vĩnh viễn, cần retry bounded và DLQ/quarantine; không rollback vô hạn trong môi trường production.

## 9. Reconnect và failover xử lý kênh, không trả lời kết quả commit cũ

ActiveMQ Classic và Artemis có cơ chế reconnect/failover theo client, transport và cấu hình HA. **Phục hồi được TCP/Connection không đồng nghĩa transaction JMS trước đó đã commit hay rollback**.

| Cơ chế | Giúp giải quyết | Giới hạn |
| --- | --- | --- |
| Reconnect/failover | Tạo lại hoặc khôi phục đường truyền khi broker/connection lỗi | Không có API portable trả lời outcome commit đã mất response |
| Persistent message | Duy trì backlog theo policy/storage | Không đồng nghĩa consumer đã xử lý |
| JMS local transaction | Gom send/receive theo session | Không tự bao trùm JDBC/HTTP |
| Artemis duplicate detection | Giảm bản gửi trùng trong cache broker | Không chứng minh side effect đã xảy ra, cache hữu hạn |
| Outbox | Có thể retry phát event an toàn | Không ngăn phát hai JMS messages |
| Consumer inbox/unique key | Ngăn side effect trùng theo eventId | Không tự bảo đảm event sẽ được producer phát |
| XA/JTA nếu được hỗ trợ | Điều phối commit nhiều resource | Có thể phát sinh transaction in-doubt và cần recovery |

**Artemis:** transaction trong lúc failover có thể bị rollback hoặc khiến client báo lỗi theo tình trạng HA/storage/provider. Nếu lỗi xảy ra ngay cửa sổ commit, vẫn phải chịu được outcome chưa rõ.

**Classic:** failover transport có các cơ chế theo dõi/replay trong cấu hình phù hợp, nhưng không phải giấy bảo đảm exactly-once business processing. Các thuộc tính Artemis duplicate detection không nên được copy sang Classic.

### XA/2PC có tránh mọi kết quả UNKNOWN không?

Một transaction manager XA/JTA có thể điều phối JMS và database nếu **cả hai resource cùng hỗ trợ và được cấu hình đúng**. Nhưng khi coordinator/participant bị mất kết nối trong prepare/commit, hệ thống có thể có **in-doubt transaction** cần log recovery và thao tác resolve. XA phức tạp hơn local transaction, phải đánh giá về tính sẵn sàng, hỗ trợ provider và chi phí vận hành. Outbox/inbox thường đủ cho nhiều luồng message bất đồng bộ, nhưng quyết định cuối phải dựa vào yêu cầu nghiệp vụ.

## 10. Đối soát khi commit UNKNOWN

Khi outbox event E1 ở trạng thái UNCERTAIN, việc không tìm thấy JMSMessageID trên queue **không phải bằng chứng không commit**. Message có thể đã ACK, in-flight, expired, DLQ hoặc được route tới subscription khác.

Quy trình đối soát theo **eventId**:

1. **Producer:** xác định outbox event, payload, destination, attempts và thời gian xảy ra lỗi.
2. **Broker:** kiểm tra log, tình trạng queue/subscription, DLQ/expiry và duplicate detection nếu được instrument; coi đây là bằng chứng hỗ trợ.
3. **Consumer:** truy vấn inbox **(consumerName, eventId)** cùng side effect đã commit, ghi nhận dịch vụ nào xử lý xong.
4. **Quyết định:** consumer đã xử lý thì không chạy lại side effect; chưa có thì kiểm tra backlog/DLQ và retry phát bằng cùng eventId nếu cần.
5. **Replay:** đặt giới hạn số lần, giữ eventId/causation metadata, quan sát kết quả; escalate khi quá SLA hoặc có xung đột dữ liệu.

| Quan sát | Không được suy luận |
| --- | --- |
| Queue depth bằng 0 | Chắc chắn event chưa gửi hoặc đã xử lý đúng |
| Một JMSMessageID không còn trên queue | Chắc chắn broker đã rollback transaction |
| EventId có trong inbox của Inventory | Audit và Notification đã xử lý |
| Outbox marked SENT | Mọi consumer đã hoàn tất |
| JMSRedelivered=false | Sự kiện nghiệp vụ này chưa bao giờ được gửi trước đó |
| Commit exception | Broker chắc chắn chưa có message |

Trong hệ thống nhiều consumer group, dedup key phải có **consumerName** để việc Inventory ACK không chặn Audit hay Notification nhận cùng event.

## 11. Thí nghiệm fault injection đúng cửa sổ lỗi

Thử **tắt broker trước khi send** chỉ kiểm tra khả năng reconnect; nó không tái hiện trường hợp **broker đã commit nhưng phản hồi thất lạc**. Cần kiểm tra nhiều điểm đứt:

| Kịch bản | Cách kiểm tra | Tiêu chí |
| --- | --- | --- |
| Broker down trước send | Dừng broker trước khi relay phát | Outbox giữ event, relay retry sau khi broker quay lại |
| Mất kết nối khi producer commit | Dùng network proxy/fault injection chặn đúng cửa sổ commit | Relay ghi UNKNOWN; retry với cùng eventId |
| JMS commit thành công, relay chết trước mark SENT | Cố ý ném lỗi sau khi commit được xác nhận, trước cập nhật outbox | Lần retry không tạo side effect thứ hai |
| Consumer chết trước DB commit | Tiêm exception trong DB transaction | DB rollback; broker có thể redeliver |
| Consumer chết sau DB commit, trước JMS commit | Chặn process ở ranh giới hai commit | Inbox ngăn reservation trùng |
| JMS commit response thất lạc sau DB commit | Proxy cắt đường truyền sát ACK commit | Consumer chấp nhận UNKNOWN, reconnect, dedup |
| DB commit phản hồi thất lạc | Cắt kết nối DB sát COMMIT | Unique constraint làm retry idempotent |
| Broker restart khi có in-flight | Restart có kiểm soát và giữ storage | Không tạo side effect trùng sau redelivery |

**Lưu ý quan trọng:** cắt TCP không bảo đảm mỗi lần thử đều rơi đúng cửa sổ broker **đã commit nhưng chưa gửi phản hồi**. Cần ghi trace phía broker, proxy, producer và consumer rồi đánh giá cả hai nhánh **COMMITTED** và **NOT COMMITTED**. Không suy một exception đơn lẻ chứng minh nhánh nào.

### Thử nghiệm dễ tái lập khi chưa có network proxy

1. Ghi outbox event với eventId cố định **payment-ORD-932-v1**.
2. Producer gửi và nhận **JMS commit thành công**.
3. Cố ý bỏ qua thao tác **mark outbox SENT**, mô phỏng relay chết trước khi ghi nhận.
4. Cho relay thử phát lại cùng eventId.
5. Nếu duplicate detection cache hoạt động, broker có thể lọc bản gửi trùng; dù không, **inbox phải bảo đảm đúng một reservation**.
6. Kiểm tra unique constraint và số row side effect; không chỉ đếm queue message.

Kịch bản này kiểm chứng nhánh **broker có commit nhưng producer không lưu được kết quả**. Nó bổ sung cho, chứ không thay thế, fault injection trực tiếp lên commit response.

### Tín hiệu cần ghi lại

~~~text
eventId=payment-ORD-932-v1
producerAttempt=3
jmsCommitOutcome=UNKNOWN
brokerDestination=orders.in
consumerName=inventory-service
dbEffect=ALREADY_PROCESSED
jmsAckOutcome=CONFIRMED
~~~

Nên theo dõi **outbox oldest age**, số event UNCERTAIN, JMS commit failures, reconnect/failover, DLQ, redelivery, inbox duplicate-hit rate, processing latency và event quá SLA. Không đưa mật khẩu hoặc payload nhạy cảm vào log.

## 12. Những cách xử lý sai cần tránh

| Cách xử lý | Lỗi căn bản | Phương án an toàn |
| --- | --- | --- |
| Catch commit exception rồi báo chắc chắn rollback | Broker có thể đã commit | Kết quả UNKNOWN |
| Bỏ event khi commit lỗi để tránh duplicate | Có thể mất event | Outbox retry cùng eventId |
| Sinh eventId mới sau mỗi retry | Consumer không dedup được | ID ổn định từ lần đầu |
| Gọi rollback sau commit exception và tuyên bố đã undo | Rollback không hủy commit đã hoàn tất | Bỏ phiên lỗi, retry/reconcile |
| Dựa vào JMSRedelivered để chặn duplicate | Producer resend có thể là JMS message mới | Inbox theo eventId |
| Chỉ dựa vào Artemis cache duplicate ID | Cache hữu hạn, không portable | Consumer idempotency |
| Mark outbox SENT trước JMS commit | Relay chết khiến event không được phát | Mark sau commit được xác nhận |
| Thấy queue trống rồi tự resend với ID mới | Queue trống không chứng minh outcome | Đối soát eventId và retry an toàn |
| Dùng cùng Session đã hỏng để retry commit | Trạng thái transaction không còn đáng tin | Phiên JMS mới theo provider contract |
| Dùng transaction JMS để suy DB đã commit | Hai transaction độc lập | Outbox/inbox hoặc XA đúng điều kiện |
| Rollback vô hạn khi payload sai | Poison message làm nghẽn hệ thống | Bounded retry, DLQ/quarantine |

## 13. Câu hỏi kiểm chứng một thiết kế chịu được UNKNOWN

| Câu hỏi | Cần chứng minh bằng test hoặc thiết kế |
| --- | --- |
| Producer không biết JMS commit thành công? | Event còn trong outbox; có thể retry cùng eventId |
| Relay chết sau JMS commit, trước mark SENT? | Retry không tạo tác dụng nghiệp vụ trùng |
| DB đã commit, consumer mất ACK JMS? | Có thể redeliver nhưng không lặp side effect |
| DB commit cũng trả lỗi mạng? | Unique key và transaction giúp retry/đối soát |
| Broker duplicate cache đã mất ID? | Consumer inbox vẫn bảo vệ kết quả |
| Message đang ở DLQ? | Có quy trình sửa/replay giữ eventId gốc |
| Nhiều nhóm subscriber cùng nhận event? | Inbox theo (consumerName, eventId) |
| Side effect qua HTTP hoặc cổng thanh toán? | Dịch vụ đích có idempotency key/reconciliation |
| Reconnect thành công? | Không tự kết luận outcome commit cũ |
| Metrics queue trống? | Không dùng như bằng chứng đã hoàn thành nghiệp vụ |

**Kết quả commit không xác định là trạng thái tri thức của client, không phải một trạng thái rollback của broker.** Trong ActiveMQ Classic và Artemis, cách xây dựng luồng đáng tin cậy là giữ sự kiện trong **outbox**, retry với **eventId ổn định**, để consumer xử lý **idempotent trong transaction DB** trước khi **commit JMS**, và có đối soát khi dữ liệu lâu không hội tụ. Cấu hình failover, persistence, DLQ và duplicate detection hỗ trợ khả năng phục hồi, còn **ranh giới transaction và khóa nghiệp vụ** giúp hệ thống giữ kết quả đúng ngay cả khi phản hồi commit bị mất.
