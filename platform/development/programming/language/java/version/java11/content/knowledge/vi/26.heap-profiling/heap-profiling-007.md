# Heap profiling Java 11+: tương tác với GC và giới hạn suy luận rò rỉ bộ nhớ

## 1. Câu hỏi cần trả lời trước khi kết luận "memory leak"

Bạn bật Java Flight Recorder (JFR) và thấy ứng dụng tạo nhiều đối tượng, heap-used tăng, thậm chí GC diễn ra thường xuyên. **Những hiện tượng đó không tự động có nghĩa ứng dụng bị memory leak**.

Để chẩn đoán đúng cần phân biệt ít nhất bốn câu hỏi:

1. **Allocation:** Ứng dụng đang tạo bao nhiêu đối tượng/byte trong một đơn vị thời gian, tạo ở class/method/thread nào?
2. **Reachability và retention:** Những object nào **vẫn còn được tham chiếu** sau một khoảng thời gian và các pha GC phù hợp?
3. **GC:** JVM đã thu gom loại rác nào, ở pha nào, giải phóng bao nhiêu heap và mất bao lâu? Liệu số đo trước/sau GC có so sánh được?
4. **Leak:** Có đối tượng **đáng lẽ không còn cần thiết theo vòng đời nghiệp vụ** nhưng vẫn bị giữ bởi một chuỗi tham chiếu không mong muốn, khiến retained memory có xu hướng tăng lâu dài không?

**Một allocation hotspot không nhất thiết là leak. Một object sống qua GC chưa chắc là leak. Heap tăng trong một thời điểm chưa chứng minh leak.** Mục tiêu của heap profiling là tìm bằng chứng có thể kiểm tra được, không biến một biểu đồ đơn lẻ thành kết luận.

Bài dùng **Java 11+**, JFR (`jdk.jfr`), `jdk.jfr.consumer` và `java.lang.management`. Các ví dụ biên dịch được bằng `javac --release 11` và sử dụng những event types/API có trong Java 11. Những sự kiện được thêm ở JDK mới hơn được chỉ rõ về phiên bản để không làm sai Special Note: chỉ dùng kiến thức còn áp dụng.

---

## 2. Mô hình: allocation → reachability → GC → retained set

```text
             Mã ứng dụng / JVM
                    |
                    v
            Object allocations
                    |
            +-------+-------+
            |               |
            v               v
       Tạm thời        Vẫn được tham chiếu
   (không còn cần)   (đúng hoặc sai mục đích)
            |               |
            +-------+-------+
                    |
                    v
             GC cycle/phases
                    |
           +--------+--------+
           |                 |
           v                 v
    Có thể reclaim      Object còn live
    những object        và tiếp tục được giữ
    không reachable             |
                                 v
                       Có phù hợp vòng đời?
                         /            \
                       Có             Không
                        |               |
                 Retention hợp lệ   Leak candidate
```

### Allocation không bằng retention

Một API có thể tạo 100 MB objects/giây rồi bỏ hết tham chiếu sau 200 ms. Allocation rate cao, nhưng **live set ổn định** nếu collector theo kịp và objects không bị giữ quá lâu.

Ngược lại, một cache tạo thêm chỉ 200 KB/phút nhưng không bao giờ evict entries có thể gây tăng retained memory trong nhiều ngày. **Leak chậm thường ít nổi bật trong allocation samples**.

### GC không "quét sạch tất cả object"

Các GC collectors hiện đại có nhiều thuật toán và pha khác nhau: young collection, concurrent mark, mixed/full collection, compaction hoặc hoạt động được phân phối theo nhiều threads. Một sự kiện GC có thể chỉ xét một phần heap hoặc diễn ra đồng thời với ứng dụng.

Vì vậy, **heap used sau bất kỳ GC event nào không tự động là tổng live objects chính xác của toàn heap**. Chỉ sử dụng các điểm đo so sánh được khi biết GC type, phase, workload, JVM version và điều kiện đo.

### Định nghĩa làm việc của memory leak trong Java

Một **Java heap memory leak** là retention không mong muốn: object vẫn reachable bởi một hoặc nhiều GC roots (hoặc cơ chế giữ sống hợp lệ về mặt JVM), mặc dù ứng dụng không còn cần dùng nó theo vòng đời nghiệp vụ.

Ví dụ:

- Cache không có eviction/TTL.
- Static collection tích lũy entry theo request không giới hạn.
- Listener/callback đăng ký nhưng không gỡ khi đóng phiên.
- ThreadLocal giữ dữ liệu của request khi thread được tái sử dụng.
- Queue backlog tăng vô hạn vì producer nhanh hơn consumer.
- Class loader hoặc task references bị giữ sau redeploy.
- Session/user state bị giữ sau logout hết hạn.

Cũng có trường hợp **retention hợp lệ** như cache warm-up, dữ liệu phục vụ phiên đang hoạt động hoặc hàng đợi xử lý tạm thời. Phải kiểm tra với owner của state và SLA nghiệp vụ mới kết luận đúng.

## 3. Các đại lượng thường bị nhầm: used, committed, max, allocation và live set

| Đại lượng | Ý nghĩa | Có chứng minh leak? |
| --- | --- | --- |
| **Allocated bytes / allocation rate** | Lượng bộ nhớ mới được cấp cho objects trong khoảng thời gian | Không; nhiều object rất ngắn đời |
| **Heap used** | Lượng Java heap được JVM báo đang dùng ở một thời điểm | Không, vì GC có thể chưa reclaim hoặc collector chạy đồng thời |
| **Heap committed** | Lượng memory đã JVM cam kết cấp cho Java heap | Không; JVM có thể giữ committed pages dù object đã chết |
| **Heap max** | Giới hạn tối đa Java heap do VM cung cấp, thường liên quan `-Xmx` | Không phải retained size |
| **Post-GC used/live-set approximation** | Heap occupancy sau một phép collection phù hợp | Là tín hiệu xu hướng, không phải lời kết tội |
| **Retained size của một object** | Lượng bộ nhớ sẽ được giải phóng nếu loại object cùng các descendants mà chỉ nó giữ | Phụ thuộc graph và dominator; cần heap analysis |
| **Native/RSS memory** | Bộ nhớ process ngoài/bao gồm Java heap: direct buffers, metaspace, code cache, stacks, malloc, mappings... | Không thể suy ra chỉ từ JFR heap events |

**Đặc biệt:** `-Xmx256m` là giới hạn heap, **không** phải RSS của JVM chỉ được phép bằng 256 MiB. Nếu RSS tăng nhưng heap after-GC tương đối ổn định, cần xét native memory, off-heap buffers, thread stacks hoặc metaspace thay vì mặc định cho là heap leak.

### `MemoryMXBean`

Trong Java:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryUsage usage = ManagementFactory
        .getMemoryMXBean()
        .getHeapMemoryUsage();

System.out.println("used=" + usage.getUsed());
System.out.println("committed=" + usage.getCommitted());
System.out.println("max=" + usage.getMax());
```

Đây là **đoạn code trong một phương thức**, không phải một chương trình độc lập. Các giá trị **thay đổi theo runtime và thời điểm**, nên không có một stdout cố định.

- `getUsed()` là một snapshot thống kê, không phân loại "đang còn cần" với "đã hết cần nhưng chưa dọn".
- `getCommitted()` là lượng memory cam kết cho heap, không đồng nghĩa số byte object còn sống.
- `getMax()` có thể là `-1` nếu JVM không xác định giới hạn.
- Các số này không được chụp atomically cùng tất cả JFR GC events ở một thời điểm duy nhất; cần chú ý timestamp khi kết hợp.

## 4. GC events liên quan đến heap profiling trong JFR Java 11

### 4.1. Những sự kiện phổ biến

| JFR event type | Thuộc tính đáng quan tâm | Tác dụng |
| --- | --- | --- |
| `jdk.GarbageCollection` | GC ID, tên/cause, duration/start time tùy schema | Khi nào có GC và diễn ra trong bao lâu |
| `jdk.GCHeapSummary` | `gcId`, `when`, `heapUsed`, `heapSpace` | Heap occupancy **Before GC / After GC** |
| `jdk.ObjectAllocationInNewTLAB` | `objectClass`, `allocationSize`, `tlabSize`, thread/stack | Những allocation liên quan TLAB refresh |
| `jdk.ObjectAllocationOutsideTLAB` | `objectClass`, `allocationSize`, thread/stack | Những allocation trực tiếp ngoài TLAB |
| `jdk.ThreadAllocationStatistics` | Thread và thống kê bytes allocated | Phân tích allocation pressure theo thread |
| `jdk.OldObjectSample` | Các sample object sống lâu, age, retention/reference path khi thu | Tìm **ứng viên** retention bất thường |

Tên fields có thể khác tùy event/JDK và provider. Khi xây analyzer tổng quát, **kiểm tra `RecordedEvent.getEventType()` và `getFields()`** trước khi lấy `getLong(...)` hoặc `getClass(...)`.

`jdk.ObjectAllocationSample` là event useful trên JDK hiện đại, dùng `weight` cho weighted sampling. Nhưng **event này được giới thiệu trong JDK 16**, không phải event baseline Java 11. Không viết hướng dẫn Java 11 mặc định bật `jdk.ObjectAllocationSample` rồi chờ chắc chắn có dữ liệu.

### 4.2. `jdk.GarbageCollection` chỉ ghi "một GC đã diễn ra"

Event này hữu ích để xem cadence và duration của các lần GC. Nhưng nó không chứng minh:

- mỗi GC đều dọn sạch toàn heap;
- tất cả object allocations trước GC đều chết;
- mỗi lần GC có một lượng byte được reclaimed giống nhau;
- GC pause tăng đồng nghĩa leak (có thể do pressure, heap size, CPU, I/O, GC configuration).

**Không suy ra leak từ GC count tăng**. Hệ thống có throughput cao với nhiều short-lived objects có thể có nhiều GC mà live set vẫn ổn định.

### 4.3. `jdk.GCHeapSummary`: Before/After cần ghép đúng GC ID

Theo runtime HotSpot thử nghiệm, event có các fields:

```text
startTime
gcId
when
heapSpace
heapUsed
```

Trong đó:

- `gcId`: ID của GC cycle/collection được báo.
- `when`: nhãn trạng thái như `Before GC` và `After GC`.
- `heapUsed`: byte Java heap used theo cách JVM thu thập metadata của event.
- `heapSpace`: cấu trúc chứa thông tin heap space; không phải một `long` để trừ trực tiếp.

Một cặp có thể được mô hình hóa:

```text
jdk.GCHeapSummary(gcId=7, when="Before GC", heapUsed=80 MiB)
jdk.GCHeapSummary(gcId=7, when="After GC",  heapUsed=45 MiB)
                           |
                           v
          observed delta for GC ID 7 = -35 MiB
```

**Ví dụ 80/45 MiB chỉ minh họa, không phải một output từ JVM cụ thể.** Dữ liệu before/after so sánh được khi đúng GC ID và schema; dữ liệu khác thời điểm hoặc từ GC cycles khác nhau không được trừ như một cặp.

- `heapUsedAfter < heapUsedBefore`: sau pha collection, reported occupancy giảm; không cho biết objects được giải phóng thuộc request nào.
- `heapUsedAfter >= heapUsedBefore`: không đủ để kết luận leak; một số collector/concurrent events hoặc các phép đo/hoạt động của mutator có thể làm before/after khác kỳ vọng.
- Một `After GC` sau **young collection** không phải số đo live set chuẩn hóa của **old generation**.
- Những GC algorithms/versions khác nhau có semantic footprint khác; cần đọc GC configuration và event type metadata cùng file.

## 5. TLAB: vì sao JFR allocation events không phải "log mọi cấp phát"?

### 5.1. TLAB là gì?

**Thread-Local Allocation Buffer (TLAB)** là vùng trong heap mà một thread sử dụng để cấp phát nhiều object nhỏ hiệu quả, giảm tranh chấp allocation trên shared memory.

```text
Thread A                    Thread B
  |                           |
  +-- TLAB A                  +-- TLAB B
       | alloc Object 1          | alloc Object X
       | alloc Object 2          | alloc Object Y
       | alloc Object 3          | ...
       |
       +-- khi cần TLAB mới
              v
      JFR ObjectAllocationInNewTLAB event (nếu enabled)
```

Trong Java 11, `jdk.ObjectAllocationInNewTLAB` có bản chất ghi **một số sự kiện liên quan đến lần lấy TLAB mới**, không phải một event cho **mỗi** object được tạo trong TLAB đó. Tương tự, `ObjectAllocationOutsideTLAB` phản ánh allocations bên ngoài TLAB theo cơ chế event được runtime hỗ trợ; không được suy diễn hai loại events cộng lại luôn là **census hoàn chỉnh** về số object.

### 5.2. Đọc fields đúng

Một event TLAB điển hình có thể có:

- `objectClass`: class của object kích hoạt allocation event.
- `allocationSize`: size của allocation đang được báo.
- `tlabSize`: size của TLAB được cấp trong context của event.
- `eventThread` và optional stack trace: thread/call site liên quan.

**`tlabSize` không phải kích thước của một object**. Cộng `tlabSize` để ước lượng allocation pressure dựa trên TLAB refill là một kỹ thuật thống kê/heuristic cần hiểu collector và event semantics; đừng cộng `allocationSize` từ những events thưa rồi tuyên bố đã đếm đủ mọi allocation.

Ngoài ra, compiler JIT có thể loại bỏ một số allocations không escape, hoặc thay đổi object layout/inline behavior. Kết quả heap profiling nên được hiểu trong điều kiện JIT, JVM và workload thực tế, không phải số tuyệt đối bất biến giữa hai builds.

### 5.3. Không lẫn allocated type với nơi tạo ra

Một `ObjectAllocation...` event có `objectClass=byte[]` nhưng stack trace có thể đi qua:

```text
com.example.ReportService.render()
java.util.ArrayList.add()
...
```

Object type trả lời **"cái gì được tạo?"**. Allocation site trả lời **"đường code nào gây ra cấp phát?"**. Để giảm pressure, hãy quan tâm **call site đủ chi tiết** và tần suất/trọng số, không chỉ top class.

### 5.4. `ThreadAllocationStatistics` hữu ích nhưng cũng có phạm vi

Thống kê allocations theo thread giúp tìm **nguồn phát sinh allocation**, không chỉ ra object nào còn giữ lâu. Với worker pools, một thread có thể xử lý hàng trăm request nên lượng allocation của thread **không map 1:1** với user request hoặc tenant. Cần correlation IDs/custom events nếu muốn liên hệ tới chức năng nghiệp vụ.

## 6. `jdk.ObjectAllocationSample` trên JDK 16+ — hiểu đúng sự khác biệt phiên bản

Oracle JDK 16 release notes giới thiệu `jdk.ObjectAllocationSample` như một event có **low-overhead allocation sampling**, được bật theo cấu hình `default`/`profile` của các bản JDK tương ứng. Nó có `weight` để phân tích **statistical allocation pressure**.

**Đây là kiến thức hiện hành nhưng không tồn tại trong Java 11 baseline.** Nếu một analyzer phải chạy Java 11, hãy dùng những event types mà JDK 11 thực tế cung cấp. Nếu runtime phát JFR là JDK mới hơn, có thể thêm một nhánh logic:

```text
JFR do Java 11 phát:
  ObjectAllocationInNewTLAB / ObjectAllocationOutsideTLAB
  ThreadAllocationStatistics / GCHeapSummary

JFR do JDK 16+ phát và được cấu hình phù hợp:
  ObjectAllocationSample (weight-aware)
  và các GC/old-object events vẫn có ý nghĩa
```

**Weight của sample không phải `byte[]` retained size.** Một object được sampled khi cấp phát có thể chết ngay trong kỳ GC tiếp theo. Bên cạnh đó, sample frequency/weight cần được giải thích theo thuật toán của runtime, không dùng `samples.count()` như tổng số object trong heap.

## 7. Old object sampling: tín hiệu mạnh hơn về retention, nhưng vẫn chưa phải kết luận

### 7.1. `jdk.OldObjectSample` hướng tới đối tượng sống lâu

Một event `jdk.OldObjectSample` thường chứa metadata liên quan:

- object/class đang được sampling;
- `allocationTime`: khi object đó được ghi nhận cấp phát;
- `objectAge`: khoảng thời gian sống của object tới lúc sample;
- `lastKnownHeapUsage`: thống kê heap occupancy liên quan lần quan sát;
- stack trace của allocation khi có cấu hình phù hợp;
- đường tham chiếu về **GC root** khi được yêu cầu và có thể thu;
- thông tin event thread liên quan theo event schema.

Ví dụ một `HashMap$Node` sống lâu và có chuỗi tham chiếu:

```text
GC Root
   |
   v
static Application.ACTIVE_SESSIONS
   |
   v
HashMap
   |
   v
HashMap$Node
   |
   v
SessionContext
   |
   v
byte[] / payload
```

Nếu nghiệp vụ yêu cầu xóa session sau khi hết hạn nhưng map không bao giờ remove, đây là **ứng viên leak có lời giải thích**. Tuy nhiên, nếu map vẫn chứa các sessions hợp lệ, thì đó là retention đúng yêu cầu.

**Path to root trả lời "vì sao JVM còn giữ object reachable?"**, không trực tiếp trả lời "nghiệp vụ có còn cần object đó không?". Câu trả lời thứ hai nằm trong business lifecycle, TTL/eviction policy và quan sát thực tế.

### 7.2. Không có sample chưa chứng minh không leak

Old object sampling không bảo đảm bắt gặp mọi object; một leak chậm hoặc object nhỏ ít có khả năng xuất hiện trong sample window. Một sample đơn lẻ không chứng minh retained size tổng thể của mọi object thuộc class đó.

Những điều có thể xảy ra:

- Object chỉ được tạo hiếm khi → không có sample.
- Sampled object sống lâu do legitimate cache.
- Root path không được thu vì chưa bật tùy chọn hoặc runtime không hỗ trợ.
- Recording được dump trước thời điểm cần thiết.
- Class đã xuất hiện trong sample nhưng chính một allocation site khác mới gây leak.

Một tiêu chuẩn thận trọng là **tìm nhiều bằng chứng độc lập**: retained set sau collections phù hợp tăng liên tục, số entries/lifetime sai, root path dẫn tới owner không mong muốn, kiểm thử sửa logic làm trend trở về ổn định.

### 7.3. Lấy path-to-GC-roots có chi phí

Trên HotSpot/JDK có hỗ trợ, có thể dùng lệnh chẩn đoán:

```bash
jcmd <PID> JFR.dump filename=possible-leak.jfr path-to-gc-roots=true
```

**Thay `<PID>` bằng process ID được phép điều tra.** Đây là ví dụ quản trị tiến trình, không phải một lệnh cần thực thi trong demo Java chạy offline.

Theo tài liệu JFR, thu **paths to GC roots** có thể tốn kém, có pause/overhead đáng kể và **mặc định thường tắt**. Chỉ kích hoạt có kiểm soát khi có nghi vấn leak, trên process được phép, tại thời điểm phù hợp; không bật liên tục trên mọi dịch vụ.

Tùy JDK và cấu hình, cần bật `jdk.OldObjectSample` hoặc dùng profile settings để có các sample và allocation stacks. Đừng nhầm `jdk.OldObjectSample` với việc phân tích heap dump đầy đủ.

**Khác biệt API:** `Recording.dump(Path)` trong Java 11 **không có tham số `path-to-gc-roots`**. Để sử dụng tùy chọn dump GC-root paths cần công cụ/thiết lập chính thức phù hợp runtime như `jcmd JFR.dump`; không tự bịa phương thức `recording.dump(path, true)`.

## 8. GC roots và retained graph: kỹ thuật xác định nguyên nhân

GC roots có thể gồm các tham chiếu từ thread stacks, static fields, JNI references và những runtime roots khác. Một object còn reachable từ GC roots thường sẽ được giữ lại theo quy tắc của collector/loại reference liên quan.

### 8.1. Một root path không phải toàn bộ object graph

`jdk.OldObjectSample` chỉ đưa ra một hoặc một số paths/chains theo sampling và runtime. Nó không liệt kê đầy đủ **mọi** object tham chiếu đến candidate. Vì vậy, nếu cần tính **retained size, dominator tree, incoming references** chính xác hơn, hãy cân nhắc heap dump + profiler có khả năng phân tích graph (ví dụ Eclipse Memory Analyzer) trong môi trường bảo mật phù hợp.

### 8.2. Shallow size vs retained size

Giả sử một `HashMap` chỉ chiếm một số byte nhỏ ở shallow footprint nhưng giữ hàng trăm nghìn entries và arrays. Tổng memory bị giữ gián tiếp có thể lớn hơn nhiều so với `HashMap` object.

- **Shallow size:** size của chính object, không tính transitively reachable descendants.
- **Retained size:** ước lượng memory có thể được giải phóng nếu loại object khỏi graph (theo dominator/reference model).
- **Allocation size:** size tại một allocation event.
- **Object count:** số instance trong một tập/snapshot; không nói đủ số byte hoặc nghiệp vụ có cần nữa không.

Nếu muốn phát hiện root cause, chỉ xem **top shallow size** thường kém hữu ích hơn các retained paths có ý nghĩa.

### 8.3. Reference semantics cần được hiểu

Không phải mọi reference đều là strong reference:

- `WeakReference`: không giữ referent sống chỉ nhờ weak reference.
- `SoftReference`: collector có chính sách reclaim theo áp lực, không bảo đảm lúc nào cũng được giải phóng ngay.
- `PhantomReference`: cơ chế notification/cleanup, không dùng để giữ object sống như strong reference.
- Cleaner/finalization/reachability details có thể gây độ trễ cleanup; đừng dùng một thời điểm GC đơn lẻ để khẳng định leak.
- Direct/off-heap buffers có phần Java object trên heap và phần native memory ngoài heap; cần đánh giá đúng nguồn tăng bộ nhớ.

**Đừng dùng `System.gc()` như một phép chứng minh rằng mọi unreachable object đã bị giải phóng.** Đây là request/hint tới JVM; hiệu quả có thể phụ thuộc options, collector và trạng thái môi trường.

## 9. Xu hướng post-GC heap: khi nào đáng nghi, khi nào chưa?

### 9.1. Các hình dạng thường gặp

```text
A. Allocation lớn, live set ổn định

heap used:
          /|   /|   /|   /|
         / |  / |  / |  / |
        /  |_/  |_/  |_/  |_
           ^    ^    ^
          GC   GC   GC
post-GC baseline gần ổn định

B. Retention tăng dần, cần điều tra

heap used:
             /|        /|
           /  |      /  |
         /    |    /    |
       /      |  /      |
     _/       |_/       |_
post-GC baseline cao dần qua các collections so sánh được

C. Cache warm-up rồi ổn định

heap used:
        /|\ /|\ /|\ /|
       / | / | / | / |
      /  |/  |/  |/  |
baseline tăng lúc warm-up, sau đó plateau
```

Các biểu đồ ASCII là **minh họa tư duy**, không phải dữ liệu đo từ một JVM cụ thể.

### 9.2. Kiểm tra nhiều chu kỳ và cùng điều kiện

Muốn kết luận có bằng chứng retention bất thường:

1. Chạy trong khoảng thời gian đủ dài để workload lặp lại.
2. Ghi lượng request, concurrent sessions, cache entries, active jobs, queue depth hoặc metric nghiệp vụ tương ứng.
3. Lấy các điểm post-GC **có ý nghĩa so sánh**: cùng collector/version, cùng loại collections thích hợp, tải/số sessions tương đương nếu có thể.
4. Tính trend qua nhiều điểm, không chỉ trước/sau một GC.
5. Kiểm tra warm-up và cache max/TTL.
6. Tìm object classes/roots có retention tăng đồng thời.
7. Thử thay đổi một cơ chế giữ tham chiếu, rồi chạy lại cùng workload để xem trend có biến mất không.

**Ngay cả trend tăng nhiều lần cũng là dấu hiệu cần điều tra, không phải proof độc lập.** Một số hệ thống cố ý giữ index/caches đến giới hạn định trước. Cần biết kỳ vọng vòng đời.

### 9.3. Đừng coi GC count tăng là nguyên nhân duy nhất

GC count/cpu time có thể tăng vì:

- allocation rate tăng;
- heap size nhỏ với throughput lớn;
- nhiều temporary objects;
- promotion pressure/fragmentation;
- container memory limits;
- collectors/concurrency/safepoint behavior;
- retention không mong muốn.

Một leak có thể làm GC ngày càng thường xuyên vì heap còn lại cho allocations giảm, nhưng đây chỉ là **một trong nhiều giải thích**.

## 10. Trình tự điều tra đề xuất: từ triệu chứng đến nguyên nhân

### Bước 1 — Xác định vấn đề đo ở đâu

- RSS của process tăng hay Java heap-used tăng?
- Memory pools trên heap, metaspace hay native/off-heap?
- Có `OutOfMemoryError: Java heap space` hay `Direct buffer memory` hay chỉ memory RSS gần container limit?
- Thời điểm nào latency, CPU, GC pause, allocation rate hoặc request backlog biến động?

Nếu heap sau GC ổn định mà RSS tăng, chuyển hướng sang native memory và thread stack/direct buffer profiling phù hợp. Không dùng mỗi `jdk.GCHeapSummary` để kết luận về native memory leak.

### Bước 2 — Bắt đầu JFR với overhead phù hợp

Dùng cấu hình JFR `default` cho giám sát thông thường hoặc `profile` trong khoảng được đánh giá. Chỉ bật allocation/stack event types cần thiết và giới hạn thời lượng/dung lượng ghi.

JFR có thể cung cấp những event snapshots giúp điều tra, nhưng **không phải audit log exactly once**. Sampling/buffering/retention/JIT có thể khiến một số allocations không được quan sát.

### Bước 3 — So sánh heap và GC events

Nhóm `jdk.GCHeapSummary` theo `gcId` và `when`, đọc các pha trước/sau GC. Đồng thời xem `jdk.GarbageCollection` để biết GC duration/type/cause, và đối chiếu timeline với throughput, heap size, warm-up.

Không so một `After GC` từ young collection với một kết quả sau full collection rồi gọi chênh lệch đó là leak rate.

### Bước 4 — Tìm allocation hotspots

Tùy JDK:

- Java 11: dùng `jdk.ObjectAllocationInNewTLAB`/`OutsideTLAB` và `ThreadAllocationStatistics`.
- JDK 16+: có thể dùng `jdk.ObjectAllocationSample` nếu runtime/config hỗ trợ.
- Xem class, method và thread; ghi rõ event semantics, sampling và weights.

### Bước 5 — Tìm retention candidates

Nếu post-GC baseline tăng, ưu tiên `OldObjectSample`/root paths khi có thể và kiểm tra object age, graph ownership. Khi cần phân tích đầy đủ, lấy heap dump có kiểm soát. Một object sống lâu vì thuộc cache có TTL có thể hợp lệ, nhưng một listener không gỡ sau session close là một candidate đáng điều tra.

### Bước 6 — Kiểm chứng bằng thử nghiệm lặp lại

Xây hypothesis cụ thể:

```text
"Hàng đợi pendingTasks giữ references đến completed futures
 sau khi worker xử lý xong."

Bằng chứng cần kiểm:
- queue depth theo thời gian
- số finished futures thực sự bị giữ
- path từ GC root đến collection và futures
- mức tăng sau các GC cycles so sánh được
- workload A/B hoặc fix cleanup/eviction
```

Sau fix, cùng workload phải cho **retained set/counters ổn định hơn**, và không gây regression về correctness/latency. Đây mới là một kết luận kỹ thuật có thể bảo vệ.

## 11. Ví dụ Java 11 hoàn chỉnh: thu JFR + GC + allocation + checkpoint heap

Chương trình dưới đây tạo một recording offline và **chủ động ghi bốn custom JFR events** đại diện các checkpoint của workload. Nó cũng bật `jdk.GarbageCollection`, `jdk.GCHeapSummary` và hai event TLAB có trong Java 11.

**Các mục tiêu thực hành:**

- Biết `MemoryMXBean.getHeapMemoryUsage().getUsed()` là snapshot, không phải live-set proof.
- Nhìn thấy JFR ghi nhận phases `baseline`, `temporary`, `retained`, `afterGcRequest`.
- Phân biệt các allocations tạm thời với **64 byte arrays** được giữ qua một danh sách mạnh.
- Hiểu `System.gc()` chỉ là **hint**, không phải lệnh bắt GC tuyệt đối.
- Đọc file `.jfr`, đếm đúng custom events và quan sát số events của JVM.
- Không kết luận leak chỉ từ bài thử này: danh sách `held` được cố tình giữ đến cuối để minh họa retention hợp lệ theo mục tiêu demo.

**Lưu file:** `HeapGcEvidenceDemo.java`.

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class HeapGcEvidenceDemo {
    @Name("demo.HeapCheckpoint")
    @Label("Heap Checkpoint")
    public static class HeapCheckpoint extends Event {
        public String phase;
        public long heapUsedBytes;
        public long collectorCount;
        public int retainedArrays;
    }

    private static long collectionCount() {
        long total = 0;
        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = gc.getCollectionCount();
            if (count >= 0) {
                total += count;
            }
        }
        return total;
    }

    private static void checkpoint(String phase, int retained) {
        HeapCheckpoint e = new HeapCheckpoint();
        e.phase = phase;
        e.heapUsedBytes =
                ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage()
                        .getUsed();
        e.collectorCount = collectionCount();
        e.retainedArrays = retained;

        if (e.isEnabled()) {
            e.commit();
        }
    }

    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("jfrAvailable=false");
            return;
        }

        Path file =
                Files.createTempFile("jfr-heap-gc-", ".jfr");

        List<byte[]> held = new ArrayList<>();
        long checksum = 0;

        try {
            try (Recording r = new Recording(
                    Configuration.getConfiguration("default"))) {

                r.setToDisk(true);
                r.setMaxAge(Duration.ofMinutes(3));
                r.setMaxSize(32L * 1024 * 1024);

                r.enable(HeapCheckpoint.class)
                        .withoutThreshold()
                        .withoutStackTrace();

                r.enable("jdk.GarbageCollection");
                r.enable("jdk.GCHeapSummary");
                r.enable("jdk.ObjectAllocationInNewTLAB");
                r.enable("jdk.ObjectAllocationOutsideTLAB");

                r.start();

                checkpoint("baseline", held.size());

                // Temporary allocations: không giữ references sau vòng lặp.
                for (int i = 0; i < 8000; i++) {
                    byte[] temporary = new byte[4096];
                    temporary[0] = (byte) i;
                    checksum += temporary[0];
                }

                checkpoint("temporary", held.size());

                // Giữ references chủ động để quan sát retention.
                for (int i = 0; i < 64; i++) {
                    byte[] bytes = new byte[64 * 1024];
                    bytes[0] = (byte) i;
                    held.add(bytes);
                }

                checkpoint("retained", held.size());

                System.gc(); // Chỉ là GC request/hint.
                Thread.sleep(250L);

                checkpoint("afterGcRequest", held.size());

                r.stop();
                r.dump(file);
            }

            List<RecordedEvent> events =
                    RecordingFile.readAllEvents(file);

            List<RecordedEvent> own = events.stream()
                    .filter(e -> "demo.HeapCheckpoint".equals(
                            e.getEventType().getName()))
                    .collect(Collectors.toList());

            System.out.println(
                    "checkpointCount=" + own.size());

            System.out.println("phases=" +
                    own.stream()
                            .map(e -> e.getString("phase"))
                            .collect(Collectors.joining(",")));

            System.out.println(
                    "retainedCount=" + held.size());

            System.out.println("retainedArrayBytes=" +
                    (long) held.size() * 64 * 1024);

            System.out.println("hasHeapMeasurements=" +
                    own.stream().allMatch(e ->
                            e.getLong("heapUsedBytes") >= 0));

            System.out.println("gcCountNonDecreasing=" +
                    (own.get(3).getLong("collectorCount") >=
                     own.get(0).getLong("collectorCount")));

            long gcEvents = events.stream()
                    .filter(e -> "jdk.GarbageCollection".equals(
                            e.getEventType().getName()))
                    .count();

            long heapSummaries = events.stream()
                    .filter(e -> "jdk.GCHeapSummary".equals(
                            e.getEventType().getName()))
                    .count();

            long inTlab = events.stream()
                    .filter(e -> "jdk.ObjectAllocationInNewTLAB".equals(
                            e.getEventType().getName()))
                    .count();

            long outsideTlab = events.stream()
                    .filter(e -> "jdk.ObjectAllocationOutsideTLAB".equals(
                            e.getEventType().getName()))
                    .count();

            System.out.println("gcEvents=" + gcEvents);
            System.out.println(
                    "heapSummaryEvents=" + heapSummaries);
            System.out.println("inNewTlabEvents=" + inTlab);
            System.out.println("outsideTlabEvents=" + outsideTlab);
            System.out.println("jfrFileNonempty=" +
                    (Files.size(file) > 0));
            System.out.println("checksum=" + checksum);

        } finally {
            held.clear();
            Files.deleteIfExists(file);
        }
    }
}
```

### Lệnh chạy

```bash
javac --release 11 --add-modules jdk.jfr HeapGcEvidenceDemo.java
java --add-modules jdk.jfr -Xms64m -Xmx128m HeapGcEvidenceDemo
```

`-Xms/-Xmx` chỉ là giới hạn heap phù hợp fixture, không phải lời khuyên cấu hình cho mọi ứng dụng. Chạy ở môi trường dev/test, **không bật allocation profiling chi tiết trên production không có đánh giá overhead**.

### Stdout đã kiểm chứng trong một lần chạy thử

```text
checkpointCount=4
phases=baseline,temporary,retained,afterGcRequest
retainedCount=64
retainedArrayBytes=4194304
hasHeapMeasurements=true
gcCountNonDecreasing=true
gcEvents=2
heapSummaryEvents=4
inNewTlabEvents=95
outsideTlabEvents=61
jfrFileNonempty=true
checksum=-1952
```

**Quan trọng: đầu ra GC/TLAB không cố định.** Các dòng `gcEvents`, `heapSummaryEvents`, `inNewTlabEvents` và `outsideTlabEvents` là **một kết quả quan sát cụ thể**, có thể khác theo collector, OS, JDK vendor, JIT, timing, TLAB sizes, concurrent GC hoặc flags. Thậm chí `System.gc()` có thể bị bỏ qua. Không đặt test assertion buộc chúng phải bằng `2,4,95,61`.

Các dòng ổn định hơn trong fixture là tên phases, `retainedCount=64`, `retainedArrayBytes=4194304` và `checksum=-1952`; tuy nhiên việc **JFR ghi đủ events** vẫn phụ thuộc availability, settings và buffers. Nếu event type không được cung cấp, một số counters có thể là 0.

### Diễn giải số 4.194.304 byte

`64 × 64 × 1024 = 4.194.304` byte là **tổng payload lengths** của 64 mảng `byte[]` mà danh sách giữ. Đây **không phải tổng retained heap size chính xác** vì object headers, alignment, `ArrayList` backing array, metadata và những object phụ khác chưa tính.

- `temporary`: vòng lặp tạo các arrays và không giữ references; JVM có thể reclaim và JIT có thể tối ưu cấp phát.
- `retained`: danh sách `held` đang giữ 64 arrays. Chúng reachable theo ý đồ của chương trình.
- `afterGcRequest`: sau `System.gc()` và ngủ 250 ms, các arrays trong `held` vẫn reachable. Không thể kỳ vọng GC reclaim chúng khi có strong references.
- `held.clear()` trong `finally` bỏ các references của danh sách, nhưng **không hứa heap-used giảm ngay**; chỉ giúp chúng trở thành eligible for collection khi không còn references khác.

**Chương trình này minh họa retention có chủ đích, không phải lỗi memory leak.** Nếu có business rule phải clear list khi kết thúc request mà production bỏ quên, cùng kiểu giữ tham chiếu ấy có thể trở thành leak.

## 12. Ví dụ Java 11: ghép `GCHeapSummary` theo `gcId` và `when`

Để không nhầm trước/sau GC khác nhau, dùng một analyzer nhỏ tự ghi một file JFR rồi ghép đúng GC ID. **Lưu:** `GcBeforeAfterDemo.java`.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class GcBeforeAfterDemo {
    public static void main(String[] args) throws Exception {
        Path file =
                Files.createTempFile("gc-pairs-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.enable("jdk.GCHeapSummary");
                recording.enable("jdk.GarbageCollection");

                recording.start();

                byte[][] keep = new byte[8][];
                for (int i = 0; i < keep.length; i++) {
                    keep[i] = new byte[128 * 1024];
                }

                System.gc(); // Hint; GC có thể không xảy ra.
                Thread.sleep(300);

                recording.stop();
                recording.dump(file);
            }

            Map<Long, Long> before = new LinkedHashMap<>();
            Map<Long, Long> after = new LinkedHashMap<>();

            List<RecordedEvent> events =
                    RecordingFile.readAllEvents(file);

            for (RecordedEvent event : events) {
                if (!"jdk.GCHeapSummary".equals(
                        event.getEventType().getName())) {
                    continue;
                }

                long gcId = event.getLong("gcId");
                long heapUsed = event.getLong("heapUsed");
                String when = event.getString("when");

                if ("Before GC".equals(when)) {
                    before.put(gcId, heapUsed);
                }
                if ("After GC".equals(when)) {
                    after.put(gcId, heapUsed);
                }
            }

            for (Map.Entry<Long, Long> row : before.entrySet()) {
                Long post = after.get(row.getKey());
                if (post != null) {
                    System.out.println(
                            "gcId=" + row.getKey()
                            + " beforeUsed=" + row.getValue()
                            + " afterUsed=" + post
                            + " delta=" +
                            (post - row.getValue()));
                }
            }

            System.out.println("pairedGcCount=" +
                    before.keySet().stream()
                            .filter(after::containsKey)
                            .count());

        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```bash
javac --release 11 --add-modules jdk.jfr GcBeforeAfterDemo.java
java --add-modules jdk.jfr GcBeforeAfterDemo
```

**Một kết quả đã chạy thử:**

```text
gcId=0 beforeUsed=17941272 afterUsed=4280088 delta=-13661184
pairedGcCount=1
```

Đây chỉ là **một sample**, các con số **không cố định**, GC có thể không xuất hiện và `pairedGcCount` có thể bằng 0. Giải thích:

1. `gcId=0`: ID một GC do JVM thử nghiệm ghi.
2. `beforeUsed` và `afterUsed`: heap occupancy hai phía của cùng GC ID.
3. `delta=-13661184`: reported occupancy sau event thấp hơn trước 13.661.184 byte ở lần thử này.
4. **Không thể kết luận** GC đã reclaim “đúng toàn bộ temporary arrays” hoặc “ứng dụng không leak” từ phép trừ ấy.
5. Khi có collector hoạt động đồng thời, metadata/các pha GC khác nhau, cùng phép tính cũng chỉ là **observed delta**, không phải một định lý về object liveness.

Để dùng lâu dài, hãy **kiểm tra field schema** và biết rõ GC type/cycle semantics. Code ví dụ trên nhằm minh họa ghép key đúng, không phải một công cụ kiểm toán mọi collector.

## 13. Ví dụ Java 11: phân biệt retention không giới hạn và cache có giới hạn

Đây là một ví dụ độc lập, không cần JFR, nhằm chứng minh **chính cơ chế giữ references**. Nó cố tình tạo hai data structures khác nhau:

- `unbounded` giữ thêm 8 arrays sau mỗi vòng.
- `bounded` có eviction khi vượt 16 entries.

**Lưu file:** `RetentionVsAllocationDemo.java`.

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class RetentionVsAllocationDemo {
    private static final List<byte[]> unbounded =
            new ArrayList<>();

    private static final Map<Integer, byte[]> bounded =
            new LinkedHashMap<Integer, byte[]>(16, 0.75f, true) {
        @Override
        protected boolean removeEldestEntry(
                Map.Entry<Integer, byte[]> eldest) {
            return size() > 16;
        }
    };

    private static void executeRound(int round) {
        long transientChecksum = 0;

        for (int i = 0; i < 100; i++) {
            byte[] temporary = new byte[1024];
            temporary[0] = (byte) i;
            transientChecksum += temporary[0];
        }

        for (int i = 0; i < 8; i++) {
            byte[] payload = new byte[4096];
            unbounded.add(payload);

            bounded.put(round * 8 + i,
                    new byte[4096]);
        }

        System.out.println(
                "round=" + round
                + " unbounded=" + unbounded.size()
                + " bounded=" + bounded.size()
                + " transientChecksum=" + transientChecksum);
    }

    public static void main(String[] args) {
        for (int round = 1; round <= 3; round++) {
            executeRound(round);
        }

        unbounded.clear();
        bounded.clear();

        System.out.println(
                "afterClear=" + unbounded.size()
                + "," + bounded.size());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 RetentionVsAllocationDemo.java
java RetentionVsAllocationDemo
```

**Stdout đã kiểm chứng:**

```text
round=1 unbounded=8 bounded=8 transientChecksum=4950
round=2 unbounded=16 bounded=16 transientChecksum=4950
round=3 unbounded=24 bounded=16 transientChecksum=4950
afterClear=0,0
```

**Kết luận đúng:**

- `unbounded` có count tăng theo mỗi round, vì chương trình cố ý tiếp tục giữ references.
- `bounded` tăng tới 16 rồi plateau vì `removeEldestEntry` giới hạn entries.
- `afterClear=0,0` nghĩa là hai collections đã bỏ references theo API; không chứng minh heap bị GC ngay lập tức.
- Cả hai đều có allocations, nhưng retention patterns khác nhau.
- Chỉ khi **quy tắc nghiệp vụ** nói `unbounded` lẽ ra phải bỏ data sau một round mà không làm, mới gọi nó là leak behavior. Nếu nó là một lịch sử dữ liệu cần giữ, đó có thể là retention hợp lệ — dù vẫn có risk hết heap nếu không giới hạn.

Trong production, một cache thực tế cần TTL, capacity theo **byte size** (không chỉ count), eviction semantics, handling concurrency và chính sách khi reload; `LinkedHashMap` đơn giản trên đây chỉ là fixture.

## 14. Kết hợp GC events và custom events để xây giả thuyết

Một cách quan sát mạnh hơn là gắn counters nghiệp vụ vào cùng timeline JFR:

| Custom metric | GC/JFR metric | Diễn giải có thể kiểm |
| --- | --- | --- |
| `activeSessions` tăng | Post-GC used tăng | Có thể là growth hợp lệ theo user load |
| `cacheEntries` chạm max và dừng | Post-GC used plateau | Kỳ vọng của bounded cache |
| `pendingTasks` tăng khi throughput không tăng | Post-GC used tăng | Nghi backlog/queue retention |
| `listenerCount` tăng sau mỗi reconnect | Live set tăng | Nghi không unregister listeners |
| `retainedArrays` không đổi | Allocation rate cao | Nghi temporary allocation pressure hơn là leak |
| `classLoaderCount` tăng sau redeploy | Metaspace/RSS tăng | Nghi classloader leak, không nhất thiết Java heap chính |
| `directBufferCount` tăng | RSS tăng, heap ổn định | Nghi off-heap/direct memory pressure |

**Tương quan không phải nhân quả**. Cần so sánh timing, workload và thiết kế lifecycle trước khi quy một nguyên nhân.

### GC có thể thay đổi hiện tượng quan sát được

Một số collector mở rộng/thu hẹp heap hoặc tạm thời giữ memory để đạt throughput/latency mục tiêu. Vì thế:

- after-GC `heapUsed` có ý nghĩa khác `heapCommitted`;
- RSS cao không có nghĩa mọi page chứa Java object còn live;
- concurrent marking có thể quan sát object liveness theo thời điểm riêng, không phải ngay tại timestamp của custom checkpoint;
- các object với weak/soft/phantom references có semantics riêng;
- sau một GC, object references vẫn có thể tồn tại trên stack do JIT/debug behavior dù source nhìn như không dùng nữa.

Đặc biệt, nếu tìm rò rỉ chậm, đừng dùng `System.gc()` liên tục trong production để “tạo số đo sạch”. Nó có thể làm thay đổi latency/throughput và với một số cấu hình không tạo collection như mong đợi.

## 15. Dấu hiệu gây kết luận sai: checklist chống false positives

### 15.1. Các dấu hiệu **không đủ** để khẳng định leak

| Quan sát | Giải thích thay thế hợp lý |
| --- | --- |
| Heap used tăng trong 5 phút | Cache warm-up, load mới, GC chưa tới |
| Một Young GC giải phóng ít | Objects mới vẫn live, promotion, phase semantics |
| `ObjectAllocationInNewTLAB` xuất hiện nhiều | Allocation pressure, không nói sống lâu |
| Tên class `byte[]` nằm top allocations | Buffers ngắn đời hoặc large payloads |
| Nhiều GC mỗi phút | Workload tăng, heap nhỏ, temporary allocations |
| RSS tăng nhưng heap-used gần ổn định | Direct/native memory, class metadata, thread stacks |
| `jdk.OldObjectSample` chỉ ra một cache entry sống lâu | Cache hợp lệ có TTL/capacity |
| `System.gc()` rồi heap không giảm ngay | GC request có thể bị bỏ qua, object vẫn reachable, JVM retain pages |
| Heap committed không giảm sau GC | JVM có thể giữ committed memory để reuse |
| Một `OldObjectSample` không có root path | Root-path collection chưa bật/không hỗ trợ hoặc sample hạn chế |
| Một snapshot không thấy candidate | Sampling không bảo đảm thấy tất cả objects |
| Heap gần `-Xmx` | Có thể là steady-state cần nhiều memory, hoặc leak; phải điều tra thêm |

### 15.2. Khi nào bằng chứng mạnh hơn?

Một chuỗi bằng chứng đáng tin hơn có dạng:

```text
1. Sau warm-up, workload lặp lại với tải/số phiên gần tương đương
2. Post-GC live-set estimate tăng qua nhiều comparable GC cycles
3. Cache/session/queue/object-count liên quan tăng không có giới hạn mong muốn
4. OldObjectSample / heap dump cho thấy root path giữ object không cần thiết
5. Sửa eviction/unregister/close logic
6. Chạy lại cùng workload → trend retained set ổn định, lỗi không tái hiện
```

Đây là **quy trình kiểm chứng hypothesis**, không phải một ngưỡng số duy nhất cho mọi ứng dụng.

## 16. Phân biệt leak của Java heap và leak ngoài heap

JFR heap profiling giải quyết tốt những câu hỏi về **Java objects**, nhưng JVM có nhiều vùng memory khác.

| Vùng | Ví dụ | Công cụ/góc nhìn cần bổ sung |
| --- | --- | --- |
| Java heap | `byte[]`, collections, entities, session objects | JFR GC/heap/old objects, heap dump, MAT |
| Direct/off-heap buffers | `ByteBuffer.allocateDirect`, native buffer pools | BufferPoolMXBean, Native Memory Tracking khi phù hợp |
| Metaspace/class metadata | Nhiều generated classes/class loaders | JFR class loading/metaspace events, NMT, class-loader graph |
| Thread stacks | Nhiều threads, deep stacks | Thread count/stack analysis, OS process metrics |
| Code cache/JIT | Generated compiled code | JIT/code cache diagnostics |
| JNI/native malloc | Library allocations, image/video compression | Native profilers, NMT/allocator instrumentation theo platform |
| Mapped files | `FileChannel.map` | OS mappings, file cache/RSS; không gộp với Java heap used |

**Không suy từ `OutOfMemoryError` một cách chung chung** rằng Java heap leak đã được chứng minh. Exception message và context quan trọng. Ngay cả `OutOfMemoryError: Java heap space` cũng có thể do workload legitimately vượt heap, allocation burst hoặc heap sizing không phù hợp, không chỉ leak.

## 17. Chi phí profiling, an toàn dữ liệu và tính tái lập

### 17.1. Không bật mọi event trong production

Các event allocation/old-object/root-path có chi phí khác nhau. JFR thường hỗ trợ ghi với overhead thấp khi cấu hình hợp lý, nhưng **không có cam kết “luôn dưới 1%” ở mọi workload**.

Đề xuất vận hành:

- Dùng `default`/cấu hình đã kiểm nghiệm cho baseline.
- Bật TLAB/allocation stack traces/old object sampling có chọn lọc trong cửa sổ chẩn đoán.
- Đánh giá overhead CPU, allocation throughput, safepoints và JFR repository I/O.
- Đặt `maxAge`/`maxSize` và quota disk.
- Hạn chế `path-to-gc-roots` do có thể gây pause đáng kể.
- Ghi rõ JDK/vendor/version/collector/heap flags, sampling configuration và workload khi so sánh dữ liệu.
- Không benchmark riêng một run ngắn rồi kết luận hiệu năng sẽ giống production.

### 17.2. Dữ liệu heap và JFR có thể rất nhạy cảm

Heap dumps có thể chứa strings, tokens, sessions và nội dung đối tượng. JFR có thể chứa class/method names, threads, paths, allocation stacks và custom event fields. Vì vậy:

- Chỉ operator được phép mới tạo và đọc artifacts.
- Không upload file `.hprof`/`.jfr` lên website bên ngoài hoặc chat công khai nếu chưa được duyệt.
- Bảo vệ file bằng quyền filesystem, encryption, retention và truy vết download.
- Cân nhắc scrub/redact hoặc phân tích nội bộ.
- Không bật `heap dump on OOM` mà không kiểm soát nơi file được ghi và quota; file có thể lớn và nhạy cảm.
- Sau điều tra, xóa dữ liệu theo policy, không giữ dump mãi trên disk của container/service.

### 17.3. Sampling và GC có thể làm thay đổi kết quả

Thao tác profiling có thể tăng overhead, làm khác timing GC/JIT hoặc khiến một transient leak chỉ xuất hiện dưới tải thật. Thiết kế một **experiment có điều kiện lặp lại**, không tối ưu/tái cấu hình JVM tùy tiện rồi so sánh các số đo không cùng baseline.

## 18. Chẩn đoán từng tình huống

### Tình huống A — CPU cao, GC nhiều, heap sau GC ổn định

**Giả thuyết:** allocation pressure do temporary objects. Tìm allocation sites theo TLAB/JDK16+ allocation samples; cân nhắc object reuse có kiểm soát, giảm intermediate arrays/boxing hoặc thay đổi streaming algorithm. Đừng tự gắn nhãn leak khi post-GC baseline không tăng.

### Tình huống B — Heap after-GC tăng, active sessions cũng tăng

**Giả thuyết:** retention đúng theo load. So sánh memory per active session, TTL, max sessions, tenant profile; quan sát khi sessions hết hạn liệu heap baseline có giảm/plateau sau collections phù hợp không.

### Tình huống C — Heap after-GC tăng dù active sessions ổn định

**Giả thuyết:** cache/queue/listener hoặc static references không được release. Dùng old-object samples và heap graph, so sánh active queues/listeners/maps; xác thực với lifecycle owner.

### Tình huống D — RSS tăng, heap-used sau GC không tăng

**Giả thuyết:** direct/native/metaspace/thread memory. Thu Native Memory Tracking, thread count, buffer pool and OS metrics; không kết luận bằng GCHeapSummary.

### Tình huống E — Sau `System.gc()` heapUsed vẫn cao

**Khả năng:** GC bị bỏ qua; objects vẫn strong reachable; collector không reclaim theo cách bạn kỳ vọng; snapshot chưa đồng bộ GC; committed pages vẫn giữ; một số pools không được đo bằng heapUsed. Đọc `jdk.GarbageCollection`/`GCHeapSummary` để biết **có thực sự có GC được ghi nhận không**, rồi kiểm tra roots/snapshots.

### Tình huống F — OldObjectSample vắng mặt

**Khả năng:** sampling chưa bật hoặc cửa sổ quá ngắn, runtime/config không thu event, no candidate sampled, file được dump ở thời điểm không phù hợp. Không suy ra absence of leak; xem JDK configuration và tăng quan sát hợp lý.

## 19. 21 câu hỏi tự kiểm tra có đáp án

**1.** Heap allocation rate cao có chứng minh Java heap leak không?

**Đáp án:** Không. Phần lớn allocations có thể là temporary objects được GC reclaim; leak liên quan retention không cần thiết.

**2.** Vì sao sau một young GC, `heapUsedAfter` không được xem là chính xác toàn bộ live set?

**Đáp án:** Young collection có phạm vi/pha nhất định và collector-specific semantics; old regions/objects vẫn có thể live hoặc chưa được quét theo nghĩa full heap.

**3.** `jdk.GCHeapSummary` ghép trước/sau theo trường nào?

**Đáp án:** `gcId` và `when`, ví dụ `Before GC`/`After GC`, đồng thời kiểm tra collector/type/timestamp.

**4.** `jdk.ObjectAllocationInNewTLAB` có ghi mọi object cấp phát bên trong TLAB không?

**Đáp án:** Không. Event liên quan đến TLAB refill/new TLAB, không phải event cho từng object.

**5.** Có thể lấy `tlabSize` của một TLAB event làm object size không?

**Đáp án:** Không. `tlabSize` là kích thước TLAB, khác `allocationSize` của object gây event.

**6.** Java 11 có `jdk.ObjectAllocationSample` làm baseline event không?

**Đáp án:** Không. Event này được đưa vào **JDK 16**; Java 11 sử dụng TLAB/outside-TLAB và thread allocation statistics phù hợp.

**7.** `jdk.ObjectAllocationSample.weight` trên JDK mới thể hiện gì?

**Đáp án:** Trọng số thống kê cho allocation sample, không phải số bytes đang retained của một object.

**8.** Vì sao đối tượng sống lâu trong `jdk.OldObjectSample` vẫn có thể hợp lệ?

**Đáp án:** Cache, session, global index hoặc object theo vòng đời ứng dụng có thể cần sống lâu; leak yêu cầu retention trái với nhu cầu nghiệp vụ.

**9.** Path to GC roots chứng minh điều gì?

**Đáp án:** Cho biết một chuỗi tham chiếu khiến object được giữ reachable (theo những dữ liệu đã ghi). Nó không tự chứng minh đường giữ ấy là lỗi nghiệp vụ.

**10.** Muốn tìm retained size đầy đủ của các object có cần chỉ dựa vào TLAB events không?

**Đáp án:** Không. Allocation events không có toàn graph; cân nhắc heap dump/dominator analysis.

**11.** `System.gc()` có buộc JVM làm full GC ngay không?

**Đáp án:** Không. Đây là request/hint; bị ảnh hưởng bởi collector/flags và không bảo đảm kết quả/độ trễ.

**12.** `HeapGcEvidenceDemo` có 64 mảng được giữ, vậy có chắc bị leak không?

**Đáp án:** Không. Chúng được giữ có chủ đích để minh họa reachability; có leak hay không phụ thuộc contract vòng đời.

**13.** Tại sao 4.194.304 bytes trong demo không phải retained heap size chính xác?

**Đáp án:** Chỉ cộng array payload lengths, chưa tính headers, alignment, ArrayList capacity/refs và các object khác.

**14.** `-Xmx128m` có giới hạn RSS của process bằng 128 MiB không?

**Đáp án:** Không. JVM còn metaspace, code cache, native buffers, thread stacks và memory ngoài heap.

**15.** Vì sao một lần `afterGcUsed` cao chưa đủ kết luận leak?

**Đáp án:** Workload có thể đang warm-up, cache hợp lệ, GC chưa xử lý hết theo collector semantics hoặc snapshot chưa so sánh được.

**16.** Có thể bật `path-to-gc-roots=true` mặc định cho mọi JFR dump production không?

**Đáp án:** Không nên. Việc thu root paths có overhead/pause đáng kể và nên dùng có kiểm soát khi nghi vấn leak.

**17.** `Recording.dump(Path)` Java 11 có overload nhận `path-to-gc-roots` không?

**Đáp án:** Không. Dùng tùy chọn chính thức của công cụ như `jcmd JFR.dump ... path-to-gc-roots=true` khi runtime hỗ trợ.

**18.** `getHeapMemoryUsage().getCommitted()` tăng có chứng minh objects chưa được GC không?

**Đáp án:** Không. JVM có thể giữ committed heap pages để sử dụng lại dù objects đã không còn live.

**19.** Trong demo `RetentionVsAllocationDemo`, cache bounded plateau ở bao nhiêu entries?

**Đáp án:** 16; unbounded list tăng 8 → 16 → 24 trong ba rounds. Đó là bằng chứng về collection growth, không tự là leak proof.

**20.** Nếu chỉ có high RSS và heap live set ổn định, cần khảo sát gì?

**Đáp án:** Native memory, direct buffers, metaspace, thread stacks, OS memory metrics hoặc NMT, tùy ngữ cảnh.

**21.** Bằng chứng thuyết phục hơn về leak gồm những gì?

**Đáp án:** Post-GC trend tăng dưới workload so sánh được, object count/retained graph không phù hợp lifecycle, root path chỉ owner giữ sai, và thử nghiệm fix làm xu hướng ổn định.

## 20. Tài liệu đáng tin cậy, còn áp dụng

- [Oracle Java SE 11 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshooting-memory-leaks.html): live-set trend, JMC Old Object Sample, allocation sites và path-to-GC-roots.
- [Oracle Java SE 24 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html): phân biệt temporary allocations, TLAB, heap growth và GC pressure.
- [Oracle JDK 16 Release Notes — New jdk.ObjectAllocationSample Event](https://www.oracle.com/java/technologies/javase/16all-relnotes.html): mốc giới thiệu `jdk.ObjectAllocationSample`, phân biệt Java 11 và JDK mới.
- [OpenJDK — Troubleshooting Memory Leaks](https://ops.java/troubleshooting/articles/memory-leaks/): hướng dẫn phối hợp live-set trend, JFR Old Object Samples và GC roots.
- [Dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): JFR configurations, `path-to-gc-roots` và nguyên tắc sử dụng.
- [Red Hat OpenJDK 11 — JFR Configuration Options](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/11/html/using_jdk_flight_recorder_with_red_hat_build_of_openjdk/configure-jfr-options): Java 11 OldObjectSample, profile settings và chi phí root paths.
- [Oracle Java SE 11 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html): `getHeapMemoryUsage` và giới hạn của số đo.
- [Oracle Java SE 11 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryUsage.html): `used`, `committed`, `max`.
- [Oracle Java SE 11 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): GC count/time và các giá trị không được hỗ trợ.
- [Oracle Java SE 11 — `Recording`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): cấu hình events, `start`, `stop`, `dump` và retention.
- [Oracle Java SE 11 — `Event`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): custom event lifecycle.
- [Oracle Java SE 11 — `RecordingFile`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc `.jfr`; với file lớn dùng streaming iterator, không phải `readAllEvents`.
- [Oracle Java SE 11 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): event type, fields, timestamp, thread và stack.
- [Oracle Java SE 11 — `RecordedObject`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `getLong`, `getString`, `getValue` và field schema.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): Flight Recorder trong OpenJDK 11 và kiến trúc chẩn đoán vẫn được dùng trong các JDK hiện hành.

**Tổng kết:** Heap profiling trả lời những câu hỏi khác nhau: **allocation đang ở đâu**, **GC xử lý khi nào**, **sau các GC cycles so sánh được còn bao nhiêu memory**, và **ai đang giữ những objects còn sống**. Java 11 JFR giúp thu bằng chứng với TLAB/GCHeapSummary/OldObjectSample, nhưng **không có một event nào tự chứng minh leak**. Bằng chứng mạnh cần kết hợp xu hướng nhiều chu kỳ, metadata root paths, số liệu nghiệp vụ, đồ thị retained references và thử nghiệm xác nhận sau khi sửa.