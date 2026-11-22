# Kiểm tra getter có gây truy vấn hoặc tác dụng phụ không

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao getter được công bố bằng `@ManagedAttribute` có thể được JMX client gọi nhiều lần, không chỉ khi người dùng bấm xem một thuộc tính.
- Phân biệt getter chỉ đọc trạng thái trong bộ nhớ với getter gây truy vấn database, gọi HTTP, đọc file, chờ khóa hoặc thay đổi dữ liệu.
- Xác định các **tác dụng phụ** và rủi ro về latency, thread contention, transaction, bảo mật, tài nguyên và hệ thống phụ thuộc.
- Thiết kế JMX attributes dựa trên snapshot hoặc counter đã được cập nhật ở luồng nghiệp vụ, giữ getter rẻ và có ngữ nghĩa rõ.
- Thực hiện kiểm tra hành vi bằng test, profiler/metrics và quan sát thực tế khi JConsole hoặc exporter polling.
- Biết khi nào nên dùng JMX operation có chủ đích thay vì một getter trông giống thao tác chỉ đọc.

## 2. Vì sao một getter quản trị cần được kiểm tra?

Trong Spring JMX, `@ManagedAttribute` đánh dấu một method để được đưa ra dưới dạng thuộc tính quản trị. Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderMonitor {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

Một JMX client có thể yêu cầu:

```java
server.getAttribute(objectName, "PendingCount");
```

Lời gọi này dẫn tới việc thực thi logic của getter (theo metadata và cơ chế dispatch của MBean). **JMX không mặc định biến getter thành một giá trị được lưu sẵn**. Nếu getter thực hiện truy vấn SQL hoặc gọi hệ thống ngoài, mỗi lần client đọc thuộc tính có thể gây thêm công việc.

Đây là điểm nguy hiểm khi một method có tên `getXxx()` trông vô hại nhưng thực chất thực hiện thao tác đắt đỏ:

```java
@ManagedAttribute
public long getPendingCount() {
    return orderRepository.countPendingOrders(); // Có thể query DB.
}
```

Một trang JConsole đọc mỗi vài giây, một exporter poll mỗi 15 giây và nhiều người vận hành cùng mở dashboard có thể tạo nhiều lần thực thi truy vấn. Nếu bảng lớn hoặc database đang nghẽn, chính hoạt động quan sát có thể làm tăng tải vào thời điểm hệ thống cần được chẩn đoán.

**Nguyên tắc:** Getter quản trị nên có chi phí và tác dụng rõ ràng; đừng suy diễn `get` đồng nghĩa với “an toàn, nhanh, không tác dụng phụ”.

## 3. JMX đọc attribute như thế nào?

Đường đi khái quát:

```text
JConsole / JMX exporter / custom client
                  |
          getAttribute("PendingCount")
                  |
                  v
             MBeanServer
                  |
             JMX metadata
                  |
                  v
          @ManagedAttribute getter
                  |
         +--------+---------+
         |                  |
         v                  v
   đọc giá trị RAM      truy vấn DB/HTTP
    nhanh, ổn định      có latency, lỗi, tải
```

Khi exporter poll nhiều attributes bằng `getAttributes`, implementation vẫn có thể gọi từng getter tương ứng. Số lần thực thi phụ thuộc exporter, bộ lọc và tần suất polling, không nên mặc định mỗi attribute chỉ được đọc một lần trong vòng đời ứng dụng.

Với MBean quản lý một process lâu dài, các client có thể kết nối đồng thời:

- JConsole/JMC hoặc công cụ vận hành.
- Exporter thu thập metric.
- Hệ thống kiểm tra trạng thái quản trị.
- Script tự động hóa.
- Người phát triển gọi thủ công qua JMX client.

Như vậy getter trở thành **điểm thực thi từ bên ngoài ứng dụng**. Các thuộc tính “chỉ đọc” về mặt JMX vẫn có thể tạo side effect nếu nội dung method có side effect.

## 4. Phân biệt attribute chỉ đọc, thuần hàm và side effect

Một getter có thể là *read-only attribute* khi metadata JMX không có setter, nhưng điều đó chỉ nói rằng **client không thể gọi setter cho attribute ấy**. Nó không bảo đảm implementation không ghi database hay thay đổi state.

Ba mức độ cần phân biệt:

| Loại getter | Ví dụ | Đánh giá |
|---|---|---|
| **Đọc snapshot RAM** | `return cachedPendingCount.get();` | Thường phù hợp với JMX polling |
| **Tính toán nhẹ, không đổi state** | `return success.sum() + failure.sum();` | Thường chấp nhận được nếu chi phí nhỏ |
| **Đọc nguồn ngoài/đắt đỏ** | `repository.countByStatus(...)` | Cần đánh giá latency và tải |
| **Thực hiện side effect** | `refreshCache(); return size;` | Không phù hợp với kỳ vọng getter chỉ đọc |
| **Chờ đồng bộ/khóa lâu** | `synchronized` trên lock có contention | Có nguy cơ gây nghẽn |
| **Gọi network** | `httpClient.getStatus()` | Dễ timeout, gây lỗi phụ thuộc ngoài |

Một getter có thể không sửa dữ liệu nhưng vẫn **không an toàn về vận hành** nếu khiến database thực hiện full table scan, tạo thread, mở kết nối mới hoặc giữ lock lâu. Ngược lại, một phép đọc counter in-memory chỉ tốn vài thao tác CPU và ít phụ thuộc hơn.

**Pure getter** theo nghĩa mạnh sẽ không làm thay đổi trạng thái quan sát được và không tạo IO; nhưng trong Java thực tế có thể có allocation nhỏ, đọc clock, cache nội bộ hay synchronized access. Mục tiêu vận hành là có **ngữ nghĩa ổn định, giới hạn chi phí và tránh tác dụng phụ không mong muốn**.

## 5. Dấu hiệu getter đang “ẩn” công việc đắt đỏ

Hãy đọc implementation và các method mà getter gọi gián tiếp. Những dấu hiệu đáng xem xét gồm:

- Repository method như `countByStatus`, `findAll`, `fetch`, `save`, `flush`.
- `EntityManager.createQuery`, `JdbcTemplate.queryForObject`, truy vấn aggregation.
- HTTP/gRPC/Redis/Kafka client gọi tới process khác.
- Đọc file, quét thư mục hoặc kiểm tra external storage.
- Vòng lặp duyệt collection lớn hoặc tính tổng trong mỗi lần getter.
- `Thread.sleep`, lock, latch, future blocking, `join()`.
- Khởi tạo lazy object, load cache hoặc refresh config.
- Ghi log nhiều ở mỗi lần đọc, làm tăng log volume.
- Increment counter, reset statistic, xóa state hoặc cập nhật timestamp.

Không phải mọi dấu hiệu đều cấm tuyệt đối. Ví dụ `countByStatus` trên bảng nhỏ có index tốt có thể đáp ứng yêu cầu, nhưng **độ trễ và tính lặp lại khi poll** phải được hiểu rõ. Một truy vấn chỉ đọc cũng vẫn làm DB chịu tải.

## 6. Ví dụ xấu: JMX getter truy vấn database mỗi lần đọc

Giả sử Spring bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderMonitor {

    private final OrderRepository repository;

    public OrderMonitor(OrderRepository repository) {
        this.repository = repository;
    }

    @ManagedAttribute
    public long getPendingOrders() {
        return repository.countPendingOrders();
    }
}
```

Đường đi:

```text
Exporter poll 15s
       |
       v
getPendingOrders()
       |
       v
SELECT COUNT(*) ... WHERE status='PENDING'
       |
       v
Database CPU / index scan / network
```

Nếu query mất 300 ms, một collector đơn lẻ chưa chắc gây vấn đề nghiêm trọng. Nhưng tải có thể tăng nếu nhiều instance hoặc nhiều collector cùng poll, và query còn chậm hơn trong thời điểm database đang bão hòa.

Ví dụ tính gần đúng về tần suất:

```text
4 collectors x 1 request/15s = 16 lần đọc/phút
10 ứng dụng x 16 = 160 lần đọc/phút
```

Đây chỉ là phép minh họa khi **mỗi collector đều thật sự gọi attribute độc lập**; không phải công thức mặc định của mọi hệ thống exporter. Tần suất thực tế cần đo từ triển khai.

Getter cũng có thể phát sinh exception như timeout/connection pool exhausted. Khi đó dashboard thiếu metric đúng lúc hệ thống gặp sự cố.

## 7. Giải pháp 1: cập nhật counter khi nghiệp vụ thay đổi

Nếu có thể xác định số lượng pending từ các transition của ứng dụng, duy trì một giá trị đo lường ở bộ nhớ và cho getter đọc nhanh.

Ví dụ:

```java
import java.util.concurrent.atomic.AtomicLong;

public class OrderStatistics {
    private final AtomicLong pending = new AtomicLong();

    public void onOrderQueued() {
        pending.incrementAndGet();
    }

    public void onOrderCompleted() {
        pending.decrementAndGet();
    }

    public long getPending() {
        return pending.get();
    }
}
```

Management bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderManagement {

    private final OrderStatistics statistics;

    public OrderManagement(OrderStatistics statistics) {
        this.statistics = statistics;
    }

    @ManagedAttribute
    public long getPendingOrders() {
        return statistics.getPending();
    }
}
```

Nhờ vậy mỗi lần JMX đọc attribute chỉ gọi `AtomicLong.get()`, không truy vấn DB.

### Điều cần cân nhắc

- Counter phải được cập nhật **đúng điểm chuyển trạng thái**; nếu một transaction rollback thì không được tính như đã hoàn thành.
- Nếu app có nhiều replica, counter trong JVM chỉ đại diện cho **instance đó**, không tự là tổng toàn cluster.
- Counter có thể lệch sau restart, crash hoặc các thay đổi dữ liệu bên ngoài ứng dụng.
- `onOrderCompleted` không nên khiến count âm khi trạng thái không phù hợp.
- Khi cần số liệu authoritative, có thể dùng quy trình reconcile/snapshot định kỳ ở background thay vì query trên mỗi lần getter.

Counter in-memory là tối ưu cho đọc nhanh, nhưng tính đúng đắn phụ thuộc cách cập nhật. Đừng chuyển một phép đo database thành counter RAM mà không làm rõ semantics.

## 8. Giải pháp 2: snapshot cập nhật theo lịch riêng

Nếu metric cần được tổng hợp từ database hoặc hệ thống ngoài, có thể cập nhật snapshot bằng một tác vụ được quản lý riêng:

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class PendingOrderSnapshot {

    private final OrderRepository repository;
    private final AtomicLong latestValue = new AtomicLong();
    private volatile long refreshedAtEpochMillis;

    public PendingOrderSnapshot(OrderRepository repository) {
        this.repository = repository;
    }

    @Scheduled(fixedDelayString =
            "\${monitoring.pending-refresh-ms:30000}")
    public void refresh() {
        long count = repository.countPendingOrders();
        latestValue.set(count);
        refreshedAtEpochMillis = System.currentTimeMillis();
    }

    public long currentValue() {
        return latestValue.get();
    }

    public long refreshedAtEpochMillis() {
        return refreshedAtEpochMillis;
    }
}
```

Và JMX management bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderSnapshot,name=primary")
public class PendingOrderManagement {

    private final PendingOrderSnapshot snapshot;

    public PendingOrderManagement(PendingOrderSnapshot snapshot) {
        this.snapshot = snapshot;
    }

    @ManagedAttribute
    public long getPendingOrders() {
        return snapshot.currentValue();
    }

    @ManagedAttribute
    public long getLastRefreshEpochMillis() {
        return snapshot.refreshedAtEpochMillis();
    }
}
```

Trong Spring, `@Scheduled` cần scheduling được kích hoạt, chẳng hạn qua `@EnableScheduling` trong cấu hình phù hợp. Khi scheduler chưa chạy, giá trị ban đầu (0 trong ví dụ) **chưa chắc là số liệu thực**. Production nên biểu diễn trạng thái “chưa khởi tạo”, “refresh lỗi” hoặc “snapshot quá cũ” rõ ràng bằng attribute bổ sung.

### Ưu điểm

- Tách tần suất đọc JMX khỏi tần suất query DB.
- Có thể giới hạn số lần truy vấn theo lịch.
- Khi DB chậm, JMX getter vẫn trả snapshot cũ thay vì trực tiếp bị block theo query.
- Có thể quan sát thời điểm refresh để biết dữ liệu mới hay cũ.

### Đánh đổi

- Giá trị có độ trễ; không phải snapshot tức thời từ database.
- Nhiều replica vẫn có thể refresh cùng lúc, tạo tải nền.
- Lỗi refresh phải được ghi nhận, tránh trả số cũ mà không ai biết.
- Cần xem xét transaction/isolation và phương pháp lấy số liệu phù hợp.

Nếu dùng một scheduler chung có nhiều job, truy vấn chậm có thể trì hoãn các job khác. Tách cadence/JMX getters không đồng nghĩa đã giải quyết mọi vấn đề tải nền.

## 9. Thiết kế attribute biểu diễn độ mới dữ liệu

Khi dùng snapshot, hãy công bố ít nhất giá trị và trạng thái cập nhật:

```text
PendingOrders = 125
LastRefreshEpochMillis = 1794391200000
SnapshotHealthy = true
```

Có thể bổ sung:

- `LastRefreshDurationMillis`: thời gian truy vấn lần cuối.
- `RefreshFailures`: số lần refresh lỗi.
- `SnapshotAgeMillis`: độ cũ khi đọc (tính toán nhẹ dựa trên clock).
- `LastErrorCode`: mã ngắn, không chứa dữ liệu nhạy cảm.
- `RefreshInProgress`: trạng thái nếu cần.

Một getter tính `SnapshotAgeMillis` từ `System.currentTimeMillis()` và timestamp đã lưu thường khá rẻ:

```java
@ManagedAttribute
public long getSnapshotAgeMillis() {
    long updatedAt = snapshot.refreshedAtEpochMillis();
    return updatedAt == 0L
            ? -1L
            : Math.max(0L, System.currentTimeMillis() - updatedAt);
}
```

Đây là một phép tính ngắn không tạo truy vấn. `-1` là convention ví dụ cho “chưa có snapshot”; hãy mô tả rõ ý nghĩa cho người vận hành và exporter, vì không phải mọi hệ thống metric thích hợp với giá trị sentinel âm.

## 10. Side effect nguy hiểm: getter thay đổi trạng thái

Ví dụ cần tránh:

```java
@ManagedAttribute
public long getPendingOrders() {
    long count = repository.countPendingOrders();
    repository.markMetricsRead(); // Ghi trạng thái khi chỉ xem.
    return count;
}
```

Hay:

```java
@ManagedAttribute
public int getRetryQueueSize() {
    retryQueue.purgeExpired(); // Có thể xóa item.
    return retryQueue.size();
}
```

Một JMX client chỉ muốn xem số liệu nhưng vô tình kích hoạt thay đổi hệ thống. Nếu monitoring chạy thường xuyên, side effect cũng xảy ra thường xuyên, khó truy vết.

Hãy tách rõ:

- **Getter/attribute:** đọc snapshot hoặc phép tính rẻ, không thực hiện hành động quản trị.
- **Operation:** hành động có chủ đích như `refreshSnapshot()`, `clearCache()`, `resetStatistics()`.

Ví dụ:

```java
@ManagedAttribute
public long getPendingOrders() {
    return snapshot.currentValue();
}

@ManagedOperation
public void refreshSnapshot() {
    snapshot.refresh();
}
```

Operation cũng phải có quyền và giới hạn tải thích hợp; việc công bố nó không tự an toàn. Với operation có thể chạy lâu, nên cân nhắc trả trạng thái job và thực thi bất đồng bộ có kiểm soát thay vì block thread JMX lâu.

## 11. Getter có block thread hoặc deadlock không?

Getter có thể không làm IO nhưng vẫn gây rủi ro nếu chờ lock mà nghiệp vụ đang giữ:

```java
@ManagedAttribute
public int getPendingOrders() {
    synchronized (sharedLock) {
        return expensiveAggregateOverLargeMap();
    }
}
```

Nếu aggregate mất nhiều giây và giữ lock, JMX polling có thể tranh chấp với nghiệp vụ. Ngược lại, nghiệp vụ đang giữ lock lâu khiến JMX reader chờ, và các client có thể timeout.

Các rủi ro cần kiểm tra:

- Lock contention và thời gian giữ khóa.
- Gọi method khác trong lock dẫn đến lock inversion.
- Blocking trên `Future.get()`, `CountDownLatch.await()` hoặc external lock.
- Duyệt collection lớn trong critical section.
- Giá trị mutable mà reader có thể thấy trạng thái chưa đồng bộ.

Giải pháp tùy workload: `AtomicLong`, `LongAdder`, snapshot immutable, read/write lock với thời gian giữ ngắn hoặc cơ chế metric registry. Không cố dùng atomic cho mọi cấu trúc phức tạp nếu cần consistency nhiều field.

### LongAdder hay AtomicLong?

`LongAdder` phù hợp counter cập nhật thường xuyên dưới contention, nhưng `sum()` không phải snapshot atomic tuyệt đối khi nhiều thread vẫn đang cập nhật. `AtomicLong` hỗ trợ đọc/ghi atomic một giá trị long. Chọn dựa trên semantics muốn công bố, không chỉ dựa trên hiệu năng.

## 12. Concurrency và consistency giữa nhiều JMX attributes

Giả sử MBean có:

```text
Queued = 100
Processed = 500
Failed = 20
```

Client có thể đọc từng attribute ở các thời điểm khác nhau. Trong khi đó các worker tiếp tục cập nhật, nên tổng hợp từ các giá trị riêng lẻ có thể không phản ánh cùng một snapshot nhất quán.

Không nên giả định `MBeanServer.getAttributes()` bảo đảm mọi attribute được tính ở cùng một thời điểm nguyên tử. Nếu consumer cần consistency của nhiều field, có thể:

1. Tạo immutable snapshot object được cập nhật đồng thời.
2. Công bố một compound attribute với các field liên quan.
3. Có generation/timestamp để nhận biết cùng snapshot.
4. Nếu tính toán phức tạp, thực hiện cập nhật snapshot ngoài luồng getter.

Ví dụ:

```java
public record QueueSnapshot(
        long queued,
        long processed,
        long failed,
        long updatedAtMillis) {}
```

Getter có thể trả một số trường số đơn giản từ một `volatile QueueSnapshot`. Để công bố record như một JMX attribute trong mọi cơ chế Standard MBean cần cân nhắc mapping type; với MXBean có các quy tắc open-type mapping riêng. Không tự mặc định mọi record Java được JMX serialization/mapping hỗ trợ mà không cấu hình.

## 13. Getter có gọi @Transactional hoặc @Cacheable?

Một getter có annotation `@ManagedAttribute` có thể gọi service được Spring AOP proxy. Nếu service thực hiện database query trong transaction, hành vi thực tế phụ thuộc proxy, transaction propagation và runtime configuration.

Ví dụ:

```java
@ManagedAttribute
public long getPendingOrders() {
    return orderService.countPendingOrders();
}
```

Dù `countPendingOrders()` được gắn `@Transactional(readOnly = true)`, mỗi lần JMX poll vẫn có thể mở transaction và thực hiện SQL. `readOnly=true` là hint hoặc mode transaction tùy stack; nó không bảo đảm getter có chi phí thấp hoặc hoàn toàn không gây hiệu ứng khác.

`@Cacheable` có thể giảm số lần query, nhưng:

- Cache miss vẫn có thể gọi DB.
- Cache expiry gây refresh ở thời điểm polling.
- Nhiều client cùng yêu cầu có thể tạo stampede nếu cache không phối hợp thích hợp.
- Giá trị cache có thể cũ.
- Proxy/self-invocation ảnh hưởng việc advice có thực sự chạy.

Vì vậy `@Transactional(readOnly = true)` hoặc `@Cacheable` không phải một chứng nhận getter “an toàn cho monitoring”.

## 14. Định lượng chi phí đọc getter

Để quyết định một getter có phù hợp với exporter polling, cần biết ít nhất:

- **Latency bình thường**: trung bình, p95, p99.
- **Latency khi dependency chậm**: có timeout rõ không.
- **Tần suất gọi**: số collector × interval × số instance.
- **Tài nguyên tiêu thụ**: SQL queries, CPU, allocations, network, lock wait.
- **Ảnh hưởng nghiệp vụ**: pool connection, thread contention, throughput.
- **Failure behavior**: ném exception, block, trả giá trị cũ hay sentinel.
- **Độ mới dữ liệu**: freshness có đáp ứng nhu cầu vận hành không.

Giả sử một getter mất 200 ms và được gọi 12 lần/phút trong một JVM. Tổng thời gian thực thi cộng dồn gần 2,4 giây/phút nếu các lần gọi diễn ra tuần tự, nhưng không thể từ con số đó tự suy ra CPU utilization hay mức độ nghẽn; getter có thể chủ yếu chờ IO. Nếu cùng các lời gọi chồng lên nhau và dùng chung pool DB với nghiệp vụ, tác động có thể lớn hơn.

Giảm polling interval từ 30 giây xuống 5 giây làm tần suất yêu cầu tăng khoảng sáu lần **trong điều kiện không thay đổi số client và lịch thu thập**. Đây là lý do cần cân nhắc frequency ngay từ thiết kế getter.

## 15. Thử nghiệm side effect bằng unit test

Một test có thể xác định getter không truy cập repository khi chỉ đọc snapshot.

Ví dụ JUnit 5 và Mockito:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class OrderManagementTest {

    @Test
    void getterReadsSnapshotWithoutDatabaseQuery() {
        OrderRepository repository = mock(OrderRepository.class);
        OrderStatistics statistics = new OrderStatistics();
        statistics.onOrderQueued();

        OrderManagement management =
                new OrderManagement(statistics);

        assertEquals(1L, management.getPendingOrders());
        assertEquals(1L, management.getPendingOrders());

        verifyNoInteractions(repository);
    }
}
```

Ví dụ này kiểm tra nguyên tắc: getter đọc `OrderStatistics` mà không gọi repository. Trong code production, nếu repository không thuộc dependency graph của object được test, xác nhận `verifyNoInteractions` trên mock chưa bao giờ được truyền vào hệ thống chỉ có giá trị minh họa. Một test có ý nghĩa hơn là **inject một spy/mock cho dependency thực tế mà getter có thể gọi**, rồi verify không có lời gọi IO; hoặc dùng integration test và SQL statement counter.

### Test side effect thực tế

Với implementation dễ gây side effect:

```java
class BadMonitor {
    private final OrderRepository repository;

    BadMonitor(OrderRepository repository) {
        this.repository = repository;
    }

    long getPendingOrders() {
        return repository.countPendingOrders();
    }
}
```

Test:

```java
@Test
void getterDoesNotQueryDatabase() {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.countPendingOrders()).thenReturn(10L);

    BadMonitor monitor = new BadMonitor(repository);
    monitor.getPendingOrders();

    verify(repository, never()).countPendingOrders();
}
```

Test này **sẽ thất bại có chủ đích**, chứng minh getter đang thực hiện truy vấn và không đáp ứng yêu cầu “không IO trong getter”. Không dùng một test thất bại như tiêu chuẩn cuối cùng; hãy refactor thành getter đọc snapshot rồi chạy lại test với một dependency graph thực tế.

Nếu yêu cầu cho phép query nhưng giới hạn thời gian, có thể dùng integration/performance tests đo số query và latency thay vì khẳng định “zero IO”.

## 16. Kiểm thử qua MBeanServer, không chỉ gọi Java method

Một getter có thể hoạt động khi gọi trực tiếp nhưng có khác biệt về exporter/proxy/metadata. Với Spring JMX, nên kiểm tra qua `MBeanServer`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.shop.orders:type=OrderMonitor,name=primary");

Object value = server.getAttribute(name, "PendingOrders");
System.out.println(value);
```

Đoạn này giả định MBean đã được register vào platform MBeanServer theo ObjectName tương ứng; Spring có thể dùng MBeanServer khác theo cấu hình. Không coi code đó là ví dụ tự hoàn chỉnh nếu không có bước đăng ký/export.

Khi kiểm tra nên thu thập:

1. Count số lần getter được gọi cho một yêu cầu đọc.
2. Số SQL queries, HTTP calls hoặc Redis calls.
3. Latency và exception.
4. Thread/lock contention khi nhiều client đọc đồng thời.
5. Ảnh hưởng tới workload nghiệp vụ khi tăng tần suất.
6. MBeanInfo xác nhận attribute đúng tên và read-only/writeable semantics.

Cần kiểm tra cả khi JConsole/exposer chạy thật, vì công cụ có thể poll nhiều attributes, hoặc nhiều client cùng kết nối hơn dự tính.

## 17. Quan sát getter trong môi trường vận hành

Một strategy thực tế:

- Gắn metric đo thời gian **refresh snapshot** hoặc truy vấn ở background.
- Theo dõi số lần refresh lỗi, tuổi snapshot và thời gian refresh gần nhất.
- Quan sát số SQL query phát ra từ monitoring code path.
- Dùng profiler, Java Flight Recorder hoặc thread dump khi nghi ngờ lock/blocking.
- Kiểm tra tải khi exporter/JConsole kết nối.
- Cấu hình timeout thích hợp cho mọi IO bắt buộc.
- Tránh thêm log ở mức INFO/ERROR trên mỗi getter call bình thường, gây log spam.

Nếu thêm instrumentation vào getter, chính instrumentation cũng cần nhẹ. Một timer/counter trong RAM thường phù hợp; việc ghi log hoặc gửi network request mỗi lần getter được đọc lại có thể tạo vòng lặp quan sát tốn tài nguyên.

## 18. Khi nào nên dùng operation thay cho attribute?

JMX attribute thường được xem như dữ liệu có thể đọc lặp lại. Những hành động sau nên được mô hình hóa thành **operation** nếu thật sự cần công bố:

- `refreshCache()`
- `recalculateStatistics()`
- `reconcileDatabaseCounts()`
- `resetCounters()`
- `purgeExpiredEntries()`
- `reloadConfiguration()`

Ví dụ:

```java
@ManagedOperation(description = "Refresh pending count snapshot")
public void refreshPendingOrders() {
    snapshot.refresh();
}
```

Một operation có thể tốn tài nguyên hoặc thay đổi trạng thái, nên phải được hạn chế quyền, có timeout và logging/auditing thích hợp nếu có ý nghĩa vận hành. **Đừng biến một getter thành operation chỉ để né kiểm tra chất lượng**; hãy chọn API theo semantics của hành vi.

Nếu giá trị cần được tính toán đắt đỏ mỗi khi người vận hành chủ động yêu cầu, có thể công bố operation `calculateCurrentCount()` và ghi rõ chi phí, đồng thời để attribute `CachedCount` trả snapshot rẻ.

## 19. Ví dụ thiết kế quản trị cho cache

Một cache có:

```text
EntryCount
HitCount
MissCount
LastRefreshEpochMillis
RefreshHealthy
```

**Getter phù hợp:**

```java
@ManagedAttribute
public long getHitCount() {
    return hitCounter.sum();
}

@ManagedAttribute
public long getMissCount() {
    return missCounter.sum();
}

@ManagedAttribute
public int getEntryCount() {
    return cacheStatsSnapshot.entryCount();
}
```

**Getter rủi ro:**

```java
@ManagedAttribute
public int getEntryCount() {
    return remoteCache.scanAllKeys().size();
}
```

Nếu mỗi lần đọc phải scan toàn bộ remote cache, hãy đánh giá lại metric semantics và dùng số liệu cache cung cấp sẵn, counter/registry hoặc snapshot background. Một phép `size()` trên distributed cache cũng có thể là operation phân tán đắt đỏ tùy implementation.

## 20. Lưu ý về dữ liệu nhạy cảm và external side effects

Getter JMX có thể bị gọi bởi client được cấp quyền đọc. Đừng để getter trả thông tin bí mật như password, access token, raw customer data hoặc chi tiết cá nhân không cần thiết.

Ngay cả attribute không thay đổi trạng thái cũng có thể tạo tác dụng phụ **ở hệ thống ngoài**:

- Tăng số request tới API có rate limit.
- Phát sinh billing cho từng API call.
- Đụng vào cache remote và làm mới access timestamp.
- Đọc database với lock/isolation gây tranh chấp.
- Khởi tạo kết nối hoặc refresh credentials.
- Ghi audit event theo chính sách hệ thống.

Do đó cần kiểm tra **toàn bộ call graph** của getter, không chỉ ba dòng code trong method được annotate.

Đối với JMX remote, cấu hình xác thực, mã hóa và quyền truy cập ở connector/server riêng. Annotation `@ManagedAttribute` không tự động áp dụng authorization cho mọi client theo role nghiệp vụ.

## 21. Những lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách giải quyết |
|---|---|---|
| Database chậm hơn khi bật JConsole | Getter gọi SQL cho mỗi read | Chuyển sang snapshot, giảm cadence hoặc tối ưu truy vấn |
| Exporter gây timeout | Getter đọc HTTP/DB có latency cao | Giới hạn IO, timeout, background refresh |
| JMX read làm thay đổi cache | Getter có `refresh`, `purge` hoặc lazy initialization | Tách operation khỏi getter |
| Attribute có giá trị cũ | Snapshot không refresh hoặc refresh lỗi | Công bố timestamp/health và cảnh báo freshness |
| Counter khác tổng database | Increment/decrement sai transition hoặc restart | Reconcile định kỳ, mô tả semantics per JVM |
| Dashboard thiếu metric khi dependency lỗi | Getter ném exception từ source ngoài | Trả snapshot cũ với trạng thái stale, quan sát refresh lỗi |
| Thread bị block bởi monitoring | Getter giữ lock hoặc chờ future | Giảm critical section, dùng atomic/snapshot |
| Số query tăng bất thường | Nhiều exporter/collector cùng poll | Quan sát request frequency và cấu hình collector |
| Transaction advice không có hiệu lực | Self-invocation hoặc gọi target bỏ qua proxy | Giữ boundary qua Spring proxy, kiểm tra AOP |
| Có attribute nhưng gọi lỗi | Export metadata đúng nhưng getter runtime ném exception | Kiểm tra logs/stack trace và MBeanServer call |

## 22. Bài tập thực hành

### Bài tập 1 — Phân loại getter

Xét:

```java
@ManagedAttribute
public long getProcessedCount() {
    return processedCounter.sum();
}

@ManagedAttribute
public long getFailedCount() {
    return repository.countFailedOrders();
}

@ManagedAttribute
public long getCacheSize() {
    cache.removeExpiredEntries();
    return cache.size();
}
```

Hãy phân loại:

1. Đọc counter RAM với chi phí nhỏ.
2. Gây database query mỗi lần JMX poll.
3. Có side effect xóa cache entries.

Đề xuất cách thay method (2), (3) bằng snapshot hoặc operation.

### Bài tập 2 — Ước lượng tải polling

Giả sử một getter gọi SQL và mỗi JVM được poll bởi 3 collectors, mỗi collector 10 giây/lần. Với 12 JVM, tổng số lần getter được gọi mỗi phút là bao nhiêu, giả định không có cache và các collectors độc lập?

```text
3 collectors × 6 lần/phút × 12 JVM = 216 lần/phút
```

Kết quả chỉ là số lần gọi theo giả định; thời gian CPU, query execution và overlap cần đo riêng.

### Bài tập 3 — Thiết kế snapshot có freshness

Thiết kế `PendingOrderSnapshot` với các fields:

```text
pendingOrders
lastRefreshEpochMillis
lastRefreshDurationMillis
refreshFailures
snapshotHealthy
```

Tạo job refresh theo lịch, rồi chỉ cho các JMX getters đọc trường đã lưu. Thử mô phỏng database timeout và xác định dashboard cần hiển thị dấu hiệu gì để không coi số cũ là số mới.

### Bài tập 4 — Kiểm tra gọi lại nhiều lần

Dùng Mockito spy hoặc mock một service được management bean sử dụng. Gọi `server.getAttribute(name, "PendingOrders")` hai lần và xác minh không có lời gọi repository. Nếu implementation hiện tại dùng DB trực tiếp, test phải phát hiện được truy vấn ấy.

### Bài tập 5 — Side effect từ lazy loading

Một getter gọi `entity.getItems().size()` trên JPA entity. Hãy giải thích khi nào điều này kích hoạt lazy loading và SQL, khi nào có thể ném `LazyInitializationException`, và vì sao JMX poll không nên phụ thuộc một persistence context chưa chắc còn sống.

## 23. Câu hỏi tự kiểm tra

**1. JMX attribute “read-only” có bảo đảm getter không ghi dữ liệu không?**

Không. Read-only chỉ mô tả metadata setter của attribute, không chứng minh implementation không có side effect.

**2. `@Transactional(readOnly=true)` có bảo đảm getter không gây tải DB không?**

Không. Nó có thể vẫn mở transaction và chạy SQL mỗi lần client đọc.

**3. Vì sao một getter có vẻ nhanh khi gọi thủ công vẫn có thể gây tải production?**

Do nhiều clients, tần suất polling, số replicas, contention và tình trạng dependency thay đổi.

**4. Cần làm gì khi giá trị cần được lấy từ DB nhưng query đắt đỏ?**

Thường nên refresh snapshot theo lịch có kiểm soát, hoặc dùng cơ chế metrics/counter phù hợp, rồi getter chỉ đọc giá trị đã lưu và công bố freshness.

**5. Getter `getPendingCount()` có thể reset counter khi đọc không?**

Không nên nếu client kỳ vọng attribute là phép đọc lặp lại. Hành vi reset nên là operation tường minh được bảo vệ.

**6. Có thể chỉ dựa vào tên method `getXxx()` để xác định không có IO không?**

Không. Phải xem implementation và các dependency/call graph.

**7. Nếu hai JMX attributes được đọc cùng lúc qua `getAttributes()`, chúng có chắc đại diện cùng snapshot nguyên tử không?**

Không có bảo đảm tổng quát như vậy; cần tự thiết kế consistency nếu consumer yêu cầu.

## 24. Ghi nhớ

- JMX getter là **code có thể được thực thi lặp lại bởi client bên ngoài** khi gọi `getAttribute`; không phải một field tự động được cache.
- `@ManagedAttribute` không bảo đảm method không có side effect, không IO hoặc không block.
- Getter tốt thường trả **snapshot/counter in-memory** hoặc thực hiện phép tính ngắn, có giới hạn chi phí.
- Nếu cần truy vấn nặng, hãy tách thành refresh background có cadence, timeout, trạng thái lỗi và timestamp độ mới.
- Tác vụ ghi/xóa/reset/refresh có chủ đích nên được biểu diễn bằng **JMX operation** có kiểm soát.
- Đo latency, số query, lock contention và tác động khi nhiều client poll; đừng chỉ suy luận từ code.
- Kiểm tra cả đường JMX thực tế qua MBeanServer và exporter, không chỉ method unit test.
- Phân biệt độ chính xác của số liệu với chi phí đọc: snapshot có thể cũ, counter JVM có thể lệch nếu update logic không đúng.
- Không cho getter vô tình tiết lộ dữ liệu nhạy cảm hoặc gọi API ngoài với tác động tính phí/rate limit.

## 25. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `ManagedAttribute`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Java SE 21 — `MBeanServer.getAttribute`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Micrometer Reference: https://docs.micrometer.io/micrometer/reference/
- Spring Framework Reference — Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
