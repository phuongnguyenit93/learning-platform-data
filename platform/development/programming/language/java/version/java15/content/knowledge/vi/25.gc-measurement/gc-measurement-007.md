# Đo lường GC: so sánh G1, ZGC và Shenandoah khi môi trường hỗ trợ

> **Bối cảnh Java 15 → JDK hiện hành:** G1, ZGC và Shenandoah đều là garbage collectors được dùng để quản lý Java heap, nhưng **không có collector tốt nhất cho mọi workload**. G1 hướng tới cân bằng throughput và pause, còn ZGC và Shenandoah tập trung vào **độ trễ tạm dừng thấp nhờ thu gom đồng thời** với application threads. Muốn so sánh có giá trị, cần chạy trên **cùng môi trường JDK/OS/CPU/heap/workload**, xác minh collector thực sự được chọn, đo **độ trễ ứng dụng, GC pauses, throughput, memory footprint, CPU và các loại stalls**, rồi đánh giá theo SLO. **Shenandoah phải được probe vì không phải mọi JDK distribution/build đều có collector này.**

## 1. Mục tiêu học tập và kết luận thực hành

Sau bài học, bạn có thể:

1. Phân biệt **GC collector**, **GC mode**, **JVM build**, **Java heap** và **tổng memory tiến trình**.
2. Bật G1, ZGC và Shenandoah bằng những cờ **còn áp dụng trong JDK hiện hành**.
3. Xác minh runtime hỗ trợ Shenandoah **trước khi chạy test**; tránh báo kết quả “Shenandoah” khi JVM thực tế dùng GC khác.
4. Hiểu rằng **GC pause p99 khác application request p99** và hiểu vì sao đo một chỉ số không đủ.
5. Thiết kế ma trận thí nghiệm **A/B/C công bằng**, có warm-up, steady state, repeated runs, GC logs, JFR và các số đo OS/container.
6. Phân tích trade-off: tail latency, throughput, CPU, allocation stalls, RSS/native memory, OOME và operational complexity.
7. Viết chương trình Java 17+ tái lập allocation workload, nhưng không tự nhận đó là benchmark production hoàn chỉnh.
8. Đưa ra quyết định chọn collector theo **bằng chứng đo được**, không theo quảng cáo hay tên công nghệ.

**Lệnh khởi đầu** cho ba trường hợp trên HotSpot có hỗ trợ:

~~~bash
# G1: có thể yêu cầu tường minh, không phụ thuộc default của VM.
java -XX:+UseG1GC -Xms128m -Xmx512m -jar app.jar

# ZGC: HotSpot JDK 24+ chỉ còn Generational ZGC.
java -XX:+UseZGC -Xms128m -Xmx512m -jar app.jar

# Shenandoah: CHỈ khi JVM build/platform thực sự hỗ trợ.
java -XX:+UseShenandoahGC -Xms128m -Xmx512m -jar app.jar
~~~

`app.jar` là tên ví dụ; thay bằng ứng dụng có thật. Ba lệnh trên **chỉ chọn collector**, không tạo ra kết quả benchmark. Những con số heap cũng là ví dụ, **không phải khuyến nghị cố định**.

**Thông tin phiên bản cần nhớ:** trong JDK 27 (phát hành tháng 9/2026), **G1 là collector mặc định trong mọi môi trường** theo JEP 523. Khi muốn phép thử lặp lại đáng tin, hãy chọn G1 **tường minh** bằng `-XX:+UseG1GC` thay vì dựa vào ergonomics mặc định.

## 2. Hiểu đúng ba collectors trước khi đo

| Khía cạnh | G1 | ZGC | Shenandoah |
| --- | --- | --- | --- |
| Hướng thiết kế | Cân bằng throughput và latency, điều tiết pause mục tiêu | Low-latency concurrent GC | Low-pause concurrent compacting GC |
| Tạo generations | Có young/old | **Generational-only từ JDK 24** | **SATB single-generation mặc định trên các build JDK25–27 đã xác minh; generational opt-in** |
| Cách xử lý phần lớn compaction/reclaim | Evacuation trong các STW pauses, có concurrent marking | Nhiều công việc thu gom/chuyển đối tượng được thực hiện concurrent | Nhiều công việc mark/evacuate/update được thực hiện concurrent |
| Stop-the-world hoàn toàn biến mất? | Không | Không | Không |
| Cờ chọn collector | `-XX:+UseG1GC` | `-XX:+UseZGC` | `-XX:+UseShenandoahGC` |
| Availability | Phổ biến trong HotSpot, mặc định JDK27 | Phụ thuộc build/platform | **Phụ thuộc mạnh vào vendor/build/OS/CPU** |
| Thế mạnh cần kiểm chứng | Throughput, footprint và pause goal cân bằng | GC pause ngắn, đặc biệt với heap lớn/latency nghiêm ngặt | GC pause ngắn, có các mode với trade-off khác nhau |
| Rủi ro quan trọng | STW evacuation và full GC có thể gây tail latency | CPU concurrent GC, allocation stalls, footprint/headroom | CPU/barrier overhead, degenerated/full GC fallback, support |
| Collector “luôn nhanh hơn” hai loại kia? | Không | Không | Không |

**G1:** sử dụng regions, young/old generations và theo dõi pause-time goal, cố gắng giữ pauses trong giới hạn mục tiêu với xác suất cao. **Không phải real-time guarantee.** Tùy workload, G1 có thể cho throughput rất tốt, nhưng vẫn có GC pauses do sao chép live objects, mixed collections hoặc full GC.

**ZGC:** phần lớn GC diễn ra concurrent, tối ưu pause rất ngắn. Điều này **không làm chi phí GC bằng 0**: concurrent phases dùng CPU, barriers và memory. Khi thiếu allocation headroom, ứng dụng có thể bị **allocation stall**, dù các GC pauses đo được có vẻ nhỏ.

**Shenandoah:** cũng di chuyển objects đồng thời và nhằm giảm pauses. Trong tình trạng memory/CPU pressure, có thể xuất hiện **degenerated hoặc full GC**; cần đo chứ không mặc định tất cả pauses luôn nhỏ.

**Cảnh báo:** không lấy số GC cycles hoặc tổng collection time của một collector so trực tiếp với collector khác rồi kết luận “ít cycles hơn = nhanh hơn”. Cách định nghĩa cycle, young/old, concurrent phase và các MXBeans có thể khác nhau.

## 3. Ma trận tương thích: chọn đúng chế độ theo JDK

### 3.1. G1: lựa chọn dễ tái lập

`-XX:+UseG1GC` là cờ HotSpot còn dùng trên JDK hiện đại. Trong JDK 27, G1 đã là default trong mọi môi trường, nhưng chạy thử so sánh nên **chỉ định tường minh** để tránh bị ảnh hưởng bởi cấu hình ẩn từ script/container.

Một lựa chọn G1 thường gặp là `-XX:MaxGCPauseMillis=200`, nhưng giá trị này là **mục tiêu heuristics, không phải giới hạn tuyệt đối**. Không ép một pause target bất khả thi khi so với ZGC rồi coi phép thử công bằng.

### 3.2. ZGC: chỉ còn generational trên JDK 24+

- Java 15 có ZGC production theo **JEP 377**.
- JDK 21 giới thiệu Generational ZGC theo **JEP 439**.
- JDK 23 chuyển Generational ZGC thành default khi chọn ZGC theo **JEP 474**.
- JDK 24 **loại bỏ non-generational ZGC** theo **JEP 490**.

**Trên JDK 24+**, bật ZGC bằng:

~~~bash
java -XX:+UseZGC -Xms128m -Xmx512m -jar app.jar
~~~

Không dùng `-XX:+ZGenerational` hay `-XX:-ZGenerational` trong cấu hình mới: cờ chọn mode đó đã bị loại bỏ. **Generational ZGC không đồng nghĩa với G1 mặc định bị thay thế**: vẫn cần `-XX:+UseZGC` nếu muốn collector ZGC.

### 3.3. Shenandoah: kiểm tra collector trước, rồi mới kiểm tra mode

- Java 15 có production Shenandoah qua **JEP 379**.
- JDK 25 có **Generational Shenandoah product** qua **JEP 521**.
- Trong OpenJDK/HotSpot builds JDK 25–27 có Shenandoah, `ShenandoahGCMode=satb` vẫn là default theo tài liệu Java command; `generational` có thể chọn **riêng**, nếu build hỗ trợ.
- **Không phải mọi Java/JDK 25 hoặc 27 đều hỗ trợ Shenandoah**. JVM có thể bị build không kèm collector.

Thử:

~~~bash
java -XX:+UseShenandoahGC -version
~~~

Nếu exit code khác 0 hoặc JVM báo unsupported, **không đưa Shenandoah vào cột benchmark như thể đã chạy được**. Hãy ghi là **không khả dụng** và giải thích vendor/build/platform. Không im lặng bỏ cờ để fallback sang G1 rồi gắn nhãn kết quả “Shenandoah”.

Nếu muốn thử **Generational Shenandoah** trên build JDK25+ hỗ trợ:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -version
~~~

Thử mode bằng một phép đo **riêng**; không trộn các kết quả SATB với generational rồi gọi chung “Shenandoah”. Trong tài liệu JDK 25–27, generational chỉ hỗ trợ heuristic `adaptive`; đừng mang cờ heuristic không phù hợp từ SATB vào mode này.

### 3.4. Java source version không quyết định collector

Một chương trình biên dịch bằng:

~~~bash
javac --release 15 GcComparisonDemo.java
~~~

vẫn có thể chạy trên JDK27 với collector được chọn lúc runtime. `--release 15` tác động tới source/API/class file tương thích Java15, **không ép thuật toán GC của Java15**. Phép so sánh phải ghi **runtime version + vendor + flags**, không chỉ nhãn “Java 15”.

## 4. “Công bằng” nghĩa là giữ những gì cố định?

Khi so sánh G1/ZGC/Shenandoah, biến thí nghiệm chính cần đổi là **GC collector**; các yếu tố khác phải được kiểm soát hoặc ghi lại và báo là confounders.

| Yếu tố | Giữ giống nhau như thế nào? | Nếu không, điều gì bị nhiễu? |
| --- | --- | --- |
| JDK vendor/build/patch | Cùng binary runtime hỗ trợ cả ba, nếu khả thi | JIT, GC implementation, object layout và runtime behavior khác |
| OS, kernel, CPU architecture | Cùng host class, CPU features, clock/cgroup policy | Khác memory throughput, scheduling, NUMA |
| CPU limit/throttling | Cùng core/quota/share và tình trạng tải | Concurrent GC bị chi phối trực tiếp |
| Memory limit | Cùng container/cgroup budget và native headroom | OOM hoặc memory pressure không công bằng |
| `-Xmx` và `-Xms` | Cùng giới hạn trước khi thử collector-specific tuning | Live set/headroom thay đổi GC workload |
| Application build | Cùng commit, dependencies, JIT/profile assumptions | Khác allocations và business logic |
| Data và traffic | Cùng phân bố payload, concurrency, request types | Khác sống/chết object và heap pressure |
| Warm-up | Cùng tiêu chí đạt steady state | JIT/class loading và caches làm méo kết quả |
| Duration | Cùng thời gian đo sau warm-up | So chu kỳ khác nhau gây bias |
| Logging/profiling | Cùng mức GC log và JFR profile khi so trực tiếp | Overhead quan sát khác nhau |
| Network/downstream | Cùng latency, DB state, backpressure | App p99 cao do I/O chứ không phải GC |
| Thứ tự chạy | Lặp lại và đảo/thay đổi thứ tự | Host nhiệt, caching và background load |

**Một caveat quan trọng:** nếu vendor A không chứa Shenandoah nhưng vendor B có, muốn thử Shenandoah phải đổi JDK build. Khi đó không thể quy toàn bộ chênh lệch cho collector. Có thể:

1. Chọn **một build hỗ trợ cả ba GC** và chạy cả G1/ZGC/Shenandoah trong build đó.
2. Nếu bất khả thi, báo rõ “so sánh JVM configuration A/B” thay vì “GC-only experiment”.
3. Không đưa số đo từ vendor khác vào một bảng rồi giấu việc khác JIT/runtime.

**Hai kiểu công bằng cần phân biệt:**

- **Cùng heap settings**: so collector trong cùng ngân sách `-Xms`/`-Xmx`; có ích để cô lập ảnh hưởng của GC.
- **Cùng mục tiêu dịch vụ**: có thể tune riêng mỗi collector sau vòng baseline để xem cấu hình tốt nhất trong **cùng giới hạn RSS/CPU/SLO**; lúc này đây là so **giải pháp được tune**, không còn GC-only.

Đừng trộn hai vòng mà không ghi nhãn.

## 5. Chọn các metrics có ý nghĩa: pause, p99, throughput, footprint

### 5.1. Application latency: p50, p95, p99, p99.9

**Request latency** là thời gian hoàn tất một yêu cầu thực tế, bao gồm application work, I/O, lock contention, scheduling, GC effects, v.v.

- `p50`: trung vị; phản ánh trải nghiệm thường gặp.
- `p95`: 95% số mẫu không vượt mức này (theo cách tính percentile đã chọn).
- `p99`: khoảng 99% số mẫu không vượt; chú ý tail latency.
- `p99.9`: phân vị rất cao, cần đủ số mẫu để đáng tin.

Ví dụ nếu có 10.000 requests trong mẫu, p99 nói về ranh giới của nhóm khoảng 100 requests chậm nhất, **không có nghĩa GC pause p99 bằng request p99**.

**Đo ở đâu?** Từ load generator hoặc distributed tracing ở endpoint, có histogram đủ độ phân giải. Nếu có timeout/error, phải **đếm riêng và không loại bỏ có chọn lọc các requests thất bại**, vì điều đó làm kết quả “đẹp giả”.

**Cảnh giác coordinated omission:** nếu load generator đợi response rồi mới gửi request kế tiếp, lúc server bị dừng/đơ nó sẽ **không tạo ra các requests đáng lẽ xảy ra**, có thể đánh giá thấp tail latency. Dùng load model có arrival rate được kiểm soát hoặc công cụ xử lý coordinated omission thích hợp.

### 5.2. GC pause durations

Đây là thời lượng các khoảng JVM khiến mutator threads tạm dừng vì GC phases. Dùng `-Xlog:gc`, JFR hoặc telemetry có cơ sở.

**Chú ý:**

- ZGC/Shenandoah có thể có pause thấp nhưng vẫn tiêu tốn CPU ở **concurrent phases**.
- G1 có những STW evacuation pauses dài hơn, nhưng tổng throughput có thể cao ở một số workloads.
- Các GC event names/phase definitions **không giống nhau**; không gộp mọi dòng có chữ GC làm “pause”.
- Một Full GC hoặc degenerated GC hiếm có thể chi phối p99.9, dù p50 rất tốt.

Vì vậy cần biết cả **GC pause histogram** và **ứng dụng chịu tác động thực tế thế nào**.

### 5.3. Throughput

Công thức chung:

~~~text
Throughput = số yêu cầu thành công / thời gian đo (giây)
~~~

Đo trong **đoạn steady state**. Nếu workload là batch, có thể dùng jobs/s, records/s hoặc bytes/s. Nên ghi cả success ratio và error/timeout rate.

Không gọi “trình xử lý GC nhanh hơn” chỉ vì có nhiều GC cycles hơn/ít hơn. Throughput nói về **công việc ứng dụng thực sự hoàn thành**.

### 5.4. Footprint: heap, RSS và container memory

Phân biệt:

- **Heap used**: memory đang dùng trong Java heap tại một thời điểm.
- **Heap committed**: memory VM đã commit cho heap.
- **Heap max**: upper bound heap nếu xác định được.
- **Process RSS / working set**: memory vật lý tiến trình có resident; bao gồm các vùng ngoài Java heap, tùy OS.
- **Container memory**: account/limit theo cgroup, không tương đương trực tiếp `Runtime.totalMemory()`.
- **Native memory**: thread stacks, metaspace, direct buffers, code cache, GC/JVM data structures và JNI.

**Không suy ra:** nếu cả ba dùng `-Xmx2g`, RSS chắc chắn như nhau. Thu gom đồng thời có overhead riêng; hệ điều hành và heap commit/uncommit cũng khác.

### 5.5. CPU và allocation pressure

Các số đo cần thiết:

- CPU process và CPU throttling time (đặc biệt container).
- CPU used by GC threads, nếu telemetry hỗ trợ.
- Allocation rate (MB/s) và live set.
- Old generation occupancy / promotions nếu mode có generations.
- Allocation stalls, degenerated/full GC và OOME.
- GC cycles/collection count như diagnostic, **không phải ranking metric độc lập**.

**Bảng đánh giá:** muốn “low latency” phải đo tail request latency + GC pauses + stalls, chứ không chỉ báo một giá trị “GC time”.

## 6. Đơn vị, phần trăm và cách ghi kết quả

### 6.1. Milliseconds, nanoseconds và seconds

- `System.nanoTime()` phù hợp đo **thời gian đã trôi qua** trong cùng tiến trình.
- `System.currentTimeMillis()` là wall-clock, có thể thay đổi vì chỉnh giờ; không ưu tiên tính elapsed benchmark.
- GC logs có thể dùng các decorators `uptime`, `time`, `level`, `tags`; phải xem đúng đơn vị.
- Ghi **ms** hoặc **µs** rõ ràng. `0.5 ms` và `500 µs` là cùng độ dài, không phải hai kết quả khác.

### 6.2. MB so với MiB

~~~text
1 MB  = 1,000,000 bytes
1 MiB = 1,048,576 bytes
1 GiB = 1,073,741,824 bytes
~~~

Các tham số `-Xmx512m` của HotSpot thường dùng suffix JVM để chỉ size binary-equivalent, còn dashboards có thể đổi thành base-10 MB. Khi so footprint, **quy đổi tất cả về bytes** để tránh lệch 5–7% mà không nhận ra.

### 6.3. GC overhead không đơn giản là tổng pause / wall time

Một số teams tính:

~~~text
STW pause fraction ≈ sum(GC stop-the-world pauses) / elapsed wall time
~~~

Đây là **chỉ số pause burden**, **không phải toàn bộ CPU cost của GC**, vì ZGC và Shenandoah có **concurrent CPU work**, và G1 cũng có các concurrent phases.

Kết luận “collector A có tổng pause time ít hơn nên không tốn tài nguyên hơn” là sai. Cần CPU samples, throughput và RSS nữa.

### 6.4. So sánh thống kê: đừng nhìn một lần chạy

Với mỗi collector, chạy **nhiều trials độc lập** (ví dụ ít nhất 5 lần) sau warm-up, giữ nguyên tiêu chí chọn mẫu. Công bố:

- Median throughput và khoảng biến thiên.
- p95/p99 latency mỗi trial, không chỉ một percentile gộp chung thiếu ngữ cảnh.
- Peak RSS/container memory.
- GC pause histogram, số lần full/degenerated/stalls.
- CPU percent/throttling; error rate.
- JDK/version/build, flags, host/container limits, workload và thời lượng.

Nếu dữ liệu dao động lớn, cần kéo dài run hoặc tăng số lần thử; đừng kết luận “tốt hơn 2%” từ hai runs nhiễu 10%.

## 7. Bước 1: kiểm tra chính runtime sẽ đo

Trước khi chạy bất kỳ benchmark nào:

~~~bash
java -version
java -XX:+UseG1GC -version
java -XX:+UseZGC -version
java -XX:+UseShenandoahGC -version
~~~

**Lưu ý:** đây là probes chạy **lần lượt**, không phải yêu cầu bật cả ba cùng lúc. Nếu một lệnh không được hỗ trợ, ghi nhận rõ; không đo tiếp như thể collector đó hiện diện.

Đặc biệt khi thử Shenandoah:

~~~bash
# Trên POSIX shell, fail fast nếu collector không có.
if java -XX:+UseShenandoahGC -version >/dev/null 2>&1; then
  echo "Shenandoah supported by this JVM"
else
  echo "Shenandoah unavailable in this JVM build" >&2
fi
~~~

Script chỉ kiểm tra collector **được chấp nhận tại startup**; không chứng minh performance. Sau đó phải xác minh **actual GC** từ startup logs/flags của ứng dụng.

Nếu `java -version` trả JDK 27 nhưng Shenandoah probe fail, **đó là một kết quả hợp lệ về availability**. Không buộc phải đổi vendor chỉ để đủ ba cột; có thể hoàn thành phần G1/ZGC và báo rằng Shenandoah chưa khả dụng. Nếu quyết định đổi runtime để lấy Shenandoah, ghi rõ confounding JVM build.

### Ghi lại thông tin tối thiểu

~~~text
JDK feature version, update/patch level
JVM vendor, VM implementation, build ID
OS, CPU architecture, CPU cores/quota
RAM/container memory limit
Java application build/version
Dependency versions, workload/data snapshots
Xms/Xmx, collector flags and other JVM args
Observed GC mode from VM flags/startup logs
Logging/JFR profiling configuration
~~~

Đừng dùng chỉ tên folder có chữ `jdk-27` làm bằng chứng về binary đang chạy; các wrappers, containers và env vars có thể chọn runtime khác.

## 8. Bước 2: thiết kế kế hoạch A/B/C

Một cách tiếp cận gồm **hai vòng**:

### Vòng A: so collector với settings chung

- Chọn JDK build **hỗ trợ các collectors cần đo**.
- Dùng cùng `-Xms`/`-Xmx` và cùng container CPU/memory limits.
- Ghi rõ mode Shenandoah `satb` hoặc `generational`; nếu so cả hai, tách thành ứng viên riêng.
- Dùng một application binary và cùng dữ liệu, traffic schedule.
- Warm-up JVM/application tới ổn định.
- Thu p99/throughput/RSS/GC logs/JFR trong cửa sổ steady state giống nhau.
- Lặp lại các runs với thứ tự được đảo để giảm ảnh hưởng thermal/cache drift.

### Vòng B: tune từng collector cho cùng SLO và resource budget

Sau khi baseline, chỉ tinh chỉnh những cờ được **tài liệu JDK đó** hỗ trợ:

- G1: heap sizing, pause target (`MaxGCPauseMillis`) khi thật sự cần.
- ZGC: heap headroom, `SoftMaxHeapSize` nếu có lý do footprint.
- Shenandoah: chọn SATB/generational nếu build hỗ trợ, heap headroom, heuristics đúng mode.
- Mọi collector: CPU limit, native memory budget, allocation behavior.
- Giữ **cùng tiêu chí chấp nhận** (ví dụ p99 mục tiêu, max RSS, throughput tối thiểu) rồi chọn cấu hình đạt SLO với tổng chi phí tốt.

Đây là hai câu hỏi khác nhau: “collector nào tốt hơn ở settings bằng nhau?” và “tổ hợp collector+tuning nào phù hợp dịch vụ?”. Không được trộn câu trả lời.

### Ví dụ tiêu chí chấp nhận, không phải kết quả thực đo

Một service có thể đặt mục tiêu:

~~~text
p99 request latency <= 80 ms
successful throughput >= 2,000 requests/s
error rate <= 0.1%
peak container memory <= 3 GiB
no unplanned OOME or full-GC latency spikes
~~~

Đây là **mục tiêu giả định để minh họa cách thiết kế thí nghiệm**, không phải chỉ số đã đạt được. Khi đưa vào thực tế, phải thay bằng SLO được đội sản phẩm xác nhận.

## 9. Bước 3: chạy ba collector bằng cùng Java class

Giả sử bạn có chương trình Java ở phần 12 trong file `GcComparisonDemo.java`. Biên dịch:

~~~bash
javac GcComparisonDemo.java
~~~

Sau đó mở **ba tiến trình JVM độc lập, chạy tuần tự**, mỗi lệnh có cùng heap policy. Không chạy cả ba trong một process; collector được lựa chọn khi JVM khởi động, không chuyển mode giữa chừng.

### 9.1. G1 trial

~~~bash
java -XX:+UseG1GC -Xms128m -Xmx512m -Xlog:gc=info:file=g1-gc.log GcComparisonDemo
~~~

### 9.2. ZGC trial

~~~bash
java -XX:+UseZGC -Xms128m -Xmx512m -Xlog:gc=info:file=zgc-gc.log GcComparisonDemo
~~~

### 9.3. Shenandoah trial khi JVM có support

~~~bash
java -XX:+UseShenandoahGC -Xms128m -Xmx512m -Xlog:gc=info:file=shen-gc.log GcComparisonDemo
~~~

**Những cờ đáng chú ý:**

- `-XX:+UseG1GC`, `-XX:+UseZGC`, `-XX:+UseShenandoahGC` chỉ để **chọn một collector**.
- `-Xms128m -Xmx512m` làm ngân sách heap ban đầu/max giống nhau trong vòng A.
- `-Xlog:gc=info:file=...` xuất GC logs vào các file khác nhau; hãy xử lý log rotation và quyền ghi trong môi trường production.
- Chạy nối tiếp các lệnh để tránh cả ba JVM cạnh tranh cùng CPU/RAM, **hoặc** thiết kế phòng thí nghiệm cô lập tương đương.

**Không coi chạy xong ba lệnh là một benchmark đủ mạnh:** class demo là một micro-workload minh họa. Phải dùng workload của dịch vụ thật, có warm-up, tải liên tục và số mẫu đủ lớn nếu mục tiêu là quyết định production.

### 9.4. Nếu muốn thử Generational Shenandoah như ứng viên thứ tư

Với JDK 25+ build có support:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xms128m -Xmx512m -Xlog:gc=info:file=shen-gen-gc.log GcComparisonDemo
~~~

**Ghi rõ đây là ứng viên khác với Shenandoah SATB mặc định** trên các build JDK 25–27 đã xác minh. Tên “Shenandoah” mà không ghi mode không đủ để tái lập kết quả.

## 10. Bước 4: lấy GC log có ích nhưng không gây quá tải

**Unified JVM Logging** dùng `-Xlog`, là phương pháp hiện hành:

~~~bash
# Mức gọn, phù hợp ban đầu:
java -XX:+UseG1GC -Xlog:gc=info -jar app.jar

# Có thêm GC sub-tags và safepoint events:
java -XX:+UseG1GC -Xlog:gc*,safepoint:file=gc-detail.log:time,uptime,level,tags:filecount=5,filesize=10M -jar app.jar
~~~

Câu lệnh thứ hai dùng cú pháp HotSpot unified logging cho tag sets và xoay log file. Trên shell có xử lý wildcard, có thể quote nguyên option phù hợp để tránh shell expansion. Không phải mọi logger đều ghi cùng một bộ phase names hoặc tag combinations; dùng `-Xlog:help` để xem tags/levels được bản JVM hỗ trợ.

**Những điều cần trích xuất:**

- Collector được chọn khi startup.
- Pauses có thời lượng cụ thể (phân biệt STW với concurrent phases).
- Full GC, degenerated GC, allocation stalls nếu collector báo.
- Trước/sau heap occupancy, free memory, concurrent cycles.
- Safepoint pauses không hoàn toàn do GC nếu có.
- Những time windows trùng với request-latency spikes.

### Lỗi parsing thường gặp

Một dòng log có chữ “concurrent” với thời lượng 200 ms **không phải** ứng dụng bị stop-the-world 200 ms. Ngược lại, một pause 5 ms thực sự có thể góp phần vào request p99 trong đúng thời điểm.

Không cộng mọi durations có chữ “GC” thành STW time. Dùng event type/phase và timestamp phù hợp từng collector. Khi đổi JDK vendor/version, parser cần được kiểm tra lại.

### Log cũng có overhead

GC logging chi tiết `debug/trace` có thể làm tăng I/O và CPU. Để so công bằng, giữ **cùng mức logging**, điều kiện disk I/O và rotation policy. Không bật JFR profile chi tiết riêng cho ZGC trong khi G1 chỉ log mức info.

## 11. Bước 5: dùng JFR và công cụ OS/containers

### 11.1. Java Flight Recorder (JFR)

JFR thu thập sự kiện JVM có timestamps và cho phép phân tích GC, allocations, safepoints, CPU và memory tùy event settings của JDK. Có thể bắt đầu recording ngay khi chạy:

~~~bash
java -XX:+UseG1GC -Xms128m -Xmx512m -XX:StartFlightRecording=filename=g1-trial.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Muốn đo ZGC hoặc Shenandoah, thay collector flag và đổi tên file JFR. Không dùng các switch legacy dành cho những JDK rất cũ như một bước “bắt buộc kích hoạt Flight Recorder”.

**`settings=profile`** có thể tăng profiling overhead và dung lượng. Khi so throughput/latency tuyệt đối, cần đo overhead của JFR và có thể chạy song song một vòng **không profiling**. JFR không nên là lý do khiến một collector bị xếp hạng thấp không công bằng.

### 11.2. JFR qua `jcmd`

Nếu service đã chạy và JDK tools/permissions cho phép:

~~~bash
jcmd
jcmd 12345 JFR.start name=gc-trial settings=profile duration=120s filename=gc-trial.jfr
jcmd 12345 JFR.check
~~~

`12345` là **PID minh họa**, thay bằng PID thật; `duration=120s` chỉ là ví dụ. `JFR.start` có thể có arguments khác theo bản JDK. Không thay thế kiểm thử steady state bằng một bản recording ngắn không bao trùm peak load.

### 11.3. `jcmd` và MXBeans

~~~bash
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
~~~

Các lệnh giúp kiểm tra JVM args, effective flags, heap information. Một số command có thể không khả dụng vì VM/provider hoặc bị chặn do quyền attach. Không tự tạo số liệu nếu tool thất bại; ghi nhận giới hạn đo lường.

Qua Java Management API có thể dùng:

- `ManagementFactory.getGarbageCollectorMXBeans()`;
- `ManagementFactory.getMemoryMXBean()`;
- `MemoryUsage.getUsed()/getCommitted()/getMax()`;
- `GarbageCollectorMXBean.getCollectionCount()/getCollectionTime()`.

**Cảnh báo:** MXBeans có thể trả `-1` khi dữ liệu không xác định; bean names/counts và semantics của các events không nhất quán giữa collectors. Dùng chúng làm **telemetry bổ trợ**, không lấy `collectionTime` làm bằng chứng toàn bộ CPU cost.

### 11.4. OS/container metrics

Java heap metrics không cho biết toàn bộ memory footprint của tiến trình. Bổ sung:

- Process RSS, container working set/usage, cgroup memory peak.
- CPU used/CPU throttling; hệ số CPU quota.
- GC/JVM native memory khi cần; có thể bật NMT theo tài liệu bản JDK.
- Network I/O, DB latency, event-loop queue length và backpressure.
- Pod restarts/OOMKilled, page faults và disk I/O.

NMT (Native Memory Tracking) có thể hỗ trợ xem một số vùng native nếu được bật lúc startup; vì có overhead, ghi rõ thí nghiệm nào đã bật:

~~~bash
java -XX:NativeMemoryTracking=summary -XX:+UseG1GC -Xmx512m -jar app.jar
~~~

Sau khi ứng dụng chạy, thử với PID thực:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

Không gọi NMT là RSS measurement hay bộ đo native memory hoàn chỉnh: NMT chỉ theo dõi những phân bổ mà JVM có thể ghi nhận, không phải mọi native allocation của mọi thư viện.

## 12. Ví dụ Java 17+ chạy được: workload phân bổ có kiểm soát

Mục tiêu của demo **không phải** tuyên bố collector nào thắng. Nó tạo cùng một mẫu phân bổ object/array, có warm-up rồi đo nhiều runs bằng `System.nanoTime()`, ghi diagnostics về heap và GC MXBeans để người học biết cách cấu trúc thí nghiệm. Muốn đo latency SLO, vẫn phải dùng workload và load generator thực tế.

Tạo file **`GcComparisonDemo.java`**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.List;
import java.util.Locale;

public final class GcComparisonDemo {
    private static final int ROUNDS = 12_000;
    private static final int BLOCK_BYTES = 8 * 1024;
    private static final int RETAINED_SLOTS = 128;
    private static final int WARMUPS = 2;
    private static final int MEASUREMENTS = 5;

    private static volatile long sink;

    private static long work(int seed) {
        byte[][] retained = new byte[RETAINED_SLOTS][];
        long checksum = 0;

        for (int i = 0; i < ROUNDS; i++) {
            byte[] block = new byte[BLOCK_BYTES];
            block[0] = (byte) (i + seed);
            block[BLOCK_BYTES - 1] = (byte) (i >>> 6);
            retained[i % RETAINED_SLOTS] = block;
            checksum += block[0] & 0xff;
            checksum += block[BLOCK_BYTES - 1] & 0xff;
        }

        // Giữ một thao tác đọc qua những mảng còn reachable.
        for (byte[] block : retained) {
            checksum += block[0] & 0xff;
        }
        return checksum;
    }

    private static long heapUsed() {
        MemoryUsage usage = ManagementFactory
                .getMemoryMXBean().getHeapMemoryUsage();
        return usage.getUsed();
    }

    public static void main(String[] args) {
        System.out.println(
                "workload=arrays; rounds=12000; bytes=8192; retained=128");
        System.out.println(
                "warmups=2; measured_runs=5");
        System.out.println(
                "run,elapsed_ms,ns_per_array,heap_used_after_bytes");

        for (int i = 0; i < WARMUPS; i++) {
            sink = work(i);
        }

        for (int run = 1; run <= MEASUREMENTS; run++) {
            long started = System.nanoTime();
            sink = work(100 + run);
            long elapsed = System.nanoTime() - started;

            double elapsedMs = elapsed / 1_000_000.0;
            double nsPerArray = (double) elapsed / ROUNDS;

            System.out.printf(Locale.ROOT,
                    "%d,%.3f,%.1f,%d%n",
                    run, elapsedMs, nsPerArray, heapUsed());
        }

        System.out.println("gc_beans:");
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();
        for (GarbageCollectorMXBean bean : beans) {
            System.out.println(bean.getName()
                    + ",collections=" + bean.getCollectionCount()
                    + ",collection_time_ms="
                    + bean.getCollectionTime());
        }
        System.out.println("checksum_positive=" + (sink > 0));
    }
}
~~~

### 12.1. Biên dịch

~~~bash
javac GcComparisonDemo.java
~~~

Các API từ `java.lang.management` và `java.util` được dùng đều ổn định; trên compiler còn hỗ trợ target Java15, có thể thử:

~~~bash
javac --release 15 GcComparisonDemo.java
~~~

Không dùng preview features. **Collector vẫn được chọn bởi runtime flags**, bất kể compiler target.

### 12.2. Chạy với G1, ZGC, Shenandoah

~~~bash
java -XX:+UseG1GC -Xms128m -Xmx512m GcComparisonDemo
java -XX:+UseZGC -Xms128m -Xmx512m GcComparisonDemo
java -XX:+UseShenandoahGC -Xms128m -Xmx512m GcComparisonDemo
~~~

Chỉ chạy lệnh Shenandoah khi probe xác nhận runtime hỗ trợ. Nếu cần log, thêm `-Xlog:gc=info:file=...` giống phần 9.

### 12.3. Stdout: phần cố định và phần thay đổi

**Ba dòng đầu có nội dung xác định:**

~~~text
workload=arrays; rounds=12000; bytes=8192; retained=128
warmups=2; measured_runs=5
run,elapsed_ms,ns_per_array,heap_used_after_bytes
~~~

Sau đó chương trình in **năm hàng số liệu đo trực tiếp** theo format:

~~~text
run,elapsed_ms,ns_per_array,heap_used_after_bytes
~~~

Không thể đưa ra **con số chính xác cho các hàng dữ liệu** khi chưa chạy trên JVM/OS thực; chúng khác theo JIT, GC, CPU, scheduling và heap. Tiếp theo là các dòng `gc_beans:`, tên bean/counters thực tế và dòng kết `checksum_positive=true`. Ví dụ không bịa một bảng thời gian cố định hay một số collections cố định.

**Điểm quan trọng khi hiểu code:**

- `ROUNDS=12000` và `BLOCK_BYTES=8192` tạo **98.304.000 bytes array payload danh nghĩa mỗi trial** (chưa tính headers và allocations phụ).
- `RETAINED_SLOTS=128` giữ khoảng **1 MiB array payload** sống tới cuối method; phần lớn arrays cũ có thể được GC thu hồi.
- `WARMUPS=2` cho JIT và runtime một cơ hội khởi động; **không bảo đảm steady state** cho một microbenchmark.
- `MEASUREMENTS=5` là các runs đo trong **một process**, không thay cho năm **fresh-process trials**.
- `System.nanoTime()` đo elapsed time trong mỗi run, không đo request latency.
- `heapUsed()` chụp heap used **tại một thời điểm sau run**, không phải peak heap/RSS.
- `getCollectionCount()/getCollectionTime()` là telemetry; `-1` có nghĩa giá trị có thể undefined, và sematics khác nhau.
- `sink` là volatile giúp tác động của workload được quan sát; tuy nhiên JIT vẫn có thể tối ưu khác nhau theo collector/JDK, nên không dùng demo như chứng minh hiệu năng sản phẩm.

### 12.4. Vấn đề microbenchmark có thể mắc phải

- Warm-up quá ngắn để JIT/libraries đạt trạng thái ổn định.
- Workload quá đều, không phản ánh payloads, caches, database và concurrent requests thực.
- GC không phải bottleneck ở heap nhỏ.
- CPU cache và memory allocator behavior làm elapsed run biến động.
- JIT có thể tối ưu những thao tác không cần thiết về mặt kết quả.
- In stdout trong vùng đo gây I/O overhead; code demo chỉ in **sau khi** kết thúc khoảng `nanoTime`.
- Đo không tách throughput application với overhead GC.
- GC bean counters không đủ định danh STW pause distribution.

Để quyết định production, dùng workload thực tế và có thể dùng một harness benchmark chuyên dụng như **JMH** cho microbenchmarks, kết hợp end-to-end load tests để đo SLO. Không dựa vào một chương trình `main` đơn giản như bằng chứng cuối.

## 13. Công thức kiểm chứng và cách báo cáo số liệu

### 13.1. Một bảng tổng hợp phải làm rõ cơ sở đo

Thay vì tự đưa các con số “có vẻ hợp lý” vào báo cáo, mỗi dòng kết quả phải gắn với:

- Collector + mode;
- JDK runtime binary/build ID;
- Heap settings và container CPU/memory budget;
- Traffic shape và duration;
- Number of trials và warm-up criteria;
- p99 latency, throughput, RSS, CPU, pauses và error rate **thực đo**;
- Công cụ đo và links đến GC log/JFR/metrics.

### 13.2. Ví dụ tính throughput

Giả sử **một trial cụ thể** hoàn tất 120.000 requests thành công trong 60 giây. Khi đó:

~~~text
throughput = 120000 / 60 = 2000 requests/s
~~~

Đây chỉ là **ví dụ số học** để giải thích công thức, không phải số đo của G1/ZGC/Shenandoah.

### 13.3. Đánh giá p99 đúng trọng tâm

Một metric `GC pause p99=2 ms` **không** bảo đảm `request latency p99≤2 ms`. Một request có thể:

- Đang chờ database 50 ms;
- Chờ lock 20 ms;
- Bị CPU scheduling delay;
- Bị GC pause trong 1 ms;
- Có network retries và serialization;
- Gặp allocation stall/concurrent GC contention.

Các thành phần này không nhất thiết cộng tuyến tính trong mọi request, nhưng cho thấy **tại sao cần end-to-end traces**.

### 13.4. Đánh giá biến thiên và uncertainty

Nếu median throughput của G1 là 2000 requests/s, ZGC 1980 requests/s nhưng runs tự dao động ±100, chưa đủ cơ sở nói ZGC “kém hơn 1%”. Cần tăng số trials hoặc kiểm soát nhiễu.

Nên báo:

- Median + min/max hoặc confidence interval thích hợp.
- p99 theo từng trial và phương pháp gộp.
- Error/timeouts cùng throughput.
- Peak footprint và CPU throttling.
- GC logs/JFR để giải thích outliers.
- Những trường hợp **support unavailable** thay vì tự bỏ sample.

## 14. Đọc GC log: “pause ngắn” không đồng nghĩa “GC rẻ”

### 14.1. G1

Ở G1, cần xem:

- `Pause Young`, `Pause Mixed`;
- Full GC khi có, và nguyên nhân;
- Evacuation failure, humongous allocations, region pressure;
- Pause durations so với target và application p99;
- Concurrent marking, CPU overhead và heap usage.

**`-XX:MaxGCPauseMillis` là mục tiêu, không phải hạn mức tuyệt đối**. Nếu live set lớn, heap thiếu headroom hoặc CPU throttled, pause có thể vượt mục tiêu. Không loại các outliers khỏi phân tích.

### 14.2. ZGC

Ở ZGC hiện hành cần quan sát:

- Young/old cycles của generational mode (JDK24+);
- Những **STW pauses** có tên cụ thể trong log;
- Concurrent phases và CPU cost;
- Allocation stalls, heap pressure và footprint;
- Memory committed/uncommitted, container RSS.

Nếu GC pauses rất thấp nhưng response p99 xấu, kiểm tra CPU throttling, allocation stalls, lock contention và memory pressure. Không kết luận ZGC “không gây tác động” chỉ vì biểu đồ pauses nhỏ.

### 14.3. Shenandoah

Khi được hỗ trợ, phải ghi rõ:

- SATB hoặc generational;
- Concurrent marking/evacuation/update phases;
- Degenerated/full GC và nguyên nhân;
- Allocation pacing/stalls;
- Heap/cgroup headroom, CPU throttling;
- Pauses và ứng dụng latency.

Đặc biệt **một degenerated/full GC hiếm** có thể rất quan trọng với SLO, dù phần lớn pauses nhỏ. Không bỏ các khoảng thời gian bất lợi khỏi data window vì “không đại diện”.

### 14.4. Safepoints khác GC pauses

Một safepoint có thể do hoạt động VM **khác GC**. Nếu chỉ nhìn end-to-end latency, không thể quy mọi stall cho GC. Logging `-Xlog:safepoint` hoặc JFR giúp tách nguyên nhân, nhưng cần chú ý overhead. So sánh collectors mà không phân biệt nguyên nhân pause sẽ dẫn tới kết luận sai.

## 15. Bộ tiêu chí chẩn đoán theo triệu chứng

| Triệu chứng | Có thể do đâu? | Kiểm tra trước |
| --- | --- | --- |
| Request p99 cao, GC pauses thấp | DB, locks, network, CPU throttling, allocation stall | App tracing, CPU, queueing, allocation stalls |
| G1 Young GC pauses vượt target | Live data nhiều, evacuation/scan roots, heap pressure | `gc+phases` logs, heap sizing, CPU |
| G1 Full GC hiếm nhưng rất dài | Heap exhaustion, evacuation failure, humongous objects | Full GC cause, heap dump, allocation profile |
| ZGC có nhiều allocation stalls | Concurrent GC không reclaim kịp allocation | Xmx/headroom, CPU throttling, live set |
| Shenandoah có degenerated GC | Concurrent GC chậm/không đủ free regions | GC logs, CPU/headroom, allocation rate |
| RSS lớn hơn Xmx | Native/metaspace/stacks/direct buffers và mappings | Process RSS, NMT/JFR, container metrics |
| CPU cao sau đổi GC | Concurrent threads, barriers, more frequent cycles | CPU profiles, throughput, GC logs |
| Throughput tăng nhưng p99 xấu | Collector ưu tiên throughput hoặc pause outliers | p99/p99.9, STW pauses, tail tracing |
| p99 tốt nhưng container OOMKilled | Native memory + heap vượt cgroup limit | RSS, cgroup memory, native overhead |
| Shenandoah option không nhận | Vendor/build/platform không có | `java -version`, probe flag, image digest |
| Cờ generational Shenandoah bị từ chối | JDK/mode không hỗ trợ | JDK25+ build và `PrintFlagsFinal` |
| Count/time GC beans “bất thường” | Semantics/bean naming khác hoặc -1 | GC logs/JFR thay vì lấy bean count xếp hạng |
| Tăng `-Xmx` làm p99 tốt hơn | Giảm heap pressure, nhưng memory cost tăng | Đánh đổi RSS/CPU, test memory limits |
| Chạy lượt đầu chậm hơn | Class loading, JIT compilation, caches | Warm-up, steady state, repeated trials |
| Chạy ba collector cùng lúc làm số tệ | Contention CPU/RAM/network | Sequential trials hoặc cô lập tài nguyên |
| Đổi JDK vendor cho Shenandoah làm hiệu năng khác | Runtime/JIT/library không giống | Ghi confound, baseline lại cùng vendor |

## 16. Các lỗi suy luận thường gặp

### Sai: “GC pause nhỏ nhất = collector tốt nhất”

GC pause là một metric. Collector có thể có pauses nhỏ nhưng gây **concurrent CPU contention**, làm throughput giảm hoặc request scheduling latency tăng. Cần quyết định dựa trên **business SLO và resource budget**.

### Sai: “Không thấy GC log = không có GC”

Ứng dụng có thể chưa đủ allocation pressure, logging chưa bật đúng tags, log bị redirect hoặc collector không in phase trong cửa sổ quan sát. Phải xác minh collector/mode qua startup logs và flags; không kết luận từ sự im lặng.

### Sai: “`collectionTime` của MXBean là tổng thời gian CPU GC”

`getCollectionTime()` là telemetry về thời gian thu gom theo bean contract, **không phải tổng CPU của mọi GC threads**, đặc biệt khi có concurrent phases. Không so trực tiếp metric đó giữa G1, ZGC và Shenandoah như một phép đo overhead đầy đủ.

### Sai: “`System.gc()` giúp benchmark công bằng”

`System.gc()` là yêu cầu explicit GC, cách xử lý phụ thuộc collector/flags; nó có thể làm biến dạng workload và không tương đương giữa collectors. Không gọi nó theo vòng để ép “số GC như nhau” khi so performance sản phẩm.

### Sai: “G1 dùng p99 cao hơn ZGC trong một bài blog, nên hệ thống này cũng thế”

Workload, live set, heap, CPU, runtime version, OS và JDK implementation khác. Hiệu năng GC có thể đảo chiều khi object lifetime pattern/traffic đổi. **Đo đúng ứng dụng**.

### Sai: “Chỉ cần 1 run vài giây”

JIT warm-up, class loading, heap state, cache và background noise có thể lấn át tác động GC. Cần **repeated trials, steady state, đủ sample size và cùng workload**.

### Sai: “Không có Shenandoah vẫn có thể báo ba collector”

Không. Trạng thái **unsupported/unavailable** là dữ liệu quan trọng của thí nghiệm. Đừng dùng kết quả fallback collector rồi đổi nhãn.

### Sai: “Đổi cùng lúc JDK + GC vẫn biết GC tạo ra mọi khác biệt”

Không. Khi JDK khác, JIT, library, heap layout, intrinsic implementations và defaults đều có thể thay đổi. Chỉ kết luận “configuration tổng thể A vs B”, không kết luận riêng collector.

## 17. Đề xuất quy trình benchmark triển khai được

### Giai đoạn 1 — Đặt câu hỏi và SLO

Viết rõ vấn đề: ví dụ “Mục tiêu giảm p99 API latency khi traffic tăng 2× nhưng không vượt 4 GiB container memory và CPU quota”. Chọn metrics và điều kiện nhận trước khi chạy, tránh chọn tiêu chí sau khi thấy kết quả.

### Giai đoạn 2 — Xác nhận build support

Chạy `java -version` và probe flags G1/ZGC/Shenandoah trên đúng container/host. Với Shenandoah, chỉ chạy khi tool probe success. Ghi JDK vendor/build/OS/arch.

### Giai đoạn 3 — Chuẩn hóa thí nghiệm

Dùng cùng binary/dependencies, CPU quota, heap max/min, container memory, data, connections, concurrency, arrival schedule. Không chạy thí nghiệm khi node bị noisy neighbor contention hoặc monitor thiếu dữ liệu.

### Giai đoạn 4 — Warm-up

Cho ứng dụng khởi động, JIT biên dịch, caches tải dữ liệu; chỉ bắt đầu đo khi throughput/latency ổn định theo tiêu chí đã đặt. Ghi warm-up length riêng, không ghép warm-up vào steady-state numbers nếu mục tiêu là latency khi ổn định.

### Giai đoạn 5 — Đo repeated trials

Thử từng collector trong process mới, lặp ít nhất vài lần, luân chuyển thứ tự test (ví dụ G1/ZGC/Shenandoah rồi Shenandoah/G1/ZGC) để tránh bias hệ thống theo thời gian. Ghi đủ errors/timeouts.

### Giai đoạn 6 — Thu thập quan sát

GC logs/JFR, p99 API latency, throughput, CPU, RSS, heap, allocation stalls, OOME/full/degenerated cycles. Dùng một tập lệnh naming/telemetry nhất quán.

### Giai đoạn 7 — Phân tích và tune riêng

Xem bản nào đáp ứng SLO, xét throughput/memory costs. Nếu cần, tune từng collector trong resource budget và chạy lại. Không giữ một cờ đã bị loại bỏ chỉ vì từng dùng trên Java15/21.

### Giai đoạn 8 — Canary/rollback

Deploy canary với collector đã chọn, theo dõi GC pauses + **application p99 + RSS + CPU + error rate**, có rollback cả flags và image nếu không đạt. Không quyết định chỉ từ một microbenchmark.

## 18. Bài tập kiểm tra kiến thức

**Câu 1.** Trong HotSpot JDK27, collector mặc định là gì, và vì sao benchmark vẫn nên ghi `-XX:+UseG1GC`?

**Đáp án:** **G1** theo JEP 523. Ghi cờ tường minh giúp loại bỏ mơ hồ khi script/env vars thay đổi default hoặc inject GC options.

**Câu 2.** Trên JDK27, `-XX:+UseZGC` sử dụng generational hay non-generational ZGC?

**Đáp án:** **Generational-only**. Non-generational ZGC đã bị loại bỏ từ JDK24; không dùng `ZGenerational` flag cũ.

**Câu 3.** Vì sao không thể mặc định benchmark Shenandoah trên mọi JDK27?

**Đáp án:** Collector phụ thuộc vendor/build/platform. Cần thử `java -XX:+UseShenandoahGC -version` trên chính runtime; nếu unsupported, ghi nhận và không giả mạo trial.

**Câu 4.** Trong JDK25–27 builds có Shenandoah, chọn Generational Shenandoah bằng cách nào?

**Đáp án:** `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational`. Mode `satb` còn là default theo tài liệu đã xác minh.

**Câu 5.** `GC pause p99=1ms` có nghĩa request p99 cũng bằng 1ms không?

**Đáp án:** Không. Request latency có I/O, locks, queuing, CPU và các chi phí khác; low GC pauses không bảo đảm end-to-end latency.

**Câu 6.** Vì sao cần đo process RSS khi cả ba dùng cùng `-Xmx2g`?

**Đáp án:** `Xmx` giới hạn Java heap, không gồm toàn bộ native memory, thread stacks, metaspace, code cache và GC overhead. RSS/working set có thể khác.

**Câu 7.** Nếu ZGC dùng CPU nhiều hơn và throughput thấp hơn G1 nhưng p99 thấp hơn, collector nào “thắng”?

**Đáp án:** Phụ thuộc SLO và resource budget. Nếu ứng dụng ưu tiên latency và vẫn đáp ứng throughput/CPU, ZGC có thể phù hợp; nếu chi phí không chấp nhận được, G1 có thể phù hợp.

**Câu 8.** Có nên cộng durations của concurrent GC phases vào tổng STW pause time?

**Đáp án:** Không. Concurrent phase không dừng toàn bộ mutator trong toàn thời lượng đó; phải phân biệt loại event.

**Câu 9.** Vì sao không so chỉ `getCollectionCount()` giữa G1 và Shenandoah?

**Đáp án:** GC cycles/generations/beans và semantics khác, nhiều cycles nhỏ không chứng minh latency/throughput kém. Cần metrics ứng dụng + logs.

**Câu 10.** Một thí nghiệm G1 chạy JDK27, Shenandoah chạy JDK25 vendor khác. Có phải GC-only comparison không?

**Đáp án:** Không. JVM/version/vendor là confounders. Báo là configuration comparison hoặc tìm build chung để cô lập collector.

**Câu 11.** Vì sao nên chạy trials theo nhiều thứ tự và lặp lại?

**Đáp án:** Giảm bias do host nhiệt, caching, background load, GC warm-up và biến thiên hệ thống; cung cấp khoảng phân tán thay vì một con số may rủi.

**Câu 12.** `System.gc()` có giúp ép mọi collector cùng thực hiện “một cycle” để so công bằng không?

**Đáp án:** Không. Explicit GC semantics phụ thuộc collector/flags và có thể làm lệch workload; đo allocation/traffic thật.

**Câu 13.** Vì sao một collector với pauses thấp vẫn có thể gây allocation stalls?

**Đáp án:** Concurrent GC cần thời gian và CPU để reclaim; nếu allocation nhanh hơn reclaim hoặc heap thiếu headroom, mutator có thể bị chờ cấp phát.

**Câu 14.** Nếu các request timeout bị loại khỏi percentile, điều gì sai?

**Đáp án:** Tail latency có thể bị đánh giá thấp vì bỏ mất requests thất bại/chậm nhất. Phải báo error/timeout rate và xác định cách xử lý samples minh bạch.

**Câu 15.** `System.nanoTime()` hay `System.currentTimeMillis()` phù hợp hơn để đo elapsed time của một trial?

**Đáp án:** `System.nanoTime()`, vì cung cấp nguồn đo elapsed monotonic trong cùng JVM, tránh lệch do điều chỉnh đồng hồ wall-clock.

**Câu 16.** Tại sao benchmark code Java ở phần 12 không đủ để chọn collector production?

**Đáp án:** Nó chỉ đo một allocation pattern ngắn, không mô phỏng concurrency, I/O, DB, request SLO, workload variations và steady state dài. Cần load test ứng dụng thật.

**Câu 17.** Nếu chỉ bật JFR profile cho ZGC mà G1 không bật, phép đo throughput có hoàn toàn công bằng không?

**Đáp án:** Không. Profiling overhead có thể khác; cần đo cùng điều kiện và tách vòng profiling khỏi vòng performance chính nếu cần.

**Câu 18.** JDK báo `-XX:+UseShenandoahGC` unsupported, có nên tự bỏ flag rồi vẫn đánh nhãn trial “Shenandoah” không?

**Đáp án:** Không. Phải báo **unavailable** hoặc dùng build hỗ trợ và ghi confounder; không falsify collector identity.

## 19. Checklist trước khi đưa kết luận vào báo cáo

- [ ] Ghi rõ JDK vendor, version, VM build, OS/architecture.
- [ ] Cả ba trials chạy với GC option thật và được xác minh startup.
- [ ] Nếu Shenandoah không có: báo unavailable, không tự fallback ngầm.
- [ ] ZGC được hiểu là generational trên JDK24+.
- [ ] Shenandoah SATB/generational được ghi đúng mode trên build hỗ trợ.
- [ ] Dùng cùng `-Xms`/`-Xmx` và container memory/CPU budgets cho baseline.
- [ ] Không thay application build, traffic schedule hay data giữa trials.
- [ ] Có warm-up, steady state, đủ samples và multiple fresh-process runs.
- [ ] Không chạy các collectors cùng lúc nếu cạnh tranh cùng host resources.
- [ ] Có p50/p95/p99/p99.9 application latency và throughput/errors.
- [ ] Có GC pause distributions và phân biệt concurrent phases.
- [ ] Có CPU utilization/throttling, RSS, heap usage và allocation rate.
- [ ] Có log/jfr evidence cho OOME, full/degenerated GC và allocation stalls.
- [ ] Đơn vị thời gian và memory thống nhất trong báo cáo.
- [ ] Có thông tin về overhead của logging/JFR.
- [ ] Không so MXBean collectionCount/time trực tiếp như ranking cuối.
- [ ] Không gọi benchmark ngắn trong `main` là bằng chứng production.
- [ ] Đã xem p99 outliers và giải thích nguyên nhân không phải GC nếu có.
- [ ] Có thí nghiệm tuning riêng khi cần, không trộn với baseline GC-only.
- [ ] Có quyết định theo SLO + cost và kế hoạch canary/rollback.

## 20. Nguồn kỹ thuật chính thức, còn áp dụng

- **Oracle JDK 27 — HotSpot Garbage Collection Tuning Guide:** https://docs.oracle.com/en/java/javase/27/gctuning/index.html
- **Oracle JDK 27 — Garbage-First (G1) Collector:** https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html
- **Oracle JDK 27 — Java command/Unified GC logging:** https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- **Oracle JDK 27 — Significant Changes / G1 default everywhere:** https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html
- **JEP 523 — G1 Default Garbage Collector in All Environments (JDK27):** https://openjdk.org/jeps/523
- **JEP 490 — ZGC: Remove the Non-Generational Mode (JDK24):** https://openjdk.org/jeps/490
- **JEP 521 — Generational Shenandoah Product (JDK25):** https://openjdk.org/jeps/521
- **Oracle JDK 25 — jcmd Tool / JFR commands:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html
- **Java SE 17 — GarbageCollectorMXBean:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html
- **Java SE 17 — MemoryMXBean:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
- **Java SE 17 — System.nanoTime():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
- **OpenJDK — Java Microbenchmark Harness (JMH):** https://github.com/openjdk/jmh

**Kết luận:** so sánh G1, ZGC và Shenandoah là **một thí nghiệm về trade-off**, không phải bài toán xếp hạng cố định. G1 là default của HotSpot JDK27 và thường cân bằng throughput/pause; ZGC dùng generational mode trên JDK24+ và tối ưu low pause; Shenandoah chỉ là ứng viên khi **JDK build/platform có hỗ trợ**, và phải ghi rõ SATB hay generational. Để chọn đúng cho ứng dụng, **giữ các biến môi trường nhất quán**, kiểm tra collector thực sự chạy, đo **p99 ứng dụng + GC pauses + throughput + CPU/RSS + stalls**, lặp lại nhiều lần rồi quyết định theo SLO, chi phí và khả năng vận hành. Không kết luận từ một dòng GC log, một giá trị MXBean hay một microbenchmark ngắn.
