# JMSContext, JMSProducer, JMSConsumer và cách kiểm tra hỗ trợ của provider

> **Chương:** Lập trình JMS  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue, topic, routing và JMS; producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành tin cậy.  
> **Trọng tâm:** Bộ API đơn giản hóa được giới thiệu từ **JMS 2.0** (`JMSContext`, `JMSProducer`, `JMSConsumer`), vòng đời và semantics thực tế của nó, cùng cách kiểm tra **provider/client phiên bản cụ thể** có thật sự hỗ trợ từng tính năng hay không. Bài dùng **Artemis 2.57.0 + Jakarta Messaging 3.x** làm ví dụ chạy chính, và đối chiếu có kiểm soát với ActiveMQ Classic 5.x/6.x.

## 1. Mục tiêu học tập và câu hỏi nền tảng

Sau bài này, bạn có thể:

1. Chuyển cách viết `Connection + Session + MessageProducer + MessageConsumer` sang `JMSContext + JMSProducer + JMSConsumer` mà vẫn hiểu connection, session và acknowledgment.
2. Chọn đúng session mode, đóng tài nguyên, xử lý `JMSRuntimeException` và tránh việc `AUTO_ACKNOWLEDGE` xác nhận message quá sớm.
3. Viết producer/consumer dùng message property, selector, correlation ID, TTL, persistent delivery, `CLIENT_ACKNOWLEDGE` và `SESSION_TRANSACTED`.
4. Giải thích được khác nhau giữa `receive()`, `receiveBody()` và `MessageListener`, cùng những hạn chế thread-safety khi sử dụng `JMSContext`.
5. Phân biệt **API có trên classpath**, **phương thức được provider hiện thực**, và **hành vi đã được thử nghiệm end-to-end**.
6. Đọc metadata của provider, thử một tính năng trên destination cô lập, phân loại lỗi `UnsupportedOperationException` khác với timeout, lỗi kết nối và lỗi quyền.
7. Chọn đúng Maven dependency/namespace cho Artemis, Classic; biết một số tính năng JMS 2.0/Jakarta Messaging vẫn **chưa hoàn chỉnh** ở một số bản ActiveMQ Classic.

**Bài toán:** Một ứng dụng Java cần gửi `CreateInvoice` vào queue và một worker nhận, lưu kết quả rồi ack. Bạn muốn rút gọn code JMS và chuẩn bị chuyển từ ActiveMQ Classic sang Artemis. `JMSContext` giúp code ngắn hơn, nhưng **không tự sửa vấn đề giao dịch, gửi trùng, thiếu ACL hay khác biệt provider**.

## 2. API đơn giản hóa thay thế những gì?

JMS 1.1 thường sử dụng:

```java
Connection connection = factory.createConnection();
Session session =
    connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
Queue queue = session.createQueue("orders.incoming");
MessageProducer producer = session.createProducer(queue);
connection.start();
producer.send(session.createTextMessage("hello"));
// Sau đó phải close producer, session, connection đúng thứ tự.
```

JMS 2.0 đưa vào API đơn giản hóa:

```java
try (JMSContext context =
         factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
    Queue queue = context.createQueue("orders.incoming");
    context.createProducer().send(queue, "hello");
}
```

| API JMS truyền thống | API đơn giản hóa | Điểm không được quên |
|---|---|---|
| `Connection` + `Session` | `JMSContext` | Connection và session **vẫn tồn tại về ngữ nghĩa** |
| `session.createProducer(destination)` | `context.createProducer()` | `JMSProducer.send(destination, body/message)` nhận destination ngay khi gửi |
| `MessageProducer` | `JMSProducer` | Fluent setters cho delivery mode, priority, TTL, property, header |
| `MessageConsumer` | `JMSConsumer` | Vẫn phụ thuộc session mode, selector và kiểu destination |
| `connection.start()` | Consumer được **auto-start** theo mặc định khi tạo từ context | Có thể dùng `setAutoStart(false)` trước lúc tạo consumer |
| `JMSException` checked cho phần lớn lời gọi | `JMSRuntimeException` unchecked cho simplified API | Không vì unchecked mà bỏ xử lý lỗi |
| Đóng từng connection/session/consumer | `JMSContext.close()`, `JMSConsumer.close()` | `JMSContext` implements `AutoCloseable`; `JMSProducer` **không có `close()`** |

Sơ đồ vòng đời:

```mermaid
flowchart TD
    CF["ConnectionFactory<br/>cấu hình endpoint + credentials"]
    CF -->|createContext(sessionMode)| CTX["JMSContext<br/>connection + session"]
    CTX -->|createProducer| P["JMSProducer<br/>định dạng send options"]
    CTX -->|createQueue / createTopic| D["Destination"]
    CTX -->|createConsumer / createDurableConsumer| C["JMSConsumer"]
    P -->|send destination| D
    D -->|broker dispatch| C
    C -->|receive hoặc listener| APP["Xử lý nghiệp vụ"]
    APP -->|acknowledge / commit / rollback| CTX
    CTX -->|close| END["Giải phóng resources"]
```

**Quan trọng:** `JMSContext` đại diện đồng thời cho connection/session, nhưng **không có nghĩa một instance được dùng tự do từ nhiều thread**. Session JMS là vùng điều khiển tuần tự; dùng **một context riêng cho từng worker/thread** nếu cần xử lý song song, hoặc nhờ framework quản lý concurrency.

### 2.1. Khi nào tạo `JMSContext`?

Trong Java SE/CLI:

```java
// Chế độ mặc định: AUTO_ACKNOWLEDGE.
try (JMSContext context = factory.createContext()) {
    // send/receive...
}

// Chỉ định rõ chế độ giao dịch JMS cục bộ.
try (JMSContext context =
         factory.createContext(JMSContext.SESSION_TRANSACTED)) {
    // send/receive...
    context.commit();
}
```

`ConnectionFactory` có các overload `createContext()`, `createContext(int)`, `createContext(user, password)` và `createContext(user, password, int)`. Trong ứng dụng quản lý bởi Jakarta EE, một `JMSContext` có thể được container inject/đóng; quy tắc local transaction và gọi `close()` có khác biệt. Ví dụ trong bài này là **application-managed JMSContext trong Java SE**.

Khi producer chỉ gửi, không cần tạo `JMSConsumer` hay gọi `start()`. Khi tạo consumer, context mặc định auto-start underlying connection để nhận message; nếu cần cấu hình client ID hoặc chuẩn bị nhiều consumer trước lúc chạy, có thể đặt `context.setAutoStart(false)` **trước khi tạo consumer**, rồi `context.start()` khi sẵn sàng.

## 3. Chọn Maven dependency và namespace đúng với provider

**JMS 2.0** là thế hệ API giới thiệu simplified API. **Jakarta Messaging 3.x** tiếp tục ý tưởng ấy và đổi package từ `javax.jms` sang `jakarta.jms`. Đổi package không phải đổi wire protocol một cách tự động.

| Provider/client | Dependency tiêu biểu | Namespace của source | Điều cần nhớ |
|---|---|---|---|
| **Artemis 2.57.0, JMS 2.0** | `org.apache.artemis:artemis-jms-client:2.57.0` | `javax.jms` | Dành cho ứng dụng còn dùng javax JMS |
| **Artemis 2.57.0, Jakarta Messaging 3.x** | `org.apache.artemis:artemis-jakarta-client:2.57.0` | `jakarta.jms` | **Dùng cho lab chính** |
| **ActiveMQ Classic 5.18+**, client Classic | `org.apache.activemq:activemq-client:5.19.x` | `javax.jms` | Simplified API **có**, một số tính năng JMS 2.0 vẫn chưa hỗ trợ |
| **ActiveMQ Classic 6.4.x**, client Classic | `org.apache.activemq:activemq-client:6.4.0` | `jakarta.jms` | Jakarta Messaging 3.1 **một phần**, cần test feature |
| Classic 5.18.x giai đoạn chuyển tiếp | `activemq-client-jakarta` ở bản tương ứng | `jakarta.jms` | Dùng cho trường hợp migration đặc thù, có giới hạn embedded/VM |

**Không trộn** `javax.jms.JMSContext` với `jakarta.jms.ConnectionFactory` hoặc ngược lại: dù tên interface giống nhau, chúng là **hai kiểu Java khác nhau**. Với Artemis, `ActiveMQConnectionFactory` của client native có thể trông giống class Classic nhưng ở package khác:

```java
// Artemis native:
org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory

// Classic native OpenWire:
org.apache.activemq.ActiveMQConnectionFactory
```

Tài liệu Artemis 2.57.0 ghi rõ cả hai tọa độ client Maven `artemis-jms-client` và `artemis-jakarta-client`. Trang hỗ trợ JMS 2.0 của Classic cho biết `JMSContext`/`JMSProducer`/`JMSConsumer` có từ dòng 5.18, nhưng **partial support** không phải lời hứa “mọi phương thức đã đủ”. Tham khảo tài liệu chính thức ở cuối bài.

### 3.1. Maven project tối thiểu cho lab Artemis/Jakarta

Dùng Java 17, Maven 3.9+, một broker **Artemis 2.57.0** sẵn sàng kết nối `tcp://127.0.0.1:61616`. Tài khoản broker được cấp qua các biến môi trường `BROKER_USER`/`BROKER_PASSWORD`. Cần cho phép producer gửi và consumer nhận ở queue `lab.jms2.orders`; queue anycast có thể được pre-create hoặc auto-create tùy broker configuration.

Đặt trong project Maven thử nghiệm:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo.messaging</groupId>
  <artifactId>jms-simplified-api-lab</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.apache.artemis</groupId>
      <artifactId>artemis-jakarta-client</artifactId>
      <version>2.57.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Đây là một dependency runtime client, **không** phải broker nhúng. Muốn test trên Classic và giữ cùng simplified API, hãy tạo **project/JAR riêng** với dependency Classic và sửa namespace/connection factory đúng như bảng trên; không nhét cả hai client JAR và các API cùng tên vào một classpath mà chưa có chiến lược rõ ràng.

## 4. Java lab: producer, browser, consumer và session mode

Thực hành dùng **một chương trình có nhiều chế độ CLI**. Các lần gửi dùng `orderId` riêng để truy dấu, còn `QueueBrowser` dùng để kiểm tra message **không tiêu thụ/ack**.

Tạo `src/main/java/demo/JmsApiLab.java`:

```java
package demo;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.ConnectionMetaData;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.QueueBrowser;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Enumeration;

public final class JmsApiLab {
    private static final String QUEUE_NAME = "lab.jms2.orders";

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            usage();
            return;
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = requiredEnv("BROKER_USER");
        String password = requiredEnv("BROKER_PASSWORD");

        ConnectionFactory factory =
                new ActiveMQConnectionFactory(url, user, password);

        switch (args[0]) {
            case "meta" -> metadata(factory);
            case "send" -> {
                if (args.length != 2) {
                    usage();
                    return;
                }
                send(factory, args[1]);
            }
            case "browse" -> browse(factory);
            case "client-ack" -> receive(factory, "client-ack");
            case "tx-commit" -> receive(factory, "tx-commit");
            case "tx-rollback" -> receive(factory, "tx-rollback");
            case "auto" -> autoReceive(factory);
            case "body" -> bodyReceive(factory);
            default -> usage();
        }
    }

    private static String requiredEnv(String name) {
        String result = System.getenv(name);
        if (result == null || result.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing environment variable: " + name);
        }
        return result;
    }

    private static Queue queue(JMSContext context) {
        return context.createQueue(QUEUE_NAME);
    }

    private static void metadata(ConnectionFactory factory)
            throws Exception {
        try (JMSContext context = factory.createContext()) {
            ConnectionMetaData metadata = context.getMetaData();
            System.out.println("provider="
                    + metadata.getJMSProviderName());
            System.out.println("providerVersion="
                    + metadata.getProviderVersion());
            System.out.println("jmsVersion="
                    + metadata.getJMSVersion());
            System.out.println("sessionMode="
                    + context.getSessionMode());
        }
    }

    private static void send(ConnectionFactory factory, String orderId)
            throws Exception {
        // Một JMS transaction chỉ quản lý thao tác trong JMS session.
        try (JMSContext context =
                     factory.createContext(JMSContext.SESSION_TRANSACTED)) {
            Queue destination = queue(context);
            TextMessage message = context.createTextMessage(
                    "{\"type\":\"CreateInvoice\","
                    + "\"orderId\":\"" + orderId + "\"}");
            message.setStringProperty("idempotencyKey", orderId);

            JMSProducer producer = context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setTimeToLive(0L)
                    .setPriority(4)
                    .setProperty("kind", "invoice")
                    .setJMSCorrelationID("invoice-" + orderId);

            // Nếu lỗi trước commit, đóng context sẽ rollback.
            producer.send(destination, message);
            context.commit();

            System.out.println("SENT orderId=" + orderId);
            System.out.println("JMSMessageID="
                    + message.getJMSMessageID());
        }
    }

    private static void browse(ConnectionFactory factory)
            throws Exception {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            QueueBrowser browser = context.createBrowser(queue(context));
            try {
                Enumeration<?> enumeration = browser.getEnumeration();
                int count = 0;
                while (enumeration.hasMoreElements()) {
                    Message message = (Message) enumeration.nextElement();
                    System.out.println(
                            "QUEUED idempotencyKey="
                            + message.getStringProperty("idempotencyKey")
                            + ", messageId=" + message.getJMSMessageID());
                    count++;
                }
                System.out.println("BROWSED=" + count);
            } finally {
                browser.close();
            }
        }
    }

    private static void receive(ConnectionFactory factory, String mode)
            throws Exception {
        int sessionMode = mode.equals("client-ack")
                ? JMSContext.CLIENT_ACKNOWLEDGE
                : JMSContext.SESSION_TRANSACTED;

        try (JMSContext context = factory.createContext(sessionMode)) {
            Queue destination = queue(context);
            try (JMSConsumer consumer = context.createConsumer(
                    destination, "kind = 'invoice'")) {

                Message message = consumer.receive(5000L);
                if (message == null) {
                    System.out.println("NO_MESSAGE");
                    if (sessionMode == JMSContext.SESSION_TRANSACTED) {
                        context.rollback();
                    }
                    return;
                }

                System.out.println("RECEIVED idempotencyKey="
                        + message.getStringProperty("idempotencyKey")
                        + ", redelivered=" + message.getJMSRedelivered()
                        + ", correlationId="
                        + message.getJMSCorrelationID());

                if (mode.equals("tx-rollback")) {
                    context.rollback();
                    System.out.println("ROLLED_BACK");
                    return;
                }

                try {
                    // Demo: chỉ in log. Production phải ghi DB
                    // và áp dụng idempotency trước khi ack/commit.
                    System.out.println("PROCESSED");
                    if (mode.equals("client-ack")) {
                        context.acknowledge(); // Ack tất cả đã tiêu thụ
                        System.out.println("ACKNOWLEDGED");
                    } else {
                        context.commit();
                        System.out.println("COMMITTED");
                    }
                } catch (RuntimeException failure) {
                    if (mode.equals("client-ack")) {
                        context.recover();
                    } else {
                        context.rollback();
                    }
                    throw failure;
                }
            }
        }
    }

    private static void autoReceive(ConnectionFactory factory)
            throws Exception {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE);
             JMSConsumer consumer =
                     context.createConsumer(queue(context))) {
            Message message = consumer.receive(5000L);
            System.out.println(message == null
                    ? "NO_MESSAGE"
                    : "AUTO_ACK_RECEIVED " + message.getJMSMessageID());
            // Trong AUTO_ACKNOWLEDGE, receive() trả thành công
            // đồng nghĩa provider đã ack ở mức session.
        }
    }

    private static void bodyReceive(ConnectionFactory factory) {
        try (JMSContext context = factory.createContext();
             JMSConsumer consumer =
                     context.createConsumer(queue(context))) {
            String body = consumer.receiveBody(String.class, 5000L);
            System.out.println(body == null ? "NO_MESSAGE" : body);
            // receiveBody không cung cấp headers/properties.
        }
    }

    private static void usage() {
        System.out.println("meta | send <orderId> | browse");
        System.out.println("client-ack | tx-commit | tx-rollback");
        System.out.println("auto | body");
    }
}
```

**Những quyết định có chủ đích trong code:**

- `JMSProducer` được tạo từ context rồi fluent chain setter; không `close()` vì producer đơn giản hóa là lightweight object do context quản lý.
- `producer.send(destination, message)` gửi tới destination truyền vào mỗi lần gọi, trong khi `MessageProducer` cũ thường gắn destination khi khởi tạo.
- `context.commit()` sau send là mốc kết thúc **JMS local transaction**; chưa phải kết quả nghiệp vụ “đã xuất hóa đơn”.
- `browse` quan sát mà không ack; dùng trước/sau mỗi bước để hiểu chuyện gì xảy ra.
- `receive` dùng selector JMS `kind = 'invoice'`; nếu queue có message khác không khớp, chúng **không được consumer này lấy** và có thể tiếp tục chờ trên queue.
- `client-ack` và `tx-commit` chỉ đọc một message rồi ack/commit; dễ quan sát hơn khi kiểm thử.
- `tx-rollback` nhận một message rồi rollback để nó được phân phối lại theo chính sách provider/broker.
- `auto` và `body` cố ý tách thành ví dụ đối chiếu; **không dùng** hai chế độ đó cho handler có tác dụng phụ chưa chống lặp.
- JSON được tạo bằng nối chuỗi cho lab dùng `orderId` giản lược; production phải dùng serializer chuẩn và validate payload, không ghép JSON từ input không tin cậy.

### 4.1. Chạy từng bước

Đặt các biến môi trường trong shell lab. Với Bash:

```bash
export BROKER_URL='tcp://127.0.0.1:61616'
export BROKER_USER='labuser'
export BROKER_PASSWORD='lab-only-password'
```

Với PowerShell:

```powershell
$env:BROKER_URL = 'tcp://127.0.0.1:61616'
$env:BROKER_USER = 'labuser'
$env:BROKER_PASSWORD = 'lab-only-password'
```

Dùng tài khoản/thông tin kết nối thực tế của broker lab. Cấp quyền gửi/nhận queue tương ứng; nếu address/queue auto-create bị vô hiệu, hãy cấu hình sẵn **anycast address + queue** cho `lab.jms2.orders`.

```bash
mvn -q compile exec:java '-Dexec.mainClass=demo.JmsApiLab' '-Dexec.args=meta'

mvn -q compile exec:java '-Dexec.mainClass=demo.JmsApiLab' '-Dexec.args=send ord-101'

mvn -q compile exec:java '-Dexec.mainClass=demo.JmsApiLab' '-Dexec.args=browse'

mvn -q compile exec:java '-Dexec.mainClass=demo.JmsApiLab' '-Dexec.args=tx-rollback'

mvn -q compile exec:java '-Dexec.mainClass=demo.JmsApiLab' '-Dexec.args=browse'

mvn -q compile exec:java '-Dexec.mainClass=demo.JmsApiLab' '-Dexec.args=client-ack'

mvn -q compile exec:java '-Dexec.mainClass=demo.JmsApiLab' '-Dexec.args=browse'
```

Khi broker mới, queue ban đầu rỗng, không có worker khác và không có delay dài:

| Mốc | Kỳ vọng |
|---|---|
| `meta` | Có tên provider, phiên bản JMS do provider báo, session mode |
| `send ord-101` | `SENT` và `JMSMessageID` |
| `browse` | Thấy `idempotencyKey=ord-101` |
| `tx-rollback` | Nhận, in `ROLLED_BACK`; message có thể trở lại trạng thái available sau delay |
| `browse` sau rollback | Message chưa bị commit xóa; có thể đang scheduled/redelivery tùy broker |
| `client-ack` | Nhận, in `ACKNOWLEDGED` nếu message sẵn sàng |
| `browse` cuối | Không thấy `ord-101` sau ack thành công |

Nếu `client-ack` trả `NO_MESSAGE` ngay sau rollback, **đừng tự kết luận message bị mất**: có thể đang trong khoảng redelivery delay, bị chuyển DLQ theo chính sách thử lại hoặc bị một consumer khác nhận. Kiểm tra queue depth/delivering/scheduled, DLQ và log broker rồi thử khi message sẵn sàng.

### 4.2. Thí nghiệm chỉ ra vì sao AUTO_ACKNOWLEDGE dễ sai

```bash
mvn -q compile exec:java '-Dexec.mainClass=demo.JmsApiLab' '-Dexec.args=send ord-auto-1'
mvn -q compile exec:java '-Dexec.mainClass=demo.JmsApiLab' '-Dexec.args=auto'
```

Nếu `receive()` trả thành công ở chế độ `AUTO_ACKNOWLEDGE` thì ack đã xảy ra khi lời gọi trả về. Giả sử ứng dụng nhận xong rồi gọi REST API xuất hóa đơn; nếu API lỗi/crash **sau** `receive()`, broker có thể không còn message để redeliver. **`AUTO_ACKNOWLEDGE` không phù hợp cho luồng cần hoàn tất side effect bên ngoài trước khi ack**, trừ khi đã có cơ chế khôi phục độc lập.

Giải pháp thường dùng: `CLIENT_ACKNOWLEDGE` cho handler có một quá trình xử lý rõ ràng; hoặc `SESSION_TRANSACTED` nếu cần commit/rollback gửi/nhận JMS. Khi ghi SQL, cần thêm idempotency/inbox/outbox vì JMS local transaction và SQL không tự động là một transaction nguyên tử.

## 5. JMSProducer: các lựa chọn có tác dụng gì?

`JMSProducer` là builder-like API; mỗi setter thường trả lại chính producer để gọi chuỗi:

```java
JMSProducer producer = context.createProducer()
    .setDeliveryMode(DeliveryMode.PERSISTENT)
    .setPriority(6)
    .setTimeToLive(60_000L)
    .setProperty("eventType", "InvoiceRequested")
    .setProperty("schemaVersion", 1)
    .setJMSCorrelationID("flow-101");

producer.send(queue, "payload");
```

| API | Ý nghĩa | Điều cần cẩn thận |
|---|---|---|
| `send(queue, "text")` | Provider tạo `TextMessage` từ `String` | Cần encoding/contract, tránh ghép JSON thủ công |
| `send(queue, message)` | Gửi `Message` đã tạo, giữ header/properties khi phù hợp | Không chia sẻ cùng message object cho nhiều thread khi send async |
| `setDeliveryMode(PERSISTENT)` | Yêu cầu lưu bền vững khi broker nhận | Không ngăn gửi trùng hoặc tác dụng phụ bị lặp |
| `setTimeToLive(ms)` | Message có thể expire sau TTL; `0` thường là không expire do producer | TTL khác delivery delay; expiry policy do broker điều khiển |
| `setDeliveryDelay(ms)` | Chỉ được deliver sớm nhất sau delay | **Phải kiểm tra hỗ trợ provider**, Classic có bản chưa hỗ trợ |
| `setPriority(0..9)` | Mức ưu tiên JMS | Broker có thể áp dụng dispatch policy riêng; không bảo đảm thứ tự toàn cục |
| `setProperty(name, value)` | Message property để selector/route/tracing | Dùng kiểu hợp lệ, trùng tên property trong message có thể bị override |
| `setJMSCorrelationID(id)` | Header liên kết request/reply/tracing | Không phải khóa idempotency nghiệp vụ |
| `setJMSReplyTo(destination)` | Chỉ định destination trả lời | Cần ACL và xử lý timeout/late replies |
| `setAsync(listener)` | Asynchronous send với callback | **Không mặc định mọi provider thực hiện**; callback chỉ cho kết quả gửi của JMS provider |

**Một JMSProducer có thể tái sử dụng và giữ các setting giữa các lần gửi**. Nếu một lần gửi đặt `eventType=A` và lần sau quên thay, message B có thể mang property sai. Tạo producer ngắn sống cho từng loại gửi hoặc cấu hình rõ mỗi lần để tránh rò state.

### 5.1. Delivery delay và TTL không giống nhau

Giả sử gửi lúc 10:00:00:

- `setDeliveryDelay(5000)`: message **không được giao trước** 10:00:05.
- `setTimeToLive(3000)`: message có thể **hết hạn** khoảng 10:00:03.
- Nếu dùng cả hai như trên, message có thể expire **trước khi đủ điều kiện deliver**.

Vì thế cấu hình delay lớn hơn TTL chỉ hợp lý khi bạn thực sự muốn message không bao giờ tới consumer (hiếm khi là ý định). Với provider chưa hỗ trợ `setDeliveryDelay`, không được giả định delay có tác dụng chỉ vì code compile.

### 5.2. Gửi bất đồng bộ không đồng nghĩa “business đã xử lý”

JMS 2.0 quy định `setAsync(CompletionListener)` để provider báo kết quả của thao tác **gửi**:

```java
import jakarta.jms.CompletionListener;
import jakarta.jms.Message;

// Fragment minh họa trong chương trình Jakarta JMS.
context.createProducer()
    .setAsync(new CompletionListener() {
        @Override
        public void onCompletion(Message message) {
            System.out.println("JMS send completed");
        }

        @Override
        public void onException(Message message, Exception error) {
            System.err.println("JMS send failed: " + error);
        }
    })
    .send(queue, "sample");
```

Callback này **không có nghĩa consumer đã xử lý xong**. Đồng thời, callback không được dùng lại cùng `JMSContext` để làm việc gây xung đột thread/commit/close. Một số provider có thể không hỗ trợ `setAsync` dù có interface `JMSProducer`: phải thực thi một phép thử tính năng riêng trên destination an toàn.

## 6. JMSConsumer: receive(), receiveBody() và MessageListener

### 6.1. `receive(timeout)`: dùng khi cần metadata và kiểm soát ack

```java
try (JMSConsumer consumer =
         context.createConsumer(queue, "kind = 'invoice'")) {
    Message message = consumer.receive(5000);
    if (message != null) {
        String id = message.getStringProperty("idempotencyKey");
        String correlation = message.getJMSCorrelationID();
        boolean redelivered = message.getJMSRedelivered();
        System.out.println(id + " " + correlation + " " + redelivered);
    }
}
```

`receive(5000)` trả về `null` khi không nhận được message trong timeout, **không phải provider unsupported** và cũng không có nghĩa queue không tồn tại. Nếu dùng nhận vô hạn `receive()`, thread có thể block lâu; cần cơ chế shutdown hợp lý.

### 6.2. `receiveBody(String.class, timeout)`: gọn nhưng mất header

```java
try (JMSConsumer consumer = context.createConsumer(queue)) {
    String body = consumer.receiveBody(String.class, 5000);
    if (body == null) {
        System.out.println("No message in timeout");
    } else {
        System.out.println(body);
    }
}
```

Chỉ dùng khi không cần `JMSMessageID`, `JMSRedelivered`, `JMSCorrelationID`, properties, delivery count và không cần điều tra lỗi nghiệp vụ theo message header. Một body không tương thích `String.class` có thể phát sinh `MessageFormatRuntimeException`. Ở chế độ `AUTO_ACKNOWLEDGE`, provider có quy tắc ack riêng khi lời gọi `receiveBody` thành công/không thể convert; không viết logic “nhận sai type thì trả về queue” dựa trên giả định ngầm. Với Classic phiên bản có `receiveBody` chưa hỗ trợ, có thể gặp `UnsupportedOperationException` dù source compile.

### 6.3. `setMessageListener`: xử lý push, không đồng thời tự gọi receive

```java
JMSConsumer consumer = context.createConsumer(queue);
consumer.setMessageListener(message -> {
    try {
        System.out.println(message.getJMSMessageID());
        // Xử lý gọn, không dùng chung context ở thread khác.
    } catch (Exception error) {
        throw new RuntimeException(error);
    }
});
```

Sau khi đăng ký listener, ứng dụng phải **giữ context/consumer còn sống**. Không tạo context trong một try-with-resources rồi thoát ngay và kỳ vọng listener chạy nền mãi. Không gọi `receive()` đồng thời trên consumer đã đặt listener. Tránh `close()` hoặc `commit()` trên **chính context của listener** từ một callback khi vi phạm quy tắc concurrency/lifecycle của provider; đặc biệt khi dùng async sends.

**Ngoại lệ trong callback không thay cho chiến lược rollback.** Trong transacted context, việc rollback/commit cần được thiết kế tường minh qua tầng quản lý luồng thích hợp. Framework message listener container thường giúp tạo và ràng buộc context/session per worker cùng transaction/ack strategy.

### 6.4. Shared/durable consumers cần kiểm thử riêng

`JMSContext` có các overload như `createDurableConsumer(topic, name)`, `createSharedConsumer(topic, name)`, `createSharedDurableConsumer(topic, name)`. Đây là tính năng **đặc thù topic subscription lifecycle**:

- Durable subscription phải được tạo **trước thời điểm muốn lưu message offline**.
- Shared consumer cho nhiều consumer chia nhau một subscription; việc triển khai tùy provider.
- Client ID, tên subscription, selector, quyền tạo queue/subscription và chính sách lưu message phải được kiểm tra.
- ActiveMQ Classic tài liệu JMS 2.0 cho biết **shared topic consumers** là tính năng chưa hỗ trợ hoàn chỉnh trong các bản đã phát hành tương ứng; không gộp nó vào “đã hỗ trợ `JMSConsumer`”.

Với Artemis, thực hiện test riêng cho durable/shared subscription với topic multicast và subscription identity ổn định. Đừng dùng queue test để suy ra shared topic support.

## 7. Acknowledgment và transaction: API đơn giản vẫn có ranh giới cũ

| Session mode (Java SE) | Khi nào message được coi đã ack? | Khuyến nghị |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | Với `receive()` đồng bộ: khi lời gọi trả thành công; với listener: sau khi listener trả thành công | Nhận và đọc đơn giản, không có side effect cần đảm bảo |
| `CLIENT_ACKNOWLEDGE` | `context.acknowledge()`; ack **mọi message đã nhận trong session** | Xử lý xong rồi xác nhận, hiểu rõ phạm vi session |
| `DUPS_OK_ACKNOWLEDGE` | Lazy acknowledgment | Chỉ khi chịu được redelivery/trùng lặp |
| `SESSION_TRANSACTED` | `context.commit()`; `rollback()` để redeliver theo policy | Tác vụ JMS cần commit/rollback rõ |

Một ví dụ dễ mắc lỗi:

```java
Message first = consumer.receive(1000);
Message second = consumer.receive(1000);
// Trong CLIENT_ACKNOWLEDGE:
context.acknowledge();
```

Lệnh cuối **không chỉ ack `second`** mà ack tất cả message đã được tiêu thụ trong session, bao gồm `first`. Nếu `first` chưa hoàn tất nghiệp vụ, thiết kế sai. Cách đơn giản nhất là **một lần nhận → xử lý → ack** trên session độc lập, hoặc quản lý batch như một đơn vị xử lý có chủ đích.

### 7.1. Context transaction không gộp tự động với SQL transaction

Giả sử consumer nhận `CreateInvoice`, ghi `invoice` vào PostgreSQL rồi gọi `context.commit()`. Nếu DB commit thành công nhưng process crash trước JMS commit, broker có thể giao lại message. Với cùng `orderId`, nếu DB không có unique constraint/idempotency, có thể tạo hóa đơn thứ hai.

Mẫu đúng về nguyên tắc:

```text
Receive CreateInvoice(orderId=ord-101)
  ├─ DB transaction: INSERT/UPSERT invoice, UNIQUE(orderId)
  ├─ Mark inbox processed by business key in same DB transaction
  ├─ Commit DB
  └─ JMS context.commit() (hoặc acknowledge)
       ▲ nếu crash trước đây → JMS redelivery
         DB uniqueness/inbox ngăn tác dụng phụ trùng
```

Nếu cần phát `InvoiceCreated` sang một broker khác sau DB commit, cân nhắc transactional outbox. `JMSContext` đơn giản hóa API, **không** cung cấp exactly-once giữa database và broker.

### 7.2. `close()` và lỗi đang xử lý

`JMSContext` là `AutoCloseable`; dùng try-with-resources đảm bảo close khi rời scope. Với context transacted **chưa commit**, đóng connection/session làm rollback. Với `CLIENT_ACKNOWLEDGE`, đóng context **không tự ack** message còn chưa xác nhận. Tuy nhiên nếu message đã ack trước khi exception xảy ra, close không “hoàn tác” acknowledgment đó.

Khi dùng pooled `ConnectionFactory`, hãy kiểm tra provider/pool có hỗ trợ `createContext()` và close trả session vào pool theo semantics cần thiết hay không. Không suy rằng một pool cũ hỗ trợ JMS 1.1 cũng hỗ trợ simplified API; ActiveMQ Classic triển khai JMSContext trên `activemq-jms-pool` theo lộ trình/version riêng.

## 8. Cách kiểm tra provider hỗ trợ tính năng: ba lớp bằng chứng

Một phép kiểm tra đúng phải phân biệt:

1. **Compile-time:** Trong dependency có interface và method không? `javac` có compile được không? Chỉ chứng minh **API tồn tại**.
2. **Runtime provider:** `ConnectionFactory.createContext()` có chạy? `receiveBody`, `setAsync`, `setDeliveryDelay` có thật sự được hiện thực hay ném `UnsupportedOperationException`?
3. **End-to-end behavior:** Một message thật có đến đúng lúc/đúng nơi? Có callback đúng? Có timeout và retry đúng? Đây mới là bằng chứng vận hành.

Có thể đặt phép thử trong CI/staging để bắt regression khi nâng version client hoặc broker.

### 8.1. Bắt đầu bằng metadata, nhưng metadata chưa đủ

```java
try (JMSContext context = factory.createContext()) {
    ConnectionMetaData md = context.getMetaData();
    System.out.println(md.getJMSProviderName());
    System.out.println(md.getProviderVersion());
    System.out.println(md.getJMSVersion());
}
```

Các giá trị metadata có thể mô tả **provider connection/runtime** và JMS specification version, nhưng **không có bitmask chuẩn** nói “async send supported”, “delivery delay supported” cho mọi phương thức. Phải kết hợp với matrix tài liệu nhà cung cấp và một **behavior probe**.

### 8.2. Thử `receiveBody` và `setDeliveryDelay` trên temporary queue

Ví dụ dùng lại `jakarta.jms` và factory của Artemis từ lab trên, nhưng phép thử mô tả cách đánh giá **provider thực tế**, kể cả khi chuyển sang một implementation khác cùng Jakarta API. Đặt vào `src/main/java/demo/ProviderFeatureProbe.java` trong **project lab**, không trong tài liệu repo:

```java
package demo;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.ConnectionMetaData;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.JMSRuntimeException;
import jakarta.jms.TemporaryQueue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ProviderFeatureProbe {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = required("BROKER_USER");
        String password = required("BROKER_PASSWORD");

        ConnectionFactory factory =
                new ActiveMQConnectionFactory(url, user, password);

        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            ConnectionMetaData metadata = context.getMetaData();
            System.out.printf("provider=%s, version=%s, JMS=%s%n",
                    metadata.getJMSProviderName(),
                    metadata.getProviderVersion(),
                    metadata.getJMSVersion());

            // Cô lập tác động; queue tạm gắn với connection.
            TemporaryQueue probeQueue = context.createTemporaryQueue();

            System.out.println("PROBE receiveBody");
            context.createProducer().send(probeQueue, "probe-text");

            try (JMSConsumer consumer =
                         context.createConsumer(probeQueue)) {
                try {
                    String value =
                            consumer.receiveBody(String.class, 3000L);
                    System.out.println(value == null
                            ? "NO_REPLY_OR_TIMEOUT"
                            : "SUPPORTED result=" + value);
                } catch (UnsupportedOperationException unsupported) {
                    System.out.println(
                            "UNSUPPORTED receiveBody: "
                            + unsupported.getClass().getSimpleName());
                }
            }

            System.out.println("PROBE delivery delay API");
            JMSProducer delayed = context.createProducer();
            try {
                delayed.setDeliveryDelay(1200L);
                long actual = delayed.getDeliveryDelay();
                System.out.println("requested=1200, reported=" + actual);
                if (actual != 1200L) {
                    System.out.println(
                            "INCONCLUSIVE: setter/getter mismatch");
                }
            } catch (UnsupportedOperationException unsupported) {
                System.out.println(
                        "UNSUPPORTED delivery delay API: "
                        + unsupported.getClass().getSimpleName());
            }
        } catch (JMSRuntimeException failure) {
            System.err.println("RUNTIME/INFRASTRUCTURE ERROR: "
                    + failure.getClass().getSimpleName()
                    + ", errorCode=" + failure.getErrorCode()
                    + ", message=" + failure.getMessage());
            throw failure;
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return value;
    }
}
```

**Cách đọc kết quả quan trọng:**

- `UnsupportedOperationException`: provider **tuyên bố chưa hiện thực** phương thức/tính năng tại runtime.
- `JMSRuntimeException`: có thể là lỗi auth, connection, destination, quyền tạo temporary queue, resource limit, server error... **không được gộp vào “provider không hỗ trợ”**.
- `receiveBody` trả `null`: chờ hết timeout/không nhận message phù hợp; có thể do routing, connection, producer/consumer lifecycle. **Không tương đương unsupported**.
- `setDeliveryDelay`/`getDeliveryDelay` đều không lỗi chỉ chứng minh **API setter/getter**; muốn chứng minh delay thực sự hoạt động, hãy **gửi message bằng producer đã set delay**, nhận với timeout ngắn hơn delay, rồi nhận lại sau thời gian phù hợp; đo timestamp và kiểm tra latency, cho phép sai số lịch trình.
- Temporary queue phải được broker cho phép tạo; nếu thiếu ACL, phép thử có thể thất bại trước khi tới feature cần đánh giá.
- Chạy probe trên **môi trường cô lập**, không gửi test message vào queue nghiệp vụ. Nếu provider ném exception sau khi bắt đầu receive, tình trạng message đã consume/ack có thể khác giữa implementation; không dùng probe để xử lý dữ liệu quan trọng.

**Không cần probe bằng reflection** chỉ để biết method tồn tại: Java compiler và dependency đã làm được việc đó. Điều cần kiểm tra là **method có chạy và semantics có đúng không**.

### 8.3. Kiểm tra asynchronous send có callback

Phép thử riêng này dùng một queue tạm hoặc queue lab. Nên thử trong unit/integration harness **có timeout**, không phụ thuộc vào `Thread.sleep()` để “đoán callback xong”.

```java
import jakarta.jms.CompletionListener;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.TemporaryQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

// Fragment giả định context đang mở, không chia sẻ qua thread khác.
TemporaryQueue destination = context.createTemporaryQueue();
CountDownLatch done = new CountDownLatch(1);
AtomicReference<Exception> failure = new AtomicReference<>();

try {
    JMSProducer producer = context.createProducer()
        .setAsync(new CompletionListener() {
            @Override
            public void onCompletion(Message message) {
                done.countDown();
            }

            @Override
            public void onException(Message message, Exception error) {
                failure.set(error);
                done.countDown();
            }
        });

    producer.send(destination, "async-probe");
    boolean finished = done.await(5, TimeUnit.SECONDS);

    if (!finished) {
        System.out.println("INCONCLUSIVE: callback timed out");
    } else if (failure.get() != null) {
        System.out.println("ASYNC SEND FAILED: " + failure.get());
    } else {
        System.out.println("ASYNC SEND CALLBACK PASSED");
    }
} catch (UnsupportedOperationException unsupported) {
    System.out.println("UNSUPPORTED async send");
}
```

Đây là **fragment trong một method `throws InterruptedException`**, không phải file Java đầy đủ. Không gọi `context.commit()` hoặc `context.close()` **bên trong** callback; việc dùng context ở callback khi application thread cũng dùng nó có thể vi phạm ràng buộc JMS. Callback success phản ánh **kết quả gửi phía provider**, không chứng minh business consumer đã xử lý message.

### 8.4. Ma trận kiểm thử nên ghi trong dự án

| Tính năng | Phép thử tối thiểu | PASS thực sự cần có |
|---|---|---|
| `createContext` | Tạo và đóng context, metadata | Không exception, tài nguyên giải phóng |
| `JMSProducer.send` | Gửi text, browse/receive | Đúng message body/property, được deliver |
| `JMSConsumer.receive` | Gửi rồi receive(timeout) | Đúng message, không hiểu nhầm `null` |
| `receiveBody` | Gửi `TextMessage`, nhận `String.class` | Body đúng, không unsupported |
| `CLIENT_ACKNOWLEDGE` | Nhận, ack, browse | Message biến mất sau ack và không redeliver vô cớ |
| `SESSION_TRANSACTED` | Send/receive commit, rollback | Commit giữ/giao; rollback cho nhận lại theo policy |
| `setDeliveryDelay` | Gửi có delay, kiểm tra trước/sau | Không deliver trước thời hạn; không chỉ setter PASS |
| `setAsync` | Callback onCompletion/onException + timeout | Callback nhận đúng kết quả và một lần cho mỗi send |
| Shared topic consumer | Hai consumer chung tên subscription, publish | Phân phối đúng vào một subscription, không throw unsupported |
| Durable subscription | Subscriber offline sau khi tạo, publish, reconnect | Nhận backlog theo contract |
| Selector | Publish nhiều property, nhận có filter | Chỉ nhận message khớp selector |
| Failover/reconnect | Cắt kết nối theo lab topology | Khôi phục đúng trạng thái, không làm trùng business side effect |

### 8.5. Provider support matrix: đừng nhầm “có API” với “đầy đủ”

Theo tài liệu hỗ trợ JMS 2.0/3.1 hiện được Apache ActiveMQ Classic công bố:

| Feature | Classic 5.18+/5.19.x (`javax.jms`) | Classic 6.4.0 (`jakarta.jms`) | Artemis 2.57.0 |
|---|---|---|---|
| `JMSContext`, `JMSProducer`, `JMSConsumer` cơ bản | Có hỗ trợ simplified API từ 5.18 | Có | Có qua client JMS/Jakarta tương ứng |
| `CLIENT_ACKNOWLEDGE` với simplified API | Có từ 5.18 | Có | Có theo JMS/Jakarta semantics |
| `JMSConsumer.receiveBody(Class<T>)` | **Chưa đủ** theo lịch sử tính năng Classic | Có từ 6.4.0 | Theo client/spec; vẫn kiểm thử |
| `JMSProducer.setAsync(CompletionListener)` | Chưa hỗ trợ trong dòng 5.19 | Được Apache liệt kê đang hướng tới bản 6.5.0 | Theo client/spec; vẫn kiểm thử |
| `JMSProducer.setDeliveryDelay` | Chưa hỗ trợ trong dòng 5.19 | Được Apache liệt kê hướng tới 7.0.0 | Theo client/spec; vẫn kiểm thử |
| Shared topic consumers | Chưa hỗ trợ đầy đủ | Được Apache liệt kê hướng tới 7.0.0 | Theo client/spec; vẫn kiểm thử |
| Pool hỗ trợ `JMSContext` | Cần xét artifact/version riêng | `activemq-jms-pool` bổ sung hỗ trợ ở 6.4.0 | Phụ thuộc pool/framework được sử dụng |

**Đây là snapshot dựa trên tài liệu hỗ trợ có công bố target và completed version**. Trạng thái ở các bản ra sau 6.4.0 cần kiểm tra lại khi triển khai. Các dòng “theo spec” của Artemis không thay thế việc chạy capability tests với broker/client security config và transport cụ thể.

**Mẹo chọn phương án:** Nếu dịch vụ Classic 5.19.x chỉ cần queue producer/consumer, message properties, `CLIENT_ACKNOWLEDGE` hoặc local JMS transaction, simplified API có thể phù hợp. Nếu business cần **delayed delivery, async send hoặc shared topic consumer**, đừng chỉ nhìn `JMSProducer`/`JMSConsumer`; hoặc dùng Artemis đã kiểm thử, hoặc thiết kế phương án khác có hành vi được chứng minh trên provider/phiên bản đang vận hành.

## 9. Những lỗi triển khai điển hình và cách khắc phục

| Dấu hiệu | Nguyên nhân có thể | Hành động đúng |
|---|---|---|
| `Cannot find symbol JMSContext` | JMS API quá cũ hoặc namespace/dependency sai | Chọn JMS 2.0 `javax.jms` hoặc Jakarta `jakarta.jms` đúng |
| `ClassCastException` giữa `javax.jms` và `jakarta.jms` | Trộn hai API khác package | Tách module/đổi toàn bộ client đúng namespace |
| `UnsupportedOperationException` tại `receiveBody` | Provider Classic phiên bản partial | Kiểm tra version; dùng `receive()` + `Message.getBody` khi hỗ trợ hoặc đọc `TextMessage.getText()` |
| `UnsupportedOperationException` tại `setAsync` | Async producer chưa được provider implement | Thử trên phiên bản hỗ trợ/giữ synchronous send hoặc thiết kế send queue riêng |
| `setDeliveryDelay` không có tác dụng | Provider chưa hỗ trợ hoặc setter/getter không phản ánh real send | Gửi message thử, đo thời điểm delivery và xem broker scheduled policy |
| `receive(5000)` trả `null` | Timeout, selector, queue rỗng, connection chưa start | Kiểm tra routing/selector, `setAutoStart(false)`, broker metrics |
| Receive thành công nhưng DB chưa commit, message đã mất | Dùng `AUTO_ACKNOWLEDGE` cho side effect | Đổi `CLIENT_ACKNOWLEDGE`/`SESSION_TRANSACTED` và idempotency |
| Ack một message làm nhiều message biến mất | `CLIENT_ACKNOWLEDGE` xác nhận toàn session | Xử lý một message/ack hoặc chia session rõ |
| Context dùng trong nhiều thread gặp lỗi khó tái hiện | Session là context tuần tự | Context riêng per thread/worker |
| Đóng context nhưng listener không còn chạy | Try-with-resources kết thúc ngay | Quản lý lifecycle worker và shutdown rõ |
| Provider metadata báo JMS 2.0 nhưng tính năng lỗi | API version không đồng nghĩa capability | Behavior probe theo từng method |
| Transaction JMS commit nhưng SQL transaction rollback | Hai transaction độc lập | Inbox/idempotency/outbox hoặc kiến trúc transaction được quản lý |
| Test chạy khi queue vẫn có message cũ | Không cô lập dữ liệu thử | Dùng isolated queue/temporary destination, test ID và môi trường riêng |
| Producer gửi thành công nhưng chỉ nhận trùng sau failover | In-flight send/ack không rõ kết quả | Business idempotency key, replay/duplicate handling và logs |

## 10. Thực hành có yêu cầu quan sát

**Bài 1 — So sánh số dòng code và lifecycle.** Viết lại producer `Connection/Session/MessageProducer` thành `JMSContext/JMSProducer`, dùng try-with-resources. Giải thích vì sao vẫn phải xem session mode dù code không còn tạo `Session` tường minh.

**Bài 2 — Phát hiện ack quá sớm.** Gửi một message tới queue lab. Dùng `auto` để receive, sau đó cố ý ném exception trong business handler. Quan sát queue. Thay bằng `tx-rollback` và chứng minh message có thể redeliver theo policy. Nêu cách tránh duplicate DB insert.

**Bài 3 — Kiểm tra provider partial support.** Chạy `ProviderFeatureProbe` trên Artemis và một client/provider Classic đã pin version phù hợp (đổi imports/dependencies theo đúng namespace). Ghi metadata, trạng thái `receiveBody`, `setDeliveryDelay` và lỗi nếu có. Giải thích vì sao `getJMSVersion()` **không đủ** làm feature detector.

**Bài 4 — Thử delivery delay end-to-end.** Trong queue tạm, gửi message với delay 2 giây, `receive(500)` ngay sau đó rồi nhận lại với timeout đủ dài. Kết quả đầu phải là `null` nếu provider thật sự áp dụng delay và kết nối/consumer đã sẵn sàng; trường hợp bất thường phải kiểm tra thời gian, TTL và broker policy.

**Bài 5 — Chuyển Classic sang Artemis.** Chọn một lối đi: giữ code `javax.jms` và chuyển sang `artemis-jms-client` hoặc dùng `jakarta.jms` và `artemis-jakarta-client`. Chỉ ra các class import và Maven dependency cần đổi. Viết checklist regression cho queue, ack, transaction, selector, receiveBody và hỗ trợ shared subscription.

**Bài 6 — Quản lý concurrency.** Có 8 worker cùng đọc một queue. Vì sao dùng **một `JMSContext` chia sẻ** cho cả 8 thread là thiết kế đáng ngại? Đề xuất mô hình tạo context/consumer riêng cho từng worker (hoặc listener container có quản lý connection/session).

**Tiêu chí đạt:** Người học chạy được đường `send → browse → tx-rollback → client-ack`, tự thu được metadata và ít nhất một kết quả capability probe, phân biệt lỗi unsupported với timeout/ACL, giải thích được giới hạn JMS transaction và không coi simplified API là bảo đảm exactly-once.

## 11. Quy tắc ghi nhớ khi dùng simplified JMS API

1. **`JMSContext` gộp Connection và Session về API; không xóa ranh giới transaction, acknowledgement và thread-safety.**
2. **`JMSProducer` là đối tượng gửi nhẹ**, hỗ trợ fluent configuration; `JMSConsumer` nhận dữ liệu đồng bộ hoặc qua listener. Đóng consumer/context đúng vòng đời.
3. **Chọn ack mode trước khi viết handler:** `AUTO_ACKNOWLEDGE` có thể ack trước khi business work hoàn tất; `CLIENT_ACKNOWLEDGE` ack theo session; `SESSION_TRANSACTED` commit/rollback theo JMS.
4. **Kiểm tra provider theo ba tầng:** compile API → runtime method → end-to-end observable behavior. `UnsupportedOperationException` khác timeout và khác lỗi kết nối/quyền.
5. **Kiểm tra namespace và artifact:** Artemis có cả `javax.jms`/`jakarta.jms` client, Classic 5.x và 6.x có các mức hỗ trợ API khác nhau.
6. **Idempotency, outbox/inbox, DLQ và quan sát vẫn cần thiết:** simplified API giúp code rõ hơn, không thay đổi bản chất giao nhận có thể trùng hoặc thất bại một phần.

## 12. Tài liệu tham khảo chính thức

- [Apache ActiveMQ Classic — JMS 2.0 và Jakarta Messaging support matrix](https://activemq.apache.org/components/classic/documentation/jms2) — trạng thái từng tính năng và phiên bản.
- [Apache Artemis 2.57.0 — The Client Classpath](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath.html) — Maven tọa độ client `javax.jms` và `jakarta.jms`.
- [Jakarta Messaging 3.1 — JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext) — mode, lifecycle, auto-start, ack/commit/rollback.
- [Jakarta Messaging 3.1 — JMSProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsproducer) — send options, properties, async, delivery delay.
- [Jakarta Messaging 3.1 — JMSConsumer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsconsumer) — receive, receiveBody, listener, selectors.
- [Jakarta Messaging Specification 3.1](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — semantics chi tiết của ack, local transactions, auto-start, receiveBody và callback.
- [Jakarta EE Tutorial — Jakarta Messaging Concepts](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html) — cách sử dụng simplified API trong ứng dụng.
