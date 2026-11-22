# Spring Framework JMX — Đánh giá khả năng kiểm thử, quan sát và tự động hóa

## 1. Mục tiêu

Trong một ứng dụng Spring Framework, JMX là một management API dành cho vận hành: đọc trạng thái qua attributes, gọi operations để quản trị, nhận notifications và truy vấn MBeans bằng ObjectName. Chất lượng thiết kế không chỉ nằm ở việc MBean đăng ký thành công trong MBeanServer, mà còn ở **khả năng kiểm thử được, quan sát được và tự động hóa được một cách an toàn**.

Bài này cung cấp khung đánh giá ba nhóm năng lực:

1. **Testability:** kiểm chứng hành vi MBean một cách độc lập, lặp lại được và phát hiện thay đổi không tương thích.
2. **Observability:** biết hệ thống đang ở trạng thái gì, operation nào đã chạy, lỗi xảy ra ở tầng nào và có thể chẩn đoán mà không cần suy đoán.
3. **Automation readiness:** script/agent có thể tìm MBean, xác định contract, thực hiện thao tác an toàn, xử lý timeout và retry mà không gây side effects ngoài ý muốn.

Ví dụ phạm vi đánh giá:

```text
Application service
   |
   v
Management facade (@ManagedResource)
   | attributes / operations / notifications
   v
MBeanExporter -> MBeanServer
   |
   +-- JUnit integration tests
   +-- JConsole / monitoring dashboards
   +-- Automated operators / scripts
         |
         +-- discover ObjectName
         +-- read MBeanInfo
         +-- validate precondition
         +-- invoke or setAttribute
         +-- observe result and audit
```

Đánh giá tốt phải nhìn đồng thời API, runtime, bảo mật và quy trình vận hành; không chấm đạt chỉ vì một công cụ hiển thị MBean.

## 2. Ba tiêu chí đánh giá có liên quan nhưng không thay thế nhau

| Tiêu chí | Câu hỏi cốt lõi | Dấu hiệu tốt |
|---|---|---|
| Kiểm thử | Có thể chứng minh MBean đúng contract và đúng hành vi không? | Test fixture tách biệt, assertions cho metadata/state/lifecycle |
| Quan sát | Khi có lỗi, có phân biệt được nguyên nhân và trạng thái thật không? | Readable attributes, audit, metrics, notification/health |
| Tự động hóa | Script có thể điều khiển an toàn và dự đoán được không? | ObjectName ổn định, operation rõ, idempotency, status query |

Ví dụ một operation `startReindex()` có thể chạy khi người vận hành bấm JConsole, nhưng nếu gọi lại khi timeout làm tạo hai jobs thì **automation readiness chưa đạt**. Nếu operation đó có request ID và status query nhưng không có integration test cho duplicate calls, **testability chưa được chứng minh**. Nếu có test và idempotency nhưng không thể quan sát tiến độ hoặc lỗi, **observability còn thiếu**.

## 3. Xác định bề mặt management API

Trước khi đánh giá, cần biết rõ JMX đang công bố những gì. Với Spring annotation-based JMX:

```java
@ManagedResource(
    objectName = "com.example.app:type=QueueControl,name=orders"
)
public class QueueControl {
    @ManagedAttribute
    public long getPendingJobs() { return 0L; }

    @ManagedAttribute
    public boolean isPaused() { return false; }

    @ManagedOperation
    public void pauseIntake() { /* ... */ }
}
```

Phải phân biệt:

- `@ManagedResource` tạo metadata cấp resource.
- `@ManagedAttribute` công bố property phục vụ đọc/ghi theo getter/setter.
- `@ManagedOperation` công bố action.
- `MBeanExporter` và `MBeanInfoAssembler`/annotation infrastructure chịu trách nhiệm đăng ký và ánh xạ bề mặt JMX.
- `ObjectName` định danh MBean trong một MBeanServer.

Đừng đánh giá chỉ dựa trên annotation source: cần đối chiếu `MBeanInfo` thực tế vì exporter, assembler, AOP proxy và cấu hình Boot có thể làm thay đổi kết quả.

## 4. Kiểm thử contract JMX bằng MBeanInfo

Contract test cần xác minh:

1. ObjectName dự kiến được register.
2. Attribute tên, type, readable/writable đúng.
3. Operation name và signature đúng, không có member nhạy cảm lộ ngoài dự kiến.
4. Notification types được khai báo nếu có listener contract.
5. Đúng MBeanServer được exporter dùng.

Ví dụ:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public void verifyQueueContract(MBeanServer server) throws Exception {
    ObjectName name = new ObjectName(
        "com.example.app:type=QueueControl,name=orders"
    );
    if (!server.isRegistered(name)) {
        throw new AssertionError("Queue MBean missing");
    }

    MBeanInfo info = server.getMBeanInfo(name);
    boolean pendingReadable = java.util.Arrays.stream(
        info.getAttributes()
    ).anyMatch(a -> a.getName().equals("PendingJobs")
        && a.isReadable() && !a.isWritable());

    boolean pauseOperation = java.util.Arrays.stream(
        info.getOperations()
    ).anyMatch(op -> op.getName().equals("pauseIntake")
        && op.getSignature().length == 0);

    if (!pendingReadable || !pauseOperation) {
        throw new AssertionError("JMX API contract mismatch");
    }
}
```

Đây là khung kiểm thử trong cùng JVM và cần một Spring test context/MBeanServer fixture đã đăng ký MBean. Nếu exporter dùng server không phải platform server, inject chính server đó vào test. Kết quả `isRegistered` trên platform server khác không chứng minh việc export thất bại.

## 5. Test behavior, không chỉ metadata

MBean có thể đúng tên mà operation không đổi trạng thái như mong đợi. Vì vậy, cần test hành vi:

- Read-only attribute trả giá trị tương ứng service state.
- Setter hợp lệ cập nhật effective state.
- Setter không hợp lệ không làm thay đổi state.
- Operation gọi đúng business collaborator một lần.
- Operation có tác dụng phụ được kiểm soát bằng fake/mock service trong test.
- Khi Spring AOP tham gia, đường JMX invocation không bypass transaction/security advice ngoài ý muốn.

Ví dụ minh họa:

```java
long before = (Long) server.getAttribute(name, "PendingJobs");

server.invoke(name, "pauseIntake", new Object[0], new String[0]);

boolean paused = (Boolean) server.getAttribute(name, "Paused");
assertTrue(paused);
```

Khung này giả định operation và `Paused` attribute thực sự được implement có trạng thái tương ứng. Test cần dùng fixture, tránh gọi operation ảnh hưởng production. Không chỉ assert `invoke()` không ném exception; hãy đo hậu trạng thái hoặc spy collaborator.

## 6. Testability và dependency injection

Một management facade dễ test nên phụ thuộc vào interface nghiệp vụ, không tự tạo global resources:

```java
public interface QueueAdministration {
    long pendingJobs();
    boolean paused();
    void setPaused(boolean desired);
}

```java
@ManagedResource(
    objectName = "com.example.app:type=QueueControl,name=orders"
)
public class QueueJmxFacade {
    private final QueueAdministration service;

    public QueueJmxFacade(QueueAdministration service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getPendingJobs() {
        return service.pendingJobs();
    }

    @ManagedAttribute
    public boolean isPaused() {
        return service.paused();
    }

    @ManagedOperation
    public void pauseIntake() {
        service.setPaused(true);
    }
}
```

Trong unit test, inject fake `QueueAdministration` để kiểm tra logic facade không cần JMX remote connector. Trong integration test, dùng `MBeanServer` để xác minh annotation/assembler và đường gọi JMX. Đây là hai mức test bổ trợ cho nhau.

Không đưa toàn bộ Spring application startup, database và external services vào mọi test nhỏ nếu có thể tách facade bằng DI. Tuy nhiên, một số lỗi như naming collision, wrong server, metadata bị proxy che chỉ xuất hiện ở integration test; không nên chỉ dựa vào unit test.

## 7. Các tầng kiểm thử khuyến nghị

| Tầng | Mục tiêu |
|---|---|
| Unit test | Validation, chuyển đổi tham số, mapping facade, idempotency logic |
| Spring context test | Exporter được tạo, bean được scan, đúng ObjectName |
| MBeanServer integration test | Attribute/operation metadata và behavior thực tế |
| Remote connector test | JSR-160 URL, auth, transport, timeout, credential và listener lifecycle |
| Migration/regression test | ObjectName, signature, notifications và quyền không đổi ngoài ý muốn |
| Failure-injection test | Mất kết nối, duplicate invoke, server restart, concurrent updates |

Một chương trình quản trị chỉ cần local JMX có thể không yêu cầu bộ remote connector test đầy đủ. Nhưng nếu production dùng remote JMX, thiếu kiểm thử transport và authorization là khoảng trống lớn.

## 8. Dễ quan sát: những tín hiệu management API cần có

Attributes phục vụ giám sát nên:

- Có tên, type, đơn vị và ý nghĩa dễ hiểu.
- Phân biệt desired value và effective value nếu việc áp dụng cấu hình bất đồng bộ.
- Trả trạng thái hiện tại với chi phí hợp lý, tránh block lâu.
- Không làm thay đổi dữ liệu khi chỉ đọc.
- Không lộ secrets, tokens hoặc thông tin cá nhân.
- Có cardinality phù hợp; không export mỗi session/request thành một MBean.

Ví dụ:

```text
PendingJobs      type=long    readable=true
ActiveWorkers    type=int     readable=true
DesiredWorkers   type=int     readable=true
EffectiveWorkers type=int     readable=true
Paused           type=boolean readable=true
LastErrorCode    type=String  readable=true
```

Điều quan trọng là `LastErrorCode` không nhất thiết nên chứa toàn bộ exception stack trace. Error code ổn định kết hợp log/tracing correlation sẽ phù hợp hơn cho monitoring tự động và ít rủi ro lộ dữ liệu.

## 9. Quan sát operation dài và không đồng bộ

Với operation như `startReindex()` hoặc `reloadConfiguration()`, việc client nhận response từ `invoke()` không tự chứng minh tác vụ đã hoàn tất. Thiết kế nên gồm:

```text
startReindex(requestId) -> jobId
getRequestStatus(requestId) -> ACCEPTED/RUNNING/SUCCEEDED/FAILED
getJobProgress(jobId) -> progress value
getLastFailureCode(jobId) -> stable error category
```

Phải tách:

- Operation được server chấp nhận.
- Tác vụ thực sự bắt đầu.
- Tác vụ kết thúc thành công/thất bại.
- Client có nhận được response hay không.

Khi connection timeout sau khi gửi invoke, client không được tự kết luận tác vụ chưa chạy. `requestId` và status query giúp phân biệt một retry hợp lệ với việc vô tình tạo hai jobs.

## 10. Notifications: hữu ích nhưng không phải nguồn sự thật duy nhất

Spring hỗ trợ `NotificationPublisherAware`, `NotificationPublisher` và các notification metadata để một bean có thể phát JMX notification. Điều này hữu ích khi trạng thái thay đổi, nhưng remote listener có thể bị ngắt kết nối và bỏ lỡ events.

Một thiết kế quan sát tốt:

- Phát notification khi event có ý nghĩa vận hành.
- Cung cấp attribute/state query để client reconcile sau reconnect.
- Công bố notification type trong `MBeanInfo`.
- Không chứa dữ liệu nhạy cảm trong old/new values hoặc message.
- Quản lý listener registration/unregistration và reconnect.

Không xây quy trình nghiệp vụ cần guaranteed delivery chỉ dựa vào JMX Notifications. Nếu cần event replay, deduplication, exactly-once-like processing, cân nhắc durable event infrastructure phù hợp.

## 11. Metrics, logs và audit

Các tín hiệu cần có ở client/server:

| Nguồn | Ví dụ quan sát |
|---|---|
| Connector client | connect attempts, failures, connect latency, current connection state |
| Connector server | authentication failures, authorization denials, session lifecycle |
| MBean operation | started/succeeded/failed, duration, operation category |
| Business service | queue depth, task counts, effective state, last failure category |
| Automation job | request ID, execution status, retries, duplicate detection |

Tên metrics minh họa:

```text
jmx_connection_up{target}
jmx_connect_failures_total{category,target}
jmx_operation_duration_seconds{operation_class}
jmx_operation_failures_total{reason}
jmx_management_request_duplicates_total{operation}
```

Đây không phải metrics Spring JMX tự sinh. Nếu dùng Micrometer hoặc hạ tầng metrics khác, hãy thiết kế nhãn và cardinality có kiểm soát. Không dùng raw ObjectName chứa ID ngẫu nhiên hoặc username/IP tự do làm metric label.

Audit nên ghi actor đã xác thực, action, target, thời điểm, request ID, outcome và correlation ID nếu chính sách cho phép. Không log password/token, full JMX credentials map hoặc dữ liệu bí mật. JMX connector authorization và Spring Security method authorization là hai boundary có thể cần kiểm thử/quan sát riêng.

## 12. Thiết kế operation phù hợp automation

Automation thường gọi operation theo lịch hoặc khi metric vượt ngưỡng. Một management API dễ tự động hóa nên:

1. Có ObjectName ổn định qua restart.
2. Không đòi người vận hành chọn overload khó phân biệt.
3. Sử dụng tham số và kiểu đơn giản, rõ ràng.
4. Hạn chế operations dạng toggle hoặc increment không idempotent.
5. Ưu tiên desired-state: `setPaused(true)` thay vì `togglePaused()`.
6. Với action dài, dùng request ID và cung cấp status query.
7. Có validation và error categories rõ ràng.
8. Bảo đảm cùng request ID không tạo hai jobs khi retry.
9. Có concurrency control và ownership.
10. Tránh long-running call giữ network connection đến timeout.

Ví dụ không phù hợp:

```java
@ManagedOperation
public void toggleMaintenance() {
    maintenanceEnabled = !maintenanceEnabled;
}
```

Ví dụ tốt hơn:

```java
@ManagedOperation
public void setMaintenanceMode(boolean enabled) {
    maintenanceEnabled = enabled;
}
```

Gọi `setMaintenanceMode(true)` hai lần có thể giữ trạng thái cuối như một lần. Tuy nhiên idempotency của toàn operation còn phụ thuộc việc nó có tạo side effects khác mỗi lần gọi không; cần test behavior thật.

## 13. Retry-safe operation và kết quả không rõ

Một remote `MBeanServerConnection.invoke()` có thể timeout sau khi request đã được server thực thi. Vì thế:

```text
Client -> invoke(startReindex, requestId=A)
Server -> creates job J1
Network -> response lost
Client -> outcome unknown
```

Client nên truy vấn `getRequestStatus(A)` hoặc retry cùng request ID nếu contract đảm bảo duplicate-safe. Không dùng request ID mới cho mỗi retry, vì sẽ vô hiệu hóa deduplication.

Test automation nên bao gồm:

- Hai requests cùng ID, cùng parameters: một execution.
- Cùng ID nhưng parameters khác: trả conflict.
- Hai client cùng gửi ID đồng thời: không tạo hai jobs.
- Process restart giữa lần đầu và retry.
- Timeout trước/sau khi server nhận request.
- Operation bị từ chối quyền: không tạo job hoặc thay đổi state.

Nếu cần bảo đảm chống trùng qua nhiều JVM replicas hoặc restart, map in-memory không đủ; cần durable/shared state và transaction/recovery logic phù hợp.

## 14. Bảo mật cho tự động hóa

Read-only monitoring và privileged management nên được tách quyền. Một script giám sát CPU không nên có quyền `clearQueue`, `shutdownWorker` hoặc thay đổi limits.

Quy tắc:

- Bảo vệ JMX remote connector bằng authentication, authorization, TLS và network isolation.
- Giới hạn quyền của service account theo operation class.
- Không mặc định JMX principal tự được chuyển thành Spring Security Authentication.
- Nếu dựa vào `@PreAuthorize`, kiểm thử lời gọi JMX đi qua proxy và identity phù hợp.
- Các thao tác rủi ro có audit và rate/concurrency limits.
- Không cho phép client truyền `claimedRole=admin` như một cơ chế cấp quyền.
- Tránh automation loop gọi lại operation khi outcome chưa rõ.

Đối với operations nguy hiểm, có thể cần workflow phê duyệt riêng ngoài JMX; không nhất thiết phải expose tất cả actions qua remote management API.

## 15. Bảng đánh giá gợi ý

Đây là rubric kỹ thuật có thể điều chỉnh theo mức độ quan trọng của hệ thống:

| Tiêu chí | Chưa đạt | Đạt tối thiểu | Tốt |
|---|---|---|---|
| Contract | Tên/method mơ hồ, không test | ObjectName và MBeanInfo có test | Regression snapshot và versioning |
| State visibility | Không biết kết quả operation | Có status attributes | Có job/request status và error codes |
| Behavioral tests | Chỉ test startup | Có test get/set/invoke | Có concurrency/failure tests |
| Remote connectivity | Không quan sát failure | Có probe và connect errors | Có classifier, latency và reconnect tests |
| Notifications | Chỉ phát events | Có listener lifecycle | Reconcile state sau mất events |
| Authorization | Tài khoản chung quyền rộng | Có least privilege | Test deny + audit + tách boundary |
| Automation | Retry mù | Có idempotent setters | Request ID, dedup và durable state |
| Operability | Phải sửa code để biết lỗi | Có logs và basic metrics | Có dashboard, alert và runbook |

Không nên biến bảng thành điểm số giả chính xác; quan trọng hơn là ghi lại **bằng chứng cụ thể**: test cases, MBeanInfo snapshot, log/metrics mẫu và cách phục hồi khi failure. Một hệ thống có operation xóa dữ liệu cần mức kiểm soát cao hơn một MBean chỉ đọc memory usage.

## 16. Quy trình đánh giá một MBean đang chạy

### Bước 1 — Inventory

Dùng `queryNames` để lấy danh sách ObjectNames theo domain ứng dụng. Ghi lại số lượng MBeans, naming convention và các endpoints đang công bố.

```java
ObjectName pattern = new ObjectName("com.example.app:*");
for (ObjectName name : connection.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
}
```

### Bước 2 — Kiểm tra metadata

Đọc `getMBeanInfo(name)` để xem attributes readable/writable, operations signatures, notification types. Đánh dấu những operations nhạy cảm hoặc không có mô tả rõ.

### Bước 3 — Kiểm thử read-only

Thử `getAttribute` với các metrics/status attributes và kiểm tra latency, error handling. Không gọi operations nguy hiểm chỉ để xem chúng có hoạt động.

### Bước 4 — Kiểm thử operation trong fixture

Trong môi trường test, xác minh input validation, hậu trạng thái, authorization, duplicate request handling và concurrency. Phân biệt kết quả của JMX call với kết quả background job.

### Bước 5 — Kiểm thử sự cố

Thử JVM restart, network disconnect, remote timeout, wrong ObjectName và invalid credentials trong môi trường được phép. Kiểm tra cảnh báo, reconnect và absence of unsafe retries.

### Bước 6 — Automation dry-run

Cho script chạy trên test target với quyền thấp nhất cần thiết, xác minh có precondition checks, status query, audit và rollback/compensation plan nếu hoạt động được.

### Bước 7 — Ghi nhận bằng chứng

Tổng hợp contract snapshot, kết quả tests, quan sát latency, error categories, audit và danh sách khoảng trống. Đưa các rủi ro có tác động lớn vào kế hoạch cải thiện trước rollout.

## 17. Các lỗi thiết kế thường gặp

| Triệu chứng | Thiếu sót thiết kế | Cách cải thiện |
|---|---|---|
| JConsole có MBean nhưng test automation không tìm được | ObjectName thay đổi theo startup/random ID | Dùng logical identity ổn định |
| Operation hoạt động bằng tay nhưng script retry tạo hai jobs | Không có idempotency/dedup | Dùng request ID và status query |
| Không biết task đã hoàn tất chưa | Operation chỉ trả void và chạy async | Expose job status/result |
| Test pass nhưng production mất authentication | Không test connector security | Test remote auth/authorization |
| Một MBean có hàng trăm dynamic instances | Cardinality không kiểm soát | Tổng hợp resource hoặc giới hạn instance |
| Không thấy thay đổi state sau timeout | Thiếu observable state | Readback và correlation ID |
| Notifications mất sau reconnect | Xem event là durable | Reconcile current state |
| Setter làm monitoring treo | Getter/setter thực thi I/O dài | Tách thao tác nặng khỏi đường quản trị |
| Audit không ghi JMX calls | Chỉ audit HTTP/proxy path | Audit ở management boundary |
| Operation có `@PreAuthorize` nhưng vẫn chạy khi JMX gọi | AOP proxy bị bypass | Dùng facade và integration test từ JMX |

## 18. Bài thực hành

### Bài 1 — Đánh giá contract

Chọn một MBean `WorkerPool` và viết test đọc `MBeanInfo` để xác nhận `ActiveWorkers` là read-only, `MaxWorkers` có đúng read/write flags và `pauseIntake()` có signature mong đợi.

### Bài 2 — Thiết kế observable operation

Thay `void reindex()` bằng `startReindex(requestId) -> jobId` và `getRequestStatus(requestId)`. Giải thích cách client biết kết quả sau timeout.

### Bài 3 — Test tự động hóa

Gọi `startReindex` hai lần cùng request ID trong fixture. Dùng fake scheduler để xác nhận chỉ một job được tạo.

### Bài 4 — Test quyền

Tạo read-only JMX account thử nghiệm. Xác minh đọc attribute thành công nhưng `setMaxWorkers` hoặc `clearQueue` bị từ chối và state không đổi.

### Bài 5 — Notification loss

Tắt connector rồi khởi động lại. Nêu cách client đăng ký lại listener và đồng bộ current state để không dựa vào event lịch sử bị mất.

### Bài 6 — Đánh giá runtime

Liệt kê các MBeans trong một domain test, tính tỷ lệ attributes có mô tả/kiểu hợp lệ và xác định operations nào có side effects hoặc thiếu status/error code.

## 19. Checklist trước khi chấp nhận thiết kế

- ObjectName ổn định và không chứa dữ liệu nhạy cảm.
- Contract có test `MBeanInfo` cho attributes, operations, notifications.
- Behavior test có hậu trạng thái/side-effect assertions.
- Getters read-only đủ nhanh và không có tác dụng phụ.
- Operations dài có request/job status.
- Có idempotency hoặc duplicate-safe contract cho retries.
- Có phân loại lỗi transport, auth, registry và business.
- Có metrics, logs và audit với nhãn được kiểm soát.
- Có notification listener lifecycle và cách reconcile state.
- Có test authorization denial và AOP proxy khi cần.
- Có integration test remote connector nếu production dùng JSR-160.
- Có runbook cho timeout, restart và mất kết nối.
- Automation có least privilege, preconditions và retry policy an toàn.

## 20. Tổng kết

Đánh giá Spring JMX management API phải xem nó như một giao diện vận hành lâu dài, không phải tập hợp getter và method được export cho đủ. **Testability** cung cấp bằng chứng về contract và hành vi; **observability** cho biết trạng thái, lỗi và tiến độ; **automation readiness** bảo đảm scripts có thể thao tác đúng và an toàn khi gặp retry, timeout và concurrency. Một thiết kế tốt kết hợp ObjectName ổn định, MBeanInfo rõ ràng, state/status attributes, idempotent operations, phân quyền, audit và integration tests. Điều quan trọng không phải số lượng MBeans mà là khả năng sử dụng và khôi phục chúng một cách đáng tin cậy trong vận hành.