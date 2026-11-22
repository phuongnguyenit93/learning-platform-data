# NotificationListener, NotificationFilter và handback trong JMX

## 1. Từ quan sát thụ động đến nhận sự kiện chủ động

Trong Java Management Extensions (JMX), một công cụ quản trị thường đọc trạng thái bằng `MBeanServerConnection.getAttribute(...)`: bộ nhớ đã dùng, số thread, số kết nối đang hoạt động, số lỗi xử lý. Cách đó thích hợp để lấy **ảnh chụp trạng thái**, nhưng có một hạn chế rõ ràng: muốn biết trạng thái đã thay đổi hay chưa, client phải chủ động hỏi lại.

Giả sử một hàng đợi xử lý tác vụ có `QueueDepth` và `Capacity`. Người vận hành cần biết ngay khi hàng đợi vượt ngưỡng, một tác vụ thất bại nghiêm trọng hoặc cấu hình runtime bị thay đổi. Nếu chỉ polling, công cụ phải chọn chu kỳ lấy mẫu, chấp nhận độ trễ và có thể bỏ lỡ sự kiện ngắn nằm giữa hai lần đọc.

JMX cung cấp **Notification**: MBean hoặc thành phần phát sự kiện (*notification broadcaster*) gửi một đối tượng `Notification` đến các bên đã đăng ký nhận. Để kiểm soát việc xử lý thông báo, JMX có ba khái niệm cốt lõi:

- **`NotificationListener`**: nơi nhận thông báo; callback được gọi khi có notification phù hợp.
- **`NotificationFilter`**: quyết định notification nào được chuyển tới listener trong một đăng ký.
- **`handback`**: đối tượng ngữ cảnh do bên đăng ký cung cấp, được trả lại nguyên tham chiếu cho callback; nó không phải dữ liệu do MBean phát ra.

Cả ba phối hợp trong một registration tại MBeanServer. Một listener có thể được đăng ký nhiều lần với các filter và handback khác nhau, giúp cùng một đoạn xử lý được sử dụng cho nhiều nguồn hoặc nhiều ngữ cảnh vận hành.

```text
                 Ứng dụng Java / MBean
                      |
          xảy ra sự kiện cần quản trị
                      |
              NotificationEmitter
                      |
                  Notification
                      |
             MBeanServer / JMX
                      |
     +----------------+----------------+
     |                                 |
Registration A                    Registration B
listener L + filter F1            listener L + filter F2
handback "critical"               handback "audit"
     |                                 |
filter cho phép?                    filter cho phép?
     |                                 |
handleNotification(n, "critical")  handleNotification(n, "audit")
```

Mô hình trên cho thấy **notification là dữ liệu sự kiện**, **filter là điều kiện chọn sự kiện** và **handback là ngữ cảnh của việc đăng ký**. Những khái niệm này độc lập với phương thức kinh doanh của ứng dụng.

## 2. Notification chứa những thông tin nào?

`javax.management.Notification` là lớp cơ bản cho thông báo JMX. Một notification điển hình có các thuộc tính sau:

| Thuộc tính | Vai trò |
|---|---|
| `type` | Chuỗi phân loại sự kiện, thường theo quy ước tên miền, ví dụ `demo.queue.threshold.exceeded` |
| `source` | Đối tượng hoặc tên nguồn phát notification |
| `sequenceNumber` | Số thứ tự do bên phát gán |
| `timeStamp` | Thời điểm sự kiện, theo milliseconds từ Unix epoch |
| `message` | Mô tả dễ đọc, có thể trống |
| `userData` | Payload mở rộng do ứng dụng đặt, nếu có |

Ví dụ tạo một sự kiện:

```java
Notification notification = new Notification(
    "demo.queue.threshold.exceeded",
    sourceObject,
    nextSequenceNumber,
    System.currentTimeMillis(),
    "Queue depth crossed warning threshold"
);
notification.setUserData("queue=orders, depth=85");
```

`type` là khóa phân loại do hợp đồng phát sự kiện quy định. Trong một hệ thống có nhiều notification, việc thiết kế type ổn định giúp filter lựa chọn chính xác. `message` giúp con người hiểu nhanh nhưng không nên là tiêu chí xử lý tự động nếu có một `type` có cấu trúc rõ ràng.

**Sequence number là số do nguồn phát quản lý**, không phải số thứ tự toàn cục giữa mọi MBean. Nó hữu ích để kiểm tra trình tự đối với một nguồn trong một giai đoạn hoạt động, nhưng không mặc nhiên chứng minh rằng tất cả thông báo trên mạng đều đã được nhận hay không có trùng lặp. Một sequence có thể khởi động lại khi MBean/JVM được tạo lại.

**Timestamp không thay thế đồng hồ logic hoặc sắp xếp phân tán**: giữa nhiều JVM có thể có sai lệch đồng hồ, độ trễ truyền và khác biệt xử lý. Khi cần truy vết nghiêm ngặt, kết hợp notification với log, correlation ID và hệ thống lưu sự kiện phù hợp.

## 3. NotificationListener: điểm nhận và xử lý sự kiện

Giao diện `javax.management.NotificationListener` có một phương thức:

```java
void handleNotification(Notification notification, Object handback);
```

Tham số đầu là notification thực tế do nguồn phát tạo. Tham số thứ hai là **handback** đã được cung cấp lúc đăng ký listener. Callback có thể nhận nhiều loại notification; vì thế thường cần đọc `notification.getType()` hoặc dữ liệu trong payload trước khi xử lý.

Ví dụ:

```java
import javax.management.Notification;
import javax.management.NotificationListener;

public final class LoggingListener implements NotificationListener {
    @Override
    public void handleNotification(Notification notification, Object handback) {
        System.out.printf(
            "[%s] type=%s, source=%s, sequence=%d, message=%s%n",
            handback,
            notification.getType(),
            notification.getSource(),
            notification.getSequenceNumber(),
            notification.getMessage()
        );
    }
}
```

Listener không tự tìm ra nguồn nào cần theo dõi. Cần đăng ký listener với một broadcaster, trực tiếp hoặc qua MBeanServer:

```java
server.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
```

Khi một notification đủ điều kiện theo filter, JMX chuyển notification và handback tương ứng vào callback.

### 3.1. Có thể đăng ký listener ở đâu?

Nếu code có tham chiếu tới một đối tượng `NotificationEmitter` local, có thể đăng ký trực tiếp bằng `emitter.addNotificationListener(listener, filter, handback)`.

Với MBean đã được đăng ký trên `MBeanServer`, dùng `MBeanServer.addNotificationListener(ObjectName, NotificationListener, NotificationFilter, Object)`. Client JMX từ xa có thể dùng API tương ứng trên `MBeanServerConnection`.

Việc đăng ký chỉ hợp lệ khi đối tượng nguồn hỗ trợ phát notification. Nếu MBean không có khả năng broadcaster/emitter tương ứng, thao tác đăng ký có thể thất bại với `RuntimeOperationsException` hoặc exception JMX phù hợp tùy trường hợp. Một getter thay đổi giá trị không có nghĩa MBean đó tự phát notification.

### 3.2. Callback nên làm gì?

Callback là code chạy khi JMX chuyển sự kiện. Nó nên thực hiện thao tác ngắn và được kiểm soát:

- Kiểm tra `type`, `source` và payload cần thiết.
- Chuyển sự kiện sang bộ xử lý khác nếu việc xử lý tốn thời gian.
- Ghi log với thông tin có ích, không ghi bí mật.
- Bảo vệ code callback trước exception do dữ liệu bất thường.
- Tránh gọi các operation nguy hiểm hoặc blocking kéo dài chỉ vì nhận notification.

Không nên mặc định một mô hình thread duy nhất cho mọi broadcaster hoặc connector. Với `NotificationBroadcasterSupport`, hành vi phân phối có thể phụ thuộc `Executor` được cấu hình. Với remote JMX, connector cũng ảnh hưởng thời điểm callback xuất hiện. Đừng thiết kế callback dựa trên giả định luôn được gọi trên một thread nghiệp vụ cụ thể.

## 4. NotificationFilter: kiểm soát thông báo nào được chuyển tới listener

`javax.management.NotificationFilter` là functional interface theo ý nghĩa thực hành: nó có phương thức `boolean isNotificationEnabled(Notification notification)`.

```java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter onlyCritical = notification ->
    notification != null
        && "demo.queue.critical".equals(notification.getType());
```

Khi đăng ký:

```java
server.addNotificationListener(
    objectName,
    listener,
    onlyCritical,
    "critical-channel"
);
```

Nếu filter trả `true`, notification được phép đi tiếp tới listener. Nếu trả `false`, registration đó không nhận notification. **Filter hoạt động theo từng registration**, không nhất thiết chặn một notification được gửi đến các listener khác. Một notification có thể được chuyển tới nhiều listener nếu các filter tương ứng cùng chấp nhận.

Truyền `null` làm filter nghĩa là không yêu cầu lọc theo registration: listener có thể nhận mọi notification broadcaster phát ra cho đăng ký đó.

### 4.1. NotificationFilterSupport

JMX cung cấp `javax.management.NotificationFilterSupport` để lọc dựa trên tiền tố của notification type:

```java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("demo.queue.");
```

Filter trên chấp nhận type bắt đầu bằng `demo.queue.`, ví dụ:

```text
demo.queue.warning
demo.queue.critical
demo.queue.recovered
```

và không chấp nhận `demo.cache.evicted`.

**Lưu ý:** `enableType("demo.queue.")` là **so khớp tiền tố**, không phải regex và không nhất thiết là một phép so khớp toàn chuỗi. Nếu chỉ muốn nhận đúng một type, dùng `NotificationFilter` tự viết hoặc logic so sánh chính xác.

`NotificationFilterSupport` còn có `disableType(...)`, `disableAllTypes()` và `getEnabledTypes()` để quản lý các tiền tố được bật. Vì quy tắc là tiền tố, một type chung như `demo.` có thể mở rộng phạm vi sự kiện nhiều hơn dự tính.

### 4.2. Filter tùy biến theo nội dung

Khi yêu cầu lọc vượt quá type, có thể kiểm tra `userData` hoặc thuộc tính notification:

```java
NotificationFilter highSequenceOnly = notification ->
    notification != null
        && "demo.queue.warning".equals(notification.getType())
        && notification.getSequenceNumber() >= 100;
```

Điều kiện trên chỉ là ví dụ kỹ thuật. Trên thực tế, sequence number không đại diện cho độ nghiêm trọng của cảnh báo, nên muốn lọc theo severity hãy cung cấp trường severity rõ ràng trong hợp đồng sự kiện.

Filter nên đơn giản, nhanh và tránh tác dụng phụ. Một filter gọi database hoặc thay đổi trạng thái có thể làm luồng phát sự kiện bị chậm, tùy mô hình dispatch. Nếu cần phân tích phức tạp, nhận sự kiện đơn giản rồi đưa sang pipeline xử lý phù hợp.

## 5. Handback: ngữ cảnh của một lần đăng ký

Handback thường bị hiểu nhầm là dữ liệu gửi kèm notification. Thực tế, đó là **đối tượng do bên đăng ký listener chọn và truyền vào lúc đăng ký**, sau đó JMX đưa lại cho listener khi callback được gọi.

```java
Object handback = "operations-dashboard";

server.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
```

Trong callback:

```java
@Override
public void handleNotification(Notification notification, Object handback) {
    System.out.println("Subscription context: " + handback);
}
```

Khác biệt quan trọng:

| Trường dữ liệu | Ai cung cấp? | Gắn với |
|---|---|---|
| `notification.getUserData()` | Bên phát sự kiện | Chính notification |
| `notification.getSource()` | Bên phát sự kiện/JMX có thể chuẩn hóa qua MBeanServer | Nguồn phát sự kiện |
| `handback` | Bên đăng ký listener | Registration cụ thể |
| `notification.getType()` | Bên phát sự kiện | Loại sự kiện |

Một broadcaster phát cùng một notification cho hai registration, nhưng mỗi registration có thể nhận một handback khác nhau. Điều này rất tiện khi một listener class được tái sử dụng:

```java
LoggingListener shared = new LoggingListener();

server.addNotificationListener(
    objectName, shared, warningFilter, "dashboard"
);
server.addNotificationListener(
    objectName, shared, criticalFilter, "pager"
);
```

Nếu một notification được cả hai filter chấp nhận, callback có thể được gọi hai lần với hai handback khác nhau. Đừng giả định “một notification chỉ tạo một callback” khi cùng listener đã được đăng ký nhiều lần.

### 5.1. Handback có thể là đối tượng bất kỳ không?

Trong đăng ký local, handback có thể là một đối tượng Java thông thường mà listener dùng làm ngữ cảnh, ví dụ một record:

```java
public record ListenerContext(String channel, String component) {}

ListenerContext context =
    new ListenerContext("dashboard", "orders");
```

Với remote notification, chi tiết xử lý handback phụ thuộc cách connector quản lý registration; theo mô hình JMX connector chuẩn, handback được giữ ở phía client để chuyển vào callback của client, nên không nên mặc định coi handback là payload được gửi đến server. Vì thế, tránh đặt dữ liệu nhạy cảm hoặc tham chiếu tài nguyên nặng vào handback nếu không cần.

Handback có thể là `null`; listener phải xử lý trường hợp đó. Nếu sử dụng đối tượng mutable làm handback, nhiều callback có thể quan sát trạng thái đã thay đổi. Nên dùng context bất biến khi muốn hành vi dự đoán được.

### 5.2. Handback không phải cơ chế định danh an toàn

Không dùng giá trị handback để thay thế authentication/authorization hoặc để mặc nhiên tin rằng một sự kiện là đáng tin cậy. Nó chỉ là tham số ngữ cảnh của code đăng ký, không phải chứng nhận nguồn sự kiện hay quyền thao tác.

## 6. Ví dụ Java hoàn chỉnh: broadcaster, listener, filter và handback

Ví dụ này minh họa một MBean theo dõi độ sâu hàng đợi. Khi độ sâu vượt ngưỡng, MBean phát một notification; hai registration sử dụng cùng listener với filter và handback khác nhau.

### 6.1. Định nghĩa giao diện MBean

```java
// QueueMonitorMBean.java
public interface QueueMonitorMBean {
    int getDepth();
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
    void updateDepth(int depth);
}
```

Các getter/setter tạo attribute quản trị; `updateDepth` là operation. Một ứng dụng thực có thể chỉ cho code nội bộ gọi update và không export operation này; trong ví dụ, nó được công bố để dễ thử qua JMX client.

### 6.2. Implement MBean có khả năng phát notification

```java
// QueueMonitor.java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    public static final String WARNING = "demo.queue.warning";
    public static final String CRITICAL = "demo.queue.critical";

    private final AtomicLong sequence = new AtomicLong();
    private volatile int depth;
    private volatile int warningThreshold = 70;

    @Override
    public int getDepth() {
        return depth;
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int threshold) {
        if (threshold < 1 || threshold > 100) {
            throw new IllegalArgumentException(
                "WarningThreshold must be 1..100"
            );
        }
        warningThreshold = threshold;
    }

    @Override
    public void updateDepth(int newDepth) {
        if (newDepth < 0) {
            throw new IllegalArgumentException("Depth cannot be negative");
        }

        depth = newDepth;

        if (newDepth >= warningThreshold) {
            String type = newDepth >= 90 ? CRITICAL : WARNING;

            Notification notification = new Notification(
                type,
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Queue depth changed to " + newDepth
            );
            notification.setUserData(newDepth);
            sendNotification(notification);
        }
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {WARNING, CRITICAL};
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                Notification.class.getName(),
                "Queue depth threshold notifications"
            )
        };
    }
}
```

Ở đây `NotificationBroadcasterSupport` cung cấp bộ máy đăng ký/gỡ listener và phát notification. Nó hỗ trợ `NotificationEmitter`, nên khi được đăng ký dưới dạng MBean thích hợp, client có thể đăng ký listener qua MBeanServer.

`getNotificationInfo()` công bố metadata mô tả các notification type mà MBean có thể phát. Metadata hỗ trợ công cụ khám phá khả năng phát sự kiện; nó không tự thực hiện gửi thông báo. Chỉ khi `sendNotification(...)` được gọi thì thông báo mới được phát.

Ví dụ trên phát notification mỗi khi `updateDepth` nhận một giá trị **đang trên ngưỡng**, kể cả khi trước đó cũng đã trên ngưỡng. Đây là lựa chọn minh họa. Hệ thống thật có thể cần phát chỉ khi **vượt qua ngưỡng**, có cơ chế chống lặp (debounce), giới hạn tần suất và sự kiện hồi phục.

### 6.3. Đăng ký hai luồng quan sát

```java
// Main.java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationFilter;
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class Main {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        QueueMonitor monitor = new QueueMonitor();

        ObjectName name =
            new ObjectName("demo.queue:type=QueueMonitor,name=orders");
        server.registerMBean(monitor, name);

        NotificationListener listener = (notification, handback) -> {
            System.out.printf(
                "channel=%s | type=%s | seq=%d | depth=%s%n",
                handback,
                notification.getType(),
                notification.getSequenceNumber(),
                notification.getUserData()
            );
        };

        NotificationFilterSupport warnings = new NotificationFilterSupport();
        warnings.enableType("demo.queue.warning");
        warnings.enableType("demo.queue.critical");

        NotificationFilter onlyCritical =
            notification -> QueueMonitor.CRITICAL.equals(
                notification.getType()
            );

        server.addNotificationListener(
            name, listener, warnings, "dashboard"
        );
        server.addNotificationListener(
            name, listener, onlyCritical, "pager"
        );

        monitor.updateDepth(40); // Không phát.
        monitor.updateDepth(75); // Dashboard nhận WARNING.
        monitor.updateDepth(95); // Dashboard và Pager đều nhận CRITICAL.

        server.removeNotificationListener(
            name, listener, warnings, "dashboard"
        );
        server.removeNotificationListener(
            name, listener, onlyCritical, "pager"
        );

        server.unregisterMBean(name);
    }
}
```

Khi chạy, kết quả điển hình:

```text
channel=dashboard | type=demo.queue.warning | seq=1 | depth=75
channel=dashboard | type=demo.queue.critical | seq=2 | depth=95
channel=pager     | type=demo.queue.critical | seq=2 | depth=95
```

Thứ tự của hai callback nhận `CRITICAL` có thể phụ thuộc cơ chế dispatch; không nên lấy thứ tự dòng log làm cam kết giữa nhiều listener. Điểm cần quan sát là **cùng notification có thể được phân phối đến nhiều registration với handback khác nhau**.

## 7. Quản lý vòng đời: đăng ký và gỡ listener

Listener cần được quản lý lifecycle để không gây rò rỉ đăng ký hoặc tiếp tục xử lý sự kiện sau khi thành phần nhận đã dừng.

JMX cung cấp hai nhóm thao tác gỡ listener:

```java
// Gỡ tất cả registration khớp listener trên MBean này:
server.removeNotificationListener(name, listener);

// Gỡ đúng registration theo listener, filter và handback:
server.removeNotificationListener(name, listener, filter, handback);
```

Với trường hợp cùng listener được đăng ký nhiều lần, phiên bản có `filter` và `handback` phù hợp khi muốn gỡ chính xác từng subscription. API so khớp đối tượng filter và handback theo identity của registration; nên giữ lại tham chiếu đã sử dụng lúc đăng ký, tránh tạo filter/context mới trông giống nhau rồi mong lệnh gỡ khớp.

Sau khi gỡ, các callback đã được dispatch trước đó có thể vẫn đang chạy tùy thực thi và connector. Nếu lifecycle yêu cầu ngừng xử lý triệt để, listener cũng cần kiểm soát trạng thái đóng và công việc đang thực hiện.

Một pattern đơn giản:

```java
final class ManagedRegistration implements AutoCloseable {
    private final MBeanServer server;
    private final ObjectName name;
    private final NotificationListener listener;
    private final NotificationFilter filter;
    private final Object handback;

    ManagedRegistration(
            MBeanServer server,
            ObjectName name,
            NotificationListener listener,
            NotificationFilter filter,
            Object handback) throws Exception {
        this.server = server;
        this.name = name;
        this.listener = listener;
        this.filter = filter;
        this.handback = handback;
        server.addNotificationListener(name, listener, filter, handback);
    }

    @Override
    public void close() throws Exception {
        server.removeNotificationListener(
            name, listener, filter, handback
        );
    }
}
```

Ở code production, chữ ký exception nên cụ thể hơn khi cần, và nếu khởi tạo nhiều resource thì giải phóng theo thứ tự ngược. `AutoCloseable` cho phép đặt registration trong `try-with-resources` để giảm nguy cơ quên cleanup.

## 8. Một listener, nhiều registration và nguy cơ xử lý trùng

Hãy xét cấu hình:

```java
NotificationListener listener = new LoggingListener();

server.addNotificationListener(name, listener, null, "all");
server.addNotificationListener(name, listener, criticalOnly, "critical");
```

Một notification loại `critical` phù hợp với cả hai đăng ký. Listener có thể nhận **hai callback cho cùng notification**:

```text
Notification #42
  -> registration ("all")      -> callback(notification #42, "all")
  -> registration ("critical") -> callback(notification #42, "critical")
```

Không thể dựa vào `NotificationListener` instance để suy ra mỗi notification chỉ được xử lý một lần. Nếu downstream cần loại trùng, hãy thiết kế khóa định danh phù hợp theo nguồn + sequence + vòng đời phát, hoặc một event ID ứng dụng, rồi kiểm tra idempotency.

Bản thân `handback` thường được dùng để phân luồng: cùng listener có thể gửi notification đến dashboard, audit logger hoặc pipeline cảnh báo khác nhau. Tuy nhiên, nếu handback chỉ là chuỗi `"critical"`, nó là ngữ cảnh routing do client định nghĩa, không phải severity đã được server xác thực.

## 9. Notification và cơ chế giám sát khác

| Cơ chế | Cách nhận dữ liệu | Phù hợp với |
|---|---|---|
| JMX attribute | Client chủ động đọc | Trạng thái/số đo tức thời |
| JMX notification | Nguồn phát chủ động gửi sự kiện | Thay đổi trạng thái, cảnh báo runtime |
| Log | Ứng dụng ghi bản ghi sự kiện | Chẩn đoán và lịch sử theo log pipeline |
| Metrics/alert | Thu thập, lưu số liệu và đánh giá điều kiện | Dashboard, xu hướng và cảnh báo theo thời gian |
| Message broker | Publish/subscribe bền vững tùy cấu hình | Tích hợp sự kiện giữa dịch vụ, xử lý bất đồng bộ |

JMX notification rất hữu ích cho sự kiện quản trị JVM/MBean, nhưng **không nên mặc định nó là hàng đợi sự kiện bền vững**. Remote connection có thể mất; listener có thể ngắt; callback có thể không xử lý kịp. Nếu ứng dụng cần replay, retry có kiểm soát, dead-letter queue, giao dịch hoặc bảo đảm giao nhận giữa nhiều dịch vụ, hãy sử dụng cơ chế messaging phù hợp thay vì coi JMX Notification là message broker.

Người vận hành thường kết hợp notification với việc đọc lại attribute để xác minh trạng thái hiện tại. Ví dụ notification báo “queue vượt 70” cho biết ngưỡng đã bị chạm tại thời điểm phát; tại thời điểm client xử lý, `QueueDepth` có thể đã giảm xuống.

## 10. Ghi chú về remote JMX

Khi client ở tiến trình khác, `MBeanServerConnection` là giao diện thao tác từ xa. Listener có thể được đăng ký bằng:

```java
MBeanServerConnection connection = connector.getMBeanServerConnection();

connection.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
```

Trong đó `connector` là một `JMXConnector` đã kết nối hợp lệ, `objectName` trỏ đến MBean hỗ trợ notifications.

Một số lưu ý:

1. **Remote JMX phải được bảo vệ** bằng xác thực, TLS khi phù hợp, giới hạn mạng và quyền truy cập quản trị.
2. Connection hoặc session có thể đứt; client cần chiến lược phát hiện mất kết nối, reconnect và đăng ký lại listener nếu cần.
3. Không kỳ vọng notification bị bỏ lỡ trong thời gian ngắt kết nối sẽ tự replay. Nếu cần lịch sử, lưu sự kiện hoặc trạng thái ở nơi khác.
4. Payload `userData` đi qua connector phải tương thích với cơ chế truyền/serialization của connector và kiểu dữ liệu phía client. Không gửi object graph lớn, mutable hoặc chứa bí mật.
5. Notification phải được xử lý như dữ liệu từ một kênh quản trị có thể lỗi, trễ hoặc bị phân quyền giới hạn; callback không nên mặc định mọi sự kiện đều đến đủ và đúng thứ tự giữa các nguồn.
6. `handback` do phía đăng ký cung cấp là ngữ cảnh callback, không phải giải pháp để gửi bí mật hoặc tham số nghiệp vụ từ client sang server.

Một hệ thống cần cảnh báo critical có thể dùng JMX Notification như một tín hiệu đầu vào rồi chuyển tới alert pipeline có lưu vết và chống trùng. Đừng để thành công của một callback là bằng chứng duy nhất rằng sự cố đã được xử lý.

## 11. Spring Framework tích hợp ra sao?

Trong Spring, MBean vẫn tuân theo các nguyên tắc JMX của Java: có nguồn phát `NotificationEmitter`, MBeanServer, các listener và registration. Spring Framework cung cấp những lớp hỗ trợ export MBean và đăng ký listener, giúp quản lý lifecycle bằng container.

Một ứng dụng có thể:

- Export một bean đã triển khai giao diện MBean và khả năng phát notification.
- Dùng `MBeanExporter` để đưa bean vào `MBeanServer`.
- Cấu hình listener qua cơ chế `NotificationListenerBean` hoặc cấu hình listener mapping phù hợp với phiên bản Spring Framework đang dùng.

Ví dụ ý tưởng đăng ký trong ứng dụng Spring:

```java
import javax.management.Notification;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    if ("demo.queue.critical".equals(notification.getType())) {
        System.out.println("Critical queue notification: " +
            notification.getMessage());
    }
};
```

Code này mới là **listener**, chưa tự đăng ký với MBean. Ứng dụng phải liên kết listener với MBean có thể phát thông báo bằng MBeanServer/Spring exporter hoặc cấu hình tương ứng. Nếu dùng custom filter và handback, cần bảo đảm cấu hình cuối cùng truyền đúng các tham số khi đăng ký, đồng thời gỡ đăng ký khi context ngừng hoạt động.

**Không nhầm Spring ApplicationEvent với JMX Notification:** ApplicationEvent là cơ chế publish/subscribe trong Spring application context; JMX Notification là sự kiện trên bề mặt quản trị của JMX và có thể được quan sát bởi JMX clients. Nếu muốn chuyển đổi giữa hai loại, cần code kết nối rõ ràng.

Trong các ứng dụng Spring Boot, cấu hình export JMX có thể phụ thuộc `spring.jmx.enabled` và auto-configuration. Việc một bean tồn tại trong ApplicationContext không đảm bảo JMX client nhìn thấy notification của bean đó.

## 12. Các lỗi thường gặp

### 12.1. Đã tạo Notification nhưng listener không chạy

Kiểm tra nguồn có thực sự gọi `sendNotification(...)`, MBean đã đăng ký đúng ObjectName chưa, listener đã được đăng ký với đúng nguồn chưa và filter có cho phép type đó không. Chỉ override `getNotificationInfo()` để khai báo metadata không tự gửi sự kiện.

### 12.2. Dùng NotificationFilterSupport như regex

```java
filter.enableType("demo.queue.*");
```

Câu lệnh trên tìm **tiền tố literal** `demo.queue.*`, không có ý nghĩa wildcard. Muốn nhận mọi type bắt đầu `demo.queue.`, dùng:

```java
filter.enableType("demo.queue.");
```

### 12.3. Nhầm userData với handback

`userData` là một phần notification do broadcaster gán. `handback` là ngữ cảnh do subscriber cung cấp khi đăng ký. Nếu hai listener có handback khác nhau, cùng notification vẫn có cùng userData mà mỗi callback nhận handback riêng.

### 12.4. Cùng listener nhận hai lần

Khi listener đăng ký trùng hoặc được đăng ký với hai filter cùng match, một notification có thể kích hoạt nhiều callback. Kiểm tra danh sách subscription và logic routing trước khi kết luận broadcaster phát hai lần.

### 12.5. removeNotificationListener không gỡ được

Kiểm tra ObjectName, listener instance và cặp filter/handback. Đặc biệt, khi dùng overload gỡ chính xác registration, phải dùng lại tham chiếu đã lưu. Một lambda mới có logic giống hệt vẫn là listener/filter object khác.

### 12.6. Callback gây chậm cả hệ thống

Nếu listener xử lý blocking trên cơ chế dispatch đồng bộ, luồng phát có thể bị chậm. Đưa xử lý nặng sang executor hoặc queue có giới hạn, theo dõi backlog và quy định chính sách khi quá tải. Khi dùng asynchronous executor, cần xử lý lỗi, thứ tự và shutdown cẩn thận.

### 12.7. Dùng notification như log lịch sử đầy đủ

JMX không tự bảo đảm lưu mọi notification và phát lại sau khi client reconnect. Muốn điều tra lịch sử, gửi sự kiện tới log/event store có thời gian lưu và truy vấn phù hợp.

## 13. Thực hành theo tình huống

**Tình huống A — chỉ nhận sự kiện critical.** Một MBean phát ba type:

```text
demo.queue.warning
demo.queue.critical
demo.queue.recovered
```

Yêu cầu: tạo `NotificationFilter` chỉ nhận đúng `demo.queue.critical` và truyền handback `"oncall"`. Trong listener, log `type`, `sequenceNumber`, `message` và handback. Thử phát cả ba type để quan sát kết quả.

**Tình huống B — một listener xử lý nhiều nhóm.** Đăng ký cùng một listener với hai filter: một filter nhận `demo.queue.`, một filter nhận `demo.cache.`. Handback lần lượt là `"queue-dashboard"` và `"cache-dashboard"`. Giải thích vì sao handback nên là context bất biến và cách gỡ từng registration riêng.

**Tình huống C — hạn chế notification lặp.** Một queue có depth thay đổi `65 -> 72 -> 80 -> 95 -> 85 -> 65` và ngưỡng warning 70, critical 90. Thiết kế quy tắc phát **khi chuyển trạng thái** `NORMAL/WARNING/CRITICAL`, thêm notification recovery, và mô tả vì sao cách này giảm số notification hơn phát mỗi lần cập nhật depth.

**Tình huống D — mất kết nối remote.** Client đăng ký listener rồi ngắt kết nối 30 giây. Trong thời gian đó, server phát ba notification. Hãy giải thích vì sao không thể tự kết luận client sẽ nhận đủ ba, và đề xuất đọc lại attribute sau reconnect để đồng bộ trạng thái hiện tại.

**Tình huống E — quan sát metadata.** Dùng `MBeanServer.getMBeanInfo(objectName).getNotifications()` để in các notification type mà MBean tuyên bố hỗ trợ. So sánh danh sách type với filter mà client đăng ký; thử tạo notification type không nằm trong metadata và thảo luận vì sao metadata nên chính xác với hợp đồng thực tế.

## 14. Câu hỏi tự kiểm tra

1. `NotificationListener.handleNotification` nhận hai tham số gì, chúng đến từ đâu?
2. `NotificationFilter.isNotificationEnabled(...)` quyết định phạm vi lọc ở mức notification hay ở mức một registration?
3. Truyền `null` vào vị trí filter có nghĩa là gì?
4. `NotificationFilterSupport.enableType` so khớp tiền tố hay so khớp toàn chuỗi/regex?
5. Một notification có thể gọi cùng listener hai lần không? Khi nào?
6. Vì sao handback không nên được coi là `userData`?
7. Hai overload của `removeNotificationListener` khác nhau ở đâu?
8. MBean có `getNotificationInfo()` nhưng không gọi `sendNotification()` thì chuyện gì xảy ra?
9. Remote JMX Notification có đảm bảo replay sau mất kết nối không?
10. JMX Notification và Spring `ApplicationEvent` khác nhau về bề mặt sử dụng ra sao?

## 15. Ghi nhớ cốt lõi

**Notification** là thông tin sự kiện được nguồn JMX phát ra. **NotificationListener** định nghĩa hành vi nhận và xử lý, **NotificationFilter** xác định một registration được nhận loại notification nào, còn **handback** mang ngữ cảnh do bên đăng ký tự gán và được trả lại khi callback chạy.

Ba thành phần tạo nên một cơ chế push event gọn cho việc quản trị JVM/MBean. Để vận hành đáng tin cậy, hãy đặt tên notification type ổn định, lọc chính xác, quản lý lifecycle đăng ký, tránh xử lý blocking trong callback, bảo vệ kết nối remote và dùng hệ thống lưu sự kiện riêng nếu cần giao nhận bền vững.
