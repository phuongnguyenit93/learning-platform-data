# Multicast và sao chép thông điệp đến các queue đăng ký

## 1. Multicast trong Artemis thực sự “sao chép” điều gì?

Trong **Apache ActiveMQ Artemis**, producer gửi message đến một **address**. Address có routing type **MULTICAST** sẽ định tuyến message đó tới **tất cả queue được bind với address theo kiểu MULTICAST và thỏa điều kiện lọc**. Mỗi queue được chọn sẽ có **một bản phân phối logic** của message; consumer trên từng queue xác nhận và xử lý bản phân phối của mình một cách độc lập.

Xét dịch vụ Đơn hàng phát sự kiện **OrderPaid** đến address **orders.events**:

~~~mermaid
flowchart LR
    P["Order Producer"] -->|"OrderPaid / MULTICAST"| A(("Address: orders.events"))
    A --> QI[("Queue: inventory.events")]
    A --> QB[("Queue: billing.paid")]
    A --> QA[("Queue: audit.events")]
    QI --> I["Inventory consumer"]
    QB --> B["Billing consumer"]
    QA --> U["Audit consumer"]
~~~

Ở thời điểm gửi **một** message OrderPaid, nếu cả ba queue đều được bind phù hợp, mỗi queue có một cơ hội xử lý message đó. **Inventory commit** không làm message tự biến mất khỏi **Billing** hoặc **Audit**. Vì vậy multicast tạo một **fan-out theo queue**, khác với việc nhiều consumer cùng tranh việc trên **một queue**.

Đặc biệt, từ “sao chép” ở đây là **sao chép trách nhiệm giao nhận**, không bắt buộc broker tạo ba bản byte payload vật lý độc lập trên đĩa. Artemis có thể quản lý phần dữ liệu message và **các queue reference** riêng để tối ưu lưu trữ; chi tiết persistence phụ thuộc phiên bản, kích thước message và cơ chế storage. Điều ứng dụng phải dựa vào là **mỗi queue có trạng thái giao/ACK riêng**, không phải số bản copy vật lý.

Bài thuộc chương **Định tuyến Artemis** của module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**. Trọng tâm là cách **MULTICAST routing** tạo các bản phân phối đến queue đăng ký, cách cấu hình, kiểm chứng bằng Java/JMS và cách xử lý khi các queue có tiến độ khác nhau.

## 2. Quy tắc định tuyến: address, routing type, queue binding

Artemis phân biệt rõ ba đối tượng:

| Đối tượng | Chức năng | Trong ví dụ |
| --- | --- | --- |
| **Address** | Đích mà producer gửi message đến | **orders.events** |
| **Routing type** | Quy tắc chọn queue nhận message | **MULTICAST** |
| **Queue** | Nơi chứa các message reference chờ consumer | **inventory.events**, **billing.paid**, **audit.events** |
| **Queue binding** | Liên hệ queue với address và routing type | Ba queue được bind vào **orders.events** với kiểu MULTICAST |
| **Filter** | Điều kiện chọn message cho queue/subscription | **billing.paid** chỉ nhận **eventType = 'OrderPaid'** |
| **Consumer** | Đọc và ACK message của một queue | Inventory, Billing và Audit chạy độc lập |

Một queue thuộc một address, trong khi một address có thể có **nhiều queue**. Với MULTICAST, Artemis kiểm tra các queue phù hợp tại thời điểm route và tạo phân phối cho **từng queue**. Nếu chỉ có **một queue** dưới address, nhiều consumer cùng đọc queue đó vẫn chia nhau công việc; không có một bản phân phối cho từng consumer.

### Ví dụ cụ thể với hai sự kiện

Giả sử address **orders.events** có ba queue:

- **inventory.events**: không filter, nhận mọi event của address.
- **billing.paid**: filter **eventType = 'OrderPaid'**.
- **audit.events**: không filter, nhận mọi event của address.

Producer gửi hai message theo thứ tự:

- **M1 — OrderPlaced** với property **eventType = OrderPlaced**.
- **M2 — OrderPaid** với property **eventType = OrderPaid**.

Bảng phân phối mong đợi:

| Queue nhận | M1: OrderPlaced | M2: OrderPaid | Vì sao? |
| --- | --- | --- | --- |
| **inventory.events** | Có | Có | Queue không có filter, nhận cả hai |
| **billing.paid** | Không | Có | Filter chỉ khớp OrderPaid |
| **audit.events** | Có | Có | Queue không có filter, nhận cả hai |

Như vậy **2 lần producer gửi** có thể tạo **5 bản phân phối logic** trên ba queue. Không nên diễn giải rằng producer đã gọi send 5 lần; broker thực hiện fan-out theo binding và filter.

~~~mermaid
flowchart TD
    M1["M1: OrderPlaced"] --> R1{"MULTICAST route"}
    M2["M2: OrderPaid"] --> R2{"MULTICAST route"}
    R1 --> I1["inventory.events: M1"]
    R1 --> A1["audit.events: M1"]
    R1 -. "Filter không khớp" .-> X["billing.paid: không có M1"]
    R2 --> I2["inventory.events: M2"]
    R2 --> B2["billing.paid: M2"]
    R2 --> A2["audit.events: M2"]
~~~

**Điều kiện tiên quyết:** queue phải tồn tại hoặc subscription phù hợp phải được tạo **trước thời điểm message được route**. Queue tạo sau không tự nhận lịch sử, trừ khi hệ thống chủ động cung cấp cơ chế replay/retroactive riêng. Một address tồn tại sẵn mà chưa có queue phù hợp không tự giữ mọi message cho các queue xuất hiện trong tương lai.

## 3. So sánh MULTICAST và ANYCAST tại cùng một address

Artemis có hai routing type cốt lõi:

| Tình huống | MULTICAST | ANYCAST |
| --- | --- | --- |
| Có ba queue phù hợp dưới một address | Message được route đến **cả ba queue** | Message thường được chọn route đến **một queue phù hợp** |
| Ba consumer cùng đọc **một queue** | Các consumer vẫn cạnh tranh trong queue đó | Các consumer cũng cạnh tranh trong queue đó |
| Muốn ba dịch vụ độc lập cùng nhận một event | Tạo **ba queue MULTICAST** | ANYCAST đơn thuần không cung cấp fan-out đến cả ba |
| Muốn ba worker cùng xử lý một hàng tác vụ | Một queue với ba consumers, không cần ba queue | Một queue ANYCAST với ba consumers |
| Queue A chậm, queue B nhanh | A có backlog/ACK riêng; B có thể xử lý xong trước | Phụ thuộc queue được chọn, không phải bản sao cho mọi queue |

Lưu ý **address có thể được cấu hình hỗ trợ cả ANYCAST và MULTICAST**. Khi đó, kết quả phụ thuộc **routing type của message**, giao thức client và cách destination được tạo. Không nên chỉ nhìn tên address rồi khẳng định producer đang fan-out.

Với **JMS**, **Topic** thường được ánh xạ đến MULTICAST; **Queue** thường được ánh xạ đến ANYCAST. Khi ứng dụng dùng Artemis Core API, AMQP hoặc các giao thức khác, cần xác định rõ message routing type và binding; một protocol có thể ánh xạ khác JMS. Với bài thực hành này, producer dùng **JMS Topic** tới **orders.events**, còn consumer truy cập trực tiếp từng queue đã bind qua **fully qualified queue name**.

## 4. Khai báo address MULTICAST và các queue đăng ký trong broker.xml

Để kết quả thử nghiệm có thể lặp lại, tạo trước address và các queue trong broker. Đặt phần sau **bên trong phần tử addresses hiện hữu** của **broker.xml** thuộc broker Artemis:

~~~xml
<address name="orders.events">
    <multicast>
        <queue name="inventory.events" durable="true"/>
        <queue name="billing.paid" durable="true">
            <filter string="eventType = 'OrderPaid'"/>
        </queue>
        <queue name="audit.events" durable="true"/>
    </multicast>
</address>
~~~

Đây là **đoạn cấu hình**, chưa phải tệp **broker.xml** hoàn chỉnh. Không thêm phần tử **addresses** thứ hai bên ngoài cấu trúc cấu hình hiện tại; phải tích hợp theo schema và quy tắc cấu hình của release Artemis đang sử dụng.

Các thuộc tính có ý nghĩa:

- **address name="orders.events"**: đích publish duy nhất cho producer.
- **multicast**: route đến mỗi queue MULTICAST thỏa điều kiện.
- **queue name="..."**: tạo binding của từng nhóm nhận; ba queue có tiến độ ACK riêng.
- **durable="true"**: queue được cấu hình bền vững. Để message còn qua restart còn cần delivery mode, storage, broker policy và điều kiện lưu trữ phù hợp.
- **filter** trên **billing.paid**: chỉ các message có property **eventType** bằng chuỗi **OrderPaid** mới được đưa vào queue này.

**Điểm khác biệt rất dễ nhầm:** **filter của queue** quyết định message có được route/enqueue vào queue đó hay không. Một **JMS message selector của consumer** dùng để chọn message mà consumer nhận trong một queue/subscription; việc đặt selector ở consumer không tự xóa các message khác khỏi một queue dùng chung. Với một số API tạo topic subscription, broker có thể hiện thực selector dưới dạng filter của queue subscription. Vì thế khi cần giảm bản phân phối ngay ở khâu routing, hãy chủ động đặt filter vào **queue binding** hoặc tạo đúng subscription selector.

### Không cần ba producer

Producer gửi **một message** đến **orders.events**. Broker lựa chọn các queue tại thời điểm routing. Không triển khai ba lần gọi send lần lượt tới ba queue nếu mục đích là một sự kiện broadcast chuẩn, vì điều đó thêm rủi ro chỉ gửi thành công một phần khi producer lỗi giữa các lần gửi.

Multicast cũng **không** có nghĩa broker sẽ đảm bảo mọi side effect của ba dịch vụ hoàn thành đồng thời. Sau khi message được route, Inventory, Billing và Audit làm việc độc lập; hệ thống nghiệp vụ phải chấp nhận độ trễ khác nhau hoặc có cơ chế phối hợp nếu cần.

### Nếu queue được thêm sau khi đã có message

Giả sử message **M0** được gửi khi chỉ có **inventory.events**; sau đó quản trị viên thêm **audit.events**. Queue Audit mới sẽ nhận các **message phù hợp tiếp theo**, không mặc nhiên nhận M0. Để Audit xử lý M0, cần nguồn lưu lịch sử (event log/outbox, snapshot, archive hoặc cơ chế replay đã thiết kế trước). Cấu hình một durable queue **sau** khi sự kiện đã được phát không làm xuất hiện bản phân phối của sự kiện quá khứ.

## 5. Subscription queue tự tạo: JMS Topic khác với queue cấu hình tĩnh

Trong JMS Topic, **mỗi subscription** có thể tương ứng với một queue phía Artemis. Có hai kiểu lifecycle quan trọng:

### Non-durable subscription

Khi client tạo consumer thông thường trên Topic, Artemis có thể tạo **queue subscription không bền** với tên do broker/client quản lý. Message được route vào queue đó khi subscription đang hoạt động; đóng subscription làm mất quyền nhận các message phát trong thời gian offline. Điều này thích hợp cho UI live, dashboard, thông báo thay đổi trạng thái có thể bỏ lỡ.

~~~java
Topic topic = context.createTopic("orders.events");
JMSConsumer liveConsumer = context.createConsumer(topic);
// Non-durable subscription thông thường, không tự có offline backlog.
~~~

Trong mô hình này, **một consumer mới** ở Topic thường là **một subscription khác**, do đó hai consumer ở hai session độc lập có thể nhận cùng event khi cả hai đang subscribe.

### Durable subscription

Với một subscription durable được đăng ký đúng và duy trì bởi broker, queue subscription có thể giữ message publish lúc consumer tạm offline. Client nhận lại backlog khi mở đúng subscription identity, theo TTL/retention và policy của broker.

~~~java
// factory, user, password đã được cấu hình.
// context.setClientID phải thực hiện trước khi bắt đầu dùng connection.
JMSContext context = factory.createContext(
        user, password, JMSContext.AUTO_ACKNOWLEDGE);
context.setClientID("inventory-service-v1");

Topic topic = context.createTopic("orders.events");
JMSConsumer consumer =
        context.createDurableConsumer(topic, "inventory-orders");
~~~

Đoạn này chỉ minh họa **đăng ký durable**; code thực tế cần đóng consumer/context, xử lý lỗi và quản lý đúng clientID/subscriptionName. Durable subscription không chia sẻ phải tuân thủ quy tắc định danh và kết nối đồng thời của JMS/provider; khi cần nhiều consumer trên **cùng một subscription**, sử dụng khả năng shared durable subscription nếu broker/client hỗ trợ và thiết kế phù hợp.

**Quan trọng:** Ba queue cấu hình tĩnh ở mục 4 là **ba queue bền vững gắn với MULTICAST address**, không phải ba JMS durable subscriptions tự động sinh từ đoạn **createDurableConsumer** này. Nếu chạy đồng thời code tạo durable subscriber mới và ba queue tĩnh, sẽ xuất hiện **thêm một queue subscription** và **thêm một bản phân phối** cho nó nếu đủ điều kiện. Tránh cấu hình trùng listener khiến bạn tưởng broker “nhân đôi message ngoài dự kiến”.

### Một queue có nhiều consumer không phải multicast đến từng consumer

Giả sử **inventory.events** có ba replica Inventory:

~~~mermaid
flowchart LR
    A(("orders.events / MULTICAST")) --> QI[("inventory.events")]
    A --> QA[("audit.events")]
    QI --> I1["Inventory-1"]
    QI --> I2["Inventory-2"]
    QI --> I3["Inventory-3"]
    QA --> AU["Audit"]
~~~

Artemis route một bản phân phối tới **inventory.events**. Trong queue đó, các replica **Inventory-1/2/3** là **competing consumers**: thông thường một message chỉ được giao cho **một** instance tại một thời điểm, và có thể được giao lại nếu instance không ACK. **Audit** là queue khác nên nhận bản phân phối riêng. Để mỗi replica Inventory đều nhận event, cần mỗi replica có subscription queue độc lập, nhưng đó thường không phải mong muốn với service scale ngang.

## 6. Truy cập queue cụ thể bằng FQQN

**Fully Qualified Queue Name (FQQN)** của Artemis có dạng:

~~~text
<address>::<queue>
~~~

Ví dụ:

~~~text
orders.events::inventory.events
orders.events::billing.paid
orders.events::audit.events
~~~

FQQN giúp client chỉ định rõ queue nào trong nhiều queue cùng address. Đây là cách thuận tiện để kiểm chứng fan-out đã cấu hình sẵn bằng API JMS:

~~~java
Topic destination = context.createTopic("orders.events"); // Publish tới address.
Queue inventory = context.createQueue(
        "orders.events::inventory.events");                // Consume đúng queue.
Queue billing = context.createQueue(
        "orders.events::billing.paid");
~~~

FQQN **không phải tên topic thứ hai** và cũng không ngụ ý tự tạo ba queue. Các queue đã được định nghĩa trong **broker.xml**; client sử dụng FQQN để truy cập. Một số protocol hoặc phiên bản client có quy tắc destination khác nhau; phải kiểm tra FQQN của đúng Artemis client khi chuyển sang Core/AMQP hoặc thư viện khác.

Nếu đổi sang **createQueue("orders.events")** không kèm FQQN, client có thể tương tác với queue cùng tên address hoặc kích hoạt auto-create/ANYCAST theo cấu hình. Đây là một lỗi khá phổ biến khi một ứng dụng mong multicast nhưng lại đọc queue khác queue subscription dự định.

## 7. Thực hành Java JMS: hai sự kiện, ba queue, năm bản phân phối

Đoạn demo sau kiểm chứng đúng ma trận ở mục 2 trên Artemis, dùng **Jakarta Messaging** và JMS transaction.

### Chuẩn bị môi trường

- Khởi động một broker **Apache ActiveMQ Artemis** và áp dụng cấu hình MULTICAST address cùng ba queue ở mục 4.
- Client kết nối tới **tcp://127.0.0.1:61616** hoặc cổng host mà bạn đã publish. Nếu chạy hai broker Classic/Artemis đồng thời và Artemis được map tới **61617**, đặt **BROKER_URL=tcp://127.0.0.1:61617**.
- Cung cấp **BROKER_USER**, **BROKER_PASSWORD** và quyền **send** trên address, **consume** trên ba queue. Broker không được tự chuyển message vào ANYCAST do destination cấu hình sai.
- Dùng JDK 17+, Maven và dependency **org.apache.activemq:artemis-jakarta-client** phù hợp broker. Không trộn namespace **jakarta.jms** và **javax.jms** trong cùng code demo này.

Ví dụ **pom.xml** độc lập:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab.messaging</groupId>
    <artifactId>artemis-multicast-routing</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.42.0</version>
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
~~~

Phiên bản Maven dependency trên là **một phiên bản tham chiếu** phục vụ minh họa; trong môi trường triển khai hãy pin client artifact tương thích phiên bản broker và xác minh support matrix chính thức. Code không yêu cầu thư viện JSON: payload dùng **TextMessage** đơn giản, còn routing dựa vào JMS properties.

Tạo **src/main/java/ArtemisMulticastProbe.java**:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Objects;
import java.util.UUID;

public final class ArtemisMulticastProbe {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");

        String runId = UUID.randomUUID().toString();
        String selector = "labRun = '" + runId + "'";

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        // Mỗi queue được tiêu thụ bằng một JMS transaction/session riêng.
        try (JMSContext producer = factory.createContext(
                        user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext inventory = factory.createContext(
                        user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext billing = factory.createContext(
                        user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext audit = factory.createContext(
                        user, password, JMSContext.SESSION_TRANSACTED)) {

            Topic topic = producer.createTopic("orders.events");

            // Send trước khi tạo consumer: các queue durable đã tồn tại
            // trong broker.xml, nên chúng vẫn có thể tích lũy message.
            send(producer, topic, runId, "evt-placed", "OrderPlaced");
            send(producer, topic, runId, "evt-paid", "OrderPaid");
            producer.commit();

            Queue inventoryQueue = inventory.createQueue(
                    "orders.events::inventory.events");
            Queue billingQueue = billing.createQueue(
                    "orders.events::billing.paid");
            Queue auditQueue = audit.createQueue(
                    "orders.events::audit.events");

            JMSConsumer invConsumer =
                    inventory.createConsumer(inventoryQueue, selector);
            JMSConsumer billConsumer =
                    billing.createConsumer(billingQueue, selector);
            JMSConsumer auditConsumer =
                    audit.createConsumer(auditQueue, selector);

            // Inventory nhận đủ M1 và M2.
            expect(inventory, invConsumer, "OrderPlaced", "evt-placed",
                    "inventory.events");
            expect(inventory, invConsumer, "OrderPaid", "evt-paid",
                    "inventory.events");

            // Billing chỉ nhận M2 do filter trên queue.
            expect(billing, billConsumer, "OrderPaid", "evt-paid",
                    "billing.paid");
            if (billConsumer.receive(1500) != null) {
                billing.rollback();
                throw new IllegalStateException(
                        "billing.paid unexpectedly received extra message");
            }

            // Audit nhận đủ M1 và M2, độc lập với commit của Inventory.
            expect(audit, auditConsumer, "OrderPlaced", "evt-placed",
                    "audit.events");
            expect(audit, auditConsumer, "OrderPaid", "evt-paid",
                    "audit.events");

            System.out.println("PASS multicast fan-out runId=" + runId);
        }
    }

    private static void send(
            JMSContext tx, Topic topic, String runId,
            String eventId, String eventType) throws Exception {
        TextMessage message = tx.createTextMessage(
                "{\"eventId\":\"" + eventId
                + "\",\"eventType\":\"" + eventType + "\"}");
        message.setStringProperty("labRun", runId);
        message.setStringProperty("eventId", eventId);
        message.setStringProperty("eventType", eventType);

        tx.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .send(topic, message);

        System.out.println("SENT " + eventType + " eventId=" + eventId);
    }

    private static void expect(
            JMSContext tx, JMSConsumer consumer,
            String expectedType, String expectedId,
            String queueName) throws Exception {
        try {
            Message message = consumer.receive(10000);
            if (!(message instanceof TextMessage)) {
                throw new IllegalStateException(
                        queueName + ": missing TextMessage");
            }
            String actualType = message.getStringProperty("eventType");
            String actualId = message.getStringProperty("eventId");
            if (!expectedType.equals(actualType)
                    || !expectedId.equals(actualId)) {
                throw new IllegalStateException(
                        queueName + ": unexpected event "
                        + actualType + "/" + actualId);
            }

            // Ứng dụng thực phải commit side effect bền vững trước bước này.
            tx.commit();
            System.out.println("ACK " + queueName + " <- "
                    + actualType + "/" + actualId);
        } catch (Exception failure) {
            tx.rollback();
            throw failure;
        }
    }
}
~~~

Trong ví dụ này, **producer.commit()** xác nhận hai lần send trong cùng JMS transaction. Từng **expect()** xác nhận message trên **session của queue tương ứng**; commit của Inventory không làm Audit tự ACK. **billing.paid** không nhận OrderPlaced ngay từ giai đoạn route vì queue filter. Selector **labRun** trên consumer chỉ phục vụ cách ly những lần chạy lab khác nhau.

Chạy trong PowerShell tại thư mục Maven chứa ví dụ:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "your-artemis-user"
$env:BROKER_PASSWORD = "your-artemis-password"

mvn -q compile exec:java "-Dexec.mainClass=ArtemisMulticastProbe"
~~~

Nếu broker Artemis được publish trên cổng **61617** thì sửa **BROKER_URL** tương ứng; ứng dụng chạy trong cùng Compose network dùng hostname service và cổng nội bộ của broker thay vì localhost của host. Mật khẩu ở đoạn mẫu là placeholder, cần thay bằng credential thực.

### Kết quả mong đợi

~~~text
SENT OrderPlaced eventId=evt-placed
SENT OrderPaid eventId=evt-paid
ACK inventory.events <- OrderPlaced/evt-placed
ACK inventory.events <- OrderPaid/evt-paid
ACK billing.paid <- OrderPaid/evt-paid
ACK audit.events <- OrderPlaced/evt-placed
ACK audit.events <- OrderPaid/evt-paid
PASS multicast fan-out runId=...
~~~

Trong lab chỉ có một producer tuần tự, các message cùng priority, không có lỗi và mỗi queue một consumer; thứ tự mong đợi trên từng queue ổn định. Ở hệ thống thực có nhiều producer, priority, rollback, redelivery, failover hoặc nhiều consumer, không nên suy ra có một **thứ tự xử lý tổng thể duy nhất** giữa các queue.

**Lưu ý khi chạy lại:** các queue **durable** có thể chứa message từ lần lab trước. Mẫu dùng consumer selector **labRun** nên chỉ đọc đúng lượt hiện tại; các message cũ không bị selector tự xóa khỏi queue. Hãy dùng queue/instance thử nghiệm riêng và quản trị backlog cũ một cách có chủ đích, tránh dùng lệnh purge trên queue production.

## 8. ACK và rollback có phạm vi của từng queue

Sau khi multicast, mỗi queue có trạng thái giao nhận riêng. Không tồn tại một ACK toàn cục với nghĩa “mọi subscriber đều xong”.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer
    participant A as Address orders.events
    participant QI as Inventory queue
    participant QA as Audit queue
    participant CI as Inventory consumer
    participant CA as Audit consumer

    P->>A: Publish OrderPaid
    A->>QI: Tạo phân phối cho Inventory
    A->>QA: Tạo phân phối cho Audit
    QI->>CI: Dispatch
    QA->>CA: Dispatch
    CI->>CI: Commit nghiệp vụ
    CI-->>QI: JMS ACK / commit
    Note over QA: Audit vẫn chưa ACK
    CA->>CA: Lỗi nghiệp vụ
    CA-->>QA: rollback
    QA->>CA: Redelivery theo policy
    CA-->>QA: ACK khi xử lý lại thành công
~~~

| Trường hợp | Inventory queue | Audit queue |
| --- | --- | --- |
| Inventory ACK, Audit chưa nhận | Không còn bản chưa ACK của Inventory | Message vẫn chờ Audit |
| Inventory ACK, Audit rollback | Không redeliver cho Inventory chỉ vì Audit lỗi | Audit có thể được redeliver |
| Inventory consumer offline, Audit online | Queue Inventory durable có thể tích lũy backlog | Audit vẫn có thể xử lý |
| Inventory queue bị xóa | Không còn backlog thuộc queue đó sau khi xóa | Audit queue không bị xóa theo mặc định |
| Broker gặp giới hạn tài nguyên chung | Backlog/flow control có thể ảnh hưởng producer hoặc cả address | Độc lập ACK không đồng nghĩa hoàn toàn độc lập tài nguyên |

**Phạm vi transaction:** JMS transaction trên một session gom các send/receive thuộc session đó. Nó không tạo distributed transaction giữa database của Inventory và database của Audit. Nếu một subscriber đã commit database nhưng mất kết nối trước JMS commit, message có thể được giao lại **trong queue đó**. Consumer phải dùng **idempotency key** như eventId ổn định để tránh side effect lặp.

### Tại sao cần quan sát từng queue?

Ví dụ một message được route tới ba queue; hai queue đã ACK, một queue tồn đọng. Số lượng pending của address không thể được diễn giải như số “sự kiện chưa xử lý trên toàn hệ thống” nếu không biết cách metric cộng các queue reference. Để xác định nhóm nhận bị kẹt, xem ít nhất:

- **Message count / pending** của từng queue.
- **Delivering/in-flight** và consumer count theo queue.
- **Oldest message age** hoặc độ trễ backlog.
- Redelivery, expired, DLQ và lỗi xử lý của từng nhóm.
- Journal/paging và giới hạn tài nguyên ở cấp address/broker.

Một subscriber chậm **không khiến ACK của subscriber khác bị hoàn tác**. Nhưng vì các queue cùng chia tài nguyên broker, backlog quá lớn của một queue vẫn có thể làm tăng memory/disk pressure hoặc kích hoạt flow control đối với producer.

## 9. Phân phối có filter: route-time và receive-time

Filter thường được áp dụng ở hai tầng có mục đích khác nhau:

**Queue filter tại binding**:

~~~xml
<queue name="billing.paid" durable="true">
    <filter string="eventType = 'OrderPaid'"/>
</queue>
~~~

Khi OrderPlaced được publish, **billing.paid không có bản phân phối** của message này. Điều đó giúp tránh tích lũy message không liên quan trong queue Billing.

**JMS consumer selector**:

~~~java
JMSConsumer consumer =
        context.createConsumer(queue, "region = 'VN'");
~~~

Selector này giới hạn những message consumer nhận trên queue được chọn. Message không khớp selector **không mặc nhiên bị xóa khỏi queue**; một consumer khác có thể nhận message đó tùy thuộc selector và policy. Nếu chỉ có một consumer với selector quá hẹp, queue có thể tích lũy thông điệp không ai nhận.

Nếu ứng dụng muốn **hai nhóm xử lý độc lập cùng lọc theo điều kiện khác nhau**, hãy tạo **hai queue MULTICAST độc lập với filter tương ứng** để tách quyền sở hữu backlog và hành vi ACK. Không tạo một queue rồi đặt hai selectors khác nhau trên hai consumer và kỳ vọng cả hai cùng nhận message phù hợp; trong một queue chúng vẫn cạnh tranh tiêu thụ.

Ví dụ phân nhánh:

~~~text
orders.events (MULTICAST)
  ├─ billing.paid      filter: eventType = 'OrderPaid'
  ├─ shipping.created  filter: eventType = 'OrderPlaced'
  └─ audit.events      không filter
~~~

Những message có property **eventType** thiếu/sai kiểu có thể không khớp filter; cần schema và kiểu property nhất quán khi producer gửi. Ví dụ **OrderPaid** trong payload JSON nhưng **không có JMS property eventType** sẽ không tự động khớp queue filter: Artemis lọc theo message properties/headers, không tự đọc trường JSON theo quy tắc filter này.

## 10. Kết hợp MULTICAST với subscriptions động và vòng đời offline

Một địa chỉ MULTICAST có thể đồng thời có **queue tĩnh** và **queue subscription do JMS client tạo**, miễn chính sách broker cho phép.

| Đường nhận | Khi consumer tạm ngoại tuyến | Điều kiện để vẫn có backlog |
| --- | --- | --- |
| Queue tĩnh **durable=true** | Queue vẫn tồn tại | Queue không bị xóa; message phù hợp, độ bền/storage và policy đáp ứng |
| JMS **durable subscription** | Broker duy trì subscription | Subscription đã được đăng ký, identity giữ ổn định, quota/TTL cho phép |
| JMS **non-durable subscription** | Subscription kết thúc khi consumer đóng/ngắt theo lifecycle | Không có bảo đảm nhận lại message publish lúc subscription không hoạt động |
| Queue tĩnh không bền hoặc auto-delete | Có thể bị xóa theo policy | Không được dựa vào queue còn tồn tại sau restart/offline |

Điểm quyết định việc fan-out ở lúc publish là: **queue/subscription có tồn tại và được bind phù hợp hay không**. Một durable queue tạo trước sẽ nhận phân phối dù consumer không kết nối; khi consumer sau này mở lại, nó có thể nhận backlog. Một non-durable subscription vừa đóng không tiếp tục nhận message mới chỉ vì topic/address còn tồn tại.

**Phân biệt “queue durable” với “message persistent”:** Queue bền vững là về **lifecycle của queue**. **DeliveryMode.PERSISTENT** là yêu cầu độ bền của message theo hợp đồng JMS và cấu hình broker. Để khôi phục backlog qua restart, cần thiết kế cả queue, message, storage và chính sách hạn lưu phù hợp. Trong mọi trường hợp, PERSISTENT không tự sinh một subscription mới cho một client chưa đăng ký.

### Kiểm tra qua restart

Một phép thử tốt:

1. Tạo address cùng ba **durable queues** như mục 4.
2. Publish một message persistent có **eventId** riêng.
3. **Không chạy consumer** trên **audit.events**; cho Inventory và Billing xử lý phần của họ.
4. Restart broker **mà vẫn giữ đúng journal/storage**, không xóa volume dữ liệu.
5. Mở consumer **audit.events** và nhận lại message còn chờ.

Kết quả dự kiến: Audit có thể nhận backlog bền vững của chính queue Audit. Thử nghiệm này không chứng minh replay cho một **non-durable subscriber được tạo sau khi publish** — đó là hai cơ chế khác nhau.

## 11. Bảo mật và quản trị queue MULTICAST

Khi nhiều ứng dụng dùng chung **orders.events**, cần kiểm soát **ai được publish** và **ai được consume từng queue**. Có user đăng nhập thành công không có nghĩa được quyền gửi/nhận mọi destination.

Quyền có thể liên quan tới:

- **send** trên address cho producer.
- **consume** trên queue/subscription của từng dịch vụ.
- **browse** để giám sát mà không tiêu thụ.
- **createDurableQueue**, **createNonDurableQueue**, **deleteDurableQueue**, **deleteNonDurableQueue** cho subscriber động nếu cho phép.
- **manage** cho quản trị viên, hạn chế cấp cho ứng dụng thông thường.

Ví dụ minh họa **security-setting** theo address, đặt bên trong phần security-settings của broker với các **role đã được tạo**:

~~~xml
<security-setting match="orders.events">
    <permission type="send" roles="orders_publisher"/>
    <permission type="consume" roles="orders_consumers"/>
    <permission type="browse" roles="orders_observer"/>
</security-setting>
~~~

Đây chỉ là mô hình quyền tối thiểu theo address; **chưa cô lập** Inventory khỏi Billing nếu cả hai cùng có role **orders_consumers**. Muốn tách quyền ở cấp queue, cần thiết kế chính sách áp dụng cho **FQQN** hoặc cơ chế phân quyền tương ứng trên release Artemis triển khai, rồi kiểm thử bằng từng user. Không dán đè một cấu hình security rộng hơn hoặc mặc định broker khi chưa đánh giá đầy đủ tác động.

### Rủi ro tự tạo queue tràn lan

Nếu producer hoặc client tùy ý tạo durable subscriptions/queues, một MULTICAST address có thể xuất hiện rất nhiều queue có backlog không ai xử lý. Mỗi queue phù hợp làm tăng số bản phân phối logic cần quản lý. Giới hạn quyền create queue, dùng tên subscription rõ chủ sở hữu, theo dõi queue không có consumer kéo dài và thiết lập quy trình xóa queue an toàn.

Không xóa queue đang còn message nghiệp vụ mà chưa có chính sách chuyển giao/replay. Cũng không dùng **auto-delete-queues** thiếu kiểm soát để “dọn” mọi queue khi service tạm offline, vì có thể làm mất backlog mà durable subscriber cần giữ.

## 12. Các lỗi thường gặp khi kiểm chứng multicast

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra |
| --- | --- | --- |
| Publish thành công nhưng chỉ một dịch vụ nhận | Có một queue/ANYCAST hoặc hai consumer cùng queue tranh nhau message | Kiểm tra address, routing type và tên queue mà từng client consume |
| Consumer dùng đúng address nhưng không thấy message | Đọc queue sai hoặc không dùng FQQN | Kiểm tra **orders.events::queueName** |
| **billing.paid** không nhận OrderPaid | Producer thiếu JMS property **eventType**, sai kiểu/chữ hoa hoặc filter không khớp | Đọc message properties và queue filter thực tế |
| **billing.paid** nhận cả OrderPlaced | Filter chưa được áp dụng trên queue đang dùng, hoặc queue tồn tại từ config cũ | Kiểm tra binding/filter của queue trong broker, không chỉ file cấu hình nguồn |
| Một queue đã ACK, queue kia còn backlog | Hành vi MULTICAST độc lập bình thường | Quan sát message count và consumer của từng queue |
| Queue mới không nhận các event cũ | Queue được tạo sau thời điểm publish | Dùng event replay/outbox nếu cần dữ liệu lịch sử |
| Backlog còn sau consumer restart | Queue durable vẫn tồn tại và message chưa ACK | Đúng kỳ vọng; kiểm tra TTL, journal và consumer state |
| Backlog biến mất khi consumer đóng | Có thể đang dùng non-durable subscription/auto-delete queue | Xác định lifecycle của subscription queue |
| Message phát lặp sau rollback | At-least-once delivery; transaction chưa ACK | Kiểm tra redelivery, idempotency và retry policy |
| Publish bị chậm hoặc bị chặn khi một queue ngừng xử lý | Storage/paging/address limits hoặc flow control ảnh hưởng chung | Quan sát queue size, journal, disk, address policy và producer latency |
| Một consumer nhận message của “lần test cũ” | Queue durable vẫn giữ backlog từ lần trước | Dùng selector **labRun** hoặc reset **queue test** có chủ đích |

### Chẩn đoán theo đúng trật tự routing

Khi thấy “producer đã gửi nhưng Billing không nhận”, kiểm tra từ trên xuống:

1. Producer gửi đến **đúng address** chưa? Destination thực tế là **JMS Topic** hay nhầm thành JMS Queue?
2. Message mang **MULTICAST routing type** chưa? Address có binding MULTICAST tương ứng không?
3. **billing.paid** đã tồn tại **trước lúc gửi** và bind đúng address chưa?
4. Queue filter có chấp nhận **eventType** và các properties khác không?
5. Queue có message pending/in-flight hay đã được consumer nào ACK?
6. User của consumer có quyền consume đúng FQQN và đang kết nối đúng broker không?
7. Message có thể đã **expired, redelivered hoặc chuyển DLQ** theo policy không?

Không kết luận “Artemis chỉ phát một bản” từ việc quan sát một JMS listener; hãy kiểm tra **cấu trúc queue bindings** trước.

## 13. Thí nghiệm nâng cao để hiểu fan-out

### Thí nghiệm A — Hai consumer cùng một queue

Khởi chạy hai instance **Inventory** cùng đọc **orders.events::inventory.events**. Publish 20 event có eventId khác nhau. Kiểm tra tổng message được ACK trên cả hai instance, và xác minh mỗi event bình thường được xử lý bởi một instance trong queue đó, không phải hai. Đối chiếu với **audit.events**: Audit có bản phân phối riêng của 20 event.

### Thí nghiệm B — Một queue chậm, một queue nhanh

Tạm dừng consumer Audit, giữ Inventory đang hoạt động. Publish 50 event OrderPlaced. Queue **audit.events** tích lũy 50 bản phân phối nếu không có filter/TTL khác; Inventory có thể ACK các bản phân phối của mình. Mở Audit sau và kiểm tra eventIds, độ trễ oldest-message. Theo dõi hạn mức tài nguyên nếu tăng lưu lượng.

### Thí nghiệm C — Thay filter

Tạo queue **shipping.created** dưới MULTICAST address với filter **eventType = 'OrderPlaced'**. Publish hỗn hợp **OrderPlaced** và **OrderPaid**. Chứng minh queue này chỉ nhận event phù hợp; nếu thêm queue sau khi gửi một batch thì batch trước không được hồi tố.

### Thí nghiệm D — Đếm bản phân phối khi thay số queue

Từ một address có hai queue không filter, tăng thành bốn queue không filter, publish cùng **N** message ở mỗi cấu hình. So sánh số message references/enqueues trên tất cả queue (không nhầm với số lời gọi send). Thảo luận chi phí storage/dispatch và nguy cơ backlog tăng khi thêm consumer group.

### Thí nghiệm E — ACK độc lập và replay an toàn

Publish một **OrderPaid** vào hai queue. Consumer A commit JMS sau khi ghi database; consumer B rollback có chủ đích một lần. Kiểm tra việc B được redeliver theo policy mà A không bị phát lại chỉ vì B thất bại. Nếu B đã commit side effect rồi mất JMS commit, dùng eventId làm idempotency key trước khi retry để không tạo thay đổi nghiệp vụ hai lần.

## 14. Tự kiểm tra thiết kế

Một thiết kế multicast Artemis đúng cần trả lời rõ:

| Câu hỏi | Câu trả lời phải có |
| --- | --- |
| Producer gửi đến đâu? | Một **address** cụ thể, ví dụ orders.events |
| Đường đi là MULTICAST thật chưa? | Message routing type phù hợp và có queue binding MULTICAST |
| Ai cần bản phân phối độc lập? | Mỗi **consumer group** cần một queue riêng; các replica cùng nhóm dùng chung queue |
| Message nào được đưa vào queue? | Queue filter và JMS properties xác định được |
| Khi service offline có giữ backlog không? | Queue/subscription lifecycle, durability, TTL, persistence và retention |
| Khi một service ACK thì service khác ra sao? | ACK/rollback riêng trên từng queue |
| Khi thêm consumer group mới thì nhận dữ liệu từ lúc nào? | Từ khi queue/subscription được tạo và nhận routing; replay quá khứ cần thiết kế riêng |
| Khi backlog của một queue lớn lên? | Có metrics, quota, paging, cảnh báo và quy trình xử lý |
| Ai được phép send/consume/create/delete? | Security roles và quyền theo address/queue |

Cốt lõi của **MULTICAST trong Artemis** là **một message gửi tới address có thể sinh nhiều bản phân phối logic độc lập**, mỗi bản thuộc về **một queue phù hợp**. Queue là đơn vị lưu chờ, giao lại và ACK; consumer chỉ làm việc trên queue đã chọn. Cách nhìn này giải thích chính xác cả fan-out, filter, offline backlog, tách tiến độ xử lý và chi phí vận hành khi số lượng subscription queue tăng.
