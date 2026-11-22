# Lọc notification ở phía phát hay phía nhận trong Spring Framework JMX

## Mục tiêu

JMX notification là cơ chế một MBean thông báo sự kiện cho những bên đăng ký lắng nghe. Khi ứng dụng Spring Framework phát nhiều notification, quyết định quan trọng không chỉ là **lọc sự kiện nào** mà còn là **đặt việc lọc ở đâu**: phía phát (source/emitter), phía đăng ký và tiếp nhận (listener), hay cả hai.

Vị trí bộ lọc ảnh hưởng trực tiếp đến chi phí tạo sự kiện, độ phức tạp của hệ thống, khả năng tái sử dụng dữ liệu cho nhiều listener, an toàn vận hành và nguy cơ bỏ sót sự kiện. Một bộ lọc đúng tại listener có thể tiết kiệm callback nhưng vẫn không tiết kiệm chi phí tạo payload tại emitter. Ngược lại, loại bỏ sự kiện ngay tại emitter tiết kiệm tài nguyên nhưng làm mọi listener mất khả năng quan sát sự kiện đó.

Bài này giúp bạn:

- Hiểu vai trò của \`NotificationBroadcaster\`, \`NotificationEmitter\`, \`NotificationListener\` và \`NotificationFilter\`.
- Phân biệt điều kiện chọn sự kiện tại nguồn và điều kiện chọn sự kiện theo nhu cầu từng subscriber.
- Giải thích trình tự gửi notification, kiểm tra filter và gọi listener trong JMX.
- Đăng ký listener/filter trên \`MBeanServer\` hoặc qua cấu hình \`NotificationListenerBean\` trong Spring.
- Thiết kế cơ chế lọc theo type, nguồn, severity và dữ liệu có giới hạn.
- Đánh giá trade-off giữa hiệu năng, tính đầy đủ quan sát, bảo mật, nhất quán và vòng đời.
- Chẩn đoán trường hợp listener không nhận sự kiện dù emitter đã phát, hoặc callback nhận quá nhiều dữ liệu.

## 1. Sơ đồ luồng notification

Một nguồn sự kiện MBean có thể gửi nhiều loại notification:

\`\`\`text
Ứng dụng Spring
      |
      v
MBean / NotificationEmitter
      |
      | 1. phát Notification (type, source, seq, timestamp, message, userData)
      v
JMX broadcaster
      |
      +--> filter của listener A ---> listener A (metrics)
      |
      +--> filter của listener B ---> listener B (audit)
      |
      +--> filter của listener C ---> listener C (alert)
\`\`\`

Khi emitter không tạo notification, **không listener nào** có thể phục hồi thông tin đó bằng cách thay filter ở phía nhận. Khi emitter tạo notification nhưng filter của một listener trả \`false\`, listener đó bỏ qua event; listener khác vẫn có thể nhận nó.

Đặt cạnh nhau hai câu hỏi:

| Quyết định | Câu hỏi trọng tâm |
|---|---|
| Lọc ở phía phát | Có nên tạo và gửi loại sự kiện này từ nguồn ngay từ đầu? |
| Lọc ở phía nhận | Subscriber cụ thể này có quan tâm đến sự kiện đã phát không? |

Đây là hai cấp quyết định khác nhau, không phải hai cú pháp viết một bộ lọc như nhau.

## 2. Các thành phần JMX liên quan

**\`Notification\`** chứa các trường cơ bản như \`type\`, \`source\`, \`sequenceNumber\`, \`timeStamp\`, \`message\` và \`userData\`. \`type\` thường là chuỗi phân cấp như \`com.example.jobs.failed\`.

**\`NotificationBroadcaster\`** định nghĩa cơ chế đăng ký, gỡ listener và mô tả các loại notification thông qua \`getNotificationInfo()\`.

**\`NotificationEmitter\`** mở rộng \`NotificationBroadcaster\` với thao tác xóa chính xác bộ ba listener/filter/handback. Một MBean có thể dùng \`NotificationBroadcasterSupport\` để triển khai cơ chế phát.

**\`NotificationListener\`** nhận callback:

\`\`\`java
void handleNotification(Notification notification, Object handback);
\`\`\`

**\`NotificationFilter\`** quyết định một notification có được chuyển đến listener đã đăng ký hay không:

\`\`\`java
boolean isNotificationEnabled(Notification notification);
\`\`\`

\`handback\` là object client cung cấp lúc đăng ký, được đưa lại cho listener; nó không phải metadata xác thực và không nên được dùng như bằng chứng về quyền.

**\`NotificationFilterSupport\`** là implementation có sẵn giúp cho phép những type theo prefix; các type được bật thông qua \`enableType(String)\`. Vì là prefix matching, bật \`com.example.jobs\` có thể nhận \`com.example.jobs.failed\` cùng nhiều loại con khác. Khi cần lọc một type chính xác, hãy tự viết filter với \`equals\`.

## 3. Lọc phía nhận: bộ lọc gắn riêng với từng đăng ký

Đây là cơ chế JMX chuẩn, dùng khi một emitter có nhiều subscriber với mối quan tâm khác nhau.

Ví dụ:

- Metrics listener muốn nhận tất cả \`job.completed\` để tăng counter.
- Alert listener chỉ muốn nhận \`job.failed\`.
- Audit listener cần cả sự kiện thay đổi trạng thái theo chính sách retention.
- UI vận hành chỉ hiển thị event thuộc một thành phần đang được theo dõi.

Một \`NotificationFilter\` được truyền khi đăng ký listener:

\`\`\`java
import javax.management.*;

NotificationFilter failuresOnly = notification ->
    "com.example.jobs.failed".equals(notification.getType());

NotificationListener listener = (notification, handback) -> {
    System.out.println("Failure event #" + notification.getSequenceNumber());
};

server.addNotificationListener(
    objectName,
    listener,
    failuresOnly,
    null
);
\`\`\`

Khi nguồn gửi \`com.example.jobs.completed\`, filter này trả \`false\`; cùng notification đó vẫn có thể được gửi đến listener khác có filter phù hợp.

Không gắn quyết định của một nhóm tiêu thụ vào emitter nếu nhiều nhóm khác cần loại dữ liệu đó. Ví dụ, tắt notification hoàn thành ở nguồn chỉ vì dashboard không cần hiển thị có thể khiến metrics listener mất dữ liệu.

### 3.1 Filter theo type bằng NotificationFilterSupport

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.failed");

server.addNotificationListener(
    objectName,
    listener,
    filter,
    "operations-dashboard"
);
\`\`\`

Ở đây \`handback\` là chuỗi ứng dụng chọn; nó không nhất thiết xuất hiện trong notification và không tự bảo vệ endpoint. Nếu muốn chỉ nhận type \`com.example.jobs.failed\` mà không nhận type có tiền tố đó, dùng \`NotificationFilter\` với phép so sánh chính xác.

### 3.2 Filter theo thuộc tính của notification

\`\`\`java
NotificationFilter slowFailures = n -> {
    if (!"com.example.jobs.failed".equals(n.getType())) {
        return false;
    }
    Object data = n.getUserData();
    if (!(data instanceof FailureInfo failure)) {
        return false;
    }
    return failure.durationMillis() >= 5_000;
};
\`\`\`

\`FailureInfo\` trong ví dụ là kiểu dữ liệu ứng dụng tự định nghĩa. Nếu nhận notification từ xa, cần cân nhắc serialize và class availability; một DTO tùy ý không chắc tương thích giữa các tiến trình. Với notification dành cho nhiều công cụ JMX, ưu tiên payload đơn giản hoặc Open MBean data theo hợp đồng ổn định.

Filter nên chạy nhanh và có tính quyết định, không truy cập database, khóa toàn cục hoặc gọi HTTP để quyết định mỗi event. Nếu việc lọc quá nặng, nguồn phát có thể bị chậm hoặc gây nghẽn pipeline sự kiện.

## 4. Lọc phía phát: quyết định có tạo/gửi sự kiện hay không

Ví dụ emitter tạo notification sau mỗi job:

\`\`\`java
Notification n = new Notification(
    "com.example.jobs.completed",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Job completed");
sendNotification(n);
\`\`\`

Nếu hệ thống hoàn thành hàng chục nghìn job mỗi giây, việc tạo từng notification, xây dựng payload, ghi metadata và phân phối đến nhiều listener có thể gây tải đáng kể. Có thể đặt điều kiện tại nguồn:

\`\`\`java
if (emitCompletionNotifications) {
    Notification n = new Notification(
        "com.example.jobs.completed",
        this,
        sequence.incrementAndGet(),
        System.currentTimeMillis(),
        "Job completed");
    sendNotification(n);
}
\`\`\`

Khi điều kiện sai, notification hoàn thành **không được tạo**. Đây là cơ chế sampling hoặc chính sách phát ở tầng nguồn, không phải JMX \`NotificationFilter\` gắn listener. Người vận hành cần biết rõ điều này bởi mất sự kiện ở nguồn là mất dữ liệu đối với toàn bộ subscriber.

Lọc ở nguồn hợp lý khi:

- Event có tần suất rất cao và không cần công bố từng sự kiện.
- Nội dung không nên được phát trên kênh quản trị vì nhạy cảm.
- Hợp đồng sản phẩm chỉ yêu cầu những cột mốc hoặc những trạng thái chuyển đổi cụ thể.
- Có kênh khác đáng tin cậy hơn cho dữ liệu chi tiết, ví dụ metrics aggregate hoặc audit log riêng.

Nhưng nếu một notification đã là một phần của hợp đồng quan sát hoặc compliance, việc tắt phát cần được quản lý như thay đổi giao diện và quy trình vận hành. Không được tự mặc định sampling có thể thay thế audit yêu cầu tính đầy đủ.

### 4.1 Tạo payload có điều kiện

Ngay cả khi muốn tất cả listener nhận notification về failure, ta vẫn có thể tránh tạo payload chẩn đoán đắt đỏ trước khi thật sự cần:

\`\`\`java
if (notifyFailures) {
    String summary = buildBoundedFailureSummary(failure);
    Notification n = new Notification(
        "com.example.jobs.failed",
        this,
        sequence.incrementAndGet(),
        System.currentTimeMillis(),
        summary);
    sendNotification(n);
}
\`\`\`

Đừng xây dựng \`buildBoundedFailureSummary\` trước \`if\` nếu mục tiêu là tiết kiệm chi phí khi không phát. Nội dung payload nên bị giới hạn và che dữ liệu bí mật. Không nên đưa stack trace vô hạn, token hoặc raw request body vào \`userData\`.

## 5. So sánh chi phí và tính đầy đủ

| Khía cạnh | Lọc phía phát | Lọc phía nhận |
|---|---|---|
| Có tạo notification? | Có thể bỏ qua hoàn toàn | Nguồn vẫn tạo |
| Có tạo payload? | Có thể tránh được trước khi gửi | Thường đã tạo ở nguồn |
| Dữ liệu có đến mọi subscriber không? | Không, nếu nguồn loại bỏ | Mỗi subscriber tự chọn |
| Tiết kiệm callback listener | Có | Có |
| Giảm chi phí phát ở nguồn | Thường có thể | Chỉ một phần hoặc không |
| Khả năng dùng cho nhiều mục đích | Bị giới hạn bởi chính sách nguồn | Cao hơn, vì các listener có filter riêng |
| Nguy cơ mất thông tin toàn cục | Cao hơn nếu loại bỏ event quan trọng | Chỉ trong phạm vi subscriber bị lọc |
| Phù hợp với | Sampling, loại dữ liệu không cần phát, giới hạn lưu lượng | Routing theo type, severity, nguồn, mối quan tâm |

Một cách thiết kế thực tế là hai tầng:

\`\`\`text
Business event
   |
   +--> Có cần công bố qua JMX không? (chính sách nguồn)
   |          |
   |         Không → không phát JMX notification
   |          |
   |         Có
   |          v
   |   Tạo notification đủ dữ liệu, giới hạn kích thước
   |          |
   |          v
   |   broadcaster phân phối theo filter từng đăng ký
   |          |
   +----------+-----------------+
              |                 |
       Alert listener     Metrics listener
\`\`\`

Lưu ý rằng JMX notification không mặc định là hàng đợi bền vững. Listener kết nối muộn hoặc mất kết nối có thể bỏ lỡ sự kiện. Vì thế, nếu cần lịch sử đầy đủ và replay, phải dùng lưu trữ bền vững hoặc messaging có bảo đảm thích hợp; filter không giải quyết vấn đề độ tin cậy của transport.

## 6. Tạo notification emitter trong ứng dụng Spring

Ví dụ MBean dùng \`NotificationBroadcasterSupport\`:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.*;

public interface JobMonitorMBean {
    long getProcessedCount();
}

public class JobMonitor extends NotificationBroadcasterSupport
        implements JobMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();
    private final AtomicLong processed = new AtomicLong();
    private volatile boolean emitCompleted = false;

    @Override
    public long getProcessedCount() {
        return processed.get();
    }

    public void onJobCompleted(String jobId) {
        processed.incrementAndGet();

        if (!emitCompleted) {
            return;
        }

        Notification notification = new Notification(
            "com.example.jobs.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job completed"
        );
        // Chỉ đưa dữ liệu đã lọc và giới hạn lên kênh JMX.
        sendNotification(notification);
    }

    public void onJobFailed(String jobId, String safeReasonCode) {
        Notification notification = new Notification(
            "com.example.jobs.failed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job failed: " + safeReasonCode
        );
        sendNotification(notification);
    }

    public void setCompletionNotificationsEnabled(boolean enabled) {
        this.emitCompleted = enabled;
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            "com.example.jobs.completed",
            "com.example.jobs.failed"
        };
        return new MBeanNotificationInfo[]{
            new MBeanNotificationInfo(
                types,
                Notification.class.getName(),
                "Lifecycle events emitted by job processing")
        };
    }
}
\`\`\`

Phương thức \`setCompletionNotificationsEnabled\` trong ví dụ là API Java nội bộ, **chưa được công bố** thành JMX operation hay attribute theo \`JobMonitorMBean\` đang khai báo. Nếu muốn thay đổi chính sách phát từ JMX, cần cân nhắc đó là hành động điều khiển hệ thống giám sát, có quyền và audit phù hợp. \`getNotificationInfo()\` mô tả các loại notification mà broadcaster có thể phát; nó không đảm bảo mỗi type luôn được tạo trong mọi thời điểm.

Khi class đăng ký là Standard MBean, interface theo quy ước tên \`JobMonitorMBean\` giúp xác định attribute/operation được công bố. \`NotificationBroadcasterSupport\` cung cấp phần phát, đăng ký và gỡ listener.

### 6.1 Đăng ký MBean và listener

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.*;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.jobs:type=Monitor,name=Primary");

JobMonitor monitor = new JobMonitor();
server.registerMBean(monitor, name);

NotificationListener errorListener = (notification, handback) -> {
    System.out.println(notification.getType()
        + " at " + notification.getTimeStamp());
};

NotificationFilter errors = n ->
    "com.example.jobs.failed".equals(n.getType());

server.addNotificationListener(name, errorListener, errors, null);
\`\`\`

Để tránh rò rỉ listener và lỗi restart trong cùng JVM, component đã đăng ký listener cần gỡ chính registration của nó khi dừng:

\`\`\`java
server.removeNotificationListener(name, errorListener);
server.unregisterMBean(name);
\`\`\`

Thứ tự này phù hợp với ví dụ có một owner quản lý toàn bộ. Trong hệ thống có nhiều context, không gỡ MBean do thành phần khác sở hữu. Nếu cùng một listener được đăng ký nhiều lần với các filter/handback khác nhau, hãy theo dõi và gỡ chính xác các đăng ký đó; phiên bản \`removeNotificationListener(name, listener)\` có thể xóa các registration khớp listener theo hợp đồng JMX.

## 7. Notification trong Spring: exporter và listener bean

Spring Framework cung cấp cơ chế đăng ký notification listener cho các MBean do ứng dụng quản lý, qua \`MBeanExporter\` và \`NotificationListenerBean\`. Ý tưởng là khai báo listener và lựa chọn MBean emitter trong cấu hình Spring thay vì đăng ký rải rác ở nhiều method.

Ví dụ cấu hình minh họa với \`NotificationListenerBean\`:

\`\`\`java
import javax.management.NotificationFilter;
import javax.management.NotificationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class NotificationConfiguration {

    @Bean
    NotificationListenerBean failureNotificationListener() {
        NotificationListener listener = (notification, handback) -> {
            System.out.println("JMX failure: " + notification.getType());
        };

        NotificationFilter filter = notification ->
            "com.example.jobs.failed".equals(notification.getType());

        NotificationListenerBean bean = new NotificationListenerBean();
        bean.setNotificationListener(listener);
        bean.setNotificationFilter(filter);
        return bean;
    }
}
\`\`\`

\`NotificationListenerBean\` mang metadata listener và filter; nó phải được nối đúng vào \`MBeanExporter\` cùng các tên MBean phù hợp thì mới có tác dụng. Chỉ khai báo \`@Bean NotificationListenerBean\` không có nghĩa exporter tự động đọc và đăng ký mọi listener bean. Dưới đây là ví dụ cấu hình exporter trực tiếp để thể hiện quan hệ đó:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.*;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class ExplicitJmxExportConfiguration {

    @Bean
    JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    MBeanExporter jmxExporter(JobMonitor monitor,
                              NotificationListenerBean failureNotificationListener)
            throws MalformedObjectNameException {
        String objectName = "com.example.jobs:type=Monitor,name=Primary";

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());
        exporter.setBeans(Map.of(objectName, monitor));

        failureNotificationListener.setMappedObjectName(
            new ObjectName(objectName));
        exporter.setNotificationListeners(
            new NotificationListenerBean[]{failureNotificationListener});
        return exporter;
    }
}
\`\`\`

Phải bảo đảm không có cơ chế export khác đăng ký trùng \`JobMonitor\` cùng \`ObjectName\`. Cấu hình cụ thể có thể khác khi dùng Spring Boot auto-configuration, annotation exporter hoặc bean factory của module.

Nếu muốn filter theo dữ liệu notification thay vì chỉ type, có thể dùng \`NotificationFilter\` tùy chỉnh; code filter chạy trong quy trình phân phối notification nên phải gọn, nhanh và an toàn đối với concurrency.

## 8. Sự thật về chỗ filter được thực thi

Khi dùng \`NotificationBroadcasterSupport\` thông thường, filter được broadcaster áp dụng trước khi gọi callback listener của đăng ký đó. Điều này có nghĩa:

1. Emitter vẫn tạo object \`Notification\`.
2. Emitter gọi \`sendNotification(notification)\`.
3. Broadcaster duyệt các đăng ký listener và kiểm tra filter tương ứng.
4. Với đăng ký được chấp nhận, callback được gọi thông qua cơ chế thực thi broadcaster dùng.

Chính vì bước 1 đã xảy ra, filter phía nhận không giúp tránh chi phí tạo notification và payload. Nó giảm những callback không cần thiết.

Tuy nhiên, ở kết nối JMX từ xa, listener/filter có thể được xử lý ở các tầng khác nhau tùy connector implementation và cách dùng API. Không nên giả định filter Java tùy chỉnh chạy trong một process cụ thể hoặc rằng nó có thể ngăn hoàn toàn mọi byte dữ liệu trước khi vận chuyển. Nếu tối ưu mạng là yêu cầu bắt buộc, hãy kiểm thử connector thực tế và thiết kế lọc ở nguồn hoặc trên endpoint quản trị có hợp đồng rõ.

Ngoài ra, \`NotificationBroadcasterSupport\` có thể dùng executor tùy constructor. Với executor mặc định, callback thường được gọi đồng bộ theo đường phát; một listener chậm có thể làm chậm nơi phát. Khi cấu hình executor bất đồng bộ, cần xét queue, thứ tự callback, saturation và lifecycle. Một filter có thao tác blocking vẫn có thể ảnh hưởng đường gửi.

## 9. Filter theo type, source, severity và userData

### 9.1 Type

Sử dụng exact comparison khi cần hợp đồng chặt:

\`\`\`java
NotificationFilter exactFailure = n ->
    "com.example.jobs.failed".equals(n.getType());
\`\`\`

Sử dụng \`NotificationFilterSupport\` khi cố ý nhận cả một nhóm prefix. Phải ghi rõ namespace để tránh vô tình đăng ký loại tương lai mới thêm vào.

### 9.2 Source

\`Notification.getSource()\` có thể là object MBean, tên quản trị hoặc kiểu do emitter cung cấp. Đừng giả định mọi source đều là \`ObjectName\` giống nhau, đặc biệt khi dữ liệu truyền qua connector hoặc nhiều thư viện phát notification.

Ví dụ:

\`\`\`java
NotificationFilter sourceFilter = n ->
    "com.example.jobs:type=Monitor,name=Primary"
        .equals(String.valueOf(n.getSource()));
\`\`\`

Đây chỉ là cách so sánh string minh họa. Cấu hình production cần xác lập dạng source có thể tin cậy trước khi so sánh; nếu nguồn là \`ObjectName\`, so sánh trực tiếp với \`ObjectName\` mong muốn sẽ có ngữ nghĩa tốt hơn.

### 9.3 Severity

JMX \`Notification\` cơ bản **không có field severity chuẩn**. Nếu muốn lọc cảnh báo theo mức nghiêm trọng, cần tự định nghĩa qua type hoặc payload:

\`\`\`text
com.example.jobs.failed.warning
com.example.jobs.failed.critical
\`\`\`

Hoặc payload cấu trúc gồm \`severity\`, \`errorCode\`, \`component\`; khi đó phải chuẩn hóa schema và tính tương thích client. Tránh parse severity từ chuỗi \`message\` tự do.

### 9.4 UserData

\`userData\` là trường mở rộng và có thể chứa thông tin nhạy cảm; filter sử dụng nó phải kiểm tra type, null và độ dài dữ liệu. Phía phát nên redact trước khi gửi vì một listener khác có thể không áp dụng filter hiện tại. Filter phía nhận không phải ranh giới bảo mật cho dữ liệu đã được công bố tới connector.

## 10. Hiệu năng: tính chi phí tại đúng giai đoạn

Giả sử ứng dụng có 10.000 job hoàn thành mỗi giây và 3 listener, trong đó chỉ một listener cần sự kiện hoàn thành.

**Phương án A: phát mọi completion**. Nguồn tạo 10.000 notification/giây, broadcaster kiểm tra filter theo từng đăng ký, rồi gọi đúng những listener chấp nhận. Chi phí nguồn vẫn lớn dù hai listener loại bỏ.

**Phương án B: không phát completion, chỉ công bố counter**. Nguồn cập nhật atomic counter và phát failure/transition hiếm gặp. Tính đầy đủ chi tiết từng completion không có trên JMX, nhưng metric tổng hợp giúp quan sát tải nhẹ hơn.

**Phương án C: sampling completion có công bố hợp đồng**. Nguồn phát theo giới hạn tốc độ hoặc sampling. Listener biết rằng stream chỉ là mẫu; không được dùng để đếm tổng số job. Số lượng tổng nên đến từ metric/counter riêng.

Tiêu chí chọn:

- Mục tiêu là quan sát tổng thể hay ghi lại từng sự kiện?
- Tần suất và kích thước payload bao nhiêu?
- Có subscriber bắt buộc nhận toàn bộ không?
- Mất một event có ảnh hưởng tới quyết định vận hành hoặc yêu cầu lưu vết không?
- Callback có chịu được backpressure và burst không?
- Cần metric tổng hợp, stream bền vững hay notification JMX tốt hơn?

Mặc dù JMX có thể gửi event tới nhiều listener, nó không nên bị biến thành event bus nghiệp vụ thay thế Kafka, JMS hoặc hệ thống log/audit bền vững.

## 11. Độ tin cậy, thứ tự và vòng đời listener

### 11.1 Không dùng JMX notification như audit log duy nhất

JMX notification không mặc định lưu bền vững hoặc replay cho listener kết nối muộn. Một listener mất kết nối có thể bỏ lỡ event. Số thứ tự \`sequenceNumber\` giúp nhận diện thứ tự do emitter gán và hỗ trợ tìm gap trong phạm vi định nghĩa; nó không bảo đảm giao hàng đúng một lần hoặc liên tục qua restart.

Nếu cần audit đầy đủ, lưu sự kiện ở kho đáng tin cậy trước hoặc song song với notification quản trị.

### 11.2 Listener được đăng ký và gỡ đúng vòng đời

Ứng dụng Spring có context refresh, redeploy hoặc test chạy nhiều lần; nếu đăng ký cùng listener lặp mà không gỡ, callback có thể chạy nhiều lần cho cùng một notification. Nếu MBean bị unregister hoặc được register lại bằng cùng tên, subscription phải được quản lý đúng cơ chế MBeanServer/connector; không nên mặc định đăng ký cũ còn hiệu lực với instance mới.

Hãy đảm bảo component sở hữu listener biết khi nào đăng ký, gỡ và đóng tài nguyên executor. Nếu listener làm I/O nặng, đẩy công việc sang queue nội bộ có giới hạn; tránh block đường phát khi thực hiện network call.

### 11.3 Thứ tự và tính đồng thời

Số \`sequenceNumber\` thường được emitter tăng theo thứ tự phát logic, nhưng việc dùng executor bất đồng bộ có thể làm thứ tự callback quan sát được khác với trình tự tạo. Listener không nên dựa vào giả định “callback luôn đơn luồng, luôn tuần tự” khi cấu hình broadcaster hoặc connector có thể thay đổi.

Nếu nhiều listener chạy đồng thời, filter cần thread-safe. Tránh mutable state không đồng bộ trong \`isNotificationEnabled\`.

## 12. Bảo mật: filter phía nhận không thay thế kiểm soát truy cập

Một yêu cầu phổ biến: “Chỉ cho đội A xem notification nhạy cảm, đặt filter của đội B để loại bỏ là đủ chưa?” Câu trả lời là **chưa đủ**. Khi thông tin đã được emitter công bố trên JMX, một client có quyền đăng ký khác có thể chọn filter khác hoặc không dùng filter. Cần bảo vệ từ:

1. **Nguồn phát**: không đưa secret/PII hay raw payload không được phép vào notification.
2. **Quyền JMX**: xác thực, phân quyền, mạng/TLS và hạn chế MBean phù hợp.
3. **Phân tách endpoint hoặc MBean**: nếu các nhóm client có quyền khác nhau, cấu trúc bề mặt quản trị phải phản ánh điều đó.
4. **Filter listener**: tối ưu thông tin cần hiển thị và giảm công việc callback sau khi truy cập đã được cấp.

Nếu muốn bảo mật theo tenant/user, phải có định danh đáng tin cậy và enforcement tại boundary của hệ thống, không dựa vào một lambda filter do chính client lựa chọn.

## 13. Chẩn đoán lỗi notification không được nhận

Dưới đây là quy trình điều tra từ nguồn tới đích:

| Triệu chứng | Khả năng | Kiểm tra |
|---|---|---|
| Không listener nào nhận | Emitter không gọi \`sendNotification\` hoặc chính sách phát chặn | Counter nội bộ tại nguồn, cấu hình enable |
| Một listener không nhận | Filter loại bỏ, listener đăng ký sai emitter | \`type\`, \`ObjectName\`, registration và filter |
| Listener nhận trùng | Đăng ký nhiều lần, nhiều nguồn phát giống nhau | Lifecycle đăng ký/gỡ, identity emitter |
| Listener nhận quá nhiều | \`NotificationFilterSupport\` prefix rộng, filter null | Danh sách enabled types, logic filter |
| Sự kiện bị trễ | Callback blocking, executor nghẽn, connector chậm | Queue/executor metrics, latency callback |
| Sau context restart mất sự kiện | Listener không đăng ký lại hoặc MBean thay instance | Lifecycle MBean và listener |
| Remote listener không giải mã được data | \`userData\` có class lạ/không serialize | Payload contract, MXBean/OpenType |
| Lượng event tăng CPU | Phát quá dày hoặc filter quá nặng | Tần suất, allocations và chi phí filter |

### 13.1 Phương pháp đo không gây sự cố

Một số bộ đếm hữu ích trong emitter:

\`\`\`text
eligibleEvents
notificationsCreated
notificationsSent
notificationsSuppressedBySourcePolicy
listenerCallbackFailures
\`\`\`

Cần định nghĩa tên metric chính xác; broadcaster có thể không biết mọi callback đã được client từ xa xử lý thành công. \`notificationsSent\` có thể chỉ nghĩa là emitter đã gọi \`sendNotification\`, không đảm bảo client đã nhận.

Để thử filter, tạo sự kiện kiểm tra có type được phân biệt và payload không nhạy cảm, tránh bắn failure giả vào pipeline cảnh báo production nếu nó có thể gây page/incident.

## 14. Bài tập vận dụng

### Bài 1: chọn tầng lọc

Một ứng dụng phát 50.000 notification \`cache.hit\` mỗi giây và 2 notification \`cache.eviction.failed\` mỗi phút. Dashboard chỉ cần hit ratio; nhóm trực ca cần biết failure.

Hướng thiết kế: dùng counter/hit ratio thay vì từng \`cache.hit\` notification ở nguồn; vẫn phát failure với payload nhỏ; listener trực ca lọc chính xác \`cache.eviction.failed\`. Nếu nhóm điều tra thực sự cần sample hit, có thể bổ sung sampling có hợp đồng riêng.

### Bài 2: phân biệt prefix và exact

\`\`\`java
NotificationFilterSupport f = new NotificationFilterSupport();
f.enableType("com.example.jobs");
\`\`\`

Filter có thể chấp nhận \`com.example.jobs.failed\` không? Có, vì matching theo prefix. Nếu chỉ muốn \`com.example.jobs\` chính xác, dùng \`NotificationFilter\` với \`equals\`.

### Bài 3: hai listener

Thiết kế một broadcaster phát \`job.started\`, \`job.completed\`, \`job.failed\`. Listener A chỉ nhận failure, listener B nhận started/completed. Viết hai \`NotificationFilter\` tương ứng và thử các type; mỗi listener phải được đăng ký và cleanup rõ ràng.

### Bài 4: security review

Một MBean phát notification chứa token trong \`userData\`. Một listener cố tình lọc theo \`type\` để loại notification token. Có giải quyết vấn đề không? Không. Token đã được công bố tới kênh quản trị và có thể bị một listener khác nhận; phải loại bỏ/che từ phía phát và áp dụng access controls thích hợp.

### Bài 5: case study chậm

Sau khi thêm listener gửi HTTP mỗi khi nhận failure, đường xử lý job bắt đầu chậm. Hãy xác định xem callback đang đồng bộ hay qua executor, đo latency và xem xét chuyển sang bounded asynchronous processing. Dù chuyển bất đồng bộ, cần xử lý queue full và shutdown; không được tạo executor không giới hạn.

## Tổng kết

**Lọc phía phát** là chính sách của nguồn: sự kiện nào được tạo và công bố qua JMX. Nó có thể tiết kiệm CPU/bộ nhớ và tránh phát nội dung không cần thiết nhưng cũng làm mất sự kiện đối với mọi subscriber. **Lọc phía nhận** là lựa chọn riêng của từng đăng ký listener: listener nào quan tâm tới notification đã được công bố. Nó giúp routing, giảm callback và tách nhu cầu của nhiều nhóm sử dụng, nhưng không xóa được chi phí tạo payload tại nguồn và không thay thế bảo mật hay lưu trữ bền vững.

Một thiết kế Spring JMX tốt xác định rõ hợp đồng loại sự kiện, đặt chính sách loại bỏ toàn cục ở nguồn, dùng \`NotificationFilter\` cho nhu cầu riêng của listener, giới hạn chi phí, quản lý lifecycle đăng ký/gỡ và có kênh quan sát độc lập để biết hệ thống thật sự đã phát, lọc và xử lý notification như thế nào.
