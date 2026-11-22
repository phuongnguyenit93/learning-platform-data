# Phát nhầm Queue/Topic và nhầm anycast/multicast

> **Chương:** Chẩn đoán sự cố  
> **Phạm vi:** Điều tra trường hợp producer gửi thành công nhưng consumer không nhận, chỉ một hệ thống nhận trong khi mong đợi fan-out, nhiều consumer chia sai message, hoặc message nằm ở destination khác dự kiến. Bài đối chiếu **JMS Queue/Topic** của ActiveMQ Classic và **address/queue/routing type ANYCAST/MULTICAST** của Artemis. Ví dụ dùng Java 17 và Jakarta Messaging; tên destination và cấu hình phải khớp broker/protocol đang chạy.

## 1. Nhận diện triệu chứng trước khi đổi cấu hình

Một producer gửi event OrderConfirmed tới orders.events và log “send OK”. Billing nhận được nhưng Analytics không thấy; hoặc hai consumer Billing đều mong nhận cùng event nhưng chỉ một consumer nhận. Hai tình huống này có thể là **hành vi đúng của Queue/ANYCAST**, hoặc là **lỗi dùng nhầm destination type** nếu yêu cầu là pub/sub.

| Triệu chứng | Nguyên nhân cần kiểm tra đầu tiên |
|---|---|
| Producer gửi thành công, queue có backlog nhưng listener Topic không nhận | Producer dùng Queue trong khi consumer dùng Topic; hoặc ngược lại |
| Chỉ một trong nhiều hệ thống nhận event | Producer gửi queue/ANYCAST, trong khi mong muốn multicast fan-out |
| Hai replica cùng service không chia đều công việc | Mỗi replica vô tình tạo subscription riêng thay vì cùng consume một queue/subscription |
| Nhiều hệ thống cùng nhận nhưng một hệ thống bị nhận lặp | Có nhiều subscription/queue cho cùng logical consumer, bridge/fan-out lặp hoặc consumer redelivery |
| Artemis address tồn tại nhưng queue không có message | Routing type của message không khớp queue binding, address không có queue phù hợp hoặc queue filter loại message |
| Topic không có subscriber lúc publish, sau đó subscriber mới không thấy event cũ | Non-durable subscription không giữ message trước khi subscriber tồn tại |
| Console hiển thị queue và topic cùng tên, nhưng message chỉ nằm một bên | Queue và Topic là hai loại destination khác nhau; cùng chuỗi tên không làm chúng trở thành một |

**Không bắt đầu bằng việc đổi default routing type toàn broker hoặc purge destination.** Trước hết xác định producer đang dùng API nào, destination type nào, broker nào và consumer đang đăng ký ở đâu.

## 2. Phân biệt Queue, Topic và routing type

### 2.1. Ngữ nghĩa JMS

| API JMS | Mô hình | Khi có hai consumer |
|---|---|---|
| Queue | Point-to-point / competing consumers | Hai consumer cùng một queue chia nhau message; một lần giao bình thường chỉ tới một consumer |
| Topic | Publish/subscribe | Mỗi subscription nhận một bản; hai subscription độc lập đều có thể nhận cùng event |
| Shared Topic subscription | Một subscription được chia sẻ | Nhiều consumer cùng subscription cạnh tranh message của subscription đó |

Nếu hai instance Billing cần scale-out và cùng xử lý một công việc, chúng nên cùng đọc **một queue hoặc một shared subscription**. Nếu Billing và Analytics đều phải nhận event, mỗi hệ thống cần **subscription/queue độc lập**.

### 2.2. Artemis address, queue và routing type

Artemis tách ba thành phần:

- **Address:** nơi producer gửi message.
- **Queue:** nơi consumer lấy message; queue được bind vào address.
- **Routing type:** quyết định message đi vào một queue hay tất cả queue phù hợp trên address.

| Routing type | Kết quả định tuyến | Mô hình gần tương ứng |
|---|---|---|
| ANYCAST | Gửi tới **một queue phù hợp** trên address | JMS Queue / competing consumers |
| MULTICAST | Gửi tới **mọi multicast queue** trên address | JMS Topic / pub-sub |

Một address có thể bind nhiều queue. Với ANYCAST, broker chọn một queue phù hợp; nhiều consumer trên **cùng queue** tiếp tục chia message. Với MULTICAST, mỗi queue nhận một bản độc lập; nếu một queue có nhiều consumer (ví dụ shared subscription), các consumer đó chia bản của queue.

```text
ANYCAST: producer -> address -> one queue -> consumer A OR consumer B

MULTICAST: producer -> address -> queue Billing   -> Billing consumer(s)
                           |
                           +-> queue Analytics -> Analytics consumer(s)
                           |
                           +-> queue Inventory -> Inventory consumer(s)
```

**Đừng đồng nhất “hai consumer” với “hai subscription”.** Hai consumer trên một queue ANYCAST không nhận hai bản giống nhau; hai multicast subscription queue mới tạo fan-out giữa hai nhóm.

## 3. JMS Queue và Topic được ánh xạ ra sao?

### 3.1. ActiveMQ Classic: cùng tên không có nghĩa cùng destination

Trong Classic, queue và topic là hai loại destination riêng. Producer tạo Queue tên orders.events sẽ gửi vào queue orders.events; consumer tạo Topic cùng tên đang subscribe một topic orders.events khác. Không có quy tắc tự động chuyển message giữa hai loại.

Ví dụ sai khi muốn pub/sub:

```java
// Producer: point-to-point
Queue destination = context.createQueue("orders.events");
context.createProducer().send(destination, "OrderConfirmed");

// Consumer: publish/subscribe
Topic topic = context.createTopic("orders.events");
JMSConsumer consumer = context.createConsumer(topic);
```

Consumer Topic không nhận message từ Queue chỉ vì chuỗi tên giống nhau. Trong Web Console/JMX, hãy kiểm tra destinationType=Queue và destinationType=Topic riêng biệt.

Ví dụ đúng nếu mục tiêu là fan-out Topic:

```java
Topic destination = context.createTopic("orders.events");
context.createProducer().send(destination, "OrderConfirmed");

JMSConsumer billing = context.createConsumer(destination);
JMSConsumer analytics = context.createConsumer(destination);
```

Hai consumer trên tạo hai subscription không durable riêng theo semantics JMS. Trong test thật, phải đăng ký chúng **trước khi publish**; nếu muốn giữ event khi một hệ thống offline, tạo durable subscription theo identity riêng cho hệ thống đó.

Nếu mục tiêu là queue work distribution, cả producer lẫn consumer dùng Queue:

```java
Queue destination = context.createQueue("orders.work");
context.createProducer().send(destination, "RebuildOrderProjection");

JMSConsumer workerA = context.createConsumer(destination);
JMSConsumer workerB = context.createConsumer(destination);
```

workerA và workerB cạnh tranh cùng queue; không viết test đòi cả hai nhận cùng message.

### 3.2. Artemis: JMS semantics ánh xạ sang ANYCAST/MULTICAST

Artemis ánh xạ JMS Queue thành address cùng tên với một anycast queue cùng tên. Tất cả JMS consumers của queue đó chia message. JMS Topic được ánh xạ thành address cùng tên; mỗi subscription là một multicast queue. Các message gửi tới Topic được route tới mọi subscription queue đang tồn tại.

| JMS destination | Artemis address | Queue/routing type |
|---|---|---|
| createQueue("orders.work") | orders.work | Queue orders.work, ANYCAST |
| createTopic("orders.events") | orders.events | Multicast subscription queue cho từng subscriber |

Đây là lý do một JMS Queue producer không nên được ghép với JMS Topic consumer cùng tên để tạo fan-out: hai bên yêu cầu routing semantics khác nhau. Nếu broker có address cùng lúc bind anycast và multicast queues, message có routing type không khớp queue vẫn không được route vào queue đó.

### 3.3. Cấu hình Artemis tường minh để tránh nhầm

Đặt fragment sau bên trong phần addresses hiện có trong broker.xml:

```xml
<addresses>
    <address name="orders.work">
        <anycast>
            <queue name="orders.work"/>
        </anycast>
    </address>

    <address name="orders.events">
        <multicast/>
    </address>
</addresses>
```

orders.work dành cho một nhóm worker cạnh tranh. orders.events dành cho subscriber; broker tạo subscription queue khi consumer Topic đăng ký theo semantics JMS. Với Topic, durable/non-durable subscription quyết định vòng đời và identity queue tương ứng. Nếu chưa có subscription queue trên address multicast, message không có nơi nhận và có thể bị drop theo mapping hiện hành.

Nếu cần provision queue cho một nhóm cụ thể, khai báo queue dưới multicast của address. Ví dụ hai subscription queue độc lập:

```xml
<address name="orders.events">
    <multicast>
        <queue name="billing.orders.events">
            <durable>true</durable>
        </queue>
        <queue name="analytics.orders.events">
            <durable>true</durable>
        </queue>
    </multicast>
</address>
```

Đây là queue cấu hình tường minh; nếu consumer dùng JMS Topic subscription được quản lý tự động, không tạo thêm queue thứ hai cho cùng một hệ thống nếu không chủ đích, vì mỗi queue multicast nhận một bản độc lập.

## 4. Quy trình điều tra theo từng bước

### Bước 1 — Ghi lại destination type thực tế ở cả producer và consumer

Không chỉ ghi tên destination. Thu thập:

| Thông tin | Producer | Consumer |
|---|---|---|
| Broker endpoint và protocol | Host/port, OpenWire/Core/AMQP/STOMP | Host/port và protocol |
| API tạo destination | createQueue hay createTopic | createConsumer(queue) hay createConsumer(topic) |
| Tên vật lý | Destination name nguyên vẹn | Destination/subscription name |
| Routing expectation | Một worker hay nhiều hệ thống | Competing consumer hay fan-out subscriber |
| Identity | Producer/service/version | clientID, subscription name, consumer group |
| Filter | Message properties, TTL | Selector, durable/shared subscription |

Nếu producer và consumer chạy qua protocol khác nhau, kiểm tra mapping của **protocol manager** trên broker. Một tên STOMP/AMQP destination chung không tự nói rõ đó là JMS Queue hay Topic nếu acceptor/protocol mapping không quy định.

### Bước 2 — Xác nhận broker và namespace

Đảm bảo producer và consumer đang nối cùng cluster/broker topology, virtual host/tenant phù hợp và đúng môi trường. Lỗi thường gặp là producer gửi staging còn consumer đọc local, hoặc hai ứng dụng dùng hostname alias khác nhau dẫn đến hai broker độc lập.

Kiểm tra:

- Broker product/version (Classic hay Artemis).
- Endpoint/protocol thực tế từ cấu hình runtime, không chỉ file YAML.
- Tên address/destination sau khi loại bỏ prefix protocol nếu có.
- Security principal có quyền send/consume trên destination dự kiến.

### Bước 3 — Dùng một event đánh dấu duy nhất

Gửi một message thử có property eventId duy nhất, testRunId và eventType; dùng payload không chứa dữ liệu nhạy cảm. Ghi lại JMSMessageID, timestamp và destination. Tránh gửi nhiều event cùng lúc khi chưa biết message đầu tiên đi đâu.

Ví dụ marker:

```java
TextMessage message = context.createTextMessage("ROUTE_PROBE");
message.setStringProperty("eventId", "route-check-2026-001");
message.setStringProperty("testRunId", "troubleshoot-004");
message.setStringProperty("eventType", "RouteProbe");
producer.send(destination, message);
```

Chỉ gửi marker vào queue/topic lab hoặc môi trường được phép. Không dùng queue thanh toán/đơn hàng production để dò routing.

### Bước 4 — Tìm message ở đúng loại destination

**ActiveMQ Classic**

- Mở Web Console và kiểm tra tab Queues lẫn Topics; cùng tên có thể xuất hiện ở hai loại riêng.
- Với JMX, tìm MBean có destinationType=Queue hoặc destinationType=Topic.
- Với Queue, đọc QueueSize, EnqueueCount, DequeueCount, ConsumerCount, InFlightCount.
- Với Topic, kiểm tra subscribers/durable subscribers và trạng thái từng subscription; không lấy QueueSize của một queue khác làm đại diện cho Topic.

**Artemis**

- Xem address producer gửi tới.
- Kiểm tra các queue binding trên address và routing type của từng queue.
- Với ANYCAST, xác định queue nào được chọn và consumer nào đang cạnh tranh trên queue đó.
- Với MULTICAST, xác nhận có subscription queue cho từng subscriber; kiểm tra message count và consumer count theo queue.
- Nếu dùng FQQN, xác nhận đúng cặp address::queue; FQQN trỏ thẳng vào queue cụ thể, có thể làm thay đổi nơi consumer đọc so với việc subscribe Topic thông thường.

Nếu address tồn tại nhưng không có queue binding phù hợp, producer có thể gửi thành công ở mức transport mà không tạo được đường giao tới consumer mong đợi. Kiểm tra routing type và queue binding trước khi kết luận message đã mất.

### Bước 5 — Kiểm tra selector, expiry và subscription

Sau khi xác nhận routing type đúng, kiểm tra các điều kiện khiến message không tới callback:

- JMS selector có khớp property và kiểu dữ liệu không? eventType = 'OrderConfirmed' không khớp nếu producer không đặt property hoặc đặt sai kiểu.
- Queue filter có loại message trước khi vào queue không?
- Message có JMSExpiration/TTL đã hết hạn không?
- Topic subscriber có tồn tại **trước khi publish** nếu là non-durable không?
- Durable subscriber có đúng clientID và subscription name không?
- Consumer có đang subscribe nhầm address/subscription queue hoặc dùng selector sai?
- User có quyền consume trên queue/subscription thực tế không?

Queue filter và consumer selector có vị trí khác nhau: queue filter quyết định message có được route vào queue; selector quyết định consumer nào nhìn thấy message đã nằm trong queue. Đừng sửa routing type khi nguyên nhân thật là selector không khớp.

## 5. Dấu hiệu nhầm ANYCAST và MULTICAST trên Artemis

### 5.1. Đòi fan-out nhưng cấu hình ANYCAST

Ví dụ address chỉ có anycast queue:

```xml
<address name="events.orders">
    <anycast>
        <queue name="events.orders"/>
    </anycast>
</address>
```

Hai hệ thống Billing và Analytics cùng tạo consumer trên queue events.orders. Chúng **chia việc**, không cùng nhận một bản event. Cách sửa phụ thuộc ý định:

- Nếu chỉ một service cần xử lý, giữ ANYCAST và đặt nhiều replica cùng queue.
- Nếu nhiều hệ thống đều cần event, chuyển thiết kế sang MULTICAST với subscription queue riêng cho từng hệ thống; bảo đảm durable subscription/queue được tạo trước khi cần giữ backlog.

### 5.2. Đòi competing consumers nhưng cấu hình MULTICAST

Ví dụ address có hai multicast queues worker.a và worker.b. Mỗi message được route tới **cả hai queue**. Nếu mỗi queue có một worker, cả hai worker đều xử lý một bản; đây là fan-out, không phải load balancing trên một queue.

Nếu chỉ cần một trong hai worker xử lý mỗi message, dùng một ANYCAST queue và cho cả hai worker consume cùng queue. Không tạo hai anycast queues riêng rồi dựa vào tên gọi để giả định consumer tự chia sẻ một hàng đợi; kiểm tra queue binding thực tế.

### 5.3. Mixed routing type trên cùng address

Artemis cho phép address có cả anycast và multicast queues, nhưng tài liệu khuyến cáo đây thường là anti-pattern. Message có routing type cụ thể chỉ được route tới queue phù hợp; do đó:

- Producer Queue/ANYCAST không tự fan-out sang multicast subscription queues.
- Producer Topic/MULTICAST không tự đi vào anycast work queue.
- Một address có queue cả hai loại làm dashboard khó đọc và khiến client phụ thuộc protocol/default.

Thiết kế dễ vận hành hơn là dùng tên address thể hiện ý định riêng, ví dụ orders.work cho ANYCAST và orders.events cho MULTICAST. Nếu phải dùng chung address vì tương thích, ghi rõ routing type và kiểm thử từng protocol.

### 5.4. Kiểm tra default-address-routing-type

Artemis có thể tự tạo address/queue để hỗ trợ protocol. Các address-setting có:

- default-address-routing-type
- default-queue-routing-type
- auto-create-addresses
- auto-create-queues
- auto-delete-addresses
- auto-delete-queues

Default routing type chỉ là **fallback khi broker không suy ra được semantics từ client/protocol hoặc cấu hình tường minh**. JMS Queue và JMS Topic vốn mang semantics riêng nên không kết luận chỉ từ default global. Với generic destination của protocol khác, default có thể ảnh hưởng trực tiếp. Đọc address-setting khớp address cụ thể và cấu hình acceptor/protocol trước khi thay.

Ví dụ address-setting hẹp cho một namespace lab:

```xml
<address-settings>
    <address-setting match="lab.work.#">
        <default-address-routing-type>ANYCAST</default-address-routing-type>
        <default-queue-routing-type>ANYCAST</default-queue-routing-type>
    </address-setting>
    <address-setting match="lab.events.#">
        <default-address-routing-type>MULTICAST</default-address-routing-type>
        <default-queue-routing-type>MULTICAST</default-queue-routing-type>
    </address-setting>
</address-settings>
```

Đặt fragment trong address-settings hiện có của broker.xml. Không đổi default # toàn broker để chữa một destination đơn lẻ; có thể làm các protocol/client khác tự tạo queue với semantics ngoài mong đợi.

## 6. FQQN và subscription queue: tránh đọc nhầm nơi

Artemis hỗ trợ Fully Qualified Queue Name (FQQN) theo cú pháp:

```text
address::queue
```

Ví dụ address orders.events có hai multicast queues billing.orders.events và analytics.orders.events. Consumer JMS có thể trỏ trực tiếp tới một queue cụ thể:

```java
Queue billingQueue =
    context.createQueue("orders.events::billing.orders.events");
JMSConsumer billing = context.createConsumer(billingQueue);
```

Đây là thao tác đọc **một queue đã bind** vào address. Nó không giống tạo một JMS Topic consumer mới và không tự đăng ký durable subscription theo clientID/subscription name. Nếu ứng dụng vốn dùng Topic nhưng vô tình đổi sang FQQN queue, hãy kiểm tra queue đó có đúng identity, durability và lifecycle mong muốn không.

Khi dùng JMS Topic thông thường, để Artemis tự quản lý subscription queue:

```java
context.setClientID("billing-service"); // đặt trước khi dùng context/connection
Topic topic = context.createTopic("orders.events");
JMSConsumer billing = context.createDurableConsumer(
    topic, "billing-orders-v1");
```

Ví dụ này dùng JMSContext riêng cho Billing; gọi setClientID trước khi dùng connection hoặc tạo consumer. Mỗi hệ thống có clientID/subscription identity riêng; nếu hai hệ thống dùng nhầm cùng identity, có thể gặp xung đột hoặc chia sẻ ngoài dự kiến.

## 7. ActiveMQ Classic: phân biệt Topic subscriber và Virtual Topic queue

Classic có JMS Queue và Topic riêng biệt. Ngoài durable Topic subscription, broker còn có **Virtual Topic** để producer gửi theo Topic nhưng mỗi nhóm consumer đọc từ một queue vật lý riêng.

Quy ước mặc định thường gặp:

```text
Producer sends to Topic: VirtualTopic.Orders

Consumer Billing queue:   Consumer.Billing.VirtualTopic.Orders
Consumer Analytics queue: Consumer.Analytics.VirtualTopic.Orders
```

Các replica Billing cùng consume queue Consumer.Billing.VirtualTopic.Orders để chia việc. Analytics consume queue riêng nên nhận bản event độc lập. Đây là cấu hình Virtual Topic của Classic, **không phải** tên queue JMS thông thường có thể tự động dùng nếu broker chưa bật/cấu hình Virtual Topic interceptor hoặc quy ước tương ứng.

Nếu chỉ có một consumer Topic durable cho Billing, kiểm tra:

- clientID và durable subscription name có ổn định không?
- Consumer có kết nối đúng broker/topic không?
- Durable subscription có được tạo trước lúc publish và có backlog không?
- Ứng dụng có đang consume queue Virtual Topic trong khi producer gửi Topic thường tên khác không?

Không đồng thời bridge cả consumer queues và Virtual Topic qua network of brokers nếu không có thiết kế loại trừ phù hợp; Classic cảnh báo có thể fan-out lại và tạo duplicate. Khi điều tra duplicate, kiểm tra network connector và destination interceptor trước khi kết luận producer gửi hai lần.

## 8. Lab Java/JMS xác minh Queue và Topic

Phép thử dùng một broker lab, queue lab.route.work, Topic lab.route.events và marker event ID duy nhất. Chạy producer/consumer với đúng provider factory cho Classic hoặc Artemis. Không chạy trên destination nghiệp vụ.

### 8.1. Queue: hai consumer chia một message

```java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;

Queue queue = context.createQueue("lab.route.work");
JMSConsumer workerA = context.createConsumer(queue);
JMSConsumer workerB = context.createConsumer(queue);
context.start();

TextMessage marker = context.createTextMessage("QUEUE_PROBE");
marker.setStringProperty("eventId", "queue-probe-001");
context.createProducer().send(queue, marker);

Message a = workerA.receive(1_000L);
Message b = workerB.receive(1_000L);
int received = (a == null ? 0 : 1) + (b == null ? 0 : 1);
if (received != 1) {
    throw new AssertionError("Expected one queue delivery, got " + received);
}
```

Trong một queue test không có consumer khác, một marker được nhận bởi một trong hai worker. Không assert workerA cụ thể phải nhận; dispatch/load balancing không bảo đảm chia đều. Đóng consumer và context sau khi test.

### 8.2. Topic: hai subscription độc lập cùng nhận marker

```java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Topic;

Topic topic = context.createTopic("lab.route.events");
JMSConsumer billing = context.createConsumer(topic);
JMSConsumer analytics = context.createConsumer(topic);
context.start();

TextMessage marker = context.createTextMessage("TOPIC_PROBE");
marker.setStringProperty("eventId", "topic-probe-001");
context.createProducer().send(topic, marker);

Message billingCopy = billing.receive(2_000L);
Message analyticsCopy = analytics.receive(2_000L);
if (billingCopy == null || analyticsCopy == null) {
    throw new AssertionError("Each topic subscription must receive a copy");
}
```

Hai consumer trên cùng JMSContext tạo hai non-durable subscriptions độc lập theo semantics JMS. Đăng ký cả hai trước khi publish. Nếu dùng shared Topic subscription, hai consumer chia message của **một subscription** và test phải có kỳ vọng khác.

### 8.3. Đọc đúng kết quả trên từng broker

| Test | Classic | Artemis |
|---|---|---|
| Queue probe | Queue MBean lab.route.work, hai consumer trên cùng queue | Address/queue ANYCAST lab.route.work, consumer count trên queue |
| Topic probe | Topic MBean lab.route.events, hai subscriber | Address MULTICAST lab.route.events, hai subscription queues |
| Chỉ một consumer Topic nhận | Kiểm tra consumer có thật sự là hai subscription độc lập không | Kiểm tra hai multicast queues có tồn tại không; nếu hai consumer share một subscription thì chỉ một bản |
| Queue probe không nhận | Kiểm tra destination type, ACL và queue name | Kiểm tra address/anycast queue binding và routing type |

Nếu dùng durable Topic test, tạo durable subscription identity riêng và dọn unsubscribe sau test; đừng so với non-durable subscriber rồi kết luận broker mất message khi subscriber offline.

## 9. Khắc phục theo nguyên nhân, không làm mất bằng chứng

| Nguyên nhân đã xác minh | Sửa ở đâu | Cách xác minh sau sửa |
|---|---|---|
| Producer tạo Queue, consumer tạo Topic | Sửa API/destination contract ở producer hoặc consumer theo yêu cầu nghiệp vụ | Gửi một event ID mới; kiểm tra queue/topic MBean hoặc Artemis bindings |
| Muốn fan-out nhưng đang dùng Queue/ANYCAST | Chuyển hợp đồng sang Topic/MULTICAST, provision subscription/queue riêng | Hai subscription độc lập nhận cùng marker |
| Muốn load balancing nhưng mỗi worker có subscription riêng | Dùng cùng queue hoặc shared subscription có identity chung | Một marker chỉ được một worker xử lý, tổng throughput chia cho nhóm |
| Artemis address không có queue phù hợp | Tạo đúng anycast/multicast binding hoặc sửa routing type hẹp | Xem queue binding và gửi marker sau khi provisioning |
| FQQN trỏ sai queue | Sửa address hoặc queue trong FQQN | Management API cho thấy đúng queue và consumer count |
| Selector/filter loại message | Sửa property type/name hoặc selector/filter | Gửi marker có properties rõ và kiểm tra queue/filter result |
| Topic subscriber offline, non-durable | Chuyển sang durable subscription/queue phù hợp | Tạo subscription trước, publish khi subscriber offline rồi reconnect |
| Virtual Topic Classic chưa được cấu hình | Kiểm tra destination interceptor và convention | Publish Topic, kiểm tra queue Consumer.<group>.VirtualTopic.<name> |
| Network bridge/federation tạo fan-out lặp | Xem bridge direction, include/exclude destination và nơi fan-out | Dùng một event ID, trace từng hop, kiểm tra không có đường forward vòng |

**Message đã vào nhầm queue không tự chuyển sang destination đúng khi đổi cấu hình.** Thay routing type chỉ ảnh hưởng message gửi sau khi cấu hình có hiệu lực. Với dữ liệu đã gửi nhầm:

1. Ghi lại destination nguồn, event ID, message ID, số lượng và trạng thái ACK.
2. Xác định queue đích và consumer nào đã xử lý một phần.
3. Chọn quy trình move/replay có kiểm soát, giữ nguyên event ID và idempotency key.
4. Chỉ sau khi xác minh đủ bản sao và quyền sở hữu mới xử lý queue nguồn; không purge để “dọn nhầm”.

Nếu không xác định được consumer nào đã xử lý, đánh dấu sự kiện cần đối soát trước khi replay; nếu không, sửa routing có thể biến lỗi thiếu message thành lỗi xử lý trùng.

## 10. Checklist xác nhận routing đã đúng

- [ ] Producer và consumer dùng đúng broker, protocol, destination name và destination type.
- [ ] Đã phân biệt Queue với Topic; cùng tên vật lý không được coi là cùng destination trong Classic.
- [ ] Với Artemis, đã kiểm tra address, queue bindings và routing type của từng queue.
- [ ] ANYCAST dùng cho một queue work distribution; các consumer cùng queue cạnh tranh.
- [ ] MULTICAST dùng cho fan-out; mỗi hệ thống có subscription queue riêng, consumer trong cùng subscription chia bản của nhóm đó.
- [ ] Không trộn anycast/multicast trên cùng address nếu không có lý do và test cụ thể.
- [ ] Default routing type chỉ được xét khi client/protocol không cung cấp semantics; không đổi default toàn broker để chữa một destination.
- [ ] Đã kiểm tra FQQN, selector, queue filter, TTL, durable subscription, ACL và auto-create.
- [ ] Đã kiểm thử một marker Queue và một marker Topic trên broker lab.
- [ ] Nếu dùng Classic Virtual Topic, xác nhận producer Topic và consumer queue theo convention/interceptor.
- [ ] Nếu có bridge/federation, đã loại trừ fan-out lặp hoặc vòng forward.
- [ ] Không purge/replay message nhầm trước khi ghi manifest và kiểm tra business side effect.

**Kết luận:** Chẩn đoán đúng bắt đầu bằng việc xác nhận **producer và consumer đang nói cùng một hợp đồng destination**. JMS Queue/Artemis ANYCAST phân phối một message cho một worker trong nhóm; JMS Topic/Artemis MULTICAST tạo một bản cho mỗi subscription queue. Trên Classic, Queue và Topic cùng tên vẫn là hai destination khác nhau; trên Artemis, tên address giống nhau không loại bỏ khác biệt routing type. Kiểm tra destination type, address bindings, subscription identity, filter và protocol mapping trước khi đổi cấu hình hoặc replay dữ liệu.

## Tài liệu chính thức

1. [Apache Artemis 2.57.0 — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): address, queue, ANYCAST/MULTICAST, automatic configuration, FQQN, filters và routing prefix.
2. [Apache Artemis 2.57.0 — Mapping JMS Concepts to the Core API](https://artemis.apache.org/components/artemis/documentation/latest/jms-core-mapping.html): JMS Queue ánh xạ sang anycast queue; JMS Topic subscription ánh xạ sang multicast queue.
3. [Apache Artemis 2.57.0 — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): default routing type và auto-create/delete.
4. [ActiveMQ Classic — Virtual Destinations](https://activemq.apache.org/components/classic/documentation/virtual-destinations): Virtual Topic, consumer queue convention, selector-aware và network of brokers duplicate warning.
5. [Jakarta Messaging 3.1 — JMSContext](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext): tạo Queue/Topic, consumer và producer.
