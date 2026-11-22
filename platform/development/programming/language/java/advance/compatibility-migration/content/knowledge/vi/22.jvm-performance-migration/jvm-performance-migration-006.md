# JIT, thời gian làm nóng và biến động hiệu năng

Khi nâng Java từ một JDK cũ lên JDK mới, ứng dụng có thể chạy đúng nhưng biểu đồ hiệu năng lại thay đổi: vài phút đầu CPU cao, request đầu tiên chậm hơn bình thường, throughput tăng dần theo thời gian, một endpoint đột ngột chậm rồi tự hồi phục, hoặc benchmark có kết quả khác nhau giữa các lần chạy cùng một commit. Không phải mọi biến động đều là lỗi; Java Virtual Machine (JVM) có nhiều cơ chế thích nghi với tải, đặc biệt là **Just-In-Time compilation (JIT)**, thu thập profile khi chạy, tối ưu lại mã và loại bỏ giả định tối ưu khi điều kiện thực tế thay đổi.

Trong **Java Advance Compatibility Migration**, câu hỏi cần trả lời không chỉ là “JDK mới nhanh hơn hay chậm hơn?”. Cần phân biệt **startup**, **warm-up**, **steady state**, **tail latency**, **CPU/memory cost**, và ảnh hưởng của môi trường chạy. Cùng một ứng dụng, nếu chỉ so throughput sau 30 phút, ta có thể bỏ qua rủi ro latency trong lúc autoscaling. Ngược lại, nếu chỉ đo 10 giây đầu, ta có thể kết luận sai về tốc độ xử lý lâu dài của JDK.

Bài học này tập trung vào HotSpot JVM — một implementation phổ biến của OpenJDK — với nguyên tắc có thể áp dụng rộng hơn: hiểu contract của JIT, thiết kế thí nghiệm phù hợp, lấy bằng chứng quan sát được và đưa ra quyết định migration dựa trên workload thực tế. Tên compiler tier, flag và sự kiện quan sát có thể khác giữa các JVM/JDK; luôn đối chiếu với runtime thực sự sử dụng.

## 1. Mô hình tư duy: Java code không chạy ở một “tốc độ cố định”

### 1.1. Bytecode và mã máy

Code Java thường được biên dịch thành bytecode trong file `.class`. Khi JVM thực thi, method có thể được:

1. Chạy thông qua interpreter.
2. Được compiler JIT biên dịch thành mã máy.
3. Được biên dịch lại với mức tối ưu cao hơn dựa vào profile thực tế.
4. Bị deoptimization và quay lại trạng thái ít tối ưu hơn khi giả định không còn đúng.
5. Bị biên dịch lại một lần nữa khi workload thay đổi.

Sơ đồ khái quát cho HotSpot:

```text
Java source
     |
     v
javac / build tool
     |
     v
Bytecode (.class)
     |
     v
Class loading, verification, linking, initialization
     |
     v
Interpreter + runtime profiling
     |
     +--------> JIT compilation (các tier)
     |               |
     |               v
     |         Optimized native code
     |               |
     |     assumption invalidated?
     |               |
     +<--- deoptimization / uncommon trap
```

Đây không phải pipeline mà từng method bắt buộc đi qua đầy đủ. Có method ít được gọi nên không bao giờ được tối ưu ở mức cao; có loop nóng được JIT xử lý thông qua cơ chế **on-stack replacement**; có compiled code vẫn tồn tại mà không được gọi lại.

### 1.2. Lợi ích và chi phí của JIT

JIT có thể tối ưu dựa trên dữ liệu mà static compiler chưa biết: loại object thực sự xuất hiện, nhánh thường được chọn, method nào được gọi nhiều, allocation có thể được loại bỏ hay không.

Nhưng JIT cũng tiêu tốn:

- CPU của compiler threads.
- Bộ nhớ cho compiler data structures và code cache.
- Thời gian thu thập profile.
- Chi phí deoptimization/recompilation nếu giả định thay đổi.
- Thời gian trước khi một hot path đạt trạng thái tối ưu ổn định.

Vì thế có trade-off giữa **khởi động nhanh** và **hiệu năng dài hạn**. Một JVM ít tối ưu hơn lúc đầu có thể sử dụng ít CPU để warm up; một JVM tối ưu nhiều hơn có thể đạt throughput cao hơn nhưng tốn tài nguyên lúc bắt đầu.

### 1.3. Hiệu năng là một véc-tơ

Khi đánh giá migration, tối thiểu cần nhìn:

| Chỉ số | Ý nghĩa | Lỗi diễn giải thường gặp |
|---|---|---|
| Startup time | Thời gian process/JVM/app khởi động | Đánh đồng process started với service ready |
| Time to readiness | Khi health/readiness báo có thể nhận tải | Không bảo đảm JIT đã warm up |
| Time to stable throughput | Khi tốc độ xử lý đạt vùng ổn định đã định nghĩa | Đặt một con số warm-up cố định cho mọi hệ thống |
| Throughput | Requests/operations hoàn thành trên đơn vị thời gian | Bỏ qua lỗi, timeout và chất lượng kết quả |
| Mean latency | Độ trễ trung bình | Có thể che các request rất chậm |
| p95/p99 latency | Độ trễ phần đuôi | Cần đủ mẫu, quan tâm coordinated omission |
| CPU time/utilization | Chi phí xử lý | Compiler CPU và application CPU có thể cùng đóng góp |
| Allocation rate | Áp lực tạo object | Không đồng nghĩa trực tiếp với GC pause |
| GC pauses | Thời gian/đặc tính dừng do collector | Không phải mọi latency spike đều do GC |
| RSS/native/code cache | Bộ nhớ ngoài heap và bộ nhớ tiến trình | Heap usage không phải tổng memory footprint |

Một kết luận “JDK mới tốt hơn” phải nói rõ tốt hơn về tiêu chí nào và trong điều kiện nào.

## 2. Interpreter, C1, C2 và tiered compilation

### 2.1. Tiered compilation trong HotSpot

HotSpot truyền thống sử dụng các mức thực thi trong cơ chế **tiered compilation**. Tên và cơ chế này hữu ích để đọc log, nhưng không phải hợp đồng bắt buộc cho mọi JVM implementation.

Mô tả thường gặp:

| Level | Cơ chế | Mục đích điển hình |
|---|---|---|
| 0 | Interpreter | Thực thi và khởi đầu quan sát |
| 1 | C1, ít hoặc không có profiling | Mã biên dịch tương đối nhanh |
| 2 | C1 với profiling hạn chế | Thu thập một phần thông tin chạy |
| 3 | C1 với profiling đầy đủ hơn | Thu profile phục vụ tối ưu sâu |
| 4 | C2 tối ưu mạnh | Tối ưu hiệu năng cho hot code |

Trong một số JDK/cấu hình, level và lựa chọn compiler khác nhau. Không suy luận rằng mọi method luôn được biên dịch lần lượt 0 → 1 → 2 → 3 → 4; compiler policy có thể chuyển tier tùy tốc độ gọi, loop backedge, queue và profile.

### 2.2. C1 và C2 có vai trò khác nhau

- **C1** thường tập trung vào biên dịch nhanh và thu profile, phù hợp cho giai đoạn làm nóng.
- **C2** thường dành nhiều công tối ưu cho hot code, tạo mã máy tối ưu sâu hơn theo profile.
- C2 không bắt buộc cải thiện mọi method; đôi khi thay đổi tối ưu có trade-off khác nhau tùy CPU, workload và code shape.
- Một ứng dụng không dùng HotSpot hoặc sử dụng JVMCI compiler có thể có cơ chế khác, cần ghi lại compiler configuration thực tế.

Để đánh giá, hỏi liệu warm-up có hoàn thành trước lúc nhận tải lớn hay không, chứ không chỉ hỏi “đã chạy qua C2 chưa”.

### 2.3. JIT quyết định method nào đáng tối ưu như thế nào?

JVM có thể dùng counters và profiling data như:

- Số lần method được gọi.
- Số lần loop quay lại nhánh đầu (backedge count).
- Kiểu receiver ở virtual/interface call site.
- Tần suất thực thi branch.
- Kiểu object và đặc điểm truy cập dữ liệu ở một số vị trí.
- Kết quả dự đoán và thông tin hỗ trợ compiler heuristics.

Một method được gọi rất nhiều thường trở thành **hot method**, nhưng “nóng” phụ thuộc policy của JVM, workload và compiler queue, không phải một ngưỡng cố định áp dụng mọi JDK.

### 2.4. Compiler threads tranh CPU với application

JIT không miễn phí. Trong startup hoặc khi traffic tăng nhanh, compiler threads có thể chiếm CPU cùng với:

- Request worker threads.
- GC workers.
- Class loading/initialization.
- TLS handshake, DNS hoặc network I/O.
- Framework proxy/code generation.
- Logging và telemetry pipelines.

Trong container với CPU quota thấp, việc tăng số hot methods cùng lúc có thể tạo compiler queue hoặc CPU contention khiến warm-up kéo dài. Đó là lý do cùng artifact có thể warm up nhanh trên laptop nhưng chậm trong Kubernetes pod giới hạn CPU.

## 3. On-stack replacement (OSR): loop nóng không nhất thiết đợi method kết thúc

### 3.1. Một method chạy rất lâu

Ví dụ:

```java
public static long calculate(long rounds) {
    long total = 0L;

    for (long i = 0; i < rounds; i++) {
        total += i & 31L;
    }

    return total;
}
```

Giả sử method được gọi đúng một lần nhưng loop chạy rất nhiều vòng. Nếu JIT chỉ quyết định khi method được gọi lại, nó khó tối ưu method này trong lúc vòng lặp đang diễn ra.

HotSpot có cơ chế **on-stack replacement (OSR)** để chuyển một frame đang thực thi từ interpreter hoặc compiled tier thấp sang phiên bản compiled tại một điểm phù hợp của loop. Nhờ vậy một long-running loop có thể hưởng lợi khi còn đang chạy.

### 3.2. Vì sao OSR quan trọng khi đo benchmark?

- Vòng lặp quá dài có thể đổi trạng thái compiler giữa phép đo.
- Lần đo đầu có thể bao gồm chi phí chuyển tier.
- Số lượng iteration có thể làm thay đổi compiler policy.
- JIT có thể loại bỏ hoặc biến đổi loop theo semantics, khiến benchmark tưởng đo tính toán nhưng thực chất đo code khác.

Vì vậy, không nên dùng một vòng lặp tự viết và lấy `System.nanoTime()` trước/sau rồi coi đó là microbenchmark khoa học.

### 3.3. OSR không giải thích mọi lần tăng throughput

Throughput có thể tăng khi:

- JIT biên dịch hot methods.
- Cache, connection pool hoặc serializer được warm up.
- JIT inlining/escape analysis tạo ít allocation hơn.
- CPU tăng frequency khi đạt điều kiện phù hợp.
- Hệ thống bên ngoài hoàn tất lazy initialization.

Khi điều tra, cần phân tách compiler events với các yếu tố khác. Chỉ thấy hiệu năng tăng theo thời gian không chứng minh đó là OSR.

## 4. Speculative optimization và deoptimization

### 4.1. JIT dùng giả định dựa trên profile

Giả sử code:

```java
interface PricingRule {
    long calculate(long base);
}

final class FixedRule implements PricingRule {
    @Override
    public long calculate(long base) {
        return base + 100;
    }
}

final class PercentRule implements PricingRule {
    @Override
    public long calculate(long base) {
        return base + base / 10;
    }
}

long total(PricingRule rule, long base) {
    return rule.calculate(base);
}
```

Nếu trong giai đoạn warm-up call site chủ yếu thấy `FixedRule`, JIT có thể tối ưu giả định receiver type đó thường xuyên xuất hiện, có guard và đường fallback khi type khác xuất hiện.

Nếu traffic production sau đó tăng tỷ lệ `PercentRule`, profile không còn đại diện. JVM có thể dùng guard/fallback hoặc thực hiện **deoptimization**, quay về execution state khác rồi biên dịch lại theo thông tin mới.

### 4.2. Deoptimization không tự động có nghĩa lỗi

Deoptimization là cơ chế hợp lệ của optimizing JIT. Nó giúp JVM giữ đúng semantics khi một giả định tối ưu bị vi phạm.

Nhưng một lượng lớn deoptimization/recompilation dưới tải có thể gây:

- Spikes trong latency.
- Compiler CPU tăng.
- Throughput tạm thời giảm.
- Mã máy được thay thế hoặc invalidated.
- Chuyển đổi execution tier nhiều lần khi workload thay đổi.

Không cần coi **mọi** deoptimization event là regression. Quan tâm tần suất, thời điểm, method liên quan và tác động tới SLO.

### 4.3. Uncommon traps và workload lệch

JIT có thể tối ưu mạnh đường đi phổ biến, còn đường đi hiếm gặp được xử lý bằng fallback/uncommon trap. Nếu benchmark chỉ chứa “happy path” còn production có validation errors, input lớn hoặc nhiều kiểu dữ liệu khác nhau, behavior JIT có thể khác rất nhiều.

Khi migration, workload test phải bao gồm:

- Happy path và error path.
- Request nhỏ/lớn.
- Dữ liệu null, empty, malformed theo phạm vi contract.
- Các implementation thực của interface.
- Client/tenant có profile dữ liệu khác nhau.
- Những luồng được gọi ít nhưng có SLO nghiêm ngặt.

### 4.4. Dynamic class loading ảnh hưởng optimization

Framework có thể sinh proxy, subclass, lambda form hoặc class mới khi runtime đã chạy. Khi nạp một class mới làm thay đổi giả định type hierarchy, một số tối ưu đã biên dịch có thể phải được xem xét hoặc invalidated.

Đừng coi kết quả benchmark của một microservice đơn giản là đại diện cho ứng dụng có class loader/plugin system phức tạp. Code loading, reflection và dynamic instrumentation phải được đưa vào workload khi thực sự xuất hiện.

## 5. Inlining: một tối ưu lớn, nhưng không phải lúc nào cũng xảy ra

### 5.1. Ý tưởng cơ bản

Với:

```java
static int addTax(int price) {
    return price + 10;
}

static int checkout(int price) {
    return addTax(price) * 2;
}
```

JIT có thể thay lời gọi `addTax` bằng thân method trong caller (**inlining**). Điều này giảm call overhead và mở ra cơ hội constant folding, elimination hoặc code motion khác.

Inlining không đảm bảo cho mọi method. JIT cân nhắc code size, call frequency, type profile, recursion và budget nội bộ.

### 5.2. Vì sao một refactor nhỏ làm hiệu năng đổi?

Các thay đổi tưởng không quan trọng có thể ảnh hưởng:

- Bytecode size của callee.
- Number/type of receivers ở call site.
- Loại exception path hoặc branch.
- Kích thước compiled method.
- Tính ổn định của class hierarchy.
- Khả năng compiler nhìn xuyên qua abstraction.

Ví dụ thêm một branch kiểm tra logging hoặc metrics vào method nhỏ có thể ảnh hưởng inlining decisions. Không kết luận JDK có regression khi chưa so sánh workload và compiler behavior.

### 5.3. Không tối ưu bằng “method càng ngắn càng nhanh”

Tách method thành nhiều hàm nhỏ có thể giúp readability; JIT thường đủ mạnh để inline khi có lợi. Nhưng cách tổ chức mã phải ưu tiên correctness và maintainability.

Chỉ cân nhắc refactor vì JIT dựa trên profiling/benchmark có bằng chứng. Không nên viết code nghiệp vụ thành một method khổng lồ để “giảm call”, vì điều đó có thể làm compiler khó tối ưu và tăng chi phí bảo trì.

## 6. Escape analysis và allocation elimination

### 6.1. Object mới không luôn dẫn tới heap allocation thực

Ví dụ:

```java
record Point(int x, int y) {}

static int distanceSquared(int x, int y) {
    Point point = new Point(x, y);
    return point.x() * point.x() + point.y() * point.y();
}
```

Nếu JIT chứng minh `point` không escape theo cách ảnh hưởng semantics, nó có thể loại bỏ allocation thực hoặc thay bằng scalar values theo các tối ưu phù hợp.

Điều đó giải thích vì sao số lệnh `new` trong source không phản ánh trực tiếp allocation rate tại runtime.

### 6.2. Tối ưu phụ thuộc profile và code shape

Escape analysis có thể bị ảnh hưởng bởi:

- Method inlining.
- Call graph complexity.
- Interface/virtual dispatch.
- Object được lưu vào field hoặc return ra ngoài.
- Synchronization và native interaction.
- Compiler tier và JVM flags.

Một đoạn code đơn giản không được tối ưu giống nhau trên mọi JDK/architecture. Nếu đo allocation bằng microbenchmark, cần tránh compiler loại bỏ toàn bộ phép tính và cần quan sát allocation thực bằng công cụ thích hợp.

### 6.3. Liên hệ với GC

Khi JIT giảm allocation, GC pressure có thể giảm. Ngược lại, thay đổi optimization khiến allocation tăng có thể tạo nhiều GC hơn. Nhưng **GC và JIT là hai hệ thống khác nhau**: GC pause spike không tự chứng minh JIT có vấn đề, và một optimized allocation path không đồng nghĩa GC không cần chạy.

Khi phân tích regression hãy xem cả compiler events, allocation rate, heap occupancy, GC logs và latency timeline.

## 7. Code cache và các tác động khi có quá nhiều compiled code

### 7.1. Code cache là gì?

JIT lưu compiled native code trong một vùng bộ nhớ gọi là **code cache**. HotSpot có thể chia code cache thành các vùng phục vụ code ở mức tối ưu khác nhau và non-method code tùy version/configuration.

Trong ứng dụng có nhiều class, generated proxies hoặc method hot, code cache có thể trở thành một tài nguyên đáng quan tâm. Nếu thiếu không gian, JVM có thể không biên dịch thêm code như mong muốn hoặc phát cảnh báo liên quan.

### 7.2. Dấu hiệu đáng điều tra

- Cảnh báo dạng code cache đầy hoặc compiler bị hạn chế.
- Tốc độ xử lý không đạt mức thường thấy sau warm-up.
- Compiler activity bất thường.
- Ứng dụng có rất nhiều dynamically generated classes.
- Mức sử dụng code cache tăng tới giới hạn được cấu hình.

Không nên chỉnh `ReservedCodeCacheSize` tùy tiện chỉ vì thấy JVM dùng nhiều native memory. Cần xem số liệu, minimum/maximum và trade-off với total RSS/container memory.

### 7.3. Compilation queue cũng quan trọng

Nếu compiler threads không xử lý kịp số method mới trở nên hot, một phần code tiếp tục chạy ở tier thấp hơn lâu hơn dự kiến. Đây có thể là vấn đề startup under load, nhưng không luôn đồng nghĩa thiếu compiler thread count.

Tăng compiler threads có thể làm CPU contention nặng hơn trong pod nhỏ. Cần so sánh warm-up timeline, compiler CPU và application latency trước khi thay flag.

## 8. Startup, readiness, warm-up và steady state phải đo riêng

### 8.1. Các giai đoạn khác nhau

Một service có thể đi qua:

```text
Process launch
      |
      v
JVM starts + classes load
      |
      v
Framework / application initializes
      |
      v
Readiness endpoint reports ready
      |
      v
Real traffic begins
      |
      v
Caches warm up + JIT compiles hot paths
      |
      v
Performance reaches defined stable region
```

Readiness thường phản ánh app đủ khả năng nhận request theo contract vận hành; nó không cam kết JIT đã đạt throughput tối đa. Nếu readiness chờ toàn bộ warm-up, startup/rollout có thể kéo dài; nếu readiness quá sớm, user traffic có thể chịu latency spike.

### 8.2. Thời gian làm nóng không có hằng số chung

“Warm up 30 giây” có thể phù hợp với một microbenchmark nhưng không có tính tổng quát. Warm-up phụ thuộc:

- Code path nào được gọi.
- Tần suất và phân bố request.
- JVM tiered compiler policy.
- CPU quota và số compiler threads.
- Class initialization/bytecode generation.
- Connection pools, DNS/TLS caches.
- GC, heap size và OS page cache.
- Container/resource throttling.
- Profile dữ liệu đầu vào.

Do đó, định nghĩa thời điểm steady state bằng **quan sát metric và tiêu chí thống kê** hơn là một thời gian cứng áp dụng mọi workload.

### 8.3. Định nghĩa ổn định có thể dựa vào cửa sổ

Ví dụ một nhóm chọn các cửa sổ 60 giây và xem throughput, p95 latency, allocation rate cùng compiler activity. Họ có thể định nghĩa vùng ổn định khi metric biến động trong ngưỡng phù hợp qua nhiều cửa sổ liên tục.

Ngưỡng cụ thể là **quyết định của workload**, không phải chuẩn JVM. Cần tránh định nghĩa thuận tiện đến mức chỉ phần thời gian có kết quả đẹp nhất mới được đưa vào báo cáo.

### 8.4. Scale-out và cold pod

Trong Kubernetes hoặc auto-scaling environment, các pod mới có thể nhận traffic trước khi các hot paths được tối ưu. Nếu load balancer phân đều traffic, người dùng có thể quan sát p99 tăng trong giai đoạn scale-out dù steady-state throughput của mỗi pod cao.

Cần test:

- Startup không tải.
- Startup dưới tải thật.
- Rolling rollout với traffic chuyển dần.
- Cold autoscaling từ số replica thấp.
- Failure/restart storm.
- Recovery sau eviction.
- Periodic deployment hoặc scheduled jobs chạy ngắn.

JIT warm-up đặc biệt quan trọng với serverless/short-lived jobs: một tác vụ kết thúc trước khi tối ưu sâu hoàn thành có thể không thu được lợi ích steady-state.

## 9. Cold performance và steady-state performance có thể mâu thuẫn

### 9.1. Vì sao kết luận một chiều dễ sai?

Giả sử hai cấu hình giả định:

| Trạng thái | Cấu hình A | Cấu hình B |
|---|---:|---:|
| Request đầu tiên | 180 ms | 120 ms |
| 1 phút đầu p95 | 90 ms | 75 ms |
| Sau 20 phút p95 | 35 ms | 45 ms |
| Throughput ổn định | 12.000 req/s | 10.500 req/s |

Các số chỉ minh họa. Cấu hình B tốt cho workload ngắn và startup, cấu hình A tốt hơn ở tải dài. Không thể chọn “bản nhanh hơn” khi chưa biết mô hình triển khai và SLO.

### 9.2. Mục tiêu có thể khác theo loại ứng dụng

| Loại workload | Trọng tâm thường có giá trị |
|---|---|
| CLI chạy vài giây | Startup/cold execution, total elapsed time |
| Batch chạy nhiều giờ | Throughput ổn định, memory/cost |
| API server long-lived | p95/p99, steady throughput, recovery warm-up |
| Serverless function | Cold starts, short-run latency, request concurrency |
| Streaming service | Throughput liên tục, GC/JIT pauses, backpressure |
| Desktop app | Time to interactive, responsiveness |
| Autoscaled microservice | Cold pod behavior + throughput/cost sau ổn định |

Không cố tối ưu JIT cho long-running server rồi áp cùng chính sách lên short-lived batch khi mục tiêu thực tế trái ngược.

## 10. Những nguồn biến động không phải JIT

### 10.1. CPU frequency, turbo boost và thermal throttling

CPU thay đổi clock theo nhiệt độ, công suất, số core được sử dụng và chính sách hệ điều hành. Hai benchmark chạy ở thời điểm khác nhau có thể có mức frequency khác nhau.

Nếu dùng shared CI runners, background jobs hoặc máy laptop đang throttling, sự chênh lệch không nhất thiết do JVM. Với phép đo nghiêm túc, cố định môi trường có thể kiểm soát và ghi lại CPU model, host load, power policy khi phù hợp.

### 10.2. Scheduler và noisy neighbors

Trong VM/container, process có thể bị gián đoạn bởi workload khác. Kubernetes CPU limits/quotas tạo CPU throttling, nhất là khi compiler, application và GC workers cùng đòi CPU.

Cần quan sát:

- Requested vs limited CPU.
- CPU throttled time/count.
- Số cores được container thấy.
- GC/JIT thread count và thread pools.
- Node-level contention.
- Hệ thống cgroup/container runtime.

Nếu container có 1 CPU quota nhưng JVM tự bố trí quá nhiều background workers theo active CPU count khác mong đợi, warm-up và latency có thể xấu. Tuy nhiên không nên tự đặt mọi JVM thread count mà chưa xem container awareness và JDK version.

### 10.3. GC, heap và native memory

Nâng JDK có thể kèm thay GC default/algorithm settings, collector version hoặc heap sizing. Cùng một benchmark, GC pause, allocation rate và memory pressure có thể khác; không thể gán toàn bộ thay đổi latency cho JIT.

Ghi lại:

- GC đang dùng và flags.
- Heap min/max, region/generation settings có chủ đích.
- Container memory limit.
- Metaspace, direct buffers và code cache.
- GC cycle timeline và pause logs.

### 10.4. Class Data Sharing và class initialization

**Class Data Sharing (CDS)** hoặc Application CDS có thể cải thiện các phần liên quan startup/class metadata trong những trường hợp phù hợp. Nhưng CDS không đồng nghĩa mọi method đã được JIT optimize sẵn, và không làm một ứng dụng tự động steady-state.

Nếu app mới dùng CDS hoặc framework AOT optimization đồng thời nâng JDK, cần tách tác động startup/class loading khỏi tác động JIT.

### 10.5. Hệ thống bên ngoài

Benchmark HTTP thực tế còn chịu ảnh hưởng:

- DNS cache.
- TLS session/connection reuse.
- Database connection pool.
- SQL plan cache.
- Redis/CDN cache.
- Disk page cache.
- Remote server autoscaling.
- Load balancer.
- Message broker backpressure.

Nếu request đầu chậm do tạo connection pool hoặc query plan, JIT có thể chỉ là một phần nhỏ. Cần timeline và metric ở nhiều tầng.

## 11. Quan sát JIT bằng công cụ HotSpot

### 11.1. `-XX:+PrintCompilation`

Một cách đơn giản để quan sát compilation activity trên những bản HotSpot hỗ trợ:

```bash
java -XX:+PrintCompilation -jar app.jar
```

Output thường gồm mốc thời gian, compilation ID, tier/level, method name và trạng thái compilation; format cụ thể phụ thuộc JDK version. Một số ký hiệu báo OSR, made not entrant hoặc thay đổi compiled code.

Lệnh này chủ yếu phục vụ môi trường chẩn đoán. Log compilation có thể lớn và thêm overhead; không nên bật đại trà cho mọi production pod nếu chưa cân nhắc chi phí.

### 11.2. Inlining diagnostics

Trong môi trường test, có thể dùng diagnostic options của HotSpot:

```bash
java \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:+PrintCompilation \
  -XX:+PrintInlining \
  -jar app.jar
```

Tùy JDK/flag, output cho biết cơ hội inlining và lý do một lời gọi được hoặc không được inline. Các flags là implementation-specific, có thể đổi hoặc không được hỗ trợ ở JVM khác.

Không coi một dòng “not inline” là bug. Inlining là quyết định heuristic; điều cần đo là tác động tới workload.

### 11.3. Java Flight Recorder (JFR)

JFR cho phép ghi các sự kiện JVM với overhead phù hợp tùy cấu hình. Có thể bắt đầu ghi từ lúc khởi động:

```bash
java \
  -XX:StartFlightRecording=filename=warmup.jfr,settings=profile \
  -jar app.jar
```

Hoặc dùng `jcmd` với process đang chạy khi quyền và runtime hỗ trợ:

```bash
jcmd <pid> JFR.start name=warmup settings=profile
jcmd <pid> JFR.dump name=warmup filename=warmup.jfr
jcmd <pid> JFR.stop name=warmup
```

Chọn recording settings/duration và event categories theo mục tiêu. JFR có thể cung cấp CPU, allocation, GC, class loading và một số thông tin compilation tùy JDK/settings. Cần kiểm tra event type cụ thể có được bật và được hỗ trợ trong JDK mục tiêu hay không.

**Một JFR recording không phải tự động chứng minh causality**. Dùng nó để đối chiếu compilation, safepoints, CPU và latency timeline.

### 11.4. `jcmd` và CodeCache

Một số bản HotSpot cung cấp diagnostic commands để xem thông tin compiler/code cache, ví dụ:

```bash
jcmd <pid> help
jcmd <pid> Compiler.codecache
jcmd <pid> Compiler.queue
```

Danh sách command khả dụng phụ thuộc JDK/VM build. Luôn chạy `jcmd <pid> help` để kiểm tra thay vì phụ thuộc hoàn toàn vào ví dụ từ release khác.

### 11.5. GC và container logs

Để phân biệt JIT với GC hoặc container:

```bash
java \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -Xlog:os+container=info \
  -jar app.jar
```

Các log này hỗ trợ điều tra nhưng không thay thế application metrics hoặc OS/container telemetry. Các option unified logging cụ thể có thể khác theo release; dùng bản JDK thực tế để xác nhận.

### 11.6. Profilers

Async-profiler, Java Mission Control và các công cụ CPU/allocation profiling khác có thể hữu ích. Khi chọn tool, chú ý:

- Có hỗ trợ JDK/OS/architecture hiện tại?
- Sampling engine có đòi quyền perf events/attach?
- Profiling có làm tăng overhead hoặc thay đổi workload không?
- Stack traces có đủ symbols/line info không?
- Có phân biệt Java, native, JIT/compiler và GC threads không?

Không bắt đầu bằng profiling dài hạn trên production nếu không có phạm vi và chính sách dữ liệu phù hợp.

## 12. Microbenchmark đúng: JMH thay vì tự viết vòng lặp

### 12.1. Vì sao `System.nanoTime()` đơn giản thường gây hiểu lầm?

Ví dụ dễ sai:

```java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    int result = calculate(42);
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

Vấn đề:

- Biến `result` không được quan sát, compiler có thể loại bỏ công việc.
- `42` là hằng số nên constant folding có thể xảy ra.
- JIT warm-up diễn ra trong lúc đang đo.
- Loop optimization khác với production call pattern.
- Một lần chạy không phản ánh variability.
- GC/OS scheduling có thể xen vào.
- Không có fork riêng để giảm ảnh hưởng của trạng thái JVM trước đó.

Kết quả có thể là phép đo về compiler optimization hoặc scheduling, chứ không phải chi phí nghiệp vụ mong muốn.

### 12.2. JMH là công cụ benchmark cho JVM

**Java Microbenchmark Harness (JMH)** giúp tổ chức warm-up iterations, measurement iterations, forks, benchmark modes và state lifecycle. Nó không tự bảo đảm benchmark đúng nghĩa nghiệp vụ; thiết kế input/output vẫn quyết định tính hợp lệ.

Ví dụ:

```java
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class PricingBenchmark {
    private long base = 1_234_567L;

    @Benchmark
    public void calculateTotal(Blackhole sink) {
        long result = (base * 110L) / 100L;
        sink.consume(result);
    }
}
```

Các con số về warm-up/measurement/fork là ví dụ, không phải quy tắc tối ưu cho mọi workload. Với một benchmark rất nhanh, cần xem batching và độ dài phép đo; với một method có network I/O, microbenchmark không thể thay load test thực tế.

### 12.3. JMH annotations phải hiểu đúng

| Annotation | Vai trò |
|---|---|
| `@Benchmark` | Đánh dấu operation được benchmark |
| `@State` | Mô tả state và phạm vi chia sẻ |
| `@Setup` / `@TearDown` | Chuẩn bị/dọn dữ liệu theo level |
| `@Warmup` | Xác định giai đoạn trước measurement |
| `@Measurement` | Xác định giai đoạn lấy mẫu |
| `@Fork` | Chạy benchmark trong JVM process riêng |
| `@BenchmarkMode` | Throughput, average time, sample time và các mode khác |
| `Blackhole` | Giúp dữ liệu kết quả được tiêu thụ, giảm nguy cơ dead-code elimination |
| `@Param` | Chạy nhiều giá trị tham số để mô phỏng input variation |

Không dùng `@Setup(Level.Invocation)` để thiết lập state nặng mà không hiểu overhead và bias. Chi phí setup có thể không nằm trong metric chính, khiến benchmark vô tình loại bỏ công việc mà production thật sự phải trả.

### 12.4. Forks và warm-up quan trọng như thế nào?

Mỗi fork là JVM process riêng, giúp giảm tác động của profile/JIT state từ phép đo khác. Warm-up iterations cho hot code cơ hội được compile trước measurement.

Nhưng warm-up không phải “nghi thức” luôn làm benchmark tốt:

- Nếu muốn đo **cold start**, không nên loại bỏ toàn bộ giai đoạn đầu.
- Nếu muốn đo steady state, cần chứng minh warm-up đã đủ.
- Nếu workload đổi phase, một profile tạo từ input cũ có thể không đại diện.
- Nếu benchmark chạy ít fork, kết quả dễ nhạy với JVM/host noise.

Nên báo cáo riêng cold behavior và steady-state benchmark thay vì dùng một bộ cấu hình cho cả hai.

## 13. Bẫy thiết kế benchmark quanh JIT

### 13.1. Constant folding

Nếu input không thay đổi và toàn bộ computation có thể được dự đoán, JIT có thể tính trước. Một benchmark xử lý hằng số có thể cho kết quả tốt hơn rất nhiều so với production input đa dạng.

Giải pháp là dùng state/parameter phù hợp, nhưng vẫn tránh thêm công việc không thuộc nghiệp vụ vào operation cần đo.

### 13.2. Dead-code elimination

Nếu kết quả không được sử dụng, compiler có thể loại bỏ phần tính toán. Dùng `Blackhole` hoặc return value theo pattern JMH hỗ trợ để bảo đảm việc tính toán ảnh hưởng tới kết quả quan sát được.

### 13.3. Escape analysis làm biến mất allocation

Benchmark đo:

```java
new Point(1, 2);
```

có thể không đo heap allocation nếu object không escape và code được tối ưu. Nếu muốn đo chi phí tạo object tồn tại thật, thiết kế state/output phản ánh việc object được sử dụng như production.

### 13.4. Loop-in-loop

Tự đặt vòng lặp 1 triệu lần bên trong `@Benchmark` có thể làm compiler optimize cả loop và cho profile khác với mỗi request thực hiện một lần. JMH đã có harness thực hiện iteration; đừng thêm vòng lặp chỉ để “đồng hồ có số đủ lớn” mà không có mục đích.

### 13.5. Monomorphic benchmark khác production polymorphic

Benchmark dùng đúng một implementation của interface có thể được inline mạnh; production có nhiều implementation có thể không có cùng tối ưu. Nếu hệ thống là plugin-based hoặc nhiều chiến lược xử lý, benchmark với phân bố receiver types thực tế.

### 13.6. Benchmark một thread khác workload nhiều thread

Code có lock, atomics, concurrent collections hoặc memory locality sẽ hoạt động khác khi nhiều threads sử dụng. JMH hỗ trợ đo thread count khác nhau nhưng cần tránh biến benchmark thành stress test không kiểm soát.

### 13.7. Benchmark có network I/O không được nhầm với pure CPU microbenchmark

Nếu operation bao gồm HTTP call, filesystem hoặc database:

- Remote service variability có thể áp đảo chi phí Java code.
- Connection pooling và TLS/DNS caching thay đổi sau warm-up.
- Retry/timeout ảnh hưởng latency distribution.
- Benchmark có thể tạo tải gây throttling ở server đích.

Trong trường hợp này, dùng integration/load test có mô hình traffic và telemetry sẽ có giá trị hơn một microbenchmark đơn lẻ.

## 14. Load test: đo warm-up của ứng dụng thật

### 14.1. Kịch bản traffic phải giống mục tiêu

Một workload thử nghiệm nên mô tả:

- Request mix theo endpoint.
- Input sizes và distribution.
- Concurrency / arrival rate.
- Cache hit/miss ratio.
- Authentication/authorization overhead.
- DB queries và side effects.
- Tỷ lệ error path.
- Network topology và connection reuse.
- Autoscaling policy và resource limits.

Nếu chỉ bắn request GET health endpoint, bạn chủ yếu làm nóng code path đó, không phải tất cả các luồng nghiệp vụ.

### 14.2. Đo theo giai đoạn

Ví dụ kế hoạch đo:

| Giai đoạn | Thao tác | Metric trọng tâm |
|---|---|---|
| T0: start | Khởi động process/container | Startup CPU, class loading, RSS |
| T1: ready | Readiness báo nhận traffic | Time to readiness, initial p95 |
| T2: ramp | Tăng traffic theo kịch bản | Compiler activity, CPU, p99 |
| T3: warm | Giữ workload cố định | Throughput trend, allocation, GC |
| T4: steady | Đủ điều kiện ổn định | p50/p95/p99, throughput/cost |
| T5: phase shift | Đổi traffic mix/data | Deopt, latency spike, recompilation |
| T6: scale/restart | Thêm pod hoặc restart | Cold pod recovery, SLO impact |

Không dùng một khoảng thời gian vừa đủ cho phép đo đẹp nhất rồi gọi là steady state. Điều kiện chọn giai đoạn phải được xác định trước khi xem kết quả.

### 14.3. Open-loop và closed-loop load generation

**Closed-loop** client thường gửi request tiếp theo sau khi request trước hoàn thành. Khi server chậm, tốc độ phát request có thể giảm, làm kết quả latency có vẻ tốt hơn tác động người dùng dưới tải thật.

**Open-loop** load generator theo lịch arrival rate có thể giúp quan sát queueing và tail latency khi server chậm, nhưng phải có capacity và cách ghi nhận failed/dropped requests rõ.

Cần biết workload thực tế là kiểu nào và tránh **coordinated omission** trong measurement. Không bỏ những request timeout/failed khi tính throughput hoặc latency mà không ghi tỷ lệ failure.

### 14.4. Kết hợp app metrics và JVM events

Đối chiếu theo timestamp:

```text
Time 00:00 — JVM/application start
Time 00:15 — Readiness = true
Time 00:18 — Load starts; p99 = 400 ms
Time 00:35 — High compiler CPU; many methods compiled
Time 01:20 — p99 = 90 ms; throughput stable
Time 03:00 — Traffic mix changes
Time 03:05 — Short p99 spike + deoptimization events
Time 03:40 — Stable again
```

Các số chỉ minh họa. Dữ liệu có ý nghĩa khi timestamps của load generator, JVM/JFR, container metrics và server tracing được đồng bộ đủ tốt để so sánh.

## 15. So sánh JDK cũ và mới sao cho công bằng

### 15.1. Một lần chạy không đủ

JIT compilation có thể làm metric biến động giữa các process launches do scheduling, compiler queue, GC, heap layout và workload timing.

Với một benchmark nghiêm túc cần:

1. Chạy nhiều forks/processes.
2. Tách warm-up khỏi measurement nếu mục tiêu là steady state.
3. Ghi phân bố kết quả, không chỉ một số trung bình.
4. Dùng confidence interval hoặc cách đánh giá noise được chọn phù hợp.
5. Chạy trên môi trường ít nhiễu và cố gắng cân bằng thứ tự A/B.
6. Lưu benchmark code, input và JVM flags.
7. Chỉ tuyên bố cải thiện khi chênh lệch đủ lớn so với noise.

Không có một số lần chạy cố định thích hợp cho mọi bài đo. Hiệu ứng nhỏ cần nhiều phép đo hơn; hiệu ứng rõ và ổn định có thể xác nhận nhanh hơn.

### 15.2. Kiểm soát biến số

| Biến | Nên cố định hoặc ghi rõ |
|---|---|
| Application artifact | Cùng commit/JAR khi cô lập JDK |
| Dependency versions | Lock và graph cùng nhau |
| JDK | Vendor, major, update, build |
| JVM flags | Heap, GC, JIT, logging, native access |
| OS/container | Kernel, image, cgroups, CPU/memory limits |
| Hardware | CPU model, architecture, frequency policy |
| Dataset | Size, distribution, warm/cold cache |
| Traffic | Concurrency, arrival rate, request mix |
| Backend | DB/Redis/network version/load |
| Measurement | Duration, repetitions, failures, metric definitions |

Nếu vừa đổi JDK vừa đổi framework/GC/container image, đó là **full stack comparison**. Không được gán toàn bộ khác biệt cho JIT của JDK.

### 15.3. Phân tích kết quả bằng phân bố

Đối với latency, báo cáo trung vị, p95/p99 và số sample. Với throughput, báo cáo mean/median qua nhiều trials và variability. Một chênh lệch 1–2% có thể nằm trong noise của shared runner; một chênh lệch 20% ổn định trên nhiều máy đáng điều tra sâu hơn.

Không nên đặt CI gate “fail nếu throughput giảm 1%” khi baseline noise đã ±5%. Đặt ngưỡng theo mức độ rủi ro, dữ liệu thống kê và chi phí false positives.

### 15.4. Giải thích cold vs steady một cách trung thực

Báo cáo nên có hai kết luận độc lập, ví dụ:

- “JDK đích có p99 giai đoạn 2 phút đầu cao hơn baseline khi autoscale.”
- “JDK đích có throughput steady state tốt hơn tại mức CPU giới hạn như nhau.”

Đây không phải mâu thuẫn. Hệ thống có thể cần chiến lược warm-up hoặc resource budget mới, thay vì rollback toàn bộ JDK.

## 16. JVM flags ảnh hưởng JIT: nên hiểu nhưng không lạm dụng

### 16.1. Giữ mặc định làm baseline trước

HotSpot có nhiều flags điều khiển compiler và optimization. Flags như `-XX:-TieredCompilation` hoặc `-Xint` có thể thay đổi sâu hành vi runtime.

Không nên bắt đầu migration bằng cách copy một danh sách “JVM performance tuning flags” từ blog cũ. Trước tiên đo với defaults được hỗ trợ bởi JDK target, sau đó đổi từng flag có hypothesis và test.

### 16.2. Một số flags quan trọng

| Flag | Ý nghĩa khái quát | Cảnh báo |
|---|---|---|
| `-Xint` | Interpreter-only mode | Chủ yếu chẩn đoán; throughput có thể rất thấp |
| `-XX:-TieredCompilation` | Tắt tiered compilation trong HotSpot hỗ trợ | Làm thay đổi warm-up và steady-state không dự đoán đơn giản |
| `-XX:TieredStopAtLevel=1` | Giới hạn tier tối ưu theo HotSpot | Có thể cải thiện startup ở một số workloads nhưng giảm throughput dài hạn |
| `-XX:+PrintCompilation` | In compilation events | Logging overhead, format phụ thuộc release |
| `-XX:+PrintInlining` | Diagnostic inlining output | Chỉ dành cho điều tra; cần unlock diagnostics |
| `-XX:ReservedCodeCacheSize=...` | Giới hạn code cache | Có trade-off native memory và khả năng compile |
| `-XX:CICompilerCount=...` | Số compiler threads trong những VM hỗ trợ | Tăng threads có thể gây CPU contention |
| `-XX:ActiveProcessorCount=...` | Điều chỉnh CPU count mà JVM dùng cho nhiều chính sách | Ảnh hưởng nhiều subsystem, không chỉ JIT |

Tên flag, default và trạng thái supported/diagnostic/experimental có thể đổi. Dùng:

```bash
java -XX:+PrintFlagsFinal -version
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintFlagsFinal -version
```

trong phạm vi phù hợp để xem flags của runtime thực tế. Không xem output của một JDK khác là kết luận cho runtime production.

### 16.3. `-Xint` dùng để cô lập vấn đề có giới hạn

Chạy interpreter-only có thể giúp kiểm tra một lỗi runtime có liên quan optimization không. Nếu behavior khác giữa interpreted và compiled execution, đó là tín hiệu cần điều tra sâu, nhưng **không đủ để khẳng định JIT bug** vì timing, concurrency và performance thay đổi rất lớn.

Không dùng `-Xint` như giải pháp production cho vấn đề hiệu năng. Nếu nghi lỗi compiler, tạo reproducer tối thiểu, thu thập logs và báo vendor/JDK issue theo kênh chính thức.

### 16.4. Giới hạn JIT tier để tối ưu startup

Một số workload ngắn có thể thử giới hạn tier nhằm giảm compilation cost. Nhưng nếu service long-lived và chạy liên tục, lựa chọn này có thể giảm steady throughput hoặc tăng CPU/request.

Chỉ điều chỉnh sau khi xác định **tổng chi phí công việc** và SLO của cả cold lẫn steady state. Đừng tối ưu vài giây đầu trong khi làm tăng chi phí vận hành hàng tháng.

### 16.5. JVM flags có thể biến mất khi nâng JDK

Một số flag từng được dùng để ép compiler hoặc GC behavior không còn được hỗ trợ, đổi default hoặc bị loại bỏ. Nếu startup script dùng flags cũ, JDK mới có thể cảnh báo hoặc từ chối khởi động.

Phải kiểm kê flags thực tế trong:

- Container command và environment variables.
- Helm/Kubernetes manifests.
- CI scripts.
- `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS`.
- Application server startup files.
- Test task JVM args.
- Java agents và instrumentation tooling.

Bất kỳ flag nào đổi nghĩa đều cần được kiểm chứng, không giữ lại chỉ vì nằm trong runbook từ nhiều năm trước.

## 17. JDK 17 → 21: nên kỳ vọng điều gì?

### 17.1. Không có bảo đảm hiệu năng đồng nhất

HotSpot có thể thay đổi compiler heuristics, intrinsics, code generation, GC integrations và CPU-specific optimizations qua từng JDK release/update. Một application có thể nhanh hơn ở đoạn mã A nhưng chậm hơn ở đoạn B.

Không có quy tắc tổng quát rằng “Java 21 nhanh hơn Java 17 x%” cho mọi workload. Những con số công bố trên benchmark bên ngoài không thay thế workload test của hệ thống.

### 17.2. Giữ chặt JDK update/vendor

So sánh phải ghi:

```text
Baseline:
  JDK vendor: ...
  JDK version/build: 17.x ...
  CPU/OS/container: ...
  Heap/GC/flags: ...

Target:
  JDK vendor: ...
  JDK version/build: 21.x ...
  CPU/OS/container: ...
  Heap/GC/flags: ...
```

Nếu vendor khác nhau, kết quả có thể phản ánh build patches hoặc cấu hình riêng. Có thể cần thêm phép đo baseline/target cùng vendor để cô lập tác động.

### 17.3. Virtual threads không làm JIT tự tối ưu mã nhanh hơn

JDK 21 có virtual threads (JEP 444) để hỗ trợ concurrency cho blocking workflows. Nếu ứng dụng chuyển sang virtual threads, workload có thể tăng số task đồng thời và thay đổi CPU/GC/network pressure.

Đó là **thay đổi kiến trúc concurrency**, không chỉ JIT version. Khi đo, cần phân biệt:

- Nâng JDK nhưng giữ thread model cũ.
- Nâng JDK và chuyển executor sang virtual threads.
- Nâng framework/driver cùng lúc.
- Tăng concurrency khiến backend resource saturation.

Nếu p99 tăng sau chuyển virtual threads, nguyên nhân có thể là tăng số requests cùng lúc, pinning trong các trường hợp liên quan JDK 21 hoặc thiếu backpressure, chứ không nhất thiết JIT tạo mã chậm hơn.

### 17.4. Preview/incubator features và JIT

Nếu source mới dùng vector API hoặc foreign-memory/native code thuộc những API khác nhau theo JDK, benchmark cần kiểm tra feature flags, CPU instructions và JDK generation. Không kết luận hiệu năng chung của HotSpot từ một workload dùng API preview hoặc native library không có trên bản cũ.

## 18. CPU architecture, intrinsics và JVM compiler

### 18.1. Cùng bytecode, mã máy có thể khác

JIT sinh code cho CPU architecture thực tế và có thể sử dụng hardware capabilities/intrinsics phù hợp. Vì vậy cùng một JAR có thể có performance khác giữa:

- x86-64 và ARM64.
- CPU generation cũ/mới.
- Instruction set support.
- Server bare metal và VM.
- Container có CPU quota khác nhau.
- Host với microcode/kernel update khác nhau.

Đừng so sánh Java 17 trên host x86-64 với Java 21 trên ARM64 rồi gán toàn bộ khác biệt cho JDK version.

### 18.2. Intrinsics không phải luôn được chọn

Một số library methods có JVM intrinsic implementations trong một số cấu hình. JIT có thể thay lời gọi bằng machine instructions chuyên biệt nếu điều kiện phù hợp, nhưng điều đó phụ thuộc JVM version, CPU features, flags và call shape.

Ngay cả khi JDK mới thêm intrinsic, throughput toàn ứng dụng chỉ cải thiện đáng kể nếu workload dùng path đó đủ nhiều. Cần profile để biết hot methods thật sự.

### 18.3. Branch prediction và memory locality

Một lần cache miss hoặc branch misprediction có thể đắt hơn nhiều instruction arithmetic. Sự thay đổi object layout, allocation pattern hoặc code generation sau migration có thể ảnh hưởng hardware-level behavior.

Nếu perf regression đáng kể nhưng không thấy nhiều thay đổi JIT events, có thể cần hardware performance counters/profiling theo chính sách môi trường. Không suy luận chính xác nguyên nhân microarchitectural chỉ từ một bảng benchmark.

## 19. Khi warm-up gây vấn đề trong production

### 19.1. Cold pod nhận traffic trước khi sẵn sàng về hiệu năng

Một pod báo readiness sớm rồi nhận cùng mức traffic như pod nóng có thể làm tail latency tăng. Cần mô hình ingress/ramp phù hợp:

- Chỉ cấp traffic sau khi dependency health đủ.
- Có thể tăng traffic dần nếu load balancer hỗ trợ.
- Tránh probe trigger code path có side effect.
- Pre-initialize những cấu phần nặng được biết rõ.
- Dùng workload đại diện để warm up trong staging/canary nếu hiệu quả được xác nhận.
- Đo time-to-SLO chứ không chỉ time-to-readiness.

Warm-up chủ động không nên gửi request nghiệp vụ thay đổi dữ liệu thật hoặc phát sinh chi phí lớn ngoài dự kiến.

### 19.2. Warm-up endpoint không thể làm nóng mọi đường

Một endpoint `/warmup` gọi vài method không bảo đảm mọi branch, receiver type và data size sẽ được compile giống production. Nó cũng có thể tạo profile lệch, làm phát sinh deoptimization khi traffic thật đến.

Nếu warm-up có giá trị, cần xác định các critical paths, phân bố request, input an toàn và mức tải phù hợp. So sánh cold SLO với/không warm-up qua nhiều rollout.

### 19.3. Warm-up bằng traffic tổng hợp có giới hạn

Một chiến lược là phát traffic synthetic tới canary/pod trước khi nhận user traffic. Cần cân nhắc:

- Authentication/authorization và test data.
- Tránh side effects hoặc dùng môi trường transaction rollback.
- Không làm nóng cache với dữ liệu khác xa production.
- Không ảnh hưởng rate limits, audit hoặc observability.
- Không làm tải backend tăng quá khả năng.
- Có timeout và giới hạn warm-up.
- Có fail-safe nếu warm-up không hoàn thành.

Không nên biến một thao tác warm-up thành điều kiện chặn deployment vô hạn.

### 19.4. Short-lived jobs có thể cần tối ưu khác

Một CLI chạy 5–10 giây có thể không hưởng lợi từ C2 compilation vì thời gian khởi động/compile chiếm phần đáng kể. Chiến lược phù hợp có thể là giảm class loading, dependency initialization, JVM memory footprint hoặc số lần khởi động process.

Có thể thử flags startup-oriented hoặc kiến trúc long-lived worker nếu có cơ sở nghiệp vụ. Nhưng không xem các lựa chọn đó là tuning bắt buộc cho mọi service.

## 20. Quy trình điều tra một regression nghi do JIT

### Bước 1: Mô tả triệu chứng bằng metric

Thay vì “JDK 21 chậm”, ghi:

```text
On JDK 17 baseline:
  p99 checkout latency at 300 req/s: 80 ms after 10 min
On JDK 21 target:
  p99 checkout latency at 300 req/s: 130 ms after 10 min
Errors: both < 0.1%
CPU quota: 2 cores; memory limit: 2 GiB
```

Các số là ví dụ, không phải kết quả đo thực. Phải ghi thời điểm warm/steady, workload mix, sample count và JDK build.

### Bước 2: Cô lập các thay đổi

Chạy cùng application artifact, dependencies, flags, OS/container và load generator khi có thể; chỉ thay JDK. Nếu không thể vì bytecode/API compatibility, ghi rõ mọi khác biệt và thiết kế so sánh phù hợp hơn.

### Bước 3: Xem timeline thay vì một điểm cuối

Thu thập p95/p99, throughput, CPU, allocation, GC, class loading và JIT compilation theo từng cửa sổ. Xem regression xảy ra:

- Chỉ lúc startup?
- Khi traffic chuyển phase?
- Khi GC cycle?
- Khi compiler queue tăng?
- Sau khi code cache gần giới hạn?
- Chỉ trên một loại CPU?
- Chỉ khi container bị throttling?

### Bước 4: Tạo reproducer nhỏ nếu có hot path nghi vấn

Dùng profiler để xác định method/operation chiếm phần lớn CPU hoặc allocation, rồi tạo JMH benchmark phản ánh data distribution. Không viết benchmark bằng cách tách method khỏi mọi dependency nếu performance phụ thuộc dispatch/inlining thực tế.

### Bước 5: Kiểm tra compiler evidence

Dùng `PrintCompilation`, JFR hoặc diagnostics phù hợp để xem tier, compilation, code cache, deoptimization và inlining khi cần. Bằng chứng này hỗ trợ hypothesis, không tự chứng minh nguyên nhân.

### Bước 6: Phân biệt JIT với GC/OS/backend

Chạy phép thử có kiểm soát:

- Cùng JVM nhưng giảm external I/O để xem CPU path.
- Cùng workload trên host ít nhiễu.
- So sánh GC timeline.
- Kiểm tra CPU throttling/frequency.
- Kiểm tra database/remote service latency.

Nếu regression biến mất khi đổi OS/container, cần điều tra tầng đó trước khi gán cho compiler.

### Bước 7: Sửa ở đúng tầng

Giải pháp có thể là:

- Cập nhật một dependency/tool chưa hỗ trợ JDK mới.
- Sửa allocation, cache hoặc input data structure.
- Điều chỉnh startup/ramp/pool size.
- Đổi code shape có bằng chứng từ profile.
- Chỉnh JVM flags một cách có kiểm soát.
- Sử dụng bản JDK update có fix đã được vendor xác nhận.
- Giữ bản JDK cũ tạm thời khi chưa có biện pháp an toàn.

Không tự sửa bằng cách tắt JIT lâu dài hoặc giữ flag nội bộ không được hỗ trợ.

### Bước 8: Regression test và đóng issue

Sau khi sửa, chạy lại load/microbench với nhiều trials, so sánh kết quả và đóng bằng evidence: commit, JDK build, flags, graphs, JFR snapshot, benchmark inputs và rollout condition.

## 21. Cách thiết lập CI performance gate mà không tạo nhiễu vô ích

### 21.1. Phân tầng kiểm thử

| Lớp CI | Mục tiêu | Tần suất phù hợp |
|---|---|---|
| Unit + functional test | Correctness, API compatibility | Mọi PR/commit |
| Smoke performance | Phát hiện regression lớn | PR quan trọng hoặc nightly |
| JMH microbenchmark | Hot path tương đối độc lập | Nightly/on-demand theo thay đổi |
| Controlled load test | Warm-up, throughput, p95/p99 | Release candidate/nightly |
| Production canary | SLO, resource cost, real traffic | Mỗi rollout có rủi ro |

Không cần chạy load test dài mỗi PR nếu chi phí quá cao. Nhưng nếu migration JDK là thay đổi lớn, phải có ít nhất một vòng đo kiểm soát trước phát hành.

### 21.2. Threshold phải dựa vào noise

Giả sử benchmark throughput thay đổi ±4% qua nhiều lần chạy trên dedicated runner. Gate fail khi giảm 1% sẽ tạo báo động giả liên tục.

Nên xác định:

- Baseline distribution.
- Minimum detectable regression đáng quan tâm.
- Số trials/forks.
- Rule xử lý outliers.
- Confidence/statistical method phù hợp.
- Thời điểm cần manual investigation.

Không cherry-pick trial tốt nhất. Cũng không xóa mọi outlier nếu outlier là tail latency thật mà khách hàng gặp.

### 21.3. Dữ liệu performance cần có provenance

Mỗi kết quả nên lưu:

```yaml
benchmark:
  name: checkout-hot-path
  revision: <git-commit>
  tool: JMH
runtime:
  jdk_vendor: <vendor>
  jdk_version: <major-update-build>
  os_arch: <os-arch>
  container_cpu_limit: <cpu-limit>
  heap: <heap-configuration>
  gc: <collector>
measurement:
  forks: 3
  warmup_iterations: 5
  measurement_iterations: 8
  metric: avg-time
  units: ns/op
```

Các placeholder cần thay bằng số liệu thật. Metadata giúp diễn giải kết quả nhiều tháng sau và phân biệt regression code với thay đổi test infrastructure.

## 22. Sai lầm thường gặp khi đánh giá JIT và warm-up

| Nhận định sai | Vì sao sai | Cách xử lý |
|---|---|---|
| “Java method chạy ở tốc độ cố định từ lần đầu” | JVM có interpreter, tiered compilation và profile | Đo cold, warm-up và steady riêng |
| “JDK mới chắc nhanh hơn mọi workload” | Tối ưu phụ thuộc code, CPU, JDK update và cấu hình | Benchmark workload thật |
| “Readiness=true nghĩa JIT đã warm” | Readiness và steady performance khác nhau | Đo time-to-SLO |
| “Warm-up luôn là 30 giây” | Phụ thuộc workload, tier và tài nguyên | Xác định bằng metric |
| “p99 tăng nghĩa JIT lỗi” | Có GC, throttling, TLS, DB, OS scheduler | Correlate timeline |
| “Một lần System.nanoTime là benchmark đủ tốt” | JIT optimizations/noise có thể làm sai | Dùng JMH và nhiều forks |
| “JMH tự bảo đảm benchmark có ý nghĩa” | Input, state và output vẫn có thể sai | Thiết kế mô phỏng production |
| “new trong source luôn allocate heap” | Escape analysis/scalar replacement | Xem allocation thực |
| “Mọi virtual call đều chậm” | JIT có type profiling/inlining | Profile call site thực |
| “Deoptimization là bug” | Là cơ chế giữ correctness của JIT | Đánh giá tần suất/tác động |
| “-Xint là cách sửa performance” | Interpreter-only thường giảm throughput mạnh | Chỉ dùng chẩn đoán có kiểm soát |
| “Tăng compiler threads luôn giúp” | Có thể làm CPU contention nặng hơn | Đo queue và CPU quota |
| “Bật CDS nghĩa code đã được tối ưu JIT” | CDS và JIT xử lý các lớp khác nhau | Đo startup và compilation riêng |
| “CPU sử dụng 100% nghĩa app xử lý nhiều nhất” | Có thể compiler/GC/OS contention | Tách CPU theo thread/subsystem |
| “Nhiều request/s hơn luôn tốt hơn” | Có thể tăng errors/timeouts, p99 xấu | Báo cáo throughput cùng SLO |
| “Benchmark app trên local đại diện cloud pod” | CPU/OS/container/quota khác | Test trên môi trường tương đương |
| “Chỉ cần đo một lần sau 20 phút” | Bỏ qua autoscaling, cold starts, phase shifts | Đo nhiều giai đoạn |
| “Bytecode giống nhau nên performance giống nhau” | JIT, CPU, GC và runtime policy khác | Kiểm soát biến số và test |

## 23. Kịch bản thực tế: nâng JDK 17 lên 21 cho dịch vụ API

Giả sử một dịch vụ xử lý đơn hàng có:

- 8 replicas chạy JVM HotSpot.
- Ứng dụng Java 17, mục tiêu Java 21.
- CPU limit mỗi pod là 2 cores.
- HTTP server, JSON serializer, JDBC pool và Redis client.
- Traffic thường xuyên, đôi lúc autoscale thêm pod.
- SLO: p99 không vượt ngưỡng nghiệp vụ tại lưu lượng mục tiêu.

### 23.1. Baseline trên JDK 17

Trước migration, nhóm lưu:

- Image checksum, JDK vendor/build, JVM flags.
- Dependency graph và framework version.
- p50/p95/p99, throughput và error rate theo thời gian.
- CPU throttling, GC, heap và allocation.
- Time to readiness và time to stable p99.
- Startup trace/JFR ở một số pod test.
- Những code paths nóng từ CPU profile.

### 23.2. Đo JDK 21 giữ nguyên ứng dụng

Nếu có thể dùng cùng artifact và dependency stack, chạy trên JDK 21 trong môi trường giống nhau để cô lập runtime delta. Nếu cần nâng framework, ghi rõ đó là thay đổi riêng và thực hiện phép so sánh full-stack bổ sung.

### 23.3. Kịch bản warm-up

Khởi tạo pod mới, chờ readiness rồi đưa traffic theo ramp có kiểm soát. Thu metric mỗi cửa sổ và ghi compilation/GC events. Sau giai đoạn ổn định, chuyển sang traffic mix có nhiều order lines hơn để kiểm tra profile shift.

### 23.4. Một kết quả giả định

Giả sử JDK 21 có throughput steady tăng nhưng p99 ba phút đầu tệ hơn. Trước khi thay flag:

1. Kiểm tra có compiler CPU spike tương ứng không.
2. Kiểm tra connection pool và JSON serializer lazy initialization.
3. Kiểm tra CPU throttling khi compiler/GC và request threads cùng tải.
4. Thử traffic ramp phù hợp và so sánh tail latency.
5. Nếu cần, kiểm tra JIT policy flags từng biến với A/B test.
6. Đảm bảo steady-state throughput không bị hy sinh quá mức.
7. Chọn rollout dựa trên SLO thực, không chỉ một metric tốt.

### 23.5. Khi canary

Giữ một phần lưu lượng tới JDK 21, theo dõi:

- p99 mới/cũ theo cùng request mix.
- Error/timeout/HTTP status.
- CPU/request và cost/throughput.
- Container CPU throttling.
- GC/logging overhead.
- Time-to-SLO của pod mới.
- Memory RSS/code cache khi liên quan.

Nếu vượt ngưỡng đã định, rollback theo kế hoạch. Không tự thêm JVM flags trong production rồi coi đó là kết luận được kiểm chứng.

## 24. Kịch bản thực tế: job batch chỉ chạy 20 giây

Một chương trình CLI xử lý tệp nhỏ và kết thúc sau 20 giây có thể dành phần đáng kể thời gian cho:

1. JVM bootstrap.
2. Class loading và initialization.
3. Framework DI/config setup.
4. File open/parsing.
5. JIT compiler hoạt động.
6. Tính toán thực tế.
7. Shutdown/cleanup.

Với job này, steady-state JMH throughput có thể không quan trọng bằng **total elapsed time**. Nhóm cần benchmark từ process start đến exit, đo cold filesystem/cache condition, và xem cấu phần nào chiếm thời gian.

Các tối ưu đáng cân nhắc có thể là:

- Giảm framework initialization không cần thiết.
- Giảm dependency/class loading.
- Batch operations để tránh khởi động JVM liên tục.
- Sử dụng startup-oriented JVM settings có test.
- Kiểm tra class data sharing hoặc build strategies phù hợp.
- Chuyển sang long-running worker nếu yêu cầu nghiệp vụ cho phép.

Không kết luận “C2 chậm” chỉ vì job ngắn; cần xem chi phí compile thực tế so với initialization/I/O.

## 25. Hồ sơ kiểm chứng và bàn giao

Một đợt migration JDK có quan tâm JIT/warm-up cần có:

1. **Runtime matrix:** vendor, update/build, JDK flags, GC, CPU architecture, OS/container.
2. **Workload contract:** request mix, dataset, arrival/concurrency, SLO, error threshold.
3. **Cold metrics:** startup, readiness, first request, time-to-SLO.
4. **Warm-up evidence:** throughput/latency timeline, compiler activity, allocation/GC.
5. **Steady-state evidence:** repeated trials, throughput, CPU cost, p95/p99.
6. **Phase-shift evidence:** đổi input distribution, request mix, autoscale/canary.
7. **JIT diagnostics:** JFR/PrintCompilation/code cache khi có hypothesis.
8. **Confounding factors:** CPU throttling, container quota, DNS/TLS, cache và DB.
9. **Microbenchmark report:** JMH version/config, forks, input distribution, raw results.
10. **Regression decision:** cải thiện hoặc suy giảm cụ thể theo metric với mức độ tin cậy phù hợp.
11. **Mitigation:** code changes, runtime flags, rollout ramp, resource budget hoặc JDK update.
12. **Release/rollback:** owner, threshold, image/artifact checksum, dashboard và runbook.

### Checklist trước khi phát hành

- [ ] Đã đo riêng startup, readiness, warm-up và steady state.
- [ ] Đã xác định workload thực tế, request mix và input distribution.
- [ ] Đã ghi JDK vendor, update, CPU/OS, container limits và JVM flags.
- [ ] Đã kiểm tra tiered compilation/C1/C2/OSR theo implementation khi cần.
- [ ] Đã nhận diện compiler CPU/queue và code cache khi có dấu hiệu liên quan.
- [ ] Đã phân biệt JIT với GC, class initialization và hệ thống bên ngoài.
- [ ] Đã quan sát p95/p99 và error rate, không chỉ throughput trung bình.
- [ ] Đã kiểm tra cold pod/autoscaling và phase-shift traffic.
- [ ] Đã tránh dead-code elimination, constant folding và benchmark loop sai.
- [ ] Đã dùng JMH phù hợp cho CPU hot paths cần microbenchmark.
- [ ] Đã chạy nhiều fork/trial và đánh giá variability của kết quả.
- [ ] Đã kiểm soát sự khác biệt dependency/framework/image giữa JDK cũ và mới.
- [ ] Đã test artifact cuối trên runtime/hardware đích.
- [ ] Đã xem xét flags JIT dựa trên bằng chứng, không mặc định sao chép flags cũ.
- [ ] Đã xác định readiness/ramp strategy không gây side effect.
- [ ] Đã lưu metrics/traces/profile và kết quả reproducible.
- [ ] Đã chuẩn bị SLO-based rollout/rollback triggers.

**Kết luận:** JIT là một hệ thống tối ưu thích nghi trong runtime; nó có thể làm cùng mã Java chạy nhanh dần, thay đổi tier khi workload chuyển pha hoặc tốn CPU để biên dịch. Vì vậy **warm-up và biến động hiệu năng là một phần phải đo trong Java compatibility migration**, không phải nhiễu có thể bỏ qua. Thay vì hỏi JDK nào “nhanh hơn” một cách tuyệt đối, hãy xác định workload, đo riêng cold và steady state, quan sát JIT cùng GC/OS/container, dùng benchmark có kiểm soát và ra quyết định theo SLO cùng chi phí vận hành thực.
