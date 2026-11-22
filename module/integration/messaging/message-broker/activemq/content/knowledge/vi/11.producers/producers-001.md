# Gửi đến destination cố định và destination xác định lúc chạy

> **Chương:** Producer  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Java/JMS với ActiveMQ Classic và ActiveMQ Artemis.  
> **Trọng tâm:** Cách producer chọn đích gửi thông điệp, thời điểm ràng buộc `Destination`, sự khác nhau giữa API JMS truyền thống và JMS 2.0/Jakarta Messaging, kèm thực hành gửi vào queue/topic của Artemis.

## 1. Bài toán: một producer luôn gửi vào một đích, hay chọn đích theo từng sự kiện?

Giả sử dịch vụ đơn hàng phát ba loại tác vụ:

- `orders`: đưa yêu cầu xử lý đơn vào queue `lab.producer.orders`.
- `email`: đưa yêu cầu gửi thư vào queue `lab.producer.email`.
- `events`: công bố `OrderCreated` lên topic `lab.producer.events` để các subscription nhận độc lập.

Có hai nhu cầu thiết kế khác nhau:

1. Một thành phần chuyên trách gửi **tất cả** message đến cùng một queue; ví dụ `OrderCommandPublisher` luôn gửi vào `lab.producer.orders`.
2. Một thành phần nhận kết quả phân loại nghiệp vụ rồi chọn **destination cho từng message ngay khi gửi**; ví dụ `RoutingPublisher` gửi một đơn vào queue xử lý, một tác vụ vào queue email và một sự kiện ra topic.

Điểm quyết định nằm ở **MessageProducer được tạo có gắn destination hay không**. Việc truyền một tên destination dưới dạng chuỗi khi chương trình chạy không tự làm nó thành destination đã tồn tại trên broker. JMS cần tạo/nhận đối tượng `Queue` hoặc `Topic` thích hợp, còn broker vẫn cần routing và quyền truy cập chính xác.

### Kết quả cần đạt

Sau bài học, bạn có thể:

1. Dùng `Session.createProducer(destination)` để gửi đến destination cố định bằng `producer.send(message)`.
2. Dùng `Session.createProducer(null)` để tạo **unidentified/anonymous producer**, rồi chọn destination ở từng lời gọi `producer.send(destination, message)`.
3. Hiểu vì sao `JMSContext.createProducer()` trả về `JMSProducer` có API `send(destination, ...)` và không có bước “gắn destination” lúc tạo producer.
4. Chọn giữa queue và topic đúng nghiệp vụ khi destination được xác định lúc chạy; kiểm tra routing type tương ứng trên Artemis.
5. Dùng allowlist, transaction, idempotency và quan sát vận hành để tránh gửi nhầm destination hoặc tạo quá nhiều queue động.

## 2. Hai kiểu MessageProducer trong API JMS truyền thống

JMS 1.1 và các giao diện tương đương trong Jakarta Messaging vẫn cung cấp cách tạo producer qua `Session`:

~~~java
Queue orders = session.createQueue("lab.producer.orders");

// Producer xác định đích ngay khi tạo.
MessageProducer fixed = session.createProducer(orders);
fixed.send(message);

// Producer chưa gắn destination lúc tạo.
MessageProducer dynamic = session.createProducer(null);
dynamic.send(orders, message);

Queue email = session.createQueue("lab.producer.email");
dynamic.send(email, anotherMessage);
~~~

Hai lối gửi này khác nhau ở **chữ ký phương thức** và **thời điểm chọn đích**, không phải là hai loại broker hay hai giao thức truyền riêng.

| Tiêu chí | Producer có destination cố định | Producer không gắn destination lúc tạo |
|---|---|---|
| Cách tạo | `session.createProducer(destination)` | `session.createProducer(null)` |
| Cách gửi phù hợp | `producer.send(message)` | `producer.send(destination, message)` |
| Chọn đích khi nào? | Khi tạo producer | Với mỗi lệnh `send` |
| Đích có thể đổi giữa hai lần `send`? | Không theo hợp đồng của producer đã bind | Có, miễn destination hợp lệ và được phép |
| `producer.getDestination()` | Trả destination đã gắn | Trả `null` |
| Dùng thích hợp | Một publisher một queue/topic cố định | Router, gateway, workflow phát đến vài destination đã cho phép |
| Nguy cơ cấu hình | Gửi mọi thông điệp đến một đích sai | Gửi nhầm giữa nhiều đích, phát tán số lượng queue/topic nếu thiếu kiểm soát |

**Quy tắc API:** Với producer đã bind, dùng `send(message)`; với anonymous producer, dùng `send(destination, message)`. Không trộn hai kiểu gọi trên cùng producer rồi dựa vào hành vi riêng của provider. Cụ thể, `send(message)` trên producer không có default destination và `send(destination, message)` trên producer đã bind không phải các trường hợp sử dụng hợp lệ theo hợp đồng JMS. Kiểu exception cụ thể có thể khác giữa JMS API và provider; hãy tránh tạo tình huống sai ngay từ đầu.

~~~mermaid
flowchart LR
    S[Session] --> F[createProducer queue A]
    F --> F1[send message 1]
    F --> F2[send message 2]
    F1 --> QA[(Queue A)]
    F2 --> QA
    S --> U[createProducer null]
    U --> U1[send Queue A message]
    U --> U2[send Queue B message]
    U --> U3[send Topic C message]
    U1 --> QA
    U2 --> QB[(Queue B)]
    U3 --> TC[(Topic C)]
~~~

### Không nhầm “destination cố định” với tên hardcode

Đích cố định có thể được lấy từ **cấu hình** hoặc **JNDI administered object**, chứ không nhất thiết phải hardcode:

~~~java
// ordersQueue được inject hoặc lookup từ cấu hình/JNDI.
MessageProducer producer = session.createProducer(ordersQueue);
producer.send(orderMessage);
~~~

Ngược lại, destination được xác định lúc chạy không có nghĩa người dùng bên ngoài được phép nhập bất kỳ tên queue/topic nào. Một router an toàn có thể chọn trong ba destination cố định đã cấu hình; quyết định chọn **route nào** xảy ra tại runtime, còn tập route vẫn do ứng dụng kiểm soát.

### Session, connection và tài nguyên producer

- Cả hai producer đều thuộc **Session** nơi chúng được tạo và sử dụng connection của session đó.
- Việc gửi message **không cần** gọi `connection.start()`; lệnh `start()` chủ yếu điều khiển giao message đến consumer.
- `Session` thông thường **không được chia sẻ đồng thời giữa nhiều thread**. Dùng một session/producer theo vòng đời thích hợp, hoặc dùng connection/session pool do framework quản lý.
- Không tạo connection và session mới cho **mỗi message** nếu nhu cầu chỉ là đổi destination; anonymous producer có thể gửi liên tiếp đến nhiều đích.
- Đóng producer, session và connection sau khi dùng. Một producer bị đóng không được gửi tiếp.

## 3. Lựa chọn destination trong JMS 2.0/Jakarta Messaging

API đơn giản hóa `JMSContext` / `JMSProducer` dùng một hình thức khác:

~~~java
try (JMSContext context = factory.createContext(
        user, password, JMSContext.SESSION_TRANSACTED)) {

    Queue orders = context.createQueue("lab.producer.orders");
    Queue email = context.createQueue("lab.producer.email");

    JMSProducer sender = context.createProducer()
        .setDeliveryMode(DeliveryMode.PERSISTENT);

    sender.send(orders, context.createTextMessage("OrderReceived"));
    sender.send(email, context.createTextMessage("SendConfirmation"));

    context.commit();
}
~~~

Ở đây, `context.createProducer()` **không nhận** destination và `JMSProducer.send(...)` **nhận** destination theo từng lần gửi. Điều đó không bắt buộc application phải là “router động”; một component có thể luôn truyền cùng biến `orders` để giữ đích logic cố định.

| API | Gắn destination khi tạo producer | Gửi đến destination mỗi lần |
|---|---|---|
| `Session / MessageProducer` | `session.createProducer(queue)` | `session.createProducer(null)` rồi `send(queue, message)` |
| `JMSContext / JMSProducer` | Không có overload `createProducer(destination)` | `context.createProducer().send(queue, message)` |

**Mục đích của sự khác biệt API:** Khi đọc mã của hai dự án, đừng kết luận “JMSProducer luôn là producer động về nghiệp vụ” chỉ vì `send` nhận đích. Bản chất routing phụ thuộc quyết định ứng dụng: truyền hằng số cấu hình hay tính destination từ ngữ cảnh xử lý.

Nếu chương trình đang dùng ActiveMQ Classic, cần chọn đúng client library và namespace JMS tương thích. Ví dụ triển khai bên dưới chủ đích dùng **Artemis Jakarta JMS client**; giao diện `Session` / `MessageProducer` hoạt động theo JMS, nhưng không được trộn các dependency `javax.jms` và `jakarta.jms` một cách tùy tiện.

## 4. Destination có được tạo trên broker ngay khi gọi createQueue/createTopic không?

Không nên suy ra như vậy.

~~~java
Queue q = session.createQueue("lab.producer.orders");
Topic t = session.createTopic("lab.producer.events");
~~~

Hai lời gọi này tạo **đối tượng Destination để ứng dụng dùng**. Việc broker tự tạo address/queue, từ chối tên chưa tồn tại hay map destination theo quy tắc riêng phụ thuộc **provider, giao thức và cấu hình broker**. Đối tượng `Queue` có thể tồn tại hợp lệ trong JVM dù broker chưa được cấu hình để route message vào queue tương ứng.

Với Artemis, lưu ý:

- **Queue JMS** thường dùng routing **anycast** đến queue thích hợp.
- **Topic JMS** thường dùng routing **multicast** đến các subscription queue.
- `auto-create-addresses` và `auto-create-queues` có thể khiến broker tự sinh tài nguyên khi thao tác. Điều đó **không phải tính năng tạo Queue của Java** và không nên dựa vào như một chính sách vận hành mặc định cho mọi môi trường.
- Đích có tên giống nhau nhưng khác loại `Queue`/`Topic` có thể áp dụng routing khác nhau.
- **Topic không tự lưu bản sao message cho một subscriber chưa tồn tại**. Nếu muốn kiểm chứng gửi topic, cần subscription hoặc multicast queue được tạo **trước khi publish**.

Nên định nghĩa destination ở phía broker hoặc dùng cơ chế provisioning có kiểm soát, sau đó để ứng dụng chọn **logical route**. Bài lab tiếp theo dùng hai anycast queue và một multicast topic đã khai báo tường minh để không phụ thuộc auto-create.

## 5. Cấu hình Artemis cho ba destination thử nghiệm

Giả sử ActiveMQ Artemis instance chạy local qua acceptor Core tại `tcp://127.0.0.1:61616`. Trong file `ARTEMIS_INSTANCE/etc/broker.xml`, tìm section `<addresses>` hiện có và thêm các address sau **chỉ khi chúng chưa tồn tại**:

~~~xml
<address name="lab.producer.orders">
    <anycast>
        <queue name="lab.producer.orders">
            <durable>true</durable>
        </queue>
    </anycast>
</address>

<address name="lab.producer.email">
    <anycast>
        <queue name="lab.producer.email">
            <durable>true</durable>
        </queue>
    </anycast>
</address>

<address name="lab.producer.events">
    <multicast>
        <queue name="lab.producer.audit">
            <durable>true</durable>
        </queue>
    </multicast>
</address>
~~~

**Giải thích thiết kế:**

- `lab.producer.orders` là địa chỉ anycast có queue cùng tên dành cho command xử lý đơn.
- `lab.producer.email` là queue anycast khác, có backlog độc lập.
- `lab.producer.events` là địa chỉ multicast. Queue `lab.producer.audit` được định nghĩa sẵn để giữ **một bản sao** của từng event publish tới topic đó. Nếu không có subscription queue phù hợp, message topic có thể không được giữ.
- Ba destination đã tồn tại theo cấu hình; khi gửi runtime, producer chỉ **chọn** destination chứ không sinh tên queue không giới hạn.

Đây là đoạn **bên trong `<addresses>`**, không phải file `broker.xml` hoàn chỉnh. Không thêm một section `<addresses>` thứ hai, không thay root XML hoặc xóa các setting broker được sinh bởi instance. Dừng/khởi động lại broker trong môi trường lab để chắc chắn cấu hình đã được nạp.

Nếu broker bật phân quyền, ứng dụng producer cần quyền `send` đối với các address trên. Ví dụ cấp quyền cho role `producer-lab` trong section `<security-settings>` hiện có:

~~~xml
<security-setting match="lab.producer.#">
    <permission type="send" roles="producer-lab"/>
    <permission type="consume" roles="producer-lab"/>
</security-setting>
~~~

Trong bài lab có thể cấp cả `consume` cho cùng tài khoản để kiểm chứng, nhưng ứng dụng thật nên phân role producer và consumer riêng theo nguyên tắc ít quyền nhất. Đảm bảo role tồn tại trong cơ chế xác thực của instance. Cấu hình `security-setting` minh họa quyền gửi/nhận; các quyền quản trị và tự tạo/xóa queue có cơ chế riêng.

### Nếu chuyển cùng mã sang ActiveMQ Classic

API `Session.createProducer(destination)`, `createProducer(null)` và `MessageProducer.send(destination, message)` vẫn là khái niệm JMS, nhưng **không sao chép `broker.xml` Artemis sang Classic**. ActiveMQ Classic có cấu hình destination/policy khác (ví dụ `activemq.xml`), client factory và version JMS khác. So sánh trong bài này nằm ở cấp **JMS producer contract**; phần address/anycast/multicast là cơ chế riêng của Artemis.

## 6. Java thực hành: producer cố định và producer chọn destination lúc chạy

### 6.1. Điều kiện và dependency

Ví dụ dùng Java 17, Artemis Jakarta JMS client, broker đang chạy và queue/topic đã được khai báo như phần 5. Tài khoản kết nối được truyền qua biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD`, không viết mật khẩu vào source.

Trong `pom.xml` của project thực hành độc lập, đặt phiên bản client cụ thể đã kiểm chứng tương thích với broker:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <artemis.version>2.33.0</artemis.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>${artemis.version}</version>
    </dependency>
</dependencies>
~~~

`2.33.0` là ví dụ version để minh họa cấu hình Maven; khi triển khai, kiểm tra yêu cầu JDK, namespace API và tương thích với bản broker thực tế. Nếu dự án đang dùng `javax.jms`, phải chọn đúng dòng Artemis client phù hợp thay vì thay mỗi import một cách cơ học.

### 6.2. Mã nguồn gửi ba mode

Lớp `ProducerDestinationLab` có ba cách chạy:

- `fixed`: gửi một message vào queue `lab.producer.orders` bằng **producer có destination cố định**.
- `dynamic orders|email|events`: nhận một **logical route** khi chạy, rồi gửi một message bằng **anonymous producer**.
- `batch`: tái sử dụng **một anonymous producer** gửi liên tiếp ba message đến hai queue và một topic, sau đó commit trong cùng JMS session transaction.

~~~java
import jakarta.jms.Connection;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;

public final class ProducerDestinationLab {

    private static final String BROKER_URL = "tcp://127.0.0.1:61616";

    public static void main(String[] args) throws Exception {
        if (!validArgs(args)) {
            printUsage();
            return;
        }

        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(BROKER_URL);
        Connection connection = factory.createConnection(user, password);

        try {
            // Một transaction JMS cho toàn bộ lệnh gửi trong mỗi lần chạy.
            Session session = connection.createSession(
                true, Session.SESSION_TRANSACTED);

            try {
                switch (args[0]) {
                    case "fixed" -> sendFixed(session);
                    case "dynamic" -> sendDynamic(session, args[1]);
                    case "batch" -> sendBatch(session);
                    default -> throw new IllegalArgumentException(
                        "Mode không hợp lệ: " + args[0]);
                }

                // Lúc này các message mới được commit vào JMS transaction.
                session.commit();
                System.out.println("JMS transaction COMMITTED.");
            } catch (JMSException | RuntimeException failure) {
                try {
                    session.rollback();
                } catch (JMSException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    // Producer đã bind: chỉ cần send(message).
    private static void sendFixed(Session session) throws JMSException {
        Queue orders = session.createQueue("lab.producer.orders");
        MessageProducer producer = session.createProducer(orders);

        try {
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);
            System.out.println("Fixed destination: "
                + producer.getDestination());

            TextMessage message = newMessage(session, "orders");
            producer.send(message);

            logSent("fixed/orders", message);
        } finally {
            producer.close();
        }
    }

    // Producer anonymous: chọn destination ngay lúc gửi.
    private static void sendDynamic(
        Session session, String route) throws JMSException {

        Destination destination = resolveRoute(session, route);
        MessageProducer producer = session.createProducer(null);

        try {
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);
            System.out.println("Anonymous destination: "
                + producer.getDestination()); // null

            TextMessage message = newMessage(session, route);
            producer.send(destination, message);

            logSent("dynamic/" + route, message);
        } finally {
            producer.close();
        }
    }

    // Một anonymous producer có thể gửi qua nhiều destination.
    private static void sendBatch(Session session) throws JMSException {
        MessageProducer producer = session.createProducer(null);

        try {
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);

            for (String route : new String[]{"orders", "email", "events"}) {
                Destination destination = resolveRoute(session, route);
                TextMessage message = newMessage(session, route);
                producer.send(destination, message);
                logSent("batch/" + route, message);
            }
        } finally {
            producer.close();
        }
    }

    // Chỉ cho phép các route do hệ thống định nghĩa.
    // Không dùng tên destination tùy ý từ HTTP request.
    private static Destination resolveRoute(
        Session session, String route) throws JMSException {

        return switch (route) {
            case "orders" -> session.createQueue("lab.producer.orders");
            case "email" -> session.createQueue("lab.producer.email");
            case "events" -> session.createTopic("lab.producer.events");
            default -> throw new IllegalArgumentException(
                "Route chưa được phép: " + route);
        };
    }

    private static TextMessage newMessage(
        Session session, String route) throws JMSException {

        String eventId = UUID.randomUUID().toString();

        TextMessage message = session.createTextMessage(
            "{\"schemaVersion\":1,\"eventId\":\"" + eventId
            + "\",\"route\":\"" + route + "\"}");

        message.setStringProperty("eventId", eventId);
        message.setStringProperty("logicalRoute", route);
        message.setStringProperty("schemaVersion", "1");

        return message;
    }

    private static void logSent(
        String route, TextMessage message) throws JMSException {

        System.out.println(route
            + " eventId=" + message.getStringProperty("eventId")
            + " JMSMessageID=" + message.getJMSMessageID());
    }

    private static boolean validArgs(String[] args) {
        if (args.length == 1) {
            return "fixed".equals(args[0]) || "batch".equals(args[0]);
        }
        if (args.length == 2 && "dynamic".equals(args[0])) {
            return "orders".equals(args[1])
                || "email".equals(args[1])
                || "events".equals(args[1]);
        }
        return false;
    }

    private static void printUsage() {
        System.out.println("ProducerDestinationLab fixed");
        System.out.println(
            "ProducerDestinationLab dynamic <orders|email|events>");
        System.out.println("ProducerDestinationLab batch");
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + key);
        }
        return value;
    }
}
~~~

**Điểm quan trọng trong mã:**

- `sendFixed()` tạo producer bằng `createProducer(orders)`, vì vậy lời gọi hợp lệ là `producer.send(message)`.
- `sendDynamic()` và `sendBatch()` tạo producer bằng `createProducer(null)`, sau đó gọi `send(destination, message)`.
- `resolveRoute()` chỉ map **ba logical route** được cho phép; đây là nơi thực hiện lựa chọn destination **ở runtime**.
- `createQueue(...)` và `createTopic(...)` không được dùng như bằng chứng rằng broker đã provision xong destination; ba address/queue trong lab được khai báo sẵn.
- Không cần `connection.start()` cho chỉ gửi message. Khi viết consumer kiểm chứng thì cần start connection nếu dùng API Session/MessageConsumer truyền thống.
- `DeliveryMode.PERSISTENT` được cấu hình cho producer; lưu trữ bền vững còn phụ thuộc persistence, journal và broker thực tế.
- Các lệnh `logSent` chạy **trước** `session.commit()`, nên dòng “send” không chứng minh message đã tồn tại bền vững. Chỉ báo `COMMITTED` khi commit trả về thành công.
- Với `batch`, các lệnh gửi trên cùng transacted session thuộc **một JMS transaction**. Đó không phải transaction nguyên tử giữa JMS và database của ứng dụng.

### Ranh giới của transaction và lỗi không xác định kết quả

Nếu `session.commit()` ném exception do đứt kết nối, ứng dụng có thể **không biết chắc** broker đã commit hay chưa. Không thể kết luận một cách máy móc rằng “nếu Java bắt exception thì không có message”. Việc retry phải dùng **định danh nghiệp vụ ổn định** cho cùng tác vụ.

Ví dụ `newMessage()` sinh UUID cho từng lần chạy để quan sát, phù hợp lab. Trong production, `eventId` hoặc `commandId` phải gắn với bản ghi nghiệp vụ/outbox và được **tái sử dụng khi retry**. Nếu lỗi mạng rồi gửi lại với UUID mới, consumer không thể dễ dàng phát hiện đây là cùng một nghiệp vụ. Trường hợp message đã được xử lý nhưng consumer chưa ACK cũng cần idempotency phía nhận.

## 7. Kiểm chứng bằng queue depth và consumer

Đặt cả ba queue trong trạng thái rỗng trước khi thử:

- Queue `lab.producer.orders`: 0.
- Queue `lab.producer.email`: 0.
- Queue `lab.producer.audit` (queue multicast của topic `lab.producer.events`): 0.

Sau khi chạy ứng dụng với từng mode theo đúng thứ tự bên dưới, hãy xem queue count trong Artemis Console hoặc công cụ quản trị:

| Lần chạy | Destination được gửi | Orders queue | Email queue | Audit queue |
|---|---|---:|---:|---:|
| Ban đầu | Chưa gửi | 0 | 0 | 0 |
| `fixed` | Queue `orders` | 1 | 0 | 0 |
| `dynamic email` | Queue `email` | 1 | 1 | 0 |
| `dynamic events` | Topic `events`, được route đến queue audit | 1 | 1 | 1 |
| `batch` | Queue `orders`, queue `email`, topic `events` | 2 | 2 | 2 |

Bảng giả định **không có consumer khác**, không có message cũ, message không hết hạn và mọi transaction commit thành công. Với publisher gửi đến topic, queue audit phải tồn tại trước khi publish; không có queue/subscription nào thì không thể khẳng định message đã được giữ để xem sau.

### Mã kiểm chứng ngắn bằng JMSContext

Sau khi hoàn thành chuỗi gửi, dùng mã sau trong một chương trình Java riêng hoặc phương thức test để đọc một message từ queue bất kỳ. Ví dụ đọc queue `lab.producer.orders`:

~~~java
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class VerifyOrderQueue {
    public static void main(String[] args) throws Exception {
        String user = System.getenv("ARTEMIS_USER");
        String password = System.getenv("ARTEMIS_PASSWORD");
        if (user == null || user.isBlank()
            || password == null || password.isBlank()) {
            throw new IllegalStateException(
                "Thiếu ARTEMIS_USER hoặc ARTEMIS_PASSWORD");
        }

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

        try (JMSContext ctx = factory.createContext(
            user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue orders = ctx.createQueue("lab.producer.orders");
            Message message = ctx.createConsumer(orders).receive(3000);

            if (message == null) {
                System.out.println("Không nhận được message trong 3 giây.");
                return;
            }
            if (!(message instanceof TextMessage)) {
                ctx.rollback();
                throw new IllegalArgumentException(
                    "Bài lab chỉ xử lý TextMessage.");
            }

            TextMessage text = (TextMessage) message;
            System.out.println("Body: " + text.getText());
            System.out.println("eventId: "
                + text.getStringProperty("eventId"));
            System.out.println("logicalRoute: "
                + text.getStringProperty("logicalRoute"));

            // Lab chỉ in log; production phải xử lý nghiệp vụ
            // và idempotency trước commit.
            ctx.commit();
        }
    }
}
~~~

Chương trình trên chỉ đọc **một** message nên queue Orders giảm 1 nếu commit thành công. Có thể thay `orders` bằng queue `lab.producer.email` để kiểm chứng luồng email, hoặc dùng cú pháp **FQQN** của Artemis để đọc multicast queue đã khai báo:

~~~java
Queue audit = ctx.createQueue(
    "lab.producer.events::lab.producer.audit");
~~~

FQQN là cú pháp Artemis `address::queue`, phù hợp khi muốn truy cập trực tiếp queue vật lý nằm dưới multicast address. Đây là tính năng riêng của Artemis, không phải cách đặt tên queue portable cho mọi JMS provider.

## 8. Những quyết định runtime cần kiểm soát

### 8.1. Route từ nghiệp vụ, không nhận tên broker tùy ý

Không nên lập trình:

~~~java
// Không nên: tên queue phụ thuộc trực tiếp vào dữ liệu bên ngoài.
Queue unsafe = session.createQueue(request.getDestinationName());
producer.send(unsafe, message);
~~~

Nếu broker bật auto-create, một người dùng hoặc lỗi client có thể tạo ra nhiều destination lạ, tiêu thụ bộ nhớ/đĩa và làm phân tán dữ liệu. Ngay cả khi auto-create tắt, hệ thống vẫn có nguy cơ gửi sai route hợp lệ.

Nên ánh xạ logical route qua cấu hình được kiểm soát:

~~~java
Destination destination = switch (logicalRoute) {
    case "orders" -> session.createQueue("lab.producer.orders");
    case "email" -> session.createQueue("lab.producer.email");
    case "events" -> session.createTopic("lab.producer.events");
    default -> throw new IllegalArgumentException("Unsupported route");
};
anonymousProducer.send(destination, message);
~~~

Có thể đưa ba tên này vào cấu hình/secret-managed deployment thay vì hardcode trong code, nhưng **vẫn cần allowlist** và cơ chế đánh giá thay đổi route. Không biến user input thành tên queue/topic hoặc tên tenant chưa được kiểm soát.

### 8.2. Queue hay Topic là một quyết định có nghĩa nghiệp vụ

Nếu một message được gửi đến queue `lab.producer.orders`, nhiều consumer cạnh tranh để xử lý **một bản**. Nếu gửi đến topic `lab.producer.events`, một message có thể được nhân bản đến nhiều subscription queue tương ứng. Anonymous producer có thể gửi cả hai kiểu destination, nhưng **không thay đổi semantics** của queue và topic.

Ví dụ:

| Logical route | Kiểu JMS destination | Mục tiêu | Hậu quả khi consumer offline |
|---|---|---|---|
| `orders` | Queue | Một worker nhận nhiệm vụ chuẩn bị đơn | Message persistent có thể chờ trong queue theo cấu hình |
| `email` | Queue | Một worker xử lý email | Message persistent có thể chờ trong queue theo cấu hình |
| `events` | Topic | Nhiều nhóm đăng ký sự kiện | Chỉ các durable subscription/queue phù hợp có thể giữ message cho subscriber offline |

Khi route runtime thay đổi từ `orders` sang `events`, người phát đã thay **hợp đồng phân phối**, không chỉ thay một chuỗi destination. Vì thế route phải là lựa chọn có chủ đích ở cấp nghiệp vụ.

### 8.3. Destination gắn với provider và context

Một `Destination` có thể do provider tạo, JNDI lookup hoặc cấu hình ứng dụng cung cấp. Tránh mang tùy tiện một đối tượng destination thuộc provider khác vào session Artemis rồi giả định tương thích. Trong hệ thống dùng nhiều broker, chọn **ConnectionFactory/Session** tương ứng với broker đang gửi và chuyển logical route sang destination của provider đó.

Nếu đích cần sinh theo tenant động (ví dụ `orders.<tenantId>`), hãy đánh giá kỹ số lượng address/queue, quota, phân quyền, TTL, cleanup và quyền tạo destination trước khi áp dụng. Đôi khi **một queue dùng tenantId làm property** hoặc message grouping phù hợp hơn hàng nghìn queue phát sinh động.

## 9. Hiệu năng: có nên tạo một producer cho mỗi destination?

Không có câu trả lời đúng cho mọi broker và client, nhưng có những lựa chọn vận hành rõ ràng:

| Bối cảnh | Cách chọn hợp lý |
|---|---|
| Service chỉ gửi vào một queue | Producer gắn đích cố định; cách gọi đơn giản, dễ quan sát |
| Service gửi vài destination ổn định | Một producer cố định cho từng đích **hoặc** anonymous producer dùng lại; benchmark trên cấu hình thật |
| Gateway nhiều route khác nhau | Anonymous producer + resolver/allowlist + giới hạn tài nguyên |
| Ứng dụng dùng `JMSContext` | Dùng `JMSProducer.send(destination, ...)`; tái sử dụng context/producer theo vòng đời framework phù hợp |
| Nhiều thread phát song song | Quản lý nhiều session/context hợp lệ hoặc pool, **không chia sẻ Session không thread-safe** |
| Số queue sinh theo tenant rất lớn | Xem lại mô hình route, auto-create, quota và vòng đời queue; tránh sinh destination vô hạn |

Không mặc định rằng anonymous producer luôn chậm hơn producer đã bind, hoặc luôn tiết kiệm tài nguyên hơn: điều này phụ thuộc cách provider thực hiện producer caching, authentication, send và flow control. **Thời gian khởi tạo connection/session, kích thước message, persistence, transaction, network latency và backlog** thường ảnh hưởng đáng kể hơn việc chọn một trong hai overload `send`.

Với producer gửi hàng nghìn message, cần đo:

- Throughput (message/giây) và độ trễ xác nhận send/commit.
- Lỗi routing/authorization theo logical route.
- Thời gian producer bị chặn bởi flow control khi queue/address đầy.
- Độ dài backlog ở từng queue, số message DLQ/expired.
- Chênh lệch giữa **lượt gửi thành công** và **lượt nghiệp vụ hoàn tất** ở consumer.

Cả hai kiểu producer đều chịu quy tắc persistent delivery, expiration/TTL và priority theo cấu hình; chọn dynamic destination không tự thay đổi chính sách redelivery/DLQ của consumer.

## 10. Các lỗi thường gặp và cách kiểm chứng

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `send(message)` lỗi khi producer tạo bằng `createProducer(null)` | Producer không có default destination | Dùng `send(destination, message)` |
| Gửi destination tham số trên producer đã bind gây lỗi | Dùng sai overload với producer có destination cố định | Gọi `send(message)` hoặc tạo anonymous producer |
| Java tạo `Queue` được nhưng message không đến | Broker chưa có queue/auto-create tắt; sai routing type; tên sai | Kiểm tra `broker.xml`, console, address và queue thực tế |
| Gửi topic không thấy message trong queue audit | Queue/subscription chưa tồn tại khi publish; gửi sai type | Tạo multicast queue trước, xác nhận route và retry |
| `JMSSecurityException` hoặc lỗi authorization | Producer không có quyền gửi đến address mới | Kiểm tra role và `security-settings` |
| Bật dynamic routing rồi xuất hiện nhiều queue lạ | Tên destination lấy trực tiếp từ input và broker bật auto-create | Chặn bằng allowlist, quota và chính sách provisioning |
| In log gửi thành công nhưng thiếu message sau đó | Transaction chưa commit, rollback, lỗi đúng lúc commit hoặc TTL/expiry | Đo commit outcome và kiểm tra lỗi/expiry; retry dùng eventId ổn định |
| Message gửi đúng queue nhưng xử lý hai lần | Redelivery hoặc producer retry trong trạng thái commit không chắc chắn | Idempotent consumer, eventId ổn định và theo dõi delivery count |
| Chạy hai producer dùng cùng Session ở nhiều thread phát sinh lỗi | Session không thread-safe | Sử dụng session riêng/pool; tránh chia sẻ trực tiếp |
| Thay tên destination xong mất sự kiện | Route mới không có subscriber/queue hoặc khác semantics | Kiểm tra migration, tạo subscription trước, quản lý backlog đích cũ |

### Thử nghiệm lỗi có chủ đích

1. Dùng `session.createProducer(null)` rồi gọi `send(message)` để thấy API từ chối khi không có destination mặc định; xử lý exception trong bài lab riêng.
2. Gửi đến một destination chưa được provision trong Artemis với auto-create **đã tắt theo cấu hình lab**: quan sát lỗi hoặc kết quả route cụ thể, sau đó khai báo destination đúng và thử lại.
3. Gửi message vào topic trước khi có subscription nào rồi tạo subscription sau: kiểm tra message cũ có thể được nhận hay không. Đừng lấy `producer.send()` thành công làm bằng chứng đã có subscriber giữ bản sao.
4. Cố tình thử role chỉ có quyền `send` trên `orders` rồi gửi `email`: kiểm tra lỗi authorization theo route.
5. Thử rollback giao dịch `batch` trước commit: xác nhận không có message mới nào được commit lên cả ba destination trong transaction đó.

Các thử nghiệm lỗi nên thực hiện trong broker local, với queue có thể xóa và không chứa dữ liệu thật.

## 11. Bài tập thực hành mở rộng

### Bài 1 — Giữ route runtime nhưng destination được cấu hình

Chuyển ba tên queue/topic khỏi phương thức `resolveRoute()` sang cấu hình đọc khi khởi động. Khi chạy `dynamic email`, producer phải chọn đích email từ allowlist mà **không** nhận trực tiếp chuỗi destination tùy ý. Xác minh các route không có trong cấu hình bị từ chối trước khi gọi broker.

### Bài 2 — Một transaction gửi nhiều loại message

Trong mode `batch`, thêm `correlationId` chung cho ba message và giữ `eventId` riêng từng message. Giải thích hai lựa chọn: một sự kiện nghiệp vụ phát tới nhiều đích với **cùng eventId** để idempotency xuyên các nhóm, hoặc ba command riêng có ba ID khác nhau nhưng liên quan cùng `correlationId`. Kiểm tra câu trả lời dựa trên hợp đồng nghiệp vụ, không chỉ cách sinh UUID.

### Bài 3 — Di chuyển từ producer cố định sang router động

Một hệ thống đang gửi email bằng cách gắn `MessageProducer` với `email.queue.v1`. Khi cần hỗ trợ thêm `email.queue.v2` trong thời gian migration, hãy thiết kế hai cách:

1. Duy trì hai producer cố định và chọn producer theo phiên bản người nhận.
2. Dùng một anonymous producer và chọn destination theo allowlist.

So sánh cách cấp quyền, quan sát backlog, xử lý rollback và dọn queue cũ. Không phát đồng thời cả hai queue nếu điều đó khiến cùng email được gửi hai lần ngoài ý định.

### Câu hỏi tự kiểm tra

1. `session.createProducer(orders)` và `session.createProducer(null)` khác nhau ở đâu, và mỗi producer dùng overload `send` nào?
2. Có thể gọi `createQueue("unknown.name")` trong Java dù broker chưa có queue không? Kết quả gửi phụ thuộc yếu tố nào?
3. Vì sao `JMSProducer.send(destination, message)` không đồng nghĩa ứng dụng nhất thiết đang định tuyến động?
4. Trong một transaction JMS, `producer.send(...)` đã trả về nhưng `session.commit()` chưa chạy. Có thể xem message đã commit chưa?
5. Tại sao gửi thành công đến topic không chứng minh subscriber tạo sau đó sẽ nhận được message cũ?
6. Vì sao một HTTP parameter chứa tên destination là nguồn rủi ro lớn nếu broker bật auto-create?
7. Trong ví dụ mode `batch`, ba message được gửi qua một producer nhưng vào ba destination: những phần nào thuộc cùng JMS transaction, và những phần nào **không** thuộc transaction đó?
8. Nếu một consumer đọc message từ queue `orders` rồi thấy `logicalRoute=email`, bạn nên kiểm tra điều gì trước tiên?

**Đáp án gợi ý:** (1) Bind lúc tạo hay gửi đích lúc send; (2) có thể tạo object client, broker quyết định routing/auto-create; (3) có thể truyền cùng destination cố định mỗi lần; (4) chưa; (5) topic không lưu lịch sử cho subscriber chưa tồn tại trừ khi đã có subscription queue phù hợp; (6) tạo tài nguyên ngoài ý muốn, phân quyền/routing sai; (7) send/commit JMS thuộc một session transaction, cập nhật DB/HTTP bên ngoài không tự tham gia; (8) logic resolver, mapping queue/topic và property ghi trên message.

## 12. Ghi nhớ khi triển khai

**Producer có destination cố định** làm mã rõ ràng khi một component luôn gửi đến một queue/topic. **Producer không gắn destination khi tạo** cho phép chọn đích ở từng lệnh gửi, hữu ích với routing theo nghiệp vụ nhưng phải được kiểm soát bằng logical route và allowlist. Trong JMS 2.0/Jakarta Messaging, `JMSProducer` luôn nhận destination tại `send(...)`; cách dùng cố định hay động là quyết định của ứng dụng.

Khi chạy với ActiveMQ Artemis, hãy xác nhận **address, queue, anycast/multicast, security, auto-create** trước khi so sánh kết quả; một đối tượng `Destination` ở client không bảo đảm message có nơi lưu ở broker. Khi chuyển giữa ActiveMQ Classic và Artemis, giữ đúng hợp đồng JMS nhưng kiểm tra cấu hình destination/routing và client tương thích. Mọi lần gửi cần xác định ranh giới `send`/`commit`, xử lý kết quả không chắc chắn và dùng eventId ổn định ở nghiệp vụ để an toàn khi retry.

**Tài liệu tham khảo chính:** Jakarta Messaging API `Session`, `MessageProducer`, `JMSContext` và `JMSProducer` tại [Jakarta Messaging](https://jakarta.ee/specifications/messaging/); mô hình address/anycast/multicast và auto-create trong [Apache ActiveMQ Artemis Documentation](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html).
