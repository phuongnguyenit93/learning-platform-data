# Giao dịch nhận–xử lý–gửi tiếp trong cùng JMS Session

> **Chương:** Xác nhận và giao dịch  
> **Bối cảnh:** Ứng dụng Java đọc message từ queue đầu vào trên ActiveMQ Classic hoặc Artemis, biến đổi nội dung, rồi gửi sang queue tiếp theo. Mục tiêu là bảo đảm **không có trạng thái "đã nhận nhưng chưa gửi" hoặc "đã gửi nhưng chưa xác nhận đầu vào"** khi công việc chỉ bao gồm các thao tác JMS thuộc **cùng một local transaction**. Ví dụ sử dụng Java 17, `jakarta.jms` và broker có persistence.

## 1. Bất biến cần đạt

Giả sử pipeline tiếp nhận đơn hàng:

```text
orders.received  ──▶  [Java validation worker]  ──▶  orders.validated
                               │
                               └──▶ orders.rejected (dữ liệu không hợp lệ)
```

Với mỗi message nguồn, kết quả đúng là **một trong hai trạng thái**:

1. **Commit:** message nguồn được xác nhận tiêu thụ, và message kết quả được gửi vào queue đích trong cùng giao dịch.
2. **Rollback:** message nguồn chưa bị xác nhận tiêu thụ, có thể được phân phối lại; mọi message đầu ra của giao dịch đó **không được phát hành**.

Nếu xử lý được xác định là **không hợp lệ vĩnh viễn** (ví dụ nội dung trống), worker có thể gửi một bản ghi kết quả sang `orders.rejected` **rồi commit**. Đó là quyết định nghiệp vụ có chủ đích, khác với rollback khi hệ thống gặp lỗi tạm thời.

| Kết quả của transaction | `orders.received` | `orders.validated` hoặc `orders.rejected` |
|---|---|---|
| `commit()` thành công | Input được acknowledge/loại khỏi trạng thái chờ xử lý | Output tương ứng được phát hành |
| `rollback()` thành công | Input được khôi phục để redelivery, theo chính sách broker | Output đã gửi trong transaction bị hủy |
| Worker chết trước commit, transaction chưa commit | Broker phục hồi input khi connection/session mất | Không có output của transaction chưa commit |
| Mất kết nối **trong khi** commit | **Chưa thể kết luận** chỉ từ phía client | **Chưa thể kết luận**; cần đối soát |

**Giới hạn:** tính nguyên tử của JMS local transaction chỉ bao phủ các thao tác gửi/nhận thuộc **một `Session`** do một provider/broker quản lý. Nó không tự bao phủ `UPDATE` trong PostgreSQL, gọi REST API hay gửi qua hai `ConnectionFactory` độc lập.

## 2. Cơ chế: một Session chứa cả phía nhận và phía gửi

Theo Jakarta Messaging, transacted Session nhóm **message đã nhận** và **message đã gửi** thành một đơn vị công việc nguyên tử. Broker chưa coi message nguồn là đã được acknowledge hoàn tất và chưa cho bên khác nhận output cho đến khi transaction commit. `commit()` hoặc `rollback()` kết thúc transaction hiện tại và **tự động bắt đầu transaction tiếp theo** trên Session.

```text
JMS Connection
└── Session(SESSION_TRANSACTED) ── TX #41
    ├── MessageConsumer.receive(orders.received)
    │   └── input = order-981
    ├── xử lý/kiểm tra (tính toán cục bộ, không side effect ngoài)
    ├── MessageProducer.send(orders.validated, normalized-order-981)
    └── session.commit()
         ├── ACK input order-981
         └── phát hành output normalized-order-981
              ↓
         TX #42 bắt đầu tự động
```

Điểm quan trọng không phải **chung Connection** mà là **chung Session**. Mỗi Session có transaction độc lập ngay cả khi tạo từ cùng Connection:

```java
// KHÔNG NGUYÊN TỬ nếu sử dụng hai session giao dịch riêng.
Session inputSession  = connection.createSession(Session.SESSION_TRANSACTED);
Session outputSession = connection.createSession(Session.SESSION_TRANSACTED);

// inputSession nhận input; outputSession gửi output.
// outputSession.commit() và inputSession.commit() là HAI bước riêng.
// Nếu tiến trình chết giữa hai bước, một phía đã commit, phía kia chưa.
```

Tương tự, hai `JMSContext` được tạo độc lập bằng `createContext(SESSION_TRANSACTED)` **không** chia sẻ một transaction. Khi muốn nhận–xử lý–gửi tiếp nguyên tử, mọi `MessageConsumer` và `MessageProducer` liên quan phải được tạo từ **một Session đang transacted**.

### Vai trò của các API

| API | Hành vi trong transacted Session |
|---|---|
| `connection.createSession(Session.SESSION_TRANSACTED)` | Tạo local transaction; thay thế cách viết cũ `createSession(true, Session.SESSION_TRANSACTED)` |
| `session.createConsumer(input)` và `session.createProducer(output)` | Cùng Session ⇒ cùng transaction |
| `consumer.receive(...)` | Đưa message nhận vào tập input chưa commit |
| `producer.send(message)` | Đưa message vào tập output của transaction; **send return không có nghĩa output đã được commit** |
| `session.commit()` | Xác nhận input và phát hành output nguyên tử theo hợp đồng provider |
| `session.rollback()` | Hoàn nguyên việc nhận và loại bỏ các send chưa commit |
| `message.acknowledge()` | Không dùng để thay thế commit của transacted Session |
| `session.close()` khi còn transaction chưa commit | Provider phải rollback transaction đang mở |

Trong Java SE, chế độ `SESSION_TRANSACTED` khiến tham số acknowledgment kiểu `AUTO_ACKNOWLEDGE` hay `CLIENT_ACKNOWLEDGE` không còn quyết định việc xác nhận input: **chính transaction commit** quyết định.

## 3. Mã Java: một local transaction cho cả pipeline

Ví dụ dùng một `ConnectionFactory` cung cấp từ phần wiring. Thân worker không gọi lớp của Classic/Artemis, chỉ dùng `jakarta.jms`. Chương trình xử lý **một message mỗi transaction**, giúp dễ đối soát và hạn chế thời gian giữ message chưa commit.

### 3.1. Worker hoàn chỉnh

**`ReceiveProcessForward.java`:**

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import jakarta.jms.TransactionRolledBackException;

import java.util.Locale;

public final class ReceiveProcessForward {
    public enum Outcome { NO_MESSAGE, FORWARDED, REJECTED }

    // Commit có thể đã xảy ra ở broker dù client không nhận được phản hồi.
    public static final class CommitInDoubtException extends RuntimeException {
        public CommitInDoubtException(String messageId, JMSException cause) {
            super("Commit outcome unknown; sourceMessageId=" + messageId, cause);
        }
    }

    private ReceiveProcessForward() {}

    public static Outcome processOne(
            ConnectionFactory factory,
            String user,
            String password,
            boolean injectFailureBeforeCommit) throws JMSException {

        try (Connection connection = factory.createConnection(user, password);
             Session session = connection.createSession(Session.SESSION_TRANSACTED)) {

            Queue input = session.createQueue("orders.received");
            Queue validated = session.createQueue("orders.validated");
            Queue rejected = session.createQueue("orders.rejected");

            // TẤT CẢ producer/consumer dùng chung một transacted Session.
            try (MessageConsumer consumer = session.createConsumer(input);
                 MessageProducer validProducer = session.createProducer(validated);
                 MessageProducer rejectProducer = session.createProducer(rejected)) {

                validProducer.setDeliveryMode(DeliveryMode.PERSISTENT);
                rejectProducer.setDeliveryMode(DeliveryMode.PERSISTENT);
                connection.start(); // Cần cho receive() của JMS API truyền thống.

                Message received = consumer.receive(3000);
                if (received == null) {
                    return Outcome.NO_MESSAGE;
                    // Không có send/receive nào cần commit; close sẽ cleanup.
                }

                String sourceId = received.getJMSMessageID();
                Outcome outcome;
                try {
                    String raw = received instanceof TextMessage
                            ? ((TextMessage) received).getText() : null;

                    if (raw == null || raw.isBlank()) {
                        // Lỗi dữ liệu vĩnh viễn: gửi kết quả từ chối và COMMIT
                        // để không bị rollback rồi lặp vô hạn.
                        TextMessage rejection = session.createTextMessage(
                            "Invalid order payload: empty or not TextMessage");
                        rejection.setStringProperty("sourceMessageId",
                            sourceId == null ? "unknown" : sourceId);
                        rejectProducer.send(rejection);
                        outcome = Outcome.REJECTED;
                    } else {
                        // Phép biến đổi minh họa thuần trong bộ nhớ.
                        String normalized = raw.strip().toUpperCase(Locale.ROOT);
                        TextMessage output = session.createTextMessage(normalized);
                        output.setStringProperty("sourceMessageId",
                            sourceId == null ? "unknown" : sourceId);

                        String orderId = received.getStringProperty("orderId");
                        if (orderId != null) {
                            output.setStringProperty("orderId", orderId);
                        }
                        validProducer.send(output);
                        outcome = Outcome.FORWARDED;
                    }

                    // Fault injection: cố tình fail SAU SEND nhưng TRƯỚC COMMIT.
                    if (injectFailureBeforeCommit) {
                        throw new IllegalStateException("test: fail before commit");
                    }
                } catch (JMSException | RuntimeException processingFailure) {
                    try {
                        session.rollback();
                    } catch (JMSException rollbackFailure) {
                        processingFailure.addSuppressed(rollbackFailure);
                    }
                    throw processingFailure;
                }

                // Cố ý đặt commit NGOÀI catch của lỗi xử lý thông thường.
                // Lỗi mạng tại đây có thể là COMMIT IN-DOUBT, không được
                // coi như rollback chắc chắn.
                try {
                    session.commit();
                    return outcome;
                } catch (TransactionRolledBackException knownRollback) {
                    // Đặc tả JMS xác nhận transaction đã rollback.
                    // Caller có thể thử lại theo redelivery policy.
                    throw knownRollback;
                } catch (JMSException commitFailure) {
                    throw new CommitInDoubtException(sourceId, commitFailure);
                }
            }
        }
    }
}
```

**Vì sao bố trí như vậy?**

1. `Session.SESSION_TRANSACTED` xuất hiện **một lần** và cùng Session đó tạo consumer lẫn hai producer. Dù gửi đến `orders.validated` hay `orders.rejected`, việc xác nhận input chỉ xảy ra khi `session.commit()`.
2. Sau `validProducer.send(output)` mà `injectFailureBeforeCommit=true`, lệnh `session.rollback()` hoàn nguyên **cả** việc nhận input lẫn send output. Không có chuyện input bị mất vì đã gọi `receive()`.
3. Với lỗi payload vĩnh viễn, worker không rollback vô hạn mà tạo message mô tả rejection **trong cùng transaction** rồi commit; input không bị consume trước khi có kết quả thay thế.
4. Khi provider ném `TransactionRolledBackException`, worker giữ nguyên tín hiệu rollback đã xác nhận. Với **lỗi commit khác không xác định được kết quả**, không lặng lẽ retry trên cùng Session: có thể broker đã commit nhưng phản hồi bị mất. Worker ném `CommitInDoubtException` để điều phối viên đối soát và khôi phục kết nối.
5. `try-with-resources` giúp đóng producer/consumer/session/connection kể cả khi exception. Nó không phải bằng chứng rằng transaction vừa báo `IN_DOUBT` đã rollback; close chỉ rollback **giao dịch chưa được commit trên broker**.

> **Không đưa** các thao tác ghi DB, trừ tiền, gọi API ngoài hoặc ghi tệp có side effect vào `normalized = ...` mà lại mặc định chúng rollback cùng JMS. Mọi side effect ngoài broker cần giao thức giao dịch bổ sung hoặc cơ chế idempotency.

### 3.2. Chọn provider tương ứng broker

Với Java 17 + `jakarta.jms`, chọn **một provider** ở mỗi ứng dụng:

| Broker | Maven dependency | Factory ví dụ | Wire protocol |
|---|---|---|---|
| ActiveMQ Classic 6.4.x | `org.apache.activemq:activemq-client:6.4.0` | `new org.apache.activemq.ActiveMQConnectionFactory("tcp://localhost:61616")` | OpenWire |
| Artemis 2.57.0 | `org.apache.artemis:artemis-jakarta-client:2.57.0` | `new org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory("tcp://localhost:61616")` | Core |

Ví dụ wiring cho **Classic**:

```java
import jakarta.jms.ConnectionFactory;

ConnectionFactory factory = new org.apache.activemq.ActiveMQConnectionFactory(
    "tcp://127.0.0.1:61616");

ReceiveProcessForward.Outcome outcome =
    ReceiveProcessForward.processOne(factory, user, password, false);
System.out.println(outcome);
```

Ví dụ wiring cho **Artemis** (chạy trong một ứng dụng riêng):

```java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
try {
    ReceiveProcessForward.Outcome outcome =
        ReceiveProcessForward.processOne(factory, user, password, false);
    System.out.println(outcome);
} finally {
    factory.close(); // đóng factory Artemis do ứng dụng tạo
}
```

Các đoạn wiring nằm trong method có biến `user`/`password` được cấp từ nguồn bí mật đáng tin cậy. Classic 5.x thường dùng `javax.jms` ở artifact truyền thống; không trộn `javax.jms.Session` với `jakarta.jms.Session`. URI kết nối và tài khoản phải khớp transport listener và authorization của broker đang chạy.

Trong mã production, factory/connection có thể được tái sử dụng qua lifecycle của một worker hoặc qua pool có giới hạn, thay vì tạo lại cho mỗi message. **Bất biến bắt buộc vẫn là mỗi luồng xử lý dùng Session riêng, không chia sẻ một Session đồng thời giữa nhiều thread.**

## 4. Timeline: rollback không đồng nghĩa gửi hai lần

Một người quan sát có thể thấy `producer.send(output)` đã chạy và lo rằng output tồn tại khi xử lý lỗi. Trên transacted Session, đó là thao tác được **ghi nhận trong transaction**, chưa có hiệu lực như một output đã commit.

```text
Thời gian       Session T                    orders.received   orders.validated
--------------------------------------------------------------------------------
t0              receive(input A)             A đang in-flight  rỗng
t1              send(output A')              A chưa ACK        A' chưa visible
t2              xử lý lỗi, rollback()         A có thể redeliver rỗng
t3              receive lại A (TX mới)        A đang in-flight  rỗng
t4              send(output A')              A chưa ACK        A' chưa visible
t5              commit() thành công           A đã ACK         A' visible
```

Số lần gọi `send` trong log worker là **hai**, nhưng sau rollback rồi commit bình thường, broker chỉ phát hành output của **transaction đã commit**. Đừng nhầm log "send called" với "output delivered".

**Điểm tinh tế:** nếu một transaction nhận **hai message** và gửi **ba message**, rồi rollback, toàn bộ hai lần nhận và ba lần gửi đó cùng bị hoàn nguyên. Transaction là đơn vị trên Session, không mặc nhiên là trên từng message. Dùng một input/transaction giúp truy vết và hạn chế rollback cả batch nếu một item lỗi.

## 5. Hai tình huống gây sai thiết kế

### 5.1. Hai Session hoặc hai JMSContext độc lập

```java
// Sai nếu kỳ vọng receive và forward nguyên tử.
try (Connection connection = factory.createConnection(user, password);
     Session receiveSession = connection.createSession(Session.SESSION_TRANSACTED);
     Session sendSession = connection.createSession(Session.SESSION_TRANSACTED)) {
    // receiveSession nhận message A.
    // sendSession gửi A' rồi sendSession.commit().
    // Trước receiveSession.commit(), worker chết => A chưa ACK, A' đã gửi.
}
```

**Cùng Connection không tạo chung local transaction.** Chuyển sang đúng một Session hoặc, nếu thực sự có nhiều resource manager, dùng JTA/XA với coordinator thích hợp.

### 5.2. Send rồi đợi reply trước commit trong cùng transaction

```java
// Không phù hợp: request chưa commit nên responder chưa thấy request.
Message request = session.createTextMessage("validate me");
producer.send(request);
Message reply = replyConsumer.receive(5000);  // dễ timeout
session.commit();                              // quá muộn
```

Một responder bên ngoài transaction sẽ **không nhận request trước commit**, nên đợi phản hồi rồi mới commit tạo vòng chờ. Với request/reply, tách ranh giới transaction: commit việc phát request trước, sau đó mở transaction nhận reply; hoặc sử dụng mẫu asynchronous workflow/Saga.

### 5.3. Gửi sang broker khác

`orders.received` ở broker A và `orders.validated` ở broker B **không thể** được tự động gom vào cùng một JMS local Session trên A. Client không thể tạo producer cho `ConnectionFactory` B bằng Session A rồi coi đó là cùng giao dịch. Cơ chế bridge/cluster cũng không nên được mặc nhiên xem là một transaction nguyên tử xuyên hai broker; phải đọc và kiểm thử guarantee của topology cụ thể.

Nếu cần thay đổi **DB + JMS** nguyên tử, cân nhắc transactional outbox + idempotent consumer; nếu yêu cầu atomic commit thật giữa các tài nguyên hỗ trợ XA, dùng JTA/XA và cấu hình recovery. XA có chi phí, vận hành và giới hạn khác local Session, không được kích hoạt chỉ bằng cách đổi `SESSION_TRANSACTED`.

## 6. Điều kiện triển khai trên ActiveMQ Classic và Artemis

Ví dụ dùng queue persistent. Hai broker có implementation khác nhau nhưng cùng tuân theo semantics JMS local transaction.

| Vấn đề | Classic | Artemis |
|---|---|---|
| Quản lý local transaction | Broker nhận lệnh send/ACK mang transaction ID; `TransactionStore` giữ chúng cho đến commit hoặc rollback | Broker xử lý send/ACK như một local transaction trên session; commit/rollback được xác nhận qua protocol |
| Độ bền sau commit | Phụ thuộc broker `persistent=true`, message `PERSISTENT` và persistence adapter (ví dụ KahaDB) | Với durable message/queue và `journal-sync-transactional=true`, broker đồng bộ journal giao dịch trước khi trả xác nhận commit |
| Input redelivery sau rollback | Chính sách redelivery phía Classic client/broker, backoff, giới hạn retry | `address-settings`: `redelivery-delay`, `max-delivery-attempts`, dead-letter address |
| Kiểm tra vận hành | JMX queue size, in-flight, enqueue/dequeue, log transaction | Management/JMX, queue delivering count, journal/error logs |
| Lỗi mất kết nối khi commit | Có thể không xác định kết quả nếu response thất lạc | Có nhánh failover được báo rollback rõ ràng, nhưng mất phản hồi trong lúc commit vẫn có thể không xác định |

**Artemis — kiểm tra durability trong `broker.xml` (thuộc khối `<core>` hiện có):**

```xml
<!-- Cấu hình minh họa; không thêm <core> trùng trong file. -->
<journal-sync-transactional>true</journal-sync-transactional>
```

Đây là giá trị mặc định phổ biến theo tài liệu Artemis; đừng hạ xuống `false` để lấy throughput nếu yêu cầu bảo đảm giao dịch sống sót sau crash. Phải dùng queue durable và message `DeliveryMode.PERSISTENT`, đồng thời bảo đảm storage thực sự bền vững theo mô hình triển khai.

**Classic — kiểm tra tối thiểu:**

```xml
<!-- Chỉ trích thuộc tính của broker có sẵn trong conf/activemq.xml. -->
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-lab"
        persistent="true">
    <!-- persistenceAdapter (ví dụ KahaDB) phải được cấu hình phù hợp. -->
</broker>
```

Đoạn này **không phải file Classic đầy đủ**; không xóa các phần tử transport, security hay persistence hiện hữu để thay vào. Cấu hình persistent alone cũng không làm local JMS transaction bao phủ cơ sở dữ liệu nghiệp vụ.

### 6.1. Rollback, delay và DLQ chỉ liên quan đến *input*

Nếu transaction rollback, message nguồn có thể được phân phối lại theo chính sách broker. Khi quá số lần phân phối cho phép, chính sách DLQ có thể đưa **input** sang dead-letter destination; đó là cơ chế vận hành khác với việc ứng dụng cố ý gửi **rejection event** và commit.

- `orders.rejected` ở ví dụ là **kết quả nghiệp vụ** cho dữ liệu hỏng vĩnh viễn, do worker tự gửi và commit trong Session.
- DLQ là **cơ chế broker** dành cho message không thể xử lý qua các lần delivery theo policy.
- Không đưa cả hai loại kết quả vào một queue mà không định nghĩa rõ semantics, schema và trách nhiệm retry/replay.

Không cần tự gọi `message.acknowledge()` trên input sau khi gửi output: `session.commit()` đã làm công việc xác nhận input.

## 7. Xử lý lỗi đúng vị trí, đặc biệt lỗi khi commit

| Lỗi xảy ra ở đâu? | Quyết định mặc định | Lý do |
|---|---|---|
| Dữ liệu đầu vào không hợp lệ vĩnh viễn | Gửi rejection event **trong Session**, sau đó commit | Không lặp lại input không bao giờ xử lý được |
| Lỗi logic/transform hoặc dependency trước commit | `rollback()` rồi để redelivery/backoff xử lý | Chưa có output nào được phát hành |
| `producer.send` lỗi trước commit | Thử rollback Session; nếu không chắc trạng thái session, đóng kết nối và báo lỗi | Transaction chưa được commit thành công; không tự coi từng send là độc lập |
| `session.commit()` thành công | Ghi nhận `COMMITTED` | Input ACK và output đi cùng transaction |
| `session.commit()` bị `TransactionRolledBackException` rõ nghĩa | Ghi nhận rollback do provider xác nhận, chuẩn bị retry theo policy | Provider đã báo giao dịch bị rollback |
| `session.commit()` mất kết nối/timeout/exception không kết luận được | Ghi nhận `IN_DOUBT`, dừng Session đang hỏng và đối soát | Có thể commit đã xảy ra nhưng ACK về client thất lạc |

**Tại sao `rollback()` trong `catch(commitFailure)` không giải quyết in-doubt?** Nếu broker đã commit và chỉ mất phản hồi, yêu cầu rollback tiếp theo không thể đảo ngược transaction đã kết thúc. Đừng log “rollback success ⇒ output không tồn tại” sau một commit timeout.

Ứng dụng nên gắn **ID nghiệp vụ bất biến** lên input và lan truyền sang output, ví dụ `orderId`/`eventId`. Khi consumer downstream nhận output, nó cần **idempotency** cho side effect ngoài JMS. Trong tình huống commit không rõ, dùng event ID và quản trị broker/consumer logs để đối soát trước khi replay thủ công; tránh tạo một sự kiện mới với ID mới.

### 7.1. Tại sao worker không nên làm công việc chậm trong một transaction?

Giữ input trong transaction quá lâu có thể kéo theo:

- Message vẫn in-flight, consumer khác chưa nhận được.
- Transaction nhiều message tốn bộ nhớ, giữ tài nguyên broker và kéo dài thời gian xử lý commit.
- Khi tiến trình chết, nhiều input/output phải rollback cùng lúc.
- Failover hoặc network timeout làm tỷ lệ `IN_DOUBT`/retry khó quản lý hơn.

Vì vậy giữ phép xử lý cục bộ ngắn gọn, đặt timeout nhận/timeout cho dependency thích hợp, **không gọi HTTP/DB có side effect** trước commit nếu thiết kế chưa có idempotency. Nếu cần xử lý lâu (ví dụ tạo PDF, gọi model AI, thanh toán), nên tách thành nhiều chặng và áp dụng outbox/workflow thay vì giữ một JMS transaction mở hàng phút.

## 8. Thực hành có thể kiểm chứng từng trạng thái

Chuẩn bị hai queue đích `orders.validated`, `orders.rejected` và một queue nguồn `orders.received` trên cùng broker Classic/Artemis. Dùng broker lab, không dùng queue chứa dữ liệu thật. Bảo đảm ACL cho phép đọc nguồn và gửi sang cả hai đích.

### 8.1. Seed input bằng một transaction riêng

Đoạn sau tạo **một message đầu vào durable**. Đây là **một transaction khác** để chuẩn bị dữ liệu, không tham gia transaction xử lý của worker:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class SeedOrder {
    public static void enqueue(
            ConnectionFactory factory, String user, String password,
            String orderId, String body) throws Exception {
        try (Connection connection = factory.createConnection(user, password);
             Session session = connection.createSession(Session.SESSION_TRANSACTED)) {
            Queue input = session.createQueue("orders.received");
            try (MessageProducer producer = session.createProducer(input)) {
                producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                TextMessage message = session.createTextMessage(body);
                message.setStringProperty("orderId", orderId);
                producer.send(message);
                session.commit();  // input hiện có thể được worker nhận
            }
        }
    }
}
```

### 8.2. Ba phép thử cốt lõi

| Phép thử | Chuẩn bị và gọi worker | Điều phải quan sát |
|---|---|---|
| **A — commit thành công** | Seed `order-981` với body `hello`; `processOne(factory,u,p,false)` | Trả `FORWARDED`; nguồn không còn input đó, đích có đúng message `HELLO` với `orderId=order-981` |
| **B — rollback sau send** | Seed `order-982` với body `retry me`; gọi `processOne(factory,u,p,true)` và bắt `IllegalStateException` | Output `RETRY ME` **chưa xuất hiện**; input có thể được redelivery. Gọi lại `processOne(factory,u,p,false)` để commit một lần |
| **C — dữ liệu không hợp lệ** | Seed `order-983` với body rỗng; `processOne(factory,u,p,false)` | Trả `REJECTED`; input đã ACK; `orders.rejected` có thông báo lỗi, `orders.validated` không có message từ `order-983` |

Gợi ý kiểm chứng không tiêu thụ:

- Dùng JMX hoặc management console để đọc số message pending của từng queue; kiểm tra ID và thuộc tính bằng `QueueBrowser`.
- `JMSMessageID` của input ổn định qua redelivery thông thường; sử dụng `orderId` hoặc mã tương quan nghiệp vụ để so sánh thông điệp trước/sau.
- Để tránh nhiễu, chạy trên queue lab trống và chỉ có **một worker/consumer** khi thử. Sau rollback có thể có redelivery delay; chờ theo policy rồi mới kiểm tra.
- Đừng xác nhận chỉ bằng `QueueSize=0`: message có thể đang in-flight hoặc đã bị consumer khác nhận; đối chiếu cả phía output.

**Cấu hình gợi ý cho thử nghiệm rollback ở Artemis** (thêm vào `<address-settings>` hiện hữu):

```xml
<address-setting match="orders.received">
    <redelivery-delay>1000</redelivery-delay>
    <max-delivery-attempts>10</max-delivery-attempts>
</address-setting>
```

Với Classic, chính sách redelivery có thể được cấu hình trên client/broker theo phiên bản; không copy XML `address-setting` của Artemis vào `activemq.xml`. Phép thử chỉ cần rollback đúng một lần, không yêu cầu bật DLQ phức tạp.

### 8.3. Fault injection bổ sung: đứt mạng đúng lúc commit

Khi muốn kiểm tra nhánh **`IN_DOUBT`**, cần proxy mạng hoặc cơ chế fault injection giữa Java và broker để có thể cắt đường phản hồi sau khi request commit đã tới broker. Lệnh `docker stop` ngẫu nhiên **không bảo đảm** rơi vào đúng cửa sổ này.

Một lần test có thể dẫn tới:

- Broker **chưa commit**: input quay lại, không có output.
- Broker **đã commit nhưng response bị mất**: input đã ACK, output đã có.

**Cả hai kết quả đều hợp lệ** từ quan sát phía client khi exception xảy ra giữa commit và phản hồi. Thu thập message IDs, timestamp, log transaction, queue state và output `orderId` để đối soát. Nếu provider trả về ngoại lệ chuyên biệt xác nhận transaction rollback (ví dụ nhánh failover của Artemis), có thể phân loại rõ hơn theo hợp đồng của provider; không gộp mọi lỗi commit vào một kết luận.

## 9. Tiêu chí hoàn thành và giới hạn áp dụng

Một implementation đạt yêu cầu **nhận–xử lý–gửi tiếp trong cùng JMS Session** khi:

1. Input consumer và mọi output producer đều do **cùng một transacted Session** tạo ra.
2. Đường xử lý thành công chỉ đánh dấu DONE sau `session.commit()`; không đánh dấu sau `receive()` hoặc `send()`.
3. Lỗi trước commit gây rollback; chứng minh input có thể redelivery và output chưa commit không hiển thị.
4. Dữ liệu hỏng vĩnh viễn được xử lý có chủ đích bằng rejection event + commit, khác với lỗi tạm thời.
5. Lỗi mạng khi commit được xử lý như `IN_DOUBT` trừ khi provider có bằng chứng rollback rõ ràng; không retry tạo tác dụng phụ mới tùy tiện.
6. Không chia sẻ Session đồng thời giữa nhiều thread và không đưa resource ngoài JMS vào phạm vi bảo đảm một cách ngầm định.

**Kết luận:** Với một broker và một transacted `Session`, pattern này đóng gói việc tiêu thụ input và phát hành output thành **một giao dịch JMS cục bộ**. Đây là công cụ mạnh cho các bước chuyển đổi message giữa queue/topic cùng provider; nó **không** đồng nghĩa với giao dịch phân tán hoặc exactly-once cho mọi side effect của hệ thống.

## Nguồn tham khảo

1. [Jakarta Messaging 3.1 Specification — Session transactions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `commit`, `rollback`, acknowledgment và giao dịch input/output cùng Session.
2. [Jakarta EE Tutorial — JMS Concepts](https://jakarta.ee/learn/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html): transacted `JMSContext`, cảnh báo request/reply trước commit và khác biệt container-managed.
3. [Jakarta Messaging — Connection.createSession API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/connection): `SESSION_TRANSACTED` ở Java SE và các giới hạn Jakarta EE/JTA.
4. [ActiveMQ Classic — How Do Transactions Work](https://activemq.apache.org/components/classic/documentation/how-do-transactions-work): TransactionStore và buffering của send/ACK trước commit.
5. [ActiveMQ Classic — Message Redelivery and DLQ Handling](https://activemq.apache.org/components/classic/documentation/message-redelivery-and-dlq-handling): rollback, redelivery và chính sách Classic.
6. [Apache Artemis — Guarantees of Sends and Commits](https://artemis.apache.org/components/artemis/documentation/latest/send-guarantees.html): `journal-sync-transactional` và độ bền sau xác nhận commit.
7. [Apache Artemis — High Availability and Failover](https://artemis.apache.org/components/artemis/documentation/latest/ha.html): xử lý failover trong transaction, rollback chuyên biệt và commit in-doubt.
8. [Apache Artemis — Message Redelivery and Undelivered Messages](https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages.html): delayed redelivery khi rollback.
