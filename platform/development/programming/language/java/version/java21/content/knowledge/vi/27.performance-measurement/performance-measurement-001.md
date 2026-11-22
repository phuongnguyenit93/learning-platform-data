# Xây baseline trước khi thay đổi ngôn ngữ, executor hoặc collector

## 1. Baseline hiệu năng là gì?

Baseline là tập số liệu đo được từ một phiên bản ứng dụng trong một môi trường và workload được xác định rõ. Nó là mốc tham chiếu để so sánh sau khi thay đổi code Java, cách thực thi task hoặc garbage collector.

Ví dụ, trước khi chuyển một service từ platform thread pool sang virtual thread, cần biết hệ thống hiện tại xử lý được bao nhiêu request mỗi giây, p95/p99 latency là bao nhiêu, CPU và heap sử dụng thế nào, queue có tăng hay không và database đang chịu tải ra sao. Sau thay đổi, đo lại trên cùng workload và môi trường để biết kết quả thực sự tốt hơn hay chỉ chuyển bottleneck sang nơi khác.

Baseline không phải một con số duy nhất. Một baseline có giá trị cần ghi lại:

- Phiên bản ứng dụng, commit và cấu hình build.
- JDK vendor, phiên bản/update, JVM arguments và hệ điều hành.
- CPU, RAM, container quota/limit và cấu hình máy chạy.
- Dữ liệu đầu vào, phân bố request và mức concurrency.
- Cách chạy benchmark/load test, thời gian warm-up và thời gian đo.
- Throughput, latency distribution, error rate, CPU, memory, allocation và GC.

Nếu thiếu các thông tin này, hai kết quả đo có thể không so sánh được dù đều ghi là “request/second” hoặc “average latency”.

## 2. Xác định câu hỏi và giả thuyết trước khi đo

Trước khi thay đổi, hãy viết rõ điều cần cải thiện và lý do dự đoán thay đổi sẽ có tác dụng. Ví dụ:

| Loại thay đổi | Câu hỏi cần trả lời | Giả thuyết có thể kiểm chứng |
|---|---|---|
| Cấu trúc ngôn ngữ Java | Cách viết mới có giảm allocation hoặc công việc CPU không? | Biểu diễn dữ liệu mới giảm object trung gian mà không đổi semantics |
| Executor | Task có bị giới hạn bởi worker thread, queue hoặc thời gian chờ I/O không? | Virtual thread giúp tăng concurrency của workload blocking I/O |
| Garbage collector | GC có ảnh hưởng đáng kể đến latency hoặc CPU không? | Generational ZGC giảm GC overhead/pause ở workload có nhiều object ngắn hạn |

Không mặc định rằng cú pháp Java mới nhanh hơn cú pháp cũ, virtual thread luôn nhanh hơn pool, hoặc ZGC luôn tốt hơn G1. Mỗi thay đổi tác động đến phần khác nhau của hệ thống và phải được đo bằng metric phù hợp.

Đặt tiêu chí thành công trước khi chạy thử. Ví dụ: p99 latency giảm ít nhất 10% trong khi throughput không giảm, error rate không tăng và CPU/RSS không vượt ngân sách. Ngưỡng cụ thể phải xuất phát từ SLA và giới hạn vận hành của service.

## 3. Chọn đúng cấp độ đo

Một thay đổi có thể cần nhiều cấp độ benchmark. Không dùng microbenchmark để kết luận trực tiếp hiệu năng production nếu thay đổi còn phụ thuộc I/O, queue, network hoặc database.

| Cấp độ | Mục tiêu | Công cụ/cách đo phù hợp |
|---|---|---|
| Microbenchmark | Đo một method, thuật toán, parser hoặc thao tác collection | JMH |
| Component benchmark | Đo một thành phần có executor, serialization, cache hoặc client giả lập | JMH có fixture phù hợp hoặc harness tích hợp có kiểm soát |
| Load test | Đo service dưới workload đồng thời, có queue và dependency | Load generator, test environment và application metrics |
| End-to-end test | Đo latency người dùng qua toàn bộ hệ thống | Distributed tracing, service metrics và load test đại diện |

Microbenchmark trả lời câu hỏi hẹp như “implementation A hay B dùng ít CPU hơn cho một lần parse?”. Load test trả lời câu hỏi hệ thống như “với 500 request đồng thời, p99 latency và error rate thay đổi thế nào?”. Cả hai hữu ích nhưng không thay thế nhau.

## 4. Ghi lại môi trường đo

Hiệu năng Java phụ thuộc mạnh vào runtime và môi trường. Trước mỗi lượt đo, ghi lại ít nhất:

```bash
java -version
javac -version
java -XshowSettings:system -version
```

Các thông tin nên lưu trong report:

| Nhóm | Thông tin cần ghi |
|---|---|
| JDK | Vendor, phiên bản đầy đủ, build/update và kiến trúc (x64/ARM64) |
| Compiler/runtime | `javac` version, `--release`, JVM mode và các JVM flags |
| Phần cứng | CPU model, số core/logical CPU, RAM, storage và loại máy |
| Container | CPU quota, memory limit, cpuset, throttling và runtime/container version |
| Hệ điều hành | OS, kernel, power plan/governor nếu có thể kiểm soát |
| Ứng dụng | Commit, build profile, dependency versions, feature flags |
| Workload | Dataset, request mix, concurrency, think time, payload size và test duration |

Trong container, số CPU JVM nhìn thấy có thể bị ảnh hưởng bởi quota/cpuset. Không chỉ ghi số core vật lý của host; hãy ghi giới hạn CPU thực tế mà process được phép dùng. CPU throttling có thể làm latency tăng dù host còn nhiều CPU.

Giữ cùng JDK và phần cứng khi mục tiêu là so sánh code/executor/collector. Nếu đang đánh giá nâng cấp JDK, đó là một biến độc lập khác; hãy ghi rõ và thiết kế ma trận thử nghiệm riêng.

## 5. Xây dựng workload đại diện

Workload phải phản ánh hành vi thật của ứng dụng. Một endpoint chỉ nhận payload nhỏ không đại diện cho service có nhiều upload, query phức tạp và request phụ thuộc remote API.

Hãy mô tả workload bằng các thuộc tính có thể lặp lại:

- Tỷ lệ từng loại request hoặc tác vụ.
- Payload size và phân bố dữ liệu (nhỏ, trung bình, lớn).
- Số request đồng thời và tốc độ gửi request.
- Tỷ lệ cache hit/miss.
- Tỷ lệ thành công, lỗi, timeout và retry.
- Thời gian chờ I/O, CPU work và thời gian giữ connection/lock.
- Dữ liệu đầu vào và random seed nếu có yếu tố ngẫu nhiên.

Nên dùng cùng dataset hoặc cùng seed cho các lượt A/B. Nếu dữ liệu thay đổi, chẳng hạn cache đã warm ở lượt thứ hai nhưng cold ở lượt đầu, kết quả có thể phản ánh khác biệt dữ liệu thay vì khác biệt code.

Với service có database hoặc upstream, phải kiểm soát cả dependency. Dùng cùng database snapshot, index, connection pool, quota và trạng thái cache; nếu không thể, ghi lại sai khác và tránh so sánh trực tiếp như một thử nghiệm A/B công bằng.

### 5.1. Chọn mô hình tải: closed-loop hay open-loop

- **Closed-loop**: client gửi request tiếp theo sau khi request trước hoàn tất. Mô hình này phù hợp để mô phỏng một số user có số request đồng thời giới hạn, nhưng khi service chậm, tốc độ phát request tự giảm theo.
- **Open-loop**: load generator phát request theo arrival rate đã định trước, độc lập với thời gian hoàn tất của request trước. Mô hình này hữu ích khi cần kiểm tra hệ thống ở một tốc độ đến cố định và quan sát queue/backlog khi service không theo kịp.

Nếu chỉ dùng closed-loop để kiểm tra một service đang quá tải, tốc độ phát request có thể giảm cùng latency và che bớt queueing delay. Đây là một dạng coordinated omission. Với workload có arrival rate cố định, hãy dùng load generator có thể ghi nhận thời điểm request được lên lịch và latency từ thời điểm đó; đồng thời theo dõi request bị drop hoặc không được phát đúng lịch. Bảo đảm chính load generator không trở thành bottleneck.

## 6. Chọn metric: không chỉ nhìn average

Một baseline nên có nhiều metric vì throughput, latency và tài nguyên có thể đánh đổi với nhau.

| Metric | Ý nghĩa | Câu hỏi trả lời |
|---|---|---|
| Throughput | Số request/task hoàn tất trong một đơn vị thời gian | Hệ thống xử lý được bao nhiêu việc? |
| p50 latency | Median thời gian hoàn tất | Trải nghiệm điển hình ra sao? |
| p95/p99 latency | Độ trễ ở nhóm request chậm | Tail latency có cải thiện không? |
| Error/timeout rate | Tỷ lệ request thất bại hoặc hết hạn | Tăng throughput có làm giảm độ tin cậy không? |
| CPU utilization/time | CPU tiêu thụ trong khoảng đo | Cần bao nhiêu năng lực tính toán? |
| Heap/RSS | Java heap và bộ nhớ process | Có vượt giới hạn container/máy không? |
| Allocation rate | Số byte object được cấp phát theo thời gian hoặc mỗi operation | Code có tạo nhiều object trung gian không? |
| GC pause/CPU | Thời gian pause và CPU dành cho GC | GC tác động thế nào đến latency và throughput? |
| Queue wait/depth | Thời gian và số tác vụ chờ | Bottleneck nằm ở admission control hay worker/resource? |
| Context switches/thread count | Hoạt động scheduler và số thread | Có tạo quá nhiều platform thread hoặc tranh chấp không? |

Average latency có thể che giấu một nhóm nhỏ request rất chậm. Với service có SLA, p95/p99 thường quan trọng hơn việc chỉ báo cáo mean. Đồng thời phải xem throughput và error rate: hệ thống có thể giảm latency đơn giản vì từ chối nhiều request hơn.

## 7. Microbenchmark Java bằng JMH

JVM có JIT compiler, class loading, profile collection và nhiều cơ chế tối ưu runtime. Đo một method bằng vòng lặp `System.nanoTime()` tự viết dễ bị ảnh hưởng bởi dead-code elimination, constant folding, loop optimization, warm-up và các lần chạy không độc lập.

JMH (Java Microbenchmark Harness) được thiết kế để đo microbenchmark trên JVM. Nó hỗ trợ warm-up, measurement iterations, forks, benchmark modes và profiler. Không nên dùng một đoạn `main` có vòng lặp đơn giản làm bằng chứng duy nhất cho khác biệt nhỏ giữa hai implementation.

OpenJDK khuyến nghị khởi tạo benchmark trong một project JMH độc lập theo Maven archetype để annotation/bytecode processor tạo benchmark harness đúng cách và giảm sai lệch do cấu hình project hoặc IDE. Có thể tích hợp vào project hiện có, nhưng cần xác minh annotation processing và cách chạy benchmark.

Ví dụ benchmark hai cách kiểm tra chuỗi:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class StringCheckBenchmark {
    @Param({"java", "", "  ", "a longer input value"})
    public String input;

    private String normalized;

    @Setup
    public void setup() {
        normalized = input.trim();
    }

    @Benchmark
    public boolean trimThenCheck() {
        return !input.trim().isEmpty();
    }

    @Benchmark
    public boolean preNormalizedCheck() {
        return !normalized.isEmpty();
    }
}
```

JMH tiêu thụ kết quả trả về của benchmark để hạn chế compiler loại bỏ công việc không quan sát được. `@Param` giúp kiểm tra nhiều input; `@Warmup`, `@Measurement` và `@Fork` tách giai đoạn warm-up, đo và JVM process độc lập.

Hai method trong ví dụ trả về cùng kết quả với `input` bất biến: method thứ nhất gọi `trim()` ở mỗi operation, method thứ hai dùng giá trị đã trim một lần trong setup. Vì vậy, benchmark này đo chiến lược tiền xử lý và tái sử dụng kết quả, không phải một phép so sánh cú pháp thuần túy. Chỉ dùng cách tiền xử lý nếu vòng đời dữ liệu cho phép tái sử dụng giá trị đó; nếu input thay đổi thì phải tính lại. Trong benchmark thực tế, luôn xác minh output và side effect tương đương trước khi so sánh.

### 7.1. Chọn benchmark mode

| Mode | Đo gì? | Khi dùng |
|---|---|---|
| `Throughput` | Số operation mỗi đơn vị thời gian | So sánh khả năng xử lý của method |
| `AverageTime` | Thời gian trung bình mỗi operation | Đo chi phí trung bình của một thao tác |
| `SampleTime` | Lấy mẫu thời gian từng operation để xem distribution | Quan sát percentile trong microbenchmark |
| `SingleShotTime` | Thời gian một lần thực thi benchmark | Đo đường chạy một lần, cần chú ý setup/JIT và fork |

Không trộn các đơn vị khi so sánh. Ghi rõ mode, output unit, số fork, warm-up và measurement trong báo cáo. Với tail latency của toàn service, dùng load test và histogram có độ phân giải phù hợp; không suy ra p99 production từ một microbenchmark đơn lẻ.

### 7.2. Đo allocation và profiler

JMH có thể chạy GC profiler để quan sát allocation:

```bash
java -jar target/benchmarks.jar StringCheckBenchmark -prof gc
```

Profiler `gc` có thể báo allocation rate, bytes/op và các chỉ số liên quan đến GC. Những số liệu này giúp phân biệt method nhanh hơn do giảm allocation hay chỉ do khác biệt khác trong JIT/runtime.

Không bật profiler cho một lượt đo rồi so sánh trực tiếp với lượt không profiler nếu profiler làm thay đổi overhead. Dùng profiler để giải thích, sau đó chạy lại phép đo chính với cùng điều kiện.

## 8. Kiểm soát JIT warm-up và tính ổn định

Java không nhất thiết thực thi code theo cùng một cách ngay từ lần gọi đầu. JVM có thể diễn giải bytecode trước, thu thập profile và biên dịch các method nóng thành native code sau đó.

Để giảm sai lệch:

- Có warm-up đủ dài để code đi vào trạng thái ổn định phù hợp với workload.
- Dùng nhiều fork độc lập để giảm ảnh hưởng profile/JIT tích lũy giữa các lần đo.
- Không lấy thời gian khởi động JVM làm thời gian steady-state nếu mục tiêu là hiệu năng sau warm-up.
- Nếu startup latency là yêu cầu, đo startup riêng như một chỉ tiêu độc lập.
- Không chạy benchmark cạnh tranh CPU với build, test hoặc workload khác.
- Giữ cấu hình JVM giống nhau giữa các biến thể, trừ biến đang được đánh giá.

Không có một số iteration warm-up đúng cho mọi chương trình. Một method thuần CPU có thể ổn định nhanh hơn service có class loading, cache warm-up, connection setup và JIT compilation trong nhiều đường code.

## 9. Baseline trước khi thay đổi cấu trúc ngôn ngữ Java

Khi chuyển từ một cách viết Java sang construct mới, trước tiên phải bảo đảm hai phiên bản có cùng semantics:

- Cùng input/output và thứ tự xử lý.
- Cùng exception behavior và validation.
- Cùng null handling, mutability và side effect.
- Cùng concurrency guarantees và thread-safety.
- Cùng cách cấp phát hoặc ownership tài nguyên nếu đó là một phần yêu cầu.

Ví dụ, khi thay chuỗi `instanceof` và cast bằng pattern matching, hoặc thay class dữ liệu bằng record, hãy kiểm tra bytecode/JIT và đo đúng tác vụ thực tế. Record có thể giúp code rõ ràng hơn nhưng không mặc định làm thuật toán nhanh hơn. Pattern matching có thể giảm code lặp nhưng lợi ích hiệu năng phụ thuộc số nhánh, profile và cách JVM tối ưu.

Quy trình so sánh:

1. Tạo benchmark riêng cho đoạn code thay đổi.
2. Đưa input đại diện vào `@Param` hoặc fixture.
3. Xác minh hai implementation trả kết quả tương đương.
4. Chạy JMH với cùng JDK, flags, forks, warm-up và measurement.
5. Đo throughput/average time và allocation nếu liên quan.
6. Nếu đoạn code nằm trong request path, xác nhận lại bằng load test end-to-end.

Không kết luận một construct ngôn ngữ “nhanh hơn” từ benchmark không tương đương hoặc từ số đo một lần chạy.

## 10. Baseline trước khi thay đổi executor

Thay executor có thể thay đổi số thread, cách xếp hàng, backpressure, scheduling, context propagation và cách xử lý cancellation. Vì vậy, phải đo cả hiệu năng lẫn hành vi vận hành.

### 10.1. Các biến cần kiểm soát

| Biến | Cần ghi lại |
|---|---|
| Executor type | Fixed thread pool, work-stealing pool, virtual-thread-per-task executor hoặc executor hiện tại |
| Worker/thread count | Số platform thread hoặc chính sách tạo virtual thread |
| Queue | Loại queue, capacity, rejection policy và queue depth |
| In-flight limit | Số task/request đồng thời được phép thực hiện |
| Task mix | Tỷ lệ CPU-bound, blocking I/O và thời gian mỗi loại |
| Downstream limits | DB connection pool, HTTP pool, quota và semaphore |
| Context | Trace ID, security context, ThreadLocal/InheritableThreadLocal và logging context |
| Shutdown/cancellation | Cách dừng task, timeout, interrupt và đóng executor |

### 10.2. So sánh platform thread pool và virtual thread

Virtual thread trong Java 21 phù hợp với workload có nhiều tác vụ blocking I/O. `Executors.newVirtualThreadPerTaskExecutor()` tạo một virtual thread mới cho mỗi task; nó không phải pool có số worker cố định và không tự giới hạn concurrency.

Ví dụ executor:

```java
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    List<Future<Response>> futures = requests.stream()
            .map(request -> executor.submit(() -> callBlockingService(request)))
            .toList();

    for (Future<Response> future : futures) {
        process(future.get());
    }
}
```

Đây là ví dụ minh họa mô hình thread-per-task; code production cần chính sách giới hạn số request được nhận và xử lý lỗi/cancellation rõ ràng. Không submit vô hạn task chỉ vì virtual thread có chi phí thấp hơn platform thread.

Khi so sánh với pool cũ, cần giữ cùng mức concurrency được phép và cùng giới hạn downstream. Nếu bản virtual thread gửi gấp mười lần request đồng thời đến database, kết quả latency xấu hơn có thể do database quá tải chứ không chứng minh virtual thread chậm hơn.

### 10.3. Metric riêng cho executor

Theo dõi:

- Task submitted, started, completed và rejected.
- Queue depth và queue wait time.
- Task execution time và tổng thời gian chờ I/O.
- Số platform thread, virtual thread đang chạy/chờ và số task in-flight.
- Semaphore wait time và số permit đang sử dụng.
- Downstream pool utilization, timeout và retry.
- CPU, memory và context switching.

Một executor có throughput cao nhưng queue wait tăng liên tục có thể đang tích lũy backlog. Cần xem cả thời gian hoàn tất và độ ổn định của queue, không chỉ số task được submit.

## 11. Baseline trước khi thay đổi garbage collector

Collector có thể tác động đến pause time, CPU overhead, allocation headroom, footprint và throughput. Khi so sánh collector, phải giữ workload và giới hạn bộ nhớ tương đương, đồng thời ghi lại JVM flags chính xác.

Ví dụ cấu hình trên Java 21:

```bash
# G1 GC
java -Xms4g -Xmx4g -XX:+UseG1GC -Xlog:gc*,safepoint:file=g1-gc.log:time,uptime,level,tags -jar application.jar

# Generational ZGC trên Java 21
java -Xms4g -Xmx4g -XX:+UseZGC -XX:+ZGenerational -Xlog:gc*,safepoint:file=zgc-gc.log:time,uptime,level,tags -jar application.jar
```

Trong Java 21, `-XX:+ZGenerational` bật chế độ generational cho ZGC. Không nhầm với các JDK mới hơn, nơi trạng thái mặc định của Generational ZGC có thể đã thay đổi. Xác minh flags trên đúng JDK đang benchmark.

Heap `4g` trong ví dụ chỉ minh họa cách giữ cùng `Xms`/`Xmx`; không phải cấu hình phù hợp cho mọi collector hoặc workload. Cần bảo đảm container có đủ memory ngoài heap cho metaspace, thread stacks, direct buffers, native libraries và overhead của JVM.

### 11.1. Metric GC cần thu thập

| Metric | Ý nghĩa |
|---|---|
| Pause duration distribution | Mức dừng ứng dụng và tail pause |
| GC CPU time | CPU tiêu thụ bởi collector |
| Allocation rate | Tốc độ tạo object |
| Live set/heap after GC | Lượng object còn sống sau thu gom |
| Heap occupancy/headroom | Khoảng trống còn lại cho allocation trong khi GC chạy |
| Promotion/old-generation growth | Xu hướng object sống lâu và áp lực old generation |
| Allocation stall | Tình huống allocation phải chờ GC giải phóng đủ dung lượng |
| Process RSS/native memory | Footprint tổng thể ngoài Java heap |

Không chỉ so sánh max pause hoặc average pause. Một collector có pause thấp hơn nhưng dùng CPU nhiều hơn hoặc tăng RSS vượt container limit có thể không phù hợp. Với service nhạy latency, cần xem p95/p99 request latency song song với GC pause.

### 11.2. Dùng JFR để bổ sung GC log

Có thể ghi JFR trong một khoảng đo:

```bash
jcmd <pid> JFR.start name=performance settings=profile duration=5m filename=performance.jfr
jfr summary performance.jfr
```

JFR giúp xem allocation, GC, CPU sampling, thread scheduling và các sự kiện runtime. Dùng GC log để theo dõi chu kỳ collector và JFR để liên kết sự kiện GC với hoạt động ứng dụng. Bảo đảm cấu hình recording tương đương giữa các lượt so sánh.

## 12. Thiết kế lượt đo A/B công bằng

Một quy trình đo có thể thực hiện như sau:

1. **Chốt biến thể A và B**: ghi commit, cấu hình và đúng một nhóm thay đổi cần đánh giá.
2. **Giữ môi trường cố định**: cùng máy, CPU quota, memory limit, JDK build, dataset và dependency state.
3. **Warm-up**: chạy đến khi JIT, cache và kết nối đạt trạng thái phù hợp với mục tiêu đo.
4. **Đo nhiều lần độc lập**: chạy nhiều fork hoặc nhiều lượt load test; không lấy một lần chạy duy nhất làm kết luận.
5. **Đổi thứ tự thử nghiệm**: nếu có thể, xen kẽ A/B hoặc randomize thứ tự để tránh ảnh hưởng nhiệt độ, tải nền và drift theo thời gian.
6. **Thu thập metric đồng thời**: latency histogram, throughput, error rate, CPU, RSS, allocation, GC, queue và downstream.
7. **Kiểm tra tính hợp lệ**: workload có giống nhau không, có timeout/retry bất thường không, cache có cùng trạng thái không?
8. **Tính mức thay đổi**: so sánh median của các lượt và phân bố kết quả; xem độ biến thiên thay vì chỉ lấy số đẹp nhất.
9. **Chạy lại nếu nhiễu lớn**: tìm nguyên nhân như CPU throttling, background job, GC warm-up hoặc dependency chậm.
10. **Lưu artifact**: command line, logs, JFR, report JMH, dataset version và commit.

Ví dụ tính phần trăm cải thiện throughput:

\[
\text{Improvement}(\%) = \frac{T_B - T_A}{T_A} \times 100
\]

Với latency, giảm là tốt hơn nên có thể tính:

\[
\text{Latency reduction}(\%) = \frac{L_A - L_B}{L_A} \times 100
\]

Không so sánh throughput của A với p99 latency của B hoặc so sánh các lượt có mức concurrency khác nhau mà không giải thích. Hãy đặt các metric thành một bảng cùng đơn vị và cùng workload.

## 13. Ví dụ mẫu bảng baseline

| Thuộc tính | Baseline A | Candidate B |
|---|---:|---:|
| Commit/configuration | `abc123` | `def456` |
| JDK | Java 21.x vendor/build | Cùng build |
| Executor | Fixed pool, 32 workers | Virtual thread per task + cùng in-flight limit |
| Collector | G1 | G1 (giữ nguyên để cô lập thay đổi executor) |
| Heap | `-Xms4g -Xmx4g` | Cùng giới hạn heap |
| Request concurrency | 200 | 200 |
| Throughput | 1,000 req/s | 1,120 req/s |
| p50 latency | 45 ms | 42 ms |
| p95 latency | 110 ms | 98 ms |
| p99 latency | 240 ms | 205 ms |
| Error/timeout rate | 0.10% | 0.08% |
| CPU average | 68% | 74% |
| Process RSS | 5.2 GB | 5.8 GB |
| GC CPU | 7% | 9% |

Các con số trong bảng là dữ liệu minh họa để trình bày cách ghi baseline, không phải kết quả benchmark hoặc khuyến nghị về hiệu năng của Java 21. Trong báo cáo thật, thay bằng số liệu đo được và ghi rõ thời lượng, số lượt, độ phân tán cùng môi trường.

Candidate B trong ví dụ chỉ thay executor; collector được giữ nguyên để cô lập tác động. Nếu muốn đánh giá Generational ZGC, hãy chạy một lượt A/B riêng giữ nguyên executor và thay collector. Candidate B tăng throughput và giảm latency nhưng dùng CPU/RSS nhiều hơn. Quyết định triển khai phải xét ngân sách tài nguyên và SLA, không chỉ chọn cột có nhiều số tốt hơn.

## 14. Các sai lầm thường làm baseline mất giá trị

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Chỉ chạy benchmark một lần | Bị ảnh hưởng bởi JIT, OS scheduling và tải nền | Dùng warm-up, nhiều fork và nhiều lượt đo |
| Đo method bằng vòng lặp `nanoTime()` đơn giản | Có thể bị tối ưu dead code, constant folding hoặc loop optimization | Dùng JMH cho microbenchmark |
| So sánh hai implementation không cùng semantics | Đo hai công việc khác nhau | Xác minh output, exception và side effect trước khi đo |
| Chỉ báo cáo average latency | Che giấu tail latency | Báo p50/p95/p99 và histogram |
| Tăng concurrency ở một biến thể | Làm thay đổi workload | Giữ cùng arrival rate/in-flight limit hoặc công bố rõ mục tiêu khác |
| Đổi executor và collector cùng lúc | Không biết biến nào tạo ra thay đổi | Thay từng yếu tố, sau đó mới đo tương tác nếu cần |
| Chạy A và B trên hai máy khác nhau | Phần cứng, quota và noise khác nhau | Dùng cùng máy hoặc kiểm soát môi trường chặt chẽ |
| Bỏ qua error rate và retry | Throughput có thể tăng giả tạo do xử lý sai hoặc retry | Đo lỗi, timeout và request hoàn tất thành công |
| So sánh GC chỉ bằng pause lớn nhất | Không phản ánh CPU, allocation và footprint | Kết hợp GC log, JFR và application latency |
| Dùng virtual thread nhưng không giới hạn downstream | Gây quá tải database/API | Giữ cùng concurrency cap, dùng semaphore/backpressure |
| Chỉ tăng heap để làm GC đẹp hơn | Có thể vượt memory limit hoặc che memory leak | Giữ ngân sách memory và theo dõi RSS/live set |

## 15. Checklist trước khi chấp nhận thay đổi hiệu năng

Trước khi kết luận thay đổi có lợi, hãy xác nhận:

1. Baseline và candidate chạy cùng workload, dữ liệu và môi trường.
2. JDK vendor/build và JVM arguments đã được ghi lại.
3. Semantics của code không thay đổi ngoài chủ đích.
4. Có warm-up, nhiều fork/lượt đo và thời gian đo đủ ổn định.
5. Throughput, p50/p95/p99 và error rate được xem cùng nhau.
6. CPU, heap, RSS, allocation và GC overhead nằm trong ngân sách.
7. Executor queue, in-flight limit và downstream capacity được kiểm soát.
8. Với collector, GC log/JFR và application latency được đối chiếu.
9. Kết quả có độ ổn định; mức cải thiện lớn hơn nhiễu của phép đo.
10. Có artifact đủ để người khác tái lập và xác minh kết quả.

## 16. Tài liệu tham khảo chính thức

- [OpenJDK JMH](https://github.com/openjdk/jmh): framework chuẩn cho JVM microbenchmark, annotation và profiler.
- [JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples): ví dụ về dead-code elimination, constant folding, state, forks, warm-up và benchmark design.
- [Java SE 21 — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): executor lifecycle và cách quản lý task.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mô hình virtual thread trong Java 21 và hướng dẫn sử dụng.
- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439): thiết kế Generational ZGC được đưa vào Java 21.
- [Java 21 Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/): cấu hình, log và đánh giá collector.
- [Java 21 `jcmd` documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): ghi JFR và thu thập thông tin runtime.

Baseline đáng tin cậy giúp tách hiệu quả thực của thay đổi khỏi nhiễu do JIT, workload, phần cứng hoặc cấu hình JVM. Hãy xác định giả thuyết và metric trước, đo microbenchmark bằng JMH khi câu hỏi ở cấp method, đo load/end-to-end khi câu hỏi ở cấp service, rồi giữ cùng điều kiện khi so sánh code, executor hoặc collector. Chỉ chấp nhận thay đổi khi kết quả lặp lại được và cải thiện đúng mục tiêu mà không vượt ngân sách latency, error rate, CPU hoặc memory.
