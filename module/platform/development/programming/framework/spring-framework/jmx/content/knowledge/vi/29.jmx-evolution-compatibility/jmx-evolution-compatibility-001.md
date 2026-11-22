# Thêm attribute mới mà không phá client hiện có trong Spring Framework JMX

## 1. Bối cảnh và mục tiêu

Trong Java Management Extensions (**JMX**), MBean cung cấp một **hợp đồng quản trị** gồm attributes, operations và notifications. Client có thể là JConsole, VisualVM, một script Java, hệ thống giám sát hoặc ứng dụng Spring sử dụng `MBeanProxyFactoryBean`.

Khi ứng dụng tiến hóa, ta thường muốn thêm một attribute mới: số job lỗi, thời điểm refresh gần nhất, trạng thái backlog hoặc cấu hình runtime. Thay đổi tưởng chừng nhỏ này vẫn có thể khiến client hiện có gặp lỗi nếu đồng thời làm đổi `ObjectName`, kiểu dữ liệu, quyền truy cập hoặc cách expose thuộc tính cũ.

**Mục tiêu:** thêm khả năng quan sát mới mà giữ nguyên hành vi hợp lệ của client cũ. Phương pháp ưu tiên là **mở rộng hợp đồng theo hướng tương thích (additive evolution)**, sau đó kiểm tra từ góc nhìn client thực tế.

Bài học thuộc nhóm **Tiến hóa và tương thích** trong Spring Framework JMX, tập trung vào:

- Khái niệm compatibility cho metadata MBean.
- Quy tắc thêm attribute an toàn.
- Ví dụ Standard MBean và Spring annotation exporter.
- Cách client typed, dynamic client và monitoring script phản ứng.
- Cơ chế versioning, rollout và rollback.
- Kiểm thử `MBeanInfo` để phát hiện thay đổi phá vỡ hợp đồng.

## 2. Hợp đồng JMX bao gồm những gì?

Giả sử một ứng dụng xuất MBean:

~~~text
ObjectName:
  com.example.orders:type=Queue,name=payments

Attributes:
  PendingCount : long [read-only]
  Enabled      : boolean [read/write]

Operations:
  pause()      : void
  resume()     : void
~~~

Một client có thể gọi:

~~~java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=payments"
);

Long pendingCount = (Long) connection.getAttribute(
    name, "PendingCount"
);
~~~

Hoặc dùng typed interface:

~~~java
public interface QueueAdminClient {
    long getPendingCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void pause();
    void resume();
}
~~~

Những yếu tố có thể là một phần của contract:

| Thành phần | Ý nghĩa đối với client |
| --- | --- |
| `ObjectName` | Tìm đúng MBean |
| Tên attribute | Gọi `getAttribute`, `setAttribute` |
| Java/JMX type | Cast, deserialize và hiển thị |
| `isReadable()` | Có quyền đọc theo metadata |
| `isWritable()` | Có lối ghi theo metadata |
| Tên/chữ ký operation | Gọi `invoke` |
| Notification types | Lọc và xử lý sự kiện |
| Semantic | Giá trị và đơn vị mang nghĩa gì |
| Lifecycle | MBean còn tồn tại, có bị replace không |

Không phải mọi thay đổi đều breaking như nhau. Thêm một attribute chỉ đọc thường ít rủi ro hơn đổi kiểu của attribute hiện có. Nhưng **tương thích không chỉ là mã Java vẫn biên dịch**: dashboard, collector và script có thể dựa vào tên, đơn vị hoặc cách đọc metadata.

## 3. Quy tắc vàng: thêm mới, không thay đổi cái cũ

Ví dụ trước phiên bản mới:

~~~text
PendingCount : long [read-only]
Enabled      : boolean [read/write]
~~~

Sau khi thêm:

~~~text
PendingCount    : long [read-only]
Enabled         : boolean [read/write]
LastRefreshTime : String [read-only]  <-- mới
~~~

Đây là mở rộng theo hướng tương thích nếu:

1. `ObjectName` vẫn giữ nguyên.
2. `PendingCount` vẫn là `long`, readable và giữ semantic.
3. `Enabled` vẫn là `boolean`, cả đọc và ghi đều hoạt động.
4. Các operation cũ vẫn được expose.
5. Client cũ không bị bắt buộc biết `LastRefreshTime`.
6. Attribute mới không gây tác động phụ làm thay đổi trạng thái cũ ngoài ý muốn.

Phần lớn client đọc một attribute theo tên sẽ không bị ảnh hưởng nếu MBean có thêm attribute khác. Tuy nhiên, client tự duyệt `MBeanInfo` có thể giả định sai rằng danh sách attributes là cố định, và cần được kiểm thử.

### Bảng thay đổi và mức rủi ro

| Thay đổi | Đánh giá thông thường | Lưu ý |
| --- | --- | --- |
| Thêm attribute read-only kiểu đơn giản | Thường tương thích | Dynamic client có thể duyệt danh sách cố định |
| Thêm attribute read/write | Có thể tương thích | Tăng bề mặt điều khiển và yêu cầu phân quyền |
| Đổi `int` thành `long` | Có nguy cơ breaking | Client cast hoặc proxy type cũ |
| Đổi tên `PendingCount` thành `QueueDepth` | Breaking với client cũ | Cần giữ alias hoặc migration |
| Xóa getter cũ | Breaking | `AttributeNotFoundException` |
| Đổi read/write thành read-only | Breaking với client ghi | `setAttribute` bị từ chối |
| Đổi ý nghĩa từ “pending” sang “total” | Breaking về semantic | Có thể không phát sinh lỗi kỹ thuật |
| Đổi ObjectName/domain | Breaking | Client không tìm được MBean |
| Thêm operation | Thường additive | Kiểm soát quyền và side effect |
| Thay chữ ký operation hiện tại | Có nguy cơ breaking | Typed client và `invoke` không khớp |

## 4. Ví dụ Standard MBean: thêm một getter mới

### Phiên bản đầu

Interface quản trị:

~~~java
package com.example.orders.management;

public interface PaymentQueueAdminMBean {
    long getPendingCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
~~~

Implementation:

~~~java
package com.example.orders.management;

public class PaymentQueueAdmin implements PaymentQueueAdminMBean {
    private volatile long pendingCount;
    private volatile boolean enabled = true;

    @Override
    public long getPendingCount() {
        return pendingCount;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

JMX Standard MBean introspection thường chuyển:

~~~text
getPendingCount()     -> PendingCount
isEnabled()           -> Enabled (readable)
setEnabled(boolean)   -> Enabled (writable)
~~~

### Phiên bản mở rộng

Thêm getter vào **interface MBean** và implementation:

~~~java
public interface PaymentQueueAdminMBean {
    long getPendingCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);

    // New additive attribute.
    String getLastRefreshTime();
}
~~~

~~~java
import java.time.Instant;

public class PaymentQueueAdmin implements PaymentQueueAdminMBean {
    private volatile long pendingCount;
    private volatile boolean enabled = true;
    private volatile Instant lastRefreshTime = Instant.EPOCH;

    @Override
    public long getPendingCount() {
        return pendingCount;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public String getLastRefreshTime() {
        return lastRefreshTime.toString();
    }
}
~~~

Trong ví dụ, `LastRefreshTime` được expose dưới kiểu `java.lang.String`. Chọn String ISO-8601 giúp client JMX cơ bản đọc dễ hơn so với truyền trực tiếp một object `Instant` tùy vào khả năng serialization/mapping của client.

**Điểm mấu chốt:** Với Standard MBean, chỉ thêm method vào implementation mà không thêm vào interface `PaymentQueueAdminMBean` không đảm bảo method được công bố như attribute. Interface MBean là nguồn hợp đồng của Standard MBean.

## 5. Ví dụ Spring @ManagedAttribute: mở rộng POJO

Với Spring `AnnotationMBeanExporter`, có thể đánh dấu getter:

~~~java
package com.example.orders.management;

import java.time.Instant;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments",
    description = "Payment queue management"
)
public class PaymentQueueManagement {

    private volatile long pendingCount;
    private volatile boolean enabled = true;
    private volatile Instant lastRefreshTime = Instant.EPOCH;

    @ManagedAttribute(description = "Queued payment jobs")
    public long getPendingCount() {
        return pendingCount;
    }

    @ManagedAttribute(description = "Whether queue processing is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    // Attribute mới: chỉ đọc.
    @ManagedAttribute(
        description = "Last successful cache/configuration refresh in ISO-8601 UTC"
    )
    public String getLastRefreshTime() {
        return lastRefreshTime.toString();
    }
}
~~~

Khi Spring exporter đọc metadata, các getter/setter được chọn có thể trở thành JMX attributes. Hãy xác minh `MBeanInfo` thực tế thay vì chỉ suy luận từ annotation.

### Vì sao không thêm setter nếu chưa cần?

~~~java
@ManagedAttribute
public void setLastRefreshTime(String value) {
    ...
}
~~~

Nếu cho client sửa `LastRefreshTime`, ta đang mở thêm khả năng điều khiển trạng thái. Với timestamp thực tế của hệ thống, đây thường là **dữ liệu quan sát**, không phải cấu hình cần thay đổi qua JMX. Do đó chỉ công bố getter sẽ giảm nguy cơ vận hành.

### Kiểm tra exporter hiện có

Trong Spring Boot hoặc ứng dụng Spring đã có cấu hình JMX, tránh tạo `AnnotationMBeanExporter` thứ hai chỉ để thêm getter. Một exporter trùng có thể gây `InstanceAlreadyExistsException` hoặc thay MBean ngoài ý muốn tùy registration policy.

## 6. Đừng đổi ObjectName khi chỉ thêm attribute

Nếu MBean trước đây có tên:

~~~text
com.example.orders:type=Queue,name=payments
~~~

thì việc thêm `LastRefreshTime` không nhất thiết cần đổi thành:

~~~text
com.example.orders:type=Queue,name=paymentsV2
~~~

Đổi ObjectName sẽ buộc client cũ cập nhật, mặc dù phần API cũ vẫn nguyên.

Khi chỉ có thay đổi additive, thường nên giữ tên ổn định. Có thể dùng metadata version để giúp client biết khả năng mới, nhưng phải tránh thay tên registry nếu không thực sự cần.

### Khi nào versioned ObjectName có ích?

Nếu cần thay hợp đồng **không tương thích**, ví dụ:

~~~text
com.example.orders:type=QueueAdmin,version=v1,name=payments
com.example.orders:type=QueueAdmin,version=v2,name=payments
~~~

Client cũ có thể tiếp tục dùng v1 trong giai đoạn chuyển tiếp, client mới dùng v2. Nhưng việc expose đồng thời hai interface điều khiển cùng resource cần concurrency và ownership rõ ràng để tránh thao tác trùng hoặc không nhất quán.

## 7. Tên, kiểu và semantic phải ổn định

Một attribute gồm nhiều yếu tố hơn một getter.

### 7.1. Tên

Nếu cũ là `PendingCount`, đừng đổi thành `PendingJobs` mà không có kế hoạch migration.

### 7.2. Kiểu

Nếu cũ là `long`, giữ `long` khi có thể. Một typed client có thể viết:

~~~java
long pending = queueAdmin.getPendingCount();
~~~

và một dynamic client có thể cast:

~~~java
Long pending = (Long) connection.getAttribute(name, "PendingCount");
~~~

Nếu MBean đổi sang `int`, dynamic client có thể gặp `ClassCastException` và typed proxy có thể không tương thích.

### 7.3. Read/write flags

Nếu attribute cũ writable, chuyển nó sang read-only là breaking đối với client đang gọi setter. Ngược lại, thêm setter vào attribute trước đây chỉ đọc có thể là mở rộng về khả năng nhưng cũng làm tăng rủi ro security.

### 7.4. Semantic và đơn vị

Nếu `AverageLatency` trước đây là milliseconds, không âm thầm đổi thành seconds mà giữ nguyên tên/kiểu. Client vẫn chạy nhưng alert threshold sai.

Một attribute mới nên mô tả rõ:

- Đơn vị.
- Phạm vi đo.
- Thời gian cập nhật.
- Giá trị khi chưa có dữ liệu.
- Quy tắc reset.
- Ý nghĩa ở môi trường nhiều replica.

Ví dụ `LastRefreshTime` là thời điểm **refresh thành công gần nhất**, không phải thời điểm bắt đầu refresh.

## 8. Kiểu dữ liệu mới và khả năng tương thích client

Một attribute mới có thể dùng kiểu Java đơn giản:

~~~text
boolean, int, long, double, String
~~~

Những kiểu này thường dễ sử dụng với client JMX chung. Đối với kiểu phức tạp, cần xem xét:

- Serializability khi remote.
- Classpath hai phía.
- MXBean Open Types.
- `CompositeData` hoặc `TabularData`.
- Cách JConsole/VisualVM hiển thị.
- Khả năng chuyển đổi của framework exporter.

Ví dụ tránh bắt mọi client có class `CacheSnapshot` tùy chỉnh chỉ để đọc một metric.

Thay vì:

~~~java
public CacheSnapshot getSnapshot() { ... }
~~~

có thể ưu tiên những attribute đơn giản:

~~~java
public long getHitCount() { ... }
public long getMissCount() { ... }
public String getLastRefreshTime() { ... }
~~~

Nếu cần dữ liệu có cấu trúc, thiết kế MXBean hoặc Open Types với hợp đồng rõ ràng. Đây là quyết định API riêng, không chỉ là chuyện thêm getter.

## 9. Client typed có cần cập nhật không?

Giả sử một client Spring có interface:

~~~java
public interface QueueAdminClient {
    long getPendingCount();
    boolean isEnabled();
}
~~~

Sau khi server thêm `LastRefreshTime`, client cũ có thể tiếp tục gọi hai method cũ nếu hợp đồng tương ứng còn nguyên. Không bắt buộc sửa interface client cũ chỉ vì server có thêm attribute.

Client mới có thể mở rộng:

~~~java
public interface QueueAdminClientV2 {
    long getPendingCount();
    boolean isEnabled();
    String getLastRefreshTime();
}
~~~

Với `MBeanProxyFactoryBean`, interface được cấu hình làm proxy contract. Server mới phải công bố attribute tương ứng, nhưng compiler Java chỉ biết interface phía client.

### Mixed versions

Trong triển khai rolling update, có thể có:

~~~text
node-a: server v2 -> has LastRefreshTime
node-b: server v1 -> no LastRefreshTime
node-c: server v2 -> has LastRefreshTime
~~~

Client mới nếu truy cập node-b và gọi getter mới sẽ gặp lỗi. Vì vậy cần kế hoạch rollout hoặc capability detection thay vì giả định mọi replica đã nâng cấp cùng lúc.

## 10. Dynamic client nên phát hiện capability

Một client dùng `MBeanServerConnection` có thể kiểm tra attribute trước khi đọc:

~~~java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public static boolean hasReadableAttribute(
        MBeanServerConnection connection,
        ObjectName name,
        String attributeName
) throws Exception {
    MBeanInfo info = connection.getMBeanInfo(name);

    for (MBeanAttributeInfo attribute : info.getAttributes()) {
        if (attributeName.equals(attribute.getName())
                && attribute.isReadable()) {
            return true;
        }
    }
    return false;
}
~~~

Sử dụng:

~~~java
if (hasReadableAttribute(connection, name, "LastRefreshTime")) {
    String value = (String) connection.getAttribute(
        name, "LastRefreshTime"
    );
    System.out.println(value);
} else {
    System.out.println("LastRefreshTime not supported");
}
~~~

Cơ chế này hữu ích khi client mới phải tương thích với server cũ trong rolling deployment.

**Lưu ý thời điểm:** có thể xảy ra race condition: client đọc metadata ở T1, MBean bị replace ở T2, rồi `getAttribute` ở T3 thất bại. Capability detection nên đi kèm xử lý exception runtime phù hợp, không coi metadata là bằng chứng vĩnh viễn.

## 11. Kiểm thử compatibility qua MBeanInfo

`MBeanInfo` cung cấp mô tả giao diện thực tế của MBean.

Ví dụ helper lấy metadata:

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

public static Map<String, MBeanAttributeInfo> attributes(
        MBeanInfo info
) {
    return Arrays.stream(info.getAttributes())
        .collect(Collectors.toMap(
            MBeanAttributeInfo::getName,
            value -> value
        ));
}
~~~

Khi so sánh hai phiên bản, điều quan trọng không phải danh sách attribute phải giống hệt, mà là **mọi attribute cũ cần còn tương thích**.

Một assertion khái niệm:

~~~java
Map<String, MBeanAttributeInfo> oldAttributes =
    attributes(oldInfo);

Map<String, MBeanAttributeInfo> newAttributes =
    attributes(newInfo);

for (var entry : oldAttributes.entrySet()) {
    String name = entry.getKey();
    MBeanAttributeInfo oldAttr = entry.getValue();
    MBeanAttributeInfo newAttr = newAttributes.get(name);

    if (newAttr == null) {
        throw new AssertionError("Removed attribute: " + name);
    }
    if (!oldAttr.getType().equals(newAttr.getType())) {
        throw new AssertionError("Changed type: " + name);
    }
    if (oldAttr.isReadable() && !newAttr.isReadable()) {
        throw new AssertionError("Lost read access: " + name);
    }
    if (oldAttr.isWritable() && !newAttr.isWritable()) {
        throw new AssertionError("Lost write access: " + name);
    }
}
~~~

Đoạn sử dụng `var` nên cần Java 10+. Nếu dự án dùng Java 8, thay `var` bằng `Map.Entry<String, MBeanAttributeInfo>`.

Test trên cho phép bổ sung attributes mới và phát hiện một số thay đổi phá vỡ hợp đồng cũ. Nó chưa kiểm tra semantic, security hoặc operations; các hợp đồng quan trọng cần kiểm tra thêm.

## 12. Integration test với MBeanServer riêng

Để tránh gây ảnh hưởng platform MBeans hoặc những test khác, có thể dùng:

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server = MBeanServerFactory.newMBeanServer();
~~~

Ví dụ luồng test:

1. Tạo Spring context test.
2. Đăng ký custom bean và exporter vào test MBeanServer.
3. Xác nhận ObjectName tồn tại.
4. Đọc `MBeanInfo`.
5. Assert attributes cũ còn đúng tên/kiểu/read-write flags.
6. Assert `LastRefreshTime` mới tồn tại và readable.
7. Gọi `getAttribute` trên cả cũ và mới.
8. Đóng Spring context.
9. Xác nhận MBean do exporter quản lý đã unregister.

### Ví dụ assert attribute mới

~~~java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=payments"
);

MBeanInfo info = server.getMBeanInfo(name);

boolean found = false;

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    if ("LastRefreshTime".equals(attribute.getName())) {
        found = "java.lang.String".equals(attribute.getType())
            && attribute.isReadable()
            && !attribute.isWritable();
    }
}

assertTrue(found, "Expected read-only LastRefreshTime");
~~~

`server` và `assertTrue` là các thành phần đã được khởi tạo/import trong test fixture; snippet chỉ minh họa assertion.

## 13. Compatibility không chỉ nằm ở metadata

Một attribute mới có thể khiến server vẫn công bố các attribute cũ nhưng làm đổi hành vi runtime.

Ví dụ getter mới:

~~~java
@ManagedAttribute
public String getRecentErrors() {
    return database.loadAllErrorsAsText();
}
~~~

Nó có thể gây vấn đề:

- JConsole hoặc collector poll thường xuyên làm tăng tải database.
- Getter có thể chặn lâu hoặc ném lỗi do downstream.
- Dữ liệu text dài gây overhead network.
- Query có thể giữ lock hoặc ảnh hưởng latency nghiệp vụ.
- Getter vô tình expose dữ liệu nhạy cảm.

Do đó, một thay đổi “additive” vẫn cần chú ý **hiệu năng, bảo mật và chi phí quan sát**.

### Getter mới nên nhẹ và không side effect

Ưu tiên:

~~~java
@ManagedAttribute
public long getRecentErrorCount() {
    return errorCounter.get();
}
~~~

Nếu cần snapshot phức tạp, có thể dùng cache, giới hạn dữ liệu trả về hoặc thiết kế operation/endpoint chuyên biệt.

**Không coi metadata tương thích là bảo đảm hiệu năng tương thích.**

## 14. Không tạo attribute bằng cách sửa tên method cũ

Ví dụ muốn thêm `QueueDepth`, không nên thay:

~~~java
public long getPendingCount()
~~~

bằng:

~~~java
public long getQueueDepth()
~~~

và xóa getter cũ. Trong introspection JMX, đó là loại bỏ `PendingCount` rồi thêm `QueueDepth`. Client cũ dùng `PendingCount` sẽ lỗi.

Nếu hai tên cần cùng tồn tại tạm thời, có thể:

~~~java
@ManagedAttribute
public long getPendingCount() {
    return queueService.pendingCount();
}

@ManagedAttribute
public long getQueueDepth() {
    return queueService.pendingCount();
}
~~~

`queueService` là dependency minh họa. Hai getter cùng đọc một nguồn dữ liệu giúp nhất quán, nhưng phải tài liệu hóa rằng hai attributes là aliases; tránh tạo hai bộ đếm độc lập có thể lệch.

Khi dự định loại bỏ alias cũ, cần một migration plan cụ thể cho consumer và có thời gian deprecation phù hợp.

## 15. Thêm attribute writable: đánh giá quyền truy cập

Một attribute mới với setter:

~~~java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int maxWorkers) {
    if (maxWorkers < 1 || maxWorkers > 64) {
        throw new IllegalArgumentException("Invalid maxWorkers");
    }
    this.maxWorkers = maxWorkers;
}
~~~

là thay đổi nhiều hơn chỉ mở rộng dữ liệu quan sát: nó tạo **khả năng chỉnh runtime configuration**.

Cần xem:

- Client nào có quyền JMX write?
- Remote JMX connector có authentication, TLS, authorization không?
- Giá trị được validate đầy đủ?
- Setter áp dụng thay đổi tới tài nguyên thật?
- Thay đổi có thread-safe và nhất quán không?
- Có cần audit?
- Có phải giới hạn theo môi trường production?
- Có cần tránh expose nếu chưa có nhu cầu quản trị thực sự?

**Không tự động cấp quyền write rộng chỉ vì attribute mới cần test.** Nên có môi trường test và tài khoản quản trị đúng quyền.

## 16. Khả năng tương thích với dashboard và monitoring collectors

Một dashboard có thể đọc theo:

~~~text
ObjectName: com.example.orders:type=Queue,name=payments
Attribute:  PendingCount
Type:       long
~~~

Sau khi thêm `LastRefreshTime`:

- Collector đọc `PendingCount` theo tên sẽ thường tiếp tục hoạt động.
- Collector khám phá tất cả attributes có thể xuất thêm metric hoặc log mới.
- Nếu collector xử lý kiểu mới không hỗ trợ, nó có thể báo lỗi khi enumerate.
- Nếu dashboard kỳ vọng số lượng attribute cố định, cần kiểm thử.
- Với nhiều replica, collector có thể gặp server v1 và v2 khác nhau trong rolling update.

### Giữ contract bằng golden snapshot

Có thể lưu một bản MBeanInfo contract được chuẩn hóa làm baseline trong test repository, gồm:

~~~text
ObjectName
Attribute name
Attribute type
Readable/writable flags
Operation name/signature
Notification types (nếu liên quan)
~~~

Khi nâng cấp, test chỉ yêu cầu các thành phần cũ vẫn tương thích, không ép metadata mới giống y hệt. Không nên so description hoặc thứ tự attribute nếu chúng không thực sự thuộc hợp đồng client; chúng có thể thay đổi giữa phiên bản hoặc assembler.

## 17. Kế hoạch rollout an toàn

Một chiến lược triển khai:

### Giai đoạn A — thêm attribute ở server

Triển khai bản MBean mới nhưng giữ toàn bộ API cũ. Chưa bắt client mới bắt buộc sử dụng attribute mới.

### Giai đoạn B — xác minh registry

Dùng JConsole, `MBeanInfo` hoặc integration tests để xác nhận trên một số JVM:

~~~text
PendingCount    present
Enabled         present
LastRefreshTime present
~~~

### Giai đoạn C — cập nhật monitoring/client

Client mới có thể đọc attribute mới nếu phát hiện capability hoặc sau khi server fleet đã nâng cấp.

### Giai đoạn D — theo dõi mixed versions

Trong rolling update, một số node chưa có attribute mới. Tránh coi việc thiếu attribute là incident nếu còn trong cửa sổ migration được công bố.

### Giai đoạn E — ổn định hợp đồng

Sau khi toàn bộ fleet hỗ trợ, có thể bắt đầu yêu cầu attribute mới trong contract tests của phiên bản tương ứng.

Nếu có kế hoạch loại bỏ attribute cũ, đó là một thay đổi breaking khác, cần migration riêng thay vì gộp vào lần “thêm mới”.

## 18. Rollback cần được tính trước

Nếu client v2 bắt buộc gọi `LastRefreshTime`, nhưng server rollback về v1 không có attribute này, client v2 có thể lỗi.

Vì vậy rollback strategy cần:

- Client mới hỗ trợ feature detection và fallback.
- Hoặc giữ server v2 hoạt động đến khi client không cần attribute mới.
- Hoặc triển khai theo thứ tự: server trước, client sau; rollback client trước, server sau.
- Có monitoring phát hiện `AttributeNotFoundException` và lỗi typed proxy.
- Không thay đổi ObjectName để “giải quyết nhanh” lỗi compatibility.

Khả năng rollback là một phần của thiết kế additive change, không phải chỉ là vấn đề deployment pipeline.

## 19. Thay thế MBean có thể làm mất listener

Nếu nâng cấp sử dụng `RegistrationPolicy.REPLACE_EXISTING` trong cùng MBeanServer, một MBean mới có thể thay MBean cũ dưới cùng ObjectName.

Hệ quả:

- Client có thể gặp khoảng thời gian ObjectName không đăng ký.
- Typed proxy có thể gọi MBean mới nếu contract còn tương thích.
- Subscription notification của emitter cũ không mặc nhiên chuyển sang emitter mới.
- Trạng thái trong adapter cũ có thể mất.
- Operation đang chạy trên object cũ không tự dừng.

Do đó, khi chỉ thêm attribute, **tránh replace runtime không cần thiết** nếu có thể dùng quá trình deploy/lifecycle bình thường. Nếu replace là bắt buộc, hãy có kế hoạch re-subscribe, trạng thái và ownership.

## 20. Thêm attribute liên quan đến versioning

Đôi khi client cần biết phiên bản management API:

~~~java
@ManagedAttribute(
    description = "Management interface schema version"
)
public String getManagementSchemaVersion() {
    return "2";
}
~~~

Một attribute kiểu này giúp diagnostics. Tuy nhiên, nếu client cũ không biết attribute version, không nên bắt nó đọc version để tiếp tục sử dụng các attribute đã có.

Có thể dùng version làm tín hiệu bổ sung, nhưng **capability detection qua MBeanInfo** thường đáng tin hơn nếu client cần quyết định có đọc một attribute cụ thể hay không.

Ngoài ra, chỉ tăng version string không làm API tự tương thích: vẫn cần giữ tên/kiểu/quyền của các attributes cũ.

## 21. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Client cũ bị `AttributeNotFoundException` | Đổi/xóa attribute cũ | Giữ getter cũ hoặc alias |
| Client cũ `ClassCastException` | Đổi kiểu attribute | Duy trì kiểu cũ |
| Typed proxy lỗi runtime | Server thiếu method/getter theo interface | So `MBeanInfo` và interface |
| JConsole thấy attribute mới nhưng script không đọc được | Tên JMX khác tên client gọi | Dùng đúng ObjectName/attribute name |
| Client mới lỗi trên một số node | Rolling update còn server v1 | Capability detection/rollout order |
| Dashboard nhầm metric | Đổi semantic hoặc đơn vị | Tài liệu và tên mới rõ nghĩa |
| Chậm sau release | Getter mới tốn tài nguyên | Snapshot/cache và polling hợp lý |
| Lộ dữ liệu nhạy cảm | Attribute mới chứa dữ liệu không nên expose | Scope/bảo mật/redaction |
| Conflict ObjectName | Tạo exporter trùng khi nâng cấp | Ownership và auto-config |
| Notification ngừng sau deploy | MBean bị replace/unregister | Re-subscribe và lifecycle handling |
| Setter mới bị gọi ngoài ý muốn | Quyền readwrite rộng | Least privilege và validation |
| Attribute mới sai kiểu remote | Complex type khó deserialize | String/Open Types/MXBean |

## 22. Checklist trước khi phát hành

1. **ObjectName** có giữ nguyên không?
2. Mọi attribute cũ có còn tồn tại không?
3. Các kiểu của attribute cũ có giữ nguyên không?
4. Readable/writable flags có còn tương thích không?
5. Operations/notifications cũ có còn phục vụ client cần thiết không?
6. Attribute mới có tên, kiểu và semantic rõ ràng không?
7. Giá trị mặc định hoặc chưa có dữ liệu được biểu diễn thế nào?
8. Getter mới có nhẹ, bounded và không side effect không?
9. Nếu writable, đã validate và giới hạn quyền chưa?
10. Client mới có xử lý server chưa hỗ trợ attribute không?
11. Deployment có rolling update/mixed versions không?
12. Rollback có làm client mới lỗi không?
13. Có integration test so sánh MBeanInfo baseline không?
14. Có kiểm tra trên đúng MBeanServer/target JVM không?
15. Có lệnh JConsole hoặc script xác minh trên staging không?
16. Có yêu cầu listener re-subscribe khi MBean bị replace không?
17. Có cập nhật tài liệu/dashboard theo attribute mới không?
18. Có cơ chế deprecation nếu định bỏ attribute cũ sau này không?

## 23. Bài tập thực hành

**Mục tiêu:** mở rộng một MBean queue từ v1 sang v2 mà một Java client v1 vẫn hoạt động.

### Phần A — tạo v1

1. Tạo Standard MBean hoặc Spring annotation MBean với `PendingCount` và `Enabled`.
2. Đăng ký ObjectName `com.example.orders:type=Queue,name=payments`.
3. Viết client v1 đọc `PendingCount` và `Enabled`.
4. Chụp baseline `MBeanInfo` trong integration test.

### Phần B — mở rộng v2

1. Thêm getter `getLastRefreshTime()` trả String ISO-8601.
2. Giữ nguyên ObjectName, hai attribute cũ và operation hiện hữu.
3. Khởi động phiên bản v2 trong MBeanServer test riêng.
4. Chạy lại client v1.
5. Đối chiếu metadata cũ và mới.
6. Xác nhận `LastRefreshTime` readable, không writable.

### Phần C — thử mixed versions

1. Chạy một target v1 và một target v2.
2. Viết client v2 kiểm tra `MBeanInfo` trước khi đọc `LastRefreshTime`.
3. Với v1, client dùng fallback thay vì coi là lỗi.
4. Với v2, client đọc giá trị thực.
5. Giả lập rollback server và quan sát client tiếp tục hoạt động.

### Phần D — phát hiện breaking change

1. Cố ý đổi `PendingCount` thành `PendingJobs`.
2. Chạy lại client v1 để thấy lỗi.
3. Khôi phục alias `PendingCount`.
4. Cập nhật contract test để bắt lỗi thay đổi tên trong những release sau.

## 24. Câu hỏi tự kiểm tra

**1. Vì sao thêm một attribute thường ít gây breaking hơn đổi tên attribute cũ?**

Vì client cũ có thể tiếp tục gọi tên cũ; đổi tên làm lookup không còn khớp.

**2. Thêm getter vào implementation Standard MBean có đủ không?**

Không nhất thiết. Standard MBean công bố hợp đồng theo MBean interface; cần thêm method vào interface tương ứng.

**3. `@ManagedAttribute` có tự đăng ký MBean không?**

Không. Spring exporter phải được cấu hình/kích hoạt và bean phải nằm trong context phù hợp.

**4. Có nên dùng `Instant` làm return type cho mọi JMX client không?**

Cần cân nhắc mapping/serialization. String ISO-8601 hoặc Open Types có thể tương thích hơn với client chung.

**5. Vì sao writable attribute mới cần security review?**

Vì nó mở ra một khả năng thay đổi trạng thái runtime, không chỉ quan sát.

**6. Client mới có thể đọc attribute mới trên server cũ không?**

Không, trừ khi server cũ đã có attribute tương ứng. Client nên kiểm tra capability hoặc thực hiện rollout theo thứ tự an toàn.

**7. `MBeanInfo` có đủ để chứng minh toàn bộ compatibility không?**

Không. Metadata chỉ kiểm tra cấu trúc; cần kiểm tra semantic, hiệu năng, bảo mật và hành vi runtime.

**8. Khi nào nên dùng ObjectName mới với version?**

Khi cần thay đổi không tương thích hoặc phải duy trì song song hai API quản trị.

## 25. Tổng kết

**Thêm attribute mới mà không phá client hiện có** đòi hỏi bảo toàn hợp đồng JMX cũ và chỉ mở rộng những khả năng cần thiết.

Cách tiếp cận an toàn:

- Giữ ObjectName và các attribute/operation đã có.
- Giữ type, quyền đọc/ghi và semantic của dữ liệu cũ.
- Thêm getter mới nhẹ, có mô tả rõ, ưu tiên read-only nếu chỉ dùng quan sát.
- Với Standard MBean, cập nhật interface quản trị; với Spring JMX, cập nhật metadata được exporter đọc.
- Test bằng `MBeanInfo` và client thật.
- Trong rolling update, client mới phải chấp nhận server chưa có attribute.
- Chuẩn bị rollback và tránh runtime replace không cần thiết.

Một thay đổi additive đúng nghĩa là **client cũ tiếp tục hoạt động mà không cần thay đổi**, trong khi client mới có thể sử dụng chức năng mở rộng theo cách có kiểm soát.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Java SE API — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
