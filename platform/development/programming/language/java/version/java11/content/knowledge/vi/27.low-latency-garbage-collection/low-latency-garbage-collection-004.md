# Đánh đổi giữa độ trễ, CPU và footprint của GC độ trễ thấp (Java 11+)

**Chủ đề cha: GC độ trễ thấp.** Garbage collector (GC) quyết định không chỉ JVM phải dừng ứng dụng bao lâu để thu gom rác mà còn cần bao nhiêu CPU, heap và bộ nhớ ngoài heap để duy trì công việc. **GC pause ngắn hơn không tự động đồng nghĩa request latency thấp hơn, throughput cao hơn hoặc RSS nhỏ hơn.** Bộ thu gom chạy phần lớn công việc đồng thời (*concurrent*) với Java threads có thể giảm stop-the-world (STW), nhưng phải dành CPU cho GC threads và đủ heap headroom để ứng dụng tiếp tục cấp phát trong lúc thu gom.

Từ Java 11 đến JDK hiện đại, việc lựa chọn chủ yếu xoay quanh **G1** (cân bằng), **ZGC** và **Shenandoah** (ưu tiên pause thấp nếu runtime hỗ trợ), **Parallel GC** (ưu tiên throughput) và đôi khi **Serial GC** với workload nhỏ. Bài học giải thích trade-off giữa **độ trễ, CPU và memory footprint**, cách đo đúng, ảnh hưởng của `-Xmx`/`-Xms`/CPU quota, ví dụ Java 11 chạy được, GC logs/JFR và quy trình so sánh cấu hình. Chỉ dùng các kỹ thuật **vẫn còn áp dụng hiện nay**; các collector hoặc flag đã legacy không phải lựa chọn cho hệ thống mới.

## 1. Ba mục tiêu khác nhau

| Mục tiêu | Chỉ số quan sát | Câu hỏi |
| --- | --- | --- |
| **Latency** | End-to-end response p50/p95/p99/p99.9, GC STW pause distribution | Bao nhiêu requests đáp ứng đúng deadline? |
| **CPU / throughput** | Requests/s, CPU-seconds/request, GC CPU, core utilization, throttling | Chi phí CPU và năng lực phục vụ có chấp nhận được? |
| **Footprint** | Heap used/committed, process RSS, container working set/limit, native memory | JVM có vừa trong ngân sách RAM và vận hành ổn định? |

**Latency** và **throughput** không có cùng mẫu số. Hệ thống xử lý 100.000 requests/s vẫn có thể có p99 latency kém nếu có những đợt STW dài hoặc hàng đợi quá tải. Ngược lại, collector giảm p99 pause có thể dùng thêm một ít CPU nhưng throughput tại tải cần thiết vẫn không đổi.

### Latency được đo ở đâu?

- **GC pause:** khoảng JVM dừng application threads do GC, do GC log hoặc JFR ghi nhận.
- **Request latency:** từ lúc request được nhận đến lúc response hoàn tất, gồm CPU, DB, network, locks, queues, scheduling và GC.
- **Tail latency:** p99 hoặc p99.9; hữu ích cho ứng dụng có deadline.
- **SLO:** ví dụ “99% requests dưới 80 ms” — đây là mục tiêu nghiệp vụ, không phải một JVM flag.

Có hai loại sai lầm phổ biến: so **maximum GC pause** với **p99 response** như thể chúng cùng một thống kê, và cho rằng thời gian GC concurrent phải cộng trực tiếp vào thời gian mỗi request. Concurrent work không làm ứng dụng dừng hoàn toàn nhưng có thể **tranh CPU**, nên ảnh hưởng tới throughput, queueing và p99 một cách gián tiếp.

### CPU được đo bằng đơn vị nào?

Phân biệt:

- **CPU time:** thời lượng thực tế các CPU cores xử lý một loại công việc; có thể lớn hơn elapsed wall time khi chạy song song.
- **CPU utilization:** phần công suất core/quota đang dùng.
- **Throughput:** số nghiệp vụ/giây; cao chưa chắc hiệu quả chi phí cao.
- **CPU-seconds/request:** tính tổng CPU consumptions chia requests đã xử lý, giúp so chi phí.

Ví dụ minh họa: server A chạy 40.000 requests/s với 2 cores, B chạy 43.000 requests/s nhưng dùng 4 cores. B có throughput tuyệt đối cao hơn nhưng **CPU efficiency có thể kém hơn**. GC concurrent có thể góp phần vào chênh lệch, nhưng phải đo thay vì đoán.

## 2. Tam giác latency–CPU–footprint

```text
                       LOW LATENCY
                       /         \
                      /           \
    Concurrent GC cần CPU        Cần headroom khi app
    trong lúc app đang chạy      vẫn allocate
                    /               \
                   /_________________\
           CPU / THROUGHPUT     MEMORY FOOTPRINT

   Không có một collector / flag luôn tối ưu cả ba.
```

Một bảng số liệu **giả định để luyện ra quyết định**, **không phải benchmark thật**:

| Candidate | p99 request | Requests/s | CPU trung bình | Peak RSS |
| --- | ---: | ---: | ---: | ---: |
| A | 105 ms | 24.000 | 2,4 core | 1,7 GiB |
| B | 68 ms | 22.500 | 2,9 core | 2,3 GiB |
| C | 130 ms | 21.000 | 2,2 core | 1,3 GiB |

Nếu SLO **p99 dưới 80 ms** và memory budget ít nhất 2,5 GiB, B đáng chọn. Nhưng nếu container RAM chỉ 1,8 GiB thì B **không đạt ràng buộc** bất kể p99 đẹp. Nếu SLO 150 ms và mục tiêu chính là chi phí, C có thể hợp lý. Cũng có thể A tốt hơn khi cần throughput cao.

**Không gán A/B/C cố định cho G1/ZGC/Parallel**: chỉ đo trên máy và workload mới biết thứ tự thực tế. Một GC phù hợp có thể đồng thời cải thiện hai chỉ số; không nên biến trade-off thành quy luật “luôn phải mất X% CPU để được Y ms”.

## 3. So sánh các collector còn được hỗ trợ

| Collector | Hướng tối ưu | Pause / concurrent work | Điểm cần kiểm tra |
| --- | --- | --- | --- |
| **G1 GC** | Cân bằng pause và throughput | Young/mixed STW, có concurrent phases | GC mặc định của HotSpot phổ biến từ JDK 9; phù hợp khởi đầu Java 11+ |
| **ZGC** | GC pause rất ngắn và tương đối độc lập heap size | Công việc lớn chủ yếu concurrent | CPU/headroom và phiên bản JVM; production từ JDK 15 |
| **Shenandoah** | GC pause rất ngắn với concurrent evacuation | Nhiều công việc concurrent | Vendor/build/JDK cụ thể có hỗ trợ không |
| **Parallel GC** | Throughput trên hệ nhiều CPU | Các đợt GC STW dùng nhiều threads | Có chấp nhận pause lớn hơn không? |
| **Serial GC** | Overhead/footprint đơn giản ở workload nhỏ | STW đơn luồng | Không mặc định tốt cho heap lớn nhiều core |

### Những mốc phiên bản cần hiểu đúng

- **G1** được chọn mặc định trên nhiều cấu hình HotSpot server-class, bao gồm Java 11 và các JDK hiện đại.
- **ZGC** xuất hiện như tính năng **experimental của JDK 11 (JEP 333)**, trở thành **production ở JDK 15 (JEP 377)**.
- **Generational ZGC** xuất hiện trong **JDK 21 (JEP 439)**; từ **JDK 24**, non-generational ZGC bị loại bỏ (**JEP 490**). Trên JDK 24+, không dùng option `ZGenerational` cũ để chọn chế độ.
- **Shenandoah** vào mainline ở **JDK 12 (JEP 189)**, được chuyển thành product feature ở **JDK 15 (JEP 379)**. Một số bản JDK 11 có backport, nhưng không suy rằng mọi JDK/vendor đều cung cấp.
- **CMS** từng hướng tới low pause nhưng đã deprecated và **bị xóa khỏi HotSpot từ JDK 14**. Không chọn CMS hoặc flags của nó cho hệ thống mới.
- Parallel và Serial vẫn là lựa chọn hiện hành, không phải obsolete chỉ vì chúng có STW.

**Lưu ý Special Note:** không lấy lệnh bật ZGC experimental từ JDK 11 làm hướng dẫn triển khai production hiện nay. Nếu đang vận hành Java 11, nên benchmark G1 ổn định trước và dùng các collector khác theo đúng bản build; dự án mới có thể sử dụng JDK LTS hiện đại có collector production được vendor hỗ trợ.

## 4. G1: mục tiêu pause là soft goal

G1 chia Java heap thành regions, thu gom theo từng collection set, điều chỉnh young-generation/collection set để cố đáp ứng **pause-time goal**. Nó còn thực hiện một số marking/refinement concurrent, do đó không phải “GC chỉ chạy STW”.

Ví dụ chạy service trên HotSpot hỗ trợ G1:

```bash
java -Xms512m -Xmx2g -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 -jar app.jar
```

Đây là **lệnh minh họa**; `app.jar` phải tồn tại và RAM/container memory phải đủ. `-XX:MaxGCPauseMillis=200` nghĩa là JVM **cố gắng** giữ các GC pauses theo mục tiêu 200 ms, **không bảo đảm** mọi pause dưới 200 ms và cũng không đặt SLO HTTP 200 ms.

### Giảm mục tiêu pause có thể làm gì?

```text
MaxGCPauseMillis: 200 -> 50 ms
          |
          v
G1 cố giữ mỗi STW collection nhỏ hơn
          |
          +-- thường chọn collection set/young gen nhỏ hơn
          +-- có thể phải GC nhiều lần hơn
          +-- tăng CPU overhead / metadata / barrier work
          +-- throughput có thể giảm
          +-- p99 có thể cải thiện hoặc không
```

Điều chỉnh này chỉ hữu ích khi log cho thấy G1 có khả năng chia công việc hiệu quả. Nếu heap quá chật hoặc concurrent marking không kịp, G1 vẫn có thể gặp **evacuation failure, to-space exhausted, Full GC** với pauses lớn.

**Oracle khuyến nghị vẫn phù hợp:** bắt đầu bằng G1 defaults, đặt `-Xmx` có cơ sở, rồi điều chỉnh pause target sau khi đã đo. **Tránh tự cố định young-gen bằng `-Xmn` hoặc `-XX:NewRatio`** khi muốn G1 tiếp tục điều chỉnh kích thước young generation để đạt pause target.

### Tăng mục tiêu pause có khi lại hợp lý

Với ứng dụng batch chấp nhận pause vài trăm ms, đặt pause goal quá thấp có thể khiến GC hoạt động quá thường xuyên. Nới mục tiêu từ 50 lên 200 ms có thể giảm overhead và tăng throughput, đổi lại tail pause có thể dài hơn.

**Không có công thức “50 tốt hơn 200”**. Quyết định dựa trên request SLO, CPU budget và kết quả thực tế, không dựa vào tên biến.

## 5. ZGC: ít STW nhưng phải trả công việc concurrent

ZGC thực hiện những công việc GC nặng như đánh dấu và di chuyển đối tượng phần lớn **concurrently** với Java threads. Các điểm STW được thiết kế rất ngắn; bản HotSpot hiện đại duy trì low pauses trên nhiều kích thước heap.

Nhưng:

1. **CPU GC:** concurrent workers và các runtime barriers tiêu thụ CPU trong lúc ứng dụng chạy.
2. **Heap headroom:** Java threads vẫn allocate trong lúc collector tìm và giải phóng object, nên cần dư heap ngoài live set.
3. **Khả năng theo kịp allocation:** nếu allocation rate vượt khả năng reclaim hoặc heap quá nhỏ, có thể xảy ra allocation stalls/khủng hoảng memory, tùy runtime.

Ví dụ cấu hình cơ bản trên **JDK có ZGC production**:

```bash
java -Xms1g -Xmx4g -XX:+UseZGC -jar app.jar
```

`-Xmx` thường là tham số quan trọng nhất để cấp headroom cho ZGC. Trong container có 2 vCPU và workload sát 100% CPU, chuyển sang collector concurrent **không tạo ra core miễn phí**. Nếu GC cần 0,5 vCPU, app có thể bị tranh CPU/throttling và request queue tăng dù max STW pause giảm.

### Lưu ý ở JDK 24+

Từ JDK 24, ZGC là **generational-only** và option `ZGenerational` đã bị loại bỏ. Vì vậy không đưa cấu hình kiểu `-XX:+ZGenerational`/`-XX:-ZGenerational` vào recipe cho JDK 24+. Khi học Java 11 cần biết ZGC lúc đó experimental, không đồng nhất tính sẵn sàng hỗ trợ của Java 11 với collector trong JDK 21/25 hiện đại.

## 6. Shenandoah và Parallel GC: hai chiến lược khác

**Shenandoah** cũng di chuyển/đánh dấu objects với nhiều pha concurrent, ưu tiên hạn chế STW. Nó phù hợp khi tail pause là mục tiêu quan trọng và người vận hành chấp nhận tiêu thụ CPU + heap headroom. Cách bật cơ bản trên **JDK có hỗ trợ**:

```bash
java -Xms1g -Xmx4g -XX:+UseShenandoahGC -jar app.jar
```

Với Shenandoah, **kiểm tra vendor và build trước**. Không phải mọi JDK 11 đều có hoặc có cùng mode/version; đừng mang một flag điều chỉnh nội bộ từ một bản Shenandoah cũ sang bản khác mà không đọc tài liệu.

**Parallel GC** cho phép nhiều GC threads dọn heap trong các đợt stop-the-world, hướng tới throughput. Nó còn dùng được trong Java mới:

```bash
java -Xms1g -Xmx4g -XX:+UseParallelGC -jar app.jar
```

Trong batch ETL, một pause dài hơn nhưng jobs/hour cao hơn có thể tốt. Trong API deadline 50 ms, pause 300 ms có thể không thể chấp nhận. **Thước đo nghiệp vụ quyết định lựa chọn**, không phải định kiến “concurrent GC luôn nhanh hơn”.

## 7. Heap headroom, live set và CPU

Ba khái niệm:

- **Live set:** lượng object còn reachable sau các collection thích hợp.
- **Allocation rate:** tốc độ tạo object, ví dụ MB/s hoặc GB/s.
- **Headroom:** chỗ để tiếp tục cấp phát trong khi GC reclaim; cần tính bursts, promotion, fragmentation và nội bộ collector.

Ví dụ minh họa:

```text
-Xmx = 4 GiB
  live set ổn định       ~2.5 GiB
  khoảng trống danh nghĩa ~1.5 GiB

-Xmx = 2.7 GiB
  live set ổn định       ~2.5 GiB
  khoảng trống danh nghĩa ~0.2 GiB
```

**Khoảng trống danh nghĩa không phải toàn bộ headroom usable**. GC cần không gian riêng cho regions, evacuation, metadata và đối phó biến động allocation; không dùng phép trừ trên như công thức sizing cuối cùng.

### Vì sao giảm heap có thể làm tăng cả CPU và latency?

Khi heap nhỏ hơn:

- GC có thể chạy thường xuyên hơn;
- concurrent collector phải bắt đầu/hoàn tất chu kỳ nhanh hơn;
- CPU dành cho GC tăng, throughput application có thể giảm;
- nếu reclaim không theo kịp allocation, xuất hiện stalls, Full GC hoặc OOME;
- p99 request có thể xấu đi mặc dù RSS giảm.

Ngược lại, tăng heap có thể giảm áp lực GC/CPU và tail latency nhưng **tăng footprint/cost**. Điểm tối ưu là có đủ headroom với chi phí chấp nhận được, không phải “Xmx càng lớn càng tốt”.

## 8. Footprint: Xmx khác RSS và container limit

**`-Xmx` chỉ giới hạn Java heap.** Bộ nhớ process còn gồm:

- Metaspace và class metadata;
- JIT code cache;
- Java thread stacks, native stacks;
- Direct/off-heap buffers và JNI allocations;
- GC bookkeeping, remembered sets, runtime metadata;
- Vùng mapped memory, thư viện native và một số allocations khác.

Với container memory limit 3 GiB và `-Xmx3g`, JVM **có thể vượt limit** vì native memory chưa được tính. Kernel/cgroup OOM killer có thể kết thúc process trước khi Java tạo một `OutOfMemoryError` và không nhất thiết có heap dump.

| Metric | Đo cái gì? | Không nên hiểu |
| --- | --- | --- |
| Heap **used** | Dung lượng Java heap sử dụng tại thời điểm đo | Tổng footprint JVM |
| Heap **committed** | Heap memory VM đã commit | RSS chính xác |
| Heap **max** | Giới hạn Java heap | Container memory limit |
| Process **RSS** | Resident memory của process | Chỉ riêng Java heap |
| Container memory | Tiêu thụ ở cấp cgroup/container theo metric cụ thể | Luôn bằng process RSS |
| NMT summary | Các native/JVM categories do HotSpot theo dõi | Bao quát mọi allocations của thư viện bên ngoài |

### Xms = Xmx và AlwaysPreTouch

Ví dụ:

```bash
java -Xms2g -Xmx2g -XX:+AlwaysPreTouch -jar app.jar
```

Điều này có thể giúp giảm heap resizing/page faults trong giai đoạn xử lý tải và làm latency ổn định hơn ở **một số** workload. Đổi lại startup chậm hơn, heap được chạm sớm, RSS và chi phí memory ban đầu tăng. Không mặc định đây là lựa chọn tốt trong container có RAM hẹp hoặc workload scale-to-zero.

Một số low-latency collectors có thể **uncommit** heap chưa sử dụng để trả bộ nhớ cho OS. Hoạt động commit/uncommit cũng có chi phí và có thể ảnh hưởng latency. Nếu muốn footprint thấp, theo dõi RSS **trong cả giờ tải thấp lẫn peak**, không chỉ một snapshot sau startup.

## 9. CPU quota: concurrent work không miễn phí

Giả sử:

```text
Ứng dụng cần                 1.7 vCPU
GC concurrent cần             0.6 vCPU
Tổng nhu cầu                  2.3 vCPU
Container quota               2.0 vCPU
                          -------------
Thiếu ~0.3 vCPU, có thể bị throttling/queueing
```

Con số chỉ để hiểu khái niệm. Khi chạm CPU quota, GC threads và request threads có thể tranh nhau thời gian xử lý. **Tail latency do scheduling/queue có thể tăng dù STW pause gần như bằng 0.**

Vì thế không có recipe “set số concurrent GC threads thật cao để nhanh hơn” hoặc “giảm về 1 để tiết kiệm CPU”. Heuristics của VM thường là khởi đầu hợp lý; việc can thiệp `ConcGCThreads` cần số liệu về GC throughput, CPU quota và các failure modes.

Trong Kubernetes, cần quan sát **CPU throttling** (cgroup CPU stats, metrics exporter), không chỉ CPU usage trung bình. Một process dùng 1,9/2 vCPU trung bình có thể vẫn bị throttling do bursts.

## 10. Đo đúng: GC pause không phải p99 request

Giả sử GC log có:

```text
20 GC pauses, mỗi pause khoảng 50 ms
vs
1000 GC pauses, mỗi pause khoảng 1 ms
```

Tổng pause time có thể gần tương đương, nhưng phân phối request latency chịu ảnh hưởng khác nhau. Khi xem một recording:

1. **Count:** số pauses, bao nhiêu young/mixed/full collections.
2. **Pause distribution:** p50/p95/p99/max STW, không chỉ average.
3. **Application latency:** end-to-end p50/p95/p99 tại tải đã xác định.
4. **Throughput và CPU:** requests/s, CPU-seconds/request, thời gian GC concurrent.
5. **Memory:** heap used/committed, RSS peak và cgroup memory limit.
6. **Failure signals:** Full GC, evacuation failure, allocation stalls, OOM, throttling.

**Một GC tốt hơn về pause nhưng thua về request p99 không phải nghịch lý.** Nó có thể chiếm CPU, gây queueing hoặc workload đã bị một thành phần khác chi phối.

### Chú ý các pha GC lồng nhau

Một số JFR events ghi **toàn bộ GC cycle**, những events khác ghi **STW pause/subphase**. Không cộng bừa duration của mọi GC event để ra “total time JVM bị stop”; có thể double-count các khoảng lồng nhau hoặc cộng cả concurrent phases.

## 11. GC Unified Logging trong Java 11

HotSpot Java 11 đã dùng **Unified JVM Logging** với `-Xlog`. Đây là cú pháp vẫn áp dụng trong Java mới, tốt hơn việc khôi phục các GC logging flags Java 8 đã cũ.

### G1 với log ra file

```bash
java -Xms256m -Xmx1g -XX:+UseG1GC \
  '-Xlog:gc*,safepoint:file=gc-g1.log:time,uptime,level,tags' \
  -jar app.jar
```

Trong **Bash**, dấu quote giúp giữ nguyên `*`; file/log path phải writable. Đoạn lệnh là ví dụ khi có `app.jar` thật.

Muốn xem timing CPU/user/sys của GC:

```bash
java -Xms256m -Xmx1g -XX:+UseG1GC \
  '-Xlog:gc*,gc+cpu=info,safepoint:file=gc-g1-cpu.log:time,uptime,level,tags' \
  -jar app.jar
```

**Đọc log để nhận biết:**

| Mẫu | Ý nghĩa |
| --- | --- |
| `Using G1` / `Using ZGC` | GC được VM chọn thật sự |
| `Pause Young` | Young collection và thời lượng |
| `Pause Mixed` | G1 mixed collection |
| `Pause Full` | Full GC, thường cần điều tra nếu có latency spike |
| `Concurrent ...` | GC đang làm việc cùng application |
| `User=..., Sys=..., Real=...` | CPU/wall times được VM ghi cho phase thích hợp |
| `to-space exhausted` hoặc evacuation failure | Áp lực không gian/promotion |
| `Allocation Stall` | Collector concurrent có thể không kịp cấp chỗ, tùy GC |
| `Safepoint` | Dừng chung JVM, có thể không chỉ do GC |

Các GC không dùng cùng từ vựng log hoàn toàn. Không viết parser giả định cả G1/Parallel/ZGC/Shenandoah đều có dòng “Pause Mixed”. Phân tích đúng loại event/phase cho collector đang chạy.

### Đừng quên retention của log

Production chạy dài cần rotation/size limit cho GC logs. Với Unified Logging có thể cấu hình output options như `filecount`/`filesize`; cần bảo đảm disk quota và quy định bảo vệ thông tin chẩn đoán.

## 12. JFR: đối chiếu GC với CPU, thread và request

JDK 11 có Java Flight Recorder tích hợp. Khi cần bắt hiện tượng trên JVM đang chạy và có quyền attach:

```bash
jcmd 12345 JFR.start name=gc-diagnosis settings=profile duration=60s filename=/var/tmp/gc-diagnosis.jfr
jcmd 12345 JFR.check name=gc-diagnosis
```

Sau khi recording đủ thời lượng:

```bash
jfr summary /var/tmp/gc-diagnosis.jfr
jfr print --events jdk.GarbageCollection /var/tmp/gc-diagnosis.jfr
jfr print --events jdk.GCPhasePause /var/tmp/gc-diagnosis.jfr
```

**PID=12345 chỉ minh họa**, cần dùng PID thật. File nằm trong filesystem của JVM target. Event names/fields và khả năng phát sự kiện phụ thuộc JDK/collector/settings; vắng `jdk.GCPhasePause` không chứng minh không có pause. Dùng `JFR.check verbose=true` và metadata khi cần xác nhận cấu hình.

**Ý nghĩa:** nếu response p99 bị chậm nhưng JFR cho thấy GC pause nhỏ, đối chiếu CPU samples, thread blocking, disk I/O và workload, không tiếp tục chỉnh GC chỉ vì nhìn thấy chữ “garbage collection”.

## 13. Bài thực hành Java 11: cùng workload, khác GC

Chương trình sau cố tình tạo nhiều byte arrays để JVM phải dọn các objects chết nhanh. Một phần allocations được giữ trong ring buffer để có live set nhỏ. Nó đo throughput và phân phối thời gian từng operation bằng `System.nanoTime()`, đồng thời in GC MXBean metrics.

**Đây là workload học tập, không phải benchmark HTTP/production.** Nó không đo max GC pause trực tiếp, không warm up một cách nghiêm ngặt và kết quả phụ thuộc máy/JDK.

### Tệp `GcTradeoffLab.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Locale;

public final class GcTradeoffLab {
    private static volatile byte[][] retained;
    private static volatile long checksum;

    static double percentileMillis(long[] sorted, double p) {
        int index = (int)Math.ceil(sorted.length * p) - 1;
        index = Math.max(0, Math.min(index, sorted.length - 1));
        return sorted[index] / 1_000_000.0;
    }

    public static void main(String[] args) {
        int ops = args.length > 0
                ? Integer.parseInt(args[0]) : 20_000;
        int bytes = args.length > 1
                ? Integer.parseInt(args[1]) : 8192;

        if (ops < 1 || ops > 200_000
                || bytes < 128 || bytes > 1_048_576) {
            throw new IllegalArgumentException(
                    "ops 1..200000; bytes 128..1048576");
        }

        long[] times = new long[ops];
        byte[][] ring = new byte[256][];
        long sum = 0L;
        long began = System.nanoTime();

        for (int op = 0; op < ops; op++) {
            long start = System.nanoTime();

            for (int j = 0; j < 8; j++) {
                byte[] data = new byte[bytes];
                data[0] = (byte)(op + j);
                sum += data[0];

                if ((j & 1) == 0) {
                    ring[(op + j) & 255] = data;
                }
            }
            times[op] = System.nanoTime() - start;
        }

        long total = System.nanoTime() - began;
        retained = ring;
        checksum = sum;

        Arrays.sort(times);
        double seconds = total / 1_000_000_000.0;

        System.out.println("operations: " + ops);
        System.out.println("bytes/array: " + bytes);
        System.out.printf(Locale.ROOT,
                "requested payload MiB: %.1f%n",
                ops * 8.0 * bytes / (1024 * 1024));
        System.out.printf(Locale.ROOT,
                "throughput ops/sec: %.1f%n", ops / seconds);
        System.out.printf(Locale.ROOT, "p50 ms: %.3f%n",
                percentileMillis(times, 0.50));
        System.out.printf(Locale.ROOT, "p95 ms: %.3f%n",
                percentileMillis(times, 0.95));
        System.out.printf(Locale.ROOT, "p99 ms: %.3f%n",
                percentileMillis(times, 0.99));

        long gcCount = 0L;
        long gcTime = 0L;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (bean.getCollectionCount() >= 0) {
                gcCount += bean.getCollectionCount();
            }
            if (bean.getCollectionTime() >= 0) {
                gcTime += bean.getCollectionTime();
            }
        }
        System.out.println("reported GC count: " + gcCount);
        System.out.println("reported GC time ms: " + gcTime);
        System.out.println("checksum observed: " + checksum);
    }
}
```

```bash
javac --release 11 -encoding UTF-8 GcTradeoffLab.java
java -Xms128m -Xmx256m -XX:+UseG1GC GcTradeoffLab
```

Với giá trị mặc định, hai dòng đầu và tổng payload là:

```text
operations: 20000
bytes/array: 8192
requested payload MiB: 1250.0
```

Các dòng còn lại như `throughput ops/sec`, `p50/p95/p99`, GC count/time và checksum thay đổi theo dữ liệu/chạy, **không dùng số cố định để test performance**. `1250.0 MiB` là tổng **payload được yêu cầu** (20.000 × 8 × 8.192 byte), chưa tính headers/alignment; không có nghĩa heap cùng lúc dùng 1.250 MiB.

**Giới hạn phép đo:**

- `p99` ở đây là đuôi thời gian **operation trong ví dụ**, không phải end-to-end HTTP latency.
- `GarbageCollectorMXBean.getCollectionTime()` trả metric do collector hỗ trợ; không phải tự động là **tổng CPU GC** hoặc tổng STW pause chính xác khi collector có concurrent phases.
- JIT/safepoint/scheduler cũng có thể làm operations chậm, nên so với GC logs/JFR.
- Vòng lặp giữ một số arrays trong ring và một observable checksum; JIT vẫn có thể tối ưu theo version. Phép đo tốt hơn cần nhiều lần chạy và/hoặc JMH.

## 14. Chạy cùng chương trình với G1 và Parallel

Để xem đặc điểm hai collector có sẵn trên Java 11, dùng **cùng JDK và heap cap**:

```bash
javac --release 11 -encoding UTF-8 GcTradeoffLab.java

java -Xms128m -Xmx256m -XX:+UseG1GC \
  '-Xlog:gc*:file=g1.log:uptime,level,tags' \
  GcTradeoffLab 20000 8192

java -Xms128m -Xmx256m -XX:+UseParallelGC \
  '-Xlog:gc*:file=parallel.log:uptime,level,tags' \
  GcTradeoffLab 20000 8192
```

Các bước đánh giá:

1. Chạy ít nhất vài lượt để loại bớt noise do startup/JIT.
2. So p95/p99, throughput và số/tổng thời gian GC **trên cùng workload**.
3. Đọc logs để tìm pauses dài và failure modes.
4. Với service thật, đưa traffic hỗn hợp đủ dài, có warmup, so ở **cùng offered load**.
5. Dùng OS process CPU và RSS / container metrics vì Java MXBeans không đo trọn native footprint.
6. Đánh giá số đo lặp lại và uncertainty, đừng chọn GC theo một lượt tốt nhất.

**Một biến tại một thời điểm:** không so G1 trên JDK 11 với ZGC JDK 25 rồi cho rằng mọi khác biệt do collector. Khác JIT, class library, G1/ZGC implementation và heap ergonomics cũng có thể tác động.

## 15. Ví dụ Java 11: xem used/committed/max heap

`java.lang.management` có các API hiện hành giúp lấy snapshot heap/GC. Nó **không thay thế RSS hoặc cgroup metrics** nhưng cung cấp góc nhìn bên trong JVM.

### Tệp `GcMemoryView.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

public class GcMemoryView {
    static long mib(long bytes) {
        return bytes < 0 ? -1 : bytes / (1024L * 1024);
    }

    public static void main(String[] args) {
        MemoryMXBean mx = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = mx.getHeapMemoryUsage();
        MemoryUsage nonHeap = mx.getNonHeapMemoryUsage();

        System.out.println("heap used MiB: " + mib(heap.getUsed()));
        System.out.println("heap committed MiB: "
                + mib(heap.getCommitted()));
        System.out.println("heap max MiB: " + mib(heap.getMax()));
        System.out.println("nonheap used MiB: "
                + mib(nonHeap.getUsed()));

        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("GC name: " + gc.getName());
            System.out.println("GC count: " + gc.getCollectionCount());
            System.out.println("GC time ms: "
                    + gc.getCollectionTime());
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 GcMemoryView.java
java -Xmx256m -XX:+UseG1GC GcMemoryView
```

Output phụ thuộc JVM/heap ergonomics và máy đang chạy. `nonHeap used` chỉ là thông tin từ memory pools quản lý bởi JVM, **không** bao trọn direct buffers/native allocations. Một số GC beans báo `-1` nếu không hỗ trợ metric. Tránh hard-code tên collector trong parser nhiều JDK.

### Native Memory Tracking

Khi được phép khởi động với NMT:

```bash
java -XX:NativeMemoryTracking=summary -Xmx2g -jar app.jar
```

Lúc JVM đang chạy:

```bash
jcmd 12345 VM.native_memory summary
```

NMT có overhead và không nhất thiết thấy **mọi** native allocations do third-party code thực hiện; nó không thay thế OS RSS. `jcmd` phải dùng đúng PID/user/namespace và quyền attach.

## 16. Benchmark production: công bằng theo RAM và CPU

Khi thử thay collector, so ở **hai chế độ**:

1. **Same heap cap:** cùng `-Xmx` để biết collector nào dùng CPU/throughput/latency tốt hơn trong giới hạn heap ấy.
2. **Same memory budget:** cùng **peak RSS/container limit** để so chi phí vận hành thực, vì collectors có native metadata và committed memory khác nhau.

Ghi lại cả:

- JDK vendor, full version/update, architecture/OS, GC thực;
- CPU quota, core count, throttling, heap `-Xms/-Xmx`;
- live set và allocation rate, retained heap, old-gen pressure;
- p99 request, throughput, CPU-seconds/request;
- GC pause p95/p99/max, số Full GC/allocation stalls;
- RSS high-water mark và container memory headroom.

### Khi nào dùng G1?

Khi yêu cầu latency vừa phải, throughput quan trọng, GC mặc định đang đáp ứng SLO, hoặc cần vận hành ổn định trên nhiều JDK/vendor. Trước khi đổi collector, thử giảm allocation rate của code và heap sizing hợp lý.

### Khi nào thử ZGC/Shenandoah?

Khi tail GC pause **được chứng minh** gây lỗi SLO, runtime có support production và CPU/RAM còn dư, hoặc chi phí vi phạm deadline lớn hơn chi phí thêm cores/RAM. Đặt giới hạn CPU/memory từ trước và benchmark trong container thật.

### Khi nào thử Parallel?

Khi workload batch/streaming ưu tiên jobs/s, GC pauses dài hơn không phá deadline và CPU throughput là trọng tâm. Nếu API đồng bộ cần phản hồi nhanh, kiểm tra worst pauses rất kỹ.

### Khi nào tối ưu code trước khi đổi GC?

Khi allocation rate tăng bất thường do tạo nhiều objects tạm, retained heap lớn do cache không giới hạn hoặc memory leak, thiếu CPU vì locking/database hoặc request queues quá sâu. GC thay đổi **không** khắc phục tất cả nguyên nhân gốc này.

## 17. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| “GC pause = request latency” | Request còn I/O/locks/queueing | Đo end-to-end p99 |
| “ZGC không tốn CPU vì concurrent” | Concurrent work cạnh tranh CPU với app | Đo CPU-seconds và throttling |
| “Giảm MaxGCPauseMillis luôn làm nhanh hơn” | Có thể tăng GC frequency/overhead | Benchmark với G1 soft goal |
| “-Xmx bằng process RSS” | Heap chỉ là một phần memory | Theo dõi RSS/native memory |
| “Xms=Xmx luôn tốt nhất” | RAM/startup cost có thể tăng | Chỉ dùng khi có lợi về latency và đủ RAM |
| “Tăng heap không có đánh đổi” | Tăng footprint/cost | Tìm đủ headroom, không lãng phí |
| “G1 chỉ có STW” | G1 có concurrent phases | Phân biệt hai pha |
| “Max GC pause thấp là đủ đạt SLO” | CPU queue, DB, network còn ảnh hưởng | Đo p99 thật |
| “ZGC JDK11 experimental tương đương JDK25” | Đời collector/production support khác | Theo version đang dùng |
| “JDK24+ vẫn dùng non-generational ZGC” | Mode đó bị xóa | Dùng generational ZGC hiện hành |
| “Shenandoah ở mọi bản Java 11” | Vendor/backport khác nhau | Kiểm tra JVM target |
| “CMS là lựa chọn low pause hiện hành” | CMS đã bị xóa | Không dùng CMS/flags legacy |
| “Một lượt benchmark đủ chọn GC” | JIT, workload variation, scheduler | Nhiều runs, warmup, tải thực tế |
| “CollectionTime là toàn bộ CPU GC” | MXBean semantics khác theo collector | Kết hợp logs/JFR/OS |
| “Container OOMKilled = Java heap OOME” | RSS/cgroup còn native memory | So heap và RSS |
| “Ít GC = hiệu năng tốt hơn” | GC ít nhưng có thể pause rất dài | Xem distribution/throughput |
| “CPU idle trung bình là không throttling” | Có bursts và quota theo chu kỳ | Đọc CPU throttling metrics |

## 18. Quy trình ra quyết định theo SLO

**Bước 1 — Định nghĩa ràng buộc.** Ví dụ giả định:

```text
SLO p99 <= 80 ms tại 15.000 requests/s
CPU budget <= 4 vCPU
Peak RSS <= 3.0 GiB
Không có OOMKilled / Full GC kéo dài
```

Các giá trị chỉ để minh họa một quyết định nhiều mục tiêu.

**Bước 2 — Baseline.** Giữ workload ổn định, lấy GC logs, JFR, request latency histogram, CPU, RSS và cgroup metrics. Kiểm tra service bottleneck có thật sự là GC hay không.

**Bước 3 — Một thay đổi.** Ví dụ G1 pause target 200 → 100 ms hoặc heap cap 2 → 3 GiB. Nếu G1 vẫn làm mất SLO do pauses, thử ZGC/Shenandoah production khi có quyền và hỗ trợ. Đừng đổi GC + JDK + memory limit đồng thời.

**Bước 4 — Đo lặp lại.** Chạy nhiều lần đủ dài, traffic mix và concurrency đại diện. Ghi p50/p95/p99, throughput, CPU-seconds/request, max GC pause, RSS high-water mark và failure events. Có thể đặt điểm A/B/C trên một **Pareto frontier**: một candidate chỉ đáng loại nếu candidate khác không tệ hơn ở bất kỳ mục tiêu nào và tốt hơn ở ít nhất một mục tiêu.

**Bước 5 — Canary/rollback.** Thử ở một tỷ lệ instance, theo dõi SLO và memory/cpu trước khi rollout. Khi RSS sát limit hoặc throttling tăng mạnh, rollback ngay theo policy. Không áp toàn cụm mà chỉ dựa vào lab synthetic.

### Bảng chấm kết quả sau benchmark

| Tiêu chí | Baseline | Candidate | Pass? |
| --- | --- | --- | --- |
| p99 request dưới SLO | Đo thật | Đo thật | Có/không |
| Peak RSS trong limit | Đo thật | Đo thật | Có/không |
| CPU-seconds/request | Đo thật | Đo thật | Mức tăng chấp nhận? |
| Throughput tại tải mục tiêu | Đo thật | Đo thật | Đủ không? |
| GC pause max / p99 | Đo thật | Đo thật | Nguyên nhân tail giảm? |
| Full GC / allocation stalls | Đo thật | Đo thật | Không tăng? |
| Container throttling | Đo thật | Đo thật | Có kiểm soát? |

**Giảm p99 25% nhưng tăng RSS 70% và làm pod OOMKilled không phải cải thiện thành công.**

## 19. Tự kiểm tra

**1.** GC pause 1 ms có bảo đảm response p99 dưới 1 ms không?

**2.** Tại sao collector concurrent giảm STW nhưng có thể làm CPU usage tăng?

**3.** Live set 3 GiB và `-Xmx3g` có đủ cho ZGC không?

**4.** Vì sao `-Xmx2g` không bảo đảm RSS dưới 2 GiB?

**5.** Nếu giảm `-XX:MaxGCPauseMillis` từ 200 xuống 50, G1 có luôn đạt pause dưới 50 ms không?

**6.** Trên JDK 24+, có cần bật `ZGenerational` không?

**7.** Hai instances cùng code, một chạy trong container 1 vCPU, một có 8 cores. Có nên giả định kết quả benchmark GC giống nhau không?

**8.** Một batch job không có request SLO nhưng ưu tiên throughput. Có đáng thử Parallel GC không?

**9.** `GarbageCollectorMXBean.getCollectionTime()` có thể thay thế hoàn toàn CPU profiler và GC logs không?

**10.** Nếu p99 request xấu mà GC pause tốt, có nên tiếp tục giảm pause target vô hạn không?

**Đáp án:** (1) Không; còn nhiều thành phần khác. (2) GC threads/barriers cần CPU. (3) Không; cần headroom cho allocations/concurrent cycle. (4) Native/nonheap/GC metadata thêm vào. (5) Không; soft goal. (6) Không; non-generational đã bị loại và option cũ không còn dùng. (7) Không; CPU quota/throttling rất khác. (8) Có, vẫn là throughput collector còn được hỗ trợ. (9) Không; semantics theo JVM/collector, không phải toàn bộ CPU/STW. (10) Không; cần điều tra CPU, locks, queue, DB và network.

## 20. Checklist triển khai

- [ ] Xác định rõ thứ tự ưu tiên **latency, CPU, footprint** và các giới hạn.
- [ ] Có request p99/p99.9, không đánh đồng với GC pause.
- [ ] Biết JVM vendor/JDK update/collector thực đang chạy.
- [ ] Đo heap used/committed/max, live set và allocation rate.
- [ ] Đo RSS/container limit, CPU quota và throttling.
- [ ] Đọc GC logs/JFR, tìm Full GC, evacuation failures hoặc stalls.
- [ ] Không dùng CMS hay ZGC experimental flags của Java 11 như recipe hiện đại.
- [ ] Chỉ bật Shenandoah/ZGC khi JVM target thực sự hỗ trợ.
- [ ] G1 pause target là **mục tiêu**, không phải cam kết.
- [ ] So collector ở cùng tải, JDK và memory/cpu budget.
- [ ] Đo lặp lại, có warmup và kiểm tra hiệu quả kinh doanh.
- [ ] Có canary, rollback và monitoring liên tục sau đổi.

## Kết luận

**Không có GC low-latency “miễn phí”.** G1 thường là baseline hợp lý và cân bằng. ZGC/Shenandoah có thể giảm mạnh STW, nhưng cần CPU cho concurrent GC và heap headroom để xử lý allocations. Parallel GC có thể tốt hơn về throughput khi được phép pause dài. CPU quota và RSS của container có thể đảo ngược kết quả so với một máy phát triển rộng tài nguyên.

Bài toán đúng là **đạt SLO với chi phí CPU và memory có thể chấp nhận**, không phải chỉ giảm một con số GC pause. Hãy đo bằng GC logs/JFR và metrics ứng dụng, thay một yếu tố mỗi lần, thử trên JDK/vendor thực và dùng canary trước khi rollout.

## Tài liệu tham khảo chính thức

- [Java SE 11 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/11/gctuning/garbage-first-garbage-collector-tuning1.html).
- [Java SE 25 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html).
- [Java SE 25 — Available Collectors](https://docs.oracle.com/en/java/javase/25/gctuning/available-collectors.html).
- [Java SE 24 — The Z Garbage Collector (generational, heap headroom)](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html).
- [Java SE 11 — java command, Unified JVM Logging](https://docs.oracle.com/en/java/javase/11/tools/java.html).
- [JDK 11 Release Notes — JEP 333 ZGC experimental, để hiểu khác biệt phiên bản](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html).
- [JDK 15 Release Notes — JEP 377 ZGC production](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html).
- [Java SE 24 Migration Guide — loại non-generational ZGC](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html).
- [Inside Java — Generational ZGC, JEP 439](https://inside.java/2023/11/28/gen-zgc-explainer/).
- [Java SE 11 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html).
- [Java SE 11 — MemoryMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html).
- [Java SE 11 — jcmd](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html).
- [Java SE 11 — jfr](https://docs.oracle.com/en/java/javase/11/tools/jfr.html).
