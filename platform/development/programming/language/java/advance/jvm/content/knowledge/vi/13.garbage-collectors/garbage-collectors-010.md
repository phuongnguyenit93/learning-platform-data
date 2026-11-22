# Mục tiêu GC pause time là mục tiêu tối ưu, không phải cam kết thời gian thực

`-XX:MaxGCPauseMillis=50` có nghĩa **JVM được yêu cầu cố gắng điều chỉnh bộ thu gom rác để các khoảng dừng phù hợp với mục tiêu 50 ms**. Nó **không** có nghĩa “mọi lần GC chắc chắn ngắn hơn hoặc bằng 50 ms”, càng không có nghĩa “mọi request Java trả lời trong 50 ms”. Đây là ranh giới quan trọng giữa **tối ưu GC theo thống kê/heuristics** với **bảo đảm thời gian thực (hard real-time deadline)**.

Theo tài liệu **Oracle Java SE 17 – Ergonomics**, `-XX:MaxGCPauseMillis=<n>` là một **hint**: GC điều chỉnh heap, generation sizes hoặc những tham số liên quan để *cố gắng* giữ các khoảng dừng ngắn hơn mục tiêu; **một số trường hợp không thể đạt được**. Với G1 Java 17, mục tiêu GC pause mặc định là **200 ms** trong cấu hình được tài liệu mô tả. Mặc định này **không phải SLA** và hoàn toàn không đảm bảo G1 sẽ không có pause trên 200 ms.

Bài thuộc nhóm **Các bộ thu gom** trong JVM, tập trung giải thích chính xác semantics của pause-time goal, cách GC quyết định lượng việc cần làm trong một pause, sự đánh đổi giữa **latency – throughput – heap footprint**, nguyên nhân vượt mục tiêu, cách dùng **GC logs/JFR/safepoint logs** và quy trình đánh giá SLA dựa trên số liệu thực. Các ví dụ **Java 17+** có stdout xác định ở phần nghiệp vụ, còn các giá trị GC time **được ghi nhận thay vì bịa số cụ thể**.

## 1. Pause time là gì? Không phải toàn bộ độ trễ ứng dụng

**GC pause time** là khoảng thời gian application threads bị dừng hoặc không được tiếp tục công việc bình thường do một giai đoạn thu gom cần stop-the-world (STW). Một collector có thể có nhiều dạng công việc:

- **Stop-the-world pause:** mutator threads tạm dừng trong khi GC thực hiện giai đoạn cần tính nhất quán.
- **Concurrent GC work:** một số GC threads làm việc trong khi mutators vẫn chạy, nhưng cùng tranh CPU/memory bandwidth.
- **Parallel GC work:** nhiều worker threads thực hiện công việc GC đồng thời; nếu đây là một pha STW thì application vẫn bị pause.
- **Non-GC safepoint:** JVM cũng có các hoạt động nội bộ cần safepoint hoặc thread handshakes; thời gian dừng này không nhất thiết được tính giống một GC pause trong log.

**Application latency** hoặc **request response time** là thời gian giữa sự kiện đầu vào và kết quả tới caller. Nó có thể bao gồm thời gian xếp hàng, network, thread scheduling, lock contention, I/O, JIT/class loading, CPU processing và ảnh hưởng của GC.

```text
Một request đơn lẻ (minh họa)
request arrived ──────────────────────────────────────────► response sent

   queue      business code       GC pause      business code   network
   ────┬──────────┬───────────────┬──────────┬───────────────┬──────
       │          │               │          │               │
       └──────────┴───────────────┴──────────┴───────────────┘
                      end-to-end latency

GC pause target = mục tiêu một loại khoảng dừng của JVM.
SLA request     = yêu cầu đo trên TOÀN bộ đường đi của request.
```

Không phải mọi GC activity đều làm toàn bộ request pause trực tiếp. Concurrent GC có thể làm giảm CPU headroom gây slowdown gián tiếp; các thread không đang xử lý request trong lúc GC pause cũng không nhất thiết có một request latency spike tương ứng. Nhưng với service đang phục vụ, một STW pause đủ dài có thể kéo nhiều requests vượt tail-latency budget.

### 1.1. Các chỉ số khác nhau không được dùng thay nhau

| Chỉ số | Đo cái gì? | Không đại diện cho |
| --- | --- | --- |
| GC pause duration | Một sự kiện JVM ngừng mutators để làm GC | Toàn bộ request response time |
| Maximum GC pause | Pause dài nhất trong cửa sổ quan sát | Bảo đảm pause tương lai không cao hơn |
| GC pause p95/p99 | Phân vị các pause events đã đo | Request p95/p99 |
| Total GC pause time | Tổng thời lượng nhiều pause trong cửa sổ | Toàn bộ CPU time của GC workers |
| GC overhead | Tỷ lệ thời gian dùng cho GC theo phép đo/tài liệu | Mọi chi phí CPU ứng dụng và background GC |
| Application p99 latency | Khoảng response time tại phân vị 99% requests | Chỉ riêng GC time |
| Deadline miss rate | Tỷ lệ yêu cầu không đạt deadline | Không tự chỉ ra nguyên nhân là GC |
| Throughput | Work hoàn thành trên một đơn vị thời gian | Bảo đảm response time từng request |

Một batch job có thể chấp nhận pause 500 ms nếu tổng thời gian xử lý thấp; một endpoint với deadline 100 ms có thể không chấp nhận ngay cả một số ít pauses như thế.

## 2. Pause-time goal là mục tiêu mềm (soft goal)

Trong Java 17 HotSpot:

```bash
-XX:MaxGCPauseMillis=50
```

có nghĩa “đề nghị GC cố gắng đạt pause tối đa khoảng 50 milliseconds theo chính sách/hành vi collector”:

- **50** là **milliseconds**, không phải microseconds, số thread, số lần GC hay phần trăm.
- JVM dùng **thống kê từ những collections trước** và heuristics của collector để lựa chọn một số tham số/khối lượng công việc.
- GC có thể tự điều chỉnh kích thước young generation, tập regions xử lý trong pause và các quyết định thích hợp với collector.
- Mục tiêu không buộc GC phải ngừng công việc giữa chừng một cách mất an toàn khi đồng hồ chạm 50 ms.
- Một pause có thể **ngắn hơn, bằng hoặc dài hơn** mục tiêu; runtime vẫn hợp lệ nếu vượt.
- Không có API chuẩn Java nào biến cờ này thành **hard real-time scheduling guarantee**.

Oracle Java 17 mô tả mục tiêu pause của HotSpot GC theo cách dùng average/variance với trọng số để theo dõi khả năng đạt mục tiêu. Đây là một **quyết định điều chỉnh dựa trên lịch sử và dự đoán**, không phải thuật toán tiên tri biết trước lượng object sống, graph edges, CPU scheduler delay hay thời gian I/O.

### 2.1. “Max” trong tên cờ không phải rào chắn cứng

Một số người đọc tên `MaxGCPauseMillis` rồi suy luận:

```text
Đặt -XX:MaxGCPauseMillis=20
⇒ JVM không bao giờ dừng ứng dụng quá 20ms
⇒ request không bao giờ vượt 20ms
```

**Cả hai phép suy luận đều sai.** Trong ngữ cảnh tuning, `Max` là tên cờ xác định **giá trị mục tiêu mong muốn**. Nếu GC cần xử lý một pha không thể tạm dừng/chia nhỏ hơn mà không vi phạm tính đúng đắn, hoặc các điều kiện thực tế khác khiến thời gian vượt dự đoán, nó **có thể vượt**.

“Đạt mục tiêu với xác suất cao” trong một workload không phải “đạt tuyệt đối với mọi sự kiện” và không phải chứng nhận hệ thống có tính hard real-time.

### 2.2. Mục tiêu 50 ms nhưng một lần GC 120 ms — có phải JVM hỏng?

**Không nhất thiết.** Ví dụ:

```text
GC(10) Pause Young ... 21.8ms
GC(11) Pause Young ... 33.5ms
GC(12) Pause Young ... 120.4ms  ← vượt mục tiêu 50ms
GC(13) Pause Young ... 27.1ms
```

Đây là **số liệu giả định để giải thích**, không phải output thực từ một chương trình được chạy ở bài này. Pause 120.4 ms có thể phản ánh live set nhiều hơn dự đoán, CPU starvation, reference processing, remembered-set work hoặc yếu tố khác. Muốn kết luận cần xem **log chi tiết của cùng GC id**, CPU/memory resource contention và collector-specific phase data.

Không có quy tắc “một lần vượt nghĩa flag không được áp dụng” hoặc “cứ tăng GC worker threads thì chắc chắn sửa được”.

## 3. HotSpot G1 trong Java 17 điều chỉnh pause bằng cơ chế nào?

**G1 (Garbage-First)** chia heap thành nhiều **regions**, và young generation là tập Eden/Survivor regions có thể thay đổi kích thước. Thay vì mỗi lần thu gom toàn bộ Old, nó thường thực hiện:

- **Young-only evacuation pauses** để thu gom Eden/Survivor.
- **Concurrent marking** để ước lượng liveness của các old regions (có các điểm dừng phù hợp trong chu kỳ).
- **Mixed GC pauses** gồm young + một tập old regions được chọn sau khi marking.
- **Full GC** hoặc những đường xử lý đặc biệt khi không còn đủ tiến triển/khả năng cấp phát thông thường.

G1 dùng dự đoán chi phí và **lựa chọn collection set (CSet)** để kiểm soát lượng công việc dự kiến xử lý trong một pause; **young region sizing** là một trong những phương tiện chính.

```text
Inputs quan sát từ collections trước:
  object survival rates
  lượng live bytes phải evacuate/copy
  remembered-set scanning work
  region/cset costs
  CPU workers / heap headroom
                 │
                 ▼
        G1 pause prediction
                 │
                 ▼
   Điều chỉnh young Eden region count
   Chọn candidate old regions trong mixed phase
                 │
                 ▼
   GC pause thực tế (STW) ──► log duration
                 │
                 └── feedback cho decisions kế tiếp
```

**Đây là mô hình heuristics**. Collector không biết chắc tương lai: allocation burst, sudden large live set, concurrent workloads và system pressure có thể khiến dự đoán sai.

### 3.1. Vì sao G1 default 200 ms không phải “mọi pause 200 ms”?

Theo Oracle Java 17 G1 GC Guide, `-XX:MaxGCPauseMillis=200` là **ergonomic default pause-time goal**. Đó là giá trị input để G1 điều chỉnh quyết định, chứ không phải một timer tự hủy collection sau 200 ms.

Một JVM dùng G1 mặc định có thể:

- Thường quan sát pauses dưới 200 ms trong workload thuận lợi.
- Thỉnh thoảng thấy các outliers lớn hơn vì nhiều lý do.
- Gặp một Full GC hoặc một tình huống evacuation pressure khác với dự đoán young evacuation thông thường.
- Có ứng dụng p99 latency tệ dù những GC pauses đo được đều dưới 200 ms, vì request bottleneck nằm ở nơi khác.

**Khi lập SLA, phải lấy measured pause distribution trên môi trường mục tiêu**, không lấy default GC flag làm một cam kết sản phẩm.

### 3.2. Vai trò của young generation sizing

Young generation lớn:

- Có thể giảm tần suất Young GC vì nhiều không gian cấp phát hơn trước khi cần collect.
- Có thể khiến mỗi lần thu gom cần xét/copy nhiều live objects hơn, nên pause tăng.
- Có thể cải thiện throughput tổng nếu phần lớn objects chết trẻ.

Young generation nhỏ:

- Có thể giảm lượng work của một pause.
- Nhưng có thể làm GC xảy ra thường xuyên hơn, tổng GC overhead tăng.
- Có thể tăng promotion pressure nếu survivor sizing không phù hợp.

G1 dùng adaptive young generation sizing để cân bằng chúng theo mục tiêu pause. Vì vậy tài liệu Oracle **khuyến cáo không ép cố định young size bằng `-Xmn`, `-XX:NewRatio` hoặc các cờ tương tự** khi đang trông cậy G1 tự đạt pause-time target: việc khóa young size có thể làm hỏng một công cụ điều chỉnh quan trọng của G1.

### 3.3. Mixed GC có thể vượt dự đoán do work không đồng đều

Độ khó của từng region không bằng nhau: cùng một lượng bytes chứa objects nhưng số references và remembered-set scanning costs khác nhau. Cũng không phải tất cả các old regions đều có cùng lượng live data. G1 chọn regions để tối đa hóa hiệu quả reclaim trong pause dự kiến, nhưng **không thể bảo đảm chi phí thực tế đúng mô hình**.

Nếu một application có object graph liên kết phức tạp, nhiều cross-region pointers hoặc thay đổi liveness bất ngờ, pause có thể dài hơn kỳ vọng. Phải đọc phases/metrics thực tế, không đoán đơn thuần từ tổng heap used.

### 3.4. Full GC có bị giới hạn tuyệt đối bởi `MaxGCPauseMillis`?

**Không.** `MaxGCPauseMillis` là mục tiêu tuning được áp dụng theo policy. Full GC có thể cần công việc trên phạm vi rộng hơn những CSet young/mixed dự báo thường ngày, có thể gây **pause dài hơn nhiều** trong điều kiện heap pressure/failure.

Không có “GC timeout” trong Java specification cho phép JVM bảo toàn object graph bằng cách tự ý ngưng collection nửa chừng và trả control an toàn nếu chưa hoàn tất công việc bắt buộc.

## 4. So sánh pause goal với collector khác

| Collector trên HotSpot Java 17 | Thiết kế cơ bản | Tác động của pause goal / cần chú ý |
| --- | --- | --- |
| **Serial GC** | Thu gom chủ yếu với một worker trong STW | Khó xử lý heap lớn dưới một pause rất nhỏ; không phải real-time |
| **Parallel GC** | STW young/old collection nhưng nhiều GC workers | Có pause/throughput ergonomics; ưu tiên throughput và không bảo đảm deadline |
| **G1 GC** | Region-based, young/mixed evacuation STW + concurrent marking | Cố điều chỉnh CSet/young size để đạt pause goal với xác suất cao; không hard bound |
| **ZGC** (JDK 17) | Phần lớn heavy GC work concurrent với mutators | Thiết kế low-pause, nhưng không phải hợp đồng hard-real-time toàn bộ application |
| **Shenandoah** (nếu có trong build) | Concurrent evacuation và GC phases phù hợp | Low-pause định hướng; availability/vendor options khác nhau, không hứa hard deadline |

Đừng suy rằng collector có pause thấp hơn **luôn** có throughput cao hơn. Collector thiên về low latency có thể phải dành thêm CPU hoặc memory headroom cho concurrent work. Mục tiêu kinh doanh quyết định trade-off.

### 4.1. ZGC cũng không biến Java thành hệ hard real-time

ZGC được thiết kế để các pause STW rất ngắn và phần lớn expensive work chạy concurrent. Nhưng **request deadline** vẫn có thể bị ảnh hưởng bởi:

- Linux/Windows scheduling và CPU starvation.
- Lock contention, thread pools và queue buildup.
- Network/database/remote service.
- Page faults, I/O hoặc memory pressure.
- JIT compilation/class loading và những VM activities khác.
- Concurrent GC CPU cost hoặc allocation stalls trong các điều kiện thiếu headroom.

Ngay cả một collector thường có pauses vài milliseconds cũng **không đủ** để đảm bảo một hệ thống Java hard real-time nếu toàn bộ OS, scheduling, libraries và application không cung cấp end-to-end guarantees tương ứng.

**Lưu ý phiên bản:** Ở Java 17, không áp đặt mô hình generational ZGC của các JDK mới lên ZGC 17. Bài tập trung ý nghĩa pause goal và low-latency định hướng, không đồng nhất architecture giữa releases.

### 4.2. Parallel GC: goal tồn tại nhưng thiết kế ưu tiên khác

Parallel GC (throughput collector) cũng hỗ trợ `-XX:MaxGCPauseMillis` theo HotSpot ergonomics. Trong đó các tiêu chí được xử lý theo thứ tự pause goal (nếu cấu hình), throughput goal và footprint phù hợp. Nhưng vì young/old collections chủ yếu STW, nếu ứng dụng cần p99 latency cực thấp thì chỉ đặt một con số goal nhỏ **không biến Parallel GC thành G1/ZGC**.

So sánh phải dựa trên workload, chứ không được coi `-XX:MaxGCPauseMillis=20` có ý nghĩa “độ trễ thực tế tương đương” khi chạy với mọi collector.

## 5. Pause-time goal và throughput goal thường đánh đổi nhau

**Throughput** theo thời gian là phần thời gian dành cho work ứng dụng so với tổng thời gian ứng dụng + GC trong cửa sổ quan sát:

```text
throughput = app_time / (app_time + gc_time)

Nếu app_time = 95 s, gc_time = 5 s:
  throughput = 95 / 100 = 95%

Nếu app_time = 99 s, gc_time = 1 s:
  throughput = 99 / 100 = 99%
```

**Đây là chỉ số tổng hợp**, không phải đo latency của từng request. Hai chương trình có throughput tương tự nhau vẫn có pause distributions rất khác nhau.

Giả sử G1 thu gom theo hai phương án minh họa:

| Chính sách | Số pause trong cửa sổ | Pause trung bình | Tổng pause time | Pause đơn lẻ |
| --- | ---: | ---: | ---: | --- |
| A, young lớn hơn | 5 | 100 ms | 500 ms | Có thể dài hơn |
| B, young nhỏ hơn | 20 | 35 ms | 700 ms | Ngắn hơn, nhưng nhiều hơn |

Các con số trên **chỉ là kịch bản minh họa để phân tích trade-off**, không phải output JVM thực tế. Cấu hình B giảm average pause, nhưng tổng thời gian STW cao hơn và có thể làm throughput thấp hơn.

### 5.1. Vì sao ép pause goal xuống 5 ms có thể phản tác dụng?

Một goal quá khắt khe có thể khiến JVM cố giảm young size, dẫn tới thu gom thường xuyên hơn. Chi phí tổng hợp gồm:

- Tần suất vào STW GC nhiều hơn.
- Bookkeeping và remembered-set work nhiều đợt.
- Promotion/survivor pressure tăng nếu live set và young sizing bất lợi.
- CPU overhead của GC tăng, ứng dụng mất throughput.
- Goal **vẫn có thể bị miss** nếu minimum unavoidable work vượt 5 ms.

Không có nguyên tắc “goal càng nhỏ thì ứng dụng càng nhanh”. Phải benchmark p95/p99 GC pauses **và** request latency, cùng requests/sec/jobs/sec, CPU và heap occupancy.

### 5.2. Tăng heap có luôn giảm pause?

Không. Heap lớn có thể giảm số lần thu gom và tăng khoảng thời gian giữa collections, nhưng cũng có thể thay đổi lượng live data, object retention, scanning/copying costs và các pha compaction. Với collector khác nhau, quan hệ không tuyến tính.

Tăng `-Xmx` có thể cung cấp headroom tránh GC pressure, **nhưng không bảo đảm pause ngắn hơn**. Ngược lại, heap quá nhỏ so với live set có thể gây repeated GC, Full GC hoặc `OutOfMemoryError` dù đặt mục tiêu pause rất thấp.

## 6. Hard real-time guarantee thực sự đòi hỏi gì?

Trong hệ **hard real-time**, một deadline là yêu cầu bắt buộc: không được miss trong phạm vi điều kiện vận hành đã định. Điều đó đòi hỏi **ràng buộc trên worst-case execution time**, scheduler, ưu tiên threads, I/O, memory allocation, lock contention, GC pauses và các nguồn jitter khác.

Một lựa chọn tối ưu JVM flag đơn lẻ không đáp ứng yêu cầu này.

| Loại mục tiêu | Ví dụ | Cần hiểu |
| --- | --- | --- |
| **Best-effort performance goal** | “Hãy cố giữ GC pause dưới 50 ms.” | VM cố đạt qua heuristics; không có hard guarantee |
| **Service SLO** | “Trong tháng, 99.9% requests dưới 100 ms.” | Chính sách mục tiêu đo từ metrics; có error budget, vẫn có ngoại lệ |
| **Hard real-time deadline** | “Mỗi chu kỳ điều khiển phải hoàn tất trước 10 ms trong mọi điều kiện cho phép.” | Cần worst-case proof/architecture, không thể suy từ GC heuristic |
| **Observed p99 GC pause** | “Trong một tuần, 99% GC events dưới 40 ms.” | Kết quả thống kê quá khứ; không bảo đảm cho tuần tới |
| **Client timeout** | “HTTP client bỏ cuộc sau 200 ms.” | Điều kiện xử lý phía client, không phải GC pause bound |

**Lưu ý:** SLO có thể rất chặt nhưng vẫn khác hard real-time guarantee. “99.99% dưới 20 ms” có **error budget** và không yêu cầu mọi sự kiện đều dưới 20 ms. Ngược lại hard deadline miss dù chỉ một lần có thể là failure nghiêm trọng trong hệ thống điều khiển.

### 6.1. Tại sao GC logs tốt không chứng minh real-time correctness?

Một chuỗi các GC pauses 5–15 ms không chứng minh:

- Scheduler sẽ luôn cấp CPU đúng hạn.
- Remote database không timeout.
- JVM không phải thực hiện Full GC ngoài dự kiến.
- Application thread không bị lock contention.
- Mọi future live sets đều giống tải kiểm thử.
- Không có sự cố memory, OS pause, container throttling hoặc disk hiccup.

GC logs cho **bằng chứng về GC behavior trong những lần chạy đã quan sát**. Nó không tự là chứng chỉ về worst-case application response time.

## 7. Ví dụ tính toán: vượt goal không nghĩa mọi pause đều xấu

Giả sử mục tiêu `-XX:MaxGCPauseMillis=50`. Quan sát 10 events (dữ liệu giả):

```text
GC pauses in milliseconds:
  6, 8, 10, 11, 12, 15, 18, 21, 29, 130
```

9/10 pauses dưới 50 ms, nhưng một event 130 ms vượt mục tiêu rất nhiều.

- **Average** = (6+8+10+11+12+15+18+21+29+130)/10 = **26.0 ms**.
- **Max** = **130 ms**.
- **90% các events** không vượt 50 ms theo tập dữ liệu này.
- Theo nearest-rank với n=10: **p90=29 ms**, **p99=130 ms**.
- **Misses** so với goal 50 ms là **1/10**.

Nếu chỉ báo average 26 ms, bạn **che giấu** event 130 ms. Nếu chỉ báo max 130 ms, bạn **chưa thấy phân phối** có thể chủ yếu ngắn. Phải xem cả count, distribution và bối cảnh GC phases.

### 7.1. Một phân vị từ sample nhỏ không ổn định

Với 10 mẫu, nearest-rank p99 trùng với giá trị cao nhất. Trong các hệ thống vận hành, cần cửa sổ đủ nhiều events và phương pháp tính nhất quán (nearest-rank, histogram buckets, HDR Histogram, v.v.). Không so sánh hai p99 nếu mỗi hệ thống dùng cửa sổ, công thức và rounding khác nhau.

### 7.2. Không dùng GC event p99 như request p99

Ví dụ 10 GC events có thể ảnh hưởng nhiều requests, hoặc xảy ra khi không có request. Request latency histogram còn tính scheduling, queue, database, network và application work. Nên duy trì **hai bộ metrics riêng**, rồi correlate timestamps và traces để tìm quan hệ.

## 8. Chương trình Java 17 chạy được: tạo allocation pressure và giữ kết quả ổn định

Chương trình sau cố tình tạo nhiều allocations, giữ một phần objects để mô phỏng live set và cho phép GC có cơ hội chạy. **Không có đoạn code Java nào ở đây hứa đo được chính xác bao nhiêu GC pause hoặc tổng thời gian pause**. Các số đó phải được ghi từ JVM thực tế.

Lưu file **`PauseGoalDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PauseGoalDemo {
    private static volatile List<byte[]> keepAlive;

    public static void main(String[] args) {
        long checksum = 0L;
        List<byte[]> retained = new ArrayList<>();

        for (int i = 0; i < 160_000; i++) {
            byte[] block = new byte[1024];
            block[0] = (byte) (i & 127);
            checksum += block[0] & 0xff;

            if (i % 8000 == 0) {
                retained.add(block);
            }
        }

        keepAlive = retained;
        System.out.println("iterations=160000");
        System.out.println("retained=" + retained.size());
        System.out.println("checksumPositive=" + (checksum > 0));
        System.out.println("done");
    }
}
```

Biên dịch trên JDK 17:

```bash
javac --release 17 PauseGoalDemo.java
```

Chạy với G1 (HotSpot Java 17):

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=50 PauseGoalDemo
```

**Stdout ứng dụng xác định, khi không bật GC logging và lệnh chạy hoàn tất:**

```text
iterations=160000
retained=20
checksumPositive=true
done
```

Giải thích:

1. Vòng lặp chạy 160.000 lần theo logic chương trình.
2. Điều kiện `i % 8000 == 0` đúng ở `i = 0, 8000, ..., 152000`, tạo **20** references được giữ.
3. Biểu thức checksum đọc dữ liệu từ từng array và tạo tổng dương; kết quả kiểm tra `true` độc lập với số lần GC.
4. Mảng `keepAlive` (ở đây thực tế là một `List<byte[]>`) giữ các retained blocks reachable sau vòng lặp.
5. JVM/JIT có thể tối ưu allocation hoặc chọn chiến lược GC theo tình trạng heap; **không suy số GC pauses từ 160.000 lần `new`**.
6. Program không in thời gian pause hay tuyên bố `MaxGCPauseMillis=50` luôn được thỏa mãn. Các số về collector phải đọc từ GC log/JFR.

**Chú ý shell:** Lệnh nhiều dòng dùng dấu `\` theo POSIX shell. Trong PowerShell/Windows Command Prompt nên viết thành một dòng hoặc dùng dấu nối dòng phù hợp với shell.

### 8.1. Chạy hai goals để quan sát trên workload giống nhau

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=20 -Xlog:gc=info PauseGoalDemo

java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=200 -Xlog:gc=info PauseGoalDemo
```

Ứng dụng phải giữ **cùng kết quả nghiệp vụ**, nhưng các GC event counts/pause durations có thể khác. Nếu lệnh hoàn thành quá nhanh hoặc JIT loại bỏ allocations, có thể không đủ số events để rút ra kết luận; hãy dùng workload thực hơn, chạy đủ lâu và thu thập nhiều mẫu.

Không diễn giải “run goal=20 ngắn hơn run goal=200” bằng một lần chạy đơn lẻ. JVM warmup/CPU scheduling/heap state đều gây biến thiên.

## 9. Java 17 ví dụ độc lập: phân vị và deadline miss trên mẫu giả định

Một công cụ hữu ích là tính trực tiếp p50/p90/p99/max trên **tập số liệu đã đo**, thay vì chỉ tin average. Ví dụ sau sử dụng số liệu **giả lập** và không đại diện cho GC thật.

Tạo file **`PauseStatisticsDemo.java`**:

```java
import java.util.Arrays;

public class PauseStatisticsDemo {
    static long nearestRank(long[] sorted, double quantile) {
        int rank = (int) Math.ceil(quantile * sorted.length);
        int index = Math.max(0, rank - 1);
        return sorted[index];
    }

    public static void main(String[] args) {
        long[] samples = {6, 8, 10, 11, 12, 15, 18, 21, 29, 130};
        Arrays.sort(samples);

        long sum = 0;
        int misses = 0;
        for (long pause : samples) {
            sum += pause;
            if (pause > 50) {
                misses++;
            }
        }

        System.out.println("count=" + samples.length);
        System.out.println("averageMs=" + (sum / (double) samples.length));
        System.out.println("p50Ms=" + nearestRank(samples, 0.50));
        System.out.println("p90Ms=" + nearestRank(samples, 0.90));
        System.out.println("p99Ms=" + nearestRank(samples, 0.99));
        System.out.println("maxMs=" + samples[samples.length - 1]);
        System.out.println("above50Ms=" + misses);
    }
}
```

Chạy:

```bash
javac --release 17 PauseStatisticsDemo.java
java PauseStatisticsDemo
```

**Stdout chính xác:**

```text
count=10
averageMs=26.0
p50Ms=12
p90Ms=29
p99Ms=130
maxMs=130
above50Ms=1
```

Ý nghĩa:

- Nearest-rank `p50` là phần tử thứ 5, **12 ms**.
- Nearest-rank `p90` là phần tử thứ 9, **29 ms**.
- Nearest-rank `p99` là phần tử thứ 10, **130 ms**.
- Trung bình **26 ms** nhưng tail có event 130 ms.
- `above50Ms=1` là **đếm sự kiện vượt goal giả định**, không phải chứng cứ Java 17 JVM đã vi phạm cờ trong lần chạy này.

Trong vận hành thực, cần thêm **time window, collector/event type, histogram resolution, sample size, max và SLO threshold** để đưa ra quyết định.

## 10. Thu thập GC pause thực tế bằng HotSpot Unified Logging

### 10.1. Ghi sự kiện GC vào file

Trên HotSpot Java 17:

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=50 \
  -Xlog:gc*,safepoint=info:file=gc-pause.log:time,uptime,level,tags \
  PauseGoalDemo
```

Log ghi vào file `gc-pause.log`. Nội dung thực tế tùy JVM build, GC activity, OS scheduling và workload. Không được tuyên bố pause time “đương nhiên 50 ms” mà chưa đọc file.

Một event có thể có dạng *minh họa*:

```text
[...][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) ... 13.7ms
[...][info][gc] GC(13) Pause Young (Normal) (G1 Evacuation Pause) ... 72.4ms
[...][info][safepoint] Safepoint "G1CollectForAllocation", ... Total: ... ns
```

Đây là **dòng mô phỏng cấu trúc để biết cần đọc gì**, không phải log thực của chương trình. Thời gian trên cùng dòng có thể có đơn vị `ms`, `us` hoặc `ns` tùy log field và cấu hình.

**Đừng trộn duration của `gc` event với “Total” của `safepoint` rồi cộng hai lần**: các measurements có thể bao trùm nhau hoặc đo những khoảng khác nhau của cùng một operation.

### 10.2. Đọc chính xác phạm vi timestamp

- `time` decorator cho wall-clock timestamp, thuận tiện correlate với app traces.
- `uptime` cho thời gian từ lúc JVM khởi động, hữu ích nếu wall-clock đổi.
- `level`/`tags` cho loại sự kiện, tránh nhập nhằng GC vs safepoint.
- `GC(id)` giúp nhóm log lines thuộc cùng GC cycle/pause.
- Dòng có chữ “Pause” thường là điểm tốt để bắt đầu, nhưng **một GC cycle có thể có nhiều events/phases**, không phải mỗi dòng text là một pause độc lập.

Khi tính phân vị pause, chọn rõ **events nào** được đưa vào mẫu (young, mixed, full, remark...). Một số dòng phase breakdown chỉ mô tả **thành phần của cùng một pause**; nếu cộng nhầm thành events độc lập sẽ đếm trùng.

### 10.3. Vì sao cần `safepoint` log?

Có lúc ứng dụng bị chậm do chờ thread tới safepoint, OS scheduling hoặc VM operation, không phải chỉ do phần GC work được ghi là pause. Safepoint logging giúp điều tra:

- Thời gian tới khi các threads có thể hợp tác cho safepoint.
- Thời gian của operation khi ở safepoint.
- Tổng thời gian theo cách JVM thống kê.
- Những VM operations không phải một garbage collection có thể tạo delay.

**Không dùng safepoint time thay thế tuyệt đối cho GC pause time**: chúng có phạm vi và measurement definitions khác nhau; cần correlate cùng timestamp/GC id hoặc operation name.

### 10.4. Chọn log level có đủ chi tiết nhưng không gây overhead quá lớn

```bash
# Ít thông tin, phù hợp quan sát ban đầu:
java -XX:+UseG1GC -Xlog:gc=info PauseGoalDemo

# Thêm breakdown chi tiết hơn cho thí nghiệm:
java -XX:+UseG1GC -Xlog:gc*,gc+phases=debug PauseGoalDemo

# Có thể ghi ra file với decorators:
java -XX:+UseG1GC \
  -Xlog:gc*,safepoint=info:file=gc-pause.log:time,uptime,level,tags \
  PauseGoalDemo
```

`debug/trace` có thể làm log nhiều và tăng CPU/I/O overhead, vì thế không bật vô hạn trên production. Hãy xem pause logs ở mức `info` trước, sau đó chỉ mở thêm tags/levels phù hợp với nguyên nhân nghi ngờ.

## 11. Dùng JFR để nhìn GC và request trong cùng timeline

**Java Flight Recorder (JFR)** có thể thu thập những events về GC, safepoints, allocation và application behavior tùy cấu hình. Đây là cách hữu ích để ghép:

- GC pause xảy ra khi nào và kéo dài bao lâu?
- Thread nào đang xử lý request vào đúng thời điểm đó?
- Có dấu hiệu lock contention, thread parking hoặc CPU bottleneck không?
- Có allocation hotspots hay pause outliers liên quan một phase cụ thể?

Lệnh startup trên JDK 17:

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -XX:MaxGCPauseMillis=50 \
  -XX:StartFlightRecording=filename=gc-pause.jfr,settings=profile \
  PauseGoalDemo
```

Ứng dụng vẫn in stdout Java bình thường; **file `gc-pause.jfr`** là recording cần phân tích riêng bằng JDK Mission Control/JFR tooling. Một chương trình rất ngắn có thể không cung cấp số sự kiện đủ lớn cho thống kê; hãy benchmark dịch vụ/workload có thời lượng đại diện.

**JFR cũng có overhead và policy sampling**. Số liệu trong recording cần được diễn giải theo event types/settings; không mặc định mọi hoạt động GC hoặc mọi request đều được ghi đầy đủ với precision vô hạn.

### 11.1. Không nhìn một GC log rồi suy request latency

Một GC event kéo dài 80 ms gần một request kéo dài 120 ms **không tự chứng minh** GC là nguyên nhân duy nhất. Cần correlate thời gian:

1. Request start/end timestamp hoặc trace spans.
2. GC pause start/end và loại event.
3. Độ trễ queue trước request handler.
4. CPU throttling/scheduling/lock contention và I/O.
5. Các requests khác cũng bị ảnh hưởng cùng thời điểm hay không.

Khi có overlap đúng và nhiều lần quan sát tương tự, giả thuyết GC ảnh hưởng request latency mạnh hơn. Nhưng phải kiểm soát những nguyên nhân khác trước khi “chữa bằng GC flag”.

## 12. Tại sao GC pause có thể vượt mục tiêu trong thực tế?

### 12.1. Live objects nhiều hơn dự đoán

Trong copying collector, chi phí pause phụ thuộc nhiều vào **bao nhiêu live bytes phải copy/scan** hơn là chỉ tổng dung lượng allocations. Khi một batch request giữ nhiều objects qua Young GC, liveness cao hơn lịch sử và pause có thể tăng.

Ví dụ cache vừa được warm-up hoặc một hàng đợi giữ nhiều objects tạm qua điểm collection; đó là thay đổi graph thực tế, không phải collector “không đọc flag”.

### 12.2. Những phases không được heuristic điều khiển trực tiếp hoàn toàn

Một pause có nhiều hạng mục:

- Root scanning.
- Remembered-set updates/scans.
- Object copying/evacuation.
- Reference processing như weak/soft/phantom references.
- Các operation GC marking/cleanup/compaction cụ thể.
- Coordination overhead giữa GC worker threads.
- Chờ threads/safepoint và CPU scheduler delays tùy measurement.

Collector không thể luôn chia nhỏ hoặc hoãn mọi subtask chỉ vì đang có pause budget nhỏ. Nếu yêu cầu consistency hoặc thiếu memory, có thể cần thực hiện những bước vượt thời gian dự kiến.

### 12.3. Full GC, allocation failure và evacuation pressure

Khi application heap gần giới hạn hoặc không còn đủ vùng phù hợp để copy live objects, G1 có thể gặp các tình huống cần xử lý nặng hơn (ví dụ Full GC). Chúng có thể tạo pause outlier dù young collections trước đó ngắn.

**Không tăng heap vô hạn** như một “lời giải real-time”: nhiều memory headroom có thể giảm failure pressure, nhưng các live objects còn reachable vẫn cần được xử lý và các nguồn latency khác còn tồn tại.

### 12.4. Humongous allocations và region fragmentation

Trong G1, object kích thước từ **một nửa region trở lên** thuộc nhóm humongous, có đường allocation đặc biệt trong old/humongous regions. Những allocations lớn này có thể gây áp lực lên contiguous regions, triggering events và fragmentation phù hợp.

Một byte array rất lớn hoặc object graph có các buffers lớn có thể khiến GC pattern khác hoàn toàn workload toàn object nhỏ. Khi thấy pause outliers liên quan humongous, xem sizes/allocations/region logs thay vì chỉ hạ `MaxGCPauseMillis`.

### 12.5. CPU throttling và hệ thống thiếu tài nguyên

Container giới hạn CPU hoặc một host bị nhiều processes tranh chấp có thể khiến các GC worker threads không được chạy đầy đủ. Pause wall-clock kéo dài dù lượng công việc GC tương tự.

Theo dõi:

- CPU quota/cgroup throttling.
- Run queue và OS scheduling.
- GC worker threads count phù hợp.
- Page faults/memory pressure.
- JVM process RSS và native memory.
- Concurrent collector CPU consumption.

Không suy `Pause Young 120ms` luôn do liveness hay GC algorithm; ở môi trường container, **CPU starvation** có thể là nhân tố chính.

### 12.6. Explicit GC và môi trường benchmark bị can thiệp

Gọi `System.gc()` trong code ứng dụng, thư viện hoặc test harness có thể yêu cầu một collection đặc biệt tùy collector/flags. Đừng dùng repeated `System.gc()` như công cụ “ép pause theo mục tiêu”. GC pressure do benchmark sinh không đại diện có thể khiến kết luận tuning sai.

Nếu log có cause `System.gc()`, hãy tìm caller/instrumentation và xem cờ JVM phù hợp; đừng lẫn nguyên nhân này với các normal allocation-driven young pauses.

## 13. Các cấu hình thử nghiệm và điều không nên làm

### 13.1. Baseline trước khi tuning

```bash
java -XX:+UseG1GC -Xms512m -Xmx512m \
  -Xlog:gc*:file=g1-baseline.log:time,uptime,level,tags \
  MyApp
```

`MyApp` chỉ là **placeholder tên class của ứng dụng thực**, không phải file `PauseGoalDemo.java` được cung cấp ở bài. Để chạy ví dụ độc lập, thay bằng `PauseGoalDemo` như phần 8.

Chốt JDK vendor/build, workload, CPU limits, request sample window, p99, throughput, heap headroom và GC event metrics. Từ đó bạn có baseline thật.

### 13.2. Chỉ chỉnh pause goal một lần

```bash
java -XX:+UseG1GC -Xms512m -Xmx512m \
  -XX:MaxGCPauseMillis=50 \
  -Xlog:gc*:file=g1-goal50.log:time,uptime,level,tags \
  MyApp
```

So với baseline cùng phần cứng/tải/tập dữ liệu. Một mục tiêu thấp hơn **có thể** giảm pauses nhưng tăng GC frequency hoặc CPU overhead. Đo lại request p95/p99, throughput và GC time fraction để biết trade-off có chấp nhận được không.

### 13.3. Tránh khóa young generation khi tuning G1 pause

```bash
# Ví dụ một cấu hình KHÔNG nên áp dụng máy móc khi dựa vào G1 pause control:
java -XX:+UseG1GC -Xmn256m -XX:MaxGCPauseMillis=20 MyApp
```

`-Xmn` giới hạn kích thước young generation theo cách có thể vô hiệu hóa/giảm khả năng G1 tự điều chỉnh young size. Lệnh là một ví dụ phản mẫu về tuning; **không khuyến cáo production** nếu chưa có nghiên cứu phù hợp.

### 13.4. Tránh ép goal quá nhỏ để che vấn đề code

Nếu 80% object allocations là temporary buffers từ việc encode/decode liên tục, có thể giải quyết bằng giảm allocations hoặc đổi data representation. Nếu cache giữ live set vài GB không kiểm soát, cần xem retention policy. Nếu service thiếu CPU, đổi pause goal không tạo thêm processor time.

**Đặt goal chỉ là một tham số**. Tối ưu code, heap sizing và hệ thống triển khai có thể quan trọng hơn.

## 14. Đọc đúng SLA/SLO: tần suất, phân vị và tail

Giả sử dịch vụ có SLO:

> 99.9% HTTP responses dưới 100 ms trong rolling 30 ngày.

Đây là **service-level objective** được đo từ **requests**, không phải `MaxGCPauseMillis=100`. Nó có thể bị miss vì 120 ms network delay dù GC không chạy; hoặc có thể đạt nếu phần lớn GC pauses diễn ra ngoài thời điểm xử lý request.

### 14.1. Ví dụ giả lập hai hệ thống

| Thuộc tính | Hệ thống A | Hệ thống B |
| --- | --- | --- |
| GC goal | 30 ms | 100 ms |
| GC pause p99 thực đo | 70 ms | 80 ms |
| Request p99 thực đo | 400 ms | 95 ms |
| Throughput | 1.000 req/s | 2.000 req/s |
| Có đạt request SLO p99 dưới 100 ms? | Không | Có |

**Dữ liệu giả lập.** Hệ thống A có goal nhỏ hơn nhưng request latency tệ hơn. Có thể A bị CPU starvation, long-running locks, network hoặc workload khác. Không dùng bảng giả lập để kết luận goal=100 luôn tốt hơn goal=30; nó chỉ chứng minh **flag value không quyết định SLA outcome**.

### 14.2. Miss rate và error budget

Nếu có 1.000.000 requests trong cửa sổ và SLO là 99.9% đạt deadline, budget tối đa 0.1% failures tương ứng **1.000 requests** ngoài mục tiêu theo cách đếm đơn giản. Thực tế cần định nghĩa chính xác “successful request”, timeouts, retries và synthetic probes.

GC pause targets không tính hộ error budget đó. Một JVM có thể có GC outlier nhưng request deadlines vẫn được đáp ứng trong giai đoạn ít tải; ngược lại request deadlines có thể miss liên tục vì upstream service chậm trong khi GC hoàn toàn bình thường.

## 15. Quy trình chẩn đoán khi p99 tăng và GC pauses dài

**Bước 1 — Xác nhận symptom.** Kiểm tra request p99, timeout rate, CPU, RSS, GC pause p99/max và cửa sổ thời gian.

**Bước 2 — Kiểm tra collector, flags và heap.** Lấy `java -version`, `-Xms/-Xmx`, `UseG1GC`/`UseParallelGC`/`UseZGC`, `MaxGCPauseMillis` thực tế (đừng chỉ đọc manifest deployment).

**Bước 3 — Tách GC causes/types.** Đếm young/mixed/full/explicit GC riêng. Full GC outlier rất khác với young evacuation đều đặn.

**Bước 4 — Kiểm tra time correlation.** Đặt GC log timestamps cạnh request traces và safepoint events. Phân biệt start/end trùng nhau với ngẫu nhiên gần nhau.

**Bước 5 — Xem live set, allocations và promotion.** High live data, large buffers và object retention pressure thường quyết định chi phí copy/scanning và heap headroom.

**Bước 6 — Quan sát CPU/runtime/container.** Kiểm tra cgroup throttling, run queue, thread count, contention và memory pressure.

**Bước 7 — Chọn một thay đổi có giả thuyết.** Có thể là giảm allocations, tăng heap headroom, điều chỉnh G1 pause goal hoặc thử collector low latency.

**Bước 8 — Benchmark lặp lại với workload đại diện.** Đo ít nhất pause distributions, request p95/p99, total throughput, CPU và memory cùng lúc. Một lần chạy không đủ.

**Bước 9 — So với SLO thực.** Nếu p99 requests cải thiện nhưng throughput giảm 30%, hãy cân nhắc mục tiêu sản phẩm. Nếu GC p99 giảm mà p99 service vẫn không đổi, bottleneck có thể ở nơi khác.

**Bước 10 — Xem lại nguyên nhân khi môi trường đổi.** Khi CPU quotas, traffic shape hoặc JDK version đổi, cần đo lại; không áp vĩnh viễn một flag tuning từ một máy benchmark cũ.

## 16. Những hiểu lầm thường gặp

1. **“`MaxGCPauseMillis=20` bảo đảm mọi GC dưới 20 ms.”** Sai; đây là target/hint, không hard bound.
2. **“Chỉ cần đặt goal bằng request SLA là đạt SLA.”** Sai; request latency bao gồm nhiều thành phần khác GC.
3. **“G1 mặc định 200 ms nghĩa G1 luôn pause đúng 200 ms.”** Sai; đây là **giá trị goal mặc định ở Java 17**, không phải kết quả đo.
4. **“Nếu có một pause 201 ms khi goal=200 thì JVM sai đặc tả.”** Sai; goal có thể bị miss.
5. **“Có thể dùng GC pause goal để chứng minh hard real-time.”** Sai; cần worst-case guarantees xuyên toàn hệ thống.
6. **“G1 là concurrent collector nên không bao giờ STW.”** Sai; G1 có young/mixed evacuation và một số phases dừng ứng dụng.
7. **“G1 có GC workers chạy song song nên ứng dụng cũng luôn chạy song song với GC.”** Sai trong STW phases.
8. **“Goal càng thấp thì throughput luôn càng cao.”** Sai; young size có thể bị giảm và GC frequency/overhead tăng.
9. **“Goal càng thấp thì mọi pause luôn càng thấp.”** Sai; outliers và non-predictable phases có thể vượt.
10. **“Một Full GC cũng sẽ tự dừng khi hết 50 ms budget.”** Sai; không có hard pause interrupt contract.
11. **“`-Xmn` luôn giúp G1 kiểm soát pause tốt hơn.”** Sai; fixed young size có thể phá khả năng adaptive control.
12. **“Young GC xảy ra nhiều hơn nghĩa memory leak chắc chắn.”** Sai; allocation churn có thể cao mà live set thấp.
13. **“GC event average=10ms nghĩa p99=10ms.”** Sai; tail có thể dài hơn rất nhiều.
14. **“GC pause p99 chính là HTTP response p99.”** Sai; hai tập samples và measurement khác nhau.
15. **“CPU starvation không ảnh hưởng GC pause.”** Sai; GC workers cũng cần CPU time.
16. **“Tăng `ParallelGCThreads` luôn giảm pause theo tỷ lệ tuyến tính.”** Sai; bandwidth và coordination overhead giới hạn.
17. **“ZGC là hard real-time JVM.”** Sai; low latency design không tự bảo đảm OS/app deadlines.
18. **“GC log line nào cũng là một GC pause độc lập.”** Sai; phase details có thể thuộc cùng một event.
19. **“Safepoint Total time và GC pause time luôn là hai con số độc lập có thể cộng vào nhau.”** Sai; chúng có thể chồng lấp.
20. **“Chạy `System.gc()` là cách kiểm tra xem flag goal có bảo đảm không.”** Sai; explicit GC có thể đi đường khác workload bình thường.
21. **“Đo một lần benchmark là đủ chọn collector.”** Sai; workload warm-up, JIT/GC heuristics và OS conditions biến thiên.
22. **“Mọi JVM vendor hỗ trợ cờ HotSpot giống hệt.”** Sai; options là implementation-specific.
23. **“Một heap càng lớn luôn có pause càng ngắn.”** Sai; quan hệ phụ thuộc live data/collector.
24. **“Chỉ cần xem GC log là biết mọi nguyên nhân request timeout.”** Sai; cần app traces, CPU, network và I/O metrics.
25. **“Khi GC goal được thỏa phần lớn thời gian thì không có quyền gặp một outlier.”** Sai; mục tiêu mềm cho phép ngoại lệ.
26. **“Tối ưu pause time là bài toán không cần hiểu overhead/throughput.”** Sai; cần cân bằng latency, throughput và footprint.
27. **“Phân vị p99 từ 10 sự kiện đáng tin như từ hàng triệu mẫu.”** Sai; sample size và phương pháp tính ảnh hưởng khả năng kết luận.
28. **“Đặt `MaxGCPauseMillis=0` nghĩa GC hoàn toàn không pause.”** Không đúng; giá trị hợp lệ/tác động phụ thuộc option parsing/runtime và không biến GC thành zero-pause real-time.
29. **“Concurrent GC work không ảnh hưởng performance ngoài pause.”** Sai; có thể tranh CPU/memory bandwidth.
30. **“Vượt request deadline chắc chắn do GC.”** Sai; cần phân tích nguyên nhân đa tầng.

## 17. Tự kiểm tra (có đáp án)

**Câu 1.** Câu “`-XX:MaxGCPauseMillis=50` đảm bảo GC dưới 50 ms” đúng không?

**Đáp án:** Không. Flag biểu diễn **goal/hint** để collector cố điều chỉnh, không tạo hard deadline.

**Câu 2.** Tại sao một Young GC của G1 có thể vượt mục tiêu?

**Đáp án:** Dự đoán live bytes, remembered-set work, CPU headroom hoặc một pha cụ thể có thể khác giả định; collector không cắt ngang công việc bắt buộc một cách tùy ý.

**Câu 3.** G1 Java 17 có default pause goal bao nhiêu theo Oracle guide?

**Đáp án:** **`-XX:MaxGCPauseMillis=200`**, là goal, không phải guaranteed pause max.

**Câu 4.** Parallel GC có thể xử lý nhiều GC tasks song song nhưng vẫn pause ứng dụng không?

**Đáp án:** Có. **Parallel** giữa GC workers khác với **concurrent** giữa GC và application.

**Câu 5.** Một dịch vụ p99 300 ms, GC pause p99 15 ms. Hạ GC goal có chắc cải thiện service p99?

**Đáp án:** Không. Phải xem queue time, locks, CPU, remote I/O và correlation giữa GC và request.

**Câu 6.** Nếu young size nhỏ hơn, có phải tổng thời gian GC luôn nhỏ hơn?

**Đáp án:** Không. Một pause có thể ngắn hơn nhưng số events tăng và throughput có thể giảm.

**Câu 7.** Một Full GC 900 ms khi goal=50 ms có vi phạm Java Language Specification không?

**Đáp án:** Không do flag này; goal là heuristic của VM, không có hard real-time requirement.

**Câu 8.** `PauseStatisticsDemo` cho average và max bao nhiêu?

**Đáp án:** Average **26.0 ms**, max **130 ms** trên 10 mẫu giả định.

**Câu 9.** `PauseGoalDemo` giữ lại bao nhiêu arrays?

**Đáp án:** **20**, do 160.000 iterations và giữ mỗi lần `i` chia hết cho 8.000.

**Câu 10.** Vì sao cần GC log và safepoint log cùng nhau?

**Đáp án:** Để phân biệt GC work với thời gian đưa threads đến safepoint và một số VM operations khác; cần kiểm tra phạm vi đo để không đếm trùng.

**Câu 11.** Vì sao p99 GC events và p99 requests không cùng mẫu?

**Đáp án:** Một bên lấy **pause events**, một bên lấy **requests**; số lượng, thời gian và việc overlap khác nhau.

**Câu 12.** Khi hạ GC goal mà throughput giảm, nên kết luận flag lỗi không?

**Đáp án:** Không. Có thể đây là trade-off dự kiến do young size nhỏ/GC events nhiều; cần so với SLO và CPU/heap metrics.

**Câu 13.** Trong hard real-time system, có thể dùng duy nhất `-XX:MaxGCPauseMillis` làm bằng chứng đáp ứng deadline không?

**Đáp án:** Không. Cần các bounds trên scheduler, worst-case app processing, allocation, GC, OS và external dependencies.

**Câu 14.** Tại sao không nên cố định `-Xmn` khi dùng G1 và trông đợi GC pause target tự điều chỉnh?

**Đáp án:** Vì young-generation sizing là một công cụ chủ yếu để G1 cân đối pause durations; cố định nó có thể hạn chế mạnh heuristic control.

## 18. Tổng kết bằng bản đồ quyết định

```text
BẠN MUỐN GIẢM GC PAUSE / REQUEST LATENCY?
                   │
                   ▼
           Xác định chỉ số cần đạt
            ├─ GC pause p95/p99/max?
            ├─ request p99/SLO?
            └─ hard real-time deadline?
                   │
                   ▼
           Thu thập dữ liệu thật
            ├─ GC logs + GC ids/events
            ├─ safepoint logs / JFR
            ├─ request tracing & histograms
            └─ CPU/heap/container metrics
                   │
                   ▼
         Phân tích cause & trade-off
            ├─ Young GCs dài? → CSet/young/live data
            ├─ Full GC? → heap headroom/retention
            ├─ CPU throttling? → resource limits
            ├─ request queue/DB? → non-GC bottleneck
            └─ throughput quá thấp? → overly aggressive goal
                   │
                   ▼
       Chọn một thay đổi có giả thuyết
            ├─ Giảm allocations/retention
            ├─ Cấp heap và CPU headroom phù hợp
            ├─ Điều chỉnh soft GC pause goal
            └─ Đổi collector khi yêu cầu latency
                   │
                   ▼
      Benchmark nhiều lần trên workload thực
                   │
            ┌──────┴──────┐
         Đạt SLO?       Chưa đạt?
            │             │
         Monitor       Điều tra lại cause,
         liên tục      không hứa deadline bằng flag
```

**Ghi nhớ:** `-XX:MaxGCPauseMillis` là **mục tiêu tối ưu được GC cố gắng đạt**, **không phải giới hạn cưỡng chế**, **không phải lời hứa thời gian thực** và **không phải SLA của request**. G1 điều chỉnh kích thước young/CSet dựa trên dự đoán từ workload; trade-off thường nằm giữa **độ dài pause, tần suất GC, thông lượng và footprint**. Full GC, live-set spikes, CPU throttling hay safepoint delays có thể khiến thời gian thực tế vượt mục tiêu. Hãy đánh giá **phân phối thực đo**, correlate GC với end-to-end latency và chọn cấu hình/collector theo SLO thay vì dựa vào một con số trong command line.

### Tài liệu tham khảo chuẩn

- [Oracle Java SE 17 — Ergonomics / Maximum Pause-Time Goal](https://docs.oracle.com/en/java/javase/17/gctuning/ergonomics.html): xác nhận `MaxGCPauseMillis` là *hint*, có thể không đạt.
- [Oracle Java SE 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): G1 region model, pause-time default goal 200 ms, evacuation và concurrent phases.
- [Oracle Java SE 17 — Garbage-First GC Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html): pause/throughput tuning, young-size interactions, diagnosis.
- [Oracle Java SE 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): Serial, Parallel, G1, ZGC và các mục tiêu khác nhau.
- [Oracle Java SE 17 — `java` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `UseG1GC`, `MaxGCPauseMillis`, `-Xlog`, heap options, `StartFlightRecording`.
- [Oracle JDK 17 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.html): event recording/observability.
- [Oracle JDK 17 — `jcmd` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): kiểm tra JVM/GC/JFR và diagnostic commands.
