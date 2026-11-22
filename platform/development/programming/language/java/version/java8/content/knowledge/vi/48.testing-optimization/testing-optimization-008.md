# Đo sau warm-up và tránh kết quả bị JIT loại bỏ

## 1. Vì sao đo hiệu năng Java dễ sai?

Thời gian chạy của một đoạn Java có thể thay đổi trong vòng đời JVM. JVM thường bắt đầu bằng interpreter, thu thập profile, rồi biên dịch các đoạn code nóng sang machine code. JIT compiler có thể inline method, tối ưu nhánh/vòng lặp, tính trước biểu thức hằng và loại bỏ phép tính không ảnh hưởng đến hành vi có thể quan sát.

Vì vậy, một phép đo ngay sau khi khởi động có thể phản ánh **startup/interpreter cost**, trong khi một phép đo sau khi JVM đã tối ưu phản ánh **steady-state cost**. Hai con số trả lời hai câu hỏi khác nhau.

Ngoài JIT, kết quả còn bị ảnh hưởng bởi CPU frequency scaling, nhiệt độ/throttling, scheduler, thread contention, background processes, garbage collection, allocation, cache CPU, memory bandwidth, class loading, I/O và cách benchmark tạo input hoặc dùng kết quả.

Đề bài **“Đo sau warm-up và tránh kết quả bị JIT loại bỏ”** thuộc nhóm **Kiểm thử và tối ưu**. Mục tiêu là đo đúng workload, để JVM có đủ cơ hội tối ưu, đồng thời giữ phép tính cần đo có thể quan sát được.

Sau bài này, bạn có thể:

1. Phân biệt warm-up, measurement, startup và steady state.
2. Hiểu JIT profiling, compilation, inlining, deoptimization và tiered compilation.
3. Nhận diện dead-code elimination (DCE), constant folding, loop unrolling, loop hoisting và escape analysis.
4. Dùng return value hoặc JMH `Blackhole` để giữ kết quả.
5. Tạo input runtime thay vì chỉ đo biểu thức hằng.
6. Tránh loop tự viết làm sai chi phí trên mỗi operation.
7. Dùng JMH, Maven archetype, forks, warm-up và measurement iterations.
8. Chọn `@State`, `@Param`, `@Setup`, `@Warmup`, `@Measurement` và `@Fork`.
9. Đọc throughput, average time, sample time, allocation và GC metrics.
10. Ghi nhận môi trường và so sánh kết quả có thể lặp lại.

## 2. JVM thực thi và tối ưu code

JVM có thể thực thi bytecode qua interpreter, thu thập thông tin runtime, rồi biên dịch các method/loop nóng. Trên HotSpot, các compiler tiers thường được gọi là C1 và C2; JVM khác có thể dùng cơ chế khác.

```text
Khởi động JVM
     |
     v
Load class / initialize
     |
     v
Interpreter và compiler tier ban đầu
     |
     v
Thu thập profile: call count, branch, receiver types
     |
     v
Biên dịch code nóng sang machine code
     |
     v
Steady-state workload
     |
     +---- giả định không còn đúng ----> deoptimization
```

Một số tối ưu quan trọng:

- **Inlining:** đưa thân method được gọi thường xuyên vào caller để giảm call overhead và mở rộng cơ hội tối ưu.
- **Constant folding:** tính trước biểu thức có đầu vào hằng.
- **Dead-code elimination:** bỏ phép tính không ảnh hưởng kết quả có thể quan sát.
- **Loop unrolling:** mở rộng vòng lặp thành nhiều bản sao phép tính.
- **Loop hoisting:** đưa phép tính không đổi ra ngoài vòng lặp.
- **Escape analysis/scalar replacement:** có thể loại bỏ allocation hoặc thay object bằng các giá trị riêng khi object không thoát khỏi phạm vi được phân tích.
- **Deoptimization:** quay về code ít tối ưu hơn khi giả định của compiler bị phá vỡ.

Các tối ưu này là hành vi bình thường của JVM. Benchmark cần phản ánh code mà ứng dụng thực sự chạy sau tối ưu.

## 3. Warm-up và measurement

**Warm-up** là giai đoạn chạy workload trước khi thu thập score. JVM có thời gian load class, khởi tạo thư viện, thu thập profile và biên dịch code nóng.

Warm-up cần gần với workload measurement:

- Cùng code path và kiểu receiver.
- Cùng phân phối input và nhánh.
- Cùng kiểu dữ liệu và kích thước dữ liệu.
- Cùng concurrency/state model.
- Cùng JVM flags và runtime configuration.

Nếu warm-up chỉ đưa một kiểu object vào method nhưng measurement lại đưa nhiều kiểu khác nhau, profile có thể không đại diện; JIT có thể deoptimize hoặc biên dịch lại.

Không có quy tắc “5 lần là đủ” cho mọi benchmark. Một cấu hình khởi đầu thường dùng với JMH:

```java
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
```

Đây là cấu hình bắt đầu, không phải bảo đảm JVM đã đạt steady state. Hãy quan sát từng warm-up/measurement iteration và tăng thời lượng khi score còn biến động.

### 3.1. Warm-up khác cold start

| Mục tiêu | Cách đo |
| --- | --- |
| Hiệu năng ổn định sau JIT | Warm-up rồi measurement |
| Thời gian khởi động process | Đo cold start riêng |
| Chi phí lần gọi đầu tiên | Single-shot trong JVM mới |
| Chuyển trạng thái sau khi workload đổi | Đo transition và warm-up lại |
| Latency service dưới tải | Benchmark steady-state, sau đó load/integration test |

Không warm-up trước nếu câu hỏi thực sự là “process mới khởi động mất bao lâu?”. Warm-up sẽ loại bỏ chính phần startup cần đo. JMH có `Mode.SingleShotTime` cho các lần gọi đơn lẻ; khi nghiên cứu cold start, cần quản lý fork/process mới và trạng thái class loading/cache.

## 4. Dead-code elimination: kết quả bị bỏ có thể biến mất

Compiler chỉ cần giữ phép tính ảnh hưởng đến hành vi có thể quan sát. Nếu kết quả không được dùng và computation không tạo side effect cần thiết, JIT có thể xóa toàn bộ computation.

```java
static int expensive(int value) {
    int result = value;
    for (int i = 0; i < 100; i++) {
        result = result * 31 + i;
    }
    return result;
}

static void benchmarkLikeMethod() {
    expensive(42); // Kết quả bị bỏ đi
}
```

*Snippet minh họa, không phải benchmark đáng tin cậy.*

Nếu compiler inline method và chứng minh kết quả không được dùng, computation có thể bị loại bỏ. Benchmark khi đó có thể chỉ đo method wrapper.

**Quy tắc:** kết quả của computation phải được sử dụng theo cách benchmark harness có thể quan sát.

### 4.1. Return value là cách đơn giản nhất

JMH tự tiêu thụ kết quả của benchmark method trả về một giá trị:

```java
@Benchmark
public int compute() {
    return expensive(input);
}
```

*Snippet minh họa; `input` và `expensive` thuộc benchmark state/class.*

JMH dùng cơ chế nội bộ dựa trên Blackhole để giữ kết quả. Không cần tự tạo biến static chỉ để giữ một giá trị.

### 4.2. Dùng Blackhole khi có nhiều kết quả

Nếu benchmark cần giữ nhiều kết quả riêng biệt, dùng `org.openjdk.jmh.infra.Blackhole`:

```java
@Benchmark
public void compareTwoValues(Blackhole blackhole) {
    blackhole.consume(computeA());
    blackhole.consume(computeB());
}
```

*Snippet minh họa; `computeA` và `computeB` phải được định nghĩa.*

Nếu chỉ có một kết quả, return value thường gọn hơn. Không thêm Blackhole vào mọi method một cách máy móc vì thao tác consume cũng có chi phí.

### 4.3. Vì sao không dùng volatile sink cho mọi benchmark?

```java
static volatile int sink;

@Benchmark
public void measure() {
    sink = expensive(input);
}
```

*Snippet minh họa anti-pattern.*

Phép ghi volatile là hành vi có thể quan sát, nhưng nó có chi phí memory ordering/cache coherence. Nếu workload thật không ghi volatile, benchmark đã thêm thao tác ngoài mục tiêu đo. Chỉ đo volatile khi ứng dụng thực sự cần đo volatile access.

Không dùng `System.out.println` để giữ kết quả: I/O và đồng bộ console thường lớn hơn nhiều chi phí computation.

## 5. Constant folding: đầu vào hằng làm phép tính bị tính trước

Ngay cả khi kết quả được return, JIT vẫn có thể inline method và tính trước computation nếu input là hằng:

```java
@Benchmark
public int wrong() {
    return expensive(42);
}
```

Khi đó benchmark có thể đo việc trả hằng số thay vì thuật toán dự định.

Cách thiết kế phù hợp:

- Đưa input vào từ runtime state, không dùng literal cố định.
- Dùng `@Param` để chạy nhiều input.
- Dùng field không final trong object `@State` cho dữ liệu runtime.
- Chuẩn bị dữ liệu đại diện trong `@Setup`.
- Return hoặc consume kết quả.

Lưu `OptimizationPitfallsBenchmark.java`:

```java
package org.example;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class OptimizationPitfallsBenchmark {

    @Param({"17", "101"})
    public int input;

    private int work(int value) {
        int result = value;
        for (int i = 0; i < 32; i++) {
            result = result * 31 + i;
        }
        return result;
    }

    @Benchmark
    public void discardedResult() {
        work(input);
    }

    @Benchmark
    public int returnedResult() {
        return work(input);
    }

    @Benchmark
    public int constantInput() {
        return work(42);
    }
}
```

Ba method minh họa:

- `discardedResult` bỏ kết quả; JIT có thể loại bỏ computation.
- `returnedResult` trả kết quả từ runtime state; JMH tiêu thụ kết quả.
- `constantInput` dùng literal 42; computation có thể được constant-fold sau khi inline.

Đây là ví dụ để nhận diện benchmark sai, không dùng score của `discardedResult` hoặc `constantInput` để kết luận hiệu năng thuật toán.

## 6. Input phải giống workload thực tế

Input không chỉ cần “không phải hằng”; nó phải đại diện cho dữ liệu production.

Ví dụ benchmark parser:

- Đo chuỗi ngắn, trung bình và dài nếu production có cả ba.
- Có ASCII và Unicode nếu dữ liệu thật có cả hai.
- Có nhánh hợp lệ/không hợp lệ theo phân phối thực tế.
- Có empty/null nếu ứng dụng xử lý các trường hợp đó.
- Không chỉ dùng chuỗi nhỏ nếu production xử lý request/file lớn.

Dữ liệu mảng có thể chuẩn bị trong `@Setup(Level.Trial)`:

```java
@Setup(Level.Trial)
public void setup() {
    data = new byte[size];
    new Random(12345L).nextBytes(data);
}
```

*Snippet minh họa; `data` và `size` là field trong benchmark state. `Random` chỉ tạo dữ liệu test, không dùng cho mật mã.*

Không sinh random mới trong từng invocation nếu mục tiêu không phải đo random generation. Nếu input ảnh hưởng branch/cache behavior, hãy chọn nhiều bộ dữ liệu và phân phối phù hợp.

## 7. Loop optimization: đừng tự lặp để giảm overhead

Một benchmark thủ công thường viết:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    compute();
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

*Snippet minh họa cách đo đơn giản, không phải harness đáng tin cậy.*

Chia elapsed cho một triệu không tự cho ra chi phí một operation thực. JIT có thể unroll loop, pipeline phép tính, hoist computation, fold biểu thức hằng hoặc loại bỏ kết quả không quan sát.

Với JMH, hãy viết method mô tả **một logical operation**:

```java
@Benchmark
public int sumOnePair() {
    return left + right;
}
```

*Snippet minh họa; `left` và `right` thuộc state.*

JMH tự lặp invocation để thu thập mẫu; không cần thêm loop thủ công để giảm overhead harness.

### 7.1. Khi batch loop là workload thật

Nếu production xử lý một batch gồm 1.000 records trong một lần gọi, benchmark batch là hợp lý. Hãy đo đúng batch size, consume kết quả và báo cáo theo batch nếu đó là đơn vị nghiệp vụ.

`@OperationsPerInvocation(1000)` có thể chuẩn hóa score khi một invocation thực hiện chính xác 1.000 logical operations. Annotation chỉ điều chỉnh score; nó **không** ngăn JIT unroll, hoist hoặc tối ưu loop.

## 8. JMH và project Maven

**Java Microbenchmark Harness (JMH)** là framework của OpenJDK để viết, chạy và phân tích nano/micro/milli/macro benchmark trên JVM.

JMH cung cấp:

- Benchmark code generation qua annotation/bytecode processor.
- Warm-up và measurement iterations.
- Fork JVM độc lập.
- State injection, setup/teardown.
- Throughput, average time, sample time, single shot.
- Blackhole, parameters, profiler và output format.

Tại thời điểm cập nhật bài học, bản stable đã phát hành trên Maven Central là **JMH 1.37**. Nhánh phát triển upstream có thể chứa snapshot tiếp theo; dùng bản release khi xây project ổn định.

### 8.1. Tạo project bằng Maven archetype chính thức

JMH khuyến nghị tạo project Maven độc lập bằng archetype để có dependency và annotation processor cần thiết:

```bash
mvn archetype:generate \
  -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DarchetypeVersion=1.37 \
  -DgroupId=org.example \
  -DartifactId=jmh-benchmarks \
  -Dversion=1.0
```

Sau khi Maven tạo thư mục `jmh-benchmarks`, thêm benchmark classes vào source tree. Build và chạy:

```bash
cd jmh-benchmarks
mvn clean verify
java -jar target/benchmarks.jar
```

Chỉ thêm dependency `jmh-core` vào project thường chưa đủ: annotation processor phải sinh harness code. Với repository lớn, giữ benchmark trong module/project riêng và phụ thuộc vào code cần đo.

## 9. Benchmark class hoàn chỉnh với JMH

Lưu `DigestBenchmark.java` trong project JMH:

```java
package org.example;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Random;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
public class DigestBenchmark {

    @Param({"64", "4096", "65536"})
    public int size;

    private byte[] input;
    private MessageDigest digest;

    @Setup(Level.Trial)
    public void setup() throws NoSuchAlgorithmException {
        input = new byte[size];
        new Random(12345L).nextBytes(input);
        digest = MessageDigest.getInstance("SHA-256");
    }

    @Benchmark
    public byte[] sha256() {
        return digest.digest(input);
    }

    @Benchmark
    public void sha256WithBlackhole(Blackhole blackhole) {
        byte[] result = digest.digest(input);
        blackhole.consume(result);
        blackhole.consume(result.length);
    }
}
```

**Giải thích:**

- `@State(Scope.Thread)` tạo state riêng cho mỗi worker thread, tránh nhiều thread dùng chung một `MessageDigest`.
- `@Param` chạy cùng benchmark với nhiều kích thước input.
- `@Setup(Level.Trial)` chuẩn bị dữ liệu và digest một lần mỗi trial.
- `@BenchmarkMode(Mode.AverageTime)` đo thời gian trung bình mỗi invocation.
- `@OutputTimeUnit` trình bày score theo microseconds.
- `@Warmup` và `@Measurement` tách hai giai đoạn.
- `@Fork(3)` chạy ba JVM fork độc lập.
- `sha256` return byte array để JMH tiêu thụ kết quả.
- `sha256WithBlackhole` minh họa việc consume nhiều giá trị.

`MessageDigest.digest(byte[])` hoàn thành digest và reset object cho lần gọi tiếp theo. State riêng cho từng thread tránh race trên cùng instance.

Benchmark này đo SHA-256 trên mảng đã có; không đo chi phí tạo mảng, random input hay khởi tạo MessageDigest. Nếu production tạo digest mới cho mỗi request, viết benchmark riêng cho toàn flow.

## 10. Annotation và cấu hình benchmark

| Annotation | Ý nghĩa |
| --- | --- |
| `@Warmup` | Số warm-up iterations và thời gian mỗi iteration |
| `@Measurement` | Số measurement iterations và thời gian mỗi iteration |
| `@Fork` | Số JVM process độc lập |
| `@BenchmarkMode` | Throughput, average time, sample time, single shot |
| `@OutputTimeUnit` | Đơn vị hiển thị score |
| `@Threads` | Số benchmark worker threads |
| `@Param` | Danh sách input parameters |
| `@State` | Vòng đời/phạm vi chia sẻ state |
| `@Setup` / `@TearDown` | Chuẩn bị và giải phóng fixture |

5 warm-up iterations, 5 measurement iterations và 3 forks là điểm khởi đầu, không phải công thức cho mọi benchmark. Computation rất ngắn hoặc workload phức tạp có thể cần thời lượng khác.

Chạy với cấu hình rõ ràng:

```bash
java -jar target/benchmarks.jar \
  '.*DigestBenchmark.*' \
  -f 3 \
  -wi 5 \
  -i 5 \
  -w 1s \
  -r 1s \
  -t 1
```

- `-f 3`: ba forks.
- `-wi 5`: năm warm-up iterations.
- `-i 5`: năm measurement iterations.
- `-w 1s`: một giây mỗi warm-up iteration.
- `-r 1s`: một giây mỗi measurement iteration.
- `-t 1`: một benchmark thread.

Để quan sát allocation/GC:

```bash
java -jar target/benchmarks.jar '.*DigestBenchmark.*' -prof gc
```

Profiler phụ thuộc nền tảng và JDK. `-prof gc` cung cấp metrics liên quan đến allocation/GC; profiler hệ thống như perf chỉ chạy trên môi trường hỗ trợ.

### 10.1. Đọc bảng kết quả

```text
Benchmark                 (size)  Mode  Cnt   Score   Error  Units
DigestBenchmark.sha256        64  avgt   ...   ...     ...   us/op
DigestBenchmark.sha256      4096  avgt   ...   ...     ...   us/op
DigestBenchmark.sha256     65536  avgt   ...   ...     ...   us/op
```

Các dấu `...` là placeholder; số đo thực tế phụ thuộc CPU, JDK, OS, JVM flags và tải hệ thống.

- `Mode`: benchmark mode.
- `Cnt`: số lượng mẫu/iteration dùng trong kết quả.
- `Score`: score chính.
- `Error`: ước lượng sai số thống kê của score.
- `Units`: đơn vị như `us/op` hoặc `ops/s`.

Không chép số đo máy khác thành kỳ vọng cố định. Lưu kết quả cùng thông tin môi trường.

## 11. Benchmark modes

| Mode | Đo gì? | Khi nào dùng |
| --- | --- | --- |
| `Mode.Throughput` | Số operations mỗi đơn vị thời gian | Thông lượng |
| `Mode.AverageTime` | Thời gian trung bình mỗi operation | Chi phí trung bình |
| `Mode.SampleTime` | Lấy mẫu thời gian invocation và phân phối | Xem phân phối/percentile |
| `Mode.SingleShotTime` | Một invocation mỗi iteration | Cold path nếu thiết kế đúng |
| `Mode.All` | Các mode liên quan | Khám phá, tốn thời gian hơn |

Không so sánh trực tiếp `ops/s` với `ns/op` mà không quy đổi đơn vị và xác định cùng workload. SampleTime không thay thế load test để xác định tail latency toàn service dưới tải production.

## 12. State scope và benchmark nhiều thread

| Scope | Vòng đời/chia sẻ | Trường hợp dùng |
| --- | --- | --- |
| `Scope.Thread` | Một state cho mỗi worker | Parser/digest/buffer riêng từng thread |
| `Scope.Benchmark` | Một state chia sẻ giữa workers | Đo contention |
| `Scope.Group` | State chia sẻ trong thread group | Mô hình reader/writer |

Ví dụ:

```java
@State(Scope.Thread)
public class LocalState {
    int counter;
}
```

Mỗi worker có counter riêng. Với `Scope.Benchmark`, nhiều worker có thể truy cập cùng state; benchmark có thể đo contention/cache coherence.

Khi tăng thread count, xem xét lock/monitor contention, atomic/CAS retries, shared mutable state, false sharing, GC pressure và CPU oversubscription. Không dùng nhiều thread chỉ để “làm benchmark chạy nhanh hơn”; số thread làm thay đổi workload.

## 13. Setup và teardown

JMH có các fixture levels:

- `Level.Trial`: một lần cho toàn trial.
- `Level.Iteration`: trước/sau mỗi iteration.
- `Level.Invocation`: trước/sau mỗi invocation.

```java
@Setup(Level.Trial)
public void prepare() {
    // Tạo dữ liệu dùng lại trong trial
}

@TearDown(Level.Trial)
public void cleanup() {
    // Giải phóng resource của trial
}
```

Không dùng `@Setup(Level.Invocation)` để reset mọi state theo mặc định. Fixture mỗi invocation cần timestamping/synchronization và có thể làm lệch phép đo, đặc biệt với operation rất ngắn. Chỉ dùng khi workload cần state mới mỗi lần và đã hiểu overhead.

Ví dụ sort mảng: nếu chỉ tạo mảng ngẫu nhiên một lần trong `@Setup(Level.Trial)` rồi sort cùng mảng nhiều lần, lần đầu sort dữ liệu chưa sắp xếp, những lần sau sort dữ liệu đã sắp xếp. Benchmark đã đổi workload giữa trial.

Hãy xác định rõ copy/reset có thuộc workload production hay chỉ là setup. Nếu copy là công việc production, tính vào benchmark. Nếu cần input chưa mutate cho mỗi lần, thiết kế fixture hoặc batch data cẩn thận.

## 14. Escape analysis và allocation elimination

JIT có thể phân tích object có thoát khỏi method/region đang xét hay không. Nếu object không escape và điều kiện phù hợp, JVM có thể loại bỏ allocation hoặc thay object bằng scalar values.

```java
static int calculate() {
    Point point = new Point(10, 20);
    return point.x + point.y;
}
```

*Snippet giả định `Point` có hai field int.*

JIT có thể tối ưu việc tạo `Point` nếu object không thoát và chỉ các field được dùng. Vì vậy, nhìn thấy `new` trong source không chứng minh benchmark đang đo allocation.

Nếu production giữ object trong collection, trả object qua API hoặc truyền sang component khác, benchmark phải mô hình hóa hành vi escape đó. Nếu muốn đo allocation, kết hợp JMH với `-prof gc` và kiểm tra allocation rate. Không thêm volatile/global sink tùy tiện để ép JVM allocate vì sẽ thay đổi workload.

## 15. nanoTime và benchmark tự viết

`System.nanoTime()` phù hợp để đo elapsed time; nó dùng clock monotonic chứ không phải wall-clock timestamp. Nhưng timer tốt không tự biến một vòng lặp thành benchmark tốt.

Harness tự viết thường thiếu warm-up/measurement, fork độc lập, cơ chế giữ kết quả, kiểm soát input/state, nhiều lần chạy và phân tích biến động.

```java
long start = System.nanoTime();
int result = compute(input);
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

*Snippet minh họa, không phải microbenchmark đáng tin cậy.*

Nếu operation chỉ mất vài nanoseconds, timer overhead và noise có thể cùng bậc hoặc lớn hơn operation. Nếu lặp nhiều lần, compiler có thể biến đổi loop. Dùng `nanoTime` cho timing trong ứng dụng hoặc smoke check là hợp lý; dùng JMH cho microbenchmark kết luận.

Không dùng `System.currentTimeMillis()` để đo elapsed time nhỏ: wall clock có thể bị điều chỉnh và độ phân giải không phù hợp.

## 16. Profiling và điều kiện môi trường

Một score thấp hơn không cho biết nguyên nhân. Sau khi benchmark đúng, dùng profiler để tìm bottleneck:

- `-prof gc`: allocation rate và GC metrics.
- CPU sampling hoặc Java Flight Recorder: method nóng.
- Compiler activity: JIT compilation/deoptimization khi cần.
- Hardware counters: cache miss, branch miss, cycles nếu nền tảng hỗ trợ.
- Lock contention: JFR/profiler phù hợp.

Chạy baseline không profiler trước, rồi profile riêng. Profiler nặng có thể thay đổi workload.

Ghi nhận ít nhất:

| Nhóm | Thông tin |
| --- | --- |
| JDK | Vendor, version, build |
| JVM | Flags, heap size, GC |
| OS | Hệ điều hành/kernel |
| Hardware | CPU model, core count, memory |
| Container | CPU/memory limits, quota, affinity |
| Benchmark | JMH version, mode, warm-up, measurement, forks |
| Input | Kích thước, phân phối, seed, threads |
| Runtime | GC, JIT compilation, cache, background load |
| Result | Score, error, units, profiler output |

Chạy từ command line trong project đã build; tránh debugger, IDE indexing và benchmark khác cạnh tranh CPU. Giữ JDK flags, heap và power profile giống nhau khi so sánh. JMH kiểm soát harness nhưng không kiểm soát toàn bộ OS, firmware hoặc container scheduler.

## 17. Đọc kết quả và so sánh công bằng

Khi so sánh hai implementation:

1. Xác nhận chúng thực hiện cùng semantics và lượng công việc.
2. Dùng cùng JDK/vendor/build và JVM flags.
3. Dùng cùng input sizes/distribution.
4. Chạy cùng warm-up, measurement và fork settings.
5. Xem variation giữa forks và error của score.
6. Chạy lại nếu kết quả không ổn định.
7. Dùng profiler tìm nguyên nhân thay vì chỉ nhìn score.
8. Kiểm tra correctness riêng.

Không chọn kết quả tốt nhất trong nhiều lần chạy rồi công bố như average. Không so sánh hai máy khác cấu hình mà bỏ qua CPU, memory, OS, JDK và runtime flags.

**Microbenchmark không dự đoán trực tiếp latency toàn hệ thống.** Một method nhanh hơn 20% không có nghĩa request production nhanh hơn 20% nếu request bị chi phối bởi database, network, lock hoặc queueing.

## 18. Benchmark correctness và performance

JMH không thay thế unit test. Benchmark có thể chạy nhanh vì computation sai hoặc bỏ qua một phần nghiệp vụ.

Trước khi benchmark:

- Viết unit tests xác nhận output.
- Kiểm tra edge cases, input rỗng/lớn và invalid data.
- Xác nhận các benchmark variants có cùng semantics.
- Nếu state bị mutate, xác nhận trạng thái đầu vào mỗi invocation.
- Kiểm tra kết quả không bị DCE.
- Chỉ sau khi correctness đạt mới so sánh hiệu năng.

## 19. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đo lần gọi đầu tiên nhưng kết luận steady state | Trộn startup/interpreter/JIT cost | Warm-up rồi measurement |
| Warm-up input khác measurement | Profile không đại diện | Cùng workload distribution |
| Gọi computation rồi bỏ kết quả | JIT có thể xóa computation | Return hoặc Blackhole.consume |
| Dùng literal constant cho mọi input | Constant folding | @Param/runtime state |
| Volatile sink cho mọi phép đo | Đo thêm volatile/cache cost | Return hoặc Blackhole |
| Tự lặp hàng triệu lần trong benchmark | Loop unrolling/hoisting làm méo score | Một logical operation mỗi invocation |
| Random mỗi invocation khi không cần | Đo thêm random generation | Chuẩn bị input trong @Setup |
| State mutable bị thay đổi sau lần đầu | Workload warm-up/measurement khác nhau | Reset/clone state |
| Setup invocation quá nặng | Fixture overhead lấn át payload | Fixture level phù hợp |
| Chạy trong IDE/debugger | Nhiễu môi trường | Standalone JMH |
| Chỉ dùng một fork | Dễ bị ảnh hưởng JVM/profile state | Nhiều forks |
| Một measurement iteration ngắn | Score không ổn định | Đủ iterations/thời lượng |
| Gọi System.gc() trước phép đo | Thay đổi workload/GC behavior | Dùng profiler phù hợp |
| System.out.println trong timed path | Đo I/O/lock console | Không log trong timed path |
| nanoTime loop thủ công để kết luận | Thiếu harness, dễ sai do JIT | JMH |
| Input hai implementation khác nhau | So sánh không công bằng | Cùng input/parameters |
| Bỏ qua allocation | Bỏ sót GC bottleneck | Kết hợp profiler |
| Suy từ một method ra toàn service | Sai phạm vi | Integration/load test |
| Blackhole cho một kết quả đơn giản | Code benchmark khó đọc | Return result |
| @OperationsPerInvocation để “sửa” loop | Không ngăn compiler tối ưu | Thiết kế batch đúng |

## 20. Bài tập thực hành

**Bài 1 — Warm-up:** Tạo benchmark JMH với 5 warm-up và 5 measurement iterations. Chạy lại với 1 warm-up iteration. Quan sát biến động và giải thích vì sao không thể kết luận từ một lần.

**Bài 2 — DCE:** Tạo hai benchmark methods: một method bỏ kết quả, method còn lại return kết quả. Vì sao method thứ nhất có thể cho score thấp bất thường?

**Bài 3 — Constant folding:** So sánh `compute(42)` với `compute(input)` trong benchmark state. Thay input bằng `@Param` có hai giá trị. Giải thích vì sao runtime input giúp tránh đo hằng đã tính trước.

**Bài 4 — Blackhole:** Viết benchmark tạo hai kết quả độc lập và consume cả hai. Viết thêm biến thể return một kết quả đã kết hợp.

**Bài 5 — Loop:** Đo một lần cộng hai số, sau đó lặp 1.000 lần trong cùng method. Vì sao chia score cho 1.000 không tự cho ra chi phí một operation?

**Bài 6 — State:** Chạy benchmark với `Scope.Thread` và `Scope.Benchmark` cùng nhiều threads. Quan sát contention.

**Bài 7 — Setup:** Benchmark sort mảng chưa sắp xếp. Đảm bảo mỗi invocation nhận đúng trạng thái đầu vào và phân biệt chi phí copy với sort.

**Bài 8 — Profiling:** Chạy `-prof gc` trên benchmark cấp phát nhiều object. Ghi lại allocation rate.

**Bài 9 — Cold start:** Thiết kế thí nghiệm đo startup của process mới. Vì sao warm-up sẽ làm mất chính chi phí cần quan sát?

**Bài 10 — Reproducibility:** Lưu JDK, OS, CPU, JVM flags, JMH settings, input size, forks và result JSON. Chạy lại ở môi trường khác và giải thích vì sao score không thể so trực tiếp.

## 21. Checklist trước khi công bố benchmark

- Câu hỏi đo là startup, first-call, steady-state latency hay throughput?
- Benchmark method thực hiện đúng một logical operation hoặc batch đã định nghĩa?
- JIT đã có warm-up phù hợp với workload?
- Warm-up và measurement dùng cùng phân phối input?
- Kết quả computation được return hoặc consume?
- Có nguy cơ DCE do kết quả không được dùng?
- Có nguy cơ constant folding do literal/final constant?
- Input đến từ @State/@Param và phản ánh dữ liệu thật?
- Loop nội bộ có thực sự thuộc workload production?
- Có đang đo thêm random generation, logging, I/O hoặc setup không cần thiết?
- State scope đúng với concurrency?
- Fixture level có gây overhead hoặc đổi state?
- Có nhiều forks và đủ measurement iterations?
- JMH và annotation processor được cấu hình đúng?
- Benchmark chạy từ executable JAR/command line?
- Correctness được kiểm tra riêng?
- Allocation/GC hoặc profile được kiểm tra khi cần?
- Error/variation được xem xét?
- Có ghi JDK vendor/build, JVM flags, OS và CPU?
- Không suy từ microbenchmark thành latency toàn service khi chưa có integration/load test?

## 22. Tài liệu chính thức hiện hành

- OpenJDK JMH project và hướng dẫn Maven archetype: https://github.com/openjdk/jmh
- JMH Sample 08 — Dead Code Elimination: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java
- JMH Sample 09 — Blackholes: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java
- JMH Sample 10 — Constant Folding: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java
- JMH Sample 11 — Loops: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_11_Loops.java
- JMH Sample 12 — Forking: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_12_Forking.java
- JMH Sample 38 — Per-invocation setup: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_38_PerInvokeSetup.java
- JMH Core 1.37 trên Maven Central: https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core/1.37
- JMH Java Benchmark Archetype 1.37: https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-java-benchmark-archetype/1.37
- Oracle HotSpot VM FAQ — compiler optimization và dead-code elimination: https://www.oracle.com/java/technologies/hotspotfaq.html

**Ghi nhớ:** Đo hiệu năng JVM phải tách warm-up khỏi measurement khi mục tiêu là steady state. Kết quả cần được quan sát để JIT không xóa computation; input phải đến từ runtime state để tránh constant folding; loop thủ công có thể bị unroll/hoist và làm sai chi phí trên mỗi operation. Dùng JMH với forks, warm-up, measurement, state và profiler phù hợp. Ghi lại môi trường và kiểm tra correctness riêng trước khi dùng score để ra quyết định.