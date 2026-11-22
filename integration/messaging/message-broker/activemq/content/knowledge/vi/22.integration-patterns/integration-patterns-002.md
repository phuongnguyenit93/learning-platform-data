# Phát sự kiện đến nhiều hệ thống với Topic, Virtual Topic hoặc multicast

> **Chương:** Mẫu tích hợp  
> **Phạm vi:** Java/JMS trên **ActiveMQ Classic** và **Apache Artemis**; phân phối cùng một sự kiện tới nhiều hệ thống độc lập bằng **JMS Topic**, **Virtual Topic của Classic** hoặc **multicast address của Artemis**. Trọng tâm là ranh giới fan-out, giữ dữ liệu khi hệ thống nhận offline, scaling theo nhóm consumer và cách kiểm chứng; không đi sâu lại vào ACK, transaction, retry hay DLQ nói chung. Ví dụ dùng Java 17, `jakarta.jms`, Classic 6.x và Artemis 2.57.x.

## 1. Bất biến fan-out: mỗi hệ thống một bản, mỗi replica không phải một bản

Đơn hàng `order-981` được xác nhận. Ba hệ thống cần biết sự kiện `OrderConfirmed`:

- **Billing** lập chứng từ.
- **Inventory** cập nhật tồn kho.
- **Analytics** cập nhật báo cáo.

Yêu cầu không phải chia ba message cho ba hệ thống theo kiểu round-robin. **Mỗi hệ thống phải có cơ hội xử lý một bản của cùng sự kiện**, đồng thời hai instance Billing chạy song song **không được mặc định thực hiện cùng một nghiệp vụ hai lần**.

```text
                                  Order service
                            publish OrderConfirmed
                                       |
                                       v
                           Topic / multicast address
                         /             |             \
                        v              v              v
                 Billing copy    Inventory copy   Analytics copy
                        |              |              |
                   Billing queue  Inventory queue Analytics queue
                     /      \
                    v        v
                Billing-1  Billing-2
                 (competing consumers cùng 1 queue)
```

Có **hai cấp độ độc lập**:

1. **Giữa các hệ thống:** phải có *fan-out* tới ba subscription/queue riêng. Billing chậm không có nghĩa Analytics mất bản của mình.
2. **Trong một hệ thống:** các replica cùng consume một subscription/queue để chia việc; một message chỉ được broker giao cho một worker tại một thời điểm trong tình huống bình thường. Redelivery sau lỗi vẫn có thể làm xử lý lặp.

| Topology | Một event gửi | Billing-1 và Billing-2 | Hệ quả |
|---|---|---|---|
| Một queue chung cho cả ba hệ thống | Một message vào queue | Cùng cạnh tranh với Inventory/Analytics | **Sai:** thường chỉ một hệ thống nhận |
| Ba Topic subscriber độc lập | Một bản cho từng subscriber đang tồn tại | Nếu tạo hai subscription riêng sẽ có **hai bản Billing** | Đúng fan-out nhưng phải thiết kế subscription identity |
| Một queue cho mỗi nhóm | Một bản mỗi queue nhóm | Hai instance Billing cạnh tranh trong cùng queue | Đúng fan-out **và** scale-out theo nhóm |

**Giao hàng không phải exactly-once side effect:** broker có thể giao lại sau consumer crash hoặc timeout. Cả Billing, Inventory và Analytics cần có khóa `eventId`/`orderId` ổn định và idempotency cho việc ghi DB/call API.

## 2. Lựa chọn thứ nhất: JMS Topic và subscription

JMS Topic diễn tả publish/subscribe theo API chuẩn. Producer gửi tới một `Topic`; mỗi subscription đủ điều kiện sẽ nhận bản tương ứng. Điểm quyết định việc có giữ event khi hệ thống tạm dừng là **loại subscription đã được đăng ký trước thời điểm publish**.

| Loại subscription | Khi consumer offline | Số active consumer của cùng subscription | Phù hợp |
|---|---|---|---|
| **Non-durable, non-shared** | Không giữ bản mới trong lúc không có subscriber | Thường một consumer mỗi subscription | Dashboard/telemetry chỉ cần sự kiện khi đang online |
| **Durable, non-shared** | Giữ bản cho subscription đã tạo, tới khi consume/expire | Chỉ một active consumer cho cùng danh tính subscription | Một worker độc lập mỗi hệ thống, có backlog |
| **Shared durable** (JMS 2.0/3.1) | Giữ backlog | Nhiều consumer có thể cùng chia message của **một** subscription | Scale nhiều replica trên một luồng thuộc một hệ thống |
| **Shared non-durable** | Không giữ backlog khi subscription không còn consumer hoạt động | Nhiều active consumer cạnh tranh trong cùng subscription | Nhóm worker xử lý live-only |

**Quan trọng:** durable không có nghĩa lưu các sự kiện *trước khi subscription tồn tại*. Nếu Billing chỉ tạo durable subscription sau khi `OrderConfirmed` đã publish, broker không thể tự khôi phục lịch sử đó. Muốn không mất sự kiện từ phút triển khai đầu, **tạo subscription trước khi bật producer**, hoặc dùng phương án queue được provision trước.

### 2.1. Ví dụ một durable subscriber chuẩn JMS

Ứng dụng Billing sử dụng ConnectionFactory tương thích broker đang chạy:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Session;
import jakarta.jms.Topic;

public final class DurableTopicSubscriber {
    public static void readOnce(ConnectionFactory factory,
                                String user, String password) throws Exception {
        try (Connection connection = factory.createConnection(user, password)) {
            // Phải chọn clientID ổn định trước khi dùng connection.
            connection.setClientID("billing-lab");
            try (Session session =
                     connection.createSession(Session.SESSION_TRANSACTED)) {
                Topic topic = session.createTopic("events.orders.v1");
                try (MessageConsumer consumer =
                         session.createDurableSubscriber(topic, "orders-v1")) {
                    connection.start();
                    Message message = consumer.receive(5_000L);
                    if (message != null) {
                        String eventId = message.getStringProperty("eventId");
                        // Chỉ xử lý trong lab; production cần idempotency.
                        System.out.println("billing eventId=" + eventId);
                        session.commit();
                    }
                }
            }
        }
    }
}
```

Để tạo subscription **trước khi publish**, có thể mở subscriber trên, cho `receive(5000)` timeout và đóng consumer. Đừng gọi `unsubscribe("orders-v1")`: thao tác đó xóa durable subscription và backlog của nó. Chạy lại bằng **cùng `clientID` và tên subscription** sẽ nối lại subscription cũ; không tạo ID ngẫu nhiên cho mỗi lần khởi động.

Với Inventory/Analytics, dùng cặp `clientID`/subscription name khác Billing. Một **unshared durable subscription** không cho nhiều active consumer cùng danh tính; nếu cần nhiều replica, thử **shared durable subscription** trên bản JMS provider/broker cụ thể hoặc dùng queue-per-group ở mục 3/4.

### 2.2. Topic có hai subscriber online không có nghĩa hai consumer cùng queue

Hai lần `createConsumer(topic)` thông thường tạo **hai non-durable subscriptions** riêng, nên mỗi subscriber nhận một bản. Hai lần `createConsumer(queue)` trên cùng queue là **competing consumers**, chia message. Nếu dùng nhiều replica của cùng dịch vụ, đừng vô tình tạo nhiều Topic subscriptions độc lập rồi gây hai lần lập hóa đơn.

## 3. Classic Virtual Topic: topic để publish, queue riêng để mỗi hệ thống xử lý

**Virtual Topic** của ActiveMQ Classic là cơ chế *virtual destination*: producer publish vào tên JMS Topic theo quy ước; Classic fan-out sang những queue tương ứng với từng nhóm logic. Không cần ba producer hoặc ba lần gọi `send`.

Với quy ước mặc định của Classic:

```text
Producer:  Topic VirtualTopic.Orders
                 |
                 +--> Queue Consumer.Billing.VirtualTopic.Orders
                 +--> Queue Consumer.Inventory.VirtualTopic.Orders
                 +--> Queue Consumer.Analytics.VirtualTopic.Orders

Billing-1, Billing-2 --> cùng Queue Consumer.Billing.VirtualTopic.Orders
```

**Quy ước mặc định** theo Apache Classic: tên virtual topic trong namespace `VirtualTopic.>`, tên consumer queue khớp mẫu `Consumer.*.VirtualTopic.>`. Dấu `*` là wildcard **một cấp**, `>` là wildcard **phần còn lại** trong cú pháp destination của Classic. Các tên như `Billing` chỉ là **tên nhóm**, không phải username hoặc client ID JMS.

### 3.1. Provision queue *trước* khi phát event

Muốn giữ event ngay cả khi Billing/Inventory đang offline, queue nhóm phải **tồn tại trước khi message được publish**. Đừng dựa vào việc một consumer lần đầu khởi động sau sự kiện rồi broker hồi tố sao chép event cũ.

Trên Classic, có thể tạo sẵn destinations bằng công cụ quản trị/JMX hoặc cấu hình trong `conf/activemq.xml`. Fragment sau thuộc **bên trong `<broker>` đã có**, không phải file cấu hình hoàn chỉnh:

```xml
<destinations>
    <queue physicalName="Consumer.Billing.VirtualTopic.Orders"/>
    <queue physicalName="Consumer.Inventory.VirtualTopic.Orders"/>
    <queue physicalName="Consumer.Analytics.VirtualTopic.Orders"/>
</destinations>
```

Broker Classic mặc định đã cung cấp Virtual Topic convention nói trên; **không cần khai báo một `destinationInterceptor` mới** chỉ để sử dụng tên mặc định. Nếu cấu hình broker đã thay quy tắc Virtual Topic, phải kiểm tra quy tắc thực tế trước khi dùng fragment này. Queue cần được giữ qua restart và có persistence phù hợp nếu nghiệp vụ yêu cầu backlog durable.

Một cách kiểm tra an toàn: **list destinations bằng JMX/console** và xác nhận ba queue hiện diện trước khi gửi sự kiện đầu tiên. Trong môi trường production, tách thay đổi topology/ACL khỏi thay đổi code producer và có quy trình thêm một hệ thống nhận mới.

### 3.2. Java/JMS: publisher tạo Topic, consumer lấy từ Queue

**Publisher:**

```java
Topic destination = context.createTopic("VirtualTopic.Orders");
context.createProducer()
    .setDeliveryMode(DeliveryMode.PERSISTENT)
    .setProperty("eventId", eventId)
    .send(destination, payload);
```

**Consumer Billing:**

```java
Queue billingQueue =
    context.createQueue("Consumer.Billing.VirtualTopic.Orders");
Message message = context.createConsumer(billingQueue).receive(5_000L);
```

Đây là các đoạn **đặt trong method** đã có `JMSContext context`, `eventId`, `payload`, cùng imports `jakarta.jms.Topic`, `Queue` và `Message`. Để tránh lặp mã, chương trình hoàn chỉnh ở mục 6 tái sử dụng cho cả Classic Virtual Topic và Artemis multicast.

**Không tiêu thụ Virtual Topic bằng cách dùng cùng tên Topic rồi gọi `createConsumer(topic)`** nếu mục tiêu là queue-per-group: đó là một **subscription khác** với các semantics về durability/identity khác queue `Consumer.Billing...`.

### 3.3. Vì sao Virtual Topic thuận tiện cho nhiều instance?

Mỗi nhóm logic có một physical queue, nên:

- Hai replica Billing có thể cạnh tranh trên **cùng** `Consumer.Billing.VirtualTopic.Orders` để scale throughput.
- Billing offline vẫn có backlog trên queue đã provision, trong khi Analytics tiếp tục xử lý queue riêng.
- Dễ đọc backlog, số consumer, enqueue/dequeue, in-flight qua JMX **theo hệ thống**.
- Có thể thiết kế DLQ/redelivery và quyền consume theo **queue nhóm**.

Giới hạn: Virtual Topic không tự xử lý idempotency, ordering xuyên nhiều worker hoặc các hệ quả của network of brokers. Khi bật selector trên consumer queue, message **không khớp selector** có thể tiếp tục tồn đọng; tùy chọn `selectorAware` là một lựa chọn nâng cao nhưng phải kiểm tra hành vi khi consumer offline trước khi bật. <https://activemq.apache.org/components/classic/documentation/virtual-destinations>

## 4. Artemis multicast: một address, nhiều queue độc lập

Artemis dùng ba khái niệm lõi: **address** là nơi message được gửi, **queue** chứa message để consumer nhận, và **routing type** quyết định queue nào nhận message.

| Routing type | Cách route | Ứng dụng cho ví dụ |
|---|---|---|
| `ANYCAST` | Đưa message đến **một queue** phù hợp trên address | Competing consumers chia việc trên một queue |
| `MULTICAST` | Route message đến **tất cả các multicast queues** gắn với address | Một bản cho Billing, Inventory và Analytics |

Một multicast address có **ba queue subscription**. Producer gửi một message vào address, broker route một **tham chiếu logic** tới mỗi queue; mỗi queue có backlog/ACK riêng. Đừng đồng nhất “ba bản để xử lý độc lập” với “payload được nhân ba ở tầng vật lý trong journal”: storage implementation có thể chia sẻ dữ liệu và reference.

### 4.1. `broker.xml`: ba queue durable tường minh

Fragment này đặt **bên trong `<addresses>` của `<core>` hiện có** trong Artemis:

```xml
<address name="events.orders.v1">
    <multicast>
        <queue name="billing.orders.events">
            <durable>true</durable>
        </queue>
        <queue name="inventory.orders.events">
            <durable>true</durable>
        </queue>
        <queue name="analytics.orders.events">
            <durable>true</durable>
        </queue>
    </multicast>
</address>
```

Như vậy, ngay từ lúc broker khởi động **đã có đủ ba queue**. Dùng producer JMS Topic:

```java
Topic destination = context.createTopic("events.orders.v1");
context.createProducer()
    .setDeliveryMode(DeliveryMode.PERSISTENT)
    .setProperty("eventId", eventId)
    .send(destination, payload);
```

Đây là publish theo **MULTICAST**, không phải JMS Queue ANYCAST. Khi tạo consumer Core JMS, có thể chỉ rõ **Fully Qualified Queue Name (FQQN)** bằng cú pháp `address::queue`:

```java
Queue billingQueue =
    context.createQueue("events.orders.v1::billing.orders.events");
Message message = context.createConsumer(billingQueue).receive(5_000L);
```

Consumer Inventory dùng `events.orders.v1::inventory.orders.events`; Analytics dùng `events.orders.v1::analytics.orders.events`. Hai replica Billing đều dùng **chính xác cùng FQQN** và chia các message của Billing, không tạo thêm queue mới cho từng instance.

**FQQN không phải một topic khác.** Đây là cách trỏ tới queue xác định đang được bind trên address. Nếu gõ nhầm tên queue hoặc address, broker có thể từ chối hoặc auto-create tài nguyên ngoài dự kiến tùy policy; nên tắt auto-create không cần thiết và provision tường minh ở production.

### 4.2. Cùng Artemis, cũng có thể dùng JMS durable Topic subscribers

Artemis ánh xạ **JMS Topic** vào một **multicast address**; mỗi JMS Topic subscription được biểu diễn bằng **multicast queue** nội bộ. Non-durable subscription thường sinh queue sống theo kết nối; durable subscription thường có tên dựa trên `clientID` và subscription name. Nhờ đó, Topic với durable subscriptions chuẩn JMS cũng là một hình thức multicast trong broker Artemis. <https://artemis.apache.org/components/artemis/documentation/latest/jms-core-mapping.html>

Chọn **một trong hai mô hình** cho mỗi hệ thống:

- **Mô hình JMS-managed subscription:** dùng `createDurableConsumer` hoặc `createSharedDurableConsumer` trên Topic, để Artemis quản lý subscription queue.
- **Mô hình pre-provisioned queue:** khai báo `billing.orders.events` trong `<multicast>` và consume qua FQQN.

**Đừng vừa khai báo queue Billing tường minh, vừa tạo thêm durable Topic subscription riêng cho Billing** rồi nghĩ cả hai dùng chung backlog. Đó là **hai multicast queues**, mỗi cái nhận một bản, có thể dẫn đến xử lý trùng nếu cả hai đang được consume.

### 4.3. Queue filter để chỉ fan-out sự kiện phù hợp

Giả sử Billing chỉ cần `OrderConfirmed` còn Analytics nhận mọi event. Trong Artemis, gắn **queue filter** (dùng JMS property `eventType`) ngay trên queue Billing:

```xml
<queue name="billing.orders.events">
    <durable>true</durable>
    <filter string="eventType = 'OrderConfirmed'"/>
</queue>
```

Đây là **thay thế định nghĩa queue Billing** trong multicast address, **không** thêm queue Billing thứ hai. Khi producer gửi, phải đặt `eventType` là JMS **String property**; filter kiểm tra metadata trước khi route message vào queue nên Billing không tích trữ các event vô ích.

**Phân biệt:** queue filter ở broker ảnh hưởng **message có được thêm vào queue hay không**. Consumer selector chỉ lọc message **đã nằm trong queue** khi consumer đọc. Với selector chỉ có trên consumer, message không khớp vẫn có thể tạo backlog; chọn filter ở đâu phải phản ánh nhu cầu replay và quyền của hệ thống.

## 5. Chọn pattern theo yêu cầu triển khai

| Yêu cầu | JMS Topic (durable/shared) | Classic Virtual Topic | Artemis multicast + queue |
|---|---|---|---|
| Một producer, nhiều hệ thống | Có | Có | Có |
| Hệ thống offline vẫn có backlog | Có, **nếu durable subscription đã tồn tại** | Có, **nếu consumer queue đã tồn tại** | Có, **nếu multicast queue durable đã tồn tại** |
| Nhiều replica cùng chia việc trong một hệ thống | `shared durable subscription`, kiểm tra provider support | Tự nhiên qua consumer queue chung | Tự nhiên qua multicast queue/FQQN chung |
| Quản lý queue nhóm qua console/JMX | Broker phụ thuộc subscription representation | Queue vật lý có tên `Consumer.X.VirtualTopic.Y` | Queue vật lý riêng trên cùng address |
| Portability giữa JMS providers | Cao nhất ở mức API và subscription contract | Phụ thuộc **ActiveMQ Classic** và quy ước Virtual Topic | Phụ thuộc **Artemis address model** / FQQN |
| Thêm hệ thống mới để nhận sự kiện tương lai | Tạo subscription | Provision queue nhóm | Provision queue multicast |
| Tự động nhận lại sự kiện **trước khi** hệ thống được thêm | **Không** | **Không** | **Không** |
| Tách backlog và xử lý lỗi theo nhóm | Theo từng subscription | Theo consumer queue | Theo multicast queue |

**Quy tắc chọn nhanh:** nếu chỉ cần hợp đồng JMS portable và số hệ thống ít, Topic durable/shared đủ dùng. Khi cần dashboard/backlog riêng cho mỗi service và scale nhiều replicas, queue-per-group thường dễ vận hành; ở Classic dùng Virtual Topic, ở Artemis dùng multicast queues.

## 6. Mã Java/JMS chung để chứng minh fan-out

Mã dưới dùng `jakarta.jms` nên phần nghiệp vụ có thể dùng lại trên cả hai broker **với provider dependency phù hợp**. Không lấy URI `tcp://...` của Artemis Core rồi đưa cho Classic OpenWire factory hoặc ngược lại khi broker không bật protocol đó.

### 6.1. Maven: chọn đúng một client provider

**Classic 6.4.x / OpenWire:**

```xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>6.4.0</version>
</dependency>
```

**Artemis 2.57.x / Core** (ứng dụng/test riêng):

```xml
<dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.57.0</version>
</dependency>
```

JDK 17 và `jakarta.jms` được dùng xuyên suốt ví dụ. Với Classic 5.x phải kiểm tra bản client và namespace `javax.jms`/`jakarta.jms` phù hợp, không trộn API khác namespace.

### 6.2. `FanoutProbe.java`: một publish và ba phép nhận có transaction

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.Topic;

import java.util.UUID;

public final class FanoutProbe {
    private FanoutProbe() {}

    static void publish(ConnectionFactory factory, String user, String password,
                        String topicName, String eventId, String payload) {
        try (JMSContext ctx = factory.createContext(user, password)) {
            Topic topic = ctx.createTopic(topicName);
            ctx.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .setProperty("eventId", eventId)
                .setProperty("eventType", "OrderConfirmed")
                .send(topic, payload);
            System.out.println("PUBLISHED eventId=" + eventId);
        }
    }

    static void receiveOne(ConnectionFactory factory,
                           String user, String password,
                           String group, String queueName, String eventId) {
        try (JMSContext tx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue groupQueue = tx.createQueue(queueName);
            // eventId do UUID của ứng dụng tạo, không lấy từ input tùy ý.
            String selector = "eventId = '" + eventId + "'";
            Message msg = tx.createConsumer(groupQueue, selector)
                .receive(5_000L);
            if (msg == null) {
                throw new IllegalStateException(
                    "Missing event for group=" + group + ", queue=" + queueName);
            }
            String actualId = msg.getStringProperty("eventId");
            String body = msg.getBody(String.class);
            if (!eventId.equals(actualId) || !"ORDER-981".equals(body)) {
                throw new IllegalStateException(
                    "Unexpected body/ID for group=" + group);
            }
            // Trong lab chỉ kiểm tra rồi commit. Production phải idempotent
            // và hoàn tất side effect trước khi ACK/commit.
            tx.commit();
            System.out.println("PASS group=" + group + ", eventId=" + actualId);
        }
    }

    static void runClassic(ConnectionFactory cf, String u, String p) {
        String id = "order-" + UUID.randomUUID();
        // Ba queue Consumer.<group>.VirtualTopic.Orders phải tạo TRƯỚC.
        publish(cf, u, p, "VirtualTopic.Orders", id, "ORDER-981");
        receiveOne(cf, u, p, "Billing",
            "Consumer.Billing.VirtualTopic.Orders", id);
        receiveOne(cf, u, p, "Inventory",
            "Consumer.Inventory.VirtualTopic.Orders", id);
        receiveOne(cf, u, p, "Analytics",
            "Consumer.Analytics.VirtualTopic.Orders", id);
    }

    static void runArtemis(ConnectionFactory cf, String u, String p) {
        String id = "order-" + UUID.randomUUID();
        // Ba multicast queues phải được provision TRƯỚC.
        publish(cf, u, p, "events.orders.v1", id, "ORDER-981");
        receiveOne(cf, u, p, "Billing",
            "events.orders.v1::billing.orders.events", id);
        receiveOne(cf, u, p, "Inventory",
            "events.orders.v1::inventory.orders.events", id);
        receiveOne(cf, u, p, "Analytics",
            "events.orders.v1::analytics.orders.events", id);
    }
}
```

**Wiring Classic** (đặt trong `main` hoặc method khởi động đã có `user`/`password`):

```java
import org.apache.activemq.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
FanoutProbe.runClassic(factory, user, password);
```

**Wiring Artemis** (ứng dụng khác, provider khác):

```java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
try {
    FanoutProbe.runArtemis(factory, user, password);
} finally {
    factory.close();
}
```

**Giới hạn:** `FanoutProbe` chứng minh **mỗi group queue có một bản** khi topology đã provision đúng. Đây **không** phải consumer nghiệp vụ hoàn chỉnh, chưa có transaction DB, DLQ, retry hoặc kiểm thử duplicate side effect. Với nhiều queue lab có message cũ, selector giúp chỉ đọc đúng `eventId` thử nghiệm nhưng không xóa backlog khác; không purge queue nghiệp vụ để làm test xanh.

## 7. Thực hành vận hành: offline, scale replicas và lọc sự kiện

### 7.1. Kiểm tra fan-out cơ bản

1. Trên **Classic**, khởi động broker với ba consumer queues; trên **Artemis**, khởi động broker với multicast address và ba queues.
2. Xác minh **đã có ba queue** qua JMX/management **trước** khi publish.
3. Publish một `OrderConfirmed` có `eventId` cố định trong test.
4. Kiểm tra ba queue cùng có event; consume lần lượt từng queue bằng `FanoutProbe`.
5. Xác minh ba dòng `PASS`, mỗi nhóm nhận cùng `eventId`. Không tạo ba event ID khác nhau rồi tuyên bố fan-out thành công.

### 7.2. Một hệ thống offline

1. Provision sẵn tất cả subscription queues, **không** khởi động consumer Billing.
2. Khởi động Inventory/Analytics consumers; publish event mới.
3. Inventory và Analytics nhận được event; message Billing **vẫn pending** trong queue Billing (cho đến khi hết hạn/được xử lý theo policy).
4. Khởi động lại Billing consumer; xác minh nhận đúng `eventId` đó.

Nếu dùng **non-durable Topic subscriber** thay cho các queue persistent, bước 3 sẽ khác: broker không giữ message cho subscriber đã offline. Đây là phép thử phân biệt **fan-out đang online** với **durable fan-out**.

### 7.3. Hai replica trong Billing

Hai consumer cùng consume `Consumer.Billing.VirtualTopic.Orders` trên Classic hoặc `events.orders.v1::billing.orders.events` trên Artemis; gửi 50 event mới có ID khác nhau:

| Điều cần đo | Kỳ vọng |
|---|---|
| Tổng event Billing xử lý | 50 event logic, nếu không có thất bại/expiry |
| Billing-1 và Billing-2 | Cùng chia 50 event; **không bắt buộc 25/25** |
| Inventory | Nhận riêng 50 event |
| Analytics | Nhận riêng 50 event |
| Duplicate processing | Có thể xuất hiện nếu consumer fail trước ACK hoặc gửi lại; cần idempotency |

Không so sánh raw số lần callback làm bằng chứng exactly-once: sau rollback/redelivery, callback có thể xảy ra nhiều lần cho cùng `eventId`. Dùng bảng đã xử lý với khóa unique per-group, ví dụ khóa hợp thành `(groupName, eventId)`.

### 7.4. Lọc event type

Đặt JMS String property `eventType="OrderConfirmed"` hoặc `"OrderCancelled"`. Với Artemis queue filter ở mục 4.3, Billing không lưu `OrderCancelled`; Inventory/Analytics vẫn nhận nếu không có filter. Với Classic, muốn fan-out theo điều kiện trước khi lưu queue cần tìm hiểu `selectorAware`/virtual destination filter **trên đúng phiên bản**; không nghĩ rằng chỉ thêm JMS selector vào một consumer sẽ làm broker loại message chưa khớp khỏi physical queue.

## 8. Điểm khác biệt quan trọng khi chuyển Classic Virtual Topic sang Artemis

Artemis có OpenWire acceptor để client Classic kết nối, nhưng **không thể giả định** chỉ cần chuyển broker là mọi queue tên `Consumer.A.VirtualTopic.Orders` được diễn giải y hệt Classic.

Artemis hỗ trợ **Virtual Topic Consumer Destination Translation** trên OpenWire acceptor. Ví dụ trong `broker.xml`:

```xml
<!-- Fragment thay thế/cấu hình acceptor OPENWIRE phù hợp.
     URL đã encode '>' và ';' bên trong giá trị mapping. -->
<acceptor name="openwire-vt">tcp://0.0.0.0:61617?protocols=OPENWIRE;virtualTopicConsumerWildcards=Consumer.*.%3E%3B2</acceptor>
```

Đối với tên `Consumer.Billing.VirtualTopic.Orders`, Artemis chuyển thành địa chỉ queue kiểu FQQN:

```text
VirtualTopic.Orders::Consumer.Billing.VirtualTopic.Orders
```

Với address `VirtualTopic.Orders` cần có routing `MULTICAST` và các subscription queues được tạo/khớp chính xác. `virtualTopicConsumerWildcards` là cấu hình **cho kết nối OpenWire**, không phải quy tắc tự động áp dụng khi ứng dụng dùng Artemis Core JMS. Nếu dùng Core JMS trực tiếp, cách rõ nhất là publish vào Topic trên multicast address và consume qua FQQN như mục 4.

**Migration checklist:**

- Kiểm kê tên topic/consumer queue, hệ thống nào đang online/offline, selector, durable backlog, message group và DLQ.
- Chọn một cách: dùng **OpenWire translation** để tương thích tên cũ, hoặc đổi ứng dụng sang **Artemis Core + multicast queues/FQQN**.
- Tạo/khôi phục subscription queues **trước** khi bật producer; kiểm tra routing type đúng.
- Kiểm thử với consumer offline, restart broker, nhiều replica, selector và event có `JMSExpiration`. Nếu chuyển dữ liệu backlog cần **kế hoạch migration riêng**, thay broker không tự mang theo journal/queue Classic.
- Tách mạng broker: Artemis acceptor lắng nghe protocol thích hợp; class `ActiveMQConnectionFactory` tên giống nhau nhưng Core/OpenWire wire format khác nhau.

**Lưu ý Classic network of brokers:** tài liệu chính thức cảnh báo **bridge consumer queues hoặc bridge virtual topic, không đồng thời cả hai**, vì message có thể bị fan-out lại và gây duplicate. Khi có liên kết broker, xác định **một nơi chịu trách nhiệm fan-out** và kiểm thử đường đi sự kiện qua từng hop. <https://activemq.apache.org/components/classic/documentation/virtual-destinations>

## 9. Reliability và vận hành fan-out theo từng hệ thống

| Trường hợp | Điều xảy ra | Hướng xử lý |
|---|---|---|
| Billing downtime, các hệ khác vẫn chạy | Billing backlog tăng trên queue riêng | Giám sát queue depth, age và tốc độ tiêu thụ; không để TTL làm mất event bắt buộc |
| Billing đã gửi lệnh thanh toán rồi crash trước ACK | Broker có thể redeliver event | Idempotency theo `(Billing, eventId)` và key ở API thanh toán |
| Một event có nhiều subscribers | Mỗi subscription/queue có vị trí ACK riêng | Không coi một consumer ACK là event đã xử lý ở tất cả hệ thống |
| Inventory queue quá tải | Queue Inventory backlog; địa chỉ/broker có thể chịu áp lực storage chung | Chính sách capacity/paging/backpressure; fan-out **không** cô lập vô hạn tài nguyên |
| Consumer mới đăng ký sau khi event đã phát | Không tự nhận event lịch sử | Backfill từ event store/outbox/replay pipeline có quy trình, không dựa vào Topic |
| Consumer selector lọc quá hẹp | Có thể có message không phù hợp nằm trong queue | Dùng queue filter/selector-aware đúng semantics; đo unmatched backlog |
| Thêm một replica nhưng số event Billing tăng gấp đôi | Có thể replica đăng ký subscription **mới** thay vì cùng queue | Đối chiếu subscription IDs, FQQN, clientID và queue names |
| Fan-out qua nhiều broker | Dễ tạo fan-out lặp nếu bridge cả topic và queue | Thiết kế một đường forwarding, test duplicate/cycle |

### Metrics tối thiểu

Đối với mỗi nhóm `Billing`/`Inventory`/`Analytics` nên có:

- Queue depth/pending, delivering/in-flight, consumer count, enqueue/dequeue theo thời gian.
- Tuổi của message tồn đọng cũ nhất, tỷ lệ expired/failed/redelivered và backlog DLQ riêng.
- Thời gian từ event `createdAt` tới side effect thành công **theo từng nhóm**, không lấy latency của producer làm latency end-to-end.
- Số event ID đã xử lý, số trùng được idempotency chặn, số hệ thống chưa xử lý xong và retry age.

**Sự khác nhau giữa “fan-out” và “quy trình hoàn thành mọi hệ thống”:** broker phát cho ba nhóm không có nghĩa producer được biết cả ba đã xử lý thành công. Nếu Order service cần xác nhận Billing + Inventory đều DONE trước bước tiếp, phải dùng một **orchestrator/saga hoặc tracking table** theo `eventId` và trạng thái từng nhóm. Topic/Virtual Topic/multicast đơn thuần không cung cấp business barrier đó.

## 10. Checklist nghiệm thu

- [ ] Producer publish **một event duy nhất** và không tự gửi ba lần cho ba nhóm.
- [ ] Billing, Inventory và Analytics có **subscription/queue riêng**, được tạo **trước** khi publish.
- [ ] Hai replica của **cùng một hệ thống** sử dụng **một shared subscription hoặc một queue chung**, không tạo hai subscription độc lập.
- [ ] Classic Virtual Topic tuân thủ `VirtualTopic.*` và `Consumer.<group>.VirtualTopic.*`; queue tồn tại, backlog đo được.
- [ ] Artemis dùng `MULTICAST` với queue durable, Core consumers đọc chính xác `address::queue`.
- [ ] Phép thử offline một nhóm không làm hai nhóm còn lại mất event; sau online nhóm đó nhận được backlog.
- [ ] Phép thử nhiều replica không tạo thêm một bản event cho nhóm Billing.
- [ ] Có `eventId` bất biến, idempotency cho side effect, TTL/retention phù hợp và giám sát backlog theo nhóm.
- [ ] Nếu đi qua nhiều broker, đã xác minh routing/bridge chỉ fan-out một lần; không có loop hay double-forward.

**Kết luận:** JMS Topic cung cấp pub/sub chuẩn; Classic Virtual Topic ánh xạ Topic thành **queue riêng mỗi nhóm**; Artemis multicast thực hiện fan-out qua **nhiều queue gắn cùng address**. Cả ba đều có thể phát một sự kiện cho nhiều hệ thống, nhưng để triển khai đáng tin cậy phải làm đúng **identity của subscription**, tạo backlog **trước khi publish**, cho replica **chia việc trong một nhóm**, và kiểm soát duplicate, capacity và replay.

## Tài liệu chính thức

1. [ActiveMQ Classic — Virtual Destinations](https://activemq.apache.org/components/classic/documentation/virtual-destinations): `VirtualTopic.>`, `Consumer.*.VirtualTopic.>`, selectorAware và cảnh báo bridge.
2. [Apache Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): ANYCAST/MULTICAST, queue-per-subscription, FQQN và queue filters.
3. [Apache Artemis — Mapping JMS Concepts to the Core API](https://artemis.apache.org/components/artemis/documentation/latest/jms-core-mapping.html): Topic ↔ multicast address, durable subscription ↔ multicast queue.
4. [Apache Artemis — OpenWire](https://artemis.apache.org/components/artemis/documentation/latest/openwire.html): `virtualTopicConsumerWildcards`, translation Virtual Topic → FQQN.
5. [Apache Artemis — Messaging Concepts](https://artemis.apache.org/components/artemis/documentation/latest/messaging-concepts.html): durable và non-durable pub/sub.
6. [Jakarta Messaging 3.1 — JMSContext](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext): `createDurableConsumer`, `createSharedDurableConsumer`, `createQueue`/`createTopic`.
