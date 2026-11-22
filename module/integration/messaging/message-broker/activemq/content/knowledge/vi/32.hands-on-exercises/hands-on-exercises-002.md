# So sánh fan-out bằng Topic Classic, Virtual Topic và multicast Artemis

> **Chương:** Bài tập tổng hợp  
> **Mục tiêu:** Gửi cùng một event tới nhiều hệ thống và kiểm chứng ba cách tổ chức subscription: JMS Topic trên ActiveMQ Classic, Virtual Topic của Classic và JMS Topic được Artemis triển khai bằng multicast queues. Bài dùng Java 17, Jakarta Messaging, JUnit 5 và hai broker chạy độc lập.

## 1. Bài toán và kết quả cần chứng minh

Order Service phát event OrderConfirmed. Billing và Analytics đều cần nhận event; mỗi hệ thống lại có nhiều instance để tăng khả năng xử lý.

Yêu cầu:

- Giữa các hệ thống: một bản cho Billing và một bản cho Analytics.
- Trong cùng hệ thống: nhiều worker cạnh tranh cùng một queue để chia việc; không phải mỗi worker nhận một bản.
- Billing offline không làm mất backlog nếu queue/subscription bền vững đã tồn tại và message được gửi persistent.
- Producer chỉ biết destination logic, không cần biết số worker của từng hệ thống.

~~~text
                    Order Service
                          |
                     OrderConfirmed
                          |
              +-----------+-----------+
              |                       |
          Billing group           Analytics group
          +---------+              +---------+
          |         |              |         |
       worker A  worker B        worker A  worker B
       (share one queue)         (share one queue)
~~~

Khi hoàn thành, dùng eventId chứng minh mỗi group nhận được một bản, worker trong cùng group không cùng nhận một marker, và subscription/destination có đúng vòng đời khi consumer ngắt kết nối.

## 2. Chuẩn bị broker

### 2.1. Endpoint lab

| Broker | Phiên bản tham chiếu | JMS endpoint | Vai trò |
|---|---|---|---|
| ActiveMQ Classic | 6.4.0 | tcp://127.0.0.1:61616 | Topic và Virtual Topic |
| Apache Artemis | 2.57.0 | tcp://127.0.0.1:61617 | Topic/multicast |

Hai broker phải chạy độc lập, không dùng chung data directory. Đảm bảo user lab có quyền tạo destination, gửi và nhận message. Chỉ chạy bài trên broker lab, không dùng queue nghiệp vụ.

### 2.2. Classic: bật Virtual Topic interceptor

Trong conf/activemq.xml đang được broker sử dụng, thêm fragment bên trong phần tử broker hiện hữu. Nếu đã có destinationInterceptors, ghép interceptor vào phần tử đó thay vì tạo phần tử trùng:

~~~xml
<destinationInterceptors>
    <virtualDestinationInterceptor>
        <virtualDestinations>
            <virtualTopic
                name="VirtualTopic.>"
                prefix="Consumer.*."
                selectorAware="false"/>
        </virtualDestinations>
    </virtualDestinationInterceptor>
</destinationInterceptors>
~~~

Quy ước tương ứng:

~~~text
Producer Topic:
    VirtualTopic.Orders

Billing queue:
    Consumer.Billing.VirtualTopic.Orders

Analytics queue:
    Consumer.Analytics.VirtualTopic.Orders
~~~

Queue cần tồn tại trước khi producer gửi để nhận bản fan-out. Consumer kết nối tới queue sẽ làm broker tạo queue theo quy ước Virtual Topic; cũng có thể provision queue trước. Persistent message có thể tồn trong queue khi worker offline. selectorAware=false giữ phép thử độc lập với selector đang hoạt động; không bật selectorAware=true nếu chưa đánh giá selector cache và hành vi consumer reconnect.

Khởi động lại Classic và xác nhận interceptor đã được nạp trước khi chạy test.

### 2.3. Artemis: cấu hình multicast Topic

Trong etc/broker.xml, thêm address sau bên trong addresses hiện hữu:

~~~xml
<addresses>
    <address name="lab.orders">
        <multicast/>
    </address>
</addresses>
~~~

JMS Topic lab.orders được biểu diễn bằng address cùng tên. Mỗi subscription tạo một multicast queue. Queue của non-durable subscription thường có tên UUID và được dọn theo vòng đời subscription; durable subscription queue được đặt tên theo clientID và subscription name. Nếu publish khi chưa có subscription queue, message có thể bị drop theo semantics multicast.

Để thử mô hình queue cố định cho từng group (gần với Virtual Topic), có thể thêm address riêng:

~~~xml
<address name="lab.orders.groups">
    <multicast>
        <queue name="billing.lab.orders.groups">
            <durable>true</durable>
        </queue>
        <queue name="analytics.lab.orders.groups">
            <durable>true</durable>
        </queue>
    </multicast>
</address>
~~~

Consumer truy cập queue qua FQQN:

~~~text
lab.orders.groups::billing.lab.orders.groups
lab.orders.groups::analytics.lab.orders.groups
~~~

FQQN có dạng address::queue. Phần mở rộng này sẽ dùng ở mục 8; test Topic tự động bên dưới dùng address lab.orders để Artemis tự quản lý subscription queues.

## 3. Tạo project Java/JMS

Tạo Maven project lab với pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab.messaging</groupId>
    <artifactId>fanout-comparison</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>6.4.0</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.57.0</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Hai client dependency cùng có mặt trong project lab để chạy một bộ test. Trong ứng dụng production, quản lý provider theo BOM/module riêng và tránh trộn dependency không cần thiết.

Khai báo endpoint bằng environment variables:

~~~text
CLASSIC_URL=tcp://127.0.0.1:61616
ARTEMIS_URL=tcp://127.0.0.1:61617
JMS_USER=<lab-user>
JMS_PASSWORD=<lab-password>
~~~

Nếu broker lab không bật authentication, bỏ JMS_USER và JMS_PASSWORD; code tạo anonymous context. Không commit credential vào source hoặc pom.xml.

## 4. Mã kiểm thử chung

Tạo src/test/java/lab/messaging/FanoutComparisonTest.java:

~~~java
package lab.messaging;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class FanoutComparisonTest {

    private static ConnectionFactory classicFactory() {
        return new org.apache.activemq.ActiveMQConnectionFactory(
            required("CLASSIC_URL"));
    }

    private static ConnectionFactory artemisFactory() {
        return new org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory(
            required("ARTEMIS_URL"));
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + key);
        }
        return value;
    }

    private static JMSContext openContext(ConnectionFactory factory) {
        String user = System.getenv("JMS_USER");
        if (user == null || user.isBlank()) {
            return factory.createContext();
        }
        return factory.createContext(user, required("JMS_PASSWORD"));
    }

    private static String newRunId() {
        return UUID.randomUUID().toString().replace("-", "");
    }

    private static void publish(JMSContext producerContext,
                                String topicName, String runId) throws Exception {
        Topic topic = producerContext.createTopic(topicName);
        TextMessage message =
            producerContext.createTextMessage("ORDER_CONFIRMED");
        message.setStringProperty("runId", runId);
        message.setStringProperty("eventId", "evt-" + runId);
        producerContext.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT)
            .send(topic, message);
    }

    private static void assertEvent(Message message, String runId)
            throws Exception {
        assertNotNull(message, "No message received before timeout");
        assertEquals(runId, message.getStringProperty("runId"));
        assertEquals("evt-" + runId, message.getStringProperty("eventId"));
        assertEquals("ORDER_CONFIRMED", ((TextMessage) message).getText());
    }

    // Hai Topic consumers là hai subscription độc lập.
    // Đăng ký cả hai trước khi publish.
    private static void topicFanout(ConnectionFactory factory,
                                    String topicName) throws Exception {
        String runId = newRunId();
        try (JMSContext billingContext = openContext(factory);
             JMSContext analyticsContext = openContext(factory);
             JMSContext producerContext = openContext(factory);
             JMSConsumer billing = billingContext.createConsumer(
                 billingContext.createTopic(topicName));
             JMSConsumer analytics = analyticsContext.createConsumer(
                 analyticsContext.createTopic(topicName))) {

            billingContext.start();
            analyticsContext.start();
            publish(producerContext, topicName, runId);

            assertEvent(billing.receive(5_000L), runId);
            assertEvent(analytics.receive(5_000L), runId);
        }
    }

    // Mỗi logical group có một queue riêng. Hai Billing workers
    // cạnh tranh trên cùng queue; Analytics đọc queue khác.
    private static void queueGroupFanout(ConnectionFactory factory,
                                         String topicName,
                                         String billingQueueName,
                                         String analyticsQueueName)
            throws Exception {
        String runId = newRunId();
        try (JMSContext billingAContext = openContext(factory);
             JMSContext billingBContext = openContext(factory);
             JMSContext analyticsContext = openContext(factory);
             JMSContext producerContext = openContext(factory);
             JMSConsumer billingA = billingAContext.createConsumer(
                 billingAContext.createQueue(billingQueueName));
             JMSConsumer billingB = billingBContext.createConsumer(
                 billingBContext.createQueue(billingQueueName));
             JMSConsumer analytics = analyticsContext.createConsumer(
                 analyticsContext.createQueue(analyticsQueueName))) {

            billingAContext.start();
            billingBContext.start();
            analyticsContext.start();
            publish(producerContext, topicName, runId);

            Message fromBillingA = billingA.receive(5_000L);
            Message fromBillingB = billingB.receive(300L);
            assertNotEquals(fromBillingA == null, fromBillingB == null,
                "Exactly one Billing worker must receive this queue message");
            assertEvent(fromBillingA != null ? fromBillingA : fromBillingB,
                runId);
            assertEvent(analytics.receive(5_000L), runId);
        }
    }

    @Test
    void classicTopicCopiesToBothActiveSubscriptions() throws Exception {
        topicFanout(classicFactory(), "lab.orders.topic");
    }

    @Test
    void classicVirtualTopicFansOutToGroupQueues() throws Exception {
        String suffix = newRunId();
        String topic = "VirtualTopic.Orders." + suffix;
        String billingQueue =
            "Consumer.Billing-" + suffix + "." + topic;
        String analyticsQueue =
            "Consumer.Analytics-" + suffix + "." + topic;

        queueGroupFanout(classicFactory(), topic, billingQueue, analyticsQueue);
    }

    @Test
    void artemisTopicMulticastCopiesToBothSubscriptions() throws Exception {
        topicFanout(artemisFactory(), "lab.orders");
    }
}
~~~

Chạy các test bằng Maven:

~~~text
mvn -q test
~~~

topicFanout xác minh hai subscription độc lập đều nhận cùng eventId. queueGroupFanout xác minh hai queue nhóm nhận bản riêng, trong khi hai Billing consumers cạnh tranh trên một queue nên chỉ một worker nhận marker. Producer dùng persistent delivery mode; việc giữ message khi subscriber offline còn phụ thuộc queue/subscription đã tồn tại và có durability phù hợp.

Các test giả định broker lab đang chạy, user được phép tạo destination và không có ứng dụng khác tiêu thụ queue lab. Test Virtual Topic tạo queue có suffix riêng theo lần chạy để tránh đọc nhầm backlog lần trước.

## 5. Thực hành A — JMS Topic thông thường trên Classic

1. Khởi động broker Classic.
2. Chạy test classicTopicCopiesToBothActiveSubscriptions.
3. Quan sát Web Console/JMX: Topic lab.orders.topic có hai subscriber đang hoạt động.
4. Xác nhận Billing và Analytics nhận cùng runId.
5. Sau khi JMS contexts đóng, non-durable subscriptions kết thúc; không có queue group độc lập để giữ backlog offline.

Kết quả mong đợi:

| Quan sát | Kết quả |
|---|---|
| Producer gửi một message lên Topic | Thành công |
| Billing subscription | Nhận một bản |
| Analytics subscription | Nhận một bản |
| Hai subscription độc lập | Mỗi subscription có bản riêng |
| Nhiều worker trong cùng group | Chưa được mô phỏng bằng hai subscription độc lập |

**Thử nghiệm offline:** đóng cả hai subscriber rồi gửi message mới lên Topic. Tạo lại non-durable subscribers; chúng không nhận message đã gửi khi chưa đăng ký. Muốn giữ message cho subscriber offline, cần durable subscription với identity đúng. Durable Topic subscription kiểu JMS 1.1 có tính độc quyền theo clientID và subscription name.

## 6. Thực hành B — Virtual Topic trên Classic

Chạy test classicVirtualTopicFansOutToGroupQueues.

Producer gửi tới VirtualTopic.Orders.<suffix>. Consumer đọc các queue:

~~~text
Consumer.Billing-<suffix>.VirtualTopic.Orders.<suffix>
Consumer.Analytics-<suffix>.VirtualTopic.Orders.<suffix>
~~~

Kết quả mong đợi:

| Destination | Số consumer | Kết quả với một event |
|---|---:|---|
| Billing queue | 2 | Chỉ một trong hai worker nhận |
| Analytics queue | 1 | Nhận một bản độc lập |
| Producer Topic | 1 send | Broker fan-out tới hai group queues |

### 6.1. Kiểm chứng worker pool

Mở rộng test để gửi 100 event có eventId khác nhau và ghi số event nhận bởi Billing worker A/B. Không yêu cầu chia đều tuyệt đối; dispatch/prefetch có thể khiến một worker nhận nhiều hơn. Điều kiện đúng:

- Tổng event duy nhất Billing nhận bằng số event đã publish.
- Không có eventId được cả Billing A và Billing B xử lý.
- Analytics nhận đủ cùng tập eventId.
- Mỗi group có queue depth riêng; không gộp thành một subscription count.

### 6.2. Kiểm chứng backlog khi group offline

1. Tạo Billing và Analytics queues bằng cách cho consumer kết nối.
2. Đóng Billing consumers nhưng giữ queue.
3. Gửi persistent message tới Virtual Topic.
4. Dùng Web Console/JMX kiểm tra Billing queue có backlog; Analytics vẫn có thể nhận ngay.
5. Kết nối Billing worker lại và xác nhận nó nhận event đã chờ.

Virtual Topic cho phép mỗi logical subscriber group dùng queue, vì vậy một group có thể có nhiều worker cạnh tranh. Queue phải tồn tại trước thời điểm publish để nhận bản fan-out. Khi dùng destination động, xác minh queue thực tế đã được tạo; đừng giả định consumer chưa từng tồn tại đã có queue để giữ message.

### 6.3. Selector và consumer queue convention

Mặc định Classic dùng namespace VirtualTopic.> và consumer queue pattern Consumer.*.VirtualTopic.>. Nếu ứng dụng đổi prefix, postfix hoặc wildcard, phải thay cả broker interceptor và tên queue phía consumer.

- selectorAware=false: fan-out không phụ thuộc selector hiện diện tại thời điểm gửi; queue có thể giữ message mà consumer hiện tại không chọn.
- selectorAware=true: broker xét selector của consumer đang hoạt động; consumer offline có thể bỏ lỡ message nếu selector cache không được cấu hình phù hợp.

Trong bài lab giữ selectorAware=false để phép thử fan-out không bị lẫn với filter semantics.

## 7. Thực hành C — Topic multicast trên Artemis

Chạy test artemisTopicMulticastCopiesToBothSubscriptions.

Trong Artemis, JMS Topic được biểu diễn bằng address cùng tên; mỗi subscription là một multicast queue bind vào address đó. Hai consumer độc lập tạo hai subscription queues. Producer gửi một message tới Topic, broker route một bản vào từng queue.

~~~text
JMS Topic lab.orders
       |
       v
Artemis address lab.orders (MULTICAST)
       |
       +---- subscription queue Billing ----> Billing consumer
       |
       +---- subscription queue Analytics --> Analytics consumer
~~~

| Quan sát | Kết quả |
|---|---|
| Producer gửi một message tới lab.orders | Thành công |
| Billing subscription queue | Nhận một bản |
| Analytics subscription queue | Nhận một bản |
| Không có subscription queue khi publish | Message có thể bị drop |
| Hai consumer cùng shared subscription | Cạnh tranh trên một queue subscription, không tạo thêm bản |

### 7.1. Quan sát subscription queues

Trong Artemis Console/JMX/management API, kiểm tra address lab.orders và queues gắn với nó khi test chạy. Queue của non-durable subscription có thể mang tên UUID; durable subscription queue dựa trên clientID và subscription name. Sau khi non-durable consumers đóng, các subscription queues tạm được dọn theo lifecycle của chúng.

### 7.2. Tạo worker pool bằng shared subscription

JMS 2.0 cho phép nhiều consumer dùng chung một subscription. Artemis hỗ trợ shared topic subscriptions. Để mở rộng nhóm Billing mà Analytics vẫn nhận bản riêng:

~~~java
Topic billingTopic = billingAContext.createTopic("lab.orders");
Topic billingTopicB = billingBContext.createTopic("lab.orders");
Topic analyticsTopic = analyticsContext.createTopic("lab.orders");

JMSConsumer billingA =
    billingAContext.createSharedConsumer(billingTopic, "billing-workers");
JMSConsumer billingB =
    billingBContext.createSharedConsumer(billingTopicB, "billing-workers");
JMSConsumer analytics =
    analyticsContext.createConsumer(analyticsTopic);
~~~

Đăng ký/start cả ba consumers trước khi publish. Hai Billing consumers chia message thuộc subscription billing-workers; Analytics subscription riêng nhận một bản. Khi cần giữ backlog qua thời gian offline, dùng shared durable subscription với identity/lifecycle được quản lý rõ; shared non-durable không tự giữ backlog.

## 8. So sánh queue group giữa Virtual Topic và Artemis

Virtual Topic của Classic và Artemis multicast có thể biểu diễn cùng mục tiêu bằng queue riêng cho từng logical group:

| Ý niệm | Classic Virtual Topic | Artemis multicast |
|---|---|---|
| Producer endpoint | JMS Topic VirtualTopic.Orders | JMS Topic/address lab.orders.groups |
| Billing group | Consumer.Billing.VirtualTopic.Orders | billing.lab.orders.groups |
| Analytics group | Consumer.Analytics.VirtualTopic.Orders | analytics.lab.orders.groups |
| Routing | Virtual destination interceptor fan-out tới matching queues | MULTICAST route tới mọi queue bind vào address |
| Worker pool | Nhiều Queue consumers cùng queue nhóm | Nhiều consumers cùng multicast queue/FQQN |
| Offline backlog | Persistent message ở queue group đã tồn tại | Persistent message ở durable multicast queue/subscription |
| Quản lý queue | Consumer convention và interceptor | Address/queue binding, management API hoặc FQQN |

### 8.1. Bài tập mở rộng: static multicast queues + FQQN

Với fragment lab.orders.groups ở mục 2.3, producer gửi tới JMS Topic lab.orders.groups. Consumer đọc trực tiếp queue nhóm:

~~~java
Queue billingQueue = billingContext.createQueue(
    "lab.orders.groups::billing.lab.orders.groups");
Queue analyticsQueue = analyticsContext.createQueue(
    "lab.orders.groups::analytics.lab.orders.groups");

JMSConsumer billingA = billingContext.createConsumer(billingQueue);
JMSConsumer billingB = billingBContext.createConsumer(
    billingBContext.createQueue(
        "lab.orders.groups::billing.lab.orders.groups"));
JMSConsumer analytics = analyticsContext.createConsumer(analyticsQueue);
~~~

Gửi một marker lên Topic. Kỳ vọng: Billing A hoặc Billing B nhận một bản từ queue Billing; Analytics nhận bản của queue Analytics. Đây là phép thử gần nhất với Virtual Topic group queues mà không cần tự tạo durable Topic subscription identity.

Trước khi gửi, tạo các JMSContext riêng cho Billing A, Billing B, Analytics và producer; tạo consumer từ các FQQN rồi gọi start trên ba context consumer. Chạy phần mở rộng này tuần tự trên broker lab. Nếu bật parallel tests, provision queue có tên riêng theo run thay vì để nhiều test cùng đọc hai static queues này.

### 8.2. Khác biệt durability và identity

- Static Artemis multicast queue phải có durability/retention phù hợp. Queue durable không có nghĩa mọi message đều persistent; producer vẫn phải gửi persistent nếu cần lưu message.
- JMS Topic durable subscription có identity riêng. Artemis biểu diễn nó bằng subscription queue; Classic cũng lưu durable subscription nhưng giới hạn một consumer hoạt động trên một identity theo JMS 1.1.
- Artemis shared durable subscription cho phép nhiều consumers chia cùng subscription; đây là lựa chọn gần với queue worker pool.
- Classic Virtual Topic dùng queue nhóm nên có thể scale nhiều consumers trong cùng group mà không cần chia sẻ một durable Topic subscriber identity.

Không chuyển tên queue Virtual Topic sang FQQN một cách máy móc. Phải xác định address, queue binding, durability, selector, client identity và consumer group ở broker đích.

## 9. Đo và ghi bằng chứng

Với mỗi scenario, ghi:

| Bằng chứng | Cách thu thập |
|---|---|
| runId và eventId | JMS message properties và log producer/consumer |
| Số bản mỗi group nhận | Đếm event ID duy nhất ở Billing và Analytics |
| Số worker trong group | Consumer count trên queue/subscription |
| Queue backlog | Classic QueueView/JMX hoặc Artemis QueueControl |
| Subscription lifecycle | Active/inactive subscriber và queue binding trước/sau disconnect |
| Persistence | Delivery mode, durable flag, store và kết quả offline test |
| Duplicate | So sánh event ID giữa workers và groups; một event có thể xuất hiện ở nhiều group nhưng không được xử lý trùng trong cùng group |

Mẫu kết quả:

| Scenario | Billing nhận | Analytics nhận | Worker chia việc? | Backlog offline |
|---|---:|---:|---|---|
| Classic Topic, 2 active subscriptions | 1 | 1 | Chưa kiểm thử group queue | Non-durable: không giữ |
| Classic Virtual Topic, 2 Billing workers | 1 tổng trong Billing queue | 1 | Có | Có nếu queue đã tồn tại và message persistent |
| Artemis Topic multicast, 2 subscriptions | 1 | 1 | Mỗi subscription riêng | Durable subscription mới giữ offline backlog |
| Artemis static multicast queues/FQQN | 1 tổng trong Billing queue | 1 | Có | Có nếu queue durable và message persistent |

Không coi “mỗi group nhận một bản” là exactly-once end-to-end. Broker có thể redeliver khi consumer rollback/crash; consumer vẫn phải idempotent theo eventId.

## 10. Chẩn đoán khi kết quả sai

| Triệu chứng | Kiểm tra |
|---|---|
| Classic Topic chỉ một hệ thống nhận | Hai consumer có thật sự tạo hai subscription độc lập và start trước publish không? |
| Classic Virtual Topic không có queue | Interceptor đã nạp chưa? Topic có khớp VirtualTopic.> và queue có khớp Consumer.*.VirtualTopic.> không? |
| Virtual Topic chỉ Billing nhận | Analytics queue đã tồn tại trước publish chưa? Có selector/filter loại message không? |
| Cả hai Billing workers nhận cùng event | Có phải hai queue khác nhau do sai group name? Cả hai có consume cùng physical queue không? |
| Artemis Topic không fan-out | Address có routing type MULTICAST không? Subscription queues đã được tạo trước publish chưa? |
| Chỉ một consumer trong Artemis shared subscription nhận | Đây là hành vi đúng của shared subscription; không phải lỗi multicast giữa các groups |
| Artemis static queue không nhận | FQQN có đúng address::queue không? Queue có bind vào address multicast và enabled không? |
| Subscriber reconnect không thấy backlog | Subscription có durable không? clientID/subscription name có giữ nguyên không? Message có persistent không? |
| Message bị nhân đôi giữa broker | Kiểm tra bridge/network connector, fan-out ở cả hai đầu và đường forward vòng |

Nếu test thất bại sau khi publish, kiểm tra backlog ở các queue lab trước khi chạy lại. Chỉ purge/delete queue lab khi xác nhận đúng owner và không có test khác đang dùng. Không dùng purge để xử lý queue nghiệp vụ.

## 11. Bài nộp và tiêu chí đạt

Nộp bảng so sánh kèm log/ảnh chụp metrics chứng minh:

1. Classic Topic: hai non-durable subscribers cùng nhận một event.
2. Classic Virtual Topic: Billing và Analytics nhận bản độc lập; hai Billing workers cạnh tranh cùng queue.
3. Artemis multicast Topic: mỗi subscription queue nhận một bản; shared subscription cho phép worker pool trong một group.
4. Artemis static multicast + FQQN (phần mở rộng): queue nhóm tương ứng Virtual Topic hoạt động đúng.
5. Subscriber offline: ghi rõ trường hợp nào giữ backlog và điều kiện durability cần có.
6. Event ID chứng minh không có duplicate trong cùng group; có ghi chú redelivery/idempotency.

Checklist:

- [ ] Đã cấu hình và chạy được cả hai broker lab.
- [ ] Producer dùng đúng Topic; consumer dùng đúng subscription hoặc queue group.
- [ ] Hai hệ thống nhận được bản độc lập.
- [ ] Hai worker trong cùng group chia message, không cùng nhận một marker.
- [ ] Đã phân biệt non-durable Topic subscription với durable subscription/queue.
- [ ] Đã xác minh Virtual Topic interceptor và consumer queue convention của Classic.
- [ ] Đã xác minh Artemis Topic ánh xạ thành address MULTICAST và queue per subscription.
- [ ] Đã thử shared subscription hoặc FQQN queue group trên Artemis.
- [ ] Có runId/eventId và metrics làm bằng chứng; không chỉ dựa vào log “send OK”.
- [ ] Queue/subscription lab được kiểm tra và dọn đúng phạm vi sau khi hoàn tất.

**Kết luận:** Classic Topic tạo một bản cho mỗi subscription đang hoạt động; Virtual Topic thêm queue riêng cho từng logical consumer group để worker trong nhóm cạnh tranh; Artemis triển khai Topic bằng multicast address với queue cho từng subscription, và có thể dùng shared subscription hoặc static multicast queue/FQQN để tạo worker pool. Điểm cần so sánh không chỉ là số bản fan-out mà còn là **identity subscription, vòng đời queue, backlog offline và cách scale consumer trong cùng nhóm**.

## Tài liệu chính thức

1. [ActiveMQ Classic — Virtual Destinations](https://activemq.apache.org/components/classic/documentation/virtual-destinations): Virtual Topic, consumer queue convention, selector-aware và tránh duplicate qua network of brokers.
2. [Apache Artemis 2.57.0 — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): address, queue, routing type ANYCAST/MULTICAST, subscription queues và FQQN.
3. [Apache Artemis 2.57.0 — Mapping JMS Concepts to the Core API](https://artemis.apache.org/components/artemis/documentation/latest/jms-core-mapping.html): JMS Topic ánh xạ sang address và multicast queue cho từng subscription.
4. [Apache Artemis Migration Guide — Virtual Topics](https://artemis.apache.org/components/artemis/migration-documentation/VirtualTopics.html): Virtual Topic Classic, JMS shared subscription và FQQN của Artemis.
5. [Apache ActiveMQ Classic — Download](https://activemq.apache.org/components/classic/download/): phiên bản broker/client và ma trận Jakarta JMS.
6. [Apache Artemis — Download](https://artemis.apache.org/components/artemis/download/): phiên bản broker/client và Java compatibility.
