# Ánh xạ Queue, Topic, Virtual Topic sang mô hình đích

> **Chương:** Di chuyển broker  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ bằng queue, topic, routing và JMS; thực hành producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi:** Ánh xạ destination từ ActiveMQ Classic sang Apache ActiveMQ Artemis. Trọng tâm là giữ đúng **ngữ nghĩa giao nhận** khi chuyển Queue, Topic và Virtual Topic; tên destination giống nhau không có nghĩa semantics tự động giống nhau.

## 1. Bắt đầu từ ngữ nghĩa, không bắt đầu từ tên destination

Một hệ thống Classic có ba loại luồng:

- **Orders.Command:** queue cho một worker pool xử lý lệnh; mỗi message được một consumer trong pool nhận.
- **Orders.Events:** topic cho billing, analytics và audit cùng nhận một sự kiện.
- **VirtualTopic.OrderConfirmed:** producer publish một lần; mỗi nhóm consumer nhận một bản riêng qua queue có dạng **Consumer.<group>.VirtualTopic.OrderConfirmed**.

Khi chuyển sang Artemis, mục tiêu là bảo toàn các hợp đồng này. Nếu chỉ tạo destination cùng tên, có thể gặp các lỗi khó phát hiện:

- Topic bị tạo thành ANYCAST queue, khiến các subscriber cạnh tranh nhau thay vì mỗi subscriber nhận một bản.
- Virtual Topic bị chuyển thành topic thuần, làm mất queue backlog riêng và competing-consumer group.
- Một queue bị tạo thành MULTICAST, làm mỗi consumer nhận một bản thay vì chia tải.
- Durable subscription bị đổi client ID/name, khiến broker tạo subscription mới và backlog cũ nằm lại.
- Queue filter/selector khác nhau, làm message bị bỏ khỏi luồng mong đợi.
- DLQ hoặc expiry policy thay đổi, làm message lỗi bị chuyển tới nơi khác hoặc hết hạn sớm.

**Nguyên tắc ánh xạ:** trước hết xác định ai phải nhận message, bao nhiêu bản giao cần tồn tại, message phải được giữ khi consumer offline đến mức nào và consumer nào được phép cạnh tranh trên cùng backlog. Sau đó mới chọn address, routing type và queue ở Artemis.

~~~mermaid
flowchart TD
    A["Classic destination inventory"] --> B{"Delivery contract"}
    B -->|"One worker gets each message"| Q["Artemis ANYCAST address + queue"]
    B -->|"Each subscriber gets a copy"| T["Artemis MULTICAST address + subscriptions"]
    B -->|"Each consumer group gets a copy"| V["MULTICAST address + one queue per group"]
    Q --> C["Map ACL, selectors, DLQ, expiry"]
    T --> C
    V --> C
    C --> D["Provision + client mapping + cutover tests"]
~~~

## 2. Lập inventory Classic trước khi chuyển

Destination name chỉ là một phần dữ liệu cần thu thập. Với mỗi destination, ghi rõ:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Loại | Queue, Topic hay Virtual Topic? |
| Producer | Ứng dụng nào publish/send? Giao thức nào? |
| Consumer | Consumer đơn, competing pool hay nhiều subscriber độc lập? |
| Durability | Message persistent? Topic subscription durable? |
| Offline behavior | Consumer offline thì message được giữ ở đâu và bao lâu? |
| Selector | Có selector ở consumer/subscription không? Property nào được lọc? |
| Ordering | FIFO toàn queue, theo group hay không có cam kết thứ tự? |
| Redelivery | Max attempts, delay, backoff và poison-message handling? |
| DLQ/expiry | Dead-letter destination và expiry destination nào? |
| Security | User/role nào send, consume, browse, create hoặc delete? |
| Volume | Message/s, size p95, peak backlog, retention và số subscription? |
| Ownership | Team nào sở hữu destination và chịu trách nhiệm cutover? |

### 2.1. Phân biệt Queue, Topic và Virtual Topic trong Classic

| Classic pattern | Cách producer gửi | Cách consumer nhận | Delivery contract |
|---|---|---|---|
| Queue Orders.Command | Gửi vào queue | Nhiều consumer cùng đọc queue | Một delivery được một consumer xử lý; competing consumers chia tải |
| Topic Orders.Events | Publish topic | Mỗi subscription nhận message phù hợp | Một publish có thể tạo một delivery cho từng subscriber |
| Virtual Topic VirtualTopic.OrderConfirmed | Publish topic VirtualTopic.* | Consumer đọc queue Consumer.<group>.VirtualTopic.* | Mỗi group có backlog riêng; consumer trong cùng group cạnh tranh nhau |

### 2.2. Virtual Topic Classic thực sự làm gì?

Virtual Topic kết hợp mô hình publish/subscribe với queue cho từng consumer group. Ví dụ:

~~~text
Producer
   |
   | publish Topic: VirtualTopic.OrderConfirmed
   v
Classic broker
   |
   +--> Queue: Consumer.Billing.VirtualTopic.OrderConfirmed
   |       +--> billing-worker-1
   |       +--> billing-worker-2       (competing consumers)
   |
   +--> Queue: Consumer.Analytics.VirtualTopic.OrderConfirmed
   |       +--> analytics-worker-1
   |
   +--> Queue: Consumer.Audit.VirtualTopic.OrderConfirmed
           +--> audit-worker-1
           +--> audit-worker-2          (competing consumers)
~~~

Billing, analytics và audit đều nhận bản riêng. Hai billing workers chia nhau queue billing; analytics không cạnh tranh với billing. Đây là điểm cần bảo toàn khi chuyển broker.

Tên **Consumer.Billing.VirtualTopic.OrderConfirmed** là một queue destination thực trong mô hình Classic, không phải tên của một durable topic subscription. Consumer group được thể hiện bằng queue prefix và có queue backlog riêng.

### 2.3. Kiểm tra Virtual Topic interceptor đang dùng

Classic thường cấu hình Virtual Topic qua destination interceptor, ví dụ:

~~~xml
<destinationInterceptors>
    <virtualDestinationInterceptor>
        <virtualDestinations>
            <virtualTopic name="VirtualTopic.>"
                         prefix="Consumer.*."/>
        </virtualDestinations>
    </virtualDestinationInterceptor>
</destinationInterceptors>
~~~

Đây là fragment cần hợp nhất với cấu hình activemq.xml hiện hữu và xác minh theo release/configuration thực tế. Có thể hệ thống đã tùy chỉnh prefix, wildcard hoặc destination policy. Không mặc định mọi broker đều dùng prefix Consumer.*.

Một số hệ thống còn có consumer prefix/suffix riêng, selector hoặc policy tạo queue. Hãy lấy **destination thực sự đang tồn tại** từ runtime/management, không chỉ đọc tên trong source code.

## 3. Bản đồ ánh xạ sang Artemis

Artemis tách **address** (điểm định tuyến) và **queue** (nơi giữ message reference để dispatch). Routing type quyết định một message được gửi tới một queue ANYCAST hay nhiều queue MULTICAST.

| Classic | Artemis đích | Hành vi phải giữ |
|---|---|---|
| Queue Orders.Command | Address Orders.Command, ANYCAST queue Orders.Command | Competing consumers chia một backlog |
| Topic Orders.Events | Address Orders.Events, MULTICAST; queue/subscription riêng cho subscriber | Mỗi subscription nhận một bản |
| Durable Topic subscription | MULTICAST address + durable subscription queue do JMS/provider quản lý | Cùng subscription identity phục hồi backlog |
| Virtual Topic VirtualTopic.OrderConfirmed | MULTICAST address cùng tên + một queue logic cho mỗi consumer group | Mỗi group có backlog riêng; consumers trong group cạnh tranh |
| Consumer.Billing.VirtualTopic.OrderConfirmed | Queue trên address VirtualTopic.OrderConfirmed, truy cập bằng FQQN | Billing workers cùng đọc một queue group |
| Classic DLQ | Artemis dead-letter address/queue theo policy | Message poison được giữ và điều tra đúng nơi |
| Expiry destination | Artemis expiry address/queue theo policy | Message hết hạn được định tuyến có chủ đích |

**FQQN (Fully Qualified Queue Name)** của Artemis có dạng:

~~~text
<address>::<queue>
~~~

Nó xác định queue cụ thể gắn với một address. Với Virtual Topic mapping, producer gửi vào topic/address VirtualTopic.OrderConfirmed, còn consumer đọc queue group qua FQQN:

~~~text
VirtualTopic.OrderConfirmed::Consumer.Billing.VirtualTopic.OrderConfirmed
~~~

Không dùng tên queue đơn lẻ Consumer.Billing.VirtualTopic.OrderConfirmed nếu queue được bind vào address VirtualTopic.OrderConfirmed và client cần đọc đúng queue đó; tên queue đơn lẻ có thể khiến client tìm hoặc auto-create một address khác. Dùng FQQN để nói rõ cả hai phần.

## 4. Ánh xạ Queue: Classic Queue sang Artemis ANYCAST

### 4.1. Semantics cần bảo toàn

Classic Queue thường có một backlog logic; nhiều consumer nhận message theo competing-consumer semantics. Một message được giao cho một consumer tại một thời điểm, và sau ACK/commit nó không còn chờ consumer khác.

Artemis biểu diễn mô hình này bằng address có routing type ANYCAST và queue. Nếu chỉ có một queue cùng tên, có thể khai báo:

~~~xml
<addresses>
    <address name="Orders.Command">
        <anycast>
            <queue name="Orders.Command"/>
        </anycast>
    </address>
</addresses>
~~~

Đây là fragment cho phần addresses trong broker.xml; hợp nhất vào cấu hình hiện hữu, không tạo thêm phần tử trùng. Nếu queue được provision qua management/CLI hoặc auto-create policy, cần bảo đảm routing type thực tế là ANYCAST.

### 4.2. Producer và consumer Java

Với Jakarta JMS client của Artemis:

~~~java
Queue queue = context.createQueue("Orders.Command");

context.createProducer()
       .setDeliveryMode(DeliveryMode.PERSISTENT)
       .send(queue, message);
~~~

Consumer trong worker pool:

~~~java
Queue queue = context.createQueue("Orders.Command");

try (JMSConsumer consumer = context.createConsumer(queue)) {
    Message message = consumer.receive(5000);
    if (message != null) {
        // Xử lý nghiệp vụ và ACK theo session/transaction policy.
    }
}
~~~

Nhiều consumer tạo consumer trên cùng queue Orders.Command sẽ chia tải. Không tạo một multicast queue cho mỗi worker nếu mong muốn của hệ thống là competing consumers; điều đó biến một bản giao thành nhiều bản giao.

### 4.3. Queue có selector

Classic consumer có thể dùng JMS selector trên message properties. Artemis cũng hỗ trợ selector, nhưng phải giữ đúng property names/types và kiểm thử các message không match.

~~~java
JMSConsumer consumer = context.createConsumer(
        context.createQueue("Orders.Command"),
        "tenant = 'acme' AND commandType = 'capture'");
~~~

Selector không tạo quota hoặc backlog riêng cho tenant. Nếu từng tenant có retention/SLA/ACL riêng, hãy cân nhắc queue riêng thay vì gom tất cả vào một queue và dựa hoàn toàn vào selector.

## 5. Ánh xạ Topic: Classic Topic sang Artemis MULTICAST

### 5.1. Semantics của topic

Classic Topic phân phối event tới các subscription phù hợp. Mỗi subscriber có delivery độc lập. Một subscriber chậm không được phép làm subscriber khác ACK thay cho nó.

Artemis dùng address MULTICAST. Mỗi subscription tương ứng với queue riêng; với durable subscription, queue subscription được giữ qua thời gian subscriber offline theo policy của broker.

~~~xml
<addresses>
    <address name="Orders.Events">
        <multicast/>
    </address>
</addresses>
~~~

Producer gửi tới JMS Topic:

~~~java
Topic topic = context.createTopic("Orders.Events");

context.createProducer()
       .setDeliveryMode(DeliveryMode.PERSISTENT)
       .send(topic, event);
~~~

Mỗi subscription phù hợp nhận bản riêng. Không ánh xạ topic sang ANYCAST: nếu nhiều subscriber cùng đọc một ANYCAST queue, họ sẽ cạnh tranh nhau và mỗi event không còn được broadcast tới tất cả subscriber.

### 5.2. Non-durable và durable subscription

| Loại | Subscriber offline | Dữ liệu cần giữ |
|---|---|---|
| Non-durable | Không có backlog dài hạn cho subscriber đã ngừng | Chỉ message khi subscription hoạt động |
| Durable | Message phù hợp có thể được giữ trong subscription queue | Subscription identity và message persistence |
| Shared durable | Nhiều consumer chia sẻ một subscription theo JMS/provider semantics | Cần test concurrency, ordering và ownership |

Với durable subscription, clientID và subscriptionName phải ổn định theo hợp đồng. Không dùng Pod name/UUID mới mỗi lần deploy nếu muốn phục hồi đúng subscription. Đóng consumer không giống unsubscribe; thao tác unsubscribe có thể xóa subscription và backlog.

### 5.3. Ví dụ durable consumer Jakarta JMS

~~~java
try (JMSContext context = factory.createContext(
        user, password, JMSContext.SESSION_TRANSACTED)) {
    context.setClientID("billing-service");
    Topic topic = context.createTopic("Orders.Events");

    try (JMSConsumer consumer = context.createDurableConsumer(
            topic,
            "billing-v1",
            "eventType = 'invoice.created'",
            false)) {
        Message message = consumer.receive(5000);
        if (message != null) {
            // Xử lý nghiệp vụ, sau đó commit transaction JMS.
            context.commit();
        }
    }
}
~~~

Client ID phải được thiết lập trước khi tạo consumer. Đóng consumer/context không unsubscribe durable subscription. Với Classic client cũ có thể dùng namespace javax.jms; Artemis Jakarta client dùng jakarta.jms. Không trộn hai namespace trong cùng một ứng dụng.

Khi chuyển subscription, kiểm kê cả client ID, subscription name, selector, noLocal và durable/shared mode. Nếu selector thay đổi, cân nhắc version subscription mới và drain backlog cũ trước khi retire.

## 6. Ánh xạ Virtual Topic: MULTICAST address + queue cho từng group

Đây là phần cần chú ý nhất khi di chuyển từ Classic sang Artemis.

### 6.1. Ví dụ source và target

Classic producer:

~~~java
Topic virtualTopic = session.createTopic(
        "VirtualTopic.OrderConfirmed");
producer.send(virtualTopic, message);
~~~

Classic consumer group Billing:

~~~java
Queue billingQueue = session.createQueue(
        "Consumer.Billing.VirtualTopic.OrderConfirmed");
MessageConsumer billingConsumer =
        session.createConsumer(billingQueue);
~~~

Artemis giữ producer topic name, tạo MULTICAST address và queue cho từng group:

~~~xml
<addresses>
    <address name="VirtualTopic.OrderConfirmed">
        <multicast>
            <queue name="Consumer.Billing.VirtualTopic.OrderConfirmed"/>
            <queue name="Consumer.Analytics.VirtualTopic.OrderConfirmed"/>
            <queue name="Consumer.Audit.VirtualTopic.OrderConfirmed"/>
        </multicast>
    </address>
</addresses>
~~~

Producer publish tới VirtualTopic.OrderConfirmed. Artemis tạo một queue reference cho từng group queue được cấu hình. Consumer Billing đọc đúng queue qua FQQN:

~~~java
Queue billingGroup = context.createQueue(
        "VirtualTopic.OrderConfirmed"
        + "::Consumer.Billing.VirtualTopic.OrderConfirmed");

JMSConsumer consumer = context.createConsumer(billingGroup);
~~~

Analytics và Audit dùng FQQN tương ứng. Nhiều Billing worker cùng đọc **một FQQN** để chia tải; chúng không tạo thêm queue mới cho từng worker.

### 6.2. Mô hình routing sau chuyển đổi

~~~mermaid
flowchart TD
    P["Producer: Topic VirtualTopic.OrderConfirmed"] --> A["Artemis MULTICAST address"]
    A --> B["Queue Consumer.Billing..."]
    A --> C["Queue Consumer.Analytics..."]
    A --> D["Queue Consumer.Audit..."]
    B --> B1["Billing worker 1"]
    B --> B2["Billing worker 2"]
    C --> C1["Analytics worker"]
    D --> D1["Audit worker 1"]
    D --> D2["Audit worker 2"]
~~~

Kết quả:

- Một event publish được route tới mọi group queue đã khai báo.
- Billing backlog độc lập với Analytics backlog.
- Billing workers cạnh tranh trên queue Billing.
- Analytics không lấy message khỏi queue Billing.
- Subscriber group mới chỉ nhận message sau khi queue được provision; nếu cần lịch sử cũ, phải có replay/backfill riêng.

### 6.3. Vì sao không chỉ tạo một Topic subscriber cho mỗi service?

Virtual Topic queue group và durable subscription có thể cùng giữ message khi consumer offline nhưng khác cách tổ chức consumer:

- **Virtual Topic queue group:** nhiều consumer trong cùng group cạnh tranh trên một queue, có queue backlog/management riêng.
- **Unshared durable subscription:** một durable subscription có identity riêng; thường gắn với một logical subscriber.
- **Shared durable subscription:** nhiều consumer chia sẻ subscription theo JMS/provider semantics; phải kiểm tra tương thích client và ordering.

Virtual Topic thường được dùng vì muốn scale consumer theo queue semantics, tách backlog từng nhóm và không buộc mỗi instance có durable client ID riêng. Khi mapping, queue per group + FQQN là cách thể hiện trực tiếp, dễ quan sát và kiểm soát.

### 6.4. Queue group phải được provision trước hoặc tạo theo policy có kiểm soát

Đừng giả định broker tự tạo tất cả Consumer.*.VirtualTopic.* queues giống Classic interceptor. Trong Artemis, cấu hình address/queue, management API hoặc automation phải tạo đúng queue group và gắn vào multicast address. Nếu client gửi FQQN tới queue chưa tồn tại, auto-create behavior có thể tạo destination không như mong muốn hoặc trả lỗi tùy policy/version.

Với số lượng Virtual Topic/group lớn, dùng manifest/config generation có kiểm soát từ inventory. Không cho application user quyền tạo queue tùy ý nếu điều đó có thể tạo backlog hoặc destination không được giám sát.

### 6.5. Consumer group selector

Nếu Billing chỉ nhận một loại event, có thể gắn filter vào queue group:

~~~xml
<address name="VirtualTopic.OrderConfirmed">
    <multicast>
        <queue name="Consumer.Billing.VirtualTopic.OrderConfirmed">
            <filter string="eventType = 'order.confirmed'"/>
        </queue>
        <queue name="Consumer.Analytics.VirtualTopic.OrderConfirmed"/>
    </multicast>
</address>
~~~

Filter ở queue được áp dụng lúc routing vào queue group; consumer selector được áp dụng khi dispatch tới consumer. Không dùng cả hai mà không hiểu kết quả kết hợp. Kiểm thử message match/non-match và xác minh event không bị loại khỏi tất cả các queue ngoài ý muốn.

## 7. Ánh xạ selector, message group, priority và ordering

### 7.1. Selector

- Kiểm kê selector thực tế trên queue consumer và topic subscription.
- Giữ property name, type và null behavior.
- Chạy positive/negative test cho mỗi selector.
- Selector không tương đương ACL: nó lọc message, không cấp quyền truy cập.
- Nếu queue filter Artemis được dùng để route Virtual Topic group, xác minh filter không làm mất event của nhóm khác.

### 7.2. Message group

Classic và Artemis hỗ trợ message grouping qua JMSXGroupID theo semantics provider. Nếu source dùng group ID để giữ thứ tự theo order/account, giữ nguyên key format và kiểm thử:

~~~java
message.setStringProperty("JMSXGroupID", orderId);
~~~

Trong Virtual Topic, group queue là lớp phân phối giữa consumer groups; JMSXGroupID là lớp phân phối bên trong từng queue group. Hai loại “group” này khác nhau:

- Queue Consumer.Billing... phân biệt nhóm ứng dụng Billing với Analytics.
- JMSXGroupID bằng order-42 giữ các message cùng order có affinity/ordering trong queue Billing.

Không đổi group ID hoặc chuyển từ queue sang topic nếu nghiệp vụ cần thứ tự per-aggregate. Consumer vẫn cần xử lý tuần tự và idempotent; broker dispatch đúng không bảo đảm side effect DB hoàn tất theo thứ tự nếu application tự xử lý song song.

### 7.3. Priority

JMS priority nằm trong khoảng 0–9, nhưng hành vi dispatch có thể khác theo broker/version/config. Kiểm tra Classic prioritizedMessages nếu source dựa vào priority ordering; benchmark Artemis đích riêng. Không mặc định priority cao có thể preempt message đã được giao hoặc bảo đảm total ordering.

### 7.4. Ordering và concurrency

| Mô hình | Điều có thể giữ | Không nên hứa |
|---|---|---|
| Queue ANYCAST một consumer | Thứ tự dispatch trong điều kiện cấu hình bình thường | Business completion order khi async handler |
| Queue ANYCAST nhiều consumers | Competing delivery | Total processing order |
| Topic MULTICAST | Mỗi subscription có luồng delivery riêng | Ordering đồng bộ giữa mọi subscriber |
| Virtual Topic queue per group | Ordering/affinity trong từng queue theo broker/group semantics | Một thứ tự toàn cục giữa các group |
| Group ID theo aggregate | Affinity cho cùng key trong queue | Global order giữa các queue hoặc sau replay |

## 8. Ánh xạ DLQ và expiry policy

Không chuyển tên DLQ một cách máy móc. Classic thường có chiến lược dead-letter destination chung hoặc per-destination qua deadLetterStrategy. Artemis dùng dead-letter-address và expiry-address trong address-settings.

Ví dụ Artemis cho luồng đơn hàng:

~~~xml
<addresses>
    <address name="DLQ.Orders">
        <anycast>
            <queue name="DLQ.Orders"/>
        </anycast>
    </address>
    <address name="Expiry.Orders">
        <anycast>
            <queue name="Expiry.Orders"/>
        </anycast>
    </address>
</addresses>

<address-settings>
    <address-setting match="Orders.#">
        <dead-letter-address>DLQ.Orders</dead-letter-address>
        <expiry-address>Expiry.Orders</expiry-address>
        <max-delivery-attempts>5</max-delivery-attempts>
        <redelivery-delay>1000</redelivery-delay>
    </address-setting>
    <address-setting match="VirtualTopic.OrderConfirmed">
        <dead-letter-address>DLQ.Orders</dead-letter-address>
        <expiry-address>Expiry.Orders</expiry-address>
        <max-delivery-attempts>5</max-delivery-attempts>
        <redelivery-delay>1000</redelivery-delay>
    </address-setting>
</address-settings>
~~~

Đây là ví dụ policy; xác minh wildcard syntax và thứ tự match của Artemis version đang dùng. Nếu nhiều queue group cần DLQ tách biệt, tạo dead-letter address/queue riêng hoặc policy phù hợp theo address/queue. Đừng để Billing poison message trộn với Audit nếu vận hành yêu cầu ownership riêng.

Khi migrate, kiểm tra max delivery attempts, redelivery delay/backoff, DLQ destination, quyền browse/replay, expiry/TTL và metadata gốc/event ID. Replay cần idempotency; không tự publish lại hàng loạt vào production.

## 9. Java/Jakarta JMS lab: producer Virtual Topic và consumer group trên Artemis

Lab dùng Java 17, Jakarta JMS 3.1 và Artemis Jakarta client. Nó minh họa **producer gửi topic** và hai worker Billing cạnh tranh trên queue group Billing, trong khi Analytics nhận bản độc lập.

### 9.1. Maven

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab</groupId>
  <artifactId>classic-to-artemis-destination-map</artifactId>
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

### 9.2. Java chương trình

File src/main/java/lab/VirtualTopicMappingLab.java:

~~~java
package lab;

import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class VirtualTopicMappingLab {
    private static final String TOPIC = "VirtualTopic.OrderConfirmed";
    private static final String BILLING_FQQN =
            TOPIC + "::Consumer.Billing.VirtualTopic.OrderConfirmed";
    private static final String ANALYTICS_FQQN =
            TOPIC + "::Consumer.Analytics.VirtualTopic.OrderConfirmed";
    private static final String COMMAND_QUEUE = "Orders.Command";

    private VirtualTopicMappingLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "publish | billing | analytics | queue-send | queue-consume");
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = required("BROKER_USER");
        String password = required("BROKER_PASSWORD");

        try (ActiveMQConnectionFactory factory =
                     new ActiveMQConnectionFactory(url)) {
            switch (args[0]) {
                case "publish" -> publish(factory, user, password);
                case "billing" -> consumeGroup(
                        factory, user, password, BILLING_FQQN, "billing");
                case "analytics" -> consumeGroup(
                        factory, user, password, ANALYTICS_FQQN, "analytics");
                case "queue-send" -> sendQueue(factory, user, password);
                case "queue-consume" -> consumeQueue(factory, user, password);
                default -> throw new IllegalArgumentException(
                        "Unknown mode: " + args[0]);
            }
        }
    }

    private static void publish(
            ConnectionFactory factory, String user, String password) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Topic topic = context.createTopic(TOPIC);

            for (int i = 1; i <= 20; i++) {
                String eventId = "evt-" + UUID.randomUUID();
                String orderId = "order-" + (i % 5);

                TextMessage event = context.createTextMessage(
                        "OrderConfirmed orderId=" + orderId);
                event.setStringProperty("eventId", eventId);
                event.setStringProperty("eventType", "order.confirmed");
                event.setStringProperty("orderId", orderId);
                event.setStringProperty("JMSXGroupID", orderId);

                context.createProducer()
                        .setDeliveryMode(DeliveryMode.PERSISTENT)
                        .send(topic, event);
            }

            context.commit();
            System.out.println("PUBLISH_COMMITTED count=20");
        }
    }

    private static void consumeGroup(
            ConnectionFactory factory, String user, String password,
            String fqqn, String groupName) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue groupQueue = context.createQueue(fqqn);
            try (JMSConsumer consumer = context.createConsumer(groupQueue)) {
                System.out.println("GROUP_READY group=" + groupName
                        + " destination=" + fqqn);

                for (int i = 0; i < 20; i++) {
                    Message message = consumer.receive(5000);
                    if (message == null) {
                        break;
                    }

                    String eventId =
                            message.getStringProperty("eventId");
                    String orderId =
                            message.getStringProperty("orderId");

                    System.out.println("DELIVERED group=" + groupName
                            + " eventId=" + eventId
                            + " orderId=" + orderId
                            + " deliveryCount="
                            + (message.propertyExists("JMSXDeliveryCount")
                               ? message.getIntProperty("JMSXDeliveryCount")
                               : 1));

                    // Production: commit DB inbox + business effect first.
                    context.commit();
                }
            }
        }
    }

    private static void sendQueue(
            ConnectionFactory factory, String user, String password) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue(COMMAND_QUEUE);
            TextMessage command =
                    context.createTextMessage("CapturePayment");
            command.setStringProperty("commandId", "cmd-1001");

            context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(queue, command);
            context.commit();
            System.out.println("QUEUE_SEND_COMMITTED commandId=cmd-1001");
        }
    }

    private static void consumeQueue(
            ConnectionFactory factory, String user, String password) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED);
             JMSConsumer consumer = context.createConsumer(
                     context.createQueue(COMMAND_QUEUE))) {
            Message message = consumer.receive(10_000);
            if (message != null) {
                System.out.println("QUEUE_RECEIVED commandId="
                        + message.getStringProperty("commandId"));
                context.commit();
            }
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

Ghi chú: JMSXGroupID trong ví dụ giữ group affinity trong từng queue group; nó không thay thế group Billing/Analytics. Producer tạo UUID một lần cho mỗi event mới. Nếu gửi lại cùng business event sau timeout, caller cần giữ event ID ban đầu để consumer idempotent.

### 9.3. Chạy thử

Giả định Artemis đã provision các address/queue ở mục 4 và 6. PowerShell:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "lab"
$env:BROKER_PASSWORD = "LAB_ONLY_PASSWORD"
mvn -q -DskipTests package

# Khởi động hai Billing worker ở hai terminal để thấy competing consumers.
mvn -q exec:java "-Dexec.mainClass=lab.VirtualTopicMappingLab" "-Dexec.args=billing"

# Khởi động Analytics consumer.
mvn -q exec:java "-Dexec.mainClass=lab.VirtualTopicMappingLab" "-Dexec.args=analytics"

# Publish event sau khi consumer sẵn sàng, hoặc dùng durable queues đã provision.
mvn -q exec:java "-Dexec.mainClass=lab.VirtualTopicMappingLab" "-Dexec.args=publish"
~~~

Billing workers cùng FQQN sẽ chia nhau message của queue Billing. Analytics nhận bản riêng từ queue Analytics. Nếu chỉ có một Billing process, nó nhận toàn bộ queue Billing; thêm worker thứ hai không tạo thêm bản giao.

### 9.4. Kiểm tra routing bằng message ID

Với 20 event publish, ghi lại tập eventId:

- Billing queue phải nhận 20 event.
- Analytics queue phải nhận 20 event.
- Nếu có Audit queue đã provision, Audit cũng nhận 20 event.
- Hai Billing workers cộng lại nhận 20 event, không phải mỗi worker 20 event.
- Orders.Command queue có semantics khác: hai worker cùng đọc thì tổng cộng chỉ một worker nhận mỗi command.

Số lượng thực tế có thể thấp hơn nếu selector, expiry, TTL, DLQ hoặc consumer đã nhận/ACK trước khi quan sát. Dùng queue depth, message IDs và log của test run để đối chiếu, không chỉ dựa vào tổng số dòng console.

## 10. Cutover migration theo từng bước

### 10.1. Lập bản đồ và đóng băng contract

1. Export destination inventory từ Classic management/runtime.
2. Phân loại queue, topic, durable subscription và Virtual Topic.
3. Ghi tên, selector, prefix/suffix, DLQ, expiry, TTL, priority, message group và ACL.
4. Xác định producer/consumer dùng javax.jms, OpenWire, AMQP hoặc protocol khác.
5. Chốt target address/queue, routing type, subscription identity và owner.

Không chỉ tìm chuỗi VirtualTopic. trong code; consumer có thể lấy tên queue từ config hoặc environment.

### 10.2. Provision target

1. Tạo Artemis address ANYCAST cho queue.
2. Tạo address MULTICAST cho topic.
3. Tạo queue per consumer group cho Virtual Topic.
4. Cấu hình FQQN consumer mapping.
5. Áp dụng security roles, selector/filter, DLQ và expiry.
6. Kiểm tra routing type thực tế bằng management API.
7. Kiểm tra user ứng dụng không có quyền admin không cần thiết.

### 10.3. Kiểm thử tương thích client

- Nâng hoặc thay JMS client theo namespace đích (javax.jms sang jakarta.jms nếu ứng dụng và framework yêu cầu).
- Kiểm tra transaction/acknowledgment, redelivery, message properties, priority và group ID.
- Kiểm tra durable subscription identity và Virtual Topic queue FQQN.
- Kiểm tra TLS/authentication/authorization trên tất cả destinations.
- Test poison message, DLQ, expiry và replay.

Artemis hỗ trợ nhiều protocol nhưng không nên coi mọi Classic client/provider behavior là tương thích hoàn toàn. Ứng dụng dùng Classic-specific API, advisory topic, broker-specific header hoặc Virtual Topic naming convention có thể cần thay đổi.

### 10.4. Chuyển message đang tồn tại

Destination mapping không tự di chuyển message trong KahaDB sang Artemis journal. Store của hai broker không phải một định dạng để mount qua lại. Chọn phương án có thể kiểm soát:

- **Drain rồi cutover:** dừng producer, để consumer xử lý hết backlog source, xác nhận queue/DLQ/durable subscription rồi chuyển producer/consumer.
- **Bridge/relay:** chuyển message từ source sang target trong thời gian chạy; cần event ID ổn định, retry và duplicate handling.
- **Snapshot/replay từ nguồn sự thật:** phù hợp khi event được lưu ở database/outbox/log độc lập và có thể phát lại.

Không copy trực tiếp thư mục data/KahaDB sang Artemis hoặc ngược lại. Không để hai broker cùng nhận producer traffic không kiểm soát; dual-publish có thể tạo hai bản nghiệp vụ.

### 10.5. Cutover và đối soát

1. Đặt maintenance/cutover window và xác định owner rollback.
2. Chuyển producer sang Artemis theo destination mapping.
3. Chuyển consumer theo queue/topic/group tương ứng.
4. Quan sát source/target backlog và lỗi auth/routing.
5. Đối chiếu event IDs, counts, business effects, DLQ và expiry.
6. Chỉ đóng source khi backlog được xử lý hoặc có quyết định retention/replay.
7. Giữ source ở chế độ read-only/isolated trong rollback window theo chính sách.

Nếu cần dual-run, dùng routing có chủ đích và dedup theo event ID. Không để cùng một consumer business effect chạy đồng thời trên cả Classic và Artemis mà không có ownership/fencing.

## 11. Ma trận kiểm thử ánh xạ

| ID | Source → Target | Kiểm thử | PASS khi |
|---|---|---|---|
| MAP-Q-01 | Classic Queue → Artemis ANYCAST | Gửi 100 command với 2 consumer | Tổng cộng 100 command được xử lý theo business ID, không fan-out |
| MAP-Q-02 | Queue selector | Match/non-match properties | Message chỉ đến consumer phù hợp; unmatched được quan sát |
| MAP-T-01 | Classic Topic → Artemis MULTICAST | 3 subscribers active | Mỗi subscriber nhận đúng tập event |
| MAP-T-02 | Durable Topic | Subscriber offline sau khi tạo durable identity | Message phù hợp được giữ và giao lại khi reconnect cùng identity |
| MAP-T-03 | Durable selector change | Thay selector cùng identity | Conflict/backlog được xử lý có chủ đích |
| MAP-VT-01 | Virtual Topic → multicast + group queues | Billing/Analytics/Audit | Mỗi group có bản độc lập |
| MAP-VT-02 | Competing consumers trong Billing | 2 Billing workers | Hai worker chia cùng queue; tổng delivery không nhân đôi |
| MAP-VT-03 | FQQN | Consumer dùng address::queue | Đọc đúng queue group, không tạo address sai |
| MAP-VT-04 | Group ID | Cùng order ID | Ordering/affinity theo queue được kiểm chứng |
| MAP-DLQ-01 | DLQ/expiry | Poison và TTL | Message đến đúng DLQ/expiry destination |
| MAP-SEC-01 | ACL | Producer/consumer role riêng | Send/consume đúng quyền, admin bị giới hạn |
| MAP-CUT-01 | Cutover | Drain/relay/replay | Event IDs được đối soát, không có business effect trùng |
| MAP-ROLLBACK-01 | Rollback window | Mô phỏng target failure | Quay về source không mất/nhân đôi event ngoài hợp đồng |

## 12. Những sai lầm ánh xạ thường gặp

**1. Queue Classic → Artemis MULTICAST.**  
Sai semantics: nhiều consumer có thể nhận mỗi bản. Queue competing phải là ANYCAST + queue.

**2. Topic Classic → Artemis ANYCAST.**  
Sai semantics: subscriber cạnh tranh nhau, không phải tất cả nhận event. Topic phải là MULTICAST.

**3. Virtual Topic → một Artemis Topic thuần.**  
Mất queue backlog độc lập và competing-consumer group. Cần queue per group trên multicast address hoặc một thiết kế shared durable đã được kiểm chứng.

**4. Virtual Topic → một queue duy nhất cho tất cả consumer groups.**  
Billing và Analytics cạnh tranh nhau, nên một nhóm có thể lấy mất message của nhóm khác.

**5. Mỗi worker tạo một Virtual Topic queue riêng.**  
Làm tăng số bản giao và phá competing-consumer semantics. Queue được tạo theo **logical consumer group**, không theo instance/pod.

**6. Bỏ qua FQQN.**  
Consumer có thể truy cập destination sai hoặc kích hoạt auto-create một queue/address không mong muốn. Dùng address::queue khi queue nằm trên address khác tên.

**7. Coi durable Topic subscription là Virtual Topic.**  
Durable identity và queue-per-consumer-group có lifecycle/scale semantics khác nhau; phải chọn theo contract thực tế.

**8. Giữ tên destination nhưng bỏ selector/ACL.**  
Message có thể đi sai tenant hoặc lộ cho consumer không được phép. Mapping phải gồm security và filter, không chỉ routing.

**9. Copy KahaDB vào Artemis.**  
Hai store không tương thích. Dùng drain, bridge/relay hoặc replay từ nguồn sự thật.

**10. Cutover bằng dual-publish không có dedup.**  
Một event có thể tạo hai business effects. Dùng stable event ID, inbox/idempotency và cutover ownership rõ.

## 13. Checklist trước khi nghiệm thu

- [ ] Mọi Classic destination đã phân loại Queue, Topic, durable subscription hoặc Virtual Topic.
- [ ] Mỗi queue target là Artemis ANYCAST với queue đúng.
- [ ] Mỗi topic target là Artemis MULTICAST.
- [ ] Mỗi Virtual Topic có một queue cho mỗi logical consumer group.
- [ ] Producer Virtual Topic gửi tới address/topic; consumer group dùng FQQN address::queue.
- [ ] Consumer instances trong cùng group cùng đọc một queue, không tạo queue riêng từng Pod.
- [ ] Durable subscription giữ client ID, subscription name, selector và lifecycle theo hợp đồng.
- [ ] Selector properties giữ nguyên tên, kiểu dữ liệu và null behavior.
- [ ] JMSXGroupID, priority và ordering được kiểm thử riêng.
- [ ] DLQ, expiry, max delivery attempts và redelivery delay được ánh xạ.
- [ ] Security roles được tách cho producer, consumer, operator và provisioning.
- [ ] Client namespace/protocol/API compatibility được kiểm tra.
- [ ] Không copy broker store trực tiếp giữa Classic và Artemis.
- [ ] Drain/bridge/replay có stable event ID và duplicate handling.
- [ ] Cutover đối soát message IDs, counts, backlog, DLQ và business effects.
- [ ] Rollback window và ownership được xác định rõ.

## 14. Kết luận

Ánh xạ destination từ Classic sang Artemis phải giữ **delivery contract**:

- **Queue → ANYCAST address + queue:** một backlog, nhiều competing consumers.
- **Topic → MULTICAST address + subscription queues:** mỗi subscriber nhận bản độc lập.
- **Virtual Topic → MULTICAST address + queue per consumer group:** mỗi nhóm có backlog riêng; nhiều worker trong cùng nhóm cạnh tranh trên một queue.

Durable Topic subscription và Virtual Topic queue group có thể cùng giữ message khi consumer offline nhưng không phải cùng một abstraction. Selector, priority, message group, DLQ, expiry, ACL và client identity đều phải được kiểm tra như một phần migration contract. Cuối cùng, destination mapping chỉ thiết lập routing đích; dữ liệu đang tồn tại phải được drain, relay hoặc replay theo quy trình riêng, với event ID ổn định và đối soát để tránh mất hoặc nhân đôi side effect.
