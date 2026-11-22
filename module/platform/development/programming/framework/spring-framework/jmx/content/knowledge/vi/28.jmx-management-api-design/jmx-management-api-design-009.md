# Quản lý quyền theo mức tác động của từng operation trong Spring Framework JMX

## 1. Vì sao phải phân quyền theo mức tác động?

Một management API thường được dùng bởi nhiều đối tượng: hệ thống monitoring, nhân viên trực vận hành, SRE, quản trị viên hoặc công cụ tự động. Không phải ai đọc được trạng thái JVM cũng nên được phép xóa cache, đổi cấu hình, dừng worker hay kích hoạt thao tác ảnh hưởng dữ liệu.

Trong Spring Framework, một bean có thể được đưa ra JMX bằng `MBeanExporter`, `@ManagedResource` và `@ManagedOperation`. Việc operation xuất hiện trong `MBeanInfo` chỉ có nghĩa là nó được công bố qua giao diện quản trị — **không có nghĩa Spring tự động kiểm tra quyền người gọi theo mức nguy hiểm của operation**.

Ví dụ:

```java
@ManagedResource(
    objectName = "com.example:type=Worker,name=Orders")
public class WorkerManagement {

    @ManagedAttribute
    public int getPendingJobs() {
        return pendingJobs;
    }

    @ManagedOperation
    public void pause() {
        worker.pause();
    }

    @ManagedOperation
    public void clearAllPendingJobs() {
        worker.clearPendingJobs();
    }
}
```

Một client chỉ cần theo dõi `PendingJobs`; người vận hành có thể được quyền `pause()`; còn `clearAllPendingJobs()` có tác động phá hủy và cần phê duyệt/giới hạn riêng.

**Mục tiêu của bài:** thiết kế chính sách theo mức tác động, áp dụng kiểm soát quyền đúng lớp, giảm khả năng sử dụng sai operation và kiểm thử được sự khác biệt giữa quyền quan sát và quyền thay đổi trạng thái.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân loại management operations theo mức tác động.
2. Phân biệt JMX metadata `ACTION`, `INFO`, `ACTION_INFO`, `UNKNOWN` với cơ chế authorization.
3. Thiết kế mô hình reader, operator, privileged operator và administrator.
4. Biết giới hạn của JMX remote access file với hai mức `readonly` và `readwrite`.
5. Hiểu vì sao `@ManagedOperation`, `@ManagedResource` và ObjectName không tự tạo ranh giới bảo mật.
6. Cân nhắc enforcement ở remote connector, MBeanServer, proxy/facade và business service.
7. Thiết kế operation nguy hiểm theo nguyên tắc least privilege, explicit intent, idempotency, audit và kiểm tra trạng thái.
8. Viết tests bảo đảm người chỉ có quyền đọc không thể thực thi operation thay đổi trạng thái.
9. Tách kiểm thử authorization khỏi kiểm thử business logic và JMX metadata.
10. Có checklist trước khi cho phép operator sử dụng API quản trị trong production.

## 3. Mô hình các lớp bảo vệ

```text
JMX client / operator
        |
        v
Network boundary
  firewall / VPN / tunnel / TLS
        |
        v
JMX connector
  authentication + access policy
        |
        v
MBeanServer / authorization layer
  object name + action + parameters
        |
        v
Spring exported MBean / management facade
  validation, explicit state checks
        |
        v
Business service
  domain authorization / invariants
        |
        v
State change + audit trail
```

Mỗi lớp trả lời một câu hỏi:

| Lớp | Câu hỏi |
|---|---|
| Network | Ai có thể kết nối tới cổng quản trị? |
| Authentication | Principal nào đang gọi? |
| Connector authorization | Principal có được phép thực hiện loại JMX request này không? |
| MBeanServer authorization | ObjectName, operation và action cụ thể có được phép không? |
| Management facade | Operation có được expose và được bảo vệ đúng use case không? |
| Business service | Thao tác có hợp lệ trong trạng thái và ngữ cảnh hiện tại không? |
| Audit | Có thể truy vết ai đã yêu cầu điều gì và kết quả ra sao không? |

Không nên chọn một lớp rồi bỏ các lớp còn lại. Ví dụ chỉ giới hạn IP không phân biệt được quyền của hai nhân viên trong cùng mạng; chỉ dùng annotation trên method không bảo vệ được connector thiếu authentication.

## 4. Phân loại operation theo mức tác động

Thay vì một nhóm “admin” chung, nên xác định **impact tier** cho từng thao tác.

| Mức | Ví dụ | Tác động | Chính sách khuyến nghị |
|---|---|---|---|
| L0 — Observe | `getPendingJobs()`, `getHealth()` | Đọc dữ liệu đã được giảm nhạy cảm | Monitoring reader |
| L1 — Diagnostics | `dumpStateSummary()`, `getFailedJobCount()` | Có thể tiết lộ topology/metadata | Diagnostics reader, audit truy cập khi cần |
| L2 — Reversible action | `pause()`, `resume()`, `setLogLevel()` | Thay đổi trạng thái có thể khôi phục | Operator, kiểm tra precondition |
| L3 — Disruptive action | `restartWorker()`, `reloadConnections()` | Gián đoạn dịch vụ | Privileged operator, xác nhận và audit |
| L4 — Destructive/security action | `deleteQueue()`, `purgeData()`, `rotateKeys()` | Có thể mất dữ liệu hoặc ảnh hưởng bảo mật | Không expose trực tiếp nếu tránh được; workflow phê duyệt riêng |

Phân loại thực tế tùy semantics:

- `clearCache()` có thể an toàn với cache có thể tái tạo, nhưng gây tải lớn hoặc mất session nếu cache được thiết kế sai.
- `setEnabled(false)` có vẻ đơn giản nhưng có thể làm ngừng xử lý nghiệp vụ.
- `refreshConfiguration()` có thể làm thay đổi endpoints, credentials hoặc business rules.
- `getConfiguration()` là read-only về mặt mutation nhưng vẫn có thể tiết lộ secrets.

**“Read-only” không đồng nghĩa “không nhạy cảm”.** Tính bảo mật dữ liệu và mức tác động vận hành cần được đánh giá song song.

## 5. JMX metadata impact không phải security policy

`MBeanOperationInfo` có các giá trị impact:

- `INFO`: operation mang tính lấy thông tin.
- `ACTION`: operation có tác động thay đổi trạng thái.
- `ACTION_INFO`: kết hợp hành động và thông tin.
- `UNKNOWN`: không xác định.

Bạn có thể inspect:

```java
MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "%s impact=%d%n",
        op.getName(),
        op.getImpact());
}
```

Thông tin này giúp công cụ quản trị mô tả operation nhưng **không tự giới hạn quyền**. Một client có quyền gọi `MBeanServerConnection.invoke` có thể cố gọi operation bất kể metadata ghi `ACTION` hay `INFO`. Việc được phép hay không do authorization thực tế của connector/server/business layer quyết định.

### 5.1. Không dựa vào tên method

Tên `refresh()`, `reconcile()` hoặc `sync()` không nói rõ tác động. Một operation `refresh` có thể cập nhật hàng triệu records. Chính sách nên dựa trên hành vi, dữ liệu liên quan và blast radius, không chỉ tiền tố getter/setter hay tác giả đặt tên.

### 5.2. Metadata nên hỗ trợ con người

Dù không phải security boundary, mô tả đầy đủ giúp người vận hành tránh nhầm:

```java
@ManagedOperation(
    description = "Pause new job intake; running jobs continue")
public void pauseIntake() { ... }
```

Trong tài liệu quản trị nên ghi rõ preconditions, side effects, thời gian hoàn tất, khả năng rollback và audit ID.

## 6. Authentication và authorization khác nhau

**Authentication:** chứng minh caller là ai, ví dụ principal `monitor-agent` hoặc `operator-alice`.

**Authorization:** principal đó được phép làm gì, chẳng hạn `monitor-agent` chỉ đọc số liệu, còn `ops-maintenance` được gọi `pauseIntake`.

**Audit:** ghi lại yêu cầu, kết quả và thông tin truy vết để điều tra sau này.

Một endpoint JMX có mật khẩu không tự động có phân quyền tốt. Nếu mọi tài khoản có cùng quyền `readwrite`, tài khoản monitoring có thể được trao nhiều quyền hơn mức cần thiết.

## 7. JMX access file: readonly và readwrite

JDK management agent truyền thống hỗ trợ cơ chế access file với các role như `readonly` và `readwrite`. Cấu hình minh họa:

```text
# jmxremote.access - illustrative only
monitorRole readonly
operatorRole readwrite
```

File password/access, cơ chế xác thực và đường dẫn được cấu hình theo JDK và triển khai. Không sao chép ví dụ này vào production mà bỏ qua TLS, quyền file, mạng và chính sách account.

Điểm giới hạn:

- `readonly` hỗ trợ phân quyền loại thao tác JMX ở mức coarse-grained.
- `readwrite` thường quá rộng cho một operator chỉ được phép `pause()` nhưng không được phép `purge()`.
- Không nên suy luận JMX access file tự thực hiện rule cho từng `ObjectName + operationName + params`.
- Một số JDK/management agent có thêm cơ chế `create`/`unregister` hạn chế theo cấu hình; cần xem tài liệu JDK phiên bản triển khai.
- Các connector tùy chỉnh có thể có semantics khác với built-in management agent.

Nếu cần phân quyền granular, cần authorization layer bổ sung hoặc thiết kế exposure theo endpoint/server dành riêng cho từng nhóm quyền.

### 7.1. Readonly không thay thế data minimization

Một principal readonly vẫn có thể đọc attributes nhạy cảm nếu server expose chúng. Vì vậy không đưa password, API tokens, raw connection strings hoặc dữ liệu cá nhân vào JMX attributes. Với thông tin diagnostics, ưu tiên safe summaries và quyền riêng.

## 8. Tách management operations theo vai trò

Một giải pháp cấu trúc là không gom mọi phương thức vào một management interface rộng.

Ví dụ thay vì:

```java
public interface EverythingManagementMBean {
    int getPendingJobs();
    void pause();
    void restart();
    void purgeAll();
}
```

có thể thiết kế:

```java
public interface WorkerStatusMBean {
    int getPendingJobs();
    String getState();
}
```

```java
public interface WorkerOperationsMBean {
    void pauseIntake();
    void resumeIntake();
}
```

Và chuyển thao tác phá hủy vào một workflow quản trị khác có phê duyệt, không expose dưới dạng JMX method thông thường.

Tách interface làm surface dễ review hơn, nhưng nếu cả hai MBeans cùng đăng ký vào một MBeanServer có connector `readwrite` dùng chung, người có quyền ghi rộng **vẫn có thể gọi các operations mà họ nhìn thấy**. Chỉ tách interface mà không có authorization policy không tạo ra ranh giới bảo mật.

## 9. Thiết kế management facade thay vì export trực tiếp service

Một business service có nhiều methods không nên được export toàn bộ:

```java
@Service
public class OrderService {
    public void createOrder(...) { ... }
    public void refund(...) { ... }
    public void purgeFailedOrders(...) { ... }
    public OrderStatus findStatus(...) { ... }
}
```

Thay vào đó, tạo một facade quản trị chỉ chứa thao tác đã được review:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Operations,name=Primary",
    description = "Restricted management API for order processing")
public class OrderManagementFacade {

    private final OrderCoordinator coordinator;

    public OrderManagementFacade(OrderCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return coordinator.pendingCount();
    }

    @ManagedOperation(
        description = "Pause intake without deleting queued orders")
    public void pauseIntake() {
        coordinator.pauseIntake();
    }
}
```

Hợp đồng này không đưa `purgeFailedOrders` lên JMX. Nếu operation có quyền thay đổi trạng thái, còn cần enforcement ở lớp connector/server hoặc business service thích hợp.

### 9.1. Hạn chế autodetection quá rộng

Nếu một custom `MBeanExporter` dùng assembler expose mọi public method hoặc một naming convention quá rộng, vô tình có thể tạo operations nguy hiểm. Production nên ưu tiên danh sách managed methods được chủ đích định nghĩa hoặc metadata có review.

## 10. Phân quyền theo operation: các chiến lược enforcement

Có nhiều lựa chọn kiến trúc, phụ thuộc yêu cầu và JMX implementation:

| Chiến lược | Mạnh ở đâu | Giới hạn |
|---|---|---|
| JMX connector authentication/role | Chặn người không được xác thực hoặc nhóm quyền thô | Có thể không granular theo operation |
| MBeanServer authorization wrapper | Kiểm tra tên MBean, operation, access type | Cần triển khai/test cẩn thận trên mọi entry point |
| Custom JMX connector/forwarder | Có thể enforce theo principal và request | Tăng complexity, lệ thuộc implementation |
| Management facade + business authorization | Giữ allowlist và invariants gần logic | Phải truyền caller identity một cách đáng tin |
| Management API riêng (HTTP/gRPC) có RBAC | Cơ chế identity, authorization, approval dễ tích hợp | Không còn là JMX operation trực tiếp |
| Không expose operation nguy hiểm | Giảm tấn công mạnh nhất | Cần workflow thay thế khi cần thao tác |

Nếu hệ thống cần xác định **principal của từng remote JMX caller**, không nên tự đọc một thread-local tùy ý trong bean rồi mặc định đó là user đã xác thực. Cơ chế truyền identity phụ thuộc connector và security context. Hãy ưu tiên API/security framework có hợp đồng identity rõ ràng hoặc lớp JMX authorization được kiểm thử trên implementation thực tế.

### 10.1. MBeanServerForwarder

JMX Remote API có `MBeanServerForwarder` để chuyển tiếp `MBeanServer` operations. Một custom forwarder có thể được sử dụng trong kiến trúc authorization, nhưng triển khai đầy đủ phải xử lý **mọi đường truy cập có tác động**, không chỉ `invoke`.

Ví dụ operations cần review:

- `invoke`: gọi method quản trị.
- `setAttribute`/`setAttributes`: thay đổi state qua attributes.
- `createMBean` hoặc `registerMBean` khi được expose.
- `unregisterMBean`: xóa registration.
- `getAttribute`/`getAttributes`: đọc data nhạy cảm.
- Notification subscriptions và metadata reads khi information disclosure quan trọng.

Nếu chặn `invoke("purge")` nhưng quên chặn `setAttribute("PurgeRequested", true)`, người dùng vẫn có đường thay đổi trạng thái. Authorization policy phải bao phủ **capabilities** chứ không chỉ method names.

## 11. Ví dụ policy engine cho management facade

Một cách diễn đạt policy độc lập JMX là phân quyền theo capability:

```java
public enum ManagementAction {
    VIEW_STATUS,
    VIEW_DIAGNOSTICS,
    PAUSE_INTAKE,
    RESTART_WORKER,
    PURGE_DATA
}
```

```java
public interface ManagementAuthorizer {
    void require(String principal, ManagementAction action);
}
```

Implementation minh họa:

```java
import java.util.Map;
import java.util.Set;

public final class RoleBasedAuthorizer
        implements ManagementAuthorizer {

    private final Map<String, Set<ManagementAction>> grants;

    public RoleBasedAuthorizer(
            Map<String, Set<ManagementAction>> grants) {
        this.grants = Map.copyOf(grants);
    }

    @Override
    public void require(
            String principal,
            ManagementAction action) {

        if (!grants.getOrDefault(principal, Set.of())
                .contains(action)) {
            throw new SecurityException(
                "Not authorized for management action");
        }
    }
}
```

Đây là ví dụ về **policy function**. Trong hệ thống thật, `principal` phải đến từ kênh identity đáng tin, không phải tham số do JMX caller tự đặt tùy ý.

### 11.1. Anti-pattern: client tự khai principal

Không an toàn:

```java
@ManagedOperation
public void purge(String callerName) {
    authorizer.require(callerName, PURGE_DATA);
    purgeService.run();
}
```

Client có thể truyền `"admin"` trong `callerName`. Không được coi string do người gọi cung cấp là bằng chứng authentication.

Tốt hơn là áp dụng policy tại connector/server boundary nơi principal đã được xác thực, hoặc sử dụng management API riêng có security context đáng tin.

### 11.2. Defense in depth trong business service

Ngay cả khi lớp JMX chỉ cho phép operator gọi `pauseIntake`, business service vẫn cần kiểm tra:

- Service hiện tại có đang cho phép pause không?
- Có batch quan trọng đang chạy không?
- Đơn vị người gọi có được thao tác trên resource này không?
- Có precondition an toàn như expected version không?
- Hệ thống cần audit và thông báo các thành phần khác không?

Phân quyền và tính hợp lệ nghiệp vụ là hai điều kiện khác nhau.

## 12. Operation có tác động lớn nên có precondition rõ

Thay vì một method mơ hồ:

```java
@ManagedOperation
public void restart() {
    restartInternal();
}
```

có thể đưa vào contract các điều kiện kiểm soát:

```java
@ManagedOperation
public String requestRestart(
        String requestId,
        String expectedState,
        String reason) {

    validateRequest(requestId, expectedState, reason);
    return maintenanceService.requestRestart(
        requestId, expectedState, reason);
}
```

Mã chỉ minh họa; `validateRequest` và `maintenanceService` cần được triển khai và bảo vệ.

Các yêu cầu thiết kế:

1. `requestId` cho phép đối chiếu và deduplicate.
2. `expectedState` chống thao tác khi trạng thái đã thay đổi.
3. `reason` hỗ trợ audit nhưng không thay danh tính người gọi.
4. Result ID/status giúp client theo dõi thay vì retry mù.
5. Authorization phải xảy ra trước side effect.
6. Không nhận “admin=true” từ client như bằng chứng quyền.
7. Nếu thay đổi nhiều resources, xác định blast radius rõ ràng.

Một validation tốt không thay thế authorization, nhưng giúp giảm sai sót vận hành.

## 13. Hai bước duyệt: preview và execute

Với operation nguy hiểm, có thể tách:

```text
previewPurge(scope) -> impact summary
          |
          v
Review/approval outside JMX
          |
          v
executeApprovedPurge(approvalToken, requestId)
```

Tuy nhiên `approvalToken` cũng là credential nhạy cảm. Nếu đặt nó vào JMX operation arguments, cần bảo vệ transport, logs, debug traces và kiểm tra expiry/scope/single use. Một hướng thực tế thường tốt hơn là thao tác phá hủy đi qua orchestration service có workflow approval chuyên dụng, thay vì expose `executeApprovedPurge` ở mọi JVM.

Mục tiêu là tránh một cú click trong JConsole gây thao tác không thể đảo ngược.

## 14. Audit: ai làm, làm gì, tác động đến đâu?

Một audit event tối thiểu nên ghi:

| Field | Ý nghĩa |
|---|---|
| `timestamp` | Thời điểm server tiếp nhận yêu cầu |
| `principal` | Identity được xác thực |
| `action` | Capability/operation đã yêu cầu |
| `objectName` | Resource quản trị |
| `requestId` | ID phục vụ đối chiếu và dedup |
| `scope` | Phạm vi ảnh hưởng được chuẩn hóa |
| `decision` | Allowed/denied |
| `outcome` | Succeeded/failed/unknown |
| `duration` | Thời gian xử lý |
| `correlationId` | Liên kết logs và workflow |

Không ghi raw passwords, tokens, private keys hoặc toàn bộ JMX parameters chưa được lọc. Một phần parameters có thể chứa dữ liệu nhạy cảm hoặc thông tin cá nhân.

### 14.1. Thất bại trước business method cũng cần audit

Nếu authorization layer từ chối `invoke`, business method không được gọi. Audit chỉ nằm bên trong method sẽ không thấy lượt denied. Nên ghi quyết định tại nơi policy được enforce và audit outcome ở layer thực thi nếu request được chấp nhận.

### 14.2. Outcome unknown với remote JMX

Nếu client mất kết nối sau khi server thực hiện operation, client có thể gặp `IOException` nhưng server đã thay đổi trạng thái. Audit phía server, request ID và query status giúp xác định kết quả. Không tự retry destructive operation chỉ vì client timeout.

## 15. Spring AOP và phương thức quản trị

Một đội phát triển có thể đặt authorization advice quanh method Spring bean. Nhưng việc JMX exporter gọi method thông qua proxy hay target phụ thuộc cấu hình exporter, assembler và AOP.

```text
JMX request
    |
    v
MBean adapter
    |
    +--> Spring AOP proxy?
    |        |
    |        +--> security advice
    |
    +--> target directly?
             |
             +--> advice có thể bị bỏ qua
```

Vì vậy:

- Không mặc định `@PreAuthorize` trên một method được export luôn được áp dụng trên mọi đường gọi JMX.
- Xác minh exported object là proxy phù hợp và việc gọi qua JMX thực sự đi qua security interceptor.
- Kiểm tra JDK dynamic proxy có expose đủ management interface không.
- Tránh self-invocation nếu logic cần AOP advice.
- Không unwrap proxy để “sửa” việc MBean không hoạt động rồi vô tình bỏ qua authorization.
- Test denial bằng **lời gọi `MBeanServerConnection.invoke` thật**, không chỉ gọi service trong unit test.

Nếu yêu cầu security nghiêm ngặt, đừng chỉ dựa vào một annotation AOP chưa được kiểm chứng end-to-end ở JMX boundary.

## 16. Read vs write không phải lúc nào cũng rõ

Một operation được đánh dấu `INFO` có thể tính toán rất nặng, đọc secret hoặc tạo áp lực lên database. Một getter cũng có thể thực hiện network request.

Ngược lại, một setter `setLogLevel` là mutation nhưng có thể được cho phép với operator theo policy.

Vì vậy nên đánh giá theo nhiều trục:

| Trục | Câu hỏi |
|---|---|
| Confidentiality | Có tiết lộ dữ liệu nhạy cảm không? |
| Integrity | Có thay đổi dữ liệu, cấu hình hay security state không? |
| Availability | Có thể dừng/chậm dịch vụ không? |
| Reversibility | Có thể rollback không? |
| Scope | Một worker, một node hay toàn cụm? |
| Cost | CPU, I/O, DB/network load bao nhiêu? |
| Auditability | Có xác định được actor và kết quả không? |

Một ma trận quyền tốt cần trả lời các trục này trước khi quyết định role nào có thể gọi operation.

## 17. Thiết kế ObjectName và resource-level authorization

Ví dụ các MBeans:

```text
com.example.orders:type=Worker,region=vn,name=Primary
com.example.orders:type=Worker,region=sg,name=Primary
```

Một operator VN có thể được phép `pauseIntake` trên resource `region=vn`, nhưng không có quyền trên `region=sg`. Authorization cần xét **ObjectName và operation**, không chỉ method name.

ObjectName là input dùng để định danh resource. Nó không tự cấp quyền. Một người gọi có thể tự xây dựng `ObjectName` khác nếu connector cho phép; server policy cần xác nhận phạm vi cho phép.

### 17.1. Không dùng wildcard quyền quá rộng

Một policy cho phép:

```text
com.example.orders:*
```

có thể vô tình bao gồm những MBeans mới trong tương lai, kể cả operations nguy hiểm. Ưu tiên allowlist theo domain/type/name/region và capability cụ thể. Sau mỗi lần thêm MBean hoặc method mới cần kiểm tra permission drift.

## 18. Kiểm thử phân quyền theo mức tác động

Các test phải kiểm tra **denied path và permitted path**.

Ma trận gợi ý:

| Principal | Status read | Diagnostics | Pause | Restart | Purge |
|---|---:|---:|---:|---:|---:|
| monitoring-reader | Allow | Deny | Deny | Deny | Deny |
| diagnostics-reader | Allow | Allow | Deny | Deny | Deny |
| operator | Allow | Allow | Allow | Deny | Deny |
| privileged-operator | Allow | Allow | Allow | Allow | Deny |
| emergency-admin | Allow | Allow | Allow | Allow | Conditional |

“Conditional” nghĩa là có thể còn cần approval, time-bound access và scope checks. Bảng chỉ minh họa; role thực tế phải do tổ chức quy định.

### 18.1. Test policy function

```java
import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class AuthorizerTest {

    @Test
    void monitoringCannotPause() {
        var grants = Map.of(
            "monitoring-reader",
            Set.of(ManagementAction.VIEW_STATUS));

        var auth = new RoleBasedAuthorizer(grants);

        assertThrows(SecurityException.class,
            () -> auth.require(
                "monitoring-reader",
                ManagementAction.PAUSE_INTAKE));

        assertDoesNotThrow(
            () -> auth.require(
                "monitoring-reader",
                ManagementAction.VIEW_STATUS));
    }
}
```

Test này chỉ xác nhận logic mapping role/capability; **chưa chứng minh JMX connector thực sự gắn đúng principal và gọi policy**.

### 18.2. Test JMX boundary

Trong integration test có security layer phù hợp:

1. Tạo principal monitoring-reader.
2. Kết nối đến connector đã được bảo vệ.
3. Assert đọc safe attribute được phép.
4. Gọi `invoke("pauseIntake")`, assert denied.
5. Assert state worker không thay đổi.
6. Dùng operator principal được cấp quyền.
7. Gọi cùng operation, assert allowed.
8. Kiểm tra audit log có cả denied/allowed decisions.
9. Đảm bảo một setter tương đương cũng bị kiểm soát.
10. Đóng connector/context và dọn MBean registrations.

Không tạo fake principal trong business method rồi coi đó là integration test xác thực. Cần dùng cơ chế authentication thật hoặc test fixture của connector tương ứng.

## 19. Kiểm thử capability trên MBeanServer

Khi chỉ cần kiểm tra metadata/contract, có thể dùng local server cô lập:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("test");

ObjectName name = new ObjectName(
    "com.example.orders:type=Worker,name=Primary");
```

Sau khi export test MBean qua Spring, kiểm tra:

```java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}
```

Điều này xác minh surface được expose, nhưng không chứng minh remote authorization. Local `MBeanServer` có thể được code trong cùng JVM gọi trực tiếp, không qua connector có xác thực. Test security phải đi qua đúng enforcement boundary.

## 20. Chống đường vòng authorization

Một policy chỉ chặn `invoke` có thể bị bỏ qua nếu resource cung cấp đường đổi trạng thái qua writable attribute.

Ví dụ:

```java
@ManagedAttribute
public void setPaused(boolean paused) {
    service.setPaused(paused);
}
```

Ngay cả khi `pauseIntake()` được bảo vệ, client có thể thử:

```java
connection.setAttribute(
    name, new Attribute("Paused", true));
```

Do đó audit/exposure review phải bao gồm:

- Readable attributes.
- Writable attributes.
- Operations.
- Create/unregister capabilities khi được expose.
- Notification subscriptions.
- Metadata discovery và quyền đọc những thông tin nhạy cảm.

Một cách thiết kế giảm rủi ro là không expose writable attributes cho hành động quan trọng; dùng operation được bảo vệ bởi authorization và precondition rõ. Nhưng không có một mô hình đủ cho mọi hệ thống; vẫn cần xem xét security policy thực.

## 21. Incident và break-glass access

Trong sự cố nghiêm trọng, có thể cần quyền cao tạm thời. Điều này không có nghĩa cấp admin vĩnh viễn cho mọi người vận hành.

Một break-glass workflow thường cần:

1. Định danh người yêu cầu.
2. Nêu incident/ticket ID và lý do.
3. Phê duyệt hoặc cơ chế khẩn cấp theo chính sách.
4. Quyền tạm thời với TTL ngắn.
5. Giới hạn scope resource.
6. Audit ngay cả khi thao tác thất bại.
7. Thu hồi quyền sau thời hạn hoặc khi incident đóng.
8. Review hậu kiểm.

Nếu JMX connector không hỗ trợ chi tiết đó, đặt thao tác đặc quyền trong management service riêng thay vì cố ép connector coarse-grained thành hệ thống IAM đầy đủ.

## 22. Hướng dẫn áp dụng cho production

### Bước 1: Lập inventory

Liệt kê các MBeans, attributes và operations được đăng ký thực tế bằng `MBeanInfo`. Không chỉ tìm `@ManagedOperation` trong source, vì libraries cũng có thể đăng ký MBeans.

### Bước 2: Phân loại tác động

Dùng ma trận L0–L4 và các trục confidentiality/integrity/availability.

### Bước 3: Chọn enforcement boundary

Đảm bảo caller identity được xác thực và truyền đáng tin cậy tới nơi kiểm tra quyền.

### Bước 4: Giảm exposure

Bỏ operations không thực sự cần; tách read-only views khỏi privileged actions.

### Bước 5: Có preconditions

Thêm expected state, request ID, dry-run hoặc preview khi thao tác phức tạp.

### Bước 6: Audit

Ghi denied/allowed attempts và outcome, không log secrets.

### Bước 7: Kiểm thử

Bao gồm wrong role, wrong ObjectName, writable attribute bypass, remote connector, context restart và denial không làm đổi state.

### Bước 8: Giám sát

Alert trên failed authorization, privileged operation burst và thay đổi configuration bất thường.

### Bước 9: Kiểm tra drift

Khi Spring/JDK/connector thay đổi, review lại MBeanInfo, policy và effective management surface.

### Bước 10: Tài liệu vận hành

Ghi rõ ai có quyền, cách xin quyền, hậu quả thao tác và hướng khôi phục.

## 23. Các lỗi thiết kế phổ biến

| Anti-pattern | Rủi ro | Cách khắc phục |
|---|---|---|
| Mọi operator dùng `readwrite` | Quyền quá rộng | Granular auth hoặc tách management surface |
| Gắn `@ManagedOperation` rồi tin là đã bảo vệ | Annotation chỉ expose | Enforce tại boundary đáng tin |
| Client gửi `role=admin` như tham số | Giả mạo quyền | Lấy principal từ authentication |
| Chỉ chặn `invoke` | Writable attribute bypass | Policy bao phủ `setAttribute(s)` |
| Gọi service trực tiếp từ JMX, bỏ qua proxy | Security advice có thể bị bypass | Kiểm thử JMX path, facade phù hợp |
| Dùng `INFO` coi là an toàn | Metadata không enforce quyền | Review tác động thực |
| Expose `purgeAll()` cho tiện vận hành | Tác động phá hủy lớn | Workflow riêng có approval |
| Không audit denial | Không thấy dò quyền | Audit tại enforcement layer |
| Retry khi JMX timeout | Thao tác có thể chạy hai lần | Request ID và reconcile status |
| Quyền wildcard domain | MBeans mới được mở ngoài ý định | Allowlist resource/capability |

## 24. Bài tập thực hành

### Bài tập A — Inventory và phân tầng

Tạo MBean có `getPendingJobs`, `pauseIntake`, `restartWorker` và `purgeQueue`. Đọc `MBeanInfo` rồi gán impact tier cho từng method, giải thích tiêu chí.

### Bài tập B — Readonly vs readwrite

Trong một lab JMX remote được cô lập và bảo vệ, tạo hai principals tương ứng với quyền readonly/readwrite. Thử đọc attribute và gọi operation thay đổi trạng thái. Ghi lại sự khác nhau, sau đó chỉ ra giới hạn của phân quyền coarse-grained.

### Bài tập C — Capability policy

Triển khai `ManagementAction` và `ManagementAuthorizer`, viết unit tests cho monitoring-reader/operator/privileged-operator. Chứng minh role thấp bị từ chối ở capability phù hợp.

### Bài tập D — Writable attribute bypass

Tạo MBean có `pause()` và `setPaused(boolean)`. Thiết kế authorization có kiểm soát cả `invoke` và `setAttribute`. Viết test chứng minh principal không đủ quyền không thể đổi state qua cả hai đường.

### Bài tập E — Spring AOP

Đặt security advice lên method facade, export qua Spring JMX, gọi bằng `MBeanServerConnection`. Kiểm tra advice thực sự được kích hoạt. Thay đổi proxy strategy trong test và xem metadata/authorization có bị ảnh hưởng không.

### Bài tập F — Operation có approval

Thiết kế workflow `preview`/approval/`execute` cho thao tác xóa dữ liệu giả. Yêu cầu request ID, expected state, audit và kiểm tra quyền từ identity đáng tin. Không dùng dữ liệu thật hoặc production để thử nghiệm.

## 25. Câu hỏi tự kiểm tra

1. Vì sao `@ManagedOperation` không tự cấp quyền truy cập?
2. Khác nhau giữa impact metadata và authorization policy là gì?
3. Principal readonly vẫn có thể gây rò rỉ thông tin trong trường hợp nào?
4. Vì sao role readwrite có thể quá rộng cho một operator?
5. Nếu chặn `invoke` nhưng cho `setAttribute`, rủi ro gì xảy ra?
6. Vì sao tham số `callerName` từ client không phải identity đáng tin?
7. Khi nào nên chuyển một operation ra workflow quản trị riêng?
8. Audit cần ghi ở lớp nào để bao phủ cả denied attempts?
9. Tại sao cần kiểm thử JMX connection thực tế thay vì chỉ unit test policy?
10. Khi nào AOP security advice có thể không được gọi?
11. Vì sao cần xét ObjectName trong policy?
12. Tại sao timeout không đủ để xác định operation có chạy thành công không?

## 26. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `@ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 — `MBeanOperationInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — `MBeanServerForwarder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/MBeanServerForwarder.html
- Oracle JDK Monitoring and Management: https://docs.oracle.com/en/java/javase/21/management/
- Spring Security Reference: https://docs.spring.io/spring-security/reference/

**Ghi nhớ:** quản lý quyền JMX phải dựa trên **mức tác động của hành động và danh tính đã được xác thực**, không dựa vào annotation, tên method hay metadata impact. Giảm surface trước, thực thi policy ở ranh giới đáng tin, bảo vệ cả operations lẫn writable attributes, áp dụng preconditions, audit và kiểm thử theo từng vai trò.
