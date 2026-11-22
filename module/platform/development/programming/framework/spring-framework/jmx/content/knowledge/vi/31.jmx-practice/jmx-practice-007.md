# Thực hành phát và nhận AttributeChangeNotification trong Spring Framework JMX

## 1. Mục tiêu bài thực hành

Trong Java Management Extensions (JMX), một MBean không chỉ hỗ trợ đọc/ghi attribute hoặc gọi operation; nó còn có thể **phát notification** khi trạng thái thay đổi. `AttributeChangeNotification` là notification chuẩn dành cho một sự kiện thay đổi giá trị attribute. Spring Framework có thể export bean thành JMX MBean, đồng thời hỗ trợ tích hợp cơ chế gửi và nhận notification bằng các thành phần của Spring JMX.

Bài thực hành xây dựng một bean quản trị có thuộc tính `Enabled`, phát `AttributeChangeNotification` khi giá trị đổi, rồi đăng ký `NotificationListener` để nhận và xác minh nội dung sự kiện.

Sau bài này, bạn có thể:

- Giải thích notification khác với việc polling `getAttribute` như thế nào.
- Biết các trường quan trọng của `AttributeChangeNotification`: source, sequenceNumber, timestamp, message, attributeName, attributeType, oldValue, newValue.
- Cấu hình MBean có khả năng phát notification qua `NotificationBroadcasterSupport` hoặc Spring `NotificationPublisher`.
- Đăng ký listener với `MBeanServer.addNotificationListener`.
- Thực hiện thay đổi trạng thái qua JMX và quan sát notification.
- Viết test xác nhận nội dung notification mà không phụ thuộc thời gian chờ ngẫu nhiên.
- Xử lý listener lifecycle, filter, thứ tự sự kiện và rủi ro dữ liệu nhạy cảm.

## 2. Notification khác attribute ở điểm nào?

Attribute và notification cùng xuất hiện trong MBean, nhưng giải quyết hai mục tiêu:

| Cơ chế | Mục đích | Cách sử dụng |
| --- | --- | --- |
| Attribute | Xem trạng thái tại thời điểm đọc | `getAttribute(ObjectName, "Enabled")` |
| Writable attribute | Yêu cầu thay đổi trạng thái | `setAttribute(ObjectName, Attribute)` |
| Notification | Thông báo một sự kiện phát sinh | Listener nhận callback |
| `AttributeChangeNotification` | Diễn tả sự kiện đổi giá trị một attribute | Listener đọc old/new values |

Ví dụ:

```text
Trạng thái ban đầu: Enabled=true
Client gọi setAttribute(Enabled=false)
            |
            v
Bean đổi trạng thái true -> false
            |
            v
Phát AttributeChangeNotification
            |
            v
NotificationListener nhận:
  attributeName=Enabled
  oldValue=true
  newValue=false
```

Notification không phải database transaction, durable message hay event log tự phục hồi. Một client đăng ký muộn có thể bỏ lỡ notification trước đó; client cũng có thể mất sự kiện khi kết nối bị gián đoạn. Vì vậy, để đồng bộ state, listener thường nên **đọc snapshot ban đầu** và tiếp tục lắng nghe thay đổi, kết hợp cơ chế resync nếu cần.

## 3. Cấu trúc AttributeChangeNotification

Lớp chuẩn:

```java
javax.management.AttributeChangeNotification
```

Một đối tượng được tạo với các thông tin:

```java
new AttributeChangeNotification(
    source,
    sequenceNumber,
    timestamp,
    message,
    attributeName,
    attributeType,
    oldValue,
    newValue
);
```

Ý nghĩa:

| Tham số | Ý nghĩa |
| --- | --- |
| `source` | Nguồn phát sự kiện, thường là MBean hoặc ObjectName |
| `sequenceNumber` | Số thứ tự do nguồn phát quản lý |
| `timestamp` | Thời điểm phát tính bằng millisecond từ epoch |
| `message` | Mô tả sự kiện |
| `attributeName` | Tên attribute được công bố trong JMX |
| `attributeType` | Tên kiểu Java của attribute |
| `oldValue` | Giá trị trước khi thay đổi |
| `newValue` | Giá trị sau khi thay đổi |

Hằng type chuẩn:

```java
AttributeChangeNotification.ATTRIBUTE_CHANGE
```

Listener có thể kiểm tra `notification.getType()` bằng hằng này. `AttributeChangeNotification` kế thừa `Notification` nên cũng có các trường chung như `getSequenceNumber()`, `getTimeStamp()`, `getMessage()` và `getSource()`.

### 3.1. Ví dụ tạo notification

```java
import javax.management.AttributeChangeNotification;

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

Chuỗi `"Enabled"` nên khớp **tên attribute JMX**, không nhất thiết là tên field Java. Với getter `isEnabled()`, tên quản trị thường là `Enabled`. `attributeType` phải phản ánh kiểu mà metadata JMX công bố.

## 4. Cách tiếp cận A: Standard MBean phát notification

Để hiểu JMX nền tảng trước, bắt đầu với một Standard MBean, sử dụng `NotificationBroadcasterSupport`. Sau đó chuyển sang Spring exporter.

Định nghĩa management interface:

```java
package com.example.jmx;

public interface FeatureSwitchMBean {
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
```

Lớp implementation:

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.AttributeChangeNotification;
import javax.management.MBeanNotificationInfo;
import javax.management.NotificationBroadcasterSupport;

public class FeatureSwitch
        extends NotificationBroadcasterSupport
        implements FeatureSwitchMBean {

    private final AtomicLong sequence = new AtomicLong();
    private boolean enabled = true;

    @Override
    public synchronized boolean isEnabled() {
        return enabled;
    }

    @Override
    public synchronized void setEnabled(boolean next) {
        boolean previous = enabled;

        if (previous == next) {
            return;
        }

        enabled = next;

        AttributeChangeNotification event =
            new AttributeChangeNotification(
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Feature switch changed",
                "Enabled",
                "boolean",
                previous,
                next
            );

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
                "Emitted when Enabled changes"
            )
        };
    }
}
```

Code này cung cấp ba thành phần:

1. `FeatureSwitchMBean`: hợp đồng attribute getter/setter cho Standard MBean.
2. `NotificationBroadcasterSupport`: phát sự kiện tới những listener đăng ký.
3. `getNotificationInfo()`: mô tả notification type trong metadata để client khám phá.

Đặt `setEnabled` là `synchronized` giúp cặp read/update của ví dụ nhất quán. Tuy nhiên việc gọi listener đồng bộ bên trong lock có thể gây vấn đề nếu listener nặng hoặc reentrant. Trong production, nên đánh giá kiểu executor của broadcaster và tránh để callback bên ngoài kéo dài critical section.

## 5. Đăng ký và nhận notification với MBeanServer

Có thể đăng ký trực tiếp Standard MBean vào một server riêng cho bài thực hành:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server =
    MBeanServerFactory.newMBeanServer("com.example.lab");

ObjectName name = new ObjectName(
    "com.example.lab:type=FeatureSwitch,name=Main"
);

FeatureSwitch bean = new FeatureSwitch();
server.registerMBean(bean, name);
```

Đăng ký listener:

```java
import javax.management.AttributeChangeNotification;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification change) {
        System.out.println("Changed: " + change.getAttributeName());
        System.out.println("Old: " + change.getOldValue());
        System.out.println("New: " + change.getNewValue());
        System.out.println("Sequence: " + change.getSequenceNumber());
    }
};

server.addNotificationListener(name, listener, null, null);
```

Thay đổi attribute thông qua JMX:

```java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE)
);
```

Khi setter đổi `true` thành `false`, broadcaster phát event và listener nhận callback. Gọi `setAttribute` lần nữa với `false` không phát notification trong implementation ở phần 4, vì không có thay đổi giá trị.

Dọn listener và MBean:

```java
try {
    server.removeNotificationListener(name, listener);
} finally {
    if (server.isRegistered(name)) {
        server.unregisterMBean(name);
    }
}
```

Chỉ unregister MBean do bài thực hành sở hữu. Không dùng cleanup kiểu “unregister mọi tên trong domain” khi chạy trên platform server dùng chung.

## 6. Kiểm tra metadata notification

Bằng `MBeanInfo`, client có thể khám phá notification mà MBean tuyên bố hỗ trợ:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanNotificationInfo notificationInfo
        : info.getNotifications()) {

    System.out.println(
        "Notification class: " + notificationInfo.getName()
    );

    for (String type : notificationInfo.getNotifTypes()) {
        System.out.println("Type: " + type);
    }
}
```

Kết quả dự kiến có type:

```text
jmx.attribute.change
```

Đây là giá trị của `AttributeChangeNotification.ATTRIBUTE_CHANGE`.

Để phát hiện contract break, test có thể xác nhận type này tồn tại trong `MBeanInfo.getNotifications()`. Nhưng việc metadata nêu một type không tự chứng minh event được phát đúng lúc; cần thêm test thực tế với listener.

## 7. Cách tiếp cận B: Spring Framework JMX với NotificationPublisher

Spring Framework JMX có cơ chế tích hợp `NotificationPublisher` cho bean do `MBeanExporter` quản lý. Một bean có thể implement `NotificationPublisherAware` và gửi `Notification` thông qua publisher được exporter cung cấp.

Đây là lựa chọn hữu ích khi bạn muốn bean dùng annotation của Spring thay vì tự kế thừa `NotificationBroadcasterSupport`.

### 7.1. Bean hỗ trợ NotificationPublisher

```java
package com.example.springjmx;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.AttributeChangeNotification;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "com.example.springjmx:type=FeatureSwitch,name=Main",
    description = "Managed feature switch"
)
@ManagedNotifications({
    @ManagedNotification(
        name = AttributeChangeNotification.ATTRIBUTE_CHANGE,
        description = "Enabled state changed",
        notificationTypes = {
            AttributeChangeNotification.ATTRIBUTE_CHANGE
        }
    )
})
public class SpringFeatureSwitch
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile boolean enabled = true;
    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute(description = "Current enabled state")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Change enabled state")
    public synchronized void setEnabled(boolean next) {
        boolean previous = enabled;

        if (previous == next) {
            return;
        }

        enabled = next;

        NotificationPublisher target = publisher;
        if (target != null) {
            AttributeChangeNotification event =
                new AttributeChangeNotification(
                    this,
                    sequence.incrementAndGet(),
                    System.currentTimeMillis(),
                    "Enabled changed",
                    "Enabled",
                    "boolean",
                    Boolean.valueOf(previous),
                    Boolean.valueOf(next)
                );

            target.sendNotification(event);
        }
    }
}
```

**Lưu ý về metadata notification:** Trong Spring, `@ManagedNotification` cung cấp metadata notification, nhưng các thuộc tính annotation có thể khác nhau theo phiên bản; khi triển khai cần đối chiếu API chính xác của version đang dùng. Một cấu hình thường chỉ yêu cầu `name` và `notificationTypes` thích hợp. Để tối giản và tránh phụ thuộc vào metadata annotation, có thể phát notification qua `NotificationPublisherAware`, sau đó xác nhận trực tiếp bằng listener và `MBeanInfo`.

Chú ý `publisher` chỉ được inject khi bean được export qua `MBeanExporter` có hỗ trợ `NotificationPublisherAware`. Nếu bạn tự tạo instance rồi gọi setter ngoài Spring JMX, `publisher` có thể `null`. Một triển khai production nên xác định rõ hành vi trước khi exporter hoàn tất khởi tạo.

### 7.2. Điểm khác so với NotificationBroadcasterSupport

| Tiêu chí | Standard MBean broadcaster | Spring NotificationPublisher |
| --- | --- | --- |
| Cơ chế phát | `sendNotification()` của `NotificationBroadcasterSupport` | `NotificationPublisher.sendNotification()` |
| Tích hợp | API JMX thuần | Qua Spring `MBeanExporter` |
| Metadata | `getNotificationInfo()` | Metadata JMX được cấu hình qua Spring |
| Khả năng test | Đăng ký Standard MBean trực tiếp | Test exporter, publisher và listener |
| Lifecycle | Code sở hữu đăng ký/listener | Spring exporter có thể quản lý MBean registration |
| Phụ thuộc framework | JDK JMX | Spring Framework JMX |

Hai cách giải quyết cùng nhu cầu: MBean phát notification và client được đăng ký nhận. Chọn cơ chế nào phụ thuộc dự án; không nên vô tình cấu hình cả hai nguồn phát cho một thay đổi nếu điều đó tạo notification trùng.

## 8. Cấu hình Spring export bean

Một cấu hình Java rõ ràng sử dụng `MetadataMBeanInfoAssembler` và `MBeanExporter`:

```java
package com.example.springjmx;

import java.util.Map;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration
public class SpringJmxLabConfig {

    @Bean
    public SpringFeatureSwitch featureSwitch() {
        return new SpringFeatureSwitch();
    }

    @Bean
    public MBeanServer labMBeanServer() {
        return MBeanServerFactory.newMBeanServer(
            "com.example.springjmx"
        );
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler metadataAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MBeanExporter featureExporter(
            SpringFeatureSwitch featureSwitch,
            MBeanServer labMBeanServer,
            MetadataMBeanInfoAssembler metadataAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(labMBeanServer);
        exporter.setAssembler(metadataAssembler);
        exporter.setBeans(Map.of(
            "com.example.springjmx:type=FeatureSwitch,name=Main",
            featureSwitch
        ));
        return exporter;
    }
}
```

Nhờ server riêng, bài thực hành không tranh chấp namespace với platform server hoặc các MBean của hệ thống. Với client ở JVM khác, server riêng không tự có JMX Remote connector; cần connector gắn đúng server và bảo mật nếu thực sự cần truy cập từ xa.

Nếu sử dụng annotation-driven export như `@EnableMBeanExport`, không nên đồng thời khai báo exporter thủ công cho cùng ObjectName nếu không có thiết kế rõ ràng.

## 9. Đăng ký listener trong Spring ApplicationContext

Ví dụ test thủ công bằng Spring context:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import javax.management.Attribute;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(
            SpringJmxLabConfig.class)) {

    MBeanServer server = context.getBean(MBeanServer.class);

    ObjectName name = new ObjectName(
        "com.example.springjmx:type=FeatureSwitch,name=Main"
    );

    NotificationListener listener = (notification, handback) -> {
        if (notification instanceof AttributeChangeNotification change) {
            System.out.printf(
                "%s: %s -> %s%n",
                change.getAttributeName(),
                change.getOldValue(),
                change.getNewValue()
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
}
```

MBean phải được exporter đăng ký trước khi `addNotificationListener` thành công. Đóng `AnnotationConfigApplicationContext` giúp exporter chạy lifecycle cleanup. Listener do client đăng ký vẫn nên được gỡ rõ ràng bằng `removeNotificationListener` khi không còn dùng.

## 10. Spring NotificationListenerBean

Ngoài đăng ký trực tiếp qua `MBeanServer.addNotificationListener`, Spring JMX còn có `NotificationListenerBean` để mô tả listener và các MBean mà listener quan tâm. Trong môi trường ứng dụng thực tế, cơ chế này giúp wiring listener qua Spring configuration.

Một ví dụ minh họa cách tạo listener:

```java
import javax.management.AttributeChangeNotification;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification change) {
        System.out.printf(
            "Attribute %s changed to %s%n",
            change.getAttributeName(),
            change.getNewValue()
        );
    }
};
```

Nếu muốn Spring quản lý đăng ký listener, cấu hình `NotificationListenerBean` qua exporter và định danh MBean phù hợp. Việc có một `NotificationListenerBean` trong context không nhất thiết đồng nghĩa nó được gắn vào mọi MBean; cần cấu hình phạm vi đăng ký và MBeanServer đúng.

Đối với bài thực hành đầu tiên, dùng `server.addNotificationListener` giúp quan sát rõ lúc đăng ký, lúc phát và lúc cleanup; sau đó mới chuyển sang wiring do Spring quản lý.

## 11. NotificationFilter để lọc event

Một broadcaster có thể phát nhiều loại notification. Listener có thể dùng `NotificationFilter` để chỉ nhận sự kiện cần thiết.

Ví dụ chỉ nhận attribute change:

```java
import javax.management.AttributeChangeNotification;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;

NotificationFilter filter = notification ->
    AttributeChangeNotification.ATTRIBUTE_CHANGE
        .equals(notification.getType());

NotificationListener listener = (notification, handback) -> {
    AttributeChangeNotification change =
        (AttributeChangeNotification) notification;

    System.out.printf(
        "%s: %s -> %s%n",
        change.getAttributeName(),
        change.getOldValue(),
        change.getNewValue()
    );
};

server.addNotificationListener(name, listener, filter, null);
```

Trong ví dụ này, filter bảo đảm event có type chuẩn phù hợp. Với nguồn phát do ứng dụng tự kiểm soát, điều kiện type thường đủ để xác định cấu trúc mong đợi, nhưng code production vẫn nên kiểm tra `instanceof AttributeChangeNotification` khi nhận từ broadcaster không tin cậy hoặc có nhiều loại event.

Có thể lọc thêm theo attribute name:

```java
NotificationFilter onlyEnabled = notification -> {
    if (!(notification instanceof AttributeChangeNotification change)) {
        return false;
    }
    return "Enabled".equals(change.getAttributeName());
};
```

Khi dùng filter, listener sẽ không nhận những notification bị loại. Điều này không phải là lỗi gửi sự kiện, mà là chủ đích lọc phía client.

## 12. Sequence number và timestamp

Mỗi notification có sequence number và timestamp. Hai trường này hữu ích để ghi log và phát hiện thay đổi theo thứ tự.

Ví dụ:

```java
private final AtomicLong sequence = new AtomicLong();

long nextSequence = sequence.incrementAndGet();

AttributeChangeNotification notification =
    new AttributeChangeNotification(
        this,
        nextSequence,
        System.currentTimeMillis(),
        "Enabled changed",
        "Enabled",
        "boolean",
        previous,
        next
    );
```

Tuy nhiên:

- Sequence chỉ có ý nghĩa theo **nguồn phát**, không phải số thứ tự toàn cục giữa mọi MBean.
- Khi ứng dụng restart hoặc instance mới được tạo, sequence có thể bắt đầu lại.
- Timestamp phụ thuộc clock của JVM phát; nếu có nhiều server, clock skew có thể ảnh hưởng so sánh.
- Listener remote có thể nhận chậm; thời điểm nhận không bằng thời điểm phát.
- Không dùng sequence đơn độc như durable offset nếu cần bảo đảm không mất sự kiện.

Nếu một hệ thống yêu cầu replay, durable delivery hoặc exactly-once semantics, JMX notification không nên thay thế event bus/message broker chuyên dụng.

## 13. Old value và new value

`AttributeChangeNotification` chứa:

```java
change.getOldValue();
change.getNewValue();
```

Đây là `Object`, nên client phải hiểu type của attribute. Với boolean:

```java
Boolean previous = (Boolean) change.getOldValue();
Boolean next = (Boolean) change.getNewValue();
```

Với attribute là collection hoặc mutable object, cần cân nhắc snapshot và aliasing. Nếu phát notification bằng cách truyền cùng một reference mutable đã bị thay đổi, old/new có thể không phản ánh ảnh chụp trạng thái mong muốn.

Một thiết kế an toàn hơn là dùng giá trị immutable hoặc copy snapshot phù hợp trước khi gửi. Tránh đưa object graph phức tạp hoặc dữ liệu nhạy cảm vào notification, đặc biệt với remote JMX.

### 13.1. Thay đổi thật và thay đổi yêu cầu

Giả sử setter nhận `next=true` nhưng business logic từ chối vì trạng thái không hợp lệ. Không nên phát một notification `old=false, new=true` khi runtime thực tế vẫn false.

Notification nên phản ánh **thay đổi đã áp dụng**, không chỉ phản ánh request được gửi. Nếu operation bất đồng bộ mới tiếp nhận yêu cầu, một notification khác có thể mô tả `ACCEPTED` và notification hoàn thành được gửi sau.

## 14. Vấn đề concurrency khi nhiều client cùng sửa

Giả sử hai client gửi:

```text
Client A: set Enabled=false
Client B: set Enabled=true
```

Nếu setter không đồng bộ, sequence và old/new values có thể không phản ánh thứ tự state transition mà người vận hành mong đợi.

Trong ví dụ Standard MBean, `synchronized` bảo vệ read/update và việc tạo event. Trong môi trường production, có thể tách việc cập nhật nguyên tử khỏi việc phát event để tránh gọi listener trong lock:

```text
lock
  đọc old value
  validate transition
  cập nhật new value
  tăng sequence
unlock
phát notification
```

Cách này giảm thời gian giữ lock, nhưng nếu các thread phát đồng thời sau khi unlock, **thứ tự giao notification** có thể khác thứ tự cập nhật. Nếu thứ tự quan trọng, nên dùng hàng đợi gửi tuần tự hoặc cơ chế event sequencing phù hợp.

Không thể suy ra một hệ thống notification được bảo đảm ordering toàn cục chỉ từ việc sequence number tăng dần ở mỗi MBean.

## 15. Unit test với CountDownLatch

Một bài test tốt không nên dùng `Thread.sleep(1000)` rồi hy vọng callback đã chạy. Dùng `CountDownLatch` để đợi notification với timeout rõ ràng.

Ví dụ JUnit 5:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import javax.management.Attribute;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FeatureSwitchNotificationTest {

    @Test
    void emitsAttributeChangeNotification() throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("com.example.test");

        ObjectName name = new ObjectName(
            "com.example.test:type=FeatureSwitch,name=Main"
        );

        FeatureSwitch bean = new FeatureSwitch();
        server.registerMBean(bean, name);

        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<AttributeChangeNotification> received =
            new AtomicReference<>();

        NotificationListener listener = (event, handback) -> {
            if (event instanceof AttributeChangeNotification change) {
                received.set(change);
                latch.countDown();
            }
        };

        server.addNotificationListener(name, listener, null, null);

        try {
            server.setAttribute(
                name,
                new Attribute("Enabled", Boolean.FALSE)
            );

            assertTrue(
                latch.await(2, TimeUnit.SECONDS),
                "Expected attribute change notification"
            );

            AttributeChangeNotification event = received.get();

            assertNotNull(event);
            assertEquals(
                AttributeChangeNotification.ATTRIBUTE_CHANGE,
                event.getType()
            );
            assertEquals("Enabled", event.getAttributeName());
            assertEquals("boolean", event.getAttributeType());
            assertEquals(Boolean.TRUE, event.getOldValue());
            assertEquals(Boolean.FALSE, event.getNewValue());
            assertTrue(event.getSequenceNumber() > 0);
        } finally {
            server.removeNotificationListener(name, listener);
            server.unregisterMBean(name);
        }
    }
}
```

Test này thực thi hoàn toàn trong một JVM, dùng isolated MBeanServer để tránh xung đột với test khác. Nếu callback đồng bộ, latch vẫn nhận giá trị trước khi `await`; nếu callback bất đồng bộ, `await` giới hạn thời gian chờ.

### 15.1. Kiểm tra không phát event khi giá trị không đổi

Có thể mở rộng test:

1. Đặt `Enabled=false`.
2. Ghi số notification hiện có.
3. Gọi `setAttribute(Enabled=false)` lần nữa.
4. Xác nhận implementation không phát thêm event theo contract.

Việc “không có sự kiện” khó chứng minh tuyệt đối bằng đợi thời gian. Với test local đồng bộ và implementation xác định, có thể dùng bộ đếm notification rồi kiểm tra ngay sau setter; nếu có async executor, cần sử dụng cơ chế deterministic synchronization hoặc kiểm soát executor.

## 16. Test Spring NotificationPublisher

Để test integration với Spring exporter:

1. Mở `AnnotationConfigApplicationContext` chứa `SpringJmxLabConfig`.
2. Lấy `MBeanServer` bean từ context.
3. Xác nhận `isRegistered(ObjectName)`.
4. Đăng ký listener trước khi thực hiện thay đổi.
5. Gọi `server.setAttribute(name, Attribute("Enabled", false))`.
6. Đợi callback bằng latch.
7. Assert `AttributeChangeNotification` có `attributeName`, `oldValue`, `newValue`, type chính xác.
8. Đọc `server.getAttribute(name, "Enabled")` để xác nhận trạng thái runtime thực sự.
9. Gỡ listener trong `finally`.
10. Đóng context để exporter dọn đăng ký của chính nó.

Bài test này khác unit test thuần ở điểm xác minh **Spring MBeanExporter đã cấp NotificationPublisher và MBeanInfo/notification path hoạt động như mong đợi**. Nếu publisher không được cấp, phải xem cấu hình exporter, cơ chế wrapping/adapting MBean và lifecycle, không chỉ nhìn event construction.

## 17. Khám phá notification qua JConsole

Nếu MBean được đăng ký vào platform server và JConsole kết nối cùng JVM:

1. Mở tab **MBeans**.
2. Tìm ObjectName, ví dụ `com.example.lab:type=FeatureSwitch,name=Main`.
3. Xem **Attributes** và giá trị `Enabled`.
4. Xem **Notifications** nếu JConsole hiển thị khu vực notification cho MBean này.
5. Đăng ký nhận notification trên công cụ nếu chức năng đó có sẵn.
6. Thay đổi `Enabled` bằng đường quản trị được phép.
7. Quan sát event với type `jmx.attribute.change`.

Kết quả giao diện có thể khác theo phiên bản JDK/JConsole và loại MBean. Nếu MBean nằm trên private MBeanServer, JConsole nối platform server sẽ không tự thấy resource. Cần connector trỏ đúng server hoặc sử dụng test Java như các phần trước.

Không dùng JConsole để thử thay đổi trạng thái production nếu chưa được phê duyệt. Một attribute writable dù chỉ là `boolean` vẫn có thể ảnh hưởng chức năng nghiệp vụ hoặc vận hành.

## 18. Listener lifecycle và memory leak

Một listener có thể giữ reference đến service, bean hoặc Spring context. Nếu MBean broadcaster sống lâu hơn ứng dụng (nhất là khi dùng shared platform MBeanServer), listener cũ có thể giữ classloader cũ sau redeploy.

Quy tắc:

- Lưu reference đến listener đã đăng ký.
- Gọi `removeNotificationListener` khi không còn nhu cầu.
- Đóng JMXConnector khi không dùng.
- Để `MBeanExporter` dọn MBean do Spring quản lý khi context đóng.
- Dọn MBean được đăng ký thủ công theo đúng ownership.
- Không unregister bừa MBean của framework/container.
- Tránh lưu listener vào static collection sống suốt JVM.

Nếu `removeNotificationListener` trả lỗi vì MBean đã bị unregister, kiểm tra thứ tự cleanup và ownership. Không nên coi việc listener không còn nhận event là bằng chứng mọi reference đã được giải phóng.

## 19. Remote notification và độ tin cậy

Khi client kết nối qua JMX Remote, notification đi qua connector. Một sự kiện có thể phát lúc client mất kết nối và không được replay.

Một consumer có tính sẵn sàng cao nên:

1. Kết nối và đọc trạng thái hiện tại.
2. Đăng ký notification listener.
3. Đọc lại snapshot nếu cần tránh khoảng trống giữa initial read và registration.
4. Theo dõi connect/disconnect và lỗi transport.
5. Khi reconnect, đăng ký lại listener.
6. Resync state thay vì giả định đã nhận đầy đủ mọi event.
7. Dùng sequence number để hỗ trợ chẩn đoán, không coi nó là durable offset.

Nếu yêu cầu nghiệp vụ cần bảo đảm delivery, audit và replay chính xác, dùng event broker chuyên dụng, database log hoặc cơ chế durable khác. Notification JMX phù hợp cho telemetry và quản trị, không phải thay thế một bus sự kiện nghiệp vụ bền vững.

## 20. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Listener không nhận event | Chưa `addNotificationListener` hoặc sai ObjectName/server | Kiểm tra đăng ký và `isRegistered` |
| `InstanceNotFoundException` khi đăng ký listener | MBean chưa được register | Khởi tạo exporter/server trước khi đăng ký |
| `ListenerNotFoundException` lúc cleanup | Xóa không đúng listener/registration | Giữ reference và unregister đúng cặp |
| Event bị thiếu | Đăng ký sau khi thay đổi hoặc kết nối mất | Đọc snapshot, resubscribe và resync |
| Event có old/new sai | Trạng thái mutable, race hoặc phát trước khi áp dụng | Snapshot và đồng bộ transition |
| Event lặp | Hai đường publish hoặc hai listeners trùng | Kiểm tra broadcaster/publisher và lifecycle |
| `getNotifications()` không chứa type | Metadata broadcaster/assembler thiếu cấu hình | Kiểm tra `getNotificationInfo` hoặc Spring metadata |
| JConsole không thấy MBean | Kiểm tra sai MBeanServer hoặc connector | Dùng đúng server/connection |
| Test lúc pass lúc fail | Đợi bằng sleep hoặc timing race | Dùng latch và server cô lập |
| Heap tăng sau redeploy | Listener hoặc MBean giữ classloader cũ | Quản lý cleanup và reference graph |

Cần phân biệt lỗi metadata với lỗi phát sự kiện thực tế. Một MBean có notification metadata không đồng nghĩa mọi state transition sẽ phát event đúng; ngược lại, có thể có event phát nhưng client không thấy type nếu metadata cấu hình không đầy đủ.

## 21. Bài tập tự thực hành

### Bài 1 — Standard MBean

1. Tạo `FeatureSwitchMBean` và `FeatureSwitch`.
2. Tạo isolated MBeanServer.
3. Đăng ký ObjectName `com.example.lab:type=FeatureSwitch,name=Main`.
4. Thêm listener bắt `AttributeChangeNotification`.
5. Gọi `setAttribute("Enabled", false)`.
6. In `attributeName`, `attributeType`, old/new, sequence, timestamp.
7. Kiểm tra `getAttribute("Enabled")` trả false.
8. Ghi false lần nữa và quan sát contract không phát thêm sự kiện.
9. Gỡ listener và unregister MBean.

### Bài 2 — Spring JMX

1. Tạo `SpringFeatureSwitch` implements `NotificationPublisherAware`.
2. Export qua `MBeanExporter` và metadata assembler.
3. Đăng ký listener với `MBeanServer` của context.
4. Thay đổi `Enabled` qua JMX.
5. Xác nhận listener nhận type `jmx.attribute.change`.
6. Đọc `MBeanInfo.getNotifications()`.
7. Đóng context và quan sát cleanup.

### Bài 3 — Phân tích thực tế

Giả sử một client remote mất kết nối trong lúc `Enabled` thay đổi ba lần. Hãy giải thích tại sao reconnect rồi chờ notification tiếp theo không bảo đảm biết trạng thái mới nhất. Thiết kế bước resync bằng `getAttribute` và theo dõi sequence.

## 22. Câu hỏi tự kiểm tra

**1. `AttributeChangeNotification` dùng để làm gì?** Thông báo một attribute đã thay đổi, kèm tên, kiểu, giá trị trước và sau.

**2. `getAttribute` khác notification thế nào?** `getAttribute` đọc snapshot hiện tại; notification thông báo sự kiện thay đổi.

**3. Type chuẩn của attribute change notification là gì?** `AttributeChangeNotification.ATTRIBUTE_CHANGE`, có giá trị `jmx.attribute.change`.

**4. `NotificationBroadcasterSupport` có vai trò gì?** Cung cấp cơ chế đăng ký listener và phát notification cho MBean.

**5. Spring `NotificationPublisherAware` giúp gì?** Cho phép bean nhận publisher do Spring JMX exporter cung cấp để gửi notification.

**6. Vì sao phải đăng ký listener trước khi đổi state?** Nếu đăng ký sau, event trước đó có thể đã phát và không được replay.

**7. Sequence number có duy nhất giữa mọi MBean không?** Không, nó thường có phạm vi theo nguồn phát.

**8. Notification có đảm bảo durable delivery không?** Không. Cần cơ chế riêng nếu muốn replay/bảo đảm nhận đầy đủ.

**9. Vì sao phải gỡ listener?** Để tránh giữ reference, rò rỉ memory và callback sau khi context dừng.

**10. Khi event nói newValue=false, có nên dùng nó thay cho snapshot mãi mãi không?** Không; client nên resync khi cần, nhất là sau reconnect hoặc mất event.

## 23. Ghi nhớ

- **`AttributeChangeNotification`** là notification chuẩn của JMX cho thay đổi attribute.
- Notification mang **attributeName, attributeType, oldValue, newValue, sequenceNumber, timestamp**.
- Dùng **`NotificationBroadcasterSupport`** với Standard MBean hoặc **Spring `NotificationPublisherAware`** khi export qua Spring JMX.
- Đăng ký listener bằng **`MBeanServer.addNotificationListener`**, gỡ bằng `removeNotificationListener`.
- MBean nên công bố notification type qua **`MBeanInfo.getNotifications()`**.
- Chỉ phát event khi state transition thực sự được áp dụng, tránh gửi thông tin sai.
- **Listener lifecycle** phải đi cùng MBean/connector lifecycle để tránh classloader leak.
- Dùng **CountDownLatch** trong test thay vì phụ thuộc vào `Thread.sleep`.
- Remote notification **không đảm bảo durable delivery**; khi reconnect cần đọc snapshot/resync.
- Không gửi bí mật hoặc dữ liệu nhạy cảm trong notification, nhất là khi dùng remote JMX.

Thực hành phát và nhận `AttributeChangeNotification` giúp hiểu cách MBean thông báo thay đổi trạng thái theo sự kiện. Khi kết hợp metadata đúng, listener được quản lý vòng đời và cơ chế đồng bộ snapshot, Spring Framework JMX có thể cung cấp kênh quan sát quản trị hữu ích mà không nhầm lẫn với hệ thống message delivery bền vững.