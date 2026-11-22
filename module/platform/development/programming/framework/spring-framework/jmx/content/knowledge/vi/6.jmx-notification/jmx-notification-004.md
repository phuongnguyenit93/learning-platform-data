# AttributeChangeNotification cho thay đổi thuộc tính trong Spring Framework JMX

## Mục tiêu

Trong Java Management Extensions (JMX), MBean công bố trạng thái vận hành qua attribute, operation và notification. `AttributeChangeNotification` là loại thông báo chuẩn cho một lần thay đổi attribute. Spring Framework JMX giúp tích hợp MBean vào ứng dụng Spring, còn việc tạo và phát thông báo tuân theo API JMX.

Sau bài học, bạn sẽ biết cách đọc thông tin về thuộc tính thay đổi, phát thông báo từ một MBean, đăng ký listener, và phân biệt notification với việc đọc attribute hiện tại.

## 1. Vì sao cần thông báo thay đổi thuộc tính?

Giả sử một MBean công bố attribute `Enabled` có giá trị `true`. Một client có thể gọi `getAttribute(objectName, "Enabled")` theo chu kỳ để phát hiện thay đổi. Nhưng giữa hai lần đọc, trạng thái có thể đổi nhiều lần mà client không biết.

Với notification, MBean chủ động gửi sự kiện khi trạng thái đổi:

```text
Client                          MBean
  |-- addNotificationListener --> |
  |                               |
  |                      Enabled: true -> false
  | <-- AttributeChangeNotification
  |                               |
  |                      Enabled: false -> true
  | <-- AttributeChangeNotification
```

Đây là mô hình hướng sự kiện: listener nhận thông tin về thay đổi đã xảy ra, gồm tên thuộc tính và giá trị trước/sau. Notification không tự mang lại trạng thái hiện tại ở mọi thời điểm: client đăng ký muộn hoặc mất kết nối có thể bỏ lỡ sự kiện. Do đó trong hệ thống quản trị, notification thường bổ sung cho việc đọc attribute.

## 2. Cấu trúc AttributeChangeNotification

Lớp `javax.management.AttributeChangeNotification` kế thừa `javax.management.Notification`. Nó mang các thông tin:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getType()` | Loại notification; hằng `ATTRIBUTE_CHANGE` có giá trị `jmx.attribute.change` |
| `getSource()` | Nguồn phát notification |
| `getSequenceNumber()` | Số thứ tự do emitter cung cấp |
| `getTimeStamp()` | Thời điểm tạo notification, mili giây tính từ Unix epoch |
| `getMessage()` | Mô tả sự kiện |
| `getAttributeName()` | Tên attribute, chẳng hạn `Enabled` |
| `getAttributeType()` | Tên kiểu, chẳng hạn `boolean` |
| `getOldValue()` | Giá trị trước thay đổi |
| `getNewValue()` | Giá trị sau thay đổi |

Tạo thông báo:

```java
AttributeChangeNotification event =
    new AttributeChangeNotification(
        this,
        1L,
        System.currentTimeMillis(),
        "Enabled changed",
        "Enabled",
        "boolean",
        Boolean.TRUE,
        Boolean.FALSE
    );
```

Constructor nhận source, sequence number, timestamp, message, tên attribute, kiểu attribute, giá trị cũ và giá trị mới. Việc tạo object này **chưa tự phát sự kiện**. MBean phải gửi nó bằng broadcaster hoặc cơ chế publisher tương ứng.

Các giá trị old/new có kiểu `Object`. Với kiểu primitive, Java thường đóng hộp thành `Boolean`, `Integer`, `Long`... Khi xử lý notification từ MBean khác, client nên xem metadata hoặc kiểm tra kiểu thực tế trước khi ép kiểu.

## 3. Xây dựng MBean có thuộc tính thay đổi

### 3.1. Giao diện Standard MBean

```java
package com.example.monitoring;

public interface SwitchMonitorMBean {
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
```

Theo quy ước Standard MBean của JMX, giao diện `SwitchMonitorMBean` định nghĩa các thành phần quản trị của lớp `SwitchMonitor`. Cặp `isEnabled()` và `setEnabled(boolean)` tạo một attribute `Enabled` có thể đọc và ghi.

### 3.2. Triển khai broadcaster và gửi notification

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanNotificationInfo;
import javax.management.NotificationBroadcasterSupport;

public class SwitchMonitor extends NotificationBroadcasterSupport
        implements SwitchMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();
    private boolean enabled = true;

    @Override
    public synchronized boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean next) {
        AttributeChangeNotification event;

        synchronized (this) {
            boolean previous = enabled;
            if (previous == next) {
                return;
            }

            enabled = next;
            event = new AttributeChangeNotification(
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Enabled changed",
                "Enabled",
                "boolean",
                previous,
                next
            );
        }

        sendNotification(event);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            AttributeChangeNotification.ATTRIBUTE_CHANGE
        };

        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                AttributeChangeNotification.class.getName(),
                "Notifications about Enabled changes"
            )
        };
    }
}
```

Phân tích:

1. `NotificationBroadcasterSupport` cung cấp cơ chế đăng ký, gỡ listener và `sendNotification(...)`.
2. Setter lấy giá trị trước thay đổi, kiểm tra sự khác biệt, cập nhật trạng thái và tạo notification.
3. Nếu gọi `setEnabled(true)` khi trạng thái đang là `true`, ví dụ này không phát sự kiện mới.
4. `sequence.incrementAndGet()` cấp số thứ tự tăng dần cho các notification.
5. `getNotificationInfo()` công bố loại notification mà MBean hỗ trợ.
6. `sendNotification(event)` thực sự gửi sự kiện tới listener.

Ví dụ cố ý phát sự kiện sau khi thoát vùng khóa để không giữ khóa trạng thái trong lúc gọi listener. Khi nhiều luồng thay đổi trạng thái đồng thời, thứ tự callback có thể khác thứ tự cập nhật; sequence number giúp nhận biết thứ tự tạo sự kiện, nhưng không tự bảo đảm mọi listener xử lý đúng thứ tự.

### 3.3. Đăng ký MBean

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.monitoring:type=SwitchMonitor,name=Main"
);

SwitchMonitor monitor = new SwitchMonitor();
server.registerMBean(monitor, name);
```

Đây là cách đăng ký trực tiếp vào platform MBeanServer. Trong ứng dụng Spring, thường để `MBeanExporter` quản lý việc đăng ký và hủy đăng ký. Không đăng ký hai lần cùng ObjectName trong một server vì có thể dẫn đến `InstanceAlreadyExistsException`.

## 4. Đăng ký NotificationListener

Client phải đăng ký `NotificationListener` với MBeanServer để nhận thông báo của một ObjectName cụ thể.

```java
import javax.management.Attribute;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanServer;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification change) {
        System.out.printf(
            "%s: %s -> %s (seq=%d)%n",
            change.getAttributeName(),
            change.getOldValue(),
            change.getNewValue(),
            change.getSequenceNumber()
        );
    }
};

server.addNotificationListener(name, listener, null, null);

try {
    server.setAttribute(
        name,
        new Attribute("Enabled", Boolean.FALSE)
    );
} finally {
    server.removeNotificationListener(name, listener);
}
```

Vì `Enabled` ban đầu là `true`, lời gọi ghi sẽ tạo thông báo `true -> false` nếu MBean đã đăng ký đúng và listener còn hoạt động. Các tham số của `addNotificationListener` gồm ObjectName, listener, filter tùy chọn và handback tùy chọn. `handback` là đối tượng ngữ cảnh do bên đăng ký cung cấp; nó không phải old/new value.

Ở ứng dụng dài hạn, listener thường được đăng ký khi component khởi tạo và gỡ khi component kết thúc. Không nên đăng ký một listener mới cho mỗi request rồi bỏ quên.

### Lọc theo attribute

Để chỉ nhận thay đổi của `Enabled`, dùng `AttributeChangeNotificationFilter`:

```java
import javax.management.AttributeChangeNotificationFilter;

AttributeChangeNotificationFilter filter =
    new AttributeChangeNotificationFilter();
filter.enableAttribute("Enabled");

server.addNotificationListener(name, listener, filter, null);
```

Filter này chọn attribute-change notifications có tên attribute phù hợp. Nếu MBean công bố nhiều attribute hoặc phát nhiều loại notification, filter giúp giảm số sự kiện mà listener phải xử lý.

## 5. Khám phá notification metadata

JMX cung cấp `MBeanInfo` để client biết những loại notification được MBean công bố:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanNotificationInfo notificationInfo :
        info.getNotifications()) {
    System.out.println(notificationInfo.getDescription());
    for (String type : notificationInfo.getNotifTypes()) {
        System.out.println("Type: " + type);
    }
}
```

Với `SwitchMonitor` ở phần trên, metadata có loại `jmx.attribute.change`. Tuy nhiên metadata chỉ nói MBean **có khả năng** phát loại thông báo này; nó không cam kết số lượng hoặc thời điểm phát. Notification chỉ xuất hiện khi logic setter thực sự gọi `sendNotification`.

Không nhầm `getNotificationInfo()` với `getNotifications()` trên metadata: MBean triển khai `getNotificationInfo()`; client đọc danh sách thông qua `MBeanInfo.getNotifications()`.

## 6. Tích hợp với Spring Framework JMX

Spring cung cấp các tiện ích để biến bean ứng dụng thành MBean. Một Standard MBean như `SwitchMonitor` có thể được xuất bằng `MBeanExporter`:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfig {

    @Bean
    public SwitchMonitor switchMonitor() {
        return new SwitchMonitor();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter switchExporter(
            SwitchMonitor monitor,
            MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
            "com.example.monitoring:type=SwitchMonitor,name=Main",
            monitor
        ));
        return exporter;
    }
}
```

Sau khi context khởi tạo và exporter đăng ký đối tượng, JMX client dùng đúng ObjectName để truy cập attribute và notification. Giữ một nguồn quản lý đăng ký cho từng MBean, tránh vừa cấu hình exporter vừa gọi `registerMBean` thủ công cho cùng tên.

### 6.1. Spring NotificationPublisher

Bên cạnh `NotificationBroadcasterSupport`, Spring có `org.springframework.jmx.export.notification.NotificationPublisher` để các bean quản trị phát thông báo. Bean triển khai `NotificationPublisherAware` có thể nhận publisher khi được xuất bởi `MBeanExporter` phù hợp.

```java
import javax.management.AttributeChangeNotification;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

public class PublisherMonitor implements NotificationPublisherAware {

    private NotificationPublisher publisher;
    private boolean enabled = true;
    private long sequence;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void setEnabled(boolean next) {
        boolean previous = enabled;
        if (previous == next) {
            return;
        }
        enabled = next;

        if (publisher != null) {
            publisher.sendNotification(
                new AttributeChangeNotification(
                    this,
                    ++sequence,
                    System.currentTimeMillis(),
                    "Enabled changed",
                    "Enabled",
                    "boolean",
                    previous,
                    next
                )
            );
        }
    }
}
```

Ví dụ thứ hai minh họa vai trò publisher, chưa bao gồm interface MBean, cấu hình export và đồng bộ đa luồng để chạy độc lập. Nó cho thấy Spring có thể cung cấp cơ chế phát thông báo mà bean không cần kế thừa broadcaster JMX. Cần bảo đảm bean thực sự được exporter quản lý và đã nhận publisher trước khi mong đợi thông báo được gửi.

### 6.2. ManagedNotification metadata

Spring hỗ trợ metadata JMX như `@ManagedResource`, `@ManagedAttribute` và `@ManagedNotification` cùng các assembler tương ứng. Metadata giúp MBean công bố loại notification mà client có thể khám phá.

Điểm cần hiểu: khai báo metadata **không tự phát** `AttributeChangeNotification`. Phải có đoạn mã phát sự kiện, chẳng hạn `sendNotification` hoặc `NotificationPublisher.sendNotification`. Các annotation cần được xử lý bởi exporter/assembler phù hợp, thay vì mặc định mọi bean có annotation đều tự đăng ký.

## 7. Attribute, operation và notification khác nhau thế nào?

| Thành phần | Cách client sử dụng | Câu hỏi trả lời |
| --- | --- | --- |
| Attribute | `getAttribute(name, "Enabled")` | Trạng thái hiện tại là gì? |
| Operation | `invoke(name, "reset", ...)` | Có thể yêu cầu thực hiện hành động nào? |
| Notification | `addNotificationListener(...)` | Sự kiện nào vừa xảy ra? |

Ghi attribute bằng `setAttribute` không bảo đảm tự động có notification. MBean phải chủ động tạo và phát. Ngược lại, nhận notification không bảo đảm trạng thái hiện tại vẫn là `newValue` của sự kiện, vì thuộc tính có thể tiếp tục thay đổi sau đó.

Ví dụ:

```text
t1: Enabled true -> false; gửi event A
t2: Enabled false -> true; gửi event B
t3: listener xử lý event A
```

Khi xử lý event A ở t3, trạng thái hiện tại có thể đã là `true`. Client nào cần sự thật hiện tại nên đọc attribute, hoặc dùng sequence/version để đối soát thứ tự.

## 8. Tính nhất quán của old/new value

Thông báo chỉ đáng tin khi emitter thu thập giá trị cũ/mới theo đúng thời điểm cập nhật.

Ví dụ có validation:

```java
public synchronized void setThreshold(int next) {
    if (next < 0) {
        throw new IllegalArgumentException(
            "Threshold must be non-negative"
        );
    }

    int previous = threshold;
    if (previous == next) {
        return;
    }

    threshold = next;
    // Tạo thông báo previous -> next sau khi cập nhật thành công.
}
```

Nếu setter từ chối giá trị mới, không nên phát notification khẳng định giá trị đã thay đổi. Đối với attribute kiểu mutable, nên cân nhắc snapshot bất biến khi đưa vào old/new value để sau đó object không bị thay đổi ngoài ý muốn.

Một số nguyên tắc:

- Lấy `oldValue` trước khi cập nhật.
- Chỉ tạo sự kiện khi điều kiện thay đổi được xác nhận.
- Cấp sequence number nhất quán theo mỗi emitter.
- Không đưa secret, token hoặc dữ liệu nhạy cảm vào message và old/new.
- Không coi callback listener là transaction với thao tác cập nhật trạng thái.

## 9. Sequence number, timestamp và concurrency

`getSequenceNumber()` hữu ích để phân biệt các notification của một nguồn; ví dụ `AtomicLong.incrementAndGet()` cho ra các số tăng dần. Nhưng số này do emitter cấp, không phải định danh toàn cục cho mọi JVM. Khi MBean hoặc ứng dụng restart, số thứ tự có thể bắt đầu lại.

`getTimeStamp()` trả về thời điểm emitter ghi nhận. Nó không nhất thiết bằng thời điểm listener nhận sự kiện, đặc biệt khi truyền qua network hoặc xử lý bất đồng bộ. Đồng hồ các JVM khác nhau còn có thể lệch.

Khi nhiều thread đổi cùng attribute, cần xác định:

1. Phép đọc giá trị cũ và ghi giá trị mới có được đồng bộ không?
2. Sequence number được cấp ở thời điểm nào?
3. Có thể gửi callback ngoài thứ tự cập nhật không?
4. Client cần giữ trạng thái cuối hay lưu toàn bộ lịch sử sự kiện?
5. Khi callback xử lý chậm, hệ thống phản ứng ra sao?

`NotificationBroadcasterSupport` có thể sử dụng executor tùy cấu hình. Với delivery đồng bộ, callback chậm có thể làm chậm luồng phát. Với callback bất đồng bộ, cần xử lý queue, lỗi và thứ tự phù hợp. Không nên cho listener thực hiện I/O kéo dài ngay trong một setter quan trọng nếu chưa hiểu tác động tới ứng dụng.

## 10. Lifecycle và truy cập từ xa

Listener được đăng ký với một MBean cụ thể bằng `ObjectName`. Nếu MBean bị unregister, đăng ký cũ không nên được xem là vĩnh viễn. Khi Spring context đóng, component quản lý listener nên gỡ đăng ký trong lifecycle tương ứng.

Với JMX Remote, client sử dụng `MBeanServerConnection`:

```java
connection.addNotificationListener(
    name,
    listener,
    filter,
    null
);
```

Cơ chế giao nhận qua connector có thể gặp lỗi mạng hoặc mất kết nối. Không mặc định rằng notification trong khoảng mất mạng sẽ được lưu lại và gửi bù. Sau khi reconnect, client nên đăng ký lại theo kết nối mới và đọc trạng thái hiện tại để đối soát.

Các lỗi cần phân biệt gồm:

- `InstanceNotFoundException`: MBean không được đăng ký dưới ObjectName đang sử dụng.
- `ListenerNotFoundException`: gỡ một listener không tồn tại theo registration tương ứng.
- `IOException` trong client remote: lỗi transport/kết nối.
- Lỗi authorization/security: client không có quyền thực hiện thao tác.
- Lỗi trong callback: logic xử lý của listener bị lỗi; cần ghi nhận và xử lý riêng.

Remote JMX là kênh quản trị nhạy cảm. Cần giới hạn network, dùng xác thực và mã hóa phù hợp; không phát dữ liệu bí mật qua notification.

## 11. Thực hành có hướng dẫn

Thực hành sử dụng `SwitchMonitor` đã đăng ký như phần 3.

**Bước 1:** Kiểm tra MBean đã tồn tại:

```java
if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Missing MBean: " + name
    );
}
```

**Bước 2:** Đọc `MBeanInfo`, xác nhận notification type có `jmx.attribute.change`.

**Bước 3:** Đăng ký listener và filter:

```java
AttributeChangeNotificationFilter filter =
    new AttributeChangeNotificationFilter();
filter.enableAttribute("Enabled");

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification change) {
        System.out.printf(
            "Attribute=%s old=%s new=%s seq=%d%n",
            change.getAttributeName(),
            change.getOldValue(),
            change.getNewValue(),
            change.getSequenceNumber()
        );
    }
};

server.addNotificationListener(name, listener, filter, null);
```

**Bước 4:** Thay đổi giá trị:

```java
server.setAttribute(
    name,
    new Attribute("Enabled", false)
);
server.setAttribute(
    name,
    new Attribute("Enabled", false)
);
server.setAttribute(
    name,
    new Attribute("Enabled", true)
);
```

Nếu trạng thái ban đầu là `true`, ví dụ này tạo hai notification vì lần ghi thứ hai không làm thay đổi giá trị.

Kết quả minh họa:

```text
Attribute=Enabled old=true new=false seq=1
Attribute=Enabled old=false new=true seq=2
```

**Bước 5:** Gỡ listener:

```java
server.removeNotificationListener(name, listener);
```

**Bước 6:** Đọc lại attribute:

```java
boolean enabled =
    (Boolean) server.getAttribute(name, "Enabled");
System.out.println("Current state: " + enabled);
```

Kết quả đọc cuối cùng là `true` nếu không có thread hoặc client khác cập nhật trong lúc thực hành. Phép đọc này xác nhận trạng thái hiện tại, còn notification kể lại các thay đổi mà listener đã nhận.

## 12. Những nhầm lẫn thường gặp

**“Gọi setAttribute tự động tạo AttributeChangeNotification.”** Không. MBean hoặc publisher phải chủ động phát.

**“Chỉ cần @ManagedNotification là có sự kiện.”** Không. Annotation mô tả metadata; emitter mới là nơi gửi notification.

**“Listener đăng ký muộn vẫn nhận được tất cả sự kiện cũ.”** Không có bảo đảm lưu và phát lại lịch sử.

**“Old/new value luôn chính xác mà không cần quan tâm code setter.”** Chúng do emitter cung cấp; logic cập nhật phải tạo dữ liệu nhất quán.

**“Một notification cho biết chắc chắn trạng thái hiện tại.”** Trạng thái có thể đổi tiếp; muốn biết hiện tại phải đọc attribute.

**“Sequence number là thứ tự tuyệt đối giữa nhiều ứng dụng.”** Không. Nó có ý nghĩa trong phạm vi nguồn phát và hợp đồng cấp số của nguồn đó.

**“Metadata liệt kê notification nghĩa là cứ ghi attribute sẽ có sự kiện.”** Không. Metadata mô tả loại sự kiện mà MBean có thể phát, không phải lời hứa về mọi lần ghi.

## 13. Câu hỏi tự kiểm tra

1. `AttributeChangeNotification` dùng để diễn tả điều gì? **Một lần thay đổi thuộc tính quản trị của MBean.**
2. Type chuẩn của nó là gì? **`jmx.attribute.change`.**
3. Hai phương thức đọc giá trị trước/sau là gì? **`getOldValue()` và `getNewValue()`.**
4. Làm sao MBean thực sự gửi sự kiện? **Qua broadcaster `sendNotification(...)` hoặc publisher thích hợp.**
5. Client đăng ký nhận sự kiện bằng API nào? **`addNotificationListener(...)` trên MBeanServer/MBeanServerConnection.**
6. Làm sao chỉ nhận sự kiện cho `Enabled`? **Dùng `AttributeChangeNotificationFilter.enableAttribute("Enabled")`.**
7. Có thể dùng notification thay thế hoàn toàn `getAttribute()` không? **Không, vì notification không bảo đảm trạng thái hiện tại hay lịch sử đầy đủ.**
8. Vì sao phải gỡ listener? **Để tránh callback và tài nguyên tồn tại lâu hơn vòng đời cần thiết.**
9. Khi remote client reconnect, nên làm gì? **Thiết lập lại listener và đọc lại trạng thái hiện tại.**

## 14. Ghi nhớ

- `AttributeChangeNotification` là chuẩn JMX cho sự kiện **thay đổi attribute**.
- Sự kiện mang **tên, kiểu, old/new value, timestamp và sequence number**.
- **Metadata không tự phát thông báo**; cần broadcaster hoặc publisher.
- **NotificationListener** nhận sự kiện; **AttributeChangeNotificationFilter** lọc theo attribute.
- **Spring MBeanExporter** kết nối vòng đời bean Spring với MBeanServer; Spring cũng cung cấp `NotificationPublisher`.
- **Đọc attribute** cho trạng thái hiện tại; **notification** cho biết một thay đổi được phát hiện và truyền tới listener.
- Cần chủ động xử lý đồng thời, thứ tự, bảo mật, reconnect và lifecycle listener.

Khi xây dựng hệ thống quan sát Spring Framework JMX, hãy xem `AttributeChangeNotification` là kênh truyền sự kiện hữu ích cho phản ứng nhanh; việc xác định trạng thái vận hành chính xác vẫn cần dựa trên hợp đồng attribute và cơ chế đối soát phù hợp.