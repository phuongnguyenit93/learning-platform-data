# Gửi và nhận đồng bộ bằng JMS API truyền thống

> **Chương:** Lập trình JMS  
> **Phạm vi:** Sử dụng `ConnectionFactory`, `Connection`, `Session`, `MessageProducer` và `MessageConsumer` để gửi/nhận thông điệp bằng API JMS cổ điển trên Apache ActiveMQ Artemis; đối chiếu với ActiveMQ Classic khi cần. Bài tập dùng **Jakarta Messaging** (`jakarta.jms`) nhưng giữ mô hình lập trình **JMS truyền thống**, không dùng `JMSContext` hoặc `JMSProducer`.

## 1. Hai thao tác “đồng bộ” có ý nghĩa gì?

Giả sử Order Service gửi thông điệp `OrderCreated` vào queue `lab.sync.orders`. Một worker khác đọc thông điệp, ghi nhận đơn hàng rồi xác nhận với broker. Khi sử dụng API JMS truyền thống, ta thường viết:

```java
producer.send(message);           // Gọi gửi theo API đồng bộ.
Message message = consumer.receive(5000L);  // Chờ tối đa 5 giây để nhận.
```

**Synchronous receive** có nghĩa là **luồng Java gọi `receive(...)` sẽ chờ** đến khi có message phù hợp, hết hạn chờ hoặc xảy ra lỗi. Không có callback `MessageListener` xử lý message trên một luồng do provider gọi. Đây là trọng tâm của bài.

**Synchronous send** nghĩa là ứng dụng gọi phương thức `MessageProducer.send(...)` rồi nhận kết quả/ngoại lệ trong cùng luồng. Tuy nhiên, thời điểm lệnh `send` trả về còn phụ thuộc cài đặt client và tùy chọn xác nhận gửi của provider. Nó **không chứng minh** consumer đã đọc, xử lý nghiệp vụ, commit database hoặc rằng broker có thể phục hồi message sau mọi kiểu sự cố.

```mermaid
sequenceDiagram
    participant O as Order Producer
    participant B as ActiveMQ Artemis
    participant W as Worker Consumer
    O->>B: producer.send(OrderCreated)
    B-->>O: send() hoàn tất theo ngữ nghĩa client/provider
    W->>B: connection.start(); consumer.receive(5000)
    alt Có message trong khoảng chờ
        B-->>W: Message
        W->>W: Đọc và xử lý
        W->>B: Ack/commit theo session mode
    else Hết 5000 ms
        B-->>W: null
    end
```

Trong một hệ thống bất đồng bộ, cả hai đầu **vẫn hoạt động độc lập theo thời gian** dù code gọi `send` và `receive` là đồng bộ. Producer không cần đợi worker đang chạy; message có thể được lưu tại broker rồi worker khởi động sau. Đừng nhầm “API nhận đồng bộ” với việc producer gọi trực tiếp một hàm của consumer.

**Kết quả cần đạt:** sau bài này, bạn phải tự chạy được producer và consumer Java ở **hai tiến trình riêng**, giải thích chính xác vì sao cần `Connection.start()`, khi nào `receive` trả về `null`, khi nào message được xác nhận và cách thay acknowledgment/transaction để tránh mất công việc đang xử lý.

## 2. Vai trò cụ thể của từng đối tượng trong API truyền thống

Chuỗi khởi tạo thường có dạng:

```text
ConnectionFactory (provider-specific configuration)
    └── Connection (kết nối logic đến provider)
          └── Session (ngữ cảnh gửi/nhận, ack, transaction)
                ├── Destination (Queue hoặc Topic)
                ├── MessageProducer → send(...)
                └── MessageConsumer → receive(...)
```

| Thành phần | Nhiệm vụ đúng | Sai lầm hay gặp |
|---|---|---|
| `ConnectionFactory` | Cấu hình endpoint, tạo `Connection`; interface JMS chuẩn, đối tượng triển khai phụ thuộc provider | Nghĩ factory chuẩn tự xác định OpenWire/Artemis Core mà không cần client library |
| `Connection` | Thiết lập connection logic, `start()`/`stop()` điều khiển delivery cho consumer, `close()` giải phóng tài nguyên | Không gọi `start()` rồi chờ `receive` đến hết timeout |
| `Session` | Tạo destination, producer, consumer, message; quản lý ack/transaction và thứ tự thao tác trong session | Chia sẻ một `Session` giữa nhiều luồng Java để gửi/nhận đồng thời |
| `Queue` / `Topic` | Đối tượng destination để producer/consumer tham chiếu | Tưởng `session.createQueue(name)` chắc chắn đã provisioning queue trên broker |
| `MessageProducer` | `send(...)` và các tùy chọn delivery mode, priority, TTL | Đồng nhất `send` thành công với nghiệp vụ phía consumer đã commit |
| `MessageConsumer` | `receive()`, `receive(timeout)`, `receiveNoWait()` hoặc async listener | Gọi blocking receive ngay trong luồng request HTTP mà không giới hạn thời gian |
| `Message` / `TextMessage` | Payload, header và typed properties | Dùng selector trên trường JSON trong body mà không đặt message property |

**Luồng sống của resource:**

1. Chọn client JMS/Jakarta phù hợp với broker.
2. Tạo `Connection` từ `ConnectionFactory` với credentials.
3. Tạo `Session`, xác định chế độ transaction và acknowledgment.
4. Tạo `Queue` và producer/consumer từ session.
5. Với **consumer**, gọi `connection.start()` trước khi chờ nhận.
6. Gửi hoặc nhận, xử lý lỗi và xác nhận message theo session mode.
7. Đóng consumer/producer, session, connection khi kết thúc.

Một `Connection` có thể có nhiều session, nhưng **`Session` là ngữ cảnh xử lý đơn luồng**, không được dùng cùng lúc từ nhiều thread. Đối với nhiều worker cạnh tranh đọc một queue, thường tạo **mỗi worker một session/consumer riêng**; tùy yêu cầu tải và cấu hình connection pool, chúng có thể dùng những connection riêng hoặc session riêng trên một connection được quản lý.

### 2.1. JMS truyền thống và API đơn giản hóa không phải hai giao thức

Đoạn code dưới đây đều dùng các khái niệm JMS, nhưng giao diện lập trình khác nhau:

```java
// API truyền thống (trọng tâm bài): Connection + Session
Connection connection = factory.createConnection(user, password);
Session session = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);

// API đơn giản hóa, có từ JMS 2.0:
// JMSContext context = factory.createContext(user, password);
```

Với **Jakarta Messaging 3.x**, interface mang package `jakarta.jms`. Với hệ cũ theo **JMS 1.1/JMS 2.0**, code thường import `javax.jms`. Đổi namespace phải đi cùng dependency/client tương ứng; không thể lấy một class chỉ triển khai `javax.jms.ConnectionFactory` rồi gán trực tiếp cho `jakarta.jms.ConnectionFactory`.

## 3. Chuẩn bị Artemis và Maven để chạy ví dụ

Bài tập sử dụng:

- JDK 17 và Maven.
- Broker Apache ActiveMQ **Artemis** đã chạy, nhận kết nối native client trên endpoint ví dụ `tcp://localhost:61616`.
- Một tài khoản được phép gửi/nhận message ở queue `lab.sync.orders`; mật khẩu đặt qua biến môi trường.
- Cấu hình queue `ANYCAST`, dành cho các consumer cạnh tranh lấy từng message.

Nếu broker không bật auto-create destination, đặt **một queue tồn tại sẵn** trong phần `<addresses>` của `broker.xml`:

```xml
<address name="lab.sync.orders">
    <anycast>
        <queue name="lab.sync.orders"/>
    </anycast>
</address>
```

Đây là **đoạn cấu hình bên trong `<addresses>`**, không phải một file `broker.xml` hoàn chỉnh. Nếu instance đã có phần tử `<addresses>`, thêm `<address>` tương ứng vào đó, không tạo wrapper trùng. Cập nhật/restart broker theo cơ chế triển khai của phiên bản đang dùng và xác nhận queue được tạo trong giao diện quản trị.

`session.createQueue("lab.sync.orders")` tạo **đối tượng JMS Queue phía client**; việc tự tạo address/queue trên Artemis phụ thuộc cấu hình auto-create và quyền của user. Nếu queue chưa tồn tại và không cho tự tạo, producer/consumer có thể gặp lỗi hoặc không có nơi nhận message như mong muốn.

### 3.1. `pom.xml` hoàn chỉnh

Dùng phiên bản client Artemis đã được kiểm thử với broker. Ví dụ ghim `2.38.0` cho lab này và dùng `artemis-jakarta-client` để import `jakarta.jms`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lab.messaging</groupId>
    <artifactId>jms-sync-traditional-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <artemis.version>2.38.0</artemis.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>${artemis.version}</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Phân biệt rõ:** `artemis-jakarta-client` là thư viện Java cho broker Artemis. API ứng dụng là `jakarta.jms`, còn giao tiếp native client thường dùng **Artemis Core** qua endpoint TCP đã cấu hình. Lệnh `mvn compile` biên dịch client Java; nó **không** khởi động broker.

## 4. Chương trình producer/consumer đồng bộ hoàn chỉnh

Tạo file `src/main/java/TraditionalJmsSyncLab.java`. Chương trình nhận hai chế độ `send <orderId>` và `receive [timeoutMs]`, dùng chính các interface JMS truyền thống, đặt property để phân biệt đơn hàng và in thông tin phục vụ kiểm chứng.

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
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class TraditionalJmsSyncLab {
    private static final String QUEUE_NAME = "lab.sync.orders";

    private static String optionalEnv(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            throw new IllegalArgumentException(
                    "Usage: send <orderId> | receive [timeoutMs]");
        }

        String mode = args[0];
        if ("send".equals(mode) && args.length != 2) {
            throw new IllegalArgumentException("Usage: send <orderId>");
        }
        if (!"send".equals(mode) && !"receive".equals(mode)) {
            throw new IllegalArgumentException(
                    "Unknown mode. Use send or receive");
        }

        long timeoutMs = 5000L;
        if ("receive".equals(mode) && args.length == 2) {
            timeoutMs = Long.parseLong(args[1]);
            if (timeoutMs <= 0L || timeoutMs > 60000L) {
                throw new IllegalArgumentException(
                        "timeoutMs must be in 1..60000");
            }
        }

        String url = optionalEnv(
                "BROKER_URL", "tcp://localhost:61616");
        String user = optionalEnv("BROKER_USER", "lab");
        String password = System.getenv("BROKER_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException("Set BROKER_PASSWORD");
        }

        // Factory cu the la client Artemis; cac bien con lai la JMS API.
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);
        Connection connection = factory.createConnection(user, password);
        try {
            // false: session khong giao dich.
            // AUTO_ACKNOWLEDGE: provider tu ack sau receive thanh cong.
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            try {
                Queue queue = session.createQueue(QUEUE_NAME);

                if ("send".equals(mode)) {
                    sendOrder(session, queue, args[1]);
                } else {
                    receiveOrder(connection, session, queue, timeoutMs);
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    private static void sendOrder(Session session, Queue queue,
                                  String orderId) throws JMSException {
        MessageProducer producer = session.createProducer(queue);
        try {
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);
            // TTL = 0: khong yeu cau expiration do producer.
            producer.setTimeToLive(0L);

            TextMessage message = session.createTextMessage(
                    "OrderCreated:" + orderId);
            message.setStringProperty("eventType", "OrderCreated");
            message.setStringProperty("orderId", orderId);

            producer.send(message);
            System.out.printf(
                    "SENT orderId=%s messageId=%s%n",
                    orderId, message.getJMSMessageID());
        } finally {
            producer.close();
        }
    }

    private static void receiveOrder(Connection connection, Session session,
                                     Queue queue, long timeoutMs)
            throws JMSException {
        MessageConsumer consumer = session.createConsumer(queue);
        try {
            // Bat buoc truoc khi cho nhan message.
            connection.start();
            long started = System.nanoTime();
            System.out.println("WAITING timeoutMs=" + timeoutMs);

            Message message = consumer.receive(timeoutMs);
            long waitedMs =
                    (System.nanoTime() - started) / 1_000_000L;

            if (message == null) {
                System.out.printf(
                        "TIMEOUT waitedMs=%d (khong co message)%n",
                        waitedMs);
                return;
            }

            if (!(message instanceof TextMessage)) {
                System.out.println("RECEIVED non-TextMessage:"
                        + message.getClass().getName());
                return;
            }

            TextMessage text = (TextMessage) message;
            System.out.printf(
                    "RECEIVED orderId=%s messageId=%s "
                    + "redelivered=%s waitedMs=%d body=%s%n",
                    message.getStringProperty("orderId"),
                    message.getJMSMessageID(),
                    message.getJMSRedelivered(),
                    waitedMs,
                    text.getText());
            // AUTO_ACKNOWLEDGE: khong goi message.acknowledge().
        } finally {
            consumer.close();
        }
    }
}
```

**Tại sao code dùng `try/finally` thay vì lược bỏ `close()`?** Ví dụ mô phỏng đúng vòng đời resource của API truyền thống, hoạt động cả khi `send` hoặc `receive` ném `JMSException`. Các API JMS/Jakarta mới hỗ trợ thêm tiện ích đóng resource, nhưng hiểu `close()` vẫn quan trọng đối với codebase cũ. Trong chương trình dài hạn, tạo resource lúc startup và quản lý pool theo framework thay vì mở connection mới cho từng message.

### 4.1. Điều cần quan sát trong source

**Đường gửi:**

```java
Session session = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);
Queue queue = session.createQueue("lab.sync.orders");
MessageProducer producer = session.createProducer(queue);
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.send(session.createTextMessage("OrderCreated:O-1001"));
```

Producer **không cần gọi `connection.start()`** để gửi message. `start()` điều khiển việc giao message đến consumer của connection. Với một send thuần túy, sau `producer.send(...)` ứng dụng cần đóng resource ở điểm phù hợp.

**Đường nhận:**

```java
MessageConsumer consumer = session.createConsumer(queue);
connection.start();
Message message = consumer.receive(5000L);
if (message == null) {
    // Khong co message trong khoang cho.
} else {
    // Da nhan message; AUTO_ACKNOWLEDGE co semantics rieng.
}
```

Tạo `MessageConsumer` trước hay sau `connection.start()` đều có thể hợp lệ; điều quan trọng là delivery trên connection phải được bật trước khi chờ nhận. Đối với một message chưa có trong queue, `receive` chặn **luồng đang gọi**, chứ không chặn JVM hay broker.

## 5. Chạy thử hai tiến trình để nhìn thấy việc chờ đồng bộ

Đặt biến môi trường tại **mỗi terminal** chạy Maven. Trên Bash/WSL:

```bash
export BROKER_URL='tcp://localhost:61616'
export BROKER_USER='lab'
export BROKER_PASSWORD='replace-with-your-lab-password'
```

Trên PowerShell:

```powershell
$env:BROKER_URL = 'tcp://localhost:61616'
$env:BROKER_USER = 'lab'
$env:BROKER_PASSWORD = 'replace-with-your-lab-password'
```

### Thí nghiệm A — Nhận trước, gửi sau

1. Đảm bảo queue `lab.sync.orders` không còn message thử nghiệm cũ; chỉ purge đúng queue lab nếu cần và có quyền xóa dữ liệu.
2. Mở **Terminal A**, chạy consumer với thời gian chờ 15 giây.
3. Trong khoảng 15 giây đó, mở **Terminal B**, chạy producer với order ID cụ thể.
4. Quan sát Terminal A thoát trạng thái chờ và in đúng order ID cùng message ID. Nếu quá 15 giây mới gửi, consumer đã trả về `TIMEOUT` và producer vẫn có thể gửi message vào queue để lần nhận sau lấy ra.

Terminal A:

```bash
mvn -q compile exec:java -Dexec.mainClass=TraditionalJmsSyncLab -Dexec.args="receive 15000"
```

Terminal B, chạy khi A đang ở dòng `WAITING`:

```bash
mvn -q compile exec:java -Dexec.mainClass=TraditionalJmsSyncLab -Dexec.args="send O-1001"
```

Ví dụ đầu ra **minh họa**, không phải số liệu cố định:

```text
# Terminal B
SENT orderId=O-1001 messageId=ID:...

# Terminal A
WAITING timeoutMs=15000
RECEIVED orderId=O-1001 messageId=ID:... redelivered=false waitedMs=... body=OrderCreated:O-1001
```

Hai lần in `messageId` được dùng để đối chiếu xem consumer nhận **đúng message đã gửi**. Trong trường hợp chỉ có một message và không có consumer khác cạnh tranh, chúng phải khớp nhau; trên hệ thống thực tế hãy dùng thêm `orderId` hoặc event ID nghiệp vụ để tra cứu.

### Thí nghiệm B — Chờ hết thời gian

Khi queue trống và không có producer, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=TraditionalJmsSyncLab -Dexec.args="receive 2000"
```

Kỳ vọng: `TIMEOUT waitedMs=...` và **không có message nào được xác nhận hay xóa chỉ vì timeout**. Con số thời gian đo có thể lệch nhẹ do JVM scheduling, network và overhead.

### Thí nghiệm C — Gửi trước, nhận sau

Chạy producer trước và đóng ứng dụng. Sau đó mới chạy consumer:

```bash
mvn -q compile exec:java -Dexec.mainClass=TraditionalJmsSyncLab -Dexec.args="send O-1002"
mvn -q compile exec:java -Dexec.mainClass=TraditionalJmsSyncLab -Dexec.args="receive 5000"
```

Nếu broker đang giữ queue và message chưa bị consumer khác ack/expiry, consumer sẽ nhận `O-1002` dù producer đã ngừng chạy. Điều này kiểm chứng tính **bất đồng bộ giữa hai dịch vụ** trong khi mỗi lời gọi API Java vẫn đồng bộ.

## 6. Ba biến thể `receive` và giới hạn thời gian

| Lời gọi | Chờ bao lâu? | Khi không có message | Khi phù hợp |
|---|---|---|---|
| `consumer.receive()` | Chờ vô thời hạn cho đến khi có message hoặc tình huống ngắt/lỗi thích hợp | Không tự trả về theo timeout | Worker chuyên dụng có cơ chế shutdown rõ ràng |
| `consumer.receive(5000L)` | Chờ tối đa khoảng 5 giây | Trả về `null` nếu timeout | Poll có thời hạn, vòng xử lý chủ động kiểm tra dừng |
| `consumer.receive(0L)` | **Chờ vô thời hạn**, tương đương không cung cấp timeout | Không tự timeout | Cần hiểu rõ để không vô tình treo thread |
| `consumer.receiveNoWait()` | Không chờ message | Trả về `null` ngay khi không có message sẵn sàng | Thử trạng thái queue không blocking, kiểm tra nhanh |

**Không chọn `receive(0)` để biểu diễn “không chờ”.** Đây là lỗi thiết kế rất thường gặp. Muốn không chờ, dùng `receiveNoWait()`.

Lời gọi timeout của JMS **không** phải timeout tổng cho việc thực thi business logic sau khi nhận. Nếu `receive(5000)` trả về sau 300 ms rồi code xử lý database 30 giây, tổng thời gian method của ứng dụng vẫn có thể hơn 30 giây. Đồng thời nó không thay thế timeout mở kết nối, reconnect, DNS hoặc các cấu hình failover của client.

### 6.1. Thiết kế vòng worker polling có điểm thoát

Ví dụ đoạn code thuộc một session/consumer đã tạo, connection đã `start()`:

Một lựa chọn dễ kiểm soát là cờ `AtomicBoolean` được thành phần quản lý vòng đời của worker giữ và truyền vào vòng xử lý. Ví dụ sau là đoạn code bên trong worker đã sở hữu `consumer`; hàm `processBusinessMessage` do ứng dụng tự triển khai:

```java
import java.util.concurrent.atomic.AtomicBoolean;

AtomicBoolean running = new AtomicBoolean(true); // Duoc lifecycle manager quan ly.
while (running.get()) {
    Message message = consumer.receive(1000L);
    if (message != null) {
        processBusinessMessage(message);
    }
}
```

Khi ngừng worker, lifecycle manager đặt `running.set(false)`, chờ vòng `receive(1000)` kết thúc rồi đóng consumer/session/connection. Không đóng hoặc dùng cùng `Session` đồng thời từ nhiều thread một cách tùy tiện; cách tổ chức shutdown phải phù hợp vòng đời và thread ownership của thư viện/provider. Trong ứng dụng thực, nên kết hợp timeout hữu hạn, cancellation và monitoring thay vì polling liên tục không có điểm kết thúc.

### 6.2. Message selector khi nhận đồng bộ

API truyền thống có overload `session.createConsumer(destination, selector)`:

```java
MessageConsumer consumer = session.createConsumer(
        queue, "eventType = 'OrderCreated'");
connection.start();
Message message = consumer.receive(5000L);
```

Selector so khớp **message header/property**, không parse JSON body. Producer trong bài đã gọi `setStringProperty("eventType", "OrderCreated")` nên selector ở trên có dữ liệu phù hợp. Nếu selector không match, consumer có thể trả về `null` dù queue đang chứa message loại khác. Đừng kết luận queue trống chỉ từ `receive(timeout) == null` trên một consumer có selector.

## 7. AUTO_ACKNOWLEDGE: nhận đồng bộ không có nghĩa đã xử lý nghiệp vụ

Trong chương trình đầu tiên, ta tạo session:

```java
Session session = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);
```

Với **`receive` đồng bộ** và `AUTO_ACKNOWLEDGE`, JMS provider có thể xem message đã được xác nhận khi **lời gọi nhận trả về thành công**. Nếu business logic chạy *sau* `receive`, message có thể đã được ack **trước khi database commit**.

```text
consumer.receive() tra Message
    ↓ provider auto-ack theo semantics cua session
application ghi don hang vao database
    ↓ JVM chet truoc khi ghi xong
broker co the khong redeliver message da ack
```

Đây là rủi ro cốt lõi: code đơn giản `receive()` → `process()` **không tự bảo đảm xử lý ít nhất một lần** ở tầng nghiệp vụ. Nếu nhiệm vụ là gửi log thử nghiệm hoặc dữ liệu có thể tái tạo, AUTO_ACKNOWLEDGE có thể đủ. Nếu nghiệp vụ cần xử lý thành công trước khi ack, hãy cân nhắc `CLIENT_ACKNOWLEDGE` hoặc **session giao dịch**.

### 7.1. CLIENT_ACKNOWLEDGE: tự xác nhận sau khi xử lý

Thay chế độ tạo session:

```java
Session session = connection.createSession(
        false, Session.CLIENT_ACKNOWLEDGE);
MessageConsumer consumer = session.createConsumer(queue);
connection.start();

Message message = consumer.receive(5000L);
if (message != null) {
    try {
        processBusinessMessage(message); // Ham nghiep vu do ban cai dat.
        message.acknowledge();           // Chi sau khi process thanh cong.
    } catch (Exception ex) {
        session.recover(); // Non-transacted: yeu cau redelivery phu hop.
        throw ex;
    }
}
```

Mã trên là **đoạn thay thế nằm trong vòng đời connection/session được quản lý**, không phải class Java độc lập; hãy đóng consumer/session/connection trong khối `finally` tương ứng. `Session.recover()` dành cho **non-transacted session**; không gọi thay cho `rollback()` ở transacted session.

**Điểm rất quan trọng:** trong một session `CLIENT_ACKNOWLEDGE`, `message.acknowledge()` xác nhận **tất cả message đã được session đó tiêu thụ và đang chờ ack**, không chỉ một message có ID đang cầm. Nếu muốn phạm vi rõ ràng, nhận và xử lý từng message một trong session, hoặc dùng transacted session có ranh giới commit được thiết kế cẩn thận.

Một cách hỏng thường gặp: code nhận 10 message cùng một session, xử lý message đầu tiên và gọi `acknowledge()`; thao tác này có thể ack cả những message đã được nhận trước đó nhưng chưa hoàn tất xử lý. Vì vậy nếu dùng batch, phải xem toàn batch là một đơn vị có chính sách xử lý lỗi tương ứng.

### 7.2. DUPS_OK_ACKNOWLEDGE có phải giải pháp cho nghiệp vụ quan trọng?

`Session.DUPS_OK_ACKNOWLEDGE` cho phép provider **trì hoãn acknowledgment** để tối ưu hiệu năng và chấp nhận khả năng **giao lặp**. Nó không thay thế transaction hoặc idempotency. Với dữ liệu đơn hàng cần kiểm soát chính xác lúc hoàn tất, nên ưu tiên một chính sách ack rõ ràng hơn.

## 8. SESSION_TRANSACTED: nhận, xử lý rồi commit/rollback

Một hướng thực hành dễ kiểm chứng là dùng session giao dịch:

```java
Session session = connection.createSession(
        true, Session.SESSION_TRANSACTED);
```

Khi `transacted=true`, chế độ ack thông thường không còn là cơ chế xác nhận chính; **`session.commit()`** xác nhận các thao tác JMS trong transaction, và **`session.rollback()`** hủy transaction cùng trạng thái xử lý nhận phù hợp để broker có thể phân phối lại.

### 8.1. Consumer giao dịch (đoạn xử lý hoàn chỉnh về mặt flow)

```java
Session session = connection.createSession(
        true, Session.SESSION_TRANSACTED);
try {
    Queue queue = session.createQueue("lab.sync.orders");
    MessageConsumer consumer = session.createConsumer(queue);
    try {
        connection.start();
        Message message = consumer.receive(5000L);
        if (message == null) {
            System.out.println("TIMEOUT");
        } else {
            try {
                String orderId = message.getStringProperty("orderId");
                processOrderIdempotently(orderId); // Ham nghiep vu cua app.
                session.commit();                   // Ack JMS transaction.
                System.out.println("COMMITTED " + orderId);
            } catch (Exception ex) {
                session.rollback();
                System.err.println("ROLLED_BACK: " + ex.getMessage());
                throw ex;
            }
        }
    } finally {
        consumer.close();
    }
} finally {
    session.close();
}
```

`processOrderIdempotently` là hàm cần triển khai và phải bảo đảm không tạo tác dụng lặp (ví dụ unique constraint theo `orderId`). Đoạn trên là minh họa được đặt **bên trong khối quản lý connection**; không có ngụ ý rằng transaction JMS bao trùm database riêng.

Nếu consumer ghi database thành công rồi JVM chết **trước** `session.commit()`, broker có thể redeliver message sau reconnect. Nếu không có idempotency, consumer có thể tạo lại đơn/lần thanh toán. Mục tiêu thực tế thường là **at-least-once delivery cộng với xử lý nghiệp vụ idempotent**, thay vì tuyên bố exactly-once end-to-end chỉ nhờ JMS transaction.

### 8.2. Producer giao dịch: `send` chưa đủ nếu chưa `commit`

```java
Session session = connection.createSession(
        true, Session.SESSION_TRANSACTED);
try {
    Queue queue = session.createQueue("lab.sync.orders");
    MessageProducer producer = session.createProducer(queue);
    try {
        producer.setDeliveryMode(DeliveryMode.PERSISTENT);
        TextMessage message = session.createTextMessage("OrderCreated:O-2001");
        message.setStringProperty("orderId", "O-2001");
        producer.send(message);

        // Truoc commit: JMS transaction chua duoc xac nhan hoan tat.
        session.commit();
    } catch (JMSException ex) {
        session.rollback();
        throw ex;
    } finally {
        producer.close();
    }
} finally {
    session.close();
}
```

Trong transacted session, kết quả gửi có hiệu lực theo `commit()`; một lần `rollback()` không tạo message đã commit trong queue. Đừng nhầm `DeliveryMode.PERSISTENT` với “tự commit”. Persistence nói về kỳ vọng lưu trữ khi message hợp lệ được broker chấp nhận; **transaction** nói về việc hoàn tất nhóm thao tác gửi/nhận.

### 8.3. Ba mức bảo đảm cần tách biệt

| Tầng | Bảo đảm/chính sách đang xét | Điều không được suy ra |
|---|---|---|
| Gửi tới broker | `send`, TTL, persistent delivery, producer transaction `commit` | Consumer đã thực hiện nghiệp vụ |
| Nhận và xác nhận | `receive`, ack, `commit`/`rollback`, redelivery và DLQ | Database của consumer được commit nguyên tử với JMS |
| Nghiệp vụ ngoài broker | Transaction database, unique key, inbox/outbox, idempotency | Broker sẽ ngăn mọi lần xử lý trùng của application |

Đối với consumer nhận đồng bộ, quyết định dùng AUTO_ACK, CLIENT_ACK hay SESSION_TRANSACTED phải đến từ **mốc xử lý thành công của nghiệp vụ**, không phải từ sở thích về cú pháp Java.

## 9. Sự khác nhau giữa queue và topic khi nhận đồng bộ

Mẫu `connection.start(); consumer.receive(timeout)` cũng áp dụng cho `Topic`:

```java
Topic topic = session.createTopic("orders.events");
MessageConsumer consumer = session.createConsumer(topic);
connection.start();
Message message = consumer.receive(5000L);
```

Nhưng với **non-durable topic subscriber**, thông điệp publish trong lúc subscriber chưa tồn tại hoặc offline thường **không được broker giữ riêng** cho subscriber đó. Với queue, thông điệp có thể ở lại cho consumer khác hoặc lần kết nối sau nếu chưa ack/expire. Vì vậy một demo “gửi trước, nhận sau” với topic non-durable **không tương đương** demo queue trong mục 5.

Nếu subscriber topic cần nhận những sự kiện xuất hiện khi offline, dùng **durable subscription** với định danh ổn định và các điều kiện persistence phù hợp. Chủ đề durable client ID/subscription name có cơ chế riêng; trong bài này chỉ cần nhớ rằng **blocking receive không tạo ra durability**.

Trong trường hợp có hai consumer đọc **cùng một queue**, chúng **cạnh tranh** để nhận mỗi message. Với hai non-durable subscribers độc lập của cùng topic khi online, mỗi subscription có thể nhận một bản sự kiện. Do đó, hiểu đúng destination là điều kiện để giải thích kết quả `receive(...)`.

## 10. Quản lý kết nối, shutdown và lỗi khi sử dụng API đồng bộ

### 10.1. `Connection.start()` và `stop()`

| Lời gọi | Tác động thực tế |
|---|---|
| `createConnection(...)` | Tạo connection logic; chưa tự động bắt đầu phân phối message như một consumer đã start |
| `connection.start()` | Cho phép giao message đến consumers của connection; idempotent khi đã start |
| `connection.stop()` | Tạm dừng delivery đến consumers của connection; không phải hủy queue hoặc message |
| `connection.close()` | Đóng connection, session và resources liên quan theo provider; không thay cho `unsubscribe` durable subscription |

Trong JMS truyền thống, **`Connection.start()` không đồng nghĩa mở TCP socket lần đầu**: factory có thể đã khởi tạo network resource khi tạo connection. Tác dụng mà code cần ghi nhớ là **cho phép message được giao đến consumer**. Producer vẫn có thể gửi khi connection chưa `start`.

Nếu ứng dụng đóng resource trong khi còn transaction chưa hoàn tất, cần xác minh chính sách rollback/recovery và trạng thái message theo broker/client. Đừng dùng “đóng connection để commit”, cũng đừng dựa vào `stop()` như cơ chế xác nhận thành công.

### 10.2. Blocking receive và xử lý shutdown

Một worker chạy `receive()` không giới hạn thời gian có thể khó dừng theo ý muốn nếu không có cơ chế lifecycle. Dùng `receive(1000)` hoặc timeout hữu hạn khi worker cần kiểm tra trạng thái dừng; giảm timeout khi cần shutdown nhanh, nhưng không polling `receiveNoWait()` liên tục gây CPU cao.

`Session` và consumer **không được dùng tùy tiện từ nhiều thread**. Đừng cho thread khác vừa gọi `session.close()` vừa gọi `session.commit()` mà không có giao thức dừng rõ ràng. Một request HTTP đang chạy trên thread pool cũng không nên gọi `receive()` không timeout, vì các request có thể bị giữ lâu và làm cạn thread pool.

### 10.3. Phân biệt timeout nhận và lỗi kết nối

**`receive(timeout) == null`** chỉ nói rằng trong khoảng chờ hiện tại, consumer **không được trả về một message**. Nó không khẳng định broker không có message nào: message có thể ở queue khác, bị selector lọc, đang delivering cho consumer khác, bị expiry hoặc đã chuyển DLQ.

Nếu broker không tới được, chứng thực thất bại hay transport lỗi, thao tác JMS có thể ném **`JMSException`**. Đó là một dạng lỗi khác `null` do timeout. Đừng chuyển mọi `JMSException` thành kết quả “queue rỗng”; làm vậy sẽ che giấu outage.

Bạn có thể đăng ký `ExceptionListener` cho connection để quan sát một số lỗi kết nối bất đồng bộ:

```java
connection.setExceptionListener(exception ->
        System.err.println("ASYNC JMS ERROR: " + exception.getMessage()));
```

Listener lỗi **không thay thế** `try/catch` quanh `send`, `receive` hoặc `commit`. Nếu callback được gọi trên thread riêng, tránh truy cập session/consumer không thread-safe từ callback đó; phát tín hiệu cho lifecycle manager xử lý kết nối.

### 10.4. Chọn số connection/session phù hợp

Trong ứng dụng production, tạo mới `Connection` và `Session` cho **mỗi message** thường tốn thời gian thiết lập và xác thực. Có thể tái sử dụng resource an toàn, dùng connection/session pooling do framework quản lý hoặc một worker sở hữu session của riêng nó. Ngược lại, **một session chia sẻ cho nhiều request/thread** là thiết kế sai do session không thread-safe.

Đối với ActiveMQ Artemis, cấu hình reconnect/failover, heartbeat, TLS, durable persistence, paging, address security và broker HA là các quyết định bổ sung. Những tính năng này không làm thay đổi ngữ nghĩa cơ bản của `receive(timeout)`, ack/transaction; chúng quyết định cách chương trình phục hồi trước lỗi thực tế.

## 11. Khi thay Artemis bằng ActiveMQ Classic

Mô hình lập trình của bài vẫn gồm các API truyền thống: `ConnectionFactory` → `Connection` → `Session` → `MessageProducer/MessageConsumer` → `send/receive`. Điều cần thay đổi là **client library/namespace, URI và cấu hình broker**, không chỉ tên cổng.

| Yếu tố | Ví dụ Artemis | Ví dụ ActiveMQ Classic |
|---|---|---|
| Broker | Apache ActiveMQ Artemis | Apache ActiveMQ Classic |
| Factory class điển hình | `org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory` | `org.apache.activemq.ActiveMQConnectionFactory` |
| API import ở bài này | `jakarta.jms.*` | Thường gặp `javax.jms.*` với client Classic thuộc dòng JMS cũ |
| Native protocol phổ biến | Artemis Core | OpenWire |
| URL ví dụ | `tcp://localhost:61616` theo acceptor cấu hình | `tcp://localhost:61616` theo transport connector cấu hình |
| Queue provisioning | Artemis address/anycast queue và auto-create policy | Destination policy/auto-create và cấu hình broker Classic |

**Cùng URL `tcp://localhost:61616` không chứng minh hai client tương thích**. Mỗi bên cần cùng một wire protocol được broker tiếp nhận; client class của Artemis khác client class của Classic. Nếu dùng Classic với `javax.jms`, đổi toàn bộ import và dependency tương ứng. Đừng trộn `artemis-jakarta-client` với API `javax.jms` chỉ vì cùng gọi là JMS.

Khi migration, xác minh thêm persistence, session acknowledgment, transaction, redelivery policy, DLQ, selector và broker security. Một message bị xử lý lặp hoặc hết hạn do cấu hình broker có thể khiến kết quả thực hành khác nhau dù phương thức `receive(...)` trong Java giống hệt.

## 12. Các tình huống hỏng và cách kiểm tra có thứ tự

| Triệu chứng | Nguyên nhân thường gặp | Kiểm chứng/khắc phục |
|---|---|---|
| `receive(5000)` luôn trả `null` | Chưa `connection.start()`; queue sai; producer gửi khác địa chỉ; selector không match; consumer khác đã nhận | Kiểm tra start, tên queue/address, selector, consumer count và ready/delivering |
| `receive()` treo lâu | Dùng overload không timeout hoặc `receive(0)`; queue không có message | Dùng timeout hữu hạn và cơ chế shutdown |
| Producer in `SENT` nhưng queue trống | Consumer đã ack nhanh; queue chưa được provision; TTL expiry; route khác; broker/client gửi thất bại nhưng xử lý lỗi sai | Tạm dừng consumers, theo dõi message added/ack, queue bindings và log |
| Đọc lại message sau khi worker crash | Chưa commit/ack, broker redeliver | Kiểm tra session mode, transaction và idempotency |
| Không redeliver dù xử lý database lỗi | `AUTO_ACKNOWLEDGE` xác nhận khi `receive` thành công trước xử lý nghiệp vụ | Chuyển sang CLIENT_ACK hoặc transacted session khi cần |
| `message.acknowledge()` làm nhiều message biến mất | `CLIENT_ACKNOWLEDGE` xác nhận các message session đã tiêu thụ | Rà soát phạm vi session/batch, tách session hoặc dùng transaction |
| `send()` trả về nhưng lần restart sau không có message | Chưa commit producer transaction; non-persistent; cấu hình persistence/volume; message đã ack/expired | Kiểm tra producer transaction, delivery mode, storage, TTL và shutdown |
| Lỗi `JMSException` khi kết nối | Sai credentials, broker tắt, endpoint hoặc protocol không khớp | Kiểm tra logs, URL/acceptor, TLS và quyền user; không xem như timeout nhận |
| Hai worker cùng nhận một `orderId` qua các thời điểm | Redelivery sau rollback/crash hoặc producer gửi trùng | Đối chiếu `JMSMessageID`, business ID, `JMSRedelivered` và xử lý idempotent |
| Tốc độ xử lý thấp | Mỗi message mở connection mới; worker nhận đồng bộ một luồng; database chậm | Tái sử dụng resource, tăng số worker/session độc lập, đo latency và backlog |

### 12.1. Bộ quan sát tối thiểu cho lab

Trong broker management console, đo ở đúng queue `lab.sync.orders`:

- **Message count/ready:** số message còn chờ consumer.
- **Delivering count:** message đã giao nhưng chưa hoàn tất acknowledgment/transaction, tùy trạng thái broker.
- **Consumer count:** số consumer đang gắn queue.
- **Messages added/acknowledged:** phân biệt producer không gửi, consumer nhận quá nhanh hoặc message đang được retry.
- **DLQ/expiry:** nơi message có thể được chuyển đến sau thất bại hoặc hết TTL theo policy.

Khi debug, ghi **orderId và JMSMessageID** ở cả hai phía. Nếu cần chụp queue depth trước khi tiêu thụ, ngắt consumer hoặc dùng công cụ duyệt message không ack được broker hỗ trợ; chạy `receive` với AUTO_ACK rồi chỉ “in cho xem” cũng đã có thể làm queue giảm số lượng.

## 13. Bài tập vận dụng và tiêu chí kiểm chứng

**Bài 1 — So sánh blocking và timeout.** Bắt đầu từ queue trống. Chạy `receive 5000` và không gửi gì; đo thời gian trả `null`. Sau đó chạy `receive 15000` và gửi `O-3001` sau khi consumer đã bắt đầu chờ. Giải thích vì sao hai lần có kết quả khác nhau.

**Bài 2 — Thiếu `Connection.start()`.** Trong một nhánh lab riêng, tạm bỏ dòng `connection.start()` ở consumer rồi chạy `receive(2000)` khi queue có message. Quan sát hành vi; bật lại `start()` rồi nhận và xác minh đúng message ID. Đừng purge queue để “sửa” lỗi start.

**Bài 3 — Thay AUTO_ACK bằng CLIENT_ACK.** Tạo session CLIENT_ACK, chỉ gọi `acknowledge()` sau khi giả lập xử lý thành công. Với trường hợp giả lập lỗi, gọi `session.recover()` rồi quan sát `JMSRedelivered` và số lần giao lại theo chính sách broker.

**Bài 4 — Transaction và rollback.** Dùng `SESSION_TRANSACTED`, gửi `O-3002` nhưng rollback trước commit; xác minh không có message từ transaction đó. Gửi lại và commit, consumer nhận rồi rollback một lần, nhận lại và cuối cùng commit. Giải thích vì sao `send` chưa đồng nghĩa commit và vì sao nhận lại không phải broker lỗi.

**Bài 5 — Hai consumer cạnh tranh.** Chạy hai tiến trình `receive 15000` trên **cùng queue**, sau đó gửi một message. Thông thường chỉ **một** consumer nhận message, tiến trình còn lại trả timeout; lặp với nhiều message để quan sát phân phối. Không kỳ vọng chia đều tuyệt đối.

**Bài 6 — Selector.** Đổi consumer thành `createConsumer(queue, "eventType = 'OrderCreated'")`. Gửi một message có property `eventType=OrderCancelled` (bổ sung chế độ gửi nếu cần) và một message `OrderCreated`. Xác minh consumer có selector chỉ nhận loại phù hợp, rồi dùng consumer không selector để kiểm tra message còn chờ.

**Bài 7 — Đánh giá rủi ro nghiệp vụ.** Lập timeline cho hai trường hợp (a) database commit rồi JMS commit thất bại, (b) AUTO_ACK trả message xong JVM chết trước database commit. Nêu dữ liệu có thể bị lặp hoặc mất hiệu ứng nghiệp vụ và đề xuất unique key/idempotency phù hợp.

### Câu hỏi tự kiểm tra

1. Vì sao producer không cần `Connection.start()` nhưng consumer lại cần?
2. `receive(0)` khác `receiveNoWait()` ở điểm nào?
3. Sau khi `receive(timeout)` trả `null`, bạn có thể khẳng định queue hoàn toàn rỗng không? Vì sao?
4. `AUTO_ACKNOWLEDGE` xác nhận vào mốc nào khi nhận đồng bộ? Rủi ro với xử lý database là gì?
5. `CLIENT_ACKNOWLEDGE` xác nhận một message hay toàn bộ message session đã nhận và chưa ack?
6. `Session.rollback()` khác `Session.recover()` ở chỗ nào?
7. Vì sao `DeliveryMode.PERSISTENT`, `session.commit()` và idempotency là ba yêu cầu khác nhau?

**Tiêu chí hoàn thành bài:** bạn chạy được một producer và consumer Java tách tiến trình bằng `Connection`/`Session`/`MessageProducer`/`MessageConsumer`; chứng minh được `receive` chờ rồi nhận hoặc timeout; giải thích được ý nghĩa của `Connection.start()`; chuyển đổi được giữa AUTO_ACK, CLIENT_ACK và SESSION_TRANSACTED; có bằng chứng đối chiếu `orderId`/`JMSMessageID` và biết đọc queue state trên Artemis để chẩn đoán lỗi.
