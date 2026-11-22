# Job định kỳ gọi operation và kiểm tra điều kiện trong Spring Framework JMX

## 1. Mục tiêu học tập

Trong hệ thống Java vận hành lâu dài, một thao tác JMX đôi khi không chỉ được người quản trị gọi thủ công qua JConsole. Một **job định kỳ** có thể kết nối tới `MBeanServer`, đọc attribute, đối chiếu với điều kiện vận hành, rồi quyết định có cần gọi một management operation hay không. Mẫu này xuất hiện trong các bài toán tự động phục hồi, dọn cache có kiểm soát, kích hoạt bảo trì, đổi chế độ xử lý hoặc xác minh trạng thái scheduler.

Bài học thuộc nhóm **Quan sát và tự động hóa** của Spring Framework JMX. Trọng tâm là thiết kế **job định kỳ gọi operation và kiểm tra điều kiện** một cách có chủ đích, đo được kết quả, giới hạn tác động và không biến kênh JMX thành nguồn thực thi lệnh nguy hiểm không kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt job **polling trạng thái** với job **thực hiện điều khiển**.
- Đọc attribute qua `MBeanServerConnection.getAttribute(...)`.
- Gọi operation qua `MBeanServerConnection.invoke(...)` với đúng `ObjectName`, tham số và signature.
- Dùng Spring `@Scheduled` hoặc scheduler phù hợp để chạy định kỳ.
- Tổ chức flow: quan sát → kiểm tra điều kiện → chống gọi lặp → thực thi → xác minh → ghi nhận.
- Nhận biết race condition, timeout, kết nối mất giữa chừng và tác động từ nhiều job cùng chạy.
- Thiết kế idempotency, cooldown, retry có giới hạn, audit, quyền truy cập và cơ chế dừng tự động hóa.
- Phân biệt metadata của MBean với trạng thái hiện tại và kết quả cuối của operation.

## 2. Bài toán thực tế

Giả sử một ứng dụng có bộ xử lý nền `WorkerControl` được export qua Spring JMX. MBean công bố:

```text
ObjectName:
com.example.ops:type=WorkerControl,name=Primary

Attributes:
- PendingJobs: int (read-only)
- AcceptingJobs: boolean (read-only)
- LastMaintenanceResult: String (read-only)

Operations:
- pauseProcessing()
- resumeProcessing()
- requestMaintenance()
```

Yêu cầu: cứ một khoảng thời gian, job quản trị kiểm tra số lượng công việc đang chờ. Nếu `PendingJobs` vượt ngưỡng trong một khoảng liên tục, thay vì tự động “xóa hết queue”, hệ thống có thể tạo cảnh báo hoặc yêu cầu maintenance đã được kiểm soát. Sau khi gọi, job xác minh operation có được chấp nhận và trạng thái có chuyển đúng không.

Điểm cốt lõi: **điều kiện kích hoạt phải gắn với một mục đích vận hành cụ thể và cơ chế kiểm soát rủi ro**, không nên cứ thấy một chỉ số cao là gọi một operation thay đổi trạng thái.

Ví dụ điều kiện:

```text
pendingJobs > 500
AND trạng thái xử lý vẫn RUNNING
AND ngưỡng vi phạm >= 3 lần poll liên tiếp
AND chưa có maintenance đang chạy
AND đã hết cooldown
THEN requestMaintenance()
```

Đây là điều kiện minh họa. Ngưỡng thực tế phải dựa trên năng lực hệ thống, yêu cầu nghiệp vụ, chi phí operation và khả năng phục hồi.

## 3. Luồng kiến trúc

```text
Scheduler / @Scheduled
         |
         v
   Read MBean attributes
         |
         v
    Evaluate condition
         |
    +----+----------------------+
    | condition false          | condition true
    v                          v
   Record                       Check safety guards
   observation                    |
                                  +-- maintenance running? -> SKIP
                                  +-- cooldown active?     -> SKIP
                                  +-- not authorized?      -> STOP
                                  |
                                  v
                             Invoke operation
                                  |
                                  v
                             Verify outcome
                                  |
                                  v
                        Metrics / logs / audit / alerts
```

Có ba nhóm trách nhiệm cần tách:

1. **Observer**: đọc trạng thái và tạo bằng chứng về điều kiện.
2. **Decision policy**: xác định khi nào được thực thi, bao gồm ngưỡng, hysteresis, cooldown, quyền và phạm vi.
3. **Executor**: gọi operation theo contract, ghi nhận và xác minh kết quả.

Phân tách này giúp kiểm thử được chính sách mà không cần gọi operation thật, đặc biệt với thao tác có side effect lớn.

## 4. JMX là cơ chế truy cập, không phải scheduler

JMX cung cấp `MBeanServer`, `MBeanServerConnection`, ObjectName, attribute và operation. Nó **không tự chạy lịch định kỳ** chỉ vì một method có `@ManagedOperation`.

Ví dụ Spring JMX:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.ops:type=WorkerControl,name=Primary",
    description = "Operational controls for background workers"
)
public class WorkerControl {

    @ManagedAttribute(description = "Number of pending jobs")
    public int getPendingJobs() {
        return 0; // Ví dụ, ứng dụng thật đọc từ queue monitor.
    }

    @ManagedOperation(
        description = "Request a maintenance operation"
    )
    public String requestMaintenance() {
        return "ACCEPTED";
    }
}
```

Một job định kỳ là thành phần khác: có thể dùng `@Scheduled`, Quartz, scheduler trong orchestration platform hoặc một dịch vụ vận hành riêng. Job đọc/call MBean bằng client JMX như bất kỳ consumer nào khác.

**Không đồng nhất `@ManagedOperation` với `@Scheduled`:**

- `@ManagedOperation` công bố hành động quản trị qua JMX.
- `@Scheduled` yêu cầu Spring scheduling gọi một phương thức theo lịch.
- Có thể dùng cả hai trong một ứng dụng, nhưng chúng không tự kết nối hoặc ràng buộc với nhau.

## 5. Thiết kế MBean có trạng thái quan sát được

Nếu job tự động hóa có thể gọi operation, MBean cần công bố đủ thông tin để job biết khi nào nên gọi và xác minh lời gọi.

Ví dụ service:

```java
package com.example.ops;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceService {

    private final AtomicInteger pendingJobs =
        new AtomicInteger();

    private final AtomicBoolean maintenanceRunning =
        new AtomicBoolean();

    private volatile String lastOutcome = "NEVER_RUN";

    public int getPendingJobs() {
        return pendingJobs.get();
    }

    public boolean isMaintenanceRunning() {
        return maintenanceRunning.get();
    }

    public String getLastOutcome() {
        return lastOutcome;
    }

    public String requestMaintenance() {
        if (!maintenanceRunning.compareAndSet(false, true)) {
            return "ALREADY_RUNNING";
        }

        try {
            // Trong thực tế: giao việc cho job executor
            // đã được quản lý vòng đời.
            runMaintenance();
            lastOutcome = "SUCCESS";
            return "COMPLETED";
        } catch (RuntimeException ex) {
            lastOutcome = "FAILED";
            throw ex;
        } finally {
            maintenanceRunning.set(false);
        }
    }

    private void runMaintenance() {
        // Logic vận hành có giới hạn và kiểm soát.
    }
}
```

MBean adapter:

```java
package com.example.ops;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=MaintenanceControl,name=Primary",
    description = "Read maintenance state and request controlled maintenance"
)
public class MaintenanceControl {

    private final MaintenanceService service;

    public MaintenanceControl(MaintenanceService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending job count")
    public int getPendingJobs() {
        return service.getPendingJobs();
    }

    @ManagedAttribute(description = "Whether maintenance is running")
    public boolean isMaintenanceRunning() {
        return service.isMaintenanceRunning();
    }

    @ManagedAttribute(description = "Last maintenance result")
    public String getLastOutcome() {
        return service.getLastOutcome();
    }

    @ManagedOperation(
        description = "Request bounded maintenance on this instance"
    )
    public String requestMaintenance() {
        return service.requestMaintenance();
    }
}
```

Mẫu minh họa này thực thi maintenance đồng bộ. Nếu tác vụ kéo dài, nên chuyển sang executor/job queue, trả request ID và công bố trạng thái tiến trình cùng kết quả cuối. Không nên giữ một JMX invoke call chờ công việc nặng không giới hạn.

### 5.1. Vì sao cần trạng thái?

Nếu job chỉ gọi `requestMaintenance()` rồi bỏ qua kết quả, nó không phân biệt được:

- Request bị từ chối vì đang có công việc khác.
- Operation đã hoàn thành thành công.
- Operation đã khởi chạy nhưng vẫn đang xử lý.
- JMX transport bị ngắt và không rõ server có nhận request chưa.
- Có worker khác xử lý cùng thời điểm.

Attribute trạng thái giúp job đối chiếu thực tế sau khi gọi và giảm retry mù.

## 6. Đọc attribute qua MBeanServerConnection

Đối với local server:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.ops:type=MaintenanceControl,name=Primary"
);

int pending = (Integer) server.getAttribute(
    name,
    "PendingJobs"
);

boolean running = (Boolean) server.getAttribute(
    name,
    "MaintenanceRunning"
);

System.out.printf(
    "pending=%d running=%s%n",
    pending, running
);
```

Nếu Spring exporter dùng một `MBeanServer` riêng, cần lấy đúng server đó thay vì platform server. Một MBean được đăng ký ở server riêng có thể không xuất hiện trong platform registry.

Đối với remote client, lấy `MBeanServerConnection` từ `JMXConnector`:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;

MBeanServerConnection connection =
    connector.getMBeanServerConnection();

Object value =
    connection.getAttribute(name, "PendingJobs");
```

Trong cả hai trường hợp, code đều đọc giá trị hiện tại; `MBeanInfo` là công cụ khám phá metadata như attribute name, type và readable/writable, không thay thế `getAttribute`.

## 7. Gọi operation bằng invoke

Sau khi điều kiện được chấp nhận, job gọi:

```java
Object result = connection.invoke(
    name,
    "requestMaintenance",
    new Object[0],
    new String[0]
);
```

`ObjectName` phải là tên MBean đã đăng ký trên connection đang dùng. `operationName` phải xuất hiện trong `MBeanInfo.getOperations()`, với chữ ký tham số đúng.

Operation có tham số:

```java
Object result = connection.invoke(
    name,
    "setThreshold",
    new Object[] { Integer.valueOf(750) },
    new String[] { "int" }
);
```

Trong ví dụ, `"int"` là kiểu tham số Java khai báo trong method, không phải tên wrapper `java.lang.Integer`. Nếu operation khai báo `Integer`, signature lại khác.

Không nên coi mọi lời gọi trả về `null` là lỗi: một operation `void` thường trả `null`. Với operation thay đổi trạng thái, cần định nghĩa riêng cách xác minh tác động.

## 8. Viết job định kỳ bằng Spring @Scheduled

Kích hoạt scheduling:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfig {
}
```

Ví dụ job dùng `MBeanServer` được inject cùng ứng dụng:

```java
package com.example.ops;

import java.time.Duration;
import java.time.Instant;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MaintenancePollingJob {

    private final MBeanServer server;
    private final ObjectName objectName;

    private int consecutiveBreaches = 0;
    private Instant lastInvocation = Instant.EPOCH;

    public MaintenancePollingJob(MBeanServer server) throws Exception {
        this.server = server;
        this.objectName = new ObjectName(
            "com.example.ops:type=MaintenanceControl,name=Primary"
        );
    }

    @Scheduled(fixedDelayString = "${ops.maintenance.poll-delay-ms:30000}")
    public void pollAndMaybeInvoke() throws Exception {

        int pending = (Integer) server.getAttribute(
            objectName, "PendingJobs"
        );

        boolean running = (Boolean) server.getAttribute(
            objectName, "MaintenanceRunning"
        );

        consecutiveBreaches =
            pending > 500 ? consecutiveBreaches + 1 : 0;

        if (consecutiveBreaches < 3 || running) {
            return;
        }

        Instant now = Instant.now();
        if (Duration.between(
                lastInvocation, now).compareTo(Duration.ofMinutes(10)) < 0) {
            return;
        }

        Object result = server.invoke(
            objectName,
            "requestMaintenance",
            new Object[0],
            new String[0]
        );

        lastInvocation = now;
        consecutiveBreaches = 0;

        System.out.println("Maintenance invoke result: " + result);
    }
}
```

Đây là **ví dụ minh họa policy đơn giản**, chưa phải implementation production đầy đủ. Nó giả định một scheduler không chạy chồng cùng instance job. Nếu nhiều node/pod hoặc nhiều scheduler cùng chạy, mỗi job có `lastInvocation` riêng và có thể cùng gọi operation. Cần thêm cơ chế leader election, distributed lock, lease hoặc conditional execution ở phía server.

### 8.1. Fixed delay khác fixed rate

- `fixedDelay`: chờ khoảng thời gian sau khi lần chạy trước kết thúc.
- `fixedRate`: lên lịch theo nhịp từ đầu lần chạy trước, có thể tạo hành vi khác nếu lần chạy lâu.
- `cron`: thực thi theo lịch biểu; phụ thuộc timezone và chính sách missed execution.

Đối với job gọi JMX có side effect, `fixedDelay` thường dễ kiểm soát hơn trong ví dụ đơn giản, nhưng không tự bảo đảm chống chạy chồng nếu hệ thống có nhiều instance hoặc scheduler executor được cấu hình phức tạp.

## 9. Đánh giá điều kiện: đừng chỉ kiểm tra một ngưỡng

Nếu `PendingJobs` dao động quanh 500, một điều kiện như:

```java
if (pending > 500) {
    invokeMaintenance();
}
```

có thể gọi liên tục khi số lượng tăng/giảm quanh ngưỡng. Thường cần:

- **Consecutive breaches**: vi phạm trong nhiều lần poll.
- **Hysteresis**: ngưỡng bật và ngưỡng trở lại bình thường khác nhau.
- **Cooldown**: thời gian tối thiểu giữa hai lần gọi.
- **MaintenanceRunning guard**: không gọi khi có job đang chạy.
- **Health guard**: không điều khiển nếu downstream đang ở trạng thái không an toàn.
- **Rate limit/budget**: tối đa số lần gọi mỗi giờ/ngày.
- **Human approval**: yêu cầu duyệt cho operation có blast radius lớn.

Ví dụ hysteresis:

```text
Enter alert state: PendingJobs >= 800
Exit alert state:  PendingJobs <= 400
```

Với policy này, chỉ số dao động 650–750 không liên tục bật/tắt trạng thái. Khi áp dụng cho operation thay đổi state, cần định nghĩa rõ khi nào cho phép điều khiển lại và khi nào chỉ cảnh báo.

## 10. Kiểm tra điều kiện trước và sau invoke

Một job có thể đọc state rồi gọi operation vài mili giây sau. Trong thời gian đó trạng thái có thể thay đổi.

```text
T1: Poller đọc MaintenanceRunning=false
T2: Operator thủ công gọi requestMaintenance()
T3: Poller cũng gọi requestMaintenance()
```

Nếu server implementation chỉ dựa vào kiểm tra từ client, hai thao tác có thể chạy song song.

Vì vậy, **precondition quan trọng phải được kiểm tra lại và thực thi nguyên tử ở phía MBean/service**, ví dụ:

```java
if (!maintenanceRunning.compareAndSet(false, true)) {
    return "ALREADY_RUNNING";
}
```

Client-side polling giúp giảm lời gọi không cần thiết, nhưng không phải cơ chế khóa cuối cùng.

Sau invoke, job cũng nên đọc lại trạng thái:

```java
String lastOutcome = (String) connection.getAttribute(
    name, "LastOutcome"
);

boolean running = (Boolean) connection.getAttribute(
    name, "MaintenanceRunning"
);
```

Lưu ý operation bất đồng bộ có thể trả `ACCEPTED` khi job còn chạy. Kết quả đọc ngay lúc đó không chắc là kết quả cuối.

## 11. Timeout, lỗi mạng và retry

Remote JMX có thể lỗi ở nhiều giai đoạn:

1. Client chưa tạo được kết nối.
2. Client đọc attribute thất bại.
3. Client gửi invoke nhưng không nhận được response.
4. Server thực hiện operation rồi trả lời, nhưng transport bị ngắt.
5. Client đọc lại state sau invoke thất bại.

Điểm nguy hiểm là trường hợp 3/4: **timeout không chứng minh operation chưa chạy**. Nếu job tự động retry ngay, có thể thực hiện trùng một thao tác không idempotent.

Quy tắc đề xuất:

- Với operation có side effect, ưu tiên idempotency hoặc request ID.
- Không retry vô hạn.
- Ghi `UNKNOWN_OUTCOME` khi không thể xác định kết quả.
- Sau lỗi, đọc trạng thái qua đường đáng tin cậy trước khi quyết định retry.
- Dùng exponential backoff và giới hạn tần suất nếu retry được phép.
- Có circuit breaker/kill switch cho automation khi liên tục lỗi.
- Phân biệt lỗi authentication, authorization, ObjectName không tồn tại và lỗi business logic.

Ví dụ xử lý:

```java
try {
    Object result = connection.invoke(
        name, "requestMaintenance",
        new Object[0], new String[0]
    );
    recordAcceptedResult(result);
} catch (Exception ex) {
    recordUnknownOutcome(ex);
    // Không tự động gọi lại ngay nếu chưa xác minh trạng thái.
}
```

Hàm `recordAcceptedResult` và `recordUnknownOutcome` là các điểm tích hợp telemetry/audit giả định.

## 12. Chống chạy đồng thời trên nhiều instance

Nếu ứng dụng chạy ba replica và mỗi replica có job `@Scheduled` giống nhau:

```text
Pod A -- poll --> JMX Target X
Pod B -- poll --> JMX Target X
Pod C -- poll --> JMX Target X
```

thì ba poller có thể cùng thấy điều kiện true. `@Scheduled` không tự cung cấp distributed lock. Các lựa chọn:

- Chỉ chạy scheduler ở một control-plane instance.
- Dùng leader election.
- Dùng distributed lock/lease với TTL và ownership rõ ràng.
- Đặt guard nguyên tử phía MBean/service.
- Cho operation nhận request ID để loại bỏ duplicate.
- Giới hạn concurrency và quota ở executor thực thi.

Nếu JMX target là từng pod riêng biệt, cần xác định policy hoạt động ở cấp instance hay cluster. Một ObjectName giống nhau ở ba JVM không chỉ cùng resource; automation phải gắn thêm identity của connection/server để tránh tác động nhầm.

## 13. Kết nối remote JMX an toàn cho automation

Khi poller chạy ở JVM khác, cần `JMXConnector` và endpoint phù hợp:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
);

try (JMXConnector connector =
        JMXConnectorFactory.connect(url, secureEnvironment)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    Object value = connection.getAttribute(
        name, "PendingJobs"
    );
}
```

`secureEnvironment` là biến giả định chứa cấu hình xác thực/connector từ nguồn quản lý secrets. Không hard-code mật khẩu hoặc token trong source.

Các yêu cầu bảo mật:

- JMX Remote ở mạng quản trị hạn chế.
- Authentication/TLS theo chính sách tổ chức.
- Quyền tối thiểu cho poller: đọc attribute và chỉ invoke operation cần thiết.
- Audit actor, target, operation và outcome.
- Không cho automation tùy ý thực thi operation ngoài allowlist.
- Không gửi credential qua URL, log hoặc thông báo lỗi.
- Có cơ chế thu hồi quyền/kill switch nhanh khi job hoạt động sai.

JMX là kênh quản trị có đặc quyền; việc tự động hóa lời gọi theo lịch làm tăng tác động của một cấu hình sai vì lỗi có thể lặp lại đều đặn.

## 14. Quản lý vòng đời của connection và scheduler

Một job polling liên tục phải quản lý tài nguyên:

- Đóng `JMXConnector` khi không sử dụng.
- Nếu tái sử dụng connector, phát hiện disconnect và khởi tạo lại có backoff.
- Không tạo hàng nghìn kết nối ngắn liên tiếp nếu polling quá dày.
- Ngừng scheduler trước khi đóng `ApplicationContext` và MBeanServer.
- Không để thread hoặc listener giữ classloader cũ sau redeploy.
- Xử lý khi MBean bị unregister hoặc ObjectName đổi.
- Ghi lại phiên bản contract của MBean nếu client phụ thuộc signature/type.

Một ứng dụng có thể dùng `MBeanServer` local và không cần connector network. Trong trường hợp đó, việc đọc trực tiếp service nội bộ có thể đơn giản hơn JMX; chỉ dùng JMX làm đường tích hợp nếu nó thực sự phù hợp với mục tiêu kiến trúc.

## 15. Kiểm tra MBeanInfo trước khi automation chạy

Đừng mặc định `PendingJobs` luôn là `int` hoặc operation luôn tồn tại sau một lần refactor.

Có thể kiểm tra contract:

```java
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = connection.getMBeanInfo(name);

boolean pendingFound = Arrays.stream(info.getAttributes())
    .anyMatch(a ->
        "PendingJobs".equals(a.getName())
        && "int".equals(a.getType())
        && a.isReadable()
    );

boolean operationFound = Arrays.stream(info.getOperations())
    .anyMatch(o ->
        "requestMaintenance".equals(o.getName())
        && o.getSignature().length == 0
    );

if (!pendingFound || !operationFound) {
    throw new IllegalStateException(
        "Incompatible JMX management contract"
    );
}
```

Metadata test cho biết interface đang công bố; nó không thay thế việc xử lý lỗi runtime. MBean có thể bị unregister sau lúc kiểm tra, và operation có thể thất bại vì trạng thái, bảo mật hoặc logic.

Nếu automation phụ thuộc contract nhiều phiên bản, nên version management API hoặc kiểm soát rollout client và server, không chỉ hy vọng tên cũ vẫn còn.

## 16. Metrics, logs và audit cho job tự động

Một job điều khiển qua JMX nên tự công bố telemetry của chính nó.

| Chỉ số | Ý nghĩa |
| --- | --- |
| `poll_count` | Tổng lần kiểm tra |
| `condition_true_count` | Số lần điều kiện kích hoạt |
| `invoke_attempt_count` | Số lần gửi operation |
| `invoke_success_count` | Số lần xác minh thành công |
| `invoke_error_count` | Số lỗi khi gọi hoặc xác minh |
| `unknown_outcome_count` | Không biết kết quả sau timeout/disconnect |
| `last_poll_timestamp` | Lần quan sát gần nhất |
| `last_invoke_timestamp` | Lần yêu cầu operation gần nhất |
| `cooldown_skip_count` | Số lần bỏ qua vì cooldown |

Log nên có các trường:

```text
scheduler=maintenance-poller
target=com.example.ops:type=MaintenanceControl,name=Primary
connection=worker-primary-jmx
condition=pendingJobs>500 for 3 polls
operation=requestMaintenance
decision=INVOKE
outcome=ACCEPTED
correlationId=...
```

Không ghi credentials, token hoặc dữ liệu nhạy cảm. Nếu job chạy nhiều replica, telemetry cần có scheduler instance và JMX target identity để biết instance nào đưa ra quyết định.

Audit cần phân biệt **yêu cầu đã gửi**, **operation được chấp nhận**, **kết quả đã hoàn thành**, và **kết quả chưa xác định**. Đó là bốn trạng thái khác nhau.

## 17. Tránh alert loop và automation loop

Một rủi ro phổ biến:

1. Một metric vượt ngưỡng.
2. Job gọi operation.
3. Operation gây thay đổi tạm thời khiến metric tiếp tục vượt ngưỡng.
4. Job gọi lại nhiều lần.
5. Tải hệ thống tăng, sự cố nghiêm trọng hơn.

Ví dụ xóa cache để giảm memory có thể làm tăng cache miss và tải database; nếu job thấy memory vẫn cao sau 30 giây rồi lại xóa, nó có thể tạo vòng lặp bất lợi.

Cách phòng ngừa:

- Số lần invoke tối đa theo cửa sổ thời gian.
- Cooldown đủ dài để hệ thống ổn định.
- Kiểm tra trend chứ không chỉ snapshot.
- Xác định tác dụng phụ dự kiến của operation.
- Có ngưỡng khôi phục và trạng thái `RECOVERING`.
- Dừng tự động hóa khi liên tục không đạt kết quả.
- Escalate cho operator thay vì retry mãi.
- Chạy dry-run mode để xem quyết định trước khi bật thực thi thật.

Với operation nguy hiểm, cảnh báo và yêu cầu phê duyệt có thể phù hợp hơn full automation.

## 18. Rule engine nhỏ cho quyết định điều khiển

Tách phần policy thành lớp thuần Java giúp test mà không cần MBeanServer:

```java
public final class MaintenancePolicy {

    private final int threshold;
    private final int requiredBreaches;
    private int consecutiveBreaches;

    public MaintenancePolicy(int threshold, int requiredBreaches) {
        this.threshold = threshold;
        this.requiredBreaches = requiredBreaches;
    }

    public boolean shouldRequest(
            int pendingJobs,
            boolean maintenanceRunning,
            boolean cooldownFinished) {

        if (pendingJobs > threshold) {
            consecutiveBreaches++;
        } else {
            consecutiveBreaches = 0;
        }

        return consecutiveBreaches >= requiredBreaches
            && !maintenanceRunning
            && cooldownFinished;
    }

    public void onRequestAccepted() {
        consecutiveBreaches = 0;
    }
}
```

Mẫu này giả định một caller serialized. Nếu policy được dùng đồng thời từ nhiều thread, trạng thái `consecutiveBreaches` cần đồng bộ hoặc chuyển sang xử lý event tuần tự.

Có thể test bằng JUnit mà không cần JMX:

```java
@Test
void requestsOnlyAfterThreeBreaches() {
    MaintenancePolicy policy = new MaintenancePolicy(500, 3);

    assertFalse(policy.shouldRequest(600, false, true));
    assertFalse(policy.shouldRequest(700, false, true));
    assertTrue(policy.shouldRequest(800, false, true));

    policy.onRequestAccepted();
    assertFalse(policy.shouldRequest(100, false, true));
}
```

Đây là cách phân tách tốt: **policy test** xác minh quyết định; **JMX integration test** xác minh attribute/operation; **end-to-end test** xác minh kết quả khi thực thi.

## 19. Tình huống lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không thấy MBean | Sai ObjectName, sai MBeanServer hoặc exporter chưa chạy | `isRegistered`, `getMBeanInfo`, đúng connection |
| `AttributeNotFoundException` | Attribute name/type thay đổi hoặc không được export | Đọc `MBeanInfo.getAttributes()` |
| `ReflectionException` | Tên/signature operation sai | Đọc `MBeanInfo.getOperations()` |
| `MBeanException` | Method quản trị gây lỗi được bọc bởi JMX | Kiểm tra root cause và server state |
| `IOException` remote | Lỗi connector/transport | Reconnect có backoff, không retry operation mù |
| Poller chạy nhiều lần | Nhiều replica/scheduler hoặc execution overlap | Leader election/lease và server guard |
| Operation lặp vô hạn | Condition vẫn true, thiếu cooldown/budget | Hysteresis, giới hạn invoke, kill switch |
| Operation báo ACCEPTED nhưng không có tác dụng | Công việc bất đồng bộ chưa hoàn tất hoặc fail | Theo dõi request ID/trạng thái cuối |
| JMX target đổi khi rollout | ObjectName/connection identity không ổn định | Version contract và discovery có kiểm soát |
| Automation gây quá tải | Operation quá nặng hoặc bị kích hoạt sai ngưỡng | Giảm scope, dừng job và review policy |

Lỗi phải được phân loại trước khi retry. Không nên catch `Exception` rồi cứ chờ vài giây và gọi lại một operation thay đổi trạng thái.

## 20. Bài tập thực hành

Xây dựng một Spring application nhỏ có `MaintenanceControl` và một job polling:

1. Tạo `MaintenanceService` chứa `PendingJobs`, `MaintenanceRunning`, `LastOutcome`.
2. Export qua `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.
3. Bật `@EnableMBeanExport` và `@EnableScheduling` hoặc cấu hình tương đương.
4. Dùng isolated `MBeanServer` trong test để không xung đột với platform server.
5. Tạo poller đọc `PendingJobs` và `MaintenanceRunning`.
6. Thực thi policy ba lần vi phạm và cooldown mười phút.
7. Khi đủ điều kiện, gọi `requestMaintenance` bằng `invoke`.
8. Kiểm tra kết quả trả về và đọc `LastOutcome`.
9. Tạo bài test khi operation đã chạy, đảm bảo không gọi lại.
10. Tạo bài test sau `IOException` giả lập, xác nhận không retry mù.
11. Giả lập hai poller cùng đọc điều kiện và xác minh guard phía service ngăn chạy trùng.
12. Ghi lại metrics: số poll, số condition true, số invoke và outcome.

Chỉ dùng fixture/lab để gọi operation. Nếu operation thật có thể xóa cache, tạm dừng worker hoặc thay cấu hình production, không được dùng môi trường production cho bài thử không có phê duyệt.

## 21. Câu hỏi tự kiểm tra

**1. JMX có tự chạy operation theo lịch không?** Không, cần scheduler hoặc automation bên ngoài.

**2. Vì sao poller cần đọc attribute trước khi invoke?** Để quyết định dựa trên trạng thái hiện tại thay vì gọi operation vô điều kiện.

**3. Tại sao điều kiện phía client chưa đủ chống chạy trùng?** Vì trạng thái có thể thay đổi giữa lúc đọc và lúc invoke, hoặc nhiều poller cùng đọc.

**4. `MBeanServerConnection.invoke` cần gì?** ObjectName, tên operation, mảng tham số và signature tương ứng.

**5. Có nên retry ngay sau remote timeout không?** Không nếu không biết operation đã thực thi; cần xác minh trạng thái hoặc idempotency.

**6. Vì sao cần cooldown?** Để tránh operation bị gọi liên tục khi metric chưa kịp ổn định.

**7. `@Scheduled` có tự cung cấp distributed lock không?** Không.

**8. Một ObjectName giống nhau trên hai JVM có chỉ cùng resource không?** Không, cần thêm identity của connection/JVM.

**9. Vì sao MBean nên công bố trạng thái operation?** Giúp automation xác minh `ACCEPTED`, `RUNNING`, `SUCCESS` và `FAILED`.

**10. Khi nào nên ưu tiên alert thay vì tự động điều khiển?** Khi tác động lớn, khó rollback hoặc cần quyết định từ operator.

## 22. Ghi nhớ

- **Job định kỳ là thành phần scheduling**, còn JMX cung cấp đường đọc attribute và gọi operation.
- Một flow an toàn là **quan sát → đánh giá điều kiện → guard → invoke → xác minh → audit**.
- **MBeanInfo** mô tả contract; **getAttribute** cung cấp state hiện tại; **invoke** thực thi operation.
- Dùng **consecutive breaches, hysteresis, cooldown và invoke budget** để tránh lệnh lặp.
- **Server-side guard** phải xử lý đồng thời; pre-check từ poller không đảm bảo atomicity.
- **Timeout không chứng minh operation chưa chạy**; cần idempotency/request ID và trạng thái cuối.
- **@Scheduled không có distributed coordination** giữa các replica.
- **JMX Remote cần được bảo vệ** và poller chỉ nên được cấp quyền tối thiểu.
- Telemetry cần theo dõi cả việc **ra quyết định** và **thực thi thực tế**.
- Có **kill switch** và runbook để tạm dừng automation khi gây side effect ngoài dự kiến.

Một job JMX tốt không phải job gọi operation càng thường xuyên càng tốt. Nó là một **bộ điều khiển vận hành có điều kiện**, biết lúc nào nên hành động, khi nào nên bỏ qua, cách xác minh kết quả và cách tự giới hạn rủi ro cho hệ thống Spring Framework.