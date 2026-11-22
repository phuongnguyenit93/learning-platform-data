# 6.9. Memory threshold notification và cách tránh xử lý nặng ngay trong callback

Khi một ứng dụng Java bị áp lực bộ nhớ, đợi đến lúc `OutOfMemoryError` mới phản ứng thường là quá muộn. JVM cung cấp **MemoryPoolMXBean** để theo dõi từng memory pool, đặt ngưỡng sử dụng, và **MemoryMXBean** để phát thông báo JMX khi điều kiện ngưỡng được phát hiện. Cơ chế này hữu ích cho việc **giảm nhận thêm tải, kiểm tra xu hướng memory, báo động và chuyển việc điều phối sang thành phần khác**.

Tuy nhiên, callback `NotificationListener.handleNotification(...)` **không phải nơi chạy heap dump, full GC, truy vấn dữ liệu, network call hoặc phân tích nặng**. Callback có thể được thực thi trong cơ chế phân phối notification của JVM; nếu bị chặn hay tạo thêm nhiều object khi memory đang căng, nó có thể làm trễ các thông báo khác, tăng áp lực bộ nhớ và khiến sự cố nặng hơn.

Bài học thuộc **6. MXBeans** và tập trung vào:

1. Phân biệt **usage threshold** với **collection usage threshold**.
2. Xác định memory pool nào thực sự hỗ trợ threshold, chọn ngưỡng và giải nghĩa `MemoryUsage`.
3. Đăng ký listener trên `MemoryMXBean`, đọc `MemoryNotificationInfo` đúng kiểu.
4. Thiết kế **callback cực ngắn → bounded queue / signal → worker riêng**.
5. Ngăn xử lý trùng, queue tràn, logging storm và phản ứng gây quá tải khi JVM thiếu memory.
6. Thực hành Java 17+ cùng các giới hạn, cách kiểm thử và checklist production.

## 1. Mô hình: MemoryPoolMXBean đặt ngưỡng, MemoryMXBean phát notification

Một JVM có các vùng memory khác nhau: **heap** (chứa object Java) và **non-heap** (ví dụ metaspace, code cache), mỗi vùng có thể được JVM biểu diễn bằng một hoặc nhiều **memory pools**. Danh sách tên và mức hỗ trợ phụ thuộc collector, vendor và version; không hard-code rằng mọi JVM đều có pool tên `G1 Old Gen`, `PS Old Gen` hay `Tenured Gen`.

Hai API giữ vai trò khác nhau:

| Thành phần | Vai trò | API quan trọng |
| --- | --- | --- |
| `ManagementFactory.getMemoryPoolMXBeans()` | Tìm memory pools trong JVM hiện tại | Trả danh sách `MemoryPoolMXBean` |
| `MemoryPoolMXBean` | Đọc usage và đặt threshold **trên từng pool** | `getUsage()`, `getCollectionUsage()`, `isUsageThresholdSupported()`, `setUsageThreshold(long)`, `isCollectionUsageThresholdSupported()`, `setCollectionUsageThreshold(long)` |
| `ManagementFactory.getMemoryMXBean()` | Lấy MXBean biểu diễn heap/non-heap tổng thể, đồng thời phát memory notifications | `getHeapMemoryUsage()`, `getNonHeapMemoryUsage()` |
| `NotificationEmitter` | Đăng ký/hủy JMX listener | `addNotificationListener(...)`, `removeNotificationListener(...)` |
| `MemoryNotificationInfo` | Giải nghĩa dữ liệu kèm notification | `from(CompositeData)`, `getPoolName()`, `getUsage()`, `getCount()` |

Luồng cơ bản:

~~~text
JVM theo dõi từng MemoryPoolMXBean
        |
        | điều kiện usage/collection threshold được phát hiện
        v
MemoryMXBean phát JMX Notification
        |
        v
NotificationListener.handleNotification(...)
        |
        | kiểm tra type, cố gắng enqueue một tín hiệu rất nhỏ
        v
Bounded queue / atomic flag
        |
        v
Worker riêng đọc MXBeans/metrics, đối chiếu trend,
rate-limit cảnh báo hoặc đề xuất giảm nhận tải
~~~

**Điểm dễ nhầm:** chúng ta **đặt ngưỡng trên MemoryPoolMXBean**, nhưng **đăng ký listener ở MemoryMXBean**, không gắn listener trực tiếp vào một `MemoryPoolMXBean` như thể mỗi pool là emitter độc lập. Vì `MemoryMXBean` phát notification liên quan nhiều pools, worker phải đọc `poolName` để phân biệt.

## 2. MemoryUsage: biết mình đang so sánh cái gì

`MemoryUsage` mang bốn số `init`, `used`, `committed` và `max`, đơn vị **bytes**:

- `init`: bộ nhớ ban đầu JVM yêu cầu cho pool; có thể không xác định.
- `used`: ước lượng số bytes hiện dùng trong pool; có thể gồm object chưa được thu gom nếu đó là pool có GC.
- `committed`: lượng memory hiện được đảm bảo sẵn cho JVM sử dụng; không nhất thiết bằng `used`.
- `max`: mức tối đa có thể dùng cho pool **nếu JVM biết**, thường là `-1` khi không xác định.

Ví dụ minh họa:

~~~text
pool=example-old
init=0
used=314572800
committed=402653184
max=536870912
~~~

Ví dụ trên biểu thị `used` khoảng 300 MiB, `committed` 384 MiB, `max` 512 MiB. Đây là số giả lập, **không phải kết quả từ một JVM cụ thể**.

**Không trộn đơn vị:**
- Ngưỡng `setUsageThreshold(long)` và `setCollectionUsageThreshold(long)` là **bytes**, không phải MiB hoặc phần trăm.
- Đổi 1 MiB thành bytes bằng `1024 × 1024`. Ví dụ `384L * 1024 * 1024` bằng 402.653.184 bytes.
- Nếu `getMax() == -1`, **không thể** tính “80% max” bằng phép nhân trực tiếp; phải có chính sách dựa trên thông số khác hoặc không đặt ngưỡng kiểu phần trăm.
- `used` của pool/heap **không phải RSS của process hoặc cgroup memory usage**; JVM còn dùng native buffers, thread stacks, metaspace, code cache và các vùng khác.

`getUsage()` là ảnh chụp *ước lượng* ở thời điểm gọi. Một số pool có thể tốn chi phí để tính usage, và pool có thể trở nên không còn hợp lệ (khi đó `getUsage()` có thể trả `null`). Không đọc liên tục ở tần suất cao trong callback hoặc coi dữ liệu là đo tức thì không độ trễ.

## 3. Hai loại threshold phải phân biệt

### 3.1. Usage threshold — mức sử dụng pool đạt/vượt ngưỡng

Để bật theo dõi usage threshold cho **một pool hỗ trợ**, dùng:

~~~java
if (pool.isUsageThresholdSupported()) {
    pool.setUsageThreshold(thresholdBytes);
}
~~~

Đây là **đoạn API minh họa**, giả định `pool` và `thresholdBytes` đã được định nghĩa và kiểm tra. Một số pool không hỗ trợ, đặc biệt pool trẻ (young generation) có tỷ lệ cấp phát cao: JVM có thể không muốn kiểm tra ngưỡng trên từng allocation do overhead.

Khi JVM phát hiện usage của pool **tăng tới hoặc vượt** threshold, `MemoryMXBean` có thể phát notification loại:

`MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED`

Điều cần hiểu:
- Để tiếp tục phát notification cho lần vượt ngưỡng **mới**, usage phải **giảm xuống dưới** ngưỡng trước rồi mới tăng qua lại.
- JVM kiểm tra ở **thời điểm phù hợp nhất**, thường có liên quan GC; không cam kết callback đến ngay đúng microsecond vượt ngưỡng.
- `getUsageThresholdCount()` là số lần JVM phát hiện vượt ngưỡng; `MemoryNotificationInfo.getCount()` chứa count tại lúc notification được tạo.
- Không thấy thông báo **không chứng minh** heap chưa từng vượt ranh giới trong khoảng quan sát ngắn.
- Đặt ngưỡng **0** tắt usage threshold monitoring cho pool đó; giá trị dương bật kiểm tra. Phải kiểm tra pool có hỗ trợ trước khi đọc/đặt.

Đây là cơ chế phát hiện **tình trạng sử dụng tăng cao**, không phải báo trước chắc chắn về OOM.

### 3.2. Collection usage threshold — mức còn lại sau GC

Với pool có `isCollectionUsageThresholdSupported() == true`, có thể thiết lập:

~~~java
if (pool.isCollectionUsageThresholdSupported()) {
    pool.setCollectionUsageThreshold(thresholdBytes);
}
~~~

Đây cũng là **minh họa API**, không phải chương trình độc lập. Loại notification:

`MemoryNotificationInfo.MEMORY_COLLECTION_THRESHOLD_EXCEEDED`

Ngữ nghĩa khác usage threshold:
- JVM kiểm tra mức sử dụng **sau khi đã cố gắng thu hồi objects** trong collection cycle phù hợp.
- Khi lượng memory sau thu gom **lớn hơn hoặc bằng** ngưỡng, JVM có thể phát collection threshold notification.
- Nó hữu ích để quan sát **live/retained heap pressure sau GC** thay vì chỉ một lần tăng tạm thời trước GC, nhưng **không tự chứng minh memory leak**: cache cố ý giữ, burst workload, fragmentation hoặc hiệu ứng collector cũng có thể làm retained usage cao.
- Có thể phát tại những lần GC phù hợp khi tình trạng usage sau collection vẫn cao; không áp dụng máy móc quy tắc rearm giống usage threshold.
- `getCollectionUsageThresholdCount()` và `getCollectionUsage()` là dữ liệu tương ứng. `getCollectionUsage()` có thể `null` nếu pool không hợp lệ hoặc chưa có thông tin phù hợp; luôn kiểm tra.

### 3.3. Bảng so sánh

| Tiêu chí | Usage threshold | Collection usage threshold |
| --- | --- | --- |
| Kiểm tra support | `isUsageThresholdSupported()` | `isCollectionUsageThresholdSupported()` |
| Đặt ngưỡng | `setUsageThreshold(bytes)` | `setCollectionUsageThreshold(bytes)` |
| Giá trị liên quan | `getUsage().getUsed()` | `getCollectionUsage().getUsed()` sau GC phù hợp |
| Loại notification | `MEMORY_THRESHOLD_EXCEEDED` | `MEMORY_COLLECTION_THRESHOLD_EXCEEDED` |
| Count | `getUsageThresholdCount()` | `getCollectionUsageThresholdCount()` |
| Ý nghĩa chính | Pool sử dụng cao/tăng qua ngưỡng | Pool vẫn cao sau nỗ lực thu gom |
| Giới hạn | Không phát mỗi lần allocation; phụ thuộc thời điểm JVM kiểm tra | Chỉ có ở pool hỗ trợ; phụ thuộc hoạt động GC |
| Cách tắt | Đặt threshold về 0 | Đặt threshold về 0 |

Không có điều kiện nào trong hai loại trên đồng nghĩa “hãy gọi `System.gc()` ngay”, “cần heap dump ngay” hoặc “JVM chắc chắn sắp chết”. Đó chỉ là **tín hiệu** để cân nhắc quan sát và điều phối.

## 4. Chọn pool và threshold có cơ sở

### 4.1. Luôn hỏi JVM hỗ trợ gì

Một chương trình có thể xem mỗi pool:

~~~java
for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
    System.out.printf(
            "%s type=%s valid=%s usageSupported=%s collectionSupported=%s%n",
            pool.getName(),
            pool.getType(),
            pool.isValid(),
            pool.isUsageThresholdSupported(),
            pool.isCollectionUsageThresholdSupported()
    );
}
~~~

Đoạn này dùng các classes trong `java.lang.management`; đây là **minh họa trong một method có imports**, không phải file Java đầy đủ. Tên pool, loại collector và support thay đổi theo runtime. Trong Java 17, đừng giả định tên G1/Parallel/ZGC/Shenandoah giống nhau hoặc mọi pool non-heap có threshold.

### 4.2. Chọn ngưỡng theo hành vi thực tế

Không có con số “80% heap” đúng cho mọi ứng dụng. Cần xét:
- Heap và pool type thực tế, `getMax()` có xác định không.
- Baseline usage và mức biến động giữa các GC.
- GC collector, allocation rate, peak và memory headroom.
- Tần suất thông báo, thời gian hồi phục, quy mô queue/caches và hoạt động nghiệp vụ khi giảm nhận tải.
- Container memory limit và các vùng memory **ngoài Java heap**.

Một cách khởi đầu ở môi trường thử nghiệm: chọn usage threshold theo một tỷ lệ phù hợp trên `max` của **pool thực sự hỗ trợ**; nếu ngưỡng quá thấp, sẽ nhiều sự kiện/false positives; quá cao, notification có thể đến trễ để phục vụ cân bằng tải. Điều chỉnh theo tỷ lệ lỗi, GC pressure và latency, không chọn bằng trực giác.

**Quy tắc API:**
- `setUsageThreshold(long)` và `setCollectionUsageThreshold(long)` nhận byte count **không âm**.
- Nếu pool có max xác định và threshold **lớn hơn max**, lời gọi có thể ném `IllegalArgumentException`; nếu không hỗ trợ có thể ném `UnsupportedOperationException`.
- Có thể có kiểm soát quyền management của runtime; việc đặt threshold là **thay đổi trạng thái theo dõi toàn JVM**, không chỉ riêng code đang gọi.
- Nếu nhiều thành phần cùng đặt threshold trên một pool, component này có thể **ghi đè** component khác; cần cấu hình/ownership tập trung. Phục hồi threshold cũ khi kết thúc ví dụ chỉ an toàn nếu người chạy là chủ cấu hình đó.

### 4.3. Hysteresis để tránh flapping

Nếu worker phản ứng bằng cách tạm dừng nhận thêm tải ở high watermark, không nên tự động mở lại ngay tại đúng mốc đó. Mô hình:

~~~text
used >= HIGH_WATERMARK --> chuyển sang chế độ giảm nhận tải
used <= LOW_WATERMARK  --> sau N lần đo ổn định mới phục hồi
LOW_WATERMARK < HIGH_WATERMARK
~~~

Notification là tín hiệu đưa worker vào luồng kiểm tra; việc **khi nào phục hồi** nên dùng polling có cadence phù hợp, trend GC/heap và hysteresis, không chỉ đợi notification mới. Khi shutdown/GC khác biệt, response phải có timeout và không bắn vô hạn một lần cho mỗi event.

## 5. Đăng ký JMX NotificationListener chính xác

`ManagementFactory.getMemoryMXBean()` trả `MemoryMXBean` có hỗ trợ `NotificationEmitter` trong JVM chuẩn của JDK 17. Đăng ký một listener:

~~~java
NotificationEmitter emitter =
        (NotificationEmitter) ManagementFactory.getMemoryMXBean();

NotificationListener listener = (notification, handback) -> {
    // Chỉ kiểm tra type và bàn giao nhanh cho worker.
};

emitter.addNotificationListener(listener, null, null);
~~~

Đây là **đoạn minh họa API**, cần imports `javax.management.NotificationEmitter` và `javax.management.NotificationListener`. Khi không dùng nữa:

~~~java
emitter.removeNotificationListener(listener);
~~~

Quan trọng:
- **Không đăng ký listener lặp mỗi request**; đăng ký theo vòng đời service/component và hủy đúng lúc shutdown.
- Với listener nhận cả hai loại notification, lọc bằng `notification.getType()` rồi **trong worker** giải mã `(CompositeData) notification.getUserData()` và `MemoryNotificationInfo.from(...)`.
- `getPoolName()` xác định pool phát tín hiệu; `getUsage()` là snapshot ở lúc notification được tạo; `getCount()` là count của loại threshold liên quan.
- Callback có thể bị gọi **đồng thời**; state chia sẻ cần atomic/thread-safe.
- Notification có thể đến trễ; thứ tự và thời điểm không thay thế timeline/metrics được lấy mẫu riêng.
- `MemoryMXBean`/`MemoryPoolMXBean` là cơ chế quản lý memory của JVM; **không phải event bus nghiệp vụ**, không đảm bảo exactly-once end-to-end, không thay thế heap monitoring ngoài ứng dụng.

### Cẩn thận với JMX userData

Dữ liệu phụ trợ của memory notification được biểu diễn bằng `javax.management.openmbean.CompositeData`. Mẫu giải nghĩa **trên worker**:

~~~java
if (notification.getUserData() instanceof CompositeData data) {
    MemoryNotificationInfo info = MemoryNotificationInfo.from(data);
    if (info != null) {
        String poolName = info.getPoolName();
        long usedBytes = info.getUsage().getUsed();
        long count = info.getCount();
        // Ghi metric hoặc quyết định trên worker; không trong callback.
    }
}
~~~

Nếu nhận notification không đúng type, userData bất thường hoặc pool đã bị xóa, không suy đoán/cast mù quáng. Cần lọc type trước; ví dụ đầy đủ ở mục 7 làm việc đó.

## 6. Vì sao tuyệt đối tránh xử lý nặng trong callback?

Oracle JDK 17 nêu rõ `handleNotification` nên làm **rất ít việc** và trả về không chậm trễ; listener còn có thể được gọi từ nhiều thread. Khi JVM đang thiếu headroom, callback làm việc nặng tạo ra hai kiểu rủi ro:

### 6.1. Làm chậm cơ chế phân phối thông báo

Những thao tác dễ gây block:
- `Thread.sleep(...)`, `BlockingQueue.put(...)` hoặc `Future.get()` trong callback.
- HTTP/DB request, gửi email, gọi cloud APIs hay dịch vụ chat cảnh báo.
- Đọc file/network, đồng bộ I/O, flush logger có appender chậm.
- Acquire lock có thể do thread nghiệp vụ đang giữ; dẫn đến lock inversion hoặc kéo dài contention.
- Chạy `GC.heap_dump` / `HotSpotDiagnosticMXBean.dumpHeap(...)` hoặc gọi explicit GC.
- Quét mọi object, serialize stack trace lớn, heap histogram, truy vấn hàng loạt MXBeans.

Callback bị chặn khiến các notifications khác có thể bị trì hoãn. Vì cơ chế phân phối tùy JVM/transport, không nên dựa vào một thứ tự gọi cố định hoặc một thread duy nhất.

### 6.2. Tăng áp lực bộ nhớ ngay lúc cần tiết kiệm

Khi memory cao:
- Tạo hàng nghìn object cảnh báo, payload JSON lớn hoặc string stack trace có thể làm tăng allocation/GC.
- Gọi `Executors.newSingleThreadExecutor()` hoặc tạo `new Thread` **mỗi lần notification** tạo thêm thread và stack.
- Gửi notification sang **unbounded queue** có thể tích lũy vô hạn nếu worker không theo kịp.
- Tạo heap dump trực tiếp tốn I/O/disk và có thể gây pause; chưa chắc đủ tài nguyên hoặc cần thiết.
- Log ERROR với full environment/payload ở callback có thể gây log storm hoặc lộ bí mật.

Thiết kế khuyến nghị: **callback chỉ lọc type và thử `offer` vào queue cố định, tăng counter nếu queue đầy, rồi return**. Nếu cần thay đổi admission control ngay, có thể đặt một `AtomicBoolean`/`volatile` đơn giản không blocking và giao logic ra quyết định cho worker có timeout/giới hạn.

### 6.3. Một callback “nhẹ” được hiểu thế nào?

~~~java
NotificationListener listener = (notification, handback) -> {
    if (MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED
            .equals(notification.getType())) {
        if (!events.offer(notification)) {
            dropped.incrementAndGet();
        }
    }
};
~~~

**Đoạn minh họa**, giả định `events` là `ArrayBlockingQueue<Notification>` đã tạo sẵn và `dropped` là `AtomicLong`. `offer` không chờ queue trống; không gọi `put` (có thể block). Worker riêng sẽ parse `CompositeData`, ghi metric và thực hiện hành động vận hành. Notification object đã được JVM tạo trước callback; queue chỉ giữ một reference có giới hạn.

**Lưu ý:** không tạo `ArrayBlockingQueue` ở *trong* callback. Tạo queue và worker **một lần** ở lúc khởi tạo, có giới hạn capacity, metrics cho drop/coalesce, graceful shutdown; các hành động nặng phải có giới hạn tần suất.

## 7. Ví dụ hoàn chỉnh Java 17+: listener nhẹ, bounded queue, worker riêng

Mẫu này **chạy độc lập chỉ với JDK 17+**, không cần SLF4J hoặc thư viện ngoài. Nó:

1. Tìm **pool HEAP có hỗ trợ usage threshold** và `max` xác định.
2. Lưu threshold cũ để phục hồi khi kết thúc **trong bối cảnh thử nghiệm chỉ có một chủ sở hữu**.
3. Đăng ký listener lên `MemoryMXBean`; callback chỉ lọc type, `offer` vào queue 32 phần tử, tăng counter nếu đầy.
4. Worker đọc `MemoryNotificationInfo` và lọc `poolName`, xuất một bản ghi tóm tắt. Việc ghi ra console nằm **ngoài callback**.
5. Theo dõi tối đa 15 giây, không cấp phát ép heap, không gọi `System.gc()` hay heap dump. Notification có thể **không phát sinh** nếu không vượt ngưỡng trong thời gian này.

Lưu thành **MemoryThresholdWatch.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryNotificationInfo;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationEmitter;
import javax.management.NotificationListener;
import javax.management.openmbean.CompositeData;

public final class MemoryThresholdWatch {
    private static final BlockingQueue<Notification> EVENTS =
            new ArrayBlockingQueue<>(32);
    private static final AtomicLong DROPPED = new AtomicLong();

    public static void main(String[] args) throws Exception {
        MemoryPoolMXBean selected = null;
        long selectedMax = -1L;

        for (MemoryPoolMXBean candidate :
                ManagementFactory.getMemoryPoolMXBeans()) {
            if (candidate.getType() != MemoryType.HEAP
                    || !candidate.isUsageThresholdSupported()
                    || !candidate.isValid()) {
                continue;
            }
            MemoryUsage usage = candidate.getUsage();
            if (usage != null && usage.getMax() > 0) {
                selected = candidate;
                selectedMax = usage.getMax();
                break;
            }
        }

        if (selected == null) {
            System.out.println("No supported heap usage-threshold pool.");
            return;
        }

        final MemoryPoolMXBean pool = selected;
        final String poolName = pool.getName();
        long oldThreshold = pool.getUsageThreshold();

        // About 80% of the selected pool max; only a DEMO value.
        // max - max/5 avoids overflow from max * 80 / 100.
        long demoThreshold = Math.max(1L,
                selectedMax - selectedMax / 5L);

        NotificationEmitter emitter =
                (NotificationEmitter) ManagementFactory.getMemoryMXBean();

        NotificationListener listener = (notification, handback) -> {
            if (!MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED
                    .equals(notification.getType())) {
                return;
            }
            if (!EVENTS.offer(notification)) {
                DROPPED.incrementAndGet();
            }
        };

        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Notification n = EVENTS.poll(
                            500L, TimeUnit.MILLISECONDS);
                    if (n == null
                            || !(n.getUserData() instanceof CompositeData data)) {
                        continue;
                    }
                    MemoryNotificationInfo info =
                            MemoryNotificationInfo.from(data);
                    if (info == null
                            || !poolName.equals(info.getPoolName())) {
                        continue;
                    }

                    // Parsing and output happen OUTSIDE the callback.
                    System.out.printf(
                            "memory.signal pool=%s usedBytes=%d count=%d%n",
                            info.getPoolName(),
                            info.getUsage().getUsed(),
                            info.getCount());
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } catch (RuntimeException ex) {
                    System.err.println(
                            "Cannot process memory signal: "
                            + ex.getClass().getSimpleName());
                }
            }
        }, "memory-monitor-worker");
        worker.setDaemon(true);

        emitter.addNotificationListener(listener, null, null);
        boolean started = false;
        boolean changedThreshold = false;
        try {
            pool.setUsageThreshold(demoThreshold);
            changedThreshold = true;
            worker.start();
            started = true;

            System.out.println("Monitoring pool: " + poolName);
            System.out.println("Threshold bytes: " + demoThreshold);
            Thread.sleep(15_000L);
        } finally {
            try {
                if (changedThreshold) {
                    pool.setUsageThreshold(oldThreshold);
                }
            } finally {
                emitter.removeNotificationListener(listener);
                if (started) {
                    worker.interrupt();
                    worker.join(1_000L);
                }
                System.out.println(
                        "Dropped queue events: " + DROPPED.get());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MemoryThresholdWatch.java
java MemoryThresholdWatch
~~~

**Output sẽ phụ thuộc JVM và memory pressure; không có stdout cố định**. Ví dụ một lần chạy *có thể* chỉ in:

~~~text
Monitoring pool: G1 Old Gen
Threshold bytes: 3435973836
Dropped queue events: 0
~~~

Đây là **output minh họa**, không phải dự đoán tên pool hoặc số bytes trên máy người học. Nếu JVM không có pool phù hợp, chương trình in đúng một dòng:

~~~text
No supported heap usage-threshold pool.
~~~

Nếu JVM phát hiện vượt ngưỡng trong khoảng chạy, worker có thể in thêm một hoặc nhiều dòng `memory.signal ...`. Nếu không xảy ra, **không phải lỗi**: chương trình chủ ý không làm căng heap. Thời gian ngủ được tính gần đúng; một process có thể bị stop/interrupted hoặc chịu lịch của OS.

**Các giới hạn cố ý của ví dụ:**
- Nó đăng ký đúng **usage** threshold (không phải collection threshold) và chọn một heap pool; các pool khác vẫn có thể phát notifications nếu thành phần khác đã đặt ngưỡng. Worker lọc `poolName`.
- Việc chọn pool/80% chỉ để minh họa; trên production phải cấu hình/đánh giá dựa trên collector, workload và limits thực.
- Dữ liệu notification được giữ trong queue hữu hạn, còn worker xử lý bên ngoài callback. Queue đầy thì tăng drop counter, không block caller.
- Khi shutdown, worker bị interrupt; các notifications còn trong queue có thể chưa xử lý. Production cần shutdown lifecycle/flush theo yêu cầu và không xem queue in-memory là durable.
- Nếu nhiều subsystem cùng quản lý threshold, không được tự ý đặt hoặc phục hồi giá trị cũ như bài demo; phải có **single owner** hoặc coordination.
- `MemoryNotificationInfo.from(...)` dùng CompositeData của notification; không giả định mọi JMX notification có cùng `userData`.
- Ghi `System.out` trên worker vẫn có thể block nếu stdout pipe bị nghẽn; điều quan trọng là **không làm điều đó trong listener**. Nếu worker tắc, queue được giới hạn và có drop metric.

### 7.1. Lưu ý nhỏ về tính runnable và thread-safety

- Java 17 hỗ trợ pattern matching `instanceof CompositeData data` và text block/record; chương trình chỉ sử dụng `instanceof` pattern và các APIs ổn định.
- `ArrayBlockingQueue` là thread-safe; `offer` không block; `AtomicLong` bảo vệ counter khi listener được gọi đồng thời.
- `NotificationEmitter.addNotificationListener(...)` và `removeNotificationListener(...)` dùng cùng instance `listener`.
- Trong `finally`, threshold được phục hồi rồi listener được hủy; cleanup cần đảm bảo cả trường hợp worker chưa kịp start.
- Đoạn mã này là **demo quan sát** chứ không có logic quyết định business load shedding. Không có giả định JVM sẽ phát chính xác một notification và không có synthetic allocation gây OOM.

## 8. Thiết kế production: tín hiệu nhỏ, worker có giới hạn, phản ứng an toàn

### 8.1. Bounded handoff và phản ứng khi queue đầy

| Cách bàn giao | Lợi ích | Rủi ro cần biết |
| --- | --- | --- |
| `ArrayBlockingQueue.offer(signal)` | Không đợi, capacity rõ ràng | Có thể drop nếu queue full; cần metric |
| `AtomicBoolean.compareAndSet(false, true)` | Gộp nhiều notifications thành một trạng thái `pending` | Bỏ chi tiết từng event; worker phải reset đúng lúc |
| `BlockingQueue.put(signal)` | Có thể giữ mọi event trong ngắn hạn | **Block listener** khi queue đầy: không phù hợp trong callback |
| `ExecutorService.submit(...)` mỗi notification | Tách thực thi khỏi caller | Có thể tạo nhiều task, queue unbounded; overload và allocation |
| Tạo `new Thread(...)` mỗi notification | Dễ viết mẫu sơ sài | Thread explosion, memory/stack/CPU overhead; không dùng |

Nếu mục tiêu là **“pool đang cao, cần kiểm tra trạng thái và admission”**, thường không cần xử lý từng notification như một giao dịch. Có thể **coalesce**: nhiều events trong lúc worker đang chạy chỉ khiến trạng thái `needsCheck=true`, worker đọc latest usage và quyết định một lần. Nếu mục tiêu audit tất cả lần crossing, MXBean notification không phải delivery pipeline được bảo đảm; cần số đếm threshold + metrics, và kênh sự kiện bền vững nếu có yêu cầu bắt buộc.

### 8.2. Gợi ý coalescing với AtomicBoolean

Ví dụ **minh họa API**, không phải chương trình chạy độc lập; giả sử đã có worker duy nhất chờ đánh thức bằng một queue có capacity 1:

~~~java
if (pending.compareAndSet(false, true)) {
    if (!queue.offer(SIGNAL)) {
        dropped.incrementAndGet();
        pending.set(false);
    }
}
~~~

Worker xử lý tín hiệu rồi cập nhật `pending` trong `finally`. Cần thiết kế thêm cơ chế không mất wakeup nếu có notification mới trong lúc worker đang xử lý; một cách là giữ `dirty` flag hoặc đọc lại latest usage trước khi clear và kiểm tra chênh lệch count. Không đơn giản hóa thành “set pending=false là đủ” mà chưa xét race. Với nhu cầu quan sát trạng thái thay vì đếm từng event, polling có điều kiện trên worker thường dễ kiểm chứng hơn.

### 8.3. Worker nên làm gì?

Tùy mục tiêu:
1. Đọc lại usage/collection usage và các metrics đã được thu từ nguồn tin cậy, không chỉ dựa vào snapshot trong notification.
2. So xu hướng `used/committed/max`, số lần threshold crossing, GC activity, allocation rate, pool growth và container/cgroup memory.
3. Kiểm tra **hysteresis, cooldown, debounce** để không cảnh báo hoặc thay đổi chế độ nhận tải nhiều lần khi usage dao động.
4. Nếu đạt điều kiện, ghi **một sự kiện có cấu trúc** với `poolName`, `usedBytes`, `thresholdBytes`, `count` và `timestamp`, hạn chế log storm.
5. Điều phối giảm nhận tải/đẩy việc sang service khác theo cơ chế nghiệp vụ đã thiết kế, có timeout và khả năng phục hồi.
6. Nếu thật sự cần heap dump/JFR, worker chỉ **đề xuất hoặc lập lịch** qua quy trình có phê duyệt và kiểm tra disk/CPU/latency, không kích hoạt tràn lan.
7. Theo dõi `queue_dropped`, worker backlog, callback latency, số lần cảnh báo, số lần chuyển admission state và recovery duration.

Không để worker vô hạn gọi `System.gc()` khi usage cao: explicit GC có thể không mang lại hiệu quả mong muốn, gây pause lớn và không xử lý nguyên nhân giữ object. Việc giảm nhận tải phải xem **memory pressure của ứng dụng lẫn JVM/container**, không chỉ một con số của memory pool.

## 9. Đảm bảo callback không làm trầm trọng sự cố

### 9.1. Những việc có thể làm trong callback

- So sánh loại notification bằng chuỗi hằng định nghĩa sẵn.
- Thử `offer` vào một bounded queue đã khởi tạo, không đợi.
- Cập nhật `AtomicBoolean` / `AtomicLong` / counter có chi phí nhỏ.
- Trả về nhanh, không tạo network connection hoặc block.
- Trong trường hợp có ràng buộc latency đặc biệt, chỉ đặt một flag/đánh dấu latest signal để worker tự thu lại dữ liệu.

Không có API nào đảm bảo “callback không allocation 100%” trong mọi JVM, nhưng nên tránh **allocation chủ động lớn và các hành động vô hạn**. Dùng metric để phát hiện callback mất bao lâu hoặc bị gọi liên tục; không nên instrument bằng cách tạo một log event lớn cho từng callback.

### 9.2. Những việc phải đưa ra worker riêng

- Parse/format nhiều `CompositeData`, gọi `getUsage()` cho nhiều pool theo chu kỳ, so state và trend.
- Ghi logger, gửi metrics, thông báo bên ngoài hoặc HTTP request.
- Retry/backoff, file/database operations, persist state.
- Phân tích trend, quyết định pause/resume workload, cooldown.
- Tạo heap histogram/heap dump/JFR có điều kiện và giới hạn, với quy trình bảo vệ dữ liệu.
- Điều tra exception/stack trace hoặc profiler, nếu có sự đồng ý vận hành phù hợp.

**Vì sao cả việc log trong callback cũng nên tránh?** Logging có thể đồng bộ, format dài, cố acquire appender lock hoặc ghi qua stdout pipe bị tắc. Khi thiếu bộ nhớ, logger có thể tự cần allocation. Thay bằng metric/counter nhỏ và để worker ghi log tổng hợp theo cửa sổ thời gian.

### 9.3. Không kỳ vọng “cảnh báo OOM sớm”

Theo JDK, threshold monitoring dùng cho quản lý tải / cân bằng công việc, **không nhằm phát hiện rồi phục hồi chắc chắn từ tình trạng thiếu bộ nhớ**. JVM có thể:
- Hết heap nhanh đến mức callback chưa được giao.
- Gặp OOME trong vùng khác không liên quan pool đã đặt threshold.
- Bị container kill do cgroup limit/native memory dù Java heap chưa chạm ngưỡng.
- Bị tắc hoặc shutdown trước khi worker xử lý signal.

Vì vậy, dùng notification kết hợp **metrics định kỳ, GC logs/JFR, container memory và alerts hạ tầng**, có admission control/fallback phù hợp. Không sử dụng listener làm cơ chế an toàn duy nhất.

## 10. Dùng count và dữ liệu snapshot để chống hiểu nhầm

`MemoryNotificationInfo` cung cấp:

| API | Dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `getPoolName()` | String | Pool đã kích hoạt thông báo |
| `getUsage()` | `MemoryUsage` | Snapshot usage **lúc notification được tạo** |
| `getCount()` | long | Số lần JVM đã ghi nhận loại threshold tương ứng tới thời điểm tạo notification |

Ví dụ minh họa: worker nhận:

~~~text
type=java.management.memory.threshold.exceeded
pool=ExampleOld
count=8
usedBytes=430000000
~~~

Trong khi khi worker lấy mẫu `pool.getUsage().getUsed()` thì còn `350000000`. Điều này **không phải data corruption**; thời điểm nhận notification và thời điểm đọc live usage có thể khác nhau, memory/GC đã thay đổi. Count `8` không phải số notifications worker đã xử lý trong queue: có thể queue drop/coalesce và count vẫn tăng. Hãy ghi riêng:
- `threshold_count` theo MXBean,
- `notifications_received` theo listener,
- `notifications_enqueued` / `notifications_dropped`,
- `alerts_emitted` / `actions_taken` bởi worker.

Từ chênh lệch giữa count và số event quan sát, **không suy ngay rằng JMX mất event** mà chưa xét việc pool khác, loại threshold khác, thời điểm chụp và việc cơ chế không phát mỗi lần usage cao. Phân biệt notification từ **cùng pool + cùng threshold type + cùng process lifetime**.

## 11. Kiểm thử đúng cách, không ép JVM OOM

### 11.1. Kiểm thử logic callback tách biệt với JVM

Vì JVM notification phụ thuộc collector/tải, hãy kiểm thử **unit** cho chính thiết kế queue:
- Gọi `listener.handleNotification(...)` bằng `Notification` giả có `type` đúng/sai.
- Kiểm tra type sai không được enqueue.
- Với queue capacity nhỏ, gửi nhiều tín hiệu, xác minh `offer` không block và dropped counter tăng.
- Kiểm tra worker nhận `CompositeData` hợp lệ, lọc đúng pool và xử lý invalid data có giới hạn.
- Xác minh worker exceptions không làm mất khả năng xử lý các tín hiệu tiếp theo.
- Test shutdown: remove listener, stop worker, đóng queue và không ghi thông tin nhạy cảm.

Không cần tạo pressure lớn để kiểm thử contract non-blocking.

### 11.2. Integration test trên JDK/collector đích

1. In danh sách `MemoryPoolMXBean` và hai cờ hỗ trợ; chọn pool có max xác định, lưu threshold cũ.
2. Dùng workload **có giới hạn cấp phát**, chạy trong môi trường test với resource limits và quan sát memory/GC. Không dùng vòng lặp allocation vô hạn chỉ để “cố tạo notification”.
3. Thiết lập threshold đủ thấp để thí nghiệm nhưng không làm cạn heap, có quy trình khôi phục.
4. Gắn listener, thu `poolName, usageBytes, count, timestamp` và metrics liên quan; chấp nhận sự kiện có thể đến chậm hoặc không đến trong khoảng ngắn.
5. Thử thay đổi ngưỡng, vượt rồi giảm dưới ngưỡng nếu workload cho phép, xác minh nguyên tắc rearm; đừng biến số lần gọi listener thành khẳng định timing chính xác.
6. Nếu test collection threshold, chỉ làm trên pool có `isCollectionUsageThresholdSupported()==true` và hiểu hành vi GC của collector; không ép explicit GC trong production.
7. Gây tải lớn cho **worker xử lý tín hiệu** trong test để xác minh callback không bị block và queue drop/coalesce hợp lý.
8. Dừng ứng dụng và xác minh listener đã hủy, worker ngừng và threshold đã phục hồi theo ownership policy.

**Không có stdout cố định cho integration test** vì mỗi JVM có tên pools, collector, MaxHeap và lịch GC khác nhau. Hãy kiểm tra **invariants** (đúng type, đúng pool, callback không block, queue bounded, metadata đúng) thay vì đòi số lượng event như một snapshot ghi sẵn.

### 11.3. Các tình huống kiểm thử quan trọng

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Không pool nào hỗ trợ usage threshold | Không throw; ứng dụng thoát/gắn cơ chế metrics thay thế |
| `getMax() == -1` | Không tính phần trăm sai hoặc đặt ngưỡng vô nghĩa |
| Memory tăng qua usage threshold | Có thể thấy event; count và snapshot phù hợp, không đòi giao ngay |
| Memory giảm xuống dưới rồi tăng lại | Có thể rearm và phát event theo cơ chế JVM |
| Retained memory sau GC vượt collection threshold | Event loại collection nếu pool/JVM hỗ trợ |
| Queue full | Callback trả nhanh, counter `dropped` tăng, không block |
| Worker/collector chậm | Queue bounded, có cooldown/log suppression và graceful degradation |
| Callback nhận pool khác | Worker lọc, không đưa ra quyết định sai service |
| Listener bị gọi đồng thời | Queue/atomic state nhất quán, không race gây corruption |
| Shutdown/exception | Cleanup listener và worker, không làm rò thread/task |
| Container OOMKilled | Không dựa vào memory threshold như đảm bảo có cảnh báo trước |

## 12. Các lỗi phổ biến

- **Đăng ký listener vào pool bean thay vì memory bean.** Memory notifications được phát từ `MemoryMXBean`, còn threshold được đặt trên từng `MemoryPoolMXBean`.
- **Bỏ kiểm tra support rồi gọi `setUsageThreshold`.** Không phải mọi pool đều hỗ trợ; có thể ném `UnsupportedOperationException`.
- **Nhầm collection usage threshold với usage threshold.** Một loại quan sát usage cao, loại kia quan sát mức còn lại sau công việc GC phù hợp.
- **Tin rằng threshold notification xảy ra ngay đúng lần allocation vượt ngưỡng.** JVM thực hiện checking vào thời điểm phù hợp, delivery không có deadline cứng.
- **Nhầm pool used với toàn process RSS.** Native memory, thread stacks, code cache và container limit còn góp phần gây hết memory.
- **Đặt threshold lớn hơn max xác định hoặc truyền -1.** `set...Threshold` nhận bytes không âm và có giới hạn API.
- **Dùng callback để tạo heap dump/GC.** Việc này nặng, có thể pause/đòi hỏi I/O và làm trầm trọng memory pressure.
- **Gọi `BlockingQueue.put`, `Future.get` hoặc HTTP trong callback.** Có thể block notification delivery.
- **Tạo executor/thread mới cho từng event.** Dễ bị thread explosion và allocation khi memory thấp.
- **Dùng unbounded queue vì sợ mất event.** Queue có thể lớn tới mức gây OOM thứ cấp.
- **Log full stack trace trong callback.** Dễ gây log storm, allocation và blocking stdout.
- **Thiếu dropped counter.** Mất tín hiệu âm thầm làm sai chẩn đoán.
- **Tin rằng count trong notification là số lần worker đã nhận.** Đây là count JVM phát hiện threshold, không phải số lần queue xử lý.
- **Xử lý mỗi signal như sự cố độc lập.** Notification có thể đến nhiều lần hoặc chậm; cần debounce/cooldown/hysteresis.
- **Chỉ đợi notification mới để mở lại nhận tải.** Recovery nên dựa trên re-check của worker; không tự động có tín hiệu “đã ổn” theo mong muốn.
- **Quên remove listener / khôi phục threshold.** Có thể rò lifecycle hoặc ghi đè cấu hình của thành phần khác.
- **Dùng notification làm hệ thống chống OOM duy nhất.** Không được đảm bảo, đặc biệt với native/cgroup memory hoặc sự cố cấp phát đột ngột.

## 13. Checklist triển khai production

**Khi đăng ký:**
1. Chọn đúng JVM, collector, pool, memory type, `isValid` và support flags.
2. Xác định `max` có nghĩa hay không, threshold theo bytes và chính sách ownership.
3. Ghi rõ muốn giám sát usage tăng cao hay retained usage sau GC.
4. Đặt threshold trong giai đoạn lifecycle được kiểm soát; không thay đổi từ các requests nghiệp vụ.
5. Đăng ký listener lên `MemoryMXBean` và hủy khi component shutdown.

**Trong callback:**
1. Lọc notification type chính xác.
2. Làm việc cực ngắn, không block, không I/O/network/heap dump/GC.
3. Chỉ `offer` vào bounded queue hoặc đặt atomic flag; có dropped/coalesced counter.
4. Không giữ object payload khổng lồ hoặc tạo worker mới cho mỗi event.
5. Đảm bảo thread-safety nếu callback được gọi đồng thời.

**Trên worker:**
1. Parse `CompositeData` thành `MemoryNotificationInfo` và lọc poolName.
2. Đọc lại live usage/collection usage phù hợp, không dùng snapshot cũ như trạng thái hiện tại.
3. Phối hợp threshold count với polling/GC metrics/container signals.
4. Dùng cooldown, hysteresis và giới hạn tần suất trước khi log/alert/change admission.
5. Xử lý worker lỗi, queue full, sink chậm và shutdown theo chính sách; tránh hành động tạo thêm memory pressure.
6. Lưu metric/log cấu trúc ít dữ liệu: pool, type, used/committed/max bytes, threshold, count, timestamp, action/outcome.
7. Không tự động chạy heap dump hoặc explicit GC mỗi lần vượt ngưỡng.

**Kiểm chứng:**
1. Test với JVM/collector thật, không kỳ vọng số notification cố định.
2. Thử pool unsupported, max không xác định, queue full, callback đồng thời.
3. Đối chiếu notifications với memory trend, GC và container signals.
4. Xác minh callback duration nhỏ, không tạo backlog và không gây p99 regression.
5. Xác định rõ ngưỡng chỉ là **tín hiệu sớm hỗ trợ điều phối**, không bảo đảm phục hồi từ OOME.

**Ghi nhớ:** `MemoryPoolMXBean` **đặt ngưỡng trên pool**, `MemoryMXBean` **phát notification**, và `MemoryNotificationInfo` **mang snapshot + count**. Hãy để `handleNotification` **lọc nhanh, bàn giao tín hiệu và return**; worker riêng có quyền quyết định sau khi đã đọc trạng thái hiện tại, áp dụng cooldown/hysteresis và kiểm tra tài nguyên. Đây là cách tận dụng MXBeans để quan sát memory pressure mà không làm JVM yếu thêm chính lúc cần phản ứng.

### Tài liệu tham khảo

- Oracle JDK 17, `MemoryPoolMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html
- Oracle JDK 17, `MemoryMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Oracle JDK 17, `MemoryNotificationInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryNotificationInfo.html
- Oracle JDK 17, `MemoryUsage`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html

Các ví dụ và threshold phần trăm trong bài mang tính học tập; xác nhận mức hỗ trợ và hành vi notification bằng chính JVM/version đang sử dụng trước khi triển khai thực tế.