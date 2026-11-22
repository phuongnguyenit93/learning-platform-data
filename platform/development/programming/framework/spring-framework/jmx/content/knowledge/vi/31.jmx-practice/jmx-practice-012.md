# Viết kiểm thử xác nhận management interface trong Spring Framework JMX

## Mục tiêu thực hành

Management interface là hợp đồng giữa một MBean và các công cụ quản trị sử dụng JMX. Khi ứng dụng Spring Framework export bean, không nên chỉ xác nhận rằng ứng dụng khởi động được hoặc JConsole hiển thị một ObjectName. Cần kiểm thử chính xác **attribute nào đọc/ghi được, operation nào được phép gọi, kiểu tham số nào được hỗ trợ, method nội bộ nào không được công bố và registration có được dọn dẹp khi context đóng hay không**.

Bài thực hành xây dựng một Standard MBean nhỏ, viết unit/integration tests với JUnit 5 và MBeanServer, rồi mở rộng sang Spring MBeanExporter. Các test tập trung vào hợp đồng runtime do MBeanServer công bố, không chỉ vào Java reflection. Mục tiêu cuối cùng là có một bộ test chạy ổn định trên CI, phát hiện breaking changes hoặc tình huống vô tình xuất thêm operation nhạy cảm.

Sau bài này, bạn có thể:

- Tạo interface Standard MBean đúng quy tắc đặt tên.
- Viết management implementation với public methods ngoài interface.
- Đăng ký MBean trên server riêng cho test.
- Kiểm tra ObjectName, MBeanInfo, attributes, operations và parameter signatures.
- Đọc một attribute và gọi operation qua MBeanServerConnection.
- Xác nhận public method không có trong management interface không được export.
- Kiểm tra read-only attribute không thể ghi qua JMX.
- Viết Spring integration test cho MBeanExporter lifecycle.
- Kiểm soát cleanup và tránh xung đột ObjectName khi test chạy song song.
- Thiết kế negative contract tests cho thay đổi phiên bản.

## 1. Bài toán

Giả sử hệ thống có một worker xử lý công việc. Nhóm vận hành chỉ cần:

1. Đọc trạng thái worker.
2. Đọc tổng số job hoàn tất.
3. Đọc số job lỗi.
4. Gửi yêu cầu tạm dừng.
5. Gửi yêu cầu tiếp tục.

Trong implementation vẫn có các method nội bộ như \`deleteCheckpoint\` hoặc \`rebuildInternalIndex\`, nhưng những method này **không được lộ ra JMX**.

Hợp đồng:

\`\`\`text
WorkerRuntimeMBean
├── State                 [read-only attribute]
├── CompletedCount        [read-only attribute]
├── FailedCount           [read-only attribute]
├── requestPause()        [operation]
└── requestResume()       [operation]

WorkerRuntime implementation:
├── Các method trong management interface
├── deleteCheckpoint(id)  [public Java method, không export]
└── rebuildInternalIndex()[public Java method, không export]
\`\`\`

Yêu cầu kiểm thử:

| Nhóm | Điều kiện phải đúng |
|---|---|
| Registration | ObjectName được đăng ký |
| Metadata | Attribute State, CompletedCount, FailedCount có mặt |
| Read-only | Không attribute nào ở trên writable |
| Operations | requestPause và requestResume có mặt, không có tham số |
| Không lộ method nội bộ | Không có deleteCheckpoint/rebuildInternalIndex |
| Behavior | Invoke requestPause thay đổi effective state phù hợp |
| Cleanup | Unregister xong không còn ObjectName |
| Spring lifecycle | Đóng ApplicationContext gỡ MBean do exporter sở hữu |

## 2. Công cụ và cấu trúc mẫu

Dự án có thể dùng Java 17+, Spring Framework và JUnit Jupiter.

Ví dụ Maven dependencies cho test:

\`\`\`xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
        <version>\${spring.version}</version>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>\${junit.jupiter.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
\`\`\`

Đây là fragment dependency, không phải POM hoàn chỉnh. Trong dự án thật, sử dụng dependency management và phiên bản tương thích của tổ chức, đồng thời cấu hình Surefire/JUnit Platform phù hợp. Java Management APIs như \`javax.management.MBeanServer\` thuộc JDK module \`java.management\`, không phải một thư viện JMX tùy ý cần tải từ Maven.

Cấu trúc:

\`\`\`text
src/main/java/com/example/jmx/
  WorkerRuntimeMBean.java
  WorkerRuntime.java
  ManagementConfiguration.java

src/test/java/com/example/jmx/
  WorkerRuntimeMBeanContractTest.java
  SpringJmxExportTest.java
\`\`\`

Trong test đơn giản không cần khởi động remote connector, vì \`MBeanServer\` local đã đủ để kiểm tra management contract. Kiểm thử authentication/TLS remote JMX nên thuộc một bộ test khác.

## 3. Viết Standard MBean interface

\`\`\`java
package com.example.jmx;

public interface WorkerRuntimeMBean {

    String getState();

    long getCompletedCount();

    long getFailedCount();

    void requestPause();

    void requestResume();
}
\`\`\`

Theo quy ước Standard MBean, implementation \`WorkerRuntime\` phù hợp với interface \`WorkerRuntimeMBean\`. Những method \`getXxx()\` không tham số thường được JMX introspection công bố như attributes; những method điều khiển được công bố như operations.

Điểm quan trọng: interface **chỉ định member được phép quản trị**. Không thêm service methods như \`deleteCheckpoint\` vào interface chỉ vì chúng đã public trong Java.

## 4. Implementation: tách management API và public internal API

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public final class WorkerRuntime implements WorkerRuntimeMBean {

    private volatile String state = "RUNNING";
    private final AtomicLong completedCount = new AtomicLong();
    private final AtomicLong failedCount = new AtomicLong();

    @Override
    public String getState() {
        return state;
    }

    @Override
    public long getCompletedCount() {
        return completedCount.get();
    }

    @Override
    public long getFailedCount() {
        return failedCount.get();
    }

    @Override
    public void requestPause() {
        state = "PAUSED";
    }

    @Override
    public void requestResume() {
        state = "RUNNING";
    }

    // Internal Java API. KHÔNG thuộc WorkerRuntimeMBean.
    public void deleteCheckpoint(String checkpointId) {
        // Trong ứng dụng thật: thao tác nhạy cảm cần giới hạn.
    }

    // Public method phục vụ logic nội bộ, KHÔNG xuất qua JMX contract.
    public void rebuildInternalIndex() {
        // Không dùng operation JMX.
    }

    public void onCompleted() {
        completedCount.incrementAndGet();
    }

    public void onFailed() {
        failedCount.incrementAndGet();
    }
}
\`\`\`

Trong ví dụ, pause/resume cập nhật trạng thái ngay để test đơn giản. Với worker thực tế, \`requestPause()\` thường chỉ ghi requested state, còn effective state đổi sau khi worker dừng nhận công việc. Khi đó test phải kiểm tra đúng semantics của operation: \`ACCEPTED\` không đồng nghĩa \`PAUSED\` ngay lập tức.

Không dùng \`public final class\` ở trên rồi kỳ vọng Spring class-based AOP proxy có thể subclass nó. Bài test Standard MBean trực tiếp không cần proxy. Nếu sau này muốn AOP trên implementation, phải đánh giá thiết kế adapter và proxy strategy.

## 5. Tạo MBeanServer riêng cho test

JMX cung cấp:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server = MBeanServerFactory.newMBeanServer();
\`\`\`

\`newMBeanServer()\` tạo một server test độc lập và không đăng ký nó trong danh sách server được factory theo dõi như \`createMBeanServer()\`. Đây là cách phù hợp để tránh va chạm với platform MBeanServer đang được test khác dùng.

Đăng ký:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.test:type=WorkerRuntime,name=Contract");

WorkerRuntime worker = new WorkerRuntime();
server.registerMBean(worker, name);
\`\`\`

Test cần cleanup để không giữ registration ngoài phạm vi fixture. Với server riêng mỗi test, rủi ro tác động đến test khác giảm, nhưng vẫn nên unregister rõ ràng để kiểm tra lifecycle và giữ thói quen ownership.

## 6. Test 1 — Xác nhận ObjectName được đăng ký

\`\`\`java
package com.example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class WorkerRuntimeMBeanContractTest {

    @Test
    void registersAsStandardMBean() throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.test:type=WorkerRuntime,name=Contract");

        server.registerMBean(new WorkerRuntime(), name);

        try {
            assertTrue(server.isRegistered(name));
            assertNotNull(server.getMBeanInfo(name));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

\`isRegistered\` xác minh registry entry tồn tại, còn \`getMBeanInfo\` cho biết server có introspection metadata của MBean. Tuy nhiên hai assertion này chưa chứng minh member nào được công bố, nên cần các test tiếp theo.

## 7. Test 2 — Xác nhận attributes qua MBeanInfo

Có thể đọc metadata:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

MBeanInfo info = server.getMBeanInfo(name);

Map<String, MBeanAttributeInfo> attributes =
    java.util.Arrays.stream(info.getAttributes())
        .collect(Collectors.toMap(
            MBeanAttributeInfo::getName,
            Function.identity()
        ));

assertTrue(attributes.containsKey("State"));
assertTrue(attributes.containsKey("CompletedCount"));
assertTrue(attributes.containsKey("FailedCount"));

assertTrue(attributes.get("State").isReadable());
assertFalse(attributes.get("State").isWritable());

assertEquals(
    "long",
    attributes.get("CompletedCount").getType());
assertFalse(attributes.get("CompletedCount").isWritable());
\`\`\`

Kiểm tra read-only flags rất quan trọng. Một class Java có thể có public setter dùng nội bộ; nếu setter không thuộc management interface, nó không nên tự biến JMX attribute thành writable trong Standard MBean contract tương ứng.

### 7.1 Test chính xác tập attributes

Nếu hợp đồng không cho phép thêm attribute, dùng set equality:

\`\`\`java
Set<String> names = java.util.Arrays.stream(
    info.getAttributes())
    .map(MBeanAttributeInfo::getName)
    .collect(Collectors.toSet());

assertEquals(
    Set.of("State", "CompletedCount", "FailedCount"),
    names);
\`\`\`

Kiểm tra exact set có ưu điểm phát hiện attributes mới được công bố ngoài kế hoạch. Trong hệ thống có metadata từ custom assembler hoặc interface kế thừa, cần xác định contract mong muốn và cập nhật test khi thay đổi có chủ đích.

## 8. Test 3 — Xác nhận operations và signatures

Một operation JMX có name, return type và parameter signature. Để kiểm tra:

\`\`\`java
import javax.management.MBeanOperationInfo;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

MBeanOperationInfo[] operations = info.getOperations();

Set<String> operationNames = Arrays.stream(operations)
    .map(MBeanOperationInfo::getName)
    .collect(Collectors.toSet());

assertEquals(
    Set.of("requestPause", "requestResume"),
    operationNames);

for (MBeanOperationInfo operation : operations) {
    assertEquals(0, operation.getSignature().length);
    assertEquals("void", operation.getReturnType());
}
\`\`\`

Đây là test chặt cho management contract không tham số. Khi một operation có overload, chỉ so sánh tên là chưa đủ; hai overload có thể cùng tên nhưng signature khác nhau. Một test tổng quát nên lưu khóa \`(operationName, listOfParameterTypes, returnType)\`.

### 8.1 Helper kiểm tra operation cụ thể

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import java.util.Arrays;

static boolean hasOperation(
        MBeanInfo info,
        String operationName,
        String... signature) {

    return Arrays.stream(info.getOperations())
        .filter(op -> op.getName().equals(operationName))
        .anyMatch(op -> {
            MBeanParameterInfo[] parameters = op.getSignature();

            if (parameters.length != signature.length) {
                return false;
            }

            for (int i = 0; i < parameters.length; i++) {
                if (!parameters[i].getType().equals(signature[i])) {
                    return false;
                }
            }
            return true;
        });
}
\`\`\`

Ví dụ:

\`\`\`java
assertTrue(hasOperation(info, "requestPause"));
assertFalse(hasOperation(info, "deleteCheckpoint", "java.lang.String"));
\`\`\`

Với primitive, signature phải dùng tên primitive như \`"int"\` thay vì \`"java.lang.Integer"\` nếu đó là kiểu khai báo. Không tự suy đoán signature từ object wrapper phía client.

## 9. Test 4 — Public methods nội bộ phải bị ẩn

Đây là negative contract test quan trọng:

\`\`\`java
Set<String> exposed = Arrays.stream(info.getOperations())
    .map(MBeanOperationInfo::getName)
    .collect(Collectors.toSet());

assertFalse(exposed.contains("deleteCheckpoint"));
assertFalse(exposed.contains("rebuildInternalIndex"));
assertFalse(exposed.contains("onCompleted"));
assertFalse(exposed.contains("onFailed"));
\`\`\`

Các method này là public Java methods, nhưng không thuộc \`WorkerRuntimeMBean\`. Standard MBean contract phải ẩn chúng khỏi JMX.

Test này có giá trị bảo mật: một refactor hoặc thay đổi exporter/assembler có thể vô tình phơi bày operation có tác dụng phụ. Nếu test chỉ kiểm tra \`requestPause\` vẫn tồn tại, nó có thể bỏ sót bề mặt quản trị đã mở rộng ngoài kế hoạch.

**Không nhầm “ẩn khỏi JMX” với kiểm soát quyền ở mọi kênh**. Method \`deleteCheckpoint\` vẫn có thể được gọi từ Java code có reference tới object; cần security boundary riêng nếu có REST, message handler hoặc control plane khác.

## 10. Test 5 — Đọc attribute thực tế

Metadata đúng chưa chắc implementation hoạt động đúng. Gọi qua \`MBeanServer\`:

\`\`\`java
import javax.management.MBeanServerConnection;

MBeanServerConnection connection = server;

Object state = connection.getAttribute(name, "State");
Object completed = connection.getAttribute(name, "CompletedCount");

assertEquals("RUNNING", state);
assertEquals(0L, completed);
\`\`\`

Trong Java, \`MBeanServer\` extends \`MBeanServerConnection\`, vì vậy có thể dùng server local như connection. Điều này giúp bộ test gần với hành vi của remote JMX client mà chưa cần network connector.

Nếu \`getAttribute\` gặp \`AttributeNotFoundException\`, cần xem \`MBeanInfo\` thay vì chỉ kiểm tra có getter tên \`getState()\` trong Java class. JMX attribute name thường là \`"State"\`, không phải \`"getState"\`.

## 11. Test 6 — Invoke operation qua JMX runtime

\`\`\`java
connection.invoke(
    name,
    "requestPause",
    new Object[0],
    new String[0]
);

assertEquals(
    "PAUSED",
    connection.getAttribute(name, "State"));

connection.invoke(
    name,
    "requestResume",
    new Object[0],
    new String[0]
);

assertEquals(
    "RUNNING",
    connection.getAttribute(name, "State"));
\`\`\`

Việc gọi \`worker.requestPause()\` trực tiếp chỉ test Java implementation. Lời gọi qua \`connection.invoke()\` kiểm tra thêm JMX operation dispatch, ObjectName và signature.

Trong ứng dụng thật, operation có thể bất đồng bộ. Khi đó cần test \`RequestedState\` và \`EffectiveState\` riêng, sử dụng latch hoặc polling có deadline thay vì assert tức thời. Một response accepted không đồng nghĩa worker đã dừng hoàn toàn.

## 12. Test 7 — Attribute read-only không được set

\`\`\`java
import javax.management.Attribute;
import javax.management.AttributeNotFoundException;

assertThrows(
    AttributeNotFoundException.class,
    () -> connection.setAttribute(
        name,
        new Attribute("CompletedCount", 100L)
    )
);
\`\`\`

Đối với Standard MBean read-only attribute, thao tác set thường bị từ chối bằng \`AttributeNotFoundException\` theo JMX API. Với custom MBean hoặc đường invocation khác, exception có thể được bọc tùy implementation. Nên kiểm tra trước \`MBeanAttributeInfo.isWritable()==false\`, sau đó kiểm thử behavior được hỗ trợ bởi server thực tế.

Đừng tạo test sửa state quan trọng trên production chỉ để chứng minh quyền. Dùng MBean test vô hại.

## 13. Một test fixture có setup và cleanup tập trung

Để tránh lặp code, dùng JUnit lifecycle:

\`\`\`java
package com.example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import javax.management.*;
import org.junit.jupiter.api.*;

class WorkerRuntimeContractTest {

    private MBeanServer server;
    private ObjectName objectName;

    @BeforeEach
    void setUp() throws Exception {
        server = MBeanServerFactory.newMBeanServer();
        objectName = new ObjectName(
            "com.example.test:type=WorkerRuntime,name=Contract");

        server.registerMBean(new WorkerRuntime(), objectName);
    }

    @AfterEach
    void tearDown() throws Exception {
        if (server != null &&
                server.isRegistered(objectName)) {
            server.unregisterMBean(objectName);
        }
    }

    @Test
    void exposesOnlyExpectedAttributes() throws Exception {
        MBeanInfo info = server.getMBeanInfo(objectName);

        Set<String> attributes =
            Arrays.stream(info.getAttributes())
                .map(MBeanAttributeInfo::getName)
                .collect(Collectors.toSet());

        assertEquals(
            Set.of("State", "CompletedCount", "FailedCount"),
            attributes);
    }

    @Test
    void hidesInternalOperations() throws Exception {
        MBeanInfo info = server.getMBeanInfo(objectName);

        Set<String> names =
            Arrays.stream(info.getOperations())
                .map(MBeanOperationInfo::getName)
                .collect(Collectors.toSet());

        assertFalse(names.contains("deleteCheckpoint"));
        assertFalse(names.contains("rebuildInternalIndex"));
        assertTrue(names.contains("requestPause"));
    }
}
\`\`\`

Ví dụ cần imports cho \`Arrays\`, \`Set\` và \`Collectors\` khi đưa vào dự án. Việc tạo server mới trong mỗi test cho phép dùng cùng ObjectName mà không gây collision giữa các fixture. Cleanup giữ thói quen lifecycle tốt dù server test không được chia sẻ.

### 13.1 Nếu đăng ký thất bại ở @BeforeEach

Khi \`server.registerMBean\` ném exception trước khi hoàn tất setup, \`@AfterEach\` vẫn cần chịu được trạng thái chưa đăng ký. Kiểm tra \`server != null\`, \`objectName != null\` và \`isRegistered\` nếu cần; hoặc dùng \`try/finally\` trong từng test có scope rõ.

Không viết cleanup unregister theo domain wildcard như \`com.example.test:*\` trên platform server chia sẻ, vì có thể xóa MBean của test khác.

## 14. Viết integration test với Spring MBeanExporter

Standard MBean test trực tiếp chưa chứng minh Spring configuration đúng. Cần test cả exporter.

Ví dụ Java configuration:

\`\`\`java
package com.example.jmx;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ManagementConfiguration {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer();
    }

    @Bean
    public WorkerRuntime workerRuntime() {
        return new WorkerRuntime();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MBeanServer testMBeanServer,
            WorkerRuntime workerRuntime) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setAutodetect(false);
        exporter.setBeans(Map.of(
            "com.example.test:type=WorkerRuntime,name=Spring",
            workerRuntime
        ));
        return exporter;
    }
}
\`\`\`

Spring exporter có quyền đăng ký danh sách này khi context khởi tạo và unregister những registration mà exporter sở hữu khi context đóng. Không nên đồng thời bật \`@EnableMBeanExport\` nếu một annotation exporter khác sẽ quét trùng bean dưới cùng ObjectName.

## 15. Test Spring context lifecycle

\`\`\`java
package com.example.jmx;

import static org.junit.jupiter.api.Assertions.*;
import javax.management.*;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SpringJmxExportTest {

    @Test
    void exporterRegistersAndUnregistersMBean() throws Exception {
        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                ManagementConfiguration.class);

        MBeanServer server = context.getBean(MBeanServer.class);
        ObjectName name = new ObjectName(
            "com.example.test:type=WorkerRuntime,name=Spring");

        try {
            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);
            assertNotNull(info);

            assertEquals(
                "RUNNING",
                server.getAttribute(name, "State"));
        } finally {
            context.close();
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

Điểm cần test:
1. Spring context khởi tạo được.
2. Exporter đúng server và ObjectName.
3. MBeanInfo phản ánh contract.
4. Attribute có thể đọc.
5. Khi context đóng, registration được gỡ.

Nếu muốn kiểm tra lifecycle độc lập của nhiều context dùng shared MBeanServer, cần fixture riêng chứng minh đóng context A không xóa MBean của B. Không cần mở remote JMX connector trong test này.

## 16. Test annotation-driven management interface

Nếu dự án dùng Spring annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.test:type=Worker,name=Annotated")
public class AnnotatedWorkerMonitor {

    @ManagedAttribute
    public String getState() {
        return "RUNNING";
    }

    @ManagedOperation
    public void requestPause() {
        // Demo.
    }

    public void deleteInternalCheckpoint() {
        // Không được annotation, không nên xuất qua metadata assembler.
    }
}
\`\`\`

Dùng \`@EnableMBeanExport\` hoặc \`AnnotationMBeanExporter\` đúng cấu hình, sau đó test \`MBeanInfo\` của ObjectName đã định. Với annotation-driven export, việc method không có \`@ManagedOperation\` bị ẩn là kết quả của metadata selection, không phải Standard MBean interface.

Nên có test riêng để bảo đảm:
- \`State\` readable.
- \`requestPause\` có mặt.
- \`deleteInternalCheckpoint\` vắng mặt.
- Không có writable attributes bất ngờ.
- Context shutdown cleanup đúng.

Nếu cùng bean được export bởi assembler khác, chỉ bỏ annotation không bảo đảm method biến mất. Test metadata runtime vẫn là bằng chứng cuối cùng.

## 17. Negative contract test khi đổi management interface

Giả sử một developer vô tình thêm:

\`\`\`java
public interface WorkerRuntimeMBean {
    String getState();
    long getCompletedCount();
    long getFailedCount();
    void requestPause();
    void requestResume();
    void deleteCheckpoint(String id); // Thay đổi nguy hiểm.
}
\`\`\`

Một test chỉ assert \`requestPause\` tồn tại vẫn PASS. Nhưng test set equality:

\`\`\`java
Set<String> operationNames =
    Arrays.stream(info.getOperations())
        .map(MBeanOperationInfo::getName)
        .collect(Collectors.toSet());

assertEquals(
    Set.of("requestPause", "requestResume"),
    operationNames);
\`\`\`

sẽ FAIL và yêu cầu review thay đổi management contract. Đây là lợi ích chính của negative contract test: **phát hiện bề mặt JMX tăng ngoài kế hoạch**.

Đối với một dự án có nhiều MBean, có thể lưu contract snapshot ở dạng dữ liệu test có version, nhưng tránh cập nhật snapshot tự động khi test fail mà chưa xem operation mới có tác dụng phụ không.

## 18. Kiểm tra operation có tham số và overload

Một MBean phức tạp có thể công bố:

\`\`\`java
void setConcurrency(int size);
String describeWorker(String workerId);
\`\`\`

Test signature:

\`\`\`java
assertTrue(
    hasOperation(info, "setConcurrency", "int"));

assertTrue(
    hasOperation(
        info, "describeWorker", "java.lang.String"));
\`\`\`

Gọi:

\`\`\`java
server.invoke(
    name,
    "setConcurrency",
    new Object[]{Integer.valueOf(4)},
    new String[]{"int"}
);
\`\`\`

Tham số \`Object[]\` chứa \`Integer\` wrapper vì Java không đưa primitive trực tiếp vào Object array. Nhưng JMX signature phải mô tả kiểu tham số khai báo là \`"int"\`. Nếu method overloaded, test phải kiểm tra từng signature, không chỉ operation name.

Với MXBean, kiểu dữ liệu có thể được map sang Open Types; test nên đọc \`MBeanInfo\` thay vì suy ra mọi kiểu giống Standard MBean.

## 19. MBeanServerConnection và remote test

Các test local sử dụng \`MBeanServer\`, vốn cũng là \`MBeanServerConnection\`. Để kiểm tra remote client, cần start \`JMXConnectorServer\` trong fixture, kết nối bằng \`JMXConnectorFactory\`, rồi assert cùng contract trên \`MBeanServerConnection\`.

Một test remote sẽ bổ sung:
- Service URL hợp lệ.
- Registry/connector startup.
- Authentication/TLS khi môi trường yêu cầu.
- Port management và firewall/network test.
- Connector cleanup.
- Serialization và error behavior.

Không cần chạy remote connector cho mọi contract test; sẽ khiến CI chậm và dễ flaky. Hãy giữ local contract tests nhanh, remote integration tests cho đường kết nối và security riêng.

## 20. Test về AOP proxy

Nếu MBean implementation bị proxy bởi Spring AOP, introspection có thể thay đổi. Một test nên xác nhận:

\`\`\`java
Object bean = context.getBean("workerRuntime");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

Với JDK dynamic proxy, cần xác định management interface có được expose không. Với class-based proxy, cần xem method/final class limitations. Đừng chỉ test target class implement interface rồi cho rằng proxy object export đúng.

Một management adapter riêng thường làm JMX contract ổn định hơn khi domain service có \`@Transactional\`, \`@Async\` hoặc tracing advice. Nếu operation điều khiển gọi service, nên kiểm tra lời gọi đi qua Spring proxy để advice không bị bypass.

## 21. Phân biệt contract và behavior test

| Loại test | Câu hỏi |
|---|---|
| Java unit test | Method implementation có hoạt động đúng? |
| JMX metadata contract test | Attribute/operation nào thực sự được export? |
| JMX invocation test | Client có thể đọc/gọi bằng ObjectName và signature đúng không? |
| Spring integration test | Context/exporter có register và unregister đúng? |
| Proxy test | Proxy làm thay đổi management contract không? |
| Remote connector test | URL, auth, TLS và transport có hoạt động đúng? |
| Security test | Client không có quyền có bị chặn không? |
| Load test | Getter có nhẹ và ổn định khi polling không? |

Không thể thay thế toàn bộ bằng một test duy nhất. Một test qua \`server.getAttribute()\` không chứng minh remote TLS hoạt động; một test remote kết nối thành công không chứng minh method nội bộ không bị công bố.

## 22. Các lỗi thường gặp khi viết test

### 22.1 Chỉ test direct Java method

\`\`\`java
worker.requestPause();
assertEquals("PAUSED", worker.getState());
\`\`\`

Test này không kiểm tra MBeanServer/ObjectName, nên không phát hiện exporter thiếu operation hoặc signature sai.

### 22.2 Chỉ kiểm tra ObjectName tồn tại

\`\`\`java
assertTrue(server.isRegistered(name));
\`\`\`

Không đủ; cần kiểm tra MBeanInfo, attributes và operations.

### 22.3 Dùng platform MBeanServer với ObjectName cố định

Test có thể xung đột với test khác hoặc ứng dụng đang chạy. Ưu tiên server test riêng hoặc namespace duy nhất, không unregister toàn domain.

### 22.4 Assert số lượng operation nhưng không kiểm tra tên

Hai tập operation khác nhau có thể có cùng số lượng. Dùng exact set, kèm signatures.

### 22.5 Test chỉ kiểm tra member cần có

Có thể bỏ sót operation nguy hiểm mới được export. Thêm negative contract assertions.

### 22.6 Dùng Thread.sleep để đợi asynchronous behavior

Nếu operation chỉ yêu cầu một trạng thái và worker thay đổi sau đó, sleep tùy ý tạo test flaky. Dùng \`CountDownLatch\`, \`Awaitility\` hoặc polling có deadline.

### 22.7 Không cleanup khi assertion thất bại

Đăng ký MBean trong test mà không dùng \`finally\` hoặc \`@AfterEach\` có thể để lại registration và gây collision các test tiếp theo.

### 22.8 Đổi test expected cho khớp runtime mà không review

Nếu operation mới xuất hiện, test fail có thể là tín hiệu cần review security contract. Không tự cập nhật expected set chỉ để CI xanh.

## 23. Quy trình kiểm thử theo từng bước

1. **Tạo management interface nhỏ.** Chọn attributes/operations thực sự cần.
2. **Tạo implementation.** Có thêm public methods không thuộc interface để thử khả năng ẩn.
3. **Khởi tạo MBeanServer riêng.** Không phụ thuộc platform registry.
4. **Đăng ký MBean qua ObjectName.**
5. **Đọc MBeanInfo.** Assert danh sách member và flags.
6. **Gọi attribute/operation qua MBeanServerConnection.**
7. **Test negative contract.** Không có methods nội bộ/writable attributes ngoài kế hoạch.
8. **Unregister trong finally.**
9. **Tạo Spring context fixture** với MBeanExporter tường minh.
10. **Kiểm tra lifecycle** khi context đóng.
11. **Mở rộng test** cho annotation/proxy/remote connector theo nhu cầu.
12. **Chạy trên CI** và review mọi thay đổi contract.

## 24. Bài tập thực hành mở rộng

### Bài 1 — Read-only và writable

Thêm Java method \`setState(String)\` vào implementation nhưng không thêm vào management interface. Viết test chứng minh attribute \`State\` vẫn read-only. Sau đó cố tình thêm setter vào interface và xem test fail như thế nào.

### Bài 2 — Xác nhận không lộ method nhạy cảm

Thêm method public \`deleteAllData()\` vào implementation. Không đưa method vào interface. Viết test exact operation set và negative assertion để bắt trường hợp một assembler vô tình xuất nó.

### Bài 3 — Signature compatibility

Thêm \`setMaxWorkers(int)\` vào management interface, viết test signature \`"int"\`. Sau đó đổi method nhận \`long\` và quan sát test contract bắt breaking change.

### Bài 4 — Spring lifecycle

Tạo hai ApplicationContext dùng cùng test MBeanServer nhưng mỗi context export ObjectName khác nhau. Đóng context thứ nhất, assert MBean của context thứ hai vẫn tồn tại.

### Bài 5 — AOP và management adapter

Một service có \`@Transactional\` được Spring proxy. Viết management adapter nhỏ, export adapter thành MBean rồi assert operation gọi qua service proxy. Tránh export raw target làm bypass advice.

### Bài 6 — Notification contract

Mở rộng MBean bằng notification \`worker.paused\`. Viết listener test với \`CountDownLatch\`, assert type, userData, sequence và cleanup. Dùng filter để chặn notification khác.

### Bài 7 — Performance

Tạo một getter đọc cached counter và một getter gọi repository. Dùng mock và test latency/interaction để chứng minh getter quản trị không trực tiếp kích hoạt I/O nặng mỗi lần đọc.

## 25. Checklist trước khi đưa test lên CI

| Mục kiểm tra | Đã có? |
|---|---|
| Management interface định nghĩa rõ contract | Cần |
| MBeanInfo attributes names/types/flags được assert | Cần |
| Operations names/signatures được assert | Cần |
| Negative assertions cho methods không được export | Cần |
| Test invocation qua MBeanServerConnection | Cần |
| Server test cô lập hoặc ObjectName duy nhất | Cần |
| Cleanup luôn chạy khi assertion fail | Cần |
| Spring exporter lifecycle có integration test | Nên |
| Annotation/proxy behavior có test khi dùng | Nên |
| Remote connector/security có test riêng | Theo hệ thống |
| Không gọi operation phá dữ liệu thật | Bắt buộc |
| Test không phụ thuộc timing ngẫu nhiên | Cần |
| Không ghi secrets vào log/test output | Cần |

## Tổng kết

Viết kiểm thử xác nhận management interface trong Spring Framework JMX là kiểm tra **hợp đồng quản trị thực tế** trên MBeanServer, chứ không chỉ kiểm tra Java methods hay Spring bean existence. Hãy bắt đầu bằng Standard MBean interface nhỏ, đọc \`MBeanInfo\` để xác nhận attributes và operations, gọi \`getAttribute\`/\`invoke\` qua connection, đồng thời chứng minh method nội bộ không xuất hiện. Dùng test server riêng và cleanup trong finally để tránh collision; bổ sung Spring integration test cho exporter lifecycle. Những negative contract tests này là lớp bảo vệ quan trọng trước refactor, auto-proxy, assembler changes và việc vô tình mở rộng bề mặt quản trị.
