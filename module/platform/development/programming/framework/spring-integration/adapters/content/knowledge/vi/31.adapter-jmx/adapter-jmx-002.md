# JMX attribute-polling adapter

## 1. Bài toán: đưa trạng thái MBean vào Spring Integration

Một ứng dụng Java expose JMX MBean để giám sát queue `Orders`. MBean có thuộc tính `Depth` (số phần tử đang chờ), nhưng **không phát JMX Notification** khi giá trị đổi. Hệ thống muốn cứ năm giây đọc `Depth`, đưa vào Spring Integration để ghi metric, kiểm tra ngưỡng và phát cảnh báo.

Đây là nhiệm vụ của **JMX attribute-polling adapter**: một Spring Integration **inbound adapter** dùng **poller** chủ động gọi `MBeanServerConnection.getAttribute(ObjectName, attributeName)` theo lịch, bọc giá trị thành Spring `Message<?>` và chuyển vào `MessageChannel`.

Bài **“JMX attribute-polling adapter”** thuộc chương **Adapter JMX** của module **SPRING_INTEGRATION_ADAPTERS**. Module học cách kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành trao đổi file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu, xử lý hợp đồng message, lỗi và vòng đời kết nối. JMX attribute polling là một nguồn **trạng thái quản trị JVM** được chuyển vào cùng pipeline message đó.

Sau bài học, người học có thể:

1. Phân biệt JMX `MBeanServer`, `MBeanServerConnection`, `ObjectName`, attribute, operation và notification.
2. Cấu hình native `int-jmx:attribute-polling-channel-adapter` với `object-name`, `attribute-name`, output channel và poller.
3. Tạo cấu hình tương đương bằng `@InboundChannelAdapter` và `MessageSource<?>` khi cần tự đọc/chuẩn hóa attribute bằng Java.
4. Viết Standard MBean, export bằng `MBeanExporter`, đọc snapshot qua `getAttribute(...)`.
5. Hiểu kiểu trả về Integer/Boolean/String và JMX OpenType/`CompositeData`.
6. Phân biệt sample snapshot với event thay đổi trạng thái, tránh spam alert và mất transition giữa các polls.
7. Thiết kế interval, backpressure, retry, lifecycle, remote JMX security và monitoring.
8. Viết JUnit test dùng MBeanServer nội bộ, xác minh Spring message contract, lỗi getter và kiểm thử có lịch polling.
9. Chọn notification-listening adapter hoặc broker bền vững khi yêu cầu vượt khả năng sampling.

**Cốt lõi:** một JMX attribute poll đọc **snapshot tại thời điểm poll**, không tự biết toàn bộ lịch sử thay đổi giữa hai lần đọc. Spring message được sinh ra **không phải** đối tượng JMX `Notification`.

## 2. Sơ đồ: MBean attribute → poller → MessageChannel

~~~mermaid
flowchart LR
    M["QueueStats MBean<br/>getDepth()"]
    S[("MBeanServer")]
    P["Spring Poller<br/>fixed-delay=5s"]
    A["JMX Attribute Polling Source<br/>getAttribute()"]
    C["jmx.queue.depth.in<br/>MessageChannel"]
    F["IntegrationFlow<br/>normalize/filter/route"]
    MET["Metrics / Audit"]
    EXT["HTTP / JMS / AMQP / Kafka"]
    M --> S
    P --> A
    A -->|"Đọc JMX attribute"| S
    A -->|"Spring Message<value>"| C --> F
    F --> MET
    F --> EXT
~~~

Một chu kỳ đọc:

1. Poller tới hạn, gọi `receive()` của nguồn JMX polling.
2. Nguồn dùng `MBeanServerConnection` và `ObjectName` để gọi `getAttribute()`.
3. Nếu kết quả hợp lệ, giá trị trở thành payload của Spring message và được đưa vào output channel.
4. IntegrationFlow kiểm tra loại dữ liệu, chuyển thành DTO, ghi metric hoặc gửi outbound.
5. Chu kỳ tiếp theo đọc lại snapshot hiện tại, **không** replay snapshot cũ.
6. Stop endpoint thì poller ngừng đọc; MBean vẫn có thể tồn tại trên MBeanServer.

### 2.1. Poller không phải JMX NotificationListener

~~~text
12:00:00 poll → Depth=3
12:00:05 poll → Depth=3
12:00:10 poll → Depth=9
12:00:15 poll → Depth=2
~~~

Nếu `Depth` tăng từ 3 lên 100 rồi về 3 giữa 12:00:00 và 12:00:05, poller **có thể hoàn toàn không nhìn thấy** đỉnh 100. Khi phải ghi nhận mọi chuyển trạng thái, hãy cân nhắc notification-listening adapter hoặc event/outbox ở nguồn.

### 2.2. Ranh giới của các thành phần

| Thành phần | Nhiệm vụ | Không phải |
| --- | --- | --- |
| MBean | Cung cấp state/operation qua JMX. | Spring MessageChannel. |
| MBeanServer | Registry, cung cấp getAttribute/metadata. | MQTT/JMS broker. |
| Poller | Quyết định thời điểm và số lần đọc source. | Lịch thay đổi của business state. |
| Attribute polling source | Đọc một JMX attribute. | Notification subscription. |
| MessageChannel | Giao message cho Spring endpoint. | Persistent event log mặc định. |
| IntegrationFlow | Validate, transform, route, persist/outbound. | JMX protocol implementation. |

### 2.3. Không có ACK nghiệp vụ tự động

Một lần `getAttribute()` trả `Depth=25` chỉ cho biết giá trị ở lúc đọc; nó không có MQTT PUBACK, Kafka offset, transaction commit hay JMX reply xác nhận người vận hành đã tiếp nhận alert. Downstream durability và acknowledgement thuộc kiến trúc ứng dụng.

## 3. Nền tảng JMX cần nắm

### 3.1. Standard MBean và attribute name

Standard MBean thường có interface `QueueStatsMBean` và class `QueueStats`. Quy ước getters/setters:

~~~java
public interface QueueStatsMBean {
    int getDepth();
    boolean isHealthy();
    void setDepth(int value);
    void resetCounters();
}
~~~

| Java method | Thực thể JMX | Tên đọc |
| --- | --- | --- |
| `getDepth()` | Readable attribute | `Depth` |
| `setDepth(int)` | Writable part của attribute | `Depth` |
| `isHealthy()` | Readable boolean attribute | `Healthy` |
| `resetCounters()` | Operation | Không dùng getAttribute. |

**Lỗi phổ biến:** cấu hình `attribute-name="getDepth"` thay vì `attribute-name="Depth"`. Attribute name phân biệt hoa/thường và không bao gồm tiền tố Java `get`.

### 3.2. MBeanServer và MBeanServerConnection

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

MBeanServer local = ManagementFactory.getPlatformMBeanServer();
MBeanServerConnection connection = local;

Integer depth = (Integer) connection.getAttribute(
        new ObjectName("demo.integration:type=QueueStats,name=Orders"),
        "Depth");
~~~

`MBeanServer` implement `MBeanServerConnection`. Client có thể dùng interface chung cho server local và remote JMX connector; remote còn có failure modes `IOException`/TLS/RMI/network.

### 3.3. ObjectName không phải Spring channel

~~~text
demo.integration:type=QueueStats,name=Orders
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=ClassLoading
~~~

`ObjectName` có domain và key properties. Để đọc một attribute cụ thể, thông thường phải chỉ định một **MBean cụ thể**: không biến `ObjectName` pattern match nhiều MBeans thành một getAttribute trả nhiều values. Nếu muốn inventory nhiều MBeans, dùng queryNames/aggregation thiết kế riêng hoặc nguồn JMX tree phù hợp.

### 3.4. MBeanInfo giúp khám phá tên attribute

~~~java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = connection.getMBeanInfo(
        new ObjectName("demo.integration:type=QueueStats,name=Orders"));

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.println(
            attr.getName() + " readable=" + attr.isReadable()
            + " type=" + attr.getType());
}
~~~

Nếu `AttributeNotFoundException` xảy ra, hãy xác minh MBean có expose `Depth` và readable, thay vì retry vô hạn hoặc đoán tên getter.

### 3.5. JMX OpenType và CompositeData

MXBean chuẩn như `java.lang:type=Memory` expose `HeapMemoryUsage`. Khi đọc qua JMX, kết quả có thể là `javax.management.openmbean.CompositeData` chứ không phải một `Long` đơn giản.

~~~java
import java.lang.management.MemoryUsage;
import javax.management.openmbean.CompositeData;

Object result = connection.getAttribute(
        new ObjectName("java.lang:type=Memory"),
        "HeapMemoryUsage");

if (result instanceof CompositeData composite) {
    MemoryUsage usage = MemoryUsage.from(composite);
    long usedBytes = usage.getUsed();
}
~~~

Đừng ép cast trực tiếp `(Long) result` hay gửi raw OpenType sang HTTP/Kafka mà chưa có schema serializer rõ ràng.

## 4. So sánh attribute-polling và notification-listening

| Tiêu chí | Attribute-polling | Notification-listening |
| --- | --- | --- |
| MBean phải có gì? | Readable attribute/getter. | NotificationBroadcaster gửi Notification. |
| Trigger | Poller định kỳ gọi getAttribute. | JMX NotificationListener callback. |
| Cần poller? | **Có.** | Không. |
| Payload | Giá trị thuộc tính (snapshot). | `javax.management.Notification`. |
| Giá trị không đổi | Có thể tạo cùng snapshot mỗi lần đọc. | Không tự phát nếu broadcaster không gửi. |
| Thay đổi nhanh giữa hai lần đọc | Có thể bỏ lỡ transitions. | Có thể nhận nếu listener đang đăng ký và sự kiện được phát. |
| Tải lên MBean | Mỗi poll gọi getter, có thể tốn tài nguyên. | Broadcaster tạo sự kiện, listener xử lý callback. |
| Offline replay | Không tự có. | Không tự có. |
| Use case | Gauge, health value, configuration snapshot. | Cảnh báo/transition/event-driven monitoring. |

Nếu cần **từng event một** với replay/ACK mạnh, có thể phải bổ sung outbox/broker hoặc CDC, thay vì ép poller trở thành event log.

## 5. Native Spring Integration XML adapter

Spring Integration hỗ trợ element `int-jmx:attribute-polling-channel-adapter`. Một cấu hình tối thiểu:

~~~xml
<int-jmx:attribute-polling-channel-adapter
        id="ordersDepthAdapter"
        mbean-server="mbeanServer"
        object-name="demo.integration:type=QueueStats,name=Orders"
        attribute-name="Depth"
        channel="jmxQueueDepth">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-jmx:attribute-polling-channel-adapter>
~~~

- `id`: Spring endpoint ID.
- `mbean-server`: bean `MBeanServer`/connection được dùng để đọc.
- `object-name`: tên MBean chính xác.
- `attribute-name`: tên attribute readable, ví dụ `Depth`.
- `channel`: Spring output MessageChannel.
- `fixed-delay="5000"`: khoảng delay giữa polls theo **mili giây**.
- `max-messages-per-poll="1"`: hạn chế số `receive()` trong một task poll.

**Đây là native JMX polling adapter.** Nó khác việc tự viết Java timer gọi JMX hoặc một notification listener được đăng ký callback.

### 5.1. XML wiring với MBeanServer và service activator

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

    <int:channel id="jmxQueueDepth"/>

    <int-jmx:attribute-polling-channel-adapter
            id="ordersDepthAdapter"
            mbean-server="mbeanServer"
            object-name="demo.integration:type=QueueStats,name=Orders"
            attribute-name="Depth"
            channel="jmxQueueDepth">
        <int:poller fixed-delay="5000"
                    max-messages-per-poll="1"/>
    </int-jmx:attribute-polling-channel-adapter>

    <bean id="depthLogHandler" class="demo.jmxpolling.DepthLogHandler"/>

    <int:service-activator
            input-channel="jmxQueueDepth"
            ref="depthLogHandler"
            method="handle"/>
</beans>
~~~

Để XML chạy, phải có MBean thật được register trên **cùng** MBeanServer với `ObjectName` nói trên. Context ở đây tạo server/channel/adapter/handler, **không tự export** QueueStats MBean.

### 5.2. Handler nhỏ tương ứng

~~~java
package demo.jmxpolling;

public class DepthLogHandler {

    public void handle(Integer depth) {
        System.out.println("Orders queue depth: " + depth);
    }
}
~~~

Log thẳng chỉ dùng cho lab. Khi gửi production, nên normalize snapshot, đo metrics, có error handling và không gọi external service chậm ngay trên poller thread.

### 5.3. Không tạo hai pollers cho cùng dữ liệu nếu không chủ ý

Nếu Spring Boot import XML ở trên và đồng thời bật Java `@InboundChannelAdapter` đọc cùng attribute, hai endpoints có thể tạo hai samples trong một khoảng. Đây không phải MQTT duplicate, mà là **hai lần đọc độc lập**, có thể gây spam cảnh báo hoặc metric sai.

## 6. Poller: interval, concurrency và độ phân giải

### 6.1. fixed-delay, fixed-rate và cron

| Trigger | Ý nghĩa | Điều cần đo |
| --- | --- | --- |
| `fixed-delay="5000"` | Đợi một khoảng giữa hai lần thực thi sau khi lần trước hoàn thành theo scheduler semantics. | MBean getter latency ảnh hưởng sample cadence. |
| `fixed-rate="5000"` | Lịch dự kiến chạy đều theo nhịp. | Khi task chậm hoặc pool nhiều threads, kiểm overlap/delay. |
| Cron | Poll vào các thời điểm lịch cụ thể. | Timezone/DST và những khoảng không có samples. |

Không cấu hình `max-messages-per-poll="1000"` để cố đọc 1.000 values khác nhau từ một attribute: source có thể đọc lại cùng snapshot nhiều lần trong cùng task, làm tăng tải và tạo messages trùng về nội dung.

### 6.2. Poll không đồng nghĩa một business event

~~~text
poll #1: Depth=25
poll #2: Depth=25
poll #3: Depth=25
~~~

Ba messages này là ba **snapshots**, không phải lỗi giao thức. Nếu dùng gauge metric, cập nhật lặp là ổn. Nếu mỗi sample `Depth>=25` làm gửi một email, cần thêm filter theo chuyển trạng thái hoặc cooldown/hysteresis, không phải thay QoS vì JMX không có MQTT QoS.

### 6.3. Có thể bỏ lỡ đỉnh ngắn hạn

~~~text
12:00:01 Depth=10
12:00:02 Depth=200
12:00:03 Depth=0
12:00:05 poll → Depth=0
~~~

Poll interval 5 giây không thấy spike 200. Giảm interval làm tăng độ phân giải nhưng cũng tăng MBean getter calls, CPU/network và downstream processing. Nếu SLA đòi bắt mọi spike, nguồn phải phát event hoặc giữ `maxSinceLastPoll` attribute có reset contract.

### 6.4. Concurrency và ordering

Với một endpoint/poller đơn giản, các polls thường chạy tuần tự. Nếu bạn thêm executor, nhiều app replicas hoặc nhiều endpoints, reads có thể xảy ra song song và snapshots tới downstream không còn theo thứ tự tuyệt đối. Cần đặt `observedAt` và source identity, và không cộng dồn snapshots như transactional events.

## 7. Snapshot message contract và chuyển đổi

Native source đưa value thô do JMX trả về làm Spring message payload. Với QueueStats, đó có thể là `Integer(25)`:

~~~text
Spring Message:
  payload = Integer(25)
  headers = Spring message metadata
~~~

Nếu cần nguồn và mốc lấy mẫu để gửi HTTP/Kafka, tự tạo DTO:

~~~json
{
  "source": "demo.integration:type=QueueStats,name=Orders",
  "attribute": "Depth",
  "value": 25,
  "observedAt": "2026-11-23T03:15:00Z",
  "schemaVersion": 1,
  "kind": "JMX_ATTRIBUTE_SNAPSHOT"
}
~~~

Đây là **schema ứng dụng minh họa**, không phải JSON tự động từ adapter. `observedAt` là lúc application đọc/đóng gói snapshot, **không phải** thời điểm thuộc tính thay đổi.

| Field | Vai trò |
| --- | --- |
| `source` / `objectName` | MBean identity có kiểm soát. |
| `attribute` | Tên readable JMX attribute. |
| `value` | Giá trị đã validate/convert. |
| `observedAt` | Thời gian lấy mẫu. |
| `schemaVersion` | Version hợp đồng outbound. |
| `readStatus` | Thành công/lỗi/gap nếu mô hình lưu lịch sử. |

### 7.1. OpenType và JSON

`CompositeData`/`TabularData` của JMX không bảo đảm tự serialize phù hợp mọi destination. Mapping rõ thành Java records có primitive/String/Instant giúp các adapter HTTP/JMS/Kafka/file/SFTP nhận contract ổn định và dễ kiểm thử.

### 7.2. Không nhầm sample time và update time

Queue có thể đạt 25 từ lâu; một snapshot ở 12:00:05 chỉ chứng minh app quan sát 25 lúc đó. Nếu muốn timestamp thay đổi thật, MBean phải expose metadata bổ sung hoặc phát JMX Notification.


## 8. Lỗi đọc JMX attribute và cách khôi phục

| Lỗi | Nguyên nhân | Chính sách xử lý |
| --- | --- | --- |
| `InstanceNotFoundException` | MBean chưa register, sai ObjectName hoặc đã bị unregister. | Kiểm lifecycle/source; retry theo lịch nếu MBean có thể xuất hiện lại. |
| `AttributeNotFoundException` | Sai tên/case hoặc attribute không readable. | Xem `MBeanInfo`, sửa schema; tránh retry vô hạn. |
| `MBeanException` | Getter MBean ném exception nội bộ. | Kiểm cause; phân loại lỗi cố định/tạm thời. |
| `ReflectionException` | JMX invocation/reflection không phù hợp. | Sửa MBean implementation/metadata. |
| `IOException` khi remote | Connector/RMI/network/TLS lỗi. | Reconnect/backoff, ghi nhận sample gap. |
| `SecurityException` | Không đủ quyền đọc JMX attribute. | Kiểm authentication/authorization; không tắt bảo mật. |
| Giá trị sai kiểu/null | MBean contract thay đổi hoặc giá trị unknown. | Validate type/quality, không cast mù. |
| Getter block lâu | MBean chậm hoặc remote latency cao. | Giới hạn sampling, timeout/liveness monitor. |
| Channel không có consumer | Flow chưa start hoặc wiring lỗi. | Kiểm endpoint status và message dispatch. |
| Handler downstream lỗi | DB/HTTP/Kafka không sẵn sàng. | Error flow, durable handoff nếu event quan trọng. |

### 8.1. Không có message không đồng nghĩa giá trị không đổi

Nếu source trả null hoặc ném exception, một polling endpoint có thể không tạo Spring message. “Không thấy message” vì thế có thể là lỗi MBean/source hoặc filtering, **không** tự chứng minh snapshot giữ nguyên.

### 8.2. Poll kế tiếp không replay sample cũ

Nếu poll 12:00:05 thất bại, poll 12:00:10 đọc **giá trị hiện tại**; adapter không tự khôi phục chính xác trạng thái lúc 12:00:05. Để lưu mọi changes, nguồn phải expose history/notifications hoặc publish tới hệ thống durable.

### 8.3. Error channel là phần của Spring, không phải JMX ACK

Spring Integration có `ErrorMessage`/`errorChannel`, advice và task-scheduler error handling tùy endpoint/version. Việc handler ném exception không bắt MBeanServer “phát lại” attribute snapshot đã đọc. Phải có metrics cho poll failures, retry budget và fail-safe business policy.

## 9. Ví dụ platform JVM: HeapMemoryUsage

JVM thường có MBean `java.lang:type=Memory`, attribute `HeapMemoryUsage`, nên không cần tạo custom MBean để thử.

~~~xml
<int-jmx:attribute-polling-channel-adapter
        id="heapUsagePoller"
        mbean-server="mbeanServer"
        channel="jmxHeapUsage"
        object-name="java.lang:type=Memory"
        attribute-name="HeapMemoryUsage">
    <int:poller fixed-delay="10000"
                max-messages-per-poll="1"/>
</int-jmx:attribute-polling-channel-adapter>
~~~

Một `HeapMemoryUsage` có thể là `CompositeData`; map về contract dễ hiểu:

~~~java
import java.lang.management.MemoryUsage;
import javax.management.openmbean.CompositeData;

public record HeapSample(
        long usedBytes, long committedBytes,
        long maxBytes, long sampledAtEpochMillis) {

    public static HeapSample fromJmxValue(Object value) {
        final MemoryUsage usage;
        if (value instanceof CompositeData data) {
            usage = MemoryUsage.from(data);
        } else if (value instanceof MemoryUsage direct) {
            usage = direct;
        } else {
            throw new IllegalArgumentException(
                    "HeapMemoryUsage sai kiểu");
        }
        return new HeapSample(
                usage.getUsed(),
                usage.getCommitted(),
                usage.getMax(),
                System.currentTimeMillis());
    }
}
~~~

Helper này **không phải class mặc định** của Spring Integration. Trong XML flow cần khai báo transformer/handler gọi `HeapSample.fromJmxValue` trên payload thực nhận.

### 9.1. Đơn vị và giới hạn max

Các giá trị MemoryUsage dùng **bytes**. Muốn MiB, chia 1.048.576. `getMax()` có thể âm khi không xác định, nên không tính tỉ lệ `used/max` nếu max ≤ 0. Thay vì bắn email ở mỗi lần heap >80%, dùng alert state transition/hysteresis.

### 9.2. Actuator/Micrometer hay JMX?

Spring Boot Actuator/Micrometer đã có nhiều JVM metrics sẵn. JMX polling thích hợp khi dự án cần đọc **custom MBean hoặc MBean của thư viện cũ** vào Spring Integration, không bắt buộc dùng cho mọi số liệu JVM có thể lấy qua metrics API.

## 10. Ví dụ Spring Boot: tự viết nguồn đọc MBean bằng Java

Demo phân biệt rõ hai lựa chọn:

- **Native JMX attribute-polling adapter:** XML namespace ở mục 5, dùng nguồn JMX của framework.
- **Java bridge tương đương về semantics:** `@InboundChannelAdapter` + `MessageSource<QueueDepthSnapshot>` gọi `MBeanServerConnection.getAttribute(...)`. Đây là cách tự hiện thực reader khi muốn chuẩn hóa source/value/time ngay tại điểm đọc, **không tuyên bố là chính native JMX source class**.

### 10.1. Maven dependencies

Java 17+, Spring Boot BOM với các versions tương thích:

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

Native XML dùng `spring-integration-jmx`; Java bridge dựa vào JDK `java.management` và Spring Integration polling annotation support. Không trộn tùy tiện các major versions.

### 10.2. Cấu trúc project

~~~text
src/main/java/demo/jmxpolling/
    JmxPollingApplication.java
    QueueStatsMBean.java
    QueueStats.java
    QueueDepthSnapshot.java
    QueueDepthReader.java
    QueueSnapshotSink.java
    JmxPollingConfiguration.java
src/test/java/demo/jmxpolling/
    QueueDepthReaderTest.java
    JmxPollingFlowTest.java
~~~

### 10.3. Standard MBean interface

~~~java
package demo.jmxpolling;

public interface QueueStatsMBean {

    int getDepth();
    void setDepth(int value);
    boolean isHealthy();
    void resetCounters();
}
~~~

`Depth` và `Healthy` là readable JMX attributes, `resetCounters` là operation. Spring polling sẽ chỉ đọc `Depth`.

### 10.4. QueueStats.java

~~~java
package demo.jmxpolling;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueStats implements QueueStatsMBean {

    private final AtomicInteger depth = new AtomicInteger();

    @Override
    public int getDepth() {
        return depth.get();
    }

    @Override
    public void setDepth(int value) {
        if (value < 0) {
            throw new IllegalArgumentException(
                    "Depth không được âm");
        }
        depth.set(value);
    }

    @Override
    public boolean isHealthy() {
        return depth.get() < 100;
    }

    @Override
    public void resetCounters() {
        depth.set(0);
    }
}
~~~

`setDepth` để lab dễ thay giá trị. Không expose setter/operations cho remote clients không tin cậy; JMX management permissions cần được quản lý chặt.

### 10.5. QueueDepthSnapshot.java

~~~java
package demo.jmxpolling;

import java.time.Instant;

record QueueDepthSnapshot(
        String objectName,
        int depth,
        Instant observedAt) {

    QueueDepthSnapshot {
        if (objectName == null || objectName.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu ObjectName");
        }
        if (depth < 0 || observedAt == null) {
            throw new IllegalArgumentException(
                    "Snapshot không hợp lệ");
        }
    }
}
~~~

`QueueDepthSnapshot` là DTO do ứng dụng định nghĩa. `observedAt` đánh dấu thời điểm **đọc** state, không phải thời điểm state thay đổi.

### 10.6. QueueDepthReader.java

~~~java
package demo.jmxpolling;

import java.io.IOException;
import java.time.Instant;

import javax.management.JMException;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

class QueueDepthReader {

    private final MBeanServerConnection connection;
    private final ObjectName objectName;

    QueueDepthReader(
            MBeanServerConnection connection,
            ObjectName objectName) {
        this.connection = connection;
        this.objectName = objectName;
    }

    QueueDepthSnapshot read() {
        try {
            Object value = connection.getAttribute(
                    objectName, "Depth");

            if (!(value instanceof Integer depth)) {
                throw new IllegalArgumentException(
                        "Depth phải là Integer");
            }

            return new QueueDepthSnapshot(
                    objectName.getCanonicalName(),
                    depth,
                    Instant.now());
        } catch (JMException | IOException ex) {
            throw new IllegalStateException(
                    "Đọc JMX Depth thất bại: " + objectName, ex);
        }
    }
}
~~~

Ưu điểm: đóng gói toàn bộ JMX API, dễ test bằng server local/remote, không nhúng scheduler/thread vào reader. `MBeanServerConnection.getAttribute` có thể ném `JMException` và remote `IOException`; code giữ exception cause cho troubleshooting.

### 10.7. QueueSnapshotSink.java

~~~java
package demo.jmxpolling;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class QueueSnapshotSink {

    private final List<QueueDepthSnapshot> items =
            new CopyOnWriteArrayList<>();

    void record(QueueDepthSnapshot value) {
        items.add(value);
    }

    List<QueueDepthSnapshot> snapshot() {
        return List.copyOf(items);
    }

    void clear() {
        items.clear();
    }
}
~~~

Sink RAM chỉ dành cho lab, không có retention/limits hay durability; production nên dùng metrics/time-series DB hoặc inbox/outbox để lưu sự kiện quan trọng. Không lưu vô hạn samples theo chu kỳ trong `CopyOnWriteArrayList` trên server chạy dài hạn.

### 10.8. Cấu hình MBeanExporter, poller và IntegrationFlow

~~~java
package demo.jmxpolling;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
class JmxPollingConfiguration {

    private static final String OBJECT_NAME =
            "demo.integration:type=QueueStats,name=Orders";

    @Bean(name = "mbeanServer")
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    QueueStats queueStats() {
        return new QueueStats();
    }

    @Bean
    MBeanExporter queueStatsExporter(
            MBeanServer mbeanServer,
            QueueStats queueStats) {

        var exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(OBJECT_NAME, queueStats));
        return exporter;
    }

    @Bean
    QueueDepthReader queueDepthReader(
            MBeanServer mbeanServer) throws Exception {
        return new QueueDepthReader(
                mbeanServer, new ObjectName(OBJECT_NAME));
    }

    @Bean(name = "jmx.queue.depth.raw")
    MessageChannel queueDepthInput() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            channel = "jmx.queue.depth.raw",
            poller = @Poller(
                    fixedDelay = "5000",
                    maxMessagesPerPoll = "1"))
    MessageSource<QueueDepthSnapshot> queueDepthSource(
            QueueDepthReader reader) {

        return () -> MessageBuilder
                .withPayload(reader.read())
                .build();
    }

    @Bean
    QueueSnapshotSink queueSnapshotSink() {
        return new QueueSnapshotSink();
    }

    @Bean
    IntegrationFlow queueDepthFlow(QueueSnapshotSink sink) {
        return IntegrationFlow.from("jmx.queue.depth.raw")
                .handle(QueueDepthSnapshot.class,
                        (snapshot, headers) -> {
                            sink.record(snapshot);
                            return null;
                        })
                .get();
    }
}
~~~

Giải thích:

1. `MBeanExporter` đăng ký Standard MBean theo `OBJECT_NAME`.
2. `@InboundChannelAdapter` tạo Spring polling endpoint cho `MessageSource`.
3. `@Poller(fixedDelay="5000")` schedule gọi `receive()` mỗi chu kỳ.
4. Source đọc JMX, chuẩn hóa thành DTO, tạo Spring `Message`.
5. `DirectChannel` chuyển message vào `IntegrationFlow`, sink nhận sample.
6. `return null` ở handler là one-way flow, không có reply.
7. Java source này không phải native JMX source class; nó là một đường cấu hình phù hợp khi phải custom payload/logic.
8. Không tạo thêm XML adapter cùng nguồn/channel trừ khi thực sự muốn double sampling.

### 10.9. Application entry point

~~~java
package demo.jmxpolling;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmxPollingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                JmxPollingApplication.class, args);
    }
}
~~~

Application dùng platform MBeanServer nội JVM và không yêu cầu remote JMX. Cần đảm bảo ObjectName chưa bị MBean khác chiếm, exporter được start trước khi lần poll đầu cần đọc; khi startup order phức tạp, test readiness và xử lý `InstanceNotFoundException` hợp lý.

## 11. Dòng chạy và ý nghĩa snapshot

~~~text
QueueStats bean
   ↓  MBeanExporter đăng ký
MBeanServer: demo.integration:type=QueueStats,name=Orders
   ↓  @InboundChannelAdapter / @Poller
QueueDepthReader.read() → Message<QueueDepthSnapshot>
   ↓
jmx.queue.depth.raw → IntegrationFlow → QueueSnapshotSink
~~~

Gọi từ service trong lab:

~~~java
queueStats.setDepth(25);
~~~

Một poll tiếp theo có thể ghi:

~~~text
QueueDepthSnapshot(
  objectName="demo.integration:name=Orders,type=QueueStats",
  depth=25,
  observedAt=2026-11-23T03:15:00Z
)
~~~

`ObjectName.getCanonicalName()` có thể sắp xếp lại key properties; hai dạng tên vẫn định danh cùng MBean. Đừng assert chuỗi property order khi không xét canonical form.

### 11.1. Ba polls bằng nhau không phải ba lần thay đổi

Nếu polling nhận depth=25 ba lần, đó là ba **observations**. Với gauge monitoring, điều này bình thường; với alert email, phải có stateful filter/cooldown để không gửi ba cảnh báo “vừa tăng lên 25”.

### 11.2. Khi MBean chưa register kịp

`MBeanExporter` và inbound endpoint có lifecycle khác nhau. Lần poll đầu có thể đến trước khi MBean tồn tại trong cấu hình phức tạp; ghi nhận poll failure, xem startup dependencies và tiếp tục kỳ sau theo policy. Không âm thầm trả `0` khi `getAttribute` thất bại vì sẽ tạo báo cáo sai.


## 12. Cảnh báo theo transition: tránh gửi alert mỗi chu kỳ

Giả sử queue được xem là quá tải khi `Depth>=80`. Một Spring filter chỉ có:

~~~java
snapshot.depth() >= 80
~~~

sẽ cho qua **mọi sample** khi queue giữ ở 80–100. Nếu poll mỗi 5 giây, một queue vẫn quá tải trong 30 phút có thể làm gửi hàng trăm email. Để chỉ phát trên transition, cần ghi nhớ alert state.

### 12.1. Severity tracker đơn giản

~~~java
package demo.jmxpolling;

import java.util.concurrent.atomic.AtomicReference;

enum QueueSeverity {
    NORMAL, WARNING, CRITICAL
}

class QueueSeverityTracker {

    private final AtomicReference<QueueSeverity> previous =
            new AtomicReference<>(QueueSeverity.NORMAL);

    QueueSeverity classify(int depth) {
        if (depth >= 120) {
            return QueueSeverity.CRITICAL;
        }
        if (depth >= 80) {
            return QueueSeverity.WARNING;
        }
        return QueueSeverity.NORMAL;
    }

    boolean changedTo(QueueSeverity next) {
        QueueSeverity before = previous.getAndSet(next);
        return before != next;
    }
}
~~~

Đây là ví dụ **lọc transition** trong một JVM, không thực hiện hysteresis thực sự và không bền qua restart. Nếu có nhiều queues, phải duy trì state **theo source ObjectName**, không dùng một `AtomicReference` chung cho toàn hệ thống.

### 12.2. Hysteresis để chống dao động gần ngưỡng

~~~text
NORMAL → WARNING khi Depth >= 80
WARNING → NORMAL khi Depth <= 65
WARNING → CRITICAL khi Depth >= 120
CRITICAL → WARNING khi Depth <= 105
~~~

Hysteresis cần thuật toán dựa trên **previous state** và các ngưỡng khôi phục, không chỉ `if (depth>=80)`. Chọn thresholds dựa trên SLA, năng lực xử lý và chi phí alert sai. Chỉ làm tròn số liệu không thể thay hysteresis.

### 12.3. Cooldown và cửa sổ theo thời gian

Với cảnh báo kéo dài, có thể cần nhắc lại sau 15 phút, nhưng không gửi mỗi 5 giây. Lưu `lastAlertAt` và current severity; nếu người vận hành chưa acknowledge thì policy nhắc lại phải có thời hạn/cấp độ. Đây là nghiệp vụ alert, không phải tính năng mặc định của JMX polling adapter.

### 12.4. Multi-instance cần idempotency bền vững

Nếu hai Spring replicas cùng poll một MBean và cả hai thấy transition, bộ nhớ local không ngăn gửi hai notifications. Dùng database unique key, lease/leader election hoặc outbox event ID được thiết kế theo source+transition+epoch và idempotent downstream khi cần một alert duy nhất ở cấp hệ thống.

### 12.5. Dùng snapshot đúng như gauge

Queue depth là một **giá trị đo tại thời điểm poll**. Đối với metrics, cập nhật gauge là hợp lý; không cộng lần lượt 25+25+25 rồi gọi đó là “75 công việc đã đến”. Muốn đếm công việc đã xử lý, MBean phải expose một counter riêng và cần xử lý reset/restart/delta.

## 13. JUnit: kiểm thử JMX reader với MBeanServer nội bộ

Một lợi thế của JMX là có thể tạo `MBeanServer` trong cùng JVM và test `getAttribute()` mà không mở remote JMX port. Đây là test đơn vị tích hợp **JMX thật**, không dùng mock return cố định.

### 13.1. QueueDepthReaderTest.java

~~~java
package demo.jmxpolling;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.InstanceNotFoundException;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class QueueDepthReaderTest {

    private static final String NAME =
            "demo.integration:type=QueueStats,name=Orders";

    @Test
    void readsRegisteredMBeanAttribute() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("demo.test");
        ObjectName name = new ObjectName(NAME);
        QueueStats bean = new QueueStats();
        bean.setDepth(37);

        try {
            server.registerMBean(bean, name);

            QueueDepthReader reader =
                    new QueueDepthReader(server, name);
            QueueDepthSnapshot snapshot = reader.read();

            assertEquals(37, snapshot.depth());
            assertEquals(name.getCanonicalName(),
                    snapshot.objectName());
            assertTrue(snapshot.observedAt() != null);
            assertEquals(Integer.valueOf(37),
                    server.getAttribute(name, "Depth"));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }

    @Test
    void missingMBeanIsNotSilentlyMappedToZero()
            throws Exception {

        MBeanServer server =
                MBeanServerFactory.createMBeanServer("demo.absent");
        try {
            ObjectName name = new ObjectName(NAME);
            QueueDepthReader reader =
                    new QueueDepthReader(server, name);

            IllegalStateException error = assertThrows(
                    IllegalStateException.class, reader::read);

            assertInstanceOf(
                    InstanceNotFoundException.class,
                    error.getCause());
        } finally {
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
~~~

Điều test chứng minh:

1. Standard MBean được đăng ký và expose attribute `Depth`.
2. `getAttribute` đọc đúng giá trị mà bean đã ghi.
3. Reader chuẩn hóa thành `QueueDepthSnapshot` với ObjectName/time.
4. Nếu MBean không tồn tại, lỗi được lan ra với cause rõ, **không** tạo snapshot giả `Depth=0`.

**Giới hạn:** test chưa chạy Spring scheduled adapter, chưa dùng remote connector và chưa chứng minh queue backlog/durability. Nó chỉ tập trung JMX reader contract.

### 13.2. Test attribute name và khả năng readable

Mở rộng test bằng `server.getMBeanInfo(name)`, kiểm `MBeanAttributeInfo` tồn tại `Depth` và readable, rồi cố `getAttribute(name, "getDepth")` để quan sát `AttributeNotFoundException`. Nhờ đó người học thấy khác biệt giữa JMX attribute name và Java method name.

### 13.3. Test dữ liệu null/kiểu khác

Nếu nguồn MBean trả `String` khi consumer đòi `Integer`, reader cần reject thay vì cast mù. Có thể tạo một test MBean khác expose `Depth` kiểu String để kiểm nhánh `IllegalArgumentException`, hoặc dùng fake `MBeanServerConnection` chỉ cho test parser (không thay test real server).

## 14. JUnit: kiểm thử Spring polling endpoint thực sự

Unit test `QueueDepthReader` chưa chứng minh scheduled Spring endpoint có chạy. Với `@SpringJUnitConfig` có thể nạp `JmxPollingConfiguration` và chờ một snapshot đi qua channel/flow. Vì poller chạy theo lịch, phải đợi **có timeout rõ ràng**, không assert ngay tại thời điểm gọi setter.

### 14.1. JmxPollingFlowTest.java

~~~java
package demo.jmxpolling;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = JmxPollingConfiguration.class)
class JmxPollingFlowTest {

    @Autowired
    QueueStats queueStats;

    @Autowired
    QueueSnapshotSink sink;

    @Test
    void pollsJmxAttributeIntoSpringIntegrationFlow()
            throws InterruptedException {

        queueStats.setDepth(42);

        QueueDepthSnapshot result =
                awaitDepth(42, Duration.ofSeconds(12));

        assertEquals(42, result.depth());
        assertTrue(result.objectName().contains("QueueStats"));
        assertTrue(result.observedAt() != null);
    }

    private QueueDepthSnapshot awaitDepth(
            int expected, Duration timeout)
            throws InterruptedException {

        long deadline = System.nanoTime() + timeout.toNanos();

        while (System.nanoTime() < deadline) {
            for (QueueDepthSnapshot value : sink.snapshot()) {
                if (value.depth() == expected) {
                    return value;
                }
            }
            Thread.sleep(50);
        }

        throw new AssertionError(
                "Không nhận Depth=" + expected
                + " trong giới hạn kiểm thử");
    }
}
~~~

`Thread.sleep(50)` ở helper này chỉ để **đợi kết quả asynchronous với deadline 12s**, không phải thay thế poller trong production. Có thể dùng `CountDownLatch` hoặc Awaitility nếu dự án có dependency tương ứng. Test chịu thời gian chạy thực tế của poller; nếu CI rất chậm, điều chỉnh timeout mà không bỏ kiểm tra business outcome.

**Vấn đề isolation:** Spring context có `MBeanExporter` đăng ký vào platform MBeanServer của JVM. Nếu nhiều test contexts cùng đăng ký ObjectName giống nhau, có thể bị `InstanceAlreadyExistsException`. Khi chạy test song song, dùng ObjectName riêng theo test hoặc chạy serial và đảm bảo exporter cleanup khi context đóng.

### 14.2. Kiểm thử đổi giá trị giữa hai polls

Khi bắt đầu, poller có thể đã lấy Depth cũ. Test nên lọc theo `depth==expected` thay vì assert `sink.snapshot().get(0)`. Thay Depth lần lượt 42→17 và chờ sample 17, chứng minh poller lấy giá trị mới ở chu kỳ kế tiếp.

### 14.3. Test runtime không chứng minh bắt mọi transition

Một test nhận được Depth 42 không có nghĩa các thay đổi 42→100→42 giữa hai polls đã được ghi. Đó là giới hạn **sampling**, không phải bug JUnit hoặc Spring Integration.

### 14.4. Test stop/start lifecycle

Một integration test bổ sung có thể lấy Spring polling endpoint bean theo ID được framework đăng ký, gọi `stop()` rồi kiểm không có polls mới sau khi các tác vụ in-flight hoàn tất; gọi `start()` và kiểm samples tiếp tục đến. Đừng giả định việc stop endpoint sẽ undo samples đã được downstream lưu.

Endpoint ID thực tế khi dùng `@InboundChannelAdapter` có thể phụ thuộc tên bean/source và framework version; lấy ID từ Spring context/management API thay vì hardcode vô căn cứ. Nếu cần stop/start chính xác trong test, thiết kế bean name và config endpoint ID có chủ đích.

## 15. Remote JMX: kết nối MBeanServerConnection ngoài JVM

`MBeanServerConnection` cho phép reader dùng chung API dù server local hay remote. Với remote, tạo `JMXConnector` theo cấu hình an toàn, lấy connection và **đóng connector** khi Spring context shutdown.

~~~java
import java.util.Map;

import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

// Pseudocode minh họa API. Không mở remote JMX không bảo mật.
JMXServiceURL url = new JMXServiceURL(
        "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi");

Map<String, ?> environment = Map.of(
        JMXConnector.CREDENTIALS,
        new String[] { "monitor-user", "demo-only-not-a-secret" });

JMXConnector connector =
        JMXConnectorFactory.connect(url, environment);

MBeanServerConnection remote =
        connector.getMBeanServerConnection();

// QueueDepthReader reader = new QueueDepthReader(remote, name);
// Khi shutdown/recreate connection: connector.close().
~~~

**Không copy hardcoded credentials sang production.** Đoạn trên chỉ mô tả API với placeholder user/password. Trong hệ thống thật, lấy secrets từ vault/config được bảo vệ, dùng TLS/cert verification, least privilege và cấu hình RMI ports/hostname/firewall phù hợp. Nếu không cần remote JMX, platform server nội JVM đơn giản và an toàn hơn.

### 15.1. Remote poll có thể block lâu hơn chu kỳ

Một `getAttribute` qua RMI phụ thuộc network latency và remote JVM load. Nếu timeout lớn hơn 5 giây, một fixed-delay poll 5 giây không còn tạo sample đều đúng 5 giây. Phải đo latency, timeout, missed samples và backpressure, không chỉ đếm số tasks đã schedule.

### 15.2. Reconnect không khôi phục giá trị lịch sử

Sau khi connector mất mạng 30 giây, lần đọc mới chỉ lấy attribute hiện tại. Những peaks/transitions trong 30 giây có thể đã biến mất; JMX attribute polling không tự lưu snapshot backlog.

### 15.3. Remote JMX security checklist

- Không expose JMX/RMI public unauthenticated.
- Yêu cầu TLS và xác minh certificate/host identity; firewall/allowlist management network.
- Dùng credentials có quyền **đọc** MBeans cần thiết, tránh cho phép gọi operations nguy hiểm.
- Không log usernames/passwords, tokens hoặc raw `userData` nhạy cảm.
- Quản lý connector lifecycle, stale references và reconnect backoff.
- Cẩn trọng với Java serialization/deserialization của remote JMX, tránh tải object classes không đáng tin.
- Kiểm tra MBeans nào thực sự được phép đọc và validate payload type trong ứng dụng.

### 15.4. MBean local/remote có cùng ObjectName nhưng khác identity

`demo.integration:type=QueueStats,name=Orders` ở JVM A khác MBean cùng tên ở JVM B. Nếu ghi vào metrics/outbox, identity phải bao gồm **server/cluster/node** hoặc một source ID được cấp tin cậy, không chỉ ObjectName string.


## 16. Lifecycle: MBean registration khác polling endpoint

MBean được `MBeanExporter` register/unregister với JMX server, trong khi Spring `@InboundChannelAdapter` hoặc XML polling endpoint có start/stop lifecycle riêng.

~~~mermaid
sequenceDiagram
    participant CT as Spring Context
    participant EXP as MBeanExporter
    participant MB as MBeanServer
    participant POLL as Polling Endpoint
    participant CH as MessageChannel
    CT->>EXP: Create QueueStats
    EXP->>MB: registerMBean(ObjectName)
    CT->>POLL: Start
    POLL->>MB: getAttribute("Depth")
    MB-->>POLL: Integer value
    POLL->>CH: Message<snapshot>
    CT->>POLL: Stop
    CT->>EXP: Unregister on close
~~~

### 16.1. Endpoint running chưa chắc đọc được giá trị

Nếu MBean chưa export, sai ObjectName hoặc remote JMX đã chết, Spring poller có thể RUNNING nhưng mọi `getAttribute()` đều fail. Readiness cần quan sát lần đọc thành công gần nhất, không chỉ `isRunning()`.

### 16.2. MBean bị unregister giữa lúc chạy

Lần đọc tiếp theo có thể ném `InstanceNotFoundException`. Nếu MBean register lại cùng tên, reader có thể hoạt động trở lại, nhưng phải kiểm kiểu/schema attribute mới. Không thay null/exception bằng snapshot `Depth=0` vì gây hiểu nhầm rằng queue đã hết việc.

### 16.3. Stop poller không xóa MBean

Gọi stop Spring polling endpoint sẽ ngừng lấy mẫu nhưng platform MBeanServer và MBean nguồn vẫn có thể hoạt động. Khi context đóng, MBeanExporter nên unregister các MBeans do nó quản lý; không tự destroy toàn bộ platform server.

### 16.4. Startup ordering và shutdown

Poller có thể được schedule trước khi MBean registration hoàn tất trong hệ thống phức tạp. Test lifecycle/startup, có retry bounded hoặc dependency/readiness rõ ràng. Khi shutdown, theo dõi in-flight remote JMX calls; stop không rollback một snapshot đã ghi DB.

## 17. Backpressure và chi phí polling

~~~mermaid
flowchart LR
    P["Poller tick"]
    READ["JMX getAttribute"]
    CH["DirectChannel"]
    SLOW["HTTP/DB handler chậm"]
    P --> READ --> CH --> SLOW
~~~

Nếu downstream handler chạy đồng bộ và mất 20 giây, poll interval 5 giây sẽ không bảo đảm nhịp lấy mẫu 5 giây. Ngay cả khi scheduler vẫn có tick, blocked executor và queue backlog có thể làm dữ liệu stale.

### 17.1. Chi phí theo nguồn và tần suất

Nếu 200 MBeans đều được poll một lần mỗi giây, application thực hiện khoảng **200 JMX reads/s** chưa kể retry, metadata discovery hoặc additional converters. Remote JMX có thêm network/RMI/serialization overhead; cần đo latency p50/p95/p99 và CPU/GC của JVM nguồn.

### 17.2. ExecutorChannel không tạo durability

Có thể dùng bounded `ExecutorChannel` hoặc `QueueChannel` để tách poller khỏi handler chậm. Tuy nhiên:

- Phải giới hạn threads và queue capacity;
- Chọn policy khi đầy (reject, backpressure, drop stale);
- Có error channel cho asynchronous handler failure;
- Drain/shutdown có timeout;
- Không coi RAM buffer là durable message broker.

Đối với gauge “giá trị mới nhất”, bỏ stale snapshot có thể phù hợp hơn xử lý hàng giờ backlog. Đối với audit quan trọng, cần durable inbox/outbox hoặc event stream ở nguồn.

### 17.3. max-messages-per-poll không phải số attributes

`max-messages-per-poll=1000` cho một attribute source có thể đọc **cùng giá trị nhiều lần** trong một poll task, không tạo 1.000 attributes khác nhau. Với nguồn một attribute luôn có giá trị, `1` thường dễ hiểu và tránh tốn MBean calls.

### 17.4. Sampling không sửa được bằng thêm workers

Nhiều threads/fixed-rate dày hơn có thể tăng sample resolution nhưng không thể ghi lại một transition chưa được quan sát. Nếu phải có mọi biến cố, chọn notification/event publisher hoặc nguồn có history.

## 18. Chuyển JMX snapshot sang adapter khác

Một khi snapshot ở Spring `MessageChannel`, flow có thể tiếp tục dùng transformer/router, database, HTTP, JMS, AMQP, Kafka, file hoặc SFTP adapters.

~~~mermaid
flowchart LR
    JMX["JMX Polling"]
    CH["MessageChannel"]
    DTO["Normalize Snapshot"]
    FILT["Filter/State Transition"]
    DB[("DB + Outbox")]
    RELAY["Relay"]
    DEST["HTTP / Kafka / JMS / SFTP"]
    JMX --> CH --> DTO --> FILT --> DB --> RELAY --> DEST
~~~

### 18.1. Database và time-series

Lưu `objectName`, `attributeName`, `value`, `observedAt` cùng namespace/node ID. Nếu mục tiêu chỉ hiển thị latest gauge, upsert một row là đủ; nếu phân tích trends, cần time-series sampling/retention. Đừng cộng mỗi `Depth` snapshot thành counter công việc.

### 18.2. HTTP outbound

HTTP timeout không luôn chứng minh server đích chưa nhận snapshot. Nếu cần retry, dùng idempotency key/contract đích. Nếu chỉ cập nhật current state, có thể dùng PUT/upsert theo source+attribute, chấp nhận xử lý giá trị cuối thay vì event lịch sử.

### 18.3. Kafka/JMS/AMQP

Khi cần durable forwarding, ghi outbox event trong database transaction rồi relay tới message broker. Relay có thể publish thành công rồi crash trước khi mark sent, vì vậy downstream cũng cần idempotency. Không quảng cáo JMX attribute polling là end-to-end exactly-once: source không replay snapshot bị bỏ lỡ.

### 18.4. File/SFTP

Muốn xuất snapshot thành CSV/JSON, chọn tên file tránh collision, temp-write + rename khi khả thi, retention và đối soát khi upload timeout. Khi poll rất dày, đừng tạo vô hạn file nhỏ không có lifecycle. Nếu cần dữ liệu time-series, tạo batch/rolling window rõ.

### 18.5. Không thể reconstruct spike đã bỏ lỡ

Queue depth tăng 100 trong 200ms nhưng poller chỉ chạy 5 giây một lần. Ngay cả Kafka downstream bền vững cũng **không thể tạo lại giá trị không được poll**. Muốn sự kiện đó, MBean phải phát Notification hoặc expose aggregate như maxSinceLastPoll.

## 19. Bảo mật local và remote JMX

### 19.1. Least privilege

Attribute polling cần **đọc** một số attributes. Không cấp quyền invoke JMX operations hoặc write attributes nếu không cần. MBean có thể expose cấu hình JVM nhạy cảm; dùng allowlist ObjectName+attribute và kiểm soát thành phần được phép kết nối.

### 19.2. Remote connector

- Dùng TLS/mTLS hoặc authentication phù hợp và xác minh hostname/certificate.
- Không expose remote JMX/RMI không bảo vệ ra Internet.
- Kiểm RMI hostname, registry port, connection port, firewall/container networking.
- Secrets lấy từ môi trường/vault an toàn, không hardcode/log.
- Giới hạn remote account chỉ đọc attributes cần thiết.
- Quản lý `JMXConnector.close()` và reconnect/backoff khi connection mất.
- Cẩn trọng Java serialization/deserialization và remote classes/userData không tin cậy.

### 19.3. ObjectName không được ghép từ input tùy ý

Nếu tenant/device IDs đến từ HTTP request, validate và quote key property values đúng JMX `ObjectName` rules. Không cho caller tự chọn `java.lang:*` hoặc đọc toàn bộ MBeanServer chỉ bằng thay query string; quyền đọc phải do service quyết định.

### 19.4. Không log mọi attribute thô

Một MBean có thể expose JDBC URLs, usernames hoặc secrets; đưa raw values vào log/HTTP/Kafka có thể làm rò rỉ thông tin. Nên allowlist attributes an toàn, redact khi cần và giới hạn retention.

## 20. Observability cho poller, reader và downstream

| Metric đề xuất | Ý nghĩa |
| --- | --- |
| `jmx_attribute_poll_attempts_total` | Số lượt đọc đã thử. |
| `jmx_attribute_poll_success_total` | Số lượt đọc thành công. |
| `jmx_attribute_poll_errors_total{kind}` | Phân loại MBean absent, IO, schema, permission. |
| `jmx_attribute_poll_duration_seconds` | Thời gian getAttribute/convert. |
| `jmx_attribute_last_success_epoch_seconds` | Phát hiện source stale. |
| `jmx_attribute_snapshot_age_seconds` | Tuổi snapshot mới nhất. |
| `jmx_mbean_registered{source}` | ObjectName có tồn tại/đọc được? |
| `jmx_remote_connection_up` | Sức khỏe remote JMX. |
| `spring_jmx_channel_errors_total` | Lỗi dispatch từ source vào channel. |
| `jmx_snapshot_dropped_total{reason}` | Samples bị drop theo policy. |
| `jmx_alert_transitions_total{severity}` | Số lần severity đổi thật. |
| `outbox_backlog_count` | Backlog durable chưa relay. |

Đây là **metric names gợi ý**, không phải Spring Integration JMX mặc định luôn xuất tất cả tên này. Không dùng từng ObjectName/device/sample timestamp làm high-cardinality metric labels; log/trace có quyền truy cập phù hợp để debug chi tiết.

### 20.1. Trace một poll bình thường

~~~text
12:00:00 POLL_TRIGGERED source=orders
12:00:00 JMX_READ Depth=42
12:00:00 SNAPSHOT_NORMALIZED
12:00:00 CHANNEL_DISPATCHED
12:00:00 GAUGE_UPDATED
~~~

Trace khi remote lỗi:

~~~text
12:00:05 POLL_TRIGGERED
12:00:07 JMX_READ_FAILED kind=IOException
12:00:07 SOURCE_STALE / next poll scheduled
~~~

Không âm thầm ghi Depth=0 khi không đọc được. Trạng thái “unknown/stale” và giá trị thực 0 là hai thông tin khác nhau.

### 20.2. Readiness không chỉ là endpoint RUNNING

Cảnh báo khi quá 2–3 chu kỳ liên tiếp không có sample hợp lệ, hoặc sample age vượt SLA. Một poller RUNNING nhưng `InstanceNotFoundException` liên tục vẫn là nguồn hỏng; kiểm cả kết nối, ObjectName, last-success, downstream backlog.


## 21. Troubleshooting theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Cách xử lý |
| --- | --- | --- |
| Adapter khởi động nhưng không có message | MBean đã đăng ký? Có poller? Channel có consumer? | Kiểm bean name, ObjectName, attribute, endpoint lifecycle và error logs. |
| `InstanceNotFoundException` liên tục | ObjectName sai hoặc source chưa export. | `mbeanServer.isRegistered(...)` và startup ordering. |
| `AttributeNotFoundException` | Tên/case attribute sai. | `MBeanInfo.getAttributes()`, dùng `Depth` thay `getDepth`. |
| Giá trị luôn bằng 0 dù queue có dữ liệu | Reader bị fallback 0 sau exception, hoặc đọc sai MBeanServer. | Không swallow exception; kiểm đúng server/identity. |
| JConsole thấy attribute nhưng app không đọc được | Có thể hai MBeanServers hoặc remote endpoints khác nhau. | Kiểm `MBeanServerConnection` thực dùng. |
| Nhận nhiều messages giống nhau | Đây là snapshots lặp do poller, hoặc hai endpoints cùng poll. | Gauge vs transition filter, kiểm duplicate configurations. |
| Cảnh báo gửi mỗi 5 giây | Predicate chỉ kiểm threshold, không nhớ state. | Stateful detector/hysteresis/cooldown. |
| Không bắt được spike rất nhanh | Thay đổi nằm giữa hai lần poll. | JMX notification, maxSinceLastPoll hoặc event stream. |
| `ClassCastException` với HeapMemoryUsage | Giá trị là `CompositeData`. | Dùng `MemoryUsage.from(...)`/converter. |
| Spring `@InboundChannelAdapter` không phát | Thiếu `@EnableIntegration`, source/channel cấu hình sai hoặc bean chưa scan. | Kiểm Spring context wiring và integration endpoint. |
| Scheduled test thất bại ngẫu nhiên | Assert ngay trước khi poller chạy. | Bounded await, điều chỉnh test timeout và test isolation. |
| CI báo ObjectName đã được đăng ký | Hai test contexts cùng platform MBeanServer/ObjectName. | Unique ObjectName, cleanup exporter, test serial. |
| Remote JMX `IOException` | RMI network, firewall, TLS hoặc server restart. | Reconnect/backoff, đo gap, kiểm connector config. |
| Poller latency cao | Getter blocking hoặc handler chậm trên DirectChannel. | Đo từng chặng; bounded executor, sampling interval hợp lý. |
| QueueChannel đầy | Producer nhanh hơn consumer, không backpressure. | Bounded buffers, drop stale/persist tùy SLA. |
| Error channel không nhận lỗi | Error path của polling endpoint/handler khác giả định. | Test đúng version và cấu hình error flow, không dựa vào exception chung. |
| MBean mới đăng ký nhưng attribute kiểu khác | Source mới không giữ contract cũ. | Schema/type/version validation, quarantine và operator alert. |
| Dashboard báo 0 ngay khi remote mất mạng | App thay giá trị lỗi bằng 0. | Chuyển sang UNKNOWN/STALE, giữ separate last-known value. |

### 21.1. Kiểm JMX attribute với Java API trước khi debug IntegrationFlow

~~~java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
        "demo.integration:type=QueueStats,name=Orders");

boolean registered = mbeanServer.isRegistered(name);
System.out.println("MBean registered: " + registered);

if (registered) {
    Object value = mbeanServer.getAttribute(name, "Depth");
    System.out.println("Depth type: "
            + (value == null ? "null" : value.getClass().getName()));
    System.out.println("Depth value: " + value);
}
~~~

Nếu chưa đọc được attribute từ MBeanServer, lỗi ở JMX/object name/source; chưa cần nghi ngờ Spring transform/router. Nếu JMX đọc được nhưng channel không nhận, chuyển sang kiểm poller schedule, endpoint running, error channel và output channel.

### 21.2. Quan sát handler trong lab

Một `DepthLogHandler` ghi log cho mỗi snapshot có thể giúp xác nhận luồng, nhưng không để mã logging tần suất cao trong production khi có hàng nghìn MBeans. Theo dõi metrics tổng, sample age và threshold transitions thay vì log raw data vô hạn.

### 21.3. Không dùng Thread.sleep trong production để tạo poll loop

Spring Integration đã có `@Poller`/XML poller. Tạo `while(true)` + `Thread.sleep(5000)` trong service riêng dẫn tới lifecycle, shutdown, error handling và concurrency khó kiểm soát. Trong JUnit, một sleep ngắn có thể dùng làm **bounded wait** để quan sát scheduler, khác hoàn toàn với loop scheduling của production.

## 22. Anti-patterns và cách sửa

| Anti-pattern | Tại sao sai | Thay thế |
| --- | --- | --- |
| Dùng notification-listening adapter cho MBean chỉ có getter. | Nguồn không phát Notification. | Attribute polling adapter với poller. |
| Bỏ poller khỏi attribute adapter. | Không có trigger chủ động để đọc. | Cấu hình `<int:poller>` hoặc `@Poller`. |
| Dùng `attribute-name="getDepth"`. | Getter method khác tên JMX attribute. | `attribute-name="Depth"`. |
| Dùng ObjectName pattern như một attribute đơn lẻ. | `getAttribute` cần MBean cụ thể. | ObjectName chính xác; query/aggregate nếu nhiều MBeans. |
| Gộp nhiều snapshots thành “số events đã xảy ra”. | Snapshot không phải event occurrence. | Gauge hoặc counter có semantics chính xác. |
| Poll 5 giây nhưng hứa bắt mọi spike 100ms. | Sampling bỏ lỡ transition giữa polls. | Notification/history/event source. |
| Mỗi poll vượt ngưỡng là một email. | Spam alerts khi state giữ nguyên. | Hysteresis/stateful change detection. |
| Cast raw `HeapMemoryUsage` sang `Long`. | MXBean thường trả `CompositeData`. | Map OpenType với converter/schema. |
| Getter lỗi thì trả `Depth=0`. | Che giấu outage và tạo cảnh báo sai. | UNKNOWN/STALE + metric error. |
| Đặt maxMessagesPerPoll rất lớn cho một attribute. | Đọc lặp cùng value trong một task. | `1` hoặc cấu hình theo source contract. |
| Dùng chung một MutableState cho mọi queues. | Alert transitions lẫn nguồn. | Key state theo source ObjectName/node. |
| Đặt JMX Client ID giống MQTT Client ID. | JMX không có MQTT client subscription semantics. | Tách identity theo protocol, dùng ObjectName/connector. |
| Gọi remote JMX không TLS/auth. | Expose management JVM. | TLS, auth, firewall, least privilege. |
| Coi ExecutorChannel RAM là durable queue. | Message mất sau crash nếu chưa persist. | Durable inbox/outbox khi cần. |
| Chuyển `CompositeData` trực tiếp ra JSON mà không map. | Schema không ổn định, serialization khó. | DTO versioned primitive fields. |
| Gửi Kafka thành công rồi nghĩ DB mark sent atomic. | Hai hệ thống không chung transaction. | Outbox + idempotent downstream. |
| Chạy hai XML/Java endpoints vô tình đọc cùng MBean. | Double sampling và alert duplication. | Chọn một owner, metrics endpoint ID. |
| Đánh đồng observedAt với lúc queue thay đổi. | Snapshot chỉ biết lúc lấy mẫu. | Thêm change timestamp/event contract ở nguồn. |

## 23. Bài tập thực hành: giám sát nhiều queue bằng JMX

**Bối cảnh:** hệ thống xử lý đơn hàng có queues `Orders`, `Billing` và `Notifications`. Mỗi queue expose Standard MBean có `Depth` và `Healthy`; hệ thống cần lấy mẫu độ sâu mỗi 5 giây, hiển thị gauge, cảnh báo khi quá tải và lưu summary sang database.

### 23.1. Yêu cầu triển khai

1. Định nghĩa `QueueStatsMBean` và `QueueStats`, expose `Depth`, `Healthy` và operation kiểm thử.
2. Đăng ký MBeans qua `MBeanExporter` với ObjectNames:
   - `demo.integration:type=QueueStats,name=Orders`
   - `demo.integration:type=QueueStats,name=Billing`
   - `demo.integration:type=QueueStats,name=Notifications`.
3. Viết XML native `int-jmx:attribute-polling-channel-adapter` cho ít nhất một source, poll 5 giây bằng `<int:poller>`.
4. Với các sources còn lại, có thể cấu hình adapters riêng theo ObjectName hoặc xây nguồn Java có danh sách MBeans đã xác định; không dùng một ObjectName pattern vào `getAttribute` như một phép đọc tự trả nhiều giá trị.
5. Đặt `max-messages-per-poll=1` cho mỗi attribute source và giải thích tại sao.
6. Dùng Java `@InboundChannelAdapter`/`MessageSource` cho một case cần DTO `QueueDepthSnapshot`.
7. Ánh xạ payload Integer và headers/source identity sang schema JSON `source,attribute,value,observedAt,schemaVersion`.
8. Cài JUnit test trực tiếp MBeanServer local, assert Depth/Healthy đúng name/type.
9. Cài Spring polling test dùng bounded await, xác minh giá trị mới tới flow sau khi `setDepth`.
10. Test `AttributeNotFoundException`, MBean chưa register và source runtime unregister/re-register.
11. Test `Depth` giữ nguyên 3 chu kỳ: cập nhật gauge nhưng không gửi 3 alerts.
12. Xây trạng thái NORMAL/WARNING/CRITICAL với hysteresis và cooldown, phân biệt từng queue.
13. Tạo một queue tăng lên 200 rồi về 0 giữa hai polls, giải thích vì sao không thể dùng snapshots để khẳng định đã bắt spike.
14. Thêm một MBean `java.lang:type=Memory`, đọc `HeapMemoryUsage` và convert `CompositeData` sang bytes.
15. Tích hợp một downstream JMS/AMQP/Kafka/HTTP gateway qua DTO, có retry/idempotency/outbox policy tương ứng.
16. Cho handler downstream chậm 10 giây, đo poll lag/backpressure và so sánh `DirectChannel` với bounded executor.
17. Dùng remote JMX trong isolated lab, bật TLS/auth, kiểm connector disconnect/reconnect.
18. Tạo dashboard cho poll success/error, last success age, sample latency và alert transitions.
19. Kiểm việc stop/start endpoint không xóa MBean hoặc rollback business writes.
20. So sánh attribute polling với JMX notification listening và quyết định công cụ cho các yêu cầu “đo trạng thái hiện tại” vs “không được bỏ lỡ bất kỳ transition nào”.

### 23.2. Tiêu chí đạt

- Đọc đúng một JMX attribute theo ObjectName cụ thể; phân biệt attribute và Java getter.
- Có Spring Poller và `MessageChannel` chạy, dùng XML native hoặc Java bridge được mô tả đúng bản chất.
- Snapshot DTO có source/time/value và schema hợp lệ; không tự coi poll là sự kiện thay đổi.
- Lỗi đọc không bị biến thành giá trị 0 giả; có retry/alert phù hợp.
- Threshold không tạo alert storm, có nguồn kiểm soát.
- Test local JMX và Spring polling đều có deadline/cleanup.
- Có giải thích giới hạn sampling, durability, remote security và backpressure.

### 23.3. Mở rộng bài tập: health monitoring có nhiều nguồn

Thiết kế `HealthSnapshot` chứa `nodeId`, `objectName`, `attribute`, `value`, `observedAt` và `quality`. Nếu đọc được lần cuối ở 12:00:00 và ba kỳ sau mất remote JMX, lưu `quality=STALE` hoặc `UNKNOWN` thay vì ghi 0. Khi connector phục hồi, cập nhật snapshot mới; không tự tạo “lịch sử trạng thái” cho khoảng thời gian không đo được.

## 24. Câu hỏi tự kiểm tra

1. JMX attribute-polling adapter là inbound hay outbound endpoint?
2. Adapter chủ động gọi API nào để lấy value?
3. Vì sao nó cần poller còn notification-listening adapter không cần?
4. `QueueStats.getDepth()` tạo JMX attribute tên gì?
5. `resetCounters()` là JMX attribute hay operation?
6. MBeanServer và MBeanServerConnection khác nhau như thế nào?
7. `ObjectName` có giống Spring bean name/MessageChannel ID không?
8. Khi cấu hình sai chữ hoa của `attribute-name`, lỗi nào có thể xảy ra?
9. `MBeanInfo` giúp debug thiếu attribute như thế nào?
10. JMX MemoryMXBean `HeapMemoryUsage` thường trả dạng dữ liệu gì?
11. `MemoryUsage.getUsed()` dùng đơn vị bytes hay MiB?
12. Khi `getMax() == -1`, có nên tính `used/max` không?
13. `fixed-delay` khác `fixed-rate` như thế nào?
14. `max-messages-per-poll=1000` có nghĩa đọc 1.000 attributes khác nhau không?
15. Vì sao ba lần poll cùng Depth=25 không phải ba thay đổi queue?
16. Một spike ngắn hơn poll interval có chắc được nhìn thấy không?
17. `observedAt` có phải timestamp thay đổi giá trị thật không?
18. Khi MBean chưa đăng ký, vì sao không được trả Depth=0 mặc định?
19. Poll thất bại 12:00:05, poll thành công 12:00:10 có replay snapshot đã mất không?
20. Trong Java bridge, vai trò của `@InboundChannelAdapter` và `MessageSource<?>` là gì?
21. Java reader tự gọi `getAttribute` có chính là native `AttributePollingMessageSource` không?
22. MBeanExporter và Spring polling endpoint có vòng đời khác nhau thế nào?
23. Vì sao remote JMX cần TLS/auth/firewall?
24. Khi hai remote JVM có cùng ObjectName, cần thêm định danh gì?
25. Một DirectChannel với handler HTTP chậm có thể gây vấn đề nào cho scheduler?
26. ExecutorChannel có làm messages tự bền vững qua restart không?
27. Khi cảnh báo Depth≥80, cần tránh gửi mail mỗi 5 giây thế nào?
28. Hysteresis khác filter threshold đơn giản ở đâu?
29. Muốn gửi snapshot sang Kafka đáng tin cậy hơn, vì sao cần outbox và downstream idempotency?
30. Một bounded JUnit await khác gì với production loop dùng Thread.sleep?
31. Khi Spring polling endpoint RUNNING mà source vẫn hỏng, cần metric nào?
32. Trong trường hợp yêu cầu mọi queue transitions, nên đổi sang công cụ/kiến trúc nào?

**Gợi ý:** JMX attribute polling luôn trả lời “trạng thái lúc đọc”, không tự trả lời “mọi biến cố đã xảy ra”. Chọn polling interval, schema, error policy và downstream guarantee theo đúng SLA.

## 25. Kết luận và nguồn tham khảo

**JMX attribute-polling adapter** là một cầu nối từ JMX quản trị JVM vào Spring Integration:

- **JMX `MBeanServerConnection.getAttribute`** đọc snapshot của attribute có tên và ObjectName cụ thể.
- **Native Spring Integration `int-jmx:attribute-polling-channel-adapter`** tạo inbound endpoint với poller, channel và metadata JMX rõ.
- **Java `@InboundChannelAdapter` + `MessageSource`** là một hướng xây dựng bridge tùy chỉnh, cho phép đóng gói DTO/source/timestamp, nhưng phải phân biệt với native JMX source implementation.
- **Polling không phải notification:** giá trị lặp không phải lỗi, transition xảy ra giữa polls có thể bị bỏ lỡ.
- **`CompositeData`/OpenType** cần normalize trước khi gửi sang HTTP/JMS/AMQP/Kafka/file/SFTP.
- **Lifecycle, error handling, backpressure và security** quyết định độ tin cậy của source, đặc biệt với remote JMX.
- **Durable delivery/idempotency** không tự có từ JMX polling; business event quan trọng cần event source và inbox/outbox/broker phù hợp.

Trong module **SPRING_INTEGRATION_ADAPTERS**, bài học minh họa việc nối **JMX attribute → Spring Poller → MessageChannel → IntegrationFlow → downstream adapter**. Khi hiểu đúng sự khác biệt giữa **snapshot sampling** và **event processing**, người học có thể xây luồng monitoring hiệu quả mà không tuyên bố bảo đảm “không mất event” khi nguồn chưa hề ghi nhận event đó.

### 25.1. Tài liệu tham khảo để đối chiếu version

- [Spring Integration Reference – JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): các adapter JMX, attribute polling, notification listening và XML namespace.
- [Spring Integration Reference – Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): cơ chế poller, fixed-delay, fixed-rate và endpoints.
- [Java 17 JMX API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html): `MBeanServer`, `MBeanServerConnection`, `ObjectName`, JMX exception types.
- [Java MemoryUsage](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): heap memory information và quy tắc max value.

**Lưu ý STEP 4:** ví dụ trong bài là tài liệu Knowledge để học và trao đổi kỹ thuật. Khi áp dụng dự án thực, đối chiếu dependencies/XSD/API theo version của ứng dụng và chạy integration tests. Vòng Content QA/refactor chuyên sâu nằm ở STEP 6, không thuộc nhiệm vụ viết một bài ở STEP 4.


