# Notification type, source, sequence number và timestamp trong JMX

## Mục tiêu

Bài học này giúp bạn hiểu bốn trường chính của Java Management Extensions (JMX) Notification, đọc chúng qua Java API, phát notification từ một Standard MBean, nhận notification từ listener và áp dụng các trường đó đúng cách khi chẩn đoán sự kiện quản trị trong ứng dụng Spring Framework.

Bạn sẽ phân biệt:

- **type:** sự kiện thuộc loại gì.
- **source:** sự kiện xuất phát từ đâu.
- **sequence number:** thứ tự logic được bên phát gán cho thông báo.
- **timestamp:** thời điểm gắn với thông báo, tính theo mili giây kể từ Unix epoch.

Các trường này có vai trò khác nhau; hiểu đúng sẽ tránh lỗi khi lọc sự kiện, đối chiếu nhiều JVM và suy luận về thứ tự hoặc thời gian.

## 1. JMX Notification là gì?

JMX cho phép một MBean công bố attributes, operations và notification. Attribute giúp đọc trạng thái, operation giúp thực hiện thao tác quản trị, còn notification thông báo một sự kiện đã xảy ra.

Ví dụ một MBean quản lý hàng đợi có thể phát notification khi:

- Queue vượt ngưỡng cảnh báo.
- Queue trở về trạng thái bình thường.
- Chế độ nhận job bị tạm dừng.
- Cấu hình quản trị được nạp lại.

Notification khác với việc polling một attribute. Listener nhận một thông báo khi broadcaster phát sự kiện; listener không cần liên tục gọi getter để kiểm tra thay đổi.

Java định nghĩa lớp javax.management.Notification, cùng các giao diện NotificationBroadcaster, NotificationEmitter và NotificationListener. NotificationBroadcasterSupport hỗ trợ triển khai broadcaster với ít mã hơn.

Sơ đồ khái niệm:

    MBean / NotificationBroadcaster
              |
              | sendNotification(Notification)
              v
       Notification listener
              |
              +-- getType()
              +-- getSource()
              +-- getSequenceNumber()
              +-- getTimeStamp()

Một notification cũng có thể mang message và userData, nhưng bài này tập trung vào bốn trường metadata chính.

## 2. Bốn trường cốt lõi

| Trường | Java API | Ý nghĩa | Ví dụ |
|---|---|---|---|
| type | getType() | Định danh loại sự kiện | learning.queue.overloaded |
| source | getSource() | Nguồn của sự kiện | ObjectName của MBean hoặc đối tượng phát |
| sequence number | getSequenceNumber() | Số thứ tự do broadcaster cấp | 27 |
| timestamp | getTimeStamp() | Mốc thời gian của notification | Giá trị epoch milliseconds |

Bốn trường cùng trả lời: **Điều gì đã xảy ra, ở nguồn nào, mang số thứ tự nào và được gắn với thời điểm nào?**

Chúng không tương đương với ID nghiệp vụ, URL của service, trace ID hay bảo đảm delivery của message broker.

## 3. Notification type: sự kiện gì?

Type là một chuỗi String, đọc qua:

\`\`\`java
String type = notification.getType();
\`\`\`

Một ứng dụng có thể định nghĩa:

\`\`\`java
public static final String QUEUE_OVERLOADED =
        "learning.queue.overloaded";

public static final String QUEUE_RECOVERED =
        "learning.queue.recovered";

public static final String CONFIG_RELOADED =
        "learning.config.reloaded";
\`\`\`

Các giá trị đó thuộc về contract của ứng dụng. JMX không bắt buộc mọi custom notification phải dùng cùng một namespace; tuy nhiên việc đặt tên có cấu trúc sẽ giúp nhiều client hiểu thống nhất.

### Type không phải tên Java class

Nhiều notification cùng là instance của javax.management.Notification nhưng có type khác nhau:

\`\`\`java
Notification overload = new Notification(
        "learning.queue.overloaded",
        source,
        1L
);

Notification recovered = new Notification(
        "learning.queue.recovered",
        source,
        2L
);
\`\`\`

Cả hai có Java class giống nhau nhưng mô tả hai sự kiện khác nhau. Khi xử lý, dùng getType() thay vì chỉ kiểm tra getClass().

### Nên đặt tên type thế nào?

Quy ước gợi ý cho custom notification:

    <namespace>.<component>.<event>

Ví dụ:

    learning.queue.overloaded
    learning.queue.recovered
    learning.cache.invalidated

Tên phải có ý nghĩa ổn định, đủ cụ thể và được tài liệu hóa. Tránh đổi type bất ngờ vì công cụ giám sát có thể lọc theo giá trị cũ.

Với các MBean của JDK hoặc thư viện, ưu tiên các constant và type chính thức. Chẳng hạn AttributeChangeNotification định nghĩa loại notification đặc thù cho việc thay đổi attribute. Không tự thay thế những type đã là một phần của contract bên thứ ba.

### Type có được khai báo trước không?

Một broadcaster thường công bố các loại notification có thể phát bằng MBeanNotificationInfo:

\`\`\`java
MBeanNotificationInfo info = new MBeanNotificationInfo(
        new String[] {
            "learning.queue.overloaded",
            "learning.queue.recovered"
        },
        Notification.class.getName(),
        "Queue state notifications"
);
\`\`\`

Thông tin này phục vụ discovery cho JMX tooling. Khai báo MBeanNotificationInfo không tự phát sự kiện; code vẫn phải tạo và gửi Notification.

## 4. Source: sự kiện đến từ đâu?

Source được đọc bằng:

\`\`\`java
Object source = notification.getSource();
\`\`\`

Kiểu trả về là Object, nên không thể giả định mọi notification đều có source là String hoặc ObjectName.

Một Notification có thể được tạo như sau:

\`\`\`java
Notification notification = new Notification(
        "learning.queue.overloaded",
        this,
        5L
);
\`\`\`

Trong trường hợp đó, code truyền đối tượng hiện tại làm source. Các cơ chế JMX có thể biểu diễn nguồn bằng tên MBean khi thông báo đi qua hệ thống quản trị. Client phải xem contract và giá trị thực tế để xác định cách diễn giải.

### Source và ObjectName

ObjectName là định danh của MBean bên trong một MBeanServer:

    learning.jmx:type=QueueMonitor,name=Primary

Có thể dùng ObjectName làm source khi phù hợp:

\`\`\`java
ObjectName sourceName = new ObjectName(
        "learning.jmx:type=QueueMonitor,name=Primary"
);

Notification notification = new Notification(
        "learning.queue.overloaded",
        sourceName,
        5L
);
\`\`\`

Nhưng đừng coi ObjectName là URL để kết nối vào JVM. Client muốn nhận notification từ JVM khác vẫn cần kết nối tới MBeanServer tương ứng qua JMX connector.

### Type và source giải quyết hai câu hỏi khác nhau

Ví dụ:

    type   = learning.queue.overloaded
    source = learning.jmx:type=QueueMonitor,name=Primary

    type   = learning.queue.overloaded
    source = learning.jmx:type=QueueMonitor,name=Secondary

Hai notification cùng type nhưng đến từ hai queue khác nhau.

Listener có thể ghi log:

\`\`\`java
System.out.println("Type: " + notification.getType());
System.out.println("Source: " + notification.getSource());
\`\`\`

Nếu xử lý nhiều nguồn, lưu cả type và source để không gộp nhầm các sự kiện độc lập.

### Source có duy nhất trên mọi JVM không?

Không nhất thiết. ObjectName có phạm vi trong một MBeanServer. Hai JVM độc lập có thể có cùng ObjectName:

    learning.jmx:type=QueueMonitor,name=Primary

Nếu tổng hợp notification từ nhiều JVM, cần giữ thêm identity của host/instance/kết nối nguồn. Source đơn lẻ không đủ làm ID toàn cục.

## 5. Sequence number: thứ tự do bên phát cấp

Đọc số thứ tự:

\`\`\`java
long sequence = notification.getSequenceNumber();
\`\`\`

Sequence number thường được tăng khi broadcaster phát notification:

    overload  -> 1
    recovered -> 2
    overload  -> 3

Nhưng Notification không tự định nghĩa một bộ đếm toàn cầu. Chính broadcaster hoặc thư viện sở hữu notification quyết định phạm vi và cách cấp số.

### Tạo sequence number bằng AtomicLong

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;

private final AtomicLong sequence = new AtomicLong();

long next = sequence.incrementAndGet();
\`\`\`

AtomicLong hỗ trợ lấy số thứ tự tăng dần an toàn khi nhiều luồng cùng cấp số.

Ví dụ tạo notification:

\`\`\`java
Notification notification = new Notification(
        "learning.queue.overloaded",
        this,
        sequence.incrementAndGet(),
        System.currentTimeMillis(),
        "Queue exceeded threshold"
);
\`\`\`

### Sequence number không phải event ID toàn hệ thống

Hai MBean khác nhau có thể cùng phát sequence 1, 2, 3. Khi JVM khởi động lại, broadcaster mới cũng có thể khởi tạo bộ đếm về 0.

Ví dụ:

    JVM A / Queue Primary: 1, 2, 3
    JVM B / Queue Primary: 1, 2, 3

Không thể kết luận notification số 2 của JVM A và số 2 của JVM B là cùng một sự kiện.

Một khóa đối chiếu hợp lý hơn có thể gồm:

    (JVM instance, MBean identity, sequence number)

Nếu ứng dụng cần correlation ID hay event ID duy nhất toàn hệ thống, hãy thiết kế riêng và đưa vào dữ liệu bổ sung.

### Sequence number có chứng minh thứ tự nhận không?

Không chắc chắn. Khi nhiều thread cấp sequence rồi gửi notification, thread có sequence lớn hơn có thể gửi hoặc được xử lý trước thread có sequence nhỏ hơn.

AtomicLong đảm bảo tính nguyên tử của thao tác tăng số; nó không tự đảm bảo thứ tự giao notification tới mọi listener trong mọi môi trường.

Nếu thứ tự nhận phải nghiêm ngặt, cần tổ chức luồng phát tuần tự và định nghĩa rõ contract ordering.

### Có thể dựa vào sequence để phát hiện mất notification không?

Chỉ nên dùng như dấu hiệu. Giả sử listener nhận 10 rồi 13. Điều này có thể do:

- Listener chỉ lọc một số type, trong khi bộ đếm tăng cho mọi type.
- Listener được đăng ký sau thời điểm một số notification đã phát.
- Các notification đến không cùng thứ tự cấp số.
- Broadcaster hoặc client thay đổi vòng đời.
- Một số notification không được chuyển tới listener.

JMX notification mặc định không phải durable message queue có cơ chế replay hoặc exactly-once delivery. Sequence number không biến JMX thành event store.

## 6. Timestamp: mốc thời gian của notification

Đọc timestamp:

\`\`\`java
long timeStamp = notification.getTimeStamp();
\`\`\`

Timestamp của Notification thường dùng epoch milliseconds: số mili giây kể từ 1970-01-01T00:00:00Z.

Ví dụ:

\`\`\`java
Notification notification = new Notification(
        "learning.queue.overloaded",
        this,
        42L,
        System.currentTimeMillis(),
        "Queue overloaded"
);
\`\`\`

Dùng Java Time API để hiển thị:

\`\`\`java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

Instant instant = Instant.ofEpochMilli(
        notification.getTimeStamp()
);

String displayed = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm:ss.SSS z")
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .format(instant);

System.out.println(displayed);
\`\`\`

Giá trị epoch milliseconds không mang múi giờ; múi giờ chỉ được áp dụng khi định dạng để hiển thị.

### Timestamp là lúc sự kiện xảy ra hay lúc nhận được?

Điều này phụ thuộc thời điểm broadcaster gắn timestamp. Một notification có thể được tạo sau khi điều kiện nghiệp vụ thực sự xảy ra. Listener có thể nhận notification muộn hơn do scheduling hoặc transport.

Ba mốc cần phân biệt:

1. **Thời điểm điều kiện xảy ra** trong nghiệp vụ.
2. **Thời điểm notification được tạo/gắn timestamp.**
3. **Thời điểm listener nhận thông báo.**

Chúng có thể khác nhau.

### Timestamp có giúp sắp xếp tuyệt đối không?

Không. Nhiều notification có thể cùng timestamp mili giây. Đồng hồ của máy có thể được điều chỉnh; giữa các máy có thể tồn tại clock skew.

Ví dụ:

    Event A: sequence=100, timestamp=1762855200123
    Event B: sequence=101, timestamp=1762855200123

Hai sự kiện cùng timestamp nhưng có sequence khác nhau là bình thường.

Không dùng timestamp làm ID duy nhất. Không mặc định rằng timestamp của hai JVM khác nhau có thể dùng để chứng minh thứ tự chính xác khi đồng hồ chưa được đồng bộ và mô hình sự kiện chưa xác định rõ.

### Đo độ trễ của listener

Có thể quan sát:

\`\`\`java
long receiveTime = System.currentTimeMillis();
long eventTime = notification.getTimeStamp();
long apparentDelay = receiveTime - eventTime;
\`\`\`

Đây chỉ là **độ trễ biểu kiến**. Khi broadcaster và listener chạy trên hai host, sai lệch đồng hồ có thể làm kết quả không chính xác, thậm chí âm.

Nếu cần đo duration trong cùng một tiến trình, dùng nguồn thời gian đơn điệu như System.nanoTime() để tính thời lượng, thay vì suy luận từ wall-clock timestamp.

## 7. Ví dụ hoàn chỉnh: MBean phát notification

Tạo một Standard MBean quản lý trạng thái queue. Khi depth vượt 100, broadcaster phát overload; khi trở lại mức cho phép, phát recovery.

### 7.1. Interface

Tệp QueueMonitorMBean.java:

\`\`\`java
package example.jmx;

public interface QueueMonitorMBean {
    int getDepth();
    boolean isOverloaded();
    void updateDepth(int newDepth);
}
\`\`\`

### 7.2. Implementation và broadcaster

Tệp QueueMonitor.java:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor
        extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    public static final String TYPE_OVERLOADED =
            "learning.queue.overloaded";
    public static final String TYPE_RECOVERED =
            "learning.queue.recovered";

    private static final int THRESHOLD = 100;
    private final AtomicLong sequence = new AtomicLong();

    private int depth;
    private boolean overloaded;

    @Override
    public synchronized int getDepth() {
        return depth;
    }

    @Override
    public synchronized boolean isOverloaded() {
        return overloaded;
    }

    @Override
    public synchronized void updateDepth(int newDepth) {
        if (newDepth < 0) {
            throw new IllegalArgumentException(
                    "newDepth must be non-negative"
            );
        }

        depth = newDepth;
        boolean next = depth > THRESHOLD;

        if (next == overloaded) {
            return;
        }

        overloaded = next;

        String type = overloaded
                ? TYPE_OVERLOADED
                : TYPE_RECOVERED;

        Notification notification = new Notification(
                type,
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                overloaded ? "Queue overloaded" : "Queue recovered"
        );

        notification.setUserData(depth);
        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] {
                    TYPE_OVERLOADED,
                    TYPE_RECOVERED
                },
                Notification.class.getName(),
                "Queue state changes"
            )
        };
    }
}
\`\`\`

Trong ví dụ:

- **type** phân biệt overload và recovery.
- **source** được truyền là đối tượng broadcaster hiện tại.
- **sequence number** tăng mỗi lần thật sự phát notification.
- **timestamp** lấy tại thời điểm tạo thông báo.
- **userData** là depth hiện tại; đây là dữ liệu bổ sung, không phải một trong bốn trường chính.

Phương thức updateDepth đồng bộ hóa việc đổi trạng thái để ví dụ dễ hiểu. Trong hệ thống thực, cần cân nhắc tác động khi gọi listener trong vùng đồng bộ hóa, giữ callback ngắn và thiết kế rõ ràng quyền gọi management operation. Độ sâu queue thực tế thường đến từ bộ xử lý nội bộ thay vì cho người dùng JMX tự chỉnh.

### 7.3. Đăng ký MBean và listener

Tệp NotificationDemo.java:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class NotificationDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "learning.jmx:type=QueueMonitor,name=Primary"
        );

        QueueMonitor monitor = new QueueMonitor();
        server.registerMBean(monitor, name);

        NotificationListener listener =
                (notification, handback) -> {
                    System.out.println(
                        "type=" + notification.getType()
                        + ", source=" + notification.getSource()
                        + ", sequence="
                        + notification.getSequenceNumber()
                        + ", timestamp="
                        + notification.getTimeStamp()
                    );
                };

        server.addNotificationListener(
                name,
                listener,
                null,
                null
        );

        monitor.updateDepth(110);
        monitor.updateDepth(120);
        monitor.updateDepth(50);

        server.removeNotificationListener(name, listener);
        server.unregisterMBean(name);
    }
}
\`\`\`

Kết quả mong đợi là hai notification, vì cập nhật từ 110 lên 120 không làm đổi trạng thái overload.

Ví dụ minh họa:

    type=learning.queue.overloaded, source=..., sequence=1, timestamp=...
    type=learning.queue.recovered, source=..., sequence=2, timestamp=...

Source và timestamp phụ thuộc vào môi trường thực thi cũng như cách JMX chuyển notification. Không nên viết test cố định một giá trị động.

## 8. Lọc theo type

Một listener chỉ muốn biết queue bị quá tải có thể dùng NotificationFilterSupport:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
        new NotificationFilterSupport();

filter.enableType(QueueMonitor.TYPE_OVERLOADED);

server.addNotificationListener(
        name,
        listener,
        filter,
        null
);
\`\`\`

Cần biết NotificationFilterSupport so khớp theo **prefix** của notification type. Nếu bật loại chung như learning.queue, listener có thể nhận nhiều type bắt đầu bằng prefix đó.

Nếu muốn khớp chính xác một type:

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter filter =
        n -> QueueMonitor.TYPE_OVERLOADED.equals(n.getType());
\`\`\`

Một listener lọc bớt event có thể nhìn thấy sequence number nhảy số. Điều này không tự chứng minh rằng thông báo đã bị mất.

## 9. Áp dụng trong Spring Framework

Spring Framework hỗ trợ xuất bản MBean qua MBeanExporter và cơ chế annotation-based management metadata. Dù MBean được khởi tạo bởi Spring, các trường type, source, sequence number và timestamp vẫn mang ý nghĩa từ Java JMX.

Ví dụ cấu hình xuất Standard MBean:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    MBeanExporter queueMonitorExporter(QueueMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(
                ManagementFactory.getPlatformMBeanServer()
        );
        exporter.setBeans(Map.of(
                "learning.jmx:type=QueueMonitor,name=Primary",
                monitor
        ));
        return exporter;
    }
}
\`\`\`

Spring quản lý bean và vòng đời exporter. MBean vẫn phải công bố notification theo JMX contract. JConsole hoặc JMX client muốn quan sát MBean ở JVM khác cần kết nối đúng JVM, đủ quyền và đăng ký listener qua MBeanServerConnection.

Phân biệt JMX Notification với Spring ApplicationEvent: Spring ApplicationEvent chủ yếu phục vụ giao tiếp nội bộ trong application context. JMX Notification là contract quản trị dành cho JMX listener. Hai cơ chế có thể được tích hợp nhưng không tự động tương đương.

## 10. Trường hợp nhiều MBean hoặc nhiều JVM

Giả sử có hai JVM:

    JVM-A: type=learning.queue.overloaded
           source=learning.jmx:type=QueueMonitor,name=Primary
           sequence=8

    JVM-B: type=learning.queue.overloaded
           source=learning.jmx:type=QueueMonitor,name=Primary
           sequence=8

Đây có thể là hai sự kiện riêng. Dù ObjectName và sequence giống nhau, identity của MBeanServer/JVM khác nhau.

Khi gửi notification vào hệ thống log tập trung, nên bổ sung metadata như:

- service và instance ID;
- hostname/pod ID nếu cần;
- ObjectName hoặc định danh nguồn;
- notification type;
- sequence number trong phạm vi broadcaster;
- timestamp và thời điểm collector nhận;
- correlation ID nếu có nhu cầu liên hệ sự kiện với request hay nghiệp vụ.

Không đặt dữ liệu nhạy cảm như token, password hoặc thông tin cá nhân vào source, message hay userData. Client quản trị có thể ghi log và chuyển tiếp các trường này.

## 11. Thứ tự, độ tin cậy và các giới hạn

### Notification không phải message broker

JMX notification thường dùng để quan sát trạng thái và sự kiện quản trị trong thời gian chạy. Nó không mặc định cung cấp:

- lưu trữ bền vững;
- replay sự kiện đã phát;
- exactly-once delivery;
- acknowledgement từ mọi listener;
- thứ tự toàn cục giữa các JVM.

Nếu cần các tính chất đó, hãy sử dụng hệ thống messaging/event log có contract phù hợp. JMX có thể vẫn được dùng để quan sát hệ thống đó.

### Sequence và timestamp không thay thế nhau

Sequence number là thứ tự logic **do nguồn phát cấp**. Timestamp là thời điểm gắn với event theo đồng hồ. Các notification có thể có sequence khác nhau nhưng cùng timestamp; hoặc callback đến listener khác với thứ tự được cấp sequence.

### Cần giữ listener đơn giản

Listener nên xử lý ngắn gọn và không thực hiện công việc mạng chậm hoặc block vô hạn trong callback. Nếu cần nhiều xử lý hơn, chuyển dữ liệu sang executor hoặc queue nội bộ với giới hạn rõ ràng.

### Không tự coi gap là mất dữ liệu

Khi listener nhận sequence 5 rồi 9, cần xem filter, thời điểm đăng ký listener, bộ đếm của broadcaster và concurrency. Chỉ kết luận có mất notification nếu contract nguồn và cơ chế delivery chứng minh điều đó.

## 12. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xem xét |
|---|---|---|
| Listener không phân biệt loại event | Chỉ đọc message, bỏ qua type | Dùng getType() |
| Hai nguồn bị gộp làm một | Bỏ qua source hoặc instance ID | Ghi cả source và JVM identity |
| Sequence trùng ở hai JVM | Bộ đếm độc lập | Đừng dùng sequence làm ID toàn cục |
| Sequence nhảy sau khi lọc | Filter bỏ qua type khác | Kiểm tra contract bộ đếm |
| Notification đến không đúng sequence | Concurrent send/transport | Xem thứ tự cấp số và phát |
| Timestamp trùng | Độ phân giải thời gian | Không dùng timestamp làm ID |
| Timestamp âm khi tính delay | Clock skew | Kiểm tra đồng hồ của các host |
| Listener không nhận sự kiện | Sai ObjectName, chưa đăng ký, filter bỏ qua | Kiểm tra broadcaster/listener |
| JConsole không có notification | MBean chưa công bố broadcaster metadata | Kiểm tra NotificationBroadcaster và getNotificationInfo() |
| Notification bị mất sau restart | Không có durable store | Dùng broker/event store nếu cần replay |

## 13. Bài tập

### Bài 1: Đọc metadata

Cho một notification:

    type = learning.cache.invalidated
    source = learning.jmx:type=Cache,name=Products
    sequenceNumber = 17
    timeStamp = 1762855200000
    message = Cache invalidated

Hãy trả lời:

1. Trường nào cho biết loại sự kiện?
2. Trường nào cho biết nguồn?
3. Sequence 17 có chứng minh đây là sự kiện thứ 17 của mọi JVM không?
4. Timestamp là lúc listener nhận hay mốc thời gian được gắn cho notification?
5. Có nên parse message để phân biệt event nếu type đã có contract?

Đáp án định hướng: type xác định loại; source xác định nguồn; sequence thuộc phạm vi broadcaster; timestamp là mốc được gắn cho notification; nên dùng type ổn định cho automation.

### Bài 2: Lọc notification

Từ ví dụ QueueMonitor, đăng ký hai listener: một nhận mọi type và một chỉ nhận learning.queue.overloaded. Thực hiện ba lần chuyển trạng thái: overload, recovered, overload. So sánh sequence number hai listener quan sát được và giải thích vì sao listener có filter thấy chuỗi số không liên tục.

### Bài 3: Phân tích nhiều nguồn

Có các log:

    source=Queue-A, type=overloaded, seq=8, ts=1000
    source=Queue-B, type=overloaded, seq=8, ts=1002
    source=Queue-A, type=recovered, seq=9, ts=1020

Timestamp ở đây là giá trị minh họa. Có thể coi hai bản ghi seq=8 là trùng lặp không? Vì sao? Nếu Queue-A và Queue-B thuộc hai JVM khác nhau, cần thêm thông tin gì để phân biệt nguồn ổn định?

Đáp án: không; sequence không duy nhất giữa các broadcaster. Nên giữ JVM/instance identity và ObjectName phù hợp.

## 14. Checklist thiết kế notification

Trước khi đưa một custom Notification vào ứng dụng:

1. Định nghĩa type ổn định và tài liệu hóa các loại sự kiện.
2. Xác định rõ source và cách nhận diện instance từ xa.
3. Định nghĩa phạm vi sequence number, khi nào reset, cách tăng an toàn.
4. Gắn timestamp tại thời điểm có ý nghĩa, và ghi rõ mốc đó.
5. Công bố getNotificationInfo() cho các type hỗ trợ.
6. Giữ message dễ hiểu, userData nhỏ gọn và không nhạy cảm.
7. Thiết kế filter theo type phù hợp.
8. Đừng giả định listener nhận sự kiện theo thứ tự toàn cục hoặc có replay.
9. Giữ callback ngắn và xử lý lỗi listener an toàn.
10. Xem JMX notification như kênh quản trị; nếu cần event stream bền vững, dùng hệ thống chuyên dụng.

## 15. Ghi nhớ

**Type trả lời “sự kiện gì”, source trả lời “nguồn nào”, sequence number biểu diễn thứ tự logic do bên phát cấp, còn timestamp biểu diễn mốc thời gian được gắn cho notification.**

Không trường nào đứng riêng có thể bảo đảm identity toàn cục hoặc delivery đáng tin cậy. Khi xây hệ thống Spring Framework có MBean phát notification, hãy phối hợp bốn trường với contract của broadcaster, ObjectName, instance identity, listener filter và quy định vận hành rõ ràng.

## Tài liệu tham khảo

- Java SE 21 Notification API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE 21 NotificationBroadcasterSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 NotificationFilterSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationFilterSupport.html
- Java SE 21 MBeanNotificationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanNotificationInfo.html
- Spring Framework JMX reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
