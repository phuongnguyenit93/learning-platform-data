# Đo hiệu năng đúng cách và tổng hợp tiêu chí chọn API trong Java Functional Programming

**Java Stream API không mặc định nhanh hơn vòng lặp, và vòng lặp cũng không mặc định là lựa chọn tốt nhất cho mọi bài toán.** Muốn quyết định giữa for/while, lambda, Stream, primitive stream, collector, reduce hay parallel stream, trước hết phải kiểm tra **tính đúng**, sau đó đo **đúng loại hiệu năng trong điều kiện có thể tái hiện** và cân nhắc tính dễ đọc, bộ nhớ, trạng thái, khả năng mở rộng cùng ràng buộc nghiệp vụ.

Một thí nghiệm chạy System.nanoTime() một lần rồi kết luận “API A nhanh gấp hai lần API B” rất dễ sai. JVM có **JIT compilation**, warmup, garbage collection, escape analysis, dead-code elimination, tối ưu theo loại dữ liệu và môi trường chạy. Bên cạnh đó, hai đoạn code có thể trả kết quả giống nhau với dữ liệu nhỏ nhưng khác semantics về thứ tự, duplicate, null, exception hoặc side effect.

Bài học thuộc phần **Kiểm thử và thực hành** của module **Java core – functional-programming**. Trọng tâm là:

- Thiết kế phép so sánh **cùng bài toán và cùng kết quả**.
- Hiểu thước đo thời gian, throughput, latency, allocation, GC và bộ nhớ.
- Biết giới hạn của System.nanoTime() và khi nào dùng **JMH**.
- Tránh benchmark sai vì JIT, constant folding, dead-code elimination, boxing, dữ liệu không đại diện hoặc chi phí setup.
- Đánh giá tác động của Stream.lazy, pipeline, stateful operations và parallel overhead.
- Tổng hợp tiêu chí chọn API theo **correctness → clarity → measurable performance**.
- Có chương trình **Java 17+ biên dịch/chạy độc lập** cho correctness và một probe thời gian chỉ mang tính minh họa, cùng mẫu JMH được ghi rõ điều kiện phụ thuộc thư viện.

## 1. Chọn API là bài toán đa tiêu chí

Ví dụ cùng tính tổng bình phương của các số chẵn trong một mảng:

~~~java
static long byLoop(int[] data) {
    long sum = 0L;
    for (int n : data) {
        if ((n & 1) == 0) {
            sum += (long) n * n;
        }
    }
    return sum;
}
~~~

Một phiên bản dùng primitive stream:

~~~java
static long byIntStream(int[] data) {
    return Arrays.stream(data)
        .filter(n -> (n & 1) == 0)
        .mapToLong(n -> (long) n * n)
        .sum();
}
~~~

Hai đoạn code có cùng mục tiêu: duyệt dữ liệu đầu vào, chọn số chẵn, bình phương rồi cộng vào long. Tuy nhiên, cùng semantics chỉ được bảo đảm nếu việc dùng số học, xử lý ngoại lệ và phạm vi đầu vào tương thích.

Một phiên bản dùng boxed Stream:

~~~java
static long byBoxedStream(int[] data) {
    return Arrays.stream(data).boxed()
        .filter(n -> (n & 1) == 0)
        .mapToLong(n -> (long) n * n)
        .sum();
}
~~~

Một phiên bản song song:

~~~java
static long byParallelStream(int[] data) {
    return Arrays.stream(data).parallel()
        .filter(n -> (n & 1) == 0)
        .mapToLong(n -> (long) n * n)
        .sum();
}
~~~

Cả bốn đều **có thể đúng**. Nhưng mức overhead, boxing, chia task, tải CPU, cache và cơ hội JIT tối ưu khác nhau. Benchmark có giá trị khi các biến thể **cùng làm một công việc cần thiết**, không phải một bên bỏ qua validation hoặc tạo ít dữ liệu đầu ra hơn.

### 1.1. Thứ tự quyết định hợp lý

1. **Correctness**: kết quả, null, overflow, thứ tự, duplicate, lifecycle và lỗi phải đúng.
2. **Maintainability**: tên hàm, hợp đồng dữ liệu, độ rõ của pipeline và khả năng test.
3. **Resource usage**: cấp phát, bộ nhớ đỉnh, I/O, GC và contention.
4. **Performance**: thời gian trung bình, throughput, latency tail, khả năng mở rộng dưới tải thật.
5. **Operational safety**: hành vi trong production, observability, cancellation, retry và concurrency.

Không chọn API chỉ vì một lần đo nanosecond thấp hơn. Một cách nhanh hơn vài phần trăm trong microbenchmark có thể làm code khó hiểu hoặc tạo rủi ro race nghiêm trọng.

## 2. Đầu tiên phải chứng minh hai cách làm tương đương

Trước khi so thời gian, viết kiểm thử để chứng minh:

- Cùng **tập dữ liệu đầu vào** và điều kiện lọc.
- Cùng kiểu kết quả và cùng quy tắc overflow/làm tròn.
- Cùng quy tắc **thứ tự và phần tử trùng** nếu bài toán phụ thuộc thứ tự.
- Cùng cách xử lý **null, input rỗng và input lỗi**.
- Không có phiên bản nào lén sửa nguồn hoặc dựa vào mutable state ngoài.
- Với nguồn Stream một lượt, phải **tạo stream mới** cho mỗi lần đo.

Ví dụ:

~~~java
int[] data = IntStream.rangeClosed(1, 200_000).toArray();

long a = byLoop(data);
long b = byIntStream(data);
long c = byBoxedStream(data);
long d = byParallelStream(data);

if (!(a == b && a == c && a == d)) {
    throw new AssertionError("Algorithms differ");
}
~~~

Phần trên giả định các phương thức đã được định nghĩa. Bài toán này dùng long cho bình phương và tổng để tránh tràn int do n*n khi n lớn; chính phần ép kiểu **(long) n * n** trước phép nhân là cần thiết.

### 2.1. Đừng so sánh hai API thực hiện logic khác nhau

Các cặp sau **không tương đương**, trừ khi bài toán định nghĩa rõ:

~~~java
stream.sorted(comparator).findFirst();
stream.min(comparator);
~~~

Hai cách có thể chọn một cực trị như nhau khi comparator/tie semantics phù hợp, nhưng sorted có chi phí và ngữ nghĩa thứ tự khác. Không dùng sorted chỉ để lấy min khi một min trực tiếp đáp ứng đầy đủ yêu cầu.

~~~java
stream.filter(predicate).count();
stream.map(sideEffectingMapper).count();
~~~

Nếu yêu cầu là đếm phần tử thỏa predicate thì hai cách không cùng bài toán. Thêm side effect vào map không phải cách đo “đã thực sự chạy bao nhiêu phần tử” vì Stream có thể tối ưu hóa một số callback không ảnh hưởng terminal result.

### 2.2. Dùng kiểm thử unit trước benchmark

Trong test nên bao phủ dữ liệu:

- Rỗng và chỉ một phần tử.
- Nhiều phần tử trùng.
- Số âm, số 0, cận số nguyên và tổng lớn.
- Giá trị null khi API hợp đồng cho phép.
- Trạng thái đầu vào mutable và chia sẻ qua nhiều caller.
- Cả ordered và unordered, nếu đó là dimension của bài toán.
- Parallel output khi phép tổng hợp có identity, associativity và compatibility thích hợp.

Nếu kết quả khác nhau, **dừng đo** và sửa correctness trước. Không cố dùng benchmark để giải thích lỗi logic.

## 3. Đo cái gì? Latency, throughput, allocation và tail

“Chạy nhanh” có nhiều nghĩa.

| Metric | Diễn giải | Khi có giá trị |
| --- | --- | --- |
| Time per operation | Thời gian cho một thao tác | Microbenchmark một thuật toán |
| Throughput | Số thao tác hoàn tất mỗi đơn vị thời gian | Xử lý nhiều request/batch |
| p50/p95/p99 latency | Phân vị thời gian đáp ứng | Hệ thống cần độ trễ ổn định |
| Allocation rate | Byte được cấp phát mỗi thao tác/giây | Tìm overhead boxing/object |
| GC activity | Số lần/pause/time của GC | Workload có nhiều allocation |
| Peak memory | Bộ nhớ đỉnh trong lúc xử lý | Dữ liệu lớn, sorted/grouping |
| CPU utilization | Sử dụng CPU trên các core | Phân tích parallel speedup |
| Scalability | Thay đổi khi tăng dữ liệu hoặc worker | Batch/parallel processing |

**Throughput cao không đồng nghĩa p99 latency thấp.** Parallel stream có thể cải thiện batch throughput nhưng chiếm nhiều CPU, làm tăng độ trễ của các request khác cùng JVM. Một phép tính rất nhanh nhưng cấp phát nhiều object có thể tạo sức ép GC khi chạy hàng triệu lần.

### 3.1. Wall-clock time và CPU time

System.nanoTime() cho phép đo **thời gian trôi qua giữa hai mốc** trong cùng JVM, phù hợp đo elapsed time ngắn tương đối. Nó **không** trực tiếp cho biết thời gian CPU tiêu thụ riêng cho một thread, không loại bỏ scheduling, GC, page faults hoặc nhiễu phần cứng.

Với parallel workload, elapsed time có thể giảm dù **tổng CPU work** tăng do nhiều thread cùng chạy. Nếu tối ưu throughput/cost trên server, hãy quan sát đồng thời cả elapsed time và lượng tài nguyên sử dụng.

### 3.2. Đơn vị và cách báo cáo

Kết quả 5 ms/op và 200 ops/s có thể cùng mô tả một workload, nhưng cần ghi rõ điều kiện. Khi báo cáo, luôn nêu:

- Đơn vị: ns/op, us/op, ms/op hay ops/s.
- Dữ liệu: số phần tử và phân bố giá trị.
- Chế độ: sequential hay parallel, số worker/CPU.
- Môi trường: phiên bản JDK, cấu hình heap, OS, CPU.
- Cách chạy: warmup, measurement iteration, fork.
- Kết quả: phân bố và độ biến thiên; không chỉ lấy một số nhỏ nhất rồi tuyên bố nhanh hơn.

## 4. Vì sao gọi System.nanoTime() một lần là không đủ?

Một phép đo thủ công ngắn:

~~~java
long start = System.nanoTime();
long result = byIntStream(data);
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

Đây là **đo thời gian trôi qua của một lần gọi**, không phải benchmark đáng tin để so sánh API.

Các nguồn sai lệch lớn:

1. **Class loading / initialization** có thể xảy ra ở lần gọi đầu.
2. **JIT compilation** cần thời gian và thông tin thực thi để tối ưu mã.
3. **Tiered compilation** có thể thay đổi chất lượng mã giữa các lượt.
4. **GC** có thể tạm dừng hoặc chạy cùng giai đoạn đo.
5. **OS scheduler** có thể dừng thread hoặc thay đổi CPU placement.
6. **CPU frequency/temperature** có thể thay đổi do turbo boost hoặc thermal throttling.
7. **Code/data cache** khác nhau giữa warm/cold inputs.
8. **Dead-code elimination** có thể loại bỏ công việc nếu kết quả không được sử dụng.
9. **Constant folding** có thể thay phép tính bằng giá trị được biết trước.
10. **Benchmark overhead** có thể chiếm phần đáng kể của phép đo quá nhỏ.
11. **Allocation / escape analysis** có thể làm phiên bản đo khác code production.
12. **Load nền** từ những process khác làm nhiễu thời gian.

Vì vậy, chạy vài lần trong cùng một main không thể thay thế một harness benchmark chuyên dụng.

### 4.1. Warmup là gì?

JVM có thể chạy mã bằng interpreter/compiled tiers trước khi đạt trạng thái đã tối ưu cho mẫu thực thi. **Warmup** chạy workload trước giai đoạn measurement để JIT có cơ hội tối ưu và class được nạp.

Nhưng warmup **không phải phép màu**: cần đủ và phù hợp workload, không bảo đảm nhiệt độ CPU/GC hay dữ liệu cache trở nên giống production. Nếu ứng dụng thực phải trả lời nhanh ở cold start, thì **startup/cold latency** là metric riêng, không thể xóa hoàn toàn warmup rồi gọi kết quả là chuẩn cho mọi mục tiêu.

### 4.2. Fork và trạng thái JVM

Chạy benchmark trong nhiều **JVM process tách biệt** giúp giảm phụ thuộc vào trạng thái JIT/heap của một lần chạy. JMH gọi những lượt như vậy là forks.

Một số liệu từ một process sau một lần warmup có thể bị lệch. Nên quan sát kết quả từ **nhiều fork, nhiều measurement iterations** và độ biến thiên. Mục tiêu là kết luận có bằng chứng, không phải chọn run đẹp nhất.

## 5. JMH: công cụ phù hợp để microbenchmark Java

**JMH (Java Microbenchmark Harness)** là công cụ được thiết kế cho việc benchmark các đoạn mã JVM nhỏ. Nó cung cấp mô hình benchmark method, warmup, measurement, forks, mode đo và cơ chế hạn chế một số lỗi tối ưu hóa thường gặp.

JMH không tự biến một benchmark sai thành đúng: nếu hai benchmark xử lý dữ liệu khác nhau, chọn input không đại diện hoặc dùng trạng thái chia sẻ không an toàn, kết quả vẫn không có ý nghĩa.

### 5.1. Mẫu JMH minh họa

Đoạn sau **không thuộc JDK chuẩn**. Nó cần dự án đã khai báo thư viện JMH phù hợp và cấu hình annotation processing/build tương ứng. Đây là mẫu để hiểu cách cấu trúc phép đo, không phải code chạy trực tiếp chỉ bằng javac không có dependency.

~~~java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 10)
@Fork(3)
public class SumBenchmarks {
    @Param({"1000", "100000", "1000000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = IntStream.rangeClosed(1, size).toArray();
    }

    @Benchmark
    public long loop() {
        long sum = 0;
        for (int value : values) {
            if ((value & 1) == 0) {
                sum += (long) value * value;
            }
        }
        return sum;
    }

    @Benchmark
    public long primitiveStream() {
        return Arrays.stream(values)
            .filter(v -> (v & 1) == 0)
            .mapToLong(v -> (long) v * v)
            .sum();
    }

    @Benchmark
    public long boxedStream() {
        return Arrays.stream(values).boxed()
            .filter(v -> (v & 1) == 0)
            .mapToLong(v -> (long) v * v)
            .sum();
    }
}
~~~

Cách đọc:

- **@State(Scope.Thread)**: mỗi thread benchmark có state của riêng nó, tránh dùng chung mảng mutable giữa thread benchmark.
- **@Param**: chạy nhiều kích thước dữ liệu, vì kết luận trên n=1000 có thể không đúng với n=1.000.000.
- **@Setup(Level.Trial)**: tạo dữ liệu trước phần đo, không trộn chi phí tạo mảng vào mỗi lời gọi nếu mục tiêu là **chi phí xử lý mảng đã tồn tại**.
- **@Benchmark**: mỗi phương thức biểu diễn một biến thể của cùng phép tính.
- **@Warmup / @Measurement**: tách lượt làm nóng khỏi lượt thu số liệu.
- **@Fork(3)**: chạy trong nhiều process JVM độc lập.
- **AverageTime**: đo thời gian trung bình cho một operation theo cấu hình JMH.
- **Return long**: cho JMH quan sát kết quả của benchmark, giúp tránh việc toàn bộ phép tính bị loại bỏ chỉ vì không dùng return value.

Cần kiểm tra kết quả các biến thể **bằng nhau bằng unit test** ngoài benchmark; JMH không tự so hai phép tính về mặt nghiệp vụ.

### 5.2. Chọn phạm vi setup phù hợp

Nếu production nhận một mảng đã tồn tại và chỉ tính tổng, tách **tạo mảng** ra ngoài thời gian đo là hợp lý.

Nếu yêu cầu production là **đọc file, parse, lọc, map rồi ghi kết quả**, benchmark chỉ map một mảng in-memory là quá hẹp để đánh giá cả pipeline. Khi đó cần một **end-to-end benchmark** bao gồm I/O, parsing, allocation và downstream side effects ở các ranh giới phù hợp.

Hãy nêu rõ câu hỏi:

- “Chi phí **xử lý** một mảng đã tạo là bao nhiêu?” → setup ngoài đo.
- “Chi phí **tạo và xử lý** một batch mới là bao nhiêu?” → có thể đo cả allocation/setup trong một workload riêng.
- “Độ trễ request thật dưới tải là bao nhiêu?” → dùng load testing / profiling ứng dụng, không chỉ microbenchmark JMH.

### 5.3. Blackhole và dead-code elimination

Một phép tính mà kết quả không được dùng có thể bị JIT loại bỏ hoặc rút gọn. JMH cung cấp **Blackhole** để tiêu thụ kết quả cần quan sát khi không trả trực tiếp:

~~~java
@Benchmark
public void benchmark(Blackhole blackhole) {
    long result = compute();
    blackhole.consume(result);
}
~~~

Đây là fragment minh họa trong một lớp JMH với import tương ứng, không phải chương trình JDK thuần. Phương thức **compute()** do ứng dụng định nghĩa.

Không đặt System.out.println trong benchmark method: I/O ghi console có chi phí lớn và nhiễu, làm kết quả không còn phản ánh thuật toán.

### 5.4. Khi nào trả về kết quả là đủ?

Với @Benchmark trả long, JMH có cơ chế sử dụng kết quả để hạn chế tối ưu loại bỏ toàn bộ công việc. Nếu nhiều kết quả, có thể dùng Blackhole hoặc một kết quả tổng hợp có nghĩa. Nhưng **không nên cố đánh lừa JIT bằng một biến global mutable** vì điều đó làm phép đo khác code cần tối ưu.

### 5.5. Hạn chế của JMH

JMH tốt cho microbenchmarks nhưng **không tự dự đoán** latency production. Production còn có:

- Concurrent users, network, DB và storage.
- GC pressure từ nhiều thành phần khác.
- CPU quotas/container limits.
- Task scheduling và thread contention.
- Dữ liệu thực, exception và cache miss.
- Connection pools, transaction boundaries và retry.

Hãy dùng JMH để hiểu một đoạn mã cụ thể, sau đó xác nhận bằng profiling/load test trên hệ thống gần thực tế.

## 6. Những lỗi benchmark rất dễ mắc

### 6.1. Đo hai cách không cùng công việc

Không thể so collector tạo đầy đủ List với count chỉ trả một số rồi bảo count nhanh hơn “mọi trường hợp”. Hai API trả **kết quả khác nhau**, nên câu hỏi phải phù hợp.

### 6.2. Quên kết quả, bị tối ưu mất

~~~java
long start = System.nanoTime();
computeSomething();
long end = System.nanoTime();
~~~

Nếu computeSomething thuần và kết quả bỏ đi, compiler/JIT có thể loại bỏ hoặc đơn giản hóa công việc. Dùng JMH và một kết quả quan sát được.

### 6.3. Thực hiện setup trong một biến thể nhưng không ở biến thể khác

Một bên gọi new Random(), tạo List, boxing và copy; bên kia dùng mảng có sẵn. Nếu muốn đo thuật toán xử lý dữ liệu đã chuẩn bị, **không được trộn các chi phí này không cân xứng**.

### 6.4. Dùng input hằng quá đơn giản

Một bộ số có thể khiến JIT đặc biệt tối ưu hoặc cache nóng bất thường. Dùng nhiều kích thước, phân bố và pattern có ý nghĩa; cân nhắc dữ liệu ngẫu nhiên tạo trước, seed được ghi lại để có thể tái lập.

### 6.5. Bỏ qua allocation

Hai biến thể có thời gian tương tự nhưng một bên tạo nhiều boxed objects, List tạm hoặc String mới; dưới tải lớn, GC có thể làm biến thể đó chậm rõ. Có thể dùng JMH GC profiler, JFR hoặc allocation profiler phù hợp để quan sát.

### 6.6. Chỉ chọn số đẹp nhất

Giá trị thấp nhất trong một loạt chạy có thể phản ánh điều kiện đặc biệt tốt, không đại diện cho hệ thống. Nên báo cáo mô hình biến thiên từ nhiều iterations/forks và diễn giải mức độ tin cậy.

### 6.7. Cùng JVM nhưng workload chạy thứ tự cố định

Luôn benchmark A rồi B có thể khiến B hưởng trạng thái JIT, cache hoặc CPU nhiệt khác A. Harness có thể điều phối tốt hơn; vẫn cần nhiều phép đo độc lập và cân nhắc hiệu ứng thứ tự.

### 6.8. Dùng parallel stream với shared mutable state

Nếu một biến thể tăng chung AtomicInteger hoặc sửa ArrayList từ nhiều thread, nó vừa khác semantics vừa có contention. Không xem đây là benchmark so sánh công bằng với reduction thuần.

### 6.9. Bỏ qua warmup hoặc đo cold start sai mục tiêu

Microbenchmark tập trung steady-state khác bài đo startup. Hãy thiết kế hai bài đo riêng khi hệ thống cần cả hai.

### 6.10. Tắt GC hoặc đổi heap tùy tiện để có số tốt

Cấu hình JVM ảnh hưởng kết quả. Nếu điều chỉnh heap/GC, phải ghi lại và giải thích vì sao phản ánh deployment. Không dùng kết quả một cấu hình để khẳng định mọi môi trường.

## 7. Stream và for loop: cách chọn trong ứng dụng

**Stream** thường diễn đạt tốt một pipeline gồm các phép biến đổi, lọc và thu kết quả. **For loop** thường phù hợp với thuật toán mệnh lệnh, trạng thái tuần tự nhỏ, short-circuit phức tạp, hoặc đường xử lý cực nóng mà đo đạc cho thấy overhead đáng kể.

| Nhu cầu | Lựa chọn thường dễ hiểu | Lưu ý |
| --- | --- | --- |
| Lọc rồi đổi object | filter().map().toList() | Callback nên stateless/non-interfering |
| Cộng số int/long | IntStream/LongStream.sum() | Tránh boxing và kiểm tra overflow |
| Đếm phần tử hợp lệ | filter(...).count() | Không dùng AtomicInteger làm holder nếu chỉ để đếm |
| Tìm một phần tử đầu | filter(...).findFirst() | Có thể short-circuit |
| Tìm bất kỳ phần tử | findAny() | Có thể khác findFirst trong parallel |
| Nhóm theo khóa | collect(groupingBy(...)) | Chú ý memory/Map type |
| Tạo Map từ record | toMap hoặc groupingBy | Xử lý duplicate key rõ |
| Nhiều nhánh imperative | for/while | Rõ biến trạng thái, break/continue |
| Đường cực nóng, vòng lặp đơn giản | for hoặc primitive stream | Benchmark trên workload thật |
| Tính toán CPU lớn độc lập | parallel stream hoặc executor | Đo overhead, thread safety |
| I/O blocking | API async/executor phù hợp | Parallel stream không mặc định phù hợp |

**Khả năng bảo trì là một tiêu chí thật.** Một pipeline dùng năm nested lambdas, ba collector lồng nhau và side effect có thể khó đọc hơn một vòng lặp 15 dòng. Ngược lại, một vòng lặp với bốn collection tạm có thể rõ hơn khi được viết thành filter/map/collect.

### 7.1. Đừng dùng Stream chỉ vì muốn code ngắn

~~~java
List<String> normalized = names.stream()
    .filter(s -> !s.isBlank())
    .map(String::trim)
    .map(String::toLowerCase)
    .toList();
~~~

Đoạn trên minh họa cách mô tả pipeline. Nhưng trong trường hợp locale-sensitive, String.toLowerCase() mặc định dựa trên locale môi trường: nếu kết quả cần xác định, chọn một Locale rõ ràng theo nghiệp vụ.

Nếu yêu cầu là kiểm tra chuỗi rỗng **sau khi trim**, phải thay đổi thứ tự các bước. **Tính đúng của pipeline quan trọng hơn việc cú pháp nhìn gọn.**

## 8. Primitive streams và boxing: ưu tiên khi dữ liệu là số

Các Stream primitive **IntStream, LongStream, DoubleStream** cho phép xử lý số không phải đóng gói mọi phần tử thành wrapper object trong nhiều trường hợp.

~~~java
long sum = Arrays.stream(data)
    .filter(n -> n > 0)
    .mapToLong(n -> (long) n * n)
    .sum();
~~~

So với:

~~~java
long sum = Arrays.stream(data).boxed()
    .filter(n -> n > 0)
    .mapToLong(n -> (long) n * n)
    .sum();
~~~

Bản boxed có thể thêm overhead do Integer wrapper và conversion. Nhưng JVM có thể tối ưu một phần, nên **không tuyên bố tỷ lệ nhanh/chậm cố định**. Hãy đo trên dữ liệu, JDK và pipeline thật.

### 8.1. mapToInt, mapToLong và giới hạn kiểu

Nếu bình phương int có thể tràn, viết:

~~~java
.mapToLong(n -> (long) n * n)
~~~

chứ không:

~~~java
.mapToLong(n -> n * n)
~~~

Ở bản thứ hai phép nhân **int xảy ra trước** khi được chuyển sang long. Một benchmark có thể chạy rất nhanh nhưng cho kết quả sai nếu quên nguyên tắc này.

### 8.2. Khi bắt buộc dùng boxed object

Nhiều API generic, Optional<T> hoặc collector cần object. Boxing khi cần là hợp lý. Chỉ tránh boxing **không cần thiết** trong vòng lặp nóng, đặc biệt khi primitive stream đã có terminal operation tương ứng.

## 9. Chọn giữa collect, reduce và vòng lặp

### 9.1. Reduce cho phép gộp theo một phép toán hợp lệ

~~~java
long total = numbers.stream()
    .mapToLong(Integer::longValue)
    .sum();
~~~

Nếu có phép tổng hợp tùy chỉnh, reduce thích hợp khi có **identity**, toán tử **associative** và, với reduce ba đối số, accumulator/combiner **compatible**.

Không dùng mutable ArrayList hoặc StringBuilder làm identity rồi sửa chung trong parallel reduce. Với xây dựng container mutable, **collect** thường phù hợp hơn.

### 9.2. Collect cho kết quả cấu trúc

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

Đây là fragment với record Employee giả định. Nếu chỉ cần số lượng phần tử, count() rõ hơn. Nếu cần **map đếm theo nhóm**, groupingBy/counting mới là đúng bài toán. So sánh hai API này chỉ có ý nghĩa nếu mục tiêu đầu ra tương đương.

### 9.3. Không tối ưu hóa chỉ để bỏ for loop

Một vòng lặp thuần trên mảng có thể rất nhanh và dễ đọc. Nhưng trong pipeline chuyển đổi object, Stream có thể làm rõ các bước nghiệp vụ. Kết luận phải xét:

- Đường xử lý có nằm ở hot path không?
- Dữ liệu có đủ lớn để overhead khác biệt có ý nghĩa không?
- Có nhiều allocation do boxing/collector không?
- Có cần giữ order, duplicate, null, exception semantics không?
- Số đo có lặp lại trong điều kiện gần production không?
- Đổi API có làm giảm khả năng bảo trì không?

## 10. Parallel stream: phải có đủ điều kiện mới đáng dùng

Parallel stream có thể chia một pipeline thành các task chạy trên nhiều core. Nhưng nó **không tự bảo đảm giảm thời gian**.

Các điều kiện thuận lợi:

1. Nguồn đủ lớn và **dễ split**, như array hoặc dải chỉ số.
2. Công việc cho từng phần tử **đủ nặng** để bù overhead scheduling/merge.
3. Lambda **stateless**, không sửa nguồn hoặc mutable state ngoài.
4. Phép tổng hợp có **identity/associativity/compatibility** phù hợp.
5. Có tài nguyên CPU thực tế, không bị giới hạn nặng bởi container quota.
6. Không chạy trong một hệ thống vốn đã bão hòa thread/CPU.
7. Benchmark cho thấy lợi ích **trên workload thật**, không chỉ một máy phát triển.

Những trường hợp cần tránh hoặc rất thận trọng:

- Dữ liệu chỉ vài trăm phần tử với phép toán rẻ.
- I/O blocking mà không có thiết kế concurrency riêng.
- Ordered stateful pipeline như sorted/limit hoặc forEachOrdered có chi phí điều phối.
- Một bộ đếm AtomicInteger chung trong callback gây contention.
- Shared mutable structures hoặc nguồn Spliterator khó chia.
- Request server cùng sử dụng tài nguyên CPU và thread pool.

### 10.1. Parallel không làm tổng CPU work giảm

Giả sử một phép tính cần tổng cộng 100 ms CPU. Chạy song song có thể rút elapsed time khi có nhiều core rảnh, nhưng overhead chia/gom và cache coherence có thể làm tổng CPU time **cao hơn**. Nếu server đang chịu nhiều request, thêm parallelism có thể làm giảm throughput toàn hệ thống.

### 10.2. Kiểm tra tính đúng song song trước

Tính tổng có thể đúng nếu phép reduction hợp lệ. Nhưng:

~~~java
List<Integer> output = new ArrayList<>();

numbers.parallelStream()
    .forEach(output::add);
~~~

Đây là **đoạn minh họa lỗi**: ArrayList không được thiết kế cho nhiều thread cùng add không đồng bộ. Có thể gây race hoặc dữ liệu hỏng.

Thay bằng:

~~~java
List<Integer> output = numbers.parallelStream()
    .toList();
~~~

Stream.toList trên Java 17 trả List **không thể chỉnh sửa**, đồng thời hoạt động theo hợp đồng Stream về kết quả/encounter order tương ứng. Nếu cần ArrayList mutable, dùng một collector hoặc tạo bản sao phù hợp sau khi thu thập.

### 10.3. Kiểm tra nhiều kích thước

Một benchmark cần chạy nhiều cỡ n. Với n nhỏ, sequential có thể thắng do overhead. Với n lớn và phép tính đủ nặng, parallel có thể thắng. **Không có một ngưỡng kích thước chung cho mọi API hoặc máy.**

## 11. Statefulness, short-circuit và chi phí bộ nhớ

Một số intermediate operations như filter/map có thể được kết hợp để xử lý từng phần tử, tránh tạo List trung gian.

Ngược lại:

- **sorted()** có thể cần buffer và chi phí sắp xếp.
- **distinct()** có thể cần trạng thái để nhớ phần tử đã thấy.
- **collect(groupingBy)** cần xây dựng Map và các container con.
- **toList()** cần lưu kết quả hữu hạn đã thu.
- **limit/findFirst/anyMatch** có thể dừng sớm theo hợp đồng và tình huống.
- **count()** đôi khi có thể tối ưu mà không gọi mọi callback nếu kích thước được biết.

### 11.1. Benchmark phải tính đúng semantics của lazy evaluation

Ví dụ sai nếu cố “đo map” chỉ bằng việc xây pipeline:

~~~java
long start = System.nanoTime();
Stream<Integer> pipeline = Stream.of(1, 2, 3)
    .map(x -> x * x);
long elapsed = System.nanoTime() - start;
~~~

Ở đây chưa có terminal operation; benchmark chủ yếu đo **chi phí dựng pipeline**, không đo việc bình phương từng phần tử.

Muốn đo xử lý:

~~~java
List<Integer> result = Stream.of(1, 2, 3)
    .map(x -> x * x)
    .toList();
~~~

Nhưng phải quyết định có tính cả chi phí tạo nguồn và List kết quả vào phạm vi benchmark hay không, rồi giữ tiêu chí đó nhất quán giữa các biến thể.

### 11.2. Không đếm số callback làm kết quả nghiệp vụ

~~~java
AtomicInteger sideCount = new AtomicInteger();

long result = List.of(1, 2, 3).stream()
    .map(n -> {
        sideCount.incrementAndGet();
        return n * 2;
    })
    .count();
~~~

JVM có thể biết kích thước nguồn và bỏ qua mapper vì nó không ảnh hưởng count. Do đó **sideCount không phải công cụ tính đúng số phần tử đã xử lý**. Nếu cần count, dùng terminal count; nếu cần benchmark map, đo một kết quả có sử dụng giá trị map thật sự.

## 12. Dữ liệu benchmark phải đại diện

Input size chỉ là một chiều. Cần xét thêm:

- **Phân bố dữ liệu:** phần lớn phần tử pass filter hay chỉ một phần nhỏ?
- **Tỷ lệ trùng:** ảnh hưởng distinct, groupingBy, Map hashing.
- **Key cardinality:** số nhóm nhiều hay ít? Phân bố có lệch?
- **Thứ tự đầu vào:** đã sorted hay ngẫu nhiên?
- **Độ dài chuỗi/object:** ảnh hưởng parsing, map, allocation.
- **Cache locality:** array liên tiếp khác List object phân tán.
- **Null / exceptions:** cần có input thực tế, nhưng không vô tình biến exception thành phần việc chỉ xuất hiện ở một biến thể.
- **Bộ nhớ đủ không:** batch lớn có thể gây paging hoặc OOM.
- **Nguồn I/O:** dữ liệu ở RAM, page cache hay disk/network?
- **Environment concurrency:** có nhiều request đồng thời, background GC hay pool dùng chung?

Một benchmark trên List 10 phần tử không dự đoán chắc chắn hiệu năng groupingBy của một triệu bản ghi với hàng chục nghìn key.

### 12.1. Nên dùng seed cố định để lặp lại

Nếu tạo input giả ngẫu nhiên, cố định seed và tạo dữ liệu **ngoài phần đo** khi mục tiêu không bao gồm chi phí sinh dữ liệu. Nếu muốn đo cả sinh dữ liệu, tạo một benchmark riêng.

Đừng tạo new Random() rồi nextInt() trong một biến thể nhưng đối thủ xử lý dữ liệu có sẵn — đó là so hai công việc khác nhau.

## 13. Chương trình Java 17+ tự chạy: correctness trước, timing chỉ tham khảo

Chương trình sau cố ý phân biệt:

- **Stdout xác định**: kiểm tra cùng kết quả, số phần tử chẵn, tổng, grouping, List không thể chỉnh sửa và sink quan sát được.
- **Stderr không xác định**: một số kết quả nanoTime của các lần chạy thử. Chúng chỉ dạy cách đọc elapsed time, **không phải phép benchmark chuẩn để xếp hạng API**.

Tạo file **ApiChoiceBenchmarkDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.LongSupplier;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ApiChoiceBenchmarkDemo {
    private static volatile long observed;

    record Sale(String region, int amount) {}

    static long byLoop(int[] data) {
        long sum = 0;
        for (int n : data) {
            if ((n & 1) == 0) {
                sum += (long) n * n;
            }
        }
        return sum;
    }

    static long byIntStream(int[] data) {
        return Arrays.stream(data)
            .filter(n -> (n & 1) == 0)
            .mapToLong(n -> (long) n * n)
            .sum();
    }

    static long byBoxedStream(int[] data) {
        return Arrays.stream(data).boxed()
            .filter(n -> (n & 1) == 0)
            .mapToLong(n -> (long) n * n)
            .sum();
    }

    static long byParallelStream(int[] data) {
        return Arrays.stream(data).parallel()
            .filter(n -> (n & 1) == 0)
            .mapToLong(n -> (long) n * n)
            .sum();
    }

    static void roughProbe(String label, LongSupplier task) {
        for (int i = 0; i < 30; i++) {
            observed = task.getAsLong();
        }
        long best = Long.MAX_VALUE;
        for (int i = 0; i < 8; i++) {
            long start = System.nanoTime();
            long result = task.getAsLong();
            long elapsed = System.nanoTime() - start;
            observed = result;
            best = Math.min(best, elapsed);
        }
        System.err.println(label + ": demo_best_ns=" + best);
    }

    public static void main(String[] args) {
        int[] data = IntStream.rangeClosed(1, 200_000).toArray();

        long loop = byLoop(data);
        long primitive = byIntStream(data);
        long boxed = byBoxedStream(data);
        long parallel = byParallelStream(data);

        System.out.println("sameResult=" +
            (loop == primitive && loop == boxed && loop == parallel));
        System.out.println("evenCount=" + Arrays.stream(data)
            .filter(n -> (n & 1) == 0).count());
        System.out.println("sum=" + loop);

        List<Sale> sales = List.of(
            new Sale("North", 10),
            new Sale("South", 25),
            new Sale("North", 15)
        );
        Map<String, Long> counts = sales.stream().collect(
            Collectors.groupingBy(Sale::region, TreeMap::new,
                Collectors.counting()));
        System.out.println("counts=" + counts);

        List<String> labels = sales.stream()
            .map(Sale::region).distinct().sorted().toList();
        System.out.println("labels=" + labels);
        try {
            labels.add("East");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable=true");
        }

        roughProbe("loop", () -> byLoop(data));
        roughProbe("primitive", () -> byIntStream(data));
        roughProbe("boxed", () -> byBoxedStream(data));
        roughProbe("parallel", () -> byParallelStream(data));

        System.out.println("observedMatches=" + (observed == loop));
    }
}
~~~

Biên dịch và chạy trên **JDK 17 trở lên**:

~~~bash
javac ApiChoiceBenchmarkDemo.java
java ApiChoiceBenchmarkDemo
~~~

**Stdout xác định đã kiểm chứng:**

~~~text
sameResult=true
evenCount=100000
sum=1333353333400000
counts={North=2, South=1}
labels=[North, South]
unmodifiable=true
observedMatches=true
~~~

**Stderr có thời gian thay đổi theo máy và lượt chạy**, ví dụ hình dạng:

~~~text
loop: demo_best_ns=<giá trị đo được>
primitive: demo_best_ns=<giá trị đo được>
boxed: demo_best_ns=<giá trị đo được>
parallel: demo_best_ns=<giá trị đo được>
~~~

Bốn dòng trên là **minh họa định dạng**, không phải stdout/stderr cố định cần đối chiếu nguyên văn. **Không sử dụng các giá trị timing của roughProbe để tuyên bố API nào tốt hơn.** Hàm này chỉ làm một ít warmup và chọn thời gian nhỏ nhất, không có forks, thống kê phân bố, GC profiling hay cấu hình JMH đáng tin.

### 13.1. Phân tích stdout

**sameResult=true:** cả bốn biến thể cho tổng bằng nhau với dãy 1..200.000.

**evenCount=100000:** trong 200.000 số nguyên dương liên tiếp có đúng 100.000 số chẵn.

**sum=1333353333400000:** tổng bình phương các số chẵn từ 2 đến 200.000. Tất cả phép tính bình phương được nâng lên long trước khi nhân, tránh tràn int.

**counts:** ba Sale được nhóm theo region; North có hai, South có một. TreeMap::new giúp thứ tự in của khóa có thể dự đoán.

**labels:** distinct kết hợp sorted tạo danh sách hai tên khu vực theo thứ tự tự nhiên.

**unmodifiable=true:** Stream.toList trên Java 17 trả List không thể chỉnh sửa, nên thao tác add ném UnsupportedOperationException.

**observedMatches=true:** kết quả của các phép gọi qua roughProbe đã được lưu/quan sát, giúp tránh một số trường hợp code chạy vô ích, nhưng **không làm phép đo thủ công trở thành microbenchmark chuẩn**.

### 13.2. Vì sao không báo một con số thời gian chính xác?

System.nanoTime() phụ thuộc thời gian thực thi của máy, JDK/JIT, CPU, GC, scheduling và điều kiện môi trường. Vì vậy ghi một stdout như “primitive luôn nhanh 120.000 ns” là **bịa một tính chất không tồn tại**. Bài này chỉ ghi phần output xác định và mô tả định dạng thời gian một cách minh bạch.

### 13.3. Có cần giữ volatile observed?

Biến volatile được dùng như một sink minh họa cho giá trị return trong roughProbe. Nó tạo ra một chi phí và ảnh hưởng tối ưu nhất định, nên cũng là lý do **không nên diễn giải giá trị roughProbe như benchmark production**. Với JMH, nên trả kết quả hoặc dùng Blackhole theo thiết kế harness thay vì tự dựng một global sink.

## 14. Tổng hợp tiêu chí chọn API

| Tình huống | API nên cân nhắc đầu tiên | Điều cần kiểm tra |
| --- | --- | --- |
| Lọc và ánh xạ theo pipeline | Stream.filter/map/toList | Stateless, thứ tự, null, allocation |
| Tính tổng số primitive | IntStream/LongStream.sum | Overflow, tránh boxing |
| Đếm số phần tử | Stream.count | Không dùng side effect counter |
| Tìm phần tử theo điều kiện | findFirst/findAny | Encounter order, Optional, short-circuit |
| Tìm min/max | min/max với Comparator | Tie-break, null, không sorted thừa |
| Kiểm tra tồn tại | anyMatch/allMatch/noneMatch | Short-circuit, hàm thuần |
| Chuyển List thành Map | Collectors.toMap | Duplicate key, merge, null |
| Nhóm dữ liệu | groupingBy/partitioningBy | Bộ nhớ, kiểu value, phân bố khóa |
| Tổng hợp giá trị | reduce hoặc primitive sum | Identity, associativity, compatibility |
| Xây dựng mutable container | collect hoặc collector có sẵn | Supplier, combiner, mutable state |
| Tạo chuỗi nối nhiều phần | Collectors.joining | Separator, prefix/suffix, allocation |
| Tính nhiều thống kê | summarizingInt/teeing | Kiểu kết quả, overflow |
| Vòng lặp stateful có break/continue | for/while | Đọc dễ hơn pipeline nhiều nhánh |
| Xử lý CPU nặng, độc lập | parallel stream | Split, CPU core, overhead, correctness |
| Xử lý I/O hoặc async | API I/O, executor, async phù hợp | Close, blocking, cancellation |
| Đường hot path ngắn | for hoặc primitive stream | JMH trước khi tối ưu |
| Hệ thống có p99 latency quan trọng | Đo end-to-end | Không chỉ nhìn microbenchmark |

Bảng là **điểm khởi đầu**, không phải mệnh lệnh phải dùng duy nhất một API. Chọn theo ngữ nghĩa, khả năng bảo trì, dữ liệu và số đo thực tế.

## 15. Cách viết một báo cáo benchmark đáng tin

Một báo cáo tối thiểu nên có:

**Câu hỏi:** “Trong cùng JVM/JDK, với một mảng int đã được tạo, cách nào tính tổng bình phương số chẵn hiệu quả nhất theo time/op và allocation?”

**Workload:** Kích thước 1.000, 100.000 và 1.000.000; mô tả phân bố dữ liệu; cùng kiểu return long; cùng phép lọc.

**Correctness:** Các biến thể cho tổng bằng nhau, test input rỗng, số âm/cận và overflow policy.

**Môi trường:** JDK version/build, CPU, core/threads, OS, heap, GC, container quota nếu có.

**Method:** JMH mode, warmup iterations, measurement iterations, forks và thread count; công bố các JVM flags khác mặc định.

**Results:** Time/op hoặc throughput theo từng kích thước, độ biến thiên, allocation/GC nếu liên quan; không chỉ copy kết quả một lượt.

**Interpretation:** Chênh lệch có đáng kể và nhất quán không? Có phụ thuộc kích thước? Có đổi được code production mà không làm khác semantics? Hiệu năng tổng thể có được xác nhận bằng workload gần thật không?

**Decision:** Chọn API vì lý do cụ thể, nêu trade-off và hoàn cảnh cần đo lại.

### 15.1. Không che kết quả trái dự đoán

Nếu vòng lặp nhanh hơn stream trên một kích thước, không kết luận Stream API kém trong mọi tình huống. Nếu parallel nhanh hơn trong batch một triệu phần tử, không kết luận nó phù hợp server đang có nhiều request đồng thời.

Hãy nhìn **điều kiện hình thành kết quả**, không chỉ thứ hạng trên bảng.

### 15.2. Đo lại khi môi trường thay đổi

Một quyết định có thể cần xem lại khi cập nhật:

- JDK version hoặc GC.
- CPU/core count, container limits.
- Kích thước hoặc phân bố dữ liệu.
- Thread concurrency của service.
- Pipeline mới có thêm sorted/distinct/collect.
- Heap, target latency hoặc yêu cầu memory.
- Cách gọi code trong ứng dụng.

Compiler/JIT và runtime có thể cải thiện theo thời gian, nên không nên “đóng băng” kết luận benchmark từ một JDK cũ cho tất cả phiên bản.

## 16. Những lỗi chọn API phổ biến

**Lỗi 1 — tối ưu trước khi đo.** Viết code phức tạp chỉ vì tưởng một API nhanh hơn. Nên bắt đầu bằng code đúng và rõ, đo sau khi xác định bottleneck.

**Lỗi 2 — benchmark không trả kết quả.** JIT có thể loại bỏ công việc; dùng JMH return value hoặc Blackhole.

**Lỗi 3 — đo dựng pipeline nhưng nói đã đo xử lý phần tử.** Intermediate Stream operations lazy, cần terminal phù hợp với mục tiêu.

**Lỗi 4 — so hai cách trả dữ liệu khác nhau.** Đừng lấy count làm đối thủ của toList nếu một bên cần full List.

**Lỗi 5 — quên boxing.** Stream<Integer> có thể có overhead khác IntStream; đo hai phiên bản đúng semantics.

**Lỗi 6 — để phép nhân int overflow rồi mới cast.** Có thể benchmark rất nhanh nhưng kết quả sai; cast trước khi nhân.

**Lỗi 7 — đo không warmup.** Lần đầu bị ảnh hưởng class loading/JIT và không đại diện steady-state.

**Lỗi 8 — chỉ đo một JVM.** Cần forks và nhiều iterations khi muốn đưa ra quyết định microbenchmark.

**Lỗi 9 — chỉ đo nanoseconds, quên allocation/GC.** Chi phí tạo object có thể ảnh hưởng performance khi tăng tải.

**Lỗi 10 — dùng cùng một mảng nhỏ duy nhất.** Phải kiểm tra nhiều kích thước và phân bố input.

**Lỗi 11 — parallel bất kể workload.** Với phép tính quá rẻ và input nhỏ, overhead có thể lớn hơn lợi ích.

**Lỗi 12 — shared mutable state trong parallel stream.** Có thể gây race hoặc contention; sử dụng collector/reduction phù hợp.

**Lỗi 13 — nghĩ atomic counter là đo số callback chính xác.** Stream có thể tối ưu/short-circuit; side effect không nên là metric nghiệp vụ.

**Lỗi 14 — dựa vào HashMap iteration order trong test.** Chọn Map có thứ tự hoặc so sánh theo nội dung Map, không theo output không được cam kết.

**Lỗi 15 — bỏ qua đặc tính output collection.** Stream.toList không thể chỉnh sửa; nếu downstream cần mutable List, phải thiết kế cho đúng.

**Lỗi 16 — chỉ nhìn average, không nhìn p99.** Server latency có thể bị GC/scheduling dù microbenchmark average tốt.

**Lỗi 17 — đưa I/O vào một bên nhưng không bên kia.** Phải đo cùng phạm vi end-to-end hoặc tách chi phí rõ ràng.

**Lỗi 18 — nhầm JMH với load test.** Microbenchmark một method không đủ để kết luận hệ thống nhiều người dùng nhanh hơn.

**Lỗi 19 — suy từ tên API ra tốc độ.** “Parallel” không đồng nghĩa nhanh; “functional” không đồng nghĩa chậm; “imperative” không đồng nghĩa tối ưu.

**Lỗi 20 — tối ưu làm thay đổi hợp đồng nghiệp vụ.** Đổi forEachOrdered sang forEach có thể phá thứ tự side effect; đổi findFirst sang findAny có thể đổi kết quả; đổi Map sang Set có thể mất duplicate.

## 17. Checklist áp dụng vào code review

- Có **benchmark question** được định nghĩa rõ không?
- Những biến thể có **cùng semantics** và xử lý ngoại lệ như nhau không?
- Có kiểm tra kết quả trước khi đo không?
- Dữ liệu đại diện cho workload thật hay chỉ là vài giá trị tiện tay?
- Có phân biệt setup với measured region không?
- Có đủ warmup, forks và measurement iterations không?
- Kết quả có được tiêu thụ để tránh dead-code elimination không?
- Có ghi phiên bản JDK/JVM flags và cấu hình máy không?
- Có quan sát allocation/GC khi cần không?
- Có xét throughput và p99 thay vì chỉ average không?
- Pipeline có boxing, sorted, distinct hay collect nặng không?
- Có shared mutable state hoặc tranh chấp atomic counter không?
- Parallel có đủ việc và đủ CPU core không?
- API được chọn có dễ test và dễ đọc hơn không?
- Có cần đo lại trong production-like workload không?

## 18. Câu hỏi tự kiểm tra

1. Vì sao một lần System.nanoTime không đủ để kết luận Stream nhanh hơn for loop?
2. Warmup và JIT compilation ảnh hưởng phép đo ra sao?
3. Fork trong JMH có ích gì?
4. Dead-code elimination và constant folding có thể làm benchmark sai thế nào?
5. Vì sao benchmark method nên trả kết quả hoặc dùng Blackhole?
6. Khi nào cần tính cả setup vào phép đo?
7. Primitive IntStream khác boxed Stream<Integer> ở những loại overhead nào?
8. Vì sao một phép tính bình phương phải cast sang long trước phép nhân?
9. Thế nào là so sánh hai API có cùng semantics?
10. Vì sao count và toList không phải hai lựa chọn có thể so sánh trực tiếp trong mọi bài?
11. Parallel stream có thể giảm elapsed time nhưng tăng tổng CPU work như thế nào?
12. Khi nào for loop rõ ràng hơn pipeline Stream?
13. Vì sao một shared ArrayList trong parallel forEach là nguy hiểm?
14. Phân biệt latency trung bình, throughput và p99 latency.
15. Khi dữ liệu có nhiều key trùng, performance groupingBy có thể khác thế nào?
16. Vì sao không dùng side effect trong map/peek để kiểm tra số lần xử lý?
17. System.nanoTime và JMH khác nhau về mức bảo đảm thống kê nào?
18. Một benchmark rất nhanh nhưng làm sai thứ tự kết quả có thể được chấp nhận không?
19. Khi nâng cấp JDK hoặc thay đổi phân bố dữ liệu, có cần đo lại không?
20. Những thông tin nào bắt buộc phải có trong báo cáo hiệu năng để người khác tái hiện?

**Kết luận:** Chọn API Java Functional Programming theo **độ đúng, độ rõ, chi phí tài nguyên và số đo có thể lặp lại**, không theo cảm giác về từ khóa Stream hay parallel. Đối với microbenchmark, dùng **JMH với nhiều kích thước, warmup, forks và kết quả được sử dụng thật**, đồng thời kiểm tra allocation/GC khi cần. Với hệ thống thực, xác nhận thêm bằng profiling và load test. Stream, primitive stream, reduce, collect và for loop đều là những công cụ hợp lệ; API phù hợp là API giải quyết đúng bài toán với **mức độ phức tạp thấp nhất và hiệu năng đã được chứng minh đủ tốt**.