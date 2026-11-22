# Thiết kế operation an toàn khi gọi nhiều lần trong Spring JMX

## 1. Vì sao operation có thể được gọi nhiều lần?

Trong Spring Framework JMX, phương thức được gắn `@ManagedOperation` có thể được công bố như **JMX operation** để công cụ quản trị gọi thông qua `MBeanServer` hoặc `MBeanServerConnection`. Một operation có thể dùng để reset metric, làm mới cache, reload cấu hình, tạm dừng bộ xử lý hoặc khởi động tác vụ bảo trì.

Ví dụ:

```java
@ManagedOperation(description = "Reload runtime configuration")
public void reloadConfiguration() {
    // Read and apply current configuration.
}
```

Không nên giả định operation chỉ được gọi đúng một lần. Trong thực tế, cùng một operation có thể được gọi lặp lại vì:

- Người vận hành nhấn nút **Invoke** nhiều lần trong JConsole hoặc một công cụ JMX khác.
- Script quản trị gọi lại sau timeout vì không biết lời gọi trước đã thực thi hay chưa.
- Hai công cụ giám sát hoặc hai nhân viên cùng thao tác.
- Một hệ thống tự động gọi operation theo lịch hoặc khi phát hiện cảnh báo.
- Kết nối JMX remote bị gián đoạn sau khi server đã thực thi nhưng trước khi client nhận được kết quả.
- Runtime có nhiều thread thực thi lời gọi quản trị đồng thời.

Một operation thiếu thiết kế an toàn có thể reset sai trạng thái, chạy hai tác vụ cùng lúc, gửi thông báo trùng, xóa dữ liệu nhiều lần hoặc làm cấu hình bị thay đổi ngoài dự kiến.

**Mục tiêu:** định nghĩa hành vi rõ ràng cho lời gọi lặp lại, lời gọi đồng thời và trường hợp kết quả thực thi không chắc chắn.

## 2. Phân biệt idempotency, thread safety và retry safety

Ba thuộc tính này liên quan nhưng không giống nhau.

### 2.1. Idempotency — tính lũy đẳng

Một operation **idempotent** khi thực thi nó nhiều lần với cùng ngữ cảnh yêu cầu có cùng hiệu quả trạng thái cuối như thực thi một lần.

Biểu diễn khái niệm:

```text
f(f(state)) = f(state)
```

Ví dụ:

```java
public void pause() {
    paused = true;
}
```

Gọi `pause()` một lần hoặc nhiều lần đều hướng trạng thái đến `paused=true`. Đây là tính idempotent về trạng thái cuối, với giả định không có tác động phụ khác.

Ngược lại:

```java
public void incrementCounter() {
    counter++;
}
```

không idempotent: gọi hai lần tăng counter hai lần.

### 2.2. Thread safety — an toàn đồng thời

Một method có thể idempotent về mặt ý tưởng nhưng vẫn không an toàn khi nhiều thread chạy cùng lúc.

Ví dụ:

```java
if (!started) {
    startWorker();
    started = true;
}
```

Hai thread có thể cùng thấy `started=false` và cùng gọi `startWorker()`. Kết quả là worker được khởi động hai lần dù mục tiêu `start()` nghe có vẻ idempotent.

Cần đồng bộ, atomic state transition hoặc cơ chế quản lý lifecycle phù hợp.

### 2.3. Retry safety — an toàn khi thử lại

Một operation được gọi lại sau timeout cần xử lý trường hợp **server có thể đã thực thi**. Ngay cả operation thread-safe cũng chưa chắc retry-safe nếu có side effect bên ngoài.

Ví dụ `sendReport()` có khóa đồng bộ nhưng mỗi lần gọi lại đều gửi một email mới. Khi client retry, người nhận vẫn có thể nhận trùng.

Nếu tác vụ có side effect không thể tự triệt tiêu, cần **request ID/idempotency key**, lưu kết quả tác vụ hoặc cơ chế deduplication ở đúng ranh giới tác động.

## 3. Nhóm operation theo mức rủi ro

| Loại operation | Ví dụ | Vấn đề khi gọi lặp | Hướng thiết kế |
| --- | --- | --- | --- |
| Đọc trạng thái | `getHealthSnapshot()` | Tăng tải, snapshot thay đổi | Giữ read-only, giới hạn chi phí |
| Đặt trạng thái | `pause()`, `setEnabled(true)` | Trạng thái cuối thường không đổi | Idempotent state transition |
| Reset bộ đếm | `resetStatistics()` | Có thể mất thêm dữ liệu đo giữa các lần reset | Xác định ranh giới reset và thời điểm |
| Làm mới cache | `refreshCache()` | Trùng tác vụ, tăng tải downstream | Single-flight hoặc coalesce |
| Khởi chạy job | `startReindex()` | Chạy nhiều job và tranh tài nguyên | State machine, operation ID |
| Gửi hiệu ứng ngoài | `sendNotifications()` | Gửi trùng, tạo nhiều bản ghi | Idempotency key, durable deduplication |
| Xóa dữ liệu | `purgeExpiredData()` | Có thể ảnh hưởng dữ liệu mới hoặc rollback khó | Điều kiện chọn rõ, bảo vệ quyền và chạy bất đồng bộ |

Không phải operation nào cũng cần idempotency key hay database lưu lịch sử. Chọn cơ chế phù hợp **tác động thật** của phương thức.

## 4. Ví dụ cơ bản: pause và resume idempotent

Giả sử một bộ xử lý cần chuyển qua hai trạng thái: chạy và tạm dừng.

```java
import java.util.concurrent.atomic.AtomicBoolean;

public class WorkerControl {
    private final AtomicBoolean paused = new AtomicBoolean(false);

    public boolean isPaused() {
        return paused.get();
    }

    public void pause() {
        paused.set(true);
    }

    public void resume() {
        paused.set(false);
    }
}
```

Các method này idempotent về trạng thái:

```text
pause(); pause();    -> paused = true
resume(); resume();  -> paused = false
```

Tuy nhiên, nếu việc pause thực tế phải dừng nhận công việc, đóng kết nối hoặc phát sự kiện, chỉ đổi cờ là chưa đủ. Cần liên kết trạng thái với tài nguyên thực và xác định side effect có được phát lại không.

### Operation có thể trả kết quả chuyển trạng thái

```java
public boolean pause() {
    return paused.compareAndSet(false, true);
}
```

Giá trị trả về:

- `true`: lời gọi này đã chuyển trạng thái từ chạy sang pause.
- `false`: trạng thái đã pause trước đó.

Điều này hữu ích khi caller cần biết operation có thực sự thay đổi trạng thái hay không. Không nên coi `false` là lỗi nếu mục tiêu của người vận hành đơn giản là “bảo đảm hệ thống đang pause”.

### Bọc bằng Spring @ManagedOperation

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.workers:type=WorkerControl,name=primary",
    description = "Worker lifecycle management"
)
public class WorkerManagement {
    private final AtomicBoolean paused = new AtomicBoolean();

    @ManagedAttribute
    public boolean isPaused() {
        return paused.get();
    }

    @ManagedOperation(description = "Pause processing if not paused")
    public boolean pause() {
        return paused.compareAndSet(false, true);
    }

    @ManagedOperation(description = "Resume processing if paused")
    public boolean resume() {
        return paused.compareAndSet(true, false);
    }
}
```

Đoạn trên minh họa atomic transition; ứng dụng production cần bảo đảm scheduler/consumer thực sự tôn trọng cờ `paused`.

## 5. Điều kiện trước và sau khi gọi operation

Một operation an toàn cần có **precondition** và **postcondition** đủ rõ.

Ví dụ `reloadConfiguration()`:

- Precondition: cấu hình mới hợp lệ và nguồn cấu hình có thể truy cập.
- Trong lúc chạy: không để lộ cấu hình nửa cập nhật cho thread khác.
- Postcondition khi thành công: tất cả thành phần liên quan sử dụng cùng phiên bản cấu hình đã áp dụng.
- Khi thất bại: vẫn giữ cấu hình cũ hoặc chuyển sang trạng thái lỗi có thể quan sát, không để hệ thống ở trạng thái không xác định.
- Khi lặp lại cùng phiên bản: không áp dụng lại các side effect không cần thiết.

Một hợp đồng vận hành nên trả lời:

1. Gọi lại khi đã hoàn tất có làm gì thêm không?
2. Gọi khi đang chạy sẽ bị từ chối, chờ hay gộp vào tác vụ hiện có?
3. Nếu timeout, client kiểm tra kết quả bằng cách nào?
4. Lỗi có để lại phần công việc đã hoàn thành không?
5. Có cần mã định danh yêu cầu để phân biệt hai lần thực thi có chủ đích?

## 6. Single-flight: chỉ cho phép một tác vụ chạy cùng thời điểm

Với operation làm mới cache, hai lời gọi đồng thời có thể cùng tải dữ liệu, tăng tải database hoặc ghi snapshot cạnh tranh. Một giải pháp là **single-flight**: chỉ một lần refresh đang chạy.

```java
import java.util.concurrent.atomic.AtomicBoolean;

public class CacheRefreshService {
    private final AtomicBoolean refreshing = new AtomicBoolean();

    public boolean refresh() {
        if (!refreshing.compareAndSet(false, true)) {
            return false; // Another refresh is already running.
        }

        try {
            loadAndPublishNewSnapshot();
            return true;
        } finally {
            refreshing.set(false);
        }
    }

    private void loadAndPublishNewSnapshot() {
        // Build a complete new snapshot, then publish it atomically.
    }
}
```

Spring management adapter:

```java
@ManagedOperation(
    description = "Refresh cache; returns false if refresh is running"
)
public boolean refreshCache() {
    return refreshService.refresh();
}
```

Cách này ngăn chạy trùng **trong cùng object/JVM** ở cùng thời điểm. Nó không bảo đảm chỉ chạy một lần trên nhiều JVM, nhiều replica hoặc trong khoảng thời gian sau khi lượt trước đã kết thúc.

Nếu nhiều client gọi lại sau khi refresh hoàn tất, tác vụ có thể chạy lại. Muốn gộp các lời gọi cùng request/phiên bản, cần thiết kế thêm operation key hoặc kiểm tra version đang được áp dụng.

### Chọn hành vi cho lời gọi trong lúc đang chạy

Một trong các hợp đồng có thể dùng:

- Trả `ALREADY_RUNNING` cùng operation ID hiện có.
- Trả `false` và tài liệu hóa ý nghĩa “đang chạy”.
- Chờ tác vụ hiện tại có giới hạn thời gian.
- Xếp hàng một tác vụ mới nếu nhu cầu vận hành thật sự yêu cầu.

Không nên âm thầm chạy hai tác vụ đắt đỏ nếu system chỉ cho phép một tác vụ cùng thời điểm.

## 7. Asynchronous operation và trạng thái theo dõi

Các operation dài như rebuild index, full cache warm-up, backup snapshot hoặc đồng bộ hệ thống thường không phù hợp lời gọi JMX đồng bộ kéo dài.

Thiết kế tốt hơn:

```text
startReindex()
    -> trả operation ID
    -> worker chạy bất đồng bộ
    -> JMX attributes cho biết trạng thái
    -> client theo dõi tiến độ/kết quả
```

Ví dụ hợp đồng quản trị:

```java
public interface ReindexManagementMBean {
    String startReindex();
    String getCurrentOperationId();
    String getCurrentStatus();
    int getProgressPercent();
}
```

Trạng thái có thể gồm:

```text
IDLE
RUNNING
SUCCEEDED
FAILED
CANCELLED
```

Điểm thiết kế quan trọng:

- Operation ID phải gắn với **một lượt thực thi**.
- Khi đang chạy, lời gọi `startReindex()` tiếp theo cần có chính sách nhất quán: trả ID hiện tại hoặc từ chối rõ ràng.
- Client có thể kiểm tra trạng thái sau timeout mà không phải khởi động lại.
- Khi process restart, operation đang chạy có được khôi phục không là quyết định riêng; không được hứa bền vững nếu trạng thái chỉ nằm trong bộ nhớ.
- Nếu job có side effect bền vững, cần quản lý checkpoint/recovery phù hợp.

### Một state machine đơn giản

```text
IDLE --start--> RUNNING
RUNNING --success--> SUCCEEDED
RUNNING --error--> FAILED
RUNNING --cancel--> CANCELLED
SUCCEEDED/FAILED/CANCELLED --new start--> RUNNING
```

Một hệ thống có thể yêu cầu thêm `STOPPING` hoặc `CANCELLING`. Các transition hợp lệ phải được xác định trước để tránh race condition.

## 8. Idempotency key khi operation có side effect bên ngoài

Giả sử operation:

```java
@ManagedOperation
public void publishReport() {
    reportPublisher.publish();
}
```

Nếu client gọi lại sau timeout, báo cáo có thể được gửi hai lần. Với công việc có side effect cần hạn chế trùng, thêm **operation key** do caller cung cấp:

```java
@ManagedOperation(
    description = "Publish a report once per request key"
)
public String publishReport(String requestKey) {
    return reportService.publishOnce(requestKey);
}
```

Hợp đồng:

1. Caller tạo `requestKey` duy nhất cho một ý định nghiệp vụ.
2. Mọi retry của cùng ý định dùng lại **chính key đó**.
3. Server kiểm tra key đã được tiếp nhận/hoàn thành chưa.
4. Nếu đã hoàn thành, trả lại trạng thái/kết quả đã lưu; không tạo side effect mới.
5. Nếu đang chạy, trả `IN_PROGRESS` hoặc operation ID hiện tại.
6. Nếu key mới, thực thi theo quy trình có kiểm soát.

### Một map trong bộ nhớ có đủ không?

Một `ConcurrentHashMap` có thể ngăn lặp trong một JVM khi process đang sống, nhưng **không đủ** nếu yêu cầu survives restart hoặc nhiều replica.

Đối với các side effect quan trọng, dùng storage có khả năng đồng bộ và lưu bền, ví dụ database với unique constraint trên `requestKey` và trạng thái operation. Nhưng vẫn cần xử lý khoảng trống giữa “ghi trạng thái” và “thực hiện side effect”; khi giao tiếp với hệ thống ngoài, có thể cần transactional outbox, sự hỗ trợ idempotency từ downstream hoặc một quy trình đối soát.

**Idempotency key giảm nguy cơ xử lý trùng; nó không tự biến một side effect bên ngoài thành exactly-once trong mọi tình huống.**

## 9. Race condition: kiểm tra rồi hành động

Đoạn mã:

```java
if (!jobRunning) {
    jobRunning = true;
    startJob();
}
```

không an toàn khi hai thread cùng gọi. Cả hai có thể đọc `false`.

Giải pháp bằng atomic CAS:

```java
import java.util.concurrent.atomic.AtomicBoolean;

private final AtomicBoolean running = new AtomicBoolean();

public boolean startJob() {
    if (!running.compareAndSet(false, true)) {
        return false;
    }

    try {
        runJob();
        return true;
    } finally {
        running.set(false);
    }
}
```

Đây là mẫu an toàn cơ bản cho một tác vụ đồng bộ trong một JVM. Khi chuyển sang background worker, không nên reset `running` ngay sau khi submit task, vì task vẫn đang chạy. Trạng thái phải được reset **khi task thực sự hoàn thành**, kể cả thành công hay lỗi.

### Với background task

```java
public boolean startAsyncJob() {
    if (!running.compareAndSet(false, true)) {
        return false;
    }

    try {
        executor.execute(() -> {
            try {
                runJob();
            } finally {
                running.set(false);
            }
        });
        return true;
    } catch (RuntimeException ex) {
        running.set(false); // Submission failed.
        throw ex;
    }
}
```

Mẫu này xử lý việc executor từ chối submit nhưng chưa bao gồm operation ID, progress, kết quả bền vững hoặc phân biệt các trạng thái lỗi. Với production, nên dùng một state machine rõ ràng.

## 10. Tránh thao tác “toggle” khi muốn idempotency

Một operation như:

```java
public void toggleEnabled() {
    enabled = !enabled;
}
```

không idempotent:

```text
enabled=false
toggle() -> true
toggle() -> false
```

Nếu client retry, trạng thái có thể trở về ban đầu, trái ý định.

Thiết kế rõ hơn:

```java
public void enable() {
    enabled = true;
}

public void disable() {
    enabled = false;
}
```

Hoặc attribute đọc–ghi:

```java
@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
```

Đây là cách truyền đạt **trạng thái đích** thay vì thực hiện phép đảo trạng thái. Dù vậy, nếu setter kích hoạt side effect mỗi lần gọi, cần thiết kế nó chỉ thực hiện thay đổi khi giá trị thực sự chuyển trạng thái.

## 11. Reset statistics: cần xác định ý nghĩa khi gọi hai lần

`resetStatistics()` nhìn như một operation idempotent, nhưng cần xem dữ liệu được cập nhật liên tục.

Giả sử bộ đếm là 100:

```text
T0: count = 100
T1: reset() -> count = 0
T2: có 5 request mới -> count = 5
T3: retry reset() -> count = 0
```

Nếu gọi lại ở T3, 5 request mới cũng bị xóa khỏi thống kê. Như vậy hai lần reset **không tương đương một lần reset** khi có thay đổi trạng thái xen giữa.

Cách xử lý tùy mục đích:

- Nếu “reset ngay bây giờ” là một thao tác chủ ý mới, hai lần reset có thể là điều chấp nhận được.
- Nếu retry của cùng một ý định phải không xóa metric phát sinh sau reset đầu, cần request ID hoặc sequence/version.
- Nếu metric quan trọng, có thể dùng **epoch** hoặc snapshot để ghi lại mốc reset thay vì xóa dữ liệu đo một cách không thể phục hồi.

Ví dụ dùng epoch:

```text
statisticsEpoch = 42
resetStatistics(expectedEpoch=42)
    -> đổi epoch 43, trả 43

retry resetStatistics(expectedEpoch=42)
    -> thấy epoch hiện tại 43, không reset lần nữa
```

Cần thiết kế tương tác đồng thời với việc cập nhật counter; epoch không tự xử lý tất cả race condition.

## 12. Reload configuration: áp dụng theo version

Với `reloadConfiguration()`, nếu config nguồn đã thay đổi giữa hai lần gọi, cùng một operation có thể áp dụng hai phiên bản khác nhau. Vì vậy cần định nghĩa “gọi lại” theo gì.

Một hướng ổn định là:

```java
@ManagedOperation(
    description = "Apply a specific validated config version"
)
public String applyConfiguration(String version) {
    return configurationService.applyVersion(version);
}
```

Server có thể:

1. Kiểm tra version đã áp dụng.
2. Nếu version hiện tại khớp, trả `ALREADY_APPLIED`.
3. Nếu khác, tải và validate bản cấu hình có version cụ thể.
4. Xây trạng thái/configuration mới hoàn chỉnh.
5. Áp dụng theo một transition có kiểm soát.
6. Ghi nhận version và kết quả để client quan sát.

Đừng chỉ dựa vào việc method tên `reload` để suy ra nó idempotent. Một reload có thể phát sự kiện, kết nối lại downstream hoặc thay đổi cấu hình hệ thống mỗi lần gọi.

## 13. Operation trả gì để client biết kết quả?

Một operation chỉ trả `void` khiến client khó phân biệt các trường hợp:

- Đã thực thi và thành công.
- Đã chạy trước đó nên không làm gì thêm.
- Đang có tác vụ khác chạy.
- Yêu cầu được nhận nhưng chưa hoàn thành.
- Lời gọi thất bại do điều kiện không đáp ứng.

Với operation đơn giản, `boolean` có thể đủ khi mô tả rõ:

```text
true  = trạng thái đã thay đổi bởi lời gọi này
false = đã ở trạng thái mong muốn
```

Với operation phức tạp, có thể dùng:

```text
STARTED
ALREADY_RUNNING
ALREADY_APPLIED
REJECTED
```

Nếu dùng `String` trả trạng thái, cần thống nhất giá trị được hỗ trợ. Với MXBean, cân nhắc các Open Types hoặc kiểu đơn giản để client JMX chung có thể đọc.

Đối với tác vụ dài, nên trả operation ID và cung cấp attribute trạng thái riêng. Một response đồng bộ trả `STARTED` **không đồng nghĩa công việc đã hoàn thành**.

## 14. Lỗi, timeout và kết quả không chắc chắn

Khi JMX client gọi operation từ xa, các tình huống:

```text
Client -> invoke() -> Server
                 Server xử lý thành công
Client <- mất kết nối trước khi nhận response
```

Client thấy timeout hoặc lỗi kết nối nhưng không thể chắc chắn server đã thực hiện hay chưa. Vì vậy:

- Không mặc định retry operation có side effect không idempotent.
- Với operation idempotent theo state/version, có thể retry khi hợp đồng cho phép.
- Với operation có request key, retry bằng key cũ.
- Với async operation, truy vấn trạng thái qua operation ID.
- Với operation không hỗ trợ retry, ưu tiên kiểm tra trạng thái trước khi quyết định gọi lại.

**Lỗi kết nối chỉ xác nhận client không nhận được kết quả đáng tin cậy; không chứng minh server không thực thi.**

### Phân biệt lỗi nghiệp vụ

Một operation có thể ném exception do dữ liệu không hợp lệ, trạng thái hiện tại không cho phép hoặc tài nguyên downstream lỗi. JMX sẽ bọc/đưa lỗi qua các loại exception phù hợp, chẳng hạn `MBeanException`, `ReflectionException` hoặc lỗi kết nối.

Client nên xem root cause và metadata chữ ký, không mặc định mọi lỗi đều đáng retry.

## 15. Tránh side effect trong getter và chú ý các operation “đọc”

Một số hệ thống xuất các operation dạng:

```java
@ManagedOperation
public String inspectQueue() {
    return queueService.describe();
}
```

Nếu chỉ đọc, operation nên không làm thay đổi trạng thái nghiệp vụ. Tuy nhiên `inspectQueue()` vẫn có thể gây tải cao, khóa hoặc gọi mạng. Việc không thay đổi state không đồng nghĩa gọi bao nhiêu lần cũng không ảnh hưởng hệ thống.

Những getter/operation dùng cho giám sát định kỳ nên:

- Có giới hạn thời gian và chi phí.
- Tránh truy vấn lớn, blocking vô hạn hoặc dump lượng dữ liệu quá mức.
- Có thể dùng snapshot cache khi phù hợp.
- Được mô tả rõ là read-only và có ảnh hưởng hiệu năng nào.
- Không tạo side effect như “đã đọc thì xóa”, “đã xem thì xác nhận”.

## 16. @ManagedOperation và annotation metadata

Spring Framework cung cấp:

```java
@ManagedOperation(
    description = "Start a cache refresh when no refresh is running"
)
public boolean startRefresh() {
    return refreshService.tryStart();
}
```

Annotation giúp exporter công bố operation và description. Có thể bổ sung metadata tham số:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(
    description = "Apply a configuration version idempotently"
)
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "version",
        description = "Immutable configuration version identifier"
    )
})
public String applyConfig(String version) {
    return configurationService.applyVersion(version);
}
```

Các service `refreshService` và `configurationService` là thành phần minh họa cần được định nghĩa/inject trong ứng dụng thực. Annotation **không tự bổ sung idempotency, khóa đồng bộ hoặc retry logic**. Nó chỉ cung cấp metadata để JMX client có thể gọi method.

Cũng cần một exporter phù hợp, ví dụ `AnnotationMBeanExporter`, để Spring đọc các annotation và đăng ký MBean.

## 17. Bảo mật operation quản trị

Vì JMX operation có thể làm thay đổi trạng thái runtime, cần có ranh giới bảo vệ phù hợp:

1. Không công bố operation nhạy cảm nếu không có nhu cầu vận hành rõ.
2. Bảo vệ JMX remote bằng authentication, TLS và giới hạn network access.
3. Phân quyền đối với các thao tác nguy hiểm; `@ManagedOperation` không tự là cơ chế authorization.
4. Ghi log/audit những thao tác thay đổi trạng thái khi cần, gồm tên operation, ObjectName, request key, thời gian và kết quả; tránh ghi secret.
5. Với tác vụ nguy hiểm, thiết kế cơ chế phê duyệt hoặc API chuyên biệt nếu hệ thống yêu cầu.
6. Không coi tên method như `safeReset` là bằng chứng an toàn; cần kiểm tra implementation và side effect thật.

Lưu ý: audit của JMX không phải lúc nào cũng có danh tính người dùng đầy đủ từ mọi môi trường; mức độ nhận diện caller phụ thuộc cấu hình connector/security.

## 18. Test những trường hợp gọi lặp

Một bộ kiểm thử hữu ích cho operation quan trọng nên bao gồm những tình huống sau:

| Trường hợp | Mục tiêu |
| --- | --- |
| Gọi một lần | Thành công theo hợp đồng |
| Gọi hai lần liên tiếp | Không tạo side effect ngoài mong đợi |
| Hai thread gọi đồng thời | Không start hai job nếu chỉ cho một job |
| Gọi lại khi job đang RUNNING | Trả trạng thái/ID rõ ràng |
| Gọi lại sau khi SUCCEEDED | Hành vi phù hợp policy |
| Gọi sau timeout giả lập | Có thể xác định trạng thái trước retry |
| Operation ném exception | Trạng thái được dọn dẹp/ghi nhận đúng |
| Executor từ chối task | Không để cờ RUNNING bị kẹt |
| Restart giữa job | Tuyên bố chính xác khả năng recovery |
| Nhiều replica cùng nhận yêu cầu | Có coordination nếu yêu cầu toàn hệ thống |

### Test concurrency bằng ExecutorService

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConcurrentStartTest {
    public static void main(String[] args) throws Exception {
        CacheRefreshService service = new CacheRefreshService();
        CountDownLatch gate = new CountDownLatch(1);

        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<Callable<Boolean>> calls = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                calls.add(() -> {
                    gate.await();
                    return service.refresh();
                });
            }

            List<Future<Boolean>> results = new ArrayList<>();
            for (Callable<Boolean> call : calls) {
                results.add(pool.submit(call));
            }

            gate.countDown();
            for (Future<Boolean> result : results) {
                System.out.println(result.get());
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Đây là **mẫu mô phỏng**. Nếu `refresh()` kết thúc rất nhanh, nhiều lời gọi có thể chạy tuần tự và đều trả true; điều đó không chứng minh single-flight sai. Muốn xác nhận đúng điều kiện “không chồng lấn”, cần làm cho tác vụ giữ trạng thái RUNNING đủ lâu bằng latch trong test hoặc đo số tác vụ đồng thời tối đa bằng một counter. Test nên kiểm tra invariant thật thay vì chỉ đếm số `true` mà không kiểm soát thời gian.

## 19. Quan sát kết quả operation qua MBean attributes

Một MBean quản trị tốt nên công bố trạng thái để client kiểm tra:

```text
Attributes:
  Status            RUNNING
  CurrentOperationId 42f...
  LastSuccessTime   2026-11-11T...
  LastError         <short summary>
  ProgressPercent   75

Operations:
  startRefresh()
  cancelRefresh()
```

Những thuộc tính này giúp:

- Xác định operation đang chạy.
- Tránh retry mù sau timeout.
- Phân biệt yêu cầu đã nhận và công việc đã hoàn tất.
- Hỗ trợ người vận hành thấy lỗi mà không phải chạy lại tác vụ.
- Quan sát tiến độ của thao tác dài.

Nếu cung cấp `LastError`, tránh đưa stacktrace lớn, token hoặc dữ liệu nhạy cảm vào attribute JMX. Với trạng thái có lịch sử dài, sử dụng hệ thống log/metrics phù hợp thay vì xuất toàn bộ lịch sử như một attribute.

## 20. Đặt tên và hợp đồng operation dễ hiểu

Tên operation nên truyền đạt **đích trạng thái hoặc hành động cụ thể**:

| Nên ưu tiên | Cần cân nhắc | Lý do |
| --- | --- | --- |
| `pauseProcessing()` | `toggleProcessing()` | Trạng thái đích rõ, dễ retry |
| `applyConfigVersion(String)` | `reloadEverything()` | Có version để xác định request |
| `startReindex()` trả ID | `reindex()` chạy lâu không rõ status | Có thể quan sát tác vụ |
| `refreshCacheIfIdle()` | `refreshCache()` chạy trùng | Hợp đồng concurrency rõ |
| `resetStatistics(expectedEpoch)` | `resetStatistics()` retry vô điều kiện | Tránh xóa thêm thống kê mới |
| `getRefreshStatus()` | Gọi lại `refresh()` để biết kết quả | Tách query khỏi command |

Không phải lúc nào cần tên dài. Điều quan trọng là description phải giải thích được hành vi khi gọi lại, khi đang chạy và khi lỗi.

## 21. Mẫu thiết kế theo tình huống thực tế

### Trường hợp A: bật/tắt chức năng

Dùng state setter hoặc operation đặt trạng thái đích:

```java
public void enable()  { enabled.set(true); }
public void disable() { enabled.set(false); }
```

Idempotent về trạng thái, đồng thời an toàn nếu dùng atomic state phù hợp và side effect chỉ xảy ra khi chuyển trạng thái.

### Trường hợp B: cache refresh

Dùng single-flight để tránh chạy chồng lấn. Nếu caller cần retry sau timeout, công bố trạng thái `RUNNING/SUCCEEDED/FAILED` và operation ID.

### Trường hợp C: gửi dữ liệu sang hệ thống ngoài

Dùng idempotency key và storage deduplication phù hợp với yêu cầu bền vững. Nếu downstream hỗ trợ idempotent request, truyền key theo đúng hợp đồng downstream.

### Trường hợp D: reset metric

Xác định reset là hành động tại thời điểm gọi hay là một request có identity. Nếu retry phải không xóa dữ liệu mới, cần epoch/version hoặc request key.

### Trường hợp E: chạy tác vụ bảo trì dài

Dùng async job, status attribute, operation ID và kiểm soát lifecycle; tránh giữ JMX caller đồng bộ trong thời gian không giới hạn.

## 22. Checklist thiết kế @ManagedOperation an toàn

Trước khi công bố một operation qua JMX, trả lời:

1. **Tác dụng:** operation thay đổi trạng thái gì và ảnh hưởng tài nguyên nào?
2. **Idempotency:** gọi hai lần cùng ý định có cùng kết quả trạng thái và side effect không?
3. **Concurrency:** hai client gọi đồng thời có gây race condition không?
4. **Retry:** khi timeout, client có thể biết server đã thực thi chưa?
5. **Identity:** có cần request ID, operation ID hoặc configuration version không?
6. **State:** khi đang chạy và khi hoàn tất, client quan sát trạng thái bằng cách nào?
7. **Error:** khi thất bại giữa chừng, trạng thái còn hợp lệ và có thể phục hồi không?
8. **Lifecycle:** nếu JVM shutdown/restart giữa tác vụ, kết quả được xử lý thế nào?
9. **Security:** ai được phép gọi operation, có cần audit không?
10. **Performance:** operation có thể block, chiếm lock hoặc tạo tải lớn không?
11. **Scope:** bảo đảm single-flight trong một JVM đã đủ hay cần coordination nhiều replica?
12. **Contract:** description, tham số, kiểu trả về và ObjectName có đủ rõ cho người vận hành?

## 23. Câu hỏi tự kiểm tra

**1. Một method được đánh dấu `@ManagedOperation` có tự idempotent không?**

Không. Annotation chỉ công bố metadata JMX; tính idempotent phải đến từ logic phương thức và các side effect được quản lý.

**2. Vì sao `toggleEnabled()` không retry-safe?**

Vì gọi hai lần có thể đảo trạng thái trở lại giá trị ban đầu. Thao tác đặt trạng thái đích như `enable()` hoặc `disable()` dễ bảo đảm hơn.

**3. `AtomicBoolean` có đủ chống chạy trùng trên nhiều replica không?**

Không. Nó chỉ đồng bộ trạng thái của một đối tượng trong một JVM. Nhiều replica cần cơ chế coordination hoặc deduplication chia sẻ nếu yêu cầu toàn hệ thống.

**4. Reset counter có luôn idempotent không?**

Không. Nếu dữ liệu mới xuất hiện giữa hai lần reset, retry có thể xóa thêm dữ liệu. Cần xác định hợp đồng reset theo thời điểm, epoch hoặc request ID.

**5. Một lỗi timeout từ JMX client có chứng minh server chưa thực thi không?**

Không. Server có thể đã xử lý xong nhưng response không đến client. Nên truy vấn trạng thái trước khi retry.

**6. Khi nào cần operation ID?**

Khi tác vụ chạy lâu, bất đồng bộ hoặc client cần biết trạng thái/kết quả sau khi kết nối bị gián đoạn.

**7. Vì sao single-flight không tự bảo đảm exactly-once?**

Vì single-flight chỉ ngăn chạy đồng thời trong phạm vi bảo vệ; gọi lại sau khi tác vụ hoàn thành vẫn có thể chạy lần mới, và nhiều JVM không chia sẻ trạng thái nếu không được phối hợp.

**8. Vì sao chỉ dùng `synchronized` chưa giải quyết retry?**

Vì `synchronized` chỉ kiểm soát concurrency của một object/JVM, không nhận diện một yêu cầu đã thực thi từ trước hoặc side effect ngoài hệ thống.

## 24. Tổng kết

Khi thiết kế Spring JMX `@ManagedOperation`, hãy giả định operation có thể được gọi **nhiều lần, đồng thời và trong tình huống kết quả chưa chắc chắn**. Một operation an toàn cần hợp đồng rõ cho các trường hợp đó.

- **Đặt trạng thái đích** thay vì toggle khi muốn idempotency.
- **Atomic transition hoặc state machine** giúp xử lý concurrency trong JVM.
- **Single-flight** hạn chế tác vụ chạy chồng lấn.
- **Operation ID và trạng thái quan sát được** giúp client xử lý timeout mà không gọi lại mù.
- **Idempotency key/version và storage phù hợp** cần thiết khi side effect bền vững phải tránh trùng qua restart hoặc replica.
- **Authorization, validation và audit** bảo vệ các operation quản trị có tác động mạnh.

Điểm mấu chốt: **`@ManagedOperation` chỉ giúp JMX nhìn thấy method; an toàn khi gọi lại phải được thiết kế trong hành vi của method và các thành phần mà nó điều khiển.**

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE API — `MBeanServerConnection.invoke`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE API — `AtomicBoolean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html
