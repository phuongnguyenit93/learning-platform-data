# Lấy MBeanInfo để biết giao diện đang được phơi bày

## 1. Mục tiêu

Trong Java Management Extensions (JMX), một MBean có thể cho phép bên ngoài JVM hoặc các công cụ quản trị bên trong JVM đọc thuộc tính, ghi thuộc tính, gọi thao tác, và nhận thông báo. Trước khi thực hiện các hành động đó, client cần biết **MBean thực sự phơi bày giao diện quản trị nào**.

\`MBeanServer.getMBeanInfo(ObjectName)\` là phương thức trung tâm để khám phá giao diện quản trị được MBean công bố tại thời điểm truy vấn. Kết quả là một đối tượng \`MBeanInfo\`, chứa các cấu trúc mô tả thuộc tính, thao tác, constructor, notification, cùng tên lớp và mô tả.

Bài học này giúp bạn:

- Lấy \`MBeanInfo\` của một MBean đã đăng ký trong \`MBeanServer\`.
- Phân biệt metadata mô tả với giá trị runtime của thuộc tính.
- Đọc quyền \`readable\`, \`writable\`, \`isIs\`, kiểu dữ liệu và chữ ký operation.
- Xem constructors, notifications và descriptors khi khả dụng.
- Xử lý trường hợp tên MBean chưa tồn tại, MBean thay đổi hoặc metadata không còn phù hợp với trạng thái hiện tại.
- Xác định giới hạn của \`MBeanInfo\` về quyền truy cập, an toàn và tính tương thích.

## 2. Mô hình tư duy: ObjectName → MBeanServer → MBeanInfo

\`\`\`text
JMX client
   |
   | 1. Tìm ObjectName của MBean
   v
MBeanServerConnection
   |
   | 2. getMBeanInfo(ObjectName)
   v
MBeanInfo
   |-- className
   |-- description
   |-- MBeanAttributeInfo[]
   |-- MBeanOperationInfo[]
   |-- MBeanConstructorInfo[]
   |-- MBeanNotificationInfo[]
   '-- Descriptor
   |
   | 3. Dựa vào metadata, lựa chọn lời gọi phù hợp
   v
getAttribute / setAttribute / invoke / addNotificationListener ...
\`\`\`

**\`ObjectName\` là địa chỉ định danh một MBean trong một \`MBeanServer\`.** Nó không phải đường dẫn HTTP, không phải tên Spring bean và không phải tên class Java. Ví dụ:

\`\`\`text
com.example.management:type=OrderQueue,name=Primary
\`\`\`

\`MBeanServer\` quản lý đăng ký và truy xuất các MBean trong JVM. Client từ xa thường làm việc với \`MBeanServerConnection\` lấy qua \`JMXConnector\`; cùng một nhóm phương thức như \`getMBeanInfo\` vẫn được dùng.

\`MBeanInfo\` là một *mô tả cấu trúc giao diện*, tức một dạng schema/runtime introspection. Nó trả lời “có thể truy cập những gì và với chữ ký nào?”, chứ không tự đọc giá trị hiện tại của tất cả thuộc tính.

## 3. Phân biệt metadata và dữ liệu thực tế

Giả sử một MBean hỗ trợ:

- Thuộc tính \`PendingCount\`: kiểu \`int\`, đọc được, không ghi được.
- Thuộc tính \`Paused\`: kiểu \`boolean\`, đọc và ghi được.
- Operation \`clearCompleted()\`: không có tham số, trả về \`void\`.
- Notification thông báo hàng đợi vượt ngưỡng.

Gọi \`getMBeanInfo\` có thể cho biết **tên và hợp đồng** của các phần tử này. Để lấy số đơn đang chờ thật sự, cần gọi riêng \`getAttribute(name, "PendingCount")\` hoặc API tương ứng.

| Câu hỏi | API phù hợp | Kết quả |
|---|---|---|
| MBean này công bố những thuộc tính nào? | \`getMBeanInfo\` | \`MBeanAttributeInfo[]\` |
| \`PendingCount\` có đọc được không? | \`MBeanAttributeInfo.isReadable()\` | Boolean mô tả giao diện |
| \`PendingCount\` hiện bằng bao nhiêu? | \`getAttribute\` | Giá trị runtime |
| MBean cho phép operation nào? | \`MBeanInfo.getOperations()\` | \`MBeanOperationInfo[]\` |
| Gọi operation cụ thể? | \`invoke\` | Kết quả thực thi hoặc exception |
| MBean đang được đăng ký không? | \`isRegistered\` | Boolean tại thời điểm gọi |

Một client quản trị thường dùng hai giai đoạn: **khám phá** bằng \`MBeanInfo\`, rồi **truy cập** bằng các API JMX khác. Metadata không phải cam kết rằng lời gọi tiếp theo luôn thành công: trạng thái, quyền và đăng ký có thể đổi ngay sau khi khám phá.

## 4. Ví dụ chuẩn: định nghĩa và đăng ký một Standard MBean

Để có dữ liệu cụ thể khi thực hành, trước tiên tạo một Standard MBean đơn giản. Standard MBean quy định interface quản trị theo quy ước \`<ClassName>MBean\`.

**OrderQueueMBean.java**

\`\`\`java
package com.example.jmx;

public interface OrderQueueMBean {
    int getPendingCount();

    boolean isPaused();

    void setPaused(boolean paused);

    void clearCompleted();
}
\`\`\`

**OrderQueue.java**

\`\`\`java
package com.example.jmx;

public class OrderQueue implements OrderQueueMBean {
    private volatile int pendingCount = 12;
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    @Override
    public void clearCompleted() {
        // Một ví dụ thao tác quản trị; triển khai thật sẽ xử lý dữ liệu.
        System.out.println("Clear completed orders requested");
    }
}
\`\`\`

**RegisterMBeanDemo.java**

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RegisterMBeanDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.management:type=OrderQueue,name=Primary"
        );

        server.registerMBean(new OrderQueue(), name);

        System.out.println("Registered: " + name);
        System.out.println("Registered? " + server.isRegistered(name));

        // Tại đây có thể truy vấn MBeanInfo ngay trong cùng JVM.
    }
}
\`\`\`

Ở ví dụ này, interface \`OrderQueueMBean\` quyết định phương thức nào được xuất ra làm thuộc tính hoặc operation. Việc class \`OrderQueue\` có thêm các phương thức public khác **không** khiến mọi phương thức đó tự được công bố qua Standard MBean.

Quy ước phân loại thường gặp:

- \`getPendingCount()\` trở thành attribute \`PendingCount\`, \`readable=true\`, \`writable=false\`.
- \`isPaused()\` và \`setPaused(boolean)\` trở thành attribute \`Paused\`, \`readable=true\`, \`writable=true\`.
- \`clearCompleted()\` trở thành operation \`clearCompleted\`.

Giá trị thực tế trong \`MBeanInfo\` phụ thuộc kiểu MBean và implementation/introspection cụ thể; ví dụ này minh họa Standard MBean theo quy ước thông thường.

## 5. Lấy MBeanInfo bằng MBeanServer

Sau khi đăng ký, truy vấn metadata:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("Class: " + info.getClassName());
System.out.println("Description: " + info.getDescription());
System.out.println("Attributes: " + info.getAttributes().length);
System.out.println("Operations: " + info.getOperations().length);
System.out.println("Constructors: " + info.getConstructors().length);
System.out.println("Notifications: " + info.getNotifications().length);
\`\`\`

**Điều kiện tiên quyết:** MBean phải được đăng ký dưới đúng \`ObjectName\` trong \`MBeanServer\` mà client đang sử dụng.

Trong môi trường chạy độc lập có thể lấy Platform MBeanServer:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
\`\`\`

Khi cần viết client chung dùng được với JMX remote, sử dụng \`MBeanServerConnection\`, vì \`MBeanServer\` kế thừa giao diện này:

\`\`\`java
import javax.management.MBeanServerConnection;

MBeanServerConnection connection = server;
MBeanInfo info = connection.getMBeanInfo(name);
\`\`\`

Không cần ép kiểu về \`MBeanServer\` để thực hiện \`getMBeanInfo\`. Đây là lợi ích quan trọng khi tách mã quản trị khỏi cách kết nối.

### 5.1. Đọc danh sách thuộc tính

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s | type=%s | readable=%s | writable=%s | isIs=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.isIs()
    );
}
\`\`\`

Ý nghĩa các trường:

- \`getName()\`: tên thuộc tính được công bố qua JMX (ví dụ \`PendingCount\`).
- \`getType()\`: tên kiểu Java dưới dạng chuỗi (ví dụ \`int\`, \`boolean\`, \`java.lang.String\`).
- \`isReadable()\`: hợp đồng cho biết thuộc tính có thể được đọc.
- \`isWritable()\`: hợp đồng cho biết thuộc tính có thể được ghi.
- \`isIs()\`: có sử dụng quy ước getter kiểu \`is...\` đối với thuộc tính boolean theo cách metadata thể hiện hay không.
- \`getDescription()\`: mô tả văn bản, có thể sơ sài hoặc để trống tùy MBean.

**Phân biệt \`isReadable()\` và quyền truy cập:** cờ này mô tả giao diện MBean, không có nghĩa mọi client đã được cấp phép để đọc. Ngoài ra, getter vẫn có thể ném exception hoặc gặp lỗi runtime.

### 5.2. Dùng metadata trước khi đọc giá trị

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public static Object readIfExposed(
        MBeanServerConnection connection,
        ObjectName objectName,
        String attributeName
) throws Exception {
    MBeanInfo info = connection.getMBeanInfo(objectName);

    for (MBeanAttributeInfo attribute : info.getAttributes()) {
        if (attribute.getName().equals(attributeName)) {
            if (!attribute.isReadable()) {
                throw new IllegalStateException(
                        "Attribute is not readable: " + attributeName
                );
            }

            return connection.getAttribute(objectName, attributeName);
        }
    }

    throw new IllegalArgumentException(
            "Attribute is not exposed: " + attributeName
    );
}
\`\`\`

Ở đây, \`getMBeanInfo\` giúp tránh gọi nhầm thuộc tính chưa được công bố. Nhưng giữa bước kiểm tra và bước \`getAttribute\`, MBean có thể bị unregister hoặc thay đổi giao diện; mã gọi thực tế vẫn phải xử lý exception.

## 6. Đọc operations và chữ ký tham số

\`MBeanInfo.getOperations()\` trả \`MBeanOperationInfo[]\`. Mỗi phần tử mô tả tên operation, kiểu trả về, mức tác động được khai báo, và danh sách tham số.

\`\`\`java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s -> %s (impact=%d)%n",
        operation.getName(),
        operation.getReturnType(),
        operation.getImpact()
    );

    for (MBeanParameterInfo parameter : operation.getSignature()) {
        System.out.printf(
            "  Parameter: %s : %s%n",
            parameter.getName(),
            parameter.getType()
        );
    }
}
\`\`\`

Các giá trị \`impact\` chuẩn của \`MBeanOperationInfo\` gồm:

| Hằng | Ý nghĩa gợi ý |
|---|---|
| \`INFO\` | Operation chủ yếu cung cấp thông tin |
| \`ACTION\` | Operation có thể thay đổi trạng thái |
| \`ACTION_INFO\` | Có cả yếu tố hành động và cung cấp thông tin |
| \`UNKNOWN\` | Mức tác động không được xác định rõ |

**Đây là phân loại metadata, không phải cơ chế kiểm soát an toàn.** Một operation tự khai báo \`INFO\` vẫn cần được xem xét cẩn thận trước khi gọi. \`getMBeanInfo\` không thay thế phân quyền hay xác nhận tác dụng phụ.

### 6.1. Vì sao chữ ký quan trọng?

Các JMX operation có thể overload cùng tên nhưng khác tham số. Khi invoke, client truyền đủ ba phần: tên operation, danh sách giá trị tham số và chữ ký các kiểu tham số.

\`\`\`java
Object result = connection.invoke(
        name,
        "clearCompleted",
        new Object[0],
        new String[0]
);
\`\`\`

Với operation ví dụ không tham số, hai mảng đều rỗng. Đối với operation có \`long\` hoặc \`java.lang.String\`, chữ ký phải dùng kiểu tương ứng với hợp đồng JMX. Không nên đoán chữ ký dựa vào tên phương thức.

Ví dụ MBean khác có \`resize(int capacity)\`:

\`\`\`java
connection.invoke(
        name,
        "resize",
        new Object[] { 100 },
        new String[] { "int" }
);
\`\`\`

Chỉ gọi ví dụ này nếu \`getMBeanInfo\` thật sự công bố \`resize\` với tham số \`int\` ở MBean được truy vấn; class \`OrderQueueMBean\` ở trên không công bố operation này.

## 7. Constructors, notifications và descriptors

Ngoài attributes và operations, \`MBeanInfo\` còn trả metadata về constructors và notifications.

### 7.1. Constructors

\`\`\`java
import javax.management.MBeanConstructorInfo;
import javax.management.MBeanParameterInfo;

for (MBeanConstructorInfo constructor : info.getConstructors()) {
    System.out.println("Constructor: " + constructor.getName());

    for (MBeanParameterInfo parameter : constructor.getSignature()) {
        System.out.printf(
            "  %s : %s%n",
            parameter.getName(),
            parameter.getType()
        );
    }
}
\`\`\`

Danh sách constructors có thể rỗng tùy cách MBean được export và loại MBean. Nó mô tả thông tin constructor trong JMX metadata, **không có nghĩa client có thể tự tạo thêm instance bằng cách gọi \`getMBeanInfo\`**. Việc tạo MBean (nếu được cho phép) là một hoạt động khác, qua API thích hợp của MBeanServer.

### 7.2. Notifications

\`\`\`java
import javax.management.MBeanNotificationInfo;

for (MBeanNotificationInfo notification : info.getNotifications()) {
    System.out.println("Description: " + notification.getDescription());

    for (String type : notification.getNotifTypes()) {
        System.out.println("  Notification type: " + type);
    }
}
\`\`\`

\`MBeanNotificationInfo\` cho biết các kiểu notification được quảng bá. Nó **không** chứa lịch sử notification và không đăng ký listener. Muốn nhận thông báo, client cần sử dụng \`addNotificationListener\` khi MBean hỗ trợ, kết nối và quyền cho phép. Không phải mọi MBean đều phát notification.

### 7.3. Descriptors

Đối tượng \`MBeanInfo\` và nhiều thành phần metadata của nó có thể mang \`Descriptor\`, một tập các trường \`name → value\` dùng để mô tả thông tin mở rộng. Metadata cụ thể thay đổi theo Standard MBean, MXBean, Dynamic MBean, framework exporter hoặc nhà cung cấp JMX.

\`\`\`java
import javax.management.Descriptor;

Descriptor descriptor = info.getDescriptor();

for (String fieldName : descriptor.getFieldNames()) {
    System.out.println(
            fieldName + " = " + descriptor.getFieldValue(fieldName)
    );
}
\`\`\`

Với metadata component cũng có thể kiểm tra descriptor:

\`\`\`java
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    Descriptor attributeDescriptor = attribute.getDescriptor();
    System.out.println(
            attribute.getName() + ": "
                    + java.util.Arrays.toString(
                            attributeDescriptor.getFieldNames()
                    )
    );
}
\`\`\`

Trong các biến thể MBean, descriptor có thể chứa thông tin như kiểu MXBean hoặc các thuộc tính bổ sung. Không nên ép client bắt buộc phải có một trường descriptor không thuộc hợp đồng đã kiểm chứng.

## 8. Chương trình hoàn chỉnh để khám phá giao diện MBean

Ví dụ Java dưới đây đăng ký \`OrderQueue\`, đọc và hiển thị metadata. Các file \`OrderQueueMBean\` và \`OrderQueue\` dùng mã ở mục 4.

**InspectMBeanInfo.java**

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.Descriptor;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanConstructorInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class InspectMBeanInfo {

    private InspectMBeanInfo() {
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.management:type=OrderQueue,name=Primary"
        );

        if (!server.isRegistered(name)) {
            server.registerMBean(new OrderQueue(), name);
        }

        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean: " + name);
        System.out.println("Implementation class: " + info.getClassName());
        System.out.println("Description: " + info.getDescription());

        System.out.println("\n=== ATTRIBUTES ===");
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                    "%s : %s [read=%s, write=%s, is=%s]%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable(),
                    attribute.isIs()
            );
        }

        System.out.println("\n=== OPERATIONS ===");
        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.print(
                    operation.getName() + "("
            );

            MBeanParameterInfo[] parameters = operation.getSignature();
            for (int i = 0; i < parameters.length; i++) {
                if (i > 0) {
                    System.out.print(", ");
                }
                System.out.print(
                        parameters[i].getType() + " "
                                + parameters[i].getName()
                );
            }

            System.out.println(") -> " + operation.getReturnType());
        }

        System.out.println("\n=== CONSTRUCTORS ===");
        for (MBeanConstructorInfo constructor : info.getConstructors()) {
            System.out.println(constructor.getName());
        }

        System.out.println("\n=== NOTIFICATIONS ===");
        for (MBeanNotificationInfo notification : info.getNotifications()) {
            System.out.println(notification.getDescription());
        }

        System.out.println("\n=== DESCRIPTOR FIELDS ===");
        Descriptor descriptor = info.getDescriptor();
        for (String fieldName : descriptor.getFieldNames()) {
            System.out.println(
                    fieldName + "=" + descriptor.getFieldValue(fieldName)
            );
        }

        System.out.println("\n=== RUNTIME READ ===");
        System.out.println(
                "PendingCount=" + server.getAttribute(name, "PendingCount")
        );
    }
}
\`\`\`

**Điều cần quan sát:** các dòng trong khối \`ATTRIBUTES\` và \`OPERATIONS\` xuất phát từ metadata. Dòng \`PendingCount=12\` cuối cùng được lấy bằng \`getAttribute\`, không phải trích từ \`MBeanInfo\`.

Bạn có thể biên dịch bằng JDK 21 trong thư mục nguồn theo package, sau đó chạy class \`com.example.jmx.InspectMBeanInfo\`. Không cần thêm thư viện bên ngoài: các API \`javax.management\` thuộc Java platform. Nếu ứng dụng đang sử dụng một runtime module system tùy chỉnh, đảm bảo module \`java.management\` được cung cấp.

## 9. Khám phá MBean không biết trước tên

Trong thực tế, client có thể không biết đầy đủ \`ObjectName\`. Dùng \`queryNames\` để liệt kê các MBean phù hợp trước khi gọi \`getMBeanInfo\`.

\`\`\`java
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

ObjectName pattern = new ObjectName(
        "com.example.management:type=OrderQueue,*"
);

Set<ObjectName> names = connection.queryNames(pattern, null);

for (ObjectName candidate : names) {
    System.out.println("Found: " + candidate);
    System.out.println(
            "Attributes: "
                    + connection.getMBeanInfo(candidate)
                            .getAttributes().length
    );
}
\`\`\`

\`ObjectName\` ở đây là **pattern**. Dấu \`*\` cho phép khớp các key properties còn lại theo quy tắc \`ObjectName\`. Nếu có nhiều MBean, xử lý từng tên riêng; không xem kết quả \`queryNames\` như một MBean duy nhất.

\`queryNames\` phục vụ discovery, nhưng hệ thống có thể thay đổi giữa lúc trả tập tên và lúc gọi \`getMBeanInfo\`. Hãy xử lý các trường hợp MBean bị unregister trong lúc duyệt.

### 9.1. Khi nào cần xem class name?

\`MBeanInfo.getClassName()\` trả tên class được mô tả trong metadata. Nó hữu ích để xác định loại đối tượng và hỗ trợ chẩn đoán, nhưng **không nên phụ thuộc hoàn toàn** vào tên class khi xây dựng client JMX. Standard MBean, Dynamic MBean, MXBean hoặc proxy/adapter có thể thay đổi cách class name được biểu diễn. Khi lập trình tương tác, hãy dựa vào metadata attribute/operation và hợp đồng giao diện cần dùng.

## 10. Spring Framework JMX: MBeanInfo giúp gì?

Trong ứng dụng Spring, một bean được export thành JMX MBean có thể thông qua \`MBeanExporter\` và annotation như \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
        objectName = "com.example.management:type=Cache,name=Main",
        description = "Cache management"
)
public class CacheMonitor {

    private volatile boolean enabled = true;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation
    public void clearCache() {
        // Logic xoá cache thật được triển khai ở đây.
    }
}
\`\`\`

Khi Spring JMX exporter được cấu hình và bean được export thành công, JMX client có thể gọi \`getMBeanInfo\` với \`ObjectName\` đã đăng ký để kiểm tra interface **thực sự được expose**, thay vì dự đoán chỉ dựa trên annotation.

Đặc biệt hữu ích khi:

- Annotation có trên class nhưng exporter chưa chạy hoặc không quét bean đó.
- Tên attribute thực tế khác với điều client mong đợi.
- Một method không xuất hiện như operation do quy tắc assembler/exposure.
- Giao diện đã thay đổi sau khi nâng cấp ứng dụng.
- Client cần tự động dựng trang đọc trạng thái dựa vào metadata.

Lưu ý: Annotation Spring không phải JMX registration độc lập. \`@Component\` tạo Spring bean, nhưng để thấy nó trong MBeanServer, application cần cấu hình JMX export thích hợp; một Spring bean bất kỳ không tự nhiên xuất hiện trong \`queryNames\`.

### 10.1. Kiểm tra interface mà Spring thực sự export

Giả sử muốn xác nhận bean \`CacheMonitor\` đã expose thuộc tính \`Enabled\` và operation \`clearCache\`:

\`\`\`java
ObjectName cacheName = new ObjectName(
        "com.example.management:type=Cache,name=Main"
);

MBeanInfo cacheInfo = connection.getMBeanInfo(cacheName);

boolean hasEnabled = false;

for (MBeanAttributeInfo attribute : cacheInfo.getAttributes()) {
    if ("Enabled".equals(attribute.getName())
            && attribute.isReadable()
            && attribute.isWritable()) {
        hasEnabled = true;
    }
}

boolean hasClearCache = false;

for (MBeanOperationInfo operation : cacheInfo.getOperations()) {
    if ("clearCache".equals(operation.getName())
            && operation.getSignature().length == 0) {
        hasClearCache = true;
    }
}

System.out.println("Enabled attribute exposed: " + hasEnabled);
System.out.println("clearCache operation exposed: " + hasClearCache);
\`\`\`

Đây là một cách xác minh hợp đồng runtime. Nếu kết quả không như mong đợi, kiểm tra cấu hình exporter, cách mapping annotation và \`ObjectName\` đang truy cập.

## 11. Remote JMX client: cùng API, khác đường kết nối

Một client chạy ngoài JVM ứng dụng thường dùng \`JMXConnectorFactory\` tạo kết nối JMX. Khi có connection, \`getMBeanInfo\` vẫn hoạt động qua \`MBeanServerConnection\`.

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteInspectDemo {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
                "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                    "com.example.management:type=OrderQueue,name=Primary"
            );

            MBeanInfo info = connection.getMBeanInfo(name);

            System.out.println("Class: " + info.getClassName());
            System.out.println(
                    "Exposed attributes: " + info.getAttributes().length
            );
        }
    }
}
\`\`\`

Địa chỉ \`localhost:9010\` chỉ mang tính minh họa; nó hoạt động khi server đã cấu hình JMX remote phù hợp, bao gồm registry/RMI endpoint và điều kiện kết nối cần thiết. Không mở JMX remote công khai chỉ để chạy ví dụ. Khi kết nối qua mạng thực, hãy sử dụng cấu hình bảo mật, xác thực và bảo vệ kênh tương ứng.

Remote JMX có thể thất bại vì endpoint không chạy, firewall/NAT, cấu hình RMI hostname, xác thực hoặc phân quyền; đó là lỗi đường kết nối, không phải bằng chứng MBeanInfo của một MBean bị thiếu.

## 12. Những ngoại lệ cần xử lý

\`getMBeanInfo\` khai báo các checked exception quan trọng qua \`MBeanServerConnection\`, như:

| Exception | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| \`InstanceNotFoundException\` | Không có MBean đăng ký dưới \`ObjectName\` đó ở thời điểm gọi | Kiểm tra tên, thời điểm đăng ký, và khả năng unregister |
| \`IntrospectionException\` | Không thể introspect MBean để tạo metadata | Kiểm tra kiểu MBean/exporter và exception gốc |
| \`ReflectionException\` | Lỗi reflection trong quá trình lấy thông tin MBean | Kiểm tra underlying exception và cách MBean triển khai |
| \`IOException\` | Lỗi giao tiếp qua \`MBeanServerConnection\`, đặc biệt remote | Kiểm tra kết nối, endpoint và mạng |
| \`SecurityException\` | Chính sách bảo mật từ chối thao tác | Cấp quyền phù hợp; không tự bỏ qua kiểm soát |

Ngoài ra, các API đọc/ghi/gọi operation có thể ném những ngoại lệ khác. Đừng dùng \`getMBeanInfo\` như chứng cứ rằng mọi operation đều gọi thành công.

Ví dụ xử lý các failure mode phổ biến:

\`\`\`java
import java.io.IOException;
import javax.management.InstanceNotFoundException;
import javax.management.IntrospectionException;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.ReflectionException;

public static MBeanInfo inspect(
        MBeanServerConnection connection,
        ObjectName name
) throws IOException {
    try {
        return connection.getMBeanInfo(name);
    } catch (InstanceNotFoundException e) {
        throw new IllegalStateException(
                "MBean no longer registered: " + name, e
        );
    } catch (IntrospectionException | ReflectionException e) {
        throw new IllegalStateException(
                "Cannot inspect management interface: " + name, e
        );
    }
}
\`\`\`

Ví dụ trên cho phép \`IOException\` được đẩy lên cho tầng quản lý kết nối; \`SecurityException\` cũng có thể lan truyền để tầng quản trị quyền xử lý. Trong ứng dụng thật, lỗi có thể được ánh xạ sang trạng thái chẩn đoán và log an toàn theo yêu cầu sản phẩm.

## 13. MBeanInfo có “đúng mãi” không?

Không nhất thiết. Có hai lý do:

1. **Dynamic MBean** có thể trả về metadata động; giao diện được công bố có thể thay đổi theo cấu hình hoặc trạng thái.
2. **Lifecycle đăng ký:** cùng \`ObjectName\` có thể bị unregister rồi đăng ký một MBean khác; thông tin lưu trong cache cũ có thể không còn phù hợp.

Vì vậy, client có thể cache \`MBeanInfo\` để giảm số lần gọi khi hợp đồng ổn định, nhưng cần cơ chế refresh khi kết nối lại, khi có thay đổi cấu hình, khi thao tác thất bại do tên/kiểu không khớp hoặc theo chính sách của ứng dụng.

### 13.1. Những gì MBeanInfo không đảm bảo

- Không khẳng định giá trị thuộc tính tại thời điểm gọi một operation tiếp theo.
- Không kiểm tra quyền của mọi người dùng chỉ vì metadata được phép đọc.
- Không đảm bảo operation là idempotent hoặc không gây tác dụng phụ.
- Không cung cấp toàn bộ trạng thái nội bộ của object ngoài những gì MBean công bố.
- Không tự liệt kê các Spring bean chưa được đăng ký làm MBean.
- Không phải tài liệu REST API hay nguồn dữ liệu metric lịch sử.
- Không hứa rằng tất cả descriptors hay descriptions đều có thông tin hữu ích.

## 14. Cách đọc kết quả với tư duy “giao diện quản trị”

Khi thấy một \`MBeanInfo\`, hãy phân tích theo thứ tự:

1. **Định danh:** \`ObjectName\` đang truy vấn có đúng MBean quan tâm không?
2. **Loại:** \`className\` và \`description\` nói gì về đối tượng?
3. **Attributes:** dữ liệu nào được xem/ghi, kiểu nào, cần xử lý runtime ra sao?
4. **Operations:** client được thiết kế để gọi hành động nào, yêu cầu tham số nào, hệ quả có thể là gì?
5. **Notifications:** MBean quảng bá các loại sự kiện nào, có cần đăng ký listener không?
6. **Descriptors:** có metadata mở rộng nào liên quan đến loại MBean hoặc tooling?
7. **Bảo mật và thời điểm:** kết nối có quyền thực hiện hay không, MBean còn được đăng ký hay không?

Nhờ đó, \`MBeanInfo\` trở thành một **bản hợp đồng kỹ thuật có thể khám phá lúc chạy**, đặc biệt hữu ích cho công cụ vận hành tự động hoặc khi không muốn hardcode mọi thuộc tính MBean.

## 15. Tự kiểm tra

**Câu 1.** \`getMBeanInfo\` có trả giá trị hiện tại của \`PendingCount\` không?  
**Đáp án:** Không. Nó trả thông tin mô tả attribute, còn giá trị lấy bằng \`getAttribute\`.

**Câu 2.** Tìm API nào để xem operation có những tham số gì?  
**Đáp án:** \`MBeanInfo.getOperations()\` → mỗi \`MBeanOperationInfo.getSignature()\` → các \`MBeanParameterInfo\`.

**Câu 3.** \`MBeanAttributeInfo.isWritable()\` trả true nghĩa là mọi người đều được ghi?  
**Đáp án:** Không. Đó là metadata về khả năng ghi, quyền truy cập thực tế còn do chính sách bảo mật và trạng thái MBean.

**Câu 4.** \`queryNames\` trả một \`ObjectName\`, nhưng sau đó \`getMBeanInfo\` ném \`InstanceNotFoundException\`. Có mâu thuẫn không?  
**Đáp án:** Không. MBean có thể bị unregister giữa hai lời gọi.

**Câu 5.** Khi export một Spring bean bằng JMX, vì sao cần kiểm tra \`MBeanInfo\` thực tế?  
**Đáp án:** Để biết danh sách attribute/operation mà exporter đã đăng ký và công bố, không suy đoán từ tên Spring bean hoặc annotation.

**Câu 6.** \`getNotifications()\` trả metadata notification. Làm sao nhận sự kiện?  
**Đáp án:** Đăng ký \`NotificationListener\` qua API JMX phù hợp khi MBean hỗ trợ và có quyền truy cập.

## 16. Tổng kết

- **\`MBeanServerConnection.getMBeanInfo(ObjectName)\`** là cửa vào để khám phá giao diện quản trị JMX thực sự được công bố.
- **\`MBeanInfo\` chứa metadata:** class name, mô tả, attributes, operations, constructors, notifications và descriptor.
- **\`MBeanAttributeInfo\`** cho biết tên, kiểu và khả năng đọc/ghi; **\`MBeanOperationInfo\`** cho biết tên, kiểu trả về, chữ ký tham số và mức tác động được khai báo.
- **Đọc metadata khác với đọc giá trị hoặc thực thi thao tác.** Dùng \`getAttribute\`, \`setAttribute\`, \`invoke\` hoặc notification listener khi cần tương tác.
- Metadata có thể thay đổi, quyền truy cập có thể hạn chế, và MBean có thể biến mất giữa hai lời gọi. Client cần xử lý những điều này khi vận hành.

### Tài liệu tham khảo

- Java SE API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE API — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE API — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE API — MBeanOperationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Oracle JMX Tutorial: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
