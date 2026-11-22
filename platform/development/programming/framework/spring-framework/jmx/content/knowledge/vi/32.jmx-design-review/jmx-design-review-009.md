# Kiểm tra tương thích khi thay đổi management interface trong Spring Framework JMX

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Xác định **management interface** là hợp đồng giữa JMX MBean và những client sử dụng nó.
- Phân loại các thay đổi có thể phá vỡ tương thích: đổi \`ObjectName\`, đổi tên attribute, kiểu dữ liệu, read/write semantics, operation, parameters, return type, notifications và hành vi thực thi.
- Phân biệt **Java source/binary compatibility** với **JMX runtime compatibility**.
- Đánh giá tác động của Standard MBean, MXBean, Spring \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` và AOP proxy.
- Xây dựng **contract tests dựa trên \`MBeanInfo\`** cùng các phép thử đọc, ghi và gọi operation thực tế.
- Kiểm tra tính tương thích của JMX remote clients, Open Types và serialization.
- Lập kế hoạch migration, alias, deprecation và rollback khi buộc phải thay management API.
- Thiết kế bảng đánh giá trước release để hạn chế lỗi cho monitoring collectors, scripts và operational tools.

## 1. Management interface là một public contract

Một Java service có thể thay đổi implementation thường xuyên. Nhưng khi method hoặc attribute được export qua JMX, nó trở thành một phần của interface mà những consumer ngoài codebase có thể sử dụng.

Ví dụ JMX client:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=QueueManagement,name=Primary"
);

long depth = (Long) connection.getAttribute(
    name,
    "PendingJobs"
);

connection.invoke(
    name,
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

Contract bao gồm:

- **MBean identity:** ObjectName và MBeanServer/connector đích.
- **Attribute schema:** tên, type, readable/writable, boolean is-getter.
- **Operation schema:** tên, parameter types/order, return type, impact.
- **Notification schema:** types và payload semantics.
- **Hành vi:** đơn vị đo, timing, side effects, idempotency, exceptions.
- **Security:** những ai có quyền đọc, ghi hoặc gọi.
- **Lifecycle:** thời điểm MBean có mặt, bị unregister hoặc thay thế.

Những consumer thường không được IDE tự sửa khi team refactor source code:

\`\`\`text
MBean exporter
    |
    v
MBeanServer
    |
    +-- JConsole / VisualVM
    +-- Monitoring collector
    +-- SRE scripts
    +-- Alert rules
    +-- Remote JMX applications
\`\`\`

Vì vậy review management interface phải đánh giá **client-visible contract**, không chỉ method signatures trong repository.

## 2. Ba tầng tương thích cần phân biệt

### Tầng 1 — Java source compatibility

Client Java compile lại với interface mới có thành công không? Ví dụ đổi return type từ \`int\` sang \`long\` có thể khiến code gán vào \`int\` không compile.

### Tầng 2 — Java binary compatibility

Một client đã compile trước đó có còn link và gọi method Java với binary descriptor phù hợp không? Thay đổi method descriptor có thể gây lỗi như \`NoSuchMethodError\` khi client không được rebuild.

### Tầng 3 — JMX management compatibility

Client dùng JMX API bằng tên chuỗi có còn tìm đúng ObjectName, attribute và operation? \`MBeanInfo\` thực tế sau deployment có tương thích không?

Ví dụ refactor:

\`\`\`java
public long getPendingJobs()
\`\`\`

thành:

\`\`\`java
public long getWaitingTasks()
\`\`\`

Java call sites trong repository có thể đã được sửa đầy đủ. Nhưng JMX client vẫn gọi:

\`\`\`java
connection.getAttribute(name, "PendingJobs");
\`\`\`

có thể gặp \`AttributeNotFoundException\`.

**Kết luận:** Không thể dùng Java compilation test thay thế JMX contract test.

## 3. Ví dụ management interface phiên bản đầu

Ta thiết kế Standard MBean để có một baseline rõ ràng.

Tệp \`QueueManagementMBean.java\`:

\`\`\`java
package example.jmx;

public interface QueueManagementMBean {

    long getPendingJobs();

    boolean isPaused();

    void pauseProcessing();

    void resumeProcessing();
}
\`\`\`

Tệp \`QueueManagement.java\`:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public class QueueManagement implements QueueManagementMBean {

    private final AtomicLong pending = new AtomicLong(5);
    private final AtomicBoolean paused = new AtomicBoolean();

    @Override
    public long getPendingJobs() {
        return pending.get();
    }

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void pauseProcessing() {
        paused.set(true);
    }

    @Override
    public void resumeProcessing() {
        paused.set(false);
    }
}
\`\`\`

Baseline JMX contract:

| Thành phần | Tên | Kiểu/semantics |
|---|---|---|
| ObjectName | \`learning.jmx:type=QueueManagement,name=Primary\` | MBean identity |
| Attribute | \`PendingJobs\` | \`long\`, chỉ đọc, số jobs đang chờ |
| Attribute | \`Paused\` | \`boolean\`, chỉ đọc |
| Operation | \`pauseProcessing\` | 0 parameters, \`void\` |
| Operation | \`resumeProcessing\` | 0 parameters, \`void\` |

Những giá trị trên cần được khóa trong test fixture hoặc contract snapshot có chủ đích.

## 4. Các loại thay đổi và mức độ rủi ro

| Thay đổi | Tác động thường gặp | Cách đánh giá |
|---|---|---|
| Đổi ObjectName | Client không tìm thấy MBean | \`isRegistered\`, discovery test |
| Đổi tên attribute | \`AttributeNotFoundException\` | \`MBeanInfo\` attribute name |
| Đổi \`int\` → \`long\` | Cast/type mismatch | Type metadata và runtime value |
| Đổi getter read-only thành writable | Tăng quyền tác động | \`isWritable\`, authorization |
| Bỏ writable setter | Existing admin scripts lỗi | \`setAttribute\` negative/compatibility tests |
| Đổi operation name | \`ReflectionException\`/operation not found | \`MBeanInfo\`, \`invoke\` |
| Đổi parameter types | Signature mismatch | Parameter type list |
| Đổi return type | Client conversion hoặc binary break | Metadata và invocation result |
| Đổi unit | Alert sai ngưỡng dù type không đổi | Semantic tests |
| Đổi sync thành async | Client hiểu sai completion | Behavioral contract |
| Thay notification type | Listener/filter không nhận event | Notification metadata và delivery tests |
| Chuyển Standard MBean sang MXBean | Mapping/representation thay đổi | Open Type metadata, remote clients |
| Đổi Spring AOP proxy strategy | Metadata/invocation có thể khác | Proxy và exporter integration tests |
| Thêm operation nhạy cảm | Mở rộng attack surface | Security review |
| Chuyển MBean sang server khác | Client kết nối sai registry | Server/connector identity |

Không phải mọi thay đổi đều chắc chắn phá hỏng mọi client. Nhưng mỗi loại thay đổi trên đều cần đánh giá consumer và contract thực tế.

## 5. Đổi ObjectName

Ví dụ ban đầu:

\`\`\`text
learning.jmx:type=QueueManagement,name=Primary
\`\`\`

Sau refactor thành:

\`\`\`text
learning.jmx:type=QueueAdministration,name=Primary
\`\`\`

Dù MBean có cùng attributes, scripts với ObjectName cũ sẽ không tìm thấy resource.

**Cách an toàn khi semantics không đổi:** giữ logical ObjectName cũ dù Java class đổi tên.

Với Spring:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary"
)
public class QueueAdministration {
    // ...
}
\`\`\`

Không sinh ObjectName từ \`bean.getClass().getSimpleName()\` vì Spring AOP có thể tạo runtime proxy class name không ổn định.

Nếu buộc đổi ObjectName, cần một migration window hoặc adapter công bố song song hai identities nếu không tạo xung đột ownership.

## 6. Đổi tên attribute

Ban đầu:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() {
    return queue.pendingJobs();
}
\`\`\`

Sau refactor:

\`\`\`java
@ManagedAttribute
public long getWaitingTasks() {
    return queue.pendingJobs();
}
\`\`\`

Từ góc nhìn JMX, \`PendingJobs\` có thể biến mất và \`WaitingTasks\` xuất hiện.

Cách giữ compatibility trong management facade:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() {
    return queue.pendingJobs();
}

@ManagedAttribute
public long getWaitingTasks() {
    return queue.pendingJobs();
}
\`\`\`

Trong thời gian migration, cả hai tên có thể được export. Nếu semantics của "job" và "task" thực sự khác, không nên tạo alias đánh đồng; khi đó phải công bố contract mới và tài liệu hóa khác biệt.

## 7. Đổi type attribute

Ví dụ:

\`\`\`java
@ManagedAttribute
public int getProcessedJobs() { ... }
\`\`\`

thành:

\`\`\`java
@ManagedAttribute
public long getProcessedJobs() { ... }
\`\`\`

Type metadata có thể đổi:

\`\`\`text
ProcessedJobs: int
ProcessedJobs: long
\`\`\`

Một client cũ:

\`\`\`java
Integer count = (Integer) connection.getAttribute(
    name, "ProcessedJobs"
);
\`\`\`

có thể bị \`ClassCastException\` khi runtime value đổi thành \`Long\`.

Đừng dựa vào autoboxing để cho rằng contract tương thích. Management API nên có migration:

\`\`\`java
@ManagedAttribute
public int getProcessedJobs() {
    return legacyIntCount();
}

@ManagedAttribute
public long getProcessedJobsLong() {
    return service.processedCount();
}
\`\`\`

\`legacyIntCount()\` phải có chính sách overflow rõ ràng; có thể clamp, báo lỗi hoặc giới hạn lifetime nhưng không nên âm thầm truncate làm sai số liệu.

Kiểm tra type qua \`MBeanAttributeInfo.getType()\`, và kiểm tra giá trị thực tế qua \`getAttribute\`.

## 8. Đổi primitive/wrapper và null semantics

Đổi:

\`\`\`java
public int getQueueDepth()
\`\`\`

sang:

\`\`\`java
public Integer getQueueDepth()
\`\`\`

có thể đổi JMX metadata type từ \`int\` sang \`java.lang.Integer\`. Đồng thời getter mới có thể trả \`null\`.

Ngay cả khi value non-null được boxed giống nhau, metadata contract đã thay đổi. Monitoring tools có thể đọc type string để chọn converter.

Nếu \`null\` biểu thị "không có dữ liệu", đừng thay bằng 0 trừ khi 0 có cùng semantics. Có thể thêm:

\`\`\`java
@ManagedAttribute
public boolean isQueueDepthAvailable() { ... }

@ManagedAttribute
public long getQueueDepth() { ... }
\`\`\`

để giữ type ổn định và biểu diễn availability riêng, tùy business contract.

## 9. Đổi signature operation

JMX operation xác định không chỉ bằng tên mà còn parameter types.

Ví dụ cũ:

\`\`\`java
@ManagedOperation
public void setQueueLimit(int limit) { ... }
\`\`\`

Client:

\`\`\`java
connection.invoke(
    name,
    "setQueueLimit",
    new Object[] { 100 },
    new String[] { "int" }
);
\`\`\`

Sau khi đổi method sang:

\`\`\`java
@ManagedOperation
public void setQueueLimit(long limit) { ... }
\`\`\`

client với signature \`int\` có thể không còn gọi được operation.

Một interface đổi \`int\` → \`long\` có thể làm Java code compile lỗi hoặc cần rebuild; JMX client dùng chuỗi \`int\` cũng cần migration.

Một cách có chủ đích là giữ overload legacy nếu framework/exporter hỗ trợ và semantics rõ:

\`\`\`java
@ManagedOperation
public void setQueueLimit(int limit) {
    service.setLimit(limit);
}

@ManagedOperation
public void setQueueLimit(long limit) {
    service.setLimit(limit);
}
\`\`\`

Nhưng cần test JMX overload resolution, parameter type arrays và tool compatibility. Không phải client nào cũng hiển thị overloads thuận tiện.

## 10. Operation semantics quan trọng hơn chỉ tên

Giả sử operation \`rebuildIndex()\` ban đầu chạy đồng bộ, chỉ trả về khi hoàn tất.

Sau nâng cấp, operation chỉ enqueue job rồi trả về ngay.

Tên và signature có thể giữ nguyên, nhưng behavioral contract đã đổi:

- Client có còn được phép hiểu completion khi method return?
- Nếu client retry, có tạo nhiều jobs không?
- Có job ID để theo dõi không?
- Timeout có nghĩa task dừng không?
- Có rate limit/concurrency gate không?

Một tên mới như \`requestIndexRebuild\` kèm một status attribute có thể đúng semantics hơn. Khi thay đổi không tương thích, migration cần cập nhật runbook và automation clients.

Không nên đánh giá compatibility chỉ qua \`MBeanInfo\` nếu operation có side effects hoặc timing contract.

## 11. Read/write semantics là một phần contract và bảo mật

Ví dụ v1:

\`\`\`java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}
\`\`\`

v2 thêm setter:

\`\`\`java
@ManagedAttribute
public void setMaxWorkers(int value) {
    validate(value);
    maxWorkers = value;
}
\`\`\`

Attribute chuyển từ read-only sang writable. Đây là **mở rộng quyền quản trị**, không phải chỉ là API convenience.

Ngược lại, bỏ setter phá client đang dùng \`setAttribute\`.

Cần kiểm tra:

\`\`\`java
MBeanAttributeInfo info = ...;

assertTrue(info.isReadable());
assertFalse(info.isWritable());
\`\`\`

Nếu read/write permissions của JMX connector quá rộng, thêm setter có thể tạo attack surface mới. Review authorization và audit song song với contract tests.

## 12. Notification contract cũng có thể bị phá vỡ

Một MBean phát notification:

\`\`\`text
learning.queue.overloaded
learning.queue.recovered
\`\`\`

Listener có thể filter đúng type string:

\`\`\`java
filter.enableType("learning.queue.overloaded");
\`\`\`

Nếu version mới đổi type thành:

\`\`\`text
learning.queue.thresholdExceeded
\`\`\`

listener cũ có thể ngừng nhận sự kiện.

Không chỉ type string quan trọng. Cần xem:

- Source semantics.
- Sequence number behavior.
- Timestamp units.
- Message và userData.
- Notification delivery timing.
- Có replay hay không khi client reconnect.
- Số notification mới có ảnh hưởng polling/automation không.

\`MBeanInfo.getNotifications()\` giúp kiểm tra metadata type list; integration test phát event thật giúp kiểm tra delivery.

## 13. Standard MBean, MXBean và Spring annotations

### Standard MBean

Management interface theo convention:

\`\`\`java
public interface QueueManagementMBean {
    long getPendingJobs();
    void pauseProcessing();
}
\`\`\`

Thay đổi interface này có thể ảnh hưởng trực tiếp tới MBeanInfo và Java clients.

### MXBean

MXBean dùng mapping từ Java types sang Open Types. Ví dụ khi trả object cấu trúc, remote client có thể thấy \`CompositeData\` thay vì custom Java class. Thay đổi fields, keys hoặc Open Type schema cần compatibility tests.

### Spring annotation-based MBean

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary"
)
public class QueueManagement {

    @ManagedAttribute
    public long getPendingJobs() { ... }

    @ManagedOperation
    public void pauseProcessing() { ... }
}
\`\`\`

Exporter và metadata assembler quyết định JMX schema thực tế.

Trong mọi trường hợp, **Java declaration chỉ là đầu vào**. Contract cần được xác nhận bằng MBeanServer sau khi application context khởi tạo.

## 14. Ảnh hưởng của Spring AOP proxy

Spring AOP có thể dùng JDK dynamic proxy hoặc class-based proxy.

\`\`\`text
Caller
  -> Spring AOP proxy
  -> target service
\`\`\`

Các tình huống ảnh hưởng management interface:

- Getter được annotate trên implementation nhưng không có trong JDK proxy interface.
- Target class metadata được exporter phát hiện khác khi đổi proxy strategy.
- Operation nhìn thấy trong metadata nhưng không invocable qua proxy theo config.
- Bỏ proxy rồi export target trực tiếp làm mất transaction/security advice.
- ObjectName được tạo từ runtime proxy class nên đổi ngoài ý muốn.

Dùng \`AopUtils\`:

\`\`\`java
Object bean = context.getBean("queueService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

Tuy vậy, kiểm tra proxy class không thay cho \`getMBeanInfo\` và invocation tests.

### Management facade

Tách JMX contract khỏi business interface:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary"
)
public class QueueManagementFacade {

    private final QueueService service;

    public QueueManagementFacade(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedOperation
    public void pauseProcessing() {
        service.pause();
    }
}
\`\`\`

Facade giữ tên/type/semantics JMX ổn định trong khi service có thể đổi method hoặc proxy strategy. Nếu service cần AOP advice, facade nên gọi Spring-managed proxy của service, không tạo target bằng \`new\` ngoài container.

## 15. Thiết kế một contract baseline

Một baseline có thể bao gồm:

\`\`\`text
MBean:
  learning.jmx:type=QueueManagement,name=Primary

Attributes:
  PendingJobs:
    type: long
    readable: true
    writable: false
    semantics: current pending job count
  Paused:
    type: boolean
    readable: true
    writable: false

Operations:
  pauseProcessing:
    parameters: []
    returnType: void
    semantics: stop accepting new jobs
  resumeProcessing:
    parameters: []
    returnType: void

Notifications:
  learning.queue.overloaded
\`\`\`

Ví dụ trên là documentation representation, không phải bắt buộc một schema YAML cụ thể. Có thể lưu baseline trong Java test assertions hoặc một artifact/versioned contract file được dự án quản lý.

Không nên chỉ so sánh snapshot textual thô rồi coi mọi thay đổi thứ tự mảng metadata là breaking change. Nên chuẩn hóa/sắp xếp các names trước khi so để tránh noise.

## 16. MBeanInfo contract tests

Test JMX metadata là cách quan trọng để phát hiện interface drift.

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class QueueManagementContractTest {

    private final MBeanServer server = /* test MBeanServer */ null;

    @Test
    void keepsAttributeContract() throws Exception {
        ObjectName name = new ObjectName(
            "learning.jmx:type=QueueManagement,name=Primary"
        );

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        MBeanAttributeInfo pending = Arrays.stream(
            info.getAttributes()
        ).filter(a -> "PendingJobs".equals(a.getName()))
         .findFirst()
         .orElseThrow();

        assertEquals("long", pending.getType());
        assertTrue(pending.isReadable());
        assertFalse(pending.isWritable());
    }

    @Test
    void keepsOperationContract() throws Exception {
        ObjectName name = new ObjectName(
            "learning.jmx:type=QueueManagement,name=Primary"
        );

        MBeanOperationInfo pause = Arrays.stream(
            server.getMBeanInfo(name).getOperations()
        ).filter(o -> "pauseProcessing".equals(o.getName()))
         .findFirst()
         .orElseThrow();

        assertEquals("void", pause.getReturnType());
        assertEquals(0, pause.getSignature().length);
    }
}
\`\`\`

\`server\` là placeholder cho test fixture: dự án cần tạo MBeanServer, đăng ký MBean và cleanup đúng lifecycle. Không dùng \`null\` ở test thực tế.

Việc kiểm tra attribute/operation bằng tên và type giúp phát hiện thay đổi mà Java compilation không phát hiện.

## 17. Ví dụ integration test runnable với MBeanServer riêng

Có thể tạo test fixture độc lập:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class StandardMBeanCompatibilityTest {

    @Test
    void exportsExpectedContract() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer(
                "compat.test"
            );

        ObjectName name = new ObjectName(
            "learning.jmx:type=QueueManagement,name=Primary"
        );

        try {
            server.registerMBean(new QueueManagement(), name);

            assertTrue(server.isRegistered(name));
            assertEquals(
                "long",
                java.util.Arrays.stream(
                    server.getMBeanInfo(name).getAttributes()
                ).filter(a -> "PendingJobs".equals(a.getName()))
                 .findFirst().orElseThrow().getType()
            );

            Object value =
                server.getAttribute(name, "PendingJobs");

            assertInstanceOf(Long.class, value);

            server.invoke(
                name,
                "pauseProcessing",
                new Object[0],
                new String[0]
            );

            assertEquals(
                true,
                server.getAttribute(name, "Paused")
            );
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
\`\`\`

Ví dụ này xác nhận schema và behavior qua JMX API. Trong hệ thống Spring, cần bổ sung test context với MBeanExporter và AOP proxy để xác nhận integration tương ứng.

## 18. Test compatibility từ góc nhìn client cũ

Một test sử dụng \`MBeanServer\` cùng tên/kiểu cũ là tốt, nhưng nên có thêm **legacy client fixture**.

Ví dụ:

\`\`\`java
public final class LegacyQueueClient {

    private final MBeanServerConnection connection;
    private final ObjectName name;

    public LegacyQueueClient(
            MBeanServerConnection connection,
            ObjectName name) {
        this.connection = connection;
        this.name = name;
    }

    public long pendingJobs() throws Exception {
        return (Long) connection.getAttribute(
            name, "PendingJobs"
        );
    }

    public void pause() throws Exception {
        connection.invoke(
            name,
            "pauseProcessing",
            new Object[0],
            new String[0]
        );
    }
}
\`\`\`

Khi nâng cấp MBean implementation, chạy fixture client cũ **không sửa code client**.

Điều này phát hiện những lỗi mà chỉ nhìn MBeanInfo có thể bỏ sót:

- Operation vẫn có cùng signature nhưng behavior khác.
- Getter trả value không còn đúng unit.
- MBean nằm ở server khác.
- Authorization chặn một action từng hợp lệ.
- Remote serialization thay đổi.

Nếu môi trường thật có nhiều phiên bản client, test nên bao phủ các phiên bản được hỗ trợ.

## 19. So sánh version trước/sau

Một cách đánh giá hệ thống là thu thập contract snapshot từ phiên bản trước và phiên bản mới:

\`\`\`text
Version A JMX metadata
         |
         v
Normalized contract baseline
         |
         | compare
         v
Version B JMX metadata
         |
         +-- Removed attributes?
         +-- Changed types?
         +-- New writable attributes?
         +-- Changed operation signatures?
         +-- Removed notification types?
\`\`\`

Quy trình:

1. Khởi tạo cả hai phiên bản trong test environments độc lập.
2. Truy vấn cùng logical ObjectName.
3. Lấy MBeanInfo và normalize các danh sách.
4. So sánh names, types, readable/writable, operation signatures.
5. Chạy các behavior tests cần thiết.
6. Phân loại thay đổi compatible, additive, breaking hoặc security-sensitive.
7. Chỉ chấp nhận breaking change khi đã có migration plan.

Một attribute được thêm mới thường là additive, nhưng cũng có thể tăng bề mặt thông tin nhạy cảm. Vì vậy "additive" không đồng nghĩa "không cần security review".

## 20. Remote JMX compatibility

Remote client còn có những vấn đề không xuất hiện trong cùng JVM:

- Custom class return type có thể thiếu trên client classpath.
- Serialization hoặc \`serialVersionUID\` có thể thay đổi.
- MXBean/Open Type mapping thay đổi shape của \`CompositeData\`.
- Connector hoặc transport policy thay đổi.
- TLS certificate/trust configuration ảnh hưởng connectivity.
- Client credentials/authorization thay đổi.
- ObjectName được đăng ký ở MBeanServer khác connector đang phục vụ.

Với API được nhiều loại client sử dụng, primitive, String và Open Types có contract rõ thường giảm coupling so với trả Java objects tùy biến.

Không nên coi một JUnit test local bằng \`MBeanServer\` là bằng chứng toàn bộ remote clients tương thích. Khi có remote usage, cần ít nhất một integration test qua connector được bảo vệ.

## 21. Compatibility và authorization

Management interface có thể thay đổi quyền mà không đổi tên method.

Ví dụ version mới thêm:

\`\`\`java
@ManagedOperation
public void clearAllQueues() { ... }
\`\`\`

Đây là một surface mới có side effects. Nếu connector dùng quyền readwrite quá rộng, automation account cũ có thể gọi operation mới.

Ngược lại, một operation cũ bị bảo vệ thêm bởi method-level security có thể khiến client hợp lệ trước đây bị từ chối.

Khi đánh giá release:

- Kiểm tra interface contract.
- Kiểm tra quyền readonly/readwrite và granularity của connector.
- Kiểm tra Spring AOP method security call path.
- Test các identity được phép và không được phép.
- Audit operations nhạy cảm.
- Không dựa vào HTTP Spring Security để bảo vệ JMX connector.

Thay đổi security là thay đổi hành vi có ảnh hưởng tới compatibility, cần được đánh giá cùng contract schema.

## 22. Chiến lược migration

Nếu buộc đổi management interface:

### Phương án A — Giữ contract cũ

Giữ tên/kiểu cũ trên facade và chỉ thay logic nội bộ.

Phù hợp khi semantics không đổi.

### Phương án B — Cùng tồn tại old/new attributes

Ví dụ:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() { ... }

@ManagedAttribute
public long getQueuedTasks() { ... }
\`\`\`

Công bố cả hai trong migration window, tài liệu hóa tên canonical.

### Phương án C — Versioned ObjectName

Ví dụ:

\`\`\`text
learning.jmx:type=QueueManagement,name=Primary,version=1
learning.jmx:type=QueueManagement,name=Primary,version=2
\`\`\`

Chỉ nên dùng khi API thực sự khác và cần song song. Hai ObjectNames là hai registrations riêng; phải quản lý ownership, lifecycle và dữ liệu nhất quán.

### Phương án D — Adapter/facade dành cho client cũ

Một adapter có thể tiếp tục trả kiểu, đơn vị và operation names cũ, trong khi delegate sang service implementation mới.

### Phương án E — Breaking release có kế hoạch

Nếu giữ tương thích không khả thi, cần công bố breaking change, tài liệu update cho operators, kiểm thử các consumer quan trọng và có rollback strategy.

Không rename hoặc thay type âm thầm trong maintenance patch khi client ngoài repository vẫn phụ thuộc.

## 23. Checklist đánh giá trước release

1. ObjectNames cũ có còn đăng ký trong cùng MBeanServer/connector không?
2. Attribute names có đổi không?
3. Attribute types có đổi không?
4. Read/write semantics có đổi không?
5. Units, nullability và value ranges có đổi không?
6. Operation names có đổi không?
7. Parameters và return types có đổi không?
8. Sync/async và side effects có đổi không?
9. Notification types/payload có đổi không?
10. Standard MBean/MXBean representation có đổi không?
11. Spring exporter/assembler có thay đổi không?
12. JDK dynamic proxy/class-based proxy strategy có đổi không?
13. Security/authorization có thay đổi không?
14. Remote client classpath/serialization có bị ảnh hưởng không?
15. Có legacy client integration tests không?
16. Có consumer inventory và migration plan không?
17. Có rollback plan không?
18. Có kiểm tra MBeanInfo và actual invocation không?
19. Có kiểm tra ObjectName collision/registration lifecycle không?
20. Có cập nhật documentation và runbooks không?

## 24. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Client gặp AttributeNotFoundException | Getter JMX bị đổi tên hoặc không export | Kiểm tra MBeanInfo và compatibility alias |
| Client cast Integer/Long lỗi | Attribute type đổi | Test metadata, giữ legacy type |
| Operation invoke thất bại | Tên hoặc parameter signature khác | So sánh MBeanOperationInfo |
| JConsole thấy MBean nhưng script hỏng | Contract thay đổi dù ObjectName còn | So sánh attributes/operations |
| Proxy bị đổi nên MBean mất getter | JDK proxy interface không có method | Facade/assembler/proxy strategy test |
| Remote client deserialize lỗi | Custom return type thay đổi | Open Types hoặc stable types |
| Alert sai ngưỡng | Đơn vị/semantics thay đổi | Ghi rõ unit, migration |
| Bot gọi được operation mới ngoài dự kiến | Quyền readwrite quá rộng | Security review và tách surface |
| MBean chuyển server | Exporter.server thay đổi | Kiểm tra MBeanServer/connector |
| Context đóng xóa MBean của context khác | Shared ObjectName ownership | Test lifecycle và policies |
| Notification listener không nhận event | Notification type đổi | Contract test và migration |
| Client timeout rồi retry tạo side effects | Operation async/timeout semantics đổi | Job ID, idempotency và runbook |

## 25. Bài tập thực hành

### Bài tập 1 — Đổi tên attribute

Tạo MBean v1 với \`PendingJobs\`. Đổi getter sang \`WaitingTasks\`. Chạy legacy client fixture và kiểm tra thất bại. Thêm compatibility getter rồi chạy lại.

### Bài tập 2 — Đổi type

Tạo v1 \`ProcessedJobs\` type \`int\`, v2 type \`long\`. Dùng \`MBeanInfo\` và \`getAttribute\` để phát hiện type break. Đề xuất migration alias.

### Bài tập 3 — Operation signature

Thay \`setQueueLimit(int)\` bằng \`setQueueLimit(long)\`. Kiểm tra operation signatures và client \`invoke\` với \`"int"\`. Thiết kế compatibility strategy.

### Bài tập 4 — AOP proxy

Export một Spring service có JDK proxy, đổi sang class-based proxy. Kiểm tra ObjectName, metadata và invocation có giữ nguyên không. Nếu không, thử management facade.

### Bài tập 5 — Remote MXBean

Tạo MXBean trả \`CompositeData\` hoặc một kiểu được Open Type mapping hỗ trợ. Thay đổi schema và thử legacy remote client. Ghi nhận field/key compatibility.

### Bài tập 6 — Security-sensitive release

Một MBean mới thêm operation \`clearCache\`. Hãy đánh giá quyền của automation bot dùng readonly và readwrite, đồng thời đề xuất negative permission test trước release.

## 26. Ghi nhớ cốt lõi

- **Management interface là public API contract**, dù được công bố qua JMX thay vì HTTP.
- Java source/binary compatibility không thay thế JMX runtime compatibility.
- ObjectName, attribute names/types, writable flags, operation signatures, notifications và semantics đều cần đánh giá.
- \`MBeanInfo\` là nguồn xác nhận metadata thực tế sau export.
- Proxy strategy, Spring JMX exporter và remote serialization có thể ảnh hưởng client-visible contract.
- Management facade giúp tách hợp đồng quản trị khỏi refactor nghiệp vụ.
- Compatibility tests nên chạy cùng legacy client fixture và behavior tests.
- Breaking changes cần migration, documentation, consumer coordination và rollback plan.

## Tài liệu tham khảo

- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework AOP Proxying: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework MBeanExporter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 MBeanOperationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
