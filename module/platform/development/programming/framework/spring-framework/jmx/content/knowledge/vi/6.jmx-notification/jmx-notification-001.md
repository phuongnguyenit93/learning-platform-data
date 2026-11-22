# JMX Notification là gì và khác với đọc metric định kỳ ra sao?

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **JMX Notification** là thông điệp sự kiện được MBean phát ra cho các listener khi có một diễn biến đáng quan tâm.
- Phân biệt cơ chế **push theo sự kiện** với cơ chế **polling đọc metric định kỳ** qua JMX attributes.
- Hiểu vai trò của \`NotificationBroadcaster\`, \`NotificationEmitter\`, \`NotificationListener\`, \`NotificationFilter\` và \`MBeanServer\`.
- Viết Standard MBean phát notification, đăng ký listener, nhận và xử lý thông điệp.
- Biết khi nào nên dùng notification, metric hoặc kết hợp cả hai để giám sát ứng dụng Spring.
- Nhận diện các giới hạn như thất lạc sự kiện, vòng đời listener, thread xử lý và yêu cầu về bảo mật hoặc khả năng chịu tải.

## 2. Bối cảnh: quan sát trạng thái hay phản ứng với sự kiện?

Trong Java Management Extensions (JMX), ứng dụng thường cần giải quyết hai câu hỏi khác nhau:

1. **Trạng thái hiện tại ra sao?** Ví dụ: có bao nhiêu request đang xử lý, kích thước cache hiện tại là bao nhiêu, thread pool còn bao nhiêu worker.
2. **Điều gì vừa xảy ra?** Ví dụ: queue vừa vượt ngưỡng cảnh báo, một cache vừa bị xóa, một tác vụ vừa thất bại hoặc một service vừa chuyển sang trạng thái degraded.

Để trả lời câu hỏi thứ nhất, MBean thường công bố **JMX attributes**. Công cụ giám sát truy vấn \`getAttribute\` theo chu kỳ: 5 giây, 30 giây hoặc 1 phút tùy cấu hình.

Để trả lời câu hỏi thứ hai, MBean có thể **phát JMX Notification** khi sự kiện xảy ra. Các listener đã đăng ký nhận thông điệp mà không phải liên tục hỏi xem sự kiện có diễn ra chưa.

Ví dụ một queue xử lý đơn hàng:

\`\`\`text
Thời điểm:          10:00       10:01       10:02       10:03

Queue size:            20          42          95          35
Metric polling:        20          42          95          35
Sự kiện thực tế:                   vượt ngưỡng 80 lúc 10:01:45

JMX Notification:                  QueueThresholdExceeded
                                  phát ngay khi phát hiện
\`\`\`

Với polling 1 phút, dashboard có thể nhìn thấy queue size 95 tại 10:02; với notification, listener có thể nhận tín hiệu ngay lúc ứng dụng xác định queue đã vượt ngưỡng. Tuy nhiên, thời gian nhận thực tế vẫn phụ thuộc cách phát notification, thread, kết nối và trạng thái client; notification không đảm bảo độ trễ bằng không.

## 3. JMX Notification là gì?

\`javax.management.Notification\` là đối tượng biểu diễn một **thông báo sự kiện quản trị**. Thông điệp thường gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| \`type\` | Chuỗi định danh loại sự kiện, ví dụ \`com.example.shop.queue.threshold.exceeded\` |
| \`source\` | Nguồn phát sự kiện; khi làm việc qua MBeanServer có thể được biểu diễn bằng ObjectName |
| \`sequenceNumber\` | Số thứ tự do nguồn phát quản lý |
| \`timeStamp\` | Thời điểm gắn trên notification (milliseconds since epoch) |
| \`message\` | Nội dung mô tả dễ đọc |
| \`userData\` | Dữ liệu bổ sung tùy chọn; cần cân nhắc serializability và khả năng tương thích client |

Ví dụ:

\`\`\`java
Notification event = new Notification(
        "com.example.shop.queue.threshold.exceeded",
        this,
        18L,
        System.currentTimeMillis(),
        "Order queue vượt ngưỡng 80"
);
\`\`\`

Notification thuộc hệ thống JMX management. Nó không đồng nghĩa với Spring \`ApplicationEvent\`, JMS message, Kafka record hoặc log event. Những cơ chế này có thể cùng xuất hiện trong một hệ thống nhưng khác API, mục đích, vòng đời và bảo đảm delivery.

**Định nghĩa dễ nhớ:** *Metric mô tả một giá trị/trạng thái; notification thông báo rằng một sự kiện quản trị đã xảy ra.*

Không phải mọi MBean tự phát notification. MBean cần triển khai cơ chế broadcaster/emitter hoặc được một framework cấu hình để hỗ trợ phát sự kiện.

## 4. Cấu trúc của cơ chế notification

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| \`Notification\` | Payload sự kiện gửi cho listener |
| \`NotificationBroadcaster\` | Contract cho phép thêm/xóa listener và khai báo loại notification |
| \`NotificationEmitter\` | Mở rộng broadcaster với thao tác gỡ listener theo filter/handback cụ thể |
| \`NotificationBroadcasterSupport\` | Lớp tiện ích phổ biến hỗ trợ quản lý listener và gửi notification |
| \`NotificationListener\` | Callback \`handleNotification(notification, handback)\` nhận sự kiện |
| \`NotificationFilter\` | Quyết định notification có được chuyển tới listener hay không |
| \`MBeanServer\` | Cho phép đăng ký MBean và quản lý listener thông qua ObjectName |

Luồng vận hành:

\`\`\`text
                 Ứng dụng cập nhật trạng thái
                             |
                             v
                   MBean phát Notification
                             |
                    NotificationBroadcaster
                             |
                    +--------+--------+
                    |                 |
                    v                 v
             Listener A          Listener B
             filter theo        xử lý mọi
             threshold          event phù hợp

Độc lập với luồng trên:
Monitoring client -- getAttribute --> MBean --> giá trị hiện tại
\`\`\`

Broadcaster quản lý danh sách người nghe. Listener có thể được gắn vào đối tượng broadcaster trực tiếp hoặc đăng ký qua \`MBeanServer.addNotificationListener\` với ObjectName của MBean.

Đối với ứng dụng có nhiều listener, filter giúp tránh xử lý loại notification không liên quan. Nó **không** thay thế cơ chế kiểm soát quyền truy cập JMX.

## 5. Polling metric định kỳ hoạt động thế nào?

Trong JMX, một MBean có thể công bố attribute như:

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    long getProcessedCount();
    boolean isPaused();
}
\`\`\`

Công cụ giám sát gọi:

\`\`\`java
Object pending = server.getAttribute(
        objectName, "PendingCount");
\`\`\`

theo chu kỳ. Với một monitoring system, dữ liệu có thể được lưu làm time series:

\`\`\`text
t=0s   PendingCount=12
t=30s  PendingCount=28
t=60s  PendingCount=95
t=90s  PendingCount=20
\`\`\`

Polling thuận tiện cho dashboard và cảnh báo dựa trên trạng thái kéo dài, trung bình, tốc độ tăng/giảm, percentile hoặc xu hướng lịch sử. Một lần polling thường chỉ cho biết giá trị tại thời điểm đọc (hoặc snapshot mà attribute phản ánh), nên có thể bỏ qua biến động ngắn nằm giữa hai lần lấy mẫu.

Ví dụ queue tăng lên 110 rồi giảm xuống 10 trong khoảng giữa hai lần poll 30 giây; nếu chỉ thu thập \`PendingCount\`, các điểm đo có thể không bao giờ biểu diễn đỉnh 110. Notification được phát khi vượt ngưỡng có khả năng phản ánh sự kiện đó, nếu listener được đăng ký và đường truyền hoạt động.

## 6. So sánh Notification và polling metric

| Tiêu chí | JMX Notification | Polling JMX attribute |
|---|---|---|
| Mô hình | Push sự kiện tới listener | Client pull giá trị theo chu kỳ |
| Câu hỏi phù hợp | “Vừa xảy ra điều gì?” | “Trạng thái hiện tại là gì?” |
| Thời điểm dữ liệu | Khi ứng dụng quyết định phát event | Khi client đọc attribute |
| Dữ liệu | Loại sự kiện, nguồn, timestamp, message, userData | Giá trị hiện tại như size, count, state |
| Tần suất | Phụ thuộc số sự kiện phát sinh | Phụ thuộc interval |
| Khi không có sự kiện | Thường không gửi thông điệp | Vẫn có thể đọc để xác nhận trạng thái |
| Sự kiện rất ngắn | Có thể phát hiện nếu ứng dụng emit đúng lúc | Có thể bị bỏ lỡ giữa các lần polling |
| Thu thập lịch sử | Cần listener và lưu trữ phía consumer | Dễ tích hợp time series với chu kỳ thu thập |
| Chi phí | Tăng theo số event và listener | Tăng theo số MBean/attribute và tần suất poll |
| Độ tin cậy | Không mặc nhiên có persistence, ack, replay | Mỗi lần poll cung cấp snapshot mới nếu kết nối thành công |
| Cảnh báo | Phù hợp edge/event, state transition | Phù hợp threshold tồn tại lâu, trend, rate |
| Khởi động listener muộn | Có thể bỏ lỡ event đã xảy ra | Đọc ngay trạng thái hiện tại được |

**Điểm then chốt:** Notification và polling không loại trừ nhau. Thiết kế tốt thường dùng **metric để biết trạng thái và xu hướng**, dùng **notification để báo sự kiện quan trọng tại thời điểm xảy ra**.

Notification không nên được coi như hàng đợi sự kiện bảo đảm giao nhận. JMX notification API không mặc định cung cấp durable storage, retry, acknowledgement hay replay. Nếu một sự kiện nghiệp vụ bắt buộc không được mất, cần cơ chế messaging/persistence phù hợp bên cạnh hoặc thay cho notification.

## 7. Ví dụ đầy đủ: Standard MBean vừa có metric vừa phát Notification

Ta tạo \`QueueMonitor\` gồm:

- Attribute \`PendingCount\` dùng để polling.
- Operation \`enqueue(int amount)\` mô phỏng thêm công việc.
- Notification khi queue chuyển từ dưới/ngang ngưỡng sang **vượt** ngưỡng.

### 7.1 Management interface

**\`QueueMonitorMBean.java\`**

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    int getWarningThreshold();
    void enqueue(int amount);
    void clear();
}
\`\`\`

Interface quyết định attributes và operations mà JMX client thấy. Notification được hỗ trợ thông qua \`NotificationBroadcasterSupport\` bên lớp cài đặt.

### 7.2 Lớp cài đặt phát notification

**\`QueueMonitor.java\`**

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    public static final String THRESHOLD_EVENT =
            "com.example.shop.queue.threshold.exceeded";

    private final AtomicLong sequence = new AtomicLong();
    private final int warningThreshold;
    private int pendingCount;

    public QueueMonitor(int warningThreshold) {
        if (warningThreshold < 0) {
            throw new IllegalArgumentException(
                    "warningThreshold must be >= 0");
        }
        this.warningThreshold = warningThreshold;
    }

    @Override
    public synchronized int getPendingCount() {
        return pendingCount;
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void enqueue(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive");
        }

        final int before;
        final int after;

        synchronized (this) {
            before = pendingCount;
            pendingCount = Math.addExact(pendingCount, amount);
            after = pendingCount;
        }

        if (before <= warningThreshold && after > warningThreshold) {
            Notification event = new Notification(
                    THRESHOLD_EVENT,
                    this,
                    sequence.incrementAndGet(),
                    System.currentTimeMillis(),
                    "Queue vượt ngưỡng: " + after
            );
            event.setUserData(after);
            sendNotification(event);
        }
    }

    @Override
    public synchronized void clear() {
        pendingCount = 0;
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {THRESHOLD_EVENT};
        return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                        types,
                        Notification.class.getName(),
                        "Queue warning threshold crossed")
        };
    }
}
\`\`\`

Giải thích:

- \`QueueMonitorMBean\` công bố thông tin quản lý của queue; \`PendingCount\` và \`WarningThreshold\` là attributes.
- \`NotificationBroadcasterSupport\` cung cấp cơ chế đăng ký listeners và \`sendNotification\`.
- \`getNotificationInfo()\` cho công cụ biết loại notification có thể phát.
- \`AtomicLong\` cấp sequence number tăng dần cho từng event của emitter.
- Khi \`pendingCount\` **vượt qua** ngưỡng, MBean phát event. Các lần tăng tiếp theo khi đã ở trên ngưỡng không phát lại nếu không đi qua trạng thái dưới/ngang ngưỡng.
- \`userData\` chứa một Integer biểu thị pending count tại thời điểm phát.

Ví dụ ngắn sử dụng \`synchronized\` để bảo vệ trạng thái; code production cần thiết kế đồng bộ và thứ tự gửi sự kiện tương ứng với đặc tính concurrency của module. Trong ví dụ, \`sendNotification\` được gọi sau khi rời khóa để tránh giữ monitor lock khi listener chạy. Với thao tác đồng thời, listener có thể quan sát metric mới hơn payload của notification; event vẫn đại diện cho lần crossing đã phát.

### 7.3 Đăng ký MBean và listener

**\`NotificationDemo.java\`**

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class NotificationDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=outbox");

        QueueMonitor monitor = new QueueMonitor(80);
        server.registerMBean(monitor, name);

        NotificationListener listener = (event, handback) -> {
            System.out.println(
                    "[EVENT] " + event.getType()
                    + " #" + event.getSequenceNumber()
                    + " value=" + event.getUserData());
        };

        NotificationFilterSupport filter =
                new NotificationFilterSupport();
        filter.enableType(QueueMonitor.THRESHOLD_EVENT);

        try {
            server.addNotificationListener(name, listener, filter, null);
            try {
                System.out.println("Initial metric: "
                        + server.getAttribute(name, "PendingCount"));

                server.invoke(name, "enqueue",
                        new Object[] {50}, new String[] {"int"});
                server.invoke(name, "enqueue",
                        new Object[] {40}, new String[] {"int"});

                System.out.println("Current metric: "
                        + server.getAttribute(name, "PendingCount"));
            } finally {
                server.removeNotificationListener(name, listener);
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Kết quả minh họa:

\`\`\`text
Initial metric: 0
[EVENT] com.example.shop.queue.threshold.exceeded #1 value=90
Current metric: 90
\`\`\`

Do ví dụ dùng \`NotificationBroadcasterSupport\` mặc định, listener được gọi đồng bộ theo luồng gửi notification. Nếu cấu hình executor riêng, hoặc với JMX remote client, thứ tự hiển thị/timing có thể thay đổi. Không nên phụ thuộc vào timing stdout như một cam kết API.

### 7.4 Chạy thử

Lưu ba file trong cùng một thư mục/package rồi thực thi:

\`\`\`bash
javac QueueMonitorMBean.java QueueMonitor.java NotificationDemo.java
java NotificationDemo
\`\`\`

Đầu tiên \`enqueue(50)\` đưa count từ 0 lên 50, chưa vượt 80. Lần thứ hai \`enqueue(40)\` đưa count lên 90 và phát một notification. Việc đọc \`PendingCount\` trả 90 ngay cả khi listener đã xử lý xong event.

Chương trình kết thúc sau khi hủy listener và unregister MBean. Muốn quan sát qua JConsole, cần giữ JVM sống trong lúc registration tồn tại.

## 8. Hai cách đăng ký listener

### Cách A: qua MBeanServer

\`\`\`java
server.addNotificationListener(objectName, listener, filter, handback);
\`\`\`

Cách này phù hợp khi client biết ObjectName và muốn xử lý MBean theo giao diện JMX chuẩn. \`MBeanServer\` xác định broadcaster theo tên đã đăng ký.

### Cách B: trực tiếp trên emitter

\`\`\`java
QueueMonitor monitor = new QueueMonitor(80);
monitor.addNotificationListener(listener, filter, null);
\`\`\`

Cách này phù hợp với code cùng JVM đã giữ reference đến đối tượng, nhưng không thay thế việc đăng ký ObjectName nếu muốn công cụ JMX bên ngoài tra cứu MBean.

Trong cả hai cách, nên hủy listener khi ngừng sử dụng để tránh tích lũy callback và giữ object không cần thiết. Với API remove có nhiều biến thể, cần dùng đúng listener/filter/handback khi cần gỡ riêng một registration.

## 9. Filter, handback và metadata

### Filter

\`NotificationFilter\` nhận một notification và trả \`true\` nếu sự kiện nên được chuyển tới listener. \`NotificationFilterSupport\` hỗ trợ các prefix của notification type:

\`\`\`java
NotificationFilterSupport filter =
        new NotificationFilterSupport();

filter.enableType("com.example.shop.queue.");
\`\`\`

Filter trên nhận các loại có prefix \`com.example.shop.queue.\`, ví dụ \`threshold.exceeded\` hoặc \`consumer.stalled\`.

Nếu chỉ muốn một loại sự kiện, cung cấp toàn bộ type string. Các filter có thể giảm callback không cần thiết, nhưng không phải cơ chế kiểm soát quyền truy cập.

### Handback

\`handback\` là object do bên đăng ký listener cung cấp và được chuyển lại cho callback:

\`\`\`java
Object handback = "orders-dashboard";

server.addNotificationListener(name, listener, filter, handback);
\`\`\`

Trong callback, tham số thứ hai giúp phân biệt ngữ cảnh đăng ký. Nó không mặc nhiên là payload do broadcaster tạo ra; payload nằm ở \`Notification\`/\`userData\`.

### Metadata

\`MBeanNotificationInfo\` mô tả các loại notification MBean có thể phát. Có thể đọc thông qua \`MBeanServer.getMBeanInfo(objectName).getNotifications()\`.

Đừng giả định chỉ cần khai báo metadata là có event. MBean phải **thực sự gọi cơ chế phát**, chẳng hạn \`sendNotification\`, tại thời điểm phù hợp.

## 10. Metric và event xử lý cùng một tình huống

Giả sử cần cảnh báo khi số job đang chờ vượt 100.

**Cách chỉ polling:**

1. Dashboard đọc \`PendingCount\` 15 giây/lần.
2. Nếu lớn hơn 100 trong ba chu kỳ liên tiếp, phát cảnh báo.
3. Trạng thái kéo dài được phát hiện; spike quá ngắn có thể bị bỏ qua.

**Cách chỉ notification:**

1. Ứng dụng phát event khi count lần đầu vượt 100.
2. Listener có thể cảnh báo ngay.
3. Nếu listener vừa restart hoặc mất kết nối tại thời điểm event, nó có thể không nhận được tín hiệu. Không có snapshot mặc định để biết hiện tại count vẫn ở mức 130.

**Cách phối hợp:**

1. Duy trì \`PendingCount\` để dashboard và công cụ poll.
2. Phát notification khi crossing threshold.
3. Khi listener mới kết nối hoặc reconnect, đọc ngay \`PendingCount\` để lấy trạng thái hiện tại.
4. Khi nhận notification, có thể đọc lại attributes cần thiết để xác minh và cập nhật bảng điều khiển.
5. Dùng alert dựa trên metric để phát hiện tình trạng kéo dài và event alert để phản ứng với chuyển trạng thái.

Đây là cách phối hợp event-driven và state-based monitoring: notification giúp biết điều gì xảy ra, metric giúp biết hệ thống **đang ở trạng thái nào**.

## 11. Sự kiện cạnh biên và trạng thái kéo dài

Cần phân biệt:

- **Edge event:** “Queue vừa vượt ngưỡng” (chỉ phát ở thời điểm chuyển từ không vượt sang vượt).
- **Level/state:** “Queue hiện đang trên ngưỡng” (có thể đúng kéo dài nhiều phút).

Nếu chỉ phát event một lần khi crossing, listener đăng ký muộn sẽ không tự được “phát lại” trạng thái đã tồn tại. Metric polling phù hợp hơn để xác định trạng thái hiện tại.

Một số thiết kế bổ sung notification khi trạng thái được khôi phục:

\`\`\`text
com.example.shop.queue.threshold.exceeded
com.example.shop.queue.threshold.recovered
\`\`\`

Hai type giúp hệ thống thể hiện vòng đời của một incident. Tuy nhiên, dựa duy nhất vào cặp event có rủi ro khi mất một thông điệp; vì vậy vẫn cần snapshot metric hoặc cơ chế đồng bộ trạng thái khác.

Với các metric tốc độ hoặc counter tích lũy, notification nên liên quan những chuyển đổi trạng thái hoặc sự kiện quản trị thực sự cần hành động. Tránh phát một notification cho mỗi increment nếu tần suất có thể cực lớn.

## 12. Thread, tải hệ thống và xử lý listener

\`NotificationBroadcasterSupport\` có thể dùng một \`Executor\` để thực thi callback thay vì để callback chạy trực tiếp trên thread phát sự kiện. Lựa chọn này ảnh hưởng rõ tới latency, thứ tự thực thi và tải hệ thống.

Ví dụ dùng executor:

\`\`\`java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.management.NotificationBroadcasterSupport;

ExecutorService executor = Executors.newSingleThreadExecutor();

NotificationBroadcasterSupport broadcaster =
        new NotificationBroadcasterSupport(executor);

// Trong vòng đời đóng component:
// executor.shutdown();
\`\`\`

Ví dụ trên minh họa khả năng cấu hình executor qua constructor. Trong ứng dụng thật, quản lý lifecycle của executor cùng component và xử lý lỗi callback. Nếu event nhiều hơn tốc độ xử lý, hàng đợi executor có thể tăng. Với \`newSingleThreadExecutor()\`, hàng đợi mặc định không có giới hạn cố định nên cần cân nhắc backpressure và tài nguyên bộ nhớ. Đừng dùng một cơ chế queue vô hạn cho workload có thể phát event ồ ạt mà không có đánh giá tải.

Khi thiết kế notification:

- Giữ payload nhỏ và dễ hiểu.
- Không làm operation nghiệp vụ quan trọng phụ thuộc việc listener xử lý thành công.
- Đặt type rõ ràng; định nghĩa version nếu schema payload thay đổi không tương thích.
- Không đưa thông tin nhạy cảm vào message hoặc \`userData\`.
- Cân nhắc giới hạn tần suất thông báo (rate limit), debounce hoặc chỉ phát khi state transition.
- Theo dõi lỗi listener và khả năng kết nối từ client.

Notification có thể gây “event storm” nếu phát mỗi lần giá trị nhấp nhô quanh threshold. Có thể dùng **hysteresis**: phát exceeded khi trên 100, chỉ coi recovered khi xuống dưới 80, giúp tránh bật/tắt cảnh báo liên tục.

## 13. Sequence number, timestamp và tính tin cậy

### Sequence number

\`Notification.sequenceNumber\` giúp consumer theo dõi thứ tự các notification do một nguồn phát gửi. JMX không tự áp đặt cách bộ đếm được lưu bền vững hay bảo đảm consumer sẽ nhận mọi số liên tiếp. Sequence hữu ích để quan sát hoặc phát hiện gap có thể xảy ra, nhưng không phải bằng chứng tuyệt đối khi MBean restart/reset counter hay có nhiều nguồn.

Dùng \`AtomicLong.incrementAndGet()\` là một cách tạo sequence nhất quán trong một emitter. Không dùng \`System.currentTimeMillis()\` như sequence number nếu cần tính đơn điệu rõ ràng.

### Timestamp

\`timeStamp\` thường được gán lúc phát sự kiện, nhưng đó là giá trị từ clock được ứng dụng cung cấp. Nó không phải cam kết thời điểm client nhận event. Clock skew, độ trễ network hoặc queue executor làm hai thời điểm khác nhau.

### Delivery

JMX notification không mặc định hỗ trợ:

- Durable log tồn tại sau restart.
- Exactly-once delivery.
- Retry/acknowledgment ở cấp ứng dụng.
- Replay các sự kiện listener đã bỏ lỡ.

Trong kết nối remote JMX, quá trình nhận notification và reconnect còn chịu ảnh hưởng network/connector implementation. Nếu sự kiện mang tính nghiệp vụ bắt buộc không mất (ví dụ payment settlement), dùng message broker hoặc transactional outbox/durable queue theo yêu cầu hệ thống, rồi có thể phát JMX notification làm tín hiệu quan sát phụ trợ.

## 14. Notification trong Spring Framework

Spring Framework có tích hợp JMX để export bean thông qua \`MBeanExporter\` và annotation như \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`. Nó cũng hỗ trợ những cơ chế liên quan notification, chẳng hạn \`NotificationPublisher\` để bean được export phát JMX notification qua Spring.

Ví dụ khái niệm với một bean:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
        objectName = "com.example.shop.orders:type=Queue,name=outbox")
public class OutboxMonitor implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile int pendingCount;

    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }

    public void onThresholdExceeded(int count) {
        pendingCount = count;

        NotificationPublisher currentPublisher = publisher;
        if (currentPublisher != null) {
            Notification event = new Notification(
                    "com.example.shop.queue.threshold.exceeded",
                    this,
                    sequence.incrementAndGet(),
                    System.currentTimeMillis(),
                    "Outbox vượt ngưỡng: " + count
            );
            event.setUserData(count);
            currentPublisher.sendNotification(event);
        }
    }
}
\`\`\`

**Điều kiện sử dụng:** \`OutboxMonitor\` phải thực sự là Spring bean được export qua JMX bằng \`MBeanExporter\` với cấu hình có hỗ trợ annotation và notification publisher. Chỉ có annotation và \`NotificationPublisherAware\` trong class không tự làm MBean xuất hiện. \`onThresholdExceeded\` là method được ứng dụng gọi khi phát hiện trạng thái, không mặc nhiên là JMX operation.

Trong ứng dụng Spring Boot, tính năng JMX export có thể cần bật cấu hình thích hợp; đừng suy ra mọi \`@ManagedResource\` tự được export nếu phần JMX chưa được kích hoạt. Ngoài ra, \`NotificationPublisher\` trong Spring là API tích hợp JMX, **không đồng nghĩa** với \`ApplicationEventPublisher\` của Spring.

### So sánh Spring ApplicationEvent và JMX Notification

| | Spring ApplicationEvent | JMX Notification |
|---|---|---|
| Mục tiêu | Giao tiếp sự kiện trong ứng dụng Spring | Thông báo quản trị MBean |
| Publisher | \`ApplicationEventPublisher\` | \`NotificationPublisher\` hoặc JMX broadcaster |
| Consumer | \`@EventListener\`/\`ApplicationListener\` | JMX \`NotificationListener\` |
| Phạm vi thông thường | Application context | MBeanServer/JMX connector |
| Điểm mạnh | Tổ chức sự kiện giữa component | Tích hợp công cụ giám sát và quản trị Java |

Không nên phát JMX notification cho mọi event nghiệp vụ nội bộ. Chỉ công bố những sự kiện có ý nghĩa vận hành cho người quản trị.

## 15. Khi nào nên chọn cơ chế nào?

### Dùng metric polling khi

- Cần dashboard về CPU, memory, queue depth, thread count, cache size.
- Cần biểu đồ thời gian, trung bình, rate, xu hướng hoặc phân tích capacity.
- Muốn biết trạng thái ngay sau khi client kết nối/reconnect.
- Cần phát hiện một tình trạng kéo dài qua nhiều chu kỳ thu thập.
- Có hệ thống observability vốn lấy dữ liệu dạng pull.

### Dùng notification khi

- Cần biết thời điểm một trạng thái **chuyển** sang lỗi hoặc degraded.
- Có sự kiện quản trị không diễn ra thường xuyên nhưng đáng quan tâm.
- Muốn báo hệ thống giám sát rằng MBean vừa thay đổi cấu hình hoặc một ngưỡng đã bị vượt.
- Cần nhận thông tin về lifecycle như component stopped/restarted hoặc tài nguyên bị loại bỏ.
- MBean phát event với tần suất có thể kiểm soát.

### Kết hợp cả hai khi

- Sự kiện có ý nghĩa ngay lập tức nhưng vẫn phải hiển thị tình trạng hiện tại.
- Client có thể ngắt kết nối rồi quay lại.
- Cần vừa có realtime signal vừa có lịch sử time series.
- Muốn dùng notification để kích hoạt một lần đọc attribute tức thời, bên cạnh polling định kỳ.

Không nên chọn notification vì cho rằng “push luôn tốt hơn pull”. Nhu cầu, độ tin cậy, tần suất event và công cụ monitoring hiện có mới quyết định thiết kế phù hợp.

## 16. Các lỗi dễ gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Listener không nhận event | Chưa đăng ký, sai ObjectName hoặc filter không khớp | Kiểm tra \`addNotificationListener\`, notification type, \`getMBeanInfo\` |
| MBean có attribute nhưng không phát notification | MBean không triển khai emitter/broadcaster hoặc không gọi \`sendNotification\` | Kiểm tra luồng phát tại điều kiện sự kiện |
| MBean bị unregister khi listener còn dùng | Vòng đời registration/listener không nhất quán | Gắn cleanup với lifecycle và xử lý reconnect |
| Event bị lặp quá nhiều | Giá trị dao động quanh threshold hoặc emitter phát mỗi cập nhật | Dùng state transition/hysteresis/debounce |
| Có event nhưng dashboard không biết trạng thái mới nhất | Notification chỉ báo diễn biến, không phải snapshot liên tục | Đọc lại attribute và duy trì metric polling |
| Bỏ lỡ event trong lúc client offline | Notification không có durable replay mặc định | Reconnect + đọc trạng thái; dùng durable messaging nếu cần |
| Ứng dụng chậm khi phát event | Listener xử lý nặng hoặc executor quá tải | Tối ưu callback, giới hạn tải, cân nhắc executor |
| Client thấy type nhưng không nhận payload đúng | Metadata/payload khác nhau hoặc filter sai | Kiểm tra \`MBeanNotificationInfo\`, \`userData\`, compatibility |
| Nhầm event JMX với Spring event | Hai API và consumer khác nhau | Xác định rõ publisher/listener cần dùng |
| Ném exception khi invoke | Operation/attribute mapping hoặc logic cài đặt lỗi | Đọc \`MBeanInfo\` và stack trace phù hợp |

## 17. Bài tập thực hành

### Bài tập 1 — Polling có thể bỏ lỡ điều gì?

Queue có giá trị:

\`\`\`text
00s: 10
05s: 130
10s: 20
15s: 15
\`\`\`

Monitoring poll mỗi 15 giây. Hãy giải thích vì sao chuỗi metric có thể chỉ thấy 10 và 15, còn notification phát ở 05s có khả năng báo được sự kiện queue vượt 100.

**Gợi ý:** Metric polling lấy snapshot tại thời điểm đọc, còn event phản ánh lần chuyển trạng thái đã được phát. Khi listener offline, notification vẫn có thể bị bỏ lỡ.

### Bài tập 2 — Thiết kế MBean cho pool

Một pool kết nối có các số đo \`ActiveConnections\`, \`IdleConnections\`, \`MaxConnections\`. Khi không lấy được connection trong 3 giây, ứng dụng có thể phát \`com.example.shop.pool.acquire.timeout\`.

Hãy nêu:

1. Các số đo nào nên là attributes.
2. Loại notification và payload nhỏ nhất đủ cho vận hành.
3. Cách listener đăng ký và lọc theo prefix \`com.example.shop.pool.\`.
4. Cách dashboard cập nhật snapshot ngay sau khi reconnect.

### Bài tập 3 — Viết filter

Cho các type:

\`\`\`text
com.example.shop.queue.threshold.exceeded
com.example.shop.queue.threshold.recovered
com.example.shop.pool.acquire.timeout
\`\`\`

Viết \`NotificationFilterSupport\` chỉ nhận sự kiện thuộc queue.

Đáp án gợi ý:

\`\`\`java
NotificationFilterSupport filter =
        new NotificationFilterSupport();
filter.enableType("com.example.shop.queue.");
\`\`\`

### Bài tập 4 — Bổ sung recovery event

Mở rộng \`QueueMonitor\`:

- Phát \`threshold.exceeded\` khi pending tăng từ \`<= 100\` lên \`> 100\`.
- Phát \`threshold.recovered\` khi pending giảm từ \`>= 80\` xuống \`< 80\`, sau khi đã ở trạng thái cảnh báo.
- Giữ \`PendingCount\` là attribute để client vẫn đọc được trạng thái hiện tại.

Mục tiêu là tránh spam notification khi queue dao động quanh ngưỡng.

### Bài tập 5 — Xử lý listener đăng ký muộn

Thêm một listener sau khi queue đã ở mức 120. Hãy xác định liệu listener có tự nhận notification crossing trước đó không, rồi đọc \`PendingCount\` để đồng bộ trạng thái. Đề xuất một chiến lược reconnect vừa lấy snapshot vừa theo dõi event mới.

## 18. Câu hỏi tự kiểm tra

**1. JMX Notification có phải một metric không?**

Không. Notification là thông điệp về sự kiện; metric thường là giá trị thuộc tính hoặc chuỗi số đo theo thời gian.

**2. Nếu không có event, notification listener có biết queue vẫn bình thường không?**

Không chắc. Nó chỉ biết những event đã nhận. Muốn xác định trạng thái hiện tại cần đọc attribute hoặc dùng cơ chế đồng bộ khác.

**3. Nếu collector poll mỗi 1 phút, một spike kéo dài 2 giây có thể bị bỏ qua không?**

Có. Nếu spike nằm hoàn toàn giữa hai mẫu và attribute chỉ hiển thị giá trị hiện tại, polling có thể không thấy. Notification có thể báo nếu ứng dụng phát event phù hợp.

**4. \`NotificationBroadcasterSupport\` có mặc định lưu bền event để client offline nhận lại không?**

Không. Nó quản lý việc gửi tới listeners, không tự cung cấp durable log/replay.

**5. \`NotificationFilterSupport.enableType\` so sánh loại sự kiện thế nào?**

Nó cho phép các notification có type bắt đầu bằng prefix đã bật.

**6. \`NotificationPublisher\` của Spring JMX có giống \`ApplicationEventPublisher\` không?**

Không. Một API phát JMX notifications, API kia phát Spring application events.

**7. Nếu đã có notification thì có bỏ metric polling được không?**

Không nên mặc định bỏ. Notification giúp phản ứng với sự kiện, trong khi metric cung cấp snapshot và phục vụ truy vấn lịch sử.

## 19. Tổng kết

- **Notification là tín hiệu sự kiện** được MBean phát cho listener đã đăng ký; polling là việc client **đọc trạng thái định kỳ** từ các JMX attributes.
- Notification phù hợp với state transitions, threshold crossing, lỗi hoặc diễn biến quản trị hiếm nhưng đáng chú ý.
- Polling phù hợp với trạng thái hiện tại, dashboard, trends, rate và phát hiện điều kiện kéo dài.
- JMX notification có metadata \`type\`, \`source\`, \`sequenceNumber\`, \`timeStamp\`, \`message\`, \`userData\`; broadcaster và listener phối hợp phát/nhận sự kiện.
- Không có durable delivery, acknowledgement hay replay mặc định. Nếu listener kết nối muộn, nên đọc metric để đồng bộ trạng thái.
- Spring Framework có tích hợp \`NotificationPublisher\`, nhưng phải cấu hình xuất bean và không nhầm với \`ApplicationEventPublisher\`.
- Mô hình thực tế thường kết hợp **metric để quan sát state** và **notification để báo event**, kèm xử lý reconnect, lọc, tải và lifecycle listener.

## 20. Tài liệu tham khảo

- Java SE 21 — \`javax.management.Notification\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE 21 — \`javax.management.NotificationBroadcasterSupport\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 — \`javax.management.NotificationListener\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE 21 — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Oracle JMX Tutorial — Notifications: https://docs.oracle.com/javase/tutorial/jmx/notifs/
- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
