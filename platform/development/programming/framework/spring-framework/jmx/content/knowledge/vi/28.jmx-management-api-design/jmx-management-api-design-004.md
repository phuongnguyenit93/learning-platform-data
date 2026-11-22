# Spring Framework JMX — Thiết kế operation an toàn khi gọi lặp lại

## 1. Vấn đề

Trong JMX, một client gọi operation qua `MBeanServerConnection.invoke(ObjectName, String, Object[], String[])`. Khi kết nối từ xa, lời gọi có thể timeout hoặc mất response sau khi server đã thực hiện công việc. Nếu client gọi lại mà operation không được thiết kế an toàn, hậu quả có thể là nhân đôi tác vụ, thay đổi cấu hình ngoài ý muốn, gửi thông báo lặp, tạo tài nguyên trùng hoặc xóa dữ liệu không thể khôi phục.

Chủ đề này hướng dẫn thiết kế **management operations có thể được gọi lặp lại một cách an toàn**, đặc biệt với Spring Framework JMX và các operation có tác dụng phụ. Hai ý trọng tâm là **idempotency** (gọi cùng yêu cầu nhiều lần có cùng hiệu quả quan sát được như một lần) và **kiểm soát trạng thái khi kết quả lời gọi không rõ**.

```text
JMX client
  | invoke(name, operation, params, signature)
  v
JMX connector --> MBeanServer --> Spring @ManagedOperation
  |                                    |
  |                                    +-- validate
  |                                    +-- check request ID / state
  |                                    +-- execute once
  |                                    +-- persist outcome
  |
  +-- response lost / timeout
        |
        +-- client must not blindly duplicate action
```

**Mục tiêu:** phân loại operation theo khả năng retry; dùng desired-state, request ID, duplicate detection, trạng thái truy vấn và concurrency control; biết khi nào một thao tác nguy hiểm không nên expose qua JMX; kiểm thử lặp, timeout và restart.

## 2. Idempotent nghĩa là gì?

Một thao tác idempotent cho kết quả trạng thái tương đương khi cùng request được thực hiện nhiều lần:

```text
setPaused(true) lần 1  -> paused = true
setPaused(true) lần 2  -> paused = true
setPaused(true) lần n  -> paused = true
```

Ngược lại:

```text
incrementWorkerCount(1) lần 1 -> count = 9
incrementWorkerCount(1) lần 2 -> count = 10
```

Thao tác tăng tương đối không idempotent. Nếu response cho lần 1 bị mất, client gọi lại sẽ vô tình tăng hai lần.

Idempotency không đồng nghĩa **không có side effect**. Một lệnh cấu hình như `setMaxWorkers(10)` vẫn làm thay đổi hệ thống ở lần đầu, nhưng cùng một yêu cầu lặp có thể không làm thay đổi thêm. Tuy nhiên, nếu setter gửi email hoặc tạo audit event nghiệp vụ mỗi lần gọi, cần cân nhắc cả side effects đó khi tuyên bố operation an toàn khi retry.

## 3. Phân loại các dạng management operations

| Kiểu operation | Ví dụ | Đặc điểm khi gọi lặp |
|---|---|---|
| Truy vấn read-only | `getStatus()`, `getActiveCount()` | Thường an toàn, nhưng kết quả có thể thay đổi theo thời gian |
| Đặt desired state | `setPaused(true)` | Có thể idempotent nếu triển khai theo trạng thái đích |
| Gán giá trị tuyệt đối | `setWorkerLimit(12)` | Có thể idempotent, cần validation và áp dụng thực tế |
| Điều chỉnh tương đối | `increaseLimit(2)` | Không idempotent nếu không có request ID |
| Hành động một lần | `resetStatistics()`, `clearQueue()` | Phải xem contract và tác dụng phụ cụ thể |
| Tạo tác vụ | `startReindex()` | Có nguy cơ tạo nhiều jobs trùng |
| Xóa/rotate/shutdown | `deleteCache()`, `rotateKeys()` | Rủi ro cao; nên có confirmation/authorization và trạng thái truy vấn |

Không có một quy tắc rằng mọi method tên `reset*` luôn idempotent hoặc luôn không idempotent. Ví dụ reset counter về 0 có thể lặp an toàn với state cuối cùng, nhưng nếu mỗi lần reset đều khởi động lại một tác vụ, tạo audit record hoặc xóa dữ liệu mới phát sinh giữa hai lần, việc gọi lặp có tác động mới.

## 4. Ưu tiên desired state hơn mệnh lệnh tương đối

Thay vì expose:

```java
@ManagedOperation
public void togglePaused() {
    paused = !paused;
}
```

hãy ưu tiên:

```java
@ManagedAttribute(description = "Whether new jobs are paused")
public boolean isPaused() {
    return paused;
}

@ManagedAttribute(description = "Set desired pause state")
public synchronized void setPaused(boolean requested) {
    if (paused == requested) return;
    paused = requested;
}
```

`togglePaused()` gọi hai lần sẽ đảo về trạng thái ban đầu; `setPaused(true)` gọi lại vẫn giữ paused=true. Đây là khác biệt lớn khi remote connection timeout rồi client retry.

Với operation cần phương thức rõ:

```java
@ManagedOperation(description = "Pause intake if not already paused")
public void pauseIntake() {
    setPaused(true);
}

@ManagedOperation(description = "Resume intake if currently paused")
public void resumeIntake() {
    setPaused(false);
}
```

Tách hai action theo desired state tốt hơn một `toggleIntake()` mơ hồ. Khi một thao tác đặt cấu hình đã phù hợp với JavaBean property, có thể dùng `@ManagedAttribute` getter/setter; các action phức tạp vẫn phù hợp `@ManagedOperation`.

## 5. Tình huống response bị mất

Xét chuỗi sự kiện:

```text
T0: Client invoke("startReindex")
T1: Server nhận request, tạo job J-100
T2: Server gửi response
T3: Network đứt trước khi client nhận response
T4: Client timeout; không biết J-100 đã được tạo
T5: Client retry -> có thể tạo job J-101 trùng
```

Một remote timeout thường là **ambiguous completion**, tức kết quả của lần gọi trước chưa xác định. Kết luận rằng operation chưa chạy là không an toàn.

Cách xử lý tốt là trả về một định danh tác vụ và cung cấp API truy vấn trạng thái, hoặc để client cấp request ID ổn định trước khi gọi:

```text
startReindex("request-2026-11-11-001")
getRequestStatus("request-2026-11-11-001")
```

Khi response bị mất, client dùng cùng request ID để kiểm tra hoặc gửi lại một yêu cầu đã được thiết kế duplicate-safe. **Không tạo UUID mới cho mỗi retry**; như vậy sẽ đánh lừa duplicate detection.

## 6. Thiết kế API có request ID

Ví dụ Spring management facade:

```java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=Maintenance,name=index"
)
public class IndexManagement {
    private final IdempotentReindexService service;

    public IndexManagement(IdempotentReindexService service) {
        this.service = service;
    }

    @ManagedOperation(description = "Schedule reindex once per request ID")
    public String startReindex(String requestId) {
        return service.startIfAbsent(requestId);
    }

    @ManagedOperation(description = "Inspect previous reindex request")
    public String getRequestStatus(String requestId) {
        return service.statusOf(requestId);
    }
}
```

`IdempotentReindexService` là service nghiệp vụ do ứng dụng định nghĩa, không phải class Spring có sẵn. Nó chịu trách nhiệm kiểm tra request ID, giữ result, bảo đảm concurrency và liên kết ID với task.

Ví dụ JMX client:

```java
String requestId = "maintenance-2026-11-11-001";

Object response = connection.invoke(
    objectName,
    "startReindex",
    new Object[] { requestId },
    new String[] { "java.lang.String" }
);
```

Nếu lỗi network xảy ra sau khi gửi lệnh, client không tạo requestId mới. Hãy dùng cùng ID và đọc trạng thái qua `getRequestStatus`, hoặc retry theo contract cụ thể mà service đã bảo đảm.

## 7. Kết quả trùng request phải thế nào?

Một contract rõ nên định nghĩa:

1. **First request**: bắt đầu tác vụ, trả `jobId` hoặc trạng thái `ACCEPTED`.
2. **Duplicate same request ID, same parameters**: không tạo job mới; trả cùng `jobId` hoặc kết quả đã lưu.
3. **Duplicate same request ID, different parameters**: từ chối bằng lỗi conflict; không âm thầm dùng cấu hình khác.
4. **Request đang chạy**: trả trạng thái `RUNNING` và cùng `jobId`.
5. **Request đã hoàn tất**: trả kết quả cuối hoặc mã trạng thái `SUCCEEDED`/`FAILED`.
6. **Request ID hết thời gian lưu**: contract quy định rõ hành vi; không mặc định vẫn được chống trùng mãi mãi.

Ví dụ:

```text
startReindex("req-A", "orders") -> job-101
startReindex("req-A", "orders") -> job-101
startReindex("req-A", "catalog") -> CONFLICT
```

**Đặc biệt:** `requestId` không phải mã xác thực. Client không được phép vượt authorization chỉ vì biết một ID hợp lệ. Mọi invoke vẫn cần authentication, authorization và input validation.

## 8. Không dùng check-then-act đơn giản khi có concurrency

Mẫu sau không thread-safe:

```java
if (!requests.containsKey(requestId)) {
    String jobId = createJob();
    requests.put(requestId, jobId);
}
```

Hai thread đồng thời có thể cùng thấy key vắng rồi đều tạo job. Ngay cả `ConcurrentHashMap` không làm nhiều bước `containsKey` + `createJob` + `put` thành atomic.

Trong một JVM, có thể dùng `computeIfAbsent` với một entry đại diện cho request và tránh thực thi công việc tốn thời gian trực tiếp trong map computation. Hoặc dùng synchronized/lock theo request ID và state machine có trạng thái `PENDING` trước khi submit job.

Ví dụ khung logic:

```java
public String startIfAbsent(String requestId) {
    validateRequestId(requestId);
    RequestRecord record = records.computeIfAbsent(
        requestId,
        key -> new RequestRecord(key, Status.PENDING)
    );
    scheduleOnce(record); // Phải bảo đảm atomically claim quyền chạy.
    return record.jobIdOrStatus();
}
```

Đây là pseudocode Java minh họa contract; `RequestRecord`, `scheduleOnce` và `Status` là thành phần tự xây. Chỉ dùng `computeIfAbsent` để tạo record chưa đủ bảo đảm job chỉ submit một lần; `scheduleOnce` phải có cơ chế atomic transition, như CAS từ `PENDING` sang `SCHEDULED`, trước khi submit.

## 9. Chống trùng qua nhiều JVM hoặc sau restart

Memory map chỉ chống trùng trong lifetime của một process. Nếu client kết nối tới replica khác hoặc JVM restart, trạng thái có thể mất. Khi yêu cầu chống trùng mạnh trong hệ thống phân tán, cần shared/durable store:

- Database table với unique constraint trên `(operation, request_id, scope)`.
- Transactional reservation trước khi thực thi.
- Lưu request parameters hash và trạng thái.
- Job queue có deduplication hoặc transactional outbox nếu phù hợp.
- Cơ chế lease/lock với ownership và timeout được thiết kế cẩn thận.
- Truy vấn kết quả qua API ổn định.

Ví dụ bảng dữ liệu:

```sql
CREATE TABLE management_requests (
    scope VARCHAR(100) NOT NULL,
    operation VARCHAR(100) NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    params_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    result_ref VARCHAR(128),
    PRIMARY KEY (scope, operation, request_id)
);
```

Unique constraint giúp tránh tạo hai reservation trùng, nhưng riêng reservation chưa bảo đảm side effects trong hệ thống ngoài database thực thi đúng một lần. Cần thiết kế phần thực thi, recovery sau crash và idempotency của downstream operation tương ứng.

## 10. State machine cho operation dài

Với tác vụ reindex, rebuild cache hay reload tập dữ liệu, một operation nên trả nhanh thay vì giữ remote JMX call rất lâu:

```text
ACCEPTED -> RUNNING -> SUCCEEDED
                    \-> FAILED
                    \-> CANCELLED
```

Client có thể gọi `startReindex(requestId)`, nhận `jobId` rồi dùng `getJobStatus(jobId)` hoặc readable attribute để theo dõi. Nếu response mất, dùng `getRequestStatus(requestId)`.

Trạng thái cần mô tả rõ:

- `ACCEPTED`: request đã được ghi nhận, chưa chắc job đang chạy.
- `RUNNING`: worker đã bắt đầu thực thi.
- `SUCCEEDED`: tác vụ hoàn tất theo contract.
- `FAILED`: tác vụ thất bại và cần chính sách retry/resume.
- `CANCELLED`: được hủy theo quy trình, không nhất thiết rollback side effects đã có.

**Không dùng trạng thái `RUNNING` mãi mãi khi JVM crash**; cần cơ chế heartbeat, lease hoặc recovery. Không đánh đồng “JMX call trả thành công” với “background job đã hoàn tất”.

## 11. Xử lý lỗi và lỗi không rõ kết quả

| Lỗi | Điều biết được | Hành vi client phù hợp |
|---|---|---|
| Validation failure trước thực thi | Request không hợp lệ | Sửa input, không retry y nguyên |
| Authorization denial | Caller không có quyền | Không retry đến khi quyền hợp lệ |
| `InstanceNotFoundException` | MBean không tồn tại ở server đã chọn | Kiểm tra endpoint/registration |
| `ReflectionException` | Operation/signature có vấn đề | Kiểm tra `MBeanInfo` |
| `IOException` khi chưa connect | Không mở được session | Reconnect với backoff |
| Timeout sau khi gửi invoke | Server có thể đã chạy | Query status; không tạo request mới |
| Business operation trả `FAILED` | Job đã chạy và thất bại | Áp dụng retry policy của nghiệp vụ |

Ở tầng remote JMX, `IOException` có thể xuất hiện trong quá trình invoke; không đủ bằng chứng để biết server đã nhận request hay chưa. Vì vậy phân biệt lỗi connection setup và lỗi sau khi gửi operation là rất quan trọng.

## 12. Tránh side effects khi repeated invocation

Ví dụ xấu:

```java
@ManagedOperation
public void sendDiagnosticsEmail() {
    mailService.sendReport();
}
```

Nếu client retry vì timeout, nhiều email có thể được gửi. Thiết kế tốt hơn:

```java
@ManagedOperation
public String sendDiagnosticsEmail(String requestId) {
    return diagnosticsScheduler.enqueueOnce(requestId);
}
```

Hoặc nếu chỉ muốn “gửi báo cáo mới” mỗi khi người vận hành click, phải công bố đây là operation không idempotent, ngăn retry tự động và có confirmation tại công cụ.

Với `resetStatistics()`, đặt trạng thái về 0 có vẻ idempotent, nhưng lần reset thứ hai có thể xóa những số liệu phát sinh sau lần đầu. Muốn chống gọi lại ngoài ý muốn, có thể dùng request ID hoặc operation có điều kiện với epoch/version.

## 13. Conditional update và optimistic concurrency

Trong một số trường hợp, thao tác có thể an toàn nhờ precondition:

```java
@ManagedOperation
public boolean setLimitIfVersion(int newLimit, long expectedVersion) {
    // Kiểm tra version và cập nhật atomically.
    // Trả false nếu version hiện tại đã đổi.
    return configService.compareAndSet(newLimit, expectedVersion);
}
```

Đây là ví dụ ý tưởng; `compareAndSet` cần triển khai atomic với version. Nếu client retry cùng expectedVersion sau lần thành công, lần sau trả false; client đọc lại trạng thái/version để biết trạng thái hiện tại. Không diễn giải false đơn giản là operation chưa bao giờ thành công.

Ưu điểm: tránh ghi đè thay đổi đồng thời của người vận hành khác. Nếu có nhiều nguồn cấu hình (JMX, REST, file reload), version/precondition cần được chia sẻ trên cùng một trạng thái nguồn.

## 14. Security và audit

Operation JMX có thể thay đổi production. Thiết kế an toàn bao gồm:

1. Chỉ export operations thực sự cần.
2. Dùng tên rõ: `pauseIntake`, `setWorkerCount` thay vì `toggle` hoặc `change` mơ hồ.
3. Validate request ID, input range, scope và quyền.
4. Tách read-only monitoring và privileged management.
5. Dùng JMX connector authentication/authorization và network isolation.
6. Kiểm tra Spring Security proxy nếu dựa vào `@PreAuthorize`.
7. Ghi audit request ID, operation, outcome, actor đã được xác thực.
8. Không đưa token/password vào ObjectName, request ID hoặc log.

Idempotency và authorization là hai yêu cầu độc lập: operation có chống trùng tốt vẫn nguy hiểm nếu bất kỳ client nào cũng có thể gọi.

## 15. Kiểm thử gọi lặp

Test cho operation có request ID:

```java
String requestId = "test-reindex-001";

String first = management.startReindex(requestId);
String second = management.startReindex(requestId);

assertEquals(first, second);
assertEquals(1, fakeScheduler.getSubmitCount());
```

Với JMX integration test:

```java
ObjectName name = new ObjectName(
    "com.example.app:type=Maintenance,name=index"
);

Object result1 = connection.invoke(
    name, "startReindex",
    new Object[] { "req-100" },
    new String[] { "java.lang.String" }
);
Object result2 = connection.invoke(
    name, "startReindex",
    new Object[] { "req-100" },
    new String[] { "java.lang.String" }
);
assertEquals(result1, result2);
```

Khung test trên yêu cầu MBean đã được export và fake scheduler đã được cấu hình; cần kiểm tra thêm số job thực sự được submit. Không chỉ assert hai kết quả giống nhau: một implementation lỗi có thể tạo hai jobs nhưng trả cùng response giả.

Các ca kiểm thử cần có:

- Gọi hai lần cùng ID, cùng parameters.
- Gọi cùng ID nhưng parameters khác: conflict.
- Hai threads cùng gọi đồng thời: đúng một execution.
- Timeout sau khi server nhận request rồi client retry.
- JVM restart giữa lần đầu và lần lặp.
- Hai replicas cùng nhận một request ID.
- Retry sau khi operation thất bại và policy xác định là retryable.
- Caller không đủ quyền: không tạo reservation/job.
- State readback đúng và audit không ghi sai actor.

## 16. Bài tập

### Bài 1: Đổi toggle thành desired-state

Thay `toggleMaintenance()` bằng `setMaintenanceEnabled(boolean enabled)` hoặc cặp `enableMaintenance()`/`disableMaintenance()`. Giải thích vì sao lần gọi lặp không đảo trạng thái.

### Bài 2: Phân biệt retry-safe

Xét các operation: `getState()`, `setLimit(10)`, `increaseLimit(2)`, `startBatch()`. Chỉ ra operation nào có thể an toàn khi lặp và điều kiện cần bổ sung cho những operation còn lại.

### Bài 3: Request ID bị trùng tham số

Client A gọi `startReindex("req-9", "orders")`, client B gọi cùng ID với scope `catalog`. Nếu ID thuộc cùng namespace deduplication, server nên từ chối conflict thay vì tạo job khác hoặc lặng lẽ trả kết quả cũ.

### Bài 4: Timeout sau invoke

Một request `clearCache("req-5")` timeout. Giải thích vì sao client nên gọi `getRequestStatus("req-5")` thay vì tạo `req-6`.

### Bài 5: Concurrent duplicate

Thiết kế test chạy 20 calls song song cùng request ID rồi xác minh chỉ một task được tạo. Nêu lý do `containsKey` + `put` riêng rẽ không đủ atomic.

## 17. Checklist thiết kế

- Operation có thể được gọi lặp bởi client/tool hay automatic retry không?
- Có thể biến thao tác tương đối thành desired-state không?
- Có request ID ổn định và scope rõ không?
- Có lưu params hash, trạng thái và result của request cũ không?
- Có kiểm tra duplicate atomically khi nhiều threads/replicas không?
- Có chiến lược recovery sau JVM restart không?
- Khi timeout có thể query status thay vì retry mù không?
- Có phân quyền, validation và audit phù hợp không?
- Có test concurrency, failure injection và ambiguous completion không?
- Có quy định thời hạn lưu deduplication record không?

## 18. Kết luận

Thiết kế operation JMX an toàn khi gọi lặp lại đòi hỏi suy nghĩ về **trạng thái đích, idempotency, duplicate detection và kết quả không rõ khi remote call timeout**. Ưu tiên operations dạng `setDesiredState` thay vì `toggle` hoặc `increment`. Với thao tác dài/không idempotent, dùng request ID, lưu trạng thái/result, xác định scope deduplication, kiểm soát concurrency và cung cấp API truy vấn. Các cơ chế này không thay thế authorization, validation hoặc audit, nhưng giúp tránh side effects trùng khi công cụ quản trị retry hoặc người vận hành click nhiều lần.