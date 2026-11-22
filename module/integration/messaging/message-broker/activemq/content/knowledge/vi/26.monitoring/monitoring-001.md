# Classic Web Console, JMX và chỉ số của từng destination

> **Chương:** Giám sát  
> **Phạm vi:** **Apache ActiveMQ Classic** (ví dụ 6.x) với Web Console, Java Management Extensions (JMX) và chỉ số cho từng queue/topic. Bài nhấn mạnh cách quan sát **backlog, in-flight, tốc độ enqueue/dequeue, consumer và giới hạn tài nguyên**, không lặp kiến thức gửi/nhận JMS cơ bản. Đoạn mã thực hành sử dụng Java 17 và broker lab; Artemis có management console/MBean khác, **không** áp nguyên tên ObjectName của Classic sang Artemis.

## 1. Một destination có nhiều trạng thái hơn “còn bao nhiêu message?”

Giả sử queue `orders.fulfillment` nhận đều 200 sự kiện/giây. Khi dashboard báo `QueueSize=5.000`, cần phân biệt:

- Message **đang chờ** consumer nhận;
- Message đã **dispatch/in-flight** tới consumer nhưng chưa được ACK;
- Message đã ACK rồi, được chuyển vào DLQ/expiry hoặc bị các policy khác xử lý;
- Các bộ đếm lịch sử tăng/giảm kể từ thời điểm broker khởi động hoặc reset statistics.

```text
Producer                    ActiveMQ Classic                    Consumer
   │                              │                                │
   ├── SEND ─────────────────────▶ │ EnqueueCount ↑                 │
   │                              │ QueueSize ↑                    │
   │                              ├──────── dispatch ────────────▶│
   │                              │ DispatchCount ↑                │
   │                              │ InFlightCount ↑                │
   │                              │                                │
   │                              │◀──────── ACK/commit ──────────┤
   │                              │ DequeueCount ↑                 │
   │                              │ InFlightCount ↓                │
   │                              │ QueueSize ↓                    │
```

Ba câu hỏi quan trọng khi trực ca:

1. **Backlog còn tăng không?** So tốc độ `EnqueueCount` và `DequeueCount` trên **cùng destination** trong một khoảng thời gian.
2. **Consumer không chạy hay đang giữ message?** Xem `ConsumerCount` kết hợp `InFlightCount`, `DispatchCount` và dấu vết xử lý trong ứng dụng.
3. **Có nghẽn tài nguyên hay message hết hạn không?** Xem `MemoryPercentUsage` của destination, `StorePercentUsage` của broker, `ExpiredCount` và log/policy.

**Không dùng một số đo `QueueSize` làm bằng chứng mất message hoặc hoàn thành nghiệp vụ.** ActiveMQ Classic đếm số message trong queue/store **chưa được acknowledge**; vì vậy phần in-flight chưa ACK cũng có thể nằm trong `QueueSize`. <https://activemq.apache.org/components/classic/documentation/how-do-i-find-the-size-of-a-queue>

## 2. Classic Web Console: quan sát nhanh, nhưng có quyền thay đổi dữ liệu

Trong bản phân phối Classic có tích hợp Web Console, URL thường là:

```text
http://127.0.0.1:8161/admin
```

Port, context path và việc Jetty/web application có được bật hay không phụ thuộc file cấu hình/đóng gói đang chạy. Nếu URL không truy cập được, **đừng mặc định broker JMS đã chết**: listener OpenWire (thường cổng `61616`) và HTTP console (thường `8161`) là **hai thành phần khác nhau**.

### 2.1. Các màn hình cần biết

| Màn hình | Đọc được gì? | Câu hỏi vận hành |
|---|---|---|
| **Home** | Trạng thái broker, memory/store/temp usage | Broker có đang tiến sát giới hạn không? |
| **Queues** | Tên queue, số message, consumer, enqueue/dequeue, thao tác Browse | Destination nào đang tồn backlog? |
| **Topics** | Topic đang có hoạt động | Có publisher/subscriber đúng tên không? |
| **Subscribers** | Thông tin subscription, kể cả durable subscription tùy bản | Durable subscription nào bị bỏ lại phía sau? |
| **Connections** | Client đang kết nối qua transport | Consumer có thực sự còn connection? |
| **Scheduled** | Message được hẹn lịch nếu scheduler có hiệu lực | Message chưa giao vì lịch hẹn hay vì thiếu consumer? |
| **Send** | Gửi message test | **Thao tác ghi**, không phải thao tác monitoring thuần |

Giao diện và cột có thể thay đổi giữa các phiên bản Classic/Jetty, nhưng các câu hỏi chẩn đoán vẫn giữ nguyên. Hãy xem tên destination, broker instance và timestamp trước khi kết luận.

### 2.2. Quy trình đọc Console an toàn

1. Xác nhận bạn đang mở **đúng broker** (tên instance/host, environment, URL), không nhầm staging với production.
2. Mở **Queues**, chọn queue cần quan sát, ghi `QueueSize`, `ConsumerCount`, tổng enqueue/dequeue và thời điểm.
3. Mở **Connections** để kiểm tra consumer thực sự đã kết nối, không chỉ có process đang chạy.
4. Nếu cần đối chiếu message cụ thể, dùng **Browse** với quyền hạn phù hợp và phạm vi nhỏ. Cẩn thận: body/properties có thể chứa PII hoặc dữ liệu nhạy cảm.
5. Lặp lại số đo sau một khoảng thời gian để xem xu hướng, không xử lý dựa vào snapshot đơn.

**Phân biệt rõ thao tác đọc/ghi:**

| Thao tác | Tác động |
|---|---|
| Xem danh sách queue/topic, xem metrics | Chủ yếu đọc |
| Browse message | Không ACK message, nhưng có thể tốn tài nguyên hoặc lộ nội dung |
| Send | Tạo message mới |
| Delete/Remove/Purge | **Làm mất message đang chờ**, không phải “làm mới số liệu” |
| Move/Retry từ DLQ | Thay đổi routing và có thể gây side effect lặp |
| Reset Statistics qua JMX | Không nhất thiết xóa message, nhưng **xóa cơ sở so sánh counter** |

**Không bấm `Purge` trong production để giảm báo động backlog.** Phải có playbook, phê duyệt, lưu manifest/event ID và đánh giá nhu cầu replay. Khi console chỉ để quan sát, dùng tài khoản có quyền đọc hạn chế; không dùng tài khoản quản trị đầy đủ cho dashboard thường trực.

### 2.3. Bật JMX cho broker nhưng không mở remote management bừa bãi

Classic dùng thuộc tính `useJmx` trên `<broker>`; tài liệu Apache cho biết JMX được bật theo mặc định ở nhiều cấu hình Classic. Mảnh ghép bên dưới minh họa **giá trị cần kiểm tra trong `conf/activemq.xml` hiện có**, không thay toàn bộ file:

```xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-monitor-lab"
        useJmx="true">
    <managementContext>
        <managementContext createConnector="false"/>
    </managementContext>
    <!-- Giữ nguyên persistenceAdapter, destinationPolicy, transportConnectors... -->
</broker>
```

`createConnector="false"` cho phép sử dụng MBeanServer trong JVM mà **không tự mở JMX connector riêng** qua mạng. Đây là lựa chọn an toàn để bắt đầu khi dùng `jconsole` ở cùng máy/JVM. Nếu dự án đã cấu hình `managementContext`, hãy **sửa phần tử đang có**, không tạo hai bản cùng chức năng.

**Khi Console không chạy:** kiểm tra cấu hình Jetty/webapps của **chính bản phân phối**, log khởi động, port 8161 và authentication của web app. Một số bản Classic tích hợp Web Console qua `conf/jetty.xml`; không sửa Jetty chỉ để làm cho JMS broker hoạt động.

## 3. JMX: tên MBean của broker và từng destination

JMX là giao diện quản trị/đo đạc trong JVM. Classic đăng ký MBeans dưới domain thường là `org.apache.activemq`. Nên phân biệt:

```text
org.apache.activemq:
  type=Broker,
  brokerName=classic-monitor-lab
      ├── Broker MBean          : tổng số kết nối, memory/store/temp usage
      ├── Queue destination     : QueueSize, Enqueue/Dequeue/InFlight...
      ├── Topic destination     : Enqueue/Dispatch/Consumer...
      ├── Connection/Consumer   : client, subscription, slow-consumer state
      └── PersistenceAdapter    : thông tin store
```

### 3.1. ObjectName theo destination

Ví dụ cho queue `orders.fulfillment` thuộc broker `classic-monitor-lab`:

```text
org.apache.activemq:type=Broker,brokerName=classic-monitor-lab,destinationType=Queue,destinationName=orders.fulfillment
```

Ví dụ cho topic `events.orders`:

```text
org.apache.activemq:type=Broker,brokerName=classic-monitor-lab,destinationType=Topic,destinationName=events.orders
```

Broker-level MBean:

```text
org.apache.activemq:type=Broker,brokerName=classic-monitor-lab
```

**Tên phải khớp broker đang chạy.** `brokerName` không nhất thiết bằng hostname hoặc tên service Kubernetes. Destination name có dấu phẩy, dấu hai chấm hoặc wildcard cần được xử lý theo cú pháp `javax.management.ObjectName`; đừng nối chuỗi tùy ý với tên lấy từ HTTP input.

Trong `jconsole`: kết nối **local** tới broker JVM → tab **MBeans** → domain `org.apache.activemq` → `type=Broker` → chọn `brokerName` → `destinationType=Queue` hoặc `Topic` → **Attributes** để đọc thuộc tính. Cây thực tế có thể nhóm theo thứ tự khác, nhưng ObjectName là nguồn tra cứu đáng tin cậy.

### 3.2. Remote JMX cần bảo vệ riêng

**Không bật** `createConnector="true"` rồi expose cổng `1099` ra Internet để tiện scrape. JMX/RMI có thể dùng **registry port và RMI server port riêng**, chịu nguy cơ truy cập quản trị và giải tuần tự dữ liệu.

Khi bắt buộc dùng remote JMX:

- Bảo vệ bằng **authentication và TLS**, ràng buộc role đọc/ghi, cấu hình JDK serialization filter thích hợp.
- Cố định host/port của registry **và** RMI server theo topology/firewall; không chỉ mở một port rồi đoán kết nối thành công.
- Ưu tiên kết nối qua mạng quản trị riêng, bastion/SSH tunnel/VPN; không công bố trên Internet.
- Kiểm tra rằng `jconsole`/monitoring client được cấp **read-only**, không có quyền invoke `purge`, `stop` hoặc `terminateJVM`.
- Phân biệt tài khoản **Web Console**, tài khoản **broker JMS** và tài khoản **JMX connector**; cấu hình một hệ không tự bảo vệ hệ khác.

Khi JMX remote chưa được setup an toàn, hãy dùng Console nội bộ, JConsole/JMX local hoặc một exporter được triển khai bởi đội vận hành theo chính sách bảo mật hiện hành.

## 4. Bảng chỉ số cần hiểu ở cấp destination

Các tên dưới đây là thuộc tính trên `DestinationViewMBean` (đặc biệt hữu ích cho **queue**) của ActiveMQ Classic.

| Attribute | Đơn vị | Ý nghĩa | Lưu ý khi diễn giải |
|---|---:|---|---|
| `QueueSize` | Message | Số message còn ở queue/store, **chưa ACK** | **Có thể gồm in-flight**; không phải chỉ phần ready |
| `EnqueueCount` | Lượt | Số message được đưa vào destination trong kỳ counter | Có thể reset khi broker restart hoặc reset statistics |
| `DequeueCount` | Lượt | Số message được ACK/loại khỏi destination trong kỳ | Không phải số business transactions thành công |
| `DispatchCount` | Lượt | Số lần broker dispatch message cho consumer | Một message redelivery có thể tạo **nhiều lần dispatch** |
| `InFlightCount` | Message | Đã dispatch nhưng chưa nhận ACK | Tăng khi consumer giữ message/transaction lâu |
| `ExpiredCount` | Lượt | Message hết TTL đã được xử lý như expired | Có thể tăng dù consumer không nhận |
| `ConsumerCount` | Consumer | Số consumer đang gắn với destination | `>0` không chứng minh consumer xử lý nhanh |
| `ProducerCount` | Producer | Số producer hiện gắn với destination | Không thay thế enqueue rate |
| `MemoryPercentUsage` | % | Phần trăm giới hạn memory usage của destination | 100% có thể kích hoạt flow control; phải xem policy |
| `BlockedSends` | Lượt | Số lần send bị block do tài nguyên theo thống kê destination | Cần kết hợp memory/store pressure và producer latency |
| `AverageEnqueueTime` | Thời gian | Thời gian trung bình message đã ở destination theo thống kê provider | Không phải end-to-end latency của nghiệp vụ |

**Đối với Topic:** các chỉ số enqueue/dispatch/consumer hữu ích, nhưng **`QueueSize` là khái niệm của Queue**; một topic với nhiều subscription không được đánh giá bằng một QueueSize tổng quát rồi suy ra mọi subscriber không tồn backlog. Phải tìm **subscription MBeans**/durable subscription tương ứng và kiểm tra từng nhóm nếu dữ liệu cần giữ khi offline.

### 4.1. Bộ đếm thời kỳ khác số đo trạng thái

Có hai kiểu dữ liệu:

**Gauge (trạng thái tại thời điểm đọc):** `QueueSize`, `InFlightCount`, `ConsumerCount`, `MemoryPercentUsage`.

**Counter (tích lũy trong một kỳ):** `EnqueueCount`, `DequeueCount`, `DispatchCount`, `ExpiredCount`, `BlockedSends`.

Nếu broker restart hoặc operator gọi `resetStatistics`, counter có thể quay về 0. Một exporter không được coi chênh lệch âm là tốc độ âm thật.

### 4.2. Những công thức thường gây sai

- **Không:** `backlog = EnqueueCount - DequeueCount`. Hai counter có kỳ đo, còn QueueSize có thể phản ánh dữ liệu tồn qua restart.
- **Không:** `outstanding = QueueSize + InFlightCount`. Message in-flight chưa ACK có thể **đã nằm trong QueueSize**, cộng thêm là đếm hai lần.
- **Không:** `tốc độ xử lý nghiệp vụ = DispatchCount/giây`. Dispatch có thể lặp vì rollback/redelivery.
- **Không:** `QueueSize=0 ⇒ event đã xử lý thành công`. Nó có thể expired, DLQ, bị purge hoặc được consumer ACK trước khi side effect bên ngoài hoàn tất.

Có thể dùng `QueueSize - InFlightCount` làm **ước lượng nhanh phần chưa dispatch** trên queue đang ổn định, nhưng không coi đó là số chính xác tuyệt đối khi có scheduled messages, cursor, selector, transaction và số đo không đồng thời.

## 5. Tính tốc độ vào/ra từ hai snapshot JMX

Lấy hai mẫu `S1` và `S2` cho **cùng broker/destination**, cách nhau `Δt` giây:

\[
\text{enqueueRate} = \frac{\text{EnqueueCount}_{S2}-\text{EnqueueCount}_{S1}}{\Delta t}
\]

\[
\text{dequeueRate} = \frac{\text{DequeueCount}_{S2}-\text{DequeueCount}_{S1}}{\Delta t}
\]

Chỉ áp dụng khi `S2 ≥ S1` cho counter được so sánh và broker **không restart/reset** giữa hai mẫu. Ví dụ minh họa:

| Thời điểm | QueueSize | EnqueueCount | DequeueCount | ConsumerCount |
|---|---:|---:|---:|---:|
| T0 | 1.200 | 8.000 | 6.800 | 3 |
| T0 + 60 giây | 1.800 | 8.900 | 7.100 | 3 |

Trong 60 giây này, `enqueueRate = 900/60 = 15 msg/s`, `dequeueRate = 300/60 = 5 msg/s`; backlog tăng 600 message. **Đây là dữ liệu minh họa**, không phải một kết quả thực đo. Nguyên nhân có thể là consumer không theo kịp; cần xem `InFlightCount`, p95 xử lý và store usage trước khi tăng số consumer.

**Không lấy số tổng broker để thay số từng queue.** Broker-level `TotalEnqueueCount`/`TotalDequeueCount` cộng nhiều destination, có thể che một queue quan trọng đang nghẽn trong khi phần còn lại vẫn nhanh.

### 5.1. Nhận diện cảnh báo phù hợp thay vì chỉ báo QueueSize lớn

| Dấu hiệu kết hợp | Giả thuyết ưu tiên | Bằng chứng cần thêm |
|---|---|---|
| QueueSize tăng liên tục, enqueueRate > dequeueRate | Consumer theo không kịp hoặc thiếu consumer | ConsumerCount, latency xử lý, thread pool, DB downstream |
| QueueSize tăng, ConsumerCount = 0 | Worker dừng, mất connection hoặc không đăng ký queue | Connection MBeans, app logs, readiness |
| InFlightCount cao và DequeueCount gần như không tăng | Consumer giữ message/không ACK, transaction dài | App listener logs, prefetch, transaction time |
| DispatchCount tăng mạnh nhưng DequeueCount ít | Redelivery hoặc consumer không hoàn tất ACK | Redelivery policy, DLQ count, lỗi listener |
| ExpiredCount tăng | TTL quá ngắn so với backlog hoặc producer đặt hạn không phù hợp | JMSExpiration, age in queue, consumer latency |
| BlockedSends và MemoryPercentUsage cao | Broker đang hãm producer do flow control | Destination policy, `systemUsage`, StorePercentUsage |
| QueueSize thấp nhưng SLA vẫn trễ | Lag trong DB/API hoặc một subscription khác | Business tracing, các destination phụ thuộc, Topic subscribers |

Không đặt ngưỡng “queue nào >100 là lỗi” cho mọi hệ thống. Một queue batch có backlog lớn theo lịch có thể bình thường; một queue thanh toán gần thời gian thực có vài trăm message đã là nghiêm trọng. Kết hợp **tốc độ tăng backlog, độ tuổi oldest message (nếu đo được), thời gian xử lý và SLA**.

## 6. Java 17: đọc JMX theo destination và tính tốc độ an toàn

Chương trình dùng **JMX chuẩn có sẵn trong JDK** (`javax.management`) nên **không cần ActiveMQ client jar** để đọc metrics. Đây là namespace JMX của Java SE, **không liên quan** việc JMS hiện đại dùng `jakarta.jms`.

Giả định đội vận hành đã chuẩn bị một **JMX endpoint được bảo vệ bằng xác thực và kết nối an toàn** qua mạng quản trị. Chương trình **chỉ đọc attributes**, không gọi bất kỳ operation nào.

### 6.1. `ClassicDestinationJmxProbe.java`

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

public final class ClassicDestinationJmxProbe {
    private record Sample(long nanos,
                          long queueSize,
                          long enqueued,
                          long dequeued,
                          long dispatched,
                          long inFlight,
                          long expired,
                          long consumers,
                          long memoryPercent) {}

    private static String env(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return value;
    }

    private static long number(MBeanServerConnection server,
                               ObjectName object,
                               String attribute) throws Exception {
        Object value = server.getAttribute(object, attribute);
        if (!(value instanceof Number n)) {
            throw new IllegalStateException(
                attribute + " is not numeric on " + object);
        }
        return n.longValue();
    }

    private static Sample read(MBeanServerConnection server,
                               ObjectName queue) throws Exception {
        long at = System.nanoTime();
        return new Sample(
            at,
            number(server, queue, "QueueSize"),
            number(server, queue, "EnqueueCount"),
            number(server, queue, "DequeueCount"),
            number(server, queue, "DispatchCount"),
            number(server, queue, "InFlightCount"),
            number(server, queue, "ExpiredCount"),
            number(server, queue, "ConsumerCount"),
            number(server, queue, "MemoryPercentUsage")
        );
    }

    private static ObjectName queueMBean(MBeanServerConnection server,
                                         String broker,
                                         String destination) throws Exception {
        // Dùng ObjectName pattern để tìm MBean đang được broker export:
        // không nối input tùy ý vào cú pháp ObjectName.
        ObjectName pattern = new ObjectName(
            "org.apache.activemq:type=Broker,brokerName=*,"
          + "destinationType=Queue,destinationName=*");
        Set<ObjectName> names = server.queryNames(pattern, null);

        return names.stream()
            .filter(n -> broker.equals(n.getKeyProperty("brokerName")))
            .filter(n -> destination.equals(n.getKeyProperty("destinationName")))
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "Queue MBean not found: " + broker + "/" + destination));
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: ClassicDestinationJmxProbe <brokerName> <queueName>");
        }
        String broker = args[0];
        String destination = args[1];
        // URL phải do admin cung cấp, không tự mở JMX connector không an toàn.
        JMXServiceURL url = new JMXServiceURL(env("JMX_SERVICE_URL"));
        String user = env("JMX_USER");
        String password = env("JMX_PASSWORD");

        // JMXConnector.CREDENTIALS = "jmx.remote.credentials".
        Map<String, ?> credentials = Map.of(
            JMXConnector.CREDENTIALS, new String[] {user, password});

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url, credentials)) {
            MBeanServerConnection server = connector.getMBeanServerConnection();
            ObjectName queue = queueMBean(server, broker, destination);

            Sample before = read(server, queue);
            Thread.sleep(5_000L);
            Sample after = read(server, queue);

            double seconds = (after.nanos - before.nanos) / 1e9;
            long deltaEnqueued = after.enqueued - before.enqueued;
            long deltaDequeued = after.dequeued - before.dequeued;
            if (deltaEnqueued < 0 || deltaDequeued < 0) {
                System.out.println("COUNTER_RESET_OR_RESTART: rates unavailable");
            } else {
                System.out.printf(
                    "enqueueRate=%.1f msg/s dequeueRate=%.1f msg/s%n",
                    deltaEnqueued / seconds, deltaDequeued / seconds);
            }
            System.out.printf(
                "queue=%s size=%d inFlight=%d consumers=%d "
              + "dispatched=%d expired=%d memory=%d%%%n",
                destination, after.queueSize, after.inFlight, after.consumers,
                after.dispatched, after.expired, after.memoryPercent);
        }
    }
}
```

**Ví dụ cách chạy trên môi trường đã có secure JMX endpoint:**

```text
JMX_SERVICE_URL=service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi
JMX_USER=<monitor-user>
JMX_PASSWORD=<secret-from-secure-environment>

java ClassicDestinationJmxProbe classic-monitor-lab lab.monitor.orders
```

Các giá trị trên **chỉ là format minh họa**, không phải endpoint đang tồn tại, cũng **không phải hướng dẫn bật JMX không mã hóa**. RMI URL có thể khác khi dùng TLS/tunnel và cấu hình JMX/JVM của đơn vị vận hành. Không lưu mật khẩu trong source, output hay lịch sử shell. Quản lý secrets ở process/container runtime.

**Điều chương trình bảo đảm:** query MBean đúng broker/queue, chỉ đọc attributes và tính tốc độ khi hai counter không giảm. **Điều chưa bảo đảm:** nếu broker restart rất nhanh giữa hai mẫu và counter vô tình đã tăng lại lớn hơn số cũ, chỉ kiểm tra chênh lệch âm chưa đủ phát hiện restart; production exporter nên theo dõi **broker lifecycle/uptime/connection reset**, gắn nhãn epoch và bỏ mẫu đứt đoạn.

**Các hạn chế khác:** `queryNames` có thể tốn thời gian nếu broker có hàng trăm nghìn dynamic destinations; nên cache ObjectName có kiểm soát và refresh khi broker restart. Một snapshot gọi nhiều `getAttribute` **không nguyên tử tuyệt đối** vì queue vẫn thay đổi trong lúc đọc. Vì vậy không dùng kết quả làm sổ cái tài chính hoặc bằng chứng exactly-once.

## 7. Jolokia: đọc JMX qua HTTP mà không nhầm với JMS REST

Một số bản phân phối Classic cung cấp **Jolokia** ở đường dẫn thường gặp:

```text
http://127.0.0.1:8161/api/jolokia/
```

Đây là REST **management** truy cập MBeans; nó **khác** API gửi/nhận message kiểu `/api/message`. Dù là HTTP, Jolokia có thể thực hiện **management operations**, bao gồm thao tác nguy hiểm nếu quyền quá rộng. Chỉ sử dụng qua mạng nội bộ, xác thực và policy giới hạn operation.

Ví dụ **GET chỉ đọc** cho queue `lab.monitor.orders` trên broker lab:

```bash
# --netrc yêu cầu file thông tin đăng nhập do người vận hành quản lý
# với quyền file chặt; không đặt password trực tiếp lên dòng lệnh.
curl --fail --silent --show-error --netrc \
  -H 'Origin: http://127.0.0.1:8161' \
  'http://127.0.0.1:8161/api/jolokia/read/org.apache.activemq:type=Broker,brokerName=classic-monitor-lab,destinationType=Queue,destinationName=lab.monitor.orders/QueueSize'
```

**Kiểm tra output JSON:** trường `value` là số đo khi response thành công; mã `status` của Jolokia phải là thành công (thường 200). Nếu server trả 401/403 hoặc CORS/Origin policy từ chối, **không tắt authentication/CORS** để làm test xanh: sửa tài khoản, trusted origin hoặc cấu hình proxy được cho phép. Path/context có thể khác giữa phiên bản/distribution.

Khi xây exporter, nên ưu tiên **đọc có kiểm soát**, giới hạn tần suất scrape và loại bỏ payload message khỏi metrics. Đừng tạo metric label với `eventId`, `JMSMessageID` hay giá trị payload: cardinality rất cao và có thể rò rỉ dữ liệu.

## 8. Thực hành queue lab: ba trạng thái quan sát qua Console và JMX

Sử dụng queue **`lab.monitor.orders`**, không phải queue nghiệp vụ. Tạo queue theo provisioning Classic của môi trường lab và đảm bảo broker có `useJmx=true`, Web Console hoạt động, user đủ quyền thao tác trên **chính queue lab**.

### 8.1. Mã gửi một batch 10 message persistent

Dependency cho ứng dụng Classic 6.x/Jakarta JMS (đặt trong Maven project Java 17):

```xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>6.4.0</version>
</dependency>
```

`ClassicMonitoringSeed.java`:

```java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import org.apache.activemq.ActiveMQConnectionFactory;

import java.util.UUID;

public final class ClassicMonitoringSeed {
    private static String env(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + key);
        }
        return value;
    }

    public static void main(String[] args) {
        String runId = "mon-" + UUID.randomUUID();
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(env("BROKER_URL"));

        try (JMSContext tx = factory.createContext(
                env("BROKER_USER"),
                env("BROKER_PASSWORD"),
                JMSContext.SESSION_TRANSACTED)) {
            Queue queue = tx.createQueue("lab.monitor.orders");
            for (int i = 1; i <= 10; i++) {
                tx.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setProperty("runId", runId)
                    .setProperty("seq", i)
                    .send(queue, "ORDER-" + i);
            }
            tx.commit();
            System.out.println("SEED_COMMIT_CONFIRMED runId=" + runId);
        }
    }
}
```

Không chạy hai tiến trình seed/consumer lẫn nhau khi muốn ghi snapshot chính xác. Với code production, thường tái sử dụng producer trong vòng lặp; bài lab giữ mã dễ đọc và chỉ gửi 10 message. `createQueue(...)` là tạo **destination handle phía client**, không bảo đảm queue broker đã được provision trong mọi cấu hình bảo mật.

### 8.2. Đo theo ba mốc

| Mốc thử | Thao tác | Điều nên thấy |
|---|---|---|
| **T0** | Không consumer, queue lab trống | `QueueSize≈0`, `ConsumerCount=0` |
| **T1** | Chạy `ClassicMonitoringSeed`, commit thành công | `QueueSize` tăng khoảng 10; `EnqueueCount` tăng 10 trong kỳ |
| **T2** | Tạo một consumer transacted, nhận 1 message nhưng **chưa commit** | `InFlightCount` tăng; `QueueSize` vẫn tính message chưa ACK |
| **T3** | Consumer commit/ACK 1 message | `DequeueCount` tăng 1; `InFlightCount` giảm; `QueueSize` giảm tương ứng |

Ví dụ consumer transacted giữ đúng một message để quan sát:

```java
try (JMSContext tx = factory.createContext(
        user, password, JMSContext.SESSION_TRANSACTED)) {
    jakarta.jms.Message msg = tx.createConsumer(
        tx.createQueue("lab.monitor.orders")).receive(5_000L);
    if (msg == null) {
        throw new IllegalStateException("Queue lab has no message");
    }

    // Trong terminal lab, tạm dừng xử lý vài giây để chụp JMX InFlightCount.
    Thread.sleep(8_000L);
    tx.commit();
}
```

Đoạn này cần được đặt trong một method có `factory`, `user` và `password` đã khai báo; không phải file Java độc lập. Nếu test trên broker có prefetch và client đã giữ nhiều message, `InFlightCount` có thể **lớn hơn 1** dù Java mới gọi `receive()` một lần; muốn phép thử in-flight sát một message, có thể giảm prefetch của Classic consumer theo client policy hoặc cô lập một message duy nhất.

**Mẫu số liệu là xu hướng, không phải assertion tuyệt đối**. Sau khi stop/restart, bộ đếm thời kỳ có thể reset, nên đối chiếu hiệu số trước/sau trên **cùng vòng đời** của broker. Một lần browse hoặc một màn hình console có thể chụp đúng lúc scheduler/consumer làm thay đổi số liệu.

### 8.3. Phép thử redelivery không tạo business event mới

Cho consumer transacted `receive` một message rồi `rollback()`, quan sát:

- `DispatchCount` có thể tăng khi broker phân phối lại **cùng message**.
- `InFlightCount` tăng/giảm qua các pha.
- `DequeueCount` không tăng chỉ vì đã gọi `receive`.
- `QueueSize` vẫn phản ánh phần chưa ACK, trừ khi message bị expiry/DLQ theo chính sách.

Kết luận: nếu `DispatchCount > EnqueueCount` trong một kỳ đo, điều đó **có thể xảy ra vì redelivery**, không nhất thiết producer gửi trùng. Muốn xác minh trùng nghiệp vụ, đối chiếu `eventId` và consumer ledger chứ không lấy dispatch count làm event count.

## 9. Dashboard, alerts và xử lý sự cố theo destination

Một dashboard tối thiểu cho queue quan trọng nên có:

| Panel | Các chỉ số | Mục tiêu |
|---|---|---|
| Backlog | `QueueSize` và tốc độ tăng 5–15 phút | Phát hiện tồn đọng kéo dài |
| Ingest/Drain | Enqueue/dequeue msg/s | Thấy nhập nhiều hơn xử lý bao nhiêu |
| Delivery/ACK | `DispatchCount` rate, `InFlightCount` | Nhận biết consumer bị kẹt/rollback |
| Consumer health | `ConsumerCount` + lỗi app | Phát hiện queue không có người nhận |
| TTL/errors | `ExpiredCount` rate và DLQ queue size | Phát hiện hết hạn hoặc poison messages |
| Capacity | Destination `MemoryPercentUsage`, broker `StorePercentUsage`/`TempPercentUsage` | Dự báo flow control và dung lượng |
| End-to-end | Latency publish-to-business-commit, oldest event age nếu instrument được | Bảo đảm SLO thật, không chỉ broker khỏe |

**Gợi ý alert có điều kiện** (cần tuning theo baseline):

1. `ConsumerCount=0` liên tục vài phút **trong khi QueueSize tăng**.
2. `enqueueRate > dequeueRate` trong khoảng đủ dài và backlog dự kiến vượt SLO xử lý.
3. `InFlightCount` cao bất thường trong khi `DequeueCount` gần như đứng yên.
4. `ExpiredCount` tăng trong hàng đợi vốn không nên có expired messages.
5. Broker store/temp usage áp sát ngưỡng configured; phát hiện trước khi producer bị block.

Đừng bật cảnh báo bằng một số `QueueSize` nhất thời. Với queue batch hoặc cron, có thể đợi theo cửa sổ vận hành; với queue thời gian thực, ngưỡng nghiêm ngặt hơn. Nếu có HA failover, dashboard phải đổi nguồn scrape sang broker active mới và đánh dấu **đứt quãng/reset counter**.

### 9.1. MBean cardinality và chi phí monitoring

Khi hệ thống tạo nhiều dynamic destination, connection và consumer, việc đăng ký mọi MBean có thể làm tăng overhead. Classic cho phép `suppressMBean` để không đăng ký một số nhóm endpoint, nhưng **nếu suppress quá rộng, dashboard sẽ không tìm thấy MBean cần đọc**.

Ví dụ fragment cấu hình **chỉ sử dụng sau khi đánh giá nhu cầu MBean**:

```xml
<managementContext>
    <managementContext createConnector="false"
        suppressMBean="endpoint=dynamicProducer,endpoint=Consumer,connectionName=*"/>
</managementContext>
```

Fragment thay thế phần tử `managementContext` đang có, không chèn thêm phần tử trùng. Ý nghĩa: tiết kiệm một phần chi phí đăng ký MBean của connection/dynamic producer/consumer; đánh đổi là **không còn đầy đủ dữ liệu từng consumer/connection** để truy vết. Chỉ dùng khi đã bảo đảm các MBean queue/broker vẫn đáp ứng mục tiêu giám sát.

### 9.2. Cây xử lý sự cố ngắn

```text
QueueSize tăng?
  ├── Không: SLO vẫn trễ?  -> kiểm tra business consumer/DB/API và Topic subscribers
  └── Có
       ├── ConsumerCount = 0?
       │    └── kiểm tra connection, listener startup, auth, deployment
       └── ConsumerCount > 0
            ├── InFlightCount cao, Dequeue thấp?
            │    └── kiểm tra transaction, ACK, prefetch, worker hang
            └── InFlightCount thấp
                 ├── enqueue tăng? -> thiếu capacity/consumer hoặc selector
                 └── memory/store cao? -> flow control, disk, paging/store
```

Nếu JMX hoàn toàn không thấy destination:

- Xác minh đúng `brokerName`, domain `org.apache.activemq`, `destinationType` và tên thực; broker có thể chưa tạo destination.
- Kiểm tra `useJmx`, `managementContext`, cấu hình suppress và exporter permissions.
- Kiểm tra lifecycle: failover có thể khiến MBean cũ biến mất; cần query lại broker active.
- Nếu Web Console có queue nhưng JMX remote không truy cập được, phân biệt lỗi **connector/RMI/auth/firewall** với lỗi bản thân broker; **không** tắt bảo mật để kết nối.

## 10. Checklist nghiệm thu

- [ ] Phân biệt Web Console (HTTP/Jetty), JMS transport và JMX; xác minh đang nhìn đúng broker/environment.
- [ ] JMX bật tại broker nhưng remote connector không bị mở công khai; authentication/TLS/role được kiểm soát.
- [ ] Biết ObjectName queue/topic; đọc được `QueueSize`, `EnqueueCount`, `DequeueCount`, `InFlightCount`, `ConsumerCount`.
- [ ] Hiểu `QueueSize` là số chưa ACK **có thể gồm in-flight**, không cộng thêm `InFlightCount` khi báo cáo outstanding.
- [ ] Counter được lấy **hai mốc cùng broker uptime**, rate không âm giả sau restart/reset.
- [ ] Với Topic, kiểm tra **subscription-level backlog**, không dùng queue metric thay cho mọi subscriber.
- [ ] Web Console/Browse/Jolokia chỉ thực hiện thao tác đọc theo quyền; không Purge/Reset/Move ngoài playbook.
- [ ] Đã thử queue lab: seed 10 persistent messages, quan sát in-flight trước commit, đo dequeue sau ACK và phân biệt redelivery với producer duplicate.
- [ ] Dashboard có backlog/rate/in-flight/consumer/expired/capacity, liên hệ với SLO xử lý nghiệp vụ và DLQ.
- [ ] Có quy trình xử lý mất kết nối JMX, suppression và failover mà không suy rằng destination/message biến mất.

**Kết luận:** Web Console giúp điều tra nhanh nhưng đi kèm quyền quản trị nhạy cảm; JMX cho phép đọc **MBean của từng destination** và tính tốc độ theo thời gian. Để giám sát Classic đúng, cần kết hợp **`QueueSize` (chưa ACK), `InFlightCount` (đã dispatch), `EnqueueCount`/`DequeueCount` (bộ đếm kỳ), consumer count và tài nguyên broker**. Những số liệu này mô tả **trạng thái broker**, không thay kiểm chứng business side effect hoặc event ledger.

## Tài liệu chính thức

1. [ActiveMQ Classic — Web Console](https://activemq.apache.org/components/classic/documentation/web-console): URL, giao diện, Jetty và bảo mật Web Console.
2. [ActiveMQ Classic — Monitoring ActiveMQ](https://activemq.apache.org/components/classic/documentation/monitoring-activemq-classic): Web Console và JMX.
3. [ActiveMQ Classic — JMX](https://activemq.apache.org/components/classic/documentation/jmx): `useJmx`, `managementContext`, MBeans, remote JMX và `suppressMBean`.
4. [ActiveMQ Classic — How Do I Find the Size of a Queue?](https://activemq.apache.org/components/classic/documentation/how-do-i-find-the-size-of-a-queue): `QueueSize`, `EnqueueCount`, `DequeueCount`, `DispatchCount`, `InFlightCount` và `ExpiredCount`.
5. [ActiveMQ Classic — DestinationViewMBean API](https://activemq.apache.org/components/classic/documentation/maven/apidocs/org/apache/activemq/broker/jmx/DestinationViewMBean.html): các attribute và operation của destination.
6. [ActiveMQ Classic — REST/Jolokia Management](https://activemq.apache.org/components/classic/documentation/rest): REST management API, đường dẫn và security policy.
7. [ActiveMQ Classic — Slow Consumer Handling](https://activemq.apache.org/components/classic/documentation/slow-consumer-handling): chỉ số subscription và cơ chế slow consumer.
