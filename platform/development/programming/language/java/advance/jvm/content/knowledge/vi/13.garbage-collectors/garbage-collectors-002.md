# Parallel GC: thu gom song song hướng đến thông lượng trong HotSpot JVM

**Parallel GC**, còn gọi là **throughput collector**, là bộ thu gom rác **theo thế hệ (generational)** của HotSpot, tối ưu hướng tới việc chương trình dành nhiều thời gian thực hiện công việc ứng dụng và ít thời gian cho GC. Điểm khác biệt với Serial GC là **nhiều GC worker threads cùng thực hiện các công việc thu gom**, khai thác nhiều CPU cores; khác biệt với các bộ thu gom low-latency như G1/ZGC là Parallel GC ưu tiên **thông lượng tổng thể** hơn việc giới hạn từng khoảng dừng ngắn.

Trong bài này, “song song” **không** có nghĩa GC luôn chạy đồng thời với ứng dụng. Những pha thu gom chính của Parallel GC thuộc loại **stop-the-world (STW)**: các application threads (mutators) phải tạm dừng, **nhiều GC worker threads** xử lý cùng một pause. Đây là chỗ dễ nhầm nhất:

> **Parallelism của các GC workers** giúp rút bớt wall-clock time của một số công việc GC bằng nhiều CPU. **Concurrency với application threads** là đặc tính khác và không phải ý nghĩa của tên Parallel GC.

Với **HotSpot Java 17**, chọn collector này bằng `-XX:+UseParallelGC`. Collector cho phép JVM tự cân đối ba mục tiêu: **pause-time goal**, **throughput goal** và **heap footprint**, theo thứ tự ưu tiên được quy định bởi cơ chế ergonomics. Người học sẽ tìm hiểu young/old collections, copying/compaction, adaptive sizing, cờ cấu hình, GC logging và một ví dụ **Java 17+ chạy được** để tạo áp lực cấp phát nhưng có stdout ổn định.

## 1. “Parallel”, “concurrent”, “throughput” là ba thuật ngữ khác nhau

| Thuật ngữ | Ý nghĩa | Ví dụ trong GC |
| --- | --- | --- |
| **Parallel work** | Nhiều worker threads xử lý công việc GC cùng lúc | Parallel GC chia công việc truy vết/copy/compact cho nhiều GC threads |
| **Concurrent work** | Một phần công việc GC diễn ra khi application threads vẫn chạy | G1 concurrent marking, ZGC concurrent phases |
| **Stop-the-world** | Mutator/application threads tạm dừng để GC thực hiện công việc cần thiết | Young và old collections chính của Parallel GC |
| **Throughput** | Tỷ lệ thời gian JVM dành cho application work so với tổng thời gian application + GC được đo | 99% application time là một mục tiêu tỷ lệ, không phải SLA cho từng pause |
| **Pause time** | Khoảng thời gian ứng dụng tạm dừng vì GC ở một event | 300 ms STW GC có thể ảnh hưởng request latency |
| **Footprint** | Dung lượng heap mà chương trình/JVM sử dụng hoặc duy trì | Giảm heap có thể tiết kiệm memory nhưng tăng tần suất GC |

### 1.1. Sơ đồ một lần GC song song nhưng STW

```text
Time ─────────────────────────────────────────────────────────►

Application threads:
  Thread A: █████████████ │ PAUSED     │ ███████████████████
  Thread B: █████████████ │ PAUSED     │ ███████████████████
  Thread C: █████████████ │ PAUSED     │ ███████████████████

Parallel GC worker threads trong khoảng pause:
  GC W1:                │ mark/copy A │
  GC W2:                │ mark/copy B │
  GC W3:                │ mark/copy C │
  GC W4:                │ compact/... │

                        ↑ STW bắt đầu ↑     ↑ STW kết thúc
```

Trong pause, **công việc thu gom có thể chạy song song**, còn application threads không có cơ hội tiến hành code nghiệp vụ theo cách thông thường. Nhờ đó Parallel GC có thể xử lý heap nhanh trên máy nhiều cores; nhưng pause dài vẫn có thể khiến người dùng thấy request timeout hoặc frame drop.

Đừng phát biểu rằng “Parallel GC không có concurrency ở bất kỳ thread nào của JVM” theo nghĩa tuyệt đối: JVM còn có compiler/service threads và implementation activities riêng. Điều quan trọng là **Parallel GC không thiết kế việc thu gom heap chính theo hướng low-pause concurrency với mutators như các concurrent collectors**.

### 1.2. Giảm GC wall time khác giảm GC CPU work

Nếu một nhiệm vụ quét có lượng công việc W, tăng số workers có thể giảm **thời gian trên đồng hồ** của pause nhờ phân chia công việc; tổng **CPU work** không nhất thiết giảm, thậm chí có thêm scheduling/synchronization overhead. Vì vậy:

- 8 GC workers không bảo đảm pause nhanh đúng gấp 8 so với 1 worker.
- Heap nhỏ hoặc live set bé có thể không đủ việc để song song hóa hiệu quả.
- CPU quota của container, NUMA, memory bandwidth, cache contention và GC synchronization ảnh hưởng speedup.
- Quá nhiều workers có thể chiếm CPU của hệ thống và làm tệ một workload đang tranh chấp tài nguyên.

Parallelism là công cụ cải thiện throughput trên hardware phù hợp, **không phải hệ số tăng tốc tuyến tính được JVM bảo đảm**.

## 2. Parallel GC là collector theo thế hệ

Parallel GC quản lý Java heap theo **young generation** và **old generation**. Trong các triển khai HotSpot phổ biến:

- Young gồm **Eden**, Survivor From/To; phần lớn allocations mới được đặt ở Eden qua các cơ chế như TLAB.
- Young collection thường dùng thuật toán **copying/evacuation**: object không còn reachable không được copy, object còn sống được chuyển sang survivor hoặc promoted sang old.
- Old chứa những objects còn live đủ lâu hoặc được phân bổ/promoted theo collector policy.
- Old collection cần xác định objects còn sống và có thể **compact** để giảm phân mảnh, tái tạo không gian cấp phát.

```text
                       YOUNG
                     ┌──────────┐
new objects ────────►│  EDEN    │
                     └────┬─────┘
                          │ Young GC (Parallel Scavenge)
                    ┌─────┴──────┐
                    │            │
                garbage       live objects
                    │            │
                 reclaim         ▼
                           SURVIVOR (age++)
                                │
                        young GC tiếp theo
                                │
               threshold / survivor capacity / policy
                                ▼
                         OLD GENERATION
                                │
                         Old collection:
                         Parallel Old compacting
                                │
                         reclaim unreachable
```

**GC age không phải số giây tuổi đời object**. Nó thường đại diện số lần sống qua young copying theo collector. Threshold không nhất thiết cố định suốt quá trình, do adaptive policy điều chỉnh.

### 2.1. Minor/Young GC: Parallel Scavenge

Trong tài liệu HotSpot, phần young collector thường gọi là **Parallel Scavenge**. Khi vùng young cần thu gom:

1. JVM đi tới điểm an toàn để thực hiện STW collection.
2. Nhiều GC workers nhận các phần công việc khám phá liveness/copy objects.
3. GC xác định live objects từ root set và những references liên quan tới young.
4. Những objects không còn reachable không cần copy.
5. Những objects còn live được copy sang survivor space phù hợp hoặc promoted sang old theo chính sách.
6. GC có thể tái sử dụng phần lớn source Eden sau khi evacuation và cập nhật references.

Vì công việc dành cho young diễn ra song song, nhiều cores có thể giúp rút ngắn pause so với một worker, **nhưng toàn bộ pause vẫn cần được đo**. Đối với live set trẻ lớn, chi phí copy/promotion có thể cao.

### 2.2. Old GC: Parallel Old, compaction song song

Trong HotSpot Java 17, chọn `-XX:+UseParallelGC` thông thường cũng bật **parallel compaction** của old generation (Parallel Old). Đây là điều quan trọng: Parallel GC không chỉ song song hóa minor collections.

Old compaction có thể gồm:

- Xác định tập objects còn live và những references cần cập nhật.
- Lập kế hoạch vị trí đích của các objects sau compaction.
- Di chuyển/copy live objects theo những pha phù hợp.
- Cập nhật object references để khớp địa chỉ mới.
- Tạo lại free space đủ hữu ích cho những allocations sau.

Việc chia phase cụ thể là **implementation detail của HotSpot**, không phải một giao diện public Java. Điều cần nhớ: **parallel old collection cũng chủ yếu là STW**, và thường có thể pause dài khi old live set lớn.

Tài liệu Oracle Java 17 cho biết parallel compaction **được bật mặc định khi `UseParallelGC` được chọn**, và có thể tắt bằng `-XX:-UseParallelOldGC`. Tắt không có nghĩa “không thu gom Old”; nó thay đổi cơ chế thực hiện major/old collections, có thể gây regression về khả năng scale, nên không phải tùy chọn khuyến nghị dùng tùy tiện.

### 2.3. Survivor space và promotion pressure

Một object trẻ còn sống sau một Young GC thường đi từ Eden sang survivor hoặc old. Nếu survivor capacity không đủ hoặc object đạt ngưỡng tenuring, nó có thể được promoted.

```text
Eden:
   A live; B dead; C live; D dead

Young collection:
   B, D → garbage, không cần copy
   A, C → Survivor hoặc Old

Survivor → ở lại khi tuổi/policy phù hợp
Survivor → Old nếu promotion cần thiết

Old:
   vẫn được GC thu gom khi object không còn reachable;
   không phải vùng “vĩnh viễn”.
```

Một ứng dụng giữ rất nhiều temporary data qua nhiều GC cycles có thể tạo **premature promotion** và tăng old occupancy. Đây có thể là retention burst, không nhất thiết là leak. Khi điều tra, xem survival rate, bytes promoted, old occupancy và heap dump thay vì kết luận từ mỗi con số collections.

### 2.4. Không mặc định mọi `new` tạo object ở Eden

Có những đường allocation đặc biệt và JIT optimization:

- Một số allocations có kích thước hoặc điều kiện khác có thể được xử lý bằng slow path/old generation tùy collector policy.
- Escape analysis/JIT có thể tránh cấp phát heap object nếu tối ưu hợp lệ.
- TLAB dành cho allocations nhanh nhưng không phải “một generation thứ ba” của heap.

Mô hình Eden→Survivor→Old dùng để hiểu cơ chế chính, không phải hợp đồng địa chỉ cho mọi instance trên mọi JVM.

## 3. Tại sao Parallel GC hướng tới throughput?

**Throughput** trong GC ergonomics thường được đo theo tỷ lệ giữa thời gian xử lý ứng dụng và tổng thời gian ứng dụng cộng GC ở khoảng đo thích hợp:

```text
throughput = application_time / (application_time + gc_time)

GC_time_fraction = gc_time / (application_time + gc_time)

Nếu application_time = 9.9 s và gc_time = 0.1 s:
  throughput ≈ 99%
  GC fraction ≈ 1%
```

Đây là **mô hình tỷ lệ thời gian**, không phải đo CPU utilization của máy, số requests/second hoặc bytes allocated trực tiếp. Một ứng dụng có throughput thời gian cao vẫn có thể có requests/second thấp vì code nghiệp vụ chậm.

### 3.1. `GCTimeRatio` biểu diễn mục tiêu gì?

HotSpot hỗ trợ:

```bash
-XX:GCTimeRatio=N
```

Mục tiêu là **phần thời gian GC** xấp xỉ:

```text
gc_time_fraction = 1 / (1 + N)
application_time_fraction = N / (1 + N)

N = 99 → GC goal = 1/100 = 1%
         application goal ≈ 99%

N = 19 → GC goal = 1/20 = 5%
         application goal ≈ 95%

N = 9  → GC goal = 1/10 = 10%
         application goal ≈ 90%
```

Theo tài liệu **Java 17 HotSpot Parallel Collector Ergonomics**, giá trị mặc định là **`GCTimeRatio=99`**, tức mục tiêu dành khoảng 1% tổng thời gian cho GC.

**Phải phân biệt goal với measurement**: thiết lập `-XX:GCTimeRatio=99` không bảo đảm mọi workload chỉ dành đúng 1% thời gian cho GC. Nếu heap quá nhỏ, allocation quá nhanh hoặc live set lớn, collector có thể không đạt mục tiêu. JVM điều chỉnh theo thống kê/heuristics và giới hạn heap/throughput.

### 3.2. Thông lượng cao có thể đi kèm pause dài

Xét một batch job hoàn tất trong 10 phút, chỉ có 2 lần GC pause 800 ms. Tỷ lệ thời gian ứng dụng có thể rất cao, phù hợp mục tiêu **batch throughput**. Nhưng nếu cùng JVM phục vụ endpoint yêu cầu p99 latency dưới 100 ms, những pause 800 ms có thể vi phạm SLA nghiêm trọng.

Vì vậy, chọn Parallel GC hợp lý khi:

- Tổng số tác vụ hoàn thành mỗi giờ/phút quan trọng hơn latency đỉnh.
- Pause tương đối dài **được chấp nhận** theo yêu cầu dịch vụ.
- Máy có nhiều processors/cores và live set/heap đủ lớn để parallel GC work hữu ích.
- Workload mang tính batch, ETL, data processing hoặc CPU-intensive mà throughput là ưu tiên.

Không chỉ dựa vào tên “Parallel” rồi chọn cho mọi ứng dụng đa luồng; ứng dụng realtime/interactive có thể cần collector chuyên về low latency.

## 4. Tuning tự thích ứng: pause, throughput và footprint

HotSpot Parallel GC có **ergonomics/adaptive sizing policy**: thay vì bắt người dùng cố định mọi generation/space size, VM đo hành vi collections rồi điều chỉnh young/old sizing và những tham số liên quan nhằm tiến gần các mục tiêu.

**Thứ tự ưu tiên mục tiêu** trong tài liệu Parallel Collector Ergonomics:

1. **Maximum pause time goal** nếu được cấu hình.
2. **Throughput goal**.
3. **Minimum heap footprint**, miễn không phá hai mục tiêu ở trên.

Điều này quan trọng vì hai mục tiêu đầu có thể xung đột. Việc cố giảm từng pause có thể cần thu gom thường xuyên hơn và làm tổng GC time tăng; một young generation lớn có thể tăng throughput do ít collections nhưng từng pause dài hơn.

### 4.1. `MaxGCPauseMillis` là mục tiêu, không phải deadline

```bash
-XX:MaxGCPauseMillis=200
```

Con số 200 ms là **hint/goal**, không phải hợp đồng JVM phải cắt GC pause đúng 200 ms. Adaptive policy có thể giảm size của những vùng liên quan để giảm lượng công việc mỗi lần collection, nhưng vẫn có thể không đạt nếu live data rất lớn hoặc điều kiện khác bất lợi.

Theo Java 17 docs, **mặc định không có maximum pause-time goal** được đặt cho Parallel GC. Nếu chọn goal quá khắt khe, JVM có thể làm giảm throughput do cần GC nhiều hơn.

### 4.2. `UseAdaptiveSizePolicy`

`-XX:+UseAdaptiveSizePolicy` cho phép VM tự thích ứng generation sizes và tham số liên quan; trên những HotSpot releases phù hợp với Java 17, adaptive sizing được bật mặc định với Parallel GC.

```bash
-XX:+UseParallelGC -XX:+UseAdaptiveSizePolicy
```

Có thể tắt bằng `-XX:-UseAdaptiveSizePolicy` để thử nghiệm cấu hình thủ công, nhưng cần hiểu `-Xmn`, `NewRatio`, `SurvivorRatio`, `MaxTenuringThreshold` và những tương tác của chúng. **Không nên bắt đầu tuning bằng việc tắt adaptive policy** nếu chưa có đo đạc chứng minh nó cản trở mục tiêu workload.

### 4.3. `Xms` và `Xmx`: heap budget

```bash
-Xms512m -Xmx2g
```

- `-Xms` đặt initial heap size theo runtime.
- `-Xmx` là maximum heap size; collector không được tự vượt giới hạn này.
- Heap lớn có thể giảm tần suất GC khi workload cho phép, nhưng footprint tăng và có thể làm GC pauses khác đi.
- Nếu Java heap live set gần `Xmx`, cả adaptive sizing cũng khó tạo free space. Có thể xuất hiện `OutOfMemoryError` hoặc nhiều collections ít thu hồi được gì.

**Tăng `-Xmx` không sửa mọi sự cố memory**: native thread stack, direct memory, metaspace và bộ nhớ thư viện native vẫn là hạng mục khác.

### 4.4. `ParallelGCThreads`

`-XX:ParallelGCThreads=N` điều khiển số GC worker threads dùng cho những phần GC thực hiện song song theo hỗ trợ HotSpot. Ví dụ:

```bash
-XX:ParallelGCThreads=4
```

Không suy rằng chương trình chỉ có tổng cộng 4 threads, hay GC chạy đồng thời với 4 application threads. Đây là cấu hình **GC workers**, không phải `Executors.newFixedThreadPool(4)`.

Số workers phù hợp phụ thuộc CPU cores thực có thể sử dụng, container quotas, heap/live-set size và contention. Tự ép giá trị quá cao có thể làm overhead tăng, không đạt pause/throughput kỳ vọng.

### 4.5. Tóm tắt các tùy chọn thường thấy

| Tùy chọn HotSpot Java 17 | Mục đích | Bẫy cần tránh |
| --- | --- | --- |
| `-XX:+UseParallelGC` | Chọn Parallel / throughput collector | Không khiến GC thành concurrent low-latency |
| `-XX:ParallelGCThreads=N` | Đặt số worker threads xử lý GC song song | Không phải tổng số JVM threads |
| `-XX:GCTimeRatio=N` | Mục tiêu GC time = 1/(N+1) | Không bảo đảm tỷ lệ đo được chính xác |
| `-XX:MaxGCPauseMillis=N` | Hint cho maximum pause time | Không phải hard deadline |
| `-XX:+UseAdaptiveSizePolicy` | Adaptive generation sizing | Có thể bị hạn chế bởi heap bounds/flags khác |
| `-Xms / -Xmx` | Initial/max Java heap size | Không tính toàn bộ native memory |
| `-XX:MaxTenuringThreshold=N` | Giới hạn tuổi survivor trước promotion theo policy | Không hứa mỗi object ở survivor N lần |
| `-XX:-UseParallelOldGC` | Tắt parallel old compaction khi ParallelGC | Có thể làm major collections scale kém |
| `-XX:+UseGCOverheadLimit` | Kiểm tra GC overhead dẫn đến OOME khi quá ít tiến triển | Không phải memory-leak detector hoàn hảo |
| `-Xlog:gc*` | Unified logging cho GC | Không hứa log giống nhau giữa JDK/runtime |

Các flags được nói ở đây trong phạm vi **HotSpot JDK 17**, không phải từ khóa Java Language Specification bắt buộc mọi JVM vendor hỗ trợ.

## 5. Sự khác biệt giữa Parallel GC và Serial/G1/ZGC

| Collector (HotSpot Java 17) | Định hướng | Kiểu thu gom khái quát | Khi nên thử |
| --- | --- | --- | --- |
| **Serial GC** | Đơn giản, overhead nhỏ trên môi trường nhỏ | Một GC worker chủ yếu, STW | Heap nhỏ, CPU ít, chương trình đơn giản |
| **Parallel GC** | **Thông lượng**, tận dụng nhiều cores | STW phases với **nhiều GC workers**, generational | Batch/throughput-oriented, pauses dài có thể chấp nhận |
| **G1 GC** | Cân bằng throughput và pause predictability | Region-based, evacuation pauses + concurrent marking | Server heap lớn, mong pause thấp hơn và đều hơn |
| **ZGC** (JDK 17) | Latency rất thấp | Concurrent phases, very short STW pauses | Yêu cầu low latency, chấp nhận CPU/throughput trade-off |

**Đây là so sánh định hướng, không phải bảng xếp hạng tuyệt đối.** Trong một workload cụ thể, G1 có thể có throughput cao hơn Parallel GC hoặc ngược lại. Heap size, live-set shape, hardware, thread count và latency SLA mới quyết định lựa chọn phù hợp.

### 5.1. Default collector trong Java 17

Trên phần lớn cấu hình server phổ biến, **G1 là collector mặc định** trong HotSpot Java 17. Vì vậy nếu muốn thí nghiệm đúng Parallel GC, hãy **chỉ định `-XX:+UseParallelGC` rõ ràng** và xác nhận từ startup GC log.

Không dạy rằng “Parallel GC luôn mặc định trên server” chỉ vì một số tài liệu Java 8 nói vậy; default collector đã thay đổi qua các JDK releases và còn phụ thuộc VM configuration.

### 5.2. Parallel không phải Parallel Streams

`java.util.stream.Stream.parallel()`, `ForkJoinPool` và `Executors` liên quan **song song hóa công việc ứng dụng**. `-XX:+UseParallelGC` liên quan **song song hóa công việc thu gom rác**.

Hai tính năng không yêu cầu nhau. Một chương trình Java chỉ có main thread vẫn có thể chạy Parallel GC, còn ứng dụng có nhiều platform threads không bắt buộc phải dùng Parallel GC.

### 5.3. “G1 cũng có parallel GC worker threads” có mâu thuẫn không?

Không. “Parallel GC” là tên một **collector cụ thể** của HotSpot, còn các collectors khác cũng có thể dùng nhiều GC workers trong những pha của chúng. Sự khác nhau nằm ở **kiến trúc toàn bộ collection algorithm và các mục tiêu latency/throughput**, không phải chỉ ở câu hỏi “GC dùng 1 hay nhiều thread”.

## 6. Một chu kỳ Young GC minh họa

Giả sử có:

- Eden chứa 160 MB allocations, phần lớn object tạm.
- Survivor trước collection chứa 20 MB live candidates.
- Tỷ lệ sống trẻ trong đợt này thấp.
- Old có đủ headroom để nhận promotions nếu cần.

Các số dưới đây chỉ là **ví dụ khái niệm**:

```text
Trước Young GC:
  Eden:       160 MB
  Survivor:    20 MB
  Old:        400 MB

Stop-the-world Young GC, nhiều workers:
  1. Xác định live objects trong young
  2. Không copy objects unreachable
  3. Copy survivors còn trẻ tới survivor destination
  4. Promote objects cần vào old
  5. Reuse/reclaim young source spaces

Sau GC (một kịch bản giả định):
  Eden:         0 MB đang dùng bởi allocations cũ
  Survivor:    25 MB live
  Old:        410 MB used

Đã thu hồi một lượng đáng kể temporary data.
```

Không thể chỉ lấy `160 + 20 - 25 - 10` rồi kết luận tổng **process RSS** giảm đúng giá trị ấy. GC có thể giữ heap committed, có headers/alignment, survivor sizing, promotions và VM native memory khác. Ngoài ra số liệu trước/sau heap pools có thể biểu diễn capacity/used theo định nghĩa tool.

### 6.1. Old collections thường pause dài hơn young collections?

Thường có thể vì old chứa nhiều live objects và marking/compaction work rộng hơn, nhưng **không có một định luật “mọi Full GC đều lâu hơn mọi Young GC”**. Pause phụ thuộc lượng live data, heap fragmentation, hardware, GC worker efficiency và trigger. Đánh giá bằng log thực tế.

### 6.2. Thế hệ GC không phải heap và metaspace

Java heap chứa Eden/Survivor/Old theo những collectors thế hệ. **Metaspace** trong HotSpot là vùng quản lý class metadata nằm ngoài Java heap theo implementation. Một `OutOfMemoryError: Metaspace` không thể được sửa chỉ bằng chọn ParallelGCThreads nhiều hơn.

## 7. Ví dụ Java 17 có thể biên dịch/chạy để thử Parallel GC

Tạo file **`ParallelGcDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ParallelGcDemo {
    // Giữ một phần dữ liệu để mô phỏng objects sống lâu.
    private static volatile List<byte[]> keepAlive;

    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();
        long checksum = 0L;

        for (int i = 0; i < 100_000; i++) {
            byte[] block = new byte[2048];
            block[0] = (byte) (i & 127);
            checksum += block[0] & 0xff;

            if (i % 5000 == 0) {
                retained.add(block);
            }
        }

        keepAlive = retained;

        System.out.println("processed=100000");
        System.out.println("retained=" + retained.size());
        System.out.println("checksumPositive=" + (checksum > 0));
        System.out.println("done");
    }
}
```

Biên dịch với JDK 17:

```bash
javac --release 17 ParallelGcDemo.java
```

Chạy với HotSpot Parallel GC, heap tương đối nhỏ để có cơ hội thấy Young GC:

```bash
java -XX:+UseParallelGC -Xms64m -Xmx64m ParallelGcDemo
```

**Stdout của chính chương trình Java (không bật GC logging):**

```text
processed=100000
retained=20
checksumPositive=true
done
```

**Giải thích output:**

- `processed=100000` do loop thực hiện đúng 100.000 iterations.
- Điều kiện `i % 5000 == 0` đúng tại `0, 5000, ..., 95000` → **20** arrays được thêm vào `retained`.
- `checksumPositive=true` vì có nhiều giá trị `block[0] & 0xff` dương.
- `keepAlive` giữ list và các retained arrays reachable cho đến lúc chương trình kết thúc.
- Các arrays khác có thể trở thành garbage sớm; **GC count, pause durations, tuổi và promotion của từng array không có stdout cố định**. Java API không công bố generation của một object riêng.

**Không khẳng định** có đúng 3 Young GC chỉ vì source tạo 100.000 mảng. Tùy JIT, TLAB, heap sizing và GC ergonomics, lượng allocations/timing quan sát được có thể khác.

### 7.1. Một ví dụ không có `System.gc()` cố ý

Chương trình không gọi `System.gc()` vì đó là **lời đề nghị JVM thực hiện GC**, không phải công cụ lập lịch GC deterministic. Mục tiêu là tạo một workload với **kết quả nghiệp vụ cố định**, rồi dùng **GC logging độc lập** quan sát actual runtime behavior.

Trong ứng dụng thực, gọi `System.gc()` liên tục có thể làm sai bức tranh throughput/pause và khiến benchmark không đại diện. Nếu cần đánh giá collector, hãy để workload đủ dài hoặc dùng bộ sinh tải có kiểm soát.

## 8. Quan sát collector và các pha GC bằng Unified Logging

### 8.1. Xác nhận Parallel GC được chọn

```bash
java -XX:+UseParallelGC -Xms64m -Xmx64m -Xlog:gc=info ParallelGcDemo
```

Trên HotSpot Java 17, startup log thường có dấu hiệu dạng `Using Parallel` hoặc các thông tin GC liên quan. Từ ngữ chính xác, timestamps, GC ids và số events có thể khác giữa JVM builds; **không đưa một log giả làm stdout chính xác**.

Khi bật `-Xlog`, lệnh in **GC logs bổ sung** cùng những dòng `processed=...` của chương trình. Nếu cần tách logs khỏi kết quả nghiệp vụ, có thể cấu hình ghi log ra file.

### 8.2. Xem heap, young/old và age table

```bash
java -XX:+UseParallelGC -Xms64m -Xmx64m \
  -Xlog:gc*,gc+heap=debug,gc+age=trace \
  ParallelGcDemo
```

Trong log phù hợp có thể quan sát:

- GC events và GC causes.
- Các thông tin young/old heap trước và sau collection.
- Thống kê capacity/used theo spaces của Parallel collector.
- Phân tích age table/survivor và tenuring threshold khi log level/tags hỗ trợ.
- Wall-clock pause durations.

Đây là cú pháp shell kiểu POSIX; trên Windows PowerShell nên viết trên một dòng hoặc dùng line-continuation đúng cú pháp PowerShell.

### 8.3. Ghi log ra file

```bash
java -XX:+UseParallelGC -Xms64m -Xmx64m \
  -Xlog:gc*,gc+heap=debug,gc+age=trace:file=parallel-gc.log:time,uptime,level,tags \
  ParallelGcDemo
```

File `parallel-gc.log` chứa dữ liệu runtime; volume có thể cao nếu chọn trace level. Trong production, cân nhắc dung lượng disk, log rotation, bảo mật và overhead.

### 8.4. Mẫu log để luyện đọc — không phải output thật

```text
[info][gc] Using Parallel
[info][gc] GC(0) Pause Young (Allocation Failure) ...ms
[info][gc] GC(1) Pause Full (Ergonomics) ...ms
```

Đây là **sơ đồ minh họa loại log**, các nguyên nhân/loại events có thể khác. Không suy `Allocation Failure` nghĩa Java `new` đã ném OutOfMemoryError: collector có thể phục hồi khả năng allocation sau Young GC, và ứng dụng vẫn chạy thành công.

GC log là bằng chứng thực tế; **một dòng ví dụ không thể làm bằng chứng cho phiên chạy của bạn**.

## 9. Tính throughput và pause từ log: ví dụ tư duy

Giả sử ở cửa sổ đo 100 giây:

- Application thực hiện công việc trong 97 giây.
- Tổng STW GC pauses là 3 giây.

```text
application_time = 97 s
gc_time          =  3 s

throughput = 97 / (97 + 3) = 97%
GC fraction = 3 / 100 = 3%
```

Nếu `GCTimeRatio=99` (mục tiêu GC fraction 1%), kết quả đo 3% nghĩa collector không đạt mục tiêu trong cửa sổ quan sát đó. Nó **không tự xác định nguyên nhân**: heap quá nhỏ, live set lớn, quá nhiều allocations, CPU thiếu, hoặc cách chọn cửa sổ đo đều cần phân tích thêm.

### 9.1. Throughput chưa phản ánh p99 latency

Giả sử cùng 3 giây GC được chia thành:

- 300 pauses × 10 ms, hoặc
- 3 pauses × 1000 ms.

Tổng pause time đều là 3 giây, nên throughput theo công thức đơn giản như nhau. Nhưng **tail latency** khác rất xa; service có SLA 100 ms có thể thất bại với các pauses 1 giây.

Điều đó giải thích vì sao Parallel GC có thể phù hợp batch processing nhưng kém phù hợp interactive service cần pauses rất thấp. Cần so sánh **throughput và pause percentiles** cùng nhau.

### 9.2. Pause time không phải application CPU time

Một GC pause dài 100 ms với 8 GC worker threads có thể tiêu thụ hơn 100 ms tổng CPU time trên tất cả workers; throughput ratio nêu trong tài liệu là **khái niệm wall-time behavior**, không đơn giản là lấy tổng CPU% mỗi thread chia hệ số nào đó.

## 10. `GC overhead limit exceeded` và những kiểu thất bại

HotSpot Java 17 có policy `-XX:+UseGCOverheadLimit` (mặc định bật trong những cấu hình phù hợp). Khi phần lớn thời gian dùng vào GC nhưng thu hồi được quá ít heap theo ngưỡng của policy, JVM có thể ném:

```text
java.lang.OutOfMemoryError: GC overhead limit exceeded
```

Tài liệu option của Java 17 mô tả tình huống parallel GC **dành trên khoảng 98% thời gian cho GC và chỉ thu hồi dưới khoảng 2% heap**. Đây là một **guard chống ứng dụng gần như không tiến triển**, không phải một loại GC mới.

Nguyên nhân cần điều tra:

- **Strong live set** gần sát `Xmx`.
- Cache/list/queue giữ references lâu hơn dự kiến.
- Allocation rate lớn kèm nhiều đối tượng sống.
- Cấu hình heap quá nhỏ so với workload.
- Object retention leak, static maps, listeners, ThreadLocals hoặc native bridges giữ Java objects.

**Không chữa trị bằng cách chỉ đặt `-XX:-UseGCOverheadLimit`** và coi vấn đề biến mất; điều đó có thể làm ứng dụng tiếp tục tốn CPU GC nhưng không có tiến triển, rồi OOME theo cơ chế khác.

### 10.1. Phân biệt OOME, Young GC và promotion failure

- **Young GC** là hoạt động bình thường; không phải exception.
- **Promotion pressure** làm old occupancy tăng, có thể dẫn tới GC nặng hơn nếu thiếu headroom.
- **OutOfMemoryError: Java heap space** xuất hiện khi JVM không cấp phát được heap object trong điều kiện tương ứng.
- **GC overhead limit exceeded** là một policy-based OOME khi phần lớn thời gian bị GC “ăn” mà memory reclaimed quá ít.
- **OutOfMemoryError: unable to create native thread** liên quan tài nguyên thread/native memory, không thể suy trực tiếp từ Eden.
- **OutOfMemoryError: Metaspace** không phải thông báo old Java heap đã đầy.

Các messages cụ thể là chi tiết implementation, phải dựa trên log/stack trace thực tế. Đừng gán mọi OOME cho Parallel GC “có bug”.

## 11. Tại sao GC workers nhiều hơn đôi khi chậm hơn?

Parallel GC làm việc trên shared heap và phải phối hợp nhiều threads trong một STW pause. Các yếu tố có thể giảm hiệu quả:

- **Memory bandwidth:** nhiều workers cùng quét/copy live objects có thể saturate memory subsystem.
- **Synchronization/task distribution:** tạo/chia công việc, cân bằng load và rendezvous có overhead.
- **CPU contention:** máy/container chỉ cấp vài cores thực, nhiều worker threads tranh nhau CPU.
- **Small heap/live set:** lượng GC work ít, chi phí quản lý workers lớn hơn lợi ích.
- **NUMA effects:** truy cập bộ nhớ ở node xa có latency cao hơn; placement ảnh hưởng.
- **Cgroup/resource limits:** JVM nhìn thấy quota processors có thể thay đổi quyết định workers, sizing và throughput.

Không có “số GC workers lý tưởng = số cores × 2” cho mọi máy. Cách đúng là đo workload dưới CPU/memory quotas thật, dùng `ParallelGCThreads` làm thí nghiệm riêng, so GC wall time, CPU, throughput và p99 latency.

## 12. Những cấu hình thực nghiệm nên thử

### 12.1. Baseline: JVM tự chọn GC

```bash
java -Xms512m -Xmx512m MyApp
```

Ghi lại collector thực sự được chọn, JVM vendor/version, log/event metrics. Trên HotSpot Java 17 server thường là G1; chỉ coi đó là baseline thực nghiệm.

### 12.2. So sánh Parallel GC

```bash
java -XX:+UseParallelGC -Xms512m -Xmx512m \
  -Xlog:gc*:file=parallel.log:time,uptime,level,tags \
  MyApp
```

Giữ nguyên workload/heap sizing, đo requests/s, total runtime, p99 pause, total GC time, process CPU và memory. Với batch job, đo **tổng thời gian hoàn tất** thường có ý nghĩa hơn một mức GC count.

### 12.3. Thử throughput goal, rồi pause goal

```bash
java -XX:+UseParallelGC -Xms512m -Xmx512m \
  -XX:GCTimeRatio=19 -Xlog:gc*=info MyApp

java -XX:+UseParallelGC -Xms512m -Xmx512m \
  -XX:MaxGCPauseMillis=200 -Xlog:gc*=info MyApp
```

Đây là **hai cấu hình thí nghiệm khác nhau**; không tự giải thích sự khác biệt là do một flag duy nhất nếu input/CPU load khác nhau. `GCTimeRatio=19` cho phép goal tới khoảng 5% thời gian GC; `MaxGCPauseMillis=200` cố hướng pause về 200 ms. Chúng là *mục tiêu*, không phải bảo đảm.

### 12.4. Thử số workers, có số liệu thực

```bash
java -XX:+UseParallelGC -XX:ParallelGCThreads=4 \
  -Xms512m -Xmx512m -Xlog:gc*=info MyApp
```

So với baseline trước đó cùng hardware, cùng heap, cùng workload. Nếu pause giảm nhưng throughput ứng dụng kém hơn do CPU contention, bạn cần quyết định theo SLA kinh doanh.

Các lệnh dùng `MyApp` chỉ là **template**, không phải Java class được bài này cung cấp. Để tự chạy bài lab hoàn chỉnh, thay bằng `ParallelGcDemo` ở mục 7.

## 13. Phương pháp so sánh công bằng với G1

Khi quyết định chọn Parallel GC thay cho G1:

1. **Định nghĩa SLA:** batch jobs/s, time-to-completion, p95/p99 service latency, tối đa pause chấp nhận được.
2. **Cố định môi trường:** JDK build/vendor, CPU quota, container limits, `-Xms/-Xmx`, dataset, traffic pattern.
3. **Warm up:** để JIT/class loading ổn định tương đối trước khi lấy mẫu dài hạn.
4. **Theo dõi peak và steady state:** GC behavior lúc bootstrap và sau warmup có thể khác nhau.
5. **Dùng đồng nhất công cụ:** GC logs với cùng mức verbose, JFR/metrics, throughput counters và heap usage.
6. **Xem cả trung bình và tail latency:** throughput cao không bù được p99 vi phạm SLA nếu ứng dụng có yêu cầu nghiêm.
7. **Thử một nhóm flags mỗi lần:** tránh thay collector, heap size, CPU threads và timeout trong cùng thí nghiệm rồi kết luận sai nguyên nhân.
8. **Chạy nhiều lần:** kết quả phụ thuộc OS scheduling, CPU cache, thermal behavior, JVM warmup và GC timing.
9. **Theo dõi OOME/GC overhead limit:** collector nhanh hơn trong 5 phút đầu chưa chắc ổn khi cache lớn dần nhiều giờ.
10. **Chọn trên dữ liệu thực:** Oracle khuyến nghị JVM tự chọn GC nếu không có ràng buộc nghiêm; đổi collector khi có bằng chứng vấn đề.

### 13.1. Những chỉ số nên đọc cùng nhau

| Metric | Trả lời câu hỏi | Tránh kết luận |
| --- | --- | --- |
| GC pause duration | Mỗi lần application bị dừng bao lâu? | Không đồng nghĩa tổng application throughput |
| Total GC wall time | JVM dừng để GC bao nhiêu trong cửa sổ đo? | Không tự phản ánh CPU workers |
| Allocation rate | Ứng dụng sinh bao nhiêu bytes mới mỗi giây? | Không đồng nghĩa live heap |
| Young survival/promotion | Bao nhiêu bytes sống qua young collection và vào old? | Không tự chứng minh memory leak |
| Old occupancy trend | Live/used old tăng có chạm plateau không? | Tăng tạm thời không nhất thiết là leak |
| Heap footprint/RSS | JVM dùng bao nhiêu memory? | RSS gồm cả native memory |
| Requests/sec/jobs/sec | Ứng dụng làm được bao nhiêu việc? | Không cho biết p99 |
| p95/p99 latency | Những request chậm nhất có vượt SLA không? | Không nhất thiết tỷ lệ thuận GC time |

**Đọc GC log theo event type/cause/time window**, không ghép các events không liên quan rồi đưa ra số liệu “trước/sau” giả.

## 14. Những hiểu nhầm phổ biến về Parallel GC

1. **“Parallel GC là concurrent GC.”** Sai. Nó chủ yếu STW, nhưng dùng nhiều GC workers song song.
2. **“Có 8 GC workers thì GC nhanh gấp 8.”** Sai. Bandwidth, scheduling, GC live-set và synchronization giới hạn scaling.
3. **“Parallel GC không có Old collection.”** Sai. Parallel Old hỗ trợ compaction old song song theo mặc định khi `UseParallelGC`.
4. **“Young GC và Full GC là một.”** Sai. Young chỉ xử lý young, còn Full có phạm vi/cost rộng hơn.
5. **“Tên Parallel nghĩa ứng dụng chạy song song với GC.”** Sai. Song song ở đây là **giữa GC workers**.
6. **“ParallelGCThreads là số application threads.”** Sai. Nó là số GC workers.
7. **“Parallel GC đảm bảo không có pause trên 200 ms khi đặt `MaxGCPauseMillis=200`.”** Sai, chỉ là goal.
8. **“`GCTimeRatio=19` nghĩa GC phải dùng 19% thời gian.”** Sai. Nó tương ứng goal **1/20 = 5%**.
9. **“`GCTimeRatio=99` bảo đảm GC chỉ chiếm đúng 1%.”** Sai. Đây là mục tiêu mặc định, không phải measurement.
10. **“Java 17 HotSpot luôn mặc định Parallel GC.”** Sai trên các cấu hình server phổ biến; thường mặc định G1.
11. **“Old generation chứa đối tượng không bao giờ chết.”** Sai. Old vẫn được collected.
12. **“Mọi object mới luôn nằm ở Eden rồi đi qua hai Survivor spaces.”** Không phải bất biến; JIT và policies có ngoại lệ.
13. **“Tăng `-Xmx` sửa mọi OOME.”** Sai. Native threads/metaspace/direct memory có ràng buộc riêng.
14. **“GC overhead limit exceeded là một loại leak được JVM kết luận chắc chắn.”** Sai. Nó là policy cảnh báo thiếu tiến triển trong điều kiện GC/heap pressure.
15. **“Chỉ cần giảm số GC events là throughput sẽ tăng.”** Không phải lúc nào cũng đúng; pauses có thể dài lên.
16. **“Bật `System.gc()` nhiều giúp benchmark collector chính xác.”** Sai. Nó gây can thiệp và không đảm bảo lịch GC.
17. **“Hai JVM cùng source bắt buộc có GC logs giống từng dòng.”** Sai. Scheduling, heap sizing, JIT và hardware ảnh hưởng.
18. **“Parallel GC luôn nhanh hơn G1.”** Sai. Phụ thuộc workload và tiêu chí đo.
19. **“G1 không có parallel workers vì tên là G1.”** Sai. G1 cũng song song hóa một số pha, còn concurrency/architecture khác.
20. **“Heap và old generation bao gồm toàn bộ Metaspace.”** Sai. Metaspace được quản lý ngoài Java heap trong HotSpot.
21. **“Một Young GC là một `OutOfMemoryError`.”** Sai. Allocation-related pause thường khôi phục memory để ứng dụng tiếp tục.
22. **“Nếu survivor đầy thì chương trình buộc crash.”** Sai. Collector có thể promote, làm các thao tác bổ sung hoặc báo lỗi khi thiếu memory thực.
23. **“Adaptive sizing giữ kích thước young/old cố định.”** Sai. Nó có thể điều chỉnh theo pause/throughput/footprint goals.
24. **“Trong Java 17, `UseParallelOldGC` mặc định tắt khi chọn Parallel.”** Sai theo Oracle docs: parallel compaction bật theo `UseParallelGC`.
25. **“Bật GC log làm thay đổi Java API semantics của `String` hay `List`.”** Không. Logging có overhead nhưng không được làm sai contract của ứng dụng.

## 15. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** Tại sao Parallel GC vẫn được gọi là stop-the-world khi nó sử dụng nhiều threads?

**Đáp án:** Vì mutator/application threads bị pause trong collection; nhiều threads đang chạy đồng thời là **các GC worker threads**, không phải ứng dụng chạy song song với GC.

**Câu 2.** `-XX:+UseParallelGC` có hỗ trợ thu gom Old song song không?

**Đáp án:** Có. Trên HotSpot Java 17, parallel old compaction thường được bật mặc định cùng `UseParallelGC`, có thể tắt bằng `-XX:-UseParallelOldGC`.

**Câu 3.** Với `GCTimeRatio=19`, mục tiêu thời gian GC chiếm tỷ lệ nào?

**Đáp án:** `1/(1+19)=1/20=5%`.

**Câu 4.** Với `GCTimeRatio=99`, throughput goal ứng dụng là bao nhiêu?

**Đáp án:** Khoảng `99/100=99%` thời gian application, tức GC fraction goal 1%, **không được đảm bảo thực tế**.

**Câu 5.** `MaxGCPauseMillis=100` có cấm JVM pause 150 ms không?

**Đáp án:** Không. Đây là mục tiêu/hint cho adaptive sizing, không phải hard deadline.

**Câu 6.** Object ở Eden còn reachable khi Young GC, sẽ thế nào?

**Đáp án:** Collector giữ object bằng cách copy/evacuate sang survivor hoặc old theo chính sách, không thu hồi chỉ vì object đang ở Eden.

**Câu 7.** Một old object không còn reachable có thể được Parallel GC thu hồi không?

**Đáp án:** Có. Old collections xác định live objects và reclaim/compact theo cơ chế Parallel Old.

**Câu 8.** Tại sao nhiều GC workers đôi khi không tăng throughput?

**Đáp án:** Vì CPU/memory bandwidth có giới hạn, synchronization và task scheduling overhead tăng, hoặc workload quá nhỏ để song song hóa hữu ích.

**Câu 9.** Chạy `ParallelGcDemo` với `-Xmx64m` có chắc thấy đúng 2 Young GCs không?

**Đáp án:** Không. GC count là runtime-dependent; chỉ stdout nghiệp vụ `processed`/`retained`/`checksumPositive` là cố định.

**Câu 10.** `retained` trong demo có bao nhiêu byte arrays?

**Đáp án:** **20**, vì 100.000 iterations và giữ mỗi phần tử thứ 5.000, tính từ 0.

**Câu 11.** GC time là 0.5 s, app time là 9.5 s. Throughput thời gian ứng dụng?

**Đáp án:** `9.5 / 10 = 95%`.

**Câu 12.** Vì sao một server p99 latency 50 ms thường không chọn Parallel GC chỉ vì throughput tốt?

**Đáp án:** Parallel GC có các pauses STW có thể dài hơn ngân sách p99; cần collector/thiết kế phù hợp latency SLA và phải đo thực tế.

**Câu 13.** `GC overhead limit exceeded` có nhất thiết chứng minh program giữ reference leak?

**Đáp án:** Không. Heap quá nhỏ hoặc live set/allocations cao cũng gây quá ít tiến triển; cần xem heap, GC log và object graph.

**Câu 14.** Nếu chương trình mặc định đang chạy G1, làm sao thử đúng Parallel?

**Đáp án:** Thêm `-XX:+UseParallelGC`, xác nhận startup log từ `-Xlog:gc=info`, giữ các tham số khác nhất quán.

## 16. Tổng kết

```text
                       Parallel GC
                     (Throughput GC)
                             │
             ┌───────────────┴────────────────┐
             │                                │
        Young GC                         Old/Full GC
    Parallel Scavenge                   Parallel Old
             │                                │
    Eden → Survivor/Old               mark/compact old
    live objects được copy            có thể tốn pause lớn
             │                                │
             └───────────────┬────────────────┘
                             │
                        STW pauses
                   GC workers chạy song song
                  application threads tạm dừng
                             │
                     Ergonomics tự điều chỉnh
                    ┌────────┼──────────┐
                    │        │          │
                pause goal  throughput  footprint
                    │        │          │
                    └────────┴──────────┘

Nếu bài toán thiên về batch throughput và chấp nhận pauses:
  Parallel GC là một lựa chọn đáng benchmark.

Nếu bài toán có latency SLA khắt khe:
  So với G1/ZGC trên dữ liệu thực, đừng chỉ nhìn throughput.
```

**Ghi nhớ:** Parallel GC là **generational, stop-the-world, multithreaded garbage collector** của HotSpot, giúp xử lý Young GC và old compaction bằng nhiều worker threads nhằm nâng **throughput**. Nó **không** có nghĩa “ứng dụng vẫn chạy khi GC”. Adaptive sizing ưu tiên **pause goal → throughput goal → footprint**, với `GCTimeRatio` biểu diễn tỷ lệ thời gian GC và `MaxGCPauseMillis` chỉ là mục tiêu mềm. Chọn Parallel GC khi throughput quan trọng hơn tail latency, sau đó dùng GC logs và workload benchmark để xác minh hiệu quả thực thay vì suy từ tên collector hoặc số core.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): mô tả Serial, Parallel, G1, ZGC, Parallel Old và use case.
- [Oracle Java SE 17 — Parallel Collector Ergonomics](https://docs.oracle.com/en/java/javase/17/gctuning/parallel-collector1.html): pause/throughput/footprint goals và policy ưu tiên.
- [Oracle Java SE 17 — HotSpot Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/index.html): generational architecture và tuning.
- [Oracle JDK 17 — `java` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `UseParallelGC`, `ParallelGCThreads`, `GCTimeRatio`, `MaxGCPauseMillis` và `UseAdaptiveSizePolicy`.
- [Oracle JDK 17 — Unified JVM Logging `-Xlog`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): logging tags/levels/file syntax.
- [Oracle JDK 17 — `jstat` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): quan sát GC counters.
- [Oracle Java SE 17 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): hướng đối chiếu concurrent marking và pause goals.
