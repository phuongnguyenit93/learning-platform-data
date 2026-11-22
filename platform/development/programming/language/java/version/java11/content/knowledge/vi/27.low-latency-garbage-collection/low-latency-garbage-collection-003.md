# GC độ trễ thấp: Ảnh hưởng của allocation rate, live set và heap headroom trong Java 11+

> **Chủ đề cha:** GC độ trễ thấp. **Trọng tâm:** Vì sao cùng một thuật toán garbage collector nhưng ứng dụng A vẫn có p99 tốt, còn ứng dụng B gặp nhiều GC cycles, allocation stalls hoặc Full GC? Ba biến số cần quan sát đồng thời là **allocation rate** (tốc độ cấp phát), **live set** (dữ liệu còn sống cần giữ), và **heap headroom** (khoảng trống dành cho đợt cấp phát/GC tiếp theo). Các nguyên lý áp dụng cho G1 trong Java 11 và cho những concurrent collectors hiện đại như Generational ZGC. Bài sử dụng Java 11-compatible APIs, không khuyến nghị các collector hoặc flags đã bị loại bỏ trên JDK mới.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa **allocation rate**, **live set**, **heap occupancy**, **headroom** và các đơn vị MiB/s, MiB, %.
2. Phân biệt **allocated bytes** (được tạo mới) với **retained/live bytes** (vẫn còn reachable), và hiểu vì sao allocation rate cao không mặc định là memory leak.
3. Giải thích quan hệ giữa **GC cycle duration**, **peak allocation rate**, **live set** và **buffer/headroom** đối với độ trễ.
4. Hiểu tại sao low-pause collector vẫn có thể **allocation stall**, to-space/evacuation failure, Full GC hoặc `OutOfMemoryError` khi bộ nhớ quá chật.
5. Tách **maximum heap `-Xmx`**, **committed heap**, **used heap**, **live set sau GC**, **RSS/cgroup usage** và **tổng bộ nhớ container**.
6. Dùng công thức headroom/budget như một **mô hình kiểm tra giả thuyết**, không dùng nó như bảo đảm toán học thay cho load test.
7. Quan sát G1 với **unified GC logging** `-Xlog:gc*,safepoint=info`, GC MXBeans và JFR phù hợp Java 11.
8. Chạy chương trình so sánh **hai pha cùng cấp phát 192 MiB payload** nhưng có live set khác nhau và thấy headroom thay đổi.
9. Đo allocation bytes của một thread trên HotSpot bằng `com.sun.management.ThreadMXBean` khi implementation hỗ trợ.
10. Biết cách sizing/benchmark ở tải ổn định, tải đột biến, sau warm-up, sau scale-down, và có container memory limits.
11. Phân biệt khả năng/phiên bản của G1, ZGC và Shenandoah; không áp dụng flags mới cho JVM Java 11 hoặc hướng dẫn legacy cho JVM mới.
12. Thiết kế checklist cải thiện p99 mà không đánh đổi bằng OOM, CPU quá tải hoặc chi phí bộ nhớ không kiểm soát.

## 2. Mô hình tổng quát: GC không chạy trong “khoảng trống tuyệt đối”

Khi ứng dụng đang làm việc, nó liên tục tạo objects. Một số objects nhanh chóng trở thành garbage; một số tồn tại qua nhiều GC cycles. Collector phải **thu hồi được garbage đủ nhanh** và đồng thời giữ đủ **vùng trống** để ứng dụng tiếp tục cấp phát.

~~~text
Java heap bị giới hạn bởi -Xmx
+------------------------------------------------------------------+
|                     Live set                                     |
|       objects vẫn reachable: caches, sessions, queues, ...       |
+---------------------------------------+--------------------------+
|    Garbage chưa được thu hồi           |  Headroom thực dụng      |
|    / objects mới cấp phát              |  & vùng cần cho GC        |
+---------------------------------------+--------------------------+
                           ^
                           |
                Allocation rate / bursts
                           |
                GC cần thu hồi kịp thời

Live set càng lớn --> vùng tái sử dụng càng ít
Allocation rate càng cao --> vùng trống bị tiêu thụ càng nhanh
GC cycle càng lâu --> cần chịu đựng nhiều allocation trong lúc GC chạy
Headroom càng nhỏ --> càng dễ stall/failure khi có burst
~~~

Với concurrent collector, GC chạy **song song với mutator** (threads ứng dụng). Nếu mutator tạo rác hoặc làm tăng live data nhanh hơn GC thu hồi/tiến triển, hệ thống có thể hết không gian cấp phát dù **STW pauses riêng lẻ vẫn ngắn**.

**Độ trễ thấp cần nhiều hơn pause nhỏ**: một request có thể đợi allocation, lock, I/O, scheduler, hoặc CPU bị GC background threads cạnh tranh. Vì vậy hãy theo dõi **end-to-end p95/p99**, **allocation stalls**, **GC pause**, **throughput**, **GC CPU**, memory và failure rate cùng lúc.

## 3. Ba khái niệm cốt lõi

### 3.1. Allocation rate — tốc độ cấp phát

Ký hiệu `A`, đơn vị thường là **MiB/s** hoặc **GiB/s**.

\[
 A_{\mathrm{avg}} =
 \frac{\text{bytes được cấp phát trong một khoảng thời gian}}
      {\text{số giây của khoảng đó}}
\]

Ví dụ code tạo tổng **2 GiB objects trong 4 giây**: tốc độ trung bình khoảng **512 MiB/s**. Nếu hầu hết objects chết trong vài milliseconds, ứng dụng có thể giữ ít heap nhưng GC vẫn phải xử lý **churn**.

Cần phân biệt:

- **Average allocation rate:** trung bình trong 1 phút hay 10 phút.
- **Peak / burst allocation rate:** tốc độ trong cửa sổ ngắn 100 ms–5 s; nhiều hệ thống gặp sự cố ở burst chứ không phải average.
- **Promotion rate / old-gen allocation:** phần objects sống lâu đi vào old generation; có thể quan trọng hơn raw young allocation rate đối với G1.
- **Thread allocation rate:** phân phối bytes được cấp phát theo thread/đường xử lý; hotspot có thể nằm ở một nhóm worker.
- **Allocation pressure:** áp lực đặt lên collector do lượng và tốc độ cấp phát, bao gồm số lần/độ lớn objects, chứ không chỉ tỷ lệ byte thô.

**Không nhầm rate với footprint:** ứng dụng có thể cấp phát 50 GiB trong một phút nhưng heap live chỉ 200 MiB nếu objects chết nhanh.

### 3.2. Live set — lượng dữ liệu thật sự cần giữ

**Live set** là lượng objects JVM xác định **còn sống/reachable** trong một pha GC theo semantics của collector, gồm objects còn được giữ bởi GC roots, static fields, thread stacks, queues, caches, request contexts, v.v.

Ví dụ:

- Service giữ 2 triệu sessions, mỗi session giữ một graph nhỏ → live set tăng.
- Một `static Map` không giới hạn eviction khiến references vẫn còn → live set tăng bền vững.
- Hệ thống tạo rất nhiều `StringBuilder` ngắn hạn → allocation rate cao, nhưng live set có thể không tăng.
- Queue backpressure không hoạt động, requests tồn đọng → live set tăng **đột ngột**, không phải một leak truyền thống.

Số đo `MemoryMXBean.getHeapMemoryUsage().getUsed()` là **used heap tại thời điểm đo**, có thể bao gồm **garbage chưa thu hồi**, nên **không được coi chính xác bằng live set**. After-GC occupancy, GC logs và JFR heap summaries thường cho ước lượng thực dụng hơn, nhưng cũng phụ thuộc GC collector, cách định nghĩa “after GC”, concurrent phases và tính tiến triển của workload.

**Live set tăng** cần xét *do thiết kế hay bất thường*: cache warm-up, tăng số phiên hợp lệ, tăng dữ liệu xử lý cũng có thể giải thích. Memory leak là khi objects **không còn cần nhưng vẫn bị giữ bởi references**.

### 3.3. Heap headroom — không gian để chịu đựng đợt cấp phát

Ở mức khái niệm:

\[
 H_{\mathrm{optimistic}} = Xmx - \text{heapUsed hiện tại}
\]

Nếu `-Xmx=8GiB` và used heap snapshot `=5GiB`, chênh lệch là `3GiB`. Nhưng đây chỉ là **upper bound tính toán**, **không** đảm bảo 3 GiB đều cấp phát được ngay:

- Còn phải xét regions/space dành cho promotion, survivor và evacuation;
- Có thể có fragmentation hoặc humongous object constraints;
- Một phần objects chưa chết hoặc chưa được collector reclaim;
- G1 và các concurrent collectors có internal accounting/safety margins;
- Heap committed có thể nhỏ hơn max, commit thêm memory có chi phí và bị giới hạn OS/cgroup;
- JVM còn dùng **native/off-heap memory** ngoài Java heap;
- Một số memory pool không có `getMax()` hữu hạn.

**Headroom thực dụng** là dung lượng còn khả dụng **sau khi tính workload đỉnh và vùng GC cần để tiến triển**, không chỉ chênh lệch số học.

## 4. Tại sao allocation rate ảnh hưởng latency?

### 4.1. Nhiều objects ngắn hạn

~~~java
// Anti-pattern minh họa, không phải chương trình đầy đủ.
for (Request request : requests) {
    String body = request.getPayload();
    String[] parts = body.split(",");
    consume(parts);
}
~~~

Nếu mỗi request tách chuỗi/gom list/boxing/serialize rất nhiều objects, tốc độ cấp phát có thể tăng theo requests/s. Phần lớn dữ liệu ngắn hạn được young GC thu hồi tốt, nhưng:

- GC frequency có thể tăng;
- Mỗi pause có thể tạo biến động latency;
- GC cycles tiêu tốn CPU/throughput;
- Một burst có thể ăn nhanh headroom trước khi collector phản ứng;
- Những objects sống qua young GC có thể được promote, làm old generation áp lực hơn.

**Không tối ưu theo hướng “zero allocation bằng mọi giá”**. Tránh tạo objects không cần thiết, nhưng đừng đánh đổi readability, safety hay contention bằng object pooling tùy tiện. Dùng profiling và benchmark trên workload thật trước khi thay đổi.

### 4.2. Allocation rate tăng theo burst

Giả sử bình thường `A=200MiB/s` nhưng trong đỉnh tải lên `A=1.2GiB/s`. Headroom vốn đủ cho bình thường có thể không chịu được đỉnh. Hệ thống cần mô hình dựa trên **peak rate và peak live set**, không phải average.

### 4.3. Allocation stall không đồng nghĩa dài STW pause

Một low-pause collector có thể có pauses ngắn nhưng application thread phải **đợi có không gian cấp phát** khi collector không kịp reclaim. Đây là **allocation stall**, và nó có thể ảnh hưởng p99 dù dashboard “GC pause max” vẫn trông đẹp.

Với G1, headroom/evacuation space quá chật có thể dẫn đến **evacuation failure** và thậm chí **Full GC**. Với concurrent collectors như ZGC, áp lực cấp phát có thể vượt khả năng reclaim, dẫn tới stall/chờ GC tiến triển.

**Vì vậy:** xem cả **allocation stall/failure**, GC pause, CPU và service latency.

## 5. Tại sao live set là yếu tố quyết định?

### 5.1. Live set giảm vùng trống dài hạn

Giả sử hai ứng dụng có `-Xmx=4GiB` và cùng cấp phát `600MiB/s`:

| Đặc điểm | Ứng dụng A | Ứng dụng B |
| --- | --- | --- |
| Xmx | 4 GiB | 4 GiB |
| Live set gần baseline | 1 GiB | 3.2 GiB |
| Chênh Xmx–live đơn giản | 3 GiB | 0.8 GiB |
| Workload churn | 600 MiB/s | 600 MiB/s |
| Khả năng chịu burst | Tương đối nhiều chỗ | Dễ hết headroom hơn |
| Rủi ro | GC CPU nếu churn quá cao | Stall/evacuation/Full GC/OOM nếu không reclaim kịp |

Đây là **mô hình giả định**, không phải benchmark đo hai collectors. B còn vùng trống ít hơn rất nhiều cho cùng tốc độ cấp phát. Nếu muốn xử lý p99, tăng `-Xmx` (khi OS cho phép), **giảm live retention** hoặc giới hạn burst có thể hiệu quả hơn việc chỉ giảm pause target.

### 5.2. Live set ảnh hưởng lượng công việc GC

Collector cần xác định/copy/relocate/live-mark những objects phù hợp với thuật toán. Live set lớn hơn có thể làm tăng một số chi phí tracing, remembered sets, relocation, scan hoặc promotion. Mức tác động **phụ thuộc collector**:

- **G1:** evacuation của các live objects trong collection set diễn ra trong pauses; nhiều live data trong regions bị thu gom có thể làm việc copy lâu hơn và khó đạt mục tiêu pause.
- **ZGC:** phần lớn công việc nặng diễn ra đồng thời, nên STW pause ít phụ thuộc tổng heap hơn, nhưng CPU/bandwidth cho concurrent work và headroom vẫn phải đủ.
- **Shenandoah:** cũng nhằm rút ngắn pauses qua concurrent work; cần đánh giá throughput, headroom và độ hỗ trợ thực tế của build/JDK.

**Không có quy tắc “live set lớn thì một collector luôn chậm hơn collector khác”**. Cần đo trên workload/CPU/heap tương đương.

### 5.3. Live set không chỉ là cache

Các nguyên nhân phổ biến:

- Quá nhiều in-flight requests hoặc queues không giới hạn;
- Cache không đặt size/TTL, reference graph vô tình bị giữ;
- `ThreadLocal` tồn tại lâu, listeners không hủy đăng ký;
- Batches giữ toàn bộ dữ liệu thay vì streaming;
- ORM entity graphs, JSON trees hoặc file buffers rất lớn;
- Sessions/connection state sống lâu;
- Classloaders/plugin registries sống lâu;
- Soft/weak references có semantics khác strong references, không thay thế capacity planning.

## 6. Headroom gồm những gì và không gồm những gì?

### 6.1. Các con số dễ bị nhầm

| Số đo | Nguồn/ý nghĩa | Có phải headroom dùng ngay? |
| --- | --- | --- |
| `-Xmx` / `Runtime.maxMemory()` | Giới hạn heap tối đa JVM sử dụng | Không, là trần |
| `heap.getUsed()` | Heap đang dùng, gồm garbage chưa reclaim | Không, chỉ snapshot |
| `heap.getCommitted()` | Heap memory JVM đã committed | Không, phần committed có thể đã dùng |
| `heap.getMax()` | Heap max theo MXBean, có thể `-1` nếu không xác định | Không, chỉ trần |
| `Xmx-used` | Khoảng số học giữa trần và used | **Ước lượng lạc quan**, không trừ GC reserves |
| After-GC occupancy | Gần hơn với retained/live footprint | Không nhất thiết chính xác live-set toàn heap |
| `RSS` / container memory.current | Resident memory thực tế ở OS/cgroup | Bao gồm heap + nhiều native/off-heap segments |
| Native allocations / direct buffers | Bộ nhớ ngoài Java heap | Không giảm trực tiếp `Xmx-used` nhưng vẫn ăn RAM của process/container |
| Cgroup hard memory limit | Trần tổng bộ nhớ container | Không phải riêng heap; OOM kill có thể xảy ra trước khi heap đạt Xmx |

### 6.2. Committed khác used và max

~~~text
Xmx (maximum heap)             8 GiB
Committed heap hiện tại        5 GiB
Used heap hiện tại             4 GiB
Chênh committed-used           1 GiB
Chênh Xmx-used                 4 GiB

Nhưng app còn native memory, GC reserve, page commitment,
memory pressure của container và các giới hạn collector.
~~~

**Dữ liệu minh họa.** Không xem 4 GiB là một “khoảng trống miễn phí” có thể cấp phát an toàn vô hạn. Ở Linux container, heap có thể commit thêm nhưng bị memory limit của pod chặn ngay cả trước khi Java ném `OutOfMemoryError`.

### 6.3. Cần chừa headroom cho GC, không chỉ business data

G1 cần vùng đích khi **evacuate live objects**. ZGC cần đủ không gian để application tiếp tục allocate khi **concurrent marking/relocation** vẫn chạy. Nếu chỉ sizing `Xmx ~= live set`, collector thiếu đường tiến triển đúng lúc workload tăng.

Không có một **tỷ lệ headroom cố định** bảo đảm 99.9th latency. 20%, 30% hay 50% chỉ là ví dụ sizing ban đầu; chính workload, CPU allocation concurrency, GC cycle time và burst mới quyết định.

## 7. Mô hình ngân sách headroom cho concurrent GC

Một phép tính định hướng:

\[
 H_{\mathrm{needed}} \gtrsim
 A_{\mathrm{peak}} \times T_{\mathrm{reclaim}}
 + B_{\mathrm{burst}}
 + R_{\mathrm{collector}}
\]

Trong đó:

- `A_peak`: tốc độ cấp phát đỉnh theo cửa sổ phù hợp;
- `T_reclaim`: thời gian mà hệ thống phải chịu đựng trước khi GC thu hồi đủ vùng dùng lại;
- `B_burst`: phần đệm cho bursts, queues và tăng live set ngoài mô hình;
- `R_collector`: reserve/fragmentation/evacuation margin tùy collector;
- Dấu `\gtrsim` có nghĩa **ước lượng thận trọng**, không phải hợp đồng hay công thức dự đoán chính xác.

**Cảnh báo:** Trong một GC cycle, collector có thể reclaim từng phần, còn application tiếp tục cấp phát; một phép nhân đơn giản không mô phỏng chính xác toàn bộ dòng bộ nhớ. Dùng nó để **chọn thông số thử nghiệm**, sau đó xác nhận bằng **GC logs, JFR, p99 và failure metrics**.

### Ví dụ tính tay

Giả sử:

- `Xmx = 8 GiB`;
- Live-set baseline gần `4.5 GiB`;
- Peak allocation `A_peak=1 GiB/s`;
- Mất khoảng `1.5s` trước khi reclaim đủ vùng trống trong tình huống xấu;
- Dự phòng burst/collector thêm `1 GiB`.

Ngân sách đơn giản: `1 × 1.5 + 1 = 2.5 GiB`. Chênh `8−4.5=3.5 GiB` *có vẻ* có vùng dự phòng; nhưng sau khi trừ working garbage/current occupancy và reserve thực tế, kết luận còn phụ thuộc collector. Hệ thống cần đo riêng các phase và container limit.

**Đừng lấy con số `T_reclaim` bằng chính p99 GC pause**: một collector concurrent có thể làm việc 1–3 giây với pauses rất ngắn, nên thời gian tới khi reclaim đủ khác thời gian STW.

## 8. Bốn kịch bản với cùng heap nhưng hành vi khác

| Allocation rate | Live set | Headroom | Hệ quả đáng nghi |
| --- | --- | --- | --- |
| Thấp | Nhỏ | Rộng | GC pressure thường thấp |
| Cao | Nhỏ | Rộng | Young GC nhiều hơn, GC CPU tăng; chưa chắc OOM |
| Thấp | Lớn | Hẹp | Ít free memory, nhạy cảm với burst/caches |
| Cao | Lớn | Hẹp | **Nguy cơ cao:** stall, eviction/evacuation failure, Full GC/OOM |
| Cao dạng burst | Trung bình | Thay đổi nhanh | Average metrics có thể che spike, cần peak window |
| Bình thường | Live set tăng sau GC | Headroom thu hẹp dần | Cache growth, backlog hoặc memory retention cần điều tra |

Hai ứng dụng có cùng “heap average used 60%” vẫn khác rủi ro nếu một ứng dụng có allocation bursts gấp 10 lần và GC reclaim chậm hơn.

## 9. G1 GC trong Java 11: nhìn allocation và live data thế nào?

**G1** là collector mặc định phổ biến của HotSpot server-class Java 11, nhằm cân bằng throughput và pause-time mục tiêu. Nó phân vùng heap thành **regions**, thu gom theo **young/mixed collections**, thực hiện một số công việc concurrent và một số công việc **STW**. <i>Không nên hiểu “low-pause” là real-time guarantee.</i>

### 9.1. Nhiều allocation → young collections

Với nhiều objects ngắn hạn:

- Eden đầy nhanh hơn;
- Young collections có thể xảy ra thường xuyên hơn;
- Objects còn sống được copy sang survivor/old tùy tuổi/policy;
- GC có chi phí CPU và pauses; nếu vừa cần throughput cao vừa yêu cầu p99 thấp, cần quan sát cả hai.

`-XX:MaxGCPauseMillis` là **soft pause target** cho G1, **không phải SLA cứng**. Một giá trị quá thấp có thể làm young-gen sizing và GC frequency thay đổi, tăng overhead mà không giải quyết live set quá lớn.

### 9.2. Live set lớn làm evacuation khó

Trong pause, G1 thường **copy các live objects** ra regions mới. Nếu không đủ vùng đích, collector có thể gặp **evacuation failure**. Khi pressure kéo dài, nó có thể phải chuyển sang Full GC/compaction, gây pause dài hơn nhiều so với bình thường.

**Dấu hiệu cần tìm:** GC logs chứa evacuation failure, Full GC, to-space/region pressure, high old occupancy, promotion pressure và humongous allocation. Tên chính xác của log phụ thuộc JDK version.

### 9.3. Humongous objects

G1 có cách xử lý đặc biệt với **humongous objects** lớn theo region threshold. Nhiều mảng/object rất lớn có thể:

- Chiếm trọn nhiều regions;
- Làm tăng old generation pressure và fragmentation;
- Khiến việc tìm vùng liên tiếp khó hơn;
- Tăng nguy cơ Full GC khi heap gần đầy.

Đừng chỉ xem tổng used heap mà bỏ qua **phân bố kích cỡ objects** và GC logs. Hạn chế allocations rất lớn trong hot path nếu có thể streaming, chunking hoặc bounded buffers; đừng tự pool huge arrays nếu pooling làm live set tăng vô ích.

### 9.4. Điều gì nên thử trước khi chỉnh flags?

1. Xác nhận GC collector/version và workload thực.
2. Đo allocation rate, after-GC live set, occupancy/headroom.
3. Kiểm chuỗi sự kiện trước Full GC/evacuation failure.
4. Giảm retained data ngoài nhu cầu, giới hạn queue/cache.
5. Kiểm kích cỡ batch, thời gian sống objects, humongous allocations.
6. Nâng Xmx **trong giới hạn container** và benchmark, nếu thiếu headroom là nguyên nhân.
7. Chỉ sau đó mới tinh chỉnh G1 flags theo **tài liệu đúng JDK version**; không copy một bộ flags từ blog cũ.

**Không lấy các giá trị mặc định của G1 đời Java 8 làm mặc định bất biến của JDK mới**. Heuristics và defaults có thay đổi qua nhiều releases.

## 10. ZGC trên JDK hiện đại: rất ngắn pause vẫn cần headroom

**ZGC** là low-latency collector thực hiện phần lớn công việc nặng đồng thời với application. Tài liệu Oracle nhấn mạnh hai điều khi sizing `-Xmx`:

1. Heap phải chứa được **live set**;
2. Phải còn **headroom** để ứng dụng cấp phát trong lúc GC đang chạy.

Nếu allocation rate vượt khả năng reclaim của GC hoặc có burst lớn hơn reserve, application có thể gặp **allocation stall**. Vì vậy một đồ thị “GC STW max pause rất nhỏ” **không chứng minh end-to-end p99 tốt**.

### 10.1. ZGC generational hiện nay

Từ **JDK 24**, ZGC là **generational**; non-generational mode đã bị loại bỏ và `-XX:+ZGenerational` không còn là flag hiện hành. Với JDK mới hỗ trợ ZGC, chọn `-XX:+UseZGC` theo tài liệu runtime. Không dạy người dùng Java 11 thêm cờ từ thời chuyển tiếp Java 21, cũng không mặc định ZGC của mọi bản Java 11 giống ZGC generational hiện đại.

Với **Java 11**, bài tập đã kiểm chạy bằng **G1**, vì tính khả dụng/tình trạng thử nghiệm của ZGC tùy bản update, vendor và OS. Chỉ dùng ZGC trên một runtime đang được hỗ trợ/chấp thuận của hệ thống; xác nhận bằng `java -version` và help flags của JVM đó.

### 10.2. Xmx và SoftMaxHeapSize

Với các bản ZGC hỗ trợ `-XX:SoftMaxHeapSize`:

- `-Xmx` là **hard maximum** của Java heap;
- `SoftMaxHeapSize` là **mục tiêu mềm** mà ZGC cố giữ dưới đó;
- Khi cần ngăn allocation stall, ZGC có thể dùng thêm heap **trên soft max nhưng không vượt Xmx**;
- Không cấu hình soft max như một giả định rằng collector **không bao giờ** vượt nó.

Ví dụ trên một JDK ZGC hiện đại **đã xác minh hỗ trợ**:

~~~bash
java -XX:+UseZGC -Xmx5g -XX:SoftMaxHeapSize=4g -jar app.jar
~~~

**Lệnh minh họa**, không áp dụng vô điều kiện cho Java 11 hoặc một app/OS không hỗ trợ ZGC. Vẫn phải đảm bảo container có đủ RAM cho heap cộng native memory.

### 10.3. GC threads cần CPU để reclaim

ZGC có concurrent GC threads. Nếu CPU budget rất thấp, GC có thể không tiến triển đủ nhanh trước allocation burst; tăng Xmx không phải lời giải duy nhất. Điều chỉnh concurrent thread counts có thể giúp một số workload nhưng cũng lấy CPU của mutator. **Đừng chỉnh `ConcGCThreads` theo cảm giác**: đo throughput, GC CPU, allocation stalls và p99.

## 11. Shenandoah: nguyên tắc giống, khả dụng tùy distribution

**Shenandoah** cũng nhằm giảm pause bằng concurrent work, và chịu các rủi ro thực tế khi **allocation rate cao, free-set/headroom thấp, hoặc GC không theo kịp mutator**. Nhưng nó không có trên mọi bản phân phối JDK hoặc mọi nền tảng; một số cờ và implementation mode thay đổi theo version.

Với mục tiêu bài Java 11:

- Dùng **G1** để thực hành portable trên HotSpot Java 11;
- Khi muốn thử Shenandoah, xác nhận **distribution/version/OS** và khả năng hỗ trợ trước;
- Không dựa vào một lệnh bật Shenandoah từ hướng dẫn cũ nếu runtime mới đã đổi;
- So sánh bằng cùng **workload, heap/native memory limit, CPU quota, warm-up và latency SLO**.

**Không khuyến nghị đổi collector như phương án đầu tiên cho một application có retention leak hoặc queue không giới hạn.** Dù dùng collector nào, objects còn reachable vẫn không thể được GC tự ý xóa.

## 12. Quan hệ với CPU, throughput và tail latency

Low-latency GC là một phần của hệ thống cân bằng:

| Khi bạn thay đổi | Thường giúp | Có thể đánh đổi |
| --- | --- | --- |
| Giảm unnecessary allocations | Ít GC work/churn | Thêm complexity nếu tối ưu quá tay |
| Giới hạn caches/queues | Live set và headroom ổn định | Cache misses, throughput hoặc throughput bursts cần kiểm |
| Tăng Xmx hợp lý | Nhiều headroom, giảm stall/Full GC risk | Memory cost, container OOM nếu thiếu physical RAM |
| Dùng collector concurrent hơn | STW pause thường ngắn hơn | Thêm GC CPU/concurrent work, throughput trade-off |
| Điều chỉnh pause target G1 thấp hơn | GC cố làm ngắn từng pause | Nhiều pauses/overhead hơn; không bảo đảm target |
| Giảm batch size | Peak live set và peak allocation | Có thể tăng per-item overhead |
| Tăng số workers/parallel requests | Throughput khi đủ tài nguyên | Nhiều live request objects, allocation bursts, GC/CPU pressure |
| Object pooling có kiểm soát | Giảm một số allocations đắt | Tăng live set, contention, memory retention |
| Bật JFR profile/allocation instrumentation | Tìm hotspots | Recording CPU/disk overhead |

**Chỉ tối ưu sau khi định nghĩa metric đích**: p99 response time, pause max, allocation stall frequency, throughput, RPS, CPU cost/request, memory footprint và OOM risk. Một cải thiện ở “GC pause p99” có thể không cải thiện “HTTP p99” nếu allocation stalls hoặc downstream I/O mới là bottleneck.

## 13. Đo allocation rate: phân biệt nguồn đo và giới hạn

### 13.1. Cách nhìn có tính thực dụng

- **JFR allocation events/sampling:** xác định allocation hotspots/classes/stack. `jdk.ObjectAllocationSample` hoặc các TLAB allocation-related events có thể được hỗ trợ/tùy version; **không** mặc định tổng event counts bằng tổng objects cấp phát.
- **GC logs:** cho biết heap occupancy transitions, young collections và patterns; có thể ước lượng allocation churn khi hiểu collector, nhưng không tự là chính xác “mọi byte allocated” trong interval.
- **HotSpot `ThreadMXBean`:** `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(...)` có thể đo số bytes cấp phát bởi thread cụ thể; đây là extension JDK có điều kiện, không portable giữa mọi JVM.
- **Application instrumentation:** đếm payload array buffers requested/objects do code biết; **không** tính chính xác mọi object overhead/JIT-eliminated allocations của JVM.
- **Profilers:** một số công cụ hỗ trợ allocation sampling và weighted estimates; xem semantics từng profiler.

**Nhớ phân biệt “attempted payload bytes” với “actual allocated heap bytes”.** Mỗi Java array còn có headers, alignment, metadata; compiler/JIT có thể tối ưu allocations, GC thậm chí có thể phát sinh internal allocations.

### 13.2. Cửa sổ đo

~~~text
t0 ---- 1 second ---- t1
Thread allocated bytes(t1) - bytes(t0) = allocated bytes trong window

MiB/s = (deltaBytes / 1_048_576) / (deltaNanos / 1e9)
~~~

Nếu đo vài microseconds, JIT compilation, clock resolution, scheduler noise và warm-up có thể làm giá trị cực kỳ biến động. Dùng nhiều intervals, percentiles, representative traffic, tập trung vào **peak-rate** đủ có ý nghĩa.

### 13.3. Đừng suy từ file JFR “0 allocations” khi sampling tắt

Nếu profile recording không bật allocation events, hoặc threshold/sampling bỏ sót, file có thể không có mẫu allocation dù ứng dụng liên tục tạo objects. Hãy ghi rõ **metric unavailable** thay vì cho rằng tốc độ cấp phát bằng 0.

## 14. Đo live set: after-GC occupancy chỉ là proxy

Có ba bước đo khác nhau:

1. **Snapshot tức thời**: `MemoryMXBean.getHeapMemoryUsage().getUsed()`; dễ lấy nhưng chứa objects chết chưa GC.
2. **After-GC occupancy/trend**: GC logs và JFR `GCHeapSummary`, biểu đồ qua nhiều cycles/long-run stable traffic. Đây là proxy tốt hơn cho live-set pressure, nhưng không hoàn hảo.
3. **Retained object graph**: heap dump và paths-to-GC-roots khi cần tìm **ai** giữ references; thao tác có thể gây pause, I/O lớn và chứa dữ liệu nhạy cảm.

### Một ví dụ phân biệt

Nếu trước GC heap là `2.7GiB` và sau một GC là `0.9GiB`, khoảng `1.8GiB` đã được collector reclaim hoặc thay đổi theo phase. Không có nghĩa tất cả 1.8GiB objects được tạo từ một method cụ thể. Nếu after-GC vẫn tăng từ 0.9 → 1.2 → 1.6GiB qua nhiều giờ tại cùng workload, cần kiểm **cache growth, queue backlog hoặc leak**.

### System.gc() không phải công cụ GC tuning production

Có thể dùng `System.gc()` **trong fixture có kiểm soát** để yêu cầu collection trước một snapshot, nhưng JVM có thể bỏ qua/cấu hình khác; trong production nó có thể gây pause dài, kể cả Full GC. **Không gọi System.gc thường xuyên** để “lấy lại headroom” thay vì xử lý allocation/retention.

## 15. Đo headroom: Java heap không phải tất cả RAM

### MemoryMXBean

~~~java
MemoryUsage usage =
        ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage();

long used = usage.getUsed();
long committed = usage.getCommitted();
long max = usage.getMax();

long optimisticHeadroom =
        max < 0 ? -1 : Math.max(0, max - used);
~~~

**Đoạn minh họa** trong method; cần imports `java.lang.management.ManagementFactory` và `MemoryUsage`. `max=-1` nghĩa JVM không xác định được maximum cho memory pool/heap trong context đó, không được tính chênh lệch trực tiếp.

### Vì sao vẫn có thể OOM kill khi headroom dương?

Ví dụ container memory limit `=2GiB`, `-Xmx=1.8GiB` và còn:

- Code cache, metaspace/class metadata;
- Thread stacks/native memory;
- Direct ByteBuffers, compression/native libraries;
- JIT, GC metadata, memory-mapped files;
- I/O buffers và overhead khác của process.

JVM có thể bị OS/cgroup OOM kill dù Java heap chưa chạm Xmx. Vì vậy **container memory headroom** là bài toán riêng. Đo `RSS`/cgroup usage, native memory tracking (nếu được bật), non-heap metrics và hard limit.

### Native Memory Tracking là dữ liệu bổ trợ

Trên các HotSpot JDK hỗ trợ, Native Memory Tracking (NMT) có thể cung cấp phân tích native allocations đã được theo dõi. Nó thường cần bật từ startup và có overhead; không được coi là phép đếm toàn bộ native allocations từ mọi thư viện ngoài JVM.

**Đừng chỉ nhìn biểu đồ “heap used” rồi đưa Xmx sát container limit.**

## 16. Demo Java 11: cùng 192 MiB allocations, live set khác nhau

Bài thực hành sử dụng **G1 với `-Xmx96m`**. Hai pha đều tạo ra **3.072 arrays × 64 KiB = 192 MiB payload bytes**. Tuy nhiên:

- **Pha transient:** không giữ các arrays sau vòng lặp, do đó sau khi GC có cơ hội reclaim, retained payload của fixture là 0.
- **Pha retained:** giữ **một trên 16 arrays**, tương đương **192 × 64 KiB = 12 MiB** payload còn reachable từ một `List` tĩnh.
- **Pha release:** xóa references trong list rồi yêu cầu GC cho mục đích test.

**Không** dùng đây làm benchmark so sánh collectors: workload là synthetic, ngắn, không có p99 request, và `System.gc()` chỉ xuất hiện trong fixture.

Tạo file **`GcHeadroomLab.java`**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class GcHeadroomLab {
    private static final int CHUNK = 64 * 1024;
    private static final int COUNT = 3_072;       // 192 MiB / phase
    private static final int KEEP_EVERY = 16;     // 12 MiB retained
    private static final long MIB = 1024L * 1024L;

    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile byte[] escape;

    private static long collectionCount() {
        long count = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionCount();
            if (value >= 0) {
                count += value;
            }
        }
        return count;
    }

    private static long allocate(boolean keepSome) {
        long start = System.nanoTime();

        for (int i = 0; i < COUNT; i++) {
            byte[] block = new byte[CHUNK];
            block[0] = (byte) i;
            block[block.length - 1] = (byte) (i >>> 8);

            // Biến volatile giữ allocations quan sát được.
            escape = block;

            if (keepSome && i % KEEP_EVERY == 0) {
                RETAINED.add(block);
            }
        }

        escape = null;
        return System.nanoTime() - start;
    }

    private static void snapshot(String label) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();

        long max = heap.getMax();
        long used = heap.getUsed();

        String headroom = max < 0 ? "unknown"
                : String.format(Locale.ROOT, "%.1f",
                        Math.max(0L, max - used) / (double) MIB);

        System.out.printf(Locale.ROOT,
                "%s.usedMiB=%.1f%n",
                label, used / (double) MIB);
        System.out.println(
                label + ".approxHeadroomMiB=" + headroom);
    }

    private static void requestedGcForDemo()
            throws InterruptedException {
        // Chỉ cho fixture: không khuyến nghị gọi trong production.
        // JVM có thể bỏ qua hoặc xử lý System.gc() khác nhau.
        System.gc();
        Thread.sleep(150);
    }

    public static void main(String[] args) throws Exception {
        long max = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getMax();

        System.out.printf(Locale.ROOT,
                "heap.maxMiB=%.1f%n", max / (double) MIB);

        long before = collectionCount();
        long transientNanos = allocate(false);
        requestedGcForDemo();

        System.out.println(
                "transient.requestedPayloadMiB=192");
        System.out.println(
                "transient.retainedPayloadMiB=0");

        System.out.printf(Locale.ROOT,
                "transient.payloadRateMiBps=%.1f%n",
                192.0 / (transientNanos / 1_000_000_000.0));

        System.out.println(
                "transient.gcCountDelta="
                        + (collectionCount() - before));
        snapshot("transient");

        before = collectionCount();
        long retainedNanos = allocate(true);
        requestedGcForDemo();

        long retainedBytes =
                (long) RETAINED.size() * CHUNK;

        System.out.println(
                "retained.requestedPayloadMiB=192");
        System.out.println(
                "retained.retainedPayloadMiB="
                        + retainedBytes / MIB);

        System.out.printf(Locale.ROOT,
                "retained.payloadRateMiBps=%.1f%n",
                192.0 / (retainedNanos / 1_000_000_000.0));

        System.out.println(
                "retained.gcCountDelta="
                        + (collectionCount() - before));
        snapshot("retained");

        RETAINED.clear();
        requestedGcForDemo();

        System.out.println(
                "release.retainedPayloadMiB=0");
        snapshot("release");
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 11 GcHeadroomLab.java
java -Xms96m -Xmx96m -XX:+UseG1GC GcHeadroomLab
~~~

Nếu dùng trực tiếp JDK 11, `javac GcHeadroomLab.java` cũng hợp lệ. `-Xms/-Xmx` 96 MiB là **kích thước bài thử**, không phải hướng dẫn dùng heap 96 MiB cho mọi ứng dụng. Trong production chọn heap theo live set, allocation bursts và native/container memory budget.

### Stdout đã chạy và kiểm chứng trên một HotSpot JDK

~~~text
heap.maxMiB=96.0
transient.requestedPayloadMiB=192
transient.retainedPayloadMiB=0
transient.payloadRateMiBps=9068.8
transient.gcCountDelta=5
transient.usedMiB=1.5
transient.approxHeadroomMiB=94.5
retained.requestedPayloadMiB=192
retained.retainedPayloadMiB=12
retained.payloadRateMiBps=12212.5
retained.gcCountDelta=4
retained.usedMiB=13.5
retained.approxHeadroomMiB=82.5
release.retainedPayloadMiB=0
release.usedMiB=1.5
release.approxHeadroomMiB=94.5
~~~

**Đây là stdout của MỘT lượt chạy đã kiểm, không phải output cố định:** MiB/s, GC count, usedMiB và headroom sẽ khác theo hardware, JIT, JVM, OS và khả năng xử lý `System.gc()`. Các dòng **requestedPayloadMiB=192**, **transient.retainedPayloadMiB=0**, **retained.retainedPayloadMiB=12** và **release.retainedPayloadMiB=0** xuất phát trực tiếp từ logic fixture nên có thể kiểm bằng code.

### Những kết luận hợp lệ từ thí nghiệm

1. Hai pha đều yêu cầu tạo **192 MiB payload** trong tổng số arrays, dù heap max chỉ **96 MiB**. Điều này **không mâu thuẫn** vì objects transient có thể bị reclaim và vùng nhớ được dùng lại nhiều lần.
2. Pha transient không giữ references sau loop; used heap snapshot sau request GC của một lượt thử là ~1.5 MiB.
3. Pha retained giữ 12 MiB payload; used heap sau request GC của lượt thử là ~13.5 MiB, cao hơn do objects giữ sống.
4. Khi live data tăng, khoảng `Xmx-used` của snapshot giảm (~94.5 → ~82.5 MiB), nhưng **đây là optimistic arithmetic headroom**, không phải toàn bộ vùng trống chắc chắn cấp phát được.
5. Sau khi xóa references, used heap giảm trong lượt chạy thử; việc giải phóng thực tế vẫn phụ thuộc GC, không bảo đảm ngay sau `clear()`.
6. Hai giá trị payloadRateMiBps là tốc độ **requested byte-array payload**, không phải tất cả JVM allocations; các objects phụ/JIT/alignment không được phản ánh.
7. `gcCountDelta` từ `GarbageCollectorMXBean` chỉ là counter của collectors có báo cáo; không đo chính xác pauses, GC CPU hay tất cả concurrent phases.
8. `System.gc()` chỉ được gọi nhằm làm snapshot sau yêu cầu GC trong lab. JVM có thể bỏ qua hoặc tiến hành khác, và không nên dùng nó định kỳ trong code production.

**Để đo gần chính xác allocation bytes của một thread trên HotSpot**, dùng ví dụ tiếp theo.

## 17. Demo Java 11: đo thread allocated bytes bằng MXBean

`com.sun.management.ThreadMXBean` là **HotSpot/JDK management extension** (không phải hợp đồng của mọi JVM). Khi được hỗ trợ, `getThreadAllocatedBytes(threadId)` cho bytes được cấp phát bởi một Java thread; dùng chênh lệch hai mẫu cùng thread và elapsed nanoseconds để ước lượng **MiB/s**.

Tạo file **`ThreadAllocationRateDemo.java`**:

~~~java
import java.lang.management.ManagementFactory;

public class ThreadAllocationRateDemo {
    private static volatile byte[] escape;

    public static void main(String[] args) {
        java.lang.management.ThreadMXBean platform =
                ManagementFactory.getThreadMXBean();

        if (!(platform instanceof com.sun.management.ThreadMXBean)) {
            System.out.println("threadAllocation.supported=false");
            return;
        }

        com.sun.management.ThreadMXBean bean =
                (com.sun.management.ThreadMXBean) platform;

        if (!bean.isThreadAllocatedMemorySupported()) {
            System.out.println("threadAllocation.supported=false");
            return;
        }

        if (!bean.isThreadAllocatedMemoryEnabled()) {
            bean.setThreadAllocatedMemoryEnabled(true);
        }

        long id = Thread.currentThread().getId();
        long before = bean.getThreadAllocatedBytes(id);
        long start = System.nanoTime();

        for (int i = 0; i < 2048; i++) {
            byte[] a = new byte[64 * 1024];
            a[0] = (byte) i;
            escape = a;
        }

        escape = null;
        long elapsed = System.nanoTime() - start;
        long after = bean.getThreadAllocatedBytes(id);

        if (before < 0 || after < before) {
            System.out.println("threadAllocation.available=false");
            return;
        }

        double rate = (after - before)
                * 1_000_000_000.0 / elapsed
                / (1024.0 * 1024.0);

        System.out.println("threadAllocation.supported=true");
        System.out.println(
                "threadAllocation.bytesPositive=" + (after > before));
        System.out.println(
                "threadAllocation.rateMiBpsPositive=" + (rate > 0));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 11 ThreadAllocationRateDemo.java
java -Xmx96m ThreadAllocationRateDemo
~~~

Stdout đã được kiểm trên HotSpot runtime có hỗ trợ thread allocation MXBean:

~~~text
threadAllocation.supported=true
threadAllocation.bytesPositive=true
threadAllocation.rateMiBpsPositive=true
~~~

**Không coi ba dòng này là output bất biến trên mọi JVM**: code kiểm `instanceof`/`isThreadAllocatedMemorySupported()`, và các JVM không hỗ trợ sẽ in `supported=false`. Việc bật theo dõi có thể chịu policy/quyền/overhead; code production cần kiểm lỗi/khả năng hỗ trợ.

### Hạn chế phép đo

- Đây là **allocation của thread đang đo**, không phải tổng process khi có nhiều threads.
- MiB/s của một vòng 2.048 allocations ngắn có thể cao bất thường vì microbenchmark warm-up/cache/JIT; không dùng làm capacity planning.
- Không đo live set hay heap retention.
- Khi JIT escape analysis loại bỏ allocation, số đo có thể thấp hơn số dòng `new` trong source; fixture dùng `volatile escape` để làm allocations có thể quan sát.
- Một số JVM không hỗ trợ extension này hoặc không cho bật tracking; dùng JFR/profiler/metrics phù hợp thay thế.
- Để báo cáo production, lấy mẫu theo cửa sổ dài đủ ý nghĩa trên **các thread mục tiêu** và so CPU/GC/p99 cùng lúc.

## 18. GC unified logging từ Java 11

Java 11 dùng **Unified JVM Logging**, ví dụ:

~~~bash
java -Xms96m -Xmx96m -XX:+UseG1GC -Xlog:gc*,safepoint=info GcHeadroomLab
~~~

Lệnh đã được kiểm **về cú pháp JVM logging** trên JDK cục bộ. Nếu muốn ghi ra file trong hệ thống thật:

~~~bash
java -Xms96m -Xmx96m -XX:+UseG1GC -Xlog:gc*,safepoint=info:file=gc.log:uptime,level,tags GcHeadroomLab
~~~

**Lệnh minh họa**: đảm bảo thư mục ghi được, đặt file rotation/retention nếu chạy lâu. Không biến log volume `gc*=trace` thành mặc định production.

### Đọc kết quả GC log đúng

Một dòng kiểu:

~~~text
GC(12) Pause Young (Normal) (G1 Evacuation Pause) 75M->30M(96M) 3.5ms
~~~

**Ví dụ định dạng minh họa, không phải stdout đã đo**:

- `75M`: used trước GC;
- `30M`: used sau GC;
- `96M`: heap size trong log ở thời điểm đó;
- `3.5ms`: pause được ghi cho sự kiện đó.

Không coi `30M` là live set hoàn hảo cho cả process/forever; phải xem collector/event semantics, các cycles khác và workload. Nhưng biểu đồ after-GC occupancy rất hữu ích để phát hiện live-set pressure.

### Những dấu hiệu cảnh báo

- Young GCs dày hơn tại cùng RPS;
- After-GC occupancy tăng theo thời gian;
- Old generation/promotions tăng, concurrent marking không xong kịp;
- G1 evacuation failure hoặc Full GC;
- GC pauses dài hơn SLO;
- Allocation stalls của concurrent collector;
- Container memory pressure/RSS tăng dù heap usage trông bình thường.

Tên chính xác của events/phrases khác giữa G1, ZGC và các JDK updates; luôn kiểm `java -version` và GC log format của runtime mục tiêu.

## 19. JFR: quan sát allocation và live set theo thời gian

JFR phù hợp ghi events theo timestamp, có overhead kiểm soát:

- `jdk.GarbageCollection` và các `jdk.GCPhasePause`/phase events cho GC timeline và pauses;
- `jdk.GCHeapSummary` cho snapshot heap quanh GC, thường có `heapUsed`/`gcId`/`when` tùy schema;
- `jdk.ObjectAllocationSample` hoặc allocation-related events được hỗ trợ trên bản JDK để tìm **allocation sites**;
- `jdk.CPULoad` và execution samples giúp biết GC/ứng dụng tranh CPU trong cùng cửa sổ;
- Custom events có thể bổ sung checkpoint thời điểm tăng queue/backlog hoặc burst.

**Không suy raw event count ra bytes/s** nếu đây là event lấy mẫu hoặc threshold-based. Cần theo đúng event schema/weights và tool semantics.

### Cấu hình recording bounded từ JVM đang chạy

~~~bash
jcmd <PID> JFR.start name=GCDiagnostics settings=profile duration=60s filename=/secure/gc-diagnostics.jfr
~~~

**Lệnh minh họa**, cần JVM có attach, PID đúng, quyền file và đã đánh giá overhead. `settings=profile` thích hợp điều tra ngắn, trong khi `default` thường tốt hơn cho bounded continuous diagnostics.

### Đọc file

~~~bash
jfr summary /secure/gc-diagnostics.jfr
jfr print --events jdk.GarbageCollection /secure/gc-diagnostics.jfr
jfr print --events jdk.GCPhasePause /secure/gc-diagnostics.jfr
jfr print --events jdk.GCHeapSummary /secure/gc-diagnostics.jfr
~~~

`JDK Mission Control` là GUI phân tích JFR, phân phối riêng; giúp xem GC pauses/allocations/CPU theo **time window** và nhận diện pha có pressure. Không coi JFR recording mặc định đã ghi mọi allocation sites; kiểm event settings.

## 20. Headroom và container memory: hai mức “sống còn”

### Cùng Xmx nhưng giới hạn OS khác

Giả sử hai pods đều cấu hình `-Xmx=4GiB`:

- Pod A có cgroup memory limit 6 GiB và native memory usage 700 MiB;
- Pod B có limit 4.3 GiB nhưng native usage có thể tăng >500 MiB.

Dù cùng Java heap headroom, B dễ gặp container OOM kill hơn khi heap commit thêm. Vì vậy:

1. Xác nhận JVM đang nhìn thấy cgroup/container limit đúng;
2. Đọc process RSS, cgroup usage và peak;
3. Đo native memory, direct buffers, metaspace và thread stacks;
4. Chọn `Xmx` đủ cho live set + headroom GC nhưng **không nuốt toàn bộ container memory**;
5. Cân nhắc thay đổi worker count/stack size/native libraries khi ảnh hưởng RAM;
6. Đừng tăng heap theo phản xạ nếu process đã chạm hard memory limit.

### Xms/Xmx có tác dụng khác nhau

- `-Xmx`: maximum heap; là trần cần xét cho allocation headroom.
- `-Xms`: initial/minimum heap commitment policy của JVM; lựa chọn ảnh hưởng startup, commit/uncommit latency và footprint.
- `-Xms=-Xmx` có thể hữu ích cho vài low-latency workloads đã được benchmark, nhưng tăng committed footprint và container pressure.
- ZGC hiện đại có các cơ chế uncommit/adaptive heap sizing tùy JDK version; phải cân nhắc latency vs footprint, không áp dụng tất cả flags ở mọi JVM.

**Tăng Xmx không sửa memory leak**, chỉ kéo dài thời gian tới khi heap đầy nếu retained graph vẫn tăng vô hạn.

## 21. Runbook: điều tra allocation pressure và headroom

### Bước 1 — xác nhận vấn đề

Đo cả **p95/p99 service latency**, GC pause max/p99, throughput, CPU%, heap after GC, allocation rate/bursts, OOM/restart count.

Nếu p99 cao nhưng không trùng GC/stall, đừng tự quy cho GC: có thể do DB, network, lock, queue hoặc CPU scheduling.

### Bước 2 — xác định live set

- Quan sát after-GC occupancy qua nhiều GC cycles sau warm-up;
- So với RPS và số sessions/connections/cached records;
- Tìm trend tăng không hồi phục;
- Nếu cần biết ai giữ references, dùng heap dump+GC roots có kiểm soát.

### Bước 3 — đo allocation rate theo cửa sổ

- Bắt đầu từ 1–5 giây quanh spike và các cửa sổ baseline;
- Dùng JFR allocation/profiler phù hợp hoặc HotSpot thread allocated bytes;
- Tách short-lived churn và long-lived promotions;
- Xem correlation với requests/s và serialized payload sizes.

### Bước 4 — xác định headroom thực tế

- Tính `Xmx−used` để có dấu hiệu, nhưng không coi là free bytes chắc chắn;
- Kiểm G1 region/evacuation/humongous space hoặc concurrent-collector allocation stalls;
- Kiểm native/cgroup limit;
- Xem concurrent GC cycle duration và burst rate.

### Bước 5 — can thiệp theo nguyên nhân

- Allocation quá lớn: giảm temporary object churn sau profiling, giới hạn batch, stream thay vì materialize;
- Live set quá lớn: giới hạn caches/queues, TTL, ownership cleanup, giảm số in-flight requests;
- GC cần thêm không gian: cân nhắc tăng Xmx trong budget/container;
- Collector/GC concurrency: thử lựa chọn/tuning dựa trên JDK/CPU support;
- CPU quota thấp: đánh giá GC CPU có đang cạnh tranh với requests;
- Kiểm load shedding/backpressure để giảm burst khi tài nguyên chật.

### Bước 6 — benchmark và rollout an toàn

- So baseline ở cùng RPS, payload distribution, CPU quota và container limit;
- Warm up JIT, caches và connection pools trước;
- Chạy steady-state **và burst** đủ dài để lộ delayed retention;
- Đo p99, throughput, GC pauses, stalls, Full GCs, after-GC heap, allocation rate, RSS;
- Có rollback guardrails nếu OOM, latency hoặc throughput xấu hơn.

## 22. Bốn bài toán minh họa

### A. Churn cao, live set thấp

Service JSON tạo 1.5 GiB short-lived objects mỗi giây; after-GC live set chỉ 500 MiB. Nếu heap có headroom rộng, collector có thể xử lý ổn định nhưng vẫn tiêu tốn GC CPU/throughput. Ưu tiên tối ưu **hot allocation sites**, tránh pooling vô hạn làm live set tăng.

### B. Churn vừa, live set tăng theo giờ

Cache không eviction làm after-GC occupancy tăng dần 0.8 → 1.5 → 2.2 GiB dưới Xmx=3 GiB. Dù allocation rate trung bình không đổi, headroom bị thu hẹp theo thời gian. Tăng heap chỉ kéo dài sự cố; cần xác định chính sách giữ objects.

### C. Burst allocation và concurrent collector

Ứng dụng có 2 GiB headroom bình thường, nhưng chạy batch làm allocation tăng gấp nhiều lần trong 2 giây và GC reclaim chưa kịp. Dù pauses đều rất ngắn, allocation stalls và request p99 có thể tăng. Giảm concurrency/batch size hoặc tăng headroom hợp lý sau đo đạc.

### D. G1 Full GC khi old generation chật

Old live set lớn, nhiều humongous allocations, concurrent marking không kịp hoàn tất. G1 có thể gặp evacuation failure hoặc Full GC. Đừng chỉ chỉnh pause target; kiểm allocation/promotions, live data, humongous objects và vùng đích evacuation, rồi mới tuning.

Các số liệu kịch bản đều **giả định** để giải thích quan hệ, không phải kết quả chuẩn của collector.

## 23. Lỗi và hiểu lầm thường gặp

| Nhầm lẫn | Vì sao sai | Sửa thế nào |
| --- | --- | --- |
| “Allocation rate cao tức memory leak.” | Nhiều objects có thể chết nhanh | Xem after-GC live set và references |
| “Heap used = live set.” | Used chứa garbage chưa reclaim | So after-GC trend, heap dump khi cần |
| “`Xmx-used` là headroom cấp phát chắc chắn.” | GC reserve/fragmentation/concurrent work/cgroup | Đo GC events và actual failures |
| “Bộ nhớ heap còn trống nên pod không OOM kill.” | Native/OS/cgroup memory có giới hạn khác | Đo RSS/non-heap/cgroup |
| “Pause thấp = HTTP p99 thấp.” | Allocation stalls, CPU, I/O, locks vẫn gây latency | End-to-end latency + stall events |
| “Chỉ cần tăng `Xmx` là giải quyết leak.” | References vẫn bị giữ | Sửa ownership/retention |
| “Full GC là lỗi của collector.” | Có thể do live set quá lớn/evacuation failure | Xem nguyên nhân và workload |
| “Giảm `MaxGCPauseMillis` là bảo đảm pause ngắn.” | Đây là soft target G1 | Benchmark và theo dõi trade-offs |
| “ZGC không cần headroom vì concurrent.” | Mutator tiếp tục cấp phát trong GC | Tính peak allocation/cycle time/reserve |
| “ZGC hiện đại cần `-XX:+ZGenerational`.” | Flag đã bị loại từ JDK24 | Dùng flags của JDK hiện tại |
| “Shenandoah có ở mọi JDK11.” | Availability khác theo vendor/build | Kiểm `java -version`/supported collectors |
| “GC logs dạng Java 8 là chuẩn Java11+.” | Java 9+ dùng unified logging | Dùng `-Xlog` |
| “Một `System.gc()` cho live set chính xác.” | JVM có thể ignore/phase behavior khác | Xem trend nhiều cycles; lab only |
| “JFR allocation sample count = total allocations.” | Sampling và threshold | Đọc schema/weights, dùng metrics chính xác khi có |
| “After-GC occupancy tăng một lần = leak.” | Cache warm-up/trafﬁc/GC semantics | Trend dưới tải tương đương |
| “MiB/s một microbenchmark = production allocation rate.” | JIT/warm-up/short interval sai lệch | Đo application thật |
| “Object pool luôn giảm GC pressure.” | Pool có thể giữ live objects và gây contention | Bounded pool chỉ sau đo |
| “G1 region size phải chỉnh bằng tay.” | Heuristics hiện đại thường phù hợp | Chỉ tune khi log/benchmark chỉ ra |
| “Một headroom % cố định hợp mọi workload.” | Rate/burst/cycle khác nhau | Model rồi validate dưới burst |
| “Thấy GC nhiều là request chậm vì GC.” | Cần correlation time window | Dùng JFR/traces/metrics cùng lúc |

## 24. Ma trận kiểm thử và xác nhận

| Test | Điều kiện kiểm | Kỳ vọng |
| --- | --- | --- |
| Java 11 compatibility | `javac --release 11` | Demo compile |
| Cùng payload allocation | Hai pha 3.072×64KiB | In `requestedPayloadMiB=192` ở cả hai |
| Transient retention | Không lưu arrays vào list | `retainedPayloadMiB=0` |
| Retained fixture | Giữ 1/16 arrays | `retainedPayloadMiB=12` |
| Release | `RETAINED.clear()` | Payload retained do fixture về 0 |
| GC availability | `GarbageCollectorMXBean` | Không crash khi một bean báo -1 count |
| Heap max | `MemoryUsage.getMax()` | Kiểm trần/unknown, không đoán |
| Headroom snapshot | `max-used` | Báo là optimistic, không guarantee |
| Thread allocation HotSpot | `ThreadMXBean` supported | Delta bytes >0 khi fixture thực cấp phát |
| Alternative JVM | Extension không supported | In supported=false, không giả lập số liệu |
| GC logging | `-Xlog:gc*,safepoint=info` | JVM chấp nhận syntax |
| Steady-state traffic | 10–30 phút hoặc theo mục tiêu | Live set/headroom stabilizes |
| Burst traffic | Spike gần peak production | Không có allocation stalls/OOM ngoài SLO |
| Cache growth | Tăng số keys/sessions | Sau GC occupancy có giới hạn |
| Container memory | Xmx + non-heap dưới limit | Không OOM kill, RSS có margin |
| G1 evacuation failure | Tải cao, ít free regions | Quan sát logs, không bỏ qua |
| ZGC test | JDK có Generational ZGC | Kiểm allocation stalls và p99, không chỉ pause |
| Collector upgrade | JDK update | Re-run với cùng workload và quota |
| JFR analysis | Bounded recording | Event settings và time window minh bạch |
| Rollback | Canaries/alerts | Có điều kiện dừng rollout nếu latency/memory xấu |

### Các số đo không nên hardcode

GC count, GC time, usedMiB, allocation MiB/s, after-GC occupancy, CPU usage và số events JFR **đều thay đổi** theo OS, JDK, collector, workload và schedule. Test nên xác nhận **logic deterministic của fixture**, còn hiệu năng cần so **xu hướng/threshold dưới cùng điều kiện**.

## 25. Checklist trước khi kết luận “GC đã được tối ưu”

- [ ] Allocation rate có cả average **và burst peak** theo cửa sổ thực tế.
- [ ] Live set được đánh giá bằng after-GC occupancy **trong nhiều cycles**.
- [ ] Biết `-Xmx`, committed heap, used heap và container hard memory limit.
- [ ] Có headroom cho burst, GC work và collector reserves; không chỉ `Xmx≈live set`.
- [ ] Cgroup/RSS/non-heap không ở sát limit khi heap tăng.
- [ ] Biết GC đang dùng thực sự: G1/ZGC/Shenandoah, JDK/vendor/version.
- [ ] Không áp dụng flags mới vào Java11 hoặc flags legacy lên JDK hiện đại.
- [ ] Có GC logs `-Xlog` hoặc JFR timeline với cấu hình đã ghi nhận.
- [ ] Theo dõi p95/p99 service latency **cùng** GC pause, stall, GC CPU.
- [ ] Không coi GC collection duration toàn bộ là STW duration.
- [ ] Có kế hoạch xử lý caches/queues/retained references nếu live set tăng.
- [ ] Có benchmark steady-state, burst và long-run để lộ memory retention.
- [ ] Không dùng `System.gc()` thường xuyên để cố giữ heap thấp.
- [ ] Không phát triển object pools không giới hạn chỉ để giảm allocations.
- [ ] Có capacity/rollout/rollback nếu thay Xmx hoặc collector.
- [ ] Có quy trình bảo vệ JFR/heap dump chứa thông tin nhạy cảm.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** Một service cấp phát 10 GiB objects trong một phút nhưng after-GC heap chỉ quanh 500 MiB. Có chắc memory leak không?

**Không.** Tốc độ cấp phát có thể cao nhưng objects chết nhanh. Vẫn cần quan sát GC CPU/pauses, nhưng leak đòi dấu hiệu retained objects không hợp lý.

**Câu 2.** Với `-Xmx=8GiB`, used heap 6GiB, ứng dụng có chắc còn đúng 2GiB cấp phát an toàn?

**Không.** Đây là chênh số học lạc quan; collector reserves, fragmentation, regions, memory commitment và OS/cgroup có thể làm khả năng thực tế thấp hơn.

**Câu 3.** Collector có pause 1ms nhưng HTTP p99 tăng đến 2s, GC chắc vô can?

**Chưa.** Có thể có allocation stalls hoặc GC CPU pressure, nhưng cũng có thể là I/O/lock. Cần cùng timeline và metrics.

**Câu 4.** Tăng live set từ 1 GiB lên 3 GiB dưới cùng Xmx và allocation rate làm headroom thế nào?

**Thu hẹp**, khiến hệ thống chịu burst kém hơn và có thể làm collector phải reclaim thường xuyên/khó hơn.

**Câu 5.** Vì sao peak allocation rate quan trọng hơn average cho tail latency?

**Vì** một burst ngắn có thể tiêu thụ headroom nhanh hơn GC tiến triển dù average cả phút vẫn thấp.

**Câu 6.** G1 `MaxGCPauseMillis=50` có bảo đảm từng pause ≤50ms không?

**Không.** Đây là soft goal; workload/copy live objects/heap pressure có thể khiến pause vượt.

**Câu 7.** Vì sao không dùng `-XX:+ZGenerational` trên JDK 24+?

**Vì** ZGC đã generational và flag chuyển tiếp này đã bị loại bỏ. Dùng đúng docs của runtime hiện tại.

**Câu 8.** `MemoryMXBean.used` sau một lần yêu cầu `System.gc()` có phải live set tuyệt đối?

**Không.** JVM có thể xử lý hoặc bỏ qua yêu cầu, còn collector/live definition khác nhau; xem trend và GC semantics.

**Câu 9.** Làm sao phân biệt CPU GC tăng do churn với retained leak?

**Đo** allocation rate, GC CPU, after-GC occupancy và GC roots khi cần. Churn cao có thể live set ổn định; leak có after-GC growth dai dẳng.

**Câu 10.** Có nên tăng Xmx sát cgroup memory limit vì heap cần headroom?

**Không.** Phải chừa chỗ cho native/off-heap, threads, metaspace và OS/kernel overhead.

**Câu 11.** ThreadMXBean có thể đo chính xác tổng allocation của mọi Java process trên mọi JVM?

**Không.** Extension có điều kiện và đo theo thread(s) được chọn; không mặc định portable.

**Câu 12.** Điều gì chứng minh tuning thành công?

**Có kết quả lặp lại** về end-to-end p99, pause/stall, throughput, heap/GC CPU và resource use dưới workloads tương đương, không phát sinh OOM hay regression.

## 27. Tài liệu hiện hành để tham khảo

1. [Oracle Java 11 — HotSpot Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/11/gctuning/): nguyên tắc GC, G1 và unified logging trong Java 11.
2. [Oracle Java 11 — Garbage-First Garbage Collector](https://docs.oracle.com/en/java/javase/11/gctuning/garbage-first-g1-garbage-collector3.html): G1 regions, live objects, young/mixed GC, evacuation failure và Full GC.
3. [Oracle Java 11 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/11/gctuning/garbage-collector-implementation.html): giải thích log `used-before → used-after (heap size)`.
4. [Oracle Java 11 — `java` tool và `-Xlog`](https://docs.oracle.com/en/java/javase/11/tools/java.html): logging `gc*,safepoint`, heap flags và diagnostic options.
5. [Oracle JDK 27 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html): hướng dẫn hiện hành về heap pressure, evacuation failure, Full GC và region heuristics.
6. [Oracle JDK 27 — HotSpot GC Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/): giới thiệu/so sánh collectors đang hỗ trợ.
7. [Oracle — Z Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/z-garbage-collector1.html): sizing `Xmx` theo live set, allocation rate và headroom; ghi chú ZGC generational từ JDK 24.
8. [Oracle JDK 26 — ZGC](https://docs.oracle.com/en/java/javase/26/gctuning/z-garbage-collector.html): quản lý headroom, concurrent GC, soft max trên ZGC hiện đại.
9. [Oracle — JDK 24 Migration: ZGC non-generational removal](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html): không dùng `-XX:+ZGenerational` trên JDK 24+.
10. [Java SE 11 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html) và [`MemoryUsage`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryUsage.html): used, committed, max.
11. [Java SE 11 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): collection count/time, giới hạn và ý nghĩa.
12. [Java SE 11 — `com.sun.management.ThreadMXBean`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): thread allocated bytes và khả năng hỗ trợ có điều kiện.
13. [Oracle Java 11 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html): JFR, JMC, jcmd, GC diagnostics và quan sát memory.
14. [OpenJDK JEP 490](https://openjdk.org/jeps/490): loại bỏ non-generational ZGC trong JDK 24.

**Kết luận:** Ba biến số có quan hệ chặt chẽ: **allocation rate** quyết định tốc độ tiêu thụ vùng cấp phát, **live set** quyết định mức bộ nhớ không thể thu hồi, và **heap headroom** quyết định hệ thống chịu được bao nhiêu work/burst trong khi GC chưa reclaim đủ. Muốn GC độ trễ thấp, hãy **giảm cấp phát dư, giữ live set có giới hạn, cấp headroom phù hợp với peak workload và tiến độ GC**, sau đó đo lại với JFR/GC logs và service p99. Chọn collector đúng phiên bản chỉ là một phần của lời giải; không một flag nào thay được capacity planning và kiểm thử thực tế.