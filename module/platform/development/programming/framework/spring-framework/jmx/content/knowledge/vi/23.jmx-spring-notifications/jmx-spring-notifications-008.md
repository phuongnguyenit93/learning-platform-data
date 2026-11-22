# Spring Framework JMX: AttributeChangeNotification và thay đổi attribute

## 1. Mục tiêu

JMX (Java Management Extensions) cung cấp các thuộc tính (attributes) để công cụ quản trị quan sát và điều chỉnh trạng thái của MBean. Khi một attribute thay đổi, MBean có thể phát sự kiện javax.management.AttributeChangeNotification đến các listener đã đăng ký. Bài học trình bày cách tạo notification, tích hợp với Spring MBeanExporter và NotificationPublisherAware, kiểm tra giá trị cũ/mới, đăng ký listener, xử lý tính đồng thời, bảo mật và kiểm thử.

Điểm quan trọng: chỉ khai báo Spring @ManagedAttribute không tự tạo AttributeChangeNotification. Bean phải chủ động phát sự kiện bằng một broadcaster hoặc publisher tương ứng. Notification không mặc định có khả năng lưu trữ bền vững hay replay sau khi client kết nối lại.

## 2. Kiến trúc

```text
Client / JConsole
   |
   | setAttribute(name, new Attribute("MaxWorkers", 16))
   v
MBeanServer
   |
   v
Spring MBeanExporter -> managed bean
                          |
                          | validate + update state
                          v
                   AttributeChangeNotification
                          |
                          v
             NotificationBroadcaster / Publisher
                          |
                 NotificationListener
                          |
                audit / monitoring
```

Một đường thay đổi giá trị nên gồm: kiểm tra giá trị mới, lấy giá trị cũ, áp dụng thay đổi thành công, tạo event và phát sau khi state đã được cập nhật. Nếu việc cấu hình executor hoặc connection pool thất bại, không phát event khẳng định rằng thay đổi đã hoàn tất.

## 3. AttributeChangeNotification là gì?

AttributeChangeNotification nằm trong package javax.management và kế thừa Notification. Constructor:

```java
new AttributeChangeNotification(
    source,
    sequenceNumber,
    timeStamp,
    message,
    attributeName,
    attributeType,
    oldValue,
    newValue
);
```

| Trường | Ý nghĩa |
|---|---|
| source | Đối tượng hoặc identity MBean nguồn |
| sequenceNumber | Số thứ tự event do nguồn phát quản lý |
| timeStamp | Epoch milliseconds |
| message | Mô tả ngắn |
| attributeName | Tên attribute JMX, ví dụ MaxWorkers |
| attributeType | Tên kiểu Java, ví dụ int |
| oldValue | Giá trị cũ |
| newValue | Giá trị mới |

Notification type chuẩn là AttributeChangeNotification.ATTRIBUTE_CHANGE, có giá trị "jmx.attribute.change". Các getter chuyên biệt gồm getAttributeName(), getAttributeType(), getOldValue() và getNewValue().

```java
if (notification instanceof AttributeChangeNotification change) {
    System.out.printf("%s: %s -> %s%n",
        change.getAttributeName(),
        change.getOldValue(),
        change.getNewValue()
    );
}
```

Một event mô tả snapshot tại lúc phát, không phải cam kết giá trị hiện tại ở mọi thời điểm về sau. Nếu client đọc lại bằng getAttribute(), có thể thấy giá trị mới hơn do một thay đổi khác.

## 4. Standard MBean với NotificationBroadcasterSupport

Định nghĩa management interface:

```java
package com.example.jmx;

public interface WorkerPoolControlMBean {
    int getMaxWorkers();
    void setMaxWorkers(int value);
}
```

Implementation:

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanNotificationInfo;
import javax.management.NotificationBroadcasterSupport;

public final class WorkerPoolControl
        extends NotificationBroadcasterSupport
        implements WorkerPoolControlMBean {

    private final AtomicLong sequence = new AtomicLong();
    private int maxWorkers = 8;

    @Override
    public synchronized int getMaxWorkers() {
        return maxWorkers;
    }

    @Override
    public void setMaxWorkers(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException("Expected 1..64");
        }

        final int oldValue;
        final long number;
        synchronized (this) {
            oldValue = maxWorkers;
            if (oldValue == value) {
                return;
            }
            maxWorkers = value;
            number = sequence.incrementAndGet();
        }

        AttributeChangeNotification event =
            new AttributeChangeNotification(
                this,
                number,
                System.currentTimeMillis(),
                "MaxWorkers changed",
                "MaxWorkers",
                "int",
                oldValue,
                value
            );
        sendNotification(event);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] {
                    AttributeChangeNotification.ATTRIBUTE_CHANGE
                },
                AttributeChangeNotification.class.getName(),
                "Worker pool configuration changed"
            )
        };
    }
}
```

Các chi tiết:
- Validation xảy ra trước khi đổi state.
- Đồng bộ hóa bảo vệ snapshot old/new và update trong ví dụ.
- Setter được gọi với giá trị không đổi không tạo event.
- Event được gửi ngoài synchronized block để hạn chế nguy cơ callback giữ lock lâu.
- getNotificationInfo() công bố metadata cho client biết MBean có thể phát loại notification nào.

Nếu có nhiều thread ghi liên tiếp, sequence được cấp trong lock nhưng sendNotification() xảy ra ngoài lock. Listener có thể nhận event không trùng thứ tự cấp sequence. Nếu thứ tự chặt chẽ là bắt buộc, thiết kế một hàng đợi phát sự kiện tuần tự thay vì trông chờ mặc định JMX.

## 5. Export Standard MBean qua Spring

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class WorkerJmxConfig {

    @Bean
    WorkerPoolControl workerPoolControl() {
        return new WorkerPoolControl();
    }

    @Bean
    MBeanExporter workerExporter(WorkerPoolControl control) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerPool,name=primary",
            control
        ));
        return exporter;
    }
}
```

MBeanExporter đăng ký bean theo ObjectName vào MBeanServer được chọn. Standard MBean interface quyết định thuộc tính; broadcaster trong implementation quyết định phát notification. Nếu có thêm annotation-driven exporter tự động hoặc một exporter khác, cần tránh đăng ký trùng ObjectName.

## 6. Spring POJO và NotificationPublisherAware

Một Spring bean không bắt buộc kế thừa NotificationBroadcasterSupport. Spring cung cấp org.springframework.jmx.export.notification.NotificationPublisherAware để exporter inject NotificationPublisher vào bean phù hợp.

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.AttributeChangeNotification;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "com.example.app:type=ConfigControl,name=primary",
    description = "Runtime configuration"
)
public class ConfigControl implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private int maxConnections = 16;
    private volatile NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute(description = "Current connection limit")
    public synchronized int getMaxConnections() {
        return maxConnections;
    }

    @ManagedAttribute(description = "Change connection limit")
    public void setMaxConnections(int value) {
        if (value < 1 || value > 200) {
            throw new IllegalArgumentException("Expected 1..200");
        }

        final int before;
        final long number;
        synchronized (this) {
            before = maxConnections;
            if (before == value) return;
            maxConnections = value;
            number = sequence.incrementAndGet();
        }

        NotificationPublisher p = publisher;
        if (p != null) {
            p.sendNotification(new AttributeChangeNotification(
                this,
                number,
                System.currentTimeMillis(),
                "MaxConnections changed",
                "MaxConnections",
                "int",
                before,
                value
            ));
        }
    }
}
```

Spring exporter có thể cấp publisher để bean gửi notification qua ModelMBean. Cần bảo đảm exporter và annotation metadata assembler phù hợp; riêng sự hiện diện của NotificationPublisherAware không đảm bảo bean đã được export. Nếu publisher chưa sẵn sàng lúc setter chạy, ví dụ trên vẫn cập nhật state nhưng không có event. Hệ thống phải chọn rõ chính sách với thay đổi xảy ra trước khi đăng ký JMX.

Ví dụ khai báo annotation-driven exporter:

```java
@Configuration
@EnableMBeanExport
public class JmxConfiguration {
    @Bean
    ConfigControl configControl() {
        return new ConfigControl();
    }
}
```

Để Spring client thấy được notification types dự kiến, phải công bố notification metadata phù hợp với phiên bản Spring, chẳng hạn ManagedNotification/ManagedNotifications, hoặc cấu hình MBeanInfoAssembler tương ứng. Metadata mô tả loại notification nhưng không tự gọi sendNotification().

## 7. Listener dùng JMX API

```java
import javax.management.AttributeChangeNotification;
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName target = new ObjectName(
    "com.example.app:type=ConfigControl,name=primary"
);

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification event) {
        System.out.printf(
            "%s: %s -> %s%n",
            event.getAttributeName(),
            event.getOldValue(),
            event.getNewValue()
        );
    }
};

connection.addNotificationListener(target, listener, null, null);
```

Hủy listener khi không còn cần theo dõi:

```java
connection.removeNotificationListener(target, listener);
```

Với remote connection, khi JVM đích restart hoặc connector bị ngắt, phải xử lý reconnect và có thể đăng ký lại listener. JMX notifications không mặc định có durable queue hay replay. Listener của ứng dụng cần tránh callback chậm hoặc I/O nặng trong đường phát sự kiện.

## 8. Lọc theo attribute

AttributeChangeNotificationFilter có thể chỉ nhận thay đổi của một số attributes:

```java
import javax.management.AttributeChangeNotificationFilter;

AttributeChangeNotificationFilter filter =
    new AttributeChangeNotificationFilter();

filter.enableAttribute("MaxConnections");

connection.addNotificationListener(
    target,
    listener,
    filter,
    null
);
```

Các API hữu ích: enableAttribute(name), disableAttribute(name), disableAllAttributes(). Tên phải là tên JMX attribute chính xác, ví dụ MaxConnections, không phải Java field name maxConnections.

Filter giảm số callback không cần thiết; nó không phải cơ chế xác thực hoặc cấp quyền.

## 9. Thay đổi ngoài JMX setter

Giá trị cấu hình có thể đổi qua REST endpoint, scheduler, configuration reload hoặc autoscaling. Nếu contract của notification là "attribute thực sự thay đổi", cần cân nhắc phát event cho tất cả những đường thay đổi chứ không chỉ JMX setter.

```text
JMX setter --------+
REST admin --------+--> ConfigService.updateLimit(...)
Scheduled reload --+                  |
                                      v
                              update effective state
                                      |
                                      v
                             publish change event
```

Nên dùng một logic cập nhật chung có validation và snapshot old/new để tránh event thiếu nhất quán. Với tài nguyên thật, chỉ phát khi thay đổi được áp dụng. Ví dụ ghi field maxWorkers nhưng executor chưa resize thành công thì event "MaxWorkers changed" có thể sai ngữ nghĩa.

JMX notification là một tín hiệu quản trị, không thay thế transactional event log hoặc message broker khi cần độ bền, retry hay thứ tự nghiêm ngặt.

## 10. Thread safety và thứ tự

Những vấn đề cần xử lý:
- Hai setter chạy đồng thời có thể tạo old/new snapshot sai nếu đọc và ghi không đồng bộ.
- Sequence number có thể có thứ tự khác notification delivery.
- Listener có thể đồng bộ, khiến setter bị chậm nếu callback tốn thời gian.
- Một listener có thể thực hiện lời gọi ngược trở lại MBean, tạo nguy cơ deadlock nếu send trong lock.
- Remote network có thể gây trễ, gián đoạn hoặc mất notification.
- Listener có thể bỏ lỡ sự kiện trong khoảng reconnect.

Một chính sách thực dụng là đồng bộ hóa cập nhật state, cấp sequence sau khi thay đổi và phát ngoài lock; với ordering mạnh, dùng executor/queue tuần tự có giới hạn. Không nên hứa exactly-once delivery hoặc replay chỉ dựa vào JMX.

## 11. Đọc metadata của MBean

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = connection.getMBeanInfo(target);

for (MBeanNotificationInfo item : info.getNotifications()) {
    System.out.println(item.getName());
    for (String type : item.getNotifTypes()) {
        System.out.println(type);
    }
}
```

Nếu không thấy jmx.attribute.change trong metadata, hãy kiểm tra getNotificationInfo() của broadcaster hoặc các annotation/assembler metadata tương ứng của Spring. Metadata chỉ mô tả khả năng phát; cần test thực tế mới xác nhận event được gửi khi attribute thay đổi.

## 12. Kiểm thử end-to-end

Quy trình test:
1. Đăng ký MBean trong một MBeanServer test.
2. Đăng ký NotificationListener ghi sự kiện vào thread-safe list.
3. Ghi một giá trị mới hợp lệ qua setAttribute.
4. Đọc lại attribute để xác nhận state thay đổi.
5. Chờ event với timeout nếu broadcaster bất đồng bộ.
6. Kiểm tra AttributeChangeNotification: attributeName, attributeType, oldValue, newValue và sequenceNumber.
7. Ghi lại cùng giá trị; nếu contract chỉ phát khi đổi thật thì không có thêm event.
8. Ghi giá trị không hợp lệ; state và event count phải không đổi.
9. Unregister listener trong finally.

Ví dụ thao tác:

```java
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerPool,name=primary"
);
int before = (Integer) server.getAttribute(name, "MaxWorkers");
server.setAttribute(name, new Attribute("MaxWorkers", before + 1));
int after = (Integer) server.getAttribute(name, "MaxWorkers");
assertEquals(before + 1, after);
```

Ví dụ giả định before+1 nằm trong miền hợp lệ. Nếu có nhiều actor, test phải cô lập state hoặc quản lý event concurrency để tránh kết quả không ổn định.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Setter thay đổi nhưng không có notification | Chưa gọi sendNotification hoặc publisher chưa được inject | Kiểm tra đường phát và exporter lifecycle |
| Notification metadata trống | Thiếu getNotificationInfo hoặc metadata assembler | Kiểm tra MBeanInfo |
| Event được phát dù old=new | Không kiểm tra thay đổi thực tế | So sánh old/new trước khi gửi |
| Event được gửi trước state update | Gửi trước validation hoặc apply state | Phát sau cập nhật thành công |
| oldValue/newValue sai | Race giữa threads | Đồng bộ hóa snapshot và update |
| Listener làm setter chậm | Callback đồng bộ hoặc I/O nặng | Tránh I/O dưới lock; dùng queue phù hợp |
| Remote client mất event | Connector/JVM restart | Re-register, đối chiếu lại current state |
| ListenerNotFoundException | Remove sai listener/registration | Quản lý identity listener và cleanup |
| InstanceNotFoundException | Sai ObjectName hoặc server | Kiểm tra MBeanServer và registration |

## 14. Bảo mật

AttributeChangeNotification có thể mang oldValue/newValue. Không nên phát password, token, dữ liệu cá nhân hoặc thông tin bí mật. Nếu một thuộc tính nhạy cảm cần đổi, có thể phát event với dữ liệu không nhạy cảm như version hoặc trạng thái thay đổi mà không tiết lộ giá trị.

Remote JMX cần authentication, authorization, bảo vệ transport và network isolation. NotificationListener không phải công cụ cấp quyền; quyền kết nối và quyền thao tác phải được thiết kế tại JMX server/connector.

## 15. Bài thực hành

**Bài 1.** Attribute hiện là 8, setter ghi 12. Hãy tạo event với tên MaxWorkers, kiểu int, oldValue=8, newValue=12 và sequence tăng một.

**Bài 2.** Ghi lại MaxWorkers=12 khi giá trị đang là 12. Nếu contract chỉ phát khi state đổi, phải phát sự kiện không? Trả lời: Không.

**Bài 3.** Setter nhận giá trị ngoài phạm vi. Có được phát event nói rằng cập nhật thành công không? Trả lời: Không; validation failure không phải state transition thành công.

**Bài 4.** Vì sao @ManagedAttribute không tự đồng nghĩa có notifications? Vì annotation mô tả JMX attribute; mã MBean hoặc Spring publisher vẫn cần chủ động phát event.

**Bài 5.** Vì sao listener có thể nhận sự kiện thứ 2 trước sự kiện thứ 1? Vì callback hoặc send xảy ra ngoài lock và có thể bị thread scheduling/remote transport thay đổi thứ tự.

**Bài 6.** Sau khi remote JVM restart, listener cũ có bảo đảm còn hiệu lực không? Không; cần xử lý re-subscription và reconcile state.

## 16. Tổng kết

AttributeChangeNotification mô tả thay đổi JMX attribute với tên thuộc tính, kiểu dữ liệu, giá trị cũ/mới, source, timestamp và sequence. Standard MBean có thể phát bằng NotificationBroadcasterSupport; Spring POJO có thể dùng NotificationPublisherAware và NotificationPublisher sau khi được export đúng cách.

Để notification đáng tin ở mức quan sát vận hành, hãy phát sau khi state áp dụng thành công, kiểm soát old/new snapshot và concurrency, giới hạn dữ liệu nhạy cảm, công bố metadata, và quản lý listener lifecycle. Khi cần event durable hoặc exactly-once, nên dùng hệ thống sự kiện nghiệp vụ thay vì chỉ dựa vào JMX notifications.