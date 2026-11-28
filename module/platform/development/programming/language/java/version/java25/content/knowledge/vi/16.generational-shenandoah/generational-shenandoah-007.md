# So sánh với cấu hình GC hiện có và xây dựng tiêu chí lựa chọn hoặc quay lui

## Mục tiêu bài học

Chọn garbage collector (GC) không chỉ là chọn một thuật toán thu gom rác. Quyết định này ảnh hưởng trực tiếp tới latency, throughput, CPU, bộ nhớ và khả năng duy trì SLO khi ứng dụng có tải cao. **Generational Shenandoah** là chế độ thế hệ của Shenandoah GC, tận dụng giả thuyết rằng phần lớn object mới tạo sẽ sớm trở thành rác, đồng thời giữ đặc tính thu gom đồng thời nhằm hạn chế thời gian dừng ứng dụng.

Trong **JDK 25**, **JEP 521 — Generational Shenandoah** đã chuyển tính năng từ trạng thái experimental ở JDK 24 thành **product feature**. Tuy nhiên, chế độ generational vẫn là lựa chọn opt-in; Shenandoah mặc định dùng mode `satb` (single-generation). Vì vậy, cần so sánh nó với GC đang chạy, thử nghiệm trên workload thật và chuẩn bị đường quay lui trước khi triển khai.

Bài **So sánh với cấu hình GC hiện có và xây dựng tiêu chí lựa chọn hoặc quay lui** thuộc chương **Generational Shenandoah** của module **JAVA_VERSION_JAVA25**. Bài kết hợp các lựa chọn hiện hành như G1, Parallel, ZGC, Shenandoah SATB và Generational Shenandoah, đồng thời cập nhật những thay đổi có liên quan đến JDK 27.

Sau bài học, bạn có thể:

1. Giải thích mô hình young/old generation và lợi ích của generational collection.
2. Phân biệt Shenandoah mode `satb` với mode `generational`.
3. Bật Generational Shenandoah bằng JVM options chính thức của JDK 25.
4. So sánh GenShen với G1, Parallel GC, ZGC và Shenandoah single-generation theo workload.
5. Đọc GC log và chọn các chỉ số phù hợp để đánh giá latency, throughput, CPU và memory.
6. Thiết kế benchmark A/B có thể lặp lại, giữ nguyên điều kiện chạy và tránh kết luận từ một lần đo.
7. Xây dựng tiêu chí go/no-go, canary, rollback và xác minh cấu hình GC sau khi quay lui.
8. Tránh các cờ experimental, heuristic không được hỗ trợ và hướng dẫn cũ không còn phù hợp.

> **Mốc phiên bản cần nhớ:** JDK 25 đã chính thức hóa Generational Shenandoah nhưng không bật mặc định. JDK 27 hiện vẫn để Shenandoah mode mặc định là `satb`; `generational` vẫn phải được chọn tường minh. Không dùng cú pháp `-XX:+UnlockExperimentalVMOptions` của giai đoạn JDK 24 cho JDK 25 trở lên.

## 1. Vì sao cần so sánh GC theo workload?

Một dịch vụ Java có thể tạo hàng triệu object mỗi giây nhưng phần lớn object chỉ sống trong một request. Một dịch vụ khác lại giữ nhiều object trong cache, session hoặc graph dữ liệu trong nhiều giờ. Cùng một GC có thể cho kết quả khác nhau đáng kể giữa hai trường hợp.

Các mục tiêu thường phải cân bằng:

| Mục tiêu | Ý nghĩa |
|---|---|
| **Latency** | Thời gian phản hồi của request; thường quan tâm p95, p99 và p99.9 |
| **Pause time** | Thời gian GC dừng các application thread |
| **Throughput** | Số request hoặc đơn vị công việc hoàn thành trong một đơn vị thời gian |
| **CPU cost** | CPU dùng cho GC và phần CPU còn lại cho ứng dụng |
| **Heap footprint** | Dung lượng heap cần để duy trì live data và vùng dự phòng |
| **Process/container memory** | RSS và memory thực tế, bao gồm heap, metaspace, code cache, thread stacks và native memory |
| **Stability** | Khả năng tránh allocation failure, degenerated/full GC, OOM và biến động latency |

Không có một GC luôn tốt nhất cho mọi mục tiêu. Một collector có pause ngắn hơn vẫn có thể dùng nhiều CPU đồng thời hơn, làm giảm throughput khi container bị giới hạn CPU. Một collector đạt throughput cao có thể có các pause dài hơn nhưng vẫn đáp ứng yêu cầu của batch job.

### 1.1. Generational hypothesis

Generational collection dựa trên quan sát phổ biến: **đa số object chết trẻ**. Ví dụ:

- String, iterator, DTO trung gian và object phục vụ một request thường có lifetime ngắn.
- Object cache, cấu hình và cấu trúc dữ liệu dùng chung thường sống lâu hơn.
- Object sống sót qua nhiều chu kỳ young collection có thể được chuyển sang old generation.

Thay vì xử lý toàn bộ heap trong mỗi chu kỳ, collector có thể thu gom young generation thường xuyên hơn và xử lý old generation theo lịch ít thường xuyên hơn.

~~~mermaid
flowchart TD
    A["Object mới được cấp phát"] --> Y["Young generation"]
    Y -->|Không còn reachable| D["Thu hồi ở young collection"]
    Y -->|Sống sót qua nhiều chu kỳ| P["Promotion / aging"]
    P --> O["Old generation"]
    O -->|Không còn reachable| R["Thu hồi trong old-generation cycle"]
    O -->|Còn được tham chiếu| O
~~~

Generational collection không làm object sống lâu tự biến mất. Nó phân chia công việc theo tuổi object và vẫn phải xử lý tham chiếu giữa các thế hệ để bảo đảm object còn reachable không bị thu hồi nhầm.

## 2. Generational Shenandoah là gì?

**Shenandoah** là concurrent low-pause garbage collector của HotSpot. Phần lớn công việc đánh dấu, di chuyển và cập nhật tham chiếu được thực hiện đồng thời với application thread; vẫn có các pha stop-the-world ngắn. Mục tiêu là giảm pause time và hạn chế việc pause tăng tỷ lệ thuận với kích thước heap.

Shenandoah có hai mode chính trong JDK 25:

| Mode | Mô hình | Mặc định |
|---|---|---|
| `satb` | Snapshot-at-the-beginning concurrent GC, single generation | **Có** |
| `generational` | Snapshot-at-the-beginning concurrent GC, có young và old generation | Không; cần chọn tường minh |

Ở mode `satb`, Shenandoah không chia heap thành young/old để ưu tiên thu gom object ngắn hạn. Ở mode `generational`, collector khai thác tuổi object để thu gom young generation thường xuyên hơn và old generation theo chu kỳ riêng.

### 2.1. Lợi ích kỳ vọng

Generational Shenandoah hướng tới các workload có đặc điểm:

- Allocation rate cao.
- Phần lớn object được tạo ra chỉ tồn tại trong thời gian ngắn.
- Có lượng live data dài hạn đáng kể bên cạnh lượng object ngắn hạn.
- Cần pause time thấp và muốn tránh quét toàn bộ live heap quá thường xuyên.

Nếu young generation chứa nhiều object đã chết, một young collection có thể tập trung công việc vào vùng này thay vì thực hiện cùng lượng công việc trên toàn bộ heap. Old generation vẫn được thu gom đồng thời và có lịch riêng.

### 2.2. Những chi phí vẫn phải tính đến

Generational mode cần duy trì tính đúng đắn khi object ở old generation tham chiếu object ở young generation. Điều đó đòi hỏi các cơ chế barrier và bookkeeping phù hợp. Các thao tác ghi reference, promotion và quản lý hai thế hệ có thể tạo thêm chi phí.

Do đó:

- Workload có nhiều object ngắn hạn có thể hưởng lợi từ việc thu gom young generation.
- Workload ít có đặc tính generational có thể không hưởng lợi tương ứng.
- Workload cập nhật reference liên thế hệ dày có thể chịu thêm chi phí barrier.
- Collector vẫn cần CPU và heap headroom để thực hiện công việc concurrent.
- Pause thấp không đồng nghĩa throughput, RSS hoặc p99 chắc chắn tốt hơn.

**JEP 521 là product feature, không phải cam kết hiệu năng cho mọi ứng dụng.** Tiêu chí lựa chọn phải dựa trên số liệu đo được của workload thực tế.

## 3. Trạng thái và cấu hình trong JDK 25

Generational Shenandoah được đưa vào JDK 24 dưới dạng experimental. Trong JDK 25, JEP 521 hoàn thiện tính năng thành product feature. Cú pháp sử dụng trong JDK 25:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -jar app.jar
~~~

Không cần bật `-XX:+UnlockExperimentalVMOptions` trong JDK 25 để dùng mode này.

Nếu muốn dùng Shenandoah single-generation:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=satb \
  -jar app.jar
~~~

Có thể bỏ `ShenandoahGCMode=satb` vì đây là mặc định của Shenandoah, nhưng khai báo rõ ràng có ích khi tạo một baseline kiểm thử.

### 3.1. Heuristics của Generational Shenandoah

`-XX:ShenandoahGCHeuristics` quyết định cách collector chọn thời điểm bắt đầu GC và lượng công việc cần thực hiện. Trong JDK 25:

- Heuristic mặc định là `adaptive`.
- Khi mode là `generational`, **chỉ heuristic mặc định `adaptive` được hỗ trợ**.
- Không đặt `static` hoặc `compact` cho Generational Shenandoah.

Ví dụ cấu hình phù hợp:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -XX:ShenandoahGCHeuristics=adaptive \
  -jar app.jar
~~~

Có thể bỏ hẳn `ShenandoahGCHeuristics=adaptive` vì đó là mặc định. Không thêm các cờ nội bộ hoặc cờ tuning không được tài liệu JDK 25 hỗ trợ chỉ để cố điều khiển tuổi object hay promotion.

### 3.2. Kiểm tra build JVM có hỗ trợ Shenandoah

Không phải mọi JDK distribution, vendor build hoặc platform đều cung cấp cùng một tập GC. Một product feature trong OpenJDK không đồng nghĩa mọi binary của mọi vendor đều đóng gói collector đó. Đáng chú ý, tài liệu lệnh `java` của Oracle JDK 25 không liệt kê các tùy chọn Shenandoah, trong khi tài liệu Oracle JDK 27 có mô tả chúng. Vì vậy, trước khi sửa deployment, kiểm tra **đúng binary Java đang chạy production**:

~~~bash
java -version
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -version
~~~

Nếu JVM báo option không được nhận diện hoặc collector không khả dụng, không thêm cờ experimental unlock để thử ép chạy. Hãy kiểm tra tài liệu của vendor, platform và build đang dùng; nếu cần Shenandoah, chọn runtime có hỗ trợ chính thức rồi kiểm thử lại.

Có thể xem các flag runtime:

~~~bash
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -XX:+PrintCommandLineFlags \
     -version
~~~

Với process đang chạy:

~~~bash
jcmd 12345 VM.flags -all
jcmd 12345 VM.info
~~~

Thay `12345` bằng PID thực tế. Trong container, chạy công cụ trong đúng process namespace và với quyền user phù hợp.

### 3.3. Xác minh mode và heuristic

Khi dùng `jcmd`, tìm các giá trị liên quan:

- `UseShenandoahGC` phải bật.
- `ShenandoahGCMode` phải là `generational`.
- `ShenandoahGCHeuristics` phải là `adaptive`.

Có thể kết hợp log khởi tạo và GC:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc+init=info,gc=info \
  -jar app.jar
~~~

Không chỉ dựa vào file cấu hình Helm, Dockerfile hoặc biến môi trường. Kiểm tra arguments và flags của **JVM process thực tế**, vì entrypoint, script hoặc platform có thể ghi đè cấu hình.

## 4. So sánh Shenandoah SATB và Generational Shenandoah

Đây là phép so sánh quan trọng nhất để biết lợi ích đến từ generational mode hay chỉ từ việc chuyển sang Shenandoah.

| Tiêu chí | Shenandoah `satb` | Generational Shenandoah |
|---|---|---|
| Số thế hệ | Một | Young và old |
| Thu gom object ngắn hạn | Không có young-only collection | Có young collections |
| Thu gom old generation | Xử lý trong chu kỳ single-generation | Có old-generation cycles riêng |
| Mô hình | Concurrent SATB, mark/evac/update | Concurrent SATB, có phân chia thế hệ |
| Heuristic | Có các lựa chọn theo build/JDK | Chỉ `adaptive` được hỗ trợ |
| Mục tiêu | Low pause với mô hình single-generation | Low pause và tận dụng weak generational hypothesis |
| Khi đáng thử | Workload ít hưởng lợi từ phân chia tuổi object hoặc cần baseline Shenandoah | Allocation rate cao, nhiều object chết trẻ |
| Rủi ro cần đo | Công việc trên heap rộng, CPU concurrent và heap headroom | Barrier/promotion overhead, young/old cycle phối hợp và CPU concurrent |

Nếu GenShen không cải thiện so với Shenandoah SATB, cần xem workload có thực sự có đặc tính generational hay không. Đừng mặc định generational mode luôn tốt hơn chỉ vì nhiều GC khác cũng dùng young/old generation.

## 5. So sánh với các GC thường gặp

Bảng dưới đây mô tả định hướng chọn lựa. Kết quả thực tế còn phụ thuộc JDK build, platform, heap, CPU và workload.

| GC | Định hướng | Điểm mạnh thường gặp | Trade-off cần đo |
|---|---|---|---|
| **G1** | General-purpose, cân bằng latency và throughput | Generational, adaptive pause-time goals, mặc định trên server-class trong JDK 25 | Một số pha stop-the-world; GC concurrent dùng CPU của ứng dụng |
| **Parallel GC** | Throughput | Thu gom song song, phù hợp batch hoặc workload ưu tiên throughput | Pause stop-the-world có thể dài |
| **ZGC** | Low latency | Concurrent, generational trong JDK 25 | Cần CPU headroom và đo memory footprint; không mặc định là nhanh hơn mọi GC |
| **Shenandoah SATB** | Low pause, single-generation | Concurrent collection, không phụ thuộc phân chia tuổi object | Không có young-only collection |
| **Generational Shenandoah** | Low pause và tận dụng object lifetime | Young collections tập trung vào object ngắn hạn, old cycles riêng | Barrier, promotion, phối hợp young/old và CPU concurrent |
| **Serial GC** | Workload nhỏ hoặc ít thread | Đơn giản, ít chi phí GC thread | Không phù hợp nhiều workload server đồng thời |

### 5.1. G1 — baseline hợp lý cho nhiều dịch vụ

G1 là collector mặc định trong JDK 25 trên server-class machines; máy không thuộc server-class có thể chọn Serial theo ergonomics. Từ JDK 27, G1 trở thành mặc định trong mọi môi trường theo JEP 523.

G1 là generational, incremental, parallel, mostly concurrent và có các pha stop-the-world. Nó cố gắng đáp ứng pause-time goal với xác suất cao, không bảo đảm một giới hạn pause tuyệt đối.

G1 là baseline tốt khi:

- Ứng dụng cần cân bằng latency và throughput.
- Heap lớn và live data đáng kể.
- Allocation/promotion thay đổi theo thời gian.
- Chưa có bằng chứng rằng GC hiện tại là bottleneck.

Không nên bỏ G1 chỉ vì GenShen có pause ngắn trong một microbenchmark. Hãy so sánh cùng workload và cùng điều kiện triển khai.

### 5.2. Parallel GC — khi throughput quan trọng hơn pause

Parallel GC thường phù hợp với batch, xử lý dữ liệu hoặc workload có thể chấp nhận pause dài hơn để đổi lấy throughput.

Nếu hệ thống đang dùng Parallel GC và latency không phải SLO nghiêm ngặt, GenShen có thể không phải nâng cấp cần thiết. Cần đo tổng thời gian GC, CPU và lượng công việc hoàn thành trước khi chuyển collector.

### 5.3. ZGC — lựa chọn low-latency khác

Trong JDK 25, ZGC dùng generational mode; non-generational mode đã bị loại bỏ. Không sử dụng các hướng dẫn cũ để bật/tắt non-generational ZGC như một phương án rollback hiện hành.

ZGC và Generational Shenandoah đều hướng tới low latency nhưng có implementation, barrier, memory behavior và tuning riêng. So sánh trực tiếp bằng p99/p99.9, throughput, CPU và RSS trên cùng workload; không chỉ so pause time.

### 5.4. Không so sánh GC bằng một chỉ số duy nhất

Một cấu hình có thể đạt pause thấp hơn nhưng:

- Tăng CPU do concurrent GC.
- Giảm throughput dưới CPU quota.
- Dùng heap hoặc RSS lớn hơn.
- Có old-generation cycle kéo dài.
- Tạo tail latency do promotion hoặc allocation pressure.

Đánh giá phải kết hợp SLO của ứng dụng và tài nguyên mà nền tảng thực sự cấp cho process.

## 6. Khi nào nên thử Generational Shenandoah?

GenShen đáng được đưa vào danh sách ứng viên khi có bằng chứng:

- Allocation rate cao và nhiều object có lifetime ngắn.
- GC đang chiếm tỷ lệ đáng kể trong CPU hoặc ảnh hưởng tail latency.
- Heap có cả lượng object ngắn hạn lớn và live data dài hạn.
- Hệ thống cần pause thấp hơn baseline hiện tại.
- Nền tảng có đủ CPU headroom để thực hiện concurrent collection.
- Runtime JDK cụ thể có Shenandoah Generational được hỗ trợ.

Một số ví dụ workload có thể phù hợp:

| Workload | Vì sao đáng thử |
|---|---|
| API service tạo nhiều request DTO, validation object và response object | Nhiều object có thể chết sau một request |
| Pipeline xử lý message có object trung gian | Object tạm thời được tạo theo từng message |
| Service chuyển đổi dữ liệu hoặc parse payload | Nhiều object tạm thời, allocation burst |
| Hệ thống cache có live set lớn nhưng vẫn tạo nhiều object ngắn hạn | Có thể tách phần object trẻ khỏi phần dữ liệu sống lâu |
| Workload cần low pause với heap lớn | Shenandoah là ứng viên để benchmark |

### 6.1. Khi nào chưa nên chuyển?

Không nên ưu tiên GenShen khi:

- GC không phải bottleneck; latency chủ yếu nằm ở database, network, lock hoặc application code.
- Allocation rate thấp và phần lớn object sống lâu.
- Workload bị giới hạn CPU; concurrent GC có thể cạnh tranh CPU với application thread.
- Heap quá sát memory limit của container, không đủ headroom cho collector.
- Build JDK hiện tại không hỗ trợ Shenandoah.
- Agent, profiler, runtime hoặc nền tảng triển khai chưa được kiểm chứng với collector này.
- Chưa có workload test đại diện và tiêu chí rollback.

Nếu ứng dụng chỉ cần throughput cao và có thể chấp nhận pause, Parallel GC có thể vẫn là lựa chọn phù hợp. Nếu G1 đang đáp ứng SLO ổn định, việc thay đổi chỉ để thử GC mới không phải mục tiêu vận hành.

## 7. Chuẩn bị baseline trước khi thay GC

Trước khi thử GenShen, ghi nhận cấu hình hiện tại:

1. JDK vendor, version, build và platform.
2. GC đang dùng và tất cả JVM flags liên quan.
3. Heap size, container memory limit và CPU quota.
4. Allocation rate, live set và tỷ lệ object sống lâu.
5. Request rate, concurrency, dataset và phân phối payload.
6. Latency p50/p95/p99/p99.9 và throughput.
7. GC pause, tổng GC CPU time và các pha GC.
8. RSS, heap occupancy và thời điểm tăng memory.
9. Sự kiện Full/degenerate GC, allocation failure và OOM.
10. External service latency để phân biệt GC với bottleneck bên ngoài.

### 7.1. Bật unified GC logging

Dùng unified logging thay cho các cờ GC logging cũ:

~~~bash
java \
  -Xlog:gc*,safepoint:file=gc-baseline.log:time,uptime,level,tags \
  -jar app.jar
~~~

Log này cung cấp thời gian, pha GC và safepoint. Khi cần chi tiết hơn, có thể thêm mức log theo tag phù hợp:

~~~bash
java \
  -Xlog:gc*=debug,gc+ergo=debug,safepoint=info:file=gc-detail.log:time,uptime,level,tags \
  -jar app.jar
~~~

Chọn mức log theo câu hỏi chẩn đoán và theo dõi kích thước file. Không bật log debug chi tiết vô thời hạn trong production nếu chưa đánh giá overhead và dung lượng.

### 7.2. Thu thập baseline metrics

| Nhóm | Metric cần lưu |
|---|---|
| Ứng dụng | Throughput, p50/p95/p99/p99.9 latency, error rate |
| Heap | Used/committed/max, live set sau GC, occupancy |
| GC | Pause count/duration, total GC time, young/old cycles nếu có |
| CPU | Process CPU, CPU quota throttling, GC worker activity |
| Memory | RSS/container working set, native memory, OOM/restart |
| Allocation | Bytes allocated/second, object allocation rate |
| Stability | Degenerated/full GC, allocation failure, safepoint duration |

Dùng cùng một cửa sổ đo giữa baseline và candidate. Không so sánh một lần chạy không tải với một lần chạy tải cao.

## 8. Chạy thử Generational Shenandoah

Bắt đầu bằng cấu hình tối thiểu:

~~~bash
java \
  -Xms4g -Xmx4g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc*,safepoint:file=gc-genshen.log:time,uptime,level,tags \
  -jar app.jar
~~~

`4g` chỉ là giá trị minh họa. Dùng heap phù hợp với baseline và bảo đảm còn đủ memory cho metaspace, code cache, thread stacks, native allocations và các thành phần ngoài heap.

Không thay heap size cùng lúc với GC mode trong lần so sánh đầu tiên. Sau khi đã đo tác động của collector, mới thử thay đổi heap nếu có giả thuyết rõ ràng.

### 8.1. So sánh ba cấu hình

Một kế hoạch tối thiểu nên có:

~~~bash
# A — GC hiện tại (ví dụ G1)
java -XX:+UseG1GC -Xms4g -Xmx4g -jar app.jar
~~~

~~~bash
# B — Shenandoah single-generation
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=satb \
     -Xms4g -Xmx4g \
     -jar app.jar
~~~

~~~bash
# C — Generational Shenandoah
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -Xms4g -Xmx4g \
     -jar app.jar
~~~

Các lệnh này giả định runtime hỗ trợ các collector tương ứng. Nếu GC hiện tại là Parallel hoặc ZGC, baseline phải giữ nguyên collector đó thay vì thay bằng G1 chỉ để tiện so sánh.

### 8.2. Giữ nguyên các điều kiện thử nghiệm

- Dùng cùng JDK build cho các lần so sánh GC trong cùng một vòng thử.
- Dùng cùng application artifact và dependency.
- Giữ nguyên heap, container memory limit và CPU quota.
- Dùng cùng dataset, request mix và concurrency.
- Warm-up ứng dụng theo cùng quy trình.
- Chạy đủ lâu để có cả các chu kỳ young và old của GenShen.
- Lặp lại nhiều lần, tốt nhất xen kẽ thứ tự A/B/C để giảm ảnh hưởng của thời điểm chạy.
- Ghi nhận cả throughput, latency, CPU và RSS, không chỉ GC pause.

Không kết luận từ một lần chạy ngắn nếu workload chưa kích hoạt old-generation cycle hoặc chưa tạo đủ allocation pressure.

## 9. Đọc GC log của Generational Shenandoah

Bắt đầu bằng:

~~~bash
grep -i shenandoah gc-genshen.log
~~~

Trên PowerShell:

~~~powershell
Select-String -Path gc-genshen.log -Pattern "Shenandoah"
~~~

Tên phase và nội dung log có thể thay đổi giữa JDK update/build. Dùng log của đúng runtime để xác định các chu kỳ young, old, concurrent, degenerated và full GC.

### 9.1. Những tín hiệu cần chú ý

| Tín hiệu | Ý nghĩa cần kiểm tra |
|---|---|
| Young collection xảy ra thường xuyên | Có thể là hành vi bình thường khi allocation rate cao; đo pause và CPU |
| Old-generation cycle kéo dài | Kiểm tra old live set, tốc độ promotion và khả năng thu hồi |
| Young cycle làm gián đoạn old marking | Kiểm tra tần suất và tiến độ old collection trong log |
| Degenerated GC | Concurrent cycle không hoàn tất đúng kế hoạch; cần điều tra nguyên nhân |
| Full GC | Có thể liên quan áp lực heap, allocation failure hoặc tình huống collector phải fallback |
| Allocation failure | Heap headroom hoặc tốc độ thu gom không đáp ứng allocation demand |
| CPU GC tăng mạnh | Concurrent GC đang tiêu thụ tài nguyên đáng kể |
| p99 tăng nhưng pause vẫn thấp | Tìm bottleneck khác như CPU contention, promotion, lock, I/O hoặc scheduling |

Không diễn giải một log line riêng lẻ như kết luận hiệu năng. Ghép GC log với application latency, CPU throttling và allocation rate trên cùng trục thời gian.

### 9.2. Dùng JFR để phân tích thêm

Có thể ghi JFR trong một cửa sổ benchmark:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -XX:StartFlightRecording=filename=genshen.jfr,settings=profile,duration=5m \
  -jar app.jar
~~~

Sau đó xem tổng quan:

~~~bash
jfr summary genshen.jfr
~~~

JFR giúp đối chiếu GC events với thread activity, allocation, lock contention và application events. Dùng cùng recording settings và workload cho baseline/candidate khi so sánh.

## 10. Tiêu chí lựa chọn dựa trên số liệu

Trước khi thử, xác định mục tiêu cụ thể:

- SLO latency hiện tại là bao nhiêu?
- Có giới hạn pause time cho GC không?
- Throughput tối thiểu cần duy trì là bao nhiêu?
- CPU headroom còn lại trong container là bao nhiêu?
- Memory/RSS có giới hạn cứng không?
- Có chấp nhận tăng CPU để giảm tail latency không?
- Loại lỗi nào sẽ kích hoạt rollback?

### 10.1. Ma trận go/no-go

| Tiêu chí | GO khi | NO-GO khi |
|---|---|---|
| p99/p99.9 latency | Đạt SLO và ổn định hơn baseline | Vượt SLO hoặc biến động mạnh |
| GC pause | Đáp ứng mục tiêu pause | Có pause kéo dài ngoài ngưỡng |
| Throughput | Đạt ngưỡng tối thiểu của sản phẩm | Throughput giảm vượt mức chấp nhận |
| CPU | Còn headroom trong giờ cao điểm | CPU throttling hoặc application CPU bị thiếu |
| Memory/RSS | Nằm trong giới hạn container | Tăng tới sát memory limit hoặc có OOM |
| Young/old cycle | Old collection theo kịp tốc độ promotion | Old generation tăng liên tục hoặc nhiều Full/degenerate GC |
| Stability | Không có allocation failure, OOM hay restart bất thường | Lỗi lặp lại hoặc crash |
| Compatibility | Runtime, agent và công cụ đã kiểm chứng | Có lỗi tương thích chưa giải quyết |

Các ngưỡng số cụ thể phải lấy từ SLO và capacity budget của tổ chức. Không dùng một tỷ lệ giảm pause hay tăng throughput phổ quát làm điều kiện chấp nhận.

### 10.2. Ví dụ scorecard minh họa

Bảng dưới chỉ minh họa cách ghi kết quả, không phải benchmark của JEP 521:

| Metric | G1 baseline | Shenandoah SATB | GenShen |
|---|---:|---:|---:|
| p99 request latency | 240 ms | 190 ms | 145 ms |
| GC pause p99 | 75 ms | 4 ms | 3 ms |
| Throughput | 10.000 req/s | 9.800 req/s | 9.650 req/s |
| Process CPU | 65% | 72% | 76% |
| RSS | 5,1 GB | 5,4 GB | 5,5 GB |
| Full/degenerate GC | 0 | 0 | 0 |

Trong ví dụ, GenShen giảm p99 và pause nhưng dùng thêm CPU/RSS. Quyết định chỉ là GO nếu CPU và memory vẫn nằm trong capacity budget, throughput đáp ứng yêu cầu và kết quả lặp lại ổn định.

Nếu CPU throttling tăng hoặc throughput xuống dưới mức tối thiểu, cần NO-GO dù pause time rất thấp.

## 11. Quy trình canary và rollout

Không thay GC đồng loạt trên toàn bộ fleet ngay từ lần đầu. Triển khai theo từng bước:

1. **Lab:** chạy benchmark có kiểm soát với workload đại diện.
2. **Staging:** kiểm tra integration, startup, heap, logs và tool compatibility.
3. **Canary:** triển khai một nhóm nhỏ instance hoặc một phần traffic.
4. **Observe:** theo dõi p99/p99.9, throughput, CPU, RSS, GC cycle và restart.
5. **Expand:** mở rộng từng bước khi các ngưỡng đều đạt.
6. **Hold:** giữ đủ lâu để quan sát workload peak, promotion và old-generation cycles.
7. **Complete:** ghi lại JVM flags, JDK build, benchmark và điều kiện rollback.

Không chỉ theo dõi vài phút đầu. Generational collector cần đủ thời gian để quan sát object aging, promotion và old-generation collection.

### 11.1. Guardrail tự động

Một pipeline hoặc hệ thống deployment có thể rollback khi:

- p99/p99.9 vượt SLO trong nhiều cửa sổ liên tiếp.
- Throughput thấp hơn ngưỡng tối thiểu.
- CPU throttling tăng vượt capacity budget.
- RSS tiến sát memory limit.
- Pod restart/OOM tăng.
- Degenerated/full GC hoặc allocation failure lặp lại.
- Old-generation occupancy tăng liên tục không có dấu hiệu ổn định.

Ngưỡng, số cửa sổ và thời gian đánh giá phải được thiết lập từ SLO/capacity policy thực tế, không dùng các con số minh họa trong tài liệu làm mặc định production.

## 12. Xây dựng kế hoạch rollback

Rollback phải là một thay đổi cấu hình đã được chuẩn bị và kiểm thử, không phải quyết định viết lệnh trong lúc incident đang xảy ra.

### 12.1. Quay từ GenShen về Shenandoah SATB

Nếu Shenandoah SATB là baseline đã kiểm thử:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=satb \
  -jar app.jar
~~~

Có thể bỏ `ShenandoahGCMode=satb` vì đây là mặc định, nhưng ghi rõ mode giúp dễ kiểm tra cấu hình sau rollback.

### 12.2. Quay về G1

Nếu G1 là collector trước đó:

~~~bash
java \
  -XX:+UseG1GC \
  -jar app.jar
~~~

Gỡ các flag chỉ dành cho Shenandoah khỏi startup script, Dockerfile, Helm values, Kubernetes arguments và biến môi trường.

### 12.3. Quay về Parallel hoặc ZGC

Nếu baseline là Parallel:

~~~bash
java -XX:+UseParallelGC -jar app.jar
~~~

Nếu baseline là ZGC trong JDK 25:

~~~bash
java -XX:+UseZGC -jar app.jar
~~~

Trong JDK 25, ZGC dùng generational mode; không khôi phục cấu hình non-generational ZGC cũ đã bị loại bỏ. Với bất kỳ rollback nào, dùng lại đúng JDK/runtime đã kiểm chứng và chỉ giữ các GC options phù hợp với collector được chọn.

### 12.4. Các bước rollback trong deployment

1. Chọn image/configuration revision đã được xác minh trước đó.
2. Khôi phục đúng GC flag set và các heap options của baseline.
3. Gỡ `ShenandoahGCMode=generational` nếu chuyển sang GC khác.
4. Rollout theo chiến lược an toàn của nền tảng.
5. Kiểm tra JVM khởi động với GC mong muốn.
6. Xác nhận log GC, readiness, throughput, latency và memory đã trở lại mức chấp nhận.
7. Lưu log và recording của phiên bản lỗi để phân tích sau.

**Lưu ý:** đổi JVM flags thường yêu cầu restart process. Không giả định có thể chuyển collector đang chạy bằng một lệnh JMX hoặc `jcmd`.

## 13. Những cấu hình không nên mang từ collector cũ sang

Mỗi GC có tuning knobs và semantics riêng. Khi chuyển collector, không sao chép toàn bộ JVM arguments của GC trước đó.

| Cấu hình cũ | Vấn đề khi chuyển |
|---|---|
| G1 young-generation sizing flags | Không phải tuning knob tương đương cho Shenandoah |
| Parallel GC thread/tenuring tuning | Không mặc định có cùng ý nghĩa với Shenandoah |
| ZGC-specific flags | Không áp dụng cho Shenandoah |
| Shenandoah heuristic `static` hoặc `compact` | Không được hỗ trợ trong Generational Shenandoah |
| JDK 24 experimental unlock | Không cần cho JEP 521 product feature trong JDK 25 |
| Internal/experimental Shenandoah aging flags | Không nên dùng làm cấu hình production phổ quát |
| GC log flags cũ như `-XX:+PrintGCDetails`, `-Xloggc` | Dùng unified logging `-Xlog:gc*` trên JDK hiện đại |

Khi chuyển GC, bắt đầu bằng bộ JVM options tối thiểu: GC selector, heap size và logging cần thiết. Chỉ thêm tuning sau khi log và benchmark cho thấy vấn đề cụ thể.

## 14. Khác biệt với hướng dẫn cũ

Một số tài liệu cũ mô tả Generational Shenandoah là experimental và yêu cầu:

~~~bash
# Cú pháp lịch sử của giai đoạn experimental, không dùng cho JDK 25.
-XX:+UnlockExperimentalVMOptions
~~~

Trong JDK 25, JEP 521 đã hoàn thiện tính năng thành product feature. Cấu hình hiện hành:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -jar app.jar
~~~

Ngoài ra:

- Không mặc định rằng Generational Shenandoah được bật khi chọn Shenandoah GC.
- Không mặc định rằng mọi JDK vendor/platform đều đóng gói Shenandoah.
- Không dùng heuristic `static` hoặc `compact` cho generational mode.
- Không coi Shenandoah mode `satb` là generational; đây là single-generation mode.
- Không lấy bài benchmark của collector khác làm cam kết hiệu năng.
- Không áp dụng các tuning flags nội bộ cũ khi chưa có tài liệu hỗ trợ cho build hiện tại.

## 15. Ma trận kiểm thử nghiệm thu

| Mã | Kịch bản | Kết quả mong đợi |
|---|---|---|
| G1 | Kiểm tra JDK version/vendor và Shenandoah availability | Xác định đúng runtime có hỗ trợ collector |
| G2 | Chạy với `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational` | JVM khởi động với GenShen |
| G3 | Kiểm tra `VM.flags -all` | Mode là generational, heuristic adaptive |
| G4 | Chạy baseline Shenandoah SATB | Có dữ liệu single-generation để so sánh |
| G5 | Chạy baseline GC hiện tại | Giữ nguyên hiệu năng cấu hình production |
| G6 | Chạy workload allocation cao, object chết trẻ | Đo young collection và latency |
| G7 | Chạy workload nhiều object sống lâu | Đo old-generation cycle và live heap |
| G8 | Chạy workload nhiều reference update | Đo CPU/barrier overhead |
| G9 | Chạy peak load với CPU quota production | Kiểm tra concurrent GC có gây CPU throttling |
| G10 | Chạy trong container với memory limit production | Không có OOM hoặc RSS vượt giới hạn |
| G11 | Thu GC log và JFR | Ghép pause, phase, allocation và application latency |
| G12 | Chạy đủ lâu cho old-generation cycle | Xác nhận old collection theo kịp promotion |
| G13 | Kiểm tra degenerated/full GC và allocation failure | Không có sự cố lặp lại ngoài ngưỡng |
| G14 | Canary một phần traffic | Guardrail không kích hoạt rollback |
| G15 | Rollback về collector baseline | JVM khởi động đúng GC cũ, SLO phục hồi |
| G16 | So sánh nhiều lần benchmark A/B | Kết quả lặp lại, không phụ thuộc một lần chạy |

## 16. Bài thực hành tổng hợp

Bạn vận hành một dịch vụ Java xử lý đơn hàng. Khi tải tăng, dịch vụ tạo nhiều DTO, object validation, object mapping và object tạm thời cho mỗi request. GC hiện tại là G1; p99 tăng trong giờ cao điểm, nhưng chưa rõ nguyên nhân có thực sự nằm ở GC hay không.

Thực hiện:

1. Ghi lại JDK vendor/build, GC hiện tại, heap, CPU quota và memory limit.
2. Bật unified GC logging và thu JFR baseline.
3. Đo allocation rate, live heap, p99/p99.9, throughput và CPU.
4. Kiểm tra Shenandoah có trong đúng JDK distribution và platform hay không.
5. Chạy thử Shenandoah SATB để có baseline của cùng collector.
6. Chạy Generational Shenandoah với heuristic adaptive.
7. Dùng cùng dataset, request mix, concurrency, heap và thời gian warm-up.
8. Để workload chạy đủ lâu để quan sát young và old-generation cycles.
9. Đối chiếu GC log với latency, CPU throttling và RSS.
10. Lặp benchmark, tính median và độ phân tán cho từng cấu hình.
11. Viết go/no-go criteria dựa trên SLO và capacity budget.
12. Triển khai canary và kiểm tra guardrail.
13. Thực hành rollback về G1 hoặc Shenandoah SATB trong môi trường staging.
14. Ghi lại lệnh khởi chạy, log xác minh và kết quả sau rollback.

**Sản phẩm nghiệm thu:** bảng so sánh G1/SATB/GenShen, file GC log và JFR, benchmark latency/throughput/CPU/RSS, tiêu chí go/no-go, manifest rollout và lệnh rollback đã được kiểm chứng.

## 17. Checklist áp dụng trong dự án

- Xác minh JDK vendor/build và platform có hỗ trợ Shenandoah.
- Dùng JEP 521 product feature trong JDK 25; không thêm experimental unlock.
- Chọn rõ mode `generational`; không giả định đây là mặc định.
- Giữ heuristic `adaptive` cho generational mode.
- Ghi nhận baseline GC và application metrics trước khi đổi.
- So sánh ít nhất GC hiện tại, Shenandoah SATB và Generational Shenandoah.
- Dùng workload đại diện có allocation/lifetime gần production.
- Giữ heap, CPU quota, memory limit và request mix nhất quán.
- Đo p99/p99.9, throughput, CPU, RSS và các GC cycles.
- Quan sát old-generation progress, promotion, degenerated/full GC và allocation failure.
- Không tuning bằng cờ nội bộ hoặc heuristic không được hỗ trợ.
- Triển khai canary với guardrail rõ ràng.
- Chuẩn bị rollback command và deployment revision trước khi rollout.
- Sau rollback, xác minh collector thực tế qua JVM flags và GC logs.
- Cập nhật tài liệu khi nâng JDK; JDK 27 hiện vẫn để Shenandoah mode mặc định là `satb`.

## Tài liệu tham khảo chính thức

- [JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): chuyển Generational Shenandoah thành product feature trong JDK 25.
- [JEP 404 — Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): lịch sử thiết kế và giai đoạn experimental trước JDK 25.
- [Inside.java — Performance Improvements in JDK 25](https://inside.java/2025/10/20/jdk-25-performance-improvements/): xác nhận trạng thái product feature của JEP 521 trong JDK 25.
- [Inside.java — What's New in Java 25 in 2 Minutes](https://inside.java/2025/10/17/new-in-jdk-25-2-mins/): cú pháp bật Generational Shenandoah sau khi được hoàn thiện.
- [Oracle JDK 27 — The java Command, Shenandoah options](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): tài liệu hiện hành về `UseShenandoahGC`, `ShenandoahGCMode`, mode `satb`/`generational` và heuristic được hỗ trợ. JDK 25 cần được kiểm tra theo đúng vendor build vì không phải binary nào cũng đóng gói Shenandoah.
- [OpenJDK JDK 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): xác nhận Shenandoah mode `satb` mặc định, mode `generational` và heuristic adaptive.
- [Oracle Java SE 25 — HotSpot VM Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/): phương pháp chọn GC và đo throughput, latency, footprint.
- [Oracle Java SE 25 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): đặc tính G1, generation và pause-time goals.
- [Oracle Java SE 25 — G1 Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): baseline và cách đọc GC log khi so sánh.
- [Oracle JDK 27 Release Notes — JEP 523](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): thay đổi G1 thành default collector trong mọi môi trường ở JDK 27.
- [Oracle JDK Migration Guide — Generational ZGC](https://docs.oracle.com/en/java/javase/25/migrate/jdk-migration-guide.pdf): ZGC generational mode và việc loại bỏ non-generational mode trong JDK 25.
