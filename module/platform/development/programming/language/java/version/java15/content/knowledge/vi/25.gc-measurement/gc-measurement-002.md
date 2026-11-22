# Warm-up, thời gian đo và độ ổn định của kết quả khi đo GC trong Java 15+

## 1. Mục tiêu của bài học

Khi so sánh hiệu năng ứng dụng Java hoặc các bộ thu gom rác (*garbage collectors* — GC), bạn có thể chạy chương trình hai lần và nhận những con số rất khác nhau dù không sửa một dòng code. Nguyên nhân thường không chỉ do GC: JVM có **class loading**, **JIT compilation**, profiling và tối ưu hóa lại code, khởi tạo cache, heap expansion, thay đổi object lifetime, điều tiết CPU, can thiệp của hệ điều hành, I/O và tải từ các tiến trình khác.

Vì vậy, ba câu hỏi cần trả lời trước khi nói “GC A nhanh hơn GC B” là:

1. **Warm-up đủ chưa?** Chương trình đã tiến vào trạng thái làm việc đại diện cho tải cần khảo sát, hay số liệu vẫn chủ yếu phản ánh quá trình khởi động/JIT/class loading?
2. **Đo trong bao lâu?** Khoảng đo có chứa đủ GC cycles, các giai đoạn tải khác nhau và những sự kiện hiếm quan trọng, hay chỉ là một lát cắt ngẫu nhiên?
3. **Kết quả có ổn định không?** Những lần chạy độc lập có tái lập được xu hướng, phân phối độ trễ và throughput, hay chênh lệch giữa các lần đo lớn hơn lợi ích bạn đang muốn chứng minh?

Đây là bài **“Warm-up, thời gian đo và độ ổn định của kết quả”**, thuộc chủ đề cha **“Đo lường GC”** của Java 15. Trọng tâm là **thiết kế phép đo đáng tin**, không phải tối ưu một cờ GC cụ thể.

Sau bài, bạn có thể:

- Tách **startup**, **warm-up**, **steady-state measurement** và **cool-down/cleanup** thành các pha rõ ràng.
- Phân biệt thời gian **GC pause**, thời gian **concurrent GC cycle**, **wall-clock response time**, **throughput**, **allocation rate** và **safepoint-related stalls**.
- Chọn độ dài vòng đo, cửa sổ quan sát, tải ổn định và điều kiện kết thúc đo theo yêu cầu SLO, thay vì dùng một “số giây chuẩn” cho mọi chương trình.
- Tính/đọc **mean, median, P95, P99, max, standard deviation và hệ số biến thiên (CV)** theo đúng ý nghĩa thống kê, tránh diễn giải percentile từ quá ít mẫu.
- Chạy **nhiều lần đo độc lập**, phân tích độ biến thiên giữa process runs và nhận diện môi trường nhiễu.
- Biết khi nào dùng **JMH** cho microbenchmark, khi nào dùng **load test + GC logs + JFR** cho đánh giá GC của hệ thống.
- Biên dịch/chạy ví dụ Java 15-compatible về warm-up và đo thời gian, tự nhìn thấy các con số có thể biến động.
- Áp dụng công cụ, API và hướng dẫn **vẫn phù hợp trên các bản JDK hiện đại**, không dùng GC logging cũ đã lỗi thời.

**Bối cảnh phiên bản:** Java 15 có ZGC ở mức production (JEP 377); các HotSpot GC và JIT tiếp tục thay đổi ở các JDK sau. Từ **JDK 24, ZGC chỉ còn chế độ generational** (JEP 490), nên không so sánh hai JDK khác thế hệ rồi tuyên bố mọi khác biệt đều do cấu hình heap. Phép đo phải ghi rõ **JDK vendor, build, GC mode, flags và môi trường**. Các nguyên tắc warm-up, lặp lại và độ ổn định trong bài vẫn áp dụng cho G1, ZGC và các collector HotSpot được hỗ trợ hiện nay.

## 2. Đầu tiên phải xác định *đang đo cái gì*

Không có một con số “thời gian GC” duy nhất đủ đại diện mọi hiệu năng ứng dụng:

| Chỉ số | Câu hỏi được trả lời | Đơn vị thường dùng | Sai lầm dễ gặp |
| --- | --- | --- | --- |
| **GC pause duration** | JVM dừng ứng dụng để thực hiện một pha GC trong bao lâu? | µs/ms | Đồng nhất toàn bộ GC cycle với thời gian ứng dụng bị dừng |
| **Sum of pauses** | Trong một GC event/cycle, tổng thời gian các pha dừng ứng dụng là bao nhiêu? | ms | Chỉ xem pause dài nhất mà bỏ qua nhiều pause cộng dồn |
| **Concurrent GC cycle duration** | Collector làm việc trong bao lâu, kể cả pha đồng thời với ứng dụng? | ms/s | Coi toàn bộ khoảng này là stop-the-world |
| **GC frequency/count** | Có bao nhiêu collections/cycles trong cửa sổ? | sự kiện/giây | Cho rằng ít GC hơn luôn tốt hơn |
| **Application throughput** | Xử lý bao nhiêu yêu cầu/đơn vị công việc? | req/s, ops/s | Tăng throughput bằng cách chấp nhận P99 latency vượt SLO |
| **Response latency** | Người dùng/consumer chờ mỗi yêu cầu bao lâu? | P50/P95/P99 ms | Tự coi P99 của request chính là P99 của GC pause |
| **Allocation rate** | Ứng dụng cấp phát bao nhiêu bytes object mỗi giây? | MiB/s, GiB/s | Dùng heap growth ròng làm đồng nghĩa gross allocation rate |
| **Live set / heap occupancy** | Có bao nhiêu object sống và heap pressure ra sao? | MiB/GiB | Lấy một snapshot `used` giữa concurrent GC làm live set chính xác |
| **CPU/GC CPU** | Collector lấy bao nhiêu CPU, ảnh hưởng throughput thế nào? | %, CPU-seconds | Bỏ qua CPU quota, throttling hoặc runnable queue |
| **Allocation stalls** | Mutator phải chờ vì chưa có đủ nơi cấp phát? | số lần/ms | Nghĩ GC pause ngắn sẽ loại trừ mọi latency spike |
| **Process/container memory** | Tổng bộ nhớ thực có sát hạn mức không? | MiB/GiB, RSS/cgroup | Cho rằng `-Xmx` bằng toàn bộ memory của tiến trình |

**Ví dụ:** với ZGC, một cycle có thể kéo dài hàng trăm mili giây hoặc hơn vì phần lớn công việc diễn ra đồng thời, nhưng những pause dừng ứng dụng có thể ngắn. Nếu báo cáo nhầm “cycle duration” thành “GC pause”, phép so sánh hoàn toàn sai ý nghĩa.

Ngược lại, pause rất nhỏ không chứng minh response latency luôn thấp: ứng dụng vẫn có thể chậm vì allocation stall, CPU contention, thread scheduling, lock, I/O, network, safepoints hoặc request queueing.

### Chỉ số nào là mục tiêu chính?

- **Độ trễ người dùng:** đo phân phối request latency, đặc biệt P99/P99.9 nếu SLO yêu cầu; liên hệ với GC events theo timeline.
- **Băng thông xử lý:** đo throughput và CPU/GC overhead dưới cùng tải.
- **Độ trễ do GC:** đo GC pauses/sum of pauses bằng GC logs/JFR; phân biệt với concurrent cycle.
- **Chi phí bộ nhớ:** đo heap occupancy, live set, committed/RSS và container limit.
- **Khả năng chịu tải:** đo allocation rate bursts, GC pressure, stalls và failure/recovery.

**Không chỉ dùng một con số.** Một collector có P99 GC pause thấp hơn nhưng tiêu thụ CPU đáng kể hơn vẫn có thể khiến application throughput giảm. Cần nêu rõ thước đo nào được ưu tiên trước khi bắt đầu.

## 3. Warm-up là gì và tại sao Java cần?

**Warm-up** là giai đoạn chạy workload trước khi lấy số liệu chính, nhằm để các cơ chế cần thiết của runtime và ứng dụng đạt trạng thái đại diện cho loại workload sẽ đo.

Trong JVM HotSpot hiện đại, warm-up có thể bao gồm:

1. **Class loading, verification, linking và initialization:** lần đầu đụng tới nhiều class/libraries có chi phí cao hơn những lần sau.
2. **JIT compilation / tiered compilation:** bytecode lúc đầu có thể được diễn giải hoặc biên dịch ở cấp tối ưu khác; các method “hot” được tối ưu theo profiling đã quan sát.
3. **Deoptimization và recompilation:** hiệu năng có thể lại thay đổi khi dữ liệu hoặc nhánh code khác xuất hiện, không phải mọi method chỉ được compile một lần rồi mãi ổn định.
4. **Cache/JVM structures:** nạp cấu hình, khởi tạo pools, regex, serializers, caches, connection pools và các lớp framework.
5. **Heap expansion và GC ergonomics:** trong thời gian đầu heap committed, thế hệ object, remembered-set/card metadata hoặc các heuristics có thể chưa phản ánh trạng thái sau khi hệ thống đã chạy một lúc.
6. **Object age distribution:** ứng dụng ổn định về số request chưa chắc đã ổn định về tỷ lệ object sống lâu, cache retention hoặc promotion.
7. **OS/hardware:** page faults, file-system caches, thread scheduling, JIT code pages, CPU frequency và thermal behavior thay đổi theo thời gian.
8. **Ứng dụng:** các tác vụ định kỳ, cache TTL/eviction, queue growth và batch flush có thể cần nhiều phút hoặc lâu hơn mới xuất hiện.

**Warm-up không phải chỉ chạy một vòng `for` rồi coi mọi thứ đã ổn định.** Trong GC measurement, bạn cần xem **heap live set**, **allocation rate**, **throughput**, **GC frequency/behavior** và **latency distributions** có đại diện cho tải mục tiêu chưa.

### 3.1. Warm-up không phải đo startup

Nếu mục tiêu là **startup latency**, **cold start**, **serverless scale-to-zero** hoặc thời gian JVM sẵn sàng nhận request đầu tiên, startup là **chính đối tượng cần đo**, không được bỏ qua bằng cách warm-up rồi báo “startup đã nhanh”.

Ngược lại, nếu mục tiêu là **steady-state throughput/GC pause** của một backend chạy liên tục, cần loại bỏ startup và xác định rõ thời điểm bắt đầu khoảng đo steady state.

Tài liệu/report tốt thường tách hai kết quả:

```text
Cold-start profile:
    từ JVM/process start → service ready → request đầu

Steady-state profile:
    khởi động → warm-up theo workload → measurement window
```

Không trộn data hai pha rồi đưa ra một trung bình chung mà không mô tả.

### 3.2. Warm-up của GC khác chỉ warm-up JIT

JIT có thể tương đối ổn định nhưng **live set/GC state** chưa ổn định. Ví dụ:

- Một cache tăng dần trong 20 phút mới đạt giới hạn.
- Một queue nhận nhanh hơn xử lý làm retained objects tăng trong 10 phút.
- Một batch job mỗi 5 phút cấp phát spike lớn.
- Một service vừa deploy nhưng lazy initialization chỉ xảy ra với endpoint ít được gọi.
- Một workload có old-generation object lifetime dài hơn vài chu kỳ GC.
- Một ZGC generational workload cần thời gian hình thành thế hệ object và profile tuổi đối tượng phù hợp.

Vì thế **độ dài warm-up phải gắn với chu kỳ vận hành của ứng dụng**, không chỉ số lần gọi method.

### 3.3. Không ép GC bằng `System.gc()` để “warm up”

`System.gc()` là **yêu cầu** explicit GC với semantics/phản hồi phụ thuộc collector, flags và JVM. Nó có thể làm thay đổi hoạt động GC, live-set timing và pause distribution so với service thật.

Nếu production không chủ động gọi explicit GC, đừng dùng `System.gc()` trước mỗi phép đo như một cách “chuẩn hóa” trạng thái. Điều này dễ khiến kết quả không phản ánh thực tế.

Nếu nghiên cứu **explicit GC behavior** là mục tiêu, phải thiết kế một thí nghiệm riêng và khai báo rõ những cuộc gọi đó. Trong ví dụ của bài, không sử dụng `System.gc()`.

## 4. Khi nào được kết thúc warm-up?

Không có quy tắc phổ quát kiểu “warm-up luôn đủ sau 3 giây”, “5 vòng là chuẩn” hay “phải chờ đúng 10 lần GC”.

Một bộ tiêu chí thực hành có thể gồm:

- **Throughput** hoặc thời gian mỗi đơn vị công việc không còn thay đổi có hệ thống theo hướng nhanh lên/chậm đi giữa những cửa sổ liên tiếp.
- **Heap occupancy/live set** đã đạt vùng làm việc mong đợi; cache và các đối tượng dài sống ổn định tương đối.
- **Allocation rate** và phân bố object sizes gần với môi trường mục tiêu.
- **GC behavior** không còn bị chi phối chủ yếu bởi startup, class loading hoặc heap growth ban đầu.
- Các endpoints/tasks quan trọng đã được chạy đủ để lazy initialization và những đường code thường gặp xuất hiện.
- **CPU utilization/quota** đang ở chế độ tải tương tự production; không có thay đổi lớn trong topology hoặc batch arrivals.
- Không có *trend* dài hạn bất thường trong memory usage/queue depth — nếu có, đó có thể là memory leak hoặc workload chưa ổn định, không phải chuyện chỉ “đợi thêm warm-up”.

### 4.1. Theo dõi qua cửa sổ

Ví dụ dùng các cửa sổ liên tiếp:

```text
Warm-up, mỗi cửa sổ 30 giây:

0–30 s     throughput 4.1k req/s, live set tăng, nhiều lazy init
30–60 s    throughput 5.4k req/s, cache tiếp tục tăng
60–90 s    throughput 5.8k req/s, một số GC cycles
90–120 s   throughput 5.7k req/s, live set tương đối phẳng
120–150 s  throughput 5.8k req/s, live set tương đối phẳng

→ Có bằng chứng tốt hơn rằng workload có thể vào pha đo
  (nhưng vẫn cần xét batch job/TTL/traffic cycle dài hơn).
```

Đây là **số liệu minh họa**, không phải tiêu chuẩn bắt buộc. Với hệ thống có job mỗi 10 phút, warm-up 150 giây vẫn không bao phủ chu kỳ đó.

### 4.2. Dùng CV hoặc xu hướng như tín hiệu, không phải phép chứng minh

Có thể tính **hệ số biến thiên** của các cửa sổ thời gian/throughput:

\[
CV = \frac{\sigma}{\mu}\times 100\%
\]

Trong đó \(\mu\) là trung bình và \(\sigma\) là độ lệch chuẩn (với định nghĩa population/sample nhất quán).

CV nhỏ có thể gợi ý **ít biến động tương đối**, nhưng:

- CV nhỏ **không chứng minh** không có trend dài hạn hoặc bias. Một hệ thống memory leak chậm có thể có CV nhỏ trong các cửa sổ ngắn.
- CV lớn có thể là dấu hiệu của **GC/jitter không ổn định**, nhưng cũng có thể do workload cố ý burst hoặc small sample.
- CV của **latency** không thể thay thế phân tích tail P99.
- Không có ngưỡng CV 5%/10% bắt buộc đúng cho mọi loại hệ thống.
- Các điểm đo kế tiếp **có thể tự tương quan** (*autocorrelation*), nên tính một confidence interval đơn giản như dữ liệu độc lập có thể tạo độ tin cậy giả.

Một định nghĩa “ổn định” hữu ích cần xét **trend + dispersion + yêu cầu workload/SLO**, không chỉ một threshold duy nhất.

## 5. Thời gian đo: đo ngắn quá có thể dẫn tới kết luận sai

Chọn **measurement window** phải bắt đầu từ tính chất của sự kiện bạn muốn quan sát:

- Nếu chỉ muốn kiểm tra method hoạt động và xem số liệu minh họa, vài giây có thể đủ cho demo.
- Nếu muốn so sánh GC pause P99, cần **đủ số lượng GC pause events** để percentile có ý nghĩa.
- Nếu muốn đo tác động của cache TTL 15 phút, cửa sổ đo 30 giây không đủ.
- Nếu muốn đo burst traffic mỗi giờ, cần chứa các burst ấy hoặc có kịch bản tải mô phỏng phù hợp.
- Nếu cần tail latency cho một service lớn, phải có **đủ request samples** ở mức concurrency và distribution mục tiêu.
- Nếu GC cycle rất thưa, một khoảng đo chỉ có 1–2 chu kỳ không cho phân phối đáng tin của GC pause.
- Nếu tải và allocation thay đổi theo ngày, cần phân tách các giờ/cấp tải hoặc đo có điều khiển từng workload profile.

**Số mẫu sự kiện quan trọng hơn chỉ số giây đồng hồ.** Một phép đo 10 phút với 2 GC events chưa phù hợp để tuyên bố “P99 GC pause là X ms”. Ngược lại, một workload có hàng trăm GC cycles trong 10 phút có thể đưa ra nhiều thông tin, nhưng vẫn cần nhiều process runs để kiểm tra tính tái lập.

### 5.1. Fixed-time vs fixed-work

| Cách đo | Ý nghĩa | Có thể bị đánh lừa bởi |
| --- | --- | --- |
| **Fixed work**: mỗi round 40.000 allocations | Thời gian thực hiện một lượng công việc cố định | Round quá ngắn, startup/JIT và OS noise chi phối |
| **Fixed time**: xử lý tối đa công việc trong 30 giây | Throughput trong khoảng thời gian cố định | Tải/queue/latency thay đổi, GC cycles phân bổ khác nhau |
| **Open-loop load test**: gửi yêu cầu theo rate độc lập với response | Phản ánh cách hệ thống xử lý tải đến và queueing | Generator không giữ được rate, overload và dropped requests |
| **Closed-loop load test**: mỗi client gửi tiếp sau response | Đo throughput/latency dưới số clients đồng thời | **Coordinated omission**: khi server chậm, generator gửi ít request hơn, có thể báo tail latency thấp giả |

Để so sánh GC của service, cần khai báo kiểu load generator và xử lý **coordinated omission** nếu đánh giá latency của workload có arrival rate. Không suy ra “tốt nhất” từ một fixed-work microbenchmark rồi áp dụng cho hệ thống có queue và network I/O.

### 5.2. Ranh giới của measurement window phải rõ

Ví dụ một run:

```text
[process start]
      |
      | startup / load configuration
      v
[ready]
      |
      | WARM-UP (có tải, không tính vào thống kê steady-state chính)
      v
[measurement start marker / timestamp]
      |
      | MEASURE: requests, GC pauses, allocations, CPU, RSS
      |
      | workload được giữ theo kịch bản
      v
[measurement end marker / timestamp]
      |
      | write reports / cool down / cleanup
      v
[process end]
```

Tốt nhất dùng chung timeline để ghép **GC log/JFR events** với **request timestamps** và CPU/cgroup metrics. Tránh gom GC events của warm-up vào kết luận steady state mà không phân loại.

### 5.3. `System.nanoTime()` và wall clock

- `System.nanoTime()` phù hợp để đo **elapsed time** trong một process. Giá trị gốc không mang ý nghĩa thời gian lịch; chỉ lấy **chênh lệch** `end - start`.
- `System.currentTimeMillis()` dùng cho thời gian lịch/log một cách gần đúng, nhưng không phải lựa chọn chính để đo operation rất ngắn; wall clock có thể bị điều chỉnh.
- Khi liên kết dữ liệu từ nhiều nguồn, cần timestamp và đồng bộ clock/timezones rõ ràng. Một microbenchmark chỉ in elapsed time vẫn chưa đủ để khớp các GC events và requests.
- `nanoTime` không “chống mọi nhiễu”: lịch chạy thread, OS scheduling, CPU contention, JIT và GC vẫn nằm trong elapsed time của operation.

Nếu thao tác ngắn hơn độ phân giải/khoảng nhiễu có ý nghĩa, hãy **gộp nhiều đơn vị công việc trong một sample** hoặc dùng **JMH**; đừng tin thời gian một lần gọi method vài nanosecond từ code thủ công.

## 6. Lặp phép đo, nhiều JVM forks và độ ổn định

Một quy trình tốt cần phân biệt:

1. **Warm-up iterations** bên trong một JVM process.
2. **Measurement iterations** sau warm-up, cũng trong JVM đó.
3. **Independent runs/forks**: khởi động **JVM process mới** và lặp lại cùng cấu hình.
4. **Environment repetitions**: nếu quan trọng, lặp trên nhiều máy/cgroup/JDK builds đại diện.

**Chạy một vòng measurement 100 lần trong cùng JVM không tương đương khởi động JVM mới 100 lần.** Các vòng cùng process chia sẻ JIT code, heap state, cache, class loading, memory pressure và một số nhiễu hệ thống.

Một test plan:

```text
Config A (collector/heap/flags được cố định):
  Fork 1: startup → warmup → 10 measurement windows → cleanup
  Fork 2: startup → warmup → 10 measurement windows → cleanup
  Fork 3: startup → warmup → 10 measurement windows → cleanup

Config B:
  Fork 1: startup → warmup → 10 measurement windows → cleanup
  Fork 2: startup → warmup → 10 measurement windows → cleanup
  Fork 3: startup → warmup → 10 measurement windows → cleanup
```

Số 3 forks và 10 windows ở đây là **kế hoạch minh họa**, không có một số lượng tiêu chuẩn cho mọi workload. Chọn số forks/windows dựa vào chi phí phép đo, độ biến thiên đang thấy và độ lớn hiệu ứng muốn phát hiện.

### 6.1. Tránh đo cấu hình A trước B trong môi trường có xu hướng thay đổi

Nếu luôn chạy A vào lúc máy rảnh, rồi chạy B sau khi CPU/temperature/background traffic tăng, chênh lệch có thể đến từ môi trường. Với phép so sánh collector hoặc flags:

- Chạy trên phần cứng và giới hạn tài nguyên tương đương.
- **Luân phiên hoặc randomize thứ tự A/B** giữa các runs.
- Dùng **mỗi run một JVM mới**, nếu cần đo ảnh hưởng clean process state.
- Giữ workload definition, request mix, concurrency, payload sizes, data set, heap và CPU quota nhất quán.
- Ghi lại phiên bản JDK, build, GC mode, kernel/OS, cgroup limits và môi trường.
- Không để hai phép benchmark nặng chạy đồng thời trên cùng tài nguyên rồi xem số liệu độc lập.

**Nếu thay nhiều yếu tố cùng lúc**, không kết luận yếu tố nào đã tạo cải thiện. Ví dụ đồng thời nâng JDK, tăng heap, đổi collector và thay business code sẽ khiến quan sát khó quy nguyên nhân.

### 6.2. Đừng chỉ giữ run tốt nhất

Một lỗi reporting phổ biến:

```text
Run 1: 100 ms
Run 2: 210 ms
Run 3: 98 ms

Chọn run tốt nhất = 98 ms và báo "latency = 98 ms".
```

Đó là cách chọn có bias. Báo cáo cần thể hiện **phân phối các runs**, phương pháp tổng hợp và sự không chắc chắn. Nếu run 2 khác thường, hãy **tìm nguyên nhân** (CPU throttling? JIT? GC? I/O? workload?) trước khi loại bỏ. Không âm thầm xóa outliers chỉ vì chúng làm kết quả xấu.

## 7. Thống kê và điều kiện để nói “kết quả ổn định”

### 7.1. Trung bình, median, percentile và max

Với thời gian các rounds `t1, t2, ..., tn`:

- **Mean**: trung bình cộng; nhạy với outliers/tail.
- **Median / P50**: phần giữa phân phối, ít bị outlier chi phối hơn mean.
- **P95/P99**: ngưỡng mà 95%/99% samples không lớn hơn theo quy tắc tính percentile đã chọn; phải ghi thuật toán và số mẫu nếu cần so sánh chính xác.
- **Max**: giá trị lớn nhất đã quan sát; phụ thuộc số mẫu và thời gian đo.
- **Standard deviation**: độ phân tán theo đơn vị gốc.
- **CV**: độ phân tán tương đối so với mean, khi mean dương và thích hợp.

**Không thể suy tail percentile có độ tin cậy cao từ quá ít samples.** Chẳng hạn với **12 rounds**, cách tính *nearest-rank P95* cho index `ceil(0.95×12) = 12`, tức chính là **max**. Nó không cho ta một phép ước lượng P95 của workload dài hạn tốt.

Nếu muốn đánh giá **GC pause P99**, hãy đo **nhiều GC pause events thực** trên nhiều windows/runs, không lấy P99 của 12 round runtimes rồi gán nhãn GC pause P99.

### 7.2. Quy tắc thống kê phải chỉ rõ đơn vị mẫu

Một **GC pause event** khác một **request**, khác một **measurement window**, và khác một **JVM fork**.

Ví dụ:

- “P99 request latency” → tính trên **từng request** được đo theo tải phù hợp.
- “P99 GC pause duration” → tính trên **những pause events** được công cụ ghi lại.
- “Median runtime per batch” → tính trên **các lần thực hiện batch**.
- “Median of fork means” → là thống kê **giữa các forks**, không bằng P50 của mọi request gộp.

Một biểu đồ chỉ ghi “P99 = 12 ms” không nêu nguồn mẫu, khoảng đo, đơn vị và phương pháp có thể gây hiểu lầm.

### 7.3. Độ ổn định không chỉ là CV thấp

Có thể xem nhiều yếu tố:

| Tín hiệu | Có lợi cho kết luận ổn định | Cần điều tra |
| --- | --- | --- |
| Latency theo thời gian | Không có drift dai dẳng, các windows gần profile kỳ vọng | Tăng dần qua các windows |
| Throughput | Duy trì mục tiêu dưới tải kiểm soát | Thay đổi mạnh cùng workload |
| Heap live set | Có baseline gần ổn định sau warm-up | Tăng liên tục vì cache/queue/leak |
| GC pauses | Distribution tương đối nhất quán, tail được quan sát đủ | Một vài sự kiện dài bất thường liên quan tải/OS |
| CPU quota/throttling | Tương đương giữa các runs | Một run bị throttled mạnh |
| Independent forks | Kết luận A/B lặp lại được | Mỗi fork cho một “người thắng” khác |
| Confidence interval | Độ không chắc chắn nhỏ tương đối so với hiệu ứng muốn phát hiện | Khoảng chồng lấp lớn, sample chưa đủ |
| JIT/class loading | Các pha đo không còn chịu startup effect chủ yếu | Còn recompilation/lazy init kéo dài |

**Không dùng kết luận “GC nhanh hơn 1%” nếu chênh lệch giữa runs lớn 10–20% mà không có phân tích thống kê phù hợp.** Với dữ liệu tương quan theo thời gian, phương pháp uncertainty cần cân nhắc block/window/fork như đơn vị lặp độc lập, thay vì xem mọi sample cùng process là độc lập tuyệt đối.

### 7.4. Cần báo cáo cả negative result

Nếu chạy đủ mà chênh lệch vẫn không tái lập, kết luận đúng có thể là:

> “Chưa tìm thấy bằng chứng đủ mạnh để phân biệt hai cấu hình trong workload và giới hạn đo đã nêu.”

Đừng ép một “cấu hình chiến thắng” chỉ vì phải đưa ra câu trả lời. Ghi rõ noise, số runs, confidence/variance và những điều chưa được đo.

## 8. Thu thập dữ liệu GC bằng công cụ hiện hành

### 8.1. Unified GC Logging bằng `-Xlog`

HotSpot Java 15+ sử dụng cơ chế **Unified Logging**. Ví dụ:

```bash
java -XX:+UseZGC -Xms64m -Xmx128m \
  '-Xlog:gc*:file=gc.log:time,level,tags' \
  GcWarmupMeasurementDemo
```

Dấu `\` ở lệnh trên là cách nối dòng của shell Unix. Trên Windows PowerShell, dùng một dòng như ví dụ ở phần chạy chương trình.

Trong một service, các mức log và file rotation cần được cân nhắc để không gây quá nhiều I/O. Dữ liệu log thay đổi theo collector/JDK version; khi phân tích:

- Xác định **collector/GC mode thực tế** và JVM build.
- Xem **GC cycle start/end**, pause phases, heap usage, allocation pressure/stalls nếu collector ghi.
- Chỉ lấy các events có timestamp thuộc **measurement window** đã đánh dấu.
- Phân biệt **concurrent** events và **stop-the-world pause** events.
- Tính pause distribution trên events thích hợp, không lấy tổng độ dài của toàn bộ concurrent cycle.
- Đối chiếu GC timeline với response P99 spikes và CPU/cgroup metrics.

**Không sử dụng flags logging GC cũ** như `-XX:+PrintGCDetails` làm khuyến nghị cho HotSpot hiện đại; `-Xlog` là API/CLI hiện hành.

### 8.2. Java Flight Recorder (JFR)

**JFR** ghi sự kiện JVM theo thời gian, hữu ích để ghép **GC, allocation, thread scheduling, I/O, CPU và latency**. Với một ứng dụng chạy lâu đủ cho recording:

```bash
java -XX:+UseZGC -Xmx2g \
  -XX:StartFlightRecording=filename=gc-study.jfr,duration=2m,settings=profile \
  -jar service.jar
```

Đây là lệnh **minh họa**, `service.jar` phải tồn tại; với chương trình demo rất ngắn, recording `duration=2m` không phù hợp để lấy đủ data nếu process kết thúc trước. Dùng một service chạy đủ lâu hoặc ghi recording theo quy trình phù hợp.

Đọc các sự kiện pause:

```bash
jfr print --events jdk.GCPhasePause gc-study.jfr
```

Khi recording có sự kiện tương ứng, mỗi `jdk.GCPhasePause` có timestamp, duration, GC ID và phase name. Oracle hướng dẫn dùng các pause phase events để tính **sum of pauses** hoặc tìm các pause dài. Trong collector đồng thời, thời gian **toàn bộ GC cycle** không bằng thời gian ứng dụng thực sự bị pause.

**Cần chú ý:**

- Không phải mọi event/type đều được bật trong mọi template/profile; kiểm tra cấu hình JFR và collector.
- Ngưỡng capture, sampling và overhead có thể làm thiếu các events ngắn.
- Nếu bật các thao tác heap statistics/heap inspection có tác dụng gây additional GC, phép đo có thể bị can thiệp; Oracle khuyến cáo tránh ép thêm GC chỉ để có statistics trong một phép đo GC bình thường.
- JFR không tự chứng minh vấn đề do GC: cần kết hợp application traces, CPU, scheduling và I/O.
- File recording có thể chứa dữ liệu nhạy cảm như class names, stack traces và event metadata; phải kiểm soát quyền, retention và chia sẻ.

### 8.3. `GarbageCollectorMXBean` và JMX metrics

Java SE cung cấp:

```java
for (GarbageCollectorMXBean bean :
        ManagementFactory.getGarbageCollectorMXBeans()) {
    System.out.println(bean.getName()
            + ": count=" + bean.getCollectionCount()
            + ", elapsedMs=" + bean.getCollectionTime());
}
```

Đây là **mảnh minh họa** trong method có import `java.lang.management.*`.

API theo chuẩn cho phép:

- `getCollectionCount()` trả số collections cộng dồn, **hoặc `-1` nếu không xác định**.
- `getCollectionTime()` trả **thời gian collection tích lũy xấp xỉ theo mili giây**, **hoặc `-1` nếu không xác định**.
- Một JVM có thể có **nhiều GC MXBeans**. Các collector có thể diễn giải “collection”/thời gian theo cách khác nhau.
- Thời gian MXBean **không phải một phép đo phân phối từng GC pause**, đặc biệt quan trọng với collector có công việc đồng thời như ZGC.
- Giá trị thời gian có độ phân giải hạn chế; count tăng nhưng collection time có thể chưa tăng.
- Lấy **chênh lệch đầu/cuối measurement window** nếu cần delta; đừng coi số tích lũy từ startup là số của pha measurement.

Với câu hỏi “P99 GC pause là bao nhiêu?”, **dùng GC logs/JFR pause events** thay vì tính P99 từ một số tổng `getCollectionTime()`.

### 8.4. Gắn GC events với ứng dụng

Bạn nên có dữ liệu đồng thời về:

- Request start/end timestamp và completion status.
- Latency histograms được bảo toàn phân phối (không chỉ một mean gộp).
- Allocation rate, heap used/committed/live set trends.
- GC pause events, concurrent cycles và stalls.
- CPU utilization, cgroup CPU throttling, process RSS và container memory.
- Request rate/concurrency/queue depth.
- JIT compilation và class-loading spikes nếu nghi ảnh hưởng warm-up.

Cùng một GC pause có thể ảnh hưởng nhiều requests, nhưng **không có quan hệ một-một** đơn giản giữa số GC pause và số request chậm. Hãy phân tích timeline và các biến khác, không lấy tương quan một lần làm chứng cứ nhân quả.

## 9. Ví dụ Java hoàn chỉnh: warm-up 5 rounds rồi đo 12 rounds

Ví dụ dưới đây là một **thí nghiệm đo lường nhỏ**, minh họa đúng cách **loại warm-up ra khỏi thống kê**, dùng **`System.nanoTime()`**, thu thập samples, tính dispersion và đọc delta của GC MXBean.

**Đây không phải công cụ microbenchmark chuẩn, không phải phép đo GC pause distribution, và không dùng 12 rounds để chứng minh P95 thực của production.** Mục đích là để người học thấy được lý do phải đo lâu hơn, lặp JVM forks và hiểu các giới hạn số liệu.

### 9.1. Chương trình `GcWarmupMeasurementDemo.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Locale;

public final class GcWarmupMeasurementDemo {
    private static final int ARRAY_BYTES = 1024;
    private static final int ALLOCATIONS_PER_ROUND = 40000;
    private static final int WARMUP_ROUNDS = 5;
    private static final int MEASURE_ROUNDS = 12;
    private static volatile byte[] keepAlive;

    private static long work(int round) {
        long checksum = 0;
        for (int i = 0; i < ALLOCATIONS_PER_ROUND; i++) {
            byte[] bytes = new byte[ARRAY_BYTES];
            bytes[0] = (byte) (round + i);
            keepAlive = bytes;
            checksum += bytes[0] & 0xff;
        }
        return checksum;
    }

    private static long gcCountOrMinusOne() {
        long total = 0;
        boolean supported = false;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = bean.getCollectionCount();
            if (count >= 0) {
                supported = true;
                total += count;
            }
        }
        return supported ? total : -1;
    }

    public static void main(String[] args) {
        long checksum = 0;
        for (int i = 0; i < WARMUP_ROUNDS; i++) {
            checksum += work(i);
        }

        long beforeGc = gcCountOrMinusOne();
        double[] durationsMs = new double[MEASURE_ROUNDS];

        for (int i = 0; i < MEASURE_ROUNDS; i++) {
            long start = System.nanoTime();
            checksum += work(100 + i);
            long elapsed = System.nanoTime() - start;
            durationsMs[i] = elapsed / 1000000.0;
        }

        long afterGc = gcCountOrMinusOne();

        double[] sorted = durationsMs.clone();
        Arrays.sort(sorted);
        double min = sorted[0];
        double median = (sorted[5] + sorted[6]) / 2.0;
        double p95 = sorted[(int) Math.ceil(0.95 * sorted.length) - 1];
        double max = sorted[sorted.length - 1];

        double sum = 0.0;
        for (double value : sorted) {
            sum += value;
        }
        double mean = sum / sorted.length;

        double variance = 0.0;
        for (double value : sorted) {
            double diff = value - mean;
            variance += diff * diff;
        }
        double stdev = Math.sqrt(variance / sorted.length);
        double cvPct = mean > 0.0
                ? (100.0 * stdev / mean)
                : Double.NaN;

        System.out.println("warmupRounds=" + WARMUP_ROUNDS);
        System.out.println("measurementRounds=" + MEASURE_ROUNDS);
        System.out.println("checksumPositive=" + (checksum > 0));
        System.out.println("minLeMedian=" + (min <= median));
        System.out.println("medianLeP95=" + (median <= p95));
        System.out.println("p95LeMax=" + (p95 <= max));

        System.out.printf(Locale.ROOT,
                "meanMs=%.3f medianMs=%.3f p95Ms=%.3f "
                + "maxMs=%.3f cvPct=%.1f%n",
                mean, median, p95, max, cvPct);

        if (beforeGc >= 0 && afterGc >= 0) {
            System.out.println("gcCountDelta=" + (afterGc - beforeGc));
        } else {
            System.out.println("gcCountDelta=unavailable");
        }
    }
}
```

### 9.2. Biên dịch và chạy

Dùng JDK hiện đại có `javac` hỗ trợ `--release 15`:

```bash
javac --release 15 -encoding UTF-8 GcWarmupMeasurementDemo.java
```

Để thử bằng ZGC trong một tiến trình có heap **nhỏ vừa đủ cho bài lab**:

```bash
java -XX:+UseZGC -Xms64m -Xmx128m \
  '-Xlog:gc*:file=gc.log:time,level,tags' \
  GcWarmupMeasurementDemo
```

Trên **PowerShell**, viết trên một dòng:

```powershell
java -XX:+UseZGC -Xms64m -Xmx128m '-Xlog:gc*:file=gc.log:time,level,tags' GcWarmupMeasurementDemo
```

`-XX:+UseZGC` yêu cầu JVM hỗ trợ ZGC. Không cần thêm `-XX:+UnlockExperimentalVMOptions` cho JDK 15 trở đi, cũng không dùng cờ `ZGenerational` cũ đã bị loại bỏ từ JDK 24. **Heap nhỏ 128 MiB** nhằm tạo hoạt động GC dễ quan sát trong **lab**, không phải heap size khuyến nghị cho backend sản xuất.

**Không chạy vòng đo này để chứng minh G1 hay ZGC là “nhanh nhất”.** Nó phân bổ một kiểu object rất đơn giản, số threads nhỏ và heap không đại diện nhiều service thực tế.

### 9.3. Các dòng output có tính cố định

Nếu chương trình chạy xong bình thường:

```text
warmupRounds=5
measurementRounds=12
checksumPositive=true
minLeMedian=true
medianLeP95=true
p95LeMax=true
```

Những dòng tiếp theo **có giá trị thay đổi theo máy và từng lần chạy**:

```text
meanMs=<thời gian trung bình>
medianMs=<trung vị> p95Ms=<P95 theo nearest-rank> maxMs=<max> cvPct=<CV>
gcCountDelta=<số đếm collections tăng, hoặc unavailable>
```

Phần trên là **ký hiệu giải thích**, không phải stdout cố định để copy vào test assertions.

**Hai lần chạy thực tế riêng biệt trên OpenJDK 24/ZGC với cùng flags** cho kết quả minh họa:

| Chỉ số | Run 1 | Run 2 |
| --- | ---: | ---: |
| Mean (ms/round) | 15,836 | 14,698 |
| Median (ms/round) | 4,444 | 4,000 |
| Nearest-rank P95 (ms/round) | 80,684 | 75,256 |
| CV (%) | 163,0 | 165,1 |
| `gcCountDelta` | 40 | 38 |

Các số này được ghi từ một **môi trường thử nghiệm cụ thể**, không phải expected output mọi nơi. Chúng minh họa rằng **median thấp hơn mean đáng kể**, tail của vài rounds có thể làm mean tăng, và độ biến thiên vẫn lớn dù đã chạy warm-up 5 rounds. Với 12 samples, nearest-rank P95 bằng max; không nên công bố hai giá trị ấy như một ước lượng P95 đáng tin của production.

### 9.4. Giải thích từng phần

**`keepAlive` có tính `volatile`:** việc gán mảng mới cho một biến static volatile làm object thoát khỏi scope phương thức theo mô hình quan sát, giảm nguy cơ JIT loại bỏ hoàn toàn allocations như công việc không có tác dụng. Đây là một thủ thuật **riêng cho thí nghiệm**, không có nghĩa ứng dụng thật nên dùng volatile để buộc GC.

**`checksum`:** xác nhận code đã thực hiện công việc có giá trị và tránh việc code không dùng kết quả trở nên quá dễ bị tối ưu. Nó không đo correctness của GC hay hiệu năng nghiệp vụ.

**`WARMUP_ROUNDS=5`:** năm lần gọi `work` được thực hiện trước khi lấy số liệu measurement. Không có số đo time của các vòng này trong `durationsMs`, vì muốn tách phase.

**`MEASURE_ROUNDS=12`:** mười hai mẫu elapsed time cho mỗi lần làm 40.000 allocations, **không phải mười hai GC pauses**. Một round có thể có nhiều GC events; một round khác có thể không có event nào.

**`System.nanoTime()`:** đo thời gian thực hiện round theo clock dành cho elapsed measurement, không phải timestamp UTC.

**`Arrays.sort` + median/P95:** tính phân phối rounds. Với 12 mẫu, `median` là trung bình vị trí 6 và 7 trong dãy đã sort (zero-based indices 5, 6). Nearest-rank P95 lấy vị trí `ceil(0.95×12)-1 = 11`, bằng max.

**`variance`/`cvPct`:** variance trong code chia cho `n` (**population standard deviation** của các rounds đã thu), không chia `n-1`. Nếu báo cáo thống kê theo sample standard deviation thì cần công thức nhất quán. Giá trị CV cao cảnh báo **cửa sổ/benchmark đang biến động**, không kết luận nguyên nhân duy nhất là GC.

**`gcCountOrMinusOne`:** chỉ cộng các `GarbageCollectorMXBean` có count không âm. `-1` nghĩa là API không xác định count, không phải “không có collections”. Kể cả khi delta là số dương, đây là một **tổng bộ đếm theo bean**, không phải thời gian pause hoặc một số GC events được timestamp đủ để tính P99.

**File `gc.log`:** lệnh `-Xlog` tạo log riêng. Trên một lần chạy thử nó có dòng `Initializing The Z Garbage Collector`, chứng tỏ collector đã được bật. Để kết luận liên quan GC, cần đọc logs và đối chiếu thời điểm với measurement window; bài demo chưa tự ghi marker tương ứng vào GC log.

### 9.5. Vì sao đây chưa phải một benchmark ổn định?

Thử nghiệm cố tình ngắn để người học chạy được:

- Mỗi round chỉ có một loại allocation, không có request/network/I/O thực.
- Có 5 vòng warm-up, nhưng chưa có tiêu chí **khẳng định compiler, cache và live set đã đạt steady state**.
- Một JVM run chỉ có 12 mẫu; P95 bằng max và P99 cũng rất gần max theo nearest-rank, không đủ mô tả tail.
- Các rounds trong cùng process có **tự tương quan** và chia sẻ heap/JIT.
- Lượng work đã cố định nhưng memory state và GC events không cố định giữa các rounds.
- Nếu GC có event chiếm phần lớn một round, mean và CV có thể biến thiên mạnh.
- Để so sánh collector, cần **nhiều forks, longer controlled load, các metrics ứng dụng và GC events**.

Vì vậy chương trình giúp **hiểu phương pháp đo và kiểm tra công cụ**, chứ không thay thế benchmark công nghiệp.

## 10. Dùng JMH khi mục tiêu là microbenchmark

**JMH — Java Microbenchmark Harness** là dự án OpenJDK chuyên cho việc tạo, chạy và phân tích JVM benchmarks ở mức nano/micro/milli/macro; còn được phát triển và sử dụng trong Java hiện đại.

JMH giải quyết nhiều vấn đề của benchmark thủ công:

- Khai báo **warm-up iterations**, **measurement iterations** và thời lượng mỗi iteration.
- Chạy **JVM forks** tách biệt.
- Có framework quản lý vòng đo, state và output thống kê.
- Có cách tiêu thụ kết quả để tránh lỗi **dead-code elimination** (ví dụ `Blackhole`).
- Có **GC profiler** như `-prof gc` để quan sát allocations/GC-related counters tùy JVM/provider.
- Giảm rủi ro đo một method quá ngắn bằng vài lời gọi `nanoTime` thô.

Ví dụ cú pháp *minh họa* trong một class JMH (cần tạo project/dependencies/annotation processing theo hướng dẫn OpenJDK; **không phải file Java SE độc lập**):

```java
@State(Scope.Thread)
public class AllocationBenchmark {
    @Benchmark
    @Warmup(iterations = 5, time = 1)
    @Measurement(iterations = 10, time = 1)
    @Fork(3)
    public void allocate(Blackhole bh) {
        byte[] bytes = new byte[1024];
        bytes[0] = 42;
        bh.consume(bytes);
    }
}
```

Cần imports `org.openjdk.jmh.annotations.*` và `org.openjdk.jmh.infra.Blackhole` cùng plugin/processor của JMH. **Các con số 5/10/3 là ví dụ**, không phải giá trị phải dùng cho mọi bài. Chọn thời gian/số forks đủ cho mục tiêu và budget.

Để bắt đầu, xem **OpenJDK JMH official README**: https://github.com/openjdk/jmh và tài liệu samples: https://github.com/openjdk/jmh/tree/master/jmh-samples

**Cảnh báo quan trọng:** JMH đo đúng hơn **microbenchmarks** nhưng **không thay thế application-level load testing** khi mục tiêu là GC behavior của hệ thống thật. Microbenchmark tạo allocations nhân tạo có thể khác rất xa object lifetime, concurrency, cache, thread pool, request queuing và traffic bursts trong production.

Nếu cần xem P99 request latency hoặc tác động GC lên request SLO, nên dùng **load generator + JFR/GC logs + application traces**, không chỉ bảng kết quả JMH.

## 11. Quy trình đo GC có thể tái lập cho một service

Một kế hoạch có thể áp dụng thực tế:

### Bước 1 — xác định mục tiêu và SLO

Ví dụ cần:

- P99 request latency dưới ngưỡng được định nghĩa cho workload.
- Không có allocation stalls đáng kể trong peak.
- Throughput đạt target req/s với error rate chấp nhận được.
- Process/container memory không vượt quota.
- Giảm GC pause tail nhưng không phá CPU budget.

Mục tiêu càng cụ thể thì càng dễ chọn duration/sample size phù hợp.

### Bước 2 — khóa các biến môi trường

Ghi nhận **JDK vendor/build**, GC và flags, heap `-Xms`/`-Xmx`, CPU architecture, số cores/quota, container memory, application artifact, dataset, traffic generator và host OS/kernel.

Không gộp một kết quả JDK 15 ZGC với JDK 24 ZGC và gọi đó là “cùng một collector mode” mà không giải thích: từ JDK 24 chỉ còn generational ZGC.

### Bước 3 — chọn profile tải

Khai báo tỉ lệ endpoint, request rate/concurrency, payload distribution, cache warm-up, session counts, dữ liệu tồn kho và các bursts/tác vụ định kỳ.

Nếu so sánh collectors, phải chạy cùng workload definition và kiểm tra generator không trở thành bottleneck.

### Bước 4 — làm nóng hệ thống

Chạy workload đến khi JIT/class loading/cache/live set và throughput/GC behavior đại diện cho hoạt động cần đo. Ghi nhận **độ dài warm-up thực tế và lý do dừng**, không chỉ một số vòng tùy ý.

### Bước 5 — bắt đầu measurement window rõ ràng

Đánh dấu thời điểm đo ở application/load generator. Thu thập **request samples**, **GC logs/JFR**, heap/cgroup memory, CPU/GC CPU và allocation metrics đồng thời. Tránh bật một profiling mode overhead cao ở giữa phép đo mà không ghi nhận.

### Bước 6 — kéo dài đến đủ dữ liệu

Với GC events hiếm, đo đủ lâu để thấy phân phối. Với recurring tasks, chứa các cycles quan trọng. Nếu một run có rất ít GC events, không công bố P99 GC pause như một ước lượng chắc chắn.

### Bước 7 — kết thúc, khởi động lại và lặp

Chạy **nhiều JVM process độc lập**. Nếu so sánh hai phương án, luân phiên thứ tự runs. Đảm bảo dữ liệu được phân nhóm theo **process run** và phase.

### Bước 8 — phân tích

Tách startup/warm-up/steady state; thống kê ứng dụng và GC theo đúng units; vẽ time-series heap, GC pauses, CPU và latency. Tính median, P95/P99, max, confidence/dispersion theo cỡ mẫu và ý nghĩa của dữ liệu. Tìm anomalies thay vì tự loại chúng.

### Bước 9 — đưa ra kết luận có điều kiện

Báo cáo “Config A tốt hơn trong workload X, trên JDK Y, với heap/CPU limits Z và N runs” thay vì “Config A luôn tốt nhất”. Nếu chênh lệch nhỏ hơn noise, nói rõ kết quả chưa đủ phân biệt.

### Bước 10 — kiểm tra lại sau thay đổi

Mỗi lần đổi JDK, GC mode, flags, object allocation profile, traffic shape, server size hoặc container quotas đều có thể cần **rerun**. Đừng dùng benchmark cũ để biện minh cho cấu hình đã thay đổi nhiều.

## 12. So sánh warm-up của GC với “ép hoàn tất mọi GC”

Một số người đề xuất “warm-up đến khi đã có N GC collections”. Cách này có giá trị như một **dấu hiệu phụ** nhưng không đủ:

- Nhiều collectors có **young/old/mixed/concurrent cycles** khác nhau.
- JDK versions có thể thay đổi tên/ý nghĩa beans và events.
- Một lần GC ở giai đoạn startup không tương đương một lần GC dưới tải peak.
- **Không có GC trong một pha warm-up** cũng chưa chắc sai, nếu workload không tạo đủ allocations; nhưng có thể nghĩa benchmark không thật sự stress memory.
- Ép `System.gc()` để tăng count có thể làm đổi kết quả.
- Một GC cycle hoàn tất không đảm bảo cache/long-lived objects đã ổn định.

Do đó, kết thúc warm-up nên dựa trên **hành vi workload + JIT/class loading + heap/GC metrics + mục tiêu phép đo**, không dựa độc nhất vào bộ đếm GC.

## 13. Khi đo P99 phải hiểu cỡ mẫu và coordinated omission

### 13.1. Sample size và percentile

Giả sử bạn đo **20 GC pause events**. Nearest-rank P99 sẽ lấy gần như **max**; tail hiếm chưa có cơ hội xuất hiện. Với 100 events, P99 cũng chỉ dựa vào một vị trí rất gần cuối.

Điểm quan trọng:

- Muốn tuyên bố **P99**, cần nhiều **độc lập hoặc gần độc lập** events trong các điều kiện đại diện; không có con số N chung bảo đảm chính xác.
- Sự kiện GC có thể **cluster theo workload**, không phải samples ngẫu nhiên i.i.d.
- P99 có thể đổi đáng kể khi thêm một burst/old generation activity hay một OS scheduling anomaly.
- Khoảng đo đủ dài và nhiều forks có ích hơn việc chỉ tăng tốc độ sampling của một khoảng ngắn.
- Báo cáo số events và khoảng tin cậy/độ nhạy nếu dùng percentile làm quyết định quan trọng.

### 13.2. Coordinated omission trong load testing

Ở **closed-loop generator**, mỗi client chờ response rồi mới gửi request tiếp. Khi server chậm vì GC hoặc CPU, generator cũng vô tình **gửi ít request hơn** trong thời gian chậm, khiến response latency histogram có thể **bỏ lỡ ảnh hưởng tới các arrivals lẽ ra xảy ra**.

Nếu ứng dụng có external arrival process, hãy dùng load model phản ánh tần suất đến, ghi request waiting/queuing và áp dụng công cụ có hỗ trợ xử lý coordinated omission khi cần. Không mặc định mọi benchmark tool đều sửa đúng vấn đề này.

### 13.3. Báo cáo P99 GC pause không phải P99 request

Một request có thể chịu một hoặc nhiều GC pauses, đồng thời còn có CPU, lock, I/O và queueing. Do đó:

- P99 GC pause 5 ms **không** suy ra P99 request 5 ms.
- P99 request cao **không** chứng minh do GC.
- Muốn quy nguyên nhân, tìm **correlation trên timeline** và phân tích các thành phần latency.
- Xem cả **sum of pauses** và **thời gian GC chiếm CPU**, không chỉ một pause đơn lẻ.

## 14. Nhiễu môi trường gây mất ổn định kết quả

| Nguồn nhiễu | Dấu hiệu | Cách kiểm soát/thông báo |
| --- | --- | --- |
| **JIT/tiered compilation** | Những rounds đầu nhanh/chậm dần | Warm-up, ghi compiler/runtime, dùng JMH khi microbench |
| **Class loading/lazy init** | Spike bất thường đầu tiên cho một code path | Khởi tạo đủ paths trước steady state hoặc đo riêng startup |
| **Heap expansion/commit** | Memory/GC thay đổi lúc mới chạy | Theo dõi committed, `-Xms`, memory, không ngầm ép GC |
| **Cache warming** | Throughput tăng dần theo thời gian | Dùng workload đủ dài, ghi nhận cache hit/size |
| **CPU throttling** | Latency spikes, CPU quota saturation | Kiểm tra cgroup CPU stats, không chỉ host CPU % |
| **CPU frequency/thermal** | Run sau chậm hơn dù workload giống | Môi trường test ổn định, randomize thứ tự |
| **Background processes** | Jitter theo hoạt động OS/agent | Tách tài nguyên khi được phép, ghi tải nền |
| **NUMA / memory placement** | Khác nhau giữa máy/CPU placement | Giữ topology/affinity nhất quán khi phù hợp |
| **Container memory pressure** | Major page faults, OOMKilled, RSS tăng | Giữ memory budget và heap/native headroom |
| **I/O/network** | Response tail tăng không liên quan GC | Tách latency sources, so sánh CPU/I/O/GC timelines |
| **Logging/profiler overhead** | Bật log/JFR làm workload chậm | Dùng mức logging tương đương giữa các cấu hình |
| **Object retention/cache TTL** | Live set tăng sau warm-up ngắn | Đo đủ chu kỳ cache/queue/batch |
| **Traffic generator** | Req/s không giữ mục tiêu, dropped requests | Tách máy generator/kiểm tra generator saturation |
| **Data-dependent branches** | Một run xử lý input “dễ” hơn | Dùng dataset/seed/case mix nhất quán |
| **Process state** | JVM forks cho kết quả khác | Báo cáo variability across forks |
| **JDK version/GC mode** | Pause/throughput đổi sau upgrade | Ghi chính xác build và flags; benchmark lại |

**Đừng tự cấm CPU frequency scaling hoặc đổi OS kernel settings trên production chỉ để làm số liệu đẹp.** Kiểm soát môi trường benchmark trong một test lab được phép và báo cáo những điều đã/không kiểm soát.

## 15. Những sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Chạy một lần rồi kết luận | Không biết biến thiên giữa các JVM runs | Nhiều forks, báo cáo distribution và uncertainty |
| Không có warm-up cho steady-state test | Startup/JIT/class loading trộn vào measurement | Tách pha, theo dõi trend và heap/GC state |
| Luôn warm-up 5 giây | Không có thời gian chung cho mọi workload | Dừng theo hành vi workload/cycles cần đo |
| Bỏ startup khỏi bài đo cold-start | Loại chính yếu tố cần đo | Báo startup riêng |
| Gọi `System.gc()` trước mọi sample | Thay đổi GC behavior và object age dynamics | Không ép GC nếu production không làm vậy |
| Dùng `System.currentTimeMillis()` cho operation rất ngắn | Độ phân giải/clock adjustments hạn chế | `nanoTime` hoặc JMH |
| Chỉ nhìn mean GC time | Tail, pause count và concurrency bị ẩn | P50/P95/P99/max cùng GC event count và app SLO |
| Lấy `getCollectionTime()` làm P99 pause | API là tổng thời gian gần đúng, không có event distribution | GC logs/JFR pause events |
| Coi GC cycle duration là stop-the-world pause | Collector concurrent làm việc nhiều khi app vẫn chạy | Phân biệt GCPhasePause/sumOfPauses và concurrent phases |
| Dùng P99 từ 12 mẫu | Tail percentile biến thành max, rất bất ổn | Tăng số mẫu, nhiều windows/runs |
| Chỉ giữ kết quả run tốt nhất | Selection bias | Báo mọi runs, giải thích anomalies |
| Thấy CV thấp rồi kết luận steady state | Có thể drift/cache leak mà CV vẫn thấp | Kiểm tra trend và nhiều metrics |
| Xem mỗi round trong cùng JVM là fork độc lập | Shared JIT/heap/GC state gây correlation | Restart JVM cho independent forks |
| Đổi JDK + heap + collector cùng lúc | Không biết nguyên nhân thay đổi | Kiểm soát từng biến hoặc thiết kế thí nghiệm rõ |
| So sánh ZGC cũ với hiện đại mà không nêu mode | Collector behavior đã thay đổi, JDK24+ chỉ generational | Ghi vendor/build/mode |
| Quên CPU/memory cgroup limits | Benchmark host khác production | Thử trong env tương đương |
| Benchmark code bị JIT loại bỏ | Công việc không có effect nên số đẹp giả | JMH Blackhole/cách dùng kết quả đúng |
| Chỉ dùng microbenchmark cho quyết định production GC | Object lifetimes/concurrency khác thật | Load-test system + observability |
| Chỉ đo request completion khi closed-loop | Có thể coordinated omission | Chọn load model và xử lý missing arrivals |
| Bật detailed profiling cho A nhưng không cho B | Overhead đo khác nhau | Giữ instrumentation tương đương và đánh giá overhead |

## 16. Checklist để báo cáo phép đo GC đáng tin

- [ ] Mục tiêu là startup, throughput, GC pauses, request tail latency, memory footprint hay allocation stalls?
- [ ] Đã phân biệt **GC pause** với **concurrent GC cycle**?
- [ ] Đã ghi JDK vendor/build, collector, mode, `-Xms`/`-Xmx`, CPU/cgroup memory limits?
- [ ] Warm-up đã chạy workload đại diện, đủ cho JIT/class loading/cache/object retention?
- [ ] Có tiêu chí dừng warm-up dựa trên xu hướng thực tế, không chỉ số giây cố định?
- [ ] Measurement window bắt đầu/kết thúc rõ, log/JFR/request metrics cùng timeline?
- [ ] Khoảng đo đủ dài để quan sát các GC cycles và events/traffic bursts quan trọng?
- [ ] Có **nhiều JVM forks** khi so sánh, và không chọn run tốt nhất làm kết quả duy nhất?
- [ ] Với A/B, có randomize/luân phiên thứ tự, giữ điều kiện tài nguyên và workload tương đương?
- [ ] Báo cáo sample count, mean, median, percentiles, max và dispersion **đúng đơn vị sự kiện**?
- [ ] Đã tránh P95/P99 từ quá ít samples và nhầm GC events với measurement rounds?
- [ ] Có phân tích instability, outliers, autocorrelation, noise và uncertainty?
- [ ] Có thu GC logs/JFR events cùng throughput, CPU, allocation rate, heap và request latency?
- [ ] Có hiểu `GarbageCollectorMXBean` count/time có thể `-1` hoặc chỉ là số tích lũy xấp xỉ?
- [ ] Có kiểm tra benchmarking code không bị dead-code elimination, và dùng JMH khi thích hợp?
- [ ] Load model có tránh/coi rõ coordinated omission khi đo request latency?
- [ ] Có ghi rõ các giới hạn, số runs và lý do chưa kết luận khi khác biệt nhỏ hơn noise?
- [ ] Kết quả có được kiểm tra lại trên staging/production-like environment sau thay đổi JDK/config/code?

## 17. Tài liệu chính thức và tiếp tục được sử dụng

- **OpenJDK — Java Microbenchmark Harness (JMH)**, hướng dẫn project, warm-up, measurement và forks: https://github.com/openjdk/jmh
- **OpenJDK — JMH Samples**, minh họa các phép đo, state và tối ưu hóa của JVM: https://github.com/openjdk/jmh/tree/master/jmh-samples
- **Oracle Java SE 25 — `GarbageCollectorMXBean`**, ý nghĩa collection count/time, `-1` khi không xác định: https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html
- **Oracle Java SE 15 — `ManagementFactory`**, GC MXBeans và các quản trị/quan sát API: https://docs.oracle.com/en/java/javase/15/docs/api/java.management/java/lang/management/ManagementFactory.html
- **Oracle Java SE 24 — Troubleshoot Performance Issues Using Flight Recorder**, `jdk.GCPhasePause` và phân tích tổng pause time: https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- **Oracle Java SE 25 — `java` command**, Unified Logging `-Xlog` và `StartFlightRecording`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **Oracle Java SE 25 — Java Flight Recorder**, các công cụ/recordings/analysis: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html
- **Oracle Java SE 25 — HotSpot VM Garbage Collection Tuning Guide**, lựa chọn collectors và đặc điểm pauses/throughput/heap: https://docs.oracle.com/en/java/javase/25/gctuning/
- **OpenJDK JEP 377 — ZGC Production (JDK 15)**: https://openjdk.org/jeps/377
- **OpenJDK JEP 439 — Generational ZGC (JDK 21)**: https://openjdk.org/jeps/439
- **OpenJDK JEP 490 — Remove Non-Generational ZGC (JDK 24)**: https://openjdk.org/jeps/490

**Kết luận:** một phép đo GC đáng tin phải **warm-up đúng workload**, xác định **measurement window đủ dài và đủ events**, rồi kiểm tra **độ ổn định bằng nhiều samples và nhiều JVM runs độc lập**. Báo cáo cần nêu rõ mình đang đo **GC pause, concurrent cycle, application latency hay throughput**, cùng JDK/GC mode/flags và các giới hạn môi trường. Nếu các kết quả biến thiên lớn hoặc chưa đủ số mẫu, kết luận có giá trị nhất có thể là **cần đo thêm**, chứ không phải tuyên bố cấu hình nào “tốt nhất” từ một lần chạy.
