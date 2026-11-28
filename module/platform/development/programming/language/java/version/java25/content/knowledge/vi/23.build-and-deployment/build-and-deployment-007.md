# Thiết lập đường cơ sở hiệu năng và đối chiếu CPU, bộ nhớ, GC cùng độ trễ

## 1. Mục tiêu: đo hiệu năng có thể tái lập

Một lần chạy nhanh hơn không đủ chứng minh bản JDK mới tốt hơn. Kết quả có thể thay đổi do CPU đang bị tranh chấp, container có quota khác, dữ liệu test khác, JIT chưa warm-up, GC chưa vào trạng thái ổn định hoặc load generator trở thành bottleneck.

**Đường cơ sở hiệu năng (performance baseline)** là tập kết quả được đo theo một quy trình cố định, trên workload và môi trường đã mô tả rõ. Baseline giúp nhóm biết ứng dụng đang tiêu thụ bao nhiêu CPU và bộ nhớ, GC hoạt động ra sao, request có độ trễ thế nào và mức biến động bình thường là bao nhiêu.

Bài thuộc chương **Build và triển khai** của module **JAVA_VERSION_JAVA25**, với đề bài **“Thiết lập đường cơ sở hiệu năng và đối chiếu CPU, bộ nhớ, GC cùng độ trễ”**. Nội dung dùng Java 25 làm mốc học tập và đối chiếu các thay đổi còn áp dụng ở JDK 27, là release GA hiện hành tại ngày biên soạn **27-11-2026**.

Mục tiêu là xây dựng baseline cho cả microbenchmark và service chạy thực tế; đo CPU, heap/native memory, garbage collection, throughput và latency; rồi so sánh các lần chạy theo cách có thể giải thích và lặp lại.

### Sau bài này, bạn có thể

1. Phân biệt microbenchmark, benchmark cấp ứng dụng và kiểm thử tải.
2. Xác định workload, môi trường, warm-up và tiêu chí steady-state.
3. Dùng JMH cho phép đo nhỏ và load test cho latency end-to-end.
4. Đo CPU, allocation rate, heap, RSS, native memory và container limits.
5. Đọc GC unified logs và JFR để tìm nguyên nhân tốn CPU/bộ nhớ.
6. Phân tích latency bằng p50, p95, p99, throughput và error rate.
7. So sánh JDK 25 với JDK 27 mà không gộp nhiều thay đổi vào một kết luận.
8. Hiểu ảnh hưởng của G1 mặc định và compact object headers trong JDK 27.
9. Đặt ngưỡng chấp nhận và quyết định rollout dựa trên SLO.

## 2. Đường cơ sở gồm những gì?

Một baseline tốt có ba nhóm thông tin:

- **Mô tả môi trường:** JDK vendor/build, OS, CPU, RAM, container limits, JVM flags, GC, dependencies và cấu hình ứng dụng.
- **Mô tả workload:** request mix, payload, concurrency hoặc arrival rate, dữ liệu, thời gian warm-up và thời gian đo.
- **Kết quả:** CPU, heap/native memory, GC activity, throughput, latency percentiles, lỗi và độ phân tán giữa các lần chạy.

Không có baseline độc lập với workload. Một dịch vụ có thể nhanh với request đọc cache nhưng chậm với request truy vấn database; một batch job có thể tối ưu throughput trong khi API cần p99 latency thấp.

### Bộ chỉ số tối thiểu

| Nhóm | Chỉ số cần lưu | Câu hỏi trả lời |
| --- | --- | --- |
| CPU | Process CPU, machine CPU, CPU throttling, GC CPU | Ứng dụng hay GC đang tiêu thụ CPU? Có bị quota giới hạn không? |
| Bộ nhớ | Heap used/committed/max, live set, RSS, native memory | Ứng dụng cần bao nhiêu RAM thật? |
| Allocation | Bytes allocated/s, objects allocated, promotion | Ứng dụng tạo object nhanh đến mức nào? |
| GC | Pause count/time, pause percentiles, concurrent time, Full GC | GC ảnh hưởng latency và throughput ra sao? |
| Latency | p50, p95, p99, max theo endpoint | Người dùng thực sự chờ bao lâu? |
| Throughput | Requests/s, operations/s, records/s | Ứng dụng xử lý được bao nhiêu công việc? |
| Reliability | Error rate, timeout, retry, rejected requests | Hiệu năng có đạt được bằng cách bỏ lỗi hoặc queue quá tải không? |

~~~mermaid
flowchart TD
    A["Chốt câu hỏi và SLO"] --> B["Đóng băng artifact, JDK và môi trường"]
    B --> C["Xác định workload và load model"]
    C --> D["Warm-up theo điều kiện định trước"]
    D --> E["Đo CPU, memory, GC và latency"]
    E --> F["Lặp nhiều run độc lập"]
    F --> G["Phân tích phân phối và sai số"]
    G --> H{"Đạt ngưỡng và không có regression?"}
    H -->|Có| I["Canary và rollout"]
    H -->|Không| J["Tìm nguyên nhân, thay một yếu tố, đo lại"]
~~~

## 3. Phân biệt ba cấp độ benchmark

Không dùng một công cụ cho mọi câu hỏi.

| Cấp độ | Ví dụ câu hỏi | Công cụ phù hợp |
| --- | --- | --- |
| Microbenchmark | Hàm parse, serialize hoặc thuật toán có nhanh hơn không? | JMH |
| Component benchmark | Repository, HTTP client, serializer hoặc pipeline có throughput thế nào? | JMH có fixture phù hợp hoặc test harness chuyên biệt |
| Macrobenchmark / load test | Service xử lý request thực tế với p95/p99 bao nhiêu? | Gatling, k6, wrk2 hoặc load generator phù hợp |
| Production observation | Sau deploy, CPU/heap/GC/latency thay đổi thế nào? | Metrics, tracing, JFR, GC logs và telemetry hạ tầng |

### Microbenchmark không thay thế load test

JMH đo một đoạn công việc ở mức JVM và kiểm soát một số yếu tố như warm-up, measurement iterations và forks. Nó không tự mô phỏng network, database, load balancer, queue, container scheduling hoặc toàn bộ request path.

Ngược lại, load test cho thấy kết quả end-to-end nhưng khó cô lập một method cụ thể. Khi endpoint chậm, dùng JFR hoặc component benchmark để thu hẹp nguyên nhân.

Một vòng lặp tự viết quanh System.nanoTime có thể bị ảnh hưởng bởi JIT compilation, dead-code elimination, constant folding, loop unrolling, GC và thứ tự chạy. JMH tạo harness phù hợp để giảm các sai lệch phổ biến. Tài liệu JMH khuyến nghị dùng project Maven benchmark độc lập để benchmark được khởi tạo đúng và đáng tin cậy hơn chạy tùy tiện trong IDE. [OpenJDK JMH](https://github.com/openjdk/jmh)

## 4. Chốt câu hỏi và tiêu chí trước khi chạy

Viết câu hỏi benchmark thành một giả thuyết có thể kiểm tra.

Ví dụ:

> Với cùng artifact, request mix và container quota, nâng runtime từ JDK 25 lên JDK 27 có làm giảm p95 latency ít nhất 5% mà không tăng peak RSS quá 5% và không làm error rate tăng không?

Câu hỏi này có một biến chính là JDK runtime, workload cố định, metric chính là p95 latency, guardrails là peak RSS và error rate, cùng ngưỡng chấp nhận được định trước.

Nếu mục tiêu là kiểm tra thay đổi GC, câu hỏi nên tập trung vào GC collector hoặc cấu hình GC, không thay đồng thời JDK, heap, framework và database.

### Định nghĩa SLO và ngưỡng

| Metric | Ví dụ tiêu chí | Lưu ý |
| --- | --- | --- |
| p95 latency | ≤ 200 ms | Theo endpoint hoặc transaction |
| p99 latency | ≤ 500 ms | Cần đủ số quan sát để ước lượng đuôi |
| Throughput | ≥ 1.000 req/s | Phải kèm error rate |
| Error rate | < 0,1% | Bao gồm timeout và lỗi server |
| Peak RSS | ≤ 1,5 GiB | Phù hợp memory limit container |
| CPU | ≤ 70% quota ở tải mục tiêu | Chừa headroom cho burst |
| GC pause | Theo SLO latency | Không chỉ nhìn pause trung bình |
| Full GC | Không xuất hiện trong steady-state test | Nếu workload yêu cầu, phải giải thích nguyên nhân |

Các con số trên chỉ là ví dụ. SLO phải dựa trên yêu cầu của sản phẩm và mức tải thực tế.

## 5. Đóng băng môi trường trước khi đo

Để so sánh có ý nghĩa, ghi lại và giữ ổn định các yếu tố sau:

| Nhóm | Cần cố định hoặc ghi nhận |
| --- | --- |
| JDK | Vendor, full version, build, JVM implementation |
| Artifact | Git commit, checksum, compiler release, dependencies |
| Host | CPU model, số core, RAM, kernel/OS |
| Container | Image digest, CPU quota, memory limit, cgroup version |
| JVM | Heap, GC, flags, agents, JFR settings |
| Ứng dụng | Profiles, environment variables, feature flags |
| Dependencies | Database, cache, broker, HTTP services, network path |
| Data | Dataset, cache state, DB snapshot, payload size |
| Load | Arrival rate/concurrency, request mix, ramp-up |
| Observability | Metrics, tracing, JFR, logging level |
| Co-tenancy | Background jobs, noisy neighbors, CPU contention |

### Cùng artifact hay biên dịch lại?

Khi đo riêng tác động runtime, ưu tiên dùng cùng artifact nếu bytecode đó chạy được trên cả hai JDK. Nếu đồng thời biên dịch lại source bằng JDK mới, compiler có thể sinh bytecode hoặc metadata khác; khi đó kết quả phản ánh cả thay đổi compiler lẫn runtime.

Có thể chạy hai thí nghiệm riêng:

1. **Runtime-only comparison:** cùng artifact và dependencies, chỉ thay JDK runtime.
2. **Full upgrade comparison:** build lại bằng toolchain mục tiêu và triển khai theo cấu hình dự kiến production.

Không gộp hai kết quả vào một con số “JDK mới nhanh hơn”.

### Kiểm tra chính binary đang chạy

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Lưu java.version, java.runtime.version, java.vendor, java.vm.name, java.vm.version, os.name và os.arch. Nếu chạy trong container, thực hiện kiểm tra trong chính image và process context triển khai.

## 6. Thiết kế workload đại diện

Workload phải phản ánh phân bố công việc mà ứng dụng thực sự nhận.

Với REST service, ghi rõ tỷ lệ request theo endpoint, payload size và độ phân bố dữ liệu, cache hit/miss ratio, authentication/authorization path, database query mix, số connection và transaction, concurrency hoặc arrival rate, tỷ lệ lỗi, retry và timeout.

Với batch/worker, ghi records/s hoặc jobs/s, kích thước batch, phân bố record size, tỷ lệ dữ liệu lỗi, số worker và thời gian đọc, xử lý, ghi.

### Load model: closed-loop và open-loop

- **Closed-loop:** load generator gửi request tiếp theo sau khi request trước hoàn thành. Khi service chậm, tốc độ phát request tự giảm.
- **Open-loop:** load generator phát request theo arrival rate đã định, độc lập tương đối với thời gian phản hồi. Khi service không theo kịp, queue và latency sẽ bộc lộ rõ hơn.

Closed-loop phù hợp với một số mô hình user/concurrency thực tế, nhưng có thể che giấu overload do request rate giảm theo latency. Open-loop hữu ích khi cần kiểm tra một arrival rate cố định; phải theo dõi queue, dropped requests và khả năng load generator tự theo kịp.

Dùng cùng load model cho cả baseline và candidate. Không so sánh closed-loop ở JDK cũ với open-loop ở JDK mới.

### Kiểm tra load generator

Load generator phải còn headroom CPU/network. Nếu máy phát tải bão hòa, số request đo được không còn đại diện cho năng lực service. Với benchmark mạng, nên chạy generator ở máy khác và ghi latency/network của cả hai phía.

## 7. Warm-up và steady-state

JVM cần thời gian để tải class, profile code, biên dịch JIT, khởi tạo connection pool và làm nóng cache. Đo ngay sau process launch có thể phản ánh startup thay vì hiệu năng steady-state.

Tách ba giai đoạn:

1. **Startup:** process launch đến readiness.
2. **Warm-up:** sau readiness đến khi workload và runtime ổn định theo tiêu chí đã định.
3. **Measurement:** cửa sổ đo chính thức.

### Ví dụ tiêu chí steady-state

Một quy ước minh họa:

- Throughput đạt ít nhất 95% target.
- p95 latency không vượt SLO.
- CPU/GC metrics không còn xu hướng tăng bất thường.
- Các điều kiện trên duy trì qua ba cửa sổ liên tiếp, mỗi cửa sổ 30 giây.

Đừng chọn tiêu chí steady-state sau khi xem kết quả. Nếu ứng dụng có traffic biến động theo chu kỳ, thời gian đo cần đủ dài để bao phủ chu kỳ đó.

### Warm-up JMH

~~~java
package benchmarks;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
@State(Scope.Thread)
public class FindFieldBenchmark {
    @Param({"order=12345;status=ready;region=apac",
            "order=98765;status=pending;region=emea"})
    public String input;

    @Benchmark
    public int parse() {
        return input.indexOf("status=");
    }
}
~~~

Ví dụ trên minh họa cấu hình harness, không phải phép đo thực tế. Benchmark thật cần thực hiện đúng nghiệp vụ, tránh input cố định khiến compiler tối ưu hóa quá mức và bảo đảm kết quả được tiêu thụ.

Chạy benchmark bằng JMH runner được tạo trong project:

~~~bash
java -jar target/benchmarks.jar FindFieldBenchmark -f 3 -wi 5 -i 8
~~~

Dùng tùy chọn profiler gc của JMH để thu thêm allocation/GC metrics khi cần:

~~~bash
java -jar target/benchmarks.jar FindFieldBenchmark -prof gc
~~~

JMH result cần được xem cùng fork, warm-up, measurement time và độ phân tán; đừng chỉ chép một score.

## 8. Lặp lại độc lập và giảm nhiễu

Một lần chạy không thể mô tả biến động bình thường. Tạo nhiều lần chạy độc lập với process/JVM mới cho benchmark startup hoặc service-level test.

Quy trình thực tế:

1. Chạy pilot 5–10 lần mỗi biến thể để phát hiện nhiễu và lỗi test.
2. Xác định số lần đo chính thức theo độ biến động và mức thay đổi tối thiểu cần phát hiện.
3. Randomize thứ tự baseline/candidate hoặc dùng paired blocks.
4. Chạy mỗi lần với cùng dữ liệu, load model và thời lượng.
5. Ghi lại run bị lỗi hoặc timeout; không âm thầm loại khỏi báo cáo.
6. Báo median, phân vị và khoảng tin cậy của chênh lệch.

Ví dụ paired blocks:

~~~text
Block 01: JDK 25 -> JDK 27
Block 02: JDK 27 -> JDK 25
Block 03: JDK 27 -> JDK 25
Block 04: JDK 25 -> JDK 27
~~~

Thứ tự ngẫu nhiên giúp giảm ảnh hưởng của nhiệt độ CPU, background load và drift theo thời gian. Nếu có nhiều host, phân tầng theo host/instance; không gộp dữ liệu từ máy có cấu hình khác nhau mà không ghi nhận.

### Số mẫu và percentiles

p99 là phân vị đuôi, cần nhiều quan sát hơn median. Nếu chỉ có vài trăm request, p99 có thể phụ thuộc vào rất ít mẫu. Hãy báo số request thực tế và khoảng thời gian đo; không khẳng định p99 ổn định khi số mẫu quá nhỏ.

Request samples trong một process cũng không phải nhiều lần startup độc lập. Với startup benchmark, một sample là một process launch mới. Với service load test, nhiều request trong một run mô tả latency distribution của run đó; cần nhiều run để đo độ ổn định giữa các lần.

## 9. Đo CPU: process, host và container

CPU utilization cần được đọc ở đúng phạm vi:

- **Process CPU:** CPU time được tiêu thụ bởi JVM process.
- **Host CPU:** mức sử dụng tổng thể trên máy.
- **Container CPU:** CPU usage so với quota/cpuset được cấp.
- **GC CPU:** phần CPU dành cho các GC threads.
- **Application CPU:** CPU dành cho application threads/JIT/compiler và các hoạt động runtime khác.

Nếu process CPU cao nhưng host còn nhiều CPU, service có thể đang chạy đúng quota của container. Nếu host CPU cao do process khác, service có thể bị chậm dù JVM không dùng hết CPU.

### Công cụ quan sát

Linux có thể dùng:

~~~bash
pidstat -u -r -d -p <pid> 1
~~~

Hoặc xem tổng quan container:

~~~bash
docker stats
~~~

Với cgroup v2, có thể đối chiếu cpu.stat, memory.current, memory.max và memory.events trong thư mục cgroup của container. Trên nền tảng khác, dùng công cụ giám sát tương đương của hệ điều hành/container runtime.

### CPU ratio

\[
CPU\ cores\ used \approx \frac{\Delta process\ CPU\ time}{\Delta wall\ time}
\]

Ví dụ, process tiêu thụ 4 giây CPU trong 2 giây elapsed thì trung bình tương đương 2 CPU cores. Tỷ lệ này có thể vượt 100% vì nhiều thread chạy song song.

Không so sánh phần trăm CPU của hai container nếu quota khác nhau. Ghi cả CPU time/cores used và quota được cấp.

### CPU throttling

Trong container có CPU quota, process có thể bị throttled dù host vẫn còn CPU. Theo dõi số lần/thời gian throttling từ cgroup metrics. Khi benchmark, giữ quota và cpuset giống nhau; nếu không, CPU time và latency không thể so sánh trực tiếp.

## 10. Đo bộ nhớ: heap không phải RSS

Heap chỉ là một phần của bộ nhớ process.

| Thành phần | Nội dung |
| --- | --- |
| Java heap | Object, array và dữ liệu quản lý bởi GC |
| Metaspace | Class metadata |
| Code cache | JIT compiled code |
| Thread stacks | Stack của platform threads và runtime threads |
| Direct/native buffers | Bộ đệm ngoài heap, native allocation |
| Native libraries/runtime | JVM structures, JNI, allocator và thư viện native |
| Mapped memory | File mapping và vùng nhớ map khác |

### Các metric heap

- **Used:** lượng heap đang được sử dụng.
- **Committed:** lượng heap JVM đã cam kết với hệ điều hành.
- **Max:** giới hạn heap tối đa được cấu hình/ergonomics xác định.
- **Post-GC live set:** dữ liệu còn sống sau collection.
- **Allocation rate:** tốc độ tạo object/bytes.
- **Promotion rate:** tốc độ object chuyển sang old generation.

Không coi heap used cao ngay trước GC là memory leak. Cần xem xu hướng live set sau GC qua nhiều chu kỳ và dưới cùng workload.

### RSS và container memory

RSS (Resident Set Size) gần với lượng trang bộ nhớ process đang cư trú trong RAM, gồm cả heap và phần native. RSS không bằng heap used hoặc heap committed.

Trong container, memory usage còn chịu ảnh hưởng page cache và các thành phần tính theo cgroup. So sánh heap với memory limit mà bỏ qua direct buffers, thread stacks, metaspace và native libraries có thể dẫn tới OOMKilled dù heap chưa chạm Xmx.

### Lấy heap/native memory snapshot

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
~~~

Để phân tích native memory, bật Native Memory Tracking (NMT) từ lúc JVM khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Sau đó:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT có overhead và cần bật từ startup; dùng nó trong một lần diagnostic có kiểm soát, không bật/tắt tùy tiện giữa hai biến thể benchmark. Đối chiếu RSS từ OS/container với NMT và heap metrics để xác định phần native tăng.

## 11. Allocation rate và object lifetime

Hai ứng dụng có cùng heap size nhưng hành vi GC rất khác nếu allocation rate hoặc object lifetime khác nhau.

Ví dụ:

- Service A tạo nhiều object ngắn hạn nhưng phần lớn được thu hồi ở young generation.
- Service B tạo ít object hơn nhưng nhiều object sống lâu, làm old generation tăng.
- Service C tạo nhiều array/object lớn, có thể gây áp lực vùng humongous với G1.

Đo allocation bytes/s, object allocation hot spots, promotion và live set. JFR allocation sampling giúp tìm class/method tạo nhiều object; không cần bật mọi event ở mức chi tiết cao trong mọi production run.

Nếu allocation rate cao, kiểm tra:
- Tạo object tạm trong loop.
- Boxing/unboxing lặp lại.
- String concatenation/serialization.
- Buffer copy.
- Collection resize.
- Request/response object graph lớn.
- Cache không có giới hạn hoặc giữ reference quá lâu.

Không tối ưu chỉ để giảm allocation nếu việc đó làm code phức tạp hoặc tăng CPU; đo lại latency, CPU và memory sau mỗi thay đổi.

## 12. Đo GC bằng unified logging

Unified JVM logging là cơ chế hiện hành để ghi GC logs. Ví dụ:

~~~bash
java \
  -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

Nếu cần chẩn đoán sâu hơn cho G1:

~~~bash
java \
  -Xlog:gc*=debug:file=gc-debug.log:time,uptime,level,tags \
  -jar app.jar
~~~

Không dùng các cờ GC logging cũ như PrintGCDetails hoặc Xloggc cho cấu hình mới; dùng unified logging và kiểm tra java -Xlog:help trên JDK mục tiêu.

### Chỉ số GC cần trích xuất

| Chỉ số | Ý nghĩa |
| --- | --- |
| Pause count | Số lần dừng ứng dụng do GC |
| Pause duration | Thời gian mỗi pause |
| Pause p95/p99/max | Đuôi phân phối pause |
| Total pause time | Tổng thời gian ứng dụng bị dừng |
| Concurrent cycle duration | Thời gian các pha concurrent |
| Allocation rate | Áp lực cấp phát object |
| Promotion/live set | Dữ liệu sống chuyển sang old generation |
| Full GC | Dấu hiệu cần điều tra heap pressure hoặc collector không theo kịp |
| Evacuation failure / allocation stall | GC không thu hồi/di chuyển kịp theo nhu cầu |

Không chỉ nhìn pause trung bình. Một vài pause dài có thể ảnh hưởng p99 latency mạnh dù average pause thấp.

### Tỷ lệ thời gian dừng

\[
GC\ pause\ ratio = \frac{Total\ GC\ pause\ time}{Measurement\ wall\ time}
\]

Tỷ lệ này hữu ích để so sánh dưới cùng workload nhưng không giải thích đầy đủ GC overhead; concurrent GC có thể tiêu thụ nhiều CPU mà không nằm trong stop-the-world pause. Luôn đọc cả concurrent time và GC CPU.

## 13. G1 trong JDK 27 và ý nghĩa khi so sánh JDK

JDK 27 thay đổi mặc định quan trọng qua **JEP 523**: G1 trở thành garbage collector mặc định trong mọi môi trường, thay vì chỉ mặc định trên môi trường server-class. Khi nâng từ JDK 25 lên JDK 27, máy nhỏ hoặc môi trường trước đây dùng Serial GC theo ergonomics có thể chuyển sang G1 nếu không cấu hình collector tường minh. [JEP 523 / JDK 27 Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)

Vì vậy, khi benchmark nâng JDK:

1. Ghi collector thực sự được chọn ở cả hai release.
2. So sánh cùng collector nếu muốn cô lập tác động runtime.
3. Chạy thêm một phép đo theo default configuration nếu muốn biết trải nghiệm production sau nâng cấp thực tế.
4. Không quy mọi khác biệt cho JIT hoặc compiler nếu collector mặc định đã đổi.

### G1 không phải real-time collector

G1 cố gắng đạt pause-time goal với xác suất cao bằng cách dự đoán chi phí collection; nó không cam kết mọi pause đều nằm dưới ngưỡng. G1 sử dụng CPU song song với ứng dụng để làm một phần công việc concurrent, nên throughput có thể thấp hơn collector thiên về throughput. [G1 GC Guide](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html)

Bắt đầu với G1 defaults, đặt Xmx nếu cần và chỉ điều chỉnh pause goal sau khi đã đo. Tránh khóa young generation bằng các tùy chọn như Xmn nếu không có bằng chứng rõ ràng, vì điều này có thể làm G1 mất khả năng điều chỉnh kích thước generation để đáp ứng pause-time target. [G1 Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html)

### So sánh collector có kiểm soát

| Collector | Khi cần thử | Metric phải xem |
| --- | --- | --- |
| G1 | Baseline mặc định của JDK 27 | Throughput, pause distribution, CPU, heap |
| Parallel GC | Ưu tiên throughput và pause dài chấp nhận được | Throughput, CPU, Full GC, pause |
| ZGC | SLO latency rất nghiêm ngặt | p99 latency, CPU, heap headroom, concurrent work |
| Shenandoah | Bản phân phối có hỗ trợ và cần low-pause concurrent GC | Pause, CPU, allocation pressure, pacing và throughput |

Chỉ so sánh collector trên cùng binary/vendor, cùng workload, heap budget, CPU quota và load. Một collector có pause thấp hơn nhưng dùng nhiều CPU hơn có thể làm throughput hoặc p99 end-to-end xấu đi.

## 14. Compact object headers trong JDK 27

JDK 27 bật **Compact Object Headers** mặc định qua JEP 534. Trên kiến trúc 64-bit, object header giảm từ 96 bit xuống 64 bit; thay đổi này có thể giảm heap footprint, cải thiện mật độ triển khai và locality dữ liệu. [JEP 534 / JDK 27 Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)

Khi so sánh memory footprint giữa JDK 25 và JDK 27, cần ghi nhận object header layout. Nếu JDK 27 dùng compact headers còn baseline JDK 25 không dùng, phần chênh lệch heap có thể đến từ layout object chứ không chỉ từ GC hoặc JIT.

Thiết kế hai lượt đo nếu cần:

- **Default-to-default:** mỗi JDK chạy với mặc định của nó; đo kết quả nâng cấp thực tế.
- **Controlled configuration:** cố gắng giữ các tính năng liên quan nhất quán nếu cả hai release đều hỗ trợ và mục tiêu là cô lập một yếu tố.

Không tắt compact headers trong production chỉ để làm hai số liệu giống nhau nếu đó không phải cấu hình triển khai dự kiến. Ghi rõ chế độ đang dùng và giải thích ảnh hưởng khi diễn giải.

## 15. JFR để liên kết CPU, allocation và GC

JDK Flight Recorder (JFR) thu thập event về JVM, CPU, GC, allocation, thread, lock và runtime. Dùng JFR để tìm nguyên nhân đằng sau một metric đã quan sát, ví dụ CPU tăng hoặc p99 latency xấu đi.

Bắt đầu recording khi khởi chạy:

~~~bash
java \
  -XX:StartFlightRecording=filename=baseline.jfr,settings=profile,duration=5m \
  -jar app.jar
~~~

Hoặc attach vào process đang chạy:

~~~bash
jcmd <pid> JFR.start name=baseline settings=profile duration=5m filename=baseline.jfr
~~~

Xem tổng quan recording:

~~~bash
jfr summary baseline.jfr
~~~

In một số event hữu ích:

~~~bash
jfr print --events jdk.CPULoad,jdk.GarbageCollection,jdk.GCHeapSummary,jdk.ExecutionSample,jdk.ObjectAllocationSample baseline.jfr
~~~

Tên event và field khả dụng có thể khác theo JDK release/recording settings. Kiểm tra jfr metadata hoặc jfr summary của đúng runtime trước khi viết parser cố định.

### Dùng JFR để trả lời câu hỏi cụ thể

| Dấu hiệu từ metrics | Event/khía cạnh nên kiểm tra |
| --- | --- |
| CPU tăng | CPU load, execution samples, hot methods |
| Allocation tăng | Object allocation samples, allocation by class/method |
| GC pause dài | GarbageCollection, GCPhasePause, heap summary |
| Thread bị chờ | ThreadPark, JavaMonitorEnter, socket/file I/O |
| Throughput giảm | CPU saturation, GC concurrent work, blocked threads |
| Heap tăng dần | Live object samples, heap summaries, class histogram ở diagnostic run |

JFR recording có overhead tùy settings và workload. Giữ cùng recording settings giữa baseline và candidate nếu so sánh số liệu có JFR; nếu muốn đo hiệu năng thuần, chạy thêm lượt không profiling để đánh giá overhead quan sát.

### JFR redaction trong JDK 27

JDK 27 bổ sung **JEP 536 — JFR In-Process Data Redaction**: command-line arguments và giá trị ban đầu của environment variables/system properties được redacted trong recording trước khi dữ liệu rời process. Điều này giảm nguy cơ lộ secret trong các trường đó. Tuy nhiên, không coi mọi JFR event đều tự động được làm sạch; vẫn cần bảo vệ file recording, giới hạn quyền truy cập và rà soát dữ liệu trước khi chia sẻ. [JEP 536](https://openjdk.org/jeps/536)

## 16. Đo latency đúng cách

Latency là thời gian một operation đi từ mốc bắt đầu tới mốc kết thúc. Với API, nên đo cả client-observed latency, server-side request duration, dependency latency (database, cache, remote HTTP) và queue/wait time nếu request đi qua executor hoặc broker.

### Percentiles quan trọng hơn một average đơn lẻ

| Metric | Ý nghĩa |
| --- | --- |
| p50 | Một request điển hình ở giữa phân phối |
| p90 | 90% request nhanh hơn hoặc bằng giá trị này |
| p95 | Độ trễ của phần lớn request, thường dùng cho SLO |
| p99 | Đuôi chậm, nhạy với contention và dependency outliers |
| max | Trường hợp chậm nhất trong cửa sổ đo; nhạy với outlier |

Không cộng p95 của các endpoint để tạo p95 toàn hệ thống. Nếu cần latency toàn service, tính từ tập observation phù hợp hoặc dùng histogram có cùng bucket/aggregation semantics.

### Coordinated omission

Với closed-loop load generator, khi server chậm thì generator tự gửi ít request hơn; những khoảng đáng lẽ có request đến nhưng không được gửi sẽ không xuất hiện trong latency sample. Đây là coordinated omission, có thể khiến latency trông tốt hơn thực tế dưới overload.

Chọn load model phản ánh traffic; với arrival rate cố định, dùng open-loop generator có cơ chế ghi nhận request bị trễ/dropped và xác minh generator không bão hòa. Báo offered load, achieved throughput, queue depth và dropped requests cùng latency.

### Error rate đi cùng latency

Một service có thể trả latency thấp vì từ chối phần lớn request. Báo success throughput, offered request rate, achieved request rate, timeout/error/retry rate, queue depth và rejected requests.

Không tuyên bố cải thiện latency nếu error rate tăng hoặc request bị drop nhiều hơn.

## 17. So sánh JDK 25 và JDK 27 theo hai góc nhìn

Khi nâng JDK, cần trả lời hai câu hỏi khác nhau:

### A. Runtime-only comparison

Giữ artifact, workload, heap, collector và flags giống nhau khi khả thi. Mục tiêu là tìm khác biệt runtime/JIT/GC trong một cấu hình có kiểm soát.

### B. Production-default comparison

Dùng cấu hình mặc định dự kiến triển khai ở từng JDK. Mục tiêu là biết ứng dụng sẽ chạy thế nào sau nâng cấp thực tế, kể cả khi default GC hoặc object layout thay đổi.

| Yếu tố | Runtime-only | Production-default |
| --- | --- | --- |
| Artifact | Giữ nguyên nếu tương thích | Có thể build theo toolchain mục tiêu |
| GC | Cố định cùng collector nếu hỗ trợ | Dùng default của mỗi release |
| Compact headers | Ghi nhận và kiểm soát nếu khả thi | Dùng default từng release |
| Heap/CPU limits | Giống nhau | Giống production target |
| JVM flags | Giống nhau ở phần liên quan | Theo cấu hình rollout |
| Kết luận | Tác động runtime trong điều kiện kiểm soát | Tác động tổng thể của việc nâng cấp |

### Các thay đổi JDK 27 cần ghi trong báo cáo

- G1 trở thành default collector trong mọi môi trường (JEP 523).
- Compact object headers được bật mặc định (JEP 534).
- JFR có in-process data redaction (JEP 536).

Ba thay đổi này có thể ảnh hưởng tới baseline GC, heap footprint và quy trình profiling. Không diễn giải kết quả nâng JDK 25 lên JDK 27 mà bỏ qua chúng. [JDK 27 Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)

## 18. Bảng báo cáo baseline

Dùng một bảng nhất quán cho mỗi run:

| Run | JDK/build | GC | CPU quota | Heap max | Offered load | Throughput | p95 | p99 | Peak RSS | GC pause ratio | Errors |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 25.x | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| 2 | 25.x | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| 3 | 27.x | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| 4 | 27.x | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

Một bảng tổng hợp cần thêm:

| Metric | Baseline median | Candidate median | Chênh lệch | CI / độ phân tán | Đạt ngưỡng? |
| --- | ---: | ---: | ---: | --- | --- |
| Throughput | ... | ... | ...% | ... | ... |
| p95 latency | ... | ... | ...% | ... | ... |
| p99 latency | ... | ... | ...% | ... | ... |
| Process CPU cores | ... | ... | ...% | ... | ... |
| Peak RSS | ... | ... | ...% | ... | ... |
| Allocation rate | ... | ... | ...% | ... | ... |
| GC pause ratio | ... | ... | ...% | ... | ... |
| Error rate | ... | ... | ... | ... | ... |

Với metric thấp hơn là tốt hơn:

\[
Improvement(\%) = \frac{Baseline - Candidate}{Baseline} \times 100
\]

Với throughput cao hơn là tốt hơn:

\[
Gain(\%) = \frac{Candidate - Baseline}{Baseline} \times 100
\]

Báo cả số tuyệt đối và phần trăm. Nếu baseline gần 0, phần trăm có thể gây hiểu nhầm; ưu tiên chênh lệch tuyệt đối.

### Diễn giải thống kê

- Dùng median và IQR/MAD để mô tả run-to-run variation.
- Dùng confidence interval cho chênh lệch/ratio khi cần kết luận.
- Với paired blocks, phân tích chênh lệch theo từng block.
- Không bỏ outlier nếu không có tiêu chí loại trừ định trước và bằng chứng độc lập.
- Nếu CI rộng hoặc bao gồm cả cải thiện lẫn suy giảm đáng kể, kết luận là chưa đủ bằng chứng.

## 19. Các lỗi benchmark thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Đo ngay sau startup | JIT/cache/connection pool chưa warm-up | Tách startup, warm-up và measurement |
| Chỉ chạy một lần | Không biết biến động | Lặp nhiều run độc lập |
| Dùng vòng lặp nanoTime tự viết | JIT, dead-code elimination và setup gây sai lệch | Dùng JMH |
| So sánh workload khác nhau | Không cô lập được thay đổi | Cố định request mix, data và load model |
| Chỉ nhìn CPU host | Không biết process/container nào tiêu thụ | Ghi process CPU, quota và throttling |
| Chỉ nhìn heap used | Bỏ sót native memory/RSS | Đo heap, RSS, NMT và cgroup |
| Chỉ nhìn GC pause trung bình | Che mất pause tail | Báo p95/p99/max và concurrent time |
| Chỉ nhìn latency trung bình | Che tail latency | Báo p50/p95/p99 |
| Không báo error rate | Latency thấp giả do request fail/drop | Báo offered/achieved load và lỗi |
| Chạy generator trên cùng host | Tranh CPU với service | Tách máy hoặc theo dõi generator |
| Đổi nhiều flags cùng lúc | Không xác định được yếu tố gây thay đổi | Thay một nhóm biến mỗi thí nghiệm |
| Bật profiler chỉ ở candidate | Overhead khác nhau | Dùng cùng settings hoặc đo riêng |
| So JDK 25/27 nhưng bỏ qua default GC | Quy sai khác biệt cho JIT | Ghi collector thực tế và chạy hai góc nhìn |
| So RSS với heap used | Hai đại lượng khác nhau | Phân tích native, committed và cgroup |

## 20. Bài thực hành: tạo baseline cho REST service

### Bối cảnh

Một REST service chạy trong container có 2 CPU quota và memory limit 2 GiB. Nhóm muốn nâng từ JDK 25 lên JDK 27 và xác định thay đổi ảnh hưởng đến latency, CPU, bộ nhớ và GC.

### Nhiệm vụ

1. Ghi JDK vendor/build, OS/CPU, image digest, CPU quota và memory limit.
2. Ghi checksum artifact, dependencies, JVM flags và application configuration.
3. Xác định GC thực tế đang chạy trên JDK 25 và JDK 27.
4. Thiết kế request mix gồm endpoint đọc, ghi và endpoint có xử lý dữ liệu lớn.
5. Chọn open-loop hoặc closed-loop load model phù hợp; ghi rõ offered load và concurrency.
6. Chạy pilot để kiểm tra load generator và warm-up.
7. Chạy nhiều process/service runs độc lập theo thứ tự ngẫu nhiên.
8. Thu process CPU, container CPU/throttling, heap used/committed/max, RSS và native memory.
9. Bật GC unified logging với cùng cấu hình ở hai biến thể.
10. Thu JFR recording cùng settings để điều tra CPU, allocation và GC.
11. Đo throughput, p50, p95, p99, max, error rate và dropped requests.
12. Tạo bảng runtime-only comparison nếu có thể giữ cùng collector/flags.
13. Tạo bảng production-default comparison theo cấu hình triển khai thực tế.
14. Đánh giá tác động của G1 default và compact object headers trên JDK 27.
15. Viết kết luận đạt/không đạt SLO, nguyên nhân chính, rủi ro và kế hoạch canary/rollback.

### Câu hỏi tự đánh giá

1. Performance baseline cần ghi những nhóm thông tin nào?
2. Khi nào dùng JMH và khi nào dùng macrobenchmark?
3. Vì sao không dùng vòng lặp nanoTime đơn giản làm microbenchmark?
4. Startup, warm-up và measurement khác nhau thế nào?
5. Closed-loop load model có thể che giấu overload ra sao?
6. Vì sao cần ghi offered load và achieved throughput?
7. Process CPU có thể vượt 100% không? Vì sao?
8. Heap used và RSS khác nhau như thế nào?
9. Vì sao NMT cần bật từ lúc JVM khởi động?
10. Vì sao pause ratio không phản ánh toàn bộ GC CPU cost?
11. JDK 27 thay đổi mặc định G1 như thế nào?
12. Compact object headers ảnh hưởng phép so sánh memory giữa JDK 25 và 27 ra sao?
13. Vì sao p99 cần nhiều mẫu hơn p50?
14. Khi nào cần paired runs và confidence interval?
15. Vì sao phải báo error rate cùng latency?

## 21. Checklist chấp nhận baseline

- [ ] Đã xác định câu hỏi, metric chính, guardrails và SLO trước khi chạy.
- [ ] JDK vendor/build, artifact và dependencies đã được ghi lại.
- [ ] Host/container CPU và memory limits được cố định.
- [ ] GC collector và JVM flags thực tế được xác nhận.
- [ ] Workload, data, request mix và load model giống nhau.
- [ ] Load generator có đủ CPU/network headroom.
- [ ] Startup, warm-up và measurement được tách riêng.
- [ ] Có nhiều run độc lập và thứ tự chạy được randomize.
- [ ] CPU process, host, container và throttling được theo dõi.
- [ ] Heap, RSS, native memory và allocation rate được ghi lại.
- [ ] GC unified logs được thu với cùng settings.
- [ ] JFR settings giống nhau nếu so sánh recording.
- [ ] Throughput, p50/p95/p99, max, errors và dropped requests được báo.
- [ ] Có độ phân tán hoặc confidence interval cho chênh lệch.
- [ ] Đã ghi ảnh hưởng của G1 default và compact headers khi nâng lên JDK 27.
- [ ] Không tune nhiều biến cùng lúc.
- [ ] Có tiêu chí chấp nhận, canary metrics và rollback plan.
- [ ] Kết luận dựa trên workload đại diện và dữ liệu có thể tái lập.

**Tiêu chí hoàn thành:** người học có thể tạo baseline hiệu năng có thể tái lập cho một ứng dụng Java, đối chiếu CPU, bộ nhớ, allocation, GC và latency dưới cùng workload, giải thích khác biệt giữa JDK 25 và JDK 27, rồi đưa ra quyết định nâng cấp dựa trên SLO và bằng chứng đo được.

## 22. Tài liệu chính thức và công cụ

- [OpenJDK JMH](https://github.com/openjdk/jmh): Java Microbenchmark Harness, hướng dẫn project benchmark độc lập và cách chạy.
- [Oracle JDK 27 — Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): G1 default mọi môi trường, compact object headers và JFR redaction.
- [JEP 523 — Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523): thay đổi default GC trong JDK 27.
- [JEP 534 — Compact Object Headers](https://openjdk.org/jeps/534): object header 64-bit trên kiến trúc 64-bit và tác động memory.
- [JEP 536 — JFR In-Process Data Redaction](https://openjdk.org/jeps/536): redaction dữ liệu nhạy cảm trong JFR.
- [Oracle JDK 27 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html): cơ chế và mục tiêu của G1.
- [Oracle JDK 27 — G1 Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html): khuyến nghị tuning, GC logs và chẩn đoán Full GC.
- [Oracle JDK 27 — Available Collectors](https://docs.oracle.com/en/java/javase/27/gctuning/available-collectors.html): lựa chọn collector theo latency, throughput và môi trường.
- [Java Flight Recorder Runtime Guide](https://docs.oracle.com/en/java/javase/27/jfapi/flight-recorder-configurations.html): cấu hình recording và event settings.
- [The jcmd Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): chẩn đoán process, JFR và native memory.
- [The jfr Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jfr.html): summary, print và phân tích recording.
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): JVM options, heap, GC và unified logging.

Khi áp dụng cho vendor JDK khác Oracle, xác nhận GC defaults, compact-header support, JFR events và công cụ chẩn đoán của đúng build. Không giả định cùng major version luôn có cùng default hoặc cùng cách đóng gói.
