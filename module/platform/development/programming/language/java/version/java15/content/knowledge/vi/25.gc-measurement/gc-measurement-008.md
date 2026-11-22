# Phân biệt memory leak với heap tăng do nhu cầu tải (Java 15+, thực hành Java 17+)

> **Chủ đề cha: Đo lường GC.** Khi dashboard báo **Java heap tăng**, chưa đủ bằng chứng để kết luận **memory leak**. Heap có thể tăng hoàn toàn hợp lý khi lượng request đồng thời, dữ liệu đang xử lý, số session còn hoạt động, kích thước cache hoặc hàng đợi tăng. Đồng thời, JVM có thể **giữ vùng nhớ đã commit** sau khi GC giải phóng object mà không lập tức trả tất cả về hệ điều hành. Ngược lại, một leak trong Java thường là những object **vẫn còn reachable từ GC roots nhưng không còn cần thiết về mặt nghiệp vụ**: GC không thể tự thu hồi vì chương trình tiếp tục giữ tham chiếu.

Điều cần phân biệt là **đường đi của các đường cong khác nhau**: heap **used**, heap **committed**, **live/retained objects sau những GC phù hợp**, **allocation rate**, **tải nghiệp vụ**, và memory của **toàn process/container**. Đo chúng **cùng thời điểm và cùng điều kiện tải** mới giúp chẩn đoán. Bài dùng API/tài liệu HotSpot, JFR, JDK Mission Control và `jcmd` còn được sử dụng ở JDK hiện đại; không dựa vào GC option/diagnostic workflow đã lỗi thời.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa *memory leak* trong môi trường GC và phân biệt với **working set tăng hợp lệ**, cache warmup, request queue/backlog và heap committed tăng.
2. Đọc đúng `MemoryUsage.getUsed()`, `getCommitted()`, `getMax()`, garbage collection counts và JVM process RSS.
3. Hiểu tại sao đồ thị heap **răng cưa** (sawtooth) là bình thường và vì sao phải xét những điểm **sau GC tương đương** theo thời gian.
4. Đặt điều kiện so sánh **cùng tải, cùng traffic mix, cùng số sessions/cache policy, cùng heap/JDK/collector**; không quy mọi tăng trưởng thành leak.
5. Phân biệt một số tình huống có triệu chứng giống nhau: allocation rate cao, heap headroom thiếu, cache không giới hạn, delayed expiry, backlog tích tụ, GC chưa chạy, fragmentation và native/direct memory.
6. Đo JVM heap/GC bằng `MemoryMXBean`, GC MXBeans, Unified Logging, JFR và `jcmd`.
7. Biết cách đọc `jdk.GCHeapSummary`: “After GC” là một sample của collector/phase cụ thể, **không luôn bằng live set chính xác sau full-heap tracing**.
8. Thu hẹp leak candidate bằng heap histograms, **dominator tree**, **retained size**, **path to GC roots**, allocation/old-object events; nhận diện dữ liệu nhạy cảm trong heap dump.
9. Thực hành bốn ví dụ Java 17+: nhu cầu tải lên/xuống so với giữ dữ liệu thừa; heap used/committed; direct memory; JFR GCHeapSummary.
10. Đưa ra kết luận có điều kiện, kèm chứng cứ và biện pháp sửa/giám sát, thay vì chỉ nói “RAM tăng = leak”.

## 2. Định nghĩa: leak, working set, allocation và heap capacity

### 2.1. Java memory leak không nhất thiết là bộ nhớ không có reference

Với Java GC, một object đủ điều kiện để thu gom khi không còn reachable qua GC roots theo thuật toán GC. Nếu một `static Map`, queue, thread, listener, cache hoặc class loader vẫn giữ tham chiếu tới object, GC **không thể biết** ứng dụng đã hết nhu cầu sử dụng nó.

Ví dụ:

~~~java
// Mảnh minh họa, không phải chương trình độc lập:
static final java.util.List<byte[]> forgotten = new java.util.ArrayList<>();

void handleRequest() {
    byte[] temporary = new byte[1024 * 1024];
    forgotten.add(temporary); // giữ lại mãi dù request đã kết thúc
}
~~~

Mảng `temporary` có thể không còn hữu dụng sau request nhưng vẫn reachable qua `forgotten`. **“Được giữ lại” khác với “cần được giữ lại”.** GC không thể xác định chính sách nghiệp vụ.

Một cache chứa dữ liệu truy cập thường xuyên **không phải leak chỉ vì còn reachable**. Nhưng cache không có size cap/TTL/eviction và tăng vô hạn sau khi tải đã ổn định có thể tạo **unbounded retention** — một leak theo nghĩa vận hành hoặc ít nhất một lỗi giới hạn tài nguyên.

### 2.2. Working set tăng vì workload là chuyện bình thường

Giả sử mỗi client hoạt động cần trung bình 64 KiB state. Nếu client đồng thời tăng từ 100 lên 1.000, lượng live state có thể tăng gấp 10 mà không hề có bug:

~~~text
Clients đang hoạt động:      100     1.000      100
State cần giữ (64 KiB/kh): ~6.25 MiB ~62.5 MiB ~6.25 MiB
                                  ↑         ↓
                         Tăng hợp lệ      Có thể giảm sau tải

Heap committed của JVM có thể vẫn cao ngay khi used/live giảm.
~~~

Ngoài client sessions còn có:
- Batching dữ liệu.
- In-flight requests/streams.
- Đồ thị object mà một transaction dài đang sử dụng.
- Cache warmup (cache tăng tới size cap/TTL ổn định).
- Backlog tiêu thụ chậm hơn producer.
- Class/JIT/metadata warmup không nằm trọn trong heap.
- Autoscaling và lưu lượng thay đổi theo giờ.

**Điểm quyết định:** Khi cùng loại tải và cùng trạng thái nghiệp vụ quay lại baseline, số **object không còn cần thiết** có còn bị giữ lại theo thời gian hay không?

### 2.3. Bốn đại lượng không được đánh đồng

| Đại lượng | Ý nghĩa | Có đồng nghĩa leak không? |
| --- | --- | --- |
| **Heap used** | Bytes đang được tính là sử dụng trong Java heap tại thời điểm đo | **Không**; có thể có nhiều garbage chưa được thu gom |
| **Heap committed** | Bytes JVM đã commit để cấp phát heap theo `MemoryUsage` | **Không**; JVM có thể giữ để cấp phát lại |
| **Heap max** | Giới hạn tối đa heap được JVM báo (có thể `-1` nếu không xác định) | **Không**; đó là capacity, không phải usage |
| **Process RSS / container memory** | Resident memory của cả JVM/native allocations, stacks, code cache, direct buffers, mmap, các thành phần khác | **Không**; thậm chí không chỉ là Java heap |
| **Live/reachable objects** | Objects còn được xem là reachable tại thời điểm/phạm vi GC | Có thể là legitimate state hoặc retention không cần thiết |
| **Allocation rate** | Bytes mới được tạo mỗi giây | Cao không chứng minh leak; objects có thể chết rất nhanh |
| **Retained size của dominator** | Tổng bộ nhớ có thể được giữ sống do một object/root thống trị tập object | Là bằng chứng giúp truy nguồn, **chưa tự cho biết semantic đúng/sai** |

**Công thức giúp hiểu:**

~~~text
Heap used = objects chưa bị reclaim + metadata/overhead trong heap
            (không thể xem toàn bộ used là business live set).

Heap committed >= Heap used.
Heap max >= Heap committed (nếu max được định nghĩa).

Process RSS != Heap used
Process RSS != Heap committed
RSS không phải thước đo direct duy nhất của Java memory leak.
~~~

Không nhất thiết heap committed giảm về mức đầu khi load giảm; GC và OS có chính sách giữ/trả memory khác nhau. **Không tạo “leak alert” chỉ từ committed hoặc RSS tăng.**

## 3. Các đường cong cần quan sát cùng lúc

### 3.1. Sawtooth bình thường

Ứng dụng liên tục tạo objects tạm: heap used tăng, rồi giảm khi GC reclaim:

~~~text
Heap used
  ^
  |       /\        /\        /\
  |      /  \      /  \      /  \
  | ____/    \____/    \____/    \____
  +------------------------------------> time
     GC↓       GC↓       GC↓

Nếu tải ổn định, các mức đáy sau GC tương đương có thể gần ổn định.
Đỉnh/chu kỳ GC thay đổi không tự kết luận leak.
~~~

Với G1, ZGC, Shenandoah và các collectors concurrent khác, sawtooth có thể **không sắc nét** hoặc metric sampling thể hiện khác. Một collector có nhiều loại cycles (young/old, minor/major); không tùy tiện ghép các đáy không tương đương.

### 3.2. Retention tăng đáng ngờ khi tải không tăng

~~~text
Heap used
  ^
  |          /\       /\       /\
  |     /\  /  \     /  \     /  \
  |    /  \/    \___/    \___/    \
  | __/        ^         ^         ^
  +------------------------------------> time
           After-GC  After-GC  After-GC (comparable)
              60        90        120 MiB
         load/request mix/cache policy tương tự

Xu hướng đáng điều tra: sau GC, retained footprint tăng liên tục
mà không có tăng workload/state được giải thích.
~~~

**Không tự kết luận chắc chắn leak.** Live-after-GC có thể tăng vì cache đang warm, session sống lâu, batch chưa kết thúc, delayed TTL eviction, GC phase không tương đương hoặc memory đã được reserve cho cấu trúc hợp lệ. Cần tìm **root giữ object và lý do nghiệp vụ**.

### 3.3. Tải tăng rồi giảm: used có thể xuống, committed vẫn cao

~~~text
Concurrent load:    100 ---- 1000 ---- 100
Heap used:           80 ----  420 ----  110 MiB (ví dụ)
Heap committed:     256 ----  512 ----  512 MiB (ví dụ)

Sau khi tải giảm:
- Objects không cần thiết có thể được GC reclaim.
- JVM vẫn có thể giữ 512 MiB committed để cấp phát nhanh sau này.
- RSS có thể chưa trả ngay cho OS.
- Không nên nói "leak 402 MiB" từ chênh lệch committed.
~~~

Đây là con số **giả định để đọc biểu đồ**, không phải kết quả một JVM được đo. Các policy commit/uncommit khác nhau theo GC, JDK, JVM options và OS; muốn xác nhận cần xem **used và live objects**.

### 3.4. Tải không tăng nhưng backlog tăng

Nếu producer đưa 5.000 messages/s vào queue, consumer chỉ xử lý 4.000 messages/s:
- Queue tăng thêm **1.000 messages/s**.
- Heap live tăng do queue đang giữ dữ liệu **để xử lý**.
- Dù không phải bug “quên xóa reference”, đây vẫn là **tích lũy không giới hạn** và nguy cơ OOM.

Cần capacity planning, bounded queues/backpressure, rate limits, drain/retry policy, deadline, load shedding và khả năng mở rộng consumer. **“Không phải leak Java” không đồng nghĩa hệ thống an toàn.**

## 4. Quy trình 6 câu hỏi để phân loại nguyên nhân

1. **Metric nào tăng?** Heap `used`, `committed`, heap `max`, old-gen pool, nonheap, buffer pool, RSS, cgroup usage? Không được gọi chung tất cả là RAM.
2. **Tải nào tăng?** QPS, concurrency, number of sessions, batch size, pending tasks, queue depth, cache hit/miss/entries, request payload sizes, transaction durations?
3. **Đặt baseline đúng:** Cùng phiên bản JDK/GC, heap settings, cấu hình cache, điều kiện warmup và tải tương tự. So sánh dữ liệu cùng phase và time window.
4. **Sau những lần GC phù hợp, footprint ra sao?** Điểm đáy ổn định khi workload ổn định, hay tăng không giải thích được? Có Full GC hoặc collector pressure không? Tránh cố ép GC production chỉ để tạo graph.
5. **Objects nào tăng và bị giữ bởi ai?** Heap histogram, JFR OldObjectSample, heap dump, dominator tree và paths to GC roots.
6. **Có nguồn giữ hợp lý không?** Active clients, cache giới hạn, pending work thật; hay `static` collection, listener không deregister, abandoned ThreadLocal, timeout task, class loader, unbounded queue?

Một kết luận mạnh phải kết nối **metric trend → object type → dominator/GC root → vòng đời nghiệp vụ → điều kiện tái hiện → fix → metric sau fix**.

## 5. Ví dụ 1 — So sánh load demand với leak qua số reference được giữ

Ví dụ không phụ thuộc thời điểm GC chạy. Nó biểu diễn **các reference được giữ**:

- `DemandCache` giữ một mảng 64 KiB cho mỗi client đang hoạt động; số client lần lượt **32 → 128 → 32**. Khi client kết thúc, map xóa entry.
- `LeakyHistory` tạo thêm 32 mảng 64 KiB sau mỗi lượt xử lý với **cùng mức tải**, nhưng không bao giờ xóa lịch sử mà ứng dụng không còn cần.
- Mọi số đếm tham chiếu và payload dưới đây **đều chính xác/ổn định**, nhưng không phải cùng với measured heap used (còn object headers/GC metadata/garbage chưa reclaim).

### 5.1. Tệp `RetentionPatternsDemo.java` — chương trình độc lập Java 17+

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class RetentionPatternsDemo {
    private static final int BLOCK_KIB = 64;

    static final class DemandCache {
        private final Map<Integer, byte[]> active = new HashMap<>();

        void setActiveClients(int count) {
            for (int i = 0; i < count; i++) {
                active.computeIfAbsent(i,
                        ignored -> new byte[BLOCK_KIB * 1024]);
            }
            active.keySet().removeIf(id -> id >= count);
        }

        int retainedBlocks() {
            return active.size();
        }
    }

    static final class LeakyHistory {
        private final List<byte[]> obsolete = new ArrayList<>();

        void processSameLoad(int requests) {
            for (int i = 0; i < requests; i++) {
                obsolete.add(new byte[BLOCK_KIB * 1024]);
            }
        }

        int retainedBlocks() {
            return obsolete.size();
        }
    }

    static void show(String label, int count) {
        long kib = (long) count * BLOCK_KIB;
        System.out.println(label + ".retainedBlocks=" + count);
        System.out.println(label + ".retainedKiB=" + kib);
    }

    public static void main(String[] args) {
        DemandCache legitimateDemand = new DemandCache();
        for (int clients : new int[]{32, 128, 32}) {
            legitimateDemand.setActiveClients(clients);
            show("demand.clients" + clients,
                    legitimateDemand.retainedBlocks());
        }

        LeakyHistory history = new LeakyHistory();
        for (int round = 1; round <= 3; round++) {
            history.processSameLoad(32);
            show("leak.round" + round,
                    history.retainedBlocks());
        }

        System.out.println("demandReturnsToBaseline=" +
                (legitimateDemand.retainedBlocks() == 32));
        System.out.println("leakRetainsObsoleteRecords=" +
                (history.retainedBlocks() == 96));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 RetentionPatternsDemo.java
java -Xms32m -Xmx128m RetentionPatternsDemo
~~~

**Stdout chính xác đã kiểm thử trên JDK 24:**

~~~text
demand.clients32.retainedBlocks=32
demand.clients32.retainedKiB=2048
demand.clients128.retainedBlocks=128
demand.clients128.retainedKiB=8192
demand.clients32.retainedBlocks=32
demand.clients32.retainedKiB=2048
leak.round1.retainedBlocks=32
leak.round1.retainedKiB=2048
leak.round2.retainedBlocks=64
leak.round2.retainedKiB=4096
leak.round3.retainedBlocks=96
leak.round3.retainedKiB=6144
demandReturnsToBaseline=true
leakRetainsObsoleteRecords=true
~~~

### 5.2. Phân tích

**Demand:** `active=32` cần `2.048 KiB`; lúc peak `128` cần `8.192 KiB`. Khi giảm xuống 32, map giữ lại 32 arrays. Mảng dư trở nên không reachable qua map và **có thể** được GC reclaim. JVM không bắt buộc thu hồi/release committed bytes tức thì.

**Leaky history:** Mỗi round chỉ xử lý 32 requests, nhưng số entry tăng `32 → 64 → 96`. `obsolete` giữ arrays dù chúng không còn phục vụ yêu cầu. Đây là retained-reference bug đã được **cố tình tạo ra**; sau mỗi lượt tải bằng nhau, lý do tăng memory không phải nhiều active clients.

**Điểm giới hạn:** Code không đọc heap used. Nó chứng minh vòng đời reference bằng state của chương trình. Nếu thêm `MemoryMXBean`, con số used có thể dao động theo GC, object headers, heap layout và thời điểm lấy mẫu. Một leak có thật không bắt buộc hiện thành đồ thị thẳng đều ở mọi giây.

## 6. Đo heap used, committed, max bằng Management API

JDK hiện đại cung cấp `java.lang.management.MemoryMXBean` và `MemoryUsage`.

~~~java
// Mảnh minh họa trong phương thức, chưa phải chương trình độc lập:
MemoryUsage heap =
    ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
long used = heap.getUsed();
long committed = heap.getCommitted();
long max = heap.getMax(); // có thể -1 nếu không được xác định
~~~

| Getter | Ý nghĩa đúng | Bẫy |
| --- | --- | --- |
| `getUsed()` | Lượng heap đang dùng theo số liệu JVM tại thời điểm chụp | Có thể chứa objects sẽ được reclaim ở lần GC kế |
| `getCommitted()` | Heap đã commit, bảo đảm có thể dùng theo `MemoryUsage` | **Không bằng** bytes reachable; không phải leak khi vẫn lớn |
| `getMax()` | Giới hạn trên nếu JVM có định nghĩa | `-1` nghĩa là không xác định; không luôn bằng chính xác `-Xmx` trong mọi environment |
| `getInit()` | Lượng ban đầu được yêu cầu lúc startup | Không phải live memory |

**Bất biến theo Javadoc:** `used ≤ committed`, và nếu `max` xác định, `committed ≤ max`. Tuy nhiên, số liệu có thể được sample tại các thời điểm khác nhau giữa pools, và việc cộng metrics từ những nguồn khác nhau không nhất thiết tạo một snapshot nguyên tử.

### 6.1. GC counts và collection time có hạn chế

`ManagementFactory.getGarbageCollectorMXBeans()` trả GC beans do runtime cung cấp. `getCollectionCount()` và `getCollectionTime()` có thể hữu ích trong trend, nhưng:
- Nhiều collector có nhiều beans (young/old, pauses/cycles).
- Một số values có thể `-1` nếu không hỗ trợ.
- Tên/semantics khác nhau giữa G1/ZGC/Shenandoah và giữa JDK versions.
- Không lấy tổng collection time làm **GC worker CPU** hoặc kết luận memory leak.
- GC count tăng khi allocation tăng cũng có thể là hành vi bình thường.

## 7. Ví dụ 2 — Quan sát demand tăng/rút bằng used và committed

Demo giữ **64 arrays × 256 KiB = 16 MiB payload** qua một static volatile field, chụp số liệu, sau đó bỏ references. `System.gc()` trong demo chỉ là **GC hint có chủ đích trong phòng thí nghiệm**; runtime được phép xử lý khác nhau, GC có thể concurrent hoặc bị vô hiệu hóa (`-XX:+DisableExplicitGC`). **Không dùng lời gọi này như “mẹo sửa memory leak” trong production**.

### 7.1. Tệp `HeapUsageSnapshotsDemo.java` — Java 17+

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.List;

public class HeapUsageSnapshotsDemo {
    private static volatile byte[][] active;

    static long countGc(
            List<GarbageCollectorMXBean> collectors) {
        long count = 0;
        for (GarbageCollectorMXBean gc : collectors) {
            if (gc.getCollectionCount() >= 0) {
                count += gc.getCollectionCount();
            }
        }
        return count;
    }

    static void snapshot(String phase, MemoryMXBean memory) {
        MemoryUsage heap = memory.getHeapMemoryUsage();
        long mib = 1024L * 1024L;
        System.out.println(phase + ".usedMiB=" +
                heap.getUsed() / mib);
        System.out.println(phase + ".committedMiB=" +
                heap.getCommitted() / mib);
        System.out.println(phase + ".maxMiB=" +
                heap.getMax() / mib);
        System.out.println(phase + ".usedNotAboveCommitted=" +
                (heap.getUsed() <= heap.getCommitted()));
        System.out.println(phase + ".committedNotAboveMax=" +
                (heap.getMax() < 0
                        || heap.getCommitted() <= heap.getMax()));
    }

    static void labGcHint() throws InterruptedException {
        System.gc(); // Demo only: hint, not guaranteed to reclaim.
        Thread.sleep(350);
    }

    public static void main(String[] args) throws Exception {
        MemoryMXBean memory =
                ManagementFactory.getMemoryMXBean();
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        labGcHint();
        snapshot("baseline", memory);
        long before = countGc(collectors);

        byte[][] roots = new byte[64][];
        for (int i = 0; i < roots.length; i++) {
            roots[i] = new byte[256 * 1024];
            roots[i][0] = (byte) i;
        }
        active = roots;
        labGcHint();
        snapshot("demandHigh", memory);
        System.out.println("activeRetainedPayloadMiB=" +
                (long) active.length * 256 / 1024);

        active = null;
        roots = null;
        labGcHint();
        snapshot("demandReleased", memory);
        System.out.println("gcCountDelta=" +
                (countGc(collectors) - before));
        System.out.println("explicitGcIsOnlyHint=true");
    }
}
~~~

Chạy trên HotSpot có G1 và ZGC (Java 17+; `-XX:+UseZGC` hỗ trợ tùy JDK build):

~~~bash
javac --release 17 -encoding UTF-8 HeapUsageSnapshotsDemo.java

java -XX:+UseG1GC -Xms32m -Xmx128m \
     HeapUsageSnapshotsDemo

java -XX:+UseZGC -Xms32m -Xmx128m \
     HeapUsageSnapshotsDemo
~~~

Các lệnh trên dùng ký hiệu nối dòng `\` trong Bash; trên Windows PowerShell hãy viết mỗi lời gọi `java` **trên một dòng** hoặc dùng cú pháp nối dòng của PowerShell.

**Một lần quan sát thực tế trên Azul Zulu JDK 24/Windows (đơn vị MiB là phép chia nguyên):**

~~~text
G1:
baseline.usedMiB=1
baseline.committedMiB=32
baseline.maxMiB=128
baseline.usedNotAboveCommitted=true
baseline.committedNotAboveMax=true
demandHigh.usedMiB=17
demandHigh.committedMiB=39
demandHigh.maxMiB=128
demandHigh.usedNotAboveCommitted=true
demandHigh.committedNotAboveMax=true
activeRetainedPayloadMiB=16
demandReleased.usedMiB=1
demandReleased.committedMiB=32
demandReleased.maxMiB=128
demandReleased.usedNotAboveCommitted=true
demandReleased.committedNotAboveMax=true
gcCountDelta=4
explicitGcIsOnlyHint=true

ZGC:
baseline.usedMiB=4
baseline.committedMiB=32
baseline.maxMiB=128
baseline.usedNotAboveCommitted=true
baseline.committedNotAboveMax=true
demandHigh.usedMiB=24
demandHigh.committedMiB=36
demandHigh.maxMiB=128
demandHigh.usedNotAboveCommitted=true
demandHigh.committedNotAboveMax=true
activeRetainedPayloadMiB=16
demandReleased.usedMiB=4
demandReleased.committedMiB=36
demandReleased.maxMiB=128
demandReleased.usedNotAboveCommitted=true
demandReleased.committedNotAboveMax=true
gcCountDelta=24
explicitGcIsOnlyHint=true
~~~

**Tất cả các số `usedMiB`, `committedMiB`, `gcCountDelta` là ví dụ từ hai lần chạy cụ thể — không phải stdout phải giống nhau trên mọi JDK/OS/collector.** Các dòng kiểm bất biến thường là `true` theo Javadoc.

### 7.2. Phân tích quan trọng

Với **G1**, used tăng `1 → 17 MiB` khi demand giữ 16 MiB rồi giảm về `1 MiB` khi release. Committed tăng lên 39 MiB rồi giảm về 32 MiB. Với **ZGC**, used tăng `4 → 24 MiB` rồi giảm về `4 MiB`, trong khi committed ở lần cuối **vẫn là 36 MiB**, không về 32 MiB.

Điều này minh họa hai ý:
1. **Live/used sau reclaim** có thể trở lại baseline khi references không còn.
2. **Committed** có thể giữ mức cao sau khi workload rút xuống, tùy GC và chính sách. Nếu ai đó chỉ nhìn committed=36 MiB thay vì baseline=32 MiB rồi kết luận “leak 4 MiB”, kết luận đó không có cơ sở.

**GC có quyền khác nhau:** `System.gc()` là lời gợi ý, không bảo đảm dọn ngay; `Thread.sleep(350)` không phải API “chờ GC hoàn tất”. Vì vậy khi kết quả của bạn khác, phân tích thêm GC log/events thay vì hardcode kỳ vọng rằng used buộc phải giảm ngay.

## 8. JFR và GC logging: dùng trend của sau-GC với điều kiện tương đương

### 8.1. Unified Logging của HotSpot

Một phương pháp ít can thiệp ở mức JVM là bật log GC ngay từ startup:

~~~bash
java -XX:+UseG1GC -Xms256m -Xmx1g \
     -Xlog:gc*=info:file=gc.log:uptime,level,tags \
     -jar app.jar
~~~

`app.jar` đại diện **ứng dụng của bạn**, không phải file được cung cấp trong bài. Nếu dùng ZGC hoặc Shenandoah trên build hỗ trợ, đổi GC flag cho phù hợp và giữ logging nhất quán khi so sánh.

Từ log, quan sát:
- Time, `GC(id)`, lý do/loại collection.
- Heap occupancy trước-sau GC.
- Young/mixed/full, minor/major cycles theo collector.
- Pause duration, concurrent phases, allocation stalls.
- Tần suất GC, pressure và headroom.

**Không đọc mọi dòng “After” như live set cuối cùng.** G1 young collection có thể để lại object ở old generation chưa được đánh giá lại trong cùng cycle; GC concurrent có nhiều phase và điểm sample. So sánh đúng loại GC, cùng điều kiện tải/collector, và dùng heap dump khi cần tìm roots.

### 8.2. JFR – ghi lại heap trước/sau GC

JFR có `jdk.GCHeapSummary` (fields `when`, `gcId`, `heapUsed`) và `jdk.GarbageCollection`. Các events này hỗ trợ xây trend nhưng không thay thế heap dump/dominator analysis. Một recording phải có sự kiện được bật và có các lần GC xảy ra; nếu không, không có sample.

## 9. Ví dụ 3 — Đọc `jdk.GCHeapSummary` bằng Java 17+ JFR API

Chương trình:
1. Tạo một file `.jfr` tạm.
2. Bật `jdk.GCHeapSummary` và `jdk.GarbageCollection`.
3. Cấp phát tổng cộng **512 MiB** objects qua ring 256 slots, cho phép GC hoạt động trong heap 128 MiB.
4. Sau recording, đọc events có `when` là `Before GC` hoặc `After GC` và tổng hợp min/max của **những mẫu After GC trong recording**.
5. Xóa file tạm, không để lại dữ liệu nhạy cảm.

### 9.1. Tệp `GcHeapSummaryJfrDemo.java` — độc lập, Java 17+

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class GcHeapSummaryJfrDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile(
                "heap-trend-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.enable("jdk.GCHeapSummary");
                recording.enable("jdk.GarbageCollection");
                recording.start();

                byte[][] ring = new byte[256][];
                for (int i = 0; i < 8_192; i++) {
                    byte[] block = new byte[64 * 1024];
                    block[0] = (byte) i;
                    ring[i % ring.length] = block;
                }
                Thread.sleep(400);

                recording.stop();
                recording.dump(file);
            }

            long before = 0;
            long after = 0;
            long afterMin = Long.MAX_VALUE;
            long afterMax = Long.MIN_VALUE;

            for (RecordedEvent event :
                    RecordingFile.readAllEvents(file)) {
                if (!"jdk.GCHeapSummary".equals(
                        event.getEventType().getName())) {
                    continue;
                }
                String when = event.getString("when");
                long heapUsed = event.getLong("heapUsed");
                if ("Before GC".equals(when)) {
                    before++;
                } else if ("After GC".equals(when)) {
                    after++;
                    afterMin = Math.min(afterMin, heapUsed);
                    afterMax = Math.max(afterMax, heapUsed);
                }
            }

            System.out.println("beforeGcSamples=" + before);
            System.out.println("afterGcSamples=" + after);
            System.out.println("hasAfterGcSamples=" + (after > 0));
            if (after > 0) {
                System.out.println("afterGcMinMiB=" +
                        afterMin / (1024 * 1024));
                System.out.println("afterGcMaxMiB=" +
                        afterMax / (1024 * 1024));
            }
            System.out.println(
                    "afterGcSamplesNotFullLiveSetProof=true");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy với JDK 17+ có module `jdk.jfr`:

~~~bash
javac --release 17 -encoding UTF-8 GcHeapSummaryJfrDemo.java

java -XX:+UseG1GC -Xms32m -Xmx128m \
     GcHeapSummaryJfrDemo

java -XX:+UseZGC -Xms32m -Xmx128m \
     GcHeapSummaryJfrDemo
~~~

**Một lần chạy kiểm chứng trên JDK 24:**

~~~text
G1:
beforeGcSamples=55
afterGcSamples=55
hasAfterGcSamples=true
afterGcMinMiB=5
afterGcMaxMiB=127
afterGcSamplesNotFullLiveSetProof=true

ZGC:
beforeGcSamples=12
afterGcSamples=12
hasAfterGcSamples=true
afterGcMinMiB=22
afterGcMaxMiB=100
afterGcSamplesNotFullLiveSetProof=true
~~~

**Đọc đúng số liệu:**
- Số lượng events phụ thuộc GC, workload, thời điểm recording, GC ergonomics và JDK build.
- `afterGcMinMiB` và `afterGcMaxMiB` là **min/max của các events After GC trong một recording**, **không** nhất thiết là live set min/max của toàn heap.
- Việc cùng một workload cho G1 55 events còn ZGC 12 events không phải bằng chứng collector nào tốt hơn; event taxonomy và collection behavior khác.
- Trong production, hãy lưu **timestamp + GC ID + loại GC/phase + traffic/load**. Không chỉ đọc min/max toàn bộ recording rồi suy leak.
- Một collector concurrent có thể báo heapUsed tại điểm thời gian khác relative to mark/reclaim; muốn so cần biết semantics của collector.
- Nếu recording không có after-GC event, `hasAfterGcSamples=false` và code không in min/max. Không coi thiếu event là “heap không bao giờ GC”.
- JFR có profiling overhead, dù thường thấp. Chọn tần suất/duration/retention theo môi trường; không bật stack/path-to-root đắt đỏ một cách tùy tiện trên peak traffic.

### 9.2. Đọc JFR file của service bằng công cụ có sẵn

Khi ứng dụng có JFR recording:

~~~bash
# Bắt đầu recording nếu service/VM cho phép attach:
jcmd <pid> JFR.start name=HeapStudy settings=profile duration=2m \
     filename=heap-study.jfr

# Có thể in các sự kiện hữu ích đã thực sự được ghi:
jfr print --events jdk.GCHeapSummary,jdk.GarbageCollection \
    heap-study.jfr
~~~

Các lệnh yêu cầu quyền truy cập process và file tương ứng; trong container có thể phải chạy trong đúng namespace/user. `<pid>` là placeholder cho PID thật, không phải ký tự để chạy nguyên xi.

Để điều tra retention, JDK Mission Control/Flight Recorder có thể hỗ trợ phân tích **Old Object Sample**, allocation stack traces và một số GC root paths nếu recording settings thu thập chúng. **Các samples không chứng minh riêng một object là leak**; cần kiểm business lifecycle và root ownership. Khả năng sự kiện và trường phụ thuộc JDK/settings/version.

## 10. Heap histogram, heap dump và path to GC roots

### 10.1. Heap histogram là bước khoanh vùng, không phải kết luận cuối

Trong HotSpot hiện đại:

~~~bash
# Xem các JVM đang chạy mà jcmd có quyền thấy:
jcmd -l

# Dùng PID thật của service:
jcmd <pid> GC.class_histogram
~~~

Histogram thường liệt kê `#instances`, `#bytes` và `class name`. Nó có thể gợi ý:
- `byte[]`, `String`, `HashMap$Node`, `ArrayList`, message envelopes.
- Một class custom tăng số instances theo thời gian.
- Class loader hoặc cache entries chưa release.

**Nhưng:** Histogram không chỉ ra đầy đủ ai giữ object, và số lượng class tăng có thể do legitimate traffic/cache. `GC.class_histogram` có **impact cao** phụ thuộc heap size/content; tùy option/VM có thể gây collection/safepoint. Không chạy liên tục trên production peak mà chưa đánh giá overhead.

Mặc định `GC.class_histogram` **không bật `-all`**; `-all` sẽ tính cả objects không reachable và không thích hợp để kết luận “mọi object trong histogram vẫn sống”. Đọc phiên bản JDK của lệnh để hiểu semantics.

### 10.2. Heap dump và dominator analysis

Khi xác định được cửa sổ đáng ngờ, thu heap dump khi có quyền:

~~~bash
# Ví dụ JDK 25:
jcmd <pid> GC.heap_dump filename=heap-incident.hprof

# Tùy chính sách, có thể bật ở startup để ghi khi Java heap OOME:
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/secure/dumps \
     -jar app.jar
~~~

**Lưu ý:**
- `GC.heap_dump` có **impact cao** và có thể yêu cầu full GC trước dump theo JDK defaults trừ khi dùng option khác; hãy đọc JDK man page.
- Heap dump có thể chứa **passwords, access tokens, PII, dữ liệu khách hàng, payloads nhạy cảm**. Lưu ở vị trí bảo vệ, giới hạn truy cập, mã hóa khi cần và áp retention policy.
- File có thể lớn nhiều GB; cần disk space/IO budget; một dump trên service đang chịu tải có thể gây pause/ảnh hưởng SLO.
- `-XX:HeapDumpPath` là địa chỉ ví dụ trên hệ Unix; trên Windows/container dùng path an toàn tương ứng.
- Java heap dump không bao quát mọi native allocations, mmap, metaspace, thread stacks hoặc vùng RSS ngoài heap.

Mở dump bằng công cụ tương thích như JDK Mission Control hoặc Eclipse Memory Analyzer (MAT); tìm:
1. Object types chiếm nhiều **shallow size**.
2. **Retained size** và **dominator tree**: object nào nếu bỏ tham chiếu sẽ cho phép reclaim một lượng lớn các object khác.
3. **Paths to GC roots** (loại trừ weak refs khi phân tích phù hợp): reference từ `static Map`, session registry, queue, callback listener, thread-local value, timer executor, class loader, singleton cache, retry state…
4. Collection size qua nhiều snapshots trong điều kiện tải tương đương.
5. Dữ liệu có hợp lệ để giữ không? Ví dụ cache cap=10.000 và có 9.500 entries là bình thường; cap=10.000 nhưng 200.000 entries không giải thích được là đáng nghi.

**Shallow size** của một `HashMap` có thể nhỏ, nhưng **retained size** của nó có thể lớn vì giữ cả graph value objects. Đừng chỉ nhìn top allocation site; cần thấy **root giữ dữ liệu và lý do tồn tại**.

### 10.3. So sánh heap dump A/B theo thời điểm

Cách làm hiệu quả:
- Snapshot A sau warmup, ở một mốc tải ổn định.
- Snapshot B sau cùng thời lượng/cùng loại tải ở thời điểm sau.
- Kiểm object counts/retained sizes tăng ở classes nào.
- Kiểm GC roots tới những objects ấy, đặc biệt objects đáng lẽ hết vòng đời.
- Với cache hợp lệ, verify size/TTL/evictions và ownership.
- Với queue, so expected queue depth/backlog theo producer-consumer rates.
- Với listener/scheduler, xem unregister/cancel/remove code path.

**Không đảm bảo so dump tự động chỉ ra nguyên nhân**: còn generation age, GC state, concurrent cycles, snapshot pause, các request đang chạy. Có thể cần nhiều lần lấy mẫu và instrumentation nghiệp vụ.

## 11. Memory tăng nhưng không thuộc Java heap

### 11.1. Process RSS gồm nhiều vùng hơn `getHeapMemoryUsage()`

Nếu dashboard báo container memory/RSS tăng nhưng heap used gần như ngang, cân nhắc:
- `ByteBuffer.allocateDirect`, Netty/direct buffer pools.
- Memory-mapped files (`MappedByteBuffer`).
- Metaspace/class metadata, code cache/JIT.
- Native allocations từ JNI/JNA/library C/C++.
- Thread stacks và thread count tăng.
- TLS/native compression/decompression, font/image libraries.
- Native heap của VM và arena/allocator fragmentation.
- Kernel/page-cache/cgroup charging theo môi trường.

**Không phân loại tất cả thành “Java heap memory leak”.** Đôi khi có native memory leak hoặc một cache ngoài heap hợp lệ; cần đo đúng nguồn.

### 11.2. `BufferPoolMXBean` cho direct/mapped buffer pools

`ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` có thể đưa ra `direct`/`mapped` pool metrics:
- `getCount()`: ước lượng số buffers.
- `getTotalCapacity()`: ước lượng capacity bytes của buffers trong pool.
- `getMemoryUsed()`: ước lượng native memory, có thể khác capacity hoặc là `-1` khi không hỗ trợ.

Đây **không phải tổng native memory của process** và **không bao quát mọi malloc từ JNI/third-party library**.

## 12. Ví dụ 4 — Direct buffers tăng mà Java heap không tăng tương ứng

Demo giữ **4 direct buffers × 8 MiB = 32 MiB** ngoài Java heap, đo thay đổi capacity của buffer pool và heap used. Các objects `ByteBuffer` wrapper nằm trên heap; phần direct payload nằm ngoài heap.

### 12.1. Tệp `HeapVsDirectBufferDemo.java` — Java 17+

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

public class HeapVsDirectBufferDemo {
    private static final List<ByteBuffer> heldDirect =
            new ArrayList<>();

    static BufferPoolMXBean directPool() {
        return ManagementFactory
                .getPlatformMXBeans(BufferPoolMXBean.class)
                .stream()
                .filter(p -> "direct".equals(p.getName()))
                .findFirst()
                .orElseThrow();
    }

    public static void main(String[] args) {
        MemoryMXBean memory =
                ManagementFactory.getMemoryMXBean();
        BufferPoolMXBean direct = directPool();
        long beforeCapacity = direct.getTotalCapacity();
        long beforeHeap = memory.getHeapMemoryUsage().getUsed();

        for (int i = 0; i < 4; i++) {
            ByteBuffer buffer =
                    ByteBuffer.allocateDirect(8 * 1024 * 1024);
            buffer.put(0, (byte) (i + 1));
            heldDirect.add(buffer);
        }

        long afterCapacity = direct.getTotalCapacity();
        long afterHeap = memory.getHeapMemoryUsage().getUsed();
        long mib = 1024L * 1024L;
        System.out.println("directBuffersHeld=" +
                heldDirect.size());
        System.out.println("requestedDirectMiB=32");
        System.out.println("directCapacityDeltaMiB=" +
                (afterCapacity - beforeCapacity) / mib);
        System.out.println("directCapacityIncreased=" +
                (afterCapacity > beforeCapacity));
        System.out.println("heapUsedDeltaMiB=" +
                (afterHeap - beforeHeap) / mib);
        System.out.println("heapObjectIsNotDirectPayload=true");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 HeapVsDirectBufferDemo.java
java -Xms32m -Xmx128m -XX:MaxDirectMemorySize=64m \
     HeapVsDirectBufferDemo
~~~

**Stdout quan sát trong lần thử JDK 24/Windows:**

~~~text
directBuffersHeld=4
requestedDirectMiB=32
directCapacityDeltaMiB=32
directCapacityIncreased=true
heapUsedDeltaMiB=0
heapObjectIsNotDirectPayload=true
~~~

`directCapacityDeltaMiB=32` đến từ 4 buffers được giữ; `heapUsedDeltaMiB=0` trong lần thử chỉ là snapshot **làm tròn/trừ nguyên** khi đo, **không** có nghĩa wrappers không tồn tại hoặc luôn đúng 0 trên mọi JVM. Heap usage có thể dao động do các objects khác/GC. Khi release references tới direct buffers, native allocations có thể được dọn **không đồng bộ**; không có cam kết lập tức giảm RSS.

### 12.2. Kiểm NMT khi nghi native leak

Trên HotSpot hỗ trợ **Native Memory Tracking (NMT)**, khởi động service với:

~~~bash
java -XX:NativeMemoryTracking=summary \
     -Xms256m -Xmx1g -jar app.jar
~~~

Trong cửa sổ điều tra:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
jcmd <pid> VM.native_memory summary
~~~

NMT giúp thấy **reserved/committed theo subsystem JVM** (Java Heap, Thread, Class, Code, GC...), nhưng **không bao quát tất cả native allocations từ code bên ngoài JVM**. Phải bật NMT từ startup; lệnh baseline/diff có overhead và yêu cầu attach permission. Nếu nghi JNI library, có thể cần native heap profiler/OS metrics riêng.

**Cảnh báo:** Với container memory, còn có OS page cache, memory maps và native buffers. Đừng áp dụng phép tính `RSS − heapUsed = native leak`; đó là một phần chênh lệch từ nhiều category, không mặc định là leak.

## 13. Tải tăng: phân loại cache, session, backlog và batch

### 13.1. Cache warmup hợp lệ

Một cache có thể tăng từ 0 đến 200.000 entries sau khi service khởi động. Nếu `maximumSize`, TTL/expireAfterAccess/Write và eviction chính xác:
- Cache tăng tới plateau có thể là **hành vi mong đợi**.
- Dù cache chiếm nhiều heap, đó có thể là quyết định capacity/latency.
- Nếu service restart, đồ thị lại tăng, cũng không chứng minh leak.

Hãy đo:
- `cache.entries` và approximate `cache.weightBytes`.
- Hit/miss/eviction/expiration rates.
- Workload diversity/unique keys.
- Maximum cache size/weight/TTL.
- Số entries còn sống sau khi chúng đã hết hợp đồng sử dụng.

**Cache không giới hạn** với tập khóa không ngừng tăng có thể vận hành giống leak; giới hạn và eviction cần là yêu cầu cụ thể.

### 13.2. Session/state theo concurrency

Nếu có một object graph cho mỗi active session:
- Heap live nên tương quan với `activeSessions`, số subscription/websocket connections, request duration.
- Khi concurrency tăng, heap live tăng hợp lý.
- Nếu sessions kết thúc nhưng registry vẫn giữ entries, đây là leak ứng dụng (quên cleanup/cancel/unsubscribe).
- Đừng so server có 50k open connections với server 2k connections rồi kết luận JVM 50k leaks.

Có thể tính **bytes retained per active session**, nhưng số này có overhead cố định và nonlinearity; hãy dùng như thước đo sau khi warmup, không như định luật tuyệt đối.

### 13.3. Queue/backlog

Một queue tăng khi consumer chậm là **state thực sự đang còn cần xử lý**, nhưng vẫn cần policy:
- Giới hạn queue length/bytes.
- Backpressure, circuit-breakers và rate limits.
- Deadline/timeout, cancellation, message age.
- Durability/retry semantics nếu không thể drop.
- Worker concurrency và khả năng xử lý burst.

Nếu queue không thể drain, heap sẽ tiếp tục tăng **dù không có lỗi quên xóa**. Đó là vấn đề capacity/throughput, không được bỏ qua chỉ vì “không phải leak”.

### 13.4. Batch lớn và data locality

Tạo một list 1 triệu records trong lúc làm báo cáo có thể tăng used heap mạnh; khi batch kết thúc, list không còn reachable và được GC reclaim theo thời điểm. Một API mới với payload lớn cũng làm tăng average object sizes mà số requests không tăng.

Cần đo **payload bytes per request**, records per batch, concurrency và data shapes bên cạnh QPS. Đôi khi giảm peak memory bằng streaming/bounded batching thay vì chỉ nâng heap max.

## 14. Khi leak thật có thể “trông như tải tăng”

### 14.1. Memory leak tỷ lệ với số requests

Một leak rất nhỏ, ví dụ **2 KiB/request** trong một `static` list, sẽ:
- Tăng nhanh ở peak QPS.
- Tăng chậm vào giờ vắng.
- Có vẻ tương quan tải nhưng vẫn là retention bug.

Cách phân biệt: ở **cùng số lượng active clients và cùng tải hiện tại**, accumulated retained state vẫn tăng theo **cumulative requests processed** hoặc uptime. Đó là dấu hiệu khác với working set theo current concurrency.

### 14.2. Leak theo số unique keys

Một cache không giới hạn có thể giữ mỗi userId hoặc token mới mãi mãi. Khi user base tích lũy:
- Dashboard thấy heap tăng cùng user growth.
- Mỗi object có thể reachable và hợp lệ trong code, nhưng không còn cần thiết sau TTL/lifecycle.
- Tăng `-Xmx` chỉ trì hoãn OOM.

Theo dõi **entry count, key cardinality, oldest age, TTL/eviction**. Đánh giá xem dữ liệu có thật sự phải tồn tại suốt đời process không.

### 14.3. Class loader / metaspace leak

Một ứng dụng hot-redeploy/plugin system có thể tạo class loaders liên tục; nếu thread, cache, static registry hoặc JNI giữ chúng, class metadata có thể không được unload. Biểu đồ **nonheap/metaspace** tăng, không nhất thiết heap used tăng tương ứng.

Để chẩn đoán:
- `jcmd <pid> VM.classloader_stats`.
- `jcmd <pid> VM.metaspace` theo build.
- JFR class loading/unloading.
- Heap dump paths to class loaders/threads nếu cần.

Không nhầm class loading warmup bình thường với leak loader.

### 14.4. Thread/ThreadLocal leak

Thread pool giữ nhiều threads sống lâu. Nếu dùng `ThreadLocal` cho request state nhưng không `remove()` theo lifecycle, dữ liệu có thể bị giữ trong worker threads qua nhiều requests. Cũng có thể có executor queue chứa lambdas/closures giữ payloads.

Nên dùng:

~~~java
// Đoạn minh họa trong một task dùng ThreadLocal:
try {
    requestContext.set(currentRequest);
    handleCurrentRequest();
} finally {
    requestContext.remove();
}
~~~

Không coi mọi ThreadLocal là leak; phải kiểm giá trị được giữ lâu hơn request, root path và policy.

## 15. Lập bảng đo và đọc trend có kiểm soát

### 15.1. Metric matrix nên thu thập

| Nhóm | Chỉ số | Mục đích |
| --- | --- | --- |
| Workload | QPS/RPS, concurrency, latency, active sessions | Giải thích memory demand thật |
| Data sizes | Payload bytes, batch records, active subscriptions | Giải thích size mỗi request |
| Queues | Depth, enqueue/dequeue/s, oldest age, dropped | Phân biệt backlog với leak |
| Caches | Size/weight, cardinality, TTL, evictions | Phân biệt cache plateau với growth không giới hạn |
| JVM heap | `used`, `committed`, `max`, memory pool usage | Phân biệt footprint và capacity |
| GC | Counts/types, before/after occupancy, pauses, allocation stalls | Tìm trend reclaim/gap |
| Allocations | Allocated bytes/s, top allocation sites | Nhận ra churn, không đồng nghĩa retention |
| Retention | Histogram, dump retained size, GC root paths | Xác định object bị giữ |
| Native | Direct/mapped pool, NMT, thread count, metaspace | Tìm tăng ngoài heap |
| OS/container | RSS, memory.current/working set, OOMKill, quota | Phân loại giới hạn hạ tầng |
| Environment | JDK version, GC, -Xms/-Xmx, pod replica, traffic pattern | So sánh đúng điều kiện |

Cùng thời gian quan sát nên có ít nhất một traffic counter và một heap/GC metric. Hai dashboard với cửa sổ time alignment khác nhau có thể tạo kết luận giả.

### 15.2. Chuẩn hóa theo tải

Một bảng ví dụ (số liệu giả định):

| Thời điểm | Active clients | Requests/s | Heap used sau GC tương đương | Cache entries | Nhận định ban đầu |
| --- | ---: | ---: | ---: | ---: | --- |
| T0 sau warmup | 100 | 500 | 180 MiB | 10.000 | Baseline |
| T1 peak | 1.000 | 5.000 | 500 MiB | 40.000 | Có thể hợp lệ vì tải tăng |
| T2 giảm tải | 100 | 500 | 190 MiB | 11.000 | Gần baseline, chưa thấy leak |
| T3 cùng tải với T2 sau 6 giờ | 100 | 500 | 370 MiB | 11.000 | Đáng điều tra retention không thuộc cache |
| T4 sau fix | 100 | 500 | 195 MiB | 11.000 | Bằng chứng cải thiện nếu cùng điều kiện |

**Cách kết luận:**
- T0→T1 chỉ nói heap tăng cùng workload, **không chứng minh leak**.
- T1→T2 cho thấy working set có thể giảm khi tải giảm.
- T2→T3 đáng nghi vì load/cache tương tự mà after-GC footprint tăng.
- T3→T4 sau fix là một phần bằng chứng; vẫn cần object/root evidence và thử lặp lại.

**Không giả định mọi GC tạo ra một after-GC point tương đương**: có collectors xử lý concurrent hoặc partial heap. Ghi rõ event/cycle loại nào và điều kiện thu mẫu.

### 15.3. Test tải có pha

Một protocol đo đáng tin:
1. Warmup ứng dụng, JIT, caches, connections.
2. Pha steady load L với dữ liệu và concurrency ổn định.
3. Pha load 2L hoặc burst, đo expected live state/cache/queue.
4. Trả lại load L và chờ in-flight work/TTL theo policy.
5. Quan sát footprint và GC sau các cycles tương đương.
6. Tiếp tục load L đủ lâu để quan sát retained-size slope theo thời gian.
7. Lặp lại với build sau fix, cùng CPU/heap/GC/JDK.
8. Chụp heap dump có bảo vệ khi slope còn tăng không giải thích được.

Việc chờ “bao lâu là đủ” phải tính từ **request duration, TTL, queue backlog, GC cycle timing và workload**, không chọn một hằng 10 giây cho mọi hệ thống.

## 16. Triệu chứng, giả thuyết và bước kiểm chứng

| Quan sát | Giả thuyết có thể | Bước kiểm chứng |
| --- | --- | --- |
| Heap used tăng theo active users và giảm khi users giảm | Working set hợp lệ | So used after GC với user/session count và retention path |
| Heap used tăng đều theo uptime tại cùng tải | Retention không cần thiết | Histogram theo thời gian, heap dump, dominator/root |
| Heap committed vẫn lớn nhưng used thấp | JVM giữ capacity | So used/committed/heap max, GC logs; không gọi đó là leak |
| RSS tăng còn heap used và committed gần phẳng | Native/direct/metaspace/stacks/mmap | NMT, BufferPoolMXBean, OS native profiler |
| GC chạy dày nhưng after-GC trough ổn định | Allocation rate cao, churn | JFR allocation profile, giảm object tạm nếu cần |
| GC chạy dày và after-GC footprint tăng tại steady load | Retained live growth hoặc GC not catching up | Kiểm GC phases, heap root, backlog, live set |
| Full GC nhiều, old occupancy vẫn cao | Live set gần heap limit hoặc retention/fragmentation | Dump, old-gen details, allocation pressure; không kết luận leak chỉ từ Full GC |
| Queue depth tăng cùng heap used | Producer vượt consumer | Tăng capacity/backpressure, giới hạn queue |
| Cache entries tăng tới limit rồi ổn định | Cache warmup hợp lệ | Check max size/weight, TTL, evictions |
| Cache entries tăng mãi khi unique keys tăng | Unbounded cache | Define cap/TTL/eviction, inspect root |
| Nonheap/metaspace tăng sau redeploy | Class loader retention | VM.classloader_stats, class unload/JFR |
| Process bị OOMKill dù heap used chưa max | Container/native headroom thiếu | Kiểm RSS/NMT/cgroup memory, native allocations |
| Java heap OOME | Heap không đáp ứng allocation tại thời điểm đó | Heap dump, GC logs, load, fragmentation/large objects, live set |
| Heap dump top class là `byte[]` | Bytes chiếm bộ nhớ nhưng nguồn chưa rõ | Dominator tree và paths to GC roots |
| Full GC “giải quyết” tạm thời nhưng RAM lại tăng | Churn, cache hoặc leak tùy vòng đời | Kiểm cùng tải + roots; đừng lặp `System.gc()` để che vấn đề |

**Định lượng evidence:** Tốt nhất là có **(a)** metric trend có traffic context, **(b)** heap dump root path/retained size, **(c)** tái hiện bằng test và **(d)** bằng chứng sau sửa cùng điều kiện.

## 17. Những sai lầm cần tránh

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “RAM tăng tức Java heap leak” | RAM còn native, stacks, code, direct buffers | Tách RSS/heap/nonheap/native |
| “Committed tăng tức objects còn sống tăng” | Committed là capacity JVM giữ | Nhìn `used` và reachable/live trend |
| “Used tăng trong vài phút chắc leak” | Garbage chưa GC, caches warm, load tăng | So tương đương after-GC + traffic |
| “Một mẫu after-GC bằng toàn bộ live set” | Young/concurrent cycles không quét hết như nhau | So đúng GC type/phase; heap dump khi cần |
| “GC nhiều = leak” | Có thể allocation churn cao | Đo allocation rate và retention riêng |
| “GC ít = không leak” | Heap lớn chưa gây pressure, leak nhỏ tích lũy | Xem retained slope dài hạn |
| “Full GC giải quyết leak” | GC không reclaim reachable garbage | Sửa root/owner/lifecycle và policies |
| “`System.gc()` luôn thu sạch heap ngay” | Chỉ là hint, có thể disabled/concurrent | Không dựa vào GC ép trong prod |
| “Allocation stack cho biết ai giữ object” | Allocation site khác retention root | Heap dump dominators/path to roots |
| “Histogram một lần chứng minh leak” | Không có baseline/owner semantics | Lặp lại và correlate traffic |
| “Cache tăng = leak” | Cache bounded warmup có thể cần thiết | Kiểm cap, TTL, evictions |
| “Cache không limit chắc không sao vì GC” | GC không dọn entries còn strong refs | Thêm eviction/size caps |
| “Queue tăng vì tải là bình thường nên bỏ qua” | Backlog có thể unbounded và OOM | Backpressure/capacity/limits |
| “Heap dump an toàn để upload public” | Có secrets/PII/credentials | Phân quyền, mã hóa, retention |
| “JFR OldObjectSample là bằng chứng 100%” | Sampling và root context có giới hạn | Kiểm path, business lifecycle |
| “Heap dump nhẹ, chạy peak lúc nào cũng được” | Impact cao/đĩa lớn/có thể Full GC | Đánh giá SLO, staging/canary |
| “NMT bao hết native memory” | Không theo dõi mọi third-party native allocation | Kết hợp OS/native profiler |
| “Đọc RSS - heap used = native leak” | Chênh lệch nhiều thành phần bình thường | Phân tích committed/NMT/pools |
| “Tăng -Xmx là chữa leak” | Chỉ trì hoãn unbounded retention | Sửa ownership/capacity; cân heap hợp lý |
| “G1, ZGC, Shenandoah có cùng event count” | Semantics/beans khác nhau | Phân tích từng collector theo docs |

## 18. Bài tập có đáp án

**Câu 1.** Heap used tăng 200→500 MiB khi concurrency tăng 5 lần. Có kết luận leak không?

**Đáp án:** Không. Có thể là legitimate working set. So số active sessions/cache/queue và after-GC snapshots cùng mức tải.

**Câu 2.** Khi tải trở về baseline, heap used sau một GC phù hợp về gần ban đầu nhưng committed vẫn cao hơn 150 MiB. Đây có phải leak 150 MiB?

**Đáp án:** Không có bằng chứng. `committed` là capacity mà JVM giữ; không đồng nghĩa retained business objects.

**Câu 3.** Tải và cache size không đổi, nhưng after-GC comparable footprint tăng từng giờ. Điều tra gì đầu tiên?

**Đáp án:** Trend GC/traffic, histogram nhiều thời điểm và heap dump tìm dominators/GC roots, đặc biệt collections/queues/listeners giữ objects vượt vòng đời.

**Câu 4.** Tại sao high allocation rate không có nghĩa leak?

**Đáp án:** Objects có thể chết nhanh và được reclaim; `allocated bytes/s` đo lượng tạo mới, không đo strong references còn giữ.

**Câu 5.** Một `static Map` lưu user data nhưng không xóa khi logout. Vì sao GC không giải phóng?

**Đáp án:** Map vẫn reachable từ static root, entries và values vẫn reachable. Phải xóa đúng lifecycle hoặc có TTL/eviction/weak reference policy phù hợp.

**Câu 6.** Queue tăng từ 100 lên 2 triệu items vì consumer chậm. Có thể nói “không phải memory leak nên không cần xử lý” không?

**Đáp án:** Không. Dù dữ liệu còn cần xử lý, unbounded queue là vấn đề capacity và có thể gây OOM; cần backpressure/caps/recovery policy.

**Câu 7.** `MemoryMXBean` có bao gồm direct buffer payload trong heap used không?

**Đáp án:** Không theo nghĩa Java heap payload. Direct memory nằm ngoài heap; wrapper `ByteBuffer` có thể nằm trên heap. Xem `BufferPoolMXBean`, NMT/OS counters.

**Câu 8.** Vì sao GCHeapSummary “After GC” không phải always-full live set?

**Đáp án:** Có minor/young/concurrent collections và các thời điểm accounting khác nhau. Một số objects unreachable chưa được full-heap traced/reclaimed trong cycle đó.

**Câu 9.** Chỉ nhìn top object `byte[]` trong histogram biết root gây leak là ai chưa?

**Đáp án:** Chưa. Dùng heap dump, retained size và paths to GC roots để tìm owner/collection/closure giữ arrays.

**Câu 10.** `jcmd <pid> GC.heap_dump` có nên chạy mỗi giây trên production không?

**Đáp án:** Không. Lệnh có impact cao, dump lớn và có thể chứa secrets; dùng có kiểm soát, đúng thời điểm và policy.

**Câu 11.** Sau `System.gc()` một lần, used không giảm. Có chứng minh leak không?

**Đáp án:** Không. `System.gc()` là hint, có thể bị disable hoặc collector đang chạy concurrent; phải xem logs/cycles và root evidence.

**Câu 12.** RSS tăng còn used heap ổn định. Nên xem gì?

**Đáp án:** Committed heap, direct/mapped buffer pools, nonheap/metaspace, thread stacks, NMT và OS-native allocations; cả cgroup memory limits.

**Câu 13.** Một service có cache LRU cap 50.000 entries, sau 1 giờ warmup cache đạt 49.800 và giữ ổn định. Có đủ bằng chứng leak không?

**Đáp án:** Không. Đó có thể là bounded cache bình thường. Đo eviction/TTL/weight và tác động RAM/SLO trước khi điều chỉnh.

**Câu 14.** Có một object root giữ 100 MiB retained size nhưng đó là session đang hoạt động. Có tự coi là leak không?

**Đáp án:** Không. Retained size chỉ cho thấy ownership; cần chứng minh session/object không còn cần thiết mà vẫn bị giữ.

**Câu 15.** Sau fix một listener không unsubscribe, số retained subscriptions trở lại ổn định ở cùng tải và heap after-GC cũng ổn định. Đánh giá?

**Đáp án:** Đây là bằng chứng tốt cho fix, nhất là khi dump/root paths và reproduction cùng điều kiện xác nhận. Vẫn theo dõi một khoảng đủ dài để tránh kết luận quá sớm.

## 19. Checklist vận hành thực tế

- [ ] Đã xác định chính xác metric đang tăng: heap used, committed, max, nonheap, direct, RSS hay cgroup.
- [ ] Có time series cùng timestamps của concurrency, RPS, active sessions, cache entries, queue depth và batch sizes.
- [ ] Có baseline sau warmup với workload và GC/JDK/heap settings rõ ràng.
- [ ] So sánh các samples **sau GC cùng loại/phase** hoặc dùng phân tích heap dump, không ghép bừa.
- [ ] Kiểm sự kiện traffic tăng, deployment, JVM patch, config cache/TTL/size, autoscale và thay đổi data shape.
- [ ] Biết objects/collections nào giữ bytes, và retained size/GC roots tương ứng.
- [ ] Không chạy `System.gc()` lặp lại như một phương án “cứu” memory leak.
- [ ] Nếu dùng `jcmd`/heap dump đã dự trù pause, disk, quyền và data privacy.
- [ ] Nếu nghi native, đã xem NMT/direct pools/OS metrics trước khi tăng heap.
- [ ] Nếu cache/queue hợp lệ tăng quá sức chứa, có backpressure/TTL/eviction/capacity plan.
- [ ] Fix được kiểm chứng bằng load test cùng điều kiện + histogram/dump/GC trend sau fix.
- [ ] Alert không chỉ dựa vào RSS/committed; có heap live trend và thời gian/threshold phù hợp.

## 20. Ghi nhớ

- **Memory leak Java:** Object còn reachable nhưng không còn cần theo vòng đời nghiệp vụ.
- **Heap tăng do tải:** Active working set/session/cache/queue có thể lớn hơn một cách hợp lệ.
- **Heap committed tăng không phải leak:** JVM có thể giữ memory để tái sử dụng sau khi used/live giảm.
- **After-GC trend hữu ích nhưng cần đúng ngữ cảnh:** GC type, phase, traffic, collector và warmup.
- **Allocation nhiều khác retention nhiều:** Churn cao có thể tạo GC pressure mà không bị leak.
- **Histogram giúp tìm class, dump/dominator/root tìm ai giữ:** Cần chứng minh object không còn cần.
- **RSS tăng khi heap phẳng:** Điều tra native/direct/metaspace/threads, không ép kết luận Java heap leak.
- **Đo theo tải và theo thời gian**, tìm root, sửa đúng lifecycle; không chữa unbounded retention bằng cách tăng heap vô hạn.

## 21. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 25 — Troubleshoot Memory Leaks: histogram, heap dump, JFR và GC roots](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshooting-memory-leaks.html)
- [Oracle Java SE 25 — Diagnostic Tools: jcmd, JMC, native memory tracking](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 25 — `jcmd` command: GC.class_histogram, GC.heap_dump, VM.native_memory](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)
- [Oracle Java SE 25 — `MemoryUsage` (used, committed, max)](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html)
- [Oracle Java SE 25 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Oracle Java SE 25 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [Oracle Java SE 25 — `BufferPoolMXBean` cho direct/mapped](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Oracle Java SE 25 — JFR `Recording` và `RecordingFile`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle Java SE 25 — G1 GC Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html)
- [OpenJDK — JDK Flight Recorder](https://openjdk.org/projects/jmc/)
