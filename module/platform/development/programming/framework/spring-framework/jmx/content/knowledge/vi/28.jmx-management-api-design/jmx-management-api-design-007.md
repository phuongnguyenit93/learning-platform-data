# Đặt mô tả và ví dụ sử dụng cho người vận hành trong Spring JMX

## 1. Vì sao management API cần tài liệu rõ ràng?

Một MBean xuất hiện trong JConsole hay VisualVM không có nghĩa người vận hành biết phương thức nào an toàn để gọi. Tên \`reset\`, \`reload\`, \`pause\` hoặc \`clear\` thường quá ngắn để giải thích hậu quả và phạm vi tác động. Trong Spring Framework JMX, lớp metadata và tài liệu runbook phải giúp trả lời: MBean phục vụ hệ thống nào, số liệu có đơn vị gì, dữ liệu mới đến đâu, lệnh ảnh hưởng node hay cluster, phải kiểm tra điều kiện gì và làm sao xác minh kết quả.

Tài liệu management API gồm hai phần bổ sung nhau:
- **Description trong MBeanInfo**: câu ngắn mô tả MBean, attribute, operation và parameter, hiển thị trong các công cụ JMX.
- **README/runbook vận hành**: ví dụ truy cập, điều kiện tiên quyết, quyền, rủi ro, thời gian chờ, kiểm chứng và phương án phục hồi.

Đừng dùng description như cơ chế phân quyền; một câu “admin only” không ngăn được client có quyền invoke.

## 2. Metadata JMX nào có thể mô tả?

\`MBeanInfo\` có \`getDescription()\`; \`MBeanAttributeInfo\`, \`MBeanOperationInfo\`, \`MBeanParameterInfo\` và \`MBeanNotificationInfo\` cũng có description riêng.

Spring có annotation thường dùng:
- \`@ManagedResource(description = "...")\` cho cả MBean.
- \`@ManagedAttribute(description = "...")\` cho thuộc tính.
- \`@ManagedOperation(description = "...")\` cho thao tác.
- \`@ManagedOperationParameters\` và \`@ManagedOperationParameter\` cho tên và mô tả tham số.

Những mô tả này chỉ xuất vào MBeanInfo khi exporter dùng đường metadata tương ứng, ví dụ \`AnnotationJmxAttributeSource\` và \`MetadataMBeanInfoAssembler\`. Nếu bean được đăng ký như Standard MBean theo interface chuẩn, mô tả có thể đến từ cơ chế khác. **Luôn đọc MBeanInfo đã được đăng ký thay vì suy đoán từ source code.**

## 3. Quy tắc viết description

Một description hữu ích thường chứa **đối tượng + ý nghĩa + phạm vi + tính chất vận hành**. Với attribute, ghi đơn vị, độ mới, read-only/writable. Với operation, ghi tác động, tính bất đồng bộ, tiền điều kiện hoặc điểm cần thận trọng.

| Thành phần | Mô tả chung chung | Mô tả giúp vận hành |
| --- | --- | --- |
| QueueDepth | Queue size | Number of pending jobs on this JVM; read-only snapshot |
| Paused | Paused state | True when this worker stops accepting new jobs |
| LastUpdatedAt | Last update | UTC timestamp of the latest management snapshot |
| pause() | Pause service | Request graceful pause for this node; active jobs continue |
| retryFailedJob | Retry job | Retry one failed job by ID; verify idempotency first |

Không tuyên bố “real-time” nếu số liệu có cache; không hứa operation hoàn tất đồng bộ nếu nó chỉ gửi yêu cầu. Tránh mô tả quá dài làm mất tính đọc nhanh trong UI; thông tin nhiều bước chuyển sang runbook.

## 4. Ví dụ Spring management adapter có documentation

~~~java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary",
    description = "Operational status and controls for the current worker node"
)
public final class WorkerJmxAdapter {
    private final WorkerManagement management;

    public WorkerJmxAdapter(WorkerManagement management) {
        this.management = management;
    }

    @ManagedAttribute(
        description = "Pending jobs on this JVM; read-only count"
    )
    public int getQueueDepth() {
        return management.snapshot().queueDepth();
    }

    @ManagedAttribute(
        description = "True if new jobs are rejected on this worker"
    )
    public boolean isPaused() {
        return management.snapshot().paused();
    }

    @ManagedAttribute(
        description = "UTC timestamp of the last management snapshot"
    )
    public String getLastUpdatedAt() {
        return management.snapshot().updatedAt().toString();
    }

    @ManagedOperation(
        description = "Request graceful pause on the current node"
    )
    public void pause() {
        management.requestPause();
    }

    @ManagedOperation(
        description = "Retry one failed job after validating job status"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            index = 0,
            name = "jobId",
            description = "Non-empty failed job identifier from the job dashboard"
        )
    })
    public void retryFailedJob(String jobId) {
        management.retryFailedJob(jobId);
    }
}
~~~

Port nghiệp vụ độc lập JMX:

~~~java
import java.time.Instant;

public interface WorkerManagement {
    WorkerSnapshot snapshot();
    void requestPause();
    void retryFailedJob(String jobId);
}

public record WorkerSnapshot(
    int queueDepth,
    boolean paused,
    Instant updatedAt
) {}
~~~

Adapter cố tình chỉ expose các thao tác cần quản trị. Phương thức nhạy cảm phải validate và kiểm tra quyền ở lớp thích hợp; annotation không cấp quyền tự động. Getter nên trả snapshot nhanh, không thực hiện truy vấn tốn tài nguyên mỗi lần công cụ poll.

## 5. Đảm bảo Spring exporter đọc metadata

Một cấu hình Spring Framework thuần có thể dùng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
class JmxExportConfig {
    @Bean
    AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter mBeanExporter(AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);
        return exporter;
    }
}
~~~

Trong Spring Boot, JMX auto-configuration có thể cung cấp exporter. Không tạo exporter thứ hai trước khi xác định cấu hình hiện tại, vì hai exporter có thể đăng ký trùng ObjectName.

Nếu description không xuất hiện, xác minh bean được export qua assembler nào, annotation nằm trên target class hay proxy, và client có đang đọc đúng MBeanServer không.

## 6. ObjectName nên nói được phạm vi

Tên JMX có cấu trúc \`domain:key=value[,key=value]\`. Ví dụ:

~~~text
com.example.jobs:type=Worker,name=Primary,node=worker-a
com.example.jobs:type=Worker,name=Secondary,node=worker-b
~~~

Domain nhóm theo ứng dụng, \`type\` nói loại thành phần, \`name\` phân biệt logical instance, \`node\` giúp thấy phạm vi. Tên phải ổn định và có canonical uniqueness khi nhiều MBean chung server.

Nếu có dữ liệu động chứa dấu phẩy hoặc wildcard, dùng \`ObjectName.quote\` đúng cho phần value, không quote toàn bộ chuỗi ObjectName. Không đưa secret, customer ID hoặc dữ liệu nhạy cảm vào tên MBean.

Câu mô tả “Pause worker” không đủ nếu một operation làm dừng toàn cluster. Cần nêu rõ tác động trên current node hay toàn hệ thống ở cả ObjectName/runbook.

## 7. Attribute: tên, đơn vị, freshness

Một tài liệu thuộc tính nên mô tả:

~~~text
Name: QueueDepth
JMX type: int
Unit: jobs
Readable: true
Writable: false
Scope: current JVM
Freshness: snapshot refreshed every 5 seconds
Normal range: non-negative
Unavailable behavior: see SnapshotAvailable
~~~

Nếu có stale snapshot, cung cấp \`LastUpdatedAt\` hoặc \`SnapshotAvailable\`. Không dùng số 0 để thể hiện “không lấy được dữ liệu” nếu số 0 cũng là giá trị hợp lệ.

Với writable attribute, nêu phạm vi hợp lệ và tác động:

~~~java
@ManagedAttribute(
    description = "Maximum concurrent jobs on this node; valid range 1..64"
)
public int getConcurrencyLimit() {
    return management.getConcurrencyLimit();
}

@ManagedAttribute(
    description = "Update local concurrency; validate 1..64"
)
public void setConcurrencyLimit(int value) {
    management.setConcurrencyLimit(value);
}
~~~

Setter phải validate thật trong code; description chỉ là lời giải thích. Với thay đổi nguy hiểm, cân nhắc operation tường minh thay cho setter đơn giản.

## 8. Operation: cách trình bày an toàn cho người vận hành

Một operation cần có:
1. Mục đích và tình huống sử dụng.
2. ObjectName/instance đích.
3. Quyền phê duyệt hoặc vai trò thao tác.
4. Điều kiện trước (capacity, health, job state).
5. Input format và range.
6. Hành vi thành công, side effect, đồng bộ/bất đồng bộ.
7. Timeout và khả năng retry.
8. Xác minh trạng thái sau thao tác.
9. Rollback hoặc escalation khi không thể hoàn tác.

Ví dụ runbook cho \`pause()\`:

~~~text
Purpose: Stop accepting new jobs on current node.
Precondition: Other workers are healthy and have spare capacity.
Risk: Cluster throughput may temporarily decrease.
Invoke: pause() on the selected node MBean.
Expected: Request accepted; active jobs may continue.
Verify: Paused=true and ActiveJobs trends toward zero.
Rollback: resume() after capacity review and approval.
Do not: Pause every node in the cluster simultaneously.
~~~

Nếu operation chỉ nhận lệnh bất đồng bộ, \`invoke\` không ném lỗi chưa có nghĩa trạng thái cuối cùng đã đạt; cần theo dõi attribute, notification hoặc job status.

## 9. Dùng JConsole và VisualVM

Một hướng dẫn thao tác nên nêu đúng môi trường và quyền:

1. Kết nối đúng JVM hoặc JMX URL đã được phê duyệt.
2. Tìm domain \`com.example.jobs\` trong MBeans.
3. Chọn chính xác MBean instance theo ObjectName.
4. Đọc \`QueueDepth\`, \`Paused\`, \`LastUpdatedAt\`.
5. Đánh giá snapshot có còn mới và health của các node khác.
6. Nếu đã được phép, mở Operations và gọi \`pause()\`.
7. Quan sát \`Paused\` và metrics liên quan.
8. Nếu cần hoàn tác, gọi \`resume()\` theo runbook.

Không dùng production để thử operation có side effect chỉ vì tò mò. Giao diện công cụ có thể thay đổi tùy JDK và MBean type, nên runbook cần dựa vào ObjectName/attribute names thay vì vị trí pixel trong UI.

## 10. Ví dụ Java đọc trạng thái JMX

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class WorkerReadProbe {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        if (!server.isRegistered(name)) {
            throw new IllegalStateException("Missing MBean: " + name);
        }

        int depth = (Integer) server.getAttribute(name, "QueueDepth");
        boolean paused = (Boolean) server.getAttribute(name, "Paused");

        System.out.printf(
            "queueDepth=%d paused=%s%n", depth, paused
        );
    }
}
~~~

Ví dụ này phù hợp với code chạy trong JVM chứa MBean. Một chương trình chạy JVM khác không nên lấy platform server của chính nó rồi kỳ vọng tìm MBean ứng dụng từ xa; cần \`JMXConnector\` và \`MBeanServerConnection\`.

Nếu dùng custom server, nhận đúng server từ Spring container thay vì mặc định platform server.

## 11. Ví dụ gọi operation qua MBeanServerConnection

~~~java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class WorkerCommand {
    public static void requestPause(
            MBeanServerConnection connection,
            ObjectName name) throws Exception {

        if (!connection.isRegistered(name)) {
            throw new IllegalStateException("Missing target: " + name);
        }

        connection.invoke(
            name, "pause", new Object[0], new String[0]
        );
    }
}
~~~

Với operation có tham số:

~~~java
connection.invoke(
    name,
    "retryFailedJob",
    new Object[] { "job-123" },
    new String[] { "java.lang.String" }
);
~~~

Tên và signature phải khớp \`MBeanInfo\`. Không retry mù operation có side effect khi client timeout: thao tác có thể đã hoàn thành trên server mà response bị mất. Kiểm tra trạng thái thực và idempotency trước khi gọi lại.

Đối với remote JMX, tránh hard-code credential. Connector phải có authentication, TLS và network isolation phù hợp.

## 12. Đọc description thực tế từ MBeanInfo

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanInfo info = server.getMBeanInfo(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);

System.out.println("MBean: " + info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute %s (%s): %s%n",
        attr.getName(), attr.getType(), attr.getDescription()
    );
}

for (var op : info.getOperations()) {
    System.out.println(
        "Operation " + op.getName() + ": " + op.getDescription()
    );

    for (var parameter : op.getSignature()) {
        System.out.printf(
            "  %s (%s): %s%n",
            parameter.getName(),
            parameter.getType(),
            parameter.getDescription()
        );
    }
}
~~~

Đoạn probe xác nhận MBean thực sự công bố mô tả. Nếu metadata thiếu, xem annotation assembler, target/proxy, Standard MBean interface và \`MBeanServer\` đang đọc. Không dựa riêng vào việc annotation xuất hiện trên class.

## 13. Đặt tên operation dễ hiểu, tránh ý nghĩa mơ hồ

| Tên mơ hồ | Tên cụ thể hơn | Điều được làm rõ |
| --- | --- | --- |
| \`reset()\` | \`resetStatistics()\` | Không phải xóa dữ liệu |
| \`clear()\` | \`clearExpiredCacheEntries()\` | Chỉ xóa cache entry hết hạn |
| \`stop()\` | \`requestGracefulWorkerStop()\` | Thao tác graceful |
| \`reload()\` | \`reloadReadOnlyConfiguration()\` | Loại config được tải lại |
| \`retry(id)\` | \`retryFailedJob(jobId)\` | Phạm vi job thất bại |
| \`update(value)\` | \`setConcurrencyLimit(value)\` | Thay đổi concurrency |

Đổi tên operation có thể làm hỏng automation; nếu API đã triển khai, phải có version/migration và cập nhật runbook, monitoring scripts.

## 14. Hành vi lỗi và cảnh báo cần ghi

| Lỗi | Nguyên nhân thường gặp | Hành động người vận hành |
| --- | --- | --- |
| MBean không thấy | Sai ObjectName, server hoặc exporter chưa đăng ký | Query danh sách MBean và kiểm tra lifecycle |
| Attribute thiếu | Metadata/assembler không expose | Đọc MBeanInfo; không tự đoán tên |
| \`InstanceNotFoundException\` | MBean đã unregister sau redeploy | Xác nhận JVM/deployment đích |
| Validation error | Tham số sai range hoặc trạng thái không hợp lệ | Kiểm tra input và precondition |
| Authorization error | Thiếu quyền JMX hoặc nghiệp vụ | Theo quy trình cấp quyền |
| Timeout | Không chắc lệnh đã chạy hay chưa | Xác minh trạng thái trước khi retry |
| Dependency unavailable | DB/cache/queue bị lỗi | Xử lý dependency rồi cân nhắc thao tác tiếp |

Description không nên hứa mọi exception có cùng class nếu Spring JMX proxy hoặc connector có thể wrap lỗi. Runbook nên nói cách tìm nested cause và tránh để log lộ thông tin nhạy cảm.

## 15. README/runbook mẫu có thể dùng trong dự án

~~~markdown
# Worker Management - Primary

## Target
ObjectName: com.example.jobs:type=Worker,name=Primary
Scope: Current JVM only.

## Read-only attributes
- QueueDepth: pending jobs, unit=jobs; snapshot every 5 seconds.
- Paused: true when worker does not accept new jobs.
- LastUpdatedAt: UTC timestamp of latest snapshot.

## Operations
### pause()
Purpose: Request graceful pause.
Precondition: Other workers have spare capacity.
Risk: Reduced throughput during drain.
Verify: Paused=true, ActiveJobs decreasing.
Rollback: resume() after operator approval.

### retryFailedJob(jobId)
Purpose: Retry exactly one failed job.
Input: job ID, example job-123.
Precondition: Job is failed, not already running.
Risk: Duplicate side effects if retried without idempotency.
Verify: Job status in monitoring dashboard.
Rollback: Not guaranteed; escalate if duplicate processing.

## Troubleshooting
- Missing MBean: verify ObjectName and correct MBeanServer.
- Stale data: check LastUpdatedAt.
- Invoke timeout: inspect real job state before retry.
~~~

Runbook cần gắn với release/version của management API để tránh một description cũ hướng dẫn sai hành vi sau khi nâng cấp.

## 16. Kiểm thử metadata và tài liệu

Một integration test nên khởi động Spring context thật và đọc \`MBeanInfo\`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import javax.management.MBeanServer;
import javax.management.ObjectName;

void assertDocumentation(MBeanServer server) throws Exception {
    var name = new ObjectName(
        "com.example.jobs:type=Worker,name=Primary"
    );
    assertTrue(server.isRegistered(name));

    var info = server.getMBeanInfo(name);
    assertNotNull(info.getDescription());
    assertFalse(info.getDescription().isBlank());

    var depth = Arrays.stream(info.getAttributes())
        .filter(a -> a.getName().equals("QueueDepth"))
        .findFirst().orElseThrow();

    assertTrue(depth.isReadable());
    assertFalse(depth.isWritable());
    assertTrue(depth.getDescription().contains("Pending"));

    var pause = Arrays.stream(info.getOperations())
        .filter(op -> op.getName().equals("pause"))
        .findFirst().orElseThrow();

    assertTrue(pause.getDescription().contains("graceful"));
}
~~~

Bài test cần bảo đảm exporter dùng metadata annotation. Nên kiểm tra cả attribute/operation names, types và signatures vì description đúng nhưng contract runtime sai vẫn gây lỗi. Với operation có tác động, chỉ thử invocation trong test environment có dữ liệu giả lập.

## 17. Vận hành API như một hợp đồng có phiên bản

Các thay đổi cần cập nhật description và runbook:

- Đổi ObjectName/domain làm dashboard mất target.
- Đổi attribute name hoặc type làm JMX client không đọc được.
- Đổi đơn vị ms thành seconds nhưng giữ tên cũ khiến cảnh báo sai.
- Đổi operation từ synchronous sang asynchronous khiến runbook xác minh sớm.
- Đổi phạm vi từ node-local sang cluster-wide làm tăng rủi ro.
- Đổi exception/error behavior hoặc quyền yêu cầu thao tác.

Khi thay đổi, cập nhật đồng thời mã nguồn, metadata, tests, runbook, automation scripts và release notes. Nếu là breaking change, dùng kế hoạch di chuyển tương thích thay vì silently đổi ý nghĩa.

## 18. Checklist cho người thiết kế management API

1. ObjectName có namespace rõ, không lộ dữ liệu nhạy cảm.
2. MBean description nói rõ thành phần và phạm vi.
3. Attribute description có ý nghĩa, đơn vị, freshness và read/write.
4. Operation description nêu hành động và tác động.
5. Parameter description có tên, type, format/range và ví dụ an toàn.
6. Getter nhẹ, không có side effect và phù hợp polling.
7. Operation quan trọng có permission, audit, precondition và rollback.
8. Documentation có ví dụ JConsole/Java không chứa credential.
9. \`MBeanInfo\` của MBean được đăng ký phản ánh mô tả thực tế.
10. README/runbook được quản lý cùng phiên bản application.
11. Monitoring/automation tương thích với ObjectName và signatures.
12. Có integration tests bảo vệ contract và lời gọi có kiểm soát.

## 19. Ghi nhớ

**Mô tả và ví dụ sử dụng là một phần của hợp đồng vận hành JMX.** Spring cung cấp \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` và metadata tham số để đưa description vào MBeanInfo. README/runbook bổ sung điều kiện trước, tác động, cách xác minh và phục hồi. Luôn kiểm chứng trên MBeanInfo thực tế, không nhầm description với quyền truy cập, và tránh ví dụ operation nguy hiểm không có cảnh báo.
