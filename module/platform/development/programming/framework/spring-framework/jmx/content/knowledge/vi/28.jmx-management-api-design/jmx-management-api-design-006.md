# Tách lệnh chẩn đoán khỏi lệnh thay đổi trạng thái trong Spring Framework JMX

## 1. Mục tiêu

JMX là giao diện quản trị runtime của ứng dụng Java. Trong Spring Framework, bean có thể được export thành MBean nhờ `MBeanExporter`, `@ManagedResource`, `@ManagedAttribute` và `@ManagedOperation`. Qua JConsole, VisualVM hoặc `MBeanServerConnection`, người vận hành có thể đọc trạng thái hoặc gọi phương thức quản trị của ứng dụng.

Vấn đề thiết kế quan trọng là **không trộn lẫn lệnh chỉ phục vụ chẩn đoán với lệnh làm thay đổi trạng thái**. Một thao tác có tên `inspect`, `getStatus` hoặc `diagnose` nhưng bên trong lại reset counter, reload config, xóa cache, mở connection hoặc chạy job có thể gây sự cố khi công cụ monitoring gọi lặp lại.

Management API nên tách hai nhóm rõ ràng:

- **Quan sát/chẩn đoán (read/query):** đọc snapshot trạng thái hiện tại, số liệu tổng hợp, health, counters, version hoặc thông tin an toàn; không làm thay đổi business state.
- **Điều khiển/thay đổi (command):** reload cấu hình, pause/resume processing, clear cache, reset counter, rotate pool, trigger retry hoặc thay đổi một tham số runtime.

**Nguyên tắc chính:** những gì chỉ dùng để quan sát phải **không có side effect đáng kể**; thao tác điều khiển phải có tên và hợp đồng rõ ràng, quyền riêng, validation, giới hạn tài nguyên, audit và chiến lược xử lý lỗi.

## 2. Tại sao phải tách? JMX client có thể tự động gọi nhiều lần

JMX monitoring thường polling attributes theo chu kỳ, ví dụ mỗi 10–30 giây. Nếu `getQueueDepth()` vô tình xóa job lỗi hoặc `getCacheStats()` reset counter thì dashboard có thể thay đổi behavior của ứng dụng chỉ bằng một lần đọc.

```text
Monitoring collector (periodic polling)
          |
          v
JMX getAttribute("QueueDepth")
          |
          v
Safe getter -> chỉ đọc snapshot

Operator (explicit action)
          |
          v
JMX invoke("pauseProcessing")
          |
          v
Command -> validation -> state change -> audit
```

Ngoài rủi ro polling, các công cụ quản trị có thể retry khi gặp timeout, hoặc một người dùng nhầm một operation vì tên gợi ý nó chỉ đọc. Tách query/command giúp giảm rủi ro vận hành và làm API dễ phân quyền hơn.

## 3. Phân biệt JMX attribute và operation

| Khái niệm | Ngữ nghĩa tốt nên hướng tới | Ví dụ |
| --- | --- | --- |
| Read-only attribute | Trạng thái quan sát, getter nhanh | `QueueDepth`, `ActiveWorkers`, `LastErrorCategory` |
| Writable attribute | Thay đổi cấu hình runtime có kiểm soát | `Enabled`, `MaxWorkers` |
| Diagnostic operation | Chẩn đoán có thể tốn tài nguyên, vẫn không làm đổi business state | `collectThreadSummary()`, `sampleCacheKeys(int limit)` |
| Control operation | Thao tác thay đổi trạng thái | `pause()`, `resume()`, `clearCache()` |

Không phải mọi operation đều thay đổi trạng thái; một operation có thể chỉ đọc nhưng cần tham số hoặc tính toán. Tuy nhiên đặt phần **diagnostic operations** riêng với phần **commands** giúp người vận hành biết operation nào an toàn để gọi lặp lại, operation nào phải được phê duyệt.

JMX attribute có setter trở thành writable, nên việc công bố `setEnabled(boolean)` thực chất là một **command** dù nhìn trong UI như sửa thuộc tính. Không mặc định mọi attribute đều read-only.

## 4. Anti-pattern: getter có side effect

```java
@ManagedAttribute
public int getFailedTaskCount() {
    int failed = failedTaskCounter.get();
    failedTaskCounter.set(0);  // Sai: polling làm mất số liệu.
    return failed;
}
```

Nếu collector đọc thuộc tính mỗi phút, counter tự reset mỗi phút. Người vận hành nhìn dashboard khó biết tổng số lỗi và số liệu của hai collector còn có thể khác nhau.

Thiết kế đúng hơn:

```java
@ManagedAttribute(description = "Tổng số task thất bại")
public long getFailedTaskCount() {
    return failedTaskCounter.get();
}

@ManagedOperation(description = "Reset counter lỗi theo yêu cầu")
public void resetFailedTaskCounter() {
    authorization.requireOperator();
    failedTaskCounter.set(0);
    audit.record("reset-failed-task-counter");
}
```

`authorization` và `audit` là abstractions do ứng dụng cung cấp. Trong production, logic reset có thể cần xử lý đồng thời với việc tăng counter; nếu phép reset có thể làm mất dữ liệu quan trọng, nên chọn thiết kế counter monotonic và tạo metric theo window thay vì reset thủ công.

## 5. Anti-pattern: lệnh có tên diagnose nhưng tự thay đổi trạng thái

```java
@ManagedOperation
public String diagnoseConnectivity() {
    reconnectAllClients();       // Tác động lớn.
    clearConnectionCache();      // Side effect.
    return runConnectivityTest();
}
```

Tên `diagnoseConnectivity` tạo kỳ vọng đọc/kiểm tra, nhưng method lại làm thay đổi các kết nối thật. Khi operator gọi lệnh để xem tình trạng, hành vi ứng dụng thay đổi ngay và có thể làm mất dấu vết lỗi.

Nên tách:

```java
@ManagedOperation(description = "Đọc trạng thái connectivity gần nhất")
public String getConnectivitySummary() {
    return diagnostics.safeConnectivitySummary();
}

@ManagedOperation(description = "Yêu cầu thử kết nối có kiểm soát")
public String runConnectivityProbe() {
    return diagnostics.runBoundedProbe();
}

@ManagedOperation(description = "Yêu cầu tạo lại các connection")
public void reconnectClients() {
    commands.reconnectClients();
}
```

Ngay cả `runConnectivityProbe()` cũng có thể dùng network/CPU và gây side effect nhỏ (thêm một request hoặc tạo connection ngắn). Vì vậy cần mô tả **chi phí chẩn đoán**, timeout và tần suất cho phép. “Read-only” trong management API nên được hiểu là không thay đổi business state, không có nghĩa hoàn toàn không tiêu thụ tài nguyên.

## 6. Tách management interface theo CQRS

Có thể áp dụng nguyên tắc Command Query Responsibility Segregation (CQRS) ở mức API quản trị nhỏ:

```java
public interface QueueDiagnostics {
    int getQueueDepth();
    long getCompletedCount();
    String getHealthSummary();
}

public interface QueueCommands {
    void pauseProcessing();
    void resumeProcessing();
    void requestRefresh();
}
```

Hai interface giúp tách trách nhiệm ở code, dù JMX không tự phân quyền chỉ dựa trên việc chúng là hai interface Java. Có thể export thành hai MBean có ObjectName riêng:

```text
com.example.jobs:type=QueueDiagnostics,name=Main
com.example.jobs:type=QueueControl,name=Main
```

Việc tách ObjectName giúp cấu hình allowlist, thao tác và giám sát rõ ràng hơn. Nhưng nếu các MBean cùng nằm trong một MBeanServer/connector được cấp quyền admin đầy đủ, sự tách biệt **không tự biến thành security boundary**. Phải bảo vệ quyền đọc/gọi operation ở connector hoặc môi trường chạy.

## 7. Ví dụ Spring JMX đầy đủ: MBean chỉ đọc

```java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=QueueDiagnostics,name=Main",
    description = "Quan sát queue mà không thay đổi trạng thái"
)
public class QueueDiagnosticsMBean {
    private final QueueMetrics metrics;

    public QueueDiagnosticsMBean(QueueMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Số job đang chờ")
    public int getQueueDepth() {
        return metrics.pendingCount();
    }

    @ManagedAttribute(description = "Số job đã hoàn thành")
    public long getCompletedCount() {
        return metrics.completedCount();
    }

    @ManagedAttribute(description = "Trạng thái tổng hợp")
    public String getHealthSummary() {
        return metrics.safeHealthSummary();
    }
}
```

`QueueMetrics` là interface/service ứng dụng cần định nghĩa. Getter nên trả snapshot có giới hạn, không gọi trực tiếp database query nặng nếu collector polling thường xuyên, không chứa secrets hoặc dữ liệu cá nhân.

Với annotation-based export, `@ManagedAttribute` chỉ được dùng trên getter nên các attribute trên dự kiến read-only. Nếu sau này thêm setter và annotate, contract sẽ đổi thành writable; cần đánh giá như một thay đổi quyền quản trị.

## 8. MBean điều khiển riêng

```java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=QueueControl,name=Main",
    description = "Các thao tác điều khiển queue"
)
public class QueueControlMBean {
    private final QueueControlService commands;
    private final ManagementAudit audit;

    public QueueControlMBean(
            QueueControlService commands,
            ManagementAudit audit) {
        this.commands = commands;
        this.audit = audit;
    }

    @ManagedOperation(description = "Tạm dừng nhận job mới")
    public void pauseProcessing() {
        commands.pauseProcessing();
        audit.record("pause-processing");
    }

    @ManagedOperation(description = "Tiếp tục nhận job")
    public void resumeProcessing() {
        commands.resumeProcessing();
        audit.record("resume-processing");
    }

    @ManagedOperation(description = "Yêu cầu làm mới cấu hình worker")
    public void requestRefresh() {
        commands.requestRefresh();
        audit.record("request-refresh");
    }
}
```

`QueueControlService` và `ManagementAudit` là các abstraction minh họa. Với thao tác quan trọng, audit nên ghi nhận cả request, kết quả thành công/thất bại và correlation ID an toàn, không chỉ ghi sau khi gọi command thành công. Không lưu secret, token hoặc thông tin cá nhân vào audit event.

## 9. Bật annotation-based MBean export

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Đảm bảo hai bean quản trị được Spring phát hiện hoặc khai báo trong ApplicationContext. `@EnableMBeanExport` giúp Spring cấu hình hạ tầng đọc metadata annotation và export các bean có quản trị phù hợp. Nếu ứng dụng có một `MBeanExporter` thủ công dùng reflection assembler, cần tránh export cùng object name hoặc vô tình expose thêm public methods.

Với thiết kế hai MBean, operator có thể nhận diện nhanh:

```text
JConsole
  com.example.jobs
    QueueDiagnostics, Main
      Attributes: QueueDepth, CompletedCount, HealthSummary
    QueueControl, Main
      Operations: pauseProcessing, resumeProcessing, requestRefresh
```

Giao diện thực tế phụ thuộc JConsole và MBeanInfo do assembler tạo. Điều quan trọng là không đặt các operation tác động trạng thái trong diagnostic MBean chỉ vì hai phần dùng cùng một service bên trong.

## 10. Read-only management adapter không nên expose service nghiệp vụ

Anti-pattern:

```java
@ManagedResource
public class JobService {
    public int getQueueDepth() { /* ... */ return 0; }
    public void deleteAllJobs() { /* ... */ }
    public void retryFailedJob(String id) { /* ... */ }
}
```

Nếu dùng reflection assembler, các public methods như `deleteAllJobs` có thể trở thành JMX operation không mong muốn. Một class mang `@ManagedResource` cũng không tự đảm bảo an toàn nếu exporter đang dùng assembler khác không tôn trọng annotation allowlist.

Nên export management adapter chuyên dụng và chỉ annotate những methods có ý nghĩa quản trị. Khi không thể sửa source, có thể dùng `InterfaceBasedMBeanInfoAssembler` hoặc `MethodNameBasedMBeanInfoAssembler` để tạo allowlist có kiểm soát.

Đừng nhầm Java method `public` với “được phép gọi qua JMX”. Contract quản trị phải là lựa chọn chủ động.

## 11. Quy tắc đặt tên cho query và command

### Nhóm chẩn đoán

Các tên dễ hiểu: `get...`, `is...`, `list...`, `describe...`, `sample...`, `getStatus...`, `getSummary...`. Nếu có tham số hoặc tính toán tốn tài nguyên, dùng operation `collect...` hoặc `run...Probe` kèm mô tả chi phí, thay vì biến thành getter bị polling vô hạn.

Ví dụ:

```text
getActiveWorkerCount
getQueueDepth
getLastSafeErrorCategory
getConnectionState
collectThreadSummary(maxThreads)
```

### Nhóm thay đổi trạng thái

Tên nên mang nghĩa chủ động: `request...`, `pause...`, `resume...`, `clear...`, `reset...`, `reload...`, `rotate...`, `shutdown...`. Tránh tên mơ hồ như `update()`, `fix()`, `checkAndRepair()` nếu người vận hành không biết mức tác động.

Ví dụ:

```text
requestRefresh
pauseProcessing
resumeProcessing
clearCache
resetFailureCounters
requestShutdown
```

Trong Java, name không đảm bảo semantics. Tên chỉ hỗ trợ hiểu contract; enforcement vẫn nằm trong implementation, security và tests.

## 12. Commands cần validation và giới hạn tài nguyên

Ví dụ một operation sửa worker limit:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Thay đổi giới hạn worker")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "limit", description = "Giá trị từ 1 tới 64"
    )
})
public void setWorkerLimit(int limit) {
    if (limit < 1 || limit > 64) {
        throw new IllegalArgumentException(
            "limit must be within [1, 64]"
        );
    }
    commands.updateWorkerLimit(limit);
}
```

Không cho operator đặt giá trị không giới hạn gây cạn CPU, thread hoặc memory. Với mọi command, xác định:

- Điều kiện tiên quyết (preconditions).
- Khoảng giá trị hợp lệ.
- Trạng thái sau thành công và hành vi nếu gọi lặp.
- Timeout, concurrency, conflict khi hai operator cùng invoke.
- Cách rollback hoặc recovery nếu operation thất bại giữa chừng.
- Audit và quyền yêu cầu hành động.

Một command trả `void` không có nghĩa nó hoàn thành tức thì. Đối với công việc dài, nên trả `requestId` không nhạy cảm hoặc expose trạng thái qua diagnostic attribute thay vì giữ JMX invocation treo vô hạn.

## 13. Idempotency cho operation thay đổi trạng thái

Những command như `pauseProcessing()` thường có thể làm idempotent: gọi hai lần cùng dẫn tới trạng thái paused. Những command như `retryJob()` hoặc `clearCache()` có thể không có tính chất đó.

Ví dụ:

```java
@ManagedOperation
public void pauseProcessing() {
    if (!state.isPaused()) {
        state.pause();
    }
}
```

Trong môi trường concurrent, đoạn check-then-act đơn giản có race condition nếu nhiều thread đồng thời thay state; implementation cần cơ chế đồng bộ/atomic phù hợp. Ví dụ chỉ minh họa ngữ nghĩa idempotent mong muốn.

Không tự retry JMX commands có side effect sau timeout: request có thể đã thành công phía server nhưng client không nhận được phản hồi. Nếu cần retry an toàn, dùng request ID/idempotency key và trạng thái command được kiểm soát.

## 14. Phân quyền: tách MBean không đồng nghĩa tách quyền

Mặc dù hai ObjectName `QueueDiagnostics` và `QueueControl` phân biệt hợp đồng quản trị, một JMX client có quyền invoke toàn bộ server vẫn có thể gọi command. Cần thiết kế:

1. **Read-only operator/monitoring roles** có quyền đọc attributes cần thiết.
2. **Privileged operator roles** có quyền invoke commands được cho phép.
3. Authentication và authorization ở JMX connector hoặc lớp quản lý MBean thích hợp.
4. Network segmentation, TLS và quản trị credentials.
5. Audit các lệnh điều khiển ở application layer.

Không mặc định Spring Security bảo vệ HTTP API cũng tự bảo vệ mọi JMX connector. Với local JMX, các quyền thực tế phụ thuộc JVM, MBeanServer và môi trường truy cập.

Tách `QueueControl` thành MBean riêng giúp dễ review và viết policy hơn, nhưng chỉ có ý nghĩa bảo mật khi enforcement đúng.

## 15. Chẩn đoán nên trả snapshot, không trả dữ liệu nội bộ thô

Thay vì:

```java
@ManagedAttribute
public List<Job> getPendingJobs() {
    return queue.getAllPendingJobs();
}
```

nên trả số liệu tổng hợp:

```java
@ManagedAttribute
public int getPendingJobCount() {
    return queue.pendingCount();
}
```

Nếu thật sự cần lấy mẫu một tập nhỏ job để debug, dùng operation có tham số và giới hạn:

```java
@ManagedOperation(description = "Lấy mẫu tối đa N job chờ")
public String getPendingJobSummary(int maxItems) {
    int limit = Math.max(1, Math.min(maxItems, 20));
    return diagnostics.safePendingJobSummary(limit);
}
```

Đầu ra phải loại PII/secrets và có giới hạn kích thước, kể cả khi operator có quyền cao. Diagnostic operation trả kết quả lớn hoặc quét database có thể làm hệ thống chậm; đặt timeout/limit và không chạy từ thread critical path.

## 16. Kết hợp notifications theo hướng một chiều

JMX notification hữu ích khi muốn báo rằng một sự kiện đã xảy ra:

```text
Control operation: requestRefresh
     |
     v
Command accepted
     |
     v
Background refresh
     |
     +--> Diagnostic attribute: RefreshState
     +--> Notification: refresh.completed / refresh.failed
```

Không nên bắt người vận hành gọi `getRefreshState()` mà mỗi lần đọc lại kích hoạt refresh. Chẩn đoán quan sát tiến trình; command khởi động hành động; notification thông báo chuyển trạng thái.

Khi client nhận notification, nên đọc lại attribute để xác nhận trạng thái hiện tại. JMX notification có thể bị mất khi client chưa subscribe hoặc connector bị ngắt; không phải message broker durable.

## 17. Thiết kế operation dài bằng request/observe

Một phương án tốt cho operation tốn thời gian:

```java
@ManagedOperation(description = "Yêu cầu rebuild index bất đồng bộ")
public String requestIndexRebuild() {
    return jobs.submitIndexRebuild();
}

@ManagedAttribute(description = "Trạng thái rebuild gần nhất")
public String getIndexRebuildStatus() {
    return jobs.getSafeCurrentStatus();
}
```

`submitIndexRebuild` trả một request ID an toàn hoặc trạng thái accepted. Worker nền chịu trách nhiệm thực hiện. Khi ứng dụng nhận event hoàn tất, có thể phát notification.

Với cách này JMX invocation không phải giữ thread chờ đến khi công việc xong. Cần có giới hạn số job đồng thời, khả năng từ chối khi backlog đầy và cách xác định idempotency để operator không vô tình tạo nhiều job.

## 18. Kiểm tra MBeanInfo để đối chiếu contract

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName diagnostics = new ObjectName(
    "com.example.jobs:type=QueueDiagnostics,name=Main"
);
ObjectName control = new ObjectName(
    "com.example.jobs:type=QueueControl,name=Main"
);

for (ObjectName name : new ObjectName[]{diagnostics, control}) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println(name.getCanonicalName());
    for (var attr : info.getAttributes()) {
        System.out.printf(
            "  Attribute %s writable=%s%n",
            attr.getName(), attr.isWritable()
        );
    }
    for (var op : info.getOperations()) {
        System.out.println("  Operation " + op.getName());
    }
}
```

Đoạn code giả định hai MBean đã được đăng ký vào platform MBeanServer. Nếu exporter dùng server khác, phải dùng đúng server đó. Đọc metadata là cách xác nhận contract JMX cuối cùng; không cần gọi operation thay đổi state để xác định nó có trong API.

## 19. Các lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách cải thiện |
| --- | --- | --- |
| Dashboard đọc getter khiến số liệu reset | Getter có side effect | Chuyển reset thành command rõ ràng |
| Operator chạy `diagnose()` nhưng service bị restart | Operation chẩn đoán gộp hành động sửa chữa | Tách `getStatus` và `requestRestart` |
| Monitoring user gọi được `clearCache()` | Connector cho phép invoke quá rộng | Phân quyền riêng command và kiểm soát ở server |
| Attribute bị writable ngoài ý muốn | Export setter public | Chỉ công bố getter hoặc dùng metadata allowlist |
| Command bị gọi nhiều lần sau timeout | Client retry không có idempotency | Dùng request ID, status và chính sách retry |
| `getConfig()` trả secrets | Chẩn đoán trả raw config | Trả safe summary, redact và giới hạn field |
| MBean có quá nhiều methods | Export business service bằng reflection | Management adapter/interface chọn lọc |
| Operation chẩn đoán làm ứng dụng chậm | Quét tài nguyên lớn không giới hạn | Bounded sampling, timeout và offload |
| Command lỗi nhưng thiếu audit | Không ghi attempt/result | Audit các lần gọi và kết quả, không ghi secrets |

## 20. Checklist cho management API

- [ ] Getter JMX không làm thay đổi business state.
- [ ] Attribute writable được xác định rõ và chỉ expose khi cần.
- [ ] Diagnostic operation có mô tả về chi phí, giới hạn và kết quả.
- [ ] Command được đặt tên bằng động từ chủ động và mô tả side effect.
- [ ] Tách management adapter/interface theo read và control khi phù hợp.
- [ ] Có validation, concurrency guard, timeout hoặc idempotency cho command.
- [ ] Không tự retry lệnh có side effect sau timeout mà không có idempotency.
- [ ] Chẩn đoán không trả secrets, token, PII hoặc object graph lớn.
- [ ] Quyền invoke được kiểm soát riêng, không chỉ dựa trên tên MBean.
- [ ] Có audit an toàn cho các command quan trọng.
- [ ] MBeanInfo phản ánh đúng attributes/operations dự kiến.
- [ ] ObjectName và management contract ổn định cho dashboard/proxy.

## 21. Mô hình tư duy kết luận

```text
Spring application
   |
   +-- Query/Diagnostics API
   |      +-- getQueueDepth
   |      +-- getHealthSummary
   |      +-- getCompletedCount
   |      +-- collectBoundedSnapshot
   |      -> Read-only MBean
   |
   +-- Command/Control API
          +-- pauseProcessing
          +-- resumeProcessing
          +-- requestRefresh
          +-- requestIndexRebuild
          -> Privileged MBean
                  |
                  v
             Validation + Audit + Execution
                  |
                  v
             Status attribute / Notification
```

**Kết luận:** tách lệnh chẩn đoán khỏi lệnh thay đổi trạng thái giúp Spring JMX trở thành management API dễ hiểu, an toàn và ổn định hơn. Getters và diagnostic operations nên nhẹ, có giới hạn, không làm thay đổi trạng thái; commands phải chủ động, có kiểm soát quyền, validation, concurrency và audit. Sự phân tách bằng interface/MBean riêng là công cụ thiết kế rõ ràng, nhưng bảo mật vẫn phải được thực thi tại connector/MBeanServer và logic ứng dụng.
