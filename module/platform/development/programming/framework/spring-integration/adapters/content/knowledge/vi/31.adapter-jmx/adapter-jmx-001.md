# JMX notification-listening adapter

## 1. Bài toán: nhận sự kiện quản trị JMX vào IntegrationFlow

Một ứng dụng Java có MBean theo dõi độ sâu hàng đợi, trạng thái connection pool hoặc cảnh báo tài nguyên. Khi hàng đợi vượt ngưỡng, MBean phát một **JMX Notification**. Backend muốn chuyển ngay notification này vào Spring Integration để:

- Kiểm tra loại sự kiện và nguồn phát;
- Chuyển thành một message contract rõ ràng;
- Ghi audit/metric, kích hoạt cảnh báo hoặc gửi tới HTTP/JMS/AMQP/Kafka;
- Không phải chạy job định kỳ hỏi lại thuộc tính MBean;
- Quản lý đăng ký và hủy đăng ký listener cùng vòng đời Spring application.

Spring Integration cung cấp **JMX notification-listening channel adapter** để làm cầu nối **JMX Notification → Spring Message → MessageChannel**. Adapter đăng ký `NotificationListener` với `MBeanServer`, chờ thông báo phát sinh, rồi đặt chính đối tượng `javax.management.Notification` vào payload của Spring message. Nó là **inbound, event-driven adapter**, không phải attribute poller.

Bài **“JMX notification-listening adapter”** thuộc chương **Adapter JMX**, module **SPRING_INTEGRATION_ADAPTERS**. Module này tập trung kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành trao đổi file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu, xử lý message contract, lỗi và vòng đời kết nối. JMX là ví dụ điển hình về một nguồn sự kiện bên trong hoặc bên cạnh JVM cần được đưa vào cùng pipeline tích hợp.

Sau bài học, người đọc có thể:

1. Phân biệt JMX `MBean`, `MBeanServer`, `ObjectName`, `Notification`, `NotificationBroadcaster` và `NotificationListener`.
2. Giải thích chính xác adapter lắng nghe notification, và vì sao **không cần poller**.
3. Cấu hình `notification-listening-channel-adapter` bằng Spring Integration XML namespace.
4. Tạo Java bean `NotificationListeningMessageProducer` để nối JMX với Spring `DirectChannel` và `IntegrationFlow`.
5. Tự viết MBean phát notifications, filter theo notification type, dùng optional handback và chuẩn hóa message.
6. Phân biệt object-name chính xác và `ObjectName` pattern, chú ý đăng ký MBean động và lifecycle.
7. Đánh giá backpressure, thread, error propagation, bảo mật remote JMX và giới hạn độ bền của JMX notifications.
8. Viết JUnit test có MBeanServer nội bộ, test filtering, handler, stop/start và các tình huống sự cố.
9. Quyết định khi nào phù hợp dùng notification listener, attribute polling, outbound gateway hoặc messaging broker bền vững.

**Điểm then chốt:** JMX notification giúp phát hiện sự kiện quản trị **khi nó xảy ra**; nó không phải topic broker, không có subscription QoS/retained như MQTT, và không mặc định cung cấp durable replay hoặc acknowledgement nghiệp vụ.

## 2. Kiến trúc JMX Notification → Spring Integration

~~~mermaid
flowchart LR
    M["Managed component<br/>QueueHealth MBean"]
    S[("MBeanServer")]
    L["NotificationListeningMessageProducer<br/>JMX NotificationListener"]
    CH["jmx.notifications.in<br/>MessageChannel"]
    F["IntegrationFlow<br/>validate + transform + route"]
    A[("Audit / Metrics")]
    Q["Kafka / JMS / AMQP / HTTP"]
    M -->|"sendNotification"| S
    S -->|"JMX listener callback"| L
    L -->|"Message<Notification>"| CH
    CH --> F
    F --> A
    F --> Q
~~~

**Luồng xử lý đi từ nguồn sang đích:**

1. Thành phần được quản lý tạo một `Notification`, ví dụ type `demo.queue.depth.changed`.
2. Một `NotificationBroadcaster` MBean gửi notification tới các listeners đã đăng ký.
3. `NotificationListeningMessageProducer` có `ObjectName` định vị MBean và đăng ký listener qua `MBeanServer`.
4. Khi callback chạy, producer tạo Spring message chứa **JMX Notification object** làm payload và đưa vào output channel.
5. Spring Integration flow đọc các trường `type`, `source`, `sequenceNumber`, `timeStamp`, `message` và `userData`, kiểm tra hợp đồng rồi chuyển sang business DTO.
6. Downstream handler ghi log/audit hoặc thực hiện outbound integration theo chính sách riêng.

Mục tiêu là **đưa notification vào pipeline message**, không phải để JMX trực tiếp đảm nhiệm queue, transaction hoặc message retention.

### 2.1. So sánh với các adapter khác

| Loại endpoint | Trigger | Payload chính | Dùng khi nào? |
| --- | --- | --- | --- |
| JMX notification-listening inbound | JMX `NotificationListener` callback | `Notification` | Bắt thay đổi/sự kiện chủ động phát từ MBean. |
| JMX attribute-polling inbound | Spring poller theo lịch | Giá trị thuộc tính MBean | MBean chỉ có attribute cần đọc định kỳ. |
| JMX tree-polling inbound | Poller lấy snapshot MBean tree | Cấu trúc MBean/attribute | Inventory/monitoring toàn bộ nhóm MBeans. |
| JMX operation-invoking outbound gateway | Spring message gọi operation MBean | Kết quả lời gọi operation | Yêu cầu điều khiển/management có request-reply. |
| MQTT inbound adapter | Broker giao PUBLISH theo subscription | Payload đã convert | Nhận events từ devices/broker MQTT. |
| JMS/AMQP/Kafka consumers | Broker/log giao message | Record/message domain | Cần queue/stream, retry/replay/durability theo broker. |

JMX listener thường phục vụ monitoring **trong JVM hoặc từ MBeanServerConnection được cấu hình**. Nó không thay database Change Data Capture hoặc một hệ thống message broker chuyên dụng.

## 3. JMX nền tảng: các kiểu đối tượng cần phân biệt

### 3.1. MBean và MBeanServer

**MBean** là managed bean mà JMX runtime có thể khám phá và thao tác qua `MBeanServer`. MBean có attributes, operations và có thể phát notifications. Một **Standard MBean** thường có interface tên `XxxMBean` và class `Xxx` implement interface đó.

`MBeanServer` là registry và dispatch infrastructure của JMX trong JVM. Có thể dùng platform server:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
~~~

`ManagementFactory.getPlatformMBeanServer()` không đồng nghĩa với một MQTT broker hoặc Spring channel. Nó là JMX management endpoint của JVM, có thể được truy cập từ Java code và qua remote connector **nếu được cấu hình rõ ràng**.

### 3.2. ObjectName

JMX dùng `javax.management.ObjectName` để định danh MBean:

~~~text
demo.integration:type=QueueHealth,name=Orders
java.lang:type=Memory
java.lang:type=GarbageCollector,name=G1 Young Generation
~~~

Một ObjectName có domain trước dấu `:`, theo sau là danh sách key/value properties. Với demo:

~~~java
import javax.management.ObjectName;

ObjectName objectName =
        new ObjectName("demo.integration:type=QueueHealth,name=Orders");
~~~

Không coi đây là một đường dẫn filesystem, Kafka topic hoặc Spring bean name. ObjectName có quy tắc quoting/wildcards riêng; tránh ghép trực tiếp giá trị không tin cậy từ HTTP caller thành ObjectName nếu chưa validate/quote.

### 3.3. Notification

Một JMX `Notification` bao gồm các metadata thường dùng:

| API | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| `getType()` | Loại sự kiện, thường dùng tên phân cấp như `demo.queue.depth.changed`. | Không tự bảo đảm trust hoặc payload schema. |
| `getSource()` | Nguồn notification theo MBean/provider. | Không luôn là `String`/`ObjectName` theo mong đợi của ứng dụng. |
| `getSequenceNumber()` | Số thứ tự do publisher quản lý. | Không phải global unique event ID; có thể reset khi restart. |
| `getTimeStamp()` | Mốc thời gian của notification. | Phụ thuộc đồng hồ nguồn; không dùng để bảo đảm ordering tuyệt đối giữa MBeans. |
| `getMessage()` | Mô tả dạng text. | Không nên parse text tự do làm schema chính. |
| `getUserData()` | Thông tin phụ thuộc ứng dụng. | Kiểu `Object`; cần validate trước khi cast/serialize. |

Ví dụ tạo notification:

~~~java
import javax.management.Notification;

Notification notification = new Notification(
        "demo.queue.depth.changed",
        sourceObject,
        42L,
        System.currentTimeMillis(),
        "Độ sâu hàng đợi Orders đã thay đổi");

notification.setUserData(Integer.valueOf(25));
~~~

**Notification type không phải Java class name.** Nên định nghĩa tên type ổn định và versioning của `userData` nếu consumer cần xử lý dài hạn.

### 3.4. NotificationBroadcaster và NotificationListener

MBean muốn phát notification thường implement `NotificationBroadcaster` hoặc kế thừa `NotificationBroadcasterSupport`. Subscriber implement `NotificationListener` với method:

~~~java
void handleNotification(
        Notification notification,
        Object handback);
~~~

`handback` là context do **người đăng ký listener** chỉ định; JMX truyền lại context khi gọi callback. Nó không tự là `Notification.getUserData()`.

### 3.5. NotificationFilter

`NotificationFilter` quyết định notification nào được đưa qua listener:

~~~java
import javax.management.NotificationFilter;

NotificationFilter onlyQueueDepth =
        notification -> "demo.queue.depth.changed"
                .equals(notification.getType());
~~~

Filter là **tầng lựa chọn notification type/metadata** ngay ở listener registration. Nó **không** phải authorization; nguồn MBean và connection JMX vẫn cần được tin cậy/cấp quyền.

## 4. Cơ chế notification-listening channel adapter

Từ phía Spring Integration, adapter cần:

1. `MBeanServer` hoặc `MBeanServerConnection` để đăng ký listener;
2. Một hoặc nhiều `ObjectName` của MBeans phát notifications;
3. Một `MessageChannel` làm output;
4. Optional `NotificationFilter` để loại events không quan tâm;
5. Optional **handback** context.

Adapter đăng ký khi endpoint start, hủy đăng ký khi stop. Thông thường Spring quản lý endpoint qua `SmartLifecycle`. Trong những tình huống MBean được export vào context muộn, implementation cũng có xử lý lifecycle/context refreshed để đăng ký listener sau khi MBean đã sẵn sàng; cần test thực tế cùng cấu hình `MBeanExporter`.

### 4.1. Event-driven, không phải polling

~~~text
MBean gửi JMX Notification
         ↓
NotificationListener callback
         ↓
Spring Integration MessageChannel
~~~

Không cần `@Poller` hay `<int:poller>` trên notification-listening adapter. Thêm poller vào endpoint không phải cách làm callback xuất hiện nhanh hơn.

Chỉ khi **nội bộ downstream** chuyển sang `QueueChannel` thì một poller/consumer có thể cần để rút message từ queue đó; điều này độc lập với JMX subscription mechanism.

### 4.2. Payload và headers

Spring Integration's `NotificationListeningMessageProducer` phát Spring message có **payload là chính đối tượng `Notification`**. Với handback không null, adapter đưa handback vào một JMX-related header (xem `JmxHeaders.NOTIFICATION_HANDBACK` ở API phù hợp).

Trước khi gửi sang Kafka/HTTP/JSON, nên **transform Notification thành DTO** có các trường ổn định. Không đưa raw `Notification.getSource()` hoặc `userData` trực tiếp vào một remote transport mà không có converter/schema/trust policy.

### 4.3. Không có ACK hoặc replay theo kiểu message broker

JMX notification tiêu chuẩn không tự cung cấp:

- Subscription backlog bền trên ổ đĩa;
- MQTT QoS 1/2, `PUBACK`, retained message;
- JMS transaction/ack mode;
- Kafka offset và replay;
- Dead-letter queue tự động;
- Mã event ID duy nhất toàn hệ thống.

Nếu consumer chậm/offline hoặc process chết, **JMX Notification có thể bị bỏ lỡ**. Khi cần bảo đảm lưu trữ, hãy persist vào database/inbox hoặc chuyển sự kiện sang hạ tầng message broker phù hợp, thiết kế idempotency/recovery ở application.

## 5. XML namespace: cấu hình tối thiểu

Spring Integration cung cấp namespace `int-jmx` và phần tử:

~~~xml
<int-jmx:notification-listening-channel-adapter
    id="queueNotificationListener"
    channel="jmxNotifications"
    object-name="demo.integration:type=QueueHealth,name=Orders"/>
~~~

Adapter mặc định tìm MBeanServer bean có tên `mbeanServer`. Với Spring XML, `<context:mbean-server/>` thường tạo bean với tên phù hợp; nếu muốn dùng server khác, đặt attribute `mbean-server`.

Ví dụ context XML rút gọn:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-jmx="http://www.springframework.org/schema/integration/jmx"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd
          http://www.springframework.org/schema/context
          https://www.springframework.org/schema/context/spring-context.xsd
          http://www.springframework.org/schema/integration
          https://www.springframework.org/schema/integration/spring-integration.xsd
          http://www.springframework.org/schema/integration/jmx
          https://www.springframework.org/schema/integration/jmx/spring-integration-jmx.xsd">

    <context:mbean-server id="mbeanServer"/>

    <int:channel id="jmxNotifications"/>

    <int-jmx:notification-listening-channel-adapter
        id="queueNotificationListener"
        mbean-server="mbeanServer"
        channel="jmxNotifications"
        object-name="demo.integration:type=QueueHealth,name=Orders"/>
</beans>
~~~

Snippet tạo server/channel/adapter, **chưa tạo publisher MBean**. Phải có MBean khớp `ObjectName` đã được đăng ký trên **cùng** server; nếu không, adapter không có nguồn sự kiện cần lắng nghe. Phần Java ở mục 10 sẽ tạo publisher MBean.

### 5.1. NotificationFilter và handback trong XML

Adapter hỗ trợ tham chiếu tới `NotificationFilter` và handback object:

~~~xml
<int-jmx:notification-listening-channel-adapter
    id="queueNotificationListener"
    channel="jmxNotifications"
    mbean-server="mbeanServer"
    object-name="demo.integration:type=QueueHealth,name=Orders"
    notification-filter="queueDepthFilter"
    handback="queueListenerContext"/>
~~~

`queueDepthFilter` và `queueListenerContext` ở đây là **bean references cần được định nghĩa** trong context. Đây là snippet thay thế cho adapter tối thiểu ở mục trước, không tạo hai adapter cùng tên. Tên/semantics của hai attributes đã có trong JMX namespace; việc filter áp dụng tại callback không thay schema validation, authorization hoặc lỗi downstream.

### 5.2. Định danh bean và JMX object là hai không gian tên

~~~text
Spring adapter bean ID:  queueNotificationListener
Spring channel ID:       jmxNotifications
JMX ObjectName:          demo.integration:type=QueueHealth,name=Orders
Spring MBeanServer bean: mbeanServer
~~~

Sửa `id` của channel không làm đổi `ObjectName` trong JMX server; sửa `ObjectName` có thể khiến adapter đăng ký nhầm MBean hoặc không nhận event dù Spring channel vẫn hoạt động.

## 6. Lắng nghe nhiều MBeans bằng ObjectName pattern

Với nhiều MBeans:

~~~text
demo.integration:type=QueueHealth,name=Orders
demo.integration:type=QueueHealth,name=Billing
demo.integration:type=QueueHealth,name=Notifications
~~~

Có thể dùng pattern:

~~~xml
<int-jmx:notification-listening-channel-adapter
    id="allQueueNotifications"
    channel="jmxNotifications"
    object-name="demo.integration:type=QueueHealth,name=*"/>
~~~

Đây là một khả năng **riêng của notification-listening adapter**: một ObjectName pattern có thể đăng ký listener cho các MBeans khớp mẫu. Có thể dùng SpEL danh sách nhiều names/patterns theo XML namespace trong phiên bản hỗ trợ.

### 6.1. Pattern không có nghĩa tự động theo dõi MBeans mới mãi mãi

Điểm quan trọng là thời điểm **resolve và đăng ký listener**. Một adapter có thể tìm nhóm MBeans khớp khi start/refresh, nhưng **không nên mặc định** nó đăng ký tự động với mọi MBean được thêm sau đó trong suốt runtime mà không cần cơ chế refresh. Nếu nhiều MBeans động được tạo/hủy, phải test cụ thể trên Spring Integration version, quản lý re-registration, hoặc cân nhắc nghe `MBeanServerDelegate` để nhận registry changes nếu thật sự cần.

### 6.2. Pattern rộng dễ tạo tải và lộ metadata

Filter `demo.integration:*` hoặc quá rộng có thể kéo theo hàng trăm MBeans phát notifications với types/payloads khác nhau. Hãy giới hạn domain/type và dùng NotificationFilter/flow routing riêng. Cũng không coi việc match pattern là bằng chứng app có quyền quản trị mọi MBean remote.

### 6.3. Một adapter hay nhiều adapters?

| Yêu cầu | Gợi ý |
| --- | --- |
| Nhiều MBeans cùng schema/type và lifecycle | Pattern hoặc danh sách object names trong một adapter. |
| MBeans có nguồn/rights khác nhau | Tách MBeanServerConnection/adapters theo security boundaries. |
| Notifications có schema rất khác nhau | Route theo type/source sang flows riêng. |
| Tải rất lệch giữa các nhóm | Tách channels/queues và chính sách backpressure. |
| Cần vận hành độc lập | Tách endpoints, metrics và lifecycle riêng. |

## 7. Notification payload contract: từ JMX object sang sự kiện nghiệp vụ

Một `Notification` là object tổng quát. Nếu chuyển trực tiếp sang một outbound HTTP gateway hoặc Kafka producer, consumer có thể nhận một biểu diễn Java nội bộ không ổn định, hoặc serializer có thể thất bại với `source`/`userData` chứa object không hỗ trợ.

Nên chuyển sang DTO:

~~~java
public record QueueDepthEvent(
        String eventType,
        String sourceName,
        long sequenceNumber,
        long occurredAtEpochMillis,
        int depth) {
}
~~~

Mapping ví dụ:

~~~text
Notification.type                 -> eventType
Listener configuration / ObjectName -> sourceName
Notification.sequenceNumber       -> sequenceNumber
Notification.timeStamp            -> occurredAtEpochMillis
Notification.userData=Integer     -> depth
~~~

Nếu dùng handback làm source context, nên đặt string/ID ổn định thay vì tham chiếu một service object trong Spring context. Notification `message` chỉ nên dùng cho log/UI, không parse bằng regex làm business schema nếu đã có `userData` có contract rõ.

### 7.1. Sequence không phải durable event ID

Một MBean có thể phát `sequenceNumber=1,2,3,...` trong đời sống của một instance, rồi reset về 1 khi JVM restart. Với nhiều MBeans, sequence cũng không phải một bộ đếm toàn hệ thống. Nếu cần idempotency khi lưu database hoặc đưa Kafka, hãy định nghĩa ID như `(sourceId, sourceBootId, sequenceNumber)` hoặc cấp `eventId` riêng và quản lý collision/retention.

### 7.2. Timestamp và source có thể chưa đáng tin

Đồng hồ có thể thay đổi; remote MBeans không nhất thiết cùng timezone/clock chính xác. `Notification.getSource()` có thể là object/string/ObjectName tùy broadcaster. Do đó log được nên dùng ID cấu hình đã validate và source metadata an toàn, không chỉ cast `getSource()` sang `ObjectName` rồi giả định luôn đúng.

### 7.3. Filter theo type không thay business validation

Ngay cả khi filter chỉ nhận `demo.queue.depth.changed`, `userData` có thể null, sai kiểu hoặc giá trị âm. Flow cần validate `type` và `userData` **trước** khi tạo DTO. Với remote JMX hoặc extension MBeans không tin cậy, không deserialize object graph lạ hoặc log raw userData bừa bãi.


## 8. Dependency và phân biệt Spring Integration 6.x/7.x

Ví dụ tiếp theo sử dụng **Java 17+, Spring Boot và Spring Integration 6.x** với module JMX riêng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-jmx</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Sử dụng BOM của Spring Boot để đồng bộ phiên bản; không trộn tùy tiện major versions của Spring Boot, Spring Framework và Spring Integration.

**Lưu ý quan trọng về Java import:**

| Spring Integration | Class notification listener producer | Chú ý |
| --- | --- | --- |
| 6.x (ví dụ 6.4/6.5) | `org.springframework.integration.jmx.NotificationListeningMessageProducer` | Các ví dụ Java bên dưới dùng import này. |
| 7.x (ví dụ 7.0/7.1) | `org.springframework.integration.jmx.inbound.NotificationListeningMessageProducer` | Package đã chuyển sang `jmx.inbound`; cần điều chỉnh import và kiểm tra compatibility. |

Trong hai dòng sản phẩm này, API ý tưởng vẫn gồm `setServer(...)`, `setObjectName(...)`, `setFilter(...)`, `setHandback(...)` và output channel. Không tự suy rằng copy đoạn mã 6.x rồi chỉ thay version dependency sẽ biên dịch trong 7.x mà không đổi import. Ngoài thay đổi package, cần đối chiếu Java baseline, Spring Boot BOM và các API đã deprecate/moved.

### 8.1. Vì sao không chỉ thêm spring-boot-starter-actuator?

Spring Boot Actuator có các endpoints HTTP/management riêng và có thể expose metrics/health, nhưng không tự biến một JMX Notification thành Spring Integration message. Muốn dùng `notification-listening-channel-adapter` phải có **Spring Integration JMX module** và MBean source phát notification.

### 8.2. Project demo

~~~text
src/main/java/demo/jmxnotifications/
    JmxNotificationsApplication.java
    QueueHealthMBean.java
    QueueHealth.java
    QueueDepthEvent.java
    NotificationSink.java
    JmxNotificationConfiguration.java

src/test/java/demo/jmxnotifications/
    JmxNotificationFlowTest.java
~~~

Các source files cùng package `demo.jmxnotifications`. Trong ví dụ, `QueueHealthMBean` và `QueueHealth` là các kiểu `public` riêng, đặt đúng file Java trùng tên. DTO/sink/config có thể package-private.

## 9. MBean phát Notification: thiết kế Standard MBean

### 9.1. Interface QueueHealthMBean

~~~java
package demo.jmxnotifications;

public interface QueueHealthMBean {

    int getDepth();

    void setDepth(int newDepth);

    void emitHeartbeat();
}
~~~

Theo quy tắc Standard MBean, interface quản trị `QueueHealthMBean` phải public và class `QueueHealth` implement nó. Việc expose `setDepth` là để lab dễ điều khiển từ JConsole/Java test; **production không nên mở public operation có thể giả dữ liệu health** nếu chưa có security và use case rõ.

### 9.2. QueueHealth extends NotificationBroadcasterSupport

~~~java
package demo.jmxnotifications;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueHealth
        extends NotificationBroadcasterSupport
        implements QueueHealthMBean {

    public static final String DEPTH_CHANGED =
            "demo.queue.depth.changed";

    public static final String HEARTBEAT =
            "demo.queue.heartbeat";

    private final AtomicLong nextSequence = new AtomicLong();

    private volatile int depth;

    @Override
    public int getDepth() {
        return depth;
    }

    @Override
    public void setDepth(int newDepth) {
        if (newDepth < 0) {
            throw new IllegalArgumentException(
                    "Queue depth không được âm");
        }

        depth = newDepth;

        var notification = new Notification(
                DEPTH_CHANGED,
                this,
                nextSequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Độ sâu hàng đợi Orders đã thay đổi");

        notification.setUserData(Integer.valueOf(newDepth));
        sendNotification(notification);
    }

    @Override
    public void emitHeartbeat() {
        var notification = new Notification(
                HEARTBEAT,
                this,
                nextSequence.incrementAndGet(),
                System.currentTimeMillis(),
                "QueueHealth heartbeat");

        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                        new String[] { DEPTH_CHANGED, HEARTBEAT },
                        Notification.class.getName(),
                        "QueueHealth notifications")
        };
    }
}
~~~

**Giải thích từng phần:**

- `NotificationBroadcasterSupport` hỗ trợ đăng ký listeners và phát notifications.
- `QueueHealthMBean` cho phép JMX quản lý attribute/operations của Standard MBean.
- `new Notification(type, source, sequence, timeStamp, message)` tạo sự kiện, `setUserData(...)` đính kèm độ sâu.
- `AtomicLong` đảm bảo tăng sequence an toàn khi nhiều threads phát sự kiện cùng một MBean instance.
- `getNotificationInfo()` công bố các notification types dự kiến để công cụ JMX và consumers khám phá.
- `emitHeartbeat()` tạo loại notification khác, phục vụ kiểm thử `NotificationFilter` chỉ nhận `DEPTH_CHANGED`.

**Thread safety:** `volatile int depth` giúp readers thấy giá trị mới, còn `nextSequence.incrementAndGet()` đảm bảo sequence tăng. Nếu cần hai operations cùng phát notifications theo thứ tự tuyệt đối và không race giữa cập nhật state/phát event, nên thêm lock hoặc event-loop riêng; demo chỉ tập trung vào listener.

### 9.3. NotificationBroadcaster không phải durable queue

`sendNotification(notification)` phân phối tới các JMX listeners đã đăng ký tại thời điểm đó. Nếu adapter chưa start, hoặc không đăng ký đúng ObjectName, thông báo có thể không đi vào Spring flow. Không có offline backlog tự động cho listener chưa tồn tại.

### 9.4. Schema type và userData

Trong demo, chỉ `DEPTH_CHANGED` có `Integer` userData. Heartbeat không có userData; nếu flow cố cast mọi notification sang `Integer` mà không kiểm tra type, handler có thể lỗi. Do đó filter ở adapter và validate type/data ở flow đều cần thiết.

## 10. Spring Java configuration: MBeanServer, MBeanExporter và listener producer

Ví dụ cấu hình đầy đủ trong `JmxNotificationConfiguration.java`:

~~~java
package demo.jmxnotifications;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationFilter;
import javax.management.ObjectName;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jmx.JmxHeaders;
import org.springframework.integration.jmx.NotificationListeningMessageProducer;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class JmxNotificationConfiguration {

    private static final String QUEUE_OBJECT_NAME =
            "demo.integration:type=QueueHealth,name=Orders";

    @Bean(name = "mbeanServer")
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    QueueHealth queueHealth() {
        return new QueueHealth();
    }

    @Bean
    MBeanExporter queueHealthExporter(
            MBeanServer mbeanServer,
            QueueHealth queueHealth) {

        var exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(
                QUEUE_OBJECT_NAME, queueHealth));
        return exporter;
    }

    @Bean(name = "jmx.notifications.in")
    MessageChannel jmxNotificationsInput() {
        return new DirectChannel();
    }

    @Bean
    NotificationFilter queueDepthFilter() {
        return notification ->
                QueueHealth.DEPTH_CHANGED
                        .equals(notification.getType());
    }

    @Bean
    NotificationListeningMessageProducer queueNotificationAdapter(
            MBeanServer mbeanServer,
            NotificationFilter queueDepthFilter,
            @Qualifier("jmx.notifications.in")
            MessageChannel output) throws Exception {

        var adapter = new NotificationListeningMessageProducer();

        adapter.setServer(mbeanServer);
        adapter.setObjectName(new ObjectName(QUEUE_OBJECT_NAME));
        adapter.setFilter(queueDepthFilter);
        adapter.setHandback("orders-queue");
        adapter.setOutputChannel(output);

        return adapter;
    }

    @Bean
    NotificationSink notificationSink() {
        return new NotificationSink();
    }

    @Bean
    IntegrationFlow queueNotificationFlow(NotificationSink sink) {
        return IntegrationFlow.from("jmx.notifications.in")
                .handle(Notification.class, (notification, headers) -> {

                    if (!QueueHealth.DEPTH_CHANGED
                            .equals(notification.getType())) {
                        throw new IllegalArgumentException(
                                "Notification type không hợp lệ");
                    }

                    Object data = notification.getUserData();
                    if (!(data instanceof Integer depth) || depth < 0) {
                        throw new IllegalArgumentException(
                                "Độ sâu hàng đợi không hợp lệ");
                    }

                    Object handback = headers.get(
                            JmxHeaders.NOTIFICATION_HANDBACK);

                    String sourceName = handback instanceof String s
                            ? s : "unidentified-queue";

                    sink.record(new QueueDepthEvent(
                            notification.getType(),
                            sourceName,
                            notification.getSequenceNumber(),
                            notification.getTimeStamp(),
                            depth));

                    return null; // One-way event, không có reply
                })
                .get();
    }
}
~~~

**Phạm vi version:** source này dùng import Spring Integration **6.x**. Với 7.x, `NotificationListeningMessageProducer` nằm trong package `org.springframework.integration.jmx.inbound`; đối chiếu version và thay import. `JmxHeaders` là class khác với `NotificationListeningMessageProducer`, không đổi package của tất cả JMX types theo suy đoán.

### 10.1. MBeanExporter và ObjectName phải khớp nhau

`MBeanExporter.setBeans(Map.of(QUEUE_OBJECT_NAME, queueHealth))` đăng ký publisher dưới ObjectName được adapter dùng. Nếu exporter đăng ký tên khác, adapter có thể không nhận sự kiện dù bean `QueueHealth` tồn tại trong Spring context.

Trong môi trường thật, platform MBeanServer có thể đã có MBean cùng ObjectName. Khi đó cần đổi naming hoặc registration policy có chủ đích, không âm thầm ghi đè MBean do service khác quản lý.

### 10.2. Filter và handback

`NotificationFilter` nhận notification từ JMX và chỉ cho phép type `demo.queue.depth.changed`. Heartbeat bị loại ở tầng listener.

`setHandback("orders-queue")` cung cấp context nguồn. Producer đưa handback không null vào JMX-related Spring message header, flow đọc bằng `JmxHeaders.NOTIFICATION_HANDBACK`. Đây **không** phải field `Notification.getUserData()`.

Nếu một adapter dùng ObjectName pattern để nghe nhiều MBeans, dùng cùng một handback string sẽ không tự giúp phân biệt từng MBean. Khi đó cần source context có đủ identity, hoặc dựa trên metadata nguồn được validate và normalize.

### 10.3. DirectChannel và thread ngữ cảnh

`DirectChannel` dispatch handler đồng bộ theo caller thread khi nhận message. Nếu broadcaster sử dụng notification delivery đồng bộ, handler chậm có thể ảnh hưởng thread phát notification. Vì vậy mã demo chỉ ghi vào sink bộ nhớ nhỏ, không gọi DB/HTTP chậm trực tiếp.

Trong production, nên cân nhắc `ExecutorChannel` có queue giới hạn, hoặc nhanh chóng ghi vào durable inbox rồi xử lý ở worker. Nhưng chuyển sang executor không tạo durability và còn cần error handling async.

### 10.4. Vòng đời exporter và adapter

Có thể xảy ra trình tự:

~~~text
Spring context tạo QueueHealth
Spring tạo MBeanExporter
MBeanExporter đăng ký ObjectName
NotificationListeningMessageProducer start/refresh
JMX listener được đăng ký
MBean phát Notification
Spring flow nhận Message<Notification>
~~~

Thứ tự khởi tạo giữa exporter và endpoint là chi tiết lifecycle cần kiểm chứng ở deployment. Implementation của listener producer có logic liên quan `ContextRefreshedEvent` vì MBeanExporter có thể hoàn tất việc export sau thời điểm start ban đầu; đừng tự gọi `adapter.handleNotification(...)` lúc khởi động để “vá” sự kiện chưa được đăng ký.

### 10.5. Không tạo MBeanServer thứ hai ngoài ý muốn

`ManagementFactory.getPlatformMBeanServer()` dùng platform server của JVM. Nếu bạn dùng XML `<context:mbean-server/>` hoặc nhiều Spring contexts, cần đảm bảo exporter và listener cùng tham chiếu **đúng server**. Cùng ObjectName nhưng ở **hai MBeanServers khác nhau** là hai MBeans khác nhau, không có notification chéo tự động.

## 11. DTO và sink để kiểm thử flow

### 11.1. QueueDepthEvent.java

~~~java
package demo.jmxnotifications;

record QueueDepthEvent(
        String eventType,
        String sourceName,
        long sequenceNumber,
        long occurredAtEpochMillis,
        int depth) {
}
~~~

DTO này dùng các kiểu đơn giản, dễ serialize và lưu trữ. `eventType` có contract riêng, `sourceName` đến từ handback được cấu hình, `sequenceNumber` không phải event ID bền vững qua restart.

### 11.2. NotificationSink.java

~~~java
package demo.jmxnotifications;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class NotificationSink {

    private final List<QueueDepthEvent> events =
            new CopyOnWriteArrayList<>();

    void record(QueueDepthEvent event) {
        events.add(event);
    }

    List<QueueDepthEvent> snapshot() {
        return List.copyOf(events);
    }

    void clear() {
        events.clear();
    }
}
~~~

`NotificationSink` chỉ để minh họa/test; dữ liệu mất khi JVM restart. Đối với event quan trọng, đưa vào database/outbox hoặc broker có replay theo SLA, và quản lý idempotency/error handling.

### 11.3. Application entry point

~~~java
package demo.jmxnotifications;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmxNotificationsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                JmxNotificationsApplication.class, args);
    }
}
~~~

MBean exporter/adapter/flow được phát hiện bằng component scanning trong cùng package. Lệnh `queueHealth.setDepth(25)` có thể được gọi từ service nội bộ hoặc qua JMX management operation trong lab. Không tự giả định Spring Boot sẽ định kỳ phát notifications chỉ vì đã tạo MBean.

## 12. Chạy thử một notification

Giả sử Spring context đã sẵn sàng và bạn có bean `QueueHealth`:

~~~java
queueHealth.setDepth(25);
~~~

MBean tạo:

~~~text
type            = demo.queue.depth.changed
sequenceNumber  = 1
timeStamp       = thời gian JVM phát sự kiện
message         = "Độ sâu hàng đợi Orders đã thay đổi"
userData        = Integer(25)
~~~

JMX listener producer nhận và gửi payload `Notification` vào `jmx.notifications.in`. Spring flow validate, đọc handback `orders-queue` và ghi:

~~~text
QueueDepthEvent(
    eventType = "demo.queue.depth.changed",
    sourceName = "orders-queue",
    sequenceNumber = 1,
    occurredAtEpochMillis = ...,
    depth = 25
)
~~~

Đây là **pipeline một chiều**, không phải request-reply. Không có JMX ACK nào được gửi trở lại MBean theo cơ chế này. Nếu một business service muốn gọi operation MBean và nhận kết quả, cần outbound operation-invoking gateway thay vì notification listener.

### 12.1. Heartbeat sẽ bị filter

Khi gọi:

~~~java
queueHealth.emitHeartbeat();
~~~

MBean phát loại `demo.queue.heartbeat`. Adapter đã cấu hình `NotificationFilter` chỉ cho `DEPTH_CHANGED` nên heartbeat không đi vào `jmx.notifications.in` (theo semantics listener/filter). Nếu bạn muốn lưu cả heartbeat, đổi filter và route hai types tới flows tương ứng, không bỏ validate schema.

### 12.2. Các đối tượng Message và Notification khác nhau

~~~text
JMX Notification:
    type, source, sequenceNumber, timeStamp, message, userData

Spring Message<Notification>:
    payload = Notification object
    headers = Spring metadata + optional JMX handback
~~~

Không giả định `Notification.getSequenceNumber()` là Spring `MessageHeaders.ID` hoặc rằng `Notification.getSource()` đã được chuyển thành một business ID an toàn. Khi chuyển sang downstream message broker, hãy ghi contract map rõ ràng.

## 13. XML và Java configuration: nên chọn cái nào?

| Khía cạnh | XML namespace | Java @Bean |
| --- | --- | --- |
| Khai báo adapter | `<int-jmx:notification-listening-channel-adapter>` | `new NotificationListeningMessageProducer()`. |
| ObjectName | Attribute `object-name` | `setObjectName(new ObjectName(...))`. |
| MBeanServer | `mbean-server` hoặc mặc định bean `mbeanServer` | `setServer(MBeanServerConnection)`. |
| Notification filter | `notification-filter` reference | `setFilter(NotificationFilter)`. |
| Handback | `handback` reference | `setHandback(Object)`. |
| Output | Attribute `channel` | `setOutputChannel(MessageChannel)`. |
| Flow processing | `<int:service-activator>`, router, transformer | `IntegrationFlow.from(...).handle(...)`. |
| Version migration | XSD namespace/API compatibility cần kiểm tra. | Package Java imports thay đổi ở 7.x. |

Chọn XML nếu dự án đã dùng namespace integration rõ ràng. Chọn Java DSL/`@Bean` nếu muốn cấu hình type-safe cùng Spring Boot và các services khác. **Tránh cấu hình cùng một listener hai lần** bằng XML và Java trên cùng ObjectName nếu không muốn hai deliveries.

## 14. Dùng NotificationFilter, Spring Filter và Router đúng tầng

~~~mermaid
flowchart LR
    M[("MBean notifications")]
    NF{"JMX NotificationFilter"}
    AD["NotificationListeningMessageProducer"]
    CH["MessageChannel"]
    VAL{"Validate Notification"}
    ROUTE{"Spring router theo type"}
    A["Queue alerts"]
    H["Health metrics"]
    E["Quarantine"]
    M --> NF
    NF -->|"Accepted"| AD --> CH --> VAL --> ROUTE
    VAL -->|"Malformed"| E
    ROUTE -->|"queue.depth.changed"| A
    ROUTE -->|"heartbeat"| H
~~~

**Ba lớp có trách nhiệm khác nhau:**

1. **JMX NotificationFilter:** lọc sớm theo type/metadata, tránh đưa mọi notification vào Spring.
2. **Spring Filter/Validator:** kiểm hợp đồng payload/userData/source, reject event không hợp lệ.
3. **Spring Router:** chọn pipeline nghiệp vụ dựa trên loại notification đã normalize.

Trong ví dụ Java hiện tại, filter chỉ cho `depth.changed` nên nhánh heartbeat không xuất hiện. Sơ đồ minh họa trường hợp mở filter rộng hơn và route hai types; không phải cấu hình được tạo tự động bởi demo.

### 14.1. Không dựa vào message text để route

`Notification.getMessage()` là text diễn giải, có thể bị đổi ngôn ngữ/câu chữ. Hãy dùng `getType()` hoặc `userData` có schema version rõ, cùng identity MBean đã kiểm chứng.

### 14.2. Filter phải nhẹ

Một `NotificationFilter` chạy ở ranh giới callback, nên làm điều kiện nhanh (so sánh type/attribute). Không gọi database/HTTP hoặc chặn trong filter, vì có thể làm nghẽn đường gửi notification của MBean.

### 14.3. MBean có thể khai báo nhiều notification types

`getNotificationInfo()` mô tả các loại mà MBean có thể phát, nhưng listener vẫn phải kiểm tra mỗi notification thực tế. Không coi mảng advertised types là bảo đảm mỗi `userData` đúng class hoặc mọi thông tin đều có schema.


## 15. JUnit integration test với MBeanServer nội bộ

Một đặc điểm hữu ích của JMX là bạn có thể kiểm tra end-to-end **trong cùng JVM**, không cần MQTT broker, Kafka cluster hay remote JMX connector. Test nạp Spring context chứa:

- `QueueHealth` là MBean publisher;
- `MBeanExporter` đăng ký MBean với platform `MBeanServer`;
- `NotificationListeningMessageProducer` nhận JMX callbacks;
- `DirectChannel` cùng `IntegrationFlow`;
- `NotificationSink` ghi dữ liệu đã normalize trong RAM.

Khác với test giả lập bằng `input.send(...)`, test này phát notification thật qua `NotificationBroadcasterSupport.sendNotification(...)` và xác nhận listener đã được đăng ký thành công. Nó vẫn **không** chứng minh remote JMX delivery hoặc downstream persistence.

### 15.1. JmxNotificationFlowTest.java

~~~java
package demo.jmxnotifications;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.ObjectName;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.jmx.NotificationListeningMessageProducer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = JmxNotificationConfiguration.class)
class JmxNotificationFlowTest {

    @Autowired
    QueueHealth queueHealth;

    @Autowired
    NotificationSink sink;

    @Autowired
    MBeanServer mbeanServer;

    @Autowired
    NotificationListeningMessageProducer queueNotificationAdapter;

    @Autowired
    @Qualifier("jmx.notifications.in")
    MessageChannel input;

    @BeforeEach
    void reset() {
        sink.clear();
    }

    @Test
    void mBeanIsRegisteredUnderExpectedObjectName()
            throws Exception {

        var name = new ObjectName(
                "demo.integration:type=QueueHealth,name=Orders");

        assertTrue(mbeanServer.isRegistered(name));
        assertTrue(queueNotificationAdapter.isRunning());
    }

    @Test
    void depthNotificationPassesThroughJmxAdapterAndFlow() {
        queueHealth.setDepth(25);

        assertEquals(1, sink.snapshot().size());

        QueueDepthEvent event = sink.snapshot().get(0);

        assertEquals(QueueHealth.DEPTH_CHANGED,
                event.eventType());
        assertEquals("orders-queue", event.sourceName());
        assertEquals(25, event.depth());
        assertTrue(event.sequenceNumber() > 0);
        assertTrue(event.occurredAtEpochMillis() > 0);
    }

    @Test
    void heartbeatIsRejectedByJmxNotificationFilter() {
        queueHealth.emitHeartbeat();

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void malformedNotificationIsRejectedBySpringFlow() {
        var wrong = new Notification(
                QueueHealth.DEPTH_CHANGED,
                "malformed-source",
                99L);
        wrong.setUserData("not-an-integer");

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder
                        .withPayload(wrong)
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void stopUnregistersListenerThenStartRestoresIt() {
        queueNotificationAdapter.stop();

        try {
            assertFalse(queueNotificationAdapter.isRunning());

            queueHealth.setDepth(30);
            assertTrue(sink.snapshot().isEmpty());
        } finally {
            queueNotificationAdapter.start();
        }

        queueHealth.setDepth(31);
        assertEquals(1, sink.snapshot().size());
        assertEquals(31, sink.snapshot().get(0).depth());
    }
}
~~~

**Giới hạn và lưu ý thực hành:**

- Test dùng Spring Integration **6.x** import; nếu dùng 7.x cần thay package của producer tương ứng.
- Với `DirectChannel` và broadcaster mặc định không truyền executor khác, callback/lưu sink thực hiện đồng bộ trong demo. Nếu thay bằng executor, phải dùng await/latch chứ không assert ngay.
- Mỗi test method xóa dữ liệu sink nhưng **không reset** sequence của publisher. Vì thế chỉ assert sequence dương, không assert một event luôn có sequence bằng 1.
- Test stop/start có `try/finally` để tránh để endpoint dừng nếu assertion fail. Test suite song song có thể ảnh hưởng lifecycle; nên chạy độc lập hoặc dùng test context riêng.
- Khi MBeanServer là platform server, các tests khác cùng JVM có thể đụng ObjectName. `MBeanExporter` phải unregister đúng MBean do nó quản lý khi context đóng; dùng tên riêng cho các test suites khác nhau.
- `assertThrows(RuntimeException.class)` cho phép Spring bọc handler exception. Vòng QA chuyên sâu cần kiểm tra cause chain/errorChannel trên version thực tế.

### 15.2. Test có nguồn phát thật khác fake Message test

| Test | Nguồn | Điều được xác minh |
| --- | --- | --- |
| `input.send(Message<Notification>)` | Fake Spring message. | DTO mapping, validation và handler wiring nội bộ. |
| `queueHealth.setDepth(...)` | JMX MBean broadcaster. | MBean registration, listener/filter, adapter → channel → handler. |
| JConsole/JMX client gọi operation | JMX management client. | Operation/attribute exposure và end-to-end event local/remote. |
| Remote JMX connector fault test | Network connection tới JMX server khác. | Auth, connection loss, listener registration và recovery. |

### 15.3. Test callback timing khi không dùng DirectChannel

Nếu đổi output sang `ExecutorChannel`, hãy sử dụng `CountDownLatch`, Awaitility hoặc polling assertion có timeout cho **trạng thái test**, không dùng `Thread.sleep(1000)` làm bằng chứng hệ thống đã xử lý xong. Tách metric “adapter nhận được” và “business handler hoàn tất”.

## 16. Thử nghiệm bằng JConsole hoặc Java JMX client

JConsole là một công cụ JDK có thể kết nối tới JVM được quản lý. Trong môi trường lab do người dùng kiểm soát, có thể:

1. Chạy Spring Boot application có `JmxNotificationConfiguration`.
2. Mở JConsole và kết nối **local JVM** (không mở remote management port công khai).
3. Trong tab **MBeans**, tìm `demo.integration:type=QueueHealth,name=Orders`.
4. Xác nhận attribute `Depth` và operation `emitHeartbeat` có mặt. Setter `setDepth(...)` có thể xuất hiện như thao tác ghi attribute `Depth`, tùy giao diện công cụ.
5. Đặt `Depth` thành 25 và quan sát `QueueDepthEvent` trong ứng dụng nếu đã cấu hình output logging/sink visibility.
6. Gọi `emitHeartbeat` rồi xác nhận flow chỉ nhận depth notifications do filter ở adapter.

**Lưu ý:** ví dụ `NotificationSink` chỉ lưu trong RAM, không tự phát log ra console. Muốn nhìn kết quả trực tiếp, thêm logging/meter đúng chỗ hoặc dùng test `sink.snapshot()`. Việc JConsole thấy MBean **không** chứng minh listener adapter đã đăng ký thành công; phải kiểm tra handler output/metrics.

### 16.1. Java JMX API gọi operation qua MBeanServer

Nếu muốn test mà không mở GUI:

~~~java
import java.lang.management.ManagementFactory;

import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "demo.integration:type=QueueHealth,name=Orders");

server.setAttribute(
        name,
        new Attribute("Depth", Integer.valueOf(25)));

Object currentDepth =
        server.getAttribute(name, "Depth");

System.out.println("Depth = " + currentDepth);
~~~

Snippet là một client JMX local. Nó hoạt động khi MBean đã đăng ký và attribute được export như kỳ vọng, không tự tạo Spring context. Nếu cần test qua `NotificationListeningMessageProducer`, phải khởi động ứng dụng listener cùng MBeanServer phù hợp trước khi set attribute.

### 16.2. Test NotificationFilter độc lập

~~~java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter filter = notification ->
        QueueHealth.DEPTH_CHANGED.equals(notification.getType());

Notification depth = new Notification(
        QueueHealth.DEPTH_CHANGED, "queue", 1L);

Notification heartbeat = new Notification(
        QueueHealth.HEARTBEAT, "queue", 2L);

assert filter.isNotificationEnabled(depth);
assert !filter.isNotificationEnabled(heartbeat);
~~~

Đây là ví dụ Java ngắn cho unit test; ở JUnit nên dùng `assertTrue/assertFalse` thay cho Java `assert` vì assertions có thể bị tắt khi JVM không bật `-ea`. Test filter độc lập không thay end-to-end MBeanServer test ở mục 15.

## 17. Lifecycle của listener và MBean registration

### 17.1. Khi nào adapter đăng ký listener?

Spring-managed `NotificationListeningMessageProducer` là một endpoint có start/stop lifecycle. Khi start, nó tìm MBean(s) theo `ObjectName` và đăng ký `NotificationListener` với `MBeanServerConnection`; khi stop, nó tháo đăng ký.

Điều này khác `MBeanExporter`, vốn có trách nhiệm tạo hoặc đăng ký MBean vào server. Để nhận notification:

~~~text
MBean exists with correct ObjectName
    +
Listener endpoint is started
    +
NotificationFilter accepts type
    +
MessageChannel has a consumer
    =
Notification can reach the Spring Integration handler
~~~

“Có adapter bean” chưa đủ; “có MBean” cũng chưa đủ nếu listener chưa attach.

### 17.2. MBean được đăng ký sau khi adapter khởi động

Đây là tình huống thường gặp trong ứng dụng có dynamic MBeans. Adapter có thể không thấy MBean tại thời điểm đăng ký ban đầu. Spring Integration listener producer có hỗ trợ tình huống MBeanExporter khởi tạo muộn trong Spring context, nhưng không nên suy ra nó theo dõi **mọi future registrations** vô hạn.

Nếu MBeans sinh/xóa thường xuyên:

- Thiết kế cơ chế đăng ký lại khi MBean xuất hiện;
- Có thể nghe registry change notifications từ `MBeanServerDelegate` nếu phù hợp JMX API;
- Hoặc stop/start/recreate adapter theo một lifecycle controller được kiểm soát;
- Test cả unregister/register lại dưới cùng ObjectName;
- Tránh tạo listeners trùng khi rebind dẫn tới duplicate events.

### 17.3. Stop không hủy các notifications đã xử lý trước đó

`adapter.stop()` thường tháo listener, không rollback side effects mà Spring handler đã thực hiện. Trong-flight callback có thể đã bắt đầu trước lúc stop; cần xác định policy drain/shutdown ở app. Không dùng stop/start để xây retry hoặc exactly-once semantics.

### 17.4. Context refresh và MBeanExporter

Trong Spring application, exporter và listener có thể tham gia nhiều phase khác nhau. Implementation producer có xử lý `ContextRefreshedEvent` để tránh trường hợp MBean chưa tồn tại khi listener start. Tuy nhiên behavior thực tế cần kiểm tra trên version và bean graph. Khi gặp thiếu notification sau startup, ghi DEBUG logs cho JMX adapter/object name resolution để xác định đã subscribe những MBeans nào.

### 17.5. Tài nguyên cần cleanup

| Tài nguyên | Ai sở hữu? | Dọn khi nào? |
| --- | --- | --- |
| `NotificationListener` registration | Inbound adapter. | Stop/destroy endpoint. |
| `MBean` registration | MBeanExporter hoặc code register thủ công. | Context close/explicit unregister. |
| `MBeanServer` platform | JVM/management runtime. | Thường không tự destroy toàn platform server. |
| `JMXConnector` remote | Code tạo connector hoặc Spring bean tương ứng. | Close khi shutdown, reconnect/failure recovery. |
| Spring channels/executors | Spring context. | Stop/drain, executor shutdown. |
| Business persistence | Repository/DB. | Retention và transaction policy, không xóa khi listener stop. |

## 18. Remote JMX: MBeanServerConnection, bảo mật và kết nối

`NotificationListeningMessageProducer.setServer(...)` nhận một `MBeanServerConnection`; với MBeanServer local, `MBeanServer` cũng là một `MBeanServerConnection`. Nếu dùng remote JMX, cần tạo một connection có bảo mật phù hợp và truyền vào adapter.

Ví dụ API **minh họa**, không phải production-ready connector configuration:

~~~java
import java.util.Map;

import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

// Cấu hình URL/credentials/SSL properties phải đến từ
// hạ tầng bảo mật, không hardcode secrets vào source.
JMXServiceURL url = new JMXServiceURL(
        "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi");

JMXConnector connector = JMXConnectorFactory.connect(url);
MBeanServerConnection remote = connector.getMBeanServerConnection();

// adapter.setServer(remote);
// ... Khi không còn dùng, phải connector.close().
~~~

**Không chạy đoạn remote demo này trên cổng công khai thiếu authentication/TLS.** URL chỉ minh họa API, local test server không tự tồn tại. Remote JMX over RMI có thể cần nhiều ports, cấu hình firewall và TLS/cert riêng; `localhost:9999` không đảm bảo hoạt động trong Docker/Kubernetes nếu connector/RMI hostname sai.

### 18.1. Nguyên tắc bảo mật remote JMX

1. Không expose remote JMX unauthenticated ra Internet.
2. Yêu cầu TLS và xác minh server identity/chứng chỉ theo chính sách hệ thống.
3. Bảo vệ credentials trong secrets và không log chúng.
4. Giới hạn network access, firewall, roles và permissions theo MBean/operation.
5. Hạn chế deserialization/cấu hình class loading không tin cậy; `userData` có thể là object graph phức tạp.
6. Chỉ subscribe MBeans cần thiết; không tự cho phép ObjectName pattern quá rộng.
7. Kiểm tra audit access, connector disconnect/reconnect và resource cleanup.
8. Cân nhắc thay remote JMX bằng agent export metrics/events sang broker/HTTPS khi security/network topology không phù hợp.

### 18.2. Remote listener không tự replay sau mất mạng

Một JMX connector bị disconnect không mặc định lưu notification backlog cho client vắng mặt. Sau reconnect, client có thể cần đăng ký lại listener; notifications trong thời gian gián đoạn có thể đã mất. Nếu cần event history, phải thêm durable store ở MBean source hoặc forwarding agent, không trông đợi connector tự phục hồi tất cả events.

### 18.3. Local JMX và remote JMX: không nên gộp SLA

| Tiêu chí | Local platform MBeanServer | Remote JMX connector |
| --- | --- | --- |
| Network dependency | Không cần remote socket cho callback nội JVM. | Có network/auth/firewall. |
| Latency | Thường thấp. | Có serialize/RMI/remote callback cost. |
| Fault modes | App/MBean lifecycle, thread blocking. | Thêm network partitions, timeouts, connector lifecycle. |
| Security boundary | JVM process và JMX management exposure. | Transport security, credentials và remote permissions. |
| Replay/durability | Không tự có. | Không tự có. |

## 19. Backpressure: callback không phải worker queue

Trong bản demo, notification tới `DirectChannel` và handler chạy đồng bộ. Với `NotificationBroadcasterSupport` không cung cấp executor tùy chỉnh, việc gọi listeners có thể diễn ra trên đường phát notification. Nếu handler gọi HTTP, query DB chậm hoặc ghi file lớn, thread của MBean có thể bị ảnh hưởng.

~~~mermaid
flowchart LR
    M["MBean phát Notification"]
    AD["JMX listener adapter"]
    DIRECT["DirectChannel"]
    BLOCK["Handler gọi downstream chậm"]
    M --> AD --> DIRECT --> BLOCK
~~~

### 19.1. Đổi sang ExecutorChannel có giới hạn

Một lựa chọn là `ExecutorChannel` với thread pool/queue bounded theo workload. Khi đó producer có thể giảm thời gian bị chặn, nhưng phải xác định:

- Pool size tối đa và queue capacity;
- Chính sách khi executor từ chối task (reject/backpressure);
- Error channel cho exception trên worker thread;
- Graceful shutdown và drain;
- Monitoring backlog và latency;
- Không mất notification khi app crash trước khi xử lý xong.

**ExecutorChannel không phải durable message broker.** Nếu cần bảo đảm notification không mất qua restart, phải ghi nhanh vào durable inbox/outbox hoặc đẩy tới queue/broker phù hợp và chấp nhận semantic tương ứng.

### 19.2. QueueChannel và poller chỉ là downstream decision

Một `QueueChannel` có thể buffer notifications, sau đó một polling endpoint đọc queue. Khi đó poller là của **Spring internal channel**, không phải notification-listening adapter. Queue RAM mặc định không bền vững và có thể tạo backpressure/memory pressure nếu không giới hạn capacity.

### 19.3. Gộp/coalesce events có chủ đích

Đối với health metrics biến đổi liên tục, có thể chỉ cần snapshot mới nhất thay vì mỗi notification; coalescing/rate limiting giúp giảm tải. Tuy nhiên không được gộp tùy tiện cảnh báo critical hay audit events cần phân biệt từng occurrence. Quy tắc sampling và lost-event tolerance phải được ghi thành SLA rõ ràng.

## 20. Error handling khi callback hoặc downstream thất bại

~~~mermaid
flowchart TD
    JMX["JMX Notification"]
    FIL{"NotificationFilter"}
    AD["Listening Adapter"]
    VAL{"Validate payload/type/source"}
    HANDLE["Business handler"]
    OK["Audit / metrics / outbox"]
    ERR["Error channel/quarantine/alert"]
    JMX --> FIL
    FIL -->|"Không match"| DROP["Ignored"]
    FIL -->|"Match"| AD --> VAL
    VAL -->|"Hợp lệ"| HANDLE --> OK
    VAL -->|"Không hợp lệ"| ERR
    HANDLE -. "Downstream exception" .-> ERR
~~~

| Lỗi | Ví dụ | Xử lý |
| --- | --- | --- |
| Chưa đăng ký listener | MBean chưa export, adapter chưa start. | Kiểm objectName/server/lifecycle, test start order. |
| Notification type bị filter | Heartbeat gửi nhưng filter chỉ nhận depth. | Điều chỉnh type/filter theo use case. |
| `userData` sai schema | Integer expected nhưng nhận String/null. | Reject/quarantine, không cast mù. |
| Channel không có subscriber | `DirectChannel` chưa có handler khi callback tới. | Chỉnh wiring/lifecycle, monitoring delivery failures. |
| Handler blocking | HTTP/DB chậm trên callback thread. | Bounded async + durable handoff khi cần. |
| Handler ném exception | DB outage hoặc mapping lỗi. | Error routing, retry ở nguồn bền, không tin có JMX redelivery. |
| Remote JMX disconnect | TCP/RMI/credential/cert lỗi. | Reconnect/re-register, báo event gap. |
| MBean bị unregister | Adapter đang nghe ObjectName không còn. | Rebind theo dynamic registry, test lifecycles. |
| Duplicate registration | Cùng listener attach hai lần. | Kiểm id/bean lifecycle và idempotency. |

### 20.1. Spring error channel không có nghĩa JMX sẽ phát lại

Spring Integration có error handling như `ErrorMessage`/`errorChannel` theo endpoint/channel configuration. Nhưng khi JMX callback đã phát notification, không tồn tại chuẩn mặc định “JMX transaction rollback rồi redeliver”. Một exception Java downstream có thể đi theo đường callback/error handler tùy version và channel; **không** bảo đảm MBean tự lưu message để retry.

Với events quan trọng, ghi vào inbox có transaction/idempotency hoặc đưa vào messaging broker bền vững; định nghĩa rõ retry source và poison message policy.

### 20.2. Retry phải gắn với business ID hoặc trạng thái bền

Nếu ứng dụng nhận lại cùng alarm sau restart, sequence có thể reset. Không dùng chỉ `sequenceNumber` làm khóa duy nhất. Với mỗi alert, có thể tạo business ID dựa trên source identity, instance epoch và sequence, hoặc payload có event ID do publisher quản lý, rồi thiết kế retention/duplicate policy thích hợp.

### 20.3. Không retry vô hạn notification hỏng

Một `Notification` có `userData` sai kiểu sẽ không tự được sửa khi retry. Quarantine có reason code, source type, sequence/time và payload an toàn; tránh vòng lặp phát ngược về chính MBean gây storm.


## 21. Thiết kế observability cho JMX listener

Một listener có thể “đang chạy” nhưng không nhận notification vì sai ObjectName, MBean chưa đăng ký, filter quá hẹp hoặc connector đã mất. Vì vậy chỉ đo `application_up=1` không đủ.

### 21.1. Metric/field nên có

| Metric/field đề xuất | Mục đích |
| --- | --- |
| `jmx_listener_running{adapter}` | Endpoint có đang chạy theo Spring lifecycle. |
| `jmx_registered_mbeans{adapter}` | Số MBeans khớp/được listener đăng ký tại thời điểm quan sát. |
| `jmx_notifications_received_total{type}` | Số notifications đi qua listener/filter. |
| `jmx_notifications_filtered_total{type}` | Số notifications bị loại, nếu implementation cung cấp hook quan sát phù hợp. |
| `jmx_notification_validation_errors_total` | Số payload/type/source sai contract. |
| `jmx_message_channel_delivery_errors_total` | Lỗi dispatch vào Spring channel. |
| `jmx_remote_connector_reconnects_total` | Giám sát remote JMX instability. |
| `jmx_notification_processing_latency_ms` | Thời gian handler xử lý sau khi nhận. |
| `jmx_notification_business_retries_total` | Retry của business handoff, tách khỏi JMX delivery. |
| `jmx_notification_gap_detected_total` | Khoảng trống sequence được **phát hiện**, không phải số messages chắc chắn đã mất. |
| `outbox_backlog_count` | Độ lớn công việc durable chưa chuyển tiếp. |
| `outbox_oldest_age_seconds` | Độ trễ xử lý downstream. |

Tên metric trên là **đề xuất thiết kế**, không phải tên được Spring Integration JMX mặc định tự tạo. Với Spring Integration management/metrics version phù hợp có thể thu thập thông tin endpoint/channel, nhưng cần phân biệt những metrics do framework cung cấp và những metrics do business handler tự ghi.

### 21.2. Đừng dùng ObjectName/sequence làm metric labels không giới hạn

Nếu mỗi tenant/device/MBean có một ObjectName riêng, đưa toàn bộ ObjectName hoặc sequence vào metric label có thể gây cardinality rất cao. Nên dùng nhóm adapter, loại notification và role/namespace có số lượng giới hạn; event IDs chi tiết thuộc structured log/tracing có access control.

### 21.3. Đo khoảng trống sequence có giới hạn

Nếu cùng MBean instance phát sequence 100, 101, 103, việc thiếu 102 **có thể** là notification bị filter hoặc bỏ lỡ. Nhưng nếu MBean restart và sequence reset, hoặc nhiều types cùng dùng một sequence, cách kiểm tra cần nhiều context hơn. Không tự kết luận mọi gap là “lost message” nếu không biết broadcaster semantics và các filters.

### 21.4. Kiểm tra readiness thực

Một bước readiness test nên xác minh:

1. MBeanServerConnection còn truy cập được;
2. ObjectName cần nghe đang tồn tại;
3. Listener endpoint đang chạy;
4. Có thể phát một notification thử nghiệm được kiểm soát và quan sát flow nhận, nếu SLA yêu cầu;
5. Downstream broker/DB/inbox hoạt động hoặc có buffering phù hợp.

Không phát health-test notification liên tục vào production business stream nếu nó có thể kích hoạt alert thật. Dùng notification type riêng hoặc test instance.

## 22. Sổ tay troubleshooting

| Triệu chứng | Cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| `QueueHealth` bean có nhưng flow không thấy event | Bean có được export thành MBean đúng ObjectName? | Xác minh `MBeanExporter` và `mbeanServer.isRegistered(...)`. |
| JConsole thấy MBean nhưng listener không nhận | Adapter đang nghe đúng MBeanServer và ObjectName? | Kiểm `setServer`/`object-name`, endpoint running. |
| Không nhận ngay sau startup | Listener start trước khi MBean export hoặc event phát quá sớm. | Kiểm lifecycle/context refreshed, startup readiness. |
| Heartbeat không tới | `NotificationFilter` chỉ nhận type depth. | Đó có thể là hành vi đúng; xem type filter contract. |
| `userData` ClassCastException | MBean phát kiểu dữ liệu khác schema. | Validate `instanceof`/version thay vì cast. |
| Không thấy `handback` trong payload | Handback thuộc callback/header, không phải userData. | Đọc đúng JMX header/API version. |
| ObjectName pattern match sai | Domain/key properties/case/quoting không khớp. | Dùng `MBeanServer.queryNames` ở môi trường test để kiểm. |
| Dynamic MBean mới không gửi notification | Listener chưa re-register cho MBean mới. | Thiết kế refresh/rebind, test dynamic registration. |
| Notification trùng | Hai adapters/listeners cùng đăng ký; source phát lại; reconnection. | Kiểm adapter ownership và business ID/idempotency. |
| Đổi sang ExecutorChannel nhưng test fail ngay | Handler chạy async, assert quá sớm. | Await/latch, tách channel acceptance khỏi processing completion. |
| Remote JMX timeout | RMI hostname/firewall/ports/cert/auth. | Kiểm JMXConnector configuration, không tắt security. |
| App xử lý chậm khi notification bùng nổ | DirectChannel blocking hoặc queue quá lớn. | Bounded executor/queue, durable inbox, coalescing theo policy. |
| Error channel không nhận exception | Endpoint/channel error path khác kỳ vọng. | Test đúng framework version, cấu hình error flow riêng. |
| MBean bị unregister nhưng context vẫn sống | Producer chưa được rebind. | Lifecycle management và kiểm hiện trạng MBeanServer. |
| Tests chạy song song làm MBean collision | Các contexts cùng dùng platform server/ObjectName. | Tên ObjectName riêng hoặc serialize tests/cleanup exporter. |
| Spring Integration 7.x không import được producer | Class chuyển từ `jmx` sang `jmx.inbound`. | Chọn đúng package theo dependency version. |
| Không thể gắn poller cho notification adapter | Endpoint này event-driven. | Dùng attribute-polling adapter nếu nhu cầu là đọc thuộc tính theo lịch. |

### 22.1. Các kiểm tra tối thiểu tại runtime

Trong code quản trị/test:

~~~java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
        "demo.integration:type=QueueHealth,name=Orders");

boolean present = mbeanServer.isRegistered(name);
System.out.println("MBean registered: " + present);
~~~

Nếu `present=false`, cần sửa việc export/register, không tiếp tục debug `IntegrationFlow` như thể notification đã được gửi đến channel.

### 22.2. Dùng DEBUG logging có chọn lọc

Spring Integration JMX listener có log các MBeans được tìm/match khi bật DEBUG theo phiên bản hỗ trợ. Bật DEBUG trong lab có thể giúp xác minh ObjectName resolution và lifecycle; không bật debug toàn bộ hệ thống quá dài ở production vì có thể chứa metadata nhạy cảm hoặc nhiều logs.

### 22.3. Phân biệt lỗi MBean và lỗi handler

Nếu JMX client gọi `setDepth(-1)`, chính MBean từ chối argument trước khi phát notification. Nếu notification đúng được phát nhưng Spring flow không chấp nhận `userData`, đó là lỗi business validation/downstream. Hai lỗi có vị trí khác nhau và cần metrics/audit khác nhau.

## 23. Các anti-patterns thường gặp

| Anti-pattern | Vì sao không phù hợp | Cách sửa |
| --- | --- | --- |
| Gắn poller để “nghe” JMX Notification | Notification listener là callback/event-driven. | Dùng notification-listening adapter; poller chỉ cho attribute polling hoặc queue nội bộ. |
| Coi ObjectName là Spring channel | Hai không gian định danh khác nhau. | Mô tả rành mạch JMX ObjectName, adapter bean, channel ID. |
| Cast `notification.getUserData()` ngay sang DTO | JMX userData có kiểu Object; dễ sai schema. | Validate type/version và transform rõ. |
| Dựa vào `getMessage()` để route business | Text có thể thay đổi. | Route theo `Notification.getType()` và normalized contract. |
| Gọi HTTP chậm trực tiếp trong JMX callback | Chặn publisher/notification delivery thread. | Bounded async hoặc durable handoff. |
| Giả định JMX notification có broker QoS/replay | JMX listener không phải message broker. | Persist inbox/outbox hoặc forwarding agent khi SLA cần. |
| ObjectName pattern mở hết MBeans | Tăng tải, lộ metadata, khó validate schema. | Giới hạn domain/type và filter. |
| Mọi sequenceNumber đều là event ID global | Sequence chỉ là con số trong scope broadcaster/instance. | Source identity + epoch + business event ID. |
| Để remote JMX auth disabled cho dễ kết nối | Rủi ro quản trị JVM bị truy cập trái phép. | TLS, auth, firewall, least privilege. |
| Hai adapters cùng listen một MBean vì cấu hình trùng | Downstream nhận duplicate events. | Một owner listener hoặc dedup nếu fan-out có chủ đích. |
| Ngừng endpoint rồi cho rằng side effect đã rollback | stop không hoàn tác message đã xử lý. | Idempotent business transitions và shutdown policy. |
| Đánh đồng MBean attribute và event stream | Attribute là snapshot, Notification là event. | Chọn polling hoặc notification dựa trên yêu cầu. |
| Dùng `spring-boot-starter-actuator` nhưng quên `spring-integration-jmx` | Actuator không tự tạo notification adapter. | Thêm đúng dependency Spring Integration JMX. |

## 24. Bài tập thực hành: JMX cảnh báo hàng đợi

**Bối cảnh:** một hệ thống xử lý đơn hàng có ba queues: Orders, Billing và Notifications. Queue implementation phát JMX notifications khi depth tăng vượt ngưỡng. Một Spring Integration service cần nhận sự kiện, ghi audit và gửi alert sang một hệ thống giám sát.

### 24.1. Yêu cầu bài tập

1. Xây `QueueHealthMBean`/`QueueHealth` với writable Depth trong lab và `NotificationBroadcasterSupport`.
2. Phát notification type `demo.queue.depth.changed`, kèm `Integer` userData, sequence và timestamp.
3. Đăng ký ba MBeans theo `demo.integration:type=QueueHealth,name=Orders|Billing|Notifications` với `MBeanExporter` hoặc `MBeanServer.registerMBean(...)` có lifecycle cleanup.
4. Cấu hình Spring Integration notification-listening adapter với ObjectName pattern `demo.integration:type=QueueHealth,name=*`.
5. Dùng `NotificationFilter` chỉ nhận `demo.queue.depth.changed` và bỏ heartbeat.
6. Đưa notifications vào `MessageChannel`, validate type/metadata/userData, chuyển thành DTO với source queue name.
7. Route depth từ 0–49 tới metrics, 50–99 tới warning, từ 100 trở lên tới critical alert.
8. Không parse queue name từ một `Notification.getMessage()` tự do; lấy identity từ ObjectName/source metadata hoặc handback contract rõ.
9. Định nghĩa business event ID/source epoch nếu cần durable dedup và audit qua restart.
10. Dùng một fake audit handler để test `DirectChannel` flow không cần remote JMX.
11. Test MBeanServer thật trong JVM: `setDepth` được nhận, heartbeat bị filter.
12. Test MBean bị unregister rồi register lại: listener được rebind khi nào, có lỗ hổng events không?
13. Test stop/start adapter, đảm bảo không có duplicate registrations.
14. Đổi sang bounded executor/queue, tạo 10.000 notifications và đo dropped/rejected/backlog/latency.
15. Ghi cảnh báo vào durable inbox/outbox trước khi gửi HTTP/JMS/AMQP/Kafka để chịu được downstream outage.
16. Thiết kế quarantine cho `userData` không hợp lệ, không retry vô hạn notification hỏng.
17. Nếu dùng remote JMX, kiểm TLS/auth/ports/firewall, connector close và reconnect.
18. Viết dashboard listener running, received notifications, processing errors, downstream lag.
19. Đối chiếu notification adapter với attribute-polling adapter nếu publisher không thể phát notification.
20. Trình bày giới hạn delivery: JMX local callback không bảo đảm replay sau khi listener offline.

### 24.2. Tiêu chí đạt

Bài tập đạt yêu cầu nếu:

- Có MBean thực sự phát `Notification` và adapter đăng ký thành công;
- JMX notification chuyển vào Spring `MessageChannel` mà **không cần poller**;
- Type và userData được validate; DTO thống nhất;
- Cảnh báo đúng threshold và source, không gửi alert từ heartbeat sai type;
- Không làm blocking work nặng trực tiếp trên đường callback;
- Có thử nghiệm lifecycle, backpressure, remote security nếu áp dụng;
- Có giải thích trung thực rằng JMX listener không tự tạo durability, ACK hoặc replay.

### 24.3. Gợi ý nâng cao

Xây một `Notification` với `userData` là một DTO chuẩn hóa chứa `alertId`, `queueName`, `depth` và `severity` thay vì Integer. Version hóa schema và viết matcher theo `type` để xử lý cả queue saturation, connection pool exhaustion và circuit-breaker transitions. Khi chuyển events sang Kafka, tạo durable outbox có eventId, không chỉ serialize raw `Notification`.

## 25. Câu hỏi tự kiểm tra

1. JMX notification-listening adapter thuộc inbound hay outbound?
2. Nó hoạt động bằng callback hay cần poller?
3. MBeanServer và Spring MessageChannel có vai trò khác nhau như thế nào?
4. `ObjectName` định danh điều gì và có giống Spring bean ID không?
5. `NotificationBroadcasterSupport` hỗ trợ cơ chế nào?
6. Một Standard MBean cần interface đặt tên ra sao trong ví dụ?
7. `getNotificationInfo()` dùng để làm gì?
8. `Notification.getType()` khác `getMessage()` như thế nào?
9. `getUserData()` có kiểu Java gì và vì sao cần validation?
10. `getSequenceNumber()` có phải event ID toàn cục bền qua restart không?
11. `NotificationListener.handleNotification(...)` nhận những đối số nào?
12. Handback object được xác định ở phía publisher hay listener registration?
13. Handback khác `Notification.getUserData()` ở đâu?
14. XML adapter cần ba cấu hình tối thiểu nào?
15. Bean MBeanServer mặc định có tên gì trong XML namespace?
16. Khi nào cần attribute `mbean-server`?
17. Vì sao ObjectName pattern có thể match nhiều MBeans?
18. Pattern có bảo đảm tự attach mọi MBean mới tạo sau start không?
19. `NotificationFilter` và Spring business validation khác nhau như thế nào?
20. JMX listener producer đưa đối tượng gì vào payload của Spring message?
21. Java package của `NotificationListeningMessageProducer` khác gì giữa Spring Integration 6.x và 7.x?
22. Dùng `DirectChannel` có thể làm chậm thread phát notification thế nào?
23. `ExecutorChannel` có biến JMX notifications thành durable messages không?
24. Nếu listener offline khi MBean phát alert, JMX có tự lưu alert để replay không?
25. Stop adapter có tự rollback các handler đã chạy không?
26. Nếu remote JMX connector disconnect, điều gì xảy ra với missed notifications?
27. Vì sao remote JMX cần TLS, auth và firewall?
28. Test `input.send(Message<Notification>)` khác test `queueHealth.setDepth(...)` ra sao?
29. Vì sao dùng Spring `MBeanExporter` mà vẫn phải chọn đúng `ObjectName` cho adapter?
30. Khi chuyển notification sang JMS/AMQP/Kafka, cần xử lý idempotency/durability thế nào?
31. Vì sao lọc notification theo human-readable `message` dễ lỗi?
32. Khi MBeanSource phát nhiều notification types, nên route vào flow bằng thông tin nào?
33. Nếu MBean mới xuất hiện trong ObjectName pattern sau khi adapter đã start, bạn cần kiểm tra gì?
34. Khi nhận một notification có `userData` không hợp lệ, có nên retry vô hạn không?
35. Metric nào cho biết adapter đang chạy, nhận được message và có lỗi downstream?

**Gợi ý:** nhớ ba tầng chính: **JMX publisher/MBeanServer → notification-listening adapter → Spring MessageChannel/IntegrationFlow**. Đây là adapter **event-driven**, không phải polling source, và `Notification` không có durability/transaction giống messaging broker.

## 26. Tổng kết và tài liệu tham khảo

**JMX notification-listening adapter** giúp dùng Spring Integration làm điểm tiếp nhận sự kiện quản trị JVM:

- `NotificationBroadcaster` phát `Notification` thông qua JMX MBean.
- `MBeanServer` định danh nguồn bằng `ObjectName` và quản lý listener registration.
- `NotificationListeningMessageProducer` là Spring Integration inbound endpoint tạo `Message<Notification>`, đăng ký/hủy listener theo lifecycle.
- XML namespace `notification-listening-channel-adapter` và Java `@Bean` đều có thể cấu hình ObjectName, MBeanServer, NotificationFilter, handback và output channel.
- Adapter **event-driven**, không cần poller; `DirectChannel` đồng bộ nên cần cân nhắc thread/backpressure.
- Khi MBeans sinh động hoặc remote JMX disconnect, không giả định notification tự replay hay listener tự attach mọi nguồn về sau.
- Phải validate notification type, userData, source và schema trước khi route/outbound.
- Bảo mật remote JMX bằng TLS, auth, network restrictions; dùng durable inbox/outbox và idempotency nếu business cần delivery guarantee mạnh hơn callback.

Trong module **SPRING_INTEGRATION_ADAPTERS**, JMX notification adapter là một điểm vào cùng hệ thống channels/flows/handlers đã dùng cho file, SFTP, HTTP, JMS, AMQP, Kafka và database. Khi tách rõ **JMX callback → normalized Spring message → business processing → downstream handoff**, ứng dụng dễ quan sát sự kiện JVM, nhưng không nhầm tín hiệu monitoring với một transaction kinh doanh có bảo đảm lưu trữ.

### 26.1. Nguồn chính thức để đối chiếu API/phiên bản

- [Spring Integration – JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): mô tả notification-listening channel adapter, XML namespace, ObjectName pattern, filter/handback và nguyên tắc event-driven.
- [Spring Integration 6.5 – NotificationListeningMessageProducer Javadoc](https://www.springframework.org/spring-integration/docs/6.5.0/api/org/springframework/integration/jmx/NotificationListeningMessageProducer.html): API `org.springframework.integration.jmx.NotificationListeningMessageProducer`.
- [Spring Integration 7.x – NotificationListeningMessageProducer Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/jmx/inbound/NotificationListeningMessageProducer.html): class chuyển vào package `jmx.inbound`.
- [Java Platform – javax.management](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html): nền tảng `MBeanServer`, `ObjectName`, `Notification`, `NotificationBroadcasterSupport`, `NotificationFilter` và `NotificationListener`.

Khi sử dụng với dự án thật, đối chiếu dependency versions và chạy kiểm thử JMX registration/lifecycle tại môi trường triển khai. Các code snippets trong bài là tài liệu học tập STEP 4, **không** thay cho vòng Content QA/refactor và kiểm chứng tích hợp chuyên sâu.



