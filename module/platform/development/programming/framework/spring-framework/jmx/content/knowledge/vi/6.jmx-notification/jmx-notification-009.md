# Phát sự kiện quản trị từ MBean an toàn trong Spring Framework JMX

## 1. Mục tiêu

JMX Notification là cơ chế để một MBean chủ động thông báo sự kiện quản trị: một thành phần đổi trạng thái, tác vụ thất bại, ngưỡng tài nguyên bị vượt, hoặc một thao tác quản lý đã hoàn tất. Nhờ Notification, JMX client có thể nhận tín hiệu theo sự kiện thay vì liên tục polling từng attribute.

Trong Spring Framework, MBean có thể phát Notification qua \`NotificationPublisherAware\` và \`NotificationPublisher\`. Tuy nhiên, một notification là tín hiệu quản trị có thể đi tới công cụ bên ngoài JVM, nên cần thiết kế **loại sự kiện, dữ liệu công bố, concurrency, bảo mật, vòng đời và khả năng chịu lỗi** cẩn thận.

Nguyên tắc nền tảng: **phát thông tin vừa đủ để vận hành, không rò rỉ dữ liệu nhạy cảm, không để việc gửi notification quyết định tính đúng đắn của nghiệp vụ, và không giả định JMX notification là message queue bền vững**.

## 2. Notification trong kiến trúc JMX

Mỗi notification thường mang các thông tin:

| Trường | Ý nghĩa | Gợi ý thiết kế |
| --- | --- | --- |
| \`type\` | Loại sự kiện dạng chuỗi | Tên ổn định, có namespace như \`com.example.jobs.failed\` |
| \`source\` | Nguồn phát sự kiện | Tham chiếu MBean hoặc nguồn được exporter xử lý |
| \`sequenceNumber\` | Số thứ tự notification | Tăng đơn điệu cho từng nguồn phát |
| \`timeStamp\` | Thời điểm sự kiện | Dùng thời gian thực hợp lý; không suy ra độ trễ phân phối tuyệt đối |
| \`message\` | Mô tả ngắn | Tránh secrets, payload cá nhân và stack trace |
| \`userData\` | Dữ liệu bổ sung tùy chọn | Dữ liệu nhỏ, có schema, tương thích JMX remote |

Client đăng ký \`NotificationListener\` với MBeanServer để nhận notification từ MBean phù hợp. Client có thể áp dụng \`NotificationFilter\` nhằm chọn loại cần quan tâm. Spring thêm lớp tích hợp để bean phát và đăng ký listener thuận tiện hơn.

\`\`\`text
Spring service gặp sự kiện nghiệp vụ/điều hành
                 |
                 v
       MBean quản trị (Spring bean)
                 |
        NotificationPublisher
                 |
                 v
          MBeanServer / JMX
                 |
                 +--> NotificationListener A
                 +--> NotificationListener B
                 +--> Công cụ quản trị JMX
\`\`\`

Notification hữu ích cho *tín hiệu*, không bảo đảm client luôn online, không có cơ chế lưu trữ/replay mặc định và không thay thế hàng đợi tin nhắn dùng cho tác vụ quan trọng.

## 3. Spring cung cấp những thành phần nào?

Các API tích hợp chính nằm trong Spring Framework:

- \`org.springframework.jmx.export.notification.NotificationPublisherAware\`: interface callback để exporter cấp publisher cho một bean được export.
- \`org.springframework.jmx.export.notification.NotificationPublisher\`: đối tượng có phương thức \`sendNotification(Notification)\`.
- \`org.springframework.jmx.export.annotation.ManagedNotification\`: khai báo metadata loại notification có thể phát từ MBean.
- \`org.springframework.jmx.export.annotation.ManagedNotifications\`: nhóm các annotation notification nếu cần.
- \`org.springframework.jmx.export.NotificationListenerBean\` và notification listener mappings của exporter: gắn listener vào MBean dưới quản lý Spring.
- JMX chuẩn: \`javax.management.Notification\`, \`NotificationListener\`, \`NotificationFilter\`, \`MBeanServerConnection\`.

Khi bean được \`MBeanExporter\` export theo cơ chế phù hợp, callback \`setNotificationPublisher\` cho phép nó gửi notification qua publisher do Spring cấp. Chỉ implements \`NotificationPublisherAware\` nhưng không có quy trình export tương ứng thì không tự tạo khả năng phát ra JMX.

## 4. Ví dụ phát notification từ một Spring-managed MBean

Giả sử service xử lý job cần báo hai trạng thái vận hành: job kết thúc thất bại và job phục hồi. Một endpoint quản trị tách riêng có thể như sau:

\`\`\`java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=JobMonitor,name=Primary",
    description = "Trạng thái và thông báo quản trị job"
)
@ManagedNotifications({
    @ManagedNotification(
        name = "com.example.jobs.failed",
        description = "Một job thất bại"
    ),
    @ManagedNotification(
        name = "com.example.jobs.recovered",
        description = "Hệ thống xử lý job phục hồi"
    )
})
public class JobMonitor implements NotificationPublisherAware {
    private final AtomicLong sequence = new AtomicLong();
    private volatile NotificationPublisher publisher;
    private volatile String health = "UNKNOWN";

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute(description = "Trạng thái gần nhất")
    public String getHealth() {
        return health;
    }

    public void onJobFailure(String safeJobCategory) {
        health = "DEGRADED";
        emit(
            "com.example.jobs.failed",
            "Job failure in category: " + safeJobCategory
        );
    }

    public void onRecovery() {
        health = "HEALTHY";
        emit(
            "com.example.jobs.recovered",
            "Job processing recovered"
        );
    }

    private void emit(String type, String message) {
        NotificationPublisher currentPublisher = publisher;
        if (currentPublisher == null) {
            return; // Endpoint chưa được export hoặc đang trong lifecycle chuyển tiếp.
        }

        Notification event = new Notification(
            type,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            message
        );

        currentPublisher.sendNotification(event);
    }
}
\`\`\`

Bật annotation export trong ứng dụng:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
\`\`\`

Ở đây:

1. \`@ManagedResource\` khai báo MBean và ObjectName.
2. \`@ManagedNotifications\` công bố những loại sự kiện dự kiến trong metadata MBean.
3. \`NotificationPublisherAware\` nhận publisher do Spring cung cấp.
4. \`AtomicLong\` bảo đảm mỗi lần phát tăng sequence ngay cả khi nhiều thread gọi.
5. Notification dùng message ngắn, chứa loại job an toàn thay vì một record/payload thực tế.

Ví dụ dùng \`safeJobCategory\` với giả định đó là danh mục đã được kiểm soát, chẳng hạn \`billing\` hoặc \`export\`; không truyền thẳng mã định danh người dùng, token hay exception message chưa được lọc vào trường này.

**Phân biệt:** \`@ManagedNotification\` chỉ mô tả loại notification trong MBean metadata. Nó không tự tạo hay gửi notification. Để phát sự kiện, code vẫn phải gọi \`sendNotification\`.

## 5. Thiết kế loại sự kiện ổn định

Tên notification nên thể hiện ý nghĩa quản trị rõ ràng và đủ ổn định để công cụ vận hành đăng ký lâu dài.

Ví dụ:

\`\`\`text
com.example.cache.capacity.exceeded
com.example.jobs.failed
com.example.jobs.recovered
com.example.datasource.connection.degraded
com.example.datasource.connection.restored
\`\`\`

Tránh các tên chung như \`error\`, \`changed\`, \`event\`, \`operation\`, vì người nhận khó phân biệt và dễ xung đột trong cùng MBean.

Có thể coi notification type như một phần **management contract**: thay đổi tên loại sự kiện làm bộ lọc client cũ ngừng nhận. Nếu cần tiến hóa schema, nên thêm type hoặc version có mục đích rõ ràng, đồng thời duy trì khả năng tương thích trong giai đoạn chuyển đổi.

Đối với cặp trạng thái, dùng các tên nhất quán: \`degraded\` / \`restored\`, \`threshold.exceeded\` / \`threshold.cleared\`. Các dạng này cho phép hệ thống cảnh báo tạo và giải quyết incident rõ nghĩa.

## 6. Không phát dữ liệu nhạy cảm

Một notification có thể được nhận bởi client remote được cấp quyền trên JMX connector; sau đó client có thể log, lưu hoặc chuyển tiếp dữ liệu. Do đó hãy xem payload notification là **dữ liệu quản trị có khả năng rời khỏi tiến trình ứng dụng**.

Không nên chứa trong \`message\` hoặc \`userData\`:

- Password, API key, access token, session token hay header xác thực.
- Dữ liệu cá nhân/khách hàng, nội dung hồ sơ, địa chỉ, số điện thoại.
- Raw SQL chứa tham số nhạy cảm, chuỗi connection chứa credentials.
- Exception stack trace đầy đủ, request body hoặc thông tin nội bộ vượt nhu cầu xử lý sự cố.
- Danh sách hàng nghìn đối tượng gây lộ dữ liệu và tốn tài nguyên truyền tải.

Thay vì:

\`\`\`java
new Notification(
    "com.example.jobs.failed",
    this,
    sequence.incrementAndGet(),
    "Job payload failed: " + payload.toString()
);
\`\`\`

hãy gửi tín hiệu tối thiểu:

\`\`\`java
new Notification(
    "com.example.jobs.failed",
    this,
    sequence.incrementAndGet(),
    "A billing job failed"
);
\`\`\`

Thông tin chi tiết nên ghi qua hệ thống logging/observability có kiểm soát truy cập và retention riêng. Có thể phát một correlation ID không nhạy cảm để kết nối notification với log, nhưng phải đánh giá xem ID có lộ danh tính hoặc chi tiết nghiệp vụ hay không.

## 7. Chọn userData nhỏ và tương thích remote JMX

\`Notification.setUserData(Object)\` cho phép kèm dữ liệu bổ sung, nhưng không phải mọi Java object đều thuận tiện cho client remote. Với remote connector, serialization/classloading và tương thích phiên bản có thể là vấn đề.

Nếu thực sự cần dữ liệu có cấu trúc, cân nhắc các kiểu đơn giản hoặc Open MBean types như \`CompositeData\`. Ví dụ dùng \`CompositeDataSupport\` cho thông tin tổng hợp:

\`\`\`java
import javax.management.Notification;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

String[] names = {"category", "failureCount"};
OpenType<?>[] types = {
    SimpleType.STRING,
    SimpleType.LONG
};

CompositeType schema = new CompositeType(
    "JobFailureSummary",
    "Sanitized job failure summary",
    names,
    new String[] {"Job category", "Failure count"},
    types
);

CompositeData data = new CompositeDataSupport(
    schema,
    names,
    new Object[] {"billing", 12L}
);

Notification event = new Notification(
    "com.example.jobs.failed",
    this,
    sequence.incrementAndGet(),
    "Job failure rate increased"
);
event.setUserData(data);
publisher.sendNotification(event);
\`\`\`

Trong code thực tế nên tạo \`CompositeType\` một lần (constant/static immutable metadata) thay vì xây schema mới cho mọi sự kiện. Chỉ gửi các trường có ý nghĩa cho client; giữ payload giới hạn kích thước và có schema ổn định.

## 8. Sequence number và concurrency

Theo JMX, mỗi \`Notification\` có \`sequenceNumber\` để client biết thứ tự tương đối của sự kiện phát từ cùng nguồn. Dùng biến \`long\` thông thường với \`++sequence\` trong nhiều thread có thể gây race, làm trùng hoặc bỏ số.

\`\`\`java
private final AtomicLong sequence = new AtomicLong();

long next = sequence.incrementAndGet();
\`\`\`

\`AtomicLong\` giúp số cấp phát là duy nhất và tăng theo thứ tự atomic, nhưng **không tự bảo đảm callback của các thread được nhận cùng thứ tự với số sequence**. Thread A có thể cấp số 1 rồi bị tạm dừng, còn thread B cấp số 2 và phát trước. Nếu hệ thống thực sự yêu cầu thứ tự phát nghiêm ngặt, cần serialize khâu tạo/phát qua một hàng đợi nội bộ hoặc một executor đơn luồng, kèm chính sách giới hạn dung lượng.

Timestamp từ \`System.currentTimeMillis()\` cũng không bảo đảm đơn điệu tuyệt đối vì đồng hồ hệ thống có thể điều chỉnh. Sequence number phù hợp để nhận ra thứ tự logic của sự kiện từ cùng nguồn, nhưng không phải bằng chứng giao hàng đầy đủ hay một durable offset.

### Tránh phát notification trong critical section

Không nên giữ lock nghiệp vụ khi gọi \`sendNotification\`, nhất là khi callback listener hoặc connector có thể thực hiện công việc đáng kể:

\`\`\`java
// Không nên giữ lock nội bộ xuyên suốt lúc phát tín hiệu.
synchronized (stateLock) {
    updateState();
    publisher.sendNotification(event);
}
\`\`\`

Một cách thiết kế dễ kiểm soát hơn:

\`\`\`java
Notification event;
synchronized (stateLock) {
    updateState();
    event = makeEventFromSanitizedSnapshot();
}
publisher.sendNotification(event);
\`\`\`

Trong đó \`makeEventFromSanitizedSnapshot()\` cần là hàm chỉ tạo dữ liệu đã được kiểm soát. Điều này giảm rủi ro listener chậm, callback gây reentrancy hoặc code notification ảnh hưởng thời gian giữ lock.

## 9. Notification không phải cơ chế bảo đảm giao hàng

JMX notification thích hợp để cập nhật trạng thái gần thời gian thực. Nó không mặc định cung cấp:

- Message persistence, durable subscription hay replay lịch sử sau reconnect.
- Exactly-once delivery giữa JVM và remote client.
- Transaction atomic giữa cập nhật database và phát notification.
- Backpressure/queue durability cho mọi tình huống client chậm.
- Tự động retry cho các consumer offline.

Vì vậy, **không được dùng việc nhận notification làm nguồn sự thật duy nhất** cho một trạng thái nghiệp vụ quan trọng. Ví dụ nếu client phải biết job có thất bại hay không, MBean nên có attribute cho trạng thái hiện tại hoặc một hệ thống trạng thái khác bền vững:

\`\`\`java
@ManagedAttribute
public long getFailedJobCount() {
    return jobMetrics.failedCount();
}

@ManagedAttribute
public String getCurrentHealth() {
    return healthService.currentHealth();
}
\`\`\`

Notification báo “có thay đổi”; attribute cho phép client **đọc lại trạng thái** sau reconnect hoặc khi nghi ngờ đã bỏ lỡ tín hiệu. Nếu yêu cầu giao hàng đáng tin cậy cho workflow nghiệp vụ, dùng broker/event infrastructure thích hợp và coi JMX chỉ là bề mặt quản trị bổ trợ.

## 10. Bảo vệ luồng nghiệp vụ khỏi lỗi phát notification

Việc phát notification không nên làm giao dịch nghiệp vụ thất bại nếu không có yêu cầu được thiết kế rõ ràng cho điều đó.

Ví dụ một wrapper quản trị:

\`\`\`java
private void publishSafely(Notification event) {
    NotificationPublisher current = publisher;
    if (current == null) {
        return;
    }

    try {
        current.sendNotification(event);
    } catch (RuntimeException ex) {
        // Log có giới hạn và không chứa payload nhạy cảm.
        // Không làm hỏng thao tác nghiệp vụ chỉ vì kênh quản trị.
        managementLogger.warn(
            "Could not emit JMX notification type={}",
            event.getType(),
            ex
        );
    }
}
\`\`\`

\`managementLogger\` ở đây là một logger được cấu hình trong class (ví dụ SLF4J); đoạn mã chỉ minh họa hàm bao phát notification. Một exception tùy ngữ cảnh có thể cần được ghi nhận qua counter/log nội bộ, nhưng tránh log vô hạn nếu kênh thông báo gặp sự cố lặp lại.

Nếu bất kỳ notification nào bị mất, ứng dụng vẫn phải giữ trạng thái nghiệp vụ đúng và có cơ chế query lại. Không nên retry vô hạn hoặc block thread nghiệp vụ để “đảm bảo” notification luôn tới nơi.

### Chống notification storm

Khi lỗi lặp đi lặp lại hàng nghìn lần mỗi giây, phát một notification cho mỗi lỗi có thể tạo tải lớn trên MBeanServer và client.

Các kỹ thuật phù hợp:

1. **Deduplication:** chỉ thông báo khi chuyển trạng thái \`HEALTHY → DEGRADED\` hoặc khi incident thay đổi.
2. **Rate limit:** giới hạn số sự kiện cùng loại trong một khoảng thời gian.
3. **Aggregation:** thông báo “120 lỗi trong 60 giây” thay vì 120 notifications.
4. **Hysteresis:** dùng ngưỡng vào/ra khác nhau để tránh trạng thái dao động liên tục.
5. **Counter attribute:** đưa tổng số lỗi vào MBean attribute để client đọc định kỳ.

Ví dụ logic khái quát:

\`\`\`java
if (previousHealth == HEALTHY && nextHealth == DEGRADED) {
    emitDegradedNotification();
}
// Các lỗi tiếp theo cập nhật failedCount, không phát trùng liên tục.
\`\`\`

Đối với chuyển trạng thái trên nhiều thread, dùng lock hoặc atomic state transition để chỉ một thread thực sự sở hữu quyền thông báo chuyển trạng thái. Nếu chỉ dùng so sánh hai biến rời rạc, nhiều thread có thể cùng phát notification giống nhau.

## 11. Khai báo metadata để client khám phá các loại sự kiện

Một MBean có thể công bố notification types qua \`MBeanNotificationInfo\`. Spring hỗ trợ biểu diễn annotation:

\`\`\`java
@ManagedNotifications({
    @ManagedNotification(
        name = "com.example.jobs.failed",
        description = "Job processing failure"
    ),
    @ManagedNotification(
        name = "com.example.jobs.recovered",
        description = "Job processing recovered"
    )
})
@ManagedResource(
    objectName = "com.example.jobs:type=JobMonitor,name=Primary"
)
public class JobMonitor {
    // Kết hợp NotificationPublisherAware khi cần phát thực tế.
}
\`\`\`

Sau khi MBean đã đăng ký, client có thể khám phá thông tin bằng \`getMBeanInfo\`:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.ObjectName;

ObjectName name =
    new ObjectName("com.example.jobs:type=JobMonitor,name=Primary");

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanNotificationInfo notification : info.getNotifications()) {
    System.out.println(notification.getDescription());
    for (String type : notification.getNotifTypes()) {
        System.out.println("  - " + type);
    }
}
\`\`\`

Metadata giúp client hiểu những sự kiện dự kiến, nhưng không bảo đảm mọi type sẽ phát trong một phiên chạy. Đồng thời code vẫn có thể phát notification không được mô tả đầy đủ nếu cấu hình sai; nên duy trì danh sách loại sự kiện nhất quán giữa annotation và implementation.

## 12. Nhận notification từ MBeanServer

JMX client dùng \`NotificationListener\` và \`addNotificationListener\`:

\`\`\`java
import javax.management.Notification;
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName name =
    new ObjectName("com.example.jobs:type=JobMonitor,name=Primary");

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.failed");
filter.enableType("com.example.jobs.recovered");

NotificationListener listener = (Notification event, Object handback) -> {
    // Xử lý rất ngắn; chuyển tác vụ nặng sang executor phù hợp.
    System.out.printf(
        "JMX type=%s sequence=%d message=%s%n",
        event.getType(),
        event.getSequenceNumber(),
        event.getMessage()
    );
};

server.addNotificationListener(name, listener, filter, null);

// Khi không cần nhận nữa:
server.removeNotificationListener(name, listener);
\`\`\`

Client phải kết nối đúng \`MBeanServer\` nơi MBean được đăng ký. Đoạn ví dụ giả định biến \`server\` là \`MBeanServer\` hoặc \`MBeanServerConnection\` hợp lệ và MBean hiện tồn tại.

Các callback listener không nên thực hiện tác vụ lâu, thao tác mạng không giới hạn hoặc logic có thể gây deadlock. Khi cần xử lý bất đồng bộ, chuyển một snapshot dữ liệu nhỏ sang executor có queue giới hạn. Listener cũng cần xử lý lỗi nội bộ để tránh một callback lỗi làm ảnh hưởng luồng phân phối; phía client remote cần quan sát reconnect và tái đăng ký listener khi cần.

Spring hỗ trợ cấu hình listener thông qua \`NotificationListenerBean\` và các mapping của exporter nếu listener nằm trong cùng mô hình quản lý Spring.

## 13. Ví dụ tình huống: cảnh báo cache gần đầy

Một MBean \`CacheMonitor\` expose:

\`\`\`text
ObjectName: com.example.cache:type=CacheMonitor,name=Products

Attributes:
  Capacity
  CurrentEntries
  UtilizationRatio
  State

Notification types:
  com.example.cache.capacity.high
  com.example.cache.capacity.normal
\`\`\`

Khi \`UtilizationRatio\` vượt 0.90, service chuyển \`NORMAL → HIGH\` và phát \`capacity.high\`. Khi tỷ lệ giảm xuống dưới 0.75, service chuyển \`HIGH → NORMAL\` và phát \`capacity.normal\`. Khoảng cách hai ngưỡng (hysteresis) hạn chế phát qua lại liên tục khi cache dao động quanh 0.90.

Một client nhận \`capacity.high\` có thể đọc lại \`CurrentEntries\` và \`Capacity\` để quyết định mức cảnh báo. Nếu client bị ngắt kết nối lúc notification phát, sau khi reconnect nó vẫn có thể đọc \`State\` và các counters. Notification chỉ đóng vai trò tín hiệu chuyển trạng thái, không phải dữ liệu duy nhất mô tả tình trạng cache.

Payload nên chứa loại cache và trạng thái tổng hợp, không chứa danh sách cache keys hoặc dữ liệu customer đang lưu.

## 14. Lưu ý bảo mật và vận hành

**Phạm vi truy cập:** Việc \`@EnableMBeanExport\` hoặc \`MBeanExporter\` đăng ký MBean trong JVM không tự động mở cổng JMX remote. Nhưng khi remote connector được cấu hình, metadata, attribute và notification có thể được truy cập từ bên ngoài theo các quyền được cấp. Bảo vệ connector bằng cấu hình mạng, xác thực, phân quyền và mã hóa phù hợp môi trường.

**Đầu vào và dữ liệu:** Không tin tưởng tuyệt đối vào chuỗi do service/exception truyền vào message. Normalize hoặc ánh xạ sang mã sự kiện an toàn; giới hạn chiều dài message; không dùng toString của các object nghiệp vụ hoặc request.

**Chi phí:** Không tạo notification trên hot path có tần suất cực cao mà không aggregation. Theo dõi số sự kiện phát, số sự kiện bị bỏ do rate-limit và số lỗi gửi notification qua metrics/attributes nội bộ.

**Lifecycle:** Publisher có thể chưa sẵn sàng trước khi MBean được export hoặc trong giai đoạn shutdown. Xử lý null hoặc trì hoãn việc phát tín hiệu theo thiết kế. Không giả định cùng một publisher tồn tại mãi nếu context được khởi tạo lại.

**Tính tương thích:** Notification type, ý nghĩa message, schema \`userData\` và contract ObjectName nên ổn định. Đổi kiểu dữ liệu hoặc tên type có thể làm bộ lọc/consumer cũ thất bại.

## 15. Checklist thiết kế

Trước khi công bố một loại notification quản trị, hãy làm rõ:

- **Trigger:** chính xác khi nào phát, có cần chuyển trạng thái hoặc rate-limit không?
- **Name:** type có namespace rõ ràng và ổn định không?
- **Data:** message/userData có bị lộ secrets, PII, payload hoặc dữ liệu quá lớn không?
- **Order:** sequence có thread-safe không, có thật sự cần thứ tự nhận nghiêm ngặt không?
- **Failure:** kênh gửi lỗi có làm hỏng logic nghiệp vụ không?
- **Recovery:** client có thể đọc trạng thái hiện tại nếu bỏ lỡ sự kiện không?
- **Client:** listener có nhẹ, có cleanup và có xử lý reconnect không?
- **Security:** JMX connector và các operation/attributes liên quan được hạn chế truy cập như thế nào?

Đây là các câu hỏi thiết kế, không phải việc Spring tự động thực hiện thay cho ứng dụng.

## 16. Mô hình tư duy

\`\`\`text
Trạng thái nghiệp vụ / tín hiệu vận hành
                  |
          Kiểm tra trigger
          lọc dữ liệu nhạy cảm
          deduplicate / aggregate
                  |
                  v
        Notification(type, seq,
          timestamp, safe message)
                  |
         NotificationPublisher
                  |
                  v
           JMX MBeanServer
                  |
          listener / remote tool
                  |
          đọc lại MBean attributes
          nếu cần trạng thái mới nhất
\`\`\`

**Điều cần nhớ:** Spring giúp MBean phát notification thông qua \`NotificationPublisherAware\` và \`NotificationPublisher\`, đồng thời công bố metadata với \`@ManagedNotification\`. Để an toàn, hãy giữ event type ổn định, chỉ gửi dữ liệu quản trị tối thiểu, dùng sequence thread-safe, hạn chế storm, không block critical path, xử lý lỗi phát độc lập với nghiệp vụ và luôn cung cấp cách query lại trạng thái. JMX Notification là tín hiệu quản trị, không phải một cơ chế truyền sự kiện bền vững có bảo đảm giao hàng.
