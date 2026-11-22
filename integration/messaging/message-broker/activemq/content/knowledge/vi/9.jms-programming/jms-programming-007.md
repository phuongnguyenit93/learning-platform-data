# MessageListener và xử lý nhận bất đồng bộ

> **Chương:** Lập trình JMS  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — giao tiếp bất đồng bộ qua Apache ActiveMQ Classic và Artemis, queue/topic/routing, Java/JMS, acknowledgment, transaction, redelivery, dead-letter queue (DLQ), bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi bài:** Thiết kế **JMS MessageListener** cho việc nhận thông điệp bất đồng bộ; chú trọng vòng đời, luồng thực thi, commit/rollback, lỗi và bảo đảm xử lý. Mã chạy minh họa **Artemis 2.40.0 + Jakarta Messaging 3.1**. Với ActiveMQ Classic 5.x, cần dùng bộ client tương ứng với namespace `javax.jms`.

## 1. Vì sao cần MessageListener?

Một worker nhận lệnh `shipping.create` từ queue. Worker không cần chủ động liên tục gọi `receive()`; khi có message, thư viện JMS gọi phương thức `onMessage(Message message)` do ứng dụng đăng ký. Từ góc nhìn người lập trình, đây là **nhận bất đồng bộ theo callback**.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as ActiveMQ broker
    participant S as JMS Session
    participant L as MessageListener
    participant D as Business database

    P->>B: send shipping.create(eventId)
    B->>S: deliver message qua consumer
    S->>L: onMessage(message)
    L->>D: cập nhật nghiệp vụ, commit DB
    D-->>L: thành công
    L->>S: commit JMS transaction
    S-->>B: ACK/commit
    Note over L,B: Nếu lỗi trước ACK commit, message có thể được giao lại
~~~

Điểm then chốt không phải cú pháp lambda, mà là **ai sở hữu luồng xử lý**, **khi nào broker coi message đã được tiêu thụ**, và **nếu callback lỗi thì thông điệp đi đâu**.

### So sánh nhận đồng bộ và bất đồng bộ

| Tiêu chí | `consumer.receive(timeout)` | `consumer.setMessageListener(listener)` |
|---|---|---|
| Ai chủ động nhận? | Luồng ứng dụng gọi `receive` | JMS provider gọi `onMessage` khi có message |
| Mô hình điều khiển | Vòng lặp/long polling do ứng dụng xây | Callback do provider dispatch |
| Khi queue rỗng | Luồng `receive` chờ tới message hoặc timeout | Không có callback cho tới khi có delivery |
| Vòng đời | Ứng dụng kiểm soát vòng lặp nhận | Cần giữ `Connection`/`Session`/`MessageConsumer` sống |
| Xử lý lỗi | `try/catch` quanh một lượt `receive` và xử lý | `try/catch` **bên trong** callback; cần rollback/recovery rõ ràng |
| Đồng thời | Ứng dụng tự cấp luồng/session | Mỗi JMS Session tuần tự dispatch listener; muốn song song cần thêm session/consumer |
| Phù hợp | Job chạy theo đợt, kiểm thử, xử lý với timeout chủ động | Worker chạy liên tục, luồng sự kiện, dịch vụ tiêu thụ nền |

Cả hai cách đều dùng **JMS consumer** và chịu chính sách routing, transaction, redelivery, DLQ của broker. **Asynchronous callback không đồng nghĩa xử lý song song, không tự bảo đảm đúng một lần, cũng không thay thế thiết kế dữ liệu nghiệp vụ.**

## 2. Lifecycle chính xác của một JMS listener

Các bước khởi tạo một listener theo API JMS truyền thống:

~~~text
ConnectionFactory
       |
       v
createConnection(user, password)
       |
       v
createSession(transacted, acknowledgeMode)
       |
       v
createConsumer(queue | topic, optionalSelector)
       |
       v
setMessageListener(listener)  ---> đăng ký callback
       |
       v
connection.start()            ---> cho phép bắt đầu message delivery
       |
       v
provider thread --> onMessage(message) --> ACK/commit/rollback
       |
       v
connection.stop()             ---> tạm ngừng delivery, đợi callback đang chạy
       |
       v
close consumer/session/connection từ luồng quản lý
~~~

### 2.1. `setMessageListener()` chưa đủ để nhận message

`MessageConsumer.setMessageListener(MessageListener)` chỉ gắn handler; **`Connection.start()`** mới cho phép việc delivery bắt đầu. Một consumer đã được tạo nhưng connection chưa start có thể đứng im dù queue đang có message.

Nên gắn listener **trước khi start connection**. Nếu start trước rồi mới đăng ký listener, ứng dụng khó xác định thời điểm nhận bắt đầu, nhất là khi có nhiều consumer trong cùng connection.

Với **JMS 2.0/3.1 `JMSContext`**, cơ chế auto-start được bật mặc định trong nhiều cách sử dụng JMS simplified API. Đừng áp dụng máy móc quy tắc `Connection.start()` của classic API lên mọi cách tạo `JMSContext`. Trong bài ta chủ động dùng `Connection` / `Session` để kiểm soát thứ tự.

### 2.2. Ai gọi `onMessage()`?

**JMS provider** điều phối callback trên luồng do nó quản lý. Ứng dụng không nên giả định đó là HTTP request thread hoặc thread của `main()`. Trong một **JMS Session**, việc giao message cho listener được **tuần tự hóa**: một session không thực thi đồng thời nhiều callback listener.

Hệ quả:

- Một listener xử lý một message trong 15 giây có thể giữ phiên đó bận trong 15 giây.
- Nhiều consumer tạo trên **cùng session** không cung cấp khả năng xử lý song song độc lập.
- Muốn xử lý đồng thời, cần nhiều **Session/Consumer** tương ứng (hoặc container/framework tạo chúng).
- Nếu nhiều session cùng gọi vào một đối tượng handler chia sẻ, handler phải tự bảo đảm thread safety cho state chung.
- `Session` có trạng thái ACK/transaction; **không dùng một Session đồng thời từ nhiều thread** chỉ vì muốn tăng throughput.

### 2.3. Dừng và đóng đúng luồng

Không nên gọi `session.close()` hoặc `connection.close()` từ chính callback đang sử dụng session đó. JMS có ràng buộc liên quan việc đóng tài nguyên khi message listener đang chạy; một số provider có thể chặn, báo lỗi hoặc có hành vi khác nhau. Hãy để **luồng quản lý vòng đời** gọi `connection.stop()`, đợi xử lý đang chạy rồi đóng consumer/session/connection.

`Connection.stop()` tạm dừng delivery nhưng **không xóa queue, không xóa message và không giải quyết transaction đang dở của ứng dụng**. Nếu server/consumer bị dừng đột ngột, message chưa ACK/commit có thể được redeliver theo chính sách broker.

## 3. Acknowledgment quyết định kết quả nhận bất đồng bộ

### 3.1. So sánh các chế độ

| Chế độ của Session | Khi nào xác nhận? | Hành vi với `onMessage` | Rủi ro cần quản lý |
|---|---|---|---|
| `AUTO_ACKNOWLEDGE` | Provider tự ACK sau khi callback xử lý thành công theo JMS contract | Ứng dụng không gọi ACK thủ công | Không có transaction chung với DB; lỗi sau side effect nhưng trước ACK có thể khiến xử lý lại |
| `CLIENT_ACKNOWLEDGE` | Ứng dụng gọi `message.acknowledge()` | Có thể ACK từ callback khi đã xử lý | Một lệnh `acknowledge()` xác nhận **các message đã tiêu thụ trong cùng Session** theo ngữ nghĩa JMS, không nên coi là ACK riêng từng message |
| `DUPS_OK_ACKNOWLEDGE` | Provider được phép ACK theo cách “lười” | Callback có thể nhận message đã giao trước đó | Cho phép bản giao trùng trong một số trường hợp, cần idempotency |
| `SESSION_TRANSACTED` | ACK là một phần của `session.commit()`; rollback loại bỏ ACK chưa commit | Callback gọi `commit()` hoặc `rollback()` theo kết quả | Vẫn có thể giao lại khi mất connection/commit không rõ trạng thái; không gộp sẵn DB transaction |

Với **transacted session**, giá trị acknowledge mode truyền vào `createSession(true, ...)` bị bỏ qua về mặt xác nhận message; transaction sẽ quyết định việc ACK. Hãy dùng `Session.SESSION_TRANSACTED` để biểu lộ ý định rõ ràng.

### 3.2. Đừng dựa vào exception để thay thế rollback

Ví dụ callback kiểu này là thiếu ràng buộc:

~~~java
consumer.setMessageListener(message -> {
    updateDatabase(message); // Có thể ném RuntimeException
});
~~~

Nếu `updateDatabase` lỗi, không có lựa chọn ACK/rollback minh bạch. Đặc biệt với callback asynchronous, **không dựa vào việc ném `RuntimeException` từ `onMessage` như một API retry portable**; xử lý của provider trước exception có thể thay đổi và ứng dụng khó kiểm soát.

Cách diễn đạt chính xác hơn: **ghi nhận lỗi, rollback transaction JMS (nếu sử dụng), để broker áp dụng redelivery policy và DLQ**. Nếu dùng non-transacted `CLIENT_ACKNOWLEDGE`, cần hiểu `Session.recover()` và phạm vi ACK của session trước khi áp dụng; không biến nó thành “retry đúng message hiện tại” một cách tùy tiện.

### 3.3. ACK không đồng nghĩa thành công nghiệp vụ

JMS ACK/commit chỉ mô tả mốc xử lý đối với broker/session. Một lời gọi HTTP tới đối tác, một cập nhật DB hoặc một lệnh gửi email có thể đã xảy ra **trước** ACK.

Ví dụ:

~~~text
T0: Broker giao shipping.create(eventId=E1)
T1: Worker ghi thành công nhãn vận chuyển vào DB
T2: Process crash trước session.commit() của JMS
T3: Broker giao lại E1
T4: Worker cần nhận diện E1 đã xử lý, tránh tạo nhãn lần hai
~~~

Vì vậy **at-least-once + idempotent consumer** thường là hợp đồng thực tế. Không có một cờ JMS nào tự bảo đảm exactly-once end-to-end khi hệ thống còn tương tác với database hoặc API bên ngoài.

## 4. Bài lab: MessageListener có JMS transaction trên Artemis

Ví dụ này đi thẳng vào xử lý bất đồng bộ, không làm lại bài khởi động broker. Giả sử một Artemis broker đã chạy và có acceptor cho Artemis JMS native client tại `tcp://127.0.0.1:61616`, tài khoản lab có quyền send/consume.

### 4.1. Broker destination và chính sách redelivery

Để kết quả nhất quán, khai báo **queue `shipping.create`** kiểu ANYCAST trong `broker.xml` của broker Artemis. Đây là đoạn chèn **vào phần `<addresses>` đang có**, không phải tệp XML độc lập:

~~~xml
<address name="shipping.create">
    <anycast>
        <queue name="shipping.create"/>
    </anycast>
</address>
<address name="DLQ">
    <anycast>
        <queue name="DLQ"/>
    </anycast>
</address>
~~~

Nếu address/queue đã tồn tại thì không khai báo trùng. Cấu hình DLQ và delay, đặt vào khối **`<address-settings>` đang có**, hợp nhất với rule trùng phạm vi:

~~~xml
<address-setting match="shipping.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>3</max-delivery-attempts>
    <redelivery-delay>2000</redelivery-delay>
</address-setting>
~~~

Phân biệt rõ:

- `max-delivery-attempts=3` là chính sách **Artemis** về số lần broker thử giao message theo phạm vi cấu hình.
- `redelivery-delay=2000` đặt khoảng trễ redelivery ban đầu (ms) theo chính sách broker.
- `dead-letter-address=DLQ` chỉ ra nơi chuyển thông điệp không xử lý được; cần kiểm tra DLQ thực có queue/binding và quyền phù hợp.
- Cấu hình cụ thể của **ActiveMQ Classic** dùng cơ chế khác, có thể liên quan `RedeliveryPolicy` ở client và broker dead-letter strategy; không sao chép XML Artemis sang Classic.

Trong môi trường production, quyết định số lần thử và thời gian delay theo loại lỗi, yêu cầu nghiệp vụ, năng lực worker và chính sách replay DLQ. Không đặt retry liên tục cho lỗi dữ liệu chắc chắn không thể sửa bằng việc thử lại.

### 4.2. Maven/JDK

Dự án:

~~~text
jms-async-lab/
├── pom.xml
└── src/main/java/lab/AsyncListenerLab.java
~~~

`pom.xml` dùng Java 17, Artemis client hỗ trợ **`jakarta.jms`**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lab</groupId>
    <artifactId>jms-async-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.40.0</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là bộ ví dụ phiên bản cố định để tái hiện, **không phải tuyên bố phiên bản mới nhất**. Nếu đang dùng Classic 5.x, cần client `org.apache.activemq:activemq-client` và API `javax.jms` tương ứng; không thay import đơn thuần rồi giữ nguyên provider.

### 4.3. Một chương trình Java có hai chế độ

Tạo `src/main/java/lab/AsyncListenerLab.java`:

~~~java
package lab;

import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.Connection;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class AsyncListenerLab {

    private static final String QUEUE_NAME = "shipping.create";

    private AsyncListenerLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 0
                || (!"send".equals(args[0]) && !"listen".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Dùng: send [payload] hoặc listen");
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = requiredEnv("BROKER_USER");
        String password = requiredEnv("BROKER_PASSWORD");

        ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(url);
        Connection connection = factory.createConnection(user, password);

        try {
            // Lỗi connection/provider bất đồng bộ khác với lỗi nghiệp vụ
            // bên trong onMessage. Hãy quan sát cả hai nguồn lỗi.
            connection.setExceptionListener(error ->
                    System.err.println("JMS CONNECTION ERROR: "
                            + error.getMessage()));

            if ("send".equals(args[0])) {
                String payload = args.length > 1
                        ? args[1] : "ship-order-101";
                sendOne(connection, payload);
            } else {
                listen(connection);
            }
        } finally {
            connection.close();
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu biến môi trường " + key);
        }
        return value;
    }

    private static void sendOne(Connection connection, String payload)
            throws JMSException {
        Session session =
                connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
        try {
            Queue queue = session.createQueue(QUEUE_NAME);
            MessageProducer producer = session.createProducer(queue);
            try {
                producer.setDeliveryMode(DeliveryMode.PERSISTENT);

                TextMessage message =
                        session.createTextMessage(payload);
                message.setStringProperty("eventId",
                        UUID.randomUUID().toString());

                producer.send(message);

                System.out.println("SENT messageId="
                        + message.getJMSMessageID());
                System.out.println("SENT eventId="
                        + message.getStringProperty("eventId"));
                System.out.println("SENT body=" + payload);
            } finally {
                producer.close();
            }
        } finally {
            session.close();
        }
    }

    private static void listen(Connection connection) throws Exception {
        // JMS transaction: auto-ack mode được bỏ qua ở transacted session.
        Session session =
                connection.createSession(true, Session.SESSION_TRANSACTED);
        try {
            Queue queue = session.createQueue(QUEUE_NAME);
            MessageConsumer consumer = session.createConsumer(queue);

            CountDownLatch oneSuccessfulCommit = new CountDownLatch(1);

            try {
                // Callback chạy trên provider thread, sử dụng đúng Session
                // tạo ra consumer. Không chia sẻ Session sang worker thread khác.
                consumer.setMessageListener(message ->
                        onDelivery(session, message, oneSuccessfulCommit));

                connection.start();
                System.out.println("LISTENING queue=" + QUEUE_NAME);
                System.out.println(
                        "Main thread đang chờ tối đa 30 giây; "
                        + "callback xử lý trên JMS provider thread.");

                boolean completed =
                        oneSuccessfulCommit.await(30, TimeUnit.SECONDS);
                if (!completed) {
                    System.out.println(
                            "NO_SUCCESS: chưa có delivery được commit "
                            + "trong khoảng chờ.");
                }
            } finally {
                // Dừng từ luồng quản lý, ngoài onMessage; chờ callback
                // đang chạy hoàn tất trước khi đóng consumer/session.
                try {
                    connection.stop();
                } finally {
                    consumer.close();
                }
            }
        } finally {
            session.close();
        }
    }

    private static void onDelivery(
            Session session,
            Message message,
            CountDownLatch oneSuccessfulCommit) {

        try {
            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException(
                        "Chỉ xử lý TextMessage");
            }

            String eventId = textMessage.getStringProperty("eventId");
            if (eventId == null || eventId.isBlank()) {
                throw new IllegalArgumentException(
                        "Message thiếu eventId");
            }

            String payload = textMessage.getText();
            int deliveryCount = message.propertyExists("JMSXDeliveryCount")
                    ? message.getIntProperty("JMSXDeliveryCount")
                    : -1;

            System.out.println("RECEIVED eventId=" + eventId
                    + " deliveryCount=" + deliveryCount
                    + " redelivered=" + message.getJMSRedelivered()
                    + " payload=" + payload
                    + " thread=" + Thread.currentThread().getName());

            // Chỉ là mô phỏng lỗi nghiệp vụ để quan sát rollback / DLQ.
            // Không đặt tác vụ DB thật vào đây nếu chưa có idempotency.
            if (payload.startsWith("FAIL:")) {
                throw new IllegalStateException(
                        "Poison message mô phỏng: " + payload);
            }

            // Trong production: gọi business handler idempotent và
            // COMMIT DB transaction thành công trước khi JMS commit.
            System.out.println("BUSINESS_HANDLED eventId=" + eventId);

            session.commit(); // Commit ACK của message thuộc transaction.
            System.out.println("JMS_COMMITTED eventId=" + eventId);
            oneSuccessfulCommit.countDown();

        } catch (Exception failure) {
            System.err.println("HANDLING_FAILED: " + failure.getMessage());
            try {
                session.rollback(); // Cho phép redelivery theo broker policy.
            } catch (JMSException rollbackFailure) {
                System.err.println(
                        "JMS_ROLLBACK_FAILED: "
                        + rollbackFailure.getMessage());
                // Trạng thái transaction có thể không xác định.
                // Nên đánh dấu consumer không khỏe và tái đồng bộ.
            }
        }
    }
}
~~~

#### Vì sao code dùng `Session` truyền vào callback?

Listener đăng ký trên `MessageConsumer` của một session cụ thể. Trong ví dụ **một consumer, một session**, provider gọi `onMessage` tuần tự trong session đó. `session.commit()` và `session.rollback()` được thực hiện tại callback xử lý cùng session, để thống nhất phạm vi transaction JMS.

Mã không `close()` session từ `onMessage`; luồng `main` giữ session và connection còn sống, rồi `stop()` và đóng ở cuối. Ngoài phạm vi lab, worker cần chính sách graceful shutdown theo tiến trình/application container chứ không phụ thuộc một `CountDownLatch`.

#### Tại sao có `JMSXDeliveryCount` và `JMSRedelivered`?

- `JMSRedelivered` cho biết provider đánh dấu lần delivery này là giao lại; nó không giải thích toàn bộ nguyên nhân nghiệp vụ.
- `JMSXDeliveryCount` khi provider cung cấp cho biết số lần message đã được deliver; giá trị thường giúp kiểm tra redelivery, nhưng không dùng nó như khóa idempotency.
- **`eventId`** do producer gán và được ứng dụng duy trì ổn định mới là một khóa thích hợp để phát hiện message xử lý trùng.

Trong một giao thức message chuẩn, mọi thuộc tính ứng dụng như `eventId` phải được thống nhất schema với bên gửi; đừng tự ý đổi tên property trong một hệ thống nhiều service.

### 4.4. Chạy thử

Trên PowerShell, cấu hình tài khoản đúng của môi trường lab:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "lab"
$env:BROKER_PASSWORD = "mat-khau-lab"
~~~

Tài khoản cần quyền gửi/consume queue `shipping.create`. Không ghi mật khẩu thật vào source hoặc commit. Biên dịch:

~~~powershell
mvn -q -DskipTests package
~~~

**Lần thử 1 — message bình thường.** Gửi trước:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.AsyncListenerLab" "-Dexec.args=send order-101"
~~~

Sau đó chạy:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.AsyncListenerLab" "-Dexec.args=listen"
~~~

Kỳ vọng có:

~~~text
LISTENING queue=shipping.create
RECEIVED eventId=... deliveryCount=1 redelivered=false payload=order-101 thread=...
BUSINESS_HANDLED eventId=...
JMS_COMMITTED eventId=...
~~~

Sau một lần commit, consumer đóng và queue thường trở lại trạng thái không còn message chờ (giả sử không có client khác).

**Lần thử 2 — lỗi có chủ đích.** Gửi:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.AsyncListenerLab" "-Dexec.args=send FAIL:simulate"
mvn -q exec:java "-Dexec.mainClass=lab.AsyncListenerLab" "-Dexec.args=listen"
~~~

Kỳ vọng callback log `HANDLING_FAILED` và `session.rollback()`; broker có thể giao lại theo delay, tối đa theo `max-delivery-attempts`, rồi chuyển message sang DLQ nếu cấu hình đầy đủ. Mã không gọi `oneSuccessfulCommit.countDown()` cho message lỗi, nên mode `listen` có thể hết thời gian 30 giây và in `NO_SUCCESS`. Đây là kết quả đúng cho bài thử lỗi.

**Không khẳng định chắc chắn thứ tự/số lượng dòng log** nếu broker đang có message khác, policy chưa được nạp hoặc phiên bản có thay đổi. Hãy đối chiếu thêm queue depth, delivering count và số message trong DLQ trên console/JMX của broker.

**Lần thử 3 — queue rỗng.** Chạy `listen` khi không có message mới, chờ tối đa 30 giây; sẽ không có callback `onMessage`. Điều này khác với `receive(timeout)`: thời gian chờ do ứng dụng **duy trì vòng đời listener** quyết định, không phải timeout của `receive`.

## 5. Luồng thực thi: cách mở rộng consumer đúng cách

### 5.1. Một Session không có nghĩa nhiều callback đồng thời

Giả sử có 100 message và một `MessageListener` xử lý trung bình 500 ms/message. Nếu listener giữ một session duy nhất và callback xử lý tuần tự, thời gian xử lý riêng phần callback có thể gần 50 giây (chưa tính overhead). Gắn thêm consumer vào **cùng session** không làm 100 message được xử lý đồng thời.

Giải pháp phổ biến: tạo **N Session và N Consumer** (có thể từ nhiều connection được quản lý) trên cùng queue, mỗi session có một listener, theo giới hạn năng lực của DB và downstream.

~~~mermaid
flowchart LR
    Q[("Queue shipping.create")] --> C1["Consumer 1\nSession 1"]
    Q --> C2["Consumer 2\nSession 2"]
    Q --> C3["Consumer 3\nSession 3"]
    C1 --> L1["Listener 1"]
    C2 --> L2["Listener 2"]
    C3 --> L3["Listener 3"]
    L1 --> DB[("Business DB")]
    L2 --> DB
    L3 --> DB
~~~

Nếu cùng dùng một đối tượng service xử lý nghiệp vụ, service đó phải an toàn khi chạy đồng thời. Những đối tượng như DB connection hoặc một `Session` không nên được chia sẻ tự do giữa callback threads.

### 5.2. Có nên tự tạo thread pool bên trong `onMessage`?

Mẫu đáng ngại:

~~~java
consumer.setMessageListener(message -> {
    executor.submit(() -> processBusiness(message));
    // Callback trả về ngay, trước khi xử lý nghiệp vụ xong.
});
~~~

Với `AUTO_ACKNOWLEDGE`, callback có thể hoàn tất rồi provider ACK **trước** khi thread pool xử lý thành công. Với transacted session, việc cố `commit()` từ một thread pool khác còn phá vỡ mô hình sở hữu session/callback.

Nếu cần tăng concurrency, ưu tiên **nhiều JMS session/consumer** được container hoặc thư viện quản lý; nếu bắt buộc dùng handoff đến worker pool thì phải thiết kế lại rõ ràng acknowledgment và handoff bền vững, không chuyển đối tượng JMS Session qua thread tự do.

**Nguyên tắc:** callback không được đánh dấu thành công chỉ vì đã enqueue công việc vào bộ nhớ tạm. Một queue trong RAM của process khác xa một transaction đã được xác nhận.

### 5.3. Giữ thời gian callback có giới hạn

Một listener ổn định thường:

1. Validate schema/type/property.
2. Kiểm tra idempotency key.
3. Gọi business logic có timeout và giới hạn tài nguyên.
4. Commit nghiệp vụ, sau đó commit/ACK JMS.
5. Ghi metric duration, success/failure, redelivery.
6. Không log payload nhạy cảm hoặc dump toàn bộ message.

Callback bị treo vì HTTP request không timeout sẽ giữ session và có thể đẩy queue backlog lên cao. Nếu broker có prefetch/consumer window, message có thể đã được chuyển đến client nhưng vẫn chưa ACK; cần theo dõi **queue depth, delivering count, message age và consumer count** cùng lúc.

### 5.4. Không suy ra thứ tự hoàn tất từ thứ tự gửi

Với nhiều consumer trên cùng queue, broker phân phối message đến các session, và nghiệp vụ có thể hoàn tất khác thứ tự ban đầu. Redelivery, rollback, priority, selector hoặc thay đổi consumer cũng tác động thứ tự quan sát.

Nếu mọi event cho một `orderId` cần xử lý tuần tự, phải chọn chiến lược như partitioning theo khóa, message groups/provider feature hoặc khóa/kiểm tra version ở database. **Một MessageListener không tự cấp thứ tự toàn cục khi hệ thống scale out.**

## 6. Idempotency: chống xử lý lại khi DB commit xong nhưng JMS chưa commit

Mục tiêu là **một tác dụng nghiệp vụ cho mỗi `eventId`**, dù broker giao cùng message nhiều lần.

Một mẫu database transaction (ví dụ **PostgreSQL**) có thể dùng bảng:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
~~~

Pseudo-flow cho business handler:

~~~text
BEGIN DB TRANSACTION

  INSERT INTO processed_events(event_id)
  VALUES (:eventId)
  ON CONFLICT DO NOTHING;

  IF inserted_one_row THEN
      UPDATE shipments ...;        -- tác dụng nghiệp vụ trong cùng DB txn
      INSERT INTO shipment_audit...;
  ELSE
      -- đã xử lý trước đó: không tạo tác dụng nghiệp vụ lần hai
  END IF

COMMIT DB TRANSACTION
session.commit()  -- JMS ACK commit sau DB commit
~~~

**Lưu ý kỹ thuật:**

- Không ghi `processed_events` trong một DB transaction nhưng lại thực hiện side effect của DB ngoài transaction khác; nếu vậy dấu dedup và thay đổi nghiệp vụ có thể lệch nhau.
- Với API bên ngoài như tạo vận đơn, dedup trong DB chưa bảo đảm tránh tạo lặp nếu đối tác đã nhận request rồi mạng timeout. Ưu tiên **idempotency key** ổn định ở API đối tác hoặc quy trình đối soát trước khi thử lại.
- Nếu producer ghi DB trước khi gửi JMS, producer cần xét **transactional outbox** để tránh trường hợp DB commit xong nhưng không phát message.
- Với một callback có nhiều message trong cùng transacted session, transaction có thể bao phủ nhiều thao tác; bài lab dùng một callback/commit mỗi message để dễ xác định phạm vi.

Idempotency là **đặc tính của business handler**, không phải option `MessageListener`.

## 7. Phân loại lỗi và chính sách retry/redelivery

Lỗi có thể là tạm thời (database unreachable), lỗi dữ liệu vĩnh viễn (schema sai), hoặc trạng thái không chắc chắn (API bên ngoài timeout sau khi có thể đã thực thi).

| Lỗi | Cách ứng xử khuyến nghị | Vì sao |
|---|---|---|
| DB timeout/network chập chờn | Rollback JMS, broker redelivery có delay/backoff, giới hạn số lần | Lỗi có khả năng tự hồi phục |
| JSON/schema sai, trường bắt buộc thiếu | Ghi rõ validation error; không retry vô hạn; vào DLQ hoặc đường quarantine theo policy | Thử lại không sửa được dữ liệu |
| Partner API trả 429 | Delay retry theo giới hạn đối tác, tránh flood; dùng idempotency key | Tránh khuếch đại sự cố |
| Partner API timeout nhưng không biết đã xử lý chưa | Tra cứu/đối soát bằng request ID trước khi gọi lại | Tránh side effect trùng |
| JVM crash sau DB commit, trước JMS commit | Message có thể được giao lại; dedup theo eventId | At-least-once và khoảng trống commit |
| Producer gửi trùng event | Consumer dedup theo eventId | Có thể phát lại khi producer timeout |
| Broker stop/failover | Reconnect; kiểm tra trạng thái giao dịch, tránh giả định send/ACK đã commit | Trạng thái commit có thể không rõ |
| Consumer liên tục rollback một message | Giới hạn attempts và chuyển DLQ, cảnh báo, kiểm tra nguyên nhân | Tránh poison message khóa queue/worker |

### 7.1. Redelivery và DLQ không phải do Java listener tự tạo ra

Callback gọi `session.rollback()` làm transaction JMS không được commit. Khi nào message được phát lại, delay bao lâu, giới hạn số lần và đi vào DLQ nào là vấn đề của **provider/broker policy**.

- Với **Artemis**, cần xem `address-settings` cho address được dùng, đặc biệt `max-delivery-attempts`, `redelivery-delay` và `dead-letter-address`.
- Với **ActiveMQ Classic**, cần xem client redelivery policy và broker dead-letter strategy; không dùng cùng XML Artemis.
- Không chỉ nhìn vào header `JMSRedelivered=true` để quyết định chắc chắn đó là lỗi vĩnh viễn; phải kiểm tra lịch sử/idempotency và loại lỗi.

### 7.2. Không nuốt lỗi rồi commit

Đoạn code sau là sai nếu nghiệp vụ chưa hoàn tất:

~~~java
try {
    processBusiness(message);
} catch (Exception error) {
    log(error);  // Chỉ log rồi tiếp tục.
}
session.commit();  // Sai: đã ACK dù business handler thất bại.
~~~

Một `catch` tốt phải quyết định rõ: **rollback**, phân loại để đưa DLQ theo policy, hoặc có phương thức xử lý thật sự hoàn tất trước khi commit. Nếu muốn bỏ một message không thể sửa và ACK để loại bỏ, cần chính sách quarantine/audit tường minh, tránh mất dữ liệu âm thầm.

## 8. Message selector với listener: lọc đúng nhưng không thay business validation

Có thể dùng JMS selector để consumer chỉ nhận message có property thỏa điều kiện, ví dụ `priorityGroup = 'HIGH'`:

~~~java
// Producer
TextMessage msg = session.createTextMessage("ship-order-101");
msg.setStringProperty("priorityGroup", "HIGH");
producer.send(msg);

// Consumer ở một session riêng
MessageConsumer consumer = session.createConsumer(
        session.createQueue("shipping.create"),
        "priorityGroup = 'HIGH'");
consumer.setMessageListener(myListener);
~~~

Selector được đánh giá theo **JMS property/header**, không parse JSON body theo cách SQL. Những message không khớp selector có thể ở lại queue để consumer khác phù hợp nhận; nếu không consumer nào khớp, backlog có thể tăng.

Đừng dùng selector thay cho **schema validation** hoặc phân quyền. Producer có thể gửi sai property; listener vẫn cần kiểm tra nội dung và business invariants.

Với topic, selector lọc message của một subscription; **non-durable subscriber** thường không giữ message khi offline, còn **durable subscription** có hợp đồng tồn tại khác và cần client/subscription identity đúng cách. Đó là bài toán thiết kế subscription riêng, không phải thay đổi cơ bản của `MessageListener`.

## 9. ExceptionListener khác MessageListener

Hai interface có tên giống nhau nhưng vai trò khác biệt:

| Interface | Được kích hoạt bởi | Nên làm gì? |
|---|---|---|
| `MessageListener.onMessage(Message)` | Broker/JMS provider deliver **message nghiệp vụ** tới consumer | Xử lý message, kiểm soát business error, transaction/ACK |
| `ExceptionListener.onException(JMSException)` | Provider báo **lỗi connection/JMS bất đồng bộ** | Log/metric, health status, kích hoạt lifecycle/recovery phù hợp |
| `try/catch` tại nơi tạo connection/session | Lỗi **đồng bộ** trong quá trình tạo, cấu hình hay thao tác | Báo lỗi, cleanup, retry theo chính sách |

`ExceptionListener` **không phải** handler mặc định cho mọi exception mà business code ném bên trong `onMessage`. Vì thế mẫu Java đặt `try/catch` trong callback và `setExceptionListener` trên connection một cách độc lập.

Nếu framework quản lý connection pooling và automatic recovery, để framework sở hữu lifecycle, đừng đồng thời tự viết vòng reconnect không phối hợp khiến tạo nhiều listener và nhận message ngoài dự kiến.

## 10. Vận hành consumer bất đồng bộ

### 10.1. Những metric nên theo dõi

| Chỉ số | Ý nghĩa | Tình huống cần điều tra |
|---|---|---|
| Queue depth / pending | Số message đang tồn/chưa xử lý theo cách broker báo | Tăng liên tục dù producer rate ổn định |
| Oldest message age | Tuổi message chờ lâu nhất | SLA bị vi phạm dù queue depth không lớn |
| Enqueue/dequeue rate | Tốc độ vào và rời queue | Dequeue chậm hơn enqueue trong thời gian dài |
| Delivering/in-flight | Message đã giao nhưng chưa hoàn tất ACK | Cao trong khi callback xử lý quá chậm |
| Consumer count | Số consumer đăng ký | Đột ngột về 0 sau deploy hoặc broker failover |
| Redelivery count | Tần suất message phải giao lại | Tăng sau thay đổi schema/DB hoặc timeout |
| DLQ count / age | Message lỗi cuối cùng chưa được xử lý | Poison message tăng hoặc re-drive bị bỏ quên |
| Listener duration p95/p99 | Thời gian callback xử lý, kể cả DB/HTTP | Tăng mạnh sau khi downstream suy giảm |
| Commit/rollback failures | Lỗi xác nhận JMS transaction | Nghi ngờ mất connection hoặc trạng thái transaction không chắc chắn |

Để cảnh báo “worker ngừng xử lý”, nên kết hợp **consumer count + queue age + throughput + listener error rate**, thay vì chỉ nhìn một con số. Consumer còn kết nối không có nghĩa business handler khỏe mạnh.

### 10.2. Graceful shutdown

Khi service nhận tín hiệu dừng:

1. Ngừng nhận thêm công việc mới qua cơ chế lifecycle `Connection.stop()` hoặc container listener shutdown phù hợp.
2. Để callback đang chạy hoàn tất trong khoảng thời gian shutdown được phép.
3. Commit DB và JMS khi xử lý thành công; rollback hoặc để redelivery nếu không hoàn tất.
4. Đóng consumer/session/connection từ luồng quản lý, giải phóng resources.
5. Không buộc kill process giữa commit DB và ACK mà không có idempotency.

Trong Kubernetes hoặc orchestrator tương tự, thời hạn graceful termination phải đủ thực tế để xử lý message hoặc phải có chính sách rollback/redelivery rõ ràng. Một cờ `SIGTERM` không thay thế transaction.

### 10.3. Backpressure và số session

Tăng số listener đôi khi giúp tiêu thụ nhanh hơn, nhưng chỉ khi downstream chịu được. Nếu DB chỉ xử lý 100 request/s, tăng từ 10 lên 100 session có thể làm DB nghẽn hơn.

Đo tải với message size thật, ACK/commit thật, retry thật; cân nhắc window/prefetch của provider:

- Artemis JMS native client chịu cơ chế credit/consumer window của Artemis; tham số cấu hình cụ thể theo version/client.
- ActiveMQ Classic có prefetch policy riêng; không dùng nguyên cấu hình Artemis cho Classic.
- Window/prefetch lớn có thể khiến nhiều message đang nằm trong client và làm phân phối giữa các worker kém đều khi worker chậm.
- Window nhỏ có thể tăng tính công bằng nhưng giảm throughput trong điều kiện latency cao.

**Không đặt giá trị tối ưu cứng** nếu chưa đo workload thực. Thứ tự ưu tiên là an toàn transaction, backlog/SLA, rồi mới tinh chỉnh throughput.

## 11. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Quên `connection.start()` trong JMS classic API | Listener không nhận dù queue có message | Gắn listener rồi gọi `start()` |
| Đóng connection ngay sau `setMessageListener()` | Callback không có thời gian hoạt động | Duy trì lifecycle của service/worker |
| Dùng `AUTO_ACKNOWLEDGE` rồi đẩy task vào thread pool | Có thể ACK trước khi task xử lý xong | Dùng session/consumer concurrency và commit rõ ràng |
| Coi `message.acknowledge()` là ACK riêng message trong `CLIENT_ACKNOWLEDGE` | Có thể ACK các delivery khác cùng session | Thiết kế phạm vi session phù hợp, cân nhắc transacted session |
| Dùng cùng một `Session` từ nhiều thread | Race trong transaction/ACK/session state | Một session gắn với một luồng xử lý hoặc container quản lý |
| Catch exception, log rồi vẫn commit | Mất message dù nghiệp vụ thất bại | Rollback/phân loại lỗi rõ ràng |
| Retry message hỏng vô hạn | Backlog, log flood, giảm năng lực xử lý | Delay + max attempts + DLQ + re-drive có kiểm soát |
| Giả định DB/JMS là cùng transaction | Có thể xử lý trùng sau crash | Idempotency + outbox theo luồng dữ liệu |
| Không đo callback latency | Queue chậm dù consumer count vẫn bình thường | Metrics duration, queue age, downstream health |
| Coi `JMSRedelivered` là event ID | Không ngăn được tác dụng phụ trùng | Event ID ổn định + DB unique constraint |
| Đọc nhầm listener ExceptionListener và MessageListener | Lỗi nghiệp vụ không được xử lý đúng | Tách business error và connection/provider error |

## 12. Câu hỏi suy luận và bài tập mở rộng

### Câu hỏi 1: `onMessage` có thật sự “chạy song song” không?

Một listener gắn với một session được provider callback bất đồng bộ so với luồng `main`, nhưng **callback trong cùng session được tuần tự hóa**. Muốn xử lý nhiều message đồng thời, dùng nhiều session/consumer được quản lý đúng lifecycle.

### Câu hỏi 2: Vì sao nhận được `JMSRedelivered=true` dù code nghiệp vụ đã ghi thành công DB?

Vì broker chưa nhận được hoặc chưa xác nhận commit ACK thành công. DB có thể commit trước khi kết nối mất. Consumer phải dedup theo event ID và commit JMS sau khi xác nhận trạng thái nghiệp vụ phù hợp.

### Câu hỏi 3: `ExceptionListener` có tự động xử lý mọi exception từ `onMessage` không?

Không. `ExceptionListener` được thiết kế cho lỗi JMS/provider bất đồng bộ, đặc biệt ở cấp connection. Callback cần tự bắt lỗi nghiệp vụ và quyết định transaction, log, health state. Không dùng unchecked exception làm hợp đồng retry portable.

### Câu hỏi 4: Một worker có thể gửi 1.000 tác vụ vào `ExecutorService` ngay trong callback rồi gọi `session.commit()` không?

Chỉ nếu việc đưa vào executor **đã là một handoff bền vững và được thiết kế ACK rõ ràng**; với một queue RAM đơn thuần, commit sớm làm mất khả năng redelivery khi process chết trước khi chạy task. Nếu muốn concurrency, mở nhiều JMS session/consumer hoặc một cơ chế handoff bền vững có kiểm soát.

### Câu hỏi 5: DLQ có giải quyết mọi lỗi message không?

Không. DLQ giữ message bị xử lý thất bại theo chính sách broker để điều tra và re-drive. Nó không tự sửa schema, không đảo ngược API call trước đó, không ngăn trùng nghiệp vụ và không thay thế monitoring. Phải xây quy trình quan sát, phân loại, sửa và phát lại có kiểm soát.

### Bài tập tự làm

1. Chạy listener và gửi ba `TextMessage` lần lượt có `eventId` khác nhau. Thay phiên bản lab để xử lý nhiều message (bỏ `CountDownLatch` một lần); xác nhận mỗi delivery được commit.
2. Gửi một message có body `FAIL:simulate`, quan sát số lần giao lại và DLQ trên Artemis. Điều chỉnh `max-delivery-attempts` trong môi trường lab rồi chạy lại, **không chỉnh production** chỉ để thử nghiệm.
3. Chạy hai consumer **trên hai JMS Session riêng** cùng queue. Ghi `threadName`, `eventId`, thời gian xử lý; so sánh throughput và thứ tự hoàn tất.
4. Mô phỏng lỗi sau DB commit nhưng trước JMS commit bằng business handler có dedup. Chứng minh lần giao lại không gây tác dụng phụ thứ hai.
5. Bật metrics queue depth và callback duration. Tạo downstream latency để quan sát backpressure, rồi quyết định concurrency dựa trên dữ liệu.

## 13. Kết luận kỹ thuật

**`MessageListener` là điểm vào bất đồng bộ do JMS provider điều phối.** Kết nối chỉ bắt đầu delivery đúng cách khi listener đã được đăng ký và connection được start theo lifecycle phù hợp. Trong một JMS Session, callback được thực thi tuần tự; muốn song song phải tổ chức nhiều session/consumer hoặc dùng container listener.

Khả năng xử lý đáng tin cậy đến từ **ACK/commit sau khi hoàn thành nghiệp vụ, rollback cho lỗi, redelivery/DLQ có giới hạn, xử lý trùng lặp theo event ID và giám sát thời gian callback**. Với Artemis và ActiveMQ Classic, các API JMS tương đồng ở tầng khái niệm nhưng client artifact, namespace `jakarta.jms`/`javax.jms` và cấu hình broker khác nhau. Không nhầm một callback được gọi thành bằng chứng message đã được xử lý bền vững từ đầu đến cuối.
