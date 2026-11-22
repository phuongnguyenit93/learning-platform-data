# Kiểm thử gọi operation qua MBeanServer trong Spring Framework JMX

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao kiểm thử method Java trực tiếp chưa đủ để xác nhận operation thực sự được công bố qua JMX.
- Tạo Spring bean sử dụng **@ManagedResource** và **@ManagedOperation**, sau đó đăng ký thành MBean.
- Dùng **MBeanServer.invoke(ObjectName, operationName, params, signature)** để gọi operation giống một JMX client.
- Viết integration test kiểm tra ObjectName, operation metadata, kết quả trả về, tham số, lỗi và tác dụng phụ.
- Phân biệt cách gọi qua MBeanServer trong cùng JVM với gọi qua MBeanServerConnection từ một client bên ngoài.
- Xử lý những lỗi thường gặp: InstanceNotFoundException, ReflectionException, MBeanException, sai signature, tên operation hoặc cấu hình exporter.

## 1. Vì sao cần kiểm thử ở ranh giới JMX?

Giả sử một Spring bean có method:

\`\`\`java
public void clearCache() {
    cache.clear();
}
\`\`\`

Unit test có thể gọi trực tiếp:

\`\`\`java
cacheManager.clearCache();
\`\`\`

Nếu test pass, ta chỉ biết Java method hoạt động trong phạm vi object. Ta **chưa chứng minh** method đó được Spring export thành JMX operation, có đúng ObjectName và tên operation, có signature mà JMX client hiểu, hoặc có thể gọi qua MBeanServer.

Trong Spring Framework JMX, đường đi quản trị thường là:

\`\`\`text
Spring ApplicationContext
    |
    +-- bean với @ManagedResource, @ManagedOperation
    |
    v
MBeanExporter + MBeanInfoAssembler
    |
    v
MBeanServer.registerMBean(...)
    |
    v
MBeanServer.invoke(ObjectName, operationName, params, signature)
    |
    v
Managed operation trong Spring bean
\`\`\`

Một integration test ở ranh giới \`MBeanServer.invoke\` kiểm chứng cả **registration**, **metadata mapping** và **việc gọi method**. Đây là kiểm thử quan trọng khi JConsole, script vận hành hoặc hệ thống quản trị khác dựa vào JMX contract.

## 2. API invoke của MBeanServer

Phương thức trọng tâm:

\`\`\`java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
)
\`\`\`

Các tham số:

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| \`name\` | ObjectName xác định MBean cần gọi | \`learning.jmx:type=Queue,name=Primary\` |
| \`operationName\` | Tên operation được công bố | \`pause\` |
| \`params\` | Mảng các đối số truyền theo thứ tự | \`new Object[] { 25 }\` |
| \`signature\` | Mảng tên kiểu Java cho từng tham số | \`new String[] { "int" }\` |
| Giá trị trả về | Kết quả operation hoặc null nếu void | \`Boolean.TRUE\`, \`null\` |

Một operation không nhận tham số:

\`\`\`java
Object result = server.invoke(
    objectName,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

Một operation nhận \`int\`:

\`\`\`java
Object result = server.invoke(
    objectName,
    "setThreshold",
    new Object[] { 25 },
    new String[] { "int" }
);
\`\`\`

Mảng \`signature\` là **tên kiểu Java theo contract JMX**, không phải các giá trị. Ví dụ \`"int"\` khác \`"java.lang.Integer"\` nếu method thực tế nhận kiểu primitive \`int\`. Với operation không có tham số, truyền mảng rỗng là cách biểu diễn rõ ràng.

**Lưu ý:** Tham số và signature phải khớp số lượng, thứ tự và kiểu của operation được export. Compiler không kiểm tra sẵn tên operation ở chuỗi \`"setThreshold"\`; sai contract thường chỉ xuất hiện lúc runtime.

## 3. @ManagedOperation định nghĩa bề mặt quản trị

Spring Framework cung cấp các annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
\`\`\`

Ví dụ:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary"
)
public class QueueAdministration {

    @ManagedOperation(description = "Pause accepting new jobs")
    public void pause() {
        // ...
    }
}
\`\`\`

\`@ManagedResource\` xác định managed resource. \`@ManagedOperation\` đánh dấu một method được công bố như operation khi exporter sử dụng annotation-based metadata assembly.

Một public method **không có annotation** không tự động được export chỉ vì nó public, nếu cấu hình metadata assembler áp dụng chiến lược chọn theo annotation.

\`@ManagedOperationParameter\` giúp mô tả tham số để tooling hiển thị dễ hiểu hơn:

\`\`\`java
@ManagedOperation(description = "Change queue threshold")
@ManagedOperationParameter(
    index = 0,
    name = "threshold",
    description = "Non-negative queue threshold"
)
public void setThreshold(int threshold) {
    // ...
}
\`\`\`

Annotation mô tả tham số không đổi kiểu Java của operation. \`signature\` khi invoke vẫn phải là \`"int"\`.

## 4. Ví dụ Spring bean có hai operations

Ta tạo một queue management component với trạng thái đơn giản:

- \`pause()\`: dừng tiếp nhận job mới.
- \`resume()\`: cho phép tiếp nhận job.
- \`updateThreshold(int)\`: đổi ngưỡng.
- \`describeState()\`: trả trạng thái dạng String.

### 4.1. Lớp managed resource

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Operational queue management"
)
public class QueueAdministration {

    private boolean paused;
    private int threshold = 100;

    @ManagedAttribute(description = "Whether queue is paused")
    public synchronized boolean isPaused() {
        return paused;
    }

    @ManagedAttribute(description = "Current queue threshold")
    public synchronized int getThreshold() {
        return threshold;
    }

    @ManagedOperation(description = "Pause accepting new jobs")
    public synchronized void pause() {
        paused = true;
    }

    @ManagedOperation(description = "Resume accepting jobs")
    public synchronized void resume() {
        paused = false;
    }

    @ManagedOperation(description = "Update the queue threshold")
    @ManagedOperationParameter(
        index = 0,
        name = "newThreshold",
        description = "A positive threshold"
    )
    public synchronized void updateThreshold(int newThreshold) {
        if (newThreshold <= 0) {
            throw new IllegalArgumentException(
                "newThreshold must be greater than zero"
            );
        }
        threshold = newThreshold;
    }

    @ManagedOperation(description = "Describe current queue state")
    public synchronized String describeState() {
        return "paused=" + paused + ",threshold=" + threshold;
    }

    // Không nằm trong management contract theo annotation.
    public void applicationInternalMethod() {
        // ...
    }
}
\`\`\`

Mã trên phục vụ minh họa API quản trị; trong ứng dụng thực, logic pause/resume cần kết nối với cơ chế xử lý queue thật, bảo đảm thread safety và authorization phù hợp.

### 4.2. Cấu hình Spring JMX exporter

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    QueueAdministration queueAdministration() {
        return new QueueAdministration();
    }
}
\`\`\`

\`@EnableMBeanExport\` bật hạ tầng export JMX dựa trên annotation. Khi Spring context khởi tạo, exporter phát hiện \`QueueAdministration\` qua \`@ManagedResource\` và đăng ký MBean theo ObjectName trên annotation.

**Điều kiện môi trường:** Test phải dùng MBeanServer phù hợp với exporter. Trong một ứng dụng có nhiều MBeanServer hoặc exporter cấu hình tùy biến, không nên mặc định \`ManagementFactory.getPlatformMBeanServer()\` luôn là server thực sự chứa MBean. Ví dụ kiểm thử dưới đây sử dụng một MBeanServer riêng để tránh xung đột với platform server và chỉ rõ nơi export.

## 5. Cấu hình test với MBeanServer riêng

Để test độc lập và tránh ObjectName collision khi các test khác chạy trong cùng JVM, có thể cung cấp MBeanServer riêng cho \`@EnableMBeanExport\`.

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "testMBeanServer")
public class TestJmxConfiguration {

    @Bean(name = "testMBeanServer")
    MBeanServer testMBeanServer() {
        return MBeanServerFactory.createMBeanServer("test.jmx");
    }

    @Bean
    QueueAdministration queueAdministration() {
        return new QueueAdministration();
    }
}
\`\`\`

Trong context này, exporter phải dùng bean \`testMBeanServer\`. Test đọc server từ cùng Spring context để bảo đảm invoke vào nơi đã đăng ký.

Lưu ý: nếu một dự án đã có nhiều configuration JMX exporter, không nên import đồng thời tất cả vào test vì có thể dẫn tới đăng ký trùng hoặc cơ chế export khác mong đợi.

## 6. Integration test: gọi operation không tham số

Ví dụ dùng JUnit Jupiter (JUnit 5). Giả định dependency Spring Framework và JUnit 5 đã được cấu hình trong build.

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class QueueAdministrationJmxTest {

    private static final String MBEAN_NAME =
        "learning.jmx:type=Queue,name=Primary";

    @Test
    void pauseAndResumeAreCallableThroughMBeanServer()
            throws Exception {

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        TestJmxConfiguration.class)) {

            MBeanServer server =
                    context.getBean("testMBeanServer", MBeanServer.class);

            ObjectName name = new ObjectName(MBEAN_NAME);

            assertTrue(server.isRegistered(name));

            Object pauseResult = server.invoke(
                    name,
                    "pause",
                    new Object[0],
                    new String[0]
            );

            assertNull(pauseResult);
            assertEquals(Boolean.TRUE,
                    server.getAttribute(name, "Paused"));

            Object resumeResult = server.invoke(
                    name,
                    "resume",
                    new Object[0],
                    new String[0]
            );

            assertNull(resumeResult);
            assertEquals(Boolean.FALSE,
                    server.getAttribute(name, "Paused"));
        }
    }
}
\`\`\`

Test này kiểm tra nhiều lớp:

1. Spring context tạo managed resource và exporter.
2. MBean được đăng ký đúng ObjectName.
3. Operation \`pause\` tồn tại với signature rỗng.
4. Operation \`resume\` tồn tại với signature rỗng.
5. State quan sát qua JMX attribute thay đổi như mong đợi.

Đây là sự khác biệt so với test chỉ gọi \`QueueAdministration.pause()\` trực tiếp.

## 7. Integration test: operation có tham số

\`\`\`java
@Test
void updateThresholdAcceptsIntParameter() throws Exception {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                    TestJmxConfiguration.class)) {

        MBeanServer server =
                context.getBean("testMBeanServer", MBeanServer.class);

        ObjectName name = new ObjectName(
                "learning.jmx:type=Queue,name=Primary"
        );

        assertEquals(100, server.getAttribute(name, "Threshold"));

        Object result = server.invoke(
                name,
                "updateThreshold",
                new Object[] { 250 },
                new String[] { "int" }
        );

        assertNull(result);
        assertEquals(250, server.getAttribute(name, "Threshold"));
    }
}
\`\`\`

Các điểm kiểm chứng:

- Operation name là \`updateThreshold\`, không phải một tên tự suy đoán từ description.
- Signature dùng \`"int"\` vì Java method nhận primitive \`int\`.
- \`new Object[] { 250 }\` truyền một Integer boxed vào JMX invocation; JMX dùng signature để tìm method tương ứng.
- Giá trị trả về của operation \`void\` là \`null\`.
- Đọc lại attribute \`Threshold\` để chứng minh operation đã thay đổi state.

### Signature dễ sai ở đâu?

Giả sử client truyền:

\`\`\`java
server.invoke(
    name,
    "updateThreshold",
    new Object[] { 250 },
    new String[] { "java.lang.Integer" }
);
\`\`\`

Nếu exporter chỉ công bố operation với signature \`int\`, client có thể không tìm được operation phù hợp. Lỗi liên quan reflection/invocation tùy metadata và implementation. Test contract nên luôn đọc đúng \`MBeanOperationInfo\`, tránh đoán signature từ giá trị runtime.

## 8. Kiểm chứng metadata bằng MBeanInfo

MBean có thể được đăng ký nhưng operation mong muốn chưa được công bố do thiếu \`@ManagedOperation\`, sai assembler hoặc khác biệt cấu hình. Vì vậy nên kiểm tra metadata trước khi kết luận.

\`\`\`java
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());

    for (MBeanParameterInfo parameter : operation.getSignature()) {
        System.out.println(
            "  " + parameter.getName() + ": "
            + parameter.getType()
        );
    }
}
\`\`\`

Ví dụ test contract:

\`\`\`java
import java.util.Arrays;

boolean hasUpdateThreshold = Arrays.stream(
        server.getMBeanInfo(name).getOperations()
).anyMatch(operation ->
        "updateThreshold".equals(operation.getName())
        && operation.getSignature().length == 1
        && "int".equals(
                operation.getSignature()[0].getType()
        )
);

assertTrue(hasUpdateThreshold);
\`\`\`

Metadata là contract thực tế mà JMX client thấy sau khi Spring exporter xử lý annotations. Việc đọc \`MBeanInfo\` đặc biệt hữu ích khi code có Spring AOP proxy hoặc metadata assembler tùy biến.

## 9. Kiểm thử giá trị trả về

Một operation trả \`String\`:

\`\`\`java
@ManagedOperation
public synchronized String describeState() {
    return "paused=" + paused + ",threshold=" + threshold;
}
\`\`\`

Test:

\`\`\`java
Object result = server.invoke(
        name,
        "describeState",
        new Object[0],
        new String[0]
);

assertEquals(
        "paused=false,threshold=100",
        result
);
\`\`\`

Không cần cast nếu dùng \`assertEquals\` nhưng khi API consumer muốn xử lý kiểu rõ, có thể kiểm tra:

\`\`\`java
assertInstanceOf(String.class, result);
\`\`\`

Nếu operation trả về custom object, JMX client từ xa có thể gặp vấn đề serialization/classpath. Với management API dùng qua nhiều JVM, nên cân nhắc types đơn giản hoặc MXBean/Open Types phù hợp.

## 10. Kiểm thử lỗi từ managed operation

Lệnh \`updateThreshold(int)\` ném \`IllegalArgumentException\` khi tham số không hợp lệ.

\`\`\`java
@Test
void invalidThresholdIsRejectedThroughJmx() throws Exception {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                    TestJmxConfiguration.class)) {

        MBeanServer server =
                context.getBean("testMBeanServer", MBeanServer.class);

        ObjectName name = new ObjectName(
                "learning.jmx:type=Queue,name=Primary"
        );

        Exception error = assertThrows(
                Exception.class,
                () -> server.invoke(
                    name,
                    "updateThreshold",
                    new Object[] { -1 },
                    new String[] { "int" }
                )
        );

        assertNotNull(error);
        assertEquals(100, server.getAttribute(name, "Threshold"));
    }
}
\`\`\`

Test trên giữ phạm vi exception tương đối rộng để minh họa ý tưởng. Khi xác nhận implementation cụ thể, nên assert chính xác wrapper exception và nguyên nhân gốc.

### Cách JMX biểu diễn exception

Một số lỗi cần phân biệt:

- \`InstanceNotFoundException\`: không tìm thấy MBean theo ObjectName.
- \`ReflectionException\`: lỗi liên quan nhận diện/gọi operation qua reflection hoặc signature.
- \`MBeanException\`: wrapper cho checked exception phát sinh từ operation trong một số trường hợp.
- \`RuntimeMBeanException\`: wrapper cho runtime exception do operation/managed resource ném.
- \`RuntimeErrorException\`: có thể bọc một \`Error\` trong đường gọi MBean.

Ví dụ đối với \`IllegalArgumentException\` trong một implementation JMX tiêu chuẩn, có thể gặp \`RuntimeMBeanException\` với cause tương ứng. Nên kiểm tra exception wrapper thực tế thay vì suy đoán rằng client luôn nhận trực tiếp cùng exception Java như khi gọi method nội bộ.

Ví dụ assert tập trung vào runtime exception:

\`\`\`java
import javax.management.RuntimeMBeanException;

RuntimeMBeanException thrown = assertThrows(
    RuntimeMBeanException.class,
    () -> server.invoke(
        name,
        "updateThreshold",
        new Object[] { -1 },
        new String[] { "int" }
    )
);

assertInstanceOf(
    IllegalArgumentException.class,
    thrown.getCause()
);
\`\`\`

Khi áp dụng vào Spring-exported MBeans, hãy kiểm tra cách exporter/adaptor bọc exception trong phiên bản thực tế. Nếu exporter thay đổi wrapping semantics, test cần khớp contract quan sát được ở ranh giới JMX.

## 11. Kiểm thử operation không được export

Một lỗi cấu hình thường gặp là method public trong bean nhưng không có \`@ManagedOperation\`:

\`\`\`java
public void applicationInternalMethod() {
    // ...
}
\`\`\`

Với annotation-based metadata assembler chỉ công bố những method được chọn, method này không nên xuất hiện như JMX operation.

Cách kiểm chứng:

\`\`\`java
boolean accidentallyExposed = Arrays.stream(
        server.getMBeanInfo(name).getOperations()
).anyMatch(operation ->
        "applicationInternalMethod".equals(operation.getName())
);

assertFalse(accidentallyExposed);
\`\`\`

Đây là một **kiểm thử bề mặt quản trị** có ý nghĩa: nó chứng minh những thao tác nghiệp vụ không mong muốn không bị mở ra qua JMX.

Không nên trực tiếp gọi method rồi suy luận rằng nó đã hoặc chưa được export. Kiểm tra metadata mới phản ánh contract JMX.

## 12. Kiểm thử lifecycle: đăng ký và hủy đăng ký

Khi MBeanExporter được Spring quản lý, registration thường gắn với vòng đời của context.

Ví dụ:

\`\`\`java
@Test
void mbeanRegistrationFollowsSpringContextLifecycle()
        throws Exception {

    MBeanServer server = MBeanServerFactory.createMBeanServer(
            "isolated.lifecycle"
    );

    ObjectName name = new ObjectName(
            "learning.jmx:type=Queue,name=Primary"
    );

    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

    context.registerBean(
            "testMBeanServer",
            MBeanServer.class,
            () -> server
    );
    context.register(TestJmxConfiguration.class);

    try {
        context.refresh();
        assertTrue(server.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(server.isRegistered(name));
}
\`\`\`

**Lưu ý kỹ thuật:** Trong các cấu hình test đơn giản, tránh đăng ký hai bean MBeanServer trùng tên nếu \`TestJmxConfiguration\` cũng khai báo \`testMBeanServer\`. Chọn **một** nơi tạo/đưa MBeanServer vào context. Ví dụ trên minh họa ý tưởng injection server; nếu dùng TestJmxConfiguration nguyên vẹn ở phần 5, hãy chỉ lấy server từ context đó trước khi đóng.

Một biến thể nhất quán và gọn hơn:

\`\`\`java
@Test
void unexportsOnContextClose() throws Exception {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                    TestJmxConfiguration.class
            );

    MBeanServer server =
            context.getBean("testMBeanServer", MBeanServer.class);

    ObjectName name = new ObjectName(
            "learning.jmx:type=Queue,name=Primary"
    );

    try {
        assertTrue(server.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(server.isRegistered(name));
}
\`\`\`

Chỉ dùng một trong các biến thể phù hợp với cấu hình thật. Trường hợp lifecycle đặc biệt quan trọng nếu test tạo nhiều Spring context trong cùng JVM: không đóng context có thể để lại đăng ký và gây ObjectName collision ở lần chạy kế tiếp.

## 13. Đọc thông tin operation từ MBeanServerConnection

Một custom client ở JVM khác thường dùng \`MBeanServerConnection\`, không có cùng đối tượng \`MBeanServer\` trong memory.

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteOperationClient {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
        );

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "learning.jmx:type=Queue,name=Primary"
            );

            Object result = connection.invoke(
                name,
                "describeState",
                new Object[0],
                new String[0]
            );

            System.out.println(result);
        }
    }
}
\`\`\`

Đây là ví dụ khung cho môi trường quản trị đã được cấu hình. Hostname chỉ là placeholder và kết nối yêu cầu server JMX remote thực sự hoạt động, mạng cho phép, credentials và TLS/quyền truy cập phù hợp. Không bật remote JMX không xác thực trong môi trường chia sẻ.

**Khác biệt quan trọng:** \`MBeanServerConnection\` cho phép client gọi cùng contract từ xa. Integration test trong cùng JVM xác nhận mapping và chức năng nhưng **không chứng minh** remote connector, mạng, auth, TLS hay chính sách quyền đã cấu hình đúng. Nếu yêu cầu triển khai cần remote JMX, bổ sung kiểm thử connectivity và authorization trong môi trường phù hợp.

## 14. Đường kiểm tra khi operation không gọi được

Khi gặp lỗi:

\`\`\`text
Operation updateThreshold not found
\`\`\`

hãy kiểm tra theo thứ tự:

1. **ObjectName có đúng?** Dùng \`server.isRegistered(name)\`.
2. **MBeanServer có đúng?** Test có đang dùng cùng server mà exporter đăng ký không?
3. **Operation có trong metadata không?** Dùng \`getMBeanInfo(name).getOperations()\`.
4. **Tên operation có chính xác?** JMX sử dụng tên method được export, phân biệt chữ hoa/thường.
5. **Signature có đúng?** Primitive \`int\` khác \`java.lang.Integer\`.
6. **Tham số có đúng số lượng và kiểu?** \`params.length\` phải tương ứng với \`signature.length\`.
7. **Method có được annotate?** Kiểm tra \`@ManagedOperation\` và assembler/exporter.
8. **Bean có AOP proxy không?** Kiểm tra metadata/proxy class nếu method không xuất hiện.
9. **Có bị lỗi do operation thực thi không?** Nếu metadata và signature đúng nhưng invoke vẫn lỗi, xem wrapper exception và cause.
10. **JMX client có quyền gọi không?** Với kết nối từ xa, permission/authorization có thể chặn operation.

### Một số nhầm lẫn phổ biến

**“Method public là JMX operation.”** Không chắc. Trong annotation-based Spring JMX, metadata assembler quyết định method nào được công bố.

**“Unit test gọi method trực tiếp là đủ.”** Không đủ để kiểm tra ObjectName, exporter, metadata và signature.

**“Operation không tham số phải truyền null.”** API cho phép một số dạng gọi null tùy triển khai, nhưng mảng rỗng giúp test rõ nghĩa và nhất quán.

**“Operation Java nhận int nên signature phải dùng Integer.”** Sai khi khai báo primitive \`int\`: tên kiểu trong signature là \`"int"\`.

**“Đăng ký MBean thành công thì mọi method sẽ gọi được.”** Registration thành công chỉ chứng minh MBean hợp lệ; cần xác nhận từng operation được expose đúng.

## 15. Kiểm thử song song và isolation

JMX platform MBeanServer là tài nguyên cấp JVM. Nếu nhiều test cùng đăng ký ObjectName giống nhau vào platform server, chúng có thể xung đột.

Các cách giảm xung đột:

- Dùng MBeanServer riêng cho integration test như ví dụ.
- Dùng ObjectName riêng theo phạm vi test nếu thật sự cần chung server.
- Đóng ApplicationContext ở cuối test.
- Không dùng RegistrationPolicy.REPLACE_EXISTING để che việc test đang ghi đè MBean thuộc test khác.
- Tránh tạo quá nhiều MBeanServer mà không cleanup, đặc biệt khi chạy nhiều test trong cùng JVM.
- Khi tự tạo MBeanServer qua factory, có thể dùng \`MBeanServerFactory.releaseMBeanServer(server)\` sau khi context đã đóng và không còn consumer, nếu server được đăng ký trong factory và thuộc quyền test.

Nếu test chạy trong cấu hình Spring Boot có Actuator JMX, chú ý exporter tự động của Boot có thể khác cấu hình thủ công. Nên cô lập cấu hình thử nghiệm để chỉ một exporter sở hữu ObjectName đang kiểm thử.

## 16. Kiểm thử giá trị và tác dụng phụ an toàn

Đối với một operation quản trị, test nên xác minh cả **kết quả gọi** và **thay đổi trạng thái**.

Ví dụ pause queue:

\`\`\`java
server.invoke(name, "pause", new Object[0], new String[0]);

assertEquals(
    Boolean.TRUE,
    server.getAttribute(name, "Paused")
);
\`\`\`

Đối với operations có tác dụng phụ thật như xóa cache, restart thread hoặc thay đổi cấu hình, không nên gọi lên production instance chỉ để test. Dùng test fixture có side effects kiểm soát được.

Cần kiểm tra:

- Operation có idempotent không?
- Gọi lại nhiều lần có nguy cơ gây lỗi không?
- Khi tham số sai, trạng thái có được giữ nguyên không?
- Operation có cần authorization và audit không?
- Kết quả trả về có dễ serialize cho JMX client không?
- Điều gì xảy ra khi bean đang trong quá trình shutdown?

Các câu hỏi này thuộc contract quản trị, vượt ra ngoài unit test đơn thuần.

## 17. Mẫu checklist integration test

Một bài test gọi operation qua MBeanServer nên trả lời:

| Kiểm tra | Kỳ vọng |
|---|---|
| Context tạo thành công | Exporter chạy không lỗi |
| ObjectName có đăng ký | \`isRegistered(name) == true\` |
| Operation xuất hiện | \`MBeanInfo\` có tên mong đợi |
| Signature đúng | Tên/kiểu và thứ tự tham số khớp |
| Invoke thành công | Không ném exception ngoài mong đợi |
| Giá trị trả về | Khớp kiểu/giá trị contract |
| Tác dụng phụ | Attribute hoặc trạng thái phản ánh thay đổi |
| Đối số sai | Lỗi được bọc/biểu diễn nhất quán |
| Method nội bộ | Không bị export ngoài ý muốn |
| Sau context.close | MBean do exporter quản lý được unregister |
| Test isolation | Không ghi đè MBeans của test/ứng dụng khác |

Bạn không cần biến mọi operation thành một bộ test khổng lồ. Đối với management API quan trọng, hãy kiểm tra các contract có khả năng phá tương thích khi đổi tên, kiểu tham số hoặc metadata.

## 18. Bài tập thực hành

### Bài tập A — Viết operation tăng bộ đếm

Tạo \`CounterAdministration\` có:

\`\`\`java
@ManagedAttribute
public int getCount() { ... }

@ManagedOperation
public void increment() { ... }
\`\`\`

Viết test:

1. Tạo Spring context và exporter.
2. Kiểm tra ObjectName đã đăng ký.
3. Đọc \`Count\` ban đầu.
4. Gọi \`increment\` qua \`MBeanServer.invoke\`.
5. Đọc lại \`Count\` và xác nhận tăng một.

### Bài tập B — Operation có hai tham số

Tạo:

\`\`\`java
@ManagedOperation
public int multiply(int left, int right) {
    return left * right;
}
\`\`\`

Lệnh invoke mong đợi:

\`\`\`java
Object value = server.invoke(
    name,
    "multiply",
    new Object[] { 6, 7 },
    new String[] { "int", "int" }
);
\`\`\`

Kiểm tra kết quả bằng \`assertEquals(42, value)\`.

Thử đổi signature phần tử thứ hai thành \`java.lang.Integer\` và xem lỗi; đối chiếu với MBeanInfo để giải thích.

### Bài tập C — Method không được annotate

Thêm public method \`deleteAllData()\` vào managed bean nhưng không annotate nó. Dùng \`getMBeanInfo\` kiểm tra method này không được công bố.

### Bài tập D — Ngăn tham số không hợp lệ

Tạo operation \`updateThreshold(int)\` ném \`IllegalArgumentException\` nếu giá trị âm. Gọi qua JMX với \`-1\`, quan sát exception wrapper và xác nhận threshold cũ không đổi.

### Bài tập E — Lifecycle

Tạo context, xác nhận MBean tồn tại; đóng context, xác nhận MBean biến mất. Sau đó tạo lại context mới và kiểm tra export không bị trùng ObjectName.

## 19. Tổng kết

Kiểm thử **gọi operation qua MBeanServer** là kiểm thử một contract quản trị, không chỉ kiểm thử method Java.

Điểm cần ghi nhớ:

1. \`@ManagedOperation\` công bố method theo Spring JMX metadata.
2. \`MBeanServer.invoke\` cần đúng ObjectName, operation name, params và signature.
3. \`MBeanInfo\` là nguồn kiểm chứng tên và kiểu operation được export.
4. Nên kiểm tra cả kết quả trả về, trạng thái sau thao tác và cách lỗi được biểu diễn.
5. Dùng MBeanServer riêng và đóng context để test độc lập, tránh ObjectName collision.
6. Test local invoke không thay thế kiểm tra remote JMX connector, bảo mật và mạng.
7. Không công bố hoặc gọi thao tác nguy hiểm chỉ vì một method là public.
8. Khi refactor tên method, kiểu tham số hoặc exporter configuration, cần bảo vệ contract mà JMX client đang sử dụng.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Spring Framework API — EnableMBeanExport: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — MBeanOperationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
