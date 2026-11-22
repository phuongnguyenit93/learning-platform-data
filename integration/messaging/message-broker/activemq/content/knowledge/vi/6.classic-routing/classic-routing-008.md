# Dọn destination không hoạt động và tránh xóa nhầm dữ liệu

> **Chương:** Định tuyến Classic  
> **Phạm vi:** Apache ActiveMQ **Classic** (không dùng cấu hình của Artemis). Bài học tập trung vào vòng đời queue/topic, chính sách xóa destination không hoạt động, thao tác quản trị qua JMX và cách bảo vệ message đang chờ xử lý. Ví dụ Java sử dụng ActiveMQ Classic 6.4.x, JDK 17 và namespace `jakarta.jms`; khi dùng Classic 5.x cần chọn client/namespace JMS phù hợp.

## 1. Vấn đề: broker có hàng nghìn destination nhưng bao nhiêu cái thực sự bỏ được?

Classic có thể tạo destination khi producer hoặc consumer truy cập một tên mới. Nếu ứng dụng đặt tên queue theo từng job, request, tenant hoặc phiên bản triển khai, sau nhiều tháng broker có thể tích lũy rất nhiều queue không còn được dùng. Số lượng destination lớn làm tăng chi phí quản lý MBean, advisory, thống kê, bộ nhớ và thao tác vận hành.

Ví dụ ứng dụng trước đây tạo queue `lab.ephemeral.export-2026-10-01`, sau đó đổi tên mỗi lần chạy. Queue cũ có thể rỗng, không còn consumer và an toàn để xóa. Tuy nhiên queue `invoice.processing` có thể **không có consumer lúc nửa đêm** nhưng vẫn đang giữ hóa đơn cần xử lý vào sáng hôm sau. Nếu quản trị viên xóa chỉ vì không thấy consumer, dữ liệu có thể mất.

Mục tiêu của việc dọn dẹp là **giảm destination bỏ hoang mà không làm mất nghiệp vụ**. Do đó phải tách ba câu hỏi:

1. Destination có đang trống và không có consumer ở thời điểm đo không?
2. Destination có còn thuộc một luồng nghiệp vụ cần được bảo toàn trong tương lai không?
3. Sau khi xác định nó không còn cần thiết, nên để broker tự thu gom, xóa thủ công hay chỉ sửa ứng dụng để không tạo thêm tên rác?

Một phép đo tức thời **không đủ** để trả lời câu hỏi thứ hai.

## 2. Phân biệt chính xác thao tác “dọn”

| Thao tác | Đối tượng bị tác động | Tác động đến dữ liệu | Khi nào thích hợp |
|---|---|---|---|
| **Chỉ giám sát** qua JMX/Web Console | Thống kê, danh sách queue/topic | Không xóa message | Bước đầu tiên cho mọi quyết định |
| **Tự GC destination không hoạt động** | Destination khớp `destinationPolicy` sau thời gian inactive | Broker loại bỏ destination khi đáp ứng điều kiện inactive; không phải công cụ lưu trữ dữ liệu | Queue động, sống ngắn, có naming convention rõ |
| **`QueueViewMBean.purge()`** | Message còn trong **queue** | **Xóa message trong queue**, giữ lại destination | Chỉ khi nghiệp vụ phê duyệt hủy backlog |
| **`BrokerViewMBean.removeQueue(name)`** | Bản thân queue | Có nguy cơ **xóa cả message chưa xử lý**; không coi là thao tác vô hại | Queue đã ngừng sử dụng, đã kiểm tra và cách ly producer |
| **`BrokerViewMBean.removeTopic(name)`** | Bản thân topic | Có thể ảnh hưởng các subscription/dữ liệu topic đang được duy trì | Chỉ khi đã đánh giá đầy đủ subscribers và retention |
| **Xóa durable subscription** | Trạng thái đăng ký nhận tin của subscriber | Có thể làm mất backlog được giữ riêng cho subscriber offline | Quy trình khác, cần xác nhận chủ sở hữu |
| **Xóa data directory/KahaDB** | Kho dữ liệu của broker | **Hủy phạm vi dữ liệu rất rộng**, bao gồm message và metadata | Không phải cách dọn destination; tuyệt đối không dùng như thao tác thường nhật |

Trong tài liệu Apache, chữ *purge* đôi khi xuất hiện trong tên cấu hình `schedulePeriodForDestinationPurge`, nhưng tính năng này **lên lịch kiểm tra và thu gom destination inactive**. Nó khác hoàn toàn phương thức `QueueViewMBean.purge()`, vốn xóa các message đang ở queue. Hai cơ chế cần được phân biệt trong runbook.

## 3. “Inactive” đối với Classic là gì?

Theo tài liệu **Delete Inactive Destinations** của ActiveMQ Classic, destination được xem là inactive khi **không còn message pending và không có consumer kết nối trong một khoảng thời gian cấu hình**. Mặc định, Classic **không tự quét** vì `schedulePeriodForDestinationPurge="0"` và `gcInactiveDestinations="false"`.

Điều kiện trên là quy tắc nội bộ của broker để thu gom tài nguyên; nó **không chứng minh queue đã hết vòng đời nghiệp vụ**.

| Tín hiệu quan sát | Ý nghĩa | Vì sao chưa đủ để quyết định xóa |
|---|---|---|
| `QueueSize = 0` | Không có message đang chờ trong queue ở lần đo | Có thể có message đang in-flight hoặc sẽ đến ở lần batch kế tiếp |
| `ConsumerCount = 0` | Không có consumer kết nối hiện tại | Consumer có thể chỉ chạy theo lịch hoặc đang bị lỗi |
| `InFlightCount = 0` | Không thấy message đã dispatch nhưng chưa được xử lý xong | Message mới vẫn có thể được gửi trong khi thao tác |
| `ProducerCount = 0` | Không có producer hiện hữu được broker ghi nhận tại thời điểm đo | Producer có thể kết nối ngắn rồi ngắt; cần xem lưu lượng theo thời gian |
| `EnqueueCount`, `DequeueCount` không tăng | Không có hoạt động tương ứng giữa hai lần chụp thống kê | Counters có thể reset khi restart hoặc được reset thủ công |
| Không có log trong khoảng quan sát | Không phát hiện hoạt động ở nguồn log đang xem | Log level, retention hoặc monitoring có thể chưa đủ |
| Không còn consumer trong một broker | Broker đó đang không có consumer trực tiếp | Network connector có thể chuyển lưu lượng giữa broker; kiểm tra toàn topology |

Đối với queue, nên giám sát cả `QueueSize`, `InFlightCount`, `ConsumerCount`, `ProducerCount` và **mức tăng** enqueue/dequeue trong cửa sổ phù hợp chu kỳ nghiệp vụ, chẳng hạn qua vài lần chạy batch. Các chỉ số là cơ sở **đề cử** queue để dọn, chưa phải lệnh xóa.

### Các nhóm cần loại trừ khỏi danh sách xóa tự động

- Queue nghiệp vụ chính, queue dùng bởi batch chạy tuần/tháng, hoặc consumer được chủ động tạm dừng.
- `ActiveMQ.DLQ` và các DLQ chuyên biệt: backlog lỗi có thể là bằng chứng điều tra hoặc dữ liệu cần replay.
- Queue kiểu `Consumer.<group>.VirtualTopic.<name>`: một consumer group đang offline vẫn có thể có ý nghĩa nghiệp vụ; kiểm tra luồng Virtual Topic và hợp đồng tiêu thụ.
- Topic có **durable subscriber** offline: `ConsumerCount = 0` không có nghĩa không có message được giữ cho subscriber.
- Advisory/temporary destination (`ActiveMQ.Advisory.*`, `TemporaryQueue`, `TemporaryTopic`), bridge hoặc network connector dùng nội bộ: có vòng đời riêng, không nên dọn bằng một rule nghiệp vụ chung.
- Destination dùng trong scheduled/delayed message, transaction còn treo, hoặc được quản lý bởi ứng dụng chưa được xác nhận đã ngừng.

**Đặc biệt với durable topic:** backlog có thể nằm ở trạng thái subscription, không thể suy ra chỉ bằng một chỉ số QueueSize của topic. ActiveMQ Classic có cấu hình **riêng** để hết hạn durable subscriber offline (`offlineDurableSubscriberTimeout`); đây là một quyết định về retention khác và không nên bật chỉ để làm gọn danh sách destination.

## 4. Kiểm kê trước khi xóa: chụp hai mốc và xác minh chủ sở hữu

Nên bắt đầu bằng **một namespace dành cho queue tạm**, ví dụ `lab.ephemeral.>` (dấu `>` là wildcard ActiveMQ khớp các phần tên còn lại). Tránh quét với ý định xóa mọi destination khớp `>` ngay từ đầu.

**Dữ liệu cần đưa vào phiếu đánh giá:**

| Nhóm bằng chứng | Trường cần lưu | Cách thu thập |
|---|---|---|
| Danh tính | Broker name, environment, queue/topic chính xác, namespace, owner | JMX, cấu hình app, tài liệu vận hành |
| Tồn đọng | `QueueSize`, `InFlightCount`, DLQ liên quan | `QueueViewMBean`, Web Console, monitoring |
| Kết nối | `ConsumerCount`, `ProducerCount`, network consumers | JMX và thông tin network topology |
| Hoạt động | `EnqueueCount`, `DequeueCount` tại T0 và T1, thời điểm producer/consumer cuối | Monitoring theo thời gian; không dựa vào counter duy nhất |
| Retention | TTL, durable subscription, chính sách retry, lịch batch | Chủ sở hữu ứng dụng và cấu hình broker |
| Kết luận | KEEP / CANDIDATE / BLOCKED / APPROVED | Review của người sở hữu luồng dữ liệu |

Ví dụ nhận xét trên ba queue:

| Destination | Quan sát | Quyết định |
|---|---|---|
| `lab.ephemeral.report-42` | Không message, không in-flight/consumer; không enqueue trong nhiều chu kỳ, job đã kết thúc | **CANDIDATE**, tiếp tục kiểm tra và chờ chốt |
| `billing.invoice` | `QueueSize=0`, `ConsumerCount=0` lúc 02:00; batch chạy 07:00 | **KEEP** |
| `ActiveMQ.DLQ` | ConsumerCount=0, có message thất bại | **BLOCKED**, điều tra DLQ riêng |

Một danh sách “ứng viên dọn” tốt **không** chứa mật khẩu, nội dung hóa đơn hoặc payload nghiệp vụ. Lưu thông tin cấu trúc và thống kê; chỉ export message thực nếu cần bảo toàn và được cấp quyền phù hợp.

## 5. Đọc thống kê an toàn qua JMX

Classic đăng ký MBeans trong miền `org.apache.activemq` (trừ khi hệ thống đổi `jmxDomainName`). Một queue có MBean theo dạng:

```text
org.apache.activemq:type=Broker,brokerName=<broker>,
  destinationType=Queue,destinationName=<exact-queue-name>
```

Trong **JConsole** hoặc công cụ JMX nội bộ có xác thực, vào broker → destination Queue, xem các thuộc tính `QueueSize`, `ConsumerCount`, `InFlightCount`, `EnqueueCount`, `DequeueCount`. Chỉ đọc thuộc tính ở bước kiểm kê; **không bấm `purge`, `removeQueue` hoặc `resetStatistics`** vì đó là các phép thay đổi trạng thái.

**Quyền quản trị:** JMX remote thường không được bật sẵn trong cấu hình Classic vì lý do bảo mật. Chỉ mở nó qua kênh quản trị được xác thực và bảo vệ mạng (localhost/SSH tunnel hoặc thiết lập TLS được kiểm soát); không xuất cổng JMX công khai chỉ để làm bài lab.

### Java/JMX: chương trình chỉ đọc để liệt kê queue thuộc một prefix

Ví dụ dùng Java 17, **không yêu cầu thư viện ActiveMQ** vì làm việc với JMX API có sẵn trong JDK. Chương trình không có phương thức xóa; nó chỉ tìm MBean queue và in thống kê.

**`DestinationAudit.java`**

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class DestinationAudit {
    private static long number(MBeanServerConnection mbs,
                               ObjectName name, String attribute) throws Exception {
        return ((Number) mbs.getAttribute(name, attribute)).longValue();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[1].startsWith("lab.ephemeral.")) {
            throw new IllegalArgumentException(
                "Usage: java DestinationAudit.java <JMX_URL> lab.ephemeral.");
        }

        String prefix = args[1];
        Map<String, Object> env = new HashMap<>();
        String user = System.getenv("JMX_USER");
        String pass = System.getenv("JMX_PASSWORD");
        if (user != null && pass != null) {
            env.put(JMXConnector.CREDENTIALS, new String[]{user, pass});
        }

        JMXServiceURL url = new JMXServiceURL(args[0]);
        try (JMXConnector connector = JMXConnectorFactory.connect(url, env)) {
            MBeanServerConnection mbs = connector.getMBeanServerConnection();
            ObjectName pattern = new ObjectName(
                "org.apache.activemq:type=Broker,brokerName=*," +
                "destinationType=Queue,destinationName=*,*");
            Set<ObjectName> names = mbs.queryNames(pattern, null);

            System.out.println(
                "Queue | Pending | InFlight | Consumers | Producers | Enqueued | Dequeued");
            for (ObjectName name : names) {
                String queue = name.getKeyProperty("destinationName");
                if (queue == null || !queue.startsWith(prefix)) {
                    continue;
                }
                System.out.printf("%s | %d | %d | %d | %d | %d | %d%n",
                    queue,
                    number(mbs, name, "QueueSize"),
                    number(mbs, name, "InFlightCount"),
                    number(mbs, name, "ConsumerCount"),
                    number(mbs, name, "ProducerCount"),
                    number(mbs, name, "EnqueueCount"),
                    number(mbs, name, "DequeueCount"));
            }
        }
    }
}
```

**Chạy sau khi đã có JMX endpoint được cấu hình an toàn:**

```bash
java DestinationAudit.java \
  'service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi' \
  lab.ephemeral.
```

URL và cổng `1099` ở đây là ví dụ, **không phải bảo đảm broker đã bật JMX remote**. Khi có xác thực, cấp `JMX_USER`/`JMX_PASSWORD` qua kênh secret cục bộ, không ghi mật khẩu vào câu lệnh hoặc Git. Trong mạng nhiều broker, chạy từng broker và lưu timestamp; không dùng kết quả ở một node để kết luận toàn cụm.

Chương trình trên là một **ảnh chụp**. Hãy lưu ít nhất hai lần chạy T0/T1 có khoảng cách bao phủ chu kỳ nghiệp vụ; đối chiếu với kế hoạch batch, logs và ứng dụng tạo destination. Không tự động gắn nhãn “có thể xóa” chỉ từ một dòng toàn số 0.

### Java/JMS: browse header trước khi quyết định

Nếu JMX cho thấy một queue **đã tồn tại**, có thể dùng JMS `QueueBrowser` để kiểm tra mẫu message còn đợi trong queue mà không gọi consumer nhận/ack. Mẫu này dùng Classic 6.4.x:

**Dependency Maven (đặt trong `<dependencies>` của `pom.xml`):**

```xml
<dependency>
  <groupId>org.apache.activemq</groupId>
  <artifactId>activemq-client</artifactId>
  <version>6.4.0</version>
</dependency>
```

**`QueuePeek.java`:**

```java
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.QueueBrowser;
import org.apache.activemq.ActiveMQConnectionFactory;

import java.util.Enumeration;

public class QueuePeek {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !args[0].startsWith("lab.ephemeral.")) {
            throw new IllegalArgumentException("Queue name must start with lab.ephemeral.");
        }

        String user = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");
        if (user == null || password == null) {
            throw new IllegalArgumentException("Missing broker credentials");
        }

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
        try (JMSContext context = factory.createContext(user, password)) {
            Queue queue = context.createQueue(args[0]);
            QueueBrowser browser = context.createBrowser(queue);
            try {
                Enumeration<?> items = browser.getEnumeration();
                int seen = 0;
                while (items.hasMoreElements() && seen < 20) {
                    Message m = (Message) items.nextElement();
                    System.out.println("JMSMessageID=" + m.getJMSMessageID()
                        + " JMSTimestamp=" + m.getJMSTimestamp());
                    seen++;
                }
                System.out.println("Browsed at most 20 pending messages.");
            } finally {
                browser.close();
            }
        }
    }
}
```

`QueueBrowser` không tiêu thụ/ack message, nhưng **không phải snapshot nhất quán**, không bảo đảm xem được toàn bộ queue hoặc các message đang in-flight. Việc mở browser trên tên chưa tồn tại có thể khiến Classic **tạo destination mới**, vì vậy luôn xác nhận tên qua JMX trước. Dùng tài khoản chỉ có quyền cần thiết và không in message body chứa dữ liệu nhạy cảm. Với Classic 5.x, dùng đúng phiên bản client `javax.jms` hoặc client Jakarta chuyển tiếp tương thích; không copy dependency 6.x sang ứng dụng 5.x một cách máy móc.

## 6. Tự thu gom destination inactive theo prefix

Tính năng GC cần **hai cấu hình cùng có hiệu lực**:

1. `schedulePeriodForDestinationPurge` trên phần tử broker phải lớn hơn 0, đơn vị **mili giây**.
2. `gcInactiveDestinations="true"` trên `policyEntry` khớp destination; đồng thời xác định `inactiveTimeoutBeforeGC` (hoặc cách viết cũ `inactiveTimoutBeforeGC` nếu phiên bản đang dùng yêu cầu).

**Ví dụ cho Classic hiện đại**, cấu hình **một namespace dành riêng cho queue tạm đã được duyệt**, không bật cho mọi queue:

```xml
<!-- Chỉ trích phần cần sửa trong activemq.xml hoàn chỉnh. -->
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-lab"
        schedulePeriodForDestinationPurge="60000">

  <destinationPolicy>
    <policyMap>
      <policyEntries>
        <policyEntry
            queue="lab.ephemeral.>"
            gcInactiveDestinations="true"
            inactiveTimeoutBeforeGC="86400000"/>
      </policyEntries>
    </policyMap>
  </destinationPolicy>

</broker>
```

Trong ví dụ:

- Mỗi **60.000 ms (1 phút)** broker kiểm tra destination inactive.
- Chỉ queue khớp `lab.ephemeral.>` được cân nhắc GC.
- `86.400.000 ms` tương ứng **24 giờ inactive**; đây là thời gian ví dụ, không phải khuyến nghị cố định cho production.
- Một queue đủ điều kiện có thể được thu gom **sau lần quét tiếp theo**, không nhất thiết đúng ở mốc 24 giờ.

Đoạn trên chỉ minh họa cấu trúc. Với cấu hình Classic thực tế, hãy **thêm thuộc tính vào phần tử `<broker>` đã có và thêm `policyEntry` trong `<policyEntries>` hiện hữu**, không tạo hai phần tử broker hoặc destinationPolicy. Một `policyEntry` cụ thể có thể được chọn **thay** policy wildcard chung; kiểm tra những thiết lập `deadLetterStrategy`, `memoryLimit`, `producerFlowControl` và các hạn mức trước đó để không vô tình thay đổi hành vi định tuyến.

### Vấn đề tên thuộc tính theo phiên bản

Tài liệu Classic cũ có ví dụ `inactiveTimoutBeforeGC` (*thiếu chữ e* trong “Timeout”), còn API/schema của các dòng mới có tên sửa đúng `inactiveTimeoutBeforeGC`; cả hai cách viết xuất hiện trong tài liệu phiên bản khác nhau. **Tra XSD và tài liệu của đúng bản Classic đang chạy**, thử khởi động broker trong staging và đọc log validation. Đừng phụ thuộc vào default timeout vì các nguồn tài liệu của nhiều phiên bản có thể khác nhau; hãy đặt giá trị tường minh đã review.

### Tại sao không dùng `queue=">"`?

`queue=">"` áp dụng rộng cho mọi queue khớp, kể cả queue nghiệp vụ, queue retry, queue dành cho consumer chạy theo lịch và có thể cả DLQ. Tính năng GC có thể xóa destination khi nó đang rỗng và không có consumer, nhưng **không biết** hợp đồng nghiệp vụ yêu cầu giữ tên đó. Vì vậy:

- Chỉ bật cho prefix được thiết kế rõ là tạm thời; đặt tên nhất quán ở ứng dụng tạo queue.
- Không áp dụng cho Virtual Topic consumer queues, DLQ hoặc queue dành cho batch dài kỳ.
- Không bật `gcWithNetworkConsumers` để ép dọn queue trong topology có network consumer khi chưa mô phỏng và xác minh hành vi bridge.
- Đọc log theo mẫu đại ý `Inactive for longer than ... - removing`, rồi đối chiếu danh sách MBean trước/sau; log này xác nhận broker đã bỏ destination, không chứng minh xóa là đúng nghiệp vụ.

Nếu producer tiếp tục sử dụng tên cũ, Classic có thể **tạo lại destination** sau khi GC. Giải pháp gốc là sửa vòng đời/naming của ứng dụng, không chỉ giảm timeout.

## 7. Dọn thủ công: quy trình hai lần kiểm tra trước khi thay đổi

Khi destination nằm ngoài prefix tự GC, hoặc cần xử lý một lần, dùng quy trình có thể kiểm toán.

### Giai đoạn A — Đề xuất và cách ly

1. Ghi **tên chính xác** `brokerName`, `destinationType` và `destinationName`; xác nhận đang kết nối đúng môi trường. Không dùng wildcard để gọi thao tác xóa.
2. Xác định chủ sở hữu, mục đích, lịch gửi/nhận; lấy xác nhận ngừng sử dụng. Kiểm tra các phiên bản ứng dụng cũ, batch scheduler, network connectors, durable subscriptions và quy tắc Virtual Topic.
3. Lưu số liệu T0/T1: `QueueSize`, `InFlightCount`, consumer/producer, lượng enqueue/dequeue và log. Nếu còn message chưa xử lý, dừng kế hoạch xóa; xử lý/replay/đưa vào lưu trữ theo quyết định nghiệp vụ trước.
4. **Ngăn producer gửi vào tên cũ** và ngăn tự tạo lại queue (qua thay đổi ứng dụng, quyền broker hoặc triển khai kiểm soát). Cho phép các transaction/in-flight kết thúc; kiểm tra lại lần cuối sau khi cách ly.
5. Ghi lại ticket, người phê duyệt, thời gian bảo trì, kế hoạch phục hồi và bằng chứng trước thao tác. Nếu cần giữ dữ liệu, dùng backup/snapshot **nhất quán theo quy trình broker**; không sao chép tùy tiện thư mục KahaDB trong lúc ghi.

Nếu không thể đóng cửa sổ race giữa bước “queue rỗng” và “xóa”, **không thực hiện xóa thủ công**. Một producer có thể đưa message mới vào queue ngay sau khi bạn vừa đọc số liệu.

### Giai đoạn B — Xóa chính xác, xác minh và theo dõi

1. Dùng JConsole/Web Console nội bộ với quyền được cấp, đi tới MBean broker đúng tên. Chỉ chọn phương thức **`BrokerViewMBean.removeQueue(String)`** và truyền **đúng một tên queue đã phê duyệt**, hoặc `removeTopic(String)` khi đã đánh giá riêng các subscriber.
2. Trước khi bấm thực hiện, đọc lại queue size, in-flight và mọi điều kiện bảo vệ; nếu điều kiện thay đổi, **dừng**.
3. Sau thao tác, xác nhận MBean của destination biến mất, các queue khác và DLQ vẫn còn, log không có lỗi bất thường. Quan sát xem queue có được producer cũ tạo lại hay không.
4. Đối chiếu số liệu và lưu log vận hành vào ticket. Nếu phát hiện mất dữ liệu, không tiếp tục dọn hàng loạt; xử lý khôi phục từ bản sao lưu đáng tin cậy theo runbook.

**Lệnh JMX cần hiểu đúng (không chạy trong chương trình kiểm kê):**

```java
// Mã minh họa cho một thay đổi ĐÃ được xác nhận ở đúng broker.
// mbs là MBeanServerConnection có quyền quản trị.
// brokerName xác định qua ObjectName của broker thực tế.
ObjectName broker = new ObjectName(
    "org.apache.activemq:type=Broker,brokerName=classic-lab");

String approvedQueue = "lab.ephemeral.report-42";
mbs.invoke(
    broker,
    "removeQueue",
    new Object[]{approvedQueue},
    new String[]{String.class.getName()});
```

Đoạn mã trên là ví dụ API cho một queue cụ thể, **không phải chương trình tự động đã hoàn chỉnh**. Trước khi biến nó thành tool vận hành, cần bắt buộc chế độ dry-run mặc định, allowlist/prefix, kiểm tra lại JMX attributes ngay trước thao tác, xác nhận chính xác broker/destination, phân quyền, audit log và giới hạn tốc độ. **Không** ghép phép gọi xóa vào chương trình quét ở mục 5.

### Vì sao `purge()` không phù hợp để dọn “queue rác”?

`QueueViewMBean.purge()` hủy các message trong queue và **để queue tồn tại**. Nó được dùng khi mục tiêu được phê duyệt là bỏ backlog, không phải khi muốn thu gọn danh sách destination. Sau purge, không thể dựa vào việc “queue vẫn còn” để kết luận dữ liệu an toàn. Tương tự, `activemq-admin purge` trong CLI là lệnh thao tác message; tên “purge” không đồng nghĩa với GC destination.

## 8. Bài thử tích hợp: chứng minh GC không làm mất backlog

Nên kiểm thử trên **broker Classic dành riêng cho lab**, dùng prefix `lab.ephemeral.`, không dùng production hoặc queue có dữ liệu thực. Bài thử có ba queue:

- `lab.ephemeral.empty-1`: được tạo rồi không có message/consumer.
- `lab.ephemeral.with-message-1`: có một message **persistent chưa được consume**.
- `billing.keep`: không có message, không có consumer, nhưng **ngoài** phạm vi policy GC.

Trong lab, tạm dùng `schedulePeriodForDestinationPurge="1000"` và `inactiveTimeoutBeforeGC="5000"` (1 giây quét, 5 giây inactive) để quan sát nhanh; đừng dùng timeout này trong production.

### Thiết lập trạng thái bằng Java/JMS

Với Maven dependency Classic 6.4.x đã nêu ở mục 5, ứng dụng test có thể tạo các destination trên bằng những lời gọi sau:

```java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import org.apache.activemq.ActiveMQConnectionFactory;

public class GcLabProducer {
    public static void main(String[] args) {
        String user = System.getenv("BROKER_USER");
        String pass = System.getenv("BROKER_PASSWORD");
        if (user == null || pass == null) {
            throw new IllegalArgumentException("Missing broker credentials");
        }

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
        try (JMSContext ctx = factory.createContext(user, pass)) {
            Queue empty = ctx.createQueue("lab.ephemeral.empty-1");
            Queue withMessage = ctx.createQueue("lab.ephemeral.with-message-1");
            Queue protectedQueue = ctx.createQueue("billing.keep");

            // JMS createQueue tạo handle ở client; gửi hoặc browse để broker
            // thực sự biết tới destination. Thực hành dùng một consumer ngắn
            // hoặc broker admin để tạo queue rỗng phục vụ GC.
            ctx.createProducer().setDeliveryMode(DeliveryMode.PERSISTENT)
                .send(withMessage, "MESSAGE-MUST-SURVIVE");
            // Không gửi message vào empty hoặc protectedQueue.
            System.out.println("Handles: " + empty + ", " + protectedQueue);
        }
    }
}
```

**Lưu ý chính xác:** `Session.createQueue` / `JMSContext.createQueue` có thể chỉ tạo *đối tượng destination ở phía client*; nó không bắt buộc tạo queue thật trên broker ngay. Để bài thử khách quan, hãy tạo `lab.ephemeral.empty-1` và `billing.keep` trước bằng công cụ quản trị broker, hoặc mở một consumer ngắn rồi đóng, sau đó xác nhận hai queue có MBean JMX. Không suy rằng hai dòng `createQueue` là bằng chứng queue đã xuất hiện.

### Kết quả mong đợi

| Destination | Dự đoán sau thời gian inactive | Bằng chứng |
|---|---|---|
| `lab.ephemeral.empty-1` | Bị GC nếu đã được tạo thật, rỗng và không còn consumer | MBean biến mất và có log GC |
| `lab.ephemeral.with-message-1` | **Còn tồn tại** vì vẫn có message pending | `QueueSize >= 1`, browse thấy message ID |
| `billing.keep` | **Còn tồn tại** vì không khớp prefix GC | MBean vẫn còn dù rỗng |

Sau khi thử xong, dùng **một consumer riêng có acknowledgment thích hợp** nhận message từ `lab.ephemeral.with-message-1` và xác minh nội dung “MESSAGE-MUST-SURVIVE”. Chỉ sau khi xử lý xong message và queue tiếp tục inactive, nó mới là ứng viên GC. Nếu queue rỗng bị GC rồi có producer quay lại, kiểm tra nó có thể được tạo lại theo chính sách auto-create: đây là một trường hợp hợp lệ về kỹ thuật nhưng có thể là lỗi thiết kế lifecycle.

Thử thêm một vòng **rollback/acknowledgment**: khi message đang được consumer giữ mà chưa ack, hãy kiểm tra `InFlightCount` và xác nhận không xóa queue. Không dùng `purge()` để “làm sạch test” nếu còn message có giá trị kiểm chứng.

## 9. Các trường hợp dễ xóa nhầm trong hệ thống thật

### 9.1. Consumer chạy thưa hoặc không ổn định

Queue cho báo cáo cuối tháng có thể rỗng và không có consumer trong nhiều ngày, nhưng vẫn cần giữ địa chỉ ổn định. Tên queue thuộc contract triển khai; không đưa nó vào GC chỉ vì đạt ngưỡng thời gian kỹ thuật. Nếu consumer ngừng vì sự cố, việc xóa queue làm che giấu vấn đề gốc.

### 9.2. Virtual Topic và network of brokers

Với Virtual Topic, các queue `Consumer.*.VirtualTopic.*` thường đại diện các nhóm nhận độc lập. Một nhóm tạm offline không đồng nghĩa đã ngừng hoạt động. Khi có network connector, producer/consumer có thể nằm trên broker khác; điều kiện inactive của một node không thay thế kiểm tra topology và hợp đồng phân phối. Tránh mở rộng GC với `gcWithNetworkConsumers` khi chưa thử tình huống bridge đứt rồi nối lại.

### 9.3. DLQ và retry

Message ở DLQ có thể cần điều tra, khôi phục hoặc replay. Một queue lỗi rỗng hôm nay vẫn có thể cần giữ vì policy redelivery sẽ gửi message vào đó ngày mai. Không đưa DLQ vào namespace “tạm để tự xóa” và không dùng purge để giải quyết chỉ số backlog vượt ngưỡng.

### 9.4. Durable topic subscriber offline

Durable subscriber lưu quyền nhận các message tương lai/trong thời gian offline theo chính sách của broker. Nó được quản lý tách biệt với việc dọn queue thông thường. Nếu muốn xóa subscriber offline, xác minh `clientID`, tên subscription, số message đang giữ và sự đồng ý của owner; cơ chế `offlineDurableSubscriberTimeout` mặc định không tự dọn subscriber (`-1`). Bật timeout này là thay đổi chính sách giữ dữ liệu, cần đánh giá độc lập.

### 9.5. Scheduled messages và giao dịch chưa kết thúc

Message được lập lịch hoặc transaction đang chờ commit có thể **chưa xuất hiện** trong các số liệu pending đơn giản tại lúc kiểm tra. Với ứng dụng dùng `AMQ_SCHEDULED_DELAY` hoặc scheduler của Classic, rà soát tác vụ/hợp đồng nghiệp vụ trước khi xóa destination đích. Không dùng `QueueSize=0` làm bằng chứng duy nhất rằng sẽ không có message gửi tới destination đó.

## 10. Runbook và tiêu chí hoàn thành

Một bản ghi dọn dẹp cần trả lời được các trường sau:

```text
Change ID:
Environment / BrokerName / Broker version:
Destination exact name / type:
Owner / ứng dụng tạo / ứng dụng tiêu thụ:
T0, T1 và khoảng quan sát:
QueueSize / InFlightCount / ConsumerCount / ProducerCount:
Delta EnqueueCount / DequeueCount:
Network / VirtualTopic / durable subscriber / DLQ check:
Ứng dụng producer đã cách ly?:
Message pending đã xử lý/được lưu an toàn?:
Phương án: KEEP / AUTO-GC / REMOVE / BLOCKED:
Người phê duyệt, thời điểm và bản sao lưu liên quan:
Before evidence / After evidence:
Kết quả quan sát queue có tái xuất hiện?:
```

**Checklist trước khi đánh dấu DONE:**

1. Đã xác minh đúng **Classic broker** và queue/topic cụ thể; không nhầm Classic với Artemis hoặc môi trường staging với production.
2. Có dữ liệu quan sát qua nhiều thời điểm, có xác nhận owner; mọi queue có pending/in-flight, durable subscriber, DLQ hoặc producer chưa cách ly đều được giữ lại.
3. Nếu bật auto-GC: có `schedulePeriodForDestinationPurge > 0`, policy chỉ khớp prefix đã được phê duyệt, timeout rõ ràng, staging test PASS, không phá chính sách DLQ/security hiện có.
4. Nếu xóa thủ công: thao tác chính xác một tên, đã cô lập producer và kiểm tra lại tức thời trước khi thực hiện, có log/ticket và kế hoạch khôi phục.
5. Sau cleanup: danh sách MBean đúng kỳ vọng, không mất message, không ảnh hưởng queue khác; monitoring tiếp tục kiểm tra tái tạo destination, backlog và lỗi tiêu thụ.

Khi số lượng queue tăng liên tục dù GC vẫn chạy, hãy kiểm tra **quy tắc đặt tên, việc tạo queue theo request và lifecycle trong ứng dụng**. Thu gom chỉ giải quyết hậu quả; sửa nơi tạo destination mới có thể quan trọng hơn xóa nhanh hơn.

## Tài liệu đối chiếu

1. Apache ActiveMQ Classic — [Delete Inactive Destinations](https://activemq.apache.org/components/classic/documentation/delete-inactive-destinations): định nghĩa inactive, scheduler, policy và log GC.
2. Apache ActiveMQ Classic — [Per Destination Policies](https://activemq.apache.org/components/classic/documentation/per-destination-policies): `gcInactiveDestinations` và những thuộc tính policy.
3. Apache ActiveMQ Classic — [JMX](https://activemq.apache.org/components/classic/documentation/jmx): MBean, counters, các operation và bảo mật JMX.
4. Apache ActiveMQ Classic — [How do I purge a queue?](https://activemq.apache.org/components/classic/documentation/how-do-i-purge-a-queue): phân biệt xóa message và xóa destination.
5. Apache ActiveMQ Classic — [How do I delete a destination?](https://activemq.apache.org/components/classic/documentation/how-do-i-delete-a-destination): `removeQueue` và `removeTopic`.
6. Apache ActiveMQ Classic — [Manage Durable Subscribers](https://activemq.apache.org/components/classic/documentation/manage-durable-subscribers): dữ liệu của subscriber offline và timeout.
7. Apache ActiveMQ Classic — [Advisory Messages](https://activemq.apache.org/components/classic/documentation/advisory-message): advisory topics, lifecycle notification và lưu ý về network brokers.
8. Apache ActiveMQ Classic — [Jakarta Messaging 3.1/JMS 2.0 Support](https://activemq.apache.org/components/classic/documentation/jms2): lựa chọn namespace client cho Classic 5.x và 6.x.
