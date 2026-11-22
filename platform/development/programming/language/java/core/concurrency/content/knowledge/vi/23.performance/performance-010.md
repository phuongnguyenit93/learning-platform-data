# Benchmark đáng tin cậy với JMH trong Java concurrency

Khi tối ưu mã đồng thời, câu hỏi cần trả lời không chỉ là “đoạn code nào chạy nhanh hơn?” mà còn là **nhanh hơn trong điều kiện tải nào, trên phần cứng/JDK nào, với mức tranh chấp tài nguyên nào, và chênh lệch có lặp lại được không?** Java có JIT compiler, garbage collector, nhiều lớp cache, CPU scheduling, memory model và các primitive đồng bộ. Vì vậy, `System.nanoTime()` quanh một vài lời gọi rất dễ tạo kết luận sai.

**JMH (Java Microbenchmark Harness)** là công cụ của dự án OpenJDK dùng để xây dựng, chạy và phân tích benchmark cho JVM. **JMH không nằm trong thư viện chuẩn của JDK**: cần dependency, trình sinh mã benchmark (annotation processor) và cấu hình build phù hợp. JMH xử lý warmup, measurement iteration, fork JVM, worker thread và nhiều bẫy đo lường; tuy nhiên nó **không tự bảo đảm** thiết kế workload đúng với hệ thống thực.

Phạm vi bài này là **Java concurrency nói chung**: cách dùng JMH để đo `AtomicLong`, `LongAdder`, mức tranh chấp, nhóm reader/writer, cách hiểu điểm số và kiểm soát độ tin cậy. Các benchmark chỉ là chứng cứ cho workload đã đo, không thay cho kiểm thử tính đúng đắn hay benchmark end-to-end.

## 1. Vì sao đo thủ công thường sai?

Ví dụ sau **không đủ** để kết luận một primitive đồng thời “nhanh hơn”:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    counter.incrementAndGet();
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

Đoạn này là **minh họa về cách đo thiếu kiểm soát**, không phải chương trình hoàn chỉnh. Nó thiếu các yếu tố quan trọng:

- **JIT warmup / tiered compilation:** những lần gọi đầu chịu chi phí khởi tạo, interpret, profiling, compile và deoptimization. Một lần đo có thể trộn nhiều giai đoạn JVM.
- **Dead-code elimination và constant folding:** JIT có thể loại phép tính không quan sát được, thay hằng số hoặc tối ưu cả vòng lặp; kết quả có thể là thời gian của “không có công việc”.
- **Loop optimization:** tự đặt vòng lặp bên trong phép đo có thể bị unroll, vectorize hoặc có cấu trúc điều khiển khác với một invocation; cần phân biệt thao tác tính trên mỗi JMH operation.
- **Timer granularity/overhead:** phép đo quá nhỏ dễ bị nhiễu bởi chi phí đọc đồng hồ và lịch chạy.
- **GC, safepoint và OS scheduling:** luồng có thể bị dừng do thu gom rác, chuyển ngữ cảnh, tiến trình nền, điều tiết nhiệt/điện hoặc chạy trên core khác.
- **Thiếu fork:** các phép thử trong cùng một JVM có thể ảnh hưởng nhau qua code cache, profiling, trạng thái class hay static data.
- **Sai mô hình contention:** benchmark một thread không thể suy ra hiệu năng của 32 thread cùng ghi một biến; ngược lại “32 thread” cũng không đồng nghĩa với 32 lõi CPU.
- **Sai workload:** so sánh thao tác có tác dụng/độ chính xác khác nhau, dùng dữ liệu chỉ nằm trong cache, bỏ qua mức allocation hoặc đọc/ghi thực tế đều dẫn tới kết luận khó dùng.

`System.nanoTime()` là đồng hồ đơn điệu tương đối phù hợp để đo khoảng thời gian, nhưng **chỉ thay timer không giải quyết** những sai lệch còn lại. JMH là điểm bắt đầu tốt; người làm benchmark vẫn phải kiểm soát giả thuyết và dữ liệu.

## 2. Những khái niệm cốt lõi của JMH

| Khái niệm / annotation | Vai trò | Lưu ý khi đo concurrency |
| --- | --- | --- |
| `@Benchmark` | Đánh dấu phương thức được harness đo | Một invocation phải đại diện cho thao tác được định nghĩa rõ |
| `@State(Scope.Thread)` | Mỗi worker thread dùng state riêng | Phù hợp đo trường hợp không chia sẻ/tranh chấp |
| `@State(Scope.Benchmark)` | Các worker của một benchmark chia sẻ state | Phù hợp đo nhiều thread truy cập cùng đối tượng |
| `@State(Scope.Group)` | Chia sẻ state trong một group | Dùng với workload reader/writer bất đối xứng |
| `@Threads(n)` hoặc `-t n` | Số worker của benchmark | Thay số thread để tìm điểm bão hòa; không suy diễn thành số core |
| `@Group` + `@GroupThreads` | Các phương thức khác nhau cùng hoạt động trong group | Kiểm tra tương tác nhiều loại thao tác |
| `@Warmup` | Chạy trước khi thu kết quả chính | Cho JIT và trạng thái đạt giai đoạn tương đối ổn định |
| `@Measurement` | Thời gian/số vòng đo | Nhiều iteration giúp quan sát dao động |
| `@Fork` | Chạy trên JVM con riêng | Giảm ảnh hưởng trạng thái giữa các lần chạy |
| `@Param` | Thử các giá trị input có kiểm soát | Không hard-code một kích thước dữ liệu |
| `@Setup`, `@TearDown` | Chuẩn bị và dọn state theo cấp | Phân biệt mã chuẩn bị với mã thực sự được đo |
| `Blackhole` / trả về kết quả | Làm kết quả tính toán có thể quan sát | Giảm nguy cơ JIT loại công việc vô ích |

**Scope quyết định ý nghĩa benchmark:** một `AtomicLong` riêng cho mỗi thread gần như không có tranh chấp; một `AtomicLong` chung cho tất cả thread có tranh chấp cập nhật. Nếu yêu cầu là so sánh hai trường hợp, đó phải là hai cấu hình state tường minh.

**JMH operation** là đơn vị công việc harness dùng để tính điểm. Nếu một `@Benchmark` thực hiện cả lô 100 increment, thông số `ops/s` mặc định là số *lần gọi benchmark method* mỗi giây, không tự động thành 100 lần increment/giây. Có thể dùng `@OperationsPerInvocation` khi phù hợp, nhưng phải mô tả đúng mô hình và tránh đếm hai lần.

## 3. Chọn mode và đọc đơn vị đo

| Benchmark mode | Ý nghĩa | Câu hỏi phù hợp |
| --- | --- | --- |
| `Mode.Throughput` | Số operations hoàn thành / đơn vị thời gian; cao hơn thường tốt hơn | Bao nhiêu cập nhật counter/giây? |
| `Mode.AverageTime` | Thời gian trung bình / operation; thấp hơn thường tốt hơn | Một phép khóa hoặc thao tác riêng mất bao lâu trung bình? |
| `Mode.SampleTime` | Lấy mẫu thời gian để xem phân phối, percentile của thao tác được đo | Có tail lớn ở mức invocation không? |
| `Mode.SingleShotTime` | Đo một lần thực hiện; phù hợp thao tác khởi động hoặc thời gian quá ngắn/dài cần đánh giá riêng | Startup/initialization tốn bao lâu? |

Ví dụ trong `Mode.Throughput`, `Score = 7_500_000 ops/s` nghĩa là trung bình đo được khoảng 7,5 triệu **JMH operation/giây** trong workload và cấu hình đó, **không** có nghĩa dịch vụ thật xử lý được 7,5 triệu request/giây. Con số trên chỉ là ví dụ đọc đơn vị, không phải kết quả đo từ máy.

JMH thường báo `Benchmark`, `Mode`, `Cnt`, `Score`, `Error` và `Units`. `Error` đi kèm cách JMH tổng hợp các mẫu/iteration; không nên xem đây là bảo chứng rằng môi trường đã sạch hoặc workload đúng. Chênh lệch nhỏ hơn dao động đo được cần thêm bằng chứng, nhiều fork và đánh giá phân phối, không chọn một lần chạy đẹp nhất.

Trong benchmark nhiều thread, thời gian của một thao tác dưới contention còn phụ thuộc lịch chạy và số thao tác mà các thread khác thực hiện. `AverageTime` và `SampleTime` ở đây chỉ đo ranh giới `@Benchmark`, không tự động là latency end-to-end của một HTTP request, database transaction hay toàn ứng dụng.

## 4. Tạo dự án JMH độc lập có thể chạy

Cần JDK 17+ và Maven. Cách đơn giản, được dự án JMH khuyến nghị là tạo **module Maven riêng bằng archetype**, không nhúng lời gọi stopwatch vào mã production. Ví dụ ghim bản JMH **1.37** (bản phát hành được công bố trong kho Maven Central khi biên soạn):

```bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DarchetypeVersion=1.37 -DgroupId=org.example -DartifactId=jmh-concurrency -Dversion=1.0-SNAPSHOT
cd jmh-concurrency
```

Archetype tạo cấu hình POM cùng đường biên dịch code generation cần thiết. Với JMH, **chỉ thêm `jmh-core` như một thư viện Java thông thường là chưa đủ**; trình xử lý annotation phải sinh các lớp harness. Nếu tự cấu hình Maven/Gradle, cần đảm bảo `jmh-core` và `jmh-generator-annprocess` tương ứng phiên bản, cấu hình processor, đầu ra executable benchmark và dependency được đóng gói đúng.

Cấu trúc phần quan trọng sau khi tạo:

```text
jmh-concurrency/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── CounterBenchmark.java
```

Đặt lớp `CounterBenchmark` dưới package `org.example` như mã ở phần sau. Archetype cũng có thể tạo mẫu `MyBenchmark.java`; việc chạy với bộ lọc `CounterBenchmark` giúp chỉ đo bài này.

Tại thư mục gốc module:

```bash
mvn clean verify
java -jar target/benchmarks.jar -l
```

`-l` liệt kê benchmark được generator phát hiện. Nếu danh sách không có phương thức bạn mới viết, cần kiểm tra package/class, annotation processor, file đặt đúng nguồn và build success. Sau đó chạy bằng `java -jar target/benchmarks.jar`; xem `-h` để biết đầy đủ tùy chọn CLI có trong JMH đang cài.

Tài liệu chính thức:

- [OpenJDK JMH – dự án, cách tạo archetype và chạy CLI](https://github.com/openjdk/jmh)
- [JMH Samples – các ví dụ nguồn về scope, group, blackhole và bẫy đo](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples)
- [JMH Core 1.37 API](https://javadoc.io/doc/org.openjdk.jmh/jmh-core/1.37)

## 5. Ví dụ chạy được: AtomicLong và LongAdder dưới contention

Hai primitive đều hỗ trợ đếm đồng thời nhưng **không có cùng hợp đồng đọc kết quả**: `AtomicLong.get()` cho phép lấy giá trị nguyên tử với semantics mạnh; `LongAdder.sum()` là phép tổng hợp, không phải snapshot nguyên tử khi còn concurrent updates. Benchmark sau **chỉ đo thao tác tăng bộ đếm**, không chứng minh hai loại hoán đổi được trong mọi API.

Tạo file `src/main/java/org/example/CounterBenchmark.java`:

```java
package org.example;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

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
@Warmup(iterations = 3, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class CounterBenchmark {
    private final AtomicLong atomic = new AtomicLong();
    private final LongAdder adder = new LongAdder();

    @Benchmark
    public void atomicIncrement() {
        atomic.incrementAndGet();
    }

    @Benchmark
    public void adderIncrement() {
        adder.increment();
    }
}
```

Giải thích thiết kế:

- `@State(Scope.Benchmark)` làm **mọi worker của từng benchmark chia sẻ cùng counter instance**, qua đó đo contention khi `-t` lớn hơn 1. Các benchmark method được JMH điều phối như các workload riêng, không phải hai bộ đếm cùng chịu tải đồng thời.
- Hai phương thức cùng thực hiện **một cập nhật trên đối tượng chia sẻ** mỗi invocation. Không thêm vòng lặp lớn vào trong benchmark và không cấp phát counter mới ở mỗi invocation.
- Trạng thái đếm thay đổi là side effect thực, quan sát được từ nhiều thread, nên khác một phép tính thuần có thể bị xóa; vẫn cần kiểm tra giả thuyết benchmark không bị JIT tối ưu làm sai.
- `@Warmup` và `@Measurement` xác định thời lượng của từng vòng; `@Fork(2)` yêu cầu hai JVM fork để cải thiện bằng chứng độc lập. Chúng là **giá trị minh họa bắt đầu**, nên điều chỉnh khi độ ổn định chưa đủ.

Biên dịch và chạy hai điều kiện **tách biệt**:

```bash
mvn clean verify
java -jar target/benchmarks.jar CounterBenchmark -t 1
java -jar target/benchmarks.jar CounterBenchmark -t 4
```

`-t 1` đo khi không có nhiều worker tranh cùng counter; `-t 4` đo bốn worker cùng đụng state chia sẻ. Kết quả số **phụ thuộc CPU, JDK, cài đặt JVM, tải máy và cả workload**; không có stdout điểm số cố định để chép lại. Khi đọc báo cáo, kiểm tra tên đầy đủ gồm `atomicIncrement` / `adderIncrement`, số thread, `Mode=thrpt`, đơn vị `ops/s` và biến động giữa fork/iteration.

Nếu `LongAdder` dẫn đầu khi nhiều thread ghi, kết luận hợp lệ chỉ là “trong workload **write-only increment** được định nghĩa ở đây, trên máy và cấu hình thử nghiệm này, throughput cao hơn.” Nó **không** chứng minh `LongAdder` luôn nhanh hơn với tần suất `sum()` cao, giới hạn bộ nhớ chặt hoặc yêu cầu snapshot nhất quán.

Có thể chạy thêm số thread `1, 2, 4, 8, ...` (giới hạn theo máy, quan sát số logical/physical cores) và vẽ đường throughput theo thread. Điểm bắt đầu bão hòa có thể khác nhau giữa máy ít core, CPU đa socket và phiên bản JDK. Không so sánh hai primitive khi một bài được chạy với số thread hoặc JVM flags khác bài còn lại.

## 6. Ví dụ chạy được: nhóm đọc/ghi bất đối xứng với @Group

Một benchmark chỉ có writers không mô phỏng hệ thống có nhiều reader và ít writer. JMH có `@Group` để đặt các phương thức benchmark khác nhau trong **cùng nhóm hoạt động đồng thời**, và `@GroupThreads` để chọn số worker của mỗi loại.

Tạo thêm file `src/main/java/org/example/ReadWriteGroupBenchmark.java`:

```java
package org.example;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Group;
import org.openjdk.jmh.annotations.GroupThreads;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 3, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class ReadWriteGroupBenchmark {

    @State(Scope.Group)
    public static class Counter {
        final AtomicLong value = new AtomicLong();
    }

    @Benchmark
    @Group("readWrite")
    @GroupThreads(3)
    public long read(Counter state) {
        return state.value.get();
    }

    @Benchmark
    @Group("readWrite")
    @GroupThreads(1)
    public long write(Counter state) {
        return state.value.incrementAndGet();
    }
}
```

Chạy:

```bash
mvn clean verify
java -jar target/benchmarks.jar ReadWriteGroupBenchmark -t 4
```

Một group có **3 worker chỉ đọc và 1 worker ghi**, cùng `Counter` thuộc `Scope.Group`. `-t 4` tạo một group đầy đủ. Nếu tăng thread lên bội số của 4, JMH có thể tạo nhiều group độc lập và các group không nhất thiết tranh cùng một `Counter`; để đo **một điểm dữ liệu chia sẻ với nhiều readers/writers**, phải thiết kế state/scope phù hợp.

Báo cáo group có kết quả tổng hợp và các dòng phụ theo phương thức. Tỉ lệ **3 reader threads : 1 writer thread không có nghĩa** số thao tác đọc : ghi sẽ bằng 3:1, vì tốc độ mỗi loại khác nhau. Một thao tác read thường ít chi phí hơn update. Benchmark này minh họa đọc/ghi trên **atomic counter**, không đại diện tự động cho `ReentrantReadWriteLock`, database workload hoặc chuỗi xử lý ứng dụng.

## 7. Thiết kế workload để so sánh có ý nghĩa

Trước khi viết `@Benchmark`, hãy ghi ra giả thuyết bằng lời:

> “Khi N thread cùng tăng một counter chia sẻ, thông lượng increment của LongAdder cao hơn AtomicLong với điều kiện người dùng không cần đọc snapshot chính xác khi đang có writers.”

Từ giả thuyết đó cần nêu **điều giữ cố định**, **biến độc lập** và **biến quan sát**. Với ví dụ ở trên: giữ máy/JDK/JVM flags, warmup, duration, fork và phương pháp gọi; biến số thread và primitive; quan sát throughput, phương sai, allocation, CPU và GC. Đặt baseline thật sự liên quan: nếu production có 99% reads, benchmark write-only không phải cơ sở chọn primitive.

**State/thread sharing:** đo cả `Scope.Thread` (không share) và `Scope.Benchmark` (share) khi muốn tách chi phí bản thân thao tác khỏi chi phí contention. Đừng vô tình để mỗi worker tạo đối tượng của riêng mình rồi kết luận shared concurrent primitive “không tranh chấp”.

**Kích cỡ dữ liệu:** dùng `@Param` cho array size, số entry, tỷ lệ hit/miss, công việc trong critical section hoặc số striping; kiểm tra rằng input của các variant tương đương. Có thể khởi tạo dữ liệu ở `@Setup(Level.Trial)` nếu muốn chỉ đo operation, nhưng nếu production luôn tạo dữ liệu trong request thì cần benchmark cấp cao hơn có tính cả chi phí ấy.

Ví dụ **trích đoạn để ghép vào một lớp benchmark có chú giải JMH phù hợp**, không phải tệp Java độc lập:

```java
@State(Scope.Thread)
public static class Input {
    @Param({"64", "4096"})
    public int size;

    public int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < size; i++) {
            values[i] = i;
        }
    }
}

@Benchmark
public long sum(Input input) {
    long result = 0;
    for (int value : input.values) {
        result += value;
    }
    return result;
}
```

Hãy import `State`, `Scope`, `Param`, `Setup`, `Level` và `Benchmark` khi ghép đoạn trên. Trả về `result` giúp harness quan sát đầu ra thay vì để vòng lặp chỉ có tính toán vô dụng. Tuy nhiên dữ liệu khởi tạo cố định có thể tạo lợi thế cache/JIT không giống production; nếu đầu vào ngoài đời thay đổi, cần mô hình hóa biến thiên đó.

**Trạng thái trước mỗi lần đo:** `@Setup(Level.Trial)` chạy theo trial, `@Setup(Level.Iteration)` theo iteration và `@Setup(Level.Invocation)` theo invocation; tương tự có `@TearDown`. Không đặt khởi tạo nặng ở cấp invocation nếu mục đích là đo đúng một thao tác nhỏ. Ngược lại, benchmark cấu trúc có dữ liệu tích lũy không giới hạn có thể thay đổi về độ khó qua thời gian; cần reset có kiểm soát hoặc đo cả quá trình tích lũy theo chủ đích.

**Tính tương đương:** thao tác có cùng tên như “insert”, “increment” hoặc “lock” chưa chắc giống về semantics. `LongAdder.sum()` không cung cấp snapshot nguyên tử như một `AtomicLong.get()` đang có cập nhật đồng thời. Thứ tự fairness, memory visibility, thuật toán fallback, tác động lên GC và độ chính xác dữ liệu đều có thể là khác biệt sản phẩm, không chỉ chênh lệch `ops/s`.

## 8. Blackhole, dead-code elimination và escape analysis

Nếu một method tính toán số học rồi bỏ kết quả, JIT có thể loại hết vì không quan sát được:

```java
@Benchmark
public void broken() {
    double x = Math.sqrt(123.456);
    // x is unused; this can be optimized away.
}
```

Đây là **trích đoạn minh họa không độc lập**, không có import/class wrapper. Để tính toán có ý nghĩa, có thể **trả về kết quả** từ method benchmark hoặc nhận `org.openjdk.jmh.infra.Blackhole` để `consume(...)` kết quả:

```java
@Benchmark
public void consumeResult(Blackhole blackhole) {
    double x = Math.sqrt(123.456);
    blackhole.consume(x);
}
```

Cần import `@Benchmark` và `Blackhole` trong lớp JMH của mình. Trả về giá trị cũng thường là giải pháp đơn giản; `Blackhole` hữu ích khi muốn tiêu thụ nhiều giá trị hoặc dữ liệu phức tạp.

**Đừng lạm dụng Blackhole:** phép tiêu thụ là một phần có overhead; trong phép đo cực nhỏ, overhead có thể tương đối lớn. Không dùng Blackhole để “cứu” một benchmark đang không làm công việc giống production. JMH giúp chống loại bỏ phép tính, nhưng vẫn phải xét constant folding, dead stores, escape analysis, scalar replacement và compiler intrinsics; khi nghi ngờ, đổi input, kiểm tra disassembly/JIT profile nếu công cụ sẵn có và benchmark workload lớn hơn.

**Không đặt phép thử vào một vòng lặp tự chế quá dài** chỉ để có số đo “đẹp”. JMH đã lo việc lặp invocation và thời gian đo. Nếu mỗi operation bắt buộc là một batch, định nghĩa rõ batch size và số operations tương ứng.

## 9. Đo đồng thời: contention, false sharing, scheduling và blocking

**Contention:** throughput có thể tăng khi có 2–4 thread rồi giảm ở 16–32 thread do giao tiếp cache coherence, CAS retries, lock contention hay bão hòa memory bandwidth. Kiểm tra từng mức thread, phân biệt CPU hữu ích với thời gian blocked/waiting. “Nhiều thread hơn” chỉ tăng cơ hội làm việc song song khi thực sự còn tài nguyên và thuật toán cho phép.

**False sharing:** hai biến logic độc lập nhưng nằm gần nhau trên cùng cache line có thể tạo cache-line ping-pong giữa core. Một benchmark với `@State(Scope.Benchmark)` chứa nhiều trường cập nhật bởi thread khác nhau có thể đo chi phí false sharing ngoài ý định. Kiểm tra layout, ownership per-thread, memory padding và phương án dữ liệu trước khi kết luận thuật toán kém. Không dùng kết quả microbenchmark để khẳng định chính xác cache-line size trên mọi CPU/JVM.

**Thread pinning, affinity và CPU topology:** OS có thể di chuyển luồng giữa các core, SMT siblings chia sẻ tài nguyên, CPU đa socket có đường truy cập bộ nhớ khác nhau. Khi cần so sánh khoa học, ghi lại số physical/logical cores, topology, power governor và cơ chế cố định CPU affinity nếu môi trường hỗ trợ. Không mặc định chạy trên laptop đang cắm/sạc ở hai lần đo là điều kiện giống nhau.

**Blocking khác CPU-bound:** tăng `@Threads` trên một phép increment CPU-bound không tương đương đo một tác vụ phải đợi I/O hoặc đợi `LockSupport.park`. Một benchmark throughput cho executor, lock hay queue cần mô hình hóa producer/consumer, tỷ lệ enqueue/dequeue, batch, thời gian giữ lock, thread count và khả năng tiến triển khi blocking. Benchmark dùng virtual thread (nếu chạy trên JDK hỗ trợ) vẫn phải xác định scheduler, điểm blocking và tài nguyên downstream; không thể suy ra từ kết quả platform-thread microbenchmark.

**Thời gian dừng JVM:** GC/safepoint, class loading hoặc JVM compilation có thể tạo outlier; warmup giúp nhưng không xóa hết. Nếu method cấp phát, xem profile allocation và GC pressure. Một variant nhanh hơn về CPU nhưng phát sinh nhiều allocation hoặc tăng tail latency thực tế có thể không phải lựa chọn tốt.

**Đúng chức năng trước khi đo:** JMH không phát hiện linearizability bug, deadlock, race hay memory visibility vi phạm. Unit test, stress test và công cụ như JCStress (cũng nằm ngoài JDK) kiểm thử tính đúng đắn đồng thời; JMH trả lời câu hỏi **hiệu năng**, không thay các phép kiểm chứng ấy.

## 10. Quy trình thực nghiệm có thể tái lập

### Bước 1: Phát biểu giả thuyết và thước đo

Viết rõ workload, phần mềm, số thread, loại state, data size, read/write ratio, thao tác đo và ý nghĩa thắng/thua. Chọn primary metric trước khi xem kết quả, chẳng hạn throughput của một increment đã được chấp nhận. Nếu metric không phản ánh mục tiêu hệ thống, thay thiết kế thử nghiệm.

### Bước 2: Cố định điều kiện và build sạch

Ghi JDK vendor/version, JMH version, hệ điều hành, CPU, core/SMT, RAM, JVM flags, GC, heap size và commit của mã benchmark + mã được đo. Không nên chạy đo trong IDE khi muốn số liệu có thể đối chiếu: môi trường và build/JMH annotation-processing có thể khác CLI. Đảm bảo cùng cách build, cùng binary/config cho các variant.

Chạy benchmark trên máy ít tác vụ nền, giữ nguồn điện và thermal ổn định. Với CI chạy trên máy chia sẻ, điểm số phù hợp làm tín hiệu tham khảo và phát hiện regression lớn, không chắc đáng tin để so các chênh lệch vài phần trăm.

### Bước 3: Chạy thử, sau đó chạy đầy đủ

Trước tiên dùng phép chạy ngắn để xác nhận command, nguồn có đúng JMH benchmark, state và kết quả không bất thường. Sau đó chạy warmup/measurement/fork đủ dài; có thể tăng fork và duration nếu mỗi iteration dao động mạnh.

Ví dụ chạy cấu hình 4 threads, 2 fork, 3 warmup iteration, 5 measurement iteration; mỗi iteration 1 giây:

```bash
java -jar target/benchmarks.jar CounterBenchmark -t 4 -f 2 -wi 3 -i 5 -w 1s -r 1s -bm thrpt -tu s
```

Ý nghĩa các cờ:

| Cờ | Ý nghĩa |
| --- | --- |
| `-t 4` | Số worker thread JMH |
| `-f 2` | Hai fork JVM riêng |
| `-wi 3` | Ba warmup iteration |
| `-i 5` | Năm measurement iteration |
| `-w 1s` | Thời lượng mỗi warmup iteration |
| `-r 1s` | Thời lượng mỗi measurement iteration |
| `-bm thrpt` | Throughput mode |
| `-tu s` | Đơn vị thời gian giây |
| `-rf json`, `-rff file.json` | Ghi kết quả dưới dạng JSON ra tệp được chỉ định |

Cần lưu artifact máy và cấu hình đã dùng cùng mỗi file JSON:

```bash
java -jar target/benchmarks.jar CounterBenchmark -t 4 -f 2 -wi 3 -i 5 -w 1s -r 1s -bm thrpt -tu s -rf json -rff counter-t4.json
```

Không có **stdout benchmark cố định**: kết quả thực tế thay đổi theo máy, môi trường và lần chạy. Lấy `Score` và `Error` từ chính run, không gán số tưởng tượng cho từng primitive.

### Bước 4: Thay đúng một biến, quan sát cả đường cong

Dùng cùng JVM flags và cấu hình benchmark, lần lượt chạy `-t 1`, `-t 2`, `-t 4`, `-t 8` rồi mở rộng nếu phần cứng và mục tiêu cần. Chạy lại toàn bộ cặp so sánh khi đổi JDK hoặc CPU; không ghép số đo của hai máy khác nhau vào một tỷ lệ speedup đơn giản.

Trong từng cấu hình, thử lặp lại ở nhiều thời điểm/đợt nếu môi trường nhiễu, và ghi độ phân tán. Đừng chỉ giữ fork có kết quả thuận ý. Xem thêm CPU utilization, GC, allocation, lock contention và nhiệt độ nếu kết quả đảo chiều hoặc dao động lớn.

### Bước 5: Giải thích kết quả theo phạm vi

Một kết luận tốt có dạng:

> “Với bốn JMH worker cùng cập nhật một counter chung, trên JDK X, CPU Y, cùng warmup/fork/duration, thuật toán A có throughput cao hơn B trong bài thử increment-only; cần xác nhận với tỷ lệ reads/writes thực tế và yêu cầu consistency trước khi thay mã production.”

Chỉ khẳng định ý nghĩa thống kê sau khi xem sai số, phân phối và số lần chạy đủ; một khoảng `Error` nhỏ không khắc phục được **systematic bias**. Nếu chênh lệch gần mức nhiễu, kết luận hợp lý có thể là “chưa có bằng chứng rõ ràng” và ưu tiên giải pháp đơn giản/đúng hợp đồng.

## 11. Profiling và khả năng giải thích kết quả

JMH hỗ trợ profiler tích hợp hoặc plugin tùy môi trường. Có thể kiểm tra các profiler sẵn có:

```bash
java -jar target/benchmarks.jar -lprof
```

Ví dụ profiler `gc` cung cấp một số thông tin như cấp phát/GC khi phiên bản và JVM hỗ trợ:

```bash
java -jar target/benchmarks.jar CounterBenchmark -t 4 -prof gc
```

Không mặc định mọi profiler (hardware counters, perf, assembly) có sẵn: thường cần OS/tool hỗ trợ, quyền truy cập perf counters hoặc JVM flags bổ sung. Profiler cũng có overhead; không đánh đồng điểm số có profiler với baseline không profiler mà không xét tác động.

Khi một benchmark lock hoặc queue có throughput bất ngờ, kiểm tra:

- CPU ở mức cao vì đang làm việc thật hay vì spinning/CAS contention?
- Blocked time và parking có phản ánh lock contention?
- Allocation rate/GC khác nhau bao nhiêu?
- Cache/false sharing, data locality hoặc branch prediction có đổi theo input?
- Throughput đã chạm bottleneck memory bandwidth, CPU scheduling hay synchronization?

Tốt nhất đo theo hai tầng: **JMH microbenchmark** để cô lập cơ chế và **application/load benchmark** để kiểm tra tài nguyên, latency, p95/p99 và throughput trong luồng thực tế. Một “chiến thắng” vài nano giây ở primitive có thể bị chi phí I/O hoặc serialization che hoàn toàn ở hệ thống thật.

## 12. Các lỗi thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chạy một lần, không warmup/fork | Trộn startup, JIT và nhiễu JVM | Warmup, nhiều iteration, nhiều fork và lưu raw results |
| Kết quả không được dùng | JIT loại phép tính hoặc biến mã thành hằng | Trả về kết quả/`Blackhole`, kiểm chứng side effect |
| Tạo đối tượng trong method vô ý | Đang đo allocation thay vì operation | `@Setup` chuẩn bị state nếu đúng với giả thuyết |
| Reset state sai | Giữ dữ liệu cũ gây drift hoặc reset phá workload | Định nghĩa rõ lifecycle và logic reset |
| Dùng `Scope.Thread` khi muốn shared contention | Bỏ lỡ chi phí đồng bộ giữa thread | `Scope.Benchmark` hoặc `Scope.Group` |
| Dùng `Scope.Benchmark` khi muốn per-thread | Tạo contention giả | `Scope.Thread` |
| So hai primitive khác hợp đồng | “Nhanh hơn” nhưng tính đúng đắn khác | So semantics, visibility, atomicity và workload |
| Đọc throughput như latency | Suy ra sai khả năng phục vụ người dùng | Chọn mode, unit và ranh giới đo phù hợp |
| Dùng 32 thread trên máy nhỏ và gọi đó là scale tuyến tính | Bị ảnh hưởng oversubscription/scheduling | Thử nhiều mức thread và ghi CPU topology |
| Đặt vòng lặp lớn bên trong `@Benchmark` vô cớ | Đếm sai operations, optimizer thay đổi semantics | Một thao tác/invocation hoặc khai báo batch minh bạch |
| Thử trên IDE/máy đang quá tải rồi so điểm | Không tái lập, nhiễu cao | Dùng build và CLI ổn định, lưu environment |
| Tối ưu từ số đo nhỏ, không có workload thực | Regression ở latency, memory hay correctness | Theo dõi end-to-end và thực hiện test chức năng |
| Cho rằng JMH thay test race | Benchmark chạy nhanh dù sai kết quả | Unit/stress/JCStress cho correctness |

## 13. Bài thực hành đề xuất

1. Chạy `CounterBenchmark` ở `-t 1` và `-t 4`, ghi lại hai primitive và đơn vị của chúng. Nếu thứ hạng thay đổi, giải thích theo mức tranh chấp và đặc điểm `LongAdder`.
2. Chạy `-t 2`, `-t 8` trên cùng máy nếu tài nguyên phù hợp. Vẽ throughput theo số thread cho mỗi primitive; chỉ ra chỗ tăng chậm hoặc giảm.
3. Chạy `ReadWriteGroupBenchmark` với group 3 read + 1 write. Đối chiếu throughput phụ của reader và writer; giải thích vì sao số lượng thao tác đọc/ghi không bằng tỷ lệ thread.
4. Thử tăng `-f` và `-r` khi kết quả bất ổn; so phương sai giữa hai cấu hình và ghi chi phí thời gian thực nghiệm.
5. Thêm một trường hợp đọc thường xuyên từ `LongAdder.sum()` và kiểm tra **đúng ngữ nghĩa cần thiết** trước khi so hiệu năng với `AtomicLong.get()`.
6. Viết báo cáo một đoạn có JDK/JMH version, phần cứng, cấu hình, Score/Error/Units và giới hạn suy diễn. Không báo cáo “X nhanh hơn Y mọi nơi” chỉ từ một tổ hợp.

## 14. Checklist trước khi tin một kết quả JMH

- [ ] Giả thuyết, thao tác đo và đơn vị `op` đã được định nghĩa rõ.
- [ ] Mọi phương án có **tính đúng đắn và semantics được chấp nhận** cho bài toán.
- [ ] State scope, thread count, group composition đúng mức chia sẻ tài nguyên muốn mô phỏng.
- [ ] Đã xem xét DCE, constant folding, escape analysis, allocation và benchmark loop.
- [ ] Warmup, measurement, forks và duration đủ để kết quả lặp lại; không lựa chọn run tốt nhất.
- [ ] JDK, JMH, JVM flags, CPU, OS và binary mã nguồn đã được ghi nhận.
- [ ] Điểm số được đọc đúng `Mode`/`Units` và có phân tích variation.
- [ ] Kết luận ghi chính xác phạm vi workload; thay đổi production được xác nhận qua profiling và load test.

**Nguyên tắc cốt lõi:** JMH giúp phép đo Java concurrency có cấu trúc và lặp lại được, nhưng chất lượng kết luận phụ thuộc vào việc chọn **workload đúng, scope đúng, số worker đúng, đối chứng đúng và môi trường đo đủ ổn định**. Số liệu chỉ đáng tin khi người khác có thể chạy lại cùng mã/cấu hình, kiểm tra sai số và hiểu rõ phép đo đang đại diện cho điều gì.