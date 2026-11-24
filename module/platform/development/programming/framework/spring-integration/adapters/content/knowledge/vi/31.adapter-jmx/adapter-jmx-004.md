# JMX notification-publishing adapter

## 1. Bài toán: biến Spring Message thành JMX Notification

Một dịch vụ Spring Integration nhận được cảnh báo từ HTTP, JMS, Kafka hoặc kết quả kiểm tra dữ liệu trong cơ sở dữ liệu. Ứng dụng muốn **công bố cảnh báo này tới các công cụ quản trị JVM** như JConsole, một JMX client hay một Spring Integration JMX notification listener khác. Hệ thống cần chuyển thông tin đã có trên `MessageChannel` thành `javax.management.Notification` và đăng ký một **MBean publisher** có `ObjectName` rõ ràng.

**JMX notification-publishing adapter** giải quyết bài toán đó. Nó là **outbound channel adapter** của Spring Integration: khi nhận Spring `Message<?>` từ input channel, adapter dùng `NotificationPublishingMessageHandler` để tạo JMX `Notification` rồi phát qua cơ chế JMX NotificationPublisher/MBeanExporter. Nó **không** tự gửi JMS/Kafka record, không gọi một operation trên MBean remote và không đòi hỏi poller.

Bài **“JMX notification-publishing adapter”** thuộc chương **Adapter JMX**, module **SPRING_INTEGRATION_ADAPTERS**. Module học cách kết nối các hệ thống ngoài với Spring Integration qua inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành luồng file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, cùng với hợp đồng message, lỗi và vòng đời kết nối. JMX notification publishing là một **điểm cuối outbound quản trị JVM** trong cùng hệ thống tích hợp đó.

Sau bài học, bạn có thể:

1. Phân biệt `NotificationPublishingMessageHandler` với inbound `NotificationListeningMessageProducer`, attribute-polling và operation-invoking gateway.
2. Hiểu vai trò `MBeanExporter`, `NotificationPublisherAware`, publisher delegate, `MBeanServer` và `ObjectName`.
3. Cấu hình native `int-jmx:notification-publishing-channel-adapter` và `<context:mbean-export/>` bằng XML.
4. Viết Java config sử dụng `@EnableMBeanExport`, `NotificationPublishingMessageHandler`, `MessageChannel` và `IntegrationFlow`.
5. Giải thích chính xác cách adapter mặc định map **String payload → Notification.message** và **non-String payload → Notification.userData**.
6. Cấu hình notification `type` bằng header `JmxHeaders.NOTIFICATION_TYPE` hoặc `default-notification-type`, và nắm thứ tự ưu tiên.
7. Tùy chỉnh mapping với `OutboundMessageMapper<Notification>` để kiểm soát source, sequence, timestamp, text và userData.
8. Viết JUnit test với local `MBeanServer.addNotificationListener(...)`, bắt notification thực tế từ Spring channel.
9. Thiết kế lỗi, backpressure, lifecycle, bảo mật JMX và giới hạn durability/replay một cách trung thực.
10. Đưa JMX Notification vào hệ thống giám sát mà không nhầm với broker event delivery hoặc business commit.

**Ý chính:** Spring Integration outbound JMX publisher chuyển **một Spring message** thành **một JMX notification publication**. Nó là một ranh giới quản trị, không phải queue bền vững hay end-to-end exactly-once.

## 2. Kiến trúc Spring Integration → JMX MBean → listener

~~~mermaid
flowchart LR
    SRC["HTTP / JMS / Kafka / DB<br/>hoặc internal service"]
    ROUTE["IntegrationFlow<br/>validate/route"]
    CH["jmx.notifications.out<br/>MessageChannel"]
    AD["NotificationPublishingMessageHandler<br/>outbound adapter"]
    PUB["NotificationPublisher<br/>MBeanExporter"]
    SERVER[("MBeanServer<br/>ObjectName publisher")]
    L1["JMX NotificationListener"]
    L2["JConsole / monitoring"]
    SRC --> ROUTE --> CH --> AD --> PUB --> SERVER
    SERVER --> L1
    SERVER --> L2
~~~

Luồng thực hiện:

1. Một endpoint/service tạo Spring `Message<?>` có payload và headers.
2. IntegrationFlow có thể kiểm schema, phân loại severity, loại events không cần công bố.
3. Message được gửi vào input `MessageChannel` dành cho JMX outbound adapter.
4. `NotificationPublishingMessageHandler` sử dụng mapper tạo `javax.management.Notification`.
5. Handler phát notification qua Spring `NotificationPublisher`, được cấp thông qua publisher MBean delegate đã đăng ký với `MBeanExporter`.
6. `MBeanServer` phân phối notification tới những `NotificationListener` đã đăng ký trên `ObjectName` tương ứng.
7. JMX consumer có thể đọc `type`, `source`, `sequenceNumber`, `timeStamp`, `message` và `userData` theo contract.

**Không tự giả định** một notification đã đến mọi client chỉ vì handler đã gọi publish xong. Listener có thể chưa đăng ký, remote client có thể mất kết nối hoặc xử lý callback thất bại; JMX không lưu backlog mặc định.

### 2.1. Hướng dữ liệu là outbound

~~~text
Spring MessageChannel
      ↓
NotificationPublishingMessageHandler
      ↓
JMX Notification Publisher MBean
      ↓
JMX NotificationListener(s)
~~~

Đảo hướng:

~~~text
JMX MBean phát Notification
      ↓
NotificationListeningMessageProducer
      ↓
Spring MessageChannel
~~~

Đầu tiên là **publishing adapter outbound**; thứ hai là **listening adapter inbound**. Đừng dùng tên gần giống để cấu hình sai hướng.

### 2.2. Có thể dùng cả hai adapters trong một ứng dụng

Ví dụ dịch vụ A có Spring Integration outbound publisher và dịch vụ B có JMX inbound listener (nếu chúng cùng thấy đúng MBeanServer/remote connector). Chúng tạo một topology **bridge** phục vụ monitoring. Tuy nhiên, muốn truyền business events đáng tin cậy giữa hai JVMs, thường nên dùng HTTP/JMS/AMQP/Kafka hoặc event broker, không dùng JMX Notifications như một transport bền.

## 3. JMX Notification là đối tượng gì?

JMX quản lý đối tượng bằng `MBeanServer` và `ObjectName`. Một notification là đối tượng `javax.management.Notification`, thường mang:

| API | Ý nghĩa | Contract cần lưu ý |
| --- | --- | --- |
| `getType()` | Loại thông báo, ví dụ `demo.queue.depth.warning`. | Nên dot-delimited và ổn định/versioned. |
| `getSource()` | Nguồn phát notification. | Có thể là ObjectName hoặc object khác theo mapper/broadcaster. |
| `getSequenceNumber()` | Số thứ tự do publisher/mapper cấp. | Không mặc định là business event ID global. |
| `getTimeStamp()` | Thời điểm tạo/phát notification. | Không nhất thiết là thời điểm business event xảy ra. |
| `getMessage()` | Mô tả text. | Không phải schema tốt để parse dữ liệu nghiêm ngặt. |
| `getUserData()` | Dữ liệu bổ sung, kiểu Object. | Cần validate type, compatibility và bảo mật. |

Ví dụ JMX notification do ứng dụng tạo thủ công:

~~~java
import javax.management.Notification;
import javax.management.ObjectName;

ObjectName publisherName =
        new ObjectName("demo.integration:type=AlarmPublisher,name=Orders");

Notification warning = new Notification(
        "demo.queue.depth.warning",
        publisherName,
        42L,
        System.currentTimeMillis(),
        "Orders queue depth đã vượt ngưỡng");

warning.setUserData(Integer.valueOf(125));
~~~

**Chú ý:** `Notification` chỉ là cấu trúc JMX event. Tạo object không có nghĩa nó đã được phát; phải gọi JMX `NotificationPublisher.sendNotification(...)` hoặc một broadcaster phù hợp. Trong bài này, Spring Integration handler thực hiện phần publishing.

### 3.1. MBeanExporter khác MBeanServer

`MBeanServer` là registry và cơ chế phân phối. `MBeanExporter` của Spring phụ trách export/register managed beans và hỗ trợ publisher delegate nhận `NotificationPublisher`.

Spring Integration `NotificationPublishingMessageHandler` cần một `MBeanExporter` khả dụng trong context; handler có nội bộ một **`PublisherDelegate`** được đăng ký với ObjectName publisher. Do đó bạn **không cần tự viết một MBean đặc biệt phát notification** trong cấu hình tối thiểu.

### 3.2. ObjectName publisher

Ví dụ:

~~~text
demo.integration:type=AlarmPublisher,name=Orders
~~~

Đây là JMX `ObjectName`, không phải Spring bean ID và cũng không phải MQTT topic. Nó phải là tên cụ thể, hợp lệ và không va chạm với MBean khác trên cùng MBeanServer.

### 3.3. NotificationPublisherAware và PublisherDelegate

Spring Framework hỗ trợ interface `org.springframework.jmx.export.notification.NotificationPublisherAware`. Khi một managed bean được export đúng cách, nó có thể được cấp `NotificationPublisher` để gọi `sendNotification(Notification)`.

Spring Integration đã đóng gói chi tiết này trong `NotificationPublishingMessageHandler.PublisherDelegate`. Cách dùng thông thường là cấu hình handler và `MBeanExporter`, **không** tự gọi `delegate.setNotificationPublisher(...)`.

## 4. So sánh với các endpoint JMX khác

| Spring Integration JMX endpoint | Hướng | Kích hoạt | Ý nghĩa |
| --- | --- | --- | --- |
| `notification-publishing-channel-adapter` | Outbound | Spring message tới channel. | Tạo và phát JMX Notification. |
| `notification-listening-channel-adapter` | Inbound | JMX Notification callback. | Nhận Notification vào Spring Message. |
| `attribute-polling-channel-adapter` | Inbound | Spring poller theo lịch. | Đọc một MBean attribute. |
| `tree-polling-channel-adapter` | Inbound | Spring poller theo lịch. | Lấy snapshot nhiều MBeans. |
| `operation-invoking-channel-adapter` | Outbound | Spring message tới channel. | Gọi operation JMX, không cần reply. |
| `operation-invoking-outbound-gateway` | Outbound request-reply | Spring request. | Gọi JMX operation và trả response. |
| `JmsSendingMessageHandler` / Kafka producer | Outbound transport | Spring message. | Gửi tới messaging broker, có protocol riêng. |

**Thông báo** và **operation** là hai khái niệm khác: notification là publish cho listeners; operation là gọi phương thức quản trị trên MBean. Nếu muốn lấy kết quả `resetQueue()`, không dùng notification publisher để giả một RPC.

## 5. Dependency và Spring Integration version

Ví dụ trong bài dùng **Java 17+, Spring Boot/Spring Integration 6.x**:

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

Sử dụng **Spring Boot BOM** để chọn các phiên bản framework tương thích; không trộn `spring-integration-core 6.x` với `spring-integration-jmx 7.x`.

### 5.1. Thay đổi package giữa 6.x và 7.x

| Kiểu | Spring Integration 6.x | Spring Integration 7.x |
| --- | --- | --- |
| `NotificationPublishingMessageHandler` | `org.springframework.integration.jmx.NotificationPublishingMessageHandler` | `org.springframework.integration.jmx.outbound.NotificationPublishingMessageHandler` |
| `JmxHeaders` | `org.springframework.integration.jmx.JmxHeaders` | Kiểm Javadoc đúng version; không suy rằng mọi JMX classes cùng chuyển vào outbound. |
| `MBeanExporter` | `org.springframework.jmx.export.MBeanExporter` | Class thuộc Spring Framework JMX, không phải Spring Integration outbound. |
| `@EnableMBeanExport` | `org.springframework.context.annotation.EnableMBeanExport` | Spring Framework annotation. |

Nếu gặp lỗi Java import sau upgrade, đối chiếu với Javadocs dependency thực tế. Đừng sửa đồng loạt mọi `org.springframework.integration.jmx` thành `jmx.outbound`: các headers, inbound sources và config classes có package khác nhau.

### 5.2. Vì sao chỉ có spring-boot-starter-actuator là chưa đủ?

Actuator expose health/metrics endpoints, nhưng không tự tạo `NotificationPublishingMessageHandler` và JMX adapter outbound. Muốn dùng native adapter phải có `spring-integration-jmx` và `MBeanExporter` đã cấu hình trong Spring context.

## 6. XML namespace: native notification-publishing channel adapter

Cấu hình tối thiểu được Spring Integration Reference hướng dẫn:

~~~xml
<context:mbean-export/>

<int-jmx:notification-publishing-channel-adapter
        id="queueAlarmPublisher"
        channel="jmx.notifications.out"
        object-name="demo.integration:type=AlarmPublisher,name=Orders"/>
~~~

Ba thành phần cần hiểu:

1. `<context:mbean-export/>` đăng ký Spring `MBeanExporter`.
2. `channel="jmx.notifications.out"` là **input channel** của outbound adapter.
3. `object-name` là tên MBean publisher sẽ được handler đăng ký vào JMX server.

**Không cần poller** trên adapter outbound này: mỗi khi Spring message được gửi vào channel, handler tạo/publish notification.

### 6.1. XML context đầy đủ

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

    <context:mbean-export server="mbeanServer"/>

    <int:channel id="jmx.notifications.out"/>

    <int-jmx:notification-publishing-channel-adapter
            id="queueAlarmPublisher"
            channel="jmx.notifications.out"
            object-name="demo.integration:type=AlarmPublisher,name=Orders"
            default-notification-type="demo.queue.alarm"/>
</beans>
~~~

Đây là cấu hình **native XML**; `MBeanExporter` được liên kết với `mbeanServer` trong context. Nó không tạo publisher bằng một `<bean class="QueuePublisher">` riêng, vì Spring Integration handler tự sử dụng publisher delegate theo cơ chế exporter.

### 6.2. Thiếu MBeanExporter có thể làm endpoint khởi tạo thất bại

`NotificationPublishingMessageHandler` cần tìm một bean kiểu `MBeanExporter` ở Spring bean factory trong lúc initialize; thiếu exporter là lỗi cấu hình. Việc chỉ có `MBeanServer` không tương đương `MBeanExporter`; tạo server không đảm bảo publisher delegate đã được export và cấp `NotificationPublisher`.

### 6.3. default-notification-type là fallback

~~~xml
<int-jmx:notification-publishing-channel-adapter
        id="queueAlarmPublisher"
        channel="jmx.notifications.out"
        object-name="demo.integration:type=AlarmPublisher,name=Orders"
        default-notification-type="demo.queue.alarm"/>
~~~

Nếu Spring message **không** có header `JmxHeaders.NOTIFICATION_TYPE`, default mapper lấy `demo.queue.alarm`. Nếu message cung cấp header type hợp lệ, **header ưu tiên**.

### 6.4. Không khai báo hai adapters dùng cùng ObjectName

Trong cùng `MBeanServer`, hai publishing handlers có ObjectName `demo.integration:type=AlarmPublisher,name=Orders` giống nhau có thể va chạm đăng ký MBean. Nếu muốn hai loại cảnh báo, thường nên gửi chúng vào **một handler** và thay notification type bằng header, không tạo thêm publisher trùng tên.

## 7. Hợp đồng mặc định: String payload và userData

Spring Integration Reference định nghĩa default mapping:

| Spring message payload | JMX Notification result | Ý nghĩa |
| --- | --- | --- |
| `String` | Dùng làm `Notification.message` text. | Phù hợp thông báo ngắn, dễ đọc trong JConsole. |
| `Integer`/record/DTO/`Map`/đối tượng khác | Đặt vào `Notification.userData`. | Truyền thêm dữ liệu có cấu trúc, cần schema/type contract. |
| Header `JmxHeaders.NOTIFICATION_TYPE` | Dùng làm `Notification.type` khi có. | Ưu tiên hơn default type. |
| Không có type header nhưng adapter có `default-notification-type` | Dùng default type. | Phù hợp endpoint chỉ phát một category. |
| Không có type header và không có default type | Default mapper không có type hợp lệ. | Phải bổ sung một trong hai trước khi gửi. |

Ví dụ gửi text:

~~~java
MessageBuilder.withPayload(
        "Orders queue vượt ngưỡng cảnh báo")
    .setHeader(JmxHeaders.NOTIFICATION_TYPE,
            "demo.queue.depth.warning")
    .build();
~~~

Payload này vào outbound channel sẽ tạo một JMX Notification có `message` text tương ứng và `type` như header.

Gửi một DTO:

~~~java
public record QueueAlarm(
        String queueName,
        int depth,
        String severity,
        String eventId) implements java.io.Serializable {
}

QueueAlarm alarm =
        new QueueAlarm("Orders", 125, "CRITICAL", "evt-1001");

MessageBuilder.withPayload(alarm)
        .setHeader(JmxHeaders.NOTIFICATION_TYPE,
                "demo.queue.depth.critical")
        .build();
~~~

Vì payload **không phải String**, default mapper gán DTO vào `userData`. Khi JMX client ở JVM khác nhận object này qua remote connector, cần chú ý classpath/Java serialization/deserialization compatibility; không mặc định remote monitoring tool có class `QueueAlarm`. Với interoperability tốt hơn, có thể dùng primitive/`CompositeData` hoặc custom mapper tạo dữ liệu an toàn.

### 7.1. Type precedence: ví dụ dễ nhớ

~~~text
Adapter default-notification-type = demo.queue.alarm
Message header NOTIFICATION_TYPE = demo.queue.depth.critical

JMX Notification type = demo.queue.depth.critical
~~~

Nếu message bỏ header, kết quả là `demo.queue.alarm`. Không lấy Spring `MessageHeaders.CONTENT_TYPE` hay `MessageHeaders.ID` thay cho JMX notification type.

### 7.2. Type nên là tên dot-delimited có version policy

Một bộ type ví dụ:

~~~text
demo.queue.depth.warning
demo.queue.depth.critical
demo.queue.depth.recovered
demo.connection.pool.exhausted
demo.integration.route.failed
~~~

Tên type là **contract cho listeners**. Không nhét sensitive values hoặc ID có cardinality cao vào type; đặt chúng ở userData/schema được quản lý. Khi thay đổi ý nghĩa hay schema, định nghĩa version/compatibility policy thay vì đổi text theo cảm hứng.

### 7.3. Notification.message không nên làm payload contract chính

Nếu parser downstream phải bóc queue/depth từ câu tiếng Việt `"Orders queue vượt ngưỡng 125"`, nó dễ gãy khi đổi câu chữ. Dùng `userData` có field rõ (`queueName`, `depth`, `eventId`, `schemaVersion`) và `message` để hiển thị, không ngược lại.

### 7.4. Sequence number không phải eventId bền

JMX `Notification.sequenceNumber` phục vụ phân biệt/order tương đối theo publisher runtime; không dùng như business event ID toàn hệ thống. Nó có thể reset khi restart, khác giữa JVMs, và không thay unique key nếu downstream persist/dedup. Mang `eventId` riêng nếu business cần idempotency.


## 8. Java configuration: NotificationPublishingMessageHandler native

Spring Integration cung cấp class `NotificationPublishingMessageHandler`. Ta có thể dùng nó trực tiếp như Spring `MessageHandler` trong `IntegrationFlow`, không cần tự gọi `NotificationPublisher`. Ví dụ sau sử dụng **Spring Integration 6.x**; với 7.x, thay package class handler thành `org.springframework.integration.jmx.outbound.NotificationPublishingMessageHandler`.

### 8.1. Sơ đồ source code

~~~text
src/main/java/demo/jmxpublish/
    JmxPublishApplication.java
    JmxPublishingConfiguration.java
    QueueAlarm.java
    QueueAlarmSender.java

src/test/java/demo/jmxpublish/
    JmxNotificationPublishingTest.java
~~~

Những classes này dùng cùng package `demo.jmxpublish`. Mỗi Java public top-level class/record nên được đặt trong file cùng tên.

### 8.2. Native Java config với MBeanExporter

~~~java
package demo.jmxpublish;

import java.lang.management.ManagementFactory;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jmx.NotificationPublishingMessageHandler;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@EnableMBeanExport(server = "mbeanServer")
class JmxPublishingConfiguration {

    static final String PUBLISHER_NAME =
            "demo.integration:type=AlarmPublisher,name=Orders";

    @Bean(name = "mbeanServer")
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean(name = "jmx.notifications.out")
    MessageChannel jmxOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    NotificationPublishingMessageHandler jmxPublisherHandler()
            throws Exception {

        var handler = new NotificationPublishingMessageHandler(
                new ObjectName(PUBLISHER_NAME));

        handler.setDefaultNotificationType(
                "demo.queue.alarm");

        return handler;
    }

    @Bean
    IntegrationFlow jmxPublishingFlow(
            NotificationPublishingMessageHandler handler) {

        return IntegrationFlow
                .from("jmx.notifications.out")
                .handle(handler)
                .get();
    }
}
~~~

**Giải thích theo đúng API:**

1. `@EnableMBeanExport(server = "mbeanServer")` cung cấp Spring `MBeanExporter` có khả năng export MBeans, tương đương `<context:mbean-export/>`.
2. `@Bean mbeanServer()` chọn platform MBeanServer của JVM; exporter và JMX listener tests phải cùng tham chiếu server này.
3. `new NotificationPublishingMessageHandler(new ObjectName(...))` định danh publisher delegate được handler đăng ký.
4. `setDefaultNotificationType(...)` tạo fallback type khi Spring message thiếu `JmxHeaders.NOTIFICATION_TYPE`.
5. `DirectChannel` là input outbound; khi gửi vào channel, `IntegrationFlow` gọi handler và phát JMX Notification.
6. `.handle(handler)` sử dụng cùng bean handler, không cần đăng ký hai handlers độc lập với cùng ObjectName.
7. MBeanExporter được tạo từ annotation, nên **không** khai báo thêm `MBeanExporter` riêng nếu chưa hiểu registration collisions.
8. Demo chỉ phát JMX notifications local JVM; remote clients cần connector riêng và security.

### 8.3. Không nhầm với một @ManagedResource tùy ý

Handler quản lý một nội bộ `PublisherDelegate`. `MBeanExporter` đăng ký delegate với `ObjectName` của handler và cấp `NotificationPublisher` thông qua JMX publisher support. Nếu bạn tự export một bean `QueueAlarmMBean` dưới **đúng ObjectName đó**, việc đăng ký có thể thất bại vì đã tồn tại MBean. Giữ naming ownership duy nhất.

### 8.4. Application entry point

~~~java
package demo.jmxpublish;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmxPublishApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                JmxPublishApplication.class, args);
    }
}
~~~

Khi cấu hình cùng package được component-scan, app tạo MBeanServer, exporter, message channel, native publishing handler và flow. Không có notification nào phát ra chỉ vì application đã khởi động; phải gửi Spring message vào channel.

## 9. Java API cho service gửi thông báo

### 9.1. QueueAlarm.java

~~~java
package demo.jmxpublish;

import java.io.Serializable;

public record QueueAlarm(
        String queueName,
        int depth,
        String severity,
        String eventId) implements Serializable {

    public QueueAlarm {
        if (queueName == null || queueName.isBlank()) {
            throw new IllegalArgumentException("Thiếu queueName");
        }
        if (depth < 0 || eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("QueueAlarm không hợp lệ");
        }
    }
}
~~~

Record dùng cho ví dụ có structured userData. Việc implement `Serializable` **không phải** lời bảo đảm remote JMX client có thể deserialize một loại Java class ứng dụng mà nó không có. Production nên cân nhắc `CompositeData`/simple types hoặc schema JSON/string nếu phải tương tác nhiều tool khác nhau.

### 9.2. QueueAlarmSender.java

~~~java
package demo.jmxpublish;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.jmx.JmxHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class QueueAlarmSender {

    private final MessageChannel outbound;

    public QueueAlarmSender(
            @Qualifier("jmx.notifications.out")
            MessageChannel outbound) {
        this.outbound = outbound;
    }

    public boolean publishText(String text) {
        return outbound.send(
                MessageBuilder.withPayload(text).build());
    }

    public boolean publishAlarm(QueueAlarm alarm) {
        String type = switch (alarm.severity()) {
            case "WARNING" -> "demo.queue.depth.warning";
            case "CRITICAL" -> "demo.queue.depth.critical";
            case "RECOVERED" -> "demo.queue.depth.recovered";
            default -> throw new IllegalArgumentException(
                    "Severity không hợp lệ: " + alarm.severity());
        };

        return outbound.send(MessageBuilder.withPayload(alarm)
                .setHeader(JmxHeaders.NOTIFICATION_TYPE, type)
                .build());
    }
}
~~~

Tạo bean sender trong cùng Java config:

~~~java
@Bean
QueueAlarmSender queueAlarmSender(
        @Qualifier("jmx.notifications.out") MessageChannel channel) {
    return new QueueAlarmSender(channel);
}
~~~

Khi dùng đoạn `@Bean` này, thêm import `org.springframework.beans.factory.annotation.Qualifier` vào file configuration. Trong production, có thể để sender là `@Service` thay vì @Bean; **chọn một** cách khởi tạo để tránh hai instances không cần thiết.

### 9.3. Hai lời gọi cho hai kiểu Notification

~~~java
sender.publishText("Orders queue đạt mức cảnh báo");

sender.publishAlarm(new QueueAlarm(
        "Orders", 125, "CRITICAL", "evt-orders-001"));
~~~

Lời gọi đầu có **String payload**, không có `NOTIFICATION_TYPE` header, nên default type `demo.queue.alarm` và text trong `Notification.message`.

Lời gọi sau có **record payload** và header type `demo.queue.depth.critical`. JMX `Notification.userData` sẽ chứa record, còn `type` lấy từ header.

### 9.4. Boolean send() không phải xác nhận mọi JMX listeners

`MessageChannel.send(...)` cho biết channel có nhận/dispatch message theo contract của channel; với `DirectChannel` và handler đồng bộ, lỗi handler có thể được propagate. Nhưng giá trị `true` không phải JMX acknowledgment từ mọi JConsole clients và cũng không có retention/replay guarantee. Không dùng nó làm “cảnh báo đã được con người xử lý”.

## 10. Java test: đăng ký JMX NotificationListener vào publisher MBean

Đây là phép kiểm thử thiết thực nhất: **không cần broker hoặc remote connector**, nhưng dùng đúng `MBeanServer` và Spring Integration outbound publisher trong cùng JVM.

### 10.1. Test wiring, type fallback và payload String

~~~java
package demo.jmxpublish;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.jmx.JmxHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = JmxPublishingConfiguration.class)
class JmxNotificationPublishingTest {

    @Autowired
    MBeanServer server;

    @Autowired
    @Qualifier("jmx.notifications.out")
    MessageChannel outbound;

    private final BlockingQueue<Notification> notifications =
            new LinkedBlockingQueue<>();

    private ObjectName publisherName;

    private NotificationListener listener;

    @BeforeEach
    void subscribe() throws Exception {
        publisherName = new ObjectName(
                JmxPublishingConfiguration.PUBLISHER_NAME);

        assertTrue(server.isRegistered(publisherName));

        listener = (notification, handback) ->
                notifications.offer(notification);

        server.addNotificationListener(
                publisherName, listener, null, null);
    }

    @AfterEach
    void unsubscribe() throws Exception {
        if (publisherName != null && listener != null
                && server.isRegistered(publisherName)) {
            server.removeNotificationListener(
                    publisherName, listener);
        }
        notifications.clear();
    }

    private Notification nextNotification() throws Exception {
        Notification notification =
                notifications.poll(2, TimeUnit.SECONDS);
        assertNotNull(notification);
        return notification;
    }

    @Test
    void stringPayloadUsesDefaultTypeAndMessageText()
            throws Exception {
        assertTrue(outbound.send(
                MessageBuilder.withPayload(
                        "Orders queue vượt ngưỡng")
                        .build()));

        Notification event = nextNotification();

        assertEquals("demo.queue.alarm", event.getType());
        assertEquals(
                "Orders queue vượt ngưỡng",
                event.getMessage());
    }

    @Test
    void headerNotificationTypeOverridesFallback()
            throws Exception {
        var message = MessageBuilder
                .withPayload("Queue phục hồi")
                .setHeader(JmxHeaders.NOTIFICATION_TYPE,
                        "demo.queue.depth.recovered")
                .build();

        assertTrue(outbound.send(message));

        Notification event = nextNotification();
        assertEquals(
                "demo.queue.depth.recovered",
                event.getType());
        assertEquals("Queue phục hồi", event.getMessage());
    }

    @Test
    void objectPayloadBecomesUserData()
            throws Exception {
        QueueAlarm payload = new QueueAlarm(
                "Orders", 125, "CRITICAL", "evt-001");

        var message = MessageBuilder
                .withPayload(payload)
                .setHeader(JmxHeaders.NOTIFICATION_TYPE,
                        "demo.queue.depth.critical")
                .build();

        assertTrue(outbound.send(message));

        Notification event = nextNotification();
        assertEquals(
                "demo.queue.depth.critical",
                event.getType());
        assertEquals(payload, event.getUserData());
        assertTrue(event.getSequenceNumber() >= 0);
    }
}
~~~

**Test chứng minh:**

- Publisher delegate được đăng ký vào đúng `MBeanServer` dưới `ObjectName`.
- `MBeanServer.addNotificationListener(...)` nhận thực tế JMX notifications do Spring Integration handler phát.
- Payload String được đưa vào text của Notification.
- Header `JmxHeaders.NOTIFICATION_TYPE` được ưu tiên so với default type.
- Payload record không phải String trở thành `userData`.

### 10.2. Các giới hạn của JUnit test

- Test chỉ chứng minh local publication và listener registration khi Spring context chạy; nó **không** chứng minh remote JMX network reliability hay durable replay.
- `BlockingQueue.poll(2, TimeUnit.SECONDS)` là **bounded wait** để chịu các scheduler/notification callback implementations khác nhau, không phải business retry.
- `@AfterEach` phải remove listener để tránh duplicate callbacks và memory leak.
- Nếu chạy nhiều test contexts cùng ObjectName trên platform server, có thể bị `InstanceAlreadyExistsException`. Dùng test ObjectName riêng hoặc serialize tests/cleanup contexts.
- Sequence number là runtime metadata, không assert cứng rằng lần đầu luôn bằng 1 do shared context/test ordering.
- Test code trên viết cho Spring Integration **6.x**; ở 7.x phải đổi import `NotificationPublishingMessageHandler` trong config.

### 10.3. Test thiếu MBeanExporter

Trong một context test khác, tạo `NotificationPublishingMessageHandler` nhưng **không** tạo `MBeanExporter`. Handler cần exporter để đăng ký delegate; đó là cấu hình phải fail khi khởi tạo, không phải lặng lẽ chấp nhận messages rồi bỏ JMX notifications. Test nên assert context startup exception có nguyên nhân tương ứng, thay vì đợi một message mãi không tới.

### 10.4. Test một listener đăng ký sau khi event được phát

Gửi một notification **trước khi** gọi `addNotificationListener`, rồi mới attach listener. Nó không được broker replay lại notification cũ theo mặc định. Điều này minh họa ranh giới durability, khác với một Kafka consumer có replay từ log.

## 11. MBeanExporter và PublisherDelegate lifecycle

### 11.1. Ai đăng ký publisher MBean?

Trong cấu hình native, `NotificationPublishingMessageHandler` sử dụng delegate được đăng ký với Spring `MBeanExporter` khi handler initialize. JMX `ObjectName` đến từ constructor hoặc XML `object-name`.

~~~mermaid
sequenceDiagram
    participant C as Spring Context
    participant E as MBeanExporter
    participant H as NotificationPublishingMessageHandler
    participant S as MBeanServer
    participant L as JMX Listener
    C->>E: Create MBeanExporter
    C->>H: Initialize handler
    H->>E: Register PublisherDelegate + ObjectName
    E->>S: Export managed resource
    L->>S: addNotificationListener(ObjectName)
    C->>H: Spring Message arrives
    H->>E: Publish Notification
    S-->>L: handleNotification(...)
~~~

Sơ đồ mô tả trách nhiệm, không cam kết exact callback/thread scheduling của mọi MBeanServer implementation.

### 11.2. Không trùng ObjectName với MBean khác

Nếu bạn tạo một bean `@ManagedResource(objectName = "demo.integration:type=AlarmPublisher,name=Orders")` **và** handler native cũng dùng ObjectName đó, hai bên có thể đụng registration. Chỉ một owner chịu trách nhiệm export từng ObjectName. Nếu muốn MBean có custom attributes riêng và đồng thời phát notifications, cần thiết kế MBean/broadcaster tùy biến có chủ đích, không thêm một publisher native cùng tên.

### 11.3. Một context có nhiều MBeanExporter

Một ứng dụng có thể có `MBeanExporter` của Spring Core và `IntegrationMBeanExporter` để quản lý Spring Integration components. Đó là hai vai trò liên quan nhưng khác nhau. Handler cần exporter khả dụng, và việc chọn exporter/server khi có nhiều exporters cần được kiểm tra trên framework version và bean graph; tránh vô tình đăng ký publisher ở server A trong khi listener đang nghe server B.

### 11.4. Application shutdown

Khi context đóng, exporter và handlers cần giải phóng MBean registrations. `MBeanServer` platform sống theo JVM và không nên bị destroy toàn bộ chỉ vì một endpoint ngừng. Nếu app restart trên cùng JVM/test context, phải bảo đảm exporter cleanup để không để lại ObjectName cũ.

### 11.5. MBeanPublisher chỉ phát tới listeners đang đăng ký

Không có “subscriber group”, “consumer offset” hoặc “retained notification” như một message broker. Publisher delegate không giữ danh sách offline listeners hay đảm bảo clients nhận lại khi reconnect. Với trường hợp cần compliance audit, phải ghi notification/business event vào durable store **trước hoặc đồng thời với** publication theo thiết kế riêng.

## 12. Tùy chỉnh mapping: OutboundMessageMapper<Notification>

Default mapper rất tiện cho text/record đơn giản. Khi cần điều khiển `source`, `sequenceNumber`, `timeStamp`, `message` và `userData` hoặc muốn chuẩn hóa payload thành một DTO đơn giản hơn, có thể dùng `NotificationPublishingMessageHandler.setNotificationMapper(...)`.

### 12.1. Ví dụ custom mapper

~~~java
package demo.jmxpublish;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.Notification;
import javax.management.ObjectName;

import org.springframework.integration.jmx.JmxHeaders;
import org.springframework.integration.jmx.NotificationPublishingMessageHandler;
import org.springframework.messaging.Message;

class CustomNotificationFactory {

    private final AtomicLong sequence = new AtomicLong();

    NotificationPublishingMessageHandler newHandler()
            throws Exception {

        ObjectName publisherName =
                new ObjectName(
                        JmxPublishingConfiguration.PUBLISHER_NAME);

        var handler =
                new NotificationPublishingMessageHandler(
                        publisherName);

        handler.setNotificationMapper(
                message -> toNotification(
                        publisherName, message));

        return handler;
    }

    Notification toNotification(
            ObjectName publisherName, Message<?> springMessage) {

        Object header = springMessage.getHeaders().get(
                JmxHeaders.NOTIFICATION_TYPE);

        String type = header instanceof String s
                && !s.isBlank()
                    ? s : "demo.queue.alarm";

        Object payload = springMessage.getPayload();

        String text = payload instanceof String s
                ? s : "Structured queue alarm";

        var result = new Notification(
                type,
                publisherName,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                text);

        if (!(payload instanceof String)) {
            result.setUserData(payload);
        }

        return result;
    }
}
~~~

`setNotificationMapper` nhận `OutboundMessageMapper<Notification>`; lambda dùng Spring Message để tạo đúng JMX Notification. Mapper minh họa dùng `AtomicLong` cho sequence. Trong production, dùng logic validation/schema/dedup phù hợp và tránh đưa các Java object tùy ý vào remote `userData`.

### 12.2. Dùng custom mapper thay thế default handler

Đừng đăng ký **cả** handler mặc định ở mục 8 và custom handler ở mục 12.1 dưới cùng ObjectName. Chọn một configuration:

~~~java
@Bean
NotificationPublishingMessageHandler jmxPublisherHandler()
        throws Exception {

    return new CustomNotificationFactory().newHandler();
}
~~~

Đây là **method @Bean thay thế** `jmxPublisherHandler()` của mục 8, không phải bean thứ hai. `@Bean` custom mapper đã tự quyết định fallback type; `setDefaultNotificationType(...)` chỉ có ý nghĩa với default mapper, không mặc định thay đổi logic do custom mapper tự viết.

### 12.3. Type validation và source identity

Custom mapper phải đảm bảo:

- Type là chuỗi dot-delimited trong danh sách events được chấp nhận.
- Source ObjectName có owner và định danh ổn định theo JVM/node.
- Sequence tăng theo publisher instance, không tuyên bố global sequence.
- Timestamp và business occurredAt là hai trường khác nhau nếu event được xử lý chậm.
- UserData không chứa secrets/PII và có schema/serialization contract rõ.
- EventId nghiệp vụ được giữ ổn định khi retries.
- Handler có error policy cho input sai, không bỏ notification silently.

### 12.4. Không gán reply-channel với JMX ACK

Custom mapper trả về `Notification` cho handler publish; nó không tạo một Spring reply message chứa JMX ACK. Nếu cần request-reply thật, hãy dùng gateway phù hợp hoặc một business acknowledgement protocol riêng. Mọi “notification received” ở consumer phải được thiết kế và xác minh tách biệt.

## 13. Notification listener lọc theo type và dùng handback

Để một JMX consumer chỉ nhận `demo.queue.depth.critical`:

~~~java
import javax.management.NotificationFilter;

NotificationFilter onlyCritical =
        notification ->
                "demo.queue.depth.critical"
                        .equals(notification.getType());
~~~

Sau đó đăng ký:

~~~java
server.addNotificationListener(
        publisherName,
        (notification, handback) -> {
            System.out.println(notification.getType());
            System.out.println(notification.getMessage());
        },
        onlyCritical,
        "critical-alert-consumer");
~~~

Object `handback` được **subscriber cung cấp khi đăng ký listener**; nó không phải Spring message header `JmxHeaders.NOTIFICATION_TYPE` và cũng không phải `Notification.userData`.

Trong Spring Integration, inbound `NotificationListeningMessageProducer` cũng có thể lắng nghe publisher MBean. Khi kết nối publisher outbound vào inbound adapter cùng JVM, hãy giữ channel names và routes riêng để tránh message loop.

### 13.1. Feedback loop phải được chặn

~~~text
Spring input → JMX publishing adapter
                     ↓
             JMX listening adapter
                     ↓
               Spring input (sai!)
~~~

Nếu listener re-publish lại cùng message vào input channel không kiểm soát, có thể tạo vòng vô hạn và bùng nổ CPU/logs. Dùng route riêng, source/tenant policy, `eventId`/hop metadata hoặc filter để không tự đưa notification quay lại publisher.

### 13.2. NotificationFilter chạy ở listener, không ở publisher

Publisher có thể tạo notifications nhiều types, và mỗi listener quyết định chấp nhận type nào. Để giảm tải hoặc loại data nhạy cảm ngay từ nguồn, phải validate/filter **Spring message trước khi publish**, không trông đợi mọi listeners tự bảo vệ.


## 14. Spring Message contract và thiết kế type/header

JMX notification publishing là một điểm **outbound side effect**. Message gửi vào channel cần được xem như một hợp đồng, không đơn thuần là object Java bất kỳ.

### 14.1. Contract đầu vào đề xuất

| Thành phần | Dùng để làm gì? | Quy tắc |
| --- | --- | --- |
| `payload` | Text hoặc structured details. | Validate size/format/type trước publishing. |
| `JmxHeaders.NOTIFICATION_TYPE` | Phân loại JMX notification. | Dot-delimited, allowlisted, ưu tiên default. |
| `eventId` trong payload/header nghiệp vụ | Idempotency và tracing. | Ổn định qua retry, không dùng random mới mỗi attempt. |
| `occurredAt` | Business event xảy ra khi nào. | Tách khỏi JMX timestamp của lúc publish. |
| `sourceNode` | JVM/instance/cluster phát thông báo. | Không chỉ dùng ObjectName nếu nhiều JVMs. |
| `severity` | Quy tắc cảnh báo/route. | Enum/allowlist, không parse free-form message text. |
| `schemaVersion` | Quản lý compatibility userData. | Versioned DTO, tránh đổi meaning âm thầm. |
| `correlationId` | Kết nối nhiều spans/flows. | Hữu ích cho logs; không thay eventId. |

Nếu chỉ cần hiển thị một câu văn, `String` payload là đủ. Nếu downstream cần đọc `depth`/`severity`, hãy gửi DTO có schema rõ và bảo đảm remote JMX client có thể deserialize hoặc map data an toàn.

### 14.2. Vì sao dùng header type thay vì hardcode một default cho mọi event?

Cùng một publisher MBean có thể phát:

~~~text
demo.queue.depth.warning
demo.queue.depth.critical
demo.queue.depth.recovered
demo.queue.connection.lost
demo.queue.connection.recovered
~~~

Khi dùng header, handler native có thể xử lý nhiều types mà không cần một publisher MBean cho mỗi type. Giữ default type như fallback cho message legacy hoặc single-purpose adapter.

### 14.3. Không đồng bộ hóa JMX type với HTTP status code

`Notification.getType()` là chuỗi contract JMX. Không ép nó trùng Kafka topic, Spring class name hoặc HTTP status `500`. Có thể có mapping tường minh từ HTTP error category → JMX type, nhưng đó là nghiệp vụ ứng dụng.

### 14.4. Tránh large object graph trong userData

`userData` có thể chứa object bất kỳ theo JMX API, nhưng điều đó không có nghĩa nên gửi entity JPA có lazy proxies, Java exception với stacktrace quá dài, database connection hoặc object giữ references nhạy cảm. Chọn DTO nhỏ/immutable/serializable, giới hạn độ dài và redaction. Remote JMX có serialization boundary; local tests không kiểm tra đủ rủi ro đó.

## 15. Phân biệt “publish accepted” và “notification consumed”

### 15.1. Một lời gọi send thành công xác nhận điều gì?

~~~mermaid
sequenceDiagram
    participant SRC as Spring Service
    participant CH as MessageChannel
    participant HANDLER as JMX Publisher Handler
    participant JMX as MBeanServer
    participant L as JMX Listener
    SRC->>CH: Message<QueueAlarm>
    CH->>HANDLER: handleMessage(...)
    HANDLER->>JMX: sendNotification(...)
    JMX-->>L: handleNotification(...)
    CH-->>SRC: send(...) result
    Note over SRC,L: Không có business ACK hay durable replay mặc định
~~~

Sơ đồ giản lược chuỗi trách nhiệm, **không cam kết callback hoàn tất trước khi `send()` trả về** trong mọi listener/connector configuration. JMX có thể có dispatch semantics local/remote khác nhau, errors từ listener hoặc network ở ranh giới khác.

### 15.2. Chưa có listener vẫn có thể publish

Publisher MBean có thể tồn tại và phát notification khi không có subscriber. Khi listener đăng ký muộn, nó không tự nhận lại messages đã phát trước đó. Điều này khác durable queue/topic có retention, replay và consumer offsets.

### 15.3. Publisher không sở hữu subscription của listeners

JMX listeners tự đăng ký bằng `MBeanServerConnection.addNotificationListener` (hoặc client tool tương ứng). Publisher không mặc định biết ai đang online, ai xử lý thành công và ai đã bỏ lỡ. Không báo “alert delivered to all admins” chỉ dựa vào `MessageChannel.send()`.

### 15.4. Muốn reliability cao hơn phải bổ sung durable layer

Nếu cảnh báo có tác động nghiệp vụ, ví dụ “không được mất alarm khi order fulfillment thất bại”:

~~~text
Business transaction
   → persist alarm event + outbox row (cùng DB transaction)
   → relay/publisher
   → JMX notification (best-effort management)
   → song song gửi Kafka/JMS/HTTP có retry/ACK riêng
~~~

JMX chỉ đóng vai trò quan sát realtime; **source of truth** là outbox/audit store, hoặc broker bền vững đã được thiết kế. Không cố biến JMX publisher thành một Kafka log.

## 16. Error handling: bốn loại lỗi phải tách riêng

### 16.1. Lỗi cấu hình startup

| Lỗi | Triệu chứng | Khắc phục |
| --- | --- | --- |
| Thiếu `MBeanExporter` | Publisher handler khởi tạo thất bại. | Bật `<context:mbean-export/>` hoặc `@EnableMBeanExport`. |
| Invalid ObjectName | Exception khi tạo handler từ ObjectName. | Validate JMX domain/key-properties, dùng `ObjectName` đúng. |
| ObjectName đã tồn tại | MBean registration collision. | Chọn owner/tên publisher duy nhất. |
| Exporter kết nối server khác | Listener trên server A không thấy publisher của server B. | Đồng bộ MBeanServer/exporter/listener. |
| Module thiếu | Class/namespace JMX không load. | Thêm `spring-integration-jmx` theo đúng BOM. |
| Import sai major version | `NotificationPublishingMessageHandler` không được resolve. | 6.x dùng `jmx`; 7.x dùng `jmx.outbound`. |

**Sai cấu hình phải fail sớm.** Không ghi status “JMX publisher hoạt động” chỉ vì Spring application context khác vẫn khởi động một phần.

### 16.2. Lỗi dữ liệu đầu vào

- Thiếu header type và không có default type: default mapper không có notification type.
- Type không theo contract: consumer bỏ qua hoặc route sai.
- Payload object không tương thích remote serialization: client có thể không decode được.
- Text quá lớn hoặc dữ liệu có PII: JMX clients/logs có thể phơi bày.
- DTO null fields hoặc severity không allowlisted: mapping lỗi.

**Giải pháp:** validate trước adapter, tách `INVALID_NOTIFICATION_TYPE`, `INVALID_PAYLOAD_SCHEMA`, `OVERSIZED_USERDATA` và `UNSUPPORTED_REMOTE_TYPE`; không retry liên tục lỗi cố định.

### 16.3. Lỗi ở JMX publisher/registration

Sau startup, việc MBean publisher bị unregister hoặc exporter/connector lifecycle thay đổi có thể khiến publication thất bại. Một `IllegalStateException` từ publisher hoặc exception Spring messaging có thể xảy ra tùy implementation/version. Đừng nuốt lỗi và log “sent” cho mọi branch.

Khi ứng dụng có nhiều Spring contexts hoặc hot-reloads, kiểm xem handler và publisher delegate còn trỏ tới đúng exporter/server. Một JMX ObjectName được đăng ký bằng code khác ở server không đồng nghĩa native handler có thể chiếm nó.

### 16.4. Lỗi bên listener không phải business retry trigger tự động

Một listener bị lỗi processing không mặc định gửi negative acknowledgement làm publisher retry. `NotificationListener.handleNotification(...)` không phải JMS listener method có transaction rollback/requeue. Cần thiết kế retry ở durable downstream nếu có yêu cầu mạnh.

### 16.5. Lỗi Spring channel/handler

Với `DirectChannel`, exception từ handler có thể được propagate về caller trong cùng thread. Với `ExecutorChannel`, lỗi có thể xảy ra sau khi sender nhận kết quả `send(true)`; cần error channel/monitoring cho nhánh asynchronous. Spring `ErrorMessage`/`errorChannel` không bổ sung replay cho JMX notifications đã publish trước đó.

## 17. Backpressure và bùng nổ notification

Một Spring service có thể tạo hàng nghìn warnings/giây. JMX NotificationPublisher và monitoring clients không nhất thiết thiết kế như high-throughput event broker.

~~~mermaid
flowchart LR
    EVENTS["10,000 Spring Messages / s"]
    FILTER{"Filter / coalesce"}
    CH["bounded channel / executor"]
    HANDLER["JMX publishing handler"]
    JMX["JMX MBeanServer"]
    CLIENTS["Monitoring clients"]
    EVENTS --> FILTER --> CH --> HANDLER --> JMX --> CLIENTS
~~~

### 17.1. Lọc cảnh báo trước khi publish

Nếu queue giữ `Depth=120` trong 10 phút, một polling flow chạy mỗi 5 giây có thể tạo 120 **samples**. Nếu mọi sample tạo cùng `CRITICAL` notification, listener nhận alert storm. Một stateful transformer/filter nên chỉ phát khi severity thay đổi hoặc đến cooldown reminder hợp lệ.

### 17.2. Hysteresis để tránh flapping

~~~text
NORMAL  → WARNING   khi depth >= 80
WARNING → NORMAL    khi depth <= 65
WARNING → CRITICAL  khi depth >= 120
CRITICAL → WARNING  khi depth <= 105
~~~

Ngưỡng chỉ mang tính ví dụ. Hysteresis cần biết state trước, không chỉ dùng `depth >= 80` tại từng message. Nếu nhiều instances cùng phát cảnh báo, state memory local không bảo đảm toàn cluster chỉ một notification; cân nhắc coordination/idempotency ở business layer.

### 17.3. DirectChannel vs ExecutorChannel

| Channel | Đặc điểm | Rủi ro |
| --- | --- | --- |
| `DirectChannel` | Dispatch handler đồng bộ với sender. | Publisher/JMX callback nặng có thể chặn nguồn. |
| `ExecutorChannel` | Handler chạy qua task executor. | Error async, queue saturation, dropped task; sender `true` không chứng minh finish. |
| `QueueChannel` | Buffer giữa producer/consumer có poller downstream. | Queue RAM không bền qua crash nếu không dùng persistent store. |
| Broker adapter | Có protocol/retention/ACK riêng. | Cần vận hành broker và idempotency. |

Chỉ thêm `ExecutorChannel` không khiến JMX notifications bền; chọn bounded executor/queue, rõ policy reject/drop/backpressure và quan sát lag.

### 17.4. Khi nên coalesce

Đối với metric 90%, 91%, 92%, có thể chỉ cần một cảnh báo “đang CRITICAL” và cập nhật gauge. Đối với security/audit events, không tự gộp vô tội vạ nếu mỗi occurrence có ý nghĩa tuân thủ. Hợp đồng quyết định có được drop/merge hay không.

## 18. Remote JMX, TLS và phạm vi công bố

**Bản demo phát local JVM.** Muốn client bên ngoài JVM quan sát, phải có JMX remote connector và cấu hình security phù hợp. Bản thân native publishing adapter không đồng nghĩa nó đã mở một public TCP port.

### 18.1. Luồng local và remote

~~~mermaid
flowchart LR
    FLOW["Spring JMX publisher"]
    SERVER[("Platform MBeanServer")]
    LOCAL["Local JMX listener"]
    CONNECTOR["JMX Remote Connector<br/>RMI/TLS/Auth"]
    REMOTE["Remote JMX client"]
    FLOW --> SERVER --> LOCAL
    SERVER --> CONNECTOR --> REMOTE
~~~

Một `MBeanServer` local vẫn có thể phục vụ remote JMX nếu server/app cấu hình connector. Không mở remote access chỉ để test dễ hơn khi unit test có thể dùng `MBeanServer.addNotificationListener` tại chỗ.

### 18.2. JMX RMI connector cần cấu hình hạ tầng riêng

Remote URL minh họa:

~~~text
service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi
~~~

RMI có thể sử dụng registry port và endpoint port riêng; trong container, cần đúng `java.rmi.server.hostname`, firewall/NAT. Cần TLS/cert, authentication và network allowlist. Không copy cài đặt tắt TLS/auth từ lab vào production.

### 18.3. Serializable userData và classpath

Với remote JMX, Notification chứa `userData` có thể đi qua Java serialization. Nếu `userData` là record `QueueAlarm`, client phải hỗ trợ class/version tương ứng và chỉ deserialize nguồn được tin cậy. Với monitoring clients đa ngôn ngữ, dùng primitive/simple map, OpenType/`CompositeData` hoặc JSON string theo hợp đồng công khai có thể dễ tương thích hơn.

### 18.4. Phân quyền read vs invoke

Remote JMX clients có thể có khả năng đọc MBeans, nhận notifications hoặc gọi operations tùy principal/connector policy. Một application chỉ dùng JMX notifications để monitoring không nên cấp remote access invoke/write tùy tiện. Least privilege ở JMX server vẫn cần dù Spring Integration flow đã validate payload.

### 18.5. Không coi remote connector là durable relay

Nếu client disconnect rồi reconnect, notifications phát trong thời gian offline có thể đã mất. JMX không tự có Kafka offset/replay. Nếu cần biết “có cảnh báo nào trong lúc mất kết nối?”, client phải đối soát một durable audit/metrics API khác hoặc app chủ động re-publish một snapshot state có contract.

## 19. Bridge từ HTTP/JMS/Kafka/DB sang JMX notification

Trong module **SPRING_INTEGRATION_ADAPTERS**, JMX publishing adapter có thể là một **nhánh fan-out phục vụ observability**.

~~~mermaid
flowchart LR
    HTTP["HTTP inbound"]
    JMS["JMS / AMQP inbound"]
    KAFKA["Kafka inbound"]
    DATABASE["DB polling / CDC"]
    ROUTER["Spring Integration flow<br/>validate + route"]
    OUTBOX[("Business state + outbox")]
    PUB["JMX publishing channel"]
    JMX["JMX MBeanServer / JConsole"]
    HTTP --> ROUTER
    JMS --> ROUTER
    KAFKA --> ROUTER
    DATABASE --> ROUTER
    ROUTER --> OUTBOX
    ROUTER --> PUB --> JMX
~~~

### 19.1. Đặt adapter ở đâu trong flow?

**Không** tự phát JMX CRITICAL notification trước khi business transaction commit nếu type mang nghĩa “đơn hàng đã thất bại được ghi nhận”. Phải xác định event meaning: `attempted`, `rejected`, `committed`, `failed`? Khi cần alignment với DB, publish sau commit hoặc từ outbox relay.

### 19.2. Exception của JMX side branch ảnh hưởng business flow ra sao?

Với một `DirectChannel` synchronous branch, JMX handler lỗi có thể ném exception ngược lên upstream. Nếu JMX chỉ là optional monitoring, bạn có thể **cô lập đường phát JMX** khỏi transaction chính bằng async channel/error flow hoặc outbox. Nếu JMX là ranh giới nghiệp vụ quan trọng, cần policy fail-fast có căn cứ; không mặc định “JMX là monitoring nên nuốt mọi lỗi” mà mất visibility.

### 19.3. Chuyển tiếp ngược về JMS/Kafka có thể tạo loop

Một JMX inbound listener có thể chuyển notifications về một Kafka topic, từ đó một consumer lại phát chúng ra JMX. Thiết kế route rõ, event origin, hop metadata và dedup; không dùng `ObjectName` hoặc `JmxHeaders.NOTIFICATION_TYPE` một mình làm unique business event ID.

### 19.4. Phân biệt event publish và state snapshot

JMX notification thường nói “có một thay đổi/cảnh báo”; JMX attribute/tree polling nói “tình trạng hiện thời”. Một ứng dụng có thể cung cấp **cả hai** để consumer vừa quan sát transitions khi online vừa đọc current state khi reconnect. Tuy nhiên, một current-state read không tái tạo toàn bộ history đã bỏ lỡ.

## 20. Observability: điều gì nên đo ở publisher?

| Metric/field gợi ý | Mục đích |
| --- | --- |
| `jmx_publication_attempts_total` | Số Spring messages định công bố. |
| `jmx_publication_success_total{type}` | Số publication methods thành công theo type. |
| `jmx_publication_errors_total{kind}` | Lỗi mapping, registration, JMX publish. |
| `jmx_publisher_mbean_registered` | ObjectName tồn tại trong MBeanServer. |
| `jmx_publication_duration_seconds` | Thời gian xử lý handler/publishing. |
| `jmx_publication_payload_bytes` | Kích thước text/userData sau serialize nếu có đo. |
| `jmx_publication_type_invalid_total` | Bị từ chối do type/schema. |
| `jmx_publication_filtered_total{reason}` | Bị loại trước handler theo policy. |
| `jmx_outbound_channel_backlog` | Độ dài queue khi dùng async/buffer. |
| `jmx_remote_client_connectivity` | Quan sát connector/clients nếu có hook. |
| `jmx_alert_state_transitions_total` | Đếm severity transitions, không đếm mọi samples. |
| `outbox_pending_alarm_count` | Durable alarms chưa được relay, nếu có outbox. |

Tên metrics này là **đề xuất thiết kế**, không phải tập metric mặc định Spring Integration tự tạo đúng nguyên văn. Khi bật Spring Integration management/Micrometer, tra exact metric names/version, không tuyên bố “có sẵn” nếu chưa cấu hình.

### 20.1. Không dùng eventId làm metric label

`eventId`, JMX notification sequence và ObjectName chứa nhiều instance names có thể có cardinality rất cao. Dùng type/severity/service group giới hạn làm labels; chi tiết event IDs cho structured logs/traces có quyền truy cập phù hợp.

### 20.2. Log một publication đúng nghĩa

~~~text
eventId=evt-001
springChannel=jmx.notifications.out
notificationType=demo.queue.depth.critical
publisherObjectName=demo.integration:type=AlarmPublisher,name=Orders
result=JMX_PUBLISH_INVOKED
businessDeliveryAck=NOT_APPLICABLE
~~~

Không ghi `DELIVERED_TO_ALL_LISTENERS=true` nếu không có cơ chế quan sát/ACK riêng. Một listener bị mất mạng có thể không hề nhìn thấy publication.

### 20.3. Alert khi ObjectName publisher không còn

Cần có health check dùng `MBeanServer.isRegistered(publisherObjectName)` và metrics về lỗi handler. Nhưng `isRegistered=true` chưa bảo đảm remote client đã subscribe hoặc client đang xử lý được userData schema.


## 21. Troubleshooting theo từng điểm của pipeline

| Hiện tượng | Nguyên nhân khả dĩ | Bước kiểm tra |
| --- | --- | --- |
| Context không khởi động khi tạo publisher | Thiếu `MBeanExporter`. | Bật `@EnableMBeanExport` hoặc `<context:mbean-export/>`. |
| ObjectName bị trùng | Hai handlers/MBeans cùng registry name. | Chọn owner và ObjectName duy nhất. |
| Không thấy publisher trong JConsole | Chọn sai MBeanServer hoặc exporter chưa register. | `MBeanServer.isRegistered(ObjectName)`. |
| Publisher có nhưng không có notification | Chưa gửi Spring Message, listener chưa attach hoặc route sai. | Gửi test message và addNotificationListener local. |
| Notification type là default thay vì header | Header đặt sai key hoặc bị xóa trong flow. | Dùng `JmxHeaders.NOTIFICATION_TYPE`. |
| Không có notification type hợp lệ | Thiếu header và default. | Thêm fallback hoặc type header. |
| Text không ở userData | Default mapper đặt `String` vào `getMessage()`. | Đọc message text hoặc tùy chỉnh mapper. |
| Record không hiện dưới getMessage | Default mapper đặt non-String vào `getUserData()`. | Kiểm DTO, remote class availability. |
| Remote consumer không decode record | Classpath/Java serialization mismatch. | DTO interoperable hoặc OpenType/JSON. |
| Adapter lỗi sau hot-reload | Exporter/handler delegate/registration stale. | Kiểm MBean ownership và context lifecycle. |
| Gửi trùng notifications | Routes trùng, event gửi lại hoặc nhiều publishers. | EventId, topology và dedup policy. |
| Notifications đến chậm | DirectChannel blocking/JMX client/queue saturated. | Đo latency, bounded async và sampling. |
| Remote JMX không kết nối | TLS/auth/firewall/RMI hostname/port. | Kiểm connector config; không tắt security. |
| CI fail `InstanceAlreadyExistsException` | Nhiều test contexts dùng platform server/ObjectName giống nhau. | Test names riêng, cleanup/serialize test. |
| Không nhận notifications trong thời gian client offline | JMX không có replay. | Durable audit/outbox và đọc current state. |
| Import Java fail khi lên Integration 7.x | Handler chuyển vào `jmx.outbound`. | Đối chiếu Javadoc với dependency thực tế. |

### 21.1. Kiểm JMX registry trước

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName publisherName = new ObjectName(
        "demo.integration:type=AlarmPublisher,name=Orders");

System.out.println("Publisher registered: "
        + server.isRegistered(publisherName));
~~~

Nếu trả `false`, kiểm `MBeanExporter`, ObjectName, native handler initialization và Spring context. Nếu `true` nhưng không thấy thông báo, gắn `NotificationListener` qua API JMX trên **đúng server**, gửi thử message vào `jmx.notifications.out` rồi xác minh type/payload.

### 21.2. Dùng đúng header

`JmxHeaders.NOTIFICATION_TYPE` là khóa phân loại notification. Không nhầm với Spring `contentType`/`MessageHeaders.ID`, và không nhầm `Notification.getType()` với class name của Java DTO.

### 21.3. Không dùng log “sent” cho mọi nhánh

Một exception ở JMX mapper/handler hoặc một `DirectChannel` không có consumer cần được ghi metric riêng. Nếu Spring channel báo accepted, chỉ nên ghi `JMX_PUBLISH_INVOKED`, không kết luận `DELIVERED_TO_EVERY_LISTENER` khi chưa có business acknowledgment.

## 22. Anti-patterns và phương án sửa

| Anti-pattern | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng notification-publishing như inbound listener. | Sai hướng dữ liệu. | Outbound publisher nhận Spring messages; inbound listener nhận JMX Notifications. |
| Thiếu MBeanExporter. | Publisher delegate không được export/cấp NotificationPublisher. | `@EnableMBeanExport` hoặc `<context:mbean-export/>`. |
| Thêm poller cho outbound publisher. | Message đến channel đã kích hoạt handler. | Poller dành cho nguồn cần polling. |
| Gán hai handlers cùng ObjectName. | MBean registration collision. | Một publisher, nhiều notification types qua header. |
| Đặt `contentType` thay `JmxHeaders.NOTIFICATION_TYPE`. | Hai header có hợp đồng khác. | Header JMX đúng hoặc fallback default type. |
| Giả định String nằm trong userData. | Default mapper đặt String ở notification message. | Đọc `getMessage()` hoặc custom mapper. |
| Đẩy nguyên JPA entity/Exception vào userData. | Serialization, memory, secrets và schema risk. | DTO nhỏ, redacted, versioned. |
| Dùng sequenceNumber làm business eventId. | Sequence reset theo publisher instance. | Business ID bền qua retry/restart. |
| Coi `send(true)` là mọi remote listeners đã ACK. | JMX không có business ACK. | Business ACK/durable protocol riêng. |
| Gửi mọi gauge sample dưới dạng CRITICAL event. | Alert storm khi giá trị không đổi. | State transitions, hysteresis, cooldown. |
| Public JMX/RMI không TLS/auth. | Phơi bày quyền quản trị JVM. | TLS, authentication, firewall. |
| ExecutorChannel RAM được xem là durable. | Crash vẫn mất messages chưa persist. | Durable inbox/outbox. |
| Remote client tự nhiên hiểu Java record của publisher. | Có thể thiếu class/serializer. | OpenType, primitive hoặc JSON contract. |
| Dùng JMX làm Kafka giữa data centers. | Không có retention/offset/replay. | Broker bền cho business events, JMX cho monitoring. |
| Nuốt exception và đánh dấu published. | Che mất lỗi. | Error path, metrics, quét backlog/đối soát. |

## 23. Test matrix cho chuẩn chất lượng

Một ứng dụng dùng native publisher nên có ít nhất các nhóm test sau:

| Case | Kỳ vọng |
| --- | --- |
| Spring context có exporter | Publisher ObjectName được đăng ký. |
| Spring context thiếu exporter | Startup fail có nguyên nhân rõ. |
| Hai publishers trùng ObjectName | Xử lý collision, không overwrite âm thầm. |
| String payload và default type | `getMessage()` và `getType()` đúng. |
| String payload với header override | Header ưu tiên default. |
| Non-String payload | `getUserData()` chứa DTO đúng. |
| Input type/header invalid | Reject trước publisher, có metric/error path. |
| Custom OutboundMessageMapper | Type/source/time/sequence/userData theo mapper. |
| Listener filter | Chỉ nhận notification types phù hợp. |
| Subscriber attach muộn | Không tự replay publications đã phát. |
| Listener removed | Không nhận tiếp, tránh leak callbacks. |
| Multiple listeners | Filters riêng và listener ownership rõ. |
| Hot-reload/restart | Không giữ stale MBean registrations. |
| DirectChannel handler failure | Caller thấy exception theo channel contract. |
| ExecutorChannel handler failure | Error monitoring không bị mất. |
| Flood warnings | Coalesce, bounded queue và lag metric. |
| Remote class mismatch | Phát hiện userData serialization incompatibility. |
| Remote TLS/auth | Unauthenticated clients bị từ chối. |
| Remote disconnect/reconnect | Không tuyên bố replay tự động. |
| Bridge loop | Không republish notification vô hạn. |
| Outbox retry | EventId ổn định, downstream idempotency. |

### 23.1. Test trực tiếp JMX nhưng không bỏ Spring flow

Có thể kiểm `NotificationPublisherAware` độc lập với một MBean của Spring, nhưng như vậy chưa chứng minh `NotificationPublishingMessageHandler` được kết nối input channel. Một integration test đầy đủ nên có **Spring MessageChannel → handler → MBeanServer → NotificationListener**, như mục 10.

### 23.2. Remote fault injection ở lab, không trên JVM production

Các tình huống network partition, remote connector restart, certificate expiry phải test trong môi trường cô lập với credentials giả, không ảnh hưởng người vận hành thật. Sau reconnect, đối soát durable alarm log nếu business yêu cầu.

## 24. Bài tập thực hành: quản trị cảnh báo bằng JMX

**Bối cảnh:** một dịch vụ nhận số liệu qua JMS/Kafka, tính severity cho queue Orders, ghi database và phát JMX notifications cho JConsole hoặc một JMX listener service.

### 24.1. Yêu cầu

1. Thêm `spring-integration-jmx` phù hợp Spring Boot BOM.
2. Tạo output `MessageChannel` tên `jmx.notifications.out`.
3. Cấu hình XML native `notification-publishing-channel-adapter` với ObjectName `demo.integration:type=AlarmPublisher,name=Orders`.
4. Bật `<context:mbean-export/>` và giải thích tại sao thiếu exporter là lỗi.
5. Tạo bản Java tương đương với `@EnableMBeanExport` và `NotificationPublishingMessageHandler`; chạy **một trong hai** để không trùng ObjectName.
6. Gửi String payload không có type header; xem type fallback và `getMessage()`.
7. Gửi String payload có `JmxHeaders.NOTIFICATION_TYPE`; xác minh header override default.
8. Gửi record `QueueAlarm` làm payload; xem `Notification.getUserData()`.
9. Định nghĩa types warning/critical/recovered theo dot-delimited convention.
10. Đăng ký local `NotificationListener` qua `MBeanServer.addNotificationListener` và chờ bằng `BlockingQueue.poll(timeout)`.
11. Kiểm `isRegistered(publisherName)` trước khi gửi và cleanup listener sau test.
12. Tạo custom `OutboundMessageMapper<Notification>` và thay thế handler mặc định.
13. Tách business `eventId`/`occurredAt` với JMX sequence/time.
14. Thiết kế hysteresis/cooldown để không publish CRITICAL ở mọi gauge sample.
15. Mô phỏng handler JMX chậm và so sánh DirectChannel với bounded ExecutorChannel.
16. Tạo test thiếu exporter, invalid type, ObjectName collision và record userData không tương thích remote client.
17. Đăng ký listener sau khi đã gửi sự kiện, giải thích vì sao không có replay.
18. Ghi alarm event vào durable audit/outbox khi nghiệp vụ không chấp nhận mất thông tin.
19. Tạo nhánh JMS/AMQP/Kafka bền cho business alert và nhánh JMX cho monitoring.
20. Chặn feedback loop nếu JMX inbound listener lại publish message vào cùng outbound channel.
21. Cấu hình JMX remote lab với TLS/auth/firewall và principal chỉ quyền cần thiết.
22. Tạo metrics attempt/success/error, publisher ObjectName registered và outbox backlog.

### 24.2. Tiêu chí hoàn thành

- Native publisher outbound có ObjectName hợp lệ và MBeanExporter được đăng ký.
- Spring Message gửi vào channel tạo JMX Notification mà không cần poller.
- Mapper phân biệt đúng String và non-String, header type đúng thứ tự ưu tiên.
- JUnit local listener thực sự quan sát notification và cleanup registrations.
- Có error handling, backpressure và remote security.
- Nêu rõ channel send không phải ACK của mọi listener.
- Có durable audit/outbox khi business cần bảo đảm retention.

### 24.3. Bài nâng cao: thống nhất cảnh báo đa nguồn

HTTP inbound nhận incident, JMS consumer nhận queue failure, Kafka listener nhận throughput alarm. Chuẩn hóa chúng về DTO `InfrastructureAlarm(eventId, sourceNode, severity, occurredAt, details)`; route nhánh JMX publishing và một nhánh durable. Dùng `origin`/hop để tránh event loop, cùng một business ID để downstream idempotent.

## 25. Câu hỏi tự kiểm tra

1. Notification-publishing adapter là inbound hay outbound?
2. Nó nhận Spring message hay nhận JMX callback?
3. Java class native publisher là gì?
4. MBeanExporter có vai trò gì?
5. MBeanServer khác MBeanExporter ra sao?
6. PublisherDelegate dùng để làm gì?
7. ObjectName publisher có trùng Spring channel ID không?
8. Thiếu MBeanExporter gây lỗi ở giai đoạn nào?
9. `@EnableMBeanExport` tương đương XML nào?
10. Header nào quyết định JMX notification type?
11. Khi header và default-notification-type đều có, cái nào ưu tiên?
12. Vì sao notification type nên dot-delimited?
13. String payload mặc định được map vào field nào?
14. Non-String payload mặc định được map vào field nào?
15. UserData có luôn phù hợp remote deserialization không?
16. Java record userData có rủi ro gì khi remote client thiếu class?
17. SequenceNumber có thay business event ID được không?
18. Notification timeStamp có luôn là business occurredAt không?
19. Custom mapper có tự dùng default-notification-type của handler không?
20. Vì sao không nên có hai publishers cùng ObjectName trên một server?
21. `MessageChannel.send(true)` có nghĩa client đã ACK chưa?
22. Listener attach sau khi event phát có nhận lại được không?
23. NotificationFilter do publisher hay listener đăng ký?
24. Handback và userData khác nhau ở đâu?
25. Vì sao không dùng JMX cho durable messaging giữa JVMs?
26. Polling flow gửi CRITICAL mỗi 5 giây sẽ gặp vấn đề gì?
27. Hysteresis khác threshold predicate ở đâu?
28. DirectChannel với handler chậm ảnh hưởng upstream thế nào?
29. ExecutorChannel có biến JMX thành broker bền không?
30. Remote JMX cần những lớp bảo mật nào?
31. Test `MBeanServer.addNotificationListener` chứng minh ranh giới nào?
32. Spring Integration 7.x chuyển import handler sang package nào?
33. Vì sao nên validate type/schema trước khi publish?
34. Làm sao chặn bridge loop giữa publisher và listener?
35. Nếu cần giữ alarm trong thời gian JMX client offline, nên dùng gì?

**Gợi ý:** tập trung ba câu hỏi: **ai kích hoạt handler outbound**, **type và payload map như thế nào**, và **các listeners có thực sự được bảo đảm nhận lại message không**.

## 26. Kết luận và tài liệu tham khảo

**JMX notification-publishing adapter** giúp dùng Spring Integration để phát sự kiện quản trị JVM:

- Native XML `int-jmx:notification-publishing-channel-adapter` hoặc Java `NotificationPublishingMessageHandler`.
- Cần `MBeanExporter` để đăng ký PublisherDelegate/cấp `NotificationPublisher`, qua `<context:mbean-export/>` hoặc `@EnableMBeanExport`.
- `object-name` là JMX publisher name, `channel` là Spring input channel.
- Default mapper dùng **String payload → notification message text** và **non-String payload → userData**.
- `JmxHeaders.NOTIFICATION_TYPE` ưu tiên `default-notification-type`; custom mapper tự chịu trách nhiệm type/schema.
- Spring channel send/JMX publish không mang business ACK của mọi listeners hoặc retention/replay.
- Remote JMX cần TLS/auth/ACL/firewall, còn userData phải có serialization contract phù hợp.
- Bảo vệ application bằng filtering, rate limiting, error handling, MBean registration health checks và durable outbox khi SLA cần.

Trong **SPRING_INTEGRATION_ADAPTERS**, pipeline **HTTP/JMS/AMQP/Kafka/DB → MessageChannel → JMX publishing handler → MBeanServer → monitoring clients** giúp quan sát hoạt động JVM. JMX notification phù hợp với monitoring event có người đăng ký trực tiếp; nếu cần replay và business commit guarantees, phải dùng store/broker riêng.

### 26.1. Nguồn kỹ thuật để đối chiếu API

- [Spring Integration Reference – JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): native XML adapter, MBeanExporter, payload type mapping và notification type precedence.
- [NotificationPublishingMessageHandler 6.4 Javadoc](https://www.springframework.org/spring-integration/docs/6.4.1/api/org/springframework/integration/jmx/NotificationPublishingMessageHandler.html): constructor và setters.
- [NotificationPublishingMessageHandler 7.x Javadoc](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/jmx/outbound/NotificationPublishingMessageHandler.html): package `jmx.outbound`.
- [EnableMBeanExport – Spring Framework](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html): export config Java tương đương XML.
- [Spring Framework JMX Publishing Notifications](https://docs.spring.io/spring-framework/docs/5.3.x/reference/html/integration.html): `NotificationPublisherAware` và `NotificationPublisher`.
- [Java JMX API 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html): `MBeanServer`/`NotificationListener`/`ObjectName`.

**Phạm vi STEP 4:** bài Knowledge này có nội dung, Java/XML examples và tests để học. Khi áp dụng thật, đối chiếu dependency versions, build và chạy integration tests. Vòng Content QA/refactor chuyên môn thuộc **STEP 6**, không phải nhiệm vụ kỹ thuật ghi bài STEP 4.




