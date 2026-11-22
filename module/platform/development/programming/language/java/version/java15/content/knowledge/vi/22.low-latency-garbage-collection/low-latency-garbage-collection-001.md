# GC độ trễ thấp: thời gian dừng, thông lượng và footprint trong Java 15+

## 1. Mục tiêu học tập và bối cảnh

Khi chọn Garbage Collector (GC) cho một dịch vụ Java, ba câu hỏi quan trọng có thể dẫn đến **ba lựa chọn khác nhau**:

1. **Thời gian dừng (pause time):** các application threads bị JVM tạm dừng vì GC bao lâu, đặc biệt ở đuôi phân phối như p95, p99, p99.9 và max?
2. **Thông lượng (throughput):** cùng phần cứng và tải, ứng dụng hoàn thành bao nhiêu request/công việc mỗi giây, và tài nguyên CPU còn lại cho nghiệp vụ?
3. **Footprint (dấu chân tài nguyên):** tiến trình chiếm bao nhiêu bộ nhớ/CPU, gồm heap, native memory, số luồng GC, dự phòng khi thu gom đồng thời và bộ nhớ thực tế được hệ điều hành/container tính?

**Không có collector tối ưu tuyệt đối trên cả ba trục.** GC có pause ngắn không tự động cho throughput cao nhất hoặc footprint nhỏ nhất. Ngược lại, collector cho throughput tốt có thể tạo các stop-the-world pauses dài hơn, không phù hợp với dịch vụ cần latency tail chặt.

Trong **Java 15**, G1 là lựa chọn cân bằng mặc định trong HotSpot phổ biến; **ZGC (JEP 377)** và **Shenandoah (JEP 379)** đã được chuyển thành tính năng production trên những JDK/build hỗ trợ. Nhưng công nghệ không đứng yên: **ZGC của Java 15 chưa phải Generational ZGC**, trong khi JDK 23 đã dùng chế độ generational mặc định và JDK 24 đã loại chế độ non-generational. Vì Special Note yêu cầu kiến thức **còn áp dụng hiện nay**, bài này dùng Java 15 làm mốc học nhưng **phân biệt rõ phiên bản**; không lấy các tùy chọn GC cũ đã bị loại để khuyến nghị trên JDK mới.

Sau bài học, bạn sẽ:
- Đọc đúng **GC pause duration**, tỷ lệ thời gian dừng, percentiles, end-to-end request latency và các điểm đo safepoint liên quan.
- Tính **throughput** bằng đơn vị công việc/giây và giải thích overhead CPU của concurrent GC.
- Đo **heap used/committed/max**, live set, native/off-heap, RSS/cgroup memory, thay vì coi `-Xmx` là tổng bộ nhớ tiến trình.
- Hiểu đánh đổi giữa **G1 / ZGC / Shenandoah / Parallel GC** theo mục tiêu, cấu hình, JDK và tải thực tế.
- Dùng `-Xlog`, Java Flight Recorder (JFR), `MemoryMXBean` và một chương trình biên dịch với `javac --release 15` để minh họa đo đạc.
- Lập kế hoạch thử nghiệm A/B có phương pháp, đánh giá SLO, chi phí tài nguyên và tránh kết luận từ benchmark giả.

## 2. Stop-the-world pause là gì?

GC thu hồi vùng nhớ Java heap không còn được sử dụng. Nhiều collector cần một số giai đoạn **stop-the-world (STW)**: các Java application threads (*mutator threads*) bị tạm ngừng để JVM thực hiện hoặc đồng bộ một bước thu gom. **Pause duration** là khoảng tạm ngừng ấy.

Ví dụ timeline:

```text
Thời gian --------------------------------------------->

Mutator  ======RUN====== [PAUSE 4 ms] ====RUN==== [PAUSE 1 ms] ===RUN===
GC                   concurrent work ----------- concurrent work

       |<---- ứng dụng và GC có thể cùng dùng CPU ----->|
```

**Concurrent GC** cố chuyển nhiều công việc sang lúc application threads đang chạy. Điều đó giúp giảm độ dài từng STW pause, nhưng vẫn dùng CPU và có thể cần bộ nhớ dự phòng khi ứng dụng tiếp tục cấp phát đối tượng. “Concurrent” **không có nghĩa hoàn toàn không bao giờ pause**.

Những điều cần phân biệt:
- **Một GC cycle** có thể gồm nhiều pause ngắn cùng thời gian xử lý đồng thời dài hơn. *Thời lượng cycle* không phải *pause duration*.
- **GC STW pause** không đồng nhất với **mọi latency spike của ứng dụng**: JIT compilation, khóa, I/O, CPU throttling, paging, OS scheduling, network và một số safepoint khác cũng gây chậm.
- **Một pause 2 ms** không bảo đảm HTTP request chỉ chậm thêm đúng 2 ms: xếp hàng và đồng bộ các thread có thể khuếch đại ảnh hưởng tại tầng dịch vụ.
- **G1 `-XX:MaxGCPauseMillis`** là *mục tiêu/heuristic*, **không phải hard guarantee**; ngay cả collector low-latency cũng không biến JVM thành hệ thống hard real-time.
- Nếu workload không cấp phát hoặc collector chưa chạy trong cửa sổ ngắn, “không thấy GC pause” **không có nghĩa** ứng dụng đã được chứng minh an toàn ở p99.99.

### Chỉ số nào nên báo cáo?

| Chỉ số | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| Pause count | Số sự kiện dừng được đo trong cửa sổ | Xác định mức độ thường xuyên |
| Pause p50 / p95 / p99 / p99.9 | Phân vị độ dài pause | Đọc tail behavior, tránh chỉ nhìn average |
| Pause max | Pause dài nhất trong khoảng đo | Hữu ích khi tìm outlier, phụ thuộc sample size |
| Total GC pause time | Tổng thời gian threads bị dừng do GC trong khoảng | Ước tính mức gián đoạn STW |
| GC pause fraction | Total paused time / wall-clock observation time | Chỉ số STW, **không phải toàn bộ overhead concurrent GC** |
| Application p99 response latency | Phân vị thời gian xử lý **end-to-end** của request | Chỉ số SLO người dùng, không thể thay bằng GC p99 |

Nếu thu số liệu từ nhiều luồng hoặc nhiều instance, ghi rõ **time window**, số mẫu, workload, cấu hình collector và cách tổng hợp; không lấy trung bình các p99 rời rạc rồi gọi là p99 toàn hệ thống.

## 3. Percentile, trung bình và vấn đề tail

Giả sử có **100 sự kiện pause tổng hợp**:
- 95 pause dài 1 ms;
- 4 pause dài 10 ms;
- 1 pause dài 100 ms.

Sắp xếp tăng dần rồi dùng **nearest-rank percentile**: vị trí `ceil(p × N / 100)`, bắt đầu đếm từ 1.

Kết quả:
- **p50 = 1 ms**;
- **p95 = 1 ms**;
- **p99 = 10 ms**;
- **max = 100 ms**;
- **mean = 2,35 ms**, vì `(95×1 + 4×10 + 100)/100 = 2,35`.

Chỉ nhìn mean 2,35 ms có thể che khuất một outlier 100 ms. Chỉ nhìn p99 10 ms cũng **không thấy** sự kiện hiếm nhất nếu số mẫu bằng 100. Khi SLO rất khắt khe, cần xem cả p99.9, max, histogram, mức tải và số mẫu đủ lớn.

Đồng thời lưu ý:
- **GC pause p99 không phải request latency p99**. Một request có thể chịu nhiều pause, hoặc không gặp GC mà vẫn chậm do database/CPU.
- Khi hệ thống ghi nhận **số request** cao hơn nhiều số pause, phân phối của hai loại đối tượng đo không cùng mẫu số. Không so trực tiếp hai p99 như thể chúng là một đại lượng.
- Công thức percentile có nhiều biến thể (nearest-rank, interpolation, histogram approximation). Ghi rõ phương pháp và công cụ; khi dùng histogram, kiểm tra độ chính xác ở tail.
- Dữ liệu không đủ mẫu có thể tạo p99/p99.9 rất nhiễu. So sánh qua nhiều lần chạy, không quyết định từ một vài pause.

## 4. Thông lượng: công việc hữu ích theo thời gian

**Application throughput** thường là `requests/s`, `transactions/s`, `messages/s` hoặc `operations/s`:

```text
Throughput = số đơn vị công việc hoàn thành / khoảng thời gian đo

Ví dụ 1000 request hoàn thành trong 5 s:
Throughput = 1000 / 5 = 200 request/s
```

Số request **bắt đầu** không giống số request **hoàn thành thành công**. Khi đánh giá hệ thống, báo số lỗi, timeout, retry và độ trễ cùng throughput; một hệ thống trả lỗi nhanh không phải hệ thống có throughput nghiệp vụ tốt.

Một số tài liệu còn dùng **mutator utilization** hoặc phần trăm thời gian không STW. Đối với một collector thu gom chủ yếu bằng STW, `T_mutator/(T_mutator + T_pause)` có thể minh họa tỷ lệ thời gian threads được chạy. Nhưng với **concurrent GC**, cách này **không đủ** để tính chi phí GC:
- GC chạy **song song** với ứng dụng, giành CPU cores, memory bandwidth, cache và có write/read barriers.
- Khi CPU có quota thấp hoặc bị throttling, GC background làm thời gian xử lý request tăng dù STW pause cực ngắn.
- Ngay cả khi tổng STW pause time gần 0, **requests/s vẫn có thể giảm** hoặc p99 end-to-end xấu đi.

Hãy đo throughput **ứng dụng thực**, CPU utilization, allocation rate và GC CPU/concurrent activity ở **cùng throughput tải, cùng phần cứng và điều kiện CPU**.

### Ví dụ về đánh đổi

| Cấu hình giả định | GC pause p99 | Throughput | Process peak RSS | Kết luận đúng |
| --- | ---: | ---: | ---: | --- |
| Cấu hình A | 3 ms | 8.000 req/s | 5,5 GiB | Ưu tiên GC pause thấp, tốn tài nguyên hơn |
| Cấu hình B | 25 ms | 10.000 req/s | 3,8 GiB | Ưu tiên throughput/footprint, pause cao hơn |

**Tất cả số liệu trong bảng này là giả định để giải thích**, không phải benchmark G1/ZGC hay cam kết của một JDK. Nếu SLO app yêu cầu p99 response dưới 100 ms và B vẫn đạt, B có thể tiết kiệm chi phí. Nếu dịch vụ real-time không chịu nổi pause 25 ms, A có thể đáng giá hơn. Quyết định dựa vào **SLO thực và budget**, không dựa tên collector.

## 5. Footprint: heap không phải toàn bộ bộ nhớ tiến trình

Các khái niệm thường bị gộp nhầm:

| Chỉ số | Diễn giải | Lưu ý |
| --- | --- | --- |
| **Live set** | Tổng đối tượng còn sống sau quá trình thu gom tương ứng | Phụ thuộc workload/retention; không đồng nghĩa heap used ở mọi thời điểm |
| **Heap used** | Dung lượng trong Java heap hiện có đối tượng được tính là đang sử dụng | Tăng/giảm theo allocation và GC; trước GC chứa garbage chưa thu hồi |
| **Heap committed** | Bộ nhớ JVM đã commit cho heap | Có thể cao hơn used; thường không vượt max |
| **Heap max** / `-Xmx` | Giới hạn tối đa cho **Java heap** | Không phải trần RSS/cgroup của **toàn JVM** |
| **Native/off-heap** | Direct buffers, thread stacks, metaspace, code cache, JNI/native allocations, GC metadata... | Không được bao hết bởi Java heap |
| **Process RSS** | Resident Set Size do OS báo cho process | Khác committed và khác address-space virtual size |
| **Container/cgroup memory** | Bộ nhớ hệ thống tính vào giới hạn container/pod | Có thể bao gồm page cache và các loại memory account theo cgroup; cần xem peak |

**Không suy:** `-Xmx4g` thì container limit 4 GiB là đủ. JVM còn có stacks, native memory, metaspace, code cache, direct memory, bộ nhớ GC, agent, JNI, libraries và hành vi commit/return-to-OS. Trong container, RSS/cgroup peak thực tế mới quyết định có bị OOM kill do vượt giới hạn hay không.

**Không suy từ `Runtime.totalMemory()` rằng đó là RSS.** `Runtime.totalMemory()` và `MemoryMXBean.getHeapMemoryUsage().getCommitted()` phản ánh heap memory view; không đo đầy đủ native. Các collector có cách quản lý reserve/commit/trả memory cho OS khác nhau, và address-space reservation lớn không nhất thiết đã là resident physical memory.

### Native Memory Tracking (NMT)

Trên HotSpot hỗ trợ, có thể bật ở startup:

```bash
java -XX:NativeMemoryTracking=summary -Xms128m -Xmx256m \
  -XX:+UseG1GC GcTradeoffDemo --load 60000
```

Nếu JVM còn chạy, dùng công cụ đi kèm JDK:

```bash
jcmd <pid> VM.native_memory summary
jcmd <pid> GC.heap_info
```

Các lệnh này mô tả **công cụ quản trị với PID thật**, không phải phần chương trình tự chạy trong một phiên shell; `<pid>` là chỗ thay bằng tiến trình Java đang chạy. Bật NMT cần cấu hình trước khi JVM chạy và có overhead theo mức tracing; NMT cũng không thay thế việc đọc **RSS/cgroup peak** ở OS. Trên Linux có thể lấy `/proc/<pid>/status` (`VmRSS`) và cgroup memory metrics theo môi trường; trên Windows dùng Process/Performance counters phù hợp.

### Footprint còn bao gồm CPU và năng lực dự phòng

Low-latency collectors thường chuyển công việc từ STW sang concurrent phases. Điều này có thể cần:
- **CPU headroom** để GC hoàn thành chu kỳ trong khi mutators tiếp tục cấp phát.
- **Heap headroom** chứa đối tượng sống và lượng object được tạo trong thời gian concurrent collection.
- Overhead của barriers/metadata cùng cách bố trí bộ nhớ.

Một collector có GC pause rất ngắn nhưng tốn nhiều CPU background vẫn có thể gây **allocation stalls** khi allocation rate vượt khả năng giải phóng bộ nhớ trong điều kiện CPU/heap chật.

## 6. Vì sao giảm pause có thể tăng chi phí?

Tưởng tượng ứng dụng có live set khoảng **1 GiB** và cấp phát thêm **200 MiB/giây**. Một GC cycle thực hiện phần lớn công việc đồng thời trong khoảng **2 giây**.

```text
Đối tượng sống                       ~ 1.000 MiB
Đối tượng mới tạo trong 2 giây       ~   400 MiB
                                     -------------
Cần chỗ cho hoạt động đồng thời      > 1.400 MiB
(chưa tính reserve, fragmentation, metadata và các khác biệt collector)
```

**Đây là ví dụ ước lượng tư duy, không phải công thức chính thức để tính `-Xmx`.** Trong thực tế một phần object được thu hồi trong quá trình chạy, concurrent phase length biến động, allocation rate có burst và từng collector quản lý generations/headroom khác nhau. Vì vậy, hãy dùng heap occupancy, allocation rate, GC cycle time và stalls **đo được** để chọn heap.

Nếu heap hoặc CPU quá nhỏ:
- Concurrent collection không hoàn tất kịp tốc độ cấp phát.
- Collector phải thay đổi chiến lược, tăng áp lực GC, gây **allocation stall** hoặc trong một số tình huống nghiêm trọng dẫn đến OOM.
- GC pause percentiles nhỏ **không đủ** để kết luận ứng dụng đáp ứng SLO.

Nếu heap rất lớn:
- Có thêm headroom và có thể giảm tần suất collection.
- Nhưng RSS/commit/cgroup peak có thể tăng; chi phí hạ tầng tăng.
- Một số thay đổi mức heap có thể ảnh hưởng đến locality, cache và những giai đoạn collection khác nhau.

**Không chọn heap “càng lớn càng tốt”** nếu bạn chưa đo chi phí bộ nhớ thực và giới hạn container. Cần tối ưu **latency + throughput + footprint + reliability** trong ngân sách.

## 7. G1, ZGC, Shenandoah và Parallel GC trong đúng bối cảnh phiên bản

| Collector | Mục tiêu chính | Điểm mạnh | Điều cần đo/đánh đổi |
| --- | --- | --- | --- |
| **G1** | Cân bằng pause/throughput với region-based collection | Lựa chọn mặc định HotSpot phổ biến; có pause target và nhiều heuristic | Vẫn có STW evacuation pauses; một số trường hợp Full GC hoặc humongous allocations làm tail xấu |
| **ZGC** | Pause rất thấp với phần lớn công việc concurrent | Phù hợp workload nhạy pause, heap lớn; độ dài pause ít phụ thuộc kích thước heap | Background GC CPU, heap headroom, stalls khi quá tải và footprint dưới cgroup |
| **Shenandoah** | Low-pause concurrent collection | Chuyển nhiều công việc khỏi STW; hữu ích khi bản phân phối hỗ trợ | CPU/barrier overhead, workload và chế độ collector cụ thể; không phải mọi JDK build đều có |
| **Parallel GC** | Throughput cao của batch jobs | Đơn giản hơn, có thể hiệu quả khi chịu được pauses | Các collection STW có thể dài hơn, không thích hợp mọi latency SLO |

**Điểm lịch sử có giá trị thực hành hiện nay:**
- **Java 15:** ZGC trở thành production (JEP 377); Shenandoah trở thành production (JEP 379). Đây là mốc xuất hiện trong module Java 15, **không có nghĩa thuật toán và tùy chọn vẫn y hệt ở mọi JDK sau này**.
- **JDK 21:** Generational ZGC được giới thiệu.
- **JDK 23:** Generational ZGC trở thành chế độ mặc định.
- **JDK 24+:** Non-generational ZGC đã bị loại; **không hướng dẫn bật các cờ non-generational legacy trên JDK hiện đại**. Dùng `-XX:+UseZGC` với tài liệu đúng phiên bản JDK.
- **G1** vẫn là collector mặc định trong hướng dẫn HotSpot phổ biến. Trên JVM khác hoặc bản build JDK đặc thù, hãy kiểm tra collector thực sự được hỗ trợ.
- **Shenandoah** là tùy chọn cần kiểm tra build/OS/platform. Không viết tài liệu giả định mọi JDK đều chấp nhận `-XX:+UseShenandoahGC`.

Chọn collector theo **SLO và kết quả thực nghiệm**:
- Nếu p99/p99.9 của service thật bị GC pauses chi phối, cân nhắc thử **ZGC/Shenandoah**.
- Nếu cần cân bằng throughput, tài nguyên và pause mục tiêu trong hàng chục/hàng trăm ms, bắt đầu với **G1**.
- Nếu batch offline ưu tiên tối đa số tác vụ hoàn thành và chấp nhận STW, thử **Parallel GC**.
- Nếu tail cao do DB, lock contention hoặc CPU quota, đổi collector có thể **không** giải quyết vấn đề.

### Đừng nhầm mục tiêu MaxGCPauseMillis với SLA

Với G1 có thể đặt:

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=100 \
  -Xms128m -Xmx256m GcTradeoffDemo --load 60000
```

Con số 100 ms là **hint/goal** để G1 điều chỉnh phạm vi công việc của pause, không phải hard upper bound. Mục tiêu rất thấp đôi khi khiến GC thu gom thường xuyên hơn, giảm throughput hoặc tăng overhead. Hãy thử với giá trị hợp lý và **đo lại**, thay vì áp dụng một con số đẹp cho mọi ứng dụng.

## 8. Thu thập GC pause thật bằng Unified Logging và JFR

### 8.1. Unified JVM logging

Trong HotSpot Java 15+:

```bash
java -XX:+UseG1GC -Xms128m -Xmx256m \
  '-Xlog:gc*,safepoint=info:file=gc-g1.log:uptime,level,tags' \
  GcTradeoffDemo --load 60000
```

Lệnh tạo log có GC phases và các sự kiện safepoint liên quan, ví dụ các dòng `Pause Young`, `Pause Full`, duration và heap before/after; mức độ chi tiết tùy collector/JDK. Lệnh trên đã được thử với G1 trên JDK hiện đại và file log được tạo. Trên Windows PowerShell, bạn cũng có thể dùng dấu nháy kép quanh toàn bộ giá trị `-Xlog:...`.

Để so sánh collector khác, thay đúng flag GC và **tên file log riêng**:

```bash
java -XX:+UseZGC -Xms128m -Xmx256m \
  '-Xlog:gc*,safepoint=info:file=gc-zgc.log:uptime,level,tags' \
  GcTradeoffDemo --load 60000

# Chỉ chạy nếu bản JDK/build thực sự hỗ trợ Shenandoah:
java -XX:+UseShenandoahGC -Xms128m -Xmx256m \
  '-Xlog:gc*,safepoint=info:file=gc-shenandoah.log:uptime,level,tags' \
  GcTradeoffDemo --load 60000
```

**Đây là lệnh quan sát**, không phải bộ benchmark công bằng chỉ bằng một lần chạy. Các tên phase/GC tags khác nhau giữa G1, ZGC, Shenandoah và phiên bản. Không parse cố định duy nhất chuỗi `Pause Young` rồi coi đó là toàn bộ GC pauses của mọi collector.

**Lưu ý vận hành:** `gc*` có thể tạo log lớn. Dùng file rotation/log retention phù hợp, đo overhead khi thu log, tránh ghi log chứa thông tin nhạy cảm và không cấu hình debug cực kỳ chi tiết liên tục mà chưa đánh giá chi phí.

### 8.2. Java Flight Recorder (JFR)

JFR là công cụ quan sát JVM còn được hỗ trợ trong các JDK hiện đại và Java 15. Có thể khởi động recording:

```bash
java -XX:+UseG1GC -Xms128m -Xmx256m \
  -XX:StartFlightRecording=filename=gc-g1.jfr,settings=profile,dumponexit=true \
  GcTradeoffDemo --load 60000

jfr print --events jdk.GCPhasePause,jdk.GarbageCollection gc-g1.jfr
```

Các event như `jdk.GCPhasePause` có `duration`, `gcId` và tên phase; `jdk.GarbageCollection` có thông tin về cycle. Dùng JFR hoặc công cụ phân tích tương thích với JDK thực tế để tính pause distribution và tương quan với application latency, CPU và allocations. **Không lấy toàn bộ duration của concurrent GC cycle làm pause duration**.

JFR có cấu hình sampling và overhead; so sánh các lần thử với **cùng cấu hình instrumentation**. Với phiên bản JDK mới, có thể có lệnh tóm tắt mới thuận tiện hơn; không đưa những tùy chọn chỉ xuất hiện từ JDK 25 vào lệnh tuyên bố tương thích Java 15.

### 8.3. Cái gì là bằng chứng về GC gây request chậm?

Một quy trình phân tích hợp lý:

1. Thu **request latency histogram/trace** và throughput theo timestamp.
2. Thu **GC pause events, safepoints, allocations, CPU usage và heap pressure** cùng khoảng thời gian.
3. Đối chiếu timestamp của request chậm với pause/safepoint và trạng thái scheduler/CPU throttling.
4. Nếu spike không trùng GC hoặc GC pause rất nhỏ, điều tra **I/O, lock contention, queuing, DB, JIT, paging, CPU** trước khi đổ lỗi cho collector.

Hai đường biểu đồ cùng tăng không tự chứng minh nhân quả. Chạy lại với thay đổi có kiểm soát rồi xem tail latency và error rate có cải thiện bền vững không.

## 9. Chương trình Java 15 có hai chế độ: phép tính xác định và workload đo đạc

Mục tiêu ví dụ là **phân biệt công thức đo** và **thí nghiệm thật**:
- `--math` tạo **100 pause samples giả lập** để giải thích nearest-rank percentile và thông lượng. Stdout **xác định**; đây không phải GC events do JVM tạo.
- `--load N` cấp phát các mảng byte vào một ring buffer, đo elapsed time của vòng lặp, percentile của **thời gian thao tác vòng lặp** và heap used/committed/max qua `MemoryMXBean`, cộng thông tin tên/count/time của `GarbageCollectorMXBean`. Đây là **workload để sinh GC/logs và học API**, **không phải benchmark đưa ra kết luận về GC pause hoặc hiệu năng production**.

Lưu đúng tên file **`GcTradeoffDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.Arrays;
import java.util.Locale;

public final class GcTradeoffDemo {
    private static volatile long sink;

    public static void main(String[] args) {
        if (args.length == 0 || "--math".equals(args[0])) {
            deterministicExample();
        } else if ("--load".equals(args[0])) {
            int operations = args.length >= 2
                    ? Integer.parseInt(args[1]) : 60000;
            if (operations < 1000 || operations > 1000000) {
                throw new IllegalArgumentException(
                        "operations must be 1000..1000000");
            }
            allocationExample(operations);
        } else {
            throw new IllegalArgumentException(
                    "Usage: GcTradeoffDemo [--math | --load N]");
        }
    }

    private static void deterministicExample() {
        long[] syntheticPauseMs = new long[100];
        Arrays.fill(syntheticPauseMs, 1);
        for (int i = 95; i < 99; i++) {
            syntheticPauseMs[i] = 10;
        }
        syntheticPauseMs[99] = 100;
        Arrays.sort(syntheticPauseMs);
        System.out.println("synthetic samples: " + syntheticPauseMs.length);
        System.out.println("p50 pause (ms): " + percentile(syntheticPauseMs, 50));
        System.out.println("p95 pause (ms): " + percentile(syntheticPauseMs, 95));
        System.out.println("p99 pause (ms): " + percentile(syntheticPauseMs, 99));
        System.out.println("max pause (ms): " + syntheticPauseMs[99]);
        System.out.printf(Locale.ROOT, "mean pause (ms): %.2f%n",
                Arrays.stream(syntheticPauseMs).average().orElse(0.0));
        System.out.println("1000 requests / 5 seconds: "
                + (1000 / 5) + " req/s");
    }

    private static void allocationExample(int operations) {
        final byte[][] ring = new byte[256][];
        final long[] operationNanos = new long[operations];
        final long start = System.nanoTime();
        for (int i = 0; i < operations; i++) {
            long startOperation = System.nanoTime();
            byte[] data = new byte[4096 + (i % 8) * 256];
            data[0] = (byte) i;
            ring[i % ring.length] = data;
            operationNanos[i] = System.nanoTime() - startOperation;
        }
        final long elapsed = System.nanoTime() - start;
        long checksum = 0L;
        for (byte[] value : ring) {
            if (value != null) {
                checksum += value[0];
            }
        }
        sink = checksum;

        Arrays.sort(operationNanos);
        MemoryUsage heap = ManagementFactory
                .getMemoryMXBean().getHeapMemoryUsage();
        System.out.println("operations: " + operations);
        System.out.printf(Locale.ROOT, "throughput (ops/s): %.1f%n",
                operations * 1_000_000_000.0 / elapsed);
        System.out.printf(Locale.ROOT, "loop p99 (us): %.1f%n",
                percentile(operationNanos, 99) / 1000.0);
        System.out.printf(Locale.ROOT,
                "heap used/committed/max (MiB): %.1f / %.1f / %.1f%n",
                mib(heap.getUsed()), mib(heap.getCommitted()),
                mib(heap.getMax()));
        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("collector: " + gc.getName()
                    + " count=" + gc.getCollectionCount()
                    + " timeMs=" + gc.getCollectionTime());
        }
        if (sink == Long.MIN_VALUE) {
            System.out.println("unexpected checksum");
        }
    }

    private static double mib(long bytes) {
        return bytes / (1024.0 * 1024.0);
    }

    private static long percentile(long[] sorted, int percent) {
        if (sorted.length == 0 || percent < 1 || percent > 100) {
            throw new IllegalArgumentException("invalid sample/percentile");
        }
        int rank = (int) Math.ceil(sorted.length * percent / 100.0);
        return sorted[rank - 1];
    }
}
```

### 9.1. Biên dịch và chạy chế độ toán học

```bash
javac --release 15 GcTradeoffDemo.java
java GcTradeoffDemo --math
```

**Stdout chính xác, đã biên dịch/chạy kiểm tra:**

```text
synthetic samples: 100
p50 pause (ms): 1
p95 pause (ms): 1
p99 pause (ms): 10
max pause (ms): 100
mean pause (ms): 2.35
1000 requests / 5 seconds: 200 req/s
```

Đây là **100 mẫu tổng hợp**, không phải thông số ZGC hoặc G1. Giá trị `mean=2.35` được tính từ đúng bộ dữ liệu mô phỏng.

### 9.2. Chạy chế độ cấp phát

```bash
java -XX:+UseG1GC -Xms128m -Xmx256m GcTradeoffDemo --load 60000
```

Stdout **phụ thuộc vào máy, JDK, CPU, heap và JIT**. Một lần chạy thực tế đã kiểm chứng với JDK hiện đại cho dạng output sau:

```text
operations: 60000
throughput (ops/s): 1792794.8
loop p99 (us): 2.9
heap used/committed/max (MiB): 45.1 / 130.0 / 256.0
collector: G1 Young Generation count=4 timeMs=3
collector: G1 Concurrent GC count=0 timeMs=0
collector: G1 Old Generation count=0 timeMs=0
```

**Đây là output một lần chạy cụ thể, không phải chuẩn phải khớp**: throughput, heap, tên/count/time của collector có thể khác rất nhiều giữa JDKs. Trên JDK hiện đại có thể xuất thêm các GC MXBeans; `getCollectionCount()` hoặc `getCollectionTime()` có thể trả `-1` nếu collector không cung cấp số liệu tương ứng. Với collector concurrent, các thống kê MXBean này **không nên diễn giải máy móc thành tổng STW pause duration**.

**Điều đặc biệt quan trọng:** `loop p99 (us)` đo thời gian các thao tác vòng lặp Java bằng `System.nanoTime()`, gồm overhead đo và ảnh hưởng môi trường. Nó **KHÔNG PHẢI GC pause p99**. Muốn đo GC pause p99 thật, dùng `-Xlog`/JFR và tổng hợp từ những sự kiện pause tương ứng.

### 9.3. Tại sao ví dụ không được dùng để xếp hạng collector?

Vòng lặp này ngắn, vừa chạy vừa JIT compile/warmup, chỉ giữ ring buffer nhỏ, không mô phỏng traffic, queueing, I/O hay live set của ứng dụng thật. Chạy một lần G1 rồi một lần ZGC trong vài chục mili giây có thể bị chi phối bởi startup, initialization, OS scheduling và instrumentation hơn là đặc tính dài hạn của collector.

Chương trình chỉ minh họa **cách đo** và tạo ít GC events cho việc học log. Nó không được định vị là JMH benchmark, load test sản xuất hoặc workload chuẩn. Các chỉ số có giá trị chọn GC cần lấy từ **ứng dụng/tải thực** hoặc một benchmark có thiết kế warmup, forks, repeated trials, resource limits và interval đủ dài.

## 10. Thiết kế thí nghiệm G1 / ZGC / Shenandoah có thể so sánh

Một so sánh GC có nghĩa phải giữ mọi điều kiện khác càng giống nhau càng tốt.

**Bước 1 — Xác định SLO và ngân sách.** Ví dụ: ứng dụng phải đạt p99 request ≤ 80 ms ở 3.000 req/s, error rate dưới ngưỡng và container peak ≤ 4 GiB với 2 CPU cores. **Đây là SLO minh họa**, không phải quy tắc chung.

**Bước 2 — Chọn workload đại diện.** Gồm request mix, tỉ lệ read/write, payload size, allocation rate, retained live set, burst, sự kiện cache/DB, số connection, warm vs cold cache. Tránh chỉ chọn một vòng lặp phân bổ bytes nhỏ.

**Bước 3 — Cố định môi trường.** Cùng JDK version/build/vendor, CPU quota, RAM/cgroup limit, heap `-Xms/-Xmx`, workload generator, số threads, runtime config và thời gian chạy. Nếu so Java 15 với Java 25, đó là thí nghiệm **JDK version + collector** chứ không chỉ collector.

**Bước 4 — Warmup và steady state.** Có giai đoạn JIT/class loading warmup đủ dài; đo tại steady state với interval rõ ràng, có load ramp-up và spike để quan sát tail và stalls.

**Bước 5 — Đo đủ ba trục:**

| Nhóm | Cần thu |
| --- | --- |
| Pause/latency | GC pause p50/p95/p99/p99.9/max; request p95/p99/p99.9, queue delay, safepoints |
| Throughput/CPU | Completed successful requests/s, GC CPU, app CPU, throttling, allocation MB/s, error rate |
| Footprint | Live set, heap used/committed/max, non-heap, native, process RSS, cgroup peak, allocation stalls |
| Stability | GC failure, Full GC, OOM/OOM kill, tail under spikes, warm/cold behavior, startup |
| Cost | CPU cores và memory limit phải đặt mua/đặt chỗ để đáp ứng SLO |

**Bước 6 — Lặp lại và báo phân phối.** Chạy nhiều trial độc lập, dùng các khoảng thời gian cố định, báo median/p95 của trial-level metrics và những lần có anomaly. Không chọn run đẹp nhất hoặc chỉ một phần biểu đồ.

**Bước 7 — Thử nghiệm theo thứ tự.** Bắt đầu với GC default và heap hợp lý; nếu không đạt SLO, xác định bottleneck (heap pressure, humongous objects, allocation hot spots, OS throttling, native memory). Đổi **một nhóm tham số mỗi lượt**, đo lại. Không bật hàng chục tùy chọn ít được hiểu chỉ vì đọc được trên forum.

**Bước 8 — Quyết định bằng Pareto frontier.** Một cấu hình được coi là tốt nếu không có cấu hình khác **vừa** thấp latency **vừa** cao throughput **vừa** thấp footprint hơn trong các điều kiện tương đương. Chọn điểm cân bằng theo SLO, độ an toàn và chi phí vận hành.

## 11. Tình huống giải quyết vấn đề

### 11.1. GC pause tốt nhưng API p99 vẫn xấu

**Triệu chứng:** `jdk.GCPhasePause` thường chỉ 1–2 ms; HTTP p99 là 700 ms.

**Đừng kết luận:** “ZGC không hiệu quả, hãy chuyển collector ngay.” Hãy kiểm tra request traces, thread dumps, CPU saturation, cgroup throttling, blocking I/O, DB query, lock contention, connection pool và queue lengths. Nếu request p99 không đồng bộ với pause timestamps, phần lớn độ trễ có thể không đến từ GC.

**Hành động:** so sánh load/RPS ở cùng mức lỗi và CPU. Giảm GC pause có thể có giá trị nhưng không giải quyết bottleneck chính.

### 11.2. Throughput cao nhưng GC pause thỉnh thoảng rất dài

**Triệu chứng:** batch xử lý được nhiều records/s nhưng có STW 0,5–2 giây.

**Câu hỏi:** có SLO latency từng request không, hay batch có thể chịu chậm theo từng đợt? Nếu là batch, throughput cao có thể quan trọng hơn pause ngắn. Nếu là dịch vụ tương tác, một vài pause dài có thể làm lỗi timeout và queue buildup.

**Hành động:** kiểm tra Full GC, heap pressure và allocation rate; thử G1/ZGC và GC logs với cùng dataset và workload, không tự áp `MaxGCPauseMillis` thấp như hard guarantee.

### 11.3. GC pause thấp nhưng container bị OOM kill

**Triệu chứng:** `-Xmx3g`, cgroup limit 3,5 GiB, GC logs có pause đẹp nhưng process bị kill.

**Nguyên nhân có thể:** heap committed + thread stacks + direct buffers + metaspace + code cache + GC/native allocations + môi trường container cùng vượt budget.

**Hành động:** đo process RSS/cgroup peak và NMT theo khả năng, điều chỉnh heap/native/container budget. Đừng chỉ nhìn heap used hoặc tăng `-Xmx` vì pause có vẻ nhỏ.

### 11.4. Concurrent GC không thu hồi kịp tốc độ cấp phát

**Triệu chứng:** allocation rate tăng vọt, GC CPU chạy liên tục, heap gần đầy, throughput giảm và xuất hiện allocation stalls.

**Hành động:** giới hạn allocation, giảm retained objects, bảo đảm CPU quota/headroom, tăng heap hợp lý trong memory budget, xem tuning guide đúng JDK/version. Nếu mỗi lần tăng heap lại làm RSS vượt giới hạn container, cần thay đổi workload/architecture chứ không chỉ chọn “GC mạnh hơn”.

### 11.5. Kết quả Java 15 và Java 25 không giống nhau

**Triệu chứng:** dùng cùng `-XX:+UseZGC`, nhưng GC logs và throughput khác rõ.

**Giải thích:** phiên bản collector đã thay đổi. Java 15 ZGC là non-generational, JDK 24+ chỉ còn Generational ZGC. So sánh này đồng thời đổi cả JDK, collector implementation, compiler, runtime và defaults; không thể gán toàn bộ biến động cho một flag.

## 12. Lỗi diễn giải và tuning thường gặp

1. **“Pause p99 = request latency p99.”** Sai: khác đại lượng và tập mẫu.
2. **“Tổng thời gian GC cycle chính là tổng thời gian ứng dụng bị dừng.”** Sai với concurrent collector; phải đo các pha STW thực.
3. **“GC pause nhỏ nhất thì GC tốt nhất.”** Không đủ: cần throughput, footprint, ổn định và chi phí.
4. **“GC count/time từ MXBean luôn là pause time chính xác.”** Không: thống kê có thể khác nghĩa giữa collectors, nhiều số liệu không được hỗ trợ hoặc bao gồm hoạt động khác.
5. **“Cùng `-Xmx` nghĩa là cùng footprint.”** Sai: heap committed, live set và native memory có thể khác.
6. **“Xmx bằng container limit là an toàn.”** Sai: còn native/off-heap, stacks, code cache, metadata và OS accounting.
7. **“Chỉ cần đặt `-XX:MaxGCPauseMillis=10` là mọi GC pause ≤ 10 ms.”** Sai: đây là mục tiêu gợi ý, không hard deadline.
8. **“Concurrent GC không dùng CPU khi app đang chạy.”** Sai: nó tranh CPU/memory bandwidth với app.
9. **“Một run ngắn với `System.nanoTime` đủ xếp hạng G1 và ZGC.”** Sai: cần warmup, repeated trials, representative workload.
10. **“Một p99 được tính từ rất ít GC events vẫn ổn định.”** Sai: tail percentiles cần đủ dữ liệu, đặc biệt p99.9.
11. **“Heap used lúc chưa GC bằng live set.”** Sai: có cả objects chưa được thu hồi.
12. **“ZGC Java 15 và ZGC JDK 25 giống hệt nhau.”** Sai: generational mode đã thay thế non-generational ở JDK 24.
13. **“Thấy VSZ rất lớn là JVM đã dùng hết RAM.”** Sai: virtual address reservation không đồng nghĩa RSS/physical resident.
14. **“GC logs đã đầy đủ mọi nguyên nhân latency.”** Sai: cần thêm request tracing, CPU, I/O, locks, JFR/safepoints.
15. **“Không cần nhìn throughput khi tuning low latency.”** Sai: CPU concurrent GC có thể làm nhiều requests bị queue.
16. **“Tăng heap luôn giảm chi phí.”** Không: có thể giảm GC pressure nhưng tăng footprint và tiền RAM; cần đo.
17. **“Kích thước heap giống nhau đảm bảo so sánh công bằng ở mọi nơi.”** Chưa đủ: live set, CPU quota, native allocations, JDK và collector mode phải cùng điều kiện.
18. **“Shenandoah luôn có mặt trong mọi JDK.”** Sai: kiểm tra build/OS và flag hỗ trợ.
19. **“Không cần đo trong spike load, chỉ cần steady state.”** Sai: SLO tail có thể bị phá ở điểm burst/CPU throttling.
20. **“Dùng `System.gc()` giữa các request để giữ latency thấp.”** Không nên. Forced full/explicit GC có thể tạo pause và méo workload; không dùng làm tuning định kỳ tùy tiện.

## 13. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** GC có 100 pauses: 95 × 1 ms, 4 × 10 ms, 1 × 100 ms. Tính p95, p99, max và mean bằng nearest-rank.

**Đáp án:** p95 = **1 ms**, p99 = **10 ms**, max = **100 ms**, mean = **2,35 ms**. p99 không thể hiện outlier lớn nhất khi N=100.

**Câu 2.** Hai collectors cho GC pause p99 lần lượt 2 ms và 20 ms, nhưng request p99 đều 500 ms. Có nên khẳng định collector 2 gây request chậm gấp 10 lần?

**Đáp án:** **Không**. GC pause và request latency là hai phân phối khác nhau. Phải đối chiếu traces, CPU, I/O và thành phần latency, cùng mức tải, trước khi kết luận nguyên nhân.

**Câu 3.** Service cần hoàn thành 3000 request/s. Cấu hình A có pause rất nhỏ nhưng chỉ làm được 2500 req/s; B pause lớn hơn nhưng 3500 req/s và vẫn đáp ứng request latency SLO. Chọn gì?

**Đáp án:** Nếu các điều kiện khác phù hợp và B vẫn đạt tail SLO/footprint, **B có thể tốt hơn**. Pause thấp không thay throughput requirement.

**Câu 4.** Đặt `-Xmx4g` trong container có giới hạn 4 GiB, JVM đã được bảo đảm không OOM kill chưa?

**Đáp án:** **Chưa**. Xmx chỉ giới hạn Java heap; native/off-heap, stacks, metaspace, code cache, GC metadata và cgroup accounting còn tiêu tốn bộ nhớ.

**Câu 5.** Collector có GC pause p99 0,5 ms nhưng cần concurrent GC CPU rất cao khi CPU quota chỉ 1 core. Có thể làm API chậm không?

**Đáp án:** **Có**. GC cạnh tranh CPU với ứng dụng, có thể tăng queueing, throughput giảm, hoặc allocation stalls; cần đo CPU, throttling và request p99.

**Câu 6.** Dùng `-XX:MaxGCPauseMillis=20` cho G1 có cam kết mọi pause dưới 20 ms không?

**Đáp án:** **Không**. Đây là mục tiêu heuristic, không phải upper bound thời gian thực cứng.

**Câu 7.** Biến `loop p99 (us)` trong demo đo gì?

**Đáp án:** Thời gian một vòng cấp phát/ghi ring được đo bằng `nanoTime()`, **không phải GC pause p99**. GC pause phải lấy từ JFR/GC logs.

**Câu 8.** Nếu thấy một GC cycle kéo dài 200 ms trên ZGC nhưng pause events chỉ vài ms, có nên báo pause = 200 ms?

**Đáp án:** **Không**. GC cycle có thể bao gồm concurrent phases trong khi app vẫn chạy; chỉ STW phase mới là pause.

**Câu 9.** Tại sao hai biểu đồ đều ghi “heap 2 GiB” nhưng RSS khác nhau?

**Đáp án:** Có thể là cùng `-Xmx` nhưng heap committed, native allocations, thread stacks, code cache, GC metadata, memory-mapping và OS accounting khác. Phải đo RSS/cgroup, không suy từ max heap.

**Câu 10.** Có thể dùng các thông số low-latency ZGC của Java 15 để suy trực tiếp hành vi của `-XX:+UseZGC` trên JDK 25?

**Đáp án:** **Không**. Java 15 dùng thiết kế non-generational, trong khi JDK 24+ chỉ còn Generational ZGC; cần tài liệu và benchmark đúng phiên bản.

**Câu 11.** Dịch vụ chỉ có một batch chạy ban đêm, không có user waiting. Vì sao Parallel GC vẫn đáng thử?

**Đáp án:** Nếu ưu tiên jobs/hour và chấp nhận pauses, Parallel GC có thể cho throughput/chi phí phù hợp; quyết định từ workload thực, không theo nhãn “low latency” của collector.

**Câu 12.** Cần điều chỉnh gì trước khi so sánh collectors?

**Đáp án:** Giữ cùng JDK/build, CPU/RAM quotas, heap settings, workload và live set, thời gian warmup/measurement, instrumentation; thu request latency, throughput, CPU, memory peak và GC pauses; chạy nhiều trial.

**Tiêu chí đạt:** Bạn giải thích được **pause time – throughput – footprint** là ba trục khác nhau, đo p99 đúng tập mẫu, không gọi benchmark vòng lặp là kết quả sản xuất, biết chọn lệnh quan sát GC/JFR và thiết kế so sánh collector có kiểm soát.

## 14. Tài liệu chính thức và hiện hành

- [JEP 377 – ZGC: A Scalable Low-Latency Garbage Collector (Production)](https://openjdk.org/jeps/377): mốc ZGC production từ Java 15.
- [JEP 379 – Shenandoah: A Low-Pause-Time Garbage Collector (Production)](https://openjdk.org/jeps/379): mốc production của Shenandoah trong Java 15.
- [JEP 439 – Generational ZGC](https://openjdk.org/jeps/439): thế hệ ZGC mới được giới thiệu sau Java 15.
- [JEP 474 – ZGC: Generational Mode by Default](https://openjdk.org/jeps/474): thay đổi mặc định ở JDK 23.
- [JEP 490 – ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490): loại bỏ chế độ ZGC cũ ở JDK 24.
- [Oracle JDK 25 – G1 Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): mục tiêu pause, throughput, overhead concurrent và collector mặc định.
- [Oracle JDK 25 – G1 Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): hướng dẫn đo GC logs và tinh chỉnh mục tiêu pause với rủi ro throughput.
- [Oracle JDK 25 – Z Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/z-garbage-collector.html): generational ZGC, heap headroom và cơ chế low-latency còn áp dụng.
- [Oracle JDK 25 – Parallel Collector](https://docs.oracle.com/en/java/javase/25/gctuning/parallel-collector1.html): collector thiên throughput và các mục tiêu heap/pause.
- [Oracle JDK 17 – Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html): `jdk.GCPhasePause`, tính total pauses và phân biệt GC cycle với pause.
- [Java SE 25 – GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): `getCollectionCount()`, `getCollectionTime()` và giá trị `-1` khi không hỗ trợ.
- [Java SE 25 – MemoryMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap management metrics.
- [Java SE 25 – MemoryUsage](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html): used/committed/max với các điều kiện áp dụng.
- [Java SE 25 – java launcher, `-Xlog` và JFR options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): lệnh JVM phù hợp với phiên bản.
- [OpenJDK – Unified JVM Logging (JEP 158)](https://openjdk.org/jeps/158): cơ chế log tags/levels/output decorators.
- [OpenJDK – Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): theo dõi native memory của HotSpot theo cấu hình và chi phí công cụ.

**Ghi nhớ:** **GC pause thấp** là một mục tiêu quan trọng, nhưng **không đồng nghĩa request nhanh, throughput cao hoặc RAM ít**. Để chọn/tune GC, phải đo đồng thời **pause percentiles + application throughput/latency + heap/native/RSS footprint**, trong cùng workload, CPU và JDK version; chỉ quyết định sau khi kiểm chứng SLO và tài nguyên thực.