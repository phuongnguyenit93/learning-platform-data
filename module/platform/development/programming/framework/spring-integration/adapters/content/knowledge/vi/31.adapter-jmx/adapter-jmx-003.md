# JMX tree-polling adapter

## 1. Mục tiêu: lấy một snapshot của nhiều MBeans qua Spring Integration

Một ứng dụng Java quản lý nhiều queue: `Orders`, `Billing` và `Notifications`. Mỗi queue expose Standard MBean chứa thuộc tính `Depth` và `Healthy`. Hệ thống giám sát cần định kỳ đọc **tất cả queue MBeans đang khớp mẫu**, không phải tạo một endpoint riêng cho mỗi queue, rồi đẩy snapshot chung vào Spring Integration để xây dashboard, gửi cảnh báo hoặc xuất JSON cho một dịch vụ khác.

**JMX tree-polling adapter** giải quyết bài toán này. Nó truy vấn **cây JMX MBean** theo `ObjectName` pattern/`QueryExp`, chuyển từng MBean và thuộc tính được chọn sang một **object graph** có kiểu đơn giản như `Map`, `List`, mảng hoặc các giá trị nguyên thủy, sau đó phát **một Spring Message chứa snapshot** lên `MessageChannel` theo lịch của Spring Integration poller.

Bài **“JMX tree-polling adapter”** thuộc chương **Adapter JMX**, module **SPRING_INTEGRATION_ADAPTERS**. Module hướng đến kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành trao đổi file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; xử lý hợp đồng message, lỗi và vòng đời kết nối. Trong chuỗi đó, JMX là nguồn dữ liệu quản trị JVM, còn tree-polling là một inbound endpoint để biến tập trạng thái JMX thành Spring message có thể xử lý như các nguồn khác.

Sau bài học, người đọc có thể:

1. Phân biệt **JMX attribute polling** của một MBean với **tree polling** truy vấn nhiều MBeans, và với **notification listening**.
2. Hiểu `MBeanServerConnection`, `ObjectName` query pattern, `query-name`, optional `QueryExp` và MBean metadata.
3. Cấu hình native `int-jmx:tree-polling-channel-adapter`, `mbean-server`, `converter`, `MessageChannel` và poller.
4. Dùng `MBeanTreePollingMessageSource` trong Java DSL/`@InboundChannelAdapter` cùng `DefaultMBeanObjectConverter`.
5. Sử dụng `NamedFieldsMBeanAttributeFilter` và `NotNamedFieldsMBeanAttributeFilter` để lọc attributes trước khi converter đọc dữ liệu.
6. Xây ví dụ nhiều Standard MBeans, query theo wildcard, nhận snapshot trong IntegrationFlow và normalize payload.
7. Biết giới hạn “một snapshot” với “một sự kiện thay đổi”, cách xử lý MBean động, partial failures, OpenType và JSON.
8. Viết test JMX thật trong cùng JVM, test Spring flow/poller, và thiết kế integration test cho remote JMX.
9. Xác định các kiểm soát bảo mật, chi phí polling, thread/backpressure, metrics, retry và durable downstream handoff.
10. Chọn giữa tree-polling, attribute-polling, JMX notification-listening và một message broker theo yêu cầu thật.

**Thông điệp nền tảng:** tree polling không phải JMX event stream. Nó là **sampling**: “Ở thời điểm poll, các MBeans khớp truy vấn có những trạng thái nào?”. Nếu trạng thái thay đổi rồi trở lại giữa hai lần lấy mẫu, snapshot có thể không phản ánh biến cố đó.

## 2. Kiến trúc nguồn → snapshot → MessageChannel → downstream

~~~mermaid
flowchart LR
    M1["QueueStats MBean<br/>Orders"]
    M2["QueueStats MBean<br/>Billing"]
    M3["QueueStats MBean<br/>Notifications"]
    SERVER[("JMX MBeanServer")]
    POLLER["Spring Poller<br/>fixed-delay=5s"]
    SOURCE["MBeanTreePollingMessageSource<br/>query-name pattern"]
    CONV["MBeanObjectConverter<br/>filter attributes"]
    CH["jmx.tree.snapshots<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>validate/normalize/route"]
    DB[("Metrics / DB / outbox")]
    EXT["HTTP / JMS / AMQP / Kafka / SFTP"]
    M1 --> SERVER
    M2 --> SERVER
    M3 --> SERVER
    POLLER --> SOURCE
    SOURCE -->|"queryNames / inspect"| SERVER
    SOURCE --> CONV
    CONV -->|"Message<graph>"| CH --> FLOW --> DB
    FLOW --> EXT
~~~

Một chu kỳ gồm:

1. Poller tới lịch, kích hoạt `MBeanTreePollingMessageSource.receive()`.
2. Source dùng `MBeanServerConnection` truy vấn các MBeans khớp `query-name` (và `query-expression` nếu cấu hình).
3. Với mỗi MBean được chọn, `MBeanObjectConverter` lấy/biến đổi thông tin MBean theo `MBeanAttributeFilter`.
4. Framework tạo một **object graph** gồm các đối tượng đơn giản như `Map`, `List`, mảng, primitive/string; graph không bắt buộc là cùng một DTO class do ứng dụng định nghĩa.
5. Poller phát Spring message lên output channel; flow nhận **snapshot toàn tập** thay vì tự động phát mỗi attribute thành một message riêng.
6. Flow chuẩn hóa và chuyển tới metrics, database hoặc downstream adapters theo schema/policy ứng dụng.
7. Poll tiếp theo truy vấn lại tập MBeans hiện thời; nếu có MBean mới hoặc biến mất, nội dung snapshot có thể khác.

**Ranh giới trách nhiệm:** JMX quản lý MBeans và attribute access; Spring poller quyết định chu kỳ; converter quyết định biểu diễn/lọc dữ liệu; IntegrationFlow kiểm soát hợp đồng dữ liệu và nghiệp vụ; downstream chịu durability riêng.

### 2.1. Snapshot 5 giây/lần không tương đương năm giây đầy đủ dữ kiện

~~~text
12:00:00 → {Orders=12, Billing=3}
12:00:05 → {Orders=20, Billing=4}
12:00:10 → {Orders=15, Billing=2, Notifications=9}
~~~

Nếu Orders tăng từ 12 lên 500 rồi về 20 trong khoảng 12:00:00–12:00:05, tree polling có thể không thấy đỉnh 500. Nếu Notifications mới được đăng ký trước poll 12:00:10, nó có thể xuất hiện trong snapshot sau; cần kiểm tra kỹ source query và lifecycle thực tế.

### 2.2. Một source có thể đọc rất nhiều attributes trong một poll

Tree-polling khác attribute-polling ở chỗ một lần `receive()` có thể duyệt nhiều MBeans và nhiều attributes. Nếu filter quá rộng, một poll có thể thực hiện nhiều JMX reads và tạo object graph lớn. Vì vậy hạn chế `query-name` và attribute filter **ngay từ đầu** thay vì đọc toàn bộ JVM rồi mới lọc ở downstream.

## 3. JMX nền tảng cho tree query

### 3.1. MBean, MBeanServerConnection và ObjectInstance

- **MBean**: thành phần Java expose managed attributes/operations; ví dụ `QueueStats` có `Depth`, `Healthy`.
- **MBeanServer**: quản lý registry trong JVM; có thể lấy bằng `ManagementFactory.getPlatformMBeanServer()`.
- **MBeanServerConnection**: interface thao tác với local hoặc remote JMX server, dùng cho `queryNames`, `queryMBeans`, `getMBeanInfo`, `getAttribute`.
- **ObjectName**: định danh JMX gồm domain và key properties, ví dụ `demo.integration:type=QueueStats,name=Orders`.
- **ObjectInstance**: một MBean được tìm thấy, chứa ObjectName và class name theo JMX.
- **QueryExp**: JMX query expression dùng thêm predicate ngoài tên pattern khi cần.
- **MBeanAttributeInfo**: metadata attribute từ `MBeanInfo`, gồm tên, kiểu, read/write access.

Các khái niệm này không phải Spring `MessageHeaders`, Kafka topic hay MQTT client ID. JMX object names và Spring bean/channel IDs là hai không gian tên độc lập.

### 3.2. ObjectName pattern và query-name

Mẫu muốn chọn ba queue instances:

~~~text
demo.integration:type=QueueStats,name=Orders
demo.integration:type=QueueStats,name=Billing
demo.integration:type=QueueStats,name=Notifications

Pattern:
demo.integration:type=QueueStats,name=*
~~~

Pattern được dùng trong **`query-name`** của tree-polling. Nó không giống `object-name` của single attribute-polling adapter, vốn đọc một MBean cụ thể.

~~~java
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();

ObjectName filter = new ObjectName(
        "demo.integration:type=QueueStats,name=*");

var matches = server.queryNames(filter, null);

for (ObjectName match : matches) {
    System.out.println(match.getCanonicalName());
}
~~~

Một `ObjectName` pattern có thể chọn nhiều MBeans; một `ObjectName` cụ thể chỉ một. Query pattern nên hẹp, ưu tiên domain/type/tenant được quản lý, không để client HTTP không tin cậy quyết định truy vấn `*:*` toàn JVM.

### 3.3. query-name khác query-expression

| Khái niệm | Kiểu JMX | Mục đích |
| --- | --- | --- |
| `query-name` | `ObjectName` pattern, thường biểu diễn bằng chuỗi trong XML. | Chọn MBeans có domain/key properties khớp. |
| `query-expression` | `QueryExp`/expression hỗ trợ bởi source. | Lọc thêm theo điều kiện JMX (nếu cần). |
| Attribute filter | `MBeanAttributeFilter`. | Quyết định attributes nào được đọc/đưa vào graph. |
| Spring `.filter(...)` | Predicate trong IntegrationFlow. | Lọc **message snapshot** sau khi source đã đọc. |

Không nhầm `query-name` dùng tìm **MBeans** với `NamedFieldsMBeanAttributeFilter` dùng chọn **attributes** của MBeans tìm được.

### 3.4. Một attribute readable có thể có getter đắt đỏ

JMX attributes là code của MBean. `getDepth()` có thể chỉ đọc `AtomicInteger`, nhưng getters của một số thư viện có thể làm I/O, lock hoặc tính thống kê nặng. Tree polling nhiều MBeans/attributes cộng dồn chi phí getter. Một server điều khiển JMX remote không phải free network call.

### 3.5. JMX OpenType: CompositeData và TabularData

MXBeans có thể expose `CompositeData`, `TabularData`, array hoặc structures phức tạp. Converter mặc định cố đưa MBean values về các cấu trúc đơn giản `Map`/`List`/mảng theo semantics hỗ trợ, nhưng downstream vẫn phải validate object graph thực và không giả định mọi custom Java class được serializer JSON xử lý an toàn.

## 4. So sánh tree-polling với các JMX adapters khác

| Endpoint | Trigger | Đối tượng đọc | Payload thường gặp | Khi nên dùng |
| --- | --- | --- | --- | --- |
| JMX attribute-polling inbound | Poller | Một attribute trên một MBean cụ thể. | Giá trị đơn: `Integer`, `String`, `CompositeData`. | Cần gauge/health của một nguồn rõ ràng. |
| JMX tree-polling inbound | Poller | Tập MBeans khớp query và những attributes được chọn. | Graph của primitives, `Map`, `List`, arrays. | Inventory/snapshot dashboard nhiều MBeans. |
| JMX notification-listening inbound | Callback listener | Notifications được MBean chủ động phát. | `javax.management.Notification`. | Cần sự kiện/transition gần lúc nó xảy ra. |
| JMX operation-invoking outbound | Spring message | Gọi operation trên MBean. | Không nhất thiết có reply. | Thực thi quản trị/điều khiển. |
| JMX operation-invoking gateway | Request-reply | Gọi operation và nhận result. | Message reply theo operation. | Cần trả lời kết quả thao tác quản trị. |
| JMS/AMQP/Kafka inbound | Broker/stream | Stored messages/records. | Message/record domain. | Muốn durability, retry/replay/consumer coordination. |

**Không dùng tree-polling để hứa bắt mọi thay đổi** vì nó chủ yếu phục vụ **quét trạng thái**; nếu mục tiêu là từng business event không được mất, cần nguồn event và hạ tầng bền.

## 5. XML namespace: native tree-polling channel adapter

Spring Integration có native endpoint `int-jmx:tree-polling-channel-adapter`.

~~~xml
<int-jmx:tree-polling-channel-adapter
        id="queueTreeAdapter"
        channel="jmxTreeSnapshots"
        query-name="demo.integration:type=QueueStats,name=*">
    <int:poller max-messages-per-poll="1"
                fixed-rate="5000"/>
</int-jmx:tree-polling-channel-adapter>
~~~

Đây là dạng native chính thức: `query-name` là JMX ObjectName pattern, `channel` là output Spring MessageChannel và nested poller đặt cadence 5000 mili giây. Nếu trong context có bean `mbeanServer`, adapter có thể tự tìm theo tên đó. Nếu dùng server khác, cấu hình rõ `mbean-server`.

### 5.1. Cấu hình XML wiring đầy đủ

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

    <int:channel id="jmxTreeSnapshots"/>

    <int-jmx:tree-polling-channel-adapter
            id="queueTreeAdapter"
            channel="jmxTreeSnapshots"
            mbean-server="mbeanServer"
            query-name="demo.integration:type=QueueStats,name=*">
        <int:poller max-messages-per-poll="1"
                    fixed-delay="5000"/>
    </int-jmx:tree-polling-channel-adapter>

    <bean id="treeLogHandler"
          class="demo.jmxtree.TreeLogHandler"/>

    <int:service-activator
            input-channel="jmxTreeSnapshots"
            ref="treeLogHandler"
            method="handle"/>
</beans>
~~~

XML tạo MBeanServer và Spring channel/endpoint/handler, **không tự sinh ba QueueStats MBeans**. Cần publisher MBeans được register trong cùng server theo names tương ứng; mục 10 sẽ tạo chúng với `MBeanExporter`.

### 5.2. Handler đơn giản cho XML example

~~~java
package demo.jmxtree;

public class TreeLogHandler {

    public void handle(Object treeSnapshot) {
        // Lab only: ghi metadata đã được giới hạn.
        System.out.println("Đã nhận JMX tree snapshot, class="
                + treeSnapshot.getClass().getName());
    }
}
~~~

Không log toàn bộ tree payload nếu có attributes chứa secrets, usernames, JDBC URLs hoặc dữ liệu nhạy cảm. Payload có thể lớn hơn nhiều so với một Integer từ attribute-polling adapter.

### 5.3. query-name, object-name và channel không thể thay cho nhau

~~~text
JMX query-name:  demo.integration:type=QueueStats,name=*
Spring channel:  jmxTreeSnapshots
Adapter ID:      queueTreeAdapter
MBeanServer bean: mbeanServer
~~~

`query-name` chọn tập JMX MBeans. `jmxTreeSnapshots` định danh Spring channel. Nếu MBean query match không có đối tượng, source có thể trả cấu trúc rỗng hoặc không phát message theo implementation/version; test explicit empty-tree behavior thay vì giả định hệ thống sẽ gửi một “empty event” có định dạng cố định.

## 6. Converter: giảm dữ liệu từ nguồn trước khi tạo graph

Theo mặc định, tree adapter đưa vào graph các attributes mà converter chọn. Mẫu đơn giản nhất để giới hạn chỉ hai attributes là:

~~~text
MBeans:
  Orders:        Depth, Healthy, ConnectionUrl, LastError, DebugInfo, ...
  Billing:       Depth, Healthy, ConnectionUrl, LastError, DebugInfo, ...
  Notifications: Depth, Healthy, ConnectionUrl, LastError, DebugInfo, ...

MBeanAttributeFilter cho phép: Depth, Healthy
⇒ downstream chỉ cần graph gồm fields thuộc whitelist này
~~~

Đây là **data minimization**: giảm chi phí polling và rủi ro tiết lộ config/credentials. Không đợi gửi toàn bộ graph sang Kafka rồi mới xóa những fields nhạy cảm.

### 6.1. MBeanObjectConverter

`MBeanObjectConverter` là chiến lược chuyển một `ObjectInstance` và server connection thành một object đơn giản:

~~~java
Object convert(
        MBeanServerConnection connection,
        ObjectInstance instance);
~~~

Spring Integration cung cấp `DefaultMBeanObjectConverter` với constructor nhận `MBeanAttributeFilter`. Converter được source dùng trong quá trình quét và build snapshot graph, không phải một Spring message converter cho raw MQTT bytes hay JSON schema tự động.

### 6.2. NamedFieldsMBeanAttributeFilter

`NamedFieldsMBeanAttributeFilter` chọn attributes theo tên:

~~~java
import org.springframework.integration.jmx.MBeanAttributeFilter;
import org.springframework.integration.jmx.NamedFieldsMBeanAttributeFilter;

MBeanAttributeFilter filter =
        new NamedFieldsMBeanAttributeFilter(
                "Depth", "Healthy");
~~~

Nếu một MBean không expose `Healthy`, filter **không thể tạo ra attribute đó**: nó chỉ quyết định có đọc attribute đang được MBean khai báo hay không.

**Phạm vi package:** đoạn code trên dùng Spring Integration **6.x**. Ở Spring Integration **7.x**, các converter/filter/tree source inbound nằm trong `org.springframework.integration.jmx.inbound`. Cần thay imports theo dependency version; không trộn 6.x và 7.x.

### 6.3. NotNamedFieldsMBeanAttributeFilter

`NotNamedFieldsMBeanAttributeFilter` loại trừ attributes theo tên:

~~~java
import org.springframework.integration.jmx.NotNamedFieldsMBeanAttributeFilter;

var exclude =
        new NotNamedFieldsMBeanAttributeFilter(
                "JdbcPassword", "AccessToken");
~~~

Blocklist phù hợp khi bạn muốn bỏ một số fields nhạy cảm đã biết, nhưng **allowlist an toàn hơn** khi MBean schema có thể được mở rộng với attributes mới. Một attribute mới như `ApiSecret` có thể lọt qua blocklist cũ.

### 6.4. XML converter bean và filter

~~~xml
<bean id="queueTreeAttributeFilter"
      class="org.springframework.integration.jmx.NamedFieldsMBeanAttributeFilter">
    <constructor-arg>
        <array value-type="java.lang.String">
            <value>Depth</value>
            <value>Healthy</value>
        </array>
    </constructor-arg>
</bean>

<bean id="queueTreeConverter"
      class="org.springframework.integration.jmx.DefaultMBeanObjectConverter">
    <constructor-arg ref="queueTreeAttributeFilter"/>
</bean>

<int-jmx:tree-polling-channel-adapter
        id="queueTreeAdapter"
        channel="jmxTreeSnapshots"
        mbean-server="mbeanServer"
        query-name="demo.integration:type=QueueStats,name=*"
        converter="queueTreeConverter">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-jmx:tree-polling-channel-adapter>
~~~

Đây là cấu hình **thay thế** adapter không converter ở mục 5, không đặt thêm một endpoint cùng `id` trong cùng XML. Các beans trên có thể được đưa vào XML context tương ứng, sử dụng Spring Integration **6.x** package names. Với Spring Integration 7.x phải kiểm tra package class mới và schema phù hợp version.

### 6.5. Tùy chỉnh filter theo từng MBean

`MBeanAttributeFilter` nhận `ObjectName` và `attributeName`. Có thể kiểm chính xác source + field:

~~~java
import javax.management.ObjectName;
import org.springframework.integration.jmx.MBeanAttributeFilter;

MBeanAttributeFilter filter =
        (ObjectName name, String attribute) ->
                "demo.integration".equals(name.getDomain())
                && "QueueStats".equals(name.getKeyProperty("type"))
                && ("Depth".equals(attribute)
                    || "Healthy".equals(attribute));
~~~

Nên triển khai policy filter với các tên MBeans được phép, không chỉ field name, khi nguồn remote có nhiều domains/trust boundaries.

## 7. Poller: cadence, số messages và tải nguồn

### 7.1. max-messages-per-poll=1 nghĩa là gì?

Tree source có khả năng trả một snapshot của **nhiều** MBeans mỗi `receive()`. Vì vậy:

~~~text
Một poll task
  → một receive()
  → query MBeans Orders/Billing/Notifications
  → một graph snapshot
  → một Spring message
~~~

`max-messages-per-poll="1"` giới hạn **số lần gọi source trong một poll task**, không hạn chế số MBeans nằm trong graph. Đặt 10 có thể khiến cùng cây JMX được query mười lần gần nhau, không có nghĩa “mỗi lần đọc một queue”.

### 7.2. fixed-rate và fixed-delay

| Trigger | Semantics | Điểm cần theo dõi |
| --- | --- | --- |
| `fixed-delay=5000` | Đợi theo interval sau khi lần trước hoàn tất, tùy scheduler. | Khi tree query chậm, cadence thực sẽ dài hơn. |
| `fixed-rate=5000` | Lịch dự kiến ở nhịp 5s. | Nếu tree query quá chậm, tasks có thể bị delay/overlap theo scheduler/executor. |
| Cron | Lấy snapshot ở giờ/phút lịch cụ thể. | Timezone và các khoảng lịch thiếu samples. |

Nếu có 500 MBeans x 20 attrs được đọc mỗi 5 giây, hệ thống có thể làm khoảng **10.000 attribute accesses mỗi chu kỳ**, chưa tính metadata queries và remote calls. Đây là ví dụ công suất lý thuyết, không phải số lượng method calls chính xác của converter implementation. Hãy đo thực tế với data filter và remote latency.

### 7.3. Chu kỳ tree polling không có transaction snapshot toàn JVM

Tree query có thể kéo dài hàng trăm mili giây hoặc vài giây. Trong lúc đó Orders Depth đã thay đổi khi Billing mới được đọc. Object graph cuối có thể chứa **các giá trị được lấy ở những thời điểm khác nhau**, không phải một transaction snapshot atomic của toàn MBeanServer. Với quyết định đòi nhất quán chéo nhiều queues, cần nguồn cung cấp snapshot atomic hoặc versioned read protocol.

### 7.4. Polling thường lặp cùng values

Khi không có thay đổi, source có thể phát graph tương tự ở chu kỳ sau. Điều này đúng với sampling, không phải “JMX duplicate delivery”. Một dashboard gauge có thể cập nhật lại; còn trigger như gửi email phải có stateful change detection/hysteresis/cooldown.

### 7.5. Quy tắc chọn interval

- Ưu tiên giới hạn số MBeans/attributes đọc.
- Ước lượng p95/p99 thời gian quét toàn graph, không chỉ một getter.
- Đặt interval lớn hơn chi phí snapshot điển hình, hoặc thiết kế concurrency/buffer rõ.
- Đặt limits cho object graph và cách xử lý khi MBeans tăng đột biến.
- Nếu đòi bắt mọi short-lived event, chuyển sang notification/event source, không chỉ thu hẹp interval.


## 8. Object graph được gửi trong Spring Message

Tree source trả **snapshot của tập MBeans**, không trả một `Notification` hoặc một `Integer` duy nhất. Spring Integration chuyển MBean data sang các đối tượng đơn giản như `Map`, `List`, mảng và primitives để downstream dễ xử lý hoặc xuất JSON. Nhưng cấu trúc key, thứ tự và kiểu root cụ thể cần được xác minh trên phiên bản converter đang chạy; không mặc định một DTO có tên `queues` hay `observedAt` được sinh sẵn.

### 8.1. Schema JSON do ứng dụng tự chuẩn hóa

Giả sử muốn gửi cho monitoring API, transformer có thể tạo schema:

~~~json
{
  "schemaVersion": 1,
  "sourceNode": "orders-service-01",
  "observedAt": "2026-11-23T03:20:00Z",
  "kind": "JMX_MBEAN_TREE_SNAPSHOT",
  "queues": [
    {
      "objectName": "demo.integration:type=QueueStats,name=Orders",
      "name": "Orders",
      "depth": 12,
      "healthy": true
    },
    {
      "objectName": "demo.integration:type=QueueStats,name=Billing",
      "name": "Billing",
      "depth": 3,
      "healthy": true
    }
  ]
}
~~~

**Đây là output ứng dụng tự thiết kế, không phải JSON mặc định mà native adapter bảo đảm phát ra.** Source chỉ tạo graph từ query/converter. Transformer phải xác minh nested keys/types, quản lý schema version, source identity và timestamp.

### 8.2. Snapshot không phải transaction toàn JMX server

Các MBeans có thể được đọc tuần tự; Orders Depth lúc 03:20:00.100 và Billing Depth lúc 03:20:00.800 thuộc hai thời điểm khác nhau. Nếu nghiệp vụ cần trạng thái nhất quán giữa queues, phải định nghĩa snapshot version/epoch hoặc API atomic ở nguồn. Đặt chung một `observedAt` trên graph không tự biến reads thành transaction.

### 8.3. Empty tree và failed tree phải khác nhau

Một `query-name` không match MBean nào có thể dẫn tới graph rỗng hoặc không có message tùy implementation; lỗi `IOException`/authorization/attribute getter cũng có thể làm poll thất bại. **Không diễn giải “không thấy MBean” là “queue đã bị xóa”** nếu không có dấu hiệu poll thành công và snapshot quality.

### 8.4. Nhận diện inventory diff

~~~text
Snapshot #1: Orders, Billing
Snapshot #2: Orders, Billing, Notifications
Diff:         + Notifications
~~~

Tạo diff business chỉ sau khi xác minh cả hai snapshots hợp lệ và cùng source scope; sự biến mất tạm thời do remote JMX lỗi không được tự coi là một business deletion.

## 9. Dependency, phiên bản và cấu trúc project

Ví dụ thực hành chọn **Java 17+, Spring Boot và Spring Integration 6.x** để dùng những imports hiện có trong nhánh 6.x:

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

Dùng Spring Boot BOM tương thích; không trộn modules Spring Integration 6.x và 7.x. Với **Spring Integration 7.x**, các classes inbound `MBeanTreePollingMessageSource`, `DefaultMBeanObjectConverter`, `NamedFieldsMBeanAttributeFilter` được đặt trong package `org.springframework.integration.jmx.inbound` thay vì `org.springframework.integration.jmx`. Đổi import theo API Javadocs chính xác trước khi build.

~~~text
src/main/java/demo/jmxtree/
  JmxTreeApplication.java
  QueueStatsMBean.java
  QueueStats.java
  JmxMBeanConfiguration.java
  JmxTreeSourceConfiguration.java
  JmxTreeFlowConfiguration.java
  TreeSnapshotSink.java

src/test/java/demo/jmxtree/
  JmxTreeSourceTest.java
  JmxTreePollingTest.java
~~~

Các class đều thuộc package `demo.jmxtree`; mỗi class/interface `public` nằm trong file trùng tên.

## 10. Ví dụ nhiều MBeans trên một MBeanServer

### 10.1. Standard MBean interface

~~~java
package demo.jmxtree;

public interface QueueStatsMBean {
    int getDepth();
    boolean isHealthy();
    String getCredentialHint();
    void setDepth(int value);
}
~~~

JMX expose attributes `Depth`, `Healthy` và `CredentialHint`. Thuộc tính `CredentialHint` có dữ liệu **giả** để kiểm chứng filter không cho nó đi vào graph, không bao giờ thử với credential thật. `setDepth` phục vụ lab; principal production chỉ đọc.

### 10.2. MBean implementation

~~~java
package demo.jmxtree;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueStats implements QueueStatsMBean {

    private final String name;
    private final AtomicInteger depth = new AtomicInteger();

    public QueueStats(String name, int initialDepth) {
        this.name = name;
        setDepth(initialDepth);
    }

    @Override
    public int getDepth() {
        return depth.get();
    }

    @Override
    public boolean isHealthy() {
        return depth.get() < 100;
    }

    @Override
    public String getCredentialHint() {
        return "SAMPLE-NOT-A-SECRET-" + name;
    }

    @Override
    public void setDepth(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("Depth không được âm");
        }
        depth.set(value);
    }
}
~~~

Getters không tự phát notification. `isHealthy()` và `getDepth()` là hai reads riêng; chúng có thể nhìn trạng thái khác nhau nếu `Depth` thay đổi giữa các lần đọc. Nếu phải bảo đảm cặp thuộc tính nhất quán, cần expose một immutable aggregate getter hoặc khóa/phiên bản dữ liệu ở nguồn.

### 10.3. MBeanExporter đăng ký ba queues

~~~java
package demo.jmxtree;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
class JmxMBeanConfiguration {

    static final String ORDERS =
            "demo.integration:type=QueueStats,name=Orders";
    static final String BILLING =
            "demo.integration:type=QueueStats,name=Billing";
    static final String NOTIFICATIONS =
            "demo.integration:type=QueueStats,name=Notifications";

    @Bean(name = "mbeanServer")
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean("ordersStats")
    QueueStats ordersStats() {
        return new QueueStats("Orders", 12);
    }

    @Bean("billingStats")
    QueueStats billingStats() {
        return new QueueStats("Billing", 3);
    }

    @Bean("notificationsStats")
    QueueStats notificationsStats() {
        return new QueueStats("Notifications", 9);
    }

    @Bean
    MBeanExporter queueStatsExporter(
            @Qualifier("mbeanServer") MBeanServer server,
            @Qualifier("ordersStats") QueueStats orders,
            @Qualifier("billingStats") QueueStats billing,
            @Qualifier("notificationsStats") QueueStats notifications) {

        var exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
                ORDERS, orders,
                BILLING, billing,
                NOTIFICATIONS, notifications));
        return exporter;
    }
}
~~~

`@Qualifier` giúp phân biệt ba Spring beans cùng kiểu QueueStats. `MBeanExporter` đăng ký object names chính xác, không phải query-name pattern. Nếu một ObjectName đã được một exporter khác đăng ký, context có thể fail; không tự xóa MBean không thuộc sở hữu ứng dụng.

## 11. Java native tree source + poller + channel

### 11.1. MBeanTreePollingMessageSource

~~~java
package demo.jmxtree;

import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.jmx.DefaultMBeanObjectConverter;
import org.springframework.integration.jmx.MBeanTreePollingMessageSource;
import org.springframework.integration.jmx.NamedFieldsMBeanAttributeFilter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class JmxTreeSourceConfiguration {

    @Bean("jmx.tree.raw")
    MessageChannel treeRawChannel() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            channel = "jmx.tree.raw",
            poller = @Poller(
                    fixedDelay = "5000",
                    maxMessagesPerPoll = "1"))
    MBeanTreePollingMessageSource treeSource(
            @Qualifier("mbeanServer") MBeanServer server) {

        var allowed = new NamedFieldsMBeanAttributeFilter(
                "Depth", "Healthy");
        var converter = new DefaultMBeanObjectConverter(allowed);

        var source = new MBeanTreePollingMessageSource(converter);
        source.setServer(server);
        source.setQueryName(
                "demo.integration:type=QueueStats,name=*");

        return source;
    }
}
~~~

Trong Spring Integration 6.x, `MBeanTreePollingMessageSource` là native `MessageSource<Object>`; constructor nhận `MBeanObjectConverter`, `setServer(...)` nhận `MBeanServerConnection` và `setQueryName(...)` là query pattern. `@InboundChannelAdapter` tạo polling endpoint gắn source vào `jmx.tree.raw`. Không cần tự viết `MBeanServer.queryNames` loop.

Đối với 7.x, cập nhật imports của ba kiểu JMX inbound vào `org.springframework.integration.jmx.inbound`, kiểm Java/Spring baseline và test lại query/filter semantics.

### 11.2. IntegrationFlow nhận whole-tree payload

~~~java
package demo.jmxtree;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class TreeSnapshotSink {

    private final List<Object> snapshots =
            new CopyOnWriteArrayList<>();

    void add(Object graph) {
        snapshots.add(graph);
    }

    List<Object> snapshot() {
        return List.copyOf(snapshots);
    }

    void clear() {
        snapshots.clear();
    }
}
~~~

~~~java
package demo.jmxtree;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
class JmxTreeFlowConfiguration {

    @Bean
    TreeSnapshotSink treeSnapshotSink() {
        return new TreeSnapshotSink();
    }

    @Bean
    IntegrationFlow jmxTreeFlow(TreeSnapshotSink sink) {
        return IntegrationFlow.from("jmx.tree.raw")
                .handle(Object.class, (payload, headers) -> {
                    sink.add(payload);
                    return null;
                })
                .get();
    }
}
~~~

Đây là **một Spring message chứa object graph**, không tự sinh ba messages chỉ vì có ba MBeans. `return null` biểu thị handler một chiều. Sink chỉ dùng cho lab; không lưu bền hoặc giới hạn memory theo thời gian.

### 11.3. Spring Boot entry point

~~~java
package demo.jmxtree;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmxTreeApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                JmxTreeApplication.class, args);
    }
}
~~~

Khi các `@Configuration` cùng package được nạp, MBeans được export, tree source được schedule và IntegrationFlow nhận snapshot. Trong app có nhiều Spring contexts, cần đảm bảo reader và exporter cùng MBeanServer; cùng ObjectName ở hai MBeanServers khác nhau **không** tạo một entity chung.

## 12. Kiểm tra thủ công một snapshot

Đầu tiên xác minh nguồn JMX có các MBeans khớp pattern:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.ObjectName;

var server = ManagementFactory.getPlatformMBeanServer();

ObjectName query = new ObjectName(
        "demo.integration:type=QueueStats,name=*");

var names = server.queryNames(query, null);

System.out.println("MBeans matched: " + names.size());
for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
~~~

Đây là bước JMX diagnostic; không tự kích hoạt Spring flow. Nếu `names.size()==0`, sửa MBean export/namespace trước khi debug `IntegrationFlow`.

Sau khi ứng dụng chạy, gọi trong lab:

~~~java
ordersStats.setDepth(85);
billingStats.setDepth(11);
~~~

Poll tiếp theo có thể thấy graph với các queue values mới. Không mặc định graph được đưa ra theo một thứ tự ổn định vì `queryMBeans/queryNames` không hứa order; nếu API downstream cần order, normalize và sort theo `ObjectName.getCanonicalName()`.

### 12.1. Chỉ lấy fields cần thiết

Filter ở `treeSource` chỉ cho phép `Depth` và `Healthy`. `CredentialHint` là giá trị giả không cần xuất hiện trong mapped attributes. Nếu transformer downstream vẫn lấy hoặc hiển thị nó, cần kiểm tra filter có được áp dụng đúng và có endpoint khác không dùng converter.

### 12.2. Tree graph cần có một hợp đồng JSON riêng

Một DTO có thể là:

~~~java
package demo.jmxtree;

import java.time.Instant;
import java.util.List;

record QueueState(
        String objectName,
        String queueName,
        int depth,
        boolean healthy) {
}

record QueueTreeSnapshot(
        String sourceNode,
        Instant observedAt,
        int schemaVersion,
        List<QueueState> queues) {
}
~~~

`QueueTreeSnapshot` **không được native source tự tạo**. Hãy quan sát graph thật trên version cụ thể, viết mapper có validation tests, rồi xuất JSON. Nếu cần nhiều messages mỗi queue, transform thành `List<QueueState>` và `split()` có chủ đích; không coi in-memory split là durable queue.

### 12.3. Phân biệt snapshot với event

Ba lần poll trả Orders=85 là ba **quan sát**, không có nghĩa đã xảy ra ba thay đổi. Một cảnh báo “queue vượt ngưỡng” nên dựa trên state transition/hysteresis hoặc điều kiện liên tục, không gửi email ở mỗi poll.

### 12.4. Những điều native adapter không tự tạo

- Không có `observedAt`/`sourceNode`/`schemaVersion` business DTO theo mặc định.
- Không có ACK/replay kiểu JMS/Kafka.
- Không tự bảo đảm snapshot atomic giữa MBeans.
- Không tự ngăn alerts lặp khi state giữ nguyên.
- Không tự tạo per-MBean downstream messages hoặc REST endpoint.


## 13. JUnit kiểm tra query MBeans và attribute allowlist

Test đầu tiên xác minh **MBeanServer API** độc lập với Spring scheduling; test sau xác minh source native trả message và lọc dữ liệu.

### 13.1. Query ObjectName pattern không cần Spring context

~~~java
package demo.jmxtree;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class JmxTreeQueryTest {

    @Test
    void queryFindsOnlyMatchingMBeans() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("tree-test");
        ObjectName orders = new ObjectName(
                "demo.integration:type=QueueStats,name=Orders");
        ObjectName billing = new ObjectName(
                "demo.integration:type=QueueStats,name=Billing");
        ObjectName other = new ObjectName(
                "demo.integration:type=AnotherType,name=Example");

        try {
            server.registerMBean(new QueueStats("Orders", 12), orders);
            server.registerMBean(new QueueStats("Billing", 3), billing);
            server.registerMBean(new QueueStats("Other", 7), other);

            var matched = server.queryNames(
                    new ObjectName(
                            "demo.integration:type=QueueStats,name=*"),
                    null);

            assertEquals(2, matched.size());
            assertTrue(matched.contains(orders));
            assertTrue(matched.contains(billing));
            assertFalse(matched.contains(other));

            assertEquals(12, server.getAttribute(orders, "Depth"));
            assertEquals(true,
                    server.getAttribute(billing, "Healthy"));
        } finally {
            if (server.isRegistered(orders)) {
                server.unregisterMBean(orders);
            }
            if (server.isRegistered(billing)) {
                server.unregisterMBean(billing);
            }
            if (server.isRegistered(other)) {
                server.unregisterMBean(other);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
~~~

Test sử dụng JMX server tách biệt, đăng ký ba `QueueStats` objects nhưng một object thuộc `AnotherType`. Query `type=QueueStats` chỉ lấy hai names theo pattern.

Trong test này `QueueStats` là Standard MBean có interface `QueueStatsMBean`; class có thể được register dưới ObjectName `type=AnotherType` vì ObjectName là tên registry do người đăng ký chọn, không bắt buộc tên key `type` trùng class/interface Java. Nếu môi trường quản lý áp naming rules chặt hơn, hãy chọn MBean class riêng để minh họa nhóm khác.

### 13.2. Kiểm tra NamedFields filter

~~~java
package demo.jmxtree;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.integration.jmx.NamedFieldsMBeanAttributeFilter;

class JmxTreeAttributeFilterTest {

    @Test
    void allowlistRejectsUnneededFields() throws Exception {
        var filter = new NamedFieldsMBeanAttributeFilter(
                "Depth", "Healthy");

        ObjectName name = new ObjectName(
                "demo.integration:type=QueueStats,name=Orders");

        assertTrue(filter.accept(name, "Depth"));
        assertTrue(filter.accept(name, "Healthy"));
        assertFalse(filter.accept(name, "CredentialHint"));
        assertFalse(filter.accept(name, "DebugDump"));
    }
}
~~~

Test kiểm chính contract `MBeanAttributeFilter` tại source, không chứng minh JSON serialization hoặc remote permissions. Khi chuyển sang Spring Integration 7.x, đổi import `NamedFieldsMBeanAttributeFilter` sang package `jmx.inbound`.

## 14. JUnit tích hợp Spring tree source và IntegrationFlow

### 14.1. Nạp cấu hình Spring với JMX server nội JVM

~~~java
package demo.jmxtree;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.jmx.MBeanTreePollingMessageSource;
import org.springframework.messaging.Message;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        JmxMBeanConfiguration.class,
        JmxTreeSourceConfiguration.class,
        JmxTreeFlowConfiguration.class
})
class JmxTreeSourceTest {

    @Autowired
    @Qualifier("mbeanServer")
    MBeanServer server;

    @Autowired
    MBeanTreePollingMessageSource treeSource;

    @Test
    void treeQueryMatchesThreeQueueMBeans() throws Exception {
        ObjectName pattern = new ObjectName(
                "demo.integration:type=QueueStats,name=*");

        assertTrue(server.queryNames(pattern, null).size() >= 3);
    }

    @Test
    void nativeSourceProducesObjectGraphMessage() {
        Message<Object> result = treeSource.receive();

        assertNotNull(result);
        assertNotNull(result.getPayload());

        // Không giả định Graph root type/key order cụ thể.
        String diagnostic = String.valueOf(result.getPayload());

        assertFalse(diagnostic.contains("SAMPLE-NOT-A-SECRET"));
    }
}
~~~

Kiểm `String.valueOf(payload)` không chứa test credential là một assertion phụ để bắt lỗi obvious leakage. Trong production, nên có kiểm tra **cấu trúc graph thật** và converter behavior rõ hơn bằng fixtures/JSON mapping; stringification không phải một security boundary.

Test này đọc từ `MBeanTreePollingMessageSource.receive()` thật. Nó không chứng minh poller cadence hoặc outbound business delivery; test ở mục 14.2 bổ sung điểm đó.

### 14.2. JUnit đợi Spring polling endpoint gửi snapshot

~~~java
package demo.jmxtree;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        JmxMBeanConfiguration.class,
        JmxTreeSourceConfiguration.class,
        JmxTreeFlowConfiguration.class
})
class JmxTreePollingTest {

    @Autowired
    TreeSnapshotSink sink;

    @Autowired
    @Qualifier("ordersStats")
    QueueStats orders;

    @Test
    void treePollingEmitsSnapshotIntoFlow()
            throws InterruptedException {

        orders.setDepth(45);

        awaitSnapshot(Duration.ofSeconds(12));

        assertFalse(sink.snapshot().isEmpty());
        assertTrue(sink.snapshot().get(0) != null);
    }

    private void awaitSnapshot(Duration timeout)
            throws InterruptedException {

        long deadline = System.nanoTime() + timeout.toNanos();

        while (System.nanoTime() < deadline) {
            if (!sink.snapshot().isEmpty()) {
                return;
            }
            Thread.sleep(50);
        }

        throw new AssertionError(
                "Không có JMX tree snapshot trong thời hạn test");
    }
}
~~~

**Lưu ý import:** `@Autowired` trong đoạn test thuộc `org.springframework.beans.factory.annotation.Autowired`, không thuộc JUnit. Đây là ví dụ minh họa; cần build và chạy test thực tế với Spring Boot/Spring Integration version đã chọn trong vòng kiểm tra chuyên môn.

Test với poller 5s và deadline 12s đủ minh họa tính bất đồng bộ của scheduling. Không dùng `Thread.sleep(5000)` rồi assert cố định, vì poller có thể được schedule trước hoặc sau thời điểm test bắt đầu; bounded await đáng tin cậy hơn.

### 14.3. Giới hạn của các test

| Loại test | Điều đã xác minh | Điều chưa chứng minh |
| --- | --- | --- |
| JMX query test | `queryNames` và MBean registration/pattern. | Tree converter và Spring scheduling. |
| Filter test | Cho phép/loại attribute names. | Mapping graph, remote permissions. |
| Native source test | Source `receive()` tạo payload. | Scheduler và downstream DB. |
| Polling integration test | Spring adapter + channel/flow phát snapshot. | Tất cả network failures hoặc durable replay. |
| Remote JMX test | Connector/auth/TLS/query latency thật. | Atomic snapshot toàn MBeanServer. |

### 14.4. Test isolation và ObjectName collision

Các test contexts cùng sử dụng `ManagementFactory.getPlatformMBeanServer()` có thể cùng cố đăng ký `demo.integration:type=QueueStats,name=Orders`. Khi chạy song song, điều này có thể gây `InstanceAlreadyExistsException` hoặc lệch dữ liệu. Nên chọn ObjectNames theo test run/context, đóng contexts đúng lifecycle, hoặc serialize tests sử dụng platform server. `MBeanExporter` chỉ nên unregister MBeans do chính nó quản lý.

### 14.5. Không khẳng định một lần poll xử lý mọi biến cố

Ngay cả test thu được một snapshot tốt sau `setDepth(45)` cũng không chứng minh các transitions 45→500→45 trong một chu kỳ đã được lưu. Đó là giới hạn sampling của tree poller, không phải lỗi JUnit.

## 15. MBean registration/unregistration động

Một lợi thế của tree query là tập MBeans có thể thay đổi qua từng poll. Nhưng cần phân biệt **tập MBeans khớp lúc query**, **thời gian đọc attributes**, và **thời điểm snapshot đến flow**.

### 15.1. MBean mới có thể xuất hiện trong snapshot sau

~~~text
T0: register Orders, Billing
T1: poll → Orders, Billing
T2: register Notifications
T3: poll → Orders, Billing, Notifications (nếu truy vấn thành công)
~~~

Tree source truy vấn registry mỗi lần poll theo query; đây là đặc điểm khác với một notification listener được đăng ký với nguồn cố định. Tuy vậy, nếu MBean bị unregister **trong lúc** converter đang đọc, có thể xảy ra race/error/partial data. Không nhầm pattern với cơ chế transaction khóa registry.

### 15.2. MBean biến mất không phải business deletion chắc chắn

Một ObjectName không còn trong graph có thể vì:

- MBean bị unregister thật;
- ObjectName changed bởi deployment mới;
- JMX connection bị lỗi;
- Query có permission mới;
- Attribute getter/converter lỗi;
- Snapshot bị filter hoặc incomplete.

Ứng dụng nên lưu snapshot quality và xác định bao nhiêu lần consecutive absence mới coi nguồn không còn, thay vì ngay lập tức xóa business resource.

### 15.3. Query hẹp hơn giúp ổn định

Nếu hệ thống có nhiều domains và một nhóm MBeans được tạo/xóa liên tục, nên dùng `demo.integration:type=QueueStats,name=*` thay vì `*:*`. Kết hợp allowlist fields và mBean count limits, đo thời gian query và số source entries.

### 15.4. Giới hạn dữ liệu theo tenant/node

Hai MBeanServers ở hai JVM có thể có ObjectName giống nhau. Trong snapshot schema phải có `sourceNode` hoặc endpoint identity được cấp tin cậy. Không merge chỉ bằng ObjectName rồi kết luận đó là cùng queue. Khi remote connector reconnect sang một node khác, phát hiện source identity drift.

## 16. OpenType, getter errors và kiểu dữ liệu phức tạp

### 16.1. Một ví dụ JVM MemoryMXBean

JMX built-in `java.lang:type=Memory` cung cấp `HeapMemoryUsage`; giá trị đọc qua MBeanServer thường ở dạng `CompositeData`. Một tree query quá rộng có thể đưa nhiều MXBeans và OpenTypes vào graph.

~~~java
import java.lang.management.MemoryUsage;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

Object value = server.getAttribute(
        new ObjectName("java.lang:type=Memory"),
        "HeapMemoryUsage");

if (value instanceof CompositeData data) {
    MemoryUsage usage = MemoryUsage.from(data);
    System.out.println("Used bytes=" + usage.getUsed());
}
~~~

Đây là ví dụ **JMX trực tiếp**, không phải API trả về của tree converter mặc định. Graph tree có thể đã normalize/flatten OpenType khác đi. Muốn extract `HeapMemoryUsage` từ tree graph, phải dùng transformer theo output shape đã được test.

### 16.2. Failure modes

| Lỗi | Nguyên nhân | Chính sách |
| --- | --- | --- |
| `InstanceNotFoundException` | MBean biến mất giữa query và đọc attributes. | Retry bounded/ghi quality; không coi là zero. |
| `AttributeNotFoundException` | MBean schema thay đổi, attribute bị rename. | Cập nhật allowlist/schema, alert. |
| `MBeanException` | Getter MBean ném exception. | Phân loại source lỗi; không retry vô hạn getter hỏng. |
| `ReflectionException` | JMX invocation/accessor lỗi. | Sửa implementation hoặc version. |
| `IOException` trên remote connection | Network/RMI/TLS disruption. | Reconnect/backoff, ghi data gap. |
| `SecurityException`/access denied | Account thiếu quyền. | Sửa authorization, không tắt security. |
| JSON serialization failure | Graph có kiểu field không phù hợp. | DTO mapping/allowlist, quarantine có kiểm soát. |
| Graph quá lớn | Query quá rộng hoặc nhiều MBeans. | Giới hạn query/filter/cadence/size. |

**Không giả định** converter luôn bỏ qua tất cả MBeans lỗi và trả partial graph thành công. Tùy phiên bản/loại lỗi, `receive()` có thể fail, log lỗi hoặc có response khác. Test fault injection thực tế và phân biệt unsuccessful poll với legitimate empty tree.

### 16.3. Getter block làm chậm toàn snapshot

Một MBean `getDepth()` nhanh, MBean khác `getDebugDump()` block 10 giây. Nếu converter không có attribute filter, toàn graph có thể đến trễ. Chỉ chọn `Depth`/`Healthy` giúp giảm tải; nếu một getter allowlisted vẫn block, cần sửa nguồn hoặc tách nhóm polling và giới hạn timeout của remote connection.

## 17. Error channel, retry và độ tin cậy

Tree polling là một **nguồn sampling**, không phải broker phát lại message. Nếu poll 12:00:05 thất bại và poll 12:00:10 thành công, bạn có snapshot lúc 12:00:10; không có cách mặc định để lấy lại đầy đủ trạng thái **đã tồn tại** lúc 12:00:05.

### 17.1. Cần phân loại error theo chặng

~~~mermaid
flowchart TD
    POLL["Poller trigger"]
    QUERY["MBean query"]
    CONV["Converter + JMX getter"]
    CH["Spring MessageChannel"]
    NORMAL["Normalization/validation"]
    OUT["Metrics/DB/Outbox"]
    E["Error monitor / quarantine"]
    POLL --> QUERY --> CONV --> CH --> NORMAL --> OUT
    QUERY -. "IO/permissions" .-> E
    CONV -. "schema/getter" .-> E
    NORMAL -. "invalid graph" .-> E
    OUT -. "downstream failure" .-> E
~~~

- Source query lỗi → poll thất bại, không tạo business snapshot hợp lệ.
- Converter/attribute getter lỗi → phân biệt loại/nguồn, không mặc định empty graph.
- Channel dispatch lỗi → kiểm output subscriber/channel startup.
- Handler/transformer lỗi → error path của Spring Integration theo endpoint/poller configuration.
- Downstream DB/HTTP/Kafka lỗi → retry/buffer theo contract hệ thống đó.

### 17.2. ErrorMessage không tạo JMX replay

Spring Integration cung cấp `ErrorMessage`/`errorChannel`, advice/retry cho polling endpoints phù hợp, nhưng chúng không biến JMX MBeanServer thành durable queue. Khi cần phục hồi một event cụ thể sau crash, event phải được lưu tại nguồn hoặc một durable inbox/outbox trước đó.

### 17.3. Backoff và retry budget

Nếu remote JMX offline, polling quá dày với retry không giới hạn có thể tạo reconnection storm. Dùng backoff có giới hạn, alert khi sample age vượt SLA, không giữ thousands of jobs awaiting network. Với lỗi schema/permission cố định, sửa config/ACL thay vì retry nhanh mãi.

### 17.4. Poison/oversized graph

Converter có thể gặp attribute type bất ngờ hoặc graph quá lớn. Nên reject/quarantine có reason, size, source identity và captured metadata có kiểm soát; **không log full graph** chứa bí mật. Với monitoring, có thể degrade health status thành `UNKNOWN`/`STALE` thay vì thay nguồn lỗi thành Depth=0.


## 18. Remote JMX tree-polling: connection, bảo mật và recovery

`MBeanTreePollingMessageSource.setServer(MBeanServerConnection)` có thể dùng server nội JVM hoặc remote `MBeanServerConnection` lấy qua `JMXConnector`. Với remote JMX, cùng một tree query có thêm network latency, auth/TLS, RMI routing và các tình huống connection mất.

### 18.1. Kết nối remote trong môi trường lab

~~~java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

// Đây là URL lab. Server không tự xuất hiện chỉ vì tạo URL.
JMXServiceURL url = new JMXServiceURL(
        "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi");

// secureEnvironment: Map<String, ?> do cấu hình bảo mật cấp.
// Phải bật xác thực và TLS khi triển khai remote production.
JMXConnector connector =
        JMXConnectorFactory.connect(url, secureEnvironment);

MBeanServerConnection remote =
        connector.getMBeanServerConnection();

// treeSource.setServer(remote);
// Khi không dùng: connector.close().
~~~

`secureEnvironment` là placeholder dành cho một cấu hình thực sự có credentials/TLS policy; không dùng code này với unauthenticated public JMX. Cần quản lý connector như một Spring bean có lifecycle/close phù hợp. RMI có thể cần registry port và remote endpoint port riêng; trong Docker/Kubernetes phải kiểm RMI hostname, firewall và chứng chỉ.

### 18.2. Remote query có thể rất đắt

Tree query 500 MBeans × 20 attributes có khả năng cần đọc rất nhiều properties, không tương đương một GET HTTP nhỏ. Giới hạn query domain/type, dùng filter whitelist, đo p95/p99 scan duration và serialized snapshot size. Nếu thời gian đọc cây lớn hơn poll interval, fixed-rate 5 giây **không** có nghĩa mỗi năm giây hoàn tất một snapshot mới.

### 18.3. Reconnect không replay các trạng thái đã bỏ lỡ

Mất remote connection 30 giây rồi poll thành công chỉ cung cấp trạng thái **lúc phục hồi**. Các MBeans xuất hiện rồi biến mất trong 30 giây có thể không được quan sát. Muốn event history/replay phải có nguồn bền ở JVM phát, JMX notification bridge hoặc broker.

### 18.4. Không merge hai JVM chỉ vì ObjectName giống nhau

ObjectName `demo.integration:type=QueueStats,name=Orders` có thể xuất hiện ở JVM A và JVM B. Khi normalize, phải kèm `sourceNode`/cluster ID đáng tin; ObjectName một mình không có global uniqueness giữa các MBeanServers.

## 19. Threading, backpressure và tài nguyên

~~~mermaid
flowchart LR
    P["Poller"]
    Q["JMX query"]
    C["Converter/getters"]
    CH["DirectChannel"]
    D["Slow HTTP / DB handler"]
    P --> Q --> C --> CH --> D
~~~

Với `DirectChannel`, handler có thể chạy đồng bộ trong task polling. Nếu remote query mất 8 giây và handler HTTP mất 10 giây, pipeline mất 18 giây cho một sample; không mong một poll hoàn tất mỗi 5 giây chỉ nhờ đặt `fixed-delay="5000"`.

### 19.1. ExecutorChannel/QueueChannel không tự có durability

Có thể tách source khỏi downstream bằng bounded `ExecutorChannel` hoặc `QueueChannel`, nhưng phải quyết định:

1. Thread pool size/queue capacity.
2. Chính sách queue đầy: backpressure, reject hoặc drop stale.
3. Error channel của async tasks.
4. Snapshot memory size và downstream lag.
5. Drain/shutdown khi context đóng.
6. Thời điểm “message đã được channel nhận” khác “business commit thành công”.
7. Khi cần không mất dữ liệu đã nhận, durable inbox/outbox thay RAM buffer.

### 19.2. Snapshot cũ có thể cần bị loại

Với dashboard chỉ muốn current gauge, replay 500 snapshots trễ 20 phút có thể tạo trạng thái lạc hậu; một policy giữ latest snapshot phù hợp hơn. Với audit/time-series, từng successful snapshot cần timestamp/retention và có thể phải persist. **Chọn semantics theo mục tiêu**, không mặc định mỗi sample có giá trị như một business event.

### 19.3. Capacity planning mẫu

Nếu poll 100 MBeans với 5 fields mỗi 10 giây, số giá trị đọc trung bình khoảng 50 fields/giây, chưa tính metadata/query/remote overhead. Đây là estimate thô, không phải method-call count chính xác. Measure thực tế để chọn interval/filter và theo dõi heap/GC.

## 20. Security: tree query có thể đọc rất rộng

Một single attribute adapter chỉ nhắm một field; tree-polling với `query-name="*:*"` có thể truy vấn nhiều MBeans của JVM và converter có thể đụng attributes nhạy cảm.

### 20.1. Các lớp bảo vệ

- **JMX identity/authorization:** remote principal chỉ có quyền read cần thiết, không cấp invoke/write bừa bãi.
- **Query scope:** cố định allowlisted domain/type/tenant, không ghép ObjectName từ input không tin cậy.
- **Attribute allowlist:** dùng `NamedFieldsMBeanAttributeFilter` ở converter, trước khi đưa dữ liệu sang Spring flow.
- **Payload schema:** normalize fields, không gửi raw unknown graph sang Internet hoặc logs.
- **Transport:** TLS, authentication, hostname/certificate verification, firewall/management network.
- **Capacity:** giới hạn số MBeans, attribute count, graph size và tốc độ poll.
- **Audit:** ghi query scope, connection identity, error type; tránh log credentials.

### 20.2. Vì sao converter filter không thay JMX ACL?

Filter ngăn ứng dụng đọc/truyền field không cần, nhưng remote credentials có thể vẫn có quyền đối với MBeans khác. Nếu credentials bị lộ, attacker có thể bỏ qua app filter và dùng JMX client riêng. Phải thực thi least privilege tại server/connector.

### 20.3. Test field nhạy cảm giả

`QueueStats.getCredentialHint()` cố ý trả giá trị dạng `SAMPLE-NOT-A-SECRET-*`; allowlist `Depth`/`Healthy` phải loại nó. Dùng synthetic sentinel thay secret thật để kiểm converter/serializer, và bảo đảm downstream log/JSON không chứa sentinel. Test không thay security review của remote JMX permissions.

### 20.4. Đừng expose arbitrary query API

Nếu người dùng HTTP có thể gửi thẳng `query-name="*:*"`, một endpoint giám sát có thể trở thành công cụ đọc toàn JVM. Chỉ chấp nhận truy vấn đã allowlist/được ứng dụng định nghĩa; kiểm soát ObjectName.quote/escaping cho key property values.

## 21. Observability và snapshot quality

| Metric/field đề xuất | Vai trò |
| --- | --- |
| `jmx_tree_poll_attempts_total` | Số lần poll thử. |
| `jmx_tree_poll_success_total` | Số snapshot thành công. |
| `jmx_tree_poll_errors_total{kind}` | Phân loại IO, MBean disappear, schema, security. |
| `jmx_tree_poll_duration_seconds` | Thời gian JMX query + convert. |
| `jmx_tree_last_success_epoch_seconds` | Đánh dấu nguồn stale. |
| `jmx_tree_matched_mbeans` | Số MBeans matched trong successful snapshot. |
| `jmx_tree_snapshot_size_bytes` | Kích thước data sau serialization. |
| `jmx_tree_normalization_errors_total` | Graph không phù hợp DTO contract. |
| `jmx_tree_remote_connection_up` | Trạng thái remote connector. |
| `jmx_tree_downstream_latency_seconds` | Thời gian handler xử lý. |
| `jmx_tree_outbox_pending_count` | Snapshot/event durable chưa được relay. |
| `jmx_tree_dropped_total{reason}` | Snapshot bị drop theo policy. |

Đây là **gợi ý metric names**, không phải tên Spring Integration tự phát tất cả theo mặc định. Không gắn từng ObjectName hoặc snapshot timestamp làm high-cardinality metric labels; dùng structured logs/traces có quyền truy cập phù hợp.

### 21.1. Trace bình thường và lỗi

~~~text
03:00:00 TREE_POLL_TRIGGERED
03:00:00 JMX_QUERY_OK matched=3
03:00:00 CONVERT_OK allowedFields=Depth,Healthy
03:00:00 SPRING_CHANNEL_DISPATCHED
03:00:00 DASHBOARD_SNAPSHOT_UPDATED
~~~

~~~text
03:00:05 TREE_POLL_TRIGGERED
03:00:10 JMX_QUERY_FAILED kind=IOException
03:00:10 SOURCE_STALE
03:00:10 LAST_KNOWN_VALUES_RETAINED, quality=STALE
~~~

Không tự thay một failed poll bằng graph rỗng hoặc Depth=0 rồi báo các queues đã biến mất. Source quality cần được theo dõi tách biệt.

### 21.2. Readiness không chỉ là endpoint RUNNING

Một polling endpoint có thể RUNNING dù connection bị đứt. Kiểm `lastSuccessfulSnapshotAt`, query scope, matched-count trend, converter errors và downstream backlog. Chọn alert khi quá số chu kỳ liên tiếp không có snapshot hợp lệ theo SLA.

## 22. Troubleshooting thường gặp

| Triệu chứng | Kiểm gì? | Hướng xử lý |
| --- | --- | --- |
| Tree snapshot không đến channel | Poller/endpoint running? Có consumer? | Xem configuration/XML và error path. |
| Không MBean nào được match | Sai `query-name` hoặc MBeanServer. | Gọi `queryNames(pattern,null)` tại đúng server. |
| Lấy một message thay vì ba | Tree source trả graph chứa nhiều MBeans. | Đây có thể là đúng; normalize + split nếu cần. |
| Converter đọc quá nhiều fields | Thiếu allowlist. | `NamedFieldsMBeanAttributeFilter`. |
| Không có field Depth | Attribute name sai case hoặc filter nhận `getDepth`. | Xem `MBeanInfo`, dùng `Depth`. |
| JSON không như ví dụ | Graph root/keys khác assumed DTO. | Viết explicit mapper với fixtures version. |
| Empty graph ngay sau startup | MBeans chưa register. | Kiểm `MBeanExporter` lifecycle. |
| MBean động lúc có lúc không | Race register/unregister khi query. | Snapshot quality/retry/thời gian lấy mẫu. |
| Converter timeout | Getter nặng, remote latency. | Narrow query, filter, split source groups. |
| `CompositeData` lỗi cast | OpenType khác Java primitive. | Convert với schema/API đúng. |
| Graph có field giả nhạy cảm | Filter sai hoặc endpoint khác bypass filter. | Test whitelist, output redaction/ACL. |
| Graph quá lớn làm heap tăng | Wildcard quá rộng, giữ nhiều snapshots RAM. | Query bounds, bounded buffers và retention. |
| Remote JMX connection lost | TLS/RMI hostname/ports/firewall. | Check connector + reconnect/backoff. |
| CI báo ObjectName đã đăng ký | Contexts dùng chung platform server. | Unique test ObjectNames/cleanup/serial tests. |
| Lỗi import Java | Dùng package 6.x khi dependency 7.x. | Đổi `jmx` sang `jmx.inbound` tương ứng. |
| Alert gửi lặp | Cùng tree state qua nhiều polls. | Stateful transition/hysteresis/cooldown. |
| Missed short spike | Tree poll không phải event listener. | JMX notification hoặc event source bền. |

### 22.1. Debug từ JMX trước Spring Integration

~~~java
ObjectName pattern = new ObjectName(
        "demo.integration:type=QueueStats,name=*");

var names = mbeanServer.queryNames(pattern, null);
System.out.println("Matched MBeans = " + names.size());
~~~

Nếu matched-count bằng 0, sửa MBean registration/namespace trước khi debug converter. Nếu query thành công nhưng Spring channel không nhận, kiểm source, @Poller, error logs, output channel và flow. Nếu channel nhận nhưng DB/Kafka chưa có dữ liệu, kiểm downstream transform/serializer/transaction.

## 23. Anti-patterns và cách thay

| Anti-pattern | Lý do sai | Cách sửa |
| --- | --- | --- |
| `query-name="*:*"` rồi filter secret ở downstream. | Đọc quá rộng và secret đã vào memory. | Query hẹp + converter allowlist/JMX ACL. |
| `max-messages-per-poll=5` là năm MBeans. | Một receive có thể quét toàn tree. | Thường 1 nhận một graph snapshot. |
| Tree payload mặc định là `QueueTreeSnapshot`. | Native source trả converter graph. | Mapper DTO có contract/fixtures. |
| Graph rỗng luôn nghĩa queue bị xóa. | Poll/query có thể fail. | Quality/error metadata trước inventory decisions. |
| Gửi alert mỗi poll vượt ngưỡng. | Sampling tạo nhiều snapshots cùng state. | Hysteresis/transition filter. |
| Coi graph là atomic snapshot. | MBeans/attributes đọc vào thời điểm khác nhau. | Versioned/atomic state API ở nguồn nếu cần. |
| Tăng poll speed để bảo đảm bắt mọi changes. | Transition ngắn vẫn có thể bị miss. | Notification/event history. |
| Gửi raw graph sang Kafka/HTTP. | Dễ lộ fields, schema/serialization không ổn định. | DTO versioned, allowlist/redaction. |
| Không đóng remote JMXConnector. | Leak socket/threads. | Lifecycle-managed close. |
| Coi `ExecutorChannel` là durable queue. | RAM messages mất khi crash. | Durable inbox/outbox. |
| Dùng ObjectName làm global key đa JVM. | Trùng tên giữa nodes. | Source node ID + ObjectName. |
| Retry vĩnh viễn khi permission denied. | Không sửa được lỗi config và tạo tải. | Alert/fix auth, bounded retry. |

## 24. Bài tập: giám sát nhiều queue bằng JMX tree

**Bối cảnh:** có năm JVMs, mỗi JVM expose nhiều `QueueStats` MBeans. Một Spring Integration service thu snapshot mỗi 10 giây để hiển thị dashboard, cảnh báo overload và đưa aggregated snapshot sang HTTP/Kafka.

### 24.1. Các việc cần làm

1. Tạo `QueueStatsMBean` với `Depth`, `Healthy`, field nhạy cảm **giả** `CredentialHint`.
2. Export ba MBeans `Orders`, `Billing`, `Notifications` dưới cùng domain/type.
3. Dùng `queryNames(new ObjectName("demo.integration:type=QueueStats,name=*"),null)` xác minh pattern.
4. Cấu hình XML native `tree-polling-channel-adapter` với `query-name`, poller 10 giây và `max-messages-per-poll=1`.
5. Cấu hình Java native `MBeanTreePollingMessageSource` với converter/allowlist.
6. Đưa graph qua `MessageChannel` tới IntegrationFlow.
7. Quan sát một payload thật trên version đang dùng; viết mapper thành DTO có sourceNode/observedAt/schemaVersion/queues.
8. Assert DTO không chứa `CredentialHint`, chỉ có `Depth`/`Healthy`.
9. Test tên MBean mới được register xuất hiện trong successful snapshot sau; unregister tương ứng.
10. Test mismatch attribute schema, getter lỗi và remote disconnected; dùng STALE/UNKNOWN thay vì Depth=0.
11. Dùng MBeanServer nội JVM và JUnit test `queryNames`, filter, `receive()`, scheduled flow.
12. Kiểm isolation của nhiều test contexts trên platform MBeanServer.
13. Mô phỏng remote latency > poll interval; đo backlog/latency.
14. Đo số MBeans, allowed attribute counts và serialized graph size.
15. Xây stateful severity/hysteresis để tránh gửi alert mỗi snapshot.
16. Chuyển output sang JSON DTO và gửi HTTP/Kafka qua outbox nếu cần durability.
17. Test relay timeout/crash và consumer idempotency.
18. Bảo vệ remote JMX bằng TLS, authentication, read-only roles và firewall.
19. Tạo dashboard poll successes/failures, last success age và snapshot quality.
20. Giải thích vì sao tree polling không bảo đảm thu mọi transition ngắn hoặc có atomic state chéo MBeans.

**Tiêu chí đạt:** có native tree polling source, converter allowlist, một graph message mỗi source receive, JUnit JMX+Spring flow, schema normalization, error/staleness policy, security và giới hạn delivery được mô tả rõ.

## 25. Câu hỏi tự kiểm tra

1. JMX tree-polling thuộc inbound hay outbound?
2. Tree-polling khác attribute-polling ở đâu?
3. `query-name` chọn MBeans hay chọn attributes?
4. `MBeanAttributeFilter` có vai trò nào?
5. `NamedFieldsMBeanAttributeFilter` khác `NotNamedFieldsMBeanAttributeFilter` ở đâu?
6. Vì sao allowlist giảm rủi ro hơn blocklist?
7. `MBeanTreePollingMessageSource` nhận converter qua API nào?
8. `setServer(...)` nhận kiểu JMX nào?
9. `setQueryName(...)` khác `setObjectName(...)` của attribute source?
10. Một poll có thể chứa mấy MBeans và phát mấy Spring messages?
11. `max-messages-per-poll=1` có giới hạn số MBeans không?
12. Tại sao snapshot không atomic giữa nhiều MBeans?
13. Converter dùng `Map`/`List`/array có nghĩa JSON schema tự động cố định không?
14. Vì sao nên có `observedAt` và `sourceNode` do app định nghĩa?
15. MBean vừa biến mất khỏi tree có chắc đã bị xóa không?
16. Nếu remote query lỗi có nên xuất graph rỗng làm inventory không?
17. Một spike nhỏ hơn poll interval có chắc được quan sát không?
18. Tại sao attribute filter ở source tốt hơn chỉ xóa field sau JSON serialization?
19. Spring Integration 7.x thay package inbound JMX ra sao?
20. Unit test `queryNames` chứng minh được gì?
21. Native source test `receive()` khác scheduled flow test ra sao?
22. Vì sao platform MBeanServer gây collision khi test song song?
23. DirectChannel + HTTP handler chậm ảnh hưởng poller thế nào?
24. ExecutorChannel có tự lưu messages qua restart không?
25. JMX remote cần bảo mật những lớp nào?
26. ObjectName giữa hai JVM có đủ làm business identity không?
27. Poller RUNNING có nghĩa dữ liệu chắc mới không?
28. Tại sao Kafka downstream không thể tái tạo một spike mà source chưa poll?
29. Khi nào chọn notification-listening thay tree-polling?
30. Những metrics nào giúp phân biệt successful empty snapshot và failed poll?

**Gợi ý:** nhớ bốn ranh giới **JMX query → converter/filter → Spring poller/MessageChannel → business DTO/downstream**. Snapshot là **quan sát trạng thái**, không phải danh sách đầy đủ events kể từ lần trước.

## 26. Kết luận và tài liệu tham khảo

**JMX tree-polling adapter** của Spring Integration truy vấn nhóm MBeans theo `query-name`, dùng converter để xây object graph rồi gửi Spring Message theo poller:

- XML native `int-jmx:tree-polling-channel-adapter` hoặc Java native `MBeanTreePollingMessageSource`.
- `DefaultMBeanObjectConverter` và `NamedFieldsMBeanAttributeFilter` giúp giới hạn thuộc tính ở nguồn.
- `max-messages-per-poll` khống chế số `receive()` trong một poll task, không phải số MBeans trong tree.
- Object graph thích hợp chuẩn hóa/serialize JSON nhưng cần schema, source identity, timestamp và validation ứng dụng.
- Polling có thể miss transitions; graph không atomic chéo MBeans, JMX không mặc định có durable ACK/replay.
- Query scope, filter, remote TLS/auth, resource bounds, error handling và stale-source metrics giúp tránh giám sát sai.
- Khi downstream cần độ bền, dùng inbox/outbox và idempotent consumer; khi cần không bỏ lỡ events, chọn JMX notification hoặc event source có history.

Trong **SPRING_INTEGRATION_ADAPTERS**, luồng **JMX tree → MessageChannel → IntegrationFlow → DB/HTTP/JMS/AMQP/Kafka/file/SFTP** là một cách dùng chung hợp đồng message và pipeline tích hợp cho dữ liệu quản trị JVM. Sự phân biệt giữa **snapshot sampling**, **delivery** và **business commit** là điều kiện để hệ thống báo trạng thái trung thực.

### 26.1. Nguồn chính thức đối chiếu API

- [Spring Integration JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): native tree adapter, `query-name`, converter và filters.
- [Javadoc Spring Integration 6.x MBeanTreePollingMessageSource](https://www.springframework.org/spring-integration/docs/6.4.0-M2/api/org/springframework/integration/jmx/MBeanTreePollingMessageSource.html): constructor/source methods.
- [Spring Integration 6.x MBeanObjectConverter](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jmx/MBeanObjectConverter.html): converter interface.
- [Spring Integration 7.x JMX inbound package](https://docs.spring.io/spring-integration/api/org/springframework/integration/jmx/inbound/package-summary.html): package migration.
- [Java 17 JMX APIs](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html): MBeanServerConnection/ObjectName/QueryExp/MBeanInfo.

**Phạm vi STEP 4:** bài viết tập trung tạo Knowledge chi tiết và ví dụ để học. Khi áp dụng vào dự án thật, phải đối chiếu dependency versions và chạy tests phù hợp. Vòng Content QA/refactor chuyên môn sẽ được thực hiện ở **STEP 6**, không phải một phần của lần ghi bài STEP 4 này.





