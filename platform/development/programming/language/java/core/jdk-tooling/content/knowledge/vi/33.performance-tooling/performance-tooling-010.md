# Tránh kết luận sai khi phân tích hiệu năng Java

## Mục tiêu

Sau bài này, bạn có thể xác định đúng câu hỏi cần đo; phân biệt latency, throughput, CPU time, wall-clock time, allocation rate và GC time; kiểm soát ảnh hưởng của JIT warm-up, cache, workload, concurrency và môi trường; tránh lỗi microbenchmark như dead-code elimination, constant folding và loop optimization; dùng JMH đúng cách; đọc metric GC, heap, CPU và JFR mà không suy diễn quá mức; nhận biết profiler overhead, sampling bias và counter tích lũy; so sánh kết quả có tính lặp lại; và kiểm chứng giả thuyết trước khi thay đổi code hoặc JVM configuration.

## 1. Vì sao dễ kết luận sai về hiệu năng?

Một metric chỉ mô tả một phần hoạt động của hệ thống tại một thời điểm hoặc trong một khoảng đo. Nó không tự giải thích nguyên nhân.

Ví dụ:

- CPU cao không tự chứng minh một method cụ thể là bottleneck.
- Heap đang sử dụng 85% không tự chứng minh có memory leak.
- Số lần GC tăng không tự chứng minh garbage collector được cấu hình sai.
- Một method có nhiều sample trong profiler không có nghĩa nó được gọi đúng số lần đó.
- Một lần benchmark nhanh hơn 12% không chứng minh phiên bản mới luôn nhanh hơn.
- Average latency giảm không bảo đảm các request chậm nhất cũng được cải thiện.
- RSS tăng trong khi Java heap ổn định không nhất thiết là Java heap leak.

Kết luận đáng tin cậy cần nối được ba phần:

1. **Quan sát:** metric, trace, event hoặc kết quả đo thực tế.
2. **Giả thuyết:** cơ chế có thể giải thích quan sát.
3. **Kiểm chứng:** phép đo hoặc thử nghiệm có khả năng xác nhận hay bác bỏ giả thuyết.

Ví dụ, old-generation occupancy tăng sau mỗi chu kỳ GC là quan sát. Giả thuyết có thể là object sống lâu bị giữ lại ngoài ý muốn. Kiểm chứng cần so sánh live set sau GC ở nhiều thời điểm, xem class histogram hoặc heap dump, rồi lần theo reference tới GC roots. Chỉ nhìn một biểu đồ heap không đủ để kết luận leak.

## 2. Xác định chính xác câu hỏi cần đo

Trước khi mở profiler hoặc thay đổi JVM flag, hãy viết câu hỏi theo dạng có thể đo được.

Ví dụ câu hỏi tốt:

- P95 và P99 latency của endpoint thanh toán tăng sau lần deploy nào?
- Throughput giảm khi số worker tăng từ 8 lên 16 hay không?
- Allocation rate tăng trên mỗi request sau khi đổi serializer?
- GC pause chiếm bao nhiêu thời gian trong cửa sổ incident?
- CPU time của JVM tăng hay process đang chờ database?
- Metaspace hoặc native memory tăng qua nhiều giờ chạy?
- Một thay đổi code cải thiện throughput bao nhiêu dưới cùng workload?

Tránh câu hỏi quá rộng như “JVM có chậm không?” hoặc “GC có vấn đề không?”. Hãy xác định:

- **Đối tượng:** một method, một endpoint, một JVM, một service hay toàn hệ thống.
- **Tác vụ:** request, transaction, batch, message hoặc benchmark operation.
- **Thước đo:** latency, throughput, CPU, allocation, pause, error rate hoặc memory.
- **Cửa sổ đo:** trước/sau deploy, giờ cao điểm, một chu kỳ batch hoặc thời gian warm-up.
- **Điều kiện:** tải, dữ liệu, số thread, JDK, collector và cấu hình runtime.

Nếu chưa xác định được câu hỏi và metric cần quan sát, rất dễ chọn một biểu đồ có vẻ bất thường rồi cố gán nguyên nhân cho nó.

## 3. So sánh trong điều kiện tương đương

Một phép so sánh chỉ có ý nghĩa khi các điều kiện quan trọng đủ giống nhau.

Khi so sánh hai phiên bản ứng dụng hoặc hai cấu hình JVM, ghi lại ít nhất:

| Nhóm | Thông tin cần giữ tương đương hoặc ghi lại |
|---|---|
| Runtime | JDK vendor, version, build, JVM flags, garbage collector |
| Phần cứng | CPU model, số core/logical processor, RAM, NUMA nếu liên quan |
| Hệ điều hành | OS/kernel, filesystem, container runtime |
| Giới hạn tài nguyên | CPU quota, memory limit, affinity, cgroup/container limits |
| Ứng dụng | Commit/build, dependency, cấu hình, feature flag |
| Workload | Request mix, payload, dataset, cache state, concurrency |
| Dữ liệu | Kích thước, phân bố, trạng thái database và cache |
| Môi trường | Background process, network, storage và downstream service |
| Đo lường | Tool version, template, sampling interval, warm-up, measurement duration |

Không so sánh kết quả từ laptop đang rảnh với máy CI đang chia sẻ CPU rồi kết luận thay đổi code làm chương trình nhanh hơn.

Nếu không thể giữ điều kiện hoàn toàn giống nhau, hãy ghi rõ khác biệt và giới hạn của kết luận. Chỉ thay đổi một yếu tố quan trọng trong mỗi thử nghiệm để biết yếu tố nào tạo ra tác động.

### Container và tài nguyên dùng chung

Một JVM chạy trong container có thể bị giới hạn CPU hoặc memory dù host còn tài nguyên. CPU throttling, memory limit, noisy neighbor và process khác tranh CPU có thể làm kết quả biến động.

Khi CPU usage của JVM thấp nhưng latency cao, hãy kiểm tra thread có đang chờ lock, I/O, connection pool hoặc CPU quota hay không. Khi CPU cao, xem cả process khác và mức sử dụng CPU của toàn máy.

Không mặc định rằng số CPU host nhìn thấy là số CPU JVM được phép dùng. Kiểm tra giới hạn container và cấu hình affinity trước khi diễn giải throughput hoặc CPU percentage.

## 4. Phân biệt các loại metric

Những metric có đơn vị khác nhau trả lời các câu hỏi khác nhau.

| Metric | Ý nghĩa | Câu hỏi trả lời |
|---|---|---|
| Wall-clock time | Thời gian thực trôi qua | Người dùng phải chờ bao lâu? |
| CPU time | Thời gian CPU thực thi cho thread/process | Code đã tiêu thụ bao nhiêu thời gian CPU? |
| Latency | Thời gian hoàn tất một request/operation | Một thao tác mất bao lâu? |
| Throughput | Số operation hoàn thành trên một đơn vị thời gian | Hệ thống xử lý được bao nhiêu việc? |
| Allocation rate | Byte object được cấp phát mỗi giây | JVM tạo object nhanh tới mức nào? |
| GC pause | Thời gian ứng dụng bị dừng bởi GC pause | GC làm gián đoạn ứng dụng bao lâu? |
| Heap used | Dung lượng Java heap đang sử dụng | Object hiện chiếm bao nhiêu heap? |
| RSS | Bộ nhớ resident của process | Process đang giữ bao nhiêu trang RAM? |

Một request có wall-clock latency 500 ms nhưng chỉ dùng CPU 20 ms có thể dành phần lớn thời gian chờ database, network, lock hoặc queue. Tối ưu vòng lặp CPU trong trường hợp này có thể không cải thiện latency đáng kể.

Ngược lại, CPU time cao gần bằng wall-clock time có thể gợi ý tác vụ đang chạy CPU-bound, nhưng vẫn cần profiler để tìm code path và xác nhận.

### Latency và throughput

Latency và throughput có liên quan nhưng không thể thay thế nhau:

- Latency đo thời gian của một operation.
- Throughput đo số operation hoàn tất trong một khoảng thời gian.

Khi tăng concurrency, throughput có thể tăng đến điểm bão hòa rồi chững lại, trong khi latency tiếp tục tăng do queueing, contention hoặc resource saturation.

Một hệ thống xử lý được nhiều request hơn nhưng P99 tăng mạnh có thể làm trải nghiệm người dùng xấu đi. Hãy xem throughput cùng P50, P95, P99 và error rate.

### Average có thể che giấu tail latency

Giả sử 99 request hoàn tất trong 20 ms và một request mất 2 giây. Average của 100 request là khoảng 39,8 ms. Con số trung bình này không cho thấy request chậm nhất đã mất 2 giây.

Hãy chọn percentile phù hợp với SLO và số lượng mẫu đủ lớn. P99 từ một tập chỉ có vài chục request không ổn định; một vài mẫu có thể làm thay đổi kết quả rất nhiều.

Khi so sánh latency, dùng cùng percentile, cùng cửa sổ, cùng workload và cùng cách tạo tải. Đừng so average của lần chạy này với P99 của lần chạy khác.

## 5. JIT và warm-up: không đo nhầm giai đoạn khởi động

Java HotSpot không nhất thiết thực thi mọi method theo cùng một cách từ đầu đến cuối process.

Trong giai đoạn đầu:

- Class được load và initialize.
- Interpreter có thể thực thi bytecode trước khi method được compile.
- Runtime thu thập profile về kiểu dữ liệu, branch và call site.
- JIT compiler có thể compile hoặc inline method khi đủ điều kiện.
- Cache, connection pool và application state được làm nóng.
- Một số tác vụ background như compilation vẫn tiếp tục trong khi ứng dụng chạy.

Vì vậy, thời gian của những request đầu tiên có thể khác đáng kể so với steady state.

### Khi mục tiêu là đo steady state

1. Chạy ứng dụng với workload đại diện.
2. Chờ class loading, JIT compilation và cache ổn định ở mức phù hợp.
3. Không lấy các mẫu warm-up vào kết quả measurement chính.
4. Đo trong một cửa sổ đủ dài để phản ánh workload.
5. Lặp lại trên process/fork độc lập khi benchmark micro.
6. Ghi rõ warm-up duration và số iteration.

### Khi mục tiêu là đo startup

Không loại bỏ warm-up nếu câu hỏi thực sự là thời gian startup hoặc thời gian từ process start tới readiness. Trong trường hợp đó, hãy đo riêng process launch tới main, main tới application ready, first request latency và warm-up tới steady-state latency.

Startup performance và steady-state performance là hai mục tiêu khác nhau. Không dùng số liệu steady state để tuyên bố startup nhanh hơn.

## 6. Vì sao stopwatch và vòng lặp tự viết dễ sai?

Đo một đoạn code bằng System.nanoTime trong một vòng lặp đơn giản có vẻ dễ, nhưng có nhiều yếu tố làm kết quả sai lệch:

- JVM có thể chưa JIT compile method.
- JIT có thể inline, unroll hoặc tối ưu code khác với dự kiến.
- Kết quả không được sử dụng nên computation có thể bị loại bỏ.
- Input hằng có thể cho phép constant folding.
- Overhead của timer và vòng lặp có thể lớn hơn công việc đang đo.
- Garbage collection có thể xảy ra trong hoặc ngoài cửa sổ đo.
- Thread scheduling, CPU frequency và background process gây nhiễu.
- Một lần chạy không phản ánh phân bố biến động.

Ví dụ một benchmark gọi method nhưng bỏ kết quả trả về. Nếu kết quả không được quan sát, compiler có thể loại bỏ computation không có side effect. Thời gian đo được khi đó không phải thời gian thực thi logic bạn muốn đo.

OpenJDK JMH có các sample riêng cho dead-code elimination, constant folding và loop optimization để minh họa những lỗi này.

## 7. Dùng JMH cho microbenchmark

**Java Microbenchmark Harness (JMH)** là framework của OpenJDK để xây dựng, chạy và phân tích benchmark Java. JMH quản lý warm-up, measurement iteration, fork, state và việc tiêu thụ kết quả để giảm nhiều lỗi đo lường phổ biến.

JMH hữu ích khi cần so sánh một thuật toán, cấu trúc dữ liệu, method hoặc đoạn code JVM trong điều kiện có kiểm soát.

JMH không tự làm cho một benchmark sai về mặt nghiệp vụ trở thành đúng. Người viết vẫn phải chọn workload, input, state và phép đo đại diện. JMH project khuyến nghị tạo benchmark project riêng bằng Maven archetype và chạy từ command line vì cách chạy trực tiếp trong IDE có môi trường khó kiểm soát hơn.

### Tạo project JMH

Cần có JDK và Maven. Tạo project mẫu:

~~~bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.sample -DartifactId=performance-lab -Dversion=1.0
~~~

Sau khi tạo project, đặt benchmark class vào source tree theo package tương ứng, sau đó build:

~~~bash
cd performance-lab
mvn clean verify
~~~

Chạy benchmark jar được tạo:

~~~bash
java -jar target/benchmarks.jar
~~~

Xem các tùy chọn:

~~~bash
java -jar target/benchmarks.jar -h
~~~

Archetype thiết lập dependencies và annotation/bytecode processing cần thiết. Chỉ thêm jmh-core vào project thông thường chưa đủ để tạo một benchmark project đúng cấu hình.

### Ví dụ benchmark có warm-up, measurement và fork

Tạo file **ArraySumBenchmark.java** trong package **org.sample**:

~~~java
package org.sample;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
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
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class ArraySumBenchmark {
    @Param({"64", "4096"})
    int size;

    int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < values.length; i++) {
            values[i] = i + 1;
        }
    }

    @Benchmark
    public long sum() {
        long total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }
}
~~~

Ý nghĩa:

- **@State(Scope.Thread)** tạo state riêng cho mỗi benchmark thread, tránh chia sẻ mảng ngoài ý muốn.
- **@Param** chạy benchmark với hai kích thước input.
- **@Setup(Level.Trial)** chuẩn bị dữ liệu trước các iteration của một trial, không tính chi phí tạo mảng vào mỗi operation.
- **@Warmup** chạy 5 iteration warm-up, mỗi iteration 1 giây.
- **@Measurement** đo 5 iteration, mỗi iteration 1 giây.
- **@Fork(3)** chạy 3 JVM fork độc lập.
- **@BenchmarkMode(Mode.AverageTime)** đo average time trên operation.
- **@OutputTimeUnit** hiển thị kết quả theo microsecond.
- Method trả về kết quả để JMH tiêu thụ, hạn chế dead-code elimination.

Chạy riêng benchmark:

~~~bash
java -jar target/benchmarks.jar ArraySumBenchmark
~~~

JMH sẽ in score, error và unit cho từng parameter. Giá trị cụ thể phụ thuộc CPU, JDK, OS, workload và trạng thái máy; không có một stdout số học cố định để dùng làm chuẩn chung.

### Đọc kết quả JMH

Một kết quả thường có các cột:

- Benchmark: tên method benchmark.
- Mode: kiểu đo như throughput hoặc average time.
- Cnt: số lượng measurement sample/iteration được tổng hợp theo output.
- Score: điểm đo được.
- Error: độ bất định được báo cáo cùng score.
- Units: đơn vị.

Không chỉ chọn hàng có Score tốt nhất. Hãy xem Error, số fork, workload và kết quả giữa các lần chạy. Nếu khác biệt nhỏ so với độ biến động, dữ liệu chưa đủ để khẳng định một implementation tốt hơn.

## 8. Các lỗi microbenchmark thường gặp

### Dead-code elimination

Nếu kết quả computation không được sử dụng, JVM có thể loại bỏ computation đó.

Cách tránh:

- Trả kết quả từ benchmark method khi phù hợp.
- Dùng **Blackhole** để tiêu thụ kết quả khi benchmark cần xử lý nhiều giá trị.
- Đảm bảo công việc được đo thực sự ảnh hưởng tới output được quan sát.

Không thêm side effect tùy tiện chỉ để ngăn compiler tối ưu. Side effect mới có thể làm benchmark đo một workload khác.

### Constant folding

Nếu input luôn là một hằng số và computation có thể xác định trước, JIT có thể tính kết quả trước hoặc đơn giản hóa computation.

Cách tránh:

- Dùng input runtime từ state hoặc parameter.
- Tránh final primitive cố định làm input nếu mục tiêu là đo computation phụ thuộc dữ liệu.
- Kiểm tra sample chính thức của JMH về constant folding.

Không biến benchmark thành workload giả tạo chỉ để ngăn tối ưu. Input nên có phân bố gần với dữ liệu thật.

### Loop optimization và unrolling

Tự bọc nhiều operation trong một vòng lặp để giảm overhead invocation có thể khiến JIT unroll, pipeline hoặc hoist computation. Chi phí trên mỗi operation khi chia tổng thời gian cho số vòng lặp có thể trở nên phi thực tế.

Hãy để JMH gọi benchmark method theo harness của nó. Vòng lặp vẫn hợp lệ khi đó là một phần thực sự của thuật toán được đo, ví dụ duyệt mảng trong method sum ở trên; tránh tạo vòng lặp nhân tạo chỉ để đo một phép cộng nhỏ.

### Benchmark overhead và fixture

Nếu setup chạy cho mỗi invocation, thời gian setup có thể lấn át method cần đo. Nếu setup chỉ cần một lần cho cả trial, dùng **@Setup(Level.Trial)**. Nếu cần setup cho mỗi iteration hoặc invocation, chọn level phù hợp và hiểu rõ chi phí đó có được tính vào phép đo hay không.

### Không dùng fork

Chạy nhiều benchmark trong cùng JVM có thể khiến profile JIT, class loading và state từ benchmark trước ảnh hưởng benchmark sau. Fork tạo JVM process riêng để giảm ảnh hưởng chéo.

Hãy dùng nhiều fork khi cần kết luận ổn định. Số fork quá ít có thể làm kết quả phụ thuộc vào một trạng thái runtime cụ thể.

### Chạy benchmark trực tiếp trong IDE

IDE có thể thêm background task, debugger, plugin, classpath và cấu hình JVM khác với môi trường thực tế. JMH khuyến nghị chạy benchmark từ command line trong project được thiết lập đúng.

## 9. Đừng nhầm microbenchmark với load test

Microbenchmark trả lời câu hỏi về một đoạn code hoặc operation dưới điều kiện cô lập. Nó không mô phỏng đầy đủ một service đang nhận traffic.

| Loại thử nghiệm | Mục tiêu | Công cụ phù hợp |
|---|---|---|
| Microbenchmark | So sánh method/algorithm/data structure | JMH |
| Component benchmark | Đo một thành phần với dependency được kiểm soát | JMH hoặc harness phù hợp |
| Load test | Đo service dưới concurrency và request mix | Công cụ load test như Gatling/k6 hoặc công cụ tổ chức đang dùng |
| Soak test | Quan sát drift, leak và degradation qua thời gian dài | Load generator + metrics/JFR |
| Startup test | Đo process launch và readiness | Script/harness đo process lifecycle |
| Production profiling | Tìm bottleneck trên workload thật | JFR/JMC, profiler, metrics và tracing |

Một method nhanh hơn trong JMH có thể không làm endpoint nhanh hơn nếu bottleneck thực tế là database, network, serialization khác, queue hoặc lock.

Ngược lại, load test chậm không chứng minh một method riêng lẻ là nguyên nhân. Dùng profiler hoặc trace để tìm code path trong request thực tế.

## 10. Đọc GC và heap metric mà không suy diễn

### Heap usage cao không tự chứng minh leak

Heap có thể tăng do workload vừa tăng, cache đang warm-up, object sống lâu được giữ theo thiết kế, JVM mở rộng committed heap, GC chưa chạy tại thời điểm snapshot, live set thực sự tăng hoặc object bị giữ ngoài ý muốn.

Hãy xem heap sau GC qua nhiều chu kỳ. Nếu live set sau GC tăng liên tục dưới workload tương đương, đó là tín hiệu cần điều tra. Tiếp theo dùng class histogram, heap dump, dominator tree và path to GC roots để xác định object nào đang được giữ.

### GC count cao không tự chứng minh GC có vấn đề

Một ứng dụng tạo nhiều object ngắn hạn có thể có young GC thường xuyên nhưng vẫn đạt latency và throughput mục tiêu.

Cần xem allocation rate, young/old GC frequency, pause time distribution, time spent in GC, heap occupancy trước và sau GC, promotion, collector và cấu hình heap, cùng application latency trong cùng cửa sổ.

Một collector có nhiều collection nhỏ và pause ngắn có thể hoạt động tốt hơn collector ít collection nhưng pause dài. Đừng so sánh chỉ bằng số lần GC.

### Counter tích lũy và gauge

Các counter như số lần GC hoặc tổng thời gian GC thường tăng tích lũy kể từ khi JVM bắt đầu. Muốn tính trong một cửa sổ, lấy chênh lệch giữa hai lần đọc:

~~~text
deltaGC = GC_count_after - GC_count_before
deltaGCTime = GC_time_after - GC_time_before
~~~

Gauge như heap used là snapshot hiện tại. Không lấy counter tích lũy làm rate hoặc so sánh hai process có uptime rất khác nhau mà không chuẩn hóa.

### Heap, committed, reserved và RSS

Các khái niệm này khác nhau:

- Heap used: object đang sử dụng trong Java heap.
- Heap committed: dung lượng heap JVM đã commit và có thể dùng.
- Reserved address space: vùng địa chỉ JVM dành trước.
- RSS: trang memory resident của process trong RAM.

RSS có thể tăng do metaspace, code cache, thread stack, direct buffer, native library hoặc memory mapping trong khi heap used ổn định.

Nếu nghi native memory, dùng Native Memory Tracking (NMT) nếu đã bật từ lúc JVM khởi động và kết hợp công cụ OS. NMT chỉ theo dõi các nhóm memory nội bộ HotSpot được hỗ trợ; không bao phủ mọi allocation từ code native bên ngoài JVM.

## 11. CPU cao, CPU thấp và profiler sample

### CPU cao không chỉ ra ngay method gây lỗi

CPU cao có thể đến từ nhiều request hơn, vòng lặp hoặc thuật toán tốn CPU, serialization/deserialization, regex/parsing, garbage collection, JIT compilation, compression/encryption/hashing, busy wait, retry loop hoặc logging quá nhiều.

Dùng JFR hoặc profiler để xem thread và stack sample, sau đó xác minh code path. Kiểm tra process và CPU quota ở cấp OS/container.

### CPU thấp không có nghĩa ứng dụng khỏe

CPU thấp nhưng latency cao có thể xảy ra khi thread chờ database, remote API, network/file I/O, connection pool, thread pool queue, monitor/lock, rate limiter hoặc downstream timeout.

Trong trường hợp này, tăng CPU hoặc tối ưu arithmetic không giải quyết nguyên nhân chờ.

### Sampling không phải số lần gọi chính xác

Profiler sampling định kỳ lấy stack của thread tại một số thời điểm. Method xuất hiện nhiều trong sample có thể đang tiêu tốn nhiều thời gian, nhưng sample count không phải số lần method được gọi chính xác.

Hãy đọc sample cùng thời lượng recording, sampling period, thread state và loại event. Method không xuất hiện trong sample không có nghĩa method chưa từng chạy.

JFR có duration event, instant event, sample event và custom event. Mỗi loại mô tả hoạt động khác nhau. Một duration event được ghi theo thời gian bắt đầu/kết thúc; sample event là quan sát tại một thời điểm hoặc chu kỳ lấy mẫu. Không cộng các loại event như thể chúng là cùng một đơn vị.

### Profiler cũng có overhead

JFR tích hợp trong JVM và được thiết kế để có overhead thấp. Tuy nhiên, template và event settings khác nhau về mức chi tiết và tác động.

- **default.jfc** phù hợp theo dõi nền với overhead thấp.
- **profile.jfc** thu thập nhiều event hơn và có thể tác động lớn hơn.
- Method profiling và allocation profiling có thể tạo thêm dữ liệu.
- Event threshold thấp hoặc stack trace chi tiết có thể tăng số event.

Đo baseline không profiler, sau đó bật cấu hình profiling cần thiết và so sánh. Nếu mục tiêu là latency nhạy với pause, tránh bật event settings có thể kích hoạt công việc bổ sung khi chưa đánh giá ảnh hưởng.

## 12. Phân tích JFR theo đúng phạm vi

JFR ghi event có timestamp và cung cấp góc nhìn về JVM, ứng dụng, thread, GC, CPU, allocation, lock và I/O.

Một quy trình hợp lý:

1. Chọn recording bao trọn incident hoặc workload.
2. Ghi lại JDK version, template và event settings.
3. Xem Overview và Environment để hiểu máy, process và workload.
4. Xác định khoảng thời gian latency hoặc CPU bất thường.
5. Xem GC pause, allocation và heap trong cùng cửa sổ.
6. Xem thread/CPU samples và lock contention.
7. Xem file/socket I/O nếu CPU không giải thích được latency.
8. Đọc stack trace và source code của các hotspot.
9. Đối chiếu với application metrics, logs và distributed trace.

Đừng chọn một chart nổi bật rồi bỏ qua timeline. Một method có nhiều sample trong recording dài có thể chỉ phản ánh nó chạy thường xuyên; hãy kiểm tra sample đó có nằm trong thời điểm chậm hay không.

Nếu recording dùng default nhưng không bật allocation profiling, không thể kết luận allocation thấp chỉ vì không thấy nhiều allocation event. Trước khi diễn giải một event không xuất hiện, xác nhận event đã được bật và threshold/period phù hợp.

## 13. Cẩn thận với concurrency và load generation

Một benchmark đơn thread không mô tả hiệu năng khi nhiều thread cùng truy cập state hoặc tài nguyên dùng chung.

Khi tăng concurrency, có thể xuất hiện lock contention, queueing và context switching, cache-line contention/false sharing, memory bandwidth saturation, connection pool exhaustion, thread pool saturation, CPU throttling, GC pressure tăng do tổng allocation và downstream service quá tải.

Hãy đo nhiều mức concurrency và xem cả throughput lẫn latency. Nếu throughput không tăng nhưng P99 tăng mạnh, có thể hệ thống đã bão hòa hoặc queue đang tăng.

### Kiểm tra false sharing và shared state

Các thread cập nhật field độc lập nhưng nằm gần nhau trong cùng cache line có thể ảnh hưởng lẫn nhau. Một benchmark dùng shared counter hoặc shared state có thể đo contention thay vì thuật toán bạn định so sánh.

Chọn **@State(Scope.Thread)** khi mỗi thread cần dữ liệu riêng. Chọn shared scope chỉ khi chia sẻ state là một phần của workload thực tế.

### Load generator cũng có thể trở thành bottleneck

Nếu máy tạo tải hết CPU, network hoặc connection, throughput đo được có thể bị giới hạn bởi load generator. Theo dõi tài nguyên ở cả client và server.

Đảm bảo số virtual user, request rate, think time và phân bố request phản ánh mục tiêu thử nghiệm. Một load test không tạo được tải mục tiêu không thể dùng để kết luận server chịu được mức tải đó.

## 14. Thống kê và độ biến động: đừng chọn kết quả đẹp nhất

Hiệu năng runtime biến động do JIT, GC, CPU frequency, OS scheduler, background process, network và workload.

Để kết quả đáng tin cậy:

- Chạy nhiều iteration và nhiều fork khi dùng JMH.
- Giữ nguyên cấu hình và workload giữa các lần chạy.
- Lưu raw result, không chỉ copy một Score.
- Xem score cùng error/uncertainty.
- Quan sát phân bố và outlier, không tự ý xóa mẫu xấu.
- Ghi lại điều kiện máy và thời gian chạy.
- Chạy lại khi kết quả không nhất quán.
- Đánh giá mức cải thiện có ý nghĩa thực tế hay không.

Không chọn lần chạy nhanh nhất làm kết quả đại diện. Không loại bỏ outlier chỉ vì nó làm thay đổi kết luận; trước tiên phải tìm nguyên nhân như GC, CPU throttling hoặc background task.

### So sánh mức cải thiện

Giả sử baseline đo được 100 microsecond/op và bản mới là 97 microsecond/op. Chênh lệch danh nghĩa là 3%. Nếu độ biến động giữa các fork cũng khoảng vài phần trăm, chưa đủ bằng chứng để tuyên bố cải thiện 3%.

Hãy xem error/uncertainty, số fork và độ lặp lại. Nếu khác biệt nhỏ hơn nhiễu, tăng chất lượng thiết kế đo hoặc kết luận rằng chưa thấy khác biệt đáng tin cậy.

### Outlier có thể là tín hiệu

Một mẫu latency rất lớn có thể phản ánh GC pause, lock convoy, network retransmission, disk stall hoặc retry. Đừng loại bỏ tail latency khi mục tiêu là reliability hoặc user experience.

Khi cần điều tra outlier, giữ timestamp để đối chiếu với JFR, GC log, distributed trace và hệ thống downstream.

## 15. Tách tương quan khỏi quan hệ nhân quả

Hai metric tăng cùng lúc không chứng minh một metric gây ra metric kia.

Ví dụ:

- CPU và latency cùng tăng có thể do traffic tăng, không nhất thiết CPU gây latency.
- Heap và request rate cùng tăng có thể do workload lớn hơn.
- GC và error rate cùng tăng có thể do traffic burst hoặc memory pressure chung.
- Một method có sample count cao có thể chỉ là code path được gọi nhiều nhất, không phải nguyên nhân duy nhất của latency.

Để kiểm tra quan hệ nhân quả:

1. Đặt giả thuyết có cơ chế cụ thể.
2. Xác định metric sẽ thay đổi nếu giả thuyết đúng.
3. Chỉ thay đổi một yếu tố có kiểm soát.
4. Chạy baseline và thử nghiệm với workload tương đương.
5. Lặp lại và xem kết quả có ổn định không.
6. Nếu có thể, rollback để xem metric có trở về baseline.
7. Ghi nhận cả tác động phụ như memory, CPU và error rate.

Ví dụ, nghi ngờ serializer mới tăng allocation. Đo allocation bytes/request, CPU time/request và latency dưới cùng payload. Chạy cùng workload với serializer cũ và mới, sau đó so sánh. Chỉ khi allocation và/hoặc CPU thay đổi theo dự đoán qua nhiều lần chạy mới có cơ sở kết luận.

## 16. Những ví dụ kết luận sai thường gặp

### “Heap đang 90%, chắc chắn có memory leak”

Một snapshot có thể được chụp trước GC hoặc trong lúc cache đang warm-up.

Cần làm: quan sát live set sau GC qua nhiều chu kỳ dưới tải tương đương; xem allocation rate; nếu live set tăng liên tục, dùng histogram/heap dump để tìm object giữ lại.

### “GC chạy 200 lần, collector quá chậm”

Số lần GC là counter tích lũy và phụ thuộc uptime, allocation rate, heap size và collector.

Cần làm: tính delta trong cùng cửa sổ; xem pause distribution, total GC time, allocation và latency; xác định collection nào ảnh hưởng SLO.

### “Method A có nhiều sample nhất, tối ưu nó sẽ nhanh nhất”

Sample count có thể phản ánh method được gọi thường xuyên, không chỉ chi phí mỗi lần gọi. Method cũng có thể nằm trong stack của nhiều caller.

Cần làm: xem thời gian self/total, call path, thread state và khoảng incident; xác nhận bằng benchmark hoặc profiling có mục tiêu.

### “CPU thấp nên JVM không phải bottleneck”

Thread có thể chờ database, lock, network hoặc connection pool.

Cần làm: xem thread state, I/O event, lock wait, downstream latency và queue depth.

### “Bản mới nhanh hơn vì một lần chạy nhanh hơn”

Một lần chạy có thể gặp JIT warm-up, GC, CPU frequency hoặc background task khác.

Cần làm: chạy nhiều fork/iteration, kiểm soát môi trường và xem error/uncertainty.

### “Average latency giảm nên user experience tốt hơn”

Average có thể giảm trong khi P99 tăng.

Cần làm: xem P50/P95/P99, error rate và request mix; so sánh cùng cửa sổ và cùng percentile.

### “JFR không có allocation event, vậy app không allocate”

Template hoặc event settings có thể không bật allocation profiling, hoặc threshold/period không phù hợp.

Cần làm: kiểm tra event settings, template và thời lượng recording; nếu cần, chạy profiling recording có cấu hình phù hợp.

### “RSS tăng, Java heap chắc chắn leak”

RSS bao gồm memory ngoài Java heap như native allocation, thread stack, direct buffer và mapped file.

Cần làm: so sánh heap used/committed với RSS; dùng NMT khi đã bật; kiểm tra direct buffer, thread count, native library và OS metrics.

## 17. Quy trình điều tra performance có thể lặp lại

### Giai đoạn 1: xác nhận triệu chứng

1. Xác định endpoint/job/JVM bị ảnh hưởng.
2. Chọn metric phản ánh triệu chứng: P99, throughput, CPU, GC pause hoặc memory.
3. Xác định thời điểm bắt đầu và cửa sổ xảy ra.
4. So sánh với baseline/SLO và workload.
5. Ghi nhận deploy, config change, traffic và downstream event.

### Giai đoạn 2: thu thập bằng chứng

1. Lấy application metrics và distributed trace.
2. Xem OS/container CPU, memory, disk, network và throttling.
3. Xem GC log và JFR.
4. Xem thread state, lock và I/O.
5. Dùng histogram/heap dump nếu có bằng chứng memory growth.
6. Ghi lại JDK, collector, JVM flags và tool settings.

### Giai đoạn 3: kiểm tra giả thuyết

1. Chọn một bottleneck có bằng chứng.
2. Tạo thử nghiệm nhỏ tái hiện workload.
3. Dùng JMH cho code-level microbenchmark.
4. Dùng load/soak test cho service-level behavior.
5. Chỉ thay đổi một yếu tố.
6. Lặp lại và đo cùng metric.
7. Xem cả tác động phụ và error/uncertainty.

### Giai đoạn 4: xác minh thay đổi

1. Chạy regression test.
2. Chạy benchmark/load test dưới điều kiện tương đương.
3. So sánh cùng percentile và cùng đơn vị.
4. Kiểm tra CPU, memory, GC, throughput và error rate.
5. Triển khai có kiểm soát nếu quy trình cho phép.
6. Theo dõi production metrics sau thay đổi.
7. Rollback nếu SLO hoặc error rate xấu đi.

## 18. Lỗi thường gặp và cách xử lý

### Benchmark chạy quá nhanh hoặc kết quả phi thực tế

**Nguyên nhân:** dead-code elimination, constant folding, input quá đơn giản hoặc vòng lặp bị tối ưu.

**Cách xử lý:** dùng JMH; trả kết quả hoặc dùng Blackhole; dùng state/parameter runtime; đọc JMH samples về dead code, constant folding và loops.

### Kết quả giữa các lần chạy chênh lệch lớn

**Nguyên nhân:** warm-up chưa đủ, CPU bị chia sẻ, GC, CPU throttling, thermal state, workload hoặc dữ liệu không giống nhau.

**Cách xử lý:** kiểm soát môi trường; dùng warm-up và fork; ghi raw results; theo dõi OS/JVM metric; lặp lại thay vì chọn kết quả tốt nhất.

### Benchmark trong IDE khác command line

**Nguyên nhân:** JVM options, classpath, background process, debugger, plugin hoặc annotation processor khác.

**Cách xử lý:** tạo JMH project riêng bằng Maven archetype và chạy executable benchmark jar từ command line.

### Throughput tăng nhưng latency xấu đi

**Nguyên nhân:** concurrency tăng khiến queue, lock contention hoặc downstream saturation.

**Cách xử lý:** xem throughput cùng P95/P99, error rate, queue depth, thread state và connection pool; kiểm tra nhiều mức concurrency.

### GC metric tăng nhưng ứng dụng vẫn đạt SLO

**Nguyên nhân:** allocation throughput cao nhưng collection ngắn và ít ảnh hưởng.

**Cách xử lý:** đánh giá pause distribution, GC time ratio, throughput và live set; chỉ tối ưu khi có tác động thực tế.

### CPU cao nhưng profiler không thấy hotspot rõ ràng

**Nguyên nhân:** recording quá ngắn, sampling không đủ, code native, compilation, GC hoặc process khác dùng CPU.

**Cách xử lý:** mở rộng cửa sổ và kiểm tra JFR event settings; xem OS process metrics, GC, compiler và native stack nếu cần.

### JFR profile làm kết quả thay đổi

**Nguyên nhân:** template/event settings thu thập chi tiết hơn và tạo overhead.

**Cách xử lý:** đo baseline; dùng default cho quan sát nền; dùng profile ngắn có mục tiêu; ghi rõ settings khi so sánh.

### Memory RSS tăng nhưng heap ổn định

**Nguyên nhân:** native memory, thread stack, direct buffer, code cache hoặc memory mapping.

**Cách xử lý:** xem NMT nếu đã bật, direct buffer, thread count, OS memory map và native library; không quy kết cho Java heap khi chưa có bằng chứng.

### Average tốt nhưng người dùng vẫn thấy chậm

**Nguyên nhân:** tail latency, request mix hoặc downstream chậm.

**Cách xử lý:** đo P95/P99 theo endpoint và phân đoạn request; đối chiếu trace, queue và dependency latency.

### Thay đổi một lúc nhiều cấu hình nên không biết nguyên nhân

**Nguyên nhân:** thay đổi code, heap, collector, thread pool và cache cùng lúc.

**Cách xử lý:** quay về baseline có thể tái lập; thay đổi từng yếu tố; ghi lại phiên bản và cấu hình cho mỗi lần thử.

## 19. Checklist trước khi kết luận

### Câu hỏi và môi trường

- [ ] Câu hỏi đo lường đã cụ thể và có metric phù hợp.
- [ ] Đã xác định workload, input, concurrency và cửa sổ đo.
- [ ] JDK, JVM flags, collector và OS đã được ghi lại.
- [ ] CPU/memory quota và background process đã được kiểm tra.
- [ ] Dữ liệu và cache state tương đương giữa các lần chạy.

### Phép đo

- [ ] Đã phân biệt wall-clock time, CPU time, latency và throughput.
- [ ] Đã xem percentile phù hợp, không chỉ average.
- [ ] Đã có warm-up nếu mục tiêu là steady state.
- [ ] Đã dùng JMH cho microbenchmark JVM.
- [ ] Đã kiểm tra dead-code elimination, constant folding và loop optimization.
- [ ] Đã dùng nhiều iteration/fork khi cần.
- [ ] Đã giữ raw result và uncertainty.
- [ ] Không tự ý bỏ outlier chưa được giải thích.

### Diễn giải metric

- [ ] Counter tích lũy đã được chuyển thành delta/rate đúng cách.
- [ ] Heap usage được xem qua nhiều chu kỳ GC.
- [ ] GC count được xem cùng pause time và latency.
- [ ] CPU cao/thấp được đối chiếu với thread state và I/O.
- [ ] JFR sample được hiểu là sample, không phải số lần gọi chính xác.
- [ ] Template và event settings đã được kiểm tra.
- [ ] RSS được phân biệt với Java heap.
- [ ] Profiler overhead đã được cân nhắc.

### Kết luận và thay đổi

- [ ] Có giả thuyết và bằng chứng ủng hộ.
- [ ] Có phép thử có thể bác bỏ giả thuyết.
- [ ] Mỗi lần thử chỉ thay đổi yếu tố cần kiểm tra.
- [ ] Kết quả được lặp lại trong điều kiện tương đương.
- [ ] Mức cải thiện lớn hơn nhiễu và có ý nghĩa vận hành.
- [ ] Có regression test và kế hoạch theo dõi sau thay đổi.

## 20. Tài liệu tham khảo chính thức

- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — JFR, JMC, jcmd, monitoring, event categories và native memory tracking.
- [OpenJDK Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh/) — hướng dẫn tạo project benchmark, Maven archetype, command-line usage và các sample.
- [JMH Sample 08: Dead Code](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java) — vì sao computation không dùng kết quả có thể bị loại bỏ.
- [JMH Sample 10: Constant Folding](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java) — tránh benchmark input có thể được compiler tính trước.
- [JMH Sample 11: Loops](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_11_Loops.java) — loop unrolling, pipelining và hoisting có thể làm sai chi phí trên operation.
- [JMH Sample 35: Profilers](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java) — cách dùng profiler, fork và hardware counter để hiểu benchmark.
- [Avoiding Benchmarking Pitfalls on the JVM — Oracle](https://www.oracle.com/technical-resources/articles/java/architect-benchmarking.html) — các lỗi benchmark JVM, JIT optimization và cách JMH giúp giảm rủi ro.

Đừng kết luận từ một con số hoặc một biểu đồ đơn lẻ. Hãy xác định đúng câu hỏi, kiểm soát điều kiện đo, hiểu JIT và profiler có thể ảnh hưởng dữ liệu ra sao, rồi đối chiếu metric với workload, timeline và bằng chứng độc lập. Một kết luận hiệu năng chỉ nên được dùng để thay đổi code hoặc cấu hình khi phép đo có thể lặp lại và giả thuyết đã được kiểm chứng.
