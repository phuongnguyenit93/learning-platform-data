# Phát notification từ MBean được export trong Spring Framework JMX

## 1. Mục tiêu

JMX (Java Management Extensions) không chỉ cho phép công cụ quản trị đọc attribute hoặc gọi operation của MBean, mà còn hỗ trợ **notification**: thông điệp sự kiện do MBean phát cho những listener đã đăng ký. Trong Spring Framework JMX, một Spring-managed bean được export bằng `MBeanExporter` có thể phát notification thuận tiện thông qua giao diện `NotificationPublisherAware`.

Ví dụ một worker pool có thể phát sự kiện khi đạt ngưỡng backlog, bắt đầu chuyển trạng thái degraded hoặc hoàn thành một lần refresh. Thay vì buộc operator polling trạng thái liên tục, ứng dụng gửi một notification khi sự kiện xảy ra.

**Điểm cốt lõi:** bean cần được export đúng qua hạ tầng JMX của Spring, nhận `NotificationPublisher` trong quá trình export, tạo một `javax.management.Notification` có type/source/sequence/timestamp rõ ràng và gọi `sendNotification`. Khai báo metadata notification giúp client khám phá loại sự kiện, nhưng metadata **không tự động tạo hoặc phát sự kiện**.

## 2. Notification trong JMX là gì?

JMX notification là một event được phát bởi một notification broadcaster tới các listener đăng ký với MBeanServer hoặc MBeanServerConnection.

```text
Spring-managed resource
      |
      | state change / management event
      v
JMX NotificationPublisher
      |
      v
Exported MBean (ObjectName)
      |
      v
MBeanServer
      |
      +--> NotificationListener A
      +--> NotificationListener B
      +--> JConsole / JMX client
```

Một `Notification` chứa các thông tin cơ bản:

- `type`: định danh loại sự kiện, ví dụ `com.example.jobs.queue.threshold`.
- `source`: đối tượng nguồn của sự kiện, thường được khai báo nhất quán với MBean nguồn.
- `sequenceNumber`: thứ tự các sự kiện của broadcaster, thường tăng đơn điệu.
- `timeStamp`: thời điểm tạo sự kiện, tính bằng milliseconds epoch.
- `message`: mô tả ngắn gọn, dễ hiểu.
- `userData`: dữ liệu bổ sung, chỉ dùng khi có schema rõ ràng và không chứa secrets.

Notification không phải Java exception, không phải HTTP callback và không đảm bảo lưu trữ lâu dài. Nó chủ yếu phục vụ quan sát **theo sự kiện** trên một kết nối JMX đang hoạt động.

## 3. Phân biệt attribute, operation và notification

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| JMX attribute | Trạng thái hiện tại có thể đọc/ghi | `QueueDepth`, `Enabled`, `LastRefreshEpochMillis` |
| JMX operation | Hành động mà client có thể yêu cầu | `requestRefresh()` |
| JMX notification | Sự kiện do MBean chủ động thông báo | `queue.threshold`, `refresh.completed` |

Ví dụ một hệ thống đang có 1.000 job chờ xử lý:

- Client đọc `QueueDepth` để biết **trạng thái hiện tại**.
- Operator gọi `requestScaleUp()` để yêu cầu **thao tác**.
- MBean phát notification `com.example.jobs.queue.threshold` khi backlog vượt ngưỡng, cho client biết **sự kiện chuyển ngưỡng**.

Ba thành phần bổ sung cho nhau. Notification không thay thế attribute vì listener có thể bị ngắt kết nối hoặc đăng ký sau khi sự kiện đã xảy ra. Một monitoring system đáng tin cậy nên vừa đọc snapshot hiện tại, vừa xử lý notification như tín hiệu hữu ích.

## 4. Spring cung cấp những thành phần nào?

Spring JMX có các API nổi bật:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `MBeanExporter` | Export Spring bean thành MBean, quản lý đăng ký/lifecycle |
| `NotificationPublisherAware` | Callback để Spring truyền `NotificationPublisher` vào bean được export |
| `NotificationPublisher` | API Spring để gửi JMX `Notification` |
| `@ManagedResource` | Đánh dấu tài nguyên quản trị và metadata ObjectName |
| `@ManagedNotification` | Mô tả notification type và metadata cho client JMX |
| `@ManagedNotifications` | Khai báo nhiều notification types trên resource |
| `@ManagedAttribute` | Công bố trạng thái có thể đọc hoặc ghi |
| `@ManagedOperation` | Công bố hành động quản trị |
| `NotificationListener` | Interface JMX chuẩn nhận notification từ MBean |
| `MBeanServerConnection.addNotificationListener` | Đăng ký listener qua JMX API |

Thông thường `NotificationPublisherAware` nằm trong `org.springframework.jmx.export.notification`; các annotation `ManagedNotification`/`ManagedNotifications` nằm trong `org.springframework.jmx.export.annotation`.

## 5. Luồng phát notification từ bean đã export

Quy trình cơ bản:

1. Spring khởi tạo management bean và export qua `MBeanExporter`.
2. Exporter tạo/adapt MBean phù hợp và đăng ký dưới một `ObjectName`.
3. Nếu bean hỗ trợ `NotificationPublisherAware`, Spring truyền publisher cho bean.
4. Khi ứng dụng phát hiện sự kiện thực tế, bean tạo `Notification`.
5. Bean gọi `publisher.sendNotification(notification)`.
6. MBeanServer chuyển notification tới các listener đã đăng ký tương ứng với ObjectName.

Không được nhầm bước **khai báo loại notification** với bước **phát notification**. `@ManagedNotification` giúp mô tả contract, nhưng sự kiện chỉ được gửi khi code gọi publisher.

## 6. Ví dụ đầy đủ: WorkerPoolManagement phát notification

Giả sử ứng dụng muốn phát sự kiện khi số job chờ đạt ngưỡng. Tạo management adapter:

```java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Main",
    description = "Giám sát worker pool và phát sự kiện vận hành"
)
@ManagedNotifications({
    @ManagedNotification(
        name = "com.example.jobs.queue.threshold",
        description = "Số job chờ vượt ngưỡng cảnh báo"
    ),
    @ManagedNotification(
        name = "com.example.jobs.refresh.completed",
        description = "Refresh worker pool đã hoàn thành"
    )
})
public class WorkerPoolManagement implements NotificationPublisherAware {
    private final WorkerPoolService service;
    private final AtomicLong sequence = new AtomicLong();
    private volatile NotificationPublisher publisher;

    public WorkerPoolManagement(WorkerPoolService service) {
        this.service = service;
    }

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute(description = "Số job đang chờ")
    public long getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedOperation(description = "Yêu cầu refresh worker pool")
    public void requestRefresh() {
        service.requestRefresh();
    }

    public void onQueueThresholdExceeded(long pending) {
        publish(
            "com.example.jobs.queue.threshold",
            "Queue backlog exceeded warning threshold",
            pending
        );
    }

    public void onRefreshCompleted() {
        publish(
            "com.example.jobs.refresh.completed",
            "Worker pool refresh completed",
            null
        );
    }

    private void publish(String type, String message, Object userData) {
        NotificationPublisher current = publisher;
        if (current == null) {
            // Chưa export xong: không có JMX publisher.
            return;
        }

        Notification event = new Notification(
            type,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            message
        );
        if (userData != null) {
            event.setUserData(userData);
        }
        current.sendNotification(event);
    }
}
```

`WorkerPoolService` là service của ứng dụng, cung cấp `pendingCount()` và `requestRefresh()`; hai callback `onQueueThresholdExceeded`/`onRefreshCompleted` phải được code nghiệp vụ hoặc một component sự kiện gọi đúng thời điểm. Chúng không tự được Spring JMX gọi khi metric đổi.

**Lưu ý source:** ví dụ dùng `this` làm notification source trong phần tạo event. Trong hệ thống thực, nhất là khi dùng ModelMBean/proxy, nên kiểm tra notification mà client thực sự nhận được và thống nhất source với contract của MBean. Client thường dùng ObjectName lúc đăng ký listener để nhận biết đối tượng gửi, không nên dựa vào serialization của cả implementation object.

## 7. Bật export cho annotated MBean

Với Spring Framework:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {
}
```

Để management bean được export bằng annotation, cần đưa nó vào `ApplicationContext` (ví dụ qua `@ComponentScan` hoặc `@Bean`) và dùng hạ tầng export phù hợp. `@ManagedResource.objectName` định danh MBean. MBeanServer cần nhìn thấy MBean đã đăng ký để JMX client kết nối.

Nếu cấu hình `MBeanExporter` thủ công, phải bảo đảm assembler đọc annotation và naming strategy phù hợp. Tránh dùng hai exporter đăng ký cùng ObjectName, và tránh giả định bean nhận publisher khi chưa được export.

## 8. Vì sao dùng NotificationPublisherAware?

Một implementation JMX thuần có thể kế thừa `NotificationBroadcasterSupport`, quản lý listener và tự phát event. Trong một Spring-managed POJO được export bằng `MBeanExporter`, `NotificationPublisherAware` giúp tách phần gửi notification khỏi việc tự viết mã broadcaster và register MBean.

```text
Application service -> management bean
                            |
               NotificationPublisherAware
                            |
                  NotificationPublisher
                            |
                     Spring JMX adapter
                            |
                        MBeanServer
```

Ưu điểm:

- Service không cần trực tiếp xử lý MBeanServer hoặc ObjectName để phát sự kiện.
- Spring cung cấp publisher gắn với MBean được export.
- Code phát event có thể ở management adapter với contract vận hành riêng.
- Metadata notification có thể được khai báo bằng annotation.
- Vòng đời đăng ký/hủy đăng ký được tích hợp với exporter.

Tuy nhiên publisher không phải message broker hoặc event store. Nếu cần delivery guarantee, replay, durable consumer offsets hoặc cross-service event stream, nên dùng hạ tầng messaging phù hợp thay vì coi JMX notification như queue nghiệp vụ.

## 9. Notification type và metadata

Client JMX có thể xem `MBeanInfo.getNotifications()` để biết các loại sự kiện mà MBean công bố.

Ví dụ:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = server.getMBeanInfo(objectName);
for (MBeanNotificationInfo notification : info.getNotifications()) {
    System.out.println(notification.getDescription());
    for (String type : notification.getNotifTypes()) {
        System.out.println("  type=" + type);
    }
}
```

Metadata nên dùng type có namespace ổn định:

```text
com.example.jobs.queue.threshold
com.example.jobs.refresh.completed
com.example.jobs.pool.degraded
```

Đừng dùng type chung chung như `error`, `event`, `state` trong ứng dụng có nhiều MBean. Một type rõ ràng giúp listener lọc và giải thích sự kiện.

**Khai báo metadata không thay thế việc phát.** Một notification type có thể xuất hiện trong `MBeanInfo` mà chưa từng có sự kiện nào được gửi. Ngược lại, sự kiện có thể được gửi nhưng nếu metadata không phản ánh đúng type thì công cụ quản trị khó khám phá contract và người vận hành dễ nhầm.

## 10. Đăng ký NotificationListener phía JMX client

JMX API chuẩn cho phép listener đăng ký theo ObjectName.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=WorkerPool,name=Main"
);

NotificationListener listener = (Notification event, Object handback) -> {
    System.out.printf(
        "type=%s sequence=%d message=%s%n",
        event.getType(),
        event.getSequenceNumber(),
        event.getMessage()
    );
};

server.addNotificationListener(name, listener, null, null);

try {
    // Trong thời gian này ứng dụng có thể phát notification.
    // Ví dụ callback onQueueThresholdExceeded được gọi ở nơi khác.
} finally {
    server.removeNotificationListener(name, listener);
}
```

Đây là ví dụ local, giả định MBean đã được đăng ký vào platform MBeanServer. Nếu Spring exporter dùng server khác, client phải dùng đúng server đó. Với remote JMX, client sử dụng `MBeanServerConnection` lấy qua JMXConnector và cần cấu hình connector bảo mật.

Listener phải sống đủ lâu để nhận sự kiện; không được đăng ký rồi remove ngay trước khi sự kiện thực sự phát. Trong code chạy lâu, lifecycle owner phải giữ listener và unregister khi ngừng, tránh rò rỉ reference.

## 11. Lọc notification theo type

JMX cung cấp `NotificationFilterSupport` để chặn những type không cần xử lý:

```java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.queue.threshold");

server.addNotificationListener(name, listener, filter, null);
```

Filter giúp listener tập trung vào một nhóm sự kiện, nhưng không phải authorization mechanism. Nếu client được cấp quyền đọc notification thì những điều kiện quyền của JMX connector vẫn phải được bảo vệ riêng.

Trường `source`, `userData` và `message` cần có schema tương thích lâu dài. Không đưa secret hoặc raw business object graph vào notification vì client có thể là remote và payload có thể bị ghi log.

## 12. Phát notification khi có sự kiện thực tế

Điểm kích hoạt không nhất thiết là JMX operation. Có ba hướng phổ biến:

1. **Từ business event:** worker pool nhận thấy ngưỡng backlog và gọi management publisher.
2. **Từ operation quản trị:** sau khi `requestRefresh()` hoàn tất, hệ thống gửi `refresh.completed`.
3. **Từ health/state transition:** khi subsystem chuyển từ UP sang DEGRADED, publisher gửi notification có type rõ ràng.

Không nên phát một notification mới mỗi lần JMX client gọi getter:

```java
@ManagedAttribute
public int getQueueDepth() {
    publishWarning(); // Anti-pattern: polling tạo sự kiện giả.
    return queue.depth();
}
```

Getter được monitoring polling thường xuyên; nếu side effect là phát notification, hệ thống có thể spam sự kiện và làm lệch kết quả. Thay vào đó, phát sự kiện khi state thực sự chuyển ngưỡng, có thể thêm debounce/hysteresis.

Ví dụ chỉ phát khi chuyển từ dưới ngưỡng lên trên ngưỡng:

```java
private final AtomicBoolean aboveThreshold = new AtomicBoolean();

public void onQueueDepthChanged(long depth) {
    boolean nowAbove = depth >= 500;
    boolean wasAbove = aboveThreshold.getAndSet(nowAbove);
    if (nowAbove && !wasAbove) {
        onQueueThresholdExceeded(depth);
    }
}
```

Ví dụ cần import `java.util.concurrent.atomic.AtomicBoolean`. Cách này không xử lý mọi trường hợp distributed state/hysteresis, nhưng minh họa việc tránh lặp thông báo vô ích. Trong production có thể cần cooldown, xác nhận trạng thái liên tục hoặc tính threshold theo business rules.

## 13. Sequence number và concurrency

Thông thường mỗi broadcaster duy trì sequence number tăng dần:

```java
private final AtomicLong sequence = new AtomicLong();

long sequenceNumber = sequence.incrementAndGet();
```

`AtomicLong` tránh hai thread phát event cùng lấy cùng một sequence number. Tuy nhiên sequence number không bảo đảm mọi listener sẽ nhận đủ toàn bộ sự kiện. Khi remote connector bị ngắt, notification có thể bị mất; một sequence gap là tín hiệu hữu ích nhưng không thay thế durable event log.

Spring application có thể phát notification từ nhiều thread, vì vậy cần cân nhắc:

- Thread-safety của state kích hoạt sự kiện.
- Tránh gọi listener hoặc notification publisher trong lock quan trọng.
- Tránh payload lớn hoặc blocking work trong đường phát event.
- Nếu phát rất thường xuyên, giới hạn tốc độ hoặc gộp sự kiện.
- Không suy diễn ordering tuyệt đối qua nhiều broadcaster hoặc nhiều JVM.

Sequence number nên được xem là thứ tự tương đối của sự kiện do **một nguồn phát** tạo, không phải global sequence cho cả hệ thống.

## 14. Event payload: userData nên chứa gì?

`Notification.setUserData(Object)` có thể đính kèm dữ liệu bổ sung. Tuy nhiên remote JMX có thể cần serialize dữ liệu qua Java connector, nên không nên đính kèm object domain phức tạp hoặc thông tin nhạy cảm.

Ví dụ đơn giản:

```java
Notification notification = new Notification(
    "com.example.jobs.queue.threshold",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Queue warning threshold exceeded"
);
notification.setUserData(Long.valueOf(750));
publisher.sendNotification(notification);
```

Đối với payload nhiều trường, có thể dùng các kiểu JMX Open Types như `CompositeData` hoặc cấu trúc đơn giản có schema được document rõ ràng. Tránh phụ thuộc class application-specific phía remote client nếu không có hợp đồng versioned.

Không gửi JWT, password, session token, PII hay stack trace chứa dữ liệu nhạy cảm vào message/userData. Notification có thể được ghi log, hiển thị trong công cụ hoặc chuyển tới nhiều listener có quyền khác nhau.

## 15. Lifecycle của publisher

`NotificationPublisherAware.setNotificationPublisher` được gọi khi Spring thiết lập đường export phù hợp. Trước thời điểm đó, reference tới publisher có thể là null.

Vì vậy code phát event nên hiểu rõ:

- Khi bean được tạo nhưng chưa export, notification có được bỏ qua hay được buffer?
- Nếu MBean đã unregister, việc tiếp tục phát event có ý nghĩa gì?
- Nếu bean được export lại, publisher có được thay thế đúng không?
- Ai sở hữu quá trình cleanup khi context đóng?

Trong ví dụ đã dùng `volatile NotificationPublisher` và kiểm tra null để tránh dereference trước khi export. Đây là policy đơn giản **bỏ qua notification khi chưa có publisher**. Nếu ứng dụng yêu cầu không mất event, cần một cơ chế event store hoặc broker độc lập, không dựa vào JMX publisher.

Không nên giữ publisher trong static global state rồi phát sau khi ApplicationContext đã đóng. Điều này làm vòng đời đối tượng khó kiểm soát và có thể giữ references tới MBeanServer/beans cũ.

## 16. Notification listener trong Spring

Ngoài JMX API trực tiếp, `MBeanExporter` hỗ trợ cấu hình notification listeners để gắn listener với các MBean được export. Cấu hình này có thể tiện khi listener cũng là Spring-managed bean.

Ý tưởng:

```text
Spring MBeanExporter
   |
   +-- exported MBean
   |
   +-- configured NotificationListener
           |
           +-- xử lý notification type đã chọn
```

Trong dự án thực, cần dùng cấu hình listener mapping thích hợp với phiên bản Spring Framework và ObjectName. Nếu listener phải nhận notification từ MBean đã đăng ký ở nơi khác hoặc qua remote connector, dùng `MBeanServerConnection.addNotificationListener` với server thích hợp có thể dễ hiểu hơn.

Không nhầm `ApplicationEventPublisher` của Spring với `NotificationPublisher` của JMX. Spring application events chạy trong cơ chế event nội bộ ApplicationContext; JMX notifications đi qua MBean broadcaster và tới JMX listeners. Có thể chuyển đổi từ event nội bộ sang JMX notification bằng management adapter, nhưng hai hệ thống không tự liên kết chỉ vì cùng mang tên publisher.

## 17. Notification là tín hiệu, không phải nguồn dữ liệu duy nhất

Một listener có thể:

- Kết nối sau khi sự kiện đã phát.
- Bị ngắt giữa chừng do redeploy, network hoặc connector restart.
- Bỏ lỡ event do client xử lý chậm hoặc sự cố.
- Nhận lại một sự kiện trong tình huống hệ thống chuyển tiếp có retry riêng.

Vì vậy notification nên hỗ trợ nhận biết tình huống cần kiểm tra lại state, chẳng hạn nhận `queue.threshold` rồi đọc `QueueDepth`, thay vì dùng notification như source of truth duy nhất.

```text
Notification received
        |
        v
Client reads current attribute
        |
        v
Decide whether action is still needed
```

Mẫu này cũng giúp tránh phản ứng sai nếu trạng thái đã tự phục hồi trước khi listener xử lý.

## 18. Bảo mật của notification

JMX notification không mặc định là kênh bí mật. Trong một ứng dụng bật remote JMX:

- Bảo vệ connector bằng network policy, authentication, TLS và authorization.
- Giới hạn MBean và notification types mà client được truy cập theo cơ chế bảo mật của server.
- Không gửi dữ liệu bí mật trong type, message, source hoặc userData.
- Không đặt operation nguy hiểm gần notification listener mà không có phân quyền.
- Cẩn thận khi thông báo lỗi vì exception message/stack trace có thể chứa thông tin nhạy cảm.

Metadata `@ManagedNotification` chỉ mô tả contract; nó không xác thực client, mã hóa payload hoặc tạo ACL.

## 19. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `setNotificationPublisher` không được gọi | Bean chưa được export hoặc đường export không hỗ trợ publisher | Kiểm tra MBeanExporter, bean instance và JMX config |
| Có metadata nhưng không nhận notification | Chưa gọi sendNotification hoặc listener chưa đăng ký | Kiểm tra event path và listener lifecycle |
| Listener đăng ký nhưng không thấy sự kiện | Sai ObjectName/MBeanServer, filter loại event | So đúng server, name, notification type |
| Listener local chạy, remote không nhận | Connector/authorization/network lỗi | Kiểm tra JMX service URL, quyền và TLS |
| Notification lặp nhiều lần | Code phát từ getter/polling hoặc không có debounce | Phát ở state transition và giới hạn tốc độ |
| userData lỗi deserialize phía client | Payload dùng class nội bộ hoặc không serializable | Dùng dữ liệu đơn giản/Open Types |
| Sequence number không liên tục | Bỏ lỡ event hoặc source thay đổi | Dùng event làm tín hiệu và đọc state hiện tại |
| MBean đóng rồi vẫn cố phát | Publisher reference sống lâu hơn MBean lifecycle | Quản lý shutdown/callback và tránh static state |
| JConsole không liệt kê notification type | Metadata annotation hoặc assembler chưa đúng | Kiểm tra MBeanInfo.getNotifications() |

## 20. Thiết kế contract notification tốt

Một notification contract nên ghi rõ:

1. **Type** có namespace ổn định: `com.example.jobs.queue.threshold`.
2. **Nguồn** là MBean nào: ObjectName xác định, không mập mờ giữa application instances.
3. **Điều kiện phát**: chuyển ngưỡng, hoàn thành tác vụ hay chuyển trạng thái.
4. **Ngữ nghĩa lặp**: có thể phát nhiều lần không, có cooldown không?
5. **Sequence**: tăng theo broadcaster và reset khi lifecycle mới hay không.
6. **Timestamp**: epoch millis, thời điểm event phát ra.
7. **Payload**: schema nhỏ, an toàn, không chứa secrets.
8. **Độ tin cậy**: best-effort, client phải đọc attribute để xác nhận trạng thái.
9. **Security**: những client nào được phép subscribe và nhận nội dung.
10. **Tương thích**: không đổi type/field bất ngờ nếu có dashboard/automation đang tiêu thụ.

## 21. Tổng kết

```text
Spring bean được export
      |
      +-- @ManagedResource
      +-- @ManagedNotifications (metadata)
      +-- NotificationPublisherAware
                 |
          publisher được inject
                 |
          application event
                 |
          Notification object
                 |
          sendNotification
                 |
              MBeanServer
                 |
        JMX NotificationListeners
```

**Ghi nhớ:** để phát notification từ MBean được export trong Spring Framework, bean thường triển khai `NotificationPublisherAware`, nhận `NotificationPublisher` do exporter cấp và gọi `sendNotification` khi sự kiện thật xảy ra. `@ManagedNotification`/`@ManagedNotifications` mô tả loại sự kiện nhưng không tự gửi event. Hãy quản lý sequence number, payload, listener lifecycle, ObjectName và bảo mật; sử dụng notification như tín hiệu bổ sung cho attribute hiện tại, không như một hàng đợi bền vững.
