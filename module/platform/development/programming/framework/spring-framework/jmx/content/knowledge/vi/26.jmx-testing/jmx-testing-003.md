# Đọc MBeanInfo và xác nhận attribute mong đợi trong kiểm thử Spring Framework JMX

## 1. Bối cảnh và mục tiêu

Trong Spring Framework JMX, một bean Java có thể được export thành MBean để công bố các **attribute**, **operation** và **notification**. Nhưng việc Spring `ApplicationContext` khởi động thành công chưa đủ chứng minh giao diện JMX đúng như yêu cầu. Một cấu hình export có thể đăng ký nhầm ObjectName, sử dụng assembler khác dự kiến hoặc bỏ sót một getter được đánh dấu `@ManagedAttribute`. Vì vậy kiểm thử cần **đọc `MBeanInfo` thực tế từ `MBeanServer` và xác nhận attribute mong đợi**.

Đây là kiểm thử **hợp đồng quản trị JMX**: thay vì chỉ kiểm tra annotation tồn tại trong source code, ta kiểm tra đối tượng đã được Spring export thực sự công bố giao diện gì cho client quản trị.

Sau bài học, bạn có thể:

- Giải thích `MBeanInfo` và `MBeanAttributeInfo` dùng để mô tả những gì.
- Đăng ký/export một managed bean trong Spring test với server được chọn tường minh.
- Lấy `MBeanInfo` từ `MBeanServer.getMBeanInfo(ObjectName)`.
- Xác nhận tên, kiểu Java, quyền đọc/ghi và mô tả của attribute.
- Phân biệt metadata test với việc gọi `getAttribute()` để kiểm tra giá trị runtime.
- Tạo test chống hồi quy khi đổi annotation, naming strategy hoặc metadata assembler.
- Tránh lỗi khi nhiều test/JVM context dùng chung platform MBeanServer.
- Thiết kế assertion ổn định, không phụ thuộc thứ tự phần tử hoặc thông tin không được hợp đồng bảo đảm.

## 2. Vì sao không chỉ kiểm tra annotation?

Xét bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=QueueMonitor,name=Primary",
    description = "Queue runtime monitoring"
)
public class QueueMonitor {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Whether queue polling is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Change queue polling state")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedAttribute(description = "Current number of queued tasks")
    public int getQueuedTasks() {
        return 4;
    }
}
```

Đọc source code cho thấy ý định công bố hai attribute:

- `Enabled`: `boolean`, đọc và ghi.
- `QueuedTasks`: `int`, chỉ đọc.

Nhưng JMX client không gọi source code. Nó kết nối `MBeanServer` và tra cứu `ObjectName`, sau đó sử dụng những attribute được MBean **thực sự công bố**. Nếu thiếu `MBeanExporter`, metadata assembler không đọc annotation, ObjectName khác hoặc một registration policy giữ MBean cũ, kết quả runtime có thể khác ý định trên.

Do đó kiểm thử nên quan sát:

```text
Spring bean
  |
  v
MBeanExporter + metadata
  |
  v
MBeanServer registry
  |
  +-- getMBeanInfo(ObjectName)
        |
        +-- getAttributes()
              |
              +-- MBeanAttributeInfo
                    name/type/readable/writable/description
```

Điểm mấu chốt là kiểm tra **hợp đồng công bố tại điểm truy cập của client**, không chỉ đánh giá cấu trúc Java ở phía producer.

## 3. MBeanInfo và MBeanAttributeInfo

JMX cung cấp các lớp chuẩn trong package `javax.management`:

| Lớp/API | Vai trò |
| --- | --- |
| `MBeanServer` | Quản lý MBean đã đăng ký và thực hiện các lời gọi quản trị |
| `ObjectName` | Định danh MBean trong server |
| `MBeanInfo` | Mô tả giao diện quản trị của một MBean |
| `MBeanAttributeInfo` | Mô tả một attribute được công bố |
| `MBeanOperationInfo` | Mô tả một operation |
| `MBeanNotificationInfo` | Mô tả loại notification |
| `MBeanConstructorInfo` | Mô tả constructor trong metadata |
| `Descriptor` | Metadata mở rộng ở dạng field/value |

Để lấy danh sách thuộc tính:

```java
MBeanInfo info = server.getMBeanInfo(name);
MBeanAttributeInfo[] attributes = info.getAttributes();
```

Với từng attribute, các trường hữu ích nhất cho test là:

```java
attribute.getName();
attribute.getType();
attribute.isReadable();
attribute.isWritable();
attribute.isIs();
attribute.getDescription();
attribute.getDescriptor();
```

Trong đó:

- `getName()`: tên mà client dùng khi gọi `getAttribute` hoặc `setAttribute`.
- `getType()`: tên kiểu của attribute, ví dụ `int`, `boolean`, `java.lang.String`.
- `isReadable()`: có getter được công bố.
- `isWritable()`: có setter được công bố.
- `isIs()`: thuộc tính getter dạng `isX()` của boolean.
- `getDescription()`: mô tả cho công cụ và người vận hành.
- `getDescriptor()`: thông tin mở rộng nếu MBean/assembler có công bố.

Không nên coi mô tả là định danh. `description` là văn bản dành cho con người; `name` mới là khóa attribute trong giao diện JMX.

## 4. Đọc MBeanInfo qua Java JMX API

Ví dụ đọc metadata của một MBean đã được đăng ký:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=QueueMonitor,name=Primary"
);

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "name=%s, type=%s, readable=%s, writable=%s, description=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.getDescription()
    );
}
```

Mẫu output có thể là:

```text
name=Enabled, type=boolean, readable=true, writable=true, description=Whether queue polling is enabled
name=QueuedTasks, type=int, readable=true, writable=false, description=Current number of queued tasks
```

Mô tả cụ thể phụ thuộc metadata assembler và cách annotation được diễn giải. Test nên xác nhận những phần là **hợp đồng của ứng dụng**, thay vì so sánh toàn bộ output text gồm các chi tiết framework không cần thiết.

Nếu exporter dùng `MBeanServer` riêng thì đoạn code phải lấy đúng server đó. Kiểm tra trên platform server khi exporter đăng ký vào server khác có thể dẫn tới `InstanceNotFoundException` dù resource được export chính xác.

## 5. Tạo đối tượng mẫu để kiểm thử

Bean ví dụ:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=QueueMonitor,name=Primary",
    description = "Queue monitoring MBean"
)
public class QueueMonitor {

    private final AtomicInteger queuedTasks = new AtomicInteger(4);
    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Whether queue polling is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Whether queue polling is enabled")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedAttribute(description = "Number of waiting tasks")
    public int getQueuedTasks() {
        return queuedTasks.get();
    }

    // Method nội bộ không dự định công bố qua JMX:
    public void internalRebuild() {
        queuedTasks.set(0);
    }
}
```

Bean có hai attribute được công bố qua metadata. `internalRebuild()` không có `@ManagedOperation`, vì vậy khi dùng assembler dựa trên annotation, operation nội bộ đó không thuộc hợp đồng JMX được dự kiến.

Hãy giữ getter và setter của cùng attribute nhất quán về ý nghĩa và description. Nếu một getter nói “seconds” nhưng setter nói “milliseconds”, metadata có thể gây nhầm lẫn cho operator.

## 6. Cấu hình Spring JMX trong môi trường test

Để kiểm tra độc lập, có thể tạo `MBeanServer` riêng cho test. Việc này giảm nguy cơ trùng ObjectName với test khác dùng platform server.

```java
package com.example.monitoring;

import java.util.Map;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration
public class JmxTestConfiguration {

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer(
            "com.example.test"
        );
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MBeanExporter mBeanExporter(
            QueueMonitor monitor,
            MBeanServer testMBeanServer,
            MetadataMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.monitoring:type=QueueMonitor,name=Primary",
            monitor
        ));
        return exporter;
    }
}
```

Cấu hình trên làm rõ ba điểm:

1. Bean `QueueMonitor` có mặt trong Spring context.
2. `MBeanExporter` được trỏ tới **server riêng của test**.
3. `MetadataMBeanInfoAssembler` sử dụng `AnnotationJmxAttributeSource` để xây dựng metadata từ annotation Spring.

Không cần mở JMX Remote cho test này. JUnit có thể tương tác trực tiếp qua `MBeanServer` local.

Trong môi trường thật, có thể dùng `@EnableMBeanExport` hoặc cơ chế tự cấu hình tương ứng. Nhưng đối với test hợp đồng, việc tường minh hóa server và assembler giúp giảm mơ hồ về nguyên nhân thất bại.

## 7. Test với JUnit 5: xác nhận attribute mong đợi

Một cách đơn giản là dùng `AnnotationConfigApplicationContext` để dựng Spring context rồi kiểm tra JMX registry.

```java
package com.example.monitoring;

import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class QueueMonitorJmxTest {

    @Test
    void exposesExpectedAttributes() throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     JmxTestConfiguration.class
                 )) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "com.example.monitoring:type=QueueMonitor,name=Primary"
            );

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            Map<String, MBeanAttributeInfo> attributes =
                Arrays.stream(info.getAttributes())
                    .collect(Collectors.toMap(
                        MBeanAttributeInfo::getName,
                        Function.identity()
                    ));

            assertTrue(
                attributes.containsKey("Enabled"),
                "Enabled should be exposed"
            );
            assertTrue(
                attributes.containsKey("QueuedTasks"),
                "QueuedTasks should be exposed"
            );

            MBeanAttributeInfo enabled = attributes.get("Enabled");
            assertEquals("boolean", enabled.getType());
            assertTrue(enabled.isReadable());
            assertTrue(enabled.isWritable());

            MBeanAttributeInfo queued =
                attributes.get("QueuedTasks");
            assertEquals("int", queued.getType());
            assertTrue(queued.isReadable());
            assertFalse(queued.isWritable());
        }
    }
}
```

Test này xác nhận **registration + metadata contract**. Nó không cần suy đoán thứ tự `info.getAttributes()` vì chuyển danh sách thành `Map` theo tên. Nếu test thất bại, thông báo assertion chỉ rõ attribute nào không xuất hiện hoặc quyền/kiểu nào bị sai.

Một số dự án có thêm attribute do MBean framework công bố. Khi yêu cầu chỉ là “phải có `Enabled` và `QueuedTasks`”, nên dùng `containsKey` thay vì bắt danh sách attribute chỉ có đúng hai phần tử. Nếu hợp đồng thật sự cấm mọi attribute khác, có thể bổ sung assertion trên tập tên.

## 8. Viết helper assertion tái sử dụng

Khi nhiều MBean cần kiểm tra, lặp lại `Arrays.stream(...)` trong mỗi test sẽ khó bảo trì. Có thể viết helper:

```java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

import static org.junit.jupiter.api.Assertions.*;

final class JmxAssertions {

    private JmxAssertions() {}

    static MBeanAttributeInfo requireAttribute(
            MBeanInfo info, String expectedName) {

        return Arrays.stream(info.getAttributes())
            .filter(attr -> expectedName.equals(attr.getName()))
            .findFirst()
            .orElseThrow(() ->
                new AssertionError(
                    "Missing JMX attribute: " + expectedName
                ));
    }

    static void assertReadOnly(
            MBeanInfo info, String name, String type) {

        MBeanAttributeInfo attr = requireAttribute(info, name);

        assertEquals(type, attr.getType());
        assertTrue(attr.isReadable());
        assertFalse(attr.isWritable());
    }

    static void assertReadWrite(
            MBeanInfo info, String name, String type) {

        MBeanAttributeInfo attr = requireAttribute(info, name);

        assertEquals(type, attr.getType());
        assertTrue(attr.isReadable());
        assertTrue(attr.isWritable());
    }
}
```

Dùng:

```java
MBeanInfo info = server.getMBeanInfo(name);

JmxAssertions.assertReadWrite(info, "Enabled", "boolean");
JmxAssertions.assertReadOnly(info, "QueuedTasks", "int");
```

Các helper này thể hiện chính xác hợp đồng cần xác nhận. Nếu có nhiều kiểu getter hoặc writable-only attribute, có thể mở rộng helper theo boolean flags hoặc cấu trúc expected metadata.

## 9. Xác nhận description khi đây là một phần hợp đồng

Nếu metadata description là nội dung quan trọng với console quản trị, có thể kiểm tra:

```java
MBeanAttributeInfo queued =
    JmxAssertions.requireAttribute(info, "QueuedTasks");

assertEquals(
    "Number of waiting tasks",
    queued.getDescription()
);
```

Nhưng không nên biến mọi thay đổi câu chữ không ảnh hưởng vận hành thành lỗi test nếu description chỉ là tài liệu phụ. Lựa chọn assertion tùy hợp đồng:

- Nếu công cụ vận hành hiển thị description và tài liệu yêu cầu wording cố định: kiểm tra chính xác.
- Nếu description chỉ giúp người đọc: có thể kiểm tra `notBlank` hoặc không kiểm tra exact text.
- Nếu metadata được bản địa hóa: cần thiết kế test theo locale hoặc kỳ vọng metadata của một môi trường cụ thể.

Description không phải tên attribute; nếu cần truy cập, client vẫn dùng `QueuedTasks` khi gọi `getAttribute`.

## 10. Kiểm tra `getAttribute()` sau khi xác nhận metadata

`MBeanInfo` cho biết thuộc tính **được công bố**. Nhưng để biết getter thật có thể chạy hay không, cần gọi `getAttribute`.

```java
Object enabled = server.getAttribute(name, "Enabled");
Object queuedTasks = server.getAttribute(name, "QueuedTasks");

assertEquals(Boolean.TRUE, enabled);
assertEquals(Integer.valueOf(4), queuedTasks);
```

Đây là lớp test bổ sung cho metadata, không thay thế nó. Có những trường hợp metadata đánh dấu readable=true nhưng getter thực tế lỗi vì dependency không sẵn sàng, trạng thái chưa khởi tạo hoặc exception từ logic bean.

Đối với writable attribute, có thể thử `setAttribute` rồi đọc lại:

```java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE)
);

assertEquals(
    Boolean.FALSE,
    server.getAttribute(name, "Enabled")
);
```

Test nên dọn hoặc reset trạng thái để không ảnh hưởng test khác nếu dùng bean/server chung.

### 10.1. Test metadata và test hành vi có phạm vi khác nhau

| Kiểm thử | Câu hỏi trả lời |
| --- | --- |
| `server.isRegistered(name)` | MBean đã đăng ký đúng ObjectName chưa? |
| `getMBeanInfo(name)` | Interface quản trị đang công bố gì? |
| `MBeanAttributeInfo.isReadable()` | Metadata cho phép đọc không? |
| `MBeanAttributeInfo.isWritable()` | Metadata cho phép ghi không? |
| `getAttribute(...)` | Getter trả dữ liệu có đúng không? |
| `setAttribute(...)` | Setter xử lý giá trị có đúng không? |
| `getOperations()` | Operation nào được export? |
| `getNotifications()` | MBean công bố loại notification nào? |

Nên dùng từng loại test cho một hợp đồng rõ ràng. Ví dụ một bài kiểm thử metadata không cần cố ý gọi operation thay đổi cache production để chứng minh `MBeanInfo` có operation đó.

## 11. Test chính xác kiểu dữ liệu và quyền đọc/ghi

Tên kiểu JMX phản ánh kiểu Java của attribute:

```text
boolean
int
long
double
java.lang.String
```

Ví dụ:

```java
@ManagedAttribute
public long getProcessedJobs() {
    return 100L;
}
```

Metadata dự kiến thường là:

```text
name = ProcessedJobs
type = long
readable = true
writable = false
```

Một lỗi có thể xảy ra khi refactor getter từ `int` sang `long`. Nếu client hoặc monitoring rule dựa vào kiểu cũ, test metadata sẽ phát hiện thay đổi contract.

Với boolean, JMX metadata có thể đánh dấu `isIs()` khi getter dạng `isEnabled()`. Hãy chỉ assert flag này nếu đó là điều kiện contract thực sự cần thiết và assembler đang dùng có semantics ổn định theo phiên bản.

### 11.1. Không giả định setter là method business bình thường

Nếu `Enabled` writable, client có thể thay đổi runtime qua JMX. Test cần xác nhận authorization và logic setter ở mức phù hợp, không chỉ xem `writable=true` là một bảo đảm về an toàn. Với operation/attribute có side effect, luôn dùng test environment và dữ liệu cô lập.

## 12. Kiểm tra sự vắng mặt của attribute không mong muốn

Một kiểm thử bảo mật hữu ích là xác nhận các getter nội bộ **không bị export**.

Ví dụ bean có:

```java
public String getInternalSecret() {
    return "not-for-jmx";
}
```

Nếu method không có `@ManagedAttribute` và dùng assembler dựa trên annotation, contract dự kiến không công bố `InternalSecret`. Test:

```java
Map<String, MBeanAttributeInfo> attributes = ...;

assertFalse(
    attributes.containsKey("InternalSecret"),
    "Sensitive internal attribute must not be exposed"
);
```

Tuy nhiên, cách export ảnh hưởng kết quả. Một Standard MBean có interface công bố getter hoặc một assembler dựa trên public methods có thể tạo bề mặt khác. Vì thế test cần chạy với **chính cấu hình exporter/assembler** mà ứng dụng sẽ dùng, không chỉ kiểm tra annotation riêng lẻ.

Không đưa giá trị secret thật vào fixture test hoặc log. Mục tiêu là xác nhận interface không phơi bày một attribute không được phép.

## 13. Test với MBeanServer riêng để tránh nhiễu

Khi chạy nhiều test trong một JVM, dùng platform MBeanServer có thể dẫn đến:

- Trùng ObjectName giữa các test.
- MBean từ test trước còn tồn tại.
- Spring contexts khác nhau ghi vào cùng registry.
- Test phụ thuộc thứ tự chạy.
- Test thất bại khi chạy song song hoặc khi có plugin khác export MBean cùng domain.

Một giải pháp là dùng:

```java
MBeanServer isolated =
    MBeanServerFactory.newMBeanServer("com.example.test");
```

Mỗi test hoặc nhóm test có thể sở hữu một server riêng. `newMBeanServer` không đăng ký server vào danh sách tra cứu của `MBeanServerFactory`, giúp giảm ảnh hưởng ngoài ý muốn. Tuy nhiên isolation không thay thế cleanup nếu test giữ reference tới context/connector hoặc tài nguyên dài hạn.

Khi dùng Spring `MBeanExporter`, `setServer(isolated)` giúp bảo đảm exporter đăng ký đúng server test. Tránh một exporter tự động tìm platform server trong khi test lại kiểm tra isolated server.

### 13.1. Dọn tài nguyên bằng Spring context

Trong test mẫu:

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(
             JmxTestConfiguration.class
         )) {
    // Assertions
}
```

`close()` được gọi khi rời `try`. Exporter có cơ hội hủy đăng ký những MBean mà nó quản lý. Nếu test tự đăng ký bằng `server.registerMBean`, cần tự unregister đúng resource do test sở hữu.

Một bài test tốt không nên xóa toàn bộ domain của platform server chỉ để dọn môi trường.

## 14. Những lỗi thường gặp và cách phân tích

| Hiện tượng | Khả năng nguyên nhân | Kiểm tra tiếp |
| --- | --- | --- |
| `isRegistered` false | Sai server, sai ObjectName hoặc exporter chưa chạy | Kiểm tra `setServer`, naming strategy và context |
| `InstanceNotFoundException` | Không có MBean dưới tên đó tại thời điểm đọc | Kiểm tra registry và lifecycle |
| `InstanceAlreadyExistsException` | Trùng ObjectName lúc đăng ký | Dùng server test riêng hoặc tên duy nhất |
| Metadata không có attribute | Thiếu annotation, assembler không dùng metadata hoặc sai exporter | Xem `getMBeanInfo` và cấu hình |
| Tên attribute khác dự kiến | Getter JavaBeans/naming khác hoặc đổi contract | Kiểm tra `getName()` thực tế |
| `readable=false` | Thiếu getter được export | Kiểm tra annotation và method |
| `writable=false` | Thiếu setter được export | Kiểm tra annotation và method |
| Type `int` thay vì `long` | Kiểu getter đã khác | Đồng bộ contract, client và test |
| `getAttribute` lỗi dù metadata có readable | Lỗi runtime trong getter, security hoặc trạng thái bean | Kiểm tra cause và trạng thái |
| Test pass đơn lẻ nhưng fail trong suite | Shared server/context hoặc lệ thuộc thứ tự | Cô lập server, cleanup, không dùng static state tùy tiện |

Không nên khắc phục test fail bằng cách bỏ qua assertion mà chưa biết nguyên nhân. Trong phạm vi xây dựng bài kiểm thử, cần xác định liệu yêu cầu contract đã thay đổi có chủ đích hay exporter đang cấu hình sai.

## 15. Đọc metadata của attribute bằng `MBeanServerConnection`

Test local sử dụng `MBeanServer`, nhưng `MBeanServerConnection` là interface chung cho nhiều thao tác từ xa. Có thể viết helper tái sử dụng cho local/remote:

```java
import javax.management.MBeanServerConnection;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

public final class JmxMetadataReader {

    private JmxMetadataReader() {}

    public static MBeanAttributeInfo findAttribute(
            MBeanServerConnection connection,
            ObjectName name,
            String attributeName) throws Exception {

        MBeanInfo info = connection.getMBeanInfo(name);
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            if (attributeName.equals(attribute.getName())) {
                return attribute;
            }
        }
        throw new IllegalArgumentException(
            "Missing attribute " + attributeName
        );
    }
}
```

Điều này cho phép test hợp đồng trên JMX connector thực tế nếu cần. Nhưng integration test remote thường chậm hơn, phụ thuộc transport, credentials, port và network policy. Với phần lớn metadata tests, test local trong cùng JVM đủ để xác minh assembler/exporter. Chỉ dùng remote test khi bạn muốn kiểm tra **connector, security, đường truyền và khả năng truy cập từ môi trường khác**.

Đặc biệt, một remote JMX client có thể thiếu class custom của server. Nên chọn kiểu dữ liệu quản trị phù hợp khi thiết kế MBean để tránh coupling classloader.

## 16. Đọc và kiểm tra descriptor metadata khi cần

Ngoài các trường chuẩn, JMX có `Descriptor` cho metadata mở rộng. Một số assembler hoặc Model MBean có thể cung cấp `default`, `currencyTimeLimit`, `persistPolicy` hoặc những field khác.

```java
import javax.management.Descriptor;
import javax.management.MBeanAttributeInfo;

MBeanAttributeInfo attribute =
    JmxAssertions.requireAttribute(info, "QueuedTasks");

Descriptor descriptor = attribute.getDescriptor();

for (String field : descriptor.getFieldNames()) {
    System.out.printf(
        "descriptor[%s]=%s%n",
        field,
        descriptor.getFieldValue(field)
    );
}
```

Không nên mặc định mọi `MBeanAttributeInfo` đều có field `default` hay bất kỳ field tùy chọn nào khác. Nếu contract ứng dụng phụ thuộc vào descriptor, test phải chứng minh chúng được exporter thực sự công bố trong phiên bản Spring/JMX đang dùng.

Với `@ManagedAttribute(defaultValue = "8")`, metadata default chỉ là thông tin mô tả; nó không tự khởi tạo giá trị runtime thành 8. Để kiểm tra trạng thái hiện tại, vẫn dùng `getAttribute`.

## 17. Tạo expected contract rõ ràng

Một cách tổ chức test giúp bảo trì là định nghĩa contract dưới dạng dữ liệu:

```java
record ExpectedAttribute(
    String name,
    String type,
    boolean readable,
    boolean writable
) {}

List<ExpectedAttribute> expected = List.of(
    new ExpectedAttribute("Enabled", "boolean", true, true),
    new ExpectedAttribute("QueuedTasks", "int", true, false)
);
```

Sau đó so sánh với `MBeanInfo`:

```java
Map<String, MBeanAttributeInfo> actual =
    Arrays.stream(info.getAttributes())
        .collect(Collectors.toMap(
            MBeanAttributeInfo::getName,
            Function.identity()
        ));

for (ExpectedAttribute item : expected) {
    MBeanAttributeInfo attribute = actual.get(item.name());

    assertNotNull(attribute, "Missing " + item.name());
    assertEquals(item.type(), attribute.getType());
    assertEquals(item.readable(), attribute.isReadable());
    assertEquals(item.writable(), attribute.isWritable());
}
```

Mẫu này dễ mở rộng sang nhiều MBean và tạo thông báo test failure rõ ràng. Khi có nhu cầu kiểm tra descriptor, description hoặc isIs flag, mở rộng cấu trúc expected theo hợp đồng thật thay vì kiểm tra tràn lan mọi metadata của framework.

### 17.1. Có nên kiểm tra chính xác số lượng attribute?

Tùy mục tiêu:

- **Positive contract:** xác nhận những attribute tối thiểu cần có. Dùng `containsKey` hoặc `assertNotNull`.
- **Strict contract:** xác nhận đúng tập attribute được phép xuất, không có attribute ngoài dự kiến.
- **Security contract:** xác nhận một số attribute nội bộ/nhạy cảm chắc chắn không được export.

Nếu chỉ cần bảo đảm `Enabled` và `QueuedTasks` tồn tại, không nên fail test vì framework công bố thêm metadata hợp lệ không ảnh hưởng yêu cầu.

## 18. Ví dụ scenario kiểm thử khi refactor Spring bean

Giả sử ứng dụng ban đầu có:

```java
@ManagedAttribute
public int getQueuedTasks() { ... }
```

Sau refactor đổi thành:

```java
@ManagedAttribute
public long getQueuedTasks() { ... }
```

Lúc này metadata type chuyển từ `int` sang `long`. Một dashboard hoặc script ép `Integer` có thể gặp lỗi. Test metadata phát hiện sự thay đổi dù cả hai phiên bản đều build thành công.

Một trường hợp khác là đổi:

```java
public boolean isEnabled()
```

thành:

```java
public boolean isQueueEnabled()
```

Nếu naming theo JavaBeans convention, tên attribute có thể thay từ `Enabled` thành `QueueEnabled`. Test theo tên phát hiện đứt gãy contract.

Một trường hợp nữa là vô tình bỏ annotation getter sau khi chia lớp service. Spring context và bean vẫn tồn tại, nhưng attribute biến mất khỏi JMX. Test `getMBeanInfo` ngăn thay đổi này vượt qua pipeline kiểm thử.

## 19. Bài tập thực hành

Hãy dùng `QueueMonitor` và `JmxTestConfiguration` ở các phần trên để thực hiện:

1. Tạo một test JUnit 5 mở `AnnotationConfigApplicationContext`.
2. Inject `MBeanServer` do test tạo.
3. Xác nhận MBean có ObjectName `com.example.monitoring:type=QueueMonitor,name=Primary`.
4. Đọc `MBeanInfo` và in danh sách `MBeanAttributeInfo`.
5. Assert `Enabled` là `boolean`, readable và writable.
6. Assert `QueuedTasks` là `int`, readable và không writable.
7. Assert `InternalSecret` không có nếu bean có một getter nội bộ không được export.
8. Đọc `Enabled` qua `getAttribute`, ghi `false` và đọc lại.
9. Thử viết `QueuedTasks` qua `setAttribute`, quan sát lỗi vì attribute chỉ đọc.
10. Đổi tên getter `getQueuedTasks` và chạy lại test để thấy contract break.
11. Đóng context và xác minh tài nguyên test không tiếp tục dùng chung với test khác.

Một kết quả kỳ vọng của metadata test:

```text
MBean registered: true
Enabled: boolean readable=true writable=true
QueuedTasks: int readable=true writable=false
```

Dùng test độc lập và server riêng để không ảnh hưởng MBean thực tế của tiến trình khác. Không chạy operation có side effect trên production để thực hiện bài thực hành.

## 20. Câu hỏi tự kiểm tra

**1. `MBeanInfo` cung cấp thông tin gì?** Metadata về interface quản trị JMX của một MBean, bao gồm attribute, operation và notification.

**2. API nào trả danh sách attribute?** `MBeanInfo.getAttributes()`.

**3. API nào trả tên và kiểu một attribute?** `MBeanAttributeInfo.getName()` và `getType()`.

**4. Làm thế nào biết một attribute có thể đọc/ghi theo metadata?** `isReadable()` và `isWritable()`.

**5. Vì sao nên dùng Map theo attribute name trong test?** Để tránh phụ thuộc thứ tự mảng metadata.

**6. Nếu metadata có attribute nhưng getter lỗi, test nào phát hiện?** Lời gọi thực tế `MBeanServer.getAttribute(...)`.

**7. Vì sao nên tạo MBeanServer riêng cho test?** Giảm trùng ObjectName, tương tác test và rủi ro rò rỉ đăng ký trên platform server.

**8. `description` có phải tên dùng để gọi `getAttribute` không?** Không, client phải dùng `getName()`.

**9. Khi nào cần assert exact list attribute?** Khi interface quản trị cần là một hợp đồng đóng, không được phép lộ bất kỳ attribute nào ngoài danh sách.

**10. Nếu exporter đã đăng ký trên server riêng, vì sao kiểm tra platform server thất bại?** Vì đó là hai registry khác nhau.

**11. Test annotation có thay thế test MBeanInfo không?** Không, annotation chỉ thể hiện ý định; `MBeanInfo` phản ánh interface mà server công bố.

**12. Nếu refactor getter từ int sang long, metadata test giúp gì?** Phát hiện sự thay đổi kiểu dữ liệu mà client JMX có thể đang phụ thuộc.

## 21. Ghi nhớ

- **Kiểm thử JMX nên đọc `MBeanInfo` thực tế**, không chỉ kiểm tra source annotation.
- **`MBeanAttributeInfo`** mô tả tên, kiểu, khả năng đọc/ghi và description của từng attribute.
- **`isRegistered`** kiểm tra sự tồn tại của MBean; **`getMBeanInfo`** kiểm tra giao diện; **`getAttribute`** kiểm tra giá trị runtime.
- **Dùng MBeanServer riêng trong test** để tránh va chạm ObjectName và tương tác giữa các Spring contexts.
- **Assert theo tên thay vì thứ tự** của `getAttributes()`.
- **Phân biệt positive contract, strict contract và security contract** khi quyết định số lượng attribute cần assert.
- **Metadata assembler, naming strategy và exporter** đều có thể thay đổi giao diện JMX cuối cùng; test cần dùng cấu hình tương ứng.
- **Description và descriptor là metadata**, không phải giá trị thực của bean.
- **Test contract JMX giúp phát hiện hồi quy** sau refactor, đổi kiểu getter, đổi annotation hoặc thay cơ chế export.

Bằng cách đọc `MBeanInfo` và xác nhận attribute mong đợi trên đúng `MBeanServer`, bạn kiểm tra được điều mà JMX client thực sự nhìn thấy. Đây là nền tảng để duy trì giao diện quản trị Spring Framework JMX nhất quán, an toàn và ổn định theo thời gian.