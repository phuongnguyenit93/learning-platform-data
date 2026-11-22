# Lựa chọn Garbage Collector: thông lượng, độ trễ, CPU và dung lượng bộ nhớ

## Mục tiêu bài học

Không có một garbage collector (GC) luôn tốt nhất cho mọi ứng dụng Java. Một batch job có thể cần **xử lý được nhiều công việc nhất mỗi phút**, một API giao dịch có thể phải giữ **p99 response time** thấp, còn một container dịch vụ nhỏ có thể bị giới hạn **CPU quota và RAM** nghiêm ngặt. Những yêu cầu đó có thể xung đột: GC chạy đồng thời có thể giảm thời gian dừng ứng dụng nhưng sử dụng thêm CPU và memory bandwidth; một heap rộng có thể giảm tần suất GC nhưng tăng memory footprint; một collector ưu tiên thông lượng có thể chấp nhận những lần dừng dài hơn.

Sau bài học, bạn có thể:

- Định nghĩa và đo đúng **throughput**, **latency (p50/p95/p99)**, **GC pause**, **GC CPU cost**, **allocation rate**, **live set**, **heap footprint** và **process RSS**.
- Phân biệt **tỷ lệ thời gian Stop-The-World (STW)** với thông lượng nghiệp vụ; biết vì sao concurrent GC không hiện đầy đủ trong tỷ lệ STW.
- Hiểu tác động của heap headroom, live-object ratio, object lifetime, large allocations và áp lực bộ nhớ.
- So sánh **Serial, Parallel, G1, ZGC và Shenandoah** trong HotSpot với ràng buộc phiên bản/JDK distribution.
- Xây dựng một **quy trình lựa chọn dựa trên SLA/SLO**, không lựa collector chỉ từ khẩu hiệu “GC nhanh nhất”.
- Lấy GC logs, JFR, metrics và jcmd đúng cách; thiết kế thử nghiệm A/B có warmup, tải thực và cùng điều kiện CPU/RAM.
- Diễn giải ví dụ Java 17+ có kết quả xác định mà không bịa số liệu GC phụ thuộc môi trường.
- Nhận ra những lỗi phổ biến khi tuning và các chiến lược giảm allocation/retention trước khi đổi collector.

## 1. Bốn trục đánh đổi

Một collector ảnh hưởng ít nhất bốn trục chính:

| Trục | Câu hỏi của người vận hành | Ví dụ chỉ số |
| --- | --- | --- |
| **Thông lượng (throughput)** | Trong một đơn vị thời gian, ứng dụng hoàn thành bao nhiêu công việc hữu ích? | requests/s, jobs/min, records/s, bytes/s |
| **Độ trễ (latency)** | Một yêu cầu mất bao lâu, đặc biệt ở phần đuôi phân phối? | p50, p95, p99, p99.9, max response time; GC pause distribution |
| **CPU** | Collector lấy bao nhiêu năng lực xử lý từ ứng dụng và hệ thống? | process CPU time, GC threads CPU, CPU quota throttling, cycles/op |
| **Bộ nhớ (memory footprint)** | Cần bao nhiêu heap và bộ nhớ của cả tiến trình để an toàn? | -Xmx, live heap, committed heap, RSS, native memory, headroom |

Chúng liên quan nhưng **không đồng nhất**. Ví dụ, một hệ thống có p99 GC pause rất thấp vẫn có thể có p99 request latency cao do database, queueing, locks, CPU contention hoặc network. Ngược lại, throughput tốt không có nghĩa một giao dịch riêng không từng bị dừng bởi GC.

### Ví dụ ba workload khác nhau

**Batch ETL:** xử lý 200 triệu records trong thời gian ngắn nhất; có thể chấp nhận pause hàng trăm mili-giây đến giây nếu công việc không phục vụ tương tác tức thì. Có thể ưu tiên throughput.

**REST API tương tác:** p99 từ ingress tới response cần dưới một ngưỡng nhất định, ví dụ 150 ms. GC pause một lần 250 ms có thể trực tiếp gây trượt SLO, nhưng **không chỉ GC** tạo tail latency. Cần quan sát full latency path.

**Nhiều JVM nhỏ trên cùng host/container:** mỗi process chỉ có 1 vCPU và hạn mức RAM chặt. Việc dành quá nhiều CPU cho concurrent GC hoặc quá nhiều headroom cho mỗi JVM có thể làm giảm mật độ triển khai, dù pause nhỏ.

**Kết luận đầu tiên:** hãy viết rõ **SLO hữu ích cho người dùng/kinh doanh**, sau đó mới chọn GC và heap size.

## 2. Định nghĩa throughput: phải nói đang đo thứ gì

Trong tài liệu GC, throughput đôi khi được mô tả gần đúng là **tỷ lệ thời gian chương trình làm việc thay vì STW collection**. Nhưng trong vận hành thực tế, cách đo quan trọng hơn là **tốc độ hoàn thành công việc hữu ích** dưới tải và SLO.

Hai phép đo có liên quan nhưng khác nhau:

~~~text
Application throughput:
  jobs_completed / wall_clock_seconds
  hoặc requests_completed / elapsed_seconds

STW pause fraction (chỉ để tham khảo):
  sum(STW_pause_durations_within_window) / window_duration

Mutator available time fraction (xấp xỉ):
  1 - STW_pause_fraction
~~~

Ví dụ trong một khoảng 10 giây có tổng STW pauses 0,3 giây:

~~~text
Window                  = 10.0 s
Total STW pauses        =  0.3 s
STW pause fraction      =  3%
Approx mutator time     = 97%
~~~

**Không được tuyên bố “throughput ứng dụng = 97%”** chỉ từ những con số trên. Khi GC chạy concurrent:
- Collector vẫn sử dụng CPU cores và memory bandwidth trong lúc mutators không bị dừng.
- Read/write barriers có thể làm đường đi của ứng dụng tốn thêm instructions.
- CPU contention có thể làm chậm request completion mà không xuất hiện như một STW pause.
- JIT, application locking, I/O và tail effects có thể thay đổi hiệu năng tổng.

Để đánh giá business throughput, hãy đo **completed work/s** và **saturation point**, đồng thời ghi **error rate**. Một chương trình trả lỗi nhanh có thể có requests/s lớn nhưng không hoàn thành công việc hữu ích đúng nghĩa.

### Đặt tải không đổi khi so sánh

So hai collector ở 500 requests/s sẽ không có ý nghĩa nếu một collector thực tế nhận 1000 requests/s trong thử nghiệm kia. Hãy phân biệt:
- **Offered load**: tốc độ client cố gắng gửi requests.
- **Completed throughput**: tốc độ server hoàn tất requests thành công.
- **Backlog/queue depth**: số yêu cầu chờ.
- **Latency distribution**: thời gian chờ + xử lý thực tế.
- **Error/timeout rate**: số requests không thành công.

Một collector tăng completed throughput nhưng tạo p99 vượt ngưỡng vẫn có thể **không đạt SLO**. Chọn theo mục tiêu chứ không xếp hạng collector bằng một số duy nhất.

## 3. Độ trễ: phân biệt GC pause với thời gian phản hồi

**GC pause** là khoảng thời gian collector dừng các application threads do sự kiện GC cụ thể (tùy cách ghi log và phase). **Response time** của một HTTP request là thời gian từ lúc request được nhận/đo ở một điểm đầu đến khi trả response ở điểm cuối được xác định.

Chúng không bằng nhau.

~~~text
Request timeline (minh họa):

Ingress --> queue wait --> application CPU --> GC STW --> DB wait
        --> serialization --> network send --> response

Response latency = tất cả các đoạn trong định nghĩa đo
GC pause latency = chỉ khoảng dừng do GC đã đo riêng
~~~

Một request có thể trượt p99 vì bị queueing dưới CPU throttling dù GC pause nhỏ. Ngược lại, một GC pause 100 ms có thể khiến nhiều requests cùng bị trễ và làm **tail latency** nặng hơn thời gian pause riêng lẻ do hàng đợi tích tụ.

### Percentile p50/p95/p99 là gì?

Nếu đo đủ mẫu cùng định nghĩa:
- **p50**: trung vị gần đúng; nửa quan sát không lớn hơn ngưỡng này theo quy tắc percentile được chọn.
- **p95**: khoảng 95% observations không vượt ngưỡng.
- **p99**: khoảng 99% observations không vượt ngưỡng.
- **p99.9**: quan tâm những lần hiếm hơn, cần số mẫu lớn và phương pháp thống kê phù hợp.

**Các công cụ percentile có thể dùng thuật toán/interpolation khác nhau** nên kết quả số cụ thể đôi lúc khác. Khi so, hãy dùng cùng phương pháp, cùng cửa sổ thời gian và tập requests. Đừng lấy **p99 GC pause** làm **p99 request latency**.

### Ví dụ một sự cố thật về mặt logic

Một collector giữ 99% GC pauses dưới 8 ms nhưng vẫn có một lần stop-the-world 400 ms trong một giờ. Nếu hệ thống có SLA p99.9 dưới 100 ms hoặc hàng đợi rất nhạy, đuôi còn lại có thể đủ gây lỗi. Ngược lại, một collector có vài pauses 60 ms có thể không làm request p99 trượt nếu ứng dụng còn dư latency budget và throughput ổn định.

**Điều kiện cần** là đưa GC metrics vào cùng timeline với service latency, CPU saturation, queueing, allocation pressure và errors.

## 4. CPU: tổng chi phí, CPU đồng thời và quota

GC có hai loại work chính (không phải mọi collector chia chính xác như nhau):

1. **STW work**: dừng mutators để một phần GC xử lý roots, references, copy/sweep/compact...
2. **Concurrent/background work**: marking, remapping, refinement, relocation hoặc housekeeping khi application threads vẫn chạy.

Hai collector có cùng tổng STW pause fraction có thể tiêu thụ lượng CPU rất khác nhau.

Ví dụ giả định:
- Collector A STW 4% thời gian, gần như không làm concurrent work.
- Collector B STW 0,3% nhưng dùng thêm một lượng đáng kể CPU cores để mark/relocate đồng thời.

Không thể kết luận B có throughput cao hơn chỉ vì STW thấp. Nếu máy có nhiều idle cores, phần CPU đồng thời có thể chấp nhận được. Nếu container chỉ được **1 vCPU**, GC threads có thể cạnh tranh mạnh với application threads, làm tăng tail latency.

### Phân biệt CPU utilization

Một process có thể dùng **200% CPU** trên hệ thống đo kiểu “100% = một core” khi chạy trên hai cores. Vì vậy cần ghi:
- Host có bao nhiêu logical cores?
- Container CPU quota/cpuset bao nhiêu?
- JVM đã nhận diện bao nhiêu active processors?
- CPU usage là **process**, **container** hay **host**?
- Có CPU throttling không?
- Collector sử dụng threads riêng bao nhiêu?

Các công cụ OS/container (ví dụ cgroup CPU throttling metrics) cần được phối hợp với Java GC data. Không suy luận “GC ít pause thì ít tốn CPU” hay “CPU host còn rảnh tức JVM không bị quota”.

### Memory bandwidth cũng là tài nguyên

GC copying/evacuation, root scanning và write barriers có thể tăng:
- cache misses,
- memory bandwidth,
- work trên reference graph,
- dirty pages,
- CPU contention.

Ngay khi CPU usage không đạt 100%, hệ thống vẫn có thể bị memory-bandwidth pressure hoặc memory stalls. Lựa chọn GC phải xét cả **CPU/memory architecture** và cách dữ liệu của ứng dụng phân bổ.

## 5. Bộ nhớ: heap size không phải toàn bộ process footprint

Một JVM process cần nhiều hơn Java heap:

~~~text
Process memory / RSS (minh họa)
  |
  +-- Java heap (objects/arrays, GC regions)
  +-- Metaspace / class metadata
  +-- Code cache / JIT-compiled code
  +-- Thread stacks / native thread-related memory
  +-- Direct ByteBuffers / native allocations
  +-- GC native metadata, card tables/remembered sets
  +-- Native libraries, runtime structures, memory mapping ...
~~~

Vì vậy **`-Xmx=2g` không có nghĩa RSS process sẽ luôn dưới 2 GiB**. Và committed heap lớn không phải đồng nghĩa live objects đều đang dùng từng byte. Một số cấu hình collector giữ nhiều committed memory để tái sử dụng, một số có cơ chế uncommit khác nhau.

| Khái niệm | Nghĩa | Cảnh báo |
| --- | --- | --- |
| **-Xms** | Initial heap size theo JVM flags | Không phải toàn bộ RAM đã dùng của process. |
| **-Xmx** | Max Java heap | Không giới hạn mọi native memory của process. |
| **Used heap** | Dung lượng heap JVM coi đang được sử dụng | Không luôn là live bytes sau full liveness analysis. |
| **Committed heap** | Bộ nhớ JVM đã commit cho heap | Có thể lớn hơn used. |
| **Live set** | Objects còn sống/reachable cần giữ | Thay đổi theo thời điểm và collector/cách đo. |
| **Allocation rate** | Bytes được cấp phát theo thời gian | Có thể rất lớn dù live set nhỏ. |
| **Heap headroom** | Chênh giữa heap budget và phần bộ nhớ cần thiết cho live data, allocations, collector work | Là khái niệm vận hành, không chỉ một phép trừ cố định. |
| **RSS / working set** | Memory process/container thực sự chiếm theo OS | Có memory ngoài heap và các sắc thái page reclaim. |

### Headroom cho concurrent collectors

Một GC concurrent phải thu hồi bộ nhớ trong khi mutators **tiếp tục allocate**. Nếu tốc độ phát sinh objects mới vượt khả năng collector hoàn thành cycle hoặc destination capacity không đủ, hệ thống có thể bị **allocation stalls**, forced collection hoặc out-of-memory theo collector cụ thể.

Một bộ nhớ quá chật:
- làm GC chạy thường xuyên;
- giảm vùng dự trữ cho các objects được di chuyển;
- tăng rủi ro phải chuyển sang đường xử lý đắt hơn;
- tăng độ khó giữ latency ổn định.

Ngược lại, tăng `-Xmx`:
- thường giảm áp lực GC đối với một số workload;
- nhưng tăng ngân sách memory, có thể tăng footprint và làm giảm density triển khai;
- có thể tăng thời gian xử lý tập live lớn hoặc thay đổi behavior GC;
- không chữa retention leak nếu object graph tăng vô hạn.

**Đừng khuyên “cứ tăng heap thật lớn để giảm GC”** nếu chưa kiểm tra RAM quota, native memory, live-set và SLA.

## 6. Tỷ lệ sống/chết quan trọng hơn chỉ số `new`

GC phải xử lý **đối tượng sống** theo thuật toán phù hợp. Allocation lớn nhưng objects chết nhanh có thể được collector xử lý tương đối hiệu quả, nhất là trong young-generation workloads. Tuy nhiên allocation quá nhanh vẫn dùng CPU/bandwidth và tạo pressure.

Hai tình huống:

**Workload A:** tạo 2 GB temporary byte arrays trong mỗi khoảng thời gian, nhưng chỉ giữ 200 MB live. Young collection có thể reclaim phần lớn dung lượng, nhưng allocation rate cao gây work.

**Workload B:** allocation rate thấp, nhưng có 10 GB objects sống lâu trong cache; mỗi major cycle phải xử lý lượng live data lớn, có thể làm heap/headroom rất căng.

Bởi vậy các metric cần cùng xuất hiện:
- bytes allocated/op và bytes/s,
- live heap sau các collection phù hợp,
- object ages/lifetime histogram khi có dữ liệu,
- humongous/large-object allocation rate,
- GC frequency, pause distribution và CPU,
- total process memory và CPU quota.

**Một “memory leak” trong Java** thường là sự giữ references ngoài ý muốn. Đổi từ G1 sang ZGC không tự làm những objects còn reachable biến mất. Khi vấn đề là leak, sửa cache/ownership/lifetime thường quan trọng hơn tuning collector.

## 7. Tổng quan Serial, Parallel, G1, ZGC, Shenandoah

Các nhận định dưới đây mô tả **hướng thiết kế chung**, không phải bảng xếp hạng tuyệt đối. Các thuật toán và flags thay đổi theo JDK release/HotSpot vendor.

| Collector | Hướng ưu tiên thường gặp | Điểm mạnh | Đánh đổi cần đo |
| --- | --- | --- | --- |
| **Serial GC** | Đơn giản, heap/workload nhỏ hoặc CPU rất hạn chế | Ít GC worker overhead, setup đơn giản | STW và GC làm việc bằng ít threads, không hợp pauses lớn trên heap lớn |
| **Parallel GC** | Ưu tiên **throughput** với parallel collection | Tận dụng nhiều CPU cores cho GC, good throughput trong nhiều batch workloads | STW pauses có thể dài, không phù hợp tail latency chặt |
| **G1 GC** | Cân bằng throughput và pause-time goal | Region-based, incremental evacuation, concurrent marking, pause target heuristic | Concurrent work, remembered-set/card overhead, evacuation/headroom và humongous object considerations |
| **ZGC** | **Low-pause/low-latency** theo hướng concurrent GC | Phần nặng của marking/relocation được làm concurrent; giảm STW contribution | CPU/bandwidth, barrier overhead, đủ heap headroom để không stall |
| **Shenandoah** | Low-pause với concurrent evacuation/compaction | Nhiều công việc GC thực hiện đồng thời với mutators | Tăng concurrent/barrier work và memory headroom; availability/mode tùy bản JDK |

### Serial GC

`-XX:+UseSerialGC` là một lựa chọn hợp lý để **thử nghiệm** cho chương trình nhỏ, heap nhỏ hoặc khi chỉ có một CPU và pauses không quan trọng. Nó không phải “GC cho Java cũ” theo nghĩa không thể dùng trên JDK mới. Nhưng khi heap lớn và độ trễ nhạy, làm collection trong STW có thể gây pause dài.

### Parallel GC

`-XX:+UseParallelGC` là collector hướng throughput. Nhiều GC worker threads giúp hoàn tất công việc GC trong những pauses; điều đó có thể làm throughput tốt khi workload có nhiều cores và chấp nhận pauses. **Parallelism của GC không biến toàn bộ collection thành concurrent**; application vẫn có thể bị dừng.

### G1

`-XX:+UseG1GC` là lựa chọn mặc định trên **nhiều cấu hình HotSpot hiện đại**. G1 thiết kế để đạt pause target với xác suất cao trong khi giữ throughput tốt; pause target là **soft goal**, không phải SLA cứng. G1 thu gom theo regions; young/mixed collections có evacuation, marking một phần đồng thời, và overhead remembered sets/barriers.

### ZGC

`-XX:+UseZGC` chọn ZGC nếu bản JDK/VM hỗ trợ. ZGC được thiết kế để làm những công việc nặng đồng thời nhằm giảm thời gian dừng ứng dụng, thích hợp với latency-sensitive workloads. Nhưng low GC pause **không miễn phí**: concurrent work và heap headroom có thể giảm throughput hoặc tăng RSS theo workload.

### Shenandoah

`-XX:+UseShenandoahGC` chọn Shenandoah **trên các build có hỗ trợ**. Đây là collector low-pause bằng concurrent work, nhưng availability/flags/modes phụ thuộc bản OpenJDK vendor và release. Không kết luận “Oracle JDK, OpenJDK, tất cả distributions cùng có Shenandoah và một bộ flags giống nhau”.

## 8. Cảnh báo khác biệt giữa các bản Java: đặc biệt ZGC

Khi đưa lệnh vào README hoặc playbook, cần ghi **bản Java mục tiêu**. Ví dụ:

~~~text
JDK 17:
  -XX:+UseZGC                 (ZGC non-generational trên JDK 17)

JDK 21:
  -XX:+UseZGC -XX:+ZGenerational
    (chọn Generational ZGC trên JDK 21)

JDK 23:
  -XX:+UseZGC                 (generational mode mặc định theo JEP 474)

JDK 24 trở lên với HotSpot tương ứng:
  -XX:+UseZGC                 (non-generational ZGC đã bị loại bỏ)
~~~

Đây là **sơ đồ tùy chọn theo phiên bản**, không phải một script chạy nguyên khối. JDK 24 loại bỏ non-generational ZGC và option `ZGenerational`, nên **không bê nguyên** lệnh JDK 21 có `-XX:+ZGenerational` sang JDK 24+. Shenandoah cũng có những bước phát triển generational và flags tùy phiên bản.

Một thực hành tốt:

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
~~~

Lệnh thứ hai có thể in rất nhiều flags. Đừng đoán collector từ năm phát hành Java; ghi **JDK build** và **selected GC thực tế**. Có thể dùng `-Xlog:gc*=info` hoặc `jcmd PID VM.flags` để hỗ trợ điều tra.

**Không nâng cấp Java rồi tái dùng một bộ GC tuning flags cũ mà không kiểm tra.** Defaults và algorithm có thể thay đổi đáng kể giữa Java 8, 17, 21, 24 và các release sau.

## 9. Đặt vấn đề dưới dạng ngân sách SLO

Thay vì hỏi “GC nào nhanh nhất?”, hãy tạo một ngân sách:

| Tiêu chí | Ví dụ yêu cầu (giả định) |
| --- | --- |
| Sustained throughput | Ít nhất 2000 successful requests/s |
| End-to-end p99 latency | Không quá 120 ms tại 2000 requests/s |
| Error/timeout rate | Dưới 0,1% |
| CPU budget | Không vượt 4 vCPU quota, tránh CPU throttling kéo dài |
| Container RAM limit | 4 GiB |
| Headroom | Không xảy ra allocation stalls/Full GC/OOME trong test kéo dài |
| GC pauses | GC-related pauses không được thường xuyên chiếm phần lớn latency budget |
| Scale-out density | Số instances cần để đáp ứng tải trong ngân sách hạ tầng |

**Đây là ví dụ học thuật, không phải chỉ tiêu áp dụng mọi ứng dụng.** Tất cả số liệu phải phù hợp dịch vụ, container và SLO thực tế. Một quyết định GC thành công phải **đồng thời** thỏa throughput, latency, stability và memory/CPU cost; nếu bất cứ mục quan trọng nào thất bại thì không nên chọn chỉ vì collector có pause median thấp.

### Latency budget

Giả sử p99 SLO = 120 ms, trong đó không-GC logic đã thường cần 100 ms ở tải mục tiêu. GC cùng CPU contention chỉ có khoảng không hẹp trước khi tổng vượt 120 ms. Nhưng không thể lấy đơn giản “p99 app = p99 business + p99 GC” trong mọi tình huống do **các phân phối có tương quan**, queueing và sampling windows. Sử dụng request tracing, event correlation và load testing để đo distribution cuối cùng.

## 10. Ma trận lựa chọn theo tình huống

| Tình huống | Khởi điểm thử nghiệm | Điểm cần kiểm tra |
| --- | --- | --- |
| CLI tool nhỏ, chạy rất ngắn, heap nhỏ | Mặc định, thử Serial nếu phù hợp | Startup, overall runtime, GC worker overhead |
| Batch throughput-first, pauses vài giây có thể chấp nhận | Parallel và mặc định/G1 làm baseline | Jobs/s, total CPU time, elapsed time, GC pause impact |
| Web API với latency SLO vừa phải | G1 mặc định làm baseline | p99, pause distribution, remembered-set work, CPU/RSS |
| API giao dịch p99 rất chặt | So G1 được tuning với ZGC hoặc Shenandoah nếu build có hỗ trợ | Tail latency **end-to-end**, CPU/headroom, allocation stalls |
| Container RAM thấp, rất nhiều JVM instances | Baseline default/Serial/G1 tùy heap và CPU | RSS, native memory, memory.max, Full GC, OOME |
| Heap nhiều GB, nhiều long-lived objects | G1/ZGC/Shenandoah theo SLA | Live-set, concurrent work, headroom, marking speed |
| Allocation rate cao, temporary objects | G1/Parallel/ZGC theo SLO; tối ưu churn trước | Bytes/op, throughput, GC CPU, stalls |
| Large arrays/humongous objects | Collector baseline và phân tích allocation distribution | G1 humongous regions, fragmentation, headroom |
| Low-latency nhưng CPU quota chặt | Không mặc định chọn concurrent GC | CPU throttling, concurrent CPU, backlog, service p99 |

**Gợi ý mặc định:** bắt đầu với lựa chọn collector mặc định của chính JDK production và heap budget hợp lý; chỉ đổi GC nếu dữ liệu cho thấy không đạt SLO hoặc cost. Oracle GC tuning guide cũng định hướng bắt đầu từ cấu hình mặc định trừ khi yêu cầu đặc thù.

## 11. Kích thước heap: rất nhỏ và rất lớn đều có mặt trái

### Khi `-Xmx` quá nhỏ

- Young/old collections xảy ra thường xuyên.
- Ít evacuation/headroom cho collector cần di chuyển objects.
- Allocation stalls hoặc Full GC có thể tăng.
- Với GC concurrent, không đủ khoảng trống để hoàn thành cycle trước khi mutator dùng hết memory.
- Có thể OOME dù ứng dụng không có memory leak, chỉ do heap budget không đáp ứng peak live set.

### Khi `-Xmx` quá lớn

- Reserved/committed footprint có thể cao; mật độ triển khai giảm.
- Tập live data vẫn có thể lớn và GC cần làm nhiều work.
- Ứng dụng có thể ẩn memory retention bug lâu hơn trước khi biểu hiện.
- Có thể đẩy tổng process memory vượt container RAM do phần **ngoài heap**.
- Với một số collector/configuration, thay đổi heap làm thay đổi generation sizing/GC cycle.

Không được kết luận “heap càng to thì GC pauses càng dài” hay “heap càng to thì latency luôn tốt”: quan hệ tùy collector và workload. Hãy đo **khoảng giá trị heap** ở tải thật và tìm điểm đáp ứng cả headroom lẫn memory cost.

### `-Xms` và `-Xmx` bằng nhau?

Đặt initial/max heap bằng nhau có thể giảm resizing activity và làm behavior ổn định hơn trong một số workload, nhưng làm committed/reserved memory cao ngay từ đầu theo VM behavior và không phải luôn tốt cho memory-constrained fleet. Một số collector có cơ chế uncommit khác nhau. Đừng biến `-Xms=-Xmx` thành quy tắc cho mọi ứng dụng.

## 12. Các flags thường dùng và giới hạn của chúng

| Cờ | Vai trò | Sai lầm phổ biến |
| --- | --- | --- |
| `-Xms256m` | Khởi tạo Java heap khoảng 256 MiB | Coi là toàn bộ process memory. |
| `-Xmx2g` | Giới hạn max Java heap | Coi là giới hạn RSS/container. |
| `-XX:+UseParallelGC` | Chọn Parallel GC | Hứa p99 nhỏ hơn G1 trong mọi workload. |
| `-XX:+UseG1GC` | Chọn G1 | Coi pause target là cam kết SLA. |
| `-XX:+UseZGC` | Chọn ZGC nếu hỗ trợ | Coi có zero overhead hoặc mọi JDK có same mode. |
| `-XX:MaxGCPauseMillis=200` | Pause-time target cho collector hỗ trợ, đặc biệt G1 | Đọc là “không pause nào vượt 200 ms”. |
| `-XX:MaxRAMPercentage=...` | Dùng tỷ lệ RAM khả dụng mà JVM nhận diện để suy heap limit | Quên native memory và cgroup headroom. |
| `-XX:ActiveProcessorCount=...` | Ghi đè số processor JVM sử dụng cho một số heuristics | Dùng để che CPU quota thay vì tìm saturation. |
| `-Xlog:gc*:file=gc.log:time,uptime,level,tags` | Bật GC unified logging theo mức và đích file | Không giới hạn rotation/dung lượng log khi chạy lâu. |

Đây là danh sách **định hướng**, không phải yêu cầu phải bật tất cả cùng lúc. Flags availability/semantic có thể thay đổi theo release. Ví dụ `MaxGCPauseMillis` là **mục tiêu điều chỉnh heuristic**, không phải timer cưỡng chế GC return.

### Tránh ép young-generation sizing tùy tiện với G1

G1 sử dụng young generation size như một trong những công cụ để cân bằng pause target và throughput. Ép `-Xmn` hay các flags thế hệ cũ có thể hạn chế khả năng tự thích nghi của G1. Tốt hơn:
1. Đặt heap bounds phù hợp.
2. Đo logs và latency trước.
3. Nếu cần, điều chỉnh **một** goal như `MaxGCPauseMillis`.
4. Kiểm tra trade-off throughput/CPU/GC frequency sau mỗi thay đổi.

**Không tối ưu một pause riêng biệt bằng cách bỏ qua hiệu quả của toàn hệ thống**.

## 13. Ví dụ Java 17+: tính throughput và percentiles từ dữ liệu cố định

Một ví dụ nhỏ, **chỉ dạy cách tính metric**, không tự sinh số liệu GC của máy:

Tạo tệp **`GcMetricMathDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public class GcMetricMathDemo {
    static long nearestRank(long[] sorted, double fraction) {
        int rank = (int) Math.ceil(fraction * sorted.length);
        return sorted[Math.max(0, rank - 1)];
    }

    public static void main(String[] args) {
        long[] latenciesMs = {5, 7, 8, 9, 10, 11, 12, 13, 30, 90};
        Arrays.sort(latenciesMs);

        long completed = 9_500L;
        double windowSeconds = 10.0;
        double stwSeconds = 0.30;

        System.out.printf(Locale.ROOT, "throughput=%.1f req/s%n",
                completed / windowSeconds);
        System.out.printf(Locale.ROOT, "stwFraction=%.1f%%%n",
                100.0 * stwSeconds / windowSeconds);
        System.out.println("p50=" +
                nearestRank(latenciesMs, 0.50) + "ms");
        System.out.println("p90=" +
                nearestRank(latenciesMs, 0.90) + "ms");
        System.out.println("p99=" +
                nearestRank(latenciesMs, 0.99) + "ms");
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 GcMetricMathDemo.java
java GcMetricMathDemo
~~~

**Stdout chính xác:**

~~~text
throughput=950.0 req/s
stwFraction=3.0%
p50=10ms
p90=30ms
p99=90ms
~~~

Giải thích:
- 9.500 công việc hoàn thành trong 10 giây → **950 req/s**.
- 0,3 giây STW trên 10 giây → **3%** theo mô hình đơn giản.
- Với **nearest-rank percentile**, p50 là phần tử thứ 5, p90 là thứ 9 và p99 là thứ 10 của 10 mẫu.
- **10 mẫu không đủ** để đại diện p99 thực tế của một hệ thống sản xuất; ví dụ chỉ nhằm làm rõ công thức. Phải có cửa sổ thời gian, số lượng mẫu và histogram phù hợp.
- Đừng lấy 3% STW để suy business throughput tăng 3% nếu loại bỏ GC, vì concurrent CPU, queueing, cache effects và các bottlenecks khác vẫn tồn tại.

## 14. Ví dụ Java 17+: workload tạo object để thử GC

Một chương trình có thể tạo nhiều arrays và giữ lại một phần nhỏ để thử các collectors **trên cùng dữ liệu logic**. Tuy nhiên GC scheduling, số pauses và timings phụ thuộc máy/JDK/heap, nên stdout chỉ cam kết những thông tin nghiệp vụ đã được viết xác định.

Tạo tệp **`GcAllocationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GcAllocationDemo {
    private static volatile byte[] latest;

    public static void main(String[] args) {
        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 100_000; i++) {
            byte[] data = new byte[1_024];
            data[0] = (byte) i;
            checksum += Byte.toUnsignedInt(data[0]);

            if ((i % 128) == 0) {
                survivors.add(data);
            } else {
                latest = data;
            }
        }

        System.out.println("survivors=" + survivors.size());
        System.out.println("checksum=" + checksum);
    }
}
~~~

Chạy trên **JDK 17+**:

~~~bash
javac --release 17 GcAllocationDemo.java
java -Xms32m -Xmx128m -XX:+UseG1GC GcAllocationDemo
~~~

**Stdout nghiệp vụ chính xác** (không tính GC logs nếu được bật):

~~~text
survivors=782
checksum=12742320
~~~

Tại sao chương trình có ý nghĩa:
- Mỗi lượt tạo một byte array; tổng logical allocation payload cỡ 100.000 × 1.024 bytes, nhưng **allocation bytes thực tế** còn có header, alignment và JIT effects.
- Mỗi 128 lượt giữ một array trong list, tức có 782 survivors được tham chiếu từ collection ở cuối vòng lặp.
- Field `latest` được khai báo `volatile` và giữ reference gần nhất của các vòng không được retain; nó không bảo đảm mỗi GC sẽ xảy ra đúng thời điểm hoặc mỗi array buộc phải được allocation vật lý trong mọi JIT mode.
- Checksum chỉ phụ thuộc dãy byte 0..255 lặp lại, không phụ thuộc GC collector.
- **Không so sánh hiệu năng bằng stdout ở đây**; muốn đo hiệu năng phải thêm phép thử có setup, warmup, số lần lặp, tính nhiều runs và tools phù hợp.

### Chạy cùng chương trình với các collectors

Ví dụ trên JDK 17+ có G1 và Parallel:

~~~bash
java -Xms32m -Xmx128m -XX:+UseParallelGC GcAllocationDemo
java -Xms32m -Xmx128m -XX:+UseG1GC GcAllocationDemo
~~~

Trên JDK 21 có thể so Generational ZGC:

~~~bash
java -Xms32m -Xmx128m -XX:+UseZGC -XX:+ZGenerational GcAllocationDemo
~~~

**Cảnh báo:** heap 128 MiB ở ví dụ chỉ là cấu hình thử cho workload nhỏ, **không phải khuyến nghị đủ headroom cho ZGC trong mọi tình huống**. Nếu một JDK/VM không hỗ trợ option đó hoặc thất bại với cấu hình hạn chế, hãy kiểm tra flags/version và tăng ngân sách theo điều kiện thử nghiệm; không suy rằng bản thân thuật toán luôn lỗi.

Với JDK 24+ (khi ZGC generational là chế độ duy nhất), chỉ dùng `-XX:+UseZGC` thay vì giữ cờ `-XX:+ZGenerational` đã loại bỏ.

### Có thể buộc GC đúng số lần không?

**Không.** `System.gc()` không phải cơ chế bảo đảm một lần STW, một lần compact hay một loại GC event cố định. Đừng viết ví dụ giáo trình hứa một số pause, GC-count hoặc milliseconds giống nhau trên mọi máy.

## 15. Bật GC logs và đọc đúng

Đối với workload đã biên dịch, ví dụ:

~~~bash
java -Xms32m -Xmx128m -XX:+UseG1GC -Xlog:gc*:file=gc.log:time,uptime,level,tags GcAllocationDemo
~~~

GC log file `gc.log` có thể chứa các dòng về initialization, pause, region usage và heap transitions tùy bản HotSpot/flags. **Không có stdout GC chính xác bất biến** vì scheduling và allocation behavior phụ thuộc runtime. Cũng có thể chương trình quá ngắn hoặc heap đủ rộng khiến event ít hơn kỳ vọng.

Nên ghi:
- Tên collector thực sự được chọn.
- JVM build và tất cả JVM args.
- Timestamps, GC IDs, phases và durations.
- Heap occupancy before/after GC, frequency, pause maxima/percentiles.
- Concurrent GC cycle work và dấu hiệu allocation stall/failure.
- G1: young/mixed/full events, remembered-set/ref-processing phases nếu cần.
- ZGC/Shenandoah: phase/concurrent work/stalls theo tags/format của bản JDK.

**Một dòng `Pause Young` trong G1 là hoạt động bình thường**, không mặc định là sự cố. **Full GC liên tục**, allocation stalls hoặc các lần pause kéo dài bất thường trong SLO mới là dấu hiệu đáng điều tra.

### Rotation logs khi chạy lâu

Ví dụ với HotSpot unified logging (điều chỉnh theo môi trường):

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -Xmx512m -XX:+UseG1GC GcAllocationDemo
~~~

Kiểm tra cú pháp các decorators/rotation options theo bản JDK. Log GC có thể lớn, cần định nghĩa retention và quyền truy cập; không ghi vô hạn lên ổ đĩa production.

## 16. JFR, jcmd và các số liệu cần thu

Để thấy bức tranh rộng hơn GC pauses, dùng **JFR (Java Flight Recorder)** và các diagnostics của HotSpot. Ví dụ lệnh tương tác với một **Java process đang chạy**, thay `PID` bằng PID thật trước khi thực thi:

~~~bash
jcmd PID VM.flags
jcmd PID GC.heap_info
jcmd PID JFR.start name=GCStudy settings=profile duration=60s filename=gc-study.jfr
jcmd PID JFR.check
~~~

Đây là cú pháp minh họa với tên process PID cần thay, **không** phải command literal PID. Tên diagnostics và cách cung cấp arguments có thể khác nhau giữa JDK builds.

Một cách khác là khởi động recorder ngay từ đầu (JDK hỗ trợ):

~~~bash
java -XX:StartFlightRecording=filename=gc-study.jfr,duration=60s,settings=profile -Xmx512m GcAllocationDemo
~~~

Những lệnh trên có thể ghi file JFR lớn và chứa dữ liệu ứng dụng; bảo vệ quyền truy cập giống các diagnostic artifacts khác. Recording duration 60s có thể dài hơn thời gian ứng dụng minh họa chạy, nên **không hứa recording đầy đủ 60s** nếu process kết thúc sớm.

Khi nghi **object retention/leak** thay vì pause problem, có thể xem histogram:

~~~bash
jcmd PID GC.class_histogram
~~~

Hoặc heap dump khi đã đánh giá ảnh hưởng đến process:

~~~bash
jcmd PID GC.heap_dump filename=gc-study.hprof
~~~

**Cảnh báo:** class histogram và heap dump có thể gây high impact/pause, và heap dump có thể chứa secrets/PII. Không thu/sao chép trên production nếu chưa có quyền và kế hoạch xử lý dữ liệu.

### Metric nào trả lời câu hỏi gì?

| Công cụ/nguồn | Trả lời tốt | Không đủ để kết luận |
| --- | --- | --- |
| GC unified logs | Pause events, heap transitions, GC phase metrics | Request p99, CPU throttling và toàn bộ native memory |
| JFR | GC, allocation samples, threads, CPU/runtime events theo cấu hình | Không phải mọi event đều được bật/sampled 100% |
| jcmd GC.heap_info | Heap trạng thái hiện tại | Retained owner graph, p99 |
| Class histogram | Count/bytes theo runtime class | Ai giữ object còn reachable |
| Heap dump + dominator | Retainers/paths to GC roots | Latency/time spent trong requests |
| Service metrics/tracing | Successful RPS, p99, errors, queue depth | GC algorithm root cause nếu chỉ đo service |
| Container/OS metrics | CPU quota, throttling, RSS/OOM killer | Phân biệt heap/native/GC phase nếu đứng riêng |
| Load-testing tool | SLO tại offered load cố định | Hiệu năng production nếu traffic model không thực |

**Cần tương quan cùng timeline**: một GC pause xảy ra lúc 10:00:03 có gây request spikes không, hay spikes tới từ DB/network/CPU throttling ở cùng cửa sổ?

## 17. Thực nghiệm lựa chọn GC có kiểm soát

Một quy trình A/B đáng tin:

**Bước 1 — Xác định ràng buộc:** workload, API SLA, p99/p99.9, desired throughput, error budget, CPU quota, RAM/RSS budget, peak traffic và thời gian tải kéo dài.

**Bước 2 — Chạy baseline:** dùng collector mặc định hoặc collector production, ghi version JDK, heap flags, CPU limits, traffic distribution, GC logging/JFR. Đo sau warmup.

**Bước 3 — Chỉ thay một yếu tố chính:** thử Parallel, G1, ZGC hoặc Shenandoah (nếu có hỗ trợ), giữ nguyên ứng dụng, tập dữ liệu, offered load và CPU/memory budget.

**Bước 4 — Test nhiều mức tải:** thường tải thấp, tải mục tiêu, peak và burst. Chạy đủ lâu để thấy aging/old-gen cycles, cache growth và các concurrent GC cycles.

**Bước 5 — Thu cả phân phối:** RPS, latency p50/p95/p99/p99.9, error rate, GC pause histogram, GC CPU, total process CPU, throttling, RSS, heap after GC, allocation stalls.

**Bước 6 — Lặp runs:** warmup/JIT, CPU frequency, cache/cgroup sharing và GC scheduling có thể gây nhiễu. Một lần chạy đẹp không đủ kết luận.

**Bước 7 — Chọn theo constraint:** loại mọi cấu hình vi phạm SLO/budget; trong số còn lại, so tổng chi phí và độ ổn định.

**Bước 8 — Canary production:** kiểm tra với traffic thật, cảnh báo CPU/GC/OOM, rollback plan và bảo đảm diagnostic logs không vượt disk budget.

Một **Pareto frontier** hữu ích hơn “GC tốt nhất”: một cấu hình có throughput cao hơn nhưng p99 tệ hơn có thể không *dominate* cấu hình khác; tùy SLA, mỗi cấu hình phù hợp mục tiêu khác nhau.

### Tránh phép so sánh thiên lệch

- Không để Parallel chạy với `-Xmx=8g` còn ZGC bị giới hạn `-Xmx=512m` rồi kết luận collector nào tốt hơn.
- Không lấy G1 sau warmup so với ZGC ngay lần chạy đầu.
- Không chỉ so trên máy local nhiều cores khi production container chỉ có 1 CPU quota.
- Không chỉ xem average latency nếu business SLO là p99.
- Không chỉ xem GC pause time mà quên throughput và total CPU.
- Không chỉ xem heap usage khi container OOM bởi direct buffers, stacks hoặc metaspace.
- Không dùng synthetic allocation benchmark như bằng chứng đủ cho data access/database workload.

## 18. Phân tích kết quả bằng một ma trận giả định

Bảng dưới đây là **số giả định để học cách ra quyết định**, không phải benchmark thật hay số liệu của bất kỳ JVM nào:

| Chỉ số tại offered load cố định | Parallel | G1 | ZGC |
| --- | ---: | ---: | ---: |
| Successful throughput | 2.300 req/s | 2.180 req/s | 2.050 req/s |
| Application p99 latency | 240 ms | 115 ms | 78 ms |
| Total process CPU | 2,8 cores | 3,1 cores | 3,7 cores |
| RSS | 2,1 GiB | 2,5 GiB | 3,0 GiB |
| Full GC / stalls | Không quan sát trong window | Không quan sát | Không quan sát |

Tùy ràng buộc:
- **Batch job không cần low latency:** Parallel có thể tốt nếu jobs/s là mục tiêu chính.
- **API p99 phải dưới 120 ms, CPU ≤3,5 cores, RSS ≤2,8 GiB:** G1 là **ứng viên đáp ứng ví dụ**; Parallel vượt p99 và ZGC vượt CPU/RSS.
- **API p99 dưới 90 ms, CPU ≤4 cores, RSS ≤3,5 GiB:** ZGC có thể là ứng viên trong bảng giả định, nhưng cần thêm test ổn định và peak.
- **Nếu tất cả đều vượt budget ở peak:** không nên ép chọn một GC; cần giảm allocation/retention, scale out, đổi heap/quota hoặc xem lại SLO/cấu trúc.

Đây là bài tập **đọc ma trận đa mục tiêu**. Không lấy số minh họa làm khuyến nghị mua CPU/RAM hay dự đoán hiệu năng của G1/ZGC thực tế.

## 19. Các nguyên nhân thường quan trọng hơn đổi GC

### Tạo object quá nhiều

Autoboxing, intermediate collections, serializers, regex/JSON objects, string concatenation patterns và temporary buffers có thể tăng allocation rate. Dùng JFR allocation profiling, benchmarks hợp lệ và tối ưu ở điểm nóng để giảm công việc của mọi collectors.

### Retention/caches quá lớn

Cache không eviction, long-lived collections, listener registrations, thread locals và large payload references có thể giữ live heap gần `-Xmx`. Collector nào cũng phải giữ objects còn reachable. Dùng heap dump + dominator tree để tìm owners.

### CPU throttling trong container

Nếu cgroup thường xuyên throttle CPU, collector concurrent có thể không hoàn thành marking đủ nhanh hoặc làm tăng queueing trong request processing. Phải điều chỉnh quota, concurrency, GC selection và ứng dụng; không giải quyết chỉ bằng `MaxGCPauseMillis`.

### Too many threads / native memory

Nhiều thread stacks, direct buffers và metaspace có thể đẩy RSS vượt memory quota dù Java heap còn rảnh. Đo native memory/OS metrics, cân nhắc thread management và container limits; đừng chỉ tăng heap.

### Large/huge allocations

G1 có thể xử lý **humongous objects** khác object nhỏ, gây áp lực contiguous regions và headroom. Giảm temporary large buffers hoặc tổ chức dữ liệu khác có thể hiệu quả hơn đổi collector. Nhưng đừng tự cắt arrays thành chunks nếu điều đó gây nhiều copies và phức tạp ứng dụng mà chưa đo.

## 20. Lỗi thường gặp khi lựa chọn GC

| Nhận định | Vì sao không chính xác |
| --- | --- |
| “ZGC có low pause nên luôn nhanh nhất.” | CPU concurrent, memory headroom và barrier overhead có thể giảm throughput. |
| “Parallel ưu tiên throughput nên mọi batch job đều phải dùng.” | Depends on heap/live set/cores; mặc định hoặc G1 cũng có thể tốt. |
| “G1 MaxGCPauseMillis=50 nghĩa là mọi pause ≤50 ms.” | Đó là soft target, không phải deadline cứng. |
| “GC p99 pause=10 ms nên API p99 ≤10 ms.” | Request latency còn application work, I/O, queueing và concurrent CPU. |
| “STW fraction 1% nghĩa ứng dụng throughput đạt 99%.” | Chỉ là available-time approximation, không tính concurrent GC/cost khác. |
| “Heap -Xmx=2g thì container 2g đủ.” | RSS bao gồm metaspace, code cache, stacks, direct buffers, GC native overhead. |
| “RSS cao chứng minh leak Java heap.” | Có native/committed memory hoặc caching pages, cần phân tách. |
| “Ít GC event nghĩa collector tốt.” | Event hiếm nhưng rất dài vẫn có thể gây p99 spikes. |
| “GC chạy concurrent là không dừng ứng dụng bao giờ.” | Vẫn có short pauses/safepoints/handshakes theo collector. |
| “CPU host còn 50% rảnh nghĩa container không bị throttle.” | Container quota có thể giới hạn độc lập với host idle cores. |
| “Giảm -Xmx luôn tiết kiệm RAM không ảnh hưởng latency.” | Có thể tăng GC frequency và allocation stalls/OOME. |
| “Tăng -Xmx luôn giảm latency.” | Có trade-offs về footprint, live set, collector scheduling. |
| “Một benchmark 30 giây đủ cho mọi long-lived workload.” | Chưa thấy old-gen cycles, aging, leak, peak behavior. |
| “Dùng cùng flags ZGC cho JDK 17, 21, 24, 26.” | Generational mode/options thay đổi qua releases. |
| “Shenandoah có trên mọi HotSpot distribution.” | Availability phụ thuộc build/vendor/version. |
| “G1 là default nên luôn tối ưu nhất.” | Default cân bằng, không phải tối ưu cho mọi workload cụ thể. |
| “Một lần System.gc() đo GC rất khách quan.” | Không hứa loại/time GC, còn ảnh hưởng warmed state và collector policies. |
| “GC logs tự cho biết throughput business.” | Cần service counters/completed work và latency metrics riêng. |
| “Tối ưu GC bằng một flag cùng lúc với đổi code/heap.” | Không biết thay đổi nào tác động; so sánh không kiểm soát. |
| “Pause trung bình giảm đủ để đạt p99.” | Tail latency phải đo distribution; mean có thể che outliers. |

## 21. Câu hỏi tự kiểm tra

**1.** Nếu tổng STW time là 0,5 giây trong 10 giây, có thể tuyên bố throughput ứng dụng 95% không?

**Đáp án:** Không. Có thể nói STW pause fraction khoảng 5%; throughput ứng dụng cần đo successful work/s, còn concurrent GC cũng dùng CPU.

**2.** p99 GC pause và p99 HTTP response latency có phải cùng chỉ số không?

**Đáp án:** Không. Chúng đo hai population khác nhau; cần correlation và request SLO.

**3.** Vì sao ZGC có thể dùng nhiều CPU hơn nhưng có pauses thấp hơn?

**Đáp án:** Nhiều GC work được làm concurrent, cùng barrier/coordination overhead và memory bandwidth; giảm work trong STW có thể đổi lấy work lúc mutators đang chạy.

**4.** Khi một container chỉ có 1 vCPU, có nên mặc định chọn GC nhiều concurrent threads không?

**Đáp án:** Không. Cần đo CPU competition/throttling và application p99 trước; có thể throughput hoặc latency bị ảnh hưởng.

**5.** Có thể đặt `-Xmx=4g` trong container RAM limit 4 GiB mà bảo đảm không bị OOMKilled không?

**Đáp án:** Không. Ngoài Java heap còn native memory, metaspace, code cache, thread stacks và runtime overhead.

**6.** Vì sao G1 pause-time target không được coi là SLA?

**Đáp án:** `MaxGCPauseMillis` là heuristic goal, không phải giới hạn bắt buộc cho mọi event.

**7.** Chọn Parallel hay ZGC cho một batch không có latency SLO?

**Đáp án:** Đo throughput/CPU/RSS trên workload thật; Parallel là một ứng viên throughput-first nhưng không bảo đảm thắng.

**8.** Tăng heap có thể gây tác động trái chiều nào?

**Đáp án:** Có thể giảm collection frequency nhưng tăng footprint/density cost, thay đổi collector behavior và che retention.

**9.** Live-set lớn nhưng allocation rate thấp có thể khiến GC đắt không?

**Đáp án:** Có. Collector vẫn cần scan/copy/mark nhiều live objects theo thuật toán, cần headroom.

**10.** Nên lấy metrics gì khi nghi allocation stalls?

**Đáp án:** GC logs với stall/failure markers, heap before/after, allocation rate, concurrent GC timing, CPU quota và free headroom.

**11.** Khi nào dùng heap dump thay vì chỉ GC log?

**Đáp án:** Khi cần tìm object graph retention, dominator/GC-root paths hoặc nghi leak. Heap dump có chi phí và chứa dữ liệu nhạy cảm.

**12.** Mục tiêu “request p99 <100 ms” có thể chứng minh chỉ bằng p99 GC pause <10 ms không?

**Đáp án:** Không. Phải đo end-to-end p99 tại tải mục tiêu và đối chiếu bottlenecks khác.

**13.** JDK 21 bật generational ZGC bằng flag nào?

**Đáp án:** `-XX:+UseZGC -XX:+ZGenerational` trên JDK 21 hỗ trợ. Từ JDK 24, không dùng `ZGenerational` vì non-generational mode đã loại bỏ.

**14.** Vì sao cùng một collector trên JDK 17 và JDK 25 vẫn phải benchmark lại?

**Đáp án:** GC algorithms, heuristics, flags, JIT/compiler, VM defaults và container awareness có thể thay đổi.

**15.** Tập thử nghiệm có throughput cao nhưng errors 5% có tốt không?

**Đáp án:** Không nếu SLO error budget thấp hơn. Completed successful work và correctness mới có ý nghĩa.

## 22. Bản đồ ghi nhớ

~~~text
                 APPLICATION GOALS / SLO
                           |
         +-----------------+------------------+
         |                 |                  |
      THROUGHPUT         LATENCY          RESOURCE BUDGET
      requests/s          p99/p99.9         CPU + RAM/RSS
         |                 |                  |
         +-----------------+------------------+
                           |
                     BASELINE DEFAULT GC
                           |
                   MEASURE WORKLOAD
             GC logs + JFR + service metrics
                  + container/OS metrics
                           |
               +-----------+-----------+
               |                       |
         Throughput first          Low latency first
               |                       |
         Parallel candidate        G1 / ZGC / Shenandoah
               |                       |
               +-----------+-----------+
                           |
                    HEADROOM / LIVE SET
                    ALLOCATION / GC CPU
                    ERRORS / STALLS / RSS
                           |
                   RUN CONTROLLED A/B
                           |
                   DOES IT MEET ALL SLOs?
                     /              \
                    NO              YES
                    |                |
             TUNE / FIX /         CANARY + MONITOR
             TRY ANOTHER
                           |
                  OPTIMIZE THE SYSTEM,
                 NOT JUST ONE GC NUMBER
~~~

**Điểm cốt lõi:** chọn GC là **bài toán nhiều mục tiêu**, không phải tối thiểu hóa một pause đơn lẻ. Throughput, tail latency, CPU quota, RSS, live set và heap headroom tác động lẫn nhau. **Parallel** thường là ứng viên throughput-first, **G1** hướng tới cân bằng, **ZGC/Shenandoah** là ứng viên low-pause khi có hỗ trợ, nhưng kết quả phải được xác nhận bằng workload và SLO thực tế. Đo đạc, giới hạn ngân sách và so sánh có kiểm soát đáng tin hơn bất kỳ lời hứa “collector nhanh nhất” nào.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — Available Collectors, hướng dẫn chọn GC](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html).
- [Oracle Java SE 21 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector-tuning.html).
- [Oracle Java SE 21 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html).
- [Oracle Java SE 21 — HotSpot GC Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/).
- [Oracle Java SE 21 — The java Command, GC logging and JVM flags](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle Java SE 21 — jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [OpenJDK JEP 439 — Generational ZGC](https://openjdk.org/jeps/439).
- [OpenJDK JEP 474 — Generational ZGC by Default](https://openjdk.org/jeps/474).
- [OpenJDK JEP 490 — Remove Non-Generational ZGC](https://openjdk.org/jeps/490).
- [OpenJDK JEP 189 — Shenandoah GC](https://openjdk.org/jeps/189).
- [Java Flight Recorder — Java SE 21 documentation](https://docs.oracle.com/en/java/javase/21/jfapi/).
