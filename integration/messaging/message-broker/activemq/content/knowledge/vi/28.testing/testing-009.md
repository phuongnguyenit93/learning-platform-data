# Kiểm thử mất kết nối, restart, failover và khôi phục subscription

> **Chương:** Kiểm thử  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue, topic, routing và JMS; thực hành producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi:** Xây dựng bộ kiểm thử có thể lặp lại cho bốn tình huống: **mất kết nối mạng, broker restart, HA failover và phục hồi durable subscription**. Ví dụ chính dùng Artemis 2.x, Java 17 và Jakarta JMS; phần Classic mô tả failover transport và những điểm cần kiểm chứng riêng.

## 1. Không gộp mọi lỗi thành “broker reconnect”

Một producer gửi message tới broker A, consumer nhận message từ topic, sau đó broker restart. Ứng dụng kết nối lại thành công, nhưng chưa đủ để kết luận hệ thống đã phục hồi đúng. Có thể xảy ra các trạng thái khác nhau:

- Producer đã gửi và broker commit, nhưng phản hồi bị mất. Producer không biết message đã được nhận hay chưa.
- Consumer đã nhận message nhưng process chết trước JMS commit. Broker có thể redeliver.
- Consumer đã commit DB nhưng chết trước JMS ACK. Message có thể redeliver và business effect có nguy cơ lặp.
- Durable subscription chưa từng được tạo, nên publisher gửi lúc subscriber offline không có backlog để phục hồi.
- Client đã reconnect tới một broker khác, nhưng broker backup không có đúng state hoặc không được cấu hình HA.
- TCP connection mở lại nhưng authentication, authorization hoặc destination provisioning thất bại.

Bài kiểm thử cần tách **transport recovery**, **broker/store recovery**, **client failover**, **subscription recovery** và **business recovery**. Đây là các lớp khác nhau, mỗi lớp có tiêu chí PASS riêng.

~~~mermaid
flowchart TD
    A["Network interruption"] --> B["Client detects connection failure"]
    C["Broker restart/crash"] --> B
    D["Primary failure"] --> E["HA backup activation"]
    B --> F["Reconnect / topology update"]
    E --> F
    F --> G["Recreate JMS session / consumer"]
    G --> H["Recover durable subscription backlog"]
    H --> I["Redelivery / transaction outcome"]
    I --> J["Idempotent business commit"]
~~~

**Mục tiêu của test:** chứng minh message không mất ngoài RPO đã chấp nhận, message có thể redeliver mà không tạo side effect trùng, consumer phục hồi đúng subscription identity và client kết nối lại đúng topology.

## 2. Phân loại failure và xác định hợp đồng phục hồi

| Failure | Điều bị gián đoạn | Trạng thái broker | Cần chứng minh |
|---|---|---|---|
| Mất mạng client ↔ broker | TCP/TLS và JMS connection | Broker vẫn chạy | Client phát hiện lỗi, reconnect, session/consumer được tạo lại |
| Mất mạng broker A ↔ broker B | Bridge/cluster transport | Hai broker có thể vẫn chạy độc lập | Backlog, retry, duplicate và routing sau phục hồi |
| Graceful restart | Broker chủ động dừng và đóng kết nối | Store được shutdown theo quy trình | Client reconnect; persistent messages/subscription còn |
| Process crash/kill | Kết nối đột ngột, shutdown không sạch | Broker phải recover store | Journal/store recovery, redelivery và data integrity |
| HA failover | Primary không còn phục vụ | Backup được promote theo topology | Client chuyển node, state/queue được phục hồi theo HA mode |
| Consumer process crash | Consumer không ACK/commit | Broker vẫn hoạt động | Message được redeliver; business idempotency |
| Subscriber offline | Consumer không đăng ký kết nối | Durable subscription vẫn tồn tại nếu đã tạo | Message phù hợp được giữ và giao khi cùng subscription quay lại |
| Subscription bị unsubscribe/xóa | Durable identity bị xóa | Backlog có thể bị loại | Hành vi xóa là chủ đích và được audit |

### 2.1. Định nghĩa RPO và RTO cho messaging

- **RPO (Recovery Point Objective):** lượng dữ liệu/message chấp nhận mất trong tình huống lỗi cụ thể. Persistent message đã commit vào broker store có kỳ vọng phục hồi cao hơn non-persistent message, nhưng RPO còn phụ thuộc disk, replication/shared-store và failure domain.
- **RTO (Recovery Time Objective):** thời gian từ lúc lỗi bắt đầu tới khi producer/consumer có thể tiếp tục hoạt động đúng.
- **Delivery guarantee:** at-most-once, at-least-once hoặc một semantics cụ thể của luồng; không dùng từ “exactly-once” nếu chưa xác định boundary.
- **Duplicate tolerance:** hệ thống chịu được bao nhiêu lần delivery cho cùng event ID mà không lặp side effect.
- **Subscription retention:** subscriber offline được giữ message bao lâu, tối đa bao nhiêu dung lượng và khi nào backlog hết hạn.

Ví dụ hợp đồng cho billing:

| Thuộc tính | Mục tiêu lab |
|---|---|
| Producer local commit | p95 dưới 200 ms trong điều kiện bình thường |
| Broker restart RTO | Consumer sẵn sàng lại trong 60 giây |
| Durable subscription | Giữ event phù hợp khi subscriber offline 10 phút |
| Consumer crash trước ACK | Event được redeliver sau recovery |
| Duplicate handling | Một event ID chỉ tạo một business effect |
| Non-durable subscriber | Không yêu cầu nhận lại event đã publish khi offline |

Các con số trên là **mục tiêu minh họa**. Hệ thống thực cần đặt SLO dựa trên tải, topology và SLA nghiệp vụ.

## 3. Phân biệt ACK của producer, ACK của consumer và durable storage

### 3.1. Producer timeout không chứng minh message chưa tới broker

Một producer gửi persistent message. Broker nhận và commit message vào store, nhưng kết nối bị đứt trước khi phản hồi đến producer:

~~~text
Producer                 Broker
   |                        |
   |------ send M --------->|
   |                        | persist + commit M
   |<---- response ---------X  network lost
   |
   | timeout / connection failure
~~~

Producer chỉ biết **không nhận được kết quả xác nhận**. Nó không thể kết luận message chưa được commit. Nếu retry bằng một ID mới, broker có thể lưu cả hai message.

Do đó, mỗi business event cần một `eventId` ổn định. Nếu producer retry, nó gửi lại **cùng eventId**. Consumer lưu eventId với business effect bằng unique constraint hoặc inbox table.

### 3.2. Consumer crash trước và sau commit

| Thời điểm crash | Trạng thái | Hành vi kỳ vọng |
|---|---|---|
| Trước khi receive | Message còn trong queue/subscription | Consumer khác hoặc consumer sau restart nhận |
| Sau receive, trước JMS commit/ACK | Delivery chưa được xác nhận | Broker redeliver khi session/connection được phục hồi |
| Sau DB commit, trước JMS commit | Business effect đã tồn tại, JMS delivery chưa ACK | Có thể redeliver; inbox/idempotency chặn side effect lặp |
| Sau JMS commit | Broker đã nhận ACK/commit | Message không được giao lại trong điều kiện bình thường |
| Trong lúc broker failover | Kết quả có thể chưa rõ ở client | Đối chiếu message ID/event ID và trạng thái DB, chấp nhận duplicate |

Với consumer transacted, JMS transaction chỉ điều khiển thao tác JMS của session. Nó **không tự gộp** transaction database vào transaction broker. Để chống crash giữa hai commit, dùng inbox/idempotency hoặc transactional integration pattern phù hợp.

### 3.3. Persistent và non-persistent

- `DeliveryMode.PERSISTENT` yêu cầu provider lưu message theo durability contract; kết quả thực tế còn phụ thuộc broker store và HA policy.
- `DeliveryMode.NON_PERSISTENT` có thể mất khi broker/process failure theo semantics và cấu hình provider.
- Durable topic subscription là một khía cạnh khác: nó quyết định subscription có giữ message phù hợp khi subscriber offline hay không.
- **Persistent message gửi vào non-durable subscription không tự biến subscription thành durable.**

Phải test riêng hai chiều: message persistence và subscription durability.

## 4. Khôi phục topic subscription: identity phải ổn định

### 4.1. Non-durable subscription

Non-durable subscriber thường chỉ nhận event khi subscription đang hoạt động. Nếu subscriber offline lúc publish, nó không có backlog durable để lấy lại khi reconnect. Dùng loại này khi mất event trong khoảng offline là chấp nhận được hoặc dữ liệu có thể được tái tạo từ nguồn khác.

### 4.2. Durable subscription

Durable subscription được định danh bằng thông tin ổn định theo JMS/provider. Với **unshared durable subscription** trong Jakarta JMS:

- Có `clientID` ổn định cho logical subscriber.
- Có `subscriptionName` ổn định.
- Selector và cấu hình subscription cần nhất quán khi reconnect.
- Đóng consumer/context không đồng nghĩa xóa durable subscription.
- Chỉ `unsubscribe(subscriptionName)` khi chủ đích retire subscription và đã xử lý backlog.

Trong Artemis, durable subscription được triển khai qua queue gắn với topic/address. Khi subscriber offline, message phù hợp có thể được giữ trong queue subscription theo persistence/expiry policy. Broker phải có routing type MULTICAST cho topic.

### 4.3. Selector là một phần của subscription contract

Giả sử subscription `billing-v1` có selector:

~~~sql
eventType = 'invoice.created'
~~~

Nếu service reconnect bằng cùng `clientID` và `subscriptionName` nhưng selector khác, provider có thể từ chối việc tạo lại subscription do metadata không tương thích. Không nên âm thầm đổi selector trên một durable subscription đang có backlog.

Nếu muốn thay đổi tập message nhận:

1. Xác định backlog của subscription cũ.
2. Quyết định drain, replay hoặc retire backlog.
3. Tạo version subscription mới có tên rõ ràng, ví dụ `billing-v2`.
4. Chạy song song/cutover theo kế hoạch để không mất event.
5. Xóa subscription cũ chỉ sau khi đối soát xong.

### 4.4. Client ID và subscription name không phải queue name tùy ý

Không đổi `clientID` theo pod ID nếu muốn phục hồi cùng một durable subscription. Nếu mỗi lần deploy tạo client ID mới, broker có thể coi đó là subscriber mới và để lại durable subscription cũ. Kết quả là backlog bị giữ ở nhiều queue, tiêu tốn storage và khó vận hành.

Với nhiều instance cần chia tải, cân nhắc **shared durable subscription** theo JMS 2.0/provider semantics. Không để nhiều unshared durable consumers cùng dùng một cặp clientID/subscriptionName. Cần test ordering, concurrency và consumer ownership trước khi scale.

## 5. Cấu hình Artemis lab: address multicast và client failover

### 5.1. Topic address trên broker

Trong phần `<addresses>` của `broker.xml` Artemis, bảo đảm topic có routing type MULTICAST:

~~~xml
<address name="orders.events">
    <multicast/>
</address>
~~~

Durable subscription được tạo khi JMS client gọi `createDurableConsumer` với client ID và subscription name. Broker cần security permission phù hợp để tạo/consume subscription queue theo chính sách; không cấp quyền admin rộng chỉ để test.

Đối với test recovery, không tự khai báo một queue tên đoán theo subscription nếu broker đã tự tạo queue durable tương ứng. Kiểm tra queue/subscription qua management API của đúng phiên bản Artemis.

### 5.2. Client URL với Artemis Core HA

Ví dụ URI cho **Artemis Core client**:

~~~text
tcp://mq-primary.internal:61616?ha=true&reconnectAttempts=-1&retryInterval=1000&retryIntervalMultiplier=2.0&maxRetryInterval=30000
~~~

Ý nghĩa:

- `ha=true` bật hành vi HA của Core client để client sử dụng topology/backup information mà broker cung cấp.
- `reconnectAttempts=-1` yêu cầu tiếp tục thử kết nối lại không giới hạn theo policy client.
- `retryInterval` là khoảng retry ban đầu.
- `retryIntervalMultiplier` tăng khoảng retry qua các lần thất bại.
- `maxRetryInterval` giới hạn khoảng retry tối đa.

**URI này không tự tạo HA topology.** Phía broker phải được cấu hình thành một HA pair/cluster phù hợp (replication hoặc shared store theo kiến trúc), và client phải nhận được thông tin backup/topology hợp lệ. Một broker đơn lẻ với `ha=true` vẫn là một broker đơn lẻ. Nếu dùng static/discovery connectors, cấu hình đúng topology của release và kiểm thử client thực tế.

Đừng dùng reconnect vô hạn như thay thế alert/RTO. Client có thể tiếp tục thử nhưng ứng dụng vẫn không có năng lực xử lý trong thời gian broker không sẵn sàng.

### 5.3. HA server-side: kiểm tra cấu hình thực thay vì suy từ client URL

Artemis hỗ trợ các chính sách HA như **replication** và **shared store**. Việc chọn loại nào phụ thuộc storage, latency, failure domain và topology. Bài test cần xác nhận tối thiểu:

- Primary và backup thuộc cùng HA group/cluster theo cấu hình được hỗ trợ.
- Backup thực sự đồng bộ/đọc được store theo chế độ đã chọn.
- Network path và authentication giữa các broker hoạt động.
- Client được thông báo backup endpoint/topology.
- Sau khi primary mất, backup được promote theo policy; không có hai active server cùng nhận ghi ngoài thiết kế.
- Persistent messages và durable subscription queues tồn tại sau failover.

Không lấy một XML fragment generic làm bằng chứng HA đã sẵn sàng. Dùng **broker configuration validation, management topology, startup logs và test failover** trên đúng Artemis release.

### 5.4. Security cho client và backup

Client phải xác thực tới node đích sau failover. Nếu TLS certificate chỉ hợp lệ cho hostname primary nhưng backup có hostname khác, failover có thể thất bại ở hostname verification. Kiểm tra SAN/trust chain cho **mọi endpoint có thể được quảng bá**.

Role cần cho durable subscription có thể bao gồm consume và quyền tạo durable queue/address tùy provisioning policy. Provision destination trước bằng broker admin nếu muốn application user chỉ có quyền consume.

## 6. ActiveMQ Classic: failover transport khác Artemis Core HA

ActiveMQ Classic client thường dùng **Failover Transport**:

~~~text
failover:(tcp://classic-a.internal:61616,tcp://classic-b.internal:61616)?initialReconnectDelay=100&maxReconnectAttempts=-1&useExponentialBackOff=true
~~~

- `failover:(...)` liệt kê các transport endpoint client có thể thử.
- `initialReconnectDelay` xác định thời gian đợi ban đầu trước retry.
- `maxReconnectAttempts=-1` yêu cầu retry không giới hạn.
- `useExponentialBackOff=true` bật tăng khoảng retry theo policy.

Đây là **client transport failover**, không tự đồng bộ message store giữa hai broker độc lập. Các endpoint phải thuộc một topology server-side hợp lệ, ví dụ master/slave hoặc cơ chế HA/network phù hợp với release Classic. Nếu chỉ liệt kê hai broker độc lập, client có thể reconnect sang broker thứ hai nhưng message state không tự xuất hiện ở đó.

### 6.1. Classic durable topic subscription

Classic cũng sử dụng client ID và durable subscription name trong JMS. Quy tắc vận hành tương tự:

- Dùng cùng client ID và subscription name để reconnect đúng durable subscription.
- Không unsubscribe khi chỉ muốn đóng kết nối tạm thời.
- Kiểm tra durable subscriber list và pending queue/backlog bằng management phù hợp.
- Nếu dùng nhiều broker qua Network of Brokers, phân biệt **network demand forwarding** với broker HA; durable subscription forwarding cần test riêng theo cấu hình network connector.

Classic client truyền thống có thể dựa trên `javax.jms`; Spring Boot 3 yêu cầu bộ client tương thích `jakarta.jms`. Đừng trộn dependency/namespace trong cùng lab.

## 7. Java/Jakarta JMS lab: publish, durable subscribe, crash và recover

Lab này dùng Artemis **2.40.0**, Java 17 và Jakarta JMS 3.1. Nó kiểm tra **subscription recovery và transaction redelivery**, không thay thế test HA server-side. Broker cần topic `orders.events` kiểu MULTICAST và một user lab có quyền publish/consume durable subscription.

### 7.1. Cấu trúc dự án

~~~text
jms-recovery-lab/
├── pom.xml
└── src/main/java/lab/RecoveryLab.java
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab</groupId>
    <artifactId>jms-recovery-lab</artifactId>
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

### 7.2. Chương trình kiểm thử

File `src/main/java/lab/RecoveryLab.java`:

~~~java
package lab;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class RecoveryLab {
    private static final String TOPIC = "orders.events";
    private static final String CLIENT_ID = "billing-service";
    private static final String SUBSCRIPTION = "billing-v1";
    private static final String SELECTOR =
            "eventType = 'order.confirmed'";

    private RecoveryLab() {}

    public static void main(String[] args) {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "init | publish <eventId> | consume | crash-before-commit | unsubscribe");
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = required("BROKER_USER");
        String password = required("BROKER_PASSWORD");

        try (ActiveMQConnectionFactory factory =
                     new ActiveMQConnectionFactory(url)) {
            switch (args[0]) {
                case "init" -> initialize(factory, user, password);
                case "publish" -> {
                    if (args.length != 2) {
                        throw new IllegalArgumentException(
                                "publish <stable-eventId>");
                    }
                    publish(factory, user, password, args[1]);
                }
                case "consume" ->
                        consumeOne(factory, user, password, false);
                case "crash-before-commit" ->
                        consumeOne(factory, user, password, true);
                case "unsubscribe" ->
                        unsubscribe(factory, user, password);
                default -> throw new IllegalArgumentException(
                        "Unknown mode: " + args[0]);
            }
        }
    }

    private static void initialize(
            ConnectionFactory factory, String user, String password) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            context.setClientID(CLIENT_ID);
            Topic topic = context.createTopic(TOPIC);

            try (JMSConsumer ignored = context.createDurableConsumer(
                    topic, SUBSCRIPTION, SELECTOR, false)) {
                System.out.println("DURABLE_SUBSCRIPTION_READY"
                        + " clientId=" + CLIENT_ID
                        + " name=" + SUBSCRIPTION);
            }
        }
    }

    private static void publish(
            ConnectionFactory factory, String user, String password,
            String eventId) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Topic topic = context.createTopic(TOPIC);
            TextMessage message =
                    context.createTextMessage("OrderConfirmed");
            message.setStringProperty("eventId", eventId);
            message.setStringProperty(
                    "eventType", "order.confirmed");

            context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(topic, message);

            context.commit();
            System.out.println("PRODUCER_COMMITTED eventId=" + eventId);
        }
    }

    private static void consumeOne(
            ConnectionFactory factory, String user, String password,
            boolean crashBeforeCommit) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            context.setClientID(CLIENT_ID);
            Topic topic = context.createTopic(TOPIC);

            try (JMSConsumer consumer = context.createDurableConsumer(
                    topic, SUBSCRIPTION, SELECTOR, false)) {
                Message message = consumer.receive(15_000);
                if (message == null) {
                    System.out.println("NO_MESSAGE");
                    return;
                }

                String eventId = message.getStringProperty("eventId");
                System.out.println("RECEIVED eventId=" + eventId
                        + " deliveryCount="
                        + (message.propertyExists("JMSXDeliveryCount")
                           ? message.getIntProperty("JMSXDeliveryCount")
                           : 1));

                if (crashBeforeCommit) {
                    System.out.println("CRASHING_BEFORE_JMS_COMMIT");
                    // Chỉ dùng trong broker lab: process dừng đột ngột,
                    // không gọi context.commit() hoặc graceful close.
                    Runtime.getRuntime().halt(23);
                }

                // Demo ACK boundary. Production cần DB inbox/idempotency
                // và commit DB trước khi commit JMS session.
                context.commit();
                System.out.println("JMS_COMMITTED eventId=" + eventId);
            }
        }
    }

    private static void unsubscribe(
            ConnectionFactory factory, String user, String password) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            context.setClientID(CLIENT_ID);
            context.unsubscribe(SUBSCRIPTION);
            System.out.println("DURABLE_SUBSCRIPTION_REMOVED"
                    + " clientId=" + CLIENT_ID
                    + " name=" + SUBSCRIPTION);
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + key);
        }
        return value;
    }
}
~~~

### 7.3. Ý nghĩa từng mode

| Mode | Hành động | Điều cần chứng minh |
|---|---|---|
| `init` | Tạo durable consumer rồi đóng | Subscription identity được tạo và còn tồn tại |
| `publish event-1` | Publish persistent message và JMS commit | Event được lưu ở broker theo persistence contract |
| `consume` | Nhận một event rồi commit | Subscription phục hồi và consumer ACK/commit |
| `crash-before-commit` | Nhận message rồi dừng process đột ngột | Message chưa commit được redeliver |
| `unsubscribe` | Xóa durable subscription | Chỉ dùng khi chủ đích retire subscription |

**Điều kiện quan trọng:**

- Chạy `init` **trước** khi subscriber offline; durable subscription chưa tồn tại thì broker không có subscription backlog để phục hồi.
- Chạy `publish` trong lúc subscriber offline để chứng minh message được giữ.
- Dùng cùng `CLIENT_ID`, `SUBSCRIPTION` và `SELECTOR` khi reconnect.
- `unsubscribe` xóa durable subscription và có thể xóa backlog của nó; không chạy để “đóng consumer bình thường”.
- `Runtime.halt` là phép thử crash process ở lab. Nó không mô phỏng power loss của máy chủ hoặc mất disk; broker cần phát hiện socket đóng trước khi redeliver.
- Code không ghi DB; log `JMS_COMMITTED` chỉ chứng minh transaction JMS đã commit, không phải business effect bên ngoài.
- Nếu dùng `JMSXDeliveryCount`, kiểm tra property được provider hỗ trợ; giá trị có thể bắt đầu từ 1 và tăng khi redelivery.

### 7.4. Chạy bài thử durable recovery

PowerShell:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "lab"
$env:BROKER_PASSWORD = "LAB_ONLY_PASSWORD"

mvn -q -DskipTests package

# 1. Tạo durable subscription trước.
mvn -q exec:java "-Dexec.mainClass=lab.RecoveryLab" "-Dexec.args=init"

# 2. Subscriber offline: publish hai event persistent.
mvn -q exec:java "-Dexec.mainClass=lab.RecoveryLab" "-Dexec.args=publish evt-1001"
mvn -q exec:java "-Dexec.mainClass=lab.RecoveryLab" "-Dexec.args=publish evt-1002"

# 3. Reconnect cùng clientID + subscription name.
mvn -q exec:java "-Dexec.mainClass=lab.RecoveryLab" "-Dexec.args=consume"
mvn -q exec:java "-Dexec.mainClass=lab.RecoveryLab" "-Dexec.args=consume"
~~~

Kỳ vọng subscriber nhận được các event đã publish khi offline. Nếu một event không xuất hiện, kiểm tra subscription queue, selector, expiry, message persistence và broker store trước khi kết luận lỗi reconnect.

### 7.5. Chạy bài thử crash trước commit

1. Tạo và publish event mới, ví dụ `evt-2001`.
2. Chạy consumer crash:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.RecoveryLab" "-Dexec.args=crash-before-commit"
~~~

Process kết thúc với exit code 23 sau khi in `RECEIVED` nhưng trước `JMS_COMMITTED`.
3. Chờ broker phát hiện connection bị đóng và thu hồi delivery chưa commit.
4. Chạy lại `consume` với cùng clientID/subscription.
5. Xác nhận event được giao lại và commit thành công.

Không giả định redelivery xảy ra ngay lập tức; detection/recovery có độ trễ. Nếu broker chưa thu hồi session, kiểm tra connection state và consumer count. Đừng xóa subscription để “làm sạch” trước khi xác minh message.

## 8. Test network interruption và reconnect

### 8.1. Các mức gián đoạn khác nhau

| Mô phỏng | Cách tạo trong lab | Dấu hiệu |
|---|---|---|
| TCP reset | Đóng socket/proxy giữa client và broker | Client nhận connection failure sớm |
| Packet drop | Firewall drop traffic trong thời gian ngắn | Timeout/heartbeat failure, retransmit |
| Latency tăng | Network emulator thêm delay | ACK/receive latency tăng, reconnect có thể chưa xảy ra |
| One-way partition | Chặn một chiều nhưng giữ chiều kia | Heartbeat/response bất thường, timeout khó đoán |
| DNS đổi endpoint | Chuyển service DNS sang node khác trong lab | Client reconnect theo resolver/cache policy |
| TLS certificate invalid | Thay cert test sai SAN/CA | TLS handshake fail, retry không sửa được cert |

Không coi mọi timeout là broker chết. Broker có thể đang hoạt động bình thường nhưng đường trả response bị chặn.

### 8.2. Kịch bản kiểm thử có thể lặp

1. Khởi động broker lab và subscriber.
2. Ghi timestamp UTC, connection count, consumer count, queue depth và event ID cuối đã commit.
3. Publish một luồng có sequence/eventId tăng dần.
4. Cắt kết nối client trong 10–30 giây bằng proxy hoặc network namespace riêng.
5. Giữ producer/consumer chạy theo policy retry đã cấu hình.
6. Khôi phục network.
7. Quan sát client reconnect, session/consumer được tạo lại và queue backlog được drain.
8. Đối soát event ID: event nào đã commit, event nào redeliver, có gap hoặc duplicate business effect không.
9. Lặp lại với latency, packet loss và asymmetric partition.

**Không chạy lệnh firewall hoặc network shaping trên host dùng chung/production.** Tạo một network namespace, container network hoặc proxy test riêng để giới hạn blast radius.

### 8.3. Kỳ vọng với client reconnect

Sau khi transport phục hồi, ứng dụng có thể cần tạo lại:

- JMS connection/session/context.
- Producer/consumer.
- Listener container hoặc consumer subscription.
- Transaction chưa commit và business retry state.

Một số client/provider có thể tự phục hồi connection và session theo HA/reconnect policy, nhưng ứng dụng vẫn phải xử lý callback lỗi và lifecycle. Không giữ reference tới một JMSContext/consumer đã bị đóng hoặc invalid rồi tiếp tục dùng như chưa có lỗi.

Đối với Spring JMS, kiểm tra listener container có recovery/reconnect behavior phù hợp, consumer count trở lại và readiness/health không báo healthy khi listener vẫn mất kết nối.

## 9. Test broker restart: graceful và abrupt crash

### 9.1. Graceful restart

Mục tiêu: broker có thời gian đóng connection và shutdown store theo quy trình.

1. Publish persistent messages và commit.
2. Xác nhận queue/subscription backlog có giá trị đã biết.
3. Dừng broker theo service manager hoặc CLI được hỗ trợ.
4. Xác nhận process dừng hoàn toàn, store đóng.
5. Khởi động lại cùng instance/store.
6. Chờ broker báo sẵn sàng, client reconnect.
7. Consume và đối chiếu event IDs, counts, order và durable subscription.

PASS khi persistent messages chưa ACK vẫn có thể được phục hồi theo semantics, durable subscription vẫn tồn tại, và consumer tiếp tục xử lý.

### 9.2. Abrupt process crash

Abrupt crash khác graceful restart:

- Process dừng không chạy shutdown hook.
- Broker phải recover journal/store khi khởi động lại.
- Connection phía client có thể chỉ phát hiện sau failure check/timeout.
- Message đang dispatch nhưng chưa ACK có thể redeliver.
- Thời gian recovery phụ thuộc kích thước store, paging, journal và cấu hình.

Chỉ thực hiện trên broker lab. Dùng process/container kill trong môi trường được cô lập; **không** xóa journal/page/large-message files và không tái sử dụng một data directory khi process cũ vẫn chạy.

### 9.3. Kiểm tra persistence bằng event ID

Tạo tập message có ID liên tiếp:

~~~text
evt-000001
evt-000002
...
evt-001000
~~~

Sau restart, consumer ghi event ID vào kết quả test. So sánh:

- Tổng số event producer đã nhận commit.
- Tổng số event consumer đã commit.
- Tập event thiếu.
- Tập event trùng.
- Message còn trong queue/subscription.
- DLQ/expiry/scheduled queue có event bị chuyển sang không.

Đừng chỉ so queue depth trước/sau; queue depth có thể giảm vì consumer đã ACK hoặc tăng vì redelivery, nhưng không chứng minh event identity đầy đủ.

## 10. Test HA failover: reconnect sang backup và xác minh state

### 10.1. Điều kiện để gọi là failover

Một client URL có `ha=true` hoặc một Classic `failover:(...)` không tự tạo server HA. Trước khi test, phải có:

- Primary/backup hoặc HA topology đúng phiên bản.
- Shared store hoặc replication được cấu hình đúng.
- Backup đã đồng bộ đủ state theo chính sách.
- Client biết topology/backup endpoints.
- Network/security giữa client, primary, backup và cluster nodes hoạt động.
- Fencing/activation bảo đảm không có hai active writers trái thiết kế.

### 10.2. Artemis Core client

Client URL lab:

~~~text
tcp://mq-primary:61616?ha=true&reconnectAttempts=-1&retryInterval=1000&retryIntervalMultiplier=2.0&maxRetryInterval=30000
~~~

Cần xác minh broker cung cấp topology và backup connector hợp lệ. Nếu client chỉ biết primary, không có topology update/backup endpoint, `ha=true` không thể tự đoán địa chỉ backup.

Kịch bản:

1. Publish persistent message, commit trên primary.
2. Để một consumer transacted nhận message nhưng chưa commit.
3. Dừng primary theo failover test plan.
4. Quan sát backup activation và client topology update.
5. Chờ client reconnect; kiểm tra producer/consumer session được khôi phục.
6. Đối chiếu persistent messages, durable subscription và redelivery.
7. Đảm bảo không có hai primary cùng nhận writes.

### 10.3. Classic failover transport

URI lab:

~~~text
failover:(tcp://classic-a:61616,tcp://classic-b:61616)?initialReconnectDelay=100&maxReconnectAttempts=-1&useExponentialBackOff=true
~~~

Để test có ý nghĩa, hai endpoint phải thuộc topology Classic HA/replication được hỗ trợ. Nếu `classic-b` là broker độc lập, client có thể reconnect thành công nhưng không thấy message đã lưu ở A. **Transport failover không phải data replication.**

### 10.4. Các kết quả cần phân biệt

| Kết quả | Kết luận |
|---|---|
| Client reconnect tới backup, message state còn | Failover và store/topology có vẻ đúng; tiếp tục kiểm tra business |
| Client reconnect nhưng queue rỗng | Có thể sai store/topology, message đã ACK/expire/route khác; cần đối soát ID |
| Client không tìm thấy backup | Topology advertisement, connector URI, DNS/network hoặc HA config |
| Hai broker cùng active | Lỗi nghiêm trọng về fencing/split brain; dừng test và điều tra |
| Consumer nhận lại event chưa commit | Redelivery hợp lệ; cần idempotent handler |
| Producer retry làm duplicate | Kết quả có thể xảy ra khi send outcome không xác định; cần eventId/dedup |
| Client connected nhưng listener chưa nhận | Connection chưa đồng nghĩa consumer được tái tạo hoặc subscription/ACL hợp lệ |

## 11. Kiểm thử idempotency và duplicate sau phục hồi

### 11.1. Inbox table trong cùng transaction với business update

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Pseudo-code consumer:

~~~java
// Trong một DB transaction duy nhất:
boolean firstDelivery = inboxRepository.insertIfAbsent(eventId);

if (firstDelivery) {
    orderService.apply(event);
}
// Commit DB transaction trước khi JMS session commit.
jmsContext.commit();
~~~

`insertIfAbsent` cần được thực hiện bằng thao tác atomic dựa trên unique constraint, ví dụ:

~~~sql
INSERT INTO processed_events(event_id)
VALUES (?)
ON CONFLICT (event_id) DO NOTHING;
~~~

Nếu insert ảnh hưởng 1 row, đây là event mới và business update được thực hiện **trong cùng transaction DB**. Nếu 0 row, event đã được xử lý và không lặp side effect. Sau DB commit, mới commit JMS session.

Nếu DB commit thành công nhưng process chết trước JMS commit, message redeliver; inbox unique constraint làm lần thứ hai không lặp side effect.

### 11.2. Producer retry cũng phải ổn định identity

Một producer không nên tạo event ID mới mỗi lần retry. Nếu event gốc được lưu trong transactional outbox, event ID được tạo một lần và relay gửi lại cùng ID tới broker. Khi producer timeout, outbox giữ trạng thái chưa xác nhận và retry có thể tạo duplicate transport, nhưng consumer dedup bảo vệ business effect.

### 11.3. Broker duplicate detection không thay thế inbox

Artemis duplicate detection có thể hỗ trợ loại bỏ một số duplicate ở broker dựa trên duplicate ID/cache. Tuy nhiên:

- Cache có giới hạn và phạm vi.
- Replay từ nguồn khác hoặc DLQ có thể bypass đường duplicate ban đầu.
- Crash giữa DB commit và JMS ACK vẫn có thể gây redelivery.
- Duplicate detection không hiểu side effect database.

Vì vậy bài test phải có **eventId + DB unique constraint** ngay cả khi broker đã bật duplicate detection.

## 12. Ma trận kiểm thử end-to-end

| ID | Sự cố | Tiền điều kiện | PASS khi |
|---|---|---|---|
| NET-01 | Client mất TCP 15 giây | Reconnect policy bật | Client reconnect, consumer được tái tạo |
| NET-02 | Packet loss/RTT cao | Network lab riêng | Timeout/latency đo được, không mất event ngoài RPO |
| NET-03 | Asymmetric partition | Proxy/firewall test | Outcome được phân loại; duplicate không gây side effect trùng |
| BRK-01 | Graceful broker restart | Persistent backlog | Store/subscription phục hồi, client reconnect |
| BRK-02 | Broker process crash | Lab store có dữ liệu | Journal recovery, message chưa ACK redeliver |
| HA-01 | Primary failover | HA pair đã đồng bộ | Backup active, client failover, persistent state còn |
| HA-02 | Backup không reachable | HA lab | Alert và RTO failure được ghi, không báo PASS giả |
| HA-03 | Split-brain guard | Fencing/test topology | Không có hai active writers |
| SUB-01 | Subscriber offline sau khi durable sub tạo | Durable identity ổn định | Message phù hợp được giữ |
| SUB-02 | Reconnect cùng clientID/name | Selector không đổi | Backlog được dispatch |
| SUB-03 | Thay selector cùng subscription name | Có backlog | Hành vi conflict được phát hiện, không xóa backlog âm thầm |
| SUB-04 | Unsubscribe có chủ đích | Backlog đã đối soát | Subscription được xóa đúng, audit ghi lại |
| ACK-01 | Consumer crash trước JMS commit | Transacted session | Message redeliver |
| ACK-02 | Crash sau DB commit trước JMS commit | Inbox/unique constraint | Redelivery không lặp business effect |
| ACK-03 | Producer mất response sau commit | Stable eventId | Retry không tạo duplicate side effect |
| CLS-01 | Classic failover URI | Classic HA topology | Client reconnect tới broker stateful đúng |
| CLS-02 | Classic reconnect sang broker độc lập | Không replication | Test chứng minh state không tự đồng bộ |

## 13. Thiết kế test tự động và tránh kết quả giả

### 13.1. Mỗi test cần marker rõ ràng

Gắn `eventId` và `testRunId` vào message properties. Log các mốc:

~~~text
PUBLISHED eventId=evt-1001 runId=run-42
BROKER_RECONNECTED node=backup-b
SUBSCRIPTION_READY clientId=billing-service name=billing-v1
RECEIVED eventId=evt-1001 deliveryCount=2
DB_COMMITTED eventId=evt-1001 firstDelivery=false
JMS_COMMITTED eventId=evt-1001
~~~

Các dòng trên là **log schema minh họa của test harness**, không phải log mặc định của Artemis. Ghi timestamp UTC, broker node và process ID để ghép sự kiện.

### 13.2. Không dùng sleep làm điều kiện phục hồi duy nhất

Thay vì đợi cố định 30 giây rồi khẳng định broker đã failover, poll các điều kiện có timeout:

- Broker backup báo active qua management/health endpoint.
- Client connection/consumer count trở lại.
- Durable subscription queue có backlog mong đợi.
- Event ID đã nhận được.
- Business DB có đúng một row cho event ID.

Nếu hết deadline mà chưa đạt, test FAIL kèm snapshot diagnostics. Không kéo dài timeout vô hạn để làm test xanh.

### 13.3. Dọn test state an toàn

- Dùng queue/topic/subscription riêng cho test run.
- Không xóa durable subscription trước khi đọc backlog và đối soát event IDs.
- Chỉ gọi `unsubscribe` khi đã xác nhận test không còn cần backlog.
- Không xóa journal/page files bằng filesystem command.
- Đặt TTL hoặc cleanup policy chỉ cho dữ liệu test đã được định danh; tránh dùng TTL làm cách che message chưa xử lý.
- Ghi lại broker config revision để tái tạo lỗi.

## 14. Chỉ số quan sát trong lúc recovery

| Chỉ số | Trước lỗi | Trong lỗi | Sau phục hồi |
|---|---|---|---|
| Client connection state | Connected | Failed/retrying | Connected tới node đúng |
| Broker node role | Primary/active | Backup activating | Một active theo topology |
| Queue message count | Baseline | Backlog tăng/giữ | Giảm theo consumer throughput |
| Delivering count | Bình thường | Có thể pending/recover | Delivery/ACK ổn định |
| Durable subscription backlog | Theo tải | Tăng khi offline | Drain sau reconnect |
| Redelivery count | Baseline | Có thể tăng | Trở về mức ổn định |
| DLQ count | Baseline | Có thể tăng do poison | Không tăng bất thường |
| Disk/journal/page | Có headroom | Có thể tăng | Ổn định/cleanup đúng |
| Reconnect attempts | 0/thấp | Tăng | Ngừng tăng sau recovery |
| Business inbox duplicates | 0 | Có thể thấy redelivery | Một business effect/event ID |

Đừng chỉ giám sát `connection count`. Client có thể kết nối được nhưng consumer chưa đăng ký đúng subscription, selector sai hoặc authorization bị từ chối.

## 15. Runbook khi subscription không phục hồi

1. Xác nhận broker hiện active và client URL/topology đúng.
2. Kiểm tra `clientID` và `subscriptionName` của runtime có khớp identity cũ không.
3. Xác nhận durable subscription vẫn tồn tại; đừng tạo identity mới để né lỗi.
4. Kiểm tra selector có khớp metadata subscription đã tạo không.
5. Kiểm tra destination là topic/MULTICAST, queue subscription có backlog không.
6. Kiểm tra auth/ACL: consume và quyền tạo durable subscription/queue nếu cần.
7. Kiểm tra message expiry, DLQ, purge hoặc administrative unsubscribe.
8. Kiểm tra client đã tạo lại consumer sau reconnect chưa.
9. Đối chiếu event ID từ producer, subscription queue, consumer log và DB inbox.
10. Chỉ retire/recreate subscription theo quy trình drain/replay và change approval.

Nếu subscriber reconnect bằng clientID mới, broker có thể tạo durable subscription khác; subscription cũ vẫn giữ backlog. Không xóa queue cũ cho đến khi xác định được owner và quyết định xử lý event.

## 16. Các anti-pattern trong kiểm thử recovery

- **Chỉ test graceful restart:** bỏ qua journal recovery và abrupt connection loss.
- **Chỉ test TCP reconnect:** không chứng minh HA backup có state.
- **Dùng non-persistent message để kiểm tra persistence:** sai mục tiêu kiểm thử.
- **Không tạo durable subscription trước khi publish offline:** không có subscription backlog để phục hồi.
- **Đổi clientID mỗi lần deploy:** để lại durable subscriptions cũ.
- **Unsubscribe để “reset test”:** có thể xóa backlog và che lỗi mất message.
- **Chỉ nhìn queue depth:** không đối soát event ID và business commit.
- **Retry producer bằng ID mới:** tạo duplicate nghiệp vụ.
- **ACK trước DB commit:** có thể mất business effect nếu DB lỗi sau ACK.
- **Gọi failover URI là HA:** client transport không đồng bộ store giữa broker độc lập.
- **Dùng reconnect vô hạn như SLA:** retry mãi không có nghĩa recovery đúng deadline.
- **Dùng một broker local để khẳng định HA:** không có backup node thì chưa test failover.
- **Chỉ test subscriber active:** bỏ qua offline durable backlog và selector identity.

## 17. Checklist nghiệm thu

- [ ] Đã định nghĩa RPO, RTO, duplicate tolerance và subscription retention.
- [ ] Phân biệt network interruption, graceful restart, abrupt crash và HA failover.
- [ ] Persistent message được publish trong transacted session và commit.
- [ ] Consumer transacted được thử crash trước JMS commit và redelivery.
- [ ] DB inbox/idempotency được kiểm tra ở cửa sổ DB commit trước JMS ACK.
- [ ] Durable subscription được tạo trước khi subscriber offline.
- [ ] Reconnect dùng cùng clientID, subscription name và selector.
- [ ] Unsubscribe chỉ chạy khi retire subscription có chủ đích.
- [ ] Artemis HA topology/backup state đã được kiểm tra; `ha=true` không bị coi là tự tạo HA.
- [ ] Classic failover transport được phân biệt với replication/server HA.
- [ ] TLS certificate/SAN/ACL đúng cho mọi node có thể failover.
- [ ] Test full partition, packet loss, latency và asymmetric failure trong network lab.
- [ ] Đối soát event IDs, message counts, redelivery, DLQ và business effects.
- [ ] Có metrics reconnect, consumer count, subscription backlog, oldest age, disk và node role.
- [ ] Test có deadline/polling điều kiện, không sleep cố định làm bằng chứng.
- [ ] Cleanup không xóa journal, page hoặc durable backlog chưa đối soát.

## 18. Kết luận

**Mất kết nối, restart, failover và subscription recovery là bốn bài test liên quan nhưng không thay thế nhau.** Network reconnect chỉ khôi phục đường truyền; broker restart còn phải phục hồi store; HA failover cần topology/backup state thực; durable subscription cần giữ đúng identity để nhận lại backlog khi subscriber online.

Một bài test đạt phải theo dõi từ **producer commit → broker persistence → consumer delivery → business commit → JMS ACK**, đối chiếu event ID sau mọi failure và chấp nhận redelivery/duplicate ở những cửa sổ không chắc chắn. Artemis Core HA và Classic Failover Transport có cấu hình khác nhau, và cả hai đều cần topology server-side đúng. Kết hợp **persistent messages, durable subscription, transaction, idempotency, failure injection và observability** mới chứng minh hệ thống messaging phục hồi đúng theo RPO/RTO đã cam kết.
