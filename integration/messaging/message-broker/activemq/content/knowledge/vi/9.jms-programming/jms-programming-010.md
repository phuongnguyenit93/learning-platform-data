# JNDI, cấu hình trực tiếp và quản lý tài nguyên an toàn

> **Chương:** Lập trình JMS  
> **Phạm vi:** Ứng dụng Java giao tiếp với Apache ActiveMQ Classic hoặc Apache Artemis qua JMS/Jakarta Messaging. Bài tập trung vào cách cung cấp `ConnectionFactory`/`Destination`, phân định quyền sở hữu tài nguyên và đóng chúng đúng cách. Các ví dụ Java dùng **JDK 17 + `jakarta.jms`**; với ActiveMQ Classic 5.x dùng đúng biến thể `javax.jms` hoặc client Jakarta tương thích.

## 1. Ba quyết định thiết kế trước khi viết producer/consumer

Một chương trình JMS có thể gửi message thành công lúc chạy thử nhưng khi triển khai lâu dài lại rò rỉ connection, không nhả consumer, hoặc trỏ sai broker sau khi đổi môi trường. Trước khi gọi `createConnection()` hay `createContext()`, cần thống nhất:

| Câu hỏi | Phương án | Hệ quả đối với mã nguồn |
|---|---|---|
| Lấy `ConnectionFactory` và `Queue`/`Topic` từ đâu? | JNDI, tạo trực tiếp, hoặc container injection | Tách mã nghiệp vụ khỏi cách chọn broker và tên destination |
| Ai sở hữu tài nguyên? | Ứng dụng Java SE hoặc Jakarta EE container | Ai tạo thì chịu trách nhiệm đóng, trừ tài nguyên do container quản lý |
| Tài nguyên tồn tại bao lâu? | Factory dùng lại, connection/context theo tác vụ hoặc qua pool có quản lý | Không mở connection tùy tiện cho mỗi message; không chia sẻ `Session` sai thread |

**Cần phân biệt hai việc**:

- **Tra cứu/khởi tạo đối tượng JMS**: trả về một `ConnectionFactory` hoặc một đối tượng mô tả destination ở phía client.
- **Tạo kết nối thật và trao đổi message**: thông thường bắt đầu khi ứng dụng gọi `createConnection(...)`/`createContext(...)` và sau đó gửi/nhận. Một JNDI lookup thành công **không chứng minh broker đang chạy**, cũng không bảo đảm queue đã được broker cấp phát.

## 2. JNDI quản lý tên logic, không phải một JMS wire protocol

JNDI (`javax.naming`) là API tra cứu tên Java. Đặc tả JMS/Jakarta Messaging cho phép lấy các **administered objects** như `ConnectionFactory`, `Queue` và `Topic` qua JNDI. `javax.naming` vẫn là namespace của Java SE, **kể cả khi ứng dụng dùng `jakarta.jms`**; không đổi thành `jakarta.naming`.

Ví dụ ứng dụng chỉ biết hai tên:

```text
JNDI name         Đối tượng JMS              Broker thực tế
----------------------------------------------------------------
ConnectionFactory -> JMS ConnectionFactory -> tcp://broker:61616
orders            -> Queue "orders.in"      -> Queue orders.in
```

Nhờ đó cùng một đoạn mã Java có thể chạy ở máy phát triển và staging bằng cách đổi cấu hình tên/endpoint. Tuy nhiên **ActiveMQ Classic và Artemis không cung cấp một JNDI registry server dùng chung**: ở mô hình Java SE đơn giản, mỗi sản phẩm có `InitialContextFactory` tự tạo các đối tượng ở phía client từ properties. Khi chạy trong application server như WildFly, JNDI có thể do chính container cung cấp; phải sử dụng tên và cơ chế cấu hình container đó.

### 2.1. ActiveMQ Classic: `jndi.properties`

Ví dụ cho ứng dụng Java SE với **Classic 6.4.x**. Tạo `src/main/resources/jndi.properties`:

```properties
java.naming.factory.initial=org.apache.activemq.jndi.ActiveMQInitialContextFactory
java.naming.provider.url=tcp://127.0.0.1:61616

# JNDI name "orders" trỏ tới tên vật lý "orders.in" trên broker.
queue.orders=orders.in

# Có thể định nghĩa topic tương tự:
topic.events=events.changed
```

Ở provider này, `ConnectionFactory` là tên JNDI mặc định thường dùng. `java.naming.provider.url` cung cấp URI kết nối của factory; `queue.orders` chỉ định ánh xạ **tên logic → tên queue vật lý**. Chuỗi `queue.orders` không phải lệnh tạo queue ngay trên broker.

**Không dùng `vm://localhost` trong lab kết nối tới broker riêng tiến trình** trừ khi chủ động cấu hình embedded broker. VM transport của Classic có thể tạo/chọn broker trong cùng JVM và làm kết quả test khác với mong đợi.

### 2.2. Artemis: `jndi.properties`

Với **Artemis 2.57.0** và client Jakarta, thay toàn bộ `jndi.properties` bằng:

```properties
java.naming.factory.initial=org.apache.activemq.artemis.jndi.ActiveMQInitialContextFactory

# Artemis dùng tiền tố connectionFactory.<JNDI-name>=<broker-URI>.
connectionFactory.ConnectionFactory=tcp://127.0.0.1:61616
queue.orders=orders.in
topic.events=events.changed
```

Điểm khác quan trọng: Artemis cấu hình URI của factory bằng `connectionFactory.ConnectionFactory=...`, thay vì giả định nó đọc URI từ `java.naming.provider.url` giống Classic. Cũng như Classic, tên `orders` là binding phía client, không phải một service naming ở broker.

Đối với Artemis, có thể tra cứu `dynamicQueues/orders.in` hoặc `dynamicTopics/events.changed` nếu không khai báo `queue.orders`/`topic.events`. Classic cũng hỗ trợ `dynamicQueues/` và `dynamicTopics/`. Cách tra cứu động tiện cho phép thử, nhưng ở production nên dùng **tên logic có kiểm soát**, tránh lỗi đánh máy tạo destination ngoài dự kiến khi broker bật auto-create.

| Mục | Classic Java SE | Artemis Java SE |
|---|---|---|
| InitialContextFactory | `org.apache.activemq.jndi.ActiveMQInitialContextFactory` | `org.apache.activemq.artemis.jndi.ActiveMQInitialContextFactory` |
| Khai báo broker endpoint | `java.naming.provider.url=tcp://...` | `connectionFactory.ConnectionFactory=tcp://...` |
| Khai báo queue | `queue.orders=orders.in` | `queue.orders=orders.in` |
| Lookup factory | `context.lookup("ConnectionFactory")` | `context.lookup("ConnectionFactory")` |
| Lookup queue | `context.lookup("orders")` | `context.lookup("orders")` |
| Giao thức mặc định của client mẫu | OpenWire | Artemis Core |

**Lưu ý tương thích:** Hai provider có thể cùng trả kiểu `jakarta.jms.ConnectionFactory` trong những dòng phát hành phù hợp, nhưng **không vì thế mà Artemis Core client kết nối trực tiếp với OpenWire-only listener của Classic**. Chọn dependency, URI và giao thức broker tương ứng.

## 3. Ví dụ Java JNDI có đóng tài nguyên rõ ràng

Mục tiêu là kiểm chứng **cùng một mã Java** có thể dùng hai bộ `jndi.properties` ở trên, miễn client provider được chọn đúng. Bài thử chỉ gửi/nhận trên queue lab `orders.in`, dùng một mã nhận dạng riêng để tránh nhận nhầm message do lần chạy khác tạo.

### 3.1. Chọn đúng dependency

Với JDK 17 và `jakarta.jms`, mỗi lần chạy hãy chọn **một** provider:

**Classic 6.4.x — OpenWire:**

```xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>6.4.0</version>
</dependency>
```

**Artemis 2.57.0 — Core:**

```xml
<dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.57.0</version>
</dependency>
```

Đặt `jndi.properties` tương ứng lên **classpath ứng dụng** (ví dụ `src/main/resources` của dự án Maven); không ghép nhiều file cùng tên từ những thư viện/ứng dụng khác rồi phụ thuộc vào thứ tự nạp. Không để cả hai provider được chọn ngẫu nhiên thông qua trùng classpath; quản lý phiên bản bằng Maven dependency tree.

### 3.2. `JndiRoundTrip.java`

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import javax.naming.Context;
import javax.naming.InitialContext;
import java.util.UUID;

public final class JndiRoundTrip {
    private JndiRoundTrip() {}

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường " + name);
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        String user = requiredEnv("BROKER_USER");
        String password = requiredEnv("BROKER_PASSWORD");

        // InitialContext đọc jndi.properties trên classpath.
        Context naming = new InitialContext();
        ConnectionFactory factory = null;
        try {
            factory = (ConnectionFactory) naming.lookup("ConnectionFactory");
            Queue orders = (Queue) naming.lookup("orders");

            String runId = UUID.randomUUID().toString();
            String body = "order-" + runId;

            // Connection, Session, producer và consumer đều AutoCloseable.
            // Chúng đóng theo thứ tự ngược khi khối try kết thúc.
            try (Connection connection = factory.createConnection(user, password);
                 Session session =
                     connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
                 MessageProducer producer = session.createProducer(orders);
                 MessageConsumer consumer = session.createConsumer(
                     orders, "labRunId = '" + runId + "'")) {

                TextMessage outgoing = session.createTextMessage(body);
                outgoing.setStringProperty("labRunId", runId);
                producer.send(outgoing);

                // Legacy JMS Connection phải start trước khi receive.
                connection.start();
                Message received = consumer.receive(5000L);
                if (!(received instanceof TextMessage textMessage)
                        || !body.equals(textMessage.getText())) {
                    throw new IllegalStateException(
                        "Không nhận được đúng message trong 5 giây");
                }
                System.out.println("PASS: " + runId);
            }
        } finally {
            // Bản demo tự tạo JNDI factory trên client, nên ứng dụng sở hữu
            // factory đó; provider có close() riêng thì giải phóng tại đây.
            try {
                if (factory instanceof AutoCloseable ownedFactory) {
                    ownedFactory.close();
                }
            } finally {
                naming.close();
            }
        }
    }
}
```

**Điểm đáng chú ý:**

1. `naming.close()` đóng naming context. `javax.naming.Context` **không** phải đối tượng JMS và không implement `AutoCloseable`; vì vậy ví dụ dùng `finally`.
2. `factory.createConnection(...)` mới thực sự tạo kết nối và xác thực tới broker. `lookup("ConnectionFactory")` có thể thành công cả khi broker đang tắt.
3. `try-with-resources` đóng consumer, producer, session và connection kể cả khi receive timeout hoặc xử lý ném exception. Không dùng `System.exit(...)` bên trong khối này vì có thể bỏ qua việc đóng tài nguyên theo cách bình thường.
4. `Session` không dùng đồng thời giữa nhiều thread. Mọi producer/consumer trong ví dụ cùng thuộc một session do đúng một thread sử dụng.
5. Bộ lọc `labRunId` được tạo từ UUID do ứng dụng sinh; khi xây selector từ input ngoài phải kiểm soát ký tự/kiểu dữ liệu và tránh tự nối chuỗi tùy tiện.

**Điều kiện để lab PASS:** broker đang chạy ở `127.0.0.1:61616` với đúng protocol, có tài khoản được phép gửi/nhận, queue `orders.in` đã được khai báo hoặc broker được cho phép tạo queue tự động. Nếu broker có message cũ không mang `labRunId` tương ứng, selector bảo đảm ví dụ không nhận nhầm message đó. Bài thử không chứng nhận transaction, redelivery hay DLQ.

## 4. Cấu hình trực tiếp khi không cần JNDI

Trong Java SE, nhất là microservice đơn giản, thường dễ quản lý hơn khi tạo `ConnectionFactory` từ cấu hình ứng dụng (URI, credential, tên queue) rồi **inject factory qua constructor** vào lớp nghiệp vụ. Khi đó ứng dụng không phụ thuộc `InitialContext` và `jndi.properties`; đổi lại cần thống nhất nơi cấu hình/validate các thông số.

### Artemis: factory được ứng dụng sở hữu

```java
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class DirectArtemis {
    public static void main(String[] args) {
        String url = System.getenv().getOrDefault(
            "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");
        if (user == null || password == null) {
            throw new IllegalArgumentException("Thiếu thông tin đăng nhập");
        }

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(url);
        try {
            // JMSContext do ứng dụng tạo là AutoCloseable.
            try (JMSContext context = factory.createContext(user, password)) {
                Queue queue = context.createQueue("orders.in");
                context.createProducer().send(queue, "order-direct");
            }
        } finally {
            // Đóng factory Artemis do chương trình tạo sau khi
            // các JMSContext phát sinh từ nó đã được đóng.
            factory.close();
        }
    }
}
```

Đây là ví dụ **Jakarta Messaging 3.x/Artemis Core**. `context.createQueue("orders.in")` tạo một **JMS Queue object phía client**; queue thật trên broker chỉ sử dụng được khi tồn tại hoặc broker cho phép auto-create. Đừng coi việc gọi `createQueue` là thao tác provisioning queue an toàn cho mọi môi trường.

### Classic: cùng ý tưởng, khác implementation

Với Classic 6.4.x, phần tạo provider và tài nguyên theo JMS kiểu truyền thống có thể là:

```java
import jakarta.jms.Connection;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import org.apache.activemq.ActiveMQConnectionFactory;

String uri = "tcp://127.0.0.1:61616";
ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(uri);

try (Connection connection = factory.createConnection(user, password);
     Session session = connection.createSession(
         false, Session.AUTO_ACKNOWLEDGE)) {
    Queue orders = session.createQueue("orders.in");
    try (MessageProducer producer = session.createProducer(orders)) {
        producer.send(session.createTextMessage("order-direct"));
    }
}
```

Đây là **đoạn mã đặt trong một method** có sẵn biến `user`/`password`. `Connection`, `Session` và `MessageProducer` đóng nhờ `try-with-resources`. Trong ví dụ này chỉ gửi message nên không cần `connection.start()`; nếu thêm `receive()` bằng API truyền thống, phải start connection.

**Không thể đổi broker bằng mỗi URI:** Classic factory ở trên dùng OpenWire; Artemis factory dùng Core. Chuyển broker yêu cầu thay provider phù hợp và xác minh giao thức mà acceptor/transportConnector đã bật.

### Khi nào chọn cách nào?

| Tiêu chí | JNDI lookup | Cấu hình trực tiếp | Container-managed resource |
|---|---|---|---|
| Nguồn tên factory/destination | `InitialContext` + binding | Properties/env + constructor | JNDI/injection do app server cấu hình |
| Mức phụ thuộc mã Java | Ít phụ thuộc lớp provider nếu chỉ dùng giao diện JMS | Phần wiring biết provider cụ thể | Mã nghiệp vụ ít phụ thuộc provider |
| Phù hợp | Ứng dụng JMS hiện hữu, triển khai cần đổi binding | Java SE/microservice, cấu hình qua deployment | Jakarta EE có JCA/pooling/transaction manager |
| Ai quản lý `JMSContext`? | Ứng dụng nếu gọi `createContext` | Ứng dụng nếu gọi `createContext` | Container nếu `@Inject` context |
| Rủi ro chính | Sai binding, thiếu `InitialContextFactory`, hiểu nhầm JNDI là server | Hardcode URI/credentials, tạo nhiều factory/connection | Đóng nhầm resource do container quản lý |

Lựa chọn không chỉ dựa vào việc “có JNDI hay không”. Hãy ưu tiên **cách cấu hình đã có trong runtime triển khai**, giữ API JMS ở phần nghiệp vụ và tập trung những chi tiết phụ thuộc broker tại một điểm wiring.

## 5. Quyền sở hữu và vòng đời tài nguyên

Một quy tắc dễ nhớ: **factory dùng lâu, session/context dùng theo phạm vi xử lý, consumer có vòng đời rõ, đóng từ trong ra ngoài**. Đừng dựa vào Java garbage collector để thu hồi socket hoặc consumer phía broker.

| Tài nguyên | Có thể giữ trong thời gian nào? | Ai đóng? | Lưu ý |
|---|---|---|---|
| `InitialContext` do ứng dụng tạo | Trong giai đoạn lookup | Ứng dụng gọi `close()` | Lookup xong có thể đóng context; không đồng nghĩa đóng JMS connection |
| `ConnectionFactory` từ JNDI/container | Thường reuse lâu dài | **Bên sở hữu** factory; container-managed thì để container quản lý | Không giả định giao diện `ConnectionFactory` có `close()`; một số triển khai có |
| Factory provider được tạo bằng `new` | Thường một instance được cấu hình cho ứng dụng | Ứng dụng đóng khi provider hỗ trợ, sau khi các context/connection xong | Tránh tạo factory mới cho từng message |
| `Connection` | Chi phí tương đối cao; có thể được pool/container quản lý | Ứng dụng nếu tự tạo, hoặc trả về pool theo hợp đồng pool | `start()` cần trước khi nhận bằng API truyền thống |
| `Session` | Phạm vi một luồng xử lý | Ứng dụng tạo hoặc vòng đời connection | **Không sử dụng đồng thời** bởi nhiều thread |
| `MessageProducer` / `MessageConsumer` / `QueueBrowser` | Phạm vi hoạt động hoặc service consumer lâu dài | Ứng dụng hoặc vòng đời session/connection | Đóng consumer ngừng đăng ký nhận, giảm rò rỉ phía broker |
| `JMSContext` do `createContext()` tạo | Phạm vi tác vụ/request hoặc một consumer loop có quản lý | Ứng dụng gọi `close()`/`try-with-resources` | `JMSContext` kết hợp connection + session và không thread-safe theo nghĩa dùng đồng thời |
| `JMSContext` được container `@Inject` | Theo phạm vi do Jakarta EE quản lý | **Container**, ứng dụng **không gọi close()** | Container-managed context có các giới hạn về commit/rollback/close |
| `Message`, `Queue`, `Topic` object | Theo tác vụ | Thường không cần `close()` | `TemporaryQueue`/`TemporaryTopic` có vòng đời riêng |

### 5.1. Lỗi phổ biến với `JMSContext` và thread

`JMSContext` kết hợp một connection với một session logic. Theo Jakarta Messaging 3.1, **session chỉ được một thread sử dụng tại một thời điểm**. Vì vậy mã dưới đây **không an toàn** nếu nhiều worker gọi đồng thời:

```java
// Không giữ một JMSContext dùng chung trong singleton rồi để nhiều
// thread gọi song song:
// private final JMSContext context = factory.createContext();
// pool.submit(() -> context.createProducer().send(queue, payload));
```

Thay vào đó, mỗi tác vụ có session/context riêng, hoặc dùng managed connection/session pool của framework:

```java
// Mã chạy trong một worker thread, factory được dùng lại.
try (JMSContext context = factory.createContext(user, password)) {
    context.createProducer().send(
        context.createQueue("orders.in"), payload);
}
```

Trong hệ thống throughput cao, tạo **connection/context mới cho từng message** vẫn có thể tốn kém; cần pool có giới hạn, kiểm soát số session và đóng/hoàn trả đúng hợp đồng. Pool không làm `Session` trở thành thread-safe; chỉ cấp các session/context riêng cho mỗi luồng đang hoạt động.

### 5.2. Consumer chạy lâu và shutdown

Một consumer chạy như service không nhất thiết mở/đóng connection sau mỗi message. Nó có thể giữ một connection và session trong suốt vòng đời worker. Khi dừng service:

1. Ngừng nhận việc mới; cho callback/transaction đang xử lý kết thúc có kiểm soát.
2. Đóng consumer/context/connection theo thứ tự mà framework hoặc ứng dụng sở hữu.
3. Dừng thread/executor sau khi quá trình xử lý và đóng tài nguyên hoàn tất.

Tránh gọi `connection.close()` hoặc `JMSContext.close()` ngay trong chính `MessageListener.onMessage()`: đặc tả cho phép những hành vi khác nhau và có thể chặn hoặc ném exception. Điều khiển shutdown từ lifecycle hook hoặc thread quản lý bên ngoài.

### 5.3. Jakarta EE và managed objects

Trong container Jakarta EE hỗ trợ Jakarta Messaging, tài nguyên có thể được cấu hình và inject:

```java
import jakarta.annotation.Resource;
import jakarta.enterprise.context.RequestScoped;
import jakarta.inject.Inject;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

@RequestScoped
public class OrderPublisher {
    @Resource(lookup = "java:comp/env/jms/Orders")
    private Queue orders;

    // Context được container tạo/đóng theo phạm vi hỗ trợ.
    @Inject
    private JMSContext context;

    public void send(String payload) {
        context.createProducer().send(orders, payload);
    }
}
```

Đây là **minh họa cho Jakarta EE runtime có cấu hình JNDI binding** `java:comp/env/jms/Orders` và default JMS connection factory phù hợp. Trong triển khai thật, nếu phải chọn factory cụ thể, dùng cấu hình injection/qualifier (`@JMSConnectionFactory`) do phiên bản Jakarta EE hỗ trợ. **Không gọi `context.close()` đối với injected context**, cũng không tự quản lý lifecycle của container pool. Một Java SE `main()` hoặc Tomcat thuần không tự có CDI/JMS container đầy đủ chỉ vì thêm các annotation này.

## 6. Cấu hình, credential và lỗi thường gặp

**Phân lớp cấu hình:**

```text
Mã nghiệp vụ: interface JMS + tên logic "orders"
       │
       ├── JNDI binding hoặc factory wiring
       │     ├── Broker URI/protocol/failover
       │     └── Tên queue/topic vật lý
       │
       └── Secret provider (không phải file nguồn)
             └── Username/password hoặc credential tương ứng
```

- Lưu broker URI, JNDI name, tên queue/topic và lựa chọn provider trong cấu hình deployment có review; **không** nhúng mật khẩu vào `jndi.properties`, source code hoặc URL có khả năng bị log.
- Cấp credential bằng secret manager, file có quyền đọc giới hạn hoặc cơ chế container phù hợp. Ví dụ dùng `BROKER_PASSWORD` cho lab đơn giản; production nên có quy trình cấp/rotate credentials và hạn chế quyền truy cập process environment.
- Thiết lập timeout, retry/failover và giới hạn pool theo khả năng xử lý. Lỗi mạng xảy ra trong `createConnection`, gửi hoặc nhận; **không** coi JNDI lookup là health check cho broker.
- Đóng tài nguyên trong mọi nhánh exception. Với thao tác gửi có trạng thái kết quả không rõ sau mất kết nối, đừng tự retry vô hạn khi chưa thiết kế idempotency/deduplication.

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `NoInitialContextException` / `NamingException` | `jndi.properties` không nằm trên classpath, thiếu `java.naming.factory.initial` | Kiểm tra tài nguyên Maven/JAR và initial context factory |
| `ClassNotFoundException` cho `ActiveMQInitialContextFactory` | Thiếu đúng provider dependency | Kiểm tra `mvn dependency:tree` và version phù hợp |
| `NameNotFoundException: orders` | Chưa có `queue.orders` hoặc lookup sai tên logic | Đối chiếu tên `orders` và `orders.in` |
| `ClassCastException` giữa `javax.jms` và `jakarta.jms` | API namespace của app không khớp provider | Đồng bộ toàn bộ dependency và import |
| JNDI lookup PASS, `createConnection` FAIL | Broker chưa chạy, URI/protocol/TLS/auth sai | Kiểm tra socket, log broker, credentials, client provider |
| `InvalidDestinationException` khi send/receive | Queue không tồn tại hoặc broker không cho auto-create | Provision destination hoặc sửa mapping/ACL |
| Số connection/consumer trên broker tăng sau mỗi request | Thiếu `close()`, singleton giữ context, pool cấu hình sai | Dùng try-with-resources hoặc quản lý worker lifecycle, đo JMX |
| Lỗi session dùng đồng thời | Cùng `Session`/`JMSContext` bị nhiều thread chia sẻ | Tạo mỗi thread một session/context hoặc dùng session pool |
| Ứng dụng không thoát khi dừng | Chưa đóng connection/factory/provider threads hoặc executor | Đóng theo thứ tự và xác minh shutdown |

## 7. Bài thực hành kiểm chứng hai kiểu wiring và vòng đời

Thiết lập broker **Classic 6.4.x hoặc Artemis 2.57.0** đang chạy ở `127.0.0.1:61616` và một queue lab `orders.in`; dùng đúng một provider mỗi lần thử. Chạy chương trình `JndiRoundTrip` với bộ `jndi.properties` phù hợp, sau đó chạy ví dụ factory trực tiếp.

| Phép thử | Thao tác | Kết quả kỳ vọng |
|---|---|---|
| 1. Lookup độc lập với network | Tạm dừng broker và thử lookup factory/destination (không `createConnection`) | Binding JNDI client-side vẫn có thể được tạo; bước tạo connection phải thất bại |
| 2. JNDI round trip | Khởi động broker, gọi `JndiRoundTrip` | In `PASS: <uuid>` trong 5 giây, không nhận nhầm message cũ |
| 3. Direct wiring | Chạy `DirectArtemis` với cùng queue và credentials, hoặc đoạn Classic trực tiếp | Producer gửi được mà không cần `InitialContext` |
| 4. Sai mapping | Đổi `queue.orders` sang tên không được broker cấp phép/không tồn tại | Lookup có thể thành công nhưng send/receive bị từ chối |
| 5. Lỗi network | Ngắt broker trong lúc mở connection | Có exception/timeout; `finally`/`try-with-resources` giải phóng tài nguyên |
| 6. Kiểm tra rò rỉ | Lặp chạy nhiều lần, quan sát active connections/consumers qua JMX/metrics broker | Không tăng liên tục sau khi các lần chạy đã đóng |
| 7. Test concurrency | Dùng nhiều worker, mỗi worker sở hữu context/session riêng | Không có lỗi dùng chung session hoặc consumer sai thread |

**Một cách ghi nhận test**: lưu phiên bản JDK, artifact client, broker version, URI, tên binding, thời điểm chạy, kết quả PASS/FAIL và số lượng connection/consumer quan sát trước/sau test. Không lưu username/password hoặc body chứa dữ liệu thật. Nếu `QueueSize` còn tăng, kiểm tra consumer/selector và những message có sẵn; không purge queue nghiệp vụ để làm cho test “xanh”.

### Bài tập mở rộng nhỏ

Tạo hai bộ cấu hình mang cùng JNDI name `orders` nhưng trỏ đến `orders.dev` và `orders.staging` trên hai broker test khác nhau. Chạy **một file `JndiRoundTrip.java` không sửa mã**, thay classpath `jndi.properties` và provider dependency tương ứng. Sau đó chuyển phiên bản direct wiring để lấy `BROKER_URL`, `ORDERS_QUEUE` từ cấu hình. So sánh: JNDI giúp tách tên logic; direct wiring giảm số lớp naming nhưng đòi hỏi tổ chức cấu hình nhất quán. Ở cả hai phương án, test cuối cùng vẫn phải xác nhận connection/consumer được đóng đúng.

## Tài liệu chính thức

1. Apache ActiveMQ Classic — [JNDI Support](https://activemq.apache.org/components/classic/documentation/jndi-support.html): `ActiveMQInitialContextFactory`, `provider.url`, mapping `queue.*`/`topic.*` và lookup động.
2. Apache Artemis 2.57.0 — [Using JMS or Jakarta Messaging](https://artemis.apache.org/components/artemis/documentation/latest/using-jms.html): `connectionFactory.<name>`, `queue.<name>`, JNDI client-side và khởi tạo trực tiếp.
3. Apache Artemis 2.57.0 — [The Client Classpath](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath.html): hai Maven artifacts `artemis-jms-client` và `artemis-jakarta-client`.
4. Jakarta Messaging 3.1 — [JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext): vòng đời `JMSContext` và container-managed injection.
5. Jakarta Messaging 3.1 — [Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): AutoCloseable, threading constraints, connection lifecycle và listener.
