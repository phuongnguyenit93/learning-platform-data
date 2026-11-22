# Attribute, operation, constructor và notification trong MBeanInfo

## Mục tiêu

Sau bài học này, bạn có thể đọc `MBeanInfo` để biết một MBean công bố thuộc tính, phương thức quản trị, constructor và notification nào; hiểu metadata khác với việc gọi thao tác thực tế; dùng `MBeanServer` để khám phá và tương tác với MBean theo đúng hợp đồng JMX.

## 1. MBeanInfo là gì?

Java Management Extensions (JMX) cho phép ứng dụng Java công bố thông tin giám sát và thao tác quản trị thông qua các **managed bean** (MBean). `MBeanInfo` nằm trong `javax.management`, mô tả giao diện quản trị mà một MBean trình bày cho công cụ JMX.

Một đối tượng `MBeanInfo` có tên lớp, mô tả và bốn nhóm metadata:

| Phương thức trên MBeanInfo | Kiểu phần tử | Thể hiện |
| --- | --- | --- |
| `getAttributes()` | `MBeanAttributeInfo[]` | Thuộc tính có thể đọc/ghi |
| `getOperations()` | `MBeanOperationInfo[]` | Phương thức quản trị có thể gọi |
| `getConstructors()` | `MBeanConstructorInfo[]` | Chữ ký constructor được mô tả |
| `getNotifications()` | `MBeanNotificationInfo[]` | Loại notification có thể phát ra |

Các mảng có thể rỗng. Metadata dùng để **khám phá khả năng**; nó không tự chứa giá trị hiện tại của attribute, không thực thi operation và không phải lịch sử notification.

`MBeanInfo` còn cung cấp `getClassName()`, `getDescription()` và `getDescriptor()`. Descriptor bổ sung metadata mở rộng, đặc biệt trong Model MBean, MXBean hoặc các công cụ quản trị chuyên dụng. Dữ liệu do MBean tự công bố có thể thay đổi với Dynamic MBean; vì vậy công cụ khám phá nên lấy lại `MBeanInfo` khi cần cập nhật.

## 2. Attribute: dữ liệu quản trị có thể đọc hoặc ghi

`MBeanAttributeInfo` mô tả **tên**, **kiểu Java**, mô tả và quyền truy cập:

- `getName()`: tên attribute, ví dụ `ActiveConnections`.
- `getType()`: tên kiểu, ví dụ `int` hoặc `java.lang.String`.
- `isReadable()`: có cho phép lấy giá trị bằng `MBeanServer.getAttribute` không.
- `isWritable()`: có cho phép đặt giá trị bằng `MBeanServer.setAttribute` không.
- `isIs()`: cho biết kiểu getter dạng `isXxx()` dành cho boolean.

Ví dụ interface Standard MBean:

```java
public interface CacheMonitorMBean {
    int getEntryCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void clear();
}
```

Với tên MBean `CacheMonitor`, JMX thường công bố hai attribute `EntryCount` (chỉ đọc) và `Enabled` (đọc/ghi), cùng operation `clear`. Getter/setter phù hợp quy ước của Standard MBean trở thành attribute; không nên mặc định mọi method Java đều là operation.

**Đọc metadata khác với đọc giá trị:**

```java
MBeanInfo info = server.getMBeanInfo(objectName);
for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf("%s: %s, read=%s, write=%s%n",
            a.getName(), a.getType(), a.isReadable(), a.isWritable());
}

Object count = server.getAttribute(objectName, "EntryCount");
server.setAttribute(objectName, new Attribute("Enabled", false));
```

`getAttribute`/ `setAttribute` gọi vào MBean thực tế, có thể ném `AttributeNotFoundException`, `InvalidAttributeValueException`, `MBeanException`, `ReflectionException` hoặc lỗi khác tùy thao tác. Chỉ gọi `setAttribute` khi attribute cho phép ghi và giá trị có kiểu phù hợp. Không nhầm `isIs()` với `isReadable()`: `isIs()` phản ánh mẫu getter boolean, không thay thế cờ quyền đọc.

## 3. Operation: hành động quản trị có thể gọi

`MBeanOperationInfo` mô tả:

- `getName()`: tên operation.
- `getReturnType()`: kiểu trả về.
- `getSignature()`: các `MBeanParameterInfo` chứa tên, kiểu và mô tả từng tham số.
- `getImpact()`: ý định tác động, một trong `INFO`, `ACTION`, `ACTION_INFO`, `UNKNOWN`.

`impact` chỉ là phân loại mang tính mô tả, **không phải cơ chế phân quyền hoặc cam kết operation không gây tác dụng phụ**. Cần đọc tài liệu và kiểm soát quyền trước khi gọi thao tác thay đổi trạng thái.

Ví dụ:

```java
for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName() + " -> " + op.getReturnType());
    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.println("  " + p.getName() + ": " + p.getType());
    }
}
server.invoke(objectName, "clear", new Object[0], new String[0]);
```

Khi operation có tham số, truyền mảng giá trị và **mảng tên kiểu tương ứng, cùng thứ tự**:

```java
server.invoke(objectName, "resize",
        new Object[] { 256 },
        new String[] { "int" });
```

Tên kiểu trong signature cần khớp chữ ký được JMX công bố (ví dụ `int` khác `java.lang.Integer`). Với overload, signature giúp chọn đúng operation. `invoke` có thể ném `ReflectionException`, `MBeanException`, `InstanceNotFoundException` và lỗi khác. Các operation không tự động được gọi chỉ vì xuất hiện trong metadata.

## 4. Constructor: metadata về cách khởi tạo

`MBeanConstructorInfo` chứa `getName()`, `getDescription()`, `getSignature()` và `getDescriptor()`. `MBeanParameterInfo[]` trong signature cho biết tên/kiểu tham số constructor.

```java
for (MBeanConstructorInfo ctor : info.getConstructors()) {
    System.out.println("Constructor: " + ctor.getName());
    for (MBeanParameterInfo p : ctor.getSignature()) {
        System.out.println("  " + p.getType() + " " + p.getName());
    }
}
```

Constructor **khác operation**: constructor mô tả cách tạo instance, không phải method quản trị gọi bằng `invoke`. Một số `MBeanServer` hỗ trợ tạo và đăng ký MBean qua `createMBean` nếu lớp và quyền truy cập cho phép; nhiều ứng dụng Spring đăng ký sẵn bean thay vì để client tạo instance.

Không suy ra rằng danh sách constructor đầy đủ như Java Reflection: metadata mô tả hợp đồng quản trị được công bố; việc có constructor trong `MBeanInfo` không đảm bảo client từ xa có thể khởi tạo thành công. Cách khởi tạo còn phụ thuộc classloader, lớp được cung cấp, môi trường và chính sách truy cập.

## 5. Notification: sự kiện bất đồng bộ do MBean phát ra

`MBeanNotificationInfo` mô tả loại thông báo MBean có thể phát:

- `getNotifTypes()`: danh sách chuỗi loại notification, ví dụ `com.example.cache.cleared`.
- `getName()`: tên lớp notification (thường `javax.management.Notification` hoặc lớp con).
- `getDescription()`: mô tả về các notification.

```java
for (MBeanNotificationInfo n : info.getNotifications()) {
    System.out.println(n.getName() + ": "
            + java.util.Arrays.toString(n.getNotifTypes()));
}
```

MBean có thể phát notification nếu hỗ trợ `NotificationBroadcaster` / `NotificationEmitter`. Để thực sự nhận sự kiện, client đăng ký `NotificationListener` qua `MBeanServer.addNotificationListener` hoặc kết nối JMX thích hợp:

```java
NotificationListener listener = (notification, handback) ->
        System.out.println(notification.getType() + ": "
                + notification.getMessage());

server.addNotificationListener(objectName, listener, null, null);
try {
    // Thực hiện thao tác và xử lý sự kiện trong vòng đời listener.
} finally {
    server.removeNotificationListener(objectName, listener);
}
```

Notification có `type`, `source`, `sequenceNumber`, `timeStamp`, `message` và có thể có `userData`. Metadata notification là danh sách **khả năng phát sự kiện**, không phải hàng đợi hay bản ghi các sự kiện đã xảy ra. Một MBean không phát notification khi client đăng ký listener thì sẽ không có sự kiện để nhận. Công cụ giám sát cần xử lý vòng đời listener, tình huống mất kết nối và giới hạn thông tin nhạy cảm trong `userData`.

## 6. Ví dụ Java hoàn chỉnh: đăng ký MBean và khám phá MBeanInfo

Ví dụ sau có thể lưu dưới tên `JmxInfoDemo.java` và chạy với JDK 17+ (JMX thuộc JDK, không cần thư viện ngoài). Đặt interface `CacheMonitorMBean` và class `CacheMonitor` là các kiểu public lồng nhau để Standard MBean nhận diện hợp đồng.

```java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.*;

public class JmxInfoDemo {
    public interface CacheMonitorMBean {
        int getEntryCount();
        boolean isEnabled();
        void setEnabled(boolean value);
        void clear();
    }

    public static class CacheMonitor
            extends NotificationBroadcasterSupport
            implements CacheMonitorMBean {
        private boolean enabled = true;
        private int entryCount = 3;
        private long sequence;

        @Override public int getEntryCount() { return entryCount; }
        @Override public boolean isEnabled() { return enabled; }
        @Override public void setEnabled(boolean value) { enabled = value; }

        @Override public void clear() {
            entryCount = 0;
            sendNotification(new Notification(
                "com.example.cache.cleared", this, ++sequence,
                System.currentTimeMillis(), "Cache cleared"));
        }

        @Override public MBeanNotificationInfo[] getNotificationInfo() {
            return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                    new String[] { "com.example.cache.cleared" },
                    Notification.class.getName(),
                    "Fired when cache is cleared")
            };
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName("com.example:type=CacheMonitor");
        server.registerMBean(new CacheMonitor(), name);

        try {
            MBeanInfo info = server.getMBeanInfo(name);
            System.out.println("MBean class: " + info.getClassName());

            for (MBeanAttributeInfo a : info.getAttributes()) {
                System.out.printf("Attribute %s [%s] R=%s W=%s%n",
                    a.getName(), a.getType(),
                    a.isReadable(), a.isWritable());
            }
            for (MBeanOperationInfo op : info.getOperations()) {
                System.out.printf("Operation %s -> %s%n",
                    op.getName(), op.getReturnType());
            }
            for (MBeanConstructorInfo c : info.getConstructors()) {
                System.out.println("Constructor " + c.getName());
            }
            for (MBeanNotificationInfo n : info.getNotifications()) {
                System.out.println("Notifications "
                    + Arrays.toString(n.getNotifTypes()));
            }

            NotificationListener listener = (n, handback) ->
                System.out.println("Received: " + n.getType());
            server.addNotificationListener(name, listener, null, null);
            try {
                System.out.println("Count before: "
                    + server.getAttribute(name, "EntryCount"));
                server.setAttribute(name, new Attribute("Enabled", false));
                server.invoke(name, "clear", new Object[0], new String[0]);
                System.out.println("Count after: "
                    + server.getAttribute(name, "EntryCount"));
            } finally {
                server.removeNotificationListener(name, listener);
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

Chạy:

```bash
javac JmxInfoDemo.java
java JmxInfoDemo
```

Kết quả minh họa gồm hai attribute, operation `clear`, một notification type và log `Received: com.example.cache.cleared`. Constructor được liệt kê tùy cách MBean cung cấp metadata; không phụ thuộc vào số constructor Reflection có thể thấy.

Trong ứng dụng Spring, các MBean được xuất qua cơ chế JMX của Spring hoặc tự đăng ký với `MBeanServer` vẫn có thể được quan sát bằng cùng các API trên. Các annotation như `@ManagedResource`, `@ManagedAttribute` và `@ManagedOperation` giúp Spring xác định metadata cần xuất khi sử dụng Spring JMX exporter; đó là một tầng cấu hình khác với API khám phá `MBeanInfo` thuần JMX.

## 7. Phân biệt và áp dụng

| Câu hỏi của công cụ quản trị | Thành phần metadata | Lệnh runtime liên quan |
| --- | --- | --- |
| Có thể xem/chỉnh cấu hình nào? | `MBeanAttributeInfo` | `getAttribute`, `setAttribute` |
| Có thể yêu cầu MBean thực hiện gì? | `MBeanOperationInfo` | `invoke` |
| MBean công bố cách khởi tạo nào? | `MBeanConstructorInfo` | `createMBean` khi được hỗ trợ |
| Có thể đăng ký nhận sự kiện nào? | `MBeanNotificationInfo` | `addNotificationListener` |

Lưu ý thực tế:

1. Luôn lấy metadata của đúng `ObjectName` đang đăng ký; không dùng tên lớp để thay thế tên đối tượng.
2. Giao diện do `MBeanInfo` công bố có thể khác public API của Java class, đặc biệt với Standard MBean, MXBean và Dynamic MBean.
3. `MBeanInfo` không thay thế quản lý quyền, xác thực, TLS hay giới hạn truy cập của JMX từ xa. Chỉ bật remote JMX trong môi trường đã cấu hình bảo mật.
4. Với dynamic metadata, công cụ quản trị nên xử lý tình huống thông tin thay đổi giữa lúc đọc metadata và lúc thực hiện action.

## 8. Tự kiểm tra

1. Vì sao `MBeanInfo.getAttributes()` không trả về giá trị hiện tại của attribute?
2. `isReadable()`, `isWritable()` và `isIs()` mô tả ba khía cạnh nào?
3. Khi gọi operation overload qua `MBeanServer.invoke`, vì sao cần truyền signature?
4. `MBeanConstructorInfo` có đồng nghĩa một client luôn tạo được MBean từ xa không?
5. Vì sao `MBeanNotificationInfo` có notification type nhưng listener vẫn có thể không nhận được sự kiện?

**Ghi nhớ:** `MBeanInfo` là bản mô tả hợp đồng quản trị JMX; attribute biểu thị trạng thái, operation biểu thị hành động, constructor mô tả cách khởi tạo và notification biểu thị khả năng phát sự kiện.