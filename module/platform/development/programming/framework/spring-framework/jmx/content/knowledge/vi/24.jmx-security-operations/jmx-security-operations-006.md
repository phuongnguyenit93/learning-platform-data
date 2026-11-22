# Operation có thể thay đổi cấu hình, cache hoặc luồng xử lý trong Spring Framework JMX

## 1. Mục tiêu và bối cảnh

Java Management Extensions (JMX) không chỉ giúp quan sát trạng thái của ứng dụng Java mà còn có thể **điều khiển trạng thái runtime**. Khi Spring Framework xuất một bean thành MBean, các phương thức được công bố dưới dạng **management operation** có thể được gọi từ JConsole, công cụ giám sát hoặc ứng dụng quản trị qua `MBeanServer.invoke(...)`.

Ví dụ, một operation có thể:

- Thay đổi cấu hình đang chạy mà không khởi động lại ứng dụng.
- Xóa hoặc làm mới bộ đệm (cache).
- Tạm dừng hoặc tiếp tục bộ xử lý nền.
- Thay đổi mức logging hoặc bật chẩn đoán.
- Yêu cầu tải lại danh sách quy tắc.
- Khởi tạo một công việc bảo trì.

Đây là khả năng hữu ích nhưng cũng là **bề mặt điều khiển đặc quyền**. Nếu operation được thiết kế không cẩn thận, một thao tác quản trị nhầm có thể làm giảm throughput, gây mất trạng thái tạm thời, tạo tải hệ thống đột biến hoặc thay đổi hành vi xử lý của ứng dụng.

Bài học thuộc nhóm **Security và vận hành** của Spring Framework JMX. Trọng tâm là cơ chế, tác động và nguyên tắc thiết kế an toàn cho **operation có thể làm thay đổi cấu hình, cache hoặc luồng xử lý**, không phải chỉ cách thêm annotation.

Sau bài học, bạn có thể:

1. Phân biệt attribute đọc trạng thái với management operation thay đổi trạng thái.
2. Xác định các loại tác động của operation tới cấu hình, cache và xử lý nền.
3. Thiết kế interface JMX hẹp, rõ mục đích, có validation và giới hạn side effect.
4. Tích hợp `@ManagedOperation` vào Spring và gọi qua `MBeanServer`.
5. Áp dụng nguyên tắc bảo mật, authorization, audit và bảo vệ remote JMX.
6. Xây dựng kết quả quan sát được cho operation đồng bộ hoặc bất đồng bộ.
7. Nhận biết rủi ro concurrency, retry, timeout, idempotency và vòng đời ứng dụng.

## 2. Management operation là gì?

Trong JMX, MBean có thể công bố:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Attribute | `ActiveJobs` | Trạng thái mà client đọc |
| Attribute writable | `Enabled` | Trạng thái có thể đọc và cập nhật |
| Operation | `clearCache()` | Hành động quản trị |
| Operation | `pauseScheduler()` | Điều khiển luồng xử lý |
| Notification | `jmx.attribute.change` | Thông tin một sự kiện đã phát |

Một management operation có tên, kiểu tham số, kiểu trả về, mô tả và metadata về tác động. Nó thường được gọi như sau:

```java
Object result = server.invoke(
    objectName,
    "clearCache",
    new Object[0],
    new String[0]
);
```

Trong Spring Framework, có thể đánh dấu một phương thức bằng:

```java
@ManagedOperation(
    description = "Clear the cache for operational recovery"
)
public void clearCache() {
    cacheService.clear();
}
```

Annotation giúp mô tả phương thức với cơ chế export phù hợp; nó **không tự mở endpoint mạng**, không tự áp dụng authorization và không bảo đảm operation an toàn. Khi JMX client có quyền gọi, mã Java bên trong sẽ thực thi theo thiết kế của ứng dụng.

## 3. Ba nhóm tác động chính

### 3.1. Thay đổi cấu hình runtime

Một operation có thể cập nhật một tham số đang chạy:

```java
@ManagedOperation(description = "Set the job polling interval")
public void setPollingIntervalMillis(long millis) {
    if (millis < 500 || millis > 60_000) {
        throw new IllegalArgumentException(
            "Polling interval must be from 500 to 60000 ms"
        );
    }
    schedulerSettings.setPollingIntervalMillis(millis);
}
```

Tác động có thể bao gồm:

- Tăng hoặc giảm tần suất gọi downstream.
- Thay đổi độ trễ xử lý.
- Tăng CPU, băng thông hoặc số lượng kết nối.
- Thay đổi hành vi của các request bắt đầu sau thời điểm cập nhật.
- Khiến cấu hình runtime khác cấu hình lưu trong file/environment.

Không nên giả định rằng việc đổi một giá trị trong memory sẽ được **lưu bền vững** qua restart. Nếu ứng dụng cần persistence, phải có thiết kế lưu và nạp cấu hình riêng.

### 3.2. Xóa hoặc làm mới cache

```java
@ManagedOperation(description = "Evict entries from the product cache")
public void evictProductCache() {
    cacheMaintenance.evictProductCache();
}
```

Xóa cache thường không làm thay đổi source of truth, nhưng vẫn có side effect vận hành:

- Tăng cache miss sau khi xóa.
- Gây truy vấn đồng thời tới database hoặc API nguồn.
- Tạo hiện tượng cache stampede nếu nhiều request cùng tái nạp.
- Làm tăng response latency tạm thời.
- Phá vỡ giả định nếu cache đang lưu trạng thái chưa được ghi bền vững (một thiết kế không nên lẫn với cache thông thường).

Vì vậy `evictAll()` thường có rủi ro cao hơn `evictKey(key)` hoặc `evictNamespace(namespace)`. Một interface quản trị tốt cần ưu tiên phạm vi tác động hẹp.

### 3.3. Tạm dừng hoặc tiếp tục luồng xử lý

```java
@ManagedOperation(description = "Pause accepting new background tasks")
public void pauseProcessing() {
    processingGate.pause();
}

@ManagedOperation(description = "Resume accepting new background tasks")
public void resumeProcessing() {
    processingGate.resume();
}
```

Một operation pause không nhất thiết phải dừng những job đang chạy. Cần mô tả rõ:

- Pause chỉ chặn việc nhận job mới hay còn yêu cầu hủy job hiện tại?
- Job đang chạy có hoàn thành không?
- Những message trong queue có tiếp tục được ack/lease/renew không?
- Có thể làm tăng queue backlog không?
- Resume có khôi phục những job bị treo hay phải dùng cơ chế retry khác?
- Nếu service restart trong lúc pause, trạng thái được khôi phục theo policy nào?

Nếu không mô tả semantics, operator có thể nghĩ rằng `pauseProcessing()` là một nút dừng an toàn trong khi thực tế nó làm gián đoạn workflow quan trọng.

## 4. Ranh giới giữa operation và business endpoint

Một management operation giải quyết yêu cầu vận hành. Business endpoint giải quyết use case của người dùng hoặc đối tác.

```text
JConsole / JMX client
       |
       v
MBeanServer.invoke(...)
       |
       v
Operational control adapter
       |
       v
Runtime service: cache / scheduler / config
```

Một luồng nghiệp vụ khác:

```text
HTTP / gRPC / message client
       |
       v
Business API adapter
       |
       v
Application service / domain workflow
```

Không nên export một phương thức xử lý nghiệp vụ như `approvePayment(accountId)` hoặc `deleteCustomer(customerId)` qua JMX chỉ để tiện thao tác. Đường gọi JMX có thể không đi qua các thành phần authentication, authorization, rate limit, request validation hoặc audit dành riêng cho business API.

Tuy nhiên, điều đó không có nghĩa mọi thao tác vận hành phải qua JMX. Một hệ thống cũng có thể xây dựng protected admin API hoặc job control plane. Điều cốt lõi là xác định **đúng trách nhiệm và quyền** của từng entry point.

## 5. Thiết kế Spring MBean cho điều khiển runtime

Một mẫu phù hợp là tách logic vào service, còn MBean adapter chỉ công bố những tác vụ quản trị cần thiết.

### 5.1. Service quản lý trạng thái xử lý

```java
package com.example.ops;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Service;

@Service
public class ProcessingControlService {

    private final AtomicBoolean acceptingNewJobs =
        new AtomicBoolean(true);

    public boolean isAcceptingNewJobs() {
        return acceptingNewJobs.get();
    }

    public void pause() {
        acceptingNewJobs.set(false);
    }

    public void resume() {
        acceptingNewJobs.set(true);
    }

    public boolean tryAcceptJob() {
        return acceptingNewJobs.get();
    }
}
```

Mẫu này minh họa một cổng kiểm tra trạng thái. Trong ứng dụng production, thao tác `tryAcceptJob()` đơn giản như trên có thể tạo race giữa kiểm tra và tiếp nhận job. Nếu cần guarantee mạnh rằng “sau pause không có job mới được nhận”, cần đồng bộ cơ chế admission, queue và worker theo hợp đồng cụ thể.

### 5.2. MBean adapter

```java
package com.example.ops;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=ProcessingControl,name=Main",
    description = "Operational controls for background processing"
)
public class ProcessingControlMBean {

    private final ProcessingControlService service;

    public ProcessingControlMBean(
            ProcessingControlService service) {
        this.service = service;
    }

    @ManagedAttribute(
        description = "Whether new background jobs are accepted"
    )
    public boolean isAcceptingNewJobs() {
        return service.isAcceptingNewJobs();
    }

    @ManagedOperation(
        description = "Stop admitting new background jobs"
    )
    public void pauseProcessing() {
        service.pause();
    }

    @ManagedOperation(
        description = "Allow admitting new background jobs"
    )
    public void resumeProcessing() {
        service.resume();
    }
}
```

Các thành phần đã được tách:

- Service chịu trách nhiệm thực thi quy tắc điều khiển runtime.
- JMX adapter chỉ lộ ba khả năng quản trị đã chọn.
- Attribute cho biết trạng thái mà operation thay đổi.
- Operation có tên và description thể hiện mục đích.
- Không công bố tràn lan toàn bộ phương thức nội bộ.

Nếu không cần expose một thao tác ra JMX, đừng đánh dấu nó chỉ vì nó public trong Java.

### 5.3. Kích hoạt Spring JMX export

Có thể dùng cấu hình annotation-driven:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Khi `ApplicationContext` chứa MBean bean và hạ tầng export phù hợp, Spring có thể đăng ký resource đã được đánh dấu. Cần bảo đảm `MBeanServer` mà client sử dụng chính là server nhận đăng ký.

Cấu hình cụ thể còn phụ thuộc phiên bản Spring, môi trường và việc dùng Spring Boot JMX auto-configuration. Tránh chạy nhiều exporter cùng đăng ký ObjectName giống nhau.

## 6. Gọi operation qua MBeanServer

Client JMX cần `ObjectName`, tên operation, mảng tham số và signature.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.ops:type=ProcessingControl,name=Main"
);

server.invoke(
    name,
    "pauseProcessing",
    new Object[0],
    new String[0]
);

boolean accepting = (Boolean) server.getAttribute(
    name, "AcceptingNewJobs"
);

System.out.println("Accepting new jobs: " + accepting);
```

Kết quả dự kiến là `false` nếu không có tác nhân khác thay đổi trạng thái giữa lời gọi và phép đọc.

Nếu có parameter:

```java
server.invoke(
    name,
    "setPollingIntervalMillis",
    new Object[] { Long.valueOf(2000L) },
    new String[] { "long" }
);
```

Chữ ký `"long"` phản ánh kiểu tham số nguyên thủy được khai báo ở method, không phải `"java.lang.Long"`. Khi có overload, signature giúp chọn đúng operation.

Không gọi operation bằng route HTTP nếu ứng dụng chưa xây dựng bridge riêng. `@ManagedOperation` là Spring JMX metadata, không phải `@PostMapping`.

## 7. Hiểu rủi ro theo phạm vi side effect

Mỗi operation cần có mô tả phạm vi:

| Operation | Phạm vi có thể ảnh hưởng | Rủi ro |
| --- | --- | --- |
| `getStatus()` | Chỉ đọc trạng thái | Thấp nếu không lộ dữ liệu nhạy cảm |
| `resetCounters()` | Thống kê runtime | Mất mốc so sánh số liệu |
| `evictKey("A")` | Một mục cache | Cache miss cục bộ |
| `evictAll()` | Toàn bộ cache | Tăng tải lớn trên backend |
| `setPollingInterval(500)` | Scheduler | Tăng tần suất/tải |
| `pauseProcessing()` | Admission của worker | Queue backlog, trễ xử lý |
| `stopWorkers()` | Worker pool | Giảm khả năng phục vụ hoặc gián đoạn công việc |
| `reloadConfiguration()` | Nhiều thành phần | Mất tính nhất quán nếu áp dụng một phần |

Bảng trên là khung đánh giá, không phải phân loại cố định cho mọi hệ thống. Ví dụ `evictKey` có thể rất nguy hiểm nếu item bị xóa chứa trạng thái đặc thù; `resetCounters` có thể ảnh hưởng alert nếu hệ thống theo dõi số liệu bằng cách lấy chênh lệch giữa các lần đọc.

Trước khi export, hãy trả lời: **ai gọi, vì sao gọi, tác động ở phạm vi nào, có rollback không, kết quả có quan sát được không?**

## 8. Validation và giới hạn đầu vào

Management interface không nên dựa vào giả định rằng chỉ người vận hành đáng tin mới gọi nó. Tham số vẫn cần được kiểm tra.

Ví dụ:

```java
@ManagedOperation(
    description = "Set maximum worker count within approved range"
)
public void resizeWorkers(int requested) {
    if (requested < 1 || requested > 64) {
        throw new IllegalArgumentException(
            "Worker count must be between 1 and 64"
        );
    }
    workerPool.resize(requested);
}
```

Một số quy tắc hữu ích:

1. Kiểm tra miền giá trị và đơn vị (`ms`, `seconds`, bytes, số worker).
2. Không cho client truyền đường dẫn file hệ thống tùy ý vào operation.
3. Không cho nhập tên class hoặc lệnh hệ điều hành tự do từ JMX.
4. Giới hạn phạm vi: cache key hoặc namespace được phép.
5. Từ chối thay đổi khi trạng thái hệ thống không phù hợp.
6. Không dùng metadata description như cơ chế thực thi validation.
7. Không trả stack trace, secret hoặc dữ liệu cá nhân trong kết quả.

Với operation làm thay đổi cấu hình, kiểm tra cả **tính hợp lệ cục bộ** và **invariant hệ thống**. Ví dụ tăng thread pool có thể hợp lệ theo min/max nhưng vẫn vượt giới hạn tài nguyên hiện tại.

## 9. Bảo mật kết nối JMX

JMX Remote là kênh quản trị đặc quyền. Nếu bật connector từ xa, bảo mật cần được thiết kế rõ.

Các lớp bảo vệ thường cần:

- Network segmentation: chỉ mở endpoint từ mạng quản trị được phép.
- Xác thực: biết ai đang kết nối.
- Mã hóa: bảo vệ dữ liệu trên đường truyền theo connector/protocol.
- Phân quyền: giới hạn ai được đọc attribute, ghi attribute hoặc gọi operation.
- Audit: ghi nhận hành động quan trọng và kết quả theo operator.
- Least privilege: không cấp quyền điều khiển toàn bộ hệ thống nếu chỉ cần đọc metrics.
- Chính sách secrets: không ghi credentials trong source hoặc log.
- Kiểm soát endpoint RMI và các cổng thực tế nếu dùng JMX RMI.

Không nên nhầm `ObjectName` domain như `com.example.ops` là một security boundary. Domain chỉ là một phần tên JMX; quyền truy cập phụ thuộc connector/server/authorization.

Ngoài ra, việc tạo `MBeanServer` riêng không tự tạo sandbox. Một connector có quyền gọi operation trên server đó vẫn có thể thực thi những thao tác mà MBean công bố.

## 10. Audit và accountability

Các operation làm thay đổi runtime có thể gây sự cố vận hành. Khi có sự kiện như pause scheduler hoặc thay config, cần có dấu vết để đối soát.

Một audit record có thể bao gồm:

```text
timestamp: 2026-11-11T10:00:00Z
operation: pauseProcessing
target: com.example.ops:type=ProcessingControl,name=Main
initiator: ops-user-or-automation-id
result: SUCCESS
correlationId: 5e80...
```

Đây là cấu trúc minh họa. JMX MBean method **không tự nhận được danh tính người dùng đã xác thực** như một HTTP controller nhận principal. Khi cần audit identity đáng tin cậy, phải thiết kế lớp connector/authorization hoặc control plane truyền và xác thực thông tin phù hợp; không tự gán “admin” cho mọi lời gọi.

Cần phân biệt:

- **Requested:** một người gọi đã yêu cầu thay đổi.
- **Accepted:** hệ thống chấp nhận yêu cầu.
- **Applied:** thay đổi đã được áp dụng.
- **Verified:** trạng thái runtime được kiểm tra lại.
- **Failed:** yêu cầu bị từ chối hoặc quá trình thực thi thất bại.

Đối với operation bất đồng bộ, trả `STARTED` không đồng nghĩa `SUCCESS` cuối cùng.

## 11. Idempotency, concurrency và retry

### 11.1. Operation được gọi lại nhiều lần

Trong vận hành, một client có thể mất kết nối sau khi đã gửi request nhưng trước khi thấy response. Khi retry, không biết lần đầu đã thực hiện chưa.

Một số operation dễ thiết kế idempotent:

```java
public void pauseProcessing() {
    acceptingNewJobs.set(false);
}
```

Gọi nhiều lần vẫn dẫn về trạng thái `false`.

Ngược lại, operation như:

```java
public void rotateKey() {
    keyManager.rotate();
}
```

có thể tạo tác động mới sau mỗi lần gọi; retry mù là nguy hiểm. Những thao tác như vậy cần job ID, precondition, audit và policy xác nhận nếu thật sự được expose qua JMX.

### 11.2. Concurrency

Hai operator hoặc automation có thể gọi operation đồng thời:

```text
Operator A: pauseProcessing()
Operator B: resumeProcessing()
```

Nếu không có cơ chế version hoặc state transition rõ ràng, trạng thái cuối có thể phụ thuộc thời điểm chạy. Với operation quan trọng, có thể dùng state machine, compare-and-set, expected version hoặc cơ chế serialize command phù hợp.

Không nên giữ một lock lớn trong lúc gọi downstream lâu; điều đó có thể làm nghẽn các thao tác quan sát JMX khác hoặc luồng nghiệp vụ.

### 11.3. Timeout không có nghĩa operation đã rollback

Nếu client JMX timeout hoặc mất kết nối, method phía server vẫn có thể đã thực hiện hoặc tiếp tục chạy. Không nên coi timeout là bằng chứng operation thất bại hoàn toàn.

Khi operation có side effect lớn, thiết kế nên hỗ trợ **đọc lại trạng thái thực tế** và sử dụng idempotency hoặc request ID thay vì tự động retry không giới hạn.

## 12. Tác vụ dài hạn và chạy bất đồng bộ

Một số thao tác như rebuild cache, reload hàng triệu entries hoặc pause một cụm worker cần thời gian dài. Đừng buộc lời gọi JMX giữ kết nối chờ mãi.

Một cách thiết kế là operation **nhận yêu cầu** rồi trả ID, trong khi worker nội bộ xử lý và công bố trạng thái.

```java
@ManagedOperation(description = "Start a cache rebuild")
public String requestCacheRebuild() {
    if (!rebuildRunning.compareAndSet(false, true)) {
        return "ALREADY_RUNNING";
    }

    String id = java.util.UUID.randomUUID().toString();

    try {
        rebuildExecutor.submit(() -> {
            try {
                cacheMaintenance.rebuild();
                lastOutcome = "SUCCESS";
            } catch (Exception ex) {
                lastOutcome = "FAILED";
            } finally {
                rebuildRunning.set(false);
            }
        });
    } catch (RuntimeException rejected) {
        rebuildRunning.set(false);
        throw rejected;
    }

    return id;
}
```

Đây là ví dụ minh họa, giả định `rebuildRunning` là `AtomicBoolean`, `rebuildExecutor` là executor được quản lý vòng đời, `cacheMaintenance` là service và `lastOutcome` được công bố phù hợp. Code production cần gắn kết request ID với trạng thái/exception cuối và xử lý shutdown, queue saturation và persistence theo yêu cầu.

Có thể công bố:

```java
@ManagedAttribute(description = "Whether a rebuild is running")
public boolean isRebuildRunning() {
    return rebuildRunning.get();
}

@ManagedAttribute(description = "Outcome of the last rebuild")
public String getLastOutcome() {
    return lastOutcome;
}
```

Các attribute này giúp operator kiểm tra trạng thái. Nếu hệ thống cần retry bền vững, nhiều bước, phân phối hoặc approval, hãy cân nhắc một job scheduler/control plane chuyên dụng thay vì dựa hoàn toàn vào JMX.

## 13. Thay đổi cấu hình có thể mất tính nhất quán

Cấu hình không phải lúc nào cũng chỉ có một biến đơn lẻ. Ví dụ một hệ thống có các thuộc tính:

```text
minThreads = 4
maxThreads = 16
queueCapacity = 1000
```

Nếu cập nhật từng giá trị riêng qua ba operation, có thể tạo trạng thái trung gian không hợp lệ. Một lời gọi `setMaxThreads(2)` khi `minThreads=4` phải được từ chối hoặc xử lý như một phần của transaction cấu hình.

Mẫu thiết kế:

```java
public void updatePoolLimits(int min, int max, int queue) {
    if (min < 1 || max < min || queue < 0) {
        throw new IllegalArgumentException("Invalid pool limits");
    }

    poolConfiguration.applyAtomically(min, max, queue);
}
```

Đây là mô hình minh họa: `applyAtomically` phải được triển khai thật; chỉ đặt tên method không tạo ra atomicity.

Với thay đổi cấu hình nhiều subsystem, có thể cần:

1. Validate toàn bộ bộ tham số trước.
2. Tạo configuration snapshot bất biến.
3. Kiểm tra precondition và giới hạn tài nguyên.
4. Áp dụng thay đổi có kiểm soát.
5. Rollback hoặc chuyển sang trạng thái failed rõ ràng nếu áp dụng dở dang.
6. Công bố version, timestamp và kết quả.

Nếu một operation thay đổi cấu hình **chỉ trong bộ nhớ**, điều này cũng phải được mô tả: sau restart, cấu hình có thể quay lại giá trị từ file hoặc môi trường.

## 14. Cache invalidation có thể gây tải đột biến

Xét một cache được truy cập hàng nghìn lần mỗi giây. Nếu operator gọi `clearAllCaches()`, rất nhiều request kế tiếp có thể cùng đi tới database.

```text
Before clear:
Requests --> Cache HIT --> Fast response

After clear:
Requests --> Cache MISS --> Database
                               |
                               +--> Higher latency / load
```

Cách giảm rủi ro:

- Ưu tiên invalidation theo key hoặc namespace thay vì toàn bộ.
- Áp dụng rate limit cho lệnh quản trị nếu cần.
- Cho phép warm-up trước hoặc sau invalidation.
- Dùng single-flight hoặc coalescing để giảm nhiều request cùng tải một key.
- Theo dõi cache hit ratio, backend latency và error rate.
- Có khả năng từ chối hoặc trì hoãn clear khi backend đang quá tải.
- Không kết hợp clear và reload dữ liệu quá lớn trong một lời gọi JMX đồng bộ.

Một operation mang tên `clearCache` nên mô tả rõ cache nào, phạm vi nào, dữ liệu nào bị ảnh hưởng và tác động dự kiến.

## 15. Điều khiển luồng xử lý và trạng thái job

Tạm dừng worker hoặc scheduler phải được định nghĩa cẩn thận. Có ít nhất ba kiểu điều khiển:

| Kiểu | Ý nghĩa | Điểm cần quyết định |
| --- | --- | --- |
| Pause admission | Không nhận job mới | Job đang chạy tiếp tục hay dừng? |
| Drain | Ngừng nhận mới và chờ job đang chạy hoàn thành | Timeout, chuyển giao lease và readiness |
| Stop | Yêu cầu dừng worker/scheduler | Hủy job, checkpoint, shutdown hooks |

Không nên dùng một method tên `stopProcessing()` cho cả ba cách nếu contract không rõ ràng. Điều này dễ làm operator hiểu sai hậu quả.

Một mô hình trạng thái:

```text
RUNNING --pause--> PAUSED
PAUSED  --resume-> RUNNING
RUNNING --drain--> DRAINING
DRAINING --finish--> PAUSED
```

Với hệ thống thật, trạng thái có thể thêm `FAILED`, `STOPPING`, `STOPPED`. Các transition cần kiểm tra hợp lệ. Nếu gọi `resume` trong lúc `DRAINING`, thiết kế phải quyết định chấp nhận, hủy drain hay từ chối.

Một operation nên có khả năng đọc trạng thái tương ứng qua attribute, chẳng hạn `ProcessingState`, `ActiveJobs`, `QueuedJobs`, `LastTransition`. Điều đó giúp automation tránh suy luận sai từ một response đơn lẻ.

## 16. Metadata operation và mức độ tác động

JMX cung cấp `MBeanOperationInfo` chứa metadata như tên, mô tả, signature, return type và impact classification.

Có thể khám phá:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(objectName);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "name=%s impact=%d return=%s%n",
        operation.getName(),
        operation.getImpact(),
        operation.getReturnType()
    );
}
```

Các giá trị impact chuẩn của JMX phân loại operation là action, informational, action/info hoặc unknown. Nhưng đây chỉ là **metadata**, không phải ACL và không tự ngăn method thay đổi trạng thái.

Vì vậy ngay cả operation được mô tả là informational vẫn cần xem xét side effect thực tế. Client quản trị cũng không nên coi impact classification là bằng chứng chắc chắn về an toàn.

Có thể viết description:

```java
@ManagedOperation(
    description = "Evicts only the search cache; may temporarily raise DB load"
)
public void evictSearchCache() {
    cacheMaintenance.evictSearchCache();
}
```

Description giúp con người nhận thức tác động, nhưng **không thay thế validation, authorization hoặc guardrail** trong code.

## 17. Xử lý lỗi khi invoke

Một JMX client có thể gặp nhiều loại lỗi:

| Lỗi | Trường hợp thường gặp |
| --- | --- |
| `InstanceNotFoundException` | Không tìm thấy MBean dưới ObjectName trên server đang dùng |
| `ReflectionException` | Operation name/signature không khớp hoặc vấn đề reflection |
| `MBeanException` | MBean method gây exception được JMX bao bọc |
| `RuntimeMBeanException` | Lỗi runtime từ MBean |
| `SecurityException` | Thao tác bị từ chối do cơ chế bảo mật phù hợp |
| `IOException` (remote) | Lỗi kết nối/transport |

Không nên lấy lỗi mạng làm bằng chứng rằng operation chưa thực hiện. Nếu `invoke` timeout, có thể operation vẫn đang chạy hoặc đã hoàn tất.

Một cách xử lý client:

```java
try {
    server.invoke(
        objectName,
        "pauseProcessing",
        new Object[0],
        new String[0]
    );

    Object state = server.getAttribute(
        objectName,
        "AcceptingNewJobs"
    );

    System.out.println("Now accepting: " + state);
} catch (Exception ex) {
    System.err.println("JMX control failed: "
        + ex.getClass().getSimpleName());

    // Tra cứu trạng thái hiện tại từ đường quản trị đáng tin cậy
    // trước khi quyết định có retry operation hay không.
}
```

Trong production, xử lý lỗi nên phân biệt rõ lỗi phía client, server, authorization và trạng thái ứng dụng; tránh bắt `Exception` chung rồi retry mù.

## 18. Lifecycle và nhiều ứng dụng trong một JVM

Một JVM có thể chứa nhiều Spring contexts hoặc nhiều ứng dụng trong application server. Những operation có side effect cần được đăng ký đúng ownership:

- `ObjectName` phải phân biệt ứng dụng, module và instance.
- `MBeanExporter` nên quản lý lifecycle của MBean mà nó đăng ký.
- Khi context đóng hoặc undeploy, phải unregister MBean và gỡ listener/connector liên quan.
- Không cho phép một MBean từ context cũ tiếp tục điều khiển service mới.
- Tránh dùng registration policy `REPLACE_EXISTING` để âm thầm chiếm ObjectName do thành phần khác sở hữu.
- Nếu nhiều context cùng trỏ platform MBeanServer, phải quản lý namespace và quyền rõ ràng.

Trong môi trường production, điều khiển runtime nên có một chủ sở hữu duy nhất hoặc một control plane điều phối, thay vì nhiều MBean khác nhau cùng ghi vào một tài nguyên mà không có coordination.

## 19. Tình huống thiết kế thường gặp

### 19.1. Muốn xóa cache để khắc phục dữ liệu cũ

Cách an toàn hơn là expose `evictProductCacheKey(String key)` hoặc một operation scope hẹp, validate key và theo dõi hit rate/backend load. Nếu cần `clearAll`, hãy xác định thời điểm, tác động dự kiến, trách nhiệm và điều kiện từ chối.

### 19.2. Muốn bật debug log tạm thời

Operation nên giới hạn mức logging, phạm vi package, thời gian bật và cách tự trở lại trạng thái bình thường. Không nên cho phép client JMX gửi tùy ý tên class, file path và nội dung script để cấu hình log.

### 19.3. Muốn tạm dừng consumer khi downstream lỗi

Xác định pause ở cấp nhận message, xử lý hay ack. Nếu không ack, hệ thống message broker có thể redeliver; nếu ack sớm, có nguy cơ bỏ mất nghiệp vụ. Operation phải phù hợp với delivery semantics của hệ thống.

### 19.4. Muốn thay đổi timeout runtime

Trước khi cho phép thay đổi, xác định timeout ảnh hưởng đến request mới hay cả request đang chạy, có áp dụng theo tenant không, và có an toàn khi tăng quá cao hoặc giảm quá thấp không.

### 19.5. Muốn thực hiện maintenance trên một cụm service

Một JMX operation local thường chỉ tác động JVM/server nơi nó được gọi. Nó không tự trở thành thao tác phân tán toàn cluster. Nếu cần coordinated rollout, hãy dùng orchestration hoặc control plane phù hợp, tránh gọi lần lượt nhiều instance mà không theo dõi trạng thái chung.

## 20. Bài tập thực hành

Sử dụng `ProcessingControlMBean` ở phần 5.

**Bước 1:** Khởi tạo Spring context và export bean qua cơ chế annotation-driven hoặc `MBeanExporter` thủ công có metadata assembler.

**Bước 2:** Kiểm tra MBean trên đúng server:

```java
ObjectName name = new ObjectName(
    "com.example.ops:type=ProcessingControl,name=Main"
);

System.out.println(server.isRegistered(name));
```

**Bước 3:** Đọc `MBeanInfo.getOperations()` để xác định `pauseProcessing` và `resumeProcessing` đã được công bố.

**Bước 4:** Đọc `AcceptingNewJobs` trước khi gọi lệnh.

**Bước 5:** Gọi `pauseProcessing` rồi đọc lại `AcceptingNewJobs`. Xác nhận giá trị chuyển từ true sang false.

**Bước 6:** Gọi `pauseProcessing` thêm lần nữa; giải thích vì sao ví dụ dùng `AtomicBoolean.set(false)` có tính idempotent.

**Bước 7:** Gọi `resumeProcessing`, đọc lại và giải thích tác động đối với việc tiếp nhận job.

**Bước 8:** Mở rộng bean bằng operation `setPollingIntervalMillis(long)` với kiểm tra min/max. Thử giá trị hợp lệ và không hợp lệ.

**Bước 9:** Viết một đoạn mô tả ngắn về các rủi ro khi operator gọi `clearAllCaches()` trong giờ cao điểm.

**Bước 10:** Đề xuất audit fields, phương thức rollback/khôi phục, và cách quan sát kết quả cho operation quan trọng của một ứng dụng cụ thể.

Lưu ý: nếu thực hành trên môi trường có dữ liệu thật, tuyệt đối không tự động gọi operation có side effect lớn hoặc thao tác test vào MBean production.

## 21. Câu hỏi tự kiểm tra

**1. JMX operation có thể thay đổi trạng thái ứng dụng không?** Có. Nó có thể cập nhật cấu hình, cache hoặc luồng xử lý nếu method thực hiện những thao tác đó.

**2. `@ManagedOperation` có tự cấp authorization không?** Không. Nó chỉ giúp mô tả/export operation trong Spring JMX.

**3. Vì sao `clearCache()` có thể làm tăng tải database?** Vì các request sau khi clear có thể đồng thời cache miss và truy vấn backend.

**4. Pause processing có đồng nghĩa hủy tất cả job đang chạy không?** Không. Phụ thuộc semantics mà service triển khai.

**5. JMX timeout có đồng nghĩa operation chưa thực thi không?** Không; phía server có thể vẫn tiếp tục hoặc đã hoàn thành.

**6. Vì sao nên có attribute trạng thái sau một operation?** Để operator xác minh hiệu quả thực tế, đặc biệt với thao tác bất đồng bộ.

**7. Có nên đưa operation thay đổi thanh toán vào JMX không?** Thường không; đó là use case nghiệp vụ cần API/workflow và quyền riêng.

**8. Domain trong ObjectName có tự bảo vệ quyền truy cập không?** Không; domain chỉ là một phần tên.

**9. Khi operation có thể được gọi lại, cần xem xét điều gì?** Idempotency, trạng thái hiện tại, điều kiện tiền đề và chính sách retry.

**10. Vì sao operation điều khiển một JVM không tự điều khiển cả cluster?** Vì JMX MBean được đăng ký trong một MBeanServer cụ thể; phối hợp nhiều JVM cần thêm cơ chế orchestration.

## 22. Ghi nhớ

- **JMX management operation có thể thay đổi runtime**, không phải chỉ đọc metrics.
- **Thay đổi cấu hình** có thể ảnh hưởng hiệu năng, consistency và persistence qua restart.
- **Cache invalidation** có thể tạo tải đột biến, nên giới hạn scope và theo dõi kết quả.
- **Pause/resume/stop** cần được định nghĩa chính xác theo queue, worker và trạng thái job.
- **`@ManagedOperation` không thay thế authentication, authorization, validation hoặc audit**.
- **Side effect phải có giới hạn**, precondition, khả năng đối soát, và nếu cần cơ chế rollback.
- **Retry sau timeout phải thận trọng** vì không biết chắc thao tác trước đã hoàn thành hay chưa.
- **MBeanInfo là metadata**, còn trạng thái sau operation nên được xác minh qua attribute hoặc control plane thích hợp.
- **Remote JMX là bề mặt đặc quyền**, cần bảo vệ bằng mạng, xác thực, mã hóa và phân quyền.
- **Mỗi operation nên có owner, phạm vi và kết quả quan sát được**, đặc biệt khi nhiều ứng dụng cùng chia sẻ JVM.

Thiết kế operation JMX an toàn không chỉ là việc làm cho một method gọi được từ JConsole. Đó là quá trình xây dựng **một hợp đồng điều khiển vận hành** với quyền, phạm vi tác động, điều kiện thực thi, hành vi thất bại và khả năng phục hồi rõ ràng.