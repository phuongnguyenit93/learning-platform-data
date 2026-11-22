# Warming up JVM, JIT và tránh microbenchmark sai

## 1. Vì sao một phép đo Java concurrency có thể sai ngay từ đầu?

Cùng một đoạn Java, thời gian thực thi lúc ứng dụng vừa khởi động có thể khác đáng kể lúc hệ thống đã hoạt động một thời gian. Nếu chỉ lấy thời gian một vòng lặp bằng `System.nanoTime()`, ta rất dễ kết luận nhầm rằng phiên bản mã A nhanh hơn B, một API concurrent nhanh hơn API khác, hoặc số thread càng lớn thì càng tốt.

**Warm-up** là quá trình chạy trước một workload để những hoạt động khởi tạo và tối ưu hóa có cơ hội diễn ra trước khi đo trạng thái mong muốn. **JIT (Just-In-Time compilation)** là một trong nhiều nguyên nhân khiến hiệu năng thay đổi theo thời gian: JVM có thể bắt đầu bằng giải thích bytecode, thu thập hồ sơ thực thi rồi biên dịch những đoạn nóng thành mã máy tối ưu.

Tuy nhiên, warm-up **không phải phép thuật làm số đo đúng**. Nó không loại bỏ sai lệch do optimizer xóa mã, CPU đổi xung nhịp, GC, lịch chạy thread, tranh chấp tài nguyên, dữ liệu không đại diện hoặc dùng benchmark sai công cụ. Với bài toán concurrency, chi phí điều phối và tranh chấp giữa các thread càng khiến kết quả dễ nhiễu.

Bài này tập trung vào **Java SE / JVM nói chung** và đo hiệu năng concurrent code, không nói về các abstraction framework ứng dụng.

### Phân biệt ba câu hỏi hiệu năng

| Câu hỏi | Đo thứ gì? | Warm-up thích hợp? |
| --- | --- | --- |
| Startup/cold path | Từ lúc process bắt đầu đến khi sẵn sàng phục vụ; request hoặc tác vụ đầu tiên | Không được loại bỏ cold-start; đó chính là đối tượng đo |
| Steady-state throughput | Số công việc hoàn thành mỗi giây khi hệ thống đã vận hành | Thường cần warm-up đủ, quan sát điểm ổn định |
| Steady-state latency | Thời gian hoàn thành một thao tác/request khi hệ thống đã hoạt động | Cần warm-up phù hợp; phân biệt latency từng thao tác với overhead của harness |

Nếu nhiệm vụ thực tế cần tối ưu thời gian khởi động, warm-up rồi bỏ tất cả lượt đầu sẽ **che giấu** chi phí cần quan tâm. Ngược lại, nếu muốn so sánh throughput lúc ổn định, trộn khởi động với chạy nóng sẽ làm lệch kết quả.

## 2. Điều gì diễn ra khi Java code nóng dần?

Các chi tiết sau mô tả **HotSpot JVM** thường gặp ở OpenJDK, không phải ràng buộc bắt buộc của mọi Java Virtual Machine.

### 2.1 Class loading, initialization và khởi tạo hệ sinh thái

Ở những lần đầu sử dụng một class, JVM có thể phải nạp, liên kết, khởi tạo class, thực hiện static initializer, thiết lập các cấu trúc liên quan và tạo các đối tượng/phương thức cần thiết. Chương trình cũng có thể chưa tạo xong worker thread, executor, bộ đệm, kết nối hay các cấu trúc dữ liệu.

Vì thế, một lần gọi có thể gánh chi phí setup chỉ phát sinh một lần hoặc thỉnh thoảng mới xuất hiện. Cần quyết định rõ chi phí setup ấy có nằm trong phạm vi đo hay không. Chẳng hạn, đo chi phí **khởi tạo ExecutorService** là bài toán khác với đo chi phí **thực thi task trên executor đã có**.

### 2.2 Interpreter, profiling, tiered compilation

Một đường đi điển hình trong HotSpot có thể là:

```text
Bytecode
   |
   v
Interpreter (quan sát cách code chạy)
   |
   +----> C1 compiler: biên dịch nhanh, có thể thu thập profiling
   |
   +----> C2 compiler: tối ưu sâu hơn cho đoạn nóng
   |
   v
Machine code đang được dùng trong JVM
```

Đây là sơ đồ khái niệm, **không phải thứ tự cứng** mà mọi method luôn phải đi qua đầy đủ. HotSpot thường bật *tiered compilation*, lựa chọn cấp biên dịch theo số lượt gọi, số lượt lặp, hồ sơ nhánh, loại đối tượng và nhiều yếu tố khác. JVM có thể biên dịch một đoạn đang chạy lâu bằng **OSR (On-Stack Replacement)**, không cần đợi method kết thúc rồi mới áp dụng mã đã biên dịch.

Những tối ưu có thể xảy ra:

- **Inlining:** thay lời gọi method bằng thân method khi hợp lý, mở đường cho tối ưu tiếp theo.
- **Constant folding/propagation:** tính trước biểu thức có giá trị biết chắc.
- **Dead-code elimination:** bỏ phép tính không ảnh hưởng kết quả quan sát được.
- **Loop optimizations:** tối ưu vòng lặp, loại phép tính thừa, thay đổi cách chạy.
- **Escape analysis và scalar replacement:** với điều kiện phù hợp, bỏ một số allocation hoặc tách object thành những giá trị vô hướng.
- **Speculative optimization:** dựa trên kiểu đối tượng/hành vi đã quan sát; nếu giả định không còn đúng, JVM có thể **deoptimize**, quay lại đường thực thi khác và biên dịch lại.

Do đó, "đã chạy 1.000 lần" **không chứng minh JIT đã tối ưu xong**. Một method ít được gọi, work khác dữ liệu, thread khác hoặc profile thay đổi có thể vẫn cần biên dịch/deoptimize.

### 2.3 Warm-up không chỉ là JIT

Sau một thời gian chạy, nhiều yếu tố ngoài JIT cũng đổi trạng thái:

- CPU data/instruction cache và branch predictor đã "học" workload.
- Heap, allocation path, TLAB, GC generation/cycle có trạng thái khác.
- Thread và thread pool đã khởi tạo; một số thread đã vượt qua chi phí lần đầu.
- JDK/libraries có cache lazy, cấu trúc nội bộ, resource initialization.
- CPU tự đổi tần số, turbo/thermal state theo tải và nhiệt.
- OS scheduling thay đổi theo các process khác và mức bận CPU.

**Hệ quả:** thấy các vòng sau nhanh hơn vòng đầu **không đủ bằng chứng** rằng riêng JIT tạo ra toàn bộ khác biệt. Nên dùng công cụ quan sát và nhiều lần chạy có kiểm soát để giải thích nguyên nhân.

## 3. Ví dụ quan sát warm-up với Java 17+

Đây là **thí nghiệm minh họa**, không phải benchmark đáng tin để công bố tỷ lệ tăng tốc. Chương trình tính một hàm có đầu vào thay đổi, lưu kết quả vào `volatile` để tạo điểm quan sát rồi in thời gian mỗi vòng.

Lưu thành `WarmupObservation.java`:

```java
public class WarmupObservation {
    private static volatile long visibleResult;

    static long work(int seed) {
        long x = seed;
        for (int i = 0; i < 1000; i++) {
            x = x * 1664525L + 1013904223L;
        }
        return x;
    }

    public static void main(String[] args) {
        for (int round = 1; round <= 5; round++) {
            long start = System.nanoTime();
            long sum = 0;
            for (int i = 0; i < 20_000; i++) {
                sum ^= work(i + round);
            }
            visibleResult = sum;
            long elapsed = System.nanoTime() - start;
            System.out.println(
                    "round=" + round
                    + ", result=" + visibleResult
                    + ", elapsedNs=" + elapsed);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 WarmupObservation.java
java WarmupObservation
```

Một lần chạy sẽ in **năm dòng**, mỗi dòng có `round=...`, `result=...` và `elapsedNs=...`. `result` được tính bằng phép toán Java xác định; **`elapsedNs` luôn phụ thuộc máy và lần chạy**, vì vậy không cung cấp "output thời gian chuẩn". Mã trên đã được biên dịch theo `--release 17` và chạy thành công bằng JDK 24.

### Đọc đúng kết quả

1. Những vòng đầu **có thể** chậm hơn vì JIT, nạp class và nhiều hiệu ứng khởi tạo, nhưng không bảo đảm độ trễ giảm đều qua từng vòng.
2. `volatile visibleResult` tạo điểm quan sát sau mỗi vòng; nó không thay thế thiết kế benchmark đúng. Chi phí ghi volatile vẫn nằm trong vùng timing.
3. `System.nanoTime()` là đồng hồ dùng đo **khoảng thời gian trôi qua**, không phải CPU time của một thread và không tự loại bỏ scheduling, GC, JIT hay OS noise.
4. Vòng `round` bao gồm cả code của harness, lời gọi method và thao tác cộng/XOR. Không thể xem `elapsedNs / 20_000` là thời gian nguyên chất của `work` khi chưa biết optimizer đã biến đổi code ra sao.
5. Việc chạy thí nghiệm vài lần và nhìn thấy những con số khác nhau là **lý do để dùng một harness chuyên dụng**, không phải bằng chứng rằng JIT bị lỗi.

Để thử quan sát biên dịch HotSpot khi chạy ví dụ:

```shell
java -XX:+PrintCompilation WarmupObservation
```

JVM có thể in nhiều dòng biên dịch cho cả thư viện JDK. Output thay đổi theo phiên bản HotSpot, trạng thái CPU và lần chạy; các dòng in không phải thang điểm hiệu năng. Trên những JDK hỗ trợ, có thể bật log GC trong một phép đo chẩn đoán riêng bằng `-Xlog:gc`; phần log cũng gây thêm overhead nên không mặc định đem so trực tiếp với lượt không logging.

## 4. Vì sao microbenchmark bằng nanoTime thường sai?

**Microbenchmark** đo một thao tác nhỏ (nanosecond, microsecond hoặc millisecond). Thao tác càng ngắn, lỗi thiết kế càng dễ áp đảo tín hiệu thực.

### 4.1 Dead-code elimination

```java
long start = System.nanoTime();
long sum = 0;
for (int i = 0; i < 1000; i++) {
    sum += i;
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

Đoạn trên là **minh họa anti-pattern**. Biến `sum` không được dùng, nên compiler có thể bỏ toàn bộ phần tính toán hoặc biến đổi vòng lặp. Bạn tưởng đo 1.000 phép cộng nhưng có thể chỉ đo clock calls và phần vỏ khác.

**Sửa nguyên tắc:** bảo đảm kết quả của phép tính thực sự được quan sát. Trong JMH, một benchmark có thể **return kết quả**, hoặc dùng `Blackhole.consume(...)` khi phải tiêu thụ nhiều kết quả. Nhưng chỉ "in kết quả ra console" bên trong phép đo lại làm I/O áp đảo thao tác cần đo.

### 4.2 Constant folding và đầu vào không đại diện

```java
// Anti-pattern khi đo một phép tính cực nhỏ:
int value = 40 + 2;
```

Compiler có thể biết ngay kết quả 42. Kể cả khi thay bằng lời gọi hàm, sau inlining JIT vẫn có thể nhận diện các input bất biến và tối ưu mạnh hơn so với workload thực tế.

**Sửa nguyên tắc:** dùng tập input đại diện được chuẩn bị trước, có biến thiên thích hợp, đặt trạng thái ở `@State` của JMH và tiêu thụ kết quả. Nhưng không nên tạo random input hoặc đọc file ngay trong vùng timing nếu đó không phải phần công việc muốn đo.

### 4.3 Thao tác quá ngắn, đo vài lần, chia sai đơn vị

```java
long t0 = System.nanoTime();
int x = 2 * 3;
long ns = System.nanoTime() - t0;
```

Đoạn trên không thể tách chi phí phép nhân khỏi độ phân giải hữu hiệu/overhead của đồng hồ và compiler. Đơn vị nanosecond không có nghĩa là đồng hồ đo chính xác mọi nanosecond.

Tăng số vòng lặp thủ công đôi khi giúp giảm overhead tương đối, nhưng tạo thêm nguy cơ JIT tối ưu **cả vòng lặp** theo cách không giống một lời gọi độc lập. Harness cần điều khiển số phép lặp và đảm bảo observable result.

### 4.4 Chỉ warm-up một cấu hình, rồi đo cấu hình khác

Nếu luôn đo A trước rồi B sau trong cùng JVM, B có thể được lợi vì cache, JIT hoặc trạng thái CPU đã nóng hơn. Ngược lại B có thể bị ảnh hưởng bởi heap/GC hoặc nhiệt độ. Không được kết luận B nhanh hơn chỉ vì được chạy sau.

**Sửa nguyên tắc:** nhiều **fork JVM độc lập**, nhiều lần đo và so sánh phân phối kết quả. Giữ cùng JDK, flags, hardware, heap, input, chế độ power và môi trường tải. Đổi thứ tự đánh giá giữa các lần thử/chuỗi thử nếu so sánh hệ thống có nhiều nhiễu.

### 4.5 Đếm thời gian tạo dữ liệu và setup nhầm vào thao tác chính

```java
// Không phù hợp nếu mục tiêu chỉ là chi phí tìm kiếm:
long t0 = System.nanoTime();
var data = new java.util.ArrayList<Integer>();
for (int i = 0; i < 100_000; i++) data.add(i);
boolean found = data.contains(99_999);
long elapsed = System.nanoTime() - t0;
```

Phép đo gồm cả allocation, boxing, xây list và tìm kiếm. **Nếu mục tiêu là cả quy trình**, cách đo đó có thể hợp lệ; **nếu mục tiêu chỉ là `contains`**, hãy chuẩn bị dữ liệu trước vùng đo.

### 4.6 Nhầm throughput, latency và speedup

- **Throughput:** `ops/s` lớn hơn thường là tốt hơn, nếu mỗi operation có cùng nghĩa.
- **Average time:** `ns/op`, `µs/op` nhỏ hơn thường là tốt hơn, nếu benchmark mode và đơn vị tương thích.
- **Latency tail (p95/p99):** cần thiết khi yêu cầu về độ trễ; average không tự mô tả phần đuôi phân phối.
- **Speedup:** chỉ có ý nghĩa khi workload, điều kiện máy, kích thước dữ liệu và mục tiêu đo tương đương; với concurrency, so sánh tổng ops/s ở 1 và 4 thread còn phụ thuộc số core, contention và mức bão hòa.

Không lấy trung bình "tỷ lệ tăng tốc" của những lượt không tương thích, cũng không báo hiệu năng với độ chính xác chữ số thập phân vượt dữ liệu và độ biến thiên thực.

## 5. Sử dụng JMH để đo microbenchmark đúng cách hơn

**JMH (Java Microbenchmark Harness)** do OpenJDK phát triển giúp điều phối warm-up, measurement, fork JVM, kết quả trả về/Blackhole, các mode throughput và thời gian, cùng cấu hình số thread. JMH **giảm nhiều lỗi phổ biến**, nhưng không thay thế việc thiết kế workload và diễn giải đúng.

### 5.1 Tạo dự án benchmark độc lập

Cần JDK và Maven có thể truy cập dependency từ Maven Central. Trong **thư mục trống không nằm trong một Maven project khác**, chạy:

```shell
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.example -DartifactId=jvm-bench -Dversion=1.0-SNAPSHOT
```

Lệnh trên dùng archetype của OpenJDK JMH để tạo cấu hình Maven gồm các bước **annotation processing** cần thiết. Chỉ thêm dependency `jmh-core` mà không chạy generator chưa đủ để có bộ benchmark JMH hoạt động đúng.

### 5.2 Benchmark JIT với input thay đổi và output quan sát được

Đặt file `jvm-bench/src/main/java/org/example/JitWarmupBenchmark.java`:

```java
package org.example;

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

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class JitWarmupBenchmark {
    private long input = 1;

    @Benchmark
    public long mix() {
        long x = input++;
        for (int i = 0; i < 100; i++) {
            x = x * 1664525L + 1013904223L;
        }
        return x;
    }
}
```

Lệnh build và chạy:

```shell
cd jvm-bench
mvn clean verify
java -jar target/benchmarks.jar JitWarmupBenchmark
```

Giải thích từng phần:

- `@Benchmark` đánh dấu phương thức cần đo. Nó chạy trong harness sinh tự động.
- `@State(Scope.Thread)` tạo state riêng cho từng benchmark thread. `input++` thay đổi giữa các lần gọi, giảm nguy cơ đo nhầm một phép tính hằng. Đây vẫn là **một phần của thao tác đo**, vì vậy phải hiểu nó khi kết luận về `mix`.
- `return x` khiến kết quả được JMH tiêu thụ bằng cơ chế phù hợp, hạn chế việc phép tính bị loại bỏ vì không có kết quả quan sát được. Với nhiều output, JMH còn hỗ trợ `Blackhole.consume`.
- `@Warmup(iterations = 5, time = 1)`: năm vòng warm-up, mỗi vòng khoảng một giây. Kết quả những vòng đó không được đưa vào điểm số đo cuối.
- `@Measurement(iterations = 5, time = 1)`: năm vòng đo sau warm-up trong mỗi fork.
- `@Fork(2)`: chạy ở hai JVM con độc lập để giảm phụ thuộc vào trạng thái một process JVM duy nhất.
- `Mode.AverageTime` và `TimeUnit.NANOSECONDS`: kết quả báo thời gian trung bình trên operation theo `ns/op`.

**Không có giá trị ns/op cố định** để so với máy của bạn: JMH phải chạy thực tế trên môi trường đích và kết quả phụ thuộc CPU, JVM và nhiễu. Các tham số warm-up/fork trên là điểm xuất phát cho thí nghiệm, **không phải bảo đảm** workload đã ổn định. Hãy đọc tiến trình từng iteration, tăng warm-up hoặc đổi cách đo nếu còn xu hướng hoặc phương sai lớn.

### 5.3 JMH có Blackhole để làm gì?

Giả sử benchmark tính hai kết quả:

```java
@Benchmark
public void twoResults(Blackhole blackhole) {
    blackhole.consume(calculate(inputA));
    blackhole.consume(calculate(inputB));
}
```

Đây là **đoạn minh họa bên trong lớp JMH**, không phải Java file độc lập: cần import `org.openjdk.jmh.infra.Blackhole`, hai input và hàm `calculate`. `Blackhole` giúp làm kết quả có thể quan sát được mà không dùng console I/O. Nếu phép tính chỉ trả về **một kết quả**, thường chỉ cần `return` giá trị từ method `@Benchmark`; không nhất thiết phải thêm Blackhole cho mọi method.

Tuy nhiên, Blackhole cũng **không thể tự sửa** việc setup sai, chỉ đo cùng một input vô nghĩa hay benchmark thiếu tương đồng với thực tế.

## 6. JMH khi đo concurrency: thread count và state quyết định kết luận

Khi một phép tính chạy trên nhiều thread, cần phân biệt **năng lực CPU**, **chi phí đồng bộ**, **contention** và **tổng throughput**. Hai điểm cốt lõi của JMH:

- `@Threads(n)` hoặc tùy chọn CLI `-t n` điều khiển số benchmark worker threads.
- `@State(Scope.Thread)` cho mỗi thread có state riêng; `@State(Scope.Benchmark)` tạo state chung cho nhiều worker của cùng benchmark, phù hợp khi cần đo **tranh chấp thực sự**.

Ví dụ sau đo throughput của một `AtomicLong` **được chia sẻ** giữa các benchmark threads:

Tạo thêm `jvm-bench/src/main/java/org/example/SharedCounterBenchmark.java`:

```java
package org.example;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class SharedCounterBenchmark {
    private final AtomicLong counter = new AtomicLong();

    @Benchmark
    public long incrementShared() {
        return counter.incrementAndGet();
    }
}
```

Build lại khi thêm file, rồi đo hai cấu hình riêng:

```shell
mvn clean verify
java -jar target/benchmarks.jar SharedCounterBenchmark -t 1
java -jar target/benchmarks.jar SharedCounterBenchmark -t 4
```

Vì `@State(Scope.Benchmark)`, các worker thực hiện `incrementShared` trên **cùng một AtomicLong** trong mỗi lần chạy. Với nhiều thread, thao tác atomic có thể tranh chấp cùng cache line. Kết quả `ops/s` là **tổng throughput** của workload được định nghĩa, không phải throughput trên từng thread.

Không mặc định rằng `-t 4` sẽ tăng gấp bốn; máy có thể thiếu core, bottleneck tại CAS/cache coherence, xung nhịp thay đổi hoặc bị OS scheduling. Nếu đổi `Scope.Benchmark` thành `Scope.Thread` thì bạn đang đo bài toán **mỗi thread có counter riêng**, khác hẳn bài toán tranh chấp. Không được đem hai số đó so như cùng một workload.

### Những bẫy đặc thù concurrency

1. **Đo mỗi một worker rồi kết luận cho nhiều worker:** không tái hiện contention, lock convoy hoặc cache-line bouncing.
2. **Tạo thread trong mỗi invocation dù chỉ muốn đo thao tác đồng bộ:** kết quả trở thành thời gian tạo thread/submit/đồng bộ cả quy trình.
3. **Đo thời gian `executor.submit` nhưng không chờ task hoàn tất:** chỉ đo enqueue/dispatch, không đo công việc.
4. **Dùng `Thread.sleep` để "đợi tác vụ xong":** dễ chờ thiếu hoặc thừa; muốn đo end-to-end phải dùng `Future.get`, `CountDownLatch`, `Phaser` hay cơ chế hoàn thành đáng tin.
5. **Đọc shared counter không an toàn:** code có data race có thể sai cả kết quả lẫn ý nghĩa đo; phải dùng đồng bộ/atomic phù hợp hợp đồng.
6. **Trộn logging, println hoặc I/O ngoài ý muốn vào critical section:** kết quả bị chi phối bởi thiết bị, bộ đệm và lock phụ.
7. **Đo `synchronized` không có tranh chấp rồi suy rộng thành ứng dụng nhiều thread:** đường uncontended và đường contended khác về hành vi.
8. **Dùng quá nhiều worker so với số core và coi đó là cải thiện của thuật toán:** cần giải thích workload là CPU-bound hay blocking/I/O-bound.

Với pipeline producer/consumer, queue và backpressure, **JMH microbenchmark chỉ trả lời một phần**. Đo thêm throughput end-to-end, độ sâu queue, số task đang chờ, p95/p99 latency, allocation/GC, CPU utilization và tỷ lệ lỗi ở load test đại diện.

## 7. Thiết kế thí nghiệm đo đạc có kiểm soát

Một quy trình thực dụng cho Java concurrency:

1. **Viết rõ giả thuyết:** ví dụ "thay synchronized counter bằng AtomicLong làm tăng throughput ở bốn thread" hoặc "warm pool giảm latency task đầu". Không bắt đầu từ việc chạy timer rồi mới suy đoán mình đã đo gì.
2. **Chọn metric tương ứng:** throughput, average time, tail latency, CPU time, allocation rate, GC pause hoặc startup. Không đánh đồng giữa chúng.
3. **Giữ đúng workload:** dữ liệu đầu vào, tỷ lệ đọc/ghi, phân phối task duration, mức contention, số producer/consumer, kích thước queue và giới hạn tốc độ phải gần tình huống thật.
4. **Thiết kế setup rõ ràng:** khởi tạo dữ liệu và tài nguyên ngoài vùng đo nếu không phải mục tiêu; để trong vùng đo nếu đúng là thứ cần đánh giá.
5. **Phân biệt cold và warm:** nếu tối ưu cold-start, đo từ process mới; nếu tối ưu steady-state, warm-up nhưng kiểm tra hiện tượng ổn định. Ghi lại cấu hình HotSpot và JDK.
6. **Chạy đủ fork và iteration:** dùng JMH cho thao tác nhỏ, xem số đo giữa các fork/iteration và điều chỉnh thời lượng; tránh tin một lượt "đẹp".
7. **Kiểm tra kết quả chức năng:** output phải đúng, các task thực sự hoàn tất và không bị optimizer xóa công việc hoặc tác vụ âm thầm thất bại.
8. **Giảm nhiễu môi trường:** ổn định CPU governor/power plan khi có thể, hạn chế background jobs, ghi hardware/core/OS/JDK/flags/heap, tránh so điểm từ máy khác cấu hình.
9. **Kiểm tra nguyên nhân bằng profiler/telemetry:** nếu nghi JIT, xem compilation; nếu nghi GC, xem GC log/JFR; nếu nghi contention, xem thread dump/JFR/lock events. Instrumentation cũng có overhead: đo chẩn đoán riêng khi cần.
10. **Báo cáo cùng bất định:** mô tả số fork, warm-up, measurement, threads, error/độ phân tán, dữ liệu và phiên bản. Lặp lại trước khi quyết định tối ưu.

### Bảng nhận định theo mẫu số liệu

| Quan sát | Kết luận được? | Việc cần kiểm tra |
| --- | --- | --- |
| Vòng đầu chậm hơn các vòng sau | Có thay đổi trạng thái runtime | Compilation, class initialization, cache, GC, CPU state |
| B nhanh hơn A một lần | Chưa đủ | Nhiều fork, variance, thứ tự chạy, cấu hình |
| Throughput tăng khi từ 1 lên 4 thread | Có thể scale trên workload đo đó | Core, contention, CPU, tổng ops/s và correctness |
| Latency trung bình tốt nhưng p99 xấu | Có tail latency đáng chú ý | Pauses, scheduling, contention, queue, GC |
| JMH score rất nhanh nhưng app không cải thiện | Benchmark thiếu tính đại diện | Dữ liệu thực, call path, I/O, lock, allocation và end-to-end |

## 8. Công cụ chẩn đoán và cách đọc số liệu

**JMH:** lựa chọn tốt để so sánh *microbenchmark* sau khi xác định đúng method/operation. Hỗ trợ fork, warm-up, measurement và thread count; nó không tự chứng minh việc benchmark đã đại diện cho service thực tế.

**JFR (Java Flight Recorder):** dùng khi cần quan sát allocation, GC, CPU, lock contention và nhiều sự kiện runtime trong ứng dụng gần thực tế. Ví dụ trên JDK hỗ trợ:

```shell
java -XX:StartFlightRecording=filename=recording.jfr,duration=60s -jar your-app.jar
```

Đây là **mẫu lệnh**, yêu cầu thay `your-app.jar` bằng JAR thực tế. Chạy có JFR sẽ phát sinh overhead nhất định; nên phân biệt profiling run và benchmark run.

**HotSpot compilation log:** `-XX:+PrintCompilation` giúp thấy phương thức nào được biên dịch, nhưng số dòng log không phải score. Để khảo sát chuyên sâu, có thể nghiên cứu JITWatch và công cụ của JVM đang dùng.

**GC log:** `-Xlog:gc` giúp xác định GC có đang xảy ra trong khoảng đo không. Không nên quy mọi "spike" cho GC nếu không có bằng chứng.

**Thread dump/CPU profiler:** giúp tìm BLOCKED, WAITING, lock ownership, contention, hot path và oversubscription. Với workload CPU-bound và synchronized/atomic, profiler và phép đo ở nhiều mức thread có thể có ý nghĩa hơn vài nanosecond riêng lẻ.

Một benchmark tốt cần **diễn giải được vì sao con số đổi**, chứ không chỉ chọn ra con số nhỏ nhất.

## 9. Những ngộ nhận cần loại bỏ

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| "Chạy 100 lần là JVM chắc chắn nóng" | Ngưỡng JIT, profile, class loading và GC phụ thuộc workload và phiên bản HotSpot |
| "Lần đo cuối luôn đáng tin nhất" | CPU throttling, GC, OS noise hoặc deoptimization có thể xảy ra bất kỳ lúc nào |
| "`nanoTime` đo chính xác thời gian một lệnh" | Nó đo elapsed time; overhead và optimizer có thể lớn hơn thao tác |
| "Đưa kết quả ra `volatile` là benchmark chuẩn" | Observable result cần thiết, nhưng không giải quyết hết tối ưu và nhiễu |
| "JMH luôn bảo đảm microbenchmark đúng" | JMH cung cấp harness; workload và thiết kế vẫn là trách nhiệm người đo |
| "Warm-up càng dài càng chính xác" | Warm-up phải đáp ứng trạng thái muốn đo, nhưng có chi phí và không loại mọi loại noise |
| "Nhiều thread nhất là nhanh nhất" | Scaling bị giới hạn bởi core, contention, memory bandwidth và scheduling |
| "Có `@Fork(2)` thì không cần nhìn variance" | Fork giảm phụ thuộc trạng thái process, vẫn phải đọc phân tán và sai số |
| "JIT luôn làm code nhanh hơn" | JIT thường tối ưu nhưng cũng tiêu thụ CPU/memory để biên dịch, có thể deoptimize |
| "Số `ns/op` thấp đồng nghĩa latency production thấp" | Production còn có mạng, queueing, GC, locks, downstream và dữ liệu khác |

## 10. Tự kiểm tra kiến thức

**Q1. Warm-up là gì?** Là chạy workload trước vùng đo nhằm đưa runtime tới trạng thái liên quan mục tiêu đo. Không nên bỏ giai đoạn startup nếu startup chính là đối tượng nghiên cứu.

**Q2. Chạy nhiều lần có bảo đảm HotSpot đạt trạng thái ổn định?** Không. Phải quan sát kết quả iteration, môi trường và khi cần cả compilation/GC.

**Q3. Vì sao có thể đo "0 ns" cho vòng lặp?** Compiler có thể loại phép tính không quan sát được, hằng hóa hoặc tối ưu vòng lặp; đồng hồ/timer overhead cũng làm phép đo đơn lẻ vô nghĩa.

**Q4. `@State(Scope.Thread)` và `@State(Scope.Benchmark)` khác nhau gì?** Một bên có state riêng cho mỗi worker, bên kia cho các workers chia sẻ state; sự khác nhau làm thay đổi cơ chế contention.

**Q5. `@Warmup` có được tính vào JMH score cuối không?** Không; nó chạy trước các iteration đo. Tuy vậy JIT/deoptimization và GC vẫn có thể xảy ra trong measurement.

**Q6. `@Fork` giải quyết vấn đề gì?** Chạy thêm JVM độc lập để giảm việc dùng chung trạng thái đã được tối ưu/khởi tạo của một JVM; không tạo môi trường phần cứng tuyệt đối giống nhau.

**Q7. Vì sao đo thời gian `submit()` chưa đo xong một task?** `submit` thường chỉ nhận/gửi task và trả `Future`, task có thể còn ở hàng đợi hoặc đang chạy. Cần đo cả đến khi hoàn tất nếu mục tiêu là end-to-end latency.

**Q8. Khi nào dùng JMH và khi nào cần load test?** JMH phù hợp thao tác nhỏ, chi phí API/hàm hoặc mẫu contention có kiểm soát; load test phù hợp end-to-end latency/throughput/queue/backpressure trên workload thực.

## 11. Checklist trước khi tin số đo

- [ ] Mục tiêu đo được định nghĩa: cold-start, steady-state, throughput hay latency.
- [ ] Java/JDK/HotSpot flags, CPU, core, OS, heap và workload được ghi lại.
- [ ] Output của thao tác được quan sát, không bị loại mã hoặc thay đổi semantics.
- [ ] Setup, dữ liệu, allocation và I/O đặt đúng chỗ theo mục tiêu.
- [ ] Warm-up đủ và kiểm tra tính ổn định; không coi số vòng cố định là chân lý.
- [ ] Có nhiều iteration/fork và đánh giá variance, không chọn kết quả thuận lợi nhất.
- [ ] Concurrency đo đúng shared state, số threads, độ contention và task completion.
- [ ] Kết luận tách khỏi ảnh hưởng JIT, GC, cache, CPU, scheduling khi chưa có bằng chứng.
- [ ] So sánh A/B trên workloads và môi trường tương đương.
- [ ] Khi đưa vào production, kiểm tra lại bằng profile và load test end-to-end.

### Nguồn tham khảo chính thức

- [OpenJDK JMH — README, cách tạo dự án và chạy benchmark](https://github.com/openjdk/jmh)
- [OpenJDK JMH Samples — ví dụ tránh dead-code elimination bằng return/Blackhole](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java)
- [JDK 21 `java` launcher — `-XX:+PrintCompilation` và tiered compilation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [JDK 21 Java Flight Recorder API và hướng dẫn](https://docs.oracle.com/en/java/javase/21/jfapi/)