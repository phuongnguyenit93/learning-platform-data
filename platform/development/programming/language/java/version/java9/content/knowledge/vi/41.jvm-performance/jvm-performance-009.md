# Kiểm tra tác động trên đúng JDK, dữ liệu và môi trường triển khai

## Mục tiêu

Một thay đổi liên quan đến hiệu năng JVM chỉ có thể được đánh giá đáng tin cậy khi thử nghiệm trên đúng phiên bản JDK, đúng dữ liệu và môi trường gần với nơi ứng dụng sẽ chạy. Kết quả trên máy phát triển không tự động đại diện cho production: JDK vendor/build, JIT, garbage collector, CPU, giới hạn container, kích thước heap, dữ liệu và mô hình tải đều có thể làm thay đổi kết quả.

Mục tiêu của việc kiểm tra là trả lời được:

- Thay đổi có cải thiện chỉ số mà người dùng hoặc hệ thống thực sự quan tâm không?
- Cải thiện có lặp lại được trên đúng JDK và cấu hình triển khai không?
- Có làm xấu đi latency tail, allocation, GC, bộ nhớ, lỗi hoặc độ ổn định không?
- Kết quả có đến từ thay đổi đang thử nghiệm hay do dữ liệu, cache, tải nền hoặc môi trường khác nhau?
- Có thể tái tạo phép đo để xác nhận sau khi nâng JDK hoặc triển khai không?

Một kết luận hiệu năng cần đi kèm điều kiện đo, workload, phiên bản runtime và các chỉ số bảo vệ. Một con số throughput đơn lẻ không đủ để quyết định.

## 1. Bắt đầu bằng giả thuyết và tiêu chí đo

Trước khi chạy benchmark, hãy mô tả thay đổi và tác động dự kiến. Ví dụ:

- Giảm số object tạm được tạo trong một request.
- Giảm thời gian CPU của một phép biến đổi dữ liệu.
- Giảm allocation rate và áp lực garbage collection.
- Cải thiện p95/p99 latency khi có nhiều request đồng thời.
- Giảm thời gian startup hoặc mức heap cần thiết.
- Giữ nguyên throughput nhưng giảm CPU để tiết kiệm tài nguyên.

Chọn chỉ số phù hợp với giả thuyết:

| Nhóm | Chỉ số | Câu hỏi |
|---|---|---|
| Latency | p50, p90, p95, p99, max | Một request mất bao lâu, đặc biệt ở tail? |
| Throughput | requests/second, operations/second | Hệ thống xử lý được bao nhiêu công việc trong một đơn vị thời gian? |
| CPU | CPU time, utilization, cycles nếu có profiler | Thay đổi có giảm công việc CPU hay chỉ chuyển tải sang nơi khác? |
| Memory | heap used/committed/max, RSS, allocation bytes/op | Cần bao nhiêu bộ nhớ và tạo bao nhiêu object? |
| GC | số lần GC, pause duration, concurrent GC time | GC có gây pause hoặc tiêu tốn CPU đáng kể không? |
| I/O | disk/network throughput, wait, queue depth | Ứng dụng bị giới hạn bởi I/O hay CPU? |
| Reliability | error rate, timeout, retry, rejected task | Hiệu năng tăng có đi kèm lỗi hoặc quá tải không? |
| Cost | CPU/memory per request, instance count | Có giảm tài nguyên để đạt cùng chất lượng dịch vụ không? |

Xác định trước ngưỡng chấp nhận. Ví dụ: p95 phải giảm ít nhất 5%, error rate không tăng, p99 không được xấu hơn 2%, heap không vượt giới hạn container. Các con số này phải xuất phát từ SLA/SLO và đặc điểm ứng dụng, không lấy làm ngưỡng chung cho mọi dự án.

Đừng tối ưu một chỉ số đơn lẻ nếu nó làm hỏng chỉ số quan trọng hơn. Throughput tăng nhưng p99 tăng mạnh hoặc error rate tăng có thể là một regression.

## 2. Xác nhận đúng JDK và runtime đang chạy

Hai chương trình cùng biên dịch từ một source có thể có hành vi hiệu năng khác nhau trên các JDK khác nhau. JIT compiler, garbage collector, class library, default flags và implementation nội bộ có thể thay đổi theo phiên bản, vendor và bản cập nhật.

Trước mỗi phép đo, ghi nhận ít nhất:

- JDK vendor và phiên bản đầy đủ, gồm build number.
- Phiên bản javac dùng để biên dịch và phiên bản Java dùng để chạy.
- Runtime VM name/version và kiến trúc CPU.
- Các JVM flags có ảnh hưởng đến heap, GC, JIT và thread.
- Số CPU mà JVM nhìn thấy và giới hạn CPU thực tế.
- Heap max, giới hạn RAM của tiến trình/container.
- Hệ điều hành, kernel, image và thư viện native liên quan.
- Artifact, commit và dependency versions đang được đo.

Các lệnh cơ bản:

~~~bash
java -version
javac -version
~~~

Đối với tiến trình đang chạy, dùng `jcmd` từ JDK tương ứng:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
jcmd <pid> GC.heap_info
~~~

`VM.flags` giúp xác nhận flags thực sự có hiệu lực; `VM.command_line` giúp đối chiếu lệnh khởi chạy; `GC.heap_info` cung cấp thông tin heap tại thời điểm kiểm tra. Cẩn thận khi chia sẻ output command line vì tham số khởi chạy có thể chứa thông tin nhạy cảm.

### Phân biệt target compile và runtime

`javac --release N` kiểm soát API và bytecode mục tiêu khi biên dịch. Nó không đảm bảo ứng dụng đang được chạy bằng đúng runtime N, cũng không mô phỏng hiệu năng của JDK N.

Ví dụ:

~~~bash
javac --release 9 -Xlint:all MyApplication.java
java MyApplication
~~~

Lệnh trên chỉ chứng minh mã được biên dịch với API/bytecode target Java 9; runtime được chọn bởi lệnh `java` trong PATH. Khi kiểm tra hiệu năng JDK 17, 21 hoặc một bản JDK khác, hãy chạy artifact trên chính runtime đó và ghi nhận phiên bản đầy đủ.

Khi so sánh hai JDK:

1. Giữ nguyên source, dependency, dữ liệu và cấu hình ứng dụng.
2. Tạo artifact theo quy trình build đã thống nhất.
3. Chạy riêng trên từng JDK, không trộn kết quả giữa các runtime.
4. Ghi đầy đủ vendor, patch/build và JVM flags của từng lần chạy.
5. Kiểm tra cả tính đúng đắn và hiệu năng trên từng runtime.

Không giả định hai bản JDK có cùng vendor hoặc cùng major version sẽ có cùng default GC, JIT behavior hay cách xử lý container.

## 3. Ghi nhận cấu hình runtime bằng chương trình

Có thể ghi lại một số thông tin runtime ngay trong ứng dụng. Ví dụ dưới đây dùng API có từ Java 9, không phụ thuộc vào công cụ bên ngoài.

Tệp `RuntimeEnvironmentSnapshot.java`:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.time.ZoneId;
import java.util.Locale;

public class RuntimeEnvironmentSnapshot {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        RuntimeMXBean vm = ManagementFactory.getRuntimeMXBean();

        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.runtime.version=" + Runtime.version());
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("vm.name=" + vm.getVmName());
        System.out.println("vm.version=" + vm.getVmVersion());
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.version=" + System.getProperty("os.version"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("availableProcessors=" + runtime.availableProcessors());
        System.out.println("maxHeapBytes=" + runtime.maxMemory());
        System.out.println("locale=" + Locale.getDefault().toLanguageTag());
        System.out.println("timezone=" + ZoneId.systemDefault());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 9 -Xlint:all RuntimeEnvironmentSnapshot.java
java RuntimeEnvironmentSnapshot
~~~

Output mẫu có dạng:

~~~text
pid=<process-id>
java.version=<major.minor.patch>
java.runtime.version=<full-runtime-build>
java.vendor=<JDK-vendor>
vm.name=<VM-name>
vm.version=<VM-build>
os.name=<operating-system>
os.version=<operating-system-version>
os.arch=<architecture>
availableProcessors=<processors-visible-to-JVM>
maxHeapBytes=<maximum-heap-bytes>
locale=<default-locale>
timezone=<default-time-zone>
~~~

Các giá trị phụ thuộc máy chạy. `availableProcessors()` là số processor mà JVM nhìn thấy tại thời điểm gọi; trong container, con số này cần được đối chiếu với CPU quota/cpuset của nền tảng. `maxMemory()` là giới hạn heap của JVM, không phải toàn bộ RAM tiến trình hay giới hạn memory của container.

Không in toàn bộ system properties hoặc environment variables vào log chẩn đoán. Chúng có thể chứa password, token, đường dẫn nội bộ hoặc dữ liệu nhạy cảm. Chỉ ghi các trường đã được chọn và kiểm soát.

## 4. Dùng dữ liệu đại diện cho workload thật

Benchmark với dữ liệu không giống production có thể cho kết luận sai. Một thuật toán có thể nhanh với mảng nhỏ nhưng chậm khi dữ liệu vượt cache CPU; một cache có thể hoạt động tốt với key phân bố đều nhưng suy giảm mạnh khi có hot key hoặc skew.

Trước khi đo, mô tả dataset:

| Thuộc tính | Cần kiểm soát |
|---|---|
| Kích thước | Số record, số object, tổng byte, kích thước payload |
| Phân bố | Giá trị phổ biến, hiếm, outlier, skew, hot key |
| Kiểu dữ liệu | Null, chuỗi rỗng, chuỗi dài, Unicode, số lớn, object lồng nhau |
| Tính lặp | Dữ liệu trùng, key trùng, cache hit/miss |
| Thứ tự | Có được sắp xếp, ngẫu nhiên hay theo thời gian không? |
| Tính nén | Payload có compressible hay chứa dữ liệu gần ngẫu nhiên? |
| Locality | Dữ liệu nằm trong heap/cache, trên disk hay qua network? |
| Tính biến đổi | Dữ liệu có bị sửa trong quá trình benchmark không? |

Dùng snapshot hoặc dataset cố định cho các lần A/B. Nếu dữ liệu được sinh tự động, cố định random seed để có thể tái tạo. Nếu dùng dữ liệu production, phải loại bỏ hoặc giả danh dữ liệu nhạy cảm theo chính sách của tổ chức.

Nên thử nhiều kích thước và phân bố:

- Dataset nhỏ vừa heap/cache.
- Dataset đủ lớn để thể hiện allocation và GC.
- Dataset gần kích thước production.
- Trường hợp phổ biến theo traffic thật.
- Trường hợp biên và worst-case hợp lệ.
- Cache nóng và cache lạnh nếu ứng dụng phụ thuộc cache.

Không chỉ dùng dữ liệu trung bình. Tail latency thường bị chi phối bởi outlier, object graph lớn, key nóng, lock contention hoặc I/O chậm.

## 5. Mô hình tải phải giống cách hệ thống được sử dụng

Ngoài dataset, phải mô phỏng cách request đến ứng dụng:

- Tỷ lệ từng loại operation.
- Số client hoặc worker đồng thời.
- Request rate và burst.
- Payload size và tỷ lệ cache hit/miss.
- Think time giữa các request.
- Tỷ lệ lỗi, retry và timeout.
- Tỷ lệ đọc/ghi và mức tranh chấp dữ liệu.
- Thời gian chạy liên tục và hành vi khi tải tăng/giảm.

Phân biệt hai mô hình tải:

- **Closed-loop:** client gửi request tiếp theo sau khi request trước hoàn tất. Khi hệ thống chậm, tốc độ phát request cũng giảm.
- **Open-loop:** request được phát theo lịch/tốc độ định trước, không phụ thuộc request trước đã hoàn tất hay chưa. Mô hình này hữu ích khi cần kiểm tra khả năng đáp ứng một arrival rate cố định.

Nếu dùng closed-loop cho hệ thống quá tải, tốc độ gửi request giảm theo latency có thể che khuất mức độ quá tải. Với open-loop, cần kiểm tra load generator có đủ năng lực phát tải và ghi nhận request bị trễ hoặc bỏ lỡ. Tránh coordinated omission: chỉ đo thời gian của request thực sự được gửi có thể đánh giá thấp latency trong thời gian hệ thống bị nghẽn.

Tách riêng load generator khỏi máy ứng dụng khi có thể. Nếu cả hai cùng tranh CPU, memory hoặc network, phép đo không còn phản ánh riêng ứng dụng.

## 6. Microbenchmark: dùng JMH thay vì vòng lặp tự viết

Đối với phép đo một method hoặc một đoạn code nhỏ, JMH là công cụ benchmark phù hợp cho JVM. JMH xử lý warmup, fork, measurement iteration và một số vấn đề tối ưu của JIT mà vòng lặp `System.nanoTime()` tự viết thường bỏ sót.

Một vòng lặp tự viết có thể bị ảnh hưởng bởi:

- JIT chưa tối ưu hoặc đang biên dịch trong lúc đo.
- Dead-code elimination nếu kết quả không được sử dụng.
- Constant folding nếu input/result quá dễ dự đoán.
- Escape analysis và inlining làm thay đổi code thực thi.
- Garbage collection xảy ra ngoài khoảng đo hoặc không được tính đúng.
- Chi phí tạo dữ liệu bị trộn vào thời gian của operation cần đo.

### Ví dụ JMH

Đo hit/miss của HashMap với nhiều kích thước dữ liệu:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Mode;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class MapLookupBenchmark {
    @Param({"100", "10000"})
    public int size;

    private Map<Integer, Integer> values;
    private int hitKey;

    @Setup(Level.Trial)
    public void setup() {
        values = new HashMap<>();
        for (int i = 0; i < size; i++) {
            values.put(i, i * 2);
        }
        hitKey = size / 2;
    }

    @Benchmark
    public Integer lookupHit() {
        return values.get(hitKey);
    }

    @Benchmark
    public Integer lookupMiss() {
        return values.get(-1);
    }
}
~~~

Ví dụ cần dependency JMH và annotation processor theo hướng dẫn của dự án JMH; đây không phải chương trình Java thuần có thể chạy chỉ bằng `javac` không dependency. Sau khi đóng gói benchmark thành executable JMH jar, chạy với cấu hình tương ứng:

~~~bash
java -jar target/benchmarks.jar MapLookupBenchmark -wi 5 -i 8 -f 3
~~~

Có thể dùng profiler tích hợp của JMH khi phù hợp:

~~~bash
java -jar target/benchmarks.jar MapLookupBenchmark -prof gc
~~~

`@Warmup` dành thời gian cho JVM ổn định trước khi đo; `@Measurement` định nghĩa các iteration lấy mẫu; `@Fork` chạy trong JVM process riêng để giảm ảnh hưởng trạng thái từ lần benchmark trước. Tham số `@Param` cho phép đo nhiều kích thước dữ liệu trong cùng một benchmark.

JMH không thay thế load test toàn hệ thống. Microbenchmark trả lời câu hỏi về operation nhỏ trong điều kiện kiểm soát; nó không dự đoán đầy đủ network, database, thread pool, queue, cache phân tán hoặc hành vi production.

## 7. Warmup, fork và lặp lại phép đo

JVM là runtime có JIT compiler. Thời gian chạy ban đầu có thể bao gồm class loading, bytecode interpretation, profiling và compilation. Vì vậy, một lần đo ngay sau startup thường không đại diện cho steady state.

Cần tách các kịch bản:

| Kịch bản | Cách đo |
|---|---|
| Cold startup | Khởi động process mới và đo thời gian đến trạng thái sẵn sàng |
| Warmup | Gửi workload đại diện để JVM, cache và connection pool ổn định |
| Steady state | Đo sau warmup trong khoảng thời gian đủ dài |
| Burst | Tăng tải nhanh để đo khả năng hấp thụ đột biến |
| Soak test | Chạy lâu để phát hiện leak, heap growth, queue growth và degradation |
| Recovery | Giảm tải hoặc phục hồi dependency rồi đo thời gian trở lại bình thường |

Đối với A/B:

1. Chạy baseline và ghi lại đầy đủ cấu hình.
2. Chạy candidate với cùng workload và dataset.
3. Lặp lại nhiều lần, tốt nhất trên cùng phần cứng và trong điều kiện tải nền tương đương.
4. Nếu có thể, thay đổi thứ tự chạy để tránh việc một phiên bản luôn được đo khi máy mát hoặc cache đang nóng.
5. Báo cáo phân bố kết quả, không chỉ một giá trị tốt nhất.
6. Kiểm tra kết quả có lặp lại qua các process/fork hay không.

Không loại bỏ một lần chạy xấu chỉ vì nó không thuận mắt. Nếu có lý do hợp lệ như máy bị tác vụ nền chiếm CPU, ghi lại lý do và chạy lại cả cặp baseline/candidate theo cùng điều kiện.

## 8. Phân tích kết quả và độ tin cậy

Với latency, báo cáo ít nhất p50, p95 và p99. Với throughput, ghi request/operation rate cùng error rate. Với memory, xem allocation rate, heap occupancy và RSS. Với GC, xem cả pause lẫn thời gian CPU của concurrent phases.

Khi so sánh:

- Báo cáo số tuyệt đối và phần trăm thay đổi.
- Ghi số lần chạy, thời lượng và số request/sample.
- So sánh cùng percentile với cùng percentile.
- Không lấy trung bình các percentile từ nhiều lần chạy rồi coi đó là percentile chung.
- Nếu có thể, tính confidence interval hoặc dùng phương pháp thống kê phù hợp.
- Kiểm tra variance; kết quả dao động lớn là dấu hiệu phép đo chưa được kiểm soát.
- Phân biệt cải thiện có ý nghĩa thực tế với chênh lệch nhỏ hơn noise của phép đo.

Ví dụ bảng báo cáo:

| Chỉ số | Baseline | Candidate | Thay đổi | Ngưỡng |
|---|---:|---:|---:|---|
| Throughput | 8.000 req/s | 8.600 req/s | +7,5% | Tăng |
| p95 latency | 120 ms | 112 ms | -6,7% | Không tăng |
| p99 latency | 260 ms | 275 ms | +5,8% | Không được xấu đi |
| CPU | 72% | 70% | -2 điểm % | Không tăng đáng kể |
| Error rate | 0,02% | 0,02% | Không đổi | Không tăng |

Các số trên chỉ minh họa cách trình bày. Trong ví dụ, throughput và p95 tốt hơn nhưng p99 xấu hơn; chưa thể kết luận candidate tốt hơn nếu p99 là chỉ số bảo vệ của dịch vụ.

Không so sánh số đo từ hai máy khác CPU, hai giới hạn container khác nhau hoặc hai dataset khác nhau rồi quy toàn bộ chênh lệch cho code. Nếu bắt buộc phải dùng hai môi trường khác nhau, cần thiết kế đối chứng và nêu rõ giới hạn của kết luận.

## 9. Dùng JFR, jcmd và GC logging để tìm nguyên nhân

Benchmark cho biết điều gì thay đổi; profiler giúp giải thích vì sao.

### Java Flight Recorder

Trên các JDK hiện đại có hỗ trợ JFR, có thể ghi profile của process đang chạy:

~~~bash
jcmd <pid> JFR.start name=performance settings=profile duration=120s filename=performance.jfr
~~~

Sau khi hoàn tất, mở file bằng Java Mission Control hoặc công cụ phân tích JFR phù hợp. Các nhóm event hữu ích gồm CPU samples, allocation, lock contention, thread park, exceptions, class loading, I/O và GC.

JFR là công cụ chẩn đoán có overhead thấp trong nhiều tình huống, nhưng vẫn cần kiểm tra cấu hình recording và overhead trong workload cụ thể. Không nên mặc định rằng bật profiler không ảnh hưởng kết quả.

### GC và safepoint logging

Java 9 trở lên có unified JVM logging. Có thể bật log GC và safepoint khi khởi chạy:

~~~bash
java '-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags' -jar app.jar
~~~

Log giúp phân tích thời điểm GC, loại collector event, heap trước/sau và pause. Cần xem cả xu hướng theo thời gian thay vì chỉ nhìn một lần GC.

### Một số lệnh jcmd hữu ích

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
jcmd <pid> JFR.check
~~~

Chỉ chạy lệnh phù hợp với JDK/runtime và quyền của môi trường. Thread dump hoặc JFR có thể chứa tên thread, class, đường dẫn và thông tin nội bộ; quản lý quyền truy cập và lưu trữ file chẩn đoán như dữ liệu vận hành nhạy cảm.

## 10. Kiểm tra đúng môi trường triển khai

Một benchmark trên laptop hoặc máy build agent có thể khác production ở nhiều lớp:

### CPU và giới hạn tài nguyên

- Model CPU, số core, SMT và kiến trúc.
- CPU quota, cpuset, throttling và frequency scaling.
- NUMA placement và tranh chấp CPU với process khác.
- RAM vật lý, container memory limit và swap.
- Giới hạn heap của JVM so với memory limit toàn container.

Trong container, `Runtime.availableProcessors()` và giới hạn heap có thể phụ thuộc cấu hình runtime/container. Hãy kiểm tra số CPU JVM nhìn thấy cùng CPU quota/cpuset thực tế. Một container có thể nhìn thấy nhiều CPU nhưng bị giới hạn quota thấp hơn; CPU throttling sẽ làm latency dao động.

### Hệ điều hành và hạ tầng

Ghi nhận:

- OS/kernel, kiến trúc và thư viện native.
- Container image và base image.
- Filesystem, loại volume và tốc độ disk.
- Network path, DNS, TLS, proxy và service mesh.
- Database/cache/queue version và vị trí triển khai.
- Số replica, autoscaling, readiness/liveness probe.
- Sidecar, agent giám sát và các process nền.

Nếu ứng dụng dùng native library, crypto provider, compression hoặc filesystem behavior, khác biệt OS/architecture có thể tác động trực tiếp đến hiệu năng.

### JVM và container

Ghi nhận heap min/max, GC, thread count, direct memory, stack size và các flags có ảnh hưởng đến runtime. Không sao chép một bộ JVM flags cũ sang JDK mới mà không xác minh flag còn được hỗ trợ và còn phù hợp.

So sánh trên cùng container image và cùng CPU/memory limits khi mục tiêu là đánh giá thay đổi code/JDK. Nếu thay đổi đồng thời cả JDK, image, GC và heap sizing, kết quả không chỉ ra được yếu tố nào tạo ra tác động.

### Cold cache và warm cache

Production có thể bắt đầu với cache rỗng sau deploy, hoặc có cache nóng trong vận hành bình thường. Đo riêng:

- Startup sau khi cache rỗng.
- Giai đoạn warmup cache.
- Steady state với cache nóng.
- Cache miss hoặc cache eviction tăng đột biến.

Không so sánh baseline có cache nóng với candidate có cache lạnh.

## 11. Kiểm tra tính đúng đắn song song với hiệu năng

Một thay đổi nhanh hơn nhưng làm sai kết quả không phải là tối ưu hợp lệ.

Mỗi lần đo cần xác nhận:

- Output nghiệp vụ giống nhau với cùng input.
- Không mất hoặc nhân đôi record.
- Không thay đổi thứ tự nếu thứ tự là yêu cầu.
- Không tăng exception, timeout hoặc retry.
- Không tạo race condition hoặc deadlock.
- Không làm tăng memory leak, queue growth hoặc thread growth.
- Không phá vỡ compatibility với JDK và dependency đang hỗ trợ.

Nếu candidate thay đổi thuật toán, hãy dùng test dữ liệu biên và property-based tests khi phù hợp. Benchmark chỉ nên chạy sau khi correctness test đã xác nhận hai cách triển khai tương đương theo hợp đồng nghiệp vụ.

## 12. Quy trình A/B có thể lặp lại

Một quy trình thực tế:

1. **Chốt câu hỏi:** xác định thay đổi, giả thuyết và chỉ số chính.
2. **Đóng băng đầu vào:** commit, artifact, dependency, dataset, random seed và workload profile.
3. **Chốt runtime:** JDK vendor/build, JVM flags, OS/image, CPU và memory limits.
4. **Chạy correctness tests:** xác nhận output và invariant giống nhau.
5. **Chạy baseline:** warmup, measurement, forks/repetitions và lưu raw results.
6. **Chạy candidate:** giữ nguyên điều kiện; chỉ thay đổi yếu tố đang đánh giá.
7. **Thu thập profile:** JFR, GC log, CPU/allocation/lock data khi cần giải thích.
8. **So sánh:** latency percentiles, throughput, resource use, error rate và variance.
9. **Chạy soak/recovery:** nếu thay đổi ảnh hưởng memory, GC, cache hoặc concurrency.
10. **Quyết định:** chấp nhận, từ chối hoặc thiết kế phép đo bổ sung; lưu lại cấu hình và kết quả.

Mỗi lần chạy nên có mã nhận dạng và metadata. Một báo cáo benchmark có thể lưu các trường:

~~~text
change-id
git-commit
artifact-sha256
jdk-vendor
jdk-runtime-version
os-and-architecture
container-image
cpu-limit
memory-limit
jvm-flags
dataset-version-and-seed
workload-profile
warmup-duration
measurement-duration
forks-or-repetitions
throughput
latency-p50-p95-p99
cpu-and-memory
allocation-and-gc
error-rate
raw-result-location
~~~

Không ghi secret hoặc dữ liệu cá nhân vào metadata benchmark.

## 13. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
|---|---|---|
| Đo trên JDK khác production | JIT, GC, class library và defaults có thể khác | Chạy trên đúng vendor/build JDK mục tiêu |
| Nghĩ `--release` chọn runtime | `--release` chỉ kiểm soát compile target | Xác minh bằng `java -version` và runtime đang chạy |
| Dùng dataset quá nhỏ | Không phản ánh heap, cache, allocation và GC thực tế | Dùng nhiều kích thước và phân bố đại diện |
| Chỉ đo dữ liệu trung bình | Bỏ qua hot key, outlier và tail latency | Đo cả phân bố và trường hợp biên |
| Đo ngay sau startup | JIT và cache chưa ổn định | Tách cold-start, warmup và steady-state |
| Tự viết vòng lặp nanoTime cho microbenchmark | Dễ bị JIT, dead-code elimination và constant folding làm sai | Dùng JMH |
| Chạy baseline và candidate với tải khác nhau | Không thể quy chênh lệch cho thay đổi | Cố định workload và điều kiện đo |
| Chỉ báo cáo throughput | Có thể che p99, error rate và CPU cost | Báo cáo latency percentiles và guardrails |
| Chỉ đo một lần | Kết quả có thể là noise hoặc may rủi | Lặp lại, dùng forks và phân tích variance |
| Load generator bị nghẽn | Ứng dụng không nhận đủ tải dự kiến | Tách load generator và kiểm tra năng lực phát tải |
| Bỏ qua CPU quota/container limit | JVM có thể bị throttling hoặc giới hạn khác | Đo trong cùng giới hạn triển khai |
| Bật profiler rồi so với baseline không profiler | Overhead làm hai phép đo không tương đương | Giữ profiling giống nhau hoặc đo riêng |
| Thay nhiều flags cùng lúc | Không biết yếu tố nào tạo ra tác động | Thay đổi từng yếu tố và giữ log cấu hình |
| Coi log GC là toàn bộ phân tích hiệu năng | Không giải thích đầy đủ CPU, lock, I/O và allocation | Kết hợp JFR/profiler và workload metrics |
| Chọn candidate vì trung bình tốt hơn | Tail latency hoặc error rate có thể xấu đi | Dùng tiêu chí chấp nhận định trước |

## 14. Checklist trước khi kết luận

- [ ] Đã ghi JDK vendor, full runtime build và compiler version.
- [ ] Đã xác minh JVM flags, GC, heap và runtime thực tế.
- [ ] Đã ghi OS, architecture, CPU quota/cpuset, RAM và container limits.
- [ ] Artifact, commit và dependency giống nhau giữa baseline/candidate.
- [ ] Dataset có kích thước, phân bố và random seed xác định.
- [ ] Workload mix, concurrency và arrival rate đại diện cho thực tế.
- [ ] Đã tách cold startup, warmup và steady-state.
- [ ] Microbenchmark dùng JMH; load test dùng load generator đủ năng lực.
- [ ] Có nhiều lần chạy và báo cáo variance/percentiles.
- [ ] Đã kiểm tra throughput, p95/p99, CPU, memory, GC và error rate.
- [ ] Đã kiểm tra correctness, timeout, retry và tài nguyên sau thời gian dài.
- [ ] JFR/GC logs được thu thập khi cần tìm nguyên nhân.
- [ ] Kết quả có thể tái tạo từ metadata và raw result đã lưu.
- [ ] Kết luận đáp ứng SLA/SLO và không vi phạm guardrails.

## 15. Tài liệu tham khảo

- [JMH — OpenJDK Code Tools](https://openjdk.org/projects/code-tools/jmh/)
- [Java Flight Recorder — Oracle Documentation](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf)
- [jcmd — Java SE 17 Tools Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Unified JVM Logging — Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Runtime.version() — Java SE API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#version())

Đánh giá hiệu năng chỉ đáng tin khi runtime, dữ liệu, workload và hạ tầng được kiểm soát. Dùng JMH cho phép đo nhỏ, load test cho hành vi toàn hệ thống, JFR/GC logs để tìm nguyên nhân, rồi lưu đầy đủ metadata để phép đo có thể lặp lại trên đúng JDK và môi trường triển khai.