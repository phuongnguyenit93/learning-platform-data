# Kiểm tra sai số, biến động và chi phí công cụ quan sát

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt sai số đo lường, biến động ngẫu nhiên và thay đổi hiệu năng thật.
- Thiết kế phép đo có thể lặp lại khi so sánh hai phiên bản JDK hoặc hai cách triển khai.
- Dùng JMH để đo microbenchmark và tránh các lỗi thường gặp khi tự đo bằng đồng hồ trong code.
- Đọc số liệu JFR theo đúng bản chất thống kê của sampling và duration events.
- Chọn cấu hình JFR phù hợp giữa continuous recording và profiling recording.
- Ước lượng chi phí do profiler, instrumentation, heap statistics và diagnostic command gây ra.
- Dùng các cải tiến JFR có trong JDK 26 đúng phạm vi và phân biệt tính năng ổn định với tính năng experimental.
- Kết luận từ dữ liệu có độ tin cậy, không quy kết mọi thay đổi nhỏ cho một tối ưu hóa.

## 1. Vì sao một kết quả benchmark có thể sai lệch?

Một lần đo hiệu năng không phải lúc nào cũng phản ánh chính xác chi phí của chương trình. Kết quả có thể thay đổi do nhiều yếu tố không liên quan đến thay đổi code đang được kiểm tra:

- JVM chưa hoàn tất warmup hoặc JIT compiler đang biên dịch method.
- Garbage collection xảy ra trong một lần chạy nhưng không xảy ra ở lần khác.
- CPU thay đổi tần số, bị thermal throttling hoặc chia sẻ với process khác.
- Container bị giới hạn CPU hoặc bị scheduler của host cấp thời gian không đều.
- Dữ liệu đầu vào, cache state, connection pool hoặc tải nền khác nhau.
- Công cụ quan sát thêm CPU, allocation, lock hoặc I/O.
- Benchmark bị tối ưu loại bỏ vì kết quả không được sử dụng.
- Chỉ đo một lần hoặc đo quá ngắn nên biến động ngẫu nhiên chi phối kết quả.

Ví dụ, hai lần chạy có kết quả:

| Lần chạy | Thời gian xử lý trung bình |
|---|---:|
| A | 10,1 ms |
| B | 9,8 ms |

Chênh lệch 0,3 ms chưa đủ để kết luận B nhanh hơn. Nếu độ biến động tự nhiên của workload là ±0,5 ms, kết quả có thể chỉ là nhiễu đo.

Khi đo hiệu năng, cần trả lời ba câu hỏi riêng:

1. Phép đo có chính xác và cùng điều kiện không?
2. Kết quả có ổn định qua nhiều lần chạy không?
3. Công cụ đo có làm thay đổi workload hay không?

## 2. Phân biệt sai số hệ thống và biến động ngẫu nhiên

Có hai nhóm vấn đề cần nhận diện.

**Sai số hệ thống (systematic error)** làm kết quả lệch theo một hướng tương đối ổn định. Ví dụ:

- Đo thời gian bằng wall clock trong khi đồng hồ hệ thống bị điều chỉnh.
- Chỉ đo phiên bản mới trên máy mạnh hơn phiên bản cũ.
- Benchmark dùng dữ liệu cố định khiến JIT constant-fold hoặc tối ưu theo một trường hợp đặc biệt.
- Load generator không đủ tải, khiến throughput đo được thấp hơn khả năng thật của server.
- Profiler bật ở một bên nhưng tắt ở bên còn lại.

**Biến động ngẫu nhiên (random variation)** làm kết quả dao động giữa các lần chạy. Ví dụ:

- Scheduler phân bổ CPU khác nhau.
- Một GC cycle rơi vào một iteration.
- Network latency thay đổi.
- Thread khác chiếm CPU hoặc lock.
- Cache CPU, filesystem page cache hoặc trạng thái kết nối khác nhau.

Sai số hệ thống không tự biến mất khi chạy benchmark nhiều lần. Nếu luôn dùng hai cấu hình máy khác nhau, tăng số lần chạy không làm phép so sánh trở nên công bằng.

Biến động ngẫu nhiên có thể được ước lượng bằng nhiều lần chạy độc lập. Hãy báo cáo phân bố và độ không chắc chắn, thay vì chỉ lấy một con số đẹp nhất.

## 3. Chọn đúng đại lượng cần đo

Không có một metric duy nhất mô tả toàn bộ hiệu năng.

| Đại lượng | Trả lời câu hỏi | Đơn vị thường dùng |
|---|---|---|
| Latency | Một request mất bao lâu? | ms, µs |
| Throughput | Hệ thống xử lý được bao nhiêu request trong một khoảng? | requests/s, operations/s |
| CPU time | Thread/process tiêu thụ bao nhiêu thời gian CPU? | ms, s |
| Allocation rate | Ứng dụng cấp phát bao nhiêu bộ nhớ mỗi giây? | MB/s |
| GC pause | Ứng dụng bị dừng bao lâu vì GC? | ms |
| GC CPU time | GC tiêu thụ bao nhiêu CPU? | ms, s |
| Memory footprint | Process/heap/native memory sử dụng bao nhiêu? | MB, GB |
| Queue depth | Công việc đang chờ xử lý bao nhiêu? | số item |

Latency và throughput không thể thay thế nhau. Khi hệ thống bị bão hòa, throughput có thể gần như không tăng nhưng latency tăng mạnh do queueing.

CPU time cũng khác wall-clock time. Một request mất 100 ms nhưng chỉ tiêu thụ 5 ms CPU có thể dành phần lớn thời gian chờ I/O hoặc lock. Ngược lại, một tác vụ chạy song song trên nhiều core có tổng CPU time lớn hơn elapsed time.

Chọn metric theo mục tiêu:

- Tối ưu API: đo p50, p95, p99 latency cùng throughput và error rate.
- Tối ưu batch: đo thời gian hoàn tất, records/s, CPU và allocation.
- Tối ưu GC: đo pause distribution, GC CPU, allocation rate và live set.
- Tối ưu CPU: đo process/thread CPU, sampling profile và thời gian chạy.
- Tối ưu startup: đo startup-to-ready và thời gian warmup đến ngưỡng throughput mục tiêu.

## 4. Thiết kế phép so sánh có kiểm soát

Khi so sánh hai phiên bản JDK, hai thuật toán hoặc hai cấu hình, giữ nguyên các yếu tố không thuộc phạm vi thử nghiệm:

- Cùng commit hoặc artifact ứng dụng.
- Cùng dependency và dữ liệu đầu vào.
- Cùng CPU model, số core, RAM và hệ điều hành.
- Cùng CPU quota, memory limit và container runtime.
- Cùng heap size, GC, JVM flags và agent, trừ yếu tố đang cần kiểm tra.
- Cùng phiên bản database, cache, message broker và dịch vụ phụ thuộc.
- Cùng mức tải, phân bố request, concurrency và thời lượng.
- Cùng phiên bản load generator và cách sinh dữ liệu.

Nếu mục tiêu là kiểm tra tác động của JDK 26, không đồng thời đổi GC, heap, framework và thư viện. Khi nhiều biến cùng thay đổi, không thể xác định yếu tố nào tạo ra khác biệt.

Nên ghi lại metadata của mỗi lần đo:

- JDK vendor, version, build và JVM arguments.
- OS/kernel, CPU model, core count và container quota.
- Commit, artifact hash và dependency lock.
- GC, heap min/max và các tùy chọn runtime.
- Dataset, request mix, concurrency và thời điểm chạy.
- Trạng thái profiler, JFR template và diagnostic flags.

Nếu load generator chạy cùng máy với server, CPU của generator có thể cạnh tranh với ứng dụng. Với phép đo tải thực tế, ưu tiên tách load generator sang máy riêng hoặc xác minh generator còn dư CPU.

## 5. Warmup và JIT ảnh hưởng đến kết quả

HotSpot là JVM tối ưu động. Code có thể được thực thi ở interpreter trước, sau đó được biên dịch bởi JIT khi method đủ nóng. Hiệu năng trong những lần gọi đầu không nhất thiết đại diện cho steady state.

Một benchmark ngắn có thể đo lẫn:

- Class loading và linking.
- Khởi tạo static state.
- JIT compilation.
- Deoptimization.
- Cache lạnh.
- Kết nối database hoặc connection pool chưa sẵn sàng.
- GC và allocation trong giai đoạn khởi tạo.

Cần tách hai mục tiêu:

**Startup benchmark:** đo từ lúc khởi chạy đến readiness hoặc đến khi tác vụ đầu tiên hoàn tất. Không loại bỏ startup nếu đó là đại lượng cần tối ưu.

**Steady-state benchmark:** warmup trước, sau đó mới đo khi code và hệ thống đạt trạng thái ổn định. Không trộn thời gian startup vào phép đo này.

Không chọn warmup chỉ theo một con số cố định. Quan sát throughput/latency qua từng iteration; nếu số liệu vẫn tăng hoặc giảm rõ rệt, benchmark có thể chưa ổn định.

## 6. Dùng JMH thay vì tự viết vòng lặp nanoTime

JMH là harness benchmark dành cho JVM. Nó xử lý các vấn đề như warmup, measurement iteration, fork, tiêu thụ kết quả và đồng bộ thời gian.

Một microbenchmark tối thiểu:

~~~java
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 10, time = 1)
@Fork(3)
@State(Scope.Thread)
public class SumBenchmark {
    @Param({"100", "1000"})
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
        long result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }
}
~~~

Trong ví dụ:

- Warmup có 5 iteration, mỗi iteration 1 giây.
- Measurement có 10 iteration, mỗi iteration 1 giây.
- Fork chạy benchmark trong 3 JVM process độc lập.
- @Param kiểm tra nhiều kích thước dữ liệu.
- Kết quả được trả về để harness tiêu thụ, tránh dead-code elimination.

Khi benchmark nhiều thuật toán, giữ cùng input và cùng điều kiện. Không tạo dữ liệu ngẫu nhiên trong mỗi lần gọi nếu mục tiêu là đo thuật toán xử lý dữ liệu; tạo dữ liệu ở @Setup và đo riêng chi phí chuẩn bị nếu đó cũng là một phần của workload thật.

Chạy benchmark bằng JMH runner hoặc build profile được cấu hình đúng. Không chạy method benchmark trực tiếp từ IDE rồi dùng thời gian của một lần gọi làm kết luận.

### Những lỗi microbenchmark thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
|---|---|---|
| Dùng System.nanoTime() quanh một lời gọi | Chi phí timer, JIT và scheduler có thể lớn hơn tác vụ | Dùng JMH |
| Kết quả không được sử dụng | JIT có thể loại bỏ phép tính | Trả kết quả hoặc dùng Blackhole |
| Input là hằng số | JIT có thể constant-fold hoặc tối ưu theo dữ liệu cố định | Dùng state và @Param |
| Chỉ chạy một fork | Kết quả phụ thuộc trạng thái JVM/process | Dùng nhiều fork |
| Không warmup | Đo lẫn interpreter và JIT compilation | Thiết lập warmup riêng |
| Đặt setup trong method benchmark | Đo cả tạo dữ liệu thay vì phần cần so sánh | Dùng @Setup hoặc benchmark setup riêng |
| Chạy nhiều benchmark đồng thời | Các benchmark cạnh tranh CPU và memory | Chạy tuần tự, kiểm soát tải nền |
| Chỉ báo cáo best score | Che giấu biến động và outlier | Xem toàn bộ iteration và phân bố |

## 7. Đọc độ biến động và độ tin cậy

Một báo cáo benchmark nên có nhiều hơn một giá trị trung bình.

Ví dụ:

| Lần chạy | Latency trung bình |
|---|---:|
| 1 | 10,2 ms |
| 2 | 10,0 ms |
| 3 | 10,1 ms |
| 4 | 10,4 ms |
| 5 | 9,9 ms |

Có thể báo cáo median, mean, standard deviation, min/max và confidence interval tùy công cụ. Median ít bị một outlier đơn lẻ chi phối hơn mean, nhưng không thay thế việc tìm nguyên nhân outlier.

Một số nguyên tắc:

- Dùng nhiều fork và iteration độc lập.
- Xem phân bố của từng iteration, không chỉ giá trị gộp.
- So sánh chênh lệch với độ biến động nền.
- Nếu confidence interval của hai kết quả chồng lấn mạnh, chưa có bằng chứng rõ về khác biệt.
- Không loại outlier chỉ vì nó làm kết quả xấu; chỉ loại khi có nguyên nhân bên ngoài được ghi nhận và quy tắc loại đã xác định trước.
- Lặp lại phép đo vào thời điểm khác nếu môi trường có tải nền biến động.
- Khi kiểm tra latency service, báo cáo p50/p95/p99 thay vì chỉ mean.

Ví dụ mức cải thiện throughput:

~~~text
Improvement (%) =
    ((Throughput_new - Throughput_base) / Throughput_base) * 100
~~~

Ví dụ mức tăng latency:

~~~text
LatencyChange (%) =
    ((Latency_new - Latency_base) / Latency_base) * 100
~~~

Nếu throughput tăng 1% nhưng độ biến động tự nhiên là 3%, chưa thể kết luận cải thiện. Nếu p99 latency tăng dù mean giảm, thay đổi có thể làm trải nghiệm của nhóm request chậm hơn.

## 8. Observer effect: công cụ quan sát cũng tiêu thụ tài nguyên

Profiler, tracing agent, logging và diagnostic command đều chạy trong cùng môi trường với ứng dụng. Chúng có thể tiêu thụ CPU, memory, I/O, thêm event allocation hoặc tạo pause.

Chi phí có thể đến từ:

- Lấy mẫu stack trace.
- Thu thập event và ghi buffer.
- Serialize event ra file.
- Instrument bytecode khi method được gọi.
- Thu thập allocation stack trace.
- Tính heap statistics.
- Tạo heap dump hoặc class histogram.
- Ghi log ở mức debug/trace.
- Gửi metric qua network hoặc export dữ liệu quá thường xuyên.

Một công cụ có thể hữu ích để tìm bottleneck nhưng làm thay đổi mức độ bottleneck. Ví dụ, method timing instrumentation có thể tăng chi phí của method ngắn được gọi hàng triệu lần. Nếu chỉ bật instrumentation ở một phiên bản benchmark, kết quả đó không thể so sánh trực tiếp với baseline không instrumentation.

### Ước lượng overhead

Đo cùng workload trong hai cấu hình:

- Baseline: không bật công cụ quan sát bổ sung.
- Observed: bật cấu hình quan sát cần đánh giá.

Với elapsed time:

~~~text
Overhead (%) =
    ((T_observed - T_baseline) / T_baseline) * 100
~~~

Với throughput:

~~~text
ThroughputLoss (%) =
    ((Q_baseline - Q_observed) / Q_baseline) * 100
~~~

Ví dụ baseline xử lý 10.000 request/s, khi bật profiler còn 9.800 request/s:

~~~text
ThroughputLoss = ((10000 - 9800) / 10000) * 100 = 2%
~~~
Đây là overhead quan sát được trong workload và môi trường đã thử. Không coi overhead là một hằng số có thể trừ khỏi mọi phép đo; chi phí công cụ phụ thuộc tần suất event, số thread, stack depth, I/O và hành vi ứng dụng.

## 9. Chọn đúng JFR recording template

JDK 26 cung cấp các cấu hình JFR thường dùng trong thư mục JDK_HOME/lib/jfr:

| Template | Mục tiêu | Chi phí tương đối |
|---|---|---|
| default.jfc | Continuous recording và giám sát dài hạn | Thấp |
| profile.jfc | Điều tra bottleneck với nhiều event hơn | Cao hơn, nên dùng trong khoảng ngắn |

Theo tài liệu Oracle JDK 26:

- Continuous recording với cấu hình mặc định thường không tạo ra ảnh hưởng hiệu năng đo được.
- Time-fixed profiling recording dùng cấu hình mặc định có overhead dưới 2% với phần lớn ứng dụng.
- Các con số trên không phải cam kết cho mọi workload; hãy đo lại trên ứng dụng thực tế.
- Heap Statistics bị tắt mặc định vì có thể gây overhead đáng kể.

Heap Statistics kích hoạt một old garbage collection ở đầu và cuối lần recording. Hai GC bổ sung này có thể tạo pause không thuộc hành vi tự nhiên của workload. Nếu đang đo latency hoặc GC pause, không bật Heap Statistics trừ khi mục tiêu là điều tra live set/memory leak và đã chấp nhận tác động.

Continuous recording với default template không thu thập heap statistics hoặc allocation profiling đầy đủ. Khi cần dữ liệu đó, hãy dùng một recording profiling ngắn và phân biệt rõ kết quả với baseline.

## 10. Bắt đầu, kiểm tra và đọc JFR bằng jcmd

Có thể bắt đầu recording khi JVM đang chạy:

~~~bash
jcmd -l
jcmd <pid> JFR.start name=continuous settings=default
jcmd <pid> JFR.check
jcmd <pid> JFR.dump name=continuous filename=continuous.jfr
~~~

Với một profiling recording ngắn:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=60s filename=profile.jfr
~~~

Sau khi có file:

~~~bash
jfr summary profile.jfr
jfr print --categories GC profile.jfr
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad profile.jfr
~~~

JFR recording chứa event có timestamp. Dùng JDK Mission Control (JMC) để xem Code, Memory, GC, Threads và I/O; dùng lệnh jfr để lọc hoặc xuất event phục vụ phân tích tự động.

JMC không nằm trong bộ cài JDK thông thường, cần cài riêng. JFR là framework tích hợp trong JDK và có thể điều khiển bằng jcmd hoặc API.

### Không nhầm vắng event với không có bottleneck

Nhiều Java Application duration events có threshold mặc định 20 ms. Nếu một thao tác lock hoặc I/O chỉ kéo dài 1 ms, event có thể không được ghi. Việc không thấy event trong recording không chứng minh rằng ứng dụng không có chờ đợi ngắn.

Có thể hạ threshold cho event cần kiểm tra, nhưng số event sẽ tăng và chi phí recording có thể tăng. Chỉ hạ threshold cho một nhóm event và trong khoảng thời gian đủ ngắn để trả lời câu hỏi cụ thể.

## 11. JFR sampling là dữ liệu thống kê, không phải trace từng lệnh

Method sampling định kỳ quan sát stack của thread đang chạy code. Method có nhiều sample thường là nơi tiêu thụ nhiều CPU hơn, nhưng sample count không phải số lần gọi chính xác hoặc thời gian chạy chính xác của method.

Cần hiểu các giới hạn:

- Thread đang chờ I/O, ngủ hoặc chờ lock thường không xuất hiện trong execution samples vì chúng không chạy code.
- Sample count thấp làm ước lượng kém ổn định.
- Sampling interval và cách lấy stack ảnh hưởng khả năng nhìn thấy method ngắn.
- Một method có thể bị bỏ qua giữa hai lần lấy mẫu.
- Kết quả thể hiện xu hướng CPU, không tự cung cấp latency end-to-end.

Để điều tra thread stall, xem các duration events như socket/file I/O, monitor wait, thread park hoặc sleep. Để điều tra CPU-bound code, xem execution samples, CPU load và thread CPU load. Không dùng một biểu đồ hot methods để kết luận toàn bộ request latency.

## 12. Những cải tiến JFR có trong JDK 26

JDK 26 bao gồm các cải tiến JFR được đưa vào từ những JDK gần đây. Cần phân biệt phiên bản xuất hiện đầu tiên và trạng thái hiện tại:

| Cải tiến | Phiên bản đầu tiên | Ý nghĩa và trạng thái trong JDK 26 |
|---|---:|---|
| JEP 509 – JFR CPU-Time Profiling | JDK 25 | Thu thập CPU-time profiling chính xác hơn trên Linux; vẫn là experimental |
| JEP 518 – JFR Cooperative Sampling | JDK 25 | Cải thiện độ ổn định khi lấy stack, chỉ walk stack tại safepoint và giảm safepoint bias |
| JEP 520 – JFR Method Timing & Tracing | JDK 25 | Dùng bytecode instrumentation để đo thời gian và trace method invocation |
| JFR default/profile templates | Có từ các JDK trước | Tiếp tục là cách cấu hình recording tiêu chuẩn trong JDK 26 |

JEP 509 là experimental feature, không phải Java preview feature. Chỉ dùng để thử nghiệm trên nền tảng Linux được hỗ trợ; không coi kết quả là metric portable giữa mọi OS hoặc mọi JVM vendor.

JEP 518 cải thiện cơ chế sampling của JFR. Nó không biến sampling thành trace toàn bộ lệnh và không loại bỏ sai số thống kê.

JEP 520 bổ sung method timing và tracing thông qua bytecode instrumentation. Tính năng này hữu ích khi cần thời gian invocation cụ thể hoặc call trace của một nhóm method, nhưng có thể tạo chi phí cao nếu instrument quá rộng.

Các cải tiến JFR này không yêu cầu bật --enable-preview. Khi dùng tính năng experimental, cần đọc tài liệu JDK mục tiêu và xác nhận trạng thái trên đúng vendor/build.

## 13. Dùng Method Timing và Method Trace có chọn lọc

JFR Method Timing và Method Trace cho phép theo dõi invocation của method thông qua bytecode instrumentation. JDK 26 hỗ trợ event jdk.MethodTiming và jdk.MethodTrace; có thể lọc theo class, method hoặc annotation.

Ví dụ tạo cấu hình chỉ theo dõi một method:

~~~bash
jfr configure --input profile.jfc --output methods.jfc jdk.MethodTiming#enabled=true jdk.MethodTiming#filter=com.example.OrderService::calculate
~~~

Sau đó chạy recording ngắn:

~~~bash
jcmd <pid> JFR.start name=method-timing settings=methods.jfc duration=30s filename=method-timing.jfr
jfr print --events jdk.MethodTiming method-timing.jfr
~~~

Cú pháp filter hỗ trợ class, class-method, method name hoặc annotation. Có thể lọc nhiều target bằng dấu chấm phẩy.

Không bật method timing cho toàn bộ package lớn trong production nếu chưa đánh giá overhead. Hãy bắt đầu từ một method nghi ngờ, một nhóm endpoint hoặc annotation cụ thể; tăng phạm vi khi dữ liệu chưa đủ.

Method Timing/Trace trả lời câu hỏi khác với sampling:

- Sampling: method nào chiếm tỷ trọng CPU lớn trong các sample?
- Method Timing: invocation được instrument mất bao lâu?
- Method Trace: method nào được gọi và theo chuỗi nào trong phạm vi instrumentation?

Một method có thời gian mỗi lần gọi nhỏ nhưng được gọi rất nhiều lần có thể tạo overhead instrumentation đáng kể. Hãy kiểm tra chi phí profiler bằng phép đo A/B trước khi dùng kết quả để so sánh hiệu năng.

## 14. JFR CPU-Time Profiling và giới hạn experimental

JEP 509 cải thiện khả năng thu thập CPU-time profiling trên Linux. Oracle JDK 26 ghi rõ tính năng này vẫn experimental.

Điều cần nhớ:

- Chỉ áp dụng trên nền tảng được hỗ trợ, không suy rộng sang Windows hoặc macOS.
- Experimental feature có thể thay đổi giữa các release.
- Không dùng dữ liệu experimental làm hợp đồng API hoặc SLA portable.
- So sánh kết quả với CPU metrics của hệ điều hành và các JFR event khác.
- Ghi lại JDK build, kernel, CPU và cấu hình profiler trong báo cáo.

CPU-time profiling khác wall-clock profiling. Một thread có thể mất nhiều thời gian wall-clock do chờ I/O nhưng chỉ dùng ít CPU. Khi tìm bottleneck, phải xác định đang tối ưu thời gian CPU hay thời gian người dùng chờ.

## 15. Những diagnostic command có thể làm lệch phép đo

jcmd công bố mức impact của nhiều lệnh. Không phải lệnh nào cũng phù hợp để chạy liên tục trong khi benchmark latency.

| Lệnh | Mức impact được tài liệu JDK 26 mô tả | Lưu ý |
|---|---|---|
| JFR.start | Low | Chọn template và event phù hợp |
| JFR.dump | Low | Ghi file có thể tạo I/O |
| JFR.check | Low | Kiểm tra trạng thái recording |
| Thread.print | Medium | Phụ thuộc số thread |
| GC.heap_info | Medium | Đọc thông tin heap |
| GC.class_histogram | High | Phụ thuộc kích thước và nội dung heap |
| GC.heap_dump | High | Có thể yêu cầu full GC nếu không dùng tùy chọn phù hợp |
| path-to-gc-roots khi dump JFR | Có thể tốn thời gian và gây pause ngắn | Chỉ bật khi điều tra memory leak |
| Compiler.memory | Medium | Pause phụ thuộc số compiled methods |

Nếu đang đo p99 latency, tránh gọi heap dump, class histogram hoặc path-to-GC-roots trong cửa sổ đo trừ khi chính thao tác đó là mục tiêu điều tra. Thu thập heap dump có thể làm thay đổi đáng kể hành vi runtime.

Tài liệu JDK 26 khuyến nghị dùng jcmd thay cho các tiện ích cũ jstack, jinfo và jmap trong nhiều tình huống chẩn đoán. Đây là hướng ưu tiên cho diagnostic command, không có nghĩa mọi tiện ích cũ biến mất hoặc không còn dùng được trong mọi môi trường.

## 16. Ghi event JFR tùy chỉnh mà không tạo chi phí không cần thiết

Ứng dụng có thể định nghĩa custom JFR event để đo một giai đoạn nghiệp vụ:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.OrderCalculation")
@Label("Order Calculation")
class OrderCalculationEvent extends Event {
    @Label("Order Type")
    String orderType;

    @Label("Item Count")
    int itemCount;
}
~~~

Dùng event trong code:

~~~java
OrderCalculationEvent event = new OrderCalculationEvent();

if (event.isEnabled()) {
    event.begin();
    try {
        calculateOrder();
    } finally {
        event.end();

        if (event.shouldCommit()) {
            event.orderType = "standard";
            event.itemCount = 12;
            event.commit();
        }
    }
}
~~~

isEnabled() tránh tạo và điền payload khi không có recording quan tâm đến event. shouldCommit() kiểm tra event có thực sự được ghi theo setting và threshold hay không; nếu false, có thể tránh phần thu thập payload tốn kém.

Custom event nên chứa metadata có ích như operation name, size hoặc result category. Không ghi password, token, PII, payload nhạy cảm hoặc dữ liệu có thể làm lộ thông tin khách hàng vào recording.

Không phát event cho mọi vòng lặp nhỏ nếu tần suất quá cao. Có thể gom thống kê theo batch, lấy mẫu ở tầng ứng dụng hoặc tăng threshold để giảm chi phí.

## 17. Đo chi phí của chính công cụ quan sát

Trước khi dùng profiler làm bằng chứng, hãy chạy một phép đo overhead riêng:

1. Chọn workload và dataset cố định.
2. Chạy baseline không có profiler bổ sung.
3. Chạy cùng workload với JFR default.
4. Chạy cùng workload với JFR profile.
5. Nếu cần method tracing, chạy một lần riêng với filter hẹp.
6. So sánh throughput, p50/p95/p99, CPU, allocation, GC pause và recording size.
7. Lặp lại đủ số lần để xác định độ biến động.
8. Ghi rõ cấu hình nào được dùng khi thu thập dữ liệu điều tra.

Không bật đồng thời JFR profile, heap statistics, method tracing toàn package, debug logging và heap histogram rồi kết luận ứng dụng chậm vì một nguyên nhân cụ thể. Khi nhiều công cụ cùng hoạt động, chi phí của chúng có thể cộng hưởng và khó tách riêng.

## 18. Quy trình chẩn đoán từ nhẹ đến sâu

Có thể đi theo quy trình tăng dần mức quan sát:

~~~text
1. Xác nhận triệu chứng bằng application metrics
                |
                v
2. Kiểm tra CPU, memory, GC và container metrics
                |
                v
3. Thu thập JFR default/continuous recording
                |
                v
4. Phân loại bottleneck: CPU, I/O, lock, GC, allocation
                |
                v
5. Dùng JFR profile ngắn với event phù hợp
                |
                v
6. Chỉ instrument method nghi ngờ bằng MethodTiming/Trace
                |
                v
7. Chạy benchmark JMH hoặc load test có kiểm soát
                |
                v
8. Đo overhead công cụ và xác nhận lại trên baseline
~~~

Bắt đầu bằng metric của ứng dụng để biết người dùng đang gặp vấn đề gì. Sau đó dùng JFR để tìm vùng nghi ngờ. Khi đã có giả thuyết cụ thể, mới bật event sâu hoặc method instrumentation.

Nếu JFR cho thấy thread chờ socket nhiều, tối ưu CPU loop có thể không giúp. Nếu CPU cao và execution samples tập trung vào một method, mới nên benchmark method đó bằng JMH hoặc dùng Method Timing để kiểm tra invocation.

## 19. Checklist trước khi kết luận một tối ưu hóa có hiệu quả

- [ ] Xác định rõ metric cần cải thiện: latency, throughput, CPU, allocation hay GC.
- [ ] Baseline và candidate dùng cùng artifact, data, JDK settings và tài nguyên.
- [ ] Workload và load generator không phải bottleneck.
- [ ] Có warmup phù hợp với mục tiêu startup hoặc steady state.
- [ ] Chạy nhiều fork/iteration độc lập.
- [ ] Báo cáo mean/median, độ biến động và percentile cần thiết.
- [ ] Không loại outlier nếu chưa xác định nguyên nhân.
- [ ] Không dùng một lần chạy hoặc best score làm kết luận.
- [ ] Ghi lại JFR template và event settings.
- [ ] Đo overhead của JFR/profiler so với baseline.
- [ ] Tránh Heap Statistics khi đo latency/GC pause.
- [ ] Dùng Method Timing/Trace với filter hẹp.
- [ ] Không coi sample count là thời gian CPU chính xác.
- [ ] Phân biệt experimental JFR CPU-Time Profiling với tính năng ổn định.
- [ ] Không chạy heap dump hoặc class histogram trong cửa sổ benchmark latency.
- [ ] Xác nhận kết quả trên môi trường production-like.

## 20. Trạng thái công cụ và tính năng trong JDK 26

| Thành phần | Trạng thái | Cách dùng |
|---|---|---|
| JFR framework và JFR API | Có sẵn trong JDK | Thu thập event, điều khiển recording |
| default.jfc / profile.jfc | Cấu hình JFR đi kèm JDK | Chọn theo mức chi tiết và chi phí |
| jcmd / jfr | Công cụ JDK | Điều khiển và phân tích recording |
| JEP 509 CPU-Time Profiling | Experimental, Linux | Chỉ dùng khi xác nhận môi trường hỗ trợ |
| JEP 518 Cooperative Sampling | Có từ JDK 25, tiếp tục trong JDK 26 | Cải thiện độ ổn định và giảm safepoint bias |
| JEP 520 Method Timing & Tracing | Có từ JDK 25, tiếp tục trong JDK 26 | Instrument method có chọn lọc |
| JDK Mission Control | Công cụ riêng, không nằm trong bộ cài JDK thông thường | Phân tích recording trực quan |
| JMH | Dự án benchmark độc lập | Microbenchmark có warmup, measurement và fork |

Các JEP 518 và 520 không phải tính năng mới được giới thiệu lần đầu trong JDK 26; chúng đã xuất hiện từ JDK 25 và tiếp tục được sử dụng trong JDK 26. JEP 509 vẫn là experimental trong tài liệu JDK 26. Không cần --enable-preview để dùng JFR thông thường hoặc Method Timing/Tracing; experimental CPU-Time Profiling có trạng thái riêng và không nên được mô tả là preview API.

## Kết luận

Một kết quả hiệu năng đáng tin cậy cần kiểm soát sai số hệ thống, ước lượng biến động ngẫu nhiên và đo chi phí của chính công cụ quan sát. Dùng JMH cho microbenchmark, tách startup khỏi steady state, chạy nhiều fork và báo cáo phân bố thay vì chỉ một con số. JFR là lựa chọn phù hợp để quan sát runtime với chi phí thấp, nhưng default.jfc và profile.jfc có mức overhead khác nhau; Heap Statistics, heap dump, class histogram và method instrumentation có thể làm thay đổi đáng kể phép đo. Trong JDK 26, JFR tiếp tục có cooperative sampling và method timing/tracing từ JDK 25, còn CPU-Time Profiling theo JEP 509 vẫn experimental trên Linux. Hãy đi từ quan sát nhẹ đến sâu, đo overhead từng công cụ và chỉ kết luận khi chênh lệch lớn hơn mức biến động của phép đo.

## Tài liệu tham khảo

- [Oracle JDK 26 – Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 26 – Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 26 – The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Oracle JDK 26 – The jfr Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [Java SE 26 API – jdk.jfr Package Summary](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle JDK 26 Migration Guide – Significant Changes](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
- [JEP 509 – JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509)
- [JEP 518 – JFR Cooperative Sampling](https://openjdk.org/jeps/518)
- [JEP 520 – JFR Method Timing & Tracing](https://openjdk.org/jeps/520)
- [OpenJDK JMH – Java Microbenchmark Harness](https://github.com/openjdk/jmh)
