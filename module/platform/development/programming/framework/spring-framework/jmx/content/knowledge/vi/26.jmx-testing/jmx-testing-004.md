# Gọi attribute read-only, read–write và operation trong kiểm thử Spring Framework JMX

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Kiểm thử  
> **Bài học:** Gọi attribute read-only, read–write và operation

## 1. Mục tiêu bài học

Kiểm thử JMX không dừng lại ở việc thấy tên MBean trong JConsole. Một MBean có thể đăng ký thành công nhưng attribute không đọc được, setter không hoạt động, chữ ký operation không khớp hoặc lỗi xuất hiện khi đi qua Spring JMX exporter. Sau bài học này, bạn có thể:

- Phân biệt attribute **read-only**, **read–write** và JMX **operation**.
- Đọc \`MBeanInfo\` để nhận diện tên, kiểu, quyền đọc/ghi và chữ ký operation thực tế.
- Gọi \`MBeanServerConnection.getAttribute\`, \`setAttribute\`, \`invoke\`.
- Viết kiểm thử tích hợp cho Spring \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`.
- Xác thực cả kết quả trả về và tác động lên trạng thái bean.
- Kiểm tra trường hợp lỗi: write vào read-only attribute, sai kiểu, sai operation signature và giá trị không hợp lệ.
- Phân biệt lỗi export, lỗi routing JMX và lỗi business method.

## 2. Bức tranh tổng thể

Spring Framework có thể xuất bản một Spring bean thành MBean thông qua \`MBeanExporter\` hoặc \`AnnotationMBeanExporter\`.

\`\`\`text
Spring ApplicationContext
         |
         v
@ManagedResource bean
         |
         +-- @ManagedAttribute getter
         |       -> Read-only attribute
         |
         +-- @ManagedAttribute getter + setter
         |       -> Read–write attribute
         |
         +-- @ManagedOperation method
                 -> JMX operation
         |
         v
MBeanExporter / ModelMBean
         |
         v
MBeanServer
         |
         +-- getAttribute(ObjectName, attributeName)
         +-- setAttribute(ObjectName, Attribute)
         +-- invoke(ObjectName, operationName, params, signature)
         |
         v
Integration test / JConsole / JMX client
\`\`\`

Một client JMX chỉ nên sử dụng những gì MBean **thật sự công bố**, không suy luận từ mọi public method trong Java class.

## 3. Phân biệt ba loại thao tác

| Loại | API JMX | Hợp đồng kiểm thử |
|---|---|---|
| Read-only attribute | \`getAttribute\` | Đọc thành công; metadata readable=true, writable=false |
| Read–write attribute | \`getAttribute\`, \`setAttribute\` | Đọc giá trị cũ, ghi giá trị hợp lệ, đọc lại và kiểm tra trạng thái |
| Operation | \`invoke\` | Đúng tên, số lượng/kiểu tham số, giá trị trả về và tác dụng phụ |

Ví dụ các thuộc tính:

\`\`\`text
QueueDepth : int
  readable=true
  writable=false

MaxWorkers : int
  readable=true
  writable=true

resetCounters() : void
  operation
\`\`\`

Attribute thường theo quy ước JavaBeans: \`getQueueDepth()\` tương ứng \`QueueDepth\`; \`getMaxWorkers()\` và \`setMaxWorkers(int)\` có thể tạo attribute đọc–ghi. Nhưng quyền thực tế phụ thuộc assembler và annotation được áp dụng. Vì vậy phải xác minh metadata.

## 4. MBean ví dụ để kiểm thử

Xây một MBean đơn giản, vừa có số liệu chỉ đọc vừa có cấu hình có thể thay đổi.

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=QueueControl,name=main",
    description = "Queue management test MBean"
)
public class QueueControl {

    private final AtomicInteger queueDepth = new AtomicInteger(3);
    private volatile int maxWorkers = 4;

    @ManagedAttribute(
        description = "Current queue depth"
    )
    public int getQueueDepth() {
        return queueDepth.get();
    }

    @ManagedAttribute(
        description = "Configured worker limit"
    )
    public int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute(
        description = "Configured worker limit"
    )
    public void setMaxWorkers(int maxWorkers) {
        if (maxWorkers < 1 || maxWorkers > 64) {
            throw new IllegalArgumentException(
                "maxWorkers must be between 1 and 64"
            );
        }
        this.maxWorkers = maxWorkers;
    }

    @ManagedOperation(
        description = "Clear queue depth counter"
    )
    public void resetCounters() {
        queueDepth.set(0);
    }

    @ManagedOperation(
        description = "Add synthetic queue entries"
    )
    public int addEntries(int count) {
        if (count <= 0 || count > 100) {
            throw new IllegalArgumentException(
                "count must be 1..100"
            );
        }
        return queueDepth.addAndGet(count);
    }
}
\`\`\`

Ý nghĩa:

- \`QueueDepth\`: chỉ có getter được expose, vì thế là read-only trong mô hình annotation này.
- \`MaxWorkers\`: getter và setter đều được đánh dấu, nên là read–write.
- \`resetCounters()\`: operation không tham số, không trả giá trị.
- \`addEntries(int)\`: operation nhận primitive \`int\` và trả \`int\`.
- Validation trong setter và operation thể hiện lỗi khi input không hợp lệ.

Mã là fixture kiểm thử. Trong ứng dụng thật, đừng xuất bản operation có thể thay đổi nghiệp vụ nếu không có authorization và audit phù hợp.

## 5. Java configuration cho Spring JMX

Để kiểm thử ổn định, cấu hình exporter sử dụng một \`MBeanServer\` xác định.

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = QueueControl.class)
@EnableMBeanExport(server = "jmxServer")
public class JmxTestConfiguration {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

\`@EnableMBeanExport\` kích hoạt annotation-based export; \`server = "jmxServer"\` tham chiếu **tên bean Spring**, không phải hostname hoặc JMX endpoint URL.

Nếu chọn platform MBeanServer, các test chia sẻ cùng JVM có thể xung đột ObjectName. Để cô lập test, có thể tạo server riêng:

\`\`\`java
@Bean
public MBeanServer jmxServer() {
    return javax.management.MBeanServerFactory
        .newMBeanServer("learning.test");
}
\`\`\`

Cách dùng custom server giúp tránh xung đột với MBeanServer nền tảng, nhưng JConsole local attach thường không tự hiển thị MBean trong server riêng. Với integration test, hãy inject và truy vấn chính server mà exporter đã được cấu hình dùng.

## 6. Bước chuẩn bị: xác minh MBean đã đăng ký

Trước khi gọi attribute hay operation:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=QueueControl,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}
\`\`\`

\`isRegistered\` trả \`true\` cho ObjectName cụ thể trong **MBeanServer hiện tại**. Nó không chứng minh bean đã công bố đúng metadata; cần đọc \`MBeanInfo\`.

Nếu \`isRegistered=false\`, kiểm tra component scan, \`@ManagedResource\`, exporter, ObjectName và server đang được sử dụng trước khi thử invocation.

## 7. Đọc MBeanInfo

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf(
        "Attribute %s type=%s readable=%s writable=%s%n",
        a.getName(),
        a.getType(),
        a.isReadable(),
        a.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.print(p.getType() + " ");
    }

    System.out.println(") -> " + op.getReturnType());
}
\`\`\`

Ví dụ metadata kỳ vọng:

\`\`\`text
Attribute QueueDepth type=int readable=true writable=false
Attribute MaxWorkers type=int readable=true writable=true
resetCounters() -> void
addEntries(int) -> int
\`\`\`

Tên attribute, kiểu và quyền đọc/ghi lấy từ \`MBeanInfo\` mới là hợp đồng JMX mà client thấy. Với môi trường có nhiều exporter hoặc assembler tùy biến, đừng chỉ dựa vào annotation trong source.

## 8. Kiểm thử read-only attribute

Cách đọc:

\`\`\`java
Object rawDepth = server.getAttribute(
    name,
    "QueueDepth"
);

int depth = (Integer) rawDepth;
System.out.println(depth);
\`\`\`

\`getQueueDepth()\` trả primitive \`int\`, nhưng JMX \`getAttribute\` trả \`Object\`, vì vậy giá trị thường được boxing thành \`Integer\`.

Một phép assert:

\`\`\`java
assertEquals(
    3,
    server.getAttribute(name, "QueueDepth")
);
\`\`\`

### Xác minh không writable

\`\`\`java
MBeanAttributeInfo depthInfo =
    Arrays.stream(server.getMBeanInfo(name).getAttributes())
        .filter(a -> a.getName().equals("QueueDepth"))
        .findFirst()
        .orElseThrow();

assertTrue(depthInfo.isReadable());
assertFalse(depthInfo.isWritable());
\`\`\`

Đây là kiểm tra metadata. Để xác nhận hành vi runtime, có thể thử write một lần trong test riêng và kỳ vọng thất bại.

\`\`\`java
assertThrows(
    javax.management.AttributeNotFoundException.class,
    () -> server.setAttribute(
        name,
        new javax.management.Attribute("QueueDepth", 99)
    )
);
\`\`\`

Tùy implementation/adapter, loại exception có thể được bọc hoặc khác nếu lỗi xảy ra ở tầng validation. Đừng chỉ dùng một loại exception để kết luận MBean bị bảo vệ đúng; kết hợp metadata và kiểm chứng state không thay đổi.

**Không thử ghi attribute chỉ đọc trên production chỉ để chứng minh lỗi.** Dùng fixture hoặc môi trường test.

## 9. Kiểm thử read–write attribute

Đọc giá trị ban đầu:

\`\`\`java
int before = (Integer) server.getAttribute(
    name,
    "MaxWorkers"
);
\`\`\`

Ghi giá trị mới:

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxWorkers", 8)
);
\`\`\`

Đọc lại:

\`\`\`java
int after = (Integer) server.getAttribute(
    name,
    "MaxWorkers"
);

assertEquals(8, after);
\`\`\`

**Quan trọng:** \`Attribute\` chứa tên thuộc tính JMX và giá trị, không chứa Java method name. Dùng \`"MaxWorkers"\`, không dùng \`"setMaxWorkers"\`.

Đối với primitive setter \`int\`, giá trị \`8\` trong object \`Attribute\` được boxing thành \`Integer\`. Nếu gửi \`Long.valueOf(8)\` cho attribute kiểu \`int\`, có thể gặp lỗi kiểu.

### Kiểm tra state bean

Nếu có Spring bean:

\`\`\`java
QueueControl bean = context.getBean(QueueControl.class);

assertEquals(
    8,
    bean.getMaxWorkers()
);
\`\`\`

Kết hợp đọc lại qua JMX và đọc state bean giúp xác nhận attribute truy cập đúng đối tượng, không phải một MBean khác cùng tên trên server khác.

## 10. Kiểm thử giá trị setter không hợp lệ

Setter có validation:

\`\`\`java
if (maxWorkers < 1 || maxWorkers > 64) {
    throw new IllegalArgumentException(...);
}
\`\`\`

Kiểm thử:

\`\`\`java
int oldValue = (Integer) server.getAttribute(
    name,
    "MaxWorkers"
);

assertThrows(
    RuntimeException.class,
    () -> server.setAttribute(
        name,
        new Attribute("MaxWorkers", -5)
    )
);

assertEquals(
    oldValue,
    server.getAttribute(name, "MaxWorkers")
);
\`\`\`

\`RuntimeException.class\` ở đây là một ví dụ rộng để minh họa failure path; với kiểm thử thực tế nên quan sát exception do JMX ModelMBean/adapter bọc, sau đó assert kiểu và cause phù hợp với runtime đã chọn.

Bảo đảm setter **validate trước khi mutate**. Nếu setter thay state rồi mới ném exception, phép kiểm thử “không thay đổi giá trị” sẽ thất bại và chỉ ra rủi ro điều khiển không an toàn.

## 11. Gọi operation không tham số

Method:

\`\`\`java
@ManagedOperation
public void resetCounters() {
    queueDepth.set(0);
}
\`\`\`

JMX invocation:

\`\`\`java
Object result = server.invoke(
    name,
    "resetCounters",
    new Object[0],
    new String[0]
);
\`\`\`

Kiểm tra:

\`\`\`java
assertNull(result);

assertEquals(
    0,
    server.getAttribute(name, "QueueDepth")
);
\`\`\`

Cặp mảng rỗng thể hiện đúng “không có tham số”. \`new Object[] { null }\` là một tham số \`null\`, không giống mảng rỗng.

Với method \`void\`, \`invoke\` thường trả \`null\`. Nhưng thành công của \`invoke\` không tự chứng minh một công việc **bất đồng bộ** do operation khởi chạy đã hoàn thành. Nếu operation enqueue job, cần chờ hoặc truy vấn trạng thái job.

## 12. Gọi operation có tham số

Method:

\`\`\`java
@ManagedOperation
public int addEntries(int count) {
    return queueDepth.addAndGet(count);
}
\`\`\`

Gọi:

\`\`\`java
Object result = server.invoke(
    name,
    "addEntries",
    new Object[] { 5 },
    new String[] { "int" }
);
\`\`\`

Nếu trước đó đã reset counter, giá trị trả về kỳ vọng là \`5\`.

\`\`\`java
assertEquals(5, result);
assertEquals(5, server.getAttribute(name, "QueueDepth"));
\`\`\`

**Signature phải là tên kiểu khai báo trong Java**, không phải class runtime của object trong \`Object[]\`. Với method \`addEntries(int)\`, signature là \`"int"\`, dù \`5\` được boxing thành \`Integer\`.

Một invocation sai:

\`\`\`java
server.invoke(
    name,
    "addEntries",
    new Object[] { Integer.valueOf(5) },
    new String[] { "java.lang.Integer" }
);
\`\`\`

có thể không tìm thấy operation \`addEntries(int)\`. JMX không tự giải quyết overload theo mọi quy tắc boxing/widening của Java compiler.

## 13. Kiểm tra metadata chữ ký trước khi invoke

\`\`\`java
MBeanOperationInfo op = Arrays.stream(
    server.getMBeanInfo(name).getOperations()
)
    .filter(o -> o.getName().equals("addEntries"))
    .filter(o -> o.getSignature().length == 1)
    .filter(o -> "int".equals(o.getSignature()[0].getType()))
    .findFirst()
    .orElseThrow();

assertEquals("int", op.getReturnType());
\`\`\`

Nếu có overload cùng tên, hãy so toàn bộ danh sách kiểu tham số. Chọn theo tên operation hoặc số lượng tham số đơn thuần có thể chọn nhầm.

Dùng \`MBeanInfo\` đặc biệt hữu ích khi exporter sử dụng assembler tùy biến hoặc khi client được biên dịch tách khỏi server.

## 14. Kịch bản integration test với JUnit 5 và Spring Test

Ví dụ bộ khung JUnit 5:

\`\`\`java
package example.jmx;

import java.util.Arrays;
import javax.management.Attribute;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(JmxTestConfiguration.class)
class QueueControlJmxTest {

    @Autowired
    MBeanServer server;

    @Autowired
    QueueControl queueControl;

    private ObjectName name() throws Exception {
        return new ObjectName(
            "learning.jmx:type=QueueControl,name=main"
        );
    }

    @Test
    void readOnlyAttributeIsReadable() throws Exception {
        ObjectName name = name();

        assertTrue(server.isRegistered(name));

        MBeanAttributeInfo metadata = Arrays.stream(
            server.getMBeanInfo(name).getAttributes()
        )
            .filter(a -> a.getName().equals("QueueDepth"))
            .findFirst()
            .orElseThrow();

        assertTrue(metadata.isReadable());
        assertFalse(metadata.isWritable());
        assertEquals(
            queueControl.getQueueDepth(),
            server.getAttribute(name, "QueueDepth")
        );
    }

    @Test
    void readWriteAttributeChangesState() throws Exception {
        ObjectName name = name();

        server.setAttribute(
            name,
            new Attribute("MaxWorkers", 8)
        );

        assertEquals(8, server.getAttribute(name, "MaxWorkers"));
        assertEquals(8, queueControl.getMaxWorkers());
    }

    @Test
    void operationCanBeInvoked() throws Exception {
        ObjectName name = name();

        server.invoke(
            name,
            "resetCounters",
            new Object[0],
            new String[0]
        );

        Object result = server.invoke(
            name,
            "addEntries",
            new Object[] { 5 },
            new String[] { "int" }
        );

        assertEquals(5, result);
        assertEquals(5, server.getAttribute(name, "QueueDepth"));
    }
}
\`\`\`

Bộ test dùng một Spring context được tạo qua \`@SpringJUnitConfig\`. Với \`MBeanServer\` bean đã khai báo trong \`JmxTestConfiguration\`, có thể inject server bằng \`@Autowired\`.

### Lưu ý độ độc lập giữa test

Các test có thay đổi state như \`setMaxWorkers\` hoặc \`resetCounters\` có thể ảnh hưởng nhau nếu cùng chia sẻ context và chạy song song. Nên:

- Reset state trong \`@BeforeEach\` hoặc dùng fixture mới.
- Dùng server test riêng khi phù hợp.
- Không dựa vào thứ tự thực thi test.
- Tránh chạy song song các test ghi cùng một MBean nếu chưa cách ly.
- Đóng context/cleanup MBean theo lifecycle của Spring Test.

## 15. Cách ly MBeanServer cho test

Nếu dùng platform MBeanServer:

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

các bài test khác cùng JVM có thể cùng đăng ký tên:

\`\`\`text
learning.jmx:type=QueueControl,name=main
\`\`\`

Khi đó \`InstanceAlreadyExistsException\` có thể xuất hiện.

Một lựa chọn là tạo MBeanServer riêng cho context test:

\`\`\`java
@Bean
public MBeanServer jmxServer() {
    return MBeanServerFactory.newMBeanServer("learning.test");
}
\`\`\`

Dùng cùng server cho exporter và kiểm thử qua \`@EnableMBeanExport(server="jmxServer")\`.

\`MBeanServerFactory.newMBeanServer\` tạo một server mới không được đưa vào registry discovery giống \`createMBeanServer\`. Test vẫn có thể truy cập nó qua Spring bean. Nhờ đó các thử nghiệm không làm rối platform JMX registry.

## 16. Kiểm tra lỗi write vào read-only attribute

Một trường hợp tiêu cực:

\`\`\`java
assertThrows(
    Exception.class,
    () -> server.setAttribute(
        name,
        new Attribute("QueueDepth", 50)
    )
);
\`\`\`

Bài kiểm thử trên chỉ đảm bảo một exception xảy ra, nên kết hợp:

\`\`\`java
assertFalse(
    Arrays.stream(server.getMBeanInfo(name).getAttributes())
        .filter(a -> a.getName().equals("QueueDepth"))
        .findFirst()
        .orElseThrow()
        .isWritable()
);
\`\`\`

Rồi xác minh giá trị \`QueueDepth\` không bị thay đổi.

Nếu không có setter được export, JMX server sẽ từ chối thao tác write theo metadata. Không sửa implementation để “cho phép setter” chỉ để test thuận tiện, vì điều đó làm thay đổi contract quản trị.

## 17. Kiểm tra sai kiểu attribute

Attribute \`MaxWorkers\` được khai báo là \`int\`. Thử truyền kiểu không phù hợp:

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxWorkers", "eight")
);
\`\`\`

Thông thường setter sẽ không chấp nhận \`String\` thay vì \`int\`. Kiểm tra exception phù hợp và xác nhận state không bị thay đổi.

Tuy vậy, không áp dụng giả định rằng mọi framework adapter luôn ném cùng một exception class. Một số lỗi có thể được bọc bởi \`InvalidAttributeValueException\`, \`MBeanException\` hoặc runtime wrapper theo đường gọi.

## 18. Kiểm tra operation không tồn tại

\`\`\`java
server.invoke(
    name,
    "missingOperation",
    new Object[0],
    new String[0]
);
\`\`\`

Mong đợi lời gọi thất bại, thường dưới dạng \`ReflectionException\` hoặc lỗi JMX tương ứng.

Đây là phép kiểm thử hữu ích để khẳng định MBean không expose những operation ngoài danh sách cho phép. Tuy nhiên, để kiểm tra toàn bộ bề mặt công bố, nên duyệt \`MBeanInfo.getOperations()\` và so sánh với hợp đồng dự kiến, thay vì thử một tên bất kỳ.

## 19. Phân biệt attribute với operation

Một getter Java như:

\`\`\`java
public int getQueueDepth()
\`\`\`

có thể được expose dưới dạng attribute \`QueueDepth\`, không phải operation \`getQueueDepth\`.

Client thường đọc bằng:

\`\`\`java
server.getAttribute(name, "QueueDepth");
\`\`\`

thay vì:

\`\`\`java
server.invoke(
    name,
    "getQueueDepth",
    new Object[0],
    new String[0]
);
\`\`\`

Không xem hai cách tương đương trừ khi metadata MBean công bố operation \`getQueueDepth\` riêng. Cùng một Java method có thể được adapter mô hình hóa khác nhau tùy assembler, nhưng client phải tuân thủ management contract đã đăng ký.

## 20. Kiểm thử từ xa khác kiểm thử local ra sao?

\`MBeanServer\` implement \`MBeanServerConnection\`, nên phần lớn API kiểm thử có thể dùng chung:

\`\`\`java
MBeanServerConnection connection = server;
\`\`\`

Remote JMX:

\`\`\`java
try (JMXConnector connector =
         JMXConnectorFactory.connect(serviceUrl, environment)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    // getAttribute / setAttribute / invoke
}
\`\`\`

Với remote cần xem xét:

- Kết nối TCP/RMI, timeout và firewall.
- Authentication/authorization/TLS.
- Kiểu dữ liệu được truyền qua connector.
- Phân biệt timeout với operation thất bại thực sự.
- Khả năng operation đã chạy nhưng response bị mất.
- MBeanServer mà connector expose có đúng exporter đang dùng không.

Đừng retry mù operation có tác dụng phụ sau timeout; có thể nó đã được thực thi.

## 21. Kiểm thử qua JConsole

Một kịch bản thủ công:

1. Khởi chạy Spring context với MBean được export trên platform server.
2. Mở JConsole, chọn đúng JVM.
3. Vào tab **MBeans**.
4. Tìm \`learning.jmx:type=QueueControl,name=main\`.
5. Mở **Attributes**, xác nhận \`QueueDepth\` chỉ đọc.
6. Đọc \`MaxWorkers\`, sửa thành một giá trị hợp lệ, đọc lại.
7. Mở **Operations**, gọi \`resetCounters\`.
8. Gọi \`addEntries\` với giá trị số nguyên.
9. Đọc lại \`QueueDepth\`, xác nhận thay đổi.
10. Dừng app và quan sát lifecycle unregister nếu cần.

JConsole có thể hiển thị cơ chế chỉnh sửa attribute theo GUI tùy kiểu dữ liệu và implementation. Nếu GUI không cho phép thao tác, kiểm tra metadata và dùng Java client để xác nhận JMX API thay vì chỉ dựa vào giao diện.

## 22. Lưu ý security và vận hành

Các operation và writable attributes có thể thay đổi trạng thái ứng dụng thật. Do đó:

- Chỉ thử trong fixture/test environment, không dùng lệnh thay đổi trạng thái trên production nếu chưa được duyệt.
- Giới hạn MBean được export và ObjectName có chủ đích.
- Bật authentication/authorization/TLS khi có remote connector.
- Không coi Spring Security HTTP filter là kiểm soát tự động cho JMX.
- Không expose getter trả secret hoặc dữ liệu người dùng.
- Ghi audit cho những operation/writable attribute quan trọng.
- Không log toàn bộ tham số nếu có thể chứa dữ liệu nhạy cảm.

Kiểm thử JMX giúp xác nhận API quản trị hoạt động, nhưng cũng phải kiểm tra **chỉ đúng API mong muốn** được công bố.

## 23. Checklist kiểm thử

- [ ] Spring bean quản trị được tạo trong context.
- [ ] Exporter sử dụng đúng MBeanServer.
- [ ] ObjectName được đăng ký và không bị trùng.
- [ ] \`MBeanInfo\` phản ánh đúng các attribute/operation được mong đợi.
- [ ] Read-only attribute có \`readable=true\`, \`writable=false\`.
- [ ] Read-only attribute đọc được bằng \`getAttribute\`.
- [ ] Ghi read-only attribute bị từ chối.
- [ ] Read–write attribute đọc/ghi/đọc lại thành công.
- [ ] Setter từ chối input không hợp lệ và bảo vệ state.
- [ ] Operation không tham số gọi bằng mảng rỗng.
- [ ] Operation có tham số dùng đúng signature.
- [ ] Giá trị trả về và tác dụng phụ được xác minh.
- [ ] Sai kiểu, sai chữ ký và operation không tồn tại được xử lý.
- [ ] Các test không phụ thuộc thứ tự hoặc chia sẻ state ngoài ý muốn.
- [ ] Remote connector được kiểm tra riêng khi đó là đường truy cập cần hỗ trợ.

## 24. Bài tập thực hành

### Bài 1: Attribute chỉ đọc

Thêm attribute:

\`\`\`java
@ManagedAttribute
public boolean isHealthy() {
    return true;
}
\`\`\`

Đọc \`Healthy\` qua JMX, kiểm tra metadata và xác nhận không có setter JMX công bố.

### Bài 2: Attribute read–write

Thêm:

\`\`\`java
private volatile long timeoutMillis = 1000;

@ManagedAttribute
public long getTimeoutMillis() {
    return timeoutMillis;
}

@ManagedAttribute
public void setTimeoutMillis(long value) {
    if (value < 100 || value > 60_000) {
        throw new IllegalArgumentException(
            "timeoutMillis out of range"
        );
    }
    timeoutMillis = value;
}
\`\`\`

Kiểm tra \`setAttribute\` với \`Long.valueOf(3000)\`, đọc lại \`TimeoutMillis\` và thử giá trị \`-1\` để xác nhận validation.

### Bài 3: Operation có hai tham số

\`\`\`java
@ManagedOperation
public String schedule(String queueName, int batchSize) {
    return queueName + ":" + batchSize;
}
\`\`\`

Cách invoke:

\`\`\`java
Object result = server.invoke(
    name,
    "schedule",
    new Object[] { "orders", 20 },
    new String[] { "java.lang.String", "int" }
);
\`\`\`

Kiểm tra kết quả \`"orders:20"\`. Sau đó đảo thứ tự signature để quan sát lỗi và giải thích vì sao client phải dùng đúng kiểu khai báo.

## 25. Câu hỏi tự kiểm tra

1. Read-only attribute được xác định qua Java getter hay metadata JMX?
2. \`getAttribute\` và \`invoke\` có thể thay thế nhau cho mọi method không?
3. Vì sao \`setAttribute\` sử dụng \`Attribute("MaxWorkers", 8)\`?
4. \`int\` và \`java.lang.Integer\` có cùng chữ ký operation không?
5. Vì sao phải kiểm tra state sau khi một operation trả về?
6. Làm sao kiểm tra getter được export nhưng setter không được?
7. Vì sao test có nhiều phương thức thay đổi cùng bean có thể phụ thuộc lẫn nhau?
8. Khi remote invocation timeout, có thể khẳng định operation chưa chạy không?
9. MBeanServer riêng cho test có ích gì?
10. Vì sao kiểm thử JMX nên kiểm tra cả metadata và hành vi thực tế?

## 26. Ghi nhớ

\`\`\`text
MBeanInfo -> hợp đồng đã công bố
    |
    +-- Read-only attribute
    |       getAttribute()
    |       setAttribute() phải bị từ chối
    |
    +-- Read–write attribute
    |       getAttribute()
    |       setAttribute()
    |       getAttribute() để xác minh
    |
    +-- Operation
            invoke(name, op, params, signature)
            kiểm tra kết quả + tác dụng phụ
\`\`\`

**Nguyên tắc cốt lõi:** kiểm thử Spring JMX phải đi qua **MBeanServer thật** để xác nhận đúng những gì client quản trị nhìn thấy. Với read-only attribute, kiểm tra quyền và khả năng đọc. Với read–write attribute, kiểm tra ghi, đọc lại và validation. Với operation, dùng đúng chữ ký JMX và xác minh cả kết quả lẫn trạng thái; chỉ đọc annotation trong source hoặc thấy MBean tồn tại là chưa đủ.